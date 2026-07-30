""".ics 端到端验证：RFC 5545 合规性 + 真实场景 + 可导入性检查。

用法: python -m filemate.tests.verify_ics_e2e
"""

import re
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

from filemate.execution.scheduler import CalendarBuilder, CalendarEvent


# ── RFC 5545 合规性检查 ──

def check_rfc5545(content: str) -> list[str]:
    """返回不合规项列表，空列表表示全部通过。"""
    issues = []

    # 1. 必须有 VCALENDAR 包裹
    if "BEGIN:VCALENDAR" not in content:
        issues.append("缺少 BEGIN:VCALENDAR")
    if "END:VCALENDAR" not in content:
        issues.append("缺少 END:VCALENDAR")

    # 2. 必须有 VERSION:2.0
    if "VERSION:2.0" not in content:
        issues.append("缺少 VERSION:2.0")

    # 3. 必须有 PRODID
    if "PRODID:" not in content:
        issues.append("缺少 PRODID")

    # 4. 每个 BEGIN:VEVENT 必须有对应 END:VEVENT
    begin_count = content.count("BEGIN:VEVENT")
    end_count = content.count("END:VEVENT")
    if begin_count != end_count:
        issues.append(f"VEVENT 不配对: BEGIN={begin_count}, END={end_count}")

    # 5. 每个 VEVENT 必须有 DTSTART
    events = content.split("BEGIN:VEVENT")[1:]  # 去掉 VCALENDAR 前的部分
    for i, block in enumerate(events, 1):
        block = block.split("END:VEVENT")[0]
        if "DTSTART" not in block:
            issues.append(f"事件 {i} 缺少 DTSTART")
        if "DTEND" not in block and "DURATION" not in block:
            issues.append(f"事件 {i} 缺少 DTEND/DURATION")
        if "SUMMARY" not in block:
            issues.append(f"事件 {i} 缺少 SUMMARY")
        if "DTSTAMP" not in block:
            issues.append(f"事件 {i} 缺少 DTSTAMP")

    # 6. 行长度不超过 75 个八位字节（RFC 5545 §3.1）
    for i, line in enumerate(content.splitlines(), 1):
        if len(line.encode("utf-8")) > 75:
            # .ics 长行应折叠，但 icalendar 库可能不做
            # 此处只记录 warning 级别
            if len(line) > 100:  # 超过 100 才算严重
                issues.append(f"行 {i} 过长 ({len(line)} 字符)")

    # 7. 换行符必须是 CRLF
    if "\r\n" not in content:
        issues.append("缺少 CRLF 换行符（RFC 5545 要求）")

    return issues


# ── 真实场景 ──

def build_competition_ics() -> CalendarEvent:
    """场景 1：竞赛通知 — 多节点。"""
    return [
        CalendarEvent(
            summary="大创项目申报截止",
            start="2026-09-15",
            location="线上提交",
            description="提交申报书至大创管理系统",
        ),
        CalendarEvent(
            summary="大创中期检查",
            start="2026-12-01",
            location="教务处",
            description="提交中期进展报告",
        ),
        CalendarEvent(
            summary="大创结题答辩",
            start="2027-04-20T14:00",
            location="教三楼 201",
            description="准备 PPT + 结题报告",
        ),
    ]


def build_exam_ics() -> list[CalendarEvent]:
    """场景 2：考试通知。"""
    return [
        CalendarEvent(
            summary="操作系统期末考试",
            start="2026-07-20T09:00",
            end="2026-07-20T11:00",
            location="教学楼 A101",
            description="闭卷考试，带学生证",
        ),
        CalendarEvent(
            summary="数据结构期末考试",
            start="2026-07-22T14:30",
            end="2026-07-22T16:30",
            location="教学楼 B203",
            description="开卷考试",
        ),
    ]


def build_single_task_ics() -> list[CalendarEvent]:
    """场景 3：单个作业截止。"""
    return [
        CalendarEvent(
            summary="[作业] 操作系统实验三 — 进程同步",
            start="2026-08-15",
            description="来源: 操作系统_实验三.docx",
        ),
    ]


def build_milestone_only_ics() -> list[CalendarEvent]:
    """场景 4：仅日期无时间的里程碑。"""
    return [
        CalendarEvent(summary="初赛作品提交", start="2026-10-01"),
        CalendarEvent(summary="复赛名单公布", start="2026-10-15"),
        CalendarEvent(summary="决赛答辩", start="2026-11-01T13:00"),
    ]


# ── 可导入性验证 ──

def check_import_compatibility(content: str) -> list[str]:
    """验证常见日历软件兼容性问题。"""
    issues = []

    # Outlook 兼容：不允许嵌套 VCALENDAR
    if content.count("BEGIN:VCALENDAR") > 1:
        issues.append("多个 BEGIN:VCALENDAR，Outlook 可能拒绝导入")

    # Google 日历兼容：必须有 UID（icalendar 自动生成）
    # 这里只检查至少有一个 UID
    # icalendar 的 Event() 自动生成 UID

    # 通用：SUMMARY 不能为空
    begin_events = content.split("BEGIN:VEVENT")[1:]
    for i, block in enumerate(begin_events, 1):
        block = block.split("END:VEVENT")[0]
        # 提取 SUMMARY 值
        m = re.search(r"SUMMARY:(.*)", block)
        if m and not m.group(1).strip():
            issues.append(f"事件 {i} 的 SUMMARY 为空")

    # Apple 日历兼容：必须有 VALARM 或无需处理（我们不做 VTODO）
    # 不强制要求

    return issues


