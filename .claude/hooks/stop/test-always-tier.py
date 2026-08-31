#!/usr/bin/env python3
"""Controls for the STOP-HOOK PRIORITY LADDER and the INVARIANT (`always`) tier.

    python3 .claude/hooks/stop/test-always-tier.py

Run by `.claude/hooks/test-hooks.sh` beside the other stop-hook selftests.

WHY A PINNED SET RATHER THAN A RULE. The admission rule for `always=True` is
prose (I1/I2/I3, in wl_checks.py beside `vadd`), and prose is exactly what
failed: the file DESCRIBED the rule, named the three checks where another party
pays in `carry_through_pause`, and left all three in the rotating tier where a
crowded session could starve them 23 keys deep. Nobody could point at a failing
assertion, because there was none. A pinned literal cannot be talked past: a
promotion or a demotion is a diff to this file, which is where the argument for
it belongs.

THE THIRD ASSERTION IS THE ONE THAT WOULD HAVE CAUGHT THE SEAM -- every key the
ladder classifies must be a key some `vadd` can actually produce. A ladder entry
naming a check that does not exist is silent by construction: the tier looks
populated, the check it meant to promote stays hygiene, and everything still
passes.
"""

import ast
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
CHECKS = HERE / "wl_checks.py"

# ---------------------------------------------------------------------------
# THE PINNED INVARIANT SET. A key belongs here iff it satisfies I1, I2 or I3 in
# wl_checks.py's tier comment. Adding one is a deliberate act with an argument
# attached; the corollary there (an I1-only check should move its latch to
# display time instead of being promoted) is why this set is not longer.
ALWAYS_KEYS = frozenset(
    {
        # I3 -- the hook or a gate cannot see.
        "event-unparseable",
        "hook-blind",
        "ci-unreadable",
        "review-unreadable",
        "pr-unreadable",
        "cl-shape",
        "adhoc-watch",
        "adhoc-watch-broken",
        "pr-finish",  # only its fail-closed arm; the ordinary finding rotates
        # I3 -- an evidence/liveness verdict whose silence would be read as a pass.
        "stuck",
        "idle-stall",
        "unblocked-claim",
        "pending-ask",
        "ci-red",
        # "Review Complete" red while everything else is clean: silence here
        # reads identically to a genuinely reviewed, unresolved-thread-free
        # head, which is the exact ambiguity CI_NONBLOCKING_CONTEXTS created
        # by design for ci_classify -- this check exists specifically to
        # un-hide it, so it cannot itself be left to rotate away.
        "review-red",
        "ladder-investigate",
        "ladder-gone",
        "ladder-idle",
        "ladder-resolve",
        "agent-bootstrap",
        # I1 -- the producer spends a budget while computing.
        "plan-fidelity",
        "bg-report",
        "agent-pushback",
        # I2 -- somebody else is blocked and cannot see this session stand down.
        "requests",
        "no-waiter",
        "no-waiter-asked",
        "waiter-lapsed",
        "unread-reports",
    }
)

# Keys built at runtime (`"agent-pushback:%s" % name`, the per-slug checklist
# keys from wl_checklist._ckey) or passed through from another module, so the
# AST sees no literal. Named here so assertion 3 stays honest about them
# instead of quietly ignoring every non-literal call.
DYNAMIC_KEYS = frozenset(
    {
        "agent-pushback",
        "cl-shape",
        "cl-flip",
        "cl-producing",
        "cl-waves",
    }
)

# Checks deliberately left at T_HYGIENE. Pinned for the same reason the ladder
# is: hygiene must be a DECISION, not what a check inherits by being forgotten.
HYGIENE_KEYS = frozenset(
    {
        "sweep-moment",
        "intent-expired",
        "brief",
        "plan-drift",
        "stale-local",
        "diverged",
        "submodule",
        "pr-stale",
        "solo-grind",
        "agent-state",
        "agent-absent",
        "docs-drift",
        "idle",
        "deferred-finding",
        "found-not-fixed",
        "no-remaining",
        "loop-died",
    }
)


def vadd_keys(tree):
    """Every literal first argument to a `vadd(...)` call in wl_checks.py."""
    keys, dynamic = set(), 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        if not (isinstance(fn, ast.Name) and fn.id == "vadd"):
            continue
        if not node.args:
            continue
        arg = node.args[0]
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            keys.add(arg.value)
        elif isinstance(arg, ast.BinOp) and isinstance(arg.left, ast.Constant):
            # `"agent-pushback:%s" % name` -- the literal prefix is the key.
            keys.add(str(arg.left.value).split(":", 1)[0])
        else:
            dynamic += 1
    return keys, dynamic


