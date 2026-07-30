"""Message catalogue for worklist.py, the Stop hook.

WHY THIS FILE EXISTS (operator request, 2026-07-30): worklist.py had grown
past 3300 lines and a large share of that was user-facing prose -- violation
texts, block reasons, the judge prompts. A future session must be able to
load and reason about the LOGIC without spending its context on prose it
will not change, so the prose lives here and the logic imports it.

THE CONTRACT, deliberately boring:
  - Named %-format template constants ONLY. No logic, no functions, no
    lookup indirection, no templating layer: a message you cannot grep from
    the code that emits it is worse than a long file. Grep for a phrase
    lands HERE; the constant's name links straight to its single call site
    in worklist.py.
  - Text is VERBATIM from where it lived in worklist.py. The test suite's
    needle assertions pin most of these strings; a reworded message is a
    behavior change, not a cleanup.
  - WHY comments stay in worklist.py next to the code they explain. This
    file carries only what the SESSION reads, never why the check exists.
  - Placeholder arity is part of the contract: every constant is rendered
    with a fixed tuple at exactly one call site, and the suite exercises
    the render for the pinned ones. Change a %s count here and its call
    site in the same edit.

WHAT IS DELIBERATELY NOT HERE:
  - The crash-handler block text and the import-failure text in
    worklist.py. Those must work when THIS file is missing or broken, so
    they cannot live in it.
  - Short one-line formats entangled with control flow (CLI die() one
    liners, systemMessage part headers, xsession_ok reason returns). Moving
    a two-line string behind a name saves nothing and costs a hop.

FAILURE MODE (decided, not accidental): worklist.py imports this module
inside a try/except. On ImportError or any load-time breakage it installs a
shim whose every attribute access raises, so query modes that use no
messages (--path, --brief, --poll on an empty inbox) keep working, while the
first message USE on the Stop path raises and is caught by the __main__
crash handler, which BLOCKS with the traceback. A broken catalogue therefore
fails closed and names itself; it can never fail open (a top-level crash
used to read as ALLOW) and never wedges the path-query plumbing.
"""

# ---- stop-path violations (the block body, one constant per check) ---------

V_STUCK = (
    "%s IN %d CONSECUTIVE STOPS, so whatever you are doing is not working and a "
    "fourth attempt of the same shape will not fix it. EMPLOY A PLANNING OR "
    "INVESTIGATION AGENT NOW (Agent tool, subagent_type Plan or Explore, or "
    "general-purpose), give it the problem and the evidence you already have, and "
    "let it come back with an approach you have not tried. This is the operator's "
    "standing rule: if it cannot be solved in three rounds, delegate it rather "
    "than repeating yourself. If you genuinely disagree, say WHY in one sentence "
    "and what will be different next round.\n    %s"
)
STUCK_HEADLINES = {
    "tasks-only": "NO TASK HAS CHANGED STATUS",
    "tasks+head": "NOTHING HAS MOVED",
    "exempt-overrun": "NO TASK HAS CHANGED STATUS",
}
STUCK_DETAILS = {
    "tasks-only": "(no task has changed status in that time. Commits do "
    "not count as movement here, deliberately: committing trivia while "
    "the real problem sits untouched is the pattern this catches.)",
    "tasks+head": "(no task changed status and HEAD did not advance. "
    "Starting a background agent clears this.)",
    "exempt-overrun": "(a background task IS running and has been for "
    "many stops, so the remedy itself has stalled. Check what it is "
    "doing, or stop it and take a different approach.)",
}

V_EVENT_UNPARSEABLE = (
    "THIS IS A HOOK BUG: the Stop event on stdin was not parseable JSON, so every "
    "check below ran against an EMPTY event and its advice is meaningless. Fix the "
    "caller or %s rather than acting on anything else this block says."
)

V_OPEN_ITEMS = (
    "%d OPEN worklist item(s). Do the next one, or move it to [?]/[>] with the "
    "state that actually applies:\n%s"
)

