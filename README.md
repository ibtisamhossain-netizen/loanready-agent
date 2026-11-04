# loanready-agent

LoanReady is a staff-facing tool for Municipal Credit Union Member Service Representatives. A rep uploads the documents for an auto-refinance application, and LoanReady checks them against a checklist, flags missing, expired, or stale items beside the source document, and keeps a simple list of open files and follow-ups. The rep verifies every result and sends every message.

Pursuit L2 Cycle 4 build by Ibtisam Hossain (build) and Priscilla Batroni (research).

## Status

Week 7: PRD done, user stories written, repo set up. First build underway.

## User stories

1. As an MCU Member Service Representative, I need to see which required auto-refinance documents are missing, expired, or stale while the member is at my desk, so that I can ask for them before the member leaves.
2. As an MSR, I need to see each extracted field beside its source page and correct or reject it, so that the file is right the first time.
3. As an MSR, I need a list of open applications with status, last activity, and next follow-up date, so that no file sits without a next action.
4. As an MSR, I need an editable follow-up draft built from the missing items I select, so that I can send a correct request through an approved MCU channel.
5. (Assumption) As an MCU QA reviewer, I need to maintain the checklist and freshness rules, so that reps check against current requirements.

Sources and demo tests for each story are in [docs/user-stories.md](docs/user-stories.md).

## Setup

Copy `.env.example` to `.env` and add your own API key. `.env` is in `.gitignore` and must never be committed.

## Docs

- [User stories](docs/user-stories.md), each traced to the JD or PRD

## Scope

In scope for the MVP: one loan type (auto refinance), synthetic documents only, document classification and field extraction, plain-code checklist rules, an open-application list, and editable follow-up drafts.

Out of scope: loan decisions, credit underwriting or credit reports, real member data, automated messaging, and MCU system integrations.

## How the agent works

To be filled in as the build goes. See "Where the agent fits" in the user stories.

## Running it

To be added.

## Safety

- Synthetic data only. Never commit real member data or API keys.
- Read-only tools first; the agent writes drafts only.
- Inputs are validated in code and tools are allow-listed.
- A person approves every correction and every message.
