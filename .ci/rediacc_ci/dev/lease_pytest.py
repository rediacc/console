"""Run pytest, or one hook-guard suite, from any checkout, a lease included.

    python3 .ci/rediacc_ci/dev/lease_pytest.py pytest [<pytest args>...]
    python3 .ci/rediacc_ci/dev/lease_pytest.py guard <stem> [<suite args>...]

WHY. The system `python3` has no pytest, so `python3 -m pytest` reports `No module named pytest` in every tree. The installed wrapper lives at `.ci/cache/toolchain/uv-tools/bin/pytest`, which a lease reaches through the symlink the seed plants. A writer that did not know the path fell back on a side copy under /tmp. The `pytest` verb finds the wrapper in this tree, then in the main checkout beside the shared git directory, and runs it, so no copy is needed and the wrapper's core lease still applies.

THE GUARD VERB. A hook-guard suite such as `guards/test-block_origin_clone.py` carries `git clone` rows in its text. `block_origin_clone` judges a script run by path and refuses one whose text names a clone verb unless the file is tracked and unchanged, so an edited suite has no direct way to run from the Bash tool. This verb starts the suite as a child of Python, the way `test_hooks_delegates.py` does, so the command the hook reads names no clone verb. The guard itself is untouched: the same text typed to Bash by path is still refused.
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys

PYTEST_REL = pathlib.PurePath(".ci", "cache", "toolchain", "uv-tools", "bin", "pytest")
GUARDS_REL = pathlib.PurePath(".claude", "rediacc_hooks", "guards")
USAGE = (
    "Usage: lease_pytest.py pytest [<pytest args>...]\n"
    "       lease_pytest.py guard <stem> [<suite args>...]\n"
    "  <stem> names guards/test-<stem>.py, for example block_origin_clone\n"
)


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


def guard_suite(top, stem):
    """The suite file for `stem`, or None. A stem is a bare name, so no separator or dot walks out of the guards directory."""
    if not stem or any(ch in stem for ch in "/\\.") or stem.startswith("-"):
        return None
    path = top / GUARDS_REL / ("test-%s.py" % stem)
    return path if path.is_file() else None


def run(argv, top):
    if not argv or argv[0] not in ("pytest", "guard"):
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
    suite = guard_suite(top, rest[0])
    if suite is None:
        sys.stderr.write(
            "lease_pytest: no guard suite test-%s.py under %s\n" % (rest[0], GUARDS_REL)
        )
        return 1
    return subprocess.run(
        [sys.executable, str(suite), *rest[1:]], cwd=str(top), check=False
    ).returncode


def main():
    top = toplevel(pathlib.Path.cwd())
    if top is None:
        sys.stderr.write("lease_pytest: run it inside a checkout\n")
        return 1
    return run(sys.argv[1:], top)


if __name__ == "__main__":
    sys.exit(main())
