r"""battery.py's tree guard must survive a CLEAN checkout.

Ported from `.ci/scripts/quality/check-battery-clean-tree.sh`, which is NOT deleted; see `rediacc_ci.quality.__init__` for why both copies live and for the phase-5 decision that retires the twin.

-----------------------------------------------------------------------------
RETARGETED 2026-09-09 (W7P3-BAT), FROM `.ci/scripts/test/run-all.sh` ONTO `.ci/rediacc_ci/battery.py`.
-----------------------------------------------------------------------------

THE SUBJECT MOVED, SO THE GATE MOVED WITH IT. `battery.py` replaces `run-all.sh` as the runner, and this gate exists only to police the runner's tracked-tree snapshot. Left pointed at the bash file it would have gone one of two ways once that file was deleted, and both are worse than a red: it would have REFUSED (`CANNOT VERIFY`, exit 1) and read as a bug in the deletion, or --
if anyone had "fixed" the refusal by treating an absent subject as clean -- it
would have passed forever while policing nothing. Retargeting is what keeps the control alive across the replacement.

WHAT DID NOT CHANGE, deliberately: the gate still EXTRACTS the live guard by name rather than copying it, still refuses when the extraction finds nothing, still plants the historical defect first to prove the instrument can fire, and still asserts BOTH directions (quiet on a clean tree, loud on a dirty one). The extraction language is the only thing that changed, because the
subject is now Python.

THE PLANT IS THE SAME DEFECT IN THE NEW LANGUAGE. `PREFIX_GUARD` below is a `tree_state` that shells the snapshot out to `bash -c 'set -euo pipefail; git
status --porcelain | grep -v ...'` under `check=True`. That is not a synthetic
failure: it is the exact pre-fix pipeline, and the realistic way a Python rewrite reintroduces it is by handing the whole thing back to bash. On a CLEAN
tree the grep matches nothing, pipefail carries the 1 out of bash, `check=True`
raises, and the snapshot aborts -- the 2026-09-03 incident, reproduced.

THE HISTORY BELOW IS THE TWIN'S AND IS CARRIED WHOLE, because the incident IS the gate and a summary of it would be a different gate. Read `run-all.sh` in it as "the runner", which is now `battery.py`.

  check:ci-battery-clean-tree -- the runner's tree guard must survive a CLEAN
  checkout.

  WHY THIS EXISTS, and it is a defect this gate's own subject introduced.
  run-all.sh snapshots tracked files before and after the battery so a gate test
  that rewrites one is caught by name. The first version of that snapshot was

      tree_state() { ... git status --porcelain | grep -v '^??' | sort; }
      TREE_BEFORE="$(tree_state)"

  and under `set -euo pipefail` a grep that filters EVERYTHING out exits 1, which
  the command substitution carries straight into an abort. `grep -v '^??'` matches
  nothing exactly when there are no MODIFIED tracked files -- a clean checkout. CI
  has one.

  THE FAILURE WAS INVISIBLE, which is the part worth gating. The abort happened
  before run-all.sh printed its first line, so CI showed the step exiting 1 with no
  test name, no assertion, no output at all. And it passed locally three times
  running, because a developer's tree nearly always carries some edit -- the grep
  matched, and the bug could not be reached from the machine where the code was
  written.

  WHAT THIS DOES NOT DO, stated because the wider rule is tempting and wrong. There
  are 21 other `VAR="$(... | grep ...)"` sites in tracked shell under `set -e`.
  Nearly all are `grep -c` over a fixture the test itself wrote, where an empty
  match means the FIXTURE is broken and aborting is defensible. The property that
  makes this one a bug is that empty is a LEGITIMATE, EXPECTED state. A blanket
  static rule cannot tell those apart and would report 21 findings to fix 1 -- the
  same shape check_git_history_depth records reverting at 89. So this gate asserts
  the behaviour, not the syntax.

  Exit 1 on a guard that cannot survive a clean tree, 2 on a failed control.

THE EXIT-2 PROMISE IS NOT KEPT BY EITHER SIDE. The header says "2 on a failed control", and the only exits the twin can reach are 0 and 1: the control failure goes through `fail`, which increments the same `FAIL` counter every other check uses, and the epilogue exits 1. Carried unchanged, because changing it would change the verdict, and reported.

-----------------------------------------------------------------------------
PORT NOTES.
-----------------------------------------------------------------------------

THE GUARD IS EXTRACTED, NEVER COPIED, and the twin says why in its own words: "a copy keeps passing after run-all.sh changes, which is the failure this whole battery exists to prevent. If the extraction finds nothing the gate REFUSES rather than reporting a clean tree guard that it never saw." That refusal is this gate's anti-vacuity rule and it is preserved exactly: an absent or
renamed `tree_state` exits 1 with `CANNOT VERIFY`, never 0.

THE PYTHON TERMINATOR IS `^\S`, AND IT IS THE ANALOGUE OF THE BASH `^}`. A
Python function ends where the next COLUMN-1 statement begins, so the extractor consumes indented lines and blank lines and stops at the first flush-left one -- including a flush-left `#` comment, which is what actually follows `tree_state` in battery.py. Trailing blank lines are dropped so the extracted text ends at the last line of the body, which is what makes the `CANNOT
VERIFY` comparison and the drive result stable.

THE ONE-LINE CASE IS KEPT, and it is not hypothetical here either: `def tree_state(root): return ...` is legal Python and would otherwise swallow the whole rest of the file, exactly as the bash draft swallowed everything after a
one-line `tree_state() { ...; }`. `SELF_CLOSING_RE` is applied to the definition
line only and tests for code after the colon.

THE GIT-STATUS SANITY CHECK HAD TO BE RE-KEYED WITH THE SUBJECT, and this is the trap in the retarget. The twin looked for the literal substring `git status`, which is right for a shell pipeline and WRONG for an argv list: battery.py spells it `["git", "status", "--porcelain"]`, where the two words are separated by `", "`. A gate carried over unchanged would have refused on a
perfectly good guard. `GIT_STATUS_RE` therefore admits up to eight non-word characters between the two tokens, which covers both spellings and still refuses a `tree_state` that reads something else entirely (`git diff --name-only` has no `status` in it at all).

`python3` IS PROBED FOR ON BOTH SIDES, and this is the one place the retarget adds a refusal the twin did not have. The subject is now Python, so the drive is `python3 <driver>`; without a probe an absent interpreter surfaces as an OSError in the port and a `command not found` in the twin, which is a divergence in the one case where the two must agree. Both sides now refuse by name
with the fix in the message.

THE DRIVER CATCHES AND PRINTS `ERR:<type>: <message>`, rather than letting the traceback out. A traceback carries the driver's own path, and the driver lives in a `mktemp` directory, so the failure detail would differ between two runs of the SAME implementation -- and every twin comparison of a red would be noise. The marker is deterministic and still names the exception.

`$(...)` STRIPS TRAILING NEWLINES, AND THAT IS LOAD-BEARING TWICE. The extracted guard is compared against `-z`, and the drive result is compared against the
literal string `"rc=0 out="` -- a comparison that a single trailing newline would
break. `_capture` therefore rstrips "\n" and nothing else, which is exactly what the shell does; stripping whitespace would additionally eat the trailing space of a `git status --porcelain` line and make two different guards look identical.

`out="$(python3 "$TMP/drive.py" 2>&1)"` MERGES THE TWO STREAMS. That is the
`2>&1` anti-pattern this repo warns about, and here it is deliberate and correct: the whole POINT is to capture the abort, which prints on stderr when it prints at all, next to the guard's stdout. Reproduced with
`stderr=subprocess.STDOUT` rather than by reading the two and concatenating,
because interleaving order would differ.

NEITHER SIDE PROBES FOR `git`. The twin shells out to `git init`, `git config`, `git add` and `git commit` with no `command -v git` in front of them, so on a host without git the failure is four unexplained non-zero exits and a `CANNOT VERIFY`-shaped red that names the wrong thing. A probe is NOT added here: it would change the verdict in exactly the case where the two
implementations would otherwise agree, which is the one thing a port may not do. Reported instead.

`pass` AND `fail` BOTH WRITE TO STDOUT, including the failures. That is unusual
for this repo -- `rediacc_ci.log` refuses to put messages on stdout -- and it is
the twin's contract: a caller reading this gate's stdout sees the whole tally. `print()` is used for them rather than `log`, exactly as `npmrc.py` does for the data its twin echoes.
"""

