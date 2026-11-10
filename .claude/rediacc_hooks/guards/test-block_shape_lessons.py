#!/usr/bin/env python3
"""Control harness for block_shape_lessons.

WHY THIS FILE IS LOAD-BEARING. The guard declares `OWN_SUITE = True` (it was never bash), so it has no golden and `test_guards_differential.py` REQUIRES a `test-<stem>.py` beside it; `check:ci-hook-integrity` and `check:ci-trap-registry` credit the guard with both directions because of this file, and every `shape:` pointer in TRAPS.md is live only while it is.

IT DRIVES THE LIVE GUARD THROUGH THE DISPATCHER against FIXTURE sources: a scratch root holding docs/agent-reference/TRAPS.md (`SHAPE_ROOT`) and a scratch memory directory (`SHAPE_MEMORY_DIR`). The user's real memory notes are never read or written here. One world at the end reads the REAL corpus, so the TRAPS seeds are judged where they live.

THE THREE CONTROLS THE BOX NAMES COME FIRST: `gh run rerun 1 --failed` passes while the bare form is refused (so the pass is not a guard that loaded nothing), a Shape that does not compile is not loaded, and a Shape whose Silent sample fires is not loaded. A shape that is not loaded must ADMIT the command it would have matched, and say so on stderr.
"""

import json
import os
import pathlib
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parents[2]
DISPATCH = str(HERE.parent / "dispatch.py")
GUARD_ARGV = [sys.executable, DISPATCH, "block_shape_lessons"]

RERUN_NOTE = """---
name: feedback-rerun-failed-only
description: "Re-run a red CI run with `gh run rerun <id> --failed`, never the bare form"
---

Re-run with `--failed`.

Shape: pre:refuse ^gh(?:\\s+(?:-R|--repo)[\\s=]\\S+)?\\s+run\\s+rerun\\b(?!.*\\s(?:--failed|--job|-j|--help|-h)(?:[\\s=]|$))
Shape-Say: a bare `gh run rerun <id>` restarts EVERY job; add --failed
Shape-Fires: gh run rerun 39766647743
Shape-Fires: gh -R rediacc/console run rerun 5
Shape-Silent: gh run rerun 1 --failed
Shape-Silent: echo gh run rerun 1
"""

TRAPS_WARN = """# Traps

## A fixture warn lesson
Trap-Id: fixture-warn
Enforced-By: shape:fixture-warn
Residue:
Shape: pre:warn ^date\\b.*%[0-9]+N
Shape-Fires: date +%s%3N
Shape-Silent: date +%s

body

## A fixture post lesson the pre guard must ignore
Trap-Id: fixture-post
Enforced-By: shape:fixture-post
Residue:
Shape: post ^make\\b
Shape-Output: boom
Shape-Fires: make all => boom
Shape-Silent: make all => fine

body
"""


def note(body_lines):
    return "---\nname: n\ndescription: a fixture note\n---\n\n" + "\n".join(body_lines) + "\n"


BAD_COMPILE = note(
    [
        "Shape: pre:refuse ^rm\\s+(-rf",
        "Shape-Fires: rm -rf x",
        "Shape-Silent: rm x",
    ]
)
BAD_SILENT = note(
    [
        "Shape: pre:refuse ^rm\\b",
        "Shape-Fires: rm -rf x",
        "Shape-Silent: rm -i x",
    ]
)
BAD_FIRES = note(
    [
        "Shape: pre:refuse ^rm\\s+-rf\\b",
        "Shape-Fires: rm -r x",
        "Shape-Silent: rm x",
    ]
)
NO_SILENT = note(["Shape: pre:refuse ^rm\\s+-rf\\b", "Shape-Fires: rm -rf x"])
NO_SIDE = note(["Shape: sometimes ^rm", "Shape-Fires: rm x", "Shape-Silent: ls"])

NOT_LOADED = "lesson shape NOT LOADED"


