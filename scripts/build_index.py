"""Scan reports/ for HTML files, extract date and P&L, write index.html."""

import json
import re
import statistics
from pathlib import Path

REPORTS_DIR = Path(__file__).parent.parent / "reports"
INDEX_PATH = Path(__file__).parent.parent / "index.html"

# Matches: Started: 2026-03-10 20:55:20 UTC
RE_STARTED = re.compile(r"Started:\s*(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})")
# Matches the Duration field in the header
RE_DURATION = re.compile(r"Duration:\s*([^|<&]+)")


def extract_meta(html: str) -> dict:
    """Pull start datetime, duration, and session P&L out of a report HTML."""
    started = None
    duration = None
    pnl_cents = None

    m = RE_STARTED.search(html)
    if m:
        started = m.group(1).strip()

    m = RE_DURATION.search(html)
    if m:
        duration = m.group(1).strip()

    # Prefer the Session P&L stat card (only present when session_summary.parquet existed).
    m = re.search(
        r"Session P&amp;L.*?<div class=\"value\">\s*([+\-$0-9,\.]+)\s*</div>",
        html,
        re.DOTALL,
    )
    if m:
        raw = m.group(1).replace("$", "").replace(",", "").strip()
        try:
            pnl_cents = float(raw) * 100
        except ValueError:
            pass

    # Fall back to the chart trace when no stat card is available.
    # Strip outliers (> 3 stdev from median) to avoid end-of-session resolution spikes,
    # then take the last clean value.
    if pnl_cents is None:
        idx = html.find("chart_pnl")
        if idx != -1:
            chunk = html[idx:]
            spec_match = re.search(r"var spec = (.*?);\s*Plotly\.newPlot", chunk, re.DOTALL)
            if spec_match:
                try:
                    spec = json.loads(spec_match.group(1))
                    for trace in spec.get("data", []):
                        if trace.get("name") == "Session PnL (\u00a2)":
                            y = trace.get("y", [])
                            if len(y) > 1:
                                med = statistics.median(y)
                                stdev = statistics.stdev(y)
                                clean = [v for v in y if stdev == 0 or abs(v - med) <= 3 * stdev]
                                if clean:
                                    pnl_cents = clean[-1]
                            elif y:
                                pnl_cents = y[-1]
                            break
                except (json.JSONDecodeError, KeyError, statistics.StatisticsError):
                    pass

    return {"started": started, "duration": duration, "pnl_cents": pnl_cents}


def fmt_pnl(pnl_cents) -> tuple[str, str]:
    """Return (display string, css class) for a P&L value in cents."""
    if pnl_cents is None:
        return "—", "neutral"
    dollars = pnl_cents / 100
    sign = "+" if dollars >= 0 else ""
    cls = "positive" if dollars > 0 else ("negative" if dollars < 0 else "neutral")
    return f"{sign}${dollars:,.2f}", cls


def build_index(reports: list[dict]) -> str:
    rows = ""
    for r in reports:
        pnl_str, pnl_cls = fmt_pnl(r["pnl_cents"])
        duration_cell = r["duration"] or "—"
        rows += f"""
        <tr>
          <td class="date">{r["started"] or "Unknown"}</td>
          <td class="duration">{duration_cell}</td>
          <td class="{pnl_cls} pnl">{pnl_str}</td>
          <td class="link"><a href="reports/{r['filename']}">View report &rarr;</a></td>
        </tr>"""

    count = len(reports)
    subtitle = f"{count} session{'s' if count != 1 else ''}"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Kalshi MM — Session Reports</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      background: #0f0f1a;
      color: #e0e0e0;
      font-size: 14px;
      line-height: 1.5;
    }}
    header {{
      background: linear-gradient(135deg, #1a1a3e 0%, #16213e 100%);
      padding: 24px 32px;
      border-bottom: 2px solid #2a2a5a;
    }}
    header h1 {{ font-size: 1.6rem; font-weight: 700; color: #ffffff; }}
    header p {{ color: #8888aa; margin-top: 4px; font-size: 0.85rem; }}
    .container {{ max-width: 900px; margin: 0 auto; padding: 32px; }}
    table {{
      width: 100%;
      border-collapse: collapse;
      background: #16213e;
      border: 1px solid #2a2a5a;
      border-radius: 10px;
      overflow: hidden;
    }}
    thead tr {{
      background: #1a1a3e;
      border-bottom: 2px solid #2a2a5a;
    }}
    th {{
      padding: 12px 16px;
      text-align: left;
      font-size: 0.72rem;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      color: #6677aa;
      font-weight: 600;
    }}
    td {{
      padding: 13px 16px;
      border-bottom: 1px solid #1e1e3a;
      vertical-align: middle;
    }}
    tr:last-child td {{ border-bottom: none; }}
    tr:hover td {{ background: #1c1c40; }}
    td.date {{ color: #c0c0e0; font-variant-numeric: tabular-nums; }}
    td.duration {{ color: #8888aa; }}
    td.pnl {{
      font-weight: 700;
      font-variant-numeric: tabular-nums;
      font-size: 1rem;
    }}
    td.positive {{ color: #2ecc71; }}
    td.negative {{ color: #e74c3c; }}
    td.neutral {{ color: #8888aa; }}
    td.link a {{
      color: #7788cc;
      text-decoration: none;
      font-size: 0.85rem;
    }}
    td.link a:hover {{ color: #aabbff; text-decoration: underline; }}
    .empty {{
      padding: 40px;
      text-align: center;
      color: #555577;
    }}
  </style>
</head>
<body>
  <header>
    <h1>Kalshi MM &mdash; Session Reports</h1>
    <p>{subtitle}</p>
  </header>
  <div class="container">
    <table>
      <thead>
        <tr>
          <th>Session Start (UTC)</th>
          <th>Duration</th>
          <th>Session P&amp;L</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        {'<tr><td colspan="4" class="empty">No reports yet.</td></tr>' if not reports else rows}
      </tbody>
    </table>
  </div>
</body>
</html>
"""


def duration_seconds(duration_str) -> int:
    """Convert a duration string like '10h 45m' or '2h 28m' to total seconds."""
    if not duration_str:
        return 0
    total = 0
    m = re.search(r"(\d+)h", duration_str)
    if m:
        total += int(m.group(1)) * 3600
    m = re.search(r"(\d+)m", duration_str)
    if m:
        total += int(m.group(1)) * 60
    m = re.search(r"(\d+)s", duration_str)
    if m:
        total += int(m.group(1))
    return total


def main():
    if not REPORTS_DIR.exists():
        print("No reports/ directory found, writing empty index.")
        INDEX_PATH.write_text(build_index([]))
        return

    entries = []
    for path in sorted(REPORTS_DIR.glob("*.html")):
        html = path.read_text(encoding="utf-8", errors="replace")
        meta = extract_meta(html)
        meta["filename"] = path.name
        entries.append(meta)

    # Drop entries with no known session start
    entries = [e for e in entries if e["started"]]

    # For duplicate session starts keep the most complete (longest duration)
    best: dict[str, dict] = {}
    for e in entries:
        key = e["started"]
        if key not in best or duration_seconds(e["duration"]) > duration_seconds(best[key]["duration"]):
            best[key] = e
    entries = list(best.values())

    # Sort by start datetime descending
    entries.sort(key=lambda r: r["started"], reverse=True)

    INDEX_PATH.write_text(build_index(entries), encoding="utf-8")
    print(f"Wrote index.html with {len(entries)} report(s).")


if __name__ == "__main__":
    main()
