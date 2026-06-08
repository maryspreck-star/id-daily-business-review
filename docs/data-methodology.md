# Daily Business Review — Data Methodology

**Last updated:** 2026-06-08  
**Report periods:** Yesterday · Last Week (Mon–Sun) · MTD

---

## Tab 1: Total Business

### Data sources
| Source | Used for |
|---|---|
| `PROD.ID_WAREHOUSE.ORDERS` + `ID_WAREHOUSE.CUSTOMERS` | Revenue, orders, AOV, segments |
| `FIVETRAN_DB.UPLOADS.ALL_COMPANY_DAILY_FORECAST` | Forecast (Looker source, column: `ID_FORECASTED_ADJUSTED_GROSS_BOOKINGS`) |
| `PROD.ID_WAREHOUSE.STG_HUBSPOT_ENGAGEMENTS_BASE` + `STG_CONTACTS` | Inbound Engagements |
| `PROD.ID_WAREHOUSE.SWATCH_ORDERS` + `STG_CONTACTS` | Swatch Performance |
| `PROD.ID_WAREHOUSE.ORDER_ITEMS` + `PRODUCTS` | Merch Contribution |
| `PROD.ID_WAREHOUSE.STG_DEAL` | Studio Deal CVR |

---

### Yesterday / Last Week / MTD — Revenue section

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
- **YoY:** same date range prior year

---

### Swatch Performance

- **Table:** `PROD.ID_WAREHOUSE.SWATCH_ORDERS so JOIN STG_CONTACTS c ON LOWER(so.EMAIL) = LOWER(c.CONTACT_EMAIL)`
- **Filter:** `c.CUSTOMER_GROUP = 'B2C'`
- **MTD orders:** `COUNT(*)` where `CREATED_AT` in current month
- **MTD customers:** `COUNT(DISTINCT so.EMAIL)`
- **YoY:** same month prior year

---

### Merch Contribution (Merchandise · MTO + QS)

- **Tables:** `ORDER_ITEMS oi JOIN PRODUCTS p ON oi.CATALOG_PRODUCT_ID = p.CATALOG_PRODUCT_ID JOIN ORDERS o ON oi.SALES_ORDER_ID = o.SALES_ORDER_ID`
- **Filters:**
  - `o.ORDER_TYPE = 'standard' AND o.CANCELLATION = 'F'`
  - `p.ITEM_CLASSIFICATION = 'Merchandise'`
  - `p.FULFILLMENT_CLASSIFICATION IN ('Made To Order', 'Quickship')`
  - Denver timezone date filter on `o.ORDER_CREATED_AT`
- **Revenue column:** `p.CLASS` (Sectionals, Sofas, Chairs, Beds, etc.)
- **AUR:** `SUM(oi.PRICE) / COUNT(oi item)` per class
- **% Mix:** category revenue / total merch revenue
- **Bar width:** relative to top category (Sectionals = 100%)
- **Matches:** Looker `qid=B2YtIQC4p3yQuoUBBFvThb`

---

### Studio Performance MTD

#### Discounted Revenue, Orders, AOV
- **Source:** Looker `qid=ZZ8GuCGmVK8zpmRaT1GeHM`
- **Formula:** `orders.md_order_revenue` grouped by `hubspot_deals.studio_name`
- **Excludes:** null studio (Website/unattributed), "Assisted No Studio"

#### % of Deals, Deal CVR
- **Source:** Looker `qid=M9kJPDOwBaf7plmqMxRte2` (hubspot_contacts explore)
- **Table in Snowflake:** `PROD.ID_WAREHOUSE.STG_DEAL`
- **Date filter:** MTD (June 1 – current date), no staff filter (studio reps have @interiordefine.com emails)
- **Filter:** `DEAL_TYPE != 'Direct Order'`
- **% of Deals:** studio inbound / total inbound across all studios (MTD)
- **Deal CVR:** `SUM(IS_CONVERTED) / COUNT(*)` per studio (MTD)

---

### Inbound Engagements

