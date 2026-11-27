"""
Report Engine Flaskinterface。

This module provides a unified HTTP/SSE entry for the front end/CLI，Responsible：
1. Initialize ReportAgent and connect background threads in series；
2. Manage task queue、Progress query、Streaming push and Logs download；
3. Provide template list、Input file checking and other peripheral capabilities。
"""

import os
import json
import threading
import time, threading
from collections import deque, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from queue import Queue, Empty
from flask import Blueprint, request, jsonify, Response, send_file, stream_with_context
from typing import Dict, Any, List, Optional
from loguru import logger
from .agent import create_agent
from .nodes import ChapterJsonParseError
from config import settings



report_bp = Blueprint('report_engine', __name__)


report_agent = None
current_task = None
task_lock = threading.Lock()



MAX_TASK_HISTORY = 5
STREAM_HEARTBEAT_INTERVAL = 15
STREAM_IDLE_TIMEOUT = 120
STREAM_TERMINAL_STATUSES = {"completed", "error", "cancelled"}
stream_lock = threading.Lock()
stream_subscribers = defaultdict(list)
tasks_registry: Dict[str, 'ReportTask'] = {}
LOG_STREAM_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
log_stream_handler_id: Optional[int] = None

EXCLUDED_ENGINE_PATH_KEYWORDS = ("ForumEngine", "InsightEngine", "MediaEngine", "QueryEngine")

def _is_excluded_engine_log(record: Dict[str, Any]) -> bool:
    """
    Determine whether Logs come from other engines（Insight/Media/Query/Forum），For filtering and mixingLogs。

    Return:
        bool: True means filtering should be performed（i.e. no writing/no forwarding）。
    """
    try:
        if "file" in record and hasattr(record["file"], "path"):
            file_path = record["file"].path
            if any(keyword in file_path for keyword in EXCLUDED_ENGINE_PATH_KEYWORDS):
                return True
    except Exception as e:
        logger.debug(f"Error extracting path from log record: {e}")

    try:
        module_name = record.get("module", "")
        if isinstance(module_name, str):
            lowered = module_name.lower()
            return any(keyword.lower() in lowered for keyword in EXCLUDED_ENGINE_PATH_KEYWORDS)
    except Exception as e:
        logger.debug(f"Error extracting module from log record: {e}")

    return False


def _stream_log_to_task(message):
    """
    Synchronize loguruLogs to SSE events of current task，Ensure front-end visibility in real time。

    Push only if there is a running task，Avoid flushing the screen with irrelevant Logs。
    """
    try:
        record = message.record
        level_name = record["level"].name
        if level_name not in LOG_STREAM_LEVELS:
            return
        if _is_excluded_engine_log(record):
            return

        with task_lock:
            task = current_task

        if not task or task.status not in ("running", "pending"):
            return

        timestamp = record["time"].strftime("%H:%M:%S.%f")[:-3]
        formatted_line = f"[{timestamp}] [{level_name}] {record['message']}"
        task.publish_event(
            "log",
            {
                "line": formatted_line,
                "level": level_name.lower(),
                "timestamp": timestamp,
                "message": record["message"],
                "module": record.get("module", ""),
                "function": record.get("function", ""),
            },
        )
    except Exception as e:
        import sys
        print(f"Error formatting stream log: {e}", file=sys.stderr)


def _setup_log_stream_forwarder():
    """Mount a one-time loguru hook for the current process，Used for SSE real-time forwarding。"""
    global log_stream_handler_id
    if log_stream_handler_id is not None:
        return
    log_stream_handler_id = logger.add(
        _stream_log_to_task,
        level="DEBUG",
        enqueue=False,
        catch=True,
    )


def _register_stream(task_id: str) -> Queue:
    """
    Register an event queue for the specified task，For consumption by SSE listeners。

    The returned Queue will be stored in `stream_subscribers`，SSE The generator will constantly read。

    Parameters:
        task_id: the task that needs to be monitoredID。

    Return:
        Queue: Thread-safe event queue。
    """
    queue = Queue()
    with stream_lock:
        stream_subscribers[task_id].append(queue)
    return queue


def _unregister_stream(task_id: str, queue: Queue):
    """
    Safely remove event queues，Avoid memory leaks。

    Need to be called in finally，Ensure that resources can be released under abnormal circumstances。

    Parameters:
        task_id: taskID。
        queue: Previously registered event queue。
    """
    with stream_lock:
        listeners = stream_subscribers.get(task_id, [])
        if queue in listeners:
            listeners.remove(queue)
        if not listeners and task_id in stream_subscribers:
            stream_subscribers.pop(task_id, None)


def _broadcast_event(task_id: str, event: Dict[str, Any]):
    """
    Push events to All listeners，FailedDo a good job of catching exceptions when。

    Using shallow copy listening list，Prevent concurrent removal from causing traversal exceptions。

    Parameters:
        task_id: Task to be pushedID。
        event: structured eventspayload。
    """
    with stream_lock:
        listeners = list(stream_subscribers.get(task_id, []))
    for queue in listeners:
        try:
            queue.put(event, timeout=0.1)
        except Exception:
            logger.exception("Push streaming eventsFailed，Skip the current listening queue")


