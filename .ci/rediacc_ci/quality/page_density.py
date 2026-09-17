#!/usr/bin/env python3
"""Port of `.ci/scripts/quality/page-density.sh`.

THE REGISTERED GATE IS `check:ci-page-density`, wired at `package.json:266`
(`"check:ci-page-density": ".ci/scripts/quality/page-density.sh"`), declared in
`scripts/ci-runner/manifest.ts:4082-4094` with `gate: true`, `slow: true` and
`leaves: ['.ci/scripts/quality/page-density.sh']`, and run in CI as the step
named "Page density" in job `quality-www-build` of
`.github/workflows/ci-quality.yml`. The twin's own `# ---- gate ----` header
agrees (`step: Page density`, `needs: node`, `selftest: true`, `lane:
quality-www-build`, `slow: true`). THE BASH TWIN REMAINS THE CALL SITE: this
port is an alternative proven equivalent, and moving the npm script onto it is
a separate, later, explicitly tracked step. Nothing here edits package.json,
the manifest or the workflow.

WHAT THE SCRIPT ACTUALLY IS: a launcher, not a gate. All the judging lives in
`scripts/gates/check-page-density.ts`, which is TypeScript and is NOT being
ported. What is ported is the decision of WHERE that gate runs -- inside the
official Playwright container by default, directly against a local Chromium
when `REDIACC_SMOKE_NO_DOCKER=1` or when docker is absent -- and the derivation
of the image tag from the installed playwright package rather than a hand-typed
pin, which is the twin's stated reason for existing.

`exec`, NOT `subprocess.run`, ON BOTH FINAL BRANCHES. The twin's last statement
is `exec` in every path, so argv, stdin, stdout, stderr, signals and the exit
status all belong to the child. `os.execvp` is the same shape, for the same
reason `rediacc_ci.deploy.upload_media_to_r2` gives: a subprocess wrapper is a
second process watching the first, and it leaves a stray parent behind when the
caller signals what it believes is the gate.

TWO DOCUMENTED DIVERGENCES, BOTH IN MESSAGE TEXT ONLY, NEVER IN EXIT CODE:

  1. A MISSING `node`. The twin's `PW_VERSION="$(node -p ...)"` fails with
     bash's own `<script>: line 36: node: command not found` and exit 127. That
     text carries a bash line number, which is not worth reproducing (same
     ruling as the `${VAR:?msg}` twins in `rediacc_ci.deploy`). This port
     prints `page-density.py: node: command not found` and exits 127.
  2. A MISSING `npx` or `docker` at the `exec`. The twin gets bash's
     `<script>: line NN: exec: npx: not found`, exit 127. This port prints
     `page-density.py: exec: npx: not found`, exit 127.

  The exit code, the stream (stderr) and the named binary all match; only the
  wrapper's own prefix differs. `test_quality_page_density.py` drives both and
  asserts agreement on exit code plus the presence of the binary name, and the
  ledger's `--finding-re` matches on the substance rather than the prefix.

NODE'S STDERR IS INHERITED, NOT CAPTURED, because `$(...)` captures stdout
only. A port that used `capture_output=True` would swallow whatever node says
about a broken playwright install -- which is precisely the failure this line
exists to surface -- and would still exit with the same code, so nothing else
in the differential would notice. `test_node_stderr_is_not_swallowed` is the
control for that.

TRAILING NEWLINES ARE STRIPPED THE WAY COMMAND SUBSTITUTION STRIPS THEM:
`rstrip("\\n")`, not `.strip()`. `$(...)` removes trailing newlines and nothing
else, so a version string with a leading space would keep it on both sides.

`REPO_ROOT` is `paths.repo_root()`, which is `<file>/../../..` exactly as the
twin's `SCRIPT_DIR/../../..` is, plus the package-wide `$REDIACC_CI_ROOT`
override the twin has no equivalent for. That override is the only way the two
roots can differ, and it exists so a harness can point the whole program at a
fixture; see `paths.py`'s docstring.

K=5 LEDGER: `.ci/shadow/w7p6-page-density.observations.jsonl`.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys

from rediacc_ci import paths

SELF = "page-density.py"

# The gate the launcher launches, and its one argument. A list rather than a string so neither side can disagree about word splitting.
GATE_ARGS = ("scripts/gates/check-page-density.ts", "--selftest")

NO_DOCKER_ENV = "REDIACC_SMOKE_NO_DOCKER"

NOTE_NO_DOCKER = "note: docker not found, running the gate directly (needs a local Chromium)"

# The registry the twin names, kept as a constant so the derivation is readable at a glance: only the VERSION comes from the installed package.
IMAGE_TEMPLATE = "mcr.microsoft.com/playwright:v%s-noble"

PW_VERSION_EXPR = "require('playwright/package.json').version"


def image_for(pw_version: str) -> str:
    """`mcr.microsoft.com/playwright:v<version>-noble`, the twin's line 38."""
    return IMAGE_TEMPLATE % pw_version


def docker_argv(root: str, image: str) -> list[str]:
    """The twin's final `docker run` invocation, token for token.

    `--ipc=host` is load-bearing and the twin says why in a comment kept here:
    Chromium crashes on the default 64MB `/dev/shm` in a container. The bind
    mount uses the SAME path inside and outside so any path the gate prints is
    meaningful on the host.
    """
    return [
        "docker",
        "run",
        "--rm",
        "--ipc=host",
        "-v",
        "%s:%s" % (root, root),
        "-w",
        root,
        "-e",
        "CI=true",
        image,
        "npx",
        "tsx",
        *GATE_ARGS,
    ]


def _exec(argv: list[str]) -> int:
    """`exec argv`. Returns 127 with bash's own exit code if it cannot start."""
    try:
        os.execvp(argv[0], argv)  # noqa: S606 -- forwarding exec, same shape as the twin's
    except OSError:
        # bash: `<script>: line NN: exec: npx: not found`, exit 127. The prefix
        # carries a line number this port does not reproduce; see the module
        # docstring's divergence 2.
        print("%s: exec: %s: not found" % (SELF, argv[0]), file=sys.stderr)
        return 127
    return 1  # unreachable: execvp replaces this process on success


def playwright_version(env: dict[str, str] | None = None) -> str:
    """`node -p "require('playwright/package.json').version"`, stdout only.

    Raises SystemExit with node's own exit code on failure, matching `set -e`
    on a failed command substitution. node's stderr is INHERITED so its
    diagnostic reaches the caller unaltered.
    """
    try:
        proc = subprocess.run(
            ["node", "-p", PW_VERSION_EXPR],
            stdout=subprocess.PIPE,
            stderr=None,
            text=True,
            check=False,
            env=env,
        )
    except FileNotFoundError:
        # bash: `<script>: line 36: node: command not found`, exit 127.
        print("%s: node: command not found" % SELF, file=sys.stderr)
        raise SystemExit(127) from None
    if proc.returncode != 0:
        raise SystemExit(proc.returncode)
    # `$(...)` strips TRAILING newlines and nothing else.
    return proc.stdout.rstrip("\n")


def main(argv: list[str]) -> int:
    del argv
    root = str(paths.repo_root())
    os.chdir(root)

    no_docker = os.environ.get(NO_DOCKER_ENV, "0")
    if no_docker == "1" or shutil.which("docker") is None:
        if no_docker != "1":
            print(NOTE_NO_DOCKER)
            sys.stdout.flush()
        return _exec(["npx", "tsx", *GATE_ARGS])

    image = image_for(playwright_version())
    print("page density: %s (tag derived from the installed playwright package)" % image)
    sys.stdout.flush()
    return _exec(docker_argv(root, image))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
