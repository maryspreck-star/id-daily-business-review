# Daily Business Review — Data Methodology

**Last updated:** 2026-06-14  
**Report periods:** Yesterday · Last Week (Mon–Sun) · MTD  
**Source file:** `src/collectors/snowflake.py` (Snowflake) · `src/collectors/deals.py` (deals/CVR) · `src/collectors/hubspot_activities.py` (HubSpot API) · `src/collectors/slack_notes.py` (Slack)

---

## Tab 1: Total Business

### Data sources
| Source | Used for |
|---|---|
| `PROD.ID_WAREHOUSE.ORDERS` + `ID_WAREHOUSE.CUSTOMERS` | Revenue, orders, AOV, segments, assisted %, UPT, repeat % |
| `FIVETRAN_DB.UPLOADS.ALL_COMPANY_DAILY_FORECAST` | Forecast (Looker source, column: `ID_FORECASTED_ADJUSTED_GROSS_BOOKINGS`) |
| `PROD.ID_WAREHOUSE.STG_HUBSPOT_ENGAGEMENTS_BASE` + `STG_CONTACTS` | Inbound Engagements |
| `PROD.ID_WAREHOUSE.SWATCH_ORDERS` + `STG_CONTACTS` | Swatch Performance |
| `PROD.ID_WAREHOUSE.ORDER_ITEMS` + `PRODUCTS` | Merch Contribution (product class, collection, fabric) |
| `PROD.ID_WAREHOUSE.STG_DEAL` | Studio Deal CVR |

---

### Yesterday / MTD — Revenue section

#### Revenue (Net Sales)
- **Formula:** `SUM(subtotal - ABS(discount_amount) + shipping_amount)`
- **Table:** `PROD.ID_WAREHOUSE.ORDERS o INNER JOIN ID_WAREHOUSE.CUSTOMERS c ON o.CUSTOMER_ID = c.CUSTOMER_ID`
- **Filters:**
  - Staff excluded: `c.EMAIL NOT LIKE '%@interiordefine.com%' OR c.EMAIL IS NULL`
  - Date: Denver timezone — `CONVERT_TIMEZONE('UTC', 'America/Denver', CAST(ORDER_CREATED_AT AS TIMESTAMP_NTZ))::DATE`
- **Matches:** Looker `orders.md_order_revenue`

#### Orders
- **Formula:** `COUNT(*)` on the same filtered order set

#### vs Forecast
- **Source:** `FIVETRAN_DB.UPLOADS.ALL_COMPANY_DAILY_FORECAST`
- **Column:** `ID_FORECASTED_ADJUSTED_GROSS_BOOKINGS`
- **Date join:** `TO_CHAR(TO_DATE(Date), 'YYYY-MM-DD')` matched to order date
- **Matches:** Looker explore `qid=FwUaEg4OKq7RHaff4IXB5A`

#### AOV (Blended, B2C, Trade)
- **Formula:** `SUM(NET_BOOKINGS_ESTIMATED) / (COUNT(DISTINCT SALES_ORDER_ID) * 0.91)`
- The `0.91` factor accounts for estimated ~9% cancellation/return rate
- **Matches:** Looker `orders.average_order_value`

---

### Revenue by Customer Class

#### Segments
- **Column:** `CASE WHEN c.CUSTOMER_ID = 20 THEN 'Havenly' ELSE c.CUSTOMER_GROUP_CLASS END`
- **Values:** B2C · Trade · Havenly (customer_id=20) · B2B
- **YoY (MTD):** same calendar days prior year

---

### Assisted Sales % and UPT

- **Table:** `PROD.ID_WAREHOUSE.ORDERS` (standard, non-cancelled)
- **Filters:** `ORDER_TYPE = 'standard' AND CANCELLATION = 'F'` + Denver timezone date filter
- **Assisted %:** `SUM(CASE WHEN INDIVIDUAL IS NOT NULL AND INDIVIDUAL != '' THEN 1 ELSE 0 END) / COUNT(*)`
  - `INDIVIDUAL` field on the order indicates a studio rep assisted the sale
- **UPT (Units per Transaction):** total line items from `ORDER_ITEMS` ÷ total orders for the same period
- **Period:** Yesterday only (not MTD)
- **Source function:** `fetch_yesterday_assisted()` in `snowflake.py`

