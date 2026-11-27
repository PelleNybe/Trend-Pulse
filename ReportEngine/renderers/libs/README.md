# Bundled Third-Party Frontend Libraries (`ReportEngine/renderers/libs/`)

This directory stores local copies of browser JavaScript libraries used by rendered HTML reports so generated reports remain self-contained and work offline without external CDN access.

## Included Libraries

1. **chart.js** (v4.5.1) — Chart rendering library
   - Source: https://cdn.jsdelivr.net/npm/chart.js
2. **chartjs-chart-sankey.js** (v0.12.0) — Sankey diagram plugin for Chart.js
   - Source: https://unpkg.com/chartjs-chart-sankey@0.12.0/dist/chartjs-chart-sankey.min.js
3. **html2canvas.min.js** (v1.4.1) — HTML-to-Canvas capture utility
   - Source: https://cdnjs.cloudflare.com/ajax/libs/html2canvas/1.4.1/html2canvas.min.js
4. **jspdf.umd.min.js** (v2.5.1) — Client-side PDF generation
   - Source: https://cdnjs.cloudflare.com/ajax/libs/jspdf/2.5.1/jspdf.umd.min.js
5. **mathjax.js** (v3.2.2) — Mathematical formula rendering
   - Source: https://cdn.jsdelivr.net/npm/mathjax@3.2.2/es5/tex-mml-chtml.js
6. **wordcloud2.min.js** — Canvas/HTML word-cloud renderer

## Usage in `html_renderer.py`

During HTML report generation, `html_renderer.py` embeds these local assets directly into standalone reports:

- Full offline support without external network access
- Fast, predictable loading without CDN latency or outages
- Consistent library versions across exported reports
- Portable single-file HTML distribution

If an expected library file is missing locally, the renderer logs a warning. Total bundled size is kept compact so offline portability outweighs the slight increase in standalone HTML size.
