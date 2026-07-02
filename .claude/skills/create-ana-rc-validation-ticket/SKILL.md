---
name: create-ana-rc-validation-ticket
description: Use when creating a Jira Epic for ANA RC release validation testing. Automates URL construction, NavApp fix ticket analysis (including RAC comment lookup), table generation, and Epic creation in the NAV project.
---

# Create ANA RC Validation Ticket

This skill automates the creation of a Jira Epic for ANA RC release validation testing. It constructs all required URLs from version numbers, fetches and analyzes NavApp fix tickets from the Jira release version, extracts use cases from RAC comments, and creates the Epic in the NAV project.

## Prerequisites

- Atlassian MCP must be authenticated. If not, ask the user to run `/mcp` and select **"claude.ai Atlassian"**.
- `gh` CLI must be authenticated with access to `tomtom-internal` GitHub repositories. If not, ask the user to run `gh auth login` in their terminal before starting.

## Inputs

Ask the user to provide the following before starting any steps:

| Input | Example | treat_as_first_rc? | Notes |
|---|---|---|---|
| `navapp_version` | `0.9.0-rc10` | — | The ANA RC version being validated |
| `treat_as_first_rc` | `yes` | Optional, default `no` | Set to `yes` to force first-RC behaviour (no diffs, no fixes table) — use when rc01 had a build issue and was never actually released |

`navsdk_version` is resolved automatically in Step 1a via the GitHub API — do not ask the user for it.

---

## Step 1 — Resolve NavApp version ID, fetch NavSDK version, derive previous versions, and construct all URLs

### 1a — Fetch `navsdk_version` from GitHub

Run the following command via the Bash tool (requires `gh` CLI to be authenticated):

```bash
gh api "/repos/tomtom-internal/navapp-automotive/contents/gradle/gosdk-libs.versions.toml?ref={navapp_version}" --jq '.content' | base64 -d
```

From the decoded content, extract the value of `gosdk` under the `[versions]` section. Example:

```toml
[versions]
gosdk = "2.4.0-rc09"
```

This value is `navsdk_version`. Store it for use in all subsequent steps. No user input is needed for this step.

If the command fails (tag not found, `gh` not authenticated), report the error and ask the user to provide `navsdk_version` manually.

### 1b — Fetch `navapp_jira_version_id` automatically

Use `searchJiraIssuesUsingJql` with `cloudId: tomtom.atlassian.net`:

```
project = NAV AND fixVersion = "ana/{navapp_version}" ORDER BY key ASC
```

with `maxResults: 1` and `fields: ["fixVersions"]`.

From the first result, read `fixVersions[0].id` — this is `navapp_jira_version_id`.

If the query returns 0 results, report the error to the user and ask them to provide `navapp_jira_version_id` manually from: `https://tomtom.atlassian.net/projects/NAV?selectedItem=com.atlassian.jira.jira-projects-plugin%3Arelease-page` (search for `ana/{navapp_version}`).

### 1c — Fetch `navsdk_jira_version_id` automatically

Use `searchJiraIssuesUsingJql` with `cloudId: tomtom.atlassian.net`:

```
project = GOSDK AND fixVersion = "navsdk-android/{navsdk_version}" ORDER BY key ASC
```

with `maxResults: 1` and `fields: ["fixVersions"]`.

From the first result, read `fixVersions[0].id` — this is `navsdk_jira_version_id`.

If the query returns 0 results, report the error to the user and ask them to provide `navsdk_jira_version_id` manually from: `https://tomtom.atlassian.net/projects/GOSDK?selectedItem=com.atlassian.jira.jira-projects-plugin%3Arelease-page` (search for `navsdk-android/{navsdk_version}`).

### 1d — Derive previous versions and construct all URLs

**If `navapp_version` ends with `rc01` OR the user provided `treat_as_first_rc = yes`:** this is the first RC — there is no previous RC to diff against. Set `is_first_rc = true`. Skip deriving `prev_navapp_version` and `prev_navsdk_version`. The diff URLs and NavApp fixes table will be omitted from the Epic description (see Step 5).

**Normal case (RC number > 01 and `treat_as_first_rc` not set to `yes`):** set `is_first_rc = false`. Set `is_final_release = false`. Parse the RC number, decrement by 1, and zero-pad to two digits.
- `0.9.0-rc10` → `prev_navapp_version = 0.9.0-rc09`
- `2.4.0-rc09` → `prev_navsdk_version = 2.4.0-rc08`