V_UNDEFAULTED = (
    "%d deferred item(s) carry no DEFAULT:. A '- [?]' without a default is a "
    "note, not a decision. Append 'DEFAULT: <what you will do if the operator "
    "does not answer>' to each, then execute the default next turn:\n%s"
)

V_REQUESTS_WAITING = (
    "%d cross-session REQUEST(S) are waiting on you. The asker cannot see your "
    "context, so silence is a black hole: do it or answer with what you know, or "
    "decline with a real reason. A broadcast wants whoever owns the area; if that "
    "is not you, declining 'not my area: <why>' releases you:\n%s\n"
    "    .claude/hooks/stop/worklist.py --answer %s <id> '<what you did or know>'\n"
    "    .claude/hooks/stop/worklist.py --decline %s <id> '<why not>'"
)

V_ANSWERS_UNACKED = (
    "your request(s) were ANSWERED and the answer is unacknowledged. This block IS "
    "the delivery (the block reason is the only channel you actually read): act on "
    "each answer now -- a decline means route around it or raise a [?] to the "
    "operator -- then acknowledge so it never blocks you again:\n%s\n"
    "    .claude/hooks/stop/worklist.py --ack %s <id>"
)

V_COMPLETION_EVIDENCE = (
    "COMPLETION WITHOUT EVIDENCE. S-2 was marked completed on another spike's "
    "evidence, nothing recorded a result anywhere, and the hole surfaced hours "
    "later. A completion must leave a record: a sha, a run id, a file:line, an "
    "exit code, or a URL. You have it in hand at completion time, so this costs "
    "one paste; if you do NOT have it, the item is not done.\n%s%s"
    "    For ticks, put the evidence IN THE LINE (it is the durable record). "
    "For tasks, put it on the line mentioning the #id in your message."
)
V_COMPLETION_TICKS = "  tick(s) with no evidence in the line:\n%s\n"
V_COMPLETION_TASKS = "  task(s) flipped to completed with no evidence near their #id:\n%s\n"

V_IDLE = (
    "NOTHING WILL WAKE THIS SESSION. Task(s) %s wait, yet no background task is "
    "running, no [>] lease is fresh, and no work cron is scheduled (the "
    "5-minute inbox poll does not count: it only reacts to other sessions), "
    "so after this stop the work sits until the operator notices -- the Wave "
    "C shape, where no third stop ever came and the stuck counter never had "
    "a chance to fire. Give the work a wake-up before stopping: start it "
    "now, delegate it (a background agent plus a [>] lease), schedule the "
    "loop (CronCreate, then declare it with --loop), or if a task truly "
    "waits on the operator, ask with AskUserQuestion and record it as "
    "'You (User Thinks So)'."
)

V_XSESSION_BAD = (
    "'waiting-cross-session' must cite an OPEN request YOU asked, or it is "
    "just a synonym for blocked wearing a checkable-looking name:\n%s\n"
    "Post the ask and put its #id on the Remaining line:\n"
    "    .claude/hooks/stop/worklist.py --ask %s <recipient|*> '<what you "
    "need> DEFAULT: <what you do if unanswered>'\n"
    "or change the state word to one that is true."
)

V_BRIEF = (
    "session brief is %s%s. Other sessions share this worktree and cannot see "
    "what you are doing. Run:\n"
    "    .claude/hooks/stop/worklist.py --brief %s '<=200 chars: what you are "
    "changing right now>'"
)

V_STALE_LOCAL = (
    "a LOCAL branch %s is %d commits behind the ref you publish to, and nothing in "
    "your workflow touches it. It is a trap for whoever checks it out next: they "
    "would work from a stale base and could push over live work. Delete it if it "
    "carries no unique commits, or say why it is being kept."
)

V_DIVERGED = (
    "%s HAS %d COMMIT(S) YOU DO NOT HAVE. You commit on a local branch and publish "
    "to a different one, so that ref can move without you. Fetch and inspect before "
    "your next push, because pushing now either fails or publishes over work nobody "
    "has looked at:\n    git fetch origin && git log --oneline HEAD..%s"
)

