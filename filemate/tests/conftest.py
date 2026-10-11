"""隔离合成模型用量账本，禁止回归测试写入真实本地学习空间。"""

import pytest


@pytest.fixture(autouse=True)
def isolated_default_model_ledger(tmp_path, monkeypatch):
    monkeypatch.setenv('FILEMATE_DATA_DIR', str(tmp_path / 'data'))
