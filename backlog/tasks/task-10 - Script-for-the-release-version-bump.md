---
id: TASK-10
title: Script for the release version bump
status: Done
assignee:
  - '@hud_dev'
created_date: '2026-10-30 15:09'
updated_date: '2026-10-30 15:53'
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
- [x] #1 One repository script takes the new version and updates the version in pyproject.toml and the install tag in README.md consistently
- [x] #2 The script rejects a malformed version or one that is not newer than the current one, and changes no file in that case
- [x] #3 README and AGENTS.md document the generic release procedure with the script; no machine-local install in the repo
- [x] #4 Tests cover the version update and the rejection cases
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Stdlib script scripts/bump_version.py X.Y.Z: strict X.Y.Z, newer than pyproject version, each target matched exactly once, else exit nonzero with no writes. Tests in tests/test_bump.py on temp copies. AGENTS.md one line; drop the manual release line from README.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
User correction: the generic release procedure belongs in README and AGENTS.md; only the local install stays out of the repo.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Added bin/bump-version X.Y.Z (pyproject version + README install tag; rejects malformed or not-newer versions with no writes) and tests/test_bump.py; AGENTS.md documents the command, README dropped the manual release line. Verified with python3 tests/run (76 OK), a dry run on copies of the real files, and agent_review (OK).
<!-- SECTION:FINAL_SUMMARY:END -->
