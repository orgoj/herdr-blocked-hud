---
id: TASK-11
title: 'Done agents grouped by status value, sticky until the agent works again'
status: Done
assignee:
  - '@hud_dev'
created_date: '2026-10-30 16:15'
updated_date: '2026-10-30 16:23'
labels: []
dependencies: []
type: feature
ordinal: 11000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The user reviews finished agents by their final STATUS value: DONE replies are usually fine and may vanish once viewed, others need follow-up and must not disappear when the pane is opened (Herdr then marks it seen and idle). One regex extracts the value from the bottom-most status line; each value gets a mode.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 done.status_regex (default '^\s*STATUS:\s*(\S+)') finds the bottom-most matching line in the pane tail and its first group is the status value; it replaces done.status_line_regex and done.ignore_regexes
- [x] #2 Done rows are grouped in one section per status value, plus one for agents without a status line
- [x] #3 Each value has a mode: transient (row leaves when the pane leaves done, as before), sticky (row stays while the pane stays idle with the same completion; it leaves when the agent works again or a new completion arrives), hide (never listed); done.modes maps values, done.default_mode covers other values, done.no_status_mode covers no status line or a failed read; defaults transient, invalid modes are startup errors
- [x] #4 A completion viewed before done.after_seconds still gets classified, so a sticky one stays listed
- [x] #5 done.after_seconds defaults to 5
- [x] #6 A done row can be dismissed with a close button and with a right click; the dismissed completion is not listed again
- [x] #7 README, contrib/config.toml and docs/design.md describe the new keys and modes; tests cover extraction, every mode, dismissal and config validation
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
logic.py: DoneConfig with status_regex/modes/default_mode/no_status_mode; status_value(); DoneTracker classifies once per completion (at threshold or when it leaves done for idle), keeps sticky ones while idle with same seq, drops hide/dismissed; LongDone carries the status; HudState builds sections. app.py: one header per section, close button and right click call on_dismiss (tracker.dismiss under a lock, then poll_now). config.py validation. Docs + tests. Verified live: idle panes keep completion_seq, working has None.
<!-- SECTION:PLAN:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
status_regex extracts the STATUS value; done rows grouped per value with transient/sticky/hide modes (done.modes, default_mode, no_status_mode), sticky kept while idle with the same completion_seq, classification also when viewed before the threshold, after_seconds 5, dismiss via close button and right click. Verified: python3 tests/run and xvfb GUI tests OK (82); live Herdr keeps completion_seq on idle panes; agent_review OK.
<!-- SECTION:FINAL_SUMMARY:END -->
