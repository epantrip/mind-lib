"""
Mind Library - Data Persistence Module

Provides file-based storage for:
- Routing cache
- Instance tokens  
- Cluster state
"""

import os
import json
import time
import hashlib
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime

logger = logging.getLogger(__name__)


class PersistenceManager:
    """
    Manages persistent storage for distributed state
    
    Thread-safe file operations with atomic writes
    """
    
    def __init__(self, data_dir: str = "/root/mind_library/persist"):
        self.data_dir = data_dir
        os.makedirs(data_dir, exist_ok=True)
        
        # File paths
        self.routing_cache_file = os.path.join(data_dir, "routing_cache.json")
        self.cluster_state_file = os.path.join(data_dir, "cluster_state.json")
        self.metrics_file = os.path.join(data_dir, "metrics.json")
        
        logger.info(f"Persistence initialized at {data_dir}")
    
    def _atomic_write(self, filepath: str, data: Any) -> bool:
        """Write data atomically using temp file"""
        temp_path = filepath + ".tmp"
        try:
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            # Atomic rename
            os.replace(temp_path, filepath)
            return True
        except Exception as e:
            logger.error(f"Write failed: {e}")
            if os.path.exists(temp_path):
                os.remove(temp_path)
            return False
    
    def _safe_read(self, filepath: str, default: Any = None) -> Any:
        """Read data safely with default fallback"""
        if not os.path.exists(filepath):
            return default
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Read failed: {e}")
            return default
    
    # ==================== Routing Cache ====================
    
    def save_routing_cache(self, cache: Dict[str, tuple]) -> bool:
        """Save routing cache (data_id -> (primary, [replicas]))"""
        # Convert tuple to list for JSON
        data = {
            k: {"primary": v[0], "replicas": v[1]}
            for k, v in cache.items()
        }
        data['_metadata'] = {
            'saved_at': datetime.now().isoformat(),
            'count': len(cache)
        }
        return self._atomic_write(self.routing_cache_file, data)
    
    def load_routing_cache(self) -> Dict[str, tuple]:
        """Load routing cache"""
        data = self._safe_read(self.routing_cache_file, {})
        
        cache = {}
        for k, v in data.items():
            if k == '_metadata':
                continue
            cache[k] = (v['primary'], v['replicas'])
        
        if cache:
            logger.info(f"Loaded {len(cache)} routing entries")
        return cache
    
    # ==================== Cluster State ====================
    
    def save_cluster_state(self, nodes: List[Dict], stats: Dict) -> bool:
        """Save cluster state snapshot"""
        data = {
            'nodes': nodes,
            'stats': stats,
            'saved_at': datetime.now().isoformat(),
            'version': '2.1.0'
        }
        return self._atomic_write(self.cluster_state_file, data)
    
    def load_cluster_state(self) -> Optional[Dict]:
        """Load cluster state"""
        return self._safe_read(self.cluster_state_file)
    
    # ==================== Metrics ====================
    
    def save_metrics(self, metrics: Dict) -> bool:
        """Save performance metrics"""
        metrics['saved_at'] = datetime.now().isoformat()
        return self._atomic_write(self.metrics_file, metrics)
    
    def load_metrics(self) -> Dict:
        """Load metrics history"""
        return self._safe_read(self.metrics_file, {
            'total_requests': 0,
            'successful_requests': 0,
            'failed_requests': 0,
            'avg_latency_ms': 0,
            'cache_hits': 0,
            'cache_misses': 0
        })
    
    # ==================== Cleanup ====================
    
    def cleanup_old_data(self, max_age_days: int = 30) -> int:
        """Remove old persisted data"""
        cleaned = 0
        now = time.time()
        
        for filename in os.listdir(self.data_dir):
            filepath = os.path.join(self.data_dir, filename)
            if os.path.isfile(filepath):
                file_age = now - os.path.getmtime(filepath)
                if file_age > max_age_days * 86400:
                    os.remove(filepath)
                    cleaned += 1
        
        if cleaned:
            logger.info(f"Cleaned {cleaned} old files")
        return cleaned


class RoutingCacheManager:
    """
    Manages routing cache with persistence
    
    Provides:
    - In-memory cache for fast access
    - Background persistence
    - Recovery on restart
    """
    
    def __init__(self, persist_dir: str = None):
        self.persist_dir = persist_dir or os.environ.get(
            'MIND_PERSIST_DIR', 
            '/root/mind_library/persist'
        )
        self.persistence = PersistenceManager(self.persist_dir)
        
        # In-memory cache
        self.cache: Dict[str, tuple] = {}
        
        # Load persisted cache
        self._load_cache()
        
        # Auto-save interval (seconds)
        self.auto_save_interval = 60
        self.last_save = time.time()
    
    def _load_cache(self):
        """Load cache from disk"""
        loaded = self.persistence.load_routing_cache()
        if loaded:
            self.cache = loaded
            logger.info(f"Routing cache restored: {len(self.cache)} entries")
    
    def get(self, data_id: str) -> Optional[tuple]:
        """Get routing info from cache"""
        return self.cache.get(data_id)
    
    def set(self, data_id: str, routing: tuple):
        """Set routing info in cache"""
        self.cache[data_id] = routing
        
        # Auto-save if interval elapsed
        if time.time() - self.last_save > self.auto_save_interval:
            self.save()
    
    def remove(self, data_id: str):
        """Remove entry from cache"""
        self.cache.pop(data_id, None)
    
    def save(self) -> bool:
        """Save cache to disk"""
        self.last_save = time.time()
        return self.persistence.save_routing_cache(self.cache)
    
    def clear(self):
        """Clear in-memory cache"""
        self.cache.clear()
    
    def get_stats(self) -> Dict:
        """Get cache statistics"""
        return {
            'entries': len(self.cache),
            'persisted': os.path.exists(
                self.persistence.routing_cache_file
            )
        }


# Test
if __name__ == "__main__":
    pm = PersistenceManager("/tmp/mind_test_persist")
    
    # Test routing cache
    test_cache = {
        "thought_001": ("node_001", ["node_002", "node_003"]),
        "thought_002": ("node_002", ["node_001", "node_003"]),
    }
    
    pm.save_routing_cache(test_cache)
    loaded = pm.load_routing_cache()
    
    print("Routing Cache Test:")
    print(f"  Saved: {len(test_cache)} entries")
    print(f"  Loaded: {len(loaded)} entries")
    print(f"  Match: {test_cache == loaded}")
    
    print("\nPersistence module ready")
