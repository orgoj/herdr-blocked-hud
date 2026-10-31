---
id: TASK-26
title: Sticky done rows survive a HUD restart
status: Idea
assignee: []
created_date: '2026-10-31 09:16'
updated_date: '2026-10-31 09:16'
labels: []
dependencies: []
type: bug
ordinal: 26000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
After a HUD restart, an agent whose reply ended with a sticky status (e.g. STATUS: NEEDS_USER) is no longer listed (user report: wdt_main). Cause: DoneTracker starts tracking a completion only while its pane is in done; a pane already viewed is idle at HUD start and is never read. User decision: sticky rows must survive a restart; the status line can be parsed at startup. This replaces the 'sticky state is not kept across restarts (decided)' line in docs/design.md. Direction: at startup also read idle panes that still carry a completion_seq (Herdr keeps it on idle panes until the agent works again) and list them per their status mode, without a sound. Open question: should a row dismissed before the restart stay dismissed (needs the dismissals in the state file)?
<!-- SECTION:DESCRIPTION:END -->
