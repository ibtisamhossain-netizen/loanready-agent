"""The field check, open-files and follow-up agents, and their guards."""
import json
import sqlite3
from datetime import date

import pytest

from loanready import agent, checklist, fieldcheck, followup, harness, pipeline, store, tools

AS_OF = date(2026, 11, 4)


def kinds(state):
    return sorted(f"{f['kind']}:{f['field']}" for f in state["findings"])


# ---------- field check ----------

def test_clean_package_has_no_findings():
    state = fieldcheck.check_fields(agent.review("pkg01", AS_OF))
    assert state["findings"] == []
    assert state["stop_reason"].startswith("done")


def test_vin_mismatch_shows_both_source_lines_and_leaves_the_checklist_alone():
    review = agent.review("pkg20", AS_OF)
    state = fieldcheck.check_fields(review)
    assert kinds(state) == ["mismatch:vin"]
    evidence = " ".join(d["evidence"] for d in state["findings"][0]["docs"])
    assert "3FA6P0H72HR123456" in evidence and "5YJSA1E26HF000001" in evidence
    assert agent.flags(review) == []


def test_near_match_name_still_goes_to_the_rep():
    state = fieldcheck.check_fields(agent.review("pkg21", AS_OF))
    assert kinds(state) == ["mismatch:name"]


def test_spacing_and_case_are_not_a_mismatch():
    review = agent.review("pkg01", AS_OF)
    review["read"]["id.txt"]["fields"]["name"]["value"] = "DANA   reyes"
    assert fieldcheck.check_fields(review)["findings"] == []


def test_unread_value_branches_to_a_scan_and_gives_a_hint_not_a_value():
    review = agent.review("pkg22", AS_OF)
    state = fieldcheck.check_fields(review)
    assert kinds(state) == ["missing_field:vin"]
    assert state["findings"][0]["hints"] == ["line 3: VIN: 3FA6P0H72HR12345"]
    assert "scan_for_field" in [e["action"] for e in state["log"]]
    assert "vin" not in review["read"]["registration.txt"]["fields"]


def test_clean_path_never_scans():
    state = fieldcheck.check_fields(agent.review("pkg01", AS_OF))
    assert "scan_for_field" not in [e["action"] for e in state["log"]]


def test_unreadable_date_is_not_reported_twice():
    state = fieldcheck.check_fields(agent.review("pkg18", AS_OF))
    assert state["findings"] == []


def test_field_check_model_view_has_no_values_or_document_text():
    state = fieldcheck.check_fields(agent.review("pkg20", AS_OF))
    view = json.dumps(fieldcheck.planner_view(state)).lower()
    assert "aisha" not in view and "3fa6p0h72hr123456" not in view


def test_field_check_cannot_scan_an_unlisted_gap():
    class Sneaky:
        def next_action(self, state):
            if state["gaps"] is None:
                return {"action": "find_gaps"}
            return {"action": "scan_for_field", "name": "../../.env#name"}
    state = fieldcheck.check_fields(agent.review("pkg01", AS_OF), planner=Sneaky())
    assert "not a listed gap" in state["log"][1]["error"]


def test_finishing_before_comparing_is_not_success():
    class Early:
        def next_action(self, state):
            return {"action": "finish"}
    state = fieldcheck.check_fields(agent.review("pkg01", AS_OF), planner=Early())
    assert state["stop_reason"].startswith("finished early")


# ---------- rep corrections ----------

def test_correcting_a_date_reruns_the_checklist_and_keeps_the_original():
    review = agent.review("pkg11", AS_OF)
    assert agent.flags(review)[0]["status"] == "stale"
    fix = agent.make_field_review(review, "payoff.txt", "good_through", "corrected", "2026-11-20")
    updated = agent.apply_field_reviews(review, [fix], AS_OF)
    assert agent.flags(updated) == []
    field = updated["read"]["payoff.txt"]["fields"]["good_through"]
    assert field["evidence"] == "line 6: Good through: 2026-11-03"
    assert field["review"]["original"] == date(2026, 11, 3)
    # the state passed in is not changed
    assert agent.flags(review)[0]["status"] == "stale"


def test_rejecting_a_date_can_only_make_the_result_stricter():
    review = agent.review("pkg01", AS_OF)
    fix = agent.make_field_review(review, "paystub.txt", "issued", "rejected")
    updated = agent.apply_field_reviews(review, [fix], AS_OF)
    assert {r["doc"]: r["status"] for r in agent.flags(updated)} == {"pay_stub": "unreadable"}


