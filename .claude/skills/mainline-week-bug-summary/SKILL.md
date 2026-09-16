# Mainline Week Bug Summary

This skill reports all Bugs the QA team raised against the **mainline/master build** (not an RC) during a given calendar week — grouped by reporter, with a severity breakdown. It mirrors `add-testing-analysis-confluence` in output style, but is scoped by week number against the `[ANA] Mainline validation - week NN/YYYY` Epic instead of a single RC validation Epic. It also posts a combined build-version breakdown table as a comment on that Epic (style modeled on [this example](https://tomtom.atlassian.net/browse/NAV-204837?focusedCommentId=12453001)).

## Prerequisites

- Atlassian MCP must be authenticated. If not, ask the user to run `/mcp` and select **"claude.ai Atlassian"**.

## Inputs

Ask the user to provide the following before starting:

| Input | Example | Notes |
|---|---|---|
| `week_number` | `35` | Required. The calendar week to report on (unpadded, e.g. `35` not `035`). |
| `year` | `2026` | Optional. Defaults to the current year if not given. |

---

## Step 1 — Find the Mainline validation Epic for that week

Use `searchJiraIssuesUsingJql` with `cloudId: tomtom.atlassian.net`:

```
project = NAV AND issuetype = Epic AND summary = "[ANA] Mainline validation - week {week_number}/{year}"
```

with `fields: ["summary", "created"]`.

- If **zero results**: search more loosely with `summary ~ "Mainline validation - week"` ORDER BY created DESC, show the user the nearest weeks that do exist, and ask them to confirm the exact week/year. Do not guess.
- If found, record its `created` timestamp as `start_date` and its key as `epic_key`.

Note: only the plain `[ANA] Mainline validation - week NN/YYYY` **Epic** counts as the week marker — ignore same-week variants like `New Feature Testing - [ANA] Mainline validation - week NN/YYYY` or `APAC [ANA] Mainline validation - week NN/YYYY` (these are Task-type sub-trackers for the same week, not the week boundary itself).

---

## Step 2 — Determine the end boundary of the week

Search for the **next** week's Epic the same way:

```
project = NAV AND issuetype = Epic AND summary = "[ANA] Mainline validation - week {week_number + 1}/{year}"
```

- If found, its `created` timestamp is `end_date` (exclusive upper bound).
- If not found and `week_number` is 52 or 53 (year boundary), also try `week 1/{year + 1}` before giving up.
- If still not found, this is the most recent tracked week — use the current time as `end_date`.

---

## Step 3 — Fetch bugs reported by the QA team in that window

The QA team reporters are fixed — do not ask the user for these, and do not widen the query to other reporters:

| Name | accountId |
|---|---|
| Ashwini Manohar Pawar | `712020:1c9e3001-3ab7-410a-b27f-56bdaef3627a` |
| Joy Salem | `70121:06132251-8fb4-4c83-b36e-ed3991d620a6` |
| Max Bogers | `70121:c8bb703b-bf46-419e-9e84-4b9f89bd5d55` |

Use `searchJiraIssuesUsingJql` with `cloudId: tomtom.atlassian.net`:

```
project = NAV AND issuetype = Bug AND reporter IN ("712020:1c9e3001-3ab7-410a-b27f-56bdaef3627a", "70121:06132251-8fb4-4c83-b36e-ed3991d620a6", "70121:c8bb703b-bf46-419e-9e84-4b9f89bd5d55") AND affectedVersion = "ana/0.12.0-dev" AND created >= "{start_date}" AND created < "{end_date}" ORDER BY reporter ASC, created ASC
```

with `fields: ["summary", "reporter", "priority", "customfield_10140", "status", "environment", "description"]`.

**Note on the affects-version bucket:** `ana/0.12.0-dev` is the current mainline dev bucket (a generic Jira version, distinct from RC-specific versions like `ana/0.11.0-rc09` or specific dev-numbered builds like `ana/0.12.0-dev259.ba0ee7dd`). When mainline moves past the 0.12.x series, update this to the new bucket (e.g. `ana/0.13.0-dev`) — check by searching `project = NAV AND affectedVersion ~ "ana/0."` sorted by version if the query above returns suspiciously few results for a recent week.

For each returned issue, record:

- `key`, `summary`
- `reporter` → `fields.reporter.displayName`
- `priority` → `fields.priority.name` (Blocker/Urgent/High/Medium/Low)
- `severity` → `fields.customfield_10140.value` (Critical (A) / Major (B) / Minor (C) / Safety / Blocks Feature Rollout). If unset, use `Not set`.
- `status` → `fields.status.name`

**Never substitute one field for the other** — `priority` and `customfield_10140` (Severity) are always reported separately, exactly as stored on the ticket.

If this query returns zero results, do not stop yet — proceed to Step 3b before concluding there's nothing to report this week (a GOSDK-only week is possible).

---

## Step 3b — Sweep GOSDK for bugs from the same reporters

A bug can be filed **directly against GOSDK** (not moved there from NAV) with no Affects Version set at all — e.g. a NavSDK-side lane-rendering defect a tester files straight in GOSDK. Step 3's `affectedVersion` filter would silently miss issues like this even if it were pointed at GOSDK, because there's nothing to match on. So this sweep matches purely on **reporter + created-date window**, with no version filter, then flags whichever results lack a recognizable version tag so the gap is visible instead of silent.

Use `searchJiraIssuesUsingJql` with `cloudId: tomtom.atlassian.net`:

```
project = GOSDK AND issuetype = Bug AND reporter IN ("712020:1c9e3001-3ab7-410a-b27f-56bdaef3627a", "70121:06132251-8fb4-4c83-b36e-ed3991d620a6", "70121:c8bb703b-bf46-419e-9e84-4b9f89bd5d55") AND created >= "{start_date}" AND created < "{end_date}" ORDER BY reporter ASC, created ASC
```

with `fields: ["summary", "reporter", "priority", "customfield_10140", "status", "environment", "description", "versions"]`.

For each returned issue, record the same fields as Step 3 (`key`, `summary`, `reporter`, `priority`, `severity`, `status`), then run it through Step 3a's App Version extraction below the same as any NAV issue.

Additionally check `versions` (Affects Version):

- If **empty**, flag the issue for the Step 5 narrative only (not the Step 6 table) with a trailing `⚠ no Affects Version set` — this is a discoverability gap on the ticket itself worth surfacing so the user can ask for it to be tagged.
- If **non-empty but not a mainline-dev tag** (e.g. `navsdk-android/2.6.0-rc09` instead of the current mainline bucket), still include the issue as-is — don't filter it out, and don't claim it as a mainline-dev bug in the narrative, just list it normally.

Merge these GOSDK issues into the same per-reporter groups as the Step 3 NAV issues (append after each reporter's NAV issues — GOSDK bugs from this sweep are rare enough that exact chronological interleaving doesn't matter). They flow into Step 4, 5, and 6 exactly like NAV issues, using their own `GOSDK-XXXXX` key and the same `https://tomtom.atlassian.net/browse/{key}` URL pattern.

---

## Step 3a — Extract the App Version per ticket

If Step 3 and Step 3b **together** returned zero issues, report: "No bugs reported by the QA team (checked both NAV and GOSDK) during week {week_number}/{year}." and stop — skip the rest of this step and everything after.

Apply this to every issue collected across Step 3 and Step 3b. The specific dev-numbered build a ticket was found on (e.g. `0.12.0-dev075.d09db400`) is **not** the same as the generic `affectedVersion` bucket (`ana/0.12.0-dev`) used to filter in Step 3 — it has to be pulled per-ticket from one of two places, in this order, using a version-pattern regex rather than fixed string-splitting (the `environment` field's format varies by reporter — e.g. `ANA/0.12.0-dev075.d09db400\n\nGoogle Automotive (Volvo)\n...` for one tester, `* App: 0.12.0-dev254.825da6a8 | NavSDK: ...` for another):

1. **Primary — the standard Jira `environment` field.** If non-empty, search it for the pattern `\d+\.\d+\.\d+(?:-(?:dev|rc)\d+(?:\.[0-9a-zA-Z]+)?)?` and take the first match (e.g. matches `0.12.0-dev075.d09db400` inside `ANA/0.12.0-dev075.d09db400`, and `0.12.0-dev254.825da6a8` inside `* App: 0.12.0-dev254.825da6a8 | NavSDK: 2.7.0-dev359...` — the regex's greediness plus the leftmost-match rule naturally picks the App version over the later NavSDK version).
2. **Fallback — the description's Test Env block** (used by tickets created via the `create-nav-bug` skill, which leaves `environment` empty). Search the `description` for a `NavApp Version:` line (logcat-style Test Env) or an `App Version:` line (inline-style Test Env) and apply the same version-pattern regex to that line's value.
3. If neither source yields a match, leave the App Version cell **blank** — do not guess or fall back to the generic `ana/0.12.0-dev` bucket string.

Record this as `app_version` for each issue.

---

## Step 4 — Group and summarize

Group the combined Step 3 + Step 3b issues by reporter (in the fixed order: Ashwini Manohar Pawar, Joy Salem, Max Bogers — omit a reporter's section entirely if they have zero bugs in this window), NAV and GOSDK issues mixed together within each reporter's group.

Also compute a combined severity breakdown across all reporters and both projects:

- Count issues per severity value (Critical (A) / Major (B) / Minor (C) / Safety / Blocks Feature Rollout).
- Any issue with `Not set` severity goes under "Also found" at the end, unlabeled.
- Never use the Jira `priority` field as a stand-in for severity in this count.

---

## Step 5 — Output to the user

**Do not write anything back to Jira or Confluence.** Present the results directly in this format:

```
Mainline Week: {week_number}/{year}
Epic: {epic_key} ({epic_url})
Date range: {start_date} → {end_date}

--- Bugs Reported by QA ---

### Ashwini Manohar Pawar (N)
* [NAV-XXXXX](https://tomtom.atlassian.net/browse/NAV-XXXXX) — {summary} — Priority: {priority}, Severity: {severity}, Status: {status}
* [GOSDK-XXXXX](https://tomtom.atlassian.net/browse/GOSDK-XXXXX) — {summary} — Priority: {priority}, Severity: {severity}, Status: {status} ⚠ no Affects Version set
...

### Joy Salem (N)
...

### Max Bogers (N)
...

--- Severity Summary ---
N Critical/Blocker: [NAV-X](url), ...
N Major: [NAV-X](url), ...
N Minor: [NAV-X](url), ...
N Blocks Feature Rollout: [NAV-X](url), ...
Also found (no severity set): [NAV-X](url), ...
```

- The `⚠ no Affects Version set` suffix (Step 3b) appears only on GOSDK issues missing it — never add it to a NAV issue or a GOSDK issue that does have a version tagged.
- Omit any severity line with a count of zero.
- If Step 3 and Step 3b together returned zero issues, skip straight to reporting "No bugs reported..." — omit both the per-reporter and severity sections, and skip Step 6 entirely (nothing to post).

---

## Step 6 — Post a build-version breakdown table as a comment on the Epic

Skip this step if Step 3 and Step 3b together returned zero issues.

Post one **combined** table covering all reporters and both projects (not split per reporter, not split by project) as a comment on `epic_key` (the same Epic found in Step 1), in this exact shape — modeled on [this example](https://tomtom.atlassian.net/browse/NAV-204837?focusedCommentId=12453001):

```
**Bugs reported by QA this week (Week {week_number}, {start_date formatted as "Mon D"} - {end_date formatted as "Mon D"}) - ANA/0.12.0-dev builds only:**

| Ticket | App Version | Severity | Priority | Summary |
| --- | --- | --- | --- | --- |
| [NAV-XXXXX](https://tomtom.atlassian.net/browse/NAV-XXXXX) | {app_version} | {severity} | {priority} | {summary} |
| [GOSDK-XXXXX](https://tomtom.atlassian.net/browse/GOSDK-XXXXX) | {app_version} | {severity} | {priority} | {summary} |
...one row per issue, ordered by reporter then created (Step 3's NAV issues, then that reporter's Step 3b GOSDK issues)...

**N Critical:** [NAV-X](url), ... | **N Major:** [NAV-X](url), ... | **N Minor:** [NAV-X](url), ... | **N Blocks Feature Rollout:** [NAV-X](url), ...
```

- Leave the App Version cell blank (not "N/A", not the generic bucket name) for any issue where Step 3a found no value.
- Do **not** add the `⚠ no Affects Version set` marker to this table — that flag is for the Step 5 narrative only, to keep this table's shape identical to the reference example.
- Omit a severity group from the final summary line entirely if its count is zero — same rule as Step 5.
- Use `addCommentToJiraIssue` with `cloudId: tomtom.atlassian.net`, `issueIdOrKey: {epic_key}`, `contentFormat: markdown`.
- Post directly once the table is built — do not show a draft and wait for confirmation first, since the content is fully mechanical (derived entirely from Steps 3–4).
- After posting, tell the user: `✅ Build-version table posted to {epic_key}: {epic_url}`.

---

## Constraints

- `cloudId` is always `tomtom.atlassian.net` — never ask for it.
- The reporter list is fixed to the three QA accountIds above — never ask for it, and never widen or narrow the query to other reporters, in either Step 3 (NAV) or Step 3b (GOSDK).
- Severity must come from `customfield_10140` on each issue, priority from the standard `priority` field — never conflate the two or infer one from the other.
- The only write this skill performs is the single `addCommentToJiraIssue` call in Step 6, posting to the week's own Mainline validation Epic — never call `updateConfluencePage`, never comment on any other ticket, and never post more than once per run.
- If the week's Epic can't be found, stop and ask the user to confirm the week/year instead of guessing a date range.
- Do not hardcode a specific dev-numbered build (e.g. `ana/0.12.0-dev259.ba0ee7dd`) in the Step 3 JQL filter — always use the generic mainline dev bucket (`ana/0.12.0-dev`) there, updating the bucket name as mainline advances past its current minor version. The per-ticket specific dev build belongs only in the App Version column (Step 3a), never in the filter.
- Never fall back to the generic `ana/0.12.0-dev` bucket string as a per-ticket App Version value — if Step 3a finds nothing, leave the cell blank.
- Step 3b deliberately has **no** `affectedVersion` filter — do not add one. Its entire purpose is to catch bugs that would be missed by a version filter (missing or non-standard Affects Version), so filtering on version there would defeat it.
- Do not silently drop a Step 3b issue just because its Affects Version is missing or doesn't match the mainline-dev convention — include it and flag it (per Step 3b's rules) rather than excluding it.
