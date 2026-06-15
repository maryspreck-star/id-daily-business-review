"""Generate today's report using Snowflake STG_DEAL for Sales Team revenue.
All data pulled via MCP queries on 2026-06-14. Report date = 2026-06-13 (Saturday).
Run: source venv/bin/activate && python scripts/run_from_mcp.py
"""
import os, sys
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


# ── DATA — Total Business tab validated against Looker dashboard 1156 ─────────

# Yesterday Jun 14, 2026 (Sunday) — Snowflake
YD_B2C_REV, YD_B2C_ORD = 82_413.00, 31
YD_TR_REV,  YD_TR_ORD  =  4_869.25,  2
YD_HV_REV,  YD_HV_ORD  =      0.00,  0
YD_TOT_REV, YD_TOT_ORD = 87_282.25, 33
YD_BLENDED_AOV = 2_747.23   # Looker calendar pivot Jun 14
YD_B2C_AOV     = 2_761.30
YD_TR_AOV      = 2_529.22
YD_ASSISTED_REV = 42_088.75   # MC=Yes revenue STG_DEAL Jun 14
YD_INBOUND, YD_INBOUND_LY     = 196, 189
MTD_INBOUND, MTD_INBOUND_LY  = 2_784, 2_703   # LY updated to Jun 1-14, 2025
YD_FCST_SNOWFLAKE   = 106_453
YD_REV_FOR_FCST     = 87_282.25
MTD_REV_FOR_FCST    = 2_840_142.07

# Yesterday LY Jun 14, 2025
YD_B2C_REV_LY, YD_B2C_ORD_LY = 123_737.70, 40
YD_TR_REV_LY,  YD_TR_ORD_LY  =   7_415.50,  2
YD_HV_REV_LY                  =   6_232.00
YD_TOT_REV_LY, YD_TOT_ORD_LY = 137_385.20, 45
YD_BLENDED_AOV_LY = 3_170.63   # Looker orders.average_order_value Jun 14 2025
YD_B2C_AOV_LY     = 3_212.67
YD_TR_AOV_LY      = 3_861.51

# MTD Jun 1-14, 2026 — Snowflake
MTD_B2C_REV, MTD_B2C_ORD = 2_022_392.89, 766
MTD_TR_REV,  MTD_TR_ORD  =   593_376.44, 210
MTD_HV_REV,  MTD_HV_ORD  =   122_055.25,  49
MTD_B2B_REV, MTD_B2B_ORD =    92_175.49,  23
MTD_TOT_REV, MTD_TOT_ORD = 2_830_000.07, 1_048
MTD_BLENDED_AOV = 2_800.90   # Looker calendar pivot
MTD_B2C_AOV     = 2_741.45
MTD_TR_AOV      = 2_925.42
MTD_REPEAT_PCT  = 327 / 965
MTD_ASSISTED_REV = 1_962_140.21   # Looker MC=Yes revenue Jun 1-14
MTD_SNOWFLAKE_FCST = 3_440_943

# MTD LY Jun 1-14, 2025 — Snowflake
MTD_B2C_REV_LY = 2_151_597.62;  MTD_B2C_ORD_LY = 802
MTD_TR_REV_LY  =   488_485.60;  MTD_TR_ORD_LY  = 179
MTD_HV_REV_LY  =   165_950.99;  MTD_HV_ORD_LY  =  65
MTD_B2B_REV_LY =    36_436.75;  MTD_B2B_ORD_LY =  10
MTD_TOT_REV_LY  = 2_861_246.71
MTD_TOT_ORD_LY  = 1_063

MTD_BLENDED_AOV_LY = 2_789.66   # Looker calendar pivot LY
MTD_B2C_AOV_LY     = 2_785.24
MTD_TR_AOV_LY      = 2_825.20

# Swatch — Jun 1-14
SW_MTD_ORD,  SW_MTD_CUST  = 4_900, 4_269   # Looker Jun 1-14
SW_LY_ORD,   SW_LY_CUST   = 4_284, 3_675   # Looker Jun 1-14, 2025

