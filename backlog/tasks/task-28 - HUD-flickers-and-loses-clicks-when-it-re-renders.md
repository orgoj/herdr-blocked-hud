---
id: TASK-28
title: HUD flickers and loses clicks when it re-renders
status: In Progress
assignee:
  - '@hud_dev'
created_date: '2026-10-31 22:33'
updated_date: '2026-10-31 22:48'
labels: []
dependencies: []
type: bug
ordinal: 28000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
User report: the HUD redraws and flickers, and a click on a row often does nothing.

Findings (code app.py Hud.apply/render, read-only probe tmp/render_probe.py against the live Herdr, 180 s: 7 renders):
1. Every View difference rebuilds the whole HUD: render() destroys all widgets and creates them again, then sets geometry. That is the visible flicker; a row under the pointer also loses its hover colour.
2. View equality compares more than is shown: Row.agent holds the full Agent (focused, completion_seq, pane ids), and View holds beep_blocked/beep_done. So a beep costs two rebuilds (flag set, then cleared next poll), and every Herdr focus change of a listed agent (also the one a row click causes) rebuilds although nothing visible changed.
3. Done rows show elapsed minutes, so each Done row forces a rebuild every minute, at its own offset.
4. A click is lost when a rebuild lands between press and release: on_release is bound to the destroyed widget, the new widget never saw the press. A row appearing or vanishing above the pointer also shifts all rows, so the click lands on another row or in a gap.

Suggested direction: (a) render only on a change of what is displayed (titles, row texts, error), never on beep flags or hidden Agent fields; (b) update row widgets in place (keyed by pane) instead of destroy/recreate, resize the window only when its height changes; (c) open: hold re-layout while the pointer is over the HUD or a button is held, and apply it on Leave/release. Needs the user's decision on (c) before implementation.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A poll whose View differs only in fields the HUD does not show (beep flags, Agent focused/completion_seq/pane ids) destroys and creates no widget and does not set the window geometry
- [ ] #2 A change of displayed text only (e.g. a Done row's elapsed minutes) updates the existing label in place: the row widgets stay the same objects, no geometry call
- [ ] #3 Rows, headers and the error line are created or destroyed only when they appear or disappear; widgets of rows that stay are kept
- [ ] #4 A row click acts on the agent of the latest poll, also when the row was not re-created since
- [ ] #5 Changes show at once also while the pointer rests on the HUD (no hold); a click on the row under a resting pointer acts on the row shown there now
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. bin/bump-version 0.1.20. 2. logic.py: pure layout(view) -> Items (key, text, agent), keys: header text, row agent_key + dismissible, error text. 3. app.py: top line (buttons, title) built once; render diffs Items against kept widgets, packs only on order change, sets geometry only when it changed; row handlers look the agent up by key. 4. Tests: layout unit tests, GUI tests for in-place update, kept widgets, resting-pointer clicks. 5. Review agent_review, tag v0.1.20, install.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
User approved (a), (b) and (c) (hold while hovered) on 2026-10-31.

User rejected (c) mid-implementation: the HUD must redraw at once while the pointer rests on it (workflow: pointer stays on the top row, click, type in the terminal). Hold removed; only (a) and (b) implemented.
<!-- SECTION:NOTES:END -->
