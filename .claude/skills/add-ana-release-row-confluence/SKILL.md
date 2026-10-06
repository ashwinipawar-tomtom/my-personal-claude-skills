# add-ana-release-row-confluence

Watch the **#navigation-pipelines-alerts** Slack channel for `SdkVer Release (ANA)` success notifications (and the legacy `ANA release … success` shape) and add a row for each newly released ANA version to the matching release-line table on the [ANA Versions Tested](https://tomtom.atlassian.net/wiki/spaces/ANA/pages/1448476996/ANA+Versions+Tested) Confluence page.

The new row contains **only the version** — every other column is left empty for QA to fill in later (by hand, or via `add-testing-analysis-confluence` and `create-ana-rc-validation-ticket`).

This skill is **idempotent**: a version that already has a row is skipped. It is safe to run repeatedly and on a schedule.

## Prerequisites

- Atlassian MCP must be authenticated. If not, ask the user to run `/mcp` and select **"claude.ai Atlassian"**.
- Slack MCP must be authenticated. If not, ask the user to run `/mcp` and select **"claude.ai Slack"**.

## Inputs

All inputs are optional — with no arguments the skill scans recent channel history and adds every missing row.

| Input | Default | Notes |
|---|---|---|
| `window_hours` | `24` | Size of the rolling time window ending **now**. Enforced with a real Unix timestamp (Step 1) — **never** with a message count. |
| `version` | — | Force a specific version (e.g. `0.11.0-rc15`), skipping the Slack scan and the window check entirely. Only when the user names a version directly. |

---

## Step 1 — Read the Slack channel, bounded by a real timestamp

**Compute the window boundary first:**

```bash
python3 -c "import time; print(int(time.time()) - 24*3600)"
```

That value is `oldest_ts`. Use `window_hours` in place of `24` if the user overrode it.

