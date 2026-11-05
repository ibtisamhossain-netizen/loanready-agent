import sqlite3
from datetime import date
from pathlib import Path

import pytest

from loanready import agent, store, tools

AS_OF = date(2026, 11, 4)
PKG11 = Path(__file__).resolve().parent.parent / "data" / "synthetic" / "pkg11"


@pytest.fixture
def uploads(tmp_path, monkeypatch):
    monkeypatch.setattr(tools, "UPLOAD_ROOT", tmp_path.resolve())
    return tmp_path


def package_files():
    return [(f.name, f.read_bytes()) for f in sorted(PKG11.glob("*.txt"))]


def test_uploaded_package_runs_end_to_end_and_saves(uploads):
    app_id = store.save_uploads(package_files())
    state = agent.review(app_id, AS_OF)
    assert state["stop_reason"].startswith("done")
    assert {r["doc"]: r["status"] for r in agent.flags(state)} == {"payoff_letter": "stale"}

    db = uploads / "test.db"
    record = store.save_review(state, AS_OF, db_path=db)
    conn = sqlite3.connect(db)
    try:
        assert conn.execute("SELECT status FROM application WHERE id = ?", (record,)).fetchone() == ("needs review",)
        assert conn.execute("SELECT count(*) FROM document").fetchone() == (4,)
        assert conn.execute("SELECT count(*) FROM checklist_result").fetchone() == (4,)
        assert conn.execute("SELECT source_line FROM extracted_field WHERE field_name = 'good_through'"
                            ).fetchone() == ("line 6: Good through: 2026-11-03",)
    finally:
        conn.close()


@pytest.mark.parametrize("name", ["evil.exe", "photo.pdf", "..", ".env", "", "a/.txt"])
def test_rejects_unsafe_or_non_text_uploads(uploads, name):
    with pytest.raises(tools.ToolError):
        store.save_uploads([(name, b"x")])
    assert list(uploads.iterdir()) == []


def test_path_parts_are_stripped_from_upload_names(uploads):
    app_id = store.save_uploads([("../../Pay Stub.txt", b"PAY STUB")])
    assert [p.name for p in (uploads / app_id).iterdir()] == ["pay_stub.txt"]


def test_rejects_oversize_and_duplicate_uploads(uploads):
    with pytest.raises(tools.ToolError):
        store.save_uploads([("big.txt", b"x" * (tools.MAX_FILE_BYTES + 1))])
    with pytest.raises(tools.ToolError):
        store.save_uploads([("a.txt", b"1"), ("A.txt", b"2")])
    with pytest.raises(tools.ToolError):
        store.save_uploads([])


def test_upload_folder_cannot_escape_its_root(uploads):
    with pytest.raises(tools.ToolError):
        tools.list_documents("../app")


def test_screen_runs_sample_and_shows_flag_with_source(tmp_path, monkeypatch):
    streamlit_testing = pytest.importorskip("streamlit.testing.v1")
    monkeypatch.setattr(store, "DB_PATH", tmp_path / "screen.db")
    app = streamlit_testing.AppTest.from_file(str(PKG11.parent.parent.parent / "app.py"), default_timeout=30)
    app.run()
    assert not app.exception
    next(b for b in app.button if b.label == "Check package").click()
    app.run()
    assert not app.exception
    page = " ".join(m.value for m in app.markdown)
    assert "Ask the member for 1 document before they leave." in page
    assert "A new payoff letter from the current lender." in page
    assert "line 6: Good through: 2026-11-03" in page



def test_screen_escapes_document_text(uploads, tmp_path, monkeypatch):
    """An uploaded file's text is shown as text, never as markup."""
    pytest.importorskip("streamlit")
    monkeypatch.setattr(store, "DB_PATH", tmp_path / "screen.db")
    app_id = store.save_uploads([("note.txt", b"PAY STUB\n<script>alert(1)</script>\nPay date: Oct 24, 2026\n")])
    state = agent.review(app_id, AS_OF)
    import importlib.util
    spec = importlib.util.spec_from_file_location("lr_app", PKG11.parent.parent.parent / "app.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    html = module.fields_html(state, "note.txt", state["read"]["note.txt"])
    assert "<script>" not in html and "&lt;script&gt;" in html
