"""Private fixed entry point; never accept an executable or business database operation."""

import json
import sys
import time
from pathlib import Path

# -I隔离环境后仅加入仓库自身，避免继承调用者的PYTHONPATH。
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def execute(payload):
    from filemate.llm_client import LLMClient, LLMConfig
    from filemate.llm_client.exceptions import (
        LLMAPIError,
        LLMConfigError,
        LLMRateLimitError,
        LLMTimeoutError,
    )
    from filemate.runtime_governance import (
        CURRENT_SCOPE,
        BudgetExceeded,
        BudgetStore,
        Limits,
        Policy,
        ResourceLimits,
        Scope,
    )

    raw_scope = payload['scope']
    raw_policy = raw_scope['policy']
    policy = Policy(**{k: (ResourceLimits(**v) if k.startswith('resources_') else Limits(**v))
        if isinstance(v, dict) else v for k, v in raw_policy.items()})
    store = BudgetStore(Path(raw_scope['path']), policy)
    scope = Scope(store, raw_scope['owner_hash'], raw_scope['kind'], raw_scope['operation'], raw_scope['trace_id'],
        Path(raw_scope['managed_db_path']) if raw_scope['managed_db_path'] else None)
    token = CURRENT_SCOPE.set(scope)
    try:
        remaining = min(20, payload['deadline']-time.monotonic())
        if remaining <= 0:
            return {'error_code': 'timeout'}
        client = LLMClient(LLMConfig(**payload['config']))
        try:
            output = client.call_structured(prompt=payload['prompt'], messages=payload['messages'], schema=payload['schema'],
                timeout=remaining, retry=1, max_tokens=3500)
        except LLMAPIError as exc:
            if isinstance(exc.__cause__, LLMRateLimitError):
                return {'error_code': 'quota_exceeded'}
            if isinstance(exc.__cause__, LLMTimeoutError):
                return {'error_code': 'timeout'}
            # 原适配层对结构坏输出使用固定公开文字，禁止回传供应商正文。
            if '模型返回内容' in str(exc):
                return {'error_code': 'invalid_output'}
            raise
        return {'output': output, 'usage': client.get_usage() or None}
    except (BudgetExceeded, LLMRateLimitError):
        return {'error_code': 'quota_exceeded'}
    except LLMTimeoutError:
        return {'error_code': 'timeout'}
    except LLMConfigError:
        return {'error_code': 'credentials_missing'}
    except LLMAPIError:
        return {'error_code': 'provider_unavailable'}
    finally:
        CURRENT_SCOPE.reset(token)


def main():
    try:
        raw = sys.stdin.buffer.read(160*1024+1)
        if len(raw) > 160*1024:
            raise ValueError('input_size')
        result = execute(json.loads(raw))
        output = json.dumps(result, ensure_ascii=False, allow_nan=False).encode('utf-8')
        if len(output) > 128*1024:
            output = b'{"error_code":"invalid_output"}'
    except Exception:  # noqa: BLE001 -- 固定进程出口不能回传包含凭据的异常正文。
        output = b'{"error_code":"provider_unavailable"}'
    sys.stdout.buffer.write(output)
    sys.stdout.buffer.flush()


if __name__ == '__main__':
    main()
