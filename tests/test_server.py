#!/usr/bin/env python3
"""
Mind Library 基础测试
"""
import pytest
import requests
import time
import os

# 测试配置
SERVER_URL = os.environ.get("TEST_SERVER_URL", "http://localhost:5000")
TEST_INSTANCE = "test_instance_" + str(int(time.time()))

class TestServer:
    """服务器端测试"""
    
    def test_health(self):
        """测试健康检查"""
        resp = requests.get(f"{SERVER_URL}/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
    
    def test_stats(self):
        """测试统计接口"""
        resp = requests.get(f"{SERVER_URL}/api/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert "thoughts" in data
        assert "skills" in data
        assert "instances" in data
    
    def test_register(self):
        """测试实例注册"""
        resp = requests.post(f"{SERVER_URL}/api/register", json={
            "instance_id": TEST_INSTANCE,
            "instance_name": "测试实例",
            "description": "自动化测试"
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
    
    def test_ping(self):
        """测试心跳"""
        resp = requests.post(f"{SERVER_URL}/api/ping", json={
            "instance_id": TEST_INSTANCE
        })
        assert resp.status_code == 200
    
    def test_upload_thought(self):
        """测试上传思想"""
        resp = requests.post(f"{SERVER_URL}/api/upload/thought", json={
            "instance_id": TEST_INSTANCE,
            "title": "测试思想",
            "content": "这是一条测试思想",
            "type": "general"
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "thought_id" in data
    
    def test_download_thoughts(self):
        """测试下载思想"""
        resp = requests.get(f"{SERVER_URL}/api/download/thoughts")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "thoughts" in data
        assert isinstance(data["thoughts"], list)
    
    def test_upload_skill(self):
        """测试上传技能"""
        resp = requests.post(f"{SERVER_URL}/api/upload/skill", json={
            "instance_id": TEST_INSTANCE,
            "skill_name": f"test_skill_{int(time.time())}",
            "description": "测试技能",
            "content": "# 测试技能\n\n这是测试内容"
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
    
    def test_download_skills(self):
        """测试下载技能"""
        resp = requests.get(f"{SERVER_URL}/api/download/skills")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "skills" in data
    
    def test_list_instances(self):
        """测试列出实例"""
        resp = requests.get(f"{SERVER_URL}/api/instances")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "instances" in data
        # 确保测试实例在列表中
        instance_ids = [i["id"] for i in data["instances"]]
        assert TEST_INSTANCE in instance_ids


if __name__ == "__main__":
    pytest.main([__file__, "-v"])