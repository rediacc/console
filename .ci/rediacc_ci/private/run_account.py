#!/usr/bin/env python3
"""Port of `.ci/scripts/private/run-account.sh`, the registered gate `check:ci-account-server`.

A thin wrapper: check that the `private/account` submodule is checked out, install its dependencies if nothing else has, and run one stage. It reimplements nothing that `private/account`'s own npm scripts do.

THE BASH TWIN REMAINS THE REGISTERED GATE. `package.json:250` spells `"check:ci-account-server": ".ci/scripts/private/run-account.sh test"`, `scripts/ci-runner/manifest.ts:3541` names that same file as the gate's `leaf`, and `.github/workflows/ci-quality.yml:2204` runs it. THIS MODULE CARRIES NO `---- gate ----` HEADER on purpose: the header is what `scripts/gate-bind.ts` reads,
and a second file claiming `id: check:ci-account-server` would give one gate two owners and the parity meta-gates would be right to complain. Cutover is a separate, later, driver-only step.

-----------------------------------------------------------------------------
THE SUBMODULE GUARD HAS THREE ARMS AND THE MIDDLE ONE IS THE WHOLE POINT
-----------------------------------------------------------------------------
    package.json present    -> run the stage
    absent, `CI` == "true"  -> three `log_error` lines and EXIT 1
    absent, otherwise       -> two `log_warn` lines and EXIT 0

The twin's own comment says why the middle arm exists: `check:ci-account-server` is a gate in `ci-quality.yml`, and a silent exit 0 there means the account suite never ran while the job reported green.

IT IS HAND-ROLLED, NOT `require_submodule`. `common.sh:488-502` already answers this question with the same three arms, and the twin does not call it: it tests `-f "$ACCOUNT_DIR/package.json"` itself and writes five sentences of its own. `rediacc_ci.core.common.require_submodule` is therefore NOT used here either, because its wording differs ("Account server not available at <dir>,
skipping." against "<label> not available, skipping (this is a hard failure in CI)") and a port that swapped one for the other would change what a caller greps. The duplication belongs to the twin and is named rather than repaired.

`CI` is tested as the LITERAL `"${CI:-}" == "true"`, so `CI=1` and
`GITHUB_ACTIONS=true` with `CI` unset both take the LOCAL arm. Driven; the
differential pins both.

THE MARKER TEST IS `-f "$ACCOUNT_DIR/package.json"`, so an uninitialised submodule's empty directory takes the ABSENT arm, unlike `run-renet.sh`'s `-e` on the directory itself.

-----------------------------------------------------------------------------
`npm ci` RUNS BEFORE THE STAGE IS VALIDATED, AND THAT IS A REAL DEFECT
-----------------------------------------------------------------------------
The twin's order is `cd`, then `npm ci` if `node_modules` is absent, then the `case`. So `run-account.sh deploy` and `run-account.sh bogus` each perform a full clean install of the account server's dependency tree and only then refuse. Driven 2026-09-14 with a recording `npm` on a scratch PATH: both print `npm ci` before their refusal.

REPRODUCED, NOT FIXED, and the differential's `calls` comparison is what makes it visible: moving the validation earlier in the port would show up as a missing `npm ci` in the call log rather than as a silent improvement. Reported as a finding against the twin; reordering it is a cutover-box decision.

-----------------------------------------------------------------------------
THE `deploy` STAGE REFUSES, AND THE REFUSAL IS THE FEATURE
-----------------------------------------------------------------------------
Five `log_error` lines and exit 1. The twin records why: this stage used to run `npx wrangler deploy` from `private/account` with no `--config`, picking up that directory's local-dev `wrangler.toml`, whose worker name and D1 id are live nowhere, so the deploy published an orphan worker. Nothing invokes the stage. The five lines are reproduced verbatim, including the two-space
indents, because they name the seven real configs and the script that resolves them.

-----------------------------------------------------------------------------
WHAT IS SHELLED OUT TO
-----------------------------------------------------------------------------
`npm ci` and `npm run test`, each with the parent's stdout and stderr, and their exit status returned unchanged under `set -e`. The differential puts a recording `npm` on a scratch PATH and compares its argv AND its cwd, because a port that printed the same banner while running npm from the console root instead of `private/account` would satisfy a stdout-only comparison and test
the wrong
package.

`cd "$ACCOUNT_DIR"` really is a `cd`: `node_modules` is then tested RELATIVE to it, and both npm invocations inherit it. `os.chdir` is used rather than a
`cwd=` argument for exactly that reason.

-----------------------------------------------------------------------------
ENVIRONMENT
-----------------------------------------------------------------------------
One variable, `CI`, read with `os.environ.get("CI", "")` at the call site and
never through an `env = dict(os.environ)` alias, so the env-registry AST scanner
can see the name.

CONSOLE ROOT comes from this file's own location (`parents[3]`), matching the twin's `get_repo_root` (common.sh:205-210). `rediacc_ci.paths.repo_root()` is deliberately not used, on the `run_renet.py` precedent: it honours `$REDIACC_CI_ROOT` and the twin honours nothing.
"""

