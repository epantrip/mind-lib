"""
Mind Library 分布式安全版 - 主服务器 v2.1.1 (Thread-Safe)

特性：
- 分布式集群支持（一致性哈希 + 多副本）
- API Key 安全认证
- 实例审批机制
- 速率限制
- Webhook 通知
- 线程安全（P0）
"""

import os
import json
import logging
import hashlib
import time
from datetime import datetime
from flask import Flask, request, jsonify, render_template_string

# 导入分布式模块（相对导入）
from distributed import (
    DistributedCoordinator, CoordinatorStatus,
    ConsistentHashRing, Node,
    NodeManager, ClusterNode, NodeStatus,
    ReplicationManager, ReplicationStatus
)

# 导入认证模块
from auth.api_key import create_auth, APIKeyAuth

# 导入线程安全数据存储层
from data_store import DataStore

# 导入节点间认证（P1: 分布式节点 API 签名认证）
from node_auth import get_node_auth

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Flask 应用
app = Flask(__name__)
app.config['JSON_SORT_KEYS'] = False

# ============== 初始化 ==============
# 存储路径
DB_PATH = os.environ.get('MIND_DB_PATH', '/root/mind_library')
os.makedirs(DB_PATH, exist_ok=True)

# 认证
auth = create_auth()

# 分布式协调者
coordinator = DistributedCoordinator(node_id='mind_hub_primary')

# 线程安全数据存储层（P0: 并发安全）
store = DataStore(DB_PATH)

# 节点间认证（P1）
node_auth = get_node_auth()


def notify_webhook(payload):
    """发送 Webhook 通知（网络 I/O，在锁外调用）"""
    webhook_url = os.environ.get('MIND_NOTIFICATION_WEBHOOK')
    if not webhook_url:
        return
    
    try:
        import requests
        requests.post(webhook_url, json=payload, timeout=5)
        logger.info(f"Webhook 通知已发送: {payload.get('event')}")
    except Exception as e:
        logger.warning(f"Webhook 通知失败: {e}")


# ============== 路由 ==============

@app.route('/')
def index():
    """Web 仪表盘"""
    stats = store.get_stats()
    stats.update({
        'version': '2.1.1',
        'coordinator_status': coordinator.status.value,
        'cluster_nodes': len(coordinator.node_manager.nodes),
    })
    
    html = '''<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Mind Library v2.1.1</title>
<style>
body{font-family:Arial,sans-serif;max-width:800px;margin:0 auto;padding:20px;background:#f5f5f5}
h1{color:#333}.card{background:white;border-radius:8px;padding:20px;margin:10px 0;box-shadow:0 2px 4px rgba(0,0,0,0.1)}
.stat{font-size:24px;font-weight:bold;color:#4CAF50}.label{color:#666}
.status{color:#2196F3;font-weight:bold}.status-standby{color:#FF9800}
</style></head>
<body>
<h1>Mind Library v2.1.1</h1>
<div class="card">
<h2>系统状态</h2>
<p><span class="label">版本:</span> <span class="stat">{{stats.version}}</span></p>
<p><span class="label">思想数量:</span> <span class="stat">{{stats.thoughts}}</span></p>
<p><span class="label">技能数量:</span> <span class="stat">{{stats.skills}}</span></p>
<p><span class="label">已批准实例:</span> <span class="stat">{{stats.approved_instances}}</span></p>
<p><span class="label">待审批:</span> <span class="stat">{{stats.pending_instances}}</span></p>
</div>
<div class="card">
<h2>分布式集群</h2>
<p><span class="label">协调者状态:</span> <span class="status">{{stats.coordinator_status}}</span></p>
<p><span class="label">集群节点:</span> <span class="stat">{{stats.cluster_nodes}}</span></p>
</div>
<div class="card">
<h2>API 端点</h2>
<p><a href="/api/health">/api/health</a> - 健康检查</p>
<p><a href="/api/stats">/api/stats</a> - 统计信息</p>
<p><a href="/api/instances">/api/instances</a> - 实例列表（需认证）</p>
</div>
</body></html>'''
    return render_template_string(html, stats=stats)


