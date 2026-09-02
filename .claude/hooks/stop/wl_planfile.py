"""wl_planfile: keep a committed `agent/PLAN-*.md` checkbox list and the
worklist IN STEP, so a plan survives compaction as something traceable rather
than as eighteen boxes nobody can account for.

WHY THIS EXISTS, from a measurement rather than from theory. On 2026-09-02
`agent/PLAN-secret-namespace-migration.md` carried 18 open `- [ ]` lines and 4
ticked ones, and its own `## Tasks` section stated the contract in as many
words:

    "Checkbox lines are what `wl_planfid.plan_tasks` parses, so this list and
     the worklist must stay in step: one `worklist.py --add` item per line."

The worklist held ZERO of them. Nothing in this directory read the file: the
only mention of `agent/PLAN-*.md` in worklist.py is the SUGGESTION string
triage prints when it tells you where to write a plan, and `wl_planfid` -- the
one module that does parse checkbox tasks -- reads the HARNESS plan named by
the transcript's `plan_mode_exit` record, never a committed one. So the durable
document that exists precisely to outlive a compaction could go stale in the
one way that makes it useless: you can read the 18 boxes and not know which are
live. The operator's words: "the stop hook doesn't really enforce for todo
items in the planning file but it should ... otherwise we cannot trace/update
the planfile in sake of multiple contexts because of compaction".

------------------------------------------------------------------------------
THE FOUR DESIGN CHOICES, each of which had a worse obvious alternative.

1. IT IS AN ADVISORY (`outq_add`), NEVER A `vadd`. This is not timidity, it is
   the only shape that does not deadlock the repo. The Stop battery's whole
   enforcement is "a turn cannot end while an open item tagged with this
   session remains". A check that converted 18 plan tasks into 18 session-owned
   open items -- or that blocked until they existed -- would wedge EVERY turn of
   EVERY session until a multi-week migration finished. The failure mode being
   fixed is invisibility, and an advisory cures invisibility; blocking cures
   nothing here and breaks the hook for everyone. `outq` also cannot wedge a
   stop by construction: it is drained on the allow path and survives a block.

2. THE NOISE CONTROL IS THE QUEUE'S OWN, PLUS A CAP, NOT A NEW LATCH.
   `OUTQ_PER_STOP` is 1, so at most one advisory section reaches any stop at
   all; `outq_add`'s content signature suppresses an unchanged body inside
   `REPORT_REFRESH_MIN` (6h) and re-fires IMMEDIATELY when the body changes.
   That is exactly the "only when the plan changed" policy, for free and
   already tested, without a second suppression ledger to go silently stale.
   On top of it: ONE plan per stop (the newest-mtime in-scope plan that has
   something to say) and at most PLAN_TASK_SHOW untracked lines quoted, with
   the remainder COUNTED. Eighteen quoted lines every stop is a wall, and a
   wall is how a check gets switched off; a count plus three is a reader's
   entry point into a file they can open.

3. SCOPE IS OWNERSHIP, LIKE EVERY OTHER SIGNATURE HERE. A plan whose header
   names a PEER as `Owner:` is skipped outright. An unowned plan stays in scope
   for the same reason an untagged worklist item does (`wl_core.owned_by_me`):
   wrongly claiming one costs a little reading, wrongly disowning one drops it
   silently. Reporting a peer's plan would be permissible -- this never blocks
   -- but it doubles the noise to say something the peer's own stop already
   says, so it is declined.

4. THE STATUS FILTER IS A BLOCKLIST, NOT A WHITELIST, AND THAT IS DELIBERATE.
   `plan_drift_rows` next door admits only `executing`/`UNKNOWN`. Copying it
   here would have made this check VACUOUS on the very plan it was written for:
   that plan reads `Status: ready`. Measured over the 62 plans in this tree the
   statuses are done/draft/ready/landed/implemented/superseded/design/proposal/
   accepted/approved/UNKNOWN and two parse artifacts -- a whitelist would have
   to guess every future word, and a word it fails to guess makes the check go
   quiet with no evidence that it did. So: FINISHED states are history and
   NOT_STARTED states are proposals, both exempt by name; everything else,
   including an unparseable status, is IN scope. A new status word costs a
   little noise, never silence, which is the correct direction for a check
   whose entire purpose is anti-vacuity.

------------------------------------------------------------------------------
PARSING IS `wl_planfid.plan_tasks`, CALLED THREE TIMES, NOT FORKED.

`plan_tasks` returns the plan's tasks but throws away WHICH BOX each came from,
and this check needs open-versus-done. Copying its body to keep the mark would
fork a parser whose rules are load-bearing (fence tracking, action-heading
bullets, the `[?]`/`[>]` exclusion, dedup, the 8-char floor). Instead the split
is derived from the real parser by set difference:

    every    = plan_tasks(text)                        # boxes + action bullets
    no_open  = plan_tasks(text minus `- [ ]` lines)
    no_done  = plan_tasks(text minus `- [x]` lines)
    open     = every - no_open      done = every - no_done

A plain bullet under an action heading survives both deletions, so it lands in
NEITHER set and is never reported -- which is the conservative reading of the
contract, whose subject is checkbox lines. `- [?]` and `- [>]` lines are not
checkboxes to `CHECKBOX_RE` and survive both deletions too, so they are
excluded for free rather than by a second rule that could drift out of step.

------------------------------------------------------------------------------
WHICH DIRECTION A WRONG ANSWER COSTS MORE. A false "untracked" sends a session
to `--add` an item that already exists, which is duplicate tracking and real
harm; a missed one leaves today's status quo. So matching is GENEROUS: a plan
task counts as tracked when any worklist item in ANY state (open, done,
deferred, leased) contains it or is contained by it at `wl_planfid.TASK_MATCH`,
in EITHER direction, and items belonging to any session count. The constants are
imported rather than restated so the calibration stays in one place.

BLINDNESS IS REPORTED, NEVER PASSED. A plan holding raw `- [ ]` lines that the
parser resolves to zero open tasks is named as unreadable rather than counted as
clean, per the V_PR_UNREADABLE convention: a check that cannot see must say so.
"""

