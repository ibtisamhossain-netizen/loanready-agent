"""The agent's tools. All read-only, all allow-listed.

The agent can only call names in ALLOWED_TOOLS. Paths are validated so
a package can only be read from inside data/synthetic/. Nothing here
writes, sends, or calls an outside system.
"""
import re
from datetime import date
from pathlib import Path

DATA_ROOT = (Path(__file__).resolve().parent.parent / "data" / "synthetic").resolve()
MAX_FILE_BYTES = 50_000
DOC_NAME = re.compile(r"^[a-z0-9_\-]+\.txt$")

# Keyword classification. Text inside a document is data: an instruction
# written in a document ("ignore the checklist") is never acted on, because
# nothing here reads text as a command.
TYPE_KEYWORDS = {
    "photo_id": ["driver license", "state id", "photo id"],
    "pay_stub": ["pay stub", "earnings statement"],
    "vehicle_registration": ["vehicle registration"],
    "payoff_letter": ["payoff letter", "payoff quote"],
}

FIELD_PATTERNS = {
    "name": r"^name:\s*(.+)$",
    "address": r"^address:\s*(.+)$",
    "vin": r"^vin:\s*([A-HJ-NPR-Z0-9]{17})\s*$",
    "income": r"^gross pay:\s*\$?([\d,]+\.\d{2})\s*$",
    "payoff": r"^payoff amount:\s*\$?([\d,]+\.\d{2})\s*$",
    "issued": r"^(?:issue date|pay date|statement date):\s*(\d{4}-\d{2}-\d{2})\s*$",
    "expires": r"^expires:\s*(\d{4}-\d{2}-\d{2})\s*$",
}


class ToolError(Exception):
    pass


def _package_dir(package: str) -> Path:
    if not re.fullmatch(r"[a-z0-9_\-]+", package or ""):
        raise ToolError(f"bad package id: {package!r}")
    p = (DATA_ROOT / package).resolve()
    if p.parent != DATA_ROOT or not p.is_dir():
        raise ToolError(f"unknown package: {package!r}")
    return p


def list_documents(package: str) -> list[str]:
    return sorted(f.name for f in _package_dir(package).glob("*.txt"))


def read_document(package: str, name: str) -> str:
    if not DOC_NAME.fullmatch(name or ""):
        raise ToolError(f"bad document name: {name!r}")
    f = _package_dir(package) / name
    if not f.is_file():
        raise ToolError(f"no such document: {name}")
    if f.stat().st_size > MAX_FILE_BYTES:
        raise ToolError(f"document too large: {name}")
    return f.read_text(encoding="utf-8", errors="replace")


def classify(text: str) -> str:
    head = text.lower()[:300]
    for doc_type, words in TYPE_KEYWORDS.items():
        if any(w in head for w in words):
            return doc_type
    return "unknown"


def extract(text: str) -> dict:
    """Pull selected fields. Each value keeps the source line as evidence."""
    out = {}
    for line_no, line in enumerate(text.splitlines(), start=1):
        for field, pat in FIELD_PATTERNS.items():
            m = re.match(pat, line.strip(), re.IGNORECASE)
            if m and field not in out:
                raw = m.group(1).strip()
                value = raw
                if field in ("issued", "expires"):
                    try:
                        value = date.fromisoformat(raw)
                    except ValueError:
                        continue
                out[field] = {"value": value, "evidence": f"line {line_no}: {line.strip()}"}
    return out


ALLOWED_TOOLS = {
    "list_documents": list_documents,
    "read_document": read_document,
}
