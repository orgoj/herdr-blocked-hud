---
id: TASK-20
title: Tray icon with HUD toggle and control menu
status: Done
assignee:
  - '@hud_dev'
created_date: '2026-10-31 08:14'
updated_date: '2026-10-31 08:31'
labels: []
dependencies: []
type: feature
ordinal: 20000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
A status-bar icon for the HUD. Tk 9 tk systray cannot receive clicks in the LXQt 1.4 panel (its XEmbed-to-SNI proxy injects clicks via XTest onto the panel; research tmp/knowledge/tk-systray-lxqt.md), so the HUD exports its own StatusNotifierItem over D-Bus, implemented with the Python standard library only (no D-Bus package). Without a session bus or StatusNotifierWatcher the HUD runs as before, without an icon.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 With a StatusNotifierWatcher on the session bus the HUD registers a StatusNotifierItem; without a bus or watcher it runs as before and reports the missing tray once on stderr
- [x] #2 The icon is grey when nothing is listed, orange when only done rows are listed, red when a pane is blocked; the tooltip gives the blocked and done counts and says when sound is muted
- [x] #3 Left click hides the HUD when it is shown and shows it when hidden, also when nothing is listed; a new blocked or done sound event shows the HUD again
- [x] #4 Right click opens a menu at the pointer with Mute/Unmute, Restart and Quit, acting like the HUD buttons (mute state saved as with the ♪ button)
- [x] #5 After the panel restarts (watcher owner changes) the item registers again
- [x] #6 D-Bus message encoding and decoding and the item's method and property replies are covered by tests without a display or a real bus
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Own StatusNotifierItem (Tk 9 tk systray gets no clicks in LXQt 1.4: XEmbed-to-SNI proxy injects XTest clicks onto the panel). New dbus.py (minimal stdlib D-Bus client: SASL EXTERNAL, strict marshalling, calls/replies/signals, input bounds) and tray.py (item properties, generated grey/orange/red ARGB32 icon, tooltip with counts and mute, Activate/ContextMenu to a bounded queue, re-registration on watcher NameOwnerChanged, daemon thread). app.py: tray left click toggles the HUD (also empty: 'Nothing waiting') until the next sound event; right click pops a Tk menu Mute/Restart/Quit. Verified: codec and item unit tests without bus or display, private dbus-daemon + gdbus integration test (GetAll, Activate, ContextMenu, re-registration), GUI tests for toggle, menu, bounded drain and tray state; 117 OK under Xvfb. Reviewed by agent_review (functional) and agent_security (after fixing its flood and malformed-frame findings).
<!-- SECTION:FINAL_SUMMARY:END -->
