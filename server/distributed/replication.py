"""
🧠 分布式思想库 - 多副本复制管理（同步版本）
P1: 节点间 API 认证 (HMAC-SHA256)
"""

import hashlib
import json
import time
import logging
from typing import Dict, List, Optional, Any, TYPE_CHECKING
from dataclasses import dataclass, field
from enum import Enum
import requests

if TYPE_CHECKING:
    from node_auth import NodeAuth, AuthenticatedSession

logger = logging.getLogger(__name__)


class ReplicationStatus(Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class ReplicaData:
    data_id: str
    data_type: str
    content: Any
    version: int = 1
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    checksum: str = ""


@dataclass
class ReplicationTask:
    task_id: str
    data_id: str
    source_node: str
    target_nodes: List[str]
    status: ReplicationStatus = ReplicationStatus.PENDING
    retry_count: int = 0
    created_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None
    error: Optional[str] = None


class ReplicationManager:
    """
    多副本复制管理器（同步版本）
    P1: 所有 HTTP 调用均使用 HMAC-SHA256 签名认证
    """

    def __init__(
        self,
        replication_factor: int = 3,
        max_retries: int = 3,
        timeout: int = 30,
        node_auth: Optional["NodeAuth"] = None,
    ):
        self.replication_factor = replication_factor
        self.max_retries = max_retries
        self.timeout = timeout

        # 复制任务队列
        self.pending_tasks: Dict[str, ReplicationTask] = {}
        self.completed_tasks: Dict[str, ReplicationTask] = {}

        # 副本缓存
        self.replica_cache: Dict[str, List[str]] = {}  # data_id -> [node_ids]

        # 节点认证（P1）
        self._node_auth: Optional["NodeAuth"] = node_auth
        self._session: Optional["AuthenticatedSession"] = None

    def _get_session(self) -> "AuthenticatedSession":
        """延迟创建 AuthenticatedSession（避免循环导入）"""
        if self._session is None:
            from node_auth import AuthenticatedSession, get_node_auth
            self._node_auth = get_node_auth()
            self._session = AuthenticatedSession(self._node_auth)
        return self._session

    def _generate_checksum(self, content: Any) -> str:
        content_str = json.dumps(content, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(content_str.encode()).hexdigest()[:16]

    def replicate_to_nodes(
        self,
        data_id: str,
        data_type: str,
        content: Any,
        primary_node: str,
        replica_nodes: List[str],
        node_urls: Dict[str, str],
    ) -> bool:
        """
        复制数据到多个节点（同步版本）
        P1: 所有节点间 HTTP 调用带 HMAC 签名
        """
        replica_data = ReplicaData(
            data_id=data_id,
            data_type=data_type,
            content=content,
            checksum=self._generate_checksum(content),
        )

        success_nodes = [primary_node]
        session = self._get_session()

        for target_node in replica_nodes:
            if target_node not in node_urls:
                logger.warning(f"跳过节点 {target_node}: 无URL配置")
                continue

            url = node_urls.get(target_node, "")
            try:
                # P1: 使用签名认证的 Session
                resp = session.post(
                    url=url,
                    path="/api/replica/store",
                    json={
                        "data_id": data.data_id,
                        "data_type": data.data_type,
                        "content": data.content,
                        "version": data.version,
                        "checksum": data.checksum,
                        "timestamp": time.time(),
                    },
                    timeout=self.timeout,
                )
                if resp.status_code == 200:
                    success_nodes.append(target_node)
                    logger.info(f"✅ 复制成功: {data_id} -> {target_node}")
                else:
                    logger.warning(f"❌ 复制失败: {data_id} -> {target_node} [{resp.status_code}]")
            except Exception as e:
                logger.error(f"❌ 复制异常: {data_id} -> {target_node}: {e}")

        min_replicas = min(2, self.replication_factor)
        if len(success_nodes) < min_replicas:
            logger.error(f"⚠️ 副本数不足: 需要{min_replicas}，实际{len(success_nodes)}")
            return False

        self.replica_cache[data_id] = success_nodes
        return True

    def read_from_replica(
        self,
        data_id: str,
        preferred_node: str,
        node_urls: Dict[str, str],
    ) -> Optional[Dict]:
        """
        从副本读取数据
        P1: 使用 HMAC 签名认证
        """
        replica_nodes = self.replica_cache.get(data_id, [])
        nodes_to_try = [preferred_node]
        nodes_to_try.extend([n for n in replica_nodes if n != preferred_node])

        session = self._get_session()

        for node_id in nodes_to_try:
            url = node_urls.get(node_id)
            if not url:
                continue
            try:
                resp = session.get(
                    url=url,
                    path=f"/api/replica/get/{data_id}",
                    timeout=self.timeout,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    logger.debug(f"📖 读取成功: {data_id} from {node_id}")
                    return data
            except Exception as e:
                logger.warning(f"📖 读取失败: {data_id} from {node_id}: {e}")

        logger.error(f"❌ 所有副本读取失败: {data_id}")
        return None

    def sync_between_nodes(
        self,
        source_node: str,
        target_node: str,
        node_urls: Dict[str, str],
    ) -> bool:
        """
        节点间数据同步
        P1: 使用 HMAC 签名认证
        """
        logger.info(f"🔄 节点间同步: {source_node} -> {target_node}")

        target_url = node_urls.get(target_node)
        if not target_url:
            return False

        session = self._get_session()
        try:
            resp = session.post(
                url=target_url,
                path="/api/sync/pull",
                json={"source_node": source_node},
                timeout=self.timeout * 2,
            )
            success = resp.status_code == 200
            if success:
                logger.info(f"✅ 同步成功: {source_node} -> {target_node}")
            return success
        except Exception as e:
            logger.error(f"❌ 同步失败: {source_node} -> {target_node}: {e}")
            return False

    def repair_replica(
        self,
        data_id: str,
        healthy_nodes: List[str],
        node_urls: Dict[str, str],
        source_node: str,
    ) -> bool:
        """修复副本（P1: 使用 HMAC 认证）"""
        logger.info(f"🔧 开始修复副本: {data_id}")
        source_url = node_urls.get(source_node)
        if not source_url:
            return False

        # P1: 从源节点读取时带签名
        session = self._get_session()
        try:
            resp = session.get(
                url=source_url,
                path=f"/api/replica/get/{data_id}",
                timeout=self.timeout,
            )
            if resp.status_code != 200:
                return False
            data = resp.json()
        except Exception:
            return False

        # P1: 写入目标节点时带签名
        for node_id in healthy_nodes:
            if node_id == source_node:
                continue
            url = node_urls.get(node_id)
            if not url:
                continue
            try:
                resp = session.post(
                    url=url,
                    path="/api/replica/store",
                    json={
                        "data_id": data_id,
                        "data_type": data.get("data_type", "thought"),
                        "content": data.get("content"),
                    },
                    timeout=self.timeout,
                )
            except Exception as e:
                logger.warning(f"🔧 修复写入失败: {node_id}: {e}")

        return True

    def get_replication_status(self, data_id: str) -> Dict:
        replicas = self.replica_cache.get(data_id, [])
        return {
            "data_id": data_id,
            "replica_count": len(replicas),
            "replica_nodes": replicas,
            "healthy": len(replicas) >= self.replication_factor // 2 + 1,
        }

    def clear_cache(self, data_id: Optional[str] = None) -> None:
        if data_id:
            self.replica_cache.pop(data_id, None)
        else:
            self.replica_cache.clear()
