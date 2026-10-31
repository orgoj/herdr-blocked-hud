---
id: TASK-23
title: Sound per done status and separate blocked/done mute
status: In Progress
assignee:
  - '@hud_dev'
created_date: '2026-10-31 08:55'
updated_date: '2026-10-31 09:07'
labels: []
dependencies: []
type: feature
ordinal: 23000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Some done statuses disturb the user and need no reaction, others need one. A [done.modes] entry sets, besides the mode, which sound its status plays (blocked or done); no new config place. The single ♪ mute becomes two buttons, one for the blocked sound and one for the done sound. The current muted ♪ (overstrike font) looks bigger than the unmuted one.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A [done.modes] value can be a table { mode = "...", sound = "blocked" | "done" }; the plain mode string keeps working and plays the done sound; an invalid sound value is a startup error
- [ ] #2 A done row whose status sound is blocked plays the blocked sound; other done rows play the done sound
- [ ] #3 The HUD top line has two sound buttons, blocked and done, each toggling its sound independently; the tray menu has matching check items; a mute silences the sound actually played
- [ ] #4 Both mute states survive a restart; an old state file with muted sets both
- [ ] #5 A muted sound button has the same size as an unmuted one
- [ ] #6 README and docs/design.md describe the config and the two buttons
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Implemented: [done.modes] values may be { mode, sound } tables (DoneConfig.mode_of/sound_of); DoneTracker sets LongDone.sound; HudState raises beep_blocked for blocked-sound rows. sound_for takes muted kinds. Two canvas ♪ buttons (red blocked, orange done) with a canvas strike line (fixed size), tray menu items Mute blocked/done sound, tray tooltip names the muted kind. State file muted = list of kinds, old bool -> both/none. Full suite under xvfb: 127 OK.
<!-- SECTION:NOTES:END -->
