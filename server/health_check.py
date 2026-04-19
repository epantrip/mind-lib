#!/usr/bin/env python3
"""
健康检查脚本 — 用于 Docker/K8s liveness/readiness 探针
用法:
    python health_check.py [--url http://localhost:5000] [--timeout 5]
退出码:
    0 = 健康
    1 = 不健康（服务异常或网络错误）
"""
import os
import sys
import argparse
import urllib.request
import urllib.error
import json


def check_health(url: str, timeout: int) -> bool:
    """检查服务健康状态"""
    try:
        req = urllib.request.Request(
            f"{url}/api/health",
            headers={"Content-Type": "application/json"},
            method="GET"
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode())
                if data.get("status") == "ok":
                    return True
    except (urllib.error.URLError, urllib.error.HTTPError,
            json.JSONDecodeError, TimeoutError):
        pass
    return False


def main():
    parser = argparse.ArgumentParser(description="Mind Library 健康检查")
    parser.add_argument(
        "--url", default=os.environ.get("MIND_SERVER_URL", "http://localhost:5000"),
        help="服务地址"
    )
    parser.add_argument(
        "--timeout", type=int, default=5,
        help="超时秒数"
    )
    args = parser.parse_args()

    ok = check_health(args.url, args.timeout)
    if ok:
        print("OK", flush=True)
        sys.exit(0)
    else:
        print("FAIL", flush=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