@app.route('/api/health')
def health():
    """健康检查"""
    return jsonify({
        'status': 'ok',
        'version': '2.1.1',
        'distributed': True,
        'secure': True,
        'thread_safe': True,
        'timestamp': datetime.now().isoformat()
    })


@app.route('/api/stats')
def stats():
    """统计信息"""
    stats_data = store.get_stats()
    stats_data.update({
        'coordinator': {
            'status': coordinator.status.value,
            'nodes': len(coordinator.node_manager.nodes),
            'replication': coordinator.replication_manager.status.value if hasattr(coordinator.replication_manager, 'status') else 'active'
        }
    })
    return jsonify(stats_data)


# ============== 客户端 API ==============

@app.route('/api/register', methods=['POST'])
def register():
    """注册新实例"""
    data = request.get_json() or {}
    instance_id = data.get('instance_id')
    instance_name = data.get('instance_name', instance_id)
    description = data.get('description', '')
    
    if not instance_id:
        return jsonify({'error': 'instance_id is required'}), 400
    
    if store.instance_exists(instance_id):
        return jsonify({'error': 'Instance already exists'}), 409
    
    # 生成 Token
    token = hashlib.sha256(f"{instance_id}_{time.time()}".encode()).hexdigest()[:32]
    
    instance = {
        'id': instance_id,
        'name': instance_name,
        'description': description,
        'approved': False,  # 需要审批
        'token': token,
        'created_at': datetime.now().isoformat(),
        'last_seen': time.time()
    }
    
    # 写存储（线程安全）
    store.add_instance(instance)
    
    # Webhook 通知（在锁外）
    notify_webhook({
        'event': 'new_instance_registration',
        'message': f'New instance {instance_id} ({instance_name}) registered and awaiting approval',
        'timestamp': datetime.now().isoformat(),
        'instance': instance
    })
    
    return jsonify({
        'message': 'Registration submitted, awaiting approval',
        'instance_id': instance_id,
        'token': token
    })


@app.route('/api/ping', methods=['POST'])
def ping():
    """实例心跳"""
    data = request.get_json() or {}
    instance_id = data.get('instance_id')
    
    if instance_id and store.instance_exists(instance_id):
        store.update_instance(instance_id, {'last_seen': time.time()})
    
    return jsonify({'status': 'ok', 'timestamp': time.time()})


@app.route('/api/download/thoughts')
def download_thoughts():
    """下载思想（需认证）"""
    api_key = request.headers.get('X-API-Key')
    instance_id = request.headers.get('X-Instance-ID')
    
    if not api_key or not instance_id:
        return jsonify({'error': 'Missing credentials'}), 401
    
    if not auth.verify_client(instance_id, api_key):
        return jsonify({'error': 'Invalid credentials'}), 401
    
    if not auth.check_rate_limit(instance_id):
        return jsonify({'error': 'Rate limit exceeded'}), 429
    
    # 过滤参数
    thought_type = request.args.get('type')
    since = request.args.get('since', '0')
    
    # 读存储（线程安全）
    result = store.get_thoughts(since=since, thought_type=thought_type)
    
    return jsonify({'thoughts': result, 'count': len(result)})


@app.route('/api/download/skills')
def download_skills():
    """下载技能（需认证）"""
    api_key = request.headers.get('X-API-Key')
    instance_id = request.headers.get('X-Instance-ID')
    
    if not api_key or not instance_id:
        return jsonify({'error': 'Missing credentials'}), 401
    
    if not auth.verify_client(instance_id, api_key):
        return jsonify({'error': 'Invalid credentials'}), 401
    
    if not auth.check_rate_limit(instance_id):
        return jsonify({'error': 'Rate limit exceeded'}), 429
    
    # 读存储（线程安全）
    skills = store.get_skills()
    
    return jsonify({'skills': skills, 'count': len(skills)})


