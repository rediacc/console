"""The one resolver for the `aws` CLI every R2 call in `.ci/rediacc_ci` runs through.

    PYTHONPATH=.ci python3 -m rediacc_ci.core.awscli which     # the binary a call would exec, rc 1 when none
    PYTHONPATH=.ci python3 -m rediacc_ci.core.awscli pin       # AWSCLI_VERSION, and the cache path it installs to

WHY ONE RESOLVER. Twenty-three modules exec `aws` (promote_r2_to_stable, write_release_sentinel, cleanup_versions, cf_auth, the release asserts, ops/scrub_sentinel and more), and each spelled its presence check its own way: `common.require_cmd("aws")`, `shutil.which("aws")`, or a local `_require_cmd`. All of them then exec a bare `"aws"` argv[0], so the version that wrote production R2 was whatever the CI runner image or the developer's host carried. Measured 2026-10-19 (agent/plans/PLAN-pin-awscli-toolchain-python-compatible.md): a dev host had no `aws` at all, so scrub_sentinel refused with "Required command 'aws' is not available", and the unpinned v1 tried through uvx on the host's Python 3.14 died with `badly formed help string` (exit 255).

THE RUNGS, IN ORDER, mirrored by `resolve_aws` in `.ci/bootstrap.sh`:

  1. `AWS_BIN`, when set and non-empty. Set but not an executable file is a REFUSAL, never a fall-through: an operator who pointed the variable somewhere asked for that binary, and quietly running a different one is how a pin stops meaning anything. CI exports it at the pinned install (B7 of the plan).
  2. `aws` on PATH, TAKEN AS FOUND, with no version probe. About 36 test files put a fake `aws` on PATH that records every call it receives, and a probe here would add an `aws --version` to each of those ledgers. `bash .ci/bootstrap.sh doctor` shows a PATH aws beside the pin, so drift is visible rather than enforced.
  3. `.ci/cache/toolchain/aws-cli/<AWSCLI_VERSION>/bin/aws`, the install `bash .ci/bootstrap.sh install aws` makes, accepted only when it reports the pinned version: a cache left at an older pin is not the pin.

THE LOGICAL argv[0] STAYS `"aws"`. Call sites build their argv with `AWS` at the head, so dry-run output, logs and the simulate_promotion differential stay byte-identical, and only the exec (`argv()`, `run()`) swaps in the resolved binary. When nothing resolves, `argv()` hands the argv back unchanged, so the exec fails exactly as it did before this module (FileNotFoundError, or exit 127 from a shell), and a caller that wants the refusal up front asks `require()`.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from typing import TYPE_CHECKING, Any

from rediacc_ci import paths
from rediacc_ci.core import toolchain
from rediacc_ci.core.common import RefusalError

if TYPE_CHECKING:
    import pathlib
    from collections.abc import Mapping

# The logical argv[0] every call site writes, and the name the PATH rung looks up.
AWS = "aws"

# The explicit-binary rung's variable.
ENV_KEY = "AWS_BIN"

# The pin key in .devcontainer/toolchain.env.
PIN_KEY = "AWSCLI_VERSION"

# Where `bash .ci/bootstrap.sh install aws` installs a version, relative to the repo root; the version directory and `bin/aws` follow.
CACHE_PARTS = (".ci", "cache", "toolchain", "aws-cli")

# The command that installs the pin, named in every refusal's `hint` and by the `which` verb.
INSTALL_HINT = "bash .ci/bootstrap.sh install aws"

# `aws --version` prints `aws-cli/2.38.1 Python/3.13.7 Linux/6.8.0 exe/x86_64.ubuntu.24`; v1 prints the same head.
VERSION_RE = re.compile(r"^aws-cli/([0-9]+(?:\.[0-9]+)*)")

# One probe per cached binary per process, keyed by path, mtime, inode and size (a reinstall replaces the file, so the inode changes even inside one mtime tick): a promote runs thousands of copies, and `aws --version` costs a third of a second on v2.
_PROBED: dict[tuple[str, int, int, int], str | None] = {}


# The refusal every caller prints. Byte-identical to `common.require_cmd("aws")`, because the frozen goldens of twelve ported twins (tests/goldens/twins/*.jsonl) pin that exact stderr line; the detail rides in `hint`.
MISSING = "Required command '%s' is not available" % AWS


class AwsCliMissingError(RefusalError):
    """No `aws` resolved, or `AWS_BIN` names something that is not an executable file.

    A `common.RefusalError`, so every caller that already catches the refusal `common.require_cmd("aws")` raised keeps catching this one. `str()` is `MISSING` in both cases; `hint` says which case it is and names the install command, and `python3 -m rediacc_ci.core.awscli which` prints it.
    """

    def __init__(self, hint: str) -> None:
        super().__init__(MISSING)
        self.hint = hint


def _environ(env: Mapping[str, str] | None) -> Mapping[str, str]:
    return os.environ if env is None else env


def pin(pins: dict[str, str] | None = None) -> str:
    """`AWSCLI_VERSION` from the pins file. Raises `toolchain.PinError`."""
    return toolchain.pin(PIN_KEY, pins)


def cache_binary(version: str | None = None, root: pathlib.Path | None = None) -> pathlib.Path:
    """`.ci/cache/toolchain/aws-cli/<version>/bin/aws`, the version defaulting to the pin."""
    return paths.from_root(*CACHE_PARTS, version or pin(), "bin", AWS, root=root)


def probe_version(binary: str, *, timeout: int = 60) -> str | None:
    """The version `binary --version` reports (`2.38.1`), or None when it would not say."""
    try:
        proc = subprocess.run(
            [binary, "--version"], capture_output=True, text=True, check=False, timeout=timeout
        )
    except (OSError, subprocess.SubprocessError):
        return None
    for line in (proc.stdout + "\n" + proc.stderr).splitlines():
        matched = VERSION_RE.match(line.strip())
        if matched:
            return matched.group(1)
    return None


def _cached_version(binary: pathlib.Path) -> str | None:
    try:
        st = binary.stat()
        # A reinstall replaces the file (new inode) even inside one mtime tick, so the inode and size join the key (review 73e2c821.2).
        key = (str(binary), st.st_mtime_ns, st.st_ino, st.st_size)
    except OSError:
        return None
    if key not in _PROBED:
        _PROBED[key] = probe_version(str(binary))
    return _PROBED[key]


def _executable(path: str) -> bool:
    return os.path.isfile(path) and os.access(path, os.X_OK)


def resolve(env: Mapping[str, str] | None = None, root: pathlib.Path | None = None) -> str | None:
    """The `aws` binary a call would exec, or None. Raises `AwsCliMissingError` for an unusable `AWS_BIN`.

    The rungs are the module docstring's: `AWS_BIN`, then PATH as found, then the repo cache at the pin.
    """
    environ = _environ(env)
    explicit = environ.get(ENV_KEY, "")
    if explicit:
        if not _executable(explicit):
            raise AwsCliMissingError(
                "%s=%s is not an executable file; unset it, or point it at an aws CLI (`%s` installs the pin)"
                % (ENV_KEY, explicit, INSTALL_HINT)
            )
        return explicit
    on_path = shutil.which(AWS, path=environ.get("PATH"))
    if on_path:
        return on_path
    try:
        version = pin()
    except toolchain.PinError:
        return None
    cached = cache_binary(version, root)
    if _executable(str(cached)) and _cached_version(cached) == version:
        return str(cached)
    return None


def require(env: Mapping[str, str] | None = None, root: pathlib.Path | None = None) -> str:
    """`resolve()`, or `AwsCliMissingError` naming the install command."""
    found = resolve(env, root)
    if found is None:
        raise AwsCliMissingError(
            "no aws CLI on AWS_BIN, on PATH or in the repo cache at %s; run `%s` to install the pin"
            % (PIN_KEY, INSTALL_HINT)
        )
    return found


def argv(args: list[str], env: Mapping[str, str] | None = None) -> list[str]:
    """`args` with a leading `AWS` replaced by the resolved binary.

    Anything else passes through untouched, so a generic runner can route every argv here. When nothing resolves the argv comes back unchanged, and the exec fails the way it always did.
    """
    if not args or args[0] != AWS:
        return list(args)
    found = resolve(env)
    if found is None:
        return list(args)
    return [found, *args[1:]]


def run(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[Any]:
    """`subprocess.run(argv(args), **kwargs)`, with `check=False` unless the caller says otherwise."""
    check = bool(kwargs.pop("check", False))
    return subprocess.run(argv(args, env=kwargs.get("env")), check=check, **kwargs)


def main(arguments: list[str]) -> int:
    verb = arguments[0] if arguments else ""
    if verb == "which":
        try:
            found = resolve()
        except AwsCliMissingError as exc:
            print("%s: %s" % (exc, exc.hint), file=sys.stderr)
            return 1
        if found is None:
            print("%s: run `%s` to install the pin" % (MISSING, INSTALL_HINT), file=sys.stderr)
            return 1
        print(found)
        return 0
    if verb == "pin":
        try:
            version = pin()
        except toolchain.PinError as exc:
            print(exc, file=sys.stderr)
            return 1
        print("%s %s" % (version, cache_binary(version)))
        return 0
    print("usage: PYTHONPATH=.ci python3 -m rediacc_ci.core.awscli which|pin", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
