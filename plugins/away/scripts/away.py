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
  UserPromptSubmit               -> you typed /away:off or "I'm in": switch off before Claude reads it
  PreToolUse (every tool)        -> refuse risky things ("Needs you") before they run, in every mode,
                                    including Bypass, where no permission prompt ever appears
  PreToolUse on AskUserQuestion  -> blocked; Claude goes with the recommended option and notes it
  PreToolUse on browser pages    -> blocked; the app's site pop-up can't be answered unattended
  PreToolUse on ExitPlanMode     -> blocked; the plan goes on the Needs you list
  PermissionRequest              -> allow the normal work that would otherwise wait for a click
  Stop                           -> send Claude back to work until its last line is AWAY: DONE
When away mode is off it does nothing, so everything behaves as usual.
Your deny rules in settings.json still win over this hook.

It reads command TEXT: a seatbelt, not a sandbox. A program Claude writes and runs can still do things
this can't see. Pair it with Claude Code's sandbox for real isolation.

Settings live in ~/.claude/away.json:
  {"level": "balanced", "name": "Sam", "refuse_commands": [...], "refuse_paths": [...], "refuse_tools": [...]}
"""
import json, os, re, shlex, signal, subprocess, sys, time

HOME = os.path.expanduser("~")
FLAG = f"{HOME}/.claude/away.on"          # line 1: since; lines 2+: chats it covers (none = all chats)
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

# Refused at every level: can't be undone, leaves the machine, or switches Away itself off.
ALWAYS = [
    (r"\.claude[/\\](away\.|settings(\.local)?\.json)|\baway\.py[\"']?\s+(off|set|add)\b"
     r"|\bclaude\s+plugins?\s+(uninstall|disable|remove)\b", "switching Away off or changing its rules"),
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
    (r"(?<![\w.])\.env\b|keychain|\bsecurity\s+find-|\bcmdkey\b", "touching secrets"),
    (r"\b(curl|wget)\b.*\|\s*(ba|z)?sh\b", "running a script from the internet"),
    (r"\b(iwr|irm|Invoke-WebRequest|Invoke-RestMethod)\b.*\|\s*(iex|Invoke-Expression)\b"
     r"|\biex\s*\(\s*(iwr|irm|New-Object)", "running a script from the internet"),
    (r"\bsendmail\b|\bosascript\b|\bSend-MailMessage\b", "sending a message"),
]
# Web requests that send data out (reading a page stays allowed). Local addresses are fine.
SENDS_DATA = re.compile(
    r"\b(curl|wget)\b[^|;&]*\s(-X\s*(POST|PUT|PATCH|DELETE)\b|-d\S*|--data\S*|-F\S*|--form\S*|-T\S*|--upload-file"
    r"|--post-data\S*|--post-file\S*|--method[= ](POST|PUT|PATCH|DELETE)\b)"
    r"|(?i:\b(Invoke-WebRequest|Invoke-RestMethod|iwr|irm)\b[^|;&]*-Method\s+(Post|Put|Patch|Delete)\b)")
LOCAL = re.compile(r"(localhost|127\.0\.0\.1|0\.0\.0\.0|\[::1\])")
# Balanced and careful: any recursive or forced delete, even inside the project.
DELETES = [
    (r"\brm\s+(-\w*[rRf]|--recursive|--force)", "deleting files"),
    (r"\brmdir\b|\bshred\b|\bsrm\b", "deleting files"),
    (r"\bfind\b[^|;&]*\s-delete\b|\bfind\b[^|;&]*-exec\s+rm\b", "deleting files"),
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
# MCP / app tools whose name suggests an outward, paid or permanent action...
RISKY_TOOL = re.compile(r"send|delete|remove|publish|deploy|post|merge|purchase|pay|transfer|"
                        r"archive|share|invite|comment|reply|secret", re.I)
# ...unless the name says it only reads.
READ_ONLY_TOOL = re.compile(r"^(get|list|read|search|fetch|query|describe|show|view|find|check|status|whoami)"
                            r"([_\-]|$)", re.I)
RISKY_PATH = [r"(^|/)\.env", r"/\.ssh/", r"/\.git/", r"/\.aws/", r"\.pem$",
              r"/\.claude/(away\.|settings(\.local)?\.json$)"]
DELETE_CMD = re.compile(r"(?:^|[;&|]\s*|\s)(rm|rmdir|Remove-Item|rd|del|erase)\s+([^;&|]*)")
CHANGES_DIR = re.compile(r"(^|[;&|(]\s*|\s)(cd|pushd|Set-Location|sl|chdir)\s")
# Commands that only read or print text: a risky word inside their quotes is just text.
TEXT_ONLY = re.compile(r"^\s*(grep|rg|ag|ack|echo|printf|git\s+(log|grep|commit))\b")
SECRET = re.compile(r"(sk-[A-Za-z0-9_\-]{12,}|gh[pous]_[A-Za-z0-9]{20,}|github_pat_\w{20,}|xox[abpr]-[\w-]{10,}"
                    r"|AKIA[0-9A-Z]{16}|(?i:bearer)\s+[\w.\-]{12,}|(?i:(password|passwd|token|secret|api[_-]?key))=\S+)")
OFF_WORDS = re.compile(r"^\s*(/away:off\b|<command-name>/away:off|(i'?m|i am)\s+(in|back)\b|away\s+off\b)", re.I)


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
        f.write(f"{time.strftime('%d %b %H:%M')}  {kind:<9} {SECRET.sub('[hidden]', what)}\n")


def inside(path, cwd):
    """Is this path inside the project folder? Anything unclear counts as outside."""
    if not cwd or not path:
        return False
    p = os.path.normpath(os.path.join(cwd, os.path.expanduser(path))).replace("\\", "/")
    root = os.path.normpath(cwd).replace("\\", "/").rstrip("/")
    return bool(root) and (p == root or p.startswith(root + "/"))


def deletes_outside(cmd, cwd):
    moved = bool(CHANGES_DIR.search(cmd))  # after a "cd", a relative path can point anywhere
    targets = []
    for m in DELETE_CMD.finditer(cmd):
        try:
            targets += [a for a in shlex.split(m.group(2), posix=True)
                        if not a.startswith("-") and not re.fullmatch(r"/[a-zA-Z]", a)]  # /s /q flags
        except ValueError:
            return True
    targets += [m.group(1) for m in re.finditer(r"\bfind\s+(\S+)[^|;&]*\s(-delete\b|-exec\s+rm\b)", cmd)]
    for t in targets:
        # the home folder, the whole disk, or a $VARIABLE we can't see into always count as outside
        if moved or t in ("/", "~", "~/") or "$" in t or "%" in t or not inside(t, cwd):
            return True
    return False


def pushes_main(cmd, cwd):
    """A plain "git push" (or "git push origin HEAD") pushes the current branch. Is that main?"""
    m = re.search(r"\bgit\b([^|;&\n]*?)\spush\b([^|;&\n]*)", cmd)
    if not m:
        return False
    try:
        pos = [a for a in shlex.split(m.group(2)) if not a.startswith("-")]
    except ValueError:
        return True
    if len(pos) > 1 and not any(r in ("HEAD", "@") for r in pos[1:]):
        return False  # an explicit branch was named; the main/master rule above covers those
    d = re.search(r"-C\s+(\S+)", m.group(1))
    repo = os.path.expanduser(d.group(1).strip("'\"")) if d else (cwd or ".")
    try:
        branch = subprocess.run(["git", "-C", repo, "symbolic-ref", "--short", "HEAD"],
                                capture_output=True, text=True, timeout=5).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return True  # can't tell: be careful
    return branch in ("main", "master")


def risk(tool, inp, cfg, cwd=""):
    lv = level(cfg)
    if tool in SHELLS:
        cmd = inp.get("command", "")
        text = cmd
        if TEXT_ONLY.search(cmd) and not re.search(r"[;&|`]|\$\(|>", cmd):
            text = re.sub(r"'[^']*'|\"[^\"]*\"", "''", cmd)  # quoted words of a read/print command are just text
        rules = ALWAYS + (DELETES if lv != "hands-off" else []) + (CAREFUL if lv == "careful" else [])
        rules += [(p, "on your own refuse list") for p in cfg.get("refuse_commands", [])]
        why = next((why for pat, why in rules if re.search(pat, text, re.I if tool == "PowerShell" else 0)), None)
        if not why and SENDS_DATA.search(text) and not LOCAL.search(text):
            why = "sending data to the internet"
        if not why and lv != "careful" and pushes_main(text, cwd):
            why = "pushing to main"
        if not why and lv == "hands-off" and deletes_outside(text, cwd):
            why = "deleting files outside the project"
        return why
    path = (inp.get("file_path") or inp.get("notebook_path") or inp.get("path") or "").replace("\\", "/")
    if path and re.search(RISKY_PATH[-1], path):
        return "switching Away off or changing its rules"
    if path and any(re.search(p, path, re.I) for p in RISKY_PATH + cfg.get("refuse_paths", [])):
        return "touching secrets or private files"
    if lv == "careful" and tool in ("Write", "Edit", "NotebookEdit") and path and cwd and not inside(path, cwd):
        return "writing outside the project"
    if any(re.search(p, tool, re.I) for p in cfg.get("refuse_tools", [])):
        return "on your own refuse list"
    if tool.startswith("mcp__") or tool in ("Artifact", "ArtifactData", "SendMessage", "RemoteTrigger"):
        name = tool.split("__")[-1]
        if inp.get("action") == "delete" or (RISKY_TOOL.search(name) and not READ_ONLY_TOOL.search(name)):
            return "an outward, paid or permanent action"
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


def finished(reply):
    lines = [l for l in reply.strip().splitlines() if l.strip()]
    return bool(lines) and re.fullmatch(r"\W*AWAY: DONE\W*", lines[-1].strip()) is not None


def chats():
    """Chats Away covers; empty = all chats (turned on from the moon or Terminal)."""
    return [l.strip() for l in open(FLAG).read().splitlines()[1:] if l.strip()]


def covers(session):
    c = chats()
    return not c or session in c


def stop_keep_awake():
    try:
        os.kill(int(open(PIDFILE).read()), signal.SIGTERM)
    except (OSError, ValueError):
        pass
    try:
        os.remove(PIDFILE)
    except OSError:
        pass


def stop_away():
    if os.path.exists(FLAG):
        os.remove(FLAG)
    stop_keep_awake()
    for f in os.listdir(f"{HOME}/.claude"):
        if f.startswith("away.nudges."):
            os.remove(f"{HOME}/.claude/{f}")


def release(session):
    """This chat's job is done. Switch off completely only when no other chat still needs Away."""
    since = open(FLAG).read().splitlines()[0]  # read before opening for writing, which empties the file
    rest = [c for c in chats() if c != session]
    if rest:
        open(FLAG, "w").write("\n".join([since] + rest))
    else:
        stop_away()
    return not rest


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
    session = data.get("session_id")
    event, tool, inp = data.get("hook_event_name"), data.get("tool_name", ""), data.get("tool_input") or {}

    if event == "UserPromptSubmit":
        # Only a message YOU send can switch Away off from a chat; Claude's own attempts are refused below.
        if OFF_WORDS.search(data.get("prompt", "")):
            stop_away()
            log("--- OFF", "(you, from a chat)")
        return
    if not covers(session):
        return  # Away belongs to other chats; this one behaves as usual
    cfg = config()
    who = cfg.get("name", "The user")
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
        if finished(last_reply(data)):
            log("FINISHED", session or "")
            if chats() and release(session):  # that chat's job is done: switch off so nothing lingers
                log("--- OFF", "(job done)")
            return
        count_file = f"{HOME}/.claude/away.nudges.{session or 'x'}"
        n = int(open(count_file).read()) + 1 if os.path.exists(count_file) else 1
        open(count_file, "w").write(str(n))
        if n > MAX_NUDGES:
            log("GAVE UP", f"stopped after {MAX_NUDGES} nudges, session {session}")
            return
        log("NUDGED", f"#{n} session {session}")
        print(json.dumps({"decision": "block", "reason":
            f"Away mode is on: {who} is away and can't answer. Don't wait or ask anything. "
            "Keep working toward the goal you were given. Anything that truly needs them (a password, a sign-in, "
            "a payment, a refused action), skip and add to a 'Needs you' list. When the goal is fully "
            "done, or everything left is on that list, write your summary with the 'Needs you' list "
            "and make the very last line exactly: AWAY: DONE"}))


