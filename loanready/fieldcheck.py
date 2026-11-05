"""Field check agent (story 2): do the extracted values agree?

Runs after the review agent, on its results. It compares values across
documents and looks for required values the strict reader did not get. When
one is missing, it goes back to the file for lines that carry that label, so
the rep has something to compare.

Findings go to the rep. They never change a checklist status, and a hint
never fills in a value. The rep corrects or rejects values on the screen
(agent.apply_field_reviews). Comparison is exact apart from spacing and
case: a near match is still a mismatch, because the rep decides.
"""
from __future__ import annotations

from . import checklist, harness, tools

ACTIONS = {"compare_field", "find_gaps", "scan_for_field", "finish"}
# compare each field, find gaps once, scan at most one gap per field per document
MAX_PASSES = len(checklist.COMPARED_FIELDS) + 1 + tools.MAX_DOCS * len(tools.FIELD_PATTERNS) + 1
DATE_FIELDS = {"issued", "expires", "good_through"}


def _same(value) -> str:
    return " ".join(str(value).split()).casefold()


class RulePlanner:
    def next_action(self, state: dict) -> dict:
        for field in checklist.COMPARED_FIELDS:
            if field not in state["compared"]:
                return {"action": "compare_field", "name": field,
                        "why": f"see whether the {field} agrees across documents"}
        if state["gaps"] is None:
            return {"action": "find_gaps", "why": "see which required values were not read"}
        for gap in state["gaps"]:
            if gap not in state["scanned"]:
                return {"action": "scan_for_field", "name": gap,
                        "why": f"{gap} has no value; looking for its line"}
        return {"action": "finish", "why": "every comparison and gap has been looked at"}


def planner_view(state: dict) -> dict:
    """Field and file names only. Values and document text never reach the model."""
    return {
        "fields_to_compare": sorted(checklist.COMPARED_FIELDS),
        "already_compared": sorted(state["compared"]),
        "gaps_found": state["gaps"] is not None,
        "gaps": state["gaps"],
        "already_scanned": sorted(state["scanned"]),
    }


def make_model_planner():
    return harness.ModelPlanner(
        "You choose the next step in checking extracted loan document fields. Reply with "
        "{action, name, why}. Run compare_field once per field in fields_to_compare (name = "
        "the field). Then find_gaps once. Then scan_for_field once per gap (name = the gap "
        "exactly as listed). Then finish. You never see or judge the values; code does.",
        planner_view, ACTIONS)


def check_fields(review_state: dict, planner=None) -> dict:
    """Check one finished review. Reads files, writes nothing."""
    state = {
        "package": review_state["package"],
        "compared": {},   # field -> "agree", "differ" or "not enough values"
        "gaps": None,     # "file.txt#field" entries
        "scanned": {},    # gap -> lines for the rep
        "findings": [],
        "log": [],
        "stop_reason": None,
    }
    read = review_state["read"]
    flagged = {r["doc"] for r in (review_state["checklist"] or [])
               if r["status"] == "unreadable"}

    def compare(field: str, entry: dict) -> None:
        if field not in checklist.COMPARED_FIELDS:
            raise harness.ToolError(f"not a compared field: {field!r}")
        docs = [{"file": name, "value": str(info["fields"][field]["value"]),
                 "evidence": info["fields"][field]["evidence"]}
                for name, info in read.items()
                if info["type"] in checklist.COMPARED_FIELDS[field]
                and info["fields"].get(field, {}).get("value") is not None]
        if len(docs) < 2:
            state["compared"][field] = entry["result"] = "not enough values"
        elif len({_same(d["value"]) for d in docs}) == 1:
            state["compared"][field] = entry["result"] = "agree"
        else:
            state["compared"][field] = entry["result"] = "differ"
            state["findings"].append({"kind": "mismatch", "field": field, "docs": docs})

    def find_gaps(entry: dict) -> None:
        gaps = []
        for name, info in read.items():
            for field in checklist.REQUIRED_FIELDS.get(info["type"], []):
                # A date behind an unreadable row is already in front of the rep.
                if field in DATE_FIELDS and info["type"] in flagged:
                    continue
                if info["fields"].get(field, {}).get("value") is None:
                    gaps.append(f"{name}#{field}")
        state["gaps"] = gaps
        entry["result"] = f"{len(gaps)} value{'s' if len(gaps) != 1 else ''} not read"

    def scan(gap: str, entry: dict) -> None:
        if gap not in (state["gaps"] or []):
            raise harness.ToolError(f"not a listed gap: {gap!r}")
        name, _, field = gap.partition("#")
        lines = tools.ALLOWED_TOOLS["find_field_lines"](state["package"], name, field)
        state["scanned"][gap] = lines
        state["findings"].append({"kind": "missing_field", "field": field, "file": name,
                                  "doc_type": read[name]["type"], "hints": lines})
        entry["result"] = f"{len(lines)} line{'s' if len(lines) != 1 else ''} for the rep"

    def act(state, step, entry):
        action = step["action"]
        if action == "compare_field":
            compare(str(step.get("name", "")), entry)
        elif action == "find_gaps":
            find_gaps(entry)
        elif action == "scan_for_field":
            scan(str(step.get("name", "")), entry)
        elif action == "finish":
            left = [f for f in checklist.COMPARED_FIELDS if f not in state["compared"]]
            left += [g for g in (state["gaps"] or []) if g not in state["scanned"]]
            if left or state["gaps"] is None:
                return f"finished early: {len(left) + (state['gaps'] is None)} checks not done"
            return "done: every comparison and gap was looked at"
        return None

    return harness.run_loop(planner or RulePlanner(), state, ACTIONS, act, MAX_PASSES)
