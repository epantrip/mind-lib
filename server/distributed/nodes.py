"""
Mind Library - Distributed Node Management
"""

import time
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from enum import Enum
import requests
import logging

logger = logging.getLogger(__name__)


class NodeStatus(Enum):
    """Node status"""
    ONLINE = "online"
    OFFLINE = "offline"
    RECOVERING = "recovering"
    JOINING = "joining"
    LEAVING = "leaving"


@dataclass
class ClusterNode:
    """Cluster node"""
    node_id: str
    host: str
    port: int
    status: NodeStatus = NodeStatus.ONLINE
    last_heartbeat: float = field(default_factory=time.time)
    storage_used_gb: float = 0
    storage_limit_gb: float = 10
    cpu_usage: float = 0
    memory_usage: float = 0
    request_count: int = 0
    error_count: int = 0

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}"

    @property
    def storage_usage_percent(self) -> float:
        if self.storage_limit_gb == 0:
            return 0
        return (self.storage_used_gb / self.storage_limit_gb) * 100

    def is_healthy(self, failure_threshold: int = 3, heartbeat_interval: int = 5) -> bool:
        """Check if node is healthy"""
        if self.status != NodeStatus.ONLINE:
            return False
        time_since_heartbeat = time.time() - self.last_heartbeat
        return time_since_heartbeat < (failure_threshold * heartbeat_interval)


class NodeManager:
    """
    Node Manager

    Responsibilities:
    - Node registration/unregistration
    - Heartbeat detection
    - Health checks
    - Failure detection and recovery
    """

    def __init__(self, heartbeat_interval: int = 5, failure_threshold: int = 3,
                 storage_limit_gb: int = 10):
        self.nodes: Dict[str, ClusterNode] = {}
        self.heartbeat_interval = heartbeat_interval
        self.failure_threshold = failure_threshold
        self.storage_limit_gb = storage_limit_gb

    def register_node(self, node_id: str, host: str, port: int) -> ClusterNode:
        """Register a new node"""
        node = ClusterNode(
            node_id=node_id, host=host, port=port,
            status=NodeStatus.ONLINE, storage_limit_gb=self.storage_limit_gb,
        )
        self.nodes[node_id] = node
        logger.info(f"[NodeManager] Node registered: {node_id} @ {host}:{port}")
        return node

    def unregister_node(self, node_id: str) -> bool:
        """Unregister a node"""
        if node_id in self.nodes:
            del self.nodes[node_id]
            logger.info(f"[NodeManager] Node unregistered: {node_id}")
            return True
        return False

    def heartbeat(self, node_id: str, storage_used_gb: Optional[float] = None) -> bool:
        """Node heartbeat"""
        if node_id not in self.nodes:
            return False
        node = self.nodes[node_id]
        node.last_heartbeat = time.time()
        node.status = NodeStatus.ONLINE
        if storage_used_gb is not None:
            node.storage_used_gb = storage_used_gb
        return True

    def get_online_nodes(self) -> List[ClusterNode]:
        """Get all online nodes"""
        return [n for n in self.nodes.values() if n.status == NodeStatus.ONLINE]

    def get_healthy_nodes(self) -> List[ClusterNode]:
        """Get healthy nodes (online and not storage-full)"""
        return [n for n in self.get_online_nodes() if n.storage_usage_percent < 80]

    def get_node(self, node_id: str) -> Optional[ClusterNode]:
        """Get a node"""
        return self.nodes.get(node_id)

    def check_node_health(self, node_id: str) -> bool:
        """Check node health status"""
        node = self.nodes.get(node_id)
        if not node:
            return False
        return node.is_healthy(self.failure_threshold, self.heartbeat_interval)

    def health_check_all(self) -> Dict[str, bool]:
        """Run health checks on all nodes (synchronous)"""
        results = {}
        for node_id, node in self.nodes.items():
            try:
                resp = requests.get(
                    f"{node.url}/api/health",
                    timeout=5, headers={"Accept": "application/json"}
                )
                results[node_id] = resp.status_code == 200
            except Exception:
                results[node_id] = False
                node.status = NodeStatus.OFFLINE
        return results

    def mark_node_failed(self, node_id: str) -> None:
        """Mark node as failed"""
        if node_id in self.nodes:
            self.nodes[node_id].status = NodeStatus.OFFLINE
            logger.warning(f"[NodeManager] Node failed: {node_id}")

    def mark_node_recovering(self, node_id: str) -> None:
        """Mark node as recovering"""
        if node_id in self.nodes:
            self.nodes[node_id].status = NodeStatus.RECOVERING
            logger.info(f"[NodeManager] Node recovering: {node_id}")

    def get_cluster_stats(self) -> Dict:
        """Get cluster statistics"""
        online = self.get_online_nodes()
        healthy = self.get_healthy_nodes()
        total_storage = sum(n.storage_limit_gb for n in self.nodes.values())
        used_storage = sum(n.storage_used_gb for n in self.nodes.values())
        return {
            "total_nodes": len(self.nodes),
            "online_nodes": len(online),
            "healthy_nodes": len(healthy),
            "offline_nodes": len(self.nodes) - len(online),
            "total_storage_gb": total_storage,
            "used_storage_gb": used_storage,
            "storage_usage_percent": (used_storage / total_storage * 100) if total_storage > 0 else 0,
            "nodes": [
                {"node_id": n.node_id, "host": n.host, "port": n.port,
                 "status": n.status.value, "storage_used_gb": n.storage_used_gb,
                 "storage_usage_percent": n.storage_usage_percent}
                for n in self.nodes.values()
            ]
        }

    def suggest_nodes_to_add(self, target_replication: int = 3) -> int:
        """
        Suggest number of nodes to add

        Based on current node count and target replication factor
        """
        current_nodes = len(self.get_online_nodes())
        if current_nodes >= target_replication:
            return 0
        return target_replication - current_nodes


# Tests
if __name__ == "__main__":
    manager = NodeManager(heartbeat_interval=5, failure_threshold=3)
    manager.register_node("node_001", "192.168.1.1", 5001)
    manager.register_node("node_002", "192.168.1.2", 5001)
    manager.register_node("node_003", "192.168.1.3", 5001)
    manager.heartbeat("node_001", storage_used_gb=3.5)
    manager.heartbeat("node_002", storage_used_gb=4.2)
    manager.heartbeat("node_003", storage_used_gb=2.8)
    print("[NodeManager] Test run")
    print("=" * 50)
    stats = manager.get_cluster_stats()
    print(f"Total nodes: {stats['total_nodes']}")
    print(f"Online: {stats['online_nodes']}")
    print(f"Healthy: {stats['healthy_nodes']}")
    print(f"Storage: {stats['used_storage_gb']:.1f}GB / {stats['total_storage_gb']:.1f}GB ({stats['storage_usage_percent']:.1f}%)")
    print("\nNode details:")
    for node in stats["nodes"]:
        print(f"  - {node['node_id']}: {node['host']}:{node['port']} | Storage: {node['storage_used_gb']:.1f}GB ({node['storage_usage_percent']:.1f}%)")
