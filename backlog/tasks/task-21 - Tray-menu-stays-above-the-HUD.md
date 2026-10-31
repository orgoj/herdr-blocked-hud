---
id: TASK-21
title: Tray menu stays above the HUD
status: In Progress
assignee:
  - '@hud_dev'
created_date: '2026-10-31 08:35'
updated_date: '2026-10-31 08:35'
labels: []
dependencies: []
type: bug
ordinal: 21000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The tray right-click menu pops up behind the HUD when the HUD overlaps it: the HUD lifts itself on every refresh, above the open menu.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 While the tray menu is open, a HUD refresh does not raise the HUD above it
- [ ] #2 After the menu closes, refreshes raise the HUD again as before
<!-- AC:END -->
