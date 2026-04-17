#!/usr/bin/env python3
"""
Mind Library v2.1 - Distributed Module Tests

Tests for:
- Consistent Hash Ring
- Node Manager
- Replication Manager
- Coordinator
"""

import unittest
import sys
import os

# Add server directory to path
server_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
server_dir = os.path.join(server_dir, 'server')
sys.path.insert(0, server_dir)

from distributed import (
    ConsistentHashRing, Node,
    NodeManager, ClusterNode, NodeStatus,
    ReplicationManager, ReplicationStatus,
    DistributedCoordinator, CoordinatorStatus
)


class TestConsistentHashRing(unittest.TestCase):
    """Test consistent hash ring"""
    
    def setUp(self):
        self.ring = ConsistentHashRing(virtual_nodes=150)
        self.nodes = [
            Node("node_001", "192.168.1.1", 5000),
            Node("node_002", "192.168.1.2", 5000),
            Node("node_003", "192.168.1.3", 5000),
        ]
    
    def test_add_node(self):
        """Test adding nodes"""
        self.ring.add_node(self.nodes[0])
        self.assertEqual(len(self.ring.nodes), 1)
        # Check virtual nodes exist in ring
        self.assertGreater(len(self.ring.ring), 0)
    
    def test_remove_node(self):
        """Test removing nodes"""
        for node in self.nodes:
            self.ring.add_node(node)
        
        self.ring.remove_node("node_001")
        self.assertEqual(len(self.ring.nodes), 2)
    
    def test_get_primary_node(self):
        """Test getting primary node for data"""
        for node in self.nodes:
            self.ring.add_node(node)
        
        # Same key should always map to same node
        node1 = self.ring.get_primary_node("thought_001")
        node2 = self.ring.get_primary_node("thought_001")
        self.assertEqual(node1, node2)
    
    def test_get_replica_nodes(self):
        """Test getting replica nodes"""
        for node in self.nodes:
            self.ring.add_node(node)
        
        replicas = self.ring.get_replica_nodes("thought_001", 3)
        self.assertEqual(len(replicas), 3)
        # All replicas should be different
        self.assertEqual(len(set(replicas)), 3)
    
    def test_distribution(self):
        """Test data distribution across nodes"""
        for node in self.nodes:
            self.ring.add_node(node)
        
        # Distribute 1000 keys
        distribution = {}
        for i in range(1000):
            node = self.ring.get_primary_node(f"key_{i}")
            distribution[node] = distribution.get(node, 0) + 1
        
        # Each node should have roughly 1/3 of the data
        for node_id, count in distribution.items():
            self.assertGreater(count, 200)  # At least 20% of data
            self.assertLess(count, 500)     # At most 50% of data


class TestNodeManager(unittest.TestCase):
    """Test node manager"""
    
    def setUp(self):
        self.manager = NodeManager(
            heartbeat_interval=30,
            failure_threshold=3,
            storage_limit_gb=100
        )
    
    def test_register_node(self):
        """Test node registration"""
        result = self.manager.register_node("node_001", "192.168.1.1", 5000)
        self.assertTrue(result)
        self.assertEqual(len(self.manager.nodes), 1)
    
    def test_unregister_node(self):
        """Test node unregistration"""
        self.manager.register_node("node_001", "192.168.1.1", 5000)
        result = self.manager.unregister_node("node_001")
        self.assertTrue(result)
        self.assertEqual(len(self.manager.nodes), 0)
    
    def test_heartbeat(self):
        """Test node heartbeat"""
        self.manager.register_node("node_001", "192.168.1.1", 5000)
        result = self.manager.heartbeat("node_001", storage_used_gb=10.5)
        self.assertTrue(result)
        
        node = self.manager.get_node("node_001")
        self.assertEqual(node.storage_used_gb, 10.5)
        self.assertEqual(node.status, NodeStatus.ONLINE)
    
    def test_get_online_nodes(self):
        """Test getting online nodes"""
        self.manager.register_node("node_001", "192.168.1.1", 5000)
        self.manager.register_node("node_002", "192.168.1.2", 5000)
        self.manager.heartbeat("node_001")
        
        # Both nodes are registered as online by default
        online = self.manager.get_online_nodes()
        self.assertEqual(len(online), 2)
    
    def test_cluster_stats(self):
        """Test cluster statistics"""
        self.manager.register_node("node_001", "192.168.1.1", 5000)
        self.manager.heartbeat("node_001", storage_used_gb=25)
        
        stats = self.manager.get_cluster_stats()
        self.assertEqual(stats['total_nodes'], 1)
        self.assertEqual(stats['online_nodes'], 1)
        self.assertEqual(stats['used_storage_gb'], 25)


