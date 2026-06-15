# Interior Define Monday Business Review — Exact Data Methodology

**Last validated:** 2026-06-15  
**Source of truth:** This document reflects the EXACT data sources, queries, and filters used in `scripts/run_from_mcp.py` as of the final validated version.  
**Rule:** Do not change any data source without updating this document AND re-validating against Looker dashboard 1156 (Tab 1) or HubSpot dashboard (Tab 2).

---

## Report periods (Monday run)
- **Yesterday** = Sunday (today − 1 day)
- **Last Week** = Monday–Sunday of the prior week (e.g., Jun 8–14 when report runs Jun 16)
- **MTD** = first of current month through Sunday
- **LY Yesterday** = same calendar date one year prior
- **LY Last Week** = same Mon–Sun range one year prior
- **LY MTD** = same calendar range one year prior

---

## Tab 1: Total Business

### Primary validation source
All Tab 1 metrics are validated against **Looker dashboard 1156** (`havenly.looker.com/dashboards/1156`).  
When in doubt, run the Looker query and use that number. Do not substitute raw Snowflake queries without checking against the dashboard.

---

### Yesterday Revenue by Segment

**Source:** Looker `interior_define` model, `orders` explore  
**Query fields:** `customers.customer_group_class`, `orders.md_order_revenue`, `orders.order_count`  
**Filters:**
- `customers.email = "-%@interiordefine.com%"` — excludes staff orders
- `orders.order_created_date = "[YD]"` — yesterday's date, Denver timezone
- **No** order_type or cancellation filter (matches Looker dashboard tile)

**Segment logic:** `CASE WHEN c.CUSTOMER_ID = 20 THEN 'Havenly' ELSE c.CUSTOMER_GROUP_CLASS END`  
**Revenue formula:** `SUM(subtotal - ABS(discount_amount) + shipping_amount)` — post-discount incl. shipping, no tax  
**LY:** Same query with LY date

---

### Yesterday AOV (Blended, B2C, Trade)

**Source:** Looker API — `orders.average_order_value` (true per-order average, NOT total/count)  
**Blended AOV:** Looker "AOV Yesterday" tile using `calendar.compare_to_previous_date_filter = "1 day ago for 1 day"` with calendar pivot  
**B2C / Trade AOV:** Looker `orders` explore with employee filter and `orders.average_order_value` by `customers.customer_group_class`  
**LY AOV:** Same Looker query for LY date — blended from `orders.average_order_value` for that specific day  
⚠️ **Looker's AOV is different from revenue/orders** — always use Looker, never compute manually

---

### Yesterday Assisted %

**Definition:** % of yesterday's revenue (not order count) from orders with Meaningful Contact = Yes  
**Formula:** `MC=Yes revenue ÷ total unfiltered revenue`  
**Source:** Looker `orders` explore, `hubspot_deals.has_meaningful_contact` dimension × `orders.md_order_revenue`  
**Filter:** `orders.order_created_date = "[YD]"`, `orders.order_type = standard`, `orders.cancellation = F`  
⚠️ Revenue-based (not order count) — matches Looker "% Asst Sales Yesterday" tile definition

---

### Yesterday Forecast Comparison

**Actual:** Unfiltered revenue (no order_type/cancellation filter) — matches Looker "v. Yesterday's Forecast" tile  
**Forecast:** `FIVETRAN_DB.UPLOADS.ALL_COMPANY_DAILY_FORECAST.ID_FORECASTED_ADJUSTED_GROSS_BOOKINGS` for [YD]

---

### Yesterday Inbound Engagements

**Source:** Looker `hubspot_contacts` explore, `hubspot_contacts.number_of_contacts`  
**Filters:**
- `hubspot_contacts.studio_name NOT IN ('The Inside','Burrow','General Managers','Remote Sales')`
- `hubspot_engagements.inbound_engagement = Yes`
- `hubspot_contacts.customer_group = B2C`
- `hubspot_engagements.engagement_created_at_date = "[YD]"`

**LY:** Same query for same calendar date LY  
**Count:** Distinct contacts (not raw engagement events)

---

### Last Week Revenue by Segment (Tab 1)

