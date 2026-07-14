# Upper Peninsula Economic Report — Embeddable Iframes

*Canonical embedding guide. Linked from the [root README](../../README.md).*

These pages are self-contained HTML embeds intended to be dropped into the Northern Michigan
University (NMU) website via `<iframe>`. Each embed mirrors one section of the live dashboard at
https://joshuaingber.github.io/upper-peninsula-economic-report/ and is rebuilt automatically every
Monday morning by a GitHub Action — no manual refresh needed on either end.

Base URL: `https://joshuaingber.github.io/upper-peninsula-economic-report/embeds/`

> **NMU hosting note.** The NMU Drupal iframe card whitelists sources that begin with the base URL
> above. Every embed below lives under that path, so it will embed; the full dashboard
> (`index.html`) lives at the site root, *not* under `/embeds/`, so it cannot be embedded as a
> single frame — rebuild the page from the individual embeds below.

## Available Embeds

There are 27 embeds: 2 region-wide overviews, plus a KPI snapshot and 4 chart sections for each of
the five largest UP county economies (Chippewa, Delta, Dickinson, Houghton, Marquette).

| Embed | Path (append to base URL) | Suggested height | Min. width |
|---|---|---:|---:|
| **Region overview** | | | |
| Upper Peninsula county map (choropleth) | `up-map.html` | 700 px | 600 px |
| Largest county economies (grouped bar) | `up-top-counties.html` | 600 px | 700 px |
| **County KPI snapshots** | | | |
| Chippewa KPI Snapshot | `kpi-chippewa.html` | 320 px | 360 px |
| Delta KPI Snapshot | `kpi-delta.html` | 320 px | 360 px |
| Dickinson KPI Snapshot | `kpi-dickinson.html` | 320 px | 360 px |
| Houghton KPI Snapshot | `kpi-houghton.html` | 320 px | 360 px |
| Marquette KPI Snapshot | `kpi-marquette.html` | 320 px | 360 px |

Each detail county has the same four chart sections. Replace `<county>` with one of `chippewa`,
`delta`, `dickinson`, `houghton`, `marquette`:

| Section | Path (append to base URL) | Suggested height | Min. width |
|---|---|---:|---:|
| Employment & Salary Trends | `<county>/trends.html` | 600 px | 700 px |
| Workforce Composition (treemap) | `<county>/workforce-composition.html` | 600 px | 600 px |
| Industry Landscape (growth quadrant) | `<county>/industry-landscape.html` | 700 px | 600 px |
| Firm Openings & Closings | `<county>/firm-formation.html` | 600 px | 600 px |

**Heights are starting values** — each embed posts its actual rendered height to the parent page via
`postMessage`, and the listener snippet below replaces the initial height attribute as soon as the
embed is ready. Below the minimum widths, Plotly tick labels start to overlap.

## How to Embed

### 1. Paste this listener once per page

Add this script tag anywhere on the host page. It listens for height messages from the embeds and
resizes them to fit their content:

```html
<script>
window.addEventListener('message', function(e) {
  if (e.origin !== 'https://joshuaingber.github.io') return;
  if (!e.data || e.data.type !== 'uper-resize') return;
  document.querySelectorAll('iframe.uper-embed').forEach(function(f) {
    if (f.contentWindow === e.source) f.style.height = e.data.height + 'px';
  });
});
</script>
```

The origin check ensures only messages from our GitHub Pages domain trigger resizing. The
`iframe.uper-embed` class selector means the listener only resizes iframes you've explicitly opted
in (so it won't interfere with other iframes on the page).

> In NMU Drupal, the iframe card may manage its own markup, so you might not be able to add this
> script. That is fine — set an explicit height on each card and the embeds still render; they just
> won't auto-resize. Use the suggested heights above as a starting point.

### 2. Paste an iframe for each embed you want

The `class="uper-embed"` is what hooks the iframe into the resize listener above. The `height`
attribute is just an initial value — it'll be replaced once the embed finishes loading.

```html
<iframe class="uper-embed"
        src="https://joshuaingber.github.io/upper-peninsula-economic-report/embeds/up-map.html"
        style="width:100%; border:0;"
        height="700"
        title="Upper Peninsula county map, shaded by year-over-year employment growth"></iframe>
```

To embed a chart, change `src` and the `title` (which screen readers read aloud):

```html
<iframe class="uper-embed"
        src="https://joshuaingber.github.io/upper-peninsula-economic-report/embeds/marquette/trends.html"
        style="width:100%; border:0;"
        height="600"
        title="Marquette County employment and salary trends"></iframe>
```

## Accessibility

Every embed already ships an accessible representation of its data — a screen-reader heading, a
concise chart summary, and a full data table below each chart (WCAG 2.1 AA; see
`docs/accessibility/GUIDELINES.md`). When placing an embed on the host page, still:

1. **Add a heading above each iframe** describing the chart's topic, in the host page's heading
   hierarchy.
2. Set a descriptive iframe `title` (examples above).

This gives non-visual users the headline information in the host page's own structure.

## Update Cadence

Every Monday at 1:00 AM Eastern, a GitHub Action regenerates all embed files from fresh BLS QCEW,
FRED, and IRS SOI data and commits the new HTML to this repository. Within ~10 minutes, GitHub Pages
serves the updated versions to any iframe pointing at these URLs — no action required on the NMU
side.

GitHub Pages sends `cache-control: max-age=600`, so individual users may see a 10-minute lag after
each refresh. To force an immediate update for any embed, open the page in a private/incognito
window.

## Troubleshooting

- **Iframe shows a scrollbar / doesn't grow:** the listener snippet above is missing or the origin
  check is failing (or the Drupal card sets a fixed height by design). Open the browser's developer
  console; if you see messages like `Refused to display ...`, the host page's Content-Security-Policy
  is blocking the embed and NMU IT needs to allow `https://joshuaingber.github.io` in the page's
  `frame-src` directive.
- **Charts render at the wrong width:** the iframe is narrower than the recommended minimum. Widen
  the column, or accept the overlap on small screens.
- **All embeds blank / 404:** the GitHub Action failed its last Monday run. Check
  https://github.com/joshuaingber/upper-peninsula-economic-report/actions for red workflows.

## Contact

If an embed breaks or you need a chart added, open an issue or pull request on the repository (see
[`CONTRIBUTING.md`](../../CONTRIBUTING.md)), or contact the repository owner, Joshua Ingber.
</content>
</invoke>