from __future__ import annotations

import inspect
import os
import pathlib
import subprocess
import sys

from rediacc_ci import log

# `STAGE="${1:-quality}"`. Three are handled; anything else is refused by name.
DEFAULT_STAGE = "quality"
TEST_STAGES = ("quality", "test")
DEPLOY_STAGE = "deploy"

# `[[ "${CI:-}" == "true" ]]`: the literal, not `is_ci()`.
CI_TRUE = "true"

# The five lines the `deploy` stage refuses with, verbatim from the twin including the two-space continuation indents.
DEPLOY_REFUSAL = (
    "This stage cannot deploy the account server.",
    "Production and edge are the seven configs under workers/account/:",
    "  wrangler.{eu,us,asia}.toml, wrangler.edge-{eu,us,asia}.toml, wrangler.bench.toml",
    "Deploy through the script that resolves them:",
    "  .ci/scripts/deploy/deploy-account.sh --region <eu|us|asia> [--target edge]",
)


def console_root() -> pathlib.Path:
    """The repository root, derived the way the twin derives it: from the subject file's own path, never from cwd and never from an env override."""
    # This file: <root>/.ci/rediacc_ci/private/run_account.py
    return pathlib.Path(__file__).resolve().parents[3]


def _shell_diagnostic(message: str) -> str:
    """`<$0>: line <n>: <message>`, the shape bash puts on a script's stderr.

    The line number is the CALLER's, taken from the live frame rather than hard-coded, so it cannot go stale when this file is reflowed.
    """
    frame = inspect.currentframe()
    back = frame.f_back if frame is not None else None
    lineno = back.f_lineno if back is not None else 0
    return "%s: line %d: %s" % (sys.argv[0], lineno, message)


def stage_of(argv: list[str]) -> str:
    """`"${1:-quality}"`: unset OR EMPTY yields `quality`, and `$2` onward is
    ignored. `run-account.sh test deploy` runs the tests and says nothing about the second word; reproduced deliberately, not endorsed."""
    return argv[0] if argv and argv[0] else DEFAULT_STAGE


def _npm(args: list[str]) -> int:
    """One `npm` invocation under `set -e`: its status, or bash's 127.

    A missing `npm` is bash's `command not found` on STDERR and status 127, which is what a caller sees today and what the differential pins. The port has no shell to produce that line, so it is composed by hand.
    """
    try:
        return subprocess.run(["npm", *args], check=False).returncode
    except FileNotFoundError:
        print(_shell_diagnostic("npm: command not found"), file=sys.stderr, flush=True)
        return 127


def main(argv: list[str]) -> int:
    stage = stage_of(argv)
    account_dir = console_root() / "private" / "account"

    # A missing submodule must not read as "tests passed".
    if not (account_dir / "package.json").is_file():
        if os.environ.get("CI", "") == CI_TRUE:
            log.error(
                "Account server not available at %s (submodule not checked out)." % account_dir
            )
            log.error("CI=true: failing rather than reporting success for tests that never ran.")
            log.error("Check out the submodule, or drop this gate from the job that needs it.")
            return 1
        log.warn("Account server not available at %s, skipping." % account_dir)
        log.warn("CI is not 'true', so absence is a soft skip here; in CI it is a hard failure.")
        return 0

    try:
        os.chdir(account_dir)
    except OSError as exc:
        # Unreachable in practice: `package.json` was just seen inside this directory. Here so a race (the submodule vanishing between the two syscalls) exits like the shell rather than raising a traceback.
        print(
            _shell_diagnostic("cd: %s: %s" % (account_dir, exc.strerror)),
            file=sys.stderr,
            flush=True,
        )
        return 1

    # RELATIVE to the directory just entered, exactly as `[[ ! -d node_modules ]]` is. BEFORE the stage is validated -- see the docstring; that ordering is a defect being reproduced, and the call log is where it stays visible.
    if not pathlib.Path("node_modules").is_dir():
        rc = _npm(["ci"])
        if rc != 0:
            return rc

    if stage in TEST_STAGES:
        log.step("Running account tests...")
        # `set -e`: npm's own status, unchanged, and nothing added on success.
        return _npm(["run", "test"])

    if stage == DEPLOY_STAGE:
        for line in DEPLOY_REFUSAL:
            log.error(line)
        return 1

    log.error("Unknown stage: %s" % stage)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
