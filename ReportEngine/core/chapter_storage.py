"""
Chapter JSON placement and list management.

Each chapter will be written to the raw file immediately during streaming generation, and then written after verification is completed.
formattedchapter.json，And record the metadata in the manifest to facilitate subsequent binding.。
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Generator, List, Optional


@dataclass
class ChapterRecord:
    """
    manifestChapter metadata recorded in .

    This structure is used in `manifest.json` Track the status of each chapter、file location、
    And a list of possible errors for easy reading by front-end or debugging tools。
    """

    chapter_id: str
    slug: str
    title: str
    order: int
    status: str
    files: Dict[str, str] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None).isoformat() + "Z")

    def to_dict(self) -> Dict[str, object]:
        """Convert records to make them easier to writemanifest.jsonSerialized dictionary of"""
        return {
            "chapterId": self.chapter_id,
            "slug": self.slug,
            "title": self.title,
            "order": self.order,
            "status": self.status,
            "files": self.files,
            "errors": self.errors,
            "updatedAt": self.updated_at,
        }


class ChapterStorage:
    """
    Chapter JSON writing with manifest manager.

    Responsible：
        - Create an independent run directory and manifest snapshot for each report；
        - Write on the fly as chapters are streamed `stream.raw`；
        - Persistence after passing verification `chapter.json` and update the manifest status。
    """

    def __init__(self, base_dir: str):
        """
        Create chapter memory。

        Args:
            base_dir: The root path of all output run directories
        """
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._manifests: Dict[str, Dict[str, object]] = {}



    def start_session(self, report_id: str, metadata: Dict[str, object]) -> Path:
        """
        Create an independent chapter output directory and manifest for this report.

        At the same time, write global metadata `manifest.json`，for rendering/Debug queries.

        parameter:
            report_id: TaskID。
            metadata: Reportmetadata (title、theme, etc.).

        return:
            Path: New run directory。
        """
        run_dir = self.base_dir / report_id
        run_dir.mkdir(parents=True, exist_ok=True)
        manifest = {
            "reportId": report_id,
            "createdAt": datetime.now(timezone.utc).replace(tzinfo=None).isoformat() + "Z",
            "metadata": metadata,
            "chapters": [],
        }
        self._manifests[self._key(run_dir)] = manifest
        self._write_manifest(run_dir, manifest)
        return run_dir

    def begin_chapter(self, run_dir: Path, chapter_meta: Dict[str, object]) -> Path:
        """
        Create a chapter subdirectory and mark it as streaming in the manifest.

        will generate `order-slug` style subdirectory and register the raw file path in advance.

        parameter:
            run_dir: session root。
            chapter_meta: Include chapterId/title/slug/order metadata.

        return:
            Path: Chapter table of contents。
        """
        slug_value = str(
            chapter_meta.get("slug") or chapter_meta.get("chapterId") or "section"
        )
        chapter_dir = self._chapter_dir(
            run_dir,
            slug_value,
            int(chapter_meta.get("order", 0)),
        )
        record = ChapterRecord(
            chapter_id=str(chapter_meta.get("chapterId")),
            slug=slug_value,
            title=str(chapter_meta.get("title")),
            order=int(chapter_meta.get("order", 0)),
            status="streaming",
            files={"raw": str(self._raw_stream_path(chapter_dir).relative_to(run_dir))},
        )
        self._upsert_record(run_dir, record)
        return chapter_dir

    def persist_chapter(
        self,
        run_dir: Path,
        chapter_meta: Dict[str, object],
        payload: Dict[str, object],
        errors: Optional[List[str]] = None,
    ) -> Path:
        """
        After the chapter streaming is generated, the final JSON is written and the manifest status is updated.

        If the verification fails, the error message will be written to the manifest for front-end display.

        parameter:
            run_dir: session root。
            chapter_meta: Chapter meta information。
            payload: Chapters that passed the verificationJSON。
            errors: Optional error list used to mark invalid status.

        return:
            Path: final `chapter.json` file path。
        """
        slug_value = str(
            chapter_meta.get("slug") or chapter_meta.get("chapterId") or "section"
        )
        chapter_dir = self._chapter_dir(
            run_dir,
            slug_value,
            int(chapter_meta.get("order", 0)),
        )
        final_path = chapter_dir / "chapter.json"
        final_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        record = ChapterRecord(
            chapter_id=str(chapter_meta.get("chapterId")),
            slug=slug_value,
            title=str(chapter_meta.get("title")),
            order=int(chapter_meta.get("order", 0)),
            status="ready" if not errors else "invalid",
            files={
                "raw": str(self._raw_stream_path(chapter_dir).relative_to(run_dir)),
                "json": str(final_path.relative_to(run_dir)),
            },
            errors=errors or [],
        )
        self._upsert_record(run_dir, record)
        return final_path

    def load_chapters(self, run_dir: Path) -> List[Dict[str, object]]:
        """
        Read all from the specified run directorychapter.jsonAnd return them in order.

        Commonly used in DocumentComposer to bind multiple chapters into an entire IR.

        parameter:
            run_dir: Session root directory.

        return:
            list[dict]: Chapter payload list。
        """
        payloads: List[Dict[str, object]] = []
        for child in sorted(run_dir.iterdir()):
            if not child.is_dir():
                continue
            chapter_path = child / "chapter.json"
            if not chapter_path.exists():
                continue
            try:
                payload = json.loads(chapter_path.read_text(encoding="utf-8"))
                payloads.append(payload)
            except json.JSONDecodeError:
                continue
        payloads.sort(key=lambda x: x.get("order", 0))
        return payloads



    @contextmanager
    def capture_stream(self, chapter_dir: Path) -> Generator:
        """
        Write streaming output to raw files in real time.

        Expose file handles through contextmanager to simplify the writing logic of chapter nodes.

        parameter:
            chapter_dir: Current chapter directory.

        return:
            Generator[TextIO]: File object used as context manager。
        """
        raw_path = self._raw_stream_path(chapter_dir)
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        with raw_path.open("w", encoding="utf-8") as fp:
            yield fp



    def _chapter_dir(self, run_dir: Path, slug: str, order: int) -> Path:
        """according toslug/orderGenerate a stable table of contents to ensure that each chapter is saved separately and can be sorted。"""
        safe_slug = self._safe_slug(slug)
        folder = f"{order:03d}-{safe_slug}"
        path = run_dir / folder
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _safe_slug(self, slug: str) -> str:
        """Remove dangerous characters to avoid generating illegal folder names。"""
        slug = slug.replace(" ", "-").replace("/", "-")
        return slug or "section"

    def _raw_stream_path(self, chapter_dir: Path) -> Path:
        """Returns the raw file path corresponding to the streaming output of a certain chapter。"""
        return chapter_dir / "stream.raw"

    def _key(self, run_dir: Path) -> str:
        """Parse the run directory into dictionary cache keys to avoid repeated disk reads。"""
        return str(run_dir.resolve())

    def _manifest_path(self, run_dir: Path) -> Path:
        """getmanifest.jsonthe actual file path of。"""
        return run_dir / "manifest.json"

    def _write_manifest(self, run_dir: Path, manifest: Dict[str, object]):
        """Write all manifest snapshots in memory back to disk。"""
        self._manifest_path(run_dir).write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _read_manifest(self, run_dir: Path) -> Dict[str, object]:
        """
        Read the existing manifest from disk.

        You can use it to restore the context when the process is restarted or multiple instances write to disk.。
        """
        manifest_path = self._manifest_path(run_dir)
        if manifest_path.exists():
            return json.loads(manifest_path.read_text(encoding="utf-8"))
        return {"reportId": run_dir.name, "chapters": []}

    def _upsert_record(self, run_dir: Path, record: ChapterRecord):
        """
        Update or append chapter records in the manifest to ensure consistent order.

        It will be automatically sorted internally and written back to the cache.+disk。
        """
        key = self._key(run_dir)
        manifest = self._manifests.get(key) or self._read_manifest(run_dir)
        chapters: List[Dict[str, object]] = manifest.get("chapters", [])
        chapters = [c for c in chapters if c.get("chapterId") != record.chapter_id]
        chapters.append(record.to_dict())
        chapters.sort(key=lambda x: x.get("order", 0))
        manifest["chapters"] = chapters
        manifest.setdefault("updatedAt", datetime.now(timezone.utc).replace(tzinfo=None).isoformat() + "Z")
        self._manifests[key] = manifest
        self._write_manifest(run_dir, manifest)


__all__ = ["ChapterStorage", "ChapterRecord"]
