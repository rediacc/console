#!/usr/bin/env python3
"""Port of `.ci/scripts/quality/browser-smoke.sh`.

THE REGISTERED GATE IS `check:ci-browser-smoke`, wired at `package.json:265`
(`"check:ci-browser-smoke": ".ci/scripts/quality/browser-smoke.sh"`), declared
in `scripts/ci-runner/manifest.ts:4056-4060` with `gate: true` and
`leaves: ['.ci/scripts/quality/browser-smoke.sh']`, and run in CI as the step
named "Browser smoke" in job `quality-www-build` of
`.github/workflows/ci-quality.yml`. The twin's own `# ---- gate ----` header
agrees (`step: Browser smoke`, `needs: node`, `selftest: true`, `lane:
quality-www-build`, `slow: true`). THE BASH TWIN REMAINS THE CALL SITE: this
port is an alternative proven equivalent, and moving the npm script onto it is
a separate, later, explicitly tracked step. Nothing here edits package.json,
the manifest or the workflow.

WHAT THE SCRIPT ACTUALLY IS: a launcher, not a gate. All the judging lives in
`scripts/gates/check-browser-smoke.ts`, which is TypeScript and is NOT being
ported. What is ported is the decision of WHERE that gate runs -- inside the
official Playwright container by default, directly against a local Chromium
when `REDIACC_SMOKE_NO_DOCKER=1` or when docker is absent -- and the derivation
of the image tag from the installed playwright package rather than a hand-typed
pin, which is the twin's stated reason for existing.

THE TWIN'S FOUR REASONS ARE ITS BODY, NOT DECORATION, so they are kept here
rather than compressed into "runs in a container":

  * WHY A CONTAINER. The gate drives a real browser. On a bare GitHub runner
    that means `npx playwright install --with-deps chromium` on every run: slow,
    and it fails differently depending on what the runner image happens to ship.
    The official image has the browser and every system library already baked
    in, so the gate behaves identically on a runner, in a devcontainer, and on
    the operator's laptop.
  * WHY mcr.microsoft.com AND NOT DOCKER HUB. Microsoft Container Registry
    serves this image anonymously and does NOT rate limit, so this needs no
    `docker login` and cannot fail with "toomanyrequests" on a busy CI day.
    Every authenticated pull in this repo goes to ghcr.io with `github.token`
    (see ct-install-methods.yml); neither registry needs Docker Hub credentials,
    and this gate deliberately keeps it that way.
  * THE IMAGE TAG IS DERIVED, NEVER PINNED BY HAND. Playwright refuses to run
    when the npm package and the browser build disagree, so the tag is read from
    the installed package at run time. Bumping the dependency moves the image
    with it and cannot drift.
  * `--ipc=host`. Chromium crashes on the default 64MB `/dev/shm` in a
    container. The workspace is MOUNTED rather than copied so the gate sees the
    `packages/www/dist` that was just built.

HOW THIS DIFFERS FROM ITS NEAR-TWIN `page_density.py`, because the two launchers
look interchangeable and are not. `page-density.sh` mounts the repo at its own
absolute path, runs as root, and passes `-e CI=true`. `browser-smoke.sh` mounts
at `/work`, drops to the invoking user with `-u "$(id -u):$(id -g)"`, and
compensates for that non-root user with `-e HOME=/tmp` and
`-e npm_config_cache=/tmp/.npm` (a non-root user cannot write root's `$HOME` or
npm cache inside the image). Neither set is copied from the other here; each
port reproduces exactly its own twin's argv.

`exec`, NOT `subprocess.run`, ON BOTH FINAL BRANCHES. The twin's last statement
is `exec` in every path, so argv, stdin, stdout, stderr, signals and the exit
status all belong to the child. `os.execvp` is the same shape, for the same
reason `rediacc_ci.deploy.upload_media_to_r2` gives: a subprocess wrapper is a
second process watching the first, and it leaves a stray parent behind when the
caller signals what it believes is the gate.

`id` IS SHELLED OUT, DELIBERATELY, WHERE `os.getuid()` WOULD BE THE OBVIOUS
PYTHON. This is the one place a "better" port would silently repair a real
defect in the twin, and this campaign reproduces defects rather than fixing them
on the bash side. See DEFECT 1 below: `os.getuid()` cannot fail, so a port using
it would be a STRICTLY DIFFERENT program on the path where `id` is missing, and
the differential would have nothing to compare. `id_value()` therefore runs the
same binary the twin runs and substitutes its stdout the same way `$(...)` does.

REPRODUCED DEFECT 1 (`browser-smoke.sh:51`, `-u "$(id -u):$(id -g)"`): A FAILED
COMMAND SUBSTITUTION INSIDE AN ARGUMENT LIST DOES NOT ABORT under `set -euo
pipefail`. If `id` is not on PATH, bash prints `id: command not found` TWICE,
substitutes the empty string for both, and hands docker a literal `-u :`, which
docker rejects with its own unrelated-looking error. The script's own exit
status up to that point stays 0.

  Confirmed by DRIVING the twin, not by reading it. Repro, 2026-09-14:

      FIX=$(mktemp -d); ln -s "$(command -v dirname)" "$FIX/dirname"
      printf '#!/usr/bin/python3\\nprint("1.55.0")\\n' > "$FIX/node"
      printf '#!/usr/bin/python3\\nimport sys\\nprint(" ".join(sys.argv[1:]))\\n' \\
        > "$FIX/docker"
      chmod 755 "$FIX/node" "$FIX/docker"
      env -i PATH="$FIX" HOME=/tmp /bin/bash \\
        .ci/scripts/quality/browser-smoke.sh; echo "exit=$?"

  prints two `browser-smoke.sh: line 50: id: command not found` lines, then
  `run --rm --ipc=host -u : ...`, then `exit=0`. Bash says line 50 rather than
  51 because it attributes a substitution to the line the whole `exec docker
  run` command STARTS on; the `-u` argument itself is on line 51.

  The port reproduces this exactly: same two stderr lines in the same order,
  same `-u :`, same handoff to docker, same exit 0. See
  `test_missing_id_yields_a_bare_colon_on_both_sides`. NOT FIXED HERE; the fix
  belongs to a later cutover phase and would be a guarded `-u`, or `id` added to
  the gate header's `needs:`.

REPRODUCED DEFECT 2 (`browser-smoke.sh:4`, `# needs: node`): the header declares
`node` only, while the DEFAULT branch also requires `docker` and `id`. `node` is
the honest declaration for the escape-hatch branch and an incomplete one for the
branch that actually runs in CI. The port carries the identical header claim by
carrying no header at all (it is not a registered gate), and this paragraph is
the record.

THREE DOCUMENTED DIVERGENCES, ALL IN MESSAGE TEXT ONLY, NEVER IN EXIT CODE:

  1. A MISSING `node`. The twin's `PW_VERSION="$(node -p ...)"` fails with
     bash's own `<script>: line 44: node: command not found` and exit 127. That
     text carries a bash line number, which is not worth reproducing (same
     ruling as the `${VAR:?msg}` twins in `rediacc_ci.deploy`). This port prints
     `browser-smoke.py: node: command not found` and exits 127.
  2. A MISSING `npx` or `docker` at the `exec`. The twin gets bash's
     `<script>: line NN: exec: npx: not found`, exit 127. This port prints
     `browser-smoke.py: exec: npx: not found`, exit 127.
  3. A MISSING `id` (defect 1 above). The twin prints
     `<script>: line 50: id: command not found` twice; this port prints
     `browser-smoke.py: id: command not found` twice. Same stream, same count,
     same order, same resulting `-u :`.

  The exit code, the stream (stderr) and the named binary all match in every
  case; only the wrapper's own prefix differs.
  `test_quality_browser_smoke.py` drives both and asserts agreement on exit code
  plus the presence of the binary name, and the ledger's `--finding-re` matches
  on the substance rather than the prefix.

NODE'S STDERR IS INHERITED, NOT CAPTURED, because `$(...)` captures stdout
only. A port that used `capture_output=True` would swallow whatever node says
about a broken playwright install -- which is precisely the failure this line
exists to surface -- and would still exit with the same code, so nothing else
in the differential would notice. `test_node_stderr_is_not_swallowed` is the
control for that. The same reasoning applies to `id`.

EXIT STATUS IS IGNORED FOR `id` AND HONOURED FOR `node`, which looks
inconsistent and is exactly what bash does. `PW_VERSION="$(node ...)"` is a
STANDALONE ASSIGNMENT, so under `set -e` its exit status is the command's and a
failure aborts. `$(id -u)` sits inside another command's argument list, so its
status is discarded and only its stdout matters -- bash substitutes whatever the
command printed even when it printed it and then failed.

TRAILING NEWLINES ARE STRIPPED THE WAY COMMAND SUBSTITUTION STRIPS THEM:
`rstrip("\\n")`, not `.strip()`. `$(...)` removes trailing newlines and nothing
else, so a version string with a leading space would keep it on both sides.

`REPO_ROOT` is `paths.repo_root()`, which is `<file>/../../..` exactly as the
twin's `SCRIPT_DIR/../../..` is, plus the package-wide `$REDIACC_CI_ROOT`
override the twin has no equivalent for. That override is the only way the two
roots can differ, and it exists so a harness can point the whole program at a
fixture; see `paths.py`'s docstring.

K=5 LEDGER: `.ci/shadow/w7p6-browser-smoke.observations.jsonl`.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys

from rediacc_ci import paths

SELF = "browser-smoke.py"

# The gate the launcher launches, and its one argument. A list rather than a
# string so neither side can disagree about word splitting.
GATE_ARGS = ("scripts/gates/check-browser-smoke.ts", "--selftest")

NO_DOCKER_ENV = "REDIACC_SMOKE_NO_DOCKER"

NOTE_NO_DOCKER = "note: docker not found, running the gate directly (needs a local Chromium)"

# The registry the twin names, kept as a constant so the derivation is readable
# at a glance: only the VERSION comes from the installed package.
IMAGE_TEMPLATE = "mcr.microsoft.com/playwright:v%s-noble"

PW_VERSION_EXPR = "require('playwright/package.json').version"

# Where the workspace is bound inside the container. The twin hard-codes this
# rather than mirroring the host path (its sibling page-density.sh does the
# opposite); `check-browser-smoke.ts` only ever prints `path.relative(ROOT, ...)`
# so nothing host-meaningless escapes, but the two launchers do differ here.
WORKDIR = "/work"


def image_for(pw_version: str) -> str:
    """`mcr.microsoft.com/playwright:v<version>-noble`, the twin's line 45."""
    return IMAGE_TEMPLATE % pw_version


