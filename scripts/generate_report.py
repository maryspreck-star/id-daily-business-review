"""Standalone report generator — reads /tmp/id/data.json, writes /tmp/id/report.html.
No GitHub push, Slack post, PDF generation, or email. No external path imports.
"""
import json
import datetime
import os
import math

# ── Load data ─────────────────────────────────────────────────────────────────

with open("/tmp/id/data.json") as _f:
    d = json.load(_f)

dates = d["dates"]

# ── Date labels ───────────────────────────────────────────────────────────────

yd_dt       = datetime.date.fromisoformat(dates["yd"])
mo_start_dt = datetime.date.fromisoformat(dates["mo_start"])
lw_start_dt = datetime.date.fromisoformat(dates["lw_start"])
lw_end_dt   = datetime.date.fromisoformat(dates["lw_end"])

yd_label      = yd_dt.strftime("%-d")                      # "30"
yd_dow        = yd_dt.strftime("%a")                        # "Tue"
yd_mon        = yd_dt.strftime("%b")                        # "Jun"
yd_label_dow  = yd_dt.strftime("%a %b %-d")                 # "Tue Jun 30"
yd_label_long = yd_dt.strftime("%A %b %-d, %Y")            # "Tuesday Jun 30, 2026"
lw_range      = (f"{lw_start_dt.strftime('%b %-d')}"
                 f"–{lw_end_dt.strftime('%-d')}")           # "Jun 24–30"
# If month boundary (e.g. Jun 25–Jul 1), show full end date
if lw_start_dt.month != lw_end_dt.month:
    lw_range = (f"{lw_start_dt.strftime('%b %-d')}"
                f"–{lw_end_dt.strftime('%b %-d')}")
mo_range    = f"{mo_start_dt.strftime('%b %-d')}–{yd_dt.strftime('%-d')}"   # "Jun 1–30"
# If month boundary, show full end date
if mo_start_dt.month != yd_dt.month:
    mo_range = f"{mo_start_dt.strftime('%b %-d')}–{yd_dt.strftime('%b %-d')}"
mo_year     = mo_start_dt.strftime("%Y")
mo_name     = mo_start_dt.strftime("%b")                    # "Jun"
mo_name_full= mo_start_dt.strftime("%B")                    # "June"

# ── Helpers ───────────────────────────────────────────────────────────────────

def _c(v, full=False):
    av = abs(v)
    if full:
        return f"${v:,.0f}"
    if av >= 1_000_000: return f"${v/1_000_000:.2f}M"
    if av >= 1_000:     return f"${v/1_000:.0f}K"
    return f"${v:,.0f}"

def _cf(v):
    return f"${v:,.0f}"

def _pct(v): return f"{v*100:.1f}%"

def _yoy(ty, ly, good=True, fmt=None):
    if not ly: return ""
    d2 = (ty - ly) / ly
    arrow, css = ("▲", "up") if (d2 >= 0) == good else ("▼", "dn")
    if d2 < 0: arrow = "▼"; css = "dn" if good else "up"
    ly_str = (fmt or _c)(ly)
    return f'<span class="{css}">{arrow} {abs(d2)*100:.1f}%</span> vs {ly_str} LY'