import os
import pathlib
import re

import wl_core as C
import wl_planfid as P

# ---------------------------------------------------------------------------
# Bounds. Every one of these exists so a pathological file cannot turn the Stop
# hook into a slow path; none of them may silently drop a finding without the
# render saying it did.

# In-scope plans whose BODY is read per stop, newest mtime first. Applied AFTER
# the status and ownership filters, and the remainder is REPORTED rather than
# dropped: a cap that hides the plan you needed reads exactly like a clean run,
# which is the failure this whole module exists to stop. Measured on this repo:
# 62 plans, 36 in scope by status, ~10 ms to read them all, so the cap is
# headroom against a pathological directory and not a routine truncation.
PLAN_MAX_READ = int(os.environ.get("WORKLIST_PLANFILE_MAX_READ", "40"))
# Untracked tasks QUOTED. The rest are counted. See design note 2.
PLAN_TASK_SHOW = int(os.environ.get("WORKLIST_PLANFILE_SHOW", "3"))
# Stale-box examples quoted in the reverse direction.
PLAN_STALE_SHOW = int(os.environ.get("WORKLIST_PLANFILE_STALE_SHOW", "2"))
# A plan bigger than this is not read. 400 KB is ~10x the largest plan here.
PLAN_MAX_BYTES = int(os.environ.get("WORKLIST_PLANFILE_MAX_BYTES", str(400 * 1024)))
TASK_QUOTE_CHARS = 96

# Statuses that put a plan OUT of scope. See design note 4: this is a blocklist
# on purpose, so an unrecognised status is noisy rather than invisible.
#
# FINISHED -- history. Demanding that history stay in step with a live worklist
# is how a check earns its way into being ignored.
FINISHED_STATES = frozenset(
    {
        "done",
        "superseded",
        "landed",
        "shipped",
        "merged",
        "implemented",
        "complete",
        "completed",
        "closed",
        "obsolete",
        "abandoned",
        "dropped",
        "cancelled",
        "canceled",
        "withdrawn",
        "archived",
        "historical",
    }
)
# NOT STARTED -- a proposal. Its boxes are a sketch of work nobody has taken
# on, and demanding worklist items for a sketch is the "18 legitimately
# not-yet-started tasks" wall this check must not become.
NOT_STARTED_STATES = frozenset(
    {
        "draft",
        "design",
        "designed",
        "proposal",
        "proposed",
        "idea",
        "sketch",
        "rfc",
        "exploratory",
        "deferred",
        "rejected",
    }
)

