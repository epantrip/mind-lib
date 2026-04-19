"""
Mind Library 分布式安全版 - 主服务器 v2.2.0 (Thread-Safe)

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
import uuid
from datetime import datetime
from flask import Flask, request, jsonify, render_template_string, make_response

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

# 导入生产配置
from config import Config

# 配置日志（生产优先）
Config.setup_logging()
logger = logging.getLogger(__name__)

# Flask 应用
app = Flask(__name__)
app.config['JSON_SORT_KEYS'] = False

# ============== 初始化 ==============
# 启动时校验配置
Config.validate()

# 存储路径
DB_PATH = Config.DB_PATH
os.makedirs(DB_PATH, exist_ok=True)

# 认证（持久化存储 + 环境变量加载客户端密钥）
# store 必须在 auth 之前初始化，因为 create_auth 需要 store.get_client_keys()
store = DataStore(DB_PATH)
auth = create_auth(persisted_keys=store.get_client_keys())
auth.set_store(store)  # 注入 DataStore，供 require_client(require_approved=True) 使用

# 分布式协调者（参数由 distributed.config.CLUSTER_CONFIG 提供）
# 但先用 Config 的 env 覆盖，以支持运行时配置
from distributed.config import CLUSTER_CONFIG
CLUSTER_CONFIG['virtual_nodes'] = Config.VIRTUAL_NODES
CLUSTER_CONFIG['heartbeat_interval'] = Config.HEARTBEAT_INTERVAL
CLUSTER_CONFIG['failure_threshold'] = Config.FAILURE_THRESHOLD
CLUSTER_CONFIG['storage_limit_gb'] = Config.STORAGE_LIMIT // 1000  # 思想数→GB 近似

coordinator = DistributedCoordinator(
    node_id=Config.NODE_ID,
    replication_factor=Config.REPLICA_FACTOR,
)

# 节点间认证（P1）
node_auth = get_node_auth()

# Webhook（从 Config 读取）
webhook_url = Config.WEBHOOK_URL


# ============== CORS + 请求追踪中间件 ==============

@app.before_request
def add_cors_and_request_id():
    """每个请求添加 CORS 头和请求 ID，方便追踪。"""
    # 生成请求 ID
    request_id = request.headers.get('X-Request-ID') or str(uuid.uuid4())[:8]
    request._request_id = request_id  # 存到 request 对象上

    # CORS 响应头
    if Config.CORS_ORIGINS:
        origins = [o.strip() for o in Config.CORS_ORIGINS.split(',')]
        origin = request.headers.get('Origin', '')
        if origin in origins:
            resp = make_response()
            resp.headers['Access-Control-Allow-Origin'] = origin
            resp.headers['Access-Control-Allow-Headers'] = (
                'Content-Type, X-API-Key, X-Instance-ID, X-Node-Signature, X-Node-ID, X-Request-ID'
            )
            resp.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
            resp.headers['Access-Control-Max-Age'] = '3600'
            # Flask 会自动处理 OPTIONS 预检，但在这里先设置头
            if request.method == 'OPTIONS':
                resp.status_code = 204
                return resp

    # 记录请求（带请求 ID）
    logger.info(f"[{request_id}] {request.method} {request.path}")


@app.after_request
def add_response_headers(response):
    """每个响应添加安全头和请求 ID。"""
    request_id = getattr(request, '_request_id', None)
    if request_id:
        response.headers['X-Request-ID'] = request_id
    # 安全头
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    return response


def notify_webhook(payload):
    """发送 Webhook 通知（网络 I/O，在锁外调用）"""
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
        'version': '2.2.0',
        'coordinator_status': coordinator.status.value,
        'cluster_nodes': len(coordinator.node_manager.nodes),
    })
    
    html = '''<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Mind Library v2.2.0</title>
<style>
body{font-family:Arial,sans-serif;max-width:800px;margin:0 auto;padding:20px;background:#f5f5f5}
h1{color:#333}.card{background:white;border-radius:8px;padding:20px;margin:10px 0;box-shadow:0 2px 4px rgba(0,0,0,0.1)}
.stat{font-size:24px;font-weight:bold;color:#4CAF50}.label{color:#666}
.status{color:#2196F3;font-weight:bold}.status-standby{color:#FF9800}
</style></head>
<body>
<h1>Mind Library v2.2.0</h1>
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
        'version': '2.2.0',
        'distributed': True,
        'secure': True,
        'thread_safe': True,
        'timestamp': datetime.now().isoformat()
    })


@app.route('/api/stats')
@auth.require_admin
def stats():
    """统计信息（需管理员认证）"""
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
    """注册新实例 — 自动生成 API Key，无需手动配置环境变量"""
    data = request.get_json() or {}
    instance_id = data.get('instance_id')
    instance_name = data.get('instance_name', instance_id)
    description = data.get('description', '')
    
    if not instance_id:
        return jsonify({'error': 'instance_id is required'}), 400
    
    if store.instance_exists(instance_id):
        return jsonify({'error': 'Instance already exists'}), 409
    
    # 生成 API Key（同时作为实例 token 和认证凭据）
    api_key = hashlib.sha256(f"{instance_id}_{time.time()}".encode()).hexdigest()[:32]
    
    instance = {
        'id': instance_id,
        'name': instance_name,
        'description': description,
        'approved': False,  # 需要审批
        'token': api_key,
        'created_at': datetime.now().isoformat(),
        'last_seen': time.time()
    }
    
    # 写存储（线程安全）
    store.add_instance(instance)
    
    # 持久化 API Key（auth 内存 + DataStore 磁盘，重启不丢失）
    auth.add_client_key(instance_id, api_key)
    store.save_client_key(instance_id, api_key)
    
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
        'api_key': api_key,
        'approved': False,
        'note': 'Use X-API-Key and X-Instance-ID headers for authenticated requests. Upload requires admin approval.'
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
@auth.require_client
def download_thoughts():
    """下载思想（需认证）"""
    instance_id = request.instance_id
    
    # 过滤参数
    thought_type = request.args.get('type')
    since = request.args.get('since', '0')
    
    # 读存储（线程安全）
    result = store.get_thoughts(since=since, thought_type=thought_type)
    
    return jsonify({'thoughts': result, 'count': len(result)})


@app.route('/api/download/skills')
@auth.require_client
def download_skills():
    """下载技能（需认证）"""
    
    # 读存储（线程安全）
    skills = store.get_skills()
    
    return jsonify({'skills': skills, 'count': len(skills)})


@app.route('/api/upload/thought', methods=['POST'])
@auth.require_client(require_approved=True)
def upload_thought():
    """上传思想（需认证+审批）"""
    instance_id = request.instance_id
    
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
@auth.require_client(require_approved=True)
def upload_skill():
    """上传技能（需认证+审批）"""
    instance_id = request.instance_id
    
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
@auth.require_admin
def list_instances():
    """列出实例（需管理员）"""
    instances = store.get_instances()
    return jsonify({'instances': list(instances.values())})


# ============== 管理员 API ==============

@app.route('/api/admin/approve_instance', methods=['POST'])
@auth.require_admin
def approve_instance():
    """批准实例"""
    
    data = request.get_json() or {}
    instance_id = data.get('instance_id')
    
    instance = store.get_instance(instance_id)
    if not instance:
        return jsonify({'error': 'Instance not found'}), 404
    
    # 更新实例（线程安全）
    store.update_instance(instance_id, {'approved': True})
    
    return jsonify({'status': 'ok', 'message': f'Instance {instance_id} approved'})


@app.route('/api/admin/revoke_instance', methods=['POST'])
@auth.require_admin
def revoke_instance():
    """撤销实例"""
    
    data = request.get_json() or {}
    instance_id = data.get('instance_id')
    
    # 删除实例（线程安全）
    store.delete_instance(instance_id)
    
    return jsonify({'status': 'ok', 'message': f'Instance {instance_id} revoked'})


@app.route('/api/admin/add_client_key', methods=['POST'])
@auth.require_admin
def add_client_key():
    """添加/更新客户端 Key（持久化到磁盘，重启不丢失）"""
    
    data = request.get_json() or {}
    instance_id = data.get('instance_id')
    new_key = data.get('api_key')
    
    if not instance_id or not new_key:
        return jsonify({'error': 'instance_id and api_key required'}), 400
    
    # auth 内存 + DataStore 磁盘双重持久化
    auth.add_client_key(instance_id, new_key)
    store.save_client_key(instance_id, new_key)
    
    # 如果实例已存在，同步更新 token 和审批状态
    if store.instance_exists(instance_id):
        store.update_instance(instance_id, {'token': new_key, 'approved': True})
    
    logger.info(f"[Admin] 客户端 Key 已添加: instance={instance_id}")
    return jsonify({'status': 'ok', 'message': f'API key added for {instance_id}', 'approved': True})


@app.route('/api/admin/remove_client_key', methods=['POST'])
@auth.require_admin
def remove_client_key():
    """移除客户端 Key（同时从 auth 内存和磁盘删除）"""
    
    data = request.get_json() or {}
    instance_id = data.get('instance_id')
    
    if not instance_id:
        return jsonify({'error': 'instance_id required'}), 400
    
    auth.remove_client_key(instance_id)
    store.remove_client_key(instance_id)
    
    logger.info(f"[Admin] 客户端 Key 已移除: instance={instance_id}")
    return jsonify({'status': 'ok', 'message': f'API key removed for {instance_id}'})


@app.route('/api/admin/list_client_keys')
@auth.require_admin
def list_client_keys():
    """列出所有已注册的客户端 Key（不暴露密钥值）"""
    return jsonify({'client_keys': auth.list_client_keys()})


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
@auth.require_admin
def add_cluster_node():
    """添加集群节点（需管理员）"""
    
    data = request.get_json() or {}
    node_id = data.get('node_id')
    host = data.get('host')
    port = data.get('port', 5000)
    
    if not node_id or not host:
        return jsonify({'error': 'node_id and host required'}), 400
    
    coordinator.add_node(node_id, host, port)
    
    return jsonify({'status': 'ok', 'message': f'Node {node_id} added'})


@app.route('/api/cluster/remove_node', methods=['POST'])
@auth.require_admin
def remove_cluster_node():
    """移除集群节点（需管理员）"""
    
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
    request_id = getattr(request, '_request_id', None)
    resp = jsonify({'error': 'Not found', 'code': 'NOT_FOUND'})
    if request_id:
        resp.headers['X-Request-ID'] = request_id
    return resp, 404


@app.errorhandler(500)
def server_error(e):
    request_id = getattr(request, '_request_id', None)
    logger.error(f"[{request_id}] Server error: {e}", exc_info=True)
    resp = jsonify({
        'error': 'Internal server error',
        'code': 'INTERNAL_ERROR',
        'request_id': request_id
    })
    if request_id:
        resp.headers['X-Request-ID'] = request_id
    return resp, 500


@app.errorhandler(429)
def rate_limited(e):
    request_id = getattr(request, '_request_id', None)
    resp = jsonify({'error': 'Rate limit exceeded', 'code': 'RATE_LIMIT'})
    if request_id:
        resp.headers['X-Request-ID'] = request_id
    return resp, 429


@app.errorhandler(Exception)
def unhandled_exception(e):
    """未捕获的异常兜底，避免服务器崩溃"""
    request_id = getattr(request, '_request_id', None)
    logger.exception(f"[{request_id}] Unhandled exception: {e}")
    resp = jsonify({
        'error': 'Internal server error',
        'code': 'UNHANDLED_EXCEPTION',
        'request_id': request_id
    })
    if request_id:
        resp.headers['X-Request-ID'] = request_id
    return resp, 500


# ============== 启动 ==============

if __name__ == '__main__':
    print("=" * 50)
    print("Mind Library v2.2.0 分布式安全版 (Thread-Safe)")
    print("=" * 50)
    print(f"节点 ID:       {Config.NODE_ID}")
    print(f"存储路径:      {Config.DB_PATH}")
    print(f"持久化目录:    {Config.PERSIST_DIR}")
    print(f"监听地址:      {Config.HOST}:{Config.PORT}")
    print(f"日志级别:      {Config.LOG_LEVEL} {'(JSON)' if Config.LOG_JSON else ''}")
    print(f"CORS 来源:     {Config.CORS_ORIGINS or '(未配置)'}")
    print(f"DEBUG 模式:    {Config.DEBUG}")
    print(f"线程安全:      启用 (RLock)")
    print(f"节点间认证:    {'启用 (HMAC-SHA256)' if Config.NODE_SECRET else '未配置 (MIND_NODE_SECRET 未设置)'}")
    print(f"管理员认证:    {'已配置' if Config.ADMIN_API_KEY else '未配置!'}")
    print("=" * 50)

    app.run(
        host=Config.HOST,
        port=Config.PORT,
        debug=Config.DEBUG
    )
