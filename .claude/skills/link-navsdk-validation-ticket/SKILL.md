---
name: link-navsdk-validation-ticket
description: Given an ANA RC version (e.g. 0.11.0-rc01), finds its row on the ANA Versions Tested Confluence page, looks up the corresponding NavSDK intake validation ticket on the NavSDK releases overview Confluence page, and links the two Jira issues with a "Contains" issue link. Use when the user wants to map or link the NavSDK validation ticket for a specific ANA version — e.g. "link the NavSDK validation ticket for 0.11.0-rc01".
---

# Link NavSDK Validation Ticket

Given an **ANA RC version**, find its row on the **ANA Versions Tested** Confluence page, read the NavSDK version shown in parentheses next to it, look up the matching NavSDK **intake validation** ticket on the **NavSDK releases overview** Confluence page, and link the two Jira issues with a **Contains** issue link (the ANA ticket *contains* the NavSDK intake ticket).

## Prerequisites

- Atlassian MCP must be authenticated. If not, ask the user to run `/mcp` and select **"claude.ai Atlassian"**.

## Constants

| Value | Data |
|---|---|
| ANA Versions Tested page | `pageId: 1448476996`, `cloudId: tomtom.atlassian.net` |
| NavSDK releases overview page | `pageId: 2120647076`, `cloudId: tomtom.atlassian.net` |
| Link type | `Contains` (Jira issue link type id `10103`) — `outward: contains`, `inward: is part of` |
| Link direction | ANA ticket = **outward** ("contains"); GOSDK intake ticket = **inward** ("is part of") — never reverse it |

## Required Input

| Input | Example | Notes |
|---|---|---|
| `ana_version` | `0.11.0-rc01` | **Required.** The skill only runs when this is provided — do not run it without an explicit ANA version, and do not scan/batch-process the whole page on its own. |

If the user invokes this skill without giving an ANA version, ask for it before doing anything else.

---

## Step 1 — Find the row on the ANA Versions Tested page

Use `getConfluencePage` with `pageId: 1448476996`, `cloudId: tomtom.atlassian.net`, `contentFormat: html`.

Each table row's **Release version** cell has the format:

```html
<p><strong>{ana_version}</strong>({navsdk_version})</p>
```

e.g. `<strong>0.11.0-rc01</strong>(2.6.0-rc01)` → `navsdk_version = 2.6.0-rc01`.

Find the row whose bolded version matches the given `ana_version` exactly (last matching row if duplicates). Read the adjacent **Ticket** cell for the ANA Jira key. It comes in one of two shapes:
- **Older rows:** a plain link, e.g. `<a href="https://tomtom.atlassian.net/browse/NAV-203806">NAV-203806</a>` → `ana_ticket_key = NAV-203806`.
- **Current rows (since 2026-10-06):** a Jira issue macro with no `<a>`, i.e. `<span data-type="inline-extension" data-extension-key="jira" … data-parameters="{…&quot;key&quot;:{&quot;value&quot;:&quot;NAV-209804&quot;}…}">`. HTML-unescape `data-parameters` and read `macroParams.key.value`.

Check for both. Matching only on `href` silently misses every current row.

**If no row matches `ana_version`, or the matching row has no Ticket cell or no `(...)` NavSDK version:** stop and report this to the user.

---

## Step 2 — Duplicate guard

Fetch `ana_ticket_key`'s `issuelinks` via `getJiraIssue` (`fields: ["issuelinks"]`).

Check for an existing `Contains` link (outward name `contains`) pointing at a GOSDK ticket. If found, report it as already linked (with the existing key) and stop — do not proceed to Step 3.

---

## Step 3 — Look up the NavSDK intake ticket

Use `getConfluencePage` with `pageId: 2120647076`, `cloudId: tomtom.atlassian.net`, `contentFormat: html`.

The page has a **"By release line"** section: a series of collapsible `<details>` blocks (one per NavSDK X.Y line, e.g. "2.6.x", "2.5.x", "2.4.x"), each containing a table with columns `NavSDK release | Intake ticket | Drive test ticket | Test type | TT App build | Testing status | Bugs found`.

