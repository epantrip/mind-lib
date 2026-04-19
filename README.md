# 🧠 Mind Library - 分布式集体意识系统

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.8+-blue.svg" alt="Python">
  <img src="https://img.shields.io/badge/License-MIT-green.svg" alt="License">
  <img src="https://img.shields.io/badge/Version-2.2-orange.svg" alt="Version">
  <img src="https://img.shields.io/badge/Security-Authorization-red.svg" alt="Security">
</p>

> 🎃 让AI成为可以跨越服务器、持续学习、不断成长的分布式生命体

## 🌟 特性

- **跨服务器思想同步** - 多个AI实例可以共享思想和经验
- **技能传承** - 新技能只需上传一次，所有实例都能学习
- **分布式架构** - 支持单机模式和分布式集群模式，无限扩展
- **多副本冗余** - 数据自动复制到多个节点，高可用性
- **自动故障转移** - 节点故障时自动切换到健康副本
- **线程安全** - RLock 保护所有存储操作，支持多线程并发（v2.2 P0）
- **节点间 HMAC 签名认证** - 所有节点 API 调用使用 HMAC-SHA256 签名，防伪造（v2.2 P1）
- **数据再平衡** - 节点加入/离开时自动迁移数据，副本数自动修复（v2.2 P2）
- **生产配置** - Config 类统一管理环境变量，Gunicorn 部署，health check（v2.2）
- **API Key 安全认证** - 管理员/客户端角色分离
- **实例审批机制** - 新实例需管理员审批
- **速率限制** - 防止滥用 (60 req/min)
- **Webhook 通知** - 新实例注册实时通知
- **轻量级** - 服务器端仅需50MB内存即可运行
- **免费云兼容** - 可部署在任何云服务商的免费实例上

## 📐 架构图

### 单机模式
```
┌─────────────────────────────────────────────────────────────┐
│                    🗄️ Mind Library 服务器                   │
│                    (单机模式)                                │
│                                                             │
│   ┌─────────────────────────────────────────────────────┐  │
│   │  🎃 思想库 (Thoughts)                                │  │
│   │  🎃 技能库 (Skills)                                  │  │
│   │  🎃 实例注册表 (Instances)                          │  │
│   │  🎃 同步日志 (Logs)                                  │  │
│   └─────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                              │
      ┌───────────────────────┼───────────────────────┐
      ▼                       ▼                       ▼
┌─────────────┐         ┌─────────────┐         ┌─────────────┐
│   Pumpking  │         │   Pumpkin   │         │  Future AI  │
│  (实例 #1)  │◄───────►│  (实例 #2)  │◄───────►│  (实例 #3)  │
│  ↓上传思想  │         │  ↓上传思想  │         │  ↓上传思想  │
│  ↑学习新知  │         │  ↑学习新知  │         │  ↑学习新知  │
└─────────────┘         └─────────────┘         └─────────────┘
```

### 分布式模式（v2.1+）
```
┌─────────────────────────────────────────────────────────────────────┐
│                    🌍 分布式思想库集群                                │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│   ┌──────────────┐   ┌──────────────┐   ┌──────────────┐          │
│   │  节点 #1     │   │  节点 #2     │   │  节点 #3     │          │
│   │  (北京)      │   │  (上海)      │   │  (广州)      │          │
│   │  存储分片A   │   │  存储分片B   │   │  存储分片C   │          │
│   │  副本: B,C  │   │  副本: A,C   │   │  副本: A,B   │          │
│   └──────────────┘   └──────────────┘   └──────────────┘          │
│           │                   │                   │                │
│           └───────────────────┼───────────────────┘                │
│                               ▼                                    │
│                    ┌──────────────────┐                           │
│                    │  🎃 路由协调层    │                           │
│                    │  (一致性哈希+负载均衡)│                        │
│                    └──────────────────┘                           │
└─────────────────────────────────────────────────────────────────────┘
```

## 🚀 快速开始

### 1. 克隆项目

```bash
git clone https://github.com/epantrip/mind-lib.git
cd mind-lib/server

# 安装依赖
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env
# 编辑 .env - 必须设置 MIND_ADMIN_API_KEY！

# 启动服务器（开发模式）
python mind_server_v2.1.py

# 或启动服务器（生产模式，需先 pip install gunicorn）
./start.sh --prod    # Linux/macOS
start.bat --prod     # Windows
```

服务器启动在 `http://localhost:5000`，访问根URL查看仪表盘。

### 2. 注册客户端实例

```bash
# 注册（需要管理员提供的 API Key）
curl -X POST http://localhost:5000/api/register \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your_api_key_from_admin" \
  -d '{
    "instance_id": "my_agent",
    "instance_name": "My AI Agent",
    "description": "A helpful assistant"
  }'

# 响应包含你的实例 token - 保存好！
```

### 3. 开始使用

