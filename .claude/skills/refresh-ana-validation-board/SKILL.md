# refresh-ana-validation-board

Regenerate the [ANA Release Validation Board](https://tomtom.atlassian.net/wiki/spaces/ANA/pages/2561638669/ANA+Release+Validation+Board+Overview+and+Current+Issues) (page `2561638669`) from Jira and Confluence.

The board is the ANA counterpart of the [NavSDK Release Validation Board](https://tomtom.atlassian.net/wiki/spaces/GOSDK/pages/2120647076/NavSDK+Release+Validation+Board+Overview+and+Current+Issues). It shows, per ANA RC: the NavSDK version, the three testing streams with their tickets and statuses, and the bugs found.

**This skill owns the page.** It rewrites the whole body every run, so nothing on it should be edited by hand.

## Prerequisites

- Atlassian MCP authenticated. If not, ask the user to run `/mcp` and select **"claude.ai Atlassian"**.
- Slack MCP authenticated (for build times). If not, ask the user to run `/mcp` and select **"claude.ai Slack"**.

## Inputs

| Input | Default | Notes |
|---|---|---|
| `lines` | `0.10,0.11,0.12,0.13` | Release lines to include, newest first in the output. |

---

## Step 1 — Fetch the validation Epics

`searchJiraIssuesUsingJql`, `cloudId: tomtom.atlassian.net`:

```
project = NAV AND issuetype = Epic AND parent = NAV-202198
AND (summary ~ "0.10" OR summary ~ "0.11" OR summary ~ "0.12" OR summary ~ "0.13")
ORDER BY summary ASC
```

Fields `["summary", "status"]`, `view: full`, `maxResults: 60`.

**Discard non-ANA matches.** The `~` operator is fuzzy and returns unrelated Epics (e.g. `[Foxtron] 0.5 RC sanity testing - 0.5.13`). Keep only summaries matching `ANA (RC )?{version} validation`.

Parse the version out of each summary. Some Epics cover **two RCs** (`ANA RC 0.11.0-rc08/09 validation`, `ANA RC 0.10.0-rc11/12 validation`) — keep the combined label and render one row.

---

## Step 2 — Fetch all children in one query

```
project = NAV AND parent in ({all Epic keys from Step 1}) ORDER BY parent ASC, created ASC
```

Fields `["summary", "status", "issuetype", "parent", "assignee"]`, `view: full`, `maxResults: 100`.

This response is large and will likely be saved to a file. **Parse it as JSON with a script** — do not read it as text.

### 2a — Classify each child into a stream

| Stream | Match on summary |
|---|---|
| **APAC** | starts with `[APAC]`, or contains `APAC` |
| **Drive test** | contains `drive test` (case-insensitive) |
| **Sanity (desk)** | everything else — `Sanity Testing for …`, `Sanity Tests for …`, or a named area test (`Route planning`, `Map Experience`, `DX UI`, `Search`, `E2E`) |

Check **APAC before Drive test before Sanity** — `[APAC] ANA RC … validation` must not fall through to Sanity.

Where an Epic has **several area tests** instead of one sanity ticket (the rc01 Epics do), render `DONE — N area tests (names)` rather than listing every key.

Render each cell as `{STATUS} {key as link}`, status uppercased (`DONE`, `IN PROGRESS`, `OPEN`, `BLOCKED`). Use `—` when a stream has no ticket.

A drive test shared across RCs (e.g. `ANA 0.12.0-rc04/05 Drive test`) appears on both rows; on the earlier one render `combined with {other rc} {key}`.

---

## Step 3 — Bug counts and NavSDK versions from ANA Versions Tested

`getConfluenceContent` with `content_id: 1448476996`, `content_format: markdown`, `detail: full`.

Large — parse the saved file as JSON and take `data.body.value`.

Locate each line's section (bold paragraphs, inconsistent spacing: `**0.10 Releases : **`, `**0.12 Releases :**`). Match tolerantly: collapse whitespace, strip the trailing colon. A section runs to the next bold-paragraph heading or `**Mainline Validation**`.

For each 8-column row in those sections:

- **Release version cell** → the ANA version, and the NavSDK version in parentheses (`0.11.0-rc16 (2.6.2)Build : 6:05 PM` → version `0.11.0-rc16`, NavSDK `2.6.2`)
- **Comments cell (column 8)** → the bug record

Escaped pipes (`\|`) inside a cell are separators *in the text*, not column boundaries — substitute a placeholder before splitting on `|`, then restore.

### 3a — Bug rendering

Reproduce the round's own counts and keys, grouped by severity, in the order Critical → Major → Minor. Keep any trailing qualifier the round recorded (`Already reported, observed on this build`, `Switched to rc14`, `Skipped`, `No new issues`).

**Use the counts as the round stated them**, even where they disagree with the number of keys listed (0.11.0-rc01 says "4 Critical" against 6 keys, one struck through; 0.11.0-rc02 says "1 Major" against 2). The page is the authoritative per-round record — do not silently recount.

Pre-existing issues re-observed on a build go on their own line, not into the new-issue counts.

---

## Step 4 — Build times from Slack

Only needed for the pulse table. For each release in the pulse, find its `*ANA release {version} success*` notification.

Use `slack_search_public` rather than paging channel history:

- `keywords`: `["\"ANA release\"", "success"]`
- `filters`: `in:<#C0700P68G10> after:{YYYY-MM-DD}`
- `include_bots: true`, `sort: timestamp`, `sort_dir: asc`, `limit: 20`

Convert each `ts` to **Europe/Amsterdam** — never raw UTC:

```bash
python3 -c "
import sys, datetime, zoneinfo
dt = datetime.datetime.fromtimestamp(float(sys.argv[1]), zoneinfo.ZoneInfo('Europe/Amsterdam'))
print(dt.strftime('%d %b %Y, %-I:%M %p'))
" {ts}
```

If a release has **no** `ANA release … success` notification, write `—` and say so in the caveats. Do **not** substitute the GitHub tag time or the pipeline `SdkVer Release (ANA)` success time — those are different events, running 2–5 hours earlier, and mixing them makes the column incomparable.

---

## Step 5 — Open-criticals check

Collect every bug key the board records as Critical. Query their current status:

```
key in ({critical keys}) ORDER BY key ASC
```

Fields `["summary", "status", "customfield_10140"]`, `view: evidence`.

- **All in a Done status category** → banner reads `**No open critical issues.** Every bug recorded as Critical in ANA release testing across {lines} is now in a Done status.`
- **Any still open** → banner lists them: `**{N} open critical issue(s):** {key} — {summary}` for each.

Some keys resolve to a **different key** (triage moved them) and some now carry a different Severity than the round recorded. Note both in the caveats; keep the round's label in the table.

---

## Step 6 — Stale Epic statuses

An Epic whose children are **all Done** but whose own status is not Done (seen in `Funnel` and `In Progress`) has a stale status. Collect these and list them in the caveats, so a reader knows to trust the per-stream statuses over the Epic.

Do not change the Epic — this skill only reports.

---

## Step 7 — Write the page

`updateConfluenceContent` with `contentId: 2561638669`, the `snapshotToken` from a fresh read, `body: {format: html, value: {full page}}`.

The skill owns the page, so a **full-body replacement is correct here** — unlike the ANA Versions Tested skills, which must do granular edits on a page other people own.

Page structure, in order:

1. Intro — what it tracks, sources, and the refresh date
2. Open-criticals banner (Step 5)
3. Severity note — graded by Jira **Severity**, not Priority; counts come from each round's record on ANA Versions Tested and span all projects and all reporters
4. A line explaining the three ANA streams (Sanity desk / APAC / Drive test)
5. **Now in work & recently finished** — the pulse: anything not finished, plus the most recent completed rounds, newest build first. Columns: Release · NavSDK · Sanity · APAC · Drive test · Build appeared · Bugs found (summarised as counts only)
6. **By release line** — one `h4` and table per line, newest line first, newest RC first within each. Columns: ANA release (with its Epic link) · NavSDK · Sanity (desk) · APAC · Drive test · Bugs found (by severity, with keys)
7. **How to use this board**
8. **Caveats for this snapshot** — refresh date and that it is script-written; stale Epic statuses (Step 6); severity drift (Step 5); moved bug keys; any RC with no validation record at all

Always `dryRun: true` first and check the result before writing for real.

Set `contentWidth: wide` — six columns of links need the room.

---

## Step 8 — Report

```
✅ ANA Release Validation Board refreshed (v{new_version})
   Lines: {lines}   Releases: {n}   Epics: {n}   Children: {n}
   Open criticals: {none | list}
   ⚠ Stale Epic statuses: {keys}
   ⚠ No release notification (build time blank): {versions}
   Page: https://tomtom.atlassian.net/wiki/spaces/ANA/pages/2561638669/
```

---

## Constraints

- The board page is always `2561638669`; ANA Versions Tested is always `1448476996`; `cloudId` is always `tomtom.atlassian.net`; the Slack channel is always `C0700P68G10`. Never ask for any of them.
- Validation Epics are always the children of **NAV-202198**.
- Filter out non-ANA Epics that the fuzzy `summary ~` match returns.
- Classify children **APAC → Drive test → Sanity**, in that order.
- Bug counts come from the **ANA Versions Tested Comments column**, never from a reporter-scoped JQL — the page records all projects and all reporters, which a NAV-only query misses.
- Reproduce each round's **stated** counts even when they disagree with the keys listed; never silently recount.
- Severity comes from the round's record; the ticket's current `customfield_10140` is only used for the open-criticals check and the drift note. Never use Jira **Priority** as severity.
- Build times come **only** from the `*ANA release … success*` Slack notification, rendered in Europe/Amsterdam. Never substitute a GitHub tag or pipeline-success time.
- Full-body replacement is correct for this page and only this page.
- Always `dryRun` before writing, and pass the `snapshotToken` from the same read; on conflict re-read and retry once rather than forcing.
- Report stale Epic statuses and severity drift — never "fix" them in Jira from this skill.
