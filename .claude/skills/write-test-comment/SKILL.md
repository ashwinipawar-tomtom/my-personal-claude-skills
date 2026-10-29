---
name: write-test-comment
description: >
  Adds a structured test-summary comment to a given ANA RC validation Epic in Jira NAV. Trigger:
  the user says something like "write my test comment" or "write my Test comment" and gives an
  Epic link or key. Pulls the build details (App/NavSDK version) straight from the Epic, adds a
  fixed Tested checklist (Sanity tests, Backported fixes, ANA scenario — "ANA + VIL scenario" for
  0.10 and older), queries every NAV
  bug the user personally reported against that RC's Affects Version and lists each with its
  Priority and Severity under "Issues Reported", and appends a blank "Go/No-Go Recommendation"
  line for the user to fill in by hand. Posts the comment directly on the Epic — no draft/confirm
  step, since the content is fully mechanical.
---

# write-test-comment

Post a structured test-summary comment on an **ANA RC validation Epic** in the Jira **NAV** project (the Epics created by the `create-ana-rc-validation-ticket` skill).

## Prerequisites

- Atlassian MCP must be authenticated. If not, ask the user to run `/mcp` and select **"claude.ai Atlassian"**.

## Inputs

| Input | Example | Notes |
|---|---|---|
| `epic_link` | `https://tomtom.atlassian.net/browse/NAV-205630` or `NAV-205630` | **Required.** The Epic to comment on. Ask for it if not given. |

There is no other required input — everything else is derived from the Epic itself or queried from Jira.

---

## Step 1 — Parse the Epic key

Accept either a full URL (`https://tomtom.atlassian.net/browse/NAV-XXXXXX`) or a bare key (`NAV-XXXXXX`). Extract the key.

---

## Step 2 — Fetch the Epic and extract build details

Use `getJiraIssue` with `cloudId: tomtom.atlassian.net`, `issueIdOrKey: {epic_key}`, fields `["summary", "description"]`.

Extract:

- **`navapp_version`** from the Epic's `summary` — it follows the pattern `ANA RC {version} validation` or `ANA {version} validation`. The version looks like `X.Y.Z-rcNN` or `X.Y.Z`.
- **`navsdk_version`** from the Epic's `description` — look for the line matching `NavSDK : {version}` (second line of the "testing should be performed from the RC Branch" block).

If either value cannot be parsed, tell the user which one failed and ask them to provide it manually — do not guess.

---

## Step 3 — Find issues the user reported against this version

Construct `affects_version = "ana/{navapp_version}"`.

Use `searchJiraIssuesUsingJql` with `cloudId: tomtom.atlassian.net`:

```
project = NAV AND issuetype = Bug AND affectedVersion = "ana/{navapp_version}" AND reporter = "712020:1c9e3001-3ab7-410a-b27f-56bdaef3627a" ORDER BY key ASC
```

with `fields: ["summary", "priority", "customfield_10140"]`.

For each returned issue, record:

- `key`
- `summary` → `fields.summary`
- `priority` → `fields.priority.name` (Blocker/Urgent/High/Medium/Low)
- `severity` → `fields.customfield_10140.value` (Critical (A) / Major (B) / Minor (C) / Safety / Blocks Feature Rollout). If unset, use `Not set`.

**Never substitute one field for the other** — `priority` and `customfield_10140` (Severity) are always reported separately, exactly as stored on the ticket.

If the query returns zero results, the Issues Reported section will read `No issues reported`.

---

## Step 3a — Handle NAV bugs converted to another project (e.g. GOSDK)

A NAV bug can get moved/converted to a different project by triage (e.g. a NavSDK-side crash filed in NAV gets moved to GOSDK). When that happens:

- Fetching the **original NAV key** (e.g. `NAV-205763`) auto-redirects and returns the issue under its **new key and project** (e.g. `GOSDK-220568`) — Jira preserves this redirect permanently.
- The move typically **clears the Affects Version field**, so the moved issue drops out of the Step 3 JQL (which is scoped to `project = NAV`) even though it's still a real bug against this RC.

If the user names a specific ticket (old or new key) that should be reflected but isn't showing up in the Step 3 results, or a ticket turns out to have moved when fetched:

1. Fetch it directly with `getJiraIssue` — note whichever key/project it now resolves to.
2. Work out the correct "Affects Version" value **for its current project's naming scheme**, using the same RC build this comment is for:
   - NAV project → `ana/{navapp_version}`
   - GOSDK project → `navsdk-android/{navsdk_version}`
   - (Other projects: ask the user for the right version-naming convention rather than guessing.)
