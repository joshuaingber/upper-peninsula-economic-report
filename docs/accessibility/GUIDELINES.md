# Accessibility Guidelines — Upper Peninsula Regional Economic Report

**Binding standard: WCAG 2.1 Level AA.** Every page published under the NMU name — the standalone
dashboard (`docs/index.html`) and every iframe embed under `docs/embeds/` — must conform to WCAG
2.1 Level A **and** Level AA. Level AAA is not required.

This is not a style preference. The U.S. Department of Justice's 2024 ADA Title II final rule
adopts WCAG 2.1 AA as the technical standard for web content provided by state and local government
entities, which includes public universities. The compliance deadline for large public entities
(state universities are sized by their state's population, not enrollment) was extended to
**April 26, 2027** by the April 2026 interim final rule. "Provide a link with a disclaimer" and
"post static images" do not satisfy the rule for interactive data content; an accessible
representation of the data itself is required.

### Sources
- WCAG 2.1 (normative standard) — https://www.w3.org/TR/WCAG21/
- WCAG in Plain English — https://aaardvarkaccessibility.com/wcag-plain-english/
- Making Graphs and Charts More Accessible — https://informationaccessgroup.com/making-graphs-and-charts-more-accessible/
- Regulation overview (Educause) — https://er.educause.edu/articles/2024/6/web-and-mobile-app-accessibility-regulations
- DOJ fact sheet — https://www.ada.gov/resources/2024-03-08-web-rule/

---

## Applicable success criteria and how this project meets them

Media criteria (WCAG 1.2.x, audio/video) are not applicable — the site has no audio or video.

### Perceivable

- **1.1.1 Non-text Content (A)** — Every chart carries a text alternative: a concise `aria-label`
  on the chart container (`role="img"`) and a full, machine-readable **data table** below the chart
  holding the numbers that build it.
- **1.3.1 Info and Relationships (A)** — Structure is programmatic: headings nest by one level,
  each chart is a `<figure>`/`<figcaption>`, and every data table uses `<caption>`, `<thead>`, and
  `<th scope="col">`/`<th scope="row">`.
- **1.4.1 Use of Color (A)** — No meaning is carried by color alone. KPI deltas show a ▲/▼ glyph
  and a signed value and an `aria-label` word ("increased"/"decreased"); firm-formation additions
  and losses read from sign and above/below-zero position, not just blue vs. red; links are
  underlined, not color-only.
- **1.4.3 Contrast (Minimum) (AA)** — Body/label text ≥ **4.5:1**; large text (≥ 24px, or ≥ 19px
  bold) ≥ **3:1**. Muted captions use `#595959` (~7:1). Links use NMU Green `#095339` (~9.5:1).
  Bright NMU Gold `#FFC425` (~1.5:1 on white) is never used for text or thin data marks — only for
  decorative fills.
- **1.4.4 Resize Text (AA)** — Type is sized in rem/em; the layout is usable at 200% zoom with no
  loss of content.
- **1.4.10 Reflow (AA)** — Charts render at container width (`responsive: true`), so there is no
  horizontal scrolling at 320 CSS px. Wide data tables may scroll horizontally — permitted, as data
  tables are an explicit reflow exception.
- **1.4.11 Non-text Contrast (AA)** — Structural UI borders, focus rings, and data-bearing chart
  marks (lines, bars, bubbles) meet ≥ 3:1 against adjacent color. Gold and sand chart series are
  darkened (`#B8860B`, `#9C7A3C`) to clear 3:1; treemap tiles use a dark palette so white labels
  clear 4.5:1.

### Operable

- **2.1.1 Keyboard (A)** — All functionality is keyboard-operable. Tabs are native `<button>`s; the
  treemap year selector uses real HTML `<button>`s (not Plotly's non-focusable SVG menu). Hover-only
  Plotly tooltips are acceptable because the same values live in the data table.
- **2.1.2 No Keyboard Trap (A)** — Focus can always move away from any component.
- **2.4.2 Page Titled (A)** — Every page has a unique, descriptive `<title>`.
- **2.4.3 Focus Order (A)** — DOM order follows reading order.
- **2.4.6 Headings and Labels (AA)** — Headings and control labels are descriptive; each embed has
  exactly one `<h1>` (visually hidden where the design has no visible top heading) and no skipped
  levels.
- **2.4.7 Focus Visible (AA)** — Every focusable element shows a visible focus indicator
  (`:focus-visible` outline, ≥ 3:1).

### Understandable

- **3.1.1 Language of Page (A)** — Every document declares `lang="en"`.

### Robust

- **4.1.2 Name, Role, Value (A)** — Custom controls expose name, role, and state: the county
  selector is a `role="group"` of native `<button>`s, each carrying `aria-pressed` for its
  selected state and `aria-controls` pointing at its panel (a plain `<div class="tab-content">`);
  the treemap year buttons likewise use `aria-pressed`; each chart container uses `role="img"` +
  `aria-label`. (This is a native-button group, not an ARIA `role="tab"`/`tabpanel` widget — the
  static build renders every county inline, so there is no single-selection tablist to model; the
  buttons stay fully operable and labeled without adopting tab semantics.)

---

## Chart rules (from the InformationAccessGroup guide)

1. **Data table below every chart** — the underlying data in a properly structured table; split
   multi-series data into clean columns, no merged cells.
2. **Text summary** of the key trend near each chart.
3. **More than one visual cue** — pair color with label, sign, position, or shape; every chart must
   still read in grayscale.
4. **Contrast** — 3:1 for graphical elements and large text, 4.5:1 for regular text.
5. **Keyboard access** for any interactive chart control.

---

## How compliance is kept (and why it stays automated)

Every fix lives in the static build (`build.py`) and the palette (`data/constants.py`) — the same
code the weekly GitHub Action runs after pulling fresh BLS QCEW / FRED / IRS SOI data. Each data
table is generated from the identical DataFrame that feeds its chart, so chart and table regenerate
together from one weekly data pull and cannot drift. **No human maintenance is required**, and no
step of the data-fetch pipeline changed. The build is the conformance boundary: CI runs an automated
accessibility check (axe / pa11y) over `docs/` and fails the build on violations, so a future data
refresh cannot silently regress accessibility.