import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

from rediacc_ci import paths
from rediacc_ci.controls import Controls

# The three extraction conditions, as three named patterns. Named rather than inlined because each one is a decision with a blast radius; see the port notes.
DEFN_RE = re.compile(r"^def tree_state\(")
# Code after the colon, i.e. a one-line def. `[^:]*` stops the scan at the first colon, which for `def tree_state(root: pathlib.Path) -> str:` is the ANNOTATION colon, so the pattern is anchored on the closing paren instead.
SELF_CLOSING_RE = re.compile(r"^def tree_state\(.*\)[^:]*:[ \t]*[^ \t#]")
# The Python analogue of the bash `^}`: the next flush-left line ends the body.
TERMINATOR_RE = re.compile(r"^[^ \t\n]")

# `git status` in EITHER spelling: the shell pipeline's two adjacent words, and the argv list's `"git", "status"`. See the port notes for why the twin's plain substring test could not survive the retarget.
GIT_STATUS_RE = re.compile(r"git[^A-Za-z0-9_]{0,8}status")

# The environment override the twin offers. ONE name, and it is the twin's own, not `REDIACC_CI_ROOT`: a harness pointing this gate at a fixture today sets this variable, and a port that stopped reading it would silently judge the real tree while the operator read a fixture's verdict.
ROOT_ENV = "BATTERY_CLEAN_TREE_ROOT"

