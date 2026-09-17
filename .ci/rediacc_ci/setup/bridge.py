"""The bash this port deliberately does NOT own, reached through one seam.

WHY A BRIDGE AND NOT MORE PORT. `setup()` calls fifteen things. Nine of them are
`.ci/lib/setup.sh` and are ported in `host.py`. The other six live in
`.ci/lib/local-common.sh` and `.ci/lib/devbox.sh`, which this box does not touch
and which other verbs (`devbox`, `account`, `service`, `rdc.sh`) still call:

    check_node_version      .ci/lib/local-common.sh:418
    ensure_host_tools       .ci/lib/local-common.sh:587
    ensure_bashcov_sup      .ci/lib/local-common.sh:566
    ensure_deps             .ci/lib/local-common.sh:203
    ensure_docker_installed .ci/lib/local-common.sh:669
    devbox_*                .ci/lib/devbox.sh

Porting those here would either DUPLICATE them, which is how two
implementations drift, or move them, which is a different box with a much larger
blast radius. So `setup` calls the same shell functions the same way, and the
behaviour of those six is not merely preserved, it is IDENTICAL: the same bytes
run. That is a stronger claim than any differential could make about a rewrite,
and it is the honest scope of "port the setup verb".

THE ENTRYPOINT IS ALWAYS THE SAME SHELL PROGRAM. Sourcing `run-legacy.sh` pulls
in `constants.sh`, `toolchain.sh`, `local-common.sh`, `service.sh` and
`setup.sh` in that order and defines nothing else, because that file ends with
`if [[ "${BASH_SOURCE[0]}" == "${0}" ]]`. `devbox.sh` is sourced on top, exactly
as the `setup()` arm does at `.ci/legacy/run-legacy.sh:583`.

STREAMS ARE NOT CAPTURED BY DEFAULT. `ensure_deps` compiles native modules and
`devbox_up` prints a probed route table; both take minutes and both are the
thing an operator watches. A bridge that captured them would turn a live install
into a silent hang, so `call()` inherits the streams and only `capture()` does
not. The two are different functions rather than a flag, because a flag is a
thing a caller gets wrong once and never notices.
"""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - `pathlib` is only ever an annotation here
    import pathlib

# Sourced in the order `.ci/legacy/run-legacy.sh:41-49` sources them, minus the ones it pulls in transitively. Kept as data so the preamble is one string in one place and a reader can see the whole environment a bridged call runs in.
PRELUDE = (
    "set -euo pipefail",
    'source "$ROOT_DIR/.ci/legacy/run-legacy.sh"',
    'source "$ROOT_DIR/.ci/lib/devbox.sh"',
)

# The names `setup()` and `setup_check()` read out of `.ci/config/constants.sh`. EXPORTED BY NAME rather than by dumping the whole environment: constants.sh defines around sixty readonly names and a dump would make this seam a place any of them could be reached from, which is how a seam stops being one.
CONSTANT_NAMES = (
    "NODE_VERSION_MIN",
    "NODE_VERSION_REQUIRED",
    "DEVBOX_IMAGE",
    "DEVBOX_PORT_BLOCK",
    "DEVBOX_PORT_RANGE_START",
    "DEVBOX_PORT_RANGE_END",
)


class BridgeError(RuntimeError):
    """The shell preamble itself failed, so no verdict about the call is possible.

    Distinct from "the bridged function returned non-zero", which is an ordinary
    result and is returned as an exit code. This is the harness fault: bash is
    missing, `run-legacy.sh` moved, `constants.sh` refused to load. A caller that
    treated the two the same would report a broken checkout as a missing tool.
    """


def _program(body: str, root: pathlib.Path) -> list[str]:
    """`bash -c` argv for one bridged call, with ROOT_DIR bound first."""
    script = "\n".join(("ROOT_DIR=%s" % _quote(str(root)), *PRELUDE, body))
    return ["bash", "-c", script]


def _quote(value: str) -> str:
    """`printf %q`, for the one interpolation this module makes."""
    return "'" + value.replace("'", "'\\''") + "'"


def call(body: str, root: pathlib.Path, env: dict[str, str] | None = None) -> int:
    """Run `body` after the prelude, streams INHERITED. Returns its exit code.

    `check=False` and no capture: this is the path `ensure_deps` and `devbox_up`
    take, and both are long-running and chatty on purpose.
    """
    proc = subprocess.run(_program(body, root), cwd=str(root), env=env, check=False)
    return proc.returncode


def capture(body: str, root: pathlib.Path, env: dict[str, str] | None = None) -> tuple[int, str]:
    """Run `body`, return `(rc, stdout)`. STDERR IS INHERITED, not captured.

    A bridged function's stdout is its VALUE (`devbox_url` prints a URL,
    `devbox_base_port` prints a number) and its stderr is its LOG, because every
    `log_*` in `.ci/scripts/lib/common.sh:35-54` writes to stderr. Capturing both
    would merge a value with the progress text around it, which is the exact
    defect `rediacc_ci.log`'s header records. So stderr goes straight through to
    the operator and only stdout comes back.
    """
    proc = subprocess.run(
        _program(body, root),
        cwd=str(root),
        env=env,
        stdout=subprocess.PIPE,
        text=True,
        check=False,
    )
    return proc.returncode, proc.stdout or ""


def constants(root: pathlib.Path, env: dict[str, str] | None = None) -> dict[str, str]:
    """`CONSTANT_NAMES` as `constants.sh` defines them. Raises BridgeError.

    A REFUSAL AND NOT A DEFAULT, and that is the whole reason this function
    exists rather than a table of literals in Python. `.ci/lib/setup.sh:44-51`
    records what a default costs here: `${NODE_VERSION_MIN:-22.0.0}` "applied
    exactly when .ci/config/constants.sh had not been sourced", and 22.0.0 is
    LOOSER than the repo's real floor, so the unsourced path "silently accepted a
    Node this repo does not support and reported 'already present' for it".
    """
    body = "\n".join('printf "%%s=%%s\\n" %s "${%s:-}"' % (name, name) for name in CONSTANT_NAMES)
    rc, out = capture(body, root, env)
    if rc != 0:
        raise BridgeError(
            "the shell prelude failed (exit %d) while reading %s; "
            "this is a broken checkout, not a missing tool" % (rc, ", ".join(CONSTANT_NAMES))
        )
    values: dict[str, str] = {}
    for line in out.split("\n"):
        if "=" in line:
            key, _, value = line.partition("=")
            values[key] = value
    missing = [name for name in CONSTANT_NAMES if not values.get(name)]
    if missing:
        raise BridgeError(
            "%s defined no value for %s. An empty floor is not a loose floor, it is "
            "an unanswered question."
            % (root / ".ci" / "config" / "constants.sh", ", ".join(missing))
        )
    return values
