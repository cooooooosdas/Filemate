"""Package tracked candidate bytes with a manifest and frozen engineering evidence."""

import argparse
import hashlib
import json
import subprocess
import zipfile
from pathlib import Path

from scripts.acceptance.wrongbook_incremental_evidence import ARCHIVE, ROOT, read_json, validate


def package(destination: Path) -> dict:
    """Create a new source ZIP without secrets or runtime databases."""
    validate()
    frozen = read_json(ARCHIVE / 'verification.json')
    for section, prefix in [('source_sha256', ROOT), ('evidence_sha256', ARCHIVE)]:
        for name, expected in frozen[section].items():
            assert hashlib.sha256((prefix / name).read_bytes()).hexdigest() == expected, name
    destination = destination.resolve()
    if not destination.is_relative_to((ROOT / '_working').resolve()) or destination.exists():
        raise ValueError('requires a new archive path below project _working')
    paths = subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT).decode('utf-8').split('\0')
    forbidden = {'_working', '.git', '.superpowers', '.filemate-data', 'node_modules', '.venv', '__pycache__'}
    hashes, excluded = {}, []
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, 'x', compression=zipfile.ZIP_DEFLATED) as archive:
        for name in filter(None, paths):
            relative = Path(name)
            if (forbidden.intersection(relative.parts)
                    or relative.suffix.lower() in {'.db', '.sqlite', '.sqlite3', '.pem', '.key', '.p12', '.pfx'}
                    or relative.name.endswith(('-wal', '-shm', '-journal'))
                    or relative.name.startswith('.env') and not relative.name.endswith('.example')):
                excluded.append(name)
                continue
            source = ROOT / relative
            if not source.is_file() or source.is_symlink() or not source.resolve().is_relative_to(ROOT):
                raise ValueError(f'unsupported tracked path: {name}')
            content = source.read_bytes()
            hashes[name] = hashlib.sha256(content).hexdigest()
            archive.writestr('FileMate-Project/' + name, content)
        manifest = {
            'head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
            'status': frozen['status'], 'policy': 'current tracked worktree bytes, not only Git objects',
            'pre_existing_24_test_changes': 'unchanged and included as tested; not committed by this task',
            'files_sha256': hashes, 'excluded': excluded,
            'not_verified': ['production deployment', 'human learning effects', 'fourth-specialty B-E'],
        }
        archive.writestr('FILEMATE-CANDIDATE-MANIFEST.json', json.dumps(manifest, ensure_ascii=False, indent=2))
    with zipfile.ZipFile(destination) as archive:
        assert archive.testzip() is None
        for name, expected in hashes.items():
            assert hashlib.sha256(archive.read('FileMate-Project/' + name)).hexdigest() == expected
    result = {'path': str(destination), 'sha256': hashlib.sha256(destination.read_bytes()).hexdigest(),
              'head': manifest['head'], 'bytes': destination.stat().st_size, 'files': len(hashes)}
    destination.with_suffix('.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, type=Path)
    options = parser.parse_args()
    print(json.dumps(package(options.out), ensure_ascii=False))