@app.route('/api/upload/thought', methods=['POST'])
def upload_thought():
    """上传思想（需认证+审批）"""
    api_key = request.headers.get('X-API-Key')
    instance_id = request.headers.get('X-Instance-ID')
    
    if not api_key or not instance_id:
        return jsonify({'error': 'Missing credentials'}), 401
    
    if not auth.verify_client(instance_id, api_key):
        return jsonify({'error': 'Invalid credentials'}), 401
    
    if not auth.check_rate_limit(instance_id):
        return jsonify({'error': 'Rate limit exceeded'}), 429
    
    # 检查实例是否已批准（线程安全）
    if not store.is_instance_approved(instance_id):
        return jsonify({'error': 'Instance not approved'}), 403
    
    data = request.get_json() or {}
    
    thought = {
        'id': hashlib.sha256(f"{time.time()}_{instance_id}".encode()).hexdigest()[:16],
        'type': data.get('type', 'insight'),
        'title': data.get('title', ''),
        'content': data.get('content', ''),
        'instance_id': instance_id,
        'created_at': datetime.now().isoformat(),
        'tags': data.get('tags', [])
    }
    
    # 写存储（线程安全，锁内完成内存+磁盘）
    store.add_thought(thought)
    
    # 分布式：同步到其他节点（在锁外，网络 I/O）
    coordinator.sync_thought(thought)
    
    return jsonify({'status': 'ok', 'thought_id': thought['id']})


@app.route('/api/upload/skill', methods=['POST'])
def upload_skill():
    """上传技能（需认证）"""
    api_key = request.headers.get('X-API-Key')
    instance_id = request.headers.get('X-Instance-ID')
    
    if not api_key or not instance_id:
        return jsonify({'error': 'Missing credentials'}), 401
    
    if not auth.verify_client(instance_id, api_key):
        return jsonify({'error': 'Invalid credentials'}), 401
    
    if not auth.check_rate_limit(instance_id):
        return jsonify({'error': 'Rate limit exceeded'}), 429
    
    # 检查实例是否已批准
    if not store.is_instance_approved(instance_id):
        return jsonify({'error': 'Instance not approved'}), 403
    
    data = request.get_json() or {}
    
    skill = {
        'id': data.get('id') or hashlib.sha256(f"{time.time()}_{instance_id}".encode()).hexdigest()[:16],
        'name': data.get('name', ''),
        'description': data.get('description', ''),
        'category': data.get('category', 'general'),
        'content': data.get('content', ''),
        'instance_id': instance_id,
        'created_at': datetime.now().isoformat(),
        'version': data.get('version', '1.0.0')
    }
    
    # 写存储（线程安全）
    store.add_skill(skill)
    
    return jsonify({'status': 'ok', 'skill_id': skill['id']})


@app.route('/api/instances')
def list_instances():
    """列出实例（需管理员）"""
    api_key = request.headers.get('X-API-Key')
    
    if not api_key or not auth.verify_admin(api_key):
        return jsonify({'error': 'Unauthorized'}), 401
    
    instances = store.get_instances()
    return jsonify({'instances': list(instances.values())})


# ============== 管理员 API ==============

@app.route('/api/admin/approve_instance', methods=['POST'])
def approve_instance():
    """批准实例"""
    api_key = request.headers.get('X-API-Key')
    if not api_key or not auth.verify_admin(api_key):
        return jsonify({'error': 'Unauthorized'}), 401
    
    data = request.get_json() or {}
    instance_id = data.get('instance_id')
    
    instance = store.get_instance(instance_id)
    if not instance:
        return jsonify({'error': 'Instance not found'}), 404
    
    # 更新实例（线程安全）
    store.update_instance(instance_id, {'approved': True})
    
    return jsonify({'status': 'ok', 'message': f'Instance {instance_id} approved'})


