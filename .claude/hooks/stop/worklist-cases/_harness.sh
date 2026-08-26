#!/bin/bash
# Shared harness for the worklist v5 control suite -- the ONE copy of every
# fixture helper. SOURCED by `.claude/hooks/stop/test-worklist-v5.sh` after it
# has scrubbed the ambient environment and exported HOOK, BASE, SID, PASS and
# FAIL; the case files under this directory are sourced after it and use these
# helpers. Nothing here runs on its own.
#
# Do not copy a helper into a case file. A second copy is the defect, not the
# convenience: the cases assume one definition of setup() and one pair of
# counters.

setup() {
    # Reset EVERY knob run() reads. A plain `BG=...` in one case leaked into the
    # next two and silently suppressed a check, which cost a debugging round.
    BG='[]'
    # TWO live crons by default, since v9: the enforced shape is one work loop
    # plus the 5-minute inbox poll, and a session missing the poll now blocks.
    # A real looped session carries both, so that is the default to model.
    # Cases that test cron behavior (25, 26, 34, 35, 101+) or I6 pin their own.
    CRONS='[{"id":"w","schedule":"17 * * * *"},{"id":"p","schedule":"*/5 * * * *"}]'
    JUDGE_MODE=off
    CADENCE=off
    # The v13 F2 email knobs. Reset here for the same reason every other knob
    # is: a stray WORKLIST_EMAIL_TRANSPORT leaking out of one case would make a
    # later case write mail into a stale directory, and a stray WORKLIST_SES_ENV
    # pointing at a deleted fixture would silently turn the channel off.
    unset WORKLIST_SES_ENV WORKLIST_EMAIL_TRANSPORT WORKLIST_EMAIL
    # The output-queue knobs, reset for the same reason: a leaked
    # WORKLIST_REPORT_PER_STOP would change how many report sections a later
    # case sees and turn a real regression into a green run. Cases that need a
    # wider drain export it AFTER their setup call.
    unset WORKLIST_REPORT_PER_STOP WORKLIST_OUTQ_MAX
    # The background-wait knobs. WORKLIST_BG_OUTPUT_DIR and WORKLIST_HARNESS_PID
    # were exported by individual cases and unset by only SOME of them, so both
    # leaked forward -- a case downstream of 163f pointed the stream reader at a
    # deleted fixture directory and gave the OS verifier a stale ancestor pid.
    # That was survivable while verify_background ran only on a due check-in; it
    # stopped being survivable in v17, which reads it on every pure-wait stop and
    # feeds the verdict into the no-op streak. WORKLIST_QUIET_WAKES is here for
    # the AMBIENT case rather than the leak: it is a real knob, so a value in the
    # operator's own shell would silently retune the streak under the suite.
    unset WORKLIST_BG_OUTPUT_DIR WORKLIST_HARNESS_PID WORKLIST_QUIET_WAKES
    # The STATE.md reap knobs, reset for exactly the reason above. Case 29h
    # points WORKLIST_PROJECTS_DIR at a fixture transcript dir to make a peer
    # section reap-eligible; leaked forward, every later case would judge
    # section liveness against that stale directory. Unset, wl_core.projects_dir
    # falls back to ~/.claude/projects/<slug>, which does not exist for a
    # mktemp fixture root, so it answers "" and no section is ever reaped by
    # transcript age -- which is the hermetic default this suite needs.
    unset WORKLIST_PROJECTS_DIR WORKLIST_DEAD_HOURS WORKLIST_ARCHIVE_HOURS
    # PINNED, NOT INHERITED. The hook no-ops when GITHUB_ACTIONS=true, so a suite
    # that inherits the ambient value passes locally and silently no-ops in CI,
    # where 30 cases came back with empty output and read as failures.
    GHA=''
    rm -rf "$BASE"
    mkdir -p "$BASE/proj/.git" "$BASE/tmp/claude-worklist" "$BASE/tasks/session-deadbeef"
    # The fixture .git is a plain directory, so `git symbolic-ref` exits 128
    # and every branch-dependent check would be SKIPPED as no-branch across
    # the whole suite -- a gate that never fires in its own tests. The env
    # override exists in wl_core.git_branch for exactly this.
    export WORKLIST_AGENT_BRANCH=agenttest
    # PINNED INTO THE FIXTURE, for the same reason TMPDIR is. Unset, the v18
    # unread-reports surface reads the OPERATOR'S REAL report store on every
    # stop in this suite. That happened to stay green only because the fixture
    # branch is `agenttest` and no real report carries it -- a hermetic suite
    # must not depend on a branch name never colliding.
    export WORKLIST_REPORTS_DIR="$BASE/reports"
    # PINNED INTO THE FIXTURE, for exactly the reason above. Unset, the
    # specialist-agent matcher (wl_agents) scores every case in this suite
    # against the OPERATOR'S REAL .claude/agents, so a case's verdict would
    # change whenever somebody edited an agent description -- a suite that
    # fails on someone else's prose edit. Empty by default, which is the
    # silent corpus every case that is not 209 wants.
    mkdir -p "$BASE/agents"
    export WORKLIST_AGENTS_DIR="$BASE/agents"
    # The hint knobs, reset for the same reason every other knob is: a leaked
    # WORKLIST_AGENT_HINT=off from case 209I would silently mute the feature
    # for every case after it, and the absence assertions would still pass.
    unset WORKLIST_AGENT_HINT WORKLIST_AGENT_HINT_MAX_PER_SESSION
    unset WORKLIST_AGENT_HINT_MIN_SCORE WORKLIST_AGENT_HINT_MIN_MARGIN
    # ONE DIRECTORY PER SESSION under agent/, plus the legacy dotted
    # root that still holds TRAPS.md. `deadbeef` is this suite's default
    # session; a fixture acting as a PEER makes its own (see state_as).
    mkdir -p "$BASE/proj/agent/deadbeef" "$BASE/proj/.agent"
    WL="$BASE/tmp/claude-worklist/$(echo "$BASE/proj" | sed 's|[^A-Za-z0-9._-]|_|g' | sed 's/^_//').md"
    : >"$WL"
    printf '%s\n' '{"type":"user","message":{"content":"go"}}' >"$BASE/t.jsonl"
    mkdir -p "$BASE/binonly" "$BASE/nohome"
    for b in python3 sh bash cat date; do ln -sf "$(command -v $b)" "$BASE/binonly/$b" 2>/dev/null; done
}

