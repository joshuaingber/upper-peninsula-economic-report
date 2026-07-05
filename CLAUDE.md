@docs/ARCHITECTURE.md

# Accessibility is a hard requirement — read before making changes

Every page this project publishes — `docs/index.html` and every embed under `docs/embeds/` — is
hosted under the NMU name and **must** conform to **WCAG 2.1 Level AA**. This is a legal requirement
(the DOJ 2024 ADA Title II rule), not a style preference, and it is the condition NMU set for
embedding the dashboard via iframe. The static build (`build.py`) is the conformance boundary.

**Before** modifying `build.py`, `data/constants.py`, `components/**`, `scripts/a11y.mjs`, or
anything under `docs/`, read **`docs/accessibility/GUIDELINES.md`** (imported below) and follow it.
**After** any change that can affect rendered output, regenerate the build and run `npm run a11y`;
all 28 pages must pass with 0 errors before you commit. Never introduce color-only meaning,
non-focusable controls, sub-threshold contrast, or a chart without an accompanying data table.

@docs/accessibility/GUIDELINES.md
