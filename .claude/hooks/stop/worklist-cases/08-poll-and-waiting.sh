#!/bin/bash
# Part of the worklist v5 control suite. SOURCED by
# `.claude/hooks/stop/test-worklist-v5.sh`, never run on its own: the harness
# (setup, check, run, the PASS/FAIL counters) lives in `_harness.sh` and every
# fixture path comes from the runner. Running this file directly does nothing
# useful and is not how CI reaches it.
#
# The 5-minute poll shape, waiting-cross-session verification, the silent fast path and its forfeits, and the message catalogue.

echo "== 101. v9: a loop with NO 5-minute poll blocks (the enforced shape) =="
setup
brief_now
hand_now
say "answer

## Remaining
- #7 thing (pending)"
task 7 pending "thing"
CRONS='[{"id":"w","schedule":"17 * * * *"}]'
check "a work cron without the poll cron blocks" block "NOTHING LISTENING FOR CROSS-SESSION MAIL"

echo "== 102. two poll crons block (one is the shape) =="
setup
brief_now
hand_now
say "answer

## Remaining
- #7 thing (pending)"
task 7 pending "thing"
CRONS='[{"id":"w","schedule":"17 * * * *"},{"id":"p1","schedule":"*/5 * * * *"},{"id":"p2","schedule":"*/5 * * * *"}]'
check "a redundant poll cron blocks" block "poll crons"

echo "== 103. the work loop dying BEHIND a surviving poll still fires =="
# The reason cron_memory is work-scoped in v9: a total-count high-water mark
# reads "1 cron live" and misses that the one driving work is gone.
setup
brief_now
hand_now
say "answer

## Remaining
- #7 thing (pending)"
task 7 pending "thing"
CRONS='[{"id":"w","schedule":"17 * * * *"},{"id":"p","schedule":"*/5 * * * *"}]'
run >/dev/null
CRONS='[{"id":"p","schedule":"*/5 * * * *"}]'
check "work loop gone, poll surviving, still fires" block "WORK LOOP DIED"

echo "== 104. CONTROL: poll-only from the START never trips loop-death =="
setup
brief_now
say "all done"
CRONS='[{"id":"p","schedule":"*/5 * * * *"}]'
check "a session that never had a work cron is not nagged" allow ""

echo "== 105. v9: waiting-cross-session with a VERIFIED open ask passes =="
setup
# Same two-class-2-sections shape as case 67: the brief and the open request
# both queue, and one is released per stop by default.
export WORKLIST_REPORT_PER_STOP=9
brief_now
hand_now
brief_other cafe1234
XRID=$(askid deadbeef cafe1234 "who owns caption regen? DEFAULT: I take it")
task 7 pending "caption regen"
say "answer

## Remaining
| #7 | caption regen | waiting-cross-session #$XRID |"
check "a verified open request IS the citation" allow "still OPEN"
unset WORKLIST_REPORT_PER_STOP

echo "== 106. and it exempts the task from I6 under a poll-only cron =="
# The pair for case 92's poll-only block: same crons, but the wait is real
# and verified, and the poll is exactly what delivers the answer. Fresh
# fixture, so cron_memory never saw a work cron here.
setup
brief_now
hand_now
brief_other cafe1234
XRID=$(askid deadbeef cafe1234 "who owns caption regen? DEFAULT: I take it")
task 7 pending "caption regen"
say "answer

## Remaining
| #7 | caption regen | waiting-cross-session #$XRID |"
CRONS='[{"id":"p","schedule":"*/5 * * * *"}]'
check "verified waiting-cross-session + poll cron is a legitimate idle" allow ""

echo "== 107. FIRE: waiting-cross-session with NO request id blocks =="
setup
brief_now
hand_now
task 7 pending "caption regen"
say "answer

## Remaining
| #7 | caption regen | waiting-cross-session on the media session |"
check "the state without a request id is a synonym for blocked" block "names no request id"

