"""
Mind Library - Distributed Coordinator (P2: Rebalance + Repair)

Incremental changes:
1. _data_ownership: Dict[str, Set[str]] — data_id -> set of nodes holding this data
2. _record_ownership(data_id, nodes): records after each write
3. _trigger_rebalance(node_id): new node pulls data it should own from old nodes
4. _repair_after_node_leave(node_id): data from leaving node is replicated to healthy nodes
5. /api/replica/migrate endpoint: inter-node data migration
"""

import hashlib
import json
import time
import os
from typing import Dict, List, Optional, Set, Any
from dataclasses import dataclass, field
from enum import Enum
import logging

from .sharding import ConsistentHashRing, Node
from .nodes import NodeManager, ClusterNode, NodeStatus
from .replication import ReplicationManager, ReplicationStatus
from .persistence import RoutingCacheManager
from . import config

logger = logging.getLogger(__name__)


class CoordinatorStatus(Enum):
    STANDBY = "standby"
    ACTIVE = "active"
    RECOVERING = "recovering"


@dataclass
class Operation:
    op_id: str
    op_type: str
    data_id: str
    timestamp: float
    status: str
    node_selected: str
    latency_ms: float = 0
    error: Optional[str] = None


class DistributedCoordinator:
    """
    Distributed Coordinator

    P2 additions:
    - Data ownership tracking (_data_ownership)
    - Data rebalancing on node join
    - Replica repair after node leave
    """

    def __init__(
        self,
        node_id: str = "coordinator_001",
        replication_factor: int = 3,
    ):
        self.node_id = node_id
        self.replication_factor = replication_factor
        self.status = CoordinatorStatus.ACTIVE

        self.hash_ring = ConsistentHashRing(
            virtual_nodes=config.CLUSTER_CONFIG["virtual_nodes"]
        )
        self.node_manager = NodeManager(
            heartbeat_interval=config.CLUSTER_CONFIG["heartbeat_interval"],
            failure_threshold=config.CLUSTER_CONFIG["failure_threshold"],
            storage_limit_gb=config.CLUSTER_CONFIG["storage_limit_gb"],
        )
        self.replication_manager = ReplicationManager(
            replication_factor=replication_factor,
        )

        # P2: Data ownership tracking
        # key = data_id, value = set of nodes holding this data
        self._data_ownership: Dict[str, Set[str]] = {}

        # Operation records
        self.operations: List[Operation] = []
        self.max_operations = 10000

        # Monitoring metrics
        self.metrics = {
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "avg_latency_ms": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            # P2 additions
            "rebalance_triggered": 0,
            "rebalance_success": 0,
            "repair_triggered": 0,
            "repair_success": 0,
        }

        persist_dir = os.environ.get('MIND_PERSIST_DIR')
        self.routing_cache = RoutingCacheManager(persist_dir)

    # ==================== Node Management ====================

    def add_node(self, node_id: str, host: str, port: int) -> bool:
        """Add a storage node"""
        self.node_manager.register_node(node_id, host, port)
        node = Node(node_id, host, port)
        self.hash_ring.add_node(node)

        logger.info(f"[Coordinator] Node added: {node_id} @ {host}:{port}")

        # P2: Trigger data rebalancing
        if config.CLUSTER_CONFIG["auto_rebalance"]:
            self._trigger_rebalance(node_id)

        return True

    def remove_node(self, node_id: str) -> bool:
        """Remove a storage node"""
        self.node_manager.unregister_node(node_id)
        self.hash_ring.remove_node(node_id)

        logger.info(f"[Coordinator] Node removed: {node_id}")

        # P2: Repair replicas from leaving node
        self._repair_after_node_leave(node_id)

        return True

    def node_heartbeat(
        self,
        node_id: str,
        storage_used_gb: Optional[float] = None,
        status: str = "online",
    ) -> bool:
        """Node heartbeat"""
        success = self.node_manager.heartbeat(node_id, storage_used_gb)

        if success:
            self.hash_ring.update_node_status(node_id, status)
            self.hash_ring.update_node_storage(
                node_id,
                storage_used_gb or (
                    self.node_manager.get_node(node_id).storage_used_gb
                    if self.node_manager.get_node(node_id) else 0
                )
            )

        return success

    # ==================== Routing Core ====================

    def _get_data_id(self, data_type: str, key: str) -> str:
        """Generate unique data ID"""
        raw = f"{data_type}:{key}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def get_storage_nodes(self, data_id: str) -> tuple:
        """Return (primary_node_id, [replica_node_ids])"""
        cached = self.routing_cache.get(data_id)
        if cached:
            return cached

        primary = self.hash_ring.get_primary_node(data_id)
        replicas = self.hash_ring.get_replica_nodes(
            data_id, self.replication_factor
        )

        result = (primary, replicas[1:] if len(replicas) > 1 else [])
        self.routing_cache.set(data_id, result)
        return result

    def get_read_node(
        self,
        data_id: str,
        preferred_node: Optional[str] = None,
    ) -> Optional[str]:
        """Get the best node for reading"""
        primary, replicas = self.get_storage_nodes(data_id)

        candidates = []
        if preferred_node and self._is_node_available(preferred_node):
            candidates.append(preferred_node)
        elif primary and self._is_node_available(primary):
            candidates.append(primary)

        for node_id in replicas:
            if self._is_node_available(node_id):
                candidates.append(node_id)

        if not candidates:
            return None

        return min(candidates, key=lambda n: self._get_node_load(n))

    def _is_node_available(self, node_id: str) -> bool:
        node = self.node_manager.get_node(node_id)
        if not node:
            return False
        return (
            node.status == NodeStatus.ONLINE and
            node.storage_usage_percent < 90
        )

    def _get_node_load(self, node_id: str) -> float:
        node = self.node_manager.get_node(node_id)
        if not node:
            return 100
        storage_load = node.storage_usage_percent
        request_load = min(node.request_count / 1000 * 10, 50)
        return storage_load + request_load

    # ==================== Data Operations ====================

    def upload_thought(
        self,
        thought_id: str,
        content: Dict,
        user_id: Optional[str] = None,
    ) -> Dict:
        """Upload a thought"""
        op_id = f"upload_{int(time.time() * 1000)}"
        data_id = self._get_data_id("thought", thought_id)

        start_time = time.time()
        primary, replicas = self.get_storage_nodes(data_id)

        if not primary:
            return {"success": False, "error": "No available nodes", "op_id": op_id}

        node_urls = self._get_node_urls()

        success = self.replication_manager.replicate_to_nodes(
            data_id=data_id,
            data_type="thought",
            content=content,
            primary_node=primary,
            replica_nodes=replicas,
            node_urls=node_urls,
        )

        # P2: Record ownership
        if success:
            self._record_ownership(data_id, [primary] + replicas)

        latency = (time.time() - start_time) * 1000
        self._record_operation(Operation(
            op_id=op_id, op_type="upload_thought", data_id=data_id,
            timestamp=time.time(),
            status="success" if success else "failed",
            node_selected=primary, latency_ms=latency,
        ))

        self.metrics["total_requests"] += 1
        if success:
            self.metrics["successful_requests"] += 1
        else:
            self.metrics["failed_requests"] += 1

        return {
            "success": success,
            "data_id": data_id,
            "primary_node": primary,
            "replica_nodes": replicas,
            "op_id": op_id,
            "latency_ms": round(latency, 2),
        }

    def download_thought(self, thought_id: str) -> Optional[Dict]:
        """Download a thought"""
        op_id = f"download_{int(time.time() * 1000)}"
        data_id = self._get_data_id("thought", thought_id)

        start_time = time.time()
        read_node = self.get_read_node(data_id)

        if not read_node:
            self.metrics["failed_requests"] += 1
            return None

        node_urls = self._get_node_urls()
        result = self.replication_manager.read_from_replica(
            data_id=data_id,
            preferred_node=read_node,
            node_urls=node_urls,
        )

        latency = (time.time() - start_time) * 1000
        self._record_operation(Operation(
            op_id=op_id, op_type="download_thought", data_id=data_id,
            timestamp=time.time(),
            status="success" if result else "failed",
            node_selected=read_node, latency_ms=latency,
        ))

        self.metrics["total_requests"] += 1
        if result:
            self.metrics["successful_requests"] += 1
        else:
            self.metrics["failed_requests"] += 1

        return result

    def upload_skill(
        self,
        skill_id: str,
        content: Dict,
    ) -> Dict:
        """Upload a skill"""
        op_id = f"upload_skill_{int(time.time() * 1000)}"
        data_id = self._get_data_id("skill", skill_id)

        primary, replicas = self.get_storage_nodes(data_id)

        if not primary:
            return {"success": False, "error": "No nodes available"}

        node_urls = self._get_node_urls()

        success = self.replication_manager.replicate_to_nodes(
            data_id=data_id,
            data_type="skill",
            content=content,
            primary_node=primary,
            replica_nodes=replicas,
            node_urls=node_urls,
        )

        if success:
            self._record_ownership(data_id, [primary] + replicas)

        return {
            "success": success,
            "data_id": data_id,
            "primary_node": primary,
            "replica_nodes": replicas,
        }

    # ==================== Cluster Management ====================

    def sync_thought(self, thought: Dict) -> bool:
        """Sync thought to distributed nodes (called by main server)"""
        thought_id = thought.get("id", "")
        if not thought_id:
            return False

        data_id = self._get_data_id("thought", thought_id)
        primary, replicas = self.get_storage_nodes(data_id)

        if not primary:
            return False

        node_urls = self._get_node_urls()

        success = self.replication_manager.replicate_to_nodes(
            data_id=data_id,
            data_type="thought",
            content=thought,
            primary_node=primary,
            replica_nodes=replicas,
            node_urls=node_urls,
        )

        if success:
            self._record_ownership(data_id, [primary] + replicas)

        return success

    def _get_node_urls(self) -> Dict[str, str]:
        """Get URL mapping for all nodes"""
        return {
            node.node_id: node.url
            for node in self.node_manager.get_online_nodes()
        }

    def _record_operation(self, op: Operation) -> None:
        self.operations.append(op)
        if len(self.operations) > self.max_operations:
            self.operations = self.operations[-self.max_operations:]

    # ==================== P2: Data Ownership Tracking ====================

    def _record_ownership(self, data_id: str, nodes: List[str]) -> None:
        """Record which nodes hold a data_id"""
        self._data_ownership[data_id] = set(nodes)

    def _get_data_owned_by_node(self, node_id: str) -> List[str]:
        """Get all data_ids held by a specific node"""
        return [
            data_id
            for data_id, owners in self._data_ownership.items()
            if node_id in owners
        ]

    # ==================== P2: Data Rebalancing ====================

    def _trigger_rebalance(self, new_node_id: str) -> Dict[str, Any]:
        """
        Trigger data rebalancing when a new node joins

        Strategy: Lazy Migration
        - New node actively pulls (pull) data it should own
        - Old nodes retain data until told to delete
        - New data is written directly to the new node

        Flow:
        1. Get all online old nodes
        2. New node pulls data it should own from each old node
        3. Old nodes return data via /api/replica/migrate endpoint
        """
        self.metrics["rebalance_triggered"] += 1
        logger.info(f"[Rebalance] Triggered: new_node={new_node_id}")

        new_node = self.node_manager.get_node(new_node_id)
        if not new_node or not new_node.is_healthy():
            logger.warning(f"[Rebalance] New node {new_node_id} not ready, skipping")
            return {"success": False, "error": "Node not healthy"}

        # Online old nodes
        old_nodes = [
            n for n in self.node_manager.get_online_nodes()
            if n.node_id != new_node_id
        ]

        if not old_nodes:
            logger.info("[Rebalance] No old nodes, skipping")
            return {"success": True, "migrated": 0}

        # Get new node URL
        new_node_url = new_node.url

        # New node pulls data from each old node
        # Old nodes return data via /api/replica/migrate endpoint
        total_migrated = 0
        session = self.replication_manager._get_session()

        for old_node in old_nodes:
            try:
                migrate_path = f"/api/replica/migrate?target={new_node_id}"
                resp = session.get(
                    url=old_node.url,
                    path=migrate_path,
                    timeout=60,
                )

                if resp.status_code == 200:
                    migrate_data = resp.json()
                    items = migrate_data.get("items", [])
                    for item in items:
                        # New node writes data (replica_store)
                        store_resp = session.post(
                            url=new_node_url,
                            path="/api/replica/store",
                            json={
                                "data_id": item["data_id"],
                                "data_type": item["data_type"],
                                "content": item["content"],
                            },
                            timeout=30,
                        )
                        if store_resp.status_code == 200:
                            # Record ownership
                            self._record_ownership(
                                item["data_id"],
                                [new_node_id]
                            )
                            total_migrated += 1

                    logger.info(
                        f"[Rebalance] {old_node.node_id} -> {new_node_id}: "
                        f"migrated {len(items)} items"
                    )
                elif resp.status_code == 404:
                    logger.debug(
                        f"[Rebalance] Node {old_node.node_id} does not support /api/replica/migrate"
                    )
            except Exception as e:
                logger.warning(
                    f"[Rebalance] Pull from {old_node.node_id} failed: {e}"
                )

        logger.info(
            f"[Rebalance] Complete: new_node={new_node_id}, "
            f"migrated={total_migrated} items"
        )
        self.metrics["rebalance_success"] += 1

        return {
            "success": True,
            "new_node": new_node_id,
            "migrated": total_migrated,
        }

    # ==================== P2: Replica Repair ====================

    def _repair_after_node_leave(self, failed_node_id: str) -> Dict[str, Any]:
        """
        After a node leaves, repair replicas (ensure every data has sufficient replica count)

        Flow:
        1. Find all data_ids held by this node
        2. For each data, check current replica count
        3. If replica count insufficient, replicate from surviving nodes
        """
        self.metrics["repair_triggered"] += 1
        logger.info(f"[Repair] Triggered: failed_node={failed_node_id}")

        # Find data held by this node
        data_ids = self._get_data_owned_by_node(failed_node_id)
        logger.info(f"[Repair] Node {failed_node_id} held {len(data_ids)} items to repair")

        if not data_ids:
            logger.info("[Repair] No data to repair")
            return {"success": True, "repaired": 0}

        # Online healthy nodes
        healthy_nodes = self.node_manager.get_healthy_nodes()
        if not healthy_nodes:
            logger.error("[Repair] No healthy nodes, repair failed")
            return {"success": False, "error": "No healthy nodes"}

        repaired = 0
        node_urls = self._get_node_urls()

        for data_id in data_ids:
            # Recalculate which nodes this data_id should be stored on
            primary, replicas = self.get_storage_nodes(data_id)
            target_nodes = [primary] + replicas if primary else replicas

            if not target_nodes:
                continue

            # Find nodes currently missing this data
            current_owners = self._data_ownership.get(data_id, set())
            missing_nodes = [
                n for n in target_nodes
                if n != failed_node_id and n not in current_owners
            ]

            if not missing_nodes:
                # Replicas already sufficient
                continue

            # Read data from existing holder
            source_node = None
            for owner in current_owners:
                if owner != failed_node_id and owner in node_urls:
                    source_node = owner
                    break

            if not source_node:
                logger.warning(f"[Repair] Cannot find data source for {data_id}")
                continue

            # Read data
            content = self.replication_manager.read_from_replica(
                data_id=data_id,
                preferred_node=source_node,
                node_urls=node_urls,
            )

            if not content:
                logger.warning(f"[Repair] Cannot read content for {data_id}")
                continue

            # Determine data_type
            data_type = content.get("data_type", "thought")
            data_content = content.get("content", {})

            # Replicate to missing nodes
            success = self.replication_manager.replicate_to_nodes(
                data_id=data_id,
                data_type=data_type,
                content=data_content,
                primary_node=target_nodes[0],
                replica_nodes=missing_nodes,
                node_urls=node_urls,
            )

            if success:
                # Update ownership record
                new_owners = current_owners | set(missing_nodes)
                new_owners.discard(failed_node_id)
                self._record_ownership(data_id, list(new_owners))
                repaired += 1
                logger.debug(f"[Repair] OK: {data_id} -> {missing_nodes}")
            else:
                logger.warning(f"[Repair] FAILED: {data_id}")

        logger.info(f"[Repair] Complete: repaired {repaired}/{len(data_ids)} items")
        self.metrics["repair_success"] += 1

        # Update ownership: remove leaving node
        for data_id in self._data_ownership:
            self._data_ownership[data_id].discard(failed_node_id)

        return {
            "success": True,
            "failed_node": failed_node_id,
            "total": len(data_ids),
            "repaired": repaired,
        }

    def get_cluster_status(self) -> Dict:
        """Get cluster status"""
        node_stats = self.node_manager.get_cluster_stats()
        ring_stats = self.hash_ring.get_stats()

        return {
            "coordinator": {
                "node_id": self.node_id,
                "status": self.status.value,
            },
            "nodes": node_stats,
            "sharding": ring_stats,
            "metrics": self.metrics,
            "replication_factor": self.replication_factor,
            "data_ownership": {
                "tracked_items": len(self._data_ownership),
            },
        }

    def get_routing_info(self, data_type: str, key: str) -> Dict:
        """Get routing info (for debugging)"""
        data_id = self._get_data_id(data_type, key)
        primary, replicas = self.get_storage_nodes(data_id)

        return {
            "data_type": data_type,
            "key": key,
            "data_id": data_id,
            "primary_node": primary,
            "replica_nodes": replicas,
        }


# Tests
if __name__ == "__main__":
    coord = DistributedCoordinator(node_id="coordinator_001")

    coord.add_node("node_001", "192.168.1.1", 5001)
    coord.add_node("node_002", "192.168.1.2", 5001)
    coord.add_node("node_003", "192.168.1.3", 5001)

    print("[Coordinator] Test run")
    print("=" * 50)

    test_thoughts = [
        ("thought_001", "My first thought"),
        ("thought_002", "Investment thinking"),
        ("thought_003", "Market analysis"),
    ]

    for thought_id, _ in test_thoughts:
        info = coord.get_routing_info("thought", thought_id)
        print(f"\n{thought_id}:")
        print(f"  Data ID: {info['data_id']}")
        print(f"  Primary: {info['primary_node']}")
        print(f"  Replicas: {info['replica_nodes']}")

    print("\n[Cluster Status]:")
    status = coord.get_cluster_status()
    print(f"  Nodes: {status['nodes']['total_nodes']}")
    print(f"  Online: {status['nodes']['online_nodes']}")
    print(f"  Storage: {status['nodes']['used_storage_gb']:.1f}GB / {status['nodes']['total_storage_gb']:.1f}GB")

    print("\n[Ready for use in Flask]")