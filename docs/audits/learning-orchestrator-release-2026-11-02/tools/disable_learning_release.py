"""Disable new learning UI and APIs without reverting databases or later user writes."""
import argparse
import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import deploy_existing as d

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--confirm-release', required=True)
args = parser.parse_args()
incoming = Path(__file__).resolve().parent
m = json.loads((incoming/'manifest.json').read_text())
rid = m['release_id']
assert args.confirm_release == rid
assert incoming == d.BACKEND/'incoming'/rid
assert (d.BACKEND/'current').resolve() == d.BACKEND/'releases'/rid
assert json.loads((incoming/'activation-result.json').read_text())['activation']=='passed'
assert not d.MAINTENANCE.exists()
off = d.WEB/'releases'/(rid+'-off')
assert off.is_dir() and (off/'index.html').is_file()
feature = Path('/etc/systemd/system/filemate-api.service.d/48-learning-release.conf')
assert feature.is_file() and not feature.is_symlink()
old_web = os.readlink(d.WEB/'current')
old_flags = feature.read_text()
receipt = d.BACKUPS/(rid+'-disable-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
receipt.mkdir(mode=0o700)
shutil.copy2(feature, receipt/'features-before.conf')
d.MAINTENANCE.touch(mode=0o644)
try:
    feature.write_text('[Service]\nEnvironment=FILEMATE_ENABLE_WRONGBOOK_V2=0\nEnvironment=FILEMATE_ENABLE_LEARNING_ORCHESTRATOR=0\n')
    d.atomic_link('releases/'+rid+'-off',d.WEB/'current')
    d.run('systemctl','daemon-reload')
    d.run('systemctl','restart','filemate-api')
    d.health('http://172.18.0.1:8001',m['version'])
    for path, field in [('/wrongbook/v2/capabilities','write_enabled'),('/api/learning/orchestrator/capabilities','enabled')]:
        body,_=d.probe('http://172.18.0.1:8001',path)
        assert json.loads(body)['data'][field] is False
    marker=json.loads((off/'release.json').read_text())
    marker.update(status='COMPATIBILITY_ROLLBACK',deployment_performed=True,release_kind='live')
    (off/'release.json').write_text(json.dumps(marker,ensure_ascii=False,indent=2))
    (off/'release.json').chmod(0o644)
    d.MAINTENANCE.unlink()
    d.save(receipt/'result.json',dict(passed=True,backend_retained=rid,web=str(off),databases_restored=False,
             user_writes_preserved=True,learning_orchestrator=False,wrongbook_v2=False))
    print(json.dumps(dict(passed=True,receipt=str(receipt),database_restored=False)))
except BaseException:
    feature.write_text(old_flags)
    d.atomic_link(old_web,d.WEB/'current')
    d.run('systemctl','daemon-reload')
    d.run('systemctl','restart','filemate-api')
    d.health('http://172.18.0.1:8001',m['version'])
    d.MAINTENANCE.unlink()
    raise
