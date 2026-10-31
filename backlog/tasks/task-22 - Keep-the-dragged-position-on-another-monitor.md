---
id: TASK-22
title: Keep the dragged position on another monitor
status: To Do
assignee: []
created_date: '2026-10-31 08:39'
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
- [ ] #1 A HUD dragged onto a non-primary monitor stays there across refreshes, height changes and restarts
- [ ] #2 A saved position on a monitor that is no longer connected is clamped onto an existing monitor
- [ ] #3 Single-monitor behaviour is unchanged
<!-- AC:END -->
