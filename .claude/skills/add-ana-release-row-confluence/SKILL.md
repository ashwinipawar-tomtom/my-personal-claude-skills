# add-ana-release-row-confluence

Watch the **#gosdk-pipelines-alerts** Slack channel for `ANA release … success` notifications and add a row for each newly released ANA version to the matching release-line table on the [ANA Versions Tested](https://tomtom.atlassian.net/wiki/spaces/ANA/pages/1448476996/ANA+Versions+Tested) Confluence page.

The new row contains **only the version** — every other column is left empty for QA to fill in later (by hand, or via `add-testing-analysis-confluence` and `create-ana-rc-validation-ticket`).

This skill is **idempotent**: a version that already has a row is skipped. It is safe to run repeatedly and on a schedule.

## Prerequisites

- Atlassian MCP must be authenticated. If not, ask the user to run `/mcp` and select **"claude.ai Atlassian"**.
- Slack MCP must be authenticated. If not, ask the user to run `/mcp` and select **"claude.ai Slack"**.

## Inputs

All inputs are optional — with no arguments the skill scans recent channel history and adds every missing row.

| Input | Default | Notes |
|---|---|---|
| `lookback` | `100 messages` | How far back to scan the channel. Accepts a message count (`200`) or a period (`7d`, `48h`). Paginate with the `cursor` from `slack_read_channel` until the window is covered. |
| `version` | — | Force a specific version (e.g. `0.11.0-rc15`), skipping the Slack scan entirely. Use when the user names a version directly. |

---

## Step 1 — Read the Slack channel

Use `slack_read_channel` with:
- `channel_id`: `C0700P68G10` (**#gosdk-pipelines-alerts**)
- `limit`: `100`
- `response_format`: `concise`

Paginate with `cursor` until the `lookback` window is covered.

**If the user supplied `version`, skip this step and Step 2 and go straight to Step 3 with that single version.**

---

## Step 2 — Extract released ANA versions

Match **only** messages of this exact shape (the bot is `ACME Notifier`):

```
*ANA release {version} success*
```

`{version}` looks like `0.11.0-rc14`, `0.9.5`, or `0.10.2`.

### 2a — Notifications that must NOT match

The channel carries three similar notifications. Only the first one counts:

| Notification | Action |
|---|---|
| `*ANA release {version} success*` | ✅ Add a row |
| `*ANA Public release {version} success*` | ❌ **Ignore** — a promotion of an already-tested build, not a new build. Report it under "Ignored" in Step 7 so the user can act on it if they want. |
| `*UXL release {version} success*` | ❌ Ignore silently — different product (UX Library), not tracked on this page. |

`ANA Public release` contains the substring `ANA release`-adjacent wording, so match on the **full** pattern with `Public` explicitly excluded — do not use a loose `contains("ANA release")` test.

Also ignore the `:white_check_mark:` / `:x:` / `:gear:` / `:github-pr-merged:` pipeline and intake-PR notifications entirely — those are `go-sdk-android` / `navapp-automotive` build events, not ANA releases.

### 2b — Version shapes this skill handles

| Shape | Example | Action |
|---|---|---|
| `X.Y.Z-rcNN` | `0.11.0-rc14` | ✅ Handle |
| `X.Y.Z` | `0.9.5`, `0.10.2` | ✅ Handle |
| anything containing `-dev` | `0.12.0-dev177.59b4ab17` | ❌ Skip — mainline dev builds belong to the **Mainline Validation** tables, which this skill must never touch. Report as skipped. |

Deduplicate the resulting version list, and keep it in **chronological order (oldest first)** so rows are appended in release order.

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

Then call `updateConfluenceContent` with:
- `cloudId`: `tomtom.atlassian.net`
- `contentId`: `1448476996`
- `snapshotToken`: from Step 4
- `body`: `{ "format": "html", "value": "<the full updated page HTML>" }`
- `minorEdit`: `true`
- `versionMessage`: `Add row for ANA {version}` (or `Add rows for ANA {v1}, {v2}` when several)

**Verify before writing:** run the same call once with `dryRun: true` and confirm the returned HTML differs from the original by exactly the intended row(s) — nothing else changed. Only then write for real.

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
ℹ  Ignored "ANA Public release" notifications: {version}, ...

Page: https://tomtom.atlassian.net/wiki/spaces/ANA/pages/1448476996/ANA+Versions+Tested
```

Omit any line that has no entries. If nothing at all was added, say so plainly rather than implying an edit was made.

---

## Constraints

- The Slack channel is always `C0700P68G10` (**#gosdk-pipelines-alerts**) — never ask for it.
- The Confluence page is always `1448476996` — never ask for it.
- `cloudId` is always `tomtom.atlassian.net` — never ask for it.
- Match **only** `*ANA release {version} success*`. `*ANA Public release …*` and `*UXL release …*` must never add a row.
- New rows carry **the version only**; all other columns stay empty. Never fill in Ticket, Configuration, Go/No-Go or Comments — other skills and the user own those.
- Never modify an existing row, and never add a second row for a version that already has one.
- Never touch the **Mainline Validation** tables or the final `Releases :` / `NavSDK Mapping` table.
- Never create a release-line section that doesn't exist — report and stop for that version.
- Append to the **last** table of a section, since sections can be split across several tables.
- Always `dryRun` the update first and confirm the diff is only the intended row(s) before writing.
- Always pass the `snapshotToken` from the same read; on conflict, re-read and retry once rather than forcing.
- Skip any version containing `-dev`.
