"""The seam between `setup` and the functions it does not own, in process.

WHY A BRIDGE AND NOT MORE PORT. `setup()` calls fifteen things. Nine of them are `.ci/lib/setup.sh` and are ported in `host.py`. The other six are the installers and checks of `core.local_common` (the port of `local-common.sh`, deleted under PLAN-retire-bash-oracles B3) and the `devbox_*` functions, which are `core.devbox`:

    check_node_version, ensure_host_tools, ensure_bashcov_sup, ensure_deps,
    deps_are_current, ensure_docker_installed     rediacc_ci.core.local_common, run in process by `_local_common_call`
    devbox_*                                      rediacc_ci.core.devbox, run in process by `_devbox_call`

The call sites keep their `bridge.call("<name>"` spelling: `setup_idempotency` and `port_parity` match those tokens, and a call that names the function it runs is easier to read than a verb table. Only the transport changed: a body that is ONE call of one of those names runs in this process, and anything else goes to a shell that sources `constants.sh` alone (the only caller left for it is `constants()`).

STREAMS ARE NOT CAPTURED BY DEFAULT. `ensure_deps` compiles native modules and `devbox_up` prints a probed route table; both take minutes and both are the thing an operator watches. A bridge that captured them would turn a live install into a silent hang, so `call()` inherits the streams and only `capture()` does not. The two are different functions rather than a flag, because a
flag is a thing a caller gets wrong once and never notices.
"""

from __future__ import annotations

import contextlib
import io
import os
import shlex
import subprocess
from typing import TYPE_CHECKING

from rediacc_ci.core import devbox, local_common, toolchain

if TYPE_CHECKING:  # pragma: no cover - `pathlib` is only ever an annotation here
    import pathlib

# What a bridged shell program runs after: `constants.sh` alone, which loads the toolchain pins itself. The local-common functions are Python now (`_local_common_call`), and so are the `devbox_*` ones (`_devbox_call`), so the shell only ever reads constants. Kept as data so the preamble is one string in one place.
PRELUDE = (
    "set -euo pipefail",
    'source "$ROOT_DIR/.ci/config/constants.sh"',
)