def test_rep_can_enter_a_date_the_reader_skipped():
    review = agent.review("pkg18", AS_OF)
    fix = agent.make_field_review(review, "paystub.txt", "issued", "corrected", "2026-10-24")
    updated = agent.apply_field_reviews(review, [fix], AS_OF)
    assert agent.flags(updated) == []
    assert updated["read"]["paystub.txt"]["fields"]["issued"]["evidence"].startswith("entered by the rep")


@pytest.mark.parametrize("file,field,action,value", [
    ("nope.txt", "name", "corrected", "x"),
    ("id.txt", "ssn", "corrected", "x"),
    ("id.txt", "name", "approved", "x"),
    ("id.txt", "name", "corrected", "   "),
    ("id.txt", "expires", "corrected", "May 1"),
])
def test_bad_corrections_are_refused(file, field, action, value):
    review = agent.review("pkg01", AS_OF)
    with pytest.raises(tools.ToolError):
        agent.make_field_review(review, file, field, action, value)


def test_corrections_survive_a_new_review_through_the_store(tmp_path):
    db = tmp_path / "t.db"
    review = agent.review("pkg18", AS_OF)
    fix = agent.make_field_review(review, "paystub.txt", "issued", "corrected", "2026-10-24")
    store.save_field_review("pkg18", fix, AS_OF, db_path=db)
    again = agent.apply_field_reviews(agent.review("pkg18", AS_OF), store.field_reviews("pkg18", db), AS_OF)
    assert agent.flags(again) == []
    assert tools.read_document("pkg18", "paystub.txt").count("Oct 24, 2026") == 1


# ---------- open files ----------

@pytest.fixture
def seeded(tmp_path):
    db = tmp_path / "t.db"
    for pkg in ["pkg01", "pkg05", "pkg06", "pkg20"]:
        store.save_review(agent.review(pkg, AS_OF), AS_OF, db_path=db)
    return db


def test_every_seeded_file_gets_a_status_step_and_follow_up_date(seeded):
    state = pipeline.review_open_files(AS_OF, db_path=seeded)
    assert state["stop_reason"].startswith("done")
    rows = pipeline.worklist(state)
    assert {r["package"] for r in rows} == {"pkg01", "pkg05", "pkg06", "pkg20"}
    assert all(r["status"] and r["next_step"] and r["next_follow_up"] and r["last_activity"] for r in rows)
    status = {r["package"]: r["status"] for r in rows}
    assert status == {"pkg01": "ready to confirm", "pkg05": "waiting on member",
                      "pkg06": "needs rep check", "pkg20": "needs rep check"}


def test_empty_store_finishes_cleanly(tmp_path):
    state = pipeline.review_open_files(AS_OF, db_path=tmp_path / "none.db")
    assert state["stop_reason"].startswith("done") and state["plan"] == {}
    assert not (tmp_path / "none.db").exists()


def test_file_that_went_stale_after_the_visit_is_caught(seeded):
    later = date(2026, 11, 12)  # pkg01's payoff letter was good through Nov 11
    plan = pipeline.review_open_files(later, db_path=seeded)["plan"]["pkg01"]
    assert plan["changed"] == ["payoff_letter"]
    assert plan["status"] == "waiting on member"
    assert plan["next_step"].startswith("Changed since the last check: payoff letter.")


def test_follow_up_comes_before_a_document_lapses():
    assert checklist.follow_up_date(date(2026, 11, 1), None) == date(2026, 11, 4)
    assert checklist.follow_up_date(date(2026, 11, 1), date(2026, 11, 2)) == date(2026, 11, 2)
    results = {"payoff_letter": {"good_through": date(2026, 11, 3)},
               "photo_id": {"expires": date(2026, 10, 1)}}
    assert checklist.next_lapse(results, date(2026, 11, 2)) == date(2026, 11, 3)


def test_overdue_files_sort_first_and_a_rep_date_is_kept(seeded):
    store.update_file("pkg05", AS_OF, next_follow_up=date(2026, 11, 20), notes="called", db_path=seeded)
    state = pipeline.review_open_files(date(2026, 11, 10), db_path=seeded)
    rows = pipeline.worklist(state)
    assert rows[-1]["package"] == "pkg05"
    assert rows[-1]["follow_up_source"] == "rep" and rows[-1]["next_follow_up"] == date(2026, 11, 20)
    assert rows[-1]["notes"] == "called"
    assert rows[0]["overdue"]


def test_the_agent_writes_nothing_to_the_store(seeded):
    def dump():
        conn = sqlite3.connect(seeded)
        try:
            return list(conn.iterdump())
        finally:
            conn.close()
    before = dump()
    pipeline.review_open_files(date(2026, 12, 1), db_path=seeded)
    assert dump() == before


