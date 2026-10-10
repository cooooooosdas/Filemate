"""受限的 Microsoft 自然语音适配，不持久化正文或音频。"""

from __future__ import annotations

import asyncio
import threading
import time
from collections import OrderedDict

import edge_tts

VOICES = (
    "zh-CN-XiaoxiaoNeural", "zh-CN-YunxiaNeural",
    "zh-CN-YunxiNeural", "zh-CN-XiaoyiNeural",
)
MAX_AUDIO_BYTES = 8 * 1024 * 1024


class SpeechUnavailable(Exception):
    """语音供应商未返回可播放结果。"""


class SpeechBusy(Exception):
    """当前语音请求超过容量或频率。"""


class MicrosoftSpeech:
    """限定声线、超时、响应大小、全局并发及每个空间请求频率。"""

    def __init__(self) -> None:
        self._slots = threading.BoundedSemaphore(2)
        self._lock = threading.Lock()
        self._requests: OrderedDict[str, list[float]] = OrderedDict()

    async def synthesize(self, text: str, voice: str, scope: str) -> bytes:
        """将已授权的文字合成为内存中的 MP3。"""
        if voice not in VOICES or not text.strip() or len(text) > 5000:
            raise ValueError("讲解文字或声线无效")
        if not self._slots.acquire(blocking=False):
            raise SpeechBusy("自然语音繁忙，请稍后重试")
        try:
            with self._lock:
                now = time.monotonic()
                recent = [stamp for stamp in self._requests.pop(scope, []) if now - stamp < 60]
                self._requests[scope] = recent
                if len(recent) >= 6:
                    raise SpeechBusy("自然语音请求过于频繁，请一分钟后重试")
                recent.append(now)
                while len(self._requests) > 1000:
                    self._requests.popitem(last=False)
            try:
                return await asyncio.wait_for(self._collect(text, voice), timeout=55)
            except (TimeoutError, OSError, edge_tts.exceptions.EdgeTTSException) as exc:
                raise SpeechUnavailable("Microsoft 自然语音暂不可用，请稍后重试") from exc
            except Exception as exc:
                # 供应商异常可能包含请求细节，只向调用方提供固定的安全消息。
                raise SpeechUnavailable("Microsoft 自然语音暂不可用，请稍后重试") from exc
        finally:
            self._slots.release()

    async def _collect(self, text: str, voice: str) -> bytes:
        """在响应大小上限内收集供应商流。"""
        audio = bytearray()
        stream = edge_tts.Communicate(text, voice, connect_timeout=5, receive_timeout=15)
        async for packet in stream.stream():
            if packet["type"] != "audio":
                continue
            audio.extend(packet["data"])
            if len(audio) > MAX_AUDIO_BYTES:
                raise SpeechUnavailable("语音响应超过大小限制，请缩短讲解文字")
        if not audio:
            raise SpeechUnavailable("Microsoft 未返回音频，请稍后重试")
        return bytes(audio)