# Merch — Looker (same validated query as last night, updated to Jun 1-14)
MERCH = [
    {"cat": "Sectionals",    "rev":  880_541.75, "units": 253, "aur": 3_480},
    {"cat": "Sofas",         "rev":  580_888.30, "units": 289, "aur": 2_010},
    {"cat": "Chairs",        "rev":  342_603.25, "units": 330, "aur": 1_038},
    {"cat": "Dining Seating","rev":  257_216.25, "units": 448, "aur":   574},
    {"cat": "Beds",          "rev":  155_595.25, "units":  79, "aur": 1_970},
    {"cat": "Ottomans",      "rev":   92_701.25, "units": 160, "aur":   579},
    {"cat": "Benches",       "rev":   31_748.50, "units":  46, "aur":   690},
    {"cat": "Accent Tables", "rev":    7_166.25, "units":   7, "aur": 1_024},
    {"cat": "Pillows",       "rev":    6_992.25, "units": 129, "aur":    54},
]
MERCH_TOTAL = 2_366_516.05  # Looker total (incl Rugs, Art, Dining Tables, Lighting)

# Studio revenue — Looker (hubspot_deals.studio_name, same validated method, Jun 1-14)
TOTAL_INBOUND = 5_526
STUDIOS_ORDERS = [
    {"name":"New York",      "rev":263_844.32,"orders":89,"inbound":735,"won":30},
    {"name":"Dallas",        "rev":206_943.08,"orders":64,"inbound":471,"won":34},
    {"name":"Minneapolis",   "rev":179_265.41,"orders":56,"inbound":492,"won":26},
    {"name":"Washington DC", "rev":177_295.69,"orders":62,"inbound":415,"won":32},
    {"name":"Chicago",       "rev":175_825.16,"orders":56,"inbound":526,"won":26},
    {"name":"Seattle",       "rev":173_642.19,"orders":56,"inbound":459,"won":24},
    {"name":"Denver",        "rev":169_388.95,"orders":53,"inbound":363,"won":25},
    {"name":"Charlotte",     "rev":165_261.25,"orders":52,"inbound":369,"won":21},
    {"name":"Boston",        "rev":161_886.97,"orders":57,"inbound":391,"won":19},
    {"name":"Los Angeles",   "rev":156_821.09,"orders":50,"inbound":434,"won":20},
    {"name":"San Francisco", "rev":127_283.49,"orders":49,"inbound":311,"won":24},
    {"name":"Baltimore",     "rev": 90_533.24,"orders":26,"inbound":270,"won": 7},
    {"name":"Philadelphia",  "rev": 74_308.50,"orders":28,"inbound":290,"won":10},
]
STUDIO_TOT_REV = sum(s["rev"] for s in STUDIOS_ORDERS)

# Studio inbound CVR MTD Jun 1-14 (sorted by CVR desc)
STUDIO_MTD_CVR = [
    {"studio": "San Francisco", "contacts": 130, "orders": 15, "cvr": 11.54},
    {"studio": "Charlotte",     "contacts": 121, "orders": 11, "cvr":  9.09},
    {"studio": "Denver",        "contacts": 172, "orders": 15, "cvr":  8.72},
    {"studio": "Dallas",        "contacts": 185, "orders": 16, "cvr":  8.65},
    {"studio": "Los Angeles",   "contacts": 204, "orders": 16, "cvr":  7.84},
    {"studio": "Washington DC", "contacts": 180, "orders": 14, "cvr":  7.78},
    {"studio": "Boston",        "contacts": 172, "orders": 13, "cvr":  7.56},
    {"studio": "Philadelphia",  "contacts": 149, "orders": 10, "cvr":  6.71},
    {"studio": "Chicago",       "contacts": 227, "orders": 15, "cvr":  6.61},
    {"studio": "New York",      "contacts": 337, "orders": 22, "cvr":  6.53},
    {"studio": "Seattle",       "contacts": 246, "orders": 16, "cvr":  6.50},
    {"studio": "Minneapolis",   "contacts": 199, "orders": 12, "cvr":  6.03},
    {"studio": "Baltimore",     "contacts": 132, "orders":  6, "cvr":  4.55},
]

