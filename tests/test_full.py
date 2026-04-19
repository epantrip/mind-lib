#!/usr/bin/env python3
"""
Mind Library v2.2.0 全面集成测试

覆盖完整业务流程：
  1. 注册 → 2. 上传(未审批403) → 3. 审批 → 4. 上传/下载 → 5. ping
  6. 管理员操作(add/list/remove key, revoke) → 7. 集群操作(add/remove node)
  8. 分布式副本(replica store/get) → 9. stats/stats

运行方式:
  $env:MIND_ADMIN_API_KEY="your-admin-key"; $env:MIND_NODE_SECRET="your-node-secret"; python tests/test_full.py
  python tests/test_full.py --no-server  # 只生成报告，不启动服务器
"""

import argparse
import hashlib
import hmac
import json
import os
import subprocess
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import requests

# ── 配置 ──────────────────────────────────────────────────────────────────────

SERVER_URL = os.environ.get("TEST_SERVER_URL", "http://localhost:5000")
ADMIN_KEY = os.environ.get("MIND_ADMIN_API_KEY", "")
NODE_SECRET = os.environ.get("MIND_NODE_SECRET", "")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
SERVER_DIR = os.path.join(PROJECT_ROOT, "server")
TEST_DB_DIR = os.environ.get("TEST_DB_DIR", "")

# ── 辅助函数 ──────────────────────────────────────────────────────────────────

def hmac_sign(method: str, path: str, body: bytes = b"", secret: str = NODE_SECRET) -> str:
    """生成节点间 HMAC-SHA256 签名"""
    body_hash = hashlib.sha256(body).hexdigest()
    message = f"{method.upper()}{path}{body_hash}".encode("utf-8")
    return hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()


def node_headers(method: str, path: str, body: bytes = b"") -> dict:
    """生成节点间认证请求头"""
    return {
        "Content-Type": "application/json",
        "X-Node-ID": "test_node",
        "X-Node-Signature": hmac_sign(method, path, body),
    }


class ResultTracker:
    """测试结果追踪"""

    def __init__(self):
        self.tests = []
        self.passed = 0
        self.failed = 0
        self.skipped = 0

    def record(self, name: str, passed: bool, detail: str = "", error: str = ""):
        status = "[PASS]" if passed else "[FAIL]"
        if not passed:
            self.failed += 1
            detail_str = f"  | {detail}" if detail else ""
            print(f"  {status} {name}{detail_str}")
            if error:
                print(f"  +-- Error: {error[:200]}")
        else:
            self.passed += 1
            print(f"  {status} {name}")

    def summary(self):
        total = self.passed + self.failed + self.skipped
        print(f"\n{'='*60}")
        print(f"  Results: {self.passed}/{total} passed", end="")
        if self.failed:
            print(f", {self.failed} failed", end="")
        if self.skipped:
            print(f", {self.skipped} skipped", end="")
        print()
        print(f"{'='*60}")
        return self.failed == 0


# ── 测试用例 ─────────────────────────────────────────────────────────────────

def test_health(tracker: ResultTracker):
    """T1: 健康检查（公开）"""
    resp = requests.get(f"{SERVER_URL}/api/health", timeout=5)
    tracker.record(
        "T1 健康检查",
        resp.status_code == 200 and resp.json().get("version") == "2.2.0",
        detail=f"status={resp.status_code}, version={resp.json().get('version')}",
    )


def test_stats_public(tracker: ResultTracker):
    """T2: stats 公开访问 → 401"""
    resp = requests.get(f"{SERVER_URL}/api/stats", timeout=5)
    tracker.record("T2 stats 需认证", resp.status_code == 401,
                   detail=f"status={resp.status_code} (期望401)")


def test_stats_admin(tracker: ResultTracker, admin_key: str):
    """T3: stats 管理员访问 → 200"""
    resp = requests.get(f"{SERVER_URL}/api/stats",
                        headers={"X-API-Key": admin_key}, timeout=5)
    data = resp.json()
    tracker.record(
        "T3 stats 管理员",
        resp.status_code == 200 and all(k in data for k in ("thoughts", "skills", "coordinator")),
        detail=f"thoughts={data.get('thoughts')}, skills={data.get('skills')}",
    )