V_PR_STALE = (
    "YOU PUSHED AFTER YOUR LAST PR-DESCRIPTION EDIT (%s). CI's freshness gate will "
    "fail on this, and that red costs a full round for a ten-second fix. The body "
    "refresh is part of the push, not a step after it. Refresh it now, and verify "
    "with the GraphQL read because `gh pr view --json lastEditedAt` is not a valid "
    "field."
)

V_PR_UNREADABLE = (
    "THIS IS A HOOK BUG: the PR-freshness lookup failed (%s), so that check is "
    "blind. It blocks rather than passing quietly, per no-escape-hatch."
)

V_CI_RED = """CI IS RED ON PR #%s AND NOTHING IS WATCHING IT. %d job(s) failed for real
%s
%s

READ THE LOG BEFORE YOU GUESS. `gh run view --log-failed` is RUN-scoped even with
--job: it refuses while the run is in progress, exits 1, and writes the reason to
stderr, so a 2>/dev/null capture looks like an empty log. Use the per-job endpoint
above, which works on a completed job inside a live run.

Then brief a sub-agent with the job name, the failing step and the log excerpt
(Agent tool, subagent_type general-purpose) and have it come back with a fix
rather than a theory. Investigation parallelises; do not read 95 jobs yourself.

THIS CANNOT TRAP YOU: it blocks at most %d consecutive stop(s) per failure set
(this is %d), then downgrades to a report for that set forever. To clear it now,
push the fix, or name the failing job in your stop message, or -- if it is not
yours to fix -- file
    - [?] (%s) CI: <job> red, <one-line reason>  DEFAULT: <what happens if nobody acts>"""

V_CI_UNREADABLE = (
    "THIS IS A HOOK BUG: the PR CI-status lookup failed (%s), so that check is "
    "blind. It blocks rather than passing quietly, per no-escape-hatch. If `gh` "
    "is simply not authenticated here, unset WORKLIST_PUBLISH_REF to opt out of "
    "the check entirely rather than leaving it half-blind."
)

CI_NOTE_RETRYABLE = """CI on PR #%s: %d job(s) failed, but every one of them is on the watchdog's
retry allowlist (%s) and the run is still live, so a rerun may already be
inbound. Reported, NOT blocked on: investigating a leg the watchdog is about to
rerun costs a round for nothing. If they are still red once the run is final,
this will say so.
%s"""

CI_NOTE_DOWNGRADED = """CI on PR #%s is still red (%d job(s)) and this has already been raised %d
time(s) for this failure set%s, so it will not block again for this set. It is
still red and still yours to decide about:
%s"""

V_LOOP_DIED = (
    "YOUR WORK LOOP DIED. This session had %d work cron(s) and now has none "
    "(the 5-minute inbox poll does not count: it only reacts to other "
    "sessions), so nothing will drive the work forward again. That is the "
    "failure this check exists for. Recreate it with CronCreate, or say out "
    "loud in your message that the loop is deliberately finished."
)

V_NO_POLL_CRON = (
    "THIS SESSION HAS A LOOP BUT NO 5-MINUTE INBOX POLL. Cross-session "
    "requests land between your stops, and an hourly loop makes the asker "
    "wait up to an hour for what costs you seconds. Create the second cron "
    "now (two crons is the required shape):\n"
    "    CronCreate with schedule '*/5 * * * *' and a prompt that runs\n"
    "        .claude/hooks/stop/worklist.py --poll %s\n"
    "    and, if it prints NOTHING, stops immediately with no summary and "
    "no commentary; if it prints requests, acts on them.\n"
    "The stop after an empty poll is silent and near-free (the hook "
    "verifies the no-op itself), so the cadence costs almost nothing."
)

V_MANY_WORK_CRONS = (
    "%d work crons are live on this session: %s. ONE work loop plus the "
    "5-minute inbox poll is the required shape; a second work schedule fires "
    "the same review twice at different phases and each firing costs a turn. "
    "Delete the redundant one with CronDelete."
)