def docker_argv(root: str, image: str, uid: str, gid: str) -> list[str]:
    """The twin's final `docker run` invocation, token for token (lines 50-57).

    `--ipc=host` is load-bearing and the twin says why in a comment kept here:
    Chromium crashes on the default 64MB `/dev/shm` in a container. `-u` drops
    to the invoking user so files the gate writes into the mounted workspace are
    not owned by root afterward, and `HOME` plus `npm_config_cache` are
    redirected to `/tmp` because that non-root user cannot write the image's
    baked-in home or npm cache.
    """
    return [
        "docker",
        "run",
        "--rm",
        "--ipc=host",
        "-u",
        "%s:%s" % (uid, gid),
        "-e",
        "HOME=/tmp",
        "-e",
        "npm_config_cache=/tmp/.npm",
        "-v",
        "%s:%s" % (root, WORKDIR),
        "-w",
        WORKDIR,
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


def id_value(flag: str, env: dict[str, str] | None = None) -> str:
    """`$(id <flag>)` as bash performs it, NOT `os.getuid()`.

    Two properties of `$(...)` inside an argument list are reproduced, and both
    are why this is not `str(os.getuid())`:

      * The exit status is DISCARDED. Whatever the command wrote to stdout is
        substituted even if it then failed.
      * A missing command yields the EMPTY STRING and does not abort the script,
        even under `set -euo pipefail`. That is reproduced defect 1.

    `id`'s stderr is inherited, as `$(...)` inherits it.
    """
    try:
        proc = subprocess.run(
            ["id", flag],
            stdout=subprocess.PIPE,
            stderr=None,
            text=True,
            check=False,
            env=env,
        )
    except FileNotFoundError:
        # bash: `<script>: line 50: id: command not found`, and the script
        # carries on with an empty substitution. See divergence 3.
        print("%s: id: command not found" % SELF, file=sys.stderr)
        return ""
    # `$(...)` strips TRAILING newlines and nothing else.
    return proc.stdout.rstrip("\n")


def playwright_version(env: dict[str, str] | None = None) -> str:
    """`node -p "require('playwright/package.json').version"`, stdout only.

    Raises SystemExit with node's own exit code on failure, matching `set -e`
    on a failed command substitution IN A STANDALONE ASSIGNMENT (contrast
    `id_value`, whose substitution sits in an argument list and so cannot
    abort). node's stderr is INHERITED so its diagnostic reaches the caller
    unaltered.
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
        # bash: `<script>: line 44: node: command not found`, exit 127.
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
    print("browser smoke: %s (tag derived from the installed playwright package)" % image)
    sys.stdout.flush()
    # ORDER MATTERS AND IS THE TWIN'S: the echo happens on line 46, and the two
    # `id` substitutions are expanded on line 51 as the exec's argv is built.
    # A port that resolved the ids first would still exec the same command and
    # would still exit the same way, and only the call log would show it.
    uid = id_value("-u")
    gid = id_value("-g")
    return _exec(docker_argv(root, image, uid, gid))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