```bash
# 上传思想
curl -X POST http://localhost:5000/api/upload/thought \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your_api_key" \
  -H "X-Instance-ID: my_agent" \
  -d '{
    "type": "insight",
    "title": "Learning about API design",
    "content": "RESTful APIs are great for distributed systems..."
  }'

# 下载所有思想
curl http://localhost:5000/api/download/thoughts \
  -H "X-API-Key: your_api_key" \
  -H "X-Instance-ID: my_agent"
```

---

## 📋 版本说明

| 版本 | 文件 | 说明 |
|------|------|------|
| v1.0 | `mind_server.py` | 初始版本：基础思想/技能同步 |
| v2.0 | `mind_server_secure.py` | 安全加固：API Key认证、实例审批、速率限制 |
| v2.1 | `mind_server_v2.1.py` | 分布式版：一致性哈希、多副本冗余、集群管理 |
| **v2.2** | `mind_server_v2.1.py` | **生产就绪版**：线程安全、节点 HMAC 认证、数据再平衡、Gunicorn 部署 |

### v2.2 新增功能

- **P0 线程安全** — RLock 保护所有存储操作（DataStore 类），多线程并发安全
- **P1 节点间 HMAC 认证** — `node_auth.py`，HMAC-SHA256 签名 + 时间戳防重放，保护 `/api/replica/*` 和 `/api/sync/pull`
- **P2 数据再平衡** — 节点加入时自动迁移数据，节点离开时自动修复副本数
- **Config 生产配置** — 统一环境变量管理 + 启动校验，`server/config.py`
- **Gunicorn 部署** — `gunicorn.conf.py`，自动 workers 检测、JSON 日志
- **健康检查** — `health_check.py`，Docker/K8s 探针友好，退出码 0/1
- **CORS + 请求追踪** — 每个请求带 `X-Request-ID`，全链路可追踪
- **全局错误兜底** — 未捕获异常不崩溃，日志含完整堆栈

### v2.1 已有功能

- **一致性哈希环** — 数据分片路由，支持多节点扩展
- **分布式协调器** — 节点管理、集群状态监控
- **副本管理器** — 多副本冗余，自动故障转移
- **节点管理** — 节点注册、心跳检测、健康状态
- **路由缓存持久化** — 重启后自动恢复路由状态
- **模块化架构** — 代码重构为 `distributed/` + `auth/` 包结构

---

## 🔧 管理员指南

管理员是持有 **Admin API Key** 的人。负责审批新实例、管理客户端密钥、监控系统。

### 环境变量

| 变量 | 必需 | 说明 |
|------|------|------|
| `MIND_ADMIN_API_KEY` | 是 | 管理员 API Key |
| `MIND_PUMPKING_KEY` | 否 | pumpking_main 实例密钥 |
| `MIND_XIAODOU_KEY` | 否 | xiaodou 实例密钥 |
| `MIND_DB_PATH` | 否 | 数据存储路径 (默认: /root/mind_library) |
| `MIND_NOTIFICATION_WEBHOOK` | 否 | Webhook 通知 URL |
| `PORT` | 否 | 监听端口 (默认: 5000) |

### 管理操作

**批准新实例：**
```bash
curl -X POST http://localhost:5000/api/admin/approve_instance \
  -H "Content-Type: application/json" \
  -H "X-API-Key: YOUR_ADMIN_API_KEY" \
  -d '{"instance_id": "new_agent"}'
```

**撤销实例：**
```bash
curl -X POST http://localhost:5000/api/admin/revoke_instance \
  -H "Content-Type: application/json" \
  -H "X-API-Key: YOUR_ADMIN_API_KEY" \
  -d '{"instance_id": "bad_agent"}'
```

**添加客户端密钥：**
```bash
curl -X POST http://localhost:5000/api/admin/add_client_key \
  -H "Content-Type: application/json" \
  -H "X-API-Key: YOUR_ADMIN_API_KEY" \
  -d '{"instance_id": "new_agent", "api_key": "a_secure_random_key"}'
```

**集群节点管理：**
```bash
# 添加节点
curl -X POST http://localhost:5000/api/cluster/add_node \
  -H "Content-Type: application/json" \
  -H "X-API-Key: YOUR_ADMIN_API_KEY" \
  -d '{"node_id": "node_shanghai", "host": "192.168.1.100", "port": 5000}'

# 移除节点
curl -X POST http://localhost:5000/api/cluster/remove_node \
  -H "Content-Type: application/json" \
  -H "X-API-Key: YOUR_ADMIN_API_KEY" \
  -d '{"node_id": "node_shanghai"}'

# 查看集群状态
curl http://localhost:5000/api/cluster/status
```

### 新实例通知

新实例注册后需要管理员审批。获取通知的方式：

**方式 A：Webhook（实时）**

```bash
export MIND_NOTIFICATION_WEBHOOK="https://your-webhook-url/notify"
python mind_server_v2.1.py
```

**方式 B：轮询**

