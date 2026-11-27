"""
Report Engine。

An intelligent report generation AI agent implementation，Aggregate Query/Media/Insight three sub-engines
Markdown and forum discussion，Finally implemented structured HTML report。
"""

from .agent import ReportAgent, create_agent

__version__ = "1.0.0"
__author__ = "Corax CoLAB & Pelle"

__all__ = ["ReportAgent", "create_agent"]
