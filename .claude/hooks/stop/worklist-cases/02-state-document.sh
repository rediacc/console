#!/bin/bash
# Part of the worklist v5 control suite. SOURCED by
# `.claude/hooks/stop/test-worklist-v5.sh`, never run on its own: the harness
# (setup, check, run, the PASS/FAIL counters) lives in `_harness.sh` and every
# fixture path comes from the runner. Running this file directly does nothing
# useful and is not how CI reaches it.
#
# The --state write path and the multi-section recovery document: refusals, peers, reaping, adoption, backup, branch follow.

echo "== 29b. --state REFUSES a bad body instead of accepting then blocking =="
# The old write path once accepted ANY body and let the Stop check reject it a
# stop later, leaving the compaction-recovery artifact broken while the session
# believed it was fine. Each rejection is paired with the ALLOW control so the
# guard cannot pass by refusing everything, and the final assert is a byte cmp,
# not a hook allow: a refused write must leave the previous document IDENTICAL.
setup
brief_now
hand_now # a GOOD STATE.md is already on disk; a refused write must not destroy it
STATE_FILE="$BASE/proj/agent/deadbeef/STATE.md"
cp "$STATE_FILE" "$BASE/state.before"
refuse() { # refuse <label> <body-producing-command...>
    local label="$1"
    shift
    local out rc
    out="$("$@" | TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" WORKLIST_AGENT_BRANCH=agenttest \
        python3 "$HOOK" --state deadbeef 2>&1)"
    rc=$?
    if [[ "$rc" -ne 0 ]] && grep -qF "STATE REFUSED" <<<"$out"; then
        pass "--state refuses $label (rc=$rc)"
    else
        fail "--state accepted $label: rc=$rc '${out:0:160}'"
    fi
}
refuse "an over-long body" python3 -c "print('## Next action: go ' + 'x'*4100)"
# The cap is FLAT again, and 29g below is why that is now safe. It was briefly
# SCALED by the number of `## SESSION` headings, because the budget was per
# session while the document was per branch and a flat cap's cheapest remedy
# was deleting the neighbour's block. Since --state merges one owned section,
# the budget and the document have the same scope and a multi-section body is
# not an over-budget document at all -- it is a whole-document paste, which is
# refused for a different and stronger reason.
refuse "a stub body" printf 'wip'
refuse "an aimless body (no Next action section)" python3 -c "print('y'*400)"
# CONTROL: a well-shaped body must still be written, or the guard is just a
# blanket refusal wearing three assertions.
if printf '%s' "$STATE_BODY" |
    TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" WORKLIST_AGENT_BRANCH=agenttest \
        python3 "$HOOK" --state deadbeef >/dev/null 2>&1; then
    pass "CONTROL: a well-shaped STATE.md is still written"
else
    fail "the refusal guard rejected a valid STATE.md"
fi
# A refused write must leave the PREVIOUS document byte-identical. Stronger
# than the old `check allow`: an allow only proves the gate was satisfied,
# a cmp proves the bytes never moved.
cp "$STATE_FILE" "$BASE/state.good"
python3 -c "print('x'*4200)" | TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" \
    WORKLIST_AGENT_BRANCH=agenttest python3 "$HOOK" --state deadbeef >/dev/null 2>&1 || true
if cmp -s "$BASE/state.good" "$STATE_FILE"; then
    pass "a refused rewrite leaves the good STATE.md byte-identical"
else
    fail "a refused rewrite MUTATED the previous STATE.md"
fi

echo "== 29f. TWO sessions share one branch and BOTH sections survive =="
# THE INCIDENT, 2026-08-09. Three sessions were live in one checkout on main.
# The staleness gate nagged 99ccf057 about a document 2fd369e0 owned, 99ccf057
# rewrote it, and a peer's entire state document -- a live canary campaign,
# attempt 6 in flight, five flag flips, an operator-owned design question --
# was destroyed. It came back only because the single-slot .prev backup was
# read before the next write overwrote it.
#
# The assertion is a BYTE COMPARISON of A's rendered section across B's write,
# not an allow: an allow would prove the gate was satisfied, and the thing that
# failed was never the gate.
setup
brief_now
hand_now # A = deadbeef
A_BEFORE="$(section_of deadbeef)"
B_BODY='This is session B, running the licensing drill on a fork of the bench universe, with the mint tool staged and the activation cap already lifted to five. Nothing here overlaps session A, and losing it would cost the drill.

