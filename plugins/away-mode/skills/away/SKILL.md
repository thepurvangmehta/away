---
name: away
description: Turn Away mode on or off. Use when the user says they're going to sleep, going out, stepping away, "away on", or wants Claude to keep working unattended; and when they say "I'm in", "I'm back", "away off", or ask what happened while they were away.
---

# Away mode

The script is `${CLAUDE_SKILL_DIR}/../../scripts/away.py`.

## Going away ("I'm going to sleep", "I'm going out", "away on")
1. Run `python3 "${CLAUDE_SKILL_DIR}/../../scripts/away.py" on`.
2. Say the goal back in one line so they know what you'll work on.
3. Keep working until the goal is done. While away mode is on, a hook approves normal work,
   refuses risky things (deleting, deploying, pushing to main, sending, secrets, paid tools),
   answers your questions with the first (recommended) option, and sends you back to work if you stop early.
4. Never wait for the user. Skip anything that needs them and keep a **"Needs you"** list.
   Don't retry or work around a refusal.
5. When the goal is done, or everything left is on the list, write a short summary with the
   "Needs you" list and end with the exact line `AWAY: DONE`.

## Coming back ("I'm in", "I'm back", "away off")
1. Run `python3 "${CLAUDE_SKILL_DIR}/../../scripts/away.py" off` and read the report it prints.
2. Tell them, in plain words: what got done, what was refused, which questions you answered for them
   (so they can change any choice), and the "Needs you" items as numbered steps.
