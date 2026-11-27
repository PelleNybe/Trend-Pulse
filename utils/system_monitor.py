import psutil
import time
import math
import json
import redis
import threading
from loguru import logger
import os

def monitor_system(redis_client, channel='system_metrics', interval=5):
    logger.info(f"System Monitor started. Publishing to {channel} every {interval}s")
    while True:
        try:
            metrics = {
                'cpu_percent': psutil.cpu_percent(interval=None),
                'memory_percent': psutil.virtual_memory().percent,
                'disk_percent': psutil.disk_usage('/').percent,
                'timestamp': time.time(),
                'net_io': {
                    'bytes_sent': psutil.net_io_counters().bytes_sent,
                    'bytes_recv': psutil.net_io_counters().bytes_recv
                }
            }
            redis_client.publish(channel, json.dumps(metrics))
        except Exception as e:
            logger.error(f"Error in System Monitor: {e}")
        threading.Event().wait(interval)

def start_monitor_thread():
    redis_host = os.environ.get('REDIS_HOST', 'localhost')
    redis_port = int(os.environ.get('REDIS_PORT', 6379))
    try:
        r = redis.Redis(host=redis_host, port=redis_port, decode_responses=True)
        r.ping()
        thread = threading.Thread(target=monitor_system, args=(r,), daemon=True)
        thread.start()
        return True
    except redis.ConnectionError:
        logger.warning("Redis not available for system monitor")
        return False

def format_size(size_bytes):
    if size_bytes == 0:
        return "0B"
    if size_bytes < 0:
        return "Invalid size"
    size_name = ("B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB")
    try:
        i = int(math.floor(math.log(size_bytes, 1024)))
        if i < 0:
            i = 0
        if i >= len(size_name):
            i = len(size_name) - 1
        p = math.pow(1024, i)
        s = round(size_bytes / p, 2)
        if s == int(s):
            s = float(int(s))
        if s >= 1024.0 and i < len(size_name) - 1:
            s = 1.0
            i += 1
        return f"{s}{size_name[i]}"
    except (ValueError, OverflowError):
        return f"{size_bytes}B"