## Next action
Re-run the license-e2e battery against the fork and read the failure reason verbatim.'
state_as cafe1234 "$B_BODY"
A_AFTER="$(section_of deadbeef)"
if [[ -n "$A_BEFORE" && "$A_BEFORE" == "$A_AFTER" ]]; then
    pass "29f: a peer's write leaves A's section byte-identical, stamp included"
else
    fail "29f: B's write MUTATED A's section: before='${A_BEFORE:0:80}' after='${A_AFTER:0:80}'"
fi
# BOTH DOCUMENTS SURVIVE, which is what the merge used to buy inside one file
# and the directory layout now buys by construction. The third clause is the
# one with teeth: B's text must be ABSENT from A's file, because a tool that
# still wrote everything into one document would satisfy the first two.
B_FILE="$BASE/proj/agent/cafe1234/STATE.md"
if grep -qF "This is session B" "$B_FILE" && grep -qF "ci-overhaul session" "$STATE_FILE" &&
    ! grep -qF "This is session B" "$STATE_FILE"; then
    pass "29f: each session's document holds its own body and nothing of the other's"
else
    fail "29f: the two documents are not separate: A=$(head -c 120 "$STATE_FILE") B=$(head -c 120 "$B_FILE" 2>&1)"
fi
# CONTROL: B writing AGAIN replaces only B's section. Without this the case
# would pass on a tool that merely refused to write anything at all.
B_ONE="$(section_of cafe1234)"
sleep 1 # so an advanced stamp is observable at second resolution
state_as cafe1234 "${B_BODY/session B/session B, round two}"
if [[ "$(section_of deadbeef)" == "$A_BEFORE" ]] &&
    [[ "$(section_of cafe1234)" != "$B_ONE" ]] &&
    grep -qF "round two" "$B_FILE"; then
    pass "29f CONTROL: a second write replaces only its own section, A untouched"
else
    fail "29f CONTROL: the second write hit the wrong section"
fi

echo "== 29k. the STOP hook still names the peer sessions after the split =="
# THE HALF OF THE SPLIT THAT COULD HAVE BEEN LOST SILENTLY. Peers used to be
# `## SESSION` headings inside one shared file, and this note read them from
# there. Once each session owns a directory, code that keeps reading only its
# OWN file goes quiet -- while every assertion about MY OWN document keeps
# passing, because mine is the file it still reads. Nothing in this suite
# covered this note before the move, which is exactly the shape of gap a
# migration slips through.
#
# Peers stopped being writable on purpose; they must not stop being VISIBLE. A
# session that cannot see its peers sweeps their uncommitted files.
setup
brief_now
hand_now
brief_other cafe1234
PEER_29K='Session cafe1234 is mid-migration on the chunk-store cold path and owns every uncommitted file under packages/cli/src/services/backup. Sweeping them into another commit is the concrete harm this note exists to prevent, so it has to be visible from a stop, not only after a compaction.

## Next action
Finish the cold-path cutover and hand the file list back to the lead.'
state_as cafe1234 "$PEER_29K"
say "answer

## Remaining
- #7 thing (pending)"
task 7 pending "thing"
export WORKLIST_REPORT_PER_STOP=9
OUT="$(run)"
if grep -qF "under agent/" <<<"$OUT" && grep -qE "cafe1234 +[0-9]+ min old" <<<"$OUT"; then
    pass "29k FIRE: a peer's session directory is named on an ordinary stop, with its age"
else
    fail "29k: the peer went invisible after the split: ${OUT:0:400}"
fi
# CONTROL, one planted fact different: no peer directory, no note. Without it
# the FIRE could be satisfied by boilerplate printed on every stop.
setup
brief_now
hand_now
say "answer

## Remaining
- #7 thing (pending)"
task 7 pending "thing"
OUT="$(run)"
if ! grep -qF "under agent/" <<<"$OUT"; then
    pass "29k CONTROL: a session alone on its branch is told about no peers"
