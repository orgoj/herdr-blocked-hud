---
id: TASK-1
title: Herdr state source over local session sockets
status: To Do
assignee: []
created_date: '2026-10-30 10:30'
labels: []
dependencies: []
type: feature
ordinal: 1000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Poll every running local Herdr session (herdr session list --json) over its Unix socket each 1 s and build the HUD model: blocked and done agents with workspace/tab/agent labels. See docs/design.md sections 1, 2A, 6.1.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Discovers running local sessions from herdr session list --json and re-reads the list about every 10 s
- [ ] #2 Reads panes, agents, workspace and tab labels over each session socket without spawning herdr per poll
- [ ] #3 Socket I/O runs off the Tk main loop; a poll never blocks the UI
- [ ] #4 An unreachable session yields an error state, never an empty blocked list
- [ ] #5 Unit tests cover parsing of captured JSON fixtures
<!-- AC:END -->