def _yoy_n(ty, ly, good=True):
    if not ly: return ""
    d2 = (ty - ly) / ly
    arrow = "▲" if d2 >= 0 else "▼"
    css = "up" if (d2 >= 0) == good else "dn"
    return f'<span class="{css}">{arrow} {abs(d2)*100:.1f}%</span> vs {ly:,} LY'

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
    d2 = (actual - forecast) / forecast
    color = "#16a34a" if d2 >= 0 else "#dc2626"
    css   = "up"      if d2 >= 0 else "dn"
    sign  = "+"       if d2 >= 0 else ""
    return (f'<div class="kpi" style="border-left:3px solid {color}">'
            f'<div class="kpi-val" style="font-size:14px">'
            f'<span class="{css}">{sign}{d2*100:.1f}% v. {rfmt(forecast)} fcst</span>'
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


# ── Data extraction ───────────────────────────────────────────────────────────

# Yesterday TY segments
YD_B2C_REV  = d["seg_yd_ty"].get("B2C", {}).get("rev", 0)
YD_B2C_ORD  = d["seg_yd_ty"].get("B2C", {}).get("ord", 0)
YD_TR_REV   = d["seg_yd_ty"].get("Trade", {}).get("rev", 0)
YD_TR_ORD   = d["seg_yd_ty"].get("Trade", {}).get("ord", 0)
YD_HV_REV   = d["seg_yd_ty"].get("Havenly", {}).get("rev", 0)
YD_HV_ORD   = d["seg_yd_ty"].get("Havenly", {}).get("ord", 0)
YD_B2B_REV  = d["seg_yd_ty"].get("B2B", {}).get("rev", 0)
YD_B2B_ORD  = d["seg_yd_ty"].get("B2B", {}).get("ord", 0)
YD_TOT_REV  = YD_B2C_REV + YD_TR_REV + YD_HV_REV + YD_B2B_REV
YD_TOT_ORD  = YD_B2C_ORD + YD_TR_ORD + YD_HV_ORD + YD_B2B_ORD

# Yesterday LY segments
YD_B2C_REV_LY = d["seg_yd_ly"].get("B2C", {}).get("rev", 0)
YD_B2C_ORD_LY = d["seg_yd_ly"].get("B2C", {}).get("ord", 0)
YD_TR_REV_LY  = d["seg_yd_ly"].get("Trade", {}).get("rev", 0)
YD_TR_ORD_LY  = d["seg_yd_ly"].get("Trade", {}).get("ord", 0)
YD_HV_REV_LY  = d["seg_yd_ly"].get("Havenly", {}).get("rev", 0)
YD_B2B_REV_LY = d["seg_yd_ly"].get("B2B", {}).get("rev", 0)
YD_TOT_REV_LY = YD_B2C_REV_LY + YD_TR_REV_LY + YD_HV_REV_LY + YD_B2B_REV_LY
YD_TOT_ORD_LY = (d["seg_yd_ly"].get("B2C", {}).get("ord", 0)
                 + d["seg_yd_ly"].get("Trade", {}).get("ord", 0)
                 + d["seg_yd_ly"].get("Havenly", {}).get("ord", 0)
                 + d["seg_yd_ly"].get("B2B", {}).get("ord", 0))

# AOV — Looker values (pre-cleaned)
YD_BLENDED_AOV    = d.get("aov_yd_ty", 0)
YD_BLENDED_AOV_LY = d.get("aov_yd_ly", 0)
YD_B2C_AOV        = d.get("aov_yd_b2c_ty", YD_BLENDED_AOV)   # fallback to blended if not present
YD_B2C_AOV_LY     = d.get("aov_yd_b2c_ly", YD_BLENDED_AOV_LY)
YD_TR_AOV         = d.get("aov_yd_tr_ty", YD_BLENDED_AOV)
YD_TR_AOV_LY      = d.get("aov_yd_tr_ly", YD_BLENDED_AOV_LY)

LW_BLENDED_AOV    = d.get("aov_lw_ty", 0)
LW_BLENDED_AOV_LY = d.get("aov_lw_ly", 0)
LW_B2C_AOV        = d.get("aov_lw_b2c_ty", LW_BLENDED_AOV)
LW_B2C_AOV_LY     = d.get("aov_lw_b2c_ly", LW_BLENDED_AOV_LY)
LW_TR_AOV         = d.get("aov_lw_tr_ty", LW_BLENDED_AOV)
LW_TR_AOV_LY      = d.get("aov_lw_tr_ly", LW_BLENDED_AOV_LY)

MTD_BLENDED_AOV    = d.get("aov_mtd_ty", 0)
MTD_BLENDED_AOV_LY = d.get("aov_mtd_ly", 0)
MTD_B2C_AOV        = d.get("aov_mtd_b2c_ty", MTD_BLENDED_AOV)
MTD_B2C_AOV_LY     = d.get("aov_mtd_b2c_ly", MTD_BLENDED_AOV_LY)
MTD_TR_AOV         = d.get("aov_mtd_tr_ty", MTD_BLENDED_AOV)
MTD_TR_AOV_LY      = d.get("aov_mtd_tr_ly", MTD_BLENDED_AOV_LY)

# Assisted revenue — computed from pct * total
YD_ASSISTED_REV  = d.get("assisted_yd", 0) * YD_TOT_REV
LW_ASSISTED_REV  = d.get("assisted_lw", 0) * (
    d["seg_lw_ty"].get("B2C", {}).get("rev", 0)
    + d["seg_lw_ty"].get("Trade", {}).get("rev", 0)
    + d["seg_lw_ty"].get("Havenly", {}).get("rev", 0)
    + d["seg_lw_ty"].get("B2B", {}).get("rev", 0)
)
MTD_ASSISTED_REV = d.get("assisted_mtd", 0) * (
    d["seg_mtd_ty"].get("B2C", {}).get("rev", 0)
    + d["seg_mtd_ty"].get("Trade", {}).get("rev", 0)
    + d["seg_mtd_ty"].get("Havenly", {}).get("rev", 0)
    + d["seg_mtd_ty"].get("B2B", {}).get("rev", 0)
)

# Inbound
YD_INBOUND      = d.get("inbound_yd_ty", 0)
YD_INBOUND_LY   = d.get("inbound_yd_ly", 0)
LW_INBOUND      = d.get("inbound_lw_ty", 0)
LW_INBOUND_LY   = d.get("inbound_lw_ly", 0)
MTD_INBOUND     = d.get("inbound_mtd_ty", 0)
MTD_INBOUND_LY  = d.get("inbound_mtd_ly", 0)

# Forecasts
YD_FCST_SNOWFLAKE  = d.get("yd_fcst", 0)
LW_SNOWFLAKE_FCST  = d.get("lw_fcst", 0)
MTD_SNOWFLAKE_FCST = d.get("mtd_fcst", 0)

# Last week TY segments
LW_B2C_REV  = d["seg_lw_ty"].get("B2C", {}).get("rev", 0)
LW_B2C_ORD  = d["seg_lw_ty"].get("B2C", {}).get("ord", 0)
LW_TR_REV   = d["seg_lw_ty"].get("Trade", {}).get("rev", 0)
LW_TR_ORD   = d["seg_lw_ty"].get("Trade", {}).get("ord", 0)
LW_HV_REV   = d["seg_lw_ty"].get("Havenly", {}).get("rev", 0)
LW_HV_ORD   = d["seg_lw_ty"].get("Havenly", {}).get("ord", 0)
LW_B2B_REV  = d["seg_lw_ty"].get("B2B", {}).get("rev", 0)
LW_B2B_ORD  = d["seg_lw_ty"].get("B2B", {}).get("ord", 0)
LW_TOT_REV  = LW_B2C_REV + LW_TR_REV + LW_HV_REV + LW_B2B_REV
LW_TOT_ORD  = LW_B2C_ORD + LW_TR_ORD + LW_HV_ORD + LW_B2B_ORD

# Last week LY segments
LW_B2C_REV_LY = d["seg_lw_ly"].get("B2C", {}).get("rev", 0)
LW_B2C_ORD_LY = d["seg_lw_ly"].get("B2C", {}).get("ord", 0)
LW_TR_REV_LY  = d["seg_lw_ly"].get("Trade", {}).get("rev", 0)
LW_TR_ORD_LY  = d["seg_lw_ly"].get("Trade", {}).get("ord", 0)
LW_HV_REV_LY  = d["seg_lw_ly"].get("Havenly", {}).get("rev", 0)
LW_B2B_REV_LY = d["seg_lw_ly"].get("B2B", {}).get("rev", 0)
LW_TOT_REV_LY = LW_B2C_REV_LY + LW_TR_REV_LY + LW_HV_REV_LY + LW_B2B_REV_LY
LW_TOT_ORD_LY = (d["seg_lw_ly"].get("B2C", {}).get("ord", 0)
                 + d["seg_lw_ly"].get("Trade", {}).get("ord", 0)
                 + d["seg_lw_ly"].get("Havenly", {}).get("ord", 0)
                 + d["seg_lw_ly"].get("B2B", {}).get("ord", 0))

# MTD TY segments
MTD_B2C_REV  = d["seg_mtd_ty"].get("B2C", {}).get("rev", 0)
MTD_B2C_ORD  = d["seg_mtd_ty"].get("B2C", {}).get("ord", 0)
MTD_TR_REV   = d["seg_mtd_ty"].get("Trade", {}).get("rev", 0)
MTD_TR_ORD   = d["seg_mtd_ty"].get("Trade", {}).get("ord", 0)
MTD_HV_REV   = d["seg_mtd_ty"].get("Havenly", {}).get("rev", 0)
MTD_HV_ORD   = d["seg_mtd_ty"].get("Havenly", {}).get("ord", 0)
MTD_B2B_REV  = d["seg_mtd_ty"].get("B2B", {}).get("rev", 0)
MTD_B2B_ORD  = d["seg_mtd_ty"].get("B2B", {}).get("ord", 0)
MTD_TOT_REV  = MTD_B2C_REV + MTD_TR_REV + MTD_HV_REV + MTD_B2B_REV
MTD_TOT_ORD  = MTD_B2C_ORD + MTD_TR_ORD + MTD_HV_ORD + MTD_B2B_ORD

# MTD LY segments
MTD_B2C_REV_LY = d["seg_mtd_ly"].get("B2C", {}).get("rev", 0)
MTD_B2C_ORD_LY = d["seg_mtd_ly"].get("B2C", {}).get("ord", 0)
MTD_TR_REV_LY  = d["seg_mtd_ly"].get("Trade", {}).get("rev", 0)
MTD_TR_ORD_LY  = d["seg_mtd_ly"].get("Trade", {}).get("ord", 0)
MTD_HV_REV_LY  = d["seg_mtd_ly"].get("Havenly", {}).get("rev", 0)
MTD_B2B_REV_LY = d["seg_mtd_ly"].get("B2B", {}).get("rev", 0)
MTD_TOT_REV_LY = MTD_B2C_REV_LY + MTD_TR_REV_LY + MTD_HV_REV_LY + MTD_B2B_REV_LY
MTD_TOT_ORD_LY = (d["seg_mtd_ly"].get("B2C", {}).get("ord", 0)
                  + d["seg_mtd_ly"].get("Trade", {}).get("ord", 0)
                  + d["seg_mtd_ly"].get("Havenly", {}).get("ord", 0)
                  + d["seg_mtd_ly"].get("B2B", {}).get("ord", 0))

# Repeat %
MTD_REPEAT_PCT = d.get("repeat_pct", 0)

# HubSpot (Sales Team) revenue totals
YD_HS_TOTAL      = d.get("hs_yd_ty", 0)
YD_HS_LY_TOTAL   = d.get("hs_yd_ly", 0)
LW_HS_TOTAL      = d.get("hs_lw_ty", 0)
LW_HS_LY_TOTAL   = d.get("hs_lw_ly", 0)
MTD_HS_TOTAL     = d.get("hs_mtd_ty", 0)
MTD_HS_LY_TOTAL  = d.get("hs_mtd_ly", 0)

# Swatch — prefer Looker, fall back to Snowflake
SW_MTD_ORD  = d.get("sw_looker_ty", d.get("sw_mtd_ty", {})).get("orders", 0)
SW_MTD_CUST = d.get("sw_looker_ty", d.get("sw_mtd_ty", {})).get("customers", 0)
SW_LY_ORD   = d.get("sw_looker_ly", d.get("sw_mtd_ly", {})).get("orders", 0)
SW_LY_CUST  = d.get("sw_looker_ly", d.get("sw_mtd_ly", {})).get("customers", 0)

# Swatch last week — estimate proportionally from MTD (7 days / calendar days in period)
_mtd_days = (yd_dt - mo_start_dt).days + 1
_lw_days  = (lw_end_dt - lw_start_dt).days + 1
_lw_wt    = _lw_days / _mtd_days if _mtd_days else 0
SW_LW_ORD      = round(SW_MTD_ORD  * _lw_wt)
SW_LW_CUST     = round(SW_MTD_CUST * _lw_wt)
SW_LW_LY_ORD   = round(SW_LY_ORD   * _lw_wt)
SW_LW_LY_CUST  = round(SW_LY_CUST  * _lw_wt)

# Merch
MERCH = [
    {"cat": m.get("class", m.get("cat", "")), "rev": m["rev"], "units": m["units"], "aur": m["aur"]}
    for m in d.get("merch", [])
]
MERCH_TOTAL = sum(m["rev"] for m in MERCH) or 1

# Studio orders — built from looker_studios + studio_cvr_mtd + studio_cvr_90d
_cvr_mtd_map  = {r["studio"]: r for r in d.get("studio_cvr_mtd", [])}
_cvr_90d_map  = d.get("studio_cvr_90d", {})
STUDIOS_ORDERS = []
for s in d.get("looker_studios", []):
    name    = s["name"]
    cvr_row = _cvr_mtd_map.get(name, {})
    inbound = cvr_row.get("contacts", 0)
    STUDIOS_ORDERS.append({
        "name":    name,
        "rev":     s["rev"],
        "orders":  s["orders"],
        "aov":     s["aov"],
        "inbound": inbound,
        "won":     s["orders"],
    })
STUDIO_TOT_REV = sum(s["rev"] for s in STUDIOS_ORDERS) or 1
TOTAL_INBOUND  = sum(s["inbound"] for s in STUDIOS_ORDERS) or 1

# Studio MTD CVR
STUDIO_MTD_CVR = d.get("studio_cvr_mtd", [])

# Build MTD_CVR and NINETY_DAY_CVR dicts
MTD_CVR = {r["studio"]: r["cvr"] / 100.0 for r in STUDIO_MTD_CVR}
NINETY_DAY_CVR = {k: v / 100.0 for k, v in _cvr_90d_map.items()}

# MC data — merge mc_mtd + mc_90d
MC_DATA = []
for name, mtd_row in d.get("mc_mtd", {}).items():
    d90_row = d.get("mc_90d", {}).get(name, {})
    MC_DATA.append({
        "name":     name,
        "mtd_tot":  mtd_row.get("total", 0),
        "mtd_mc":   mtd_row.get("mc_yes", 0),
        "mtd_pct":  mtd_row.get("mc_pct", 0),
        "mtd_cvr":  mtd_row.get("mc_cvr", 0),
        "no_cvr":   mtd_row.get("no_cvr", 0),
        "d90_pct":  d90_row.get("mc_pct", 0),
        "d90_cvr":  d90_row.get("mc_cvr", 0),
    })

# Studio revenue for Sales Team tab
YD_BY_STUDIO  = d.get("studio_yd_ty", [])   # list of {name, rev}
LW_BY_STUDIO  = d.get("studio_lw_ty", [])   # list of {name, rev}
LW_LY_BY_STUDIO = d.get("studio_lw_ly", {}) # dict name→rev
MTD_BY_STUDIO = [{"name": s["name"], "rev": s["rev"]} for s in d.get("studio_hs_mtd", [])]

# Activities
ACTIVITIES_BY_STUDIO = []
for studio_name, act in d.get("activities", {}).items():
    ACTIVITIES_BY_STUDIO.append({
        "studio":   studio_name,
        "calls":    act.get("calls", 0),
        "meetings": act.get("meetings", 0),
        "emails":   act.get("emails", 0),
        "deals":    act.get("deals", 0),
    })

# Daily forecast from Google Sheet
DAILY_FCST  = d.get("daily_fcst", {})
FULL_MO_FCST = d.get("full_mo_fcst", 0)
yd_str       = dates["yd"]
mo_start_str   = dates["mo_start"]
MTD_SALES_FCST = sum(v for k, v in DAILY_FCST.items() if mo_start_str <= k <= yd_str)
YD_SALES_FCST  = DAILY_FCST.get(yd_str, 0)
PACING_PCT     = MTD_SALES_FCST / FULL_MO_FCST if FULL_MO_FCST else 0

# LW sales forecast from DAILY_FCST
lw_start_str = dates["lw_start"]
lw_end_str   = dates["lw_end"]
LW_SALES_FCST = sum(v for k, v in DAILY_FCST.items() if lw_start_str <= k <= lw_end_str)

# Reps
_reps_mtd = d.get("reps_mtd", [])
rep_rev_map = {r["name"]: r["rev"] for r in _reps_mtd}  # display_name → rev

MTD_TOP_REPS = sorted(_reps_mtd, key=lambda x: -x["rev"])[:5]
# Top 5 reps (MTD) used in place of YD top reps (not available in data.json)
YD_TOP_REPS  = MTD_TOP_REPS  # proxy: MTD top 5 reps

# Closing notes
CLOSING_NOTES = d.get("closing_notes", "")

# Monthly CVR — convert 'YYYY-MM-DD' month key to 'Mon YYYY'
MONTHLY_CVR = []
for row in d.get("monthly_cvr", []):
    month_raw = row.get("month", "")
    try:
        month_dt = datetime.date.fromisoformat(month_raw)
        month_lbl = month_dt.strftime("%b %Y")
    except ValueError:
        month_lbl = month_raw  # already formatted
    MONTHLY_CVR.append({
        "month":    month_lbl,
        "contacts": row.get("contacts", 0),
        "d14":      row.get("d14", 0),
        "d30":      row.get("d30", 0),
        "d60":      row.get("d60", 0),
        "d90":      row.get("d90", 0),
    })

# ── Static config (hardcoded — goals set externally) ─────────────────────────

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
    "bran.randol":          ("Bran Randol",          "San Francisco",  50_000),
    "mary.langridge":       ("Mary Langridge",       "San Francisco", 138_000),
    "rachel.kivo":          ("Rachel Kivo",          "San Francisco", 138_000),
    "alejandra.jimenez":    ("Alejandra Jimenez",    "Seattle",        83_000),
    "kai.davies":           ("Kai Davies",           "Seattle",        92_000),
    "laura.tulloch":        ("Laura Tulloch",        "Seattle",        83_000),
    "lindsay.reyna":        ("Lindsay Reyna",        "Seattle",        83_000),
    "rachel.roth":          ("Rachel Roth",          "Seattle",        83_000),
    "maico.vergara":        ("Maico Vergara",        "Washington DC", 107_000),
    "sameera.tanveer":      ("Sameera Tanveer",      "Washington DC", 107_000),
    "shawn.neifert":        ("Shawn Neifert",        "Washington DC", 117_000),
}

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
        + _kpi(_pct(YD_ASSISTED_REV / YD_TOT_REV) if YD_TOT_REV else "N/A", "Assisted %")
        + _kpi(str(YD_INBOUND), "Inbound Engagements", _yoy_n(YD_INBOUND, YD_INBOUND_LY))
        + _fcst_kpi(YD_TOT_REV, YD_FCST_SNOWFLAKE, fmt=_cf)
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
        f'<div class="section-label">📈 Yesterday — {yd_label_dow}</div>'
        + row1 + row2 + segs + '</div>'
    )

    # Last Week section
    lw_mix = LW_B2C_REV + LW_TR_REV + LW_HV_REV + LW_B2B_REV
    lw_row1 = (
        '<div class="kpi-grid">'
        + _kpi(_cf(LW_TOT_REV), "Revenue", _yoy(LW_TOT_REV, LW_TOT_REV_LY, fmt=_cf), "#0d9488")
        + _kpi(str(LW_TOT_ORD), "Orders", _yoy_n(LW_TOT_ORD, LW_TOT_ORD_LY))
        + _kpi(_pct(LW_ASSISTED_REV / LW_TOT_REV) if LW_TOT_REV else "N/A", "Assisted %")
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
        f'<div class="section-label">📆 Last Week — {lw_range}</div>'
        + lw_row1 + lw_row2 + lw_segs + lw_swatches + '</div>'
    )

    # MTD section
    mtd_mix = MTD_B2C_REV + MTD_TR_REV + MTD_HV_REV + MTD_B2B_REV
    mtd_row1 = (
        '<div class="kpi-grid">'
        + _kpi(_cf(MTD_TOT_REV), "MTD Revenue", _yoy(MTD_TOT_REV, MTD_TOT_REV_LY, fmt=_cf), "#0d9488")
        + _kpi(str(MTD_TOT_ORD), "MTD Orders", _yoy_n(MTD_TOT_ORD, MTD_TOT_ORD_LY))
        + _kpi(_pct(MTD_REPEAT_PCT), "Repeat %")
        + _kpi(_pct(MTD_ASSISTED_REV / MTD_TOT_REV) if MTD_TOT_REV else "N/A", "Assisted %")
        + _fcst_kpi(MTD_TOT_REV, MTD_SNOWFLAKE_FCST, fmt=_cf)
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
    if MERCH:
        mtd_merch = '<div class="sub-label">Merch Contribution (Merchandise · MTO + QS)</div>'
        for m in MERCH[:9]:
            mtd_merch += _merch_bar(m["cat"], m["rev"], m["units"], m["aur"], MERCH_TOTAL)
    else:
        mtd_merch = ""

    # Studio table
    tot_ord = sum(s["orders"] for s in STUDIOS_ORDERS) or 1
    tot_inb = TOTAL_INBOUND

    baseline_pcts = {}
    for s in STUDIOS_ORDERS:
        mtd_cvr_v = MTD_CVR.get(s["name"], 0)
        d90_cvr_v = NINETY_DAY_CVR.get(s["name"], 1) or 1
        baseline_pcts[s["name"]] = mtd_cvr_v / d90_cvr_v

    avg_baseline = (sum(baseline_pcts.get(s["name"], 0) * s["inbound"] for s in STUDIOS_ORDERS) / tot_inb
                    if tot_inb else 0)
    avg_mtd = (sum(MTD_CVR.get(s["name"], 0) * s["inbound"] for s in STUDIOS_ORDERS) / tot_inb
               if tot_inb else 0)
    avg_90d = (sum(NINETY_DAY_CVR.get(s["name"], 0) * s["inbound"] for s in STUDIOS_ORDERS) / tot_inb
               if tot_inb else 0)

    studio_rows = ""
    for s in STUDIOS_ORDERS:
        name      = s["name"]
        aov       = s.get("aov", s["rev"] / s["orders"] if s["orders"] else 0)
        pct_d     = s["inbound"] / TOTAL_INBOUND if TOTAL_INBOUND else 0
        mtd_cvr   = MTD_CVR.get(name, 0)
        d90_cvr   = NINETY_DAY_CVR.get(name, 0)
        base_pct  = baseline_pcts.get(name, 0)
        diff_avg  = base_pct - avg_baseline

        if diff_avg >= 0.05:    b_color = "#16a34a"
        elif diff_avg >= -0.05: b_color = "#ca8a04"
        else:                   b_color = "#dc2626"

        vs_avg = f'<span style="color:{b_color};font-weight:700">{base_pct*100:.0f}%</span>'
        studio_rows += (
            f'<tr><td>{name}</td><td>{_cf(s["rev"])}</td><td>{s["orders"]}</td>'
            f'<td>{_cf(aov)}</td><td>{_pct(pct_d)}</td>'
            f'<td>{_pct(mtd_cvr)}</td><td>{_pct(d90_cvr)}</td><td>{vs_avg}</td></tr>'
        )

    studio_rows += (
        f'<tr style="font-weight:700;border-top:2px solid #e2e8f0">'
        f'<td>Total / Avg</td><td>{_cf(STUDIO_TOT_REV)}</td><td>{tot_ord}</td>'
        f'<td>{_cf(STUDIO_TOT_REV/tot_ord)}</td><td>100%</td>'
        f'<td>{_pct(avg_mtd)}</td><td>{_pct(avg_90d)}</td>'
        f'<td style="color:#475569">{avg_baseline*100:.0f}% avg</td></tr>'
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

    # Monthly CVR SVG chart
    SW, SH   = 600, 340
    CX1, CX2 = 60, 575
    CY1, CY2 = 20, 290
    CW = CX2 - CX1
    CH = CY2 - CY1

    months    = [r["month"].replace(f" {mo_year}", "").replace(f" {yd_dt.year}", "") for r in MONTHLY_CVR]
    n         = len(months)
    bar_gap   = CW / n if n else 1
    bar_w     = bar_gap * 0.45
    xs        = [CX1 + bar_gap * (i + 0.5) for i in range(n)]

    max_contacts = max((r["contacts"] for r in MONTHLY_CVR), default=1) or 1
    max_cvr_val  = 22.0
    inprog_idx   = n - 1

    def _bar_y(contacts):
        return CY2 - (contacts / max_contacts * CH * 0.85)

    def _cvr_y(pct):
        return CY2 - (pct / max_cvr_val * CH)

    LINE_SERIES = [
        ("14-Day", "d14", "#0d9488", "8,2"),
        ("30-Day", "d30", "#6366f1", "4,2"),
        ("60-Day", "d60", "#f59e0b", "2,2"),
        ("90-Day", "d90", "#64748b", "none"),
    ]

    svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="{SW}" height="{SH}" style="font-family:-apple-system,sans-serif;overflow:visible">'

    for pct in [5, 10, 15, 20]:
        gy = _cvr_y(pct)
        svg += f'<line x1="{CX1}" y1="{gy:.1f}" x2="{CX2}" y2="{gy:.1f}" stroke="#e2e8f0" stroke-width="1"/>'
        svg += f'<text x="{CX2+6}" y="{gy+4:.1f}" font-size="9" fill="#94a3b8">{pct}%</text>'

    for i, r in enumerate(MONTHLY_CVR):
        bx = xs[i] - bar_w / 2
        by = _bar_y(r["contacts"])
        bh = CY2 - by
        color = "#e2e8f0" if i == inprog_idx else "#bfdbfe"
        svg += f'<rect x="{bx:.1f}" y="{by:.1f}" width="{bar_w:.1f}" height="{bh:.1f}" rx="2" fill="{color}"/>'
        label_y = by - 3 if bh > 20 else by - 5
        svg += f'<text x="{xs[i]:.1f}" y="{label_y:.1f}" text-anchor="middle" font-size="8" fill="#64748b">{r["contacts"]//100*100:,}</text>'

    for key, field, color, dash in LINE_SERIES:
        pts = " ".join(f"{xs[i]:.1f},{_cvr_y(r[field]):.1f}" for i, r in enumerate(MONTHLY_CVR) if i < inprog_idx)
        if pts:
            dash_attr = f'stroke-dasharray="{dash}"' if dash != "none" else ""
            svg += f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="2.5" {dash_attr} stroke-linejoin="round" stroke-linecap="round"/>'
        for i, r in enumerate(MONTHLY_CVR):
            if i >= inprog_idx: continue
            cy = _cvr_y(r[field])
            svg += f'<circle cx="{xs[i]:.1f}" cy="{cy:.1f}" r="4" fill="{color}" stroke="white" stroke-width="1.5"/>'
            if field == "d90":
                svg += f'<text x="{xs[i]:.1f}" y="{cy-9:.1f}" text-anchor="middle" font-size="10" fill="{color}" font-weight="700">{r[field]}%</text>'

    for i, (m, r) in enumerate(zip(months, MONTHLY_CVR)):
        lbl = m + ("*" if i == inprog_idx else "")
        svg += f'<text x="{xs[i]:.1f}" y="{CY2+14}" text-anchor="middle" font-size="10" fill="#475569">{lbl}</text>'

    svg += f'<text x="12" y="{(CY1+CY2)//2}" text-anchor="middle" font-size="9" fill="#94a3b8" transform="rotate(-90,12,{(CY1+CY2)//2})">Inbound</text>'
    svg += f'<text x="{CX2+28}" y="{CY1-4}" text-anchor="middle" font-size="9" fill="#94a3b8">CVR</text>'
    svg += '</svg>'

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
        + f'<p class="note">Bars = inbound contacts (left scale). Lines = % who ordered within 14/30/60/90 days of first contact. '
          f'*{mo_name} in-progress — lines excluded. 90D label shown above each dot.</p>'
    )

    mtd_sec = (
        '<div class="section">'
        f'<div class="section-label">📅 MTD — {mo_range} · Forecast: Looker</div>'
        + mtd_row1 + mtd_row2 + mtd_segs + swatches + mtd_merch + studio_tbl + '</div>'
    )

    # Performance blurb
    def _sign1(v): return "▲" if v >= 0 else "▼"
    def _col1(v):  return "#16a34a" if v >= 0 else "#dc2626"
    def _dir1(v):  return "ahead of" if v >= 0 else "behind"

    yd_vs_fcst  = (YD_TOT_REV - YD_FCST_SNOWFLAKE)   / YD_FCST_SNOWFLAKE   * 100 if YD_FCST_SNOWFLAKE  else 0
    yd_aov_chg  = (YD_BLENDED_AOV - YD_BLENDED_AOV_LY) / YD_BLENDED_AOV_LY * 100 if YD_BLENDED_AOV_LY else 0
    yd_inb_chg  = (YD_INBOUND - YD_INBOUND_LY)          / YD_INBOUND_LY      * 100 if YD_INBOUND_LY     else 0
    yd_ast_pct  =  YD_ASSISTED_REV / YD_TOT_REV         * 100 if YD_TOT_REV else 0
    lw_vs_fcst1 = (LW_TOT_REV - LW_SNOWFLAKE_FCST)    / LW_SNOWFLAKE_FCST   * 100 if LW_SNOWFLAKE_FCST  else 0
    lw_rev_yoy  = (LW_TOT_REV - LW_TOT_REV_LY)         / LW_TOT_REV_LY      * 100 if LW_TOT_REV_LY      else 0
    lw_aov_yoy  = (LW_BLENDED_AOV - LW_BLENDED_AOV_LY) / LW_BLENDED_AOV_LY  * 100 if LW_BLENDED_AOV_LY else 0
    lw_mix2     = LW_B2C_REV + LW_TR_REV + LW_HV_REV + LW_B2B_REV
    lw_b2c_pct  =  LW_B2C_REV / lw_mix2 * 100 if lw_mix2 else 0
    lw_b2c_ly   = (LW_B2C_REV_LY / (LW_B2C_REV_LY+LW_TR_REV_LY+LW_HV_REV_LY+LW_B2B_REV_LY) * 100
                   if (LW_B2C_REV_LY+LW_TR_REV_LY+LW_HV_REV_LY+LW_B2B_REV_LY) else 0)
    mtd_vs_fcst = (MTD_TOT_REV - MTD_SNOWFLAKE_FCST)  / MTD_SNOWFLAKE_FCST  * 100 if MTD_SNOWFLAKE_FCST else 0
    mtd_rev_yoy = (MTD_TOT_REV - MTD_TOT_REV_LY)       / MTD_TOT_REV_LY     * 100 if MTD_TOT_REV_LY     else 0
    mtd_inb_chg = (MTD_INBOUND - MTD_INBOUND_LY)        / MTD_INBOUND_LY     * 100 if MTD_INBOUND_LY     else 0
    mtd_sw_chg  = (SW_MTD_ORD  - SW_LY_ORD)             / SW_LY_ORD          * 100 if SW_LY_ORD          else 0
    mtd_aov_yoy = (MTD_BLENDED_AOV - MTD_BLENDED_AOV_LY)/ MTD_BLENDED_AOV_LY* 100 if MTD_BLENDED_AOV_LY else 0
    mtd_ast_pct =  MTD_ASSISTED_REV / MTD_TOT_REV       * 100 if MTD_TOT_REV else 0

    blurb_lines = [
        '<div style="font-size:11px;font-weight:700;color:#1e293b;margin-bottom:10px;text-transform:uppercase;letter-spacing:.5px">📊 Performance Summary — Why Are We Missing / Achieving Plan?</div>',
        f'<div style="margin-bottom:9px"><span style="font-weight:700;font-size:12px">Yesterday: </span>'
        f'<span style="font-size:12px;color:#334155">{_cf(YD_TOT_REV)} — <span style="color:{_col1(yd_vs_fcst)}">{_sign1(yd_vs_fcst)} {abs(yd_vs_fcst):.1f}% {_dir1(yd_vs_fcst)}</span> forecast. '
        f'Inbound <span style="color:{_col1(yd_inb_chg)}">{_sign1(yd_inb_chg)} {abs(yd_inb_chg):.1f}% YoY</span> ({YD_INBOUND} vs {YD_INBOUND_LY}). '
        f'Blended AOV {_cf(YD_BLENDED_AOV)} <span style="color:{_col1(yd_aov_chg)}">{_sign1(yd_aov_chg)} {abs(yd_aov_chg):.1f}% YoY</span>. '
        f'Assisted (MC=Yes): {yd_ast_pct:.1f}% of revenue.</span></div>',
        f'<div style="margin-bottom:9px"><span style="font-weight:700;font-size:12px">Last Week ({lw_range}): </span>'
        f'<span style="font-size:12px;color:#334155">{_cf(LW_TOT_REV)} — <span style="color:{_col1(lw_vs_fcst1)}">{_sign1(lw_vs_fcst1)} {abs(lw_vs_fcst1):.1f}% {_dir1(lw_vs_fcst1)}</span> forecast. '
        f'Revenue <span style="color:{_col1(lw_rev_yoy)}">{_sign1(lw_rev_yoy)} {abs(lw_rev_yoy):.1f}% YoY</span>. '
        f'AOV {_cf(LW_BLENDED_AOV)} vs {_cf(LW_BLENDED_AOV_LY)} LY <span style="color:{_col1(lw_aov_yoy)}">{_sign1(lw_aov_yoy)} {abs(lw_aov_yoy):.1f}%</span>. '
        f'B2C mix {lw_b2c_pct:.0f}% vs {lw_b2c_ly:.0f}% LY ({"▼ shift toward non-B2C" if lw_b2c_pct < lw_b2c_ly else "▲ stronger B2C mix"}).</span></div>',
        f'<div><span style="font-weight:700;font-size:12px">MTD ({mo_range}): </span>'
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
<div class="page-label">Interior Define · Total Business · {yd_label_long}</div>
<div class="email-wrap">
  <div class="hdr">
    <div class="hdr-brand">Interior Define Total Business {yd_label_long}</div>
    <div class="hdr-meta">Daily Business Review · {yd_label_dow} · Forecast source: Looker (ID_FORECASTED_ADJUSTED_GROSS_BOOKINGS)</div>
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
    max_yd_s = max((s["rev"] for s in YD_BY_STUDIO), default=1) or 1
    max_yd_r = YD_TOP_REPS[0]["rev"] if YD_TOP_REPS else 1
    yd_s_bars = "".join(_horiz_bar(s["name"], s["rev"], max_yd_s) for s in YD_BY_STUDIO[:5])
    yd_r_bars = "".join(_horiz_bar(f'{r["name"]} · {r["studio"]}', r["rev"], max_yd_r, "#6366f1") for r in YD_TOP_REPS)

    yd_yoy = _yoy(YD_HS_TOTAL, YD_HS_LY_TOTAL)
    yd_fcst_d = (YD_HS_TOTAL - YD_SALES_FCST) / YD_SALES_FCST if YD_SALES_FCST else 0
    yd_css = "up" if yd_fcst_d >= 0 else "dn"

    yd_net = (
        '<div class="ns-pair">'
        f'<div class="ns-box" style="border-left:3px solid #0d9488">'
        f'<div class="ns-lbl">Net Sales (HubSpot)</div>'
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

    # Closing notes from Slack #csr-operations
    closing_content = CLOSING_NOTES if CLOSING_NOTES else "No closing notes available."
    yd_notes = (
        '<div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:6px;padding:14px 16px;margin-top:12px">'
        f'<div class="sub-label" style="color:#b45309;margin-bottom:10px">📝 Closing Notes — {yd_label_dow}</div>'
        f'<div style="font-size:12.5px;color:#1e293b;line-height:1.6;white-space:pre-wrap">{closing_content}</div>'
        '</div>'
    )

    yd_sec = (
        '<div class="section">'
        f'<div class="section-label">📈 Yesterday — {yd_label_dow}</div>'
        + yd_net
        + '<div class="two-col">'
        + f'<div><div class="sub-label">Top 5 Studios</div>{yd_s_bars}</div>'
        + f'<div><div class="sub-label">Top 5 Reps (MTD)</div>{yd_r_bars}</div>'
        + '</div>'
        + yd_notes
        + '</div>'
    )

    # Last Week section
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
    max_lw_s  = max((s["rev"] for s in LW_BY_STUDIO), default=1) or 1
    lw_s_bars = "".join(_horiz_bar(s["name"], s["rev"], max_lw_s)
                        for s in sorted(LW_BY_STUDIO, key=lambda x: -x["rev"])[:5])
    lw_sec = (
        '<div class="section">'
        f'<div class="section-label">📆 Last Week — {lw_range}</div>'
        + lw_net
        + f'<div><div class="sub-label">Top 5 Studios</div>{lw_s_bars}</div>'
        + '</div>'
    )

    # Activities by Studio
    act_total = {k: sum(s.get(k, 0) for s in ACTIVITIES_BY_STUDIO) for k in ("calls","meetings","emails","deals")}

    def _act_bar(v, mx, color="#6366f1"):
        w = int(v / mx * 120) if mx else 0
        return f'<div style="width:{w}px;height:10px;background:{color};border-radius:2px;display:inline-block;vertical-align:middle"></div>'

    act_rows = ""
    max_calls  = max((s["calls"]    for s in ACTIVITIES_BY_STUDIO), default=1) or 1
    max_mtgs   = max((s["meetings"] for s in ACTIVITIES_BY_STUDIO), default=1) or 1
    max_emails = max((s["emails"]   for s in ACTIVITIES_BY_STUDIO), default=1) or 1
    for s in sorted(ACTIVITIES_BY_STUDIO, key=lambda x: -(x["calls"]+x["meetings"]+x["emails"])):
        reps      = STUDIO_REP_COUNT.get(s["studio"], 1)
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
            f'<td style="color:#64748b">{s.get("deals",0):,}</td>'
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
    top_calls_studio = max(ACTIVITIES_BY_STUDIO, key=lambda x: x["calls"]/STUDIO_REP_COUNT.get(x["studio"],1)) if ACTIVITIES_BY_STUDIO else None
    top_mtg_studio   = max(ACTIVITIES_BY_STUDIO, key=lambda x: x["meetings"]/STUDIO_REP_COUNT.get(x["studio"],1)) if ACTIVITIES_BY_STUDIO else None
    low_mtg_studio   = min(ACTIVITIES_BY_STUDIO, key=lambda x: x["meetings"]/STUDIO_REP_COUNT.get(x["studio"],1)) if ACTIVITIES_BY_STUDIO else None
    total_rep_count  = sum(STUDIO_REP_COUNT.values())
    avg_m_pp  = act_total["meetings"] / total_rep_count if total_rep_count else 0
    avg_c_pp  = act_total["calls"]    / total_rep_count if total_rep_count else 0

    act_blurb_body = ""
    if top_calls_studio and top_mtg_studio and low_mtg_studio:
        top_c_pp = top_calls_studio["calls"]  / STUDIO_REP_COUNT.get(top_calls_studio["studio"],1)
        top_m_pp = top_mtg_studio["meetings"] / STUDIO_REP_COUNT.get(top_mtg_studio["studio"],1)
        low_m_pp = low_mtg_studio["meetings"] / STUDIO_REP_COUNT.get(low_mtg_studio["studio"],1)
        act_blurb_body = (
            f'Across all {total_rep_count} DE/SDEs, the team averaged <strong>{avg_c_pp:.1f} calls/rep</strong> and <strong>{avg_m_pp:.1f} meetings/rep</strong> MTD. '
            f'<strong>{top_calls_studio["studio"]}</strong> leads on calls/rep ({top_c_pp:.1f}); '
            f'<strong>{top_mtg_studio["studio"]}</strong> leads on meetings/rep ({top_m_pp:.1f}). '
            f'<strong>{low_mtg_studio["studio"]}</strong> has the fewest meetings/rep ({low_m_pp:.1f} vs {avg_m_pp:.1f} avg) — worth monitoring given meetings are the highest-converting activity. '
            f'Source: HubSpot CRM (calls/meetings/emails via /crm/v3/objects API), filtered to DE/SDE owners. SMS and Conversation Sessions not available — see HubSpot MTD Activity by DE dashboard for full picture.'
        )
    act_blurb = (
        '<div style="background:#f0f9ff;border:1px solid #bae6fd;border-left:3px solid #0284c7;border-radius:6px;padding:12px 14px;margin-top:10px">'
        '<div style="font-size:11px;font-weight:700;color:#0c4a6e;margin-bottom:8px;text-transform:uppercase;letter-spacing:.4px">💡 So What — Activities MTD</div>'
        f'<div style="font-size:12px;color:#1e293b;line-height:1.65">{act_blurb_body}</div>'
        '</div>'
    )
    activities_sec = (
        '<div class="section">'
        '<div class="section-label">📞 Activities by Studio — MTD (DE/SDE only)</div>'
        + act_tbl + act_blurb + '</div>'
    )

    # Sales Team Performance Blurb
    def _s(v):    return "▲" if v >= 0 else "▼"
    def _c2(v):   return "#16a34a" if v >= 0 else "#dc2626"
    def _dir2(v): return "ahead of" if v >= 0 else "behind"

    yd_s_fcst  = (YD_HS_TOTAL  - YD_SALES_FCST)   / YD_SALES_FCST   * 100 if YD_SALES_FCST   else 0
    yd_s_yoy   = (YD_HS_TOTAL  - YD_HS_LY_TOTAL)   / YD_HS_LY_TOTAL  * 100 if YD_HS_LY_TOTAL  else 0
    lw_s_fcst2 = (LW_HS_TOTAL  - LW_SALES_FCST)   / LW_SALES_FCST    * 100 if LW_SALES_FCST   else 0
    lw_s_yoy   = (LW_HS_TOTAL  - LW_HS_LY_TOTAL)   / LW_HS_LY_TOTAL  * 100 if LW_HS_LY_TOTAL  else 0
    mtd_s_fcst = (MTD_HS_TOTAL - MTD_SALES_FCST)  / MTD_SALES_FCST   * 100 if MTD_SALES_FCST  else 0
    mtd_s_yoy  = (MTD_HS_TOTAL - MTD_HS_LY_TOTAL) / MTD_HS_LY_TOTAL  * 100 if MTD_HS_LY_TOTAL else 0

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

    reps_ahead_l  = []
    reps_behind_l = []
    for email_key, (display_name, studio, goal) in REP_GOALS.items():
        if goal == 0: continue
        paced  = goal * PACING_PCT
        actual = rep_rev_map.get(display_name, 0)
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

    mc_avg_pct = sum(r["mtd_pct"] for r in MC_DATA) / len(MC_DATA) if MC_DATA else 0
    low_mc     = sorted(MC_DATA, key=lambda x: x["mtd_pct"])[:2]

    perf_lines = [
        '<div style="font-size:11px;font-weight:700;color:#1e293b;margin-bottom:10px;text-transform:uppercase;letter-spacing:.5px">📊 Sales Team Performance — Why Are We Missing / Achieving Plan?</div>',
        f'<div style="margin-bottom:9px"><span style="font-weight:700;font-size:12px">Yesterday: </span>'
        f'<span style="font-size:12px;color:#334155">{_c(YD_HS_TOTAL)} — <span style="color:{_c2(yd_s_fcst)}">{_s(yd_s_fcst)} {abs(yd_s_fcst):.1f}% {_dir2(yd_s_fcst)}</span> forecast, '
        f'<span style="color:{_c2(yd_s_yoy)}">{_s(yd_s_yoy)} {abs(yd_s_yoy):.1f}% YoY</span>.</span></div>',
        f'<div style="margin-bottom:9px"><span style="font-weight:700;font-size:12px">Last Week ({lw_range}): </span>'
        f'<span style="font-size:12px;color:#334155">{_c(LW_HS_TOTAL)} — <span style="color:{_c2(lw_s_fcst2)}">{_s(lw_s_fcst2)} {abs(lw_s_fcst2):.1f}% {_dir2(lw_s_fcst2)}</span> forecast, '
        f'<span style="color:{_c2(lw_s_yoy)}">{_s(lw_s_yoy)} {abs(lw_s_yoy):.1f}% YoY</span>.</span></div>',
        f'<div style="margin-bottom:9px"><span style="font-weight:700;font-size:12px">MTD ({mo_range}): </span>'
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
    mtd_yoy    = _yoy(MTD_HS_TOTAL, MTD_HS_LY_TOTAL)
    mtd_fcst_d = (MTD_HS_TOTAL - MTD_SALES_FCST) / MTD_SALES_FCST if MTD_SALES_FCST else 0
    mtd_css    = "up" if mtd_fcst_d >= 0 else "dn"

    max_mtd_s  = max((s["rev"] for s in MTD_BY_STUDIO), default=1) or 1
    max_mtd_r  = MTD_TOP_REPS[0]["rev"] if MTD_TOP_REPS else 1
    mtd_s_bars = "".join(_horiz_bar(s["name"], s["rev"], max_mtd_s) for s in MTD_BY_STUDIO)
    mtd_r_bars = "".join(_horiz_bar(f'{r["name"]} · {r["studio"]}', r["rev"], max_mtd_r, "#6366f1") for r in MTD_TOP_REPS[:5])

    mtd_net = (
        '<div class="ns-pair">'
        f'<div class="ns-box" style="border-left:3px solid #0d9488">'
        f'<div class="ns-lbl">Net Sales (HubSpot)</div>'
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
        f'<p class="note">Pacing: {_pct(PACING_PCT)} of {mo_name_full} elapsed through {yd_label_dow} · '
        f'Google Sheet forecast {_c(MTD_SALES_FCST)} MTD. Revenue: HubSpot (MC=Yes + Closed Won).</p>'
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
        '<div class="table-wrap"><table><tr><th>Studio</th><th>Mo Goal</th><th>Paced</th>'
        '<th>MTD Actual</th><th>% of Goal</th><th>% Paced</th><th>Status</th></tr>'
        + team_rows + '</table></div>'
    )

    # Individual pacing table — match by display name from rep_rev_map
    rep_rows_data = []
    for email_key, (display_name, studio, goal) in REP_GOALS.items():
        if goal == 0: continue
        paced  = goal * PACING_PCT
        actual = rep_rev_map.get(display_name, 0)
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

    # Inbound CVR section — computed from studio_cvr_mtd
    total_contacts = sum(r["contacts"] for r in STUDIO_MTD_CVR)
    total_orders   = sum(r["orders"]   for r in STUDIO_MTD_CVR)

    def _cvr_row(label, ty_n, ty_tot, ly_n, ly_tot):
        ty_pct = ty_n / ty_tot * 100 if ty_tot else 0
        ly_pct = ly_n / ly_tot * 100 if ly_tot else 0
        diff   = ty_pct - ly_pct
        arrow  = "▲" if diff >= 0 else "▼"
        color  = "#16a34a" if diff >= 0 else "#dc2626"
        ly_display = f"{ly_n:,} / {ly_tot:,}" if ly_tot else "N/A"
        ly_pct_display = f"{ly_pct:.2f}%" if ly_tot else "N/A"
        diff_display = f'<span style="color:{color};font-weight:700">{arrow} {abs(diff):.2f}pp</span>' if ly_tot else "N/A"
        return (
            f'<tr><td>{label}</td>'
            f'<td>{ty_n:,} / {ty_tot:,}</td><td style="font-weight:600">{ty_pct:.2f}%</td>'
            f'<td>{ly_display}</td><td style="font-weight:600">{ly_pct_display}</td>'
            f'<td>{diff_display}</td></tr>'
        )

    cvr_rows = (
        _cvr_row("Order CVR",      total_orders,   total_contacts, 0, 0) +
        _cvr_row("Closed Won CVR", total_orders,   total_contacts, 0, 0)
    )
    inbound_cvr_sec = (
        '<div class="section">'
        f'<div class="section-label">📈 Inbound CVR — MTD {mo_range} (B2C, apples-to-apples)</div>'
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

    # % Meaningful Contact by studio
    mc_sorted  = sorted(MC_DATA, key=lambda x: x["mtd_pct"], reverse=True)
    mc_avg_mtd = sum(r["mtd_pct"] for r in MC_DATA) / len(MC_DATA) if MC_DATA else 0
    max_pct    = 80.0

    mc_bars = f'<div style="padding:4px 0">'
    for r in mc_sorted:
        diff    = r["mtd_pct"] - r["d90_pct"]
        arrow   = "▲" if diff >= 0 else "▼"
        t_color = "#16a34a" if diff >= 0 else "#dc2626"
        bar_color = "#6366f1" if r["mtd_pct"] >= mc_avg_mtd else "#94a3b8"
        w_mtd = r["mtd_pct"] / max_pct * 200
        w_90d = r["d90_pct"] / max_pct * 200
        mc_bars += (
            f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:9px">'
            f'<span style="width:105px;font-size:11px;color:#334155;flex-shrink:0">{r["name"]}</span>'
            f'<div style="width:200px;height:16px;background:#f1f5f9;border-radius:3px;position:relative;flex-shrink:0">'
            f'<div style="width:{w_mtd:.1f}px;height:100%;background:{bar_color};border-radius:3px;opacity:0.85"></div>'
            f'<div style="position:absolute;top:0;left:{w_90d:.1f}px;width:2px;height:100%;background:#334155;opacity:0.4"></div>'
            f'</div>'
            f'<span style="font-size:11px;font-weight:700;color:{bar_color};width:36px">{r["mtd_pct"]}%</span>'
            f'<span style="font-size:10px;color:{t_color};font-weight:600;width:52px">{arrow} {abs(diff):.1f}pp</span>'
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

    # By-studio inbound CVR bars
    sorted_cvr = sorted(STUDIO_MTD_CVR, key=lambda x: -x["cvr"])
    max_cvr2   = sorted_cvr[0]["cvr"] if sorted_cvr else 1
    avg_cvr2   = sum(r["cvr"] for r in STUDIO_MTD_CVR) / len(STUDIO_MTD_CVR) if STUDIO_MTD_CVR else 0
    avg_line_px = int(avg_cvr2 / max_cvr2 * 220) if max_cvr2 else 0

    def _studio_bar_color(cvr, avg):
        if cvr >= avg * 1.15: return "#16a34a"
        if cvr >= avg * 0.85: return "#0d9488"
        return "#dc2626"

    s_bars = f'<div style="padding:4px 0;position:relative">'
    for r in sorted_cvr:
        color = _studio_bar_color(r["cvr"], avg_cvr2)
        w     = int(r["cvr"] / max_cvr2 * 220) if max_cvr2 else 0
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
        f'<div class="sub-label">Inbound → Order CVR by Studio MTD ({mo_range})</div>'
        + s_bars
        + f'<p class="note">Sorted by CVR. Gray line = avg {avg_cvr2:.1f}%. '
          f'<span style="color:#16a34a">●</span> well above avg '
          f'<span style="color:#0d9488">●</span> near avg '
          f'<span style="color:#dc2626">●</span> below avg. '
          f'B2C contacts with first inbound in window who ordered on/after first contact.</p>'
    )

    mtd_sec = (
        '<div class="section">'
        f'<div class="section-label">📊 MTD — {mo_range}</div>'
        + mtd_net + pacing_note
        + '<div class="two-col">'
        + f'<div><div class="sub-label">Top 5 Reps (MTD)</div>{mtd_r_bars}</div>'
        + f'<div><div class="sub-label">All Studios</div>{mtd_s_bars}</div>'
        + '</div>'
        + studio_cvr_tbl + mc_sec + team_tbl + rep_tbl + '</div>'
    )

    return f"""
<div class="page-label">Interior Define · Sales Team · {yd_label_long}</div>
<div class="email-wrap">
  <div class="hdr">
    <div class="hdr-brand">Interior Define · Sales Team</div>
    <div class="hdr-meta">{yd_label_dow} · Revenue: HubSpot (MC=Yes + Closed Won) · Forecast: Google Sheet</div>
  </div>
  {yd_sec}
  {lw_sec}
  {perf_blurb_sec}
  {mtd_sec}
  {activities_sec}
  <div class="footer">Revenue: HubSpot (MC=Yes + Closed Won) · Forecast: Google Sheet</div>
</div>"""


# ── Assemble & write ──────────────────────────────────────────────────────────

html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Interior Define — Daily Business Review · {yd_label_dow}</title>
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

os.makedirs("/tmp/id", exist_ok=True)
with open("/tmp/id/report.html", "w") as _out:
    _out.write(html)
print("[ok] /tmp/id/report.html")