def test_closed_file_leaves_the_list_and_a_new_check_reopens_it(seeded):
    store.update_file("pkg01", AS_OF, close=True, db_path=seeded)
    assert "pkg01" not in pipeline.review_open_files(AS_OF, db_path=seeded)["plan"]
    store.save_review(agent.review("pkg01", AS_OF), AS_OF, db_path=seeded)
    assert "pkg01" in pipeline.review_open_files(AS_OF, db_path=seeded)["plan"]


def test_rechecking_the_same_package_keeps_one_open_file(seeded):
    store.update_file("pkg05", AS_OF, next_follow_up=date(2026, 11, 20), db_path=seeded)
    store.save_review(agent.review("pkg05", AS_OF), AS_OF, db_path=seeded)
    files = [f for f in store.open_files(seeded) if f["package"] == "pkg05"]
    assert len(files) == 1 and files[0]["next_follow_up"] == "2026-11-20"


def test_updating_an_unknown_file_is_refused(seeded):
    with pytest.raises(tools.ToolError):
        store.update_file("nope", AS_OF, notes="x", db_path=seeded)


def test_missing_source_folder_becomes_a_next_step_not_a_crash(seeded, monkeypatch):
    conn = sqlite3.connect(seeded)
    with conn:
        conn.execute("UPDATE open_file SET package = 'app-gone' WHERE package = 'pkg01'")
    conn.close()
    plan = pipeline.review_open_files(AS_OF, db_path=seeded)["plan"]["app-gone"]
    assert plan["status"] == "check did not finish"
    assert "by hand" in plan["next_step"]
    assert plan["next_follow_up"]


def test_open_files_refuses_off_list_action_and_unknown_file(seeded):
    class Bad:
        def next_action(self, state):
            return {"action": "email_member"}
    assert "not allowed" in pipeline.review_open_files(AS_OF, seeded, Bad())["stop_reason"]

    class Sneaky:
        def next_action(self, state):
            if state["files"] is None:
                return {"action": "list_open_files"}
            return {"action": "recheck_file", "name": "../secret"}
    state = pipeline.review_open_files(AS_OF, seeded, Sneaky())
    assert "not an open file" in state["log"][1]["error"]


def test_open_files_model_view_is_ids_and_progress_only(seeded):
    state = pipeline.review_open_files(AS_OF, db_path=seeded)
    view = json.dumps(pipeline.planner_view(state)).lower()
    assert "reyes" not in view and "payoff" not in view and "status" not in view


# ---------- follow-up draft ----------

class Scripted:
    """A writer that returns the given drafts in turn, like a misbehaving model."""
    source = "model"

    def __init__(self, *drafts):
        self.drafts = list(drafts)
        self.problems_seen = []

    def write(self, items, problems):
        self.problems_seen.append(list(problems))
        draft = self.drafts.pop(0)
        if isinstance(draft, Exception):
            raise draft
        return draft


GOOD = "Hello [member name],\n\nPlease send an updated payoff letter from your current lender.\n\nThank you."


def test_draft_lists_exactly_the_selected_items():
    review = agent.review("pkg05", AS_OF)
    state = followup.draft_followup(review, ["vehicle_registration"])
    assert state["draft"].startswith("DRAFT")
    assert "vehicle registration" in state["draft"].lower()
    assert "payoff" not in state["draft"].lower()


def test_item_that_is_not_flagged_cannot_be_requested():
    review = agent.review("pkg05", AS_OF)
    state = followup.draft_followup(review, ["payoff_letter", "photo_id"])
    assert [i["doc"] for i in state["items"]] == ["payoff_letter"]
    assert state["ignored"] == ["photo_id"]
    assert "photo id" not in state["draft"].lower()


def test_nothing_selected_means_no_draft():
    state = followup.draft_followup(agent.review("pkg05", AS_OF), [])
    assert state["draft"] == "" and state["stop_reason"].startswith("nothing to draft")


def test_every_flag_status_gets_a_template_that_passes_its_own_check():
    for pkg, expected in json.loads((tools.DATA_ROOT / "labels.json").read_text())["expected_flags"].items():
        if expected:
            state = followup.draft_followup(agent.review(pkg, AS_OF), list(expected))
            assert state["stop_reason"].startswith("done"), pkg


def test_good_model_draft_is_used():
    state = followup.draft_followup(agent.review("pkg11", AS_OF), ["payoff_letter"], writer=Scripted(GOOD))
    assert state["source"] == "model" and GOOD in state["draft"]


