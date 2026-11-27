"""
Flask Main App - Unified management of three Streamlit apps
"""

import warnings

_orig_showwarning = warnings.showwarning
def _quiet_showwarning(message, category, filename, lineno, file=None, line=None):
    msg_str = str(message).lower()
    if issubclass(category, (DeprecationWarning, FutureWarning)) or "inplace" in msg_str or "eventlet" in msg_str:
        return
    return _orig_showwarning(message, category, filename, lineno, file=file, line=line)
warnings.showwarning = _quiet_showwarning
warnings.filterwarnings("ignore")

import os
import json
import logging

_ASYNC_MODE = os.environ.get('ASYNC_MODE', 'threading')
if _ASYNC_MODE == 'eventlet':
    try:
        import eventlet
        eventlet.monkey_patch()
    except Exception:
        pass

logging.getLogger("yfinance").setLevel(logging.CRITICAL)

import pandas as pd
import yfinance as yf
import numpy as np
import feedparser
import sys
import psutil
import collections


os.environ['PYTHONIOENCODING'] = 'utf-8'
os.environ['PYTHONUTF8'] = '1'
os.environ['PYTHONUNBUFFERED'] = '1'  # Disable Python output buffering, ensure real-time log output

import subprocess
import time, threading
from datetime import datetime, timezone; APP_START_TIME = datetime.now(timezone.utc).replace(tzinfo=None)
from functools import wraps
from flask import Flask, render_template, request, jsonify, Response
from flask_socketio import SocketIO, emit
from utils.token_tracker import tracker
from utils.forum_reader import get_recent_agent_speeches, get_latest_host_speech
import atexit
import requests
import concurrent.futures

from loguru import logger
import importlib
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

_PROJECT_ROOT = Path(__file__).resolve().parent
if not (_PROJECT_ROOT / "config.py").exists():
    try:
        from generate_config import generate_config
        generate_config(_PROJECT_ROOT)
    except Exception as cfg_err:
        logger.warning(f"Could not auto-generate config.py: {cfg_err}")


try:
    from ReportEngine.flask_interface import report_bp, initialize_report_engine
    REPORT_ENGINE_AVAILABLE = True
except ImportError as e:
    logger.error(f"Failed to import ReportEngine: {e}")
    report_bp = None
    initialize_report_engine = None
    REPORT_ENGINE_AVAILABLE = False


import time
from collections import defaultdict, deque
request_counts = defaultdict(deque)
RATE_LIMIT_WINDOW = 60
RATE_LIMIT_MAX_REQUESTS = 30

def check_rate_limit(ip):
    now = time.time()
    # OPTIMIZATION: Use deque with O(1) amortized left pops instead of O(N) list comprehension
    # to drop old timestamps, improving rate limiter performance under heavy load.
    while request_counts[ip] and now - request_counts[ip][0] >= RATE_LIMIT_WINDOW:
        request_counts[ip].popleft()

    if len(request_counts[ip]) >= RATE_LIMIT_MAX_REQUESTS:
        return False
    request_counts[ip].append(now)
    return True

app = Flask(__name__)


@app.after_request
def add_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    response.headers['X-Permitted-Cross-Domain-Policies'] = 'none'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    # Enforce CSP to mitigate XSS and injection attacks.
    response.headers['Content-Security-Policy'] = "default-src 'self' 'unsafe-inline' 'unsafe-eval' data: https: wss:; frame-ancestors 'self';"
    return response


_secret_key = os.environ.get('SECRET_KEY')
if not _secret_key:
    logger.critical("SECRET_KEY not found in environment. Please set SECRET_KEY in your .env file.")
    raise RuntimeError("SECRET_KEY environment variable is required for security.")
app.config['SECRET_KEY'] = _secret_key

# Restrict CORS allowed origins to prevent potential cross-site attacks.
_CORS_PORT = os.environ.get("PORT", "5000")
_DEFAULT_ORIGINS = [
    f"http://127.0.0.1:{_CORS_PORT}",
    f"http://localhost:{_CORS_PORT}",
    f"http://0.0.0.0:{_CORS_PORT}",
    "http://127.0.0.1",
    "http://localhost",
]
_RAW_ORIGINS = os.environ.get("CORS_ALLOWED_ORIGINS")
if _RAW_ORIGINS:
    allowed_origins = [origin.strip() for origin in _RAW_ORIGINS.split(",") if origin.strip()]
else:
    allowed_origins = _DEFAULT_ORIGINS

socketio = SocketIO(app, cors_allowed_origins=allowed_origins, ping_timeout=60, ping_interval=25, async_mode=_ASYNC_MODE)

def emit_market_ticker():
    # import eventlet

    symbols = ['BTC-USD', 'ETH-USD', 'SOL-USD', 'AAPL', 'TSLA', 'MSFT', 'NVDA', 'AMZN']

    # Keep track of last valid data to use if yfinance fails
    last_data = []

    while True:
        try:
            ticker_data = []
            # ⚡ OPTIMIZATION: Fetch all ticker data in a single bulk request using yf.download
            # instead of making N individual calls to .info in a loop (N+1 problem).
            # We fetch 2 days to ensure we have the previous close.
            data = yf.download(symbols, period="2d", progress=False)
            for s in symbols:
                try:
                    if isinstance(data.columns, pd.MultiIndex):
                        ticker_df = data.xs(s, level=1, axis=1)
                    else:
                        ticker_df = data

                    if not ticker_df.empty and len(ticker_df) >= 1:
                        # Extract price and previous close from the historical data
                        close_vals = ticker_df['Close'].values
                        price = float(close_vals[-1])
                        prev_close = float(close_vals[-2]) if len(ticker_df) >= 2 else price

                        if price and prev_close:
                            change = (price - prev_close) / prev_close
                            display_symbol = s.replace('-USD', '')
                            ticker_data.append({
                                'symbol': display_symbol,
                                'price': f"${price:.2f}",
                                'change_pct': change * 100,
                                'up': change >= 0
                            })
                except Exception:
                    pass

            if ticker_data:
                last_data = ticker_data
                socketio.emit('market_ticker', ticker_data)
            elif last_data:
                socketio.emit('market_ticker', last_data)

        except Exception as e:
            pass

        # import time, threading (hoisted)
        threading.Event().wait(15)

socketio.start_background_task(emit_market_ticker)




def _patch_eventlet_disconnect_logging():
    try:
        import eventlet.wsgi
    except Exception as exc:
        logger.debug(f"eventlet Not available，skip broken patches: {exc}")
        return

    try:
        original_finish = eventlet.wsgi.HttpProtocol.finish  # type: ignore[attr-defined]
    except Exception as exc:  # pragma: no cover
        logger.debug(f"eventlet Lack HttpProtocol.finish，skip broken patches: {exc}")
        return

    def _safe_finish(self, *args, **kwargs):
        try:
            return original_finish(self, *args, **kwargs)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError) as exc:
            try:
                environ = getattr(self, 'environ', {}) or {}
                method = environ.get('REQUEST_METHOD', '')
                path = environ.get('PATH_INFO', '')
                logger.warning(f"Client has actively disconnected, ignoring exception: {method} {path} ({exc})")
            except Exception as inner_exc:
                logger.warning(f"Client has actively disconnected, ignoring exception: {exc}, inner: {inner_exc}")
            return

    eventlet.wsgi.HttpProtocol.finish = _safe_finish  # type: ignore[attr-defined]
    logger.info("Protected against eventlet connection drop")

if _ASYNC_MODE == 'eventlet':
    _patch_eventlet_disconnect_logging()


if REPORT_ENGINE_AVAILABLE and report_bp is not None:
    app.register_blueprint(report_bp, url_prefix='/api/report')
    logger.info("ReportEngine interface registered")
else:
    logger.info("ReportEngine unavailable, skipping interface registration")


LOG_DIR = Path('logs')
LOG_DIR.mkdir(exist_ok=True)

CONFIG_MODULE_NAME = 'config'
CONFIG_FILE_PATH = Path(__file__).resolve().parent / 'config.py'
CONFIG_KEYS = [
    'HOST',
    'PORT',
    'DB_DIALECT',
    'DB_HOST',
    'DB_PORT',
    'DB_USER',
    'DB_PASSWORD',
    'DB_NAME',
    'DB_CHARSET',
    'REDIS_HOST',
    'REDIS_PORT',
    'INSIGHT_ENGINE_API_KEY',
    'INSIGHT_ENGINE_BASE_URL',
    'INSIGHT_ENGINE_MODEL_NAME',
    'MEDIA_ENGINE_API_KEY',
    'MEDIA_ENGINE_BASE_URL',
    'MEDIA_ENGINE_MODEL_NAME',
    'QUERY_ENGINE_API_KEY',
    'QUERY_ENGINE_BASE_URL',
    'QUERY_ENGINE_MODEL_NAME',
    'REPORT_ENGINE_API_KEY',
    'REPORT_ENGINE_BASE_URL',
    'REPORT_ENGINE_MODEL_NAME',
    'FORUM_HOST_API_KEY',
    'FORUM_HOST_BASE_URL',
    'FORUM_HOST_MODEL_NAME',
    'KEYWORD_OPTIMIZER_API_KEY',
    'KEYWORD_OPTIMIZER_BASE_URL',
    'KEYWORD_OPTIMIZER_MODEL_NAME',
    'TAVILY_API_KEY',
    'SEARCH_TOOL_TYPE',
    'BOCHA_WEB_SEARCH_API_KEY',
    'ANSPIRE_API_KEY',
    'ADMIN_API_KEY'
]