V_MANY_POLL_CRONS = (
    "%d poll crons (*/5 * * * *) are live; one is the shape. Delete the "
    "extra with CronDelete."
)

V_HANDOVER = (
    "the compact-recovery handover is %s%s. Compaction has already cost this "
    "project one operator decision (the autopilot App was reported blocked "
    "AFTER the operator had created it), and the transcript cannot be the "
    "recovery mechanism because the transcript is what gets summarised. "
    "Rewrite it as %d-%d characters (at most 3 paragraphs), addressed to a "
    "session that knows NOTHING: what this work is, where it stands, what to "
    "do next, and any fact that must not be re-litigated. No headings, no "
    "bullet lists. It is a handoff prompt, not a status report. Stale means "
    "the WORLD has moved since it was written; an unchanged world never "
    "stales it:\n"
    "    .claude/hooks/stop/worklist.py --handover %s <<'EOF'\n    ...\n    EOF"
)

V_DOCS_DRIFT = (
    "the design docs have DRIFTED: %d commits have touched %s since %s was last "
    "updated. Those documents are how a new or compacted session understands this "
    "work, so code moving without them deletes the next session's starting "
    "context. Update the ones your changes invalidated, in this turn."
)

V_UNCONFIRMED = (
    "%s marked blocked on the operator WITHOUT their confirmation. You cannot "
    "declare someone else blocked: ask with AskUserQuestion, giving concrete "
    "options plus the do-it-anyway option, and only then write it as "
    "'You (User Thinks So)'. Until they answer, it is blocked on YOU."
)

V_UNCITED = (
    "a blocker is a CLAIM ABOUT REALITY and these carry no source:\n%s\n"
    "This is the Wave C failure exactly: the report said 'blocked on Wave B "
    "landing' while 05-execution-guide.md:108 said it lands with every stage "
    "flag off, and nothing challenged it because the SHAPE was valid and only "
    "the CONTENT was wrong. Cite the line that blocks you as <path>:<line>, or "
    "if you cannot find one, that is your answer: it is not blocked, so go do "
    "it. Waiting on something real (a run, an agent) belongs in a [>] lease or "
    "a background task instead, which this check already exempts."
)

V_FOUND_NOT_FIXED = (
    "your message carries a 'found, not fixed' list. CLAUDE.md's rule is to FIX "
    "what you find: reporting it is the fallback, not the default. For each item, "
    "either fix it now and say you did, or record it as '- [?] ... DEFAULT: <what "
    "you will do if unanswered>' so it is tracked and time-boxed rather than "
    "restated every turn. Then drop the phrase."
)

V_UNSTATED = (
    "%s listed without a STATE. Every remaining item must say whether it is "
    "ongoing, pending or blocked, because 'who it is blocked on' does not tell "
    "the operator what is actually moving. Add the word to each line."
)

V_MISLABELLED = (
    "your Remaining section DISAGREES with the task list the operator sees: %s. "
    "Either fix the wording or move the task with TaskUpdate, so the two match."
)

V_OUT_OF_SYNC = (
    "your Remaining section is OUT OF SYNC with the task list the operator sees. "
    "%d open task(s) are not mentioned by id: %s. List every open task, or close "
    "the ones that are done."
)

V_HOOK_BLIND = (
    "THIS IS A HOOK BUG, not something you did wrong: no assistant text could be "
    "read from the transcript (path=%r), so the '## Remaining' check is BLIND. "
    "It blocks rather than waving you through, per no-escape-hatch. Inspect the "
    "captured event at %s and fix transcript_tail in %s."
)

V_NO_REMAINING = (
    "work remains and your last message has no '## Remaining' section. The "
    "operator reads YOUR message, not this hook's output, so a report that "
    "lives only here does not exist. Re-state the answer and end it with a "
    "'## Remaining' section listing what is left and who it is blocked on:\n%s"
)

