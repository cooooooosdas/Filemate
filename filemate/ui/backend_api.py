"""Gradio 后端 API 封装，供 UI 层调用。"""

from __future__ import annotations

from pathlib import Path


class BackendAPI:
    """后端 API 封装。TODO(余恒 + 胡希)"""

    def submit(self, file_path: str) -> dict:
        raise NotImplementedError("TODO: submit")

    def confirm(self, session_id: str, accepted: bool, edits: dict | None = None) -> dict:
        raise NotImplementedError("TODO: confirm")

    def get_queue(self) -> list[dict]:
        raise NotImplementedError("TODO: get_queue")
