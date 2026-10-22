# setup-new-ana-rc

End-to-end setup for a **newly released ANA RC**. Detects new releases from Slack, then for each one:

1. Creates the RC validation **Epic** (by invoking `create-ana-rc-validation-ticket`)
2. Creates **2 child work items** under that Epic — desk sanity and APAC sanity (**none for rc01**, which is regression-tested by hand-planned area tests, and **none while the previous RC's Epic is still Open/Funnel**, Step 5-pre2)
3. Adds (or enriches) the version's row on the [ANA Versions Tested](https://tomtom.atlassian.net/wiki/spaces/ANA/pages/1448476996/ANA+Versions+Tested) Confluence page, including the **build date/time** and the **owner tag** in each testing column
4. For every release: sets the Epic's **Target end** to the build date + 5 working days (RC) or + 2 working days (final or patch release), and puts a **Planned, To be finished by {date}** line in the row's Comments cell. On every run, it also strikes that line through once the round's testing is Done (Step 6f).

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
- `channel_id`: `C0700P68G10` (**#navigation-pipelines-alerts**)
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

**On 2 October 2026 this replaced the old `*ANA release {version} success*` format, but only on the newest release line.** `0.13.0-rc01` was the first build under the new scheme. It has no `ANA release … success` message, and that is not a fault.

**Older release branches still post the legacy format, so accept both formats at any date.** On 6 October 2026, `0.10.3` and `0.11.1` came from release/0.10 and release/0.11 as `*ANA release {version} success*` messages, while `0.13.0-rc02` came as `SdkVer Release (ANA)`. A date cut-off on the legacy format would have silently dropped both patch releases. If one version appears in both formats, deduplicate on the version and use the earlier `ts`.

The legacy message carries the NavSDK version as `*NavSDK Version:* {navsdk_version}` in its attachment. Use it for the same cross-check described below.

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
| *(legacy)* `*ANA release {version} success*` | ✅ Process, at any date. Older release branches still use this format. |
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

- **Epic exists** → do not create another. Record its key and continue to Steps 4a, 5 and 6, which will fill in anything still missing (children, Confluence row). Report the version as "Epic already existed".
- **No Epic** → continue to Step 4.

---

## Step 4 — Create the validation Epic

Invoke the **`create-ana-rc-validation-ticket`** skill with `navapp_version = {version}`.

Do not re-implement any of it. That skill owns NavSDK version resolution, previous-version derivation, the fixes table, the Epic fields, the sanity checklist comment and its own Slack notification — and it has its own duplicate guard.

**Patch releases (`X.Y.Z` with `Z > 0`, e.g. `0.11.1`) need the previous version passed in.** They have no RC tags of their own, so the Epic skill's final-release lookup ("last `X.Y.Z-rcNN` tag") finds nothing. Use `prev_navapp_version = X.Y.(Z-1)` (e.g. `0.11.1` → `0.11.0`, `0.10.3` → `0.10.2`). This is what was confirmed by hand on 2026-10-06. Check that the tag exists before using it. If it doesn't, stop for this version and report it, because an unattended run cannot ask. Take `prev_navsdk_version` from `gosdk-libs.versions.toml` at that previous tag. Build the fixes table from the `fix(NAV-…)` commits in the `{prev}...{version}` diff, as the final-release path does. A ticket that carries the fixVersion but has no commit in the diff (e.g. NAV-209472 on 0.10.3) is left out of the table. Mention it in the report.

Record from its output:
- `epic_key` and `epic_url`
- `navsdk_version` (needed for the Confluence row)

**If it fails or stops** (e.g. it cannot resolve a version id, or the fixes table can't be built), **stop for this version**. Do not create children or a Confluence row pointing at an Epic that doesn't exist. Report the failure and move to the next version.

### 4a — Target end on the Epic (every release)

The user asked for this on 2026-10-13. A stakeholder kept asking in Slack when a round would finish, and the page didn't say.

| Version shape | Example | Working days added |
|---|---|---|
| `X.Y.Z-rcNN` (rc01 included) | `0.12.0-rc07` | **5** |
| Patch release `X.Y.Z`, `Z > 0` | `0.9.6`, `0.10.3` | **2** (added 2026-10-13) |
| Final release `X.Y.0` | `0.11.0` | **2** (added 2026-10-13) |

In short: **5 for an RC, 2 for anything without an RC suffix.**

- **Date:** `build_date` plus that many **working days** (`N` below), skipping Saturdays and Sundays. `build_date` is the calendar date of the Slack `ts` in Europe/Amsterdam (Step 2c). Public holidays are not skipped. Examples: 0.12.0-rc07 was built on Fri 9 Oct 2026, so Target end is Fri 16 Oct 2026. A patch built on Fri 9 Oct would get Tue 13 Oct.

  ```bash
  python3 -c "
  import sys, datetime, zoneinfo
  d = datetime.datetime.fromtimestamp(float(sys.argv[1]), zoneinfo.ZoneInfo('Europe/Amsterdam')).date()
  n = 0
  while n < int(sys.argv[2]):
      d += datetime.timedelta(days=1)
      if d.weekday() < 5: n += 1
  print(d.isoformat())
  " {ts} {N}      # N = 5 for an RC, 2 for a final or patch release
  ```

- **Field:** `customfield_10023` (**Target end**), format `YYYY-MM-DD`, set with `editJiraIssue` on `{epic_key}`. Leave **Target start** (`customfield_10022`) alone; the user said to skip it.
- **Idempotency:** read the Epic's Target end first. If it is already set, **keep it**, even if it differs from the computed date. Someone may have moved the plan on purpose. Use the value that's there for the planned line in Step 6.
- **No build time** (a `version` forced without one): set nothing, and report it.
- If the edit is rejected, report the error and carry on. Write no planned line, because it must match Jira.

---

## Step 5 — Create the child work items (none for rc01)

### 5-pre — Skip children entirely for rc01

**If `version` ends with `rc01`, create no child work items at all.** Go straight to Step 6.

An rc01 is validated as a **full regression** spread across named area tests (Route planning, Map Experience, DX UI, Search, E2E) rather than the single desk/APAC sanity pair — the testing scope on an rc01 Epic reads `Regression Test`, not `Sanity test`. Who owns which area is decided per release by the team, so the split cannot be derived here. Creating the two sanity tickets anyway produces work items nobody uses, sitting alongside the real area tests.

Report rc01 as `Epic created, no children (rc01 — area tests are planned by hand)`.

This applies to any version the Epic treats as a first RC, including one forced with `treat_as_first_rc = yes`.

### 5-pre2 — Skip children while the previous RC hasn't started

The user asked for this on 2026-10-22, ahead of 0.13.0-rc04. When a new RC lands before testing of the previous RC has even started, the team picks up the newer build instead. Children created for the older round would sit unused next to the new ones.

**Applies to `X.Y.Z-rcNN` with `NN ≥ 02`.** Final and patch releases (no RC suffix) are not affected.

1. Find the **previous RC's Epic** in the same release line: the Epic under NAV-202198 whose summary is `ANA RC X.Y.Z-rcMM validation` (or `ANA X.Y.Z-rcMM validation`) with the **highest `MM` below `NN`**. Match exactly, because `~` is fuzzy. A combined Epic counts when either side of the slash matches, e.g. `ANA RC 0.12.0-rc06/07 validation` for rc07.

   ```
   project = NAV AND issuetype = Epic AND parent = NAV-202198 AND summary ~ "X.Y.Z-rc" ORDER BY created DESC
   fields: ["summary", "status"]
   ```

2. **Its status is `Open` or `Funnel`** (testing not started): **create no child work items** for this version. Create the Epic as normal (Step 4, with Target end from 4a) and go on to Step 6.
   - **Confluence row:** add or enrich it as usual. The desk and APAC owner cells get the **mention only**, with no child macro, the same as an rc01 with no children yet (6d).
   - **Previous Epic left alone:** don't change its status or anything else about it.
3. **Its status is anything else** (In Progress, Done, Blocked…), or **no previous Epic is found** (e.g. a skipped RC), or the previous version is rc01: create the children as normal (5a).

Report it as `Epic created, no children (previous RC {prev_version} {prev_epic_key} still {status})`.

**Re-runs:** the check runs again every time Step 5 is reached. A later manual run with `version = {version}`, once the previous Epic has moved on, creates the children then. Steps 5c and 6d stop duplicates and fill the owner cells.

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
| Row exists, cells empty | **Enrich in place**: fill Release version, Ticket, Configuration and the three owner columns (with the child-ticket links, 6d). Never add a second row. |
| Row exists with a non-empty cell | **Leave that cell exactly as it is** and fill only the empty ones. Report which cells were left alone. |

Never overwrite a non-empty cell — Go/No-Go and Comments in particular are owned by QA and by `add-testing-analysis-confluence`. The planned line (6d) is the one exception: it is **added** to the Comments cell, never replacing what's there, and only this skill's own line is ever struck through (6f).

### 6d — Cell contents

| Column | Content |
|---|---|
| Release version | `<strong>{version}</strong>({navsdk_version})Build : {build_datetime}` |
| Ticket | the Epic as an inline **Jira issue macro** (`key = {epic_key}`, `showSummary = false`), the same shape as the child tickets below, so the cell shows the key and the Epic's live status. Not a plain link. |
| Configuration | `Orbis + Daichi + Online_first` then `Ref App - Release` (copy the exact shape from the row above — it is two lines in one cell) |
| Full Regression(Includes Drive Test) / Sanity(Exploratory) | mention **Ashwini Manohar Pawar**, then the desk sanity child (`Sanity Testing for ANA {version}`) as an inline smart link on its own line |
| Drive Test ? | mention **Max Bogers** (no ticket — Drive test is not created per RC, Step 5b) |
| APAC Tested ? | mention **Joy Salem**, then the APAC sanity child (`[APAC] Sanity Testing for ANA {version}`) as an inline smart link on its own line |
| Go/ No-Go Recommendation | **empty** |
| Comments | the **planned line** (below) |

Mention accountIds:

| Person | accountId |
|---|---|
| Ashwini Manohar Pawar | `712020:1c9e3001-3ab7-410a-b27f-56bdaef3627a` |
| Max Bogers | `70121:c8bb703b-bf46-419e-9e84-4b9f89bd5d55` |
| Joy Salem | `70121:06132251-8fb4-4c83-b36e-ed3991d620a6` |

Author a mention as `<span data-type="mention" data-user-id="{accountId}">@{Display Name}</span>`. Confirm the exact node shape against the format guide from 6a before writing — if the mention node is rejected, fall back to the plain text `@{Display Name}` and say so in the report rather than failing the whole row.

Leave Go/No-Go empty. The owner columns carry **who** and **which ticket**, not a date.

**Planned line (every release, added 2026-10-13):** the Comments cell gets the Epic's Target end (Step 4a) as one paragraph, in the shape the user wrote by hand for 0.12.0-rc07 (page v625): bold text, a Confluence date, then a plain `*`.

```html
<p><strong>Planned, To be finished by </strong><time datetime="{target_end}">{Month D, YYYY}</time>*</p>
```

- Use the date that is **on the Epic**, not one you computed, so the page and Jira always agree.
- **The `*` points to a note at the top of the page:** `* Planned dates may change due to other priorities / team capacity.` (in italics). It was added on 2026-10-13 (page v626) as the first paragraph, before `Release Version :`. Write it there **only if no paragraph on the page already starts with `* Planned dates may change`**, using `insertNodeBefore` on the page's first paragraph. Never edit or move it once it's there.
- **Empty Comments cell:** `replaceNode` on its empty paragraph.
- **Non-empty Comments cell without the line:** `insertNodeBefore` its first paragraph, so the plan sits on top and nothing is replaced.
- **A plan is already in the cell**, in any wording: `Planned, To be finished by`, `Planned, Will be Done by`, `planned for {date}`, struck through or not. Leave the cell alone. Someone wrote it by hand, and a second line would contradict it.
- **No Target end on the Epic:** write no line, and report it.

**Child ticket + live status (added 2026-10-06):** in the desk and APAC cells, put the child from Step 5 in a second paragraph after the mention, as an inline **Jira issue macro** with the summary hidden:

```html
<p><span data-type="mention" data-user-id="{accountId}">@{Display Name}</span></p>
<p><span data-type="inline-extension" data-extension-key="jira" data-extension-type="com.atlassian.confluence.macro.core" data-parameters='{"macroParams":{"key":{"value":"{child_key}"},"showSummary":{"value":"false"}},"macroMetadata":{"schemaVersion":{"value":"1"},"title":"Jira Legacy"}}'></span></p>
```

It renders as the linked key plus a **status lozenge read live from the ticket** (Open → In Progress → Done), so nobody has to update the cell. This is what the user asked for. Two other forms were tried and rejected on 2026-10-06:
- **Static `NAV-XXXXXX | Open` text:** it goes stale.
- **An inline smart card** (`data-card-appearance="inline"`): it isn't the key | status shape the user wants.

The macro shape is copied from an existing one on the ANA page *Q4 2026 UxLibrary* (2462515985). Only `key` is needed, with no `serverId`. Omit `macroId`, because Confluence generates it. Verified on page v565. Use the child keys whether this run created them or found them already present (Step 5c).

**rc01, and any version without the sanity pair:** this skill creates no children for an rc01 (Step 5-pre) or while the previous RC is still Open/Funnel (Step 5-pre2), but the team adds area-test tickets under the Epic by hand. Link **whatever children already exist**, matched to a column by **assignee**:

```
parent = {epic_key} ORDER BY key ASC      fields: ["summary", "assignee"]
```

| Assignee accountId | Column |
|---|---|
| `712020:1c9e3001-3ab7-410a-b27f-56bdaef3627a` (Ashwini) | Full Regression / Sanity |
| `70121:06132251-8fb4-4c83-b36e-ed3991d620a6` (Joy Salem) | APAC Tested ? |

Rules for this matching:
- **Placement:** each matched child gets its own Jira-macro paragraph, inserted with `insertNodeAfter` directly after that person's **mention paragraph**. Keep key order.
- **Who gets matched:** match on assignee, never on summary text. Children assigned to anyone else are left out, and so are unassigned children. Report them so a person can place them. The Drive Test column and Max Bogers get no ticket (Step 5b).
- **Existing cell content:** the owner cell may already hold hand-written lines (e.g. `In-progress {date}`). Leave them exactly as they are. This adds paragraphs and never replaces any.
- **Duplicates:** skip any child whose key already appears in the cell, as a macro, a link or plain text. A re-run must not add a second copy.
- **No children yet:** the cell holds only the mention. Report `rc01 — no child tickets under {epic_key} yet`.

First done by hand on 2026-10-06 for 0.13.0-rc01 (page v569): NAV-209696 "DX UI" went to Ashwini's column and NAV-209697 "[APAC] validation" went to Joy's.

⚠️ An rc01's area tickets are often filed **after** the scheduled run that set the version up. The Step 2d window guard stops later runs from revisiting it, so tickets filed later have to be linked with a manual run: `version = {rc01 version}`. That run goes through Step 3 ("Epic exists") and on to this enrichment.

When **enriching** an existing row whose owner cell holds only the mention and no child link, add the link with `insertNodeAfter` on the mention paragraph's `data-local-id`. That fills a gap and is not an overwrite. If the cell already holds anything else, leave it alone (6c).

### 6e — Write it

**Prefer a granular edit over a full-body replacement** — the page is ~235 KB and owned by other people, so it cannot be passed through a tool call in one piece anyway.

**Enriching an existing row (the normal case):** `replaceNode`, once per cell, targeting the **empty paragraph's** `data-local-id` inside that `<td>` — not the row's and not the cell's:

```json
edits: [
  { "name": "replaceNode", "localId": "<the empty <p>'s data-local-id>",
    "value": "<p><span data-type=\"inline-extension\" data-extension-key=\"jira\" data-extension-type=\"com.atlassian.confluence.macro.core\" data-parameters='{\"macroParams\":{\"key\":{\"value\":\"NAV-XXXXXX\"},\"showSummary\":{\"value\":\"false\"}},\"macroMetadata\":{\"schemaVersion\":{\"value\":\"1\"},\"title\":\"Jira Legacy\"}}'></span></p>" }
]
```

Verified working on 2026-10-05. Omit `data-local-id` on the replacement node — the server assigns one.

⚠️ **Do not use `appendNodeToEnd` to add a row to a table on this page.** The `<tbody>` tags here carry **no** `data-local-id`, so there is no valid tbody target, and aiming it at the **table's** `data-local-id` appends the `<tr>` *after* `</table>` — an orphaned row outside any table, at the very end of the page body. Caught by the dryRun diff on 2026-10-05; it would have published malformed markup.

**Adding a new row:** use `insertNodeAfter` with `localId` set to the **last `<tr>`'s `data-local-id`** in the target table. Rows on this page do carry ids, even though `<tbody>` does not. Copy each cell's `data-colwidth` and `data-background` from that row, and omit `data-local-id` on the new nodes. This was verified on 2026-10-06 (page v549): it added 0.13.0-rc02, 0.11.1 and 0.10.3 in one batched call, and the dryRun row diff showed exactly 3 inserts, each inside its own table. In the dryRun, the raw count of `<table` goes up by one. That comes from an existing `legacy-content` macro whose `data-parameters` payload is re-escaped (`&lt;table` → `<table`). It is not a new table. Check the `</table>` count and the row diff instead.

If a version has no row and even `insertNodeAfter` can't place one inside the table, **report that and stop for that version** rather than writing a malformed page. Do not fall back to a full-body replacement on a page this large that other people own.

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

### 6f — Strike through finished plans (every run)

**Run this on every run, even when Slack shows no new release.** A round finishes days after its release, long after the Step 2d window has closed on it. The user asked for this on 2026-10-13: once testing is Done, keep the wording as it is and strike it through.

1. On the page from 6a, find every paragraph containing `Planned, To be finished by` that is **not** struck through yet (no `<s>` around it), in the release-line tables only. Never look in the Mainline Validation tables.
2. Take the Epic key from each row's Ticket cell. It's a Jira macro (`macroParams.key.value`) or a link.
3. Query those Epics and their children in one go:

   ```
   key in ({epic keys}) OR parent in ({epic keys})      fields: ["status", "parent"]
   ```

4. Testing is **Done** when the Epic's status category is Done, **or** the Epic has at least one child and every child's status category is Done. Epic statuses are often left stale (Funnel or In Progress after all the testing finished), so the children count as well.
5. For each Done round, `replaceNode` the line's paragraph with the same wording, struck through:

   ```html
   <p><s><strong>Planned, To be finished by </strong>{Month D, YYYY}*</s></p>
   ```

   The date goes in as **plain text**, copied from the date node's `datetime`. A Confluence date node can't carry the strikethrough mark, so leaving the node in place would strike only the words and not the date.

- **Only strike a line that's still exactly as this skill wrote it:** the bold `Planned, To be finished by `, one date node, then `*`, with nothing else in the paragraph. A line without the `*` (written before 2026-10-13) also counts; strike it as-is, without adding a `*`. If it has been changed by hand in any way (extra text, other wording, a typed date instead of a date node, other formatting), **leave it untouched** and report `planned line edited by hand, not struck: {version}`. The user asked for this on 2026-10-13: manual changes on the page are never overwritten.
- **The date comes from the cell, not from Jira.** If someone moved the date on the page, the struck line keeps their date, even when the Epic's Target end says something else.
- **Leave the line alone when testing isn't Done**, even if the date has passed. An overdue plan should stay visible.
- **Never strike another line** in the cell, and never change the wording or the date.
- **Batch:** put every strike in the same write as any row edits from this run, with the same dryRun and `<tr>` list check. Exactly the struck rows may differ.
- **Nothing to strike and no new release:** make no write at all.

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
ℹ  No children created (previous RC not started): {version} — {prev_version} {prev_epic_key} is still {Open/Funnel}
   Linked existing children by assignee: {key} → Ashwini, {key} → Joy  (or "none under {epic_key} yet")
⚠  Children not placed (other assignee / unassigned): {key} ({assignee}), ...
⚠  Cells left untouched because they were already filled: {column}, ... for {version}
📅 Target end set: {epic_key} → {date} ({version})   (or "kept existing {date}")
✂️ Planned line struck through (testing Done): {version}, ...
✋ Planned line edited by hand, not struck (strike it manually): {version}, ...
⚠  No planned line: {version} ({reason: no Target end / edit rejected / no build time})
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

- The Slack channel is always `C0700P68G10` (**#navigation-pipelines-alerts**) — never ask for it.
- The Confluence page is always `1448476996` — never ask for it.
- `cloudId` is always `tomtom.atlassian.net` — never ask for it.
- **Always bound the Slack scan with the `oldest` timestamp from Step 1.** Never rely on `limit` to mean "recent".
- Never process a version whose notification predates the window, even if it has no Epic. Report it instead.
- Use `response_format: detailed` on the Slack read — the message `ts` is the build time and `concise` omits it.
- Render `build_datetime` in **Europe/Amsterdam**, never raw UTC.
- Match the `SdkVer Release (ANA)` success notification on `tomtom-internal/navapp-automotive` **and** the legacy `*ANA release {version} success*` at any date (Step 2). Older release branches still post the legacy format.
- **Never match the `SdkVer Release (UXL)` twin** — same version, ~4 s earlier — nor a `:x:` failed run, a `go-sdk-android` release, or a `Promote to Public …` run.
- Do not blanket-ignore `:white_check_mark:` pipeline messages; the notification this skill needs is one.
- Skip any version containing `-dev`.
- **Never create a Drive test work item** (Step 5b) — it is a shared, multi-RC task owned by the Drive Test team.
- **No child work items for an rc01** (Step 5-pre) — rc01 is a full regression split into area tests planned by hand, not the desk/APAC sanity pair.
- **No child work items while the previous RC's Epic is Open or Funnel** (Step 5-pre2): create the Epic only, and leave the previous Epic untouched.
- For rc02 and later: exactly 2 children, both `Test Execution`, assigned as in Step 5a. Never substitute a different issue type if `Test Execution` is rejected — report instead.
- Delegate Epic creation entirely to `create-ana-rc-validation-ticket`; never re-implement its steps.
- If Epic creation fails, create no children and no Confluence row for that version.
- Never overwrite a non-empty Confluence cell. Go/No-Go is always left empty by this skill. Comments gets only the planned line, which is added and never replaces anything (6d).
- Target end = build date + 5 working days for an RC, + 2 for a final or patch release (no RC suffix), never overwriting an existing value; leave Target start alone (Step 4a).
- Step 6f runs on **every** run, even with no new release. It strikes through only this skill's own `Planned, To be finished by` line, and only once testing is Done (the Epic Done, or all its children Done).
- **Never overwrite a manual change on the page.** A planned line edited by hand is never struck or rewritten. A cell that already holds a plan in any wording gets no second line. Any date someone typed on the page wins over the Epic's (6d, 6f).
- Never add a second row for a version that already has one — enrich the existing row.
- Never touch the **Mainline Validation** tables or the final `Releases :` / `NavSDK Mapping` table.
- Never create a release-line section that doesn't exist — report and stop for that version.
- Always `dryRun` the Confluence update and verify it **by comparing extracted `<tr>` lists**, never a character diff — the server regenerates every `data-local-id` on write (Step 6e).
- Enrich cells with `replaceNode` on the empty paragraph's `data-local-id`. Add a row with `insertNodeAfter` on the table's last `<tr>` id. **Never `appendNodeToEnd` against a table's id**, because it orphans the row outside the table (Step 6e).
- For a patch release (`X.Y.Z`, `Z > 0`), pass `prev_navapp_version = X.Y.(Z-1)` to the Epic skill after checking the tag exists (Step 4).
- Find a release-line table by its own `<table> … </table>` span, never by slicing to the next bold paragraph — the table can run past it (Step 6b).
- Always pass the `snapshotToken` from the same read; on conflict re-read and retry once rather than forcing.
