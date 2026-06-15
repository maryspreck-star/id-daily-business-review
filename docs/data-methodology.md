# Interior Define Daily Business Review — Full Methodology

**Last updated:** 2026-06-15  
**Author:** Mary Claire Spreck  
**For:** Anyone maintaining this report while MC is OOO  

---

## Overview

This report runs **every Monday at 8am CT** automatically via a Claude remote agent. It covers two tabs:
- **Tab 1 — Total Business:** Company-wide order revenue, AOV, merch, inbound engagements, studio performance, CVR trends
- **Tab 2 — Sales Team:** HubSpot net sales, pacing vs goals, closing notes, MC%, inbound CVR

**Report periods (as of each Monday morning):**
- **Yesterday** = Sunday (day before the Monday run)
- **MTD** = 1st of the month through Sunday
- **LY comparisons** = same calendar dates one year prior

---

## Automation Setup

### How the report runs
- **Schedule:** Every Monday at 8am CDT (1pm UTC). Cron: `0 13 * * 1`
- **Platform:** Claude Remote Agent (Anthropic cloud) — `trig_01RswSW7MsvW5ZGDdvKMhqB5`
- **Manage/pause:** https://claude.ai/code/routines/trig_01RswSW7MsvW5ZGDdvKMhqB5
- **Script:** `scripts/run_from_mcp.py` in the GitHub repo
- **GitHub repo:** https://github.com/maryspreck-star/id-daily-business-review (public)

### What the agent does
1. Downloads `scripts/run_from_mcp.py` from GitHub
2. Runs ~20 Snowflake queries via Havenly Analytics MCP
3. Calls HubSpot API for sales deal data
4. Reads Google Sheets for pacing forecasts and rep goals
5. Reads Slack `#id--retail-closing-notes` for closing notes
6. Calls Looker API for AOV tile values
7. Updates all data variables in the script and runs it
8. Emails the HTML report to: mary.spreck@interiordefine.com, leeanne@havenly.com, olivia.black@havenly.com, matthew.gomes@havenly.com

### DST note
The cron fires at 13:00 UTC. In CDT (summer, UTC-5) this is 8am. When DST ends in November 2026, it will fire at 7am CST. Update the cron to `0 14 * * 1` in November to keep it at 8am CST.

### How to make edits
1. Edit `scripts/run_from_mcp.py` on GitHub (or clone locally)
2. The agent downloads fresh on every run — changes take effect next Monday automatically
3. To test manually: go to https://claude.ai/code/routines and click "Run now"

---

## Credentials & Data Access

| System | Key/ID | Used for |
|---|---|---|
| HubSpot API | Stored in Claude routine prompt (see claude.ai/code/routines) | Deal revenue by studio/rep |
| Looker | Client ID stored in Claude routine prompt | AOV calendar pivot tiles |
| Looker | Secret stored in Claude routine prompt | Same |
| Havenly Analytics MCP | Auto-connected via claude.ai | All Snowflake queries |
| Google Drive MCP | Auto-connected via claude.ai | Google Sheets forecast & goals |
| Slack MCP | Auto-connected via claude.ai | Closing notes |
| Gmail MCP | Auto-connected via claude.ai | Email delivery |
| Google Sheets (forecast) | File ID: `1lJcsmRhG3ScG8s2ol2jPwUBJ18n20MMn101rXc1ZQp0` | Daily studio retail plan |
| Google Sheets (goals) | File ID: `1CkbEVt9utgqkO4xbCnxpc1A6tJCTTRaXWo_iQZQiyJw` | Rep & team monthly goals |
| Slack channel | `C08MYB2S3DH` | `#id--retail-closing-notes` |

---

## Tab 1: Total Business

### Section: Yesterday Revenue

**What it shows:** Single-day order revenue for Sunday broken out by customer segment (B2C, Trade, Havenly), with YoY comparison, AOV, assisted %, inbound engagements, and forecast vs actual.

