---
name: id-hubspot-sales
description: Pull Interior Define Sales Team data from HubSpot — net sales, AOV, deal count by studio or rep matching the HubSpot dashboard exactly. Also covers YoY comparison and activities. Use when someone asks about sales team performance, HubSpot revenue, rep results, or activity metrics.
---

# Interior Define — HubSpot Sales Team Data

## When to use this skill
Use when someone asks:
- "What's [studio/rep] MTD net sales?"
- "Pull HubSpot revenue by studio"
- "How many deals did [rep] close this week?"
- "What's the AOV by studio?"
- "How are we pacing vs last year?"
- "Show me activity metrics — calls, meetings, emails"

**Revenue, deal count, and AOV** → HubSpot MCP (`mcp__claude_ai_HubSpot__query_crm_data`) — matches HubSpot dashboard exactly.  
**YoY LY comparison (pre-Aug 2025)** → Snowflake STG_DEAL with stage-date logic — MC wasn't tracked in HubSpot before Aug 2025.  
**Activities** → Snowflake STG_DEAL — not available via HubSpot MCP query.

---

## The Correct Filters (verified against HubSpot dashboard)

| Filter | HubSpot field | Value |
|---|---|---|
| Deal owner | `hubspot_owner_id` | IS NOT NULL |
| HubSpot team | `hubspot_team_id` | IS NOT NULL |
| Meaningful Contact | `meaningful_contact_` | `= 'true'` |
| Closed Won stage | `dealstage` | IN closed won values (see query) |
| Date | `closedate` | BETWEEN month start AND today |

⚠️ `meaningful_contact_` value is `'true'` (string) — NOT `True`, `'Yes'`, or `1`.  
⚠️ Group by `hubspot_team_id`, not studio name — HubSpot uses team IDs internally.  
⚠️ Revenue field is `amount` — this is HubSpot's native Amount field.  
⚠️ Must include all four Closed Won `dealstage` values — they exist across different pipelines.

---

## Queries — Run via HubSpot MCP (`mcp__claude_ai_HubSpot__query_crm_data`)

### Net Sales + Deal Count + AOV by Studio (MTD)

HubSpot MCP does not support division in SELECT, so pull net_sales and deals, then compute AOV = net_sales ÷ deals after the query returns.

```sql
SELECT hubspot_team_id, SUM(amount) AS net_sales, COUNT(*) AS deals
FROM DEAL
WHERE hubspot_owner_id IS NOT NULL
  AND hubspot_team_id IS NOT NULL
  AND meaningful_contact_ = 'true'
  AND dealstage IN ('264c3b2f-856c-4973-b659-95b5f775dc8b', 'closedwon', '221181253', '957899065')
  AND closedate BETWEEN '2026-06-01' AND '2026-06-15'
GROUP BY hubspot_team_id
ORDER BY SUM(amount) DESC
```

Replace the `closedate` range with the current month start and today's date. After results return, present as: studio name | net sales | deals | AOV (net_sales ÷ deals).

### Net Sales + Deal Count + AOV by Rep (MTD)

Step 1 — run via `mcp__claude_ai_HubSpot__query_crm_data`:
```sql
SELECT hubspot_team_id, hubspot_owner_id, SUM(amount) AS net_sales, COUNT(*) AS deals
FROM DEAL
WHERE hubspot_owner_id IS NOT NULL
  AND hubspot_team_id IS NOT NULL
  AND meaningful_contact_ = 'true'
  AND dealstage IN ('264c3b2f-856c-4973-b659-95b5f775dc8b', 'closedwon', '221181253', '957899065')
  AND closedate BETWEEN '2026-06-01' AND '2026-06-15'
GROUP BY hubspot_team_id, hubspot_owner_id
ORDER BY SUM(amount) DESC
```

Step 2 — owner IDs come back as numbers. Look up names via `mcp__claude_ai_HubSpot__search_owners` with the full list of IDs returned:
```
{ ownerIds: [id1, id2, id3, ...] }
```

Step 3 — join names to results and compute AOV (net_sales ÷ deals) per rep. Present grouped by studio.

---

## HubSpot Team ID → Studio Name Mapping

Results return team IDs, not names. Map them as follows:

| Team ID | Studio |
|---|---|
| 14075804 | New York |
| 14075778 | Dallas |
| 14075800 | Minneapolis |
| 14118313 | Washington DC |
| 14072464 | Chicago |
| 14072444 | Denver |
| 14075806 | Seattle |
| 14075777 | Charlotte |
| 14075744 | Boston |
| 14075781 | Los Angeles |
| 14075805 | San Francisco |
| 55992894 | Baltimore |
| 14118420 | Philadelphia |

