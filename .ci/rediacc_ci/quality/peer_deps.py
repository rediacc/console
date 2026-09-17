"""`npm ls` must not report an invalid peer dependency.

Ported from `.ci/scripts/quality/check-peer-deps.sh`, which is NOT deleted; see `rediacc_ci.quality.__init__` for why both copies live until a differential ledger row exists over K distinct trees.

WHAT THE TWIN SAYS, carried whole because it is the entire statement of intent the original ever made:

    Check for peer dependency conflicts
    Usage: check-peer-deps.sh

    Runs npm ls and checks for invalid peer dependencies.
    Peer dependency conflicts can cause runtime issues and should be resolved.

    Example:
      .ci/scripts/quality/check-peer-deps.sh

Its gate header registers it as step "Verify no peer dependency conflicts", needs none, lane quality-code.

-----------------------------------------------------------------------------
PORT NOTES. What is identical, what is deliberately stronger, and why.
-----------------------------------------------------------------------------

THE MERGE IS THE CONTRACT. The twin runs `npm ls 2>&1` and greps the COMBINED text, and that is not laziness: `npm ls` prints the dependency tree on stdout and its `npm error invalid: ...` lines on stderr, so a search of one stream alone would pass while the evidence went to the other. `rediacc_ci.proc.run` refuses to merge streams (its docstring names the 2026-09-06 stream-swap
incident recorded at `.ci/scripts/lib/emit-advisory.sh:22-52`), so this module reaches for
`subprocess` directly with `stderr=STDOUT` rather than quietly weakening the
shared helper. Reproducing the merge is reproducing the subject.

`|| true` IS REPRODUCED, AND IT IS LOAD-BEARING. `npm ls` exits non-zero on ANY tree problem, including the extraneous-package warnings this repository produces routinely, so the twin deliberately ignores the exit status and rules only on the TEXT. A port that trusted the exit code would fail on trees the twin passes. The status is therefore captured and reported in the success
line, where a reader can see it, and never used as a verdict.

"invalid" IS A SUBSTRING TEST, NOT A WORD TEST. `grep -q "invalid"` matches `invalidate`, `Invalidated` is NOT matched (the pattern is case-sensitive), and matching inside a package name is possible in principle. The over-match is carried across on purpose: for a dead-code gate a false positive deletes live code, but for THIS gate a false positive is a human reading one extra line
of `npm ls`, while a false negative ships a broken peer tree. The selftest pins the over-match in both directions so the next reader knows it is a decision.

THE TWIN SOURCES `.ci/scripts/lib/common.sh` AND THE PORT DOES NOT, which is the one archaeology token this file would otherwise drop. `log_step`, `log_error`, `log_info` and `get_repo_root` are the gate's only dependency on the shared bash library, which is what makes the twin cheap to retire. Here `log.*` comes from `rediacc_ci.log` and the root from
`rediacc_ci.paths.repo_root()`.

TWO PLACES THIS IS DELIBERATELY STRONGER THAN THE TWIN, both of them cases where the twin reports a clean tree having verified NOTHING. Neither can fire on a tree where npm works, so neither is reachable from the differential ledger; they are stated here so the divergence is a decision on the record rather than a surprise.

  1. NO npm ON PATH. `NPM_LS_OUTPUT=$(npm ls 2>&1 || true)` captures bash's own
     "npm: command not found" into the variable, finds no "invalid" in it, and
     the twin prints its green line. That is the archetype: a gate that exits 0
     because the tool was not installed. This port exits 77 (cannot-run, never a
     verdict) and prints the fix.
  2. EMPTY OUTPUT. `npm ls` that produces not one byte has told us nothing about
     the tree, and an empty haystack contains no needle, so the twin is green.
     This port refuses in the repository's own vocabulary instead.

WHAT NEITHER IMPLEMENTATION CAN SEE: whether the peer ranges are RIGHT. `npm ls` reports what the installed tree violates, so a dependency nobody installed, a workspace nobody linked, and an `overrides` entry that papers over a genuine conflict are all invisible here.
"""

import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

from rediacc_ci import log, paths
from rediacc_ci.controls import Controls