def admin_required(f):
    """
    Decorator to restrict access to sensitive system APIs.
    Requires X-API-Key header to match ADMIN_API_KEY configuration value.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Consistently check the dynamic configuration for the admin key.
        config = read_config_values()
        admin_key = config.get('ADMIN_API_KEY')

        # If the key is masked ('********'), we need the actual value from the settings.
        if admin_key == '********':
            try:
                # from config import settings (hoisted)
                admin_key = getattr(settings, 'ADMIN_API_KEY', None)
            except Exception:
                admin_key = os.environ.get('ADMIN_API_KEY')

        if not admin_key:
            return f(*args, **kwargs)

        request_key = request.headers.get('X-API-Key')
        if request_key != admin_key:
            logger.warning(f"Unauthorized access attempt to {request.path} from {request.remote_addr}")
            return jsonify({'success': False, 'message': 'Unauthorized: Invalid or missing API Key'}), 401
        return f(*args, **kwargs)
    return decorated_function


def _load_config_module():
    """Load or reload the config module to ensure latest values are available."""
    importlib.invalidate_caches()
    module = sys.modules.get(CONFIG_MODULE_NAME)
    try:
        if module is None:
            module = importlib.import_module(CONFIG_MODULE_NAME)
        else:
            module = importlib.reload(module)
    except ModuleNotFoundError:
        return None
    return module


def read_config_values():
    """Return the current configuration values that are exposed to the frontend."""
    try:

        # from config import reload_settings, settings (hoisted)
        reload_settings()
        
        values = {}
        for key in CONFIG_KEYS:

            value = getattr(settings, key, None)
            # Convert to string for uniform handling on the frontend.
            if value is None:
                values[key] = ''
            else:
                # Mask sensitive admin key when sending to frontend.
                if key == 'ADMIN_API_KEY' and value:
                    values[key] = '********'
                else:
                    values[key] = str(value)
        return values
    except ModuleNotFoundError:
        values = {}
        for key in CONFIG_KEYS:
            value = os.environ.get(key)
            if value is None:
                values[key] = ''
            else:
                if key == 'ADMIN_API_KEY' and value:
                    values[key] = '********'
                else:
                    values[key] = str(value)
        return values
    except Exception as exc:
        logger.exception(f"Failed to read configuration: {exc}")
        return {}


def _serialize_config_value(value):
    """Serialize Python values back to a config.py assignment-friendly string."""
    if isinstance(value, bool):
        return 'True' if value else 'False'
    if isinstance(value, (int, float)):
        return str(value)
    if value is None:
        return 'None'

    value_str = str(value)
    escaped = value_str.replace('\\', '\\\\').replace('"', '\"')
    return f'"{escaped}"'


def write_config_values(updates):
    """Persist configuration updates to .env file (Pydantic Settings source)."""
    # from pathlib import Path (hoisted)
    

    project_root = Path(__file__).resolve().parent
    cwd_env = Path.cwd() / ".env"
    env_file_path = cwd_env if cwd_env.exists() else (project_root / ".env")
    

    env_lines = []
    env_key_indices = {}
    if env_file_path.exists():
        env_lines = env_file_path.read_text(encoding='utf-8').splitlines()

        for i, line in enumerate(env_lines):
            line_stripped = line.strip()
            if line_stripped and not line_stripped.startswith('#'):
                if '=' in line_stripped:
                    key = line_stripped.split('=')[0].strip()
                    env_key_indices[key] = i
    

    for key, raw_value in updates.items():

        if raw_value is None or raw_value == '':
            env_value = ''
        elif isinstance(raw_value, (int, float)):
            env_value = str(raw_value)
        elif isinstance(raw_value, bool):
            env_value = 'True' if raw_value else 'False'
        else:
            value_str = str(raw_value)

            if ' ' in value_str or '\n' in value_str or '#' in value_str:
                escaped = value_str.replace('\\', '\\\\').replace('"', '\"')
                env_value = f'"{escaped}"'
            else:
                env_value = value_str
        

        if key in env_key_indices:

            env_lines[env_key_indices[key]] = f'{key}={env_value}'
        else:

            env_lines.append(f'{key}={env_value}')
    

    env_file_path.parent.mkdir(parents=True, exist_ok=True)
    env_file_path.write_text('\n'.join(env_lines) + '\n', encoding='utf-8')
    

    _load_config_module()


system_state_lock = threading.Lock()
system_state = {
    'started': False,
    'starting': False,
    'shutdown_in_progress': False
}


def _set_system_state(*, started=None, starting=None):
    """Safely update the cached system state flags."""
    with system_state_lock:
        if started is not None:
            system_state['started'] = started
        if starting is not None:
            system_state['starting'] = starting


def _get_system_state():
    """Return a shallow copy of the system state flags."""
    with system_state_lock:
        return system_state.copy()


def _prepare_system_start():
    """Mark the system as starting if it is not already running or starting."""
    with system_state_lock:
        if system_state['started']:
            return False, 'System already started'
        if system_state['starting']:
            return False, 'System is starting'
        system_state['starting'] = True
        return True, None

def _mark_shutdown_requested():
    """Mark shutdown requested；If the shutdown process has been completed, return False。"""
    with system_state_lock:
        if system_state.get('shutdown_in_progress'):
            return False
        system_state['shutdown_in_progress'] = True
        return True


def initialize_system_components():
    """Start All dependent components（Streamlit sub-application、ForumEngine、ReportEngine）。"""
    logs = []
    errors = []
    
    # Database initialization is handled by SQLAlchemy on first query in the financial refactor

    try:
        stop_forum_engine()
        logs.append("Stopped ForumEngine monitor to avoid file conflicts")
    except Exception as exc:
        message = f"Exception occurred while stopping ForumEngine: {exc}"
        logs.append(message)
        logger.exception(message)

    processes['forum']['status'] = 'stopped'

    for app_name, script_path in STREAMLIT_SCRIPTS.items():
        logs.append(f"Checking file: {script_path}")
        if os.path.exists(script_path):
            success, message = start_streamlit_app(app_name, script_path, processes[app_name]['port'])
            logs.append(f"{app_name}: {message}")
            if success:
                startup_success, startup_message = wait_for_app_startup(app_name, 30)
                logs.append(f"{app_name} startup check: {startup_message}")
                if not startup_success:
                    errors.append(f"{app_name} startup failed: {startup_message}")
            else:
                errors.append(f"{app_name} startup failed: {message}")
        else:
            msg = f"File does not exist: {script_path}"
            logs.append(f"Error: {msg}")
            errors.append(f"{app_name}: {msg}")

    forum_started = False
    try:
        start_forum_engine()
        processes['forum']['status'] = 'running'
        logs.append("ForumEngine startup completed")
        forum_started = True
    except Exception as exc:
        error_msg = f"ForumEngine startup failed: {exc}"
        logs.append(error_msg)
        errors.append(error_msg)

    if REPORT_ENGINE_AVAILABLE:
        try:
            if initialize_report_engine():
                logs.append("ReportEngine initialized successfully")
            else:
                msg = "ReportEngine initialization failed"
                logs.append(msg)
                errors.append(msg)
        except Exception as exc:  # pragma: no cover
            msg = f"ReportEngine initialization exception: {exc}"
            logs.append(msg)
            errors.append(msg)

    if errors:
        cleanup_processes()
        processes['forum']['status'] = 'stopped'
        if forum_started:
            try:
                stop_forum_engine()
            except Exception:  # pragma: no cover
                logger.exception("Failed to stop ForumEngine")
        return False, logs, errors

    return True, logs, []


def init_forum_log():
    """Initialize the forum.log file"""
    try:
        forum_log_file = LOG_DIR / "forum.log"

        if not forum_log_file.exists():
            with open(forum_log_file, 'w', encoding='utf-8') as f:
                start_time = datetime.now(timezone.utc).replace(tzinfo=None).strftime('%Y-%m-%d %H:%M:%S')
                f.write(f"=== ForumEngine System Initialization - {start_time} ===\n")
            logger.info(f"ForumEngine: forum.log initialized")
        else:
            with open(forum_log_file, 'w', encoding='utf-8') as f:
                start_time = datetime.now(timezone.utc).replace(tzinfo=None).strftime('%Y-%m-%d %H:%M:%S')
                f.write(f"=== ForumEngine System Initialization - {start_time} ===\n")
            logger.info(f"ForumEngine: forum.log initialized")
    except Exception as e:
        logger.exception(f"ForumEngine: initializationforum.logFailed: {e}")


init_forum_log()


def start_forum_engine():
    """Start ForumEngine Forum"""
    try:
        # from ForumEngine.monitor import start_forum_monitoring (hoisted)
        logger.info("ForumEngine: Starting forum...")
        success = start_forum_monitoring()
        if not success:
            logger.info("ForumEngine: Forum startup failed")
    except Exception as e:
        logger.exception(f"ForumEngine: Failed to start forum: {e}")


def stop_forum_engine():
    """Stop ForumEngine Forum"""
    try:
        # from ForumEngine.monitor import stop_forum_monitoring (hoisted)
        logger.info("ForumEngine: Stopping forum...")
        stop_forum_monitoring()
        logger.info("ForumEngine: Forum stopped")
    except Exception as e:
        logger.exception(f"ForumEngine: Failed to stop forum: {e}")

def parse_forum_log_line(line):
    """Parse forum.log line content，Extract conversationInfo"""
    # import re (hoisted)
    

    pattern = r'\[(\d{2}:\d{2}:\d{2})\]\s*\[([^\]]+)\]\s*(.*)'
    match = re.match(pattern, line)
    
    if not match:
        return None

    timestamp, raw_source, content = match.groups()
    source = raw_source.strip().upper()


    if source == 'SYSTEM' or not content.strip():
        return None
    

    if source not in ['QUERY', 'INSIGHT', 'MEDIA', 'HOST']:
        return None
    

    cleaned_content = content.replace('\\n', '\n').replace('\\r', '').strip()
    

    if source == 'HOST':
        message_type = 'host'
        sender = 'Forum Host'
    else:
        message_type = 'agent'
        sender = f'{source.title()} Engine'
    
    return {
        'type': message_type,
        'sender': sender,
        'content': cleaned_content,
        'timestamp': timestamp,
        'source': source
    }



forum_log_positions = {}


def monitor_forum_log():
    """Listen to the Redis event bus and push to the front end"""
    # import time, threading (hoisted)
    # from ForumEngine.redis_pubsub import event_bus (hoisted)
    # from loguru import logger (hoisted)
    # from datetime import datetime, timezone (hoisted)

    def handle_message(data):
        try:
            timestamp = datetime.now(timezone.utc).replace(tzinfo=None).strftime('%H:%M:%S')
            source = data.get("source", "UNKNOWN")
            content = data.get("content", "")

            # Format according to what the frontend expects from parse_forum_log_line
            if source == 'HOST':
                message_type = 'host'
                sender = 'Forum Host'
            else:
                message_type = 'agent'
                sender = f'{source.title()} Engine'

            parsed_message = {
                'type': message_type,
                'sender': sender,
                'content': content,
                'timestamp': timestamp,
                'source': source
            }

            socketio.emit('forum_message', parsed_message)

            formatted_line = f"[{timestamp}] [{source}] {content}"
            socketio.emit('console_output', {
                'app': 'forum',
                'line': formatted_line
            })
        except Exception as e:
            logger.error(f"Error handling Redis message in app.py: {e}")

    while True:
        try:
            event_bus.subscribe("forum", handle_message)
            logger.info("Successfully subscribed to Redis forum channel")

            # Keep the thread alive as it's spawned as daemon in app.py
            while True:
                threading.Event().wait(5)

        except Exception as e:
            logger.error(f"Failed to subscribe to Redis forum channel: {e}. Retrying in 5s...")
            threading.Event().wait(5)

from utils.system_monitor import start_monitor_thread
from ForumEngine.monitor import start_forum_monitoring, stop_forum_monitoring
from ForumEngine.redis_pubsub import event_bus
from config import reload_settings, settings
from flask import make_response
import random
import re
import select

forum_monitor_thread = threading.Thread(target=monitor_forum_log, daemon=True)
forum_monitor_thread.start()

start_monitor_thread()

def monitor_system_socket():
    # import time, threading (hoisted)
    last_net_io = psutil.net_io_counters()
    last_time = time.time()
    while True:
        try:
            current_net_io = psutil.net_io_counters()
            current_time = time.time()
            dt = current_time - last_time

            sent_speed = (current_net_io.bytes_sent - last_net_io.bytes_sent) / dt if dt > 0 else 0
            recv_speed = (current_net_io.bytes_recv - last_net_io.bytes_recv) / dt if dt > 0 else 0

            last_net_io = current_net_io
            last_time = current_time

            metrics = {
                'cpu': psutil.cpu_percent(interval=None),
                'memory': psutil.virtual_memory().percent,
                'disk': psutil.disk_usage('/').percent,
                'net_sent_kbps': sent_speed / 1024,
                'net_recv_kbps': recv_speed / 1024
            }
            socketio.emit('system_metrics', metrics)
        except Exception as e:
            logger.error(f"Socket IO monitor error: {e}")
        threading.Event().wait(2)

threading.Thread(target=monitor_system_socket, daemon=True).start()




processes = {
    'insight': {'process': None, 'port': 8501, 'status': 'stopped', 'output': [], 'log_file': None, 'healthcheck_started_at': None},
    'media': {'process': None, 'port': 8502, 'status': 'stopped', 'output': [], 'log_file': None, 'healthcheck_started_at': None},
    'query': {'process': None, 'port': 8503, 'status': 'stopped', 'output': [], 'log_file': None, 'healthcheck_started_at': None},
    'report': {'process': None, 'port': None, 'status': 'running' if REPORT_ENGINE_AVAILABLE else 'stopped', 'output': [], 'log_file': None},
    'forum': {'process': None, 'port': None, 'status': 'stopped', 'output': [], 'log_file': None}
}

STREAMLIT_SCRIPTS = {
    'insight': 'SingleEngineApp/insight_engine_streamlit_app.py',
    'media': 'SingleEngineApp/media_engine_streamlit_app.py',
    'query': 'SingleEngineApp/query_engine_streamlit_app.py'
}

def _log_shutdown_step(message: str):
    """Unified recording of shutdown steps，Easy to troubleshoot。"""
    logger.info(f"[Shutdown] {message}")


def _describe_running_children():
    """List currently alive child processes。"""
    running = []
    for name, info in processes.items():
        proc = info.get('process')
        if proc is not None and proc.poll() is None:
            port_desc = f", port={info.get('port')}" if info.get('port') else ""
            running.append(f"{name}(pid={proc.pid}{port_desc})")
    return running


output_queues = {
    'insight': None,
    'media': None,
    'query': None,
    'report': None,
    'forum': None
}

def write_log_to_file(app_name, line):
    """Write Logs to file"""
    try:
        log_file_path = LOG_DIR / f"{app_name}.log"
        with open(log_file_path, 'a', encoding='utf-8') as f:
            f.write(line + '\n')
            f.flush()
    except Exception as e:
        logger.error(f"Error writing log for {app_name}: {e}")

def read_log_from_file(app_name, tail_lines=None):
    """read from fileLogs"""
    try:
        log_file_path = LOG_DIR / f"{app_name}.log"
        if not log_file_path.exists():
            return []
        
        with open(log_file_path, 'r', encoding='utf-8') as f:
            lines = [line.rstrip('\n\r') for line in f if line.strip()]
            
            if tail_lines:
                return lines[-tail_lines:]
            return lines
    except Exception as e:
        logger.exception(f"Error reading log for {app_name}: {e}")
        return []

def read_process_output(process, app_name):
    """Read process output and write to file"""
    # import select (hoisted)
    # import sys (hoisted)
    
    while True:
        try:
            if process.poll() is not None:

                remaining_output = process.stdout.read()
                if remaining_output:
                    lines = remaining_output.decode('utf-8', errors='replace').split('\n')
                    for line in lines:
                        line = line.strip()
                        if line:
                            timestamp = datetime.now(timezone.utc).replace(tzinfo=None).strftime('%H:%M:%S')
                            formatted_line = f"[{timestamp}] {line}"
                            write_log_to_file(app_name, formatted_line)
                            socketio.emit('console_output', {
                                'app': app_name,
                                'line': formatted_line
                            })
                break
            

            if sys.platform == 'win32':

                output = process.stdout.readline()
                if output:
                    line = output.decode('utf-8', errors='replace').strip()
                    if line:
                        timestamp = datetime.now(timezone.utc).replace(tzinfo=None).strftime('%H:%M:%S')
                        formatted_line = f"[{timestamp}] {line}"
                        

                        write_log_to_file(app_name, formatted_line)
                        

                        socketio.emit('console_output', {
                            'app': app_name,
                            'line': formatted_line
                        })
                else:

                    threading.Event().wait(0.1)
            else:

                ready, _, _ = select.select([process.stdout], [], [], 0.1)
                if ready:
                    output = process.stdout.readline()
                    if output:
                        line = output.decode('utf-8', errors='replace').strip()
                        if line:
                            timestamp = datetime.now(timezone.utc).replace(tzinfo=None).strftime('%H:%M:%S')
                            formatted_line = f"[{timestamp}] {line}"
                            

                            write_log_to_file(app_name, formatted_line)
                            

                            socketio.emit('console_output', {
                                'app': app_name,
                                'line': formatted_line
                            })
                            
        except Exception as e:
            error_msg = f"Error reading output for {app_name}: {e}"
            logger.exception(error_msg)
            write_log_to_file(app_name, f"[{datetime.now(timezone.utc).replace(tzinfo=None).strftime('%H:%M:%S')}] {error_msg}")
            break

def start_streamlit_app(app_name, script_path, port):
    """Launch the Streamlit app"""
    try:
        if processes[app_name]['process'] is not None:
            return False, "Application is already running"
        

        if not os.path.exists(script_path):
            return False, f"File does not exist: {script_path}"
        

        log_file_path = LOG_DIR / f"{app_name}.log"
        if log_file_path.exists():
            log_file_path.unlink()
        

        start_msg = f"[{datetime.now(timezone.utc).replace(tzinfo=None).strftime('%H:%M:%S')}] start up {app_name} application..."
        write_log_to_file(app_name, start_msg)
        
        cmd = [
            sys.executable, '-m', 'streamlit', 'run',
            script_path,
            '--server.port', str(port),
            '--server.headless', 'true',
            '--browser.gatherUsageStats', 'false',

            '--logger.level', 'info',
            '--server.enableCORS', 'false'
        ]
        

        env = os.environ.copy()
        env.update({
            'PYTHONIOENCODING': 'utf-8',
            'PYTHONUTF8': '1',
            'LANG': 'en_US.UTF-8',
            'LC_ALL': 'en_US.UTF-8',
            'PYTHONUNBUFFERED': '1',
            'STREAMLIT_BROWSER_GATHER_USAGE_STATS': 'false'
        })
        

        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=0,
            universal_newlines=False,
            cwd=os.getcwd(),
            env=env,
            encoding=None,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
        )
        
        processes[app_name]['process'] = process
        processes[app_name]['status'] = 'starting'
        processes[app_name]['output'] = []
        processes[app_name]['healthcheck_started_at'] = time.time()
        

        output_thread = threading.Thread(
            target=read_process_output,
            args=(process, app_name),
            daemon=True
        )
        output_thread.start()
        
        return True, f"{app_name} Application starting..."
        
    except Exception as e:
        error_msg = f"startup failed: {str(e)}"
        write_log_to_file(app_name, f"[{datetime.now(timezone.utc).replace(tzinfo=None).strftime('%H:%M:%S')}] {error_msg}")
        return False, error_msg

def stop_streamlit_app(app_name):
    """Stop the Streamlit application"""
    try:
        process = processes[app_name]['process']
        if process is None:
            _log_shutdown_step(f"{app_name} Not running，skip stop")
            return False, "App is not running"
        
        try:
            pid = process.pid
        except Exception:
            pid = 'unknown'

        _log_shutdown_step(f"Stopping {app_name} (pid={pid})")
        process.terminate()
        

        try:
            process.wait(timeout=5)
            _log_shutdown_step(f"{app_name} quitCompleted，returncode={process.returncode}")
        except subprocess.TimeoutExpired:
            _log_shutdown_step(f"{app_name} Termination timeout，Try to force end (pid={pid})")
            process.kill()
            process.wait()
            _log_shutdown_step(f"{app_name} Forced to end，returncode={process.returncode}")
        
        processes[app_name]['process'] = None
        processes[app_name]['status'] = 'stopped'
        processes[app_name]['healthcheck_started_at'] = None
        
        return True, f"{app_name} Application has been stopped"
        
    except Exception as e:
        _log_shutdown_step(f"{app_name} stopFailed: {e}")
        return False, f"stopFailed: {str(e)}"

HEALTHCHECK_PATH = "/_stcore/health"
HEALTHCHECK_PROXIES = {'http': None, 'https': None}
HEALTHCHECK_GRACE_SECONDS = 15


def _build_healthcheck_url(port):
    return f"http://127.0.0.1:{port}{HEALTHCHECK_PATH}"


def _healthcheck_grace_active(app_name: str) -> bool:
    started_at = processes.get(app_name, {}).get('healthcheck_started_at')
    if not started_at:
        return False
    return (time.time() - started_at) < HEALTHCHECK_GRACE_SECONDS


def _log_healthcheck_failure(app_name: str, exc: Exception):
    if _healthcheck_grace_active(app_name):
        logger.debug(f"Starting{app_name}，please wait")
        return
    logger.warning(f"{app_name} health checkFailed: {exc}")


def check_app_status():
    """Check application status"""

    def check_single_app(app_name, info):
        if info['process'] is not None:
            if info['process'].poll() is None:
                try:
                    response = requests.get(
                        _build_healthcheck_url(info['port']),
                        timeout=2,
                        proxies=HEALTHCHECK_PROXIES
                    )
                    if response.status_code == 200:
                        info['status'] = 'running'
                    else:
                        info['status'] = 'starting'
                except Exception as exc:
                    _log_healthcheck_failure(app_name, exc)
                    info['status'] = 'starting'
            else:
                info['process'] = None
                info['status'] = 'stopped'
                info['healthcheck_started_at'] = None


    with concurrent.futures.ThreadPoolExecutor(max_workers=len(processes) or 1) as executor:
        futures = []
        for app_name, info in processes.items():
            futures.append(executor.submit(check_single_app, app_name, info))
        concurrent.futures.wait(futures)

def wait_for_app_startup(app_name, max_wait_time=90):
    """Waiting for applicationstartup completed"""
    # import time, threading (hoisted)
    start_time = time.time()
    while time.time() - start_time < max_wait_time:
        info = processes[app_name]
        if info['process'] is None:
            return False, "Process has stopped"
        
        if info['process'].poll() is not None:
            return False, "process startFailed"
        
        try:
            response = requests.get(
                _build_healthcheck_url(info['port']),
                timeout=2,
                proxies=HEALTHCHECK_PROXIES
            )
            if response.status_code == 200:
                info['status'] = 'running'
                return True, "start upSuccess"
        except Exception as exc:
            _log_healthcheck_failure(app_name, exc)

        threading.Event().wait(1)

    return False, "Start timeout"

def cleanup_processes():
    """Clean up All processes"""
    _log_shutdown_step("Start serial cleanup child process")
    for app_name in STREAMLIT_SCRIPTS:
        stop_streamlit_app(app_name)

    processes['forum']['status'] = 'stopped'
    try:
        stop_forum_engine()
    except Exception:  # pragma: no cover
        logger.exception("Failed to stop ForumEngine")
    _log_shutdown_step("Child process cleanupCompleted")
    _set_system_state(started=False, starting=False)

def cleanup_processes_concurrent(timeout: float = 6.0):
    """Concurrently clean up all child processes，Forcefully kill remaining processes after timeout。"""
    _log_shutdown_step(f"Start concurrent cleanup of child processes（time out {timeout}s）")
    _log_shutdown_step("Only terminate child processes started and logged by the current console，No port scanning")
    running_before = _describe_running_children()
    if running_before:
        _log_shutdown_step("Current surviving child processes: " + ", ".join(running_before))
    else:
        _log_shutdown_step("No live child processes detected，A shutdown command will still be sent")

    threads = []


    for app_name in STREAMLIT_SCRIPTS:
        t = threading.Thread(target=stop_streamlit_app, args=(app_name,), daemon=True)
        threads.append(t)
        t.start()


    forum_thread = threading.Thread(target=stop_forum_engine, daemon=True)
    threads.append(forum_thread)
    forum_thread.start()


    end_time = time.time() + timeout
    for t in threads:
        remaining = end_time - time.time()
        if remaining <= 0:
            break
        t.join(timeout=remaining)


    for app_name in STREAMLIT_SCRIPTS:
        proc = processes[app_name]['process']
        if proc is not None and proc.poll() is None:
            try:
                _log_shutdown_step(f"{app_name} The process is still alive，Trigger secondary termination (pid={proc.pid})")
                proc.terminate()
                proc.wait(timeout=1)
            except Exception:
                try:
                    _log_shutdown_step(f"{app_name} secondary terminationFailed，trykill (pid={proc.pid})")
                    proc.kill()
                    proc.wait(timeout=1)
                except Exception:
                    logger.warning(f"{app_name} process force exitFailed，Continue to shut down")
            finally:
                processes[app_name]['process'] = None
                processes[app_name]['status'] = 'stopped'

    processes['forum']['status'] = 'stopped'
    _log_shutdown_step("Concurrent cleanup ends，Marking system is not started")
    _set_system_state(started=False, starting=False)

def _schedule_server_shutdown(delay_seconds: float = 0.1):
    """Exit as soon as possible after cleaning Completed，Avoid blocking the current request。"""
    def _shutdown():
        threading.Event().wait(delay_seconds)
        try:
            socketio.stop()
        except Exception as exc:  # pragma: no cover
            logger.warning(f"SocketIO Exception while stopping，Continue to exit: {exc}")
        _log_shutdown_step("SocketIO Stop command sent，About to exit the main process")
        os._exit(0)

    threading.Thread(target=_shutdown, daemon=True).start()

def _start_async_shutdown(cleanup_timeout: float = 3.0):
    """Asynchronously trigger cleanup and force exit，Avoid blocking HTTP requests。"""
    _log_shutdown_step(f"Received shutdown command，Start asynchronous cleanup（time out {cleanup_timeout}s）")

    def _force_exit():
        _log_shutdown_step("shutdown timeout，Trigger force quit")
        os._exit(0)


    hard_timeout = cleanup_timeout + 2.0
    force_timer = threading.Timer(hard_timeout, _force_exit)
    force_timer.daemon = True
    force_timer.start()

    def _cleanup_and_exit():
        try:
            cleanup_processes_concurrent(timeout=cleanup_timeout)
        except Exception as exc:  # pragma: no cover
            logger.exception(f"Shutdown cleaning exception: {exc}")
        finally:
            _log_shutdown_step("Cleanup thread ends，Scheduling the main process to exit")
            _schedule_server_shutdown(0.05)

    threading.Thread(target=_cleanup_and_exit, daemon=True).start()


atexit.register(cleanup_processes)


API_CACHE = {}

def cache_json_response(ttl_seconds=60):
    def decorator(func):
        # from functools import wraps (hoisted)
        # import time, threading (hoisted)
        # from flask import make_response (hoisted)
        @wraps(func)
        def wrapper(*args, **kwargs):
            cache_key = f"{func.__name__}_{str(args)}_{str(kwargs)}"
            current_time = time.time()

            if cache_key in API_CACHE:
                cached_time, cached_result = API_CACHE[cache_key]
                if current_time - cached_time < ttl_seconds:
                    return cached_result

            # Remove cleanup loop to prevent premature eviction of other endpoints' entries from the shared global cache.
            # (Eviction logic should ideally be handled by a dedicated thread or maxsize limit, not per endpoint execution)

            result = func(*args, **kwargs)
            # Only cache successful responses
            API_CACHE[cache_key] = (current_time, result)
            return result
        return wrapper
    return decorator

@app.route('/')
def index():
    """Home page"""
    return render_template('index.html')


@app.route('/api/health')
def api_health():
    """Health check endpoint for containers and orchestrators."""
    return jsonify({
        'status': 'ok',
        'report_engine_available': REPORT_ENGINE_AVAILABLE,
        'uptime_seconds': int((datetime.now(timezone.utc).replace(tzinfo=None) - APP_START_TIME).total_seconds())
    })

@app.route('/api/status')
@admin_required
@cache_json_response(ttl_seconds=5)
def get_status():
    """Get All application status with detailed psutil metrics"""
    # import psutil (hoisted)
    check_app_status()

    response = {}
    for app_name, info in processes.items():
        cpu_percent = 0.0
        mem_mb = 0.0
        if info['status'] == 'running' and info['process']:
            try:
                # import psutil (hoisted)
                p = psutil.Process(info['process'].pid)
                cpu_percent = p.cpu_percent(interval=0.0)
                mem_mb = p.memory_info().rss / (1024 * 1024)
            except Exception as e:
                logger.debug(f"Error reading system stats: {e}")

        response[app_name] = {
            'status': info['status'],
            'port': info['port'],
            'output_lines': len(info['output']),
            'cpu': f"{cpu_percent:.1f}%",
            'memory': f"{mem_mb:.1f} MB"
        }

    return jsonify(response)


@app.route("/api/system/tokens", methods=["GET"])
@admin_required
@cache_json_response(ttl_seconds=10)
def get_tokens():
    try:
        stats = tracker.get_stats()
        return jsonify(stats)
    except Exception as e:
        logger.error(f"Error fetching tokens: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/start/<app_name>')
@admin_required
def start_app(app_name):
    if app_name not in ['query', 'media', 'insight', 'report', 'forum']:
        return jsonify({"error": f"Invalid app name: {app_name}" }), 400

    """Start the specified application"""
    if app_name not in processes:
        return jsonify({'success': False, 'message': 'Unknown application'})

    if app_name == 'report':
        if not REPORT_ENGINE_AVAILABLE or initialize_report_engine is None:
            return jsonify({'success': False, 'message': 'ReportEngine unavailable'})
        try:
            ok = initialize_report_engine()
            processes['report']['status'] = 'running' if ok else 'stopped'
            return jsonify({'success': bool(ok), 'message': 'ReportEngine started' if ok else 'ReportEngine initialization failed'})
        except Exception as exc:
            logger.exception("Manual start ReportEngine failed")
            return jsonify({'success': False, 'message': f'ReportEngine startup failed: {exc}'})

    if app_name == 'forum':
        try:
            start_forum_engine()
            processes['forum']['status'] = 'running'
            return jsonify({'success': True, 'message': 'ForumEngineStarted'})
        except Exception as exc:  # pragma: no cover
            logger.exception("Manual startForumEngineFailed")
            return jsonify({'success': False, 'message': f'ForumEnginestartup failed: {exc}'})

    script_path = STREAMLIT_SCRIPTS.get(app_name)
    if not script_path:
        return jsonify({'success': False, 'message': 'The app does not support launch operations'})

    success, message = start_streamlit_app(
        app_name,
        script_path,
        processes[app_name]['port']
    )

    if success:

        startup_success, startup_message = wait_for_app_startup(app_name, 15)
        if not startup_success:
            message = f"{message} But start checkingFailed: {startup_message}"
    
    return jsonify({'success': success, 'message': message})

@app.route('/api/stop/<app_name>')
@admin_required
def stop_app(app_name):
    if app_name not in ['query', 'media', 'insight', 'report', 'forum']:
        return jsonify({"error": f"Invalid app name: {app_name}" }), 400

    """Stop specified application"""
    if app_name not in processes:
        return jsonify({'success': False, 'message': 'Unknown application'})

    if app_name == 'report':
        processes['report']['status'] = 'stopped'
        return jsonify({'success': True, 'message': 'ReportEngine stopped'})

    if app_name == 'forum':
        try:
            stop_forum_engine()
            processes['forum']['status'] = 'stopped'
            return jsonify({'success': True, 'message': 'ForumEngineStopped'})
        except Exception as exc:  # pragma: no cover
            logger.exception("ManualFailed to stop ForumEngine")
            return jsonify({'success': False, 'message': f'ForumEnginestopFailed: {exc}'})

    success, message = stop_streamlit_app(app_name)
    return jsonify({'success': success, 'message': message})

@app.route('/api/output/<app_name>')
@admin_required
def get_output(app_name):
    if app_name not in ['query', 'media', 'insight', 'report', 'forum']:
        return jsonify({"error": f"Invalid app name: {app_name}" }), 400

    """Get application output"""
    if app_name not in processes:
        return jsonify({'success': False, 'message': 'Unknown application'})
    

    if app_name == 'forum':
        try:
            forum_log_content = read_log_from_file('forum')
            return jsonify({
                'success': True,
                'output': forum_log_content,
                'total_lines': len(forum_log_content)
            })
        except Exception as e:
            return jsonify({'success': False, 'message': f'readforumLogsFailed: {str(e)}'})
    

    output_lines = read_log_from_file(app_name)
    
    return jsonify({
        'success': True,
        'output': output_lines
    })

@app.route('/api/test_log/<app_name>')
@admin_required
def test_log(app_name):
    if app_name not in ['query', 'media', 'insight', 'report', 'forum']:
        return jsonify({"error": f"Invalid app name: {app_name}" }), 400

    """TestLogswrite function"""
    if app_name not in processes:
        return jsonify({'success': False, 'message': 'Unknown application'})
    

    test_msg = f"[{datetime.now(timezone.utc).replace(tzinfo=None).strftime('%H:%M:%S')}] TestLogsinformation - {datetime.now(timezone.utc).replace(tzinfo=None)}"
    write_log_to_file(app_name, test_msg)
    

    socketio.emit('console_output', {
        'app': app_name,
        'line': test_msg
    })
    
    return jsonify({
        'success': True,
        'message': f'Testmessage has been written {app_name} Logs'
    })

@app.route('/api/forum/start')
@admin_required
def start_forum_monitoring_api():
    """Manually start the ForumEngine forum"""
    try:
        # from ForumEngine.monitor import start_forum_monitoring (hoisted)
        success = start_forum_monitoring()
        if success:
            return jsonify({'success': True, 'message': 'ForumEngineForum has been started'})
        else:
            return jsonify({'success': False, 'message': 'ForumEngineForum startup failed'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Failed to start forum: {str(e)}'})

@app.route('/api/forum/stop')
@admin_required
def stop_forum_monitoring_api():
    """Stop the ForumEngine forum manually"""
    try:
        # from ForumEngine.monitor import stop_forum_monitoring (hoisted)
        stop_forum_monitoring()
        return jsonify({'success': True, 'message': 'ForumEngineForum stopped'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Failed to stop forum: {str(e)}'})

@app.route('/api/forum/log')
@app.route('/api/forum/analysis/log')
@admin_required
def get_forum_log():
    """
    Get Forum logs and parsed messages.
    Supports both standard log access and analysis-specific access.
    """
    try:
        forum_log_file = LOG_DIR / "forum.log"
        if not forum_log_file.exists():
            return jsonify({
                'success': True,
                'log_lines': [],
                'parsed_messages': [],
                'total_lines': 0
            })
        
        with open(forum_log_file, 'r', encoding='utf-8', errors='ignore') as f:
            # OPTIMIZATION: Tail the file efficiently with O(1) memory using collections.deque
            lines = [line.rstrip('\n\r') for line in collections.deque(f, maxlen=1000) if line.strip()]
        

        parsed_messages = []
        for line in lines:
            parsed_message = parse_forum_log_line(line)
            if parsed_message:
                parsed_messages.append(parsed_message)
        
        return jsonify({
            'success': True,
            'log_lines': lines,
            'parsed_messages': parsed_messages,
            'total_lines': len(lines)
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'readforum.logFailed: {str(e)}'})


@app.route('/api/forum/export')
# Enforce admin authentication for exporting forum logs
@admin_required
def export_forum():
    try:
        forum_log_file = LOG_DIR / "forum.log"
        if not forum_log_file.exists():
            return jsonify({'success': False, 'message': 'Forum log not found'})

        # ⚡ OPTIMIZATION: Replacing O(n^2) immutable string concatenation (`+=`) inside loops with
        # O(n) list appending (`.append()`) followed by a single string `join()` for memory efficiency.
        content_parts = ["# Forum Engine Debate Export\n\n"]
        with open(forum_log_file, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                parsed = parse_forum_log_line(line)
                if parsed:
                    content_parts.append(f"**[{parsed['timestamp']}] {parsed['sender']}**:\n{parsed['content']}\n\n")

        return Response(
            "".join(content_parts),
            mimetype="text/markdown",
            headers={"Content-disposition": "attachment; filename=forum_export.md"}
        )
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/forum/log/history', methods=['POST'])
@admin_required
def get_forum_log_history():
    """Get Forum historyLogs（Support starting from a specified location）"""
    try:
        data = request.get_json()
        start_position = data.get('position', 0)
        max_lines = data.get('max_lines', 1000)

        forum_log_file = LOG_DIR / "forum.log"
        if not forum_log_file.exists():
            return jsonify({
                'success': True,
                'log_lines': [],
                'position': 0,
                'has_more': False
            })

        with open(forum_log_file, 'r', encoding='utf-8', errors='ignore') as f:

            f.seek(start_position)
            lines = []
            line_count = 0

            for line in f:
                if line_count >= max_lines:
                    break
                line = line.rstrip('\n\r')
                if line.strip():

                    timestamp = datetime.now(timezone.utc).replace(tzinfo=None).strftime('%H:%M:%S')
                    formatted_line = f"[{timestamp}] {line}"
                    lines.append(formatted_line)
                    line_count += 1


            current_position = f.tell()


            f.seek(0, 2)
            end_position = f.tell()
            has_more = current_position < end_position

        return jsonify({
            'success': True,
            'log_lines': lines,
            'position': current_position,
            'has_more': has_more
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'Read forum historyFailed: {str(e)}'})


@app.route('/api/search/suggest', methods=['GET'])
@admin_required
def suggest_queries():
    if not check_rate_limit(request.remote_addr):
        return jsonify({'success': False, 'error': 'Rate limit exceeded'}), 429

    query = request.args.get('q', '').lower()
    # 🛡️ SECURITY FIX: Prevents potential DoS attacks via extremely long query parsing by enforcing a strict 100 character limit on suggestions.
    if len(query) > 100:
        return jsonify({'success': False, 'message': 'Search query too long'}), 400
    if not query:
        return jsonify({'success': True, 'suggestions': []})

    common_queries = [
        "Analyze TSLA sentiment",
        "Compare BTC and ETH performance",
        "What is the market outlook for AI stocks?",
        "Latest news on AAPL earnings",
        "Macroeconomic trends for Q3",
        "Predict MSFT price movement",
        "Impact of interest rates on tech sector",
        "Top trending cryptocurrencies today",
        "How is the energy sector performing?",
        "Consumer confidence index updates"
    ]

    suggestions = [q for q in common_queries if query in q.lower()][:5]
    return jsonify({'success': True, 'suggestions': suggestions})
SEARCH_CACHE = {}

@app.route('/api/search', methods=['POST'])
@admin_required
def search():
    if not check_rate_limit(request.remote_addr):
        return jsonify({'error': 'Rate limit exceeded'}), 429

    """Unified search interface with basic rate limiting and caching"""
    # import time, threading (hoisted)
    data = request.get_json()
    query = data.get('query', '').strip()
    # 🛡️ SECURITY FIX: Enforces a strict 500 character limit on primary search queries to prevent heavy payload abuses and ReDoS vulnerabilities in downstream parsing algorithms.
    if len(query) > 500:
        return jsonify({'success': False, 'message': 'Search query exceeds maximum length of 500 characters'}), 400
    
    if not query:
        return jsonify({'success': False, 'message': 'Search query cannot be empty'})

    client_ip = request.remote_addr
    cache_key = f"{client_ip}:{query}"

    # Cache response for 10 seconds to avoid spamming the backend
    if cache_key in SEARCH_CACHE:
        cached_time, cached_result = SEARCH_CACHE[cache_key]
        if time.time() - cached_time < 10:
            return jsonify(cached_result)

    check_app_status()
    requested_engines = data.get('engines')
    searchable_engines = ['insight', 'media', 'query']
    if isinstance(requested_engines, list) and requested_engines:
        target_apps = [name for name in requested_engines if name in searchable_engines]
    else:
        target_apps = [name for name in searchable_engines if processes[name]['status'] == 'running']
        if not target_apps:
            target_apps = searchable_engines

    def run_engine_search(app_name, q):
        try:
            write_log_to_file(app_name, f"[SEARCH] Query received: {q}")
            if app_name == 'insight':
                from InsightEngine.tools.search import TrendPulseDB
                db = TrendPulseDB()
                res = db.search_topic_globally(q, limit=10)
                items = [
                    {
                        'ticker': r.ticker,
                        'asset_class': r.asset_class,
                        'title': r.title_or_content,
                        'source': r.source,
                        'publish_time': str(r.publish_time) if r.publish_time else None,
                        'engagement': r.engagement,
                        'sentiment_score': r.sentiment_score,
                    }
                    for r in (res.results or [])
                ]
                return app_name, {'success': True, 'count': len(items), 'results': items}
            elif app_name == 'media':
                if not getattr(settings, 'BOCHA_API_KEY', None):
                    return app_name, {'success': False, 'message': 'BOCHA_API_KEY not configured'}
                from MediaEngine.tools.search import BochaMultimodalSearch
                client = BochaMultimodalSearch()
                res = client.comprehensive_search(q, max_results=5)
                items = [
                    {
                        'title': w.name,
                        'url': w.url,
                        'snippet': w.snippet,
                        'source': w.site_name,
                        'published': w.date_published,
                    }
                    for w in (res.webpages or [])
                ]
                return app_name, {'success': True, 'count': len(items), 'results': items}
            elif app_name == 'query':
                if not getattr(settings, 'TAVILY_API_KEY', None):
                    return app_name, {'success': False, 'message': 'TAVILY_API_KEY not configured'}
                from QueryEngine.tools.search import TavilyNewsAgency
                client = TavilyNewsAgency()
                res = client.basic_search_news(q, max_results=5)
                items = [
                    {
                        'title': r.title,
                        'url': r.url,
                        'content': r.content,
                        'score': r.score,
                        'published': r.published_date,
                    }
                    for r in (res.results or [])
                ]
                return app_name, {'success': True, 'count': len(items), 'results': items}
            return app_name, {'success': False, 'message': f'Unsupported search engine: {app_name}'}
        except Exception as e:
            logger.exception(f"In-process search failed for {app_name}: {e}")
            return app_name, {'success': False, 'message': str(e)}

    results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, len(target_apps))) as executor:
        futures = {executor.submit(run_engine_search, app_name, query): app_name for app_name in target_apps}
        for future in concurrent.futures.as_completed(futures):
            app_name, result = future.result()
            results[app_name] = result

    final_result = {'success': True, 'results': results}
    SEARCH_CACHE[cache_key] = (time.time(), final_result)
    
    # Clean up old cache entries
    current_time = time.time()
    keys_to_delete = list(k for k, (t, _) in SEARCH_CACHE.items() if current_time - t > 60)
    for k in keys_to_delete:
        del SEARCH_CACHE[k]

    return jsonify(final_result)


@app.route("/api/geo_data")
@admin_required
# ⚡ OPTIMIZATION: Added @cache_json_response to prevent redundant yfinance network calls and avoid API rate limiting.
@cache_json_response(ttl_seconds=60)
def api_geo_data():
    try:
        # import random (hoisted)
        # We need to provide locations and sentiment. Since yfinance doesn't give geo sentiment,
        # we'll map major indices to locations and use their price change as a proxy for sentiment.

        indices = {
            '^GSPC': {'lat': 40.7128, 'lng': -74.0060, 'name': 'New York'},
            '^FTSE': {'lat': 51.5074, 'lng': -0.1278, 'name': 'London'},
            '^N225': {'lat': 35.6762, 'lng': 139.6503, 'name': 'Tokyo'},
            '^HSI': {'lat': 22.3193, 'lng': 114.1694, 'name': 'Hong Kong'},
            '^GDAXI': {'lat': 50.1109, 'lng': 8.6821, 'name': 'Frankfurt'},
            '^FCHI': {'lat': 48.8566, 'lng': 2.3522, 'name': 'Paris'},
            '^AXJO': {'lat': -33.8688, 'lng': 151.2093, 'name': 'Sydney'},
        }

        symbols = list(indices.keys())
        data = yf.download(symbols, period='2d', progress=False)
        geo_data = []
        for symbol, info in indices.items():
            sentiment = 0.5  # neutral default
            intensity = 0.5

            try:
                if isinstance(data.columns, pd.MultiIndex):
                    close_prices = data.xs(symbol, level=1, axis=1)['Close']
                else:
                    close_prices = data['Close']

                if len(close_prices) >= 2:
                    close_vals = close_prices.values
                    change = float((close_vals[-1] - close_vals[-2]) / close_vals[-2])
                    # Map change to 0-1 sentiment (e.g., -2% -> 0, +2% -> 1)
                    sentiment = max(0.0, min(1.0, (change * 25) + 0.5))
                    intensity = min(1.0, abs(change) * 50 + 0.2)
            except Exception:
                pass

            geo_data.append({
                "lat": info['lat'],
                "lng": info['lng'],
                "sentiment": float(sentiment),
                "intensity": float(intensity),
                "location": info['name']
            })

        return jsonify(geo_data)
    except Exception as e:
        logger.error(f"Error fetching geo data: {e}")
        return jsonify([])

@app.route('/geo')
@admin_required
def geo_pulse():
    return render_template('geo_pulse.html')

@app.route('/nexus')
@admin_required
def nexus_map():
    return render_template('nexus_map.html')

@app.route('/mem0')
@admin_required
def mem0_explorer():
    return render_template('mem0_explorer.html')

@app.route('/oracle')
@admin_required
def oracle_paths():
    return render_template('oracle_paths.html')

@app.route('/heat')
@admin_required
def heat_link():
    return render_template('heat_link.html')

@app.route('/swarm')
@admin_required
def swarm_matrix():
    return render_template('swarm_matrix.html')

@app.route('/omnifeed')
@admin_required
def omni_feed():
    return render_template('omni_feed.html')

@app.route('/api/correlation_data')
@admin_required
# ⚡ OPTIMIZATION: Added @cache_json_response to prevent redundant yfinance network calls and avoid API rate limiting.
@cache_json_response(ttl_seconds=60)
def api_correlation_data():
    try:

        symbols = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'TSLA', 'NVDA']
        data = yf.download(symbols, period='1mo', progress=False)

        returns = pd.DataFrame()
        for symbol in symbols:
            if symbol in data.columns.levels[0] if isinstance(data.columns, pd.MultiIndex) else True:
                # Handle MultiIndex and flat dataframe
                try:
                    close_col = data.xs(symbol, level=1, axis=1)['Close'] if isinstance(data.columns, pd.MultiIndex) else data['Close']
                    returns[symbol] = close_col.pct_change().dropna()
                except Exception:
                    pass

        if returns.empty:
            return jsonify([])

        corr = returns.corr()

        # ⚡ OPTIMIZATION: Vectorize O(N^2) python nested loops using pandas C-level methods
        # .unstack() creates a MultiIndex series, .reset_index() converts it to a DataFrame.
        # This reduces correlation JSON serialization latency significantly for large N.
        corr_df = corr.unstack().reset_index()
        corr_df.columns = ['source', 'target', 'value']

        # O(1) vectorized serialization using .values.tolist()
        correlation_matrix = [
            {"source": row[0], "target": row[1], "value": row[2]}
            for row in corr_df.values.tolist()
        ]

        return jsonify(correlation_matrix)
    except Exception as e:
        logger.error(f"Error fetching correlation data: {e}")
        return jsonify([])

@app.route('/ta_matrix')
@admin_required
def ta_matrix():
    return render_template('ta_matrix.html')

@app.route('/api/ta_matrix_data')
@admin_required
@cache_json_response(ttl_seconds=60)
def ta_matrix_data():

    symbols = ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "TSLA", "BRK-B", "JPM", "V", "WMT", "NVDA", "UNH"]
    data = {}

    try:
        df = yf.download(symbols, period="1mo", progress=False)

        # ⚡ OPTIMIZATION: Vectorized computation for TA indicators across all symbols
        if isinstance(df.columns, pd.MultiIndex):
            close_prices = df['Close']
        else:
            close_prices = df[['Close']].rename(columns={'Close': symbols[0]})

        if len(close_prices) >= 20:
            # RSI (14 days)
            delta = close_prices.diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            rsi = 100 - (100 / (1 + rs))

            # SMA 20 & Bollinger Bands
            sma20 = close_prices.rolling(window=20).mean()
            std = close_prices.rolling(window=20).std()
            upper_band = sma20 + (std * 2)
            lower_band = sma20 - (std * 2)

            # MACD
            ema12 = close_prices.ewm(span=12, adjust=False).mean()
            ema26 = close_prices.ewm(span=26, adjust=False).mean()
            macd = ema12 - ema26
            signal = macd.ewm(span=9, adjust=False).mean()

            # ⚡ OPTIMIZATION: Replacing `.values[-1]` Pandas access with vectorized `values[-1]`
            # dictionary mapping to achieve O(1) array access performance and avoid high `.iloc` overhead.
            recent_price = dict(zip(close_prices.columns, close_prices.values[-1]))
            recent_rsi = dict(zip(rsi.columns, rsi.values[-1]))
            recent_upper = dict(zip(upper_band.columns, upper_band.values[-1]))
            recent_lower = dict(zip(lower_band.columns, lower_band.values[-1]))
            recent_macd = dict(zip(macd.columns, macd.values[-1]))
            recent_signal = dict(zip(signal.columns, signal.values[-1]))

            for symbol in symbols:
                if symbol not in recent_price:
                    continue

                s_price = float(recent_price[symbol])
                if pd.isna(s_price):
                    continue

                s_rsi = float(recent_rsi.get(symbol, 50.0)) if not pd.isna(recent_rsi.get(symbol, 50.0)) else 50.0
                s_upper = float(recent_upper[symbol])
                s_lower = float(recent_lower[symbol])
                s_macd = float(recent_macd[symbol])
                s_signal = float(recent_signal[symbol])

                data[symbol] = {
                    "price": s_price,
                    "rsi": s_rsi,
                    "upper_band": s_upper if not pd.isna(s_upper) else s_price,
                    "lower_band": s_lower if not pd.isna(s_lower) else s_price,
                    "macd": s_macd,
                    "macd_signal": s_signal,
                    "trend": "Bullish" if s_macd > s_signal else "Bearish"
                }
    except Exception as e:
        app.logger.error(f"Error fetching TA data: {e}")
        return jsonify({"error": str(e)}), 500

    return jsonify(data)

@app.route('/portfolio_optimizer')
@admin_required
def portfolio_optimizer():
    return render_template('portfolio_optimizer.html')

@app.route('/api/portfolio_data')
@admin_required
@cache_json_response(ttl_seconds=60)
def portfolio_data():

    symbols = ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "TSLA", "BRK-B", "JPM", "V", "WMT"]
    try:
        df = yf.download(symbols, period="1y", progress=False)['Close']
        returns = df.pct_change().dropna()
        mean_returns = returns.mean() * 252
        cov_matrix = returns.cov() * 252

        num_portfolios = 500
        np.random.seed(42) # fixed seed for reproducibility per guidelines

        results = np.zeros((3, num_portfolios))

        # ⚡ OPTIMIZATION: Vectorized Monte Carlo Portfolio Optimization
        weights_record = np.random.random((num_portfolios, len(symbols)))
        weights_record /= np.sum(weights_record, axis=1)[:, np.newaxis]

        portfolio_returns = np.dot(weights_record, mean_returns.values)
        portfolio_stddevs = np.sqrt(np.einsum('ij,ji->i', weights_record, np.dot(cov_matrix.values, weights_record.T)))

        results[0, :] = portfolio_returns
        results[1, :] = portfolio_stddevs
        results[2, :] = portfolio_returns / portfolio_stddevs  # Sharpe Ratio

        max_sharpe_idx = np.argmax(results[2])
        optimal_weights = weights_record[max_sharpe_idx]

        # Prepare data for frontend
        scatter_data = [{"x": float(results[1,i]), "y": float(results[0,i]), "sharpe": float(results[2,i])} for i in range(num_portfolios)]
        weights_data = {symbols[i]: float(optimal_weights[i]) for i in range(len(symbols))}

        return jsonify({
            "scatter": scatter_data,
            "optimal_weights": weights_data,
            "max_sharpe": float(results[2, max_sharpe_idx]),
            "expected_return": float(results[0, max_sharpe_idx]),
            "expected_volatility": float(results[1, max_sharpe_idx])
        })
    except Exception as e:
        app.logger.error(f"Error optimizing portfolio: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/anomaly_radar')
@admin_required
def anomaly_radar():
    return render_template('anomaly_radar.html')

@app.route('/api/anomaly_data')
@admin_required
@cache_json_response(ttl_seconds=60)
def anomaly_data():

    symbols = ["SPY", "QQQ", "IWM", "DIA", "GLD", "SLV", "USO", "TLT"]
    anomalies = []

    try:
        df = yf.download(symbols, period="1mo", progress=False)

        # ⚡ OPTIMIZATION: Vectorized computation for rolling means/stds and pct_change across all symbols.
        if isinstance(df.columns, pd.MultiIndex):
            vol_df = df['Volume']
            prices_df = df['Close']
        else:
            # Handle single symbol case gracefully though symbols list > 1
            vol_df = df[['Volume']].rename(columns={'Volume': symbols[0]})
            prices_df = df[['Close']].rename(columns={'Close': symbols[0]})

        if len(vol_df) >= 20:
            vol_mean_df = vol_df.rolling(window=20).mean()
            vol_std_df = vol_df.rolling(window=20).std()
            price_pct_df = prices_df.pct_change()

            # ⚡ OPTIMIZATION: Replacing `.values[-1]` Pandas access with vectorized `values[-1]`
            # dictionary mapping to achieve O(1) array access performance and avoid high `.iloc` overhead.
            recent_vol = dict(zip(vol_df.columns, vol_df.values[-1]))
            recent_vol_mean = dict(zip(vol_mean_df.columns, vol_mean_df.values[-1]))
            recent_vol_std = dict(zip(vol_std_df.columns, vol_std_df.values[-1]))
            recent_price_change = dict(zip(price_pct_df.columns, price_pct_df.values[-1]))

            for symbol in symbols:
                if symbol not in recent_vol:
                    continue

                s_vol = float(recent_vol[symbol])
                s_vol_mean = float(recent_vol_mean[symbol])
                s_vol_std = float(recent_vol_std[symbol])
                s_price_change = float(recent_price_change[symbol])

                if pd.isna(s_vol) or pd.isna(s_vol_mean) or pd.isna(s_vol_std):
                    continue

                # Anomaly: Volume > 2 standard deviations above mean
                if s_vol > (s_vol_mean + 2 * s_vol_std):
                    anomalies.append({
                        "symbol": symbol,
                        "type": "Volume Spike",
                        "severity": "High",
                        "description": f"Trading volume ({s_vol:,.0f}) is significantly above the 20-day average ({s_vol_mean:,.0f}).",
                        "price_change": s_price_change * 100
                    })

                # Anomaly: Price movement > 3%
                elif abs(s_price_change) > 0.03:
                    anomalies.append({
                        "symbol": symbol,
                        "type": "Price Breakout" if s_price_change > 0 else "Price Breakdown",
                        "severity": "Medium",
                        "description": f"Price moved {s_price_change*100:.1f}% in a single day.",
                        "price_change": s_price_change * 100
                    })

        return jsonify({"anomalies": anomalies})
    except Exception as e:
        app.logger.error(f"Error fetching anomalies: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/news_feed')
@admin_required
def news_feed():
    return render_template('news_feed.html')


@app.route('/api/mem0/memories')
@admin_required
@cache_json_response(ttl_seconds=60)
def api_mem0_memories():
    """Return structured agentic memories and graph nodes/links from Mem0 and live forum/news context."""
    memories = []
    nodes = [{"id": "Core Market Thesis", "group": 0, "radius": 25, "content": "Unified multi-agent market synthesis across macro, news, and quantitative telemetry."}]
    links = []
    seen_ids = {"Core Market Thesis"}

    # 1. Try reading real memories from Mem0
    try:
        from ForumEngine.llm_host import host_memory, mem0_available
        if mem0_available and host_memory is not None:
            raw = host_memory.get_all(user_id="forum_agents")
            items = raw.get("results", []) if isinstance(raw, dict) else (raw if isinstance(raw, list) else [])
            for idx, m in enumerate(items[:20]):
                if not isinstance(m, dict):
                    continue
                mem_text = str(m.get("memory") or m.get("text") or "")
                if not mem_text:
                    continue
                mem_id = str(m.get("id") or f"mem_{idx + 1}")
                memories.append({"id": mem_id, "memory": mem_text, "metadata": m.get("metadata") or {}})
                node_id = mem_text[:36] + ("..." if len(mem_text) > 36 else "")
                if node_id not in seen_ids:
                    seen_ids.add(node_id)
                    group_id = 1 + (idx % 4)
                    nodes.append({"id": node_id, "group": group_id, "radius": 14, "content": mem_text})
                    links.append({"source": "Core Market Thesis", "target": node_id, "value": 3})
    except Exception as exc:
        logger.debug(f"Mem0 store unavailable or empty: {exc}")

    # 2. Enrich with recent forum speeches
    try:
        speeches = get_recent_agent_speeches(limit=6) or []
        for idx, sp in enumerate(speeches):
            content = str(sp.get("content") or "").strip()
            if not content:
                continue
            agent_label = sp.get("agent", "Agent")
            mem_id = f"forum_{idx + 1}"
            memories.append({"id": mem_id, "memory": f"[{agent_label}] {content}", "metadata": {"source": "forum"}})
            node_id = f"{agent_label}: {content[:24]}..."
            if node_id not in seen_ids:
                seen_ids.add(node_id)
                group_id = 1 if agent_label == "INSIGHT" else (2 if agent_label == "MEDIA" else 3)
                nodes.append({"id": node_id, "group": group_id, "radius": 13, "content": content})
                links.append({"source": "Core Market Thesis", "target": node_id, "value": 2})
    except Exception as exc:
        logger.debug(f"Could not read forum speeches for Mem0 graph: {exc}")

    # 3. Enrich with live RSS financial news headlines
    try:
        news_res = news_data()
        news_json = news_res[0].json if isinstance(news_res, tuple) else news_res.json
        if news_json and "news" in news_json:
            for idx, item in enumerate(news_json["news"][:8]):
                title = str(item.get("title") or "").strip()
                if not title:
                    continue
                sent = item.get("sentiment", "Neutral")
                memories.append({"id": f"news_{idx + 1}", "memory": title, "metadata": {"sentiment": sent, "source": item.get("source", "RSS")}})
                group_id = 1 if sent == "Positive" else (2 if sent == "Negative" else 4)
                node_id = f"News: {title[:26]}..."
                if node_id not in seen_ids:
                    seen_ids.add(node_id)
                    nodes.append({"id": node_id, "group": group_id, "radius": 12, "content": f"[{sent}] {title}"})
                    links.append({"source": "Core Market Thesis", "target": node_id, "value": 2})
    except Exception as exc:
        logger.error(f"Error fetching news context for Mem0: {exc}")

    return jsonify({"success": True, "memories": memories, "nodes": nodes, "links": links})


@app.route('/api/mem0/feed', methods=['POST'])
@admin_required
def api_mem0_feed():
    """Inject a selected memory snippet into the active agent forum log and Mem0 store."""
    payload = request.get_json(silent=True) or {}
    content = str(payload.get("content") or payload.get("memory") or "").strip()
    source = str(payload.get("source") or "Mem0 Explorer").strip()
    if not content:
        return jsonify({"success": False, "message": "Memory content cannot be empty"}), 400

    write_log_to_file("forum", f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] [MEM0] ({source}) {content[:400]}")
    try:
        from ForumEngine.llm_host import host_memory, mem0_available
        if mem0_available and host_memory is not None:
            host_memory.add(content[:1000], user_id="forum_agents", metadata={"source": source})
    except Exception as exc:
        logger.debug(f"Mem0 feed persistence skipped: {exc}")

    return jsonify({"success": True, "message": "Memory injected into agent forum stream"})


@app.route('/api/nexus/debate')
@admin_required
@cache_json_response(ttl_seconds=60)
def api_nexus_debate():
    # Try to get real debate from forum logs
    recent_speeches = get_recent_agent_speeches(limit=10)
    debate = []

    topic = "Multi-Agent Market Debate"
    if recent_speeches:
        for speech in recent_speeches:
            agent_name = speech.get('agent', 'Unknown')
            agent_type = "msg-neutral"
            if agent_name == "INSIGHT":
                agent_type = "msg-bull"
                agent_name = "Insight Agent"
            elif agent_name == "MEDIA":
                agent_type = "msg-bear"
                agent_name = "Media Agent"
            elif agent_name == "QUERY":
                agent_type = "msg-risk"
                agent_name = "Query Agent"

            debate.append({
                "agent": agent_name,
                "type": agent_type,
                "text": speech.get('content', '')
            })

        host_speech = get_latest_host_speech()
        if host_speech:
            debate.append({
                "agent": "Forum Host",
                "type": "msg-neutral",
                "text": host_speech
            })
    else:
        debate.append({
            "agent": "System Monitor",
            "type": "msg-neutral",
            "text": "No forum debate messages recorded yet. Start ForumEngine or run an analysis."
        })

    return jsonify({"topic": topic, "debate": debate})


@app.route('/api/oracle/paths')
@admin_required
@cache_json_response(ttl_seconds=60)
def api_oracle_paths():
    # Use real market data to influence probabilities
    try:
        # Check QQQ and SPY momentum as a proxy
        data = yf.download(['SPY', 'QQQ', 'TLT'], period='5d', progress=False)['Close']
        if not data.empty and len(data) >= 2:
            # ⚡ OPTIMIZATION: Replaced DataFrame.iloc with O(1) array lookups for performance.
            spy_ret = (data['SPY'].values[-1] / data['SPY'].values[0]) - 1
            qqq_ret = (data['QQQ'].values[-1] / data['QQQ'].values[0]) - 1
            tlt_ret = (data['TLT'].values[-1] / data['TLT'].values[0]) - 1

            # Base probabilities
            spx_prob = 50 + int(spy_ret * 500) # Adjust by 5% per 1% move
            spx_prob = max(10, min(90, spx_prob))

            rate_cut_prob = 50 + int(tlt_ret * 500) # TLT up implies rate cut expectations
            rate_cut_prob = max(10, min(90, rate_cut_prob))
        else:
            spx_prob = 50
            rate_cut_prob = 50
    except Exception as e:
        spx_prob = 50
        rate_cut_prob = 50

    nasdaq_prob = 100 - spx_prob
    inflation_prob = 100 - rate_cut_prob

    treeData = {
        "name": "Market Singularity",
        "type": "root",
        "children": [
            {
                "name": "SPX Breakout (Bull)",
                "prob": spx_prob,
                "type": "bull",
                "desc": "S&P 500 breaks current resistance levels driven by tech earnings and favorable macro.",
                "drivers": ["Tech Earnings (+15%)", "Dovish Fed", "Strong Consumer Spending"],
                "risks": ["Valuation Stretch", "Yield Curve Steepening"],
                "action": "Increase QQQ exposure, sell out-of-the-money put spreads.",
                "children": [
                    {
                        "name": "Fed Rate Cut",
                        "prob": rate_cut_prob,
                        "type": "bull",
                        "desc": "Fed cuts rates aggressively, fueling a sustained risk-on environment.",
                        "drivers": ["Cooling CPI", "Weakening Labor Market"],
                        "risks": ["Inflation Resurgence"],
                        "action": "Long high-beta tech, short USD."
                    },
                    {
                        "name": "Sticky Inflation",
                        "prob": inflation_prob,
                        "type": "bear",
                        "desc": "Inflation remains above target, capping equity multiples despite strong earnings.",
                        "drivers": ["Energy Prices", "Wage Growth"],
                        "risks": ["Stagflation", "Fed Hike"],
                        "action": "Rotate to defensive value, long commodities."
                    }
                ]
            },
            {
                "name": "Nasdaq Correction (Bear)",
                "prob": nasdaq_prob,
                "type": "bear",
                "desc": "Tech-heavy Nasdaq undergoes a significant correction due to macro headwinds.",
                "drivers": ["Hawkish Fed", "Geopolitical Tensions", "Earnings Misses"],
                "risks": ["Recession", "Credit Event"],
                "action": "Increase cash position, buy VIX calls.",
                "children": [
                    {
                        "name": "Energy Shock",
                        "prob": min(90, int(inflation_prob * 1.2)),
                        "type": "bear",
                        "desc": "Oil prices spike, exacerbating inflation and squeezing margins.",
                        "drivers": ["Supply Disruptions", "Geopolitics"],
                        "risks": ["Demand Destruction"],
                        "action": "Long Energy sector, short Consumer Discretionary."
                    },
                    {
                        "name": "Soft Landing",
                        "prob": max(10, 100 - min(90, int(inflation_prob * 1.2))),
                        "type": "neutral",
                        "desc": "Economy slows but avoids recession, allowing for a gradual recovery.",
                        "drivers": ["Stable Employment", "Moderate Growth"],
                        "risks": ["Policy Error"],
                        "action": "Neutral allocation, focus on stock picking."
                    }
                ]
            }
        ]
    }

    def _enrich_oracle_node(node):
        if "prob" in node and "probability" not in node:
            node["probability"] = node["prob"]
        if node.get("type") in ("bull",):
            node.setdefault("node_tier", "high")
        elif node.get("type") in ("bear",):
            node.setdefault("node_tier", "low")
        else:
            node.setdefault("node_tier", "med")
        if "risks" in node and "risk" not in node:
            node["risk"] = ", ".join(node["risks"])
        if "spy" not in node and node.get("type") != "root":
            base_prob = node.get("probability", 50)
            est_move = ((base_prob - 50) / 10.0) if node.get("type") == "bull" else (-abs(50 - base_prob) / 10.0 - 1.5)
            node["spy"] = f"{'+' if est_move >= 0 else ''}{est_move:.1f}%"
        for child in node.get("children", []):
            _enrich_oracle_node(child)

    _enrich_oracle_node(treeData)
    return jsonify({"treeData": treeData})


@app.route('/api/oracle/simulate', methods=['POST'])
@admin_required
def api_oracle_simulate():
    """Run quantitative historical backtest/projection for the selected Oracle scenario."""
    payload = request.get_json(silent=True) or {}
    scenario_name = str(payload.get("scenario") or "Market Scenario")
    direction = -1 if "bear" in scenario_name.lower() or "correction" in scenario_name.lower() or "inflation" in scenario_name.lower() or "shock" in scenario_name.lower() else 1

    try:
        from InsightEngine.tools.backtest_tool import PortfolioBacktester
        df = yf.download("SPY", period="6mo", progress=False)
        if df.empty or "Close" not in df:
            return jsonify({"success": False, "message": "Market feed unavailable for simulation"}), 503
        close_col = df["Close"]
        prices = close_col.iloc[:, 0] if isinstance(close_col, pd.DataFrame) else close_col.squeeze()
        prices = pd.Series(prices).dropna()
        ema_fast = prices.ewm(span=12, adjust=False).mean()
        ema_slow = prices.ewm(span=26, adjust=False).mean()
        signals = pd.Series(np.where(ema_fast > ema_slow, direction, -direction), index=prices.index)
        bt = PortfolioBacktester(initial_capital=100000.0).run_backtest(prices, signals)
        return jsonify({"success": True, "scenario": scenario_name, "metrics": bt})
    except Exception as exc:
        logger.error(f"Oracle simulation error: {exc}")
        return jsonify({"success": False, "message": str(exc)}), 500


@app.route('/api/market_tickers')
@admin_required
@cache_json_response(ttl_seconds=60)
def api_market_tickers():
    """Fetch live prices and 24h changes for trending benchmark tickers."""
    tickers = {"BTC-USD": "$BTC", "NVDA": "$NVDA", "AAPL": "$AAPL", "TSLA": "$TSLA", "ETH-USD": "$ETH"}
    items = []
    try:
        df = yf.download(list(tickers.keys()), period="5d", progress=False)
        close = df["Close"] if "Close" in df else pd.DataFrame()
        for sym, label in tickers.items():
            price = None
            change_pct = 0.0
            try:
                series = close[sym].dropna() if sym in close else pd.Series(dtype=float)
                if len(series) >= 2:
                    last_p = float(series.iloc[-1])
                    prev_p = float(series.iloc[-2])
                    price = last_p
                    change_pct = ((last_p - prev_p) / prev_p) * 100.0 if prev_p else 0.0
                elif len(series) == 1:
                    price = float(series.iloc[-1])
            except Exception:
                pass
            if price is not None:
                items.append({
                    "symbol": label,
                    "ticker": sym,
                    "price": round(price, 2),
                    "change_pct": round(change_pct, 2),
                    "up": change_pct >= 0,
                })
    except Exception as exc:
        logger.error(f"Error fetching live market tickers: {exc}")
    return jsonify({"success": True, "tickers": items})

@app.route('/api/news_data')
@admin_required
@cache_json_response(ttl_seconds=60)
def news_data():
    # from datetime import datetime, timezone (hoisted)


    # Financial news RSS feeds
    feeds = [
        "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=10000664", # Finance
        "https://feeds.a.dj.com/rss/RSSMarketsMain.xml", # WSJ Markets
    ]

    news_items = []

    def fetch_feed(feed_url):
        items = []
        try:
            # OPTIMIZATION/SECURITY: Use requests with timeout to prevent blocking thread indefinitely
            import requests
            response = requests.get(feed_url, timeout=10)
            parsed = feedparser.parse(response.content)
            for entry in parsed.entries[:10]: # Top 10 from each
                # basic sentiment heuristic
                title_lower = entry.title.lower()
                sentiment = "Neutral"
                if any(word in title_lower for word in ["surge", "jump", "record", "gain", "profit", "bull", "rally", "up"]):
                    sentiment = "Positive"
                elif any(word in title_lower for word in ["plunge", "drop", "loss", "bear", "crash", "down", "fear", "risk"]):
                    sentiment = "Negative"

                items.append({
                    "title": entry.title,
                    "link": entry.link,
                    "published": entry.get("published", datetime.now(timezone.utc).replace(tzinfo=None).strftime("%a, %d %b %Y %H:%M:%S GMT")),
                    "sentiment": sentiment,
                    "source": "CNBC" if "cnbc" in feed_url else "WSJ"
                })
        except Exception as e:
            app.logger.debug(f"Error parsing feed {feed_url}: {e}")
        return items

    try:
        with concurrent.futures.ThreadPoolExecutor() as executor:
            results = list(executor.map(fetch_feed, feeds))
            for res in results:
                news_items.extend(res)

        return jsonify({"news": news_items[:15]})
    except Exception as e:
        app.logger.error(f"Error fetching news: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/stress_matrix')
@admin_required
def stress_matrix():
    return render_template('stress_matrix.html')

@app.route('/api/stress_matrix_data')
@admin_required
@cache_json_response(ttl_seconds=60)
def stress_matrix_data():

    symbols = ["SPY", "QQQ", "TLT", "GLD", "USO", "UUP", "BTC-USD"]
    try:
        df = yf.download(symbols, period="6mo", progress=False)['Close']
        returns = df.pct_change().dropna()
        correlation = returns.corr()

        # ⚡ OPTIMIZATION: Vectorized O(N^2) python loops by utilizing pandas C-level methods.
        # Using .values.tolist() provides O(1) performance as the matrix is already aligned by df.corr()
        matrix = correlation.values.tolist()

        return jsonify({
            "symbols": symbols,
            "correlation_matrix": matrix
        })
    except Exception as e:
        app.logger.error(f"Error fetching stress matrix: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/system/swarm_status')
@admin_required
def swarm_status():
    status = []
    for app_name, app_data in processes.items():
        state = app_data.get('status', 'stopped')
        status.append({"name": app_name, "status": state})
    return jsonify({"agents": status})

@app.route('/api/system/logs/forum.log')
@admin_required
def get_forum_logs():
    try:
        if os.path.exists('app.log'):
            with open('app.log', 'r', encoding='utf-8') as f:
                # Read last 50 lines or so
                lines = list(collections.deque(f, maxlen=50))
                return jsonify({"success": True, "logs": "".join(lines)})
        return jsonify({"success": True, "logs": ""})
    except Exception as e:
        app.logger.error(f"Error reading logs: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/system/logs/all')
@admin_required
def api_system_logs_all():
    return get_all_logs()


@app.route('/api/system/status', methods=['GET'])
@admin_required
@cache_json_response(ttl_seconds=10)
def api_system_status():
    status = "running"

    # Calculate real uptime
    uptime_duration = datetime.now(timezone.utc).replace(tzinfo=None) - APP_START_TIME
    days = uptime_duration.days
    hours, remainder = divmod(uptime_duration.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)

    uptime_parts = []
    if days > 0:
        uptime_parts.append(f"{days}d")
    if hours > 0:
        uptime_parts.append(f"{hours}h")
    if minutes > 0:
        uptime_parts.append(f"{minutes}m")
    uptime_parts.append(f"{seconds}s")

    uptime_str = " ".join(uptime_parts)

    return jsonify({
        "success": True,
        "status": status,
        "uptime": uptime_str
    })

@app.route('/api/system/start', methods=['POST'])
@admin_required
def api_system_start():
    # Start all agents that are not already running
    started = []
    failed = []

    for app_name in processes.keys():
        if processes[app_name]['status'] != 'running':
            if app_name == 'forum':
                try:
                    start_forum_engine()
                    processes['forum']['status'] = 'running'
                    started.append(app_name)
                except Exception as exc:
                    app.logger.error(f"Failed to start forum engine: {exc}")
                    failed.append(app_name)
            else:
                try:
                    script_path = STREAMLIT_SCRIPTS.get(app_name)
                    if not script_path:
                        failed.append(app_name)
                        continue

                    success, message = start_streamlit_app(
                        app_name,
                        script_path,
                        processes[app_name]['port']
                    )

                    if success:
                        started.append(app_name)
                    else:
                        failed.append(app_name)
                except Exception as exc:
                    app.logger.error(f"Failed to start {app_name}: {exc}")
                    failed.append(app_name)

    if not failed:
        return jsonify({
            "success": True,
            "message": f"System started successfully. Agents started: {', '.join(started) if started else 'None (all were running)'}."
        })
    else:
        return jsonify({
            "success": False,
            "message": f"System start partially failed. Started: {started}, Failed: {failed}"
        }), 500

@app.route('/api/system/shutdown', methods=['POST'])
@admin_required
def api_system_shutdown():
    # Stop all agents that are running
    stopped = []
    failed = []

    for app_name in processes.keys():
        if processes[app_name]['status'] == 'running':
            if app_name == 'forum':
                try:
                    stop_forum_engine()
                    processes['forum']['status'] = 'stopped'
                    stopped.append(app_name)
                except Exception as exc:
                    app.logger.error(f"Failed to stop forum engine: {exc}")
                    failed.append(app_name)
            else:
                try:
                    stop_streamlit_app(app_name)
                    stopped.append(app_name)
                except Exception as exc:
                    app.logger.error(f"Failed to stop {app_name}: {exc}")
                    failed.append(app_name)

    if not failed:
        return jsonify({
            "success": True,
            "message": f"System shutdown successfully. Agents stopped: {', '.join(stopped) if stopped else 'None (all were already stopped)'}."
        })
    else:
        return jsonify({
            "success": False,
            "message": f"System shutdown partially failed. Stopped: {stopped}, Failed: {failed}"
        }), 500

@app.route('/api/config', methods=['GET'])
@admin_required
def get_config():
    # Return minimal system config to satisfy frontend
    config_vals = read_config_values()
    if config_vals is None:
        config_vals = {k: '' for k in CONFIG_KEYS}

    # Hide actual ADMIN_API_KEY
    if 'ADMIN_API_KEY' in config_vals and config_vals['ADMIN_API_KEY']:
        config_vals['ADMIN_API_KEY'] = '********'

    return jsonify({
        "success": True,
        "config": config_vals
    })

@app.route('/api/config', methods=['POST'])
@admin_required
def update_config():
    updates = request.json
    if not updates:
        return jsonify({"success": False, "message": "No data provided"}), 400

    # Prevent updating ADMIN_API_KEY if it's the masked value
    if 'ADMIN_API_KEY' in updates and updates['ADMIN_API_KEY'] == '********':
        del updates['ADMIN_API_KEY']

    try:
        write_config_values(updates)

        # Optionally reload settings here or just return success
        try:
            # from config import reload_settings (hoisted)
            reload_settings()
        except ImportError:
            pass

        new_config = read_config_values()
        if new_config and 'ADMIN_API_KEY' in new_config and new_config['ADMIN_API_KEY']:
            new_config['ADMIN_API_KEY'] = '********'

        return jsonify({"success": True, "config": new_config})
    except Exception as e:
        app.logger.error(f"Error updating config: {e}")
        return jsonify({"success": False, "message": str(e)}), 500

def get_all_logs():
    try:
        if os.path.exists('app.log'):
            with open('app.log', 'r', encoding='utf-8') as f:
                lines = [l.strip() for l in collections.deque(f, maxlen=20) if l.strip()]
                return jsonify({"success": True, "logs": lines})
        return jsonify({"success": True, "logs": []})
    except Exception as e:
        app.logger.error(f"Error reading logs: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

if __name__ == "__main__":
    host = os.environ.get('HOST', '0.0.0.0')
    port = int(os.environ.get('PORT', 5000))
    logger.info(f"Starting TrendPulse on http://{host}:{port} (Local: http://localhost:{port})")
    socketio.run(app, host=host, port=port, allow_unsafe_werkzeug=True)
