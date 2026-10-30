---
id: TASK-2
title: 'HUD window, blocked rows and beep'
status: Done
assignee:
  - '@herdr_dev'
created_date: '2026-10-30 10:30'
updated_date: '2026-10-30 11:02'
labels: []
dependencies:
  - TASK-1
type: feature
ordinal: 2000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Always-on-top Tk window listing blocked agents, beeping on new blocks, hiding when empty. See docs/design.md sections 1 (sketch defects), 4, 5, 6.2, 6.6.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Window stays above other windows on Openbox, is on all desktops and does not take keyboard focus when it appears
- [x] #2 Rows show workspace · tab · agent; session name only when more than one session runs
- [x] #3 Beeps via paplay without blocking when a terminal_id newly enters blocked; at most one beep per poll; no beep for panes already blocked at HUD start
- [x] #4 A row is hidden and silent while its pane is focused and the X11 active window is that session's Herdr window; it reappears without a beep
- [x] #5 Window hides when nothing is listed and shows an error row when Herdr is unreachable
- [x] #6 Single instance via a lock in XDG_RUNTIME_DIR
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Override-redirect Tk window chosen (design.md section 4). Live checks: --demo window rendered above Chrome on the primary monitor (screenshot), active window and keyboard focus unchanged, not in _NET_CLIENT_LIST and no _NET_WM_DESKTOP; real poll mode ran 4 s; second instance exits 1; paplay of dialog-warning.oga exits 0. Viewed-pane rule queries X11 only when a blocked agent is focused.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Added logic.py (rows, beep baseline, viewed-pane hiding, error row after 3 failed polls), x11.py (UI client/session detection, parent walk, active window pid, primary monitor), app.py (override-redirect Tk HUD, paplay via Popen, flock single instance, --demo) and python3 -m herdr_blocked_hud. Verified with python3 tests/run (29 tests) and the live checks in notes.
<!-- SECTION:FINAL_SUMMARY:END -->
