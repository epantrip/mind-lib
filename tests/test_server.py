#!/usr/bin/env python3
"""
Mind Library Basic Tests

Test Routes:
- /api/health (public)
- /api/stats (admin auth)
- /api/register (public, auto-generates API Key)
- /api/ping (public)
- /api/upload/thought (client auth + approval)
- /api/download/thoughts (client auth)
- /api/upload/skill (client auth + approval)
- /api/download/skills (client auth)
- /api/instances (admin auth)
- /api/admin/add_client_key (admin auth)
- /api/admin/remove_client_key (admin auth)
- /api/admin/list_client_keys (admin auth)
- /api/admin/approve_instance (admin auth)
- /api/cluster/nodes (admin auth)
- /api/cluster/status (admin auth)
"""
import pytest
import requests
import time
import os
import uuid

# Test configuration
SERVER_URL = os.environ.get("TEST_SERVER_URL", "http://localhost:5000")

# Dynamically generate unique instance_id to avoid test conflicts
TEST_INSTANCE = f"test_{uuid.uuid4().hex[:8]}"


class TestHealth:
    """Health check (public endpoint)"""

    def test_health(self):
        resp = requests.get(f"{SERVER_URL}/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["version"] == "2.2.3"


class TestStatsAuth:
    """/api/stats auth tests"""

    def test_stats_without_auth_returns_401(self):
        """Accessing stats without auth → 401"""
        resp = requests.get(f"{SERVER_URL}/api/stats")
        assert resp.status_code == 401

    def test_stats_with_wrong_key_returns_401(self):
        """Wrong admin key → 401"""
        resp = requests.get(f"{SERVER_URL}/api/stats", headers={
            "X-API-Key": "wrong-key"
        })
        assert resp.status_code == 401

    def test_stats_with_admin_key_returns_200(self, admin_key):
        """Correct admin key → 200"""
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
    """Instance registration (auto-generates API Key)"""

    _instance_id = None
    _api_key = None

    @pytest.fixture(autouse=True)
    def _register_instance(self):
        """Register test instance, return api_key"""
        # Use a new instance_id each run
        iid = f"test_{uuid.uuid4().hex[:8]}"
        TestRegister._instance_id = iid

        resp = requests.post(f"{SERVER_URL}/api/register", json={
            "instance_id": iid,
            "instance_name": "Test Instance",
            "description": "Automated test"
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "api_key" in data
        assert data["approved"] is False
        TestRegister._api_key = data["api_key"]

    def test_register_returns_api_key(self):
        """Registration returns api_key"""
        assert TestRegister._api_key is not None
        assert len(TestRegister._api_key) == 32

    def test_register_duplicate_returns_409(self):
        """Duplicate registration → 409"""
        resp = requests.post(f"{SERVER_URL}/api/register", json={
            "instance_id": TestRegister._instance_id,
        })
        assert resp.status_code == 409

    def test_upload_thought_before_approval_returns_403(self):
        """Upload before approval → 403"""
        resp = requests.post(f"{SERVER_URL}/api/upload/thought", json={
            "type": "insight",
            "title": "Test",
            "content": "Pre-approval test"
        }, headers={
            "X-API-Key": TestRegister._api_key,
            "X-Instance-ID": TestRegister._instance_id
        })
        assert resp.status_code == 403


class TestAdminKeyManagement:
    """Admin Key Management API"""

    def test_add_client_key(self, admin_key):
        """Admin adds client key"""
        if not admin_key:
            pytest.skip("TEST_ADMIN_KEY not set")
        resp = requests.post(f"{SERVER_URL}/api/admin/add_client_key", json={
            "instance_id": "admin_test_instance",
            "api_key": "test-key-12345"
        }, headers={"X-API-Key": admin_key})
        assert resp.status_code == 200

    def test_list_client_keys(self, admin_key):
        """List client keys"""
        if not admin_key:
            pytest.skip("TEST_ADMIN_KEY not set")
        resp = requests.get(f"{SERVER_URL}/api/admin/list_client_keys",
                           headers={"X-API-Key": admin_key})
        assert resp.status_code == 200
        data = resp.json()
        assert "client_keys" in data
        # Key values should be masked
        if "admin_test_instance" in data["client_keys"]:
            assert data["client_keys"]["admin_test_instance"] == "***"

    def test_remove_client_key(self, admin_key):
        """Remove client key"""
        if not admin_key:
            pytest.skip("TEST_ADMIN_KEY not set")
        resp = requests.post(f"{SERVER_URL}/api/admin/remove_client_key", json={
            "instance_id": "admin_test_instance"
        }, headers={"X-API-Key": admin_key})
        assert resp.status_code == 200

    def test_remove_client_key_without_auth(self):
        """Remove without auth → 401"""
        resp = requests.post(f"{SERVER_URL}/api/admin/remove_client_key", json={
            "instance_id": "admin_test_instance"
        })
        assert resp.status_code == 401


class TestDownloadAuth:
    """Download API auth tests"""

    def test_download_thoughts_without_auth_returns_401(self):
        """Download without auth → 401"""
        resp = requests.get(f"{SERVER_URL}/api/download/thoughts")
        assert resp.status_code == 401

    def test_download_skills_without_auth_returns_401(self):
        """Download skills without auth → 401"""
        resp = requests.get(f"{SERVER_URL}/api/download/skills")
        assert resp.status_code == 401


class TestClusterAuth:
    """Cluster API auth tests"""

    def test_cluster_nodes_without_auth_returns_401(self):
        resp = requests.get(f"{SERVER_URL}/api/cluster/nodes")
        assert resp.status_code == 401

    def test_cluster_status_without_auth_returns_401(self):
        resp = requests.get(f"{SERVER_URL}/api/cluster/status")
        assert resp.status_code == 401


# ============== Fixtures ==============

@pytest.fixture(scope="session")
def admin_key():
    """Read admin key from env var or .env file"""
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
