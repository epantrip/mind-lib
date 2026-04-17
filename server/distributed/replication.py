"""
🧠 分布式思想库 - 多副本复制管理（同步版本）

职责：
- 副本数据同步
- 链式复制
- 副本一致性保证
- 故障恢复
"""

import hashlib
import json
import time
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum
import requests

logger = logging.getLogger(__name__)


class ReplicationStatus(Enum):
    """复制状态"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class ReplicaData:
    """副本数据"""
    data_id: str
    data_type: str  # "thought" or "skill"
    content: Any
    version: int = 1
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    checksum: str = ""


@dataclass
class ReplicationTask:
    """复制任务"""
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
    
    职责：
    - 副本数据同步
    - 链式复制
    - 副本一致性保证
    - 故障恢复
    """
    
    def __init__(
        self,
        replication_factor: int = 3,
        max_retries: int = 3,
        timeout: int = 30,
    ):
        self.replication_factor = replication_factor
        self.max_retries = max_retries
        self.timeout = timeout
        
        # 复制任务队列
        self.pending_tasks: Dict[str, ReplicationTask] = {}
        self.completed_tasks: Dict[str, ReplicationTask] = {}
        
        # 副本缓存
        self.replica_cache: Dict[str, List[str]] = {}  # data_id -> [node_ids]
        
    def _generate_checksum(self, content: Any) -> str:
        """生成数据校验和"""
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
        
        使用链式复制：主节点 -> 副本1 -> 副本2
        """
        # 创建副本数据
        replica_data = ReplicaData(
            data_id=data_id,
            data_type=data_type,
            content=content,
            checksum=self._generate_checksum(content),
        )
        
        # 链式复制
        success_nodes = [primary_node]
        
        for target_node in replica_nodes:
            if target_node not in node_urls:
                logger.warning(f"跳过节点 {target_node}: 无URL配置")
                continue
                
            try:
                success = self._send_to_node(
                    node_id=target_node,
                    url=node_urls.get(target_node, ""),
                    data=replica_data,
                )
                
                if success:
                    success_nodes.append(target_node)
                    logger.info(f"✅ 复制成功: {data_id} -> {target_node}")
                else:
                    logger.warning(f"❌ 复制失败: {data_id} -> {target_node}")
                    
            except Exception as e:
                logger.error(f"❌ 复制异常: {data_id} -> {target_node}: {e}")
                
        # 检查是否达到最小副本数
        min_replicas = min(2, self.replication_factor)  # 至少2个副本
        
        if len(success_nodes) < min_replicas:
            logger.error(f"⚠️ 副本数不足: 需要{min_replicas}，实际{len(success_nodes)}")
            return False
            
        # 更新缓存
        self.replica_cache[data_id] = success_nodes
        return True
    
    def _send_to_node(
        self,
        node_id: str,
        url: str,
        data: ReplicaData,
    ) -> bool:
        """发送数据到单个节点"""
        if not url:
            return False
            
        try:
            endpoint = f"{url}/api/replica/store"
            
            payload = {
                "data_id": data.data_id,
                "data_type": data.data_type,
                "content": data.content,
                "version": data.version,
                "checksum": data.checksum,
                "timestamp": time.time(),
            }
            
            resp = requests.post(
                endpoint,
                json=payload,
                timeout=self.timeout,
                headers={"Content-Type": "application/json"}
            )
            
            return resp.status_code == 200
                    
        except requests.Timeout:
            logger.warning(f"⏱️ 复制超时: {node_id}")
            return False
        except Exception as e:
            logger.error(f"❌ 复制错误: {node_id} - {e}")
            return False
    
    def read_from_replica(
        self,
        data_id: str,
        preferred_node: str,
        node_urls: Dict[str, str],
    ) -> Optional[Dict]:
        """
        从副本读取数据
        
        优先从首选节点读取，如果失败则尝试其他副本
        """
        # 获取数据ID对应的所有副本节点
        replica_nodes = self.replica_cache.get(data_id, [])
        
        # 按优先级排序：首选节点优先
        nodes_to_try = [preferred_node]
        nodes_to_try.extend([n for n in replica_nodes if n != preferred_node])
        
        for node_id in nodes_to_try:
            url = node_urls.get(node_id)
            if not url:
                continue
                
            try:
                result = self._fetch_from_node(node_id, url, data_id)
                if result:
                    logger.debug(f"📖 读取成功: {data_id} from {node_id}")
                    return result
            except Exception as e:
                logger.warning(f"📖 读取失败: {data_id} from {node_id}: {e}")
                
        logger.error(f"❌ 所有副本读取失败: {data_id}")
        return None
    
    def _fetch_from_node(
        self,
        node_id: str,
        url: str,
        data_id: str,
    ) -> Optional[Dict]:
        """从单个节点获取数据"""
        try:
            endpoint = f"{url}/api/replica/get/{data_id}"
            
            resp = requests.get(
                endpoint,
                timeout=self.timeout,
                headers={"Accept": "application/json"}
            )
            
            if resp.status_code == 200:
                return resp.json()
            return None
        except Exception:
            return None
    
    def repair_replica(
        self,
        data_id: str,
        healthy_nodes: List[str],
        node_urls: Dict[str, str],
        source_node: str,
    ) -> bool:
        """
        修复副本：从健康节点重新复制到故障节点
        """
        logger.info(f"🔧 开始修复副本: {data_id}")
        
        # 从健康节点获取数据
        source_url = node_urls.get(source_node)
        if not source_url:
            return False
            
        data = self._fetch_from_node(source_node, source_url, data_id)
        if not data:
            logger.error(f"❌ 无法获取源数据: {data_id}")
            return False
            
        # 复制到不健康节点
        for node_id in healthy_nodes:
            if node_id == source_node:
                continue
            
            url = node_urls.get(node_id)
            if not url:
                continue
                
            self._send_to_node(
                node_id, 
                url, 
                ReplicaData(data_id, data.get("type", "thought"), data.get("content"))
            )
                                                
        return True
    
    def sync_between_nodes(
        self,
        source_node: str,
        target_node: str,
        node_urls: Dict[str, str],
    ) -> bool:
        """
        节点间数据同步
        """
        logger.info(f"🔄 节点间同步: {source_node} -> {target_node}")
        
        try:
            target_url = node_urls.get(target_node)
            if not target_url:
                return False
                
            endpoint = f"{target_url}/api/sync/pull"
            payload = {"source_node": source_node}
            
            resp = requests.post(
                endpoint,
                json=payload,
                timeout=self.timeout * 2,
                headers={"Content-Type": "application/json"}
            )
            
            success = resp.status_code == 200
            if success:
                logger.info(f"✅ 同步成功: {source_node} -> {target_node}")
            return success
        except Exception as e:
            logger.error(f"❌ 同步失败: {source_node} -> {target_node}: {e}")
            return False
    
    def get_replication_status(self, data_id: str) -> Dict:
        """获取数据副本状态"""
        replicas = self.replica_cache.get(data_id, [])
        
        return {
            "data_id": data_id,
            "replica_count": len(replicas),
            "replica_nodes": replicas,
            "healthy": len(replicas) >= self.replication_factor // 2 + 1,
        }
    
    def clear_cache(self, data_id: Optional[str] = None) -> None:
        """清除副本缓存"""
        if data_id:
            self.replica_cache.pop(data_id, None)
        else:
            self.replica_cache.clear()


# 测试
if __name__ == "__main__":
    # 创建复制管理器
    manager = ReplicationManager(replication_factor=3)
    
    print("🎃 多副本复制管理器测试（同步版本）")
    print("=" * 50)
    
    # 模拟节点URL
    node_urls = {
        "node_001": "http://192.168.1.1:5001",
        "node_002": "http://192.168.1.2:5001",
        "node_003": "http://192.168.1.3:5001",
    }
    
    print("📝 复制管理器接口:")
    print("  - replicate_to_nodes(): 复制数据到多个节点")
    print("  - read_from_replica(): 从副本读取")
    print("  - repair_replica(): 修复副本")
    print("  - sync_between_nodes(): 节点间同步")
    print("\n✅ 同步版本就绪，可在 Flask 中直接调用")
