r"""The account portal must typecheck and build.

Ported from `.ci/scripts/quality/check-account-portal.sh`, which is NOT deleted;
see `rediacc_ci.quality.__init__` for why both copies live and for the phase-5 decision that retires the twin.

THE TWIN'S OWN HEADER, carried over:

  Check that the account portal frontend compiles and builds correctly

  Usage:
    .ci/scripts/quality/check-account-portal.sh

  Exit codes:
    0 - All checks pass
    1 - Check failed

AND ITS ONE PIECE OF ARCHAEOLOGY, which is the reason phase 3b exists at all and is carried verbatim because a summary of it would lose the mechanism:

  Phase 3b: TypeScript typecheck (e2e). NOTHING checked this until 2026-08-15,
  and the cost was a TS2352 sitting on a branch unseen: the backup wave made
  `kind` part of BackupDestinationSchema while an e2e fixture still built a
  destination without one. Playwright TRANSPILES without typechecking, so the
  suite ran green over a type error, and the schema's own `.default('storage')`
  meant runtime was fine too. Two layers of "works anyway" is exactly how a
  type error becomes invisible.

  It lives here rather than in a new gate key because this script is already
  the place a reader looks for "does the account package typecheck", and a
  third phase costs nothing next to the two above it.

-----------------------------------------------------------------------------
PORT NOTES.
-----------------------------------------------------------------------------

THIS GATE IS AN ORCHESTRATOR, NOT A SCANNER. Every verdict it reaches comes from the exit status of an external tool: `npm ci`, `npx tsc` three times, `npx biome`, `npm run build:account-onboarding`, `npx vite build`, and one `-f` test on the artifact those produce. The port therefore runs the SAME argv vectors in the SAME working directories and in the SAME order. There is nothing
here to re-implement, and anything that looked like an improvement would be a different gate.

THE CHILDREN INHERIT BOTH STREAMS. `npx tsc` writes its diagnostics straight to the caller's stdout and stderr in the twin, and those diagnostics ARE the finding a developer acts on. `subprocess.run` is called without `capture_output` so the same bytes reach the same places. `sys.stdout` and `sys.stderr` are flushed before every spawn, because Python block-buffers a redirected
stdout and a gate whose own message arrives AFTER the child's output is a gate whose log reads backwards.

`cd` IS NOT A PROCESS-WIDE CHDIR HERE. The twin walks between three directories
with bare `cd`s; the port passes `cwd=` per call instead. Same effect, and it
removes the class of bug where an early `return` leaves the process somewhere unexpected -- which matters more in a library that a test imports than in a script that exits.

THE ONE SHAPE THE TWO SIDES' STDERR DIFFERS ON, stated rather than discovered later: a MISSING directory. `cd "$WEB_DIR"` under `set -e` prints bash's own `check-account-portal.sh: line 39: cd: /path: No such file or directory` and exits, while the port raises no such message and returns 1 at the same point. `scripts/lib/shadow-gate.ts` classifies that bash diagnostic as CHATTER --
it carries no severity marker and does not match the grep-style finding shape -- so the FINDING SET and the EXIT CODE still agree, which is what equivalence is measured on. The message also names a script path and a line number that no port could reproduce. Named here so it is a decision and not a surprise.

PHASE 1 IS AN INSTALL, NOT A CHECK, and it is the only phase that MUTATES the tree. `npm ci --ignore-scripts` runs whenever `private/account/web/node_modules` is absent, and there is no `log_error` around it: under `set -e` a failing `npm ci` kills the script with npm's own output and no gate message at all. Carried unchanged; a reader who sees this step go red is reading npm's
diagnostics, not this gate's.

`--ignore-scripts` IS NOT DECORATION. `.npmrc` sets `ignore-scripts=true`
repo-wide (see `rediacc_ci.quality.npmrc`), and this call states it again at the call site so a future `.npmrc` edit cannot silently re-enable lifecycle scripts
for this one install.

PHASE 4 IS A WARNING AND NOTHING ELSE. `npx biome check private/account/web/src/` failing produces `log_warn "Frontend lint issues found (non-blocking)"` and the script continues; the twin says "(if biome is available)" in its section comment, and BIOME NOT BEING INSTALLED IS INDISTINGUISHABLE FROM LINT FINDINGS because both are a non-zero exit. So the phase can be permanently
satisfied by a missing tool while reporting the same single line either way. Carried, because distinguishing them would change the verdict, and reported.

PHASE 7 IS THE ANTI-VACUITY CHECK, and it is the reason this gate is not merely a chain of exit codes. `vite build` can exit 0 having written nothing useful, so the artifact is tested for directly: `workers/account/dist/account/index.html` must exist. Note what it does NOT do -- it never checks the file is non-empty, or newer than the sources, so a stale artifact from a previous
run satisfies it. Carried, and reported.

NEITHER SIDE PROBES FOR `npm` OR `npx`. A host without them produces a `command not found` from bash and a `FileNotFoundError` from Python. The port catches that and returns the same exit code at the same point rather than raising a traceback, which is the only place it deliberately behaves better than the twin without changing the verdict: a traceback and a `command not found` are
both non-zero with no findings, and a traceback is the one that reads as a bug in the gate.
"""

