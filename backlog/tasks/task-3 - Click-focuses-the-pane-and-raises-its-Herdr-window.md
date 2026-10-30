---
id: TASK-3
title: Click focuses the pane and raises its Herdr window
status: Done
assignee:
  - '@herdr_dev'
created_date: '2026-10-30 10:30'
updated_date: '2026-10-30 11:31'
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
- [x] #1 Click runs herdr --session <name> agent focus <pane_id>
- [x] #2 Host window found by walking the session's Herdr UI client process parents to a window pid; fallback by configurable WM_CLASS; never by window title
- [x] #3 With several matching windows the first match is raised
- [x] #4 When agent focus fails nothing is focused or raised and the HUD re-polls immediately
- [x] #5 Unit tests cover client/session matching and window selection over process and window fixtures
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Live: host window of the default session resolved by parent walk to 0x04200003 (wezterm-gui --class herdr); wmctrl activation of the already active window ok; agent focus on a missing pane exits 1 (agent_not_found) and nothing is raised. A successful agent focus was not run live because it moves the user's Herdr view; covered by unit tests and the verified --session flag placement (herdr --session default agent get). WM_CLASS is a focus_agent parameter (default herdr.herdr); TASK-5 exposes it in the config file.

Review fix (agent_review): WM_CLASS fallback only when every local UI client belongs to the requested session (two sessions with one class raised the wrong window); UI-client detection parses Herdr global options so 'herdr --session x agent …' CLI processes and --machine commands are not clients, 'herdr session attach x' is, and --remote clients belong to no local session. Regression tests added.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Added focus.py (herdr --session <name> agent focus, then raise), window listing/selection/activation in x11.py (wmctrl -lpx, parent walk, exact WM_CLASS fallback, no title matching), Poller.poll_now and click wiring on a worker thread that always re-polls. Verified with python3 tests/run (38 tests) and the live checks in notes.
<!-- SECTION:FINAL_SUMMARY:END -->