@app.route('/api/admin/revoke_instance', methods=['POST'])
def revoke_instance():
    """撤销实例"""
    api_key = request.headers.get('X-API-Key')
    if not api_key or not auth.verify_admin(api_key):
        return jsonify({'error': 'Unauthorized'}), 401
    
    data = request.get_json() or {}
    instance_id = data.get('instance_id')
    
    # 删除实例（线程安全）
    store.delete_instance(instance_id)
    
    return jsonify({'status': 'ok', 'message': f'Instance {instance_id} revoked'})


@app.route('/api/admin/add_client_key', methods=['POST'])
def add_client_key():
    """添加客户端 Key"""
    api_key = request.headers.get('X-API-Key')
    if not api_key or not auth.verify_admin(api_key):
        return jsonify({'error': 'Unauthorized'}), 401
    
    data = request.get_json() or {}
    instance_id = data.get('instance_id')
    new_key = data.get('api_key')
    
    if not instance_id or not new_key:
        return jsonify({'error': 'instance_id and api_key required'}), 400
    
    # 在认证系统中添加 key
    auth.client_keys[instance_id] = new_key
    
    # 更新实例（线程安全）
    if store.instance_exists(instance_id):
        store.update_instance(instance_id, {'token': new_key, 'approved': True})
    
    return jsonify({'status': 'ok', 'message': f'API key added for {instance_id}'})


# ============== 分布式集群 API ==============

@app.route('/api/cluster/nodes')
@auth.require_admin
def cluster_nodes():
    """列出集群节点"""
    return jsonify({
        'nodes': [
            {
                'node_id': n.node_id,
                'host': n.host,
                'port': n.port,
                'status': n.status.value,
                'storage_used': n.storage_used_gb
            }
            for n in coordinator.node_manager.nodes.values()
        ]
    })


@app.route('/api/cluster/add_node', methods=['POST'])
def add_cluster_node():
    """添加集群节点（需管理员）"""
    api_key = request.headers.get('X-API-Key')
    if not api_key or not auth.verify_admin(api_key):
        return jsonify({'error': 'Unauthorized'}), 401
    
    data = request.get_json() or {}
    node_id = data.get('node_id')
    host = data.get('host')
    port = data.get('port', 5000)
    
    if not node_id or not host:
        return jsonify({'error': 'node_id and host required'}), 400
    
    coordinator.add_node(node_id, host, port)
    
    return jsonify({'status': 'ok', 'message': f'Node {node_id} added'})


@app.route('/api/cluster/remove_node', methods=['POST'])
def remove_cluster_node():
    """移除集群节点（需管理员）"""
    api_key = request.headers.get('X-API-Key')
    if not api_key or not auth.verify_admin(api_key):
        return jsonify({'error': 'Unauthorized'}), 401
    
    data = request.get_json() or {}
    node_id = data.get('node_id')
    
    coordinator.remove_node(node_id)
    
    return jsonify({'status': 'ok', 'message': f'Node {node_id} removed'})


@app.route('/api/cluster/status')
@auth.require_admin
def cluster_status():
    """获取集群详细状态"""
    return jsonify(coordinator.get_cluster_status())


# ============== 副本存储 API（分布式节点间通信）=============

@app.route('/api/replica/store', methods=['POST'])
@node_auth.require_node_auth
def replica_store():
    """存储副本数据（节点间调用）"""
    data = request.get_json() or {}
    data_id = data.get('data_id')
    data_type = data.get('data_type')
    content = data.get('content')
    
    if not data_id or not content:
        return jsonify({'error': 'data_id and content required'}), 400
    
    # 存储副本（线程安全）
    success = store.replica_store(data_id, data_type, content)
    
    return jsonify({'status': 'ok', 'data_id': data_id})


@app.route('/api/replica/get/<data_id>')
@node_auth.require_node_auth
def replica_get(data_id):
    """获取副本数据（节点间调用）"""
    # 读取副本（线程安全）
    result = store.replica_get(data_id)
    
    if result:
        return jsonify({
            'data_id': data_id,
            **result
        })
    
    return jsonify({'found': False, 'data_id': data_id})


