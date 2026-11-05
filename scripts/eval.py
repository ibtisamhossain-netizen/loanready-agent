"""End-to-end eval: run the agent on every synthetic package and compare
its flags to the labels. PRD target: correct flags on at least 9 of 10.

    python3 scripts/eval.py
"""
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from loanready import agent, fieldcheck, followup  # noqa: E402

LABELS = Path(__file__).resolve().parent.parent / "data" / "synthetic" / "labels.json"


def main():
    data = json.loads(LABELS.read_text())
    as_of = date.fromisoformat(data["as_of"])
    passed, failed, paths = 0, [], set()
    for pkg, expected in data["expected_flags"].items():
        state = agent.review(pkg, as_of, planner=agent.RulePlanner())
        got = {r["doc"]: r["status"] for r in agent.flags(state)}
        checked = fieldcheck.check_fields(state)
        found = sorted(f"{x['kind']}:{x['field']}" for x in checked["findings"])
        want = sorted(data["expected_field_findings"].get(pkg, []))
        selected = list(got)
        draft = followup.draft_followup(state, selected)
        draft_ok = not selected or (draft["stop_reason"].startswith("done")
                                    and {i["doc"] for i in draft["items"]} == set(selected))
        ok = (got == expected and state["stop_reason"].startswith("done") and found == want
              and checked["stop_reason"].startswith("done") and draft_ok)
        passed += ok
        # the shape of the run, ignoring which file was read
        path = tuple(e["action"] for e in state["log"] if e["action"] != "read_document")
        paths.add(path)
        mark = "PASS" if ok else "FAIL"
        print(f"{mark} {pkg}: expected {expected or 'no flags'} | got {got or 'no flags'} | "
              f"fields {found or 'clean'} | {len(state['log'])} passes: {' > '.join(path)} | "
              f"{state['stop_reason']}")
        if not ok:
            failed.append(pkg)
    total = len(data["expected_flags"])
    print(f"\nEnd-to-end success: {passed}/{total} (regression gate: all packages pass)")
    print(f"Distinct paths taken: {len(paths)} (a fixed chain would show 1)")
    return 0 if total > 0 and not failed else 1


if __name__ == "__main__":
    sys.exit(main())
