"""LoanReady demo screen for the rep at the desk.

    .venv/bin/python -m streamlit run app.py

Runs locally on synthetic data with the offline planner. It sends nothing and
decides nothing: the rep verifies every result. Layout and tokens are
described in docs/ui-handoff.md.

Every piece of document-derived text (file names, source lines, hints) is
escaped before it goes into HTML, so an uploaded file cannot inject markup.
"""
import json
from datetime import date, timedelta
from html import escape
from pathlib import Path

import streamlit as st

from loanready import agent, checklist, store, tools

ROOT = Path(__file__).resolve().parent
LABELS = ROOT / "data" / "synthetic" / "labels.json"
LABEL_DATE = date.fromisoformat(json.loads(LABELS.read_text())["as_of"])
STATUS = {"ok": "Passes", "missing": "Missing", "expired": "Expired", "stale": "Out of date",
          "unreadable": "Needs your check"}
TONE = {"ok": "pass", "missing": "flag", "expired": "flag", "stale": "flag", "unreadable": "review"}
NAMES = {"photo_id": "Photo ID", "pay_stub": "Pay stub", "vehicle_registration": "Vehicle registration",
         "payoff_letter": "Payoff letter"}
# Which extracted field a checklist rule looked at, so a flag can show its source line.
RULE_FIELD = {"photo_id": "expires", "vehicle_registration": "expires",
              "pay_stub": "issued", "payoff_letter": "good_through"}
STEP_NAMES = {"list_documents": "Listed the documents", "read_document": "Read",
              "scan_document": "Took a second look at", "run_checklist": "Ran the checklist",
              "finish": "Finished"}
RULER_BEFORE, RULER_AFTER = 90, 60  # days shown either side of the visit

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Public+Sans:ital,wght@0,400;0,500;0,600;0,700;1,400&display=swap');
:root {
  --paper: #F6F7F5; --ink: #1E2A32; --ink-soft: #55636D; --rule: #D3D9DD;
  --pass: #2E6B5A; --flag: #A8322A; --review: #8A5B12; --visit: #2747A0;
  --name-w: 190px; --space-xs: 4px; --space-sm: 8px; --space-md: 16px; --space-lg: 28px; --space-xl: 48px;
}
.stApp, .stApp *:not([data-testid="stIconMaterial"]) {
  font-family: 'Public Sans', system-ui, sans-serif;
}
.stApp { background: var(--paper); color: var(--ink); }
header[data-testid="stHeader"], #MainMenu, footer { display: none; }
.block-container { max-width: 1040px; padding-top: var(--space-lg); padding-bottom: var(--space-xl); }
h1, h2, h3 { color: var(--ink); letter-spacing: -0.01em; }
.lr-brand { font-size: 1.05rem; font-weight: 700; margin: 0; }
.lr-brand span { font-weight: 400; color: var(--ink-soft); }
.lr-demo { font-size: 0.85rem; color: var(--ink-soft); border-left: 3px solid var(--review);
  padding: var(--space-xs) var(--space-md); margin: var(--space-md) 0 var(--space-lg); max-width: 70ch; }
.lr-empty { font-size: 1.15rem; color: var(--ink-soft); padding: var(--space-xl) 0; max-width: 52ch; }
.lr-verdict { padding: var(--space-lg) 0 var(--space-md); border-top: 2px solid var(--ink); }
.lr-verdict h2 { font-size: 2rem; font-weight: 700; line-height: 1.15; margin: 0 0 var(--space-md); }
.lr-verdict h3 { font-size: 1rem; font-weight: 600; margin: var(--space-md) 0 0; padding: 0; }
.lr-ask { list-style: none; padding: 0; margin: 0; }
.lr-ask li { font-size: 1.2rem; line-height: 1.45; padding: var(--space-sm) 0 var(--space-sm) 22px;
  position: relative; max-width: 68ch; }
.lr-ask li::before { content: ""; position: absolute; left: 0; top: 0.95em; width: 10px; height: 10px; }
.lr-ask.flag li::before { background: var(--flag); }
.lr-ask.review li::before { background: var(--review); }
.lr-ask .why { display: block; font-size: 0.95rem; color: var(--ink-soft); }
.lr-quote { font-style: italic; color: var(--ink); }
.lr-clear { font-size: 1.2rem; color: var(--pass); margin: 0; }
.lr-section { font-size: 1rem; font-weight: 600; margin: var(--space-lg) 0 var(--space-sm);
  padding-top: var(--space-md); border-top: 1px solid var(--rule); }
