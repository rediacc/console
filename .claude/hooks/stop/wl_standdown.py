"""wl_standdown: the Stop hook's stand-down profiles, the keep-lists that decide which checks still block while the session is told to wait.

THREE STATES STAND THE BATTERY DOWN, and all share one mechanism. A KEEP-list rather than a drop-list, deliberately: a check that is not kept stands down, which is what "should not be invoked" means, and it matches `check_tier`'s rule that an unknown key is hygiene.

PR_LOOP PARKS NOTHING SILENTLY. Every effort.json key that blocks at `high` or below (a FLOOR key included) is either kept by PR_LOOP or named in PARKED_BY_DESIGN with the reason it stands down; test_wl_standdown_class.py fails on a key that is neither. The keep-list alone let `writers-now-due` (operator ruling #ac2de21f: a /writers-now round at least hourly at effort high) block nowhere: the development tree stops under PR_LOOP, which named it in no set, and 81 stops in a row parked it ("Stood down: ... writers-now-due x81", session ace763dd, 2026-11-23). A new check has to be placed in a keep set or argued into PARKED_BY_DESIGN before the class guard passes.

  CONC_WAIT  every queued item is held by a live plan's mutex or Owns and nothing this session could start (operator 2026-09-24, first given for a full writer cap: stand the order down while nothing can start, with "exceptions like 2% compaction"; agent/plans/PLAN-stop-hook-cap-saturated-wait.md, narrowed to file-clash queues when the writer limit was removed, agent/plans/PLAN-unlimited-writers.md). `wl_roster.concurrency_wait` decides it, because it needs the roster's queue holds.

THE EFFORT LEVEL RUNS FIRST (wl_effort, agent/plans/PLAN-stop-hook-effort.md): it turns each check into a block, an advisory or nothing, and these profiles then park what remains. The FLOOR that blocks at every level lives in wl_floor, beside CORE, and is sealed the same way.

  PR_LOOP   the checkout is on the one-plan-per-PR loop (`wl_prscope.loop_state`, kind other than off-loop; operator ruling 2026-10-03, agent/plans/PLAN-stop-hook-one-plan-scope.md Design 4). The hook blocks only on the live PR's plan set, its CI and reviews, the items on that set's epics and the loop's own duties; every other check is parked and named in one queued line.

  LANDING_TREE  the stop runs in the landing tree (agent/plans/PLAN-simple-two-tree-loop.md B2). The landing tree's job is to land the one PR, so it keeps the PR protection (_PR_GUARD) plus the loop's duties (the landing state machine's step rides `loop-next`) and parks the checks that start new work.

`profile_for` picks one: LANDING_TREE by the tree role first, then CONC_WAIT over PR_LOOP, the narrower declaration. The development tree always builds. The phase verb and its FOCUS profile were deleted with agent/plans/PLAN-simple-two-tree-loop.md B10; the tree role replaced them.

SEALED. `.ci/policy/worklist-env-registry.json` lists this file under `sealed_modules`: it reads no environment variable and imports only the standard library, and `FOCUS_PR_TTL_S` is pinned as a literal. A knob that retuned a keep-list would be exactly the escape hatch the roster rules out.

EACH KEY LITERAL APPEARS EXACTLY ONCE IN THIS FILE, so every mutation control that removes one line (`mutated_hook` asserts the count is 1) is unambiguous, and the producer scan in test_wl_cap_wait.py c9 stays meaningful. `pr-finish` is kept by several profiles in different tiers, so it is named once through `_PR_FINISH`; `defer-expired`, `queue-slot` and `undefaulted` likewise through `_DEFER_EXPIRED`, `_QUEUE_SLOT` and `_UNDEFAULTED`.
"""

import types
from typing import NamedTuple


class Profile(NamedTuple):
    name: str
    keeps: frozenset  # exact keys kept
    prefixes: tuple  # keys kept whatever their `:<subject>` suffix
    always_keeps: (
        frozenset  # kept only when the violation is on the always tier (a hook-bug branch)
    )
    compaction_keys: frozenset  # kept only when compaction is imminent


