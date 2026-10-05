# setup-new-ana-rc

End-to-end setup for a **newly released ANA RC**. Detects new releases from Slack, then for each one:

1. Creates the RC validation **Epic** (by invoking `create-ana-rc-validation-ticket`)
2. Creates **2 child work items** under that Epic — desk sanity and APAC sanity
3. Adds (or enriches) the version's row on the [ANA Versions Tested](https://tomtom.atlassian.net/wiki/spaces/ANA/pages/1448476996/ANA+Versions+Tested) Confluence page, including the **build date/time** and the **owner tag** in each testing column

Designed to run **unattended on a schedule**. Every step is idempotent, so a repeat run on an already-processed version changes nothing.

## Prerequisites

- Atlassian MCP authenticated. If not, ask the user to run `/mcp` and select **"claude.ai Atlassian"**.
- Slack MCP authenticated. If not, ask the user to run `/mcp` and select **"claude.ai Slack"**.
- `gh` CLI authenticated for `tomtom-internal` (needed by `create-ana-rc-validation-ticket`).

## Inputs

All optional — with no arguments the skill scans Slack and processes every new RC it finds.

| Input | Default | Notes |
|---|---|---|
| `window_hours` | `24` | Rolling window ending **now**, enforced with a real Unix timestamp (Step 1). Never with a message count. |
| `version` | — | Force one version (e.g. `0.12.0-rc06`), skipping the Slack scan. Only when the user names a version directly. The build time then has to come from the user or be left out. |

---

## Step 1 — Read Slack, bounded by a real timestamp

Compute the boundary first:

```bash
python3 -c "import time; print(int(time.time()) - 24*3600)"
```

That is `oldest_ts` (substitute `window_hours` for `24` if overridden).

