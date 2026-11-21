"""wl_standdown: the Stop hook's stand-down profiles, the keep-lists that decide which checks still block while the session is told to wait.

THREE STATES STAND THE BATTERY DOWN, and all share one mechanism. A KEEP-list rather than a drop-list, deliberately: a check added later stands down by default, which is what "should not be invoked" means, and it matches `check_tier`'s rule that an unknown key is hygiene.

  CAP_WAIT  every writer slot is verified live and nothing this session could start (operator 2026-09-24: "the stop hook should not be invoked (or should skip the order) when writer slots are full! There could be exceptions like 2% compaction etc."; agent/plans/PLAN-stop-hook-cap-saturated-wait.md). `wl_roster.cap_saturated_wait` decides it, because it needs the writer cap (`wl_roster.writer_cap`, QUEUE.md `writer_cap:`).

THE EFFORT LEVEL RUNS FIRST (wl_effort, agent/plans/PLAN-stop-hook-effort.md): it turns each check into a block, an advisory or nothing, and these profiles then park what remains. The FLOOR that blocks at every level lives in wl_floor, beside CORE, and is sealed the same way.

  PR_LOOP   the checkout is on the one-plan-per-PR loop (`wl_prscope.loop_state`, kind other than off-loop; operator ruling 2026-10-03, agent/plans/PLAN-stop-hook-one-plan-scope.md Design 4). The hook blocks only on the live PR's plan set, its CI and reviews, the items on that set's epics and the loop's own duties; every other check is parked and named in one queued line.

  LANDING_TREE  the stop runs in the landing tree (agent/plans/PLAN-simple-two-tree-loop.md B2). The landing tree's job is to land the one PR, so it keeps the PR protection (_PR_GUARD) plus the loop's duties (the landing state machine's step rides `loop-next`) and parks the checks that start new work.

`profile_for` picks one: LANDING_TREE by the tree role first, then CAP_WAIT over PR_LOOP, the narrower declaration. The development tree always builds. The phase verb and its FOCUS profile were deleted with agent/plans/PLAN-simple-two-tree-loop.md B10; the tree role replaced them.

SEALED. `.ci/policy/worklist-env-registry.json` lists this file under `sealed_modules`: it reads no environment variable and imports only the standard library, and `FOCUS_PR_TTL_S` is pinned as a literal. A knob that retuned a keep-list would be exactly the escape hatch the roster rules out.

EACH KEY LITERAL APPEARS EXACTLY ONCE IN THIS FILE, so every mutation control that removes one line (`mutated_hook` asserts the count is 1) is unambiguous, and the producer scan in test_wl_cap_wait.py c9 stays meaningful. `pr-finish` is kept by several profiles in different tiers, so it is named once through `_PR_FINISH`; `defer-expired` likewise through `_DEFER_EXPIRED`.
"""

from typing import NamedTuple


class Profile(NamedTuple):
    name: str
    keeps: frozenset  # exact keys kept
    prefixes: tuple  # keys kept whatever their `:<subject>` suffix
    always_keeps: (
        frozenset  # kept only when the violation is on the always tier (a hook-bug branch)
    )
    compaction_keys: frozenset  # kept only when compaction is imminent


# The pr-babysit finish line. PR_LOOP and LANDING_TREE keep it outright; CAP_WAIT keeps only its always-tier HOOK BUG branch (a blind finish line must say so even in a cap wait).
_PR_FINISH = "pr-finish"

# Shared by both profiles: what the lead CAN and MUST act on even while told to wait.
CORE = frozenset(
    {
        # Hook integrity: the hook cannot see, or said it has a bug.
        "event-unparseable",
        "hook-blind",
        "cl-shape",
        "adhoc-watch",
        "adhoc-watch-broken",
        # One-shot latches spent when computed (I1): hiding them would burn them unseen.
        "agent-bootstrap",
        # Owed to a party that cannot see this session's silence.
        "unread-reports",
        # The other tree waits on this one (wl_handover): an unanswered stuck or churn handover in the development tree, an answered lease the landing tree has not landed.
        "handover-open",
        "handover-land",
        # Ledger honesty: one-turn exits that start nothing.
        "completion",
        "found-not-fixed",
        "deferred-finding",
        "deflected-finding",
        # The roster: each means a slot is free, a lease is on nobody, or a running writer owes liveness.
        "roster-cap",
        "roster-silent",
        "roster-unleased",
        "roster-dead",
        # A wait on background work with no wake-up timer (wl_wake): every profile stands the session down to WAIT, which is exactly when a hung task would never wake it.
        "wake-timer",
        # The operator's ownership question for a checklist whose owner is not live: parking it would turn it back into the advisory nobody settles.
        "cl-owner",
        # Two live writers already breaking a plan mutex or sharing files (agent/plans/PLAN-plan-priority-concurrency.md section 5c): waiting does not resolve it.
        "roster-concurrency",
        "ladder-gone",
        "ladder-idle",
        # Per-commit reviews (agent/plans/PLAN-per-commit-review.md section 7): an open high finding or a hand-edited record protects the PR, and waiting on writers resolves neither, so both profiles keep them.
        "commit-review",
        "commit-review-malformed",
        # The context is past ctx_budget.WISDOM_FRACTION with its in-flight work not handed over (wl_checks.wisdom_due): waiting on writers does not write the briefs, and the window closes at compaction.
        "wisdom-due",
    }
)
# Kept whatever their suffix: `agent-pushback:<id>`, `giveup-claim:<id>` (one-shot latches, as above).
PREFIXES = ("agent-pushback:", "giveup-claim:")
# Kept only when compaction is imminent: the recovery document must be current before the context is summarised.
COMPACTION_KEYS = frozenset(
    {
        "agent-state",
        "agent-absent",
    }
)

