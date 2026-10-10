"""合成回归：自然语音授权、边界和故障，不证明真实供应商可用。"""

import asyncio

import pytest
from fastapi.testclient import TestClient

from filemate.speech import MicrosoftSpeech, SpeechBusy, SpeechUnavailable
from filemate.tests import test_digital_human

local_server = test_digital_human.local_server


def test_speech_requires_consent_and_valid_voice(local_server, monkeypatch):
    module, _ = local_server
    calls = []

    async def synthesize(text, voice, scope):
        calls.append((text, voice, scope))
        return b"synthetic-mp3"

    monkeypatch.setattr(module._natural_speech, "synthesize", synthesize)
    with TestClient(module.app) as client:
        assert client.post('/api/digital-human/speech', json={'text': '学习'}).status_code == 403
        for invalid in ({'text': ' '}, {'text': '学' * 5001}, {'voice_id': 'default'}, {'allow_external_voice': 1}):
            data = {'text': '学习', 'allow_external_voice': True, **invalid}
            assert client.post('/api/digital-human/speech', json=data).status_code == 422
        assert calls == []
        response = client.post('/api/digital-human/speech', json={'text': '学习', 'allow_external_voice': True})
        assert response.status_code == 200 and response.content == b'synthetic-mp3'
        assert response.headers['cache-control'] == 'no-store'
        assert calls == [('学习', 'zh-CN-XiaoxiaoNeural', 'local')]
        monkeypatch.setenv('FILEMATE_ENABLE_NATURAL_VOICE', '0')
        assert client.post('/api/digital-human/speech', json={'text': '学习', 'allow_external_voice': True}).status_code == 503
        assert client.get('/api/health').status_code == 200


@pytest.mark.parametrize('failure,code', [(SpeechBusy, 429), (SpeechUnavailable, 502)])
def test_speech_failure_does_not_break_other_modules(local_server, monkeypatch, failure, code):
    module, _ = local_server

    async def synthesize(*args):
        raise failure('合成故障')

    monkeypatch.setattr(module._natural_speech, 'synthesize', synthesize)
    with TestClient(module.app) as client:
        assert client.post('/api/digital-human/speech', json={'text': '学习', 'allow_external_voice': True}).status_code == code
        assert client.get('/api/digital-human/playbacks').status_code == 200
        assert client.get('/api/health').status_code == 200


@pytest.mark.asyncio
async def test_provider_bounds_calls_and_releases_capacity(monkeypatch):
    provider = MicrosoftSpeech()

    async def failed(*args):
        raise RuntimeError('sensitive-provider-response')

    monkeypatch.setattr(provider, '_collect', failed)
    for _ in range(6):
        with pytest.raises(SpeechUnavailable, match='暂不可用') as error:
            await provider.synthesize('学习', 'zh-CN-XiaoxiaoNeural', 'a')
        assert 'sensitive' not in str(error.value)
    with pytest.raises(SpeechBusy):
        await provider.synthesize('学习', 'zh-CN-XiaoxiaoNeural', 'a')
    started = asyncio.Event()

    async def hold(*args):
        started.set()
        await asyncio.sleep(100)

    monkeypatch.setattr(provider, '_collect', hold)
    task = asyncio.create_task(provider.synthesize('学习', 'zh-CN-XiaoxiaoNeural', 'b'))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert provider._slots.acquire(blocking=False)
    assert provider._slots.acquire(blocking=False)
    provider._slots.release()
    provider._slots.release()


@pytest.mark.asyncio
async def test_provider_rejects_empty_and_oversized_audio(monkeypatch):
    from filemate import speech

    class Stream:
        async def stream(self):
            yield {'type': 'audio', 'data': b'x' * 30}

    monkeypatch.setattr(speech.edge_tts, 'Communicate', lambda *a, **k: Stream())
    monkeypatch.setattr(speech, 'MAX_AUDIO_BYTES', 20)
    with pytest.raises(SpeechUnavailable):
        await MicrosoftSpeech().synthesize('学习', 'zh-CN-XiaoxiaoNeural', 'a')
