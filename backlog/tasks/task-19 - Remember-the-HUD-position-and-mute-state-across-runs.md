---
id: TASK-19
title: Remember the HUD position and mute state across runs
status: In Progress
assignee:
  - '@hud_dev'
created_date: '2026-10-31 07:41'
updated_date: '2026-10-31 07:41'
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
- [ ] #1 After a drag and a restart the HUD appears at the dragged position
- [ ] #2 After muting and a restart the HUD starts muted, and unmuting is remembered the same way
- [ ] #3 The state is saved to $XDG_STATE_HOME/herdr-blocked-hud/state.json (default ~/.local/state/...), written atomically; the config file is never written
- [ ] #4 A missing, unreadable or malformed state file gives the default position and sound on; a saved position from another configured corner is ignored
- [ ] #5 The HUD is kept fully on the monitor, so a saved position from a larger monitor cannot put it off screen
- [ ] #6 --demo neither reads nor writes the state file
<!-- AC:END -->
