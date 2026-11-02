"""Keep the audit manifest usable on the declared Python floor."""

import hashlib
from pathlib import Path

from scripts.acceptance import wrongbook_learning_evidence as evidence


def test_source_hashes_without_path_walk(tmp_path, monkeypatch):
    included = [
        'main.py', 'filemate/资料.py', 'scripts/audit.ps1',
        'filemate/web/src/views/Review.vue', 'filemate/web/tests/review.mjs',
        'filemate/web/package.json',
    ]
    excluded = [
        'filemate/__pycache__/secret.py', 'filemate/node_modules/secret.py',
        'filemate/web/node_modules/secret.py', 'filemate/web/dist/secret.py',
        'scripts/.venv/secret.py', 'scripts/report.txt', 'outside.py',
    ]
    for name in included + excluded:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes('合成内容\n'.encode())

    installed_walk = getattr(Path, 'walk', None)

    def unavailable(path, *args, **kwargs):
        if path in {tmp_path / 'filemate', tmp_path / 'scripts'}:
            raise AssertionError('Path.walk is unavailable before Python 3.12')
        # Keep Python 3.12's own rglob implementation intact during simulation.
        assert installed_walk is not None
        return installed_walk(path, *args, **kwargs)

    monkeypatch.setattr(Path, 'walk', unavailable, raising=False)
    monkeypatch.setattr(evidence, 'ROOT', tmp_path)
    expected_hash = hashlib.sha256('合成内容\n'.encode()).hexdigest()
    assert evidence.source_hashes() == {name: expected_hash for name in included}
