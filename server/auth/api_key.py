"""
Mind Library 安全认证模块 - API Key 认证

安全提醒：
- 生产环境必须通过环境变量设置密钥
- 不要使用默认密钥！
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
    """API Key 认证管理器"""
    
    def __init__(self, admin_key: str = "", client_keys: Dict[str, str] = None):
        if not admin_key:
            raise ValueError(
                "Admin API Key 不能为空！请设置环境变量 MIND_ADMIN_API_KEY"
            )
        
        self.admin_key = admin_key
        self.client_keys: Dict[str, str] = client_keys or {}
        self._lock = threading.Lock()  # 保护 client_keys 的并发修改
        self.rate_limits: Dict[str, list] = {}  # instance_id -> [timestamps]
        self.rate_limit_window = 60  # 60秒窗口
        self.rate_limit_max = 60     # 最大60请求
        self._store = None  # DataStore 引用，由 set_store() 注入
    
    def set_store(self, store) -> None:
        """注入 DataStore 引用（供装饰器检查审批状态）"""
        self._store = store
        
    def verify_admin(self, api_key: str) -> bool:
        """验证管理员 API Key"""
        return hmac.compare_digest(self.admin_key, api_key)
    
    def verify_client(self, instance_id: str, api_key: str) -> bool:
        """验证客户端 API Key"""
        with self._lock:
            expected = self.client_keys.get(instance_id)
        if not expected:
            return False
        return hmac.compare_digest(expected, api_key)
    
    def check_rate_limit(self, instance_id: str) -> bool:
        """检查速率限制"""
        now = time.time()
        if instance_id not in self.rate_limits:
            self.rate_limits[instance_id] = []
        
        # 清理过期的时间戳
        self.rate_limits[instance_id] = [
            ts for ts in self.rate_limits[instance_id]
            if now - ts < self.rate_limit_window
        ]
        
        if len(self.rate_limits[instance_id]) >= self.rate_limit_max:
            return False
            
        self.rate_limits[instance_id].append(now)
        return True
    
    def add_client_key(self, instance_id: str, api_key: str) -> None:
        """动态添加客户端 API Key（线程安全）"""
        with self._lock:
            self.client_keys[instance_id] = api_key
        logger.info(f"客户端 Key 已添加: instance={instance_id}")
    
    def remove_client_key(self, instance_id: str) -> bool:
        """动态移除客户端 API Key（线程安全），返回是否成功"""
        with self._lock:
            if instance_id in self.client_keys:
                del self.client_keys[instance_id]
                logger.info(f"客户端 Key 已移除: instance={instance_id}")
                return True
        return False
    
    def list_client_keys(self) -> Dict[str, str]:
        """列出所有客户端 instance_id（不暴露密钥值）"""
        with self._lock:
            return {iid: "***" for iid in self.client_keys}
    
    def has_client_key(self, instance_id: str) -> bool:
        """检查指定实例是否已有 API Key"""
        with self._lock:
            return instance_id in self.client_keys
    
    def require_admin(self, f):
        """管理员权限装饰器"""
        @wraps(f)
        def decorated(*args, **kwargs):
            api_key = request.headers.get('X-API-Key')
            if not api_key or not self.verify_admin(api_key):
                return jsonify({'error': 'Unauthorized', 'code': 'ADMIN_REQUIRED'}), 401
            return f(*args, **kwargs)
        return decorated
    
    def require_client(self, f=None, *, require_approved: bool = False):
        """
        客户端权限装饰器（一步完成：认证 + 限流 + 可选审批检查）
        
        用法:
            @auth.require_client                          # 仅认证+限流
            @auth.require_client(require_approved=True)   # 认证+限流+审批检查
        
        认证通过后，instance_id 和 api_key 挂到 request 上供路由直接使用：
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
                
                # 可选：检查实例是否已审批
                if require_approved and self._store:
                    if not self._store.is_instance_approved(instance_id):
                        return jsonify({'error': 'Instance not approved', 'code': 'NOT_APPROVED'}), 403
                
                # 注入到 request 上，路由函数可直接使用
                request.instance_id = instance_id
                request.api_key = api_key
                
                return fn(*args, **kwargs)
            return decorated
        
        # 支持 @auth.require_client 和 @auth.require_client(require_approved=True) 两种写法
        if f is not None:
            return decorator(f)
        return decorator


def create_auth(persisted_keys: Dict[str, str] = None) -> APIKeyAuth:
    """
    创建认证实例（从环境变量 + 持久化存储加载）
    
    必须设置的环境变量：
    - MIND_ADMIN_API_KEY: 管理员密钥（必须）
    
    客户端密钥来源（优先级从高到低）：
    1. 持久化存储（DataStore 中的 client_keys.json）
    2. 环境变量（MIND_PUMPKING_MAIN_KEY, MIND_XIAODOU_KEY 等）
    """
    admin_key = os.environ.get('MIND_ADMIN_API_KEY')
    
    if not admin_key:
        logger.error("=" * 60)
        logger.error("安全错误：未设置 MIND_ADMIN_API_KEY 环境变量！")
        logger.error("请在启动前设置：")
        logger.error("  export MIND_ADMIN_API_KEY=your_secure_key")
        logger.error("=" * 60)
        raise ValueError("MIND_ADMIN_API_KEY 环境变量未设置")
    
    # 合并客户端密钥：持久化存储优先，环境变量兜底
    client_keys = dict(persisted_keys) if persisted_keys else {}
    
    for instance_id in ['pumpking_main', 'xiaodou']:
        key_env = f'MIND_{instance_id.upper()}_KEY'
        key = os.environ.get(key_env)
        # 环境变量作为 fallback，不覆盖持久化存储中的值
        if key and instance_id not in client_keys:
            client_keys[instance_id] = key
            logger.info(f"从环境变量加载客户端密钥: {instance_id}")
    
    if not client_keys:
        logger.warning("未设置任何客户端 API Key，将无法进行客户端认证")
    
    logger.info(f"认证模块已加载：管理员密钥已设置，{len(client_keys)} 个客户端密钥")
    
    return APIKeyAuth(admin_key, client_keys)
