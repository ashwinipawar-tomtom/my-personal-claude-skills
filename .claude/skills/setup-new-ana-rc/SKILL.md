# setup-new-ana-rc

End-to-end setup for a **newly released ANA RC**. Detects new releases from Slack, then for each one:

1. Creates the RC validation **Epic** (by invoking `create-ana-rc-validation-ticket`)
2. Creates **2 child work items** under that Epic — desk sanity and APAC sanity (**none for rc01**, which is regression-tested by hand-planned area tests)
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

Match the **`SdkVer Release (ANA)`** success notification (bot: `ACME Notifier`):

```
:white_check_mark: *tomtom-internal/navapp-automotive {version}*: SdkVer Release (ANA) run from event workflow_dispatch successful: <run> @ {ISO time}, SHA: <sha>, BRANCH: {branch}
*NavSDK:* {navsdk_version}
*ANA:* </com/tomtom/automotive/app-ana/{version}|Main> · Edge: … · API docs
```

All four conditions must hold: repo is **`tomtom-internal/navapp-automotive`**, the text contains **`SdkVer Release (ANA)`**, it is the **success** variant (`:white_check_mark:` / `successful`), and the version comes from the `*tomtom-internal/navapp-automotive {version}*` prefix.

**This replaced the old `*ANA release {version} success*` format on 2 October 2026.** `0.13.0-rc01` was the first build under the new scheme — it has no `ANA release … success` message, and that is not a fault. Still accept the old shape for anything released before that date, so historical runs stay reproducible.

The new message also carries **`*NavSDK:* {navsdk_version}`** inline. Use it as a cross-check against the version read from `gradle/gosdk-libs.versions.toml` at the tag; the toml stays authoritative, and a mismatch is worth reporting rather than silently preferring one.

### 2a — Must NOT match

| Notification | Action |
|---|---|
| `… navapp-automotive {version}*: SdkVer Release (ANA) … successful` | ✅ Process |
| `… navapp-automotive {version}*: SdkVer Release (UXL) … successful` | ❌ **Ignore.** The twin, posted ~4 seconds earlier for the same version. Matching it would double every release. |
| `:x: … SdkVer Release (ANA) … failed` | ❌ Ignore — a failed run is not a release. |
| `… go-sdk-android {version}*: Release pipeline run …` | ❌ Ignore silently — that is a NavSDK release, not ANA. |
| `… Promote to Public Release` / `Promote to Public Pre-Release` | ❌ Ignore — promotion of an already-tested build. Report under "Ignored". |
| `:gear:` / `:github-pr-merged:` intake-PR messages | ❌ Ignore entirely. |
| *(legacy)* `*ANA release {version} success*` | ✅ Process — pre-2 Oct 2026 only. |
| *(legacy)* `*ANA Public release {version} success*` | ❌ Ignore — promotion. Report under "Ignored". |
| *(legacy)* `*UXL release {version} success*` | ❌ Ignore silently — different product. |

⚠️ **Do not use a blanket "ignore all `:white_check_mark:` pipeline notifications" rule.** That was correct for the old format and is now wrong — the notification this skill depends on *is* a `:white_check_mark:` pipeline message. Discriminate on repo + `SdkVer Release (ANA)` + success, as above.

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

Use the **Slack message `ts`**, not the `@ {ISO time}` embedded in the message text. They differ by only a few seconds, but `ts` is what every existing row was built from.

⚠️ **Build times are not comparable across 2 October 2026.** The old `ANA release … success` event fired 2–5 hours *after* the `SdkVer Release (ANA)` pipeline, so times recorded from the new notification are earlier in the day than historical rows for the same point in the process. Never retro-fill or "correct" an older row to match.

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

## Step 5 — Create the child work items (none for rc01)

### 5-pre — Skip children entirely for rc01

**If `version` ends with `rc01`, create no child work items at all.** Go straight to Step 6.

An rc01 is validated as a **full regression** spread across named area tests (Route planning, Map Experience, DX UI, Search, E2E) rather than the single desk/APAC sanity pair — the testing scope on an rc01 Epic reads `Regression Test`, not `Sanity test`. Who owns which area is decided per release by the team, so the split cannot be derived here. Creating the two sanity tickets anyway produces work items nobody uses, sitting alongside the real area tests.