- **Table:** `STG_HUBSPOT_ENGAGEMENTS_BASE e JOIN STG_CONTACTS c ON e.CONTACT_ID = c.PRIMARY_HUBSPOT_ID`
- **Filters:**
  - `ENGAGEMENT_TYPE NOT IN ('NOTE', 'TASK')`
  - `ENGAGEMENT_DIRECTION = 'Incoming'`
  - `c.CUSTOMER_GROUP = 'B2C'`
  - Studio exclusions: `c.STUDIO_NAME NOT IN ('The Inside', 'Burrow', 'General Managers', 'Remote Sales')`
  - Denver timezone on `e.CREATED_AT`
- **Count:** `COUNT(DISTINCT c.PRIMARY_HUBSPOT_ID)` (distinct contacts)
- **YoY:** same day-of-week prior year (yesterday − 364 days)
- **Matches:** Looker dashboard 1156 "Daily Inbound Engagement" tile exactly

---

## Tab 2: Sales Team

### Data sources
| Source | Used for |
|---|---|
| HubSpot CSV export | Revenue (Net Sales) — exact match to dashboard |
| Google Sheet `1lJcsmRhG3ScG8s2ol2jPwUBJ18n20MMn101rXc1ZQp0` tab "For claude_add each month" | Daily retail forecast (studio plan) |
| Google Sheet `1CkbEVt9utgqkO4xbCnxpc1A6tJCTTRaXWo_iQZQiyJw` tab "for claude" | Monthly rep and team goals |
| `PROD.ID_WAREHOUSE.STG_DEAL` | Deal CVR, response time, pacing actuals |
| HubSpot API `/crm/v3/owners` | Rep → studio team mapping |
| HubSpot API (calls + meetings) | Activity counts per rep |
| `#id--retail-closing-notes` Slack channel (ID: C08MYB2S3DH) | Closing notes narrative |

---

### Net Sales (HubSpot)

- **Source:** HubSpot CSV export — `hubspot-crm-exports-all-deals-YYYY-MM-DD.csv`
- **Filter:** `Deal Stage = "Closed Won"` (any of 3 pipelines) AND `Meaningful Contact? = Yes` AND `HubSpot Team` known AND `Close Date` in period
- **Metric:** `Amount` (deal amount field)
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
  - Calls: `POST /crm/v3/objects/calls/search` filtered by owner + MTD close date
  - Meetings: `POST /crm/v3/objects/meetings/search` filtered by owner + MTD close date
- **Team attribution:** HubSpot owners API (`/crm/v3/owners`) — primary studio team from `hs_teams`
- **Displayed as:** total calls per studio and calls-per-rep average
- **Note:** SMS and Chat not yet included (HubSpot sync limitation)

---

### Closing Notes

- **Source:** Slack channel `#id--retail-closing-notes` (channel ID: `C08MYB2S3DH`)
- **Date range:** Yesterday — notes posted between noon and midnight CDT
- **Last Week** — full week recap synthesized from all daily notes
- **Format:** Human-synthesized summary of key themes (traffic, closes, watch items)

---

## Forecast sources summary

| Tab | Forecast source | Column |
|---|---|---|
| Total Business | `FIVETRAN_DB.UPLOADS.ALL_COMPANY_DAILY_FORECAST` | `ID_FORECASTED_ADJUSTED_GROSS_BOOKINGS` |
| Sales Team | Google Sheet (studio retail plan) | Daily $ from "For claude_add each month" tab |

The two sources differ significantly — the Snowflake/Looker forecast is the full company plan (all channels), while the Google Sheet is the retail studio plan calibrated to HubSpot deal revenue.

---

## Known limitations & open items

1. **HubSpot revenue automation:** CSV export must be done manually each morning. The API and Snowflake return ~$65K more than the HubSpot dashboard (internal reporting engine difference unresolved). Blocking full automation.
2. **LY comparison for Sales tab:** Uses Snowflake with MC=Yes filter, which gives different LY totals than the CSV approach (2025 historical export not available).
3. **SMS/Chat activities:** Not included in activity table — not synced to Snowflake, HubSpot API scopes needed.
4. **GitHub Actions cron:** Not yet live — requires `SENDGRID_API_KEY` in GitHub secrets + repo push.
5. **Swatch CVR by window:** Deferred — requires complex cohort SQL to match Looker exactly.