**Data source:** Looker dashboard 1156 (validated), queries run against Snowflake `PROD.ID_WAREHOUSE.ORDERS` + `CUSTOMERS`.

#### Revenue by segment (KPI boxes)
- **Query:** `ORDERS` INNER JOIN `CUSTOMERS` on `CUSTOMER_ID`
- **Employee filter:** `c.EMAIL NOT LIKE '%@interiordefine.com%' OR c.EMAIL IS NULL` — excludes staff orders
- **Date filter:** Denver timezone — `CONVERT_TIMEZONE('UTC','America/Denver',CAST(ORDER_CREATED_AT AS TIMESTAMP_NTZ))::DATE = yesterday`
- **No order_type or cancellation filter** — matches Looker dashboard tile exactly
- **Segment logic:** `CASE WHEN c.CUSTOMER_ID = 20 THEN 'Havenly' ELSE c.CUSTOMER_GROUP_CLASS END`
- **Revenue formula:** `SUM(subtotal - ABS(discount_amount) + shipping_amount)` — discounted revenue including shipping, no tax
- **YoY:** Same calendar date one year ago (not same day-of-week)

#### AOV (Blended, B2C, Trade)
- **Source:** Looker API — `interior_define` model, `orders` explore
- **Field:** `orders.average_order_value` — Looker's average of per-order values (NOT total revenue ÷ order count; these differ when order sizes vary)
- **Looker tile:** "AOV Yesterday" with `calendar.compare_to_previous_date_filter = "1 day ago for 1 day"` and pivot on `calendar.yesterday` for TY vs LY comparison
- **Employee filter:** `customers.email = "-%@interiordefine.com%"`
- **Why Looker API instead of direct Snowflake:** The calendar dimension's date logic gives the exact match to the dashboard tile

#### Assisted %
- **Definition:** % of yesterday's revenue (not order count) from deals with Meaningful Contact = Yes
- **Formula:** `MC=Yes revenue ÷ total revenue`
- **Source:** Two queries on `PROD.ID_WAREHOUSE.ORDERS`:
  1. Total unfiltered revenue for yesterday
  2. Revenue from orders linked to deals where `MEANINGFUL_CONTACT = TRUE` in `STG_DEAL`
- **Looker tile:** "% Asst Sales Yesterday" — `orders.md_order_revenue` pivoted by `hubspot_deals.has_meaningful_contact`
- **Why revenue-based (not order count):** Matches Looker's "% Asst Sales" tile definition

#### Inbound Engagements (Yesterday)
- **Source:** Snowflake `STG_HUBSPOT_ENGAGEMENTS_BASE` × `STG_CONTACTS`
- **Filters:**
  - `ENGAGEMENT_TYPE NOT IN ('NOTE','TASK')`
  - `ENGAGEMENT_DIRECTION = 'Incoming'`
  - `c.CUSTOMER_GROUP = 'B2C'`
  - Studio exclusions: `c.STUDIO_NAME NOT IN ('The Inside','Burrow','General Managers','Remote Sales')`
  - Denver timezone date filter
- **Count:** `COUNT(DISTINCT c.PRIMARY_HUBSPOT_ID)` — distinct contacts, not raw engagement events
- **YoY:** Same calendar date last year (LY yesterday)
- **Matches:** Looker dashboard 1156 "Daily Inbound Engagement" tile exactly

#### vs Forecast (Yesterday)
- **Actual:** Unfiltered order revenue (no order_type or employee filter) — matches Looker's "v. Yesterday's Forecast" tile
- **Forecast:** `FIVETRAN_DB.UPLOADS.ALL_COMPANY_DAILY_FORECAST.ID_FORECASTED_ADJUSTED_GROSS_BOOKINGS` for the specific date
- **Looker tile:** `orders.order_created_date = "1 day ago for 1 day"` (no type/cancel filter)

---

### Section: Revenue by Customer Class (bars)

