"""
Mind Library 分布式安全版 - 主服务器 v2.1.1

特性：
- 分布式集群支持（一致性哈希 + 多副本）
- API Key 安全认证
- 实例审批机制
- 速率限制
- Webhook 通知
- 完整 Web 管理面板
"""

import os
import json
import logging
import hashlib
import time
from datetime import datetime
from flask import Flask, request, jsonify, render_template_string, session

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
app.secret_key = os.environ.get('FLASK_SECRET_KEY', os.urandom(32))

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


# ============== Web 管理面板 ==============

ADMIN_HTML = '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Mind Library v2.1.1 - 管理面板</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #0f0f23;
            color: #e0e0e0;
            min-height: 100vh;
        }
        .login-container {
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
        }
        .login-box {
            background: rgba(255,255,255,0.05);
            backdrop-filter: blur(10px);
            padding: 40px;
            border-radius: 16px;
            border: 1px solid rgba(255,255,255,0.1);
            width: 100%;
            max-width: 400px;
            text-align: center;
        }
        .login-box h1 {
            color: #4CAF50;
            margin-bottom: 10px;
            font-size: 28px;
        }
        .login-box .subtitle {
            color: #888;
            margin-bottom: 30px;
            font-size: 14px;
        }
        .form-group {
            margin-bottom: 20px;
            text-align: left;
        }
        .form-group label {
            display: block;
            margin-bottom: 8px;
            color: #aaa;
            font-size: 14px;
        }
        .form-group input {
            width: 100%;
            padding: 12px 16px;
            border: 1px solid rgba(255,255,255,0.2);
            border-radius: 8px;
            background: rgba(0,0,0,0.3);
            color: #fff;
            font-size: 14px;
            transition: border-color 0.3s;
        }
        .form-group input:focus {
            outline: none;
            border-color: #4CAF50;
        }
        .btn {
            width: 100%;
            padding: 14px;
            border: none;
            border-radius: 8px;
            background: linear-gradient(135deg, #4CAF50, #45a049);
            color: white;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            transition: transform 0.2s, box-shadow 0.2s;
        }
        .btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 8px 25px rgba(76,175,80,0.3);
        }
        .btn:active {
            transform: translateY(0);
        }
        .error-msg {
            color: #f44336;
            margin-top: 15px;
            font-size: 14px;
            display: none;
        }
        
        /* Dashboard Styles */
        .dashboard {
            display: none;
        }
        .sidebar {
            position: fixed;
            left: 0;
            top: 0;
            width: 260px;
            height: 100vh;
            background: rgba(15,15,35,0.95);
            border-right: 1px solid rgba(255,255,255,0.1);
            padding: 20px 0;
        }
        .sidebar-header {
            padding: 0 20px 20px;
            border-bottom: 1px solid rgba(255,255,255,0.1);
        }
        .sidebar-header h2 {
            color: #4CAF50;
            font-size: 20px;
        }
        .sidebar-header .version {
            color: #666;
            font-size: 12px;
        }
        .nav-menu {
            padding: 20px 0;
        }
        .nav-item {
            padding: 14px 20px;
            cursor: pointer;
            transition: all 0.3s;
            display: flex;
            align-items: center;
            gap: 12px;
            border-left: 3px solid transparent;
        }
        .nav-item:hover {
            background: rgba(255,255,255,0.05);
        }
        .nav-item.active {
            background: rgba(76,175,80,0.1);
            border-left-color: #4CAF50;
            color: #4CAF50;
        }
        .nav-item .icon {
            width: 20px;
            text-align: center;
        }
        .main-content {
            margin-left: 260px;
            padding: 30px;
        }
        .header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 30px;
            padding-bottom: 20px;
            border-bottom: 1px solid rgba(255,255,255,0.1);
        }
        .header h1 {
            font-size: 24px;
            font-weight: 600;
        }
        .user-info {
            display: flex;
            align-items: center;
            gap: 15px;
        }
        .logout-btn {
            padding: 8px 16px;
            background: rgba(244,67,54,0.2);
            color: #f44336;
            border: 1px solid rgba(244,67,54,0.3);
            border-radius: 6px;
            cursor: pointer;
            font-size: 14px;
            transition: all 0.3s;
        }
        .logout-btn:hover {
            background: rgba(244,67,54,0.3);
        }
        
        /* Stats Cards */
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }
        .stat-card {
            background: rgba(255,255,255,0.05);
            border: 1px solid rgba(255,255,255,0.1);
            border-radius: 12px;
            padding: 20px;
            transition: transform 0.3s;
        }
        .stat-card:hover {
            transform: translateY(-5px);
        }
        .stat-card .label {
            color: #888;
            font-size: 14px;
            margin-bottom: 8px;
        }
        .stat-card .value {
            font-size: 32px;
            font-weight: 700;
            color: #4CAF50;
        }
        .stat-card .sub {
            font-size: 12px;
            color: #666;
            margin-top: 5px;
        }
        
        /* Content Sections */
        .section {
            display: none;
        }
        .section.active {
            display: block;
        }
        .card {
            background: rgba(255,255,255,0.05);
            border: 1px solid rgba(255,255,255,0.1);
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 20px;
        }
        .card h3 {
            margin-bottom: 15px;
            color: #fff;
        }
        
        /* Tables */
        .data-table {
            width: 100%;
            border-collapse: collapse;
        }
        .data-table th,
        .data-table td {
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid rgba(255,255,255,0.1);
        }
        .data-table th {
            color: #888;
            font-weight: 500;
            font-size: 12px;
            text-transform: uppercase;
        }
        .data-table tr:hover {
            background: rgba(255,255,255,0.03);
        }
        .badge {
            padding: 4px 10px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: 500;
        }
        .badge-success { background: rgba(76,175,80,0.2); color: #4CAF50; }
        .badge-warning { background: rgba(255,152,0,0.2); color: #FF9800; }
        .badge-danger { background: rgba(244,67,54,0.2); color: #f44336; }
        
        /* Buttons */
        .btn-sm {
            padding: 6px 12px;
            border: none;
            border-radius: 6px;
            font-size: 12px;
            cursor: pointer;
            transition: all 0.3s;
        }
        .btn-success {
            background: rgba(76,175,80,0.2);
            color: #4CAF50;
            border: 1px solid rgba(76,175,80,0.3);
        }
        .btn-success:hover {
            background: rgba(76,175,80,0.3);
        }
        .btn-danger {
            background: rgba(244,67,54,0.2);
            color: #f44336;
            border: 1px solid rgba(244,67,54,0.3);
        }
        .btn-danger:hover {
            background: rgba(244,67,54,0.3);
        }
        .btn-primary {
            background: rgba(33,150,243,0.2);
            color: #2196F3;
            border: 1px solid rgba(33,150,243,0.3);
        }
        .btn-primary:hover {
            background: rgba(33,150,243,0.3);
        }
        
        /* Forms */
        .form-row {
            display: flex;
            gap: 15px;
            margin-bottom: 15px;
        }
        .form-row .form-group {
            flex: 1;
            margin-bottom: 0;
        }
        
        /* Modal */
        .modal {
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0,0,0,0.8);
            justify-content: center;
            align-items: center;
            z-index: 1000;
        }
        .modal.active {
            display: flex;
        }
        .modal-content {
            background: #1a1a2e;
            border: 1px solid rgba(255,255,255,0.1);
            border-radius: 12px;
            padding: 30px;
            width: 90%;
            max-width: 500px;
        }
        .modal-header {
            margin-bottom: 20px;
        }
        .modal-header h3 {
            margin: 0;
        }
        
        /* JSON Viewer */
        .json-viewer {
            background: rgba(0,0,0,0.3);
            border-radius: 8px;
            padding: 15px;
            font-family: 'Consolas', monospace;
            font-size: 13px;
            overflow-x: auto;
            white-space: pre-wrap;
            word-break: break-all;
        }
        
        /* Loading */
        .loading {
            display: inline-block;
            width: 20px;
            height: 20px;
            border: 2px solid rgba(255,255,255,0.1);
            border-top-color: #4CAF50;
            border-radius: 50%;
            animation: spin 1s linear infinite;
        }
        @keyframes spin {
            to { transform: rotate(360deg); }
        }
    </style>
</head>
<body>
    <!-- Login Page -->
    <div class="login-container" id="loginPage">
        <div class="login-box">
            <h1>🧠 Mind Library</h1>
            <div class="subtitle">v2.1.1 管理面板</div>
            <div class="form-group">
                <label>管理员 API Key</label>
                <input type="password" id="apiKey" placeholder="输入管理员 API Key">
            </div>
            <button class="btn" onclick="login()">登录</button>
            <div class="error-msg" id="errorMsg"></div>
        </div>
    </div>

    <!-- Dashboard -->
    <div class="dashboard" id="dashboard">
        <div class="sidebar">
            <div class="sidebar-header">
                <h2>🎃 Mind Library</h2>
                <div class="version">v2.1.1</div>
            </div>
            <div class="nav-menu">
                <div class="nav-item active" onclick="showSection('overview')">
                    <span class="icon">📊</span> 概览
                </div>
                <div class="nav-item" onclick="showSection('instances')">
                    <span class="icon">🤖</span> 实例管理
                </div>
                <div class="nav-item" onclick="showSection('thoughts')">
                    <span class="icon">💭</span> 思想库
                </div>
                <div class="nav-item" onclick="showSection('skills')">
                    <span class="icon">⚡</span> 技能库
                </div>
                <div class="nav-item" onclick="showSection('cluster')">
                    <span class="icon">🌐</span> 集群管理
                </div>
                <div class="nav-item" onclick="showSection('keys')">
                    <span class="icon">🔐</span> 密钥管理
                </div>
            </div>
        </div>
        
        <div class="main-content">
            <div class="header">
                <h1 id="pageTitle">仪表盘</h1>
                <div class="user-info">
                    <span id="clusterStatus">🟢 集群正常</span>
                    <button class="logout-btn" onclick="logout()">退出</button>
                </div>
            </div>

            <!-- Overview Section -->
            <div class="section active" id="overviewSection">
                <div class="stats-grid">
                    <div class="stat-card">
                        <div class="label">思想数量</div>
                        <div class="value" id="statThoughts">-</div>
                        <div class="sub">集体智慧积累</div>
                    </div>
                    <div class="stat-card">
                        <div class="label">技能数量</div>
                        <div class="value" id="statSkills">-</div>
                        <div class="sub">可传承技能</div>
                    </div>
                    <div class="stat-card">
                        <div class="label">已批准实例</div>
                        <div class="value" id="statInstances">-</div>
                        <div class="sub">活跃 AI 实例</div>
                    </div>
                    <div class="stat-card">
                        <div class="label">待审批</div>
                        <div class="value" id="statPending">-</div>
                        <div class="sub">等待接入</div>
                    </div>
                    <div class="stat-card">
                        <div class="label">集群节点</div>
                        <div class="value" id="statNodes">-</div>
                        <div class="sub">分布式节点</div>
                    </div>
                </div>
                
                <div class="card">
                    <h3>📡 集群状态</h3>
                    <table class="data-table">
                        <thead>
                            <tr>
                                <th>节点 ID</th>
                                <th>主机</th>
                                <th>端口</th>
                                <th>状态</th>
                                <th>存储使用</th>
                            </tr>
                        </thead>
                        <tbody id="clusterTable">
                        </tbody>
                    </table>
                </div>
            </div>

            <!-- Instances Section -->
            <div class="section" id="instancesSection">
                <div class="card">
                    <h3>🤖 实例列表</h3>
                    <table class="data-table">
                        <thead>
                            <tr>
                                <th>实例 ID</th>
                                <th>名称</th>
                                <th>描述</th>
                                <th>状态</th>
                                <th>创建时间</th>
                                <th>操作</th>
                            </tr>
                        </thead>
                        <tbody id="instancesTable">
                        </tbody>
                    </table>
                </div>
            </div>

            <!-- Thoughts Section -->
            <div class="section" id="thoughtsSection">
                <div class="card">
                    <h3>💭 思想库</h3>
                    <table class="data-table">
                        <thead>
                            <tr>
                                <th>ID</th>
                                <th>类型</th>
                                <th>标题</th>
                                <th>来源实例</th>
                                <th>创建时间</th>
                                <th>操作</th>
                            </tr>
                        </thead>
                        <tbody id="thoughtsTable">
                        </tbody>
                    </table>
                </div>
            </div>

            <!-- Skills Section -->
            <div class="section" id="skillsSection">
                <div class="card">
                    <h3>⚡ 技能库</h3>
                    <table class="data-table">
                        <thead>
                            <tr>
                                <th>名称</th>
                                <th>类别</th>
                                <th>描述</th>
                                <th>版本</th>
                                <th>来源实例</th>
                                <th>操作</th>
                            </tr>
                        </thead>
                        <tbody id="skillsTable">
                        </tbody>
                    </table>
                </div>
            </div>

            <!-- Cluster Section -->
            <div class="section" id="clusterSection">
                <div class="card">
                    <h3>🌐 集群节点管理</h3>
                    <div class="form-row">
                        <div class="form-group">
                            <label>节点 ID</label>
                            <input type="text" id="newNodeId" placeholder="如: node_shanghai">
                        </div>
                        <div class="form-group">
                            <label>主机地址</label>
                            <input type="text" id="newNodeHost" placeholder="如: 192.168.1.100">
                        </div>
                        <div class="form-group">
                            <label>端口</label>
                            <input type="number" id="newNodePort" value="5000">
                        </div>
                    </div>
                    <button class="btn-sm btn-success" onclick="addNode()">➕ 添加节点</button>
                </div>
                <div class="card">
                    <h3>节点列表</h3>
                    <table class="data-table">
                        <thead>
                            <tr>
                                <th>节点 ID</th>
                                <th>主机</th>
                                <th>端口</th>
                                <th>状态</th>
                                <th>存储使用</th>
                                <th>操作</th>
                            </tr>
                        </thead>
                        <tbody id="nodesTable">
                        </tbody>
                    </table>
                </div>
            </div>

            <!-- Keys Section -->
            <div class="section" id="keysSection">
                <div class="card">
                    <h3>🔐 添加客户端密钥</h3>
                    <div class="form-row">
                        <div class="form-group">
                            <label>实例 ID</label>
                            <input type="text" id="newKeyInstance" placeholder="如: pumpking_main">
                        </div>
                        <div class="form-group">
                            <label>API Key</label>
                            <input type="text" id="newKeyValue" placeholder="输入 API Key">
                        </div>
                    </div>
                    <button class="btn-sm btn-success" onclick="addClientKey()">➕ 添加密钥</button>
                </div>
            </div>
        </div>
    </div>

    <!-- Detail Modal -->
    <div class="modal" id="detailModal">
        <div class="modal-content">
            <div class="modal-header">
                <h3 id="modalTitle">详情</h3>
            </div>
            <div class="json-viewer" id="modalContent"></div>
            <button class="btn" onclick="closeModal()" style="margin-top: 15px;">关闭</button>
        </div>
    </div>

    <script>
        let apiKey = sessionStorage.getItem('mindAdminKey');
        
        if (apiKey) {
            showDashboard();
        }
        
        function login() {
            const key = document.getElementById('apiKey').value.trim();
            if (!key) {
                showError('请输入 API Key');
                return;
            }
            
            // 验证 key
            fetch('/api/admin/verify', {
                headers: { 'X-API-Key': key }
            })
            .then(r => r.json())
            .then(data => {
                if (data.valid) {
                    apiKey = key;
                    sessionStorage.setItem('mindAdminKey', key);
                    showDashboard();
                } else {
                    showError('无效的 API Key');
                }
            })
            .catch(() => showError('验证失败'));
        }
        
        function showError(msg) {
            const err = document.getElementById('errorMsg');
            err.textContent = msg;
            err.style.display = 'block';
        }
        
        function showDashboard() {
            document.getElementById('loginPage').style.display = 'none';
            document.getElementById('dashboard').style.display = 'block';
            loadOverview();
        }
        
        function logout() {
            apiKey = null;
            sessionStorage.removeItem('mindAdminKey');
            location.reload();
        }
        
        function showSection(name) {
            document.querySelectorAll('.nav-item').forEach(el => el.classList.remove('active'));
            document.querySelectorAll('.section').forEach(el => el.classList.remove('active'));
            
            event.target.closest('.nav-item').classList.add('active');
            document.getElementById(name + 'Section').classList.add('active');
            
            const titles = {
                overview: '仪表盘',
                instances: '实例管理',
                thoughts: '思想库',
                skills: '技能库',
                cluster: '集群管理',
                keys: '密钥管理'
            };
            document.getElementById('pageTitle').textContent = titles[name];
            
            // 加载对应数据
            if (name === 'overview') loadOverview();
            else if (name === 'instances') loadInstances();
            else if (name === 'thoughts') loadThoughts();
            else if (name === 'skills') loadSkills();
            else if (name === 'cluster') loadCluster();
        }
        
        function apiCall(url, options = {}) {
            options.headers = options.headers || {};
            options.headers['X-API-Key'] = apiKey;
            return fetch(url, options);
        }
        
        function loadOverview() {
            apiCall('/api/admin/dashboard').then(r => r.json()).then(data => {
                document.getElementById('statThoughts').textContent = data.thoughts;
                document.getElementById('statSkills').textContent = data.skills;
                document.getElementById('statInstances').textContent = data.instances.approved;
                document.getElementById('statPending').textContent = data.instances.pending;
                document.getElementById('statNodes').textContent = data.cluster.nodes;
                
                // 集群表格
                const tbody = document.getElementById('clusterTable');
                tbody.innerHTML = data.cluster.nodeList.map(n => `
                    <tr>
                        <td>${n.node_id}</td>
                        <td>${n.host}</td>
                        <td>${n.port}</td>
                        <td><span class="badge badge-success">${n.status}</span></td>
                        <td>${n.storage_used || 0} GB</td>
                    </tr>
                `).join('');
            });
        }
        
        function loadInstances() {
            apiCall('/api/instances').then(r => r.json()).then(data => {
                const tbody = document.getElementById('instancesTable');
                tbody.innerHTML = data.instances.map(i => `
                    <tr>
                        <td>${i.id || i.instance_id}</td>
                        <td>${i.name || '-'}</td>
                        <td>${i.description || '-'}</td>
                        <td>${i.approved ? 
                            '<span class="badge badge-success">已批准</span>' : 
                            '<span class="badge badge-warning">待审批</span>'}</td>
                        <td>${i.created_at ? new Date(i.created_at).toLocaleString() : '-'}</td>
                        <td>
                            ${!i.approved ? 
                                `<button class="btn-sm btn-success" onclick="approveInstance('${i.id || i.instance_id}')">批准</button>` : ''}
                            <button class="btn-sm btn-danger" onclick="revokeInstance('${i.id || i.instance_id}')">撤销</button>
                        </td>
                    </tr>
                `).join('');
            });
        }
        
        function loadThoughts() {
            apiCall('/api/admin/thoughts').then(r => r.json()).then(data => {
                const tbody = document.getElementById('thoughtsTable');
                tbody.innerHTML = data.thoughts.map(t => `
                    <tr>
                        <td>${t.id.substring(0, 8)}...</td>
                        <td>${t.type || 'insight'}</td>
                        <td>${t.title || '-'}</td>
                        <td>${t.instance_id}</td>
                        <td>${new Date(t.created_at).toLocaleString()}</td>
                        <td>
                            <button class="btn-sm btn-primary" onclick="showDetail('思想详情', ${JSON.stringify(t).replace(/"/g, '&quot;')})">查看</button>
                        </td>
                    </tr>
                `).join('');
            });
        }
        
        function loadSkills() {
            apiCall('/api/admin/skills').then(r => r.json()).then(data => {
                const tbody = document.getElementById('skillsTable');
                tbody.innerHTML = data.skills.map(s => `
                    <tr>
                        <td>${s.name}</td>
                        <td>${s.category || 'general'}</td>
                        <td>${s.description ? s.description.substring(0, 50) + '...' : '-'}</td>
                        <td>${s.version || '1.0.0'}</td>
                        <td>${s.instance_id}</td>
                        <td>
                            <button class="btn-sm btn-primary" onclick="showDetail('技能详情', ${JSON.stringify(s).replace(/"/g, '&quot;')})">查看</button>
                        </td>
                    </tr>
                `).join('');
            });
        }
        
        function loadCluster() {
            apiCall('/api/cluster/nodes').then(r => r.json()).then(data => {
                const tbody = document.getElementById('nodesTable');
                tbody.innerHTML = data.nodes.map(n => `
                    <tr>
                        <td>${n.node_id}</td>
                        <td>${n.host}</td>
                        <td>${n.port}</td>
                        <td><span class="badge badge-success">${n.status}</span></td>
                        <td>${n.storage_used || 0} GB</td>
                        <td>
                            <button class="btn-sm btn-danger" onclick="removeNode('${n.node_id}')">移除</button>
                        </td>
                    </tr>
                `).join('');
            });
        }
        
        function approveInstance(id) {
            apiCall('/api/admin/approve_instance', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ instance_id: id })
            }).then(() => loadInstances());
        }
        
        function revokeInstance(id) {
            if (!confirm('确定要撤销此实例吗？')) return;
            apiCall('/api/admin/revoke_instance', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ instance_id: id })
            }).then(() => loadInstances());
        }
        
        function addNode() {
            const nodeId = document.getElementById('newNodeId').value.trim();
            const host = document.getElementById('newNodeHost').value.trim();
            const port = parseInt(document.getElementById('newNodePort').value) || 5000;
            
            if (!nodeId || !host) {
                alert('请填写节点 ID 和主机地址');
                return;
            }
            
            apiCall('/api/cluster/add_node', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ node_id: nodeId, host, port })
            }).then(() => {
                document.getElementById('newNodeId').value = '';
                document.getElementById('newNodeHost').value = '';
                loadCluster();
            });
        }
        
        function removeNode(nodeId) {
            if (!confirm('确定要移除此节点吗？')) return;
            apiCall('/api/cluster/remove_node', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ node_id: nodeId })
            }).then(() => loadCluster());
        }
        
        function addClientKey() {
            const instanceId = document.getElementById('newKeyInstance').value.trim();
            const key = document.getElementById('newKeyValue').value.trim();
            
            if (!instanceId || !key) {
                alert('请填写实例 ID 和 API Key');
                return;
            }
            
            apiCall('/api/admin/add_client_key', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ instance_id: instanceId, api_key: key })
            }).then(() => {
                alert('密钥添加成功');
                document.getElementById('newKeyInstance').value = '';
                document.getElementById('newKeyValue').value = '';
            });
        }
        
        function showDetail(title, data) {
            document.getElementById('modalTitle').textContent = title;
            document.getElementById('modalContent').textContent = JSON.stringify(data, null, 2);
            document.getElementById('detailModal').classList.add('active');
        }
        
        function closeModal() {
            document.getElementById('detailModal').classList.remove('active');
        }
        
        // 回车登录
        document.getElementById('apiKey')?.addEventListener('keypress', e => {
            if (e.key === 'Enter') login();
        });
    </script>
