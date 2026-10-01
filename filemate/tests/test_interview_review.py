"""面试增强的证据、取消竞态、数据生命周期与API回归。"""

from __future__ import annotations

import importlib
import json
import sys
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from filemate.execution.storage import _MIGRATIONS, SQLiteStorage
from filemate.interview_review.models import CONTENT_AREAS, VisualMetrics
from filemate.interview_review.reports import build_report, report_markdown, report_pdf
from filemate.interview_review.repository import ReviewRepository
from filemate.understanding.interview import InterviewEvaluator

ANSWER = "首先分析项目背景，因为任务需要支持范围查询，例如用有序索引验证结果。"


def visual():
    return {"source": "mediapipe_local_v1", "timeline_origin": "recording",
            "duration_seconds": 10, "sample_count": 20, "face_samples": 12,
            "low_light_samples": 4, "dropped_samples": 0, "events_truncated": False,
            "events": [{"kind": "no_face", "start": 4, "end": 7},
                       {"kind": "low_light", "start": 8, "end": 10}]}


def model_payload():
    return {"score": 80, "dimensions": {k: 80 for k in ("内容", "结构", "表达", "岗位匹配")},
            "dimension_evidence": {k: "首先分析项目背景" for k in ("内容", "结构", "表达", "岗位匹配")},
            "feedback": "补充验证条件与量化结果。",
            "keywords": ["范围查询", "有序索引"],
            "content_analysis": {k: {"status": "partial", "evidence": "首先分析项目背景",
                                     "suggestion": "对照原资料补充定义、条件和例子。"}
                                 for k in CONTENT_AREAS}}


class FakeLLM:
    def __init__(self, payload=None):
        self.payload = model_payload() if payload is None else payload

    def call(self, **kwargs):
        if isinstance(self.payload, Exception):
            raise self.payload
        return json.dumps(self.payload, ensure_ascii=False)


@pytest.fixture
def storage(tmp_path):
    store = SQLiteStorage(tmp_path / "interview.db")
    store.init_schema()
    yield store
    store.close()


def session(storage, questions=None):
    return storage.create_interview(target_role="后端开发", scenario="求职面试", difficulty="标准",
                                    questions=questions or ["介绍项目", "解释索引"])


def answer(storage, id, index=0, metrics=None):
    return storage.save_interview_turn(
        interview_id=id, question_index=index, question="介绍项目", answer=ANSWER,
        score=None, dimensions={}, feedback="内容待评估", scoring_mode="local_fallback",
        visual_metrics=metrics,
        fluency_metrics={"source": "speech_recognition", "duration_seconds": 8,
                         "chars_per_minute": 180, "filler_count": 1, "long_pause_count": 1,
                         "recording_offset_seconds": 1,
                         "markers": [{"kind": "long_pause", "second": 3, "label": "较长停顿"}]},
    )


def test_visual_validation_rejects_inconsistent_and_private_fields():
    assert VisualMetrics.model_validate(visual()).face_samples == 12
    for payload in [visual() | {"face_samples": 21}, visual() | {"duration_seconds": 0},
                    visual() | {"frame": "base64 private image"},
                    visual() | {"events": [{"kind": "no_face", "start": 8, "end": 4}]},
                    visual() | {"events": [{"kind": "emotion", "start": 0, "end": 1}]},
                    visual() | {"duration_seconds": float("nan")},
                    visual() | {"events": [{"kind": "low_light", "start": 4, "end": 11}]}]:
        with pytest.raises(ValidationError):
            VisualMetrics.model_validate(payload)


def test_model_content_and_dimension_evidence_are_original_quotes():
    result = InterviewEvaluator(FakeLLM()).evaluate("介绍项目", ANSWER, "后端")
    assert result["scoring_mode"] == "llm"
    assert set(result["content_analysis"]["areas"]) == set(CONTENT_AREAS)
    assert all(q in ANSWER for q in result["content_analysis"]["dimension_evidence"].values())


@pytest.mark.parametrize("mutation", ["missing", "quote", "score", "dimension", "status", "empty"])
def test_invalid_model_evidence_is_unassessed(mutation):
    payload = model_payload()
    if mutation == "missing":
        del payload["content_analysis"]["star"]
    elif mutation == "quote":
        payload["content_analysis"]["logic"]["evidence"] = "不存在的成果"
    elif mutation == "score":
        payload["score"] = float("nan")
    elif mutation == "dimension":
        payload["dimension_evidence"]["表达"] = "编造证据"
    elif mutation == "status":
        payload["content_analysis"]["star"]["status"] = "confident"
    else:
        payload["content_analysis"]["logic"]["evidence"] = ""
    result = InterviewEvaluator(FakeLLM(payload)).evaluate("介绍项目", ANSWER, "后端")
    assert result["score"] is None and result["scoring_mode"] == "local_fallback"


