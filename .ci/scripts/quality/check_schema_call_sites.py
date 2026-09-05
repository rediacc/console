#!/usr/bin/env python3
"""check:ci-schema-call-sites -- every schema-constrained model call retries exhaustion.

WHY THIS EXISTS. `retry_schema_exhaustion` turns "the model could not produce an object
matching the schema" into one retry instead of a hard failure. On 2026-09-05 a sweep
added it to the judge call sites one at a time and MISSED THE FIFTH -- the one in
wl_shapedup.py -- and the commit that found it says so in its own subject: "the fifth
schema-constrained call site". Five examples checked individually is not the same claim
as the set being uniform, and the fifth is exactly what an example-based sweep drops.

THE INVARIANT. A function that builds a `--json-schema` model invocation must route its
subprocess through `retry_schema_exhaustion`. Not "most of them"; the whole set,
enumerated from the source, so a SIXTH site is covered the day it is written with no
edit here.

Blind spot, stated: this proves the helper is CALLED in the same function, not that its
result is used correctly. A site that calls it and discards `proc` passes here.

---- gate ----
step: Schema call sites
needs: none
why: a per-site sweep added the retry to four judge call sites and missed the fifth in
     wl_shapedup.py, because five examples are not a property over the set
---- end gate ----
"""

from __future__ import annotations

import ast
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
HELPER = "retry_schema_exhaustion"
MARKER = "--json-schema"
SPAWN = "subprocess."

# A walk that finds nothing prints a tick indistinguishable from a clean tree.
# Measured 2026-09-05: five sites across wl_judge.py and wl_shapedup.py.
MIN_SITES = 4


def sites(src: str) -> list[tuple[str, int, bool]]:
    """(name, line, routed) for each TOP-LEVEL function that builds a schema call.

    Top-level only, deliberately: the inner `_call` closures carry the argv, and the
    OUTER function is where the retry wraps them. Reporting the closure would name the
    wrong line and invite the fix in the wrong place.
    """
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return []
    out: list[tuple[str, int, bool]] = []
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef):
            continue
        body = ast.get_source_segment(src, node) or ""
        # A REAL call site SPAWNS something. test-judge-schema.py:498 `fake_run` names
        # `--json-schema` in a stub that returns a canned object. A name-based exclusion
        # (test-*.py) would be the same proxy-for-a-role mistake this repo has paid for
        # three times in one session; spawning is the property that distinguishes them.
        if MARKER in body and SPAWN in body:
            out.append((node.name, node.lineno, HELPER in body))
    return out


def selftest() -> int:
    bad = 0

    def ck(label: str, ok: bool) -> None:
        nonlocal bad
        print(f"  {'ok  ' if ok else 'FAIL'} {label}")
        if not ok:
            bad += 1

    routed = 'def a():\n    argv = ["--json-schema", s]\n    subprocess.run(argv)\n    retry_schema_exhaustion("a", p, c)\n'
    bare = 'def a():\n    argv = ["--json-schema", s]\n    return subprocess.run(argv)\n'
    ck("THE MISSED SHAPE is found: a schema call with no retry", sites(bare) == [("a", 1, False)])
    ck("CONTROL: the same call WITH the retry is silent", sites(routed)[0][2] is True)
    ck(
        "CONTROL: a function with no schema call is out of scope",
        sites("def a():\n    return 1\n") == [],
    )
    ck("CONTROL: unparseable source yields no verdict", sites("def (:") == [])
    ck(
        "CONTROL: an inner closure is not reported -- the OUTER function owns the retry",
        [
            n
            for n, _, _ in sites(
                'def outer():\n    def _call():\n        return subprocess.run(["--json-schema"])\n    retry_schema_exhaustion("x", p, _call)\n'
            )
        ]
        == ["outer"],
    )
    ck(
        "CONTROL: a test FAKE that only names the flag is not a call site",
        sites('def fake_run(argv):\n    assert "--json-schema" in argv\n    return Canned()\n')
        == [],
    )
    return bad


def main() -> int:
    print("schema call sites: controls first, then the verdict")
    failures = selftest()
    if failures:
        print(
            "✗ instrument control failed; every verdict below would be meaningless", file=sys.stderr
        )
        return 2

    listed = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", ".claude/hooks"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()

    found: list[tuple[str, str, int, bool]] = []
    for rel in listed:
        if not rel.endswith(".py"):
            continue
        src = (ROOT / rel).read_text(encoding="utf-8", errors="replace")
        if MARKER not in src:
            continue
        for name, line, routed in sites(src):
            found.append((rel, name, line, routed))

    if len(found) < MIN_SITES:
        print(
            f"✗ VACUOUS: found {len(found)} schema-constrained call site(s), floor {MIN_SITES}. "
            "The walk lost its corpus; refusing a verdict.",
            file=sys.stderr,
        )
        return 1

    unrouted = [(r, n, ln) for r, n, ln, ok in found if not ok]
    if unrouted:
        print(
            f"✗ {len(unrouted)} schema-constrained call site(s) with no exhaustion retry:",
            file=sys.stderr,
        )
        for rel, name, line in unrouted:
            print(f"    {rel}:{line} {name}()", file=sys.stderr)
        print(
            f"\n  Route the subprocess through {HELPER}, as the other sites do. A schema\n"
            "  exhaustion is a flake, not a verdict, and an unrouted site turns it into one.",
            file=sys.stderr,
        )
        return 1

    print(f"✓ schema call sites: all {len(found)} route through {HELPER}")
    print(f"  Blind spot: this proves {HELPER} is CALLED in the same function, never that")
    print("  its result is used -- a site that calls it and discards `proc` passes here.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