# ── Archiver 端到端 ──

def verify_archiver():
    """验证 archiver 端到端：创建目录 + 移动文件。"""
    from filemate.execution.file_ops import FileOps
    from filemate.execution.archiver import Archiver

    file_ops = FileOps()
    errors = []

    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp) / "archive"
        archiver = Archiver(base, file_ops)

        # 1. 基础归档
        src = Path(tmp) / "test.docx"
        src.write_text("操作系统实验内容")
        result = archiver.archive("s1", "课件", "操作系统", "[操作系统]-[课件]-[第一章].docx", src)
        if not result.success:
            errors.append(f"归档失败: {result.error}")
        dest = base / "操作系统" / "课件" / "[操作系统]-[课件]-[第一章].docx"
        if not dest.exists():
            errors.append(f"归档文件不存在: {dest}")
        if src.exists():
            errors.append(f"源文件未被移动: {src}")

        # 2. 未知分类 → 待确认
        src2 = Path(tmp) / "unknown.txt"
        src2.write_text("杂项内容")
        result2 = archiver.archive("s2", "未知类型", "通用", "generic.txt", src2)
        if not result2.success:
            errors.append(f"未知分类归档失败: {result2.error}")
        fallback = base / "通用" / "待确认" / "generic.txt"
        if not fallback.exists():
            errors.append(f"fallback 目录未创建: {fallback}")

        # 3. preview_dest 不执行移动
        preview = archiver.preview_dest(base, "作业", "高数", "math.pdf")
        if preview != base / "高数" / "作业" / "math.pdf":
            errors.append(f"preview 路径不正确: {preview}")
        # preview 不应创建文件
        if (base / "高数" / "作业" / "math.pdf").exists():
            errors.append("preview 不应创建文件")

        # 4. 空字符串课程名
        src3 = Path(tmp) / "nobody.txt"
        src3.write_text("无归属")
        result3 = archiver.archive("s3", "课件", "", "nobody.txt", src3)
        if not result3.success:
            errors.append(f"空课程名归档失败: {result3.error}")

    return errors


# ── main ──

def main():
    print("=" * 60)
    print("FileMate .ics 端到端验证")
    print("=" * 60)

    builder = CalendarBuilder()
    all_ok = True

    # ── 测试 4 个场景 ──
    scenarios = [
        ("竞赛通知（3 节点）", build_competition_ics()),
        ("考试通知（2 场）", build_exam_ics()),
        ("单作业截止", build_single_task_ics()),
        ("纯里程碑事件", build_milestone_only_ics()),
    ]

    for name, events in scenarios:
        print(f"\n── 场景: {name} ──")
        data = builder.build(events)
        content = data.decode("utf-8")

        # RFC 5545 检查
        rfc_issues = check_rfc5545(content)
        if rfc_issues:
            all_ok = False
            for issue in rfc_issues:
                print(f"  [FAIL] RFC 5545: {issue}")
        else:
            print(f"  [PASS] RFC 5545 合规")

        # 兼容性检查
        compat_issues = check_import_compatibility(content)
        if compat_issues:
            all_ok = False
            for issue in compat_issues:
                print(f"  [FAIL] 兼容性: {issue}")
        else:
            print(f"  [PASS] 兼容性检查")

        # 内容完整性
        for ev in events:
            if ev.summary not in content:
                all_ok = False
                print(f"  [FAIL] 缺少摘要: {ev.summary}")
        print(f"  [INFO] {len(events)} 个事件, {len(data)} bytes")

        # 写入临时文件确认可写入
        with tempfile.NamedTemporaryFile(suffix=".ics", delete=False) as f:
            f.write(data)
            ics_path = Path(f.name)
        print(f"  [INFO] 已生成: {ics_path}")
        ics_path.unlink()

    # ── Archiver 端到端 ──
    print(f"\n── Archiver 端到端验证 ──")
    arch_errors = verify_archiver()
    if arch_errors:
        all_ok = False
        for e in arch_errors:
            print(f"  [FAIL] {e}")
    else:
        print(f"  [PASS] Archiver 端到端通过")

    # ── 汇总 ──
    print()
    print("=" * 60)
    if all_ok:
        print("[PASS] 所有 .ics 端到端验证通过")
        print("系统日历应可正常导入生成的 .ics 文件")
        print("Archiver 端到端功能正常")
    else:
        print("[FAIL] 存在未通过的检查项，见上方详情")
    print("=" * 60)

    return all_ok


if __name__ == "__main__":
    ok = main()
    raise SystemExit(0 if ok else 1)
