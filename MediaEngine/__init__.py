"""
Trend Pulse
A framework-less Trend Pulse AI agent implementation
"""

from .agent import TrendPulseAgent, AnspireSearchAgent, create_agent
from config import Settings

__version__ = "1.0.0"
__author__ = "Corax CoLAB & Pelle"

__all__ = ["TrendPulseAgent", "AnspireSearchAgent", "create_agent", "Settings"]
