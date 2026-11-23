"""Refuse a writer spawn that would break a live plan's mutex, or claim files a live plan already owns.

THE ASK (operator, 2026-09-25, section X): "The concurrency field is really about files. 'Exclusive' is only needed when two plans touch the same files, like today's A3 and scanner collision. Declaring the owned paths lets the hook decide instead of relying on a label." Plan: agent/plans/PLAN-plan-priority-concurrency.md section 5a (T5).

THE DECISION, for an Agent or Task call (the rules are `wl_planconc.spawn_verdict`, shared with the roster's queue):
  1. not a spawn, or a read-only type (`wl_roster.read_only_types`, as the cap guard) -> ALLOW;
  2. S = the plans the spawn serves (`spawn_plans`: none for a `Plan: none -- <reason>` line, else a `Plan: PLAN-x.md` line, else
     the `#<id>` items it names, else a bare `PLAN-x.md [<8hex>]`); L = the plans live writers serve (`live_plans`: this
     session's live writers through their first prompts, every session's fresh leases on plan-linked items), minus S;
  2b. a live agent of a writer type whose brief says `Owns: none` and whose transcript shows no edit is a reader, not a holder:
     it serves no plan in L, a same-session lease to it holds nothing, and an allowed spawn's stderr names it (#55b1f90b);
  2c. the spawn itself briefed `Owns: none -- <reason>` is such a runner: S is empty whatever plan it names, it claims nothing, and its stderr says so (#79b7e92e); a bare `Owns: none` does not parse and is judged as declaring nothing;
  3. DENY when a plan in L is `Concurrency: exclusive` (the mutex);
  4. DENY when a plan in S is exclusive and L is not empty (decision D5: a mutex taken while others hold files is no mutex);
  5. DENY when S's Owns and L's Owns share a path, naming both globs and one witness path; a spawn the harness isolates in its own tree is ALLOWED with a stderr note naming the witness instead (the lease plan's W12, a lead decision awaiting the operator's look), since a clash then surfaces at landing. Steps 3, 4 and the header refusals still apply to it;
  6. a planless spawn is judged on its own `Owns:` line when it declares one, refused under a live exclusive plan unless that
     line is disjoint, and ALLOWED with a stderr note when it declares nothing (decision D4). An `Owns:` line that does not
     parse reads as nothing declared, and every refusal or note built on that says the line was not read and why.

  7. a spawn briefed `Handover: #<id>` with no `Plan:` line is ADMITTED past every file rule (an exclusive plan's mutex is over its files), still refused by the writer cap and still recorded as a claim, with a stderr note, when that id is a handover in the store answered `lease:<lease>` and that lease's record says it was cut with `--tree landing` (agent/plans/PLAN-simple-two-tree-loop.md D5, box B7): the writer works in a tree cut from the landing branch, which no live plan of the development checkout shares. Any other `Handover:` brief (an unknown id, an answer naming no lease, a development-cut lease, or a `Plan:` line beside it) is judged by the rules above, and the note says why the handover did not admit it.

The writer cap still applies first: `block_agent_cap` is ORDER 3 on the same chain.

SAME-MESSAGE SPAWNS (#105d59a7, the lease plan's W13). A sibling started by the same message has no meta and no Stop event yet, so the roster cannot list it: on 2026-11-04 three writers passed this guard with real Owns overlaps. Each admitted writer spawn therefore appends a claim (`wl_planconc.claim_gate`), and L above includes the unexpired claims of every session whose agent has not appeared. Read, decide and append sit inside one flock, so either hook order is safe. The cap is decided here too, because a count read at ORDER 3 and a claim appended at ORDER 5 would leave two racing spawns both under it: this session's live writers plus its claims must stay under `wl_roster.writer_cap`. As the last guard of the chain that can REFUSE, nothing behind it can refuse a spawn it claimed: the one guard behind it, `warn_writer_brief` (ORDER 5, PLAN-experience-feedback P1/P4), never exits 2, and its own suite asserts rc 0 on every case.

THE X FIELDS ARE MANDATORY (PLAN-plan-priority-concurrency.md T11): a missing Owns fails closed as `**` and a spawn for such a plan is refused.

FAILS OPEN, LOUDLY, when it cannot see: a module that will not import, a store that will not fold, a writer estimate that is blind with no cross-session lease or claim visible either, or a claim file that cannot be locked or read (judged then without its siblings). The Stop hook's roster recounts from the authoritative event (PLAN-plan-priority-concurrency T8, `roster-concurrency`).

NO ENVIRONMENT READ. This file is a sealed module in `.ci/policy/worklist-env-registry.json`. The payload's own `cwd` and `session_id` locate the session.

ITS EVIDENCE. `OWN_SUITE = True`, so `.claude/rediacc_hooks/guards/test-block_plan_concurrency.py` drives it through the dispatcher in both directions against fixture trees and stores; `.claude/hooks/stop/test-plandeps.py` covers `spawn_verdict` and the overlap engine it calls.
"""

