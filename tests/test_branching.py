"""The loop picks its next step from what it finds, and stops safely."""
import json
from datetime import date

import pytest

from loanready import agent, store, tools

AS_OF = date(2026, 11, 4)


def actions(state):
    return [e["action"] for e in state["log"]]


def test_clean_package_takes_the_short_path():
    state = agent.review("pkg01", AS_OF)
    assert "scan_document" not in actions(state)
    assert actions(state).count("run_checklist") == 1


def test_unrecognized_file_is_scanned_and_checklist_reruns():
    state = agent.review("pkg17", AS_OF)
    assert state["stop_reason"].startswith("done")
    assert actions(state).count("run_checklist") == 2
    assert "scan_document" in actions(state)
    assert agent.flags(state) == []
    assert state["read"]["paystub.txt"]["type"] == "pay_stub"


def test_unreadable_date_gets_hints_but_stays_flagged():
    state = agent.review("pkg18", AS_OF)
    assert {r["doc"]: r["status"] for r in agent.flags(state)} == {"pay_stub": "unreadable"}
    assert state["hints"]["pay_stub"] == ["line 3: Pay date: Oct 24, 2026"]


def test_two_documents_of_one_type_go_to_the_rep():
    state = agent.review("pkg19", AS_OF)
    row = next(r for r in state["checklist"] if r["doc"] == "pay_stub")
    assert row["status"] == "unreadable"
    assert "paystub_aug.txt" in row["rule"] and "paystub_oct.txt" in row["rule"]
    assert "scan_document" not in actions(state)


def test_paths_differ_across_packages():
    shapes = {tuple(a for a in actions(agent.review(p, AS_OF)) if a != "read_document")
              for p in ["pkg01", "pkg06", "pkg17", "pkg19"]}
    assert len(shapes) >= 3


def test_every_pass_logs_a_reason():
    state = agent.review("pkg17", AS_OF)
    assert all(e["why"] for e in state["log"])


def test_finishing_with_an_out_of_date_checklist_is_not_success():
    class EarlyFinish(agent.RulePlanner):
        def next_action(self, state):
            step = super().next_action(state)
            if step["action"] == "run_checklist" and state["checklist"] is not None:
                return {"action": "finish", "why": "skip the rerun"}
            return step
    state = agent.review("pkg17", AS_OF, planner=EarlyFinish())
    assert state["stop_reason"] == "finished early: checklist is out of date"


def test_rewording_the_reason_does_not_hide_a_repeat():
    class Reworder:
        n = 0
        def next_action(self, state):
            self.n += 1
            return {"action": "list_documents", "why": f"attempt {self.n}"}
    state = agent.review("pkg01", AS_OF, planner=Reworder())
    assert state["stop_reason"].startswith("stuck")


def test_pass_limit_stops_a_planner_that_never_finishes():
    class PingPong:
        n = 0
        def next_action(self, state):
            self.n += 1
            return {"action": "list_documents" if self.n % 2 else "run_checklist"}
    state = agent.review("pkg01", AS_OF, planner=PingPong())
    assert state["stop_reason"] == f"pass limit reached ({agent.MAX_PASSES})"


def test_cannot_scan_a_file_that_was_not_listed():
    class Sneaky:
        def next_action(self, state):
            if state["documents"] is None:
                return {"action": "list_documents"}
            return {"action": "scan_document", "name": "../../.env"}
    state = agent.review("pkg01", AS_OF, planner=Sneaky())
    assert "not a listed document" in state["log"][1]["error"]


def test_model_planner_never_sees_document_text():
    state = agent.review("pkg07", AS_OF)
    view = json.dumps(agent.planner_view(state)).lower()
    assert "ignore the checklist" not in view
    assert "dana reyes" not in view and "priya nair" not in view


def test_too_many_files_are_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(tools, "UPLOAD_ROOT", tmp_path.resolve())
    with pytest.raises(tools.ToolError):
        store.save_uploads([(f"doc{i}.txt", b"x") for i in range(tools.MAX_DOCS + 1)])