def world(base, name, traps=None, notes=None):
    """A scratch root and memory dir. Returns the env overrides that point the guard at them."""
    root = base / name / "root"
    (root / "docs" / "agent-reference").mkdir(parents=True)
    (root / "docs" / "agent-reference" / "TRAPS.md").write_text(traps or "# Traps\n", "utf-8")
    memory = base / name / "memory"
    memory.mkdir()
    for stem, text in (notes or {}).items():
        (memory / ("%s.md" % stem)).write_text(text, "utf-8")
    return {
        "SHAPE_ROOT": str(root),
        "SHAPE_MEMORY_DIR": str(memory),
        "TRAPGUARD_DIR": str(base / name / "ledgers"),
        "CLAUDE_PROJECT_DIR": str(root),
    }


def run(command, env, session=""):
    payload = {"tool_name": "Bash", "session_id": session, "tool_input": {"command": command}}
    proc = subprocess.run(
        GUARD_ARGV,
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=False,
        env=dict(os.environ, **env),
        timeout=60,
    )
    return proc.returncode, proc.stdout, proc.stderr


TALLY = {"fails": 0, "total": 0, "blocked": 0}


def case(name, command, env, want_rc, needles=(), absent=(), session=""):
    TALLY["total"] += 1
    rc, out, err = run(command, env, session)
    TALLY["blocked"] += rc == 2
    missing = [n for n in needles if n not in err]
    present = [n for n in absent if n in err]
    ok = rc == want_rc and not missing and not present and out == ""
    TALLY["fails"] += not ok
    print("%-70s want=%d got=%d %s" % (name[:70], want_rc, rc, "ok" if ok else "*** FAIL ***"))
    if missing:
        print("    stderr does not name: %s" % missing)
    if present:
        print("    stderr should not name: %s" % present)
    if out:
        print("    stdout is not empty: %r" % out[:200])
    if not ok and err:
        print("    stderr: %s" % err.strip().splitlines()[:6])


