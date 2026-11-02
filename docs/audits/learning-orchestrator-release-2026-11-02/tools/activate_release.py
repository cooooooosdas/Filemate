"""Activate only after stopped-write backup, independent restore and schema upgrade rehearsal."""
import json
import os
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import deploy_existing as d
from migrate_data import migrate

incoming = Path(__file__).resolve().parent
metadata = json.loads((incoming / 'manifest.json').read_text())
ID, COMMIT, VERSION = (metadata[k] for k in ('release_id', 'commit', 'version'))
assert re.fullmatch(r'alpha4-[0-9a-f]{12}', ID)
assert incoming == d.BACKEND / 'incoming' / ID
release = d.BACKEND / 'releases' / ID
feature = Path('/etc/systemd/system/filemate-api.service.d/48-learning-release.conf')
staged = json.loads((incoming / 'staged.json').read_text())
assert staged['commit'] == COMMIT and staged['release_id'] == ID
assert not d.MAINTENANCE.exists() and not feature.exists()
assert d.DATA.resolve() == Path('/var/lib/filemate') and not d.DATA.is_symlink()
for line in (release / '.env.production').read_text().splitlines():
    assert line.partition('=')[0].strip() not in {'FILEMATE_ENABLE_WRONGBOOK_V2', 'FILEMATE_ENABLE_LEARNING_ORCHESTRATOR'}
d.check_migration_upgrade(d.BACKEND / 'current/filemate/execution/storage.py', release / 'filemate/execution/storage.py')
backup = d.BACKUPS / (ID + '-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
backup.mkdir(mode=0o700)
old_backend, old_web = os.readlink(d.BACKEND / 'current'), os.readlink(d.WEB / 'current')
for src, name in [(d.CONFIG, 'nginx-before.conf'), (d.DROPIN, 'dropin-before.conf')]:
    assert src.is_file() and not src.is_symlink()
    shutil.copy2(src, backup / name)
    (backup / name).chmod(0o600)
(backup / 'systemd-before.service').write_bytes(subprocess.check_output(['systemctl', 'cat', 'filemate-api']))
(backup / 'systemd-before.service').chmod(0o600)
d.save(backup / 'release-metadata.json', dict(metadata, previous_backend=old_backend, previous_web=old_web))
public_opened = data_changed = False
manifest = None
d.MAINTENANCE.touch(mode=0o644)
try:
    d.run('systemctl', 'stop', 'filemate-api')
    assert subprocess.run(['systemctl', 'is-active', 'filemate-api'], text=True, capture_output=True).stdout.strip() != 'active'
    manifest = d.snapshot(backup / 'data')
    d.save(backup / 'ownership.json', manifest)
    d.restore_drill(backup / 'data', backup / 'restore-drill', manifest)
    drill = migrate(backup / 'restore-drill')
    d.save(backup / 'restore-migration-drill.json', drill)
    data_changed = True
    actual = migrate(d.DATA)
    assert actual['business_databases'] == drill['business_databases']
    d.save(backup / 'actual-migration.json', actual)
    shutil.copy2(release / 'deploy/nginx.filemate.conf', d.CONFIG)
    d.run('docker', 'exec', 'nginx-app', 'nginx', '-t')
    d.DROPIN.write_text('[Service]\nExecStart=\nExecStart=/opt/filemate/venvs/' + ID + '/bin/python /opt/filemate/current/server.py\n')
    feature.write_text('[Service]\nEnvironment=FILEMATE_ENABLE_WRONGBOOK_V2=1\nEnvironment=FILEMATE_ENABLE_LEARNING_ORCHESTRATOR=1\n')
    feature.chmod(0o644)
    d.atomic_link(str(release), d.BACKEND / 'current')
    d.atomic_link('releases/' + ID, d.WEB / 'current')
    d.run('systemctl', 'daemon-reload')
    d.run('systemctl', 'start', 'filemate-api')
    d.health('http://172.18.0.1:8001', VERSION)
    pid = int(subprocess.check_output(['systemctl', 'show', 'filemate-api', '--property=MainPID', '--value'], text=True))
    assert ID.encode() in Path(f'/proc/{pid}/cmdline').read_bytes()
    assert (d.BACKEND / 'current').resolve() == release
    for path in (*d.PREFLIGHT_PATHS, '/api/knowledge-graph/courses'):
        d.probe('http://172.18.0.1:8001', path)
    d.run('docker', 'exec', 'nginx-app', 'nginx', '-s', 'reload')
    d.run('docker', 'exec', 'nginx-app', 'test', '-r', '/data/filemate/current/index.html')
    d.save(backup / 'pre-public-result.json', dict(passed=True, backup_restore_verified=True,
           migration=actual, restore_drill=drill, pid=pid, commit=COMMIT))
    public_opened = True
    d.MAINTENANCE.unlink()
    d.health('https://filemate.asia', VERSION)
    marker, _ = d.probe('https://filemate.asia', '/release.json')
    assert json.loads(marker)['commit'] == COMMIT
    body, headers = d.probe('https://filemate.asia', '/', html=True)
    assert headers.get('Cache-Control') == 'no-store'
    assets = re.findall(r'(?:src|href)="(/assets/[^" ]+)"', body.decode())
    assert assets
    for asset in assets:
        content, h = d.probe('https://filemate.asia', asset)
        assert content and 'immutable' in h.get('Cache-Control', '')
    result = dict(activation='passed', commit=COMMIT, version=VERSION, backup=str(backup),
                  databases_backed_up=len(manifest['databases']),
                  files_backed_up=sum(bool(r['sha256']) for r in manifest['records']),
                  backup_restore_verified=True, migration=actual, pid=pid,
                  rollback_policy='after public writes preserve schema36/governance3 and current data; disable learning/wrongbook flags and use compatible off web')
    d.save(backup / 'result.json', result)
    d.save(incoming / 'activation-result.json', result)
    print(json.dumps(result), flush=True)
except BaseException as error:
    if public_opened:
        d.save(backup / 'post-public-error.json', dict(error_type=type(error).__name__,
               policy='new data retained; no database rollback after public writes'))
        raise
    d.run('systemctl', 'stop', 'filemate-api')
    if data_changed:
        failed = backup / 'failed-upgrade-data'
        assert not failed.exists() and failed.resolve().is_relative_to(d.BACKUPS)
        d.DATA.rename(failed)
        d.restore_drill(backup / 'data', d.DATA, manifest)
    d.atomic_link(old_backend, d.BACKEND / 'current')
    d.atomic_link(old_web, d.WEB / 'current')
    shutil.copy2(backup / 'nginx-before.conf', d.CONFIG)
    shutil.copy2(backup / 'dropin-before.conf', d.DROPIN)
    d.DROPIN.chmod(0o644)
    feature.unlink(missing_ok=True)
    d.run('systemctl', 'daemon-reload')
    d.run('systemctl', 'start', 'filemate-api')
    d.health('http://172.18.0.1:8001', VERSION)
    d.run('docker', 'exec', 'nginx-app', 'nginx', '-t')
    d.run('docker', 'exec', 'nginx-app', 'nginx', '-s', 'reload')
    d.MAINTENANCE.unlink()
    d.save(backup / 'rolled-back.json', dict(error_type=type(error).__name__, data_restored=data_changed))
    raise
