# Away for Claude Code

Claude Code is great until you step away.
You come back and it's been waiting on one "Allow?" for three hours.

Away mode keeps it working while you sleep.
It skips anything risky and hands you a short list in the morning.

## What it does

| While you're away | What happens |
|---|---|
| Normal work (terminal, files, installs, tests) | Approved, Claude keeps going |
| Risky things (deleting, deploying, pushing to main, sending, secrets, paid tools) | Refused and added to a **Needs you** list |
| Claude wants to ask you something | It can't ask. It goes with its recommended option and lists it for you in the morning |
| Claude wants to open a new web page in the browser | Blocked, because the app's "allow this site?" pop-up can't be answered while you're away. It reads the page another way or leaves it for you |
| Claude finishes a plan and wants your OK | It can't get it. The plan goes on the Needs you list |
| Claude stops early or asks "should I continue?" | Sent back to work until the goal is done (capped at 30 nudges) |

When away mode is off, nothing changes. Your own deny rules always win.

## Install

In Claude Code:

```
/plugin marketplace add thepurvangmehta/away
/plugin install away@away
```

Needs Python 3 (already on macOS). Keeping the machine awake works on macOS; on other systems, keep it awake yourself.

## Use

1. Type **`/away:on`** followed by the job, for example `/away:on fix the images on the Work page`.
   Or give Claude the job first, then say "I'm going to sleep". Away covers only that chat, and switches off when the job is done.
2. In the morning, type **`/away:off`** (or say "I'm in"). You get what got done, what was refused, the answers it picked for you, and the Needs you list.

Keep the laptop plugged in with the lid open.

## Menu bar moon (Mac, optional)

A moon in your menu bar: outline when Away is off, filled when it's on.
Click it to turn Away on for every open chat, or off, see tonight's count, and read the "Needs you" list.
A number next to the moon means new things are waiting for you.

```
git clone https://github.com/thepurvangmehta/away && ./away/menubar/build.sh
```

Needs Xcode Command Line Tools (`xcode-select --install`). Turn on "Open at login" from its menu.

## Your own refuse list (optional)

Create `~/.claude/away.json`:

```json
{
  "name": "Sam",
  "refuse_commands": ["\\bterraform\\s+apply"],
  "refuse_paths": ["/Finance/"],
  "refuse_tools": ["stripe"]
}
```

Each entry is a regular expression. A match means "skip it and ask me in the morning".

## Good to know

- It can't answer pop-ups that come from the Claude app itself: "Do you trust this folder?" (start in a folder you've used before) and the browser's "allow this site?" (so Away keeps Claude out of the browser overnight).
- It's cautious on purpose. A command that only *mentions* `rm -rf` gets skipped too.
- If Remote Control is on, your phone may still buzz for prompts Away mode already approved (a known Claude Code bug, anthropics/claude-code#96126). Turn it off for the night.
- You're trusting Claude with your machine overnight. Use it on work you'd be fine to review in the morning, and keep backups.

## Want it set up for your team?

I set this up for studios and small teams, with rules that fit how you work.
[thepurvangmehta.com](https://thepurvangmehta.com)

MIT license. Made by Purvang Mehta.
