r"""run-all.sh's tree guard must survive a CLEAN checkout.

Ported from `.ci/scripts/quality/check-battery-clean-tree.sh`, which is NOT
deleted; see `rediacc_ci.quality.__init__` for why both copies live and for the
phase-5 decision that retires the twin.

THE TWIN'S OWN HEADER, carried over verbatim because the incident IS the gate
and a summary of it would be a different gate:

  check:ci-battery-clean-tree -- run-all.sh's tree guard must survive a CLEAN
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

THE EXIT-2 PROMISE IS NOT KEPT BY EITHER SIDE. The header says "2 on a failed
control", and the only exits the twin can reach are 0 and 1: the control failure
goes through `fail`, which increments the same `FAIL` counter every other check
uses, and the epilogue exits 1. Carried unchanged, because changing it would
change the verdict, and reported.

-----------------------------------------------------------------------------
PORT NOTES.
-----------------------------------------------------------------------------

THE GUARD IS EXTRACTED, NEVER COPIED, and the twin says why in its own words:
"a copy keeps passing after run-all.sh changes, which is the failure this whole
battery exists to prevent. If the extraction finds nothing the gate REFUSES
rather than reporting a clean tree guard that it never saw." That refusal is
this gate's anti-vacuity rule and it is preserved exactly: an absent or renamed
`tree_state` exits 1 with `CANNOT VERIFY`, never 0.

THE ONE-LINE CASE IS THE ONE THE FIRST DRAFT GOT WRONG, and the twin records
it: "a `sed` range from the definition to the next `^}` swallowed everything
after a ONE-LINE `tree_state() { ...; }`, including run-all.sh's own `cd
"$GATES_DIR"`, and the harness then failed on an unbound variable rather than on
the property under test. Take the definition line, and only keep reading if it
did not close itself." `extract_guard` below is that awk program transliterated
rule for rule, and the live `run-all.sh:349` is in fact a one-liner, so this is
the branch that runs every day.

THE AWK CONDITIONS, spelled out because two of them are subtly narrow:

    /^tree_state\(\) \{/     ANCHORED at column 1 and requiring EXACTLY one
                             space before the brace. An indented definition, or
                             `tree_state () {`, or `tree_state(){`, is invisible
                             and the gate refuses. That is the safe direction --
                             it refuses rather than passing -- but it is a
                             refusal for a formatting reason, and it is reported.
    /\}[[:space:]]*$/        the SELF-CLOSING test, applied to the definition
                             line only. Any line ending in `}` counts, including
                             one that merely closes a subshell block.
    /^\}/                    the terminator, anchored at column 1, so an indented
                             `}` does not end the function.

`[[:space:]]` IS NOT `\s`. POSIX space is exactly [ \t\n\v\f\r]; Python's `\s`
on a str pattern also matches U+00A0 and friends. Written out, as
`rediacc_ci.quality.npmrc` does, and for the same reason.

`$(...)` STRIPS TRAILING NEWLINES, AND THAT IS LOAD-BEARING TWICE. The extracted
guard is compared against `-z` and against `*"git status"*`, and the drive
result is compared against the literal string `"rc=0 out="` -- a comparison that
a single trailing newline would break. `_capture` therefore rstrips "\n" and
nothing else, which is exactly what the shell does; stripping whitespace would
additionally eat the trailing space of a `git status --porcelain` line and make
two different guards look identical.

`out="$(bash "$TMP/drive.sh" 2>&1)"` MERGES THE TWO STREAMS. That is the
`2>&1` anti-pattern this repo warns about, and here it is deliberate and
correct: the whole POINT is to capture the abort, which prints on stderr when it
prints at all, next to the guard's stdout. Reproduced with
`stderr=subprocess.STDOUT` rather than by reading the two and concatenating,
because interleaving order would differ.

NEITHER SIDE PROBES FOR `git`. The twin shells out to `git init`, `git config`,
`git add` and `git commit` with no `command -v git` in front of them, so on a
host without git the failure is four unexplained non-zero exits and a `CANNOT
VERIFY`-shaped red that names the wrong thing. A probe is NOT added here: it
would change the verdict in exactly the case where the two implementations would
otherwise agree, which is the one thing a port may not do. Reported instead.

`pass` AND `fail` BOTH WRITE TO STDOUT, including the failures. That is unusual
for this repo -- `rediacc_ci.log` refuses to put messages on stdout -- and it is
the twin's contract: a caller reading this gate's stdout sees the whole tally.
`print()` is used for them rather than `log`, exactly as `npmrc.py` does for the
data its twin echoes.
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

# POSIX [[:space:]], written out. See the port notes for why `\s` is wrong here.
SPACE = r"[ \t\n\v\f\r]"

# The three awk conditions, as three named patterns. Named rather than inlined
# because each one is a decision with a blast radius; see the port notes.
DEFN_RE = re.compile(r"^tree_state\(\) \{")
SELF_CLOSING_RE = re.compile(r"\}%s*$" % SPACE)
TERMINATOR_RE = re.compile(r"^\}")

# The environment override the twin offers. ONE name, and it is the twin's own,
# not `REDIACC_CI_ROOT`: a harness pointing this gate at a fixture today sets
# this variable, and a port that stopped reading it would silently judge the real
# tree while the operator read a fixture's verdict.
ROOT_ENV = "BATTERY_CLEAN_TREE_ROOT"

# Where the guard lives, relative to the root.
RUN_ALL_REL = ".ci/scripts/test/run-all.sh"

# THE PLANT. The pre-fix form of the guard, which MUST abort on a clean tree.
# Without it the two assertions that follow could both pass against a guard that
# cannot fail, and this gate would be the thing it was written to catch.
PREFIX_GUARD = (
    'tree_state() { (cd "$BATTERY_REPO_ROOT" && git status --porcelain 2>/dev/null '
    "| grep -v '^??' | sort); }"
)


def extract_guard(text: str) -> str:
    """The `tree_state` definition, by NAME, out of run-all.sh's source.

    The awk program transliterated rule for rule:

        /^tree_state\\(\\) \\{/ { print; if ($0 ~ /\\}[[:space:]]*$/) exit;
                                  inside = 1; next }
        inside                 { print; if ($0 ~ /^\\}/) exit }

    Returns "" when there is no definition, which is what makes the caller's
    refusal reachable. The result is NOT rstripped here: `$(...)` does that at
    the call site and doing it twice would hide which one is responsible.
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
        out.append(line)
        if TERMINATOR_RE.search(line):
            break
    return "\n".join(out)


