"""Run pytest from any checkout, a lease included.

    python3 .ci/rediacc_ci/dev/lease_pytest.py pytest [<pytest args>...]

WHY. The system `python3` has no pytest, so `python3 -m pytest` reports `No module named pytest` in every tree. The installed wrapper lives at `.ci/cache/toolchain/uv-tools/bin/pytest`, which a lease reaches through the symlink the seed plants. A writer that did not know the path fell back on a side copy under /tmp. The `pytest` verb finds the wrapper in this tree, then in the main checkout beside the shared git directory, and runs it, so no copy is needed and the wrapper's core lease still applies.


"""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys

PYTEST_REL = pathlib.PurePath(".ci", "cache", "toolchain", "uv-tools", "bin", "pytest")
USAGE = "Usage: lease_pytest.py pytest [<pytest args>...]\n"


def _git(top, *args):
    done = subprocess.run(["git", *args], cwd=str(top), capture_output=True, text=True, check=False)
    return done.stdout.strip() if done.returncode == 0 else ""


def toplevel(start):
    """The checkout holding `start`, or None outside any."""
    out = _git(start, "rev-parse", "--show-toplevel")
    return pathlib.Path(out) if out else None


def main_checkout(top):
    """The main checkout of the repository `top` belongs to: the parent of the shared git directory. None when the layout is not `<main>/.git`."""
    common = _git(top, "rev-parse", "--path-format=absolute", "--git-common-dir")
    if not common:
        return None
    path = pathlib.Path(common)
    return path.parent if path.name == ".git" else None


def find_pytest(top):
    """The pytest wrapper this tree can run, or None: this tree's first, the main checkout's next."""
    roots = [top]
    main = main_checkout(top)
    if main is not None and main != top:
        roots.append(main)
    for root in roots:
        candidate = root / PYTEST_REL
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate
    return None


def run(argv, top):
    if not argv or argv[0] != "pytest":
        sys.stderr.write(USAGE)
        return 2
    verb, rest = argv[0], argv[1:]
    if verb == "pytest":
        wrapper = find_pytest(top)
        if wrapper is None:
            sys.stderr.write(
                "lease_pytest: no %s in %s or its main checkout; run `bash .ci/bootstrap.sh` there\n"
                % (PYTEST_REL, top)
            )
            return 1
        return subprocess.run([str(wrapper), *rest], cwd=str(top), check=False).returncode
    if not rest:
        sys.stderr.write(USAGE)
        return 2
    return None


def main():
    top = toplevel(pathlib.Path.cwd())
    if top is None:
        sys.stderr.write("lease_pytest: run it inside a checkout\n")
        return 1
    return run(sys.argv[1:], top)


if __name__ == "__main__":
    sys.exit(main())