Report rc01 as `Epic created, no children (rc01 — area tests are planned by hand)`.

This applies to any version the Epic treats as a first RC, including one forced with `treat_as_first_rc = yes`.

### 5a — The two children (rc02 and later)

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

### 5b — Never create a Drive test ticket

**Do not create a Drive test work item.** Drive testing is tracked on its own long-running task that spans several RCs (e.g. `ANA 0.12.0-rc04/05 Drive test`), owned and maintained by the Drive Test team. Creating a per-RC Drive test ticket would duplicate it.

If an existing Drive test task is already parented to this Epic, leave it alone.

### 5c — Idempotency

Before creating, list existing children:

```
parent = {epic_key}
```

Skip any child whose summary already matches the target summary. Never create a second copy. If both already exist, report "children already present" and continue to Step 6.

### 5d — If `Test Execution` is rejected

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

⚠️ **Do not slice the page to the next bold paragraph and then read rows out of that slice.** A release-line table can extend *past* the point where the next bold heading appears, so rows fall outside the slice and an existing row looks absent. On 2026-10-05 this made the 0.13 table read as header-only when it already held a 0.13.0-rc01 row, and nearly produced a duplicate. Instead locate the table by its own `<table> … </table>` span and enumerate the `<tr>`s inside **that**.

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

**Prefer a granular edit over a full-body replacement** — the page is ~235 KB and owned by other people, so it cannot be passed through a tool call in one piece anyway.

**Enriching an existing row (the normal case):** `replaceNode`, once per cell, targeting the **empty paragraph's** `data-local-id` inside that `<td>` — not the row's and not the cell's:

```json
edits: [
  { "name": "replaceNode", "localId": "<the empty <p>'s data-local-id>",
    "value": "<p><a href=\"https://tomtom.atlassian.net/browse/NAV-XXXXXX\">NAV-XXXXXX</a></p>" }
]
```

Verified working on 2026-10-05. Omit `data-local-id` on the replacement node — the server assigns one.

⚠️ **Do not use `appendNodeToEnd` to add a row to a table on this page.** The `<tbody>` tags here carry **no** `data-local-id`, so there is no valid tbody target, and aiming it at the **table's** `data-local-id` appends the `<tr>` *after* `</table>` — an orphaned row outside any table, at the very end of the page body. Caught by the dryRun diff on 2026-10-05; it would have published malformed markup.

If a version genuinely has no row and no granular operation will place one inside the tbody, **report that and stop for that version** rather than writing a malformed page. Do not fall back to a full-body replacement on a page this large that other people own.

Also pass `snapshotToken` from 6a, `minorEdit: true`, and `versionMessage: Set up ANA {version} validation row`.

**Always `dryRun: true` first**, and verify it with a script — the result is ~245 KB, far too large to eyeball.

**Do not use a character-level diff.** The server regenerates **every** `data-local-id` on write, so the whole body differs: on 2026-10-05 the common prefix between original and dryRun was 2,503 characters out of 235,000. Stripping the ids helps but other churn remains, and `difflib.SequenceMatcher` on strings that size does not finish in reasonable time.

**Compare at row level instead.** Extract every `<tr>` from both, flatten each to its cell text, and diff the two *lists*:

```python
def rows(s):
    s = html.unescape(s); out = []
    for r in re.findall(r'<tr[^>]*>.*?</tr>', s, re.S):
        cells = re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', r, re.S)
        out.append(' | '.join(re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', c)).strip() for c in cells))
    return out
```

The checks: when **enriching**, the row count must be **unchanged** and exactly one row may differ, in exactly the cells intended. When **adding**, the count must go up by exactly one. Anything else means stop and re-read.

**To undo a row added in error:** `edits: [{ "name": "deleteNode", "localId": "<that row's data-local-id>" }]`. (Not yet exercised on this page — `dryRun` it and check the row count drops by exactly one before writing.)

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
ℹ  rc01 — no children created (area tests are planned by hand): {version}
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

