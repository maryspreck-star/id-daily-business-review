"""Generate today's report using Snowflake STG_DEAL for Sales Team revenue.
All data pulled via MCP queries on 2026-06-25. Report date = 2026-06-24 (Wednesday).
Run: source venv/bin/activate && python scripts/run_from_mcp.py
"""
import os, sys, datetime, asyncio, pathlib, requests, base64
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ── Formatting helpers ────────────────────────────────────────────────────────

def _c(v, full=False):
    """Currency formatter. full=True → always $X,XXX (no K/M). Default → $XK / $X.XXM for large."""
    av = abs(v)
    if full:
        return f"${v:,.0f}"
    if av >= 1_000_000: return f"${v/1_000_000:.2f}M"
    if av >= 1_000:     return f"${v/1_000:.0f}K"
    return f"${v:,.0f}"

def _cf(v):
    """Full dollar format — no K/M abbreviation, no decimals."""
    return f"${v:,.0f}"

def _pct(v): return f"{v*100:.1f}%"

def _yoy(ty, ly, good=True, fmt=None):
    if not ly: return ""
    d = (ty - ly) / ly
    arrow, css = ("▲", "up") if (d >= 0) == good else ("▼", "dn")
    if d < 0: arrow = "▼"; css = "dn" if good else "up"
    ly_str = (fmt or _c)(ly)
    return f'<span class="{css}">{arrow} {abs(d)*100:.1f}%</span> vs {ly_str} LY'

def _yoy_n(ty, ly, good=True):
    if not ly: return ""
    d = (ty - ly) / ly
    arrow = "▲" if d >= 0 else "▼"
    css = "up" if (d >= 0) == good else "dn"
    return f'<span class="{css}">{arrow} {abs(d)*100:.1f}%</span> vs {ly:,} LY'

def _kpi(val, lbl, sub="", accent=""):
    style = f' style="border-left:3px solid {accent};"' if accent else ""
    s = (f'<div class="kpi"{style}>'
         f'<div class="kpi-val">{val}</div>'
         f'<div class="kpi-lbl">{lbl}</div>')
    if sub: s += f'<div class="kpi-chg">{sub}</div>'
    return s + '</div>'

def _fcst_kpi(actual, forecast, fmt=None):
    if not forecast: return ""
    rfmt = fmt or _c
    d = (actual - forecast) / forecast
    color = "#16a34a" if d >= 0 else "#dc2626"
    css   = "up"      if d >= 0 else "dn"
    sign  = "+"       if d >= 0 else ""
    return (f'<div class="kpi" style="border-left:3px solid {color}">'
            f'<div class="kpi-val" style="font-size:14px">'
            f'<span class="{css}">{sign}{d*100:.1f}% v. {rfmt(forecast)} fcst</span>'
            f'</div><div class="kpi-lbl">Forecast</div></div>')

def _aov_box(lbl, val, yoy="", fmt=None):
    rfmt = fmt or _c
    v = f'{val}' if isinstance(val, str) else rfmt(val)
    return (f'<div class="aov-box">'
            f'<div class="aov-lbl">{lbl}</div>'
            f'<div class="aov-val">{v}</div>'
            f'<div class="aov-chg">{yoy}</div></div>')

def _seg_bar(lbl, rev, total, rev_ly, color, fmt=None):
    pct  = rev / total if total else 0
    w    = int(pct * 100)
    rfmt = fmt or _c
    return (f'<div class="bar-row">'
            f'<span class="bar-lbl">{lbl}</span>'
            f'<div class="bar-track"><div class="bar-fill" style="width:{w}%;background:{color}"></div></div>'
            f'<span class="bar-val">{_pct(pct)}</span>'
            f'<span class="bar-amt">{rfmt(rev)}</span>'
            f'<span class="bar-yoy">{_yoy(rev, rev_ly, fmt=rfmt)}</span>'
            f'</div>')

def _horiz_bar(lbl, amt, max_amt, color="#0d9488"):
    w = int(amt / max_amt * 100) if max_amt else 0
    return (f'<div class="bar-row">'
            f'<span class="bar-lbl" style="width:180px;flex-shrink:0">{lbl}</span>'
            f'<div class="bar-track" style="max-width:180px"><div class="bar-fill" style="width:{w}%;background:{color}"></div></div>'
            f'<span class="bar-val">{_c(amt)}</span>'
            f'</div>')

def _merch_bar(cat, rev, units, aur, total):
    pct = rev / total if total else 0
    w   = int(pct * 100)
    return (f'<div class="bar-row" style="margin-bottom:8px">'
            f'<span class="bar-lbl" style="width:120px">{cat}</span>'
            f'<div class="bar-track" style="max-width:160px"><div class="bar-fill" style="width:{w}%;background:#0d9488"></div></div>'
            f'<span style="font-size:11px;color:#334155;margin-left:8px">'
            f'{_c(rev)} · {units:,} units · AUR {_c(aur)} · <strong>{_pct(pct)}</strong>'
            f'</span></div>')

def _paced_bar(pct_p):
    w = min(int(pct_p * 100), 100)
    color = "#16a34a" if pct_p >= 1.10 else "#ca8a04" if pct_p >= 0.90 else "#ea580c" if pct_p >= 0.70 else "#dc2626"
    return (f'<div style="display:flex;align-items:center;gap:6px">'
            f'<div style="width:70px;height:6px;background:#f1f5f9;border-radius:2px">'
            f'<div style="width:{w}%;height:100%;background:{color};border-radius:2px"></div></div>'
            f'<span style="font-size:11px;font-weight:700;color:{color}">{_pct(pct_p)}</span>'
            f'</div>')

def _status(pct_p):
    if pct_p >= 1.10: return '<span class="badge badge-ahead">Ahead</span>'
    if pct_p >= 0.90: return '<span class="badge badge-track">On Track</span>'
    if pct_p >= 0.70: return '<span class="badge badge-behind">Behind</span>'
    return '<span class="badge badge-risk">At Risk</span>'


# ── CSS ───────────────────────────────────────────────────────────────────────

CSS = """
*{box-sizing:border-box;margin:0;padding:0}
body{background:#f1f5f9;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif}
.tab-radio{display:none}
.tab-bar{display:flex;background:#fff;border-bottom:2px solid #e2e8f0;padding:0 20px;position:sticky;top:0;z-index:100;box-shadow:0 1px 3px rgba(0,0,0,.08)}
.tab-bar label{padding:14px 20px 12px;font-size:14px;font-weight:500;color:#64748b;cursor:pointer;border-bottom:3px solid transparent;margin-bottom:-2px}
#tab-biz:checked~.tab-shell .tab-bar label[for="tab-biz"],
#tab-sales:checked~.tab-shell .tab-bar label[for="tab-sales"]{color:#6366f1;border-bottom-color:#6366f1;font-weight:600}
.tab-content{display:none}
#tab-biz:checked~.tab-shell #content-biz{display:block}
#tab-sales:checked~.tab-shell #content-sales{display:block}
.page-label{text-align:center;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:2px;color:#94a3b8;margin:24px 0 16px}
.email-wrap{max-width:680px;margin:0 auto 48px;background:#fff;border-radius:8px;overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,.10)}
.hdr{background:#0f172a;color:#f1f5f9;padding:22px 28px}
.hdr-brand{font-size:18px;font-weight:700}
.hdr-meta{color:#94a3b8;font-size:12px;margin-top:5px}
.hdr-badge{display:inline-block;background:#1e3a5f;color:#93c5fd;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:1px;padding:2px 8px;border-radius:3px;margin-left:8px}
.section{padding:20px 28px;border-bottom:1px solid #e2e8f0}
.section-label{font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:1.2px;color:#64748b;margin-bottom:12px}
.sub-label{font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.8px;color:#94a3b8;margin:14px 0 8px}
.kpi-grid{display:flex;gap:10px;margin-bottom:10px}
.kpi{flex:1;background:#f8fafc;border:1px solid #e2e8f0;border-radius:6px;padding:10px 14px}
.kpi-val{font-size:18px;font-weight:800;color:#0f172a}
.kpi-lbl{font-size:10px;color:#94a3b8;margin-top:2px;text-transform:uppercase;letter-spacing:.5px}
.kpi-chg{font-size:11px;font-weight:600;margin-top:4px}
.up{color:#16a34a}.dn{color:#dc2626}
.aov-grid{display:flex;gap:10px;margin-bottom:10px}
.aov-box{flex:1;background:#f8fafc;border:1px solid #e2e8f0;border-radius:6px;padding:10px 14px}
.aov-val{font-size:17px;font-weight:800;color:#0f172a;margin-top:2px}
.aov-lbl{font-size:10px;color:#94a3b8;text-transform:uppercase;letter-spacing:.5px}
.aov-chg{font-size:11px;font-weight:600;margin-top:3px}
.ns-pair{display:flex;gap:12px;margin-bottom:10px}
.ns-box{flex:1;background:#f8fafc;border:1px solid #e2e8f0;border-radius:6px;padding:12px 16px}
.ns-val{font-size:20px;font-weight:800;color:#0f172a}
.ns-lbl{font-size:10px;color:#94a3b8;text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px}
.ns-chg{font-size:12px;font-weight:600;margin-top:4px}
.two-col{display:flex;gap:20px}
.two-col>div{flex:1;min-width:0}
.bar-row{display:flex;align-items:center;gap:8px;margin-bottom:5px;font-size:11px}
.bar-lbl{width:110px;flex-shrink:0;color:#475569;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.bar-track{flex:1;height:7px;background:#f1f5f9;border-radius:2px;max-width:180px}
.bar-fill{height:100%;border-radius:2px}
.bar-val{width:54px;text-align:right;color:#334155;font-weight:600}
.bar-amt{font-size:11px;color:#334155;font-weight:600;width:50px}
.bar-yoy{font-size:10px;color:#64748b}
.note{font-size:11px;color:#64748b;margin-top:8px;line-height:1.6;font-style:italic}
.table-wrap{overflow-x:auto;-webkit-overflow-scrolling:touch}
table{width:100%;border-collapse:collapse;font-size:11px;min-width:500px}
th{padding:7px 8px;text-align:center;color:#475569;font-weight:600;background:#f8fafc;border-bottom:1px solid #e2e8f0;white-space:nowrap}
td{padding:6px 8px;text-align:center;border-bottom:1px solid #f1f5f9;color:#334155}
td:first-child{text-align:left;font-weight:500}
.badge{display:inline-block;padding:2px 7px;border-radius:3px;font-size:10px;font-weight:700}
.badge-ahead{background:#dcfce7;color:#16a34a}
.badge-track{background:#fef9c3;color:#a16207}
.badge-behind{background:#ffedd5;color:#ea580c}
.badge-risk{background:#fee2e2;color:#dc2626}
.footer{padding:14px 28px;background:#f8fafc;text-align:center;font-size:12px;color:#64748b}
@media print{
  .tab-radio,.tab-bar{display:none!important}
  .tab-content{display:block!important}
  #content-sales{page-break-before:always}
  body{background:#fff}
  .email-wrap{box-shadow:none;margin-bottom:0}
}
"""


# ── DATA — Total Business tab — Snowflake Jun 30, 2026 ───────────────────────

# Yesterday Jun 30, 2026 (Tuesday) — Snowflake
YD_B2C_REV, YD_B2C_ORD = 431_100.82, 138
YD_TR_REV,  YD_TR_ORD  =  75_239.93,  27
YD_HV_REV,  YD_HV_ORD  =  25_758.50,  11
YD_B2B_REV, YD_B2B_ORD =  29_120.50,  11
YD_TOT_REV, YD_TOT_ORD = 561_219.75, 176
YD_BLENDED_AOV = 3_189      # Snowflake rev/orders
YD_B2C_AOV     = 3_124      # Snowflake
YD_TR_AOV      = 2_787      # Snowflake
YD_ASSISTED_REV = 367_094.77  # Snowflake STG_DEAL MC=Yes (65.4% of rev)
YD_INBOUND, YD_INBOUND_LY     = 481, 310
MTD_INBOUND, MTD_INBOUND_LY  = 5_985, 5_276
YD_FCST_SNOWFLAKE   = 571_551
YD_REV_FOR_FCST     = 561_219.75
MTD_REV_FOR_FCST    = 7_939_485.97

# Yesterday LY Jun 30, 2025
YD_B2C_REV_LY, YD_B2C_ORD_LY = 284_694.37, 96
YD_TR_REV_LY,  YD_TR_ORD_LY  =  59_615.10, 23
YD_HV_REV_LY                  =  52_947.50
YD_TOT_REV_LY, YD_TOT_ORD_LY = 411_782.97, 132
YD_BLENDED_AOV_LY = 3_120   # Snowflake est
YD_B2C_AOV_LY     = 2_966   # Snowflake est
YD_TR_AOV_LY      = 2_592   # Snowflake est

# MTD Jun 1-30, 2026 — Snowflake
MTD_B2C_REV, MTD_B2C_ORD = 5_952_320.46, 2_249
MTD_TR_REV,  MTD_TR_ORD  = 1_373_115.67,   480
MTD_HV_REV,  MTD_HV_ORD  =   327_249.50,   125
MTD_B2B_REV, MTD_B2B_ORD =   271_423.59,    54
MTD_TOT_REV, MTD_TOT_ORD = 7_939_485.97, 2_913
MTD_BLENDED_AOV = 2_726      # Snowflake rev/orders
MTD_B2C_AOV     = 2_647      # Snowflake
MTD_TR_AOV      = 2_861      # Snowflake
MTD_REPEAT_PCT  = 857 / 2699   # 31.8% — all orders MTD
MTD_ASSISTED_REV = 4_817_017.92  # Snowflake STG_DEAL MC=Yes (60.7% of rev)
MTD_SNOWFLAKE_FCST = 8_852_645   # Snowflake ALL_COMPANY_DAILY_FORECAST Jun 1-30