def always_keys(tree):
    """Keys whose `vadd` passes always=True. Positional second argument only,
    which is how every call site in the file spells it."""
    out = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        if not (isinstance(fn, ast.Name) and fn.id == "vadd"):
            continue
        if len(node.args) < 2:
            continue
        arg, flag = node.args[0], node.args[1]
        if not (isinstance(flag, ast.Constant) and flag.value is True):
            continue
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            out.add(arg.value)
        elif isinstance(arg, ast.BinOp) and isinstance(arg.left, ast.Constant):
            out.add(str(arg.left.value).split(":", 1)[0])
    return out


def main():
    sys.path.insert(0, str(HERE))
    import wl_checks  # noqa: PLC0415 -- the module under test

    tree = ast.parse(CHECKS.read_text(encoding="utf-8"))
    seen, dynamic = vadd_keys(tree)
    seen |= DYNAMIC_KEYS
    fails = []

    # 1. The invariant tier is exactly what is pinned above.
    got = always_keys(tree) | {
        # wl_checklist hands `cl-shape` through with always=True from its own
        # fail-closed arms; the AST of THIS file cannot see those.
        "cl-shape"
    }
    if got != ALWAYS_KEYS:
        fails.append(
            "the always tier drifted from the pinned set:\n"
            "    newly always: %s\n"
            "    no longer always: %s\n"
            "  If the change is deliberate, edit ALWAYS_KEYS here WITH the I1/I2/I3\n"
            "  argument for it -- that is what this control is for."
            % (sorted(got - ALWAYS_KEYS) or "(none)", sorted(ALWAYS_KEYS - got) or "(none)")
        )

    # 2. Every ladder key is a key some vadd can really produce. THIS is the
    #    assertion that catches a promotion that never took effect.
    laddered = set()
    for _tier, keys in wl_checks.PRIORITY_LADDER:
        laddered |= set(keys)
    ghosts = sorted(laddered - seen)
    if ghosts:
        fails.append(
            "PRIORITY_LADDER names %d key(s) no vadd produces, so their tier is\n"
            "  unreachable and they silently sit at T_HYGIENE: %s" % (len(ghosts), ghosts)
        )

    # 3. Every check is CLASSIFIED -- laddered or pinned as hygiene. A new check
    #    must be placed on purpose rather than default into the bottom tier.
    unclassified = sorted(seen - laddered - HYGIENE_KEYS)
    if unclassified:
        fails.append(
            "these checks are neither on the PRIORITY_LADDER nor pinned as hygiene,\n"
            "  so they default to T_HYGIENE by accident: %s" % unclassified
        )

    # 4. Every invariant is at least T_INTEGRITY. A check that cannot be rotated
    #    away but sorts below docs drift in the collapse is a contradiction.
    misplaced = sorted(k for k in ALWAYS_KEYS if wl_checks.check_tier(k) > wl_checks.T_INTEGRITY)
    if misplaced:
        fails.append("invariants sitting below T_INTEGRITY on the ladder: %s" % misplaced)

    # 5. THE CONTROL FOR THE CONTROL. The parser must actually find things; a
    #    green run over an empty key set proves nothing at all.
    if len(seen) < 40 or not always_keys(tree):
        fails.append(
            "the AST scan found only %d vadd key(s) and %d always -- the parser is\n"
            "  broken, so every assertion above passed vacuously"
            % (len(seen), len(always_keys(tree)))
        )

    # 6. check_tier's prefix matching, which every per-subject key depends on.
    if wl_checks.check_tier("cl-waves:demo") != wl_checks.T_MISSION:
        fails.append("check_tier does not resolve a `prefix:subject` key by its prefix")
    if wl_checks.check_tier("a-key-nobody-defined") != wl_checks.T_HYGIENE:
        fails.append("check_tier does not default an unknown key to T_HYGIENE")

    for f in fails:
        print("FAIL: %s" % f)
    print(
        "always-tier control: %d check key(s), %d invariant(s), %d dynamic call(s), %s"
        % (len(seen), len(ALWAYS_KEYS), dynamic, "FAILED" if fails else "ok")
    )
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