def _capture(argv: list[str], cwd: str | None = None, merge: bool = False) -> tuple[int, str]:
    """Run a command, return (rc, output with trailing newlines stripped).

    `merge` puts stderr onto stdout, reproducing `2>&1` INSIDE the child rather
    than by concatenating two captured buffers, so the interleaving is the
    child's. See the port notes.

    THE RSTRIP IS `"\\n"` AND NOT `.strip()`. `$(...)` removes trailing newlines
    and nothing else; a `git status --porcelain` line can end in a meaningful
    space, and eating it would make two different guards produce the same text.
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

    An UNTRACKED file in both, because the guard filters `??` and that filtering
    is exactly what makes the clean case produce no output at all.
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

    The heredoc is UNQUOTED in the twin (`<<DRIVE`, not `<<'DRIVE'`), so `$repo`
    and `$src` are expanded by the OUTER shell while `\\$(tree_state)` and `\\$T`
    survive into the generated script. That split is reproduced by building the
    text here with the two values interpolated and the two dollar signs literal.
    """
    script = pathlib.Path(tmp) / "drive.sh"
    script.write_text(
        "set -euo pipefail\n"
        'BATTERY_REPO_ROOT="%s"\n'
        "%s\n"
        'T="$(tree_state)"\n'
        'echo "OUT:$T"\n' % (repo, src),
        encoding="utf-8",
    )
    rc, out = _capture(["bash", str(script)], merge=True)
    # `${out#OUT:}` -- strip ONE leading marker if it is there. A run that
    # aborted before the echo has no marker and keeps whatever it printed.
    out = out.removeprefix("OUT:")
    return "rc=%s out=%s" % (rc, out)


