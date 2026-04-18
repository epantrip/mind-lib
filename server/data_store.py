"""
🧠 Mind Library - 线程安全数据存储层

P0: 并发安全
- 使用 RLock 保护 thoughts/skills/instances 的读写
- 锁只包内存操作 + 本地磁盘 I/O，网络 I/O 放锁外
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
    线程安全的数据存储层
    
    设计原则：
    1. 锁只包内存读写 + 本地磁盘写入（毫秒级）
    2. 网络 I/O（同步、webhook）必须在锁外调用
    3. 读取操作也要加锁，防止读到部分写入的数据
    """
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        os.makedirs(db_path, exist_ok=True)
        
        # 线程锁 - 保护所有数据操作
        self._lock = threading.RLock()
        
        # 内存缓存
        self._thoughts: List[Dict] = []
        self._skills: List[Dict] = []
        self._instances: Dict[str, Dict] = {}
        
        # 加载数据
        self._load_all()
    
    # ==================== 私有方法 ====================
    
    def _load_all(self) -> None:
        """加载所有数据"""
        self._thoughts = self._load_file('thoughts.json', [])
        self._skills = self._load_file('skills.json', [])
        self._instances = self._load_file('instances.json', {})
        
        # 兼容 v2.0 目录式存储
        self._load_compat_directory()
        
        logger.info(f"📂 数据加载完成: {len(self._thoughts)} 思想, {len(self._skills)} 技能, {len(self._instances)} 实例")
    
    def _load_file(self, filename: str, default: Any) -> Any:
        """加载单个数据文件"""
        path = os.path.join(self.db_path, filename)
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"加载 {filename} 失败: {e}")
        return default
    
    def _load_compat_directory(self) -> None:
        """兼容 v2.0 目录式存储"""
        # instances: 从 instances/ 目录加载
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
        
        # thoughts: 从 thoughts/ 目录加载
        thoughts_dir = os.path.join(self.db_path, 'thoughts')
        if os.path.isdir(thoughts_dir):
            for fname in sorted(os.listdir(thoughts_dir)):
                if fname.endswith('.json'):
                    try:
                        with open(os.path.join(thoughts_dir, fname), 'r', encoding='utf-8') as f:
                            self._thoughts.append(json.load(f))
                    except Exception:
                        pass
        
        # skills: 从 skills/ 目录加载
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
        """保存数据到文件"""
        # 兼容 v2.0 目录式存储
        if filename == 'instances.json' and isinstance(data, dict):
            self._save_directory('instances', data)
            return
        if filename in ('thoughts.json', 'skills.json') and isinstance(data, list):
            self._save_directory(filename.replace('.json', ''), data)
            return
        
        # 默认 JSON 文件
        path = os.path.join(self.db_path, filename)
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存 {filename} 失败: {e}")
    
    def _save_directory(self, dir_name: str, data: Any) -> None:
        """保存到目录（v2.0 兼容）"""
        dir_path = os.path.join(self.db_path, dir_name)
        os.makedirs(dir_path, exist_ok=True)
        
        if isinstance(data, dict):
            # instances: 每个实例一个文件
            for iid, inst_data in data.items():
                try:
                    fname = f"{iid}.json"
                    with open(os.path.join(dir_path, fname), 'w', encoding='utf-8') as f:
                        json.dump(inst_data, f, ensure_ascii=False, indent=2)
                except Exception as e:
                    logger.error(f"保存实例 {iid} 失败: {e}")
        elif isinstance(data, list):
            # thoughts/skills: 每个条目一个文件
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
                    logger.error(f"保存到 {fname} 失败: {e}")
    
    # ==================== Thoughts ====================
    
    def get_thoughts(self, since: str = '', thought_type: str = None) -> List[Dict]:
        """获取思想列表（线程安全）"""
        with self._lock:
            result = [t for t in self._thoughts if t.get('created_at', '') > since]
            if thought_type:
                result = [t for t in result if t.get('type') == thought_type]
            return result
    
    def get_all_thoughts(self) -> List[Dict]:
        """获取所有思想"""
        with self._lock:
            return list(self._thoughts)
    
    def add_thought(self, thought: Dict) -> Dict:
        """添加思想（线程安全）"""
        with self._lock:
            self._thoughts.append(thought)
            self._save_file('thoughts.json', self._thoughts)
        return thought
    
    def update_thought(self, thought_id: str, thought: Dict) -> bool:
        """更新思想"""
        with self._lock:
            for i, t in enumerate(self._thoughts):
                if t.get('id') == thought_id:
                    self._thoughts[i] = thought
                    self._save_file('thoughts.json', self._thoughts)
                    return True
        return False
    
    # ==================== Skills ====================
    
    def get_skills(self) -> List[Dict]:
        """获取技能列表（线程安全）"""
        with self._lock:
            return list(self._skills)
    
    def add_skill(self, skill: Dict) -> Dict:
        """添加技能（线程安全）"""
        with self._lock:
            # 更新已存在的技能
            for i, s in enumerate(self._skills):
                if s.get('name') == skill['name']:
                    self._skills[i] = skill
                    self._save_file('skills.json', self._skills)
                    return skill
            # 新增
            self._skills.append(skill)
            self._save_file('skills.json', self._skills)
        return skill
    
    def update_skill(self, skill_id: str, skill: Dict) -> bool:
        """更新技能"""
        with self._lock:
            for i, s in enumerate(self._skills):
                if s.get('id') == skill_id:
                    self._skills[i] = skill
                    self._save_file('skills.json', self._skills)
                    return True
        return False
    
    # ==================== Instances ====================
    
    def get_instances(self) -> Dict[str, Dict]:
        """获取所有实例"""
        with self._lock:
            return dict(self._instances)
    
    def get_instance(self, instance_id: str) -> Optional[Dict]:
        """获取单个实例"""
        with self._lock:
            return self._instances.get(instance_id)
    
    def add_instance(self, instance: Dict) -> Dict:
        """添加实例（线程安全）"""
        with self._lock:
            instance_id = instance.get('id') or instance.get('instance_id')
            self._instances[instance_id] = instance
            self._save_file('instances.json', self._instances)
        return instance
    
    def update_instance(self, instance_id: str, updates: Dict) -> bool:
        """更新实例"""
        with self._lock:
            if instance_id in self._instances:
                self._instances[instance_id].update(updates)
                self._save_file('instances.json', self._instances)
                return True
        return False
    
    def delete_instance(self, instance_id: str) -> bool:
        """删除实例"""
        with self._lock:
            if instance_id in self._instances:
                del self._instances[instance_id]
                self._save_file('instances.json', self._instances)
                return True
        return False
    
    def instance_exists(self, instance_id: str) -> bool:
        """检查实例是否存在"""
        with self._lock:
            return instance_id in self._instances
    
    def is_instance_approved(self, instance_id: str) -> bool:
        """检查实例是否已批准"""
        with self._lock:
            inst = self._instances.get(instance_id)
            return inst is not None and inst.get('approved', False)
    
    # ==================== Stats ====================
    
    def get_stats(self) -> Dict:
        """获取统计信息"""
        with self._lock:
            return {
                'thoughts': len(self._thoughts),
                'skills': len(self._skills),
                'instances': len(self._instances),
                'approved_instances': len([i for i in self._instances.values() if i.get('approved')]),
                'pending_instances': len([i for i in self._instances.values() if not i.get('approved')]),
            }
    
    # ==================== Replica Operations ====================
    
    def replica_store(self, data_id: str, data_type: str, content: Dict) -> bool:
        """存储副本数据（节点间调用）"""
        with self._lock:
            # 规范化：将 data_id 作为内容的 id 字段
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
        """获取副本数据"""
        with self._lock:
            # 在思想中查找
            for t in self._thoughts:
                if t.get('id') == data_id:
                    return {'data_type': 'thought', 'content': t, 'found': True}
            # 在技能中查找
            for s in self._skills:
                if s.get('id') == data_id:
                    return {'data_type': 'skill', 'content': s, 'found': True}
        return None
    
    def get_all_for_sync(self) -> Dict:
        """获取全部数据供节点同步"""
        with self._lock:
            return {
                'thoughts': list(self._thoughts),
                'skills': list(self._skills),
            }
    
    # ==================== Context Manager ====================
    
    def acquire_lock(self):
        """获取锁（用于需要长时间在锁内操作的场景）"""
        return self._lock
    
    def __enter__(self):
        self._lock.acquire()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self._lock.release()
        return False
