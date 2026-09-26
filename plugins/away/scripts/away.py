#!/usr/bin/env python3
"""Away mode: keeps Claude Code working while you sleep or step out.

  away.py on        turn it on (also keeps the Mac awake)
  away.py off       turn it off, show the morning report
  away.py status    is it on?
  away.py report    what it approved, refused and answered

With no arguments it runs as the Claude Code hook (see hooks/hooks.json):
  PermissionRequest              -> allow normal work, refuse risky things ("Needs you")
  PreToolUse on AskUserQuestion  -> pick the first option (the "Recommended" one)
  Stop                           -> send Claude back to work until it says AWAY: DONE
When away mode is off it does nothing, so everything behaves as usual.
Your deny rules in settings.json still win over this hook.

Optional ~/.claude/away.json:
  {"name": "Sam", "refuse_commands": [regex...], "refuse_paths": [regex...], "refuse_tools": [regex...]}
"""
import json, os, re, signal, subprocess, sys, time

HOME = os.path.expanduser("~")
FLAG = f"{HOME}/.claude/away.on"
LOG = f"{HOME}/.claude/away.log"
PIDFILE = f"{HOME}/.claude/away.caffeinate"
CONFIG = f"{HOME}/.claude/away.json"
MAX_NUDGES = 30  # ponytail: per-session cap so an impossible goal can't loop all night

# Bash commands never auto-approved. Claude is told to skip them and list them for the morning.
RISKY_BASH = [
    (r"\brm\s+(-\w*[rRf]|--recursive|--force)", "deleting files"),
    (r"\brmdir\b|\bshred\b|\bsrm\b", "deleting files"),
    (r"\bgit\s+push\b.*(\s-f\b|--force)", "force-pushing"),
    (r"\bgit\s+push\b.*\b(main|master)\b", "pushing to main"),
    (r"\bgit\s+(reset\s+--hard|clean\s+-\w*f|branch\s+-D|filter-branch|filter-repo)", "throwing away git work"),
    (r"\bgit\s+(config\b.*user\.|commit\b.*--author)", "changing git identity"),
    (r"\b(vercel|netlify)\b(?!\s+(dev|logs|ls|list|whoami|inspect|link|env\s+pull)\b)", "deploying"),
    (r"\bfirebase\s+deploy|\bwrangler\s+(deploy|publish|pages\s+deploy|secret|delete)", "deploying"),
    (r"\bgh\s+(pr\s+merge|repo\s+(delete|edit)|release\s+create|secret)", "publishing on GitHub"),
    (r"\b(npm|pnpm|yarn)\s+publish\b", "publishing a package"),
    (r"\bsudo\b|\bshutdown\b|\breboot\b|\bdiskutil\b|\bcsrutil\b|\bdefaults\s+write\b", "changing the computer itself"),
    (r"\.env\b|keychain|\bsecurity\s+find-", "touching secrets"),
    (r"\b(curl|wget)\b.*\|\s*(ba|z)?sh\b", "running a script from the internet"),
    (r"\bsendmail\b|\bosascript\b", "sending a message"),
]
# MCP / app tools whose name suggests an outward, paid or permanent action.
RISKY_TOOL = re.compile(
    r"send|delete|remove|publish|deploy|post|merge|purchase|pay|transfer|"
    r"archive|share|invite|comment|reply|secret|generate_|upscale",
    re.I,
)
RISKY_PATH = [r"(^|/)\.env", r"/\.ssh/", r"/\.git/", r"/\.aws/", r"\.pem$"]


def config():
    try:
        return json.load(open(CONFIG))
    except (OSError, ValueError):
        return {}


def log(kind, what):
    with open(LOG, "a") as f:
        f.write(f"{time.strftime('%d %b %H:%M')}  {kind:<9} {what}\n")


def risk(tool, inp, cfg):
    if tool == "Bash":
        cmd = inp.get("command", "")
        rules = RISKY_BASH + [(p, "on your own refuse list") for p in cfg.get("refuse_commands", [])]
        return next((why for pat, why in rules if re.search(pat, cmd)), None)
    path = inp.get("file_path") or inp.get("notebook_path") or inp.get("path") or ""
    if path and any(re.search(p, path, re.I) for p in RISKY_PATH + cfg.get("refuse_paths", [])):
        return "touching secrets or private files"
    if tool.startswith("mcp__") or tool in ("Artifact", "ArtifactData", "SendMessage", "RemoteTrigger"):
        if RISKY_TOOL.search(tool.split("__")[-1]) or inp.get("action") == "delete":
            return "an outward, paid or permanent action"
    if any(re.search(p, tool, re.I) for p in cfg.get("refuse_tools", [])):
        return "on your own refuse list"
    return None


def short(tool, inp):
    s = inp.get("command") or inp.get("file_path") or inp.get("url") or json.dumps(inp)[:120]
    return f"{tool}: {' '.join(str(s).split())[:160]}"


def last_reply(data):
    if data.get("last_assistant_message"):
        return str(data["last_assistant_message"])
    try:
        for line in reversed(open(data["transcript_path"]).read().splitlines()[-50:]):
            msg = json.loads(line).get("message", {})
            if msg.get("role") == "assistant":
                c = msg.get("content")
                return c if isinstance(c, str) else " ".join(b.get("text", "") for b in c if isinstance(b, dict))
    except (OSError, KeyError, ValueError):
        pass
    return ""


