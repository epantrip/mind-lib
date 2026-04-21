# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.2.1] - 2026-04-21

### Fixed
- **Idempotent registration** — /api/register now returns existing instance token (approved status) instead of 409 Conflict when an instance is already registered; clients that restart and re-register no longer fail
- **Encoding corruption** — Fixed UTF-8 replacement character corruption in docs/API_REFERENCE.md, docs/DEPLOY_GUIDE.md, docs/FAQ.md, docs-zh/FAQ.md, docs-zh/basic_usage.py, server/mind_server.py
- **BOM removal** — Removed unnecessary UTF-8 BOM from CHANGELOG.md, README_ZH.md, server/mind_server_v2.1.py, server/start.sh, server/distributed/config.py, server/distributed/coordinator.py
- **Remote server version** — Oracle Cloud server confirmed running v2.2.1 with all patches applied

### Changed
- All source files normalized to UTF-8 without BOM, CRLF line endings on Windows
- Version bumped: pyproject.toml, mind_server_v2.1.py (health response + web dashboard)

---

## [2.2.0] - 2026-04-19

### 🎯 P0 — Thread Safety

- **Thread-safe DataStore** — New data_store.py; all storage operations (thoughts/skills/instances/replicas) protected by threading.RLock; process-internal multi-thread safe
- Removed scattered file locks from routes; replaced with unified DataStore API
- upload_thought etc.: lock covers memory write + disk persistence; network I/O (coordinator.sync_thought) executes outside lock to avoid blocking other requests

### 🔐 P1 — Node-to-Node HMAC Authentication

- New node_auth.py — HMAC-SHA256 signature authentication; protects all inter-node APIs
- Signature payload: method + path + timestamp + body; 5-minute timestamp window for replay protection
- Protected endpoints: /api/replica/store, /api/replica/get/<id>, /api/sync/pull, /api/replica/migrate
- New request headers: X-Node-Signature, X-Node-Timestamp

### 🔧 P2 — Data Rebalancing & Replica Repair

- _trigger_rebalance: on node join, iterates local data and returns data that should belong to the new node
- _repair_after_node_leave: on node leave, recalculates affected data replica lists; repairs to target REPLICA_FACTOR
- New endpoint /api/replica/migrate?target=<node_id> — returns all data that should migrate to the target node
- Fixed replica_store data_id not normalized causing hash routing failure

### ⚙️ Production Configuration

- New config.py — Config class centralizes all environment variable management; includes startup validation
- New gunicorn.conf.py — Gunicorn production settings (auto-detect workers CPU×2+1; timeout 120s; JSON logging)
- New start.bat / start.sh — cross-platform startup scripts (dev / prod modes)
- New health_check.py — HTTP health check script (Docker/K8s liveness/readiness probes; exit code 0/1)
- New DEPLOY.md — complete deployment guide (Docker Compose, systemd, security checklist)
- Updated requirements.txt — added gunicorn, gevent
- Startup prints full configuration status (node ID, listen address, log level, CORS, auth state, etc.)

### 🛡️ Reliability & Observability

- CORS middleware — whitelist mode; configured via CORS_ORIGINS environment variable
- Request ID tracing — every request generates X-Request-ID (8 chars); present in logs and response headers; full chain traceable
- Security response headers — X-Frame-Options: DENY, HSTS max-age=31536000, X-XSS-Protection
- Global error handling — 404/500/429 include request_id; 500 includes exc_info (stack trace); Exception handler prevents crashes

### 📦 Files Added

    server/config.py          # Production config class
    server/data_store.py      # Thread-safe storage layer
    server/node_auth.py       # Inter-node HMAC auth
    server/gunicorn.conf.py   # Gunicorn config
    server/health_check.py    # Health check script
    server/start.bat          # Windows startup script
    server/start.sh           # Linux/macOS startup script
    server/DEPLOY.md          # Deployment guide
    server/.env.example       # Environment variable template

---

## [2.1.1] - 2026-04-17

### Added
- Web UI admin panel (embedded HTML; accessible at root URL)

---

## [2.1.0] - 2026-04-17

### Added
- **Distributed cluster architecture** — consistent hash ring + multi-replica redundancy
- **Distributed Coordinator** (DistributedCoordinator) — node management, cluster state monitoring, heartbeat detection
- **Replication Manager** (ReplicationManager) — multi-replica writes, automatic failover
- **Routing cache persistence** — auto-restores hash ring state after restart
- **Node management API** — /api/cluster/nodes, /api/cluster/status, /api/cluster/add_node, /api/cluster/remove_node
- **Replica storage API** — /api/replica/store, /api/replica/get/<id>, /api/sync/pull

### Changed
- Refactored to modular architecture: distributed/ package + auth/ package

---

## [2.0.1] - 2026-04-15

### Added
- Webhook notifications (MIND_NOTIFICATION_WEBHOOK)
- Real-time notifications for new instance registration

---

## [2.0.0] - 2026-04-15

### Added
- **API Key security authentication** — admin/client role separation
- **Instance approval mechanism** — new instances require admin approval before uploading
- **Rate limiting** — prevents abuse (60 req/min)
- mind_server_secure.py

---

## [1.0.0] - 2026-04-13

### Added
- Basic thought/skill sync
- Instance registration and token management
- mind_server.py original server