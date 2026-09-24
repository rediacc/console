"""The message catalogue: every constant renders at its call-site arity (117), and a missing catalogue fails closed (118).

Ported from `.claude/hooks/stop/worklist-cases/08-poll-and-waiting.sh`. Cases 101-116 (the poll shape, waiting-cross-session and the silent poll fast path) were removed with cross-session messaging on 2026-09-24.
"""

from __future__ import annotations

import importlib.util
import json
import re
import shutil
import subprocess
import sys

from rediacc_hooks.tests import wlfix
from rediacc_hooks.tests.wlfix import wl  # noqa: F401


def run_script(script, argv: list[str], env: dict, stdin: str = "") -> wlfix.Result:
    """One invocation of a COPY of the hook, for the missing-catalogue case.

    `wlfix.Fixture.python` always drives the shipped `worklist.py`; case 118 has to drive a copy that was deliberately separated from its own `wl_*` modules, so the path is a parameter here rather than a knob on the shared fixture.
    """
    proc = subprocess.run(
        [sys.executable, str(script), *argv],
        input=stdin,
        capture_output=True,
        text=True,
        env=dict(env),
        check=False,
    )
    return wlfix.Result(proc.stdout, proc.stderr, proc.returncode)


# The arity of every catalogue constant at its call site in `worklist.py`. Six strings have no needle anywhere in this suite (V_DIVERGED, V_PR_UNREADABLE, V_EVENT_UNPARSEABLE, R_JUDGE_CONTINUE, CTX_SESSION_START_STALE, the exempt-overrun stuck detail), and this registry is their shape protection: every constant must exist and render with the EXACT argument
# arity its call site uses, so a placeholder added or dropped in the catalogue cannot lurk in a branch no test drives. `None` means the constant is printed verbatim and the `%` check is skipped; it still has to be REGISTERED, which is what the gap check at the end of the test is for.
ARITY = {
    "V_STUCK": ("H", 3, "D"),
    "V_EVENT_UNPARSEABLE": ("f",),
    "V_OPEN_ITEMS": (1, "x"),
    "V_UNDEFAULTED": (1, "x"),
    "V_COMPLETION_EVIDENCE": ("a", "b"),
    "V_COMPLETION_TICKS": ("x",),
    "V_COMPLETION_TASKS": ("x",),
    "V_IDLE": ("#1",),
    "V_STALE_LOCAL": ("r", 2),
    "V_DIVERGED": ("r", 2, "r"),
    "V_PR_STALE": ("d",),
    "V_PR_UNREADABLE": ("d",),
    "V_LOOP_DIED": (1,),
    "V_CI_RED": ("9", 1, "q", "rows", 2, 1, "m"),
    "V_CI_UNREADABLE": ("d",),
    # (task-id, the offending command blob): see wl_ci.adhoc_watch.
    "V_ADHOC_WATCH": ("b1", "blob"),
    "CI_NOTE_RETRYABLE": ("9", 1, "pats", "rows"),
    "CI_NOTE_DOWNGRADED": ("9", 1, 2, "", "rows"),
    # v24 review-red gate (wl_ci.review_red). V_REVIEW_RED takes the PR number, head sha, the check-run's title and summary, then owner/name/pr FOUR times (inline-query, inline-reply, top-level-reply and workflow re-dispatch commands each need their own repo slug), then the block ceiling, the current count, the session prefix, and the PR number again for the --defer exit.
    # REVIEW_NOTE_DOWNGRADED takes the PR, the title, the count, then owner/name/pr for its own re-dispatch command.
    "V_REVIEW_RED": (
        "9",
        "sha",
        "t",
        "s",
        "o",
        "n",
        9,
        "o",
        "n",
        9,
        "o",
        "n",
        9,
        "o",
        "n",
        9,
        2,
        1,
        "me",
        "9",
    ),
    "REVIEW_NOTE_DOWNGRADED": ("9", "t", 1, "o", "n", "9"),
    "V_REVIEW_UNREADABLE": ("d",),
    "V_MANY_WORK_CRONS": (2, "l"),
    "V_AGENT_STATE": ("me", "s", "", 250, 4000, "m"),
    "V_AGENT_BOOTSTRAP": ("me", "me"),
    "V_AGENT_STILL_ABSENT": ("me",),
    "CLI_STATE_REFUSED": ("v", "d", 250, 4000),
    "CLI_STATE_WHOLE_DOC": ("m",),
    # One substitution: the offending first step, quoted back so the refusal names what it saw rather than restating the rule in the abstract.
    "CLI_STATE_WAIT_LED": ("lead",),
    "V_SOLO_GRIND": (39, 12),
    "N_UNREAD_REPORTS": (2, "b", "rows", "p", "p", "m"),
    "CLI_REAP_USAGE": (),
    "CLI_REAP_UNKNOWN": ("t", "l"),
    "N_ROSTER_STALE": (20, 1, 19, "p", "m"),
    # The parallel-writer roster (wl_checks.run_stop, wl_roster.status_verb).
    "V_ROSTER_CAP": (5, 4, "rows", "a1 a2", "m"),
    "V_ROSTER_SILENT": (1, 20, "rows", "m"),
    "V_ROSTER_UNLEASED": (1, "rows", "m"),
    "V_ROSTER_DEAD": (1, "rows", "m", "m"),
    "V_QUEUE_SLOT": {"free": 1, "queued": 12, "ids": "#a", "me": "m"},
    "N_ROSTER_HONEST": (3, 4, 1, "12:00Z", "rows"),
    "CLI_STATUS_ROW": {
        "id": "a1",
        "type": "t",
        "desc": "d",
        "lineage": "depth 1",
        "children": "none",
        "size": 1,
        "quiet": "0m",
        "edits": 0,
        "tool": "Bash x",
        "text": "x",
        "verdict": "v",
    },
    "CLI_STATUS_NONE": ("a1",),
    "CLI_STATUS_BLIND": ("m",),
    "CLI_LOOP_USAGE": (),
    "CLI_BRIEF_USAGE": (),
    "CLI_UNKNOWN_VERB": ("v",),
    "CLI_BRIEF_LOOKS_LIKE_ID": ("v",),
    "V_JUDGE_ORDER_REJECTED": ("v", "v"),
    "V_LADDER_INVESTIGATE_GONE": ("rows", "facts", "m", "m"),
    "CLI_STATE_NO_DIR": ("me", "me"),
    "CLI_STATE_USAGE": (),
    "CLI_STATE_NO_BODY": ("x", "p"),
    "V_UNCONFIRMED": ("#1",),
    "V_BROKEN_SCHEDULE": (2, "rows"),
    "GUIDE_HEADER": None,
    "GUIDE_EMPTY": None,
    "GUIDE_TRUNCATED": (3, 12),
    "V_DEFER_EXPIRED": (2, 120, "rows", "", "m"),
    "V_UNJUSTIFIED": (2, 30, "rows", "", "m", "m"),
    "V_CI_WAITING": ("w", 2, "rows"),
    "V_DEFER_AUDIT": (1, "rows", "m"),
    "N_DEFER_AUDIT_OK": (1, "rows"),
    "R_AUDIT_MALFORMED": ("p", "f"),
    "CLI_DEFER_NO_JUSTIFICATION": None,
    "CLI_DEFER_VAGUE_WHY": ("w",),
    "CLI_DEFER_ALREADY_SETTLED": ("f", "r"),
    "CLI_RESERVED_ACTOR": ("m",),
    "DEFER_AUDIT_PROMPT": {"n": 1, "window": 120, "items": "i"},
    "V_LADDER_INVESTIGATE": ("rows", "facts", "m"),
    "V_LADDER_RESOLVE": ("rows", "facts", "m"),
    "N_LADDER_PING": ("rows", "m"),
    "N_JUDGE_STAMP": ("m", "approved"),
    "N_JUDGE_STAMP_FULL": ("m", "approved", "why"),
    "N_OUTQ_MORE": (3,),
    "N_OUTQ_DIGEST": (3, "rows"),
    "N_UNBLOCKED": ("i", "t"),
    "CLI_RELAY_USAGE": None,
    "N_OUTQ_DIGEST_MORE": (3,),
    "N_OUTQ_LADDER_LINE": (2, "#a, #b"),
    "N_ONBOARD_DELIVERED": (17,),
    "N_AGENT_HINT": ("a", "a", "t, t"),
    "N_AGENT_CORPUS_ERR": ("rows",),
    "N_BEHAVIOR_HINT": (1, 12, "heading", "hint-id", "file:CLAUDE.md:1"),
    "N_HINT_CORPUS_ERR": ("rows",),
    "N_HINT_PROPOSALS_PENDING": (3,),
    # (claims, agent, matched terms): the give-up push-back.
    "V_AGENT_PUSHBACK": ("does-not-reproduce", "ops-vms", "ceph, ops, vms"),
    # (claims): the agent-free half of the same conjunction.
    "V_GIVEUP_CLAIM": ("does-not-reproduce",),
    # (matched dismissal text): the deflected-finding check.
    "V_DEFLECTED_FINDING": ("that's pre-existing and unrelated",),
    # (count, threshold_min, rows): the orphan-background-shell sweep.
    "V_BG_ORPHAN": (2, 20, "    pid 123, 45.0 min old: bash\n"),
    "CLI_ITEM_USAGE": None,
    "CLI_TICK_NO_EVIDENCE": ("id",),
    # v16: the triage verb, the tick door gate and the plan-file convention.
    "CLI_TICK_ISSUE_DOOR": ("id",),
    "CLI_TRIAGE_INLINE": {"id": "i", "me": "m", "reason": "r"},
    "CLI_TRIAGE_PLAN": {"id": "i", "me": "m", "reason": "r", "plan": "p", "finding": "f"},
    "CLI_TRIAGE_OPERATOR": {"id": "i", "me": "m", "reason": "r"},
    "CLI_TRIAGE_SELF": {"id": "i", "me": "m", "why": "", "context": "c", "branch": "b"},
    "TRIAGE_PROMPT": {"finding": "f", "context": "c"},
    # v20: the /handoff checklist gate (wl_checklist, agent/programs/<slug>/CHECKLIST.md).
    "V_CL_SHAPE": ("d", "rows"),
    "V_CL_UNREADABLE": ("e",),
    "V_CL_PRODUCING": ("s", 0, 1, "rows", "d"),
    "V_CL_PRODUCING_DONE": ("s", "d"),
    "V_CL_FLIP": ("d", "executing", "rows", "d"),
    "V_CL_WAVES": ("s", "d", "rows"),
    "N_CL_FOREIGN": ("s", "o", ""),
    "N_CL_FOREIGN_DRIFT": ("d", "executing", "o", "rows"),
    "N_CL_FOREIGN_WAVES": ("slug", "d", "o", "rows", "hint"),
    "N_CL_DOOR_PARKED": ("d", 1, "rows"),
    "N_CADENCE_PAUSE": (2, "k", 1, 3, "carried"),
    "N_CADENCE_PAUSE_CARRIED": ("rows",),
    "V_PLAN_DRIFT": (1, "rows"),
    "V_INTENT_EXPIRED": ("t", 1, 1, "cov"),
    # Epics and the published snapshot. USAGE constants carry no placeholder; the rest are single-substitution except CLI_EPIC_MADE/ATTACHED/WROTE.
    "CLI_EPIC_USAGE": None,
    "CLI_EPIC_REFUSED": ("reason",),
    "CLI_EPIC_MADE": ("f2757830", "a title"),
    "CLI_EPIC_ATTACHED": ("f2757830", 3),
    "CLI_PUBLISH_USAGE": None,
    "CLI_PUBLISH_WROTE": ("agent/pr/x.md", 1312, 1),
    "CLI_INTENT_USAGE": None,
    "CTX_CHECKLISTS": ("listing",),
    "CTX_PLANS": ("l",),
    "CTX_PLANS_EXCERPT": ("p", "b"),
    "V_UNCITED": ("x",),
    "V_FOUND_NOT_FIXED": None,
    "V_UNSTATED": ("#1",),
    "V_MISLABELLED": ("x",),
    "V_OUT_OF_SYNC": (1, "#1"),
    "V_SUBMODULE_POINTER": (1, "x"),
    # Printed verbatim by `--help`; no interpolation, so None (skip the % check) rather than an arity. It still has to be REGISTERED, which is the point of the gap check: a constant nobody mapped is a constant nobody rendered.
    "USAGE": None,
    "V_HOOK_BLIND": ("p", "e", "f"),
    "V_NO_REMAINING": ("x",),
    "R_BLOCK": (1, "v", "f"),
    "R_BLOCK_FOCUS": ("v", "m", "f", "me"),
    "R_FOCUS_MORE": (2,),
    "R_FOCUS_ONLY": None,
    "N_CI_QUEUE": ("r", 2, 30, ""),
    "N_CI_QUEUE_PR_STALE_LINE": None,
    "V_BG_REPORT": ("never", "2026-01-01T00:15:00Z", 15, 2, "rows"),
    "V_BG_REPORT_TASKS": ("never", "2026-01-01T00:15:00Z", 15, 2, 1, "tasks", "rows"),
    # v19: runtime caller identity (L1 refusal, L2 backstop, L3 repair).
    "CLI_REASSIGN_USAGE": None,
    "CLI_REASSIGN_ALIVE": ("p", "p"),
    "CLI_REASSIGN_YOUNG": ("p", 5, 30, "p"),
    "CLI_REASSIGN_EMPTY": ("p", "p"),
    "CLI_REASSIGN_DONE": ("p", "m", "i", "m"),
    "N_PHANTOM_IDENTITY": (1, "rows", "p", "m"),
    "N_PHANTOM_BLIND": ("why",),
    "R_JUDGE_UNAVAILABLE": ("e", "f", "m"),
    "R_REGGATE_MALFORMED": ("p", "f"),
    "R_JUDGE_CONTINUE": ("r", "n", "t"),
    "R_REGGATE_BLOCK": ("b", "i", "", "", "m", "t"),
    "R_REGGATE_HALLUCINATED": ("g",),
    "R_REGGATE_ALSO": ("r", "n"),
    # Round-log splice verb (wl_roundlog.py) and the admission detector (wl_admit.py). USAGE and PROMPT carry no placeholders; REFUSED takes (reason, detail) and NO_LOG takes the target path.
    "CLI_ROUNDLOG_USAGE": None,
    "ADMISSION_PROMPT": None,
    "CLI_ROUNDLOG_REFUSED": ("v", "d"),
    "CLI_ROUNDLOG_NO_LOG": ("p",),
    "CTX_SESSION_START": ("s", "d", "l", ""),
    "CTX_SESSION_START_STALE": (3, "s"),
    "CTX_POSTCOMPACT_MISSING": ("p", "m"),
    "CTX_POSTCOMPACT_BRIEFING": ("d", "s", "r", "p", "t"),
    "CTX_POSTCOMPACT_PEERS": ("b",),
    "CTX_POSTCOMPACT_FACTS": ("b", "h", "g"),
    "JUDGE_PROMPT": {
        "streak": 1,
        "remaining": "r",
        "leases": 0,
        "loop": "l",
        "citations": "c",
        "message": "m",
        "traps": "t",
    },
    "REGGATE_PROMPT": {"fixset": "f", "keys": "k"},
    "FIXSET_GROUND_TRUTH": {"count": 1, "files": "f", "more": "", "how": "diff-tree"},
    "V_PLAN_ADOPTED": {"rel": "p", "n_open": 2, "n_gap": 1, "recipes": "r", "me": "m"},
    # ONE HOLE, and deliberately one: every number in the plan-implementation block -- the ceiling, the day, the three ownership buckets, the named box -- is computed by `wl_planenforce.render`, so the catalogue string wraps a body rather than formatting fourteen fields a call site would have to keep in step.
    "V_PLAN_UNIMPLEMENTED": {"body": "b"},
    # v20 plan fidelity (wl_planfid.py). V_PLANFID takes the plan path, the umbrella rows, the untracked-task rows, the judge's instruction, and then the session prefix TWICE (once for the --add exit, once as the owner tag of the deferral line) before the planfid: token.
    "V_PLANFID": ("p", "u", "m", "i", "me", "me", "t"),
    "V_PLANFID_DEGRADED": ("e",),
    # v21 idle-stall gate. V_IDLE_STALL takes the open-item count, the rendered rows, then the session prefix THREE times (one per exit: --tick, --lease, --defer). V_UNBLOCKED_CLAIM takes the count and the claimed lines.
    "V_IDLE_STALL": (1, "rows", "me", "me", "me"),
    "V_UNBLOCKED_CLAIM": (1, "rows"),
    # v23 pending-ask gate. V_PENDING_ASK takes the announcing line then the session prefix (the --defer exit); N_ASK_REFUSALS takes the count and the ledger path.
    "V_PENDING_ASK": ("line", "me"),
    "N_ASK_REFUSALS": (2, "p"),
    # v22. V_DEFERRED_FINDING takes the rendered finding lines; V_SWEEP_MOMENT takes what just closed. Both are single-substitution, and case 117 is what caught them being unregistered: the registry works.
    "V_DEFERRED_FINDING": ("rows",),
    "V_SWEEP_MOMENT": ("an item this turn",),
    "PLANFID_PROMPT": {"plan": "p", "items": "i", "message": "m"},
    # v21 priority ladder. V_PR_FINISH takes the branch, the PR number, the rendered boxes, then the hook path, the session prefix and the PR number for the --add exit, and the hook path and the session prefix for the --tick. R_ALWAYS_COLLAPSED takes
    # the rendered one-line-per-invariant block.
    "V_PR_FINISH": ("b", 543, "rows", "h", "me", 543, "h", "me"),
    "R_ALWAYS_COLLAPSED": ("rows",),
    "R_ROTATING_COLLAPSED": ("rows",),
    # v23 lineage. CLI_ADOPT_USAGE takes nothing (it is a static usage block). CLI_ADOPT_REFUSED takes the session prefix, the predecessor prefix and the reason the evidence failed; CLI_ADOPT_SELF takes the prefix that turned out to be the caller; and CLI_ADOPT_DONE takes the session prefix, the predecessor prefix, the rung that fired, the evidence basis, the boundary uuid, how
    # many items just changed owner, and the session prefix again for the follow-up command.
    "CLI_ADOPT_USAGE": None,
    "CLI_MIGRATE_USAGE": None,
    "CLI_ADOPT_REFUSED": ("me", "prev", "why"),
    # No format args: it is appended to REGGATE_PROMPT verbatim, never % -ed.
    "REGGATE_GATE_MAINTENANCE": None,
    "CLI_ADOPT_SELF": ("prev",),
    "CLI_ADOPT_DONE": ("me", "prev", "continued-in", "1 shared record", "bde8bb05", 3, "me"),
    # W12 plan records (wl_planrec.py). USAGE carries no placeholder; REFUSED takes the RecordError text and DRY takes the rendered record, both single substitutions. WROTE and REVIVED are keyed, and WROTE spends `blob` three times (the git show recipe, the git log recipe, and the message body), which is exactly the arity a positional tuple would get wrong silently.
    "CLI_PLANREC_USAGE": None,
    "CLI_PLANREC_REFUSED": ("why",),
    "CLI_PLANREC_DRY": ("record",),
    "CLI_PLANREC_WROTE": {
        "rel": "p",
        "status": "compacted",
        "bytes": 900,
        "was": 9000,
        "blob": "b",
        "me": "m",
    },
    "CLI_PLANREC_REVIVED": {"rel": "p", "blob": "b", "bytes": 9000},
    # W12 P2. --plan-why has THREE answers and each is its own constant, because "no record names this file" and "there is no index" are different results and collapsing them would make an empty answer indistinguishable from a blind one. NO_EDGE spends `path` twice (the sentence and the git log recipe), which a positional tuple would get wrong silently.
    "CLI_PLANWHY_USAGE": None,
    "CLI_PLANWHY_HIT": {"path": "p", "body": "b"},
    "CLI_PLANWHY_NO_EDGE": {"path": "p", "n": 3, "index": "agent/INDEX.md"},
    "CLI_PLANWHY_NO_INDEX": {"path": "p", "index": "agent/INDEX.md"},
    "CLI_PLANTICK_USAGE": None,
    "CLI_PLANTICK_DRY": {"rel": "p", "note": "n"},
    "CLI_PLANTICK_WROTE": {"rel": "p", "ledger": "l", "investigation": "i", "note": "n", "me": "m"},
    "CLI_PLANINV_USAGE": None,
    "CLI_PLANINV_DRY": {
        "rel": "p",
        "sig": "s",
        "verdict": "v",
        "head": "h",
        "br": "b",
        "table": "t",
    },
    "CLI_PLANINV_WROTE": {
        "rel": "p",
        "sig": "s",
        "verdict": "v",
        "head": "h",
        "br": "b",
        "table": "t",
        "ledger": "l",
        "next": "n",
    },
}


