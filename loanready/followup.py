"""Follow-up agent (story 4): an editable request for the items the rep selected.

A writer words the draft, plain code checks it, and a draft that fails is
rewritten once with the reasons. If it still fails, the agent falls back to a
fixed template. The offline writer is that template, so this works with no key.

The model writer only sees document types and what is needed. It never sees
member details, document text or file names. There is no send action anywhere:
the rep edits the draft and sends it through an approved MCU channel.
"""
from __future__ import annotations

import json
import re

from . import agent, harness

ACTIONS = {"write_draft", "check_draft", "use_template", "finish"}
MAX_WRITES = 2
MAX_PASSES = 2 * MAX_WRITES + 3
MAX_BODY_CHARS = 1200
MARKER = "DRAFT - review and edit before sending through an approved MCU channel."
GREETING = "[member name]"

LABELS = {
    "photo_id": "photo ID",
    "pay_stub": "pay stub",
    "vehicle_registration": "vehicle registration",
    "payoff_letter": "payoff letter",
}
# A draft must not decide anything, promise anything, or invent contact details.
FORBIDDEN = {
    "decision or credit language": re.compile(
        r"approv|den(y|ied|ial)|declin|eligib|qualif|guarante|underwrit|credit (score|report)"
        r"|interest rate|\bapr\b", re.IGNORECASE),
    "a link or email address": re.compile(r"https?://|www\.|@"),
    "a number, such as an invented date, amount or phone number": re.compile(r"\d"),
}


def build_items(review_state: dict, selected: list) -> tuple:
    """(items to request, ignored). Only a flagged document can be requested."""
    rows = {r["doc"]: r for r in agent.flags(review_state)}
    items, ignored = [], []
    for doc in selected:
        if doc not in rows:
            ignored.append(doc)
            continue
        label, status = LABELS[doc], rows[doc]["status"]
        if doc in review_state["conflicts"]:
            need = f"confirmation of which {label} we should use"
        elif status == "missing":
            need = f"your {label}"
        elif status == "expired":
            need = f"an unexpired {label}"
        elif doc == "payoff_letter" and status == "stale":
            need = "an updated payoff letter from your current lender"
        elif status == "stale":
            need = f"a more recent {label}"
        else:
            need = f"a clearer copy of your {label}"
        items.append({"doc": doc, "label": label, "need": need})
    return items, ignored


def template_body(items: list) -> str:
    needs = "\n".join(f"- {i['need'][0].upper()}{i['need'][1:]}" for i in items)
    return (f"Hello {GREETING},\n\nTo keep your auto refinance application moving, we still need:\n"
            f"{needs}\n\nPlease let us know if you have any questions.")


class TemplateWriter:
    source = "template"

    def write(self, items: list, problems: list) -> str:
        return template_body(items)


class ModelWriter:
    source = "model"
    SYSTEM = (
        "You write a short, friendly request from a credit union representative to a member, "
        f"asking for the documents listed. Start with 'Hello {GREETING},' and keep that "
        "placeholder exactly. Name each listed document using its label, and no other document. "
        "Do not mention approval, eligibility, credit, rates or timing. Do not use digits, links "
        "or contact details. Reply with the message text only. The rep will edit and send it."
    )

    def __init__(self):
        import anthropic  # optional dependency
        import os

        self.client = anthropic.Anthropic()
        self.model = os.environ["MODEL_ID"]

    def write(self, items: list, problems: list) -> str:
        request = {"documents": [{"label": i["label"], "what_we_need": i["need"]} for i in items]}
        if problems:
            request["fix_these_problems_from_your_last_draft"] = problems
        return harness.call_model(self.client, self.model, self.SYSTEM, json.dumps(request))


def make_writer():
    return ModelWriter() if harness.model_settings() else TemplateWriter()


def check_body(body: str, items: list) -> list:
    """Plain-code check of a draft body. Returns the problems found."""
    problems = []
    low = body.lower()
    if not body.strip():
        return ["the draft is empty"]
    if len(body) > MAX_BODY_CHARS:
        problems.append(f"the draft is longer than {MAX_BODY_CHARS} characters")
    if GREETING not in body:
        problems.append(f"the placeholder {GREETING} is missing")
    selected = {i["doc"] for i in items}
    for doc, label in LABELS.items():
        named = label.lower() in low
        if doc in selected and not named:
            problems.append(f"it does not name the {label}")
        elif doc not in selected and named:
            problems.append(f"it names the {label}, which was not selected")
    # A numbered list's "1." is formatting, not an invented date or amount.
    text = re.sub(r"^\s*\d{1,2}[.)]\s", "", body, flags=re.MULTILINE)
    for what, pattern in FORBIDDEN.items():
        if pattern.search(text):
            problems.append(f"it contains {what}")
    return problems


class RulePlanner:
    def next_action(self, state: dict) -> dict:
        if state["body"] is None:
            return {"action": "write_draft", "why": "start: word the request"}
        if state["problems"] is None:
            return {"action": "check_draft", "why": "check the wording against the selected items"}
        if state["problems"]:
            if state["writes"] < MAX_WRITES:
                return {"action": "write_draft", "why": "the last draft failed its check"}
            if state["source"] != TemplateWriter.source:
                return {"action": "use_template", "why": "still failing; use the fixed wording"}
        return {"action": "finish", "why": "the draft passed its check"}


def draft_followup(review_state: dict, selected: list, writer=None, planner=None) -> dict:
    """Build a draft for the rep to edit. Nothing here sends or saves anything."""
    writer = writer or TemplateWriter()
    items, ignored = build_items(review_state, selected)
    state = {"items": items, "ignored": ignored, "body": None, "problems": None, "writes": 0,
             "last_problems": [], "source": None, "draft": "", "log": [], "stop_reason": None}
    if not items:
        state["stop_reason"] = "nothing to draft: no flagged item was selected"
        return state

    def act(state, step, entry):
        action = step["action"]
        if action == "write_draft":
            state["writes"] += 1
            state["source"] = writer.source
            state["problems"] = None
            try:
                state["body"] = writer.write(items, state["last_problems"])
                entry["result"] = f"attempt {state['writes']}"
            except harness.ModelError as err:
                state["body"] = ""
                entry["result"] = str(err)
        elif action == "check_draft":
            if state["body"] is None:
                raise harness.ToolError("no draft to check yet")
            state["problems"] = state["last_problems"] = check_body(state["body"], items)
            entry["result"] = "; ".join(state["problems"]) or "passed"
        elif action == "use_template":
            state["body"] = template_body(items)
            state["source"] = TemplateWriter.source
            state["problems"] = None
            entry["result"] = "fixed wording"
        elif action == "finish":
            if state["problems"] is None or state["problems"]:
                return "finished early: the draft did not pass its check"
            state["draft"] = f"{MARKER}\n\n{state['body']}"
            return "done: the draft passed its check; the rep edits and sends it"
        return None

    return harness.run_loop(planner or RulePlanner(), state, ACTIONS, act, MAX_PASSES)
