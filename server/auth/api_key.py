"""
Mind Library Security Authentication Module - API Key Authentication

Security Reminder:
- Production environments must set keys via environment variables
- Do not use default keys!
"""

import hmac
import hashlib
import time
import os
import logging
import threading
from typing import Optional, Dict
from functools import wraps
from flask import request, jsonify

logger = logging.getLogger(__name__)


class APIKeyAuth:
    """API Key authentication manager"""

    def __init__(self, admin_key: str = "", client_keys: Dict[str, str] = None):
        if not admin_key:
            raise ValueError(
                "Admin API Key cannot be empty! Please set environment variable MIND_ADMIN_API_KEY"
            )

        self.admin_key = admin_key
        self.client_keys: Dict[str, str] = client_keys or {}
        self._lock = threading.Lock()  # Protects concurrent modification of client_keys
        self.rate_limits: Dict[str, list] = {}  # instance_id -> [timestamps]
        self.rate_limit_window = 60  # 60-second window
        self.rate_limit_max = 60     # Max 60 requests
        self._store = None  # DataStore reference, injected via set_store()

    def set_store(self, store) -> None:
        """Inject DataStore reference (for decorator to check approval status)"""
        self._store = store

    def verify_admin(self, api_key: str) -> bool:
        """Verify admin API key"""
        return hmac.compare_digest(self.admin_key, api_key)

    def verify_client(self, instance_id: str, api_key: str) -> bool:
        """Verify client API key"""
        with self._lock:
            expected = self.client_keys.get(instance_id)
        if not expected:
            return False
        return hmac.compare_digest(expected, api_key)

    def check_rate_limit(self, instance_id: str) -> bool:
        """Check rate limit"""
        now = time.time()
        if instance_id not in self.rate_limits:
            self.rate_limits[instance_id] = []

        # Clean up expired timestamps
        self.rate_limits[instance_id] = [
            ts for ts in self.rate_limits[instance_id]
            if now - ts < self.rate_limit_window
        ]

        if len(self.rate_limits[instance_id]) >= self.rate_limit_max:
            return False

        self.rate_limits[instance_id].append(now)
        return True

    def add_client_key(self, instance_id: str, api_key: str) -> None:
        """Dynamically add client API key (thread-safe)"""
        with self._lock:
            self.client_keys[instance_id] = api_key
        logger.info(f"Client key added: instance={instance_id}")

    def remove_client_key(self, instance_id: str) -> bool:
        """Dynamically remove client API key (thread-safe), returns success status"""
        with self._lock:
            if instance_id in self.client_keys:
                del self.client_keys[instance_id]
                logger.info(f"Client key removed: instance={instance_id}")
                return True
        return False

    def list_client_keys(self) -> Dict[str, str]:
        """List all client instance_ids (does not expose key values)"""
        with self._lock:
            return {iid: "***" for iid in self.client_keys}

    def has_client_key(self, instance_id: str) -> bool:
        """Check if specified instance already has an API key"""
        with self._lock:
            return instance_id in self.client_keys

    def require_admin(self, f):
        """Admin permission decorator"""
        @wraps(f)
        def decorated(*args, **kwargs):
            api_key = request.headers.get('X-API-Key')
            if not api_key or not self.verify_admin(api_key):
                return jsonify({'error': 'Unauthorized', 'code': 'ADMIN_REQUIRED'}), 401
            return f(*args, **kwargs)
        return decorated

    def require_client(self, f=None, *, require_approved: bool = False):
        """
        Client permission decorator (one-step: auth + rate limit + optional approval check)

        Usage:
            @auth.require_client                          # Auth + rate limit only
            @auth.require_client(require_approved=True)   # Auth + rate limit + approval check

        After successful auth, instance_id and api_key are attached to request for direct use in routes:
            request.instance_id
            request.api_key
        """
        def decorator(fn):
            @wraps(fn)
            def decorated(*args, **kwargs):
                api_key = request.headers.get('X-API-Key')
                instance_id = request.headers.get('X-Instance-ID')

                if not api_key or not instance_id:
                    return jsonify({'error': 'Missing credentials', 'code': 'CREDENTIALS_REQUIRED'}), 401

                if not self.verify_client(instance_id, api_key):
                    return jsonify({'error': 'Invalid credentials', 'code': 'INVALID_KEY'}), 401

                if not self.check_rate_limit(instance_id):
                    return jsonify({'error': 'Rate limit exceeded', 'code': 'RATE_LIMIT'}), 429

                # Optional: check if instance is approved
                if require_approved and self._store:
                    if not self._store.is_instance_approved(instance_id):
                        return jsonify({'error': 'Instance not approved', 'code': 'NOT_APPROVED'}), 403

                # Inject into request for direct use in route functions
                request.instance_id = instance_id
                request.api_key = api_key

                return fn(*args, **kwargs)
            return decorated

        # Support both @auth.require_client and @auth.require_client(require_approved=True)
        if f is not None:
            return decorator(f)
        return decorator


def create_auth(persisted_keys: Dict[str, str] = None) -> APIKeyAuth:
    """
    Create auth instance (loads from environment variables + persistent storage)

    Required environment variables:
    - MIND_ADMIN_API_KEY: Admin key (required)

    Client key sources (priority high to low):
    1. Persistent storage (client_keys.json in DataStore)
    2. Environment variables (MIND_PUMPKING_MAIN_KEY, MIND_XIAODOU_KEY, etc.)
    """
    admin_key = os.environ.get('MIND_ADMIN_API_KEY')

    if not admin_key:
        logger.error("=" * 60)
        logger.error("Security error: MIND_ADMIN_API_KEY environment variable is not set!")
        logger.error("Please set before starting:")
        logger.error("  export MIND_ADMIN_API_KEY=your_secure_key")
        logger.error("=" * 60)
        raise ValueError("MIND_ADMIN_API_KEY environment variable is not set")

    # Merge client keys: persistent storage takes priority, environment variables as fallback
    client_keys = dict(persisted_keys) if persisted_keys else {}

    for instance_id in ['pumpking_main', 'xiaodou']:
        key_env = f'MIND_{instance_id.upper()}_KEY'
        key = os.environ.get(key_env)
        # Environment variables as fallback, do not overwrite values in persistent storage
        if key and instance_id not in client_keys:
            client_keys[instance_id] = key
            logger.info(f"Loaded client key from environment variable: {instance_id}")

    if not client_keys:
        logger.warning("No client API keys set, client authentication will not be possible")

    logger.info(f"Auth module loaded: admin key set, {len(client_keys)} client keys")

    return APIKeyAuth(admin_key, client_keys)
