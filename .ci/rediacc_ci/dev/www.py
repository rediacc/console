"""`./run.sh dev` -- start the www (marketing site) development server.

WHAT MOVED. `dev()` at `.ci/legacy/run-legacy.sh:73-84` and its dispatch arm. Four statements, and the reason the port is worth its own file rather than an inline branch in the router is that three of the four are the parts a transcription gets wrong: which stream the step line lands on, whether a failing precondition still reaches `npm`, and whose process the dev server ends up
being.

WHAT DID NOT MOVE, AND WHY THAT IS THE RIGHT SCOPE. `check_node_version` and `ensure_deps` live in `.ci/lib/local-common.sh`, which `devbox`, `account`, `service` and `rdc.sh` also call. They are reached through `rediacc_ci.setup.bridge`, so the same bytes run and the behaviour is not merely preserved, it is identical. That module's own header names these two functions among the
six it exists for; this is the second verb through the same seam rather than a second seam.

-----------------------------------------------------------------------------
THE FOUR THINGS THIS FILE IS JUDGED ON
-----------------------------------------------------------------------------
  ORDER. `check_node_version`, then the step line, then `ensure_deps`, then `npm`. The step line sits BETWEEN the version check and the install, so a port that hoisted it to the top would announce a server it is about to refuse to start. `.ci/rediacc_ci/tests/test_dev_www.py` traces the sequence with both sides' externals recorded rather than comparing two tables.

  SHORT-CIRCUIT. The twin's body runs under `set -euo pipefail`, so a non-zero from either precondition aborts before `npm` is reached and the script exits with that code. `return rc` below is that `set -e`, spelled out. A port that ran `npm` anyway would look correct on a healthy machine and start a dev server against an uninstalled tree on every other one.

  THE STEP LINE IS ON STDERR. `log_step` is `echo -e ... >&2` (`.ci/scripts/lib/common.sh:47-49`), and `rediacc_ci.log` writes to stderr for the same reason. The 2026-09-06 emit-advisory incident was a stream swap and nothing about it is visible to a comparison that merges the two.

  THE SERVER REPLACES THIS PROCESS. `os.execvp`, not `subprocess.run`. The dev server is a long-running foreground program that an operator stops with Ctrl-C, and a Python parent in the middle of that turns one SIGINT into a KeyboardInterrupt traceback beside npm's own shutdown. The router already `exec`s for this reason (`run.sh:51`, `:109`); the chain stays one process.

-----------------------------------------------------------------------------
ARGUMENTS ARE IGNORED, AS THEY WERE
-----------------------------------------------------------------------------
The twin's arm is `dev) dev ;;` with no `shift` and a body that reads none of them, so `./run.sh dev anything` has always started the server and dropped the word. Rejecting it here would be a better command line and a different one, and equivalence is what this change is allowed to claim. The differential drives the case rather than leaving the reading to a comment.
"""

from __future__ import annotations

import os

from rediacc_ci import log, paths
from rediacc_ci.setup import bridge

# Byte for byte the twin's `log_step "Starting www development server"`.
STEP_MESSAGE = "Starting www development server"

# `npm run dev -w @rediacc/www`, as argv. NOT run through a shell: there is nothing to expand, and a shell here would be a second place for a quoting rule to live.
NPM_ARGV = ("npm", "run", "dev", "-w", "@rediacc/www")

# What bash reports for a command it cannot find. The twin's own message names a line number inside `run-legacy.sh`, which a port cannot and should not reproduce; the exit code is the part callers and CI act on, so that is what is kept identical and the text names the program instead.
EXIT_NOT_FOUND = 127


def main(argv: list[str]) -> int:
    """Run the twin's four statements. Returns an exit code, or never returns."""
    del argv  # see the module docstring: the twin reads none of them either
    root = paths.repo_root()

    rc = bridge.call("check_node_version", root)
    if rc != 0:
        return rc

    log.step(STEP_MESSAGE)

    rc = bridge.call("ensure_deps", root)
    if rc != 0:
        return rc

    try:
        os.execvp(NPM_ARGV[0], list(NPM_ARGV))  # noqa: S606 -- forwarding exec, same shape as the twin's
    except OSError as exc:
        # REACHED ONLY WHEN THE EXEC ITSELF FAILS, which is npm absent from PATH or not executable. Everything after a successful execvp belongs to npm, so there is no fall-through to guard against.
        log.error("%s: %s" % (NPM_ARGV[0], exc.strerror or exc))
        return EXIT_NOT_FOUND
    return 0  # pragma: no cover - unreachable; execvp either replaces us or raises