def test_report_no_fabricated_score_and_timebases_are_explicit(storage):
    id = session(storage)["interview_id"]
    data = answer(storage, id, metrics=visual())
    report = build_report(data)
    assert report["overall_score"] is None and report["assessed"] == 0
    assert report["visual"]["face_observed_ratio"] == .6
    speech = next(e for e in report["timeline"] if e["kind"] == "long_pause")
    assert speech["start"] == 4 and speech["timebase"] == "recording"
    data["turns"][0]["visual_metrics"] = {}
    without_visual = build_report(data)
    assert without_visual["timeline"][0]["timebase"] == "recording"
    del data["turns"][0]["fluency_metrics"]["recording_offset_seconds"]
    assert build_report(data)["timeline"][0]["timebase"] == "speech"
    data["turns"][0]["fluency_metrics"] = {}
    empty = build_report(data)
    assert empty["expression"]["chars_per_minute"] is None
    assert empty["visual"]["face_observed_ratio"] is None
    assert not empty["timeline"]


def test_report_persistence_idempotency_and_late_changes(storage):
    repo, id = ReviewRepository(storage), session(storage)["interview_id"]
    with pytest.raises(ValueError, match="先提交"):
        repo.generate(id)
    answer(storage, id, metrics=visual())
    first = repo.generate(id)
    assert repo.generate(id) == first
    assert sum(e["action"] == "report_generated" for e in repo.events(id)) == 1
    answer(storage, id, 1)
    assert repo.report(id) is None
    second = repo.generate(id)
    assert second["artifact_id"] == first["artifact_id"] and second["answered"] == 2
    reopened = SQLiteStorage(storage.db_path)
    reopened.init_schema()
    assert ReviewRepository(reopened).report(id)["answered"] == 2
    reopened.close()


def test_cancel_and_clear_prevent_late_analysis_and_preserve_raw(storage):
    repo, id = ReviewRepository(storage), session(storage)["interview_id"]
    data = answer(storage, id, metrics=visual())
    turn_id = data["turns"][0]["turn_id"]
    report = repo.generate(id)
    _, revision = repo.snapshot(id)
    evaluation = InterviewEvaluator(FakeLLM()).evaluate("介绍项目", ANSWER, "后端")
    repo.cancel(id)
    with pytest.raises(ValueError, match="取消"):
        repo.apply_analysis(id, turn_id, revision, evaluation)
    assert repo.report(id) == report
    _, revision = repo.snapshot(id)
    repo.apply_analysis(id, turn_id, revision, evaluation)
    assert storage.get_interview(id)["assessed_turn_count"] == 1
    _, revision = repo.snapshot(id)
    cleared = repo.clear(id)
    repo.clear(id)
    assert cleared["turns"][0]["answer"] == ANSWER
    assert cleared["turns"][0]["fluency_metrics"]["long_pause_count"] == 1
    assert cleared["turns"][0]["visual_metrics"] == {}
    assert cleared["overall_score"] is None and repo.report(id) is None
    with pytest.raises(ValueError):
        repo.apply_analysis(id, turn_id, revision, evaluation)
    assert sum(e["action"] == "analysis_cleared" for e in repo.events(id)) == 1


def test_corrupt_observations_preserve_answer_and_report_can_regenerate(storage):
    repo, id = ReviewRepository(storage), session(storage)["interview_id"]
    answer(storage, id, metrics=visual())
    conn = storage._conn()
    conn.execute("UPDATE interview_turns SET visual_metrics='broken' WHERE interview_id=?", (id,))
    conn.commit()
    report = repo.generate(id)
    assert report["turns"][0]["data_error"]
    assert report["turns"][0]["answer"] == ANSWER and not report["visual"]["sample_count"]
    assert conn.execute("SELECT visual_metrics FROM interview_turns").fetchone()[0] == "broken"
    conn.execute("UPDATE artifacts SET content='[]' WHERE artifact_id=?", (report["artifact_id"],))
    conn.commit()
    with pytest.raises(ValueError, match="报告数据异常"):
        repo.report(id)
    assert repo.generate(id)["answered"] == 1


