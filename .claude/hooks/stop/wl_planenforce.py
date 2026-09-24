"""wl_planenforce: the blocking half of "implement the plans", bounded by a descending ceiling so the exit is arithmetic rather than a hope.

WHY THIS EXISTS. The operator's ask, paraphrased because the verbatim wording carries a first-person pronoun the house style keeps out of prose: the repo plans and does not implement, and the stated aim is to eliminate 'planned but not implemented'.
Offered three narrower scopes -- per-PR-diff, per-branch, per-plan-adoption -- after seeing a census of 27 plans, 299 open boxes and five owners across a 654-commit branch, the answer was ALL. That ruling is not re-narrowed here. What it earns is a CLOCK, not an exemption. Full design: agent/plans/PLAN-plan-implementation-enforcement.md.

THE BOUNDARY AGAINST THE THREE NEIGHBOURS, drawn before anything was written, because the eighth mechanism in this area becomes a duplicate of one of the other seven unless it is:

  * `wl_planfile.plan_rows` asks whether a plan's boxes are TRACKED. This asks
    whether they are DONE. Neither implies the other: a plan can have a worklist
    item per box and none of them finished.
  * `wl_backlog.next_plan` is the ADVISORY half of exactly this ask and stays
    advisory. It is not edited, not promoted, and its never-blocks control must
    keep passing unchanged. What is reused from it, by import rather than by
    re-derivation, is `_open_boxes` (the shared census, so this is never a third
    scan of the corpus) and `_dead_peer` (peer liveness, so this never invents a
    second liveness oracle).
  * the existing `plan-adopted` vadd fires only on the ADOPTION MARKER, one
    plan at a time. This is that scope widened from "adopted" to "all", which is
    what the operator asked for; the call-site comment beside `plan-adopted`
    states the old boundary and names the wedge it was protecting against, and
    the ceiling below is the answer to that wedge rather than a denial of it.

WHY A CEILING AND NOT A CLIFF, and why the difference is the whole safety argument. Three repeated-nag incidents are already on record in this hook -- PLAN-fix-stop-hook-completion-evidence-refire.md, PLAN-stop-hook-refactor-enforcement.md and PLAN-sweep-obligation-carry-forward.md -- and every one of them blocked with NO REACHABLE EXIT.
A gate that reds on the mere existence of an open box would be the fourth, on the day it landed, over a standing backlog this session did not create.
So the block is silent whenever the corpus is at or under the day's ceiling, the ceiling descends by a fixed number of boxes per day from a baseline written at landing, and the block's own text prints the exact number of boxes that ends it. The exit is arithmetic and it is reachable by real work.

NO FIRE CAP, deliberately, and it is the one place this departs from the sibling advisories. `wl_rules.Demand` gives every other latch a TTL and a max-fires; a T_MISSION block must not have one, because a mission that goes quiet after two asks is not a mission. The bound comes from the ceiling instead. A cap is what an unreachable exit needs; a reachable exit does not need one.

NOTHING HERE IS JUDGED. Ordering, ownership, counting and the ceiling are arithmetic over file metadata, a committed config file and the worklist event stream. There is no score, no threshold and no model call anywhere in this module, which is the line `wl_claimcheck`'s measurements drew and this design inherits.

`recs` and `plan_owner` are passed in rather than imported, matching `wl_planfile.plan_rows` and `wl_backlog.next_plan`: this module must never import `wl_checks`, which imports it, and the injection is what lets the controls drive it on fixtures instead of a real `agent/` tree.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import json
import pathlib

import wl_backlog as BL
import wl_core as C
import wl_planfile as F
import wl_planrec as R
import wl_store as S

#: The clock, committed, read by BOTH halves. `.ci/scripts/quality/check_plan_implementation.py` reads this same file through this same loader, which is what makes the CI gate and the Stop hook incapable of disagreeing about the number. plan-lifecycle.json's own $comment states the rule being obeyed: duplicating a number into two scripts is exactly what creates a deadlock.
CONFIG_REL = ".ci/config/plan-implementation.json"

#: The keys, and the SAME dict is what C10 pins across the two halves. A default here is a FALLBACK FOR A MISSING FILE, never a silent substitute for a malformed one: `load_clock` reports which of the two happened, and a caller that cannot read the config renders a diagnostic rather than a verdict.
CLOCK_KEYS = ("baseline_open", "baseline_at", "drain_per_day", "warn_slack", "floor_open")

#: What the gate falls back to when the config is absent entirely. Chosen so an absent config cannot ACCUSE anybody: `drain_per_day` 0 freezes the ceiling at the baseline, and a baseline of 0 with a floor of 0 would make every tree over ceiling, so the loader reports the absence instead and the caller goes silent. See `load_clock`.
CLOCK_DEFAULTS = {
    "baseline_open": 0,
    "baseline_at": "",
    "drain_per_day": 0,
    "warn_slack": 0,
    "floor_open": 0,
}

#: How many plans are NAMED in the block before the rest are counted. The wall that gets a check switched off is made of quoted lines, not of headers -- wl_planfile's design note 2 measured that -- so the cap is on names and the remainder is always COUNTED rather than dropped.
PLANS_SHOWN = 3

#: Verdict states. `silent` is silent, not quiet-but-present: a clock that talks while it is satisfied is a clock nobody reads.
SILENT, WARN, BLOCK = "silent", "warn", "block"


def _quiet():
    """`contextlib.suppress(Exception)`, named once so the reason is written once: everything this module does is a COURTESY TO THE READER of a block that is already decided, and a peer-liveness read or a header parse must never turn a stop into a crash. Failures degrade the message, never the verdict."""
    return contextlib.suppress(Exception)


def load_clock(root):
    """(clock, problem). `problem` is "" when the file was read and parsed.

    A MISSING CONFIG IS NOT A PASS AND NOT AN ACCUSATION. It is reported to the caller, which goes silent rather than blocking on numbers it does not have: the config is committed beside the gate, so its absence means a broken checkout rather than a session that failed to drain anything, and accusing one for the other is how a gate earns its way into being switched off.
    """
    path = pathlib.Path(root) / CONFIG_REL
    clock = dict(CLOCK_DEFAULTS)
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        return clock, "%s cannot be read (%s)" % (CONFIG_REL, exc)
    try:
        doc = json.loads(raw)
    except ValueError as exc:
        return clock, "%s does not parse (%s)" % (CONFIG_REL, exc)
    if not isinstance(doc, dict):
        return clock, "%s is not a JSON object" % CONFIG_REL
    missing = [k for k in CLOCK_KEYS if k not in doc]
    if missing:
        return clock, "%s is missing %s" % (CONFIG_REL, ", ".join(missing))
    for key in CLOCK_KEYS:
        clock[key] = doc[key]
    return clock, ""


def _days_since(baseline_at, today):
    """Whole days from `baseline_at` to `today`, never negative and never None.

    Never negative because a clock that runs backwards would hand a session slack it did not earn by setting a landing date in the future, and the honest reading of "not yet started" is day 0.
    """
    try:
        start = dt.date.fromisoformat(str(baseline_at or "").strip())
    except ValueError:
        return 0
    return max(0, (today - start).days)


def ceiling(clock, today=None):
    """(ceiling, days_elapsed) for one day. Pure arithmetic, no I/O.

        ceiling(d) = max(floor_open, baseline_open - floor(d * drain_per_day))

    EXPORTED AND PURE so the controls can assert the clock at THREE points -- day 0 silent, day 1 with nothing closed red, day 1 with a day's drainage silent again. A clock asserted at one point is a constant, and a constant that happens to hold today is the exact shape of a check that cannot fail.
    """
    # dt.datetime.now(dt.UTC).date() rather than dt.date.today(): the ceiling is a claim about a DATE, and a machine in a different timezone must not read a different ceiling off the same committed baseline.
    today = today or dt.datetime.now(dt.UTC).date()
    days = _days_since(clock.get("baseline_at"), today)
    base = int(clock.get("baseline_open") or 0)
    rate = int(clock.get("drain_per_day") or 0)
    floor = int(clock.get("floor_open") or 0)
    return max(floor, base - days * rate), days


def scope_rows(root, recs, boxes=None, read_text=None):
    """[row] for every IN-SCOPE plan, newest first, one dict each.

    In scope means: `wl_checks.plan_records` found it, its `Status:` is not in `wl_planfile.FINISHED_STATES`, and it resolves at least one open box.

    `NOT_STARTED_STATES` IS DELIBERATELY NOT HONOURED, and the measurement is the reason rather than a preference. `wl_planfile`'s design note 4 already recorded on 2026-09-02 that its own premise had stopped holding -- "`Status: draft` is the DEFAULT header on plans under active execution" -- and downgraded drafts to a one-line census instead of finishing the job.
    Measured against this tree on 2026-09-22, `draft` alone carries 130 of 221 open boxes; exempting it would leave this gate asserting almost nothing. ALL means all.

    `boxes` is `wl_backlog._open_boxes`'s shared census, injected so this is never a third scan of the corpus and so a fixture can supply one. `read_text` is injected for the same reason.
    """
    boxes = BL._open_boxes(root) if boxes is None else boxes
    reader = read_text or _read_text
    out = []
    for rel, status, _n in recs:
        if str(status or "").strip().lower() in F.FINISHED_STATES:
            continue
        n_open = boxes.get(rel, (0, None))[0]
        if n_open <= 0:
            continue
        out.append({"rel": rel, "status": status, "open": n_open, "reader": reader})
    return out


def _read_text(root, rel):
    try:
        return (pathlib.Path(root) / rel).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def first_box(root, rel, reader=None):
    """(sig, body) of the FIRST open box in one plan, or None. One file read.

    The signature is `wl_planrec.box_sig`, which is what the committed ledger, the compaction record and the investigation row all speak. `wl_planfid.TASK_MATCH` and `wl_planfile.match_item`'s token overlap are deliberately NOT used: fuzzy matching has no business in a blocking path, and an exact 8-hex signature is what makes the printed recipe copy-pasteable.
    """
    text = (reader or _read_text)(root, rel)
    if not text:
        return None
    try:
        boxes = R.open_boxes(text)
    except Exception:  # noqa: BLE001 -- a plan read must never wedge a stop
        return None
    if not boxes:
        return None
    _i, _line, body, sig = boxes[0]
    return sig, body


def partition(root, rows, plan_owner, session_id, liveness):
    """(owned, idle_peer, live_peer) -- the three-way split of Part 6.3.

    OWNERSHIP IS `wl_core.owned_by_me`, which treats an UNOWNED plan as this session's, for the reason `wl_planfile` states: wrongly claiming one costs a little reading, wrongly disowning one drops it silently.

    LIVENESS IS `wl_store.session_liveness` AND NOTHING ELSE. It is reached through the `liveness` callable the caller injects, which in production is that function, so this module holds no second opinion about whether a peer is running.
    `wl_backlog._dead_peer` walks the same function, which is what lets the migrate recipe this block prints and the nomination `wl_backlog` prints name the same plan rather than two different ones.
    """
    owned, idle_peer, live_peer = [], [], []
    for row in rows:
        owner = None
        try:
            owner = plan_owner(root, row["rel"])
        except Exception:  # noqa: BLE001 -- a header read must never wedge a stop
            owner = None
        tagged = dict(row, owner=owner)
        if C.owned_by_me(owner, session_id):
            owned.append(tagged)
            continue
        verdict, _why = liveness(owner)
        if verdict in ("live", "unknown"):
            live_peer.append(tagged)
        else:
            idle_peer.append(tagged)
    return owned, idle_peer, live_peer


def assess(clock, total_open, live_peer_open, today=None):
    """The verdict dict. Pure arithmetic over three numbers, no I/O, no judgement.

    THE LIVE-PEER SUBTRACTION IS THE ONE ARITHMETIC CONCESSION IN THE DESIGN, and it is necessary rather than kind: demanding drainage of boxes a live peer is actively working would make the ceiling unreachable by any action this session can take, which is the no-reachable-exit shape the whole module exists to avoid.
    A peer that goes idle drops back into the comparison on the next stop, with no state to remember. The subtraction is STATED in the rendered text, never applied silently.
    """
    ceil, days = ceiling(clock, today)
    slack = int(clock.get("warn_slack") or 0)
    comparable = max(0, int(total_open) - int(live_peer_open))
    if comparable > ceil:
        state = BLOCK
    elif comparable > ceil - slack:
        state = WARN
    else:
        state = SILENT
    return {
        "state": state,
        "ceiling": ceil,
        "days": days,
        "total": int(total_open),
        "live_peer": int(live_peer_open),
        "comparable": comparable,
        "gap": max(0, comparable - ceil),
        "warn_slack": slack,
    }


def render(root, verdict, owned, idle_peer, live_peer, session_id, named=None, blind=None):
    """The block's body. NO LIVE COUNTER anywhere in this text.

    `wl_backlog.render`'s discipline applies verbatim: a body carrying a minute-precision age moves its own content signature on every stop and re-enqueues forever, which is the repeated-nag shape this must not become. Counts of boxes and plans, and the ceiling itself, are stable between edits and are safe.

    THE BLOCK NAMES EXACTLY ONE BOX. A wall of eighteen recipes is how a check earns its way into being ignored; one box with its exact signature and its exact command pair is an entry point into a file a reader can open.
    """
    me8 = (session_id or "")[:8]
    lines = []
    if verdict["state"] == WARN:
        lines.append(
            "PLAN IMPLEMENTATION CLOCK -- %d open box(es) against a ceiling of %d. Within the "
            "%d-box warn band." % (verdict["comparable"], verdict["ceiling"], verdict["warn_slack"])
        )
    else:
        lines.append(
            "PLANNED BUT NOT IMPLEMENTED -- %d open box(es) against today's ceiling of %d. "
            "%d more must close." % (verdict["comparable"], verdict["ceiling"], verdict["gap"])
        )
    lines.append(
        "  The ceiling descends by %s box(es) a day from the baseline written at landing, so "
        "this is silent again as soon as the count is at or under it. Day %d."
        % (_rate(root), verdict["days"])
    )
    if verdict["live_peer"]:
        lines.append(
            "  %d box(es) across %d plan(s) belong to peers this machine reads as LIVE and were "
            "SUBTRACTED from that comparison (%d in the corpus, %d compared). Nothing is demanded "
            "about work somebody else is doing right now."
            % (verdict["live_peer"], len(live_peer), verdict["total"], verdict["comparable"])
        )
    if blind:
        lines.append(
            "  CANNOT SEE: %s. Treat this clock as UNRUN on those file(s); a box the parser "
            "cannot read is debt nothing counts." % blind
        )

    if owned:
        lines.append("")
        lines.append(
            "  OWNED BY THIS SESSION (or naming no Owner) -- %d box(es) across %d plan(s):"
            % (sum(r["open"] for r in owned), len(owned))
        )
        lines.extend(
            "    %s  [Status: %s], %d open" % (row["rel"], row["status"] or "UNKNOWN", row["open"])
            for row in owned[:PLANS_SHOWN]
        )
        rest = len(owned) - min(len(owned), PLANS_SHOWN)
        if rest:
            lines.append("    + %d more plan(s), same verdict" % rest)

    if named:
        rel, sig, body = named
        lines.append("")
        lines.append("  ONE BOX, the first open one in the newest plan this session can reach:")
        lines.append("    %s  %s" % (sig, body[:96]))
        lines.append("")
        lines.append("  FIVE DOORS, and every one of them ends this block:")
        lines.append("")
        lines.append("  1. IT IS DONE, OR IT WAS ALREADY DONE. Investigate first, then tick:")
        lines.append(
            "       worklist.py --plan-investigate %s %s %s present|absent|partial \\"
            % (me8, rel, sig)
        )
        lines.append("           <kind>:<token> <kind>:<token> -- <what was looked at> --write")
        lines.append(
            "       worklist.py --plan-tick %s %s %s '<evidence>' --write" % (me8, rel, sig)
        )
        lines.append(
            "     A `present` verdict -- the work landed and only the record was stale -- is a "
            "COMPLETE answer and closes the box in two commands."
        )
        lines.append("")
        lines.append("  2. IT IS REAL WORK NOBODY IS TRACKING. Put it where the worklist owns it:")
        lines.append('       worklist.py --add %s "<the box text>"' % me8)
        lines.append("")
        lines.append("  3. IT IS A PEER'S PLAN AND THE PEER IS IDLE. Take it, with provenance:")
        lines.append("       worklist.py --migrate %s --plan <agent/plans/PLAN-x.md>" % me8)
        lines.append("")
        lines.append("  4. IT IS GENUINELY THE OPERATOR'S CALL:")
        lines.append(
            "       worklist.py --defer %s <id> '<q> DEFAULT: <action> WHY: ... HOW: ...'" % me8
        )
        lines.append("")
        lines.append("  5. THE PLAN'S TEXT IS BLOATED AND ITS WORK IS NOT FINISHED:")
        lines.append("       worklist.py --plan-compact %s <agent/plans/PLAN-x.md> --park" % me8)
        lines.append(
            "     `parked` deliberately stays on every clock, so this buys a smaller file and "
            "never an exemption."
        )
        lines.append("")
        lines.append(
            "  EDITING `Status:` TO A FINISHED WORD IS NOT A DOOR. check:ci-plan-boxes G-A3 "
            "refuses a finished status over open boxes and will red the branch, so it trades "
            "this block for a CI failure. A door the gate will punish is worse than no door."
        )

    if idle_peer:
        total_idle = sum(r["open"] for r in idle_peer)
        lines.append("")
        lines.append(
            "  A PEER'S, AND THE PEER READS IDLE -- %d box(es) across %d plan(s). NOT demanded "
            "of this session: implementing one without adopting it first produces a committed "
            "document that contradicts who did the work. Adopt one and it joins the list above:"
            % (total_idle, len(idle_peer))
        )
        lines.extend(
            "    worklist.py --migrate %s --plan %s   (%d open, owner %s)"
            % (me8, row["rel"], row["open"], row["owner"] or "unowned")
            for row in idle_peer[:PLANS_SHOWN]
        )
        rest = len(idle_peer) - min(len(idle_peer), PLANS_SHOWN)
        if rest:
            lines.append("    + %d more idle-owned plan(s)" % rest)

    lines.append("")
    lines.append(
        "  SHAPE: %d in-scope plan(s) carrying %d open box(es) -- %d yours, %d idle-owned, "
        "%d live-owned. Ceiling %d on day %d."
        % (
            len(owned) + len(idle_peer) + len(live_peer),
            verdict["total"],
            sum(r["open"] for r in owned),
            sum(r["open"] for r in idle_peer),
            sum(r["open"] for r in live_peer),
            verdict["ceiling"],
            verdict["days"],
        )
    )
    return "\n".join(lines)


def _rate(root):
    clock, _err = load_clock(root)
    return clock.get("drain_per_day")


def evaluate(
    root,
    recs,
    session_id,
    plan_owner,
    worklist,
    projects_dir=None,
    events=None,
    today=None,
    boxes=None,
    read_text=None,
    liveness=None,
):
    """(state, text, detail) for one stop. `state` is silent/warn/block.

    THE ONLY ENTRY POINT THE CALL SITE USES, so the call site stays one `try` and one `vadd`. Every failure mode inside here resolves to SILENT with a reason in `detail`, never to a block on numbers this could not read: a blocking tier that fires because a config file was unreadable is the shape that gets switched off within a day.
    """
    detail = {"reason": "", "verdict": None}
    clock, problem = load_clock(root)
    if problem:
        detail["reason"] = problem
        return SILENT, "", detail
    if liveness is None:

        def liveness(owner):
            return S.session_liveness(worklist, owner, projects_dir, events)

    rows = scope_rows(root, recs, boxes=boxes, read_text=read_text)
    if not rows:
        # ZERO IN-SCOPE PLANS IS NOT AUTOMATICALLY A PASS, but it is not this module's finding either: check:ci-plan-implementation's P-A6 owns the anti-vacuity floor, where there is a committed ledger to compare the tree against. Here the honest answer is that there is nothing over the ceiling, which is what silence means.
        detail["reason"] = "no in-scope plan carries an open box"
        return SILENT, "", detail
    owned, idle_peer, live_peer = partition(root, rows, plan_owner, session_id, liveness)
    total = sum(r["open"] for r in rows)
    verdict = assess(clock, total, sum(r["open"] for r in live_peer), today)
    detail["verdict"] = verdict
    if verdict["state"] == SILENT:
        detail["reason"] = "at or under the ceiling with room to spare"
        return SILENT, "", detail

    # THE IDLE-PEER HEADLINE COMES FROM `wl_backlog._dead_peer`, CALLED, and the ordering below is the whole reason. That function is what `wl_backlog.render` already prints its own `--migrate --plan` recipe from, so taking its answer here makes the advisory nomination and this block name the SAME plan rather than two, which is what a session reading both would otherwise have to
    # reconcile. Suppressed rather than fatal: a liveness read is a courtesy to the reader and must never wedge a stop.
    dp = None
    with _quiet():
        dp = dead_peer_recipe(
            root,
            recs,
            boxes if boxes is not None else BL._open_boxes(root),
            plan_owner,
            session_id,
            worklist,
            projects_dir,
            events,
        )
    if dp is not None:
        idle_peer = sorted(idle_peer, key=lambda r: r["rel"] != dp["rel"])
    detail["dead_peer"] = dp

    named = None
    for row in owned:
        got = first_box(root, row["rel"], row.get("reader"))
        if got:
            named = (row["rel"], got[0], got[1])
            break
    blind = None
    if owned and named is None:
        blind = (
            "%d plan(s) this session owns resolve open boxes in the shared census but none in their own text"
            % len(owned)
        )
    text = render(root, verdict, owned, idle_peer, live_peer, session_id, named, blind)
    return verdict["state"], text, detail


def dead_peer_recipe(
    root, recs, boxes, plan_owner, session_id, worklist, projects_dir=None, events=None
):
    """`wl_backlog._dead_peer`'s answer, IMPORTED AND CALLED rather than reimplemented.

    It already walks `wl_store.session_liveness`, already skips live and unknown owners, and already returns the count plus the newest candidate. Its own comment states the reason this module inherits: implementing a peer's plan without `worklist.py --migrate --plan` first would produce a committed document that contradicts who did the work.
    Kept as a named seam so a control can assert the two mechanisms name the SAME plan.
    """
    return BL._dead_peer(root, recs, boxes, plan_owner, session_id, worklist, projects_dir, events)


# --------------------------------------------------------------------------- CONTROLS live in test-planenforce.py beside this file, run by .claude/hooks/test-hooks.sh, which is the placement wl_planfile states as the convention: keeping fixtures out of here keeps the import that every Stop pays for free of them.
