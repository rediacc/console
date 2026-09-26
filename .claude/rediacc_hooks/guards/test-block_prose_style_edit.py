#!/usr/bin/env python3
"""Control harness for block_prose_style_edit.

BOTH DIRECTIONS, because a one-sided control is satisfiable by a broken hook: one that always blocks passes the positive cases, one that never blocks passes the negative ones. A prose linter is the worst case for a one-sided suite, because "flag everything" and "flag the right things" look identical from the block side alone.

WHY THIS FILE IS LOAD-BEARING RATHER THAN OPTIONAL. This guard declares
`OWN_SUITE = True`: it was never bash, so there is no golden to judge it
against. `test_guards_differential.py` REQUIRES a `test-<stem>.py` beside any guard carrying the sentinel, precisely so the sentinel cannot become the cheap way out of having evidence. `check-hook-integrity.sh` reads this file's existence too, crediting the guard with both directions under section B.

IT DRIVES THE LIVE GUARD THROUGH THE DISPATCHER, not the module's `run` directly and not a copy: `python3 dispatch.py block_prose_style_edit` is what `.claude/settings.json` ultimately invokes, and a suite that tested anything else would keep passing while the thing that actually runs went unchecked.

THE PATHS BELOW ARE RELATIVE AND DERIVED FROM THIS FILE. An absolute path under one operator's checkout is the exact failure CLAUDE.md's "Worktree Warning" names: in another worktree it would silently test a stale copy, or nothing.
"""

import json
import pathlib
import subprocess
import sys

DISPATCH = str(pathlib.Path(__file__).resolve().parents[1] / "dispatch.py")
GUARD_ARGV = [sys.executable, DISPATCH, "block_prose_style_edit"]

# Assembled rather than written, so this harness is not itself a tripwire for the rule it is testing. The guard reads the JSON payload, not this source, but the CI gate `check:ci-prose-style` DOES read this file's comments, and a literal violation here would be a finding in the gate's own corpus.
Y = "y" + "ou"
EYE = "I"

