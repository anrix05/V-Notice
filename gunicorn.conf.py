import os

# Railway automatically sets the PORT environment variable.
# If not set, default to 5000.
port = os.environ.get('PORT', '5000')
bind = f'0.0.0.0:{port}'

workers = 1
threads = 4
worker_class = 'gthread'
timeout = 120
keepalive = 5

accesslog = '-'
errorlog = '-'
loglevel = 'info'
