# loanready-agent

LoanReady is a staff-facing tool for Municipal Credit Union Member Service Representatives. A rep uploads the documents for an auto-refinance application, and LoanReady checks them against a checklist, flags missing, expired, or stale items beside the source document, and keeps a simple list of open files and follow-ups. The rep verifies every result and sends every message.

Pursuit L2 Cycle 4 build by Ibtisam Hossain (build) and Priscilla Batroni (research).

## Status

Week 7: PRD revised and resubmitted, user stories written, repo set up. Four agents run end to end on synthetic data, and the local demo screen covers stories 1 to 4: flags beside the source, correcting or rejecting a value, the open-file list, and editable follow-up drafts. PDFs and photos, marking a requested document as received, and the checklist-maintenance screen are not built.

## User stories

1. As an MCU Member Service Representative, I need to see which required auto-refinance documents are missing, expired, or stale while the member is at my desk, so that I can ask for them before the member leaves.
2. As an MSR, I need to see each extracted field beside its source page and correct or reject it, so that the file is right the first time.
3. As an MSR, I need a list of open applications with status, last activity, and next follow-up date, so that no file sits without a next action.
4. As an MSR, I need an editable follow-up draft built from the missing items I select, so that I can send a correct request through an approved MCU channel.
5. (Assumption) As an MCU QA reviewer, I need to maintain the checklist and freshness rules, so that reps check against current requirements.

Sources and demo tests for each story are in [docs/user-stories.md](docs/user-stories.md).

## Setup

The project targets Python 3.9. For offline tests, create a virtual environment with `python3 -m venv .venv`, then install pytest with `.venv/bin/python -m pip install -r requirements-dev.txt`. Use `.venv/bin/python` for the commands below.

Offline mode needs no key. For the optional live planner, install `requirements.txt` and put `ANTHROPIC_API_KEY` and `MODEL_ID=claude-sonnet-5-5` in a local `.env` (see `.env.example`). `.env` is in `.gitignore` and must never be committed. Run `.venv/bin/python test_model.py` to check the key and model; it makes one small API call. `make_planner()` loads `.env`.

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

## The agents

| Agent | Story | File | What it does | What it may write |
|---|---|---|---|---|
| Review | 1, 2 | `loanready/agent.py` | Reads a package and runs the checklist | Nothing |
| Field check | 2 | `loanready/fieldcheck.py` | Compares names and VINs across documents, finds values it could not read, and gets the lines for the rep | Nothing |
| Open files | 3 | `loanready/pipeline.py` | Rechecks every open file against today and proposes a next step and follow-up date | Nothing |
| Follow-up | 4 | `loanready/followup.py` | Drafts a request for the items the rep selected and checks the wording | An editable draft on screen, never sent |

All four run on the same loop and guards (`loanready/harness.py`): an allow-list of actions, a pass limit set before the loop, repeat detection, and a log of every step. Each has an offline planner, so nothing depends on a key. Only the rep's actions change saved data: saving a correction, a follow-up date or a note, or closing a file.

The model is limited to two jobs, as the PRD says: choosing an agent's next step and wording a follow-up draft. It decides no result.

- **What the model sees.** Planners get only file names, field names, statuses and progress. The follow-up writer gets only document types and what is needed. Member details, document text and extracted values never reach it, and tests check that.
- **Field check.** Comparison is exact apart from spacing and case, so a near match still goes to the rep. If a required value was not read, the agent scans the file for lines with that label. Those lines are hints: they never fill in a value or change a checklist status.
- **Corrections.** A rep's correction or rejection reruns the checklist. The original value and source line stay visible, and the source file is never changed. Corrections are saved and carry over to later checks of the same file.
- **Open files.** A file that passed at the visit can go stale later, so each file is rechecked as of the date on screen, and any status that changed since the last check is called out. A follow-up date is the last activity plus 3 days, or sooner if a document will lapse first. A date the rep sets is kept. This timing is an assumption and a staff reminder only, not a legal deadline.
- **Follow-up drafts.** Plain code checks every draft: it must name exactly the selected documents and contain no decision or credit language, links or numbers. A draft that fails is rewritten once with the reasons, then replaced with fixed wording. No agent has a send action.

## How the review agent works

`loanready/agent.py` runs one review as a loop: observe the package state, pick one next action, run it, check the result, repeat.