else
    fail "29k CONTROL: a peers note appeared with no peer directory: ${OUT:0:300}"
fi
# And the liveness marker: a peer whose owner is past the dead horizon is
# labelled, because "12 minutes old" and "gone since yesterday" ask different
# things of the reader. NOT called reap-eligible any more: nothing prunes
# another session's directory, and a label promising a sweep that never comes
# is a check that cannot fire.
setup
brief_now
hand_now
brief_other cafe1234
state_as cafe1234 "$PEER_29K"
age_state cafe1234 1800 # 30 hours, past WORKLIST_DEAD_HOURS, no transcript
mkdir -p "$BASE/projects"
export WORKLIST_PROJECTS_DIR="$BASE/projects"
say "answer

## Remaining
- #7 thing (pending)"
task 7 pending "thing"
OUT="$(run)"
# THE ROW, not the word: the note's own prose explains the marker, so a bare
# grep for it passes on the explanation alone -- which is how a control ends up
# testing a paragraph instead of a verdict.
if grep -qE "cafe1234 +[0-9]+ min old +ABANDONED" <<<"$OUT"; then
    pass "29k: a peer past the dead horizon is marked ABANDONED rather than silently equal"
else
    fail "29k: the dead peer read as a live one: ${OUT:0:400}"
fi
# CONTROL: the same fixture with ONE fact changed, the peer's stamp. It gets
# its own setup rather than a second stop in the same session, because a
# class-2 section is released once per stop and a repeat stop would report its
# absence for a reason that has nothing to do with the marker.
setup
brief_now
hand_now
brief_other cafe1234
state_as cafe1234 "$PEER_29K"
age_state cafe1234 5 # minutes, so the owner is alive by any horizon
say "answer

## Remaining
- #7 thing (pending)"
task 7 pending "thing"
OUT="$(run)"
# No `$` anchor: the note travels inside a JSON string, where the row ends in a
# literal backslash-n rather than a newline. An anchored pattern would never
# match and this control would pass on any output at all.
if grep -qE "cafe1234 +[0-9]+ min old" <<<"$OUT" &&
    ! grep -qE "min old +ABANDONED" <<<"$OUT"; then
    pass "29k CONTROL: a fresh peer is listed WITHOUT the abandoned marker"
else
    fail "29k CONTROL: the marker is unconditional, so it says nothing: ${OUT:0:400}"
fi
unset WORKLIST_PROJECTS_DIR WORKLIST_REPORT_PER_STOP

echo "== 29g. --state REFUSES a body carrying a '## SESSION' heading =="
# The old habit is pasting the WHOLE document, and that habit is what destroyed
# a peer's document. The tool now writes the heading itself, so a body with one
# in it is a whole-document paste; refusing teaches the contract at zero cost,
# because the previous document is untouched.
setup
brief_now
hand_now
cp "$STATE_FILE" "$BASE/state.before29g"
WHOLE_DOC="$(
    cat <<EOF
## SESSION deadbeef 2026-08-09T18:30:00Z

$STATE_BODY
EOF
)"
out="$(printf '%s' "$WHOLE_DOC" | TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" \
    WORKLIST_AGENT_BRANCH=agenttest python3 "$HOOK" --state deadbeef 2>&1)"
rc=$?
if [[ "$rc" -ne 0 ]] && grep -qF "looks like the WHOLE document" <<<"$out"; then
    pass "29g FIRE: a body with a '## SESSION' heading is refused, naming the contract"
else
    fail "29g: a whole-document paste was accepted: rc=$rc '${out:0:200}'"
fi
if cmp -s "$BASE/state.before29g" "$STATE_FILE"; then
    pass "29g: the refusal left the document byte-identical"
else
    fail "29g: a REFUSED whole-document write still mutated the document"
fi
# CONTROL: the same body WITHOUT the heading is accepted, so the refusal keys
# on the heading and not on the body being long or familiar.
if printf '%s' "$STATE_BODY" | TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" \
    WORKLIST_AGENT_BRANCH=agenttest python3 "$HOOK" --state deadbeef >/dev/null 2>&1; then
    pass "29g CONTROL: the same body without the heading is accepted"
