"""
Chapter-level JSON structure validator。

LLMAfter generating IR by chapter，Need to undergo strict verification before placement and binding，to avoid
Structural collapse of rendering period。This module implements lightweight Python verification logic，
Quickly locate errors without relying on the jsonschema library。
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from .schema import (
    ALLOWED_BLOCK_TYPES,
    ALLOWED_INLINE_MARKS,
    ENGINE_AGENT_TITLES,
    IR_VERSION,
)


class IRValidator:
    """
    Chapter IR Structure Verifier。

    illustrate：
        - validate_chapterReturn (whether passed, error list)
        - Error location uses path syntax，The following content covers all block types such as paragraph/list/table/swot/pest/widget one by one
    """

    def __init__(self, schema_version: str = IR_VERSION):
        """Record the current Schema version，Facilitate the coexistence of multiple versions in the future"""
        self.schema_version = schema_version



    def validate_chapter(self, chapter: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """Verify the required fields and block structure of a single chapter object"""
        errors: List[str] = []
        if not isinstance(chapter, dict):
            return False, ["chapterMust be an object"]

        for field in ("chapterId", "title", "anchor", "order", "blocks"):
            if field not in chapter:
                errors.append(f"missing chapter.{field}")

        if not isinstance(chapter.get("blocks"), list) or not chapter.get("blocks"):
            errors.append("chapter.blocksMust be a non-empty array")
            return False, errors

        blocks = chapter.get("blocks", [])
        for idx, block in enumerate(blocks):
            self._validate_block(block, f"blocks[{idx}]", errors)

        return len(errors) == 0, errors



    def _validate_block(self, block: Any, path: str, errors: List[str]):
        """Call different validators based on block type"""
        if not isinstance(block, dict):
            errors.append(f"{path} Must be an object")
            return

        block_type = block.get("type")
        if block_type not in ALLOWED_BLOCK_TYPES:
            errors.append(f"{path}.type not supported: {block_type}")
            return

        validator = getattr(self, f"_validate_{block_type}_block", None)
        if validator:
            validator(block, path, errors)

    def _validate_heading_block(self, block: Dict[str, Any], path: str, errors: List[str]):
        """headingMust havelevel/text/anchor"""
        if "level" not in block or not isinstance(block["level"], int):
            errors.append(f"{path}.level Must be an integer")
        if "text" not in block:
            errors.append(f"{path}.text Missing")
        if "anchor" not in block:
            errors.append(f"{path}.anchor Missing")

    def _validate_paragraph_block(self, block: Dict[str, Any], path: str, errors: List[str]):
        """paragraphNeed to be non-nullinlines，and verify them one by one"""
        inlines = block.get("inlines")
        if not isinstance(inlines, list) or not inlines:
            errors.append(f"{path}.inlines Must be a non-empty array")
            return
        for idx, run in enumerate(inlines):
            self._validate_inline_run(run, f"{path}.inlines[{idx}]", errors)

    def _validate_list_block(self, block: Dict[str, Any], path: str, errors: List[str]):
        """The list needs to declare listType and each item is a block array"""
        if block.get("listType") not in {"ordered", "bullet", "task"}:
            errors.append(f"{path}.listType Illegal value")
        items = block.get("items")
        if not isinstance(items, list) or not items:
            errors.append(f"{path}.items Must be a non-empty list")
            return
        for i, item in enumerate(items):
            if not isinstance(item, list):
                errors.append(f"{path}.items[{i}] Must be an array of blocks")
                continue
            for j, sub_block in enumerate(item):
                self._validate_block(sub_block, f"{path}.items[{i}][{j}]", errors)

    def _validate_table_block(self, block: Dict[str, Any], path: str, errors: List[str]):
        """Form is requiredrows/cells/blocks，Verify cell contents recursively"""
        rows = block.get("rows")
        if not isinstance(rows, list) or not rows:
            errors.append(f"{path}.rows Must be a non-empty array")
            return
        for r_idx, row in enumerate(rows):
            cells = row.get("cells") if isinstance(row, dict) else None
            if not isinstance(cells, list) or not cells:
                errors.append(f"{path}.rows[{r_idx}].cells Must be a non-empty array")
                continue
            for c_idx, cell in enumerate(cells):
                if not isinstance(cell, dict):
                    errors.append(f"{path}.rows[{r_idx}].cells[{c_idx}] Must be an object")
                    continue
                blocks = cell.get("blocks")
                if not isinstance(blocks, list) or not blocks:
                    errors.append(
                        f"{path}.rows[{r_idx}].cells[{c_idx}].blocks Must be a non-empty array"
                    )
                    continue
                for b_idx, sub_block in enumerate(blocks):
                    self._validate_block(
                        sub_block,
                        f"{path}.rows[{r_idx}].cells[{c_idx}].blocks[{b_idx}]",
                        errors,
                    )

    def _validate_swotTable_block(self, block: Dict[str, Any], path: str, errors: List[str]):
        """SWOTThe table provides at least one of the four quadrants，Each quadrant is an array of entries"""
        quadrants = ("strengths", "weaknesses", "opportunities", "threats")
        if not any(block.get(name) is not None for name in quadrants):
            errors.append(f"{path} Need to contain at least one of strengths/weaknesses/opportunities/threats")
        for name in quadrants:
            entries = block.get(name)
            if entries is None:
                continue
            if not isinstance(entries, list):
                errors.append(f"{path}.{name} Must be an array")
                continue
            for idx, entry in enumerate(entries):
                self._validate_swot_item(entry, f"{path}.{name}[{idx}]", errors)


    ALLOWED_IMPACT_VALUES = {"Low", "medium low", "middle", "Middle to high", "high", "extremely high"}

    def _validate_swot_item(self, item: Any, path: str, errors: List[str]):
        """Individual SWOT entries support strings or objects with fields"""
        if isinstance(item, str):
            if not item.strip():
                errors.append(f"{path} Cannot be an empty string")
            return
        if not isinstance(item, dict):
            errors.append(f"{path} Must be a string or object")
            return
        title = None
        for key in ("title", "label", "text", "detail", "description"):
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                title = value
                break
        if title is None:
            errors.append(f"{path} Missing text fields such as title/label/text/description")


        impact = item.get("impact")
        if impact is not None:
            if not isinstance(impact, str) or impact not in self.ALLOWED_IMPACT_VALUES:
                errors.append(
                    f"{path}.impact Only impact ratings are allowed（Low/Medium Low/Medium/Medium High/High/Extremely High），"
                    f"current value: {impact}；If you need a detailed description, please write the detail field"
                )


        # score = item.get("score")
        # if score is not None:
        #     valid_score = False
        #     if isinstance(score, (int, float)):
        #         valid_score = 0 <= score <= 10
        #     elif isinstance(score, str):

        #         try:
        #             numeric_score = float(score)
        #             valid_score = 0 <= numeric_score <= 10
        #         except ValueError:
        #             valid_score = False
        #     if not valid_score:
        #         errors.append(

        #         )

    def _validate_blockquote_block(
        self, block: Dict[str, Any], path: str, errors: List[str]
    ):
        """A reference block requires at least one subblock"""
        inner = block.get("blocks")
        if not isinstance(inner, list) or not inner:
            errors.append(f"{path}.blocks Must be a non-empty array")
            return
        for idx, sub_block in enumerate(inner):
            self._validate_block(sub_block, f"{path}.blocks[{idx}]", errors)

    def _validate_engineQuote_block(
        self, block: Dict[str, Any], path: str, errors: List[str]
    ):
        """Single-engine speech blocks must be marked engine and include sub-blocks"""
        engine_raw = block.get("engine")
        engine = engine_raw.lower() if isinstance(engine_raw, str) else None
        if engine not in {"insight", "media", "query"}:
            errors.append(f"{path}.engine Illegal value: {engine_raw}")
        title = block.get("title")
        expected_title = ENGINE_AGENT_TITLES.get(engine) if engine else None
        if title is None:
            errors.append(f"{path}.title Missing")
        elif not isinstance(title, str):
            errors.append(f"{path}.title Must be a string")
        elif expected_title and title != expected_title:
            errors.append(
                f"{path}.title Technology media and industry reports paint a promising picture of technological empowerment，Use the corresponding Agent name: {expected_title}"
            )
        inner = block.get("blocks")
        if not isinstance(inner, list) or not inner:
            errors.append(f"{path}.blocks Must be a non-empty array")
            return
        for idx, sub_block in enumerate(inner):
            sub_path = f"{path}.blocks[{idx}]"
            if not isinstance(sub_block, dict):
                errors.append(f"{sub_path} Must be an object")
                continue
            if sub_block.get("type") != "paragraph":
                errors.append(f"{sub_path}.type only allowed paragraph")
                continue

            inlines = sub_block.get("inlines")
            if not isinstance(inlines, list) or not inlines:
                errors.append(f"{sub_path}.inlines Must be a non-empty array")
                continue
            for ridx, run in enumerate(inlines):
                self._validate_inline_run(run, f"{sub_path}.inlines[{ridx}]", errors)
                if not isinstance(run, dict):
                    continue
                marks = run.get("marks") or []
                if not isinstance(marks, list):
                    errors.append(f"{sub_path}.inlines[{ridx}].marks Must be an array")
                    continue
                for midx, mark in enumerate(marks):
                    mark_type = mark.get("type") if isinstance(mark, dict) else None
                    if mark_type not in {"bold", "italic"}:
                        errors.append(
                            f"{sub_path}.inlines[{ridx}].marks[{midx}].type only allowed bold/italic"
                        )

    def _validate_callout_block(self, block: Dict[str, Any], path: str, errors: List[str]):
        """calloutNeed to declaretone，and has at least one childblock"""
        tone = block.get("tone")
        if tone not in {"info", "warning", "success", "danger"}:
            errors.append(f"{path}.tone Illegal value: {tone}")
        blocks = block.get("blocks")
        if not isinstance(blocks, list) or not blocks:
            errors.append(f"{path}.blocks Must be a non-empty array")
            return
        for idx, sub_block in enumerate(blocks):
            self._validate_block(sub_block, f"{path}.blocks[{idx}]", errors)

    def _validate_kpiGrid_block(self, block: Dict[str, Any], path: str, errors: List[str]):
        """KPICard needs to be non-emptyitems，Each item containslabel/value"""
        items = block.get("items")
        if not isinstance(items, list) or not items:
            errors.append(f"{path}.items Must be a non-empty array")
            return
        for idx, item in enumerate(items):
            if not isinstance(item, dict):
                errors.append(f"{path}.items[{idx}] Must be an object")
                continue
            if "label" not in item or "value" not in item:
                errors.append(f"{path}.items[{idx}] Requires label andvalue")

    def _validate_widget_block(self, block: Dict[str, Any], path: str, errors: List[str]):
        """widgetMust declarewidgetId/type，and provide data or data references"""
        if "widgetId" not in block:
            errors.append(f"{path}.widgetId Missing")
        if "widgetType" not in block:
            errors.append(f"{path}.widgetType Missing")
        if "data" not in block and "dataRef" not in block:
            errors.append(f"{path} Requires one of data or dataRef")

    def _validate_code_block(self, block: Dict[str, Any], path: str, errors: List[str]):
        """code blockAt least there must becontent"""
        if "content" not in block:
            errors.append(f"{path}.content Missing")

    def _validate_math_block(self, block: Dict[str, Any], path: str, errors: List[str]):
        """Math block requires latex field"""
        if "latex" not in block:
            errors.append(f"{path}.latex Missing")

    def _validate_figure_block(
        self, block: Dict[str, Any], path: str, errors: List[str]
    ):
        """figureAn img object is required and must contain at leastsrc"""
        img = block.get("img")
        if not isinstance(img, dict):
            errors.append(f"{path}.img Must be an object")
            return
        if "src" not in img:
            errors.append(f"{path}.img.src Missing")

    def _validate_inline_run(
        self, run: Any, path: str, errors: List[str]
    ):
        """Verify the legality of inline run and marks in paragraph"""
        if not isinstance(run, dict):
            errors.append(f"{path} Must be an object")
            return
        if "text" not in run:
            errors.append(f"{path}.text Missing")
        marks = run.get("marks", [])
        if marks is None:
            return
        if not isinstance(marks, list):
            errors.append(f"{path}.marks Must be an array")
            return
        for m_idx, mark in enumerate(marks):
            if not isinstance(mark, dict):
                errors.append(f"{path}.marks[{m_idx}] Must be an object")
                continue
            m_type = mark.get("type")
            if m_type not in ALLOWED_INLINE_MARKS:
                errors.append(f"{path}.marks[{m_idx}].type not supported: {m_type}")


__all__ = ["IRValidator"]