# say <text-of-last-assistant-message>
# Does NOT imply a turn boundary, and must not: case 24 depends on two say()
# calls landing in ONE turn, because multiple assistant text blocks per turn is
# exactly the shape that once hid a '## Remaining' section from this hook. Use
# the explicit newturn helper when a fixture wants a fresh window.
say() {
    python3 -c '
import json,sys
rec={"type":"assistant","message":{"content":[{"type":"text","text":sys.argv[1]}]}}
open(sys.argv[2],"a").write(json.dumps(rec)+"\n")
' "$1" "$BASE/t.jsonl"
}

mk_agent() { # mk_agent <name> <description> -- one fixture agent in the corpus
    # INVENTED NOUNS ONLY in the cases below. A fixture that borrows the real
    # agents' vocabulary would pass or fail depending on prose nobody thinks of
    # as test data, which is the same coupling WORKLIST_AGENTS_DIR removes.
    printf -- '---\nname: %s\ndescription: %s\ntools: Bash\nmodel: opus\n---\nbody text\n' \
        "$1" "$2" >"$BASE/agents/$1.md"
}

task() { # task <id> <status> <subject> [blockedBy-csv]
    local blocked="[]"
    if [[ -n "${4:-}" ]]; then
        blocked=$(printf '%s' "$4" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read().split(",")))')
    fi
    printf '{"id":"%s","status":"%s","subject":"%s","blockedBy":%s}\n' "$1" "$2" "$3" "$blocked" >"$BASE/tasks/session-deadbeef/$1.json"
}

