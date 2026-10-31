---
id: TASK-19
title: Remember the HUD position and mute state across runs
status: Done
assignee:
  - '@hud_dev'
created_date: '2026-10-31 07:41'
updated_date: '2026-10-31 07:51'
labels: []
dependencies: []
type: feature
ordinal: 19000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The dragged position (TASK-16) and the mute state (TASK-17) last only for the process; after a restart or login the HUD is back in the corner and audible. Save both to a state file under XDG_STATE_HOME (default ~/.local/state/herdr-blocked-hud/state.json), not to the hand-written config.toml (rewriting it would drop comments; stdlib has no TOML writer). Demo mode neither reads nor writes it.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 After a drag and a restart the HUD appears at the dragged position
- [x] #2 After muting and a restart the HUD starts muted, and unmuting is remembered the same way
- [x] #3 The state is saved to $XDG_STATE_HOME/herdr-blocked-hud/state.json (default ~/.local/state/...), written atomically; the config file is never written
- [x] #4 A missing, unreadable or malformed state file gives the default position and sound on; a saved position from another configured corner is ignored
- [x] #5 The HUD is kept fully on the monitor, so a saved position from a larger monitor cannot put it off screen
- [x] #6 --demo neither reads nor writes the state file
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
New state.py saves corner+drag offset and mute to $XDG_STATE_HOME/herdr-blocked-hud/state.json (atomic tmp+os.replace) on drag end and mute toggle; Hud loads it via state_file (main only; demo passes none). Any malformed field voids the file; a valid offset from another corner is dropped, mute kept. Every render clamps the HUD onto the monitor. config.toml is never written. Verified: tests/test_state.py (round trip, malformed cases, corner change, failed save, XDG path, clamp) and GUI test_position_and_mute_survive_a_restart (new Hud takes position and mute; demo leaves the file untouched); 95 OK under Xvfb; reviewed by agent_review.
<!-- SECTION:FINAL_SUMMARY:END -->
