#!/usr/bin/env python3
"""Control harness for block-git-amend.sh.

Both directions, because a one-sided control is satisfiable by a broken hook: one that always blocks passes the positive cases, one that never blocks passes the negative ones.
"""

import json
import pathlib
import subprocess
import sys

# Derived from THIS file, never hard-coded: the hook lives beside the harness. An absolute path under one operator's checkout is the exact failure CLAUDE.md's "Worktree Warning" names -- in any other worktree, container or CI runner it would silently test a stale copy, or nothing at all, while still reporting success. THIS HARNESS SITS BESIDE ITS GUARD, which is what
# .ci/scripts/quality/check-hook-integrity.sh means by a dedicated test file: `test-<stem>.py` next to `<stem>.py` credits the guard with BOTH directions, and it is the only credit these four have because their block direction needs fixture work `test-hooks.sh`'s one-line `check` helper cannot express.
#
# THE GUARD IS A PYTHON MODULE NOW. W5 P7 ported it from a bash original that PLAN-retire-bash-oracles A3 later deleted, once the differential compared the two byte for byte and froze the result as a golden (tests/goldens/<stem>.jsonl). This harness drives the LIVE guard, which is the dispatcher, for the reason the cutover exists at all: a suite that kept driving the retired file would keep passing while the thing that actually runs went unchecked.
DISPATCH = str(pathlib.Path(__file__).resolve().parents[1] / "dispatch.py")
GUARD_ARGV = [sys.executable, DISPATCH, "block_git_amend"]
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
    # `<<-` strips leading TABS from the terminator, so bash closes the heredoc at the tab-indented delimiter and the NEXT line is ordinary shell. The scanner used to compare the raw line, never matched, and swallowed the rest of the command to EOF -- a real amend rode through. Reported on #552, reproduced, fixed.
    ("<<- tab-indented terminator does not hide an amend", "cat <<-EOF\n\tbody\n\tEOF\n" + A, True),
    ("<<- with quoted delimiter, same", "cat <<-'EOF'\n\tbody\n\tEOF\n" + A, True),
    # The other direction: `<<-` docs must still be allowed, or the fix above would just be "block everything with a heredoc", which passes the case above while breaking the tool.
    (
        "<<- heredoc body is still DOCS, allowed",
        "cat > R.md <<-'EOF'\n\tnever run " + A + "\n\tEOF",
        False,
    ),
    # A PLAIN `<<` terminator is NOT tab-stripped by bash, so a tab-indented line does not close it and the body legitimately continues. Pins that the fix did not over-strip.
    (
        "plain << is not tab-stripped, body still docs",
        "cat > R.md <<'EOF'\n\tnever run " + A + "\nEOF",
        False,
    ),
]


def run(cmd):
    p = subprocess.run(
        GUARD_ARGV,
        input=json.dumps({"tool_input": {"command": cmd}}),
        capture_output=True,
        text=True,
        check=False,
    )
    return p.returncode != 0


fails = 0
for name, cmd, want in CASES:
    got = run(cmd)
    ok = got == want
    fails += not ok
    print(
        "%-40s want=%-9s got=%-9s %s"
        % (
            name,
            "BLOCKED" if want else "allowed",
            "BLOCKED" if got else "allowed",
            "ok" if ok else "*** FAIL ***",
        )
    )

print()
print("FAILURES: %d" % fails)
sys.exit(1 if fails else 0)
