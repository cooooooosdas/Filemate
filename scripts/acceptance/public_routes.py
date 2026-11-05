"""在自有回环网关验证真实公开路由、静态资源和 API 边界。"""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    """使用新证据目录和自有 Caddy 进程执行 HTTP 合同。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--caddy', type=Path, required=True)
    parser.add_argument('--dist', type=Path, required=True)
    parser.add_argument('--api', required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if not args.api.startswith('http://127.0.0.1:'):
        raise ValueError('只允许自有回环测试 API')
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        port = probe.getsockname()[1]
    base = f'http://127.0.0.1:{port}'
    source = (ROOT / 'deploy/Caddyfile').read_text(encoding='utf-8')
    source = source.replace('admin off', 'admin off\n\tpersist_config off\n'
                            f'\tstorage file_system {{\n\t\troot "{out.as_posix()}/storage"\n\t}}')
    source = source.replace('{$FILEMATE_DOMAIN} {', f'{base} {{\n\tbind 127.0.0.1')
    source = source.replace('api:8001', args.api.removeprefix('http://'))
    source = source.replace('root * /srv', f'root * "{args.dist.resolve().as_posix()}"')
    config = out / 'Caddyfile'
    config.write_text(source, encoding='utf-8')
    env = os.environ.copy()
    hashed = subprocess.check_output(
        [str(args.caddy), 'hash-password', '--plaintext', 'synthetic-route-test'],
        text=True, encoding='utf-8',
    ).strip()
    env.update(FILEMATE_BASIC_USER='synthetic', FILEMATE_BASIC_PASSWORD_HASH=hashed)
    results = []
    with (out / 'gateway.log').open('w', encoding='utf-8') as log:
        process = subprocess.Popen(
            [str(args.caddy), 'run', '--config', str(config), '--adapter', 'caddyfile'],
            env=env, stdout=log, stderr=subprocess.STDOUT,
        )
        try:
            with httpx.Client(base_url=base, auth=('synthetic', 'synthetic-route-test'),
                              trust_env=False, timeout=10) as client:
                for _ in range(60):
                    try:
                        client.get('/')
                        break
                    except httpx.ConnectError:
                        if process.poll() is not None:
                            raise RuntimeError('网关启动失败，请检查 gateway.log')
                        time.sleep(0.1)
                cases = [(path, 'text/html', 404, 'text/html') for path in
                         ('/abc', '/foo/bar', '/foo/bar?q=one', '/assets/missing.js')]
                cases += [(path, 'text/html', 200, 'text/html') for path in
                          ('/', '/login', '/register', '/trust', '/today', '/knowledge-graph')]
                cases += [('/robots.txt', '*/*', 200, 'text/plain'),
                          ('/sitemap.xml', '*/*', 200, 'application/xml'),
                          ('/api/health', 'text/html', 200, 'application/json'),
                          ('/knowledge/sources?limit=1', 'application/json', 200, 'application/json'),
                          ('/knowledge/missing-api', 'application/json', 404, 'application/json')]
                for path, accept, status, mime in cases:
                    response = client.get(path, headers={'Accept': accept})
                    passed = (response.status_code == status
                              and mime in response.headers.get('content-type', '')
                              and response.headers.get('x-content-type-options') == 'nosniff')
                    results.append({'path': path, 'accept': accept, 'status': response.status_code,
                                    'mime': response.headers.get('content-type'), 'passed': passed})
        finally:
            process.terminate()
            process.wait(timeout=10)
    report = {'synthetic': True, 'api': args.api, 'gateway': base, 'checks': results,
              'passed': all(row['passed'] for row in results)}
    (out / 'result.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