# % Meaningful Contact by studio — MTD Jun 1-14 and last 90 days
MC_DATA = [
    {"name":"New York",      "mtd_tot":735, "mtd_mc":321, "mtd_pct":43.7, "mtd_cvr":7.8,  "no_cvr":1.7, "d90_pct":52.2, "d90_cvr":22.5},
    {"name":"Chicago",       "mtd_tot":526, "mtd_mc":252, "mtd_pct":47.9, "mtd_cvr":9.5,  "no_cvr":0.7, "d90_pct":51.0, "d90_cvr":25.4},
    {"name":"Minneapolis",   "mtd_tot":492, "mtd_mc":287, "mtd_pct":58.3, "mtd_cvr":8.0,  "no_cvr":2.0, "d90_pct":68.2, "d90_cvr":19.1},
    {"name":"Dallas",        "mtd_tot":471, "mtd_mc":271, "mtd_pct":57.5, "mtd_cvr":11.4, "no_cvr":2.0, "d90_pct":53.5, "d90_cvr":24.5},
    {"name":"Seattle",       "mtd_tot":459, "mtd_mc":222, "mtd_pct":48.4, "mtd_cvr":9.9,  "no_cvr":1.3, "d90_pct":54.1, "d90_cvr":23.9},
    {"name":"Los Angeles",   "mtd_tot":434, "mtd_mc":212, "mtd_pct":48.8, "mtd_cvr":8.5,  "no_cvr":0.9, "d90_pct":61.9, "d90_cvr":17.9},
    {"name":"Washington DC", "mtd_tot":415, "mtd_mc":218, "mtd_pct":52.5, "mtd_cvr":13.8, "no_cvr":1.0, "d90_pct":48.3, "d90_cvr":27.9},
    {"name":"Boston",        "mtd_tot":391, "mtd_mc":192, "mtd_pct":49.1, "mtd_cvr":8.9,  "no_cvr":1.5, "d90_pct":61.8, "d90_cvr":21.3},
    {"name":"Charlotte",     "mtd_tot":369, "mtd_mc":164, "mtd_pct":44.4, "mtd_cvr":11.0, "no_cvr":1.5, "d90_pct":40.5, "d90_cvr":27.2},
    {"name":"Denver",        "mtd_tot":363, "mtd_mc":159, "mtd_pct":43.8, "mtd_cvr":13.8, "no_cvr":2.0, "d90_pct":49.0, "d90_cvr":26.4},
    {"name":"San Francisco", "mtd_tot":311, "mtd_mc":147, "mtd_pct":47.3, "mtd_cvr":15.0, "no_cvr":1.8, "d90_pct":45.7, "d90_cvr":24.9},
    {"name":"Philadelphia",  "mtd_tot":290, "mtd_mc":129, "mtd_pct":44.5, "mtd_cvr":7.8,  "no_cvr":0.0, "d90_pct":52.8, "d90_cvr":21.3},
    {"name":"Baltimore",     "mtd_tot":270, "mtd_mc":154, "mtd_pct":57.0, "mtd_cvr":4.5,  "no_cvr":0.0, "d90_pct":73.4, "d90_cvr":17.4},
]

# Deal CVR — computed from MC_DATA (closed_won / total_deals) MTD Jun 1-14 and 90D
MTD_CVR = {
    "Washington DC": 0.0773, "San Francisco": 0.0807, "Dallas":       0.0741,
    "Denver":        0.0716, "Charlotte":     0.0572, "Minneapolis":  0.0551,
    "Seattle":       0.0547, "Boston":        0.0514, "Los Angeles":  0.0461,
    "Chicago":       0.0491, "New York":      0.0435, "Philadelphia": 0.0348,
    "Baltimore":     0.0256,
}
NINETY_DAY_CVR = {
    "Washington DC": 0.1555, "Dallas":        0.1520, "Denver":       0.1466,
    "Minneapolis":   0.1464, "Chicago":       0.1451, "Seattle":      0.1450,
    "Boston":        0.1437, "San Francisco": 0.1371, "New York":     0.1366,
    "Charlotte":     0.1363, "Baltimore":     0.1368, "Los Angeles":  0.1233,
    "Philadelphia":  0.1215,
}

# ── Snowflake STG_DEAL — Sales Team tab ──────────────────────────────────────

