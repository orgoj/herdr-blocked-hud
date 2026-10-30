---
id: TASK-9
title: Distinct built-in sounds for blocked and done
status: Done
assignee:
  - '@herdr_dev'
created_date: '2026-10-30 14:15'
updated_date: '2026-10-30 14:32'
labels: []
dependencies: []
type: enhancement
ordinal: 9000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
User report: the blocked and done sounds (freedesktop dialog-warning.oga and complete.oga) cannot be told apart from each other, from system notifications or from the Bluetooth connect sound. The HUD should play its own sounds by default, clearly different for blocked and done. Approach: generate two short tone patterns with the stdlib (wave), write them once to a cache file and play them with paplay; no binary assets, no new dependencies. Config keys blocked_sound and done_sound keep accepting a file path and "" (off); the new default "builtin" selects the HUD's own sound. --demo plays both so the user can hear them.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 By default a blocked event plays a HUD-generated sound and a done event a different HUD-generated sound, neither taken from the system sound theme
- [x] #2 blocked_sound and done_sound accept "builtin" (default), a file path, or "" to disable; README and contrib/config.toml document it
- [x] #3 herdr-blocked-hud --demo plays the blocked sound and then the done sound
- [x] #4 Unit tests cover sound selection and that the generated sounds are valid WAV data that differ between blocked and done
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
New sounds.py renders two WAV patterns (blocked: double two-tone call 1319/988 Hz; done: rising C-E-G chime), cached in XDG_CACHE_HOME/herdr-blocked-hud/<kind>-v1.wav; blocked_sound/done_sound default "builtin"; --demo plays both. Verified: tests/run 70 OK, paplay plays both files, user listened and approved the sounds.
<!-- SECTION:FINAL_SUMMARY:END -->
