---
name: create-nav-bug
description: >
  Creates a Bug issue in the Jira NAV (Navigation) project using TomTom's standard bug template.
  Use this skill whenever the user wants to file, log, report, or create a bug, defect, or issue
  in the NAV space — even if they just say "log a bug", "file an issue", "create a ticket", or
  simply describe a problem they encountered in plain language. The user only needs to explain
  what went wrong in their own words (plus paste their DebugInfo logs); the skill writes the
  structured summary, description, expected/actual outcomes, and reproduce steps automatically.
---

# create-nav-bug

Create a Bug in the Jira **NAV** project from the user's plain-language description of the problem.

## Your role

The user will describe the bug in natural language — they will NOT fill in a structured form.
Your job is to:
1. Ask only for what you genuinely cannot infer (DebugInfo logs, test case coverage, Epic key)
2. Draft the full structured bug ticket yourself from their description
3. Show the drafted content to the user for a quick review/edit before creating
4. Create the ticket

## Fixed field values (always set these — no need to ask the user)

| Jira field | Field ID | Value | Option ID |
|---|---|---|---|
| Issue Type | `issuetype` | Bug | `10100` |
| Project | `project` | NAV | `10120` |
| Reporter | `reporter` | ashwini.pawar@tomtom.com | accountId `712020:1c9e3001-3ab7-410a-b27f-56bdaef3627a` |
| Teams & Communities | `customfield_10215` | [PT] Automotive NavApp | `{"id": "12825"}` |
| Products | `customfield_10309` | ANA | `{"id": "44512"}` |
| Customer | `customfield_10250` | Automotive NavApp | `{"id": "16965"}` |
| Found by | `customfield_10107` | Internal - Product Team | `{"id": "10920"}` |
| Severity | `customfield_10140` | Ask user (Major/Critical/Minor/Safety) | Major (B) → `{"id": "12400"}` |

**Do NOT set the `Team` field (`customfield_10001`).**

---

## Step 1 — Understand the bug from the user's words

Read the user's natural-language description carefully. Extract or infer:
- What feature/component is broken
- What the user was trying to do
- What went wrong (the observation)
- What should have happened instead
- Approximate reproduction steps (even if implied, not explicitly listed)
- Whether the task could be completed despite the bug

If the description is ambiguous on any critical point, ask one clarifying question before continuing. Don't ask for things you can write yourself.

Always ask for:
- **DebugInfo log lines OR build info block** — either the raw `DebugInfo:` lines from logcat, or the inline build summary from the crash description. Both are accepted:
  - *Logcat format*:
    ```
    2026-06-09 13:05:11.366 +0200 22842 22842 I DebugInfo: App Version: 0.10.0-rc02
    2026-06-09 13:05:11.366 +0200 22842 22842 I DebugInfo: NavApp Version: 0.10.0-rc02
    2026-06-09 13:05:11.366 +0200 22842 22842 I DebugInfo: NavSdk Version: 2.5.0-rc02
    ...
    ```
  - *Inline build info format* (common in crash reports):
    ```
    App version: 0.8.1 (release) | NavSDK: 2.3.0
    Branch: release/0.8 | Commit: d181bbc4cecdbd512b1c76ab6dd1e17e56af4dff
    Build date: Tue Jun 16 12:09:53 CEST 2026
    ```
  Either is sufficient to populate Test Env and extract the app version.
- **Stack trace** *(for crash bugs)* — paste the full stack trace if available.
- **Bug covered in a test case?** — Yes or No. If Yes, the test case ID/link.
- **Priority** — Blocker / Urgent / High / Medium / Low. Default: **Medium**.
- **Severity** — Critical (A) / Major (B) / Minor (C) / Safety. Default: **Major (B)**.
- **Epic key** *(optional)* — if the bug should be linked to an Epic (e.g. the current RC validation Epic).

---

## Step 2 — Draft the bug content

Using the user's description and your understanding of ANA/NavApp, write:

**Summary**: A concise, specific one-line title. Use the pattern `<Feature/component>: <what is broken>`.
- Good: `"Favourites: Map marker not shown after adding a new favourite location"`
- Bad: `"Bug with favourites"`

**Description** — follow this exact template:

