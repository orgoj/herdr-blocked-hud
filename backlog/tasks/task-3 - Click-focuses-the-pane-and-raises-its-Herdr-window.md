---
id: TASK-3
title: Click focuses the pane and raises its Herdr window
status: To Do
assignee: []
created_date: '2026-10-30 10:30'
labels: []
dependencies:
  - TASK-1
type: feature
ordinal: 3000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Click runs agent focus in the row's session, then raises that session's Herdr host window on X11. See docs/design.md sections 3, 6.1, 6.4, 6.7.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Click runs herdr --session <name> agent focus <pane_id>
- [ ] #2 Host window found by walking the session's Herdr UI client process parents to a window pid; fallback by configurable WM_CLASS; never by window title
- [ ] #3 With several matching windows the first match is raised
- [ ] #4 When agent focus fails nothing is focused or raised and the HUD re-polls immediately
- [ ] #5 Unit tests cover client/session matching and window selection over process and window fixtures
<!-- AC:END -->