# Yesterday (Jun 14, 2026) by studio — STG_DEAL MC=Yes
YD_BY_STUDIO = [
    {"name": "Chicago",       "rev": 12_096.50},
    {"name": "Philadelphia",  "rev":  8_112.00},
    {"name": "Seattle",       "rev":  6_037.25},
    {"name": "New York",      "rev":  4_152.00},
    {"name": "Boston",        "rev":  3_450.00},
    {"name": "Minneapolis",   "rev":  2_744.00},
    {"name": "San Francisco", "rev":  1_912.50},
    {"name": "Baltimore",     "rev":  1_292.00},
    {"name": "Dallas",        "rev":  1_207.50},
    {"name": "Los Angeles",   "rev":  1_085.00},
]
YD_HS_TOTAL    = 42_088.75
YD_HS_LY_TOTAL = 0.0  # Jun 14 2025 — no MC=Yes closes

# Yesterday top reps — STG_DEAL MC=Yes Jun 14
YD_TOP_REPS = [
    {"name": "Kagen Haberstick",  "studio": "Philadelphia", "rev":  8_112.00},
    {"name": "Kristen Rosario",   "studio": "Chicago",      "rev":  4_811.00},
    {"name": "Jamie Williams",    "studio": "New York",     "rev":  4_152.00},
    {"name": "Sean Steele",       "studio": "Chicago",      "rev":  3_843.00},
    {"name": "Heaven Chartier",   "studio": "Boston",       "rev":  3_450.00},
]

# MTD (Jun 1-14) by studio — STG_DEAL MC=Yes, IS_CONVERTED=TRUE
MTD_BY_STUDIO = [
    {"name": "New York",      "rev": 210_253.57},
    {"name": "Dallas",        "rev": 184_898.08},
    {"name": "Washington DC", "rev": 165_701.94},
    {"name": "Chicago",       "rev": 151_908.66},
    {"name": "Minneapolis",   "rev": 147_997.41},
    {"name": "Denver",        "rev": 147_843.52},
    {"name": "Seattle",       "rev": 147_151.99},
    {"name": "Charlotte",     "rev": 131_823.25},
    {"name": "Los Angeles",   "rev": 131_505.34},
    {"name": "Boston",        "rev": 128_511.97},
    {"name": "San Francisco", "rev": 114_485.49},
    {"name": "Baltimore",     "rev":  85_468.49},
    {"name": "Philadelphia",  "rev":  64_623.75},
]
MTD_HS_TOTAL = 1_786_366.71  # HubSpot dashboard Jun 1-14 (MC=Yes + Closed Won)

# MTD LY (Jun 1-13, 2025) — HubSpot API (same filters, same methodology)
MTD_LY_BY_STUDIO = {
    "Boston":        170_319.63, "New York":       169_047.25,
    "Minneapolis":    98_869.51, "San Francisco":   92_644.23,
    "Seattle":        89_446.76, "Denver":          62_544.20,
    "Washington DC":  61_565.00, "Baltimore":       58_268.68,
    "Chicago":        47_043.75, "Los Angeles":     28_977.70,
    "Charlotte":      15_656.75, "Philadelphia":    13_921.38,
    "Dallas":              0.00,  # no closed-won deals Jun 1-13, 2025
}
MTD_HS_LY_TOTAL = 1_468_895.08  # Snowflake pre-Aug methodology (stage dates, Jun 1-14 2025)