else
    fail "29g CONTROL: the heading check refused a plain section body"
fi

echo "== 29h. a DEAD peer's section is reaped, and archived BEFORE it is dropped =="
# Reaping is the one path that deletes content nobody chose to delete, so it is
# the one path with an append-only archive rather than a single slot. Liveness
# is the repo's existing notion (owner_age_hours over the transcript dir), with
# the section's own stamp as the fallback for an owner that has no transcript.
setup
brief_now
hand_now
mkdir -p "$BASE/projects"
export WORKLIST_PROJECTS_DIR="$BASE/projects"
DEAD_BODY='Session ghost1234 was driving the ceph cutover rehearsal and has not been seen since. Its last recorded position is the RBD snapshot step on carrier two, with the node sync verified and the fork not yet taken.

## Next action
Take the fork once node sync is confirmed on all three carriers.'
LIVE_BODY='Session live5678 is watching the nightly on main and is very much alive, which is the whole point of this control: an age in the DOCUMENT must not outvote a transcript that is still being written.

## Next action
Read the nightly job log and diagnose any red.'
plant_doc "$(section_of deadbeef)
$(mk_section ghost1234 1800 "$DEAD_BODY")
$(mk_section live5678 1800 "$LIVE_BODY")"
: >"$BASE/projects/live5678-1111-2222-3333-444444444444.jsonl" # a fresh transcript
REAPED="$(TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" python3 "$HOOK" --path)"
REAPED="${REAPED%.md}.agentstate.reaped.deadbeef.md"
age_state deadbeef 1800 # the writer's OWN section is 30h old too
out="$(printf '%s' "$STATE_BODY" | TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" \
    WORKLIST_TASKS_DIR="$BASE/tasks" WORKLIST_AGENT_BRANCH=agenttest \
    python3 "$HOOK" --state deadbeef 2>&1)"
if ! grep -qF "ghost1234" "$STATE_FILE" && grep -qF "Session ghost1234" "$REAPED" 2>/dev/null; then
    pass "29h FIRE: the dead peer's section is gone from STATE.md and present in the archive"
else
    fail "29h: reap/archive wrong (in doc: $(grep -c ghost1234 "$STATE_FILE"), archive: $(head -c 80 "$REAPED" 2>&1))"
fi
if grep -qF "Session live5678" "$STATE_FILE"; then
    pass "29h CONTROL 1: a peer with a fresh transcript is NOT reaped despite a 30h stamp"
else
    fail "29h CONTROL 1: a LIVE peer's section was reaped"
fi
# CONTROL 2 asserts the ABSENCE of the writer from the archive, not the
# presence of its section in the document: the write re-adds its own section
# either way, so a presence check would pass even on a tool that reaped it
# first and then wrote it back with the old body lost.
if [[ "$(grep -c '## SESSION deadbeef' "$STATE_FILE")" == "1" ]] &&
    ! grep -qF "SESSION deadbeef" "$REAPED" 2>/dev/null; then
    pass "29h CONTROL 2: the writer's own 30h-old section is never reaped"
else
    fail "29h CONTROL 2: the writer reaped or duplicated its own section: $(head -c 200 "$STATE_FILE")"
fi
if grep -qF "sections REAPED as dead" <<<"$out" && grep -qF "$REAPED" <<<"$out"; then
    pass "29h: the write names what it reaped and where the archive went"
else
    fail "29h: the reap was silent: '${out:0:220}'"
fi
unset WORKLIST_PROJECTS_DIR

echo "== 29i. a LEGACY single-section document is ADOPTED, never destroyed =="
# Three checkouts hold a pre-section STATE.md on disk right now. The first
# merge on such a branch must keep that text, because it may be an in-flight
# peer's only record -- which is exactly the loss this whole change is about.
setup
brief_now
LEGACY_BODY='This document predates the section format entirely. It belongs to whichever session wrote it last, it has no heading, and if the first sectioned write deletes it then this change has reproduced the very incident it was built to prevent.

