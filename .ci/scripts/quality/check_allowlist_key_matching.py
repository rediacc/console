#!/usr/bin/env python3
"""check:ci-allowlist-key-matching -- an allowlist key must be matched by EQUALITY.

WHY THIS EXISTS. .ci/config/docker-npm-pin-exclusions.json is keyed `<path>:<line>` and
was once consumed with `if k in line`. private/account/Dockerfile carries a bare
`npm install` on line 67 and `npm install --omit=dev && \\` on line 91, so the SHORT key
claimed the LONG key's line, the long entry matched nothing, and the dead-entry report
named the correct key as the one to delete. The fix was to match with `==`.

THE INVARIANT THIS GATES is the matcher, not the key shape. A first draft of this gate
refused configs where one key is a prefix of another; run against the tree it flagged
those two npm-install keys, which are both live, both correct, and harmless under
equality. That gate would have made a correct config carry an exemption for a
non-problem. Key shapes are the SYMPTOM; `in` is the DEFECT.

THE RULE. In a script that loads a config under .ci/config/, a key drawn from that config
must not be tested against a line of text with `in` or `.startswith(`. Compare with `==`,
or build the full key and look it up.

Usage: check_allowlist_key_matching.py [--selftest]

---- gate ----
step: Allowlist key matching
needs: none
why: docker-npm-pin-exclusions.json was matched with `k in line`, so the bare
     `npm install` key claimed the `npm install --omit=dev` line and the correct
     entry was reported as dead scaffolding
---- end gate ----
"""

from __future__ import annotations

import ast
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]

# A loop variable holding an allowlist KEY, and a variable holding a line of TEXT.
KEYISH = ("k", "key", "excl", "entry", "pat", "prefix")
TEXTISH = ("line", "raw", "src", "text", "content", "body", "haystack")

# The corpus cannot be allowed to vanish: a walk that lists nothing prints a tick that is
# indistinguishable from a clean tree. See scripts/check-enumeration-vacuity.ts.
MIN_CONSUMERS = 2


def loads_config(src: str) -> bool:
    """Does this script read a file under .ci/config/?"""
    return ".ci/config/" in src


def _name(node: ast.AST) -> str:
    return node.id.lower() if isinstance(node, ast.Name) else ""


def substring_matches(src: str) -> list[str]:
    """`<keyish> in <textish>` or `<textish>.startswith(<keyish>)` -- both are the defect."""
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return []
    out: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare) and len(node.ops) == 1 and isinstance(node.ops[0], ast.In):
            left, right = _name(node.left), _name(node.comparators[0])
            if left.startswith(KEYISH) and right.startswith(TEXTISH):
                out.append(f"line {node.lineno}: `{left} in {right}` matches a key by substring")
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "startswith"
            and node.args
        ):
            obj, arg = _name(node.func.value), _name(node.args[0])
            if obj.startswith(TEXTISH) and arg.startswith(KEYISH):
                out.append(f"line {node.lineno}: `{obj}.startswith({arg})` matches by prefix")
    return sorted(set(out))


def selftest() -> int:
    bad = 0

    def ck(label: str, ok: bool) -> None:
        nonlocal bad
        print(f"  {'ok  ' if ok else 'FAIL'} {label}")
        if not ok:
            bad += 1

    ck(
        "THE REAL DEFECT is found",
        len(substring_matches("for k in excl:\n    if k in line:\n        pass\n")) == 1,
    )
    ck(
        "a prefix test is found too",
        len(substring_matches("for key in excl:\n    if line.startswith(key):\n        pass\n"))
        == 1,
    )
    ck(
        "CONTROL: equality is the fix, and is silent",
        substring_matches("for k in excl:\n    if k == line:\n        pass\n") == [],
    )
    ck(
        "CONTROL: a key in a DICT is a lookup, not a substring test",
        substring_matches("if key in excl:\n    pass\n") == [],
    )
    ck(
        "CONTROL: an unrelated membership test is not flagged",
        substring_matches("if name in seen:\n    pass\n") == [],
    )
    ck("CONTROL: unparseable source yields no verdict", substring_matches("def (:") == [])
    return bad


def main(argv: list[str]) -> int:
    print("allowlist key matching: controls first, then the verdict")
    failures = selftest()
    if argv[1:2] == ["--selftest"]:
        print(f"{'✓' if not failures else '✗'} selftest: {failures} failure(s)")
        return 1 if failures else 0
    if failures:
        print(
            "✗ instrument control failed; every verdict below would be meaningless", file=sys.stderr
        )
        return 2

    listed = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", ".ci/scripts", "scripts"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    consumers = [
        f
        for f in listed
        if f.endswith(".py")
        and loads_config((ROOT / f).read_text(encoding="utf-8", errors="replace"))
    ]

    if len(consumers) < MIN_CONSUMERS:
        print(
            f"✗ VACUOUS: found {len(consumers)} config-reading script(s), floor {MIN_CONSUMERS}. "
            "The walk lost its corpus; refusing a verdict.",
            file=sys.stderr,
        )
        return 1

    findings: list[str] = []
    for f in consumers:
        src = (ROOT / f).read_text(encoding="utf-8", errors="replace")
        findings.extend(f"{f}: {hit}" for hit in substring_matches(src))

    if findings:
        print(f"✗ {len(findings)} allowlist key(s) matched by substring:", file=sys.stderr)
        for f in findings:
            print(f"    {f}", file=sys.stderr)
        print(
            "\n  A key that is a prefix of another key claims the other one's line. The\n"
            "  longer entry then matches nothing and gets reported as dead scaffolding.\n"
            "  Fix: compare with `==`, or build the full key and look it up in the dict.",
            file=sys.stderr,
        )
        return 1

    print(
        f"✓ allowlist key matching: {len(consumers)} config-reading script(s), all match by equality"
    )
    print("  Blind spot: this reads NAMES, so a key variable called `n` is invisible to it.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
