---
name: off
description: Turn Away mode off and give the morning report. Use when the user types /away:off or says "I'm in", "I'm back", "away off", or asks what happened while they were away.
---

# Away mode: off

The script: `python3 "${CLAUDE_SKILL_DIR}/../../scripts/away.py"` (on Windows, use `python` if `python3` isn't found).

When the user types /away:off, "I'm in", "I'm back" or "away off", Away switches itself off the moment their
message arrives, before you read it. Claude can't switch Away off by itself on purpose, so nothing Claude
does at night can remove the safety net.

1. Run `away.py status`.
   - If it says OFF: good, go on.
   - If it still says ON (they used other words), don't try to turn it off yourself. Tell them:
     "Type /away:off, or click the moon and choose Turn off." Then stop.
2. Run `away.py report` and read it.
3. Tell them, in plain words:
   - what got done
   - what was refused
   - which questions you answered for them, so they can change any choice
   - the "Needs you" items as numbered steps they can act on
