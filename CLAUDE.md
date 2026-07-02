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
