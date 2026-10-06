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

Pre-existing issues re-observed on a build go on their own line, **not into the new-issue counts**.

**Split the cell before counting anything.** Several rounds append a clause like `Already reported, still present in rc05 — 1 Major: NAV-206998` or `Already reported, observed on this build — 1 Major: … | 1 Minor: …`. A regex that sums every `N Major` in the cell silently inflates the round — verified on 0.12.0-rc05 (reported 7 Major instead of 6) and 0.11.0-rc16 (3 Major, 3 Minor instead of 2 and 2).

Split on `(?i)already reported`, count severities in the **first** part only, and summarise the second as a separate `+ N pre-existing` rather than merging it:

```python
parts = re.split(r'(?i)already reported', comments, maxsplit=1)
fresh, prior = parts[0], (parts[1] if len(parts) > 1 else '')
```

---

## Step 4 — Build times from Slack

Only needed for the pulse table. For each release in the pulse, find its release notification.

**Two formats, both still live. Accept either at any date:**

| Posted by | Notification to match |
|---|---|
| the newest release line (0.13.0-rc01 onward, from 2 Oct 2026) | `:white_check_mark: *tomtom-internal/navapp-automotive {version}*: SdkVer Release (ANA) … successful` |
| older release branches, still after 2 Oct | `*ANA release {version} success*` (legacy) |

Do **not** split on the date. On 6 October 2026, `0.10.3`, `0.11.1` and `0.12.0-rc06` all came as legacy messages, while `0.13.0-rc02` came as `SdkVer Release (ANA)`. A date cut-off would have left three pulse rows without a build time. If a version appears in both formats, use the earlier one.

Match on repo `tomtom-internal/navapp-automotive` **plus** `SdkVer Release (ANA)` **plus** success. **Never** the `SdkVer Release (UXL)` twin (same version, ~4 s earlier), a `:x:` failed run, a `go-sdk-android` release, or a `Promote to Public …` run.

**Read the channel directly — do not use `slack_search_public`.** Verified broken on 2026-10-05: given `filters: {in: "<#C0700P68G10>", after: "2026-09-24"}` it ignored both the channel and the date and returned messages from **#ana-release-notification in 2025**. It also found nothing for a version that is definitely in the channel.

Use `slack_read_channel`, bounded by real timestamps:

