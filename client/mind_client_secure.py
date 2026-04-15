#!/usr/bin/env python3
"""
🎃 Pumpking 思想同步客户端 - 安全加固版
支持：API Key认证 + Token验证 + 请求重试
"""
import os
import json
import requests
from datetime import datetime
from pathlib import Path

# ==================== 配置 ====================
# 服务器地址
SERVER_URL = os.environ.get('MIND_SERVER_URL', 'http://132.226.117.183:5000')

# 实例ID和名称
INSTANCE_ID = os.environ.get('MIND_INSTANCE_ID', 'pumpking_main')
INSTANCE_NAME = os.environ.get('MIND_INSTANCE_NAME', 'Pumpking(主服务器)')

# API Keys（从环境变量读取，或使用默认值）
API_KEY = os.environ.get('MIND_API_KEY', 'pumpking_secret_abc123')
INSTANCE_TOKEN = None  # 注册后获取

# 详细日志
VERBOSE = os.environ.get('MIND_VERBOSE', 'true').lower() == 'true'

class MindSyncClient:
    def __init__(self, server_url, instance_id, instance_name, api_key):
        self.server_url = server_url.rstrip('/')
        self.instance_id = instance_id
        self.instance_name = instance_name
        self.api_key = api_key
        self.token = None
        self.last_sync_file = os.path.expanduser("~/.pumpking_last_sync")
        
    def _request(self, method, endpoint, **kwargs):
        """带认证的请求"""
        url = f"{self.server_url}{endpoint}"
        headers = kwargs.get('headers', {})
        
        # 添加认证头
        headers['X-API-Key'] = self.api_key
        headers['X-Instance-ID'] = self.instance_id
        if self.token:
            headers['X-Instance-Token'] = self.token
        
        kwargs['headers'] = headers
        kwargs['timeout'] = kwargs.get('timeout', 30)
        
        if VERBOSE:
            print(f"🔄 {method} {url}")
        
        try:
            resp = requests.request(method, url, **kwargs)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException as e:
            print(f"❌ 请求失败: {e}")
            return {"status": "error", "error": str(e)}
    
    def register(self):
        """注册实例并获取Token"""
        print(f"📝 注册实例: {self.instance_id} ({self.instance_name})")
        
        data = {
            "instance_id": self.instance_id,
            "instance_name": self.instance_name,
            "description": "Pumpking main instance - secured"
        }
        
        result = self._request('POST', '/api/register', json=data)
        
        if result.get('status') == 'ok':
            self.token = result.get('token')
            print(f"✅ 注册成功! Token: {self.token[:16]}...")
            self._save_token()
            return True
        else:
            print(f"❌ 注册失败: {result.get('error')}")
            return False
    
    def _save_token(self):
        """保存Token到本地"""
        token_file = os.path.expanduser("~/.pumpking_token")
        with open(token_file, 'w') as f:
            f.write(self.token or "")
    
    def _load_token(self):
        """从本地加载Token"""
        token_file = os.path.expanduser("~/.pumpking_token")
        if os.path.exists(token_file):
            with open(token_file, 'r') as f:
                self.token = f.read().strip()
            return bool(self.token)
        return False
    
    def ping(self):
        """发送心跳"""
        data = {"instance_id": self.instance_id}
        return self._request('POST', '/api/ping', json=data)
    
    def upload_thought(self, title, content, thought_type='general'):
        """上传思想"""
        if not self.token:
            print("❌ 未注册Token，请先调用 register()")
            return None
        
        data = {
            "instance_id": self.instance_id,
            "type": thought_type,
            "title": title,
            "content": content
        }
        
        return self._request('POST', '/api/upload/thought', json=data)
    
    def upload_skill(self, skill_name, content, description=''):
        """上传技能"""
        if not self.token:
            print("❌ 未注册Token，请先调用 register()")
            return None
        
        data = {
            "instance_id": self.instance_id,
            "skill_name": skill_name,
            "content": content,
            "description": description
        }
        
        return self._request('POST', '/api/upload/skill', json=data)
    
    def download_thoughts(self, thought_type=None, since=None):
        """下载思想"""
        params = {}
        if thought_type:
            params['type'] = thought_type
        if since:
            params['since'] = since
            
        return self._request('GET', '/api/download/thoughts', params=params)
    
    def download_skills(self):
        """下载技能"""
        return self._request('GET', '/api/download/skills')
    
    def list_instances(self):
        """列出实例"""
        return self._request('GET', '/api/instances')
    
    def stats(self):
        """获取统计"""
        return self._request('GET', '/api/stats')
    
    def health_check(self):
        """健康检查"""
        try:
            resp = requests.get(f"{self.server_url}/api/health", timeout=5)
            return resp.json()
        except:
            return {"status": "error", "error": "Connection failed"}


def main():
    """测试客户端"""
    print("=" * 50)
    print("🎃 Pumpking 思想库客户端 - 安全加固版")
    print("=" * 50)
    
    # 创建客户端
    client = MindSyncClient(
        server_url=SERVER_URL,
        instance_id=INSTANCE_ID,
        instance_name=INSTANCE_NAME,
        api_key=API_KEY
    )
    
    # 健康检查
    print("\n1️⃣ 健康检查...")
    health = client.health_check()
    print(f"   {health}")
    
    # 尝试加载Token
    if client._load_token():
        print(f"\n2️⃣ 加载已有Token: {client.token[:16]}...")
    else:
        # 注册新实例
        print("\n2️⃣ 注册新实例...")
        client.register()
    
    # 发送心跳
    print("\n3️⃣ 发送心跳...")
    result = client.ping()
    print(f"   {result}")
    
    # 获取统计
    print("\n4️⃣ 获取统计...")
    stats = client.stats()
    print(f"   思想: {stats.get('thoughts', 'N/A')}, 技能: {stats.get('skills', 'N/A')}, 实例: {stats.get('instances', 'N/A')}")
    
    # 获取实例列表
    print("\n5️⃣ 获取实例列表...")
    instances = client.list_instances()
    print(f"   共 {instances.get('count', 0)} 个实例")
    for inst in instances.get('instances', [])[:3]:
        print(f"   - {inst.get('name')}: {inst.get('last_seen', '')[:19]}")
    
    print("\n✅ 测试完成!")


if __name__ == '__main__':
    main()