import os
import pathlib
import re
import time

from rediacc_hooks import hookio, syspath
from rediacc_hooks.guards import tables

CHAIN = "pre-agent"
OWN_SUITE = True
ORDER = 4

__getattr__ = tables("block_plan_concurrency", "FIXTURES", "ENVS", "EDGE_CASES")

# The mutex refusal, planted away: the differential's mutex EDGE_CASE must then stop speaking.
DEFECT = ("return _refuse(event, verdict, kind, MUTEX_EXITS)", "return hookio.ALLOW")

STOP_DIR = pathlib.Path(__file__).resolve().parents[2] / "hooks" / "stop"
# The Agent tool's `isolation` value that gives a spawn its own tree.
ISOLATED_SPAWN = "worktree"
# How long a spawn waits on the claim lock before failing open; each holder keeps it for milliseconds.
LOCK_WAIT_S = 30


MUTEX_EXITS = """
Do one of these:
  - queue the work until the holder finishes; queue-slot names it then:
      .claude/hooks/stop/worklist.py --lease <me> <id> +120 worker:queue
  - dispatch read-only work as subagent_type Plan or Explore, which is never refused
  - stop the holder (TaskStop <id>) and release its lease
"""

OVERLAP_EXITS = """
Do one of these:
  - queue the work until the holder finishes:
      .claude/hooks/stop/worklist.py --lease <me> <id> +120 worker:queue
  - if a plan over-claims, narrow its Owns (visible in the diff):
      .ci/scripts/quality/check_plan_deps.py --set-x <plan> "Owns: ..." --write
  - dispatch read-only work as subagent_type Plan or Explore
  - stop the holder (TaskStop <id>) and release its lease
"""

CAP_EXITS = """
Do one of these:
  - queue the work until a slot frees, naming its brief and files in the todo list:
      .claude/hooks/stop/worklist.py --lease <me> <id> +120 worker:queue
  - dispatch read-only work as subagent_type Plan or Explore, which the cap does not count
  - do the work inline in this session
"""

# Printed when a refusal's holder is a claim, which has no task id to stop.
CLAIM_NOTE = """
A `spawn claim` is a sibling admitted moments ago, with no agent on disk yet. It clears when that agent appears and expires by itself; a refused spawn sent again after it has started is judged on the live writer.
"""

HEAD = {
    "cap": "BLOCKED: this %r writer would pass the writer cap, counting the spawns of this message.",
    "mutex": "BLOCKED: a live plan holds the mutex, so this %r writer does not start.",
    "mutex-own": "BLOCKED: this %r writer serves an exclusive plan, and other plans are live.",
    "overlap": "BLOCKED: this %r writer would edit files a live plan already owns.",
    "no-owns": "BLOCKED: this %r writer serves a plan that declares no Owns, which fails closed.",
    "owns-none": "BLOCKED: this %r writer serves a plan that declares it edits nothing.",
}

# A spawn's `Owns:` line that did not parse: it was judged as declaring nothing, and the reader is told why.
OWNS_UNREAD = (
    "this spawn's Owns: line was not read (%s); write comma-separated globs, e.g. Owns: a/**, b.py"
)

UNSEEN_CLAIMS = (
    "plan-concurrency: the spawn claims could not be read (%s: %s), so this %r spawn was judged\n"
    "without its same-message siblings. The Stop hook's roster recounts plan concurrency from the\n"
    "authoritative event on the next stop.\n"
)

UNEXAMINED = (
    "plan-concurrency: %s, so this %r spawn was ALLOWED unchecked. The Stop hook's roster\n"
    "recounts plan concurrency from the authoritative event on the next stop.\n"
)


# `Handover: #<id>` on a line of its own in the brief (rule 7).
HANDOVER_LINE = re.compile(r"(?m)^\s*Handover:\s*#([0-9a-f]{8})\b")


