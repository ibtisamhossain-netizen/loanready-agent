"""Open-files agent (story 3): what is the next step on every open file?

It rechecks each open file against today, because a file that passed at the
visit can go stale later, and proposes a next step and follow-up date. It
does not write: the rep saves any date, note or closure on the screen, and
LoanReady never contacts a member. A follow-up date is a staff reminder only,
not a legal deadline (checklist.follow_up_date).
"""
from __future__ import annotations

from datetime import date

from . import agent, checklist, fieldcheck, harness, store

ACTIONS = {"list_open_files", "recheck_file", "propose_next_step", "finish"}
MAX_FILES = 100
MAX_PASSES = 2 * MAX_FILES + 2


class RulePlanner:
    def next_action(self, state: dict) -> dict:
        if state["files"] is None:
            return {"action": "list_open_files", "why": "start: see which files are open"}
        for package in state["files"]:
            if package not in state["checked"]:
                return {"action": "recheck_file", "name": package,
                        "why": "documents can run out after the visit"}
            if package not in state["plan"]:
                return {"action": "propose_next_step", "name": package,
                        "why": "the recheck is done; work out what comes next"}
        return {"action": "finish", "why": "every open file has a next step"}


def planner_view(state: dict) -> dict:
    """File ids and progress only, never member details or document text."""
    return {
        "files_listed": state["files"] is not None,
        "open_files": sorted(state["files"] or {}),
        "already_rechecked": sorted(state["checked"]),
        "already_planned": sorted(state["plan"]),
    }


def make_model_planner():
    return harness.ModelPlanner(
        "You choose the next step in updating a credit union rep's open-file list. Reply with "
        "{action, name, why}. Run list_open_files once. For each file run recheck_file, then "
        "propose_next_step, with name = the file id. Then finish. Code decides every status "
        "and date; you only choose the order.",
        planner_view, ACTIONS)


def _names(docs: list) -> str:
    return ", ".join(d.replace("_", " ") for d in docs)


def _recheck(package: str, today: date, db_path) -> dict:
    """Rerun the review and field check as of today, with the rep's saved corrections."""
    try:
        review = agent.review(package, today)
        if review["checklist"] is None:
            return {"error": review["stop_reason"]}
        review = agent.apply_field_reviews(review, store.field_reviews(package, db_path), today)
    except harness.ToolError as err:
        return {"error": str(err)}
    return {"review": review, "findings": fieldcheck.check_fields(review)["findings"]}


def _propose(row: dict, check: dict, today: date) -> dict:
    last = date.fromisoformat(row["last_activity"])
    plan = {"package": row["package"], "last_activity": last, "notes": row["notes"],
            "changed": [], "flags": {}}
    lapse = None
    if "error" in check:
        plan["status"] = "check did not finish"
        plan["next_step"] = f"Check this file by hand. LoanReady could not recheck it: {check['error']}."
    else:
        review = check["review"]
        rows = review["checklist"]
        plan["flags"] = {r["doc"]: r["status"] for r in rows if r["status"] != "ok"}
        before = row["last_statuses"]
        plan["changed"] = [r["doc"] for r in rows
                           if r["doc"] in before and before[r["doc"]] != r["status"]]
        ask = [d for d, s in plan["flags"].items() if s in checklist.ASK_STATUSES]
        check_docs = [d for d, s in plan["flags"].items() if s not in checklist.ASK_STATUSES]
        by_type, _ = agent.fields_by_type(review)
        lapse = checklist.next_lapse(by_type, today)
        steps = []
        if plan["changed"]:
            steps.append(f"Changed since the last check: {_names(plan['changed'])}.")
        if ask:
            steps.append(f"Ask the member for: {_names(ask)}.")
        if check_docs:
            steps.append(f"Read these yourself: {_names(check_docs)}.")
        if check["findings"]:
            n = len(check["findings"])
            steps.append(f"Compare {n} value{'s' if n != 1 else ''} with the originals.")
        if ask:
            plan["status"] = "waiting on member"
        elif check_docs or check["findings"]:
            plan["status"] = "needs rep check"
        else:
            plan["status"] = "ready to confirm"
            steps.append("Compare with the originals, then close the file.")
        plan["next_step"] = " ".join(steps)

    if row["next_follow_up"]:
        plan["next_follow_up"] = date.fromisoformat(row["next_follow_up"])
        plan["follow_up_source"] = "rep"
    else:
        plan["next_follow_up"] = checklist.follow_up_date(last, lapse)
        plan["follow_up_source"] = "suggested"
    plan["overdue"] = plan["next_follow_up"] < today
    return plan


def review_open_files(today: date, db_path=None, planner=None) -> dict:
    """Update the open-file list as of today. Reads the store, writes nothing."""
    state = {"today": today, "files": None, "checked": {}, "plan": {},
             "not_shown": 0, "log": [], "stop_reason": None}

    def act(state, step, entry):
        action, package = step["action"], str(step.get("name", ""))
        if action == "list_open_files":
            rows = store.open_files(db_path)
            state["not_shown"] = max(0, len(rows) - MAX_FILES)
            state["files"] = {r["package"]: r for r in rows[:MAX_FILES]}
            entry["result"] = f"{len(rows)} open"
        elif action == "recheck_file":
            if package not in (state["files"] or {}):
                raise harness.ToolError(f"not an open file: {package!r}")
            state["checked"][package] = _recheck(package, today, db_path)
            found = state["checked"][package]
            entry["result"] = ("could not recheck" if "error" in found
                               else f"{len(agent.flags(found['review']))} flags")
        elif action == "propose_next_step":
            if package not in state["checked"]:
                raise harness.ToolError(f"recheck {package!r} before planning it")
            state["plan"][package] = _propose(state["files"][package], state["checked"][package], today)
            entry["result"] = state["plan"][package]["status"]
        elif action == "finish":
            left = [p for p in (state["files"] or []) if p not in state["plan"]]
            if state["files"] is None or left:
                return f"finished early: {len(left)} files without a next step"
            return "done: every open file has a next step"
        return None

    return harness.run_loop(planner or RulePlanner(), state, ACTIONS, act, MAX_PASSES)


def worklist(state: dict) -> list:
    """Overdue files first, then anything that changed, then by follow-up date."""
    return sorted(state["plan"].values(),
                  key=lambda p: (not p["overdue"], not p["changed"], p["next_follow_up"], p["package"]))