@pytest.mark.parametrize("field", ["keywords", "dimension_evidence"])
def test_corrupt_saved_quotes_are_not_used_as_report_evidence(storage, field):
    repo, id = ReviewRepository(storage), session(storage)["interview_id"]
    saved = answer(storage, id)
    evaluation = InterviewEvaluator(FakeLLM()).evaluate("介绍项目", ANSWER, "后端")
    _, revision = repo.snapshot(id)
    repo.apply_analysis(id, saved["turns"][0]["turn_id"], revision, evaluation)
    analysis = evaluation["content_analysis"]
    if field == "keywords":
        analysis[field] = ["编造的专业关键词"]
    else:
        analysis[field]["内容"] = "编造的回答引用"
    raw = json.dumps(analysis, ensure_ascii=False)
    conn = storage._conn()
    conn.execute("UPDATE interview_turns SET content_analysis=? WHERE interview_id=?", (raw, id))
    conn.commit()
    turn = storage.get_interview(id)["turns"][0]
    assert turn["analysis_data_error"] and turn["content_analysis"] == {}
    assert repo.generate(id)["turns"][0]["data_error"]
    assert conn.execute("SELECT content_analysis FROM interview_turns").fetchone()[0] == raw


def test_delete_preview_stale_and_idempotent_delete_cleans_linked_memory(storage):
    run = storage.create_agent_run(task_type="interview_session", goal="面试训练", selected_agents=[])
    data = storage.create_interview(target_role="后端", scenario="求职面试", difficulty="标准",
                                    questions=["问题一", "问题二"], agent_run_id=run["run_id"])
    id = data["interview_id"]
    storage.save_agent_memory(memory_type="session", scope_id=id, source_type="interview_goal",
                              source_id=id, summary="私有训练方向", allowed_agents=[])
    other = session(storage)["interview_id"]
    repo = ReviewRepository(storage)
    preview = repo.delete_preview(id)
    answer(storage, id)
    with pytest.raises(ValueError, match="重新预览"):
        repo.delete(id, preview["confirmation_token"])
    repo.generate(id)
    preview = repo.delete_preview(id)
    assert preview["answers"] == 1 and preview["reports"] == 1
    repo.delete(id, preview["confirmation_token"])
    assert repo.delete(id, preview["confirmation_token"])["deleted"]
    assert storage.get_interview(id) is None and storage.get_interview(other)
    assert storage.get_agent_run(run["run_id"]) is None
    assert not storage._conn().execute("SELECT * FROM agent_memories WHERE scope_id=?", (id,)).fetchall()
    assert not storage._conn().execute("SELECT * FROM artifacts WHERE artifact_type='interview_report'").fetchall()


def test_migration_from_22_is_append_only(tmp_path):
    import sqlite3

    db = tmp_path / "old.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE schema_migrations(version INTEGER PRIMARY KEY,name TEXT,applied_at TEXT)")
    for version, name, script in _MIGRATIONS:
        if version > 22:
            break
        conn.executescript(script)
        conn.execute("INSERT INTO schema_migrations(version,name) VALUES (?,?)", (version, name))
    conn.execute("INSERT INTO interview_sessions(interview_id,target_role,scenario,difficulty,questions) "
                 "VALUES ('old','后端','求职面试','标准','[\"问题\"]')")
    conn.commit()
    conn.close()
    store = SQLiteStorage(db)
    store.init_schema()
    assert store.get_schema_version() == 23 and store.get_interview("old")["questions"] == ["问题"]
    store.init_schema()
    store.close()


def test_concurrent_request_key_creates_one_turn(storage):
    id = session(storage)["interview_id"]

    def save():
        return storage.save_interview_turn(interview_id=id, question_index=0, question="问题",
                                           answer=ANSWER, score=None, dimensions={}, feedback="记录",
                                           scoring_mode="local_fallback", answer_key="same_key_12345678",
                                           answer_digest="fixed_digest")

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: save(), range(4)))
    assert all(r["current_index"] == 1 for r in results)
    assert len(storage.get_interview(id)["turns"]) == 1


def test_markdown_and_pdf_contain_chinese_and_escape_user_markup(storage):
    data = answer(storage, session(storage)["interview_id"])
    data["turns"][0]["answer"] = "<script>用户原文 & 保留</script>\n" + ANSWER
    report = build_report(data)
    assert "内容薄弱知识点待评估" in report_markdown(report)
    pdf = report_pdf(report)
    assert pdf.startswith(b"%PDF") and b"NotoSansSC" in pdf
    import io

    import pdfplumber
    with pdfplumber.open(io.BytesIO(pdf)) as document:
        text = "".join(page.extract_text() or "" for page in document.pages)
        assert "面试复盘报告" in text and "用户原文" in text