Find the row whose **NavSDK release** column is a GitHub tag link (`href` ending in `/releases/tag/{navsdk_version}`) matching the target `navsdk_version` exactly.

Read the **Test type** column of that same row (not the "Intake ticket" column). It looks like:

```html
<a href="https://tomtom.atlassian.net/browse/GOSDK-217547">Intake validation (desk)</a> + <a href="https://tomtom.atlassian.net/browse/GOSDK-218120">Drive test</a>
```

Take the Jira key from the link whose text is **"Intake validation (desk)"** specifically — ignore the "Drive test" link (and any other test-type links) in the same cell, even though they appear in the same column separated by `+`.

**Version format quirks to handle:**
- Combined RC entries appear as `X.Y.Z-rcNN/MM` (e.g. `0.74.0-rc06/07`) when two RCs share one testing ticket — match if `navsdk_version` equals either side of the slash.
- If not found under "By release line" (very fresh RC not yet filed into its line), also check the **"Now in work & tested last week"** table at the top of the page, which uses the same "Test type" column format.

**If no match is found anywhere on the page:** report that no intake validation ticket exists yet for that NavSDK version (may not have been cut/detected yet) and stop.

**If no link with text "Intake validation (desk)" is found in the Test type cell** (only a Drive test link, or unrecognized text): report the ambiguity and ask the user which ticket to link.

---

## Step 4 — Confirm before linking

Show the user:

```
{ana_ticket_key} ({ana_version}) — NavSDK {navsdk_version}
  → will link as "contains" → {gosdk_key}
```

Ask: **"Create this link?"** Wait for explicit confirmation before Step 5. Do not link anything without this confirmation — it's a visible, shared-state change on both tickets.

---

## Step 5 — Create the link

**Confirmed by direct test (2026-07-15):** the `createIssueLink` tool's `outwardIssue`/`inwardIssue` parameters are inverted relative to their names. Calling it with `outwardIssue: {ana_ticket_key}, inwardIssue: {gosdk_key}` produces a link where, on re-fetch, `{ana_ticket_key}` shows up under `"inwardIssue"` (i.e. it ends up on the "is part of" side — backwards). The correct call to make the ANA ticket hold the "contains" role is with the parameters **swapped**:

```json
{
  "outwardIssue": "{gosdk_key}",
  "inwardIssue": "{ana_ticket_key}",
  "type": "Contains"
}
```

Use `cloudId: tomtom.atlassian.net`.

**Always verify after creating** — re-fetch `{ana_ticket_key}`'s `issuelinks` and confirm the new Contains entry shows `"outwardIssue": {gosdk_key}` (meaning, per standard GET semantics where the field name reflects the role of the *currently-fetched* issue, the ANA ticket implicitly holds the "contains"/outward role). If it instead shows `"inwardIssue": {gosdk_key}`, the link was created backwards — there is no delete-link tool available in this toolset, so stop and ask the user to remove the wrong link manually via the Jira UI before retrying.

---

## Step 6 — Output

```
✅ {ana_ticket_key} → contains → {gosdk_key} (NavSDK {navsdk_version})
```

---

## Constraints

- Never run this skill without an explicit `ana_version` input — always ask for it first if missing. There is no batch/scan-all mode.
- Always source `navsdk_version` from the parenthetical in the ANA Versions Tested page's Release version column for the matching `ana_version` row — never guess it from the ANA version number or parse it from the Jira epic description.
- Always source the GOSDK ticket key from the NavSDK releases overview page's "Test type" column (the "Intake validation (desk)" link) for the matching NavSDK release — never fuzzy-match on Jira summary text.
- Always check for an existing `Contains` link before creating a new one (Step 2) to avoid duplicates.
- Wait for explicit user confirmation (Step 4) before calling `createIssueLink`.
- The link direction is fixed: ANA ticket = outward ("contains"), GOSDK ticket = inward ("is part of"). Never reverse it.
- The NavSDK releases overview page is auto-refreshed from Jira and should not be edited — only read from it.