**If `navapp_version` has no RC suffix (it is a final release, e.g. `0.8.0`):** set `is_final_release = true`, `is_first_rc = false`. Find `prev_navapp_version` as the last RC tag of that same series using the Bash tool:

```bash
gh api "/repos/tomtom-internal/navapp-automotive/git/refs/tags" \
  --jq '[.[].ref | ltrimstr("refs/tags/")] | map(select(test("^{major}\\.{minor}\\.{patch}-rc[0-9]+$"))) | last'
```

Example: `0.8.0` → last RC tag is `0.8.0-rc23` → `prev_navapp_version = 0.8.0-rc23`. The fixes table in Step 2 will be built from the GitHub diff, not from all Jira fixVersion tickets.

**If `navsdk_version` has no RC suffix (it is a final release, e.g. `2.3.0`):** the previous version is the last RC of that same release series. Search using `searchJiraIssuesUsingJql` with:

```
project = GOSDK AND fixVersion ~ "navsdk-android/{major}.{minor}.{patch}-rc" ORDER BY fixVersion DESC
```

Pick the highest RC number from the results. Example: `2.3.0` → last RC is `2.3.0-rc13` → `prev_navsdk_version = 2.3.0-rc13`.

Construct the following URLs and store them for use in the description:

| Variable | URL pattern |
|---|---|
| `gosdk_url` | `https://artifactory.tomtomgroup.com/artifactory/automotive-maven-release/com/tomtom/automotive/app-gosdk/{navapp_version}/app-gosdk-{navapp_version}.apk` |
| `ana_url` | `https://artifactory.tomtomgroup.com/artifactory/automotive-maven-release/com/tomtom/automotive/app-ana/{navapp_version}/app-ana-{navapp_version}.apk` |
| `viltestapp_url` | `https://artifactory.tomtomgroup.com/artifactory/automotive-maven-release/com/tomtom/automotive/vilTestApp/{navapp_version}/vilTestApp-{navapp_version}.apk` |
| `navapp_diff_url` | `https://github.com/tomtom-internal/navapp-automotive/compare/{prev_navapp_version}...{navapp_version}` |
| `navsdk_diff_url` | `https://github.com/tomtom-internal/go-sdk-android/compare/{prev_navsdk_version}...{navsdk_version}` |
| `navapp_fixes_url` | `https://tomtom.atlassian.net/projects/NAV/versions/{navapp_jira_version_id}/tab/release-report-all-issues` |
| `navsdk_fixes_url` | `https://tomtom.atlassian.net/projects/GOSDK/versions/{navsdk_jira_version_id}/tab/release-report-all-issues` |
| `known_issues_url` | `https://tomtom.atlassian.net/jira/dashboards/37545` (always fixed) |
| `bd_scan_url` | `https://hub.tomtomgroup.com/api/projects/63b17d4d-b948-4b52-bab8-18d2fe780acc/versions?limit=100&offset=0` (always fixed) |

---

## Step 2 — Fetch NavApp fix tickets from the release version

**If `is_first_rc = true`:** skip Steps 2 and 3 entirely. Proceed directly to Step 4.

**If `is_final_release = true`:** do NOT fetch all fixVersion tickets. Instead, extract only the tickets introduced in the final cut using the GitHub compare diff via the Bash tool:

```bash
gh api "/repos/tomtom-internal/navapp-automotive/compare/{prev_navapp_version}...{navapp_version}" \
  --jq '[.commits[].commit.message]' \
  | grep -oP 'fix\(NAV-\d+\)' | grep -oP 'NAV-\d+' | sort -u
```

This extracts only commit messages following the conventional commit format `fix(NAV-XXXXX):`, ignoring merge commits, plain mentions, or non-fix references. Deduplicate the resulting ticket list. Proceed to Step 3 with only these tickets.

**Normal case (`is_final_release = false`):** use `searchJiraIssuesUsingJql` with `cloudId: tomtom.atlassian.net`:

```
project = NAV AND fixVersion = "ana/{navapp_version}" ORDER BY key ASC
```

Retrieve all fields including `summary`, `description`, `comment`, `status`, and `issuetype`. If there are more than 50 results, paginate with `startAt` until all tickets are fetched.

---

## Step 3 — Analyze each ticket for use cases (backport subtask → RAC comment fallback)

