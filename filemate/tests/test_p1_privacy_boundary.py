# ruff: noqa: F811
"""存储部署模式与模型/浏览器权限相互独立的公开合同。"""

from fastapi.testclient import TestClient

from filemate.tests.test_accounts import account_server  # noqa: F401
from filemate.tests.test_server_persistence import server_module  # noqa: F401


def test_website_discloses_server_and_browser_credentials_without_secrets(account_server, monkeypatch):
    monkeypatch.setenv('FILEMATE_INTERVIEW_LOCAL_ONLY', '1')
    with TestClient(account_server.app) as client:
        boundary = client.get('/api/privacy/boundary').json()['data']
        assert boundary['storage_location'] == 'server'
        assert '网站服务器' in boundary['storage_notice']
        assert boundary['guest_inactive_days'] == 90
        assert '第三方留存' in boundary['model_notice'] and '不保证' in boundary['speech_notice']
        assert '文字回答' in boundary['camera_notice']
        trust = client.get('/trust/overview').json()['data']
        assert trust['boundaries'] == boundary and trust['mode'] == 'local'
        assert '本机工作区' not in str(trust['guarantees'])
        assert client.get('/api/llm/status').json()['data']['credential_storage'] == 'browser'
        assert client.get('/settings/llm').status_code == 403
        assert not any(key in boundary for key in ('api_key', 'token', 'password', 'data_dir'))


def test_local_device_disclosure_keeps_outbound_model_and_speech_boundaries(server_module):
    module, _storage = server_module
    with TestClient(module.app) as client:
        boundary = client.get('/api/privacy/boundary').json()['data']
        assert boundary['storage_location'] == 'local_machine'
        assert boundary['guest_inactive_days'] is None
        assert '运行 FileMate 服务的设备' in boundary['storage_notice']
        assert '发送给当前配置的模型' in boundary['model_notice']
        assert client.get('/api/llm/status').json()['data']['credential_storage'] == 'system'
        assert client.get('/trust/overview').json()['data']['boundaries'] == boundary