def load_catalogue():
    """`worklist_messages.py` loaded by path, exactly as the bash probe loaded it."""
    path = wlfix.STOP_DIR / "worklist_messages.py"
    spec = importlib.util.spec_from_file_location("wm", path)
    assert spec is not None, path
    assert spec.loader is not None, path
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_117_the_message_catalogue_renders_at_every_call_site_arity():
    """Shape protection for the whole catalogue, including the constants no needle in this suite ever reaches."""
    catalogue = load_catalogue()
    failures = []
    for name, args in ARITY.items():
        value = getattr(catalogue, name, None)
        if value is None:
            failures.append("MISSING %s" % name)
            continue
        if args is None:
            continue
        try:
            value % args
        except (TypeError, ValueError, KeyError, IndexError) as exc:
            # The bash caught bare Exception. These four are what a `%` render can raise: a missing key, too few or mistyped arguments, and an unsupported format character. Anything outside them is a defect this test should surface as an error rather than fold into the tally.
            failures.append("ARITY %s: %s" % (name, exc))
    strings = {
        key
        for key, value in vars(catalogue).items()
        if not key.startswith("_") and isinstance(value, str)
    }
    gap = strings - set(ARITY)
    if gap:
        failures.append("UNMAPPED new constant(s), add arity here: %s" % sorted(gap))
    assert not failures, "catalogue-arity failures=%d: %s" % (len(failures), failures)


