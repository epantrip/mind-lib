"""
Mind Library - Distributed Coordinator (P2: Rebalance + Repair)

增量改动：
1. _data_ownership: Dict[str, Set[str]] — data_id → 持有该数据的节点集合
2. _record_ownership(data_id, nodes): 每次写入后记录
3. _trigger_rebalance(node_id): 新节点从旧节点拉取应负责的数据
4. _repair_after_node_leave(node_id): 离开节点的数据重新复制到健康节点
5. /api/replica/migrate 端点：节点间数据迁移
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
    分布式协调者

    P2 新增：
    - 数据所有权追踪（_data_ownership）
    - 节点加入时的数据再平衡
    - 节点离开后的副本修复
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

        # P2: 数据所有权追踪
        # key = data_id, value = 持有该数据的节点集合
        self._data_ownership: Dict[str, Set[str]] = {}

        # 操作记录
        self.operations: List[Operation] = []
        self.max_operations = 10000

        # 监控指标
        self.metrics = {
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "avg_latency_ms": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            # P2 新增
            "rebalance_triggered": 0,
            "rebalance_success": 0,
            "repair_triggered": 0,
            "repair_success": 0,
        }

        persist_dir = os.environ.get('MIND_PERSIST_DIR')
        self.routing_cache = RoutingCacheManager(persist_dir)

    # ==================== Node Management ====================

    def add_node(self, node_id: str, host: str, port: int) -> bool:
        """添加存储节点"""
        self.node_manager.register_node(node_id, host, port)
        node = Node(node_id, host, port)
        self.hash_ring.add_node(node)

        logger.info(f"🎃 节点添加成功: {node_id} @ {host}:{port}")

        # P2: 触发数据再平衡
        if config.CLUSTER_CONFIG["auto_rebalance"]:
            self._trigger_rebalance(node_id)

        return True

    def remove_node(self, node_id: str) -> bool:
        """移除存储节点"""
        self.node_manager.unregister_node(node_id)
        self.hash_ring.remove_node(node_id)

        logger.info(f"🎃 节点移除: {node_id}")

        # P2: 修复离开节点的副本
        self._repair_after_node_leave(node_id)

        return True

    def node_heartbeat(
        self,
        node_id: str,
        storage_used_gb: Optional[float] = None,
        status: str = "online",
    ) -> bool:
        """节点心跳"""
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

    # ==================== 路由核心 ====================

    def _get_data_id(self, data_type: str, key: str) -> str:
        """生成数据唯一ID"""
        raw = f"{data_type}:{key}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def get_storage_nodes(self, data_id: str) -> tuple:
        """返回 (primary_node_id, [replica_node_ids])"""
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
        """获取最佳读取节点"""
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

    # ==================== 数据操作 ====================

    def upload_thought(
        self,
        thought_id: str,
        content: Dict,
        user_id: Optional[str] = None,
    ) -> Dict:
        """上传思想"""
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

        # P2: 记录所有权
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
        """下载思想"""
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
        """上传技能"""
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

    # ==================== 集群管理 ====================

    def sync_thought(self, thought: Dict) -> bool:
        """同步思想到分布式节点（供主服务器调用）"""
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
        """获取所有节点的URL映射"""
        return {
            node.node_id: node.url
            for node in self.node_manager.get_online_nodes()
        }

    def _record_operation(self, op: Operation) -> None:
        self.operations.append(op)
        if len(self.operations) > self.max_operations:
            self.operations = self.operations[-self.max_operations:]

    # ==================== P2: 数据所有权追踪 ====================

    def _record_ownership(self, data_id: str, nodes: List[str]) -> None:
        """记录 data_id 由哪些节点持有"""
        self._data_ownership[data_id] = set(nodes)

    def _get_data_owned_by_node(self, node_id: str) -> List[str]:
        """获取指定节点持有的所有 data_id"""
        return [
            data_id
            for data_id, owners in self._data_ownership.items()
            if node_id in owners
        ]

    # ==================== P2: 数据再平衡 ====================

    def _trigger_rebalance(self, new_node_id: str) -> Dict[str, Any]:
        """
        新节点加入时，触发数据再平衡

        策略：懒迁移（lazy migration）
        - 新节点主动拉取（pull）自己应该负责的数据
        - 旧节点保留数据直到被告知可删除
        - 新数据直接写入新节点

        流程：
        1. 获取所有在线旧节点
        2. 让新节点从各旧节点拉取自己应负责的数据
        3. 旧节点收到 /api/replica/migrate 请求后推送数据
        """
        self.metrics["rebalance_triggered"] += 1
        logger.info(f"🎃 触发数据再平衡: 新节点={new_node_id}")

        new_node = self.node_manager.get_node(new_node_id)
        if not new_node or not new_node.is_healthy():
            logger.warning(f"新节点 {new_node_id} 未就绪，跳过再平衡")
            return {"success": False, "error": "Node not healthy"}

        # 在线旧节点
        old_nodes = [
            n for n in self.node_manager.get_online_nodes()
            if n.node_id != new_node_id
        ]

        if not old_nodes:
            logger.info("无旧节点，跳过再平衡")
            return {"success": True, "migrated": 0}

        # 获取新节点的 URL
        new_node_url = new_node.url

        # 让新节点依次从各旧节点拉取数据
        # 旧节点通过 /api/replica/migrate 端点返回应迁移的数据
        total_migrated = 0
        session = self.replication_manager._get_session()

        for old_node in old_nodes:
            try:
                # 请求旧节点返回"应该属于 new_node 的数据"列表
                # 这里用 GET /api/replica/migrate?target={new_node_id}
                # 旧节点的 migrate 端点会：
                #   1. 计算每个本地 data_id 现在应该属于哪些节点
                #   2. 如果 new_node 在目标节点中，返回该数据
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
                        # 新节点写入数据（replica_store）
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
                            # 记录所有权
                            self._record_ownership(
                                item["data_id"],
                                [new_node_id]
                            )
                            total_migrated += 1

                    logger.info(
                        f"  {old_node.node_id} -> {new_node_id}: "
                        f"迁移 {len(items)} 条数据"
                    )
                elif resp.status_code == 404:
                    # 旧节点不支持 migrate 端点，忽略
                    logger.debug(
                        f"节点 {old_node.node_id} 不支持 /api/replica/migrate"
                    )
            except Exception as e:
                logger.warning(
                    f"  从 {old_node.node_id} 拉取失败: {e}"
                )

        logger.info(
            f"✅ 再平衡完成: 新节点={new_node_id}, "
            f"迁移 {total_migrated} 条数据"
        )
        self.metrics["rebalance_success"] += 1

        return {
            "success": True,
            "new_node": new_node_id,
            "migrated": total_migrated,
        }

    # ==================== P2: 副本修复 ====================

    def _repair_after_node_leave(self, failed_node_id: str) -> Dict[str, Any]:
        """
        节点离开后，修复副本（确保每条数据有足够的副本数）

        流程：
        1. 找出该节点持有的所有 data_id
        2. 对每条数据，检查当前副本数
        3. 副本数不足时，从存活节点重新复制
        """
        self.metrics["repair_triggered"] += 1
        logger.info(f"🎃 修复副本: 离开节点={failed_node_id}")

        # 找出该节点负责的数据
        data_ids = self._get_data_owned_by_node(failed_node_id)
        logger.info(f"  节点 {failed_node_id} 持有 {len(data_ids)} 条数据需要修复")

        if not data_ids:
            logger.info("  无数据需要修复")
            return {"success": True, "repaired": 0}

        # 在线健康节点
        healthy_nodes = self.node_manager.get_healthy_nodes()
        if not healthy_nodes:
            logger.error("  无健康节点，修复失败")
            return {"success": False, "error": "No healthy nodes"}

        repaired = 0
        node_urls = self._get_node_urls()

        for data_id in data_ids:
            # 重新计算该 data_id 现在应该存储在哪些节点
            primary, replicas = self.get_storage_nodes(data_id)
            target_nodes = [primary] + replicas if primary else replicas

            if not target_nodes:
                continue

            # 找出该数据目前缺失的节点
            current_owners = self._data_ownership.get(data_id, set())
            missing_nodes = [
                n for n in target_nodes
                if n != failed_node_id and n not in current_owners
            ]

            if not missing_nodes:
                # 副本已足够
                continue

            # 从现有持有者读取数据
            source_node = None
            for owner in current_owners:
                if owner != failed_node_id and owner in node_urls:
                    source_node = owner
                    break

            if not source_node:
                logger.warning(f"  无法找到 {data_id} 的数据源")
                continue

            # 读取数据
            content = self.replication_manager.read_from_replica(
                data_id=data_id,
                preferred_node=source_node,
                node_urls=node_urls,
            )

            if not content:
                logger.warning(f"  无法读取 {data_id} 的数据内容")
                continue

            # 确定 data_type
            data_type = content.get("data_type", "thought")
            data_content = content.get("content", {})

            # 重新复制到缺失节点
            success = self.replication_manager.replicate_to_nodes(
                data_id=data_id,
                data_type=data_type,
                content=data_content,
                primary_node=target_nodes[0],
                replica_nodes=missing_nodes,
                node_urls=node_urls,
            )

            if success:
                # 更新所有权记录
                new_owners = current_owners | set(missing_nodes)
                new_owners.discard(failed_node_id)
                self._record_ownership(data_id, list(new_owners))
                repaired += 1
                logger.debug(f"  ✅ 修复: {data_id} -> {missing_nodes}")
            else:
                logger.warning(f"  ❌ 修复失败: {data_id}")

        logger.info(f"✅ 副本修复完成: 修复 {repaired}/{len(data_ids)} 条数据")
        self.metrics["repair_success"] += 1

        # 更新所有权记录：移除离开节点
        for data_id in self._data_ownership:
            self._data_ownership[data_id].discard(failed_node_id)

        return {
            "success": True,
            "failed_node": failed_node_id,
            "total": len(data_ids),
            "repaired": repaired,
        }

    def get_cluster_status(self) -> Dict:
        """获取集群状态"""
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
        """获取路由信息（调试用）"""
        data_id = self._get_data_id(data_type, key)
        primary, replicas = self.get_storage_nodes(data_id)

        return {
            "data_type": data_type,
            "key": key,
            "data_id": data_id,
            "primary_node": primary,
            "replica_nodes": replicas,
        }


# 测试
if __name__ == "__main__":
    coord = DistributedCoordinator(node_id="coordinator_001")

    coord.add_node("node_001", "192.168.1.1", 5001)
    coord.add_node("node_002", "192.168.1.2", 5001)
    coord.add_node("node_003", "192.168.1.3", 5001)

    print("🎃 分布式协调者测试（同步版本）")
    print("=" * 50)

    test_thoughts = [
        ("thought_001", "我的第一个想法"),
        ("thought_002", "关于投资的思考"),
        ("thought_003", "今天的市场分析"),
    ]

    for thought_id, _ in test_thoughts:
        info = coord.get_routing_info("thought", thought_id)
        print(f"\n{thought_id}:")
        print(f"  Data ID: {info['data_id']}")
        print(f"  主节点: {info['primary_node']}")
        print(f"  副本: {info['replica_nodes']}")

    print("\n📊 集群状态:")
    status = coord.get_cluster_status()
    print(f"  节点数: {status['nodes']['total_nodes']}")
    print(f"  在线: {status['nodes']['online_nodes']}")
    print(f"  存储: {status['nodes']['used_storage_gb']:.1f}GB / {status['nodes']['total_storage_gb']:.1f}GB")

    print("\n✅ 同步版本就绪，可在 Flask 中直接调用")