def handover_lease(text, root, worklist):
    """(lease id, "") when the brief's `Handover: #<id>` names a handover answered `lease:<lease>` whose record was cut with `--tree landing`; ("", why) for a brief that names a handover the rule does not admit; ("", "") for a brief with no Handover line. A read that fails raises, and the caller judges the spawn by the plan rules."""
    found = HANDOVER_LINE.search(text)
    if not found:
        return "", ""
    import wl_core as C
    import wl_handover
    import wl_worktrees

    hid = found.group(1)
    record = wl_handover.fold(worklist, root=root).get(hid)
    if record is None:
        return "", "handover #%s is not in the store" % hid
    lease = wl_handover.lease_of(record)
    if not lease:
        return "", "handover #%s is answered %r, which names no lease" % (
            hid,
            record.get("answer") or "nothing yet",
        )
    dirs = C._git_dirs(pathlib.Path(root))
    if dirs is None:
        return "", "the record store of %s cannot be located" % root
    base = pathlib.Path(os.path.realpath(pathlib.Path(root) / ".claude" / "worktrees"))
    lease_record = wl_worktrees.read_records(dirs[1], base).get(lease)
    if not lease_record or not wl_worktrees.landing_cut(lease_record):
        return "", "lease %s of handover #%s was not cut with `--tree landing`" % (lease, hid)
    return lease, ""


def _refuse(event, verdict, kind, exits):
    head = HEAD.get(
        verdict.kind, "BLOCKED: this %r writer breaks plan concurrency (" + verdict.kind + ")."
    )
    facts = "\n".join("  " + ln for ln in verdict.lines)
    note = CLAIM_NOTE if "spawn claim" in facts or verdict.kind == "cap" else ""
    event.warn_raw("%s\n\n%s\n%s%s" % (head % kind, facts, exits, note))
    return hookio.DENY


