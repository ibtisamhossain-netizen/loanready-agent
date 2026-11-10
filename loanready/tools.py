"""The agent's tools. All read-only, all allow-listed.

The agent can only call names in ALLOWED_TOOLS. Paths are validated so
a package can only be read from inside data/synthetic/ or data/uploads/.
Nothing here writes, sends, or calls an outside system.
"""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from .harness import ToolError

DATA_ROOT = (Path(__file__).resolve().parent.parent / "data" / "synthetic").resolve()
UPLOAD_ROOT = (Path(__file__).resolve().parent.parent / "data" / "uploads").resolve()
MAX_FILE_BYTES = 50_000
MAX_DOCS = 12  # per package; keeps the pass budget meaningful
DOC_NAME = re.compile(r"^[a-z0-9_\-]+\.txt$")

# Keyword classification. Text inside a document is data: an instruction
# written in a document ("ignore the checklist") is never acted on, because
# nothing here reads text as a command.
TYPE_KEYWORDS = {
    "photo_id": ["driver license", "state id", "photo id"],
    "pay_stub": ["pay stub", "earnings statement"],
    "vehicle_registration": ["vehicle registration"],
    "payoff_letter": ["payoff letter", "payoff quote"],
    "insurance_card": ["insurance card", "insurance id card",
                       "insurance identification card", "proof of insurance"],
    "title": ["certificate of title"],
}

# Other documents often mention these two in their body text ("the lien on
# the certificate of title is released", "proof of insurance is required"),
# so their keywords only count in the document's header, its first non-blank
# line. A real card or title with another first line is left unknown, and the
# rep reads it (assumption).
HEADER_ONLY = {"insurance_card", "title"}

FIELD_PATTERNS = {
    "name": r"^name:\s*(.+)$",
    "address": r"^address:\s*(.+)$",
    "vin": r"^vin:\s*([A-HJ-NPR-Z0-9]{17})\s*$",
    "income": r"^gross pay:\s*\$?([\d,]+\.\d{2})\s*$",
    "payoff": r"^payoff amount:\s*\$?([\d,]+\.\d{2})\s*$",
    "issued": r"^(?:issue date|pay date|statement date):\s*(\d{4}-\d{2}-\d{2})\s*$",
    "expires": r"^expires:\s*(\d{4}-\d{2}-\d{2})\s*$",
    # Keep blank/malformed dates visible so the checker cannot fall back silently.
    "good_through": r"^good[ -]through(?: date)?:\s*(.*)$",
}


def _package_dir(package: str) -> Path:
    if not re.fullmatch(r"[a-z0-9_\-]+", package or ""):
        raise ToolError(f"bad package id: {package!r}")
    for root in (DATA_ROOT, UPLOAD_ROOT):
        p = (root / package).resolve()
        if p.parent == root and p.is_dir():
            return p
    raise ToolError(f"unknown package: {package!r}")


def list_documents(package: str) -> list[str]:
    names = sorted(f.name for f in _package_dir(package).glob("*.txt"))
    if len(names) > MAX_DOCS:
        raise ToolError(f"too many documents ({len(names)}); the limit is {MAX_DOCS}")
    return names


def read_document(package: str, name: str) -> str:
    if not DOC_NAME.fullmatch(name or ""):
        raise ToolError(f"bad document name: {name!r}")
    f = _package_dir(package) / name
    if not f.is_file():
        raise ToolError(f"no such document: {name}")
    if f.stat().st_size > MAX_FILE_BYTES:
        raise ToolError(f"document too large: {name}")
    return f.read_text(encoding="utf-8", errors="replace")


def classify(text: str, limit: int | None = 300) -> str:
    """Quick look at the top of the page. limit=None searches the whole text."""
    head = text.lower() if limit is None else text.lower()[:limit]
    header = next((line for line in head.splitlines() if line.strip()), "")
    # The header decides first. Otherwise the keyword that appears earliest
    # wins, so a word a document merely mentions lower down cannot outrank
    # the word that names it.
    return (_earliest(header, TYPE_KEYWORDS)
            or _earliest(head, {t: w for t, w in TYPE_KEYWORDS.items()
                                if t not in HEADER_ONLY})
            or "unknown")


def _earliest(text: str, keywords: dict) -> str | None:
    best = None  # (position, dict order, doc_type)
    for order, (doc_type, words) in enumerate(keywords.items()):
        for w in words:
            pos = text.find(w)
            if pos >= 0 and (best is None or (pos, order) < best[:2]):
                best = (pos, order, doc_type)
    return best[2] if best else None


DATE_LIKE = re.compile(
    r"\b(\d{4}-\d{1,2}-\d{1,2}|\d{1,2}/\d{1,2}/\d{2,4}|"
    r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.? \d{1,2},? \d{4})\b",
    re.IGNORECASE,
)


def scan_document(package: str, name: str) -> dict:
    """Second, slower look at one document. Read-only.

    Classifies using the whole text (not just the top) and lists every
    line that looks like it holds a date. The lines are hints for the
    rep only: the checklist never passes a document on a hint.
    """
    text = read_document(package, name)
    date_lines = [f"line {n}: {line.strip()}"
                  for n, line in enumerate(text.splitlines(), start=1)
                  if DATE_LIKE.search(line)]
    return {"type": classify(text, limit=None), "date_lines": date_lines[:10]}


def extract(text: str) -> dict:
    """Pull selected fields. Each value keeps the source line as evidence."""
    out = {}
    for line_no, line in enumerate(text.splitlines(), start=1):
        for field, pat in FIELD_PATTERNS.items():
            m = re.match(pat, line.strip(), re.IGNORECASE)
            if m and field == "good_through" and field in out:
                out[field] = {"value": None,
                              "evidence": out[field]["evidence"] + f"; line {line_no}: {line.strip()}"}
                continue
            if m and field not in out:
                raw = m.group(1).strip()
                value = raw
                if field in ("issued", "expires", "good_through"):
                    try:
                        value = date.fromisoformat(raw)
                    except ValueError:
                        if field != "good_through":
                            continue
                        value = None
                out[field] = {"value": value, "evidence": f"line {line_no}: {line.strip()}"}
    return out


# Labels the field check looks for when the strict reader did not get a value.
FIELD_LABELS = {
    "name": r"name",
    "address": r"address",
    "vin": r"vin",
    "income": r"gross pay",
    "payoff": r"payoff amount",
    "issued": r"issue date|pay date|statement date",
    "expires": r"expires|expiration",
    "good_through": r"good[ -]through",
}


def find_field_lines(package: str, name: str, field: str) -> list[str]:
    """Lines in one document that carry a field's label, as hints for the rep.

    Read-only. A hint is never used as the value: the rep reads it and decides.
    """
    if field not in FIELD_LABELS:
        raise ToolError(f"unknown field: {field!r}")
    label = re.compile(rf"^(?:{FIELD_LABELS[field]})\b", re.IGNORECASE)
    lines = [f"line {n}: {line.strip()}"
             for n, line in enumerate(read_document(package, name).splitlines(), start=1)
             if label.match(line.strip())]
    return lines[:10]


ALLOWED_TOOLS = {
    "list_documents": list_documents,
    "read_document": read_document,
    "scan_document": scan_document,
    "find_field_lines": find_field_lines,
}