# ---- v10: autonomy window and the liveness ladder ---------------------------

V_DEFER_EXPIRED = (
    "%d deferred item(s) have OUTLIVED their autonomy window (%d min). A "
    "DEFAULT: is time-boxed autonomy, not a parking bay: the operator almost "
    "always takes the recommended action, so once the window closes the "
    "recommendation IS the decision. EXECUTE each default now and tick the "
    "item with evidence; if the operator has since answered, act on their "
    "answer instead; if executing is genuinely wrong now, ask with "
    "AskUserQuestion and refresh the item so the window restarts:\n%s\n%s"
    "    .claude/hooks/stop/worklist.py --tick %s <id> '<evidence>'"
)

V_LADDER_INVESTIGATE = (
    "IN-FLIGHT WORK HAS GONE QUIET (90-minute rung, fires once per item until "
    "it moves). An 'ongoing' that nothing has touched for this long is how "
    "stale claims outlive their workers. INVESTIGATE each one now: read the "
    "worker's output, then either refresh the item with one line of evidence "
    "(--update <id> '<what moved>'), restart or replace the worker and "
    "re-lease, or reclassify the item to the state that is actually true:\n%s\n"
    "  What the OS could verify about your background workers:\n%s\n"
    "    .claude/hooks/stop/worklist.py --update %s <id> '<what moved>'"
)

V_LADDER_RESOLVE = (
    "IN-FLIGHT WORK HAS BEEN QUIET FOR TWO HOURS (top rung, fires once per "
    "item until it moves). Waiting harder is not a plan; pick a TERMINAL "
    "action for each, this turn: stop the worker and re-delegate (TaskStop, "
    "then a fresh agent plus a new --lease), do the work inline now, or "
    "defer it to the operator as a [?] with a DEFAULT (always available, so "
    "this rung can never trap you):\n%s\n"
    "  What the OS could verify about your background workers:\n%s\n"
    "    .claude/hooks/stop/worklist.py --defer %s <id> '<question> DEFAULT: <action>'"
)

N_LADDER_PING = (
    "Liveness ping (45-minute rung, report-only): these in-flight subjects "
    "have not moved lately. Verify each worker is really progressing, and "
    "when it is, refresh the item:\n%s\n"
    "    .claude/hooks/stop/worklist.py --update %s <id> '<one line of what moved>'\n"
    "(this becomes a block at 90 minutes; --update resets the clock)"
)

# ---- block-reason wrappers (the `reason` field of an emitted block) ---------

R_BLOCK = (
    "Do not stop yet. %d check(s) failed:\n\n%s\n\n"
    "Fix all of them in this turn, then stop. There is no block cap: a "
    "check that fires wrongly is a bug in %s and you are the session that "
    "fixes it."
)

R_JUDGE_UNAVAILABLE = (
    "The stop-gate judge could not answer: %s\n\n"
    "This is a BUG in the gate, and blocking is deliberate: a judge that "
    "fails open is an escape hatch. You are the primary session, so fix "
    "it now in %s. Diagnose with:\n"
    "    STOPHOOK_CHILD= claude -p 'reply OK' --output-format json "
    "--model %s\n"
    "If the model is simply unreachable and you have verified that, set "
    "WORKLIST_JUDGE=off in the hook env and say so out loud in your "
    "summary, so a disabled gate is never silent."
)

R_REGGATE_MALFORMED = (
    "A fix landed this turn and the judge's answer "
    "carried no usable regression_gate object (%s). This is a "
    "judge error and it FAILS CLOSED, same as an invalid "
    "verdict: a gate that cannot ask its question must not "
    "become the way past it. Fix the judge path in %s, or set "
    "WORKLIST_JUDGE=off and say so out loud."
)

R_JUDGE_CONTINUE = (
    "The stop-gate judge says this stop is not legitimate.\n\n"
    "  reason:      %s\n  next action: %s\n\n"
    "Tracked work:\n%s\n\nDo the next action, then stop."
)

