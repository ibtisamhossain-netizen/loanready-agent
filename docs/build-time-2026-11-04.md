> Historical snapshot of the November 4 build session. Counts and setup notes here are out of date: see the README for current results. The planner now loads `.env`, and this work is on `main`.

# November 4 Build Time

Source: Pursuit, November 4, activity 08, Build time!
PRD: https://docs.google.com/document/d/13PdSSm3r90brJy7IKs01sfHN7xzYHCYl8iN7mEMqxh0/edit
Repository base: d9a7f287e2e2a3f1ce7cd31f8c381da784ba907c

The existing coach discussion prioritizes stories 1 and 2 and proposes testing a payoff letter issued nine days ago whose printed good-through date has already passed. The open question asks what happens if that date is unreadable or ambiguous.

## Implemented

- Read the good-through date with source-line evidence; retain malformed values for review.
- Use printed validity instead of the previous ten-day issue-age assumption.
- Flag missing, blank, ambiguous, invalid, or repeated validity dates as unreadable. Do not guess or fall back to issue age.
- Flag future issue dates or validity ending before issue as inconsistent.
- Keep date-only, inclusive validity as an explicit unconfirmed demo assumption.
- Add six synthetic packages and focused tests; require all evaluation cases to pass.
- Document local pytest setup and clarify that the optional model planner does not automatically load .env.

## Verification

Commands run from the repository root:

```sh
.venv/bin/python -m pytest -q tests
.venv/bin/python scripts/eval.py
git diff --check
```

Results: 28 tests passed; 16/16 synthetic packages matched their expected flags. Existing injection, tool allow-list, path validation, evidence, draft-only, and loop stop tests passed. .env, .env.local, data/real/, and .venv remain ignored.

These are offline synthetic regressions, not an independent accuracy benchmark or a live-model evaluation. MCU validation and human confirmation of source documents remain required.

## Proposed coach reply — awaiting user approval

I'd flag it as unreadable and require the rep to check the source. I wouldn't guess the date or fall back to the ten-day rule, because that could pass an invalid payoff quote. I implemented that locally: missing, blank, ambiguous, invalid, or duplicate good-through dates need review. The original source line stays visible. The nine-day-old letter with an expired good-through date is now stale. All 28 tests and 16 synthetic packages pass. Treating the good-through day as inclusive is still an unconfirmed demo assumption for MCU to validate.

## Delivery status

Prepared on local branch codex/payoff-validity. No push, deployment, or new Pursuit coach reply has been made in this session. The browser remains on the open Build Time question for review.
