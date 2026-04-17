"""
Mind Library Authentication Module

安全提醒：必须通过环境变量配置密钥
"""

from .api_key import APIKeyAuth, create_auth

__all__ = ["APIKeyAuth", "create_auth"]