# Where the guard lives, relative to the root. RETARGETED 2026-09-09: this was `.ci/scripts/test/run-all.sh` until battery.py replaced it as the runner.
BATTERY_REL = ".ci/rediacc_ci/battery.py"

# THE DRIVER'S PREAMBLE AND EPILOGUE. Held as constants so the twin can be diffed against them line for line; the two implementations must generate the SAME driver or they are not testing the same thing.
DRIVER_HEAD = "import pathlib\nimport subprocess\nimport sys\n\n"
DRIVER_TAIL = (
    "\n\ntry:\n"
    "    T = tree_state(pathlib.Path(sys.argv[1]))\n"
    "except BaseException as exc:\n"
    '    print("ERR:%s: %s" % (type(exc).__name__, exc))\n'
    "    raise SystemExit(1)\n"
    'print("OUT:%s" % T)\n'
)

# THE PLANT. The pre-fix form of the guard in the subject's new language: the
# same pipeline, handed back to bash, under `check=True`. It MUST abort on a
# clean tree. Without it the two assertions that follow could both pass against a guard that cannot fail, and this gate would be the thing it was written to catch.
PREFIX_GUARD = (
    "def tree_state(root):\n"
    "    proc = subprocess.run(\n"
    '        ["bash", "-c", "set -euo pipefail; '
    "git status --porcelain | grep -v '^??' | sort\"],\n"
    "        cwd=str(root),\n"
    "        capture_output=True,\n"
    "        text=True,\n"
    "        check=True,\n"
    "    )\n"
    '    return proc.stdout.rstrip("\\n")\n'
)


def extract_guard(text: str) -> str:
    """The `tree_state` definition, by NAME, out of battery.py's source.

    The rules, which are the awk program's rules with `^}` replaced by `^\\S`:

        /^def tree_state\\(/  { print; if (one-liner) exit; inside = 1; next }
        inside               { if ($0 ~ /^[^ \\t]/) exit; print }

    Returns "" when there is no definition, which is what makes the caller's refusal reachable. Trailing blank lines are dropped, because a Python body ends at its last statement while the blank lines before the next top-level statement belong to neither.
    """
    out: list[str] = []
    inside = False
    for line in text.split("\n"):
        if not inside:
            if DEFN_RE.search(line):
                out.append(line)
                if SELF_CLOSING_RE.search(line):
                    break
                inside = True
            continue
        if TERMINATOR_RE.search(line):
            break
        out.append(line)
    while out and out[-1].strip() == "":
        out.pop()
    return "\n".join(out)


