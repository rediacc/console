#!/usr/bin/env python3
"""Control for completion_evidence's citation scan, BOTH directions.

Separate from test-worklist-v5.sh on purpose. That harness drives the whole hook
against a fixture repo whose files I cannot cite, and its evidence section is a
deliberately sequenced fixture: an earlier attempt to add these cases inline
truncated the shared worklist file and broke the two SHA tests that string-replace
a line it had just deleted. A control that damages the suite it joins is not a
control. This calls the function directly against the REAL repo, where a resolving
path is knowable.

The bug: completion_evidence delegated to citation_state, which uses
CITE_RE.search and therefore judges only the FIRST citation in a line. A tick
carrying four resolving full paths read as evidence-free because a bare
"05-docs-and-decommission.md" happened to come first.
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import wl_checks as W

ROOT = pathlib.Path(__file__).resolve().parents[3]

# A path that really exists in this repo, so "resolving" means resolving.
REAL = ".claude/hooks/stop/wl_checks.py:1"

MUST_PASS = [
    (
        "a typo'd first citation must not hide a resolving one",
        f"cites bare-filename.md:12 first, then {REAL}",
    ),
    ("a single resolving citation is evidence", f"fixed it, see {REAL}"),
]

MUST_FAIL = [
    ("no citation at all is not evidence", "I finished it, all good"),
    ("one fabricated path is not evidence", "see totally/made/up/file.ts:99"),
    (
        "several citations, none resolving, is not evidence",
        "cites nowhere/at/all.md:12 and also other/fake.ts:7",
    ),
]


def main() -> int:
    bad = []
    for name, text in MUST_PASS:
        if not W.completion_evidence(ROOT, text):
            bad.append(f"MUST PASS but did not: {name}")
    for name, text in MUST_FAIL:
        if W.completion_evidence(ROOT, text):
            bad.append(f"MUST FAIL but passed: {name}")
    if bad:
        print(f"✗ completion_evidence: {len(bad)} control failure(s)")
        for b in bad:
            print(f"    {b}")
        return 1
    print(
        f"✓ completion_evidence: {len(MUST_PASS)} pass-cases, {len(MUST_FAIL)} fail-cases "
        "(scanning every citation did not make everything pass)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