---

### Repeat Customer %

- **Table:** `PROD.ID_WAREHOUSE.ORDERS` (standard, non-cancelled)
- **Definition:** MTD orders where the customer placed at least one order before the current month
- **Method:**
  1. Pull all MTD order IDs + customer IDs
  2. Find each customer's `MIN(order_date)` across all-time orders
  3. `repeat_pct = orders where first_order_date < month_start / total MTD orders`
- **Period:** MTD
- **Source function:** `fetch_mtd_repeat_pct()` in `snowflake.py`

---

### Swatch Performance

- **Table:** `PROD.ID_WAREHOUSE.SWATCH_ORDERS so JOIN STG_CONTACTS c ON LOWER(so.EMAIL) = LOWER(c.CONTACT_EMAIL)`
- **Filter:** `c.CUSTOMER_GROUP = 'B2C'`
- **MTD orders:** `COUNT(*)` where `CREATED_AT` in current month
- **MTD customers:** `COUNT(DISTINCT so.EMAIL)`
- **Rolling chart:** 6 prior complete months (oldest first), same filters
- **YoY:** same month prior year
- **Source function:** `fetch_swatches()` in `snowflake.py`

---

### Merch Contribution

All three breakdowns use the same base join and filters:

- **Tables:** `ORDER_ITEMS oi JOIN PRODUCTS p ON oi.CATALOG_PRODUCT_ID = p.CATALOG_PRODUCT_ID JOIN ORDERS o ON oi.SALES_ORDER_ID = o.SALES_ORDER_ID`
- **Filters:** `o.ORDER_TYPE = 'standard' AND o.CANCELLATION = 'F'` + Denver timezone MTD date filter on `o.ORDER_CREATED_AT`
- **Revenue metric:** `SUM(oi.PRICE)` per category
- **% Mix:** category revenue ÷ total revenue for that breakdown
- **Bar width:** relative to the top category (100% = highest)

#### By Product Class (primary chart)
- **Column:** `p.CLASS` (e.g. Sectionals, Sofas, Chairs, Beds)
- **Matches:** Looker `qid=B2YtIQC4p3yQuoUBBFvThb`

#### By Collection
- **Column:** `p.COLLECTION` (e.g. Topher, Austin, Jarvis)
- Rows with `NULL` COLLECTION excluded

#### By Fabric Family
- **Column:** `p.FABRIC_FAMILY` (e.g. Performance, Velvet, Leather)
- Rows with `NULL` FABRIC_FAMILY excluded

- **Source function:** `fetch_merch_mix()` in `snowflake.py`

---

### Studio Performance MTD

#### Discounted Revenue, Orders, AOV (from Snowflake ORDERS)
- **Table:** `PROD.ID_WAREHOUSE.ORDERS`
- **Column grouped by:** `LOCATION` field on the order (the studio that placed/assisted the order)
- **Filter:** standard + non-cancelled + Denver timezone MTD date filter + `LOCATION IS NOT NULL`
- **Formula:** `SUM(subtotal - ABS(discount_amount) + shipping_amount)` per studio
- **Source function:** `fetch_by_studio()` in `snowflake.py`
- **Note:** This uses `ORDERS.LOCATION`, which differs from HubSpot's `hubspot_deals.studio_name`. The two may not align exactly for assisted/online-initiated orders.

#### % of Deals and Deal CVR (from STG_DEAL)
- **Table:** `PROD.ID_WAREHOUSE.STG_DEAL`
- **Date filter:** MTD (month start – today, Denver timezone)
- **Staff exclusion:** `DEAL_OWNER_EMAIL NOT LIKE '%@interiordefine.com%' OR DEAL_OWNER_EMAIL IS NULL`
- **% of Deals:** studio inbound ÷ total inbound across all studios (MTD)

##### Two CVR methods (both computed, report displays based on cohort maturity):

**14-Day Mature Cohort CVR** (`cvr_14day_mtd`)
- Denominator: deals created more than 14 days ago (`CREATE_DATE < today − 14 days`)
- Numerator: those mature deals where `14_DAY_CONVERTED = 1`
- Used when sufficient cohort maturity exists; avoids penalizing fresh leads

