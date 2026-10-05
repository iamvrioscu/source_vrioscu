# Gunicorn settings for the VRIOSCU website.
# Bound to loopback only: nginx is the only thing that should reach it.
bind = "127.0.0.1:8000"
workers = 3                 # (2 x vCPU) + 1 is typical; SQLite in WAL mode handles this comfortably
worker_class = "sync"
timeout = 30
graceful_timeout = 20
keepalive = 5
max_requests = 2000         # recycle workers periodically
max_requests_jitter = 200
limit_request_line = 4094
limit_request_fields = 60
forwarded_allow_ips = "127.0.0.1"
accesslog = None            # the app writes structured request logs itself
errorlog = "-"
loglevel = "warning"
proc_name = "vrioscu-web"
