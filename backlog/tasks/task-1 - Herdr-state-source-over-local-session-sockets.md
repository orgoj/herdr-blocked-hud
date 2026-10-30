---
id: TASK-1
title: Herdr state source over local session sockets
status: Done
assignee:
  - '@herdr_dev'
created_date: '2026-10-30 10:30'
updated_date: '2026-10-30 11:31'
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
- [x] #1 Discovers running local sessions from herdr session list --json and re-reads the list about every 10 s
- [x] #2 Reads panes, agents, workspace and tab labels over each session socket without spawning herdr per poll
- [x] #3 Socket I/O runs off the Tk main loop; a poll never blocks the UI
- [x] #4 An unreachable session yields an error state, never an empty blocked list
- [x] #5 Unit tests cover parsing of captured JSON fixtures
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
One session.snapshot request per running session and poll (agents, workspaces, tabs in one reply, ~21 KB, 2-4 ms live). Session list via herdr session list --json, refreshed every 10 s and retried on the next poll after a failure. No running session is reported as an error.

Review fix (agent_review): schema-incompatible JSON from session list or snapshot now yields SourceError / SessionState.error instead of killing the poll thread; Poller._run has an exception boundary that reports an internal error state; socket replies are capped at 8 MiB with a 3 s absolute deadline. Regression tests added.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Added herdr_blocked_hud/source.py: session discovery, Unix-socket session.snapshot client, Agent/SessionState/Model with labels, Poller on a daemon thread. Verified with python3 tests/run (13 tests, fixtures shaped from a captured Herdr 0.9.5 snapshot) and a live read-only poll of the default session.
<!-- SECTION:FINAL_SUMMARY:END -->
