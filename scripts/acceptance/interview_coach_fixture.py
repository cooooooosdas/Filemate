"""Loopback-only synthetic interview fixture; never use a production directory."""
import json
import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit

root = Path(__file__).resolve().parents[2]
if not os.environ.get('FILEMATE_FIXTURE_DIR'):
    raise SystemExit('FILEMATE_FIXTURE_DIR must explicitly name a synthetic _working directory')
evidence = Path(os.environ['FILEMATE_FIXTURE_DIR']).resolve()
if '_working' not in evidence.parts:
    raise SystemExit('fixture directory must be inside _working')
marker = evidence / '.synthetic-interview-coach'
if evidence.exists() and any(evidence.iterdir()) and not marker.exists():
    raise SystemExit('nonempty unmarked directory refused')
evidence.mkdir(parents=True, exist_ok=True)
marker.touch(exist_ok=True)
web = urlsplit(os.environ.get('FILEMATE_WEB_URL', 'http://127.0.0.1:5187'))
api = urlsplit(os.environ.get('FILEMATE_API_URL', 'http://127.0.0.1:8037'))
if any(url.hostname not in {'localhost','127.0.0.1','::1'} or url.scheme != 'http' for url in (web,api)):
    raise SystemExit('only loopback HTTP fixture addresses are allowed')
sys.path.insert(0, str(root))
os.environ.update(FILEMATE_DATA_DIR=str(evidence/'data'), FILEMATE_DB_PATH=str(evidence/'data/main.db'), FILEMATE_UPLOAD_DIR=str(evidence/'data/inbox'), FILEMATE_ARCHIVE_DIR=str(evidence/'data/archive'), FILEMATE_IDENTITY_SECRET='synthetic-local-acceptance-only-000000000', FILEMATE_ENV='development', FILEMATE_IDENTITY_MODE='local', FILEMATE_ENABLE_INTERVIEW_COACH='1', FILEMATE_ENABLE_INTERVIEW_REVIEW='1', FILEMATE_CORS_ORIGINS=web.geturl(), FILEMATE_INTERVIEW_LOCAL_ONLY='0')
os.environ.pop('OPENAI_API_KEY', None)
os.environ.pop('DEEPSEEK_API_KEY', None)
import server
from filemate.llm_client.exceptions import LLMRateLimitError, LLMTimeoutError
from filemate.runtime_governance import BudgetExceeded, GovernanceUnavailable
from filemate.tests.test_interview_coach_analysis import payload

control = evidence/'control.json'
if not control.exists():
    control.write_text('{"mode":"success","delay":0}', encoding='utf-8')

class SyntheticProvider:
    config = SimpleNamespace(provider='synthetic_acceptance',base_url='https://example.invalid',model='fixture-only')
    def call(self, **kwargs):
        cfg=json.loads(control.read_text(encoding='utf-8'))
        with (evidence/'calls.jsonl').open('a', encoding='utf-8') as f:
            f.write(json.dumps({'mode':cfg['mode'],'time':time.time()})+'\n')
        time.sleep(min(4,float(cfg.get('delay',0))))
        if cfg['mode']=='timeout': raise LLMTimeoutError('synthetic timeout')
        if cfg['mode']=='429': raise LLMRateLimitError('synthetic limit')
        if cfg['mode']=='budget': raise BudgetExceeded('synthetic limit')
        if cfg['mode']=='503': raise GovernanceUnavailable('synthetic governance failure')
        if cfg['mode']=='badjson': return 'invalid synthetic json'
        result=payload();result['feedback']=cfg.get('feedback',result['feedback'])
        return json.dumps(result,ensure_ascii=False)

server._coach_llm = SyntheticProvider
@server.app.middleware('http')
async def fixture_flags(request, call_next):
    cfg=json.loads(control.read_text(encoding='utf-8'))
    os.environ['FILEMATE_ENABLE_INTERVIEW_COACH']=str(cfg.get('coach',1))
    os.environ['FILEMATE_ENABLE_INTERVIEW_REVIEW']=str(cfg.get('review',1))
    return await call_next(request)
conn = server._local_storage._conn()
conn.execute("CREATE TRIGGER IF NOT EXISTS synthetic_coach_write_failure BEFORE INSERT ON interview_answer_attempts WHEN NEW.answer LIKE '[DB_FAILURE]%' BEGIN SELECT RAISE(ABORT,'synthetic write failure'); END")
conn.commit()
# Serve the default-off production build in this fixture, as nginx would.
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

dist=root/'filemate/web/dist'
server.app.mount('/assets',StaticFiles(directory=dist/'assets'),name='synthetic-build-assets')
@server.app.get('/interview')
def legacy_build():
    return FileResponse(dist/'index.html')
if __name__ == '__main__':
    import uvicorn
    uvicorn.run(server.app,host='127.0.0.1',port=api.port or 8037,log_level='warning')
