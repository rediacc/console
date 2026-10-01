"""Every function in a `.ci/lib/*.sh` or `.ci/scripts/lib/*.sh` library has a Python twin. No baseline: an unmapped function is a finding.

WHY. W7P5-b ported the bash libraries one function at a time, and "account.sh 22 of 22" was a count a writer made by hand on 2026-09-24. Nothing held it: a bash function added the next day, or a Python def renamed away, would leave the twin incomplete while every differential stayed green, because a differential only compares the functions it already drives.

WHY THERE IS NO BASELINE ANY MORE (2026-10-01, PLAN-retire-bash-oracles G2). The shrink-only baseline once held 59 "unported" functions. Every one of them had a twin all along; the gate could not see it. 39 were class methods (fixed 2026-09-27), 5 were log functions in `rediacc_ci/log.py`, which no module list named, and the last 15 were twins under a different name, each of whose docstrings cites the bash function it ports (`compose_argv` says "`_service_compose`", `class_is_infra` says "`review_attempt_class_is_infra`"). An empty baseline is a door: the next `--write-baseline` would re-absorb a genuinely unported function without anyone reading it. So the door is gone, and a gap is a red until it is ported or named in `ALIASES`.

WHAT IT CHECKS, per library in `LIBS`:
  - each bash function maps to a `def` (module level OR a class method) in the library's Python modules, through `ALIASES` or by the naming rule (the name itself, the name minus the library prefix, and either one without leading underscores);
  - an `ALIASES` entry is QUALIFIED, `<module>:<def>`, and the def must exist in THAT module: an alias that resolves only because some other module happens to carry a def of the same name is the false twin this rule refuses;
  - a `.sh` under `LIB_DIRS` missing from `LIBS` is a finding, so a new library cannot bypass the gate;
  - a `LIBS` library whose `.sh` is gone, a listed module that does not exist, and an alias whose bash function no longer exists are findings, so the tables only describe the tree that is there.

THE RETIREMENT IS BUILT IN. When B1/B3 delete a library, its `LIBS` row must go in the same change. When the last row goes, zero functions are scanned, and that is a finding telling the author to retire this gate (package.json key, manifest entry, workflow step), because a gate that scans nothing passes forever.

Exit 0 clean, 1 on findings, 2 when the gate's own controls fail (controls_first convention).
"""

from __future__ import annotations

import pathlib
import re
import sys

from rediacc_ci import paths
from rediacc_ci.controls import controls_first

# Every .sh in these directories must be listed in LIBS.
LIB_DIRS = (".ci/lib", ".ci/scripts/lib")
CORE_DIR = ".ci/rediacc_ci/core"
PLAN = "agent/plans/PLAN-retire-bash-oracles.md (task G2)"

