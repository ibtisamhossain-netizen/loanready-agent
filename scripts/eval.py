"""End-to-end eval: run the agent on every synthetic package and compare
its flags to the labels. PRD target: correct flags on at least 9 of 10.

    python3 scripts/eval.py
"""
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from loanready import agent  # noqa: E402

LABELS = Path(__file__).resolve().parent.parent / "data" / "synthetic" / "labels.json"


def main():
    data = json.loads(LABELS.read_text())
    as_of = date.fromisoformat(data["as_of"])
    passed, failed = 0, []
    for pkg, expected in data["expected_flags"].items():
        state = agent.review(pkg, as_of, planner=agent.RulePlanner())
        got = {r["doc"]: r["status"] for r in agent.flags(state)}
        ok = got == expected and state["stop_reason"].startswith("done")
        passed += ok
        mark = "PASS" if ok else "FAIL"
        print(f"{mark} {pkg}: expected {expected or 'no flags'} | got {got or 'no flags'} | {state['stop_reason']}")
        if not ok:
            failed.append(pkg)
    total = len(data["expected_flags"])
    print(f"\nEnd-to-end success: {passed}/{total} (target: at least 9/{total})")
    return 0 if passed >= 9 else 1


if __name__ == "__main__":
    sys.exit(main())
