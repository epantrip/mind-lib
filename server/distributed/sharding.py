"""
🧠 一致性哈希分片 - 分布式存储的核心算法
"""

import hashlib
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
import bisect


@dataclass
class Node:
    """存储节点"""
    node_id: str
    host: str
    port: int
    weight: int = 100  # 权重，用于负载均衡
    status: str = "online"  # online, offline, recovering
    storage_used_gb: float = 0
    storage_limit_gb: float = 10


class ConsistentHashRing:
    """
    一致性哈希环
    
    使用 Ketama 算法：
    - 每个物理节点映射到 150 个虚拟节点
    - 虚拟节点均匀分布在哈希环上
    - 新节点加入只需迁移 1/N 的数据
    """
    
    def __init__(self, virtual_nodes: int = 150):
        self.virtual_nodes = virtual_nodes
        self.ring: Dict[int, str] = {}  # 哈希值 -> 节点ID
        self.sorted_keys: List[int] = []  # 排序的哈希值列表
        self.nodes: Dict[str, Node] = {}  # 节点ID -> Node对象
        
    def _hash(self, key: str) -> int:
        """计算哈希值"""
        return int(hashlib.md5(key.encode()).hexdigest(), 16)
    
    def add_node(self, node: Node) -> None:
        """添加节点"""
        self.nodes[node.node_id] = node
        
        # 为每个节点创建虚拟节点
        for i in range(node.weight * self.virtual_nodes // 100):
            virtual_key = f"{node.node_id}:{i}"
            hash_value = self._hash(virtual_key)
            self.ring[hash_value] = node.node_id
            
        self._rebuild_sorted_keys()
        
    def remove_node(self, node_id: str) -> None:
        """移除节点"""
        if node_id not in self.nodes:
            return
            
        # 移除所有虚拟节点
        node = self.nodes[node_id]
        for i in range(node.weight * self.virtual_nodes // 100):
            virtual_key = f"{node_id}:{i}"
            hash_value = self._hash(virtual_key)
            self.ring.pop(hash_value, None)
            
        del self.nodes[node_id]
        self._rebuild_sorted_keys()
        
    def _rebuild_sorted_keys(self) -> None:
        """重建排序的哈希值列表"""
        self.sorted_keys = sorted(self.ring.keys())
        
    def get_primary_node(self, key: str) -> Optional[str]:
        """获取主节点"""
        if not self.ring:
            return None
            
        hash_value = self._hash(key)
        
        # 找到顺时针方向第一个节点
        idx = bisect.bisect(self.sorted_keys, hash_value)
        if idx >= len(self.sorted_keys):
            idx = 0
            
        return self.ring[self.sorted_keys[idx]]
    
    def get_replica_nodes(self, key: str, replication_factor: int = 3) -> List[str]:
        """
        获取副本节点列表
        
        策略：主节点 + 顺时针后 N-1 个不同的节点
        确保副本分布在不同物理节点上
        """
        if not self.ring:
            return []
            
        primary = self.get_primary_node(key)
        if not primary:
            return []
            
        hash_value = self._hash(key)
        idx = bisect.bisect(self.sorted_keys, hash_value)
        
        nodes = [primary]
        seen_physical = {self._get_physical_node(primary)}
        
        # 顺时针遍历
        for _ in range(len(self.sorted_keys)):
            idx = (idx + 1) % len(self.sorted_keys)
            node_id = self.ring[self.sorted_keys[idx]]
            
            physical = self._get_physical_node(node_id)
            if physical not in seen_physical:
                nodes.append(node_id)
                seen_physical.add(physical)
                
            if len(nodes) >= replication_factor:
                break
                
        return nodes
    
    def _get_physical_node(self, virtual_node_id: str) -> str:
        """从虚拟节点ID获取物理节点ID"""
        return virtual_node_id.split(":")[0]
    
    def get_all_nodes(self) -> List[Node]:
        """获取所有在线节点"""
        return [n for n in self.nodes.values() if n.status == "online"]
    
    def get_node(self, node_id: str) -> Optional[Node]:
        """获取节点"""
        return self.nodes.get(node_id)
    
    def update_node_status(self, node_id: str, status: str) -> None:
        """更新节点状态"""
        if node_id in self.nodes:
            self.nodes[node_id].status = status
            
    def update_node_storage(self, node_id: str, used_gb: float) -> None:
        """更新节点存储使用"""
        if node_id in self.nodes:
            self.nodes[node_id].storage_used_gb = used_gb
    
    def get_stats(self) -> Dict:
        """获取统计信息"""
        total_storage = sum(n.storage_limit_gb for n in self.nodes.values())
        used_storage = sum(n.storage_used_gb for n in self.nodes.values())
        
        return {
            "total_nodes": len(self.nodes),
            "online_nodes": len(self.get_all_nodes()),
            "virtual_nodes_per_physical": self.virtual_nodes,
            "total_virtual_nodes": len(self.ring),
            "total_storage_gb": total_storage,
            "used_storage_gb": used_storage,
            "usage_percent": (used_storage / total_storage * 100) if total_storage > 0 else 0,
        }
    
    def estimate_migration(self, new_node: Node) -> Dict[str, float]:
        """
        估算新增节点需要迁移的数据量
        
        返回：{old_node_id: 数据量百分比}
        """
        if not self.nodes:
            return {}
            
        # 模拟添加新节点后的分布
        old_distribution = {}
        for node_id in self.nodes:
            old_distribution[node_id] = 0
            
        # 统计每个物理节点负责的虚拟节点比例
        total_vnodes = len(self.ring)
        vnode_counts = {}
        
        for hash_value, node_id in self.ring.items():
            physical = self._get_physical_node(node_id)
            vnode_counts[physical] = vnode_counts.get(physical, 0) + 1
            
        for node_id, count in vnode_counts.items():
            if node_id in old_distribution:
                old_distribution[node_id] = count / total_vnodes
                
        # 新节点加入后的分布（假设权重100）
        new_distribution = old_distribution.copy()
        new_share = 1 / (len(self.nodes) + 1)
        new_distribution[new_node.node_id] = new_share
        
        # 估算迁移量
        migration = {}
        for node_id in old_distribution:
            change = old_distribution[node_id] - new_share
            if change > 0:
                migration[node_id] = change * 100  # 百分比
                
        return migration


# 测试
if __name__ == "__main__":
    # 创建哈希环
    ring = ConsistentHashRing(virtual_nodes=150)
    
    # 添加节点
    nodes = [
        Node("node_001", "192.168.1.1", 5001),
        Node("node_002", "192.168.1.2", 5001),
        Node("node_003", "192.168.1.3", 5001),
    ]
    
    for node in nodes:
        ring.add_node(node)
        
    # 测试路由
    test_keys = [f"thought_{i}" for i in range(10)]
    
    print("🎃 一致性哈希环测试")
    print("=" * 50)
    
    for key in test_keys:
        primary = ring.get_primary_node(key)
        replicas = ring.get_replica_nodes(key, 3)
        print(f"{key}: 主节点={primary}, 副本={replicas}")
        
    print("\n📊 统计信息:")
    print(ring.get_stats())