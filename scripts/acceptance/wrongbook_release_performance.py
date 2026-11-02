"""Measure authenticated first requests, warm requests and four concurrent clients."""

import argparse
import asyncio
import json
import math
import os
import time
from pathlib import Path

import httpx


async def measure(base: str, origin: str, manifest: Path, output: Path) -> dict:
    if not base.startswith('http://127.0.0.1:'):
        raise ValueError('loopback only')
    fixture = json.loads(manifest.read_text(encoding='utf-8'))
    assert fixture['synthetic'] and not output.exists()
    rows = []
    for user in sorted(fixture['users'],
                       key=lambda u: u['wrong_count']):
        async with httpx.AsyncClient(base_url=base, timeout=30) as client:
            response = await client.post('/api/auth/login',
                                        headers={'Origin': origin, 'X-FileMate-Action': 'account'},
                                        json={'email': user['email'],
                                              'password': os.environ['FILEMATE_AUDIT_PASSWORD'],
                                              'remember': False})
            assert response.status_code == 200

            async def query(search, subject=user, session=client):
                params = {'limit': 30}
                if search:
                    params['q'] = '合成复盘' + str(subject['wrong_count']).zfill(5)
                start = time.perf_counter()
                response = await session.get('/wrongbook/v2/page', params=params)
                assert response.status_code == 200
                data = response.json()['data']
                assert len(data['items']) <= 30
                assert data['total'] == (int(bool(subject['wrong_count'])) if search else subject['wrong_count'])
                return (time.perf_counter() - start) * 1000

            for search in (False, True):
                first = await query(search)
                warm = [await query(search) for _ in range(20)]
                parallel = []
                for _ in range(5):
                    parallel.extend(await asyncio.gather(*(query(search) for _ in range(4))))

                def distribution(samples):
                    samples = sorted(samples)
                    return {'samples': len(samples), 'p50_ms': round(samples[len(samples) // 2], 2),
                            'p95_ms': round(samples[math.ceil(len(samples) * .95) - 1], 2)}
                row = {'count': user['wrong_count'], 'search': search,
                       'process_first_ms': round(first, 2),
                       'warm': distribution(warm), 'concurrent_4': distribution(parallel)}
                row['warm_meets_500ms_p95'] = row['warm']['p95_ms'] <= 500
                row['concurrent_4_meets_500ms_p95'] = row['concurrent_4']['p95_ms'] <= 500
                rows.append(row)
    report = {'synthetic': True, 'target_p95_ms': 500,
              'first_request_definition': 'fresh API process and first query per workspace/mode; OS cache not flushed',
              'rows': rows}
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', required=True)
    parser.add_argument('--origin', required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    report = asyncio.run(measure(args.base, args.origin, args.manifest, args.out))
    print(json.dumps(report))
    if not all(r['warm_meets_500ms_p95'] and r['concurrent_4_meets_500ms_p95']
               for r in report['rows']):
        raise SystemExit(1)