# MTD LY Jun 1-30, 2025 — Snowflake
MTD_B2C_REV_LY = 4_932_622.95;  MTD_B2C_ORD_LY = 1_820
MTD_TR_REV_LY  = 1_144_170.63;  MTD_TR_ORD_LY  =   400
MTD_HV_REV_LY  =   546_070.48;  MTD_HV_ORD_LY  =   215
MTD_B2B_REV_LY =   122_939.45;  MTD_B2B_ORD_LY =    30
MTD_TOT_REV_LY  = 6_784_979.26
MTD_TOT_ORD_LY  = 2_465

MTD_BLENDED_AOV_LY = 2_753   # Snowflake est
MTD_B2C_AOV_LY     = 2_711   # Snowflake est
MTD_TR_AOV_LY      = 2_861   # Snowflake est

# Swatch — Jun 1-30 (Snowflake SWATCH_ORDERS)
SW_MTD_ORD,  SW_MTD_CUST  = 10_696, 9_073   # Snowflake Jun 1-30
SW_LY_ORD,   SW_LY_CUST   =  9_092, 7_639   # Snowflake Jun 1-30, 2025

# Merch — Snowflake Jun 1-30, 2026
MERCH = [
    {"cat": "Sectionals",    "rev": 3_447_214.0, "units": 695, "aur": 4_960},
    {"cat": "Sofas",         "rev": 1_856_695.2, "units": 670, "aur": 2_771},
    {"cat": "Chairs",        "rev":   733_342.5, "units": 519, "aur": 1_413},
    {"cat": "Beds",          "rev":   483_325.0, "units": 182, "aur": 2_656},
    {"cat": "Dining Seating","rev":   422_891.25,"units": 425, "aur":   995},
    {"cat": "Ottomans",      "rev":   294_805.0, "units": 348, "aur":   847},
    {"cat": "Benches",       "rev":   105_785.0, "units": 115, "aur":   920},
    {"cat": "Rugs",          "rev":    28_094.0, "units":  21, "aur": 1_338},
    {"cat": "Accent Tables", "rev":    25_105.0, "units":  26, "aur":   966},
]
MERCH_TOTAL = 7_432_661   # All merch categories Jun 1-30

# Studio revenue — STG_DEAL MEANINGFUL_CONTACT=TRUE Jun 1-30
TOTAL_INBOUND = 5_980
STUDIOS_ORDERS = [
    {"name":"New York",      "rev":562_148.03,"orders":201,"aov":2_797,"inbound":703,"won":201},
    {"name":"Chicago",       "rev":448_242.88,"orders":161,"aov":2_784,"inbound":563,"won":161},
    {"name":"Minneapolis",   "rev":435_193.47,"orders":151,"aov":2_882,"inbound":528,"won":151},
    {"name":"Denver",        "rev":428_043.96,"orders":139,"aov":3_080,"inbound":486,"won":139},
    {"name":"Dallas",        "rev":426_513.80,"orders":152,"aov":2_806,"inbound":532,"won":152},
    {"name":"Seattle",       "rev":384_424.77,"orders":137,"aov":2_805,"inbound":479,"won":137},
    {"name":"Boston",        "rev":366_272.81,"orders":139,"aov":2_636,"inbound":486,"won":139},
    {"name":"Washington DC", "rev":360_798.36,"orders":126,"aov":2_863,"inbound":441,"won":126},
    {"name":"Los Angeles",   "rev":329_473.29,"orders":119,"aov":2_769,"inbound":416,"won":119},
    {"name":"Charlotte",     "rev":319_679.20,"orders":105,"aov":3_044,"inbound":367,"won":105},
    {"name":"San Francisco", "rev":300_938.39,"orders":114,"aov":2_640,"inbound":399,"won":114},
    {"name":"Baltimore",     "rev":257_596.93,"orders": 87,"aov":2_961,"inbound":304,"won": 87},
    {"name":"Philadelphia",  "rev":197_692.03,"orders": 79,"aov":2_502,"inbound":276,"won": 79},
]
STUDIO_TOT_REV = sum(s["rev"] for s in STUDIOS_ORDERS)

# Studio inbound CVR MTD Jun 1-30 — STG_DEAL MC=Yes
STUDIO_MTD_CVR = [
    {"studio": "Denver",        "contacts": 448, "orders":  96, "cvr": 21.4},
    {"studio": "San Francisco", "contacts": 364, "orders":  74, "cvr": 20.3},
    {"studio": "Charlotte",     "contacts": 350, "orders":  61, "cvr": 17.4},
    {"studio": "Dallas",        "contacts": 647, "orders": 104, "cvr": 16.1},
    {"studio": "Washington DC", "contacts": 467, "orders":  73, "cvr": 15.6},
    {"studio": "New York",      "contacts": 759, "orders": 114, "cvr": 15.0},
    {"studio": "Seattle",       "contacts": 539, "orders":  81, "cvr": 15.0},
    {"studio": "Minneapolis",   "contacts": 680, "orders":  99, "cvr": 14.6},
    {"studio": "Philadelphia",  "contacts": 323, "orders":  47, "cvr": 14.6},
    {"studio": "Chicago",       "contacts": 676, "orders":  97, "cvr": 14.3},
    {"studio": "Baltimore",     "contacts": 356, "orders":  49, "cvr": 13.8},
    {"studio": "Boston",        "contacts": 510, "orders":  66, "cvr": 12.9},
    {"studio": "Los Angeles",   "contacts": 585, "orders":  71, "cvr": 12.1},
]

# % Meaningful Contact by studio — MTD Jun 1-30 and last 90 days
MC_DATA = [
    {"name":"New York",      "mtd_tot":1683, "mtd_mc":759,  "mtd_pct":45.1, "mtd_cvr":15.0, "no_cvr":2.9, "d90_pct":51.3, "d90_cvr":22.5},
    {"name":"Chicago",       "mtd_tot":1244, "mtd_mc":676,  "mtd_pct":54.3, "mtd_cvr":14.3, "no_cvr":2.6, "d90_pct":53.3, "d90_cvr":24.1},
    {"name":"Minneapolis",   "mtd_tot":1087, "mtd_mc":680,  "mtd_pct":62.6, "mtd_cvr":14.6, "no_cvr":4.2, "d90_pct":67.3, "d90_cvr":19.3},
    {"name":"Dallas",        "mtd_tot":1048, "mtd_mc":647,  "mtd_pct":61.7, "mtd_cvr":16.1, "no_cvr":3.7, "d90_pct":56.6, "d90_cvr":23.0},
    {"name":"Seattle",       "mtd_tot":1024, "mtd_mc":539,  "mtd_pct":52.6, "mtd_cvr":15.0, "no_cvr":2.5, "d90_pct":55.0, "d90_cvr":23.4},
    {"name":"Boston",        "mtd_tot":1006, "mtd_mc":510,  "mtd_pct":50.7, "mtd_cvr":12.9, "no_cvr":2.4, "d90_pct":59.2, "d90_cvr":20.8},
    {"name":"Los Angeles",   "mtd_tot": 976, "mtd_mc":585,  "mtd_pct":59.9, "mtd_cvr":12.1, "no_cvr":2.6, "d90_pct":61.7, "d90_cvr":18.5},
    {"name":"Washington DC", "mtd_tot": 915, "mtd_mc":467,  "mtd_pct":51.0, "mtd_cvr":15.6, "no_cvr":4.2, "d90_pct":49.3, "d90_cvr":26.4},
    {"name":"Denver",        "mtd_tot": 876, "mtd_mc":448,  "mtd_pct":51.1, "mtd_cvr":21.4, "no_cvr":2.3, "d90_pct":50.6, "d90_cvr":27.5},
    {"name":"Charlotte",     "mtd_tot": 848, "mtd_mc":350,  "mtd_pct":41.3, "mtd_cvr":17.4, "no_cvr":2.4, "d90_pct":41.7, "d90_cvr":27.5},
    {"name":"San Francisco", "mtd_tot": 744, "mtd_mc":364,  "mtd_pct":48.9, "mtd_cvr":20.3, "no_cvr":2.4, "d90_pct":47.9, "d90_cvr":24.6},
    {"name":"Philadelphia",  "mtd_tot": 665, "mtd_mc":323,  "mtd_pct":48.6, "mtd_cvr":14.6, "no_cvr":2.3, "d90_pct":52.4, "d90_cvr":20.8},
    {"name":"Baltimore",     "mtd_tot": 606, "mtd_mc":356,  "mtd_pct":58.7, "mtd_cvr":13.8, "no_cvr":1.2, "d90_pct":71.5, "d90_cvr":18.6},
]

# Deal CVR — MTD Jun 1-30 and 90D
MTD_CVR = {
    "Denver":        0.2140, "San Francisco": 0.2030, "Charlotte":    0.1740,
    "Dallas":        0.1610, "Washington DC": 0.1560, "New York":     0.1500,
    "Seattle":       0.1500, "Minneapolis":   0.1460, "Philadelphia": 0.1460,
    "Chicago":       0.1430, "Baltimore":     0.1380, "Boston":       0.1290,
    "Los Angeles":   0.1210,
}
NINETY_DAY_CVR = {
    "Denver":        0.2750, "Charlotte":     0.2750, "Washington DC": 0.2640,
    "San Francisco": 0.2460, "Chicago":       0.2410, "Seattle":       0.2340,
    "Dallas":        0.2300, "New York":      0.2250, "Boston":        0.2080,
    "Philadelphia":  0.2080, "Baltimore":     0.1860, "Minneapolis":   0.1930,
    "Los Angeles":   0.1850,
}

# ── Snowflake STG_DEAL — Sales Team tab ──────────────────────────────────────

# Yesterday (Jun 30, 2026) by studio — STG_DEAL MC=Yes, CLOSE_DATE
YD_BY_STUDIO = [
    {"name": "Minneapolis",   "rev": 85_151.93},
    {"name": "Denver",        "rev": 50_143.34},
    {"name": "San Francisco", "rev": 42_292.00},
    {"name": "Chicago",       "rev": 41_600.00},
    {"name": "Dallas",        "rev": 28_230.00},
    {"name": "New York",      "rev": 26_459.25},
    {"name": "Charlotte",     "rev": 23_008.75},
    {"name": "Philadelphia",  "rev": 15_800.00},
    {"name": "Los Angeles",   "rev": 13_630.75},
    {"name": "Baltimore",     "rev": 11_667.50},
    {"name": "Boston",        "rev": 10_417.25},
    {"name": "Washington DC", "rev":  9_423.00},
    {"name": "Seattle",       "rev":  9_271.00},
]
YD_HS_TOTAL    = 367_094.77
YD_HS_LY_TOTAL = 209_380.90  # Jun 30 2025

# Yesterday top reps — STG_DEAL MC=Yes CLOSE_DATE Jun 30
YD_TOP_REPS = [
    {"name": "Angela Sunder",    "studio": "Minneapolis",   "rev": 31_460.19},
    {"name": "Brittany Herrera", "studio": "Denver",        "rev": 28_232.00},
    {"name": "Rachel Kivo",      "studio": "San Francisco", "rev": 27_065.00},
    {"name": "Zoe Finkelstein",  "studio": "Minneapolis",   "rev": 26_820.50},
    {"name": "Brandi Davis",     "studio": "Chicago",       "rev": 25_531.00},
]

# MTD (Jun 1-30) by studio — STG_DEAL MC=Yes, CLOSE_DATE
MTD_BY_STUDIO = [
    {"name": "New York",      "rev": 562_148.03},
    {"name": "Chicago",       "rev": 448_242.88},
    {"name": "Minneapolis",   "rev": 435_193.47},
    {"name": "Denver",        "rev": 428_043.96},
    {"name": "Dallas",        "rev": 426_513.80},
    {"name": "Seattle",       "rev": 384_424.77},
    {"name": "Boston",        "rev": 366_272.81},
    {"name": "Washington DC", "rev": 360_798.36},
    {"name": "Los Angeles",   "rev": 329_473.29},
    {"name": "Charlotte",     "rev": 319_679.20},
    {"name": "San Francisco", "rev": 300_938.39},
    {"name": "Baltimore",     "rev": 257_596.93},
    {"name": "Philadelphia",  "rev": 197_692.03},
]
MTD_HS_TOTAL = 4_817_017.92  # STG_DEAL MC=Yes Closed Won Jun 1-30

# MTD LY (Jun 1-30, 2025) — IS_CONVERTED=TRUE
MTD_LY_BY_STUDIO = {
    "New York":      715_179.41, "Seattle":        447_687.59,
    "Boston":        433_319.47, "Minneapolis":    423_171.13,
    "Charlotte":     414_214.54, "Denver":         390_455.11,
    "Chicago":       329_745.90, "Washington DC":  317_544.50,
    "Dallas":        316_714.82, "Philadelphia":   284_627.38,
    "Los Angeles":   198_721.19, "San Francisco":  196_628.87,
    "Baltimore":     116_634.16,
}
MTD_HS_LY_TOTAL = 4_584_644.07  # IS_CONVERTED=TRUE Jun 1-30 2025

