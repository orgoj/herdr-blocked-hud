---
id: TASK-4
title: Long-done agents section with status-line filter
status: Done
assignee:
  - '@herdr_dev'
created_date: '2026-10-30 10:30'
updated_date: '2026-10-30 11:10'
labels: []
dependencies:
  - TASK-2
type: feature
ordinal: 4000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
List agents done (finished, not seen) longer than a threshold, with an optional regex filter on the agent's final status line. See docs/design.md section 5 (Long-done agents) and 6.3.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Agents done longer than done.after_seconds (default 60) appear in a second section with elapsed time; the timer is keyed by terminal_id and completion_seq
- [x] #2 Rows leave the section when the pane is no longer done
- [x] #3 Done sound has its own switch done.sound_enabled (default true), independent of the blocked sound
- [x] #4 With empty done.ignore_regexes every long-done agent is reported
- [x] #5 With ignore regexes set, only the bottom-most line matching done.status_line_regex is tested; no status line or a failed read reports the agent
- [x] #6 Pane output is read once per completion, not every poll; invalid regexes fail at startup
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Live: with 2 done agents, no ignore patterns reports both without any read; with ignore STATUS: DONE one is filtered after one agent read each (12 ms total). --demo screenshot shows Blocked and Done sections with elapsed time. complete.oga is the done sound (paplay rc 0). Reads use herdr --session <name> agent read <pane> --source recent --lines N on the poll thread. Config values come from DoneConfig defaults until TASK-5 loads the file.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Added DoneConfig (regexes compiled at construction), should_report (bottom-most status line decides, fail open), DoneTracker (timer per session/terminal/completion_seq, one read per completion, only with ignore patterns), Done section with elapsed time and done sound behind its own switch (sound_for). Verified with python3 tests/run (52 tests) and the live checks in notes.
<!-- SECTION:FINAL_SUMMARY:END -->
