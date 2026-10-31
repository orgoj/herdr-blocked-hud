---
id: TASK-17
title: Mute button on the HUD top line
status: Done
assignee:
  - '@hud_dev'
created_date: '2026-10-31 07:27'
updated_date: '2026-10-31 07:29'
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
- [x] #1 A mute button on the top line toggles all HUD sounds (blocked and done) off and on
- [x] #2 While muted the HUD still appears and lists rows as usual; only sound is suppressed
- [x] #3 The button shows whether sound is on or off
- [x] #4 Mute state lasts for the life of the process
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Added a ♪ label on the top line (DejaVu Sans has U+266A, checked with fc-match); a click toggles Hud.muted, which skips play() in show(); while muted the glyph is struck through and grey. In-memory only. Verified with test_mute_button_silences_sounds_but_keeps_the_hud (HUD still shown, no play while muted, state survives re-render); suite 87 OK under Xvfb.
<!-- SECTION:FINAL_SUMMARY:END -->
