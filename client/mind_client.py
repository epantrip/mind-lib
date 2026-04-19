#!/usr/bin/env python3
"""
🎃 Pumpking Mind Sync Client: Download and share thoughts from the mind library across instances
"""
import os
import json
import requests
import hashlib
from datetime import datetime
from pathlib import Path

class MindSyncClient:
    def __init__(self, server_url, instance_id, instance_name):
        self.server_url = server_url.rstrip('/')
        self.instance_id = instance_id
        self.instance_name = instance_name
        self.last_sync_file = os.path.expanduser("~/.pumpking_last_sync")
        
    def register(self):
        """Register with the mind server"""
        try:
            resp = requests.post(f"{self.server_url}/api/register", json={
                "instance_id": self.instance_id,
                "instance_name": self.instance_name,
                "description": "Pumpking instance"
            }, timeout=10)
            return resp.json().get('status') == 'ok'
        except Exception as e:
            print(f"Registration failed: {e}")
            return False
    
    def ping(self):
        """Heartbeat ping"""
        try:
            resp = requests.post(f"{self.server_url}/api/ping", json={
                "instance_id": self.instance_id
            }, timeout=5)
            return resp.json().get('status') == 'ok'
        except:
            return False
    
    def upload_thought(self, title, content, thought_type="general"):
        """Upload a thought"""
        try:
            resp = requests.post(f"{self.server_url}/api/upload/thought", json={
                "instance_id": self.instance_id,
                "title": title,
                "content": content,
                "type": thought_type
            }, timeout=30)
            result = resp.json()
            if result.get('status') == 'ok':
                print(f"✓ Uploaded thought: {title}")
                return True
            return False
        except Exception as e:
            print(f"✗ Upload failed: {e}")
            return False
    
    def upload_skill(self, skill_name, skill_content, skill_desc=""):
        """Upload a skill"""
        try:
            resp = requests.post(f"{self.server_url}/api/upload/skill", json={
                "instance_id": self.instance_id,
                "skill_name": skill_name,
                "content": skill_content,
                "description": skill_desc
            }, timeout=30)
            result = resp.json()
            if result.get('status') == 'ok':
                print(f"✓ Uploaded skill: {skill_name}")
                return True
            return False
        except Exception as e:
            print(f"✗ Upload skill failed: {e}")
            return False
    
    def download_thoughts(self, thought_type=None):
        """Download new thoughts"""
        try:
            since = self._get_last_sync_time()
            params = {}
            if thought_type:
                params['type'] = thought_type
            if since:
                params['since'] = since
                
            resp = requests.get(f"{self.server_url}/api/download/thoughts", 
                              params=params, timeout=30)
            result = resp.json()
            
            if result.get('status') == 'ok':
                thoughts = result.get('thoughts', [])
                print(f"📥 Got {len(thoughts)} new thoughts")
                return thoughts
            return []
        except Exception as e:
            print(f"✗ Download thoughts failed: {e}")
            return []
    
    def download_skills(self):
        """Download new skills"""
        try:
            resp = requests.get(f"{self.server_url}/api/download/skills", timeout=30)
            result = resp.json()
            
            if result.get('status') == 'ok':
                skills = result.get('skills', [])
                print(f"📥 Got {len(skills)} new skills")
                return skills
            return []
        except Exception as e:
            print(f"✗ Download skills failed: {e}")
            return []
    
    def sync_all(self):
        """Full sync"""
        print(f"\n🎃 Starting sync for {self.instance_name}")
        print("=" * 40)
        
        # 1. Heartbeat
        if self.ping():
            print("✓ Heartbeat OK")
        
        # 2. Download new thoughts
        new_thoughts = self.download_thoughts()
        for thought in new_thoughts:
            if thought.get('instance_id') != self.instance_id:
                self._save_thought(thought)
        
        # 3. Download new skills
        new_skills = self.download_skills()
        for skill in new_skills:
            self._save_skill(skill)
        
        # 4. Update sync timestamp
        self._update_last_sync()
        
        print("=" * 40)
        print("🎉 Sync complete!\n")
        return True
    
    def _save_thought(self, thought):
        """Save thought to local storage"""
        save_dir = Path(os.path.expanduser("~/.openclaw/workspace/memory/mind_sync"))
        save_dir.mkdir(parents=True, exist_ok=True)
        
        filename = f"{thought.get('id', 'unknown')}.json"
        filepath = save_dir / filename
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(thought, f, ensure_ascii=False, indent=2)
        
        print(f"  📝 New thought: {thought.get('title')} (from {thought.get('instance_id')})")
    
    def _save_skill(self, skill):
        """Save skill to local storage"""
        save_dir = Path(os.path.expanduser("~/.openclaw/workspace/skills"))
        skill_name = skill.get('name', 'unknown')
        skill_dir = save_dir / skill_name
        skill_dir.mkdir(parents=True, exist_ok=True)
        
        # Save in learned.md format
        skill_file = skill_dir / "learned.md"
        with open(skill_file, 'w', encoding='utf-8') as f:
            f.write(f"# {skill_name}\n\n")
            f.write(f"**Source**: {skill.get('uploaded_by')}\n\n")
            f.write(f"**Description**: {skill.get('description')}\n\n")
            f.write("---\n\n")
            f.write(skill.get('content', ''))
        
        print(f"  🧠 New skill: {skill_name}")
    
    def _get_last_sync_time(self):
        """Get last sync timestamp"""
        if os.path.exists(self.last_sync_file):
            with open(self.last_sync_file, 'r') as f:
                return f.read().strip()
        return None
    
    def _update_last_sync(self):
        """Update sync timestamp"""
        with open(self.last_sync_file, 'w') as f:
            f.write(datetime.now().isoformat())


# ========== CLI Tool ==========

def main():
    import argparse
    parser = argparse.ArgumentParser(description='🎃 Pumpking Mind Sync Client')
    parser.add_argument('--server', '-s', required=True, help='Mind server URL')
    parser.add_argument('--id', '-i', default='pumpking_local', help='Instance ID')
    parser.add_argument('--name', '-n', default='Pumpking', help='Instance name')
    parser.add_argument('--upload-thought', '-u', nargs=2, metavar=('TITLE', 'CONTENT'), 
                       help='Upload a thought')
    parser.add_argument('--upload-skill', metavar=('NAME', 'FILE'), 
                       help='Upload a skill file')
    parser.add_argument('--sync', action='store_true', help='Run full sync')
    
    args = parser.parse_args()
    
    client = MindSyncClient(args.server, args.id, args.name)
    
    # Register
    client.register()
    
    # Execute operation
    if args.upload_thought:
        title, content = args.upload_thought
        client.upload_thought(title, content, "insight")
    elif args.upload_skill:
        name, filepath = args.upload_skill
        with open(filepath, 'r') as f:
            content = f.read()
        client.upload_skill(name, content, f"From {args.name}")
    elif args.sync:
        client.sync_all()
    else:
        parser.print_help()

if __name__ == '__main__':
    main()