**Source:** Same Looker `orders` explore as Yesterday but date range = Mon–Sun of prior week  
**Filters:** Same employee exclusion, no order_type/cancellation filter  
**Segments:** B2C, Trade, Havenly, B2B — same logic as Yesterday  
**LY:** Same query for same Mon–Sun range one year prior  
**AOV (Blended, B2C, Trade):** Looker `orders.average_order_value` for the same week range — always use Looker, never compute manually  
**Assisted %:** MC=Yes revenue ÷ total revenue for the week  
**Forecast:** `SUM(DAILY_FCST values for Mon–Sun)` — summed from the hardcoded `DAILY_FCST` dict in the script  
**Inbound:** ⚠️ Not available directly from Looker for a prior week window — current value is estimated as `MTD_INBOUND / days_MTD × 7`. Update from Looker dashboard 1156 "Daily Inbound Engagement" filtered to the specific Mon–Sun dates.  
**Swatch orders:** ⚠️ Same limitation — estimated as `SW_MTD_ORD / days_MTD × 7`. Update from Looker `swatch_orders` explore filtered to the same week.  
**Studio breakdown:** `STG_DEAL` — `CLOSE_DATE` CDT in Mon–Sun range, `MEANINGFUL_CONTACT = TRUE`, `IS_CONVERTED = TRUE`, same studio exclusions

---

### MTD Revenue by Segment

**Source:** Same Looker `orders` explore as yesterday but date range = `this month`, `before 0 days ago`  
**Filters:** Employee exclusion only (no order_type/cancellation) — matches Looker MTD tile  
**LY:** Same query for LY month range

---

### MTD AOV (Blended, B2C, Trade)

**Source:** Looker "AOV" tile using `calendar.compare_to_previous_date_filter = "this month"` with `calendar.mtm` pivot  
**Returns:** "This Month" and "This Month Last Year" values  
⚠️ Always use Looker calendar pivot — never compute from revenue/orders

---

### MTD vs Forecast Comparison

**Actual for comparison:** Unfiltered MTD revenue — matches Looker "v. MTD Forecast" tile (no order_type/cancellation filter)  
**Forecast:** `SUM(ID_FORECASTED_ADJUSTED_GROSS_BOOKINGS)` from `FIVETRAN_DB.UPLOADS.ALL_COMPANY_DAILY_FORECAST` for MTD date range

---

### MTD Assisted %

**Definition:** MC=Yes revenue ÷ unfiltered MTD revenue  
**Source:** Looker `orders` explore, `hubspot_deals.has_meaningful_contact` × `orders.md_order_revenue`  
**Filter:** `orders.order_created_month = "this month"`, `orders.order_created_date = "before 0 days ago"`

---

### MTD Repeat Business %

**Source:** Snowflake two-step query:
1. All MTD orders (standard + non-cancelled) with `CUSTOMER_ID`
2. Each customer's `MIN(order_date)` ever
3. Repeat % = orders where first_order_date < month_start / total MTD orders

---

### MTD Inbound Engagements

**Source:** Same Looker `hubspot_contacts` query as yesterday but date range = MTD  
**LY:** Same query for LY MTD date range  
**Looker tile:** Dashboard 1156 "Daily Inbound Engagement" tile definition

---

### Swatch Performance MTD

**Source:** Looker `swatch_orders` explore  
**Fields:** `swatch_orders.count`, `customers.count`  
**Filters:**
- `swatch_orders.swatch_order_created_date = "this month"`
- `swatch_orders.status = "-%merged%,-%ignored%,-%canceled%,-%merge^_pending%"` — active orders only
- `customers.customer_group_class = "B2C,Trade"` — includes both segments (NOT just B2C)

**LY:** Same query for LY month range  
⚠️ Must include Trade — B2C-only gives lower numbers

---

### Merch Contribution MTD

**Source:** Looker `orders` explore  
**Fields:** `products.class`, `order_items.order_item_revenue`, `order_items.quantity`, `order_items.aur`  
**Filters:**
- `orders.order_type = standard`, `orders.cancellation = F`
- `products.item_classification = Merchandise` — critical filter, excludes swatches/accessories
- Date: MTD range

**Revenue:** `SUM(order_items.order_item_revenue)` per class  
**Matches:** Looker `qid=B2YtIQC4p3yQuoUBBFvThb`

---

### Studio Performance MTD

**Source:** Looker `orders` explore, `hubspot_deals.studio_name` dimension (NOT `orders.location`)  
**Filter:** Date = MTD, `hubspot_deals.studio_name != NULL`  
**Matched against:** Looker explore `qid=g8UAPEJnqwtT67Z3PrHejp`  
⚠️ Must use `hubspot_deals.studio_name` — `orders.location` gives completely different numbers  

**% of Deals column:** studio inbound / total inbound from `PROD.ID_WAREHOUSE.STG_DEAL`, `CREATE_DATE` MTD  
**Deal CVR:** `closed_won / total_inbound` from same STG_DEAL MTD query  
**MTD CVR (inbound CVR) and 90D CVR:** Looker `hubspot_contacts` explore, `hubspot_deals.deal_conversion_rate`, excl. Direct Orders  
**% of Baseline column:** MTD CVR ÷ 90D CVR — shows how close each studio is to their normal close rate

