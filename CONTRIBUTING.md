# Contributing & Maintenance Guide

This repository powers the **Upper Peninsula Economic Report** dashboard, which is embedded on the
Northern Michigan University (NMU) Economics Department website via iframe. This guide is written for
Economics Department contributors who need to fix or update the reports after launch.

**Why this matters:** NMU embeds these reports on the condition that they stay accessible (WCAG 2.1
Level AA) and maintained. Under NMU's arrangement, the **Economics Department is responsible for
addressing accessibility issues that surface after launch.** An issue left unaddressed for a long
period can result in NMU removing the iframe embeds. Keeping the checks below green is what keeps the
reports on the NMU site.

## How the site stays up to date

You usually don't need to touch anything for routine data updates. A GitHub Action
(`.github/workflows/update-data.yml`) runs **every Monday**, pulls fresh BLS QCEW / FRED / IRS SOI
data, regenerates `docs/index.html` and every embed under `docs/embeds/`, runs the accessibility
gate, and commits the result. GitHub Pages then serves the new HTML to the NMU iframes within about
ten minutes. No manual step is required for the weekly refresh.

You only need the workflow below when you want to **change** something — fix a bug, adjust a chart,
correct text, or respond to an accessibility finding.

## Making a change (fork → edit → pull request)

The repository owner (Joshua Ingber) reviews and merges all changes. Contributors work on a fork and
open a pull request; direct pushes are not expected.

1. **Fork the repo** on GitHub: from
   `https://github.com/joshuaingber/upper-peninsula-economic-report`, click **Fork** (top right).
   This creates your own copy under your GitHub account.
2. **Clone your fork** locally and create a branch:
   ```bash
   git clone https://github.com/<your-username>/upper-peninsula-economic-report.git
   cd upper-peninsula-economic-report
   git checkout -b fix-short-description
   ```
3. **Set up the environment** (Python 3.11):
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   npm install          # for the accessibility checker
   ```
4. **Make your change.** Most content and chart logic lives in `build.py`, the `components/`
   folder, and the color palette in `data/constants.py`. See `docs/ARCHITECTURE.md` for the layout.
   **Read `docs/accessibility/GUIDELINES.md` before changing anything that affects rendered output.**
5. **Regenerate the static build and run the accessibility gate** (this is required — see below):
   ```bash
   python build.py
   npm run a11y
   ```
   `npm run a11y` must report **0 errors across all pages**. If it fails, fix the finding before
   continuing — a failing build will not be merged.
6. **Commit and push** to your fork:
   ```bash
   git add -A
   git commit -m "Fix: short description of the change"
   git push origin fix-short-description
   ```
7. **Open a pull request** from your branch against
   `joshuaingber/upper-peninsula-economic-report` `main`. Describe what you changed and why. In the
   PR, confirm that `npm run a11y` passed locally.
8. **Review & merge.** Joshua reviews the PR. On merge, the weekly Action (and the next build)
   regenerate the published `docs/` output, and the NMU embeds update automatically.

## The one hard rule: accessibility must stay green

Every page this project publishes must conform to **WCAG 2.1 Level AA**. This is a legal requirement
(the U.S. DOJ 2024 ADA Title II rule), not a style preference, and it is the condition under which
NMU hosts the embeds. Concretely, for any change:

- Run `npm run a11y` and confirm **0 errors** before opening a PR. CI runs the same check
  (`.github/workflows/accessibility.yml`) and blocks merges that regress it.
- Never introduce color-only meaning, non-focusable controls, sub-threshold contrast, or a chart
  without an accompanying data table. The full rules are in `docs/accessibility/GUIDELINES.md`.

## Reporting an issue without fixing it

If you find a problem but can't fix it yourself, open a **GitHub Issue** on the repository describing
the page, the browser, and what's wrong. Accessibility issues should be flagged clearly so they can
be prioritized — leaving one unaddressed risks the NMU embed.

## Where things live

| Area | File(s) |
|---|---|
| Static build (produces `docs/`) | `build.py` |
| Interactive app (local only) | `app.py` |
| Chart builders | `components/` |
| Colors / FIPS / labels | `data/constants.py` |
| Data fetch & cleaning | `data/fetch*.py`, `data/clean.py` |
| Accessibility rules | `docs/accessibility/GUIDELINES.md` |
| Accessibility checker | `scripts/a11y.mjs` (run via `npm run a11y`) |
| Embed usage guide | `docs/embeds/README.md` |
| Architecture reference | `docs/ARCHITECTURE.md` |
</content>