**Meaningful Contact CVR** (`cvr_meaningful_mtd`)
- Denominator: MTD deals where `MEANINGFUL_CONTACT = 1`
- Numerator: meaningful deals where `IS_CONVERTED = 1`
- Aligns with HubSpot's internal reporting definition (post-Aug 2025 methodology)

- **Source function:** `fetch_deals()` in `deals.py`

---

### Inbound Engagements

- **Table:** `PROD.ID_WAREHOUSE.STG_HUBSPOT_ENGAGEMENTS_BASE e JOIN STG_CONTACTS c ON e.CONTACT_ID = c.PRIMARY_HUBSPOT_ID`
- **Filters:**
  - `ENGAGEMENT_TYPE NOT IN ('NOTE', 'TASK')`
  - `ENGAGEMENT_DIRECTION = 'Incoming'`
  - `c.CUSTOMER_GROUP = 'B2C'`
  - Studio exclusions: `c.STUDIO_NAME NOT IN ('The Inside', 'Burrow', 'General Managers', 'Remote Sales')`
  - Denver timezone on `e.CREATED_AT`
- **Count:** `COUNT(DISTINCT c.PRIMARY_HUBSPOT_ID)` (distinct contacts per day, not raw engagement events)
- **Matches:** Looker dashboard 1156 "Daily Inbound Engagement" tile exactly

#### KPI cards
- **Yesterday:** engagement count for yesterday (Denver date)
- **YoY:** same day-of-week prior year (yesterday − 364 days, preserving Mon/Tue/etc. alignment)

#### Rolling 4-week chart
- **Weeks:** 4 complete prior weeks, each anchored to Monday (Mon–Sun)
- Week starts computed in Python: `this_monday − 1, 2, 3, 4 weeks`, displayed oldest → newest
- All 6 dates (yesterday, LY date, 4 week-starts) fetched in a single SQL query with an `IN` clause

- **Source function:** `fetch_engagements()` in `snowflake.py`

---

## Tab 2: Sales Team

### Data sources
| Source | Used for |
|---|---|
| HubSpot CSV export | Revenue (Net Sales) — exact match to dashboard |
| Google Sheet `1lJcsmRhG3ScG8s2ol2jPwUBJ18n20MMn101rXc1ZQp0` tab "For claude_add each month" | Daily retail forecast (studio plan) |
| Google Sheet `1CkbEVt9utgqkO4xbCnxpc1A6tJCTTRaXWo_iQZQiyJw` tab "for claude" | Monthly rep and team goals |
| `PROD.ID_WAREHOUSE.STG_DEAL` | Deal CVR, inbound volume, by-studio and by-rep breakdowns |
| HubSpot API `/crm/v3/owners` | Rep → primary studio team mapping |
| HubSpot API `/crm/v3/objects/calls/search` + `/meetings/search` | MTD call and meeting counts per rep |
| `#id--retail-closing-notes` Slack channel (ID: C08MYB2S3DH) | Closing notes narrative |

---

### Net Sales (HubSpot)

- **Source:** HubSpot CSV export — `hubspot-crm-exports-all-deals-YYYY-MM-DD.csv`
- **Filter:** `Deal Stage = "Closed Won"` (any of 3 pipelines) AND `Meaningful Contact? = Yes` AND `HubSpot Team` known AND `Close Date` in period
- **Metric:** `Amount` (deal amount field, post-discount, excludes tax/shipping)
- **Matches:** HubSpot dashboard "MTD Sales by Team" — `qid=10022704`
- **Note:** Snowflake and the HubSpot API return ~$65K more than the dashboard due to an internal HubSpot reporting engine difference. CSV export gives exact match.

#### vs Forecast
- **Source:** Google Sheet daily retail forecast (studio plan)
- **File:** `1lJcsmRhG3ScG8s2ol2jPwUBJ18n20MMn101rXc1ZQp0` → tab "For claude_add each month"
- **Note:** This is the retail/studio plan — different and lower than the Snowflake company-wide forecast used on Tab 1

---

### Top Studios / Top Individuals (Yesterday & Last Week)

