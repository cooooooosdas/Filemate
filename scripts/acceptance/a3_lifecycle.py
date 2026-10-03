"""A3 数据生命周期验收：创建 → 重启可读 → 删除预览 → 删除 → 外部文件保留 → 重复删除 404。"""

import json
import os
import tempfile
from pathlib import Path

tmp = Path(tempfile.mkdtemp(prefix="fm_a3_"))
external_file = tmp / "external.txt"
external_file.write_text("external file should survive", encoding="utf-8")

os.environ["FILEMATE_DB_PATH"] = str(tmp / "a3.db")
os.environ["FILEMATE_DATA_DIR"] = str(tmp / "data")
os.environ["FILEMATE_UPLOAD_DIR"] = str(tmp / "inbox")
os.environ["FILEMATE_ARCHIVE_DIR"] = str(tmp / "archive")

from fastapi.testclient import TestClient

import server

source_id = server._storage.save_source(
    original_name="external.txt",
    source_path=str(external_file),
    raw_text="external content",
    media_type="text/plain",
)
server._storage.save_artifact(
    artifact_type="notes",
    source_id=source_id,
    title="derived artifact",
    content={"text": "derived"},
)

client = TestClient(server.app)
report = {"source_id": source_id, "steps": []}


def require(condition: bool, message: str) -> None:
    """验收条件不满足时立即以非零状态失败。"""
    if not condition:
        raise RuntimeError(message)


# 重启可读：用新的存储实例读取同一数据库
from filemate.execution.storage import SQLiteStorage

restarted = SQLiteStorage(str(tmp / "a3.db"))
restarted.init_schema()
source_survived_restart = restarted.get_source(source_id) is not None
require(source_survived_restart, "重建存储实例后资料源不可读")
report["steps"].append(
    {
        "step": "restart_readable",
        "source_exists": source_survived_restart,
    }
)

preview = server._storage.preview_source_deletion(source_id)
require(preview is not None, "删除预览未找到已创建的资料源")
require(preview["affected"]["artifacts"] == 1, "删除预览未统计派生 Artifact")
report["steps"].append({"step": "delete_preview", "affected": preview["affected"]})

delete_resp = client.delete(f"/knowledge/sources/{source_id}")
require(
    delete_resp.status_code == 200,
    f"删除资料源失败：{delete_resp.status_code} {delete_resp.text}",
)
require(delete_resp.json()["success"] is True, "删除接口未返回 success=true")
report["steps"].append(
    {
        "step": "delete_source",
        "status": delete_resp.status_code,
        "success": delete_resp.json()["success"],
    }
)

report["steps"].append(
    {
        "step": "external_file_untouched",
        "exists": external_file.exists(),
    }
)
require(external_file.exists(), "删除资料源时误删了外部原始文件")

get_after = client.get(f"/knowledge/sources/{source_id}")
require(get_after.status_code == 404, "删除后资料源仍可读取")
report["steps"].append(
    {
        "step": "get_after_delete",
        "status": get_after.status_code,
    }
)

delete_again = client.delete(f"/knowledge/sources/{source_id}")
require(delete_again.status_code == 404, "重复删除未按合同返回 404")
report["steps"].append(
    {
        "step": "delete_again",
        "status": delete_again.status_code,
    }
)

out = Path(os.getenv("FILEMATE_EVIDENCE_DIR", str(Path.cwd() / "_working"))) / "a3-lifecycle.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps(report, ensure_ascii=False, indent=2))