def _capture(argv: list[str], cwd: str | None = None, merge: bool = False) -> tuple[int, str]:
    """Run a command, return (rc, output with trailing newlines stripped).

    `merge` puts stderr onto stdout, reproducing `2>&1` INSIDE the child rather than by concatenating two captured buffers, so the interleaving is the child's. See the port notes.

    THE RSTRIP IS `"\\n"` AND NOT `.strip()`. `$(...)` removes trailing newlines and nothing else; a `git status --porcelain` line can end in a meaningful space, and eating it would make two different guards produce the same text.
    """
    proc = subprocess.run(
        argv,
        cwd=cwd,
        capture_output=not merge,
        stdout=subprocess.PIPE if merge else None,
        stderr=subprocess.STDOUT if merge else None,
        text=True,
        check=False,
    )
    return proc.returncode, (proc.stdout or "").rstrip("\n")


def make_repo(directory: str, dirty: bool) -> None:
    """make_repo <dir> <dirty:0|1> -- a one-commit repository, optionally edited.

    An UNTRACKED file in both, because the guard filters `??` and that filtering is exactly what makes the clean case produce no output at all.
    """
    path = pathlib.Path(directory)
    path.mkdir(parents=True, exist_ok=True)
    _capture(["git", "init", "-q", "--initial-branch=main", directory])
    _capture(["git", "-C", directory, "config", "user.email", "t@example.com"])
    _capture(["git", "-C", directory, "config", "user.name", "t"])
    (path / "tracked.txt").write_text("original\n", encoding="utf-8")
    _capture(["git", "-C", directory, "add", "tracked.txt"])
    _capture(["git", "-C", directory, "commit", "-q", "-m", "init"])
    if dirty:
        (path / "tracked.txt").write_text("changed\n", encoding="utf-8")
    (path / "untracked.txt").write_text("scratch\n", encoding="utf-8")


def drive(tmp: str, src: str, repo: str) -> str:
    """drive <guard-source> <repo> -> "rc=<n> out=<value>".

    The generated driver is DRIVER_HEAD + the extracted definition + DRIVER_TAIL, and the twin generates the same bytes from the same three pieces. The repo arrives as `sys.argv[1]` rather than as an interpolated literal, so a path holding a quote cannot rewrite the driver.

    `src` IS RSTRIPPED OF NEWLINES HERE, and that is a parity requirement rather than tidiness: on the twin's side `src` arrives through `$(...)`, which has already eaten them, so a port that kept one would generate a driver one byte different from the twin's for the same guard.
    """
    script = pathlib.Path(tmp) / "drive.py"
    script.write_text(DRIVER_HEAD + src.rstrip("\n") + DRIVER_TAIL, encoding="utf-8")
    rc, out = _capture(["python3", str(script), repo], merge=True)
    # `${out#OUT:}` -- strip ONE leading marker if it is there. A run that
    # aborted before the print has no marker and keeps whatever it printed.
    out = out.removeprefix("OUT:")
    return "rc=%s out=%s" % (rc, out)


