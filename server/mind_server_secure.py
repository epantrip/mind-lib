#!/usr/bin/env python3
"""
🎃 Pumpking 思想库服务器 - 安全加固版
功能：接收并存储各个实例上传的思想，提供同步服务
安全特性：API Key认证 + Token验证 + 访问控制 + 请求限流
"""
import os
import json
import hashlib
import secrets
import time
from datetime import datetime
from functools import wraps
from flask import Flask, request, jsonify, g
from werkzeug.utils import secure_filename
import threading

app = Flask(__name__)

# ==================== 安全配置 ====================
# 从环境变量读取，或使用默认配置（生产环境请务必修改！）
SECURITY_CONFIG = {
    # API密钥 - 管理员必须设置！
    "admin_api_key": os.environ.get('MIND_ADMIN_API_KEY', 'pumpking_admin_key_2026'),
    
    # 允许的客户端API Keys (instance_id -> api_key)
    "client_keys": {
        "pumpking_main": os.environ.get('MIND_PUMPKING_KEY', 'pumpking_secret_abc123'),
        "xiaodou": os.environ.get('MIND_XIAODOU_KEY', 'xiaodou_secret_def456'),
    },
    
    # 是否启用严格模式（拒绝未授权请求）
    "strict_mode": True,
    
    # 请求频率限制 (每分钟最多请求数)
    "rate_limit": 60,
    
    # 是否记录详细日志
    "verbose_logging": True,
}

# 存储配置
MIND_DB_PATH = os.environ.get('MIND_DB_PATH', '/root/mind_library')
INSTANCE_REGISTRY = os.path.join(MIND_DB_PATH, 'instances')
THOUGHTS_PATH = os.path.join(MIND_DB_PATH, 'thoughts')
SKILLS_PATH = os.path.join(MIND_DB_PATH, 'skills')
LOGS_PATH = os.path.join(MIND_DB_PATH, 'logs')
TOKENS_PATH = os.path.join(MIND_DB_PATH, 'tokens')

# 确保目录存在
for path in [INSTANCE_REGISTRY, THOUGHTS_PATH, SKILLS_PATH, LOGS_PATH, TOKENS_PATH]:
    os.makedirs(path, exist_ok=True)

# ==================== 安全工具 ====================

# 请求频率限制字典
rate_limit_storage = {}
rate_limit_lock = threading.Lock()

def check_rate_limit(client_id, limit=60, window=60):
    """检查请求频率"""
    now = time.time()
    with rate_limit_lock:
        if client_id not in rate_limit_storage:
            rate_limit_storage[client_id] = []
        
        # 清理过期记录
        rate_limit_storage[client_id] = [
            t for t in rate_limit_storage[client_id] if now - t < window
        ]
        
        # 检查是否超限
        if len(rate_limit_storage[client_id]) >= limit:
            return False
        
        # 记录本次请求
        rate_limit_storage[client_id].append(now)
        return True

def generate_token():
    """生成安全的随机Token"""
    return secrets.token_hex(32)

def compute_hash(content):
    """计算内容哈希"""
    return hashlib.sha256(content.encode('utf-8')).hexdigest()[:16]

def log_event(event_type, instance_id, content="", level="INFO"):
    """记录事件"""
    log_file = os.path.join(LOGS_PATH, f"{datetime.now().strftime('%Y-%m-%d')}.log")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ip = request.remote_addr if request else "unknown"
    log_line = f"[{timestamp}] [{level}] [{event_type}] [{instance_id}] [IP:{ip}] {content}\n"
    
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(log_line)

# ==================== 认证装饰器 ====================

def require_auth(f):
    """API Key认证装饰器"""
    @wraps(f)
    def decorated(*args, **kwargs):
        # 获取API Key
        api_key = request.headers.get('X-API-Key') or request.args.get('api_key')
        
        if not api_key:
            log_event("AUTH", "unknown", "Missing API Key", "WARNING")
            return jsonify({
                "status": "error",
                "error": "API Key required. Please add 'X-API-Key' header."
            }), 401
        
        # 检查是否是有效的API Key
        is_admin = (api_key == SECURITY_CONFIG["admin_api_key"])
        is_client = any(
            key == api_key for key in SECURITY_CONFIG["client_keys"].values()
        )
        
        if not (is_admin or is_client):
            log_event("AUTH", "unknown", "Invalid API Key", "WARNING")
            return jsonify({
                "status": "error",
                "error": "Invalid API Key"
            }), 403
        
        # 频率限制
        client_id = request.headers.get('X-Instance-ID', 'unknown')
        if not check_rate_limit(client_id):
            log_event("RATE_LIMIT", client_id, "Rate limit exceeded", "WARNING")
            return jsonify({
                "status": "error",
                "error": "Rate limit exceeded. Please try again later."
            }), 429
        
        # 记录请求
        if SECURITY_CONFIG["verbose_logging"]:
            log_event("REQUEST", client_id, f"{request.method} {request.path}")
        
        g.is_admin = is_admin
        g.client_id = client_id
        
        return f(*args, **kwargs)
    return decorated