R_REGGATE_BLOCK = (
    "A FIX LANDED AND NO REGRESSION GATE PROTECTS IT. This is the i18n "
    "lesson: the defect was fixed by hand and nothing prevented its "
    "return, because every existing gate was blind to it by construction.\n\n"
    "  judge's blind spot:  %s\n"
    "  judge's instruction: %s\n%s%s\n"
    "Three exits, pick one THIS turn:\n"
    "  1. WRITE THE GATE control-first: a new scripts/check-*.ts or "
    ".ci/scripts/quality/check-*.sh, wired as a check:ci-* key REACHABLE "
    "from `npm run ci` (transitively; defined-but-never-run does not "
    "count). The next stop runs it bounded, and a green run IS the "
    "planted-defect proof, because a control-first gate self-fails when "
    "its own control cannot fire.\n"
    "  2. DEFER to the operator: append to the worklist\n"
    "     - [?] (%s) %s <should this be gated?> DEFAULT: <what you do if "
    "unanswered>\n"
    "     and the deferral machinery prints it to them every stop.\n"
    "  3. REBUT in your message: say why it is not applicable, already "
    "covered (name the REAL key), or a one-off; the judge re-reads your "
    "message next stop."
)

R_REGGATE_HALLUCINATED = (
    "  you cited %r as existing coverage but no such check:* key "
    "exists, so that coverage is HALLUCINATED and counts as none.\n"
)

# ---- CLI texts (request_cli) ------------------------------------------------

CLI_REQUEST_USAGE = (
    "usage: --ask <my-prefix> <to-prefix|*> <text...>\n"
    "       --answer <my-prefix> <id> <text...>\n"
    "       --decline <my-prefix> <id> <reason...>\n"
    "       --ack <my-prefix> <id>"
)

CLI_BODY_REFUSED = (
    "%s is %d chars, limit %d. REFUSED rather than silently truncated: "
    "the tail is often the crucial part, and a clipped payload that "
    "reports success is how findings get lost. Shorten it, or put the "
    "detail in a file and cite the path."
)

CLI_ITEM_USAGE = (
    "usage: --add <my-prefix> <text...>\n"
    "       --tick <my-prefix> <id> <evidence...>   (a sha, run id, file:line, exit code or URL)\n"
    "       --defer <my-prefix> <id> <question... DEFAULT: <action>>\n"
    "       --lease <my-prefix> <id> <+minutes|until-ISO8601Z> worker:<bg-task-id> [note...]\n"
    "       --update <my-prefix> <id> <what moved...>\n"
    "       --list"
)

CLI_TICK_NO_EVIDENCE = (
    "REFUSED: ticking #%s needs evidence in the line (a real sha, a run id, "
    "a file:line that resolves, an exit code, or a URL). You have it in hand "
    "at completion time, so this costs one paste; if you do NOT have it, the "
    "item is not done."
)

# ---- SessionStart / PostCompact additionalContext ---------------------------

CTX_SESSION_START = (
    "This project keeps its design in %s, and those documents are the "
    "starting context for the work. READ ALL OF THEM before acting: "
    "they carry decisions you must not re-litigate and constraints "
    "that are invisible in the code.\n%s\n\n"
    "They are also YOURS TO MAINTAIN. When you change what the program "
    "does, update the document describing it in the SAME turn.%s"
)

CTX_SESSION_START_STALE = (
    "\n\nRIGHT NOW THEY ARE STALE: %d commits have touched %s since the docs "
    "were last updated. Reconcile them early, not at the end."
)

CTX_POSTCOMPACT_MISSING = (
    "CONTEXT WAS JUST COMPACTED and there is NO handover document at %s.\n"
    "Reconstruct one from what survived, write it with\n"
    "    .claude/hooks/stop/worklist.py --handover %s <<'EOF' ... EOF\n"
    "and do NOT report anything as blocked-on-operator until you have "
    "re-checked it: that is exactly the error compaction caused last time."
)