def main(argv: list[str] | None = None) -> int:
    """Run the gate. Exit 0 clean, 1 a guard that cannot survive a clean tree.

    `--selftest` is intercepted BEFORE the extraction and before any repository is built. The twin takes no arguments at all, so no caller can be passing this string today.
    """
    args = list(argv or [])
    if args and args[0] == "--selftest":
        return selftest()

    root_dir = os.environ.get(ROOT_ENV) or str(paths.repo_root())
    battery = os.path.join(root_dir, BATTERY_REL)

    if shutil.which("python3") is None:
        print(
            "✗ CANNOT VERIFY: python3 is not on PATH, and the subject is a Python", file=sys.stderr
        )
        print("  function that has to be DRIVEN to judge it. Install python3.", file=sys.stderr)
        return 1

    failures = 0

    def passed(label: str) -> None:
        print("PASS: %s" % label)

    def failed(label: str, detail: str = "") -> None:
        nonlocal failures
        print("FAIL: %s" % label)
        if detail:
            print("      %s" % detail)
        failures += 1

    tmp = tempfile.mkdtemp()
    try:
        # --- the REAL function, extracted by name ------------------------
        try:
            source = pathlib.Path(battery).read_text(encoding="utf-8", errors="replace")
        except OSError:
            # `awk ... "$BATTERY" 2>/dev/null` prints nothing for a file it cannot open, so an absent battery.py reaches the refusal below rather than raising here.
            source = ""
        guard = extract_guard(source).rstrip("\n")
        if guard == "" or not GIT_STATUS_RE.search(guard):
            print(
                "✗ CANNOT VERIFY: no tree_state() reading git status found in %s." % battery,
                file=sys.stderr,
            )
            print(
                "  Either the guard was removed -- in which case the battery no longer",
                file=sys.stderr,
            )
            print(
                "  notices a gate test rewriting a tracked file -- or it was renamed and",
                file=sys.stderr,
            )
            print("  this gate needs to follow it. Refusing rather than passing.", file=sys.stderr)
            return 1

        clean_repo = os.path.join(tmp, "clean")
        dirty_repo = os.path.join(tmp, "dirty")
        make_repo(clean_repo, dirty=False)
        make_repo(dirty_repo, dirty=True)

        # --- THE PLANT: the pre-fix form must abort on a clean tree -------
        #
        # Without this the two assertions below could both pass against a guard that cannot fail, and this gate would be the thing it was written to catch.
        plant = drive(tmp, PREFIX_GUARD, clean_repo)
        if plant.startswith("rc=0"):
            failed("CONTROL: the pre-fix guard did NOT abort on a clean tree", plant)
        else:
            passed("CONTROL: the pre-fix guard aborts on a clean tree, so the defect is detectable")

        # --- the live guard, both trees -----------------------------------
        live_clean = drive(tmp, guard, clean_repo)
        if live_clean == "rc=0 out=":
            passed("the live guard survives a CLEAN checkout and reports no change")
        else:
            failed("the live guard does not survive a clean checkout", live_clean)

        live_dirty = drive(tmp, guard, dirty_repo)
        if live_dirty.startswith("rc=0") and "tracked.txt" in live_dirty:
            passed("CONTROL: it still REPORTS a modified tracked file, so the fix did not blind it")
        else:
            failed("the live guard no longer reports a modified tracked file", live_dirty)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print()
    if failures > 0:
        print("✗ battery clean-tree guard: %d failure(s)" % failures, file=sys.stderr)
        return 1
    print(
        "✓ battery clean-tree guard: battery.py's snapshot survives a clean checkout "
        "and still sees a real change"
    )
    print("  Blind spot: this asserts battery.py's guard only. The general 'a filter that")
    print("  legitimately matches nothing aborts the snapshot' shape is deliberately not")
    print("  gated -- see this file's header.")
    return 0


# The live guard's shape as of battery.py:313, kept here so the selftest has a CONTROL that must pass. It is a MULTI-LINE def, which is the branch every real run takes; the one-line branch is exercised by its own case below.
_LIVE_GUARD = (
    "def tree_state(root):\n"
    "    try:\n"
    "        proc = subprocess.run(\n"
    '            ["git", "status", "--porcelain"],\n'
    "            cwd=str(root),\n"
    "            capture_output=True,\n"
    "            text=True,\n"
    "            check=False,\n"
    "            timeout=120,\n"
    "        )\n"
    "    except (OSError, subprocess.SubprocessError):\n"
    '        return ""\n'
    '    return "\\n".join('
    'sorted(ln for ln in proc.stdout.splitlines() if not ln.startswith("??")))\n'
)