---

### Inbound CVR Maturation Chart (monthly cohorts)

**Source:** Snowflake — for each contact's first inbound month, % who placed an order within 14/30/60/90 days  
**Tables:** `STG_HUBSPOT_ENGAGEMENTS_BASE` × `STG_CONTACTS`  
**Filters:** B2C, incoming direction, not NOTE/TASK, studio exclusions  
**Note:** Current month always shows same % for all windows (not yet mature — in progress)

---

## Tab 2: Sales Team

### Primary validation source
All Tab 2 revenue metrics must match the **HubSpot "MTD Sales by Team" dashboard** exactly.  
When in doubt: check HubSpot dashboard first, then update the hardcoded value.

---

### Yesterday Net Sales (TY)

**Source:** `PROD.ID_WAREHOUSE.STG_DEAL`  
**Filter:** `CLOSE_DATE = [YD]` (CDT), `MEANINGFUL_CONTACT = TRUE`, `IS_CONVERTED = TRUE`, studio NOT IN excluded list  
**Revenue field:** `DEAL_AMOUNT` (post-discount, excl. tax/shipping)  
**Total:** Sum of all qualified studio deals for that day

---

### Yesterday Net Sales (LY)

**Source:** `PROD.ID_WAREHOUSE.STG_DEAL` — pre-Aug 2025 methodology  
**WHY different:** HubSpot's `meaningful_contact_` field did not exist before Aug 2025. Using it on 2025 data undercounts by ~40%.  
**Pre-Aug filter (use for any LY date before Aug 1, 2025):**
```sql
(CONNECTED_STAGE_DATE IS NOT NULL AND DATEDIFF(day,CONNECTED_STAGE_DATE,CLOSE_DATE) BETWEEN 0 AND 120)
OR (LOGGED_MEETING_STAGE_DATE IS NOT NULL AND DATEDIFF(day,LOGGED_MEETING_STAGE_DATE,CLOSE_DATE) BETWEEN 0 AND 120)
OR (QUOTE_GENERATED_STAGE_DATE IS NOT NULL AND DATEDIFF(day,QUOTE_GENERATED_STAGE_DATE,CLOSE_DATE) BETWEEN 0 AND 120)
```
**Filter:** `CLOSE_DATE = [LY_YD]`, `IS_CONVERTED = TRUE`, same studio exclusions

---

### MTD Net Sales (TY)

**Source:** HubSpot dashboard value — hardcoded each Monday from the "MTD Sales by Team" dashboard  
**Dashboard URL:** `havenly.looker.com` → HubSpot Sales → MTD Sales by Team  
**Filter:** Closed Won + Meaningful Contact = Yes + team known + close date in MTD  
⚠️ HubSpot API and Snowflake return ~$65K more than the dashboard — always use dashboard value  
⚠️ Do NOT use STG_DEAL totals as MTD_HS_TOTAL — the methodologies diverge

---

### MTD Net Sales (LY)

**Source:** `PROD.ID_WAREHOUSE.STG_DEAL` using pre-Aug stage-date methodology  
**Filter:** `CLOSE_DATE BETWEEN [LY_MO_START] AND [LY_YD]`, pre-Aug engagement filter, same studio exclusions  
**Confirmed total for Jun 1-14, 2025:** $1,468,895.08

---

### MTD by Studio (TY bar chart + All Studios)

**Source:** `PROD.ID_WAREHOUSE.STG_DEAL`  
**Filter:** `CLOSE_DATE` CDT in MTD, `MEANINGFUL_CONTACT = TRUE`, `IS_CONVERTED = TRUE`, studio exclusions  
**Note:** Sum of studios (~$1,812K) may slightly exceed `MTD_HS_TOTAL` ($1,786K) due to HubSpot team filter excluding some deals at the total level

---

### MTD by Studio (LY All Studios bar chart)

**Source:** `PROD.ID_WAREHOUSE.STG_DEAL` — pre-Aug methodology  
**Filter:** Same as LY Net Sales, grouped by `STUDIO_NAME`

---

### Pacing — Team % to Goal

| Column | Source |
|---|---|
| Jun Goal | Google Sheet `1CkbEVt9utgqkO4xbCnxpc1A6tJCTTRaXWo_iQZQiyJw` tab "for claude" |
| Paced | Jun Goal × (MTD retail forecast ÷ full-month retail forecast) |
| MTD Actual | `MTD_BY_STUDIO` (STG_DEAL MC=Yes by studio) |
| % Paced | Actual ÷ Paced |
| Status | Ahead ≥110%, On Track 90-110%, Behind 70-90%, At Risk <70% |