---

## Date Ranges

Replace the `closedate BETWEEN` clause — all other filters stay the same.

| Period | closedate filter |
|---|---|
| MTD | `BETWEEN 'YYYY-MM-01' AND 'YYYY-MM-DD'` (first of current month → today) |
| Yesterday | `BETWEEN 'YYYY-MM-DD' AND 'YYYY-MM-DD'` (same date both sides) |
| Last week (Mon–Sun) | `BETWEEN 'YYYY-MM-DD' AND 'YYYY-MM-DD'` (prior Monday → prior Sunday) |
| Custom | `BETWEEN 'YYYY-MM-DD' AND 'YYYY-MM-DD'` |

Always use today's actual date — HubSpot MCP does not support dynamic date functions like `CURRENT_DATE`.

---

## Activities — Run via HubSpot MCP (`mcp__claude_ai_HubSpot__query_crm_data`)

All activity queries use `hs_timestamp BETWEEN 'YYYY-MM-DD' AND 'YYYY-MM-DD'` for the date range. Replace with current month start and today's date for MTD.

### Calls by Studio (Inbound vs Outbound)

```sql
SELECT hubspot_team_id, hs_call_direction, COUNT(*) AS calls
FROM CALL
WHERE hs_timestamp BETWEEN '2026-06-01' AND '2026-06-15'
  AND hubspot_owner_id IS NOT NULL
  AND hubspot_team_id IS NOT NULL
GROUP BY hubspot_team_id, hs_call_direction
ORDER BY hubspot_team_id, hs_call_direction
```

Map `hubspot_team_id` to studio name using the table above. `hs_call_direction` returns `INBOUND` or `OUTBOUND`.

### Calls by Rep (Inbound vs Outbound)

```sql
SELECT hubspot_owner_id, hs_call_direction, COUNT(*) AS calls
FROM CALL
WHERE hs_timestamp BETWEEN '2026-06-01' AND '2026-06-15'
  AND hubspot_owner_id IS NOT NULL
GROUP BY hubspot_owner_id, hs_call_direction
ORDER BY hubspot_owner_id, hs_call_direction
```

After results return, look up rep names via `mcp__claude_ai_HubSpot__search_owners` with the full list of owner IDs.

### Meetings by Studio (Scheduled vs Completed)

```sql
SELECT hubspot_team_id, hs_meeting_outcome, COUNT(*) AS meetings
FROM MEETING
WHERE hs_timestamp BETWEEN '2026-06-01' AND '2026-06-15'
  AND hubspot_owner_id IS NOT NULL
  AND hubspot_team_id IS NOT NULL
GROUP BY hubspot_team_id, hs_meeting_outcome
ORDER BY hubspot_team_id, hs_meeting_outcome
```

`hs_meeting_outcome` values: `COMPLETED`, `SCHEDULED`, `RESCHEDULED`, `CANCELED`, `NO_SHOW`. Present only Completed and Scheduled broken out — the total across all outcomes matches HubSpot's "MTD Activity by Team" dashboard total.

### Meetings by Rep (Scheduled vs Completed)

```sql
SELECT hubspot_owner_id, hs_meeting_outcome, COUNT(*) AS meetings
FROM MEETING
WHERE hs_timestamp BETWEEN '2026-06-01' AND '2026-06-15'
  AND hubspot_owner_id IS NOT NULL
GROUP BY hubspot_owner_id, hs_meeting_outcome
ORDER BY hubspot_owner_id, hs_meeting_outcome
```

After results return, look up rep names via `mcp__claude_ai_HubSpot__search_owners`.

### Emails by Studio (Inbound vs Outbound)

```sql
SELECT hubspot_team_id, hs_email_direction, COUNT(*) AS emails
FROM EMAIL
WHERE hs_timestamp BETWEEN '2026-06-01' AND '2026-06-15'
  AND hubspot_owner_id IS NOT NULL
  AND hubspot_team_id IS NOT NULL
  AND hs_email_direction IN ('INCOMING_EMAIL', 'EMAIL')
GROUP BY hubspot_team_id, hs_email_direction
ORDER BY hubspot_team_id, hs_email_direction
```