**What it shows:** Horizontal bar chart with B2C, Trade, Havenly, B2B as a % of total revenue, with $ amount and YoY for each segment.

**Data source:** Same Looker orders query as yesterday revenue — filtered to yesterday or MTD as appropriate.

- **Bar width:** Proportional to segment's % of total revenue in that period
- **YoY:** Each segment compared to same period last year
- **Color coding:** B2C = indigo, Trade = teal, Havenly = purple, B2B = gray

---

### Section: MTD Revenue

**What it shows:** Month-to-date total revenue, orders, repeat %, assisted %, and forecast comparison.

#### MTD Revenue & Orders
- **Same query as yesterday but date range:** `BETWEEN month_start AND yesterday`
- **YoY:** Same calendar days last year (e.g., Jun 1–14, 2026 vs Jun 1–14, 2025)

#### MTD Blended AOV
- **Source:** Looker API — "AOV" tile with `calendar.compare_to_previous_date_filter = "this month"`
- **YoY LY:** Captured in same Looker API call via "This Month Last Year" pivot value

#### vs Forecast (MTD)
- **Actual:** Unfiltered MTD order revenue (no type/cancel filter) — matches Looker "v. MTD Forecast" tile
- **Forecast:** Sum of `ID_FORECASTED_ADJUSTED_GROSS_BOOKINGS` for all dates month_start through yesterday
- **Looker tile filters:** `orders.order_created_month = "this month"`, `orders.order_created_date = "before 0 days ago"` (no type/cancel filter)

#### Repeat Business %
- **Definition:** % of MTD orders from customers who placed at least one order before the current month
- **Source:** Snowflake — two-step CTE: (1) all MTD orders with customer IDs, (2) MIN(order_date) per customer ever, (3) count where first_order_date < month_start
- **Filter:** `ORDER_TYPE = 'standard' AND CANCELLATION = 'F'`

#### Assisted % (MTD)
- **Same methodology as yesterday assisted % but for full MTD period**
- **Source:** Looker `orders` explore with `hubspot_deals.has_meaningful_contact` — MC=Yes revenue ÷ total revenue

#### Inbound MTD
- **Same query as yesterday inbound but date range:** `BETWEEN month_start AND yesterday`
- **YoY:** Same calendar range last year

---

### Section: Swatch Performance

**What it shows:** MTD swatch orders and unique customers with YoY comparison.

- **Source:** `PROD.ID_WAREHOUSE.SWATCH_ORDERS` × `STG_CONTACTS`
- **Filter:**
  - `c.CUSTOMER_GROUP IN ('B2C','Trade')` — includes both (NOT just B2C like old versions)
  - Status filter: `status NOT LIKE '%merged%' AND NOT LIKE '%ignored%' AND NOT LIKE '%canceled%' AND NOT LIKE '%merge_pending%'`
  - Date: `so.CREATED_AT >= month_start AND so.CREATED_AT < today`
- **MTD orders:** `COUNT(*)`
- **MTD customers:** `COUNT(DISTINCT so.EMAIL)`
- **YoY:** Same calendar range last year, same filters
- **Matches:** Looker dashboard 1156 "Swatch Orders" and "Swatch Customers" tiles

> ⚠️ **Note:** Earlier versions used B2C-only filter. Looker tiles include Trade, which gives higher numbers (~8% more). Always use `IN ('B2C','Trade')`.

---

### Section: Merch Contribution (bar chart)

**What it shows:** MTD revenue by product class (Sectionals, Sofas, Chairs, etc.) with unit count and AUR, sorted by revenue.

- **Source:** `ORDER_ITEMS` × `PRODUCTS` × `ORDERS`
- **Filters:**
  - `o.ORDER_TYPE = 'standard' AND o.CANCELLATION = 'F'`
  - `p.ITEM_CLASSIFICATION = 'Merchandise'` — excludes swatches, warranties, accessories
  - `p.CLASS IS NOT NULL`
  - Denver timezone MTD date filter