def test_register_and_upload_flow(tracker: ResultTracker, admin_key: str):
    """T4-T8: 注册→未审批上传→审批→上传→下载 完整流程"""
    instance_id = f"comprehensive_{uuid.uuid4().hex[:8]}"

    # T4: 注册
    resp = requests.post(f"{SERVER_URL}/api/register", json={
        "instance_id": instance_id,
        "instance_name": "全面测试实例",
        "description": "完整流程测试",
    }, timeout=5)
    data = resp.json()
    api_key = data.get("api_key", "")
    registered = resp.status_code == 200 and len(api_key) == 32
    tracker.record("T4 注册返回32位API Key", registered,
                    detail=f"status={resp.status_code}, api_key={api_key[:8]}...")

    # T5: 未审批时上传 → 403
    resp = requests.post(f"{SERVER_URL}/api/upload/thought", json={
        "type": "insight",
        "title": "不应成功的思想",
        "content": "测试内容",
    }, headers={"X-API-Key": api_key, "X-Instance-ID": instance_id}, timeout=5)
    tracker.record("T5 未审批上传→403", resp.status_code == 403,
                    detail=f"status={resp.status_code} (期望403)")

    # T6: 管理员审批
    resp = requests.post(f"{SERVER_URL}/api/admin/approve_instance", json={
        "instance_id": instance_id,
    }, headers={"X-API-Key": admin_key}, timeout=5)
    approved = resp.status_code == 200
    tracker.record("T6 审批实例", approved,
                    detail=f"status={resp.status_code}")

    # T7: 审批后上传思想
    resp = requests.post(f"{SERVER_URL}/api/upload/thought", json={
        "type": "insight",
        "title": "测试思想 - 全面测试",
        "content": "这是全面测试的思想内容",
        "tags": ["测试", "全面测试"],
    }, headers={"X-API-Key": api_key, "X-Instance-ID": instance_id}, timeout=5)
    data = resp.json()
    thought_id = data.get("thought_id", "")
    upload_ok = resp.status_code == 200 and len(thought_id) > 0
    tracker.record("T7 上传思想", upload_ok,
                    detail=f"status={resp.status_code}, id={thought_id}")

    # T8: 下载思想（带过滤参数）
    resp = requests.get(
        f"{SERVER_URL}/api/download/thoughts",
        params={"type": "insight"},
        headers={"X-API-Key": api_key, "X-Instance-ID": instance_id}, timeout=5
    )
    data = resp.json()
    download_ok = resp.status_code == 200 and isinstance(data.get("thoughts"), list)
    tracker.record("T8 下载思想", download_ok,
                    detail=f"status={resp.status_code}, count={data.get('count')}")

    return instance_id, api_key, thought_id


def test_skill_upload_download(tracker: ResultTracker, instance_id: str, api_key: str):
    """T9-T10: 技能上传下载"""
    # T9: 上传技能
    skill_data = {
        "name": "test_skill_comprehensive",
        "description": "全面测试技能",
        "category": "testing",
        "content": "def execute(): return 'comprehensive test'",
        "version": "1.0.0",
    }
    resp = requests.post(f"{SERVER_URL}/api/upload/skill", json=skill_data,
                         headers={"X-API-Key": api_key, "X-Instance-ID": instance_id}, timeout=5)
    data = resp.json()
    skill_id = data.get("skill_id", "")
    tracker.record("T9 上传技能", resp.status_code == 200 and len(skill_id) > 0,
                    detail=f"status={resp.status_code}, id={skill_id}")

    # T10: 下载技能列表
    resp = requests.get(f"{SERVER_URL}/api/download/skills",
                         headers={"X-API-Key": api_key, "X-Instance-ID": instance_id}, timeout=5)
    data = resp.json()
    tracker.record("T10 下载技能列表", resp.status_code == 200 and "skills" in data,
                    detail=f"status={resp.status_code}, count={data.get('count')}")


def test_ping(tracker: ResultTracker, instance_id: str):
    """T11: ping 心跳"""
    resp = requests.post(f"{SERVER_URL}/api/ping", json={"instance_id": instance_id}, timeout=5)
    data = resp.json()
    tracker.record("T11 ping 心跳", resp.status_code == 200 and data.get("status") == "ok",
                    detail=f"status={resp.status_code}")


