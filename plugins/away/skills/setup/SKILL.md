---
name: setup
description: Choose how careful Away is (careful, balanced or hands-off) and add your own must-wait rules. Use when the user types /away:setup, or asks to change what Away approves or refuses while they're away.
---

# Away setup

The script: `python3 "${CLAUDE_SKILL_DIR}/../../scripts/away.py"` (on Windows, use `python` if `python3` isn't found).
Below it's written as `away.py`.

1. Run `away.py status`. If Away is ON, say "Switch Away off first with /away:off, then run /away:setup", and stop
   (questions are blocked while Away is on).
2. Run `away.py config` to see the current settings.
3. Ask these in ONE AskUserQuestion call:
   - "What kind of work will Claude do while you're away?" (single choice)
     - "A mix (Recommended)": waits on deleting, deploying, pushing to main, secrets, sending and paid tools → `balanced`
     - "Client or company code": also waits on installs, any push, database commands and writing outside the project → `careful`
     - "My own side projects": only waits on what can't be undone → `hands-off`
   - "Anything else that must always wait for you?" (multiSelect; skip options the chosen level already covers)
     - "Installing software"
     - "Any push to GitHub"
     - "Database changes"
     - "Nothing else"
   - "What should Claude call you in its notes?" (single choice): offer their first name if `git config user.name`
     gives one, and "Just 'you'".
4. Save the answers:
   - `away.py set level <balanced|careful|hands-off>`
   - Installing software: `away.py add refuse_commands "\b(npm|pnpm|yarn|bun)\s+(install|i|add|ci)\b|\bpip3?\s+install\b|\b(brew|cargo|gem|go|winget|choco)\s+install\b"`
   - Any push to GitHub: `away.py add refuse_commands "\bgit\b[^|;&\n]*\spush\b"`
   - Database changes: `away.py add refuse_commands "\b(psql|mysql|mongosh?|sqlite3|redis-cli)\b|\bprisma\s+(migrate|db)\b|\bsupabase\s+db\b"`
   - Name: `away.py set name <name>` (skip for "Just 'you'")
5. Run `away.py config` and tell them in plain words what will wait for them now.
   End with: "Next time you leave, type /away:on followed by the job."
