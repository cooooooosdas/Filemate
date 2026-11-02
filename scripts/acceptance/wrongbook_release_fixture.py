"""Create original four-scale fixtures in the product's managed backup layout."""

import argparse
import json
import os
from pathlib import Path

from filemate.execution.storage import SQLiteStorage
from scripts.acceptance.wrongbook_workspace_fixture import prepare, seed_course

ROOT = Path(__file__).resolve().parents[2]


def prepare_managed(root: Path, password: str) -> dict:
    root = root.resolve()
    if not root.is_relative_to((ROOT / '_working').resolve()) or root.exists():
        raise ValueError('a new project _working root is required')
    manifest = prepare(root, password)
    (root / 'accounts.db').rename(root / 'filemate.db')
    for user in manifest['users']:
        store = SQLiteStorage(root / 'users' / user['workspace'] / 'filemate.db')
        try:
            for source in store._conn().execute('SELECT source_id,raw_text FROM sources').fetchall():
                path = root / 'users' / user['workspace'] / 'inbox' / (source['source_id'] + '.txt')
                path.parent.mkdir(exist_ok=True)
                with path.open('x', encoding='utf-8') as stream:
                    stream.write(source['raw_text'] or '原创合成资料')
                with store._conn() as connection:
                    connection.execute('UPDATE sources SET source_path=? WHERE source_id=?',
                                       (str(path), source['source_id']))
            if not user['wrong_count']:
                user.update(seed_course(store, user['source_id'], user['artifact_id']))
        finally:
            store.close()
    manifest['database_path'] = str(root / 'filemate.db')
    (root / 'manifest.json').write_text(json.dumps(
        manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-root', type=Path, required=True)
    options = parser.parse_args()
    result = prepare_managed(options.data_root, os.environ['FILEMATE_AUDIT_PASSWORD'])
    print(json.dumps({'synthetic': True, 'counts': [u['wrong_count'] for u in result['users']]}))