import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

from rediacc_ci import log, paths
from rediacc_ci.controls import Controls, plant

# The three directories the twin walks between, relative to the repository root.
WEB_REL = "private/account/web"
ACCOUNT_REL = "private/account"

# The artifact phase 7 insists on. See the port notes: existence only.
OUTPUT_REL = "workers/account/dist/account/index.html"

# Every external command, as an argv vector. Named rather than inlined so the ORDER and the ARGUMENTS are both readable in one place -- the order is the gate's control flow and the arguments are what it actually asserts.
NPM_CI = ["npm", "ci", "--ignore-scripts"]
TSC = ["npx", "tsc", "--noEmit"]
TSC_E2E = ["npx", "tsc", "--noEmit", "-p", "e2e/tsconfig.json"]
BIOME = ["npx", "biome", "check", "private/account/web/src/"]
ONBOARDING = ["npm", "run", "build:account-onboarding"]
VITE_BUILD = ["npx", "vite", "build"]


def run(argv: list[str], cwd: pathlib.Path) -> int:
    """Run one external command with both streams INHERITED. Returns its status.

    THE FLUSH BEFORE THE SPAWN IS NOT OPTIONAL. Python block-buffers a redirected stdout, so without it this gate's own `log_step` line lands after the child's output in a CI log and the reader sees the phases in the wrong order.

    A MISSING BINARY RETURNS 127 rather than raising. That is bash's own status
    for `command not found`, so the two implementations agree on the exit code
    and on the empty finding set, and a reader gets a status instead of a traceback that reads as a defect in the gate. See the port notes.

    A MISSING `cwd` RETURNS 1 for the same reason: bash's `cd` failure exits non-zero having printed a diagnostic no port can reproduce, and the finding sets agree either way.
    """
    sys.stdout.flush()
    sys.stderr.flush()
    try:
        return subprocess.run(argv, cwd=str(cwd), check=False).returncode
    except OSError as failure:
        # THE TWO FAILURES ARRIVE AS THE SAME EXCEPTION TYPE, and they must not get the same exit code. Measured:
        #
        #   args=["definitely_not_a_binary_xyz"], cwd="/tmp"
        #       -> FileNotFoundError errno=2 filename='definitely_not_a_binary_xyz'
        #   args=["true"], cwd="/tmp/definitely-not-here-xyz"
        #       -> FileNotFoundError errno=2 filename='/tmp/definitely-not-here-xyz'
        #   args=["true"], cwd="/etc/hostname"
        #       -> NotADirectoryError errno=20 filename='/etc/hostname'
        #
        # `filename` is the only thing that separates the first two, so it is what decides. Bash gives 127 for `command not found` and 1 for a failed `cd`, and matching both is what keeps the exit codes equal.
        if failure.filename == str(cwd):
            return 1
        return 127


