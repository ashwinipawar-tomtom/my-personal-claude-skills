# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This repository contains Claude Code skills for ANA release QA automation on `tomtom.atlassian.net`.

Skills are invoked by name in Claude Code.

## Personal AI Skills

- `create-ana-rc-validation-ticket` — Create a Jira Epic for ANA RC release validation. Fetches NavApp fix tickets, analyzes RAC comments, constructs all URLs from version numbers, and creates the Epic in the NAV project. Skill file: `/Users/ashwini.pawar/myproject/.claude/skills/create-ana-rc-validation-ticket/SKILL.md`
- `add-testing-analysis-confluence` — Reads all comments on a given Jira Epic, generates a short severity-based testing analysis narrative, and updates the Comments column of the matching row in the ANA Versions Tested Confluence page. Skill file: `/Users/ashwini.pawar/myproject/.claude/skills/add-testing-analysis-confluence/SKILL.md`
- `install-gosdk` — Downloads a GoSDK APK by version from Artifactory, does a fresh uninstall+install on the connected tablet, and launches the app. Skill file: `/Users/ashwini.pawar/myproject/.claude/skills/install-gosdk/SKILL.md`
- `update-alpha-beta-confluence` — Reads both Alpha and Beta Slack notification channels, fetches Jira summaries to tag APAC (JP/KR) and ROW features, removes features already in Test Debt, and publishes the updated ANA Alpha/Beta features Confluence page. Skill file: `/Users/ashwini.pawar/myproject/.claude/skills/update-alpha-beta-confluence/SKILL.md`
- `link-navsdk-validation-ticket` — Given an ANA RC version, finds its row on the ANA Versions Tested Confluence page, reads the NavSDK version in parentheses, looks up the matching intake validation ticket on the NavSDK releases overview Confluence page, and links the two Jira issues as "Contains". Requires an explicit ANA version input — no batch mode. Skill file: `/Users/ashwini.pawar/myproject/.claude/skills/link-navsdk-validation-ticket/SKILL.md`
- `write-test-comment` — Given an ANA RC validation Epic link, posts a structured test-summary comment: build details pulled from the Epic, a fixed Tested checklist (Sanity tests, Backported fixes, ANA + VIL scenario), an Issues Reported list (NAV bugs the user reported against that RC's Affects Version, with Priority and Severity), and a blank Go/No-Go Recommendation line. Posts directly, no confirmation step. Skill file: `/Users/ashwini.pawar/myproject/.claude/skills/write-test-comment/SKILL.md`
- `mainline-week-bug-summary` — Given a calendar week number (and optional year), finds the `[ANA] Mainline validation - week NN/YYYY` Epic to derive that week's date range, then reports all NAV bugs the QA team (Ashwini, Joy Salem, Max Bogers) raised against the mainline dev build (`ana/0.14.0-dev`) in that window — grouped by reporter with a severity breakdown. Read-only: no Jira or Confluence writes. Skill file: `/Users/ashwini.pawar/myproject/.claude/skills/mainline-week-bug-summary/SKILL.md`
- `add-ana-release-row-confluence` — Scans the #navigation-pipelines-alerts Slack channel for `ANA release <version> success` notifications and adds a version-only row to the matching release-line table on the ANA Versions Tested Confluence page. Idempotent, batches multiple versions, and never touches the Mainline Validation tables. **Manual use only:** its scheduled routine "ANA release rows to Confluence" (`trig_01KFLsXpbDCXzzQdCz2GdbrZ`) was disabled on 2026-10-09. That routine didn't read this skill file and only matched the legacy release message, and `setup-new-ana-rc` already adds or fills in the row for each new release. Skill file: `/Users/ashwini.pawar/myproject/.claude/skills/add-ana-release-row-confluence/SKILL.md`
- `setup-new-ana-rc` — Full setup for a newly released ANA RC, intended to run unattended on a schedule. Detects new releases from the #navigation-pipelines-alerts Slack channel, invokes `create-ana-rc-validation-ticket` for the Epic, creates 2 child Test Executions (desk sanity → Ashwini, APAC sanity → Joy Salem; never a Drive test ticket; none for rc01, and none while the previous RC's Epic is still Open/Funnel, in which case it creates the Epic only), and adds or enriches the version's row on the ANA Versions Tested Confluence page with the build date/time from the Slack notification plus an owner mention in each testing column, each followed by that person's child ticket as a live-status Jira macro (for rc01, existing children matched by assignee). Also adds the version's row (build time, backported-fix count) to the ANA RC Details page (2551710615). Idempotent at every step. Skill file: `/Users/ashwini.pawar/myproject/.claude/skills/setup-new-ana-rc/SKILL.md`
- `refresh-ana-validation-board` — Regenerates the ANA Release Validation Board Confluence page (2561638669), the ANA counterpart of the NavSDK board: per-RC NavSDK version, the three testing streams (Sanity desk / APAC / Drive test) with their tickets and statuses, and the bugs found. Sources the RC validation Epics under NAV-202198, their children, bug counts from the ANA Versions Tested Comments column, and build times from the Slack release notification. Owns the page and rewrites it in full; reports stale Epic statuses and severity drift rather than fixing them. Skill file: `/Users/ashwini.pawar/myproject/.claude/skills/refresh-ana-validation-board/SKILL.md`

## Skill Architecture

The skill (`create-ana-rc-validation-ticket/SKILL.md`) is a declarative step-by-step procedure that Claude executes using the Atlassian MCP tools. The five steps run sequentially with strict data dependencies:

1. **URL construction** — derives previous RC versions (decrement + zero-pad) and builds all artifact/diff/Jira URLs
2. **Jira ticket fetch** — JQL query against NAV project `fixVersion`, paginating if >50 results
3. **RAC comment analysis** — fetches each ticket's full comments, extracts use-case text from RAC/QA comments, builds the fixes table
4. **Custom field resolution** — discovers dynamic Jira field IDs for Epic-specific fields (Teams & Communities, Team, Products, Epic Name)
5. **Epic creation** — creates the Jira Epic with the pre-formatted description and table; outputs the created ticket URL

**Hard dependencies:** Atlassian MCP must be authenticated before the skill runs. The user needs VPN for the BD scan URL to be reachable.

## Required Inputs

The skill requires only one user-provided value before starting:

| Input | Description |
|---|---|
| `navapp_version` | ANA RC version string (e.g. `0.9.0-rc10`) |

`navsdk_version` is auto-fetched in Step 1a from `gradle/gosdk-libs.versions.toml` at the NavApp git tag via the GitHub API.
`navapp_jira_version_id` and `navsdk_jira_version_id` are resolved automatically in Step 1 via the Jira REST API.

## Key Constraints

- RC numbers must always be zero-padded to two digits (`rc09`, not `rc9`)
- The known issues dashboard URL is always `https://tomtom.atlassian.net/jira/dashboards/37545` — never ask the user for it
- `navapp_jira_version_id` is auto-fetched — never ask the user for it unless the API lookup fails
- `navsdk_jira_version_id` is auto-fetched — never ask the user for it unless the API lookup fails
- Do not create the Epic until Step 3 (fixes table) is fully populated
- If `getJiraIssueTypeMetaWithFields` cannot resolve a custom field ID, report it and ask the user for the field ID manually

## Modifying the Skill

All skill logic lives in `create-ana-rc-validation-ticket/SKILL.md`. To change behavior — step order, description template, field values, URL patterns — edit that file directly. There is no compilation or build step.
