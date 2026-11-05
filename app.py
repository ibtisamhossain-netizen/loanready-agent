"""LoanReady demo screen: upload documents, run the check, see flags beside the source.

    .venv/bin/python -m streamlit run app.py

Runs locally on synthetic data with the offline planner. It sends nothing and
decides nothing: the rep verifies every result.
"""
import json
from datetime import date
from pathlib import Path

import streamlit as st

from loanready import agent, checklist, store, tools

ROOT = Path(__file__).resolve().parent
LABELS = ROOT / "data" / "synthetic" / "labels.json"
DEFAULT_VISIT = date.fromisoformat(json.loads(LABELS.read_text())["as_of"])
STATUS = {"ok": "OK", "missing": "Missing", "expired": "Expired", "stale": "Stale", "unreadable": "Unreadable"}
# Which extracted field a checklist rule looked at, so a flag can show its source line.
RULE_FIELD = {"photo_id": "expires", "vehicle_registration": "expires",
              "pay_stub": "issued", "payoff_letter": "good_through"}


def label(text: str) -> str:
    return {"photo_id": "Photo ID", "vin": "VIN"}.get(text, text.replace("_", " ").capitalize())


def source_line(state: dict, row: dict) -> str:
    for doc in state["read"].values():
        if doc["type"] == row["doc"]:
            field = doc["fields"].get(RULE_FIELD[row["doc"]])
            return field["evidence"] if field else "That date was not found in this document."
    return "No document of this type was uploaded."


def show_results(state: dict, record_id: str) -> None:
    flagged = agent.flags(state)
    st.divider()
    if state["checklist"] is None:
        st.error(f"The check did not finish: {state['stop_reason']}")
        return
    if flagged:
        st.subheader(f"{len(flagged)} item{'s' if len(flagged) > 1 else ''} to resolve before the member leaves")
        for row in flagged:
            st.error(f"**{label(row['doc'])}: {STATUS[row['status']]}**  \nWhy: {row['rule']}  \n"
                     f"Source: `{source_line(state, row)}`")
    else:
        st.subheader("No checklist flags")
        st.success("All 4 required documents passed the demo checklist. Verify them against the originals.")

    st.markdown("#### Checklist")
    st.dataframe([{"Document": label(r["doc"]), "Status": STATUS[r["status"]], "Why": r["rule"],
                   "Source line": source_line(state, r)} for r in state["checklist"]],
                 hide_index=True, use_container_width=True)

    st.markdown("#### Fields beside their source line")
    for name, doc in state["read"].items():
        recognized = doc["type"] != "unknown"
        title = f"{name}: {label(doc['type'])}" if recognized else f"{name}: not recognized, not counted"
        with st.expander(title, expanded=False):
            st.dataframe([{"Field": label(k), "Value": "No usable value" if v["value"] is None else str(v["value"]),
                           "Source line": v["evidence"]} for k, v in doc["fields"].items()],
                         hide_index=True, use_container_width=True)
            st.code(tools.read_document(state["package"], name), language=None)

    with st.expander("Agent steps"):
        for entry in state["log"]:
            action = entry.get("action", entry.get("refused"))
            st.text(f"Pass {entry['pass']}: {action.get('action')} {action.get('name', '')}".rstrip())
        st.text(f"Stopped because: {state['stop_reason']}")
    st.caption(f"Saved locally as {record_id}.")


st.set_page_config(page_title="LoanReady", layout="wide")
st.title("LoanReady")
st.write("First-pass document check for auto-refinance applications at the member's visit.")
st.warning("Demo with synthetic documents only. Do not upload real member data. The checklist rules are our own "
           "assumptions, not confirmed by MCU. LoanReady sends nothing and makes no loan decisions.")
if not checklist.CONFIRMED:
    with st.expander("Demo checklist (assumption)"):
        st.markdown("- **Photo ID and vehicle registration:** unexpired on the day of the visit\n"
                    f"- **Pay stub:** issued within the last {checklist.MAX_AGE_DAYS['pay_stub']} days\n"
                    "- **Payoff letter:** valid through its printed good-through date, counting that day\n"
                    "- **No readable date:** flagged for the rep, never passed")

visit_date = st.date_input("Date of visit", value=DEFAULT_VISIT)
sample_tab, upload_tab = st.tabs(["Sample package", "Upload documents"])
package = None
with sample_tab:
    samples = sorted(p.name for p in tools.DATA_ROOT.iterdir() if p.is_dir())
    choice = st.selectbox("Synthetic package", samples, index=samples.index("pkg11") if "pkg11" in samples else 0)
    if st.button("Run check on sample", type="primary"):
        package = choice
with upload_tab:
    files = st.file_uploader("Add the member's documents (.txt)", type=["txt"], accept_multiple_files=True)
    if st.button("Run check on uploads", type="primary", disabled=not files):
        try:
            package = store.save_uploads([(f.name, f.getvalue()) for f in files])
        except tools.ToolError as err:
            st.error(str(err))

if package:
    state = agent.review(package, visit_date, planner=agent.RulePlanner())
    st.session_state["result"] = (state, store.save_review(state, visit_date))
if "result" in st.session_state:
    show_results(*st.session_state["result"])