def test_118_a_missing_catalogue_fails_closed_and_spares_the_query_modes(wl):  # noqa: F811
    """The import is guarded so a broken worklist_messages.py cannot become the old crash-reads-as-ALLOW hole: message USE raises into the crash handler (block, naming the catalogue), while --path, which uses no messages, keeps working for the scripts that call it."""
    nocat = wl.base / "nocat"
    (nocat / "proj" / ".git").mkdir(parents=True, exist_ok=True)
    (nocat / "tmp").mkdir(parents=True, exist_ok=True)
    hook = nocat / "worklist.py"
    shutil.copy(str(wlfix.HOOK), str(hook))

    env = dict(wl.env)
    env["TMPDIR"] = str(nocat / "tmp")
    env["CLAUDE_PROJECT_DIR"] = str(nocat / "proj")
    got = run_script(hook, ["--path"], env)
    merged = got.out + got.err
    why = "--path broke without the catalogue: rc=%d %r" % (got.rc, merged[:120])
    assert got.rc == 0, why
    assert "claude-worklist" in merged, why

    slug = re.sub(r"[^A-Za-z0-9._-]", "_", str(nocat / "proj")).lstrip("_")
    worklist = nocat / "tmp" / "claude-worklist" / ("%s.md" % slug)
    worklist.parent.mkdir(parents=True, exist_ok=True)
    with worklist.open("a", encoding="utf-8") as handle:
        handle.write("- [ ] (deadbeef) open thing\n")

    stop_env = dict(env)
    stop_env["WORKLIST_TASKS_DIR"] = str(nocat / "tasks")
    stop_env["GITHUB_ACTIONS"] = ""
    payload = json.dumps(
        {
            "session_id": wl.sid,
            "cwd": str(nocat / "proj"),
            "transcript_path": "/none",
            "last_assistant_message": "done",
        }
    )
    blocked = run_script(hook, [], stop_env, stdin=payload)
    assert blocked.decision == "block", "missing catalogue produced decision=%s: %r" % (
        blocked.decision,
        blocked.out[:160],
    )
    assert "worklist_messages" in blocked.out, (
        "the blocking stop did not name the catalogue: %r" % blocked.out[:160]
    )
