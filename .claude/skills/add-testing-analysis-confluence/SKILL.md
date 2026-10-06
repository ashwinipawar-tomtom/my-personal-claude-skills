# Add Testing Analysis in Confluence

This skill reads all comments on a Jira Epic, generates a short testing analysis note based on severity, and updates the **Comments** column of the matching row in the [ANA Versions Tested](https://tomtom.atlassian.net/wiki/spaces/ANA/pages/1448476996/ANA+Versions+Tested) Confluence page.

## Prerequisites

- Atlassian MCP must be authenticated. If not, ask the user to run `/mcp` and select **"claude.ai Atlassian"**.

## Inputs

Ask the user to provide the following before starting:

| Input | Example | Notes |
|---|---|---|
| `epic_jira_link` | `https://tomtom.atlassian.net/browse/NAV-202400` or `NAV-202400` | The Jira Epic to analyze |

---

## Step 1 — Parse the Epic key

Extract the Jira issue key from the input. Accept both full URLs (`https://tomtom.atlassian.net/browse/NAV-XXXXXX`) and bare keys (`NAV-XXXXXX`).

---

## Step 2 — Fetch the Epic: comments and linked work items

Use `getJiraIssue` with `cloudId: tomtom.atlassian.net`, including fields `summary`, `priority`, `comment`, `issuelinks`, `subtasks`.

### 2a — Collect all ticket references from comments

**Read every comment in full** — do not truncate. If the result is saved to a file, read the entire file.

Extract every Jira ticket key mentioned in any comment (pattern: `[A-Z]+-\d+`, e.g. `NAV-202308`, `GOSDK-205740`). Build a list: **tickets_in_comments**.

Scan all comments for the following signals:

- **Severity / issue counts**: look for keywords like Critical, Blocker, Urgent, Major, Minor — and any counts (e.g. "2 Criticals, 3 Majors")
- **Test status**: Done, In-progress, Blocked, Switched to next RC, No issues reported, Passed, Failed
- **Blockers or escalations**: any mention of blocking issues, customer escalations, or unresolved criticals
- **Scope of testing**: Sanity, Full Regression, Drive Test, APAC, specific use-case testing
- **QA sign-off phrases**: "qa-verified", "no new issues", "confirmed", "cleared"

### 2b — Collect all linked work items

From the `issuelinks` field, extract every linked issue key (both inward and outward links). Also extract any `subtasks` keys. Build a list: **tickets_in_links**.

**Completeness check:** After building the list, count the total number of `issuelinks` entries returned and verify it matches the number of links visible on the Jira issue page. If the response appears truncated (e.g. only 1–2 links returned for an issue known to have more), re-fetch before proceeding. Always include all **"while testing discovered"** links — these are the bugs found during testing and must not be missed.

### 2c — Cross-check and flag discrepancies

Compare **tickets_in_comments** against **tickets_in_links**:

- **Mentioned in comments but NOT in linked items** — these are referenced in QA notes but not formally linked. Flag them as: `⚠ Mentioned in comments only (not linked): NAV-XXXXX`
- **In linked items but NOT mentioned in comments** — these are formally linked but never discussed in QA comments. Flag them as: `ℹ Linked but not mentioned in comments: NAV-XXXXX`
- **In both** — confirmed referenced issues. Use these as the basis for the narrative.

### 2d — Resolve missing severity by fetching tickets directly

For any ticket in **tickets_in_comments** or **tickets_in_links** that has no explicit severity label stated in the comments, fetch that ticket directly using `getJiraIssue` with fields `["summary", "customfield_10140"]` (the **Severity** custom field: Critical (A) / Major (B) / Minor (C) / Safety / Blocks Feature Rollout) and use its value as that ticket's severity.

**Do not use the Jira `priority` field as a fallback** — `priority` (Blocker/Urgent/High/Medium/Low) is a different field from `customfield_10140` (Severity) and must never substitute for it, whether the value appears in a comment or directly on the ticket. Only `customfield_10140` counts as an authoritative severity source.

If `customfield_10140` is also empty/unset on the ticket itself, only then list it under "Also found" with no severity classification.

### 2e — Generate the narrative

Based on the cross-checked data, generate a **short narrative (2–4 sentences)** summarizing:
1. The overall severity level (e.g. "Testing completed with no critical issues" vs "1 Critical blocker found")
2. Specific issue counts by **severity** (Critical / Blocker / Major / Minor), sourced from comments first and `customfield_10140` as fallback per Step 2d — **do not use Jira priority field (High/Medium/Low)**
3. Any open blockers, customer-facing risks, or items requiring follow-up
4. Overall test health verdict (low risk / medium risk / high risk / in-progress)

**Severity source rule:** Use severity labels explicitly stated in QA comments first (e.g. "Major (B)", "Critical", "Minor"). If none is stated, use the ticket's own `customfield_10140` value fetched in Step 2d. If a linked ticket has neither, list it without a severity classification. Never infer severity from the Jira priority field, in comments or on the ticket.

**Style rules:**
- Be factual and concise — draw only from what is in the comments and linked items, do not infer
- If testing is still in progress, say so explicitly
- If no issues were found, say "No issues reported"
- Match the tone and format of existing Comments in the Confluence table (see examples below)

**Examples of good comment style (from the existing table):**
- `1 Critical (crash), 3 Major, 1 Minor`
- `DONE, 1 Critical/Urgent reported for APAC — 4 Major and 2 Minor issues reported`
- `No new issues found`
- `Back-ported fix's use-cases verified, Sanity — 1 issue reported`
- `1 Critical blocker: NAV-XXXXXX still reproducible on this build`

---

## Step 3 — Fetch the Confluence page

Use `getConfluencePage` with:
- `cloudId`: `tomtom.atlassian.net`
- `pageId`: `1448476996`
- `contentFormat`: `html`

Search the page HTML for a table row (`<tr>`) where **either**:
- The **Ticket** column (`<td>`) contains the Epic key (e.g. `NAV-202400`), as a link on older rows or as a Jira issue macro on current rows. For the macro, the key sits only in the `data-parameters` attribute (`macroParams.key.value`), with no link text. Search the cell's raw HTML, not its rendered text. **OR**
- The **Release version** column contains the version string extracted from the Epic summary (e.g. `0.9.0-rc11`)

If **multiple rows** match the same ticket key, use the **last** matching row.

If **no row is found**, report to the user: "No matching row found for {epic_key} in the ANA Versions Tested page."

---

## Step 4 — Output the narrative to the user

**Do NOT call `updateConfluencePage`.** Present the results directly to the user in this format:

```
Epic: {epic_key}
Row matched: {release_version} in the ANA Versions Tested table

--- Cross-check ---
✅ Confirmed (in both comments and linked items): NAV-XXXXX, ...
⚠  Mentioned in comments only (not linked): NAV-XXXXX, ...
ℹ  Linked but not mentioned in comments: NAV-XXXXX, ...

--- Suggested Comments cell content ---
{test status line}
{severity counts — format: N Critical/Blocker: NAV-X, NAV-Y | N Critical/Urgent: NAV-X | N Major: NAV-X | N Minor: NAV-X}
```

**Severity count rules:**
- List each severity group on a line or separated by `|`
- The count number MUST match the number of ticket keys listed — always verify before outputting
- Include ticket keys as markdown hyperlinks next to each count (e.g. `2 Critical/Blocker: [NAV-199938](https://tomtom.atlassian.net/browse/NAV-199938), [NAV-202308](https://tomtom.atlassian.net/browse/NAV-202308)`)
- Omit a severity level entirely if count is zero
- **Use severity labels from QA comments first, falling back to the ticket's own `customfield_10140` (Severity) field per Step 2d** — never use Jira priority (High/Medium/Low) as a substitute for severity, in comments or on the ticket
- If a ticket has no severity label in comments AND no value in `customfield_10140`, list it at the end without any label, e.g. `Also found: NAV-XXXXX, NAV-YYYYY`
- Do NOT add notes, explanations, or recommendations — counts and keys only
- If no issues were found, write: `No issues reported`

If there are no cross-check discrepancies, omit the ⚠ and ℹ lines.

The user will decide whether to apply it.

---

## Constraints

- Read **all** comments in full before generating the analysis — do not truncate
- Always fetch both `comment` and `issuelinks`/`subtasks` fields from the Epic
- Cross-check ticket keys found in comments against formally linked items — flag any that appear in only one source
- Do not call `updateConfluencePage` — output the narrative and cross-check to the user instead
- If the row is not found, report it and stop
- Draw the analysis only from actual comment and linked-item content — do not infer or fabricate issue counts
- Match the concise, factual style of existing Comments in the table
- The Confluence page ID is always `1448476996` — do not ask the user for it