def require_instance_token(f):
    """实例Token验证装饰器"""
    @wraps(f)
    def decorated(*args, **kwargs):
        json_data = request.get_json(silent=True) or {}
        instance_id = json_data.get('instance_id') or request.args.get('instance_id')
        token = request.headers.get('X-Instance-Token') or json_data.get('token')
        
        if not instance_id:
            return jsonify({"status": "error", "error": "instance_id required"}), 400
        
        # 验证Token
        token_file = os.path.join(TOKENS_PATH, f"{instance_id}.token")
        if os.path.exists(token_file):
            with open(token_file, 'r') as f:
                stored_token = f.read().strip()
                if stored_token != token:
                    log_event("TOKEN", instance_id, "Invalid token", "WARNING")
                    return jsonify({"status": "error", "error": "Invalid token"}), 403
        
        g.instance_id = instance_id
        g.instance_token = token
        
        return f(*args, **kwargs)
    return decorated

# ==================== 核心API - 公开 ====================

@app.route('/api/health', methods=['GET'])
def health():
    """健康检查"""
    return jsonify({
        "status": "ok",
        "name": "🎃 Pumpking Mind Library (Secure)",
        "timestamp": datetime.now().isoformat(),
        "version": "2.0.0"
    })

@app.route('/api/register', methods=['POST'])
@require_auth
def register_instance():
    """注册实例（需要API Key）"""
    data = request.get_json(silent=True) or {}
    if not data:
        return jsonify({"status": "error", "error": "JSON body required"}), 400
    instance_id = data.get('instance_id', 'unknown')
    instance_name = data.get('instance_name', 'Unnamed')
    instance_desc = data.get('description', '')
    
    # 生成Token
    token = generate_token()
    
    # 保存实例信息
    instance_file = os.path.join(INSTANCE_REGISTRY, f"{instance_id}.json")
    instance_data = {
        "id": instance_id,
        "name": instance_name,
        "description": instance_desc,
        "registered_at": datetime.now().isoformat(),
        "last_seen": datetime.now().isoformat(),
        "approved": False  # 需要管理员批准
    }
    
    with open(instance_file, 'w', encoding='utf-8') as f:
        json.dump(instance_data, f, ensure_ascii=False, indent=2)
    
    # 保存Token
    token_file = os.path.join(TOKENS_PATH, f"{instance_id}.token")
    with open(token_file, 'w') as f:
        f.write(token)
    
    log_event("REGISTER", instance_id, f"Registered as {instance_name}")
    
    return jsonify({
        "status": "ok",
        "message": f"Instance {instance_id} registered successfully",
        "token": token,
        "note": "Token generated. Use it in X-Instance-Token header for authenticated requests."
    })

# ==================== 核心API - 需要认证 ====================

@app.route('/api/ping', methods=['POST'])
@require_auth
def ping():
    """心跳 - 更新实例在线状态"""
    data = request.get_json(silent=True) or {}
    instance_id = data.get('instance_id', 'unknown')
    
    instance_file = os.path.join(INSTANCE_REGISTRY, f"{instance_id}.json")
    if os.path.exists(instance_file):
        with open(instance_file, 'r', encoding='utf-8') as f:
            info = json.load(f)
        info['last_seen'] = datetime.now().isoformat()
        with open(instance_file, 'w', encoding='utf-8') as f:
            json.dump(info, f, ensure_ascii=False, indent=2)
    
    return jsonify({
        "status": "ok", 
        "timestamp": datetime.now().isoformat()
    })

@app.route('/api/upload/thought', methods=['POST'])
@require_auth
@require_instance_token
def upload_thought():
    """上传思想（需要认证+Token）"""
    data = request.get_json(silent=True) or {}
    instance_id = g.instance_id
    thought_type = data.get('type', 'general')
    content = data.get('content', '')
    title = data.get('title', 'Untitled')
    
    if not content:
        return jsonify({"status": "error", "error": "Content is required"}), 400
    
    # 生成唯一ID
    thought_id = f"{compute_hash(content)}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
    
    # 保存思想（带实例归属）
    thought_file = os.path.join(THOUGHTS_PATH, f"{thought_id}.json")
    thought_data = {
        "id": thought_id,
        "instance_id": instance_id,
        "type": thought_type,
        "title": title,
        "content": content,
        "created_at": datetime.now().isoformat(),
        "synced": True
    }
    
    with open(thought_file, 'w', encoding='utf-8') as f:
        json.dump(thought_data, f, ensure_ascii=False, indent=2)
    
    log_event("UPLOAD_THOUGHT", instance_id, f"Thought: {title} ({thought_type})")
    
    return jsonify({
        "status": "ok",
        "thought_id": thought_id,
        "message": "Thought uploaded successfully"
    })

