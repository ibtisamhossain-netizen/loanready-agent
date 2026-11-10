"""Insurance card and NY Certificate of Title (research, Nov 10, 2026).

Both rules are assumptions in loanready/checklist.py, not confirmed with MCU.
"""
import importlib.util
from datetime import date
from pathlib import Path

import pytest

from loanready import agent, checklist, fieldcheck, followup, tools

AS_OF = date(2026, 11, 4)
ROOT = Path(__file__).resolve().parent.parent


def statuses(package):
    return {r["doc"]: r["status"] for r in agent.review(package, AS_OF)["checklist"]}


def kinds(state):
    return sorted(f"{f['kind']}:{f['field']}" for f in state["findings"])


def six_docs(**changes):
    results = {
        "photo_id": {"expires": date(2029, 5, 1)},
        "pay_stub": {"issued": date(2026, 10, 24)},
        "vehicle_registration": {"expires": date(2027, 8, 31)},
        "payoff_letter": {"issued": date(2026, 11, 1), "good_through": date(2026, 11, 11)},
        "insurance_card": {"expires": date(2027, 4, 30)},
        "title": {"name": "Grace Chen", "vin": "1N4AL3AP7JC123456"},
    }
    for doc, fields in changes.items():
        if fields is None:
            del results[doc]
        else:
            results[doc] = fields
    return results


def row(results, doc):
    return next(r for r in checklist.check(results, AS_OF) if r["doc"] == doc)


# ---------- the rules ----------

def test_required_list_adds_insurance_card_and_title():
    assert checklist.REQUIRED_DOCS == ["photo_id", "pay_stub", "vehicle_registration",
                                       "payoff_letter", "insurance_card", "title"]
    assert checklist.CONFIRMED is False


def test_pay_stub_and_photo_id_rules_are_unchanged():
    assert checklist.MAX_AGE_DAYS == {"pay_stub": 30}
    assert "photo_id" in checklist.EXPIRES
    assert checklist.REQUIRED_FIELDS["photo_id"] == ["name", "address", "expires"]
    assert checklist.REQUIRED_FIELDS["pay_stub"] == ["name", "issued", "income"]


def test_insurance_card_must_be_unexpired_on_the_visit_date():
    assert row(six_docs(), "insurance_card")["status"] == "ok"
    assert row(six_docs(insurance_card={"expires": AS_OF}), "insurance_card")["status"] == "ok"
    expired = row(six_docs(insurance_card={"expires": date(2026, 11, 3)}), "insurance_card")
    assert expired["status"] == "expired" and "2026-11-03" in expired["rule"]


def test_insurance_card_without_a_usable_expiry_is_unreadable():
    assert row(six_docs(insurance_card={"name": "Grace Chen"}), "insurance_card")["status"] == "unreadable"


def test_missing_insurance_card_is_flagged():
    assert row(six_docs(insurance_card=None), "insurance_card")["status"] == "missing"


def test_title_only_needs_to_be_present():
    assert row(six_docs(title={}), "title") == {"doc": "title", "status": "ok", "rule": "present"}
    assert row(six_docs(title=None), "title")["status"] == "missing"


def test_insurance_expiry_counts_toward_the_next_lapse():
    results = six_docs(insurance_card={"expires": date(2026, 11, 6)})
    results["payoff_letter"] = {"good_through": date(2026, 11, 20)}
    assert checklist.next_lapse(results, AS_OF) == date(2026, 11, 6)


def test_classification_keywords():
    assert tools.classify("PROOF OF INSURANCE\nName: X\n") == "insurance_card"
    assert tools.classify("Auto Insurance Card\nName: X\n") == "insurance_card"
    assert tools.classify("NEW YORK CERTIFICATE OF TITLE\nName: X\n") == "title"
    # the older types still win on their own words
    assert tools.classify("VEHICLE REGISTRATION\nName: X\n") == "vehicle_registration"
    # wording NY insurance ID cards commonly use
    assert tools.classify("NEW YORK AUTOMOBILE INSURANCE IDENTIFICATION CARD\nName: A\n") == "insurance_card"


def test_a_document_is_named_by_its_header_not_by_what_it_mentions():
    # payoff letters often mention the title and insurance in their text
    assert tools.classify("PAYOFF LETTER\nThe lien on the certificate of title will be "
                          "released. Proof of insurance is not needed.\n") == "payoff_letter"
    assert tools.classify("NEW YORK CERTIFICATE OF TITLE\nVehicle registration class: PAS\n") == "title"
    assert tools.classify("AUTO INSURANCE CARD\nDriver license required to drive.\n") == "insurance_card"
    assert tools.classify("VEHICLE REGISTRATION\nKeep proof of insurance in the car.\n") == "vehicle_registration"


def test_a_mention_of_the_title_or_insurance_below_the_header_never_names_the_document():
    text = ("PAYOFF STATEMENT\nLender lien on the certificate of title is released "
            "on payment. Proof of insurance on file.\n")
    assert tools.classify(text) == "unknown"
    assert tools.classify(text, limit=None) == "unknown"


def test_older_types_still_found_below_the_header():
    # the earliest keyword wins when the header names nothing
    text = "Acme Payroll\nEarnings statement (pay stub). Bring your driver license.\n"
    assert tools.classify(text) == "pay_stub"


