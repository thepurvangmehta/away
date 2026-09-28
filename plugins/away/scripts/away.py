#!/usr/bin/env python3
"""Away mode: keeps Claude Code working while you sleep or step out.

  away.py on                   turn it on (also keeps the computer awake)
  away.py off                  turn it off, show the morning report
  away.py status               is it on, and at which level?
  away.py report               what it approved, refused and answered
  away.py config               show your settings
  away.py set level careful    careful | balanced | hands-off
  away.py set name Sam         what to call you in Claude's notes
  away.py add refuse_commands "regex"   also refuse_paths, refuse_tools

With no arguments it runs as the Claude Code hook (see hooks/hooks.json):
  PreToolUse (every tool)        -> refuse risky things ("Needs you") before they run, in every mode,
                                    including Bypass, where no permission prompt ever appears
  PreToolUse on AskUserQuestion  -> blocked; Claude goes with the recommended option and notes it
  PreToolUse on browser pages    -> blocked; the app's site pop-up can't be answered unattended
  PreToolUse on ExitPlanMode     -> blocked; the plan goes on the Needs you list
  PermissionRequest              -> allow the normal work that would otherwise wait for a click
  Stop                           -> send Claude back to work until it says AWAY: DONE
When away mode is off it does nothing, so everything behaves as usual.
Your deny rules in settings.json still win over this hook.

Settings live in ~/.claude/away.json:
  {"level": "balanced", "name": "Sam", "refuse_commands": [...], "refuse_paths": [...], "refuse_tools": [...]}
"""
import json, os, re, shlex, signal, subprocess, sys, time

HOME = os.path.expanduser("~")
FLAG = f"{HOME}/.claude/away.on"
LOG = f"{HOME}/.claude/away.log"
PIDFILE = f"{HOME}/.claude/away.caffeinate"
CONFIG = f"{HOME}/.claude/away.json"
MAX_NUDGES = 30  # ponytail: per-session cap so an impossible goal can't loop all night
SHELLS = ("Bash", "PowerShell")  # PowerShell is Claude Code's shell tool on Windows

LEVELS = {
    "careful": "for client or company code: also waits on installs, any push, database commands and "
               "writing outside the project",
    "balanced": "the default: waits on deleting, deploying, pushing to main, secrets, sending and paid tools",
    "hands-off": "for your own side projects: only waits on what can't be undone (deleting outside the project, "
                 "force push or push to main, deploying, secrets, sending, payments)",
}

G = r"\bgit\b[^|;&\n]*\s"  # "git" plus any options before the subcommand, e.g. "git -C some/folder push"

