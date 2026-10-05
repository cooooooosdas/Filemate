# ruff: noqa: F811
"""全量错题分页与筛选回归，全部数据均为合成。"""

import json

from fastapi.testclient import TestClient

from filemate.tests.test_server_persistence import server_module  # noqa: F401


def test_ten_thousand_wrong_questions_are_all_reachable(server_module):
    module, store = server_module
    source = store.save_source(original_name="合成分页教材", source_path="synthetic.txt")
    questions = [{"question": f"合成题{i:05d}", "answer": "答案"} for i in range(10000)]
    artifact = store.save_artifact(source_id=source, artifact_type="questions", content=questions)
    conn = store._conn()
    conn.executemany("INSERT INTO wrong_questions(wrong_id,artifact_id,source_id,question_index,question,mastered,error_cause,next_review_at) VALUES(?,?,?,?,?,?,?,?)",
                     [(f"w{i:05d}", artifact, source, i, json.dumps(questions[i], ensure_ascii=False),
                       int(i % 3 == 0), "concept_gap" if i % 2 else "memory_gap",
                       "2000-01-01T00:00:00+00:00" if i % 2 else "2099-01-01T00:00:00+00:00") for i in range(10000)])
    conn.commit()
    all_ids = set()
    with TestClient(module.app) as client:
        for mastered in (False, True):
            offset = 0
            while True:
                response = client.get("/wrongbook/page", params={"mastered": str(mastered).lower(), "limit": 200, "offset": offset})
                assert response.status_code == 200
                page = response.json()["data"]
                ids = {row["wrong_id"] for row in page["items"]}
                assert len(ids) == len(page["items"]) and not all_ids.intersection(ids)
                all_ids.update(ids)
                offset += len(ids)
                if not page["has_more"]:
                    assert offset == page["total"]
                    break
        assert len(all_ids) == 10000
        found = client.get("/wrongbook/page", params={"mastered": "true", "q": "合成题09999"}).json()["data"]
        assert found["total"] == 1 and found["items"][0]["wrong_id"] == "w09999"
        assert client.get("/wrongbook/page", params={"q": "%"}).json()["data"]["total"] == 0
        due = client.get("/wrongbook/page", params={"due_only": "true", "error_cause": "concept_gap", "source_id": source}).json()["data"]
        assert due["total"] == sum(i % 3 != 0 and i % 2 != 0 for i in range(10000))
        assert all(row["error_cause"] == "concept_gap" for row in due["items"])
        first = client.get("/wrongbook?limit=20").json()["data"]
        second = client.get("/wrongbook?limit=20&offset=20").json()["data"]
        assert {row["wrong_id"] for row in first}.isdisjoint(row["wrong_id"] for row in second)
        for params in ({"offset": -1}, {"limit": 201}, {"error_cause": "invented"}, {"q": "x" * 161}):
            assert client.get("/wrongbook/page", params=params).status_code == 422
