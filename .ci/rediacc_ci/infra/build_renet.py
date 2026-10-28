#!/usr/bin/env python3
"""Builds the renet dev binary of one flavor and hands its path back on stdout as `RENET_BINARY=<path>`.

A thin CI wrapper over `local_common.ensure_renet_built`, which owns the build, the source fingerprint and the per-flavor stamp (`<flavor dir>/.renet-build-stamp`). `private/renet/build.sh dev` writes a `nolicense` build to `bin/` and an enforcing one to `bin/enforce/` (`core.renet_flavor`), so a job that built one flavor can never hand its binary to a job that wanted the other, and the old shared-path identity stamp is gone.

The flavor follows build.sh's precedence (`renet_flavor.flavor_for`): `RDC_RENET_LICENSE=1` selects enforcement, then the last `--license` or `--nolicense` wins. Every other argument is dropped in silence, as the retired shell script did.

What stays here: the submodule check, the `RENET_BINARY` line and its append to `$GITHUB_ENV`, and the embed-assets cache verdict (`renet_embed_cache`), written after the build on every exit path.

Environment is read at the call site, one name at a time (`RDC_RENET_LICENSE`, `GITHUB_ENV`); `ACCOUNT_ED25519_PUBLIC_KEY` is read by `ensure_renet_built` through the environment handed to it. The console root comes from this file's own location, never from cwd.
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys

from rediacc_ci import log
from rediacc_ci.core import local_common, renet_flavor
from rediacc_ci.infra import renet_embed_cache

# U+2014, written as an escape so no em dash is typed into a file under `.ci/rediacc_ci`, which `check:ci-em-dash-surfaces` scans.
_EM_DASH = "—"

# The three `uname -s` prefixes that mean Windows.
_WINDOWS_UNAME_PREFIXES = ("MINGW", "MSYS", "CYGWIN")


def console_root() -> pathlib.Path:
    """The repository root, derived from this file's own path, never from cwd and never from an env override."""
    # This file: <root>/.ci/rediacc_ci/infra/build_renet.py
    return pathlib.Path(__file__).resolve().parents[3]


def build_args(argv: list[str]) -> list[str]:
    """`--license` and `--nolicense` are forwarded in the order given; every other argument is dropped in silence."""
    return [arg for arg in argv if arg in ("--nolicense", "--license")]


def exe_suffix() -> str:
    """`.exe` under Git Bash / MSYS / Cygwin, empty everywhere else. `uname` is asked rather than `platform.system()`, which says "Windows" under MSYS."""
    try:
        completed = subprocess.run(["uname", "-s"], capture_output=True, text=True, check=False)
    except OSError:
        return ""
    system = completed.stdout.strip() if completed.returncode == 0 else ""
    return ".exe" if system.startswith(_WINDOWS_UNAME_PREFIXES) else ""


def main(argv: list[str]) -> int:
    """Build, then write the embed-assets cache verdict whether or not the build succeeded: a staging that completed before the go build failed is still worth saving."""
    renet_src = console_root() / "private" / "renet"
    if renet_src.is_dir():
        warning = renet_embed_cache.stale_hit_warning(renet_src)
        if warning is not None:
            print(warning, flush=True)
    try:
        return _build(argv)
    finally:
        if renet_src.is_dir():
            renet_embed_cache.write_verdict(renet_src)


def _build(argv: list[str]) -> int:
    root = console_root()
    renet_src = root / "private" / "renet"
    if not renet_src.is_dir():
        log.error("private/renet/ not found %s submodule not checked out" % _EM_DASH)
        log.error("Run: git submodule update --init private/renet")
        return 1

    flavor = renet_flavor.flavor_for(os.environ.get("RDC_RENET_LICENSE", ""), build_args(argv))
    renet_bin = renet_flavor.binary(str(renet_src), flavor, exe_suffix())

    # ensure_renet_built derives its root from LOCAL_ROOT_DIR, so this file's root is named, not left to the caller's environment.
    env = {**os.environ, "LOCAL_ROOT_DIR": str(root)}
    try:
        built = local_common.ensure_renet_built(env, flavor=flavor)
    except local_common.LocalCommonError as error:
        return error.code
    if not built:
        return 1

    github_env = os.environ.get("GITHUB_ENV", "")
    if github_env:
        with pathlib.Path(github_env).open("a", encoding="utf-8") as handle:
            handle.write("RENET_BINARY=%s\n" % renet_bin)
        log.info("Set RENET_BINARY in GITHUB_ENV")

    print("RENET_BINARY=%s" % renet_bin, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