def _prune_task_history_locked():
    """
    Called while task_lock is held，Clean up too many historical tasks。

    Keep only the most recent `MAX_TASK_HISTORY` tasks，Avoid taking up too much memory when running for a long time。

    Its training data set must contain elderly samples that are proportionate to the population structure `task_lock`，Otherwise, there is a race risk。
    """
    if len(tasks_registry) <= MAX_TASK_HISTORY:
        return

    sorted_tasks = sorted(tasks_registry.values(), key=lambda t: t.created_at)
    for task in sorted_tasks[:-MAX_TASK_HISTORY]:
        tasks_registry.pop(task.task_id, None)


def _get_task(task_id: str) -> Optional['ReportTask']:
    """
    Unified task search method，Parameters:
            blocks: list or subtree of blocks for the chapter。

    Avoid duplicating lock logic，Facilitates sharing between multiple APIs。

    Parameters:
        task_id: taskID。

    return:
        ReportTask | None: Returns task instance on hit，OtherwiseNone。
    """
    with task_lock:
        if current_task and current_task.task_id == task_id:
            return current_task
        return tasks_registry.get(task_id)


def _format_sse(event: Dict[str, Any]) -> str:
    """
    Format messages according to SSE protocol。

    The output looks like `id:/event:/data:` three paragraphs of text，For direct consumption on the browser side。

    Parameters:
        event: eventpayload，contains at least id/type。

    Return:
        str: string required by SSE protocol。
    """
    payload = json.dumps(event, ensure_ascii=False)
    event_id = event.get('id', 0)
    event_type = event.get('type', 'message')
    return f"id: {event_id}\nevent: {event_type}\ndata: {payload}\n\n"


def _safe_filename_segment(value: str, fallback: str = "report") -> str:
    """
    Generate safe fragments that can be used for filenames，Preserve alphanumeric and common delimiters。

    Parameters:
        value: original string。
        fallback: Dirty text，Used when value is empty or empty after cleaning。
    """
    sanitized = "".join(c for c in str(value) if c.isalnum() or c in (" ", "-", "_")).strip()
    sanitized = sanitized.replace(" ", "_")
    return sanitized or fallback


def initialize_report_engine():
    """
    initializationReport Engine。

    Singleton ReportAgent，Convenient to receive tasks directly after the API is started。

    Return:
        bool: return from initialization SuccessTrue，Return on exceptionFalse。
    """
    global report_agent
    try:
        report_agent = create_agent()
        logger.info("Report EngineinitializationSuccess")
        _setup_log_stream_forwarder()


        try:
            from .utils.dependency_check import log_dependency_status
            log_dependency_status()
        except Exception as dep_err:
            logger.warning(f"Dependency detectionFailed: {dep_err}")

        return True
    except Exception as e:
        logger.exception(f"Report EngineinitializationFailed: {str(e)}")
        return False