CTX_POSTCOMPACT_BRIEFING = (
    "You are picking up an in-progress session and your context was just "
    "compacted, so treat the briefing below as the truth and your own "
    "recollection as unreliable. Re-verify anything it calls decided before "
    "you report it as blocked. Re-read %s before acting, and update whichever "
    "of those documents your work has invalidated.\n\n%s"
)

# ---- judge prompts -----------------------------------------------------------

REGGATE_PROMPT = """

A FIX LANDED THIS TURN, so ALSO fill the `regression_gate` object. The fix-set:
%(fixset)s

Answer FOUR questions about it:

(1) BLIND SPOT: state the property of this defect that made every existing
check blind to it. This repo's own example: every i18n gate compared a locale
against English, so text copied from one non-English locale into another
differed from English and passed every gate; no check ever compared two
non-English locales, so the defect was invisible BY CONSTRUCTION.

(2) EXISTING COVERAGE: would any gate in the list below have FAILED against
the tree BEFORE the fix? Naming a gate that catches a different symptom does
not count. These are the real check:* keys; do not invent others:
%(keys)s

(3) RECURRENCE: could a future edit reintroduce this defect while `npm run ci`
stays green, and is that edit one a reasonable change could make? A one-off
mistake with no invariant behind it does not warrant a gate.

(4) If a gate IS warranted, name the invariant and the cheapest artifact it
can be asserted on.

Fill regression_gate accordingly: applicable (false only if this fix-set
contains no defect fix at all), blind_spot, existing_gate (the EXACT key that
already covers it, or empty string), recurring, gate_needed, gate_proven
(true only if a new gate is already written and wired), instruction (the
concrete next step for the session).
"""

JUDGE_PROMPT = """\
You are a stop-gate for an autonomous coding session. Decide ONE thing: is
ending the turn right now legitimate, or is the session idling with work it
could be doing?

Answer "stop" when the session is genuinely blocked, and hold that word to a
high bar. Waiting counts ONLY when the thing waited on is NAMED and real: a run
id, a task id, a live lease, or a question actually put to the human. "Waiting
on <a phase of this project>" is not a blocker, it is a sentence.

Challenge every blocker that is not about the human. Ask: could the session
unblock this ITSELF? Landing code and enabling a feature are DIFFERENT events,
so "blocked on X landing" is valid only if the source says the CODE cannot be
written or merged, never merely that a FLAG cannot flip yet. If the work could
be built now and left switched off, it is not blocked, and answering "stop"
endorses an idle session.

Answer "continue" when tracked work remains that the session could advance
without the human, or when the last message is a status report that moves
nothing forward.

Be strict about one specific failure: reporting a problem instead of fixing it.
This project's rules say defects found on the way get FIXED, not filed.

Consecutive times this gate has already said continue: %(streak)d. If that number
is above 3, weigh heavily whether your advice is actually actionable.

Remaining work the harness is tracking:
%(remaining)s

Fresh background leases (work genuinely in flight): %(leases)d
Declared loop: %(loop)s

Check these specifically, because they are how this session drifts:
  - Does the message list EVERY open task by id? The operator sees the same list
    in their app, so an omission is a report that disagrees with their view.
  - Does it state the loop schedule, so the operator knows when work resumes?
  - Is anything marked blocked on the operator that they never confirmed? Only
    "You (User Thinks So)" counts; anything else is the session guessing at
    someone else's intent, and it must become an AskUserQuestion instead.
  - Are any remaining items COMPLICATED (multi-file design, an unknown root
    cause, or work that needs its own verification loop)? If so the message must
    say which ones, and say that a Plan agent will design it and a separate
    sub-agent will implement it. This session leads and reviews; it does not do
    complicated work inline. Sub-agents are kept OPEN and given feedback rather
    than re-spawned, so they fix their own mistakes in their own context.
Answer "continue" if any of these is missing.

Sources the session CITED for its blockers, quoted from the tree:
%(citations)s

If a citation is present, READ IT. The question is not whether the file exists,
it is whether that text SAYS the work cannot proceed. A source that describes
how the work is done, or that says it can be built and left switched off, is
EVIDENCE AGAINST the blocker, not for it. Answer "continue" when the quoted text
does not support the claim it was cited for.

The session's last message:
<<<
%(message)s
>>>

Write `reason` and `next_action` as instructions addressed TO the session.
Never use em dashes. Keep next_action concrete and small enough to do now.
"""