CASES = [
    # (name, tool_input, expect_blocked) ---- the block direction ------------------------------------------
    (
        "a markdown write addressing the reader",
        {"file_path": "docs/probe.md", "content": "Did %s run the tests?\n" % Y},
        True,
    ),
    (
        "an edit whose new_string uses the first person",
        {"file_path": "docs/probe.md", "new_string": "%s think this is wrong.\n" % EYE},
        True,
    ),
    (
        "a MultiEdit edits[] entry is read",
        {"file_path": "docs/probe.md", "edits": [{"new_string": "Did %s run it?" % Y}]},
        True,
    ),
    (
        "a python COMMENT is prose",
        {"file_path": "scripts/probe.py", "content": "x = 1  # Did %s run it?\n" % Y},
        True,
    ),
    (
        "a typescript // comment is prose",
        {"file_path": "scripts/probe.ts", "content": "// Did %s run it?\n" % Y},
        True,
    ),
    # ---- the allow direction, which is the half that keeps it usable ----
    (
        "the rewritten sentence passes",
        {"file_path": "docs/probe.md", "content": "Have the tests been run?\n"},
        False,
    ),
    (
        "the ownership exception passes",
        {"file_path": "docs/probe.md", "content": "M%s mistake; a fix is on the way.\n" % "y"},
        False,
    ),
    (
        "a fenced block is not prose",
        {"file_path": "docs/probe.md", "content": "```\nDid %s run it?\n```\n" % Y},
        False,
    ),
    (
        "an inline code span is not prose",
        {"file_path": "docs/probe.md", "content": "The flag is `%s` here.\n" % Y},
        False,
    ),
    (
        "a quotation is somebody else's words",
        {"file_path": "docs/probe.md", "content": "> Did %s run it?\n" % Y},
        False,
    ),
    (
        "a bad: exemplar carries its violation on purpose",
        {"file_path": "docs/probe.md", "content": "bad: Did %s run it?\n" % Y},
        False,
    ),
    (
        "the explicit marker exempts the line",
        {
            "file_path": "docs/probe.md",
            "content": "Did %s run it? <!-- style-ok -->\n" % Y,
        },
        False,
    ),
    (
        "a .sh file is out of scope entirely",
        {"file_path": "scripts/probe.sh", "content": "# Did %s run it?\n" % Y},
        False,
    ),
    (
        "packages/www is linted like every other tree",
        {"file_path": "packages/www/src/probe.md", "content": "Did %s run it?\n" % Y},
        True,
    ),
    (
        "a submodule path is excluded",
        {"file_path": "private/renet/probe.md", "content": "Did %s run it?\n" % Y},
        False,
    ),
    (
        "a path outside the repository is not this repository's prose",
        {"file_path": "/tmp/probe.md", "content": "Did %s run it?\n" % Y},
        False,
    ),
    (
        "a warning-only absolute does not block",
        {"file_path": "docs/probe.md", "content": "That will never work.\n"},
        False,
    ),
    (
        "a python STRING is not a comment",
        {"file_path": "scripts/probe.py", "content": "x = 'did %s run it'\n" % Y},
        False,
    ),
    (
        "the // inside a string literal is not a comment",
        {"file_path": "scripts/probe.ts", "content": 'const u = "https://x/%s";\n' % Y},
        False,
    ),
    # THE CWD PIN. Measured 2026-09-16: with `os.path.abspath` resolving against the INTERPRETER's directory, running this harness from /tmp reported "22 case(s), 0 blocked, 22 allowed / FAILURES: 6" -- six refusals silently became passes because every relative path landed outside the tree. The absolute form cannot be fooled by a working directory at all, so it pins the block from
    # the other side.
    (
        "an ABSOLUTE in-tree path blocks regardless of the working directory",
        {
            "file_path": str(pathlib.Path(__file__).resolve().parents[3] / "docs/probe.md"),
            "content": "Did %s run the tests?\n" % Y,
        },
        True,
    ),
    ("no file path at all", {"content": "Did %s run it?" % Y}, False),
    ("no content at all", {"file_path": "docs/probe.md"}, False),
    ("an empty payload", {}, False),
    # R19 EDGE_CASES, PLAN-prose-style-under-wrap.md: a fresh multi-line under-wrapped paragraph in a Write/content block is flagged (a), the same paragraph rewritten at full width passes (b), and a single-line Edit.new_string with no sibling context is NOT flagged, a documented limitation of a rule that needs 3+ lines to see the fixed-column signature at all (c).
    (
        "(a) a fresh hard-wrapped paragraph is flagged by R19",
        {
            "file_path": "docs/probe.md",
            "content": (
                "This paragraph is hard-wrapped at a narrow column width for no\n"
                "real reason and every line here sits close to the same length\n"
                "which is the classic fixed-width wrap signature to look for.\n"
            ),
        },
        True,
    ),
    (
        "(b) the same paragraph rewritten at full width passes",
        {
            "file_path": "docs/probe.md",
            "content": (
                "This paragraph is hard-wrapped at a narrow column width for no real reason "
                "and every line here sits close to the same length which is the classic "
                "fixed-width wrap signature to look for.\n"
            ),
        },
        False,
    ),
    (
        "(c) a single-line Edit.new_string is not flagged, R19 needs 3+ lines",
        {
            "file_path": "docs/probe.md",
            "new_string": "This paragraph is hard-wrapped at a narrow column width for no reason.",
        },
        False,
    ),
]


def run(tool_input):
    proc = subprocess.run(
        GUARD_ARGV,
        input=json.dumps({"tool_name": "Write", "tool_input": tool_input}),
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.returncode != 0, proc.stderr


fails = 0
blocked = 0
for name, payload, want in CASES:
    got, err = run(payload)
    blocked += got
    ok = got == want
    fails += not ok
    print(
        "%-56s want=%-9s got=%-9s %s"
        % (
            name,
            "BLOCKED" if want else "allowed",
            "BLOCKED" if got else "allowed",
            "ok" if ok else "*** FAIL ***",
        )
    )
    if not ok and err:
        print("    stderr: %s" % err.strip().splitlines()[:3])

print()
# ANTI-VACUITY. A suite where nothing blocked, or where everything did, has compared the guard against a constant. `test_every_guard_discriminates` makes the same argument for the differential's corpus; it is made here too because this harness is the ONLY control for a guard with no oracle.
if blocked == 0 or blocked == len(CASES):
    print(
        "*** FAIL *** %d of %d cases blocked: the guard answered the same way on every "
        "input, so this suite compared it against a constant." % (blocked, len(CASES)),
        file=sys.stderr,
    )
    fails += 1
print("%d case(s), %d blocked, %d allowed" % (len(CASES), blocked, len(CASES) - blocked))
print("FAILURES: %d" % fails)
sys.exit(1 if fails else 0)
