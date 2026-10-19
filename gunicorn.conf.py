# Gunicorn configuration for AI Photo Enhancer.
import multiprocessing

bind = "0.0.0.0:8000"
workers = max(2, min(multiprocessing.cpu_count(), 4))
threads = 4
worker_class = "gthread"
timeout = 120
graceful_timeout = 30
keepalive = 5
accesslog = "-"
errorlog = "-"
loglevel = "info"
capture_output = True
max_requests = 500
max_requests_jitter = 50