def main(argv: list[str] | None = None) -> int:
    """Run the gate. Exit 0 all checks pass, 1 a check failed.

    Seven phases, in the twin's order, each one returning immediately on failure. Written as one function rather than seven, because the ORDER is the gate: phase 6 must not run when phase 5 failed, and a caller assembling seven independent results could get that wrong.

    `--selftest` is intercepted BEFORE any of them. The twin takes no arguments at all, so no caller can be passing this string today.
    """
    args = list(argv or [])
    if args and args[0] == "--selftest":
        return selftest()

    repo_root = paths.repo_root()
    web_dir = repo_root / WEB_REL
    account_dir = repo_root / ACCOUNT_REL

    # Phase 1: Check that frontend dependencies are installed
    log.step("Checking frontend dependencies...")
    if not (web_dir / "node_modules").is_dir():
        log.step("Installing frontend dependencies...")
        # NO `log_error` AROUND THIS ONE. Under `set -e` a failing `npm ci` kills the twin with npm's own output and no gate message; the port returns the same non-zero at the same point. See the port notes.
        rc = run(NPM_CI, web_dir)
        if rc != 0:
            return rc

    # Phase 2: TypeScript typecheck (frontend)
    log.step("Typechecking account portal frontend...")
    if run(TSC, web_dir) != 0:
        log.error("Frontend typecheck failed!")
        return 1
    log.info("Frontend typecheck passed")

    # Phase 3: TypeScript typecheck (backend)
    log.step("Typechecking account portal backend...")
    if run(TSC, account_dir) != 0:
        log.error("Backend typecheck failed!")
        return 1
    log.info("Backend typecheck passed")

    # Phase 3b: TypeScript typecheck (e2e). See the module docstring for the 2026-08-15 TS2352 that rode a branch unseen because Playwright transpiles without typechecking.
    log.step("Typechecking account e2e suite...")
    if run(TSC_E2E, account_dir) != 0:
        log.error("e2e typecheck failed!")
        return 1
    log.info("e2e typecheck passed")

    # Phase 4: Lint (if biome is available)
    log.step("Linting account portal frontend...")
    if run(BIOME, repo_root) != 0:
        # A MISSING BIOME AND REAL FINDINGS PRODUCE THE SAME LINE. See the port notes; carried rather than distinguished.
        log.warn("Frontend lint issues found (non-blocking)")

    # Phase 5: Generate onboarding content from canonical www tutorials
    log.step("Generating account onboarding content...")
    if run(ONBOARDING, repo_root) != 0:
        log.error("Account onboarding content generation failed!")
        return 1
    log.info("Account onboarding content generated")

    # Phase 6: Build frontend
    log.step("Building account portal frontend...")
    if run(VITE_BUILD, web_dir) != 0:
        log.error("Frontend build failed!")
        return 1
    log.info("Frontend build succeeded")

    # Phase 7: Verify output exists
    output_file = repo_root / OUTPUT_REL
    if not output_file.is_file():
        log.error("Expected build output not found: %s" % output_file)
        return 1
    log.info("Build output verified: %s" % output_file)

    return 0


# --------------------------------------------------------------------------- The selftest's stub toolchain ---------------------------------------------------------------------------
#
# THE STUBS ARE REAL EXECUTABLES ON A REAL PATH, not a monkeypatched `run`. A seam invented for the test would prove the seam works; putting `npx` and `npm` on PATH exercises the same `subprocess.run` the gate uses in anger, including the argv vectors, the working directories and the exit codes. That is also exactly how the committed ledger
# `.ci/shadow/w7p2-account-portal.observations.jsonl` drives both sides, so the selftest and the differential agree about what "running the gate" means.

_NPX_STUB = """#!/usr/bin/env bash
# Stub npx. Exit codes come from the environment so one script serves every case.
case "$1 $2 $3" in
    "tsc --noEmit -p") echo "stub: e2e tsc"; exit "${STUB_E2E_RC:-0}" ;;
esac
case "$1 $2" in
    "tsc --noEmit")
        if [ "$(basename "$PWD")" = web ]; then
            echo "stub: frontend tsc"; exit "${STUB_FE_RC:-0}"
        fi
        echo "stub: backend tsc"; exit "${STUB_BE_RC:-0}" ;;
    "biome check") echo "stub: biome"; exit "${STUB_LINT_RC:-0}" ;;
    "vite build") echo "stub: vite"; exit "${STUB_BUILD_RC:-0}" ;;
esac
exit 0
"""

