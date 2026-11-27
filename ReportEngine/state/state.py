"""
Report EngineStatus management
Define simplified status data structures during report generation
"""

from dataclasses import dataclass, field
from typing import Dict, Any, Optional
import json
from datetime import datetime, timezone


@dataclass
class ReportMetadata:
    """Simplified reporting metadata"""
    query: str = ""
    template_used: str = ""
    generation_time: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None).isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format"""
        return {
            "query": self.query,
            "template_used": self.template_used,
            "generation_time": self.generation_time,
            "timestamp": self.timestamp
        }


@dataclass 
class ReportState:
    """
    Simplified report status management.

    Store basic task information、enter、Output and metadata for sharing between Agent and Flask layer。
    """

    task_id: str = ""
    query: str = ""
    status: str = "pending"
    

    query_engine_report: str = ""
    media_engine_report: str = ""
    insight_engine_report: str = ""
    forum_logs: str = ""
    

    selected_template: str = ""
    html_content: str = ""
    

    metadata: ReportMetadata = field(default_factory=ReportMetadata)
    
    def __post_init__(self):
        """Post-initialization processing"""
        if not self.task_id:
            self.task_id = f"report_{datetime.now(timezone.utc).replace(tzinfo=None).strftime('%Y%m%d_%H%M%S')}"
        self.metadata.query = self.query
    
    def mark_processing(self):
        """Marked as processing, the background thread starts scheduling the generation process。"""
        self.status = "processing"
    
    def mark_completed(self):
        """Marked as complete, also means `html_content` Already available。"""
        self.status = "completed"
    
    def mark_failed(self, error_message: str = ""):
        """Mark as failed and log the last error message。"""
        self.status = "failed"
        self.error_message = error_message
    
    def is_completed(self) -> bool:
        """Check whether it is completed, including the status is completed and the presence of HTML content。"""
        return self.status == "completed" and bool(self.html_content)
    
    def get_progress(self) -> float:
        """Get the progress percentage, according to the template/Rough estimate of content in two stages。"""
        if self.status == "completed":
            return 100.0
        elif self.status == "processing":

            progress = 0.0
            if self.selected_template:
                progress += 30.0
            if self.html_content:
                progress += 70.0
            return progress
        else:
            return 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format to facilitate serialization to the front end。"""
        return {
            "task_id": self.task_id,
            "query": self.query,
            "status": self.status,
            "progress": self.get_progress(),
            "selected_template": self.selected_template,
            "has_html_content": bool(self.html_content),
            "html_content_length": len(self.html_content) if self.html_content else 0,
            "metadata": self.metadata.to_dict()
        }
    
    def save_to_file(self, file_path: str):
        """Save state to file, exclude HTML body to control size。"""
        try:
            state_data = self.to_dict()

            state_data.pop("html_content", None)
            
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(state_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Failed to save state file: {str(e)}")
    
    @classmethod
    def load_from_file(cls, file_path: str) -> Optional["ReportState"]:
        """Load state from file, restore only key fields for easy debugging。"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            

            state = cls(
                task_id=data.get("task_id", ""),
                query=data.get("query", ""),
                status=data.get("status", "pending"),
                selected_template=data.get("selected_template", "")
            )
            

            metadata_data = data.get("metadata", {})
            state.metadata.template_used = metadata_data.get("template_used", "")
            state.metadata.generation_time = metadata_data.get("generation_time", 0.0)
            
            return state
            
        except Exception as e:
            print(f"Failed to load status file: {str(e)}")
            return None
