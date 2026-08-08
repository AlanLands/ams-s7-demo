"""Rule-based (non-LLM) requirement extraction, and source file decoding.

Deliberately not AI: a deterministic parser that pulls a title, business
objective, summary and numbered requirement bullets out of arbitrary text.
Used for simulation-mode intake extraction — CLAUDE.md's staged-output rule
means this is never presented as "AI Extraction"; see
`Provenance.RULE_BASED` and `engine.intake_extract`.
"""

from __future__ import annotations

import io
import re

MAX_REQUIREMENTS = 12
_MIN_ITEM_LEN = 10
_MAX_ITEM_LEN = 300

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_EPIC_PREFIX_RE = re.compile(r"^EPIC-[A-Za-z0-9-]+\s*[—-]\s*", re.IGNORECASE)
_BLOCKQUOTE_RE = re.compile(r"^>\s?(.*)$")
_LIST_ITEM_RE = re.compile(r"^\s*(?:[-*]|\d+[.)])\s+(.*)$")
_TABLE_ROW_RE = re.compile(r"^\s*\|")
_MD_EMPHASIS_RE = re.compile(r"\*{1,2}(.+?)\*{1,2}")

_OBJECTIVE_HEADING_RE = re.compile(r"objective|business ask|target state|goal", re.IGNORECASE)
_SUMMARY_HEADING_RE = re.compile(r"summary|business context|current state", re.IGNORECASE)
_REQUIREMENT_HEADING_RE = re.compile(
    r"requirement|capabilit|business rule|acceptance criteria|in scope|target state",
    re.IGNORECASE,
)

_TRIGGER_WORDS = ("must", "shall", "should", "reject", "require", "calculate",
                   "store", "validate", "confirm")


class ExtractionError(Exception):
    """Raised when source text is unusable, or a file can't be decoded."""


def decode_source(filename: str, content: bytes) -> str:
    """Turn uploaded bytes into text. Supported: .txt, .md, .pdf, .docx."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext in ("txt", "md"):
        return content.decode("utf-8", errors="replace")
    if ext == "pdf":
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(content))
        return "\n\n".join(page.extract_text() or "" for page in reader.pages)
    if ext == "docx":
        from docx import Document
        doc = Document(io.BytesIO(content))
        lines = []
        for para in doc.paragraphs:
            text = para.text.strip()
            if not text:
                continue
            style = (para.style.name if para.style else "") or ""
            m = re.match(r"Heading\s*(\d)", style)
            if m:
                lines.append(f"{'#' * min(int(m.group(1)), 6)} {text}")
            else:
                lines.append(text)
        return "\n\n".join(lines)
    raise ExtractionError(
        f"Unsupported file type {filename!r} — supported: .txt, .md, .pdf, .docx"
    )


def _blocks(text: str) -> list[str]:
    """Blank-line-separated blocks; a block's own internal newlines stay."""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    return [b.strip() for b in re.split(r"\n\s*\n", normalized) if b.strip()]


def _block_kind(block: str) -> str:
    first_line = block.splitlines()[0]
    if _HEADING_RE.match(first_line):
        return "heading"
    if _BLOCKQUOTE_RE.match(first_line):
        return "blockquote"
    if _TABLE_ROW_RE.match(first_line):
        return "table"
    if _LIST_ITEM_RE.match(first_line):
        return "list"
    return "prose"


def _heading_text(block: str) -> str:
    m = _HEADING_RE.match(block.splitlines()[0])
    return m.group(2).strip() if m else ""


def _clean_block(block: str) -> str:
    lines = block.splitlines()
    if _BLOCKQUOTE_RE.match(lines[0]):
        return "\n".join(_BLOCKQUOTE_RE.sub(r"\1", line) for line in lines)
    return block


def _truncate(text: str, limit: int) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    cut = text.rfind(". ", 0, limit)
    cut = limit if cut == -1 else cut + 1
    return text[:cut].strip()


def _title(text: str, blocks: list[str]) -> str:
    if blocks:
        first_line = blocks[0].splitlines()[0]
        m = _HEADING_RE.match(first_line)
        if m:
            return _EPIC_PREFIX_RE.sub("", m.group(2).strip()).strip()
    first_line = text.strip().splitlines()[0].strip() if text.strip() else ""
    if first_line and len(first_line) <= 120:
        return _EPIC_PREFIX_RE.sub("", first_line).strip()
    return "Untitled requirement"