# The pr-babysit finish line. PR_LOOP and LANDING_TREE keep it outright; CONC_WAIT keeps only its always-tier HOOK BUG branch (a blind finish line must say so even in a concurrency wait).
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
        # The roster: each means a lease is on nobody, or a running writer owes liveness.
        "roster-silent",
        "roster-unleased",
        "roster-dead",
        # A sub-agent an API error killed (wl_roster_resume): only the lead's SendMessage restarts it, and a saturated wait is exactly when its silence would read as a writer still running.
        "resume-dead-agent",
        # A wait on background work with no wake-up timer (wl_wake): every profile stands the session down to WAIT, which is exactly when a hung task would never wake it.
        "wake-timer",
        # The operator's ownership question for a checklist whose owner is not live: parking it would turn it back into the advisory nobody settles.
        "cl-owner",
        # Two live writers already breaking a plan mutex or sharing files (agent/plans/PLAN-plan-priority-concurrency.md section 5c): waiting does not resolve it.
        "roster-concurrency",
        # A shell command stuck past its limit holds the turn itself: standing down to WAIT would sit behind the very command that never returns.
        "stuck-shell",
        "ladder-gone",
        "ladder-idle",
        # Per-commit reviews (agent/plans/PLAN-per-commit-review.md section 7): an open high finding or a hand-edited record protects the PR, and waiting on writers resolves neither, so both profiles keep them.
        "commit-review",
        "commit-review-malformed",
        # The context is past ctx_budget.WISDOM_FRACTION with its in-flight work not handed over (wl_checks.wisdom_due): waiting on writers does not write the briefs, and the window closes at compaction.
        "wisdom-due",
        # A trapguard rule raised and was skipped (wl_trapfires): a FLOOR key (wl_floor.FLOOR), which no effort level turns off, so no profile parks it either.
        "trapguard-errors",
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

# An expired `[?]` DEFAULT is an order to execute it: both the concurrency wait and the PR loop keep it.
_DEFER_EXPIRED = "defer-expired"
# Queued writer work nothing holds any more: the concurrency wait keeps it, and so does the development tree's PR loop, whose writers it queued.
_QUEUE_SLOT = "queue-slot"
# A `[?]` with no DEFAULT can never expire into `defer-expired`, so both profiles that keep the expiry keep this too. A deferral is never queued out of the PR loop's scope (wl_store.classify_items).
_UNDEFAULTED = "undefaulted"
# The concurrency wait's own additions: a queue lease nothing holds any more, and deferrals that must execute.
_CONC_WAIT_ONLY = frozenset(
    {
        _QUEUE_SLOT,
        _DEFER_EXPIRED,
        _UNDEFAULTED,
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
        # Session hygiene, not plan scope (2026-10-24): twelve hung wait loops a sub-agent armed lived for hours while every stop printed "Stood down: bg-orphan x158". The shells are this session's own process tree on every PR, so the loop keeps the check. CONC_WAIT still parks it, as its plan's hygiene table lists it.
        "bg-orphan",
    }
) | {_DEFER_EXPIRED}
# The checks that start, adopt, schedule or settle plan work (writers-now-due, plan-box-owed and the queue slot sit beside the starters): the development tree's PR loop keeps them, the landing tree ("finish, don't start") parks them.
_BUILD_ONLY = frozenset(
    {
        "idle-stall",
        "unblocked-claim",
        "plan-unimplemented",
        "plan-adopted",
        # No /writers-now round of this session in the last hour while Promoted boxes are open (operator ruling #ac2de21f, wl_writersnow.due): the round is how the development tree starts writers.
        "writers-now-due",
        # An armed action of this session fired, expired or went void (agent/plans/PLAN-armed-actions.md Design 10): it starts held development work the moment its trigger fires; the landing tree finishes and does not start (ruling B2), and it owns no development arms.
        "armed-action-due",
        # A commit landed on the live branch names a still-open box with no investigation row (wl_boxaudit): the tick duty of the plan the branch builds.
        "plan-box-owed",
        # Box ticks finished writers reported, their commits landed (wl_planbox's pending-tick queue): the same tick duty as plan-box-owed, applied with `worklist.py --apply-ticks`.
        "ready-ticks",
        _QUEUE_SLOT,
    }
)
# The development tree's own duties beyond the plan set (agent/plans/PLAN-stop-hook-one-plan-scope.md ruling 1d: dead watches, findings this session raised): the PR loop keeps them, the landing tree parks them with the rest of the work it does not start.
_DEV_DUTIES = frozenset(
    {
        _UNDEFAULTED,
        # The stops that end the turn with work in hand: three stops with nothing moving, a wait with nothing to wake it, a question announced and not asked (CLAUDE.md rule 2, the ten-stop loop).
        "stuck",
        "idle",
        "pending-ask",
        # The session's work loop: its crons died, or one carries a schedule nothing can parse (and so counts as no loop).
        "loop-died",
        "broken-schedule",
        # A production fault this session claimed or ticked without evidence (wl_schedred, wl_opshealth), and the off-box alerter whose silence would hide one.
        "scheduled-red",
        "ops-health-red",
        "ops-health-offbox-stale",
    }
)
# The PR loop's own additions: the loop's duties, the PR plan's own pushes, the build checks and the development tree's duties.
_PR_LOOP_ONLY = _LOOP_DUTIES | _BUILD_ONLY | _DEV_DUTIES

