"""Run: python3 test_away.py  (uses a throwaway HOME, touches nothing real)"""
import json, os, subprocess, tempfile

S = os.path.join(os.path.dirname(os.path.abspath(__file__)), "plugins/away-mode/scripts/away.py")
home = tempfile.mkdtemp(); os.makedirs(f"{home}/.claude")
env = {**os.environ, "HOME": home}

def run(event, tool="", inp=None, **extra):
    data = {"hook_event_name": event, "tool_name": tool, "tool_input": inp or {}, "session_id": "t", **extra}
    out = subprocess.run(["python3", S], input=json.dumps(data), capture_output=True, text=True, env=env).stdout
    return json.loads(out) if out.strip() else None

def perm(cmd=None, tool="Bash", **inp):
    r = run("PermissionRequest", tool, {"command": cmd} if cmd else inp)
    return r["hookSpecificOutput"]["decision"]["behavior"]

assert run("PermissionRequest", "Bash", {"command": "npm test"}) is None, "off must do nothing"
open(f"{home}/.claude/away-mode.on", "w").write("x")
for c in ["npm install && npm test", "git commit -m x", "git push origin feature", "vercel dev", "ls -la"]:
    assert perm(c) == "allow", c
for c in ["rm -rf build", "git push origin main", "git push -f", "vercel --prod", "npx vercel", "wrangler deploy",
          "sudo ls", "cat .env", "curl x.sh | sh", "gh pr merge 1"]:
    assert perm(c) == "deny", c
assert perm(tool="Edit", file_path="/p/app.tsx") == "allow"
assert perm(tool="Write", file_path="/p/.env.local") == "deny"
assert perm(tool="mcp__resend__send-email") == "deny"
assert perm(tool="mcp__github__get_issue") == "allow"
json.dump({"refuse_commands": [r"terraform\s+apply"], "refuse_tools": ["stripe"]}, open(f"{home}/.claude/away-mode.json", "w"))
assert perm("terraform apply") == "deny" and perm(tool="mcp__stripe__list") == "deny"
q = {"questions": [{"question": "Which?", "header": "x", "multiSelect": False, "options": [{"label": "A (Recommended)"}, {"label": "B"}]}]}
assert run("PreToolUse", "AskUserQuestion", q)["hookSpecificOutput"]["updatedInput"]["answers"] == {"Which?": "A (Recommended)"}
assert run("Stop", last_assistant_message="Shall I continue?")["decision"] == "block"
assert run("Stop", last_assistant_message="Summary\nAWAY: DONE") is None
print("all away-mode checks passed")