`hs_email_direction` values: `EMAIL` = Outgoing, `INCOMING_EMAIL` = Incoming. (Exclude `FORWARDED_EMAIL` and `DRAFT_EMAIL` — not relevant for activity tracking.)

### Emails by Rep (Inbound vs Outbound)

```sql
SELECT hubspot_owner_id, hs_email_direction, COUNT(*) AS emails
FROM EMAIL
WHERE hs_timestamp BETWEEN '2026-06-01' AND '2026-06-15'
  AND hubspot_owner_id IS NOT NULL
  AND hs_email_direction IN ('INCOMING_EMAIL', 'EMAIL')
GROUP BY hubspot_owner_id, hs_email_direction
ORDER BY hubspot_owner_id, hs_email_direction
```

After results return, look up rep names via `mcp__claude_ai_HubSpot__search_owners`.

⚠️ HubSpot MCP supports max 2 GROUP BY dimensions — you cannot group by studio + rep + direction in a single query. Run studio-level and rep-level as separate queries.

---

## Meaningful Contact Rate (MC%) — HubSpot MCP

MC% = what share of all closed won deals had meaningful contact. Query returns Yes/No/Unassigned buckets — compute MC% = Yes ÷ (Yes + No + Unassigned) × 100 after results return.

### MC% by Studio

```sql
SELECT hubspot_team_id, meaningful_contact_, COUNT(*) AS deals
FROM DEAL
WHERE hubspot_owner_id IS NOT NULL
  AND hubspot_team_id IS NOT NULL
  AND dealstage IN ('264c3b2f-856c-4973-b659-95b5f775dc8b', 'closedwon', '221181253', '957899065')
  AND closedate BETWEEN '2026-06-01' AND '2026-06-15'
GROUP BY hubspot_team_id, meaningful_contact_
ORDER BY hubspot_team_id, meaningful_contact_
```

Results return three rows per studio (`Yes (true)`, `No (false)`, `Unassigned`). Present as:

| Studio | MC Deals | Total Deals | MC% |
|---|---|---|---|
| Studio name | yes count | yes + no + unassigned | yes ÷ total × 100 |

### MC% by Rep

Step 1 — run via `mcp__claude_ai_HubSpot__query_crm_data`:
```sql
SELECT hubspot_owner_id, meaningful_contact_, COUNT(*) AS deals
FROM DEAL
WHERE hubspot_owner_id IS NOT NULL
  AND dealstage IN ('264c3b2f-856c-4973-b659-95b5f775dc8b', 'closedwon', '221181253', '957899065')
  AND closedate BETWEEN '2026-06-01' AND '2026-06-15'
GROUP BY hubspot_owner_id, meaningful_contact_
ORDER BY hubspot_owner_id, meaningful_contact_
```

Step 2 — look up rep names via `mcp__claude_ai_HubSpot__search_owners` with all returned owner IDs.

Step 3 — compute MC% per rep (Yes ÷ total) and present grouped by studio.

### MC% CVR (Conversion Rate of MC Deals)

CVR = of all MC=true deals **created** this month, what % are **currently** in closed won stage. Both queries use `createdate` — NOT `closedate`.

⚠️ Do NOT use `closedate` for CVR. Using closedate captures deals created in prior months that closed this month, which inflates the numerator and doesn't match how HubSpot calculates it.  
⚠️ Do NOT filter by `hubspot_owner_id` or `hubspot_team_id` — unassigned deals must be included in both queries.

**Query A — Total MC deals created MTD (denominator):**
```sql
SELECT COUNT(*) AS mc_pipeline_deals
FROM DEAL
WHERE meaningful_contact_ = 'true'
  AND createdate BETWEEN '2026-06-01' AND '2026-06-16'
```

**Query B — MC deals created MTD that are currently Closed Won (numerator):**
```sql
SELECT COUNT(*) AS mc_closed_won
FROM DEAL
WHERE meaningful_contact_ = 'true'
  AND dealstage IN ('264c3b2f-856c-4973-b659-95b5f775dc8b', 'closedwon', '221181253', '957899065')
  AND createdate BETWEEN '2026-06-01' AND '2026-06-16'
```

CVR = Query B ÷ Query A. Example verified June 1–16: 299 ÷ 3,369 = **8.9%**.

For studio-level CVR, add `GROUP BY hubspot_team_id` to both queries, then divide per studio. For rep-level CVR, use `GROUP BY hubspot_owner_id` and look up names via `mcp__claude_ai_HubSpot__search_owners`.