_NPM_STUB = """#!/usr/bin/env bash
# Stub npm. Only the two invocations this gate makes are answered.
if [ "$1" = "ci" ]; then echo "stub: npm ci"; exit "${STUB_CI_RC:-0}"; fi
if [ "$1" = "run" ] && [ "$2" = "build:account-onboarding" ]; then
    echo "stub: onboarding"; exit "${STUB_ONB_RC:-0}"
fi
exit 0
"""


def write_stubs(bindir: pathlib.Path) -> None:
    """Put a stub `npx` and `npm` in `bindir` and make them executable."""
    bindir.mkdir(parents=True, exist_ok=True)
    for name, body in (("npx", _NPX_STUB), ("npm", _NPM_STUB)):
        target = bindir / name
        target.write_text(body, encoding="utf-8")
        target.chmod(0o755)


def seed_tree(root: pathlib.Path, *, node_modules: bool = True, output: bool = True) -> None:
    """The directory shape this gate walks. Both switches are plants.

    `node_modules=False` takes phase 1's install branch, which is the only phase
    that mutates anything. `output=False` takes phase 7's refusal, which is the
    anti-vacuity check and the only phase that looks at an artifact rather than at an exit code.
    """
    (root / WEB_REL / "src").mkdir(parents=True, exist_ok=True)
    (root / ACCOUNT_REL / "e2e").mkdir(parents=True, exist_ok=True)
    (root / ACCOUNT_REL / "e2e" / "tsconfig.json").write_text("{}\n", encoding="utf-8")
    if node_modules:
        (root / WEB_REL / "node_modules").mkdir(parents=True, exist_ok=True)
    out = root / OUTPUT_REL
    out.parent.mkdir(parents=True, exist_ok=True)
    if output:
        out.write_text("<!doctype html>\n", encoding="utf-8")


