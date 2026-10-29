"""Archive release evidence without turning a known capacity failure into a pass."""

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path

from scripts.acceptance.wrongbook_learning_evidence import source_hashes

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / '_working/wrongbook-e-20261029'
ARCHIVE = ROOT / 'docs/audits/wrongbook-2-e-2026-10-29'
REPORT = ARCHIVE / 'verification.json'
INPUTS = {
    'workspace': 'workspace-complete/browser-results.json',
    'learning': 'learning-final/browser-results.json',
    'journey': 'journey-final/results.json',
    'sqlite326': 'runtime-326-relative/result.json',
    'performance': 'performance-final.json',
    'performance_before_cache': 'performance-idle.json',
    'budget_on': 'budget-on.json',
    'budget_off': 'budget-off.json',
    'search_before': 'search-trace.json',
    'search_after': 'search-trace-fixed.json',
    'gate': 'final-gate.log',
    'gate_exit': 'final-gate-exit.txt',
    'empty_filter': 'empty-filter.json',
    'empty_red_unit': 'empty-state-red.log',
    'empty_green_unit': 'empty-state-green.log',
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(name: str) -> dict:
    return json.loads((OUT / INPUTS[name]).read_text(encoding='utf-8-sig'))


def record() -> None:
    assert (OUT / INPUTS['gate_exit']).read_text().strip() == '0'
    gate = (OUT / INPUTS['gate']).read_text(encoding='utf-8', errors='replace')
    backend = re.search(r'(\d+) passed, (\d+) skipped, (\d+) deselected', gate)
    frontend = re.search(r'ℹ tests (\d+).*?ℹ pass (\d+).*?ℹ fail (\d+)', gate, re.DOTALL)
    assert backend and int(backend[1]) >= 1720 and frontend and frontend[1] == frontend[2]
    assert frontend[3] == '0' and int(frontend[1]) >= 277
    browser_counts = {}
    for name, expected in [('workspace', 21), ('learning', 11), ('journey', 14)]:
        result = read_json(name)
        assert result['synthetic'] and len(result['checks']) == expected
        assert all(item['passed'] for item in result['checks'])
        assert not result.get('errors')
        browser_counts[name] = expected
    compatibility = read_json('sqlite326')
    assert compatibility['passed'] and compatibility['engine'].startswith('3.26.0')
    assert compatibility['failed_migration_rolled_back'] and compatibility['sqlite326_backup_restore']
    assert read_json('empty_filter')['passed']
    budgets = {}
    for name in ('budget_on', 'budget_off'):
        data = read_json(name)
        assert data['passed'] and data['budget']['javascript_gzip'] == 143360
        budgets[name] = data['measurements']
    performance = read_json('performance')
    assert performance['target_p95_ms'] == 500 and len(performance['rows']) == 8
    assert sorted((r['count'], r['search']) for r in performance['rows']) == [
        (count, search) for count in (0, 100, 1000, 10000) for search in (False, True)]
    assert all(row['warm_meets_500ms_p95'] for row in performance['rows'])
    failures = [row for row in performance['rows'] if not row['concurrent_4_meets_500ms_p95']]
    assert failures, 'Do not silently erase the measured capacity issue; rerun and document a fix.'
    hashes = source_hashes()
    ARCHIVE.mkdir(parents=True, exist_ok=True)
    evidence = {}
    for name, relative in INPUTS.items():
        source = OUT / relative
        destination = ARCHIVE / (name + Path(relative).suffix)
        destination.write_bytes(source.read_bytes())
        evidence[destination.name] = digest(destination)
    preserved = json.loads((ROOT / '_working/wrongbook-a-20261025/preserved-tests.json').read_text(encoding='utf-8'))
    for name, expected in preserved.items():
        assert digest(ROOT / name) == expected, f'pre-existing user file changed: {name}'
    report = {
        'status': 'CONDITIONAL_PASS_LOCAL_ENGINEERING',
        'functional_scenarios': '10/10', 'browser_and_recovery_groups': browser_counts,
        'backend': {'passed': int(backend[1]), 'skipped': int(backend[2]), 'deselected_e2e': int(backend[3])},
        'frontend_passed': int(frontend[1]), 'bundle_measurements': budgets,
        'known_issues': [{
            'id': 'E-P2-01', 'severity': 'P2',
            'description': '10000 rows: four concurrent requests exceed the unchanged 500ms p95 reference.',
            'measurements': failures, 'status': 'open; not a passing performance result',
        }],
        'unexecuted': [
            'Production Linux Python/process runtime with SQLite3.26 and real deployment capacity',
            'Real external model answer quality and real student learning outcomes',
            'OS disk cache eviction and an independent physical mobile-device run',
        ],
        'pre_existing_tests_preserved': preserved,
        'source_revision_before_documentation': subprocess.check_output(
            ['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        'source_hashes': hashes, 'evidence_sha256': evidence,
    }
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'Archived {len(hashes)} source hashes; functional checks passed; capacity remains CONDITIONAL.')


def check() -> None:
    report = json.loads(REPORT.read_text(encoding='utf-8'))
    assert report['status'] == 'CONDITIONAL_PASS_LOCAL_ENGINEERING'
    assert report['source_hashes'] == source_hashes(), 'source changed: rerun affected verification'
    for name, expected in report['evidence_sha256'].items():
        assert digest(ARCHIVE / name) == expected, f'archived evidence changed: {name}'
    assert report['known_issues'][0]['id'] == 'E-P2-01'
    assert report['known_issues'][0]['status'].startswith('open')
    print('Audit archive consistent; this does not mean the open concurrency target passed.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--record', action='store_true')
    options = parser.parse_args()
    if options.record:
        record()
    else:
        check()
