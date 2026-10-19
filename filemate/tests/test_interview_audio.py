# ruff: noqa: F811
"""Synthetic audio evidence contracts; no physical microphone or vendor accuracy claims."""

from copy import deepcopy

import pytest
from pydantic import ValidationError

from filemate.execution.storage import SQLiteStorage
from filemate.interview_coach.commands import local_evaluation
from filemate.interview_coach.models import SubmitAnswer
from filemate.interview_coach.repository import CoachRepository
from filemate.interview_review.reports import build_report, report_markdown, report_pdf
from filemate.interview_review.repository import ReviewRepository
from filemate.interview_runtime import RuntimeCommand
from filemate.operations.personal_backup import PersonalBackup
from filemate.tests.test_accounts import account_server  # noqa: F401
from filemate.tests.test_interview_coach_api import api  # noqa: F401
from filemate.tests.test_interview_runtime_api import action, prepare


def evidence():
    return {
        "source": "browser_media_v1", "duration_seconds": 2,
        "audio": {"status": "measured", "summary": {
            "method": "web_audio_energy_v1", "duration_seconds": 2,
            "sample_rate": 8000, "sample_count": 16000, "rms": 0.2,
            "low_energy_seconds": 0.5, "clipping_ratio": 0.01, "threshold": 0.01,
        }},
        "transcription": {
            "provider": "browser_web_speech", "status": "completed", "language": "zh-CN",
            "segments": [{"text": "识别原文", "confidence": None, "callback_seconds": 1}],
            "confidence": None,
        },
    }


def command(metrics):
    return SubmitAnswer(answer="人工编辑后的回答", question_index=0, expected_revision=0,
                        request_key="audio_contract_0001", fluency_metrics=metrics)


def test_new_audio_is_durable_versioned_and_does_not_change_score(tmp_path):
    store = SQLiteStorage(tmp_path / "synthetic.db")
    store.init_schema()
    try:
        sid = store.create_interview(target_role="开发", scenario="技术面", difficulty="标准",
                                     questions=["说明RAII"])['interview_id']
        metrics = command(evidence()).fluency_metrics
        plain = local_evaluation("人工编辑后的回答", None, speech_language="zh-CN")
        evaluated = local_evaluation("人工编辑后的回答", metrics, speech_language="zh-CN")
        assert evaluated['score'] == plain['score']
        assert evaluated['dimensions'] == plain['dimensions']
        assert evaluated['fluency'] == metrics
        repo = CoachRepository(store)
        first = repo.submit(sid, command(metrics)).snapshot.current_attempt
        second_command = command({**metrics, 'transcription': None}).model_copy(update={
            'expected_revision': repo.snapshot(sid).revision,
            'expected_attempt_id': first.attempt_id, 'request_key': 'audio_contract_0002',
        })
        second = repo.submit(sid, second_command).snapshot.current_attempt
        assert first.attempt_id != second.attempt_id
        history = repo.list_attempts(sid, first.turn_id)['items']
        assert history[1]['fluency_metrics']['transcription']['confidence'] is None
        report = build_report(repo.snapshot(sid).session)
        assert report['audio']['sampled_turns'] == 1
        assert report['audio']['duration_seconds'] == 2
        assert report['expression']['speech_turns'] == 0
        assert report['turns'][0]['audio']['summary']['rms'] == 0.2
        markdown = report_markdown(report)
        assert '音频' in markdown and '非能力评分' in markdown
        assert report_pdf(report).startswith(b'%PDF')
    finally:
        store.close()


@pytest.mark.parametrize('change', [
    lambda v: v.update(audio=None, transcription=None),
    lambda v: v['audio']['summary'].update(rms=float('nan')),
    lambda v: v['audio']['summary'].update(low_energy_seconds=3),
    lambda v: v['audio']['summary'].update(sample_count=1),
    lambda v: v['transcription'].update(status='listening'),
    lambda v: v['transcription']['segments'][0].update(confidence=1.1),
    lambda v: v['transcription']['segments'][0].update(text='x' * 1001),
    lambda v: v.update(duration_seconds=601),
])
def test_rejects_impossible_or_unfinished_evidence_at_request_boundary(change):
    value = deepcopy(evidence())
    change(value)
    with pytest.raises(ValidationError):
        command(value)
    with pytest.raises(ValidationError):
        RuntimeCommand(kind='submit', expected_revision=0, expected_token='a'*16,
                       request_key='audio_runtime_0001', answer='回答', fluency_metrics=value)


def test_unknown_confidence_is_not_filled_and_callbacks_are_not_audio_timestamps():
    value = evidence()
    value['audio'] = None
    value['transcription']['confidence'] = 0.99
    validated = command(value).fluency_metrics
    assert validated['transcription']['confidence'] is None
    assert validated['transcription']['segments'][0]['callback_seconds'] == 1
    assert 'markers' not in validated


def test_audio_summary_backup_restore_delete(tmp_path):
    store = SQLiteStorage(tmp_path / "audio.db")
    store.init_schema()
    try:
        sid = store.create_interview(target_role="开发", scenario="技术面", difficulty="标准",
                                     questions=["说明索引"])['interview_id']
        repo = CoachRepository(store)
        saved = repo.submit(sid, command(evidence())).snapshot.current_attempt
        backup = PersonalBackup(store, 'local', tmp_path / 'inbox', tmp_path / 'archive')
        raw = backup.export()
        preview = backup.preview(raw)
        backup.restore(preview['backup_id'], preview['confirmation_token'])
        restored = repo.snapshot(sid).current_attempt
        assert restored.attempt_id == saved.attempt_id
        assert restored.fluency_metrics == saved.fluency_metrics
        review = ReviewRepository(store)
        preview = review.delete_preview(sid)
        assert review.delete(sid, preview['confirmation_token'])['deleted']
        assert store._conn().execute('SELECT COUNT(*) FROM interview_answer_attempts').fetchone()[0] == 0
    finally:
        store.close()


def test_runtime_invalid_audio_returns_422_before_command(api, monkeypatch):
    client, _ = api
    monkeypatch.setenv('FILEMATE_ENABLE_INTERVIEW_RUNTIME', '1')
    state = prepare(client).json()['data']
    state = action(client, state, 'start').json()['data']['snapshot']
    invalid = evidence()
    invalid['audio']['summary']['rms'] = 10
    response = action(client, state, 'submit', answer='原回答', fluency_metrics=invalid)
    assert response.status_code == 422
    valid = action(client, state, 'submit', answer='原回答', fluency_metrics=evidence())
    assert valid.status_code == 200, valid.text
    assert valid.json()['data']['snapshot']['current_attempt']['fluency_metrics']['source'] == 'browser_media_v1'
