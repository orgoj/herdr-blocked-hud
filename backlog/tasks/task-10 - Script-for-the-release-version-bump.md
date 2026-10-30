---
id: TASK-10
title: Script for the release version bump
status: To Do
assignee: []
created_date: '2026-10-30 15:09'
labels: []
dependencies: []
type: chore
ordinal: 10000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Releases 0.1.1-0.1.4 were bumped by hand with sed in pyproject.toml and in the README install tag, then committed and tagged. The user wants a script in the repository for the version bump.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 One repository script takes the new version and updates the version in pyproject.toml and the install tag in README.md consistently
- [ ] #2 The script rejects a malformed version or one that is not newer than the current one, and changes no file in that case
- [ ] #3 README documents the release procedure with the script
- [ ] #4 Tests cover the version update and the rejection cases
<!-- AC:END -->
