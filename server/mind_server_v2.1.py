"""
Mind Library 分布式安全版 - 主服务器 v2.1.0

特性：
- 分布式集群支持（一致性哈希 + 多副本）
- API Key 安全认证
- 实例审批机制
- 速率限制
- Webhook 通知
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

# 本地数据存储（主节点数据）
thoughts = []
skills = []
instances = {}


# ============== 辅助函数 ==============
def load_data(filename, default=None):
    """加载数据文件（兼容v2.0目录式存储）"""
    if default is None:
        default = []
    path = os.path.join(DB_PATH, filename)
    # instances: 支持从目录加载单个json文件（v2.0兼容）
    if filename == 'instances.json':
        dir_path = os.path.join(DB_PATH, 'instances')
        if os.path.isdir(dir_path):
            result = {}
            for fname in os.listdir(dir_path):
                if fname.endswith('.json'):
                    try:
                        with open(os.path.join(dir_path, fname), 'r', encoding='utf-8') as f:
                            data = json.load(f)
                            iid = data.get('id') or data.get('instance_id') or fname.replace('.json', '')
                            result[iid] = data
                    except Exception:
                        pass
            return result
    # thoughts/skills: 支持从目录加载（v2.0兼容）
    if filename in ('thoughts.json', 'skills.json') and not os.path.exists(path):
        dir_name = filename.replace('.json', '')
        dir_path = os.path.join(DB_PATH, dir_name)
        if os.path.isdir(dir_path):
            result = []
            for fname in sorted(os.listdir(dir_path)):
                if fname.endswith('.json'):
                    try:
                        with open(os.path.join(dir_path, fname), 'r', encoding='utf-8') as f:
                            result.append(json.load(f))
                    except Exception:
                        pass
            return result
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"加载 {filename} 失败: {e}")
    return default


def save_data(filename, data):
    """保存数据文件（兼容v2.0目录式存储）"""
    # instances: 保存到目录下单独文件（v2.0兼容）
    if filename == 'instances.json' and isinstance(data, dict):
        dir_path = os.path.join(DB_PATH, 'instances')
        os.makedirs(dir_path, exist_ok=True)
        for iid, inst_data in data.items():
            try:
                with open(os.path.join(dir_path, f'{iid}.json'), 'w', encoding='utf-8') as f:
                    json.dump(inst_data, f, ensure_ascii=False, indent=2)
            except Exception as e:
                logger.error(f"保存实例 {iid} 失败: {e}")
        return
    # thoughts/skills: 保存到目录下单独文件（v2.0兼容）
    if filename in ('thoughts.json', 'skills.json') and isinstance(data, list):
        dir_name = filename.replace('.json', '')
        dir_path = os.path.join(DB_PATH, dir_name)
        os.makedirs(dir_path, exist_ok=True)
        for item in data:
            item_id = item.get('id') or item.get('instance_id', '')
            ts = item.get('timestamp', item.get('created_at', ''))
            if item_id and ts:
                fname = f"{item_id}_{ts.replace('-','').replace(':','').replace('.','')}.json"
            elif item_id:
                fname = f"{item_id}.json"
            else:
                fname = f"{int(time.time())}.json"
            try:
                with open(os.path.join(dir_path, fname), 'w', encoding='utf-8') as f:
                    json.dump(item, f, ensure_ascii=False, indent=2)
            except Exception as e:
                logger.error(f"保存到 {fname} 失败: {e}")
        return
    path = os.path.join(DB_PATH, filename)
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"保存 {filename} 失败: {e}")


# 初始化数据
thoughts = load_data('thoughts.json', [])
skills = load_data('skills.json', [])
instances = load_data('instances.json', {})


def notify_webhook(payload):
    """发送 Webhook 通知"""
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
    stats = {
        'version': '2.1.0',
        'thoughts': len(thoughts),
        'skills': len(skills),
        'instances': len([i for i in instances.values() if i.get('approved')]),
        'pending': len([i for i in instances.values() if not i.get('approved')]),
        'coordinator_status': coordinator.status.value,
        'cluster_nodes': len(coordinator.node_manager.nodes),
    }
    
    html = '''<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Mind Library v2.1.0</title>
<style>
body{font-family:Arial,sans-serif;max-width:800px;margin:0 auto;padding:20px;background:#f5f5f5}
h1{color:#333}.card{background:white;border-radius:8px;padding:20px;margin:10px 0;box-shadow:0 2px 4px rgba(0,0,0,0.1)}
.stat{font-size:24px;font-weight:bold;color:#4CAF50}.label{color:#666}
.status{color:#2196F3;font-weight:bold}.status-standby{color:#FF9800}
</style></head>
<body>
<h1>Mind Library v2.1.0</h1>
<div class="card">
<h2>系统状态</h2>
<p><span class="label">版本:</span> <span class="stat">{{stats.version}}</span></p>
<p><span class="label">思想数量:</span> <span class="stat">{{stats.thoughts}}</span></p>
<p><span class="label">技能数量:</span> <span class="stat">{{stats.skills}}</span></p>
<p><span class="label">已批准实例:</span> <span class="stat">{{stats.instances}}</span></p>
<p><span class="label">待审批:</span> <span class="stat">{{stats.pending}}</span></p>
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
        'version': '2.1.0',
        'distributed': True,
        'secure': True,
        'timestamp': datetime.now().isoformat()
    })


@app.route('/api/stats')
def stats():
    """统计信息"""
    return jsonify({
        'thoughts': len(thoughts),
        'skills': len(skills),
        'instances': {
            'total': len(instances),
            'approved': len([i for i in instances.values() if i.get('approved')]),
            'pending': len([i for i in instances.values() if not i.get('approved')])
        },
        'coordinator': {
            'status': coordinator.status.value,
            'nodes': len(coordinator.node_manager.nodes),
            'replication': coordinator.replication_manager.status.value if hasattr(coordinator.replication_manager, 'status') else 'active'
        }
    })


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
    
    if instance_id in instances:
        return jsonify({'error': 'Instance already exists'}), 409
    
    # 生成 Token
    token = hashlib.sha256(f"{instance_id}_{time.time()}".encode()).hexdigest()[:32]
    
    instances[instance_id] = {
        'id': instance_id,
        'name': instance_name,
        'description': description,
        'approved': False,  # 需要审批
        'token': token,
        'created_at': datetime.now().isoformat(),
        'last_seen': time.time()
    }
    save_data('instances.json', instances)
    
    # Webhook 通知
    notify_webhook({
        'event': 'new_instance_registration',
        'message': f'New instance {instance_id} ({instance_name}) registered and awaiting approval',
        'timestamp': datetime.now().isoformat(),
        'instance': instances[instance_id]
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
    
    if instance_id and instance_id in instances:
        instances[instance_id]['last_seen'] = time.time()
        save_data('instances.json', instances)
    
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
    
    result = [t for t in thoughts if t.get('created_at', '') > since]
    if thought_type:
        result = [t for t in result if t.get('type') == thought_type]
    
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
    
    # 检查实例是否已批准
    if instance_id not in instances or not instances[instance_id].get('approved'):
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
    
    thoughts.append(thought)
    save_data('thoughts.json', thoughts)
    
    # 分布式：同步到其他节点
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
    if instance_id not in instances or not instances[instance_id].get('approved'):
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
    
    # 更新已存在的技能
    for i, s in enumerate(skills):
        if s.get('name') == skill['name']:
            skills[i] = skill
            break
    else:
        skills.append(skill)
    
    save_data('skills.json', skills)
    
    return jsonify({'status': 'ok', 'skill_id': skill['id']})


@app.route('/api/instances')
def list_instances():
    """列出实例（需管理员）"""
    api_key = request.headers.get('X-API-Key')
    
    if not api_key or not auth.verify_admin(api_key):
        return jsonify({'error': 'Unauthorized'}), 401
    
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
    
    if instance_id not in instances:
        return jsonify({'error': 'Instance not found'}), 404
    
    instances[instance_id]['approved'] = True
    save_data('instances.json', instances)
    
    return jsonify({'status': 'ok', 'message': f'Instance {instance_id} approved'})


@app.route('/api/admin/revoke_instance', methods=['POST'])
def revoke_instance():
    """撤销实例"""
    api_key = request.headers.get('X-API-Key')
    if not api_key or not auth.verify_admin(api_key):
        return jsonify({'error': 'Unauthorized'}), 401
    
    data = request.get_json() or {}
    instance_id = data.get('instance_id')
    
    if instance_id in instances:
        del instances[instance_id]
        save_data('instances.json', instances)
    
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
    
    # 更新实例
    if instance_id in instances:
        instances[instance_id]['token'] = new_key
        instances[instance_id]['approved'] = True
        save_data('instances.json', instances)
    
    return jsonify({'status': 'ok', 'message': f'API key added for {instance_id}'})


# ============== 分布式集群 API ==============

@app.route('/api/cluster/nodes')
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
def cluster_status():
    """获取集群详细状态"""
    return jsonify(coordinator.get_cluster_status())


# ============== 副本存储 API（分布式节点间通信）=============

@app.route('/api/replica/store', methods=['POST'])
def replica_store():
    """存储副本数据（节点间调用）"""
    data = request.get_json() or {}
    data_id = data.get('data_id')
    data_type = data.get('data_type')
    content = data.get('content')
    
    if not data_id or not content:
        return jsonify({'error': 'data_id and content required'}), 400
    
    # 根据类型存储
    if data_type == 'thought':
        # 检查是否已存在
        for i, t in enumerate(thoughts):
            if t.get('id') == data_id:
                thoughts[i] = content
                break
        else:
            thoughts.append(content)
        save_data('thoughts.json', thoughts)
    elif data_type == 'skill':
        for i, s in enumerate(skills):
            if s.get('id') == data_id:
                skills[i] = content
                break
        else:
            skills.append(content)
        save_data('skills.json', skills)
    
    return jsonify({'status': 'ok', 'data_id': data_id})


@app.route('/api/replica/get/<data_id>')
def replica_get(data_id):
    """获取副本数据（节点间调用）"""
    # 在思想中查找
    for t in thoughts:
        if t.get('id') == data_id:
            return jsonify({
                'data_id': data_id,
                'data_type': 'thought',
                'content': t,
                'found': True
            })
    
    # 在技能中查找
    for s in skills:
        if s.get('id') == data_id:
            return jsonify({
                'data_id': data_id,
                'data_type': 'skill',
                'content': s,
                'found': True
            })
    
    return jsonify({'found': False, 'data_id': data_id})


@app.route('/api/sync/pull', methods=['POST'])
def sync_pull():
    """节点间数据同步拉取"""
    data = request.get_json() or {}
    source_node = data.get('source_node')
    
    # 返回本地数据供同步
    return jsonify({
        'thoughts': thoughts,
        'skills': skills,
        'timestamp': datetime.now().isoformat()
    })


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
    print("Mind Library v2.1.0 分布式安全版")
    print("=" * 50)
    print(f"存储路径: {DB_PATH}")
    print(f"监听端口: {port}")
    print(f"认证: API Key + 实例审批")
    print(f"分布式: 启用")
    print("=" * 50)
    
    app.run(host='0.0.0.0', port=port, debug=debug)