# Plant a STATE.md DIRECTLY on disk, bypassing `--state`.
#
# The CLI refuses a badly-shaped body at write time, so piping one through it
# produces no file and the previous document survives. The Stop check's shape
# detection must still work regardless, because a document can reach that path
# without the CLI: written by an older flow, hand-edited, by a raw Write, or
# truncated by a full disk. So the shape cases plant the file and the refusal
# gets its own case.
#
# SINCE THE SECTION FORMAT (2026-08-09), a plant with no `## SESSION` heading
# is specifically a LEGACY document: agent_state_parse turns it into one
# unowned section, and the read path judges that section as if it were the
# caller's. That is deliberate and is what keeps every shape case below
# meaningful without a stamped fixture -- but it also means these cases now
# exercise the mtime FALLBACK rather than the heading stamp, so any case whose
# subject is AGE must use age_state on a real stamped section instead.
plant_state() { # plant_state <body>
    printf '%s' "$1" >"$BASE/proj/agent/deadbeef/STATE.md"
}

# The same raw plant, named for what the new cases use it for: a whole
# DOCUMENT (possibly multi-section) placed on disk without going through the
# merge, which is the only way to fabricate a peer's section for a read case.
plant_doc() { # plant_doc <text>
    printf '%s' "$1" >"$BASE/proj/agent/deadbeef/STATE.md"
}

mk_section() { # mk_section <owner> <minutes-ago> <body> -> one stamped section
    python3 -c '
import sys, time
owner, mins, body = sys.argv[1], float(sys.argv[2]), sys.argv[3]
stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - mins * 60))
sys.stdout.write("## SESSION %s %s\n\n%s\n" % (owner, stamp, body.strip()))
' "$1" "$2" "$3"
}

section_now() { # section_now <owner> <body> -> one section stamped now
    mk_section "$1" 0 "$2"
}

# owner_state_file <owner> -- the file that OWNS <owner>'s section.
#
# Since the tree split there are two kinds of owner in this suite and they live
# in different files: a real session (deadbeef, cafe1234) writes its own
# agent/<owner>/STATE.md, while a PLANTED pseudo-owner (legacy,
# ghost1234, live5678) exists only as a heading inside the default session's
# document, which is exactly how those cases fabricate a peer without running
# one. Resolving by existence keeps every call site below unchanged and, more
# importantly, keeps each case pointed at the file whose behaviour it is about.
owner_state_file() {
    if [[ -f "$BASE/proj/agent/$1/STATE.md" ]]; then
        printf '%s' "$BASE/proj/agent/$1/STATE.md"
    else
        printf '%s' "$BASE/proj/agent/deadbeef/STATE.md"
    fi
}

age_state() { # age_state <owner> <minutes-ago> -- backdate that section's stamp
    # The heading stamp is the age source now, so `touch -d` no longer ages a
    # section written by --state: it moves the file's mtime, which is only the
    # FALLBACK for an unstamped section. A case that keeps touching the file
    # would silently test the fallback instead of the rule, so this helper
    # EXITS NON-ZERO when the owner's heading is not there rather than aging
    # nothing and passing quietly.
    python3 - "$(owner_state_file "$1")" "$1" "$2" <<'PYEOF'
import re, sys, time
path, owner, mins = sys.argv[1], sys.argv[2], float(sys.argv[3])
stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - mins * 60))
text = open(path, encoding="utf-8").read()
new, n = re.subn(
    r"(?m)^(##[ \t]+SESSION[ \t]+%s\b)[ \t]*.*$" % re.escape(owner),
    lambda m: m.group(1) + " " + stamp,
    text,
)
if n != 1:
    sys.exit("age_state: expected ONE '## SESSION %s' heading, found %d" % (owner, n))
open(path, "w", encoding="utf-8").write(new)
PYEOF
}