# `--help` used to fall through to the Stop-hook path, where stdin is not JSON,
# so asking this tool how to use it produced a BLOCK accusing the caller of a
# hook bug. A tool whose help text is an error message teaches people to guess.
USAGE = """worklist.py -- shared per-repo worklist and cross-session inbox.

Items (v10: a JSONL event store; the old markdown file still works as an
inbox and is synced in, but the verbs are the first-class interface):
  --add <me> <text...>          track a new open item (prints its #id)
  --tick <me> <id> <evidence>   close it; the evidence (sha, run id,
                                file:line, exit code, URL) is REQUIRED
  --defer <me> <id> <q... DEFAULT: <action>>   hand it to the operator;
                                the DEFAULT executes after the window
  --lease <me> <id> <+min|ISO8601Z> worker:<bg-id> [note]   mark in-flight
                                on a NAMED background worker
  --update <me> <id> <text...>  record progress (resets the liveness ladder)
  --list                        render every item with ids and ages

Query:
  --path                        print the worklist file path
  --requests <me>               list cross-session requests addressed to you
  --poll <me>                   inbox poll; prints NOTHING when empty (exit 0)

Cross-session messaging:
  --ask <me> <to> <text...>     ask another session (or '*') a question
  --answer <me> <id> <text...>  answer a request addressed to you
  --decline <me> <id> <why...>  decline it, with a real reason
  --ack <me> <id>               acknowledge without answering

Session state:
  --brief <me> <text...>        publish what you are changing right now
  --handover <me>               write a compact-recovery handover (body on stdin)
  --loop <me> <next> <count> <what...>   declare a scheduled loop

Maintenance:
  --compact                     drop tombstones and fold the event log

Item states: `- [ ]` open, `- [x]` done, `- [?]` deferred with a DEFAULT,
`- [>]` in-flight (carries `until:<ISO8601>Z` and `worker:<id>`). Lines
appended to the markdown file by hand are synced into the store on the next
invocation, so nothing written there is ever silently ignored.

With no arguments this runs as the Stop hook and expects a JSON event on stdin.
"""


# A dirty gitlink is the one tree state where the standing "sweep everything with
# git add -A" rule silently changes what a PR DEPENDS ON. It happened: a subagent
# committed inside private/renet on its own branch, which necessarily moved the
# superproject's gitlink, and a blind sweep would have repointed the console PR at
# a commit living only on an unmerged branch. That does not lose work (the branch
# usually descends from the old pointer) but it adds a submodule PR to the merge
# chain, and `Quality / Submodule Branches` only says so minutes later, in CI.
#
# Deliberately NOT auto-resolved: pointing at an unmerged submodule branch is
# LEGITIMATE in this repo's flow (that is how a stacked submodule PR lands). Only
# the human-or-agent deciding can say which case this is, so the check hands over
# the facts rather than a verdict.
V_SUBMODULE_POINTER = """SUBMODULE POINTER MOVED IN THE WORKTREE (%d): %s

`git add -A` would COMMIT this pointer move, changing what this PR depends on.
Decide explicitly, then act:
  - keep the move (the submodule PR is part of this chain): stage it, and make
    sure the console PR body links that submodule PR, or Quality / Submodule
    Branches fails on the missing link.
  - drop the move (the submodule work belongs to a different PR): restore the
    recorded pointer with
        git submodule update --checkout <path>
    which is safe ONLY while that submodule's worktree is clean and its commit
    is pushed. Verify both first; this is not an undo you can take back."""