# MTD all reps (Jun 1-13) — exact from HubSpot API (MC=Yes + Closed Won + studio team)
# email_prefix: (display_name, studio, revenue)
MTD_ALL_REPS = {
    "jasmyne.boles":        ("Jasmyne Boles",        "Dallas",        112_329.58),
    "vaughan.hazeldine":    ("Vaughan Hazeldine",    "Charlotte",      88_747.50),
    "anastasia.seminchenko":("Anastasia Seminchenko","New York",       88_464.24),
    "sydney.stetzel":       ("Sydney Stetzel",       "Denver",         83_448.73),
    "shawn.neifert":        ("Shawn Neifert",        "Washington DC",  70_033.72),
    "brynn.cohune":         ("Brynn Cohune",         "Boston",         57_363.22),
    "sean.steele":          ("Sean Steele",          "Chicago",        56_588.75),
    "brittany.herrera":     ("Brittany Herrera",     "Denver",         49_270.79),
    "rachel.kivo":          ("Rachel Kivo",          "San Francisco",  48_086.48),
    "luz.rivera":           ("Lucy Rivera",          "Minneapolis",    48_002.73),
    "richard.boone":        ("Richard Boone",        "Los Angeles",    45_902.45),
    "nikolaus.pollutra":    ("Nikolaus Pollutra",    "Baltimore",      45_579.00),
    "julie.alfonso":        ("Jules Alfonso",        "Charlotte",      44_812.00),
    "sameera.tanveer":      ("Sameera Tanveer",      "Washington DC",  44_427.98),
    "angela.sunder":        ("Angela Sunder",        "Minneapolis",    44_015.75),
    "maico.vergara":        ("Maico Vergara",        "Washington DC",  41_149.74),
    "zoe.finkelstein":      ("Zoe Finkelstein",      "Minneapolis",    39_387.70),
    "kaylee.krostag":       ("Kaylee Krostag",       "Chicago",        42_526.17),
    "mouny.alfraik":        ("Mouny Alfraik",        "New York",       38_034.00),
    "victoria.correa":      ("Victoria Correa",      "Dallas",         37_396.25),
    "kristen.rosario":      ("Kristen Rosario",      "Chicago",        39_838.25),
    "lindsay.reyna":        ("Lindsay Reyna",        "Seattle",        34_246.96),
    "jose.macario":         ("Jose Marcario",        "Minneapolis",    34_138.22),
    "ashanti.gillespie":    ("Ashanti Gillespie",    "Baltimore",      34_073.75),
    "kai.davies":           ("Kai Davies",           "Seattle",        32_894.50),
    "david.mckeever":       ("David McKeever",       "Los Angeles",    32_357.72),
    "mary.langridge":       ("Mary Langridge",       "San Francisco",  32_131.00),
    "lauren.shull":         ("Lauren Shull",         "New York",       31_402.50),
    "alex.wray":            ("Alex Wray",            "Seattle",        31_386.53),
    "abby.keane":           ("Abby Keane",           "Boston",         30_963.50),
    "laurel.clark":         ("Laurel Clark",         "Philadelphia",   30_489.00),
    "ibtesam.chowdhury":    ("Ibtesam Chowdhury",   "New York",       30_352.83),
    "sarah.dreier":         ("Sarah Dreier",         "Los Angeles",    44_366.19),
    "amira.seale":          ("Amira Seale",          "San Francisco",  27_415.50),
    "eric.sorensen":        ("Eric Sorensen",        "Boston",         26_720.75),
    "robyn.yannoukos":      ("Robyn Yann",           "Denver",         25_211.50),
    "nick.pagdilao":        ("Nick Pagdilao",        "Los Angeles",    24_549.72),
    "laura.tulloch":        ("Laura Tulloch",        "Seattle",        23_747.49),
    "emily.nunn":           ("Emily Nunn",           "Dallas",         22_610.25),
    "rachel.roth":          ("Rachel Roth",          "Seattle",        19_296.50),
    "robert.perez":         ("Robert Perez",         "New York",       18_927.50),
    "kagen.haberstick":     ("Kagen Haberstick",     "Philadelphia",   16_511.25),
    "brandi.davis":         ("Brandi Davis",         "Chicago",        15_714.74),
    "heaven.chartier":      ("Heaven Chartier",      "Boston",         14_361.50),
    "jamie.williams":       ("Jamie Williams",       "New York",       13_897.25),
    "olga.pushina":         ("Olga Pushina",         "Baltimore",      13_783.49),
    "jenee.satterwhite":    ("Jenee Satterwhite",    "Philadelphia",   12_985.75),
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
    "2026-06-13":  96_411, "2026-06-14":  62_254,
}
FULL_MO_FCST   = 5_177_028
MTD_SALES_FCST = sum(DAILY_FCST.values())   # $2,012,265
YD_SALES_FCST  = DAILY_FCST["2026-06-14"]  # $62,254
PACING_PCT     = MTD_SALES_FCST / FULL_MO_FCST  # 38.87%

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
    "amira.seale":          ("Amira Seale",          "San Francisco",  13_000),
    "mary.langridge":       ("Mary Langridge",       "San Francisco", 138_000),
    "rachel.kivo":          ("Rachel Kivo",          "San Francisco", 138_000),
    "alex.wray":            ("Alex Wray",            "Seattle",        83_000),
    "kai.davies":           ("Kai Davies",           "Seattle",        92_000),
    "laura.tulloch":        ("Laura Tulloch",        "Seattle",        83_000),
    "lindsay.reyna":        ("Lindsay Reyna",        "Seattle",        83_000),
    "rachel.roth":          ("Rachel Roth",          "Seattle",        83_000),
    "maico.vergara":        ("Maico Vergara",        "Washington DC", 107_000),
    "sameera.tanveer":      ("Sameera Tanveer",      "Washington DC", 107_000),
    "shawn.neifert":        ("Shawn Neifert",        "Washington DC", 117_000),
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
    {"month": "Jun 2026*","contacts": 2_639, "d14":  6.82, "d30":  6.82, "d60":  6.82, "d90":  6.82},
]

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
    merch = '<div class="sub-label">Merch Contribution (Merchandise · MTO + QS)</div>'
    for m in MERCH[:9]:
        merch += _merch_bar(m["cat"], m["rev"], m["units"], m["aur"], MERCH_TOTAL)
    yd_sec = (
        '<div class="section">'
        '<div class="section-label">📈 Yesterday — Sun Jun 14</div>'
        + row1 + row2 + segs + merch + '</div>'
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
        aov       = s["rev"] / s["orders"] if s["orders"] else 0
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
        '<div class="section-label">📅 MTD — Jun 1–14 · Forecast: Looker/Snowflake</div>'
        + mtd_row1 + mtd_row2 + mtd_segs + swatches + mtd_merch + studio_tbl + '</div>'
    )

    cvr_sec = (
        '<div class="section">'
        '<div class="section-label">📈 Inbound CVR Trend — 2026 Monthly Cohorts</div>'
        + monthly_cvr_tbl + '</div>'
    )

    return f"""
<div class="page-label">Interior Define · Total Business · Sun Jun 14, 2026</div>
<div class="email-wrap">
  <div class="hdr">
    <div class="hdr-brand">Interior Define <span class="hdr-badge">Total Business</span></div>
    <div class="hdr-meta">Daily Business Review · Sun Jun 14, 2026 · Forecast source: Looker (ID_FORECASTED_ADJUSTED_GROSS_BOOKINGS)</div>
  </div>
  {yd_sec}
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
        '<div class="sub-label" style="color:#b45309;margin-bottom:10px">📝 Closing Notes — Sun Jun 14</div>'
        + _nl("Light traffic system-wide.", "World Cup events and Camden Commons closure (Charlotte) kept foot traffic down. Most studios described it as slower than a typical Saturday — but high-intent walk-ins continued.")
        + _nl("NYC led in revenue ($14.6K)", "despite slow traffic. No pushback on 16-week lead times. WDC strong with 8 walk-ins, multiple Havenly clients engaged on Ella, Scarlett, and Tatum.")
        + _nl("Dallas ($3.7K) and Chicago ($3.8K)", "had productive days with re-engagements and trade assists. Charlotte hit 39% MTD to goal after today. Minneapolis team generated 11 new leads with $0 sales — clients explicitly waiting for sale.")
        + _nl("Pipeline primed for Jun 15 early access.", "Multiple studios reporting quotes prepped and clients ready to close once the promo code drops. LA noted a notable design consultation (Anna Kendrick visited the showroom).")
        + '<div style="margin-top:10px;padding:8px 12px;background:#fff7ed;border-left:3px solid #ea580c;border-radius:3px;font-size:12px;color:#9a3412">'
        '⚠ <strong>Watch:</strong> CX escalations accelerating — Seattle client threatening "fraudulent lead-time marketing" language; Charlotte had escalated 1-star review call; Boston flagged multiple extended lead-time tickets. Website checkout failures also reported across LA and other studios.'
        '</div>'
        '</div>'
    )

    yd_sec = (
        '<div class="section">'
        '<div class="section-label">📈 Yesterday — Sun Jun 14</div>'
        + yd_net
        + '<div class="two-col">'
        + f'<div><div class="sub-label">Top 5 Studios</div>{yd_s_bars}</div>'
        + f'<div><div class="sub-label">Top 5 Individuals</div>{yd_r_bars}</div>'
        + '</div>'
        + yd_notes
        + '</div>'
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
        f'<p class="note">Pacing: {_pct(PACING_PCT)} of June elapsed through Jun 13 · '
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
        '<div class="sub-label" style="color:#b45309;margin-bottom:10px">📝 Closing Notes — Week of Jun 8–12</div>'
        + _note_line("Post-promo slowdown across all studios.", "Traffic pulled back sharply after the Weekender sale ended. Teams report clients actively waiting for the next promo (Jun 15 early access) before committing.")
        + _note_line("CX escalations at elevated volume.", "Widespread delays on Presidents&rsquo; Day orders (Feb–Mar) driving inbound calls. Teams quoting 10–16 week lead times. Website checkout issues also flagged by multiple studios.")
        + _note_line("Pipeline primed for Jun 15 sale.", "All studios sent swatchee sequences and SMS outreach mid-week. Charlotte (Vaughan: $22K single day), Denver (trade closes), and Dallas (Jasmyne) posted standout individual days.")
        + _note_line("Trade active.", "Multiple studios noting trade inquiries and closures — WDC, Denver, SF, Dallas, and Minneapolis all had trade activity this week.")
        + '<div style="margin-top:10px;padding:8px 12px;background:#fff7ed;border-left:3px solid #ea580c;border-radius:3px;font-size:12px;color:#9a3412">'
        '⚠ <strong>Watch:</strong> CX + delivery complaints elevated all week — Metropolitan delays and order status calls flagged across Dallas, Charlotte, Philadelphia, Boston, NYC, and LA.'
        '</div>'
        '</div>'
    )

    # Inbound CVR section — id-inbound-cvr skill, Jun 1-13 TY vs LY
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
        _cvr_row("Order CVR",       177, 2_639, 202, 2_574) +
        _cvr_row("Closed Won CVR",  206, 2_639, 204, 2_574)
    )
    inbound_cvr_sec = (
        '<div class="section">'
        '<div class="section-label">📈 Inbound CVR — MTD Jun 1–14 (B2C, apples-to-apples)</div>'
        '<div class="table-wrap"><table>'
        '<tr><th>Metric</th>'
        '<th>2026 (Contacts/Inbound)</th><th>2026 CVR</th>'
        '<th>2025 (Contacts/Inbound)</th><th>2025 CVR</th>'
        '<th>YoY Δ</th></tr>'
        + cvr_rows +
        '</table></div>'
        '<p class="note">Source: STG_HUBSPOT_ENGAGEMENTS_BASE × STG_CONTACTS × STG_DEAL. '
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
        '<div class="sub-label">Inbound → Order CVR by Studio MTD (Jun 1–14)</div>'
        + s_bars
        + f'<p class="note">Sorted by CVR. Gray line = avg {avg_cvr:.1f}%. '
          f'<span style="color:#16a34a">●</span> well above avg '
          f'<span style="color:#0d9488">●</span> near avg '
          f'<span style="color:#dc2626">●</span> below avg. '
          f'B2C contacts with first inbound Jun 1–14 who ordered on/after first contact.</p>'
    )

    mtd_sec = (
        '<div class="section">'
        '<div class="section-label">📊 MTD — Jun 1–14</div>'
        + mtd_net + pacing_note
        + week_notes_html
        + '<div class="two-col">'
        + f'<div><div class="sub-label">Top 5 Individuals</div>{mtd_r_bars}</div>'
        + f'<div><div class="sub-label">All Studios</div>{mtd_s_bars}</div>'
        + '</div>'
        + studio_cvr_tbl + mc_sec + team_tbl + rep_tbl + '</div>'
    )

    return f"""
<div class="page-label">Interior Define · Sales Team · Sun Jun 14, 2026</div>
<div class="email-wrap">
  <div class="hdr">
    <div class="hdr-brand">Interior Define · Sales Team</div>
    <div class="hdr-meta">Sun Jun 14, 2026 · Revenue: Snowflake STG_DEAL (MC=Yes + Closed Won)</div>
  </div>
  {yd_sec}
  {mtd_sec}
  <div class="footer">Revenue: Snowflake STG_DEAL (MC=Yes + Closed Won) · Pacing: Google Sheet</div>
</div>"""


# ── Assemble & write ──────────────────────────────────────────────────────────

html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Interior Define — Daily Business Review · Sun Jun 14</title>
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
for path in ["output/report.html", "output/report-2026-06-13.html"]:
    with open(path, "w") as f:
        f.write(html)
    print(f"[ok] {path}", file=sys.stderr)