section_of() { # section_of <owner> -- that section rendered, or nothing
    python3 - "$(dirname "$HOOK")" "$(owner_state_file "$1")" "$1" <<'PYEOF'
import os, sys
sys.path.insert(0, sys.argv[1])
import wl_store as S
try:
    text = open(sys.argv[2], encoding="utf-8").read()
    mtime = os.path.getmtime(sys.argv[2])
except OSError:
    sys.exit(0)
for s in S.agent_state_parse(text, mtime):
    if s["owner"] == sys.argv[3]:
        sys.stdout.write(S.agent_state_render([s]))
PYEOF
}

state_as() { # state_as <prefix> <body> -- write STATE.md as ANOTHER session
    # MKDIR FIRST, because the tool refuses to create a session folder and a
    # peer's folder is not the default fixture's: without this every peer write
    # in the suite would be refused, and (before the loud rc check below) the
    # cases built on them would have asserted the absence of a document that
    # was never written.
    mkdir -p "$BASE/proj/agent/$1"
    # LOUD ON FAILURE, deliberately. The first draft swallowed stderr, and a
    # peer body two characters under the 250-char floor was silently refused:
    # three cases then asserted the ABSENCE of a section that had never been
    # written, and two of them would have passed for the wrong reason. A helper
    # whose failure is invisible turns every case built on it into a vacuity.
    local out rc
    out="$(printf '%s' "$2" |
        TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" WORKLIST_TASKS_DIR="$BASE/tasks" \
            WORKLIST_AGENT_BRANCH=agenttest WORKLIST_SESSION_ID="$(peer_id "$1")" \
            python3 "$HOOK" --state "$1" 2>&1)"
    rc=$?
    if [[ "$rc" -ne 0 ]]; then
        fail "FIXTURE BROKEN: state_as $1 was refused (rc=$rc): ${out:0:200}"
        return 1
    fi
}

# A STATE.md fresh enough and well-shaped enough to satisfy the gate. Keeps the
# literal phrase "ci-overhaul session" (case 20 greps for it in the PostCompact
# additionalContext) and carries the mandatory '## Next action' section.
# WORKLIST_TASKS_DIR is passed DELIBERATELY: hand_now's predecessor omitted it,
# so all 91 setup handovers recorded a world signature computed against an
# EMPTY task dir that could never match a stop-time signature (latent only
# because no fixture aged past the stale limit). Finding F3 in the plan.
STATE_BODY='You are picking up the ci-overhaul session driving PR #543 to green on branch 0728-2. Round 23 went red on a dead-shell finding, now fixed by running the stop-gate suite from test-hooks.sh. The rediacc-autopilot App already exists and is validated, so never report it as blocked on the operator.

## Next action

Push and watch the run, then bump the submodule pointers to the squash commits before the merge chain.'

hand_now() {
    printf '%s' "$STATE_BODY" |
        TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" WORKLIST_TASKS_DIR="$BASE/tasks" \
            WORKLIST_AGENT_BRANCH=agenttest python3 "$HOOK" --state deadbeef >/dev/null
}

brief_now() {
    printf '%s %s %s\n' "deadbeef" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "doing the thing" >>"${WL%.md}.sessions"
}

newturn() { # a fresh user record; transcript_tail only reads back to the last one
    printf '%s\n' '{"type":"user","message":{"content":"go"}}' >>"$BASE/t.jsonl"
}

reqcli() { # drive the request CLI against the fixture worklist
    TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" python3 "$HOOK" "$@"
}

peer_id() { # the full session id a fixture PREFIX stands for
    printf '%s-1111-2222-3333-444444444444' "$1"
}

