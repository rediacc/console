"""When a session's working directory leaves `agent/`, and where it goes. The library half of `check:ci-agent-session-archival`.

WHY THIS EXISTS. `agent/<session-prefix>/` holds one session's STATE.md, and the Stop hook already computes which of those directories are ABANDONED on every stop -- `wl_checks` calls `wl_store.agent_peer_sections` then `wl_store.agent_state_dead` and LABELS the result. Nothing ever moved anything, so the label accumulated: 19 peer directories, 18 of them abandoned, the
oldest 43.9 days idle, against an `agent/archive/` whose last real entry was five weeks old. `agent/README.md` describes the manual move and nobody ran it.

THE ORACLE IS REUSED, NEVER REINVENTED. `wl_store.agent_state_dead` is the ONE liveness judge in this repository and nothing here re-implements it. This module takes its verdict as DATA -- a `Session` record per directory, carrying the owner, the last-touch stamp and the oracle's own kept/reaped answer -- and asks the one question the oracle does not: has enough time passed on
top of abandonment that leaving the directory in place is now somebody's responsibility.

THREE CLOCKS, AND ONLY THE THIRD IS NEW.

  * `WORKLIST_DEAD_HOURS` (24) is the hook's abandonment horizon, read here
    rather than redefined, so a session judged live by the hook is never a
    finding here either.
  * A section's own `ts`, the heading stamp inside STATE.md, is the last-touch
    clock. On disk, tracked, and reproducible on a CI runner that has no
    `~/.claude/projects/` of its own -- which is exactly why the entry point
    pins `projects_dir=""` and takes this fallback deliberately rather than by
    accident.
  * `grace_days` (14), the retention this module adds, read from
    `.ci/config/agent-session-archival.json`. A directory is a finding only once
    it is ABANDONED **and** `grace_days` have passed on top: roughly 15 days
    idle in total.

WHY THE GRACE PERIOD RATHER THAN THE 24-HOUR HORIZON. A gate that red on "any abandoned directory is unarchived" reds on 18 directories today, on every unrelated PR, blaming whoever's branch runs CI next for eighteen other sessions going idle. That is a fact about the passage of time, not about a diff, and it is the exact shape that gets suppressed within a day. The backlog is
migrated as the implementing plan's own step and the gate lands already fatal, never advisory-then-flipped. The grace period is what stops the 18-red-forever problem coming back: long enough that ordinary session cadence clears the debt, short enough to still create pressure.

NO SHRINK-ONLY BASELINE, and the omission is a decision. A baseline is for debt that needs per-file judgment. The fix here is one `git mv` per directory, always safe and never partial, so there is no progress state worth freezing -- a baseline would only be a place to park the work.

THE PURE CORE IS PURE ON PURPOSE. Every function below takes data and returns data: no git, no filesystem, no clock, no `wl_store`. That is what lets the gate's controls PLANT a defect into a fixture record and assert the finding appears, instead of staging nineteen session directories per control.
"""

import dataclasses
import json
import os
import pathlib
import re

from rediacc_ci import paths

# --------------------------------------------------------------------------- The layout, in one place.

AGENT_DIR = "agent"
ARCHIVE_DIR = "agent/archive"

DEFAULT_CONFIG_REL = ".ci/config/agent-session-archival.json"

#: The hook's own abandonment horizon, read from the SAME environment variable
#: `wl_store.agent_state_dead` reads. Spelled here so the gate's arithmetic and
#: the oracle's verdict cannot disagree about what "abandoned" means; a second
#: default would be a second definition of the horizon.
DEAD_HOURS_ENV = "WORKLIST_DEAD_HOURS"
DEFAULT_DEAD_HOURS = 24.0

ROOT_ENV = "AGENT_SESSION_ARCHIVAL_ROOT"

#: The floor under the enumeration. Zero session directories is CANNOT RUN, never
#: a green: a tree that thin has no `.claude/hooks/stop` to derive the oracle
#: from either, so a pass would be a claim about a tree the gate never saw.
MIN_SESSIONS = 1

#: What a label may contain. A label becomes a directory component under
#: `agent/archive/`, so a slash would nest one level deeper than every reader
#: expects and a leading dot would hide the whole archive from an ordinary
#: listing. Anchored, and the sanitiser below is the only way a label is built.
LABEL_OK_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

SECONDS_PER_DAY = 86400.0
SECONDS_PER_HOUR = 3600.0