def main(argv: list[str] | None = None) -> int:
    """Run the gate. Exit 0 clean, 1 a guard that cannot survive a clean tree.

    `--selftest` is intercepted BEFORE the extraction and before any repository
    is built. The twin takes no arguments at all, so no caller can be passing
    this string today.
    """
    args = list(argv or [])
    if args and args[0] == "--selftest":
        return selftest()

    root_dir = os.environ.get(ROOT_ENV) or str(paths.repo_root())
    run_all = os.path.join(root_dir, RUN_ALL_REL)

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
            source = pathlib.Path(run_all).read_text(encoding="utf-8", errors="replace")
        except OSError:
            # `awk ... "$RUN_ALL" 2>/dev/null` prints nothing for a file it
            # cannot open, so an absent run-all.sh reaches the refusal below
            # rather than raising here.
            source = ""
        guard = extract_guard(source).rstrip("\n")
        if guard == "" or "git status" not in guard:
            print(
                "✗ CANNOT VERIFY: no tree_state() reading git status found in %s." % run_all,
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
        # Without this the two assertions below could both pass against a guard
        # that cannot fail, and this gate would be the thing it was written to
        # catch.
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
        "✓ battery clean-tree guard: run-all.sh's snapshot survives a clean checkout "
        "and still sees a real change"
    )
    print("  Blind spot: this asserts run-all.sh's guard only. The general 'empty grep aborts")
    print("  under set -e' shape is deliberately not gated -- see this file's header.")
    return 0


# The live guard's shape as of run-all.sh:349, which is a ONE-LINER and therefore
# exercises the self-closing branch of the extractor on every real run.
_LIVE_ONE_LINER = (
    'tree_state() { (cd "$BATTERY_REPO_ROOT" && { git status --porcelain 2>/dev/null || true; } '
    "| { grep -v '^??' || true; } | sort); }"
)


