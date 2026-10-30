---
id: TASK-7
title: Ctrl+C ends the HUD quietly
status: Done
assignee:
  - '@herdr_dev'
created_date: '2026-10-30 12:54'
updated_date: '2026-10-30 13:48'
labels: []
dependencies: []
type: bug
ordinal: 7000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Ctrl+C in the terminal running herdr-blocked-hud prints a KeyboardInterrupt traceback from Tk mainloop (reported by the user on v0.1.1).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Ctrl+C (SIGINT) leaves the Tk main loop and the process exits with status 130 without a traceback
- [x] #2 A unit test covers that the SIGINT handler stops the main loop
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Review fix (agent_review): the handler schedules root.quit via after_idle, since entering mainloop resets Tk's quit flag and a startup-time Ctrl+C was lost. Verified: tests/run 69 OK; real Tk with SIGINT before mainloop leaves the loop; live --demo SIGINT -> rc 130, no output.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
SIGINT handler (quit_on_sigint) asks Tk to quit and main() returns 130. Verified: tests/run 69 OK; live --demo with Python 3.14 + Tk, SIGINT after 2 s -> exit 130, empty stdout/stderr.
<!-- SECTION:FINAL_SUMMARY:END -->
