"""Jupyter display helpers for Verovio-rendered MusicXML previews."""

from __future__ import annotations

import html
import json
from pathlib import Path
from uuid import uuid4

from .rule_costs import RuleAnalysis

DEFAULT_VEROVIO_FONT = "Bravura"
DEFAULT_VEROVIO_FONT_FALLBACK = "Bravura"


def render_score_inline(
    score_path: str | Path,
    *,
    input_from: str = "xml",
    font: str = DEFAULT_VEROVIO_FONT,
    font_fallback: str = DEFAULT_VEROVIO_FONT_FALLBACK,
    scale: int = 34,
    page_width: int = 1800,
    tooltips_by_color: dict[str, str] | None = None,
) -> None:
    """Render a score inline in a Jupyter notebook using browser-side Verovio."""

    from IPython.display import HTML, Javascript, display

    path = Path(score_path)
    score_data = path.read_text(encoding="utf-8")
    target_id = f"verovio-{uuid4().hex}"
    display(HTML(f"<div id='{target_id}'><em>Rendering score...</em></div>"))
    display(
        Javascript(
            _verovio_browser_script_for_source(
                score_data,
                target_id,
                input_from=input_from,
                font=font,
                font_fallback=font_fallback,
                scale=scale,
                page_width=page_width,
                tooltips_by_color=tooltips_by_color or {},
            )
        )
    )


