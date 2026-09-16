"""Every Go module that `replace`s the renet worktree must stay TIDY against it.

Ported from `.ci/scripts/quality/check-go-module-sync.sh`, which is not deleted;
see `rediacc_ci.quality.__init__` for why both copies live.

WHAT BROKE, carried from the twin's header because the incident is the gate.
`.ci/scripts/private/license-mint/` is its own module and pulls renet in through
`replace github.com/rediacc/renet => ../../../../private/renet`, so renet's
dependency graph is part of its own. Bumping renet's `go.mod`
(logrus v1.10.0 -> v1.10.1) left license-mint still pinning v1.10.0 as indirect,
and `go build` then refuses with:

    go: updates to go.mod needed; to update it:
            go mod tidy

WHY IT NEEDS A GATE RATHER THAN CARE. Nothing surfaced this until
`Tests + Infra / License Enforcement`, roughly 25 minutes into CI and well past
every quality lane, on run 32462755535. The signal is also misleading at first
read: the job announces "Building license-mint" and then prints a wall of
`go: downloading ...` lines including the OLD version, so it looks like a
network step rather than a lockstep violation. The coupling is invisible from
renet's side, where the bump looks complete and self-contained.

It is DISCOVERED, not hardcoded: any future module that replaces renet is
covered the day it is added, and a zero-module result is a failure rather than
a pass, because a discovery gate that finds nothing has verified nothing.

`go mod tidy -diff` reports what tidying WOULD change and exits non-zero without
writing, so this never mutates the tree it checks.

Exit 0 clean, 1 violation, 2 setup error.

-----------------------------------------------------------------------------
PORT NOTES.
-----------------------------------------------------------------------------

EXIT 2 IS KEPT, NOT RENUMBERED TO 77. The W7 contract reserves 77 for
cannot-run, and "go is not installed" is exactly that. The twin answers 2, its
own header documents 2, and a port that changes an exit code is not a port: the
differential compares exit codes and would rule MISMATCH_EXIT on the very case
this gate is most likely to hit on a developer laptop. The renumbering is a
decision for whoever retires the twin, in the change that retires it, and it is
named here so the choice is visible rather than forgotten.

GOTOOLCHAIN IS DELIBERATELY NOT FORCED, and the twin says why: "renet's go.mod
requires >= 1.25.0 and a machine whose local toolchain is older (1.24.0 was
observed) would fail with 'go.mod requires go >= 1.25.0' and read as a
module-sync defect, which it is not." The port therefore passes the ambient
environment through untouched and sets no Go variables at all.

THE `mapfile` NOTE SURVIVES EVEN THOUGH PYTHON HAS NO mapfile. The twin uses a
`while read` loop rather than `mapfile` because "check-commands.sh refuses
mapfile because ubuntu-slim and other minimal CI images may not provide bash
4+". That constraint shaped the twin's shape and is invisible in the result, so
it is written down here: the list comprehension below is not a simplification
anyone chose, it is the constraint disappearing.

DISCOVERY IS `grep -rln ... --include=go.mod .`, AND FOUR OF ITS PROPERTIES ARE
BEHAVIOUR RATHER THAN INCIDENT:

  * `--include=go.mod` matches the BASENAME, so a file called `vendor.go.mod`
    is not included and `go.mod` at any depth is.
  * The argument is `.`, so every reported path is `./`-prefixed and
    `dirname ./go.mod` is `.`. The port joins with "." for the same shape,
    because the path is printed in the finding and a bare `go.mod` versus
    `./go.mod` would read as a finding difference.
  * `grep -r` does NOT follow directory symlinks (that is `-R`). The walk runs
    through `paths.walk_tree`, whose `follow_symlinks` defaults to False and is
    passed down to `os.walk` explicitly, because a default that happens to match
    is one refactor away from not matching.

THIS GATE IS WHY `paths.walk_tree` EXISTS, so the divergence from the twin is
deliberate and is the point rather than an oversight. On 2026-09-13 a peer
session's stale checkout at `.claude/worktrees/agent-afc2194d0118609f2/` carried
a copy of `.ci/scripts/private/license-mint`, and this discovery returned it as a
SECOND module. Its `replace ../../../../private/renet` cannot resolve from the
nested location, so `go mod tidy -diff` failed there and the gate went red over a
file that is not in the repository: `git ls-files` cannot see `.claude/worktrees`
(`.git/info/exclude:11`) and neither can any CI checkout. The twin's
`grep -rln ... .` still has this bug. Fixing it here and not there means the two
can disagree on a tree that has a peer worktree open, which is exactly the tree
the shadow ledger refuses to record from (it demands a clean checkout), and is
worth far less than a gate whose verdict does not depend on who else is working.
  * `grep -v node_modules` is a SUBSTRING test on the whole path, not a path
    component test, so a directory named `my_node_modules_backup` is excluded
    too. Carried as `in`, not as a component check.

THE `go mod tidy -diff` OUTPUT IS CAPTURED MERGED, `2>&1`, and that is the
twin's contract rather than laziness. Go writes its diff and its errors to
different streams depending on the failure, and the twin prints the first 20
lines of the combined blob under the finding. `rediacc_ci.proc.run` refuses to
merge streams (for the 2026-09-06 stream-swap reason in
`.ci/scripts/lib/emit-advisory.sh:22-52`), so this module reaches for
`subprocess` directly rather than quietly weakening the shared helper.

`head -20` IS A TRUNCATION, NOT A SUMMARY, and it is preserved: a module with 40
lines of diff shows 20 of them on both sides. Dropping the truncation would make
the port noisier than its twin on exactly the tree where the gate fires.
"""

