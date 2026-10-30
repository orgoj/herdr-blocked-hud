---
id: TASK-12
title: HUD click must not reach the window below
status: Done
assignee:
  - '@hud_dev'
created_date: '2026-10-30 16:20'
updated_date: '2026-10-30 16:23'
labels: []
dependencies: []
type: bug
ordinal: 12000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
User report: when a click makes the HUD hide, the click also reaches the application behind it. The HUD acts on button press; the window can unmap before the release, X then drops the implicit grab and delivers the release to the window below.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Row click, close button and right-click dismiss act on button release, not press, and only when the pointer is still over the widget
- [x] #2 A headless test shows that a press alone triggers nothing and a release outside the widget triggers nothing
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Row click, close button and right-click dismiss now act on ButtonRelease over the widget, so a click that hides the HUD no longer falls through. Verified with the xvfb GUI test (press alone and release outside trigger nothing); real WM behaviour still to be confirmed in use. agent_review OK.
<!-- SECTION:FINAL_SUMMARY:END -->