def _block_after_heading(
    blocks: list[str], pattern: re.Pattern[str], kinds: tuple[str, ...]
) -> str | None:
    for i, block in enumerate(blocks):
        if _block_kind(block) == "heading" and pattern.search(_heading_text(block)):
            for nxt in blocks[i + 1:]:
                kind = _block_kind(nxt)
                if kind == "heading":
                    break
                if kind in kinds:
                    return nxt
    return None


def _first_of_kind(blocks: list[str], kind: str) -> str | None:
    for block in blocks:
        if _block_kind(block) == kind:
            return block
    return None


def _business_objective(blocks: list[str]) -> str:
    found = (_block_after_heading(blocks, _OBJECTIVE_HEADING_RE, ("blockquote", "prose"))
             or _first_of_kind(blocks, "blockquote")
             or _first_of_kind(blocks, "prose"))
    return _truncate(_clean_block(found), 400) if found else "Not stated in the source text."


def _requirement_summary(blocks: list[str]) -> str:
    found = (_block_after_heading(blocks, _SUMMARY_HEADING_RE, ("prose",))
             or _first_of_kind(blocks, "prose"))
    return _truncate(found, 500) if found else "Not stated in the source text."


def _strip_emphasis(text: str) -> str:
    return _MD_EMPHASIS_RE.sub(r"\1", text)


def _list_items_in_block(block: str) -> list[str]:
    items: list[str] = []
    current: list[str] = []

    def flush() -> None:
        if not current:
            return
        text = _strip_emphasis(" ".join(" ".join(current).split()))
        if _MIN_ITEM_LEN <= len(text) <= _MAX_ITEM_LEN:
            items.append(text)
        current.clear()

    for line in block.splitlines():
        m = _LIST_ITEM_RE.match(line)
        if m:
            flush()
            current.append(m.group(1))
        elif current and line.strip():
            current.append(line.strip())
    flush()
    return items


def _collect_list_items(blocks: list[str], only_after: re.Pattern[str] | None) -> list[str]:
    items: list[str] = []
    seen: set[str] = set()
    under_match = only_after is None
    for block in blocks:
        kind = _block_kind(block)
        if kind == "heading":
            if only_after is not None:
                under_match = bool(only_after.search(_heading_text(block)))
            continue
        if kind == "list" and under_match:
            for item in _list_items_in_block(block):
                if item not in seen:
                    seen.add(item)
                    items.append(item)
    return items


def _trigger_sentences(blocks: list[str]) -> list[str]:
    items: list[str] = []
    seen: set[str] = set()
    prose = " ".join(b for b in blocks if _block_kind(b) == "prose")
    for sentence in re.split(r"(?<=[.!?])\s+", prose):
        sentence = sentence.strip()
        if not (_MIN_ITEM_LEN <= len(sentence) <= _MAX_ITEM_LEN):
            continue
        lower = f" {sentence.lower()} "
        if any(f" {w} " in lower for w in _TRIGGER_WORDS) and sentence not in seen:
            seen.add(sentence)
            items.append(sentence)
    return items


def _extracted_requirements(blocks: list[str]) -> list[dict]:
    items = (_collect_list_items(blocks, _REQUIREMENT_HEADING_RE)
             or _collect_list_items(blocks, None)
             or _trigger_sentences(blocks))
    if not items:
        return [{"rule_id": "REQ-01",
                  "text": "No discrete requirements detected in the source text — "
                          "review it directly."}]
    return [{"rule_id": f"REQ-{i + 1:02d}", "text": item}
            for i, item in enumerate(items[:MAX_REQUIREMENTS])]


def extract_requirement(text: str) -> dict:
    if not text or not text.strip():
        raise ExtractionError("Source text is empty")
    blocks = _blocks(text)
    return {
        "epic_title": _title(text, blocks),
        "business_objective": _business_objective(blocks),
        "requirement_summary": _requirement_summary(blocks),
        "extracted_requirements": _extracted_requirements(blocks),
    }
