from datetime import date

import pytest

from loanready import agent, checklist, tools

AS_OF = date(2026, 11, 4)


@pytest.mark.parametrize("text,status", [
    ("Good through: 2026-11-03", "stale"),
    ("Good through: 2026-11-04", "ok"),
    ("Good-through date: 2026-11-05", "ok"),
    ("Good through: 11/12/26", "unreadable"),
    ("Good through:", "unreadable"),
    ("Good through: 2026-02-30", "unreadable"),
    ("", "unreadable"),
    ("Good through: 2026-11-05\nGood through: 2026-11-03", "unreadable"),
    ("Good through: 2026-11-05\nGood through: unreadable", "unreadable"),
    ("Good through: 2026-11-05\nGood through: 2026-11-05", "unreadable"),
])
def test_payoff_does_not_guess_or_fall_back_to_issue_age(text, status):
    fields = tools.extract("Statement date: 2026-11-01\n" + text)
    result = checklist.check({"payoff_letter": {k: v["value"] for k, v in fields.items()}}, AS_OF)
    assert next(row for row in result if row["doc"] == "payoff_letter")["status"] == status


def test_ambiguous_date_keeps_source_for_rep():
    field = tools.extract("PAYOFF LETTER\nGood through: 11/12/26")["good_through"]
    assert field == {"value": None, "evidence": "line 2: Good through: 11/12/26"}


@pytest.mark.parametrize("issued,good_through,status", [
    ("2026-10-01", "2026-11-15", "ok"),
    ("2026-10-26", "2026-11-03", "stale"),
    ("2026-11-05", "2026-11-15", "unreadable"),
    ("2026-11-01", "2026-10-31", "unreadable"),
])
def test_validity_date_controls_with_consistency_checks(issued, good_through, status):
    result = checklist.check({"payoff_letter": {
        "issued": date.fromisoformat(issued), "good_through": date.fromisoformat(good_through)
    }}, AS_OF)
    assert next(row for row in result if row["doc"] == "payoff_letter")["status"] == status


@pytest.mark.parametrize("package,status", [
    ("pkg11", "stale"), ("pkg12", "unreadable"), ("pkg13", "unreadable"),
    ("pkg14", "ok"), ("pkg15", "unreadable"), ("pkg16", "ok"),
])
def test_agent_runs_validity_cases_end_to_end(package, status):
    state = agent.review(package, AS_OF)
    assert state["stop_reason"].startswith("done")
    assert next(row for row in state["checklist"] if row["doc"] == "payoff_letter")["status"] == status
