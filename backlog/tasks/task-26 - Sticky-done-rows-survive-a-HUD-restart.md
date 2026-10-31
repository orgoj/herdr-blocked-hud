---
id: TASK-26
title: Read done status of idle panes at HUD start
status: To Do
assignee: []
created_date: '2026-10-31 09:16'
updated_date: '2026-10-31 09:17'
labels: []
dependencies: []
type: bug
ordinal: 26000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
After a HUD restart, an agent whose reply ended with a sticky status (e.g. STATUS: NEEDS_USER) is no longer listed (user report: wdt_main). Cause: DoneTracker starts tracking a completion only while its pane is in done; a pane already viewed is idle at HUD start and is never read. User decision: nothing is stored on disk (no sticky or dismissal state file); at startup the HUD reads the status line of every pane that carries a completion (done, or idle with a completion_seq; Herdr keeps it until the agent works again) and lists it per its status mode. A dismissal before the restart is not remembered. Update the 'sticky state is not kept across restarts' line in docs/design.md.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 At HUD start, an idle pane whose last reply has a sticky status is listed in its Done section
- [ ] #2 At HUD start, an idle pane whose status is transient or hide (or has no status line, with no_status_mode transient) is not listed
- [ ] #3 Rows listed at startup play no sound
- [ ] #4 Nothing new is written to disk; docs/design.md describes the startup read
<!-- AC:END -->