.lr-section + .lr-note { margin-top: 0; }
.lr-note { font-size: 0.85rem; color: var(--ink-soft); margin: 0 0 var(--space-md); max-width: 70ch; }
/* the date ruler */
.lr-ruler { position: relative; margin-top: var(--space-sm); }
.lr-axis { position: relative; height: 22px; margin-left: var(--name-w); border-bottom: 1px solid var(--rule); }
.lr-tick { position: absolute; bottom: 0; height: 6px; border-left: 1px solid var(--rule); }
.lr-tick span { position: absolute; bottom: 8px; left: 3px; font-size: 0.75rem; color: var(--ink-soft); white-space: nowrap; }
.lr-row { display: flex; align-items: center; min-height: 46px; border-bottom: 1px solid var(--rule); }
.lr-row-name { width: var(--name-w); flex: none; font-size: 0.95rem; }
.lr-row-name b { font-weight: 600; display: block; }
.lr-row-name small { font-size: 0.8rem; }
.lr-row-name small.pass { color: var(--pass); } .lr-row-name small.flag { color: var(--flag); }
.lr-row-name small.review { color: var(--review); }
.lr-track { position: relative; flex: 1; height: 46px; }
.lr-bar { position: absolute; top: 19px; height: 8px; }
.lr-bar.pass { background: var(--pass); } .lr-bar.flag { background: var(--flag); }
.lr-dot { position: absolute; top: 16px; width: 2px; height: 14px; background: var(--ink); }
.lr-lbl { position: absolute; top: 30px; z-index: 2; background: var(--paper); padding-right: 4px; font-size: 0.72rem; color: var(--ink-soft); white-space: nowrap;
  font-variant-numeric: tabular-nums; }
.lr-lbl.end { transform: translateX(-100%); }
.lr-ruler { margin-bottom: var(--space-lg); }
.lr-none { position: absolute; top: 14px; left: 8px; font-size: 0.85rem; color: var(--ink-soft); }
.lr-visit { position: absolute; top: 0; bottom: 0; width: 2px; background: var(--visit); pointer-events: none; z-index: 1; }
.lr-visit span { position: absolute; top: 2px; left: 6px; font-size: 0.75rem; font-weight: 600; color: var(--visit);
  white-space: nowrap; background: var(--paper); padding: 0 2px; }
/* documents and steps */
.lr-fields { width: 100%; border-collapse: collapse; font-size: 0.9rem; font-variant-numeric: tabular-nums; }
.lr-fields td { padding: 6px var(--space-sm) 6px 0; border-bottom: 1px solid var(--rule); vertical-align: top; }
.lr-fields td:first-child { color: var(--ink-soft); width: 120px; }
.lr-fields td:last-child { color: var(--ink-soft); font-style: italic; }
.lr-original { white-space: pre-wrap; font-size: 0.85rem; background: #fff; border: 1px solid var(--rule);
  padding: var(--space-sm) var(--space-md); margin-top: var(--space-sm); line-height: 1.6; }
