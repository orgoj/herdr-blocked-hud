---
id: TASK-14
title: Quit and restart buttons in the HUD
status: Done
assignee:
  - '@hud_dev'
created_date: '2026-10-30 16:40'
updated_date: '2026-10-30 16:49'
labels: []
dependencies: []
type: feature
ordinal: 14000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
User request: a close button that ends the HUD, and before it a restart button, so a newly installed version starts with one click.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 While the HUD is shown, its top line has a restart button (↻) followed by a quit button (×), acting on button release like the row buttons
- [x] #2 Quit ends the HUD with exit status 0
- [x] #3 Restart replaces the process with the same command and arguments (sys.executable plus the original argv), so the newly installed version starts; the single-instance lock is released by the exec; an exec failure is reported and the HUD exits 1
- [x] #4 Both glyphs render with DejaVu Sans, which has them; headless tests cover the buttons and the restart command; README describes them
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Top line has ↻ (restart: exec of sys.executable with the original argv after the main loop) and × (quit, exit 0) in DejaVu Sans, acting on release; exec failure reported with exit 1. Verified: tests OK plain and under xvfb; subprocess test proves same argv and lock release across exec; agent_review OK.
<!-- SECTION:FINAL_SUMMARY:END -->
