---
id: TASK-6
title: MIT license and pilot-project disclaimer for GitHub publication
status: Done
assignee:
  - '@herdr_dev'
created_date: '2026-10-30 12:40'
updated_date: '2026-10-30 12:41'
labels: []
dependencies: []
type: docs
ordinal: 6000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Prepare the repository for publication on GitHub under the MIT license. The user decided: internal files (AGENTS.md, .dippy, backlog/, docs/) stay; README must say the project is a personal pilot built for the author's own machine and setup, provided without any warranty.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 LICENSE contains the MIT license text with copyright holder Michael Heca, 2026
- [x] #2 pyproject.toml declares license MIT, the license file and the author
- [x] #3 README states near the top that this is a personal pilot project for the author's machine and setup, unofficial and unaffiliated with Herdr, provided as is without warranty, and links the LICENSE
- [x] #4 README install instructions no longer depend on a local file:// path
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Added MIT LICENSE, PEP 639 license/author metadata in pyproject.toml, README pilot-project/no-warranty/unofficial notice, License section and a repository-URL install line. Verified: uv build wheel has License-Expression: MIT and dist-info/licenses/LICENSE.
<!-- SECTION:FINAL_SUMMARY:END -->