@dataclasses.dataclass(frozen=True)
class Session:
    """One `agent/<session>/` directory, as the oracle already judged it.

    `dead` is CARRIED rather than recomputed. It is `wl_store.agent_state_dead`'s own answer, and the moment this module derived it from `ts` instead there would be two liveness judges in the repository disagreeing in the cases that matter.

    `stamped` is False when the section carried no parseable heading stamp, in which case `ts` fell back to the FILE's mtime. That is a fresh-checkout clock on a CI runner, so such a section ages past nothing at all there; it is counted and printed rather than silently folded into the healthy set.
    """

    name: str
    ts: float
    dead: bool
    stamped: bool = True


@dataclasses.dataclass(frozen=True)
class Finding:
    code: str
    message: str


# --------------------------------------------------------------------------- The judgment. Data in, data out.


def idle_hours(session: Session, now: float) -> float:
    """Hours since the session's directory was last touched. Never negative.

    Clamped at zero because a stamp in the future (a clock skew between two machines writing one tree, which this repository really does have) would otherwise read as a NEGATIVE age and sort ahead of everything, making the oldest directory look like the youngest.
    """
    return max(0.0, (now - session.ts) / SECONDS_PER_HOUR)


def idle_days(session: Session, now: float) -> float:
    return idle_hours(session, now) / 24.0


def due_after_hours(grace_days: float, dead_hours: float) -> float:
    """The total idle time at which a directory becomes somebody's responsibility.

    Abandonment PLUS the grace, not the grace alone: the two clocks are stacked deliberately so the number a reader sees in the config (14) is the extra time bought on top of the horizon the hook already applies, rather than a third horizon competing with it.
    """
    return float(dead_hours) + float(grace_days) * 24.0


def classify_due(
    sessions: list[Session], *, grace_days: float, dead_hours: float, now: float
) -> list[Session]:
    """Every session whose directory is overdue for archival, oldest first.

    BOTH halves are required and neither implies the other here. `dead` is the oracle's verdict and is the only thing that can retire a directory at all; the age comparison is this module's grace period on top. Keeping them separate is what lets `--force` exist for a live directory without that path silently widening the gate.
    """
    threshold = due_after_hours(grace_days, dead_hours)
    due = [s for s in sessions if s.dead and idle_hours(s, now) >= threshold]
    return sorted(due, key=lambda s: s.ts)


def finding_s1(
    sessions: list[Session], *, grace_days: float, dead_hours: float, now: float
) -> list[Finding]:
    """S1: an abandoned session directory that has outlived the grace period.

    NOT DIFF-SCOPED, and that is deliberate. Whether a directory is overdue is a property of the tree and of the calendar; scoping it to the diff would mean the finding appears only for whoever happens to touch `agent/` next, which is the same accident of timing the grace period exists to remove.
    """
    return [
        Finding(
            "S1",
            "%s/%s/ has been idle %.1f days (last touch %s); archive it: "
            "`.ci/scripts/quality/check_agent_session_archival.py --move %s`"
            % (AGENT_DIR, s.name, idle_days(s, now), stamp_text(s.ts), s.name),
        )
        for s in classify_due(sessions, grace_days=grace_days, dead_hours=dead_hours, now=now)
    ]


def findings(
    sessions: list[Session], *, grace_days: float, dead_hours: float, now: float
) -> list[Finding]:
    """Every finding, in one call. One code today; the shape is the family's."""
    return finding_s1(sessions, grace_days=grace_days, dead_hours=dead_hours, now=now)


def vacuity_reason(
    sessions: list[Session], *, archive_exists: bool, floor: int = MIN_SESSIONS
) -> str:
    """ "" when the gate really looked at a tree, else WHY its verdict would mean nothing.

    Returned as a REASON rather than a finding because neither case is a fact about the tree's hygiene: an enumeration that found no session directory, or an `agent/archive/` that does not exist, both say the instrument is pointed somewhere else. The caller raises CannotRunError on a non-empty return, exactly as `check_tree_shape.py` refuses a missing `.claude/`.
    """
    if not archive_exists:
        return (
            "%s/ does not exist, so there is nowhere to archive a session to and a green "
            "here would only mean the gate never looked" % ARCHIVE_DIR
        )
    if len(sessions) < floor:
        return (
            "%d session director(ies) enumerated under %s/, below the floor of %d: the gate "
            "is not seeing the tree, so its green would mean nothing"
            % (len(sessions), AGENT_DIR, floor)
        )
    return ""


# --------------------------------------------------------------------------- Labels and paths.


def sanitise_label(raw: str) -> str:
    """A label reduced to something that is safely ONE directory component, or "".

    A branch name is free text: it carries slashes (`feature/x`), and this repository's own branches are `0914-1`-shaped. Slugging rather than rejecting, because the caller's fallback for "" is to refuse the move, and a detached HEAD -- which an interactive rebase produces every time -- has no branch at all.
    """
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", str(raw or "")).strip("-.")
    return slug if LABEL_OK_RE.match(slug) else ""