@pytest.fixture
def api(storage, monkeypatch, tmp_path, request):
    monkeypatch.setenv("FILEMATE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("FILEMATE_DB_PATH", str(tmp_path / "bootstrap.db"))
    monkeypatch.setenv("FILEMATE_INTERVIEW_LOCAL_ONLY", "1")
    monkeypatch.setenv("FILEMATE_IDENTITY_MODE", getattr(request, "param", "local"))
    sys.modules.pop("server", None)
    module = importlib.import_module("server")
    module._storage.close()
    module._storage = module._StorageRouter(storage)
    with TestClient(module.app) as client:
        yield client, module
    sys.modules.pop("server", None)


def create_api(client):
    response = client.post("/interviews", json={"target_role": "后端开发", "scenario": "求职面试",
                                                "allow_external_analysis": False})
    assert response.status_code == 200
    return response.json()["data"]["interview_id"]


def test_api_answers_idempotent_boundaries_report_exports_and_protection(api):
    client, _ = api
    id = create_api(client)
    base = {"answer": ANSWER, "question_index": 0, "request_key": "request_test_12345678",
            "visual_metrics": visual()}
    assert client.post(f"/interviews/{id}/answers", json=base | {"answer": " "}).status_code == 422
    assert client.post(f"/interviews/{id}/answers", json=base | {"answer": "a" * 12001}).status_code == 422
    assert client.post(f"/interviews/{id}/answers", json=base | {"visual_metrics": visual() | {"face_samples": 21}}).status_code == 422
    first = client.post(f"/interviews/{id}/answers", json=base).json()["data"]
    assert first["current_index"] == 1
    assert client.post(f"/interviews/{id}/answers", json=base).json()["data"]["current_index"] == 1
    assert client.post(f"/interviews/{id}/answers", json=base | {"answer": "另一回答"}).status_code == 409
    assert client.post(f"/interviews/{id}/answers", json=base | {"request_key": "another_key_123456"}).status_code == 409
    report = client.post(f"/interviews/{id}/review").json()["data"]
    assert client.get(f"/interviews/{id}/review").json()["data"]["report"] == report
    assert client.patch(f"/knowledge/artifacts/{report['artifact_id']}", json={"title": "覆盖", "content": {}}).status_code == 409
    for format, prefix in [("json", b"{"), ("markdown", b"#"), ("pdf", b"%PDF")]:
        response = client.get(f"/interviews/{id}/review/export", params={"format": format})
        assert response.status_code == 200 and response.content.startswith(prefix)
    assert client.get(f"/interviews/{id}/review/export?format=html").status_code == 422
    assert client.post(f"/interviews/{id}/analysis/clear", json={}).status_code == 422


def test_api_model_failure_and_cancel_race_preserve_report(api, monkeypatch):
    client, module = api
    id = create_api(client)
    turn = client.post(f"/interviews/{id}/answers", json={"answer": ANSWER}).json()["data"]["turns"][0]
    original = client.post(f"/interviews/{id}/review").json()["data"]
    path = f"/interviews/{id}/turns/{turn['turn_id']}/analyze"
    assert client.post(path, json={}).status_code == 422
    monkeypatch.delenv("FILEMATE_INTERVIEW_LOCAL_ONLY")
    import filemate.llm_client as llm
    monkeypatch.setattr(llm.LLMConfig, "from_env", lambda: object())
    monkeypatch.setattr(llm, "LLMClient", lambda _: FakeLLM(RuntimeError("secret API error")))
    failure = client.post(path, json={"external_consent": True})
    assert failure.status_code == 502 and "secret" not in failure.text
    assert client.get(f"/interviews/{id}/review").json()["data"]["report"] == original
    started, release = threading.Event(), threading.Event()

    class Blocking(FakeLLM):
        def call(self, **kwargs):
            started.set()
            assert release.wait(10)
            return super().call(**kwargs)

    monkeypatch.setattr(llm, "LLMClient", lambda _: Blocking())
    with ThreadPoolExecutor(max_workers=1) as pool:
        task = pool.submit(client.post, path, json={"external_consent": True})
        assert started.wait(10)
        assert client.post(f"/interviews/{id}/analysis/cancel").status_code == 200
        release.set()
        assert task.result().status_code == 409
    assert module._storage.get_interview(id)["assessed_turn_count"] == 0
    assert client.get(f"/interviews/{id}/review").json()["data"]["report"] == original


def test_feature_disable_leaves_original_practice_working(api, monkeypatch):
    client, _ = api
    id = create_api(client)
    monkeypatch.setenv("FILEMATE_ENABLE_INTERVIEW_REVIEW", "0")
    assert client.get("/interview/review/status").json()["data"]["enabled"] is False
    for method, path, body in [
        ("get", f"/interviews/{id}/review", None), ("post", f"/interviews/{id}/review", {}),
        ("post", f"/interviews/{id}/turns/no/analyze", {}),
        ("post", f"/interviews/{id}/analysis/cancel", {}),
        ("post", f"/interviews/{id}/analysis/clear", {}),
        ("get", f"/interviews/{id}/delete-preview", None),
        ("delete", f"/interviews/{id}", {}), ("get", f"/interviews/{id}/review/export", None),
    ]:
        assert client.request(method, path, json=body).status_code == 503
    assert client.post(f"/interviews/{id}/answers", json={"answer": ANSWER, "visual_metrics": visual()}).status_code == 503
    assert client.post(f"/interviews/{id}/answers", json={"answer": ANSWER}).status_code == 200
    assert client.get(f"/interviews/{id}").status_code == 200


def test_api_valid_model_analysis_cached_and_keywords_verified(api, monkeypatch):
    client, module = api
    id = create_api(client)
    turn = client.post(f"/interviews/{id}/answers", json={"answer": ANSWER}).json()["data"]["turns"][0]
    monkeypatch.delenv("FILEMATE_INTERVIEW_LOCAL_ONLY")
    import filemate.llm_client as llm
    monkeypatch.setattr(llm.LLMConfig, "from_env", lambda: object())
    calls = []

    class Counted(FakeLLM):
        def call(self, **kwargs):
            calls.append(kwargs)
            return super().call(**kwargs)

    monkeypatch.setattr(llm, "LLMClient", lambda _: Counted())
    path = f"/interviews/{id}/turns/{turn['turn_id']}/analyze"
    for _ in range(2):
        response = client.post(path, json={"external_consent": True})
        assert response.status_code == 200
    assert len(calls) == 1
    assert response.json()["data"]["turns"][0]["content_analysis"]["keywords"] == ["范围查询", "有序索引"]
    assert module._storage.get_interview(id)["assessed_turn_count"] == 1
    payload = model_payload() | {"keywords": ["不存在的关键词"]}
    assert InterviewEvaluator(FakeLLM(payload)).evaluate("介绍项目", ANSWER, "后端")["score"] is None


def test_expert_calibration_stays_pending_without_real_expert_samples(tmp_path):
    from evaluation.calibrate_interview import calibrate, spearman

    source = tmp_path / "scores.csv"
    source.write_text("case_id,dimension,model_score,expert_score,scoring_mode,sample_kind\n", encoding="utf-8")
    assert calibrate(source)["status"] == "真实专家校准待评测"
    source.write_text(source.read_text(encoding="utf-8") + "".join(
        f"case_{i},内容,{i * 10},{i * 10},llm,synthetic\n" for i in range(5)
    ), encoding="utf-8")
    assert calibrate(source)["comparisons"][0]["spearman"] == 1
    assert calibrate(source)["real_expert_pairs"] == 0
    assert spearman([1, 1, 2], [3, 3, 2]) == -1
    assert spearman([1, 1, 1], [1, 2, 3]) is None
    source.write_text(source.read_text(encoding="utf-8") + "case_0,内容,0,0,llm,synthetic\n", encoding="utf-8")
    with pytest.raises(ValueError, match="重复"):
        calibrate(source)


@pytest.mark.parametrize("api", ["anonymous"], indirect=True)
def test_anonymous_cannot_read_delete_cancel_other_interview(api):
    owner, module = api
    id = create_api(owner)
    owner.post(f"/interviews/{id}/answers", json={"answer": ANSWER})
    report = owner.post(f"/interviews/{id}/review").json()["data"]
    with TestClient(module.app) as other:
        for path in [f"/interviews/{id}", f"/interviews/{id}/review", f"/interviews/{id}/delete-preview",
                     f"/interviews/{id}/review/export", f"/knowledge/artifacts/{report['artifact_id']}"]:
            assert other.get(path).status_code == 404
        assert other.post(f"/interviews/{id}/analysis/cancel").status_code == 404
        assert other.request("DELETE", f"/interviews/{id}", json={"confirmed": True, "confirmation_token": "a" * 64}).status_code == 200
    assert owner.get(f"/interviews/{id}").status_code == 200