- Actions are allow-listed: list documents, read a document, scan a document, run the checklist, finish. Anything else is refused and the run stops.
- The path depends on what the agent finds. After the first checklist run it looks at the flags. If a required document is missing and a file was not recognized, it scans that file in full, and if the file turns out to be the missing type, it runs the checklist again. If a document is unreadable, it scans it and collects lines that look like dates as hints for the rep. Hints never pass a document. If two files have the same type, the checklist flags it for the rep instead of picking one.
- Every pass logs the action, a short reason, and the result, and the demo screen shows them under "Agent steps".
- Tools are read-only and can only open files inside `data/synthetic/` (`loanready/tools.py`).
- Stop rules: done when every listed document is read and the checklist is current with a result for every required document; a pass limit set before the loop (30, with at most 12 documents per package); or the same action on the same file twice in a row. Finishing with an out-of-date checklist is reported as finishing early, not success.
- Checklist decisions are plain code in `loanready/checklist.py`, never the model. That file is a placeholder until MCU confirms the real document list (`CONFIRMED = False`).
- Every extracted field keeps the source line as evidence, so the rep can compare it to the original.
- The only output is an editable draft marked DRAFT. LoanReady never sends anything.
- Text inside a document is treated as data. Package 07 has a planted "ignore the checklist" note, and the agent still flags it. The model planner only sees file names and checklist statuses, never document text, and a test checks that.

The offline `RulePlanner` is used for tests and evals. `ClaudePlanner` asks the model for the next step when `ANTHROPIC_API_KEY` and `MODEL_ID` are set in `.env` or the environment, and its choice still goes through the same allow-list. A failed or refused model call stops the run with a reason. It does not guess.

## Running it

To see the demo screen, install `requirements.txt` and run `.venv/bin/python -m streamlit run app.py`. Pick a sample package or upload `.txt` files. The screen opens with what to ask the member for, then a date ruler that shows each document's valid period against the visit day, then every extracted field beside its source line. The layout and tokens are in [docs/ui-handoff.md](docs/ui-handoff.md). Uploads go to `data/uploads/` and results to `data/loanready.db`, both ignored by git. The screen's check uses the offline `RulePlanner`; when a key is set, a "Reword with the model" button can word the draft. The Open files tab lists every checked package; `scripts/seed_open_files.py` adds five samples. Use synthetic documents only.

```
.venv/bin/python scripts/make_synthetic.py   # build the 22 synthetic packages
.venv/bin/python scripts/seed_open_files.py   # add sample open files to the local database
.venv/bin/python scripts/eval.py              # end-to-end eval against the labels
.venv/bin/python -m pytest -q tests           # safety and loop tests
```

The evaluation now includes the original 10 synthetic packages plus six payoff-date regression packages. The regression gate requires every package to pass. The rules and the labels were written together, so this checks loop behavior, not real-world accuracy. Real accuracy needs MCU's checklist and documents labeled by someone else.

The added cases cover a nine-day-old letter with an expired good-through date, ambiguous and blank dates, an invalid calendar date, validity ending today, and an older letter with an explicit later validity date. Unit tests also cover missing or duplicate dates and inconsistent issue/validity dates.

Packages 17 to 19 make the loop branch: a pay stub hidden under a long letterhead (scanned, recognized, checklist rerun), a pay stub with a date the strict reader skips (stays unreadable, rep gets the line), and two pay stubs in one package (sent to the rep). The eval prints each run's path and how many distinct paths were taken.

Packages 20 to 22 pass the checklist but fail the field check: a payoff letter with another vehicle's VIN, a pay stub in another name, and a VIN one character short. The eval also requires a passing follow-up draft for every flagged package.

Verified November 5, 2026 on Python 3.9.6: 109 tests passed and 22/22 synthetic packages matched their labels with 3 distinct paths, using the offline planners. The screen was also checked in a browser. In one live run on `claude-sonnet-5-5`, the model planners for the review, field check and open-files agents finished on four packages, and the review flags matched the offline planner's. The follow-up writer's drafts on two packages passed the check. These results do not measure live-model reliability or production accuracy. The 95% field-accuracy metric still needs field-level labels, written by someone other than the person who wrote the rules.

## Safety

- Synthetic data only. Never commit real member data or API keys.
- Read-only tools first; the agent writes drafts only.
- Inputs are validated in code and tools are allow-listed.
- A person approves every correction and every message.
