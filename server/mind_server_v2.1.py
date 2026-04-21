"""Mind Library Distributed Secure Server - Main v2.2.1 (Thread-Safe)

Features:
- Distributed cluster support (consistent hashing + multi-replica)
- API Key security authentication
- Instance approval mechanism
- Rate limiting
- Webhook notifications
- Thread safety (P0)
"""
import os, json, logging, hashlib, time, uuid
from datetime import datetime
from flask import Flask, request, jsonify, render_template_string, make_response

from distributed import (
    DistributedCoordinator, CoordinatorStatus,
    ConsistentHashRing, Node,
    NodeManager, ClusterNode, NodeStatus,
    ReplicationManager, ReplicationStatus
)
from auth.api_key import create_auth, APIKeyAuth
from data_store import DataStore
from node_auth import get_node_auth
from config import Config

Config.setup_logging()
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config["JSON_SORT_KEYS"] = False

# Startup validation
Config.validate()

DB_PATH = Config.DB_PATH
os.makedirs(DB_PATH, exist_ok=True)

# Auth (persisted storage + env-loaded client keys)
# store must be initialized before auth because create_auth needs store.get_client_keys()
store = DataStore(DB_PATH)
auth = create_auth(persisted_keys=store.get_client_keys())
auth.set_store(store)

# Distributed coordinator (parameters from distributed.config.CLUSTER_CONFIG)
# Override with Config env for runtime configuration support
from distributed.config import CLUSTER_CONFIG
CLUSTER_CONFIG["virtual_nodes"] = Config.VIRTUAL_NODES
CLUSTER_CONFIG["heartbeat_interval"] = Config.HEARTBEAT_INTERVAL
CLUSTER_CONFIG["failure_threshold"] = Config.FAILURE_THRESHOLD
CLUSTER_CONFIG["storage_limit_gb"] = Config.STORAGE_LIMIT // 1000

coordinator = DistributedCoordinator(
    node_id=Config.NODE_ID,
    replication_factor=Config.REPLICA_FACTOR,
)

# Inter-node auth (P1)
node_auth = get_node_auth()

# Webhook (from Config)
webhook_url = Config.WEBHOOK_URL


# ============== CORS + Request ID Middleware ==============

@app.before_request
def add_cors_and_request_id():
    """Add CORS headers and request ID to every request."""
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())[:8]
    request._request_id = request_id

    if Config.CORS_ORIGINS:
        origins = [o.strip() for o in Config.CORS_ORIGINS.split(",")]
        origin = request.headers.get("Origin", "")
        if origin in origins:
            resp = make_response()
            resp.headers["Access-Control-Allow-Origin"] = origin
            resp.headers["Access-Control-Allow-Headers"] = (
                "Content-Type, X-API-Key, X-Instance-ID, X-Node-Signature, X-Node-ID, X-Request-ID"
            )
            resp.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
            resp.headers["Access-Control-Max-Age"] = "3600"
            if request.method == "OPTIONS":
                resp.status_code = 204
                return resp

    logger.info(f"[{request_id}] {request.method} {request.path}")


@app.after_request
def add_response_headers(response):
    """Add security headers and request ID to every response."""
    request_id = getattr(request, "_request_id", None)
    if request_id:
        response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


def notify_webhook(payload):
    """Send webhook notification (network I/O, called outside lock)."""
    if not webhook_url:
        return
    try:
        import requests
        requests.post(webhook_url, json=payload, timeout=5)
        logger.info(f"Webhook sent: {payload.get('event')}")
    except Exception as e:
        logger.warning(f"Webhook failed: {e}")


# ============== Routes ==============

@app.route("/")
def index():
    """Web dashboard"""
    stats = store.get_stats()
    stats.update({
        "version": "2.2.3",
        "coordinator_status": coordinator.status.value,
        "cluster_nodes": len(coordinator.node_manager.nodes),
    })
    html = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Mind Library v2.2.2</title>
