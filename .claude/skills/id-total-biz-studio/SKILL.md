---
name: id-total-biz-studio
description: Pull Total Business studio performance from Looker with the exact verified filters — MC=Yes, correct studio exclusions, employee exclusion. Use this when someone asks about studio revenue in the context of the Total Business tab (all channels, MC-assisted orders).
---

# Interior Define — Total Business Studio Performance (Looker)

## When to use this skill
Use when someone asks:
- "How are studios performing in total business?"
- "Pull studio breakdown from Looker"
- "What's studio revenue MTD?"
- "Show me the studio performance view"

This skill uses the **Looker `interior_define/orders` explore** — the correct source for the Total Business tab. It shows all-channel studio revenue (not HubSpot-only), so numbers will differ from a STG_DEAL query.

---

## Verified Filters (confirmed against Looker qid=5joOfEerqlwRPE3A7e1CNs)

| Filter | Field | Value |
|---|---|---|
| Date | `orders.order_created_date` | `this month` |
| Employee exclusion | `customers.email` | doesn't contain `@interiordefine.com` |
| Studio exclusion | `hubspot_deals.studio_name` | doesn't contain: `Assisted No Studio, Burrow, The Inside, Automated DE, Santa Monica` + is not null |
| Meaningful Contact | `hubspot_deals.has_meaningful_contact` | `Yes` |

⚠️ `hubspot_deals.has_meaningful_contact = Yes` is required — without it you get all orders, not just studio-assisted revenue.  
⚠️ Use `hubspot_deals.studio_name` — NOT `orders.location`. These give completely different numbers.  
⚠️ `Automated DE` and `Santa Monica` must be excluded — they are not real studio locations.

---

## What You Can Pull with This Skill

### ✅ Revenue, AOV, Deal Count — from the `orders` explore

| Metric | Looker field | Notes |
|---|---|---|
| Discounted revenue | `orders.md_order_revenue` | Post-discount, incl. shipping, excl. tax — this is the correct revenue field |
| # of deals / orders | `orders.order_count` | Count of sales orders |
| AOV | `orders.average_order_value` | True per-order average after discounts, incl. shipping |

All three use the same filters below and can be pulled together in one query.

### ⚠️ MC CVR — requires a separate query from `hubspot_contacts` explore

MC CVR (the rate at which MC=Yes contacts convert to closed orders) is **not available in the `orders` explore**. It lives in the `hubspot_contacts` explore. Use this query:

```
mcp__looker__query
  model: interior_define
  explore: hubspot_contacts
  fields: [hubspot_deals.studio_name, hubspot_deals.deal_conversion_rate]
  filters:
    hubspot_contacts.customer_group: "B2C"
    hubspot_engagements.inbound_engagement: "Yes"
    hubspot_contacts.studio_name: "-Direct Orders,-Remote Sales,-The Inside,-Burrow,-General Managers,-Remote"
    hubspot_deals.has_meaningful_contact: "Yes"
    hubspot_engagements.engagement_created_at_date: "this month"
  sorts: [hubspot_deals.deal_conversion_rate desc]
```

`deal_conversion_rate` = closed won deals / total inbound contacts for that studio.

### ✅ MC Rate (% of closed deals with MC) — Snowflake via Havenly Analytics MCP

This answers "of all closed deals, what fraction had a meaningful contact touch?" It is different from MC CVR above — this is a penetration rate, not a lead-to-close rate.

No pre-built Looker measure exists for this, so run via `mcp__claude_ai_Havenly_Brands_Analytics_MCP__execute_query`:

```sql
SELECT
    STUDIO_NAME,
    COUNT(*)                                                                        AS total_closed_deals,
    SUM(CASE WHEN MEANINGFUL_CONTACT = TRUE THEN 1 ELSE 0 END)                     AS mc_deals,
    ROUND(100.0 * SUM(CASE WHEN MEANINGFUL_CONTACT = TRUE THEN 1 ELSE 0 END)
          / NULLIF(COUNT(*), 0), 1)                                                 AS mc_pct
FROM PROD.ID_WAREHOUSE.STG_DEAL
WHERE IS_CONVERTED = TRUE
  AND CLOSE_DATE >= DATE_TRUNC('month', CONVERT_TIMEZONE('UTC', 'America/Chicago', CURRENT_TIMESTAMP)::DATE)
  AND CLOSE_DATE <  CONVERT_TIMEZONE('UTC', 'America/Chicago', CURRENT_TIMESTAMP)::DATE
  AND STUDIO_NAME NOT IN ('Remote Sales','The Inside','Burrow','General Managers','Remote','Assisted No Studio','Automated DE','Santa Monica')
GROUP BY STUDIO_NAME
ORDER BY mc_pct DESC
```

To break down by rep, add `DEAL_OWNER_EMAIL` to the `SELECT` and `GROUP BY`.

To change the date range, replace the `CLOSE_DATE` filters — e.g. yesterday: `CLOSE_DATE = DATEADD('day', -1, CONVERT_TIMEZONE('UTC', 'America/Chicago', CURRENT_TIMESTAMP)::DATE)`.

---

## Run via Looker MCP

### By Studio (Revenue + AOV + Deal Count)

```
mcp__looker__query
  model: interior_define
  explore: orders
  fields: [hubspot_deals.studio_name, orders.md_order_revenue, orders.order_count, orders.average_order_value]
  filters:
    orders.order_created_date: "this month"
    customers.email: "-%@interiordefine.com%"
    hubspot_deals.studio_name: "-NULL,-Assisted No Studio,-Burrow,-The Inside,-Automated DE,-Santa Monica"
    hubspot_deals.has_meaningful_contact: "Yes"
  sorts: [orders.md_order_revenue desc]
```

### By Individual Rep (Revenue + AOV + Deal Count)

Add `hubspot_deals.deal_owner_email` to the fields list. All filters stay exactly the same — same studio exclusions, same MC=Yes requirement.

```
mcp__looker__query
  model: interior_define
  explore: orders
  fields: [hubspot_deals.studio_name, hubspot_deals.deal_owner_email, orders.md_order_revenue, orders.order_count, orders.average_order_value]
  filters:
    orders.order_created_date: "this month"
    customers.email: "-%@interiordefine.com%"
    hubspot_deals.studio_name: "-NULL,-Assisted No Studio,-Burrow,-The Inside,-Automated DE,-Santa Monica"
    hubspot_deals.has_meaningful_contact: "Yes"
  sorts: [orders.md_order_revenue desc]
```

This returns each rep's revenue, deal count, and AOV within their studio. Use `hubspot_deals.deal_owner_email` — NOT `orders.sales_rep_email` (different source, different numbers).

Or open directly in Looker:
https://havenly.looker.com/explore/interior_define/orders?qid=5joOfEerqlwRPE3A7e1CNs

---

## For Yesterday or a Custom Date Range

Replace `"this month"` with:
- Yesterday: `"yesterday"`
- Last week (Mon–Sun): `"last week"`
- Custom: `"2026-06-01 to 2026-06-14"`

All other filters stay the same.

---

## Source of Truth

Validate results against **Looker dashboard 1156** (`havenly.looker.com/dashboards/1156`) — Studio Performance tile. Numbers should match within ~$2K (live data shifts throughout the day as orders are placed or modified).
