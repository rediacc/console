"""The one place that spells how a Python tool invokes wrangler.

A bare `npx wrangler` run from a directory with no local install makes npx download the latest wrangler from the registry, which bypasses the lockfile and the 24h release-age rule (`.ci/config/release-age.json`). Every executed call therefore starts from `ARGV`, whose `--no-install` makes npx run a local `node_modules/.bin/wrangler` (walking up from the cwd) or a package in npm's global prefix (the CI global install, pinned by `WRANGLER_VERSION`) and fail when neither exists, never fetch.

NPX NEVER READS PATH. npm 11.21.0's `npx --no-install wrangler`, run from a temporary directory with a pinned `workers/*/node_modules/.bin` first on PATH, answers "npm error npx canceled due to missing packages and no YES option" (measured 2026-11-10). So `ARGV` works only for a caller whose cwd is inside a worker directory with its install. A caller that runs anywhere else (control_db's neutral temporary directory) passes its argv through `resolve(argv, cwd, env)`, which swaps the leading `ARGV` for the absolute path of the pinned binary: the local install reachable from `cwd`, else the first `wrangler` on `env`'s PATH (`control_db.wrangler_env` puts the repo's pinned `.bin` directories there).

`binary(cwd, env)` is that lookup, and the explicit refusal: it raises `WranglerNotInstalledError` naming the directory and the fix before any subprocess starts. `require(cwd, env)` is the same refusal for a caller that runs `ARGV` from `cwd` itself.
"""

from __future__ import annotations

import pathlib
import shutil
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

ARGV: list[str] = ["npx", "--no-install", "wrangler"]
FIX = "npm ci --prefix <worker dir> (after `npm run pins -- lockfiles <worker dir>`)"


class WranglerNotInstalledError(RuntimeError):
    """No pinned wrangler is reachable from the working directory."""


def local_binary(cwd: pathlib.Path) -> pathlib.Path | None:
    """`node_modules/.bin/wrangler` in `cwd` or the nearest ancestor that has one."""
    for base in (cwd, *cwd.parents):
        candidate = base / "node_modules" / ".bin" / "wrangler"
        if candidate.exists():
            return candidate
    return None


def binary(cwd: pathlib.Path, env: Mapping[str, str] | None = None) -> pathlib.Path:
    """The pinned wrangler a call from `cwd` runs: the local install in `cwd` or an ancestor, else the first `wrangler` on `env`'s PATH (this process's when `env` is None), else a named error."""
    found = local_binary(cwd)
    if found is not None:
        return found
    on_path = shutil.which("wrangler", path=None if env is None else env.get("PATH"))
    if on_path is not None:
        return pathlib.Path(on_path)
    raise WranglerNotInstalledError(
        "wrangler is not installed for %s: no node_modules/.bin/wrangler in it or an ancestor, "
        "and none on PATH; run: %s" % (cwd, FIX)
    )


def resolve(
    argv: Sequence[str], cwd: pathlib.Path, env: Mapping[str, str] | None = None
) -> list[str]:
    """`argv` with a leading `ARGV` replaced by the absolute path of `binary(cwd, env)`, so the pinned binary runs from any cwd; any other argv comes back unchanged."""
    out = list(argv)
    if out[: len(ARGV)] != ARGV:
        return out
    return [str(binary(cwd, env)), *out[len(ARGV) :]]


def require(cwd: pathlib.Path, env: Mapping[str, str] | None = None) -> list[str]:
    """`ARGV` once `binary(cwd, env)` finds a wrangler, else its named error. npx itself resolves only the local install or npm's global prefix, so a caller outside a worker directory runs `resolve` instead."""
    binary(cwd, env)
    return list(ARGV)