**Derive `release_branch_short`** from `navapp_version` by taking the first two version components:
- `0.10.0-rc04` → `release_branch_short = 0.10`
- `0.9.0-rc13` → `release_branch_short = 0.9`

For each ticket returned in Step 2:

1. Use `getJiraIssue` with `cloudId: tomtom.atlassian.net` and fields `["summary", "description", "subtasks", "comment"]`.

2. **Primary — backport subtask lookup:**
   - Check the `subtasks` array for a subtask whose summary contains both `Backport` (case-insensitive) AND `{release_branch_short}` (e.g. `0.10`). A summary like "Backport ... to release/0.10" or "Backport for 0.10 release" qualifies.
   - If a matching subtask is found, fetch it using `getJiraIssue` (fields `["summary", "description"]`) and read its full description.
   - In the subtask description, locate the **"Use cases"** section (look for a heading or label containing "Use case", "Use Cases", or "Use case to be tested"). Extract all content under that section as the use case text for the table.
   - If the subtask exists but has no "Use cases" section, **do not leave the cell blank** — proceed to step 3 (RAC comment fallback on the original ticket) before giving up.

3. **Fallback — RAC comment lookup (if no matching subtask was found, OR if a subtask was found but had no "Use cases" section):**
   - Read **every comment in full** on the original ticket — do not truncate. If the result is saved to a file, read the entire file before drawing conclusions.
   - Search ALL comments for a **Risk Assessment** comment by scanning for the keywords: **"Risk Assessment"**, **"use case"**, **"Verification checklist for QA"**, or **"special attention"**. Do **not** filter by author name — RAC comments may be posted by automated agents (e.g. "Product Requirements Guide") or bots.
   - Extract a concise use case description from the Risk Assessment comment (all use cases).
   - If no Risk Assessment comment is found, leave the use case cell **blank** — do not write "N/A" or infer use cases from the ticket summary.

4. Note any blocking issues, known failures, or special comments in the **Comments** column.

Build the NavApp fixes table:

| Ticket | Summary | Use case to be tested | Comments |
|---|---|---|---|
| NAV-XXXXX | Short summary of the fix | Use case from RAC comment | Any blockers or notes |

---

## Step 4 — Resolve Jira custom field IDs

Use `getJiraIssueTypeMetaWithFields` with:
- `cloudId`: `tomtom.atlassian.net`
- `projectKey`: `NAV`
- `issueTypeName`: `Epic`

Find and record the field IDs for:
- **Teams & Communities** — look for a field named "Teams & Communities" or similar
- **Team** — look for a field named "Team"
- **Products** — look for a field named "Products" or "Product"
- **Epic Name** — required for Epic issue type in Jira

---

## Step 4b — Check for an existing ticket (duplicate guard)

Before creating or previewing, search for a duplicate using `searchJiraIssuesUsingJql` with `cloudId: tomtom.atlassian.net`:

```
project = NAV AND issuetype = Epic AND summary = "ANA {navapp_version} validation"
```

- If **one or more results are returned**: stop immediately. Report to the user: "A validation ticket for this version already exists: {existing_issue_url}. Skipping creation." Do **not** proceed to Step 5.
- If **zero results are returned**: continue to Step 5.

---

## Step 5 — Create Epic in Jira

Use `createJiraIssue` with `cloudId: tomtom.atlassian.net` and the following fields:

- `projectKey`: `NAV`
- `issueTypeName`: `Epic`
- `summary`: `ANA RC {navapp_version} validation`
- `contentFormat`: `markdown`
- `parent`: `NAV-202198`
- `additional_fields`:
  - `priority`: `{"name": "High"}`
  - `customfield_10011`: `ANA {navapp_version} validation` (Epic Name)
  - `customfield_10215`: `[{"id": "12825"}]` (Teams & Communities — [PT] Automotive NavApp)
  - `customfield_10309`: `[{"id": "22304"}]` (Products — Automotive UI on NavSDK)
  - Note: `customfield_10001` (Team = NavApp: Quality Assurance, id `0adc78d9-0980-42bf-9183-957a2606133d-938`) must be set manually — the Jira Align team field format is not supported by the MCP tool.

**Description (markdown) — normal case (`is_first_rc = false`):**

