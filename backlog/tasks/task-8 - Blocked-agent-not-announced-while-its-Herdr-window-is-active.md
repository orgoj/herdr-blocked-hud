---
id: TASK-8
title: Blocked rows are never hidden for the viewed pane
status: Done
assignee:
  - '@herdr_dev'
created_date: '2026-10-30 13:58'
updated_date: '2026-10-30 14:11'
labels: []
dependencies: []
type: bug
ordinal: 8000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
User report on v0.1.2: an agent was blocked (red in Herdr) but the HUD showed nothing and did not beep. The row appeared only while the user made a region screenshot, then disappeared again while Herdr still showed blocked. Known cause candidate: design decision 6 (docs/design.md) hides and silences a blocked row while its pane is focused (on screen in the active workspace and tab, verified in Herdr src/app/creation.rs pane_info) and the X11 active window is that session's Herdr host window; the screenshot tool took the active window, so the row showed. Suggested direction: confirm with the user that the blocked pane was the visible one, then decide whether viewed blocked rows should still beep, stay listed, or be hidden only under a stricter rule. Needs analysis before implementation.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A blocked pane is listed and beeps on becoming blocked regardless of Herdr pane focus and the active X11 window
- [x] #2 The active-window query and viewed-session code are removed; xdotool is no longer a requirement
- [x] #3 README and docs/design.md decision 6 describe the new behavior
- [x] #4 Unit tests cover a focused blocked pane being listed and beeping
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
User decision: the looking-at rule must not apply to blocked rows; done needs none either because Herdr clears done when the pane is focused. So the rule is removed completely, with its X11 active-window query (xdotool).

Review fix (agent_review): docs/spec.md and the design.md plugin comparison no longer say the HUD uses xdotool.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Removed the looking-at rule: HudState lists and beeps every newly blocked pane; viewed_for, x11.active_window_pid and x11.viewed_sessions are gone, xdotool dropped from README requirements; README and design decision 6 updated. Verified: tests/run 67 OK (viewed tests replaced by test_focused_pane_is_listed_and_beeps); --demo smoke on Python 3.14 + Tk ok.
<!-- SECTION:FINAL_SUMMARY:END -->