import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

from rediacc_ci import log, paths
from rediacc_ci.controls import Controls

# The needle. A literal string, not a pattern: the twin passes it to grep with no
# `-E`, and `.` in `github.com` would match any character under a regex reading.
# It does not matter for this needle and it would matter for the next one.
REPLACE_NEEDLE = "replace github.com/rediacc/renet"

# `--include=go.mod`: a basename match, not a suffix match.
MODULE_FILENAME = "go.mod"

# `grep -v node_modules`: a substring test over the whole path.
EXCLUDE_SUBSTRING = "node_modules"

# `head -20` on the captured diff.
DIFF_EXCERPT_LINES = 20

# The exit code for a setup error, documented in the twin's header as "2 setup
# error". See the port notes for why it is not 77.
EXIT_SETUP_ERROR = 2


def find_modules(root: pathlib.Path) -> list[str]:
    """Every `go.mod` under `root` that replaces the renet worktree.

    Returns `./`-prefixed, byte-sorted paths, which is what
    `grep -rln ... . | grep -v node_modules | sort` produces under LC_ALL=C.
    A ZERO-LENGTH RESULT IS NOT AN ERROR HERE; it is the caller's refusal, so
    that a test can assert on the discovery and on the refusal separately.
    """
    found: list[str] = []
    for dirpath, _dirnames, filenames in paths.walk_tree(root):
        if MODULE_FILENAME not in filenames:
            continue
        absolute = pathlib.Path(dirpath) / MODULE_FILENAME
        try:
            text = absolute.read_text(encoding="utf-8", errors="replace")
        except OSError:
            # grep skips what it cannot read and carries on; it does not abort
            # the scan. One unreadable go.mod must not turn a discovery gate
            # into a gate that discovered nothing, which is the failure this
            # whole file is written against.
            continue
        if REPLACE_NEEDLE not in text:
            continue
        relative = os.path.relpath(str(absolute), str(root))
        composed = "./" + relative if relative != "." else "."
        if EXCLUDE_SUBSTRING in composed:
            continue
        found.append(composed)
    # `sort` with LC_ALL=C is a byte sort. Python's default str comparison is by
    # code point, which agrees for ASCII and diverges for anything else, so the
    # bytes are compared rather than the characters.
    return sorted(found, key=str.encode)


def tidy_diff(directory: pathlib.Path) -> tuple[int, str]:
    """`cd <dir> && go mod tidy -diff 2>&1`. Returns (exit code, merged output).

    Merged on purpose; see the port notes. The environment is inherited whole,
    with no GOTOOLCHAIN pin, which is also the twin's behaviour and also on
    purpose.
    """
    completed = subprocess.run(
        ["go", "mod", "tidy", "-diff"],
        cwd=str(directory),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )
    # `out="$(...)"` strips every trailing newline, and the twin then tests
    # `[[ -n "$out" ]]`. An output of only newlines is therefore EMPTY to the
    # twin and would be non-empty to a naive port.
    return completed.returncode, completed.stdout.rstrip("\n")


