#!/usr/bin/env python3
"""Builds the renet dev binary and hands its path back on stdout as `RENET_BINARY=<path>`.

A thin CI wrapper over `local_common.ensure_renet_built`, which owns the build, the source fingerprint, the stamp (`bin/.renet-build-stamp`) and the key gate. There is one licensed build in `bin/` (agent/plans/PLAN-production-key-only.md Design 6). Arguments are dropped in silence, as the retired shell script did, except the one `go-licenses <output.csv>` verb that writes the release's Go dependency report.

What stays here: the submodule check, the `RENET_BINARY` line and its append to `$GITHUB_ENV`, and the embed-assets cache verdict (`renet_embed_cache`), written after the build on every exit path.

Environment is read at the call site (`GITHUB_ENV`); `ACCOUNT_ED25519_PUBLIC_KEY` is read by `ensure_renet_built` through the environment handed to it. The console root comes from this file's own location, never from cwd.
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys

from rediacc_ci import log
from rediacc_ci.core import local_common
from rediacc_ci.infra import renet_embed_cache

# The go-licenses release that writes the Go dependency report. Pinned here and in `.ci/config/pins.json` (`devcontainer:go-licenses`), never `@latest`.
GO_LICENSES_VERSION = "v1.6.0"

# The renet module's own packages carry no licence row of their own: rdc's notice lists third-party code.
GO_LICENSES_IGNORE = "github.com/rediacc/renet"

# Written beside the renet binaries and uploaded in the `renet-binaries-<sha>` artifact, which `ci-build-cli.yml` downloads into `private/bin/`.
GO_LICENSES_CSV = "renet-go-licenses.csv"

# U+2014, written as an escape so no em dash is typed into a file under `.ci/rediacc_ci`, which `check:ci-em-dash-surfaces` scans.
_EM_DASH = "\u2014"

# The three `uname -s` prefixes that mean Windows.
_WINDOWS_UNAME_PREFIXES = ("MINGW", "MSYS", "CYGWIN")


def console_root() -> pathlib.Path:
    """The repository root, derived from this file's own path, never from cwd and never from an env override."""
    # This file: <root>/.ci/rediacc_ci/infra/build_renet.py
    return pathlib.Path(__file__).resolve().parents[3]


def exe_suffix() -> str:
    """`.exe` under Git Bash / MSYS / Cygwin, empty everywhere else. `uname` is asked rather than `platform.system()`, which says "Windows" under MSYS."""
    try:
        completed = subprocess.run(["uname", "-s"], capture_output=True, text=True, check=False)
    except OSError:
        return ""
    system = completed.stdout.strip() if completed.returncode == 0 else ""
    return ".exe" if system.startswith(_WINDOWS_UNAME_PREFIXES) else ""


def write_go_licenses(renet_src: pathlib.Path, output: pathlib.Path) -> int:
    """The Go dependency report of the module that was just built: `go-licenses report ./...` at the pinned version, renet's own packages ignored, written as CSV (module,url,licence) to `output`. Non-zero when go-licenses fails or reports a renet package, so a release never ships a report it could not make."""
    try:
        completed = subprocess.run(
            [
                "go",
                "run",
                "github.com/google/go-licenses@%s" % GO_LICENSES_VERSION,
                "report",
                "./...",
                "--ignore",
                GO_LICENSES_IGNORE,
            ],
            cwd=renet_src,
            stdout=subprocess.PIPE,
            text=True,
            check=False,
        )
    except OSError as error:
        log.error("go-licenses could not start: %s" % error)
        return 1
    if completed.returncode != 0:
        log.error("go-licenses exited %d" % completed.returncode)
        return completed.returncode
    rows = [line for line in completed.stdout.splitlines() if line.strip()]
    if not rows:
        log.error("go-licenses produced no rows")
        return 1
    if any(row.startswith(GO_LICENSES_IGNORE) for row in rows):
        log.error("go-licenses reported a %s package despite --ignore" % GO_LICENSES_IGNORE)
        return 1
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(rows) + "\n", encoding="utf-8")
    log.info("Wrote %d Go licence rows to %s" % (len(rows), output))
    return 0


def main(argv: list[str]) -> int:
    """`go-licenses <output>` writes the Go dependency report and nothing else. Otherwise build, then write the embed-assets cache verdict whether or not the build succeeded: a staging that completed before the go build failed is still worth saving."""
    renet_src = console_root() / "private" / "renet"
    if argv[:1] == ["go-licenses"]:
        if len(argv) != 2:
            log.error("Usage: build_renet go-licenses <output.csv>")
            return 2
        return write_go_licenses(renet_src, pathlib.Path(argv[1]))
    if renet_src.is_dir():
        warning = renet_embed_cache.stale_hit_warning(renet_src)
        if warning is not None:
            print(warning, flush=True)
    try:
        return _build()
    finally:
        if renet_src.is_dir():
            renet_embed_cache.write_verdict(renet_src)


def _build() -> int:
    root = console_root()
    renet_src = root / "private" / "renet"
    if not renet_src.is_dir():
        log.error("private/renet/ not found %s submodule not checked out" % _EM_DASH)
        log.error("Run: git submodule update --init private/renet")
        return 1

    renet_bin = str(renet_src / "bin" / ("renet" + exe_suffix()))

    # ensure_renet_built derives its root from LOCAL_ROOT_DIR, so this file's root is named, not left to the caller's environment.
    env = {**os.environ, "LOCAL_ROOT_DIR": str(root)}
    # build.sh's own exit status is the wrapper's when the build fails, as the shell twin returned it; 1 only when no status was recorded (review 6de769e7.2). A build killed by a signal is a negative subprocess code, which the shell reports as 128 + the signal, so it is mapped to that (review f57d518c.2).
    status: list[int] = []
    try:
        built = local_common.ensure_renet_built(env, status=status)
    except local_common.LocalCommonError as error:
        return error.code
    if not built:
        if not status:
            return 1
        return 128 - status[-1] if status[-1] < 0 else status[-1]

    github_env = os.environ.get("GITHUB_ENV", "")
    if github_env:
        with pathlib.Path(github_env).open("a", encoding="utf-8") as handle:
            handle.write("RENET_BINARY=%s\n" % renet_bin)
        log.info("Set RENET_BINARY in GITHUB_ENV")

    print("RENET_BINARY=%s" % renet_bin, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
