# herdr-blocked-hud

Always-on-top desktop HUD (Linux, X11) that lists Herdr panes whose agent is
`blocked`, beeps when one appears, focuses the pane and its terminal window on
click, and hides itself when nothing is blocked.

- Specification: `docs/spec.md` (Czech).
- Design: `docs/design.md`; tasks in `backlog/` (Backlog.md).
- Code: `herdr_blocked_hud/` (Python 3 stdlib only). Tests: `python3 tests/run`.
- Temporary files only in `tmp/` (gitignored).