echo "== 108. FIRE: someone ELSE'S request does not make it your wait =="
setup
brief_now
hand_now
brief_other cafe1234
# BOTH peers brief, and the second one is not decoration: since v19 --ask
# refuses a recipient that has never briefed here, and this fixture's whole
# premise is that beef9999 is a REAL other session. Without it the ask is
# refused, XRID is empty, and the case degrades into testing an empty citation.
brief_other beef9999
XRID=$(askid_as cafe1234 beef9999 "between two other sessions")
task 7 pending "thing"
say "answer

## Remaining
| #7 | thing | waiting-cross-session #$XRID |"
check "citing a request you did not ask blocks" block "not by you"

echo "== 109. FIRE: an ANSWERED request is a stale wait =="
setup
brief_now
hand_now
brief_other cafe1234
XRID=$(askid deadbeef cafe1234 "please confirm the regen path")
as_peer cafe1234 reqcli --answer cafe1234 "$XRID" "confirmed: regen goes via the media session" >/dev/null
task 7 pending "thing"
say "answer

## Remaining
| #7 | thing | waiting-cross-session #$XRID |"
# FOCUS=off: the ANSWERS delivery check also fires here (the asker has an
# unacked answer), and rotation would rightly surface it first.
export WORKLIST_FOCUS=off
check "an answered id means the wait is over" block "already ANSWERED"
unset WORKLIST_FOCUS

echo "== 110. FIRE: an ESCALATED request is the operator's now =="
setup
brief_now
hand_now
printf '{"ev":"ask","id":"feedc0de","from":"deadbeef","to":"beef9999","at":"%s","body":"republish the caption media"}\n' \
    "$(date -u -d '-120 minutes' +%Y-%m-%dT%H:%M:%SZ)" >>"${WL%.md}.requests"
say "answer

## Remaining
- the republish ask, escalated to the operator as a [?]"
run >/dev/null # this stop escalates feedc0de into an operator [?]
task 7 pending "thing"
newturn
say "answer

## Remaining
| #7 | thing | waiting-cross-session #feedc0de |"
check "an escalated id can no longer justify waiting" block "already ESCALATED"

echo "== 111. THE HEADLINE: a no-op poll stop is SILENT (zero output, exit 0) =="
setup
brief_now
hand_now
echo '- [?] (deadbeef) keep the flag? DEFAULT: keep it' >>"$WL"
say "answer

## Remaining
- the flag decision, deferred with a default"
check "the full stop allows and reports (writes the poll baseline)" allow "operator may answer"
if [[ -f "${WL%.md}.pollbase-deadbeef" ]]; then
    echo "  PASS: the allowed full stop wrote the poll baseline"
    PASS=$((PASS + 1))
else
    echo "  FAIL: no pollbase file after an allowed stop"
    FAIL=$((FAIL + 1))
fi
POLLOUT="$(reqcli --poll deadbeef 2>"$BASE/poll.err")"
RC=$?
if [[ "$RC" -eq 0 && -z "$POLLOUT" && ! -s "$BASE/poll.err" ]]; then
    echo "  PASS: --poll on an empty inbox prints NOTHING and exits 0"
    PASS=$((PASS + 1))
else
    echo "  FAIL: --poll rc=$RC out='${POLLOUT:0:120}' err='$(head -c 120 "$BASE/poll.err")'"
    FAIL=$((FAIL + 1))
fi
OUT="$(run)"
RC=$?
if [[ "$RC" -eq 0 && -z "$OUT" ]]; then
    echo "  PASS: the poll stop is SILENT: exit 0, zero bytes of output"
    PASS=$((PASS + 1))
else
    echo "  FAIL: poll stop rc=$RC out='${OUT:0:160}'"
    FAIL=$((FAIL + 1))
fi
if [[ ! -f "${WL%.md}.pollmark-deadbeef" ]]; then
    echo "  PASS: the marker was CONSUMED (one poll vouches for one stop)"
    PASS=$((PASS + 1))
else
    echo "  FAIL: the poll marker survived the stop"
    FAIL=$((FAIL + 1))
fi
OUT="$(run)"
if [[ -n "$OUT" ]] && grep -qF "operator may answer" <<<"$OUT"; then
    echo "  PASS: CONTROL: without a fresh marker the same world is NOT silent"
    PASS=$((PASS + 1))
