# Handoff spec: LoanReady rep screen

## Overview

One screen for an MCU Member Service Representative with the member sitting at the desk. The rep picks a package (sample or uploaded `.txt` files), runs the check, and needs one answer fast: what to ask the member for before they leave. Everything below the answer is there so the rep can see why, and compare each value with the original.

The screen is built in Streamlit (`app.py`). Custom parts are HTML strings rendered with `st.markdown(..., unsafe_allow_html=True)`; Streamlit widgets handle input. Theme values are in `.streamlit/config.toml` and the CSS tokens at the top of `app.py`.

## Layout

Single column, left aligned, max width 1040px. Sections are separated by rules and space, not boxes.

```
LoanReady  auto refinance, document check at the desk        [Visit date]
| Demo with made-up documents only ...                   (amber left rule)

Sample package | Member's documents
[ package select                         ] [ Check package ]
-------------------------------------------------------------- 2px ink rule
Ask the member for 2 documents before they leave.          (verdict, 2rem)
  ■ A vehicle registration.
    None was in the package.
  ■ A new payoff letter from the current lender.
    This one was good through Oct 20, 2026.
  Then check 1 thing yourself
  ■ Read the pay stub date yourself.  (amber square)
-------------------------------------------------------------- 1px rule
Dates against the visit
              Sep        Oct         | Visit, Nov 5, 2026      Jan
Photo ID      ===========================================|  valid until ...
Pay stub                     =====|========|               issued ..., 30 days
Vehicle reg.  Not in the package  |
Payoff letter            ==|      |                        good through ...
-------------------------------------------------------------- 1px rule
Documents in the package   (one expander per file: fields + original text)
How LoanReady checked it (8 steps)   (expander, numbered list)
Saved on this computer as pkg05-xxxx
```

The verdict comes first because it is the only thing the rep must act on during the visit. The date ruler is the one bold element: it answers "why" for every date rule in one picture.

## Design tokens

| Token | Value | Usage |
|-------|-------|-------|
| `--paper` | #F6F7F5 | Page background, label backing on the ruler |
| `--ink` | #1E2A32 | Text, verdict rule, primary button |
| `--ink-soft` | #55636D | Secondary text, notes, field source lines |
| `--rule` | #D3D9DD | Section rules, row dividers, ticks |
| `--pass` | #2E6B5A | "Passes" status, current bars |
| `--flag` | #A8322A | Missing, expired, out of date: ask the member |
| `--review` | #8A5B12 | Needs your check: the rep reads it, and the demo note rule |
| `--visit` | #2747A0 | Visit-day line, tab underline, focus ring, button hover |
| `--name-w` | 190px (104px on phones) | Ruler name column; axis and visit line use the same value |
| `--space-xs/sm/md/lg/xl` | 4 / 8 / 16 / 28 / 48px | All spacing |
| Type | Public Sans 400/500/600/700, italic 400 | One family for everything; tabular figures for dates |
| Verdict | 2rem / 700 / 1.15 | The answer |
| Ask item | 1.2rem / 400 / 1.45 | Each thing to ask for, max 68ch |
| Section heading | 1rem / 600 | "Dates against the visit", etc. |
| Ruler label | 0.72rem | Date range under each bar |

All text colors pass WCAG AA on `--paper` (lowest is `--review` at about 5.5:1).

Status is never shown by color alone: every colored square or bar has a word beside it ("Missing", "Out of date", "Needs your check", "Passes").

## Components

| Component | Variant | Content | Notes |
|-----------|---------|---------|-------|
| Verdict | Ask | "Ask the member for N document(s) before they leave." + red-square list | One item per flagged row with status missing, expired or stale |
| Verdict | Check only | "Check N thing(s) yourself before the member leaves." + amber list | Unreadable rows and duplicate documents |
| Verdict | Ask + check | Ask list, then "Then check N thing(s) yourself" | |
| Verdict | Clear | "Nothing to ask for." + green line telling the rep to compare with originals | |
| Verdict | Did not finish | "The check did not finish." + stop reason + what to do | Shown when the agent stopped without a checklist |
| Ask item | per status | Sentence of what to ask for, then a "why" line with the real date | Wording is built in `ask_sentence()`; quotes the source line for unreadable dates |
| Date ruler row | expiry doc | Bar from the left edge to the expiry date | Photo ID, registration |
| Date ruler row | pay stub | Bar from issue date to issue + 30 days | Window length from `checklist.MAX_AGE_DAYS` |
| Date ruler row | payoff letter | Bar from statement date to good-through date | Falls back to a dot at good-through if the statement date is missing or later |
| Date ruler row | no bar | "Not in the package", "No readable date", or "Two documents of this type" | |
| Document expander | per file | Field table (field, value, source line) + the original text | Unrecognized files say "Not recognized, not counted" |
| Steps expander | | Numbered list: plain-language action, reason, result | Numbered because the steps are a real sequence |

## States and interactions

| Element | State | Behavior |
|---------|-------|----------|
| Page | First load | Prompt: "Pick a sample package or add the member's documents, then check them." No results area |
| Check package | Default / hover / focus | Ink fill, white text / `--visit` fill / 3px `--visit` outline, 2px offset |
| Check these documents | Disabled | Disabled until at least one file is added |
| Upload | Error | Red note under the button naming the problem ("only simple .txt file names are accepted: ...", "too many documents (13); the limit is 12") |
| Visit date | Changed | Next check runs against the new date. Sample tab shows a note when the date differs from the label date (Nov 4, 2026) |
| Results | After a run | Stay on screen until the next run (kept in session state) |
| Expanders | Open / closed | Streamlit default; summary arrow is the Material icon |

## Responsive behavior

| Width | Changes |
|-------|---------|
| > 700px | Layout above. Ruler labels sit under each bar, left aligned at the bar start, or right aligned at the bar end when the bar starts past 55% |
| ≤ 700px | Verdict 1.5rem, ask items 1.05rem. Ruler name column 104px. Ruler labels wrap below the bar. Month labels hidden; visit label moves to the left of the line |

## Edge cases

- **Date far in the future** (ID expiring 2029): bar runs to the right edge and the label adds ", past the right edge".
- **Date far in the past** (pay stub from August): bar is clamped to the left edge; the "why" line in the verdict still gives the real date.
- **Window**: 90 days before the visit to 60 days after. Month ticks near the visit label are hidden so labels don't overlap.
- **Two documents of one type**: no bar; the verdict names both files and the rep decides.
- **Unrecognized extra file** (flyer): listed under documents as not counted; does not affect the verdict.
- **Long file names**: wrap inside the expander summary.
- **Uploaded text with markup**: every document-derived string (file names, values, source lines, original text, step names) goes through `html.escape`. A test feeds `<script>` through the field view.

## Motion

None beyond Streamlit's expander default. Reduced-motion turns off all transitions.

## Accessibility

- Focus order follows the page: visit date, tabs, package select, Check package, then expanders.
- Status words always accompany status colors.
- Verdict is an `h2`, section titles are `h3`.
- Keyboard: every control is a native Streamlit widget, so Tab, Enter and Space work as usual. Focus ring is 3px `--visit`.
- Not done yet: the ruler is decorative HTML with text labels. Screen readers get the labels, but not the bar positions. The verdict and the documents section carry the same information in text.

## Not covered

Correcting or rejecting a field (story 2), the open-file list (story 3) and the follow-up draft (story 4) have no screen yet.
