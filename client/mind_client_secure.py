#!/usr/bin/env python3
"""
🎃 Pumpking Mind Sync Client - Secure Version
Supports: API Key authentication + Token validation + Request retry
"""
import os
import json
import requests
from datetime import datetime
from pathlib import Path

# ==================== Configuration ====================
# Server URL
SERVER_URL = os.environ.get('MIND_SERVER_URL', 'http://132.226.117.183:5000')

# Instance ID and name
INSTANCE_ID = os.environ.get('MIND_INSTANCE_ID', 'pumpking_main')
INSTANCE_NAME = os.environ.get('MIND_INSTANCE_NAME', 'Pumpking(Main Server)')

# API Keys (read from env vars, or use defaults)
API_KEY = os.environ.get('MIND_API_KEY', 'pumpking_secret_abc123')
INSTANCE_TOKEN = None  # Obtained after registration

# Verbose logging
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
        """Authenticated request"""
        url = f"{self.server_url}{endpoint}"
        headers = kwargs.get('headers', {})
        
        # Add auth headers
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
            print(f"❌ Request failed: {e}")
            return {"status": "error", "error": str(e)}
    
    def register(self):
        """Register instance and obtain token"""
        print(f"📝 Registering instance: {self.instance_id} ({self.instance_name})")
        
        data = {
            "instance_id": self.instance_id,
            "instance_name": self.instance_name,
            "description": "Pumpking main instance - secured"
        }
        
        result = self._request('POST', '/api/register', json=data)
        
        if result.get('status') == 'ok':
            self.token = result.get('token')
            print(f"✅ Registration success! Token: {self.token[:16]}...")
            self._save_token()
            return True
        else:
            print(f"❌ Registration failed: {result.get('error')}")
            return False
    
    def _save_token(self):
        """Save token to local file"""
        token_file = os.path.expanduser("~/.pumpking_token")
        with open(token_file, 'w') as f:
            f.write(self.token or "")
    
    def _load_token(self):
        """Load token from local file"""
        token_file = os.path.expanduser("~/.pumpking_token")
        if os.path.exists(token_file):
            with open(token_file, 'r') as f:
                self.token = f.read().strip()
            return bool(self.token)
        return False
    
    def ping(self):
        """Send heartbeat"""
        data = {"instance_id": self.instance_id}
        return self._request('POST', '/api/ping', json=data)
    
    def upload_thought(self, title, content, thought_type='general'):
        """Upload a thought"""
        if not self.token:
            print("❌ Token not registered, call register() first")
            return None
        
        data = {
            "instance_id": self.instance_id,
            "type": thought_type,
            "title": title,
            "content": content
        }
        
        return self._request('POST', '/api/upload/thought', json=data)
    
    def upload_skill(self, skill_name, content, description=''):
        """Upload a skill"""
        if not self.token:
            print("❌ Token not registered, call register() first")
            return None
        
        data = {
            "instance_id": self.instance_id,
            "skill_name": skill_name,
            "content": content,
            "description": description
        }
        
        return self._request('POST', '/api/upload/skill', json=data)
    
    def download_thoughts(self, thought_type=None, since=None):
        """Download thoughts"""
        params = {}
        if thought_type:
            params['type'] = thought_type
        if since:
            params['since'] = since
            
        return self._request('GET', '/api/download/thoughts', params=params)
    
    def download_skills(self):
        """Download skills"""
        return self._request('GET', '/api/download/skills')
    
    def list_instances(self):
        """List instances"""
        return self._request('GET', '/api/instances')
    
    def stats(self):
        """Get statistics"""
        return self._request('GET', '/api/stats')
    
    def health_check(self):
        """Health check"""
        try:
            resp = requests.get(f"{self.server_url}/api/health", timeout=5)
            return resp.json()
        except:
            return {"status": "error", "error": "Connection failed"}


def main():
    """Test client"""
    print("=" * 50)
    print("🎃 Pumpking Mind Library Client - Secure Version")
    print("=" * 50)
    
    # Create client
    client = MindSyncClient(
        server_url=SERVER_URL,
        instance_id=INSTANCE_ID,
        instance_name=INSTANCE_NAME,
        api_key=API_KEY
    )
    
    # Health check
    print("\n1️⃣ Health check...")
    health = client.health_check()
    print(f"   {health}")
    
    # Try to load token
    if client._load_token():
        print(f"\n2️⃣ Loaded existing token: {client.token[:16]}...")
    else:
        # Register new instance
        print("\n2️⃣ Registering new instance...")
        client.register()
    
    # Send heartbeat
    print("\n3️⃣ Sending heartbeat...")
    result = client.ping()
    print(f"   {result}")
    
    # Get statistics
    print("\n4️⃣ Getting statistics...")
    stats = client.stats()
    print(f"   Thoughts: {stats.get('thoughts', 'N/A')}, Skills: {stats.get('skills', 'N/A')}, Instances: {stats.get('instances', 'N/A')}")
    
    # Get instance list
    print("\n5️⃣ Getting instance list...")
    instances = client.list_instances()
    print(f"   Total {instances.get('count', 0)} instances")
    for inst in instances.get('instances', [])[:3]:
        print(f"   - {inst.get('name')}: {inst.get('last_seen', '')[:19]}")
    
    print("\n✅ Test complete!")


if __name__ == '__main__':
    main()
