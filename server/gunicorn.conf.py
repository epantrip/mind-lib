"""
Gunicorn Production Config - gunicorn -c gunicorn.conf.py mind_server_v2.1:app

Key design decisions:
- workers = CPU cores * 2 + 1 (2-4 workers is sufficient)
- threads = 1 (RLock handles concurrency at Python level;
               single-thread + multi-worker is better than
               multi-thread + single-worker for I/O-bound workloads)
- timeout = 120 (distributed inter-node HTTP calls can be slow)
- keep-alive = 5 (reduce TCP connection overhead)
"""
import multiprocessing, os

# Auto-detect worker count
def _get_workers():
    env = os.environ.get("GUNICORN_WORKERS", "")
    if env.isdigit():
        return int(env)
    return min((multiprocessing.cpu_count() or 1) * 2 + 1, 8)  # max 8

# ========== Basic Config ==========
bind = os.environ.get("GUNICORN_BIND", "0.0.0.0:5000")
workers = _get_workers()
threads = 1  # single-thread + multi-worker for I/O-bound

# ========== Timeout & Retry ==========
timeout = 120
graceful_timeout = 30
keepalive = 5

# ========== Logging ==========
accesslog = "-"
errorlog = "-"
loglevel = os.environ.get("GUNICORN_LOG_LEVEL", "info")
access_log_format = "%(h)s %(l)s %(u)s %(t)s \"%(r)s\" %(s)s %(b)s \"%(f)s\" \"%(a)s\" request_id=%({X-Request-ID})s"

# ========== Process Naming ==========
proc_name = "mind-library-server"

# ========== Security ==========
worker_tmp_dir = "/dev/shm"

# ========== Signal Handling ==========
def on_starting(server):
    server.log.info("Mind Library server starting...")

def on_reload(server):
    server.log.info("Mind Library reloading...")

def when_ready(server):
    server.log.info(f"Mind Library ready, listening on {bind}, {workers} workers")

def worker_int(worker):
    worker.log.info(f"Worker {worker.pid} received SIGINT, shutting down...")
