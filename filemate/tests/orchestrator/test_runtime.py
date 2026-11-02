"""Runtime proofs never mutate the inspected database or fake an engine."""

import hashlib
import importlib
import importlib.util

import pytest


def runtime():
    assert importlib.util.find_spec('scripts.acceptance.orchestrator_runtime'), 'runtime verifier missing'
    return importlib.import_module('scripts.acceptance.orchestrator_runtime')


def test_runtime_probe_cannot_migrate_or_write(world, tmp_path):
    store = world['store']
    store._conn().execute('PRAGMA wal_checkpoint(TRUNCATE)')
    before = hashlib.sha256(store.db_path.read_bytes()).hexdigest()
    report = runtime().probe(store.db_path)
    assert report['schema_version'] == 36 and report['mode'] == 'probe_only'
    assert hashlib.sha256(store.db_path.read_bytes()).hexdigest() == before
    assert 'source_path' not in str(report)


def test_schema36_unchanged_by_schedule(tmp_path):
    report = runtime().self_test(tmp_path)
    assert report['mode'] == 'full_application' and report['status'] == 'PASS'
    assert report['schema_before'] == report['schema_after'] == 36
    assert report['domain_fingerprint_unchanged'] and report['integrity'] == 'ok'


def test_runtime_cli_rejects_missing_or_wrong_engine(tmp_path):
    with pytest.raises((ValueError, FileNotFoundError)):
        runtime().engine_subset(tmp_path / 'missing.exe', tmp_path / 'candidate')


def test_real_old_engine_works_under_unicode_candidate(tmp_path):
    import sys
    from pathlib import Path
    engine = Path('_working/wrongbook-e-20261029/sqlite3.exe')
    if sys.platform != 'win32' or not engine.is_file():
        pytest.skip('actual Windows SQLite 3.26 engine is an external validation dependency')
    result = runtime().engine_subset(engine, tmp_path / '中文候选')
    assert result['status'] == 'PASS' and result['full_target_application_verified'] is False


def test_full_application_proves_c_contracts_and_nonempty_protected_evidence(tmp_path):
    report = runtime().self_test(tmp_path)
    assert report['c_read_contracts'] and all(report['c_read_contracts'].values())
    assert report['protected_evidence_counts']
    assert all(value > 0 for value in report['protected_evidence_counts'].values())
    assert report['domain_fingerprint_unchanged']
