---
id: TASK-18
title: 'README: install through an agent, STATUS prompt and config examples'
status: Done
assignee:
  - '@hud_dev'
created_date: '2026-10-31 07:38'
updated_date: '2026-10-31 07:39'
labels: []
dependencies: []
type: docs
ordinal: 18000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Before GitHub publication the README must show how to get the Done sections working and how to install. Recommended install: hand the repository to your own coding agent, which reviews it for safety, installs it for your environment and adapts the config. The README must also give an anonymized agent instruction that makes agents end replies with a STATUS line, and a complete config example matching it.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 README recommends installing by asking your coding agent to fetch the repository, review it for safety, install it for your environment and adapt the config, and keeps the manual uv install as an alternative
- [x] #2 README contains a generic, anonymized instruction snippet for agent instruction files that makes the agent end each reply with a STATUS line using DONE, DONE_FOLLOWUP, NEEDS_USER and WAITING
- [x] #3 README contains a config example matching that snippet (DONE transient, other values sticky) and explains why
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
README: recommended install via the user's own coding agent (review, install, autostart, adapt config) with the manual uv install as alternative; anonymized STATUS-line instruction snippet; matching config (DONE transient, default sticky) with rationale. Docs-only; agent_review declined the review gate for docs-only changes. python3 tests/run 88 OK.
<!-- SECTION:FINAL_SUMMARY:END -->