CONC_WAIT = Profile(
    "concurrency-wait", CORE | _CONC_WAIT_ONLY, PREFIXES, frozenset({_PR_FINISH}), COMPACTION_KEYS
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
PROFILES = (CONC_WAIT, PR_LOOP, LANDING_TREE)

# THE CHECKS PR_LOOP PARKS ON PURPOSE, each with its reason. Every effort.json key that blocks at `high` or below is kept by PR_LOOP (here, or through wl_checks' IDLE_KEEPS, WORKTREE_KEEPS and LANDING_KEEPS, which `wl_checks.stand_down_keeps` folds in) or named here; test_wl_standdown_class.py refuses a key that is neither, and a key that is both. The scope reasons cite agent/plans/PLAN-stop-hook-one-plan-scope.md ruling 2: every item and plan outside the PR's plan set is one queued line.
_ITEM_SCOPE = "a ladder over every owned open item; items outside the PR plan's epic are one queued line (ruling 2), and in-epic ones block through open-items"
_JUDGE = "the judge's audit of the closing message's evidence wording, not a duty of the plan set; Design 4 parks the judge battery (SC5 names no-remaining)"
_HYGIENE = "session or repository hygiene with no bearing on the PR's plan set"
_PROGRAMS = "an agent/programs checklist is work outside the PR's plan set (ruling 2)"
PARKED_BY_DESIGN = types.MappingProxyType(
    {
        "wl-stale": _ITEM_SCOPE,
        "ladder-investigate": _ITEM_SCOPE,
        "ladder-resolve": _ITEM_SCOPE,
        "unconfirmed": "the wording of a [?] item's operator claim, a judge-side honesty check; the deferral itself still blocks through defer-expired and undefaulted",
        "ci-waiting": "forces the aged [?] backlog while a CI watch is the only work in flight; that backlog is the queued work ruling 2 parks",
        "unjustified": _JUDGE,
        "uncited": _JUDGE,
        "unstated": _JUDGE,
        "mislabelled": _JUDGE,
        "phantom-gate": _JUDGE,
        "no-remaining": _JUDGE,
        "plan-fidelity": _JUDGE,
        "intent-expired": "a stated intent's horizon, a claim of the message rather than a box of the plan set; open work it covered still blocks through open-items",
        "cl-producing": _PROGRAMS,
        "cl-flip": _PROGRAMS,
        "cl-waves": _PROGRAMS,
        "lessons-weekly": _HYGIENE,
        "many-work-crons": _HYGIENE
        + " (a second work cron costs turns; loop-died and broken-schedule are kept)",
        "sweep-moment": _HYGIENE,
        "stale-local": _HYGIENE + " (a stale local branch, not the live one)",
        "submodule": _HYGIENE + " (rulable, wl_ruling.RULABLE_CHECKS)",
        "bigpieces": _HYGIENE + " (rulable, wl_ruling.RULABLE_CHECKS)",
        "plan-drift": "Design 4's own example of a stood-down check; drift is a docs question, not a box of the plan set",
        "solo-grind": "Design 4 SC5 stands it down by name; the PR loop's writer cadence is writers-now-due, which it keeps",
    }
)
# The tree roles of wl_prscope, repeated here because this module imports nothing.
ROLE_LANDING = "landing"
ROLE_DEVELOPMENT = "development"


def profile_for(role, conc_wait, on_loop):
    """The stand-down profile of one stop, None for the full battery. The tree role decides first (agent/plans/PLAN-simple-two-tree-loop.md B2): the landing tree always stands down to LANDING_TREE. Then the concurrency wait, then the PR loop."""
    if role == ROLE_LANDING:
        return LANDING_TREE
    if conc_wait:
        return CONC_WAIT
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
