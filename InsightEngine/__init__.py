"""
Trend Pulse
A framework-less Trend Pulse AI agent implementation
"""

from .agent import TrendPulseAgent, create_agent
from config import Settings, settings

__version__ = "1.0.0"
__author__ = "Corax CoLAB & Pelle"

__all__ = ["TrendPulseAgent", "create_agent", "settings", "Settings"]