## Next action
Preserve me verbatim under a legacy heading.'
plant_doc "$LEGACY_BODY"
printf '%s' "$STATE_BODY" | TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" \
    WORKLIST_TASKS_DIR="$BASE/tasks" WORKLIST_AGENT_BRANCH=agenttest \
    python3 "$HOOK" --state deadbeef >/dev/null 2>&1
if grep -qF "## SESSION legacy" "$STATE_FILE" && grep -qF "predates the section format" "$STATE_FILE" &&
    grep -qF "## SESSION deadbeef" "$STATE_FILE"; then
    pass "29i FIRE: the legacy text survives under a legacy heading beside the new section"
else
    fail "29i: the legacy document was lost: $(head -c 250 "$STATE_FILE")"
fi
# CONTROL: aged past the dead horizon it is REAPED -- into the archive, never
# into nothing. Adoption is a grace period, not a permanent squatter.
mkdir -p "$BASE/projects"
export WORKLIST_PROJECTS_DIR="$BASE/projects"
REAPED="$(TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" python3 "$HOOK" --path)"
REAPED="${REAPED%.md}.agentstate.reaped.deadbeef.md"
age_state legacy 1800
printf '%s' "$STATE_BODY" | TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" \
    WORKLIST_TASKS_DIR="$BASE/tasks" WORKLIST_AGENT_BRANCH=agenttest \
    python3 "$HOOK" --state deadbeef >/dev/null 2>&1
if ! grep -qF "predates the section format" "$STATE_FILE" &&
    grep -qF "predates the section format" "$REAPED" 2>/dev/null; then
    pass "29i CONTROL: an aged legacy section is reaped INTO THE ARCHIVE, not into nothing"
else
    fail "29i CONTROL: aged legacy handling wrong (doc: $(grep -c predates "$STATE_FILE"), archive: $(grep -c predates "$REAPED" 2>/dev/null))"
fi
unset WORKLIST_PROJECTS_DIR

echo "== 29j. a MALFORMED document is never silently replaced =="
# Fail closed: the parser must degrade rather than discard. A document that
# yields no usable section is still SOMEBODY'S text, and the write that lands
# beside it must leave it recoverable from the document itself and from .prev.
setup
brief_now
JUNK='half a sentence with no heading and no next action, well under the floor'
plant_doc "$JUNK"
BACKUP="$(TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" python3 "$HOOK" --path)"
BACKUP="${BACKUP%.md}.agentstate.prev.deadbeef.md"
printf '%s' "$STATE_BODY" | TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" \
    WORKLIST_TASKS_DIR="$BASE/tasks" WORKLIST_AGENT_BRANCH=agenttest \
    python3 "$HOOK" --state deadbeef >/dev/null 2>&1
if grep -qF "$JUNK" "$STATE_FILE"; then
    pass "29j: an unparseable body is preserved in the document, not discarded"
else
    fail "29j: the malformed body vanished: $(head -c 200 "$STATE_FILE")"
fi
if [[ "$(cat "$BACKUP" 2>/dev/null)" == "$JUNK" ]]; then
    pass "29j: and the original bytes are also in the .prev backup"
else
    fail "29j: .prev does not hold the original: '$(head -c 80 "$BACKUP" 2>&1)'"
fi
# CONTROL: the caller's own verdict is unaffected by the junk beside it. The
# junk is under the thin floor, and a shape check that judged the whole FILE
# would call this document thin and block a session whose own section is fine.
task 7 pending "thing"
say "answer

## Remaining
- #7 thing (pending)"
check "29j CONTROL: a peer's malformed text never blocks my own good section" allow ""

echo "== 29e. a SHORT or body-less --state refuses instead of HANGING =="
# REGRESSION GATE for the defect session 4c3e095a reported as #7c1c2629 and
# this session fixed by hand. `--state` used to require argv[2] to enter its
# own branch at all (`len(sys.argv) > 2`), so a BARE `--state` matched nothing
# and fell through to the Stop-HOOK path, which reads the hook event from
# stdin and therefore BLOCKED FOREVER on a terminal. It cost the reporter a
# ten-minute tool timeout, and no test could see it: every existing --state
# case pipes a body in, which is exactly the shape that does NOT reproduce it.
#
# The timeout IS the assertion. A regression re-hangs, `timeout` returns 124,
# and the case fails loudly instead of stalling the suite forever -- which is
# what a naive assert-on-exit-code test would have done.
bare_out="$(TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" WORKLIST_AGENT_BRANCH=agenttest \
    timeout 15 python3 "$HOOK" --state 2>&1)"
