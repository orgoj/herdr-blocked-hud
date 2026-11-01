---
id: TASK-29
title: 'Delayed, repeating reminder sound instead of a beep per new row'
status: Done
assignee:
  - '@hud_dev'
created_date: '2026-11-01 08:12'
updated_date: '2026-11-01 08:16'
labels: []
dependencies: []
type: feature
ordinal: 29000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
With 10+ agents the HUD beeps constantly; the sound stops being a notice and only disturbs. New sound_mode "delayed" (default): no sound when a row appears; once something that sounds (a blocked row or a done row with its sound) has been listed for sound_delay seconds (default 60), one sound plays, repeated every sound_repeat seconds (default 300, 0 = once) while such rows stay listed; the timer resets when none is listed. Popups and the HUD itself stay immediate. sound_mode = "immediate" keeps the old beep per new row.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Default config: no sound when a blocked or done row appears; one sound after sound_delay (default 60 s) if a sounding row is still listed
- [x] #2 While sounding rows stay listed the sound repeats every sound_repeat (default 300 s) after the first one; sound_repeat = 0 plays it only once
- [x] #3 When no sounding row is listed the timer resets; the next row starts the delay again
- [x] #4 Muted kinds and done.sound_enabled = false do not count as sounding; blocked wins over done when both are due
- [x] #5 sound_mode = "immediate" keeps the previous beep per new row; invalid sound_mode or negative sound_delay/sound_repeat is a config error
- [x] #6 README and docs describe the new keys
- [x] #7 New rows still show the HUD at once (the HUD has no popups of its own; Herdr toasts are untouched)
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Implemented SoundReminder (logic.py), View.pending, Hud.remind (app.py), config keys sound_mode/sound_delay/sound_repeat. A kind with sound "" also does not count. Tests: xvfb-run -a env HUD_GUI_TESTS=1 python3 tests/run, 154 OK.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Default sound_mode "delayed": View.pending + SoundReminder play a reminder after sound_delay (60 s), repeated every sound_repeat (300 s, 0 = once) while a row with a sound is listed; reset when none is; muted/disabled kinds do not count; "immediate" keeps the old beep. Verified with tests/test_logic.py, test_config.py, test_hud_gui.py (154 OK under xvfb-run); reviewed by agent_review.
<!-- SECTION:FINAL_SUMMARY:END -->
