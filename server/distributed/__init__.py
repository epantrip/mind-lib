"""
Mind Library Distributed Module - Unified Entry
"""

from .coordinator import DistributedCoordinator, CoordinatorStatus
from .sharding import ConsistentHashRing, Node
from .nodes import NodeManager, ClusterNode, NodeStatus
from .replication import ReplicationManager, ReplicationStatus
from .persistence import PersistenceManager, RoutingCacheManager
from . import config

__version__ = "1.0.0"
__author__ = "Pumpking"

__all__ = [
    "DistributedCoordinator",
    "CoordinatorStatus", 
    "ConsistentHashRing",
    "Node",
    "NodeManager",
    "ClusterNode", 
    "NodeStatus",
    "ReplicationManager",
    "ReplicationStatus",
    "PersistenceManager",
    "RoutingCacheManager",
    "config",
]