- **Revenue:** `SUM(oi.PRICE)` per class
- **Units:** `COUNT(oi.SALES_ORDER_ITEM_ID)` per class
- **AUR:** `SUM(oi.PRICE) / COUNT(oi.SALES_ORDER_ITEM_ID)` per class
- **Bar width:** Proportional to % of total Merchandise revenue
- **Matches:** Looker `qid=B2YtIQC4p3yQuoUBBFvThb`

> ⚠️ **Note:** The `ITEM_CLASSIFICATION = 'Merchandise'` filter is critical. Without it, total is ~20% higher (includes swatches, warranties). Always keep this filter.

---

### Section: Studio Performance (table)

**What it shows:** MTD revenue, orders, AOV, % of deals, MTD CVR, 90-day CVR, and "% of baseline" for each studio.

#### Revenue, Orders, AOV columns
- **Source:** Snowflake `STG_DEAL` — `hubspot_deals.studio_name` (NOT `ORDERS.LOCATION`)
- **Query:** `SUM(DEAL_AMOUNT)` from `STG_DEAL` where `IS_CONVERTED = TRUE` and `CLOSE_DATE` in MTD range and `STUDIO_NAME` is a real studio
- **Why STG_DEAL not ORDERS.LOCATION:** The Looker dashboard (Looker explore `interior_define/orders`, saved query `g8UAPEJnqwtT67Z3PrHejp`) uses `hubspot_deals.studio_name`. The two can differ by ~10–20% per studio because website/online orders get attributed differently.
- **Date filter:** `CLOSE_DATE` in CDT timezone BETWEEN month_start AND yesterday (no order_type/cancel filter — matches Looker tile)

#### % of Deals column
- **Source:** `STG_DEAL` grouped by `STUDIO_NAME`, using `CREATE_DATE` in MTD range
- **Formula:** studio inbound count ÷ total inbound across all studios MTD

#### MTD CVR column
- **Source:** Looker `hubspot_contacts` explore — `hubspot_deals.deal_conversion_rate`
- **Filter:** `hubspot_deals.deal_type != 'Direct Order'`, MTD CREATE_DATE range, real studios only
- **Definition:** Closed Won ÷ total inbound deals for that studio MTD

#### 90-Day CVR column
- **Source:** Same Looker query but `CREATE_DATE` over last 90 days
- **Purpose:** Provides a baseline for each studio's typical CVR so MTD can be compared in context

#### % of Baseline column (last column)
- **Formula:** MTD CVR ÷ 90-Day CVR — "what fraction of their normal close rate is this studio hitting this month?"
- **Color coding:**
  - Purple bar: MTD CVR ≥ group average
  - Gray bar: MTD CVR < group average
  - Gray tick mark: 90-day baseline position
  - ▲ green / ▼ red label: whether MTD % is above or below the group average

---

### Section: Inbound CVR Maturation Chart (combo chart)

**What it shows:** SVG combo chart — bars = monthly inbound contact volume, 4 lines = CVR at 14/30/60/90 days for each cohort (Jan–current month 2026).

**What it answers:** "Are leads from February converting faster/better than March? Which months had the strongest early conversion?"

**Data source:** Snowflake `STG_HUBSPOT_ENGAGEMENTS_BASE` × `STG_CONTACTS`

**Query logic:**
1. For each contact, find their first inbound engagement date within each calendar month
2. Check if they placed an order within 14, 30, 60, or 90 days of that first engagement
3. CVR = contacts with order ÷ total inbound contacts in that cohort month

**Filters:**
- Same studio exclusions and B2C-only filter as inbound engagements
- Engagements: `ENGAGEMENT_DIRECTION = 'Incoming'`, `ENGAGEMENT_TYPE NOT IN ('NOTE','TASK')`
- Orders must be placed ON OR AFTER first inbound engagement