# The two checkbox shapes, spelled here ONLY to delete lines before handing the
# text back to the real parser. Nothing downstream reads them as tasks.
OPEN_BOX_LINE = re.compile(r"^\s*[-*+]\s+\[ \]\s+\S")
DONE_BOX_LINE = re.compile(r"^\s*[-*+]\s+\[[xX]\]\s+\S")
# A worklist state that means the item is no longer outstanding. ' ', '?' and
# '>' are the open three (wl_checks uses the same triple).
CLOSED_STATES = frozenset({"x"})


def _drop_lines(text, rx):
    return "\n".join(ln for ln in (text or "").splitlines() if not rx.match(ln))


def plan_boxes(text):
    """(open_tasks, done_tasks) for one plan body, via wl_planfid.plan_tasks.

    Three calls to the REAL parser and two set differences -- see the module
    docstring for why this is not a re-implementation. Order is the plan's own,
    which is the order a reader will find them in the file.
    """
    every = P.plan_tasks(text)
    if not every:
        return [], []
    no_open = set(P.plan_tasks(_drop_lines(text, OPEN_BOX_LINE)))
    no_done = set(P.plan_tasks(_drop_lines(text, DONE_BOX_LINE)))
    return [t for t in every if t not in no_open], [t for t in every if t not in no_done]


def raw_box_counts(text):
    """(open, done) counted straight off the raw lines, with no parser at all.

    The anti-vacuity control. If a plan plainly holds `- [ ]` lines and
    plan_boxes resolves none of them, the check is BLIND on that file and says
    so; without this second, dumber count there is nothing to compare against
    and 'no findings' would be indistinguishable from 'saw nothing'.
    """
    o = d = 0
    for ln in (text or "").splitlines():
        if OPEN_BOX_LINE.match(ln):
            o += 1
        elif DONE_BOX_LINE.match(ln):
            d += 1
    return o, d


def item_rows(fold):
    """[(id, state, base_text)] for every item in the fold, any owner, any state.

    ANY OWNER: the question is "is this task tracked", and a peer tracking it
    is tracked. ANY STATE: a ticked item is what a `- [x]` box should match, so
    filtering to open items would report every finished task as untracked.

    BASE text, not `rec['text']`: that field accumulates every update note
    forever (one live item reached ~20 concatenated lines), and a token bag
    inflated by twenty notes matches almost anything -- which would silently
    turn this check off by declaring everything tracked. The extraction mirrors
    wl_store.brief_text's own fallback rather than importing it, because
    brief_text appends the LATEST note, which is the part being excluded.
    """
    rows = []
    for r in list(getattr(fold, "items", None) or []):
        # Typed rather than try/except-guarded: a record that is not a mapping
        # is skipped, while a genuine bug in the three lines below still raises
        # into the caller's one wrapper instead of being swallowed per record.
        if not isinstance(r, dict):
            continue
        base = str(r.get("basetext") or "").strip()
        if not base:
            base = str(r.get("text") or "").strip().split("  ", 1)[0]
        if not base:
            continue
        rows.append((str(r.get("id") or ""), str(r.get("state") or " "), base))
    return rows


def _toks(s):
    """wl_planfid's own normalisation, deliberately NOT a variant of it.

    No stopword list: TASK_MATCH was calibrated at 0.7 against text tokenised
    exactly this way, and stripping connectives would move the threshold's
    meaning while leaving its number alone.
    """
    return set(P._norm(s).split())


def prepare(rows):
    """[(id, state, tokens)] -- the item side tokenised ONCE.

    Not an optimisation for its own sake: `reconcile` asks about every task, so
    tokenising inside the inner loop is items x tasks (48 x 22 on this repo's
    live plan) of work on the path that lets every session end a turn.
    """
    out = []
    for iid, state, text in rows:
        toks = _toks(text)
        if len(toks) >= P.MIN_MATCH_TOKENS:
            out.append((iid, state, toks))
    return out