All URLs must be written as markdown hyperlinks using `[label](url)` syntax — never as bare URLs. Use the following label conventions:
- APK files: use the filename as label (e.g. `[app-gosdk-{navapp_version}.apk](url)`)
- Diffs: use `{prev_version}...{version}` as label (e.g. `[0.9.0-rc10...0.9.0-rc11](url)`)
- Fix report pages: use `NAV versions/{id}` or `GOSDK versions/{id}` as label
- BD scan: use `BD scan link` as label
- Known issues: use `Known issues dashboard` as label

```
The testing should be performed from the RC Branch:
    1    ANA reference app : [app-gosdk-{navapp_version}.apk]({gosdk_url})
    2    NavSDK : {navsdk_version}
    3    ANA app : [app-ana-{navapp_version}.apk]({ana_url})
    4    VilTestApp : [vilTestApp-{navapp_version}.apk]({viltestapp_url})

Testing scope:
    1    Sanity test
    2    ANA + VIL
    3    Drive test

NavSDK combinations:
    1    Orbis + Daichi + online_first

BD scan : [BD scan link]({bd_scan_url}) - QA to connect to VPN and check for specific version, if we have any BD issues

New features/changes:
Change diff NavApp: [{prev_navapp_version}...{navapp_version}]({navapp_diff_url})
Change diff NavSDK: [{prev_navsdk_version}...{navsdk_version}]({navsdk_diff_url})

NavApp fixes : [NAV versions/{navapp_jira_version_id}]({navapp_fixes_url})
{navapp_fixes_table}

NavSDK fixes : [GOSDK versions/{navsdk_jira_version_id}]({navsdk_fixes_url})

Known issues : [Known issues dashboard]({known_issues_url})
```

**Description (markdown) — first RC case (`is_first_rc = true`):**

```
The testing should be performed from the RC Branch:
    1    ANA reference app : {gosdk_url}
    2    NavSDK : {navsdk_version}
    3    ANA app : {ana_url}
    4    VilTestApp : {viltestapp_url}

Testing scope:
    1    Regression Test
    2    ANA + VIL
    3    Drive test

NavSDK combinations:
    1    Orbis + Daichi + online_first

BD scan : [BD scan link]({bd_scan_url}) - QA to connect to VPN and check for specific version, if we have any BD issues

NavApp fixes : [NAV versions/{navapp_jira_version_id}]({navapp_fixes_url})

NavSDK fixes : [GOSDK versions/{navsdk_jira_version_id}]({navsdk_fixes_url})

Known issues : [Known issues dashboard]({known_issues_url})
```

After creating the Epic, output the created ticket URL to the user.

---

## Step 6 — Post Slack notification

Use `slack_send_message` to post to channel `C0AJ015923D` with the following message:

```
ANA {navapp_version} validation ticket created: {epic_url}
```

Where `{epic_url}` is the URL of the Jira Epic created in Step 5.

---

## Constraints

- Do not create the ticket until the NavApp fixes table (Step 3) is fully populated. If `is_first_rc = true`, this constraint does not apply — proceed directly to Step 4 after Step 1.
- Always zero-pad RC numbers to two digits (e.g. `rc09`, not `rc9`).
- The BD scan URL is always `https://hub.tomtomgroup.com/api/projects/63b17d4d-b948-4b52-bab8-18d2fe780acc/versions?limit=100&offset=0` — do not ask the user for it.
- The known issues dashboard URL is always `https://tomtom.atlassian.net/jira/dashboards/37545` — do not ask the user for it.
- `navapp_jira_version_id` is fetched automatically via the Jira REST API in Step 1a — do not ask the user for it unless the API lookup fails.
- `navsdk_version` is fetched automatically via the GitHub API in Step 1a — do not ask the user for it unless the API lookup fails.
- `navsdk_jira_version_id` is fetched automatically via the Jira REST API in Step 1c — do not ask the user for it unless the API lookup fails.
- If `getJiraIssueTypeMetaWithFields` fails to resolve a custom field ID, report the missing fields to the user and ask them to provide the field IDs manually before proceeding.
- The `Products` field is always `Automotive UI on NavSDK` (id: `22304`) — never use `ANA`.
- The `Parent` field is always `NAV-202198` — always set this on every Epic created by this skill.
- If `navsdk_version` is a final release (no `-rcXX` suffix), `prev_navsdk_version` must be resolved by finding the last RC of that release series (see Step 1c). Never ask the user for it unless the GOSDK JQL search returns no results.