- **Revenue:** From HubSpot CSV, same filter as Net Sales above
- **Grouped by:** `HubSpot Team` (studio) and `Deal owner` (rep name)
- **Sorted:** by revenue descending

---

### Pacing — Team % to Goal

- **Goals:** Google Sheet `1CkbEVt9utgqkO4xbCnxpc1A6tJCTTRaXWo_iQZQiyJw` — monthly goal by studio
- **Pacing %:** MTD forecast ÷ full-month forecast (daily distribution from Google Sheet)
  - Example: Jun 1–7 forecast ($1.24M) ÷ June total forecast ($5.18M) = 24.0%
- **Paced target:** Monthly goal × pacing %
- **Actual:** MTD HubSpot revenue from CSV (same filter as Net Sales)
- **% to Paced:** Actual ÷ Paced target
- **Status:** Ahead ≥110% · On Track 90–110% · Behind 70–90% · At Risk <70%

---

### Pacing — Individual % to Goal

- **Goals:** Google Sheet — monthly goal per rep (Design Expert vs. Senior Design Expert tiers)
- **Actuals:** MTD HubSpot CSV revenue filtered to each rep (`Deal owner` field)
- **Same pacing %, status logic as team table above**

---

### Activity by Studio (Calls & Meetings per rep)

- **Source:** HubSpot API
  - Calls: `POST /crm/v3/objects/calls/search` filtered by `hubspot_owner_id` + `hs_createdate ≥ month start (ms)`
  - Meetings: `POST /crm/v3/objects/meetings/search`, same filters
- **Team attribution:** HubSpot owners API (`GET /crm/v3/owners`) — primary studio team from `hs_teams` where `primary=true` and team name matches known studio list
- **Studio list:** New York, Chicago, Minneapolis, Seattle, Dallas, Charlotte, Los Angeles, Washington DC, Boston, Denver, Philadelphia, San Francisco, Baltimore
- **Displayed as:** total calls + meetings per studio, calls-per-rep average, meetings-per-rep average
- **Rate limiting:** 120ms sleep between each API call to stay under HubSpot's 100 req/10s limit
- **Note:** SMS and Chat not yet included (HubSpot sync limitation)
- **Source function:** `fetch_activities()` in `hubspot_activities.py`

---

### Closing Notes

- **Source:** Slack channel `#id--retail-closing-notes` (channel ID: `C08MYB2S3DH`)
- **Date range:** Yesterday — notes posted between noon and midnight CDT
- **Last Week** — full week recap synthesized from all daily notes
- **Format:** Human-synthesized summary of key themes (traffic, closes, watch items)

---

## Forecast sources summary

| Tab | Forecast source | Column / sheet |
|---|---|---|
| Total Business | `FIVETRAN_DB.UPLOADS.ALL_COMPANY_DAILY_FORECAST` | `ID_FORECASTED_ADJUSTED_GROSS_BOOKINGS` |
| Sales Team | Google Sheet `1lJcsmRhG3ScG8s2ol2jPwUBJ18n20MMn101rXc1ZQp0` | Daily $ from "For claude_add each month" tab |

The two sources differ significantly — the Snowflake/Looker forecast is the full company plan (all channels), while the Google Sheet is the retail studio plan calibrated to HubSpot deal revenue.

---

## Known limitations & open items

1. **HubSpot revenue automation:** CSV export must be done manually each morning. The API and Snowflake return ~$65K more than the HubSpot dashboard (internal reporting engine difference unresolved). Blocking full automation.
2. **LY comparison for Sales tab:** Uses Snowflake with MC=Yes filter, which gives different LY totals than the CSV approach (2025 historical export not available).
3. **SMS/Chat activities:** Not included in activity table — not synced to Snowflake, HubSpot API scopes needed.
4. **GitHub Actions cron:** Not yet live — requires `SENDGRID_API_KEY` in GitHub secrets + repo push.
5. **Swatch CVR by window:** Deferred — requires complex cohort SQL to match Looker exactly.
6. **Studio revenue source discrepancy:** Tab 1 studio table uses `ORDERS.LOCATION`; Tab 2 and Looker use `hubspot_deals.studio_name`. These can differ for online-initiated orders with studio assists.