---

## YoY Comparison

TY and LY use **different tools and filters** because Meaningful Contact wasn't tracked in HubSpot before August 2025.

### TY (2026) — HubSpot MCP
Use the standard query above with the current year date range. Example for June 2026 MTD:
```sql
SELECT hubspot_team_id, SUM(amount) AS net_sales, COUNT(*) AS deals
FROM DEAL
WHERE hubspot_owner_id IS NOT NULL
  AND hubspot_team_id IS NOT NULL
  AND meaningful_contact_ = 'true'
  AND dealstage IN ('264c3b2f-856c-4973-b659-95b5f775dc8b', 'closedwon', '221181253', '957899065')
  AND closedate BETWEEN '2026-06-01' AND '2026-06-15'
GROUP BY hubspot_team_id
ORDER BY SUM(amount) DESC
```

### LY (2025, pre-Aug) — Snowflake STG_DEAL with stage-date logic

MC wasn't tracked in HubSpot before August 2025, so LY uses Snowflake with a stage-date proxy filter. Run via `mcp__claude_ai_Havenly_Brands_Analytics_MCP__execute_query`:

```sql
SELECT
    STUDIO_NAME,
    SUM(DEAL_AMOUNT)  AS net_sales,
    COUNT(*)          AS deals
FROM PROD.ID_WAREHOUSE.STG_DEAL
WHERE IS_CONVERTED = TRUE
  AND CLOSE_DATE BETWEEN '2025-06-01' AND '2025-06-14'
  AND STUDIO_NAME NOT IN ('Remote Sales','The Inside','Burrow','General Managers','Remote')
  AND (
      (CONNECTED_STAGE_DATE IS NOT NULL AND DATEDIFF('day', CONNECTED_STAGE_DATE, CLOSE_DATE) BETWEEN 0 AND 120)
      OR (LOGGED_MEETING_STAGE_DATE IS NOT NULL AND DATEDIFF('day', LOGGED_MEETING_STAGE_DATE, CLOSE_DATE) BETWEEN 0 AND 120)
      OR (QUOTE_GENERATED_STAGE_DATE IS NOT NULL AND DATEDIFF('day', QUOTE_GENERATED_STAGE_DATE, CLOSE_DATE) BETWEEN 0 AND 120)
  )
GROUP BY STUDIO_NAME
ORDER BY net_sales DESC
```

Shift the date range back exactly one year from the TY period. Keep the same elapsed days — e.g. if TY is June 1–15, LY is June 1–14 (one fewer day if LY had fewer elapsed days).

⚠️ LY results group by `STUDIO_NAME` (text), TY results group by `hubspot_team_id` (number) — use the team ID mapping table to align them side by side.

---

## Rep Goals — What to Know Before Building a Pacing Table

Rep goals are **not stored in HubSpot** — they are set by GMs and tracked separately. When building a rep-level pacing or goal-tracking table:

1. **Always verify goals with the user** before populating — do not pull from a stale artifact or prior session snapshot.
2. **Not all reps have assigned goals.** GMs in particular may have no individual revenue goal.
3. **Exclude no-goal reps from pacing tables** — if a rep has no goal, omit their row entirely (their revenue still rolls into the studio total).

### Known reps without goals (as of June 2026)

| Rep | Owner ID | Studio | Note |
|---|---|---|---|
| Bran Randol | 85929996 | San Francisco | GM — no June goal assigned (user-confirmed 2026-06-29) |

> When you encounter other reps with suspiciously low goals (e.g. $13K for a full-time DE) or clearly new/part-time staff, confirm with the user before including them in a pacing table.

---

## Common Mistakes

| ❌ Wrong | ✅ Right | Why |
|---|---|---|
| `meaningful_contact_ = 'Yes'` | `meaningful_contact_ = 'true'` | Enum value is 'true', not 'Yes' |
| Snowflake STG_DEAL for revenue | HubSpot MCP for revenue | Only HubSpot MCP matches dashboard exactly |
| Missing dealstage filter | Include all 4 Closed Won values | Multiple pipelines have their own Closed Won stage ID |
| Group by studio name | Group by `hubspot_team_id` | HubSpot uses team IDs — map with table above |
| Include GMs in rep pacing tables | Confirm goal exists first | GMs may have no individual goal assigned |

---

## Source of Truth

Results match the **HubSpot MTD Sales by Team dashboard** exactly when using the query above. Verify by comparing totals row-by-row.