**Pacing %:** `sum(daily retail forecast Jun 1 to yesterday) ÷ full June retail forecast`  
**Retail forecast source:** Google Sheet `1lJcsmRhG3ScG8s2ol2jPwUBJ18n20MMn101rXc1ZQp0` tab "For claude_add each month"  
⚠️ This is the RETAIL/STUDIO plan — different and lower than the Snowflake company forecast on Tab 1

---

### Pacing — Individual % to Goal

Same pacing %, status logic as team table.  
**Actuals:** `MTD_ALL_REPS` dict — HubSpot API (MC=Yes + Closed Won + studio team, incl. inactive owners), keyed by email prefix  
**Goals:** Same Google Sheet, per-rep monthly goals

---

### % Meaningful Contact by Studio

**Source:** `PROD.ID_WAREHOUSE.STG_DEAL`  
**MTD filter:** `CREATE_DATE` CDT in MTD, `DEAL_TYPE != 'Direct Order'`, studio exclusions  
**90D filter:** `CREATE_DATE` CDT in last 90 days  
**MC%:** `SUM(CASE WHEN MEANINGFUL_CONTACT=TRUE THEN 1 ELSE 0 END) / COUNT(*)`  
**MC CVR:** Close rate on MC=Yes deals  
**% of Baseline:** MTD CVR ÷ 90D CVR (how close to normal rate this month)

---

### Inbound CVR by Studio MTD

**Source:** Snowflake `STG_HUBSPOT_ENGAGEMENTS_BASE` × `STG_CONTACTS`  
**Definition:** B2C contacts with first inbound in MTD who placed an order on/after first contact  
**Same filters as Tab 1 inbound** (B2C, studio exclusions, incoming direction, not NOTE/TASK)

---

### Last Week Net Sales (Tab 2)

**Source:** `PROD.ID_WAREHOUSE.STG_DEAL`  
**TY filter:** `CLOSE_DATE` CDT in Mon–Sun prior week, `MEANINGFUL_CONTACT = TRUE`, `IS_CONVERTED = TRUE`, studio exclusions  
**LY filter:** Same Mon–Sun range LY — pre-Aug stage-date methodology (same as LY Yesterday/MTD)  
**Forecast:** `SUM(DAILY_FCST Mon–Sun)` from the hardcoded retail `DAILY_FCST` dict  
**Studio breakdown:** Grouped by `STUDIO_NAME`, top 5 shown as bars

---

### Activities by Studio (Tab 2 — MTD)

**Source:** `PROD.ID_WAREHOUSE.STG_DEAL`  
**Fields used:**
- `CALLS` — all calls logged on a deal (inbound + outbound combined, no directional split available)
- `MEETINGS` — meetings logged on a deal
- `DEAL_INCOMING_EMAILS` — emails sent to the contact from HubSpot
- Deal count = number of deals touched in the period

**Filter:** `CREATE_DATE` CDT in MTD, `STUDIO_NAME` in known studio list, `DEAL_TYPE != 'Direct Order'`  
**Grouped by:** `STUDIO_NAME`  
**Per-rep average:** Studio total ÷ `STUDIO_REP_COUNT[studio]` — headcount from `REP_GOALS` dict, DE/SDE roles only  
**Sorted by:** Total activity volume (calls + meetings + emails) descending  
⚠️ STG_DEAL is deal-level — one row per deal. If a deal has multiple logged calls, the `CALLS` field reflects the count at the deal level. Raw HubSpot activity dashboard may show higher counts for activities not yet linked to a deal.  
⚠️ No inbound vs outbound split on calls — treat as total call volume per studio.

---

### Performance Blurbs (Tab 1 and Tab 2)

Both tabs include a dynamically generated narrative blurb explaining why revenue is missing or achieving plan. No additional data sources — all figures are computed from variables already pulled for the rest of the report.

**Tab 1 — Total Business blurb computes:**
- Revenue vs Snowflake forecast (%) for Yesterday, Last Week, MTD
- Inbound YoY % change
- Swatch orders YoY % change (MTD only)
- Blended AOV YoY % change
- B2C mix shift vs LY
- Assisted % (MC=Yes share of revenue)

**Tab 2 — Sales Team blurb computes:**
- Revenue vs retail plan forecast (%) for Yesterday, Last Week, MTD
- Revenue YoY % change for all three periods
- Studios ahead of paced goal (>105%) and behind (<85%)
- Reps pacing above 110% and below 75% of paced goal
- Average team MC% MTD + lowest studios — flags studios where low MC% may be suppressing conversion

