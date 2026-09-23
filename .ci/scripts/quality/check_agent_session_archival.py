#!/usr/bin/env python3
"""check:ci-agent-session-archival -- an idle session directory leaves agent/ for agent/archive/.

Logic is in `rediacc_ci.quality.agent_session_archival`, which pytest and this file's `--selftest` import directly. The reasoning for the three clocks, the grace period and the deliberate absence of a baseline is in that module's docstring and is not repeated here.

WHAT THIS GATE ADDS TO WHAT ALREADY EXISTED. The Stop hook has computed this every stop, for free, since the per-session split: `wl_checks` calls `wl_store.agent_peer_sections` then `wl_store.agent_state_dead` and prints an ABANDONED label beside each peer. Its own comment says outright that the label is NOT "reap-eligible any more: nothing prunes another session's directory,
so a label promising that would be a check that cannot fire." That is exactly right for a hook -- a hook must never move a peer's document as a side effect -- and it leaves the debt with nobody. This gate is the half that can be responsible: it never writes, it only reds, and the remedy is a verb a human runs by name.

THE ORACLE IS WHOSE. `wl_store.agent_state_dead` is the ONE liveness judge in this repository and this gate calls it exactly as written, deriving it through `paths.hooks_stop_dir` + `paths.on_sys_path` the way `check_tree_shape.py` derives `AGENT_RESERVED_DIRS`. Two arguments a CI runner cannot fill from live event context are PINNED, and both pins are decisions:

    session_id=""     `wl_core.same_session` returns `bool(a) and bool(b) and ...`,
                      so an empty caller id matches no owner. Every section in the
                      tree is judged uniformly; none is exempted as "the caller's
                      own". The gate has no session of its own to exempt.
    projects_dir=""   A CI runner's home has no `~/.claude/projects/<slug>/`, so
                      `owner_age_hours` returns None and the oracle falls back to
                      the section's own heading stamp: on disk, tracked, and the
                      same answer on a laptop and on a runner. It is also the
                      right QUESTION for archival -- has anyone touched this
                      directory recently, independent of whether a transcript for
                      it happens to live on this particular disk.

THE VERBS.

    --check    (the default) the verdict
    --status   every session directory, its age and its verdict, with no verdict
               of its own
    --move S   git mv agent/S into agent/archive/<label>/S, leaving NOTHING behind
    --selftest the controls, and nothing else

`--check` NEVER WRITES, under any argument, and it is wired into `.ci/` only -- never under `.claude/hooks/`. `--move` is the one verb that touches the tree and a human names its target. That separation is the hard constraint the per-session STATE.md split exists to defend: no session may destroy another's document by naming its path, so nothing automatic may move a peer's
directory.

WHY `--move` LEAVES NO STUB, which looks like an omission and is the opposite. `agent_peer_sections` reads `<dir>/STATE.md` literally, and `agent_state_parse` "NEVER RAISES, and never discards": any file of that name with no `## SESSION` heading is adopted as a `legacy` section stamped at the file's own mtime. A three-line "Status: moved" stub would therefore be read, the
instant it was written, as a brand-new zero-minutes-old peer -- resurrecting the archived session into the hook's roster and into this gate's own count, on a clock that restarts every time the stub is re-derived. Nothing mechanically resolves an `agent/<session>/` path either (no citation in the tree carries the `<path>:<line>` shape any checker matches), so there is nothing
for a stub to keep resolving. The regression control for this lives in `.claude/rediacc_hooks/tests/test_wl_agent_session_archival.py`.

WHAT A GREEN HERE DOES NOT MEAN. It does not mean the archive is tidy, or that anything in a moved directory was worth keeping: this gate reads directory names and one heading stamp per directory. A session that never wrote a STATE.md is invisible to it, and a section carrying no parseable stamp ages by its FILE's mtime, which on a fresh CI checkout is today -- both are
counted and printed rather than folded into the healthy set.

---- gate ----
step: Agent session archival
needs: none
selftest: true
lane: quality-branch
why: agent/<session>/ directories accumulate for ever. The Stop hook already
     labels which are abandoned and deliberately moves nothing, so without this
     the archival step in agent/README.md holds only by whoever remembers it --
     and it reached 18 unarchived directories, the oldest 43.9 days idle.
---- end gate ----
"""

import pathlib
import sys
import time

import _cipath  # noqa: F401
from rediacc_ci import controls, gitx, paths
from rediacc_ci.controls import plant
from rediacc_ci.quality import agent_session_archival as ASA

CONTROL_FLOOR = 26

