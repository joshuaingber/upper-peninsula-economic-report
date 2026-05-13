# South Florida Economic Report — Embeddable Iframes

These pages are self-contained HTML embeds intended to be dropped into the FAU website via `<iframe>`. Each embed mirrors one section of the live dashboard at https://bryanpcutsinger.github.io/south-florida-economic-report/ and is rebuilt automatically every Monday morning by a GitHub Action — no manual refresh needed on either end.

Base URL: `https://bryanpcutsinger.github.io/south-florida-economic-report/embeds/`

## Available Embeds

| Embed | Path (append to base URL) | Suggested height | Min. width |
|---|---|---:|---:|
| Regional KPI Snapshot (all 3 counties + caption) | `kpi-cards.html` | 380 px | 900 px |
| **Palm Beach** | | | |
| Employment & Salary Trends | `palm-beach/trends.html` | 600 px | 700 px |
| Workforce Composition (treemap) | `palm-beach/workforce-composition.html` | 600 px | 600 px |
| Industry Landscape (growth quadrant) | `palm-beach/industry-landscape.html` | 700 px | 600 px |
| Firm Openings & Closings | `palm-beach/firm-formation.html` | 600 px | 600 px |
| **Broward** | | | |
| Employment & Salary Trends | `broward/trends.html` | 600 px | 700 px |
| Workforce Composition (treemap) | `broward/workforce-composition.html` | 600 px | 600 px |
| Industry Landscape (growth quadrant) | `broward/industry-landscape.html` | 700 px | 600 px |
| Firm Openings & Closings | `broward/firm-formation.html` | 600 px | 600 px |
| **Miami-Dade** | | | |
| Employment & Salary Trends | `miami-dade/trends.html` | 600 px | 700 px |
| Workforce Composition (treemap) | `miami-dade/workforce-composition.html` | 600 px | 600 px |
| Industry Landscape (growth quadrant) | `miami-dade/industry-landscape.html` | 700 px | 600 px |
| Firm Openings & Closings | `miami-dade/firm-formation.html` | 600 px | 600 px |

**Heights are starting values** — each embed posts its actual rendered height to the parent page via `postMessage`, and the listener snippet below replaces the initial height attribute as soon as the embed is ready. Below the minimum widths, Plotly tick labels start to overlap; the KPI snapshot stacks its 3 county cards vertically below 768 px automatically.

## How to Embed

### 1. Paste this listener once per page

Add this script tag anywhere on the FAU page that hosts these iframes. It listens for height messages from the embeds and resizes them to fit their content:

```html
<script>
window.addEventListener('message', function(e) {
  if (e.origin !== 'https://bryanpcutsinger.github.io') return;
  if (!e.data || e.data.type !== 'sfer-resize') return;
  document.querySelectorAll('iframe.sfer-embed').forEach(function(f) {
    if (f.contentWindow === e.source) f.style.height = e.data.height + 'px';
  });
});
</script>
```

The origin check ensures only messages from our GitHub Pages domain trigger resizing. The `iframe.sfer-embed` class selector means the listener only resizes iframes you've explicitly opted in (so it won't interfere with other iframes on the page).

### 2. Paste an iframe for each embed you want

The `class="sfer-embed"` is what hooks the iframe into the resize listener above. The `height` attribute is just an initial value — it'll be replaced once the embed finishes loading.

```html
<iframe class="sfer-embed"
        src="https://bryanpcutsinger.github.io/south-florida-economic-report/embeds/kpi-cards.html"
        style="width:100%; border:0;"
        height="380"
        title="South Florida Regional Snapshot"></iframe>
```

To embed a chart, change `src` and the `title` (which screen readers read aloud):

```html
<iframe class="sfer-embed"
        src="https://bryanpcutsinger.github.io/south-florida-economic-report/embeds/palm-beach/trends.html"
        style="width:100%; border:0;"
        height="600"
        title="Palm Beach County employment and salary trends, 2014 to present"></iframe>
```

## Accessibility

Plotly renders charts to a `<canvas>` element that screen readers can't interpret meaningfully, even with an iframe `title` attribute set. To make the embeds accessible:

1. **Add an `<h2>` above each iframe** describing the chart's topic.
2. **Add a one-sentence text description** below the heading summarizing what the chart shows and its current trend. (Example: *"Palm Beach County's total employment has grown from 580K in 2014 to 670K in the latest quarter, an 18% increase over the period."*)

This gives non-visual users the headline information without depending on the chart itself.

## Update Cadence

Every Monday at 1:00 AM Eastern, a GitHub Action regenerates all 13 embed files from fresh BLS QCEW, FRED, and IRS SOI data and commits the new HTML to this repository. Within ~10 minutes, GitHub Pages serves the updated versions to any iframe pointing at these URLs — no action required on the FAU side.

GitHub Pages sends `cache-control: max-age=600`, so individual users may see a 10-minute lag after each refresh. If FAU needs to force an immediate update for any embed (e.g., for a press event), open the page in a private/incognito window.

## Troubleshooting

- **Iframe shows a scrollbar / doesn't grow:** the listener snippet above is missing or the origin check is failing. Open the browser's developer console; if you see messages like `Refused to display ...`, FAU's Content-Security-Policy is blocking the embed and IT needs to allow `https://bryanpcutsinger.github.io` in the page's `frame-src` directive.
- **Charts render at the wrong width:** the iframe is narrower than the recommended minimum. Either widen the column, or accept the overlap on small screens (the embed already stacks its multi-chart layouts vertically below 768 px).
- **All embeds blank / 404:** the GitHub Action failed its last Monday run. Check https://github.com/bryanpcutsinger/south-florida-economic-report/actions for red workflows.