All thresholds are hardcoded in the script and can be adjusted without changing data sources.

---

### Closing Notes

**Source:** Slack channel `#id--retail-closing-notes` (ID: `C08MYB2S3DH`)  
**Bot token:** `SLACK_BOT_TOKEN` — `curl https://slack.com/api/conversations.history?channel=C08MYB2S3DH`  
**Yesterday notes:** Sunday evening posts (5pm-midnight CT)  
**Week notes:** Monday–Saturday of prior week  
**Format:** Claude-synthesized summary of key themes

---

### Google Sheets

| Sheet | File ID | Tab | Used for |
|---|---|---|---|
| Retail forecast | `1lJcsmRhG3ScG8s2ol2jPwUBJ18n20MMn101rXc1ZQp0` | "For claude_add each month" | Daily $ retail plan, pacing % |
| Goals | `1CkbEVt9utgqkO4xbCnxpc1A6tJCTTRaXWo_iQZQiyJw` | "for claude" | Studio + rep monthly goals |

⚠️ **Update these at the start of each new month** — `STUDIO_GOALS`, `REP_GOALS`, and `DAILY_FCST` in the script

---

## Forecast Sources Summary

| Tab | Forecast source | What it is |
|---|---|---|
| Tab 1 Total Business | `FIVETRAN_DB.UPLOADS.ALL_COMPANY_DAILY_FORECAST` | Full company plan (all channels) |
| Tab 2 Sales Team | Google Sheet (retail studio plan) | Studio/HubSpot deal revenue only |

These are completely different — Tab 2 forecast is ~40% of Tab 1.

---

## YoY Hybrid Methodology (Sales Team tab only)

| Period | Source | Filter |
|---|---|---|
| **2026+ (TY)** | HubSpot dashboard / STG_DEAL | `MEANINGFUL_CONTACT = TRUE` |
| **Pre-Aug 2025 (LY)** | STG_DEAL | Stage dates within 0-120 days of close |

**Why hybrid:** HubSpot's `meaningful_contact_` field wasn't used before Aug 2025. Applying it to 2025 data captures only ~50% of actual engaged deals. The stage-date filter approximates what HubSpot tracked pre-Aug.

---

## Automation

| Setting | Value |
|---|---|
| Schedule | Every Monday 8am CT (`0 13 * * 1` UTC = CDT) |
| Routine | `trig_01RswSW7MsvW5ZGDdvKMhqB5` |
| Manage | https://claude.ai/code/routines/trig_01RswSW7MsvW5ZGDdvKMhqB5 |
| GitHub | https://github.com/maryspreck-star/id-daily-business-review |
| Delivery | Slack webhook → havenlyteam.slack.com · Email PDF via SendGrid → `EMAIL_TO` in `.env` |
| Webhook | `https://hooks.slack.com/services/[see routine config]` |
| DST note | Update cron to `0 14 * * 1` in November when CDT→CST |

---

## Known Limitations

1. **HubSpot API stage IDs:** Live HubSpot API calls in the script return $0 due to missing closed-won stage IDs. Pacing table actuals use hardcoded `MTD_BY_STUDIO` (STG_DEAL MC=Yes). Studio bar charts use `MTD_BY_STUDIO`. Net sales total uses hardcoded `MTD_HS_TOTAL` from dashboard.

2. **Google Sheets in automation:** Google Drive MCP doesn't work in headless remote sessions. Pacing goals (`STUDIO_GOALS`, `REP_GOALS`, `DAILY_FCST`) must be updated manually at the start of each month.

3. **MTD_BY_STUDIO vs MTD_HS_TOTAL gap:** The sum of per-studio STG_DEAL MC=Yes (~$1,812K) is slightly higher than the HubSpot dashboard total ($1,786K). The net sales box uses the dashboard total; the studio bars use the STG_DEAL breakdown.

4. **Fabric/collection merch:** Not shown in the current report (only product class). Add if needed.

5. **Rep goals new hire:** When a new rep joins, add them to `REP_GOALS` dict in `run_from_mcp.py` using their email prefix as the key.

6. **Last Week inbound/swatches are estimated:** These values are approximated as `MTD / days_elapsed × 7`. They carry a visible warning note in the report and should be updated from Looker dashboard 1156 each Monday before the report sends.

7. **Activities calls field = inbound + outbound combined:** STG_DEAL does not split call direction. If directional data is needed, it must be pulled from the HubSpot raw activities API directly.

8. **Email delivery requires SENDGRID_API_KEY:** If the key is not set in `.env`, the script skips email silently and logs `[skip] SENDGRID_API_KEY not set`. Slack delivery is not affected.
