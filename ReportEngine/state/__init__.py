"""
Report EngineStatus management module.

Export ReportState/ReportMetadata，For sharing between Agent and Flask interface。
"""

from .state import ReportState, ReportMetadata

__all__ = ["ReportState", "ReportMetadata"]
