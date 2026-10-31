---
id: TASK-16
title: Drag the HUD to a new position
status: Done
assignee:
  - '@hud_dev'
created_date: '2026-10-31 07:23'
updated_date: '2026-10-31 07:25'
labels: []
dependencies: []
type: feature
ordinal: 16000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The HUD window is override-redirect, so Openbox does not manage it and its move binding (Win+Left drag) never reaches it; the user cannot move the overlay. Dragging inside the HUD moves it instead, keeping override-redirect (always on top, every desktop, never focused). Saving the position across runs is out of scope.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Dragging the HUD background or a section header with the left button moves the window with the pointer
- [x] #2 A press and release on a row or control button without moving still acts as a click; a drag that starts there does not trigger it
- [x] #3 The dragged position stays across refreshes and height changes for the life of the process; the edge of the configured corner stays put when the height changes
- [x] #4 The window stays override-redirect and on top
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Left-button drag anywhere in the HUD moves the override-redirect window (root-level bindings); a drag suppresses the row/button release action, a press moving < 4 px stays a click; the offset from the configured corner is kept in memory and applied on every render. Verified with new Xvfb tests test_drag_moves_the_hud_and_keeps_the_position and test_dragged_bottom_corner_keeps_its_bottom_edge; full suite 86 OK.
<!-- SECTION:FINAL_SUMMARY:END -->