bare_rc=$?
if [[ "$bare_rc" -eq 124 ]]; then
    fail "a bare --state HUNG again (rc=124): the argv-length guard regressed"
elif [[ "$bare_rc" -ne 0 ]] && grep -qF "usage: worklist.py --state" <<<"$bare_out"; then
    pass "a bare --state refuses with usage instead of hanging (rc=$bare_rc)"
else
    fail "a bare --state did not refuse with usage: rc=$bare_rc '${bare_out:0:160}'"
fi
# The second half of the same report: the body is read from STDIN, so passing
# it as argv left the body EMPTY and the shape check said `thin: 0 chars`.
# "Too short" and "never arrived" are different diagnoses, and the reporter
# chased the wrong one twice. Empty stdin must say so in its own words.
argv_out="$(TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" WORKLIST_AGENT_BRANCH=agenttest \
    timeout 15 python3 "$HOOK" --state deadbeef "a body passed as an argument" </dev/null 2>&1)"
argv_rc=$?
if [[ "$argv_rc" -eq 124 ]]; then
    fail "--state with an argv body HUNG (rc=124)"
elif grep -qF "no body arrived on stdin" <<<"$argv_out" && grep -qF "extra argument" <<<"$argv_out"; then
    pass "an argv-passed body is diagnosed as absent stdin, naming the extra argument"
else
    fail "--state mis-diagnosed an argv body: rc=$argv_rc '${argv_out:0:200}'"
fi
# CONTROL: the empty-stdin message must NOT be a blanket response. A body that
# genuinely IS too short has to keep saying `thin`, or the new branch has just
# swallowed the old diagnosis.
thin_out="$(printf 'wip' | TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" \
    WORKLIST_AGENT_BRANCH=agenttest timeout 15 python3 "$HOOK" --state deadbeef 2>&1)"
if grep -qF "thin" <<<"$thin_out" && ! grep -qF "no body arrived" <<<"$thin_out"; then
    pass "CONTROL: a genuinely short body still reports thin, not absent-stdin"
else
    fail "the absent-stdin branch swallowed the thin diagnosis: '${thin_out:0:200}'"
fi

echo "== 29c. the OUTGOING document is recoverable from the backup =="
# Two live sessions share one branch, and --state used to be last-write-wins.
# What was not by design is that the loss was permanent: session 84611aab
# replaced session b9491d9c's 0-minute-old document twice, and neither body
# could be recovered -- the event log stores item TEXT, never STATE bodies.
# The write path keeps exactly one previous DOCUMENT beside the lock.
#
# Since the merge (2026-08-09) a peer write cannot clobber anything, so this
# case is no longer about a clobber: 29f owns that property. What is left for
# the backup to cover is a bug in the WRITE itself, which is why the copy is of
# the whole outgoing document and why one slot is enough. The assertions moved
# from `== $VICTIM` to "contains VICTIM", because the outgoing document may hold
# more than the section being replaced.
#
# BOTH WRITES ARE THE SAME SESSION since the tree split (2026-08-14). They used
# to be two, which read as the stronger fixture and stopped being a fixture at
# all the moment each session got its own file: a peer's write now lands in a
# peer's slot, so the assertion below would have been checking a slot nothing
# had written. The property under test was never "a peer overwrote me" -- it is
# "the body I replaced is still on disk somewhere".
setup
brief_now
hand_now # writes STATE_BODY
STATE_FILE="$BASE/proj/agent/deadbeef/STATE.md"
BACKUP="$(TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" python3 "$HOOK" --path)"
# Branch-scoped since the 2026-07-31 review round: one shared slot let a
# write on ANOTHER branch destroy this branch's only backup.
BACKUP="${BACKUP%.md}.agentstate.prev.deadbeef.md"
VICTIM='This is the document a SECOND session wrote and must be able to get back. It carries the one fact that would otherwise die with it: PR #547 merged to main at 01:30Z, so the nightly is now watchable on main rather than on the branch.

