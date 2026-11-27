"""
Log Monitor - Real-time monitoring of SummaryNode output in three log files
"""

import time, threading
from .redis_pubsub import event_bus
import threading
from pathlib import Path
from datetime import datetime, timezone
import re
import json
from typing import Optional, List
from threading import Lock
from loguru import logger


try:
    from .llm_host import FinancialCommitteeHost, generate_host_speech
    HOST_AVAILABLE = True
except ImportError:
    logger.exception("ForumEngine: Forum moderator module not found，Will run in monitor-only mode")
    FinancialCommitteeHost = None
    generate_host_speech = None
    HOST_AVAILABLE = False

class LogMonitor:
    """Intelligent log monitor based on file changes"""
   
    def __init__(self, log_dir: str = "logs"):
        """Initialize log monitor"""
        self.log_dir = Path(log_dir)
        self.forum_log_file = self.log_dir / "forum.log"
       

        self.monitored_logs = {
            'insight': self.log_dir / 'insight.log',
            'media': self.log_dir / 'media.log',
            'query': self.log_dir / 'query.log'
        }
       

        self.is_monitoring = False
        self.monitor_thread = None
        self.file_positions = {}
        self.file_line_counts = {}
        self.is_searching = False
        self.search_inactive_count = 0
        self.write_lock = Lock()
        

        self.agent_speeches_buffer = []
        self.host_speech_threshold = 5
        self.is_host_generating = False
       





        self.target_node_patterns = [
            'FirstSummaryNode',
            'ReflectionSummaryNode',
            'InsightEngine.nodes.summary_node',
            'MediaEngine.nodes.summary_node',
            'QueryEngine.nodes.summary_node',
            'nodes.summary_node',
            'Generating first paragraph summary',
            'Generating reflection summary',
        ]
        

        self.capturing_json = {}
        self.json_buffer = {}
        self.json_start_line = {}
        self.in_error_block = {}
       

        self.log_dir.mkdir(exist_ok=True)
   
    def clear_forum_log(self):
        """Clear the forum.log file"""
        try:
            if self.forum_log_file.exists():
                self.forum_log_file.unlink()
           

            start_time = datetime.now(timezone.utc).replace(tzinfo=None).strftime('%Y-%m-%d %H:%M:%S')

            open(self.forum_log_file, 'w', encoding='utf-8').close()
            self.write_to_forum_log(f"=== ForumEngine Monitoring starts - {start_time} ===", "SYSTEM")
               
            logger.info("ForumEngine: forum.log Cleared and initialized")
            

            self.capturing_json = {}
            self.json_buffer = {}
            self.json_start_line = {}
            self.in_error_block = {}
            

            self.agent_speeches_buffer = []
            self.is_host_generating = False
           
        except Exception as e:
            logger.exception(f"ForumEngine: Failed to clear forum.log: {e}")
   
    def write_to_forum_log(self, content: str, source: str = None):
        """Write content toforum.log（Thread safety）"""
        try:
            with self.write_lock:
                with open(self.forum_log_file, 'a', encoding='utf-8') as f:
                    timestamp = datetime.now(timezone.utc).replace(tzinfo=None).strftime('%H:%M:%S')

                    content_one_line = content.replace('\n', '\\n').replace('\r', '\\r')

                    if source:
                        f.write(f"[{timestamp}] [{source}] {content_one_line}\n")
                    else:
                        f.write(f"[{timestamp}] {content_one_line}\n")
                    f.flush()
        except Exception as e:
            logger.exception(f"ForumEngine: Writing to forum.log failed: {e}")
    
    def get_log_level(self, line: str) -> Optional[str]:
        """Check the level of log lines（INFO/ERROR/WARNING/DEBUGwait）
        
        Support loguru format：YYYY-MM-DD HH:mm:ss.SSS | LEVEL | ...
        
        Returns:
            'INFO', 'ERROR', 'WARNING', 'DEBUG' or None（Unrecognized）
        """


        match = re.search(r'\|\s*(INFO|ERROR|WARNING|DEBUG|TRACE|CRITICAL)\s*\|', line)
        if match:
            return match.group(1)
        return None
    
    def is_target_log_line(self, line: str) -> bool:
        """Check if it is the target log line（SummaryNode）
        
        Support multiple identification methods：
        1. Class name：FirstSummaryNode, ReflectionSummaryNode
        2. full module path：InsightEngine.nodes.summary_node、MediaEngine.nodes.summary_node、QueryEngine.nodes.summary_node
        3. partial module path：nodes.summary_node（compatibility）
        4. key identification text：Generating first paragraph summary、Generating reflection summary
        
        Exclusion criteria：
        - ERROR level logging（Error log should not be recognized as target node）
        - Logs containing incorrect keywords（JSONParsing failed、JSONRepair failure etc.）
        """

        log_level = self.get_log_level(line)
        if log_level == 'ERROR':
            return False
        

        if "| ERROR" in line or "| ERROR    |" in line:
            return False
        

        error_keywords = ["JSONParsing failed", "JSONRepair failed", "Traceback", "File \""]
        for keyword in error_keywords:
            if keyword in line:
                return False
        

        for pattern in self.target_node_patterns:
            if pattern in line:
                return True
        return False
    
    def is_valuable_content(self, line: str) -> bool:
        """Determine whether it is valuable content（Exclude short prompts and error messages）"""

        if "Cleaned output" in line:
            return True
        

        exclude_patterns = [
            "JSONParsing failed",
            "JSONRepair failed",
            "Use the cleaned text directly",
            "JSONParsed successfully",
            "Successfully generated",
            "Paragraph updated",
            "Generating",
            "Start processing",
            "Processing completed",
            "HOST statement has been read",
            "Failed to read HOST statement",
            "HOST speech not found",
            "debug output",
            "information record"
        ]
        
        for pattern in exclude_patterns:
            if pattern in line:
                return False
        


        clean_line = re.sub(r'\[\d{2}:\d{2}:\d{2}\]', '', line)
        clean_line = re.sub(r'\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d{3}\s*\|\s*[A-Z]+\s*\|\s*[^|]+?\s*-\s*', '', clean_line)
        clean_line = clean_line.strip()
        if len(clean_line) < 30:
            return False
            
        return True
    
    def is_json_start_line(self, line: str) -> bool:
        """Determine whether it is the beginning line of JSON"""
        return "Cleaned output: {" in line
    
    def is_json_end_line(self, line: str) -> bool:
        """Determine whether it is the end of JSON line
        
        Only evaluate pure closing tag lines，Does not contain any log format information（Timestamp etc.）。
        If row contains timestamp，You should clean up first and then judge，But returning False here indicates that further processing is required。
        """
        stripped = line.strip()
        


        if re.match(r'^\[\d{2}:\d{2}:\d{2}\]', stripped):
            return False

        if re.match(r'^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d{3}', stripped):
            return False
        

        if stripped == "}" or stripped == "] }":
            return True
        return False
    
    def extract_json_content(self, json_lines: List[str]) -> Optional[str]:
        """Extract and parse JSON content from multiple lines"""
        try:

            json_start_idx = -1
            for i, line in enumerate(json_lines):
                if "Cleaned output: {" in line:
                    json_start_idx = i
                    break
            
            if json_start_idx == -1:
                return None
            

            first_line = json_lines[json_start_idx]
            json_start_pos = first_line.find("Cleaned output: {")
            if json_start_pos == -1:
                return None
            
            json_part = first_line[json_start_pos + len("Cleaned output: "):]
            

            if json_part.strip().endswith("}") and json_part.count("{") == json_part.count("}"):
                try:
                    json_obj = json.loads(json_part.strip())
                    return self.format_json_content(json_obj)
                except json.JSONDecodeError:

                    fixed_json = self.fix_json_string(json_part.strip())
                    if fixed_json:
                        try:
                            json_obj = json.loads(fixed_json)
                            return self.format_json_content(json_obj)
                        except json.JSONDecodeError:
                            pass
                    return None
            

            json_text_parts = [json_part]
            for line in json_lines[json_start_idx + 1:]:


                clean_line = re.sub(r'^\[\d{2}:\d{2}:\d{2}\]\s*', '', line)


                clean_line = re.sub(r'^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d{3}\s*\|\s*[A-Z]+\s*\|\s*[^|]+?\s*-\s*', '', clean_line)
                json_text_parts.append(clean_line)
            

            try:
                json_text = "".join(json_text_parts)
                json_obj = json.loads(json_text.strip())
                return self.format_json_content(json_obj)
            except json.JSONDecodeError:

                fixed_json = self.fix_json_string(json_text.strip())
                if fixed_json:
                    try:
                        json_obj = json.loads(fixed_json)
                        return self.format_json_content(json_obj)
                    except json.JSONDecodeError:
                        pass
                return None
            
        except Exception:

            return None
    
    def format_json_content(self, json_obj: dict) -> str:
        """Format JSON content into readable form"""
        try:

            content = None
            
            if "updated_paragraph_latest_state" in json_obj:
                content = json_obj["updated_paragraph_latest_state"]
            elif "paragraph_latest_state" in json_obj:
                content = json_obj["paragraph_latest_state"]
            

            if content:
                return content
            

            return f"Cleaned output: {json.dumps(json_obj, ensure_ascii=False, indent=2)}"
            
        except Exception as e:
            logger.exception(f"ForumEngine: Error formatting JSON: {e}")
            return f"Cleaned output: {json.dumps(json_obj, ensure_ascii=False, indent=2)}"

    def extract_node_content(self, line: str) -> Optional[str]:
        """Extract node content，Remove timestamp、Node name and other prefixes"""
        content = line
        


        match_old = re.search(r'\[\d{2}:\d{2}:\d{2}\]\s*(.+)', content)
        if match_old:
            content = match_old.group(1).strip()
        else:

            match_new = re.search(r'\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d{3}\s*\|\s*[A-Z]+\s*\|\s*[^|]+?\s*-\s*(.+)', content)
            if match_new:
                content = match_new.group(1).strip()
        
        if not content:
            return line.strip()
        

        content = re.sub(r'^\[.*?\]\s*', '', content)
        

        while re.match(r'^\[.*?\]\s*', content):
            content = re.sub(r'^\[.*?\]\s*', '', content)
        

        prefixes_to_remove = [
            "First summary: ",
            "Reflection and summary: ",
            "Cleaned output: "
        ]
        
        for prefix in prefixes_to_remove:
            if content.startswith(prefix):
                content = content[len(prefix):]
                break
        

        app_names = ['INSIGHT', 'MEDIA', 'QUERY']
        for app_name in app_names:

            content = re.sub(rf'^{app_name}\s+', '', content, flags=re.IGNORECASE)
        

        content = re.sub(r'\s+', ' ', content)
        
        return content.strip()
   
    def get_file_size(self, file_path: Path) -> int:
        """Get file size"""
        try:
            return file_path.stat().st_size if file_path.exists() else 0
        except Exception:
            return 0
   
    def get_file_line_count(self, file_path: Path) -> int:
        """Get the number of file lines"""
        try:
            if not file_path.exists():
                return 0
            with open(file_path, 'r', encoding='utf-8') as f:
                return sum(1 for _ in f)
        except Exception:
            return 0
   
    def read_new_lines(self, file_path: Path, app_name: str) -> List[str]:
        """Read new lines in file"""
        new_lines = []
       
        try:
            if not file_path.exists():
                return new_lines
           
            current_size = self.get_file_size(file_path)
            last_position = self.file_positions.get(app_name, 0)
           

            if current_size < last_position:
                last_position = 0

                self.capturing_json[app_name] = False
                self.json_buffer[app_name] = []
                self.in_error_block[app_name] = False
           
            if current_size > last_position:
                with open(file_path, 'r', encoding='utf-8') as f:
                    f.seek(last_position)
                    new_content = f.read()
                    new_lines = new_content.split('\n')
                   

                    self.file_positions[app_name] = f.tell()
                   

                    new_lines = [line.strip() for line in new_lines if line.strip()]
                   
        except Exception as e:
            logger.exception(f"ForumEngine: read{app_name}Log failed: {e}")
       
        return new_lines
   
    def process_lines_for_json(self, lines: List[str], app_name: str) -> List[str]:
        """Process rows to capture multi-line JSON content
        
        Implement ERROR block filtering：If you encounter ERROR level logs，Refuse to process until the next INFO level log is encountered
        """
        captured_contents = []
        

        if app_name not in self.capturing_json:
            self.capturing_json[app_name] = False
            self.json_buffer[app_name] = []
        if app_name not in self.in_error_block:
            self.in_error_block[app_name] = False
        
        for line in lines:
            if not line.strip():
                continue
            

            log_level = self.get_log_level(line)
            if log_level == 'ERROR':

                self.in_error_block[app_name] = True

                if self.capturing_json[app_name]:
                    self.capturing_json[app_name] = False
                    self.json_buffer[app_name] = []

                continue
            elif log_level == 'INFO':

                self.in_error_block[app_name] = False

            

            if self.in_error_block[app_name]:

                if self.capturing_json[app_name]:
                    self.capturing_json[app_name] = False
                    self.json_buffer[app_name] = []

                continue
                

            is_target = self.is_target_log_line(line)
            is_json_start = self.is_json_start_line(line)
            


            if is_target and is_json_start:

                self.capturing_json[app_name] = True
                self.json_buffer[app_name] = [line]
                self.json_start_line[app_name] = line
                

                if line.strip().endswith("}"):

                    content = self.extract_json_content([line])
                    if content:

                        clean_content = self._clean_content_tags(content, app_name)
                        captured_contents.append(f"{clean_content}")
                    self.capturing_json[app_name] = False
                    self.json_buffer[app_name] = []
                    
            elif is_target and self.is_valuable_content(line):

                clean_content = self._clean_content_tags(self.extract_node_content(line), app_name)
                captured_contents.append(f"{clean_content}")
                    
            elif self.capturing_json[app_name]:

                self.json_buffer[app_name].append(line)
                


                cleaned_line = line.strip()

                cleaned_line = re.sub(r'^\[\d{2}:\d{2}:\d{2}\]\s*', '', cleaned_line)

                cleaned_line = re.sub(r'^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d{3}\s*\|\s*[A-Z]+\s*\|\s*[^|]+?\s*-\s*', '', cleaned_line)
                cleaned_line = cleaned_line.strip()
                

                if cleaned_line == "}" or cleaned_line == "] }":

                    content = self.extract_json_content(self.json_buffer[app_name])
                    if content:

                        clean_content = self._clean_content_tags(content, app_name)
                        captured_contents.append(f"{clean_content}")
                    

                    self.capturing_json[app_name] = False
                    self.json_buffer[app_name] = []
        
        return captured_contents
    
    def _trigger_host_speech(self):
        """Trigger the host to speak（Synchronous execution）"""
        if not HOST_AVAILABLE or self.is_host_generating:
            return
        
        try:

            self.is_host_generating = True
            

            recent_speeches = self.agent_speeches_buffer[:5]
            if len(recent_speeches) < 5:
                self.is_host_generating = False
                return
            
            logger.info("ForumEngine: Generating moderator's speech...")
            

            host_speech = generate_host_speech(recent_speeches) if generate_host_speech else None
            
            if host_speech:

                self.write_to_forum_log(host_speech, "HOST")
                logger.info("ForumEngine: The moderator's speech has been recorded")
                

                self.agent_speeches_buffer = self.agent_speeches_buffer[5:]
            else:
                logger.error("ForumEngine: Moderator speech generation failed")
            

            self.is_host_generating = False
                
        except Exception as e:
            logger.exception(f"ForumEngine: Error when triggering moderator to speak: {e}")
            self.is_host_generating = False
    
    def _clean_content_tags(self, content: str, app_name: str) -> str:
        """Clean up duplicate tags and redundant prefixes in content"""
        if not content:
            return content
            


        all_app_names = ['INSIGHT', 'MEDIA', 'QUERY']
        
        for name in all_app_names:

            content = re.sub(rf'\[{name}\]\s*', '', content, flags=re.IGNORECASE)

            content = re.sub(rf'^{name}\s+', '', content, flags=re.IGNORECASE)
        

        content = re.sub(r'^\[.*?\]\s*', '', content)
        

        content = re.sub(r'\s+', ' ', content)
        
        return content.strip()
   
    def monitor_logs(self):
        """Intelligent monitoring log files"""
        logger.info("ForumEngine: Forum is being created...")
       

        for app_name, log_file in self.monitored_logs.items():
            self.file_line_counts[app_name] = self.get_file_line_count(log_file)
            self.file_positions[app_name] = self.get_file_size(log_file)
            self.capturing_json[app_name] = False
            self.json_buffer[app_name] = []
            self.in_error_block[app_name] = False

       
        while self.is_monitoring:
            try:

                any_growth = False
                any_shrink = False
                captured_any = False
               

                for app_name, log_file in self.monitored_logs.items():
                    current_lines = self.get_file_line_count(log_file)
                    previous_lines = self.file_line_counts.get(app_name, 0)
                   
                    if current_lines > previous_lines:
                        any_growth = True

                        new_lines = self.read_new_lines(log_file, app_name)
                       

                        if not self.is_searching:
                            for line in new_lines:

                                if line.strip() and self.is_target_log_line(line):

                                    if 'FirstSummaryNode' in line or 'Generating first paragraph summary' in line:
                                        logger.info(f"ForumEngine: exist{app_name}The first forum post was detected.")
                                        self.is_searching = True
                                        self.search_inactive_count = 0

                                        self.clear_forum_log()
                                        break
                       

                        if self.is_searching:

                            captured_contents = self.process_lines_for_json(new_lines, app_name)
                            
                            for content in captured_contents:

                                source_tag = app_name.upper()
                                self.write_to_forum_log(content, source_tag)
                                event_bus.publish("forum", {"source": source_tag, "content": content})

                                captured_any = True
                                

                                timestamp = datetime.now(timezone.utc).replace(tzinfo=None).strftime('%H:%M:%S')
                                log_line = f"[{timestamp}] [{source_tag}] {content}"
                                self.agent_speeches_buffer.append(log_line)
                                

                                if len(self.agent_speeches_buffer) >= self.host_speech_threshold and not self.is_host_generating:

                                    self._trigger_host_speech()
                   
                    elif current_lines < previous_lines:
                        any_shrink = True


                        self.file_positions[app_name] = self.get_file_size(log_file)

                        self.capturing_json[app_name] = False
                        self.json_buffer[app_name] = []
                        self.in_error_block[app_name] = False
                   

                    self.file_line_counts[app_name] = current_lines
               

                if self.is_searching:
                    if any_shrink:


                        self.is_searching = False
                        self.search_inactive_count = 0

                        self.agent_speeches_buffer = []
                        self.is_host_generating = False

                        end_time = datetime.now(timezone.utc).replace(tzinfo=None).strftime('%Y-%m-%d %H:%M:%S')
                        self.write_to_forum_log(f"=== ForumEngine Forum ends - {end_time} ===", "SYSTEM")

                    elif not any_growth and not captured_any:

                        self.search_inactive_count += 1
                        if self.search_inactive_count >= 7200:
                            logger.info("ForumEngine: long period of inactivity，End forum")
                            self.is_searching = False
                            self.search_inactive_count = 0

                            self.agent_speeches_buffer = []
                            self.is_host_generating = False

                            end_time = datetime.now(timezone.utc).replace(tzinfo=None).strftime('%Y-%m-%d %H:%M:%S')
                            self.write_to_forum_log(f"=== ForumEngine Forum ends - {end_time} ===", "SYSTEM")
                    else:
                        self.search_inactive_count = 0
               

                threading.Event().wait(1)
               
            except Exception as e:
                logger.exception(f"ForumEngine: Error in forum logs: {e}")
                import traceback
                traceback.print_exc()
                threading.Event().wait(2)
       
        logger.info("ForumEngine: Stop forum log file")
   
    def start_monitoring(self):
        """Start smart monitoring"""
        if self.is_monitoring:
            logger.info("ForumEngine: The forum is already running")
            return False
       
        try:

            self.is_monitoring = True
            self.monitor_thread = threading.Thread(target=self.monitor_logs, daemon=True)
            self.monitor_thread.start()
           
            logger.info("ForumEngine: Forum has been started")
            return True
           
        except Exception as e:
            logger.exception(f"ForumEngine: Failed to start forum: {e}")
            self.is_monitoring = False
            return False
   
    def stop_monitoring(self):
        """Stop monitoring"""
        if not self.is_monitoring:
            logger.info("ForumEngine: Forum is not running")
            return
       
        try:
            self.is_monitoring = False
           
            if self.monitor_thread and self.monitor_thread.is_alive():
                self.monitor_thread.join(timeout=2)
           

            end_time = datetime.now(timezone.utc).replace(tzinfo=None).strftime('%Y-%m-%d %H:%M:%S')
            self.write_to_forum_log(f"=== ForumEngine Forum ends - {end_time} ===", "SYSTEM")
           
            logger.info("ForumEngine: Forum has been stopped")
           
        except Exception as e:
            logger.exception(f"ForumEngine: Failed to stop forum: {e}")
   
    def get_forum_log_content(self) -> List[str]:
        """Get the contents of forum.log"""
        try:
            if not self.forum_log_file.exists():
                return []
           
            with open(self.forum_log_file, 'r', encoding='utf-8') as f:
                return [line.rstrip('\n\r') for line in f]
               
        except Exception as e:
            logger.exception(f"ForumEngine: Failed to read forum.log: {e}")
            return []

    def fix_json_string(self, json_text: str) -> str:
        """Fix common issues in JSON strings，Especially unescaped double quotes"""
        try:

            json.loads(json_text)
            return json_text
        except json.JSONDecodeError:
            pass
        


        
        try:


            # ⚡ OPTIMIZATION: Replaced inefficient string concatenation `+=` with `list.append` and `"".join()`
            # to resolve O(N^2) memory reallocation bottleneck when processing large JSON texts.
            fixed_text_parts = []
            i = 0
            in_string = False
            escape_next = False
            
            while i < len(json_text):
                char = json_text[i]
                
                if escape_next:

                    fixed_text_parts.append(char)
                    escape_next = False
                    i += 1
                    continue
                
                if char == '\\':

                    fixed_text_parts.append(char)
                    escape_next = True
                    i += 1
                    continue
                
                if char == '"' and not escape_next:

                    if in_string:


                        next_char_pos = i + 1
                        while next_char_pos < len(json_text) and json_text[next_char_pos].isspace():
                            next_char_pos += 1
                        
                        if next_char_pos < len(json_text):
                            next_char = json_text[next_char_pos]
                            if next_char in [':', ',', '}']:

                                in_string = False
                                fixed_text_parts.append(char)
                            else:

                                fixed_text_parts.append('\\"')
                        else:

                            in_string = False
                            fixed_text_parts.append(char)
                    else:

                        in_string = True
                        fixed_text_parts.append(char)
                else:

                    fixed_text_parts.append(char)
                
                i += 1
            
            fixed_text = "".join(fixed_text_parts)

            try:
                json.loads(fixed_text)
                return fixed_text
            except json.JSONDecodeError:

                return None
                
        except Exception:
            return None


_monitor_instance = None

def get_monitor() -> LogMonitor:
    """Get global monitor instance"""
    global _monitor_instance
    if _monitor_instance is None:
        _monitor_instance = LogMonitor()
    return _monitor_instance

def start_forum_monitoring():
    """Start ForumEngine intelligent monitoring"""
    return get_monitor().start_monitoring()

def stop_forum_monitoring():
    """Stop ForumEngine monitoring"""
    get_monitor().stop_monitoring()

def get_forum_log():
    """Get forum.log content"""
    return get_monitor().get_forum_log_content()