Scheduled as the cloud routine **ANA new RC setup** (`trig_013vPDdkVW5DxQQJwMJZaxYJ`), **every 6 hours** at `9 */6 * * *` UTC — 02:09, 08:09, 14:09 and 20:09 Amsterdam in summer. Model `claude-opus-5`; Atlassian + Slack + GitHub connectors; this repo checked out as the session source, so the routine reads this file rather than carrying a copy of it.

It runs with **`window_hours=7`**, not 6. Keep `window_hours` at least as large as the interval, or a release landing between runs is missed — and a missed release is then permanently out of scope by the Step 2d guard, so it has to be run by hand with an explicit `version`. The extra hour absorbs a late or retried run; the overlap is harmless because every step is idempotent.

**No authenticated `gh` CLI in the cloud sandbox.** `create-ana-rc-validation-ticket` shells out to `gh api` for the NavSDK version and the compare diffs; the routine's prompt redirects those to the GitHub MCP connector (`get_file_contents`, `list_tags`, `list_commits`) against `tomtom-internal`. If that mapping changes, update the routine prompt at https://claude.ai/code/routines/trig_013vPDdkVW5DxQQJwMJZaxYJ

Because this skill creates Jira issues and edits a shared Confluence page, a scheduled run has real side effects. The idempotency guards (Steps 3, 5c, 6c) are what make that safe — do not weaken them.

---

## Constraints

- The Slack channel is always `C0700P68G10` (**#gosdk-pipelines-alerts**) — never ask for it.
- The Confluence page is always `1448476996` — never ask for it.
- `cloudId` is always `tomtom.atlassian.net` — never ask for it.
- **Always bound the Slack scan with the `oldest` timestamp from Step 1.** Never rely on `limit` to mean "recent".
- Never process a version whose notification predates the window, even if it has no Epic. Report it instead.
- Use `response_format: detailed` on the Slack read — the message `ts` is the build time and `concise` omits it.
- Render `build_datetime` in **Europe/Amsterdam**, never raw UTC.
- Match the `SdkVer Release (ANA)` success notification on `tomtom-internal/navapp-automotive` (Step 2); accept the legacy `*ANA release {version} success*` only for builds before 2 Oct 2026.
- **Never match the `SdkVer Release (UXL)` twin** — same version, ~4 s earlier — nor a `:x:` failed run, a `go-sdk-android` release, or a `Promote to Public …` run.
- Do not blanket-ignore `:white_check_mark:` pipeline messages; the notification this skill needs is one.
- Skip any version containing `-dev`.
- **Never create a Drive test work item** (Step 5b) — it is a shared, multi-RC task owned by the Drive Test team.
- **No child work items for an rc01** (Step 5-pre) — rc01 is a full regression split into area tests planned by hand, not the desk/APAC sanity pair.
- For rc02 and later: exactly 2 children, both `Test Execution`, assigned as in Step 5a. Never substitute a different issue type if `Test Execution` is rejected — report instead.
- Delegate Epic creation entirely to `create-ana-rc-validation-ticket`; never re-implement its steps.
- If Epic creation fails, create no children and no Confluence row for that version.
- Never overwrite a non-empty Confluence cell. Go/No-Go and Comments are always left empty by this skill.
- Never add a second row for a version that already has one — enrich the existing row.
- Never touch the **Mainline Validation** tables or the final `Releases :` / `NavSDK Mapping` table.
- Never create a release-line section that doesn't exist — report and stop for that version.
- Always `dryRun` the Confluence update and verify it **by comparing extracted `<tr>` lists**, never a character diff — the server regenerates every `data-local-id` on write (Step 6e).
- Enrich cells with `replaceNode` on the empty paragraph's `data-local-id`. **Never `appendNodeToEnd` against a table's id** — it orphans the row outside the table (Step 6e).
- Find a release-line table by its own `<table> … </table>` span, never by slicing to the next bold paragraph — the table can run past it (Step 6b).
- Always pass the `snapshotToken` from the same read; on conflict re-read and retry once rather than forcing.