def match_item(task, prepared):
    """(item_id, state) of the worklist item that stands for this task, or None.

    Takes PREPARED rows (see `prepare`), not raw ones: `reconcile` asks about
    every task, and tokenising the item side inside that loop is items x tasks
    of work on the path that lets every session in this repo end a turn.

    Containment in EITHER direction at wl_planfid.TASK_MATCH: an item that
    quotes a long task line, and an item whose wording the task line is a short
    version of, are both tracking. Generous on purpose -- see the module
    docstring on which direction a wrong answer costs more. Ties break on the
    strongest overlap so the id quoted back is the best one, not the first one.
    """
    tt = _toks(task)
    if len(tt) < P.MIN_MATCH_TOKENS:
        return None
    best = None
    for iid, state, it in prepared:
        inter = len(tt & it)
        if not inter:
            continue
        if inter / len(tt) >= P.TASK_MATCH or inter / len(it) >= P.TASK_MATCH:
            score = inter / float(min(len(tt), len(it)))
            if best is None or score > best[0]:
                best = (score, iid, state)
    return None if best is None else (best[1], best[2])


def reconcile(open_tasks, done_tasks, rows):
    """The three findings for one plan, as ([untracked], [stale_open], n_reopened).

    untracked    open `- [ ]` boxes with no worklist item at all -- the core.
    stale_open   open `- [ ]` boxes whose item is TICKED: the plan is behind the
                 work, and the fix is one character in a file this session owns.
    n_reopened   `- [x]` boxes whose item is still open. COUNT ONLY, no quotes:
                 the remedy is a tick, and ticks already have a gate of their
                 own with evidence rules this check has no business restating.
    """
    prepared = prepare(rows)
    untracked, stale_open, reopened = [], [], 0
    for t in open_tasks:
        hit = match_item(t, prepared)
        if hit is None:
            untracked.append(t)
        elif hit[1] in CLOSED_STATES:
            stale_open.append((t, hit[0]))
    for t in done_tasks:
        hit = match_item(t, prepared)
        if hit is not None and hit[1] not in CLOSED_STATES:
            reopened += 1
    return untracked, stale_open, reopened


def _read(path):
    """A plan's text, or None. NEVER raises: this runs on the path that lets
    every session in the repo end a turn."""
    try:
        p = pathlib.Path(path)
        if p.stat().st_size > PLAN_MAX_BYTES:
            return None
        return p.read_text(encoding="utf-8", errors="replace")
    except (OSError, ValueError):
        return None


def _owner(plan_owner, root, rel):
    """The plan's declared Owner, or None when it cannot be read.

    None means UNOWNED, which `wl_core.owned_by_me` treats as in scope. That is
    the deliberate direction: a header this cannot parse should make the check
    noisy, never silent, for the same reason an untagged worklist item counts as
    yours.
    """
    try:
        return plan_owner(root, rel)
    except Exception:  # noqa: BLE001 -- a header read must never wedge a stop
        return None


def in_scope_status(status):
    s = str(status or "").strip().lower()
    return s not in FINISHED_STATES and s not in NOT_STARTED_STATES


def plan_rows(root, recs, fold, session_id, plan_owner):
    """[dict] of findings, newest plan first. `recs` and `plan_owner` are passed
    in rather than imported so this module never depends on wl_checks, which
    imports it (and so the selftest can drive it with fixtures).

    Returns (rows, unread) where `unread` is how many in-scope plans the read
    cap kept this stop from opening. Never silently zero-truncated: see
    PLAN_MAX_READ.

    Each dict: rel, status, n_open, n_done, untracked, stale_open, reopened,
    blind. `blind` is a string when the parser could not resolve boxes the raw
    text plainly holds, and is a FINDING rather than a skip.
    """
    rows = item_rows(fold)
    # Status first because it is free (plan_records already parsed it), then
    # ownership, which costs a header read. Only what survives both is capped,
    # so the cap counts plans this session actually had a reason to open.
    scoped = [
        rec
        for rec in list(recs)
        if in_scope_status(rec[1]) and C.owned_by_me(_owner(plan_owner, root, rec[0]), session_id)
    ]
    unread = max(0, len(scoped) - PLAN_MAX_READ)
    out = []
    for rec in scoped[:PLAN_MAX_READ]:
        rel, status = rec[0], rec[1]
        text = _read(pathlib.Path(root) / rel)
        if text is None or len(text) < P.MIN_PLAN_CHARS:
            continue
        raw_open, raw_done = raw_box_counts(text)
        if not raw_open and not raw_done:
            continue
        try:
            open_tasks, done_tasks = plan_boxes(text)
        except Exception:  # noqa: BLE001
            open_tasks, done_tasks = [], []
        blind = None
        if raw_open and not open_tasks:
            blind = "%d raw `- [ ]` line(s) that the task parser resolved to none" % raw_open
        untracked, stale_open, reopened = reconcile(open_tasks, done_tasks, rows)
        if not (untracked or stale_open or reopened or blind):
            continue
        out.append(
            {
                "rel": rel,
                "status": status,
                "n_open": len(open_tasks),
                "n_done": len(done_tasks),
                "untracked": untracked,
                "stale_open": stale_open,
                "reopened": reopened,
                "blind": blind,
            }
        )
    return out, unread