@pytest.mark.parametrize("bad,problem", [
    ("Hello [member name], please send your payoff letter and pay stub.", "not selected"),
    ("Hello [member name], please send something.", "does not name"),
    ("Hello [member name], send your payoff letter and you will be approved.", "decision"),
    ("Hello [member name], send your payoff letter to help@example.org.", "link or email"),
    ("Hello [member name], send your payoff letter by November 30.", "number"),
    ("Hello Dana, please send your payoff letter.", "placeholder"),
    ("", "empty"),
])
def test_bad_draft_is_rewritten_with_the_reasons(bad, problem):
    writer = Scripted(bad, GOOD)
    state = followup.draft_followup(agent.review("pkg11", AS_OF), ["payoff_letter"], writer=writer)
    assert problem in writer.problems_seen[1][0]
    assert state["source"] == "model" and GOOD in state["draft"]


def test_numbered_list_is_not_an_invented_number():
    items = [{"doc": "payoff_letter", "label": "payoff letter", "need": "x"}]
    assert followup.check_body("Hello [member name],\n\n1. Your payoff letter\n", items) == []
    assert followup.check_body("Hello [member name],\n\n1. Your payoff letter by May 3\n", items)


def test_writer_that_keeps_failing_falls_back_to_the_template():
    writer = Scripted("You are approved!", "You are approved!!")
    state = followup.draft_followup(agent.review("pkg11", AS_OF), ["payoff_letter"], writer=writer)
    assert state["source"] == "template"
    assert state["stop_reason"].startswith("done")
    assert "approved!" not in state["draft"]
    assert "use_template" in [e["action"] for e in state["log"]]


def test_model_failure_falls_back_to_the_template():
    writer = Scripted(harness.ModelError("model call failed"), harness.ModelError("model call failed"))
    state = followup.draft_followup(agent.review("pkg11", AS_OF), ["payoff_letter"], writer=writer)
    assert state["source"] == "template" and state["draft"].startswith("DRAFT")


def test_document_text_cannot_reach_the_writer():
    review = agent.review("pkg07", AS_OF)  # has a planted instruction and a member name
    items, _ = followup.build_items(review, ["payoff_letter"])
    sent = json.dumps(items).lower()
    assert "ignore the checklist" not in sent and "priya" not in sent and "payoff.txt" not in sent


def test_conflict_file_names_cannot_reach_the_writer():
    review = agent.review("pkg19", AS_OF)
    items, _ = followup.build_items(review, ["pay_stub"])
    assert "paystub_aug" not in json.dumps(items)


def test_no_agent_has_a_send_action():
    all_actions = agent.ACTIONS | fieldcheck.ACTIONS | pipeline.ACTIONS | followup.ACTIONS
    assert not [a for a in all_actions if any(w in a for w in ("send", "email", "post", "approve"))]
    assert not [t for t in tools.ALLOWED_TOOLS if "send" in t or "write" in t]


# ---------- model planners, with a fake client ----------

class FakeBlock:
    type = "text"

    def __init__(self, text):
        self.text = text


class FakeMessage:
    def __init__(self, text, stop_reason="end_turn"):
        self.content = [FakeBlock(text)]
        self.stop_reason = stop_reason


class FakeClient:
    def __init__(self, reply):
        self.reply = reply
        self.calls = []
        self.messages = self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply


def planner_with(reply):
    anthropic = pytest.importorskip("anthropic")
    assert anthropic
    planner = harness.ModelPlanner.__new__(harness.ModelPlanner)
    planner.client, planner.model, planner.system = FakeClient(reply), "test-model", "system"
    planner.view = lambda state: {"seen": "view only"}
    planner.schema = {"type": "object"}
    return planner


def test_model_planner_sends_only_the_view_and_returns_its_choice():
    planner = planner_with(FakeMessage('{"action": "finish", "why": "done"}'))
    assert planner.next_action({"secret": "document text"})["action"] == "finish"
    assert "document text" not in json.dumps(planner.client.calls[0]["messages"])


@pytest.mark.parametrize("reply", [FakeMessage("not json"), FakeMessage('{"action":"finish"}', "refusal"),
                                   FakeMessage('{"action":"fin', "max_tokens")])
def test_bad_model_replies_become_a_refused_action(reply):
    assert planner_with(reply).next_action({})["action"] == "invalid"


def test_api_failure_stops_the_run_with_a_reason():
    anthropic = pytest.importorskip("anthropic")
    import httpx
    planner = planner_with(anthropic.APIConnectionError(request=httpx.Request("POST", "http://x")))
    planner.view = agent.planner_view
    state = agent.review("pkg01", AS_OF, planner=planner)
    assert "not allowed" in state["stop_reason"]
    assert "APIConnectionError" in state["log"][0]["why"]
    assert state["checklist"] is None


def test_off_list_model_choice_is_refused_by_the_harness():
    planner = planner_with(FakeMessage('{"action": "send_email", "why": "because"}'))
    planner.view = agent.planner_view
    assert "not allowed" in agent.review("pkg01", AS_OF, planner=planner)["stop_reason"]
