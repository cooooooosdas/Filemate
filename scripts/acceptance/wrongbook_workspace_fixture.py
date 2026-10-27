"""Prepare isolated original synthetic accounts for review workspace acceptance."""

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from filemate.accounts import AccountStore, validate_password
from filemate.execution.storage import SQLiteStorage
from filemate.study.question_validation import validate_question


def seed_course(store: SQLiteStorage, sid: str, aid: str) -> dict[str, Any]:
    """Publish original local concepts and explicitly map a synthetic question."""
    from filemate.course_graph import question_links, review
    from filemate.course_graph.drafts import DraftService
    from filemate.course_graph.repository import CourseGraphRepository
    repo = CourseGraphRepository(store)
    cid = repo.create_course('合成数据结构复盘', 'synthetic_course_0001')['course_id']
    repo.attach_sources(cid, [sid], None, 0)
    service = DraftService(store, lambda: None, lambda: datetime.now(timezone.utc))
    did = service.create_group(cid, [sid], 'local', 'synthetic_draft_0001')['draft_id']
    snap = service.extract_source(cid, did, sid, 'synthetic_extract_0001', False)
    choices = [{'item_id': n['item_id'], 'verdict': 'accept'} for source in snap['sources'] for n in source['payload'].get('nodes', [])]
    review.save_decisions(store, cid, did, snap['revision_digest'], [review.ItemDecision(**n) for n in choices])
    preview = review.preview_review(store, cid, did)
    review.confirm_review(store, cid, did, 'synthetic_publish_0001', preview['confirmation_token'], True)
    nid = store._conn().execute("SELECT concept_id FROM kg_concepts WHERE label='栈' AND course_id=?", (cid,)).fetchone()[0]
    from filemate.course_graph.question_links import question_digest
    refs = [{'artifact_id': aid, 'question_index': i, 'question_digest': question_digest(q)}
            for i, q in enumerate(store.get_artifact(aid)['content'][:3])]
    preview = question_links.preview_question_links(store, cid, nid, refs, True)
    question_links.confirm_question_links(store, cid, nid, refs, True, preview['confirmation_token'], 'synthetic_links_0001', True)
    return {'course_id': cid, 'concept_id': nid}


def seed(database: Path, count: int) -> dict[str, Any]:
    """Seed bounded synthetic wrong records without contacting a model."""
    store = SQLiteStorage(database)
    store.init_schema()
    source = store.save_source(original_name='原创合成数据结构-' + '长文件名' * 25 + '.txt', source_path='synthetic.txt', raw_text='栈：后进先出的线性表。队列：先进先出的线性表。原创合成资料：栈后进先出，队列先进先出。此资料仅用于工程测试。')
    questions = [{'question_type': 'fill', 'stem': f'合成复盘{i + 1:05}：栈遵循什么顺序？', 'answer': '后进先出', 'analysis': '原创解释：栈后进先出。'} for i in range(max(1, count))]
    questions[0].update(question_type='choice', options=['后进先出', '先进先出'], answer='A')
    if count > 2:
        questions[2].update(question_type='short_answer', stem='合成复盘00003：解释栈和队列及 O(n log n)。')
        questions[3].update(question_type='short_answer', stem='合成复盘00004：阅读以下超长代码', code='int main() {\n' + '  // 原创工程验收代码\n' * 300 + '}')
    for question in questions:
        validate_question(question)
    aid = store.save_artifact(source_id=source, artifact_type='questions', content=questions)
    history = store.save_artifact(source_id=source, artifact_type='questions', content=[questions[0]], metadata={'read_only_snapshot': True})
    refs = []
    if count:
        store.record_quiz_attempt(artifact_id=aid, question_index=0, user_answer='B', is_correct=False, score=0, feedback='合成工程验收错答')
        conn = store._conn()
        base = dict(conn.execute('SELECT * FROM wrong_questions').fetchone())
        conn.execute('DELETE FROM wrong_questions')
        fields = list(base)
        values = []
        for i in range(count):
            row = {**base, 'wrong_id': f'synthetic-wrong-{i + 1:05}', 'question_index': i, 'question': json.dumps(questions[i], ensure_ascii=False), 'error_count': i % 17 + 1, 'next_review_at': '2020-01-01T00:00:00+00:00'}
            if i == 5:
                row['schedule_status'] = 'paused'
            if i == 6:
                row['next_review_at'] = '2026-02-30T00:00:00Z'
            if i == 7:
                row['source_id'] = None
            if i == 8:
                row['mastered'] = 1
            if i == 9:
                row.update(artifact_id=history, question_index=0, question=json.dumps(questions[0], ensure_ascii=False))
            refs.append({'wrong_id': row['wrong_id'], 'artifact_id': row['artifact_id'], 'question_index': row['question_index']})
            values.append(tuple(row[f] for f in fields))
        conn.executemany('INSERT INTO wrong_questions (' + ','.join(fields) + ') VALUES (' + ','.join('?' for _ in fields) + ')', values)
        conn.commit()
    graph = seed_course(store, source, aid) if count == 100 else {}
    store.close()
    return {**graph, 'source_id': source, 'artifact_id': aid, 'history_artifact_id': history, 'wrong_count': count, 'examples': refs[:10], 'last': refs[-1] if refs else None}


def prepare(data_root: Path, password: str) -> dict[str, Any]:
    """Refuse existing paths and keep plaintext credentials out of evidence."""
    if not data_root.is_absolute() or data_root.exists():
        raise ValueError('需指定尚不存在的绝对目录')
    validate_password(password)
    data_root.mkdir(parents=True, exist_ok=False)
    (data_root / '.synthetic-wrongbook').touch()
    database = data_root / 'accounts.db'
    store = SQLiteStorage(database)
    store.init_schema()
    store.close()
    accounts = AccountStore(database)
    users = []
    for count in (10000, 1000, 100, 0):
        workspace = f'u_{uuid4().hex}'
        email = f'wrongbook-{count}@example.invalid'
        accounts.register(email, password, f'合成复盘{count}', workspace, False)
        users.append({'email': email, 'workspace': workspace, **seed(data_root / 'users' / workspace / 'filemate.db', count)})
    result = {'synthetic': True, 'data_root': str(data_root), 'database_path': str(database), 'users': users, 'notice': '原创工程验收资料；不代表真人学习效果。密码只由环境变量提供。'}
    (data_root / 'manifest.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-root', type=Path, required=True)
    args = parser.parse_args()
    password = os.environ.get('FILEMATE_AUDIT_PASSWORD', '')
    if not password:
        parser.error('需通过FILEMATE_AUDIT_PASSWORD提供临时合成账户密码')
    print(json.dumps(prepare(args.data_root, password), ensure_ascii=False, indent=2))