else
    echo "  FAIL: an ordinary stop went silent without a poll marker: '${OUT:0:120}'"
    FAIL=$((FAIL + 1))
fi

echo "== 112. the poll DELIVERS: a waiting request forfeits the silence =="
setup
brief_now
hand_now
echo '- [?] (deadbeef) keep the flag? DEFAULT: keep it' >>"$WL"
say "answer

## Remaining
- the flag decision, deferred with a default"
check "baseline stop" allow ""
XRID=$(askid_as cafe1234 deadbeef "please rebuild the docs index")
POLLOUT="$(reqcli --poll deadbeef)"
RC=$?
if [[ "$RC" -eq 0 ]] && grep -qF "INBOX #$XRID" <<<"$POLLOUT" &&
    grep -qF "please rebuild the docs index" <<<"$POLLOUT"; then
    echo "  PASS: --poll prints the full pending payload"
    PASS=$((PASS + 1))
else
    echo "  FAIL: --poll rc=$RC out='${POLLOUT:0:160}'"
    FAIL=$((FAIL + 1))
fi
check "and the stop after it blocks with the delivery, never silently" block "waiting on you"

echo "== 113. ABUSE CONTROL: tracked work forfeits the fast path =="
setup
brief_now
hand_now
echo '- [?] (deadbeef) keep the flag? DEFAULT: keep it' >>"$WL"
say "answer

## Remaining
- the flag decision, deferred with a default"
check "baseline stop" allow ""
task 9 pending "the new thing I quietly started"
reqcli --poll deadbeef >/dev/null
OUT="$(run)"
if [[ -n "$OUT" ]] && grep -qF "OUT OF SYNC" <<<"$OUT"; then
    echo "  PASS: a changed world signature pays the full battery despite the poll"
    PASS=$((PASS + 1))
else
    echo "  FAIL: work slipped through the poll fast path: '${OUT:0:160}'"
    FAIL=$((FAIL + 1))
fi

echo "== 114. the fast path EXPIRES: an old baseline pays the battery again =="
setup
brief_now
hand_now
echo '- [?] (deadbeef) keep the flag? DEFAULT: keep it' >>"$WL"
say "answer

## Remaining
- the flag decision, deferred with a default"
check "baseline stop" allow ""
touch -d '80 minutes ago' "${WL%.md}.pollbase-deadbeef"
reqcli --poll deadbeef >/dev/null
OUT="$(run)"
if [[ -n "$OUT" ]] && grep -qF "operator may answer" <<<"$OUT"; then
    echo "  PASS: past the horizon a poll stop runs the full battery (and re-arms)"
    PASS=$((PASS + 1))
else
    echo "  FAIL: the horizon did not expire the fast path: '${OUT:0:120}'"
    FAIL=$((FAIL + 1))
fi
reqcli --poll deadbeef >/dev/null
OUT="$(run)"
RC=$?
if [[ "$RC" -eq 0 && -z "$OUT" ]]; then
    echo "  PASS: the full stop re-armed the baseline, so the next poll is silent"
    PASS=$((PASS + 1))
else
    echo "  FAIL: the baseline did not re-arm: rc=$RC out='${OUT:0:120}'"
    FAIL=$((FAIL + 1))
fi

echo "== 115. an EXPIRING lease forfeits the silence (the poll notices in 5min) =="
setup
brief_now
hand_now
echo '- [?] (deadbeef) keep the flag? DEFAULT: keep it' >>"$WL"
say "answer

## Remaining
- the flag decision, deferred with a default"
check "baseline stop" allow ""
echo "- [>] (deadbeef) until:$(date -u -d '-5 minutes' +%Y-%m-%dT%H:%MZ) delegated thing" >>"$WL"
reqcli --poll deadbeef >/dev/null
check "an expired lease is a wake-up the poll stop must not sleep through" block "lease expired"

echo "== 116. --poll misuse is refused loudly (a short prefix half-works) =="
setup
if reqcli --poll dead >/dev/null 2>"$BASE/pollmis.err"; then
    echo "  FAIL: a 4-char prefix was accepted (its marker would never match)"
    FAIL=$((FAIL + 1))
