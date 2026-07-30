"""SQLite 线程安全压测：10 线程 × 100 次并发写入。

用法: python -m filemate.tests.stress_test_storage
"""

import threading
import time
import uuid
from pathlib import Path
from filemate.execution.storage import SQLiteStorage


def _worker(storage: SQLiteStorage, worker_id: int, iterations: int, results: list):
    """单个线程：创建 session + 更新 + 记录哈希 + 写操作日志。"""
    errors = []
    for i in range(iterations):
        try:
            sid = f"stress-w{worker_id}-i{i}-{uuid.uuid4().hex[:6]}"
            # 1. create session
            storage.create_session(sid, f"/fake/worker{worker_id}/file{i}.pdf")

            # 2. update session
            storage.update_session(sid, category="课件", confidence=0.85 + (i % 10) * 0.01)

            # 3. record hash
            storage.record_hash(f"hash-w{worker_id}-{i}", sid)

            # 4. log operation
            storage.log_operation(sid, "classify", f"worker{worker_id} iter{i}")

            # 5. read back and verify
            row = storage.get_session(sid)
            if row is None:
                errors.append(f"[w{worker_id} i{i}] get_session returned None")
            elif row["category"] != "课件":
                errors.append(f"[w{worker_id} i{i}] category mismatch: {row['category']}")

        except Exception as exc:
            errors.append(f"[w{worker_id} i{i}] {type(exc).__name__}: {exc}")

    results.append((worker_id, errors))


def main():
    db_path = Path(__file__).resolve().parent / "stress_test.db"
    storage = SQLiteStorage(db_path)
    storage.init_schema()

    WORKERS = 10
    ITERATIONS = 100

    results: list = []
    threads: list[threading.Thread] = []

    t0 = time.perf_counter()

    for w in range(WORKERS):
        t = threading.Thread(target=_worker, args=(storage, w, ITERATIONS, results))
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    elapsed = time.perf_counter() - t0

    # ── 汇总 ──
    total_errors = 0
    for worker_id, errors in results:
        if errors:
            print(f"Worker {worker_id}: {len(errors)} errors")
            for e in errors[:5]:
                print(f"  {e}")
            if len(errors) > 5:
                print(f"  ... and {len(errors) - 5} more")
            total_errors += len(errors)

    total_operations = WORKERS * ITERATIONS * 5  # 5 种操作 × 每个线程每次

    print()
    print(f"线程数: {WORKERS}")
    print(f"每线程操作: {ITERATIONS} 次（各含 5 种操作）")
    print(f"总操作量: {total_operations}")
    print(f"耗时: {elapsed:.2f}s")
    print(f"错误数: {total_errors}")
    print(f"吞吐: {total_operations / elapsed:.0f} ops/s")

    if total_errors == 0:
        print("\n[PASS] Thread-safety stress test passed - 0 errors")
    else:
        print(f"\n[FAIL] Stress test failed - {total_errors} errors")

    # 验证数据库内容完整性
    all_sessions = storage.list_sessions()
    expected = WORKERS * ITERATIONS
    print(f"数据库 session 数: {len(all_sessions)}（预期 ≥ {expected}）")

    # 清理
    storage.close()
    db_path.unlink(missing_ok=True)

    return total_errors == 0


if __name__ == "__main__":
    ok = main()
    raise SystemExit(0 if ok else 1)
