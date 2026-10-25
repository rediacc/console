"""Refuse a local Worker deploy whose wrangler is not the pinned version.

CI installs `wrangler@${WRANGLER_VERSION}` globally (cd-deploy-account.yml). A local deploy resolves wrangler from `workers/account/node_modules`, and that tree drifted to 4.131.2 while `.ci/config/constants.sh` pinned a newer one, so a local deploy ran code the pin never covered. Three places must agree, and this module refuses when they do not:

  1. `WRANGLER_VERSION` in `.ci/config/constants.sh`, the pin (moved by `npm run pins -- bump toolchain:wrangler`).
  2. The `wrangler` spec in `workers/account/package.json`, which must be that exact version (no range).
  3. The wrangler actually installed under `workers/account/node_modules`.

Exit codes: 0 all three agree, 1 a mismatch (each named, with the fix), 2 no verdict (a file cannot be read).

Run: `PYTHONPATH=.ci python3 -m rediacc_ci.deploy.wrangler_pin`.
"""

from __future__ import annotations

import json
import re
import sys
from typing import TYPE_CHECKING

from rediacc_ci import paths

if TYPE_CHECKING:
    import pathlib

SELF = "rediacc_ci.deploy.wrangler_pin"
CONSTANTS_REL = (".ci", "config", "constants.sh")
PACKAGE_REL = ("workers", "account", "package.json")
INSTALLED_REL = ("workers", "account", "node_modules", "wrangler", "package.json")
PIN_LINE = re.compile(r'^readonly WRANGLER_VERSION="([^"]+)"', re.MULTILINE)
FIX = "npm ci --prefix workers/account (after `npm run pins -- lockfiles workers/account`)"


class NoVerdictError(Exception):
    """A file the check reads is absent or malformed."""


def pinned(root: pathlib.Path) -> str:
    """The version `constants.sh` pins."""
    path = root.joinpath(*CONSTANTS_REL)
    try:
        found = PIN_LINE.search(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise NoVerdictError("cannot read %s (%s)" % (path, exc.strerror)) from None
    if found is None:
        raise NoVerdictError("%s has no WRANGLER_VERSION line" % path)
    return found.group(1)


def declared(root: pathlib.Path) -> str:
    """The `wrangler` spec in `workers/account/package.json`."""
    path = root.joinpath(*PACKAGE_REL)
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise NoVerdictError("cannot read %s (%s)" % (path, type(exc).__name__)) from None
    spec = (doc.get("devDependencies") or {}).get("wrangler") or (
        doc.get("dependencies") or {}
    ).get("wrangler")
    if not isinstance(spec, str) or not spec:
        raise NoVerdictError("%s declares no wrangler dependency" % path)
    return spec


def installed(root: pathlib.Path) -> str:
    """The version of the wrangler under `workers/account/node_modules`."""
    path = root.joinpath(*INSTALLED_REL)
    try:
        version = json.loads(path.read_text(encoding="utf-8")).get("version")
    except (OSError, ValueError) as exc:
        raise NoVerdictError(
            "cannot read the installed wrangler at %s (%s); run: %s"
            % (path, type(exc).__name__, FIX)
        ) from None
    if not isinstance(version, str) or not version:
        raise NoVerdictError("%s carries no version" % path)
    return version


def check(root: pathlib.Path) -> tuple[int, list[str]]:
    """(exit code, lines) for the three-way comparison."""
    try:
        want = pinned(root)
        spec = declared(root)
        have = installed(root)
    except NoVerdictError as exc:
        return 2, ["%s: %s; no verdict" % (SELF, exc)]
    problems: list[str] = []
    if spec != want:
        problems.append(
            "workers/account/package.json pins wrangler %r but constants.sh WRANGLER_VERSION is %r"
            % (spec, want)
        )
    if have != want:
        problems.append(
            "the installed wrangler is %s but constants.sh WRANGLER_VERSION is %s" % (have, want)
        )
    if problems:
        return 1, [
            *("%s: %s" % (SELF, p) for p in problems),
            "  fix: %s" % FIX,
        ]
    return 0, ["%s: wrangler %s (constants.sh, package.json and the install agree)" % (SELF, want)]


def main(argv: list[str]) -> int:
    del argv
    code, lines = check(paths.repo_root())
    stream = sys.stdout if code == 0 else sys.stderr
    for line in lines:
        print(line, file=stream)
    return code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