# MTD all reps (Jun 1-30) — STG_DEAL MC=Yes + Closed Won, CLOSE_DATE
MTD_ALL_REPS = {
    "anastasia.seminchenko": ("Anastasia Seminchenko",  "New York",       230_660.73),
    "vaughan.hazeldine":     ("Vaughan Hazeldine",      "Charlotte",      217_163.99),
    "jasmyne.boles":         ("Jasmyne Boles",          "Dallas",         216_844.32),
    "rachel.kivo":           ("Rachel Kivo",            "San Francisco",  167_781.48),
    "sydney.stetzel":        ("Sydney Stetzel",         "Denver",         158_806.15),
    "brittany.herrera":      ("Brittany Herrera",       "Denver",         157_697.58),
    "kaylee.krostag":        ("Kaylee Krostag",         "Chicago",        153_264.10),
    "sean.steele":           ("Sean Steele",            "Chicago",        137_387.54),
    "shawn.neifert":         ("Shawn Neifert",          "Washington DC",  132_992.34),
    "angela.sunder":         ("Angela Sunder",          "Minneapolis",    127_102.10),
    "sameera.tanveer":       ("Sameera Tanveer",        "Washington DC",  121_111.12),
    "brynn.cohune":          ("Brynn Cohune",           "Boston",         116_913.44),
    "kai.davies":            ("Kai Davies",             "Seattle",        116_413.42),
    "luz.rivera":            ("Lucy Rivera",            "Minneapolis",    116_328.21),
    "zoe.finkelstein":       ("Zoe Finkelstein",        "Minneapolis",    113_725.70),
    "mouny.alfraik":         ("Mouny Alfraik",          "New York",       112_206.35),
    "robyn.yannoukos":       ("Robyn Yann",             "Denver",         111_540.23),
    "victoria.correa":       ("Victoria Correa",        "Dallas",         107_771.99),
    "maico.vergara":         ("Maico Vergara",          "Washington DC",  106_694.90),
    "nikolaus.pollutra":     ("Nikolaus Pollutra",      "Baltimore",      105_709.69),
    "sarah.dreier":          ("Sarah Dreier",           "Los Angeles",    104_596.29),
    "julie.alfonso":         ("Jules Alfonso",          "Charlotte",      101_762.71),
    "david.mckeever":        ("David McKeever",         "Los Angeles",     92_601.96),
    "eric.sorensen":         ("Eric Sorensen",          "Boston",          90_454.59),
    "kristen.rosario":       ("Kristen Rosario",        "Chicago",         87_609.75),
    "abby.keane":            ("Abby Keane",             "Boston",          85_940.54),
    "alejandra.jimenez":     ("Alejandra Jimenez",      "Seattle",         83_307.42),
    "ashanti.gillespie":     ("Ashanti Gillespie",      "Baltimore",       77_482.50),
    "jose.macario":          ("Jose Marcario",          "Minneapolis",     76_938.71),
    "emily.nunn":            ("Emily Nunn",             "Dallas",          73_915.00),
    "olga.pushina":          ("Olga Pushina",           "Baltimore",       73_065.99),
    "heaven.chartier":       ("Heaven Chartier",        "Boston",          72_964.24),
    "kagen.haberstick":      ("Kagen Haberstick",       "Philadelphia",    71_864.00),
    "richard.boone":         ("Richard Boone",          "Los Angeles",     70_696.59),
    "brandi.davis":          ("Brandi Davis",           "Chicago",         69_981.49),
    "lindsay.reyna":         ("Lindsay Reyna",          "Seattle",         63_510.10),
    "ibtesam.chowdhury":     ("Ibtesam Chowdhury",      "New York",        62_116.66),
    "rachel.roth":           ("Rachel Roth",            "Seattle",         61_893.99),
    "lauren.shull":          ("Lauren Shull",           "New York",        61_619.00),
    "nick.pagdilao":         ("Nick Pagdilao",          "Los Angeles",     61_578.45),
    "laurel.clark":          ("Laurel Clark",           "Philadelphia",    60_908.25),
    "amira.seale":           ("Amira Seale",            "San Francisco",   59_822.62),
    "laura.tulloch":         ("Laura Tulloch",          "Seattle",         59_299.84),
    "jenee.satterwhite":     ("Jenee Satterwhite",      "Philadelphia",    57_893.99),
    "robert.perez":          ("Robert Perez",           "New York",        56_898.79),
    "mary.langridge":        ("Mary Langridge",         "San Francisco",   54_308.04),
    "jamie.williams":        ("Jamie Williams",         "New York",        38_646.50),
    "christian.villarreal":  ("Christian Villarreal",   "Dallas",          25_587.24),
    "bran.randol":           ("Bran Randol",            "San Francisco",   19_026.25),
    "matt.schork":           ("Matt Schork",            "Philadelphia",     7_025.79),
    "karl.fish":             ("Karl Fish",              "Dallas",           2_395.25),
    "tony.contreras":        ("Tony Contreras",         "Baltimore",        1_338.75),
    "elise.goplen":          ("Elise Goplen",           "Minneapolis",      1_098.75),
    "katherine.parnell":     ("Katherine Parnell",      "Charlotte",          752.50),
    "elisa.jones":           ("Elisa Jones",            "Washington DC",        0.00),
}

MTD_TOP_REPS = [
    {"name": n, "studio": s, "rev": r}
    for _, (n, s, r) in sorted(MTD_ALL_REPS.items(), key=lambda x: -x[1][2])[:5]
]

# ── Forecast & goals ──────────────────────────────────────────────────────────

DAILY_FCST = {
    "2026-06-01": 195_196, "2026-06-02": 414_750, "2026-06-03":  75_161,
    "2026-06-04":  94_105, "2026-06-05": 184_945, "2026-06-06": 120_363,
    "2026-06-07": 158_663, "2026-06-08": 237_443, "2026-06-09": 117_637,
    "2026-06-10": 102_265, "2026-06-11":  69_967, "2026-06-12":  83_105,
    "2026-06-13":  96_411, "2026-06-14":  62_254, "2026-06-15": 115_367,
    "2026-06-16": 103_172, "2026-06-17": 134_595, "2026-06-18": 191_604,
    "2026-06-19": 218_145, "2026-06-20": 160_872, "2026-06-21": 169_165,
    "2026-06-22": 185_238, "2026-06-23": 177_020, "2026-06-24": 218_734,
    "2026-06-25": 215_202, "2026-06-26": 204_393, "2026-06-27": 261_323,
    "2026-06-28": 195_489, "2026-06-29": 288_973, "2026-06-30": 325_471,
}
FULL_MO_FCST   = 5_177_028
MTD_SALES_FCST = sum(v for k,v in DAILY_FCST.items() if k <= "2026-06-30")  # $5,177,028 — ID RETAIL DAILY SALES_MC
YD_SALES_FCST  = DAILY_FCST["2026-06-30"]  # $325,471
PACING_PCT     = MTD_SALES_FCST / FULL_MO_FCST  # 100.00%

STUDIO_GOALS = {
    "Baltimore":     264_000, "Boston":        476_000, "Charlotte":     337_000,
    "Chicago":       533_000, "Dallas":        378_000, "Denver":        352_000,
    "Los Angeles":   435_000, "Minneapolis":   404_000, "New York":      704_000,
    "Philadelphia":  259_000, "San Francisco": 290_000, "Seattle":       425_000,
    "Washington DC": 331_000,
}

# Rep goals: email_prefix → (display_name, studio, goal)
REP_GOALS = {
    "ashanti.gillespie":    ("Ashanti Gillespie",    "Baltimore",      88_000),
    "nikolaus.pollutra":    ("Nikolaus Pollutra",    "Baltimore",      88_000),
    "olga.pushina":         ("Olga Pushina",         "Baltimore",      88_000),
    "abby.keane":           ("Abby Keane",           "Boston",        113_000),
    "brynn.cohune":         ("Brynn Cohune",         "Boston",        113_000),
    "eric.sorensen":        ("Eric Sorensen",        "Boston",        125_000),
    "heaven.chartier":      ("Heaven Chartier",      "Boston",        125_000),
    "julie.alfonso":        ("Jules Alfonso",        "Charlotte",     160_000),
    "vaughan.hazeldine":    ("Vaughan Hazeldine",    "Charlotte",     177_000),
    "brandi.davis":         ("Brandi Davis",         "Chicago",       133_000),
    "kaylee.krostag":       ("Kaylee Krostag",       "Chicago",       133_000),
    "kristen.rosario":      ("Kristen Rosario",      "Chicago",       133_000),
    "sean.steele":          ("Sean Steele",          "Chicago",       133_000),
    "emily.nunn":           ("Emily Nunn",           "Dallas",         80_000),
    "jasmyne.boles":        ("Jasmyne Boles",        "Dallas",        146_000),
    "victoria.correa":      ("Victoria Correa",      "Dallas",        146_000),
    "brittany.herrera":     ("Brittany Herrera",     "Denver",        133_000),
    "robyn.yannoukos":      ("Robyn Yann",           "Denver",         73_000),
    "sydney.stetzel":       ("Sydney Stetzel",       "Denver",        146_000),
    "david.mckeever":       ("David McKeever",       "Los Angeles",   109_000),
    "nick.pagdilao":        ("Nick Pagdilao",        "Los Angeles",   109_000),
    "richard.boone":        ("Richard Boone",        "Los Angeles",   109_000),
    "sarah.dreier":         ("Sarah Dreier",         "Los Angeles",   109_000),
    "angela.sunder":        ("Angela Sunder",        "Minneapolis",    99_000),
    "jose.macario":         ("Jose Marcario",        "Minneapolis",    99_000),
    "luz.rivera":           ("Lucy Rivera",          "Minneapolis",   108_000),
    "zoe.finkelstein":      ("Zoe Finkelstein",      "Minneapolis",    99_000),
    "anastasia.seminchenko":("Anastasia Seminchenko","New York",      131_000),
    "ibtesam.chowdhury":    ("Ibtesam Chowdhury",   "New York",       95_000),
    "jamie.williams":       ("Jamie Williams",       "New York",      119_000),
    "lauren.shull":         ("Lauren Shull",         "New York",      119_000),
    "mouny.alfraik":        ("Mouny Alfraik",        "New York",      119_000),
    "robert.perez":         ("Robert Perez",         "New York",      119_000),
    "jenee.satterwhite":    ("Jenee Satterwhite",    "Philadelphia",   86_000),
    "kagen.haberstick":     ("Kagen Haberstick",     "Philadelphia",   86_000),
    "laurel.clark":         ("Laurel Clark",         "Philadelphia",   86_000),
    "amira.seale":           ("Amira Seale",          "San Francisco",  13_000),
    "bran.randol":           ("Bran Randol",          "San Francisco",  50_000),
    "mary.langridge":        ("Mary Langridge",       "San Francisco", 138_000),
    "rachel.kivo":           ("Rachel Kivo",          "San Francisco", 138_000),
    "alejandra.jimenez":     ("Alejandra Jimenez",    "Seattle",        83_000),
    "kai.davies":            ("Kai Davies",           "Seattle",        92_000),
    "laura.tulloch":         ("Laura Tulloch",        "Seattle",        83_000),
    "lindsay.reyna":         ("Lindsay Reyna",        "Seattle",        83_000),
    "rachel.roth":           ("Rachel Roth",          "Seattle",        83_000),
    "maico.vergara":         ("Maico Vergara",        "Washington DC", 107_000),
    "sameera.tanveer":       ("Sameera Tanveer",      "Washington DC", 107_000),
    "shawn.neifert":         ("Shawn Neifert",        "Washington DC", 117_000),
}


# ── Inbound CVR data ─────────────────────────────────────────────────────────

# Monthly 14/30/60/90-day CVR for 2026 (Total Business tab)
# Cohort = contacts who had first inbound in that month; CVR = % who ordered within N days
MONTHLY_CVR = [
    {"month": "Jan 2026", "contacts": 6_587, "d14": 12.72, "d30": 15.45, "d60": 17.12, "d90": 17.53},
    {"month": "Feb 2026", "contacts": 7_188, "d14": 17.64, "d30": 19.03, "d60": 19.85, "d90": 20.46},
    {"month": "Mar 2026", "contacts": 6_332, "d14": 12.02, "d30": 14.13, "d60": 15.45, "d90": 16.20},
    {"month": "Apr 2026", "contacts": 5_897, "d14": 11.57, "d30": 13.97, "d60": 15.72, "d90": 15.75},
    {"month": "May 2026", "contacts": 7_556, "d14": 17.23, "d30": 19.26, "d60": 19.32, "d90": 19.32},
    {"month": "Jun 2026*","contacts": 5_985, "d14":  7.61, "d30":  7.61, "d60":  7.61, "d90":  7.61},
]

# ── Last Week Jun 24–30, 2026 — Total Business tab ───────────────────────────

LW_B2C_REV, LW_B2C_ORD = 2_304_225.21, 790
LW_TR_REV,  LW_TR_ORD  =   359_701.36, 117
LW_HV_REV,  LW_HV_ORD  =   101_514.25,  34
LW_B2B_REV, LW_B2B_ORD =    55_093.65,   6
LW_TOT_REV, LW_TOT_ORD = 2_820_534.47, 947
LW_BLENDED_AOV =   2_979
LW_B2C_AOV     =   2_917
LW_TR_AOV      =   3_075
LW_ASSISTED_REV =  1_317_405   # STG_DEAL MC=Yes Jun 24-30 (46.7%)
LW_SNOWFLAKE_FCST = 1_709_585   # sum DAILY_FCST Jun 24-30

# Last week LY Jun 24–30, 2025 — Snowflake
LW_B2C_REV_LY, LW_B2C_ORD_LY = 1_478_818.85, 499
LW_TR_REV_LY,  LW_TR_ORD_LY  =   333_367.74, 116
LW_HV_REV_LY,  LW_HV_ORD_LY  =   232_998.60,  81
LW_B2B_REV_LY, LW_B2B_ORD_LY =    14_115.55,   4
LW_TOT_REV_LY, LW_TOT_ORD_LY = 2_059_300.74, 700
LW_BLENDED_AOV_LY =  2_942
LW_B2C_AOV_LY     =  2_963
LW_TR_AOV_LY      =  2_874

# Last week inbound — Jun 24-30
LW_INBOUND    = 2_485   # Jun 24-30 2026
LW_INBOUND_LY = 1_880   # Jun 24-30 2025

# Last week swatch — estimated proportional to MTD
SW_LW_ORD,    SW_LW_CUST    = 2_490, 2_113   # estimated Jun 24-30
SW_LW_LY_ORD, SW_LW_LY_CUST = 2_121, 1_782   # estimated LY

# ── Last Week Jun 24–30, 2026 — Sales Team tab ───────────────────────────────

