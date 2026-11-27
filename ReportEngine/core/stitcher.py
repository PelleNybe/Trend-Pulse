"""
Chapter binder: Responsible for merging multiple JSON chapters into the entire IR.

DocumentComposer will inject missing anchors、Unify the order and complete IR-level metadata。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Set

from ..ir import IR_VERSION


class DocumentComposer:
    """
    A simple binder that splices chapters into Document IR.

    effect：
        - Sort chapters by order, supplement the defaultchapterId；
        - Prevent anchor duplication and generate globally unique anchor points；
        - Inject IR version and generate timestamp。
    """

    def __init__(self):
        """Initialize the binder and record used anchor points to avoid duplication"""
        self._seen_anchors: Set[str] = set()

    def build_document(
        self,
        report_id: str,
        metadata: Dict[str, object],
        chapters: List[Dict[str, object]],
    ) -> Dict[str, object]:
        """
        Sort all chapters in order and inject unique anchor points to form the entire IR.

        merge simultaneously metadata/themeTokens/assets，For direct consumption by the renderer.

        parameter:
            report_id: This reportID。
            metadata: Global meta information (title、theme、tocwait）。
            chapters: Chapter payload list.

        return:
            dict: Meet the needs of the rendererDocument IR。
        """

        toc_anchor_map = self._build_toc_anchor_map(metadata)

        ordered = sorted(chapters, key=lambda c: c.get("order", 0))
        for idx, chapter in enumerate(ordered, start=1):
            chapter.setdefault("chapterId", f"S{idx}")


            chapter_id = chapter.get("chapterId")
            anchor = (
                toc_anchor_map.get(chapter_id) or
                chapter.get("anchor") or
                f"section-{idx}"
            )
            chapter["anchor"] = self._ensure_unique_anchor(anchor)
            chapter.setdefault("order", idx * 10)
            if chapter.get("isErrorFallback"):
                self._ensure_heading_block(chapter)

        document = {
            "version": IR_VERSION,
            "reportId": report_id,
            "metadata": {
                **metadata,
                "generatedAt": metadata.get("generatedAt")
                or datetime.now(timezone.utc).replace(tzinfo=None).isoformat() + "Z",
            },
            "themeTokens": metadata.get("themeTokens", {}),
            "chapters": ordered,
            "assets": metadata.get("assets", {}),
        }
        return document

    def _ensure_unique_anchor(self, anchor: str) -> str:
        """If there are duplicate anchor points, append the sequence number to ensure global uniqueness.。"""
        base = anchor
        counter = 2
        while anchor in self._seen_anchors:
            anchor = f"{base}-{counter}"
            counter += 1
        self._seen_anchors.add(anchor)
        return anchor

    def _build_toc_anchor_map(self, metadata: Dict[str, object]) -> Dict[str, str]:
        """
        frommetadata.toc.customEntriesConstruct a mapping from chapterId to anchor.

        parameter:
            metadata: Document meta information.

        return:
            dict: chapterId -> anchor mapping。
        """
        toc_config = metadata.get("toc") or {}
        custom_entries = toc_config.get("customEntries") or []
        anchor_map = {}

        for entry in custom_entries:
            if isinstance(entry, dict):
                chapter_id = entry.get("chapterId")
                anchor = entry.get("anchor")
                if chapter_id and anchor:
                    anchor_map[chapter_id] = anchor

        return anchor_map

    def _ensure_heading_block(self, chapter: Dict[str, object]) -> None:
        """Ensure that fallback chapters still have content available for the table of contentsheading block。"""
        blocks = chapter.get("blocks")
        if isinstance(blocks, list):
            for block in blocks:
                if isinstance(block, dict) and block.get("type") == "heading":
                    return
        heading = {
            "type": "heading",
            "level": 2,
            "text": chapter.get("title") or "Chapter Overview",
            "anchor": chapter.get("anchor"),
        }
        if isinstance(blocks, list):
            blocks.insert(0, heading)
        else:
            chapter["blocks"] = [heading]


__all__ = ["DocumentComposer"]