def main(argv: list[str] | None = None) -> int:
    """Run the gate. Exit 0 clean, 1 violation, 2 setup error."""
    args = list(argv or [])
    if args and args[0] == "--selftest":
        return selftest()

    root = paths.repo_root()

    # A MISSING TOOL IS A LOUD FAILURE WITH THE FIX IN THE MESSAGE, not a
    # traceback from a subprocess launch that reads as flake. The twin probes
    # with `command -v go`; `shutil.which` is the same question.
    if shutil.which("go") is None:
        log.error("go is required to check module sync")
        return EXIT_SETUP_ERROR

    modules = find_modules(root)

    # ZERO INPUTS IS A FAILURE, NEVER A PASS. The twin's three lines say both
    # things a reader needs: what a green would have meant, and the two ways the
    # discovery could have gone stale.
    if not modules:
        log.error("no go.mod replaces the renet worktree, so this gate verified NOTHING.")
        log.error("  Either the coupling is gone and this gate should be deleted deliberately,")
        log.error("  or the replace directive moved and the discovery below needs retargeting.")
        return 1

    failed = False
    for module in modules:
        directory = os.path.dirname(module)
        code, out = tidy_diff(root / directory)
        if code == 0:
            log.info("%s is tidy against renet" % directory)
            continue
        log.error("%s is OUT OF SYNC with the renet worktree it replaces." % directory)
        log.error("  Fix: (cd %s && go mod tidy)" % directory)
        if out:
            for line in out.split("\n")[:DIFF_EXCERPT_LINES]:
                print(line, file=sys.stderr)
        failed = True

    if failed:
        log.error(
            "Go module sync FAILED (a renet dependency bump must re-tidy every module "
            "that replaces it)"
        )
        return 1

    # THE SHAPE, NOT JUST THE VERDICT. The count is in the success line so a
    # reader notices the day it collapses from N to 1.
    log.info("Go module sync holds: %d module(s) tidy against the renet worktree" % len(modules))
    return 0


# A module that needs no network: it requires the replaced module and nothing
# else, and the replacement is a local directory inside the fixture. `go mod
# tidy -diff` on this resolves entirely from disk, so the selftest cannot fail
# because a proxy was unreachable -- which would be a red that names the wrong
# thing.
_REPLACED_GOMOD = "module github.com/rediacc/renet\n\ngo 1.21\n"
_REPLACED_SRC = 'package renet\n\nfunc Name() string { return "renet" }\n'
_CONSUMER_SRC = (
    'package main\n\nimport "github.com/rediacc/renet"\n\nfunc main() { _ = renet.Name() }\n'
)
_TIDY_GOMOD = (
    "module example.com/consumer\n\ngo 1.21\n\n"
    "require github.com/rediacc/renet v0.0.0\n\n"
    "replace github.com/rediacc/renet => ./renet\n"
)
# THE UNTIDY ONE DIFFERS IN EXACTLY ONE LINE: the `require` is gone while the
# import stays, which is the shape the incident took (a require left pinning a
# stale version is the same class). Two fixtures that differ in more than the
# property under test prove nothing about which difference fired.
_UNTIDY_GOMOD = (
    "module example.com/consumer\n\ngo 1.21\n\nreplace github.com/rediacc/renet => ./renet\n"
)


def _build_module(base: pathlib.Path, name: str, gomod: str) -> pathlib.Path:
    """A consumer module at `base/name` replacing a local renet stub."""
    directory = base / name
    (directory / "renet").mkdir(parents=True, exist_ok=True)
    (directory / "go.mod").write_text(gomod, encoding="utf-8")
    (directory / "main.go").write_text(_CONSUMER_SRC, encoding="utf-8")
    (directory / "renet" / "go.mod").write_text(_REPLACED_GOMOD, encoding="utf-8")
    (directory / "renet" / "renet.go").write_text(_REPLACED_SRC, encoding="utf-8")
    return directory


