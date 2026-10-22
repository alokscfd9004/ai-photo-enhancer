# Gunicorn configuration for AI Photo Enhancer.
import multiprocessing
import os

# Render (and most PaaS) inject $PORT and route to it.
bind = "0.0.0.0:{}".format(int(os.environ.get("PORT", "8000")))

# Small instances (Render free is 0.1 vCPU / 512MB) cannot afford many workers.
workers = int(os.environ.get("WEB_CONCURRENCY", max(1, min(multiprocessing.cpu_count(), 2))))
threads = int(os.environ.get("GUNICORN_THREADS", 2))
worker_class = "gthread"
timeout = int(os.environ.get("GUNICORN_TIMEOUT", 300))
graceful_timeout = 30
keepalive = 5
accesslog = "-"
errorlog = "-"
loglevel = "info"
capture_output = True
max_requests = 500
max_requests_jitter = 50
