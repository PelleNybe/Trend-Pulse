"""
Report EngineCollection of core tools.

This package encapsulates template slicing、The three basic capabilities of chapter storage and chapter binding are:
All upper-level nodes will reuse these tools to ensure a consistent structure.。
"""

from .template_parser import TemplateSection, parse_template_sections
from .chapter_storage import ChapterStorage
from .stitcher import DocumentComposer

__all__ = [
    "TemplateSection",
    "parse_template_sections",
    "ChapterStorage",
    "DocumentComposer",
]
