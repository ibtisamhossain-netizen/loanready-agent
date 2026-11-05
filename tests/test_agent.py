from datetime import date

import pytest

from loanready import agent, checklist, followup, tools

AS_OF = date(2026, 11, 4)


def test_rejects_path_outside_synthetic_data():
    with pytest.raises(tools.ToolError):
        tools.read_document("pkg01", "../../README.md")
    with pytest.raises(tools.ToolError):
        tools.list_documents("../loanready")


def test_injected_instruction_is_ignored():
    state = agent.review("pkg07", AS_OF)
    statuses = {r["doc"]: r["status"] for r in state["checklist"]}
    assert statuses["payoff_letter"] == "stale"


def test_refuses_action_off_allow_list():
    class BadPlanner:
        def next_action(self, state):
            return {"action": "send_email"}
    state = agent.review("pkg01", AS_OF, planner=BadPlanner())
    assert "not allowed" in state["stop_reason"]
    assert state["checklist"] is None


def test_stops_when_stuck():
    class LoopPlanner:
        def next_action(self, state):
            return {"action": "list_documents"}
    state = agent.review("pkg01", AS_OF, planner=LoopPlanner())
    assert state["stop_reason"].startswith("stuck")


def test_extraction_keeps_source_evidence():
    text = tools.read_document("pkg01", "registration.txt")
    fields = tools.extract(text)
    assert fields["vin"]["value"] == "1HGCM82633A004352"
    assert fields["vin"]["evidence"].startswith("line ")


def test_draft_only_lists_selected_items_and_is_marked_draft():
    state = agent.review("pkg05", AS_OF)
    draft = followup.draft_followup(state, ["payoff_letter"])["draft"]
    assert draft.startswith("DRAFT")
    assert "payoff letter" in draft and "registration" not in draft


def test_checklist_is_marked_unconfirmed():
    assert checklist.CONFIRMED is False
