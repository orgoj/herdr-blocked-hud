---
id: TASK-17
title: Mute button on the HUD top line
status: To Do
assignee: []
created_date: '2026-10-31 07:27'
labels: []
dependencies: []
type: feature
ordinal: 17000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Sometimes the user only wants the HUD to pop up, without sound. A button on the top line (next to restart and quit) toggles the HUD's sounds off and on; the HUD itself keeps appearing as before. Remembering the state across restarts is out of scope.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A mute button on the top line toggles all HUD sounds (blocked and done) off and on
- [ ] #2 While muted the HUD still appears and lists rows as usual; only sound is suppressed
- [ ] #3 The button shows whether sound is on or off
- [ ] #4 Mute state lasts for the life of the process
<!-- AC:END -->