LW_BY_STUDIO = [
    {"name": "New York",      "rev": 149_352.33},
    {"name": "Chicago",       "rev": 142_498.58},
    {"name": "Denver",        "rev": 138_845.96},
    {"name": "Seattle",       "rev": 131_927.90},
    {"name": "Boston",        "rev": 122_593.46},
    {"name": "Dallas",        "rev": 120_898.73},
    {"name": "Minneapolis",   "rev":  86_754.91},
    {"name": "Washington DC", "rev":  83_684.85},
    {"name": "Los Angeles",   "rev":  81_414.94},
    {"name": "Charlotte",     "rev":  71_929.32},
    {"name": "Baltimore",     "rev":  68_127.75},
    {"name": "San Francisco", "rev":  61_503.17},
    {"name": "Philadelphia",  "rev":  40_899.28},
]
LW_HS_TOTAL = 1_317_405   # STG_DEAL MC=Yes Closed Won CLOSE_DATE Jun 24-30
LW_LY_BY_STUDIO = {
    "New York":      182_189.76, "Denver":        130_638.45,
    "Charlotte":     116_115.22, "Boston":        105_177.25,
    "Seattle":        91_421.97, "Minneapolis":    91_027.10,
    "Chicago":        72_207.97, "Philadelphia":   71_322.70,
    "San Francisco":  62_619.70, "Dallas":         50_710.07,
    "Washington DC":  44_925.48, "Los Angeles":    43_892.64,
    "Baltimore":      12_830.74,
}
LW_HS_LY_TOTAL = 1_075_080   # IS_CONVERTED=TRUE Jun 24-30 2025

# Last week sales forecast — derived from DAILY_FCST
LW_SALES_FCST = sum(v for k,v in DAILY_FCST.items() if '2026-06-24' <= k <= '2026-06-30')

# ── Activities by studio — STG_HUBSPOT_ENGAGEMENTS_BASE, owner→studio via rep_map, MTD Jun 1–30 ──
# Source: HubSpot engagements (ENGAGEMENT_TYPE: call / meeting / email)
# Note: SMS and Conversation Sessions not available in Snowflake — see HubSpot dashboard for full picture
ACTIVITIES_BY_STUDIO = [
    {"studio": "New York",      "calls": 969, "meetings": 416, "emails": 14_015, "deals": 4_200},
    {"studio": "Chicago",       "calls": 732, "meetings": 240, "emails": 10_917, "deals": 3_249},
    {"studio": "Boston",        "calls": 474, "meetings": 182, "emails":  9_353, "deals": 2_987},
    {"studio": "Dallas",        "calls": 569, "meetings": 241, "emails": 14_230, "deals": 2_839},
    {"studio": "Minneapolis",   "calls": 893, "meetings": 241, "emails": 10_153, "deals": 2_562},
    {"studio": "Los Angeles",   "calls": 545, "meetings": 218, "emails":  8_621, "deals": 2_432},
    {"studio": "Denver",        "calls": 698, "meetings": 221, "emails":  8_428, "deals": 2_396},
    {"studio": "Seattle",       "calls": 350, "meetings": 269, "emails":  8_291, "deals": 2_307},
    {"studio": "Washington DC", "calls": 642, "meetings": 167, "emails":  8_932, "deals": 2_292},
    {"studio": "Charlotte",     "calls": 374, "meetings": 145, "emails":  6_446, "deals": 2_025},
    {"studio": "Baltimore",     "calls": 366, "meetings":  59, "emails":  9_496, "deals": 1_750},
    {"studio": "San Francisco", "calls": 231, "meetings": 177, "emails":  5_588, "deals": 1_717},
    {"studio": "Philadelphia",  "calls": 422, "meetings": 160, "emails":  4_755, "deals": 1_482},
]

# Rep headcount per studio — Design Experts + Senior Design Experts only (from REP_GOALS)
STUDIO_REP_COUNT = {
    "Baltimore": 3, "Boston": 4, "Charlotte": 2, "Chicago": 4,
    "Dallas": 3, "Denver": 3, "Los Angeles": 4, "Minneapolis": 4,
    "New York": 6, "Philadelphia": 3, "San Francisco": 3,
    "Seattle": 5, "Washington DC": 3,
}

# ── Tab 1: Total Business ─────────────────────────────────────────────────────