as_peer() { # as_peer <prefix> <cmd...> -- drive a helper as ANOTHER session
    # A SUBSHELL, not a `WORKLIST_SESSION_ID=... reqcli ...` prefix assignment.
    #
    # NOT because the prefix form leaks here -- it does not, and an earlier
    # version of this comment claimed it did. Measured on this machine rather
    # than recalled: bash 5.2 in default mode, bash 5.2 under `set -o posix`,
    # and dash all DISCARD the assignment when the function returns. The rule
    # that does persist is POSIX's rule for SPECIAL BUILTINS (eval, export,
    # set), which a function is not.
    #
    # The real reason is portability of the CONSTRUCT. That persistence rule has
    # genuinely differed across shells and modes, this helper is the kind of
    # thing that gets copied into contexts its author does not control, and the
    # failure it would cause is invisible: a leaked peer id disarms the identity
    # check for every later case while the suite stays green. A subshell cannot
    # leak under ANY shell. Choose the construct that cannot fail over the one
    # that happens not to fail here -- the same leaked-knob class the setup()
    # comment above documents, arriving through a different door.
    (
        local sid
        sid="$(peer_id "$1")"
        export WORKLIST_SESSION_ID="$sid"
        shift
        "$@"
    )
}

askid() { # askid <from> <to> <text...> -> prints the new request id
    reqcli --ask "$@" | sed -n 's/.*#\([0-9a-f]\{8\}\).*/\1/p' | head -n1
}

askid_as() { # askid for a request sent BY another session: askid_as <from> <to> ...
    as_peer "$1" askid "$@"
}

