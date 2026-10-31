---
id: TASK-22
title: Keep the dragged position on another monitor
status: Done
assignee:
  - '@hud_dev'
created_date: '2026-10-31 08:39'
updated_date: '2026-10-31 08:45'
labels: []
dependencies: []
type: bug
ordinal: 22000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
With several monitors, dragging the HUD to a non-primary monitor does not stick: on the next render (a state change) the HUD jumps back to the primary monitor. Likely cause: render() clamps the window onto self.monitor (the primary monitor, TASK-19 clamp), so any position outside it is pulled back. Fix direction: clamp onto the monitor that contains the dragged position (or the union of all monitors), and keep the saved offset working when that monitor is absent at startup.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A HUD dragged onto a non-primary monitor stays there across refreshes, height changes and restarts
- [x] #2 A saved position on a monitor that is no longer connected is clamped onto an existing monitor
- [x] #3 Single-monitor behaviour is unchanged
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
clamp() now takes all monitors (x11.monitors(), primary first) and clamps onto the monitor holding the window centre, else the nearest; place() still uses the primary. Tests: ClampTests (multi-monitor, gap, off-screen), MonitorTests (parse_monitors), GUI test_position_on_a_second_monitor_sticks (drag, refreshes with height change, restart, monitor removed). Full suite under xvfb: 121 OK.

Review fix: parse_monitors accepts signed origins (monitor left of/above the primary); GUI test also covers a second monitor with a negative origin. 122 OK.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
clamp() keeps the HUD fully on the monitor holding its centre, else the nearest one, using all monitors from xrandr (signed origins, primary first); place() still uses the primary corner. Verified: ClampTests, MonitorTests, GUI test for a right and a left second monitor (drag, refreshes with height change, restart, monitor removed); single-monitor drag tests unchanged. 122 OK under xvfb; reviewed by agent_review.
<!-- SECTION:FINAL_SUMMARY:END -->