**Reading the chart:**
- Tall bars = high inbound volume that month
- Lines rising steeply from 14D→30D→90D = long conversion tail (buyers take time to decide)
- Lines flat across 14D→30D = quick decision-makers, conversion happens fast
- Current month (e.g., June) will show same % for all windows since it hasn't had time to mature

> ⚠️ **The current month's CVR is not meaningful** — all windows will show the same low number since the month is in progress. Only compare prior complete months.

---

## Tab 2: Sales Team

### Section: Yesterday — Net Sales

**What it shows:** HubSpot deal revenue for the prior day (Sunday), vs retail forecast, plus Top 5 Studios and Top 5 Individuals bars.

#### Net Sales (TY)
- **Source:** HubSpot API — `POST /crm/v3/objects/deals/search`
- **Filters:**
  - `dealstage IN ('957899065', 'closedwon', '264c3b2f-856c-4973-b659-95b5f775dc8b')` — Closed Won across all pipelines
  - `meaningful_contact_ = 'true'` — only deals with Meaningful Contact = Yes
  - `hubspot_owner_id HAS_PROPERTY` — known rep
  - `hs_all_team_ids HAS_PROPERTY` — deal assigned to a studio team
  - `closedate BETWEEN yesterday_midnight_UTC AND today_midnight_UTC`
- **Revenue field:** `amount` (post-discount, excludes tax and shipping)

#### Net Sales YoY (LY)
- **Source:** Snowflake `STG_DEAL` — NOT the HubSpot API for LY
- **Why different source:** HubSpot's Meaningful Contact field (`meaningful_contact_`) only existed from Aug 2025 onward. Applying it to 2025 data gives wrong (too low) LY numbers.
- **Pre-Aug 2025 methodology (for LY):** A deal is "engaged/assisted" if at least one of these stage entry dates is within 0–120 days before close date:
  - `CONNECTED_STAGE_DATE` (stage 957899062)
  - `LOGGED_MEETING_STAGE_DATE` (stage 957899063)
  - `QUOTE_GENERATED_STAGE_DATE` (stage 957899064)
- **LY date filter:** Same calendar date last year (e.g., if yesterday = Jun 15, 2026, LY = Jun 15, 2025)
- **LY query:** `STG_DEAL` where `CLOSE_DATE = LY_yesterday AND IS_CONVERTED = TRUE` and the stage-date engagement filter above

#### vs Forecast (Yesterday)
- **Forecast source:** Google Sheet `1lJcsmRhG3ScG8s2ol2jPwUBJ18n20MMn101rXc1ZQp0` tab "For claude_add each month"
- **Value:** That specific day's forecasted dollar amount from the sheet
- **Note:** This is the **retail/studio plan** — different from the Snowflake company forecast on Tab 1. Much lower.

#### Top 5 Studios / Top 5 Individuals
- **Source:** Same HubSpot API pull, aggregated by studio team and by deal owner
- **Studio:** HubSpot's `hs_owning_teams` team name
- **Individual:** Rep name from `GET /crm/v3/owners` (includes inactive reps)
- **Sorted:** Revenue descending

---

### Section: Closing Notes — Yesterday

**What it shows:** Synthesized summary of what studios posted to `#id--retail-closing-notes` on Slack for the prior day.

- **Source:** Slack MCP — `slack_read_channel` on channel `C08MYB2S3DH`
- **Time window:** Notes posted on the prior day (studios typically post 5–9pm local time)
- **Content:** Studio traffic, closes, pipeline highlights, watch items
- **Format:** Claude-synthesized narrative highlighting key themes across all studios

> ⚠️ **Saturday notes:** Studios do not always post on Saturdays. If running a Monday report after a Saturday with no notes, the section will indicate this.

---

### Section: % Meaningful Contact by Studio (visual bars)

**What it shows:** For each studio, what % of their inbound deals this month have Meaningful Contact = Yes, compared to their 90-day baseline.