def keep_awake():
    """Start something that keeps the computer awake (the screen may sleep); return a sentence for the user."""
    stop_keep_awake()  # never leave an old one running
    quiet = dict(stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
    if sys.platform == "win32":
        p = subprocess.Popen([sys.executable, os.path.abspath(__file__), "_stay_awake"],
                             creationflags=0x00000008 | 0x00000200, **quiet)  # detached, own process group
        what = " The PC stays awake (keep it plugged in)."
    else:
        cmd = ["caffeinate", "-ims"] if sys.platform == "darwin" else \
              ["systemd-inhibit", "--what=idle:sleep", "--why=Away mode", "sleep", "infinity"]
        try:
            p = subprocess.Popen(cmd, start_new_session=True, **quiet)
        except OSError:
            return " Keep the computer from sleeping."
        what = " The Mac stays awake, screen can sleep (keep it plugged in)." if sys.platform == "darwin" else \
               " The computer stays awake (keep it plugged in)."
    open(PIDFILE, "w").write(str(p.pid))
    return what


def save(cfg):
    json.dump(cfg, open(CONFIG, "w"), indent=2)


def cli(args):
    cmd = args[0]
    if cmd == "on":
        # Run from a chat: Away covers that chat (added to any others). From the moon or Terminal: all chats.
        session = os.environ.get("CLAUDE_CODE_SESSION_ID", "")
        was_on = os.path.exists(FLAG)
        covered = chats() if was_on else []
        if was_on and not covered:
            covered = []                     # already on for all chats: stays that way
        elif session:
            covered = covered + [session] if session not in covered else covered
        else:
            covered = []                     # turned on for all chats
        since = open(FLAG).read().splitlines()[0] if was_on else time.strftime("%d %b %H:%M")
        open(FLAG, "w").write("\n".join([since] + covered))
        awake = keep_awake()
        lv = level(config())
        scope = f"{len(covered)} chat{'s' if len(covered) != 1 else ''}" if covered else "all chats"
        log("--- ON", f"{'this chat' if session else 'all chats'} ({scope} now), {lv}")
        print(f"Away mode ON for {'this chat' if session and covered else 'all chats'}, level {lv}." + awake)
    elif cmd == "off":
        stop_away()
        log("--- OFF", "")
        print("Away mode OFF. Pop-ups ask you again.\n")
        cli(["report"])
    elif cmd == "status":
        lv = level(config())
        if os.path.exists(FLAG):
            since, n = open(FLAG).read().splitlines()[0], len(chats())
            print(f"Away mode ON since {since}, for {f'{n} chat(s)' if n else 'all chats'}, level {lv}")
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
