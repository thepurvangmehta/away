---
name: on
description: Turn Away mode on so Claude keeps working unattended. Use when the user types /away:on or says they're going to sleep, going out, stepping away, or "away on".
---

# Away mode: on

1. Run `python3 "${CLAUDE_SKILL_DIR}/../../scripts/away.py" on`.
2. Say the goal back in one line so they know what you'll work on. If no goal was given, work on what the
   conversation was already doing.
3. Keep working until the goal is done. While away mode is on, a hook approves normal work,
   refuses risky things (deleting, deploying, pushing to main, sending, secrets, paid tools),
   answers your questions with the first (recommended) option, and sends you back to work if you stop early.
4. Never wait for the user. Skip anything that needs them and keep a **"Needs you"** list.
   Don't retry or work around a refusal.
5. When the goal is done, or everything left is on the list, write a short summary with the
   "Needs you" list and end with the exact line `AWAY: DONE`.