## Next action
Diagnose any red in the nightly from its full log; the run itself is scheduled on main.'
printf '%s' "$VICTIM" |
    TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" WORKLIST_AGENT_BRANCH=agenttest \
        python3 "$HOOK" --state deadbeef >/dev/null 2>&1
out="$(printf '%s' "$STATE_BODY" |
    TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" WORKLIST_AGENT_BRANCH=agenttest \
        python3 "$HOOK" --state deadbeef 2>&1)"
if grep -qF "PR #547 merged to main at 01:30Z" "$BACKUP" 2>/dev/null; then
    pass "the outgoing document is recoverable from the backup"
else
    fail "the backup does not hold the outgoing document: '$(head -c 120 "$BACKUP" 2>&1)'"
fi
# The backup must be the OUTGOING document, never the incoming one -- a copy
# taken after os.replace would look like a backup and restore nothing.
if ! grep -qF "Round 23 went red" "$BACKUP" 2>/dev/null; then
    pass "CONTROL: the backup is the outgoing document, not the one just written"
else
    fail "the backup captured the INCOMING body; restoring it is a no-op"
fi
# The writing session has to be TOLD where the copy went, in the same line that
# tells it something was there before.
if grep -qF "previous document saved to" <<<"$out" && grep -qF "$BACKUP" <<<"$out"; then
    pass "the success line names the backup path"
else
    fail "the write was silent about recovery: '${out:0:200}'"
fi
# CONTROL: the FIRST write on a branch replaces nothing, so it must not claim
# a backup exists -- an unconditional path in that line would send the next
# session chasing a file holding someone else's unrelated document.
rm -f "$STATE_FILE" "$BACKUP"
out="$(printf '%s' "$STATE_BODY" |
    TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" WORKLIST_AGENT_BRANCH=agenttest \
        python3 "$HOOK" --state deadbeef 2>&1)"
if grep -qF "previous document saved to" <<<"$out"; then
    fail "a first write with nothing to replace still advertised a backup"
else
    pass "CONTROL: a first write advertises no backup"
fi

echo "== 29d. the document and its backup FOLLOW THE SESSION across a branch change =="
# This case used to assert the opposite -- one backup slot PER BRANCH (review
# findings 3688784930/3688787780) -- and it was right while the document itself
# was per branch. On 2026-08-18 the branch left the path entirely, so the
# property it protected inverted: one session now has ONE STATE.md and ONE
# backup, and a checkout that changes branch under a live session must not fork
# either. That is not a theoretical inversion. Session 97604f47 was found
# owning three STATE.md files at once (main, 0815-1, backup-storage) because a
# /pr-merge moved the checkout mid-session, and the two it was no longer
# writing were invisible to it.
#
# So: write on branch A, then write the SAME session on branch B, and both the
# document and the .prev slot must be the same files. The peer half below is
# unchanged and still the guard against the OTHER loss (a peer's write taking
# my only backup), which is what makes this pair a real control: one asserts a
# branch cannot separate two writes, the other asserts a SESSION still can.
setup
brief_now
hand_now # branch agenttest, STATE_BODY
STATE_A="$BASE/proj/agent/deadbeef/STATE.md"
BACKUP_A="$(TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" python3 "$HOOK" --path)"
BACKUP_BRANCHED="${BACKUP_A%.md}.agentstate.prev.otherbranch.deadbeef.md"
BACKUP_A="${BACKUP_A%.md}.agentstate.prev.deadbeef.md"
VICT_A='Victim body, deliberately long enough for the shape gate to accept it as a real state document (the gate refuses anything under 250 characters as thin, and an earlier draft of this very fixture was refused exactly that way, which is why this sentence exists). It carries the one fact only this document holds.

## Next action
Recover me from the backup and nothing else.'
# Branch A: write VICT_A, then write over it, so the slot holds VICT_A.
printf '%s' "$VICT_A" |
    TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" WORKLIST_AGENT_BRANCH=agenttest \
        python3 "$HOOK" --state deadbeef >/dev/null 2>&1