def tab1():
    # Yesterday section
    yd_mix = YD_B2C_REV + YD_TR_REV + YD_HV_REV
    row1 = (
        '<div class="kpi-grid">'
        + _kpi(_cf(YD_TOT_REV), "Revenue", _yoy(YD_TOT_REV, YD_TOT_REV_LY, fmt=_cf), "#0d9488")
        + _kpi(str(YD_TOT_ORD), "Orders", _yoy_n(YD_TOT_ORD, YD_TOT_ORD_LY))
        + _kpi(_pct(YD_ASSISTED_REV / YD_TOT_REV), "Assisted %")
        + _kpi(str(YD_INBOUND), "Inbound Engagements", _yoy_n(YD_INBOUND, YD_INBOUND_LY))
        + _fcst_kpi(YD_REV_FOR_FCST, YD_FCST_SNOWFLAKE, fmt=_cf)
        + '</div>'
    )
    row2 = (
        '<div class="aov-grid">'
        + _aov_box("Blended AOV", YD_BLENDED_AOV, _yoy(YD_BLENDED_AOV, YD_BLENDED_AOV_LY, fmt=_cf), fmt=_cf)
        + _aov_box("B2C AOV",     YD_B2C_AOV,     _yoy(YD_B2C_AOV,     YD_B2C_AOV_LY,     fmt=_cf), fmt=_cf)
        + _aov_box("Trade AOV",   YD_TR_AOV,       _yoy(YD_TR_AOV,      YD_TR_AOV_LY,       fmt=_cf), fmt=_cf)
        + '</div>'
    )
    segs = (
        '<div class="sub-label">Revenue by Customer Class</div>'
        + _seg_bar("B2C",     YD_B2C_REV, yd_mix, YD_B2C_REV_LY, "#6366f1", fmt=_cf)
        + _seg_bar("Trade",   YD_TR_REV,  yd_mix, YD_TR_REV_LY,  "#0d9488", fmt=_cf)
        + _seg_bar("Havenly", YD_HV_REV,  yd_mix, YD_HV_REV_LY,  "#a78bfa", fmt=_cf)
    )
    yd_sec = (
        '<div class="section">'
        '<div class="section-label">📈 Yesterday — Tue Jun 30</div>'
        + row1 + row2 + segs + '</div>'
    )

    # Last Week section — Jun 15–21, 2026
    lw_mix = LW_B2C_REV + LW_TR_REV + LW_HV_REV + LW_B2B_REV
    lw_row1 = (
        '<div class="kpi-grid">'
        + _kpi(_cf(LW_TOT_REV), "Revenue", _yoy(LW_TOT_REV, LW_TOT_REV_LY, fmt=_cf), "#0d9488")
        + _kpi(str(LW_TOT_ORD), "Orders", _yoy_n(LW_TOT_ORD, LW_TOT_ORD_LY))
        + _kpi(_pct(LW_ASSISTED_REV / LW_TOT_REV), "Assisted %")
        + _kpi(str(LW_INBOUND), "Inbound Engagements", _yoy_n(LW_INBOUND, LW_INBOUND_LY))
        + _fcst_kpi(LW_TOT_REV, LW_SNOWFLAKE_FCST, fmt=_cf)
        + '</div>'
    )
    lw_row2 = (
        '<div class="aov-grid">'
        + _aov_box("Blended AOV", LW_BLENDED_AOV, _yoy(LW_BLENDED_AOV, LW_BLENDED_AOV_LY, fmt=_cf), fmt=_cf)
        + _aov_box("B2C AOV",     LW_B2C_AOV,     _yoy(LW_B2C_AOV,     LW_B2C_AOV_LY,     fmt=_cf), fmt=_cf)
        + _aov_box("Trade AOV",   LW_TR_AOV,       _yoy(LW_TR_AOV,      LW_TR_AOV_LY,       fmt=_cf), fmt=_cf)
        + '</div>'
    )
    lw_segs = (
        '<div class="sub-label">Revenue by Customer Class</div>'
        + _seg_bar("B2C",     LW_B2C_REV, lw_mix, LW_B2C_REV_LY, "#6366f1", fmt=_cf)
        + _seg_bar("Trade",   LW_TR_REV,  lw_mix, LW_TR_REV_LY,  "#0d9488", fmt=_cf)
        + _seg_bar("Havenly", LW_HV_REV,  lw_mix, LW_HV_REV_LY,  "#a78bfa", fmt=_cf)
        + _seg_bar("B2B",     LW_B2B_REV, lw_mix, LW_B2B_REV_LY, "#64748b", fmt=_cf)
    )
    lw_swatches = (
        '<div class="sub-label">Swatch Performance</div>'
        '<div class="kpi-grid">'
        + _kpi(f"{SW_LW_ORD:,}", "Swatch Orders", _yoy_n(SW_LW_ORD, SW_LW_LY_ORD))
        + _kpi(f"{SW_LW_CUST:,}", "Unique Customers", _yoy_n(SW_LW_CUST, SW_LW_LY_CUST))
        + '</div>'
        + '<p class="note">⚠ Inbound and swatch figures are estimated — update from Looker dashboard 1156.</p>'
    )
    lw_sec = (
        '<div class="section">'
        '<div class="section-label">📆 Last Week — Jun 24–30</div>'
        + lw_row1 + lw_row2 + lw_segs + lw_swatches + '</div>'
    )

    # MTD section
    mtd_mix = MTD_B2C_REV + MTD_TR_REV + MTD_HV_REV + MTD_B2B_REV
    mtd_row1 = (
        '<div class="kpi-grid">'
        + _kpi(_cf(MTD_TOT_REV), "MTD Revenue", _yoy(MTD_TOT_REV, MTD_TOT_REV_LY, fmt=_cf), "#0d9488")
        + _kpi(str(MTD_TOT_ORD), "MTD Orders", _yoy_n(MTD_TOT_ORD, MTD_TOT_ORD_LY))
        + _kpi(_pct(MTD_REPEAT_PCT), "Repeat %")
        + _kpi(_pct(MTD_ASSISTED_REV / MTD_TOT_REV), "Assisted %")
        + _fcst_kpi(MTD_REV_FOR_FCST, MTD_SNOWFLAKE_FCST, fmt=_cf)
        + '</div>'
    )
    mtd_row2 = (
        '<div class="aov-grid">'
        + _aov_box("Blended AOV", MTD_BLENDED_AOV,    _yoy(MTD_BLENDED_AOV,    MTD_BLENDED_AOV_LY,    fmt=_cf), fmt=_cf)
        + _aov_box("B2C AOV",     MTD_B2C_AOV,        _yoy(MTD_B2C_AOV,        MTD_B2C_AOV_LY,        fmt=_cf), fmt=_cf)
        + _aov_box("Trade AOV",   MTD_TR_AOV,         _yoy(MTD_TR_AOV,         MTD_TR_AOV_LY,          fmt=_cf), fmt=_cf)
        + f'<div class="aov-box"><div class="aov-lbl">Inbound MTD</div>'
          f'<div class="aov-val">{MTD_INBOUND:,}</div>'
          f'<div class="aov-chg">{_yoy_n(MTD_INBOUND, MTD_INBOUND_LY)}</div></div>'
        + '</div>'
    )
    mtd_segs = (
        '<div class="sub-label">Revenue by Customer Class</div>'
        + _seg_bar("B2C",     MTD_B2C_REV, mtd_mix, MTD_B2C_REV_LY, "#6366f1", fmt=_cf)
        + _seg_bar("Trade",   MTD_TR_REV,  mtd_mix, MTD_TR_REV_LY,  "#0d9488", fmt=_cf)
        + _seg_bar("Havenly", MTD_HV_REV,  mtd_mix, MTD_HV_REV_LY,  "#a78bfa", fmt=_cf)
        + _seg_bar("B2B",     MTD_B2B_REV, mtd_mix, MTD_B2B_REV_LY, "#64748b", fmt=_cf)
    )
    swatches = (
        '<div class="sub-label">Swatch Performance</div>'
        '<div class="kpi-grid">'
        + _kpi(f"{SW_MTD_ORD:,}", "Swatch Orders MTD", _yoy_n(SW_MTD_ORD, SW_LY_ORD))
        + _kpi(f"{SW_MTD_CUST:,}", "Unique Customers MTD", _yoy_n(SW_MTD_CUST, SW_LY_CUST))
        + '</div>'
    )
    mtd_merch = '<div class="sub-label">Merch Contribution (Merchandise · MTO + QS)</div>'
    for m in MERCH[:9]:
        mtd_merch += _merch_bar(m["cat"], m["rev"], m["units"], m["aur"], MERCH_TOTAL)

    # Studio table — Looker studio_name revenue + Looker CVR (MTD & 90D)
    # "% of Baseline" = MTD CVR / 90D CVR — shows how close each studio is to its normal rate
    # Color: green = above group avg baseline %, yellow = near avg, red = well below
    tot_ord = sum(s["orders"] for s in STUDIOS_ORDERS)
    tot_inb = TOTAL_INBOUND

    # Compute each studio's baseline % and group average
    baseline_pcts = {s["name"]: (MTD_CVR.get(s["name"],0) / NINETY_DAY_CVR.get(s["name"],1))
                     for s in STUDIOS_ORDERS}
    avg_baseline  = sum(baseline_pcts[s["name"]] * s["inbound"] for s in STUDIOS_ORDERS) / tot_inb

    avg_mtd = sum(MTD_CVR.get(s["name"],0) * s["inbound"] for s in STUDIOS_ORDERS) / tot_inb
    avg_90d = sum(NINETY_DAY_CVR.get(s["name"],0) * s["inbound"] for s in STUDIOS_ORDERS) / tot_inb

    studio_rows = ""
    for s in STUDIOS_ORDERS:
        name      = s["name"]
        aov       = s.get("aov", s["rev"] / s["orders"] if s["orders"] else 0)
        pct_d     = s["inbound"] / TOTAL_INBOUND
        mtd_cvr   = MTD_CVR.get(name, 0)
        d90_cvr   = NINETY_DAY_CVR.get(name, 0)
        base_pct  = baseline_pcts[name]
        diff_avg  = base_pct - avg_baseline   # above/below group avg baseline %

        # Color based on how studio compares to group average baseline %
        if diff_avg >= 0.05:   b_color = "#16a34a"  # well above avg → green
        elif diff_avg >= -0.05: b_color = "#ca8a04"  # near avg → yellow
        else:                   b_color = "#dc2626"  # below avg → red

        vs_avg = f'<span style="color:{b_color};font-weight:700">{base_pct*100:.0f}%</span>'
        studio_rows += (
            f'<tr><td>{name}</td><td>{_cf(s["rev"])}</td><td>{s["orders"]}</td>'
            f'<td>{_cf(aov)}</td><td>{_pct(pct_d)}</td>'
            f'<td>{_pct(mtd_cvr)}</td><td>{_pct(d90_cvr)}</td><td>{vs_avg}</td></tr>'
        )

    # Total row
    avg_base_pct = avg_baseline
    studio_rows += (
        f'<tr style="font-weight:700;border-top:2px solid #e2e8f0">'
        f'<td>Total / Avg</td><td>{_cf(STUDIO_TOT_REV)}</td><td>{tot_ord}</td>'
        f'<td>{_cf(STUDIO_TOT_REV/tot_ord)}</td><td>100%</td>'
        f'<td>{_pct(avg_mtd)}</td><td>{_pct(avg_90d)}</td>'
        f'<td style="color:#475569">{avg_base_pct*100:.0f}% avg</td></tr>'
    )
    studio_tbl = (
        '<div class="sub-label">Studio Performance</div>'
        '<p class="note" style="margin-bottom:8px">% of Baseline = MTD CVR ÷ 90-Day CVR. '
        f'Group avg this month: {avg_baseline*100:.0f}% of baseline. '
        '<span style="color:#16a34a">●</span> above avg &nbsp;'
        '<span style="color:#ca8a04">●</span> near avg &nbsp;'
        '<span style="color:#dc2626">●</span> below avg</p>'
        '<div class="table-wrap"><table><tr>'
        '<th>Studio</th><th>Revenue</th><th>Orders</th><th>AOV</th>'
        '<th>% Deals</th><th>MTD CVR</th><th>90D CVR</th>'
        '<th>MTD CVR<br><span style="font-weight:400;font-size:9px;color:#94a3b8">as % of 90D avg</span></th>'
        '</tr>' + studio_rows + '</table></div>'
    )

    # Monthly CVR — combo chart: bars = inbound contacts, lines = CVR by window
    # SVG dimensions
    SW, SH   = 600, 340   # total SVG
    CX1, CX2 = 60, 575    # chart x bounds
    CY1, CY2 = 20, 290    # chart y bounds
    CW = CX2 - CX1        # chart width
    CH = CY2 - CY1        # chart height

    months     = [r["month"].replace(" 2026","") for r in MONTHLY_CVR]
    n          = len(months)
    bar_gap    = CW / n
    bar_w      = bar_gap * 0.45
    xs         = [CX1 + bar_gap * (i + 0.5) for i in range(n)]

    max_contacts = max(r["contacts"] for r in MONTHLY_CVR)
    max_cvr      = 22.0   # secondary Y-axis max %
    inprog_idx   = n - 1  # June = in-progress

    def _bar_y(contacts):
        return CY2 - (contacts / max_contacts * CH * 0.85)

    def _cvr_y(pct):
        return CY2 - (pct / max_cvr * CH)

    LINE_SERIES = [
        ("14-Day", "d14", "#0d9488", "8,2"),
        ("30-Day", "d30", "#6366f1", "4,2"),
        ("60-Day", "d60", "#f59e0b", "2,2"),
        ("90-Day", "d90", "#64748b", "none"),
    ]

    # Build SVG
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="{SW}" height="{SH}" style="font-family:-apple-system,sans-serif;overflow:visible">'

    # Y-axis gridlines (CVR scale, right)
    for pct in [5, 10, 15, 20]:
        gy = _cvr_y(pct)
        svg += f'<line x1="{CX1}" y1="{gy:.1f}" x2="{CX2}" y2="{gy:.1f}" stroke="#e2e8f0" stroke-width="1"/>'
        svg += f'<text x="{CX2+6}" y="{gy+4:.1f}" font-size="9" fill="#94a3b8">{pct}%</text>'

    # Bars (inbound contacts)
    for i, r in enumerate(MONTHLY_CVR):
        bx = xs[i] - bar_w / 2
        by = _bar_y(r["contacts"])
        bh = CY2 - by
        color = "#e2e8f0" if i == inprog_idx else "#bfdbfe"
        svg += f'<rect x="{bx:.1f}" y="{by:.1f}" width="{bar_w:.1f}" height="{bh:.1f}" rx="2" fill="{color}"/>'
        # contact count label inside bar (if room) or above
        label_y = by - 3 if bh > 20 else by - 5
        svg += f'<text x="{xs[i]:.1f}" y="{label_y:.1f}" text-anchor="middle" font-size="8" fill="#64748b">{r["contacts"]//100*100:,}</text>'

    # CVR lines
    for key, field, color, dash in LINE_SERIES:
        pts = " ".join(f"{xs[i]:.1f},{_cvr_y(r[field]):.1f}" for i, r in enumerate(MONTHLY_CVR) if i < inprog_idx)
        dash_attr = f'stroke-dasharray="{dash}"' if dash != "none" else ""
        svg += f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="2.5" {dash_attr} stroke-linejoin="round" stroke-linecap="round"/>'
        # dots
        for i, r in enumerate(MONTHLY_CVR):
            if i >= inprog_idx: continue
            cy = _cvr_y(r[field])
            svg += f'<circle cx="{xs[i]:.1f}" cy="{cy:.1f}" r="4" fill="{color}" stroke="white" stroke-width="1.5"/>'
            if field == "d90":
                svg += f'<text x="{xs[i]:.1f}" y="{cy-9:.1f}" text-anchor="middle" font-size="10" fill="{color}" font-weight="700">{r[field]}%</text>'

    # X-axis labels
    for i, (m, r) in enumerate(zip(months, MONTHLY_CVR)):
        lbl = m + ("*" if i == inprog_idx else "")
        svg += f'<text x="{xs[i]:.1f}" y="{CY2+14}" text-anchor="middle" font-size="10" fill="#475569">{lbl}</text>'

    # Left Y-axis label
    svg += f'<text x="12" y="{(CY1+CY2)//2}" text-anchor="middle" font-size="9" fill="#94a3b8" transform="rotate(-90,12,{(CY1+CY2)//2})">Inbound</text>'
    svg += f'<text x="{CX2+28}" y="{CY1-4}" text-anchor="middle" font-size="9" fill="#94a3b8">CVR</text>'

    svg += '</svg>'

    # Legend
    legend_items = "".join(
        f'<span style="display:flex;align-items:center;gap:4px;font-size:10px;color:#334155">'
        f'<svg width="16" height="10"><line x1="0" y1="5" x2="16" y2="5" stroke="{color}" stroke-width="2" '
        f'{"stroke-dasharray="+chr(34)+dash+chr(34) if dash != "none" else ""}/></svg>{key}</span>'
        for key, field, color, dash in LINE_SERIES
    )
    legend = f'<div style="display:flex;gap:16px;margin-bottom:6px;flex-wrap:wrap">{legend_items}</div>'

    monthly_cvr_tbl = (
        '<div class="sub-label">Inbound Contacts (bars) + CVR by Window (lines) — 2026 Monthly Cohorts</div>'
        + legend
        + f'<div style="overflow-x:auto">{svg}</div>'
        + '<p class="note">Bars = inbound contacts (left scale). Lines = % who ordered within 14/30/60/90 days of first contact. '
        '*Jun in-progress (Jun 1–14) — lines excluded. 90D label shown above each dot.</p>'
    )

    mtd_sec = (
        '<div class="section">'
        '<div class="section-label">📅 MTD — Jun 1–30 · Forecast: Looker/Snowflake</div>'
        + mtd_row1 + mtd_row2 + mtd_segs + swatches + mtd_merch + studio_tbl + '</div>'
    )

    # Performance blurb — dynamically generated from all data
    def _sign1(v): return "▲" if v >= 0 else "▼"
    def _col1(v):  return "#16a34a" if v >= 0 else "#dc2626"
    def _dir1(v):  return "ahead of" if v >= 0 else "behind"

    yd_vs_fcst  = (YD_REV_FOR_FCST  - YD_FCST_SNOWFLAKE)  / YD_FCST_SNOWFLAKE  * 100
    yd_aov_chg  = (YD_BLENDED_AOV   - YD_BLENDED_AOV_LY)  / YD_BLENDED_AOV_LY  * 100
    yd_inb_chg  = (YD_INBOUND       - YD_INBOUND_LY)       / YD_INBOUND_LY       * 100 if YD_INBOUND_LY else 0
    yd_ast_pct  =  YD_ASSISTED_REV  / YD_TOT_REV * 100
    lw_vs_fcst1 = (LW_TOT_REV       - LW_SNOWFLAKE_FCST)   / LW_SNOWFLAKE_FCST   * 100
    lw_rev_yoy  = (LW_TOT_REV       - LW_TOT_REV_LY)       / LW_TOT_REV_LY       * 100
    lw_aov_yoy  = (LW_BLENDED_AOV   - LW_BLENDED_AOV_LY)   / LW_BLENDED_AOV_LY   * 100
    lw_b2c_pct  =  LW_B2C_REV / lw_mix * 100
    lw_b2c_ly   =  LW_B2C_REV_LY / (LW_B2C_REV_LY+LW_TR_REV_LY+LW_HV_REV_LY+LW_B2B_REV_LY) * 100
    mtd_vs_fcst = (MTD_REV_FOR_FCST - MTD_SNOWFLAKE_FCST)  / MTD_SNOWFLAKE_FCST  * 100
    mtd_rev_yoy = (MTD_TOT_REV      - MTD_TOT_REV_LY)      / MTD_TOT_REV_LY      * 100
    mtd_inb_chg = (MTD_INBOUND      - MTD_INBOUND_LY)      / MTD_INBOUND_LY      * 100 if MTD_INBOUND_LY else 0
    mtd_sw_chg  = (SW_MTD_ORD       - SW_LY_ORD)           / SW_LY_ORD           * 100
    mtd_aov_yoy = (MTD_BLENDED_AOV  - MTD_BLENDED_AOV_LY)  / MTD_BLENDED_AOV_LY  * 100
    mtd_ast_pct =  MTD_ASSISTED_REV / MTD_TOT_REV * 100

    blurb_lines = [
        '<div style="font-size:11px;font-weight:700;color:#1e293b;margin-bottom:10px;text-transform:uppercase;letter-spacing:.5px">📊 Performance Summary — Why Are We Missing / Achieving Plan?</div>',
        f'<div style="margin-bottom:9px"><span style="font-weight:700;font-size:12px">Yesterday: </span>'
        f'<span style="font-size:12px;color:#334155">{_cf(YD_TOT_REV)} — <span style="color:{_col1(yd_vs_fcst)}">{_sign1(yd_vs_fcst)} {abs(yd_vs_fcst):.1f}% {_dir1(yd_vs_fcst)}</span> forecast. '
        f'Inbound <span style="color:{_col1(yd_inb_chg)}">{_sign1(yd_inb_chg)} {abs(yd_inb_chg):.1f}% YoY</span> ({YD_INBOUND} vs {YD_INBOUND_LY}). '
        f'Blended AOV {_cf(YD_BLENDED_AOV)} <span style="color:{_col1(yd_aov_chg)}">{_sign1(yd_aov_chg)} {abs(yd_aov_chg):.1f}% YoY</span>. '
        f'Assisted (MC=Yes): {yd_ast_pct:.1f}% of revenue.</span></div>',
        f'<div style="margin-bottom:9px"><span style="font-weight:700;font-size:12px">Last Week (Jun 24–30): </span>'
        f'<span style="font-size:12px;color:#334155">{_cf(LW_TOT_REV)} — <span style="color:{_col1(lw_vs_fcst1)}">{_sign1(lw_vs_fcst1)} {abs(lw_vs_fcst1):.1f}% {_dir1(lw_vs_fcst1)}</span> forecast. '
        f'Revenue <span style="color:{_col1(lw_rev_yoy)}">{_sign1(lw_rev_yoy)} {abs(lw_rev_yoy):.1f}% YoY</span>. '
        f'AOV {_cf(LW_BLENDED_AOV)} vs {_cf(LW_BLENDED_AOV_LY)} LY <span style="color:{_col1(lw_aov_yoy)}">{_sign1(lw_aov_yoy)} {abs(lw_aov_yoy):.1f}%</span>. '
        f'B2C mix {lw_b2c_pct:.0f}% vs {lw_b2c_ly:.0f}% LY ({"▼ shift toward non-B2C" if lw_b2c_pct < lw_b2c_ly else "▲ stronger B2C mix"}).</span></div>',
        f'<div><span style="font-weight:700;font-size:12px">MTD (Jun 1–30): </span>'
        f'<span style="font-size:12px;color:#334155">{_cf(MTD_TOT_REV)} — <span style="color:{_col1(mtd_vs_fcst)}">{_sign1(mtd_vs_fcst)} {abs(mtd_vs_fcst):.1f}% {_dir1(mtd_vs_fcst)}</span> forecast. '
        f'Revenue <span style="color:{_col1(mtd_rev_yoy)}">{_sign1(mtd_rev_yoy)} {abs(mtd_rev_yoy):.1f}% YoY</span>. '
        f'Lead indicators: inbound <span style="color:{_col1(mtd_inb_chg)}">{_sign1(mtd_inb_chg)} {abs(mtd_inb_chg):.1f}% YoY</span> ({MTD_INBOUND:,} vs {MTD_INBOUND_LY:,}), '
        f'swatches <span style="color:{_col1(mtd_sw_chg)}">{_sign1(mtd_sw_chg)} {abs(mtd_sw_chg):.1f}% YoY</span> ({SW_MTD_ORD:,} vs {SW_LY_ORD:,}). '
        f'Blended AOV {_cf(MTD_BLENDED_AOV)} vs {_cf(MTD_BLENDED_AOV_LY)} LY <span style="color:{_col1(mtd_aov_yoy)}">{_sign1(mtd_aov_yoy)} {abs(mtd_aov_yoy):.1f}%</span>. '
        f'Assisted: {mtd_ast_pct:.1f}% of revenue.</span></div>',
    ]
    blurb_sec = (
        '<div class="section">'
        '<div style="background:#f0fdf4;border:1px solid #bbf7d0;border-left:3px solid #16a34a;border-radius:6px;padding:14px 16px">'
        + "".join(blurb_lines) + '</div></div>'
    )

    cvr_sec = (
        '<div class="section">'
        '<div class="section-label">📈 Inbound CVR Trend — 2026 Monthly Cohorts</div>'
        + monthly_cvr_tbl + '</div>'
    )

    return f"""
<div class="page-label">Interior Define · Total Business · Tue Jun 30, 2026</div>
<div class="email-wrap">
  <div class="hdr">
    <div class="hdr-brand">Interior Define Total Business Tuesday Jun 30, 2026</div>
    <div class="hdr-meta">Daily Business Review · Tue Jun 30, 2026 · Forecast source: Looker (ID_FORECASTED_ADJUSTED_GROSS_BOOKINGS)</div>
  </div>
  {yd_sec}
  {lw_sec}
  {blurb_sec}
  {mtd_sec}
  {cvr_sec}
  <div class="footer">Interior Define Daily Business Review — auto-generated · Forecast: FIVETRAN_DB.UPLOADS.ALL_COMPANY_DAILY_FORECAST</div>
</div>"""


