# Intake upload/extraction — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the Control Centre's Intake stage a genuine upload/paste front door — rule-based extraction in simulation mode, a real LLM call in live mode — that produces a requirement and an epic from what the user actually gave it, without changing anything about the default rehearsed demo path.

**Architecture:** A new pure module (`s7_delivery/factory/extraction.py`) does deterministic file-decoding and rule-based parsing. A new `live_intake.run_extraction` mirrors the existing `run_analysis`/`route_requirement` pattern for the live path. Three new `Engine` actions (`intake_set_source`, `intake_extract`, `intake_edit_extraction`) plus one new orchestrating action (`intake_finalize`) sit alongside the existing, untouched `intake_analyse`/`intake_create_epic` — the latter gains exactly one new branch (build the epic from an extraction when one exists) and is otherwise byte-for-byte unchanged. Five new HTTP endpoints translate this to the browser. The frontend gets a new two-panel "Source Requirement" / "Extraction" section at the top of the existing Intake page; everything below it is untouched.

**Tech Stack:** Python 3.14, FastAPI, Pydantic, vanilla JS (no build step), `pypdf`, `python-docx`.

## Global Constraints

- **Pin, not a range** for the two new dependencies (hard rule 4) — `pypdf==6.14.2`, `python-docx==1.2.0`.
- **The default rehearsed demo path must not change at all.** A run where nobody uploads or pastes anything must produce the exact `EPIC-S7-001` content it does today, in both simulation and live mode. This is verified by a regression test in Task 6, not just asserted.
- **`intake_create_epic`'s existing precondition (`analysis.json` must exist) is never removed or bypassed.** `test_epic_requires_analysis` in `tests/test_factory_planning.py` already encodes this and must keep passing unmodified.
- **Simulation-mode extraction is genuinely rule-based, not canned** — it must reflect the actual uploaded/pasted text — and it is labelled "Extraction (Rule-Based)", never "AI Extraction", in both the `Provenance` badge and the UI copy. Live mode's real LLM call is labelled "AI Extraction."
- **10MB max upload size**, enforced server-side (reusing the existing `MAX_UPLOAD_BYTES` constant) — a deliberate, smaller cap than the 20MB shown in the reference mockup.
- **20,000 character cap** on source text (upload or paste), enforced in `Engine.intake_set_source`.
- No real client data, no client names anywhere (hard rules 1–2) — nothing from the reference mockup ("canada life", named individuals) appears in any file touched by this plan.
- Every test in every task runs offline, no network, no API key.

---

### Task 1: Dependencies, `Provenance.RULE_BASED`, `RequirementExtraction` model

**Files:**
- Modify: `requirements.txt`
- Modify: `s7_delivery/factory/models.py:28-34` (the `Provenance` enum), `:154-163` (after `EpicRecord`)
- Test: `tests/test_factory_models.py` (new file)

**Interfaces:**
- Produces: `Provenance.RULE_BASED` (value `"rule_based"`); `RequirementExtraction` Pydantic model with fields `epic_title: str`, `business_objective: str`, `requirement_summary: str`, `extracted_requirements: list[dict]`, `method: str`, `provenance: Provenance`, `generated_at: str`, `edited_by: str | None`, `edited_at: str | None`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_factory_models.py`:

```python
"""New model additions for intake extraction."""

from s7_delivery.factory.models import Provenance, RequirementExtraction


def test_rule_based_provenance_value():
    assert Provenance.RULE_BASED.value == "rule_based"


def test_requirement_extraction_defaults():
    rec = RequirementExtraction(
        epic_title="Claims Deductible Handling",
        business_objective="Apply policy deductible during claim intake.",
        requirement_summary="Add a per-policy deductible and apply it during intake.",
        extracted_requirements=[{"rule_id": "REQ-01", "text": "Reject claims at or below the deductible."}],
        method="rule_based",
        provenance=Provenance.RULE_BASED,
    )
    assert rec.edited_by is None
    assert rec.edited_at is None
    assert rec.generated_at  # auto-stamped
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_factory_models.py -v`
Expected: FAIL — `ImportError: cannot import name 'RequirementExtraction'` (and `Provenance.RULE_BASED` doesn't exist).

- [ ] **Step 3: Add the dependency pins**

In `requirements.txt`, under the existing `# --- API layer ---` block (near `python-multipart`), add a new block:

```
# --- intake document parsing ---
# Real text extraction for the upload/paste requirement flow (not a document
# store — content is parsed once, never re-served as a file except as the
# original upload evidence).
pypdf==6.14.2
python-docx==1.2.0
```

- [ ] **Step 4: Add `Provenance.RULE_BASED`**

In `s7_delivery/factory/models.py`, change:

```python
class Provenance(StrEnum):
    HUMAN = "human"
    LIVE_AI = "live_ai"
    REPLAYED_AI = "replayed_ai"
    STAGED = "staged"
    SIMULATED = "simulated"
```

to:

```python
class Provenance(StrEnum):
    HUMAN = "human"
    LIVE_AI = "live_ai"
    REPLAYED_AI = "replayed_ai"
    STAGED = "staged"
    SIMULATED = "simulated"
    # A real, deterministic, non-AI parse of real input (CLAUDE.md § Staged
    # output) — neither fabricated (SIMULATED/STAGED) nor a model call
    # (LIVE_AI/REPLAYED_AI). Used by the rule-based intake extraction parser.
    RULE_BASED = "rule_based"
```

- [ ] **Step 5: Add `RequirementExtraction`**

In `s7_delivery/factory/models.py`, immediately after the `EpicRecord` class (ends around line 162, right before the `# --- planning ---` section comment), add:

```python
class RequirementExtraction(BaseModel):
    """The upload/paste intake front door's output — title, objective,
    summary and numbered requirement bullets pulled from real source text.
    `method` is "rule_based" (simulation) or "live_llm" (live mode); the UI
    labels each honestly and never calls the rule-based path "AI"."""

    epic_title: str
    business_objective: str
    requirement_summary: str
    extracted_requirements: list[dict]  # [{"rule_id": "REQ-01", "text": "..."}]
    method: str
    provenance: Provenance
    generated_at: str = Field(default_factory=now_iso)
    edited_by: str | None = None
    edited_at: str | None = None
```

- [ ] **Step 6: Run test to verify it passes**

Run: `pytest tests/test_factory_models.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add requirements.txt s7_delivery/factory/models.py tests/test_factory_models.py
git commit -m "feat: pin pypdf/python-docx, add RequirementExtraction model and RULE_BASED provenance"
```

---

### Task 2: Rule-based requirement parser (`extraction.extract_requirement`)

**Files:**
- Create: `s7_delivery/factory/extraction.py`
- Test: `tests/test_factory_extraction.py`

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces: `extraction.ExtractionError` (exception); `extraction.extract_requirement(text: str) -> dict` returning `{"epic_title": str, "business_objective": str, "requirement_summary": str, "extracted_requirements": list[dict]}`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_factory_extraction.py`:

```python
"""Rule-based (non-LLM) requirement extraction. Pure functions, offline."""

from pathlib import Path

import pytest

from s7_delivery.factory import extraction

EPIC_S7_001 = (Path(__file__).resolve().parent.parent / "crs" / "EPIC-S7-001.md").read_text()

PLAIN_TEXT = """Claims Deductible Handling

Apply policy deductible during claim intake to ensure valid claim processing
and accurate payable amount calculation.

Add a per-policy deductible and apply it during claim intake.

- Policy record must contain a deductible amount.
- Reject claim if claim amount is at or below the policy deductible.
- For accepted claims, calculate payable amount = claim amount - deductible
  and store it.
"""

NO_STRUCTURE_TEXT = "Sponsors need a way to submit claims online without calling support."


def test_extract_from_epic_s7_001_finds_real_title_and_objective():
    result = extraction.extract_requirement(EPIC_S7_001)
    assert result["epic_title"] == "Online disability claim submission for plan sponsors"
    assert "guided online way" in result["business_objective"]
    assert result["requirement_summary"]
    assert len(result["extracted_requirements"]) >= 1
    assert all(r["rule_id"].startswith("REQ-") for r in result["extracted_requirements"])