def test_payoff_statement_mentioning_the_title_is_left_for_the_rep(tmp_path, monkeypatch):
    monkeypatch.setattr(tools, "UPLOAD_ROOT", tmp_path.resolve())
    pkg = tmp_path / "probe"
    pkg.mkdir()
    for f in (ROOT / "data" / "synthetic" / "pkg01").glob("*.txt"):
        (pkg / f.name).write_text(f.read_text())
    (pkg / "payoff.txt").write_text(
        "PAYOFF STATEMENT\nLender lien on the certificate of title is released on payment.\n")
    state = agent.review("probe", AS_OF)
    assert state["read"]["payoff.txt"]["type"] == "unknown"
    rows = {r["doc"]: r["status"] for r in state["checklist"]}
    assert rows["title"] == "ok"
    assert rows["payoff_letter"] == "missing"


# ---------- the packages ----------

def test_clean_package_has_all_six_documents_and_no_flags():
    state = agent.review("pkg01", AS_OF)
    types = sorted(i["type"] for i in state["read"].values())
    assert types == sorted(checklist.REQUIRED_DOCS)
    assert agent.flags(state) == []
    assert fieldcheck.check_fields(state)["findings"] == []


@pytest.mark.parametrize("package, doc, status", [
    ("pkg23", "insurance_card", "missing"),
    ("pkg24", "insurance_card", "expired"),
    ("pkg25", "insurance_card", "unreadable"),
    ("pkg26", "title", "missing"),
])
def test_single_change_packages_flag_only_that_document(package, doc, status):
    state = agent.review(package, AS_OF)
    assert state["stop_reason"].startswith("done")
    assert {r["doc"]: r["status"] for r in agent.flags(state)} == {doc: status}
    assert fieldcheck.check_fields(state)["findings"] == []


def test_unreadable_insurance_expiry_gives_the_rep_the_line():
    state = agent.review("pkg25", AS_OF)
    assert state["hints"]["insurance_card"] == ["line 5: Expires: 5/31/27"]


def test_title_vin_mismatch_passes_the_checklist_but_the_field_check_flags_it():
    review = agent.review("pkg27", AS_OF)
    assert agent.flags(review) == []
    state = fieldcheck.check_fields(review)
    assert kinds(state) == ["mismatch:vin"]
    files = sorted(d["file"] for d in state["findings"][0]["docs"])
    assert files == ["payoff.txt", "registration.txt", "title.txt"]


def test_title_name_is_compared_and_insurance_name_is_not():
    review = agent.review("pkg01", AS_OF)
    review["read"]["insurance.txt"]["fields"]["name"]["value"] = "Someone Else"
    assert fieldcheck.check_fields(review)["findings"] == []
    review["read"]["title.txt"]["fields"]["name"]["value"] = "Someone Else"
    assert kinds(fieldcheck.check_fields(review)) == ["mismatch:name"]


def test_title_without_a_vin_is_a_gap_for_the_rep():
    review = agent.review("pkg01", AS_OF)
    del review["read"]["title.txt"]["fields"]["vin"]
    state = fieldcheck.check_fields(review)
    assert kinds(state) == ["missing_field:vin"]
    assert state["findings"][0]["hints"] == ["line 3: VIN: 1HGCM82633A004352"]


# ---------- follow-up drafts ----------

@pytest.mark.parametrize("package, doc, need", [
    ("pkg23", "insurance_card", "your insurance card"),
    ("pkg24", "insurance_card", "an unexpired insurance card"),
    ("pkg26", "title", "your certificate of title"),
])
def test_draft_asks_for_the_new_documents_and_passes_its_check(package, doc, need):
    state = followup.draft_followup(agent.review(package, AS_OF), [doc])
    assert state["stop_reason"].startswith("done")
    assert need in state["draft"].lower()


def test_draft_check_refuses_an_unselected_new_document():
    items = [{"doc": "title", "label": "certificate of title", "need": "your certificate of title"}]
    body = "Hello [member name],\n\nPlease send your certificate of title and your insurance card."
    assert "it names the insurance card, which was not selected" in followup.check_body(body, items)


# ---------- the screen ----------

@pytest.fixture
def app_module():
    pytest.importorskip("streamlit")
    spec = importlib.util.spec_from_file_location("lr_app_mcu", ROOT / "app.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_screen_asks_for_a_missing_insurance_card(app_module):
    state = agent.review("pkg23", AS_OF)
    html = app_module.verdict_html(state)
    assert "Ask the member for 1 document before they leave." in html
    assert "An insurance card." in html


def test_screen_ruler_shows_every_document_and_the_title_has_no_date_rule(app_module):
    html = app_module.ruler_html(agent.review("pkg01", AS_OF), AS_OF)
    assert "Insurance card" in html and "valid until Apr 30, 2027" in html
    assert "Certificate of title" in html and "In the package; no date rule" in html


def test_screen_clear_verdict_does_not_count_documents(app_module):
    html = app_module.verdict_html(agent.review("pkg01", AS_OF))
    assert "Nothing to ask for." in html and "four" not in html