printf '%s' "$STATE_BODY" |
    TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" WORKLIST_AGENT_BRANCH=agenttest \
        python3 "$HOOK" --state deadbeef >/dev/null 2>&1
# The checkout moves to another branch under the SAME session. No new directory
# is created for it, deliberately: if one were needed the write would refuse,
# which is itself the old behaviour this case now forbids.
OUT29D="$(printf '%s' "$VICT_A" |
    TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" WORKLIST_AGENT_BRANCH=otherbranch \
        python3 "$HOOK" --state deadbeef 2>&1)"
if [[ -f "$STATE_A" ]] && grep -qF "Recover me from the backup" "$STATE_A" &&
    ! [[ -e "$BASE/proj/agent/otherbranch" ]] && ! [[ -e "$BACKUP_BRANCHED" ]]; then
    pass "29d: a branch change does not fork the document or its backup slot"
else
    fail "29d: the branch forked the session's document (out: ${OUT29D:0:160})"
fi
# ... and the branch-B write's backup landed in the ONE slot, holding the body
# the branch-A write had left behind. Without this the case above would pass on
# a build that simply stopped writing backups at all.
if grep -qF "Round 23 went red" "$BACKUP_A" 2>/dev/null; then
    pass "29d1: the single slot holds the body the previous write left, whatever the branch"
else
    fail "29d1: the branch-B write did not back up through the session slot (A: $(head -c 60 "$BACKUP_A" 2>&1))"
fi
# THE SESSION SCOPE, which the case above deliberately does NOT cover: a peer
# writing twice must leave deadbeef's slot alone. Two writes, because the first
# has nothing to replace and would leave an unwritten slot looking exactly like
# a respected one.
mkdir -p "$BASE/proj/agent/cafe1234"
BACKUP_PEER="${BACKUP_A%.deadbeef.md}.cafe1234.md"
# A body only the PEER ever writes. The previous draft had the peer write
# STATE_BODY, which both slots already contained, so the "mine is intact"
# assertion would have held just as well on a build where the peer HAD taken my
# slot. A marker no other writer uses is what makes the check able to fail.
PEER_BODY='Peer body owned by cafe1234 alone, long enough for the shape gate to accept it as a real state document rather than refusing it as thin, which is a floor of 250 characters and easy to fall under when writing a fixture in a hurry.

## Next action
This text must never appear in another session backup slot.'
for i in 1 2; do
    printf '%s' "$PEER_BODY" |
        TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" WORKLIST_AGENT_BRANCH=agenttest \
            WORKLIST_SESSION_ID="$(peer_id cafe1234)" python3 "$HOOK" --state cafe1234 >/dev/null 2>&1
done
if grep -qF "Round 23 went red" "$BACKUP_A" 2>/dev/null &&
    grep -qF "Peer body owned by cafe1234" "$BACKUP_PEER" 2>/dev/null &&
    ! grep -qF "Peer body owned by cafe1234" "$BACKUP_A" 2>/dev/null; then
    pass "29d2: a PEER's two writes keep their own slot and leave mine intact"
else
    fail "29d2: a peer write took my slot (mine: $(head -c 40 "$BACKUP_A" 2>&1), theirs: $(head -c 40 "$BACKUP_PEER" 2>&1))"
fi
# A failed backup copy must be CONFESSED, not advertised as a recovery path.
rm -f "$BACKUP_A"
mkdir -p "$BACKUP_A" # a directory at the path makes write_text raise OSError
out="$(printf '%s' "$STATE_BODY" |
    TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" WORKLIST_AGENT_BRANCH=agenttest \
        python3 "$HOOK" --state deadbeef 2>&1)"
rmdir "$BACKUP_A" 2>/dev/null
if grep -qF "backup copy FAILED" <<<"$out" && ! grep -qF "previous document saved to" <<<"$out"; then
    pass "29d CONTROL: a failed backup write warns instead of naming a phantom file"
else
    fail "29d CONTROL: the failed backup was advertised as saved: '${out:0:200}'"
fi
