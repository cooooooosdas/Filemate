"""Enforce a hard wall deadline around one private model process."""

import json
import os
import subprocess
import sys
import threading
import time
from dataclasses import asdict
from pathlib import Path

import psutil

MAX_BYTES = 128 * 1024
MEMORY_BYTES = 384 * 1024 * 1024


class BoundedLLMRunner:
    def run(self, config, scope, *, prompt, messages, schema, deadline, cancelled):
        """Send trusted configuration through a pipe; always reap the process we own."""
        if cancelled():
            return {'error_code': 'cancelled'}
        if deadline <= time.monotonic():
            return {'error_code': 'timeout'}
        if len(json.dumps(messages, ensure_ascii=False).encode('utf-8')) > MAX_BYTES:
            return {'error_code': 'invalid_output'}
        payload = json.dumps({'config': asdict(config), 'scope': {'path': str(scope.store.path),
            'policy': asdict(scope.store.policy), 'owner_hash': scope.owner_hash, 'kind': scope.kind,
            'operation': scope.operation, 'trace_id': scope.trace_id,
            'managed_db_path': str(scope.managed_db_path) if scope.managed_db_path else None},
            'prompt': prompt, 'messages': messages, 'schema': schema, 'deadline': deadline}, ensure_ascii=False).encode('utf-8')
        if len(payload) > MAX_BYTES+32*1024:
            return {'error_code': 'invalid_output'}
        env = {key: os.environ[key] for key in ('SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP', 'LANG', 'LC_ALL') if key in os.environ}
        env.update(PYTHONUTF8='1', OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1')
        chunks, overflow = [], threading.Event()
        worker = Path(__file__).with_name('bounded_worker.py')
        try:
            process = subprocess.Popen([sys.executable, '-I', str(worker)], stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=env,
                start_new_session=os.name == 'posix',
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        except OSError:
            return {'error_code': 'provider_unavailable'}

        def write():
            try:
                process.stdin.write(payload)
                process.stdin.close()
            except (OSError, ValueError):
                pass

        def read():
            size = 0
            try:
                while block := process.stdout.read(8192):
                    size += len(block)
                    if size > MAX_BYTES:
                        overflow.set()
                        return
                    chunks.append(block)
            except (OSError, ValueError):
                overflow.set()

        writer, reader = threading.Thread(target=write, daemon=True), threading.Thread(target=read, daemon=True)
        writer.start()
        reader.start()
        try:
            tracked = psutil.Process(process.pid)
            while process.poll() is None:
                if cancelled():
                    return {'error_code': 'cancelled'}
                if time.monotonic() >= deadline:
                    return {'error_code': 'timeout'}
                if overflow.is_set():
                    return {'error_code': 'invalid_output'}
                try:
                    if tracked.memory_info().rss > MEMORY_BYTES:
                        return {'error_code': 'provider_unavailable'}
                except psutil.NoSuchProcess:
                    pass
                time.sleep(0.025)
            reader.join(timeout=1)
            if time.monotonic() >= deadline:
                return {'error_code': 'timeout'}
            if process.returncode != 0 or reader.is_alive() or overflow.is_set():
                return {'error_code': 'provider_unavailable'}
            result = json.loads(b''.join(chunks))
            return result if isinstance(result, dict) else {'error_code': 'invalid_output'}
        except (OSError, ValueError, psutil.Error):
            return {'error_code': 'provider_unavailable'}
        finally:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=5)
            writer.join(timeout=1)
            reader.join(timeout=1)
            process.stdin.close()
            process.stdout.close()
