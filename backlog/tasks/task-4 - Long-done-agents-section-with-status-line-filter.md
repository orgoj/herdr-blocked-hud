---
id: TASK-4
title: Long-done agents section with status-line filter
status: To Do
assignee: []
created_date: '2026-10-30 10:30'
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
- [ ] #1 Agents done longer than done.after_seconds (default 60) appear in a second section with elapsed time; the timer is keyed by terminal_id and completion_seq
- [ ] #2 Rows leave the section when the pane is no longer done
- [ ] #3 Done sound has its own switch done.sound_enabled (default true), independent of the blocked sound
- [ ] #4 With empty done.ignore_regexes every long-done agent is reported
- [ ] #5 With ignore regexes set, only the bottom-most line matching done.status_line_regex is tested; no status line or a failed read reports the agent
- [ ] #6 Pane output is read once per completion, not every poll; invalid regexes fail at startup
<!-- AC:END -->
