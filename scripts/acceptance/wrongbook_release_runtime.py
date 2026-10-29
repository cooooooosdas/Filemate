"""Exercise real SQLite 3.26 migrations and restore using synthetic data only."""

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from unittest.mock import patch

from filemate.execution import storage as module
from filemate.execution.storage import SQLiteStorage
from filemate.wrongbook.repository import ReviewRepository

ROOT = Path(__file__).resolve().parents[2]


def run(executable: Path, db: Path, sql: str, *, success: bool = True) -> str:
    """Run a private CLI with bounded UTF-8 input and explicit error checking."""
    result = subprocess.run([str(executable), '-bail', db.name], input=sql,
        cwd=db.parent, encoding='utf-8', capture_output=True, timeout=30, check=False)
    if success and result.returncode:
        raise AssertionError(result.stderr)
    if not success and result.returncode == 0:
        raise AssertionError('fault injection did not fail')
    return result.stdout.strip()


def main():
    """Refuse reused roots and verify every migration/restore assertion."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sqlite', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    out, executable = args.out.resolve(), args.sqlite.resolve()
    if not out.is_relative_to(ROOT/'_working') or out.exists():
        raise ValueError('requires a new project _working directory')
    version = subprocess.check_output([str(executable), '--version'], encoding='utf-8').strip()
    assert version.startswith('3.26.0 '), version
    out.mkdir(parents=True)
    db = out/'legacy34.db'
    old = SQLiteStorage(db)
    with patch.object(module, '_MIGRATIONS', tuple(m for m in module._MIGRATIONS if m[0] <= 34)):
        old.init_schema()
    sid = old.save_source(original_name='原创旧版合成课程', source_path='synthetic.txt', raw_text='栈后进先出。')
    question = {'question_type': 'choice', 'stem': '旧版合成：栈的规则？',
        'options': ['后进先出', '先进先出'], 'answer': 'A', 'analysis': '栈后进先出。'}
    aid = old.save_artifact(source_id=sid, artifact_type='questions', content=[question])
    with old._conn() as conn:
        conn.execute("INSERT INTO quiz_attempts(attempt_id,artifact_id,source_id,question_index,user_answer,is_correct,score) VALUES('legacy-attempt',?,?,0,'B',0,0)", (aid, sid))
        conn.execute("INSERT INTO wrong_questions(wrong_id,artifact_id,source_id,question_index,question,latest_answer) VALUES('legacy-wrong',?,?,0,?,'B')", (aid, sid, json.dumps(question, ensure_ascii=False)))
    old.close()
    rollback = out/'rollback34.db'
    run(executable, db, f".backup '{rollback.name}'\n")
    migrations = [(v, n, sql) for v, n, sql in module._MIGRATIONS if v > 34]
    failing = 'BEGIN IMMEDIATE;\n'+migrations[0][2]+'\nINVALID_SQL;\nCOMMIT;'
    run(executable, rollback, failing, success=False)
    assert run(executable, rollback, 'SELECT MAX(version) FROM schema_migrations;') == '34'
    assert run(executable, rollback, "SELECT user_answer FROM quiz_attempts WHERE attempt_id='legacy-attempt';") == 'B'
    assert run(executable, rollback, "SELECT COUNT(*) FROM pragma_table_info('quiz_attempts') WHERE name='judgement_status';") == '0'
    for version_number, name, sql in migrations:
        safe_name = name.replace("'", "''")
        run(executable, db, f"PRAGMA foreign_keys=ON;\nBEGIN IMMEDIATE;\n{sql}\nINSERT INTO schema_migrations(version,name) VALUES({version_number},'{safe_name}');\nCOMMIT;")
    assert run(executable, db, 'SELECT MAX(version) FROM schema_migrations;') == '36'
    assert run(executable, db, 'PRAGMA foreign_key_check;') == ''
    assert run(executable, db, 'PRAGMA integrity_check;') == 'ok'
    run(executable, db, f"PRAGMA foreign_keys=ON;INSERT INTO quiz_attempts(attempt_id,artifact_id,source_id,question_index,user_answer,is_correct,score,judgement_status) VALUES('pending-attempt','{aid}','{sid}',0,'尚待核对',NULL,NULL,'pending');")
    assert run(executable, db, "SELECT is_correct IS NULL AND score IS NULL FROM quiz_attempts WHERE attempt_id='pending-attempt';") == '1'
    snapshot, restored = out/'snapshot.db', out/'restored.db'
    run(executable, db, f".backup '{snapshot.name}'\n")
    run(executable, restored, f".restore '{snapshot.name}'\n")
    read = SQLiteStorage(restored)
    read.init_schema()
    repo = ReviewRepository(read)
    assert repo.detail('legacy-wrong')['latest_answer'] == 'B'
    assert repo.history('legacy-wrong', kind='attempts')['total'] == 2
    assert read._conn().execute('PRAGMA foreign_key_check').fetchall() == []
    read.close()
    report = {'synthetic': True, 'passed': True, 'engine': version,
        'engine_sha256': hashlib.sha256(executable.read_bytes()).hexdigest(),
        'migrations': [v for v, _, _ in migrations], 'legacy_answer_preserved': True,
        'pending_is_null': True, 'failed_migration_rolled_back': True,
        'foreign_key_check': 'clean', 'integrity_check': 'ok',
        'sqlite326_backup_restore': True, 'current_repository_read_restored_attempts': 2,
        'scope': 'actual SQLite3.26 Windows engine; not production Linux Python/process validation'}
    (out/'result.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()
