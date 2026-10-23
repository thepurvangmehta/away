# AGENTS.md: rules for AI coding agents working on Away

- **What this is:** see `README.md`. The plugin lives in `plugins/away/` (`hooks/`, `menubar/`, `scripts/`, `skills/`); pictures for the README in `docs/`.
- **Test before every commit:** `python test_away.py`. CI runs it on macOS, Ubuntu and Windows, so keep it portable.
- **Safety is the product.** Never loosen what Away refuses while the user is away (deleting, deploying, pushing to main, sending, secrets, paid tools) without the maintainer's explicit OK.
- **Words people read** (README, menus, messages): plain language, short lines, no em dashes.
