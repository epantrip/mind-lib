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
        self.client_keys = client_keys or {}
        self.rate_limits: Dict[str, list] = {}  # instance_id -> [timestamps]
        self.rate_limit_window = 60  # 60秒窗口
        self.rate_limit_max = 60     # 最大60请求
        
    def verify_admin(self, api_key: str) -> bool:
        """验证管理员 API Key"""
        return hmac.compare_digest(self.admin_key, api_key)
    
    def verify_client(self, instance_id: str, api_key: str) -> bool:
        """验证客户端 API Key"""
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
    
    def require_admin(self, f):
        """管理员权限装饰器"""
        @wraps(f)
        def decorated(*args, **kwargs):
            api_key = request.headers.get('X-API-Key')
            if not api_key or not self.verify_admin(api_key):
                return jsonify({'error': 'Unauthorized', 'code': 'ADMIN_REQUIRED'}), 401
            return f(*args, **kwargs)
        return decorated
    
    def require_client(self, f):
        """客户端权限装饰器"""
        @wraps(f)
        def decorated(*args, **kwargs):
            api_key = request.headers.get('X-API-Key')
            instance_id = request.headers.get('X-Instance-ID')
            
            if not api_key or not instance_id:
                return jsonify({'error': 'Missing credentials', 'code': 'CREDENTIALS_REQUIRED'}), 401
            
            if not self.verify_client(instance_id, api_key):
                return jsonify({'error': 'Invalid credentials', 'code': 'INVALID_KEY'}), 401
                
            if not self.check_rate_limit(instance_id):
                return jsonify({'error': 'Rate limit exceeded', 'code': 'RATE_LIMIT'}), 429
                
            return f(*args, **kwargs)
        return decorated


def create_auth() -> APIKeyAuth:
    """
    创建认证实例（从环境变量加载）
    
    必须设置的环境变量：
    - MIND_ADMIN_API_KEY: 管理员密钥（必须）
    
    可选的客户端密钥：
    - MIND_PUMPKING_MAIN_KEY: pumpking_main 客户端密钥
    - MIND_XIAODOU_KEY: xiaodou 客户端密钥
    """
    admin_key = os.environ.get('MIND_ADMIN_API_KEY')
    
    if not admin_key:
        logger.error("=" * 60)
        logger.error("安全错误：未设置 MIND_ADMIN_API_KEY 环境变量！")
        logger.error("请在启动前设置：")
        logger.error("  export MIND_ADMIN_API_KEY=your_secure_key")
        logger.error("=" * 60)
        raise ValueError("MIND_ADMIN_API_KEY 环境变量未设置")
    
    # 加载客户端密钥
    client_keys = {}
    for instance_id in ['pumpking_main', 'xiaodou']:
        key_env = f'MIND_{instance_id.upper()}_KEY'
        key = os.environ.get(key_env)
        if key:
            client_keys[instance_id] = key
    
    if not client_keys:
        logger.warning("未设置任何客户端 API Key，将无法进行客户端认证")
    
    logger.info(f"认证模块已加载：管理员密钥已设置，{len(client_keys)} 个客户端密钥")
    
    return APIKeyAuth(admin_key, client_keys)
