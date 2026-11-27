#!/usr/bin/env python3
"""
IR Document verification tool.

Command line tool for：
- Scan all charts and tables in a specified JSON file
- Report structural issues and missing data
- Supports automatic repair of common problems
- Support batch processing

How to use:
    python -m ReportEngine.scripts.validate_ir chapter-030-section-3-0.json
    python -m ReportEngine.scripts.validate_ir *.json --fix
    python -m ReportEngine.scripts.validate_ir ./output/ --recursive --fix --verbose
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field


project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from loguru import logger

from ReportEngine.utils.chart_validator import (
    ChartValidator,
    ChartRepairer,
    ValidationResult,
)
from ReportEngine.utils.table_validator import (
    TableValidator,
    TableRepairer,
    TableValidationResult,
)


@dataclass
class BlockIssue:
    """Single block problem"""
    block_type: str
    block_id: str
    path: str
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    is_fixable: bool = False


@dataclass
class DocumentReport:
    """Document Verification Report"""
    file_path: str
    total_blocks: int = 0
    chart_count: int = 0
    table_count: int = 0
    wordcloud_count: int = 0
    issues: List[BlockIssue] = field(default_factory=list)
    fixed_count: int = 0

    @property
    def has_issues(self) -> bool:
        return len(self.issues) > 0

    @property
    def error_count(self) -> int:
        return sum(len(issue.errors) for issue in self.issues)

    @property
    def warning_count(self) -> int:
        return sum(len(issue.warnings) for issue in self.issues)


class IRValidator:
    """IR Document Validator"""

    def __init__(
        self,
        chart_validator: Optional[ChartValidator] = None,
        table_validator: Optional[TableValidator] = None,
        chart_repairer: Optional[ChartRepairer] = None,
        table_repairer: Optional[TableRepairer] = None,
    ):
        self.chart_validator = chart_validator or ChartValidator()
        self.table_validator = table_validator or TableValidator()
        self.chart_repairer = chart_repairer or ChartRepairer(self.chart_validator)
        self.table_repairer = table_repairer or TableRepairer(self.table_validator)

    def validate_document(
        self,
        document: Dict[str, Any],
        file_path: str = "<unknown>",
    ) -> DocumentReport:
        """
        Validate entire document。

        Args:
            document: IR Document data
            file_path: File path (for reporting）

        Returns:
            DocumentReport: Verification report
        """
        report = DocumentReport(file_path=file_path)


        chapters = document.get("chapters", [])
        for chapter_idx, chapter in enumerate(chapters):
            if not isinstance(chapter, dict):
                continue

            chapter_id = chapter.get("chapterId", f"chapter-{chapter_idx}")
            blocks = chapter.get("blocks", [])

            self._validate_blocks(
                blocks,
                f"chapters[{chapter_idx}].blocks",
                chapter_id,
                report,
            )

        return report

    def _validate_blocks(
        self,
        blocks: List[Any],
        path: str,
        chapter_id: str,
        report: DocumentReport,
    ):
        """Recursively verify a list of blocks"""
        if not isinstance(blocks, list):
            return

        for idx, block in enumerate(blocks):
            if not isinstance(block, dict):
                continue

            report.total_blocks += 1
            block_path = f"{path}[{idx}]"
            block_type = block.get("type", "")
            block_id = block.get("widgetId") or block.get("id") or f"block-{idx}"


            if block_type == "widget":
                widget_type = (block.get("widgetType") or "").lower()
                if "chart.js" in widget_type:
                    report.chart_count += 1
                    self._validate_chart(block, block_path, block_id, report)
                elif "wordcloud" in widget_type:
                    report.wordcloud_count += 1
                    self._validate_wordcloud(block, block_path, block_id, report)

            elif block_type == "table":
                report.table_count += 1
                self._validate_table(block, block_path, block_id, report)


            nested_blocks = block.get("blocks")
            if isinstance(nested_blocks, list):
                self._validate_blocks(nested_blocks, f"{block_path}.blocks", chapter_id, report)


            if block_type == "table":
                rows = block.get("rows", [])
                for row_idx, row in enumerate(rows):
                    if isinstance(row, dict):
                        cells = row.get("cells", [])
                        for cell_idx, cell in enumerate(cells):
                            if isinstance(cell, dict):
                                cell_blocks = cell.get("blocks", [])
                                self._validate_blocks(
                                    cell_blocks,
                                    f"{block_path}.rows[{row_idx}].cells[{cell_idx}].blocks",
                                    chapter_id,
                                    report,
                                )


            if block_type == "list":
                items = block.get("items", [])
                for item_idx, item in enumerate(items):
                    if isinstance(item, list):
                        self._validate_blocks(
                            item,
                            f"{block_path}.items[{item_idx}]",
                            chapter_id,
                            report,
                        )

    def _validate_chart(
        self,
        block: Dict[str, Any],
        path: str,
        block_id: str,
        report: DocumentReport,
    ):
        """Validate chart"""
        result = self.chart_validator.validate(block)

        if not result.is_valid or result.warnings:
            issue = BlockIssue(
                block_type="chart",
                block_id=block_id,
                path=path,
                errors=result.errors,
                warnings=result.warnings,
                is_fixable=result.has_critical_errors(),
            )
            report.issues.append(issue)

    def _validate_table(
        self,
        block: Dict[str, Any],
        path: str,
        block_id: str,
        report: DocumentReport,
    ):
        """Verification form"""
        result = self.table_validator.validate(block)

        if not result.is_valid or result.warnings or result.nested_cells_detected:
            issue = BlockIssue(
                block_type="table",
                block_id=block_id,
                path=path,
                errors=result.errors,
                warnings=result.warnings,
                is_fixable=result.nested_cells_detected or result.has_critical_errors(),
            )


            if result.nested_cells_detected:
                issue.warnings.insert(0, "Nested cells structure detected (LLM common error）")


            if result.empty_cells_count > 0:
                issue.warnings.append(
                    f"Number of empty cells: {result.empty_cells_count}/{result.total_cells_count}"
                )

            report.issues.append(issue)

    def _validate_wordcloud(
        self,
        block: Dict[str, Any],
        path: str,
        block_id: str,
        report: DocumentReport,
    ):
        """Verify word cloud"""
        errors: List[str] = []
        warnings: List[str] = []


        data = block.get("data")
        props = block.get("props", {})

        words_found = False
        words_count = 0


        data_paths = [
            ("data.words", data.get("words") if isinstance(data, dict) else None),
            ("data.items", data.get("items") if isinstance(data, dict) else None),
            ("data", data if isinstance(data, list) else None),
            ("props.words", props.get("words") if isinstance(props, dict) else None),
            ("props.items", props.get("items") if isinstance(props, dict) else None),
            ("props.data", props.get("data") if isinstance(props, dict) else None),
        ]

        for path_name, value in data_paths:
            if isinstance(value, list) and len(value) > 0:
                words_found = True
                words_count = len(value)


                for idx, item in enumerate(value[:5]):
                    if isinstance(item, dict):
                        word = item.get("word") or item.get("text") or item.get("label")
                        weight = item.get("weight") or item.get("value")
                        if not word:
                            warnings.append(f"{path_name}[{idx}] Lack word/text/label Field")
                        if weight is None:
                            warnings.append(f"{path_name}[{idx}] Lack weight/value Field")
                    elif not isinstance(item, (str, list, tuple)):
                        warnings.append(f"{path_name}[{idx}] Incorrect format")

                break

        if not words_found:
            errors.append("Word cloud data is missing: not present data.words, data.items, props.words Wait for path to find valid data")
        elif words_count == 0:
            warnings.append("Word cloud data is empty")

        if errors or warnings:
            issue = BlockIssue(
                block_type="wordcloud",
                block_id=block_id,
                path=path,
                errors=errors,
                warnings=warnings,
                is_fixable=False,
            )
            report.issues.append(issue)

    def repair_document(
        self,
        document: Dict[str, Any],
        report: DocumentReport,
    ) -> Tuple[Dict[str, Any], int]:
        """
        Fix issues in documentation。

        Args:
            document: IR Document data
            report: Verification report

        Returns:
            Tuple[Dict[str, Any], int]: (Repaired document, Number of repairs)
        """
        fixed_count = 0


        chapters = document.get("chapters", [])
        for chapter in chapters:
            if not isinstance(chapter, dict):
                continue

            blocks = chapter.get("blocks", [])
            chapter["blocks"], chapter_fixed = self._repair_blocks(blocks)
            fixed_count += chapter_fixed

        return document, fixed_count

    def _repair_blocks(
        self,
        blocks: List[Any],
    ) -> Tuple[List[Any], int]:
        """Recursively repair blocks list"""
        if not isinstance(blocks, list):
            return blocks, 0

        fixed_count = 0
        repaired_blocks: List[Any] = []

        for block in blocks:
            if not isinstance(block, dict):
                repaired_blocks.append(block)
                continue

            block_type = block.get("type", "")


            if block_type == "table":
                result = self.table_repairer.repair(block)
                if result.has_changes():
                    block = result.repaired_block
                    fixed_count += 1
                    logger.info(f"Repair table: {result.changes}")


            elif block_type == "widget":
                widget_type = (block.get("widgetType") or "").lower()
                if "chart.js" in widget_type:
                    result = self.chart_repairer.repair(block)
                    if result.has_changes():
                        block = result.repaired_block
                        fixed_count += 1
                        logger.info(f"Repair chart: {result.changes}")


            nested_blocks = block.get("blocks")
            if isinstance(nested_blocks, list):
                block["blocks"], nested_fixed = self._repair_blocks(nested_blocks)
                fixed_count += nested_fixed


            if block_type == "table":
                rows = block.get("rows", [])
                for row in rows:
                    if isinstance(row, dict):
                        cells = row.get("cells", [])
                        for cell in cells:
                            if isinstance(cell, dict):
                                cell_blocks = cell.get("blocks", [])
                                cell["blocks"], cell_fixed = self._repair_blocks(cell_blocks)
                                fixed_count += cell_fixed


            if block_type == "list":
                items = block.get("items", [])
                for i, item in enumerate(items):
                    if isinstance(item, list):
                        items[i], item_fixed = self._repair_blocks(item)
                        fixed_count += item_fixed

            repaired_blocks.append(block)

        return repaired_blocks, fixed_count


def print_report(report: DocumentReport, verbose: bool = False):
    """Print verification report"""
    print(f"\n{'=' * 60}")
    print(f"document: {report.file_path}")
    print(f"{'=' * 60}")

    print(f"\n📊 statistics:")
    print(f"  - total blocks: {report.total_blocks}")
    print(f"  - Number of charts: {report.chart_count}")
    print(f"  - Number of tables: {report.table_count}")
    print(f"  - word cloud quantity: {report.wordcloud_count}")

    if report.has_issues:
        print(f"\n⚠️  Discover {len(report.issues)} questions:")
        print(f"  - mistake: {report.error_count}")
        print(f"  - warn: {report.warning_count}")

        if verbose:
            for issue in report.issues:
                print(f"\n  [{issue.block_type}] {issue.block_id}")
                print(f"    path: {issue.path}")
                if issue.errors:
                    for error in issue.errors:
                        print(f"    ❌ {error}")
                if issue.warnings:
                    for warning in issue.warnings:
                        print(f"    ⚠️  {warning}")
                if issue.is_fixable:
                    print(f"    🔧 Can be repaired automatically")
    else:
        print(f"\n✅ No problem found")

    if report.fixed_count > 0:
        print(f"\n🔧 Fixed {report.fixed_count} questions")


def validate_file(
    file_path: Path,
    validator: IRValidator,
    fix: bool = False,
    verbose: bool = False,
) -> DocumentReport:
    """Verify a single file"""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            document = json.load(f)
    except json.JSONDecodeError as e:
        logger.error(f"JSON Parse error: {file_path}: {e}")
        report = DocumentReport(file_path=str(file_path))
        report.issues.append(BlockIssue(
            block_type="document",
            block_id="root",
            path="",
            errors=[f"JSON Parse error: {e}"],
        ))
        return report
    except Exception as e:
        logger.error(f"Reading file error: {file_path}: {e}")
        report = DocumentReport(file_path=str(file_path))
        report.issues.append(BlockIssue(
            block_type="document",
            block_id="root",
            path="",
            errors=[f"Reading file error: {e}"],
        ))
        return report


    report = validator.validate_document(document, str(file_path))


    if fix and report.has_issues:
        fixable_issues = [i for i in report.issues if i.is_fixable]
        if fixable_issues:
            logger.info(f"try to fix {len(fixable_issues)} questions...")
            document, fixed_count = validator.repair_document(document, report)
            report.fixed_count = fixed_count

            if fixed_count > 0:

                backup_path = file_path.with_suffix(f".bak{file_path.suffix}")
                try:

                    import shutil
                    shutil.copy(file_path, backup_path)
                    logger.info(f"Backup created: {backup_path}")


                    with open(file_path, "w", encoding="utf-8") as f:
                        json.dump(document, f, ensure_ascii=False, indent=2)
                    logger.info(f"Repaired file saved: {file_path}")
                except Exception as e:
                    logger.error(f"Failed to save file: {e}")

    return report


def main():
    """main function"""
    parser = argparse.ArgumentParser(
        description="IR Document verification tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Example:
  %(prog)s chapter-030-section-3-0.json
  %(prog)s *.json --fix
  %(prog)s ./output/ --recursive --fix --verbose
        """,
    )
    parser.add_argument(
        "paths",
        nargs="+",
        help="JSON file or directory to validate",
    )
    parser.add_argument(
        "-r", "--recursive",
        action="store_true",
        help="Process directories recursively",
    )
    parser.add_argument(
        "-f", "--fix",
        action="store_true",
        help="Automatically fix common problems",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Show details",
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="Disable color output",
    )

    args = parser.parse_args()


    logger.remove()
    if args.verbose:
        logger.add(sys.stderr, level="DEBUG")
    else:
        logger.add(sys.stderr, level="INFO")


    files: List[Path] = []
    for path_str in args.paths:
        path = Path(path_str)
        if path.is_file():
            if path.suffix.lower() == ".json":
                files.append(path)
        elif path.is_dir():
            if args.recursive:
                files.extend(path.rglob("*.json"))
            else:
                files.extend(path.glob("*.json"))
        else:

            import glob
            matched = glob.glob(path_str)
            for m in matched:
                mp = Path(m)
                if mp.is_file() and mp.suffix.lower() == ".json":
                    files.append(mp)

    if not files:
        print("JSON file not found")
        sys.exit(1)

    print(f"turn up {len(files)} files")


    validator = IRValidator()


    total_issues = 0
    total_fixed = 0
    reports: List[DocumentReport] = []

    for file_path in files:
        report = validate_file(file_path, validator, args.fix, args.verbose)
        reports.append(report)
        total_issues += len(report.issues)
        total_fixed += report.fixed_count

        if args.verbose or report.has_issues:
            print_report(report, args.verbose)


    print(f"\n{'=' * 60}")
    print("Summarize")
    print(f"{'=' * 60}")
    print(f"  - Number of files: {len(files)}")
    print(f"  - total number of questions: {total_issues}")
    if args.fix:
        print(f"  - Fixed: {total_fixed}")


    if total_issues > 0 and total_fixed < total_issues:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
