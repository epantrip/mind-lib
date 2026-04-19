"""
Mind Library - Consistent Hash Sharding
Core algorithm for distributed storage
"""

import hashlib
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
import bisect


@dataclass
class Node:
    """Storage node"""
    node_id: str
    host: str
    port: int
    weight: int = 100  # Weight for load balancing
    status: str = "online"  # online, offline, recovering
    storage_used_gb: float = 0
    storage_limit_gb: float = 10


class ConsistentHashRing:
    """
    Consistent Hash Ring

    Uses Ketama algorithm:
    - Each physical node maps to 150 virtual nodes
    - Virtual nodes evenly distributed on the hash ring
    - New node join only migrates 1/N of data
    """

    def __init__(self, virtual_nodes: int = 150):
        self.virtual_nodes = virtual_nodes
        self.ring: Dict[int, str] = {}  # hash_value -> node_id
        self.sorted_keys: List[int] = []  # sorted hash values
        self.nodes: Dict[str, Node] = {}  # node_id -> Node object

    def _hash(self, key: str) -> int:
        """Calculate hash value"""
        return int(hashlib.md5(key.encode()).hexdigest(), 16)

    def add_node(self, node: Node) -> None:
        """Add a node"""
        self.nodes[node.node_id] = node
        # Create virtual nodes for this node
        for i in range(node.weight * self.virtual_nodes // 100):
            virtual_key = f"{node.node_id}:{i}"
            hash_value = self._hash(virtual_key)
            self.ring[hash_value] = node.node_id
        self._rebuild_sorted_keys()

    def remove_node(self, node_id: str) -> None:
        """Remove a node"""
        if node_id not in self.nodes:
            return
        node = self.nodes[node_id]
        # Remove all virtual nodes
        for i in range(node.weight * self.virtual_nodes // 100):
            virtual_key = f"{node_id}:{i}"
            hash_value = self._hash(virtual_key)
            self.ring.pop(hash_value, None)
        del self.nodes[node_id]
        self._rebuild_sorted_keys()

    def _rebuild_sorted_keys(self) -> None:
        """Rebuild sorted hash value list"""
        self.sorted_keys = sorted(self.ring.keys())

    def get_primary_node(self, key: str) -> Optional[str]:
        """Get primary node"""
        if not self.ring:
            return None
        hash_value = self._hash(key)
        # Find first node in clockwise direction
        idx = bisect.bisect(self.sorted_keys, hash_value)
        if idx >= len(self.sorted_keys):
            idx = 0
        return self.ring[self.sorted_keys[idx]]

    def get_replica_nodes(self, key: str, replication_factor: int = 3) -> List[str]:
        """
        Get replica node list

        Strategy: primary + next N-1 distinct nodes clockwise
        Ensures replicas are distributed across different physical nodes
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
        # Clockwise traversal
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
        """Get physical node ID from virtual node ID"""
        return virtual_node_id.split(":")[0]

    def get_all_nodes(self) -> List[Node]:
        """Get all online nodes"""
        return [n for n in self.nodes.values() if n.status == "online"]

    def get_node(self, node_id: str) -> Optional[Node]:
        """Get a node"""
        return self.nodes.get(node_id)

    def update_node_status(self, node_id: str, status: str) -> None:
        """Update node status"""
        if node_id in self.nodes:
            self.nodes[node_id].status = status

    def update_node_storage(self, node_id: str, used_gb: float) -> None:
        """Update node storage usage"""
        if node_id in self.nodes:
            self.nodes[node_id].storage_used_gb = used_gb

    def get_stats(self) -> Dict:
        """Get statistics"""
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
        Estimate data volume to migrate when adding a new node

        Returns: {old_node_id: data volume percentage}
        """
        if not self.nodes:
            return {}
        # Simulate distribution after adding new node
        old_distribution = {}
        for node_id in self.nodes:
            old_distribution[node_id] = 0
        # Count virtual node ratio per physical node
        total_vnodes = len(self.ring)
        vnode_counts = {}
        for hash_value, node_id in self.ring.items():
            physical = self._get_physical_node(node_id)
            vnode_counts[physical] = vnode_counts.get(physical, 0) + 1
        for node_id, count in vnode_counts.items():
            if node_id in old_distribution:
                old_distribution[node_id] = count / total_vnodes
        # New distribution after node joins (weight=100 assumed)
        new_distribution = old_distribution.copy()
        new_share = 1 / (len(self.nodes) + 1)
        new_distribution[new_node.node_id] = new_share
        # Estimate migration
        migration = {}
        for node_id in old_distribution:
            change = old_distribution[node_id] - new_share
            if change > 0:
                migration[node_id] = change * 100  # percentage
        return migration


# Tests
if __name__ == "__main__":
    ring = ConsistentHashRing(virtual_nodes=150)
    nodes = [
        Node("node_001", "192.168.1.1", 5001),
        Node("node_002", "192.168.1.2", 5001),
        Node("node_003", "192.168.1.3", 5001),
    ]
    for node in nodes:
        ring.add_node(node)
    test_keys = [f"thought_{i}" for i in range(10)]
    print("[ConsistentHashRing] Test run")
    print("=" * 50)
    for key in test_keys:
        primary = ring.get_primary_node(key)
        replicas = ring.get_replica_nodes(key, 3)
        print(f"{key}: Primary={primary}, Replicas={replicas}")
    print("\n[Stats]:")
    print(ring.get_stats())