def selftest() -> int:
    """Plant each failure, prove it reds; remove it, prove it greens.

    BOTH DIRECTIONS FOR EVERY CONTROL. Seven phases means seven ways to fail and exactly one way to pass, so a suite of only plants would be green against a gate that refused everything. The CONTROL below -- every tool succeeding and the artifact present -- is asserted FIRST, and re-asserted after the warning-only plant, because a plant that fires against an already-failing fixture
    proves nothing.
    """
    ctl = Controls("account-portal", floor=20, verbose=True)

    with tempfile.TemporaryDirectory() as tmp:
        base = pathlib.Path(tmp)
        bindir = base / "bin"
        write_stubs(bindir)

        def run_gate(*, node_modules: bool = True, output: bool = True, **codes: str) -> int:
            """Drive `main()` against a fresh fixture with the stubs on PATH."""
            root = base / "tree"
            shutil.rmtree(root, ignore_errors=True)
            root.mkdir(parents=True)
            seed_tree(root, node_modules=node_modules, output=output)
            saved = {key: os.environ.get(key) for key in (paths.ROOT_ENV, "PATH", *codes)}
            os.environ[paths.ROOT_ENV] = str(root)
            os.environ["PATH"] = "%s:%s" % (bindir, saved["PATH"] or "")
            for key, value in codes.items():
                os.environ[key] = value
            try:
                return main([])
            finally:
                for key, value in saved.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value

        # THE CONTROL. Every tool green and the artifact present, so every plant below is measured against a fixture that was passing.
        ctl.check("CONTROL: a healthy tree passes every phase", run_gate(), 0)

        # PLANT: each of the three typechecks, one at a time. Three plants and not one, because a loop that stopped invoking the second and third would look identical to a clean tree.
        ctl.check("PLANT: a frontend typecheck failure is caught", run_gate(STUB_FE_RC="1"), 1)
        ctl.check("PLANT: a backend typecheck failure is caught", run_gate(STUB_BE_RC="2"), 1)
        ctl.check("PLANT: an e2e typecheck failure is caught", run_gate(STUB_E2E_RC="1"), 1)

        # PLANT: the onboarding generation and the build.
        ctl.check("PLANT: an onboarding generation failure is caught", run_gate(STUB_ONB_RC="1"), 1)
        ctl.check("PLANT: a vite build failure is caught", run_gate(STUB_BUILD_RC="1"), 1)

        # PLANT: phase 7, the anti-vacuity check. `vite build` exits 0 and writes nothing; the gate must still refuse.
        ctl.check(
            "PLANT: a green build with NO artifact is refused",
            run_gate(output=False),
            1,
        )

        # ITS MIRROR: the artifact present makes phase 7 pass, so the plant above fired on the artifact and not on something else.
        ctl.check("MIRROR: the artifact present makes phase 7 pass", run_gate(output=True), 0)

        # PLANT: phase 4 is a WARNING. It must NOT change the exit code, which is the whole distinction between it and the six phases around it.
        ctl.check(
            "MIRROR: a lint failure warns and does NOT fail the gate", run_gate(STUB_LINT_RC="1"), 0
        )
        ctl.check(
            "MIRROR: and the tree still passes with lint green, so the plant was the cause",
            run_gate(STUB_LINT_RC="0"),
            0,
        )

        # PLANT: phase 1. An absent node_modules takes the install branch, and a FAILING install kills the gate with no message of its own.
        ctl.check(
            "MIRROR: an absent node_modules installs and carries on",
            run_gate(node_modules=False),
            0,
        )
        ctl.check(
            "PLANT: a failing npm ci stops the gate",
            run_gate(node_modules=False, STUB_CI_RC="1"),
            1,
        )
        ctl.check(
            "MIRROR: the same failing npm ci is NOT reached when node_modules exists",
            run_gate(node_modules=True, STUB_CI_RC="1"),
            0,
        )

        # ORDERING. Phase 2 failing must stop phase 3 from running at all, which is the property a caller assembling seven independent results would lose. Proven by planting a failure in BOTH and checking the second never spoke.
        marker = base / "reached-phase-5"
        onb_stub = bindir / "npm"
        onb_stub.write_text(
            plant(
                _NPM_STUB,
                'echo "stub: onboarding"',
                'echo "stub: onboarding"; : > "%s"' % marker,
            ),
            encoding="utf-8",
        )
        onb_stub.chmod(0o755)
        marker.unlink(missing_ok=True)
        ctl.check("ORDER: a frontend failure stops the run", run_gate(STUB_FE_RC="1"), 1)
        ctl.check("ORDER: and phase 5 was never reached", marker.exists(), False)
        marker.unlink(missing_ok=True)
        ctl.check("ORDER: a healthy tree DOES reach phase 5", run_gate(), 0)
        ctl.check("ORDER: the marker proves it", marker.exists(), True)
        write_stubs(bindir)

        # THE COMMAND VECTORS THEMSELVES. A port that ran `tsc` without `--noEmit` would EMIT files into the tree and still exit 0, and every control above would stay green. Asserted directly.
        ctl.check("ARGV: the typecheck really passes --noEmit", TSC, ["npx", "tsc", "--noEmit"])
        ctl.check(
            "ARGV: the e2e typecheck points at its own tsconfig",
            TSC_E2E,
            ["npx", "tsc", "--noEmit", "-p", "e2e/tsconfig.json"],
        )
        ctl.check(
            "ARGV: the install states --ignore-scripts at the call site",
            NPM_CI,
            ["npm", "ci", "--ignore-scripts"],
        )

        # A MISSING BINARY IS 127, NOT A TRACEBACK. Driven against an empty PATH so the failure is real rather than simulated.
        saved_path = os.environ.get("PATH", "")
        os.environ["PATH"] = str(base / "definitely-not-here")
        try:
            ctl.check("TOOLING: an absent npx yields 127, not an exception", run(TSC, base), 127)
        finally:
            os.environ["PATH"] = saved_path
        ctl.check(
            "TOOLING: an absent working directory yields 1, not an exception",
            run(["true"], base / "nope" / "deeper"),
            1,
        )
        ctl.check(
            "TOOLING: a cwd that is a FILE also yields 1",
            run(["true"], base / "bin" / "npx"),
            1,
        )

    return 0 if ctl.report() else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
