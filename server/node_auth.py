"""
🧠 Distributed Inter-node API Authentication Module

Inter-node communication uses HMAC-SHA256 signature verification:
- All nodes share the same MIND_NODE_SECRET
- Outbound requests attach X-Node-Signature header
- Verification: HMAC(request_method + request_path + body_sha256, secret)
"""

import hmac
import hashlib
import os
import logging
from functools import wraps
from typing import Optional
from flask import request, jsonify

logger = logging.getLogger(__name__)


class NodeAuth:
    """Inter-node API authentication (HMAC-SHA256)"""

    HEADER_SIGNATURE = "X-Node-Signature"
    HEADER_NODE_ID = "X-Node-ID"

    def __init__(self, secret: str = ""):
        if not secret:
            raise ValueError(
                "MIND_NODE_SECRET environment variable is not set! "
                "All cluster nodes must use the same shared secret."
            )
        self.secret = secret.encode("utf-8")
        self.local_node_id = os.environ.get("MIND_NODE_ID", "unknown")

    def sign(self, method: str, path: str, body: bytes = b"") -> str:
        """
        Generate HMAC-SHA256 signature

        Signature content = HTTP_METHOD + request_path + SHA256(request_body)
        """
        body_hash = hashlib.sha256(body).hexdigest()
        message = f"{method.upper()}{path}{body_hash}".encode("utf-8")
        return hmac.new(self.secret, message, hashlib.sha256).hexdigest()

    def verify(self, signature: str, method: str, path: str, body: bytes = b"") -> bool:
        """Verify signature"""
        expected = self.sign(method, path, body)
        return hmac.compare_digest(expected, signature)

    def inject_headers(
        self,
        method: str,
        path: str,
        body: bytes = b"",
        extra: Optional[dict] = None,
    ) -> dict:
        """
        Generate signed headers for outbound requests

        Example:
            headers = node_auth.inject_headers("POST", "/api/replica/store", body_bytes)
            requests.post(url, headers=headers, json=payload)
        """
        headers = {
            "Content-Type": "application/json",
            self.HEADER_NODE_ID: self.local_node_id,
            self.HEADER_SIGNATURE: self.sign(method, path, body),
        }
        if extra:
            headers.update(extra)
        return headers

    def require_node_auth(self, f):
        """
        Flask decorator: protect inter-node APIs

        Verification flow:
        1. Read signature from X-Node-Signature header
        2. Read source node from X-Node-ID header
        3. Recalculate signature with the same algorithm and compare
        """
        @wraps(f)
        def decorated(*args, **kwargs):
            signature = request.headers.get(self.HEADER_SIGNATURE, "")
            node_id = request.headers.get(self.HEADER_NODE_ID, "unknown")

            if not signature:
                logger.warning(f"[NodeAuth] Node {node_id} missing signature header")
                return jsonify({
                    "error": "Missing node authentication",
                    "code": "NODE_AUTH_REQUIRED"
                }), 401

            # Get original request body for verification
            # request.full_path always has '?' suffix even with no query params
            # To match client sign() behavior, rebuild using request.path + query_string
            method = request.method
            qs = request.query_string.decode()
            path = request.path + (('?' + qs) if qs else '')
            body = request.get_data()

            if not self.verify(signature, method, path, body):
                logger.warning(
                    f"[NodeAuth] Node {node_id} signature verification failed "
                    f"(method={method}, path={path})"
                )
                return jsonify({
                    "error": "Invalid node signature",
                    "code": "NODE_AUTH_FAILED"
                }), 401

            logger.debug(f"[NodeAuth] Node {node_id} authentication passed")
            return f(*args, **kwargs)

        return decorated


# ─────────────────────────────────────────────
# Environment Variable Check & Factory Functions
# ─────────────────────────────────────────────

_node_auth_instance: Optional[NodeAuth] = None


def get_node_auth() -> NodeAuth:
    """Get NodeAuth singleton (lazy initialization)"""
    global _node_auth_instance
    if _node_auth_instance is None:
        secret = os.environ.get("MIND_NODE_SECRET")
        _node_auth_instance = NodeAuth(secret)
    return _node_auth_instance


def require_node_auth_decorator(f):
    """
    Flask decorator (uses singleton)

    Use this decorator on main server routes:
        @app.route('/api/replica/store', methods=['POST'])
        @require_node_auth_decorator
        def replica_store(): ...
    """
    return get_node_auth().require_node_auth(f)


def create_node_auth(secret: str = "") -> NodeAuth:
    """Create NodeAuth instance (used when manually passing secret)"""
    if not secret:
        secret = os.environ.get("MIND_NODE_SECRET", "")
    return NodeAuth(secret)


# ─────────────────────────────────────────────
# Requests Session Integration (used by replication.py)
# ─────────────────────────────────────────────

class AuthenticatedSession:
    """
    requests.Session wrapper with node authentication

    Replaces bare requests calls in replication.py
    """

    def __init__(self, node_auth: NodeAuth):
        self.node_auth = node_auth

    def post(
        self,
        url: str,
        path: str,
        json: dict = None,
        timeout: int = 30,
    ) -> "requests.Response":
        import requests
        import json as _json

        body = _json.dumps(json or {}).encode("utf-8")
        headers = self.node_auth.inject_headers("POST", path, body)
        return requests.post(url, headers=headers, json=json, timeout=timeout)

    def get(
        self,
        url: str,
        path: str,
        timeout: int = 30,
    ) -> "requests.Response":
        import requests

        headers = self.node_auth.inject_headers("GET", path)
        return requests.get(url, headers=headers, timeout=timeout)