# Refused at every level: can't be undone, or leaves the machine.
ALWAYS = [
    (G + r"push\b[^|;&\n]*(\s-f\b|--force)", "force-pushing"),
    (G + r"push\b[^|;&\n]*\b(main|master)\b", "pushing to main"),
    (G + r"(reset\s+--hard|clean\s+-\w*f|branch\s+-D|filter-branch|filter-repo)", "throwing away git work"),
    (G + r"(config\b.*user\.|commit\b.*--author)", "changing git identity"),
    (r"\b(vercel|netlify)\b(?!\s+(dev|logs|ls|list|whoami|inspect|link|env\s+pull)\b)", "deploying"),
    (r"\bfirebase\s+deploy|\bwrangler\s+(deploy|publish|pages\s+deploy|secret|delete)", "deploying"),
    (r"\bgh\s+(pr\s+merge|repo\s+(delete|edit)|release\s+create|secret)", "publishing on GitHub"),
    (r"\b(npm|pnpm|yarn|bun)\s+publish\b|\btwine\s+upload\b|\bcargo\s+publish\b", "publishing a package"),
    (r"\bsudo\b|\bshutdown\b|\breboot\b|\bdiskutil\b|\bcsrutil\b|\bdefaults\s+write\b", "changing the computer itself"),
    (r"\bFormat-Volume\b|\bSet-ExecutionPolicy\b|\breg(\.exe)?\s+(add|delete)\b|\bbcdedit\b|-Verb\s+RunAs"
     r"|\b(Stop|Restart)-Computer\b", "changing the computer itself"),
    (r"\.env\b|keychain|\bsecurity\s+find-|\bcmdkey\b", "touching secrets"),
    (r"\b(curl|wget)\b.*\|\s*(ba|z)?sh\b", "running a script from the internet"),
    (r"\b(iwr|irm|Invoke-WebRequest|Invoke-RestMethod)\b.*\|\s*(iex|Invoke-Expression)\b"
     r"|\biex\s*\(\s*(iwr|irm|New-Object)", "running a script from the internet"),
    (r"\bsendmail\b|\bosascript\b|\bSend-MailMessage\b", "sending a message"),
]
# Balanced and careful: any recursive or forced delete, even inside the project.
DELETES = [
    (r"\brm\s+(-\w*[rRf]|--recursive|--force)", "deleting files"),
    (r"\brmdir\b|\bshred\b|\bsrm\b", "deleting files"),
    (r"\bRemove-Item\b.*-(Recurse|Force)|\b(rd|del|erase)\s+/[sq]\b", "deleting files"),
]
# Careful only.
CAREFUL = [
    (r"\b(npm|pnpm|yarn|bun)\s+(install|i|add|ci)\b|\bpip3?\s+install\b|\b(brew|cargo|gem|go)\s+install\b"
     r"|\bwinget\s+install\b|\bchoco\s+install\b", "installing software"),
    (G + r"push\b", "pushing to GitHub"),
    (r"\b(psql|mysql|mongosh?|sqlite3|redis-cli)\b|\bprisma\s+(migrate|db)\b|\bdrizzle-kit\s+(push|migrate)\b"
     r"|\bsupabase\s+db\b", "changing a database"),
]
# MCP / app tools whose name suggests an outward, paid or permanent action.
RISKY_TOOL = re.compile(
    r"send|delete|remove|publish|deploy|post|merge|purchase|pay|transfer|"
    r"archive|share|invite|comment|reply|secret|generate_|upscale",
    re.I,
)
RISKY_PATH = [r"(^|/)\.env", r"/\.ssh/", r"/\.git/", r"/\.aws/", r"\.pem$"]
DELETE_CMD = re.compile(r"(?:^|[;&|]\s*|\s)(rm|rmdir|Remove-Item|rd|del|erase)\s+([^;&|]*)")


def config():
    try:
        return json.load(open(CONFIG))
    except (OSError, ValueError):
        return {}


def level(cfg):
    lv = cfg.get("level", "balanced")
    return lv if lv in LEVELS else "balanced"


def log(kind, what):
    with open(LOG, "a") as f:
        f.write(f"{time.strftime('%d %b %H:%M')}  {kind:<9} {what}\n")


def inside(path, cwd):
    """Is this path inside the project folder? Anything unclear counts as outside."""
    if not cwd or not path:
        return False
    p = os.path.normpath(os.path.join(cwd, os.path.expanduser(path))).replace("\\", "/")
    root = os.path.normpath(cwd).replace("\\", "/").rstrip("/")
    return bool(root) and (p == root or p.startswith(root + "/"))


def deletes_outside(cmd, cwd):
    for m in DELETE_CMD.finditer(cmd):
        try:
            args = shlex.split(m.group(2), posix=True)
        except ValueError:
            return True
        targets = [a for a in args if not a.startswith("-") and not re.fullmatch(r"/[a-zA-Z]", a)]  # /s /q flags
        for t in targets:
            # the home folder, the whole disk, or a $VARIABLE we can't see into always count as outside
            if t in ("/", "~", "~/") or "$" in t or "%" in t or not inside(t, cwd):
                return True
    return False