phantom_store() { # plant <n> events by <prefix> at <age-minutes>, owning one open item
    local pfx="$1" age="$2" at
    at=$(python3 -c "
import datetime,sys
print((datetime.datetime.now(datetime.timezone.utc)-datetime.timedelta(minutes=float(sys.argv[1]))).strftime('%Y-%m-%dT%H:%M:%SZ'))" "$age")
    python3 - "${WL%.md}.events.jsonl" "$pfx" "$at" <<'PYEOF'
import json, sys
path, pfx, at = sys.argv[1], sys.argv[2], sys.argv[3]
with open(path, "a", encoding="utf-8") as fh:
    for i in range(3):
        fh.write(json.dumps({"ev": "add", "id": "ph%s%d" % (pfx[:4], i), "at": at,
                             "by": pfx, "s": " ", "o": pfx,
                             "t": "phantom-owned item %d" % i}) + "\n")
PYEOF
}

brief_other() { # brief_other <prefix> -- a fresh brief for another live session
    printf '%s %s %s\n' "$1" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "other session" >>"${WL%.md}.sessions"
}

shim_judge() { # shim_judge '<regression_gate JSON>' -- a canned claude that always says stop
    RG="$1" python3 -c '
import json, os, pathlib, stat, sys
rg = os.environ.get("RG", "")
out = {"is_error": False, "structured_output": {"verdict": "stop", "reason": "ok", "next_action": "none"}}
if rg:
    out["structured_output"]["regression_gate"] = json.loads(rg)
body = "#!/bin/bash\necho " + json.dumps(json.dumps(out)) + "\n"
p = pathlib.Path(sys.argv[1])
p.write_text(body)
p.chmod(p.stat().st_mode | stat.S_IEXEC)
' "$BASE/binonly/claude"
}

runj() { # like run() but with the shim claude on PATH and the judge ON
    printf '{"session_id":"%s","cwd":"%s","transcript_path":"%s","session_crons":%s,"background_tasks":%s}' \
        "$SID" "$BASE/proj" "$BASE/t.jsonl" "${CRONS:-[]}" "${BG:-[]}" |
        PATH="$BASE/binonly:$PATH" TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" \
            WORKLIST_TASKS_DIR="$BASE/tasks" WORKLIST_AGENT_BRANCH="${WORKLIST_AGENT_BRANCH-agenttest}" \
            WORKLIST_JUDGE=on GITHUB_ACTIONS="${GHA:-}" \
            python3 "$HOOK" 2>"$BASE/err.txt"
}

checkj() { # check <label> <expect-decision> <must-contain>, through runj
    local label="$1" want="$2" needle="$3" out
    out="$(runj)"
    local got
    got="$(python3 -c 'import json,sys
raw=sys.stdin.read().strip()
print(json.loads(raw).get("decision","allow") if raw else "allow")' <<<"$out" 2>/dev/null)"
    if [[ "$got" == "$want" ]] && grep -qF "$needle" <<<"$out"; then
        echo "  PASS: $label"
        PASS=$((PASS + 1))
    else
        echo "  FAIL: $label (want=$want got=$got, needle '$needle' $(grep -qF "$needle" <<<"$out" && echo present || echo MISSING))"
        echo "        out: ${out:0:220}"
        [[ -s "$BASE/err.txt" ]] && echo "        err: $(head -c 200 "$BASE/err.txt")"
        FAIL=$((FAIL + 1))
    fi
}

reg_repo() { # a git repo with one base commit; the marker will init at this HEAD
    (
        cd "$BASE/proj" || exit
        git init -q 2>/dev/null
        git config user.email t@t
        git config user.name t
        echo base >base.txt
        git add -A
        git commit -qm "chore: base"
    ) >/dev/null 2>&1
    MARKER="${WL%.md}.reggate-deadbeef"
}

fixcommit() { # fixcommit <file> <subject>
    (
        cd "$BASE/proj" || exit
        mkdir -p "$(dirname "$1")"
        echo x >>"$1"
        git add -A
        git commit -qm "$2"
    ) >/dev/null 2>&1
}

run() { # feed the hook a Stop event and print its raw JSON verdict
    # CADENCE OFF BY DEFAULT HERE, and this is a deliberate trade worth naming.
    # The cadence stands the hook down for one turn after it demanded and the
    # session answered, so ANY case shaped block -> new say -> block sees a pause
    # instead of the second block. That is most of this suite, and rewriting
    # hundreds of assertions to alternate would make them harder to read without
    # making them truer: what they exist to pin is WHAT each check says when it
    # fires, not the pacing between firings.
    #
    # The cost is real and must not be forgotten: with this off, none of the
    # cases below exercise the cadence, so the guards are only as covered as the
    # dedicated cases that set CADENCE=on explicitly (214*). If you add a guard,
    # add a case there -- nothing here will catch it for you.
    printf '{"session_id":"%s","cwd":"%s","transcript_path":"%s","session_crons":%s,"background_tasks":%s}' \
        "$SID" "$BASE/proj" "$BASE/t.jsonl" "${CRONS:-[]}" "${BG:-[]}" |
        TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" WORKLIST_TASKS_DIR="$BASE/tasks" \
            WORKLIST_AGENT_BRANCH="${WORKLIST_AGENT_BRANCH-agenttest}" \
            WORKLIST_JUDGE="${JUDGE_MODE:-off}" GITHUB_ACTIONS="${GHA:-}" \
            WORKLIST_CADENCE="${CADENCE:-off}" \
            python3 "$HOOK" 2>"$BASE/err.txt"
}

# Defined HERE, beside check(), not near the cases that first used them.
# They lived at the bottom of this file until 2026-07-30, which meant any case
# above that point calling them got `pass: command not found` on stderr while
# the suite still reported "0 failed" -- the assertions were silent no-ops. That
# is exactly the vacuity this suite exists to catch, and it caught itself only
# because stderr was read separately from stdout. Keep them at the top.
pass() {
    echo "  PASS: $1"
    PASS=$((PASS + 1))
}
fail() {
    echo "  FAIL: $1"
    FAIL=$((FAIL + 1))
}

run_as() { # run_as <prefix> -- drive a Stop event as ANOTHER live session
    # The whole point of the per-session STATE.md rule is that two sessions on
    # one branch get DIFFERENT verdicts, and a suite that can only ever stop as
    # `deadbeef` cannot observe that. Both the event's session_id and
    # WORKLIST_SESSION_ID move together, exactly as they do for a real peer.
    local sid
    sid="$(peer_id "$1")"
    printf '{"session_id":"%s","cwd":"%s","transcript_path":"%s","session_crons":%s,"background_tasks":%s}' \
        "$sid" "$BASE/proj" "$BASE/t.jsonl" "${CRONS:-[]}" "${BG:-[]}" |
        TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" WORKLIST_TASKS_DIR="$BASE/tasks" \
            WORKLIST_SESSION_ID="$sid" \
            WORKLIST_AGENT_BRANCH="${WORKLIST_AGENT_BRANCH-agenttest}" \
            WORKLIST_JUDGE="${JUDGE_MODE:-off}" GITHUB_ACTIONS="${GHA:-}" \
            python3 "$HOOK" 2>"$BASE/err.txt"
}

check_as() { # check_as <prefix> <label> <expect-decision> <must-contain>
    local who="$1" label="$2" want="$3" needle="$4" out
    out="$(run_as "$who")"
    local got
    got="$(python3 -c 'import json,sys
raw=sys.stdin.read().strip()
print(json.loads(raw).get("decision","allow") if raw else "allow")' <<<"$out" 2>/dev/null)"
    if [[ "$got" == "$want" ]] && grep -qF "$needle" <<<"$out"; then
        echo "  PASS: $label"
        PASS=$((PASS + 1))
    else
        echo "  FAIL: $label (want=$want got=$got, needle '$needle' $(grep -qF "$needle" <<<"$out" && echo present || echo MISSING))"
        echo "        out: ${out:0:220}"
        [[ -s "$BASE/err.txt" ]] && echo "        err: $(head -c 200 "$BASE/err.txt")"
        FAIL=$((FAIL + 1))
    fi
}

check() { # check <label> <expect-decision> <must-contain>
    local label="$1" want="$2" needle="$3" out
    out="$(run)"
    local got
    got="$(python3 -c 'import json,sys
raw=sys.stdin.read().strip()
print(json.loads(raw).get("decision","allow") if raw else "allow")' <<<"$out" 2>/dev/null)"
    if [[ "$got" == "$want" ]] && grep -qF "$needle" <<<"$out"; then
        echo "  PASS: $label"
        PASS=$((PASS + 1))
    else
        echo "  FAIL: $label (want=$want got=$got, needle '$needle' $(grep -qF "$needle" <<<"$out" && echo present || echo MISSING))"
        echo "        out: ${out:0:220}"
        [[ -s "$BASE/err.txt" ]] && echo "        err: $(head -c 200 "$BASE/err.txt")"
        FAIL=$((FAIL + 1))
    fi
}

# check_quiet <label> <must-NOT-contain> -- DECISION-AGNOSTIC absence.
#
# For a control whose subject is "this one check said nothing", where the rest
# of the battery's verdict is not the point and pinning it would make the case
# fail whenever an unrelated check changed. It still refuses to pass on SILENCE:
# an empty stdout means the hook died before deciding, and a needle is trivially
# absent from nothing -- the vacuity this suite exists to catch.
check_quiet() {
    local label="$1" needle="$2" out
    out="$(run)"
    if [[ -n "${out//[[:space:]]/}" ]] && ! grep -qF "$needle" <<<"$out"; then
        echo "  PASS: $label"
        PASS=$((PASS + 1))
    else
        echo "  FAIL: $label (needle '$needle' $(grep -qF "$needle" <<<"$out" && echo PRESENT || echo "absent, but the hook produced NO output"))"
        echo "        out: ${out:0:220}"
        [[ -s "$BASE/err.txt" ]] && echo "        err: $(head -c 200 "$BASE/err.txt")"
        FAIL=$((FAIL + 1))
    fi
}

check_absent() { # check_absent <label> <expect-decision> <must-NOT-contain>
    local label="$1" want="$2" needle="$3" out
    out="$(run)"
    local got
    got="$(python3 -c 'import json,sys
raw=sys.stdin.read().strip()
print(json.loads(raw).get("decision","allow") if raw else "allow")' <<<"$out" 2>/dev/null)"
    if [[ "$got" == "$want" ]] && ! grep -qF "$needle" <<<"$out"; then
        echo "  PASS: $label"
        PASS=$((PASS + 1))
    else
        echo "  FAIL: $label (want=$want got=$got, needle '$needle' $(grep -qF "$needle" <<<"$out" && echo PRESENT || echo absent))"
        echo "        out: ${out:0:220}"
        FAIL=$((FAIL + 1))
    fi
}
