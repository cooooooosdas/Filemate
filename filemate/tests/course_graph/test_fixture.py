"""Acceptance preparation must never overwrite an existing workspace."""

import importlib
import json

import pytest


def test_fixture_requires_new_absolute_directory(tmp_path):
    prepare = importlib.import_module("scripts.acceptance.course_graph_fixture").prepare
    with pytest.raises(ValueError):
        prepare(tmp_path, "Synthetic934!z")
    assert list(tmp_path.iterdir()) == []
    with pytest.raises(ValueError):
        prepare(type(tmp_path)("relative/audit"), "Synthetic934!z")


def test_fixture_is_original_isolated_and_secret_free(tmp_path):
    prepare = importlib.import_module("scripts.acceptance.course_graph_fixture").prepare
    destination = tmp_path / "fresh"
    result = prepare(destination, "Synthetic934!z")
    assert len(list((destination / "documents").glob("*.txt"))) == 3
    assert (destination / "data/accounts.db").exists()
    assert "Synthetic934!z" not in json.dumps(result)
    assert "recovery" not in json.dumps(result)
    assert result["synthetic"] is True