def risk(tool, inp, cfg, cwd=""):
    lv = level(cfg)
    if tool in SHELLS:
        cmd = inp.get("command", "")
        rules = ALWAYS + (DELETES if lv != "hands-off" else []) + (CAREFUL if lv == "careful" else [])
        rules += [(p, "on your own refuse list") for p in cfg.get("refuse_commands", [])]
        why = next((why for pat, why in rules if re.search(pat, cmd, re.I if tool == "PowerShell" else 0)), None)
        if not why and lv == "hands-off" and deletes_outside(cmd, cwd):
            why = "deleting files outside the project"
        return why
    path = (inp.get("file_path") or inp.get("notebook_path") or inp.get("path") or "").replace("\\", "/")
    if path and any(re.search(p, path, re.I) for p in RISKY_PATH + cfg.get("refuse_paths", [])):
        return "touching secrets or private files"
    if lv == "careful" and tool in ("Write", "Edit", "NotebookEdit") and path and cwd and not inside(path, cwd):
        return "writing outside the project"
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


BROWSER = re.compile(r"Claude_Browser__(navigate|preview_start|tabs_create)|claude-in-chrome__(navigate|tabs_create)")


def deny(event, reason):
    print(json.dumps({"hookSpecificOutput": {"hookEventName": event, "permissionDecision": "deny",
                                             "permissionDecisionReason": reason}}))


def refused_text(who, why):
    return (f"Away mode: {who} is away and this looks like {why}, so it was refused. "
            "Don't retry or work around it. Skip it, carry on with everything else, and "
            "list it under 'Needs you' in your final summary.")


def hook():
    if not os.path.exists(FLAG):
        return  # away mode off: normal behaviour
    data = json.load(sys.stdin)
    if owner() and data.get("session_id") != owner():
        return  # Away belongs to another chat; this one behaves as usual
    cfg = config()
    who = cfg.get("name", "The user")
    event, tool, inp = data.get("hook_event_name"), data.get("tool_name", ""), data.get("tool_input") or {}
    cwd = data.get("cwd", "")

    if event == "PreToolUse" and tool == "AskUserQuestion":
        # Blocked, not auto-answered: the desktop app still shows the question card and waits
        # even when a hook supplies answers (found in the 28 Sep live test).
        answers = {q["question"]: q["options"][0]["label"] for q in inp.get("questions", []) if q.get("options")}
        log("ANSWERED", "; ".join(f"{k} -> {v}" for k, v in answers.items()))
        picks = "; ".join(f'"{k}" -> "{v}"' for k, v in answers.items())
        deny("PreToolUse", f"Away mode: {who} is away and can't answer questions. Don't ask. "
             f"Go with the recommended option yourself ({picks}), list it under 'Answered for you' "
             "in your final summary so they can change it, and keep working.")

    elif event == "PreToolUse" and tool == "ExitPlanMode":
        # The plan-approval card ignores hook answers (anthropics/claude-code#97656), and approving a plan is theirs to do.
        log("REFUSED", "(approving a plan is their call) ExitPlanMode")
        deny("PreToolUse", f"Away mode: {who} is away and can't approve a plan. Don't wait for approval. "
             "Put the finished plan under 'Needs you' in your final summary, then end with AWAY: DONE.")

    elif event == "PreToolUse" and BROWSER.search(tool):
        # The app's own "allow this site?" pop-up can't be answered by a hook and would wait all night.
        log("REFUSED", f"(opening a web page needs their OK in the app) {short(tool, inp)}")
        deny("PreToolUse", f"Away mode: {who} is away. Opening pages in the browser can trigger the app's "
             "'allow this site?' pop-up, which nobody can answer tonight. Don't use the browser. "
             "Read the page with WebFetch instead if that's enough, otherwise put it under 'Needs you' and move on.")

    elif event == "PreToolUse":
        # Checked before every action, so the risky list holds in Bypass mode too, where nothing ever prompts.
        why = risk(tool, inp, cfg, cwd)
        if why:
            log("REFUSED", f"({why}) {short(tool, inp)}")
            deny("PreToolUse", refused_text(who, why))

    elif event == "PermissionRequest":  # risky ones never get here: PreToolUse already refused them
        why = risk(tool, inp, cfg, cwd)
        if why:
            log("REFUSED", f"({why}) {short(tool, inp)}")
            decision = {"behavior": "deny", "message": refused_text(who, why)}
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


