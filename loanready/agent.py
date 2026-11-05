"""LoanReady review agent: observe, think, act, check, with stop rules.

The planner picks ONE next action each pass from an allow-list, and
says why. Two planners exist:
  - RulePlanner: offline, no API key needed. Used for tests and evals.
  - ClaudePlanner: asks the model for the next action as JSON. Its
    choice is validated in code; anything off the allow-list is refused.
Either way, checklist decisions are made by plain code in checklist.py,
never by the model, and the agent only produces a draft for the rep.

The path is not fixed. After the first checklist run, the planner looks
at what came back and picks a follow-up:
  - a required document is missing and a file was not recognized:
    scan that file in full; if it turns out to be the missing type,
    run the checklist again.
  - a document is unreadable: scan it and collect date-like lines as
    hints for the rep. Hints never change a status.
  - nothing left to try: finish.
"""
from __future__ import annotations

import copy
from datetime import date

from . import checklist, harness, tools

# Chosen before the loop starts. A package has at most tools.MAX_DOCS
# files, so a full run needs at most 1 + 2*MAX_DOCS + 3 passes.
MAX_PASSES = 2 * tools.MAX_DOCS + 6
ACTIONS = {"list_documents", "read_document", "scan_document", "run_checklist", "finish"}
DATE_FIELDS = {"issued", "expires", "good_through"}


def _doc_for(state: dict, doc_type: str) -> list[str]:
    return [n for n, info in state["read"].items() if info["type"] == doc_type]


class RulePlanner:
    def next_action(self, state: dict) -> dict:
        if state["documents"] is None:
            return {"action": "list_documents", "why": "start: see what the member brought"}
        for name in state["documents"]:
            if name not in state["read"]:
                return {"action": "read_document", "name": name,
                        "why": f"{name} not read yet"}
        if state["checklist"] is None or state["checklist_stale"]:
            why = ("a document was reclassified, so the last checklist is out of date"
                   if state["checklist_stale"] else "every document read; check them")
            return {"action": "run_checklist", "why": why}

        flagged = {r["doc"]: r["status"] for r in state["checklist"] if r["status"] != "ok"}
        unknown = [n for n, i in state["read"].items()
                   if i["type"] == "unknown" and n not in state["scanned"]]
        for doc, status in flagged.items():
            if status == "missing" and unknown:
                return {"action": "scan_document", "name": unknown[0],
                        "why": f"{doc.replace('_', ' ')} missing; checking unrecognized "
                               f"{unknown[0]} in full"}
        for doc, status in flagged.items():
            if status != "unreadable" or doc in state["conflicts"]:
                continue
            for name in _doc_for(state, doc):
                if name not in state["scanned"]:
                    return {"action": "scan_document", "name": name,
                            "why": f"{doc.replace('_', ' ')} unreadable; looking for "
                                   f"date-like lines the rep can check"}
        why = "no flags" if not flagged else "nothing left to try; the rep resolves the flags"
        return {"action": "finish", "why": why}


def planner_view(state: dict) -> dict:
    """What a model planner is allowed to see: names and statuses only.

    Document text never reaches the model, so an instruction written
    inside a document cannot steer the next action.
    """
    return {
        "documents": state["documents"],
        "already_read": sorted(state["read"]),
        "unrecognized": sorted(n for n, i in state["read"].items() if i["type"] == "unknown"),
        "already_scanned": sorted(state["scanned"]),
        "checklist_done": state["checklist"] is not None and not state["checklist_stale"],
        "flags": {r["doc"]: r["status"] for r in (state["checklist"] or []) if r["status"] != "ok"},
    }


class ClaudePlanner(harness.ModelPlanner):
    """Needs ANTHROPIC_API_KEY and MODEL_ID in the environment."""

    def __init__(self):
        super().__init__(
            "You choose the next step for reviewing a loan document package. Reply with "
            "{action, name, why}: name is the file name when reading or scanning, why is one "
            "short sentence. Read every document, then run the checklist. If a required document "
            "is missing and a file is unrecognized, scan that file. If a document is unreadable, "
            "scan it once. Run the checklist again if it is not done. Finish when nothing is "
            "left to try. You never decide whether a document passes; the checklist does.",
            planner_view, ACTIONS)


def fields_by_type(state: dict) -> tuple:
    """(doc type -> field values, doc type -> file names) for recognized documents."""
    by_type, names = {}, {}
    for name, info in state["read"].items():
        if info["type"] != "unknown":
            names.setdefault(info["type"], []).append(name)
            by_type[info["type"]] = {k: v["value"] for k, v in info["fields"].items()}
    return by_type, names


def _run_checklist(state: dict, as_of: date) -> None:
    by_type, names = fields_by_type(state)
    state["conflicts"] = {t: n for t, n in names.items() if len(n) > 1}
    state["checklist"] = checklist.check(by_type, as_of, state["conflicts"])
    state["checklist_stale"] = False