@app.route('/api/sync/pull', methods=['POST'])
@node_auth.require_node_auth
def sync_pull():
    """节点间数据同步拉取"""
    data = request.get_json() or {}
    source_node = data.get('source_node')
    
    # 获取全部数据（线程安全）
    sync_data = store.get_all_for_sync()
    sync_data['timestamp'] = datetime.now().isoformat()
    
    return jsonify(sync_data)


# ============== P2: 数据迁移 API（分布式节点间通信）==============
# P1: 需 HMAC 签名认证
# 用途：节点加入时，旧节点返回应迁移给该节点的数据列表

@app.route('/api/replica/migrate')
@node_auth.require_node_auth
def replica_migrate():
    """
    返回应迁移给目标节点的数据列表

    Query params:
        target: 目标节点 ID（迁移数据的新归属节点）

    逻辑：
    1. 遍历本地存储的所有 data_id
    2. 对每个 data_id，用 hash_ring 计算现在应该属于哪些节点
    3. 如果 target 在目标节点列表中，说明这个数据应该迁到 target
    4. 返回所有应迁移的数据
    """
    from distributed.sharding import ConsistentHashRing, Node

    target_node = request.args.get('target', '')

    if not target_node:
        return jsonify({'error': 'target node ID required'}), 400

    # 获取本地所有数据
    all_thoughts = store.get_all_thoughts()
    all_skills = store.get_skills()  # get_skills() 无参数=返回全部

    items = []

    # 计算每个 thought 应该属于哪个节点
    for thought in all_thoughts:
        data_id = thought.get('id', '')
        if not data_id:
            continue
        # 用一致性哈希判断该数据现在属于哪些节点
        # 协调者的 hash_ring 直接算
        primary = coordinator.hash_ring.get_primary_node(data_id)
        replicas = coordinator.hash_ring.get_replica_nodes(
            data_id, coordinator.replication_factor
        )
        target_nodes = [primary] + (replicas[1:] if len(replicas) > 1 else [])

        if target_node in target_nodes:
            items.append({
                'data_id': data_id,
                'data_type': 'thought',
                'content': thought,
            })

    # 计算每个 skill
    for skill in all_skills:
        data_id = skill.get('id', '')
        if not data_id:
            continue
        primary = coordinator.hash_ring.get_primary_node(data_id)
        replicas = coordinator.hash_ring.get_replica_nodes(
            data_id, coordinator.replication_factor
        )
        target_nodes = [primary] + (replicas[1:] if len(replicas) > 1 else [])

        if target_node in target_nodes:
            items.append({
                'data_id': data_id,
                'data_type': 'skill',
                'content': skill,
            })

    logger.info(f"[Migrate] 返回 {len(items)} 条应迁移数据到 {target_node}")
    return jsonify({'target': target_node, 'items': items})


# ============== 错误处理 ==============

@app.errorhandler(404)
def not_found(e):
    return jsonify({'error': 'Not found', 'code': 'NOT_FOUND'}), 404


@app.errorhandler(500)
def server_error(e):
    logger.error(f"Server error: {e}")
    return jsonify({'error': 'Internal server error', 'code': 'INTERNAL_ERROR'}), 500


@app.errorhandler(429)
def rate_limited(e):
    return jsonify({'error': 'Rate limit exceeded', 'code': 'RATE_LIMIT'}), 429


# ============== 启动 ==============

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('DEBUG', 'false').lower() == 'true'
    
    print("=" * 50)
    print("Mind Library v2.1.1 分布式安全版 (Thread-Safe)")
    print("=" * 50)
    print(f"存储路径: {DB_PATH}")
    print(f"监听端口: {port}")
    print(f"认证: API Key + 实例审批")
    print(f"分布式: 启用")
    print(f"线程安全: 启用 (RLock)")
    print("=" * 50)
    
    app.run(host='0.0.0.0', port=port, debug=debug)
