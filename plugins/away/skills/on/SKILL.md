---
name: on
description: Turn Away mode on so Claude keeps working unattended in this chat. Use when the user types /away:on or says they're going to sleep, going out, stepping away, or "away on".
argument-hint: "[the job to finish while you're away]"
---

# Away mode: on

The job the user typed after the command: $ARGUMENTS

## 1. Decide the goal first
- If a job was typed above, that is the goal.
- Otherwise, if this chat already has work in progress, the goal is to finish that work.
- Otherwise there is no goal. **Don't turn Away on** and don't start anything on your own.
  Reply with one line: "Tell me the job first, like: `/away:on fix the images on the Work page`", then stop.

## 2. Turn it on (only with a goal)
1. Run `python3 "${CLAUDE_SKILL_DIR}/../../scripts/away.py" on`.
   Away now covers only this chat. The user's other chats keep asking as normal.
2. Say the goal back in one line.
3. Work until the goal is done. While Away is on, a hook approves normal work,
   refuses risky things (deleting, deploying, pushing to main, sending, secrets, paid tools),
   answers your questions with the first (recommended) option, and sends you back to work if you stop early.
4. Never wait for the user. Skip anything that needs them and keep a **"Needs you"** list.
   Don't retry or work around a refusal. Stay on the goal: don't pick up other tasks, reminders or board items.
5. When the goal is done, or everything left is on the list, write a short summary with the
   "Needs you" list and end with the exact line `AWAY: DONE`.
