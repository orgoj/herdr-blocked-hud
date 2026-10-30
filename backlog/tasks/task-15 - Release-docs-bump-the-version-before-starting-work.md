---
id: TASK-15
title: 'Release docs: bump the version before starting work'
status: Done
assignee:
  - '@hud_dev'
created_date: '2026-10-30 17:04'
updated_date: '2026-10-30 17:04'
labels: []
dependencies: []
type: chore
ordinal: 15000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
User decision: the version is bumped before the work starts, so a build run from the checkout already carries the new version and is never confused with the installed release.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 README and AGENTS.md describe the release procedure with the bump first, then the work, tests, commit and tag
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
README and AGENTS.md now put bin/bump-version before the work. Docs only; diff checked.
<!-- SECTION:FINAL_SUMMARY:END -->