elif grep -qF "8-char" "$BASE/pollmis.err"; then
    echo "  PASS: a short prefix is refused with the reason (exit nonzero)"
    PASS=$((PASS + 1))
else
    echo "  FAIL: refusal was silent: $(head -c 120 "$BASE/pollmis.err")"
    FAIL=$((FAIL + 1))
fi

echo "== 117. the message catalogue renders at every call-site arity =="
# Seven catalogue strings have no needle in this suite (V_DIVERGED,
# V_PR_UNREADABLE, V_EVENT_UNPARSEABLE, R_JUDGE_CONTINUE, CLI_REQUEST_USAGE,
# CTX_SESSION_START_STALE, the exempt-overrun stuck detail). This case is
# their shape protection: every constant must exist and render with the
# EXACT argument arity its call site in worklist.py uses, so a placeholder
# added or dropped in the catalogue cannot lurk in a branch no test drives.
OUT=$(
    python3 - "$(dirname "$HOOK")/worklist_messages.py" <<'PYEOF'
import importlib.util, sys
spec = importlib.util.spec_from_file_location("wm", sys.argv[1])
wm = importlib.util.module_from_spec(spec); spec.loader.exec_module(wm)
ARITY = {
    "V_STUCK": ("H", 3, "D"), "V_EVENT_UNPARSEABLE": ("f",),
    "V_OPEN_ITEMS": (1, "x"), "V_UNDEFAULTED": (1, "x"),
    "V_REQUESTS_WAITING": (1, "r", "m", "m"), "V_ANSWERS_UNACKED": ("r", "m"),
    "V_COMPLETION_EVIDENCE": ("a", "b"), "V_COMPLETION_TICKS": ("x",),
    "V_COMPLETION_TASKS": ("x",), "V_IDLE": ("#1",),
    "V_XSESSION_BAD": ("r", "m"), "V_BRIEF": ("s", "", "m"),
    "V_STALE_LOCAL": ("r", 2), "V_DIVERGED": ("r", 2, "r"),
    "V_PR_STALE": ("d",), "V_PR_UNREADABLE": ("d",), "V_LOOP_DIED": (1,),
    "V_CI_RED": ("9", 1, "q", "rows", 2, 1, "m"), "V_CI_UNREADABLE": ("d",),
    # (task-id, the offending command blob) -- see wl_ci.adhoc_watch
    "V_ADHOC_WATCH": ("b1", "blob"),
    "CI_NOTE_RETRYABLE": ("9", 1, "pats", "rows"),
    "CI_NOTE_DOWNGRADED": ("9", 1, 2, "", "rows"),
    # v24 review-red gate (wl_ci.review_red). V_REVIEW_RED takes the PR
    # number, head sha, the check-run's title and summary, then owner/name/pr
    # FOUR times (inline-query, inline-reply, top-level-reply, workflow
    # re-dispatch commands each need their own repo slug), then the block
    # ceiling, the current count, the session prefix, and the PR number again
    # for the --defer exit. REVIEW_NOTE_DOWNGRADED takes the PR, the title,
    # the count, then owner/name/pr for its own re-dispatch command.
    "V_REVIEW_RED": (
        "9", "sha", "t", "s",
        "o", "n", 9, "o", "n", 9, "o", "n", 9, "o", "n", 9,
        2, 1, "me", "9",
    ),
    "REVIEW_NOTE_DOWNGRADED": ("9", "t", 1, "o", "n", "9"),
    "V_REVIEW_UNREADABLE": ("d",),
    "V_NO_POLL_CRON": ("m", "m"), "V_NO_WAITER": (2, "p", "m"),
    "N_WAITER_NUDGE": (2, "p", "m", 60), "V_MANY_WORK_CRONS": (2, "l"),
    # (n waiters, the TaskStop rows, the wl_wait path, me, the fresh timeout)
    "N_WAITER_DRAINED": (1, "rows", "p", "m", 60),
    "V_MANY_POLL_CRONS": (2,),
    "V_AGENT_STATE": ("me", "s", "", 250, 4000, "m"),
    "V_AGENT_BOOTSTRAP": ("me", "me"),
    "V_AGENT_STILL_ABSENT": ("me",),
    "CLI_STATE_REFUSED": ("v", "d", 250, 4000),
    "N_AGENT_PEERS": ("rows",), "CLI_STATE_WHOLE_DOC": ("m",),
    # One substitution: the offending first step, quoted back so the refusal names
    # what it saw rather than restating the rule in the abstract.
    "CLI_STATE_WAIT_LED": ("lead",),
    "V_SOLO_GRIND": (39, 12),
    "N_UNREAD_REPORTS": (2, "b", "rows", "p", "p", "m"),
    "CLI_REAP_USAGE": (), "CLI_REAP_UNKNOWN": ("t", "l"),
    "N_ROSTER_STALE": (20, 1, 19, "p", "m"),
    "CLI_LOOP_USAGE": (), "CLI_BRIEF_USAGE": (), "CLI_UNKNOWN_VERB": ("v",),
    "CLI_BRIEF_LOOKS_LIKE_ID": ("v",),
    "V_JUDGE_ORDER_REJECTED": ("v", "v"),
    "V_LADDER_INVESTIGATE_GONE": ("rows", "facts", "m", "m"),
    "CLI_STATE_NO_DIR": ("me", "me"),
    "CLI_STATE_USAGE": (), "CLI_STATE_NO_BODY": ("x", "p"),
    "V_DOCS_DRIFT": (3, "s", "d"), "V_UNCONFIRMED": ("#1",),
    "V_BROKEN_SCHEDULE": (2, "rows"),
    "GUIDE_HEADER": None, "GUIDE_EMPTY": None, "GUIDE_TRUNCATED": (3, 12),
    "V_DEFER_EXPIRED": (2, 120, "rows", "", "m"),
    "V_UNJUSTIFIED": (2, 30, "rows", "", "m", "m"),
    "V_CI_WAITING": ("w", 2, "rows"),
    "V_DEFER_AUDIT": (1, "rows", "m"),
    "N_DEFER_AUDIT_OK": (1, "rows"),
    "R_AUDIT_MALFORMED": ("p", "f"),
    "CLI_DEFER_NO_JUSTIFICATION": None, "CLI_DEFER_VAGUE_WHY": ("w",),
    "DEFER_AUDIT_PROMPT": {"n": 1, "window": 120, "items": "i"},
    "V_LADDER_INVESTIGATE": ("rows", "facts", "m"),
    "V_LADDER_RESOLVE": ("rows", "facts", "m"),
    "N_LADDER_PING": ("rows", "m"),
    "N_JUDGE_STAMP": ("m", "approved"),
    "N_JUDGE_STAMP_FULL": ("m", "approved", "why"),
    "N_OUTQ_MORE": (3,),
    "N_AGENT_HINT": ("a", "a", "t, t"), "N_AGENT_CORPUS_ERR": ("rows",),
    # (claims, agent, matched terms) -- the give-up push-back.
    "V_AGENT_PUSHBACK": ("does-not-reproduce", "ops-vms", "ceph, ops, vms"),
    "N_POLL_BACKOFF": (25, 5, "*/5 * * * *", "*/10 * * * *", 10),
    "N_POLL_BACKOFF_RESET": ("*/10 * * * *", "*/5 * * * *"),
    "N_QUIET_WAKE": (3, 5, "*/5 * * * *", "*/10 * * * *", 10),
    "N_QUIET_WAKE_CAPPED": (7, 60),
    "CLI_ITEM_USAGE": None, "CLI_TICK_NO_EVIDENCE": ("id",),
    # v16: the triage verb, the tick door gate and the plan-file convention.
    "CLI_TICK_ISSUE_DOOR": ("id",),
    "CLI_TRIAGE_INLINE": {"id": "i", "me": "m", "reason": "r"},
    "CLI_TRIAGE_PLAN": {"id": "i", "me": "m", "reason": "r", "plan": "p",
                        "finding": "f"},
    "CLI_TRIAGE_OPERATOR": {"id": "i", "me": "m", "reason": "r"},
    "CLI_TRIAGE_SELF": {"id": "i", "me": "m", "why": "", "context": "c",
                        "branch": "b"},
    "TRIAGE_PROMPT": {"finding": "f", "context": "c"},
    # v20: the /handoff checklist gate (wl_checklist, agent/programs/<slug>/CHECKLIST.md).
    "V_CL_SHAPE": ("d", "rows"), "V_CL_UNREADABLE": ("e",),
    "V_CL_PRODUCING": ("s", 0, 1, "rows", "d"), "V_CL_PRODUCING_DONE": ("s", "d"),
    "V_CL_FLIP": ("d", "executing", "rows", "d"), "V_CL_WAVES": ("s", "d", "rows"),
    "N_CL_FOREIGN": ("s", "o", ""),
    "N_CL_FOREIGN_DRIFT": ("d", "executing", "o", "rows"),
    "N_CL_FOREIGN_WAVES": ("slug", "d", "o", "rows", "hint"),
    "N_CL_DOOR_PARKED": ("d", 1, "rows"),
    "N_CADENCE_PAUSE": (2, "k", 1, 3, "carried"),
    "N_CADENCE_PAUSE_CARRIED": ("rows",), "V_ASK_NOLISTEN_CMD": ("p", "m"),
    "V_PLAN_DRIFT": (1, "rows"),
    "V_INTENT_EXPIRED": ("t", 1, 1, "cov"),
    # Epics and the published snapshot. USAGE constants carry no placeholder;
    # the rest are single-substitution except CLI_EPIC_MADE/ATTACHED/WROTE.
    "CLI_EPIC_USAGE": None,
    "CLI_EPIC_REFUSED": ("reason",),
    "CLI_EPIC_MADE": ("f2757830", "a title"),
    "CLI_EPIC_ATTACHED": ("f2757830", 3),
    "CLI_PUBLISH_USAGE": None,
    "CLI_PUBLISH_WROTE": ("agent/pr/x.md", 1312, 1),
    "CLI_INTENT_USAGE": None,
    "CTX_CHECKLISTS": ("listing",),
    "CTX_PLANS": ("l",), "CTX_PLANS_EXCERPT": ("p", "b"),
    "V_UNCITED": ("x",), "V_FOUND_NOT_FIXED": None, "V_UNSTATED": ("#1",),
    "V_MISLABELLED": ("x",), "V_OUT_OF_SYNC": (1, "#1"),
    "V_SUBMODULE_POINTER": (1, "x"),
    # Printed verbatim by `--help`; no interpolation, so None (skip the % check)
    # rather than an arity. It still has to be REGISTERED, which is the point of
    # the gap check below: a constant nobody mapped is a constant nobody rendered.
    "USAGE": None,
    "V_HOOK_BLIND": ("p", "e", "f"), "V_NO_REMAINING": ("x",),
    "R_BLOCK": (1, "v", "f"), "R_BLOCK_FOCUS": ("v", "m", "f"),
    "R_FOCUS_MORE": (2,), "R_FOCUS_ONLY": None,
    "N_CI_QUEUE": ("r", 2, 30, ""), "N_CI_QUEUE_PR_STALE_LINE": None,
    "V_BG_REPORT": ("never", "2026-01-01T00:15:00Z", 15, 2, "rows"),
    "V_BG_REPORT_TASKS": ("never", "2026-01-01T00:15:00Z", 15, 2, 1, "tasks", "rows"),
    "CLI_ASK_OPERATOR_NO_DEFAULT": None,
    "CLI_ASK_UNKNOWN_RECIPIENT": ("to", "a, b"),
    # v19: runtime caller identity (L1 refusal, L2 backstop, L3 repair).
    "CLI_REASSIGN_USAGE": None, "CLI_REASSIGN_ALIVE": ("p", "p"),
    "CLI_REASSIGN_YOUNG": ("p", 5, 30, "p"), "CLI_REASSIGN_EMPTY": ("p", "p"),
    "CLI_REASSIGN_DONE": ("p", "m", "i", "r", "m", "m"),
    "N_PHANTOM_IDENTITY": (1, "rows", "p", "m"), "N_PHANTOM_BLIND": ("why",),
    "R_JUDGE_UNAVAILABLE": ("e", "f", "m"),
    "R_REGGATE_MALFORMED": ("p", "f"), "R_JUDGE_CONTINUE": ("r", "n", "t"),
    "R_REGGATE_BLOCK": ("b", "i", "", "", "m", "t"),
    "R_REGGATE_HALLUCINATED": ("g",), "CLI_REQUEST_USAGE": None,
    # Round-log splice verb (wl_roundlog.py) and the admission detector
    # (wl_admit.py). USAGE and PROMPT carry no placeholders; REFUSED takes
    # (reason, detail) and NO_LOG takes the target path.
    "CLI_ROUNDLOG_USAGE": None, "ADMISSION_PROMPT": None,
    "CLI_ROUNDLOG_REFUSED": ("v", "d"), "CLI_ROUNDLOG_NO_LOG": ("p",),
    "CLI_BODY_REFUSED": ("b", 1200, 1000), "CTX_SESSION_START": ("s", "d", "l", ""),
    "CTX_SESSION_START_STALE": (3, "s"),
    "CTX_POSTCOMPACT_MISSING": ("p", "m"),
    "CTX_POSTCOMPACT_BRIEFING": ("d", "s", "r", "p", "t"),
    "CTX_POSTCOMPACT_PEERS": ("b",),
    "JUDGE_PROMPT": {"streak": 1, "remaining": "r", "leases": 0, "loop": "l",
                     "citations": "c", "message": "m", "traps": "t"},
    "REGGATE_PROMPT": {"fixset": "f", "keys": "k"},
    # v20 plan fidelity (wl_planfid.py). V_PLANFID takes the plan path, the
    # umbrella rows, the untracked-task rows, the judge's instruction, and then
    # the session prefix TWICE (once for the --add exit, once as the owner tag
    # of the deferral line) before the planfid: token.
    "V_PLANFID": ("p", "u", "m", "i", "me", "me", "t"),
    "V_PLANFID_DEGRADED": ("e",),
    # v21 idle-stall gate. V_IDLE_STALL takes the open-item count, the rendered
    # rows, then the session prefix THREE times (one per exit: --tick, --lease,
    # --defer). V_UNBLOCKED_CLAIM takes the count and the claimed lines.
    "V_IDLE_STALL": (1, "rows", "me", "me", "me"),
    "V_UNBLOCKED_CLAIM": (1, "rows"),
    # v23 pending-ask gate. V_PENDING_ASK takes the announcing line then the
    # session prefix (the --defer exit); N_ASK_REFUSALS takes the count and the
    # ledger path.
    "V_PENDING_ASK": ("line", "me"),
    "N_ASK_REFUSALS": (2, "p"),
    # v22. V_DEFERRED_FINDING takes the rendered finding lines; V_SWEEP_MOMENT
    # takes what just closed. Both are single-substitution, and case 117 is
    # what caught them being unregistered -- the registry works.
    "V_DEFERRED_FINDING": ("rows",),
    "V_SWEEP_MOMENT": ("an item this turn",),
    "PLANFID_PROMPT": {"plan": "p", "items": "i", "message": "m"},
    # v21 priority ladder. V_WAITER_LAPSED takes which exit the waiter took, how
    # many minutes ago, the live-peer count, the wl_wait path and the session
    # prefix. V_PR_FINISH takes the branch, the PR number, the rendered boxes,
    # then hook/me/PR-number for the --add exit and hook/me for the --tick.
    # R_ALWAYS_COLLAPSED takes the rendered one-line-per-invariant block.
    "V_WAITER_LAPSED": ("timeout", 12, 2, "p", "me"),
    "V_PR_FINISH": ("b", 543, "rows", "h", "me", 543, "h", "me"),
    "R_ALWAYS_COLLAPSED": ("rows",),
    # v23 lineage. CLI_ADOPT_USAGE takes nothing (it is a static usage block).
    # CLI_ADOPT_REFUSED takes me, prev and the reason the evidence failed;
    # CLI_ADOPT_SELF takes the prefix that turned out to be the caller; and
    # CLI_ADOPT_DONE takes me, prev, the rung that fired, the evidence basis,
    # the boundary uuid, how many items just became mine, and me again for the
    # follow-up command.
    "CLI_ADOPT_USAGE": None,
    "CLI_MIGRATE_USAGE": None,
    "CLI_ADOPT_REFUSED": ("me", "prev", "why"),
    # No format args: it is appended to REGGATE_PROMPT verbatim, never % -ed.
    "REGGATE_GATE_MAINTENANCE": None,
    "CLI_ADOPT_SELF": ("prev",),
    "CLI_ADOPT_DONE": ("me", "prev", "continued-in", "1 shared record", "bde8bb05", 3, "me"),
}
fail = 0
for name, args in ARITY.items():
    val = getattr(wm, name, None)
    if val is None:
        print("MISSING %s" % name); fail += 1; continue
    if args is None:
        continue
    try:
        _ = val % args
    except Exception as exc:
        print("ARITY %s: %s" % (name, exc)); fail += 1
strs = {k for k, v in vars(wm).items()
        if not k.startswith("_") and isinstance(v, str)}
gap = strs - set(ARITY)
if gap:
    print("UNMAPPED new constant(s), add arity here: %s" % sorted(gap)); fail += 1
print("catalogue-arity failures=%d" % fail)
sys.exit(1 if fail else 0)
PYEOF
)
RC=$?
if [[ "$RC" -eq 0 ]]; then
    echo "  PASS: every catalogue constant renders at its call-site arity"
    PASS=$((PASS + 1))