def run(event):
    doc = event.doc
    if not isinstance(doc, dict) or doc.get("tool_name") not in ("Agent", "Task"):
        return hookio.ALLOW
    raw_input = doc.get("tool_input")
    tool_input = raw_input if isinstance(raw_input, dict) else {}
    kind = str(tool_input.get("subagent_type") or "general-purpose")
    cwd = str(doc.get("cwd") or event.cwd)
    session_id = str(doc.get("session_id") or "")
    text = "%s\n%s" % (tool_input.get("description") or "", tool_input.get("prompt") or "")
    isolated = tool_input.get("isolation") == ISOLATED_SPAWN
    entered = time.time()
    syspath.on_sys_path(STOP_DIR)
    try:
        import wl_core as C
        import wl_leasehelp as LH
        import wl_planconc as X
        import wl_roster

        root = C.project_root(C.project_start({"cwd": cwd}))
        if kind in wl_roster.read_only_types(root):
            return hookio.ALLOW
        # RULE 7: a handover fix in a landing-cut lease, briefed with no plan line, shares no tree with a live plan here.
        handover_why = ""
        admitted_lease = ""
        if HANDOVER_LINE.search(text):
            if X.spawn_plans(text):
                handover_why = "the brief also names a plan, which the plan rules judge"
            else:
                try:
                    worklist = C.worklist_for(C.project_start({"cwd": cwd}))
                    lease, handover_why = handover_lease(text, root, worklist)
                except Exception as exc:
                    lease, handover_why = (
                        "",
                        "the handover could not be read (%s: %s)"
                        % (
                            type(exc).__name__,
                            str(exc)[:160],
                        ),
                    )
                admitted_lease = lease
        declared = X.declared_owns(text)
        owns_problem = X.owns_line_problem(text) if declared is None else None
        # A brief `Owns: none -- <reason>` (the grammar refuses a bare `none`, which reads as None above) is a runner: it holds no plan, as `live_plans` already treats such an agent once it is live, so it serves none here and claims nothing (#79b7e92e).
        runner = declared == ()
        names_work = bool(X.spawn_plans(text) or LH.item_refs(text))
        # THE CHEAP PATH: a spawn that names no plan, no item and no Owns can only be refused by a live mutex, and there is none anywhere unless some plan declares one. Reading ~40 plan heads costs milliseconds; a full fold costs ~0.5 s.
        cheap = not names_work and declared is None and not X.exclusive_plans(root)
        serving: set[str] = set()
        live: dict[str, list[str]] | None = X.LivePlans()
        if not cheap:
            import wl_store as S

            fold = S.load(C.worklist_for(C.project_start({"cwd": cwd})), sync=False)
            by_id = {r["id"]: r for r in fold.items if isinstance(r, dict) and r.get("id")}
            serving = set() if runner else X.spawn_plans(text, by_id)
            live = X.live_plans(cwd, session_id, fold)
        rows, metas = wl_roster.live_estimate(cwd, session_id)
        writers = sum(1 for r in rows or () if r.get("writer"))
        cap = wl_roster.writer_cap(root)
        claims_path = C.worklist_for(C.project_start({"cwd": cwd})).with_suffix(X.CLAIMS_SUFFIX)
    except Exception as exc:
        event.warn_raw(
            UNEXAMINED
            % (
                "the plan state could not be read (%s: %s)" % (type(exc).__name__, str(exc)[:160]),
                kind,
            )
        )
        return hookio.ALLOW

    judged_against: list[dict] = []

    def judge(claims):
        pending = X.unconsumed(claims, metas, session_id)
        judged_against[:] = pending
        # Blind with no claim either: nothing to judge against, as the failing-open line below says.
        if cheap or (live is None and not pending):
            verdict = X.Verdict(True, "unjudged")
        else:
            verdict = X.spawn_verdict(
                serving,
                X.with_claims(live, pending),
                lambda base: X.plan_x(root, base),
                declared,
                root=root,
                isolated=isolated,
            )
        if not verdict.allow and admitted_lease:
            # Rule 7: a landing-cut tree shares no file with a plan of this checkout, and a planless spawn meets only file rules here (an exclusive plan's mutex is over its files), so none refuses it; the writer cap still does, and the claim row is still appended.
            verdict = X.Verdict(True, "handover", (), verdict.note)
        if not verdict.allow:
            return verdict
        return X.cap_verdict(writers, pending, session_id, cap) or verdict

    row = X.claim_row(
        session_id, serving, declared, tool_input.get("description"), isolated, entered
    )
    try:
        verdict = X.claim_gate(claims_path, judge, row, LOCK_WAIT_S)
    except Exception as exc:
        event.warn_raw(UNSEEN_CLAIMS % (type(exc).__name__, str(exc)[:160], kind))
        verdict = judge([])
    if owns_problem and not verdict.allow:
        verdict = X.Verdict(
            verdict.allow,
            verdict.kind,
            (*verdict.lines, OWNS_UNREAD % owns_problem),
            verdict.note,
        )
    if admitted_lease and verdict.allow:
        event.warn_raw(
            "plan-concurrency: this %r spawn serves a handover in lease %s, cut with `--tree landing`; no live plan of this checkout shares its tree, so no file rule refuses it (the writer cap still applies).\n"
            % (kind, admitted_lease)
        )
    if handover_why:
        event.warn_raw(
            "plan-concurrency: the `Handover:` line did not admit this spawn: %s.\n" % handover_why
        )
    if verdict.kind in ("mutex", "mutex-own"):
        return _refuse(event, verdict, kind, MUTEX_EXITS)
    if verdict.kind == "cap":
        return _refuse(event, verdict, kind, CAP_EXITS)
    if not verdict.allow:
        return _refuse(event, verdict, kind, OVERLAP_EXITS)
    if cheap:
        event.warn_raw(
            "plan-concurrency: a planless %r writer declares no `Owns:` line, so its files are not "
            "checked against live plans (add `Plan: PLAN-x.md` or `Owns: <globs>` to the prompt).\n"
            % kind
        )
    if owns_problem:
        event.warn_raw("plan-concurrency: %s.\n" % (OWNS_UNREAD % owns_problem))
    if runner:
        event.warn_raw(
            "plan-concurrency: this %r spawn is briefed `Owns: none`, so it holds no plan and overlaps no file; one edit makes it a holder at the next spawn's check.\n"
            % kind
        )
    readers = getattr(live, "readers", None) or []
    if readers:
        event.warn_raw(
            "plan-concurrency: %d live agent(s) of a writer type hold no plan, briefed `Owns: none` with no edit: %s.\n"
            % (len(readers), "; ".join(readers))
        )
    if live is None and judged_against and not cheap:
        event.warn_raw(
            "plan-concurrency: no live writer could be counted for session %r, so this %r spawn was judged against the %d unexpired sibling claim(s) only. The Stop hook's roster\n"
            "recounts plan concurrency from the authoritative event on the next stop.\n"
            % (session_id, kind, len(judged_against))
        )
    elif live is None:
        event.warn_raw(
            UNEXAMINED
            % (
                "no live writer could be counted for session %r and no lease is visible"
                % session_id,
                kind,
            )
        )
    if verdict.note:
        event.warn_raw("plan-concurrency: %s.\n" % verdict.note)
    return hookio.ALLOW
