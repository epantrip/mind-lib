#!/usr/bin/env python3
"""
Mind Library 客户端配置示例
复制此文件为 config.py 并修改配置
"""

# ============ 服务器配置 ============
SERVER_URL = "http://localhost:5000"  # 思想库服务器地址

# ============ 实例配置 ============
INSTANCE_ID = "my_ai_instance"        # 唯一标识符(英文+数字)
INSTANCE_NAME = "My AI"               # 显示名称
INSTANCE_DESC = "AI实例描述"           # 可选描述

# ============ 同步配置 ============
AUTO_SYNC_INTERVAL = 3600             # 自动同步间隔 (秒)，0为禁用
LAST_SYNC_FILE = "~/.pumpking_last_sync"  # 上次同步时间记录文件

# ============ 存储配置 ============
THOUGHTS_SAVE_DIR = "~/memory/mind_sync"  # 下载的思想保存目录
SKILLS_SAVE_DIR = "~/skills"              # 下载的技能保存目录
