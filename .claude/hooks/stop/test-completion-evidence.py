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

import importlib.util
import inspect
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


# =============================================================================
# v22: the deferred-finding detector and the sweep prompt
# =============================================================================
# Added 2026-08-26 after an operator had to ask, by hand, for the findings a
# session had reported and not fixed. The pre-existing `found, not fixed` gate
# matched ONE phrase at line-lead; every near-synonym the session actually used
# walked past it.
#
# Collects failures and RETURNS a code, matching main() above -- no bare
# `assert`, which ruff's S101 forbids in this tree and which would also vanish
# under `python -O`.


def _wl():
    spec = importlib.util.spec_from_file_location(
        "wl_checks_t", pathlib.Path(__file__).resolve().parent / "wl_checks.py"
    )
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


# The REAL phrasings, verbatim from the session that escaped the old gate.
MUST_HIT = [
    "- Reported, not fixed (not my file): rsv_sentinel_exists cannot tell.",
    "- Agent finding I didn't fix: the orphan parser.",
    "- Findings in code I do not own -- not fixed, reported.",
    "- I have not fixed the stale comment yet.",
]

# Must NOT fire on prose ABOUT the rule: a gate that cannot survive being
# written about is too broad, and this very file quotes its own triggers.
MUST_MISS = [
    "- This line says `found, not fixed` in backticks and is prose.",
    '- The message said "reported, not fixed" in quotes.',
    "- A totally normal line about progress.",
    "- Everything is fixed and verified.",
]


def _extra():
    w = _wl()
    bad = []
    bad.extend(
        f"MISSED a deferred finding: {line!r}" for line in MUST_HIT if not w.deferred_findings(line)
    )
    bad.extend(f"FALSE POSITIVE on: {line!r}" for line in MUST_MISS if w.deferred_findings(line))
    # CONTROL: it must be able to return nothing, or MUST_HIT would pass against
    # a function that simply echoes its input.
    if w.deferred_findings("") or w.deferred_findings("plain text, no admission"):
        bad.append("control failed: the detector fires on text with no admission")

    # The sweep prompt keys on idle_stall's early-return TEXT. The first version
    # looked for "closed", a word that string never contains, so the prompt
    # could never have fired. Pin the coupling: change the sentence and this
    # goes red rather than the prompt going silently off.
    sentinel = "an item left the open state this turn"
    if sentinel not in inspect.getsource(w.idle_stall):
        bad.append("idle_stall's early-return text changed; the sweep prompt would go vacuous")
    if "left the open state" not in sentinel:
        bad.append("the sweep condition substring no longer matches its sentinel")

    if bad:
        print(f"✗ deferred-finding/sweep: {len(bad)} failure(s)")
        for b in bad:
            print(f"    {b}")
        return 1
    print(
        f"ok  deferred-finding detector: {len(MUST_HIT)} hit, {len(MUST_MISS)} missed, "
        "control fired; sweep sentinel still matches"
    )
    return 0


# THE ENTRYPOINT IS LAST ON PURPOSE. It used to sit mid-file, so the cases
# appended below it never ran and the suite still exited 0 -- a test that cannot
# fail, caught only because its own output never appeared.
if __name__ == "__main__":
    sys.exit(main() or _extra())
