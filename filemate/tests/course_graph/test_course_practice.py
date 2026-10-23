# ruff: noqa: F811
"""Synthetic, offline practice work and confirmation fault contracts."""

import importlib
import json
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest

from filemate.course_graph.models import CourseGraphError
from filemate.execution.storage import SQLiteStorage
from filemate.llm_client.exceptions import LLMTimeoutError
from filemate.operations.personal_backup import PersonalBackup
from filemate.tests.course_graph.test_fusion import merge, pair  # noqa: F401
from filemate.tests.course_graph.test_learning_evidence import NOW
from filemate.tests.course_graph.test_learning_links import learning_context  # noqa: F401


def service(context, provider=None, clock=lambda: NOW):
    return importlib.import_module('filemate.course_graph.practice').PracticeService(
        context[0], lambda: provider, clock)


def generate(context, svc=None, **overrides):
    arguments = {'difficulty': 'standard', 'count': 1, 'mode': 'local',
                 'request_key': 'practice_generate_0001', **overrides}
    return (svc or service(context)).generate(context[1], context[3], **arguments)


def decisions(work):
    return [{'index': i, 'verdict': 'accept'} for i in range(len(work['payload']['questions']))]


def confirm(context, work, svc=None, key='practice_confirm_0001'):
    svc = svc or service(context)
    items = decisions(work)
    preview = svc.preview(context[1], work['work_id'], items)
    return svc.confirm(context[1], work['work_id'], items, preview['confirmation_token'], key, True)


def test_local_cloze_is_supported_not_llm(learning_context):
    class Forbidden:
        def call_structured(self, **kwargs):
            pytest.fail('Local practice must never call a provider')
    work = generate(learning_context, service(learning_context, Forbidden()))
    assert work['status'] == 'ready' and work['payload']['mode'] == 'local'
    question = work['payload']['questions'][0]
    assert '____' in question['stem'] and question['answer'] == '栈'
    assert question['answer'] in work['payload']['quotes'][0]['quote']
    assert learning_context[0]._conn().execute("SELECT COUNT(*) FROM artifacts WHERE metadata LIKE '%course_learning_work%'").fetchone()[0] == 0


def test_human_review_required_before_artifact(learning_context):
    work, svc = generate(learning_context), service(learning_context)
    with pytest.raises(CourseGraphError, match='review_required'):
        svc.preview(learning_context[1], work['work_id'], [])
    with pytest.raises(CourseGraphError, match='confirmation_required'):
        svc.confirm(learning_context[1], work['work_id'], decisions(work), '', 'practice_confirm_0001', False)


def test_confirmed_selection_creates_one_real_artifact_and_links(learning_context):
    store, cid, *_ = learning_context
    svc, work = service(learning_context), generate(learning_context)
    items = decisions(work)
    token = svc.preview(cid, work['work_id'], items)['confirmation_token']
    args = (cid, work['work_id'], items, token, 'practice_confirm_0001', True)
    receipt = svc.confirm(*args)
    assert svc.confirm(*args) == receipt
    assert svc.confirm(cid, work['work_id'], items, token, 'practice_confirm_0002', True) == receipt
    artifact = store.get_artifact(receipt['artifact_id'])
    assert artifact['artifact_type'] == 'questions' and artifact['content'][0]['answer'] == '栈'
    assert store._conn().execute('SELECT COUNT(*) FROM kg_question_links WHERE artifact_id=?',
                                 (receipt['artifact_id'],)).fetchone()[0] == 1
    assert store._conn().execute('SELECT COUNT(*) FROM quiz_attempts').fetchone()[0] == 0
    from filemate.study import check_answer
    result = check_answer(artifact['content'][0], '不知道')
    store.record_quiz_attempt(artifact_id=receipt['artifact_id'], question_index=0,
        user_answer='不知道', is_correct=result, score=1 if result else 0, feedback='真实规则核对')
    assert store._conn().execute('SELECT COUNT(*) FROM wrong_questions').fetchone()[0] == 1


def test_model_requires_consent_and_runs_once_outside_write_lock(learning_context):
    store, cid, *_ = learning_context
    calls = []

    class Provider:
        def call_structured(self, **kwargs):
            calls.append(kwargs)
            other = SQLiteStorage(store.db_path)
            try:
                with other._conn() as conn:
                    conn.execute("UPDATE kg_courses SET name='模型运行仍可写' WHERE course_id=?", (cid,))
                    conn.execute("UPDATE kg_courses SET name='数据结构' WHERE course_id=?", (cid,))
            finally:
                other.close()
            data = json.loads(kwargs['messages'][0]['content'])
            return {'questions': [{'question_type': 'fill', 'stem': '____是后进先出的线性表。',
                'answer': '栈', 'citation_ids': [data['quotes'][0]['evidence_id']]}]}

    svc = service(learning_context, Provider())
    with pytest.raises(CourseGraphError, match='model_consent_required'):
        generate(learning_context, svc, mode='llm')
    work = generate(learning_context, svc, mode='llm', allow_external_model=True)
    assert work['status'] == 'ready' and len(calls) == 1
    assert calls[0]['timeout'] == 20 and calls[0]['retry'] == 1
    assert generate(learning_context, svc, mode='llm', allow_external_model=True)['work_id'] == work['work_id']
    assert len(calls) == 1


