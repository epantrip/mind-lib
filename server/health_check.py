#!/usr/bin/env python3
"""
Health Check Script - for Docker/K8s liveness/readiness probes

Usage:
    python health_check.py [--url http://localhost:5000] [--timeout 5]

Exit codes:
    0 = healthy
    1 = unhealthy (service error or network error)
"""
import os, sys, argparse, urllib.request, urllib.error, json


def check_health(url: str, timeout: int) -> bool:
    """Check service health status"""
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
    parser = argparse.ArgumentParser(description="Mind Library Health Check")
    parser.add_argument(
        "--url", default=os.environ.get("MIND_SERVER_URL", "http://localhost:5000"),
        help="Service URL"
    )
    parser.add_argument(
        "--timeout", type=int, default=5,
        help="Timeout in seconds"
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