with tempfile.TemporaryDirectory(prefix="shape-lessons-") as tmp:
    base = pathlib.Path(tmp)

    # ---- the three controls, first ----
    rerun = world(base, "rerun", notes={"feedback_rerun_failed_only": RERUN_NOTE})
    case(
        "CONTROL: gh run rerun 1 --failed passes",
        "gh run rerun 1 --failed",
        rerun,
        0,
        absent=[NOT_LOADED, "BLOCKED"],
    )
    case(
        "and the bare form is refused (the shape IS loaded)",
        "gh run rerun 1",
        rerun,
        2,
        ["BLOCKED", "restarts EVERY job", "gh run rerun 1"],
    )
    bad = world(base, "compile", notes={"bad": BAD_COMPILE})
    case(
        "CONTROL: a Shape that does not compile is not loaded",
        "rm -rf x",
        bad,
        0,
        [NOT_LOADED, "does not compile"],
    )
    silent = world(base, "silent", notes={"bad": BAD_SILENT})
    case(
        "CONTROL: a Shape whose Silent sample fires is not loaded",
        "rm -rf x",
        silent,
        0,
        [NOT_LOADED, "Shape-Silent sample 'rm -i x' fires"],
    )

    # ---- the refusing direction ----
    case(
        "the rerun refusal after cd &&",
        "cd /x && gh run rerun 7 --repo a/b",
        rerun,
        2,
        ["matched: `gh run rerun 7 --repo a/b`"],
    )
    case(
        "the rerun refusal inside bash -c",
        "bash -c 'gh run rerun 8'",
        rerun,
        2,
        ["matched: `gh run rerun 8`"],
    )
    case("the rerun refusal with a global -R", "gh -R a/b run rerun 9", rerun, 2, ["BLOCKED"])
    case(
        "the refusal names its source note",
        "gh run rerun 1",
        rerun,
        2,
        ["feedback_rerun_failed_only.md"],
    )

    # ---- the admitting direction ----
    case("--failed before the id", "gh run rerun --failed 1", rerun, 0)
    case("a single job", "gh run rerun 1 --job 2", rerun, 0)
    case("an echo naming it is not a run", 'echo "gh run rerun 1"', rerun, 0)
    case("a commit message naming it is not a run", 'git commit -m "gh run rerun 1" -- a', rerun, 0)
    case("a heredoc read by cat is not a run", "cat <<'E'\ngh run rerun 1\nE", rerun, 0)
    case("an unrelated gh run", "gh run view 1", rerun, 0)
    case("an empty command", "", rerun, 0)

    # ---- every other reason a shape is not loaded ----
    fires = world(base, "fires", notes={"bad": BAD_FIRES})
    case(
        "a Fires sample that stays silent: not loaded",
        "rm -rf x",
        fires,
        0,
        [NOT_LOADED, "Shape-Fires sample 'rm -r x' does not fire"],
    )
    nosilent = world(base, "nosilent", notes={"bad": NO_SILENT})
    case(
        "no Silent sample: not loaded",
        "rm -rf x",
        nosilent,
        0,
        [NOT_LOADED, "no Shape-Silent sample"],
    )
    noside = world(base, "noside", notes={"bad": NO_SIDE})
    case("a Shape naming no side: not loaded", "rm x", noside, 0, [NOT_LOADED, "names no side"])

    # ---- named once per session ----
    once = world(base, "once", notes={"bad": BAD_COMPILE})
    case(
        "a broken shape is named on the first call of a session",
        "ls",
        once,
        0,
        [NOT_LOADED],
        session="s-1",
    )
    case("and not again in the same session", "ls", once, 0, absent=[NOT_LOADED], session="s-1")
    case("but again in another session", "ls", once, 0, [NOT_LOADED], session="s-2")

    # ---- TRAPS fixture: warn, and a post shape the pre guard ignores ----
    traps = world(base, "traps", traps=TRAPS_WARN)
    case(
        "a pre:warn shape admits with a warning",
        "date +%s%3N",
        traps,
        0,
        ["WARNING (lesson fixture-warn)", "TRAPS.md (Trap-Id: fixture-warn)"],
    )
    case("its Silent spelling says nothing", "date +%s", traps, 0, absent=["WARNING"])
    case(
        "a post-only shape never acts before the call",
        "make all",
        traps,
        0,
        absent=["WARNING", "BLOCKED"],
    )

    # ---- memory notes off ----
    off = dict(rerun, SHAPE_MEMORY_DIR="")
    case("an empty SHAPE_MEMORY_DIR reads no memory note", "gh run rerun 1", off, 0)

    # ---- the REAL corpus: the TRAPS seed where it lives ----
    real_env = {
        "CLAUDE_PROJECT_DIR": str(REPO),
        "SHAPE_MEMORY_DIR": "",
        "TRAPGUARD_DIR": str(base / "real-ledgers"),
    }
    # An inherited SHAPE_ROOT would point these two cases away from the real corpus.
    os.environ.pop("SHAPE_ROOT", None)
    case(
        "REAL TRAPS: date +%s%3N warns (seed date-precision-digit-under-uutils)",
        "date +%s%3N",
        real_env,
        0,
        ["date-precision-digit-under-uutils", "EPOCHREALTIME"],
        absent=[NOT_LOADED],
    )
    case(
        "REAL TRAPS: date +%s says nothing", "date +%s", real_env, 0, absent=["WARNING", NOT_LOADED]
    )

print()
# ANTI-VACUITY: a guard that answers one way on every input passes half of any suite.
total, blocked = TALLY["total"], TALLY["blocked"]
if blocked in (0, total):
    print(
        "*** FAIL *** %d of %d cases blocked: the guard answered the same way on every input."
        % (blocked, total),
        file=sys.stderr,
    )
    TALLY["fails"] += 1
print("%d case(s), %d blocked, %d allowed" % (total, blocked, total - blocked))
print("FAILURES: %d" % TALLY["fails"])
sys.exit(1 if TALLY["fails"] else 0)