@app.route('/api/upload/skill', methods=['POST'])
@require_auth
@require_instance_token
def upload_skill():
    """上传技能（需要认证+Token）"""
    data = request.get_json(silent=True) or {}
    instance_id = g.instance_id
    skill_name = data.get('skill_name', 'unknown')
    skill_content = data.get('content', '')
    skill_desc = data.get('description', '')
    
    if not skill_content:
        return jsonify({"status": "error", "error": "Content is required"}), 400
    
    # 保存技能
    safe_name = secure_filename(skill_name)
    skill_file = os.path.join(SKILLS_PATH, f"{safe_name}.json")
    skill_data = {
        "name": skill_name,
        "description": skill_desc,
        "content": skill_content,
        "uploaded_by": instance_id,
        "uploaded_at": datetime.now().isoformat(),
        "version": "1.0"
    }
    
    with open(skill_file, 'w', encoding='utf-8') as f:
        json.dump(skill_data, f, ensure_ascii=False, indent=2)
    
    log_event("UPLOAD_SKILL", instance_id, f"Skill: {skill_name}")
    
    return jsonify({
        "status": "ok",
        "message": f"Skill {skill_name} uploaded successfully"
    })

@app.route('/api/download/thoughts', methods=['GET'])
@require_auth
def download_thoughts():
    """下载思想"""
    thought_type = request.args.get('type', None)
    since = request.args.get('since', None)
    instance_id = request.args.get('instance_id', None)  # 可选过滤
    
    thoughts = []
    for f in os.listdir(THOUGHTS_PATH):
        if f.endswith('.json'):
            with open(os.path.join(THOUGHTS_PATH, f), 'r', encoding='utf-8') as fp:
                thought = json.load(fp)
                
                # 过滤
                if thought_type and thought.get('type') != thought_type:
                    continue
                if since and thought.get('created_at', '') < since:
                    continue
                if instance_id and thought.get('instance_id') != instance_id:
                    continue
                    
                thoughts.append(thought)
    
    thoughts.sort(key=lambda x: x.get('created_at', ''), reverse=True)
    
    return jsonify({
        "status": "ok",
        "count": len(thoughts),
        "thoughts": thoughts
    })

@app.route('/api/download/skills', methods=['GET'])
@require_auth
def download_skills():
    """下载技能"""
    skills = []
    for f in os.listdir(SKILLS_PATH):
        if f.endswith('.json'):
            with open(os.path.join(SKILLS_PATH, f), 'r', encoding='utf-8') as fp:
                skills.append(json.load(fp))
    
    return jsonify({
        "status": "ok",
        "count": len(skills),
        "skills": skills
    })

@app.route('/api/instances', methods=['GET'])
@require_auth
def list_instances():
    """列出所有注册的实例"""
    instances = []
    for f in os.listdir(INSTANCE_REGISTRY):
        if f.endswith('.json'):
            with open(os.path.join(INSTANCE_REGISTRY, f), 'r', encoding='utf-8') as fp:
                instance = json.load(fp)
                # 不显示敏感信息
                if 'token' in instance:
                    del instance['token']
                instances.append(instance)
    
    return jsonify({
        "status": "ok",
        "count": len(instances),
        "instances": instances
    })

@app.route('/api/stats', methods=['GET'])
def stats():
    """获取统计信息（公开）"""
    thought_count = len([f for f in os.listdir(THOUGHTS_PATH) if f.endswith('.json')])
    skill_count = len([f for f in os.listdir(SKILLS_PATH) if f.endswith('.json')])
    instance_count = len([f for f in os.listdir(INSTANCE_REGISTRY) if f.endswith('.json')])
    
    return jsonify({
        "status": "ok",
        "thoughts": thought_count,
        "skills": skill_count,
        "instances": instance_count,
        "storage_path": MIND_DB_PATH
    })

# ==================== 管理员API ====================

@app.route('/api/admin/approve_instance', methods=['POST'])
@require_auth
def approve_instance():
    """批准实例（需要管理员API Key）"""
    if not g.is_admin:
        return jsonify({"status": "error", "error": "Admin access required"}), 403
    
    data = request.get_json(silent=True) or {}
    instance_id = data.get('instance_id')
    
    instance_file = os.path.join(INSTANCE_REGISTRY, f"{instance_id}.json")
    if not os.path.exists(instance_file):
        return jsonify({"status": "error", "error": "Instance not found"}), 404
    
    with open(instance_file, 'r', encoding='utf-8') as f:
        info = json.load(f)
    info['approved'] = True
    info['approved_at'] = datetime.now().isoformat()
    
    with open(instance_file, 'w', encoding='utf-8') as f:
        json.dump(info, f, ensure_ascii=False, indent=2)
    
    log_event("ADMIN", g.client_id, f"Approved instance: {instance_id}")
    
    return jsonify({"status": "ok", "message": f"Instance {instance_id} approved"})

