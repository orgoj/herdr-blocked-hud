---
id: TASK-28
title: HUD flickers and loses clicks when it re-renders
status: Idea
assignee: []
created_date: '2026-10-31 22:33'
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
