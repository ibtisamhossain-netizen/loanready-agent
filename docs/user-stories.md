# LoanReady user stories

Source documents: the LoanReady Product PRD (Nov 3, 2026) and the MCU Member Service Representative JD it is based on. The JD lists accurate first-time documentation, loan pipeline follow-ups, and a 95%+ QA target as priorities.

Each story names the line it comes from. Stories with no source are labeled as assumptions and stay out of the first build.

## Story 1: Catch gaps during the visit

As an MCU Member Service Representative, I need to see which required auto-refinance documents are missing, expired, or stale while the member is at my desk, so that I can ask for them before the member leaves.

- Source: JD "accurate first-time documentation"; PRD Problem; PRD Key User Need 1.
- Demo test: correct flags on at least 9 of 10 labeled synthetic files.
- Depends on: the checklist rules (see Story 5).

## Story 2: Check extracted fields against the source

As an MSR, I need to see each extracted field (name, address, date, income, VIN, payoff) beside its source page and correct or reject it, so that the file is right the first time.

- Source: JD 95%+ QA target; PRD Journey 1 P0 requirements.
- Demo test: at least 95% exact match on labeled fields in the synthetic set.

## Story 3: See every open file's next step

As an MSR, I need a list of open applications with status, last activity, and next follow-up date, so that no file sits without a next action.

- Source: JD "loan pipeline follow-ups"; PRD Key User Need 2; PRD Journey 1 P0 (track the open application).
- Demo test: every seeded open file shows a status and a next follow-up date.

## Story 4: Draft the follow-up, rep sends it

As an MSR, I need an editable follow-up draft built from the missing items I select, so that I can send a correct request through an approved MCU channel.

- Source: PRD Journey 2 P0 (review and send follow-up); PRD Appendix (AI drafts, rep edits and sends).
- Demo test: a draft lists exactly the items the rep selected, and nothing is sent by LoanReady.

## Story 5: Maintain the checklist (assumption)

As an MCU QA reviewer, I need to maintain the checklist and freshness rules, so that reps check against current requirements.

- Source: PRD secondary users. The exact checklist and freshness rules are not confirmed with MCU operations yet (PRD Risks).
- Status: assumption. Not in the first build. Stories 1 and 2 depend on it, so the first build uses a placeholder checklist file that is clearly marked as unconfirmed.
- What would confirm it: MCU operations shares the auto-refinance document list and how old a pay stub or payoff letter can be.

## Where the agent fits

Stories 1 and 2 run as an agent loop over one uploaded package.

- Observe: the package, the checklist, and the last tool result.
- Think and act: pick one next step (classify a document, extract fields, run the checklist).
- Check: compare results to the success criteria and add them to the context.
- Stop when every required checklist item has a result, after a fixed pass limit, or if the last two passes repeat the same action. Report what it found either way.
- Tools: read-only access to synthetic files and the checklist; the only write is a draft. Inputs are validated in code, tools are allow-listed, checklist rules run in plain code (not the model), and the rep approves every correction and every message.