def keep_awake():
    """Start something that keeps the computer awake; return a sentence for the user."""
    quiet = dict(stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
    if sys.platform == "win32":
        p = subprocess.Popen([sys.executable, os.path.abspath(__file__), "_stay_awake"],
                             creationflags=0x00000008 | 0x00000200, **quiet)  # detached, own process group
        what = " The PC stays awake (keep it plugged in)."
    else:
        cmd = ["caffeinate", "-dimsu"] if sys.platform == "darwin" else \
              ["systemd-inhibit", "--what=idle:sleep", "--why=Away mode", "sleep", "infinity"]
        try:
            p = subprocess.Popen(cmd, start_new_session=True, **quiet)
        except OSError:
            return " Keep the computer from sleeping."
        what = " The Mac stays awake (keep it plugged in)." if sys.platform == "darwin" else \
               " The computer stays awake (keep it plugged in)."
    open(PIDFILE, "w").write(str(p.pid))
    return what


def save(cfg):
    json.dump(cfg, open(CONFIG, "w"), indent=2)


def cli(args):
    cmd = args[0]
    if cmd == "on":
        # Run from a chat: Away covers only that chat. Run from the moon or Terminal: all chats.
        session = os.environ.get("CLAUDE_CODE_SESSION_ID", "")
        open(FLAG, "w").write(time.strftime("%d %b %H:%M") + "\n" + session)
        awake = keep_awake()
        lv = level(config())
        log("--- ON", f"{'this chat' if session else 'all chats'}, {lv}")
        print(f"Away mode ON for {'this chat' if session else 'all chats'}, level {lv}." + awake)
    elif cmd == "off":
        stop_away()
        log("--- OFF", "")
        print("Away mode OFF. Pop-ups ask you again.\n")
        cli(["report"])
    elif cmd == "status":
        lv = level(config())
        if os.path.exists(FLAG):
            since = open(FLAG).read().splitlines()[0]
            print(f"Away mode ON since {since}, for {'one chat' if owner() else 'all chats'}, level {lv}")
        else:
            print(f"Away mode OFF (level when on: {lv})")
    elif cmd == "report":
        lines = open(LOG).read().splitlines() if os.path.exists(LOG) else []
        run = lines[max((i for i, l in enumerate(lines) if "--- ON" in l), default=0):]
        for kind in ("REFUSED", "ANSWERED", "APPROVED", "NUDGED", "GAVE UP"):
            hits = [l for l in run if f"  {kind}" in l]
            print(f"{kind.title()} ({len(hits)})")
            print("\n".join("  " + h for h in hits[-40:]) or "  none")
    elif cmd == "config":
        cfg = config()
        print(f"Level: {level(cfg)} ({LEVELS[level(cfg)]})")
        print(f"Name: {cfg.get('name', '(not set)')}")
        for k in ("refuse_commands", "refuse_paths", "refuse_tools"):
            print(f"{k}: {', '.join(cfg.get(k, [])) or 'none'}")
    elif cmd == "set" and len(args) == 3 and args[1] in ("level", "name"):
        if args[1] == "level" and args[2] not in LEVELS:
            sys.exit(f"Level must be one of: {', '.join(LEVELS)}")
        cfg = config(); cfg[args[1]] = args[2]; save(cfg)
        print(f"Saved {args[1]}: {args[2]}")
    elif cmd == "add" and len(args) == 3 and args[1] in ("refuse_commands", "refuse_paths", "refuse_tools"):
        re.compile(args[2])  # fail loudly on a broken pattern instead of silently never matching
        cfg = config(); cfg.setdefault(args[1], [])
        if args[2] not in cfg[args[1]]:
            cfg[args[1]].append(args[2])
        save(cfg)
        print(f"Added to {args[1]}: {args[2]}")
    elif cmd == "_stay_awake" and sys.platform == "win32":
        import ctypes  # ES_CONTINUOUS | ES_SYSTEM_REQUIRED, held until this process is stopped
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001)
        while True:
            time.sleep(3600)
    else:
        print(__doc__)


if __name__ == "__main__":
    cli(sys.argv[1:]) if len(sys.argv) > 1 else hook()