# ── Tab 2: Sales Team ─────────────────────────────────────────────────────────

def tab2():
    # Yesterday
    max_yd_s = max(s["rev"] for s in YD_BY_STUDIO)
    max_yd_r = YD_TOP_REPS[0]["rev"]
    yd_s_bars = "".join(_horiz_bar(s["name"], s["rev"], max_yd_s) for s in YD_BY_STUDIO[:5])
    yd_r_bars = "".join(_horiz_bar(f'{r["name"]} · {r["studio"]}', r["rev"], max_yd_r, "#6366f1") for r in YD_TOP_REPS)

    yd_yoy = _yoy(YD_HS_TOTAL, YD_HS_LY_TOTAL)  # LY: Snowflake pre-Aug methodology
    yd_fcst_d = (YD_HS_TOTAL - YD_SALES_FCST) / YD_SALES_FCST
    yd_css = "up" if yd_fcst_d >= 0 else "dn"

    yd_net = (
        '<div class="ns-pair">'
        f'<div class="ns-box" style="border-left:3px solid #0d9488">'
        f'<div class="ns-lbl">Net Sales (Snowflake/HubSpot)</div>'
        f'<div class="ns-val">{_c(YD_HS_TOTAL)}</div>'
        f'<div class="ns-chg">{yd_yoy}</div>'
        f'</div>'
        f'<div class="ns-box" style="border-left:3px solid {"#16a34a" if yd_fcst_d>=0 else "#dc2626"}">'
        f'<div class="ns-lbl">vs Forecast</div>'
        f'<div class="ns-val" style="font-size:16px"><span class="{yd_css}">{"+" if yd_fcst_d>=0 else ""}{yd_fcst_d*100:.1f}% v. {_c(YD_SALES_FCST)} fcst</span></div>'
        f'</div>'
        '</div>'
    )
    def _nl(bold, rest):
        return f'<div style="margin-bottom:7px;font-size:12.5px;color:#1e293b;line-height:1.6"><strong>{bold}</strong> {rest}</div>'

    yd_notes = (
        '<div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:6px;padding:14px 16px;margin-top:12px">'
        '<div class="sub-label" style="color:#b45309;margin-bottom:10px">📝 Closing Notes — Tue Jun 30</div>'
        + _nl("Strong end-of-month Tuesday — Minneapolis led with $85K.", "Angela Sunder ($31K) and Zoe Finkelstein ($27K) powered Minneapolis to the top spot. Denver $50K (Brittany Herrera $28K), SF $42K (Rachel Kivo $27K), Chicago $42K.")
        + _nl("June finished at $7.9M vs $6.8M LY (+17%).", "MTD Total Business up 17% YoY on 18% more orders. All studio tiers contributed — strong end-of-month push across all 13 studios closed out Q2.")
        + '<div style="margin-top:10px;padding:8px 12px;background:#fff7ed;border-left:3px solid #ea580c;border-radius:3px;font-size:12px;color:#9a3412">'
        '⚠ <strong>Watch:</strong> June studio-assisted revenue hit $4.8M MTD — track July pipeline health early given end-of-month pull-forward effect.'
        '</div>'
        '</div>'
    )

    yd_sec = (
        '<div class="section">'
        '<div class="section-label">📈 Yesterday — Tue Jun 30</div>'
        + yd_net
        + '<div class="two-col">'
        + f'<div><div class="sub-label">Top 5 Studios</div>{yd_s_bars}</div>'
        + f'<div><div class="sub-label">Top 5 Individuals</div>{yd_r_bars}</div>'
        + '</div>'
        + yd_notes
        + '</div>'
    )

    # ── Last Week section (Jun 18–24) ─────────────────────────────────────────
    lw_hs_yoy   = _yoy(LW_HS_TOTAL, LW_HS_LY_TOTAL)
    lw_fcst_d   = (LW_HS_TOTAL - LW_SALES_FCST) / LW_SALES_FCST if LW_SALES_FCST else 0
    lw_fcst_css = "up" if lw_fcst_d >= 0 else "dn"
    lw_net = (
        '<div class="ns-pair">'
        f'<div class="ns-box" style="border-left:3px solid #0d9488">'
        f'<div class="ns-lbl">Net Sales — Last Week</div>'
        f'<div class="ns-val">{_c(LW_HS_TOTAL)}</div>'
        f'<div class="ns-chg">{lw_hs_yoy}</div>'
        f'</div>'
        f'<div class="ns-box" style="border-left:3px solid {"#16a34a" if lw_fcst_d>=0 else "#dc2626"}">'
        f'<div class="ns-lbl">vs Forecast</div>'
        f'<div class="ns-val" style="font-size:16px"><span class="{lw_fcst_css}">{"+" if lw_fcst_d>=0 else ""}{lw_fcst_d*100:.1f}% v. {_c(LW_SALES_FCST)} fcst</span></div>'
        f'</div>'
        '</div>'
    )
    max_lw_s = max(s["rev"] for s in LW_BY_STUDIO)
    lw_s_bars = "".join(_horiz_bar(s["name"], s["rev"], max_lw_s) for s in sorted(LW_BY_STUDIO, key=lambda x: -x["rev"])[:5])
    lw_sec = (
        '<div class="section">'
        '<div class="section-label">📆 Last Week — Jun 24–30</div>'
        + lw_net
        + f'<div><div class="sub-label">Top 5 Studios</div>{lw_s_bars}</div>'
        + '</div>'
    )

    # ── Activities by Studio ───────────────────────────────────────────────────
    act_total = {k: sum(s[k] for s in ACTIVITIES_BY_STUDIO) for k in ("calls","meetings","emails","deals")}
    def _act_bar(v, mx, color="#6366f1"):
        w = int(v / mx * 120) if mx else 0
        return f'<div style="width:{w}px;height:10px;background:{color};border-radius:2px;display:inline-block;vertical-align:middle"></div>'

    act_rows = ""
    max_calls = max(s["calls"] for s in ACTIVITIES_BY_STUDIO)
    max_mtgs  = max(s["meetings"] for s in ACTIVITIES_BY_STUDIO)
    max_emails= max(s["emails"]   for s in ACTIVITIES_BY_STUDIO)
    for s in sorted(ACTIVITIES_BY_STUDIO, key=lambda x: -(x["calls"]+x["meetings"]+x["emails"])):
        reps = STUDIO_REP_COUNT.get(s["studio"], 1)
        calls_pp  = s["calls"]    / reps
        mtgs_pp   = s["meetings"] / reps
        emails_pp = s["emails"]   / reps
        act_rows += (
            f'<tr>'
            f'<td style="font-weight:600">{s["studio"]}</td>'
            f'<td>{s["calls"]:,} {_act_bar(s["calls"],max_calls,"#6366f1")}</td>'
            f'<td style="font-size:10px;color:#64748b">{calls_pp:.1f}/rep</td>'
            f'<td>{s["meetings"]:,} {_act_bar(s["meetings"],max_mtgs,"#0d9488")}</td>'
            f'<td style="font-size:10px;color:#64748b">{mtgs_pp:.1f}/rep</td>'
            f'<td>{s["emails"]:,} {_act_bar(s["emails"],max_emails,"#94a3b8")}</td>'
            f'<td style="font-size:10px;color:#64748b">{emails_pp:.1f}/rep</td>'
            f'<td style="color:#64748b">{s["deals"]:,}</td>'
            f'</tr>'
        )
    act_rows += (
        f'<tr style="font-weight:700;border-top:2px solid #cbd5e1">'
        f'<td>TOTAL</td>'
        f'<td colspan="2">{act_total["calls"]:,} calls</td>'
        f'<td colspan="2">{act_total["meetings"]:,} mtgs</td>'
        f'<td colspan="2">{act_total["emails"]:,} emails</td>'
        f'<td>{act_total["deals"]:,}</td></tr>'
    )
    act_tbl = (
        '<div class="table-wrap"><table>'
        '<tr><th>Studio</th>'
        '<th>Calls</th><th>Calls/Rep</th>'
        '<th>Meetings</th><th>Mtgs/Rep</th>'
        '<th>Emails Sent</th><th>Emails/Rep</th>'
        '<th>Deals Touched</th></tr>'
        + act_rows + '</table></div>'
    )
    # So-what blurb
    top_calls_studio = max(ACTIVITIES_BY_STUDIO, key=lambda x: x["calls"]/STUDIO_REP_COUNT.get(x["studio"],1))
    top_mtg_studio   = max(ACTIVITIES_BY_STUDIO, key=lambda x: x["meetings"]/STUDIO_REP_COUNT.get(x["studio"],1))
    low_mtg_studio   = min(ACTIVITIES_BY_STUDIO, key=lambda x: x["meetings"]/STUDIO_REP_COUNT.get(x["studio"],1))
    top_c_pp  = top_calls_studio["calls"]  / STUDIO_REP_COUNT.get(top_calls_studio["studio"],1)
    top_m_pp  = top_mtg_studio["meetings"] / STUDIO_REP_COUNT.get(top_mtg_studio["studio"],1)
    low_m_pp  = low_mtg_studio["meetings"] / STUDIO_REP_COUNT.get(low_mtg_studio["studio"],1)
    avg_m_pp  = act_total["meetings"] / sum(STUDIO_REP_COUNT.values())
    avg_c_pp  = act_total["calls"]    / sum(STUDIO_REP_COUNT.values())
    act_blurb = (
        '<div style="background:#f0f9ff;border:1px solid #bae6fd;border-left:3px solid #0284c7;border-radius:6px;padding:12px 14px;margin-top:10px">'
        '<div style="font-size:11px;font-weight:700;color:#0c4a6e;margin-bottom:8px;text-transform:uppercase;letter-spacing:.4px">💡 So What — Activities MTD</div>'
        f'<div style="font-size:12px;color:#1e293b;line-height:1.65">'
        f'Across all {sum(STUDIO_REP_COUNT.values())} DE/SDEs, the team averaged <strong>{avg_c_pp:.1f} calls/rep</strong> and <strong>{avg_m_pp:.1f} meetings/rep</strong> MTD. '
        f'<strong>{top_calls_studio["studio"]}</strong> leads on calls/rep ({top_c_pp:.1f}); '
        f'<strong>{top_mtg_studio["studio"]}</strong> leads on meetings/rep ({top_m_pp:.1f}). '
        f'<strong>{low_mtg_studio["studio"]}</strong> has the fewest meetings/rep ({low_m_pp:.1f} vs {avg_m_pp:.1f} avg) — worth monitoring given meetings are the highest-converting activity. '
        f'Note: source is HubSpot engagements (STG_HUBSPOT_ENGAGEMENTS_BASE), owner mapped to studio via STG_DEAL. SMS and Conversation Sessions not available in Snowflake — see HubSpot MTD Activity by DE dashboard for full picture.'
        f'</div>'
        '</div>'
    )
    activities_sec = (
        '<div class="section">'
        '<div class="section-label">📞 Activities by Studio — MTD (DE/SDE only)</div>'
        + act_tbl + act_blurb + '</div>'
    )

    # ── Sales Team Performance Blurb ──────────────────────────────────────────
    def _s(v):    return "▲" if v >= 0 else "▼"
    def _c2(v):   return "#16a34a" if v >= 0 else "#dc2626"
    def _dir2(v): return "ahead of" if v >= 0 else "behind"

    yd_s_fcst  = (YD_HS_TOTAL  - YD_SALES_FCST)  / YD_SALES_FCST  * 100 if YD_SALES_FCST  else 0
    yd_s_yoy   = (YD_HS_TOTAL  - YD_HS_LY_TOTAL)  / YD_HS_LY_TOTAL  * 100 if YD_HS_LY_TOTAL  else 0
    lw_s_fcst2 = (LW_HS_TOTAL  - LW_SALES_FCST)  / LW_SALES_FCST   * 100 if LW_SALES_FCST  else 0
    lw_s_yoy   = (LW_HS_TOTAL  - LW_HS_LY_TOTAL)  / LW_HS_LY_TOTAL  * 100 if LW_HS_LY_TOTAL  else 0
    mtd_s_fcst = (MTD_HS_TOTAL - MTD_SALES_FCST)  / MTD_SALES_FCST  * 100 if MTD_SALES_FCST else 0
    mtd_s_yoy  = (MTD_HS_TOTAL - MTD_HS_LY_TOTAL) / MTD_HS_LY_TOTAL * 100 if MTD_HS_LY_TOTAL else 0

    # Studios ahead/behind paced goal MTD
    studios_ahead  = []
    studios_behind = []
    for studio in sorted(STUDIO_GOALS.keys()):
        goal   = STUDIO_GOALS[studio]
        paced  = goal * PACING_PCT
        actual = next((s["rev"] for s in MTD_BY_STUDIO if s["name"] == studio), 0)
        pct_p  = actual / paced if paced else 0
        if pct_p >= 1.05:
            studios_ahead.append((studio, pct_p))
        elif pct_p < 0.85:
            studios_behind.append((studio, pct_p))
    studios_ahead.sort(key=lambda x: -x[1])
    studios_behind.sort(key=lambda x: x[1])

    # Reps pacing well vs not
    reps_ahead_l  = []
    reps_behind_l = []
    for email_key, (display_name, studio, goal) in REP_GOALS.items():
        if goal == 0: continue
        paced  = goal * PACING_PCT
        actual = MTD_ALL_REPS[email_key][2] if email_key in MTD_ALL_REPS else 0
        pct_p  = actual / paced if paced else 0
        short  = display_name.split()[0][0] + ". " + display_name.split()[-1]
        if pct_p >= 1.1:
            reps_ahead_l.append((short, studio, pct_p))
        elif pct_p < 0.75:
            reps_behind_l.append((short, studio, pct_p))
    reps_ahead_l.sort(key=lambda x: -x[2])
    reps_behind_l.sort(key=lambda x: x[2])

    def _studio_list(lst, color, fmt):
        return ", ".join(f'<span style="color:{color};font-weight:600">{s}</span> ({fmt(p)})' for s,p in lst[:3])
    def _rep_list(lst, color, fmt):
        return ", ".join(f'<span style="color:{color};font-weight:600">{n} ({st})</span> ({fmt(p)})' for n,st,p in lst[:3])

    # MC% average MTD
    mc_avg_pct = sum(r["mtd_pct"] for r in MC_DATA) / len(MC_DATA) if MC_DATA else 0
    low_mc = sorted(MC_DATA, key=lambda x: x["mtd_pct"])[:2]

    perf_lines = [
        '<div style="font-size:11px;font-weight:700;color:#1e293b;margin-bottom:10px;text-transform:uppercase;letter-spacing:.5px">📊 Sales Team Performance — Why Are We Missing / Achieving Plan?</div>',
        f'<div style="margin-bottom:9px"><span style="font-weight:700;font-size:12px">Yesterday: </span>'
        f'<span style="font-size:12px;color:#334155">{_c(YD_HS_TOTAL)} — <span style="color:{_c2(yd_s_fcst)}">{_s(yd_s_fcst)} {abs(yd_s_fcst):.1f}% {_dir2(yd_s_fcst)}</span> forecast, '
        f'<span style="color:{_c2(yd_s_yoy)}">{_s(yd_s_yoy)} {abs(yd_s_yoy):.1f}% YoY</span>.</span></div>',
        f'<div style="margin-bottom:9px"><span style="font-weight:700;font-size:12px">Last Week (Jun 24–30): </span>'
        f'<span style="font-size:12px;color:#334155">{_c(LW_HS_TOTAL)} — <span style="color:{_c2(lw_s_fcst2)}">{_s(lw_s_fcst2)} {abs(lw_s_fcst2):.1f}% {_dir2(lw_s_fcst2)}</span> forecast, '
        f'<span style="color:{_c2(lw_s_yoy)}">{_s(lw_s_yoy)} {abs(lw_s_yoy):.1f}% YoY</span>.</span></div>',
        f'<div style="margin-bottom:9px"><span style="font-weight:700;font-size:12px">MTD (Jun 1–30): </span>'
        f'<span style="font-size:12px;color:#334155">{_c(MTD_HS_TOTAL)} — <span style="color:{_c2(mtd_s_fcst)}">{_s(mtd_s_fcst)} {abs(mtd_s_fcst):.1f}% {_dir2(mtd_s_fcst)}</span> forecast, '
        f'<span style="color:{_c2(mtd_s_yoy)}">{_s(mtd_s_yoy)} {abs(mtd_s_yoy):.1f}% YoY</span>.</span></div>',
    ]
    if studios_ahead:
        perf_lines.append(
            f'<div style="margin-bottom:7px;font-size:12px;color:#334155">'
            f'<span style="font-weight:700">Pacing ahead (&gt;105%): </span>'
            + _studio_list(studios_ahead, "#16a34a", lambda p: f"{p*100:.0f}%") + '.</div>'
        )
    if studios_behind:
        perf_lines.append(
            f'<div style="margin-bottom:7px;font-size:12px;color:#334155">'
            f'<span style="font-weight:700">Pacing behind (&lt;85%): </span>'
            + _studio_list(studios_behind, "#dc2626", lambda p: f"{p*100:.0f}%") + '.</div>'
        )
    if reps_ahead_l:
        perf_lines.append(
            f'<div style="margin-bottom:7px;font-size:12px;color:#334155">'
            f'<span style="font-weight:700">Top pacing reps (&gt;110%): </span>'
            + _rep_list(reps_ahead_l, "#16a34a", lambda p: f"{p*100:.0f}%") + '.</div>'
        )
    if reps_behind_l:
        perf_lines.append(
            f'<div style="margin-bottom:7px;font-size:12px;color:#334155">'
            f'<span style="font-weight:700">Reps to watch (&lt;75% paced): </span>'
            + _rep_list(reps_behind_l, "#dc2626", lambda p: f"{p*100:.0f}%") + '.</div>'
        )
    if low_mc:
        low_mc_str = ", ".join(f'<span style="color:#dc2626;font-weight:600">{r["name"]}</span> ({r["mtd_pct"]}%)' for r in low_mc)
        perf_lines.append(
            f'<div style="margin-bottom:7px;font-size:12px;color:#334155">'
            f'<span style="font-weight:700">MC% concern: </span>'
            f'Avg team MC rate {mc_avg_pct:.0f}% MTD. Lowest: {low_mc_str}. '
            f'MC=Yes deals convert at 8–16% vs 1–2% without MC — studios below avg should prioritize meaningful contact activities (meetings, warm calls).'
            f'</div>'
        )
    perf_blurb_sec = (
        '<div class="section">'
        '<div style="background:#fefce8;border:1px solid #fde68a;border-left:3px solid #d97706;border-radius:6px;padding:14px 16px">'
        + "".join(perf_lines) + '</div></div>'
    )

    # MTD section
    mtd_yoy = _yoy(MTD_HS_TOTAL, MTD_HS_LY_TOTAL)
    mtd_fcst_d = (MTD_HS_TOTAL - MTD_SALES_FCST) / MTD_SALES_FCST
    mtd_css = "up" if mtd_fcst_d >= 0 else "dn"

    max_mtd_s = max(s["rev"] for s in MTD_BY_STUDIO)
    max_mtd_r = MTD_TOP_REPS[0]["rev"]
    mtd_s_bars = "".join(_horiz_bar(s["name"], s["rev"], max_mtd_s) for s in MTD_BY_STUDIO)
    mtd_r_bars = "".join(_horiz_bar(f'{r["name"]} · {r["studio"]}', r["rev"], max_mtd_r, "#6366f1") for r in MTD_TOP_REPS[:5])

    mtd_net = (
        '<div class="ns-pair">'
        f'<div class="ns-box" style="border-left:3px solid #0d9488">'
        f'<div class="ns-lbl">Net Sales (Snowflake/HubSpot)</div>'
        f'<div class="ns-val">{_c(MTD_HS_TOTAL)}</div>'
        f'<div class="ns-chg">{mtd_yoy}</div>'
        f'</div>'
        f'<div class="ns-box" style="border-left:3px solid {"#16a34a" if mtd_fcst_d>=0 else "#dc2626"}">'
        f'<div class="ns-lbl">vs Forecast</div>'
        f'<div class="ns-val" style="font-size:16px"><span class="{mtd_css}">{"+" if mtd_fcst_d>=0 else ""}{mtd_fcst_d*100:.1f}% v. {_c(MTD_SALES_FCST)} fcst</span></div>'
        f'</div>'
        '</div>'
    )
    pacing_note = (
        f'<p class="note">Pacing: {_pct(PACING_PCT)} of June elapsed through Jun 24 · '
        f'Google Sheet forecast {_c(MTD_SALES_FCST)} MTD. Revenue: Snowflake STG_DEAL (MC=Yes + Closed Won).</p>'
    )

    # Team pacing table
    team_rows = ""
    for studio in sorted(STUDIO_GOALS.keys()):
        goal   = STUDIO_GOALS[studio]
        paced  = goal * PACING_PCT
        actual = next((s["rev"] for s in MTD_BY_STUDIO if s["name"] == studio), 0)
        pct_g  = actual / goal  if goal  else 0
        pct_p  = actual / paced if paced else 0
        team_rows += (
            f'<tr><td>{studio}</td><td>{_c(goal)}</td><td>{_c(paced)}</td>'
            f'<td style="font-weight:700">{_c(actual)}</td>'
            f'<td>{_pct(pct_g)}</td><td>{_paced_bar(pct_p)}</td>'
            f'<td>{_status(pct_p)}</td></tr>'
        )
    team_tbl = (
        '<div class="sub-label">Team % to Paced Goal</div>'
        '<div class="table-wrap"><table><tr><th>Studio</th><th>Jun Goal</th><th>Paced</th>'
        '<th>MTD Actual</th><th>% of Goal</th><th>% Paced</th><th>Status</th></tr>'
        + team_rows + '</table></div>'
    )

    # Individual pacing table — all reps with goals, matched by email key
    rep_rows_data = []
    for email_key, (display_name, studio, goal) in REP_GOALS.items():
        if goal == 0: continue
        paced  = goal * PACING_PCT
        actual = MTD_ALL_REPS[email_key][2] if email_key in MTD_ALL_REPS else 0
        pct_g  = actual / goal  if goal  else 0
        pct_p  = actual / paced if paced else 0
        short  = display_name.split()[0][0] + ". " + display_name.split()[-1]
        rep_rows_data.append((short, studio, goal, paced, actual, pct_g, pct_p))

    rep_rows_data.sort(key=lambda x: -x[6])
    rep_rows = ""
    for short, studio, goal, paced, actual, pct_g, pct_p in rep_rows_data:
        rep_rows += (
            f'<tr><td>{short}</td>'
            f'<td style="color:#64748b;font-size:11px">{studio}</td>'
            f'<td>{_c(goal)}</td><td>{_c(paced)}</td>'
            f'<td style="font-weight:700">{_c(actual)}</td>'
            f'<td>{_pct(pct_g)}</td><td>{_paced_bar(pct_p)}</td>'
            f'<td>{_status(pct_p)}</td></tr>'
        )
    rep_tbl = (
        '<div class="sub-label">Individual % to Paced Goal</div>'
        '<div class="table-wrap"><table><tr><th>Rep</th><th>Studio</th><th>Goal</th><th>Paced</th>'
        '<th>Actual</th><th>% of Goal</th><th>% Paced</th><th>Status</th></tr>'
        + rep_rows + '</table></div>'
    )

    def _note_line(bold, rest):
        return f'<div style="margin-bottom:7px;font-size:12.5px;color:#1e293b;line-height:1.6"><strong>{bold}</strong> {rest}</div>'

    week_notes_html = (
        '<div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:6px;padding:14px 16px;margin-top:12px;margin-bottom:14px">'
        '<div class="sub-label" style="color:#b45309;margin-bottom:10px">📝 Closing Notes — Week of Jun 24–30</div>'
        + _note_line("Best week of the month — $1.32M HS revenue vs $1.08M LY (+23%).", "NY ($149K) and Chicago ($142K) topped week rankings; Denver ($139K) had its strongest week. Anastasia Seminchenko (NY) led all reps at $68K for the week.")
        + _note_line("End-of-Q2 push drove strong daily cadence all 5 days.", "All 13 studios active through the full week. Minneapolis closed June strong with Angela Sunder ($31K) and Zoe Finkelstein ($27K) combining for $58K on the final day.")
        + _note_line("June final: $4.8M HS revenue MTD (+5% vs $4.6M LY).", "Studio-assisted revenue hit $4.8M for June. Denver, NY, Minneapolis, and Chicago all above $400K MTD.")
        + '<div style="margin-top:10px;padding:8px 12px;background:#fff7ed;border-left:3px solid #ea580c;border-radius:3px;font-size:12px;color:#9a3412">'
        '⚠ <strong>Watch:</strong> July pipeline — monitor early July inbound velocity to confirm Q3 momentum isn\'t a pull-forward from month-end urgency.'
        '</div>'
        '</div>'
    )

    # Inbound CVR section — Jun 1-30 TY vs LY
    def _cvr_row(label, ty_n, ty_tot, ly_n, ly_tot):
        ty_pct = ty_n / ty_tot * 100 if ty_tot else 0
        ly_pct = ly_n / ly_tot * 100 if ly_tot else 0
        diff   = ty_pct - ly_pct
        arrow  = "▲" if diff >= 0 else "▼"
        color  = "#16a34a" if diff >= 0 else "#dc2626"
        return (
            f'<tr><td>{label}</td>'
            f'<td>{ty_n:,} / {ty_tot:,}</td><td style="font-weight:600">{ty_pct:.2f}%</td>'
            f'<td>{ly_n:,} / {ly_tot:,}</td><td style="font-weight:600">{ly_pct:.2f}%</td>'
            f'<td><span style="color:{color};font-weight:700">{arrow} {abs(diff):.2f}pp</span></td></tr>'
        )

    cvr_rows = (
        _cvr_row("Order CVR",       557, 5_985, 338, 0) +
        _cvr_row("Closed Won CVR",  654, 5_985, 345, 0)
    )
    inbound_cvr_sec = (
        '<div class="section">'
        '<div class="section-label">📈 Inbound CVR — MTD Jun 1–30 (B2C, apples-to-apples)</div>'
        '<div class="table-wrap"><table>'
        '<tr><th>Metric</th>'
        '<th>2026 (Contacts/Inbound)</th><th>2026 CVR</th>'
        '<th>2025 (Contacts/Inbound)</th><th>2025 CVR</th>'
        '<th>YoY Δ</th></tr>'
        + cvr_rows +
        '</table></div>'
        '<p class="note">Source: STG_DEAL CREATE_DATE × STG_CONTACTS × ORDERS. '
        'Order CVR = contacts who placed an order on/after first inbound in window. '
        'Closed Won CVR = contacts with a deal closed won on/after first inbound in window.</p>'
        '</div>'
    )

    # % Meaningful Contact by studio — MTD vs 90D visual chart
    mc_sorted = sorted(MC_DATA, key=lambda x: x["mtd_pct"], reverse=True)
    mc_avg_mtd = sum(r["mtd_pct"] for r in MC_DATA) / len(MC_DATA)
    max_pct = 80.0  # scale bars to 80%

    mc_bars = f'<div style="padding:4px 0">'
    for r in mc_sorted:
        diff   = r["mtd_pct"] - r["d90_pct"]
        arrow  = "▲" if diff >= 0 else "▼"
        t_color = "#16a34a" if diff >= 0 else "#dc2626"
        # Bar colors: solid = MTD %, outline marker = 90D %
        bar_color = "#6366f1" if r["mtd_pct"] >= mc_avg_mtd else "#94a3b8"
        w_mtd = r["mtd_pct"] / max_pct * 200
        w_90d = r["d90_pct"] / max_pct * 200
        mc_bars += (
            f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:9px">'
            f'<span style="width:105px;font-size:11px;color:#334155;flex-shrink:0">{r["name"]}</span>'
            # bar track
            f'<div style="width:200px;height:16px;background:#f1f5f9;border-radius:3px;position:relative;flex-shrink:0">'
            # MTD fill
            f'<div style="width:{w_mtd:.1f}px;height:100%;background:{bar_color};border-radius:3px;opacity:0.85"></div>'
            # 90D marker line
            f'<div style="position:absolute;top:0;left:{w_90d:.1f}px;width:2px;height:100%;background:#334155;opacity:0.4"></div>'
            f'</div>'
            # MTD %
            f'<span style="font-size:11px;font-weight:700;color:{bar_color};width:36px">{r["mtd_pct"]}%</span>'
            # vs 90D
            f'<span style="font-size:10px;color:{t_color};font-weight:600;width:52px">{arrow} {abs(diff):.1f}pp</span>'
            # MC=Yes CVR
            f'<span style="font-size:10px;color:#64748b">MC CVR: {r["mtd_cvr"]}%</span>'
            f'</div>'
        )
    mc_bars += '</div>'

    mc_legend = (
        f'<div style="display:flex;gap:16px;margin-bottom:8px;flex-wrap:wrap;align-items:center">'
        f'<span style="font-size:10px;color:#64748b">Bar = MTD MC% &nbsp;|&nbsp; Gray tick = 90D baseline</span>'
        f'<span style="display:flex;align-items:center;gap:4px;font-size:10px;color:#334155">'
        f'<span style="width:12px;height:10px;background:#6366f1;border-radius:2px;display:inline-block"></span>≥ avg ({mc_avg_mtd:.0f}%)</span>'
        f'<span style="display:flex;align-items:center;gap:4px;font-size:10px;color:#334155">'
        f'<span style="width:12px;height:10px;background:#94a3b8;border-radius:2px;display:inline-block"></span>&lt; avg</span>'
        f'</div>'
    )

    mc_sec = (
        '<div class="section">'
        '<div class="section-label">🎯 % Meaningful Contact by Studio — MTD vs 90-Day Baseline</div>'
        + mc_legend + mc_bars
        + f'<p class="note">Sorted by MTD MC%. <span style="color:#16a34a">▲</span> = improving vs 90D baseline, '
          f'<span style="color:#dc2626">▼</span> = declining. MC CVR = close rate on MC=Yes deals. '
          f'Non-MC deals convert at ~1–2% vs 8–16% for MC deals.</p>'
        '</div>'
    )

    # By-studio inbound CVR — visual bars (Sales Team tab)
    sorted_cvr  = sorted(STUDIO_MTD_CVR, key=lambda x: -x["cvr"])
    max_cvr     = sorted_cvr[0]["cvr"]
    avg_cvr     = sum(r["cvr"] for r in STUDIO_MTD_CVR) / len(STUDIO_MTD_CVR)
    avg_line_px = int(avg_cvr / max_cvr * 220)  # pixel position of avg line in 220px track

    def _studio_bar_color(cvr, avg):
        if cvr >= avg * 1.15:  return "#16a34a"   # well above avg → green
        if cvr >= avg * 0.85:  return "#0d9488"   # near avg → teal
        return "#dc2626"                           # below avg → red

    s_bars = f'<div style="padding:4px 0;position:relative">'
    for r in sorted_cvr:
        color = _studio_bar_color(r["cvr"], avg_cvr)
        w     = int(r["cvr"] / max_cvr * 220)
        s_bars += (
            f'<div style="display:flex;align-items:center;gap:10px;margin-bottom:8px">'
            f'<span style="width:110px;font-size:11px;color:#334155;flex-shrink:0">{r["studio"]}</span>'
            f'<div style="width:220px;height:16px;background:#f1f5f9;border-radius:3px;position:relative;flex-shrink:0">'
            f'<div style="width:{w}px;height:100%;background:{color};border-radius:3px"></div>'
            f'<div style="position:absolute;top:0;left:{avg_line_px}px;width:2px;height:100%;background:#94a3b8;opacity:0.6"></div>'
            f'</div>'
            f'<span style="font-size:11px;font-weight:700;color:{color};width:38px">{r["cvr"]}%</span>'
            f'<span style="font-size:10px;color:#94a3b8">{r["orders"]}/{r["contacts"]:,}</span>'
            f'</div>'
        )
    s_bars += '</div>'

    studio_cvr_tbl = (
        '<div class="sub-label">Inbound → Order CVR by Studio MTD (Jun 1–30)</div>'
        + s_bars
        + f'<p class="note">Sorted by CVR. Gray line = avg {avg_cvr:.1f}%. '
          f'<span style="color:#16a34a">●</span> well above avg '
          f'<span style="color:#0d9488">●</span> near avg '
          f'<span style="color:#dc2626">●</span> below avg. '
          f'B2C contacts with first inbound Jun 1–21 who ordered on/after first contact.</p>'
    )

    mtd_sec = (
        '<div class="section">'
        '<div class="section-label">📊 MTD — Jun 1–24</div>'
        + mtd_net + pacing_note
        + week_notes_html
        + '<div class="two-col">'
        + f'<div><div class="sub-label">Top 5 Individuals</div>{mtd_r_bars}</div>'
        + f'<div><div class="sub-label">All Studios</div>{mtd_s_bars}</div>'
        + '</div>'
        + studio_cvr_tbl + mc_sec + team_tbl + rep_tbl + '</div>'
    )

    return f"""
<div class="page-label">Interior Define · Sales Team · Tue Jun 30, 2026</div>
<div class="email-wrap">
  <div class="hdr">
    <div class="hdr-brand">Interior Define · Sales Team</div>
    <div class="hdr-meta">Tue Jun 30, 2026 · Revenue: Snowflake STG_DEAL (MC=Yes + Closed Won)</div>
  </div>
  {yd_sec}
  {lw_sec}
  {perf_blurb_sec}
  {mtd_sec}
  {activities_sec}
  <div class="footer">Revenue: Snowflake STG_DEAL (MC=Yes + Closed Won) · Pacing: Google Sheet</div>
</div>"""


