---
id: TASK-26
title: Sticky done rows survive a HUD restart
status: Idea
assignee: []
created_date: '2026-10-31 09:16'
labels: []
dependencies: []
type: bug
ordinal: 26000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
After a HUD restart, an agent whose reply ended STATUS: NEEDS_USER (sticky) is no longer listed (user report: wdt_main). Cause from the code: DoneTracker starts tracking a completion only while its pane is in done; a pane the user already viewed is idle at HUD start and is never read. design.md records 'sticky state is not kept across restarts' as decided; the user now wants it kept. Suggested direction: at startup also read idle panes that still carry a completion_seq (Herdr keeps it on idle panes until the agent works again) and list them per their status mode, without a sound. Needs analysis before implementation.
<!-- SECTION:DESCRIPTION:END -->