@pytest.mark.parametrize('question', [
    {'question_type': 'fill', 'stem': '____', 'answer': '', 'citation_ids': ['unknown']},
    {'question_type': 'fill', 'stem': '____', 'answer': '栈', 'citation_ids': ['unknown']},
])
def test_malformed_answer_or_unknown_quote_cannot_confirm(learning_context, question):
    class Provider:
        def call_structured(self, **kwargs):
            return {'questions': [question]}
    work = generate(learning_context, service(learning_context, Provider()), mode='llm', allow_external_model=True)
    assert work['status'] == 'failed' and work['error_code'] == 'invalid_output'
    with pytest.raises(CourseGraphError):
        service(learning_context).preview(learning_context[1], work['work_id'], [{'index': 0, 'verdict': 'accept'}])


def test_revised_answer_revalidated_against_quote(learning_context):
    work, svc = generate(learning_context), service(learning_context)
    question = {**work['payload']['questions'][0], 'answer': '无依据的答案'}
    with pytest.raises(CourseGraphError, match='unsupported_answer'):
        svc.preview(learning_context[1], work['work_id'], [{'index': 0, 'verdict': 'accept', 'question': question}])


def test_source_purge_keeps_request_tombstone_and_daily_budget(learning_context):
    store, cid, sid, nid, *_ = learning_context
    svc = service(learning_context)
    work = generate(learning_context, svc)
    store.delete_source(sid)
    assert store._conn().execute('SELECT COUNT(*) FROM kg_learning_work').fetchone()[0] == 0
    inputs = {'concept_id': nid, 'difficulty': 'standard', 'count': 1, 'mode': 'local'}
    with pytest.raises(CourseGraphError, match='learning_work_unavailable'):
        svc.work.find(cid, 'practice', inputs, 'practice_generate_0001')
    assert store._conn().execute("SELECT COUNT(*) FROM kg_changes WHERE kind='learning_work_claim'").fetchone()[0] == 1
    with pytest.raises(CourseGraphError):
        svc.get(cid, work['work_id'])


def test_existing_other_command_key_is_a_conflict_not_storage_failure(learning_context):
    from filemate.course_graph.learning_evidence import learning_snapshot
    store, cid, sid, nid, *_ = learning_context
    projection = learning_snapshot(store, cid, now=NOW)
    with pytest.raises(CourseGraphError, match='request_key_conflict'):
        service(learning_context).work.claim(cid, 'practice', {'concept_id': nid}, 'create_draft_00001',
            [sid], projection['graph_digest'], projection['evidence_digest'])


def test_formal_practice_and_provenance_backup_roundtrip(learning_context, tmp_path):
    store, cid, sid, *_ = learning_context
    work = generate(learning_context)
    receipt = confirm(learning_context, work)
    artifact = store.get_artifact(receipt['artifact_id'])
    backup = PersonalBackup(store, 'local', tmp_path / 'inbox', tmp_path / 'archive')
    raw = backup.export()
    store.delete_source(sid)
    preview = backup.preview(raw)
    backup.restore(preview['backup_id'], preview['confirmation_token'])
    assert store.get_artifact(receipt['artifact_id']) == artifact
    assert store._conn().execute('SELECT source_id FROM kg_learning_artifact_sources WHERE artifact_id=?',
                                 (receipt['artifact_id'],)).fetchone()[0] == sid
    assert service(learning_context).get(cid, work['work_id'])['status'] == 'confirmed'
    assert store._conn().execute('PRAGMA foreign_key_check').fetchall() == []


@pytest.mark.parametrize('error', [LLMTimeoutError('secret-key private-text'), RuntimeError('secret-key private-text')])
def test_timeout_and_provider_error_are_persisted_failure_without_secret(learning_context, error):
    class Provider:
        def call_structured(self, **kwargs):
            raise error
    work = generate(learning_context, service(learning_context, Provider()), mode='llm', allow_external_model=True)
    assert work['status'] == 'failed'
    assert work['error_code'] in {'provider_failed', 'model_timeout'}
    stored = str(list(learning_context[0]._conn().execute('SELECT payload,error_code FROM kg_learning_work').fetchone()))
    assert 'secret-key' not in stored and 'private-text' not in stored


