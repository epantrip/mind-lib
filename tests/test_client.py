#!/usr/bin/env python3
"""
Mind Library 客户端测试
"""
import pytest
import os
import sys

# 添加client目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'client'))

class TestClient:
    """客户端测试"""
    
    def test_import(self):
        """测试能否正确导入客户端"""
        from mind_client import MindSyncClient
        assert MindSyncClient is not None
    
    def test_client_init(self):
        """测试客户端初始化"""
        from mind_client import MindSyncClient
        client = MindSyncClient(
            server_url="http://localhost:5000",
            instance_id="test",
            instance_name="Test"
        )
        assert client.server_url == "http://localhost:5000"
        assert client.instance_id == "test"
        assert client.instance_name == "Test"
    
    def test_last_sync_file_path(self):
        """测试同步文件路径"""
        from mind_client import MindSyncClient
        client = MindSyncClient(
            server_url="http://localhost:5000",
            instance_id="test",
            instance_name="Test"
        )
        # 验证文件路径包含instance_id
        assert "test" in client.last_sync_file or ".pumpking" in client.last_sync_file


if __name__ == "__main__":
    pytest.main([__file__, "-v"])