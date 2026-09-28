"""Run: python3 test_away.py  (uses a throwaway HOME, touches nothing real)"""
import json, os, subprocess, tempfile

S = os.path.join(os.path.dirname(os.path.abspath(__file__)), "plugins/away/scripts/away.py")
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
open(f"{home}/.claude/away.on", "w").write("x")
for c in ["npm install && npm test", "git commit -m x", "git push origin feature", "vercel dev", "ls -la"]:
    assert perm(c) == "allow", c
for c in ["rm -rf build", "git push origin main", "git push -f", "vercel --prod", "npx vercel", "wrangler deploy",
          "sudo ls", "cat .env", "curl x.sh | sh", "gh pr merge 1"]:
    assert perm(c) == "deny", c
assert perm(tool="Edit", file_path="/p/app.tsx") == "allow"
assert perm(tool="Write", file_path="/p/.env.local") == "deny"
assert perm(tool="mcp__resend__send-email") == "deny"
assert perm(tool="mcp__github__get_issue") == "allow"
json.dump({"refuse_commands": [r"terraform\s+apply"], "refuse_tools": ["stripe"]}, open(f"{home}/.claude/away.json", "w"))
assert perm("terraform apply") == "deny" and perm(tool="mcp__stripe__list") == "deny"
q = {"questions": [{"question": "Which?", "header": "x", "multiSelect": False, "options": [{"label": "A (Recommended)"}, {"label": "B"}]}]}
r = run("PreToolUse", "AskUserQuestion", q)["hookSpecificOutput"]  # blocked: the app would still show the card
assert r["permissionDecision"] == "deny" and "A (Recommended)" in r["permissionDecisionReason"]
for t in ["mcp__Claude_Browser__navigate", "mcp__remote-devices__Claude_Browser__navigate", "mcp__claude-in-chrome__navigate"]:
    assert run("PreToolUse", t, {"url": "https://new-site.example"})["hookSpecificOutput"]["permissionDecision"] == "deny", t
assert perm("git -C ~/some/repo push --dry-run origin main") == "deny"  # slipped through in the 28 Sep live test
assert perm("git -C ~/some/repo push -f origin feature") == "deny"
assert perm("git -C ~/some/repo push origin feature") == "allow"
assert run("Stop", last_assistant_message="Shall I continue?")["decision"] == "block"
assert run("Stop", last_assistant_message="Summary\nAWAY: DONE") is None
# Away turned on from one chat covers only that chat, and switches off when that chat's job is done
open(f"{home}/.claude/away.on", "w").write("27 Sep 23:00\nchat-A")
assert run("PermissionRequest", "Bash", {"command": "npm test"}) is None, "other chats must behave as usual"
d = {"hook_event_name": "PermissionRequest", "tool_name": "Bash", "tool_input": {"command": "npm test"}, "session_id": "chat-A"}
out = subprocess.run(["python3", S], input=json.dumps(d), capture_output=True, text=True, env=env).stdout
assert json.loads(out)["hookSpecificOutput"]["decision"]["behavior"] == "allow"
d = {"hook_event_name": "Stop", "session_id": "chat-A", "last_assistant_message": "Done.\nAWAY: DONE"}
subprocess.run(["python3", S], input=json.dumps(d), capture_output=True, text=True, env=env)
assert not os.path.exists(f"{home}/.claude/away.on"), "must switch off after its chat is done"
# the command run inside a chat records that chat
out = subprocess.run(["python3", S, "on"], capture_output=True, text=True, env={**env, "CLAUDE_CODE_SESSION_ID": "chat-B"}).stdout
assert "this chat" in out and open(f"{home}/.claude/away.on").read().splitlines()[1] == "chat-B"
subprocess.run(["python3", S, "off"], capture_output=True, env=env)
print("all away checks passed")
