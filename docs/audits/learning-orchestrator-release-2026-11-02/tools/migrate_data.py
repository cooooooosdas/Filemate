"""Upgrade isolated or quiesced databases and verify pre-existing row fingerprints."""
import hashlib
import json
import sqlite3
import sys
from collections import Counter
from contextlib import closing
from pathlib import Path

from filemate.course_graph.privacy import normalize_restored_course_graph
from filemate.execution.storage import SQLiteStorage
from filemate.interview_assessment.repository import normalize_restored_assessments
from filemate.interview_coach.repository import normalize_restored_coach
from filemate.interview_config import normalize_restored_configuration
from filemate.interview_runtime import normalize_restored_runtime
from filemate.runtime_governance import BudgetStore, resource_schema_version


def fingerprint(conn, table, columns=None):
    assert '"' not in table
    columns = columns or [row[1] for row in conn.execute(f'PRAGMA table_info("{table}")')]
    assert all('"' not in name for name in columns)
    selected = ",".join('"' + name + '"' for name in columns)
    value = hashlib.sha256()
    for row in conn.execute(f'SELECT {selected} FROM "{table}" ORDER BY rowid'):
        value.update(repr(tuple(row)).encode('utf-8'))
        value.update(b'\n')
    return value.hexdigest()


def migrate(root, *, normalize=False):
    root = Path(root).resolve()
    assert root.is_relative_to('/var/backups/filemate') or root == Path('/var/lib/filemate')
    versions, controls = Counter(), Counter()
    count = 0
    for path in sorted(root.rglob('*.db')):
        assert not path.is_symlink()
        with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as conn:
            tables = {r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
            assert conn.execute('PRAGMA integrity_check').fetchall() == [('ok',)]
            control = 'resource_schema_migrations' in tables
            if control:
                before = resource_schema_version(conn)
                assert before in (1, 2, 3)
                excluded = 'resource_schema_migrations'
            else:
                assert 'schema_migrations' in tables, 'Unknown managed database kind'
                before = conn.execute('SELECT MAX(version) FROM schema_migrations').fetchone()[0]
                assert before in (34, 36)
                excluded = 'schema_migrations'
            columns = {t: [row[1] for row in conn.execute(f'PRAGMA table_info("{t}")')] for t in tables if t != excluded}
            signatures = {t: (names, fingerprint(conn, t, names)) for t, names in columns.items()}
        if control:
            BudgetStore(path).initialize()
            with closing(sqlite3.connect(path)) as conn:
                assert resource_schema_version(conn) == 3
                for table, value in signatures.items():
                    assert fingerprint(conn, table, value[0]) == value[1], f'Control rows changed: {table}'
                assert conn.execute('PRAGMA integrity_check').fetchall() == [('ok',)]
                assert not conn.execute('PRAGMA foreign_key_check').fetchall()
                conn.execute('PRAGMA wal_checkpoint(TRUNCATE)')
            controls[before] += 1
            continue
        store = SQLiteStorage(path)
        try:
            store.init_schema()
            assert store.get_schema_version() == 36
            conn = store._conn()
            for table, value in signatures.items():
                assert fingerprint(conn, table, value[0]) == value[1], f'Existing rows changed: {table}'
            assert conn.execute('PRAGMA integrity_check').fetchall()[0][0] == 'ok'
            assert not conn.execute('PRAGMA foreign_key_check').fetchall()
            if normalize:
                with conn:
                    conn.execute('BEGIN IMMEDIATE')
                    normalize_restored_coach(conn)
                    normalize_restored_configuration(conn)
                    normalize_restored_runtime(conn)
                    normalize_restored_assessments(conn)
                    normalize_restored_course_graph(conn)
                assert conn.execute('SELECT COUNT(*) FROM interview_coach_state WHERE external_consent<>0').fetchone()[0] == 0
            conn.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        finally:
            store.close()
        versions[before] += 1
        count += 1
    assert count > 0 and sum(controls.values()) == 1
    return dict(business_databases=count, before=dict(versions), after_schema=36,
                resource_databases=sum(controls.values()), resource_before=dict(controls), resource_after=3,
                all_existing_business_rows_preserved=True, all_existing_control_rows_preserved=True,
                integrity_and_foreign_keys='passed', restore_permissions_revoked=normalize)


if __name__ == '__main__':
    print(json.dumps(migrate(sys.argv[1], normalize='--normalize' in sys.argv)))