def selftest() -> int:
    """Plant an out-of-sync module, prove it reds; tidy it, prove it greens.

    THE go-DEPENDENT HALF IS NOT SKIPPED WHEN go IS ABSENT. Skipping would let
    the suite report green having exercised only the discovery, which is the
    "unknown folded into fine" shape the anti-vacuity contract refuses. A
    missing toolchain is recorded as a FAILED control naming the fix.
    """
    ctl = Controls("go-module-sync", floor=12, verbose=True)

    with tempfile.TemporaryDirectory() as tmp:
        base = pathlib.Path(tmp)

        def run(root: pathlib.Path) -> int:
            saved = os.environ.get(paths.ROOT_ENV)
            os.environ[paths.ROOT_ENV] = str(root)
            try:
                return main([])
            finally:
                if saved is None:
                    del os.environ[paths.ROOT_ENV]
                else:
                    os.environ[paths.ROOT_ENV] = saved

        # -- DISCOVERY, which needs no toolchain at all -------------------------
        empty = base / "empty"
        empty.mkdir()
        ctl.check("DISCOVERY: a tree with no go.mod finds nothing", find_modules(empty), [])

        # A go.mod WITHOUT the replace directive is not a subject. This is the
        # mirror that stops the discovery matching every Go module in the tree.
        unrelated = base / "unrelated"
        unrelated.mkdir()
        (unrelated / "go.mod").write_text("module example.com/x\n\ngo 1.21\n", encoding="utf-8")
        ctl.check(
            "DISCOVERY MIRROR: a go.mod without the replace is not a subject",
            find_modules(unrelated),
            [],
        )

        tidy_root = base / "tidy"
        _build_module(tidy_root, "mod", _TIDY_GOMOD)
        ctl.check(
            "DISCOVERY: the replacing go.mod is found", find_modules(tidy_root), ["./mod/go.mod"]
        )

        # node_modules is excluded as a SUBSTRING of the path, so a module
        # vendored under one is invisible even though it replaces renet.
        vendored = base / "vendored"
        _build_module(vendored, "node_modules", _TIDY_GOMOD)
        ctl.check("DISCOVERY: a node_modules path is excluded", find_modules(vendored), [])

        # -- THE REFUSAL -------------------------------------------------------
        # Zero modules must be a FAILURE. A discovery gate that finds nothing
        # and reports success is the exact defect this gate is written against.
        ctl.check("VACUITY: zero replacing modules is a refusal", run(empty), 1)

        # -- THE MISSING-TOOLCHAIN BRANCH --------------------------------------
        # Driven for real by emptying PATH, so the branch is exercised rather
        # than reasoned about. Exit 2, not 1: a setup error is not a verdict.
        saved_path = os.environ.get("PATH", "")
        os.environ["PATH"] = str(base / "no-such-bin")
        try:
            ctl.check(
                "SETUP: an absent go answers 2, not a verdict", run(tidy_root), EXIT_SETUP_ERROR
            )
        finally:
            os.environ["PATH"] = saved_path

        # -- THE go-DEPENDENT HALF ---------------------------------------------
        if shutil.which("go") is None:
            ctl.fail(
                "TOOLCHAIN: go is absent, so the tidy/untidy plants did not run. "
                "Install Go (https://go.dev/dl/) and re-run; an unchecked half is "
                "not a passing half",
                "go not on PATH",
            )
        else:
            # CONTROL FIRST: the tidy fixture must be genuinely tidy, or every
            # plant below fires against something that was broken to begin with.
            code, out = tidy_diff(tidy_root / "mod")
            ctl.check("CONTROL: the tidy fixture is tidy (go mod tidy -diff)", code, 0)
            ctl.check("CONTROL: a tidy module produces no diff", out, "")
            ctl.check("CONTROL: a tidy tree passes the gate", run(tidy_root), 0)

            # THE PLANT: the same module with its `require` removed.
            untidy_root = base / "untidy"
            _build_module(untidy_root, "mod", _UNTIDY_GOMOD)
            planted_code, planted_out = tidy_diff(untidy_root / "mod")
            ctl.truthy("PLANT: go reports the untidy module non-zero", planted_code != 0)
            ctl.truthy("PLANT: go says something about it", planted_out != "")
            ctl.check("PLANT: an out-of-sync module is caught", run(untidy_root), 1)

            # AND THE MIRROR, which is the half a reviewer waves through: two
            # modules, one tidy and one not, must still be a failure -- a loop
            # that stopped after its first success would pass this.
            mixed_root = base / "mixed"
            _build_module(mixed_root, "a-tidy", _TIDY_GOMOD)
            _build_module(mixed_root, "b-untidy", _UNTIDY_GOMOD)
            ctl.check("PLANT: one bad module among good ones is caught", run(mixed_root), 1)
            ctl.check(
                "PLANT: both modules were discovered",
                find_modules(mixed_root),
                ["./a-tidy/go.mod", "./b-untidy/go.mod"],
            )

    return 0 if ctl.report() else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
