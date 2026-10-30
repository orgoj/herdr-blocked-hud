---
id: TASK-2
title: 'HUD window, blocked rows and beep'
status: To Do
assignee: []
created_date: '2026-10-30 10:30'
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
- [ ] #1 Window stays above other windows on Openbox, is on all desktops and does not take keyboard focus when it appears
- [ ] #2 Rows show workspace · tab · agent; session name only when more than one session runs
- [ ] #3 Beeps via paplay without blocking when a terminal_id newly enters blocked; at most one beep per poll; no beep for panes already blocked at HUD start
- [ ] #4 A row is hidden and silent while its pane is focused and the X11 active window is that session's Herdr window; it reappears without a beep
- [ ] #5 Window hides when nothing is listed and shows an error row when Herdr is unreachable
- [ ] #6 Single instance via a lock in XDG_RUNTIME_DIR
<!-- AC:END -->
