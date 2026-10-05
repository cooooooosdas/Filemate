"""预览、创建、校验和暂存恢复托管数据快照。"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import stat
import time
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from filemate.execution.storage import _MIGRATIONS

FORMAT_VERSION = 1
MAX_MANIFEST_BYTES = 8 * 1024 * 1024
DATABASE_TIMEOUT_SECONDS = 60


def _digest(value: Any) -> str:
    """生成稳定的预览指纹。"""
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _file_digest(path: Path) -> str:
    """分块校验文件而不输出内容。"""
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def _check_node(path: Path) -> None:
    """拒绝链接、重解析点和特殊文件。"""
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
        raise ValueError("托管目录中存在链接或重解析点，拒绝跟随")
    if not stat.S_ISDIR(info.st_mode) and not stat.S_ISREG(info.st_mode):
        raise ValueError("托管目录包含特殊文件")
    if stat.S_ISREG(info.st_mode) and info.st_nlink > 1:
        raise ValueError("托管文件存在硬链接，无法确认独立数据边界")


def _relative(value: str) -> PurePosixPath:
    """只接受可跨平台恢复的相对文件名。"""
    if not isinstance(value, str) or not value or "\\" in value:
        raise ValueError("快照文件名非法")
    path = PurePosixPath(value)
    if path.is_absolute() or path.as_posix() != value:
        raise ValueError("快照文件名必须是规范相对路径")
    for part in path.parts:
        if part in {".", ".."} or ":" in part or part.rstrip(" .") != part:
            raise ValueError("快照文件名越过数据边界")
        if re.fullmatch(r"(?i)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?", part):
            raise ValueError("快照文件名包含系统保留名称")
    return path


def _database_path(relative: str) -> bool:
    """识别现役主库和匿名分库。"""
    return relative == "filemate.db" or bool(
        re.fullmatch(r"users/u_[0-9a-f]{32}/filemate\.db", relative)
    )


def _managed_path(relative: str, directory: bool) -> bool:
    """限定现役网站数据卷布局。"""
    parts = _relative(relative).parts
    if parts[0] in {'privacy-tombstones', 'privacy-activity'}:
        return (directory and len(parts) == 1) or (not directory and len(parts) == 2 and bool(re.fullmatch(r'[0-9a-f]{64}\.json', parts[1])))
    if parts[0] in {"inbox", "archive"}:
        return directory or len(parts) > 1
    if parts[0] == "users":
        if len(parts) == 1:
            return directory
        if not re.fullmatch(r"u_[0-9a-f]{32}", parts[1]):
            return False
        if len(parts) == 2:
            return directory
        if parts[2] in {"inbox", "archive"}:
            return directory or len(parts) > 3
        return (
            not directory
            and len(parts) == 3
            and parts[2]
            in {
                "filemate.db",
                "filemate.db-wal",
                "filemate.db-shm",
                "filemate.db-journal",
                "filemate.backup-secret",
            }
        )
    return (
        not directory
        and len(parts) == 1
        and parts[0]
        in {
            "filemate.db",
            "filemate.db-wal",
            "filemate.db-shm",
            "filemate.db-journal",
            "identity.secret",
            "filemate.backup-secret",
        }
    )


def _walk(root: Path) -> tuple[list[str], list[str]]:
    """遍历前校验目录边界，保留空目录。"""
    _check_node(root)
    directories, files = [], []
    for current, folders, names in os.walk(root, followlinks=False):
        relative_parent = Path(current).relative_to(root).as_posix()
        for folder in tuple(folders):
            # 临时预览/已提交删除的暂存副本不得进入可恢复业务快照。
            if (folder == '_working' and (relative_parent == '.' or re.fullmatch(r'users/u_[0-9a-f]{32}', relative_parent))) or re.fullmatch(r'\.personal-rollback-[0-9a-f]{32}', folder):
                _check_node(Path(current) / folder)
                folders.remove(folder)
        for name in sorted(folders + names):
            item = Path(current) / name
            _check_node(item)
            relative = item.relative_to(root).as_posix()
            _relative(relative)
            (directories if item.is_dir() else files).append(relative)
    return sorted(directories), sorted(files)


def _readonly_connection(path: Path) -> sqlite3.Connection:
    """无WAL时禁止建立侧文件，有WAL时只读现有共享索引。"""
    wal, shm = Path(str(path) + "-wal"), Path(str(path) + "-shm")
    has_wal = wal.exists() and wal.stat().st_size > 0
    if has_wal:
        _check_node(wal)
        if not shm.is_file():
            raise ValueError("已提交WAL缺少共享索引，需先恢复数据库并完成停写")
        _check_node(shm)
    suffix = "?mode=ro" if has_wal else "?mode=ro&immutable=1"
    return sqlite3.connect(path.as_uri() + suffix, uri=True, timeout=5)


def _database_facts(path: Path) -> dict[str, Any]:
    """只读核对数据库完整性和表记录数。"""
    started = time.monotonic()
    with closing(_readonly_connection(path)) as conn:
        conn.set_progress_handler(
            lambda: int(time.monotonic() - started > DATABASE_TIMEOUT_SECONDS),
            10000,
        )
        if conn.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
            raise ValueError("数据库完整性检查失败")
        if conn.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise ValueError("数据库外键检查失败")
        tables = [
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        ]
        if "schema_migrations" not in tables:
            raise ValueError("数据库缺少FileMate迁移记录")
        versions = [
            row[0] for row in conn.execute("SELECT version FROM schema_migrations ORDER BY version")
        ]
        if not versions or not all(isinstance(value, int) for value in versions):
            raise ValueError("数据库迁移版本非法")
        version = versions[-1]
        required = {value[0] for value in _MIGRATIONS if value[0] <= version}
        # v10/v11属于历史分支；现役迁移列表不要求新库生成它们。
        allowed = {value[0] for value in _MIGRATIONS} | {10, 11}
        if not required.issubset(versions) or not set(versions).issubset(allowed):
            raise ValueError("数据库版本超出现役支持或缺少必要迁移")
        counts = {
            name: conn.execute('SELECT COUNT(*) FROM "' + name.replace('"', '""') + '"').fetchone()[
                0
            ]
            for name in sorted(tables)
        }
        references = []
        for name, columns in {
            "sessions": ["source_path"],
            "sources": ["source_path"],
            "execution_records": ["source_path", "dest_path", "ics_path"],
        }.items():
            if name in tables:
                for column in columns:
                    references.extend(
                        row[0]
                        for row in conn.execute(
                            f'SELECT "{column}" FROM "{name}" WHERE "{column}" IS NOT NULL'
                        )
                    )
        return {
            "schema_version": version,
            "table_counts": counts,
            "path_references": references,
        }


def _identity(root: Path) -> tuple[bytes | None, str]:
    """保留服务实际使用的身份密钥，环境配置优先。"""
    configured = os.environ.get("FILEMATE_IDENTITY_SECRET", "").strip()
    if configured:
        encoded, origin = configured.encode("utf-8"), "environment"
    elif (root / "identity.secret").is_file():
        encoded, origin = (root / "identity.secret").read_bytes().strip(), "file"
    else:
        return None, "absent"
    if len(encoded) < 32:
        raise ValueError("身份密钥无效，不能创建可恢复的匿名快照")
    return encoded, origin


def plan_backup(data_dir: Path) -> dict[str, Any]:
    """只读预览托管数据和确认指纹。"""
    _check_node(data_dir)
    root = data_dir.resolve()
    directories, files = _walk(root)
    for relative in directories + files:
        if not _managed_path(relative, relative in directories):
            raise ValueError("数据目录包含未支持的布局；不进行不完整备份")
    secret, origin = _identity(root)
    if any(value.startswith("users/u_") for value in directories) and secret is None:
        raise ValueError("匿名用户数据缺少有效身份密钥")
    if secret is not None and "identity.secret" not in files:
        files.append("identity.secret")
    entries = []
    for relative in sorted(files):
        path = root / relative
        if relative == "identity.secret":
            entries.append(
                {
                    "path": relative,
                    "kind": "identity",
                    "bytes": len(secret or b""),
                    "sha256": hashlib.sha256(secret or b"").hexdigest(),
                }
            )
            continue
        entry: dict[str, Any] = {
            "path": relative,
            "bytes": path.stat().st_size,
            "sha256": _file_digest(path),
            "kind": "database" if _database_path(relative) else "file",
        }
        if _database_path(relative):
            entry["database"] = _database_facts(path)
            references = entry["database"].pop("path_references")
            entry["external_reference_count"] = sum(
                (PurePosixPath(value).is_absolute() or PureWindowsPath(value).is_absolute())
                and not Path(value).resolve().is_relative_to(root)
                for value in references
                if isinstance(value, str)
            )
        elif relative.endswith((".db-wal", ".db-shm", ".db-journal")) and _database_path(
            relative.rsplit("-", 1)[0]
        ):
            if relative.endswith("-shm"):
                # SHM由读取连接维护，不能把其瞬时字节作为数据变化证据。
                continue
            if relative.endswith("-journal"):
                raise ValueError("存在回滚日志，需先完成数据库恢复再备份")
            if entry["bytes"] == 0:
                continue
            entry["kind"] = "wal"
        entries.append(entry)
    if not any(entry["kind"] == "database" for entry in entries):
        raise ValueError("没有可备份的FileMate数据库")
    result: dict[str, Any] = {
        "format_version": FORMAT_VERSION,
        "source_root": str(root),
        "identity_origin": origin,
        "directories": directories,
        "entries": entries,
        "consistency": "quiesced managed files; SQLite backup includes committed WAL",
    }
    result["confirmation"] = _digest(result)
    return result


def _new_target(target: Path, source: Path) -> Path:
    """拒绝覆盖、嵌套输出和不明确的父目录。"""
    if target.exists() or target.is_symlink():
        raise ValueError("目标已存在，禁止覆盖；请选择尚不存在的新目录")
    _check_node(target.parent)
    resolved = target.resolve()
    if resolved.is_relative_to(source) or source.is_relative_to(resolved):
        raise ValueError("输出与输入目录不能嵌套")
    return resolved


def _write(path: Path, content: bytes) -> None:
    """独占创建私有文件，绝不覆盖已有内容。"""
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())


def _copy(source: Path, target: Path) -> None:
    """只复制普通文件到独占创建的目标。"""
    _check_node(source)
    with source.open("rb") as src:
        descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as dst:
            for chunk in iter(lambda: src.read(1024 * 1024), b""):
                dst.write(chunk)
            dst.flush()
            os.fsync(dst.fileno())


def _copy_database(source: Path, target: Path) -> None:
    """使用SQLite备份接口合并已提交WAL，保留原schema。"""
    _write(target, b"")
    started = time.monotonic()

    def progress(_status: int, _remaining: int, _total: int) -> None:
        if time.monotonic() - started > DATABASE_TIMEOUT_SECONDS:
            raise TimeoutError("数据库备份超时，输出不作为成功快照")

    with (
        closing(_readonly_connection(source)) as src,
        closing(sqlite3.connect(target)) as dst,
    ):
        src.backup(dst, pages=256, progress=progress, sleep=0.05)


def create_backup(
    data_dir: Path, out: Path, confirmation: str, *, quiesced: bool
) -> dict[str, Any]:
    """确认停写和原预览后创建完整快照。"""
    if not quiesced:
        raise ValueError("附件与多库需要统一停写，请停止服务后显式确认quiesced")
    plan = plan_backup(data_dir)
    if confirmation != plan["confirmation"]:
        raise ValueError("数据已变化或确认指纹不匹配，请重新预览")
    if any(entry.get("external_reference_count") for entry in plan["entries"]):
        raise ValueError("数据库引用托管目录外的文件，本工具不创建不完整快照")
    root = Path(plan["source_root"])
    target = _new_target(out, root)
    target.mkdir(mode=0o700)
    payload = target / "data"
    payload.mkdir(mode=0o700)
    for relative in plan["directories"]:
        (payload / relative).mkdir(mode=0o700, parents=True, exist_ok=True)
    saved = []
    secret, _origin = _identity(root)
    for entry in plan["entries"]:
        if entry["kind"] == "wal":
            continue
        relative = entry["path"]
        destination = payload / relative
        if entry["kind"] == "identity":
            _write(destination, secret or b"")
        elif entry["kind"] == "database":
            _copy_database(root / relative, destination)
        else:
            _copy(root / relative, destination)
        copied = {
            "path": relative,
            "kind": entry["kind"],
            "bytes": destination.stat().st_size,
            "sha256": _file_digest(destination),
        }
        if entry["kind"] == "database":
            copied["database"] = _database_facts(destination)
            copied["database"].pop("path_references")
            if copied["database"] != entry["database"]:
                raise ValueError("数据库记录发生变化，快照未完成")
        elif copied["sha256"] != entry["sha256"]:
            raise ValueError("文件发生变化，快照未完成")
        saved.append(copied)
    if plan_backup(root)["confirmation"] != confirmation:
        raise ValueError("备份期间数据发生变化，快照未完成；保留失败目录")
    manifest = {
        "format_version": FORMAT_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_root": str(root),
        "identity_origin": plan["identity_origin"],
        "source_confirmation": confirmation,
        "consistency": plan["consistency"],
        "directories": plan["directories"],
        "entries": saved,
    }
    _write(
        target / "manifest.json",
        json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8"),
    )
    return verify_backup(target)


def verify_backup(backup: Path) -> dict[str, Any]:
    """校验完整快照的精确文件集、哈希及每个数据库。"""
    _check_node(backup)
    root = backup.resolve()
    manifest_path = root / "manifest.json"
    _check_node(manifest_path)
    if manifest_path.stat().st_size > MAX_MANIFEST_BYTES:
        raise ValueError("快照清单过大")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (
        not isinstance(manifest, dict)
        or type(manifest.get("format_version")) is not int
        or manifest.get("format_version") != FORMAT_VERSION
    ):
        raise ValueError("不支持的快照版本")
    if (
        not isinstance(manifest.get("source_root"), str)
        or not Path(manifest["source_root"]).is_absolute()
    ):
        raise ValueError("快照缺少原逻辑数据路径")
    directories, entries = manifest.get("directories"), manifest.get("entries")
    if not isinstance(directories, list) or not isinstance(entries, list) or not entries:
        raise ValueError("快照清单不完整")
    expected_files, expected_dirs = [], []
    for relative in directories:
        if not _managed_path(relative, True):
            raise ValueError("清单目录越过托管范围")
        expected_dirs.append(relative)
    payload = root / "data"
    actual_dirs, actual_files = _walk(payload)
    for entry in entries:
        if not isinstance(entry, dict) or not _managed_path(entry.get("path"), False):
            raise ValueError("清单文件越过托管范围")
        relative = entry["path"]
        kind = (
            "database"
            if _database_path(relative)
            else "identity" if relative == "identity.secret" else "file"
        )
        if entry.get("kind") != kind or relative.endswith(
            ("filemate.db-wal", "filemate.db-shm", "filemate.db-journal")
        ):
            raise ValueError("清单文件类型非法，不能恢复SQLite侧文件")
        path = payload / relative
        _check_node(path)
        if entry.get("bytes") != path.stat().st_size or entry.get("sha256") != _file_digest(path):
            raise ValueError("快照文件大小或校验和不匹配")
        if kind == "database":
            facts = _database_facts(path)
            facts.pop("path_references")
            if entry.get("database") != facts:
                raise ValueError("快照数据库记录不匹配")
        if kind == "identity" and len(path.read_bytes().strip()) < 32:
            raise ValueError("快照身份密钥无效")
        expected_files.append(relative)
    all_names = expected_dirs + expected_files
    if len({name.casefold() for name in all_names}) != len(all_names):
        raise ValueError("快照存在重复或跨平台冲突文件名")
    if sorted(expected_dirs) != actual_dirs or sorted(expected_files) != actual_files:
        raise ValueError("快照文件集不完整或存在额外内容")
    if not any(entry["kind"] == "database" for entry in entries):
        raise ValueError("快照缺少数据库")
    if (
        any(name.startswith("users/u_") for name in expected_dirs)
        and "identity.secret" not in expected_files
    ):
        raise ValueError("匿名快照缺少身份密钥")
    if {item.name for item in root.iterdir()} != {"data", "manifest.json"}:
        raise ValueError("快照根目录包含额外内容")
    return {"manifest": manifest, "confirmation": _digest(manifest), "passed": True}


def _current_erasure_ledger(original: Path, manifest: dict[str, Any]) -> list[dict[str, str]]:
    """保留备份之后发生的删除，业务恢复不得撤销用户注销。"""
    folder = original / 'privacy-tombstones'
    if not folder.exists():
        return []
    from filemate.operations.workspace_privacy import WorkspaceDeletion
    _check_node(folder)
    secret, _origin = _identity(original)
    if secret is None:
        raise ValueError('当前删除账本缺少签名配置，拒绝恢复')
    identity = next((entry for entry in manifest['entries'] if entry['path'] == 'identity.secret'), None)
    if identity and _file_digest(original / 'identity.secret') != identity['sha256']:
        raise ValueError('身份密钥已经轮换，请先完成签名迁移再恢复旧备份')
    ledger = WorkspaceDeletion(original, secret)
    records = []
    for path in sorted(folder.glob('*.json')):
        if not re.fullmatch(r'[0-9a-f]{64}\.json', path.name):
            raise ValueError('当前删除账本文件名异常')
        record = ledger._read(path)
        if record.get('state') == 'pending':
            raise ValueError('请先恢复中断的注销操作再进行管理员恢复')
        if record.get('state') == 'erased':
            records.append({'path': path.name, 'sha256': _file_digest(path)})
    return records


def plan_restore(backup: Path, target: Path) -> dict[str, Any]:
    """预览恢复到新目录，不修改现役数据或路径引用。"""
    report = verify_backup(backup)
    destination = _new_target(target, backup.resolve())
    original = Path(report["manifest"]["source_root"]).resolve()
    if destination != original and destination.is_relative_to(original):
        raise ValueError("不能将恢复目录嵌入现役数据目录")
    result = {
        "backup": str(backup.resolve()),
        "target": str(destination),
        "backup_confirmation": report["confirmation"],
        "logical_source_root": report["manifest"]["source_root"],
        "file_count": len(report["manifest"]["entries"]),
        "path_policy": "preserve references; activate only at original logical mount path",
        "preserved_erasure_ledger": _current_erasure_ledger(original, report['manifest']),
    }
    result["confirmation"] = _digest(result)
    return result


def restore_backup(backup: Path, target: Path, confirmation: str) -> dict[str, Any]:
    """按预览独占恢复，不覆盖目录且不启动服务。"""
    plan = plan_restore(backup, target)
    if plan["confirmation"] != confirmation:
        raise ValueError("快照或目标变化，请重新预览恢复")
    manifest = verify_backup(backup)["manifest"]
    destination = Path(plan["target"])
    destination.mkdir(mode=0o700)
    for relative in manifest["directories"]:
        (destination / relative).mkdir(mode=0o700, parents=True, exist_ok=True)
    for entry in manifest["entries"]:
        source, output = (
            backup.resolve() / "data" / entry["path"],
            destination / entry["path"],
        )
        _copy(source, output)
        if _file_digest(output) != entry["sha256"]:
            raise ValueError("恢复文件校验失败，保留未启用的新目录")
        if entry["kind"] == "database":
            facts = _database_facts(output)
            facts.pop("path_references")
            if facts != entry["database"]:
                raise ValueError("恢复数据库校验失败，保留未启用的新目录")
    if verify_backup(backup)["confirmation"] != plan["backup_confirmation"]:
        raise ValueError("恢复期间快照变化，不能启用恢复目录")
    current_ledger = _current_erasure_ledger(Path(plan['logical_source_root']), manifest)
    if current_ledger != plan['preserved_erasure_ledger']:
        raise ValueError('恢复期间删除账本变化，新目录不可启用')
    for entry in current_ledger:
        source = Path(plan['logical_source_root']) / 'privacy-tombstones' / entry['path']
        output = destination / 'privacy-tombstones' / entry['path']
        output.parent.mkdir(mode=0o700, exist_ok=True)
        if output.exists():
            _check_node(output); output.unlink()
        _copy(source, output)
        if _file_digest(output) != entry['sha256']:
            raise ValueError('当前删除账本复制失败，新目录不可启用')
    return {
        "passed": True,
        "target": str(destination),
        "file_count": plan["file_count"],
        "activated": False,
        "path_policy": plan["path_policy"],
        'preserved_erasure_count': len(current_ledger),
    }


def _summary(report: dict[str, Any]) -> dict[str, Any]:
    """隐藏清单中的用户标识和密钥指纹，仅输出运维摘要。"""
    manifest = report.get("manifest", report)
    if "entries" not in manifest:
        return report
    entries = manifest["entries"]
    return {
        "passed": report.get("passed"),
        "confirmation": report["confirmation"],
        "database_count": sum(entry["kind"] == "database" for entry in entries),
        "file_count": sum(entry["kind"] != "wal" for entry in entries),
        "bytes": sum(entry["bytes"] for entry in entries if entry["kind"] != "wal"),
        "schema_versions": sorted(
            {
                entry["database"]["schema_version"]
                for entry in entries
                if entry["kind"] == "database"
            }
        ),
        "identity_origin": manifest["identity_origin"],
        "consistency": manifest["consistency"],
    }


def main() -> int:
    """运行本地管理员工具，不提供公网恢复接口。"""
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("plan", "create"):
        command = commands.add_parser(name)
        command.add_argument("--data-dir", type=Path, required=True)
        if name == "create":
            command.add_argument("--out", type=Path, required=True)
            command.add_argument("--confirm", required=True)
            command.add_argument("--quiesced", action="store_true")
    for name in ("verify", "restore-plan", "restore"):
        command = commands.add_parser(name)
        command.add_argument("--backup", type=Path, required=True)
        if name != "verify":
            command.add_argument("--target", type=Path, required=True)
        if name == "restore":
            command.add_argument("--confirm", required=True)
    args = parser.parse_args()
    try:
        if args.command == "plan":
            result = plan_backup(args.data_dir)
        elif args.command == "create":
            result = create_backup(args.data_dir, args.out, args.confirm, quiesced=args.quiesced)
        elif args.command == "verify":
            result = verify_backup(args.backup)
        elif args.command == "restore-plan":
            result = plan_restore(args.backup, args.target)
        else:
            result = restore_backup(args.backup, args.target, args.confirm)
        print(json.dumps(_summary(result), ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, TypeError, KeyError, sqlite3.Error, TimeoutError):
        # 不输出异常中的SQL、文件内容或身份信息；失败证据目录仍保留。
        print(
            json.dumps(
                {
                    "passed": False,
                    "error": "备份/恢复校验失败；检查布局、确认指纹、停写状态、权限和新目录要求",
                },
                ensure_ascii=False,
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
