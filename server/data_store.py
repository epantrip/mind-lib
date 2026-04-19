"""
🧠 Mind Library - Thread-safe Data Storage Layer

P0: Concurrency Safety
- Uses RLock to protect reads/writes of thoughts/skills/instances
- Locks cover memory operations + local disk I/O only; network I/O goes outside the lock
"""

import os
import json
import logging
import threading
import time
from typing import Any, Dict, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class DataStore:
    """
    Thread-safe data storage layer

    Design Principles:
    1. Locks cover memory reads/writes + local disk writes only (millisecond-level)
    2. Network I/O (sync, webhooks) must be called outside the lock
    3. Read operations must also be locked to prevent reading partially-written data
    """

    def __init__(self, db_path: str):
        self.db_path = db_path
        os.makedirs(db_path, exist_ok=True)

        # Thread lock - protects all data operations
        self._lock = threading.RLock()

        # In-memory cache
        self._thoughts: List[Dict] = []
        self._skills: List[Dict] = []
        self._instances: Dict[str, Dict] = {}
        self._client_keys: Dict[str, str] = {}  # Persisted client API keys

        # Load data
        self._load_all()

    # ==================== Private Methods ====================

    def _load_all(self) -> None:
        """Load all data"""
        self._thoughts = self._load_file('thoughts.json', [])
        self._skills = self._load_file('skills.json', [])
        self._instances = self._load_file('instances.json', {})
        self._client_keys = self._load_file('client_keys.json', {})

        # Compatibility with v2.0 directory-based storage
        self._load_compat_directory()

        logger.info(f"Data load complete: {len(self._thoughts)} thoughts, {len(self._skills)} skills, {len(self._instances)} instances")

    def _load_file(self, filename: str, default: Any) -> Any:
        """Load a single data file"""
        path = os.path.join(self.db_path, filename)
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load {filename}: {e}")
        return default

    def _load_compat_directory(self) -> None:
        """Compatibility with v2.0 directory-based storage"""
        # instances: load from instances/ directory
        inst_dir = os.path.join(self.db_path, 'instances')
        if os.path.isdir(inst_dir):
            for fname in os.listdir(inst_dir):
                if fname.endswith('.json'):
                    try:
                        with open(os.path.join(inst_dir, fname), 'r', encoding='utf-8') as f:
                            data = json.load(f)
                            iid = data.get('id') or data.get('instance_id') or fname.replace('.json', '')
                            self._instances[iid] = data
                    except Exception:
                        pass

        # thoughts: load from thoughts/ directory
        thoughts_dir = os.path.join(self.db_path, 'thoughts')
        if os.path.isdir(thoughts_dir):
            for fname in sorted(os.listdir(thoughts_dir)):
                if fname.endswith('.json'):
                    try:
                        with open(os.path.join(thoughts_dir, fname), 'r', encoding='utf-8') as f:
                            self._thoughts.append(json.load(f))
                    except Exception:
                        pass

        # skills: load from skills/ directory
        skills_dir = os.path.join(self.db_path, 'skills')
        if os.path.isdir(skills_dir):
            for fname in sorted(os.listdir(skills_dir)):
                if fname.endswith('.json'):
                    try:
                        with open(os.path.join(skills_dir, fname), 'r', encoding='utf-8') as f:
                            self._skills.append(json.load(f))
                    except Exception:
                        pass

    def _save_file(self, filename: str, data: Any) -> None:
        """Save data to file"""
        # Compatibility with v2.0 directory-based storage
        if filename == 'instances.json' and isinstance(data, dict):
            self._save_directory('instances', data)
            return
        if filename in ('thoughts.json', 'skills.json') and isinstance(data, list):
            self._save_directory(filename.replace('.json', ''), data)
            return

        # Default JSON file
        path = os.path.join(self.db_path, filename)
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to save {filename}: {e}")

    def _save_directory(self, dir_name: str, data: Any) -> None:
        """Save to directory (v2.0 compatibility)"""
        dir_path = os.path.join(self.db_path, dir_name)
        os.makedirs(dir_path, exist_ok=True)

        if isinstance(data, dict):
            # instances: one file per instance
            for iid, inst_data in data.items():
                try:
                    fname = f"{iid}.json"
                    with open(os.path.join(dir_path, fname), 'w', encoding='utf-8') as f:
                        json.dump(inst_data, f, ensure_ascii=False, indent=2)
                except Exception as e:
                    logger.error(f"Failed to save instance {iid}: {e}")
        elif isinstance(data, list):
            # thoughts/skills: one file per entry
            for item in data:
                item_id = item.get('id') or item.get('instance_id', '')
                ts = item.get('timestamp', item.get('created_at', ''))
                if item_id and ts:
                    fname = f"{item_id}_{ts.replace('-','').replace(':','').replace('.','')}.json"
                elif item_id:
                    fname = f"{item_id}.json"
                else:
                    fname = f"{int(time.time())}.json"
                try:
                    with open(os.path.join(dir_path, fname), 'w', encoding='utf-8') as f:
                        json.dump(item, f, ensure_ascii=False, indent=2)
                except Exception as e:
                    logger.error(f"Failed to save {fname}: {e}")

    # ==================== Thoughts ====================

    def get_thoughts(self, since: str = '', thought_type: str = None) -> List[Dict]:
        """Get thought list (thread-safe)"""
        with self._lock:
            result = [t for t in self._thoughts if t.get('created_at', '') > since]
            if thought_type:
                result = [t for t in result if t.get('type') == thought_type]
            return result

    def get_all_thoughts(self) -> List[Dict]:
        """Get all thoughts"""
        with self._lock:
            return list(self._thoughts)

    def add_thought(self, thought: Dict) -> Dict:
        """Add thought (thread-safe)"""
        with self._lock:
            self._thoughts.append(thought)
            self._save_file('thoughts.json', self._thoughts)
        return thought

    def update_thought(self, thought_id: str, thought: Dict) -> bool:
        """Update thought"""
        with self._lock:
            for i, t in enumerate(self._thoughts):
                if t.get('id') == thought_id:
                    self._thoughts[i] = thought
                    self._save_file('thoughts.json', self._thoughts)
                    return True
        return False

    # ==================== Skills ====================

    def get_skills(self) -> List[Dict]:
        """Get skills list (thread-safe)"""
        with self._lock:
            return list(self._skills)

    def add_skill(self, skill: Dict) -> Dict:
        """Add skill (thread-safe)"""
        with self._lock:
            # Update existing skill
            for i, s in enumerate(self._skills):
                if s.get('name') == skill['name']:
                    self._skills[i] = skill
                    self._save_file('skills.json', self._skills)
                    return skill
            # New entry
            self._skills.append(skill)
            self._save_file('skills.json', self._skills)
        return skill

    def update_skill(self, skill_id: str, skill: Dict) -> bool:
        """Update skill"""
        with self._lock:
            for i, s in enumerate(self._skills):
                if s.get('id') == skill_id:
                    self._skills[i] = skill
                    self._save_file('skills.json', self._skills)
                    return True
        return False

    # ==================== Instances ====================

    def get_instances(self) -> Dict[str, Dict]:
        """Get all instances"""
        with self._lock:
            return dict(self._instances)

    def get_instance(self, instance_id: str) -> Optional[Dict]:
        """Get single instance"""
        with self._lock:
            return self._instances.get(instance_id)

    def add_instance(self, instance: Dict) -> Dict:
        """Add instance (thread-safe)"""
        with self._lock:
            instance_id = instance.get('id') or instance.get('instance_id')
            self._instances[instance_id] = instance
            self._save_file('instances.json', self._instances)
        return instance

    def update_instance(self, instance_id: str, updates: Dict) -> bool:
        """Update instance"""
        with self._lock:
            if instance_id in self._instances:
                self._instances[instance_id].update(updates)
                self._save_file('instances.json', self._instances)
                return True
        return False

    def delete_instance(self, instance_id: str) -> bool:
        """Delete instance"""
        with self._lock:
            if instance_id in self._instances:
                del self._instances[instance_id]
                self._save_file('instances.json', self._instances)
                return True
        return False

    def instance_exists(self, instance_id: str) -> bool:
        """Check if instance exists"""
        with self._lock:
            return instance_id in self._instances

    def is_instance_approved(self, instance_id: str) -> bool:
        """Check if instance is approved"""
        with self._lock:
            inst = self._instances.get(instance_id)
            return inst is not None and inst.get('approved', False)

    # ==================== Stats ====================

    def get_stats(self) -> Dict:
        """Get statistics"""
        with self._lock:
            return {
                'thoughts': len(self._thoughts),
                'skills': len(self._skills),
                'instances': len(self._instances),
                'approved_instances': len([i for i in self._instances.values() if i.get('approved')]),
                'pending_instances': len([i for i in self._instances.values() if not i.get('approved')]),
            }

    # ==================== Client Keys ====================

    def get_client_keys(self) -> Dict[str, str]:
        """Get persisted client API keys"""
        with self._lock:
            return dict(self._client_keys)

    def save_client_key(self, instance_id: str, api_key: str) -> None:
        """Persist client API key (thread-safe)"""
        with self._lock:
            self._client_keys[instance_id] = api_key
            self._save_file('client_keys.json', self._client_keys)

    def remove_client_key(self, instance_id: str) -> bool:
        """Remove persisted client API key"""
        with self._lock:
            if instance_id in self._client_keys:
                del self._client_keys[instance_id]
                self._save_file('client_keys.json', self._client_keys)
                return True
        return False

    # ==================== Replica Operations ====================

    def replica_store(self, data_id: str, data_type: str, content: Dict) -> bool:
        """Store replica data (inter-node calls)"""
        with self._lock:
            # Normalize: use data_id as the id field of content
            if 'id' not in content:
                content['id'] = data_id

            if data_type == 'thought':
                for i, t in enumerate(self._thoughts):
                    if t.get('id') == data_id:
                        self._thoughts[i] = content
                        self._save_file('thoughts.json', self._thoughts)
                        return True
                self._thoughts.append(content)
                self._save_file('thoughts.json', self._thoughts)
                return True
            elif data_type == 'skill':
                for i, s in enumerate(self._skills):
                    if s.get('id') == data_id:
                        self._skills[i] = content
                        self._save_file('skills.json', self._skills)
                        return True
                self._skills.append(content)
                self._save_file('skills.json', self._skills)
                return True
        return False

    def replica_get(self, data_id: str) -> Optional[Dict]:
        """Get replica data"""
        with self._lock:
            # Search in thoughts
            for t in self._thoughts:
                if t.get('id') == data_id:
                    return {'data_type': 'thought', 'content': t, 'found': True}
            # Search in skills
            for s in self._skills:
                if s.get('id') == data_id:
                    return {'data_type': 'skill', 'content': s, 'found': True}
        return None

    def get_all_for_sync(self) -> Dict:
        """Get all data for node synchronization"""
        with self._lock:
            return {
                'thoughts': list(self._thoughts),
                'skills': list(self._skills),
            }

    # ==================== Context Manager ====================

    def acquire_lock(self):
        """Acquire lock (for scenarios requiring long operations inside the lock)"""
        return self._lock

    def __enter__(self):
        self._lock.acquire()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._lock.release()
        return False