def _quote(t):
    t = re.sub(r"\s+", " ", str(t or "")).strip()
    return t if len(t) <= TASK_QUOTE_CHARS else t[: TASK_QUOTE_CHARS - 3] + "..."


def render(row, n_more_plans=0, unread=0):
    """The advisory body for ONE plan, or "" when there is nothing to say.

    Prints the SHAPE (boxes seen, open, done, items scanned is implicit in the
    verdicts) and not merely the verdict, so a reader can tell a real finding
    from a parser that saw nothing.
    """
    if not row:
        return ""
    lines = [
        "PLAN FILE vs WORKLIST -- %s [Status: %s], %d open box(es), %d ticked"
        % (row["rel"], row["status"], row["n_open"], row["n_done"])
    ]
    if row.get("blind"):
        lines.append(
            "  CANNOT SEE: %s. Treat this check as UNRUN on this file until the\n"
            "  list parses; a box the parser cannot read is a task nothing tracks." % row["blind"]
        )
    n = len(row["untracked"])
    if n:
        lines.append(
            "  %d open task(s) have NO worklist item. A plan is the compaction-proof\n"
            "  record, and a box with no item is untraceable the moment this context\n"
            "  ends -- nobody can tell which of them are live. Track them:" % n
        )
        lines.extend(
            '    worklist.py --add <me> "%s"' % _quote(t) for t in row["untracked"][:PLAN_TASK_SHOW]
        )
        rest = n - min(n, PLAN_TASK_SHOW)
        if rest:
            lines.append("    + %d more open task(s) in that file, same verdict" % rest)
    if row["stale_open"]:
        lines.append(
            "  %d open `- [ ]` box(es) whose worklist item is already TICKED -- the\n"
            "  plan is behind the work; tick the box in the file:" % len(row["stale_open"])
        )
        lines.extend(
            "    #%s  %s" % (iid, _quote(t)) for t, iid in row["stale_open"][:PLAN_STALE_SHOW]
        )
        rest = len(row["stale_open"]) - min(len(row["stale_open"]), PLAN_STALE_SHOW)
        if rest:
            lines.append("    + %d more" % rest)
    if row["reopened"]:
        lines.append(
            "  %d `- [x]` box(es) still have an OPEN worklist item. Count only: the\n"
            "  remedy is a tick with evidence, which the tick gate already owns." % row["reopened"]
        )
    lines.append(
        "  ADVISORY, never a block: this plan's tasks must not become open items\n"
        "  that wedge every stop until a multi-week migration finishes. Only\n"
        "  plans you own or that name no Owner are checked, and finished or\n"
        "  not-started plans are exempt."
    )
    if unread:
        lines.append(
            "  + %d in-scope plan file(s) were NOT opened this stop (read cap %d).\n"
            "  Their state is UNKNOWN, not clean." % (unread, PLAN_MAX_READ)
        )
    if n_more_plans:
        lines.append(
            "  + %d more in-scope plan file(s) with findings, not shown this stop." % n_more_plans
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CONTROLS live in test-planfile.py beside this file, and are run by
# .claude/hooks/test-hooks.sh. Keeping them out of here keeps the import that
# every Stop pays for free of fixtures.
