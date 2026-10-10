import os

# Railway automatically sets the PORT environment variable.
# Since you configured Port 5001 in Railway Networking, default to 5001.
port = os.environ.get('PORT', '5001')
bind = f'0.0.0.0:{port}'

workers = 1
threads = 4
timeout = 120
keepalive = 5

accesslog = '-'
errorlog = '-'
loglevel = 'info'