def selftest() -> int:
    """Plant each violation, prove it reds; remove it, prove it greens.

    BOTH DIRECTIONS FOR EVERY CONTROL. A gate with only positive plants would happily refuse a correct battery.py, and the mirrors below (the live guard, a one-line def, a body whose blank lines run on into a comment) are the half that proves it does not.
    """
    ctl = Controls("battery-clean-tree", floor=24, verbose=True)

    with tempfile.TemporaryDirectory() as tmp:
        base = pathlib.Path(tmp)

        # -- the extractor, on its own -------------------------------------
        ctl.check(
            "EXTRACT: a multi-line def stops at the next flush-left line",
            extract_guard("x = 1\n%s\n# a comment\nclass Report:\n" % _LIVE_GUARD.rstrip("\n")),
            _LIVE_GUARD.rstrip("\n"),
        )
        ctl.check(
            "EXTRACT: a flush-left COMMENT terminates it, which is what follows it live",
            extract_guard("def tree_state(root):\n    return git_status()\n# next\nx = 1\n"),
            "def tree_state(root):\n    return git_status()",
        )
        ctl.check(
            "EXTRACT: BLANK lines inside the body are kept",
            extract_guard("def tree_state(root):\n    a = 1\n\n    return a\ndef other():\n"),
            "def tree_state(root):\n    a = 1\n\n    return a",
        )
        ctl.check(
            "EXTRACT: trailing blank lines are dropped, so the text ends at the body",
            extract_guard("def tree_state(root):\n    return 1\n\n\ndef other():\n"),
            "def tree_state(root):\n    return 1",
        )
        ctl.check(
            "EXTRACT: a ONE-LINE def takes only its own line and nothing after it",
            extract_guard('def tree_state(root): return "x"\nmain()\n'),
            'def tree_state(root): return "x"',
        )
        ctl.check(
            "EXTRACT: an ANNOTATED signature is not mistaken for a one-liner",
            extract_guard("def tree_state(root: pathlib.Path) -> str:\n    return 1\nx = 2\n"),
            "def tree_state(root: pathlib.Path) -> str:\n    return 1",
        )
        ctl.check("EXTRACT: no definition yields the empty string", extract_guard("nothing\n"), "")
        ctl.check(
            "EXTRACT: an INDENTED definition is invisible, and the gate then refuses",
            extract_guard("    def tree_state(root):\n        return 1\n"),
            "",
        )
        ctl.check(
            "EXTRACT: a differently NAMED function is invisible",
            extract_guard("def tree_state2(root):\n    return 1\n"),
            "",
        )
        ctl.check(
            "EXTRACT: an unterminated definition runs to end of file",
            extract_guard("def tree_state(root):\n    return 1\n"),
            "def tree_state(root):\n    return 1",
        )

        # -- the git-status sanity check, both spellings --------------------
        #
        # THE RE-KEY THE RETARGET TURNED ON. The twin's plain `git status` substring is FALSE against the argv list battery.py actually writes.
        ctl.check(
            'SANITY: the argv spelling `"git", "status"` is recognised',
            bool(GIT_STATUS_RE.search('["git", "status", "--porcelain"]')),
            True,
        )
        ctl.check(
            "SANITY: the shell spelling `git status` is recognised",
            bool(GIT_STATUS_RE.search("git status --porcelain | sort")),
            True,
        )
        ctl.check(
            "SANITY: a guard reading `git diff --name-only` is NOT recognised",
            bool(GIT_STATUS_RE.search('["git", "diff", "--name-only"]')),
            False,
        )

        # -- the whole gate, against planted battery.py files ---------------
        def run(body: str | None) -> int:
            root = base / "root"
            shutil.rmtree(root, ignore_errors=True)
            target = root / BATTERY_REL
            target.parent.mkdir(parents=True)
            if body is not None:
                target.write_text(body, encoding="utf-8")
            saved = os.environ.get(ROOT_ENV)
            os.environ[ROOT_ENV] = str(root)
            try:
                return main([])
            finally:
                if saved is None:
                    del os.environ[ROOT_ENV]
                else:
                    os.environ[ROOT_ENV] = saved

        # THE CONTROL. The live guard, verbatim, must PASS -- otherwise every plant below fires against a fixture that was already failing and the suite is green while testing nothing.
        ctl.check("CONTROL: the live guard passes", run(_LIVE_GUARD), 0)

        # VACUITY, in the gate's own vocabulary: an absent or unrecognisable subject is a REFUSAL, never a clean verdict.
        ctl.check("VACUITY: an absent battery.py is refused", run(None), 1)
        ctl.check("VACUITY: an EMPTY battery.py is refused", run(""), 1)
        ctl.check("VACUITY: a battery.py with no tree_state is refused", run("x = 1\n"), 1)
        ctl.check(
            "VACUITY: a tree_state that does not read git status is refused",
            run(
                "def tree_state(root):\n"
                '    return subprocess.run(["git", "diff", "--name-only"], cwd=str(root),'
                " capture_output=True, text=True).stdout\n"
            ),
            1,
        )

        # PLANT 1: the pre-fix form itself, in the new language. This is the historical defect, and the gate exists to red on it.
        ctl.check("PLANT: the pre-fix guard is caught", run(PREFIX_GUARD), 1)

        # PLANT 2: a guard that survives a clean tree by seeing NOTHING. The blind direction, which a naive fix produces and which the twin's third assertion is there for.
        ctl.check(
            "PLANT: a guard blinded to a real change is caught",
            # `cwd` AND `capture_output` are both load-bearing in a fixture that is deliberately broken: without them this plant runs git in the REAL tree and sprays its status into the selftest transcript, and the transcript then differs between two runs of the same code.
            run(
                "def tree_state(root):\n"
                '    subprocess.run(["git", "status"], cwd=str(root), capture_output=True)\n'
                '    return ""\n'
            ),
            1,
        )

        # PLANT 3: a guard that reports UNTRACKED files, so a clean checkout is not quiet.
        ctl.check(
            "PLANT: a guard that reports untracked files is caught",
            run(
                "def tree_state(root):\n"
                '    proc = subprocess.run(["git", "status", "--porcelain"], cwd=str(root),'
                " capture_output=True, text=True)\n"
                '    return "\\n".join(sorted(proc.stdout.splitlines()))\n'
            ),
            1,
        )

        # PLANT 4: both directions broken at once.
        ctl.check(
            "PLANT: a guard printing a constant fails BOTH assertions",
            run(
                "def tree_state(root):\n"
                '    subprocess.run(["git", "status", "--porcelain"], cwd=str(root),'
                " capture_output=True)\n"
                '    return "CONST"\n'
            ),
            1,
        )

        # ITS MIRROR: a ONE-LINE rewrite of the live guard still passes, so the gate is asserting the BEHAVIOUR and not the multi-line def's shape. This is the control that would fail if someone re-implemented the extractor as a string comparison against battery.py:313.
        ctl.check(
            "MIRROR: a one-line rewrite with the same behaviour passes",
            run(
                "def tree_state(root): return "
                '"\\n".join(sorted(ln for ln in subprocess.run(["git", "status", "--porcelain"],'
                " cwd=str(root), capture_output=True, text=True).stdout.splitlines()"
                ' if not ln.startswith("??")))\n'
                "x = 1\n"
            ),
            0,
        )

        # -- the plant the gate carries, driven directly -------------------
        work = base / "work"
        work.mkdir(exist_ok=True)
        clean = str(work / "c")
        dirty = str(work / "d")
        make_repo(clean, dirty=False)
        make_repo(dirty, dirty=True)
        ctl.check(
            "PLANT: the pre-fix guard really does abort on a clean tree",
            drive(str(work), PREFIX_GUARD, clean).startswith("rc=1 out=ERR:CalledProcessError"),
            True,
        )
        ctl.check(
            "MIRROR: and it does NOT abort on a dirty one, which is why it survived review",
            drive(str(work), PREFIX_GUARD, dirty).startswith("rc=0"),
            True,
        )
        ctl.check(
            "CONTROL: the live guard is quiet on a clean tree",
            drive(str(work), _LIVE_GUARD, clean),
            "rc=0 out=",
        )
        ctl.check(
            "CONTROL: and still reports the modified tracked file on a dirty one",
            "tracked.txt" in drive(str(work), _LIVE_GUARD, dirty),
            True,
        )

        # THE FIXTURES THEMSELVES. A clean repo that was not actually clean, or a dirty one that was not actually dirty, would make every assertion above true for the wrong reason.
        rc, out = _capture(["git", "-C", clean, "status", "--porcelain", "-uall"])
        ctl.check("FIXTURE: the clean repo has no MODIFIED tracked file", rc, 0)
        ctl.check(
            "FIXTURE: and its only entry is the untracked scratch file",
            out,
            "?? untracked.txt",
        )
        rc, out = _capture(["git", "-C", dirty, "status", "--porcelain", "-uall"])
        ctl.check(
            "FIXTURE: the dirty repo reports its modified tracked file", "tracked.txt" in out, True
        )
        ctl.check(
            "FIXTURE: and it reports the modification, not just the untracked file",
            " M " in out,
            True,
        )

        # THE REAL SUBJECT IS STILL THERE. Every case above runs against a fixture root; this one asserts the live tree still holds a battery.py
        # with an extractable guard, so a rename cannot leave the selftest green
        # while the gate refuses on every real run.
        live = paths.repo_root() / BATTERY_REL
        ctl.check("REAL: the subject file exists on this tree", live.is_file(), True)
        ctl.check(
            "REAL: and its tree_state extracts and reads git status",
            bool(GIT_STATUS_RE.search(extract_guard(live.read_text(encoding="utf-8")))),
            True,
        )

    return 0 if ctl.report() else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
