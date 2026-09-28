---
name: moon
description: Add the Away moon to the Mac menu bar (a one-click on/off switch that also shows the "Needs you" count). Use when the user types /away:moon or asks for the menu bar icon.
---

# Add the Away moon

1. This only works on a Mac. On anything else, say so in one line and stop.
2. Run `bash "${CLAUDE_SKILL_DIR}/../../menubar/build.sh"`.
3. If the output says `NEEDS_XCODE_TOOLS`, tell the user, in plain words:
   "Your Mac needs Apple's free developer tools first. Run `xcode-select --install`, click Install
   in the window that opens, wait for it to finish, then type /away:moon again."
4. When it works, tell them:
   - Look at the top right of the screen, near the clock: the outline moon is Away.
   - Filled moon = Away is on. A number next to it = things waiting for you.
   - Click it, then "Open at login" so it comes back after a restart.
