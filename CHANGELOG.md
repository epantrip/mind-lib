# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.2.0] - 2026-04-19

### 🎯 P0 — Thread Safety (并发安全)

- **Thread-safe DataStore** — 新增 `data_store.py`，所有存储操作（思想/技能/实例/副本）通过 `threading.RLock` 保护，进程内多线程安全
- 移除了原来分散在路由中的文件锁，改用 `DataStore` 统一 API
- `upload_thought` 等写操作：锁内完成内存写入 + 磁盘持久化，锁外执行网络 I/O（`coordinator.sync_thought`），避免阻塞其他请求

### 🔐 P1 — Node-to-Node HMAC Authentication (节点间认证)

- 新增 `node_auth.py` — HMAC-SHA256 签名认证，保护所有节点间 API
- 签名内容：`method + path + timestamp + body`，时间戳窗口 5 分钟防重放
- 受保护端点：`/api/replica/store`、`/api/replica/get/<id>`、`/api/sync/pull`、`/api/replica/migrate`
- 新增 `X-Node-Signature` 和 `X-Node-Timestamp` 请求头

### 🔧 P2 — Data Rebalancing & Replica Repair (数据再平衡)

- `_trigger_rebalance`：节点加入时，遍历本地数据，把应归属新节点的数据返回给协调者
- `_repair_after_node_leave`：节点离开时，重新计算受影响数据的副本列表，修复到目标 `REPLICA_FACTOR`
- 新增端点 `/api/replica/migrate?target=<node_id>` — 返回应迁移给目标节点的全部数据
- 修复 `replica_store` 中 `data_id` 未规范化导致哈希路由失效的 bug

### ⚙️ Production Configuration (生产配置)

- 新增 `config.py` — `Config` 类集中管理所有环境变量，含启动校验
- 新增 `gunicorn.conf.py` — Gunicorn 生产参数（workers 自动检测 CPU*2+1、timeout 120s、JSON 日志）
- 新增 `start.bat` / `start.sh` — 跨平台启动脚本（dev / prod 模式）
- 新增 `health_check.py` — HTTP 健康检查脚本（Docker/K8s liveness/readiness 探针用，退出码 0/1）
- 新增 `DEPLOY.md` — 完整部署指南（Docker Compose、systemd、安全检查清单）
- 更新 `requirements.txt` — 新增 gunicorn、gevent
- 启动时打印完整配置状态（节点 ID、监听地址、日志级别、CORS、认证状态等）

### 🛡️ Reliability & Observability (可靠性与可观测性)

- CORS 中间件 — 白名单模式，从 `CORS_ORIGINS` 环境变量配置
- 请求 ID 追踪 — 每个请求生成 `X-Request-ID`（8位），日志和响应头都带，全链路可追踪
- 安全响应头 — `X-Frame-Options: DENY`、`HSTS max-age=31536000`、`X-XSS-Protection`
- 全局错误处理 — 404/500/429 含 `request_id`；500 含 `exc_info`（堆栈）；`Exception` 兜底防止崩溃

### 📦 Files Added

```
server/config.py          # 生产配置类
server/data_store.py      # 线程安全存储层
server/node_auth.py       # 节点 HMAC 认证
server/gunicorn.conf.py   # Gunicorn 配置
server/health_check.py    # 健康检查脚本
server/start.bat          # Windows 启动脚本
server/start.sh           # Linux/macOS 启动脚本
server/DEPLOY.md          # 部署指南
server/.env.example       # 环境变量模板
```

---

## [2.1.1] - 2026-04-17

### Added
- Web UI 管理面板（内嵌 HTML，直接访问根路径）

---

## [2.1.0] - 2026-04-17

### Added
- **分布式集群架构** — 一致性哈希环 + 多副本冗余
- **分布式协调器** (`DistributedCoordinator`) — 节点管理、集群状态监控、心跳检测
- **副本管理器** (`ReplicationManager`) — 多副本写入、故障转移
- **路由缓存持久化** — 重启后自动恢复哈希环状态
- **节点管理 API** — `/api/cluster/nodes`、`/api/cluster/status`、`/api/cluster/add_node`、`/api/cluster/remove_node`
- **副本存储 API** — `/api/replica/store`、`/api/replica/get/<id>`、`/api/sync/pull`

### Changed
- 重构为模块化架构：`distributed/` 包 + `auth/` 包

---

## [2.0.1] - 2026-04-15

### Added
- Webhook 通知 (`MIND_NOTIFICATION_WEBHOOK`)
- 新实例注册实时通知

---

## [2.0.0] - 2026-04-15

### Added
- **API Key 安全认证** — 管理员/客户端角色分离
- **实例审批机制** — 新实例需管理员审批才能上传
- **速率限制** — 防止滥用 (60 req/min)
- `mind_server_secure.py`

---

## [1.0.0] - 2026-04-13

### Added
- 基础思想/技能同步
- 实例注册与 Token 管理
- `mind_server.py` 原始服务器