# Library (repo path) -> the modules that carry its twin, relative to rediacc_ci/core. Every .sh under LIB_DIRS must appear here.
LIBS: dict[str, tuple[str, ...]] = {
    ".ci/lib/account.sh": ("account.py", "account_lifecycle.py"),
    ".ci/lib/devbox.sh": ("devbox.py",),
    ".ci/lib/local-common.sh": ("local_common.py",),
    ".ci/lib/service.sh": ("service.py",),
    # allowlist.py because `_blocker_py` is nothing but a forwarder to `python3 -m rediacc_ci.core.allowlist`.
    ".ci/scripts/lib/blocker-validator.sh": ("blocker_validator.py", "allowlist.py"),
    # ../log.py because common.sh's log_* functions are ported there and nowhere else; it was missing from this list until 2026-10-01, which left 5 ported functions baselined as unported.
    ".ci/scripts/lib/common.sh": (
        "common.py",
        "review_budget.py",
        "ghx.py",
        "../proc.py",
        "../log.py",
    ),
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

# Library -> bash name -> "<module>:<def>", where the naming rule does not reach. The module must be one of the library's LIBS modules and must define the def; each target's docstring or comment names the bash function it ports, which is how every row below was checked (2026-10-01).
ALIASES: dict[str, dict[str, str]] = {
    ".ci/lib/account.sh": {
        "account_spawn": "account_lifecycle.py:spawn_background",
    },
    ".ci/lib/service.sh": {
        "_service_compose": "service.py:compose_argv",
    },
    ".ci/scripts/lib/blocker-validator.sh": {
        "_blocker_emit": "blocker_validator.py:replay_frames",
        "_blocker_py": "allowlist.py:main",
    },
    ".ci/scripts/lib/common.sh": {
        # ghx.gh(attempts=3) is _gh_probe's retry; GhResult.json() is gh_json's parse-or-refuse half (ghx.py TRAP 1 and TRAP 3).
        "_gh_probe": "ghx.py:gh",
        "gh_retry": "ghx.py:gh",
        "gh_json": "ghx.py:json",
        "get_repo_root": "common.py:repo_root",
        "pr_diff_loc": "review_budget.py:diff_loc",
        "review_attempt_class_is_infra": "review_budget.py:class_is_infra",
        "log_info": "../log.py:info",
        "log_warn": "../log.py:warn",
        "log_error": "../log.py:error",
        "log_step": "../log.py:step",
        "log_debug": "../log.py:debug",
    },
    ".ci/scripts/lib/toolchain.sh": {
        "toolchain_load": "toolchain.py:load_pins",
        # The `pairs` and `keys` verbs of toolchain.main print load_pins() in the two shapes these produce.
        "toolchain_pairs": "toolchain.py:load_pins",
        "toolchain_keys": "toolchain.py:load_pins",
        "_toolchain_need_checksums": "toolchain.py:checksums",
        "_toolchain_os": "toolchain.py:os_name",
        "_toolchain_sha256sum": "toolchain.py:sha256_of",
    },
}

_BASH_FN = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s*\(\)", re.MULTILINE)
# Indented defs count: a twin may be a class method (core/devbox.py ports devbox.sh as methods of one class). A column-0-only match left 39 ported devbox functions baselined as "unported" until 2026-09-27.
_PY_DEF = re.compile(r"^[ \t]*def ([A-Za-z_][A-Za-z0-9_]*)", re.MULTILINE)


def _prefix(lib: str) -> str:
    return pathlib.PurePosixPath(lib).name.removesuffix(".sh").replace("-", "_") + "_"


def candidates(fn: str, lib: str) -> set[str]:
    out = {fn, fn.lstrip("_")}
    for pre in (_prefix(lib), *PREFIXES.get(lib, ())):
        for name in (fn, fn.lstrip("_")):
            bare = name.removeprefix(pre)
            out |= {bare, bare.lstrip("_")}
    return out


def bash_functions(bash_text: str) -> list[str]:
    return _BASH_FN.findall(bash_text)


def unported(
    bash_text: str,
    py: dict[str, str],
    lib: str,
    aliases: dict[str, str] | None = None,
) -> list[str]:
    """Bash functions in `bash_text` with no twin in `py` (module name -> source).

    An aliased function is held to its alias ALONE, in the named module only; the naming rule is not consulted for it, so an alias cannot be satisfied by an unrelated def elsewhere.
    """
    by_mod = {mod: set(_PY_DEF.findall(text)) for mod, text in py.items()}
    every = set().union(*by_mod.values()) if by_mod else set()
    table = ALIASES.get(lib, {}) if aliases is None else aliases
    out = []
    for fn in bash_functions(bash_text):
        if fn in table:
            mod, _, name = table[fn].partition(":")
            if name not in by_mod.get(mod, set()):
                out.append(fn)
        elif not (candidates(fn, lib) & every):
            out.append(fn)
    return out


def table_findings(root: pathlib.Path) -> list[str]:
    """LIBS and ALIASES describe the tree as it is: no library, module or alias that names nothing."""
    listed = sorted(
        p.relative_to(root).as_posix() for d in LIB_DIRS for p in (root / d).glob("*.sh")
    )
    out = [
        "%s is not in LIBS: name its Python modules, or port and delete it" % sh
        for sh in listed
        if sh not in LIBS
    ]
    for lib, mods in LIBS.items():
        if not (root / lib).exists():
            out.append(
                "%s: the library is gone; drop its LIBS row and its ALIASES block in this change"
                % lib
            )
            continue
        out.extend(
            "%s: LIBS names %s, which does not exist under %s; fix the module list"
            % (lib, m, CORE_DIR)
            for m in mods
            if not (root / CORE_DIR / m).exists()
        )
    for lib, table in ALIASES.items():
        if lib not in LIBS:
            out.append("ALIASES[%s] names a library that is not in LIBS; drop the block" % lib)
            continue
        present = (
            set(bash_functions((root / lib).read_text(encoding="utf-8")))
            if (root / lib).exists()
            else set()
        )
        for fn, target in sorted(table.items()):
            mod, sep, name = target.partition(":")
            if not sep or not name:
                out.append("ALIASES[%s][%s] = %r is not '<module>:<def>'" % (lib, fn, target))
            elif mod not in LIBS[lib]:
                out.append(
                    "ALIASES[%s][%s] points into %s, which is not one of the library's LIBS modules (%s)"
                    % (lib, fn, mod, ", ".join(LIBS[lib]))
                )
            if (root / lib).exists() and fn not in present:
                out.append(
                    "ALIASES[%s][%s]: %s() no longer exists in the library; drop the alias"
                    % (lib, fn, fn)
                )
    return out


def scan(root: pathlib.Path) -> tuple[list[str], int, int]:
    """(findings, functions scanned, of which matched through ALIASES)."""
    out = table_findings(root)
    scanned = aliased = 0
    for lib, mods in LIBS.items():
        sh_path = root / lib
        if not sh_path.exists():
            continue
        bash_text = sh_path.read_text(encoding="utf-8")
        py = {
            m: (root / CORE_DIR / m).read_text(encoding="utf-8")
            for m in mods
            if (root / CORE_DIR / m).exists()
        }
        fns = bash_functions(bash_text)
        scanned += len(fns)
        aliased += sum(1 for fn in fns if fn in ALIASES.get(lib, {}))
        for fn in unported(bash_text, py, lib):
            if fn in ALIASES.get(lib, {}):
                out.append(
                    "%s: %s() is aliased to %s, which defines no such def; the twin was renamed or "
                    "removed, so repoint the alias at the twin or restore it"
                    % (lib, fn, ALIASES[lib][fn])
                )
            else:
                out.append(
                    "%s: %s() has no Python twin in %s. Port it there (a class method counts), or, if "
                    "the twin exists under another name, add ALIASES[%r][%r] = '<module>:<def>'"
                    % (lib, fn, ", ".join(mods), lib, fn)
                )
    if scanned == 0 and not out:
        out.append(
            "0 bash functions scanned: every library is gone, so this gate checks nothing. Retire it "
            "(package.json check:ci-bash-lib-ported, its manifest entry and workflow step) per %s"
            % PLAN
        )
    return out, scanned, aliased


def selftest() -> bool:
    """True when a control FAILED. Each control plants one defect in an in-memory library."""
    failed = False
    lib = ".ci/lib/account.sh"
    bash = "account_a() {\n:\n}\naccount_b() {\n:\n}\n"
    flat = {"m.py": "def a():\n    pass\ndef b():\n    pass\n"}

    def check(got: list[str], want: list[str], what: str) -> None:
        nonlocal failed
        if got != want:
            print("\u2717 control: %s (got %r, want %r)" % (what, got, want), file=sys.stderr)
            failed = True

    check(unported(bash, flat, lib, {}), [], "a fully ported library read as having gaps")
    check(
        unported(bash + "account_new() {\n:\n}\n", flat, lib, {}),
        ["account_new"],
        "a NEW bash function without a twin was not reported",
    )
    check(
        unported(bash, {"m.py": "def a():\n    pass\n"}, lib, {}),
        ["account_b"],
        "a removed Python def was not reported",
    )
    check(
        unported(
            bash,
            {"m.py": "class D:\n    def a(self):\n        pass\n    def b(self):\n        pass\n"},
            lib,
            {},
        ),
        [],
        "a twin written as a class method read as unported",
    )
    check(
        unported(bash, {"m.py": "class D:\n    def a(self):\n        pass\n"}, lib, {}),
        ["account_b"],
        "a class missing one ported METHOD read as complete",
    )
    alias = {"account_spawn": "m.py:spawn_background"}
    check(
        unported(
            "account_spawn() {\n:\n}\n", {"m.py": "def spawn_background():\n    pass\n"}, lib, alias
        ),
        [],
        "a qualified alias was not honoured",
    )
    check(
        unported(
            "account_spawn() {\n:\n}\n",
            {"m.py": "def other():\n    pass\n", "n.py": "def spawn_background():\n    pass\n"},
            lib,
            alias,
        ),
        ["account_spawn"],
        "an alias resolved through a def in a DIFFERENT module",
    )
    check(
        unported(
            "account_spawn() {\n:\n}\n",
            {"m.py": "def spawn():\n    pass\n"},
            lib,
            alias,
        ),
        ["account_spawn"],
        "an aliased function fell back to the naming rule when its alias target was gone",
    )
    return failed


def main(argv: list[str]) -> int:
    rc = controls_first("bash-lib port completeness", selftest)
    if rc:
        return rc
    if "--selftest" in argv:
        return 0
    found, scanned, aliased = scan(paths.repo_root())
    if found:
        print("\u2717 %d bash-lib port finding(s):" % len(found), file=sys.stderr)
        for f in found:
            print("    %s" % f, file=sys.stderr)
        return 1
    print(
        "\u2713 %d librar(ies), %d bash function(s): every one has a Python twin "
        "(%d by name, %d through ALIASES)" % (len(LIBS), scanned, scanned - aliased, aliased)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
