import datetime


# ── Shared CSS (matches the mockup style) ──────────────────────────────────

_CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body { background: #f1f5f9; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; }
.tab-radio { display: none; }
.tab-bar { display: flex; background: #fff; border-bottom: 2px solid #e2e8f0; padding: 0 20px;
           position: sticky; top: 0; z-index: 100; box-shadow: 0 1px 3px rgba(0,0,0,.08); }
.tab-bar label { padding: 14px 20px 12px; font-size: 14px; font-weight: 500; color: #64748b;
                 cursor: pointer; border-bottom: 3px solid transparent; margin-bottom: -2px; }
#tab-biz:checked ~ .tab-shell .tab-bar label[for="tab-biz"],
#tab-sales:checked ~ .tab-shell .tab-bar label[for="tab-sales"]
  { color: #6366f1; border-bottom-color: #6366f1; font-weight: 600; }
.tab-content { display: none; }
#tab-biz:checked ~ .tab-shell #content-biz { display: block; }
#tab-sales:checked ~ .tab-shell #content-sales { display: block; }
.page-label { text-align: center; font-size: 11px; font-weight: 700; text-transform: uppercase;
              letter-spacing: 2px; color: #94a3b8; margin: 24px 0 16px; }
.email-wrap { max-width: 680px; margin: 0 auto 48px; background: #fff; border-radius: 8px;
              overflow: hidden; box-shadow: 0 4px 24px rgba(0,0,0,.10); }
.hdr { background: #0f172a; color: #f1f5f9; padding: 22px 28px; }
.hdr-brand { font-size: 18px; font-weight: 700; }
.hdr-meta { color: #94a3b8; font-size: 12px; margin-top: 5px; }
.hdr-badge { display: inline-block; background: #1e3a5f; color: #93c5fd; font-size: 10px;
             font-weight: 700; text-transform: uppercase; letter-spacing: 1px;
             padding: 2px 8px; border-radius: 3px; margin-left: 8px; }
.section { padding: 22px 28px; border-bottom: 1px solid #e2e8f0; }
.section-label { font-size: 11px; font-weight: 700; text-transform: uppercase;
                 letter-spacing: 1.2px; color: #64748b; margin-bottom: 12px; }
.kpi-grid { display: flex; gap: 10px; margin-bottom: 14px; }
.kpi { flex: 1; background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 10px 14px; }
.kpi-val { font-size: 20px; font-weight: 800; color: #0f172a; }
.kpi-lbl { font-size: 10px; color: #94a3b8; margin-top: 2px; text-transform: uppercase; }
.kpi-chg { font-size: 11px; font-weight: 600; margin-top: 4px; }
.up { color: #16a34a; } .dn { color: #dc2626; }
.bar-row { display: flex; align-items: center; gap: 8px; margin-bottom: 5px; font-size: 11px; }
.bar-lbl { width: 110px; flex-shrink: 0; color: #475569; }
.bar-track { flex: 1; height: 7px; background: #f1f5f9; border-radius: 2px; max-width: 180px; }
.bar-fill { height: 100%; border-radius: 2px; }
.bar-val { width: 60px; text-align: right; color: #334155; font-weight: 600; }
.bar-pct { font-size: 10px; color: #94a3b8; width: 44px; }
.tldr { background: #eff6ff; border-left: 4px solid #2563eb; padding: 14px 20px; }
.tldr-label { font-size: 10px; font-weight: 800; text-transform: uppercase;
              letter-spacing: 1.5px; color: #1d4ed8; margin-bottom: 5px; }
.tldr p { font-size: 13px; color: #1e3a5f; line-height: 1.7; }
.prose { font-size: 13.5px; color: #1e293b; line-height: 1.85; }
.prose strong { color: #0f172a; }
.watch-section { padding: 22px 28px; border-bottom: 1px solid #e2e8f0; background: #fffbeb; }
.watch-label { font-size: 11px; font-weight: 700; text-transform: uppercase;
               letter-spacing: 1.2px; color: #b45309; margin-bottom: 14px; }
.watch-item { display: flex; gap: 10px; align-items: flex-start; margin-bottom: 10px;
              font-size: 13px; color: #1e293b; line-height: 1.7; }
.watch-tag { background: #fef3c7; border: 1px solid #fcd34d; border-radius: 4px;
             padding: 2px 8px; font-size: 10px; font-weight: 800; color: #92400e;
             white-space: nowrap; flex-shrink: 0; margin-top: 2px; }
.monday-section { padding: 22px 28px; border-bottom: 1px solid #e2e8f0; background: #f0f9ff; }
.monday-label { font-size: 11px; font-weight: 700; text-transform: uppercase;
                letter-spacing: 1.2px; color: #0369a1; margin-bottom: 12px; }
.note { font-size: 11px; color: #64748b; margin-top: 10px; line-height: 1.6; }
table { width: 100%; border-collapse: collapse; font-size: 12px; }
th { padding: 9px 12px; text-align: right; color: #475569; font-weight: 600;
     background: #f8fafc; border-bottom: 1px solid #e2e8f0; }
th:first-child { text-align: left; }
td { padding: 9px 12px; text-align: right; border-bottom: 1px solid #f1f5f9; color: #334155; }
td:first-child { text-align: left; }
.footer { padding: 14px 28px; background: #f8fafc; text-align: center;
          font-size: 12px; color: #64748b; }
"""


# ── Formatting helpers ─────────────────────────────────────────────────────

def _currency(v: float) -> str:
    if abs(v) >= 1_000_000:
        return f"${v / 1_000_000:.2f}M"
    if abs(v) >= 1_000:
        return f"${v / 1_000:.0f}K"
    return f"${v:,.0f}"


def _pct(v: float) -> str:
    return f"{v * 100:.1f}%"


def _yoy(current: float, prior: float, positive_is_good: bool = True) -> str:
    if not prior:
        return ""
    delta = (current - prior) / prior
    arrow = "▲" if delta >= 0 else "▼"
    css   = "up" if (delta >= 0) == positive_is_good else "dn"
    return f'<span class="{css}">{arrow} {abs(delta)*100:.0f}%</span> vs {_currency(prior)} LY'


def _kpi(value: str, label: str, change: str = "", accent: str = "") -> str:
    style = f' style="border-left:3px solid {accent};"' if accent else ""
    chg   = f'<div class="kpi-chg">{change}</div>' if change else ""
    return f'<div class="kpi"{style}><div class="kpi-val">{value}</div><div class="kpi-lbl">{label}</div>{chg}</div>'


def _bar(label: str, value: str, pct: float, max_pct: float, color: str, pct_label: str = "") -> str:
    width    = int(pct / max_pct * 100) if max_pct else 0
    pct_html = f'<span class="bar-pct">{pct_label}</span>' if pct_label else ""
    return (
        f'<div class="bar-row">'
        f'<span class="bar-lbl">{label}</span>'
        f'<div class="bar-track"><div class="bar-fill" style="width:{width}%;background:{color};"></div></div>'
        f'<span class="bar-val">{value}</span>'
        f'{pct_html}'
        f'</div>'
    )


def _section(icon_label: str, content: str, extra_style: str = "") -> str:
    style = f' style="{extra_style}"' if extra_style else ""
    return (
        f'<div class="section"{style}>'
        f'<div class="section-label">{icon_label}</div>'
        f'{content}'
        f'</div>'
    )


# ── Tab 1: Total Business ──────────────────────────────────────────────────

def _render_total_business(data: dict) -> str:
    d        = data["yesterday"]
    mtd      = data["mtd"]
    eng      = data["engagements"]
    sw       = data["swatches"]
    mm       = data["merch_mix"]
    studios  = data.get("by_studio", [])

    report_date = data["report_date"]
    date_str    = report_date.strftime("%b %-d, %Y") if hasattr(report_date, "strftime") else str(report_date)

    rev_kpis = (
        '<div class="kpi-grid">'
        + _kpi(_currency(d["revenue_total"]), "Yesterday Revenue", "", "#0d9488")
        + _kpi(_currency(d["aov_blended"]), "Blended AOV")
        + _kpi(str(d["orders_total"]), "Orders")
        + '</div>'
        + '<div class="kpi-grid">'
        + _kpi(_currency(d["aov_b2c"]),    "B2C AOV")
        + _kpi(_currency(d["aov_trade"]),  "Trade AOV")
        + _kpi(_pct(d["assisted_pct"]),    "Assisted %")
        + '</div>'
    )

    total_rev = d["revenue_b2c"] + d["revenue_trade"] + d["revenue_havenly"]
    mix_bars  = ""
    for seg, rev, color in [
        ("B2C",     d["revenue_b2c"],     "#6366f1"),
        ("Trade",   d["revenue_trade"],   "#0d9488"),
        ("Havenly", d["revenue_havenly"], "#a78bfa"),
    ]:
        pct_val  = rev / total_rev if total_rev else 0
        mix_bars += _bar(seg, _currency(rev), pct_val, 1.0, color, f"{pct_val*100:.1f}%")

    rev_section = _section("📈 Revenue — Yesterday", rev_kpis + mix_bars)

    mtd_kpis = (
        '<div class="kpi-grid">'
        + _kpi(_currency(mtd["revenue_total"]), "MTD Revenue",
               _yoy(mtd["revenue_total"], mtd["revenue_total_ly"]))
        + _kpi(str(mtd["orders_total"]), "MTD Orders")
        + _kpi(_pct(mtd["repeat_pct"]),  "Repeat Business")
        + '</div>'
    )
    mtd_section = _section("📊 MTD Performance", mtd_kpis)

    pc       = mm.get("product_contribution", [])
    max_pct  = max((x["pct"] for x in pc), default=1)
    pc_bars  = "".join(
        _bar(x["name"], _pct(x["pct"]), x["pct"], max_pct, "#0d9488", _pct(x["pct"]))
        for x in pc[:6]
    )
    merch_section = _section("🛋 Product Contribution MTD", pc_bars or '<p class="note">No data.</p>')

    sw_kpis = (
        '<div class="kpi-grid">'
        + _kpi(f"{sw['mtd_orders']:,}", "Swatch Orders MTD")
        + _kpi(f"{sw['mtd_customers']:,}", "Unique Customers MTD")
        + '</div>'
    )
    sw_section = _section("🎨 Swatch Performance MTD", sw_kpis)

    eng_yoy  = _yoy(eng["yesterday"], eng["yesterday_ly"])
    eng_kpis = (
        '<div class="kpi-grid">'
        + _kpi(str(eng["yesterday"]),    "Inbound Yesterday", eng_yoy)
        + _kpi(str(eng["yesterday_ly"]), "Same Day LY")
        + '</div>'
    )
    eng_section = _section("📞 Inbound Engagements", eng_kpis)

    rows = "".join(
        f'<tr><td>{s["studio"]}</td><td>{_currency(s["revenue"])}</td><td>{s["orders"]}</td></tr>'
        for s in studios[:8]
    )
    studio_table   = (
        '<table><tr><th>Studio</th><th>Revenue MTD</th><th>Orders</th></tr>'
        + rows + '</table>'
    )
    studio_section = _section("🏬 Studio Performance MTD", studio_table)

    return f"""
<div class="page-label">Interior Define · Total Business · {date_str}</div>
<div class="email-wrap">
  <div class="hdr">
    <div class="hdr-brand">Interior Define <span class="hdr-badge">Total Business</span></div>
    <div class="hdr-meta">Daily Business Review · {date_str}</div>
  </div>
  {rev_section}
  {mtd_section}
  {merch_section}
  {sw_section}
  {eng_section}
  {studio_section}
  <div class="footer">Interior Define Daily Business Review — auto-generated</div>
</div>
"""


# ── Tab 2: Sales Team ──────────────────────────────────────────────────────

def _render_sales_team(data: dict, narrative: dict, is_monday: bool) -> str:
    deals       = data.get("deals", {})
    report_date = data["report_date"]
    date_str    = report_date.strftime("%b %-d, %Y") if hasattr(report_date, "strftime") else str(report_date)
    day_name    = report_date.strftime("%A") if hasattr(report_date, "strftime") else ""

    tldr_html = (
        f'<div class="tldr">'
        f'<div class="tldr-label">TL;DR</div>'
        f'{narrative.get("tldr", "")}'
        f'</div>'
    )

    monday_html = ""
    if is_monday:
        mtd      = data["mtd"]
        rolling  = data["engagements"]["weekly_rolling"]
        lw_eng   = rolling[-1]["count"] if rolling else "—"
        monday_html = (
            f'<div class="monday-section">'
            f'<div class="monday-label">📅 Last Week Recap</div>'
            f'<p class="prose">'
            f'Inbound engagements LW: <strong>{lw_eng}</strong>. '
            f'MTD revenue: <strong>{_currency(mtd["revenue_total"])}</strong> '
            f'({_yoy(mtd["revenue_total"], mtd["revenue_total_ly"])}).'
            f'</p>'
            f'</div>'
        )

    story_html = _section(
        f"📊 {day_name}'s Story" if day_name else "📊 Yesterday's Story",
        f'<p class="prose">{narrative.get("yesterday_story", "")}</p>'
    )

    cvr_kpis = (
        '<div class="kpi-grid">'
        + _kpi(_pct(deals.get("cvr_14day_mtd",      0)), "14-Day CVR MTD")
        + _kpi(_pct(deals.get("cvr_meaningful_mtd", 0)), "Meaningful Contact CVR")
        + _kpi(str(deals.get("inbound_yesterday",    0)), "Inbound Yesterday")
        + '</div>'
    )
    cvr_section = _section("📈 Conversion Rates MTD", cvr_kpis)

    reps      = deals.get("by_rep", [])[:10]
    rep_rows  = "".join(
        f'<tr><td>{r["rep"].split("@")[0]}</td>'
        f'<td>{r["inbound"]}</td>'
        f'<td>{r["closed_won"]}</td>'
        f'<td>{_pct(r["cvr"])}</td></tr>'
        for r in reps
    )
    rep_table   = (
        '<table><tr><th>Rep</th><th>Inbound</th><th>Won</th><th>CVR</th></tr>'
        + rep_rows + '</table>'
    ) if reps else '<p class="note">No rep data available.</p>'
    rep_section = _section("👤 Rep Performance MTD", rep_table)

    watch_items = narrative.get("watch_items", [])
    watch_html  = ""
    if watch_items:
        items = "".join(
            f'<div class="watch-item">'
            f'<span class="watch-tag">{w["tag"]}</span>'
            f'<span>{w["text"]}</span>'
            f'</div>'
            for w in watch_items
        )
        watch_html = (
            f'<div class="watch-section">'
            f'<div class="watch-label">⚠ Watch</div>'
            f'{items}'
            f'</div>'
        )

    monday_badge = "&nbsp;&nbsp;<span class='hdr-badge'>⚡ Monday Mode</span>" if is_monday else ""
    return f"""
<div class="page-label">Interior Define · Sales Team · {date_str}</div>
<div class="email-wrap">
  <div class="hdr">
    <div class="hdr-brand">Interior Define · Daily Business Review</div>
    <div class="hdr-meta">{day_name + ", " if day_name else ""}{date_str}{monday_badge}</div>
  </div>
  {tldr_html}
  {monday_html}
  {story_html}
  {cvr_section}
  {rep_section}
  {watch_html}
  <div class="footer">Interior Define Daily Business Review — auto-generated</div>
</div>
"""


# ── Main render function ───────────────────────────────────────────────────

def render(data: dict, narrative: dict, is_monday: bool = False) -> str:
    """Build the complete two-tab HTML email."""
    biz_tab   = _render_total_business(data)
    sales_tab = _render_sales_team(data, narrative, is_monday)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Interior Define — Daily Business Review</title>
<style>{_CSS}</style>
</head>
<body>
<input type="radio" name="tab" id="tab-biz" class="tab-radio" checked>
<input type="radio" name="tab" id="tab-sales" class="tab-radio">
<div class="tab-shell">
  <div class="tab-bar">
    <label for="tab-biz">📊 Total Business</label>
    <label for="tab-sales">👥 Sales Team</label>
  </div>
  <div class="tab-content" id="content-biz">{biz_tab}</div>
  <div class="tab-content" id="content-sales">{sales_tab}</div>
</div>
</body>
</html>"""