def selftest() -> int:
    """Plant each violation, prove it reds; remove it, prove it greens.

    BOTH DIRECTIONS FOR EVERY CONTROL. A gate with only positive plants would
    happily refuse a correct run-all.sh, and the mirrors below (the live
    one-liner, a multi-line definition, a `}` that only closes a subshell) are
    the half that proves it does not.
    """
    ctl = Controls("battery-clean-tree", floor=24, verbose=True)

    with tempfile.TemporaryDirectory() as tmp:
        base = pathlib.Path(tmp)

        # -- the extractor, on its own -------------------------------------
        ctl.check(
            "EXTRACT: the live one-liner is taken whole and nothing after it",
            extract_guard('prelude\n%s\ncd "$GATES_DIR"\n' % _LIVE_ONE_LINER),
            _LIVE_ONE_LINER,
        )
        ctl.check(
            "EXTRACT: a multi-line definition stops at a column-1 closing brace",
            extract_guard("x\ntree_state() {\n  git status --porcelain\n}\nafter\n"),
            "tree_state() {\n  git status --porcelain\n}",
        )
        ctl.check(
            "EXTRACT: an INDENTED closing brace does not terminate it",
            extract_guard("tree_state() {\n  (\n  )\n}\nafter\n"),
            "tree_state() {\n  (\n  )\n}",
        )
        ctl.check("EXTRACT: no definition yields the empty string", extract_guard("nothing\n"), "")
        ctl.check(
            "EXTRACT: an INDENTED definition is invisible, and the gate then refuses",
            extract_guard("  tree_state() { git status; }\n"),
            "",
        )
        ctl.check(
            "EXTRACT: `tree_state () {` with a space before the parens is invisible",
            extract_guard("tree_state () { git status; }\n"),
            "",
        )
        ctl.check(
            "EXTRACT: `tree_state(){` with no space before the brace is invisible",
            extract_guard("tree_state(){ git status; }\n"),
            "",
        )
        ctl.check(
            "EXTRACT: a trailing space after the closing brace still self-closes",
            extract_guard("tree_state() { git status; } \nafter\n"),
            "tree_state() { git status; } ",
        )
        ctl.check(
            "EXTRACT: a definition that does NOT self-close keeps reading",
            extract_guard("tree_state() { git status\n  | sort\n}\nafter\n"),
            "tree_state() { git status\n  | sort\n}",
        )
        ctl.check(
            "EXTRACT: an unterminated definition runs to end of file",
            extract_guard("tree_state() {\n  git status\n"),
            "tree_state() {\n  git status\n",
        )

        # -- the whole gate, against planted run-all.sh files ---------------
        def run(body: str | None) -> int:
            root = base / "root"
            shutil.rmtree(root, ignore_errors=True)
            target = root / RUN_ALL_REL
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

        # THE CONTROL. The live guard, verbatim, must PASS -- otherwise every
        # plant below fires against a fixture that was already failing and the
        # suite is green while testing nothing.
        ctl.check("CONTROL: the live one-liner guard passes", run(_LIVE_ONE_LINER + "\n"), 0)

        # VACUITY, in the gate's own vocabulary: an absent or unrecognisable
        # subject is a REFUSAL, never a clean verdict.
        ctl.check("VACUITY: an absent run-all.sh is refused", run(None), 1)
        ctl.check("VACUITY: an EMPTY run-all.sh is refused", run(""), 1)
        ctl.check("VACUITY: a run-all.sh with no tree_state is refused", run("echo hi\n"), 1)
        ctl.check(
            "VACUITY: a tree_state that does not read git status is refused",
            run('tree_state() { (cd "$BATTERY_REPO_ROOT" && git diff --name-only); }\n'),
            1,
        )

        # PLANT 1: the pre-fix form itself. This is the historical defect, and
        # the gate exists to red on it.
        ctl.check("PLANT: the pre-fix guard is caught", run(PREFIX_GUARD + "\n"), 1)

        # PLANT 2: a guard that survives a clean tree by seeing NOTHING. The
        # blind direction, which a naive fix produces and which the twin's third
        # assertion is there for.
        ctl.check(
            "PLANT: a guard blinded to a real change is caught",
            run(
                'tree_state() { (cd "$BATTERY_REPO_ROOT" && git status --porcelain '
                ">/dev/null 2>&1; true); }\n"
            ),
            1,
        )

        # PLANT 3: a guard that reports UNTRACKED files, so a clean checkout is
        # not quiet.
        ctl.check(
            "PLANT: a guard that reports untracked files is caught",
            run('tree_state() { (cd "$BATTERY_REPO_ROOT" && git status --porcelain | sort); }\n'),
            1,
        )

        # PLANT 4: both directions broken at once.
        ctl.check(
            "PLANT: a guard printing a constant fails BOTH assertions",
            run(
                'tree_state() { (cd "$BATTERY_REPO_ROOT" && git status --porcelain '
                ">/dev/null 2>&1; echo CONST); }\n"
            ),
            1,
        )

        # ITS MIRROR: a multi-line rewrite of the live guard still passes, so the
        # gate is asserting the BEHAVIOUR and not the one-liner's syntax. This is
        # the control that would fail if someone re-implemented the extractor as
        # a string comparison against run-all.sh:349.
        ctl.check(
            "MIRROR: a multi-line rewrite with the same behaviour passes",
            run(
                "tree_state() {\n"
                '  (cd "$BATTERY_REPO_ROOT" \\\n'
                "    && { git status --porcelain 2>/dev/null || true; } \\\n"
                "    | { grep -v '^??' || true; } \\\n"
                "    | sort)\n"
                "}\n"
                'cd "$GATES_DIR"\n'
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
            drive(str(work), PREFIX_GUARD, clean),
            "rc=1 out=",
        )
        ctl.check(
            "MIRROR: and it does NOT abort on a dirty one, which is why it survived review",
            drive(str(work), PREFIX_GUARD, dirty).startswith("rc=0"),
            True,
        )
        ctl.check(
            "CONTROL: the live guard is quiet on a clean tree",
            drive(str(work), _LIVE_ONE_LINER, clean),
            "rc=0 out=",
        )
        ctl.check(
            "CONTROL: and still reports the modified tracked file on a dirty one",
            "tracked.txt" in drive(str(work), _LIVE_ONE_LINER, dirty),
            True,
        )

        # THE FIXTURES THEMSELVES. A clean repo that was not actually clean, or a
        # dirty one that was not actually dirty, would make every assertion above
        # true for the wrong reason.
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

    return 0 if ctl.report() else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