#: How many findings are printed before the rest become a count.
SHOWN = 20


class CannotRunError(RuntimeError):
    """The instrument is missing, which is never a verdict about the tree."""


# --------------------------------------------------------------------------- The fixture the controls plant into.

#: A fixed clock. Every fixture row below is an age relative to it, so no control
#: depends on when the suite runs -- which is the one thing a gate about elapsed
#: time must not do.
NOW = 1_758_500_000.0

GRACE_DAYS = 14.0
DEAD_HOURS = 24.0

#: `<name> <idle-hours> <live|dead>`, one session per line. TEXT rather than a
#: list of records so every mutation below goes through `plant()` and cannot
#: silently no-op: a control fed the CLEAN fixture reports a pass for an
#: assertion it never made, which is the whole reason that helper raises.
#:
#: The three rows are the three cases the grace period has to tell apart: a live
#: session, an abandoned one past the grace, and an abandoned one still inside it.
CLEAN_ROSTER = "live0001 0.5 live\nabandon1 400 dead\nrecent01 100 dead\n"

#: The reserved names, MIRRORED here for the controls only. The real refusal reads
#: `wl_store.AGENT_RESERVED_DIRS` at run time; this copy exists so a control can run
#: in a checkout with no `.claude/`, and `test_quality_agent_session_archival.py`
#: compares the two in both directions. A mirror nobody compares is a second set.
RESERVED_MIRROR = frozenset(
    {"archive", "programs", "worklist", "reggate", "plans", "ledgers", "pr", "legacy"}
)


def _roster(text: str) -> list[ASA.Session]:
    """`Session` records from the fixture TEXT above, aged against `NOW`."""
    out = []
    for line in text.splitlines():
        if not line.strip():
            continue
        name, hours, verdict = line.split()
        out.append(
            ASA.Session(
                name=name,
                ts=NOW - float(hours) * ASA.SECONDS_PER_HOUR,
                dead=verdict == "dead",
            )
        )
    return out


def _named(found: list[ASA.Finding]) -> set[str]:
    """The session names a finding list accuses, which is what a control asserts.

    The CODES alone would be a weaker claim than this gate can make: there is one code, so a set of codes cannot tell "fired on the right directory" from "fired on all of them".
    """
    return {f.message.split("/")[1] for f in found}


def _fire(text: str, *, grace_days: float = GRACE_DAYS) -> set[str]:
    return _named(
        ASA.findings(_roster(text), grace_days=grace_days, dead_hours=DEAD_HOURS, now=NOW)
    )


