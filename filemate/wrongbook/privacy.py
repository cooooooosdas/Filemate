"""Bind erasure to all review inputs and invalidate restored execution epochs."""

from uuid import uuid4


def normalize_restored_wrongbook(conn):
    """Never resume an analysis or preserve external authorization after restore."""
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='wrong_review_analyses'").fetchone():
        return
    for row in conn.execute('SELECT analysis_id FROM wrong_review_analyses').fetchall():
        conn.execute("UPDATE wrong_review_analyses SET epoch=?,error_code=CASE WHEN status IN ('running','cancelling') THEN 'backup_restored' ELSE error_code END,status=CASE WHEN status IN ('running','cancelling') THEN 'interrupted' ELSE status END WHERE analysis_id=?", (uuid4().hex, row[0]))
    conn.execute("DELETE FROM data_action_previews WHERE action LIKE 'review_learning_%'")


def source_impact(storage, source_id):
    """Count the union of direct and transitive deletes instead of summing overlaps."""
    conn = storage._conn()
    artifacts = {r[0] for r in conn.execute('''SELECT artifact_id FROM artifacts WHERE source_id=?
        UNION SELECT artifact_id FROM kg_learning_artifact_sources WHERE source_id=?''', (source_id, source_id))}
    analysis_rows = {}
    while True:
        previous = len(artifacts)
        direct = conn.execute('''SELECT * FROM wrong_review_analyses WHERE analysis_id IN
            (SELECT analysis_id FROM wrong_review_analysis_sources WHERE source_id=?)''', (source_id,))
        for row in direct:
            analysis_rows[row['analysis_id']] = dict(row)
        for aid in tuple(artifacts):
            for row in conn.execute('''SELECT * FROM wrong_review_analyses WHERE wrong_id IN
                (SELECT wrong_id FROM wrong_questions WHERE artifact_id=?) OR attempt_id IN
                (SELECT attempt_id FROM quiz_attempts WHERE artifact_id=?)''', (aid, aid)):
                analysis_rows[row['analysis_id']] = dict(row)
        artifacts.update(r['result_artifact_id'] for r in analysis_rows.values() if r['result_artifact_id'])
        if len(artifacts) == previous:
            break
    analyses = [analysis_rows[key] for key in sorted(analysis_rows)]
    # 图谱派生产物也可能是题集，其作答与事件同样会被级联清理。
    counts = {'artifacts': len(artifacts), 'wrong_review_analyses': len(analyses)}
    for table, identity in (('quiz_attempts', 'attempt_id'), ('wrong_questions', 'wrong_id'), ('study_plans', 'plan_id'), ('review_events', 'event_id')):
        affected = set()
        for aid in artifacts:
            affected.update(r[0] for r in conn.execute(f'SELECT {identity} FROM {table} WHERE artifact_id=?', (aid,)))
        if table != 'review_events':
            affected.update(r[0] for r in conn.execute(f'SELECT {identity} FROM {table} WHERE source_id=?', (source_id,)))
        counts[table] = len(affected)
    return {'counts': counts, 'revision': [dict(r) for r in analyses]}
