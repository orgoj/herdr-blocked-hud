---
id: TASK-25
title: Configurable order of Done sections
status: Done
assignee:
  - '@hud_dev'
created_date: '2026-10-31 09:13'
updated_date: '2026-10-31 09:28'
labels: []
dependencies: []
type: feature
ordinal: 25000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
User wants Done sections in a defined order (e.g. Done · NEEDS_USER right below Blocked). Today sections follow the order of their oldest row. User decision: no new config key; sections follow the order in which their status values are written in [done.modes]; statuses not listed there follow afterwards (in the current oldest-row order), the plain Done section (no status line) last. Rows within a section stay oldest first.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Done sections listed in [done.modes] appear in the order of their keys in the config file
- [x] #2 Sections of status values not in [done.modes] follow the listed ones in oldest-row order, and the plain Done section comes last
- [x] #3 Rows within a section keep the oldest-first order
- [x] #4 README, contrib/config.toml and docs/design.md describe the order
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
HudState.section_order = keys of [done.modes] (file order); sections sorted by (plain Done last, configured rank, oldest-row order). README, contrib/config.toml, docs/design.md describe it. Tests in test_done/test_config/test_hud_gui; 134 OK under xvfb; reviewed by agent_review.
<!-- SECTION:FINAL_SUMMARY:END -->