def selftest() -> int:
    """Every rail, planted and mirrored. The mirror is half the control.

    A control that only proves the red case cannot tell a detector apart from a function that returns a finding unconditionally, so each plant below is paired with the clean fixture it was built from -- and the grace period is driven from BOTH sides of its boundary, because a threshold tested on one side is a threshold whose direction is a guess.
    """
    tally = controls.Controls("agent session archival", floor=CONTROL_FLOOR)

    # S1, against the clean roster: exactly the one abandoned session past the grace.
    tally.check("S1 clean roster accuses only the overdue dir", _fire(CLEAN_ROSTER), {"abandon1"})

    # The grace boundary, from both sides, planted into the AGE rather than the verdict.
    threshold = ASA.due_after_hours(GRACE_DAYS, DEAD_HOURS)
    tally.check("the threshold is the horizon plus the grace", threshold, 360.0)
    at_boundary = plant(CLEAN_ROSTER, "recent01 100 dead", "recent01 360 dead")
    tally.check("S1 fires exactly AT the boundary", _fire(at_boundary), {"abandon1", "recent01"})
    just_under = plant(CLEAN_ROSTER, "recent01 100 dead", "recent01 359.9 dead")
    tally.check("S1 spares a directory one tenth of an hour short", _fire(just_under), {"abandon1"})
    just_over = plant(CLEAN_ROSTER, "recent01 100 dead", "recent01 360.1 dead")
    tally.check("S1 fires one tenth of an hour past it", _fire(just_over), {"abandon1", "recent01"})

    # The oracle's verdict is load-bearing: age alone must never retire a directory.
    ancient_live = plant(CLEAN_ROSTER, "live0001 0.5 live", "live0001 9000 live")
    tally.check("a LIVE session is spared at any age", _fire(ancient_live), {"abandon1"})
    ancient_dead = plant(ancient_live, "live0001 9000 live", "live0001 9000 dead")
    tally.check(
        "the same age with the oracle's verdict flipped DOES fire",
        _fire(ancient_dead),
        {"abandon1", "live0001"},
    )

    # An already-archived directory is absent from the enumeration, so nothing accuses it.
    archived = plant(CLEAN_ROSTER, "abandon1 400 dead\n", "")
    tally.check("a directory already moved produces no finding", _fire(archived), set())

    # The grace period is data, so a control drives it as data.
    tally.check(
        "a wider grace spares what the default accuses", _fire(CLEAN_ROSTER, grace_days=30), set()
    )
    tally.check(
        "a narrower grace accuses what the default spares",
        _fire(CLEAN_ROSTER, grace_days=3),
        {"abandon1", "recent01"},
    )

    # The message has to be actionable, not a count.
    only = ASA.findings(
        _roster(CLEAN_ROSTER), grace_days=GRACE_DAYS, dead_hours=DEAD_HOURS, now=NOW
    )
    tally.check("one finding for one overdue directory", len(only), 1)
    tally.truthy("the finding names the verb that fixes it", "--move abandon1" in only[0].message)
    tally.truthy("the finding names the age in days", "16.7 days" in only[0].message)

    # Ordering, because a reader fixes the oldest first.
    both = ASA.classify_due(
        _roster(at_boundary), grace_days=GRACE_DAYS, dead_hours=DEAD_HOURS, now=NOW
    )
    tally.check(
        "the overdue list is oldest first", [s.name for s in both], ["abandon1", "recent01"]
    )

    # Ages. The clamp is not decoration: two machines writing one tree have skewed clocks.
    future = ASA.Session(name="skewed", ts=NOW + 10_000, dead=True)
    tally.check("a future stamp reads as zero, never negative", ASA.idle_hours(future, NOW), 0.0)
    tally.check(
        "idle_days is idle_hours over 24",
        round(ASA.idle_days(_roster(CLEAN_ROSTER)[1], NOW), 3),
        round(400 / 24, 3),
    )

    # The vacuity floor, both directions.
    clean_sessions = _roster(CLEAN_ROSTER)
    tally.check(
        "a real roster with an archive present is not vacuous",
        ASA.vacuity_reason(clean_sessions, archive_exists=True),
        "",
    )
    tally.truthy(
        "an empty enumeration REFUSES rather than passing",
        ASA.vacuity_reason([], archive_exists=True),
    )
    tally.truthy(
        "a missing agent/archive/ REFUSES rather than passing",
        ASA.vacuity_reason(clean_sessions, archive_exists=False),
    )

    # Labels.
    tally.check("a branch name is its own label", ASA.label_for("0914-1"), "0914-1")
    tally.check("a slash is slugged, never nested", ASA.label_for("feature/thing"), "feature-thing")
    tally.check("a detached HEAD yields no label at all", ASA.label_for(""), "")
    tally.check(
        "a label is one component", ASA.archive_rel("L", "abcd1234"), "agent/archive/L/abcd1234"
    )

    # --move's rails, each refused for its own reason and each mirrored by a pass.
    def refusal(**over: object) -> str:
        args = {
            "session": "abandon1",
            "reserved": RESERVED_MIRROR,
            "exists": True,
            "dead": True,
            "forced": False,
            "dirty": False,
            "target_exists": False,
            "label": "2026-09-22-backfill",
        }
        args.update(over)
        return ASA.move_refusal(**args)  # type: ignore[arg-type]

    tally.check("an abandoned target on a quiet tree is allowed", refusal(), "")
    tally.truthy("a reserved name is refused outright", refusal(session="archive"))
    tally.truthy("every reserved name is refused", all(refusal(session=n) for n in RESERVED_MIRROR))
    tally.truthy("a path, not a name, is refused", refusal(session="a/b"))
    tally.truthy("an unresolvable label is refused", refusal(label=""))
    tally.truthy("a directory that is not there is refused", refusal(exists=False))
    tally.truthy("a dirty directory is refused, because a peer may be writing", refusal(dirty=True))
    tally.truthy("a LIVE target is refused without --force", refusal(dead=False))
    tally.check(
        "the same LIVE target is allowed WITH --force", refusal(dead=False, forced=True), ""
    )
    tally.truthy("an occupied archive path is refused", refusal(target_exists=True))
    tally.truthy(
        "the dirty-tree refusal says a writer may be racing",
        "race a live writer" in refusal(dirty=True),
    )

    return 0 if tally.report() else 1


# --------------------------------------------------------------------------- The tree-reading half.


