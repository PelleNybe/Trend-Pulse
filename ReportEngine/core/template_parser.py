"""
MarkdownTemplate slicing tool.

LLM needs to be "called by chapter", so the Markdown template must be parsed into a structured chapter queue.
This is compatible with lightweight regularity and indentation heuristics“
“- **1.0 title** /   - 1.1 Subtitle" and other writing methods。
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import List, Optional

SECTION_ORDER_STEP = 10


@dataclass
class TemplateSection:
    """
    Template chapter entity.

    record title、slug、serial number、Hierarchy、original title、Chapter numbers and outlines,
    It is convenient for subsequent nodes to be referenced in prompt words and to keep the anchor points consistent.。
    """

    title: str
    slug: str
    order: int
    depth: int
    raw_title: str
    number: str = ""
    chapter_id: str = ""
    outline: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """
        Serialize chapter entities into a dictionary.

        This structure is widely used in cue word context as well as layout/word budget Node input。
        """
        return {
            "title": self.title,
            "slug": self.slug,
            "order": self.order,
            "depth": self.depth,
            "number": self.number,
            "chapterId": self.chapter_id,
            "outline": self.outline,
        }




heading_pattern = re.compile(
    r"""
    (?P<marker>\#+)
    [ \t]+
    (?P<title>[^\r\n]+)
    """,
    re.VERBOSE,
)
bullet_pattern = re.compile(
    r"""
    (?P<marker>[-*+])
    [ \t]+
    (?P<title>[^\r\n]+)
    """,
    re.VERBOSE,
)
number_pattern = re.compile(
    r"""
    (?P<num>
        (?:0|[1-9]\d*)
        (?:\.(?:0|[1-9]\d*))*
    )
    (?:
        (?:[ \t\u00A0\u3000、:：-]+|\.(?!\d))+
        (?P<label>[^\r\n]*)
    )?
    """,
    re.VERBOSE,
)


def parse_template_sections(template_md: str) -> List[TemplateSection]:
    """
    Divide the Markdown template into a list of chapters (by large title).

    Each TemplateSection returned carriesslug/order/Chapter number,
    This facilitates subsequent chapter calling and anchor point generation. Will be compatible at the same time when parsing
    "

    parameters:
        template_md: Template Markdown full text.

    return:
        list[TemplateSection]: Structured chapter sequence。
    """

    sections: List[TemplateSection] = []
    current: Optional[TemplateSection] = None
    order = SECTION_ORDER_STEP
    used_slugs = set()

    for raw_line in template_md.splitlines():
        if not raw_line.strip():
            continue

        indent = len(raw_line) - len(raw_line.lstrip(" "))
        stripped = raw_line.strip()

        meta = _classify_line(stripped, indent)
        if not meta:
            continue

        if meta["is_section"]:
            slug = _ensure_unique_slug(meta["slug"], used_slugs)
            section = TemplateSection(
                title=meta["title"],
                slug=slug,
                order=order,
                depth=meta["depth"],
                raw_title=meta["raw"],
                number=meta["number"],
            )
            sections.append(section)
            current = section
            order += SECTION_ORDER_STEP
            continue


        if current:
            current.outline.append(meta["title"])

    for idx, section in enumerate(sections, start=1):

        section.chapter_id = f"S{idx}"

    return sections


def _classify_line(stripped: str, indent: int) -> Optional[dict]:
    """
    Sort lines based on indentation and symbols.

    Use regular rules to determine whether the current line is the chapter title、The outline is still an ordinary list item,
    and derived depth/slug/number and other derived information.

    parameter:
        stripped: Original line after removing leading and trailing spaces。
        indent: The number of spaces at the beginning of the line is used to distinguish levels.

    return:
        dict | None: Recognized metadata; returned if unrecognizedNone。
    """

    heading_match = heading_pattern.fullmatch(stripped)
    if heading_match:
        level = len(heading_match.group("marker"))
        payload = _strip_markup(heading_match.group("title").strip())
        title_info = _split_number(payload)
        slug = _build_slug(title_info["number"], title_info["title"])
        return {
            "is_section": level <= 2,
            "depth": level,
            "title": title_info["display"],
            "raw": payload,
            "number": title_info["number"],
            "slug": slug,
        }

    bullet_match = bullet_pattern.fullmatch(stripped)
    if bullet_match:
        payload = _strip_markup(bullet_match.group("title").strip())
        title_info = _split_number(payload)
        slug = _build_slug(title_info["number"], title_info["title"])
        is_section = indent <= 1
        depth = 1 if indent <= 1 else 2
        return {
            "is_section": is_section,
            "depth": depth,
            "title": title_info["display"],
            "raw": payload,
            "number": title_info["number"],
            "slug": slug,
        }


    number_match = number_pattern.fullmatch(stripped)
    if number_match and number_match.group("label"):
        payload = stripped
        title = number_match.group("label").strip()
        number = number_match.group("num")
        slug = _build_slug(number, title)
        is_section = indent == 0 and number.count(".") <= 1
        depth = 1 if is_section else 2
        display = f"{number} {title}" if title else number
        return {
            "is_section": is_section,
            "depth": depth,
            "title": display,
            "raw": payload,
            "number": number,
            "slug": slug,
        }

    return None


def _strip_markup(text: str) -> str:
    """unwrapped**、__etc. to avoid interfering with title matching。"""
    if text.startswith(("**", "__")) and text.endswith(("**", "__")) and len(text) > 4:
        return text[2:-2].strip()
    return text


def _split_number(payload: str) -> dict:
    """
    Split numbers and titles.

    For example `1.2 market trends` will be broken into number=1.2、label=market trends,
    And provide display for backfilling the title.

    parameter:
        payload: Original title string.

    return:
        dict: Include number/title/display。
    """
    match = number_pattern.fullmatch(payload)
    number = match.group("num") if match else ""
    label = match.group("label") if match else payload
    label = (label or "").strip()
    display = f"{number} {label}".strip() if number else label or payload
    title_core = label or payload
    return {
        "number": number,
        "title": title_core,
        "display": display,
    }


def _build_slug(number: str, title: str) -> str:
    """
    According to number/The title generates an anchor point, reuses the number first, and slugs the title when missing.

    parameter:
        number: Chapter number。
        title: Title text.

    return:
        str: shaped like `section-1-0` ofslug。
    """
    if number:
        token = number.replace(".", "-")
    else:
        token = _slugify_text(title)
    token = token or "section"
    return f"section-{token}"


def _slugify_text(text: str) -> str:
    """
    Denoise and transcribe any text to obtain URL-friendly slug fragments.

    Will correct case、Remove special symbols and retain Chinese characters to ensure anchors are readable。
    """
    text = unicodedata.normalize("NFKD", text)
    text = text.replace("·", "-").replace(" ", "-")
    text = re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff-]+", "-", text)
    text = re.sub(r"-{2,}", "-", text)
    return text.strip("-").lower()


def _ensure_unique_slug(slug: str, used: set) -> str:
    """
    If the slug is repeated, the serial number will be automatically appended until it is unique in the used collection.

    Pass `-2/-3...` to ensure unique anchors for identical titles.

    parameter:
        slug: initialslug。
        used: Collection used.

    return:
        str: After deduplicationslug。
    """
    if slug not in used:
        used.add(slug)
        return slug
    base = slug
    idx = 2
    while slug in used:
        slug = f"{base}-{idx}"
        idx += 1
    used.add(slug)
    return slug


__all__ = ["TemplateSection", "parse_template_sections"]