Call `slack_read_channel` with:
- `channel_id`: `C0700P68G10` (**#gosdk-pipelines-alerts**)
- `oldest`: `{oldest_ts}` ← **required; this is what bounds the scan**
- `limit`: `100`
- `response_format`: `detailed` ← **not `concise`** — this skill needs each message's `ts`

⚠️ **`limit` is a page size, not a time window.** This channel carries ~10–20 messages a day, so `limit: 100` alone reaches back over a week. `oldest` is the only thing that scopes the run.

**Keep each matched message's `ts`** — it is the build time for Step 6.

If `version` was supplied, skip Steps 1–2 and go to Step 3 with that single version.

---

## Step 2 — Extract released ANA versions and their build times

Match **only** this exact shape (bot: `ACME Notifier`):

```
*ANA release {version} success*
```

### 2a — Must NOT match

| Notification | Action |
|---|---|
| `*ANA release {version} success*` | ✅ Process |
| `*ANA Public release {version} success*` | ❌ Ignore — promotion of an already-tested build. Report under "Ignored". |
| `*UXL release {version} success*` | ❌ Ignore silently — different product. |

Match the **full** pattern with `Public` explicitly excluded — never a loose `contains("ANA release")`. Ignore the `:white_check_mark:` / `:x:` / `:gear:` / `:github-pr-merged:` pipeline notifications entirely.

### 2b — Version shapes

| Shape | Example | Action |
|---|---|---|
| `X.Y.Z-rcNN` | `0.12.0-rc06` | ✅ Process |
| `X.Y.Z` | `0.11.0`, `0.9.5` | ✅ Process |
| contains `-dev` | `0.13.0-dev177.59b4ab17` | ❌ Skip — mainline dev builds belong to the **Mainline Validation** tables, which this skill never touches. Report as skipped. |

Deduplicate, keep **chronological order (oldest first)** so versions are processed in release order.

### 2c — Convert each `ts` to a build time

```bash
python3 -c "
import sys, datetime, zoneinfo
ts = float(sys.argv[1])
dt = datetime.datetime.fromtimestamp(ts, zoneinfo.ZoneInfo('Europe/Amsterdam'))
print(dt.strftime('%d %b %-I:%M %p'))
" {ts}
```

Gives e.g. `30 Sep 6:33 PM`. That string is `build_datetime`.

Always render it in **Europe/Amsterdam** — the page and the team work in that timezone, and a raw UTC time would be an hour or two off and silently wrong.

### 2d — Re-check every match against the window (hard guard)

Independently verify each matched notification falls inside the window and **discard any that does not**, even if `slack_read_channel` returned it.

This is a deliberate second line of defence. The job is only ever to set up **today's** releases. A version released days ago with no Epic is not this skill's business — it was either deliberately skipped or handled another way, and silently creating an Epic, two tickets and a Confluence row for it is a wrong and surprising set of edits. **Report it and do nothing.**

---

## Step 3 — Per-version duplicate guard

For each version, before doing anything, check whether the Epic already exists:

```
project = NAV AND issuetype = Epic AND summary ~ "{version}" ORDER BY created DESC
```

Match on a summary of `ANA RC {version} validation` or `ANA {version} validation` **exactly** — `~` is fuzzy and will also return the other RCs in the line.

- **Epic exists** → do not create another. Record its key and continue to Steps 5 and 6, which will fill in anything still missing (children, Confluence row). Report the version as "Epic already existed".
- **No Epic** → continue to Step 4.

---

## Step 4 — Create the validation Epic

Invoke the **`create-ana-rc-validation-ticket`** skill with `navapp_version = {version}`.

Do not re-implement any of it. That skill owns NavSDK version resolution, previous-version derivation, the fixes table, the Epic fields, the sanity checklist comment and its own Slack notification — and it has its own duplicate guard.

Record from its output:
- `epic_key` and `epic_url`
- `navsdk_version` (needed for the Confluence row)

**If it fails or stops** (e.g. it cannot resolve a version id, or the fixes table can't be built), **stop for this version**. Do not create children or a Confluence row pointing at an Epic that doesn't exist. Report the failure and move to the next version.

---

## Step 5 — Create the 2 child work items

Create these under the Epic with `createJiraIssue`, `parent: {epic_key}`:

| # | Summary | Issue type | Assignee | accountId |
|---|---|---|---|---|
| 1 | `Sanity Testing for ANA {version}` | `Test Execution` | Ashwini Manohar Pawar | `712020:1c9e3001-3ab7-410a-b27f-56bdaef3627a` |
| 2 | `[APAC] Sanity Testing for ANA {version}` | `Test Execution` | Joy Salem | `70121:06132251-8fb4-4c83-b36e-ed3991d620a6` |

Also set on both:
- `projectKey`: `NAV`
- `parent`: `{epic_key}`
- `customfield_10215`: `[{"id": "12825"}]` (Teams & Communities — [PT] Automotive NavApp)

Leave description, priority and dates empty — the assignee owns those.

### 5a — Never create a Drive test ticket

**Do not create a Drive test work item.** Drive testing is tracked on its own long-running task that spans several RCs (e.g. `ANA 0.12.0-rc04/05 Drive test`), owned and maintained by the Drive Test team. Creating a per-RC Drive test ticket would duplicate it.

If an existing Drive test task is already parented to this Epic, leave it alone.

### 5b — Idempotency

Before creating, list existing children:

```
parent = {epic_key}
```

Skip any child whose summary already matches the target summary. Never create a second copy. If both already exist, report "children already present" and continue to Step 6.

### 5c — If `Test Execution` is rejected

`Test Execution` (id `10007`) is an Xray type and may require extra fields in some projects. If the create is rejected, **report the exact error and the allowed values from the response, and stop for this version's children** — do not silently fall back to `Task`, because the type is what puts these on the test-execution board.

---

## Step 6 — Add or enrich the Confluence row

### 6a — Fetch the page

`getConfluenceContent` with `cloudId: tomtom.atlassian.net`, `content_id: 1448476996`, `detail: full`, `content_format: html`.

Keep the **`snapshotToken`** — required for the update.

The page returns `metadata.hasSpaceInstructions: false`, so **do not** call `getConfluenceSpace`.

The body is ~200 KB on a single line. If it is saved to a file, slice it by character range (`python3`, `cut -c`) rather than line-based reads.

Get the format guide once before authoring: `execute` with `name=getContentFormatGuide`, `inputs={toolName: "updateConfluenceContent"}`.

### 6b — Find the section and table

Release line = first two dot-separated components (`0.12.0-rc06` → `0.12`).

Sections are **bold paragraphs**, not headings, with inconsistent spacing: `**0.12 Releases :**`, `**0.11 Releases : **`. Match tolerantly — whitespace collapsed, trailing `:` stripped, equals `{release_line} Releases`.

**Target the LAST table in that section** — a section can be split across several tables (the 0.11 section is).

Release-line tables have **8 columns**:

```
Release version | Ticket | Configuration | Full Regression(Includes Drive Test) / Sanity(Exploratory) |
Drive Test ? | APAC Tested ? | Go/ No-Go Recommendation | Comments
```

Identify one by its first header cell reading **`Release version`**. The Mainline Validation tables use `ANA Version` — **never touch those**, nor the final `Releases :` / `NavSDK Mapping` reference table.

**If no section exists for the release line: report it and stop for that version.** Never create the section — a new release line needs the right heading and column set, which is the user's call.

### 6c — Existing row? Enrich, don't duplicate

Search the **whole section** (all its tables) for a row whose Release version cell contains this version. Compare on the version string only, ignoring bold markup, whitespace, and any trailing NavSDK/build text.

A version-only row may already be there — `add-ana-release-row-confluence` runs on its own schedule and adds bare version rows. **That is the expected case, not a conflict.**

| Found | Action |
|---|---|
| No row | Insert a new row (6d) |
| Row exists, cells empty | **Enrich in place**: fill Release version, Ticket, Configuration and the three owner columns. Never add a second row. |
| Row exists with a non-empty cell | **Leave that cell exactly as it is** and fill only the empty ones. Report which cells were left alone. |

Never overwrite a non-empty cell — Go/No-Go and Comments in particular are owned by QA and by `add-testing-analysis-confluence`.

### 6d — Cell contents

| Column | Content |
|---|---|
| Release version | `<strong>{version}</strong>({navsdk_version})Build : {build_datetime}` |
| Ticket | link to `{epic_url}`, text `{epic_key}` |
| Configuration | `Orbis + Daichi + Online_first` then `Ref App - Release` (copy the exact shape from the row above — it is two lines in one cell) |
| Full Regression(Includes Drive Test) / Sanity(Exploratory) | mention **Ashwini Manohar Pawar** |
| Drive Test ? | mention **Max Bogers** |
| APAC Tested ? | mention **Joy Salem** |
| Go/ No-Go Recommendation | **empty** |
| Comments | **empty** |

Mention accountIds:

| Person | accountId |
|---|---|
| Ashwini Manohar Pawar | `712020:1c9e3001-3ab7-410a-b27f-56bdaef3627a` |
| Max Bogers | `70121:c8bb703b-bf46-419e-9e84-4b9f89bd5d55` |
| Joy Salem | `70121:06132251-8fb4-4c83-b36e-ed3991d620a6` |

Author a mention as `<span data-type="mention" data-user-id="{accountId}">@{Display Name}</span>`. Confirm the exact node shape against the format guide from 6a before writing — if the mention node is rejected, fall back to the plain text `@{Display Name}` and say so in the report rather than failing the whole row.

Leave Go/No-Go and Comments empty. The owner columns carry **who**, not a date — no planned dates are set anywhere by this skill.

### 6e — Write it

**Prefer a granular edit over a full-body replacement.** Every node carries a `data-local-id`:

- New row → `edits: [{ "name": "appendNodeToEnd", "localId": "<target tbody data-local-id>", "value": "<new <tr> HTML>" }]`
- Enriching an existing row → target that row's cells, not the whole page

Also pass `snapshotToken` from 6a, `minorEdit: true`, and `versionMessage: Set up ANA {version} validation row`.

**Always `dryRun: true` first.** It returns the resulting HTML (large — save it and diff with a script, don't eyeball). The server normalises entities on round-trip (`'` ↔ `&#39;`), so compare **entity-normalised** text (`html.unescape`). The check: normalised original with the intended change applied must equal the normalised dryRun result exactly.

**To undo a row added in error:** `edits: [{ "name": "deleteNode", "localId": "<that row's data-local-id>" }]`.

**Batch all versions into a single page update** when processing several, rather than one write each.

**On a version conflict** (this page is edited often, by people and by the other ANA skills): re-read for a fresh `snapshotToken`, re-run the 6c checks (a row may have appeared meanwhile), retry once. Never pass a stale token and never force an overwrite.

---

## Step 7 — Report

```
✅ Set up ANA {version}
   Epic      : {epic_url}
   Children  : {child1_key} (Sanity, Ashwini), {child2_key} ([APAC] Sanity, Joy Salem)
   Confluence: row added / enriched in the {release_line} Releases table
               Build : {build_datetime}  (from the Slack release notification)

⏭  Already set up (no change): {version} — Epic {key}, children present, row present
⚠  Cells left untouched because they were already filled: {column}, ... for {version}
⚠  No section for release line {release_line} — nothing written for {version}
🚫 Skipped (mainline dev build): {version}, ...
🕒 Outside the {window_hours}h window — NOT processed: {version} (released {date}), ...
ℹ  Ignored "ANA Public release" notifications: {version}, ...
❌ Failed for {version}: {what failed and at which step}

Page: https://tomtom.atlassian.net/wiki/spaces/ANA/pages/1448476996/ANA+Versions+Tested
```

Omit lines with no entries. If nothing was created or changed, say so plainly rather than implying work was done.

---

## Running it on a schedule

This skill is written to run unattended. To schedule it, use the `schedule` skill with a prompt like:

```
Run the setup-new-ana-rc skill with window_hours=6
```

Every 6 hours with `window_hours=6` gives continuous coverage with no gap and no overlap. Keep `window_hours` at least as large as the interval, or a release landing between runs is missed — and a missed release is then permanently out of scope by the Step 2d guard, so it has to be run by hand with an explicit `version`.

Because this skill creates Jira issues and edits a shared Confluence page, a scheduled run has real side effects. The idempotency guards (Steps 3, 5b, 6c) are what make that safe — do not weaken them.

---

## Constraints

- The Slack channel is always `C0700P68G10` (**#gosdk-pipelines-alerts**) — never ask for it.
- The Confluence page is always `1448476996` — never ask for it.
- `cloudId` is always `tomtom.atlassian.net` — never ask for it.
- **Always bound the Slack scan with the `oldest` timestamp from Step 1.** Never rely on `limit` to mean "recent".
- Never process a version whose notification predates the window, even if it has no Epic. Report it instead.
- Use `response_format: detailed` on the Slack read — the message `ts` is the build time and `concise` omits it.
- Render `build_datetime` in **Europe/Amsterdam**, never raw UTC.
- Match only `*ANA release {version} success*`. `*ANA Public release …*` and `*UXL release …*` never trigger setup.
- Skip any version containing `-dev`.
- **Never create a Drive test work item** (Step 5a) — it is a shared, multi-RC task owned by the Drive Test team.
- Exactly 2 children, both `Test Execution`, assigned as in Step 5. Never substitute a different issue type if `Test Execution` is rejected — report instead.
- Delegate Epic creation entirely to `create-ana-rc-validation-ticket`; never re-implement its steps.
- If Epic creation fails, create no children and no Confluence row for that version.
- Never overwrite a non-empty Confluence cell. Go/No-Go and Comments are always left empty by this skill.
- Never add a second row for a version that already has one — enrich the existing row.
- Never touch the **Mainline Validation** tables or the final `Releases :` / `NavSDK Mapping` table.
- Never create a release-line section that doesn't exist — report and stop for that version.
- Always `dryRun` the Confluence update and confirm the diff before writing.
- Always pass the `snapshotToken` from the same read; on conflict re-read and retry once rather than forcing.