@pytest.mark.parametrize('interrupt', ['cancel', 'restore', 'source_change'])
def test_cancel_restore_source_change_blocks_late_finish(learning_context, tmp_path, interrupt):
    store, cid, sid, *_ = learning_context
    entered, release = Event(), Event()

    class Provider:
        def call_structured(self, **kwargs):
            entered.set()
            assert release.wait(10)
            data = json.loads(kwargs['messages'][0]['content'])
            return {'questions': [{'question_type': 'fill', 'stem': '____是线性表。',
                'answer': '栈', 'citation_ids': [data['quotes'][0]['evidence_id']]}]}

    svc = service(learning_context, Provider())
    backup = PersonalBackup(store, 'local', tmp_path / 'inbox', tmp_path / 'archive')
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(generate, learning_context, svc, mode='llm', allow_external_model=True)
            assert entered.wait(5)
            wid = store._conn().execute('SELECT work_id FROM kg_learning_work').fetchone()[0]
            if interrupt == 'cancel':
                svc.work.cancel(cid, wid, 'practice_cancel_0001')
            elif interrupt == 'restore':
                raw = backup.export()
                preview = backup.preview(raw)
                backup.restore(preview['backup_id'], preview['confirmation_token'])
            else:
                store.save_source(source_id=sid, original_name='修订', source_path='x.txt', raw_text='正文变了')
            release.set()
            assert future.result(5)['status'] in {'cancelled', 'interrupted'}
            assert store._conn().execute("SELECT COUNT(*) FROM kg_learning_work WHERE status='ready'").fetchone()[0] == 0
    finally:
        release.set()


def test_rate_and_running_budget(learning_context):
    store, cid, sid, nid, *_ = learning_context
    from filemate.course_graph.learning_evidence import learning_snapshot
    from filemate.course_graph.learning_work import LearningWorkService
    projection = learning_snapshot(store, cid, now=NOW)
    svc = LearningWorkService(store, lambda: NOW)

    def claim(key):
        return svc.claim(cid, 'practice', {'concept_id': nid}, key, [sid],
                         projection['graph_digest'], projection['evidence_digest'])

    first = claim('budget_practice_00001')
    with pytest.raises(CourseGraphError, match='learning_busy'):
        claim('budget_practice_00002')
    svc.cancel(cid, first['work_id'], 'budget_cancel_00001')
    for i in range(1, 30):
        work = claim(f'budget_practice_{i + 1:05}')
        svc.cancel(cid, work['work_id'], f'budget_cancel_{i + 1:05}')
    with pytest.raises(CourseGraphError, match='learning_budget_exceeded'):
        claim('budget_practice_00031')
    assert len(list(store._conn().execute('SELECT work_id FROM kg_learning_work'))) == 30


def test_multi_source_formal_question_is_purged_with_nonprimary_source(pair):
    context, ids = pair
    store, _, cid, sid = context
    merge(pair)
    learning = (store, cid, sid, ids[0], '', {})
    work = generate(learning, count=2)
    assert len(work['payload']['quotes']) == 2
    receipt = confirm(learning, work)
    artifact = store.get_artifact(receipt['artifact_id'])
    store.record_quiz_attempt(artifact_id=receipt['artifact_id'], question_index=0,
        user_answer='不知道', is_correct=False, score=0, feedback='合成回归')
    edited = [{**q, 'stem': q['stem'] + '（修订）'} for q in artifact['content']]
    store.update_artifact(receipt['artifact_id'], title='修订练习', content=edited)
    history = [r[0] for r in store._conn().execute('''SELECT artifact_id FROM artifacts
        WHERE json_extract(metadata,'$.question_revision_parent')=?''', (receipt['artifact_id'],))]
    assert len(history) == 1
    other_sid = next(q['source_id'] for q in work['payload']['quotes'] if q['source_id'] != artifact['source_id'])
    impact = store.source_deletion_preview(other_sid)
    assert impact['affected']['course_learning_derived_artifacts'] == 2
    store.delete_source(other_sid)
    assert store.get_artifact(receipt['artifact_id']) is None
    assert all(store.get_artifact(aid) is None for aid in history)
    assert store._conn().execute('PRAGMA foreign_key_check').fetchall() == []


@pytest.mark.parametrize('count,difficulty', [(True, 'standard'), (6, 'standard'), (1, 'unknown')])
def test_invalid_generation_options_do_not_create_work(learning_context, count, difficulty):
    with pytest.raises(CourseGraphError):
        generate(learning_context, count=count, difficulty=difficulty)
    assert learning_context[0]._conn().execute('SELECT COUNT(*) FROM kg_learning_work').fetchone()[0] == 0