# The command, as one constant. The twin spells it `npm ls` in exactly one place and so does this: two spellings of a subject is how one of them stops being exercised.
NPM = "npm"
NPM_LS_ARGS = ["ls"]

# The needle. Case-sensitive, substring, exactly as `grep -q "invalid"` is.
NEEDLE = "invalid"

# Cannot-run. Never a verdict; see `rediacc_ci.quality.__init__`.
EXIT_CANNOT_RUN = 77


def invalid_lines(output: str) -> list[str]:
    """The lines `echo "$NPM_LS_OUTPUT" | grep "invalid"` would print.

    Pure, so the selftest and pytest can drive it without an npm on PATH. The trailing-newline strip reproduces `$( )`, which eats trailing newlines before the text ever reaches grep; without it the last element is an empty string that grep never sees.
    """
    return [line for line in output.rstrip("\n").split("\n") if NEEDLE in line]


def npm_ls(cwd: pathlib.Path) -> tuple[int, str]:
    """Run `npm ls` with stderr MERGED into stdout. Returns (exit code, text).

    The merge is the twin's `2>&1` and is described in the port notes. The exit code is returned rather than swallowed so the caller can PRINT it; the twin's `|| true` means it must never decide anything.
    """
    completed = subprocess.run(
        [NPM, *NPM_LS_ARGS],
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )
    return completed.returncode, completed.stdout or ""


def main(argv: list[str] | None = None) -> int:
    """Run the gate. Returns the process exit code; never raises for a verdict."""
    if argv and argv[0] == "--selftest":
        return selftest()

    root = paths.repo_root()
    # The twin `cd`s to the repo root before running npm, because `npm ls` resolves the workspace from the working directory and would otherwise describe whatever tree the caller happened to be standing in.
    os.chdir(root)

    log.step("Checking for peer dependency conflicts...")

    if shutil.which(NPM) is None:
        log.error(
            "peer-deps: no `npm` on PATH, so NOTHING was verified. Install Node "
            "(see .devcontainer/Dockerfile, which pins npm 11) and re-run. This "
            "gate refuses rather than reporting the clean tree its bash twin "
            "would report here."
        )
        return EXIT_CANNOT_RUN

    status, output = npm_ls(root)

    if output.strip() == "":
        log.error(
            "peer-deps: `npm ls` produced no output at all (exit %d), so its verdict "
            "would be meaningless. An empty haystack contains no needle." % status
        )
        return 1

    hits = invalid_lines(output)
    if hits:
        log.error("Peer dependency conflicts detected")
        # stdout, exactly as the twin: `echo ""` then the header then the hits. A gate's stdout is DATA and this is the data -- the offending lines, verbatim, so the reader can paste them into a resolution.
        print()
        print("Invalid dependencies:")
        for line in hits:
            print(line)
        return 1

    # PRINT THE SHAPE, NOT JUST THE VERDICT. The twin's green line is seven words and cannot tell a reader whether it saw a dependency tree or one line of noise. The counts are what makes a collapsed scan visible.
    log.info(
        "No peer dependency conflicts found (npm ls exit %d, %d line(s) scanned)"
        % (status, len(output.rstrip("\n").split("\n")))
    )
    return 0


def _shim(bin_dir: pathlib.Path, body: str) -> None:
    """Write an `npm` the gate will find on PATH.

    A FILE, not a Python mock. The subject resolves `npm` through PATH exactly as the bash twin does, and a patched `subprocess.run` would prove nothing about that resolution -- which is the very thing case MISSING TOOL is about.
    """
    shim = bin_dir / "npm"
    shim.write_text("#!/bin/bash\n%s\n" % body, encoding="utf-8")
    shim.chmod(0o755)


