"""
Gunicorn 生产配置 — gunicorn -c gunicorn.conf.py mind_server_v2.1:app

关键设计：
- workers = CPU核心数 * 2 + 1（2-4 个worker足够）
- threads = 1（因为我们在 Python 层用 RLock 做并发控制，
              多线程 + 单 worker 比单线程 + 多 worker 更适合 IO 密集型）
- timeout = 120（分布式节点间 HTTP 调用可能较慢）
- keep-alive = 5（减少 TCP 建连开销）
"""
import multiprocessing
import os

# 自动检测 worker 数量
def _get_workers():
    env = os.environ.get('GUNICORN_WORKERS', '')
    if env.isdigit():
        return int(env)
    return min((multiprocessing.cpu_count() or 1) * 2 + 1, 8)  # 最多 8 个

# ========== 基础配置 ==========
bind = os.environ.get('GUNICORN_BIND', '0.0.0.0:5000')
workers = _get_workers()
threads = 1  # 单线程 + 多 worker > 多线程 + 单 worker（IO 密集型场景）

# ========== 超时与重试 ==========
timeout = 120          # 请求超时（秒），分布式节点间调用较慢
graceful_timeout = 30  # 优雅终止超时
keepalive = 5         # keep-alive 秒数

# ========== 日志 ==========
accesslog = '-'                        # stdout（配合 JSON 日志）
errorlog = '-'                         # stderr
loglevel = os.environ.get('GUNICORN_LOG_LEVEL', 'info')
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" request_id=%({X-Request-ID})s'

# ========== 进程命名 ==========
proc_name = 'mind-library-server'

# ========== 安全 ==========
worker_tmp_dir = '/dev/shm'  # Linux 共享内存tmpfs，减少磁盘 I/O（仅 Linux）

# ========== 预加载 ==========
# preload_app = True  # 注释：预加载会共享 fork 后的内存，
#                      # 但我们的 Config 从 env 读取，每个 worker 独立读取 env 没问题
#                      # 如果开启，要确保 Config 不在 import 时做副作用
#                      # 当前 Config.setup_logging() 在模块加载时执行，
#                      # 多 worker 场景下每个 worker 会独立初始化日志，没问题

# ========== 信号处理 ==========
def on_starting(server):
    """服务器启动时"""
    server.log.info("Mind Library 服务器启动中...")

def on_reload(server):
    """热重载时（如 SIGHUP）"""
    server.log.info("Mind Library 正在热重载...")

def when_ready(server):
    """workers 启动完成后"""
    server.log.info(f"Mind Library 就绪，监听 {bind}，{workers} workers")

def worker_int(worker):
    """Worker 被 SIGINT 终止前"""
    worker.log.info(f"Worker {worker.pid} 收到 SIGINT，正在关闭...")
