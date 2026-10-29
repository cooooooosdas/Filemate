"""Package the verified tracked source bytes, excluding runtime data and credentials."""

import argparse
import hashlib
import json
import subprocess
import zipfile
from pathlib import Path

from scripts.acceptance.wrongbook_release_evidence import REPORT, check

ROOT = Path(__file__).resolve().parents[2]


def package(destination: Path) -> dict:
    check()
    destination = destination.resolve()
    if not destination.is_relative_to((ROOT / '_working').resolve()) or destination.exists():
        raise ValueError('a new _working archive path is required')
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    paths = subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT).decode('utf-8').split('\0')
    files, excluded = {}, []
    destination.parent.mkdir(parents=True, exist_ok=True)
    forbidden = {'_working', '.git', '.superpowers', '.filemate-data', 'node_modules', '.venv', '__pycache__'}
    with zipfile.ZipFile(destination, 'x', compression=zipfile.ZIP_DEFLATED) as archive:
        for relative in filter(None, paths):
            path = ROOT / relative
            if (forbidden.intersection(Path(relative).parts)
                    or path.suffix.lower() in {'.db', '.sqlite', '.sqlite3', '.pem', '.key', '.p12', '.pfx'}
                    or path.name.endswith(('-wal', '-shm', '-journal'))
                    or path.name.startswith('.env') and not path.name.endswith('.example')):
                excluded.append(relative)
                continue
            if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(ROOT):
                raise ValueError(f'unsupported tracked path: {relative}')
            content = path.read_bytes()
            files[relative] = hashlib.sha256(content).hexdigest()
            archive.writestr('FileMate-Project/' + relative, content)
        report = json.loads(REPORT.read_text(encoding='utf-8'))
        assert all(files.get(name) == expected for name, expected in report['source_hashes'].items())
        manifest = {
            'head': revision, 'status': report['status'], 'source_byte_policy': 'current Git-tracked bytes',
            'pre_existing_test_bytes_preserved': True, 'files_sha256': files, 'excluded': excluded,
        }
        archive.writestr('FileMate-Project/_release/manifest.json',
                         json.dumps(manifest, ensure_ascii=False, indent=2).encode('utf-8'))
    with zipfile.ZipFile(destination) as archive:
        assert archive.testzip() is None
        for relative, expected in files.items():
            assert hashlib.sha256(archive.read('FileMate-Project/' + relative)).hexdigest() == expected
    sha = hashlib.sha256(destination.read_bytes()).hexdigest()
    destination.with_suffix('.zip.sha256').write_text(sha + '  ' + destination.name + '\n', encoding='utf-8')
    result = {'path': str(destination), 'head': revision, 'sha256': sha,
              'files': len(files), 'bytes': destination.stat().st_size, 'excluded': excluded}
    destination.with_suffix('.zip.json').write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    package(args.out)