def label_for(branch: str) -> str:
    """The archive label a branch implies. "" when the branch cannot be resolved.

    `agent/README.md` gives latitude here ("whatever names that work best -- historically a branch name"), and the precedent already in the tree is branch-shaped: `agent/archive/0815-1/97604f47/`. An explicit `--label` overrides it, which is what a bulk migration spanning five weeks and several branches needs.
    """
    return sanitise_label(branch)


def archive_rel(label: str, session: str) -> str:
    """`agent/archive/<label>/<session>` -- the ONE spelling of the destination.

    Shared by the mover and by every message that names where a directory went, so a refusal cannot describe a path the move would not have used.
    """
    return "%s/%s/%s" % (ARCHIVE_DIR, label, session)


def session_rel(session: str) -> str:
    return "%s/%s" % (AGENT_DIR, session)


def stamp_text(ts: float) -> str:
    """An ISO-8601 Z stamp, matching the heading format the sections carry."""
    import datetime as dt  # noqa: PLC0415 -- one formatting call; the module stays clock-free at import

    return dt.datetime.fromtimestamp(float(ts), dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


# --------------------------------------------------------------------------- The refusals `--move` owes its caller.


def move_refusal(
    session: str,
    *,
    reserved: frozenset[str] | set[str],
    exists: bool,
    dead: bool,
    forced: bool,
    dirty: bool,
    target_exists: bool,
    label: str,
) -> str:
    """ "" when the move may proceed, else the sentence explaining why it may not.

    PURE, so every rail below is provable from a fixture instead of from a staged git tree; the entry point does nothing but gather these six facts and print what comes back. Order is load-bearing rather than tidy: a reserved name is refused before anything reads the filesystem, because `agent/archive` is itself a name a careless `--move archive` would otherwise walk into.
    """
    if session in reserved:
        return (
            "%r is a reserved directory under %s/, not a session. Moving it would take the "
            "archive, the worklist or the plans tree with it." % (session, AGENT_DIR)
        )
    if not session or "/" in session or session.startswith("."):
        return "%r is not a session directory name" % (session,)
    if not label:
        return (
            "no archive label: pass --label <name>, because the branch could not be resolved "
            "(a detached HEAD has none) and an unlabelled archive path would be "
            "%s//%s" % (ARCHIVE_DIR, session)
        )
    if not exists:
        return "%s does not exist" % session_rel(session)
    if dirty:
        return (
            "%s carries uncommitted changes, so another session may be writing in it right "
            "now. Moving it would race a live writer; re-run once the tree is quiet."
            % session_rel(session)
        )
    if not dead and not forced:
        return (
            "%s is still LIVE by the same oracle the Stop hook uses, so it is not abandoned. "
            "Pass --force to archive it anyway (which is how a session archives itself on "
            "the day it finishes)." % session_rel(session)
        )
    if target_exists:
        return (
            "%s already exists; pick another --label rather than merging two sessions' "
            "directories into one" % archive_rel(label, session)
        )
    return ""


#: Printed by `--move` before it acts, and never enforced. `agent/README.md`'s archival step also says to promote anything in RULES.md that turned out to be true of the REPO into TRAPS.md -- a judgment about a document every session sharpens in place, not a property of the directory being moved, and nothing can verify it mechanically. An advisory nudge is the honest shape; a gate
#: over it would be a check that cannot fire.
PROMOTION_REMINDER = (
    "Before archiving: promote anything in agent/RULES.md that turned out to be true of the "
    "REPO into docs/agent-reference/TRAPS.md. This is a reminder, not a gate."
)


# --------------------------------------------------------------------------- The impure edge, kept to two functions.


def repo_root() -> pathlib.Path:
    override = os.environ.get(ROOT_ENV)
    return pathlib.Path(override) if override else paths.repo_root()


def dead_hours(env: dict[str, str] | None = None) -> float:
    """The hook's abandonment horizon, from the hook's own environment variable.

    Read here and passed down rather than looked up inside the judgment, so a control can drive the boundary from both sides without touching `os.environ` and leaking the change into whatever runs next in the same process.
    """
    raw = (env if env is not None else os.environ).get(DEAD_HOURS_ENV, "")
    try:
        return float(raw) if raw else DEFAULT_DEAD_HOURS
    except ValueError:
        return DEFAULT_DEAD_HOURS


def load_config(root: pathlib.Path) -> dict:
    """`agent-session-archival.json`, with `grace_days` required.

    No default for `grace_days` here. A default would put the retention in two places, and the one that a reader edits would be the one that is not consulted.
    """
    return json.loads((root / DEFAULT_CONFIG_REL).read_text(encoding="utf-8"))