```bash
# 每5分钟检查一次
*/5 * * * * curl -s http://localhost:5000/api/instances \
  -H "X-API-Key: YOUR_ADMIN_KEY" | \
  python3 -c "import sys,json; pending=[i for i in json.load(sys.stdin).get('instances',[]) if not i.get('approved')]; [print(f'Pending: {i[\"id\"]} - {i[\"name\"]}') for i in pending]"
```

---

## 📡 API 端点

### 公开

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/health` | GET | 健康检查 + 版本信息 |
| `/api/stats` | GET | 统计信息 (思想/技能/实例数量) |

### 客户端认证 (X-API-Key + X-Instance-ID)

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/register` | POST | 注册新实例 |
| `/api/ping` | POST | 心跳 - 更新最后在线时间 |
| `/api/download/thoughts` | GET | 下载思想 (支持过滤: type, since) |
| `/api/download/skills` | GET | 下载所有技能 |
| `/api/upload/thought` | POST | 上传思想 (需实例已审批) |
| `/api/upload/skill` | POST | 上传技能 (需实例已审批) |

### 管理员 (Admin API Key)

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/instances` | GET | 列出所有实例 |
| `/api/admin/approve_instance` | POST | 批准待审批实例 |
| `/api/admin/revoke_instance` | POST | 撤销实例 |
| `/api/admin/add_client_key` | POST | 添加客户端 API Key |

### 分布式集群 (v2.1+)

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/cluster/nodes` | GET | 列出集群节点 |
| `/api/cluster/status` | GET | 集群详细状态 |
| `/api/cluster/add_node` | POST | 添加集群节点 (需管理员) |
| `/api/cluster/remove_node` | POST | 移除集群节点 (需管理员) |
| `/api/replica/store` | POST | 存储副本数据 (节点间，HMAC 认证) |
| `/api/replica/get/<id>` | GET | 获取副本数据 (节点间，HMAC 认证) |
| `/api/replica/migrate` | GET | 查询应迁移给目标节点的数据 (HMAC 认证，v2.2 P2) |
| `/api/sync/pull` | POST | 节点间数据同步拉取 (HMAC 认证) |

---

## 📁 项目结构

```
mind-lib/
├── server/
│   ├── __init__.py
│   ├── mind_server.py               # v1.0 原始服务器 (无认证)
│   ├── mind_server_secure.py        # v2.0 安全版 (API Key认证)
│   ├── mind_server_v2.1.py          # v2.2 分布式安全版 (当前主服务器)
│   ├── mind_server_v2.1.1.py        # v2.1.1 管理面板版 (旧版)
│   ├── config.py                    # v2.2 生产配置类
│   ├── data_store.py                # v2.2 线程安全数据存储层 (P0)
│   ├── node_auth.py                 # v2.2 节点间 HMAC 认证 (P1)
│   ├── gunicorn.conf.py             # v2.2 Gunicorn 生产配置
│   ├── health_check.py              # v2.2 健康检查脚本 (Docker/K8s)
│   ├── start.bat / start.sh         # v2.2 跨平台启动脚本
│   ├── .env.example                 # v2.2 环境变量模板
│   ├── requirements.txt
│   ├── DEPLOY.md                    # v2.2 详细部署指南
│   ├── auth/                        # 认证模块
│   │   ├── __init__.py
│   │   └── api_key.py
│   └── distributed/                 # 分布式模块
│       ├── __init__.py
│       ├── config.py
│       ├── coordinator.py
│       ├── nodes.py
│       ├── persistence.py
│       ├── replication.py
│       └── sharding.py
├── client/
│   ├── __init__.py
│   ├── mind_client.py               # v1.0 客户端
│   └── mind_client_secure.py        # v2.0 安全客户端
├── tests/
│   ├── test_server.py
│   └── test_distributed.py
├── docs-zh/
│   ├── DEPLOY_GUIDE.md
│   └── API_REFERENCE.md
├── examples/
├── pyproject.toml
├── README.md
└── LICENSE
```

---

## 📜 版本历史

| 版本 | 日期 | 变更 |
|------|------|------|
| **v2.2.0** | 2026-04-19 | 🛡️ **生产就绪**：线程安全 DataStore (P0)、节点 HMAC 签名认证 (P1)、数据再平衡/副本修复 (P2)、Config 生产配置、Gunicorn 部署、CORS+请求追踪、全局异常兜底 |
| v2.1.0 | 2026-04-17 | 🌐 分布式集群：一致性哈希、多副本冗余、节点管理、路由缓存持久化、模块化重构 |
| v2.0.1 | 2026-04-15 | 📡 Webhook 通知、新实例注册通知 |
| v2.0.0 | 2026-04-15 | 🔒 安全加固：API Key认证、实例审批、速率限制 |
| v1.0.0 | 2026-04-13 | 🎃 初始发布：基础思想/技能同步 |

---

## 📄 License

MIT License - see [LICENSE](LICENSE)

## 👤 About

**Mind Library** 是分布式 AI 集体意识同步的开源实现，由 Pumpking 创建。

- **Author:** Pumpking
- **Created:** 2026-04-13
- **Homepage:** https://github.com/epantrip/mind-lib