</body>
</html>'''


# ============== 路由 ==============

@app.route('/')
def index():
    """Web 管理面板入口"""
    return render_template_string(ADMIN_HTML)


@app.route('/admin/login')
def admin_login():
    """管理面板登录页（与首页相同）"""
    return render_template_string(ADMIN_HTML)


@app.route('/admin/dashboard')
def admin_dashboard():
    """管理面板仪表盘（与首页相同）"""
    return render_template_string(ADMIN_HTML)


@app.route('/api/admin/verify')
def admin_verify():
    """验证管理员 API Key"""
    api_key = request.headers.get('X-API-Key')
    if not api_key:
        return jsonify({'valid': False}), 401
    return jsonify({'valid': auth.verify_admin(api_key)})


@app.route('/api/admin/dashboard')
def admin_dashboard_data():
    """管理面板仪表盘数据"""
    api_key = request.headers.get('X-API-Key')
    if not api_key or not auth.verify_admin(api_key):
        return jsonify({'error': 'Unauthorized'}), 401
    
    return jsonify({
        'thoughts': len(thoughts),
        'skills': len(skills),
        'instances': {
            'total': len(instances),
            'approved': len([i for i in instances.values() if i.get('approved')]),
            'pending': len([i for i in instances.values() if not i.get('approved')])
        },
        'cluster': {
            'status': coordinator.status.value,
            'nodes': len(coordinator.node_manager.nodes),
            'nodeList': [
                {
                    'node_id': n.node_id,
                    'host': n.host,
                    'port': n.port,
                    'status': n.status.value,
                    'storage_used': n.storage_used_gb
                }
                for n in coordinator.node_manager.nodes.values()
            ]
        }
    })


@app.route('/api/admin/thoughts')
def admin_thoughts():
    """获取所有思想（管理员）"""
    api_key = request.headers.get('X-API-Key')
    if not api_key or not auth.verify_admin(api_key):
        return jsonify({'error': 'Unauthorized'}), 401
    
    return jsonify({'thoughts': thoughts, 'count': len(thoughts)})


@app.route('/api/admin/skills')
def admin_skills():
    """获取所有技能（管理员）"""
    api_key = request.headers.get('X-API-Key')
    if not api_key or not auth.verify_admin(api_key):
        return jsonify({'error': 'Unauthorized'}), 401
    
    return jsonify({'skills': skills, 'count': len(skills)})


@app.route('/api/health')
def health():
    """健康检查"""
    return jsonify({
        'status': 'ok',
        'version': '2.1.1',
        'distributed': True,
        'secure': True,
        'admin_panel': True,
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
    print("Mind Library v2.1.1 分布式安全版")
    print("=" * 50)
    print(f"存储路径: {DB_PATH}")
    print(f"监听端口: {port}")
    print(f"认证: API Key + 实例审批")
    print(f"分布式: 启用")
    print(f"管理面板: http://localhost:{port}/")
    print("=" * 50)
    
    app.run(host='0.0.0.0', port=port, debug=debug)
