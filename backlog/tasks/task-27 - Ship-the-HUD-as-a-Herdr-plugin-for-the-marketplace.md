---
id: TASK-27
title: Ship the HUD as a Herdr plugin for the marketplace
status: Done
assignee:
  - '@hud_dev'
created_date: '2026-10-31 10:20'
updated_date: '2026-10-31 10:27'
labels: []
dependencies: []
type: feature
ordinal: 27000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
User wants the HUD listed on herdr.dev/plugins. The marketplace lists public repos with GitHub topic herdr-plugin (set) and a parseable herdr-plugin.toml on the default branch. User decision: minimal manifest at the repo root, a startup hook that starts the HUD detached and exits, an action to start it by hand, no build step (stdlib only, runs from the plugin checkout). Out of scope: changing the user's own Herdr (no link/install here), panes, events, supervision.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 herdr-plugin.toml at the repo root has id, name, version, min_herdr_version, description and platforms linux, and its version follows the release version (bin/bump-version updates it)
- [x] #2 A startup hook and an action run a launcher that starts the HUD detached from Herdr (no inherited HERDR_* variables, herdr from HERDR_BIN_PATH reachable on PATH, output to a log in HERDR_PLUGIN_STATE_DIR) and exits at once; a second start leaves the running HUD alone
- [x] #3 README describes installing with herdr plugin install and its requirements (python3 with tkinter, X11 DISPLAY in the Herdr server)
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
herdr-plugin.toml at the root (id orgoj.blocked-hud, linux, min 0.7.5, startup hook + global start action) runs bin/herdr-plugin-start: setsid -f python3 -m herdr_blocked_hud with stdio redirected to HERDR_PLUGIN_STATE_DIR/hud.log (fails closed without it), HERDR_* dropped, HERDR_BIN_PATH dir on PATH; the HUD's lock keeps one instance. bump-version sets the manifest version. README documents install and requirements. Tests in test_plugin/test_bump; reviewed by agent_review and agent_security, Herdr behaviour confirmed by herdr_dev.
<!-- SECTION:FINAL_SUMMARY:END -->
