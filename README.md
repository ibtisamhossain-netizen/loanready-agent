# loanready-agent

LoanReady is a staff-facing tool for Municipal Credit Union Member Service Representatives. A rep uploads the documents for an auto-refinance application, and LoanReady checks them against a checklist, flags missing, expired, or stale items beside the source document, and keeps a simple list of open files and follow-ups. The rep verifies every result and sends every message.

Pursuit L2 Cycle 4 build by Ibtisam Hossain (build) and Priscilla Batroni (research).

## Status

Week 7: PRD done, user stories written, repo set up. First build: the review agent for stories 1 and 2 runs end to end on synthetic data.

## User stories

1. As an MCU Member Service Representative, I need to see which required auto-refinance documents are missing, expired, or stale while the member is at my desk, so that I can ask for them before the member leaves.
2. As an MSR, I need to see each extracted field beside its source page and correct or reject it, so that the file is right the first time.
3. As an MSR, I need a list of open applications with status, last activity, and next follow-up date, so that no file sits without a next action.
4. As an MSR, I need an editable follow-up draft built from the missing items I select, so that I can send a correct request through an approved MCU channel.
5. (Assumption) As an MCU QA reviewer, I need to maintain the checklist and freshness rules, so that reps check against current requirements.

Sources and demo tests for each story are in [docs/user-stories.md](docs/user-stories.md).

## Setup

For offline tests, create a virtual environment with `python3 -m venv .venv`, then install pytest with `.venv/bin/python -m pip install -r requirements-dev.txt`. Use `.venv/bin/python` for the commands below.

Copy `.env.example` to `.env` locally if needed. `.env` is in `.gitignore` and must never be committed. Offline mode needs no key. The optional live planner reads environment variables; it does not load `.env` automatically.

## Docs

- [User stories](docs/user-stories.md), each traced to the JD or PRD

## Scope

In scope for the MVP: one loan type (auto refinance), synthetic documents only, document classification and field extraction, plain-code checklist rules, an open-application list, and editable follow-up drafts.

Out of scope: loan decisions, credit underwriting or credit reports, real member data, automated messaging, and MCU system integrations.

## Build order

Story 1 (catch missing, expired, or stale documents during the visit) is built first. It is the core of the PRD problem and the JD's "accurate first-time documentation" goal, and stories 3 and 4 both depend on its output: the open-file list needs each file's status, and the follow-up draft is built from the missing items. Story 2 (fields beside their source line) comes with it, because a flag the rep can't check against the original isn't useful.

## Assumptions

These are working guesses so the build can move. Each one gets replaced when MCU or Priscilla's research confirms the real answer.

- The required documents for an auto refinance are photo ID, pay stub, vehicle registration, and a payoff letter from the current lender.
- A pay stub counts as stale after 30 days from its issue date.
- A payoff letter uses its explicit good-through date, not a guessed 10-day issue-age limit. The demo treats that date as inclusive at date-only granularity; MCU must confirm cutoff times and actual policy.
- Missing, blank, invalid, ambiguous, or repeated good-through dates require rep review (`unreadable`). No guessed date and no fallback to issue age. The original source line is retained. An issue date in the future or after the good-through date also requires review.
- Photo ID and registration only need to be unexpired on the day of the check.
- A document with no readable date is flagged "unreadable" for the rep to check, never passed.
- The check runs against the date of the visit, so a file that passes today can go stale later.
- Documents arrive as text files in one folder per application. Real uploads (PDFs, photos) are out of scope until the loop is proven.
- These rules live in `loanready/checklist.py` with `CONFIRMED = False` until MCU operations signs off.

## How the agent works

`loanready/agent.py` runs one review as a loop: observe the package state, pick one next action, run it, check the result, repeat.

- Actions are allow-listed: list documents, read a document, run the checklist, finish. Anything else is refused and the run stops.
- Tools are read-only and can only open files inside `data/synthetic/` (`loanready/tools.py`).
- Stop rules: done when every required document has a checklist result, a 12-pass limit, or the same action twice in a row.
- Checklist decisions are plain code in `loanready/checklist.py`, never the model. That file is a placeholder until MCU confirms the real document list (`CONFIRMED = False`).
- Every extracted field keeps the source line as evidence, so the rep can compare it to the original.
- The only output is an editable draft marked DRAFT. LoanReady never sends anything.
- Text inside a document is treated as data. Package 07 has a planted "ignore the checklist" note, and the agent still flags it.

The offline `RulePlanner` is used for tests and evals. `ClaudePlanner` asks the model for the next step when `ANTHROPIC_API_KEY` and `MODEL_ID` are set in `.env`, and its choice still goes through the same allow-list. The model planner has not been tested yet.

## Running it

```
python3 scripts/make_synthetic.py   # build the 16 synthetic packages
python3 scripts/eval.py             # end-to-end eval against the labels
python3 -m pytest -q tests          # safety and loop tests
```

The evaluation now includes the original 10 synthetic packages plus six payoff-date regression packages. The regression gate requires every package to pass. The rules and the labels were written together, so this checks loop behavior, not real-world accuracy. Real accuracy needs MCU's checklist and documents labeled by someone else.

The added cases cover a nine-day-old letter with an expired good-through date, ambiguous and blank dates, an invalid calendar date, validity ending today, and an older letter with an explicit later validity date. Unit tests also cover missing or duplicate dates and inconsistent issue/validity dates.

Verified locally on November 4, 2026: 28 tests passed and 16/16 synthetic packages matched their labels using the offline RulePlanner. These results do not measure live-model extraction or production accuracy.

## Safety

- Synthetic data only. Never commit real member data or API keys.
- Read-only tools first; the agent writes drafts only.
- Inputs are validated in code and tools are allow-listed.
- A person approves every correction and every message.