def test_admin_key_management(tracker: ResultTracker, admin_key: str):
    """T12-T15: 管理员 Key 管理"""
    test_iid = f"adminkey_test_{uuid.uuid4().hex[:8]}"
    test_key = uuid.uuid4().hex

    # T12: 添加 Key
    resp = requests.post(f"{SERVER_URL}/api/admin/add_client_key", json={
        "instance_id": test_iid,
        "api_key": test_key,
    }, headers={"X-API-Key": admin_key}, timeout=5)
    tracker.record("T12 添加客户端Key", resp.status_code == 200,
                    detail=f"status={resp.status_code}")

    # T13: 列出 Key
    resp = requests.get(f"{SERVER_URL}/api/admin/list_client_keys",
                         headers={"X-API-Key": admin_key}, timeout=5)
    data = resp.json()
    has_keys = "client_keys" in data
    tracker.record("T13 列出客户端Keys", has_keys and resp.status_code == 200,
                    detail=f"count={len(data.get('client_keys', {}))}")

    # T14: 用新Key下载（客户端认证，非管理员认证）
    resp = requests.get(f"{SERVER_URL}/api/download/thoughts",
                         headers={"X-API-Key": test_key, "X-Instance-ID": test_iid}, timeout=5)
    tracker.record("T14 新Key认证有效", resp.status_code == 200,
                    detail=f"status={resp.status_code}")

    # T15: 移除 Key
    resp = requests.post(f"{SERVER_URL}/api/admin/remove_client_key", json={
        "instance_id": test_iid,
    }, headers={"X-API-Key": admin_key}, timeout=5)
    tracker.record("T15 移除客户端Key", resp.status_code == 200,
                    detail=f"status={resp.status_code}")

    # 验证移除后 Key 失效
    resp = requests.get(f"{SERVER_URL}/api/stats",
                         headers={"X-API-Key": test_key}, timeout=5)
    tracker.record("T15b 移除后Key失效→401", resp.status_code == 401,
                    detail=f"status={resp.status_code} (期望401)")


def test_cluster_operations(tracker: ResultTracker, admin_key: str):
    """T16-T20: 集群操作"""
    node_id = f"test_node_{uuid.uuid4().hex[:8]}"

    # T16: 添加节点
    resp = requests.post(f"{SERVER_URL}/api/cluster/add_node", json={
        "node_id": node_id,
        "host": "192.168.1.100",
        "port": 5000,
    }, headers={"X-API-Key": admin_key}, timeout=5)
    tracker.record("T16 添加集群节点", resp.status_code == 200,
                    detail=f"status={resp.status_code}")

    # T17: 列出节点
    resp = requests.get(f"{SERVER_URL}/api/cluster/nodes",
                         headers={"X-API-Key": admin_key}, timeout=5)
    data = resp.json()
    nodes = data.get("nodes", [])
    has_node = any(n.get("node_id") == node_id for n in nodes)
    tracker.record("T17 节点在列表中", has_node and resp.status_code == 200,
                    detail=f"node_id={node_id}, 列表长度={len(nodes)}")

    # T18: 集群状态
    resp = requests.get(f"{SERVER_URL}/api/cluster/status",
                         headers={"X-API-Key": admin_key}, timeout=5)
    data = resp.json()
    tracker.record("T18 集群状态", resp.status_code == 200 and "nodes" in data,
                    detail=f"status={resp.status_code}")

    # T19: 节点间通信 - store replica
    body = json.dumps({"data_id": f"test_replica_{uuid.uuid4().hex[:8]}",
                       "data_type": "thought",
                       "content": {"title": "副本测试", "body": "测试内容"}}).encode("utf-8")
    resp = requests.post(
        f"{SERVER_URL}/api/replica/store",
        json=json.loads(body),
        headers=node_headers("POST", "/api/replica/store", body),
        timeout=5
    )
    tracker.record("T19 节点间存储副本", resp.status_code == 200,
                    detail=f"status={resp.status_code}")

    # T20: 节点间通信 - get replica
    data_id = json.loads(body)["data_id"]
    resp = requests.get(
        f"{SERVER_URL}/api/replica/get/{data_id}",
        headers=node_headers("GET", f"/api/replica/get/{data_id}"),
        timeout=5
    )
    data = resp.json()
    tracker.record("T20 节点间获取副本", resp.status_code == 200 and data.get("found") is True,
                    detail=f"found={data.get('found')}")

    # T21: 节点间通信 - sync/pull
    body_pull = json.dumps({"source_node": "test_node"}).encode("utf-8")
    resp = requests.post(
        f"{SERVER_URL}/api/sync/pull",
        json=json.loads(body_pull),
        headers=node_headers("POST", "/api/sync/pull", body_pull),
        timeout=5
    )
    data = resp.json()
    tracker.record("T21 节点间数据同步", resp.status_code == 200 and "thoughts" in data,
                    detail=f"status={resp.status_code}, thoughts={len(data.get('thoughts', []))}")

    # T22: replica/migrate 端点
    resp = requests.get(
        f"{SERVER_URL}/api/replica/migrate?target={node_id}",
        headers=node_headers("GET", f"/api/replica/migrate?target={node_id}"),
        timeout=5
    )
    data = resp.json()
    tracker.record("T22 数据迁移计算", resp.status_code == 200 and "items" in data,
                    detail=f"status={resp.status_code}, items={len(data.get('items', []))}")

    # T23: 无节点认证访问 → 401
    resp = requests.post(f"{SERVER_URL}/api/replica/store", json={
        "data_id": "test_no_auth",
        "content": "no auth",
    }, timeout=5)
    tracker.record("T23 节点间API无认证→401", resp.status_code == 401,
                    detail=f"status={resp.status_code} (期望401)")

    # T24: 移除节点
    resp = requests.post(f"{SERVER_URL}/api/cluster/remove_node", json={
        "node_id": node_id,
    }, headers={"X-API-Key": admin_key}, timeout=5)
    tracker.record("T24 移除集群节点", resp.status_code == 200,
                    detail=f"status={resp.status_code}")