def test_extract_caps_at_twelve_and_dedupes():
    result = extraction.extract_requirement(EPIC_S7_001)
    assert len(result["extracted_requirements"]) <= 12
    texts = [r["text"] for r in result["extracted_requirements"]]
    assert len(texts) == len(set(texts))


def test_extract_from_plain_text_with_bullets():
    result = extraction.extract_requirement(PLAIN_TEXT)
    assert result["epic_title"] == "Claims Deductible Handling"
    assert "deductible" in result["business_objective"].lower()
    assert len(result["extracted_requirements"]) == 3
    assert result["extracted_requirements"][0]["rule_id"] == "REQ-01"
    assert "deductible amount" in result["extracted_requirements"][0]["text"]


def test_extract_wraps_multiline_bullets_into_one_item():
    result = extraction.extract_requirement(PLAIN_TEXT)
    payable = [r for r in result["extracted_requirements"] if "payable amount" in r["text"]][0]
    assert "and store it" in payable["text"]


def test_extract_falls_back_to_first_line_title_and_trigger_sentences():
    result = extraction.extract_requirement(NO_STRUCTURE_TEXT)
    assert result["epic_title"] == NO_STRUCTURE_TEXT
    assert result["extracted_requirements"]


def test_extract_never_returns_silently_empty_requirements():
    result = extraction.extract_requirement("A short requirement with no lists or trigger words at all here.")
    assert len(result["extracted_requirements"]) == 1
    assert "No discrete requirements detected" in result["extracted_requirements"][0]["text"]


def test_extract_rejects_empty_text():
    with pytest.raises(extraction.ExtractionError, match="empty"):
        extraction.extract_requirement("   ")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_factory_extraction.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 's7_delivery.factory.extraction'`

- [ ] **Step 3: Write `s7_delivery/factory/extraction.py`**

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_factory_extraction.py -v`
Expected: PASS (7 tests)

If `test_extract_from_epic_s7_001_finds_real_title_and_objective` fails on the objective assertion, print `result["business_objective"]` and check which blockquote was matched — `crs/EPIC-S7-001.md` has two blockquotes (a "Synthetic" disclaimer near the top, and the real business ask under "## 3. Target state — the business ask"); `_block_after_heading` must find the second one via the heading-scoped search, not `_first_of_kind(blocks, "blockquote")`, which would incorrectly pick the disclaimer.

- [ ] **Step 5: Commit**

```bash
git add s7_delivery/factory/extraction.py tests/test_factory_extraction.py
git commit -m "feat: rule-based requirement extraction, labelled honestly as non-AI"
```

---

### Task 3: File decoding tests (`decode_source` for PDF/DOCX)

**Files:**
- Modify: `tests/test_factory_extraction.py` (append)

**Interfaces:**
- Consumes: `extraction.decode_source(filename, content) -> str` (Task 2).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_factory_extraction.py`:

```python
def test_decode_txt_and_md():
    assert extraction.decode_source("req.txt", b"Hello world") == "Hello world"
    assert extraction.decode_source("req.md", "café".encode()) == "café"


def test_decode_unsupported_extension_raises():
    with pytest.raises(extraction.ExtractionError, match="Unsupported file type"):
        extraction.decode_source("req.xlsx", b"data")


def test_decode_pdf(monkeypatch):
    class FakePage:
        def __init__(self, text):
            self._text = text

        def extract_text(self):
            return self._text

    class FakeReader:
        def __init__(self, stream):
            self.pages = [FakePage("Page one text."), FakePage("Page two text.")]

    monkeypatch.setattr("pypdf.PdfReader", FakeReader)
    text = extraction.decode_source("req.pdf", b"%PDF-fake-bytes")
    assert "Page one text." in text
    assert "Page two text." in text


def test_decode_docx_real_roundtrip():
    import docx

    doc = docx.Document()
    doc.add_heading("Claims Deductible Handling", level=1)
    doc.add_paragraph("Apply the deductible during claim intake.")
    buf = io.BytesIO()
    doc.save(buf)

    text = extraction.decode_source("req.docx", buf.getvalue())
    assert "# Claims Deductible Handling" in text
    assert "Apply the deductible during claim intake." in text
    result = extraction.extract_requirement(text)
    assert result["epic_title"] == "Claims Deductible Handling"
```

Add `import io` to the top of `tests/test_factory_extraction.py` alongside the existing imports.

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_factory_extraction.py -v -k decode`
Expected: FAIL — `test_decode_pdf` fails because `monkeypatch.setattr("pypdf.PdfReader", ...)` patches the wrong target (the module-level `from pypdf import PdfReader` inside `decode_source`'s function body means `pypdf.PdfReader` itself is what gets called — verify this patches correctly; if the local `from pypdf import PdfReader` import inside the function resolves the name at call time, patching `pypdf.PdfReader` on the `pypdf` module works because the import happens fresh on every call). The other three should already fail only because pdf mocking isn't wired yet if the pypdf/python-docx packages aren't installed — if `pytest` errors with `ModuleNotFoundError: No module named 'pypdf'` or `'docx'`, install them first: `pip install pypdf==6.14.2 python-docx==1.2.0` (or the repo's usual dependency install step).

- [ ] **Step 3: Confirm implementation (no code change expected)**

`decode_source` was already fully implemented in Task 2, including the `.pdf` and `.docx` branches. This task exists purely to add coverage for those two branches. If any test fails for a reason other than missing dependencies, fix `decode_source` in `s7_delivery/factory/extraction.py` to match — the most likely gap is the `Heading N` style-name regex not matching python-docx's actual style name (`"Heading 1"`) — verify with `print(repr(style))` in a scratch script if needed.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_factory_extraction.py -v`
Expected: PASS (11 tests total)

- [ ] **Step 5: Commit**

```bash
git add tests/test_factory_extraction.py
git commit -m "test: cover decode_source PDF/DOCX paths"
```

---

### Task 4: Live extraction (`live_intake.run_extraction`)

