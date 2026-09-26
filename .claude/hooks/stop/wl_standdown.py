"""wl_standdown: the Stop hook's stand-down profiles, the keep-lists that decide which checks still block while the session is told to wait.

TWO STATES STAND THE BATTERY DOWN, and both share one mechanism. A KEEP-list rather than a drop-list, deliberately: a check added later stands down by default, which is what "should not be invoked" means, and it matches `check_tier`'s rule that an unknown key is hygiene.

  CAP_WAIT  every writer slot is verified live and nothing this session could start (operator 2026-09-24: "the stop hook should not be invoked (or should skip the order) when writer slots are full! There could be exceptions like 2% compaction etc."; agent/plans/PLAN-stop-hook-cap-saturated-wait.md). `wl_roster.cap_saturated_wait` decides it, because it needs `WRITER_CAP`.
  FOCUS     the session declared a PR wind-down with `worklist.py --focus <me> babysit|merge` (operator 2026-09-25, spec Y: "Finish, don't start"; agent/plans/PLAN-stop-hook-focus-mode.md). What stays is what protects the PR: CI red, a dead watch, unread reports, STATE.md near compaction and hook integrity.

When both hold, FOCUS governs: it is the operator's explicit declaration, and its judge skip already covers the cap wait's.

SEALED. `.ci/policy/worklist-env-registry.json` lists this file under `sealed_modules`: it reads no environment variable and imports only the standard library, and `FOCUS_BATCH_MIN` / `FOCUS_MAX_HOURS` are pinned as literals. A knob that retuned a keep-list would be exactly the escape hatch the roster rules out.

EACH KEY LITERAL APPEARS EXACTLY ONCE IN THIS FILE, so every mutation control that removes one line (`mutated_hook` asserts the count is 1) is unambiguous, and the producer scan in test_wl_cap_wait.py c9 / test_wl_focus.py f13 stays meaningful. `pr-finish` is kept by both profiles in different tiers, so it is named once through `_PR_FINISH`.
"""

import datetime
import re
from typing import NamedTuple


class Profile(NamedTuple):
    name: str
    keeps: frozenset  # exact keys kept
    prefixes: tuple  # keys kept whatever their `:<subject>` suffix
    always_keeps: (
        frozenset  # kept only when the violation is on the always tier (a hook-bug branch)
    )
    compaction_keys: frozenset  # kept only when compaction is imminent


# The pr-babysit finish line. FOCUS keeps it outright; CAP_WAIT keeps only its always-tier HOOK BUG branch (finding 3 of the focus plan: a blind finish line must say so even in a cap wait).
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
        # Two live writers already breaking a plan mutex or sharing files (agent/plans/PLAN-plan-priority-concurrency.md section 5c): waiting does not resolve it.
        "roster-concurrency",
        "ladder-gone",
        "ladder-idle",
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

# The cap wait's own additions: a queue lease with a free slot, and deferrals that must execute.
_CAP_WAIT_ONLY = frozenset(
    {
        "queue-slot",
        "defer-expired",
        "undefaulted",
    }
)
# Focus's own additions: the checks that protect the PR itself.
_FOCUS_ONLY = frozenset(
    {
        "ci-red",
        "review-red",
        "ci-unreadable",
        "review-unreadable",
        "pr-unreadable",
        "pr-stale",
        "diverged",
        "bg-report",
        "focus-pr-items",
    }
)

CAP_WAIT = Profile(
    "cap-wait", CORE | _CAP_WAIT_ONLY, PREFIXES, frozenset({_PR_FINISH}), COMPACTION_KEYS
)
FOCUS = Profile("focus", CORE | _FOCUS_ONLY | {_PR_FINISH}, PREFIXES, frozenset(), COMPACTION_KEYS)
PROFILES = (CAP_WAIT, FOCUS)


def keeps(profile, key, always, compaction_due):
    """True when violation `key` still blocks under `profile`."""
    key = str(key)
    if key in profile.keeps or key.startswith(profile.prefixes):
        return True
    if always and key in profile.always_keeps:
        return True
    return bool(compaction_due) and key in profile.compaction_keys


