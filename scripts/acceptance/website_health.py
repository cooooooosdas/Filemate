"""只读抽样网站可用性与响应时间，不上传资料或调用模型。"""

from __future__ import annotations

import argparse
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from statistics import fmean, median

import httpx


def probe(base: str, samples: int = 12) -> dict:
    """在一个独立访客会话中顺序抽样，记录失败和非健康接口状态。"""
    records = []
    checks = []
    version = None
    started = datetime.now(timezone.utc).isoformat()
    with httpx.Client(base_url=base, timeout=20, follow_redirects=True) as client:
        for index in range(samples):
            begin = time.perf_counter()
            try:
                response = client.get("/api/health")
                payload = response.json() if response.status_code == 200 else {}
                version = payload.get("data", {}).get("version", version)
                healthy = response.status_code == 200 and payload.get("success") is True
                records.append({"sample": index + 1, "status": response.status_code,
                                "healthy": healthy,
                                "elapsed_ms": round((time.perf_counter() - begin) * 1000, 2)})
            except (httpx.HTTPError, ValueError) as error:
                records.append({"sample": index + 1, "healthy": False,
                                "error_type": type(error).__name__,
                                "elapsed_ms": round((time.perf_counter() - begin) * 1000, 2)})
        endpoints = ["/", "/api/digital-human/playbacks", "/api/knowledge-graph",
                     "/api/programming/status", "/interview/review/status", "/api/career/status"]
        for endpoint in endpoints:
            begin = time.perf_counter()
            try:
                response = client.get(endpoint)
                check = {"endpoint": endpoint, "status": response.status_code,
                         "content_type": response.headers.get("content-type", ""),
                         "elapsed_ms": round((time.perf_counter() - begin) * 1000, 2)}
                if endpoint == "/" and response.status_code == 200:
                    check["security_headers"] = {key: response.headers.get(key) for key in
                        ["strict-transport-security", "content-security-policy",
                         "x-content-type-options", "x-frame-options"]}
                    assets = re.findall(r'(?:src|href)="([^\"]+\.(?:js|css))"', response.text)
                    check["entry_assets"] = assets
                    for asset in assets[:2]:
                        asset_start = time.perf_counter()
                        fetched = client.get(asset)
                        checks.append({"endpoint": asset, "status": fetched.status_code,
                                       "bytes": len(fetched.content),
                                       "elapsed_ms": round((time.perf_counter() - asset_start) * 1000, 2)})
                if "json" in check["content_type"] and response.status_code == 200:
                    data = response.json().get("data", {})
                    if isinstance(data, dict):
                        check["capability"] = {key: data[key] for key in
                            ["enabled", "ready", "reason", "version", "platform"] if key in data}
                checks.append(check)
            except (httpx.HTTPError, ValueError) as error:
                checks.append({"endpoint": endpoint, "error_type": type(error).__name__})
    timings = sorted(row["elapsed_ms"] for row in records if row["healthy"])
    return {"base_url": base, "started_at": started,
            "finished_at": datetime.now(timezone.utc).isoformat(), "version": version,
            "sample_count": samples, "healthy_count": len(timings),
            "latency_ms": {"mean": round(fmean(timings), 2), "p50": median(timings),
                           "p95_nearest_rank": timings[max(0, (95 * len(timings) + 99) // 100 - 1)],
                           "maximum": max(timings)} if timings else None,
            "samples": records, "checks": checks,
            "notice": "单访客短窗口只读抽样；不代表并发容量、模型生成质量或长期SLA。"}


def main() -> int:
    """保存不含身份Cookie、响应正文或服务器密钥的探测结果。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="https://filemate.asia")
    parser.add_argument("--samples", type=int, default=12, choices=range(1, 31))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = probe(args.base, args.samples)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in ["version", "sample_count", "healthy_count", "latency_ms"]}, ensure_ascii=False))
    homepage = next((row for row in report["checks"] if row["endpoint"] == "/"), {})
    return 0 if report["healthy_count"] == report["sample_count"] and homepage.get("status") == 200 else 1


if __name__ == "__main__":
    raise SystemExit(main())