**Files:**
- Modify: `s7_delivery/factory/live_intake.py` (append near the other `run_*` functions, after `run_clarification` and before `run_new_app_setup`, or at the end of the file — exact placement doesn't matter, grouping matters)
- Test: `tests/test_live_intake.py` (append)

**Interfaces:**
- Consumes: `common.llm.complete`, `common.llm.parse_json_response`, `common.llm.LLMError` (existing); `live_intake._call` (existing private helper).
- Produces: `live_intake.run_extraction(text: str) -> tuple[dict, dict]` returning `({"epic_title", "business_objective", "requirement_summary", "extracted_requirements"}, usage_dict)`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_live_intake.py`:

```python
# --- extraction tests -----------------------------------------------------

GOOD_EXTRACTION = {
    "epic_title": "Claims Deductible Handling",
    "business_objective": "Apply policy deductible during claim intake.",
    "requirement_summary": "Add a per-policy deductible and apply it during intake.",
    "extracted_requirements": [
        {"rule_id": "REQ-01", "text": "Policy record must contain a deductible amount."},
        {"rule_id": "REQ-02", "text": "Reject claim if claim amount is at or below the deductible."},
    ],
}

SOURCE_TEXT = "Apply a per-policy deductible during claim intake and reject claims at or below it."


def test_run_extraction_validates_and_badges(monkeypatch):
    monkeypatch.setattr(live_intake, "complete", fake_complete(GOOD_EXTRACTION))
    monkeypatch.setenv("LLM_MODE", "live")
    result, usage = live_intake.run_extraction(SOURCE_TEXT)
    assert result["epic_title"] == "Claims Deductible Handling"
    assert len(result["extracted_requirements"]) == 2
    assert usage["input_tokens"] == 1200


def test_run_extraction_rejects_missing_title(monkeypatch):
    bad = dict(GOOD_EXTRACTION, epic_title="")
    monkeypatch.setattr(live_intake, "complete", fake_complete(bad))
    with pytest.raises(LLMError, match="epic_title"):
        live_intake.run_extraction(SOURCE_TEXT)


def test_run_extraction_rejects_malformed_requirement_entries(monkeypatch):
    bad = dict(GOOD_EXTRACTION, extracted_requirements=[{"text": "no id"}])
    monkeypatch.setattr(live_intake, "complete", fake_complete(bad))
    with pytest.raises(LLMError, match="rule_id"):
        live_intake.run_extraction(SOURCE_TEXT)


def test_run_extraction_rejects_empty_source_text():
    with pytest.raises(LLMError, match="[Ee]mpty|non-empty"):
        live_intake.run_extraction("   ")


def test_run_extraction_needs_no_connected_repos(monkeypatch):
    """Unlike run_analysis/route_requirement, extraction reads the source
    text itself, not a target codebase — it must work before any repo is
    connected."""
    monkeypatch.setattr(live_intake, "complete", fake_complete(GOOD_EXTRACTION))
    result, _ = live_intake.run_extraction(SOURCE_TEXT)
    assert result["epic_title"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_live_intake.py -v -k extraction`
Expected: FAIL — `AttributeError: module 's7_delivery.factory.live_intake' has no attribute 'run_extraction'`

- [ ] **Step 3: Add `run_extraction` to `live_intake.py`**

Add near the other role/shape constants (after `CLARIFY_ROLE`, before `NEW_APP_ROLE` is a reasonable spot) and the function anywhere among the other `run_*` functions:

```python
EXTRACTION_ROLE = (
    "Your role is requirement extraction: read raw, unstructured source "
    "text — an uploaded document or pasted text — and pull out a short "
    "epic title, a one-paragraph business objective, a short requirement "
    "summary, and the discrete, testable requirements it states. Extract "
    "only what the text actually says; never invent a requirement the "
    "source does not support."
)

_EXTRACTION_SHAPE = """{
  "epic_title": "<short title>",
  "business_objective": "<one paragraph>",
  "requirement_summary": "<short paragraph>",
  "extracted_requirements": [
    {"rule_id": "REQ-<n>", "text": "<requirement, in the source's own words>"}
  ]
}"""


def run_extraction(text: str) -> tuple[dict, dict]:
    if not text or not text.strip():
        raise LLMError("Live extraction needs non-empty source text.")
    task = f"""The source text, verbatim:

{text}

Extract the requirement from this text. Return JSON exactly matching:
{_EXTRACTION_SHAPE}"""
    data, usage = _call(
        role=EXTRACTION_ROLE,
        ref="",
        task=task,
        beat="extract",
        key_material=text,
    )
    return _validate_extraction(data), usage


def _validate_extraction(data: dict) -> dict:
    title = str(data.get("epic_title", "")).strip()
    if not title:
        raise LLMError("extraction has no epic_title")
    objective = str(data.get("business_objective", "")).strip()
    if not objective:
        raise LLMError("extraction has no business_objective")
    summary = str(data.get("requirement_summary", "")).strip()
    if not summary:
        raise LLMError("extraction has no requirement_summary")
    reqs = data.get("extracted_requirements")
    if not isinstance(reqs, list) or not reqs:
        raise LLMError("extraction has no extracted_requirements")
    cleaned = []
    for r in reqs:
        if not (isinstance(r, dict) and r.get("rule_id") and r.get("text")):
            raise LLMError(f"extracted_requirements entry missing rule_id/text: {r!r}")
        cleaned.append({"rule_id": str(r["rule_id"]), "text": str(r["text"])})
    return {
        "epic_title": title,
        "business_objective": objective,
        "requirement_summary": summary,
        "extracted_requirements": cleaned,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_live_intake.py -v`
Expected: PASS (all existing tests plus the 5 new ones)

- [ ] **Step 5: Commit**

```bash
git add s7_delivery/factory/live_intake.py tests/test_live_intake.py
git commit -m "feat: live_intake.run_extraction — real LLM requirement extraction"
```

---

### Task 5: Engine actions — `intake_set_source`, `intake_extract`

**Files:**
- Modify: `s7_delivery/factory/engine.py:20-39` (imports), `:471-493` (insert new methods between `intake_clarify_answer` and `intake_create_epic`), `:281-290` (`state()`'s `intake` dict)
- Test: `tests/test_factory_intake_extraction.py` (new file)

**Interfaces:**
- Consumes: `extraction.extract_requirement` (Task 2), `live_intake.run_extraction` (Task 4), `RequirementExtraction`/`Provenance.RULE_BASED` (Task 1).
- Produces: `Engine.intake_set_source(role, text, filename=None, source_kind="paste", raw_content=None) -> None`; `Engine.intake_extract(role) -> None`. Both raise `EngineError` on invalid input. Writes `intake/source.json` and `intake/extraction.json`; patches `requirement.json`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_factory_intake_extraction.py`:

```python
"""intake_set_source / intake_extract — the upload/paste front door."""

import pytest

from s7_delivery.factory.engine import Engine, EngineError
from s7_delivery.factory.models import DemoMode, Role

SOURCE_TEXT = """Claims Deductible Handling

Apply policy deductible during claim intake to ensure valid claim processing.

- Policy record must contain a deductible amount.
- Reject claim if claim amount is at or below the policy deductible.
"""


@pytest.fixture()
def eng(tmp_path):
    return Engine.create(DemoMode.SIMULATION, root=tmp_path)


def test_set_source_updates_requirement(eng):
    eng.intake_set_source(Role.PRODUCT_ANALYST, SOURCE_TEXT, filename="epic.md", source_kind="upload")
    req = eng.state()["intake"]["requirement"]
    assert req["description"] == SOURCE_TEXT
    assert req["source_type"] == "Uploaded document"
    assert req["source_documents"] == ["epic.md"]


def test_set_source_paste_uses_placeholder_source_document(eng):
    eng.intake_set_source(Role.PRODUCT_ANALYST, SOURCE_TEXT, source_kind="paste")
    req = eng.state()["intake"]["requirement"]
    assert req["source_type"] == "Pasted text"
    assert req["source_documents"] == ["pasted-text"]


def test_set_source_rejects_empty_text(eng):
    with pytest.raises(EngineError, match="empty"):
        eng.intake_set_source(Role.PRODUCT_ANALYST, "   ")


def test_set_source_rejects_oversized_text(eng):
    with pytest.raises(EngineError, match="20,000"):
        eng.intake_set_source(Role.PRODUCT_ANALYST, "x" * 20_001)


def test_set_source_persists_raw_upload_bytes(eng, tmp_path):
    eng.intake_set_source(Role.PRODUCT_ANALYST, SOURCE_TEXT, filename="epic.md",
                           source_kind="upload", raw_content=SOURCE_TEXT.encode())
    assert eng.store.exists("intake", "documents", "epic.md")


def test_extract_requires_source_first(eng):
    with pytest.raises(EngineError, match="Provide a source"):
        eng.intake_extract(Role.PRODUCT_ANALYST)


def test_extract_produces_rule_based_extraction_in_simulation(eng):
    eng.intake_set_source(Role.PRODUCT_ANALYST, SOURCE_TEXT, filename="epic.md", source_kind="upload")
    eng.intake_extract(Role.PRODUCT_ANALYST)
    state = eng.state()
    ext = state["intake"]["extraction"]
    assert ext["method"] == "rule_based"
    assert ext["provenance"] == "rule_based"
    assert ext["epic_title"] == "Claims Deductible Handling"
    assert len(ext["extracted_requirements"]) == 2


def test_extract_patches_requirement_title(eng):
    eng.intake_set_source(Role.PRODUCT_ANALYST, SOURCE_TEXT, filename="epic.md", source_kind="upload")
    eng.intake_extract(Role.PRODUCT_ANALYST)
    assert eng.state()["intake"]["requirement"]["title"] == "Claims Deductible Handling"


def test_extract_records_provenance_and_activity(eng):
    eng.intake_set_source(Role.PRODUCT_ANALYST, SOURCE_TEXT, filename="epic.md", source_kind="upload")
    eng.intake_extract(Role.PRODUCT_ANALYST)
    state = eng.state()
    assert any(r["artifact_id"] == "EXT-001" for r in state["provenance_ledger"])
    assert any(a["workflow"] == "intake-extraction" for a in state["activity"])


def test_state_exposes_source_and_extraction_as_none_by_default(eng):
    intake = eng.state()["intake"]
    assert intake["source"] is None
    assert intake["extraction"] is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_factory_intake_extraction.py -v`
Expected: FAIL — `AttributeError: 'Engine' object has no attribute 'intake_set_source'`

- [ ] **Step 3: Update imports in `engine.py`**

Change:

```python
from s7_delivery.factory.models import (
    STAGE_ORDER,
    AcceptanceCriterion,
    ActivityEvent,
    Approval,
    DeliveryRun,
    DemoMode,
    GateId,
    GateRecord,
    Provenance,
    ProvenanceRecord,
    Requirement,
    Role,
    RollbackPlan,
    Stage,
    StageState,
    Status,
    Story,
    now_iso,
)
```

to (adding `EpicRecord` and `RequirementExtraction`, alphabetically):

```python
from s7_delivery.factory.models import (
    STAGE_ORDER,
    AcceptanceCriterion,
    ActivityEvent,
    Approval,
    DeliveryRun,
    DemoMode,
    EpicRecord,
    GateId,
    GateRecord,
    Provenance,
    ProvenanceRecord,
    Requirement,
    RequirementExtraction,
    Role,
    RollbackPlan,
    Stage,
    StageState,
    Status,
    Story,
    now_iso,
)
```

- [ ] **Step 4: Add `MAX_SOURCE_CHARS` and the two new methods**

Add the constant near the top of the file, alongside `GATE_LABELS`:

```python
MAX_SOURCE_CHARS = 20_000  # long enough for any realistic epic doc, short
                            # enough to keep both the parser and the LLM
                            # prompt bounded (CLAUDE.md § intake extraction)
```

In `engine.py`, insert the two new methods immediately after `intake_clarify_answer` (which ends with `details=f"{len(answers)} answers recorded",\n        )`) and before `def intake_create_epic`:

```python
    def intake_set_source(
        self, role: Role, text: str, filename: str | None = None,
        source_kind: str = "paste", raw_content: bytes | None = None,
    ) -> None:
        """The upload/paste front door: replaces the requirement's own text
        with real source content. Presence of intake/source.json is the
        single signal `intake_extract` and `intake_create_epic` use to know
        a real source was provided — the mechanism that keeps the default
        seeded demo path completely untouched (CLAUDE.md § intake extraction)."""
        roles.require("upload_intake_document", role)
        text = text.strip()
        if not text:
            raise EngineError("Source text is empty")
        if len(text) > MAX_SOURCE_CHARS:
            raise EngineError(
                f"Source text exceeds the {MAX_SOURCE_CHARS:,}-character limit "
                f"({len(text):,} chars) — trim it and try again"
            )
        safe_name = None
        if filename:
            safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", filename).lstrip(".") or "document"
            if raw_content is not None:
                self.store.write_bytes(raw_content, "intake", "documents", safe_name)
        req = Requirement.model_validate(self.store.read_json("intake", "requirement.json"))
        req.description = text
        req.source_type = "Uploaded document" if source_kind == "upload" else "Pasted text"
        req.source_documents = [safe_name] if safe_name else ["pasted-text"]
        self.store.write_json(req, "intake", "requirement.json")
        source = {
            "text": text, "filename": safe_name, "source_kind": source_kind,
            "set_at": now_iso(),
        }
        self.store.write_json(source, "intake", "source.json")
        self._record(
            artifact_id=req.request_id, artifact_type="requirement", payload=req,
            author=role.value, stage=Stage.INTAKE, action="set-source",
            outcome="amended",
        )
        self._activity(
            stage=Stage.INTAKE, actor=role.value, actor_type="human",
            workflow="set-source", outcome="set",
            details=f"{source_kind}: {safe_name or '(pasted text)'}, {len(text)} chars",
        )

    def intake_extract(self, role: Role) -> None:
        roles.require("run_intake_analysis", role)
        source = self.store.read_json_or(None, "intake", "source.json")
        if source is None:
            raise EngineError("Provide a source document or pasted text before extracting")

        if self.run().mode is DemoMode.LIVE:
            import time

            from s7_delivery.factory import live_intake

            t0 = time.monotonic()
            result, usage = live_intake.run_extraction(source["text"])
            method, provenance, actor_type = "live_llm", live_intake.provenance_now(), "live_ai"
            duration = round(time.monotonic() - t0, 2)
            details = f"in={usage.get('input_tokens')} out={usage.get('output_tokens')} tokens"
        else:
            from s7_delivery.factory import extraction

            result = extraction.extract_requirement(source["text"])
            method, provenance, actor_type = "rule_based", Provenance.RULE_BASED, "simulation"
            duration = 0.0
            details = f"{len(result['extracted_requirements'])} requirements found"

        record = RequirementExtraction(
            epic_title=result["epic_title"],
            business_objective=result["business_objective"],
            requirement_summary=result["requirement_summary"],
            extracted_requirements=result["extracted_requirements"],
            method=method,
            provenance=provenance,
        )
        self.store.write_json(record, "intake", "extraction.json")

        req = Requirement.model_validate(self.store.read_json("intake", "requirement.json"))
        req.title = record.epic_title
        self.store.write_json(req, "intake", "requirement.json")

        self._record(
            artifact_id="EXT-001", artifact_type="requirement_extraction",
            payload=record, author=f"intake-extraction ({method})",
            stage=Stage.INTAKE, action="extract", outcome="created",
            inputs=[req.request_id],
        )
        self._activity(
            stage=Stage.INTAKE, actor="intake-extraction", actor_type=actor_type,
            workflow="intake-extraction", artifact="EXT-001",
            duration_s=duration, outcome="created", details=details,
        )
```

- [ ] **Step 5: Add `source`/`extraction` to `state()`**

In `engine.py`'s `state()` method, change:

```python
            "intake": {
                "requirement": self.store.read_json_or(None, "intake", "requirement.json"),
                "analysis": self.store.read_json_or(None, "intake", "analysis.json"),
```

to:

```python
            "intake": {
                "requirement": self.store.read_json_or(None, "intake", "requirement.json"),
                "source": self.store.read_json_or(None, "intake", "source.json"),
                "extraction": self.store.read_json_or(None, "intake", "extraction.json"),
                "analysis": self.store.read_json_or(None, "intake", "analysis.json"),
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_factory_intake_extraction.py -v`
Expected: PASS (10 tests)

Also run the full suite to confirm nothing else broke: `pytest tests/ -q`

- [ ] **Step 7: Commit**

```bash
git add s7_delivery/factory/engine.py tests/test_factory_intake_extraction.py
git commit -m "feat: intake_set_source / intake_extract — mode-aware requirement extraction"
```

---

### Task 6: `intake_edit_extraction`, extraction-aware `intake_create_epic`, `intake_finalize`

**Files:**
- Modify: `s7_delivery/factory/engine.py:493-509` (`intake_create_epic`), insert new methods after it.
- Test: `tests/test_factory_intake_extraction.py` (append)

**Interfaces:**
- Consumes: `RequirementExtraction`, `EpicRecord`, `Provenance` (Task 1); `intake_set_source`/`intake_extract` (Task 5).
- Produces: `Engine.intake_edit_extraction(role, patch: dict) -> None`; `Engine.intake_create_epic(role)` gains the extraction-aware branch (signature unchanged); `Engine.intake_finalize(role) -> None`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_factory_intake_extraction.py`:

```python
from s7_delivery.factory import seed


def _seeded_epic_only(eng):
    eng.intake_analyse(Role.PRODUCT_ANALYST)
    eng.intake_create_epic(Role.PRODUCT_ANALYST)
    return eng.state()["intake"]["epic"]


def test_create_epic_without_extraction_matches_seed_exactly(eng):
    """The regression test that protects the rehearsed demo path: a run
    where nobody ever uploads or pastes anything must keep producing the
    exact seeded epic, unchanged."""
    epic = _seeded_epic_only(eng)
    assert epic["epic_id"] == "EPIC-S7-001"
    assert epic["title"] == seed.EPIC.title
    assert epic["business_outcome"] == seed.EPIC.business_outcome
    assert epic["estimated_stories"] == seed.EPIC.estimated_stories


def test_create_epic_still_requires_analysis_first(eng):
    """test_epic_requires_analysis in test_factory_planning.py already
    covers this for the untouched path; this re-confirms it here too so a
    future edit to this file can't silently regress it."""
    with pytest.raises(EngineError):
        eng.intake_create_epic(Role.PRODUCT_ANALYST)


def test_create_epic_from_extraction_uses_extracted_content(eng):
    eng.intake_set_source(Role.PRODUCT_ANALYST, SOURCE_TEXT, filename="epic.md", source_kind="upload")
    eng.intake_extract(Role.PRODUCT_ANALYST)
    eng.intake_analyse(Role.PRODUCT_ANALYST)
    eng.intake_create_epic(Role.PRODUCT_ANALYST)
    epic = eng.state()["intake"]["epic"]
    assert epic["epic_id"] != "EPIC-S7-001"
    assert epic["epic_id"] == f"EPIC-{eng.run_id}"
    assert epic["title"] == "Claims Deductible Handling"
    assert epic["provenance"] == "rule_based"


def test_edit_extraction_updates_fields_and_stamps_editor(eng):
    eng.intake_set_source(Role.PRODUCT_ANALYST, SOURCE_TEXT, filename="epic.md", source_kind="upload")
    eng.intake_extract(Role.PRODUCT_ANALYST)
    eng.intake_edit_extraction(Role.BUSINESS_OWNER, {"epic_title": "Corrected Title"})
    ext = eng.state()["intake"]["extraction"]
    assert ext["epic_title"] == "Corrected Title"
    assert ext["edited_by"] == "business_owner"
    assert ext["edited_at"]


def test_edit_extraction_rejects_unknown_fields(eng):
    eng.intake_set_source(Role.PRODUCT_ANALYST, SOURCE_TEXT, filename="epic.md", source_kind="upload")
    eng.intake_extract(Role.PRODUCT_ANALYST)
    with pytest.raises(EngineError, match="not editable"):
        eng.intake_edit_extraction(Role.BUSINESS_OWNER, {"method": "live_llm"})


def test_edit_extraction_requires_extraction_first(eng):
    with pytest.raises(EngineError, match="No extraction"):
        eng.intake_edit_extraction(Role.BUSINESS_OWNER, {"epic_title": "x"})


def test_finalize_runs_analysis_when_missing_then_creates_epic(eng):
    eng.intake_set_source(Role.PRODUCT_ANALYST, SOURCE_TEXT, filename="epic.md", source_kind="upload")
    eng.intake_extract(Role.PRODUCT_ANALYST)
    eng.intake_finalize(Role.PRODUCT_ANALYST)
    state = eng.state()
    assert state["intake"]["analysis"] is not None
    assert state["intake"]["epic"]["title"] == "Claims Deductible Handling"


def test_finalize_does_not_rerun_existing_analysis(eng):
    eng.intake_analyse(Role.PRODUCT_ANALYST)
    first_generated_at = eng.state()["intake"]["analysis"]["generated_at"]
    eng.intake_set_source(Role.PRODUCT_ANALYST, SOURCE_TEXT, filename="epic.md", source_kind="upload")
    eng.intake_extract(Role.PRODUCT_ANALYST)
    eng.intake_finalize(Role.PRODUCT_ANALYST)
    assert eng.state()["intake"]["analysis"]["generated_at"] == first_generated_at
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_factory_intake_extraction.py -v`
Expected: FAIL — `test_create_epic_from_extraction_uses_extracted_content` fails (epic still matches seed); `intake_edit_extraction`/`intake_finalize` don't exist yet (`AttributeError`).

- [ ] **Step 3: Modify `intake_create_epic`**

Change:

```python
    def intake_create_epic(self, role: Role) -> None:
        roles.require("create_epic", role)
        if not self.store.exists("intake", "analysis.json"):
            raise EngineError("Run intake analysis before creating the epic")
        epic = seed.EPIC.model_copy(update={"created_at": now_iso()})
        self.store.write_json(epic, "intake", "epic.json")
        self._record(
            artifact_id=epic.epic_id, artifact_type="epic", payload=epic,
            author=epic.created_by, stage=Stage.INTAKE, action="create-epic",
            outcome="created", inputs=[seed.REQUIREMENT.request_id, "ANL-001"],
        )
        self._activity(
            stage=Stage.INTAKE, actor="intake-analysis", actor_type="simulation",
            workflow="epic-creation", artifact=epic.epic_id, duration_s=3.0,
            outcome="created",
        )
```

to:

```python
    def intake_create_epic(self, role: Role) -> None:
        roles.require("create_epic", role)
        if not self.store.exists("intake", "analysis.json"):
            raise EngineError("Run intake analysis before creating the epic")
        extraction = self.store.read_json_or(None, "intake", "extraction.json")
        if extraction is not None:
            req = self.store.read_json("intake", "requirement.json")
            req_count = len(extraction.get("extracted_requirements", []))
            epic = EpicRecord(
                epic_id=f"EPIC-{self.run_id}",
                title=extraction["epic_title"],
                business_outcome=extraction["business_objective"],
                estimated_stories=max(2, min(8, (req_count + 1) // 2)),
                status=Status.READY,
                created_by=f"intake-extraction ({extraction['method']})",
                provenance=Provenance(extraction["provenance"]),
            )
            epic_inputs = [req["request_id"], "EXT-001", "ANL-001"]
        else:
            epic = seed.EPIC.model_copy(update={"created_at": now_iso()})
            epic_inputs = [seed.REQUIREMENT.request_id, "ANL-001"]
        self.store.write_json(epic, "intake", "epic.json")
        self._record(
            artifact_id=epic.epic_id, artifact_type="epic", payload=epic,
            author=epic.created_by, stage=Stage.INTAKE, action="create-epic",
            outcome="created", inputs=epic_inputs,
        )
        self._activity(
            stage=Stage.INTAKE, actor="intake-analysis", actor_type="simulation",
            workflow="epic-creation", artifact=epic.epic_id, duration_s=3.0,
            outcome="created",
        )
```

- [ ] **Step 4: Add `intake_edit_extraction` and `intake_finalize`**

Add the following immediately after the modified `intake_create_epic` — the class attribute
`EDITABLE_EXTRACTION_FIELDS` right above `intake_edit_extraction`, mirroring how
`EDITABLE_STORY_FIELDS` sits right above the planning stage's own field-patch logic elsewhere
in this file:

```python
    EDITABLE_EXTRACTION_FIELDS = {
        "epic_title", "business_objective", "requirement_summary",
        "extracted_requirements",
    }

    def intake_edit_extraction(self, role: Role, patch: dict) -> None:
        roles.require("edit_requirement", role)
        data = self.store.read_json_or(None, "intake", "extraction.json")
        if data is None:
            raise EngineError("No extraction to edit — run extraction first")
        illegal = set(patch) - self.EDITABLE_EXTRACTION_FIELDS
        if illegal:
            raise EngineError(f"Fields not editable: {', '.join(sorted(illegal))}")
        data.update(patch)
        data["edited_by"] = role.value
        data["edited_at"] = now_iso()
        record = RequirementExtraction.model_validate(data)
        self.store.write_json(record, "intake", "extraction.json")
        self._record(
            artifact_id="EXT-001", artifact_type="requirement_extraction",
            payload=record, author=role.value, stage=Stage.INTAKE, action="edit",
            outcome=f"amended ({', '.join(sorted(patch))})",
        )
        self._activity(
            stage=Stage.INTAKE, actor=role.value, actor_type="human",
            workflow="extraction-edit", artifact="EXT-001",
            outcome="amended", details=", ".join(sorted(patch)),
        )

    def intake_finalize(self, role: Role) -> None:
        """One-shot action for the upload/paste panel's "Create Epic &
        Proceed to Planning" button: runs analysis first only if it hasn't
        run yet, then creates the epic. `run_intake_analysis` and
        `create_epic` are permitted to the identical pair of roles in
        roles.py, so this is a plain sequencing wrapper over the two
        existing, unmodified public methods — no new permission surface,
        and intake_create_epic's own precondition stays exactly as it was."""
        if not self.store.exists("intake", "analysis.json"):
            self.intake_analyse(role)
        self.intake_create_epic(role)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_factory_intake_extraction.py -v`
Expected: PASS (17 tests total in this file)

Run the pre-existing regression test explicitly to confirm it's untouched:
`pytest tests/test_factory_planning.py::test_epic_requires_analysis -v`
Expected: PASS

Run the full suite: `pytest tests/ -q`
Expected: all green

- [ ] **Step 6: Commit**

```bash
git add s7_delivery/factory/engine.py tests/test_factory_intake_extraction.py
git commit -m "feat: epic creation from extraction, intake_edit_extraction, intake_finalize"
```

---

### Task 7: HTTP endpoints

**Files:**
- Modify: `apps/control/server.py` (imports near the top; new endpoints inserted after `post_create_new_app_repo`, before the `# --- planning` section comment)
- Test: `tests/test_control_api.py` (append)

**Interfaces:**
- Consumes: `Engine.intake_set_source`, `Engine.intake_extract`, `Engine.intake_edit_extraction`, `Engine.intake_finalize` (Tasks 5–6); `extraction.decode_source`, `extraction.ExtractionError` (Task 2).
- Produces: `POST /api/runs/{run_id}/intake/upload-source`, `POST .../paste-source`, `POST .../re-extract`, `PATCH .../intake/extraction`, `POST .../intake/finalize-epic`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_control_api.py`:

```python
SOURCE_TEXT = """Claims Deductible Handling

Apply policy deductible during claim intake to ensure valid claim processing.

- Policy record must contain a deductible amount.
- Reject claim if claim amount is at or below the policy deductible.
"""


def test_upload_source_extracts_and_updates_requirement(client, run_id):
    res = client.post(
        f"/api/runs/{run_id}/intake/upload-source",
        data={"role": "product_analyst"},
        files={"file": ("epic.md", SOURCE_TEXT.encode(), "text/markdown")},
    )
    assert res.status_code == 200
    state = res.json()
    assert state["intake"]["requirement"]["title"] == "Claims Deductible Handling"
    assert state["intake"]["extraction"]["method"] == "rule_based"


def test_upload_source_rejects_unsupported_extension(client, run_id):
    res = client.post(
        f"/api/runs/{run_id}/intake/upload-source",
        data={"role": "product_analyst"},
        files={"file": ("epic.xlsx", b"data", "application/octet-stream")},
    )
    assert res.status_code == 400
    assert "Unsupported file type" in res.json()["detail"]


def test_upload_source_rejects_oversized_file(client, run_id):
    oversized = b"x" * (10 * 1024 * 1024 + 1)
    res = client.post(
        f"/api/runs/{run_id}/intake/upload-source",
        data={"role": "product_analyst"},
        files={"file": ("epic.txt", oversized, "text/plain")},
    )
    assert res.status_code == 400
    assert "10MB" in res.json()["detail"]


def test_paste_source_extracts(client, run_id):
    res = client.post(
        f"/api/runs/{run_id}/intake/paste-source",
        json={"role": "product_analyst", "text": SOURCE_TEXT},
    )
    assert res.status_code == 200
    assert res.json()["intake"]["extraction"]["epic_title"] == "Claims Deductible Handling"


def test_re_extract(client, run_id):
    client.post(f"/api/runs/{run_id}/intake/paste-source",
                json={"role": "product_analyst", "text": SOURCE_TEXT})
    res = client.post(f"/api/runs/{run_id}/intake/re-extract", json={"role": "product_analyst"})
    assert res.status_code == 200
    assert res.json()["intake"]["extraction"]["method"] == "rule_based"


def test_patch_extraction(client, run_id):
    client.post(f"/api/runs/{run_id}/intake/paste-source",
                json={"role": "product_analyst", "text": SOURCE_TEXT})
    res = client.patch(
        f"/api/runs/{run_id}/intake/extraction",
        json={"role": "business_owner", "patch": {"epic_title": "Corrected"}},
    )
    assert res.status_code == 200
    assert res.json()["intake"]["extraction"]["epic_title"] == "Corrected"


def test_finalize_epic_creates_epic_from_extraction(client, run_id):
    client.post(f"/api/runs/{run_id}/intake/paste-source",
                json={"role": "product_analyst", "text": SOURCE_TEXT})
    res = client.post(f"/api/runs/{run_id}/intake/finalize-epic", json={"role": "product_analyst"})
    assert res.status_code == 200
    state = res.json()
    assert state["intake"]["epic"]["title"] == "Claims Deductible Handling"
    assert state["intake"]["analysis"] is not None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_control_api.py -v -k "upload_source or paste_source or re_extract or patch_extraction or finalize_epic"`
Expected: FAIL — 404s (routes don't exist yet).

- [ ] **Step 3: Add the import and the five endpoints**

In `apps/control/server.py`, add to the existing import block (alongside `from s7_delivery.factory import seed`):

```python
from s7_delivery.factory import extraction, seed
```

Insert the following after `post_create_new_app_repo` (ends with `return eng.state()` around the current line 256) and before the `# --- planning (spec §8) -----` comment:

```python
@app.post("/api/runs/{run_id}/intake/upload-source")
async def post_intake_upload_source(
    run_id: str, role: str = Form(...), file: UploadFile = File(...)
) -> dict:
    eng = _engine(run_id)
    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail="File exceeds the 10MB demo limit")
    filename = file.filename or "document"
    try:
        text = extraction.decode_source(filename, content)
    except extraction.ExtractionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    r = _role(role)
    eng.intake_set_source(r, text, filename=filename, source_kind="upload", raw_content=content)
    eng.intake_extract(r)
    return eng.state()


class PasteSourceBody(BaseModel):
    role: str
    text: str


@app.post("/api/runs/{run_id}/intake/paste-source")
def post_intake_paste_source(run_id: str, body: PasteSourceBody) -> dict:
    eng = _engine(run_id)
    r = _role(body.role)
    eng.intake_set_source(r, body.text, source_kind="paste")
    eng.intake_extract(r)
    return eng.state()


@app.post("/api/runs/{run_id}/intake/re-extract")
def post_intake_re_extract(run_id: str, body: RoleBody) -> dict:
    eng = _engine(run_id)
    eng.intake_extract(_role(body.role))
    return eng.state()


class ExtractionPatch(BaseModel):
    role: str
    patch: dict


@app.patch("/api/runs/{run_id}/intake/extraction")
def patch_intake_extraction(run_id: str, body: ExtractionPatch) -> dict:
    eng = _engine(run_id)
    eng.intake_edit_extraction(_role(body.role), body.patch)
    return eng.state()


@app.post("/api/runs/{run_id}/intake/finalize-epic")
def post_intake_finalize_epic(run_id: str, body: RoleBody) -> dict:
    eng = _engine(run_id)
    eng.intake_finalize(_role(body.role))
    return eng.state()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_control_api.py -v`
Expected: PASS (all existing tests plus the 7 new ones)

Run the full suite: `pytest tests/ -q`
Expected: all green

- [ ] **Step 5: Commit**

```bash
git add apps/control/server.py tests/test_control_api.py
git commit -m "feat: HTTP endpoints for upload/paste requirement extraction"
```

---

### Task 8: Styles — dropzone, file row, tag chip, rule-based provenance badge

**Files:**
- Modify: `apps/control/static/styles.css:392` (after the `.prov-staged` line), `:487` (after the `.chip.priority-low` line)

**Interfaces:**
- Produces: CSS classes `.dropzone`, `.file-row`, `.chip.tag`, `.prov-rule_based` — consumed by Task 9's `app.js` changes.

- [ ] **Step 1: Add the provenance badge color**

In `apps/control/static/styles.css`, immediately after:

```css
.prov-staged { border: 2px solid var(--amber); background: #f9e2ac; color: #4d3800; }
```

add:

```css
.prov-rule_based { border-color: #2f6b5e; color: #1e453c; background: #e3f1ee; }
```

- [ ] **Step 2: Add the tag chip variant**

Immediately after:

```css
.chip.priority-low { color: var(--muted); border: 1px solid var(--border-strong); background: var(--surface-2); }
```

add:

```css
.chip.tag { color: var(--muted); border: 1px solid var(--border-strong); background: var(--surface-2); }
```

- [ ] **Step 3: Add dropzone and file-row styles**

In the same block (right after the `.chip.tag` rule just added), add:

```css
.dropzone {
  border: 2px dashed var(--border-strong);
  border-radius: var(--radius-md);
  padding: 22px;
  text-align: center;
  background: var(--surface-2);
}
.dropzone input[type="file"] { display: block; margin: 10px auto 0; font-size: 12.5px; }

.file-row {
  display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
  margin-top: 12px; padding: 8px 12px;
  border: 1px solid var(--border); border-radius: var(--radius-md);
  background: var(--surface-2); font-size: 12.5px;
}
```

- [ ] **Step 4: Verify visually**

There is no CSS test suite (plain static file, no build step, per CLAUDE.md hard rule 4). Verification happens in Task 9's manual browser check, once these classes are actually used.

- [ ] **Step 5: Commit**

```bash
git add apps/control/static/styles.css
git commit -m "style: dropzone, file-row, tag chip, rule-based provenance badge"
```

---

### Task 9: Frontend — Source Requirement / Extraction panel

**Files:**
- Modify: `apps/control/static/app.js` — insert two new functions (`sourceRequirementSection`, `openEditExtractionModal`) immediately before `function renderIntake()` (currently starts at line 404); modify the `return el("section", ...)` statement inside `renderIntake()` (currently lines 623–644).

**Interfaces:**
- Consumes: `el`, `api`, `act`, `go`, `toast`, `prov`, `openModal`/`closeModal`, `state` (all existing, top of `app.js`); the five endpoints from Task 7; `d.intake.source`, `d.intake.extraction` (Task 5's `state()` additions).

- [ ] **Step 1: Add the two new functions**

In `apps/control/static/app.js`, immediately before `function renderIntake() {` (currently line 404), insert:

```javascript
  function openEditExtractionModal(ext) {
    closeModal();
    const title = el("input", { type: "text", value: ext.epic_title });
    const objective = el("textarea", { rows: "3" }); objective.value = ext.business_objective;
    const summary = el("textarea", { rows: "3" }); summary.value = ext.requirement_summary;
    const reqs = el("textarea", { rows: "6" });
    reqs.value = ext.extracted_requirements.map((r) => r.text).join("\n");
    const modal = el("div", { id: "modal", class: "modal-overlay", onclick: (e) => { if (e.target === modal) closeModal(); } },
      el("div", { class: "modal card" },
        el("div", { class: "card-head" },
          el("h3", { text: "Edit Extracted Epic" }),
          el("button", { class: "kebab", text: "✕", onclick: closeModal })),
        el("div", {}, el("label", { class: "fld", text: "Epic Title" }), title),
        el("div", {}, el("label", { class: "fld", text: "Business Objective" }), objective),
        el("div", {}, el("label", { class: "fld", text: "Requirement Summary" }), summary),
        el("div", {}, el("label", { class: "fld", text: "Extracted Requirements (one per line)" }), reqs),
        el("div", { class: "actions-row" },
          el("button", {
            class: "primary sq", text: "Save",
            onclick: () => {
              const lines = reqs.value.split("\n").map((t) => t.trim()).filter(Boolean);
              const patch = {
                epic_title: title.value.trim(),
                business_objective: objective.value.trim(),
                requirement_summary: summary.value.trim(),
                extracted_requirements: lines.map((text, i) =>
                  ({ rule_id: `REQ-${String(i + 1).padStart(2, "0")}`, text })),
              };
              api(`/api/runs/${state.runId}/intake/extraction`, {
                method: "PATCH", body: JSON.stringify({ role: state.role, patch }),
              }).then((data) => { state.data = data; render(); toast("Extraction updated"); closeModal(); })
                .catch((err) => toast(err.message, true));
            },
          }),
          el("button", { class: "ghost", text: "Cancel", onclick: closeModal }),
        )));
    document.body.appendChild(modal);
    title.focus();
  }

  function sourceRequirementSection(d) {
    const ext = d.intake?.extraction;
    const isLive = d.run?.mode === "live";

    const uploadInput = el("input", { type: "file", accept: ".txt,.md,.pdf,.docx" });
    const uploadPane = el("div", {},
      el("div", { class: "dropzone" },
        el("p", { class: "hint", text: "Upload a requirement or epic document" }),
        uploadInput,
        el("p", { class: "hint", style: "margin-top:8px", text: "Supported formats: PDF, DOCX, TXT, MD — up to 10MB" })),
      el("button", {
        class: "primary sq block", style: "margin-top:10px", text: "⬆ Upload & Extract",
        onclick: async () => {
          const file = uploadInput.files?.[0];
          if (!file) { toast("Choose a file first", true); return; }
          const form = new FormData();
          form.append("role", state.role);
          form.append("file", file);
          try {
            state.data = await api(`/api/runs/${state.runId}/intake/upload-source`, { method: "POST", headers: {}, body: form });
            render();
            toast(`${file.name} extracted`);
          } catch (err) { toast(err.message, true); }
        },
      }));

    const pasteArea = el("textarea", { rows: "8", placeholder: "Paste the requirement or epic text here…" });
    const pastePane = el("div", { style: "display:none" }, pasteArea, el("button", {
      class: "primary sq block", style: "margin-top:10px", text: "Extract from pasted text",
      onclick: () => {
        if (!pasteArea.value.trim()) { toast("Paste some text first", true); return; }
        act("/intake/paste-source", { text: pasteArea.value }, "Text extracted");
      },
    }));

    const uploadTab = el("button", { class: "on", text: "Upload File" });
    const pasteTab = el("button", { text: "Paste Text" });
    uploadTab.onclick = () => {
      uploadTab.className = "on"; pasteTab.className = "";
      uploadPane.style.display = ""; pastePane.style.display = "none";
    };
    pasteTab.onclick = () => {
      pasteTab.className = "on"; uploadTab.className = "";
      pastePane.style.display = ""; uploadPane.style.display = "none";
    };

    const sourceCard = el("div", { class: "card" },
      el("h3", { text: "1. Source Requirement" }),
      el("p", { class: "hint", text: "Upload a file or paste text — the requirement is extracted from what you actually give it." }),
      el("div", { class: "tabs", style: "margin-top:10px" }, uploadTab, pasteTab),
      uploadPane, pastePane,
      d.intake?.source ? el("div", { class: "file-row" },
        el("span", { class: "mono", text: d.intake.source.filename || "(pasted text)" }),
        el("span", { class: "chip tag", text: `${d.intake.source.text.length.toLocaleString()} chars` }),
        el("span", { class: "prov prov-human", text: "SET" })) : null);

    const extractionCard = el("div", { class: "card" },
      el("div", { class: "section-title" },
        el("h3", { text: ext ? (ext.method === "live_llm" ? "2. AI Extraction" : "2. Extraction (Rule-Based)") : "2. Extraction" }),
        ext ? prov(ext.provenance) : null),
      !ext
        ? el("p", { class: "hint", text: "Upload or paste a source above to extract a requirement from it." })
        : el("div", {},
            el("div", { class: "kv", style: "grid-template-columns: 160px 1fr" },
              el("b", { text: "Epic Title" }), el("span", { text: ext.epic_title }),
              el("b", { text: "Business Objective" }), el("span", { text: ext.business_objective }),
              el("b", { text: "Requirement Summary" }), el("span", { text: ext.requirement_summary })),
            el("h4", { style: "margin-top:14px; font-size:12.5px; color:var(--muted)", text: "Extracted Requirements" }),
            el("ul", { class: "plain" }, ext.extracted_requirements.map((r) =>
              el("li", {},
                el("span", { class: "chip tag", style: "margin-right:8px", text: r.rule_id }),
                r.text))),
            ext.edited_by ? el("p", { class: "hint", style: "margin-top:8px",
              text: `Edited by ${ext.edited_by} at ${ext.edited_at}` }) : null,
            el("div", { class: "actions-row", style: "margin-top:14px" },
              el("button", { class: "outline", text: "✎ Edit Extracted Epic", onclick: () => openEditExtractionModal(ext) }),
              el("button", {
                class: "primary sq", text: "Create Epic & Proceed to Planning →",
                onclick: () => act("/intake/finalize-epic", {}, "Epic created")
                  .then((ok) => { if (ok) go("epic_to_stories"); }),
              })),
            !isLive ? el("p", { class: "hint", style: "margin-top:10px",
              text: "Simulation mode demonstrates extraction from your actual document; downstream " +
                "planning still follows the rehearsed demo scenario, exactly as it does for every run " +
                "in simulation mode today." }) : null));

    return el("div", { class: "grid cols-2", style: "margin-bottom:14px" }, sourceCard, extractionCard);
  }

```

- [ ] **Step 2: Wire the new section into `renderIntake()`'s return statement**

In `apps/control/static/app.js`, inside `renderIntake()`, change:

```javascript
    return el("section", { class: "page-with-rail" },
      el("div", {},
        el("div", { class: "page-head", style: "margin-bottom:16px" },
          el("h2", { text: "Intake — AI Analysis" }),
          el("span", { class: "hint", text: "The analysis model reviews the requirement and extracts key information. A human passes the gate." })),
        repoCard ? el("div", { style: "margin-bottom:14px" }, repoCard) : null,
```

to:

```javascript
    return el("section", { class: "page-with-rail" },
      el("div", {},
        el("div", { class: "page-head", style: "margin-bottom:16px" },
          el("h2", { text: "Intake — Requirement Input" }),
          el("span", { class: "hint", text: "Upload your business epic or requirement. Extraction reads the actual document; a human passes the gate." })),
        sourceRequirementSection(d),
        repoCard ? el("div", { style: "margin-bottom:14px" }, repoCard) : null,
```

- [ ] **Step 3: Start the dev server and verify in the browser**

Invoke the `run` skill (or, if it reports no project skill covers this app, run directly):

```bash
demo/run_control.sh
```

Then, using the Chrome MCP tools (load them via `ToolSearch` with `select:mcp__claude-in-chrome__tabs_context_mcp,mcp__claude-in-chrome__navigate,mcp__claude-in-chrome__computer,mcp__claude-in-chrome__read_page,mcp__claude-in-chrome__tabs_create_mcp,mcp__claude-in-chrome__file_upload` if not already loaded), walk through:

1. Navigate to the Control Centre, open the Intake tab. Confirm the new "1. Source Requirement" / "2. Extraction" two-panel layout renders above the existing Requirement Summary card, and that everything below (Requirement Summary, Intake Gate, AI Analysis, rail buttons) still renders exactly as before.
2. Paste some short requirement text (e.g. a paragraph plus 2–3 bullet points) into the "Paste Text" tab and click "Extract from pasted text". Confirm the right panel populates with a title, objective, summary, and `REQ-xx` bullets, badged "RULE_BASED" (not "AI").
3. Click "✎ Edit Extracted Epic", change the title, save, and confirm the panel updates and shows "Edited by … at …".
4. Click "Create Epic & Proceed to Planning →" and confirm it navigates to the Planning tab and the epic there shows the edited title, not `EPIC-S7-001`.
5. Start a **fresh** run (or reset the current one) and, **without touching the new panel at all**, walk the existing rail buttons (Regenerate Analysis → Generate Epic → Pass Intake Gate) exactly as before. Confirm the epic is still `EPIC-S7-001` with its original seeded content — the default rehearsed path must look and behave identically to before this change.
6. Switch the run to live mode (if an API key / replay recording is available) and confirm the extraction panel's header reads "AI Extraction" and badges `LIVE_AI` — do not attempt this if no live credentials are configured; note in the task report that it was skipped and why.

If any step fails, fix the relevant file and re-verify — this is the acceptance test for the whole plan, since there is no automated JS test suite in this repo (confirmed: no `package.json`, no JS test runner — plain static file per CLAUDE.md hard rule 4).

- [ ] **Step 4: Run the full Python test suite once more**

Run: `pytest tests/ -q`
Expected: all green (this task changes no Python, but confirms nothing in the dev-server run left stray state affecting other tests — it shouldn't, since server state lives under `artifacts/runs/`, not in test fixtures).

- [ ] **Step 5: Commit**

```bash
git add apps/control/static/app.js
git commit -m "feat(ui): intake upload/paste requirement extraction panel"
```

---

### Task 10: CLAUDE.md / AGENTS.md sync

**Files:**
- Modify: `CLAUDE.md`
- Modify: `AGENTS.md`

**Interfaces:** none — documentation only.

- [ ] **Step 1: Update `CLAUDE.md`**

Add a new paragraph under the existing "**Artifact export and delivery handoff, added 2026-08-08.**" paragraph (in the section that lists dated additions), following the same style:

```markdown
**Intake upload/paste requirement extraction, added 2026-08-08.** The
Intake stage now opens with a genuine extraction front door: upload a file
(`.txt`/`.md`/`.pdf`/`.docx`) or paste text, and the requirement's title,
business objective, summary and numbered requirement bullets are extracted
from what was actually given — not canned output. Simulation mode uses a
real, deterministic, non-AI parser (`s7_delivery/factory/extraction.py`),
badged `RULE_BASED` and labelled "Extraction (Rule-Based)" rather than "AI
Extraction" — presenting a heuristic as AI output is exactly the
mislabelling § Staged output forbids. Live mode calls the model for real
(`live_intake.run_extraction`), labelled "AI Extraction" and badged
`LIVE_AI`/`REPLAYED_AI` like every other live call. A run where nobody
uploads or pastes anything is completely unaffected — `intake_create_epic`
still produces the exact seeded `EPIC-S7-001` content it always has;
extraction-driven epic creation is additive, gated behind an explicit
`intake/source.json` marker that only exists once a human provides real
source content.
```

- [ ] **Step 2: Update `AGENTS.md`**

`AGENTS.md` mirrors `CLAUDE.md` in a more condensed style (compare its "Requirement routing and new-application onboarding" paragraph at line 191 against `CLAUDE.md`'s longer version of the same entry). Immediately after the existing "Artifact export and delivery handoff, added 2026-08-08." paragraph (ends at line 216, "...this system never automates."), add:

```markdown

**Intake upload/paste requirement extraction, added 2026-08-08.** Intake
now opens with an extraction front door: upload `.txt`/`.md`/`.pdf`/`.docx`
or paste text, and the requirement's title, objective, summary and numbered
requirements are extracted from what was actually given. Simulation mode
uses a real, deterministic, non-AI parser (`s7_delivery/factory/
extraction.py`), badged `RULE_BASED` and labelled "Extraction (Rule-Based)"
rather than "AI Extraction" — never presenting a heuristic as AI output.
Live mode calls the model for real (`live_intake.run_extraction`), labelled
"AI Extraction". A run where nobody uploads or pastes anything is
unaffected — `intake_create_epic` still produces the exact seeded
`EPIC-S7-001` content; extraction-driven epic creation is additive, gated
behind an explicit `intake/source.json` marker.
```

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md AGENTS.md
git commit -m "docs: intake upload/paste requirement extraction — status"
```

---

## Post-plan verification

After all ten tasks are committed:

```bash
pytest tests/ -q
ruff check .
```

Both must be clean. Then do one final manual pass in the browser (Task 9, Step 3, items 1–5) against a fully fresh `git clone` (or `artifacts/runs/` wiped) to confirm the default demo path is untouched end to end, since that is this plan's single hardest constraint.