# ── Assemble & write ──────────────────────────────────────────────────────────

html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Interior Define — Daily Business Review · Tue Jun 30</title>
<style>{CSS}</style>
</head>
<body>
<input type="radio" name="tab" id="tab-biz" class="tab-radio" checked>
<input type="radio" name="tab" id="tab-sales" class="tab-radio">
<div class="tab-shell">
  <div class="tab-bar">
    <label for="tab-biz">📊 Total Business</label>
    <label for="tab-sales">👥 Sales Team</label>
  </div>
  <div class="tab-content" id="content-biz">{tab1()}</div>
  <div class="tab-content" id="content-sales">{tab2()}</div>
</div>
</body>
</html>"""

os.makedirs("output", exist_ok=True)
for path in ["output/report.html", "output/report-2026-06-30.html"]:
    with open(path, "w") as f:
        f.write(html)
    print(f"[ok] {path}", file=sys.stderr)

# ── GitHub Pages delivery ─────────────────────────────────────────────────────

_GH_TOKEN      = os.getenv("GITHUB_PAT", "")
_GH_REPO       = "maryspreck-star/id-daily-business-review"
_PAGE_URL      = "https://maryspreck-star.github.io/id-daily-business-review/"
_SLACK_TOKEN   = os.getenv("SLACK_BOT_TOKEN", "")
_SLACK_CHANNEL = "C05CJH674S3"  # #salesoperations

def _push_to_pages(html_str, date_label):
    encoded = base64.b64encode(html_str.encode()).decode()
    hdrs = {"Authorization": f"token {_GH_TOKEN}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json"}
    r = requests.get(f"https://api.github.com/repos/{_GH_REPO}/contents/index.html",
                     headers=hdrs, params={"ref": "gh-pages"})
    body = {"message": f"Report {date_label}", "content": encoded, "branch": "gh-pages"}
    if r.ok:
        body["sha"] = r.json()["sha"]
    r2 = requests.put(f"https://api.github.com/repos/{_GH_REPO}/contents/index.html",
                      headers=hdrs, json=body)
    if r2.ok:
        print(f"[ok] Published to {_PAGE_URL}", file=sys.stderr)
        return _PAGE_URL
    print(f"[warn] GitHub Pages push failed: {r2.status_code} {r2.text[:200]}", file=sys.stderr)
    return None

def _post_slack_link(page_url, subject):
    r = requests.post("https://slack.com/api/chat.postMessage",
        headers={"Authorization": f"Bearer {_SLACK_TOKEN}", "Content-Type": "application/json"},
        json={"channel": _SLACK_CHANNEL,
              "text": f"📊 *{subject}*\n<{page_url}|View Report →>"})
    if r.json().get("ok"):
        print("[ok] Slack link posted to #salesoperations", file=sys.stderr)
    else:
        print(f"[warn] Slack post failed: {r.json().get('error')}", file=sys.stderr)

_today_label = datetime.date.today().strftime("%a %b %-d, %Y")
_subject     = f"Interior Define Daily Business Review — {_today_label}"
_page        = _push_to_pages(html, _today_label)
if _page:
    _post_slack_link(_page, _subject)

# ── PDF generation ────────────────────────────────────────────────────────────

REPO = pathlib.Path(__file__).parent.parent
HTML_PATH = (REPO / "output" / "report.html").resolve()
PDF_PATH  = (REPO / "output" / "report.pdf").resolve()

async def _gen_pdf():
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        b = await p.chromium.launch()
        pg = await b.new_page()
        await pg.goto(f"file://{HTML_PATH}")
        await pg.wait_for_load_state("networkidle")
        await pg.pdf(path=str(PDF_PATH), format="A4", print_background=True,
            margin={"top":"10mm","bottom":"10mm","left":"8mm","right":"8mm"})
        await b.close()

asyncio.run(_gen_pdf())
print(f"[ok] {PDF_PATH}", file=sys.stderr)

# ── Email delivery ────────────────────────────────────────────────────────────

SENDGRID_KEY = os.getenv("SENDGRID_API_KEY", "")
EMAIL_TO     = os.getenv("EMAIL_TO",   "mary.spreck@interiordefine.com")
EMAIL_FROM   = os.getenv("EMAIL_FROM", "reports@interiordefine.com")

if SENDGRID_KEY:
    # Upload PDF for attachment link
    upload = requests.post(
        "https://catbox.moe/user/api.php",
        data={"reqtype": "fileupload"},
        files={"fileToUpload": ("report.pdf", open(PDF_PATH, "rb"), "application/pdf")},
        timeout=30,
    )
    pdf_url = upload.text.strip()

    send_date = datetime.date.today().strftime("%A, %B %-d, %Y")
    body_html = f"""<p>Report for {send_date}.</p>
<p style="margin:16px 0">
  <a href="{pdf_url}" style="background:#6366f1;color:#fff;padding:10px 20px;border-radius:5px;text-decoration:none;font-weight:600;font-size:14px">Download PDF</a>
</p>"""

    resp = requests.post(
        "https://api.sendgrid.com/v3/mail/send",
        headers={"Authorization": f"Bearer {SENDGRID_KEY}", "Content-Type": "application/json"},
        json={
            "personalizations": [{"to": [{"email": EMAIL_TO}]}],
            "from": {"email": EMAIL_FROM},
            "subject": "ID Monday Business Report",
            "content": [{"type": "text/html", "value": body_html}],
        },
        timeout=15,
    )
    if resp.status_code == 202:
        print(f"[ok] email sent to {EMAIL_TO}", file=sys.stderr)
    else:
        print(f"[warn] email failed: {resp.status_code} {resp.text}", file=sys.stderr)
else:
    print("[skip] SENDGRID_API_KEY not set — email not sent", file=sys.stderr)