- `channel_id`: `C0700P68G10` (**#navigation-pipelines-alerts**, renamed from #gosdk-pipelines-alerts on 2026-10-06; the ID is unchanged)
- `oldest` / `latest`: Unix timestamps spanning the window you need
- `limit`: `100`, `response_format`: `concise` (the rendered time is in each line; `detailed` is only needed when you want the raw `ts`)

Compute the bounds rather than guessing:

```bash
python3 -c "
import datetime, zoneinfo
tz = zoneinfo.ZoneInfo('Europe/Amsterdam')
for d in ['2026-09-26','2026-10-06']:
    y,m,dd = map(int, d.split('-'))
    print(d, int(datetime.datetime(y,m,dd,tzinfo=tz).timestamp()))
"
```

Releases older than the first window need a second read further back — the pulse usually spans two to three weeks, and the channel goes quiet at weekends, so a single 10-day window often does not reach the oldest pulse row.

Convert each `ts` to **Europe/Amsterdam** — never raw UTC:

```bash
python3 -c "
import sys, datetime, zoneinfo
dt = datetime.datetime.fromtimestamp(float(sys.argv[1]), zoneinfo.ZoneInfo('Europe/Amsterdam'))
print(dt.strftime('%d %b %Y, %-I:%M %p'))
" {ts}
```

If a release has **neither** notification, write `—` and say so in the caveats. Do **not** substitute the GitHub tag or release-publication time — that is a different event again, and mixing it in makes the column meaningless.

⚠️ **The column is not comparable across the two formats.** The legacy event fires 2–5 hours *after* the `SdkVer Release (ANA)` pipeline, so a time from the new notification sits earlier in the day than a legacy one for the same stage. That holds for historical rows and for older-branch releases posted today. Note it in the caveats; never retro-fill or "correct" an older row.

---

## Step 5 — Open-criticals check

### 5a — Collecting the Critical keys

Rounds do not phrase this consistently. A regex expecting only `N Critical: …` **will miss real criticals** — verified on 0.11.0-rc04. Handle all of these:

| Phrasing seen | Example |
|---|---|
| `N Critical:` | `1 Critical: NAV-203186` |
| `N Critical :` (space before colon) | `2 Critical : GOSDK-214776, NAV-202312` |
| lower case | `1 critical : NAV-206307` |
| with the severity letter | `1 Critical (A): NAV-209428` |
| **key first, label in parentheses** | `NAV-205381 (Critical issues exists on this build)` |

Use **two passes** over each Comments cell:

1. **Labelled groups** — `(?i)(\d+)\s*critical[^:]{0,12}:\s*(.*?)(?=\d+\s*(?:major|minor)\b|$)`, then take every ticket key out of the captured group.
2. **Inline mentions** — any ticket key within ~80 characters *before* a parenthesised or trailing occurrence of `critical`, e.g. `(?i)((?:NAV|GOSDK|NGSD|NDSIMP|SEARCHPU|IM|ONEAPP)-\d+)[^|\n]{0,80}?\(\s*critical`.

Union both passes and de-duplicate. Keys struck through on the source page (`~~KEY~~`) still count — the round recorded them.

**Sanity-check the result:** the count of Critical keys found should be at least the sum of the `N` values in the labelled groups. If it is lower, a phrasing variant was missed — report it rather than publishing a silently short list.

### 5b — Query their current status

Query the collected keys:

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
5. **Now in work & recently finished** — the pulse: **every round that is Open or In Progress** (the Epic is not Done, or any child is not Done), **plus the single most recently finished round** (the newest build whose Epic and children are all Done). No other finished rounds; the user asked for exactly this on 2026-10-06. Newest build first, with a one-line intro: `Every round still Open or In Progress, plus the most recently finished one.` Columns: Release · NavSDK · Sanity · APAC · Drive test · Build appeared · Bugs found (summarised as counts only).
6. **By release line** — one `h4` and table per line, newest line first, newest RC first within each. Columns: ANA release · NavSDK · Sanity (desk) · APAC · Drive test · Bugs found (by severity, with keys).

**Release cell, in both tables:** the version in bold, then the Epic key as a visible link on its own line, so the key can be read without hovering:

```html
<p><strong>{label}</strong><br>Epic: <a href="https://tomtom.atlassian.net/browse/{epic_key}">{epic_key}</a></p>
```

A round with no Epic reads `<strong>{label}</strong><br>(no Epic)`. Don't put the link on the version text alone. The user asked for the Epic to be visible on every row.
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

## Running it on a schedule

Scheduled as the cloud routine **ANA Release Validation Board refresh** (`trig_01BNdiCHi2bohfNdFFa4Err8`), **three times every weekday**: `0 7,11,15 * * 1-5` UTC. In summer (CEST) that is 09:00, 13:00 and 17:00 Amsterdam, as requested on 2026-10-06. Cron is UTC-only, so after the clock change on 25 Oct 2026 these runs land at 08:00, 12:00 and 16:00 Amsterdam. Shift the cron to `0 8,12,16 * * 1-5` for winter, and back again on 28 Mar 2027. Model `claude-opus-5`; Atlassian + Slack connectors.

The routine checks this repository out as its session source and **reads this file**, so editing it changes the scheduled run as well as the local `/refresh-ana-validation-board` command. (It previously carried an inlined copy of the procedure, because the Claude GitHub App was installed only on the `tomtom-internal` org; it is now installed on the `ashwinipawar-tomtom` account too, so the clone works and the copy is gone.)

---

## Constraints

- The board page is always `2561638669`; ANA Versions Tested is always `1448476996`; `cloudId` is always `tomtom.atlassian.net`; the Slack channel is always `C0700P68G10`. Never ask for any of them.
- Validation Epics are always the children of **NAV-202198**.
- Filter out non-ANA Epics that the fuzzy `summary ~` match returns.
- Classify children **APAC → Drive test → Sanity**, in that order.
- Bug counts come from the **ANA Versions Tested Comments column**, never from a reporter-scoped JQL — the page records all projects and all reporters, which a NAV-only query misses.
- Reproduce each round's **stated** counts even when they disagree with the keys listed; never silently recount.
- Severity comes from the round's record; the ticket's current `customfield_10140` is only used for the open-criticals check and the drift note. Never use Jira **Priority** as severity.
- Build times come **only** from the release notification: `SdkVer Release (ANA)` or the legacy `*ANA release … success*`, whichever the version posted, at any date (older branches still post the legacy one). Render them in Europe/Amsterdam. Never substitute a GitHub tag or release-publication time, and never the `SdkVer Release (UXL)` twin.
- Get those notifications with a timestamp-bounded `slack_read_channel`. **Never `slack_search_public`** — it ignores the `in:` and `after:` filters and returns the wrong channel and year (Step 4).
- Split each Comments cell on `already reported` before counting severities; pre-existing issues are reported separately and never added to the round's new-issue counts (Step 3a).
- Full-body replacement is correct for this page and only this page.
- Always `dryRun` before writing, and pass the `snapshotToken` from the same read; on conflict re-read and retry once rather than forcing.
- Report stale Epic statuses and severity drift — never "fix" them in Jira from this skill.