**What it answers:** "Which studios are engaging their leads before closing? Is the engagement rate improving or declining vs their recent baseline?"

#### Data source
- **Snowflake:** `PROD.ID_WAREHOUSE.STG_DEAL`
- **MTD filter:** `CREATE_DATE` in CDT timezone BETWEEN month_start AND yesterday
- **90D filter:** `CREATE_DATE` in last 90 days
- **Exclusions:** `DEAL_TYPE != 'Direct Order'`, `STUDIO_NAME NOT IN ('Assisted No Studio','Automated DE','Santa Monica')`

#### Metrics per studio
- **MC%:** `SUM(CASE WHEN MEANINGFUL_CONTACT=TRUE THEN 1 ELSE 0 END) / COUNT(*)`
- **MC=Yes CVR:** Close rate on MC=Yes deals this month
- **MC=No CVR:** Close rate on MC=No deals (typically 1–2%, vs 8–16% for MC=Yes)

#### Visual interpretation
- **Bar:** MTD MC% (purple = above group average, gray = below)
- **Gray tick:** 90-day baseline position
- **▲/▼:** Whether studio's MC% is tracking above or below their 90D baseline
- **"% of Baseline" in group note:** Group average = weighted avg of (MTD MC% / 90D MC%) across all studios

> 💡 **Why this matters:** MC=Yes deals close at 5–26x the rate of MC=No deals. A studio with high MC% is engaging leads before close — this is a leading indicator of their CVR performance.

---

### Section: Inbound CVR by Studio (visual bars)

**What it shows:** Ranked bar chart of each studio's MTD inbound→order conversion rate, with an average line.

**Definition:** For B2C contacts who had their first inbound engagement MTD, what % placed an order on or after that first contact, within the MTD window.

- **Source:** Snowflake `STG_HUBSPOT_ENGAGEMENTS_BASE` × `STG_CONTACTS`
- **Filters:** Same as overall inbound engagements (B2C, studio exclusions, incoming direction)
- **Date:** First inbound BETWEEN month_start AND yesterday
- **Order must be:** on or after the first inbound contact
- **Sorted:** CVR descending
- **Color:** Green = above average, teal = near average, red = below average
- **Average line:** Gray tick at group average position

---

### Section: MTD — Net Sales

**What it shows:** HubSpot MTD deal revenue vs Google Sheet forecast, YoY comparison, Top 5 Individuals, All Studios ranked by revenue.

#### Net Sales TY (MTD)
- **Source:** HubSpot API — same filters as yesterday but `closedate` range = month_start through yesterday
- **Important:** The MTD total is validated against HubSpot's "MTD Sales by Team" dashboard to ensure exact match. Small discrepancies can occur due to team attribution (see note below).

#### Net Sales LY (MTD)
- **Source:** Snowflake `STG_DEAL` with pre-Aug 2025 stage-date methodology
- **LY range:** Same calendar range last year (month_start LY through yesterday LY)
- **Methodology:** Same 0–120 day stage date rule as yesterday LY

#### vs Forecast (MTD)
- **Forecast:** Sum of daily forecast values from the Google Sheet for month_start through yesterday

#### Pacing note
- **Pacing %:** Sum of daily forecast values through yesterday ÷ full month total from Google Sheet
- **Example:** If Jun 1–14 forecast = $1.95M and Jun total = $5.18M, pacing = 37.7%

---

### Section: Closing Notes — Week

**What it shows:** Synthesized summary of the full week's closing notes from `#id--retail-closing-notes`.

- **Source:** Slack MCP — all posts in channel `C08MYB2S3DH` from Monday through Sunday of the prior week
- **Format:** Key themes across the week (sale performance, pipeline, CX issues, watch items)

---

### Section: Team % to Paced Goal

**What it shows:** For each studio: June goal, paced target, MTD actual, % of goal achieved, % to paced target, and status badge.

