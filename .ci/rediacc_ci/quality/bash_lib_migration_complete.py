"""Every function in a `.ci/lib/*.sh` library has a Python twin in `rediacc_ci.core`, or is a recorded, shrink-only gap.

WHY. W7P5-b ported the bash libraries one function at a time, and "account.sh 22 of 22" was a count a writer made by hand on 2026-09-24. Nothing held it: a bash function added the next day, or a Python def renamed away, would leave the twin incomplete while every differential stayed green, because a differential only compares the functions it already drives.

WHAT IT CHECKS, per library in `LIBS` (every `.sh` under `.ci/lib` and `.ci/scripts/lib`; the other bash libraries have no Python twin yet, so there is nothing to hold):
  - each bash function name maps to a `def` in one of the library's Python modules, through `ALIASES` or by the naming rule (the name itself, the name minus the library prefix, and either one without leading underscores);
  - an unmapped function must be listed in the baseline (`.ci/config/bash-lib-port-baseline.json`) or it is a finding: a NEW unported function;
  - a baseline entry whose function now maps, or no longer exists, is a finding too, so the baseline only shrinks;
  - a `.sh` under `LIB_DIRS` missing from `LIBS` is a finding, so a new library cannot bypass the gate.

Exit 0 clean, 1 on findings, 2 when the gate's own controls fail (controls_first convention).
"""

from __future__ import annotations

import json
import pathlib
import re
import sys

from rediacc_ci import paths
from rediacc_ci.controls import controls_first

# Every .sh in these directories must be listed in LIBS.
LIB_DIRS = (".ci/lib", ".ci/scripts/lib")
CORE_DIR = ".ci/rediacc_ci/core"
BASELINE = ".ci/config/bash-lib-port-baseline.json"

# Library (repo path) -> the modules that carry its twin, relative to rediacc_ci/core. Every .sh under LIB_DIRS must appear here.
LIBS: dict[str, tuple[str, ...]] = {
    ".ci/lib/account.sh": ("account.py", "account_lifecycle.py"),
    ".ci/lib/devbox.sh": ("devbox.py",),
    ".ci/lib/local-common.sh": ("local_common.py",),
    ".ci/lib/service.sh": ("service.py",),
    ".ci/scripts/lib/blocker-validator.sh": ("blocker_validator.py",),
    ".ci/scripts/lib/common.sh": ("common.py", "review_budget.py", "ghx.py", "../proc.py"),
    ".ci/scripts/lib/emit-advisory.sh": ("advisory.py",),
    ".ci/scripts/lib/release-state-validator.sh": ("release_state_validator.py",),
    ".ci/scripts/lib/toolchain.sh": ("toolchain.py",),
}

# Extra name prefixes a library puts on its functions, beyond its own file stem; the twin drops them.
PREFIXES: dict[str, tuple[str, ...]] = {
    ".ci/scripts/lib/release-state-validator.sh": ("rsv_",),
    ".ci/scripts/lib/blocker-validator.sh": ("blocker_",),
    ".ci/scripts/lib/common.sh": ("review_",),
}

# Bash name -> Python name, where the naming rule does not reach.
ALIASES: dict[str, str] = {
    "account_spawn": "spawn_background",
}

_BASH_FN = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s*\(\)", re.MULTILINE)
_PY_DEF = re.compile(r"^def ([A-Za-z_][A-Za-z0-9_]*)", re.MULTILINE)


def _prefix(lib: str) -> str:
    return pathlib.PurePosixPath(lib).name.removesuffix(".sh").replace("-", "_") + "_"


def candidates(fn: str, lib: str) -> set[str]:
    out = {fn, fn.lstrip("_")}
    for pre in (_prefix(lib), *PREFIXES.get(lib, ())):
        for name in (fn, fn.lstrip("_")):
            bare = name.removeprefix(pre)
            out |= {bare, bare.lstrip("_")}
    if fn in ALIASES:
        out.add(ALIASES[fn])
    return out


def unported(bash_text: str, py_texts: list[str], lib: str) -> list[str]:
    defs: set[str] = set()
    for t in py_texts:
        defs |= set(_PY_DEF.findall(t))
    return [fn for fn in _BASH_FN.findall(bash_text) if not (candidates(fn, lib) & defs)]


def findings(root: pathlib.Path) -> list[str]:
    out: list[str] = []
    baseline = json.loads((root / BASELINE).read_text(encoding="utf-8"))
    listed = sorted(
        p.relative_to(root).as_posix() for d in LIB_DIRS for p in (root / d).glob("*.sh")
    )
    out.extend(
        "%s is not in LIBS: name its Python modules, or port and delete it" % sh
        for sh in listed
        if sh not in LIBS
    )
    for lib, mods in LIBS.items():
        sh_path = root / lib
        if not sh_path.exists():
            if baseline.get(lib):
                out.append("%s: the library is gone; drop its baseline entry" % lib)
            continue
        bash_text = sh_path.read_text(encoding="utf-8")
        py_texts = [
            (root / CORE_DIR / m).read_text(encoding="utf-8")
            for m in mods
            if (root / CORE_DIR / m).exists()
        ]
        gaps = set(unported(bash_text, py_texts, lib))
        known = set(baseline.get(lib, []))
        present = set(_BASH_FN.findall(bash_text))
        out.extend(
            "%s: %s() has no Python twin in %s (NEW unported function)" % (lib, fn, ", ".join(mods))
            for fn in sorted(gaps - known)
        )
        out.extend(
            "%s: baseline entry %s %s; remove it (the baseline only shrinks)"
            % (lib, fn, "now has a Python twin" if fn in present else "no longer exists")
            for fn in sorted(known - gaps)
        )
    return out


def selftest() -> bool:
    """True when a control FAILED. Each control plants one defect in an in-memory library."""
    failed = False
    bash = "account_a() {\n:\n}\naccount_b() {\n:\n}\n"
    if unported(bash, ["def a():\n    pass\ndef b():\n    pass\n"], ".ci/lib/account.sh"):
        print("\u2717 control: a fully ported library read as having gaps", file=sys.stderr)
        failed = True
    if unported(
        bash + "account_new() {\n:\n}\n",
        ["def a():\n    pass\ndef b():\n    pass\n"],
        ".ci/lib/account.sh",
    ) != ["account_new"]:
        print(
            "\u2717 control: a NEW bash function without a twin was not reported", file=sys.stderr
        )
        failed = True
    if unported(bash, ["def a():\n    pass\n"], ".ci/lib/account.sh") != ["account_b"]:
        print("\u2717 control: a removed Python def was not reported", file=sys.stderr)
        failed = True
    if unported(
        "account_spawn() {\n:\n}\n", ["def spawn_background():\n    pass\n"], ".ci/lib/account.sh"
    ):
        print("\u2717 control: ALIASES were not honoured", file=sys.stderr)
        failed = True
    return failed


def main(argv: list[str]) -> int:
    rc = controls_first("bash-lib port completeness", selftest)
    if rc:
        return rc
    if "--selftest" in argv:
        return 0
    root = paths.repo_root()
    found = findings(root)
    if found:
        print("\u2717 %d bash-lib port finding(s):" % len(found), file=sys.stderr)
        for f in found:
            print("    %s" % f, file=sys.stderr)
        return 1
    baseline = json.loads((root / BASELINE).read_text(encoding="utf-8"))
    print(
        "\u2713 %d librar(ies): every bash function has a Python twin or a recorded gap (%d gap(s) in %s)"
        % (len(LIBS), sum(len(v) for v in baseline.values()), BASELINE)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