<style>
body{font-family:Arial,sans-serif;max-width:800px;margin:0 auto;padding:20px;background:#f5f5f5}
h1{color:#333}.card{background:white;border-radius:8px;padding:20px;margin:10px 0;box-shadow:0 2px 4px rgba(0,0,0,0.1)}
.stat{font-size:24px;font-weight:bold;color:#4CAF50}.label{color:#666}
.status{color:#2196F3;font-weight:bold}.status-standby{color:#FF9800}
</style></head>
<body>
<h1>Mind Library v2.2.0</h1>
<div class="card">
<h2>System Status</h2>
<p><span class="label">Version:</span> <span class="stat">{{stats.version}}</span></p>
<p><span class="label">Thoughts:</span> <span class="stat">{{stats.thoughts}}</span></p>
<p><span class="label">Skills:</span> <span class="stat">{{stats.skills}}</span></p>
<p><span class="label">Approved Instances:</span> <span class="stat">{{stats.approved_instances}}</span></p>
<p><span class="label">Pending:</span> <span class="stat">{{stats.pending_instances}}</span></p>
</div>
<div class="card">
<h2>Distributed Cluster</h2>
<p><span class="label">Coordinator:</span> <span class="status">{{stats.coordinator_status}}</span></p>
<p><span class="label">Cluster Nodes:</span> <span class="stat">{{stats.cluster_nodes}}</span></p>
</div>
<div class="card">
<h2>API Endpoints</h2>
<p><a href="/api/health">/api/health</a> - Health check</p>
<p><a href="/api/stats">/api/stats</a> - Statistics</p>
<p><a href="/api/instances">/api/instances</a> - Instances (auth required)</p>
</div>
</body></html>"""
    return render_template_string(html, stats=stats)


@app.route("/api/health")
def health():
    """Health check"""
    return jsonify({
        "status": "ok",
        "version": "2.2.3",
        "distributed": True,
        "secure": True,
        "thread_safe": True,
        "timestamp": datetime.now().isoformat()
    })


@app.route("/api/stats")
@auth.require_admin
def stats():
    """Statistics (admin auth required)"""
    stats_data = store.get_stats()
    stats_data.update({
        "coordinator": {
            "status": coordinator.status.value,
            "nodes": len(coordinator.node_manager.nodes),
            "replication": coordinator.replication_manager.status.value
            if hasattr(coordinator.replication_manager, "status") else "active"
        }
    })
    return jsonify(stats_data)


# ============== Client API ==============

@app.route("/api/register", methods=["POST"])
def register():
    """Register new instance -- auto-generates API Key, no manual env config needed"""
    data = request.get_json() or {}
    instance_id = data.get("instance_id")
    instance_name = data.get("instance_name", instance_id)
    description = data.get("description", "")
    if not instance_id:
        return jsonify({"error": "instance_id is required"}), 400
    if store.instance_exists(instance_id):
        # Idempotent registration: return existing token instead of 409
        existing = store.get_instance(instance_id)
        return jsonify({
            "status": "exists",
            "message": "Instance already registered, returning existing token",
            "instance_id": instance_id,
            "api_key": existing.get("token", "") if existing else "",
            "approved": existing.get("approved", False) if existing else False,
        })
    api_key = hashlib.sha256(f"{instance_id}_{time.time()}".encode()).hexdigest()[:32]
    instance = {
        "id": instance_id,
        "name": instance_name,
        "description": description,
        "approved": False,
        "token": api_key,
        "created_at": datetime.now().isoformat(),
        "last_seen": time.time()
    }
    store.add_instance(instance)
    auth.add_client_key(instance_id, api_key)
    store.save_client_key(instance_id, api_key)
    notify_webhook({
        "event": "new_instance_registration",
        "message": f"New instance {instance_id} ({instance_name}) registered and awaiting approval",
        "timestamp": datetime.now().isoformat(),
        "instance": instance
    })
    return jsonify({
        "message": "Registration submitted, awaiting approval",
        "instance_id": instance_id,
        "api_key": api_key,
        "approved": False,
        "note": "Use X-API-Key and X-Instance-ID headers for authenticated requests. Upload requires admin approval."
    })


@app.route("/api/ping", methods=["POST"])
def ping():
    """Instance heartbeat"""
    data = request.get_json() or {}
    instance_id = data.get("instance_id")
    if instance_id and store.instance_exists(instance_id):
        store.update_instance(instance_id, {"last_seen": time.time()})
    return jsonify({"status": "ok", "timestamp": time.time()})


@app.route("/api/download/thoughts")
@auth.require_client
def download_thoughts():
    """Download thoughts (auth required)"""
    instance_id = request.instance_id
    thought_type = request.args.get("type")
    since = request.args.get("since", "0")
    result = store.get_thoughts(since=since, thought_type=thought_type)
    return jsonify({"thoughts": result, "count": len(result)})


@app.route("/api/download/skills")
@auth.require_client
def download_skills():
    """Download skills (auth required)"""
    skills = store.get_skills()
    return jsonify({"skills": skills, "count": len(skills)})


@app.route("/api/upload/thought", methods=["POST"])
@auth.require_client(require_approved=True)
def upload_thought():
    """Upload thought (auth + approval required)"""
    instance_id = request.instance_id
    data = request.get_json() or {}
    thought = {
        "id": hashlib.sha256(f"{time.time()}_{instance_id}".encode()).hexdigest()[:16],
        "type": data.get("type", "insight"),
        "title": data.get("title", ""),
        "content": data.get("content", ""),
        "instance_id": instance_id,
        "created_at": datetime.now().isoformat(),
        "tags": data.get("tags", [])
    }
    store.add_thought(thought)
    coordinator.sync_thought(thought)
    return jsonify({"status": "ok", "thought_id": thought["id"]})


@app.route("/api/upload/skill", methods=["POST"])
@auth.require_client(require_approved=True)
def upload_skill():
    """Upload skill (auth + approval required)"""
    instance_id = request.instance_id
    data = request.get_json() or {}
    skill = {
        "id": data.get("id") or hashlib.sha256(f"{time.time()}_{instance_id}".encode()).hexdigest()[:16],
        "name": data.get("name", ""),
        "description": data.get("description", ""),
        "category": data.get("category", "general"),
        "content": data.get("content", ""),
        "instance_id": instance_id,
        "created_at": datetime.now().isoformat(),
        "version": data.get("version", "1.0.0")
    }
    store.add_skill(skill)
    return jsonify({"status": "ok", "skill_id": skill["id"]})


@app.route("/api/instances")
@auth.require_admin
def list_instances():
    """List instances (admin)"""
    instances = store.get_instances()
    return jsonify({"instances": list(instances.values())})


# ============== Admin API ==============

@app.route("/api/admin/approve_instance", methods=["POST"])
@auth.require_admin
def approve_instance():
    """Approve instance"""
    data = request.get_json() or {}
    instance_id = data.get("instance_id")
    instance = store.get_instance(instance_id)
    if not instance:
        return jsonify({"error": "Instance not found"}), 404
    store.update_instance(instance_id, {"approved": True})
    return jsonify({"status": "ok", "message": f"Instance {instance_id} approved"})


@app.route("/api/admin/revoke_instance", methods=["POST"])
@auth.require_admin
def revoke_instance():
    """Revoke instance"""
    data = request.get_json() or {}
    instance_id = data.get("instance_id")
    store.delete_instance(instance_id)
    return jsonify({"status": "ok", "message": f"Instance {instance_id} revoked"})


@app.route("/api/admin/add_client_key", methods=["POST"])
@auth.require_admin
def add_client_key():
    """Add/update client key (persisted to disk, survives restart)"""
    data = request.get_json() or {}
    instance_id = data.get("instance_id")
    new_key = data.get("api_key")
    if not instance_id or not new_key:
        return jsonify({"error": "instance_id and api_key required"}), 400
    auth.add_client_key(instance_id, new_key)
    store.save_client_key(instance_id, new_key)
    if store.instance_exists(instance_id):
        store.update_instance(instance_id, {"token": new_key, "approved": True})
    logger.info(f"[Admin] Client key added: instance={instance_id}")
    return jsonify({"status": "ok", "message": f"API key added for {instance_id}", "approved": True})


@app.route("/api/admin/remove_client_key", methods=["POST"])
@auth.require_admin
def remove_client_key():
    """Remove client key (deleted from both auth memory and disk)"""
    data = request.get_json() or {}
    instance_id = data.get("instance_id")
    if not instance_id:
        return jsonify({"error": "instance_id required"}), 400
    auth.remove_client_key(instance_id)
    store.remove_client_key(instance_id)
    logger.info(f"[Admin] Client key removed: instance={instance_id}")
    return jsonify({"status": "ok", "message": f"API key removed for {instance_id}"})


@app.route("/api/admin/list_client_keys")
@auth.require_admin
def list_client_keys():
    """List all registered client keys (values not exposed)"""
    return jsonify({"client_keys": auth.list_client_keys()})


# ============== Distributed Cluster API ==============

@app.route("/api/cluster/nodes")
@auth.require_admin
def cluster_nodes():
    """List cluster nodes"""
    return jsonify({
        "nodes": [
            {
                "node_id": n.node_id,
                "host": n.host,
                "port": n.port,
                "status": n.status.value,
                "storage_used": n.storage_used_gb
            }
            for n in coordinator.node_manager.nodes.values()
        ]
    })


@app.route("/api/cluster/add_node", methods=["POST"])
@auth.require_admin
def add_cluster_node():
    """Add cluster node (admin)"""
    data = request.get_json() or {}
    node_id = data.get("node_id")
    host = data.get("host")
    port = data.get("port", 5000)
    if not node_id or not host:
        return jsonify({"error": "node_id and host required"}), 400
    coordinator.add_node(node_id, host, port)
    return jsonify({"status": "ok", "message": f"Node {node_id} added"})


@app.route("/api/cluster/remove_node", methods=["POST"])
@auth.require_admin
def remove_cluster_node():
    """Remove cluster node (admin)"""
    data = request.get_json() or {}
    node_id = data.get("node_id")
    coordinator.remove_node(node_id)
    return jsonify({"status": "ok", "message": f"Node {node_id} removed"})


@app.route("/api/cluster/status")
@auth.require_admin
def cluster_status():
    """Get detailed cluster status"""
    return jsonify(coordinator.get_cluster_status())


# ============== Replica Storage API (inter-node) ==============

@app.route("/api/replica/store", methods=["POST"])
@node_auth.require_node_auth
def replica_store():
    """Store replica data (inter-node call)"""
    data = request.get_json() or {}
    data_id = data.get("data_id")
    data_type = data.get("data_type")
    content = data.get("content")
    if not data_id or not content:
        return jsonify({"error": "data_id and content required"}), 400
    success = store.replica_store(data_id, data_type, content)
    return jsonify({"status": "ok", "data_id": data_id})


@app.route("/api/replica/get/<data_id>")
@node_auth.require_node_auth
def replica_get(data_id):
    """Get replica data (inter-node call)"""
    result = store.replica_get(data_id)
    if result:
        return jsonify({"data_id": data_id, **result})
    return jsonify({"found": False, "data_id": data_id})


@app.route("/api/sync/pull", methods=["POST"])
@node_auth.require_node_auth
def sync_pull():
    """Inter-node data sync pull"""
    data = request.get_json() or {}
    source_node = data.get("source_node")
    sync_data = store.get_all_for_sync()
    sync_data["timestamp"] = datetime.now().isoformat()
    return jsonify(sync_data)


# ============== P2: Data Migration API (inter-node) ==============
# P1: requires HMAC signature auth
# Purpose: when a node joins, old nodes return a list of data that should migrate to it

@app.route("/api/replica/migrate")
@node_auth.require_node_auth
def replica_migrate():
    """
    Return data that should migrate to the target node.

    Query params:
        target: target node ID (new owner of migrated data)

    Logic:
    1. Iterate all data_ids in local storage
    2. For each data_id, calculate which nodes it should belong to via hash_ring
    3. If target is in the target node list, this data should migrate to target
    4. Return all items that should migrate
    """
    from distributed.sharding import ConsistentHashRing, Node

    target_node = request.args.get("target", "")

    if not target_node:
        return jsonify({"error": "target node ID required"}), 400

    all_thoughts = store.get_all_thoughts()
    all_skills = store.get_skills()

    items = []

    for thought in all_thoughts:
        data_id = thought.get("id", "")
        if not data_id:
            continue
        primary = coordinator.hash_ring.get_primary_node(data_id)
        replicas = coordinator.hash_ring.get_replica_nodes(
            data_id, coordinator.replication_factor
        )
        target_nodes = [primary] + (replicas[1:] if len(replicas) > 1 else [])

        if target_node in target_nodes:
            items.append({
                "data_id": data_id,
                "data_type": "thought",
                "content": thought,
            })

    for skill in all_skills:
        data_id = skill.get("id", "")
        if not data_id:
            continue
        primary = coordinator.hash_ring.get_primary_node(data_id)
        replicas = coordinator.hash_ring.get_replica_nodes(
            data_id, coordinator.replication_factor
        )
        target_nodes = [primary] + (replicas[1:] if len(replicas) > 1 else [])

        if target_node in target_nodes:
            items.append({
                "data_id": data_id,
                "data_type": "skill",
                "content": skill,
            })

    logger.info(f"[Migrate] Returning {len(items)} items for node {target_node}")
    return jsonify({"target": target_node, "items": items})


# ============== Error Handling ==============

@app.errorhandler(404)
def not_found(e):
    request_id = getattr(request, "_request_id", None)
    resp = jsonify({"error": "Not found", "code": "NOT_FOUND"})
    if request_id:
        resp.headers["X-Request-ID"] = request_id
    return resp, 404


@app.errorhandler(500)
def server_error(e):
    request_id = getattr(request, "_request_id", None)
    logger.error(f"[{request_id}] Server error: {e}", exc_info=True)
    resp = jsonify({"error": "Internal server error", "code": "INTERNAL_ERROR", "request_id": request_id})
    if request_id:
        resp.headers["X-Request-ID"] = request_id
    return resp, 500


@app.errorhandler(429)
def rate_limited(e):
    request_id = getattr(request, "_request_id", None)
    resp = jsonify({"error": "Rate limit exceeded", "code": "RATE_LIMIT"})
    if request_id:
        resp.headers["X-Request-ID"] = request_id
    return resp, 429


@app.errorhandler(Exception)
def unhandled_exception(e):
    """Catch-all for unhandled exceptions, prevents server crash"""
    request_id = getattr(request, "_request_id", None)
    logger.exception(f"[{request_id}] Unhandled exception: {e}")
    resp = jsonify({"error": "Internal server error", "code": "UNHANDLED_EXCEPTION", "request_id": request_id})
    if request_id:
        resp.headers["X-Request-ID"] = request_id
    return resp, 500


# ============== Startup ==============

if __name__ == "__main__":
    print("=" * 50)
    print("Mind Library v2.2.1 Distributed Secure Server (Thread-Safe)")
    print("=" * 50)
    print(f"Node ID:       {Config.NODE_ID}")
    print(f"Storage path:  {Config.DB_PATH}")
    print(f"Persist dir:   {Config.PERSIST_DIR}")
    print(f"Listen:        {Config.HOST}:{Config.PORT}")
    print(f"Log level:     {Config.LOG_LEVEL} {'(JSON)' if Config.LOG_JSON else ''}")
    print(f"CORS origins:  {Config.CORS_ORIGINS or '(not configured)'}")
    print(f"DEBUG:         {Config.DEBUG}")
    print(f"Thread safety: Enabled (RLock)")
    print(f"Node auth:     {'Enabled (HMAC-SHA256)' if Config.NODE_SECRET else 'Not configured (MIND_NODE_SECRET not set)'}")
    print(f"Admin auth:   {'Configured' if Config.ADMIN_API_KEY else 'NOT CONFIGURED!'}")
    print("=" * 50)
    app.run(host=Config.HOST, port=Config.PORT, debug=Config.DEBUG)