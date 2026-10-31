---
id: TASK-24
title: Set the HUD width by dragging its sides
status: Done
assignee:
  - '@hud_dev'
created_date: '2026-10-31 09:13'
updated_date: '2026-10-31 09:37'
labels: []
dependencies: []
type: feature
ordinal: 24000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
User wants to set the HUD width by mouse. Today the width comes only from config width (default 320); the override-redirect window cannot be resized by the WM. User decision: drag the left or right edge to resize; the width is saved in state.json like the position and mute, config width stays the default. In scope: an edge grab zone with a resize cursor, the opposite edge stays put, min width, wrap of the error text follows the width. Out of scope: height resize (height follows the content), resize from the tray menu.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Dragging the left or right edge of the HUD changes its width; the opposite edge stays in place and a drag elsewhere still moves the HUD
- [x] #2 The pointer shows a horizontal resize cursor over the edge zones
- [x] #3 The width never goes below 200 px nor beyond the monitor width
- [x] #4 The width is saved in state.json and restored after a restart; it is ignored when config width differs from the value it was saved with; deleting the file resets it
- [x] #5 README and docs/design.md describe the resize
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Left/right frame padding are placed grab zones (sb_h_double_arrow); an edge drag resizes with the opposite edge fixed and the moved one stopping at the monitor side; config/saved width bounded to 200..monitor width; width saved in state.json with the config width it replaced, void when that changes, reset by deleting the file. README and docs/design.md updated. 140 tests OK under xvfb; reviewed by agent_review (2 findings fixed).
<!-- SECTION:FINAL_SUMMARY:END -->
