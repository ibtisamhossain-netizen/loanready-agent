"""Checklist rules for an auto-refinance package.

PLACEHOLDER: these rules are NOT confirmed with MCU operations.
The PRD says the real document list and freshness rules must be
confirmed before launch. Every rule lives here, in plain code, so the
model never decides what counts as missing or stale and the whole
file is cheap to replace once MCU confirms the real list.
"""
from datetime import date

CONFIRMED = False  # flip only after MCU operations signs off

REQUIRED_DOCS = ["photo_id", "pay_stub", "vehicle_registration", "payoff_letter"]

# Max age in days, counted from the document's issue date (assumption)
MAX_AGE_DAYS = {
    "pay_stub": 30,
    "payoff_letter": 10,
}

# Documents with an expiry date that must still be valid (assumption)
EXPIRES = {"photo_id", "vehicle_registration"}


def check(results: dict, as_of: date) -> list[dict]:
    """results maps doc_type -> extracted fields (dates as date objects).

    Returns one row per required document with status:
    ok, missing, expired, stale, or unreadable.
    """
    rows = []
    for doc in REQUIRED_DOCS:
        fields = results.get(doc)
        if fields is None:
            rows.append({"doc": doc, "status": "missing", "rule": "required document"})
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