def test_instances_and_revoke(tracker: ResultTracker, admin_key: str):
    """T25-T27: 实例列表和撤销"""
    # T25: 列出实例
    resp = requests.get(f"{SERVER_URL}/api/instances",
                         headers={"X-API-Key": admin_key}, timeout=5)
    data = resp.json()
    instances = data.get("instances", [])
    tracker.record("T25 列出实例", resp.status_code == 200 and isinstance(instances, list),
                    detail=f"status={resp.status_code}, count={len(instances)}")

    # T26: 撤销实例
    revoke_iid = f"revoke_test_{uuid.uuid4().hex[:8]}"
    requests.post(f"{SERVER_URL}/api/admin/add_client_key", json={
        "instance_id": revoke_iid,
        "api_key": "revoke-test-key",
    }, headers={"X-API-Key": admin_key}, timeout=5)
    resp = requests.post(f"{SERVER_URL}/api/admin/revoke_instance", json={
        "instance_id": revoke_iid,
    }, headers={"X-API-Key": admin_key}, timeout=5)
    tracker.record("T26 撤销实例", resp.status_code == 200,
                    detail=f"status={resp.status_code}")

    # T27: 撤销后该实例的 Key 失效
    resp = requests.get(f"{SERVER_URL}/api/stats",
                         headers={"X-API-Key": "revoke-test-key"}, timeout=5)
    tracker.record("T27 撤销后Key失效→401", resp.status_code == 401,
                    detail=f"status={resp.status_code} (期望401)")


def test_concurrent_upload(tracker: ResultTracker, instance_id: str, api_key: str):
    """T28: 并发上传思想"""
    results = []
    errors = []

    def upload_thought(i: int):
        try:
            resp = requests.post(f"{SERVER_URL}/api/upload/thought", json={
                "type": "test",
                "title": f"并发测试思想 {i}",
                "content": f"并发测试内容 {i}",
            }, headers={"X-API-Key": api_key, "X-Instance-ID": instance_id}, timeout=10)
            return resp.status_code == 200
        except Exception as e:
            errors.append(str(e))
            return False

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(upload_thought, i) for i in range(10)]
        for f in as_completed(futures):
            results.append(f.result())

    success_count = sum(results)
    all_ok = success_count == 10 and len(errors) == 0
    tracker.record("T28 并发上传(10线程)", all_ok,
                    detail=f"成功={success_count}/10, 错误={len(errors)}")


