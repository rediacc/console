#!/usr/bin/env python3
"""Run this package's tests with the pytest `.ci/bootstrap.sh` provisions.

WHY A RUNNER AT ALL, when `pytest .claude/rediacc_hooks/tests` from the repo root does the same thing. Because on the host these hooks run on, `pytest` is not on PATH and neither is pip, pipx, uv or uvx (measured 2026-09-06 and recorded in `.ci/bootstrap.sh`'s own header). Typing `pytest` there gets "command not found", which reads as "the suite is broken" rather than "the
toolchain is not installed". This asks the bootstrap where pytest is, exactly as the bootstrap defines it, and says what to run when it is absent.

IT DOES NOT REIMPLEMENT THE RESOLUTION ORDER. `.ci/bootstrap.sh install` is idempotent by resolution rather than by a stamp -- it asks the binary its version -- so calling it on every run costs one process and cannot disagree
with itself. Copying its search order here would be a second place the answer
is written down, which is the failure `.ci/rediacc_ci/paths.py` was written to end.

    python3 .claude/rediacc_hooks/run_tests.py            the whole package
    python3 .claude/rediacc_hooks/run_tests.py -k shellscan   pass-through args
    PYTEST_BIN=/usr/bin/pytest python3 ... run_tests.py   an explicit binary

Arguments after the script name go to pytest unchanged. With none, it runs this package's tests directory.

NOT A GATE. A gate's entry point has to live where `scripts/gate-bind.ts` can see it (driver contract 5d), and registering this one is the root driver's call, not this file's -- see the report accompanying phase 1.
"""

import os
import pathlib
import subprocess
import sys


def repo_root():
    """The tree holding both `.claude` and `.ci`, found by looking, not counting."""
    for candidate in pathlib.Path(__file__).resolve().parents:
        if (candidate / ".claude").is_dir() and (candidate / ".ci").is_dir():
            return candidate
    print("run_tests: no repository root above %s" % __file__, file=sys.stderr)
    raise SystemExit(2)


def resolve_pytest(root):
    explicit = os.environ.get("PYTEST_BIN")
    if explicit:
        return explicit
    bootstrap = root / ".ci" / "bootstrap.sh"
    proc = subprocess.run(
        ["bash", str(bootstrap), "install"],
        capture_output=True,
        check=False,
        cwd=str(root),
    )
    out = proc.stdout.decode("utf-8", "surrogateescape")
    err = proc.stderr.decode("utf-8", "surrogateescape")
    if proc.returncode != 0:
        # The bootstrap's own message is the useful one -- it names the pin, the URL and the checksum. Reprinting it beats paraphrasing it.
        sys.stderr.write(out)
        sys.stderr.write(err)
        print("run_tests: %s could not provide pytest" % bootstrap, file=sys.stderr)
        raise SystemExit(2)
    for line in out.splitlines():
        # `ok pytest 9.1.1 already at <path>` / `... installed at <path>`.
        if " pytest " in line and " at " in line:
            return line.rsplit(" at ", 1)[1].strip()
    sys.stderr.write(out)
    print("run_tests: could not read a pytest path out of the bootstrap report", file=sys.stderr)
    raise SystemExit(2)


def main(argv):
    root = repo_root()
    pytest_bin = resolve_pytest(root)
    tests = str((root / ".claude" / "rediacc_hooks" / "tests").relative_to(root))
    args = list(argv)
    # THE TESTS DIRECTORY IS APPENDED UNLESS THE CALLER NAMED A PATH, and the first cut of this only did it when there were NO arguments at all. So `run_tests.py -k proc` fell through to pytest with no path, pytest fell back to `testpaths` in pyproject.toml -- which is `.ci/rediacc_ci/tests`, a DIFFERENT package -- and reported "37 passed" from a suite this runner has nothing to do
    # with. A runner that silently runs someone else's tests is worse than one that fails.
    named = [a for a in args if not a.startswith("-") and ((root / a).exists() or "::" in a)]
    if not named:
        args.append(tests)
    # CWD IS THE REPO ROOT, always. pytest discovers `pyproject.toml` by walking up from its arguments, and that file carries `pythonpath`, `cache_dir`
    # (pointing into the gitignored `.ci/cache`) and `filterwarnings = error`.
    # Run from elsewhere and it finds a different rootdir, silently, with none of those applied.
    print("run_tests: %s %s (cwd %s)" % (pytest_bin, " ".join(args), root))
    return subprocess.run([pytest_bin, *args], check=False, cwd=str(root)).returncode


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