def _wl_store(root: pathlib.Path):
    """`wl_store`, DERIVED rather than copied.

    A missing `.claude/` is CANNOT RUN rather than a verdict, for `check_tree_shape.py`'s reason: without the hook's own liveness judge there is nothing to ask, and a gate that silently skipped the derivation would report a clean tree while the one thing it exists to check had not happened. `paths.hooks_stop_dir` rather than a join, because that is the ONE place the
    `.claude/hooks/stop` literal lives and the spelling `check:ci-python-gate-deps` recognises as a first-party sys.path hop.
    """
    hooks = paths.hooks_stop_dir(root)
    paths.on_sys_path(hooks)
    try:
        import wl_store  # noqa: PLC0415 -- the derivation is the point; see the docstring
    except ImportError as exc:
        raise CannotRunError(
            "cannot import wl_store from %s (%s), so the ONE liveness oracle cannot be "
            "reached and every verdict below would be invented here instead" % (hooks, exc)
        ) from exc
    return wl_store


def _gather(root: pathlib.Path) -> tuple[list[ASA.Session], int]:
    """Every session directory under `agent/`, judged by the hook's own oracle.

    Returns the sessions and how many directories carried no STATE.md at all. The second number is PRINTED rather than dropped: such a directory is invisible to `agent_peer_sections`, so no finding is able to name it, and a count that vanished would let the roster shrink without anyone noticing.
    """
    store = _wl_store(root)
    sections = store.agent_peer_sections(root, "")
    _kept, reaped = store.agent_state_dead(sections, "", "")
    dead_owners = {s["owner"] for s in reaped}
    sessions = [
        ASA.Session(
            name=str(s["owner"]),
            ts=float(s["ts"]),
            dead=s["owner"] in dead_owners,
            stamped=bool(s.get("stamped", True)),
        )
        for s in sections
    ]
    sessions.sort(key=lambda s: s.ts)
    documented = {s.name for s in sessions}
    silent = len([d for d in store.agent_session_dirs(root) if d.name not in documented])
    return sessions, silent


def _config(root: pathlib.Path) -> float:
    try:
        return float(ASA.load_config(root)["grace_days"])
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise CannotRunError(
            "%s must carry a numeric grace_days (%s). One number, one place: a default "
            "here would be a second definition of the retention." % (ASA.DEFAULT_CONFIG_REL, exc)
        ) from exc


def _refuse_vacuity(root: pathlib.Path, sessions: list[ASA.Session]) -> None:
    why = ASA.vacuity_reason(sessions, archive_exists=(root / ASA.ARCHIVE_DIR).is_dir())
    if why:
        raise CannotRunError(why)


def _archive_labels(root: pathlib.Path) -> int:
    try:
        return len([p for p in (root / ASA.ARCHIVE_DIR).iterdir() if p.is_dir()])
    except OSError:
        return 0


def run(root: pathlib.Path, grace_days: float) -> int:
    sessions, silent = _gather(root)
    _refuse_vacuity(root, sessions)
    now = time.time()
    hours = ASA.dead_hours()
    found = ASA.findings(sessions, grace_days=grace_days, dead_hours=hours, now=now)
    if found:
        print(
            "✗ agent session archival: %d director(ies) overdue, of %d enumerated"
            % (len(found), len(sessions)),
            file=sys.stderr,
        )
        for finding in found[:SHOWN]:
            print("  %s %s" % (finding.code, finding.message), file=sys.stderr)
        if len(found) > SHOWN:
            print("  ...and %d more" % (len(found) - SHOWN), file=sys.stderr)
        print(
            "  Archiving is not destructive: the whole directory is renamed under "
            "%s/<label>/ and its history follows. Do not suppress this; move the "
            "directory." % ASA.ARCHIVE_DIR,
            file=sys.stderr,
        )
        return 1
    abandoned = len([s for s in sessions if s.dead])
    unstamped = len([s for s in sessions if not s.stamped])
    print(
        "✓ agent session archival: %d session director(ies) under %s/, %d abandoned and "
        "none past the %.0f-day grace, %d archive label(s) already in %s/"
        % (
            len(sessions),
            ASA.AGENT_DIR,
            abandoned,
            grace_days,
            _archive_labels(root),
            ASA.ARCHIVE_DIR,
        )
    )
    print(
        "  Blind spot: %d director(ies) carry no STATE.md and are invisible to the oracle; "
        "%d section(s) carry no heading stamp and age by their file's mtime, which on a "
        "fresh checkout is today." % (silent, unstamped)
    )
    return 0


