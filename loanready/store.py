"""Save uploaded documents and review results locally. Synthetic data only.

Uploads go to data/uploads/<application id>/ and results go to a SQLite file.
Both are ignored by git. Nothing leaves this machine.
"""
import re
import sqlite3
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

from . import tools

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "loanready.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS application (
    id TEXT PRIMARY KEY, loan_type TEXT NOT NULL, visit_date TEXT NOT NULL, status TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS document (
    id INTEGER PRIMARY KEY, application_id TEXT NOT NULL REFERENCES application(id),
    file_name TEXT NOT NULL, detected_type TEXT NOT NULL, stored_path TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS extracted_field (
    id INTEGER PRIMARY KEY, document_id INTEGER NOT NULL REFERENCES document(id),
    field_name TEXT NOT NULL, value TEXT, source_line TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS checklist_result (
    id INTEGER PRIMARY KEY, application_id TEXT NOT NULL REFERENCES application(id),
    required_document TEXT NOT NULL, status TEXT NOT NULL, rule_applied TEXT NOT NULL,
    checked_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS open_file (
    package TEXT PRIMARY KEY, application_id TEXT NOT NULL REFERENCES application(id),
    last_activity TEXT NOT NULL, next_follow_up TEXT, notes TEXT NOT NULL DEFAULT '', closed_on TEXT
);
CREATE TABLE IF NOT EXISTS field_review (
    id INTEGER PRIMARY KEY, package TEXT NOT NULL, file_name TEXT NOT NULL, field_name TEXT NOT NULL,
    action TEXT NOT NULL, original_value TEXT, new_value TEXT, reviewed_on TEXT NOT NULL
);
"""


def clean_name(name: str) -> str:
    """Return a safe .txt file name, or refuse the upload."""
    cleaned = re.sub(r"\s+", "_", Path(name or "").name.strip().lower())
    if not tools.DOC_NAME.fullmatch(cleaned):
        raise tools.ToolError(f"only simple .txt file names are accepted: {name!r}")
    return cleaned


def save_uploads(files: list) -> str:
    """Save (name, bytes) pairs in a new application folder and return its id."""
    if not files:
        raise tools.ToolError("no documents uploaded")
    if len(files) > tools.MAX_DOCS:
        raise tools.ToolError(f"too many documents ({len(files)}); the limit is {tools.MAX_DOCS}")
    cleaned = {}
    for name, data in files:
        safe = clean_name(name)
        if safe in cleaned:
            raise tools.ToolError(f"duplicate file name: {safe}")
        if len(data) > tools.MAX_FILE_BYTES:
            raise tools.ToolError(f"document too large: {safe}")
        cleaned[safe] = data
    app_id = f"app-{uuid.uuid4().hex[:8]}"
    folder = tools.UPLOAD_ROOT / app_id
    folder.mkdir(parents=True)
    for safe, data in cleaned.items():
        (folder / safe).write_bytes(data)
    return app_id


def _text(value):
    return value.isoformat() if isinstance(value, date) else value


def save_review(state: dict, visit_date: date, db_path=None) -> str:
    """Store one review and return its record id. Each run gets a new record."""
    db_path = Path(db_path or DB_PATH)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    record_id = f"{state['package']}-{uuid.uuid4().hex[:6]}"
    results = state["checklist"] or []
    status = "needs review" if any(r["status"] != "ok" for r in results) or not results else "ready"
    checked_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    conn = sqlite3.connect(db_path)
    try:
        with conn:
            conn.executescript(SCHEMA)
            conn.execute("INSERT INTO application VALUES (?, ?, ?, ?)",
                         (record_id, "auto refinance", visit_date.isoformat(), status))
            for name, doc in state["read"].items():
                cur = conn.execute(
                    "INSERT INTO document (application_id, file_name, detected_type, stored_path) VALUES (?, ?, ?, ?)",
                    (record_id, name, doc["type"], f"{state['package']}/{name}"))
                conn.executemany(
                    "INSERT INTO extracted_field (document_id, field_name, value, source_line) VALUES (?, ?, ?, ?)",
                    [(cur.lastrowid, k, _text(v["value"]), v["evidence"]) for k, v in doc["fields"].items()])
            conn.executemany(
                "INSERT INTO checklist_result (application_id, required_document, status, rule_applied, checked_at) "
                "VALUES (?, ?, ?, ?, ?)",
                [(record_id, r["doc"], r["status"], r["rule"], checked_at) for r in results])
            # One open file per package: a new check reopens it and keeps the rep's date and notes.
            conn.execute(
                "INSERT INTO open_file (package, application_id, last_activity) VALUES (?, ?, ?) "
                "ON CONFLICT(package) DO UPDATE SET application_id = excluded.application_id, "
                "last_activity = max(last_activity, excluded.last_activity), closed_on = NULL",
                (state["package"], record_id, visit_date.isoformat()))
    finally:
        conn.close()
    return record_id


def _read(db_path, query: str, args: tuple = ()) -> list:
    """Rows from the local database, or none if nothing has been saved yet."""
    db_path = Path(db_path or DB_PATH)
    if not db_path.exists():
        return []
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(SCHEMA)
        return conn.execute(query, args).fetchall()
    finally:
        conn.close()


def open_files(db_path=None) -> list[dict]:
    """Every file not closed yet, with the statuses from its last saved check."""
    rows = _read(db_path, "SELECT package, application_id, last_activity, next_follow_up, notes "
                          "FROM open_file WHERE closed_on IS NULL ORDER BY package")
    files = []
    for package, application_id, last_activity, next_follow_up, notes in rows:
        statuses = _read(db_path, "SELECT required_document, status FROM checklist_result "
                                  "WHERE application_id = ?", (application_id,))
        files.append({"package": package, "application_id": application_id,
                      "last_activity": last_activity, "next_follow_up": next_follow_up,
                      "notes": notes, "last_statuses": dict(statuses)})
    return files


def update_file(package: str, today: date, next_follow_up: date = None, notes: str = None,
                close: bool = False, db_path=None) -> None:
    """The rep's changes to an open file. Only the rep's actions call this."""
    db_path = Path(db_path or DB_PATH)
    conn = sqlite3.connect(db_path)
    try:
        with conn:
            conn.executescript(SCHEMA)
            found = conn.execute(
                "UPDATE open_file SET last_activity = ?, "
                "next_follow_up = coalesce(?, next_follow_up), notes = coalesce(?, notes), "
                "closed_on = ? WHERE package = ?",
                (today.isoformat(), next_follow_up.isoformat() if next_follow_up else None, notes,
                 today.isoformat() if close else None, package)).rowcount
    finally:
        conn.close()
    if not found:
        raise tools.ToolError(f"not an open file: {package!r}")


def save_field_review(package: str, review: dict, today: date, db_path=None) -> None:
    """Record a rep's correction or rejection. The source document is not changed."""
    db_path = Path(db_path or DB_PATH)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        with conn:
            conn.executescript(SCHEMA)
            conn.execute(
                "INSERT INTO field_review (package, file_name, field_name, action, original_value, "
                "new_value, reviewed_on) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (package, review["file"], review["field"], review["action"],
                 _text(review.get("original")), _text(review.get("value")), today.isoformat()))
    finally:
        conn.close()


def field_reviews(package: str, db_path=None) -> list[dict]:
    """A package's saved reviews, oldest first, so the newest one wins."""
    rows = _read(db_path, "SELECT file_name, field_name, action, new_value FROM field_review "
                          "WHERE package = ? ORDER BY id", (package,))
    return [{"file": f, "field": k, "action": a, "value": v} for f, k, a, v in rows]
