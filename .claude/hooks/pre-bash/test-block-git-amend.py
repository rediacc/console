#!/usr/bin/env python3
"""Control harness for block-git-amend.sh.

Both directions, because a one-sided control is satisfiable by a broken hook:
one that always blocks passes the positive cases, one that never blocks passes
the negative ones.
"""
import json
import subprocess
import sys

HOOK = "/home/muhammed/monorepo/console/.claude/hooks/pre-bash/block-git-amend.sh"
A = "git commit --" + "amend"  # assembled so this file is not itself a tripwire

CASES = [
    # (name, command, expect_blocked)
    ("bare amend", A, True),
    ("amend with flags", A + " --no-edit", True),
    ("amend after &&", "git add -A && " + A, True),
    ("short -a with amend", "git commit -a --" + "amend", True),
    ("INTERPRETER heredoc still blocked", "bash <<'EOF'\n" + A + "\nEOF", True),
    ("sh heredoc still blocked", "sh <<EOF\n" + A + "\nEOF", True),
    ("cat heredoc is DOCS, allowed", "cat > R.md <<'EOF'\nnever run " + A + "\nEOF", False),
    ("tee heredoc is DOCS, allowed", "tee R.md <<'EOF'\nnever run " + A + "\nEOF", False),
    ("ordinary commit allowed", "git commit -m 'fix: x'", False),
    ("unrelated command allowed", "ls -la", False),
]


def run(cmd):
    p = subprocess.run(
        ["bash", HOOK], input=json.dumps({"tool_input": {"command": cmd}}),
        capture_output=True, text=True, check=False,
    )
    return p.returncode != 0


fails = 0
for name, cmd, want in CASES:
    got = run(cmd)
    ok = got == want
    fails += not ok
    print("%-40s want=%-9s got=%-9s %s" % (
        name, "BLOCKED" if want else "allowed",
        "BLOCKED" if got else "allowed", "ok" if ok else "*** FAIL ***"))

print()
print("FAILURES: %d" % fails)
sys.exit(1 if fails else 0)