# An expired `[?]` DEFAULT is an order to execute it: both the cap wait and the PR loop keep it.
_DEFER_EXPIRED = "defer-expired"
# The cap wait's own additions: a queue lease with a free slot, and deferrals that must execute.
_CAP_WAIT_ONLY = frozenset(
    {
        "queue-slot",
        _DEFER_EXPIRED,
        "undefaulted",
    }
)
# The checks that protect the PR itself, kept by both loop profiles.
_PR_GUARD = frozenset(
    {
        "ci-red",
        "ci-unreadable",
        "pr-unreadable",
        "pr-stale",
        "diverged",
        "bg-report",
        # Review Complete is a required check again (operator ruling 2026-10-03): an unanswered PR review or a failed review run holds the merge, so it blocks in the landing tree too.
        "pr-review",
    }
)

# The loop's duties both loop profiles keep (agent/plans/PLAN-stop-hook-one-plan-scope.md Design 4): the scoped open list, the loop's next step (in the landing tree, the state machine's step), and an expired DEFAULT.
_LOOP_DUTIES = frozenset(
    {
        "open-items",
        "loop-next",
        # Session hygiene, not plan scope (2026-10-24): twelve hung wait loops a sub-agent armed lived for hours while every stop printed "Stood down: bg-orphan x158". The shells are this session's own process tree on every PR, so the loop keeps the check. CAP_WAIT still parks it, as its plan's hygiene table lists it.
        "bg-orphan",
    }
) | {_DEFER_EXPIRED}
# The checks that start or adopt plan work: the development tree's PR loop keeps them, the landing tree ("finish, don't start") parks them.
_BUILD_ONLY = frozenset(
    {
        "idle-stall",
        "unblocked-claim",
        "plan-unimplemented",
        "plan-adopted",
    }
)
# The PR loop's own additions: the loop's duties, the PR plan's own pushes and the build checks.
_PR_LOOP_ONLY = _LOOP_DUTIES | _BUILD_ONLY

CAP_WAIT = Profile(
    "cap-wait", CORE | _CAP_WAIT_ONLY, PREFIXES, frozenset({_PR_FINISH}), COMPACTION_KEYS
)
# STATE.md freshness is a loop duty at every band (ruling 1d), so the compaction keys are full keeps here rather than late-band ones.
PR_LOOP = Profile(
    "pr-loop",
    CORE | _PR_GUARD | _PR_LOOP_ONLY | COMPACTION_KEYS | {_PR_FINISH},
    PREFIXES,
    frozenset(),
    frozenset(),
)
# THE LANDING TREE (agent/plans/PLAN-simple-two-tree-loop.md B2): the landing tree's standing profile, read from the tree role. It keeps what protects the PR and the loop's duties (the landing state machine's step rides `loop-next`), and parks what starts new work. STATE.md freshness is a loop duty, as in PR_LOOP.
LANDING_TREE = Profile(
    "landing",
    CORE | _PR_GUARD | _LOOP_DUTIES | COMPACTION_KEYS | {_PR_FINISH},
    PREFIXES,
    frozenset(),
    frozenset(),
)
PROFILES = (CAP_WAIT, PR_LOOP, LANDING_TREE)
# The tree roles of wl_prscope, repeated here because this module imports nothing.
ROLE_LANDING = "landing"
ROLE_DEVELOPMENT = "development"


def profile_for(role, cap_wait, on_loop):
    """The stand-down profile of one stop, None for the full battery. The tree role decides first (agent/plans/PLAN-simple-two-tree-loop.md B2): the landing tree always stands down to LANDING_TREE. Then the cap wait, then the PR loop."""
    if role == ROLE_LANDING:
        return LANDING_TREE
    if cap_wait:
        return CAP_WAIT
    return PR_LOOP if on_loop else None


def keeps(profile, key, always, compaction_due):
    """True when violation `key` still blocks under `profile`."""
    key = str(key)
    if key in profile.keeps or key.startswith(profile.prefixes):
        return True
    if always and key in profile.always_keeps:
        return True
    return bool(compaction_due) and key in profile.compaction_keys


def parked_line(counts, cap=6):
    """The parked keys in one phrase: the top `cap` by stops parked (`key xN`), then "+N more"; "nothing" when none. The PR loop's queued line."""
    counts = counts if isinstance(counts, dict) else {}
    ranked = sorted(counts.items(), key=lambda kv: (-int(kv[1] or 0), kv[0]))
    names = ", ".join("%s x%d" % (k, int(n or 0)) for k, n in ranked[:cap]) or "nothing"
    if len(ranked) > cap:
        names += " +%d more" % (len(ranked) - cap)
    return names


# The one PR read (wl_ci.pr_link) is cached this long per branch.
FOCUS_PR_TTL_S = 180