def selftest() -> int:
    """Plant a defect in BOTH directions and require the gate to notice.

    Every case has its mirror. A gate that always fires is as useless as one that never does, and red is the direction a reviewer waves through.
    """
    # floor=13 rather than 0: the floor is the only thing that catches a selftest
    # whose cases stopped executing, and a default of zero is a floor that cannot fail. See rediacc_ci.controls for the five drifted copies that taught it.
    ctl = Controls("peer-deps", floor=13, verbose=True)
    saved_cwd = os.getcwd()
    saved_env = dict(os.environ)

    with tempfile.TemporaryDirectory() as tmp:
        base = pathlib.Path(tmp)
        fake_root = base / "root"
        fake_root.mkdir()
        bin_dir = base / "bin"
        bin_dir.mkdir()

        def run(body: str | None) -> int:
            """Drive main() with an npm shim, or with NO npm when body is None."""
            for child in bin_dir.iterdir():
                child.unlink()
            if body is not None:
                _shim(bin_dir, body)
            os.environ[paths.ROOT_ENV] = str(fake_root)
            # PATH is REPLACED, not prepended: an empty bin dir must mean no npm anywhere, or the MISSING TOOL case silently finds the real one and scores a pass while proving the opposite.
            os.environ["PATH"] = str(bin_dir)
            try:
                return main([])
            finally:
                os.environ.clear()
                os.environ.update(saved_env)
                os.chdir(saved_cwd)

        # EVERY SHIM USES ONLY BASH BUILTINS (printf, echo). PATH is replaced
        # with the shim directory alone so the MISSING TOOL case is honest, and a
        # shim that reached for `cat` would then die with 127 and no "invalid" in its output -- which reads as a CLEAN tree. That is not hypothetical: it is what the first run of this selftest did, and two plants scored 0.
        clean_tree = "printf '%s\\n' 'console@0.0.0-dev /repo' '+-- tsx@4.20.6' '`-- zod@4.5.4'"
        ctl.check("CONTROL: a clean npm ls tree passes", run(clean_tree), 0)

        # THE PLANT. One invalid peer line, on stdout.
        stdout_hit = (
            "printf '%s\\n' 'console@0.0.0-dev /repo' "
            "'+-- zod@3.25.76 invalid: \"^4.4.3\" from the root project'"
        )
        ctl.check("PLANT: an invalid peer on stdout is a conflict", run(stdout_hit), 1)

        # THE MIRROR THAT PROVES THE MERGE. npm writes its error lines to STDERR. A port that captured only stdout passes this tree, which is the exact blindness the twin's `2>&1` exists to prevent.
        stderr_hit = (
            "printf '%s\\n' 'console@0.0.0-dev /repo'\n"
            "echo 'npm error invalid: zod@3.25.76 /repo/node_modules/zod' >&2"
        )
        ctl.check("PLANT: an invalid peer on STDERR is still a conflict", run(stderr_hit), 1)

        # The exit status of npm must not decide anything: `|| true`.
        ctl.check(
            "CONTROL: a non-zero npm ls with clean text still passes",
            run("%s\nexit 1" % clean_tree),
            0,
        )
        ctl.check(
            "PLANT: a ZERO-exit npm ls with an invalid line still fails",
            run("%s\nexit 0" % stdout_hit),
            1,
        )

        # The documented over-match, both directions. `invalid` is a substring.
        ctl.check(
            "OVER-MATCH: a line containing 'invalidate' fires, as grep -q does",
            run("echo 'note: run npm cache invalidate'"),
            1,
        )
        ctl.check(
            "OVER-MATCH MIRROR: capital 'Invalid' does NOT fire (grep is case-sensitive)",
            run("echo 'Invalid: capitalised, and the needle is not'"),
            0,
        )

        # VACUITY. Both of these are trees the twin reports as CLEAN.
        ctl.check("VACUITY: empty npm ls output is refused", run("true"), 1)
        ctl.check("VACUITY: whitespace-only npm ls output is refused", run("printf '  \\n\\n'"), 1)
        ctl.check(
            "VACUITY: no npm on PATH is cannot-run (%d), never a pass" % EXIT_CANNOT_RUN,
            run(None),
            EXIT_CANNOT_RUN,
        )

    # The pure helper, driven directly. `$( )` eats trailing newlines, so a trailing blank line must not become a scanned line.
    ctl.check("HELPER: a trailing blank line is not a hit", invalid_lines("clean\n\n"), [])
    ctl.check("HELPER: no output at all yields no hits", invalid_lines(""), [])
    ctl.check(
        "HELPER: every matching line is returned, in order",
        invalid_lines("one invalid\nclean\ntwo invalid\n"),
        ["one invalid", "two invalid"],
    )

    return 0 if ctl.report() else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
