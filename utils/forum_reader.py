"""
ForumLogRead tool
for latest HOST statements in Readforum.log
"""

import re
import collections
from pathlib import Path
from typing import Optional, List, Dict
from loguru import logger

def get_latest_host_speech(log_dir: str = "logs") -> Optional[str]:
    """
    Get the latest HOST statement in forum.log
    
    Args:
        log_dir: log directory path
        
    Returns:
        The latest HOST speech content，If not returnNone
    """
    try:
        forum_log_path = Path(log_dir) / "forum.log"
        
        if not forum_log_path.exists():
            logger.debug("forum.logFile does not exist")
            return None
            
        with open(forum_log_path, 'r', encoding='utf-8', errors='ignore') as f:
            lines = list(collections.deque(f, maxlen=5000))
        

        host_speech = None
        for line in reversed(lines):

            match = re.match(r'\[(\d{2}:\d{2}:\d{2})\]\s*\[HOST\]\s*(.+)', line)
            if match:
                _, content = match.groups()

                host_speech = content.replace('\\n', '\n').strip()
                break
        
        if host_speech:
            logger.info(f"Find the latest HOST statement，length: {len(host_speech)}character")
        else:
            logger.debug("Not foundHOSTspeak")
            
        return host_speech
        
    except Exception as e:
        logger.error(f"Readforum.logfail: {str(e)}")
        return None


def get_all_host_speeches(log_dir: str = "logs") -> List[Dict[str, str]]:
    """
    Get all HOST comments in forum.log
    
    Args:
        log_dir: log directory path
        
    Returns:
        Contains a list of all HOST statements，Each element is a dictionary containing timestamp and content
    """
    try:
        forum_log_path = Path(log_dir) / "forum.log"
        
        if not forum_log_path.exists():
            logger.debug("forum.logFile does not exist")
            return []
            
        host_speeches = []
        with open(forum_log_path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                match = re.match(r'\[(\d{2}:\d{2}:\d{2})\]\s*\[HOST\]\s*(.+)', line)
                if match:
                    timestamp, content = match.groups()

                    content = content.replace('\\n', '\n').strip()
                    host_speeches.append({
                        'timestamp': timestamp,
                        'content': content
                    })
        
        logger.info(f"turn up{len(host_speeches)}HOST statement")
        return host_speeches
        
    except Exception as e:
        logger.error(f"Readforum.logfail: {str(e)}")
        return []


def get_recent_agent_speeches(log_dir: str = "logs", limit: int = 5) -> List[Dict[str, str]]:
    """
    Get the latest Agent statement in forum.log（Not includedHOST）
    
    Args:
        log_dir: Log directory path
        limit: the maximum number of comments returned
        
    Returns:
        Contains a list of recent Agent statements
    """
    try:
        forum_log_path = Path(log_dir) / "forum.log"
        
        if not forum_log_path.exists():
            return []
            
        with open(forum_log_path, 'r', encoding='utf-8', errors='ignore') as f:
            lines = list(collections.deque(f, maxlen=5000))
        
        agent_speeches = []
        for line in reversed(lines):

            match = re.match(r'\[(\d{2}:\d{2}:\d{2})\]\s*\[(INSIGHT|MEDIA|QUERY)\]\s*(.+)', line)
            if match:
                timestamp, agent, content = match.groups()

                content = content.replace('\\n', '\n').strip()
                agent_speeches.append({
                    'timestamp': timestamp,
                    'agent': agent,
                    'content': content
                })
                if len(agent_speeches) >= limit:
                    break
        
        agent_speeches.reverse()
        return agent_speeches
        
    except Exception as e:
        logger.error(f"Readforum.logfail: {str(e)}")
        return []


def format_host_speech_for_prompt(host_speech: str) -> str:
    """
    Format HOST speech，Used to add to prompt
    
    Args:
        host_speech: HOST speech content
        
    Returns:
        Formatted content
    """
    if not host_speech:
        return ""
    
    return f"""

The following is the forum moderator’s latest summary and guidance on each Agent’s discussion，Please refer to the views and suggestions contained therein：

{host_speech}

---
"""