# ---- focus mode -------------------------------------------------------------

FOCUS_MODES = ("babysit", "merge")
# Advisories outside FOCUS_ADVISORY_KEYS are held and released as one digest at most this often.
FOCUS_BATCH_MIN = 30
# A focus older than this ends on its own (`why: expired`); re-issuing the verb renews it.
FOCUS_MAX_HOURS = 24
# The merged/closed read is cached this long per session.
FOCUS_PR_TTL_S = 180
# Advisories released in full on every focused stop: they are about the PR or owed to someone else. `focus-pr-unreadable` (the merged/closed read went blind) is added to the plan's list: holding the one note that says focus may never end on its own would defeat it.
FOCUS_ADVISORY_KEYS = frozenset(
    {"ci-queue", "ci-report", "unread-reports", "ladder", "focus-ended", "focus-pr-unreadable"}
)
# A spawn declares babysit/merge fix work with `focus-fix:#<item-id>`.
FOCUS_FIX_RE = re.compile(r"\bfocus-fix:#?([0-9a-f]{6,})\b")


def advisory_kept(key):
    """True when an advisory queue key is released in full on every focused stop (its base, before any `:<subject>`, is in FOCUS_ADVISORY_KEYS)."""
    return str(key).split(":", 1)[0] in FOCUS_ADVISORY_KEYS


def active_focus(focus_map, owned):
    """The newest focus event over every owner key `owned(key)` accepts, or None when there is none or it is `off`.

    `focus_map` is `Fold.focus` ({owner8: event}); `owned` is `lambda o: C.owned_by_me(o, session_id)`, so a proven lineage edge carries focus across compaction. An event without an owner never applies (the fold drops it too): `owned_by_me(None, ...)` is True, and an untagged focus would bind every session.
    """
    best = None
    for owner, ev in (focus_map or {}).items():
        if not owner or not isinstance(ev, dict) or not owned(owner):
            continue
        if best is None or (str(ev.get("at") or ""), int(ev.get("ns") or 0)) >= (
            str(best.get("at") or ""),
            int(best.get("ns") or 0),
        ):
            best = ev
    if best is None or best.get("mode") not in FOCUS_MODES:
        return None
    return best


def pr_token(focus):
    """`pr:<n>` for the focus's PR, or "" while the PR is not known yet."""
    pr = (focus or {}).get("pr")
    return "pr:%s" % pr if pr not in (None, "", 0) else ""


def pr_linked(text, focus):
    """True when an item's text carries the focus PR's `pr:<n>` token (as a whole token: pr:54 is not pr:543)."""
    tok = pr_token(focus)
    if not tok:
        return False
    if isinstance(text, dict):
        text = text.get("text") or text.get("line") or ""
    return re.search(r"(?<![\w:])%s(?![0-9])" % re.escape(tok), str(text or "")) is not None


def _parse(stamp):
    try:
        dt = datetime.datetime.fromisoformat(str(stamp))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=datetime.UTC)


def age_hours(focus, now=None):
    """Hours since the focus event was written, or None when its stamp does not parse."""
    at = _parse((focus or {}).get("at") or "")
    if at is None:
        return None
    now = now or datetime.datetime.now(datetime.UTC)
    return (now - at).total_seconds() / 3600.0


def expired(focus, now=None):
    """True when the focus is older than FOCUS_MAX_HOURS."""
    h = age_hours(focus, now)
    return h is not None and h >= FOCUS_MAX_HOURS


def batch_due(sd, now=None):
    """True when the held advisories are due as one digest: the last release is FOCUS_BATCH_MIN old. The hook seeds `batch_at` when focus starts, so an unseeded doc holds rather than releasing everything on the first stop."""
    at = _parse((sd or {}).get("batch_at") or "")
    if at is None:
        return False
    now = now or datetime.datetime.now(datetime.UTC)
    return (now - at).total_seconds() >= FOCUS_BATCH_MIN * 60
