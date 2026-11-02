"""Validate and freeze local incremental-review acceptance without user data."""

import argparse
import hashlib
import json
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / '_working/wrongbook-incremental-closeout-20261030'
ARCHIVE = ROOT / 'docs/audits/wrong-review-incremental-2026-10-31'


def read_json(path: Path) -> dict:
    """Read one UTF-8 acceptance record."""
    return json.loads(path.read_text(encoding='utf-8-sig'))


def validate() -> dict:
    """Refuse partial, failed or non-synthetic acceptance artifacts."""
    assert (OUT / 'verify-exit.txt').read_text(encoding='utf-8-sig').strip() == '0'
    log = (OUT / 'verify.log').read_text(encoding='utf-8-sig')
    assert '1820 passed, 22 skipped, 5 deselected' in log and 'tests 298' in log
    final = (OUT / 'post-review-frontend.log').read_text(encoding='utf-8-sig')
    assert re.search(r'tests\s+302', final) and re.search(r'fail\s+0', final)
    assert 'built in' in (OUT / 'post-review-build.log').read_text(encoding='utf-8-sig')
    assert (OUT / 'post-review-build-exit.txt').read_text(encoding='utf-8-sig').strip() == '0'
    assert read_json(OUT / 'post-review-bundle.json')['passed']
    assert (OUT / 'enabled-exit.txt').read_text(encoding='utf-8-sig').strip() == '0'
    assert read_json(OUT / 'bundle-enabled.json')['passed']
    totals = {}
    for name, relative, count in [('new_ui', 'browser-3/browser-results.json', 10),
                                  ('learning', 'learning-browser-4/browser-results.json', 11),
                                  ('journey_restore', 'journey-2/results.json', 14)]:
        result = read_json(OUT / relative)
        assert result['synthetic'] and len(result['checks']) == count
        assert all(item['passed'] for item in result['checks'])
        assert not result.get('errors', [])
        totals[name] = count
    assert len(list((OUT / 'browser-3').glob('workspace-*.png'))) == 20
    assert read_json(OUT / 'sqlite326-2/result.json')['passed']
    preserved = read_json(ROOT / '_working/wrongbook-a-20261025/preserved-tests.json')
    assert len(preserved) == 24
    for relative, expected in preserved.items():
        assert hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() == expected, relative
    sources = [p for p in (ROOT / 'filemate/web/src/wrongbook').glob('*.ts')]
    sources += list((ROOT / 'filemate/web/src/components/wrongbook').glob('*'))
    sources += [ROOT / 'filemate/web/src/components/course-graph/CourseWorkspace.vue']
    return {'status': 'CONDITIONAL PASS', 'scope': 'local engineering candidate; not production or human learning effects',
            'synthetic': True, 'backend': {'passed': 1820, 'skipped': 22, 'deselected': 5, 'warnings': 3},
            'full_gate_frontend': 298, 'final_frontend': 302, 'checks': totals,
            'screenshots': 20, 'preserved_test_files': 24,
            'source_sha256': {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                              for p in sources if p.is_file()}}


def freeze() -> dict:
    """Copy an explicit evidence whitelist, never fixtures or credentials."""
    report = validate()
    if ARCHIVE.exists():
        raise ValueError('evidence destination already exists')
    ARCHIVE.mkdir(parents=True)
    names = ['verify.log', 'verify-exit.txt', 'final-frontend.log', 'final-build.log',
             'build-enabled.log', 'bundle-enabled.json', 'enabled-exit.txt',
             'task1-red.log', 'task2-red.log', 'normalized409-red.log', 'graph-navigation-red.log',
             'browser-1/browser-results.json', 'browser-2/browser-results.json',
             'learning-browser/browser-results.json', 'learning-browser-2/browser-results.json',
             'learning-browser-3/browser-results.json', 'journey-2/results.json',
             'sqlite326-2/result.json']
    names += [p.relative_to(OUT).as_posix() for p in (OUT / 'browser-2').glob('workspace-*.png')]
    names += [p.relative_to(OUT).as_posix() for p in (OUT / 'learning-browser-3').glob('learning-*.png')]
    report['evidence_sha256'] = {}
    for name in names:
        source, target = OUT / name, ARCHIVE / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        report['evidence_sha256'][name] = hashlib.sha256(target.read_bytes()).hexdigest()
    (ARCHIVE / 'verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return report


def finalize() -> dict:
    """Append the single review fix evidence while preserving the first freeze."""
    report = validate()
    first_path = ARCHIVE / 'verification.json'
    first_bytes = first_path.read_bytes()
    first = json.loads(first_bytes)
    prior_path = ARCHIVE / 'verification-pre-review.json'
    with prior_path.open('xb') as stream:
        stream.write(first_bytes)
    report['pre_review_verification_sha256'] = hashlib.sha256(first_bytes).hexdigest()
    report['evidence_sha256'] = dict(first['evidence_sha256'])
    for name, expected in report['evidence_sha256'].items():
        assert hashlib.sha256((ARCHIVE / name).read_bytes()).hexdigest() == expected
    names = ['post-review-frontend.log', 'post-review-build.log', 'post-review-build-exit.txt',
             'post-review-bundle.json', 'review-draft-red.log', 'review-summary-red.log',
             'browser-3/browser-results.json', 'learning-browser-4/browser-results.json']
    names += [p.relative_to(OUT).as_posix() for p in (OUT / 'browser-3').glob('workspace-*.png')]
    names += [p.relative_to(OUT).as_posix() for p in (OUT / 'learning-browser-4').glob('learning-*.png')]
    for name in names:
        target = ARCHIVE / name
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('xb') as stream:
            stream.write((OUT / name).read_bytes())
        report['evidence_sha256'][name] = hashlib.sha256(target.read_bytes()).hexdigest()
    for name in ['review.md', 'verification-pre-review.json']:
        report['evidence_sha256'][name] = hashlib.sha256((ARCHIVE / name).read_bytes()).hexdigest()
    report['review'] = {'critical': 0, 'important_found': 1, 'important_fixed': 1, 'minor': 0,
                        'method': 'one independent read-only review, one RED-to-GREEN fix pass; no second review'}
    first_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--freeze', action='store_true')
    parser.add_argument('--finalize', action='store_true')
    args = parser.parse_args()
    if args.freeze and args.finalize:
        parser.error('choose freeze or finalize')
    result = finalize() if args.finalize else freeze() if args.freeze else validate()
    print(json.dumps({k: v for k, v in result.items() if not k.endswith('sha256')}, ensure_ascii=False))