| Column | Source | Formula |
|---|---|---|
| Jun Goal | Google Sheet goals file, "for claude" tab | Monthly goal by studio |
| Paced | Jun Goal × Pacing % | Where pacing % = MTD forecast ÷ full-month forecast |
| MTD Actual | HubSpot API deal revenue by studio team | MC=Yes + Closed Won + team known |
| % of Goal | MTD Actual ÷ Jun Goal | |
| % Paced | MTD Actual ÷ Paced | Color-coded bar |
| Status | Ahead ≥110% · On Track 90–110% · Behind 70–90% · At Risk <70% | Color badge |

---

### Section: Individual % to Paced Goal

**What it shows:** Same pacing logic as team table but broken down by rep.

| Column | Source |
|---|---|
| Rep | Goals sheet — email prefix matched to HubSpot owner name |
| Studio | Goals sheet |
| Goal | Goals sheet — individual monthly goal (Design Expert vs Senior Design Expert tiers) |
| Paced | Rep Goal × Pacing % |
| Actual | HubSpot API — deal revenue filtered to that rep's `hubspot_owner_id`, including inactive owners |
| % Paced | Color-coded bar + status badge |

> ⚠️ **Name matching:** Rep names in HubSpot can differ from the goals sheet (e.g., "julie.alfonso" → "Jules Alfonso", "luz.rivera" → "Lucy Rivera"). The script has an email-to-name mapping that handles known mismatches. If a new rep appears and their numbers show as $0, check the `REP_GOALS` dict in `run_from_mcp.py` and add their email prefix.

---

## YoY Methodology — Hybrid Approach

**The core problem:** HubSpot's "Meaningful Contact" field (`meaningful_contact_`) was not used systematically before August 2025. Applying the current MC=Yes filter to 2025 historical data would dramatically undercount LY (only ~40–50% of 2025 deals have MC=Yes vs ~80% expected).

**Solution: Hybrid methodology**

| Period | Source | Filter |
|---|---|---|
| **2026 (TY)** | HubSpot API | `meaningful_contact_ = 'true'` + Closed Won + team known |
| **2025 (LY)** | Snowflake `STG_DEAL` | At least one stage date (Connected, Logged Meeting, or Quote Generated) within 0–120 days before close |

**LY stage date filter:**
```sql
(CONNECTED_STAGE_DATE IS NOT NULL AND DATEDIFF(day, CONNECTED_STAGE_DATE, CLOSE_DATE) BETWEEN 0 AND 120)
OR (LOGGED_MEETING_STAGE_DATE IS NOT NULL AND DATEDIFF(day, LOGGED_MEETING_STAGE_DATE, CLOSE_DATE) BETWEEN 0 AND 120)
OR (QUOTE_GENERATED_STAGE_DATE IS NOT NULL AND DATEDIFF(day, QUOTE_GENERATED_STAGE_DATE, CLOSE_DATE) BETWEEN 0 AND 120)
```

**Why this is apples-to-apples:** In 2025, reps logged activities on contact records (reflected in stage dates). In 2026, reps flag Meaningful Contact on deals. Both capture the same behavior — a rep substantively engaged a client before they closed.

**Memory note:** This is documented in the `id-inbound-cvr` skill and `project_id_hubspot_engaged_pipeline` memory.

---

## Data Source Hierarchy

When sources conflict, use this order:

