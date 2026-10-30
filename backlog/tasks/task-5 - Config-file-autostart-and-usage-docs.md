---
id: TASK-5
title: 'Config file, autostart and usage docs'
status: Done
assignee:
  - '@herdr_dev'
created_date: '2026-10-30 10:30'
updated_date: '2026-10-30 11:31'
labels: []
dependencies:
  - TASK-2
  - TASK-3
type: feature
ordinal: 5000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Configuration, desktop autostart and a README for the prototype. See docs/design.md section 5.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Settings read from ~/.config/herdr-blocked-hud/ (position, window class, sounds, poll interval, done options) with documented defaults
- [x] #2 README documents install, config keys and run
- [x] #3 contrib/herdr-blocked-hud.desktop passes desktop-file-validate, runs herdr-blocked-hud from PATH, and ~/.local/bin is on the LXQt session PATH
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
AC2 narrowed to what is verifiable before installation: the user wants a review and the bin agent to own installation into ~/.local/bin and ~/.config/autostart, so no login test was run. Evidence: desktop-file-validate rc 0; lxqt-session PATH contains /home/michael/.local/bin; launcher works through a symlink from another cwd (--check-config rc 0); unknown arguments exit 2. Nothing was installed.

Review fix (agent_review): config rejects non-positive width and done.after_seconds and negative margins; README and contrib/config.toml document the limits and the session-safe wm_class fallback.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Added config.py (config.toml via tomllib, defaults, strict key/type/regex validation), place() for corner positioning, config wiring (poll interval, wm_class, sounds, done options), --check-config, bin/herdr-blocked-hud launcher, contrib/config.toml (all defaults, tested equal to Config()), contrib/herdr-blocked-hud.desktop and README.md. Verified with python3 tests/run (57 tests) and the checks in notes.
<!-- SECTION:FINAL_SUMMARY:END -->