class TestReplicationManager(unittest.TestCase):
    """Test replication manager"""
    
    def setUp(self):
        self.manager = ReplicationManager(replication_factor=3)
    
    def test_checksum_generation(self):
        """Test data checksum"""
        content1 = {"key": "value"}
        content2 = {"key": "different"}
        
        checksum1 = self.manager._generate_checksum(content1)
        checksum2 = self.manager._generate_checksum(content1)
        checksum3 = self.manager._generate_checksum(content2)
        
        self.assertEqual(checksum1, checksum2)
        self.assertNotEqual(checksum1, checksum3)
    
    def test_replica_cache(self):
        """Test replica cache"""
        data_id = "test_001"
        nodes = ["node_001", "node_002", "node_003"]
        
        self.manager.replica_cache[data_id] = nodes
        
        status = self.manager.get_replication_status(data_id)
        self.assertEqual(status['replica_count'], 3)
        self.assertTrue(status['healthy'])
    
    def test_clear_cache(self):
        """Test cache clearing"""
        self.manager.replica_cache["test_001"] = ["node_001"]
        self.manager.replica_cache["test_002"] = ["node_002"]
        
        self.manager.clear_cache("test_001")
        self.assertNotIn("test_001", self.manager.replica_cache)
        self.assertIn("test_002", self.manager.replica_cache)
        
        self.manager.clear_cache()
        self.assertEqual(len(self.manager.replica_cache), 0)


class TestDistributedCoordinator(unittest.TestCase):
    """Test distributed coordinator"""
    
    def setUp(self):
        self.coord = DistributedCoordinator(node_id="test_coordinator")
    
    def test_add_node(self):
        """Test adding cluster node"""
        result = self.coord.add_node("node_001", "192.168.1.1", 5000)
        self.assertTrue(result)
        self.assertEqual(len(self.coord.node_manager.nodes), 1)
    
    def test_remove_node(self):
        """Test removing cluster node"""
        self.coord.add_node("node_001", "192.168.1.1", 5000)
        result = self.coord.remove_node("node_001")
        self.assertTrue(result)
        self.assertEqual(len(self.coord.node_manager.nodes), 0)
    
    def test_data_id_generation(self):
        """Test data ID generation"""
        id1 = self.coord._get_data_id("thought", "key1")
        id2 = self.coord._get_data_id("thought", "key1")
        id3 = self.coord._get_data_id("thought", "key2")
        
        self.assertEqual(id1, id2)
        self.assertNotEqual(id1, id3)
    
    def test_routing_cache(self):
        """Test routing cache"""
        self.coord.add_node("node_001", "192.168.1.1", 5000)
        self.coord.add_node("node_002", "192.168.1.2", 5000)
        
        data_id = "test_data_001"
        primary, replicas = self.coord.get_storage_nodes(data_id)
        
        # Cache should be populated
        self.assertIn(data_id, self.coord.routing_cache)
    
    def test_cluster_status(self):
        """Test cluster status"""
        self.coord.add_node("node_001", "192.168.1.1", 5000)
        
        status = self.coord.get_cluster_status()
        
        self.assertEqual(status['coordinator']['node_id'], "test_coordinator")
        self.assertEqual(status['coordinator']['status'], "active")
        self.assertIn('metrics', status)


class TestIntegration(unittest.TestCase):
    """Integration tests"""
    
    def test_full_workflow(self):
        """Test complete workflow"""
        # Create coordinator
        coord = DistributedCoordinator()
        
        # Add nodes
        coord.add_node("node_001", "192.168.1.1", 5000)
        coord.add_node("node_002", "192.168.1.2", 5000)
        coord.add_node("node_003", "192.168.1.3", 5000)
        
        # Get routing info
        routing = coord.get_routing_info("thought", "test_001")
        
        self.assertIsNotNone(routing['primary_node'])
        self.assertGreaterEqual(len(routing['replica_nodes']), 2)
        
        # Check cluster status
        status = coord.get_cluster_status()
        self.assertEqual(status['nodes']['total_nodes'], 3)


if __name__ == '__main__':
    unittest.main(verbosity=2)