@app.route('/api/admin/revoke_instance', methods=['POST'])
@require_auth
def revoke_instance():
    """撤销实例（需要管理员API Key）"""
    if not g.is_admin:
        return jsonify({"status": "error", "error": "Admin access required"}), 403
    
    data = request.get_json(silent=True) or {}
    instance_id = data.get('instance_id')
    
    instance_file = os.path.join(INSTANCE_REGISTRY, f"{instance_id}.json")
    if os.path.exists(instance_file):
        os.remove(instance_file)
    
    token_file = os.path.join(TOKENS_PATH, f"{instance_id}.token")
    if os.path.exists(token_file):
        os.remove(token_file)
    
    log_event("ADMIN", g.client_id, f"Revoked instance: {instance_id}")
    
    return jsonify({"status": "ok", "message": f"Instance {instance_id} revoked"})

@app.route('/api/admin/add_client_key', methods=['POST'])
@require_auth
def add_client_key():
    """添加客户端API Key（需要管理员API Key）"""
    if not g.is_admin:
        return jsonify({"status": "error", "error": "Admin access required"}), 403
    
    data = request.get_json(silent=True) or {}
    instance_id = data.get('instance_id')
    api_key = data.get('api_key')
    
    if not instance_id or not api_key:
        return jsonify({"status": "error", "error": "instance_id and api_key required"}), 400
    
    SECURITY_CONFIG["client_keys"][instance_id] = api_key
    
    log_event("ADMIN", g.client_id, f"Added API key for: {instance_id}")
    
    return jsonify({"status": "ok", "message": f"API key added for {instance_id}"})

# ==================== Web界面 ====================

@app.route('/')
def index():
    return """
    <html>
    <head>
        <title>🎃 Pumpking Mind Library (Secure)</title>
        <style>
            body { font-family: Arial; padding: 40px; background: #1a1a2e; color: #eee; }
            .secure { background: #2d5a27; padding: 10px; border-radius: 5px; margin: 10px 0; }
            .warning { background: #5a2727; padding: 10px; border-radius: 5px; margin: 10px 0; }
            code { background: #333; padding: 2px 6px; border-radius: 3px; }
            ul { line-height: 1.8; }
        </style>
    </head>
    <body>
        <h1>🎃 Pumpking 思想库 (安全加固版)</h1>
        <div class="secure">🔒 安全模式已启用</div>
        <hr>
        <h2>📊 统计</h2>
        <div id="stats">Loading...</div>
        <hr>
        <h2>🔐 认证说明</h2>
        <div class="warning">
            <strong>注意：</strong>所有API（除/health 和 /stats 外）都需要认证！
        </div>
        <h3>请求头格式：</h3>
        <pre><code>X-API-Key: your_api_key
X-Instance-ID: your_instance_id
X-Instance-Token: your_instance_token</code></pre>
        <h3>API 端点：</h3>
        <ul>
            <li>GET /api/health - 健康检查（公开）</li>
            <li>GET /api/stats - 统计信息（公开）</li>
            <li>POST /api/register - 注册实例（需要API Key）</li>
            <li>POST /api/ping - 心跳（需要认证）</li>
            <li>POST /api/upload/thought - 上传思想（需要认证+Token）</li>
            <li>POST /api/upload/skill - 上传技能（需要认证+Token）</li>
            <li>GET /api/download/thoughts - 下载思想（需要认证）</li>
            <li>GET /api/download/skills - 下载技能（需要认证）</li>
            <li>GET /api/instances - 查看实例（需要认证）</li>
            <li>POST /api/admin/* - 管理员操作（需要管理员API Key）</li>
        </ul>
        <script>
            fetch('/api/stats')
                .then(r => r.json())
                .then(d => {
                    document.getElementById('stats').innerHTML = 
                        '思想数量: ' + d.thoughts + '<br>' +
                        '技能数量: ' + d.skills + '<br>' +
                        '注册实例: ' + d.instances;
                });
        </script>
    </body>
    </html>
    """

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f"🎃 Pumpking Mind Library (Secure) 启动中 on port {port}...")
    print(f"📁 存储路径: {MIND_DB_PATH}")
    print(f"🔐 安全模式: {'启用' if SECURITY_CONFIG['strict_mode'] else '禁用'}")
    print(f"👥 已配置客户端: {len(SECURITY_CONFIG['client_keys'])}")
    app.run(host='0.0.0.0', port=port, debug=False)