3. Resolve that version's id (e.g. via `searchJiraIssuesUsingJql` against a ticket already carrying that fixVersion, same technique used elsewhere) and, if the issue's `versions` field is empty, set it with `editJiraIssue` (`fields: {"versions": [{"id": "<resolved_id>"}]}`) so the ticket stays discoverable for this RC going forward.
4. Include it in the Issues Reported list like any other issue (Step 4), using its **current** key and priority/severity.

This is a repair-on-mention step, not a blind background scan — only act on tickets the user points out or that you already know were filed against this RC (e.g. earlier in the same conversation), since there's no reliable way to discover a silently-moved, version-cleared ticket purely from the Step 3 JQL.

---

## Step 4 — Build the comment

Compose the comment body (markdown) in this exact shape:

```
Build Details : App {navapp_version} | NavSDK {navsdk_version}

Tested :
1. Sanity tests : Done
2. Backported fixes : Done
3. {ana_line} : Done

Issues Reported :
{one bullet per issue, in the form below — or the literal line "No issues reported" if Step 3 found none}

Go/No-Go Recommendation : 
```

Each issue bullet:

```
* [{key}](https://tomtom.atlassian.net/browse/{key}) — {summary} — Priority: {priority}, Severity: {severity}
```

Use a markdown `[text](url)` link with the **summary included as plain text** in the bullet itself — do not rely on a bare URL to auto-unfurl into a smart-link card. A bare URL posted via `addCommentToJiraIssue` is **not** clickable and does **not** unfurl (confirmed: it renders as inert plain text), so the summary must be written out explicitly, and the key must be wrapped in a real markdown link to be clickable at all.

`{ana_line}` is `ANA scenario` when the release line of `navapp_version` is **0.11 or later** (the major is above 0, or the major is 0 and the minor is 11 or more), and `ANA + VIL scenario` for 0.10 and older. The user asked for this on 2026-10-29, to match the Epic description, which drops the VilTestApp from 0.11 on.

The three "Tested" lines are always exactly this fixed wording and order — do not reword, reorder, or add/remove items regardless of what was actually tested. If the user later says a specific item was *not* done, that's a manual edit to the posted comment, not something this skill infers.

Leave the text immediately after `Go/No-Go Recommendation :` empty — do not write a recommendation, a placeholder, or an emoji there. That line is for the user to fill in by hand.

---

## Step 5 — Post the comment

Use `addCommentToJiraIssue` with `cloudId: tomtom.atlassian.net`, `issueIdOrKey: {epic_key}`, `commentBody: {the composed body}`, `contentFormat: markdown`.

Post immediately once Steps 2–4 succeed — **do not show a draft and wait for confirmation first.** The content is fully mechanical (build details pulled from the Epic, a fixed checklist, a queried issue list, and a blank line), so there is nothing for the user to approve before posting.

---

## Step 5a — Link every mentioned issue under "while testing discovered"

For every issue that ended up in the Issues Reported list (Step 3 results plus any Step 3a repairs), create a Jira issue link from the Epic to that issue using `createIssueLink`:

- `cloudId`: `tomtom.atlassian.net`
- `type`: `Bonfire testing` (this is the link type whose inward phrase is "while testing discovered")
- `inwardIssue`: the bug's key (e.g. `NAV-205766`, `GOSDK-220568`)
- `outwardIssue`: the Epic key

This makes the bug show up on the Epic under **Linked items → while testing discovered**. Do this for every issue in the list, using each issue's *current* key (post Step 3a repair if applicable). Skip this step entirely if Issues Reported is empty. Don't ask for confirmation — link immediately, same as posting the comment.

---

## Step 6 — Output

Report back:

```
✅ Test comment added to {epic_key}: {epic_url}
🔗 Linked under "while testing discovered": {key1}, {key2}, ...   (omit this line if Issues Reported was empty)
```

Then show the exact comment text that was posted, so the user can see it and go fill in the Go/No-Go line (or edit anything else) directly in Jira.

---

## Constraints

- `cloudId` is always `tomtom.atlassian.net` — never ask for it.
- The reporter filter is always accountId `712020:1c9e3001-3ab7-410a-b27f-56bdaef3627a` (Ashwini Manohar Pawar) — never ask for it, and never widen the query to other reporters.
- Severity must come from `customfield_10140` on each issue, priority from the standard `priority` field — never conflate the two or infer one from the other.
- Do not add a confirmation/review step before posting — post directly, then show the user what was posted.
- Do not fill in the Go/No-Go Recommendation line — always leave it blank.
- Do not invent or reorder the three Tested checklist items.
- If `navapp_version` or `navsdk_version` can't be parsed from the Epic, stop and ask the user for the missing value instead of guessing.
- If a ticket the user names turns out to have moved to another project, follow Step 3a: fetch it by whichever key resolves, repair its Affects Version using that project's own naming convention (never `ana/...` on a non-NAV ticket), and still include it in Issues Reported under its current key.
