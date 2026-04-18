"""
🧠 分布式节点间 API 认证模块

节点间通信使用 HMAC-SHA256 签名验证：
- 所有节点持有同一个 MIND_NODE_SECRET
- 出站请求附加 X-Node-Signature header
- 验签：HMAC(request_method + request_path + body_sha256, secret)
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
    """节点间 API 认证（HMAC-SHA256）"""

    HEADER_SIGNATURE = "X-Node-Signature"
    HEADER_NODE_ID = "X-Node-ID"

    def __init__(self, secret: str = ""):
        if not secret:
            raise ValueError(
                "MIND_NODE_SECRET 环境变量未设置！"
                "所有集群节点必须使用相同的共享密钥。"
            )
        self.secret = secret.encode("utf-8")
        self.local_node_id = os.environ.get("MIND_NODE_ID", "unknown")

    def sign(self, method: str, path: str, body: bytes = b"") -> str:
        """
        生成 HMAC-SHA256 签名
        
        签名内容 = HTTP_METHOD + request_path + SHA256(request_body)
        """
        body_hash = hashlib.sha256(body).hexdigest()
        message = f"{method.upper()}{path}{body_hash}".encode("utf-8")
        return hmac.new(self.secret, message, hashlib.sha256).hexdigest()

    def verify(self, signature: str, method: str, path: str, body: bytes = b"") -> bool:
        """验签"""
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
        为出站请求生成带签名的 headers
        
        示例：
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
        Flask 装饰器：保护节点间 API
        
        验签流程：
        1. 从 X-Node-Signature 读取签名
        2. 从 X-Node-ID 读取请求来源节点
        3. 用相同算法重新计算签名并比对
        """
        @wraps(f)
        def decorated(*args, **kwargs):
            signature = request.headers.get(self.HEADER_SIGNATURE, "")
            node_id = request.headers.get(self.HEADER_NODE_ID, "unknown")

            if not signature:
                logger.warning(f"[NodeAuth] 节点 {node_id} 缺少签名 header")
                return jsonify({
                    "error": "Missing node authentication",
                    "code": "NODE_AUTH_REQUIRED"
                }), 401

            # 获取原始请求内容用于验签
            method = request.method
            path = request.path
            body = request.get_data()

            if not self.verify(signature, method, path, body):
                logger.warning(
                    f"[NodeAuth] 节点 {node_id} 签名验证失败 "
                    f"(method={method}, path={path})"
                )
                return jsonify({
                    "error": "Invalid node signature",
                    "code": "NODE_AUTH_FAILED"
                }), 401

            logger.debug(f"[NodeAuth] 节点 {node_id} 认证通过")
            return f(*args, **kwargs)

        return decorated


# ─────────────────────────────────────────────
# 环境变量检查 & 工厂函数
# ─────────────────────────────────────────────

_node_auth_instance: Optional[NodeAuth] = None


def get_node_auth() -> NodeAuth:
    """获取 NodeAuth 单例（延迟初始化）"""
    global _node_auth_instance
    if _node_auth_instance is None:
        secret = os.environ.get("MIND_NODE_SECRET")
        _node_auth_instance = NodeAuth(secret)
    return _node_auth_instance


def require_node_auth_decorator(f):
    """
    Flask 装饰器（使用单例）
    
    在主服务器的路由上使用此装饰器：
        @app.route('/api/replica/store', methods=['POST'])
        @require_node_auth_decorator
        def replica_store(): ...
    """
    return get_node_auth().require_node_auth(f)


def create_node_auth(secret: str = "") -> NodeAuth:
    """创建 NodeAuth 实例（手动传入密钥时用）"""
    if not secret:
        secret = os.environ.get("MIND_NODE_SECRET", "")
    return NodeAuth(secret)


# ─────────────────────────────────────────────
# Requests Session 集成（replication.py 用）
# ─────────────────────────────────────────────

class AuthenticatedSession:
    """
    带节点认证的 requests.Session 封装
    
    替代 replication.py 中的裸 requests 调用
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