Then call `slack_read_channel` with:
- `channel_id`: `C0700P68G10` (**#navigation-pipelines-alerts**)
- `oldest`: `{oldest_ts}` ← **required, this is what bounds the scan**
- `limit`: `100`
- `response_format`: `concise`

⚠️ **`limit` is not a time window.** This channel carries roughly 10–20 messages a day, so `limit: 100` alone reaches back well over a week and will surface long-since-released versions. `oldest` is the only thing that actually scopes the run. Never rely on `limit` to mean "recent", and never page backwards past `oldest_ts` with `cursor`.

**If the user supplied `version`, skip this step and Step 2 and go straight to Step 3 with that single version.**

---

## Step 2 — Extract released ANA versions

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

### 2b — Version shapes this skill handles

| Shape | Example | Action |
|---|---|---|
| `X.Y.Z-rcNN` | `0.11.0-rc14` | ✅ Handle |
| `X.Y.Z` | `0.9.5`, `0.10.2` | ✅ Handle |
| anything containing `-dev` | `0.12.0-dev177.59b4ab17` | ❌ Skip — mainline dev builds belong to the **Mainline Validation** tables, which this skill must never touch. Report as skipped. |

Deduplicate the resulting version list, and keep it in **chronological order (oldest first)** so rows are appended in release order.

### 2c — Re-check every match against the window (hard guard)

Each message carries its own timestamp. **Independently verify that every matched notification falls inside the window**, and discard any that does not — even if `slack_read_channel` returned it.

This is a deliberate second line of defence. The window is the whole point of the run: the page is assumed already up to date, so the job is only ever to catch **today's** releases. A version released days or weeks ago that has no row is *not* this skill's business — it was either deliberately skipped or handled some other way, and silently adding a row for it is a wrong, surprising edit. If such a version turns up, **report it and do not add it.**

---

## Step 3 — Derive the release line for each version

The **release line** is the first two dot-separated components of the version:

- `0.11.0-rc14` → `0.11`
- `0.9.5` → `0.9`
- `0.10.2` → `0.10`

This determines which section of the page the row belongs to.

---

## Step 4 — Fetch the Confluence page

Use `getConfluenceContent` with:
- `cloudId`: `tomtom.atlassian.net`
- `content_id`: `1448476996`
- `detail`: `full`
- `content_format`: `html`

Keep the returned **`snapshotToken`** — it is required for the update in Step 6.

This page returns `metadata.hasSpaceInstructions: false`, so **do not** call `getConfluenceSpace` for it.

If the HTML is too large to return inline it will be saved to a file. Read the whole file before editing — slice it by character range with a shell command (`python3`, `cut -c`, `dd`) rather than line-based reads, because the body is a single very long line.

Before authoring the edit, get the format guide once: call `execute` with `name=getContentFormatGuide`, `inputs={toolName: "updateConfluenceContent"}`.

---

## Step 5 — Locate the target table and check for an existing row

### 5a — Find the section

Release-line sections are **bold paragraphs**, not headings (the page has no heading outline). Their text varies in spacing and punctuation:

```
**0.7 Releases **
**0.8 Releases :  **
**0.9 Releases : **
**0.10 Releases : **
**0.11 Releases : **
**0.12 Releases :**
```

Match tolerantly: a paragraph whose text, with whitespace collapsed and trailing `:` stripped, equals `{release_line} Releases`.

**If no section exists for the release line: report it and stop for that version** (see Step 7). Do **not** create the section or invent page structure — a new release line needs the right heading and column set, which is the user's call.

### 5b — Find the last table in that section

A section may contain **more than one table** — the 0.11 section is split across two, because it grew long. The section runs from its bold paragraph up to the next section's bold paragraph.

**Always target the LAST table within the section.** That is the one currently being appended to.

The release-line tables have **8 columns**:

```
Release version | Ticket | Configuration | Full Regression(Includes Drive Test) / Sanity(Exploratory) |
Drive Test ? | APAC Tested ? | Go/ No-Go Recommendation | Comments
```

### 5c — Never touch these tables

| Table | Why |
|---|---|
| **Mainline Validation** tables (`ANA Version` / `Ticket` / … , 5–6 columns) | Mainline dev builds, tracked separately |
| The final `Releases :` table (`Release` / `NavSDK Mapping`) | A version-mapping reference table, not a test log |

Identify a release-line table by its first header cell reading **`Release version`** — the Mainline tables use **`ANA Version`** instead.

### 5d — Idempotency check

Search **the whole section** (all its tables, not just the last) for a row whose **Release version** cell already contains this exact version.

Compare on the version string only, ignoring bold markup, surrounding whitespace, and any trailing NavSDK version in parentheses — e.g. an existing `**0.11.0-rc12 **(2.6.0-rc11)` counts as a row for `0.11.0-rc12`.

**If a row already exists, skip this version** and report it as already present. Never add a duplicate row and never overwrite an existing row's other columns.

---

## Step 6 — Insert the row and update the page

Append a new `<tr>` as the **last row** of the table found in Step 5b:

- **Release version** cell: the version wrapped in `<strong>` (matching every other row on the page, e.g. `<strong>0.11.0-rc14</strong>`)
- **All 7 remaining cells: empty** (`<td><p /></td>` or the page's equivalent empty-cell shape — copy the shape from an existing blank cell, such as the `0.11.0-rc11` "Skipped" row's empty cells)

Do **not** add the NavSDK version in parentheses. The recent convention on this page is version-only (`**0.11.0-rc13**`, `**0.11.0-rc14**`, `**0.12.0-rc02**`), and the request is a row with just the version.

**Prefer a granular edit over replacing the body.** This page is ~200 KB of HTML in a single line; a full-body round-trip is fragile and unwieldy. Every node carries a `data-local-id`, so target the table's `<tbody>` directly:

- `cloudId`: `tomtom.atlassian.net`
- `contentId`: `1448476996`
- `snapshotToken`: from Step 4
- `edits`: `[{ "name": "appendNodeToEnd", "localId": "<the target tbody's data-local-id>", "value": "<the new <tr> HTML>" }]`
- `minorEdit`: `true`
- `versionMessage`: `Add row for ANA {version}` (or `Add rows for ANA {v1}, {v2}` when several)

Fall back to a full `body` replacement (`{ "format": "html", "value": "<full page HTML>" }`) only if a granular edit is rejected.

**Verify before writing:** run the same call with `dryRun: true`. It returns the resulting HTML (large — save and diff it with a script, don't eyeball it). Confirm the diff is exactly the intended row(s).

Note the server normalises HTML entities on round-trip (`'` ↔ `&#39;`), so compare **entity-normalised** text (`html.unescape`) or you will see spurious differences. The real check: `normalised(original)` with the new row inserted must equal `normalised(dryRun result)` exactly.

**To undo a row added in error:** `edits: [{ "name": "deleteNode", "localId": "<that row's data-local-id>" }]` removes exactly that `<tr>`. Verified working on this page.

**Batch multiple versions into a single update** when more than one row is missing, rather than one write per version.

**On a version conflict** (the page changed since Step 4 — this page is edited often, by people and by the other ANA skills): re-read the page to get a fresh `snapshotToken`, re-run the Step 5 checks (the row may have appeared in the meantime), and retry once. Never pass a stale token, and never force an overwrite.

---

## Step 7 — Report

```
✅ Added rows to ANA Versions Tested (v{new_page_version}):
   {version}  → {release_line} Releases table
   ...

⏭  Already present (no change): {version}, ...
⚠  No section for release line {release_line} — row NOT added for {version}.
   Create a "**{release_line} Releases : **" section with the standard 8-column table, then re-run.
🚫 Skipped (mainline dev build): {version}, ...
🕒 Outside the {window_hours}h window — NOT added: {version} (released {date}), ...
ℹ  Ignored "ANA Public release" notifications: {version}, ...

Page: https://tomtom.atlassian.net/wiki/spaces/ANA/pages/1448476996/ANA+Versions+Tested
```

Omit any line that has no entries. If nothing at all was added, say so plainly rather than implying an edit was made.

---

## Constraints

- The Slack channel is always `C0700P68G10` (**#navigation-pipelines-alerts**) — never ask for it.
- **Always bound the scan with the `oldest` timestamp computed in Step 1.** `limit` is a page size, not a time window; relying on it back-searches over a week of history. The page is assumed already up to date, so only releases inside the window are in scope.
- Never add a row for a version whose notification predates the window, even when that version genuinely has no row. Report it instead.
- The Confluence page is always `1448476996` — never ask for it.
- `cloudId` is always `tomtom.atlassian.net` — never ask for it.
- Match the `SdkVer Release (ANA)` success notification on `tomtom-internal/navapp-automotive`; accept the legacy `*ANA release {version} success*` only for builds before 2 Oct 2026.
- **Never match the `SdkVer Release (UXL)` twin** — same version, ~4 s earlier — nor a `:x:` failed run, a `go-sdk-android` release, or a `Promote to Public …` run. Do not blanket-ignore `:white_check_mark:` pipeline messages.
- New rows carry **the version only**; all other columns stay empty. Never fill in Ticket, Configuration, Go/No-Go or Comments — other skills and the user own those.
- Never modify an existing row, and never add a second row for a version that already has one.
- Never touch the **Mainline Validation** tables or the final `Releases :` / `NavSDK Mapping` table.
- Never create a release-line section that doesn't exist — report and stop for that version.
- Append to the **last** table of a section, since sections can be split across several tables.
- Always `dryRun` the update first and confirm the diff is only the intended row(s) before writing.
- Always pass the `snapshotToken` from the same read; on conflict, re-read and retry once rather than forcing.
- Skip any version containing `-dev`.