def status(root: pathlib.Path, grace_days: float) -> int:
    """Every session directory, its age and its verdict. No verdict of its own.

    Exits 0 whatever it finds, exactly as `check_plan_folders.py --status` does: a reporter that also judged would be a second gate with a different threshold, and the two would disagree the first time one was retuned.
    """
    sessions, silent = _gather(root)
    _refuse_vacuity(root, sessions)
    now = time.time()
    hours = ASA.dead_hours()
    due = {
        s.name for s in ASA.classify_due(sessions, grace_days=grace_days, dead_hours=hours, now=now)
    }
    for session in sessions:
        print(
            "%-10s %7.1f days  %-9s %-8s %s"
            % (
                session.name,
                ASA.idle_days(session, now),
                "abandoned" if session.dead else "live",
                "OVERDUE" if session.name in due else "",
                ASA.stamp_text(session.ts) + ("" if session.stamped else "  (unstamped: mtime)"),
            )
        )
    print(
        "%d session(s), %d abandoned, %d overdue past the %.0f-day grace, %d with no STATE.md"
        % (len(sessions), len([s for s in sessions if s.dead]), len(due), grace_days, silent)
    )
    return 0


def move(root: pathlib.Path, session: str, *, label: str, forced: bool) -> int:
    """`git mv agent/<session>` under `agent/archive/<label>/`, leaving NOTHING behind.

    Whole-directory rename, so git detects it and the full history follows. No stub at the old path, deliberately: see this file's header, where the resurrection that a stub causes is spelled out.
    """
    print(ASA.PROMOTION_REMINDER)
    store = _wl_store(root)
    sessions, _silent = _gather(root)
    by_name = {s.name: s for s in sessions}
    rel = ASA.session_rel(session)
    dirty = gitx.git(["status", "--porcelain", "--", rel], root=root)
    if not dirty.ok:
        print(
            "✗ git status failed for %s: %s. Refusing to move a directory whose tree state "
            "is unknown." % (rel, dirty.stderr.strip() or "no stderr"),
            file=sys.stderr,
        )
        return 1
    # A directory with no STATE.md is absent from the roster entirely. Treated as NOT dead, so it takes the `--force` door rather than being swept silently: the oracle has said nothing about it, and "no evidence of life" is not "evidence of death".
    known = by_name.get(session)
    why = ASA.move_refusal(
        session,
        reserved=frozenset(store.AGENT_RESERVED_DIRS),
        exists=(root / rel).is_dir(),
        dead=bool(known and known.dead),
        forced=forced,
        dirty=bool(dirty.stdout.strip()),
        target_exists=(root / ASA.archive_rel(label, session)).exists(),
        label=label,
    )
    if why:
        print("✗ %s" % why, file=sys.stderr)
        return 1
    new_rel = ASA.archive_rel(label, session)
    (root / new_rel).parent.mkdir(parents=True, exist_ok=True)
    result = gitx.git(["mv", "--", rel, new_rel], root=root)
    if not result.ok:
        print(
            "✗ git mv %s -> %s failed: %s" % (rel, new_rel, result.stderr.strip()), file=sys.stderr
        )
        return 1
    if (root / rel).exists():
        print(
            "✗ %s still exists after the move. A same-named leftover is read by "
            "agent_peer_sections as a brand-new peer, which is the resurrection this "
            "verb exists to avoid." % rel,
            file=sys.stderr,
        )
        return 1
    print("✓ %s -> %s" % (rel, new_rel))
    return 0


def main(argv: list[str]) -> int:
    try:
        if "--selftest" in argv:
            return selftest()

        refused = controls.controls_first("agent session archival", selftest)
        if refused:
            return refused

        root = ASA.repo_root()
        if not gitx.is_work_tree(root):
            raise CannotRunError(
                "%s is not a git work tree, so no session directory can be enumerated" % root
            )
        grace_days = _config(root)

        if "--status" in argv:
            return status(root, grace_days)
        if "--move" in argv:
            i = argv.index("--move")
            target = argv[i + 1] if len(argv) > i + 1 else ""
            if not target or target.startswith("-"):
                print("✗ --move needs a session directory name", file=sys.stderr)
                return 2
            if "--label" in argv:
                j = argv.index("--label")
                label = ASA.sanitise_label(argv[j + 1] if len(argv) > j + 1 else "")
            else:
                label = ASA.label_for(_wl_store(root).C.git_branch(root))
            return move(root, target, label=label, forced="--force" in argv)
        return run(root, grace_days)
    except CannotRunError as exc:
        print("⚠ CANNOT RUN (exit 77, which is not a verdict): %s" % exc, file=sys.stderr)
        return 77


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
