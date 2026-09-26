---
name: off
description: Turn Away mode off and give the morning report. Use when the user types /away:off or says "I'm in", "I'm back", "away off", or asks what happened while they were away.
---

# Away mode: off

1. Run `python3 "${CLAUDE_SKILL_DIR}/../../scripts/away.py" off` and read the report it prints.
2. Tell them, in plain words:
   - what got done
   - what was refused
   - which questions you answered for them, so they can change any choice
   - the "Needs you" items as numbered steps they can act on
