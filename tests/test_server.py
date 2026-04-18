#!/usr/bin/env python3
"""
Mind Library 基础测试

测试路由：
- /api/health (公开)
- /api/stats (管理员认证)
- /api/register (公开，自动生成 API Key)
- /api/ping (公开)
- /api/upload/thought (客户端认证+审批)
- /api/download/thoughts (客户端认证)
- /api/upload/skill (客户端认证+审批)
- /api/download/skills (客户端认证)
- /api/instances (管理员认证)
- /api/admin/add_client_key (管理员认证)
- /api/admin/remove_client_key (管理员认证)
- /api/admin/list_client_keys (管理员认证)
- /api/admin/approve_instance (管理员认证)
- /api/cluster/nodes (管理员认证)
- /api/cluster/status (管理员认证)
"""
import pytest
import requests
import time
import os
import uuid

# 测试配置
SERVER_URL = os.environ.get("TEST_SERVER_URL", "http://localhost:5000")

# 动态生成唯一 instance_id，避免测试间冲突
TEST_INSTANCE = f"test_{uuid.uuid4().hex[:8]}"


class TestHealth:
    """健康检查（公开端点）"""

    def test_health(self):
        resp = requests.get(f"{SERVER_URL}/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["version"] == "2.2.0"


class TestStatsAuth:
    """/api/stats 鉴权测试"""

    def test_stats_without_auth_returns_401(self):
        """无认证访问 stats → 401"""
        resp = requests.get(f"{SERVER_URL}/api/stats")
        assert resp.status_code == 401

    def test_stats_with_wrong_key_returns_401(self):
        """错误 admin key → 401"""
        resp = requests.get(f"{SERVER_URL}/api/stats", headers={
            "X-API-Key": "wrong-key"
        })
        assert resp.status_code == 401

    def test_stats_with_admin_key_returns_200(self, admin_key):
        """正确 admin key → 200"""
        if not admin_key:
            pytest.skip("TEST_ADMIN_KEY not set")
        resp = requests.get(f"{SERVER_URL}/api/stats", headers={
            "X-API-Key": admin_key
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "thoughts" in data
        assert "skills" in data
        assert "coordinator" in data


class TestRegister:
    """实例注册（自动生成 API Key）"""

    _instance_id = None
    _api_key = None

    @pytest.fixture(autouse=True)
    def _register_instance(self):
        """注册测试实例，返回 api_key"""
        # 每次运行用新的 instance_id
        iid = f"test_{uuid.uuid4().hex[:8]}"
        TestRegister._instance_id = iid

        resp = requests.post(f"{SERVER_URL}/api/register", json={
            "instance_id": iid,
            "instance_name": "测试实例",
            "description": "自动化测试"
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "api_key" in data
        assert data["approved"] is False
        TestRegister._api_key = data["api_key"]

    def test_register_returns_api_key(self):
        """注册返回 api_key"""
        assert TestRegister._api_key is not None
        assert len(TestRegister._api_key) == 32

    def test_register_duplicate_returns_409(self):
        """重复注册 → 409"""
        resp = requests.post(f"{SERVER_URL}/api/register", json={
            "instance_id": TestRegister._instance_id,
        })
        assert resp.status_code == 409

    def test_upload_thought_before_approval_returns_403(self):
        """未审批的上传 → 403"""
        resp = requests.post(f"{SERVER_URL}/api/upload/thought", json={
            "type": "insight",
            "title": "测试",
            "content": "未审批测试"
        }, headers={
            "X-API-Key": TestRegister._api_key,
            "X-Instance-ID": TestRegister._instance_id
        })
        assert resp.status_code == 403


class TestAdminKeyManagement:
    """管理员 Key 管理接口"""

    def test_add_client_key(self, admin_key):
        """管理员添加客户端 Key"""
        if not admin_key:
            pytest.skip("TEST_ADMIN_KEY not set")
        resp = requests.post(f"{SERVER_URL}/api/admin/add_client_key", json={
            "instance_id": "admin_test_instance",
            "api_key": "test-key-12345"
        }, headers={"X-API-Key": admin_key})
        assert resp.status_code == 200

    def test_list_client_keys(self, admin_key):
        """列出客户端 Key"""
        if not admin_key:
            pytest.skip("TEST_ADMIN_KEY not set")
        resp = requests.get(f"{SERVER_URL}/api/admin/list_client_keys",
                           headers={"X-API-Key": admin_key})
        assert resp.status_code == 200
        data = resp.json()
        assert "client_keys" in data
        # 密钥值应该被遮蔽
        if "admin_test_instance" in data["client_keys"]:
            assert data["client_keys"]["admin_test_instance"] == "***"

    def test_remove_client_key(self, admin_key):
        """移除客户端 Key"""
        if not admin_key:
            pytest.skip("TEST_ADMIN_KEY not set")
        resp = requests.post(f"{SERVER_URL}/api/admin/remove_client_key", json={
            "instance_id": "admin_test_instance"
        }, headers={"X-API-Key": admin_key})
        assert resp.status_code == 200

    def test_remove_client_key_without_auth(self):
        """无认证移除 → 401"""
        resp = requests.post(f"{SERVER_URL}/api/admin/remove_client_key", json={
            "instance_id": "admin_test_instance"
        })
        assert resp.status_code == 401


class TestDownloadAuth:
    """下载接口认证测试"""

    def test_download_thoughts_without_auth_returns_401(self):
        """无认证下载 → 401"""
        resp = requests.get(f"{SERVER_URL}/api/download/thoughts")
        assert resp.status_code == 401

    def test_download_skills_without_auth_returns_401(self):
        """无认证下载技能 → 401"""
        resp = requests.get(f"{SERVER_URL}/api/download/skills")
        assert resp.status_code == 401


class TestClusterAuth:
    """集群接口认证测试"""

    def test_cluster_nodes_without_auth_returns_401(self):
        resp = requests.get(f"{SERVER_URL}/api/cluster/nodes")
        assert resp.status_code == 401

    def test_cluster_status_without_auth_returns_401(self):
        resp = requests.get(f"{SERVER_URL}/api/cluster/status")
        assert resp.status_code == 401


# ============== Fixtures ==============

@pytest.fixture(scope="session")
def admin_key():
    """从环境变量或 .env 文件读取管理员 Key"""
    key = os.environ.get("TEST_ADMIN_KEY", "")
    if not key:
        env_path = os.path.join(os.path.dirname(__file__), '..', 'server', '.env')
        if os.path.exists(env_path):
            with open(env_path, 'r') as f:
                for line in f:
                    if line.startswith('MIND_ADMIN_API_KEY='):
                        key = line.strip().split('=', 1)[1]
                        break
    return key


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