.lr-steps { padding-left: 1.4em; margin: 0; font-size: 0.9rem; }
.lr-steps li { padding: 3px 0; }
.lr-steps .why { color: var(--ink-soft); }
.lr-steps .res { font-weight: 600; }
.lr-steps .bad { color: var(--flag); font-weight: 600; }
.lr-stop { font-size: 0.9rem; margin: var(--space-sm) 0 0; }
.lr-saved { font-size: 0.8rem; color: var(--ink-soft); margin-top: var(--space-lg); }
div[data-testid="stExpander"] details { border: none; border-top: 1px solid var(--rule); border-radius: 0; background: transparent; }
div[data-testid="stExpander"] summary { padding-left: 0; font-weight: 600; }
.stButton button[kind="primary"] { background: var(--ink); border-color: var(--ink); border-radius: 2px; font-weight: 600; }
.stButton button[kind="primary"]:hover { background: var(--visit); border-color: var(--visit); }
.stButton button:focus-visible { outline: 3px solid var(--visit); outline-offset: 2px; }
@media (max-width: 700px) {
  .lr-verdict h2 { font-size: 1.5rem; }
  .lr-ask li { font-size: 1.05rem; }
  :root { --name-w: 104px; }
  .lr-row { align-items: flex-start; padding: var(--space-sm) 0; }
  .lr-row-name { font-size: 0.85rem; }
  .lr-track { height: auto; min-height: 46px; }
  .lr-lbl, .lr-lbl.end { position: static; display: block; transform: none; margin-top: 32px;
    white-space: normal; background: transparent; }
  .lr-tick span { display: none; }
  .lr-visit span { left: auto; right: 6px; }
}
@media (prefers-reduced-motion: reduce) { * { transition: none !important; } }
</style>
"""


def nice(d: date) -> str:
    return f"{d:%b} {d.day}, {d.year}"


def doc_fields(state: dict, doc_type: str):
    """(file name, fields) for the one document of this type, or (None, None)."""
    found = [(n, i["fields"]) for n, i in state["read"].items() if i["type"] == doc_type]
    return found[0] if len(found) == 1 else (None, None)


def source_line(state: dict, row: dict) -> str | None:
    name, fields = doc_fields(state, row["doc"])
    field = (fields or {}).get(RULE_FIELD[row["doc"]])
    return field["evidence"] if field else None


def quote(evidence: str) -> str:
    """'line 3: Pay date: x' -> 'line 3, "Pay date: x"', escaped."""
    where, _, text = evidence.partition(": ")
    return f'{escape(where)}, <span class="lr-quote">&ldquo;{escape(text)}&rdquo;</span>'


def ask_sentence(state: dict, row: dict) -> tuple[str, str]:
    """(what to say, why) for one flagged checklist row. Returns HTML."""
    doc, status = row["doc"], row["status"]
    name = NAMES[doc].lower()
    _, fields = doc_fields(state, doc)
    get = lambda k: ((fields or {}).get(k) or {}).get("value")
    if status == "missing":
        return f"A {name}.", "None was in the package."
    if status == "expired":
        exp = get("expires")
        return f"An unexpired {name}.", f"This one expired {nice(exp)}." if exp else escape(row["rule"])
    if status == "stale" and doc == "pay_stub":
        issued = get("issued")
        limit = checklist.MAX_AGE_DAYS["pay_stub"]
        return ("A more recent pay stub.",
                f"This one is from {nice(issued)}, more than {limit} days before the visit." if issued
                else escape(row["rule"]))
    if status == "stale" and doc == "payoff_letter":
        gt = get("good_through")
        return ("A new payoff letter from the current lender.",
                f"This one was good through {nice(gt)}." if gt else escape(row["rule"]))
    if doc in state["conflicts"]:
        files = ", ".join(escape(f) for f in state["conflicts"][doc])
        return f"Decide which {name} counts.", f"The package has more than one: {files}."
    src = source_line(state, row)
    hints = state["hints"].get(doc) or []
    if hints:
        why = "LoanReady could not read its date. These lines look like dates: " + "; ".join(quote(h) for h in hints) + "."
    elif src:
        why = f"LoanReady could not use the date on {quote(src)}."
    else:
        why = "LoanReady found no date it could read on it."
    return f"Read the {name} date yourself.", why


def verdict_html(state: dict) -> str:
    flagged = agent.flags(state)
    ask = [r for r in flagged if TONE[r["status"]] == "flag"]
    check = [r for r in flagged if TONE[r["status"]] == "review"]

    def items(rows, tone):
        lis = "".join(f'<li>{say}<span class="why">{why}</span></li>'
                      for say, why in (ask_sentence(state, r) for r in rows))
        return f'<ul class="lr-ask {tone}">{lis}</ul>'

    if not flagged:
        return ('<div class="lr-verdict"><h2>Nothing to ask for.</h2>'
                '<p class="lr-clear">All four documents pass the demo checklist. '
                'Compare them with the originals before the member leaves.</p></div>')
    n = len(ask)
    c = len(check)
    head = (f"Ask the member for {n} document{'s' if n != 1 else ''} before they leave." if ask
            else f"Check {c} thing{'s' if c != 1 else ''} yourself before the member leaves.")
    body = items(ask, "flag") if ask else ""
    if check and ask:
        body += f"<h3>Then check {c} thing{'s' if c != 1 else ''} yourself</h3>" + items(check, "review")
    elif check:
        body += items(check, "review")
    return f'<div class="lr-verdict"><h2>{head}</h2>{body}</div>'


def ruler_html(state: dict, visit: date) -> str:
    start, end = visit - timedelta(days=RULER_BEFORE), visit + timedelta(days=RULER_AFTER)
    span = (end - start).days

    def pct(d: date) -> float:
        return max(0.0, min(100.0, (d - start).days / span * 100))

    ticks = []
    m = date(start.year, start.month, 1)
    while m <= end:
        if m >= start:
            near_visit = -4 < pct(m) - pct(visit) < 22  # the visit label sits here
            label = "" if near_visit else f"<span>{m:%b}</span>"
            ticks.append(f'<div class="lr-tick" style="left:{pct(m):.2f}%">{label}</div>')
        m = date(m.year + (m.month == 12), m.month % 12 + 1, 1)

    rows = []
    for row in state["checklist"]:
        doc, status = row["doc"], row["status"]
        _, fields = doc_fields(state, doc)
        get = lambda k: ((fields or {}).get(k) or {}).get("value")
        tone = TONE[status]
        track = ""
        if doc in checklist.EXPIRES:
            exp = get("expires")
            if isinstance(exp, date):
                track = bar(start, exp, pct, tone, f"valid until {nice(exp)}", end)
        elif doc == "pay_stub":
            iss = get("issued")
            if isinstance(iss, date):
                days = checklist.MAX_AGE_DAYS["pay_stub"]
                limit = iss + timedelta(days=days)
                track = bar(iss, limit, pct, tone,
                            f"issued {nice(iss)}, counts for {days} days, to {nice(limit)}", end)
        elif doc == "payoff_letter":
            iss, gt = get("issued"), get("good_through")
            if isinstance(gt, date):
                first = iss if isinstance(iss, date) and iss <= gt else gt
                text = (f"issued {nice(first)}, good through {nice(gt)}" if first != gt
                        else f"good through {nice(gt)}")
                track = bar(first, gt, pct, tone, text, end)
        if not track:
            note = {"missing": "Not in the package",
                    "unreadable": "Two documents of this type" if doc in state["conflicts"] else "No readable date"
                    }.get(status, "")
            track = f'<span class="lr-none">{note}</span>'
        rows.append(f'<div class="lr-row"><div class="lr-row-name"><b>{NAMES[doc]}</b>'
                    f'<small class="{tone}">{STATUS[status]}</small></div>'
                    f'<div class="lr-track">{track}</div></div>')

    visit_line = (f'<div class="lr-visit" style="left:calc(var(--name-w) + (100% - var(--name-w)) * {pct(visit) / 100:.4f})">'
                  f'<span>Visit, {nice(visit)}</span></div>')
    return (f'<div class="lr-ruler"><div class="lr-axis">{"".join(ticks)}</div>'
            f'{"".join(rows)}{visit_line}</div>')


def bar(a: date, b: date, pct, tone: str, label: str, end: date) -> str:
    l, r = pct(a), pct(b)
    w = max(r - l, 0.6)
    if b > end:
        label += ", past the right edge"
    # left-align the label at the bar start unless that would run off the right side
    place = (f'class="lr-lbl" style="left:{l:.2f}%"' if l < 55
             else f'class="lr-lbl end" style="left:{r:.2f}%"')
    return (f'<div class="lr-bar {tone}" style="left:{l:.2f}%;width:{w:.2f}%"></div>'
            f'<div class="lr-dot" style="left:{r:.2f}%"></div>'
            f'<span {place}>{label}</span>')


def fields_html(state: dict, name: str, info: dict) -> str:
    labels = {"issued": "Issue date", "expires": "Expires", "good_through": "Good through", "vin": "VIN",
              "income": "Gross pay", "payoff": "Payoff amount", "name": "Name", "address": "Address"}
    rows = "".join(
        f"<tr><td>{labels.get(k, k)}</td>"
        f"<td>{'No usable value' if v['value'] is None else escape(nice(v['value']) if isinstance(v['value'], date) else str(v['value']))}</td>"
        f"<td>{escape(v['evidence'])}</td></tr>"
        for k, v in info["fields"].items())
    table = f'<table class="lr-fields">{rows}</table>' if rows else '<p class="lr-note">No fields found.</p>'
    original = escape(tools.read_document(state["package"], name))
    return f'{table}<div class="lr-original">{original}</div>'


def steps_html(state: dict) -> str:
    lis = []
    for e in state["log"]:
        target = f" {escape(e['name'])}" if e.get("name") else ""
        why = f' <span class="why">because {escape(e["why"])}</span>' if e.get("why") else ""
        if e.get("refused"):
            res = ' <span class="bad">refused by the harness</span>'
        elif e.get("error"):
            res = f' <span class="bad">error: {escape(e["error"])}</span>'
        elif e.get("result"):
            res = f' <span class="res">{escape(e["result"])}</span>'
        else:
            res = ""
        verb = STEP_NAMES.get(e["action"], e["action"] or "unknown action")
        lis.append(f"<li>{escape(verb)}{target}{why}.{res}</li>")
    return (f'<ol class="lr-steps">{"".join(lis)}</ol>'
            f'<p class="lr-stop">Stopped: {escape(state["stop_reason"] or "")}</p>')


def show_results(state: dict, record_id: str, visit: date) -> None:
    if state["checklist"] is None:
        st.markdown(f'<div class="lr-verdict"><h2>The check did not finish.</h2>'
                    f'<p class="lr-note">Reason: {escape(state["stop_reason"] or "unknown")}. '
                    f'Check the documents by hand, or run the check again.</p></div>', unsafe_allow_html=True)
        return
    st.markdown(verdict_html(state), unsafe_allow_html=True)

    st.markdown('<h3 class="lr-section">Dates against the visit</h3>'
                '<p class="lr-note">Each bar is the period a document counts as current. '
                'A bar that ends before the blue line has run out.</p>', unsafe_allow_html=True)
    st.markdown(ruler_html(state, visit), unsafe_allow_html=True)

    st.markdown('<h3 class="lr-section">Documents in the package</h3>'
                '<p class="lr-note">Compare each value with its line in the original.</p>',
                unsafe_allow_html=True)
    for name, info in state["read"].items():
        kind = NAMES.get(info["type"], "Not recognized, not counted")
        with st.expander(f"{name}: {kind}"):
            st.markdown(fields_html(state, name, info), unsafe_allow_html=True)

    with st.expander(f"How LoanReady checked it ({len(state['log'])} steps)"):
        st.markdown(steps_html(state), unsafe_allow_html=True)
    st.markdown(f'<p class="lr-saved">Saved on this computer as {escape(record_id)}.</p>', unsafe_allow_html=True)


st.set_page_config(page_title="LoanReady", layout="wide")
st.markdown(CSS, unsafe_allow_html=True)

top_l, top_r = st.columns([3, 1], vertical_alignment="bottom")
with top_l:
    st.markdown('<p class="lr-brand">LoanReady <span>auto refinance, document check at the desk</span></p>',
                unsafe_allow_html=True)
with top_r:
    visit_date = st.date_input("Visit date", value=date.today(), format="MM/DD/YYYY")
st.markdown('<p class="lr-demo">Demo with made-up documents only. Do not add real member files. '
            'The checklist rules are our own guesses until MCU confirms them. '
            'LoanReady sends nothing and makes no loan decisions.</p>', unsafe_allow_html=True)

sample_tab, upload_tab = st.tabs(["Sample package", "Member's documents"])
package = None
with sample_tab:
    samples = sorted(p.name for p in tools.DATA_ROOT.iterdir() if p.is_dir())
    c1, c2 = st.columns([3, 1], vertical_alignment="bottom")
    with c1:
        choice = st.selectbox("Sample package", samples,
                              index=samples.index("pkg11") if "pkg11" in samples else 0)
    with c2:
        if st.button("Check package", type="primary", key="run_sample", use_container_width=True):
            package = choice
    if visit_date != LABEL_DATE:
        st.caption(f"The sample answers were written for a visit on {nice(LABEL_DATE)}. "
                   "On another date some results change, which is expected.")
with upload_tab:
    files = st.file_uploader("Add the member's documents as .txt files", type=["txt"],
                             accept_multiple_files=True)
    if st.button("Check these documents", type="primary", disabled=not files, key="run_upload"):
        try:
            package = store.save_uploads([(f.name, f.getvalue()) for f in files])
        except tools.ToolError as err:
            st.markdown(f'<p class="lr-note" style="color:var(--flag)">Could not add the files: '
                        f'{escape(str(err))}.</p>', unsafe_allow_html=True)

if package:
    state = agent.review(package, visit_date, planner=agent.RulePlanner())
    st.session_state["result"] = (state, store.save_review(state, visit_date), visit_date)
if "result" in st.session_state:
    show_results(*st.session_state["result"])
else:
    st.markdown('<p class="lr-empty">Pick a sample package or add the member\'s documents, '
                'then check them. The answer shows what to ask for before the member leaves.</p>',
                unsafe_allow_html=True)