| Metric | Authoritative Source | Why |
|---|---|---|
| Yesterday/MTD revenue by segment | Looker dashboard 1156 (via Snowflake `ORDERS`) | Validated against Looker |
| AOV (blended, B2C, Trade) | Looker API calendar pivot tiles | Dashboard uses `average_order_value`, not revenue/count |
| Inbound engagements | Snowflake direct query | Exact match to Looker dashboard 1156 tile |
| Swatch orders/customers | Snowflake (B2C+Trade, status filter) | Matches Looker "Swatch Orders" tile |
| Merch contribution | Snowflake (item_classification=Merchandise) | Matches Looker |
| Studio revenue (Total Business) | Snowflake `STG_DEAL.DEAL_AMOUNT` by `STUDIO_NAME` | Matches Looker explore `g8UAPEJnqwtT67Z3PrHejp` |
| Assisted % | Looker (MC=Yes revenue ÷ total revenue) | Revenue-based, matches "% Asst Sales" tile |
| Repeat % | Snowflake direct | No Looker tile available |
| Sales Team TY revenue | HubSpot API (MC=Yes + Closed Won) | Exact match to HubSpot dashboard |
| Sales Team LY revenue | Snowflake pre-Aug methodology | HubSpot MC= field didn't exist in 2025 |
| Forecast % (Total Business) | Snowflake `FIVETRAN_DB.UPLOADS.ALL_COMPANY_DAILY_FORECAST` | Full company plan |
| Forecast % (Sales Team) | Google Sheet retail plan | Studio-specific plan |
| Pacing goals | Google Sheet | Set monthly by finance/leadership |

---

## Known Issues & Workarounds

1. **HubSpot API ≠ dashboard exactly:** The HubSpot API for TY deals (~$817K for Jun 1-13 example) returned far less than the dashboard ($1.73M) due to a pipeline stage ID issue. The current approach uses `STG_DEAL` for Snowflake data and the HubSpot API directly for real-time deal data. The MTD_HS_TOTAL value is validated against the HubSpot dashboard manually.

2. **Dallas/WDC revenue discrepancy:** Some studios show ~$15–18K difference between Snowflake `STG_DEAL` and the HubSpot dashboard. This is likely due to multi-team deal attribution. The script uses Snowflake as the source for the studio revenue table. If a studio's revenue looks wrong, cross-check against HubSpot dashboard "MTD Sales by Team."

3. **New reps not showing in pacing table:** If a rep is hired and has a goal but shows $0 actual, add them to the `REP_GOALS` dict in `run_from_mcp.py` with their email prefix as the key. Format: `"first.last": ("Full Name", "Studio", goal_amount)`

4. **Swatch status filter:** The `%merge_pending%` pattern uses a literal underscore in a LIKE clause. In Snowflake, `_` matches any single character. This is intentional — it matches both `merge_pending` and any variant. If swatch counts seem inflated, verify this filter is being applied.

5. **November DST:** The cron runs at 13:00 UTC. When DST ends in November, update to `0 14 * * 1` at https://claude.ai/code/routines/trig_01RswSW7MsvW5ZGDdvKMhqB5 → Edit.

6. **Monthly CVR chart — current month:** The current month's CVR lines are not meaningful (all windows show the same low %). Only compare prior complete months. The current month bar is grayed out as a visual indicator.

7. **Studio name mismatches:** The `STUDIO_MTD_CVR` and `MC_DATA` lists in the script are updated each Monday by the agent via fresh Snowflake queries. If a studio is renamed in HubSpot, it may not match the existing list. The agent should handle this automatically via the live queries.

---

## Updating the Report

### Adding a new metric
1. Identify the data source (Snowflake table, HubSpot API, Looker tile)
2. Write and validate the SQL query against Looker dashboard manually
3. Add the data variable in the `# ── DATA` section of `run_from_mcp.py`
4. Add the rendering HTML in the appropriate `tab1()` or `tab2()` function
5. Commit and push — next Monday's run will include the new metric

### Changing which studios appear
The studios list is hardcoded in `STUDIOS_ORDERS` and `MC_DATA` in `run_from_mcp.py`. If a studio opens or closes, update these lists.

### Adding/removing email recipients
Update the email addresses in Step 8 of the Claude remote agent prompt at:
https://claude.ai/code/routines/trig_01RswSW7MsvW5ZGDdvKMhqB5 → Edit

### Pausing the automation
Go to https://claude.ai/code/routines/trig_01RswSW7MsvW5ZGDdvKMhqB5 and toggle "Enabled" off.
