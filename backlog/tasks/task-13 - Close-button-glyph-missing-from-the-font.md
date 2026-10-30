---
id: TASK-13
title: Close button glyph missing from the font
status: Done
assignee:
  - '@hud_dev'
created_date: '2026-10-30 16:26'
updated_date: '2026-10-30 16:28'
labels: []
dependencies: []
type: bug
ordinal: 13000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
User report: the done-row close button shows a missing-glyph box; U+2715 is not in the user's Tk font.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The close button uses U+00D7 (×), present in every Latin-1 font
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Close button glyph U+2715 replaced by U+00D7 in app, GUI test and docs; Noto Sans (user's font) has U+00D7. Tests OK incl. xvfb GUI; agent_review OK.
<!-- SECTION:FINAL_SUMMARY:END -->
