"""Pin D acceptance to source bytes and actual saved command results."""
import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT/'_working/wrongbook-d-20261028'
REPORT = ROOT/'docs/audits/wrongbook-2-d-2026-10-28/verification.json'


def source_hashes():
    """Exclude runtime data, build products and dependencies from the source manifest."""
    paths = {ROOT/name for name in ('server.py', 'main.py', 'pyproject.toml', 'uv.lock', '.env.example')}
    for directory, suffixes in [('filemate', {'.py'}), ('scripts', {'.py', '.mjs', '.ps1'})]:
        for parent, dirs, files in (ROOT/directory).walk():
            dirs[:] = [d for d in dirs if d not in {'web', '__pycache__', '.venv', 'node_modules', 'dist'}]
            paths.update(parent/f for f in files if Path(f).suffix in suffixes)
    for directory in ('src', 'tests', 'scripts'):
        paths.update(p for p in (ROOT/'filemate/web'/directory).rglob('*') if p.is_file() and p.suffix in {'.ts', '.vue', '.css', '.mjs'})
    paths.update(ROOT/'filemate/web'/name for name in ('package.json', 'package-lock.json', 'vite.config.ts', 'tsconfig.json', 'tsconfig.app.json', 'tsconfig.node.json', 'index.html'))
    return {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths) if p.is_file()}


def load(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def record():
    """Require real green gate outputs before recording a source manifest."""
    assert (OUT/'full-gate-exit.txt').read_text(encoding='utf-8-sig').strip() == '0', 'full_gate_not_green'
    log = (OUT/'full-gate.log').read_text(encoding='utf-8-sig', errors='replace')
    backend = re.findall(r'(\d+) passed, (\d+) skipped, (\d+) deselected', log)
    assert backend and 'failed,' not in log, 'backend_results_missing'
    browser = load(OUT/'browser-results.json')
    assert browser['synthetic'] and len(browser['checks']) >= 11 and all(c['passed'] for c in browser['checks']) and not browser['errors'], 'browser_not_green'
    budgets = {mode: load(OUT/f'bundle-{mode}.json') for mode in ('enabled', 'disabled')}
    assert all(b['passed'] and b['measurements']['javascript_gzip'] <= 143360 for b in budgets.values()), 'budget_not_green'
    assert all((OUT/f'build-{m}-exit.txt').read_text().strip() == '0' for m in budgets), 'build_not_green'
    outputs = {name: hashlib.sha256((OUT/name).read_bytes()).hexdigest() for name in ('full-gate.log', 'browser-results.json', 'bundle-enabled.json', 'bundle-disabled.json')}
    report = {'stage': 'D', 'status': 'PASS_LOCAL_ENGINEERING', 'recorded_at': datetime.now(timezone.utc).isoformat(),
        'synthetic': True, 'production_deployed': False, 'backend': dict(zip(('passed', 'skipped', 'deselected'), map(int, backend[-1]), strict=True)),
        'browser': browser, 'budgets': budgets, 'evidence_sha256': outputs, 'source_hashes': source_hashes(),
        'not_executed': ['生产SQLite3.26迁移及恢复', '生产容量与部署', '真实外部模型质量评估', '真人学习效果实验']}
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(f'Recorded {len(report["source_hashes"])} source hashes and {len(browser["checks"])} browser groups.')


def check():
    """Reject old results when a relevant source file changes."""
    report = load(REPORT)
    assert report['status'] == 'PASS_LOCAL_ENGINEERING' and report['source_hashes'] == source_hashes(), 'source_changed_rerun_affected_gates'
    assert all(c['passed'] for c in report['browser']['checks']) and not report['browser']['errors']
    for name, value in report['evidence_sha256'].items():
        assert hashlib.sha256((OUT/name).read_bytes()).hexdigest() == value, f'evidence_changed:{name}'
    print('Recorded D evidence matches current source bytes.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--record', action='store_true')
    args = parser.parse_args()
    record() if args.record else check()
