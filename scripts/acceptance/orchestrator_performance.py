"""Cold/warm and four-concurrent scoped decision reads on original synthetic data."""

import argparse
import json
import math
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from itertools import pairwise

from filemate.study.orchestrator.models import ScheduleOptions, utc_now
from filemate.study.orchestrator.scheduler import build_schedule
from filemate.study.orchestrator.snapshot import SnapshotReader
from filemate.study.orchestrator.task_views import project_tasks

from .orchestrator_runtime import output_path, seed, write_json


def stats(values):
    ordered = sorted(values)
    return {'p50_ms': ordered[math.ceil(len(ordered) * .5) - 1],
            'p95_ms': ordered[math.ceil(len(ordered) * .95) - 1], 'max_ms': max(ordered), 'samples': len(values)}


def benchmark(root, count, *, distinct_dates=False):
    store, scope = seed(root, count=count)
    if distinct_dates:
        start = datetime(2020, 1, 1, tzinfo=timezone.utc)
        store._conn().executemany('UPDATE wrong_questions SET next_review_at=? WHERE wrong_id=?',
            [((start + timedelta(seconds=i + group * count)).isoformat(), f'synthetic-{group}-{i:06}')
             for group in (0, 1) for i in range(count)])
        store._conn().commit()
    def run(_=0):
        start = time.perf_counter()
        marks = [start]
        sql = []
        with store.read_snapshot() as read:
            marks.append(time.perf_counter())
            read._conn().set_trace_callback(sql.append)
            snap = SnapshotReader(store).read_in_transaction(read, scope, as_of=utc_now())
            marks.append(time.perf_counter())
            projection = project_tasks(snap)
            marks.append(time.perf_counter())
            schedule = build_schedule(snap, projection, ScheduleOptions(available_minutes=60))
            marks.append(time.perf_counter())
            size = len(json.dumps({'snapshot': snap.model_dump(mode='json'), 'projection': projection.model_dump(mode='json')}, ensure_ascii=False).encode())
            marks.append(time.perf_counter())
        marks.append(time.perf_counter())
        if snap.coverage['reviews']['total'] != count or len(projection.tasks) > 200 or len(schedule.selected) > 20:
            raise AssertionError('capacity_contract_failed')
        return (time.perf_counter() - start) * 1000, size, len(sql), [(b-a)*1000 for a,b in pairwise(marks)]
    try:
        cold = run()
        warm = [run() for _ in range(10)]
        with ThreadPoolExecutor(max_workers=4) as pool:
            concurrent = list(pool.map(run, range(16)))
        maximum_size = max(row[1] for row in [cold, *warm, *concurrent])
        a, b = stats([r[0] for r in warm]), stats([r[0] for r in concurrent])
        return {'scope_wrong_count': count, 'foreign_wrong_count': count,
                'distinct_due_times_per_scope': count if distinct_dates else 1, 'cold_ms': cold[0], 'warm': a,
                'stage_max_ms': dict(zip(('open','snapshot','projection','schedule','serialize','close'),
                    (max(r[3][i] for r in warm+concurrent) for i in range(6)))),
                'four_concurrent': b, 'max_response_bytes': maximum_size, 'max_sql_statements': max(r[2] for r in warm + concurrent),
                'status': 'PASS' if a['p95_ms'] <= 500 and b['p95_ms'] <= 500 and maximum_size <= 524288 else 'P2'}
    finally:
        store.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True)
    parser.add_argument('--distinct-dates', action='store_true')
    args = parser.parse_args(argv)
    root = output_path(args.out)
    root.mkdir(parents=True)
    results = [benchmark(root / str(n), n, distinct_dates=args.distinct_dates) for n in (100, 1000, 10000)]
    report = {'synthetic': True, 'results': results, 'status': 'PASS' if all(r['status'] == 'PASS' for r in results) else 'P2'}
    write_json(root / 'result.json', report)
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
