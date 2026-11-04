# Skill: update-alpha-beta-confluence

Read the Alpha and Beta Slack notification channels, build a feature list, and update the ANA Alpha/Beta features Confluence page.

## Trigger

User says something like:
- `/update-alpha-beta-confluence`
- "update the alpha beta confluence page"
- "refresh the alpha/beta features page"

---

## Constants

| Value | Data |
|---|---|
| Alpha Slack channel ID | `C0B23EZU2UX` (#navapp-in-alpha-notification) |
| Beta Slack channel ID | `C0ARMMY406T` (#navapp-in-beta-notification) |
| Confluence page ID | `2100726927` |
| Confluence cloud ID | `tomtom.atlassian.net` |
| Test Debt page ID | `1435599648` |

---

## Step 1 — Read the current Confluence page

Use `getConfluencePage` with `pageId: 2100726927`, `cloudId: tomtom.atlassian.net`, `contentFormat: html`.

For each existing row in the table, extract:
- **ticket_key**: the NAV key from the Feature column
- **product**: current value of the Product cell (may be blank)
- **in_alpha**: current value of the In Alpha cell (may be blank)
- **in_beta**: current value of the In Beta cell (may be blank)
- **all other cell values**: APAC, ROW, Test case, Comments, Status — preserve exactly as-is

Build three sets:
- **existing_tickets**: all ticket keys currently on the page
- **alpha_only_tickets**: ticket keys where In Alpha has a date but In Beta is blank
- **no_product_tickets**: ticket keys whose Product cell is blank

---

## Step 2 — Read both Slack channels

Use `slack_read_channel` for both channel IDs with `limit: 50` and `response_format: concise`.

Read both channels in parallel.

Collect only messages where the transition type is **"New Feature"** — skip messages that say "transitioned an Epic", "transitioned a Task", or any non-feature type.

For each qualifying message, extract:
- **ticket_key**: e.g. `NAV-197912`
- **alpha_date**: date of transition if from the Alpha channel (format: `DD MMM`, e.g. `26 Jun`)
- **beta_date**: date of transition if from the Beta channel (format: `DD MMM`, e.g. `26 Jun`)

If the same ticket appears in both channels, merge into one row with both dates filled.

Now sort the work into three buckets (A and B from Slack, C from the page itself):

**Bucket A — Truly new tickets**: ticket_key is NOT in existing_tickets at all. These become new rows.

**Bucket B — Beta upgrades**: ticket_key IS in alpha_only_tickets AND the Slack Beta channel has a beta_date for it. These rows already exist on the page but need their In Beta cell filled in.

**Bucket C — Product backfill**: every ticket in no_product_tickets (Step 1). These rows get only their Product cell filled.

If all three buckets are empty, tell the user "No new features or updates since last update" and stop.

---

## Step 3 — Fetch ticket summaries and products from Jira

For every ticket in Buckets A, B and C, fetch `summary` and `customfield_10309` (**Products**). Use one `searchJiraIssuesUsingJql` call with `key in (...)` (batches of up to 50) rather than one `getJiraIssue` per ticket.

**Product:** join the `value` of every entry in `customfield_10309`, in the order Jira returns them, with `, ` — e.g. `ANA`, `UX Library`, `Automotive UI on NavSDK`, `ANA, Automotive UI on NavSDK`. If the field is empty, leave the cell blank. Never guess the product from the summary (e.g. `[appUxLib]`). The user asked for this column on 2026-11-04.

From the summary, determine:

- **APAC**: set to `Yes` if the summary contains `[JP]`, `[KR]`, `JP`, or `KR` (case-sensitive, as these always appear as region tags in square brackets or standalone uppercase)
- **ROW**: set to `Yes` if the summary contains `[RoW]`, `[ROW]`, or `RoW` (case-insensitive match on "row")

Leave the cell blank if neither tag is present.

---

## Step 4 — Fetch the Test Debt page and filter

Use `getConfluencePage` with `pageId: 1435599648`, `cloudId: tomtom.atlassian.net`, `contentFormat: html`.

Extract all NAV ticket keys from the page HTML using pattern `NAV-\d+`.

Remove any ticket from your feature list that appears in the Test Debt page. These are already tracked there.

---

## Step 5 — Build and publish the updated page

Reconstruct the full table as follows:

1. **New rows** (Bucket A): build fresh rows for each new ticket, with the Product from Step 3. Sort newest first. Insert at the **top** of the table body.
2. **Existing rows**: copy them from the current page HTML exactly, with two exceptions:
   - **Bucket B:** fill in the In Beta cell with the beta_date from Slack.
   - **Bucket C:** fill in the blank Product cell with the Product from Step 3.

   All other cells (APAC, ROW, Test case, Comments, Status) stay untouched. **Never overwrite a Product cell that already has a value**, even if Jira now says something else: someone may have set it by hand.

The result is the complete table: new rows on top, existing rows below with any beta upgrades applied.

Use `updateConfluencePage` with:
- `cloudId`: `tomtom.atlassian.net`
- `pageId`: `2100726927`
- `status`: `current` (always publish, not draft)
- `contentFormat`: `html`
- `title`: `ANA Alpha/Beta features`, always exactly this. Never add a date or `WIP`. The user asked for this on 2026-11-04: the title is part of the page URL, so a dated title changed the link on every update and broke links people had shared.
- `body`: full HTML table with all rows

### Table column structure (preserve existing widths)

| Column | Notes |
|---|---|
| Feature | Ticket URL as inline smart link (`data-card-appearance="inline"`) |
| Product | Products (`customfield_10309`) values from the ticket, joined with `, `; blank if unset. Fill only when blank |
| In Alpha | Date e.g. `15 Jun` — blank if not in Alpha channel |
| In Beta | Date e.g. `26 Jun` — blank if not in Beta channel |
| APAC | `Yes` if JP or KR in summary, else blank |
| ROW | `Yes` if RoW/ROW in summary, else blank |
| Test case | Preserve existing value, leave blank if new |
| Comments | Preserve existing value, leave blank if new |
| Status | Preserve existing value, leave blank if new |

### HTML row template

```html
<tr>
  <td data-colwidth="{w}"><p><a href="https://tomtom.atlassian.net/browse/{KEY}" data-card-appearance="inline">https://tomtom.atlassian.net/browse/{KEY}</a></p></td>
  <td data-colwidth="{w}"><p>{product or empty}</p></td>
  <td data-colwidth="{w}"><p>{alpha_date or empty}</p></td>
  <td data-colwidth="{w}"><p>{beta_date or empty}</p></td>
  <td data-colwidth="{w}"><p>{APAC: Yes or empty}</p></td>
  <td data-colwidth="{w}"><p>{ROW: Yes or empty}</p></td>
  <td data-colwidth="{w}"><p>{test_case or empty}</p></td>
  <td data-colwidth="{w}"><p>{comments or empty}</p></td>
  <td data-colwidth="{w}"><p>{status or empty}</p></td>
</tr>
```

Use the colwidths from the live page structure (Step 4), not hardcoded values.

---

## Step 6 — Confirm

Tell the user:
- How many new features were added (Bucket A)
- How many existing rows were updated with a Beta date (Bucket B)
- How many existing rows got their Product filled in (Bucket C), and which tickets have no Products value in Jira
- How many were skipped (already fully up to date or in Test Debt)
- Which tickets had APAC or ROW set to Yes
