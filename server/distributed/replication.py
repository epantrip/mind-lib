"""
Mind Library - Multi-Replica Replication Manager (Synchronous)

P1: All HTTP calls use HMAC-SHA256 signature authentication
"""

import hashlib, json, time, logging
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
    Multi-replica replication manager (synchronous)
    P1: All HTTP calls use HMAC-SHA256 signature authentication
    """

    def __init__(self, replication_factor: int = 3, max_retries: int = 3,
                 timeout: int = 30, node_auth: Optional["NodeAuth"] = None):
        self.replication_factor = replication_factor
        self.max_retries = max_retries
        self.timeout = timeout
        # Replication task queue
        self.pending_tasks: Dict[str, ReplicationTask] = {}
        self.completed_tasks: Dict[str, ReplicationTask] = {}
        # Replica cache
        self.replica_cache: Dict[str, List[str]] = {}
        # Node authentication (P1)
        self._node_auth: Optional["NodeAuth"] = node_auth
        self._session: Optional["AuthenticatedSession"] = None

    def _get_session(self) -> "AuthenticatedSession":
        """Lazily create AuthenticatedSession (avoids circular import)"""
        if self._session is None:
            from node_auth import AuthenticatedSession, get_node_auth
            self._node_auth = get_node_auth()
            self._session = AuthenticatedSession(self._node_auth)
        return self._session

    def _generate_checksum(self, content: Any) -> str:
        content_str = json.dumps(content, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(content_str.encode()).hexdigest()[:16]

    def replicate_to_nodes(self, data_id: str, data_type: str, content: Any,
                           primary_node: str, replica_nodes: List[str],
                           node_urls: Dict[str, str]) -> bool:
        """
        Replicate data to multiple nodes (synchronous)
        P1: All inter-node HTTP calls carry HMAC signature
        """
        replica_data = ReplicaData(
            data_id=data_id, data_type=data_type, content=content,
            checksum=self._generate_checksum(content))
        success_nodes = [primary_node]
        session = self._get_session()
        for target_node in replica_nodes:
            if target_node not in node_urls:
                logger.warning(f"Skipping node {target_node}: no URL configured")
                continue
            url = node_urls.get(target_node, "")
            try:
                # P1: Use HMAC-authenticated session
                resp = session.post(url=url, path="/api/replica/store",
                    json={"data_id": data.data_id, "data_type": data.data_type,
                          "content": data.content, "version": data.version,
                          "checksum": data.checksum, "timestamp": time.time()},
                    timeout=self.timeout)
                if resp.status_code == 200:
                    success_nodes.append(target_node)
                    logger.info(f"Replica OK: {data_id} -> {target_node}")
                else:
                    logger.warning(f"Replica FAIL: {data_id} -> {target_node} [{resp.status_code}]")
            except Exception as e:
                logger.error(f"Replica ERROR: {data_id} -> {target_node}: {e}")
        min_replicas = min(2, self.replication_factor)
        if len(success_nodes) < min_replicas:
            logger.error(f"Insufficient replicas: need {min_replicas}, got {len(success_nodes)}")
            return False
        self.replica_cache[data_id] = success_nodes
        return True

    def read_from_replica(self, data_id: str, preferred_node: str,
                          node_urls: Dict[str, str]) -> Optional[Dict]:
        """
        Read data from replica
        P1: Uses HMAC signature authentication
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
                resp = session.get(url=url, path=f"/api/replica/get/{data_id}", timeout=self.timeout)
                if resp.status_code == 200:
                    data = resp.json()
                    logger.debug(f"Read OK: {data_id} from {node_id}")
                    return data
            except Exception as e:
                logger.warning(f"Read FAIL: {data_id} from {node_id}: {e}")
        logger.error(f"All replica reads failed: {data_id}")
        return None

    def sync_between_nodes(self, source_node: str, target_node: str,
                           node_urls: Dict[str, str]) -> bool:
        """
        Inter-node data sync
        P1: Uses HMAC signature authentication
        """
        logger.info(f"Syncing: {source_node} -> {target_node}")
        target_url = node_urls.get(target_node)
        if not target_url:
            return False
        session = self._get_session()
        try:
            resp = session.post(url=target_url, path="/api/sync/pull",
                               json={"source_node": source_node}, timeout=self.timeout * 2)
            success = resp.status_code == 200
            if success:
                logger.info(f"Sync OK: {source_node} -> {target_node}")
            return success
        except Exception as e:
            logger.error(f"Sync FAIL: {source_node} -> {target_node}: {e}")
            return False

    def repair_replica(self, data_id: str, healthy_nodes: List[str],
                       node_urls: Dict[str, str], source_node: str) -> bool:
        """Repair replica (P1: uses HMAC auth)"""
        logger.info(f"Repairing replica: {data_id}")
        source_url = node_urls.get(source_node)
        if not source_url:
            return False
        # P1: Read from source node with signature
        session = self._get_session()
        try:
            resp = session.get(url=source_url, path=f"/api/replica/get/{data_id}", timeout=self.timeout)
            if resp.status_code != 200:
                return False
            data = resp.json()
        except Exception:
            return False
        # P1: Write to target nodes with signature
        for node_id in healthy_nodes:
            if node_id == source_node:
                continue
            url = node_urls.get(node_id)
            if not url:
                continue
            try:
                session.post(url=url, path="/api/replica/store",
                    json={"data_id": data_id, "data_type": data.get("data_type", "thought"),
                          "content": data.get("content")}, timeout=self.timeout)
            except Exception as e:
                logger.warning(f"Repair write failed: {node_id}: {e}")
        return True

    def get_replication_status(self, data_id: str) -> Dict:
        replicas = self.replica_cache.get(data_id, [])
        return {"data_id": data_id, "replica_count": len(replicas),
                "replica_nodes": replicas,
                "healthy": len(replicas) >= self.replication_factor // 2 + 1}

    def clear_cache(self, data_id: Optional[str] = None) -> None:
        if data_id:
            self.replica_cache.pop(data_id, None)
        else:
            self.replica_cache.clear()
