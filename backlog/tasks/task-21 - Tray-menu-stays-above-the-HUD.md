---
id: TASK-21
title: Tray menu stays above the HUD
status: Done
assignee:
  - '@hud_dev'
created_date: '2026-10-31 08:35'
updated_date: '2026-10-31 08:37'
labels: []
dependencies: []
type: bug
ordinal: 21000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The tray right-click menu pops up behind the HUD when the HUD overlaps it: the HUD lifts itself on every refresh, above the open menu.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 While the tray menu is open, a HUD refresh does not raise the HUD above it
- [x] #2 After the menu closes, refreshes raise the HUD again as before
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Hud tracks the tray menu with <Map>/<Unmap> and skips root.lift() while it is open, so refreshes no longer cover it; lifting resumes after it closes. Verified with test_open_tray_menu_is_not_covered_by_a_refresh (Xvfb, real tk_popup/unpost); 118 OK; reviewed by agent_review.
<!-- SECTION:FINAL_SUMMARY:END -->
