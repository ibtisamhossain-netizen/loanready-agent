"""Checklist rules for an auto-refinance package.

PLACEHOLDER: these rules are NOT confirmed with MCU operations.
The PRD says the real document list and freshness rules must be
confirmed before launch. Every rule lives here, in plain code, so the
model never decides what counts as missing or stale and the whole
file is cheap to replace once MCU confirms the real list.
"""
from __future__ import annotations

from datetime import date, timedelta

CONFIRMED = False  # flip only after MCU operations signs off

REQUIRED_DOCS = ["photo_id", "pay_stub", "vehicle_registration", "payoff_letter",
                 "insurance_card", "title"]

# insurance_card and title come from the team's research (Priscilla Batroni,
# Nov 10, 2026), which found both on MCU's real auto-refinance checklist.
# Both rules are ASSUMPTIONS (guesses), not confirmed with MCU operations:
#   - insurance_card: required, and must be unexpired on the visit date, like
#     the photo ID. The research does not say how current it must be. (assumption)
#   - title (NY Certificate of Title): required for every package. MCU's checklist
#     says NY vehicles, but synthetic registrations record no state, so the demo
#     asks every package for one. Presence is enough: no date rule. (assumption)
# The pay stub and photo ID rules are unchanged: those questions are still open.

# Max age in days, counted from the document's issue date (assumption)
MAX_AGE_DAYS = {
    "pay_stub": 30,
}

# Documents with an expiry date that must still be valid (assumption)
EXPIRES = {"photo_id", "vehicle_registration", "insurance_card"}

# Statuses the rep asks the member to fix. Anything else the rep reads first.
ASK_STATUSES = {"missing", "expired", "stale"}

# Values the field check expects on each document type (assumption)
REQUIRED_FIELDS = {
    "photo_id": ["name", "address", "expires"],
    "pay_stub": ["name", "issued", "income"],
    "vehicle_registration": ["name", "vin", "expires"],
    "payoff_letter": ["name", "vin", "issued", "payoff", "good_through"],
    "insurance_card": ["name", "expires"],
    "title": ["name", "vin"],
}

# Values that must agree wherever they appear (assumption). The insurance card
# is not in the name comparison: the research does not say whose name must be
# on the policy, so a difference there is not treated as a mismatch (assumption).
# Its VIN is not compared either: the research does not say the card must list
# the vehicle, so a card for another vehicle is not flagged (assumption).
COMPARED_FIELDS = {
    "name": set(REQUIRED_DOCS) - {"insurance_card"},
    "vin": {"vehicle_registration", "payoff_letter", "title"},
}

# Days after the last activity to look at an open file again (assumption). This
# is a staff reminder only, not a legal deadline: MCU compliance has not approved
# any timing for incomplete files.
FOLLOW_UP_DAYS = 3


def check(results: dict, as_of: date, conflicts: dict | None = None) -> list[dict]:
    """results maps doc_type -> extracted fields (dates as date objects).

    conflicts maps doc_type -> file names when more than one file has that
    type. The checklist never picks one: the rep decides (assumption).

    Returns one row per required document with status:
    ok, missing, expired, stale, or unreadable.
    """
    conflicts = conflicts or {}
    rows = []
    for doc in REQUIRED_DOCS:
        if doc in conflicts:
            rows.append({"doc": doc, "status": "unreadable",
                         "rule": f"{len(conflicts[doc])} documents of this type "
                                 f"({', '.join(conflicts[doc])}); rep picks one"})
            continue
        fields = results.get(doc)
        if fields is None:
            rows.append({"doc": doc, "status": "missing", "rule": "required document"})
            continue
        if doc == "payoff_letter":
            good_through = fields.get("good_through")
            issued = fields.get("issued")
            if not isinstance(good_through, date):
                status, rule = "unreadable", "needs one unambiguous good-through date; rep review required"
            elif issued is not None and (issued > as_of or good_through < issued):
                status, rule = "unreadable", "inconsistent payoff dates; rep review required"
            elif good_through < as_of:
                status, rule = "stale", f"good-through date passed ({good_through.isoformat()})"
            else:
                status, rule = "ok", f"valid through {good_through.isoformat()} (inclusive; demo assumption)"
            rows.append({"doc": doc, "status": status, "rule": rule})
            continue
        if doc in EXPIRES:
            exp = fields.get("expires")
            if exp is None:
                rows.append({"doc": doc, "status": "unreadable", "rule": "needs an expiry date"})
            elif exp < as_of:
                rows.append({"doc": doc, "status": "expired", "rule": f"expired {exp.isoformat()}"})
            else:
                rows.append({"doc": doc, "status": "ok", "rule": "valid"})
            continue
        if doc in MAX_AGE_DAYS:
            issued = fields.get("issued")
            limit = MAX_AGE_DAYS[doc]
            if issued is None:
                rows.append({"doc": doc, "status": "unreadable", "rule": "needs an issue date"})
            elif (as_of - issued).days > limit:
                rows.append({"doc": doc, "status": "stale",
                             "rule": f"older than {limit} days ({issued.isoformat()})"})
            else:
                rows.append({"doc": doc, "status": "ok", "rule": f"within {limit} days"})
            continue
        rows.append({"doc": doc, "status": "ok", "rule": "present"})
    return rows


def next_lapse(results: dict, as_of: date) -> date | None:
    """The soonest day on or after as_of that a document stops counting."""
    dates = [results.get(doc, {}).get("expires") for doc in EXPIRES]
    dates.append(results.get("payoff_letter", {}).get("good_through"))
    for doc, limit in MAX_AGE_DAYS.items():
        issued = results.get(doc, {}).get("issued")
        if isinstance(issued, date):
            dates.append(issued + timedelta(days=limit))
    upcoming = [d for d in dates if isinstance(d, date) and d >= as_of]
    return min(upcoming) if upcoming else None


def follow_up_date(last_activity: date, lapse: date | None) -> date:
    """Suggested staff reminder: a few days out, sooner if a document will lapse."""
    follow_up = last_activity + timedelta(days=FOLLOW_UP_DAYS)
    return min(follow_up, lapse) if lapse else follow_up