else
    echo "  FAIL: $OUT"
    FAIL=$((FAIL + 1))
fi

echo "== 118. a MISSING catalogue fails CLOSED and spares the query modes =="
# The import is guarded so a broken worklist_messages.py cannot become the
# old crash-reads-as-ALLOW hole: message USE raises into the crash handler
# (block, naming the catalogue), while --path, which uses no messages,
# keeps working for the scripts that call it.
mkdir -p "$BASE/nocat/proj/.git" "$BASE/nocat/tmp"
cp "$HOOK" "$BASE/nocat/worklist.py"
OUT=$(TMPDIR="$BASE/nocat/tmp" CLAUDE_PROJECT_DIR="$BASE/nocat/proj" python3 "$BASE/nocat/worklist.py" --path 2>&1)
RC=$?
if [[ "$RC" -eq 0 && "$OUT" == *"claude-worklist"* ]]; then
    echo "  PASS: --path works without the catalogue"
    PASS=$((PASS + 1))
else
    echo "  FAIL: --path broke without the catalogue: rc=$RC ${OUT:0:120}"
    FAIL=$((FAIL + 1))
fi
NWL="$BASE/nocat/tmp/claude-worklist/$(echo "$BASE/nocat/proj" | sed 's|[^A-Za-z0-9._-]|_|g' | sed 's/^_//').md"
echo '- [ ] (deadbeef) open thing' >>"$NWL"
OUT=$(printf '{"session_id":"%s","cwd":"%s","transcript_path":"/none","last_assistant_message":"done"}' "$SID" "$BASE/nocat/proj" |
    TMPDIR="$BASE/nocat/tmp" CLAUDE_PROJECT_DIR="$BASE/nocat/proj" WORKLIST_TASKS_DIR="$BASE/nocat/tasks" \
        GITHUB_ACTIONS="" python3 "$BASE/nocat/worklist.py" 2>/dev/null)
GOT=$(python3 -c 'import json,sys
raw=sys.stdin.read().strip()
print(json.loads(raw).get("decision","allow") if raw else "allow")' <<<"$OUT" 2>/dev/null)
if [[ "$GOT" == "block" ]] && grep -qF "worklist_messages" <<<"$OUT"; then
    echo "  PASS: a blocking stop without the catalogue BLOCKS naming it"
    PASS=$((PASS + 1))
else
    echo "  FAIL: missing catalogue produced decision=$GOT: ${OUT:0:160}"
    FAIL=$((FAIL + 1))
fi
