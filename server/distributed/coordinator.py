"""
Mind Library - Distributed Coordinator (Synchronous Version)

Responsibilities:
- Routing: Distribute requests to correct nodes
- Load balancing: Smart selection across replicas
- Failover: Auto-switch on node failure
- Cluster coordination: Node join/leave/failure handling
"""

import hashlib
import json
import time
import os
from typing import Dict, List, Optional, Any
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
    """协调者状态"""
    STANDBY = "standby"      # 备用
    ACTIVE = "active"        # 主协调者
    RECOVERING = "recovering"


@dataclass
class Operation:
    """操作记录"""
    op_id: str
    op_type: str      # upload_thought, upload_skill, download, delete
    data_id: str
    timestamp: float
    status: str       # pending, success, failed
    node_selected: str
    latency_ms: float = 0
    error: Optional[str] = None


class DistributedCoordinator:
    """
    分布式协调者（同步版本）
    
    是整个系统的核心，负责：
    1. 路由 - 确定数据存储在哪个节点
    2. 负载均衡 - 选择最佳副本节点响应请求
    3. 故障转移 - 节点故障时自动切换到健康副本
    4. 数据迁移 - 节点加入/离开时重新分配数据
    """
    
    def __init__(
        self,
        node_id: str = "coordinator_001",
        replication_factor: int = 3,
    ):
        self.node_id = node_id
        self.replication_factor = replication_factor
        self.status = CoordinatorStatus.ACTIVE
        
        # 核心组件
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
        }
        
        # Routing cache with persistence
        persist_dir = os.environ.get('MIND_PERSIST_DIR')
        self.routing_cache = RoutingCacheManager(persist_dir)
        
    # ==================== Node Management ====================
    
    def add_node(self, node_id: str, host: str, port: int) -> bool:
        """添加存储节点"""
        # 注册到节点管理器
        self.node_manager.register_node(node_id, host, port)
        
        # 添加到哈希环
        node = Node(node_id, host, port)
        self.hash_ring.add_node(node)
        
        logger.info(f"🎃 节点添加成功: {node_id} @ {host}:{port}")
        
        # 数据再平衡（同步版本）
        if config.CLUSTER_CONFIG["auto_rebalance"]:
            self._trigger_rebalance()
            
        return True
    
    def remove_node(self, node_id: str) -> bool:
        """移除存储节点"""
        self.node_manager.unregister_node(node_id)
        self.hash_ring.remove_node(node_id)
        
        logger.info(f"🎃 节点移除: {node_id}")
        
        # 触发数据修复
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
        
        # 更新哈希环中的节点状态
        if success:
            self.hash_ring.update_node_status(node_id, status)
            self.hash_ring.update_node_storage(
                node_id,
                storage_used_gb or self.node_manager.get_node(node_id).storage_used_gb
            )
            
        return success
    
    # ==================== 路由核心 ====================
    
    def _get_data_id(self, data_type: str, key: str) -> str:
        """生成数据唯一ID"""
        raw = f"{data_type}:{key}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]
    
    def get_storage_nodes(self, data_id: str) -> tuple:
        """
        Get storage node list
        
        Returns: (primary_node_id, [replica_node_ids])
        """
        # Check cache
        cached = self.routing_cache.get(data_id)
        if cached:
            return cached
            
        # Calculate routing
        primary = self.hash_ring.get_primary_node(data_id)
        replicas = self.hash_ring.get_replica_nodes(
            data_id, 
            self.replication_factor
        )
        
        result = (primary, replicas[1:] if len(replicas) > 1 else [])
        
        # Update cache
        self.routing_cache.set(data_id, result)
        
        return result
    
    def get_read_node(
        self,
        data_id: str,
        preferred_node: Optional[str] = None,
    ) -> Optional[str]:
        """
        获取最佳读取节点
        
        策略：
        1. 优先使用首选节点
        2. 检查节点健康状态
        3. 负载最低的节点优先
        """
        primary, replicas = self.get_storage_nodes(data_id)
        
        # 可用节点列表
        candidates = []
        
        # 首选节点
        if preferred_node and self._is_node_available(preferred_node):
            candidates.append(preferred_node)
        elif primary and self._is_node_available(primary):
            candidates.append(primary)
            
        # 副本节点
        for node_id in replicas:
            if self._is_node_available(node_id):
                candidates.append(node_id)
                
        if not candidates:
            return None
            
        # 选择负载最低的节点
        best_node = min(
            candidates,
            key=lambda n: self._get_node_load(n)
        )
        
        return best_node
    
    def _is_node_available(self, node_id: str) -> bool:
        """检查节点是否可用"""
        node = self.node_manager.get_node(node_id)
        if not node:
            return False
            
        # 在线且存储未满
        return (
            node.status == NodeStatus.ONLINE and
            node.storage_usage_percent < 90
        )
    
    def _get_node_load(self, node_id: str) -> float:
        """获取节点负载（0-100）"""
        node = self.node_manager.get_node(node_id)
        if not node:
            return 100
            
        # 综合考虑存储和请求量
        storage_load = node.storage_usage_percent
        request_load = min(node.request_count / 1000 * 10, 50)  # 简化的请求负载
        
        return storage_load + request_load
    
    # ==================== 数据操作 ====================
    
    def upload_thought(
        self,
        thought_id: str,
        content: Dict,
        user_id: Optional[str] = None,
    ) -> Dict:
        """
        上传思想（同步版本）
        
        流程：
        1. 确定存储节点
        2. 写入主节点
        3. 复制到副本节点
        4. 返回结果
        """
        op_id = f"upload_{int(time.time() * 1000)}"
        data_id = self._get_data_id("thought", thought_id)
        
        start_time = time.time()
        
        # 获取存储节点
        primary, replicas = self.get_storage_nodes(data_id)
        
        if not primary:
            return {
                "success": False,
                "error": "No available nodes",
                "op_id": op_id,
            }
            
        # 构建节点URL映射
        node_urls = self._get_node_urls()
        
        # 复制到所有节点
        success = self.replication_manager.replicate_to_nodes(
            data_id=data_id,
            data_type="thought",
            content=content,
            primary_node=primary,
            replica_nodes=replicas,
            node_urls=node_urls,
        )
        
        latency = (time.time() - start_time) * 1000
        
        # 记录操作
        self._record_operation(Operation(
            op_id=op_id,
            op_type="upload_thought",
            data_id=data_id,
            timestamp=time.time(),
            status="success" if success else "failed",
            node_selected=primary,
            latency_ms=latency,
        ))
        
        # 更新指标
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
    
    def download_thought(
        self,
        thought_id: str,
    ) -> Optional[Dict]:
        """
        下载思想（同步版本）
        
        流程：
        1. 确定数据ID
        2. 选择最佳读取节点
        3. 获取数据
        """
        op_id = f"download_{int(time.time() * 1000)}"
        data_id = self._get_data_id("thought", thought_id)
        
        start_time = time.time()
        
        # 获取最佳读取节点
        read_node = self.get_read_node(data_id)
        
        if not read_node:
            self.metrics["failed_requests"] += 1
            return None
            
        node_urls = self._get_node_urls()
        
        # 从副本读取
        result = self.replication_manager.read_from_replica(
            data_id=data_id,
            preferred_node=read_node,
            node_urls=node_urls,
        )
        
        latency = (time.time() - start_time) * 1000
        
        # 记录
        self._record_operation(Operation(
            op_id=op_id,
            op_type="download_thought",
            data_id=data_id,
            timestamp=time.time(),
            status="success" if result else "failed",
            node_selected=read_node,
            latency_ms=latency,
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
        """上传技能（与思想类似）"""
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
        
        return self.replication_manager.replicate_to_nodes(
            data_id=data_id,
            data_type="thought",
            content=thought,
            primary_node=primary,
            replica_nodes=replicas,
            node_urls=node_urls,
        )
    
    def _get_node_urls(self) -> Dict[str, str]:
        """获取所有节点的URL映射"""
        urls = {}
        for node in self.node_manager.get_online_nodes():
            urls[node.node_id] = node.url
        return urls
    
    def _record_operation(self, op: Operation) -> None:
        """记录操作"""
        self.operations.append(op)
        
        # 保持操作记录在限制内
        if len(self.operations) > self.max_operations:
            self.operations = self.operations[-self.max_operations:]
    
    def _trigger_rebalance(self) -> None:
        """触发数据再平衡（简化版本）"""
        logger.info("🎃 检查是否需要数据再平衡...")
        # 实际实现可以在这里添加数据迁移逻辑
        
    def _repair_after_node_leave(self, failed_node_id: str) -> None:
        """节点离开后的数据修复（简化版本）"""
        logger.info(f"🎃 开始修复数据，节点 {failed_node_id} 已离开")
        # 实际实现可以在这里添加副本修复逻辑
        
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
        }
    
    # ==================== API 端点 ====================
    
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
    # 创建协调者
    coord = DistributedCoordinator(node_id="coordinator_001")
    
    # 添加节点
    coord.add_node("node_001", "192.168.1.1", 5001)
    coord.add_node("node_002", "192.168.1.2", 5001)
    coord.add_node("node_003", "192.168.1.3", 5001)
    
    print("🎃 分布式协调者测试（同步版本）")
    print("=" * 50)
    
    # 测试路由
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
    
    # 集群状态
    print("\n📊 集群状态:")
    status = coord.get_cluster_status()
    print(f"  节点数: {status['nodes']['total_nodes']}")
    print(f"  在线: {status['nodes']['online_nodes']}")
    print(f"  存储: {status['nodes']['used_storage_gb']:.1f}GB / {status['nodes']['total_storage_gb']:.1f}GB")
    
    print("\n✅ 同步版本就绪，可在 Flask 中直接调用")