```
**Problem description/ Observation:** <what the user observed, written as a clear factual statement>
< screenshots should be attached under this section >

**Expected outcome:** <what should have happened>

**Actual outcome:** <what actually happened, distinct from expected>

**Reproduce steps:**
1. <first step>
2. <second step>
...
(Steps must be concise and reproducible — describe how to trigger the bug, not just what the user did)

[ONLY include this section if the bug is a crash / exception — omit entirely otherwise]
**Occurrences:**
| # | Timestamp | PID |
|---|-----------|-----|
| 1 | <timestamp> | <pid> |
...

**Stack trace:**
```
<paste stack trace here>
```
[END crash-only section]

**Is it possible to complete what you wanted to do?** <Yes / No / Partially — infer from description>

**Bug covered in a test case:** <Yes, <test_case_id_and_name>  OR  No>

**Test Env:**
<paste the raw DebugInfo block OR inline build info here, as a code block>

**Logs:**
(Attach log files manually after ticket creation)
```

Show the drafted summary and description to the user and ask: "Does this look right? Any changes before I create the ticket?"

---

## Step 3 — Extract version and resolve Jira version ID

Parse the build info to find the app version. Two formats are accepted:

- *Logcat DebugInfo*: look for `NavApp Version:` → e.g. `NavApp Version: 0.10.0-rc02` → use `0.10.0-rc02`
- *Inline build info*: look for `App version:` → e.g. `App version: 0.8.1 (release)` → strip `(release)` / `(debug)` suffix → use `0.8.1`

Also extract **Branch** and **Commit** from the inline build info if present; include them in the Test Env block.

Construct the **affects-version name**: `ana/<version>` → e.g. `ana/0.10.0-rc02` or `ana/0.8.1`

Resolve the version ID via the Atlassian MCP fetch tool:
```
GET https://api.atlassian.com/ex/jira/1cca41ed-de92-4455-812e-a4a463fc61a9/rest/api/3/project/10120/versions
```

Find the entry where `name == "ana/<NavApp Version>"` and note its `id`.
If no match is found, warn the user and proceed without setting `versions`.

---

## Step 4 — Resolve priority

| User says | Jira priority name | Jira ID |
|---|---|---|
| blocker | Blocker | `10000` |
| urgent | Urgent | `10001` |
| critical / high | High | `10002` |
| major / medium / (default) | Medium | `10003` |
| minor / low | Low | `10004` |

Use `"priority": { "name": "<name>" }` in the API call — the name is resolved server-side.

---

## Step 4b — Resolve severity

Ask the user for severity if not provided. Default: **Major (B)**.

| User says | Jira value | Option ID |
|---|---|---|
| critical / A | Critical (A) | `12398` |
| major / B / (default) | Major (B) | `12400` |
| minor / C | Minor (C) | `12402` |
| safety | Safety | `12404` |
| blocks feature rollout | Blocks Feature Rollout | `12394` |

---

## Step 5 — Print summary and wait for confirmation

Before creating anything, print a full summary of the ticket to the user in this format:

```
📋 Ready to create the following bug in NAV:

Summary:      <summary>
Priority:     <priority>
Affects Ver:  <ana/X.Y.Z-rcNN>
Reporter:     Ashwini Manohar Pawar
Teams & Communities: [PT] Automotive NavApp
Products:     ANA
Customer:     Automotive NavApp
Found by:     Internal - Product Team

--- Description ---
<full description text>
-------------------
```

Then ask: **"Type 'create it' to proceed, or tell me what to change."**

Wait for the user to explicitly confirm before doing anything. Do not create the ticket without this confirmation.

---

## Step 6 — Create the Jira Bug

Once the user says "create it" (or equivalent), call `createJiraIssue` with all fields:

```json
{
  "cloudId": "tomtom.atlassian.net",
  "projectKey": "NAV",
  "issueType": "Bug",
  "summary": "<drafted summary>",
  "description": "<ADF description from Step 2>",
  "priority": { "name": "<priority>" },
  "reporter": { "accountId": "712020:1c9e3001-3ab7-410a-b27f-56bdaef3627a" },
  "versions": [{ "id": "<affects_version_id>" }],
  "customfield_10215": [{ "id": "12825" }],
  "customfield_10309": [{ "id": "44512" }],
  "customfield_10250": [{ "id": "16965" }],
  "customfield_10107": { "id": "10920" },
  "customfield_10140": { "id": "<severity_option_id>" }
}
```


---

## Step 7 — Output

```
✅ Bug created: https://tomtom.atlassian.net/browse/<NEW_KEY>
```

Remind the user:
> Screenshots and log files need to be attached manually — open the link above and use the paperclip icon.
