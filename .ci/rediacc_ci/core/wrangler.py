"""The one place that spells how a Python tool invokes wrangler.

A bare `npx wrangler` run from a directory with no local install makes npx download the latest wrangler from the registry, which bypasses the lockfile and the 24h release-age rule (`.ci/config/release-age.json`). Every executed call therefore starts from `ARGV`, whose `--no-install` makes npx resolve a local `node_modules/.bin/wrangler` (walking up from the cwd) or a wrangler on PATH (the CI global install, pinned by `WRANGLER_VERSION`) and fail when neither exists, never fetch.

`require(cwd)` is the explicit refusal for a caller that knows its worker directory: it raises `WranglerNotInstalledError` naming the directory and the fix before any subprocess starts.
"""

from __future__ import annotations

import shutil
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pathlib
    from collections.abc import Mapping

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


def require(cwd: pathlib.Path, env: Mapping[str, str] | None = None) -> list[str]:
    """`ARGV` once a local or PATH wrangler is proven reachable from `cwd`, else a named error."""
    if local_binary(cwd) is not None:
        return list(ARGV)
    if shutil.which("wrangler", path=None if env is None else env.get("PATH")) is not None:
        return list(ARGV)
    raise WranglerNotInstalledError(
        "wrangler is not installed for %s: no node_modules/.bin/wrangler in it or an ancestor, "
        "and none on PATH; run: %s" % (cwd, FIX)
    )