def export_score_preview_html(
    score_path: str | Path,
    output_path: str | Path,
    *,
    title: str = "BCFB chorale preview",
    input_from: str = "xml",
    font: str = DEFAULT_VEROVIO_FONT,
    font_fallback: str = DEFAULT_VEROVIO_FONT_FALLBACK,
    scale: int = 34,
    page_width: int = 1800,
    tooltips_by_color: dict[str, str] | None = None,
) -> Path:
    """Write a standalone HTML preview for a MusicXML or MEI score."""

    score_data = Path(score_path).read_text(encoding="utf-8")
    output = Path(output_path)
    target_id = f"verovio-{uuid4().hex}"
    browser_script = _verovio_browser_script_for_source(
        score_data,
        target_id,
        input_from=input_from,
        font=font,
        font_fallback=font_fallback,
        scale=scale,
        page_width=page_width,
        tooltips_by_color=tooltips_by_color or {},
    )
    html_text = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <style>
    body {{ font-family: Georgia, 'Times New Roman', serif; margin: 2rem auto; max-width: 1200px; color: #1f2328; }}
    h1 {{ margin-bottom: 0.35rem; }}
    p {{ line-height: 1.5; }}
    .score {{ margin-top: 1.5rem; }}
  </style>
</head>
<body>
  <h1>{html.escape(title)}</h1>
  <p>Highlighted notes mark the highest-cost events. Hover over them for rule-cost details.</p>
  <div class="score" id="{target_id}"><em>Rendering score...</em></div>
  <script>
{browser_script}
  </script>
</body>
</html>
"""
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html_text, encoding="utf-8")
    return output


def display_cost_summary(
    analysis: RuleAnalysis,
    *,
    top_events: int = 12,
    anchors_only: bool = False,
) -> None:
    """Display compact HTML tables summarizing rule-cost analysis."""

    from IPython.display import HTML, display

    totals = analysis.totals_by_rule()
    total_rows = len(analysis.rows)
    anchor_rows = len(analysis.anchor_indices)
    total_cost = sum(totals.values())
    totals_html = "".join(
        f"<tr><td>{html.escape(rule)}</td><td>{cost:.1f}</td></tr>"
        for rule, cost in sorted(totals.items(), key=lambda item: item[1], reverse=True)
    )
    high_rows_html = "".join(
        _event_row_html(row, analysis.rule_columns)
        for row in analysis.high_cost_rows(limit=top_events, anchors_only=anchors_only)
    )
    display(
        HTML(
            f"""
<style>
  .harm-summary {{ font-family: system-ui, sans-serif; max-width: 1000px; }}
  .harm-summary table {{ border-collapse: collapse; margin: 0.75rem 0 1.25rem; width: 100%; }}
  .harm-summary th, .harm-summary td {{ border-bottom: 1px solid #d0d7de; padding: 0.35rem 0.45rem; text-align: left; vertical-align: top; }}
  .harm-summary th {{ font-weight: 650; }}
  .harm-summary code {{ font-family: ui-monospace, SFMono-Regular, Consolas, monospace; }}
</style>
<div class="harm-summary">
  <p><strong>Total cost:</strong> {total_cost:.1f}
  &nbsp; <strong>Events:</strong> {total_rows}
  &nbsp; <strong>Anchors:</strong> {anchor_rows}
  &nbsp; <strong>Scope:</strong> <code>{html.escape(analysis.score_scope)}</code>
  &nbsp; <strong>Anchor threshold:</strong> {analysis.anchor_threshold:.2f}</p>

  <h3>Rule totals</h3>
  <table>
    <thead><tr><th>Rule</th><th>Total</th></tr></thead>
    <tbody>{totals_html}</tbody>
  </table>

  <h3>Highest-cost events</h3>
  <table>
    <thead><tr><th>Event</th><th>Location</th><th>Total</th><th>Nonzero costs</th></tr></thead>
    <tbody>{high_rows_html}</tbody>
  </table>
</div>
"""
        )
    )


def _event_row_html(row: dict[str, object], rule_columns: tuple[str, ...]) -> str:
    costs = [
        f"{html.escape(column)}: {float(row[column]):.1f}"
        for column in rule_columns
        if float(row[column]) != 0.0
    ]
    cost_text = "<br>".join(costs) if costs else "none"
    location = f"m. {row['measure']}, beat {row['beat']}"
    anchor = "anchor" if row["is_anchor"] == "yes" else "raw"
    return (
        "<tr>"
        f"<td>{row['index']}<br><code>{anchor}</code></td>"
        f"<td>{html.escape(location)}</td>"
        f"<td>{float(row['total_cost']):.1f}</td>"
        f"<td>{cost_text}</td>"
        "</tr>"
    )


def _verovio_browser_script_for_source(
    score_data: str,
    target_id: str,
    *,
    input_from: str = "xml",
    font: str = DEFAULT_VEROVIO_FONT,
    font_fallback: str = DEFAULT_VEROVIO_FONT_FALLBACK,
    scale: int = 34,
    page_width: int = 1800,
    tooltips_by_color: dict[str, str] | None = None,
) -> str:
    return f"""
    (async () => {{
      const target = document.getElementById({json.dumps(target_id)});
      const scoreData = {json.dumps(score_data)};
      const tooltipsByColor = {json.dumps(tooltips_by_color or {})};
      const scriptUrl = 'https://www.verovio.org/javascript/latest/verovio-toolkit-wasm.js';

      const loadScriptOnce = (src) => new Promise((resolve, reject) => {{
        const existing = Array.from(document.querySelectorAll('script')).find((element) => element.src === src);
        if (existing) {{
          if (window.verovio && window.verovio.module && window.verovio.module.calledRun) {{
            resolve();
            return;
          }}
          existing.addEventListener('load', () => resolve(), {{ once: true }});
          existing.addEventListener('error', reject, {{ once: true }});
          return;
        }}

        const script = document.createElement('script');
        script.src = src;
        script.async = true;
        script.onload = () => resolve();
        script.onerror = reject;
        document.head.appendChild(script);
      }});

      const waitForToolkit = () => new Promise((resolve, reject) => {{
        const start = Date.now();
        const tick = () => {{
          if (window.verovio && window.verovio.toolkit && window.verovio.module && window.verovio.module.calledRun) {{
            resolve();
            return;
          }}
          if (Date.now() - start > 20000) {{
            reject(new Error('Timed out loading Verovio.'));
            return;
          }}
          setTimeout(tick, 100);
        }};
        tick();
      }});

      const normalizeColor = (value) => {{
        if (!value) return null;
        const trimmed = String(value).trim().toLowerCase();
        if (/^#[0-9a-f]{{6}}$/.test(trimmed)) return trimmed;
        const rgb = trimmed.match(/^rgb\\((\\d+),\\s*(\\d+),\\s*(\\d+)\\)$/);
        if (!rgb) return null;
        return '#' + rgb.slice(1).map((part) => Number(part).toString(16).padStart(2, '0')).join('');
      }};

      const colorsForElement = (element) => {{
        const colors = [element.getAttribute('fill'), element.getAttribute('stroke')];
        const style = element.getAttribute('style') || '';
        for (const match of style.matchAll(/(?:fill|stroke):\\s*(#[0-9a-f]{{6}}|rgb\\([^)]*\\))/gi)) {{
          colors.push(match[1]);
        }}
        return colors.map(normalizeColor).filter(Boolean);
      }};

      const attachTooltips = () => {{
        if (!tooltipsByColor || Object.keys(tooltipsByColor).length === 0) return;
        const svgElements = target.querySelectorAll('svg *');
        for (const element of svgElements) {{
          const colors = colorsForElement(element);
          const matchedColor = colors.find((color) => Object.prototype.hasOwnProperty.call(tooltipsByColor, color));
          if (!matchedColor) continue;
          if (!element.querySelector(':scope > title')) {{
            const title = document.createElementNS('http://www.w3.org/2000/svg', 'title');
            title.textContent = tooltipsByColor[matchedColor];
            element.prepend(title);
          }}
          element.style.cursor = 'help';
        }}
      }};

      try {{
        await loadScriptOnce(scriptUrl);
        await waitForToolkit();

        const toolkit = new verovio.toolkit();
        toolkit.setOptions({{
          scale: {scale},
          pageWidth: {page_width},
          adjustPageHeight: true,
          breaks: 'auto',
          inputFrom: {json.dumps(input_from)},
          font: {json.dumps(font)},
          fontFallback: {json.dumps(font_fallback)},
          smuflTextFont: 'embedded'
        }});
        toolkit.loadData(scoreData);

        const pageCount = toolkit.getPageCount();
        let svgPages = '';
        for (let page = 1; page <= pageCount; page += 1) {{
          svgPages += `<div style="margin-bottom: 1.5rem;">${{toolkit.renderToSVG(page, {{}})}}</div>`;
        }}
        target.innerHTML = svgPages;
        attachTooltips();
      }} catch (error) {{
        target.innerHTML = `<pre>${{String(error)}}</pre>`;
      }}
    }})();
    """