# The bash function names that run in process, each with the `local_common` function behind it. A name that takes the environment is called with it; the others read `os.environ`, so the call runs under `_environ`.
LOCAL_COMMON_NAMES = {
    "check_node_version": "check_node_version",
    "deps_are_current": "deps_are_current",
    "ensure_bashcov_sup": "ensure_bashcov_sup",
    "ensure_deps": "ensure_deps",
    "ensure_docker_installed": "ensure_docker_installed",
    "ensure_host_tools": "ensure_host_tools",
}

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

    Distinct from "the bridged function returned non-zero", which is an ordinary result and is returned as an exit code. This is the harness fault: bash is missing, a sourced library moved, `constants.sh` refused to load. A caller that treated the two the same would report a broken checkout as a missing tool.
    """


def _program(body: str, root: pathlib.Path) -> list[str]:
    """`bash -c` argv for one bridged call, with ROOT_DIR bound first."""
    script = "\n".join(("ROOT_DIR=%s" % _quote(str(root)), *PRELUDE, body))
    return ["bash", "-c", script]


def _quote(value: str) -> str:
    """`printf %q`, for the one interpolation this module makes."""
    return "'" + value.replace("'", "'\\''") + "'"


def _devbox_words(body: str) -> list[str] | None:
    """`body` as an argv when it is ONE call of a `devbox.sh` function, else None.

    The library is Python now (`core.devbox`), so a body naming one of its fifty-five functions runs there and never reaches bash. Anything else, including a multi-line program, goes to the shell.
    """
    if "\n" in body:
        return None
    try:
        words = shlex.split(body)
    except ValueError:
        return None
    return words if words and words[0] in devbox.BASH_NAMES else None


def _devbox_call(
    words: list[str],
    root: pathlib.Path,
    env: dict[str, str] | None,
    *,
    stdout=None,
    stderr=None,
) -> int:
    """`( set -e; devbox_<name> args )` in process, over `env` (or this process's environment) with `root` as the checkout."""
    box = devbox.Devbox(
        env=dict(os.environ if env is None else env),
        cwd=str(root),
        repo_root=str(root),
        stdout=stdout,
        stderr=stderr,
    )
    return box.invoke(words[0], words[1:])


def _local_common_words(body: str) -> list[str] | None:
    """`body` as an argv when it is ONE call of a `local-common.sh` function, else None."""
    if "\n" in body:
        return None
    try:
        words = shlex.split(body)
    except ValueError:
        return None
    return words if words and words[0] in LOCAL_COMMON_NAMES else None


@contextlib.contextmanager
def _environ(env: dict[str, str]):
    """`os.environ` is `env` for the duration, then what it was. The local-common functions that probe the PATH (`shutil.which`) read the process environment."""
    saved = dict(os.environ)
    os.environ.clear()
    os.environ.update(env)
    try:
        yield
    finally:
        os.environ.clear()
        os.environ.update(saved)


def _local_common_call(words: list[str], root: pathlib.Path, env: dict[str, str] | None) -> int:
    """`( set -e; <name> args )` in process, with `root` as the checkout and `env` (or this process's environment) as the environment.

    The prelude exported `LOCAL_ROOT_DIR` from the library's own location, which was `root`; the port reads the same variable. `$NODE_VERSION_MIN` is the one argument a caller passes, and it is the toolchain's node floor.
    """
    environment = dict(os.environ if env is None else env, LOCAL_ROOT_DIR=str(root))
    name, args = words[0], words[1:]
    args = [toolchain.node_floor() if arg == "$NODE_VERSION_MIN" else arg for arg in args]
    function = getattr(local_common, LOCAL_COMMON_NAMES[name])
    try:
        with _environ(environment):
            if name == "check_node_version":
                ok = function(*args)
            elif name == "ensure_host_tools":
                ok = function()
            else:
                ok = function(environment)
    except local_common.LocalCommonError as exc:
        return exc.code
    return 0 if ok else 1


def call(body: str, root: pathlib.Path, env: dict[str, str] | None = None) -> int:
    """Run `body` after the prelude, streams INHERITED. Returns its exit code.

    `check=False` and no capture: this is the path `ensure_deps` and `devbox_up`
    take, and both are long-running and chatty on purpose.
    """
    words = _devbox_words(body)
    if words is not None:
        return _devbox_call(words, root, env)
    words = _local_common_words(body)
    if words is not None:
        return _local_common_call(words, root, env)
    proc = subprocess.run(_program(body, root), cwd=str(root), env=env, check=False)
    return proc.returncode


def capture(
    body: str,
    root: pathlib.Path,
    env: dict[str, str] | None = None,
    *,
    quiet_err: bool = False,
) -> tuple[int, str]:
    """Run `body`, return `(rc, stdout)`. STDERR IS INHERITED, not captured, unless `quiet_err` (`2>/dev/null`).

    A bridged function's stdout is its VALUE (`devbox_url` prints a URL, `devbox_base_port` prints a number) and its stderr is its LOG, because every `log_*` in `.ci/scripts/lib/common.sh:35-54` writes to stderr. Capturing both would merge a value with the progress text around it, which is the exact defect `rediacc_ci.log`'s header records. So stderr goes straight through to the
    operator and only stdout comes back.
    """
    words = _devbox_words(body)
    if words is not None:
        sink = io.BytesIO()
        rc = _devbox_call(words, root, env, stdout=sink, stderr=io.BytesIO() if quiet_err else None)
        return rc, sink.getvalue().decode("utf-8", "replace")
    if _local_common_words(body) is not None:
        raise BridgeError(
            "%r is a local-common function and runs in process through call(); none of them "
            "has a stdout value to capture" % body
        )
    proc = subprocess.run(
        _program(body, root),
        cwd=str(root),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL if quiet_err else None,
        text=True,
        check=False,
    )
    return proc.returncode, proc.stdout or ""


def constants(root: pathlib.Path, env: dict[str, str] | None = None) -> dict[str, str]:
    """`CONSTANT_NAMES` as `constants.sh` defines them. Raises BridgeError.

    A REFUSAL AND NOT A DEFAULT, and that is the whole reason this function exists rather than a table of literals in Python. `.ci/lib/setup.sh:44-51`
    records what a default costs here: `${NODE_VERSION_MIN:-22.0.0}` "applied
    exactly when .ci/config/constants.sh had not been sourced", and 22.0.0 is LOOSER than the repo's real floor, so the unsourced path "silently accepted a Node this repo does not support and reported 'already present' for it".
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