# ── 主流程 ───────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Mind Library v2.2.0 全面测试")
    parser.add_argument("--no-server", action="store_true",
                        help="跳过服务器启动，仅生成测试报告")
    args = parser.parse_args()

    if not ADMIN_KEY:
        print("[FAIL] Please set MIND_ADMIN_API_KEY env var first")
        sys.exit(1)
    if not NODE_SECRET:
        print("[WARN] MIND_NODE_SECRET not set - node-to-node auth tests will fail")
        print("   Set with: $env:MIND_NODE_SECRET='your-secret'")

    print(f"\n{'='*60}")
    print(f"  Mind Library v2.2.0 全面测试")
    print(f"  服务器: {SERVER_URL}")
    print(f"  时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")

    tracker = ResultTracker()
    server_proc = None

    # 启动服务器
    if not args.no_server:
        env = os.environ.copy()
        env["MIND_ADMIN_API_KEY"] = ADMIN_KEY
        env["MIND_NODE_SECRET"] = NODE_SECRET
        if TEST_DB_DIR:
            env["MIND_DB_PATH"] = TEST_DB_DIR
        else:
            import tempfile
            td = tempfile.mkdtemp(prefix="mind_full_test_")
            env["MIND_DB_PATH"] = td
            print(f"[服务器] 测试数据库: {td}")

        print("[服务器] 启动 mind_server_v2.1.py ...")
        server_proc = subprocess.Popen(
            [sys.executable, "mind_server_v2.1.py"],
            cwd=SERVER_DIR,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

        # 等待服务器就绪（最多30秒）
        print("[服务器] 等待就绪...", end="", flush=True)
        for i in range(30):
            try:
                r = requests.get(f"{SERVER_URL}/api/health", timeout=1)
                if r.status_code == 200:
                    print(f" OK ({i+1}s)")
                    break
            except requests.exceptions.ConnectionError:
                pass
            except requests.exceptions.Timeout:
                pass
            print(".", end="", flush=True)
            time.sleep(1)
        else:
            print("\n[FAIL] Server startup timeout")
            if server_proc:
                server_proc.terminate()
            sys.exit(1)

        # 打印服务器启动日志前几行
        try:
            import select
            if hasattr(select, "select"):
                ready, _, _ = select.select([server_proc.stdout], [], [], 0.5)
                if ready:
                    lines = server_proc.stdout.readline().strip()
                    if lines:
                        print(f"[服务器] {lines[:100]}")
        except Exception:
            pass

    # 运行测试
    print(f"\n{'─'*60}")
    print("  基础端点")
    print(f"{'─'*60}")
    test_health(tracker)
    test_stats_public(tracker)
    test_stats_admin(tracker, ADMIN_KEY)

    print(f"\n{'─'*60}")
    print("  注册 → 审批 → 上传/下载 完整流程")
    print(f"{'─'*60}")
    instance_id, api_key, thought_id = test_register_and_upload_flow(tracker, ADMIN_KEY)

    print(f"\n{'─'*60}")
    print("  技能上传下载")
    print(f"{'─'*60}")
    test_skill_upload_download(tracker, instance_id, api_key)

    print(f"\n{'─'*60}")
    print("  ping 心跳")
    print(f"{'─'*60}")
    test_ping(tracker, instance_id)

    print(f"\n{'─'*60}")
    print("  管理员 Key 管理 (add→list→auth→remove→auth验证)")
    print(f"{'─'*60}")
    test_admin_key_management(tracker, ADMIN_KEY)

    print(f"\n{'─'*60}")
    print("  集群操作 + 节点间副本 API")
    print(f"{'─'*60}")
    test_cluster_operations(tracker, ADMIN_KEY)

    print(f"\n{'─'*60}")
    print("  实例列表 + 撤销")
    print(f"{'─'*60}")
    test_instances_and_revoke(tracker, ADMIN_KEY)

    print(f"\n{'─'*60}")
    print("  并发安全")
    print(f"{'─'*60}")
    test_concurrent_upload(tracker, instance_id, api_key)

    # 关闭服务器
    if server_proc:
        print(f"\n[服务器] 关闭中...")
        server_proc.terminate()
        try:
            server_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server_proc.kill()

    success = tracker.summary()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