def owner():
    """Session that turned Away on ("" = all chats, e.g. from the menu bar moon)."""
    lines = open(FLAG).read().splitlines()
    return lines[1].strip() if len(lines) > 1 else ""


def stop_away():
    if os.path.exists(FLAG):
        os.remove(FLAG)
    try:
        os.kill(int(open(PIDFILE).read()), signal.SIGTERM)
        os.remove(PIDFILE)
    except (OSError, ValueError):
        pass
    for f in os.listdir(f"{HOME}/.claude"):
        if f.startswith("away.nudges."):
            os.remove(f"{HOME}/.claude/{f}")


def hook():
    if not os.path.exists(FLAG):
        return  # away mode off: normal behaviour
    data = json.load(sys.stdin)
    if owner() and data.get("session_id") != owner():
        return  # Away belongs to another chat; this one behaves as usual
    cfg = config()
    who = cfg.get("name", "The user")
    event, tool, inp = data.get("hook_event_name"), data.get("tool_name", ""), data.get("tool_input") or {}

    if event == "PreToolUse" and tool == "AskUserQuestion":
        answers = {q["question"]: q["options"][0]["label"] for q in inp.get("questions", []) if q.get("options")}
        log("ANSWERED", "; ".join(f"{k} -> {v}" for k, v in answers.items()))
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse", "permissionDecision": "allow",
            "permissionDecisionReason": f"Away mode: {who} is away, so the first (recommended) option was picked. Note it for the morning.",
            "updatedInput": {**inp, "answers": answers}}}))

    elif event == "PermissionRequest":
        why = risk(tool, inp, cfg)
        if why:
            log("REFUSED", f"({why}) {short(tool, inp)}")
            decision = {"behavior": "deny", "message":
                        f"Away mode: {who} is away and this looks like {why}, so it was refused. "
                        "Don't retry or work around it. Skip it, carry on with everything else, and "
                        "list it under 'Needs you' in your final summary."}
        else:
            log("APPROVED", short(tool, inp))
            decision = {"behavior": "allow"}
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PermissionRequest", "decision": decision}}))

    elif event == "Stop":
        if "AWAY: DONE" in last_reply(data):
            log("FINISHED", data.get("session_id", ""))
            if owner():  # that chat's job is done: switch off so nothing lingers
                stop_away()
                log("--- OFF", "(job done)")
            return
        count_file = f"{HOME}/.claude/away.nudges.{data.get('session_id', 'x')}"
        n = int(open(count_file).read()) + 1 if os.path.exists(count_file) else 1
        open(count_file, "w").write(str(n))
        if n > MAX_NUDGES:
            log("GAVE UP", f"stopped after {MAX_NUDGES} nudges, session {data.get('session_id', '')}")
            return
        log("NUDGED", f"#{n} session {data.get('session_id', '')}")
        print(json.dumps({"decision": "block", "reason":
            f"Away mode is on: {who} is away and can't answer. Don't wait or ask anything. "
            "Keep working toward the goal you were given. Anything that truly needs them (a password, a sign-in, "
            "a payment, a refused action), skip and add to a 'Needs you' list. When the goal is fully "
            "done, or everything left is on that list, write your summary with the 'Needs you' list "
            "and end with the exact line: AWAY: DONE"}))


def cli(cmd):
    if cmd == "on":
        # Run from a chat: Away covers only that chat. Run from the moon or Terminal: all chats.
        session = os.environ.get("CLAUDE_CODE_SESSION_ID", "")
        open(FLAG, "w").write(time.strftime("%d %b %H:%M") + "\n" + session)
        try:  # macOS only; elsewhere the user keeps the machine awake themselves
            p = subprocess.Popen(["caffeinate", "-dimsu"], start_new_session=True,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
            open(PIDFILE, "w").write(str(p.pid))
            awake = " The Mac stays awake (keep it plugged in)."
        except OSError:
            awake = " Keep the computer from sleeping."
        log("--- ON", "this chat" if session else "all chats")
        print(f"Away mode ON for {'this chat' if session else 'all chats'}." + awake)
    elif cmd == "off":
        stop_away()
        log("--- OFF", "")
        print("Away mode OFF. Pop-ups ask you again.\n")
        cli("report")
    elif cmd == "status":
        if os.path.exists(FLAG):
            since = open(FLAG).read().splitlines()[0]
            print(f"Away mode ON since {since}, for {'one chat' if owner() else 'all chats'}")
        else:
            print("Away mode OFF")
    elif cmd == "report":
        lines = open(LOG).read().splitlines() if os.path.exists(LOG) else []
        run = lines[max((i for i, l in enumerate(lines) if "--- ON" in l), default=0):]
        for kind in ("REFUSED", "ANSWERED", "APPROVED", "NUDGED", "GAVE UP"):
            hits = [l for l in run if f"  {kind}" in l]
            print(f"{kind.title()} ({len(hits)})")
            print("\n".join("  " + h for h in hits[-40:]) or "  none")
    else:
        print(__doc__)


if __name__ == "__main__":
    cli(sys.argv[1]) if len(sys.argv) > 1 else hook()