def review(package: str, as_of: date, planner=None) -> dict:
    state = {
        "package": package,
        "documents": None,
        "read": {},          # name -> {"type", "fields"}
        "scanned": {},       # name -> {"type", "date_lines"}
        "hints": {},         # doc_type -> date-like lines for the rep
        "conflicts": {},     # doc_type -> file names, when more than one
        "checklist": None,
        "checklist_stale": False,
        "log": [],
        "stop_reason": None,
    }

    def act(state, step, entry):
        action = step["action"]
        if action == "list_documents":
            state["documents"] = tools.ALLOWED_TOOLS["list_documents"](package)
            entry["result"] = f"{len(state['documents'])} documents"
        elif action in ("read_document", "scan_document"):
            name = step.get("name", "")
            if state["documents"] is None or name not in state["documents"]:
                raise tools.ToolError(f"not a listed document: {name!r}")
            if action == "read_document":
                text = tools.ALLOWED_TOOLS["read_document"](package, name)
                state["read"][name] = {"type": tools.classify(text),
                                       "fields": tools.extract(text)}
                entry["result"] = state["read"][name]["type"].replace("_", " ")
            else:
                if name not in state["read"]:
                    raise tools.ToolError(f"read {name} before scanning it")
                found = tools.ALLOWED_TOOLS["scan_document"](package, name)
                state["scanned"][name] = found
                info = state["read"][name]
                if info["type"] == "unknown" and found["type"] != "unknown":
                    info["type"] = found["type"]
                    state["checklist_stale"] = True
                    entry["result"] = f"recognized as {found['type'].replace('_', ' ')}"
                elif info["type"] != "unknown":
                    state["hints"][info["type"]] = found["date_lines"]
                    n = len(found["date_lines"])
                    entry["result"] = f"{n} date-like line{'s' if n != 1 else ''} for the rep"
                else:
                    entry["result"] = "still not recognized"
        elif action == "run_checklist":
            _run_checklist(state, as_of)
            n_flags = sum(r["status"] != "ok" for r in state["checklist"])
            entry["result"] = f"{n_flags} flag{'s' if n_flags != 1 else ''}"
        elif action == "finish":
            # check: success means every listed document was read and the
            # checklist is current and has a row for every required document
            unread = [n for n in (state["documents"] or []) if n not in state["read"]]
            if state["checklist_stale"]:
                return "finished early: checklist is out of date"
            if unread:
                return f"finished early: {len(unread)} documents not read"
            if state["checklist"] and len(state["checklist"]) == len(checklist.REQUIRED_DOCS):
                return "done: every required item has a result"
            return "finished early without a full checklist"
        return None

    return harness.run_loop(planner or RulePlanner(), state, ACTIONS, act, MAX_PASSES)


def make_field_review(state: dict, file: str, field: str, action: str, value: str = "") -> dict:
    """Validate a rep's correction or rejection. Refuses a value it cannot use."""
    if file not in state["read"]:
        raise tools.ToolError(f"not a document in this package: {file!r}")
    if field not in tools.FIELD_LABELS:
        raise tools.ToolError(f"unknown field: {field!r}")
    if action not in ("corrected", "rejected"):
        raise tools.ToolError(f"unknown review action: {action!r}")
    value = " ".join(value.split())
    if action == "corrected":
        if not value:
            raise tools.ToolError("enter the corrected value")
        if field in DATE_FIELDS:
            try:
                date.fromisoformat(value)
            except ValueError:
                raise tools.ToolError("enter dates as YYYY-MM-DD") from None
    current = state["read"][file]["fields"].get(field, {}).get("value")
    return {"file": file, "field": field, "action": action,
            "value": value if action == "corrected" else None, "original": current}


def apply_field_reviews(state: dict, reviews: list, as_of: date) -> dict:
    """Return a copy with the rep's reviews applied and the checklist rerun.

    The original value and source line stay on the field, so the rep can
    always see what the document said. The source file is never changed.
    """
    if not reviews:
        return state
    state = copy.deepcopy(state)
    for r in reviews:
        info = state["read"].get(r["file"])
        if info is None:  # the file is no longer in the package
            continue
        fields = info["fields"]
        was = fields.get(r["field"], {})
        value = r["value"]
        if value is not None and r["field"] in DATE_FIELDS:
            value = date.fromisoformat(value)
        fields[r["field"]] = {
            "value": value,
            "evidence": was.get("evidence", "entered by the rep; not read from the document"),
            "review": {"action": r["action"],
                       "original": was["review"]["original"] if "review" in was else was.get("value")},
        }
    _run_checklist(state, as_of)
    state["log"].append({"pass": len(state["log"]) + 1, "action": "apply_rep_reviews",
                         "why": "the rep corrected or rejected a value",
                         "result": f"{len(reviews)} applied; checklist rerun"})
    return state


def flags(state: dict) -> list[dict]:
    return [r for r in (state["checklist"] or []) if r["status"] != "ok"]


def make_planner():
    """Use the model when the repo's .env (or the environment) has a key and model."""
    return ClaudePlanner() if harness.model_settings() else RulePlanner()