class ReportTask:
    """
    Report generation task。

    The object concatenates the running status、schedule、Event history and final file path，
    Both for background thread updates，Also read by HTTP interface。
    """

    def __init__(self, query: str, task_id: str, custom_template: str = ""):
        """
        Initialize task object，record query terms、Custom templates and runtime metadata。

        Args:
            query: The final report theme that needs to be generated
            task_id: task is uniqueID，Usually constructed from a timestamp
            custom_template: Optional custom Markdown template
        """
        self.task_id = task_id
        self.query = query
        self.custom_template = custom_template
        self.status = "pending"
        self.progress = 0
        self.result = None
        self.error_message = ""
        self.created_at = datetime.now(timezone.utc).replace(tzinfo=None)
        self.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
        self.html_content = ""
        self.report_file_path = ""
        self.report_file_relative_path = ""
        self.report_file_name = ""
        self.state_file_path = ""
        self.state_file_relative_path = ""
        self.ir_file_path = ""
        self.ir_file_relative_path = ""
        self.markdown_file_path = ""
        self.markdown_file_relative_path = ""
        self.markdown_file_name = ""


        self.event_history: deque = deque(maxlen=1000)
        self._event_lock = threading.Lock()
        self.last_event_id = 0

    def update_status(self, status: str, progress: int = None, error_message: str = ""):
        """
        Update task status and broadcast events。

        Will automatically refresh `updated_at`、ErrorsInfo，Chapter content streaming callback `status` type SSE。

        Parameters:
            status: task stage（pending/running/completed/error/cancelled）。
            progress: Optional progress percentage。
            error_message: A human-readable description of the error。
        """
        self.status = status
        if progress is not None:
            self.progress = progress
        if error_message:
            self.error_message = error_message
        self.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)

        self.publish_event(
            'status',
            {
                'status': self.status,
                'progress': self.progress,
                'error_message': self.error_message,
                'hint': error_message or '',
                'task': self.to_dict(),
            }
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format，Convenient to return directly toJSON API。"""
        return {
            'task_id': self.task_id,
            'query': self.query,
            'status': self.status,
            'progress': self.progress,
            'error_message': self.error_message,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
            'has_result': bool(self.html_content),
            'report_file_ready': bool(self.report_file_path),
            'report_file_name': self.report_file_name,
            'report_file_path': self.report_file_relative_path or self.report_file_path,
            'state_file_ready': bool(self.state_file_path),
            'state_file_path': self.state_file_relative_path or self.state_file_path,
            'ir_file_ready': bool(self.ir_file_path),
            'ir_file_path': self.ir_file_relative_path or self.ir_file_path,
            'markdown_file_ready': bool(self.markdown_file_path),
            'markdown_file_name': self.markdown_file_name,
            'markdown_file_path': self.markdown_file_relative_path or self.markdown_file_path
        }

    def publish_event(self, event_type: str, payload: Dict[str, Any]) -> None:
        """
        Put arbitrary events into the cache and broadcast them，AllNew logic is provided with Chinese instructions。

        Parameters:
            event_type: event name in SSE。
            payload: actual business data。
        """
        timestamp = datetime.now(timezone.utc).replace(tzinfo=None).isoformat() + 'Z'
        event: Dict[str, Any] = {
            'id': 0,
            'type': event_type,
            'task_id': self.task_id,
            'timestamp': timestamp,
            'payload': payload,
        }
        with self._event_lock:
            self.last_event_id += 1
            event['id'] = self.last_event_id
            self.event_history.append(event)
        _broadcast_event(self.task_id, event)

    def history_since(self, last_event_id: Optional[int]) -> List[Dict[str, Any]]:
        """
        Reissue historical events based on Last-Event-ID，Make sure nothing is missed when disconnected and reconnected。

        Parameters:
            last_event_id: The last event recorded by the SSE clientID。

        Return:
            list[dict]: list of events starting from last_event_id。
        """
        with self._event_lock:
            if last_event_id is None:
                return list(self.event_history)
            return [evt for evt in self.event_history if evt['id'] > last_event_id]


def check_engines_ready() -> Dict[str, Any]:
    """
    Check if all three sub-engines have new files。

    Call ReportAgent’s benchmark detection logic，And comes with the existence of forum Logs，
    yes /status、/generate pre-check。
    """
    directories = {
        'insight': 'insight_engine_streamlit_reports',
        'media': 'media_engine_streamlit_reports',
        'query': 'query_engine_streamlit_reports'
    }

    forum_log_path = 'logs/forum.log'

    if not report_agent:
        return {
            'ready': False,
            'error': 'Report Enginenot initialized'
        }

    return report_agent.check_input_files(
        directories['insight'],
        directories['media'],
        directories['query'],
        forum_log_path
    )


def run_report_generation(task: ReportTask, query: str, custom_template: str = ""):
    """
    Run report generation in a background thread。

    include：Check input→Load document→callReportAgent→Persistent output→
    Push phased events。When Errors occur, the status will be automatically pushed and written.。

    Parameters:
        task: object of this task，Internally held event queue。
        query: ReportTheme。
        custom_template: Optional custom template string。
    """
    global current_task

    try:

        def stream_handler(event_type: str, payload: Dict[str, Any]):
            """AllStage events are all distributed through the same interface，Ensure Logs are consistent。"""
            task.publish_event(event_type, payload)

            if event_type == 'progress' and 'progress' in payload:
                task.update_status("running", payload['progress'])

        task.update_status("running", 5)
        task.publish_event('stage', {'message': 'Task started，Checking input file', 'stage': 'prepare'})


        check_result = check_engines_ready()
        if not check_result['ready']:
            task.update_status("error", 0, f"Input file not ready: {check_result.get('missing_files', [])}")
            return

        task.publish_event('stage', {
            'message': 'Input file check passed，Ready to load content',
            'stage': 'io_ready',
            'files': check_result.get('latest_files', {})
        })


        content = report_agent.load_input_files(check_result['latest_files'])
        task.publish_event('stage', {'message': 'Source data loadingCompleted，Start the build process', 'stage': 'data_loaded'})


        for attempt in range(1, 3):
            try:
                task.publish_event('stage', {
                    'message': f'Calling ReportAgent to generate a report（No.{attempt}attempts）',
                    'stage': 'agent_running',
                    'attempt': attempt
                })
                generation_result = report_agent.generate_report(
                    query=query,
                    reports=content['reports'],
                    forum_logs=content['forum_logs'],
                    custom_template=custom_template,
                    save_report=True,
                    stream_handler=stream_handler
                )
                break
            except ChapterJsonParseError as err:
                hint_message = "Try changing the API of Report Engine to one with stronger computing power、longer contextLLM"
                task.publish_event('warning', {
                    'message': hint_message,
                    'stage': 'agent_running',
                    'attempt': attempt,
                    'reason': 'chapter_json_parse',
                    'error': str(err),
                    'task': task.to_dict(),
                })

                # backoff = min(5 * attempt, 15)
                # task.publish_event('stage', {

                #     'stage': 'retry_wait',
                #     'wait_seconds': backoff
                # })
                # threading.Event().wait(backoff)
                raise ChapterJsonParseError(hint_message) from err
            except Exception as err:

                task.publish_event('warning', {
                    'message': f'ReportAgentimplementFailed: {str(err)}',
                    'stage': 'agent_running',
                    'attempt': attempt
                })
                if attempt == 2:
                    raise

                backoff = min(5 * attempt, 15)
                task.publish_event('stage', {
                    'message': f'{backoff} Retry generates tasks after seconds',
                    'stage': 'retry_wait',
                    'wait_seconds': backoff
                })
                threading.Event().wait(backoff)

        if isinstance(generation_result, dict):
            html_report = generation_result.get('html_content', '')
        else:
            html_report = generation_result

        task.publish_event('stage', {'message': 'Report generation completed，Prepare for persistence', 'stage': 'persist'})


        task.html_content = html_report
        if isinstance(generation_result, dict):
            task.report_file_path = generation_result.get('report_filepath', '')
            task.report_file_relative_path = generation_result.get('report_relative_path', '')
            task.report_file_name = generation_result.get('report_filename', '')
            task.state_file_path = generation_result.get('state_filepath', '')
            task.state_file_relative_path = generation_result.get('state_relative_path', '')
            task.ir_file_path = generation_result.get('ir_filepath', '')
            task.ir_file_relative_path = generation_result.get('ir_relative_path', '')
        task.publish_event('html_ready', {
            'message': 'HTMLrenderingCompleted，Refreshable preview',
            'report_file': task.report_file_relative_path or task.report_file_path,
            'state_file': task.state_file_relative_path or task.state_file_path,
            'task': task.to_dict(),
        })
        task.update_status("completed", 100)
        task.publish_event('completed', {
            'message': 'TaskCompleted',
            'duration_seconds': (task.updated_at - task.created_at).total_seconds(),
            'report_file': task.report_file_relative_path or task.report_file_path,
            'task': task.to_dict(),
        })

    except Exception as e:
        logger.exception(f"Occurs during report generationErrors: {str(e)}")
        task.update_status("error", 0, str(e))
        task.publish_event('error', {
            'message': str(e),
            'stage': 'failed',
            'task': task.to_dict(),
        })

        with task_lock:
            if current_task and current_task.task_id == task.task_id:
                current_task = None


@report_bp.route('/status', methods=['GET'])
def get_status():
    """
    Get Report Engine status，Includes engine readiness and current tasksInfo。

    Return:
        Response: JSON structure contains initialized/engines_ready/current tasks, etc.。
    """
    try:
        engines_status = check_engines_ready()

        return jsonify({
            'success': True,
            'initialized': report_agent is not None,
            'engines_ready': engines_status['ready'],
            'files_found': engines_status.get('files_found', []),
            'missing_files': engines_status.get('missing_files', []),
            'current_task': current_task.to_dict() if current_task else None
        })
    except Exception as e:
        logger.exception(f"Get Report Engine statusFailed: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@report_bp.route('/generate', methods=['POST'])
def generate_report():
    """
    Start generating reports。

    Responsible for queuing、Create background thread、ClearLogsand returns the SSE address。

    Request body:
        query: reportTheme（Optional）。
        custom_template: Custom template string（Optional）。

    return:
        Response: JSON，Contains task_id and SSE stream url。
    """
    global current_task

    try:

        with task_lock:
            if current_task and current_task.status == "running":
                return jsonify({
                    'success': False,
                    'error': 'A report generation task is already running',
                    'current_task': current_task.to_dict()
                }), 400


            if current_task and current_task.status in ["completed", "error"]:
                current_task = None


        data = request.get_json() or {}
        if not isinstance(data, dict):
            logger.warning("generate_report Non-object JSON payload received，Original content ignored")
            data = {}
        query = data.get('query', 'Intelligent public opinion analysis report')
        custom_template = data.get('custom_template', '')


        clear_report_log()


        if not report_agent:
            return jsonify({
                'success': False,
                'error': 'Report Enginenot initialized'
            }), 500


        engines_status = check_engines_ready()
        if not engines_status['ready']:
            return jsonify({
                'success': False,
                'error': 'Input file not ready',
                'missing_files': engines_status.get('missing_files', [])
            }), 400


        task_id = f"report_{int(time.time())}"
        task = ReportTask(query, task_id, custom_template)

        with task_lock:
            current_task = task
            tasks_registry[task_id] = task
            _prune_task_history_locked()


        task.publish_event(
            'status',
            {
                'status': task.status,
                'progress': task.progress,
                'message': 'Task queued，Wait for resources to become free',
                'task': task.to_dict(),
            }
        )


        thread = threading.Thread(
            target=run_report_generation,
            args=(task, query, custom_template),
            daemon=True
        )
        thread.start()

        return jsonify({
            'success': True,
            'task_id': task_id,
            'message': 'Report generation started',
            'task': task.to_dict(),
            'stream_url': f"/api/report/stream/{task_id}"
        })

    except Exception as e:
        logger.exception(f"Start generating reportsFailed: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@report_bp.route('/progress/<task_id>', methods=['GET'])
def get_progress(task_id: str):
    """
    Get report generation progress，If the task is cleared, a Completed state is returned.。

    Parameters:
        task_id: task unique identifier。

    Return:
        Response: JSON contains the current status of the task。
    """
    try:
        task = _get_task(task_id)
        if not task:

            return jsonify({
                'success': True,
                'task': {
                    'task_id': task_id,
                    'status': 'completed',
                    'progress': 100,
                    'error_message': '',
                    'has_result': True,
                    'report_file_ready': False,
                    'report_file_name': '',
                    'report_file_path': '',
                    'state_file_ready': False,
                    'state_file_path': ''
                }
            })

        return jsonify({
            'success': True,
            'task': task.to_dict()
        })

    except Exception as e:
        logger.exception(f"Get report generation progressFailed: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@report_bp.route('/stream/<task_id>', methods=['GET'])
def stream_task(task_id: str):
    """
    Real-time push interface based on SSE。

    - Automatically reissue historical events after Last-Event-ID；
    - Send heartbeats periodically in case of agent outage；
    - Automatically log out of the monitor after the task is completed。

    Parameters:
        task_id: task unique identifier。

    return:
        Response: `text/event-stream` type response。
    """
    task = _get_task(task_id)
    if not task:
        return jsonify({'success': False, 'error': 'Task does not exist'}), 404

    last_event_header = request.headers.get('Last-Event-ID')
    try:
        last_event_id = int(last_event_header) if last_event_header else None
    except ValueError:
        last_event_id = None

    def client_disconnected() -> bool:
        """
        Detect as early as possible whether the client has disconnected，Avoid continuing write triggersBrokenPipe。

        eventlet On Windows throws when closing the connection ConnectionAbortedError，
        Exiting the generator early can reduce the meaninglessLogs。
        """
        try:
            env_input = request.environ.get('wsgi.input')
            return bool(getattr(env_input, 'closed', False))
        except Exception:
            return False

    def event_generator():
        """
        SSEevent generator。

        - Responsible for registering and consuming the event queue of the corresponding task；
        - Play back historical events first and then continue to monitor real-time events；
        - Send heartbeats periodically and automatically log off the listener after the task ends。
        """
        queue = _register_stream(task_id)
        last_data_ts = time.time()
        try:

            history = task.history_since(last_event_id)
            for event in history:
                yield _format_sse(event)
                if event.get('type') != 'heartbeat':
                    last_data_ts = time.time()

            finished = task.status in STREAM_TERMINAL_STATUSES
            while True:
                if finished:
                    break
                if client_disconnected():
                    logger.info(f"SSEClient has been disconnected，Stop pushing: {task_id}")
                    break
                event = None
                try:
                    event = queue.get(timeout=STREAM_HEARTBEAT_INTERVAL)
                except Empty:
                    if task.status in STREAM_TERMINAL_STATUSES:
                        logger.info(f"Task {task_id} Ended and no new events，SSEAutomatic closing")
                        break
                    heartbeat = {
                        'id': f"hb-{int(time.time() * 1000)}",
                        'type': 'heartbeat',
                        'task_id': task_id,
                        'timestamp': datetime.now(timezone.utc).replace(tzinfo=None).isoformat() + 'Z',
                        'payload': {'status': task.status}
                    }
                    event = heartbeat
                if event is None:
                    logger.warning(f"SSEpush eventFailed（task {task_id}），end early")
                    break

                try:
                    yield _format_sse(event)
                    if event.get('type') != 'heartbeat':
                        last_data_ts = time.time()
                except GeneratorExit:
                    logger.info(f"SSEGenerator closed，Stop task {task_id} Push")
                    break
                except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError) as exc:
                    logger.warning(f"SSEThe connection was interrupted by the client（task {task_id}）: {exc}")
                    break
                except Exception as exc:
                    event_type = event.get('type') if isinstance(event, dict) else 'unknown'
                    logger.exception(f"SSEPushFailed（task {task_id}, event {event_type}）: {exc}")
                    break

                if event.get('type') in ("completed", "error", "cancelled"):
                    finished = True
                else:
                    finished = finished or task.status in STREAM_TERMINAL_STATUSES


                if task.status in STREAM_TERMINAL_STATUSES:
                    idle_for = time.time() - last_data_ts
                    if idle_for > STREAM_IDLE_TIMEOUT:
                        logger.info(f"Task {task_id} Finalized and idle {int(idle_for)}s，Actively closeSSE")
                        break
        finally:
            _unregister_stream(task_id, queue)

    response = Response(
        stream_with_context(event_generator()),
        mimetype='text/event-stream'
    )
    response.headers['Cache-Control'] = 'no-cache'
    response.headers['X-Accel-Buffering'] = 'no'
    return response


@report_bp.route('/result/<task_id>', methods=['GET'])
def get_result(task_id: str):
    """
    Get report generation results。

    Parameters:
        task_id: taskID。

    return:
        Response: JSON，Contains HTML preview and file path。
    """
    try:
        task = _get_task(task_id)
        if not task:
            return jsonify({
                'success': False,
                'error': 'Task does not exist'
            }), 404

        if task.status != "completed":
            return jsonify({
                'success': False,
                'error': 'Report not yetCompleted',
                'task': task.to_dict()
            }), 400

        return Response(
            task.html_content,
            mimetype='text/html'
        )

    except Exception as e:
        logger.exception(f"Get report generation resultsFailed: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@report_bp.route('/result/<task_id>/json', methods=['GET'])
def get_result_json(task_id: str):
    """Get report generation results（JSONFormat）"""
    try:
        task = _get_task(task_id)
        if not task:
            return jsonify({
                'success': False,
                'error': 'Task does not exist'
            }), 404

        if task.status != "completed":
            return jsonify({
                'success': False,
                'error': 'Report not yetCompleted',
                'task': task.to_dict()
            }), 400

        return jsonify({
            'success': True,
            'task': task.to_dict(),
            'html_content': task.html_content
        })

    except Exception as e:
        logger.exception(f"Get report generation resultsFailed: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@report_bp.route('/download/<task_id>', methods=['GET'])
def download_report(task_id: str):
    """
    Download the generated report HTML file。

    Parameters:
        task_id: taskID。

    Return:
        Response: Attachment download response of HTML file。
    """
    try:
        task = _get_task(task_id)
        if not task:
            return jsonify({
                'success': False,
                'error': 'Task does not exist'
            }), 404

        if task.status != "completed" or not task.report_file_path:
            return jsonify({
                'success': False,
                'error': 'The report is not Completed or has not been saved yet'
            }), 400

        if not os.path.exists(task.report_file_path):
            return jsonify({
                'success': False,
                'error': 'Report file does not exist or has been deleted'
            }), 404

        download_name = task.report_file_name or os.path.basename(task.report_file_path)
        return send_file(
            task.report_file_path,
            mimetype='text/html',
            as_attachment=True,
            download_name=download_name
        )

    except Exception as e:
        logger.exception(f"Download reportFailed: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@report_bp.route('/cancel/<task_id>', methods=['POST'])
def cancel_task(task_id: str):
    """
    Cancel report generation task。

    Parameters:
        task_id: the task that needs to be canceledID。

    return:
        Response: JSON，Contains cancellation results orErrorsInfo。
    """
    global current_task

    try:
        with task_lock:
            if current_task and current_task.task_id == task_id:
                if current_task.status == "running":
                    current_task.update_status("cancelled", 0, "User cancels task")
                    current_task.publish_event('cancelled', {
                        'message': 'The task was actively terminated by the user',
                        'task': current_task.to_dict(),
                    })
                current_task = None
            task = tasks_registry.get(task_id)
            if task and task.status == 'running':
                task.update_status("cancelled", task.progress, "User cancels task")
                task.publish_event('cancelled', {
                    'message': 'The task was actively terminated by the user',
                    'task': task.to_dict(),
                })

                return jsonify({
                    'success': True,
                    'message': 'Task canceled'
                })
            else:
                return jsonify({
                    'success': False,
                    'error': 'The task does not exist or cannot be canceled'
                }), 404

    except Exception as e:
        logger.exception(f"Cancel report generation taskFailed: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@report_bp.route('/templates', methods=['GET'])
def get_templates():
    """
    Get a list of available templates，Optional Markdown skeleton for front-end display。

    return:
        Response: JSON，List template name/description/size。
    """
    try:
        if not report_agent:
            return jsonify({
                'success': False,
                'error': 'Report Enginenot initialized'
            }), 500

        template_dir = settings.TEMPLATE_DIR
        templates = []

        if os.path.exists(template_dir):
            for filename in os.listdir(template_dir):
                if filename.endswith('.md'):
                    template_path = os.path.join(template_dir, filename)
                    try:
                        with open(template_path, 'r', encoding='utf-8') as f:
                            content = f.read()

                        templates.append({
                            'name': filename.replace('.md', ''),
                            'filename': filename,
                            'description': content.split('\n')[0] if content else 'No description',
                            'size': len(content)
                        })
                    except Exception as e:
                        logger.exception(f"Read templateFailed {filename}: {str(e)}")

        return jsonify({
            'success': True,
            'templates': templates,
            'template_dir': template_dir
        })

    except Exception as e:
        logger.exception(f"Get a list of available templatesFailed: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500



@report_bp.errorhandler(404)
def not_found(error):
    """404Deal with everything：Ensure that the interface returns a JSON structure uniformly"""
    logger.exception(f"APIEndpoint does not exist: {str(error)}")
    return jsonify({
        'success': False,
        'error': 'APIEndpoint does not exist'
    }), 404


@report_bp.errorhandler(500)
def internal_error(error):
    """500Deal with everything：Catching exceptions that are not actively caught"""
    logger.exception(f"Inside the serverErrors: {str(error)}")
    return jsonify({
        'success': False,
        'error': 'Inside the serverErrors'
    }), 500


def clear_report_log():
    """
    Clearreport.logdocument，It is convenient for new tasks to only view this runLogs。

    return:
        None
    """
    try:
        log_file = settings.LOG_FILE



        with open(log_file, 'r+', encoding='utf-8') as f:
            f.truncate(0)
            f.flush()

        logger.info(f"ClearLogs file: {log_file}")
    except FileNotFoundError:

        try:
            with open(log_file, 'w', encoding='utf-8') as f:
                f.write('')
            logger.info(f"Create Logs file: {log_file}")
        except Exception as e:
            logger.exception(f"Create Logs fileFailed: {str(e)}")
    except Exception as e:
        logger.exception(f"ClearLogsdocumentFailed: {str(e)}")


@report_bp.route('/log', methods=['GET'])
def get_report_log():
    """
    Get report.log content，and stripping the whitespace row by row returns。

    【repair】Optimize large file reading，Add Errors handling and file locking

    Return:
        Response: JSON，Array containing the latest Logs lines。
    """
    try:
        log_file = settings.LOG_FILE

        if not os.path.exists(log_file):
            return jsonify({
                'success': True,
                'log_lines': []
            })


        file_size = os.path.getsize(log_file)
        max_size = 10 * 1024 * 1024

        if file_size > max_size:

            with open(log_file, 'rb') as f:
                f.seek(-max_size, 2)

                f.readline()
                content = f.read().decode('utf-8', errors='replace')
            lines = content.splitlines()
            logger.warning(f"LogsFile too large ({file_size} bytes)，Return only the last {max_size} bytes")
        else:

            with open(log_file, 'r', encoding='utf-8', errors='replace') as f:
                import collections
                lines = list(collections.deque(f, maxlen=5000))


        log_lines = [line.rstrip('\n\r') for line in lines if line.strip()]

        return jsonify({
            'success': True,
            'log_lines': log_lines
        })

    except PermissionError as e:
        logger.error(f"Insufficient permission to read Logs: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'Insufficient permission to read Logs'
        }), 403
    except UnicodeDecodeError as e:
        logger.error(f"LogsFile encodingErrors: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'LogsFile encodingErrors'
        }), 500
    except Exception as e:
        logger.exception(f"readLogsFailed: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'readLogsFailed: {str(e)}'
        }), 500


@report_bp.route('/log/clear', methods=['POST'])
def clear_log():
    """
    ManualClearLogs，Provides a REST portal for one-click reset of the front-end。

    return:
        Response: JSON，Is the mark cleared?Success。
    """
    try:
        clear_report_log()
        return jsonify({
            'success': True,
            'message': 'LogsalreadyClear'
        })
    except Exception as e:
        logger.exception(f"ClearLogsFailed: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'ClearLogsFailed: {str(e)}'
        }), 500


@report_bp.route('/export/md/<task_id>', methods=['GET'])
def export_markdown(task_id: str):
    """
    Export report to Markdown format。

    Called based on a saved Document IR MarkdownRenderer，Generate file and return to download。
    """
    try:
        task = tasks_registry.get(task_id)
        if not task:
            return jsonify({
                'success': False,
                'error': 'Task does not exist'
            }), 404

        if task.status != 'completed':
            return jsonify({
                'success': False,
                'error': f'Task not yetCompleted，Current status: {task.status}'
            }), 400

        if not task.ir_file_path or not os.path.exists(task.ir_file_path):
            return jsonify({
                'success': False,
                'error': 'IRFile does not exist，Unable to generateMarkdown'
            }), 404

        with open(task.ir_file_path, 'r', encoding='utf-8') as f:
            document_ir = json.load(f)

        from .renderers import MarkdownRenderer
        renderer = MarkdownRenderer()

        markdown_text = renderer.render(document_ir, ir_file_path=task.ir_file_path)

        metadata = document_ir.get('metadata') if isinstance(document_ir, dict) else {}
        topic = (metadata or {}).get('topic') or (metadata or {}).get('title') or (metadata or {}).get('query') or task.query
        safe_topic = _safe_filename_segment(topic or 'report')
        timestamp = datetime.now(timezone.utc).replace(tzinfo=None).strftime('%Y%m%d_%H%M%S')
        filename = f"report_{safe_topic}_{timestamp}.md"

        output_dir = Path(settings.OUTPUT_DIR)
        output_dir.mkdir(parents=True, exist_ok=True)
        md_path = output_dir / filename
        md_path.write_text(markdown_text, encoding='utf-8')

        task.markdown_file_path = str(md_path.resolve())
        task.markdown_file_relative_path = os.path.relpath(task.markdown_file_path, os.getcwd())
        task.markdown_file_name = filename

        logger.info(f"ExportMarkdownCompleted: {md_path}")

        return send_file(
            task.markdown_file_path,
            mimetype='text/markdown',
            as_attachment=True,
            download_name=filename
        )

    except Exception as e:
        logger.exception(f"ExportMarkdownFailed: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'ExportMarkdownFailed: {str(e)}'
        }), 500


@report_bp.route('/export/pdf/<task_id>', methods=['GET'])
def export_pdf(task_id: str):
    """
    Export report to PDF format。

    Generate optimized from IR JSON filePDF，Support automatic layout adjustment。

    The following content covers all block types such as paragraph/list/table/swot/pest/widget one by one（defaulttrue）

    Return:
        Response: PDF file stream orErrorsInfo
    """
    try:

        from .utils.dependency_check import check_pango_available
        pango_available, pango_message = check_pango_available()
        if not pango_available:
            return jsonify({
                'success': False,
                'error': 'PDF Export function is not available：Missing system dependencies',
                'details': 'Please check the root directory README.md “Source code startup”The second step（PDF Export dependencies）Learn how to install',
                'help_url': 'https://github.com/PelleNybe/Trend-Pulse',
                'system_message': pango_message
            }), 503


        task = tasks_registry.get(task_id)
        if not task:
            return jsonify({
                'success': False,
                'error': 'Task does not exist'
            }), 404


        if task.status != 'completed':
            return jsonify({
                'success': False,
                'error': f'Task not yetCompleted，Current status: {task.status}'
            }), 400


        if not task.ir_file_path or not os.path.exists(task.ir_file_path):
            return jsonify({
                'success': False,
                'error': 'IRFile does not exist'
            }), 404


        with open(task.ir_file_path, 'r', encoding='utf-8') as f:
            document_ir = json.load(f)


        optimize = request.args.get('optimize', 'true').lower() == 'true'


        from .renderers import PDFRenderer
        renderer = PDFRenderer()

        logger.info(f"Start exportPDF，TaskID: {task_id}，Layout optimization: {optimize}")


        pdf_bytes = renderer.render_to_bytes(document_ir, optimize_layout=optimize)


        topic = document_ir.get('metadata', {}).get('topic', 'report')
        pdf_filename = f"report_{topic}_{datetime.now(timezone.utc).replace(tzinfo=None).strftime('%Y%m%d_%H%M%S')}.pdf"


        return Response(
            pdf_bytes,
            mimetype='application/pdf',
            headers={
                'Content-Disposition': f'attachment; filename="{pdf_filename}"',
                'Content-Type': 'application/pdf'
            }
        )

    except Exception as e:
        logger.exception(f"ExportPDFFailed: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'ExportPDFFailed: {str(e)}'
        }), 500


@report_bp.route('/export/pdf-from-ir', methods=['POST'])
def export_pdf_from_ir():
    """
    Export directly from IR JSONPDF（No tasks requiredID）。

    Suitable for scenarios where the front-end directly transmits IR data。

    Request body:
        {
            "document_ir": {...},  // Document IR JSON
            "optimize": true       // Whether to enable layout optimization（Optional）
        }

    Return:
        Response: PDF file stream orErrorsInfo
    """
    try:

        from .utils.dependency_check import check_pango_available
        pango_available, pango_message = check_pango_available()
        if not pango_available:
            return jsonify({
                'success': False,
                'error': 'PDF Export function is not available：Missing system dependencies',
                'details': 'Please check the root directory README.md “Source code startup”The second step（PDF Export dependencies）Learn how to install',
                'help_url': 'https://github.com/PelleNybe/Trend-Pulse',
                'system_message': pango_message
            }), 503

        data = request.get_json() or {}
        if not isinstance(data, dict):
            logger.warning("export_pdf_from_ir The request body is not a JSON object")
            return jsonify({
                'success': False,
                'error': 'The request body must be a JSON object'
            }), 400

        if not data or 'document_ir' not in data:
            return jsonify({
                'success': False,
                'error': 'missing document_ir parameter'
            }), 400

        document_ir = data['document_ir']
        optimize = data.get('optimize', True)


        from .renderers import PDFRenderer
        renderer = PDFRenderer()

        logger.info(f"Export directly from IRPDF，Layout optimization: {optimize}")


        pdf_bytes = renderer.render_to_bytes(document_ir, optimize_layout=optimize)


        topic = document_ir.get('metadata', {}).get('topic', 'report')
        pdf_filename = f"report_{topic}_{datetime.now(timezone.utc).replace(tzinfo=None).strftime('%Y%m%d_%H%M%S')}.pdf"


        return Response(
            pdf_bytes,
            mimetype='application/pdf',
            headers={
                'Content-Disposition': f'attachment; filename="{pdf_filename}"',
                'Content-Type': 'application/pdf'
            }
        )

    except Exception as e:
        logger.exception(f"Export from IRPDFFailed: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'ExportPDFFailed: {str(e)}'
        }), 500
