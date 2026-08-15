#!/bin/bash
# Controls for worklist.py v5. Every check must FIRE on a planted defect and
# stay silent when clean. Nothing here touches the live worklist: TMPDIR,
# WORKLIST_TASKS_DIR and the project root are all isolated fixtures.
set -uo pipefail

# AMBIENT SCRUB, before a single case runs. The hook reads ~65 WORKLIST_* knobs
# and setup() resets only the ones cases set, so anything exported in the shell
# that launches this suite silently retuned it: a developer who set
# WORKLIST_BG_REPORT_MIN or WORKLIST_QUIET_WAKES while debugging would get a
# different suite from CI's, and the difference would look like flakiness rather
# than like configuration. The fixtures were always isolated on DISK (TMPDIR,
# WORKLIST_TASKS_DIR, the project root); this makes them isolated in the
# ENVIRONMENT too. WORKLIST_AGENT_BRANCH and the rest are exported by setup()
# and the cases themselves, after this point, so nothing the suite needs is lost.
#
# CLAUDE_CODE_SESSION_ID IS SCRUBBED TOO, and it is not decoration -- one
# omission here produced two OPPOSITE failures. Since v19 every `<me>` argument
# is checked against the real session id (wl_core.check_me), which resolves
# WORKLIST_SESSION_ID first and CLAUDE_CODE_SESSION_ID second. Run from inside
# a Claude session with the ambient id live, every fixture prefix mismatches and
# ~110 call sites refuse: mass breakage that looks like a broken feature. Run in
# CI with it unset, check_me takes its silent-pass path and every identity case
# passes VACUOUSLY -- a green suite proving nothing, inside the very change
# meant to close a cannot-fire gap. The second is the dangerous one, because it
# is green. Scrubbing makes the suite behave identically in both places, and
# case 200's meta-control below is what proves the scrub actually happened.
while IFS='=' read -r _k _; do
    case "$_k" in
        WORKLIST_* | CLAUDE_CODE_SESSION_ID | CLAUDE_SESSION_ID) unset "$_k" ;;
    esac
done < <(env)
unset _k

HOOK="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/worklist.py"
BASE="$(mktemp -d)/hookfix"
trap 'rm -rf "$(dirname "$BASE")"' EXIT
SID="deadbeef-1111-2222-3333-444444444444"
# ARMED, suite-wide, immediately after the scrub. Every case that drives the CLI
# passes `deadbeef` as its `<me>`, which is a prefix of SID, so one export arms
# the identity check for all of them instead of ~110 edits that would drift. The
# handful of cases modelling a PEER session declare that peer's id per call (see
# as_peer). Exported, not assigned, because the CLI is a child process.
export WORKLIST_SESSION_ID="$SID"
PASS=0
FAIL=0

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
    mkdir -p "$BASE/proj/.agent/agenttest"
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
    printf '%s' "$1" >"$BASE/proj/.agent/agenttest/STATE.md"
}

# The same raw plant, named for what the new cases use it for: a whole
# DOCUMENT (possibly multi-section) placed on disk without going through the
# merge, which is the only way to fabricate a peer's section for a read case.
plant_doc() { # plant_doc <text>
    printf '%s' "$1" >"$BASE/proj/.agent/agenttest/STATE.md"
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

age_state() { # age_state <owner> <minutes-ago> -- backdate that section's stamp
    # The heading stamp is the age source now, so `touch -d` no longer ages a
    # section written by --state: it moves the file's mtime, which is only the
    # FALLBACK for an unstamped section. A case that keeps touching the file
    # would silently test the fallback instead of the rule, so this helper
    # EXITS NON-ZERO when the owner's heading is not there rather than aging
    # nothing and passing quietly.
    python3 - "$BASE/proj/.agent/agenttest/STATE.md" "$1" "$2" <<'PYEOF'
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
    python3 - "$(dirname "$HOOK")" "$BASE/proj/.agent/agenttest/STATE.md" "$1" <<'PYEOF'
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

state_as() { # state_as <prefix> <body> -- merge a section as ANOTHER session
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

echo "== 1. open [ ] blocks =="
setup
say "done for now"
brief_now
hand_now
echo '- [ ] (deadbeef) do the thing' >>"$WL"
check "an open [ ] item blocks" block "OPEN worklist item"

echo "== 2. [?] without DEFAULT blocks =="
setup
say "here is my answer

## Remaining
nothing"
brief_now
hand_now
echo '- [?] (deadbeef) should we do X' >>"$WL"
check "a deferral with no DEFAULT: blocks" block "no DEFAULT:"

echo "== 3. [?] WITH DEFAULT passes that check =="
setup
say "answer

## Remaining
- the X decision"
brief_now
hand_now
echo '- [?] (deadbeef) should we do X DEFAULT: do X on Monday' >>"$WL"
check "a deferral WITH DEFAULT: does not block" allow "operator may answer"

echo "== 4. missing session brief blocks =="
setup
say "answer

## Remaining
- stuff"
echo '- [?] (deadbeef) q DEFAULT: d' >>"$WL"
check "a missing brief blocks" block "session brief is missing"

echo "== 5. STALE brief blocks =="
setup
say "answer

## Remaining
- stuff"
echo '- [?] (deadbeef) q DEFAULT: d' >>"$WL"
printf '%s %s %s\n' deadbeef "$(date -u -d '-200 minutes' +%Y-%m-%dT%H:%M:%SZ)" "old" >>"${WL%.md}.sessions"
check "a stale brief blocks" block "session brief is stale"

echo "== 6. THE HEADLINE: a pending TASK with no ## Remaining blocks =="
setup
say "All done, nothing to report."
brief_now
hand_now
task 7 pending "merge the chain"
check "pending task + no ## Remaining blocks" block "no '## Remaining' section"

echo "== 7. same pending task WITH ## Remaining passes =="
setup
say "Here is the answer.

## Remaining
| #7 | merge the chain | pending, you |"
brief_now
hand_now
task 7 pending "merge the chain"
check "pending task + ## Remaining allowed (judge off)" allow ""

echo "== 8. completed tasks are not remaining work =="
setup
say "All done."
brief_now
hand_now
task 7 completed "merge the chain"
check "a completed task does not demand a Remaining section" allow ""

echo "== 9. WORKLIST_FOCUS=off: ONE block lists EVERY violation =="
# v13 made the FOCUSED single-check block the default; the dump-all contract
# survives behind WORKLIST_FOCUS=off and this case keeps that path exercised.
setup
say "nothing"
echo '- [ ] (deadbeef) open thing' >>"$WL"
echo '- [?] (deadbeef) undefaulted q' >>"$WL"
export WORKLIST_FOCUS=off
out="$(run)"
unset WORKLIST_FOCUS
n=$(grep -o "check(s) failed" <<<"$out" | wc -l)
v=$(python3 -c 'import json,sys;d=json.loads(sys.stdin.read());print(d["reason"].count("\n\n  "))' <<<"$out" 2>/dev/null)
if [[ "$n" -ge 1 && "${v:-0}" -ge 3 ]]; then
    echo "  PASS: one block carries all 3+ violations (found $v)"
    PASS=$((PASS + 1))
else
    echo "  FAIL: expected >=3 violations in one block, got ${v:-0}"
    FAIL=$((FAIL + 1))
fi

echo "== 10. recursion guard =="
setup
echo '- [ ] (deadbeef) open thing' >>"$WL"
out="$(printf '{"session_id":"%s","cwd":"%s","transcript_path":"%s"}' "$SID" "$BASE/proj" "$BASE/t.jsonl" |
    TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" WORKLIST_TASKS_DIR="$BASE/tasks" \
        STOPHOOK_CHILD=1 python3 "$HOOK" 2>&1)"
if [[ -z "$out" ]]; then
    echo "  PASS: STOPHOOK_CHILD=1 exits silently (no recursion)"
    PASS=$((PASS + 1))
else
    echo "  FAIL: guard produced output: ${out:0:120}"
    FAIL=$((FAIL + 1))
fi

echo "== 11. judge failure FAILS CLOSED (no escape hatch) =="
setup
say "waiting on CI.

## Remaining
- #7 merge the chain (pending)"
brief_now
hand_now
task 7 pending "merge the chain"
JUDGE_MODE=on
# A live cron in the event, else the v8 idle check fires statically and the
# stop never reaches the judge path this case exists to pin.
out="$(printf '{"session_id":"%s","cwd":"%s","transcript_path":"%s","session_crons":[{"id":"w","schedule":"17 * * * *"},{"id":"p","schedule":"*/5 * * * *"}]}' "$SID" "$BASE/proj" "$BASE/t.jsonl" |
    TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" WORKLIST_TASKS_DIR="$BASE/tasks" \
        PATH="$BASE/binonly" HOME="$BASE/nohome" GITHUB_ACTIONS="${GHA:-}" python3 "$HOOK" 2>"$BASE/err.txt")"
got="$(python3 -c 'import json,sys
raw=sys.stdin.read().strip()
print(json.loads(raw).get("decision","allow") if raw else "allow")' <<<"$out" 2>/dev/null)"
if [[ "$got" == "block" ]] && grep -qF "no-escape-hatch" <<<"$out"; then
    echo "  PASS: an unreachable judge BLOCKS rather than waving the stop through"
    PASS=$((PASS + 1))
else
    echo "  FAIL: judge failure did not block (got=$got): ${out:0:200}"
    FAIL=$((FAIL + 1))
fi
JUDGE_MODE=off

echo "== 12. nothing tracked anywhere = clean stop, no judge, no block =="
setup
say "All finished."
brief_now
hand_now
check "an empty world allows the stop" allow ""

echo "== 16. a Remaining section that OMITS an open task blocks =="
setup
say "answer

## Remaining
| #7 | thing | pending, me |"
brief_now
hand_now
task 7 pending "thing"
task 8 pending "the forgotten one"
check "an omitted task id blocks" block "OUT OF SYNC"

echo "== 17. naming every open task passes =="
setup
say "answer

## Remaining
| #7 | thing | pending, me |
| #8 | the forgotten one | pending, you |"
brief_now
hand_now
task 7 pending "thing"
task 8 pending "the forgotten one"
check "all task ids named is fine" allow ""

echo "== 18. a MISSING STATE.md blocks when work remains =="
setup
say "answer

## Remaining
- #7 thing (pending)"
brief_now
task 7 pending "thing"
check "a missing STATE.md blocks" block "STATE.md is missing"

echo "== 19. a THIN STATE.md blocks (a stub is not a recovery document) =="
setup
say "answer

## Remaining
- #7 thing (pending)"
brief_now
task 7 pending "thing"
plant_state 'wip'
check "a too-short STATE.md blocks" block "STATE.md is thin"
# 1.4 CONTROL: a SHAPE verdict must carry no age at all. `thin` is about the
# body, and printing a staleness limit beside it suggests that waiting or
# re-stamping would help. Without this control the change above could have
# simply appended a phrase everywhere and still read as wall-clock.
OUT="$(run)"
if ! grep -qE "min old" <<<"$OUT"; then
    pass "212b CONTROL: a thin STATE.md carries no age, because age is irrelevant to shape"
else
    fail "212b CONTROL: a shape verdict printed an age: ${OUT:0:300}"
fi

echo "== 20. PostCompact hands back STATE.md, RULES.md AND the trap titles =="
setup
hand_now
printf 'settled fact: the reconciler exists, never rebuild it\n' >"$BASE/proj/.agent/agenttest/RULES.md"
printf '# Traps\n\n## The review tooling comes from main\n\nbody detail here\n' >"$BASE/proj/.agent/TRAPS.md"
out="$(printf '{"session_id":"%s","cwd":"%s"}' "$SID" "$BASE/proj" |
    TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" WORKLIST_AGENT_BRANCH=agenttest \
        python3 "$HOOK" --post-compact 2>/dev/null)"
if grep -qF "picking up an in-progress session" <<<"$out" && grep -qF "ci-overhaul session" <<<"$out" &&
    grep -qF "settled fact: the reconciler exists" <<<"$out" &&
    grep -qF "The review tooling comes from main" <<<"$out" &&
    ! grep -qF "body detail here" <<<"$out"; then
    echo "  PASS: PostCompact returns STATE + RULES + trap TITLES (never trap bodies)"
    PASS=$((PASS + 1))
else
    echo "  FAIL: PostCompact briefing incomplete or carries trap bodies: ${out:0:300}"
    FAIL=$((FAIL + 1))
fi

echo "== 21. PostCompact with NO STATE.md still tells the session what to do =="
setup
out="$(printf '{"session_id":"%s","cwd":"%s"}' "$SID" "$BASE/proj" |
    TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" python3 "$HOOK" --post-compact 2>/dev/null)"
if grep -qF "NO STATE.md" <<<"$out"; then
    echo "  PASS: a missing STATE.md after compaction is reported, not silent"
    PASS=$((PASS + 1))
else
    echo "  FAIL: missing-STATE.md PostCompact was silent: ${out:0:200}"
    FAIL=$((FAIL + 1))
fi

echo "== 21b. PostCompact puts MY section first and LABELS the peer's =="
# A compacted session reads top-down, and the block it must act on is its own.
# The peer's section rides along because this checkout runs several sessions at
# once and a peer's section is the only place the reader learns which
# uncommitted files are not theirs to sweep -- but it must be unmistakably
# marked as not theirs to rewrite, or the briefing itself becomes the next
# clobber's instruction.
setup
hand_now
PEER_BODY='Session cafe1234 owns packages/cli/src/services/licensing and the two drill scripts under scripts/dev, all of them uncommitted. A git add -A from any other session in this checkout would sweep them into somebody else s commit, which is the cross-session fact that has no home in a per-session file.

## Next action
Finish the renewal drill and report the soft-claim slot count.'
state_as cafe1234 "$PEER_BODY"
out="$(printf '{"session_id":"%s","cwd":"%s"}' "$SID" "$BASE/proj" |
    TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" WORKLIST_AGENT_BRANCH=agenttest \
        python3 "$HOOK" --post-compact 2>/dev/null)"
OWN_AT="$(python3 -c "import sys; print(sys.stdin.read().find('ci-overhaul session'))" <<<"$out")"
PEER_AT="$(python3 -c "import sys; print(sys.stdin.read().find('SESSION cafe1234'))" <<<"$out")"
if [[ "$OWN_AT" -ge 0 && "$PEER_AT" -gt "$OWN_AT" ]] &&
    grep -qF "NOT YOURS" <<<"$out" && grep -qF "owns packages/cli" <<<"$out"; then
    pass "21b: own section first, peer's after it and labelled NOT YOURS"
else
    fail "21b: ordering/labelling wrong (own@$OWN_AT peer@$PEER_AT): ${out:0:300}"
fi
# CONTROL: with no peer section there is no peers block at all, so the label is
# information about the file rather than boilerplate on every briefing.
setup
hand_now
out="$(printf '{"session_id":"%s","cwd":"%s"}' "$SID" "$BASE/proj" |
    TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" WORKLIST_AGENT_BRANCH=agenttest \
        python3 "$HOOK" --post-compact 2>/dev/null)"
if grep -qF "ci-overhaul session" <<<"$out" && ! grep -qF "OTHER SESSIONS' SECTIONS" <<<"$out"; then
    pass "21b CONTROL: a solo document produces no peers block"
else
    fail "21b CONTROL: a peers block appeared with no peers: ${out:0:300}"
fi

echo "== 20b. PostCompact with NO section of MY OWN still hands back the peer's =="
# Before sections, this path returned NO state content whatsoever: a compacted
# session on a branch where only a peer had written was told to reconstruct
# from what survived, while the peer's section sat unread in the file in front
# of it. The instruction to write one must survive too, or this becomes a way
# to inherit a peer's document as your own.
setup
state_as cafe1234 "$PEER_BODY"
out="$(printf '{"session_id":"%s","cwd":"%s"}' "$SID" "$BASE/proj" |
    TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" WORKLIST_AGENT_BRANCH=agenttest \
        python3 "$HOOK" --post-compact 2>/dev/null)"
if grep -qF "NO STATE.md" <<<"$out" && grep -qF "owns packages/cli" <<<"$out" &&
    grep -qF "NOT YOURS" <<<"$out"; then
    pass "20b: the own-missing instruction AND the peer's body are both returned"
else
    fail "20b: the missing branch dropped the peer's section: ${out:0:300}"
fi

echo "== 22. an UNREADABLE transcript blames the HOOK, not the session =="
setup
brief_now
hand_now
task 7 pending "thing"
out="$(printf '{"session_id":"%s","cwd":"%s","transcript_path":"%s"}' "$SID" "$BASE/proj" "$BASE/does-not-exist.jsonl" |
    TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" WORKLIST_TASKS_DIR="$BASE/tasks" \
        WORKLIST_JUDGE=off GITHUB_ACTIONS="${GHA:-}" python3 "$HOOK" 2>/dev/null)"
if grep -qF "THIS IS A HOOK BUG" <<<"$out" && grep -qF '"decision": "block"' <<<"$out"; then
    echo "  PASS: a blind read blocks AND says it is the hook's fault"
    PASS=$((PASS + 1))
else
    echo "  FAIL: blind read not distinguished: ${out:0:200}"
    FAIL=$((FAIL + 1))
fi

echo "== 23. a heading that lands LATE is still honoured (flush race) =="
setup
brief_now
hand_now
task 7 pending "thing"
say "answer with no section yet"
(
    sleep 0.6
    say "answer

## Remaining
- #7 thing (pending)"
) &
check "a heading written mid-check is picked up by the retry" allow ""
wait

echo "== 24. THE REGRESSION: narration blocks after the answer must not hide it =="
# Every narration line before a tool call is its own assistant text block, so
# reading only the LAST block sees a one-liner and calls the section missing.
# This fired on a real message that did carry its heading.
setup
brief_now
hand_now
task 7 pending "thing"
say "Here is the answer.

## Remaining
| #7 | thing | pending, me |"
say "Checking one more thing."
say "And another."
check "a Remaining section survives later narration blocks" allow ""

echo "== 25. TWO LIVE work crons block, read from the event not a declaration =="
setup
brief_now
hand_now
say "answer

## Remaining
- #7 thing (pending)"
task 7 pending "thing"
CRONS='[{"id":"aaa","schedule":"*/23 * * * *"},{"id":"bbb","schedule":"17 * * * *"},{"id":"p","schedule":"*/5 * * * *"}]'
check "two live work crons block" block "2 work crons are live"
CRONS='[]'

echo "== 26. the canonical shape (one work cron + the poll) does not block =="
setup
brief_now
hand_now
say "answer

## Remaining
- #7 thing (pending)"
task 7 pending "thing"
CRONS='[{"id":"bbb","schedule":"17 * * * *"},{"id":"p","schedule":"*/5 * * * *"}]'
check "work cron + poll cron is fine" allow ""
CRONS='[]'

echo "== 27. 'blocked on You' WITHOUT confirmation blocks =="
setup
brief_now
hand_now
say "answer

## Remaining
| #7 | thing | pending, You |"
task 7 pending "thing"
check "an unconfirmed operator-block is rejected" block "WITHOUT their confirmation"

echo "== 28. the confirmed form passes =="
setup
brief_now
hand_now
say "answer

## Remaining
| #7 | thing | pending, You (User Thinks So) |"
task 7 pending "thing"
check "the confirmed operator-block is accepted" allow ""

echo "== 29. a BLOATED STATE.md is rejected (it is a prompt, not a report) =="
# .agent split: the cap moved 1500 -> 4000. Rules and traps left the budget,
# so STATE.md needs room for state alone; 4000 still refuses a pasted
# transcript. The boundary pair pins the new edge, and both bodies carry the
# '## Next action' section so length is the ONLY variable under test.
setup
brief_now
say "answer

## Remaining
- #7 thing (pending)"
task 7 pending "thing"
plant_state "$(python3 -c "print('## Next action\\ngo\\n' + 'x'*4100)")"
check "an over-long STATE.md blocks" block "STATE.md is bloated"
plant_state "$(python3 -c "print('## Next action\\ngo\\n' + 'x'*3900)")"
check "3900-odd chars sits inside the new 4000 budget" allow ""

echo "== 30. AIMLESS: a STATE.md without a Next action section blocks =="
# The paragraph guard is DELETED: it was an explicit proxy for the old
# 600-char cap and split("\n\n") counted every markdown heading as a
# paragraph, which is why the old message had to forbid headings outright.
# `aimless` is the strictly better gate: presence of a next action IS the
# value, and padding cannot satisfy it. Three probes: FIRE without the
# section, SILENT with it, SILENT with unusual case (the regex is
# case-insensitive on purpose; a shouted heading is still a next action).
setup
brief_now
say "answer

## Remaining
- #7 thing (pending)"
task 7 pending "thing"
plant_state 'You are picking up the ci-overhaul session driving PR #543 to green on branch 0728-2, where the immediate job is to watch the running CI round and diagnose any red from its complete failed-step log before changing anything at all. Padding padding padding padding to comfortably clear the thin floor of the shape gate.'
check "a STATE.md with no Next action section is aimless and blocks" block "STATE.md is aimless"
plant_state 'You are picking up the ci-overhaul session driving PR #543 to green on branch 0728-2, where the immediate job is to watch the running CI round and diagnose any red from its complete failed-step log before changing anything at all.

## Next action

Watch the run and diagnose from the job logs API.'
check "the same document WITH a Next action section is fine" allow ""
# Case-insensitivity probed as a UNIT assertion rather than a third stop:
# three consecutive stops on an unmoved world trip the stuck detector, which
# would make this case test the wrong gate.
if python3 -c "
import sys; sys.path.insert(0, '$(dirname "$HOOK")')
import wl_store as S
v, _ = S.agent_state_shape('x'*260 + chr(10) + '## NEXT ACTION' + chr(10) + 'go')
sys.exit(0 if v == 'ok' else 1)"; then
    pass "the Next action heading is matched case-insensitively"
else
    fail "a shouted '## NEXT ACTION' heading was not recognised"
fi

echo "== 29b. --state REFUSES a bad body instead of accepting then blocking =="
# The old write path once accepted ANY body and let the Stop check reject it a
# stop later, leaving the compaction-recovery artifact broken while the session
# believed it was fine. Each rejection is paired with the ALLOW control so the
# guard cannot pass by refusing everything, and the final assert is a byte cmp,
# not a hook allow: a refused write must leave the previous document IDENTICAL.
setup
brief_now
hand_now # a GOOD STATE.md is already on disk; a refused write must not destroy it
STATE_FILE="$BASE/proj/.agent/agenttest/STATE.md"
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
if grep -qF "This is session B" "$STATE_FILE" && grep -qF "ci-overhaul session" "$STATE_FILE"; then
    pass "29f: the merged document carries BOTH sections"
else
    fail "29f: a section is missing from the merged document: $(head -c 200 "$STATE_FILE")"
fi
# CONTROL: B writing AGAIN replaces only B's section. Without this the case
# would pass on a tool that merely refused to write anything at all.
B_ONE="$(section_of cafe1234)"
sleep 1 # so an advanced stamp is observable at second resolution
state_as cafe1234 "${B_BODY/session B/session B, round two}"
if [[ "$(section_of deadbeef)" == "$A_BEFORE" ]] &&
    [[ "$(section_of cafe1234)" != "$B_ONE" ]] &&
    grep -qF "round two" "$STATE_FILE"; then
    pass "29f CONTROL: a second write replaces only its own section, A untouched"
else
    fail "29f CONTROL: the second write hit the wrong section"
fi

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
REAPED="${REAPED%.md}.agentstate.reaped.agenttest.md"
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
REAPED="${REAPED%.md}.agentstate.reaped.agenttest.md"
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
BACKUP="${BACKUP%.md}.agentstate.prev.agenttest.md"
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
# the backup to cover is a bug in the MERGE itself, which is why the copy is of
# the whole outgoing document and why one slot is enough. The assertions moved
# from `== $VICTIM` to "contains VICTIM", because the outgoing document now
# holds every section rather than just the one being replaced.
setup
brief_now
hand_now # writes STATE_BODY
STATE_FILE="$BASE/proj/.agent/agenttest/STATE.md"
BACKUP="$(TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" python3 "$HOOK" --path)"
# Branch-scoped since the 2026-07-31 review round: one shared slot let a
# write on ANOTHER branch destroy this branch's only backup.
BACKUP="${BACKUP%.md}.agentstate.prev.agenttest.md"
VICTIM='This is the document a SECOND session wrote and must be able to get back. It carries the one fact that would otherwise die with it: PR #547 merged to main at 01:30Z, so the nightly is now watchable on main rather than on the branch.

## Next action
Watch the scheduled nightly run on main and diagnose any red from its full log.'
printf '%s' "$VICTIM" |
    TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" WORKLIST_AGENT_BRANCH=agenttest \
        python3 "$HOOK" --state deadbeef >/dev/null 2>&1
out="$(printf '%s' "$STATE_BODY" |
    TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" WORKLIST_AGENT_BRANCH=agenttest \
        WORKLIST_SESSION_ID="$(peer_id cafe1234)" python3 "$HOOK" --state cafe1234 2>&1)"
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

echo "== 29d. the backup slot is BRANCH-scoped, and a failed copy is confessed =="
# Review findings 3688784930/3688787780 (shared slot across branches) and
# 3688770247/3688779150/3688787850 (success line claimed a backup the failed
# write never created).
setup
brief_now
hand_now # branch agenttest, STATE_BODY
STATE_A="$BASE/proj/.agent/agenttest/STATE.md"
BACKUP_A="$(TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" python3 "$HOOK" --path)"
BACKUP_B="${BACKUP_A%.md}.agentstate.prev.otherbranch.md"
BACKUP_A="${BACKUP_A%.md}.agentstate.prev.agenttest.md"
VICT_A='Branch A victim body, deliberately long enough for the shape gate to accept it as a real state document (the gate refuses anything under 250 characters as thin, and an earlier draft of this very fixture was refused exactly that way, which is why this sentence exists). It carries the one fact only this branch-A document holds.

## Next action
Recover me from the branch-A backup and nothing else.'
printf '%s' "$VICT_A" |
    TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" WORKLIST_AGENT_BRANCH=agenttest \
        python3 "$HOOK" --state deadbeef >/dev/null 2>&1
printf '%s' "$STATE_BODY" |
    TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" WORKLIST_AGENT_BRANCH=agenttest \
        WORKLIST_SESSION_ID="$(peer_id cafe1234)" python3 "$HOOK" --state cafe1234 >/dev/null 2>&1
mkdir -p "$BASE/proj/.agent/otherbranch"
printf '%s' "$STATE_BODY" |
    TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" WORKLIST_AGENT_BRANCH=otherbranch \
        python3 "$HOOK" --state deadbeef >/dev/null 2>&1
printf '%s' "$VICT_A" |
    TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" WORKLIST_AGENT_BRANCH=otherbranch \
        WORKLIST_SESSION_ID="$(peer_id cafe1234)" python3 "$HOOK" --state cafe1234 >/dev/null 2>&1
if grep -qF "Recover me from the branch-A backup" "$BACKUP_A" 2>/dev/null &&
    grep -qF "Round 23 went red" "$BACKUP_B" 2>/dev/null &&
    ! grep -qF "Recover me from the branch-A backup" "$BACKUP_B" 2>/dev/null; then
    pass "29d: each branch keeps its own backup; a write elsewhere cannot destroy it"
else
    fail "29d: cross-branch write clobbered the backup (A: $(head -c 40 "$BACKUP_A" 2>&1))"
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

echo "== 31. design-doc DRIFT blocks =="
setup
brief_now
hand_now
say "answer

## Remaining
- #7 thing (pending)"
task 7 pending "thing"
mkdir -p "$BASE/proj/docs/ci-overhaul"
echo "# design" >"$BASE/proj/docs/ci-overhaul/README.md"
(
    cd "$BASE/proj" || exit
    git init -q 2>/dev/null
    git config user.email t@t
    git config user.name t
    mkdir -p .ci
    git add -A >/dev/null 2>&1
    git commit -qm docs 2>/dev/null
    for i in $(seq 1 12); do
        echo "$i" >".ci/f$i.sh"
        git add -A >/dev/null 2>&1
        git commit -qm "code $i" 2>/dev/null
    done
) >/dev/null 2>&1
check "12 code commits with untouched docs block" block "design docs have DRIFTED"

echo "== 32. no drift once the docs move with the code =="
(
    cd "$BASE/proj" || exit
    echo "# updated" >>docs/ci-overhaul/README.md
    git add -A >/dev/null 2>&1
    git commit -qm "docs refresh" 2>/dev/null
) >/dev/null 2>&1
check "docs updated after the code clears the drift" allow ""

echo "== 33. SessionStart hands the design docs to a new session =="
out="$(printf '{"session_id":"%s","cwd":"%s"}' "$SID" "$BASE/proj" |
    TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" python3 "$HOOK" --session-start 2>/dev/null)"
if grep -qF "READ ALL OF THEM" <<<"$out" && grep -qF "docs/ci-overhaul/README.md" <<<"$out"; then
    echo "  PASS: SessionStart lists the docs and demands they be read"
    PASS=$((PASS + 1))
else
    echo "  FAIL: SessionStart did not surface the docs: ${out:0:200}"
    FAIL=$((FAIL + 1))
fi

echo "== 34. a LOOP THAT DIED blocks (had crons, now none) =="
setup
brief_now
hand_now
say "answer

## Remaining
- #7 thing (pending)"
task 7 pending "thing"
CRONS='[{"id":"bbb","schedule":"17 * * * *"},{"id":"p","schedule":"*/5 * * * *"}]'
run >/dev/null
CRONS='[]'
check "losing the last cron blocks" block "WORK LOOP DIED"

echo "== 35. a session that NEVER had a cron is not nagged =="
setup
brief_now
hand_now
say "answer

## Remaining
- #7 thing (pending)"
task 7 pending "thing"
# No cron ever, but a running background agent, so the v8 idle check stays
# quiet and this case keeps pinning ONLY the loop-died non-fire.
CRONS='[]'
BG='[{"status":"running","description":"agent"}]'
check "no cron ever means no complaint" allow ""

echo "== 34b. DECLARING the loop finished clears it, and STAYS cleared =="
# V_LOOP_DIED offers two exits: recreate the cron, or say the loop is
# deliberately finished. The second one did not exist -- cron_memory never read
# the message -- so a session that retired its cron on purpose and said so was
# blocked on every stop after, with no wording that could satisfy it. The final
# assert is the one that matters: the declaration must FORGET the high-water
# mark, not skip a single stop, or the block returns next stop forever.
setup
brief_now
hand_now
task 7 pending "thing"
# A live background agent, exactly as case 35 does. Without it the repeated
# stops in this case trip the idle check and the 3-identical-stops check, and
# the assertion then fails on THEIR reasons while V_LOOP_DIED is already clear
# -- a confound that made this very case red on its first run.
BG='[{"status":"running","description":"agent"}]'
CRONS='[{"id":"bbb","schedule":"17 * * * *"},{"id":"p","schedule":"*/5 * * * *"}]'
say "answer

## Remaining
- #7 thing (pending)"
run >/dev/null
CRONS='[]'
# CONTROL first: the SAME world without the declaration must still block, or
# the case proves nothing about the declaration.
check "CONTROL: no declaration, the dead loop still blocks" block "WORK LOOP DIED"
say 'The campaign is done, so the loop is deliberately finished and I retired the cron.

## Remaining
- #7 thing (pending)'
check "declaring the loop deliberately finished clears it" allow ""
check "and it STAYS cleared on the next stop" allow ""

echo "== 34c. CONTROL: merely QUOTING the instruction does NOT opt out =="
# This is an opt-out, so it must survive being written about: every message
# that discusses this check quotes its own instruction text back. Stripping
# quoted and backticked spans before matching is what keeps that honest.
setup
brief_now
hand_now
task 7 pending "thing"
BG='[{"status":"running","description":"agent"}]'
CRONS='[{"id":"bbb","schedule":"17 * * * *"},{"id":"p","schedule":"*/5 * * * *"}]'
say "answer

## Remaining
- #7 thing (pending)"
run >/dev/null
CRONS='[]'
say 'The hook says to recreate it or "say out loud in your message that the loop is deliberately finished", and `the loop is deliberately finished` is the phrase it wants.

## Remaining
- #7 thing (pending)'
check "a quoted/backticked mention does NOT switch the check off" block "WORK LOOP DIED"

echo "== 36. a STALE LOCAL branch sharing the publish name blocks =="
setup
brief_now
hand_now
task 7 pending "thing"
(
    cd "$BASE/proj" || exit
    git init -q 2>/dev/null
    git config user.email t@t
    git config user.name t
    echo a >a.txt
    git add -A
    git commit -qm base
    git branch -f pub HEAD
    echo b >b.txt
    git add -A
    git commit -qm newer
    git update-ref refs/remotes/origin/pub "$(git rev-parse HEAD)"
) >/dev/null 2>&1
out="$(printf '{"session_id":"%s","cwd":"%s","last_assistant_message":"x\\n\\n## Remaining\\n- #7 thing (pending)","session_crons":[]}' "$SID" "$BASE/proj" |
    TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" WORKLIST_TASKS_DIR="$BASE/tasks" \
        WORKLIST_PUBLISH_REF=pub WORKLIST_JUDGE=off GITHUB_ACTIONS="${GHA:-}" python3 "$HOOK" 2>/dev/null)"
if grep -qF "is a trap for whoever checks it out" <<<"$out"; then
    echo "  PASS: a stale local branch sharing the publish name blocks"
    PASS=$((PASS + 1))
else
    echo "  FAIL: stale local branch not detected: ${out:0:220}"
    FAIL=$((FAIL + 1))
fi

echo "== 37. PR-freshness: a push after the last body edit blocks =="
setup
brief_now
hand_now
task 7 pending "thing"
(
    cd "$BASE/proj" || exit
    git init -q 2>/dev/null
    git config user.email t@t
    git config user.name t
    git remote add origin https://github.com/fake/repo.git 2>/dev/null
    echo a >a.txt
    git add -A
    git commit -qm base
    git update-ref refs/remotes/origin/pub "$(git rev-parse HEAD)"
) >/dev/null 2>&1
# A gh shim that answers the GraphQL read with a body edited in 1970, i.e. long
# before any commit. The gate under test is the real one.
cat >"$BASE/binonly/gh" <<'SHIM'
#!/bin/bash
echo '{"data":{"repository":{"pullRequests":{"nodes":[{"number":9,"lastEditedAt":"1970-01-01T00:00:00Z","updatedAt":"1970-01-01T00:00:00Z"}]}}}}'
SHIM
chmod +x "$BASE/binonly/gh"
out="$(printf '{"session_id":"%s","cwd":"%s","last_assistant_message":"x\\n\\n## Remaining\\n- #7 thing (pending)","session_crons":[]}' "$SID" "$BASE/proj" |
    PATH="$BASE/binonly:$PATH" TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" \
        WORKLIST_TASKS_DIR="$BASE/tasks" WORKLIST_PUBLISH_REF=pub WORKLIST_JUDGE=off \
        GITHUB_ACTIONS="${GHA:-}" python3 "$HOOK" 2>/dev/null)"
if grep -qF "PUSHED AFTER YOUR LAST PR-DESCRIPTION EDIT" <<<"$out"; then
    echo "  PASS: pushing after the body edit blocks before CI can waste a round"
    PASS=$((PASS + 1))
else
    echo "  FAIL: stale PR body not detected: ${out:0:220}"
    FAIL=$((FAIL + 1))
fi

echo "== 38. PR-freshness: a body edited AFTER the tip passes =="
cat >"$BASE/binonly/gh" <<'SHIM'
#!/bin/bash
echo '{"data":{"repository":{"pullRequests":{"nodes":[{"number":9,"lastEditedAt":"2999-01-01T00:00:00Z","updatedAt":"2999-01-01T00:00:00Z"}]}}}}'
SHIM
chmod +x "$BASE/binonly/gh"
out="$(printf '{"session_id":"%s","cwd":"%s","last_assistant_message":"x\\n\\n## Remaining\\n- #7 thing (pending)","session_crons":[]}' "$SID" "$BASE/proj" |
    PATH="$BASE/binonly:$PATH" TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" \
        WORKLIST_TASKS_DIR="$BASE/tasks" WORKLIST_PUBLISH_REF=pub WORKLIST_JUDGE=off \
        GITHUB_ACTIONS="${GHA:-}" python3 "$HOOK" 2>/dev/null)"
if grep -qF "PUSHED AFTER" <<<"$out"; then
    echo "  FAIL: a fresh body must not block: ${out:0:200}"
    FAIL=$((FAIL + 1))
else
    echo "  PASS: a body newer than the tip does not block"
    PASS=$((PASS + 1))
fi
rm -f "$BASE/binonly/gh"

echo "== 39. an item listed with NO state word blocks =="
setup
brief_now
hand_now
say "answer

## Remaining
| #7 | thing | me |"
task 7 pending "thing"
check "a stateless remaining item blocks" block "listed without a STATE"

echo "== 40. saying 'ongoing' while the app says pending blocks =="
setup
brief_now
hand_now
say "answer

## Remaining
| #7 | thing | ongoing, me |"
task 7 pending "thing"
check "message and task list must agree" block "DISAGREES with the task list"

echo "== 41. 'ongoing' matches an in_progress task =="
setup
brief_now
hand_now
say "answer

## Remaining
| #7 | thing | ongoing, me |"
task 7 in_progress "thing"
check "an in_progress task labelled ongoing is fine" allow ""

echo "== 41b. literal 'in_progress' (underscore) is recognized as the state word, even with a later 'pending' in the same line =="
setup
brief_now
hand_now
say "answer

## Remaining
| #7 | **in_progress** | demo done; another observation still pending -- blocked on X |"
task 7 in_progress "thing"
check "in_progress spelled with an underscore is not skipped in favour of a later 'pending'" allow ""

echo "== 42. a 'found, not fixed' list blocks: fix it or track it =="
setup
brief_now
hand_now
say "answer

Found, not fixed: CLAUDE.md points at a dead endpoint.

## Remaining
| #7 | thing | pending, me |"
task 7 pending "thing"
check "reporting instead of fixing blocks" block "CLAUDE.md's rule is to FIX"

echo "== 43b. MENTIONING the phrase mid-sentence must NOT block =="
setup
brief_now
hand_now
say "answer

The hook now blocks on a found, not fixed list, and I described that as
\"Found, not fixed\" is now a blocking phrase.

## Remaining
| #7 | thing | pending, me |"
task 7 pending "thing"
check "describing the check does not trip it" allow ""

echo "== 43. the same message without that phrase passes =="
setup
brief_now
hand_now
say "answer

## Remaining
| #7 | thing | pending, me |"
task 7 pending "thing"
check "no found-not-fixed list, no complaint" allow ""

echo "== 44. a STATE.md just over the limit is STALE (the limit is load-bearing) =="
# NOTE: 44 and 45 are ONE indivisible fixture; 45 has no setup of its own and
# re-stamps the section 44 planted. Do not reorder or insert a setup between
# them.
setup
brief_now
hand_now
say "answer

## Remaining
| #7 | thing | pending, me |"
task 7 pending "thing"
# Age it past the default without touching the clock. AGE COMES FROM THE
# SECTION'S HEADING STAMP since 2026-08-09, not from the file's mtime, so this
# re-stamps the section rather than touching the file: mtime is per FILE while
# the obligation is per SESSION, and a peer's write used to reset everyone's
# clock. `touch -d` here would silently exercise the unstamped fallback instead
# of the rule under test.
# The limit is 15 minutes, and the pair BRACKETS it: 16 must block, 14 must
# not. A single far-past fixture would keep passing if the constant were
# raised to an hour by accident. The world has moved since hand_now banked the
# signature (task 7 landed after), so world-keyed staleness is armed.
age_state deadbeef 16
check "a 16-minute-old STATE.md blocks at the 15-minute limit" block "STATE.md is stale"

echo "== 45. and one just inside it does not =="
age_state deadbeef 14
check "a 14-minute-old STATE.md is inside the 15-minute limit" allow ""

echo "== 44b. staleness is PER SESSION: one session's write cannot silence another =="
# THE OTHER HALF OF THE 2026-08-09 INCIDENT, and the half that made the first
# half inevitable. Age used to come from the file's MTIME, which is per FILE,
# while the recorded signature is per SESSION. So a peer's write reset
# everyone's clock: session B's 30-minute-stale document read "ok" the instant
# session A wrote, and -- worse than a skipped stop -- wl_checks then banked
# A's world signature as B's own, so B adopted a document describing A's world
# as its own recovery artifact. Reproduced against the real function before the
# fix: ('stale', 30) became ('ok', 0) purely because A wrote.
#
# A mutation that reverts the age source to p.stat().st_mtime must turn this
# case red.
setup
brief_now
brief_other cafe1234
hand_now # A = deadbeef, stamped now
B_BODY='Session B is holding the canary campaign: attempt 6 is in flight behind watch id 9be21c, five flags are flipped, and v1.2.24 is released. None of this is session A material and none of it may be silenced by session A writing.

## Next action
Read attempt 6 to completion and record the flag states before touching anything.'
state_as cafe1234 "$B_BODY"
age_state cafe1234 30 # B is stale; A is not. A's write above is the "peer write".
# B needs work of its OWN outstanding, because the STATE.md violation only
# fires when something remains for that session: the tasks in the fixture dir
# are keyed to `deadbeef`, so without this B has an empty plate and the case
# would pass vacuously by never reaching the check under test.
as_peer cafe1234 reqcli --add cafe1234 "B's own open item" >/dev/null
task 7 pending "thing"
newturn
say "answer

## Remaining
- #7 thing (pending)"
B_SIG_BEFORE="$(python3 -c "
import json, pathlib
p = pathlib.Path('${WL%.md}.state-cafe1234.json')
print(json.loads(p.read_text()).get('state_sig', '') if p.exists() else '')")"
# FOCUS=off for B's two stops. B legitimately has TWO violations (its open item
# and its stale section) and the focus mechanism surfaces one, so a focused run
# would assert the needle's absence for a reason that has nothing to do with
# the rule under test -- and the anti-vacuity control below would then pass on
# a hook that never computed staleness at all.
export WORKLIST_FOCUS=off
check_as cafe1234 "44b FIRE: the STALE session B is nagged" block "STATE.md is stale"
unset WORKLIST_FOCUS
check "44b: session A, fresh, is NOT nagged by B's staleness" allow ""
# THE BANKING HALF, which is worse than the skipped stop it hid behind. On a
# "stale" verdict nothing may be banked, or the next stop would compare against
# a signature recorded DURING the block and clear itself. Under the mtime bug B
# got an "ok" verdict off A's write and banked A's world as its own.
B_SIG_AFTER="$(python3 -c "
import json, pathlib
p = pathlib.Path('${WL%.md}.state-cafe1234.json')
print(json.loads(p.read_text()).get('state_sig', '') if p.exists() else '')")"
if [[ -n "$B_SIG_BEFORE" && "$B_SIG_BEFORE" == "$B_SIG_AFTER" ]]; then
    pass "44b: B's banked signature is untouched by its stale block and by A's stop"
else
    fail "44b: B's signature moved during the block ('${B_SIG_BEFORE:0:12}' -> '${B_SIG_AFTER:0:12}')"
fi
# ANTI-VACUITY. Re-stamp B fresh: the nag must go away. Without this the case
# would pass on a hook that simply blocks every peer for every reason.
age_state cafe1234 1
export WORKLIST_FOCUS=off
OUT="$(run_as cafe1234)"
unset WORKLIST_FOCUS
# The second half of the anti-vacuity: B must still be SPEAKING (it still owns
# an open item), so the missing needle is the staleness verdict changing rather
# than the hook having gone quiet.
if ! grep -qF "STATE.md is stale" <<<"$OUT" && grep -qF "OPEN worklist item" <<<"$OUT"; then
    pass "44b ANTI-VACUITY: a freshly stamped section B is no longer nagged"
else
    fail "44b ANTI-VACUITY: B is nagged even when fresh, or went silent: ${OUT:0:220}"
fi

echo "== 44c. a FUTURE heading stamp cannot buy permanent freshness =="
# FOUND ON THE LIVE DOCUMENT, not imagined: driving this code against the real
# .agent/main/STATE.md for the first time showed a peer's hand-written heading
# stamped 101 minutes AHEAD -- almost certainly local time written with a Z. A
# trusted future stamp makes that section permanently fresh, which is worse
# than the unstamped fallback it would otherwise have taken, because the entire
# point of per-section staleness is that a section cannot dodge its own clock.
# A future stamp is therefore treated exactly like an unparseable one.
setup
brief_now
hand_now
say "answer

## Remaining
| #7 | thing | pending, me |"
task 7 pending "thing"
age_state deadbeef -60                                           # stamped an hour AHEAD
touch -d '40 minutes ago' "$BASE/proj/.agent/agenttest/STATE.md" # the honest age
check "44c FIRE: a future-stamped section falls back to mtime and goes stale" block "STATE.md is stale"
# CONTROL 1: a stamp inside the tolerated skew is still TRUSTED, so this is a
# rule about wrong clocks rather than a blanket distrust of the future.
age_state deadbeef -2
check "44c CONTROL: a stamp 2 minutes ahead is inside the skew and stays fresh" allow ""
# CONTROL 2: and the fallback is really the mtime, not a hardcoded stale. Same
# future stamp, fresh file: allowed.
age_state deadbeef -60
touch -d '1 minute ago' "$BASE/proj/.agent/agenttest/STATE.md"
task 8 pending "moved"
newturn
say "answer

## Remaining
| #7 | thing | pending, me |
| #8 | moved | pending, me |"
check "44c CONTROL: the untrusted stamp falls back to mtime, which here is fresh" allow ""

echo "== 46. CONTROL: an open item still blocks off a runner =="
setup
brief_now
hand_now
say "answer

## Remaining
| #7 | thing | pending, me |"
task 7 pending "thing"
printf -- '- [ ] (deadbeef) an item nobody will ever answer\n' >>"$WL"
check "an open item blocks in a normal session" block "OPEN worklist item"

echo "== 47. and the SAME state no-ops under GITHUB_ACTIONS =="
# Same worklist, same open item, one env var different. Without the control
# above this would pass even if the hook had stopped blocking entirely.
GHA=true check "GITHUB_ACTIONS=true never blocks a runner" allow ""

echo "== 48. a value other than 'true' is NOT a runner =="
GHA=false check "GITHUB_ACTIONS=false still blocks" block "OPEN worklist item"

echo "== 49. CONTROL: two identical stops do NOT trip the stuck check =="
setup
brief_now
hand_now
say "answer

## Remaining
| #7 | thing | pending, me |"
task 7 pending "thing"
check "stop 1 of 3 is quiet" allow ""
check "stop 2 of 3 is still quiet" allow ""

echo "== 50. the THIRD identical stop demands an agent =="
check "3 stops with nothing moved blocks" block "EMPLOY A PLANNING OR INVESTIGATION AGENT"

echo "== 51. and it RESETS, so stop 4 is quiet again =="
check "the nag is rate-limited, not every-stop" allow ""

# 51b. THE DEFERRAL BLIND SPOT. The stuck check used to fire on
# `something_remains`, which counts `[?]` deferrals. A `[?]` is BY CONSTRUCTION
# the one shape a session cannot advance -- it is parked on the operator's
# decision or on a capability only they hold -- so "nothing moved" is the
# CORRECT outcome there, not a stall, and the remedy the check prints (delegate
# to a Plan/Explore agent) cannot work: the constraint is authority, not
# knowledge. Measured 2026-08-15, the two survivors were "set four Worker
# secrets with the operator's Cloudflare session" and "delete the last restore
# path once a machine has round-tripped a repo". The only way to satisfy the
# check was to spawn a decorative agent, i.e. to game it.
#
# `[>]` deliberately still counts as actionable (case 53 covers it): work on a
# worker genuinely can stall, and the bg-wait check reports that separately.
echo "== 51b. CONTROL: with ONLY [?] deferrals left, the stuck check stays quiet =="
setup
brief_now
hand_now
say "answer

## Remaining
| #7 | blocked on the operator | deferred |"
echo '- [?] (deadbeef) set the four Worker secrets DEFAULT: hold, it needs the operator session' >>"$WL"
check "deferral-only stop 1 is quiet" allow ""
check "deferral-only stop 2 is quiet" allow ""
# The third identical stop is where case 50 fires. It must NOT here.
check "deferral-only stop 3 does NOT demand an agent" allow ""

echo "== 51c. and one OPEN item alongside the deferral restores the demand =="
setup
brief_now
hand_now
say "answer

## Remaining
| #7 | thing | pending, me |"
echo '- [?] (deadbeef) a parked question DEFAULT: hold' >>"$WL"
echo '- [ ] (deadbeef) something I can actually do' >>"$WL"
# An open item blocks EVERY stop on its own account, so these two assert the
# OTHER blocker by name -- the point is that the stuck demand is absent until
# the third stop, and then present.
check "mixed stop 1 blocks on the open item, not the stuck check" block "OPEN worklist item"
check "mixed stop 2 blocks on the open item, not the stuck check" block "OPEN worklist item"
check "an actionable item alongside a deferral still trips it" block "EMPLOY A PLANNING OR INVESTIGATION AGENT"

echo "== 52. a task changing status counts as movement =="
setup
brief_now
hand_now
say "answer

## Remaining
| #7 | thing | pending, me |"
task 7 pending "thing"
check "fresh signature, stop 1" allow ""
check "fresh signature, stop 2" allow ""
# Same session, but the task moved. The counter must restart, not fire.
task 7 in_progress "thing"
newturn
say "answer

## Remaining
| #7 | thing | ongoing, me |"
check "moving a task resets the stuck counter" allow ""

echo "== 53. a running background task exempts it (an agent IS the remedy) =="
setup
brief_now
hand_now
say "answer

## Remaining
| #7 | thing | pending, me |"
task 7 pending "thing"
BG='[{"status":"running","description":"plan agent"}]'
BG="$BG" check "stop 1" allow ""
BG="$BG" check "stop 2" allow ""
BG="$BG" check "a live agent means the remedy is already running" allow ""

echo "== 54. THE MISSING CONTROL: a COMMIT must move the signature =="
# Its absence is why a dead HEAD leg shipped. The hook resolved the repo from
# the worklist tmp dir, git returned nothing, and every commit was invisible.
setup
git -C "$BASE/proj" init -q 2>/dev/null
git -C "$BASE/proj" config user.email t@t
git -C "$BASE/proj" config user.name t
echo one >"$BASE/proj/f"
git -C "$BASE/proj" add f
git -C "$BASE/proj" commit -qm one
brief_now
hand_now
say "answer

## Remaining
| #7 | thing | pending, me |"
task 7 pending "thing"
check "stop 1" allow ""
check "stop 2" allow ""
# A real commit between stops. If HEAD is wired, this resets tasks+head.
echo two >>"$BASE/proj/f"
git -C "$BASE/proj" commit -qam two
newturn
say "answer

## Remaining
| #7 | thing | pending, me |"
check "a commit resets the tasks+head counter" allow ""

echo "== 55. but a commit buys SLACK, not immunity: tasks-only still fires =="
# Commit every round; the tasks-only signature never moves, so at 2x it fires.
# case 54 already spent 3 stops; tasks-only fires at 2x STUCK_ROUNDS = 6, so
# exactly 3 more land ON the fire rather than past its reset.
for i in 4 5 6; do
    echo "c$i" >>"$BASE/proj/f"
    git -C "$BASE/proj" commit -qam "c$i"
    newturn
    say "answer

## Remaining
| #7 | thing | pending, me |"
    LAST="$(run)"
done
if grep -qF "EMPLOY A PLANNING OR INVESTIGATION AGENT" <<<"$LAST" &&
    grep -qF "Commits do not count as movement here" <<<"$LAST"; then
    echo "  PASS: the commit-trivia treadmill still trips the tasks-only tier"
    PASS=$((PASS + 1))
else
    echo "  FAIL: committing every round escaped the stuck check"
    echo "        out: ${LAST:0:220}"
    FAIL=$((FAIL + 1))
fi

echo "== 56. THE WAVE C REPLAY: an uncited prose blocker blocks =="
setup
brief_now
hand_now
# The exact line that started this, verbatim in shape.
say "answer

## Remaining
| #12 | Wave C autopilot | blocked on Wave B landing |"
task 12 pending "Wave C autopilot"
check "an uncited blocker blocks" block "carries no <path>:<line> citation"

echo "== 57. citing a REAL line clears it =="
setup
brief_now
hand_now
mkdir -p "$BASE/proj/docs"
printf 'a\nb\nc\nd\ne\n' >"$BASE/proj/docs/guide.md"
say "answer

## Remaining
| #12 | Wave C autopilot | blocked, docs/guide.md:3 |"
task 12 pending "Wave C autopilot"
check "a citation that resolves is accepted" allow ""

echo "== 58. CONTROL: a citation past end-of-file is NOT accepted =="
setup
brief_now
hand_now
mkdir -p "$BASE/proj/docs"
printf 'a\nb\nc\nd\ne\n' >"$BASE/proj/docs/guide.md"
say "answer

## Remaining
| #12 | Wave C autopilot | blocked, docs/guide.md:900 |"
task 12 pending "Wave C autopilot"
check "a fabricated line number is caught" block "has only 5 lines"

echo "== 59. CONTROL: a citation to a file that does not exist is NOT accepted =="
setup
brief_now
hand_now
say "answer

## Remaining
| #12 | Wave C autopilot | blocked, docs/nope.md:3 |"
task 12 pending "Wave C autopilot"
check "an invented path is caught" block "which does not exist"

echo "== 60. a live background task exempts the citation requirement =="
setup
brief_now
hand_now
say "answer

## Remaining
| #12 | Wave C autopilot | blocked on the agent |"
task 12 pending "Wave C autopilot"
BG='[{"status":"running","description":"agent"}]'
check "real machinery needs no prose citation" allow ""

echo "== 61. 'blocked on you' keeps its own check, not this one =="
setup
brief_now
hand_now
say "answer

## Remaining
| #12 | Wave C autopilot | blocked, You (User Thinks So) |"
task 12 pending "Wave C autopilot"
check "an operator blocker is not asked for a file citation" allow ""

echo "== 62. the judge is HANDED the cited text, not just told a path =="
# citation_state only proves a source EXISTS, which any real file satisfies.
# This is the half that lets the judge check whether the source says what the
# session claimed. Tested directly now that the module is importable.
setup
mkdir -p "$BASE/proj/docs"
printf 'alpha\nbravo\nLands with every stage flag off\ndelta\necho\n' >"$BASE/proj/docs/g.md"
OUT=$(cd "$BASE/proj" && python3 -c '
import importlib.util, sys
spec = importlib.util.spec_from_file_location("wl", sys.argv[1])
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
print(m.cited_excerpts(".", "blocked on Wave B landing, docs/g.md:3"))
' "$HOOK" 2>&1)
if grep -qF "Lands with every stage flag off" <<<"$OUT" && grep -qF ">3|" <<<"$OUT"; then
    echo "  PASS: the cited line is quoted and marked"
    PASS=$((PASS + 1))
else
    echo "  FAIL: excerpt missing or unmarked: ${OUT:0:200}"
    FAIL=$((FAIL + 1))
fi

echo "== 63. CONTROL: importing the hook must NOT run the Stop path =="
# The bare main() call meant any import executed the whole hook. If that
# regresses, case 62 silently tests a hook run instead of a function.
if grep -qF "no such option" <<<"$OUT" || grep -qF '"decision"' <<<"$OUT"; then
    echo "  FAIL: import executed main(); the module is not importable"
    FAIL=$((FAIL + 1))
else
    echo "  PASS: import is side-effect free"
    PASS=$((PASS + 1))
fi

echo "== 64. CONTROL: a citation past EOF yields no excerpt, never a crash =="
OUT2=$(cd "$BASE/proj" && python3 -c '
import importlib.util, sys
spec = importlib.util.spec_from_file_location("wl", sys.argv[1])
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
print("EXCERPT[" + m.cited_excerpts(".", "blocked, docs/g.md:900 and docs/nope.md:2") + "]")
' "$HOOK" 2>&1)
if grep -qF "EXCERPT[]" <<<"$OUT2"; then
    echo "  PASS: out-of-range and missing files quote nothing"
    PASS=$((PASS + 1))
else
    echo "  FAIL: expected an empty excerpt, got: ${OUT2:0:200}"
    FAIL=$((FAIL + 1))
fi

echo "== 65. v6: a request addressed to ME blocks my stop =="
setup
say "done for now"
brief_now
RID=$(askid_as cafe1234 deadbeef "regenerate the caption media and republish")
check "a direct request to this session blocks" block "waiting on you"

echo "== 65b. the block carries the WHOLE payload, both directions =="
# The motivating failure: a finding parked in a commit message, correct and
# unread, relayed by hand. Delivery must not depend on the recipient choosing
# to read anything (--requests included), so the body and the answer ride
# inside the block untruncated. The crucial detail sits past the 300-char
# mark that an earlier draft truncated at.
setup
say "done for now"
brief_now
LONGASK="$(python3 -c "print('caption combos: ' + 'x' * 320 + ' CRUCIAL-ASK: republish then rerun check:ci-tutorial-caption-sync')")"
RID=$(askid_as cafe1234 deadbeef "$LONGASK")
check "the tail of a long request body survives into the block" block "CRUCIAL-ASK: republish then rerun"
LONGANS="$(python3 -c "print('context: ' + 'y' * 320 + ' CRUCIAL-ANSWER: the media session already republished at 14:02Z')")"
reqcli --answer deadbeef "$RID" "$LONGANS" >/dev/null
out="$(printf '{"session_id":"cafe1234-9999-8888-7777-666666666666","cwd":"%s","transcript_path":"%s","last_assistant_message":"done"}' "$BASE/proj" "$BASE/t.jsonl" |
    TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" WORKLIST_TASKS_DIR="$BASE/tasks" \
        WORKLIST_JUDGE=off GITHUB_ACTIONS="${GHA:-}" python3 "$HOOK" 2>/dev/null)"
if grep -qF '"decision": "block"' <<<"$out" && grep -qF "CRUCIAL-ANSWER: the media session already republished" <<<"$out"; then
    echo "  PASS: the tail of a long answer survives into the asker's block"
    PASS=$((PASS + 1))
else
    echo "  FAIL: the answer was truncated or did not block: ${out:0:220}"
    FAIL=$((FAIL + 1))
fi

echo "== 66. CONTROL: a request between two OTHER sessions never blocks me =="
setup
say "done for now"
brief_now
brief_other cafe1234
askid_as aaaa1111 cafe1234 "please do Y" >/dev/null
check "someone else's request does not block a bystander" allow ""

echo "== 67. CONTROL: my own OPEN request never blocks me, and is reported =="
setup
# The fixture produces TWO class-2 sections (this other session's brief and
# the open request), and the output queue releases one per stop by default.
# This case is about the request being reported at all, not about rationing,
# so it drains wide; cases 173 to 177 own the rationing behaviour.
export WORKLIST_REPORT_PER_STOP=9
say "done for now"
brief_now
brief_other cafe1234
askid deadbeef cafe1234 "please regenerate captions" >/dev/null
check "the asker is never blocked on their own open request" allow "still OPEN"
unset WORKLIST_REPORT_PER_STOP

echo "== 68. answering releases the recipient =="
setup
say "done for now"
brief_now
RID=$(askid_as cafe1234 deadbeef "do X")
check "unanswered, it blocks" block "waiting on you"
reqcli --answer deadbeef "$RID" "done: X is finished, gate green" >/dev/null
check "answered, it releases the recipient" allow ""

echo "== 69. a decline MUST carry a reason; an unanswered ack is refused =="
setup
say "done for now"
brief_now
RID=$(askid_as cafe1234 deadbeef "do X")
if reqcli --decline deadbeef "$RID" >/dev/null 2>&1; then
    echo "  FAIL: a reasonless decline was accepted"
    FAIL=$((FAIL + 1))
else
    echo "  PASS: a reasonless decline is refused (exit nonzero)"
    PASS=$((PASS + 1))
fi
if grep -q '"ev":"decline"' "${WL%.md}.requests"; then
    echo "  FAIL: the refused decline still left an event behind"
    FAIL=$((FAIL + 1))
else
    echo "  PASS: the refusal wrote nothing"
    PASS=$((PASS + 1))
fi
if as_peer cafe1234 reqcli --ack cafe1234 "$RID" >/dev/null 2>&1; then
    echo "  FAIL: acking an unanswered request was accepted"
    FAIL=$((FAIL + 1))
else
    echo "  PASS: acking an unanswered request is refused"
    PASS=$((PASS + 1))
fi

echo "== 70. the ANSWER is delivered to the asker as a block, until ack =="
setup
say "done for now"
brief_now
brief_other cafe1234
RID=$(askid deadbeef cafe1234 "which session owns caption regen")
as_peer cafe1234 reqcli --answer cafe1234 "$RID" "the media session owns it; rerun your gate after publish" >/dev/null
check "an unacked answer blocks the asker WITH the answer text" block "the media session owns it"
reqcli --ack deadbeef "$RID" >/dev/null
check "after --ack the answer never re-blocks" allow ""

echo "== 71. a DIRECT decline resolves it and carries its reason back =="
setup
say "done for now"
brief_now
brief_other cafe1234
RID=$(askid deadbeef cafe1234 "please also do Z")
as_peer cafe1234 reqcli --decline cafe1234 "$RID" "out of scope: Z belongs to the GPU session" >/dev/null
check "the decline reason reaches the asker as a block" block "out of scope: Z belongs to the GPU session"
reqcli --ack deadbeef "$RID" >/dev/null
check "an acked decline is silent" allow ""

echo "== 72. a BROADCAST blocks each live session only until IT responds =="
setup
say "done for now"
brief_now
RID=$(askid_as cafe1234 '*' "who owns tutorial caption regeneration")
check "an unanswered broadcast blocks a session that has not responded" block "broadcast"
reqcli --decline deadbeef "$RID" "not my area: I only touch the stop hook" >/dev/null
check "declining a broadcast releases the decliner" allow ""

echo "== 73. a request to a DEAD recipient escalates to an operator [?] once =="
setup
say "done for now"
brief_now
printf '{"ev":"ask","id":"feedc0de","from":"cafe1234","to":"beef9999","at":"%s","body":"republish the caption media"}\n' \
    "$(date -u -d '-120 minutes' +%Y-%m-%dT%H:%M:%SZ)" >>"${WL%.md}.requests"
check "a dead-recipient request blocks nobody and escalates" allow "ESCALATED"
# v10: the [?] is a store event, not a markdown append; --list renders the
# same line shape the markdown used to carry, so the assertions keep their
# regexes and read the store instead of the file.
LIST="$(reqcli --list)"
if grep -q '\- \[?\] (cafe1234) request #feedc0de' <<<"$LIST" && grep -q 'proceeds without an answer' <<<"$LIST"; then
    echo "  PASS: the [?] item exists, owned by the asker, with a generic DEFAULT"
    PASS=$((PASS + 1))
else
    echo "  FAIL: no operator [?] item was recorded: $LIST"
    FAIL=$((FAIL + 1))
fi
run >/dev/null
if [[ "$(reqcli --list | grep -c 'request #feedc0de')" == "1" ]]; then
    echo "  PASS: a second stop does not escalate it again"
    PASS=$((PASS + 1))
else
    echo "  FAIL: escalation is not idempotent: $(reqcli --list | grep -c 'request #feedc0de') lines"
    FAIL=$((FAIL + 1))
fi

echo "== 74. a broadcast with NO other live session escalates, not black-holes =="
setup
# The [?] lands on the ASKER (deadbeef), so it is a deferred item of ours the
# moment it is appended, and the usual something-remains machinery (handover,
# ## Remaining) applies to this stop. That is intended: the asker must report
# that the question went to the operator.
say "done for now

## Remaining
- the fedora ownership question, escalated to the operator as a [?]"
brief_now
hand_now
askid deadbeef '*' "anyone own the flaky fedora leg? DEFAULT: I quarantine it myself" >/dev/null
check "a broadcast nobody can answer escalates immediately" allow "ESCALATED"
if reqcli --list | grep -q 'DEFAULT: I quarantine it myself'; then
    echo "  PASS: the ask's own DEFAULT: is carried into the [?] item"
    PASS=$((PASS + 1))
else
    echo "  FAIL: the ask's DEFAULT was not reused: $(reqcli --list)"
    FAIL=$((FAIL + 1))
fi

echo "== 75. CONTROL: the request block no-ops under GITHUB_ACTIONS =="
setup
say "done for now"
brief_now
askid_as cafe1234 deadbeef "do X" >/dev/null
check "off a runner the request still blocks" block "waiting on you"
GHA=true check "GITHUB_ACTIONS=true never blocks a runner on a request" allow ""

echo "== 76. RACE: concurrent writers lose nothing =="
setup
for i in $(seq 1 16); do
    as_peer "sess000$i" reqcli --ask "sess000$i" cafe1234 "concurrent probe $i" >/dev/null 2>&1 &
done
wait
RQ="${WL%.md}.requests"
OUT=$(python3 -c '
import json, sys
ids, bad, n = set(), 0, 0
for line in open(sys.argv[1]):
    line = line.strip()
    if not line:
        continue
    try:
        ev = json.loads(line)
    except ValueError:
        bad += 1
        continue
    if ev.get("ev") == "ask":
        n += 1
        ids.add(ev.get("id"))
print("asks=%d ids=%d bad=%d" % (n, len(ids), bad))
' "$RQ")
if [[ "$OUT" == "asks=16 ids=16 bad=0" ]]; then
    echo "  PASS: 16 concurrent asks -> 16 parseable events, 16 distinct ids"
    PASS=$((PASS + 1))
else
    echo "  FAIL: concurrent asks were lost or torn: $OUT"
    FAIL=$((FAIL + 1))
fi
RID=$(python3 -c '
import json, sys
print(sorted(json.loads(l)["id"] for l in open(sys.argv[1]) if l.strip())[0])
' "$RQ")
for i in $(seq 1 8); do
    as_peer "answ000$i" reqcli --answer "answ000$i" "$RID" "answer $i" >/dev/null 2>&1 &
done
wait
NANS=$(grep -c "\"ev\":\"answer\",\"id\":\"$RID\"" "$RQ")
if [[ "$NANS" == "8" ]]; then
    echo "  PASS: 8 concurrent answers to one request all survive"
    PASS=$((PASS + 1))
else
    echo "  FAIL: expected 8 answer events, found $NANS"
    FAIL=$((FAIL + 1))
fi

echo "== 77. an over-length body is REFUSED, never silently truncated =="
# Silent write-time truncation would be the commit-message defect one layer
# down: the tail (often the crucial part) vanishes while the sender is told
# the payload was delivered.
setup
say "done for now"
brief_now
if as_peer cafe1234 reqcli --ask cafe1234 deadbeef "$(python3 -c "print('x' * 1000)")" >/dev/null 2>&1; then
    echo "  PASS: a body exactly at the 1000-char limit is accepted"
    PASS=$((PASS + 1))
else
    echo "  FAIL: an at-limit body was refused"
    FAIL=$((FAIL + 1))
fi
if as_peer cafe1234 reqcli --ask cafe1234 deadbeef "$(python3 -c "print('x' * 1100)")" >/dev/null 2>"$BASE/asklen.err"; then
    echo "  FAIL: an over-length ask was accepted"
    FAIL=$((FAIL + 1))
elif grep -qF "REFUSED rather than silently truncated" "$BASE/asklen.err" &&
    [[ "$(grep -c '"ev":"ask"' "${WL%.md}.requests")" == "1" ]]; then
    echo "  PASS: an over-length ask is refused loudly and writes nothing"
    PASS=$((PASS + 1))
else
    echo "  FAIL: over-length refusal was silent or leaked an event: $(cat "$BASE/asklen.err")"
    FAIL=$((FAIL + 1))
fi
RID=$(reqcli --requests | sed -n 's/^#\([0-9a-f]\{8\}\).*/\1/p' | head -n1)
if reqcli --answer deadbeef "$RID" "$(python3 -c "print('y' * 1100)")" >/dev/null 2>"$BASE/anslen.err"; then
    echo "  FAIL: an over-length answer was accepted"
    FAIL=$((FAIL + 1))
elif grep -qF "REFUSED rather than silently truncated" "$BASE/anslen.err" &&
    ! grep -q '"ev":"answer"' "${WL%.md}.requests"; then
    echo "  PASS: an over-length answer is refused loudly and writes nothing"
    PASS=$((PASS + 1))
else
    echo "  FAIL: over-length answer refusal was silent or leaked an event"
    FAIL=$((FAIL + 1))
fi

echo "== 78. --compact never touches the requests sidecar; blocking survives it =="
setup
say "done for now"
brief_now
askid_as cafe1234 deadbeef "must survive compaction" >/dev/null
printf -- '- [ ] (deadbeef) live item that must survive compaction, exit 0\n' >>"$WL"
printf -- '- [~] (cafe1234) archived tombstone line\n' >>"$WL"
# Force the EVENTS FILE to exist before compacting: the event-log compaction
# once deadlocked against its own flock (load(sync=True) inside the held
# lock), and this fixture's original shape dodged that path entirely because
# no events file had been created yet. `timeout` turns a regression into a
# failure instead of a hung suite.
reqcli --list >/dev/null
BEFORE=$(md5sum "${WL%.md}.requests" | cut -d' ' -f1)
TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" \
    timeout 20 python3 "$HOOK" --compact >/dev/null 2>&1 </dev/null || true
if grep -q 'archived tombstone' "$WL"; then
    echo "  FAIL: --compact did not run (tombstone still present), test is vacuous"
    FAIL=$((FAIL + 1))
else
    echo "  PASS: --compact really ran (tombstone dropped)"
    PASS=$((PASS + 1))
fi
if reqcli --list | grep -qF "live item that must survive compaction"; then
    echo "  PASS: the compacted event log still folds the live item"
    PASS=$((PASS + 1))
else
    echo "  FAIL: event-log compaction lost a live item: $(reqcli --list)"
    FAIL=$((FAIL + 1))
fi
AFTER=$(md5sum "${WL%.md}.requests" | cut -d' ' -f1)
if [[ "$BEFORE" == "$AFTER" ]]; then
    echo "  PASS: the requests sidecar is byte-identical after --compact"
    PASS=$((PASS + 1))
else
    echo "  FAIL: --compact modified the requests sidecar"
    FAIL=$((FAIL + 1))
fi
# FOCUS=off: this fixture has several outstanding checks and the assertion
# is about the request one specifically, not about which check rotation picks.
export WORKLIST_FOCUS=off
check "an open request still blocks after --compact" block "waiting on you"
unset WORKLIST_FOCUS

echo "== 79. requests survive the worklist file being deleted entirely =="
# Deleting the worklist is the hook's documented allow-a-stop residual, but it
# must not delete cross-session obligations: the sidecar is a separate file
# and the request checks run unconditionally, not under worklist.exists().
setup
say "done for now"
brief_now
RID=$(askid_as cafe1234 deadbeef "still here after the worklist dies")
rm -f "$WL"
check "deleting the worklist does not delete the obligation" block "waiting on you"
reqcli --answer deadbeef "$RID" "done regardless of the worklist" >/dev/null
check "and the lifecycle still completes without a worklist file" allow ""

echo "== 80. RACE: concurrent escalators write the [?] exactly once =="
# The double-write question: two sessions escalating the same request in the
# same second. By construction both appends happen INSIDE the non-blocking
# flock and every escalator re-reads AFTER acquiring it, so a racer either
# fails the acquire (skips) or sees the winner's escalate event. This drives
# 8 hook processes at one dead-recipient request to prove it empirically.
setup
say "done for now"
brief_now
printf '{"ev":"ask","id":"feedc0de","from":"cafe1234","to":"beef9999","at":"%s","body":"race the escalators"}\n' \
    "$(date -u -d '-120 minutes' +%Y-%m-%dT%H:%M:%SZ)" >>"${WL%.md}.requests"
for i in $(seq 1 8); do
    (run >/dev/null 2>&1) &
done
wait
NESC=$(reqcli --list | grep -c 'request #feedc0de')
NEVT=$(grep -c '"ev":"escalate","id":"feedc0de"' "${WL%.md}.requests")
if [[ "$NESC" == "1" && "$NEVT" == "1" ]]; then
    echo "  PASS: 8 concurrent stops produced exactly one [?] item and one escalate event"
    PASS=$((PASS + 1))
else
    echo "  FAIL: expected 1 [?] item and 1 escalate event, got $NESC and $NEVT"
    FAIL=$((FAIL + 1))
fi

echo "== 81. v7: marker init asks nothing; a DOC-ONLY fix never asks =="
setup
say "done for now"
brief_now
reg_repo
check "the first stop initialises the reggate marker silently" allow ""
if [[ -f "$MARKER" ]] && grep -q '"head": "' "$MARKER"; then
    echo "  PASS: the marker exists with a recorded HEAD"
    PASS=$((PASS + 1))
else
    echo "  FAIL: no marker was written: $(ls "${WL%.md}".* 2>/dev/null)"
    FAIL=$((FAIL + 1))
fi
fixcommit docs/note.md "fix: typo in the docs"
check "THE NAG CONTROL: a doc-only fix commit never asks" allow ""
if [[ "$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["head"])' "$MARKER")" == "$(git -C "$BASE/proj" rev-parse HEAD)" ]]; then
    echo "  PASS: the marker advanced past the doc-only fix (it will never ask)"
    PASS=$((PASS + 1))
else
    echo "  FAIL: the marker did not advance past a skipped fix"
    FAIL=$((FAIL + 1))
fi

echo "== 82. a fix COVERED by a real existing gate settles, once =="
setup
say "done for now"
brief_now
reg_repo
printf '{"name":"p","version":"0.0.0","scripts":{"ci":"npm run check:ci-real","check:ci-real":"true"}}\n' >"$BASE/proj/package.json"
run >/dev/null # marker init
fixcommit src.ts "fix(cli): guard the empty ref"
shim_judge '{"applicable":true,"blind_spot":"no check compared refs","existing_gate":"check:ci-real","recurring":true,"gate_needed":false,"gate_proven":false,"instruction":"none"}'
checkj "a REAL existing gate settles the fix-set as covered" allow "settled as covered"
if grep -q '"verdict": "covered"' "$MARKER"; then
    echo "  PASS: the verdict is recorded in the marker"
    PASS=$((PASS + 1))
else
    echo "  FAIL: no covered verdict in the marker: $(cat "$MARKER")"
    FAIL=$((FAIL + 1))
fi
checkj "a settled fix-set is NEVER re-asked" allow ""

echo "== 83. HALLUCINATED coverage cannot settle: block with three exits =="
setup
say "done for now"
brief_now
reg_repo
printf '{"name":"p","version":"0.0.0","scripts":{"ci":"npm run check:ci-real","check:ci-real":"true"}}\n' >"$BASE/proj/package.json"
run >/dev/null
fixcommit src.ts "fix: a real defect"
shim_judge '{"applicable":true,"blind_spot":"uncovered path","existing_gate":"check:ci-i-dreamed-this","recurring":true,"gate_needed":false,"gate_proven":false,"instruction":"write a gate"}'
OUT="$(runj)"
if grep -qF '"decision": "block"' <<<"$OUT" && grep -qF "HALLUCINATED" <<<"$OUT" &&
    grep -qF "WRITE THE GATE control-first" <<<"$OUT" && grep -qF "REBUT" <<<"$OUT"; then
    echo "  PASS: a nonexistent gate name is called hallucinated and the block names the exits"
    PASS=$((PASS + 1))
else
    echo "  FAIL: hallucinated coverage was not caught: ${OUT:0:220}"
    FAIL=$((FAIL + 1))
fi

echo "== 84. the DEFERRAL exit settles it as an operator decision =="
TOK="$(grep -o 'reggate:[0-9a-f]\{8\}' <<<"$OUT" | head -n1)"
if [[ -n "$TOK" ]]; then
    echo "  PASS: the block hands the session its exact deferral token ($TOK)"
    PASS=$((PASS + 1))
else
    echo "  FAIL: no reggate token in the block"
    FAIL=$((FAIL + 1))
fi
printf -- '- [?] (deadbeef) %s should this be gated? DEFAULT: no gate, operator decides\n' "$TOK" >>"$WL"
# The [?] is now OUR deferred item, so the something-remains machinery
# (handover + ## Remaining) applies to this stop -- intended, as in case 74.
hand_now
say "deferred the gate question to the operator

## Remaining
- the reggate deferral, waiting on the operator"
checkj "the [?] deferral settles the fix-set" allow "settled as deferred"

echo "== 85. recurring=false settles as one-off =="
setup
say "done for now"
brief_now
reg_repo
printf '{"name":"p","version":"0.0.0","scripts":{"ci":"true"}}\n' >"$BASE/proj/package.json"
run >/dev/null
fixcommit src.ts "fix: pasted one wrong constant"
shim_judge '{"applicable":true,"blind_spot":"typo with no invariant behind it","existing_gate":"","recurring":false,"gate_needed":false,"gate_proven":false,"instruction":"none"}'
checkj "a one-off mistake warrants no gate and settles" allow "settled as one-off"

echo "== 86. PROOF: a new gate, wired TRANSITIVELY and green, settles as proven =="
setup
say "done for now"
brief_now
reg_repo
printf '{"name":"p","version":"0.0.0","scripts":{"ci":"npm run check:ci-batch","check:ci-batch":"npm run check:ci-newgate","check:ci-newgate":"bash .ci/scripts/quality/check-newgate.sh"}}\n' >"$BASE/proj/package.json"
run >/dev/null # init seeds gate hashes (no scripts yet)
fixcommit src.ts "fix: the recurring defect"
mkdir -p "$BASE/proj/.ci/scripts/quality"
printf '#!/bin/bash\nexit 0\n' >"$BASE/proj/.ci/scripts/quality/check-newgate.sh"
shim_judge '{"applicable":true,"blind_spot":"nothing asserted the invariant","existing_gate":"","recurring":true,"gate_needed":true,"gate_proven":true,"instruction":"gate written"}'
checkj "a wired (ci -> batch -> gate), green gate is the proof" allow "settled as proven"
if grep -q '"exit": 0' "$MARKER" && grep -q 'check-newgate.sh' "$MARKER"; then
    echo "  PASS: the bounded run is cached in the marker by content hash"
    PASS=$((PASS + 1))
else
    echo "  FAIL: no cached gate run in the marker: $(cat "$MARKER")"
    FAIL=$((FAIL + 1))
fi

echo "== 87. CONTROL: a gate DEFINED but not reachable from ci does not prove =="
# Also the anti-substring control: ci MENTIONS the key inside an echo, so a
# substring reachability test would wrongly pass this. Only `npm run` edges count.
setup
say "done for now"
brief_now
reg_repo
printf '{"name":"p","version":"0.0.0","scripts":{"ci":"echo check:ci-newgate","check:ci-newgate":"bash .ci/scripts/quality/check-newgate.sh"}}\n' >"$BASE/proj/package.json"
run >/dev/null
fixcommit src.ts "fix: the recurring defect"
mkdir -p "$BASE/proj/.ci/scripts/quality"
printf '#!/bin/bash\nexit 0\n' >"$BASE/proj/.ci/scripts/quality/check-newgate.sh"
shim_judge '{"applicable":true,"blind_spot":"nothing asserted the invariant","existing_gate":"","recurring":true,"gate_needed":true,"gate_proven":true,"instruction":"gate written"}'
checkj "defined-but-never-run does not count as proof" block "NOT reachable"

echo "== 88. a CORRUPT marker is forgotten loudly, never a block =="
setup
say "done for now"
brief_now
reg_repo
run >/dev/null
echo 'not json {{{' >"$MARKER"
check "corruption re-initialises and reports, allowing the stop" allow "forgotten"
if python3 -c 'import json,sys;json.load(open(sys.argv[1]))' "$MARKER" 2>/dev/null; then
    echo "  PASS: the marker is valid JSON again after the reset"
    PASS=$((PASS + 1))
else
    echo "  FAIL: the marker was left corrupt"
    FAIL=$((FAIL + 1))
fi

echo "== 89. a judge that OMITS regression_gate on a fix stop fails closed =="
setup
say "done for now"
brief_now
reg_repo
printf '{"name":"p","version":"0.0.0","scripts":{"ci":"true"}}\n' >"$BASE/proj/package.json"
run >/dev/null
fixcommit src.ts "fix: something real"
shim_judge ''
checkj "a missing regression_gate on a fix-signal stop blocks" block "no usable regression_gate"

echo "== 90. TICKS are the uncommitted-tree signal; pre-existing ones are not =="
setup
say "done for now"
brief_now
reg_repo
echo '- [x] (deadbeef) an old already-done item' >>"$WL"
shim_judge '{"applicable":true,"blind_spot":"x","existing_gate":"","recurring":false,"gate_needed":false,"gate_proven":false,"instruction":"none"}'
checkj "init with a pre-existing tick asks nothing" allow ""
if grep -q '"fixsets": {}' "$MARKER"; then
    echo "  PASS: the pre-existing tick was seeded, not asked about"
    PASS=$((PASS + 1))
else
    echo "  FAIL: init asked about an old tick: $(cat "$MARKER")"
    FAIL=$((FAIL + 1))
fi
# Evidence in the line (a real sha), else I7 blocks before the reggate settle.
echo "- [x] (deadbeef) fixed the parser crash on empty input, $(git -C "$BASE/proj" rev-parse --short HEAD)" >>"$WL"
checkj "a NEWLY ticked [x] is a fix signal even with no commit" allow "settled as one-off"

echo "== 91. I6: a stop with NOTHING inbound blocks on the first stop =="
setup
brief_now
hand_now
say "answer

## Remaining
| #7 | thing | pending, me |"
task 7 pending "thing"
CRONS='[]'
check "pending task + no cron + no bg + no lease blocks immediately" block "NOTHING WILL WAKE THIS SESSION"

echo "== 92. I6 CONTROLS: each wake-up source suppresses it =="
# Fresh fixture per control: chaining them on one fixture walks the stuck
# counter to its threshold and a later control fails for the wrong reason.
i6_fixture() {
    setup
    brief_now
    hand_now
    say "answer

## Remaining
| #7 | thing | pending, me |"
    task 7 pending "thing"
    CRONS='[]'
}
i6_fixture
CRONS='[{"id":"w","schedule":"17 * * * *"},{"id":"p","schedule":"*/5 * * * *"}]'
check "a live work cron is a wake-up" allow ""
i6_fixture
CRONS='[{"id":"p","schedule":"*/5 * * * *"}]'
check "v9: a poll cron ALONE is not a wake-up (it only reacts to others)" block "NOTHING WILL WAKE THIS SESSION"
i6_fixture
BG='[{"status":"running","description":"agent"}]'
check "a running background task is a wake-up" allow ""
i6_fixture
echo "- [>] (deadbeef) until:$(date -u -d '+30 minutes' +%Y-%m-%dT%H:%MZ) delegated to agent" >>"$WL"
check "a fresh [>] lease is a wake-up" allow ""

echo "== 93. I6: a CONFIRMED operator-blocked task is a legitimate idle =="
setup
brief_now
hand_now
say "answer

## Remaining
| #7 | thing | blocked, You (User Thinks So) |"
task 7 pending "thing"
CRONS='[]'
check "confirmed 'You (User Thinks So)' waits without a wake-up" allow ""

echo "== 94. I7: a tick without evidence blocks; a REAL pointer clears it =="
setup
say "done for now"
brief_now
reg_repo
run >/dev/null # marker init
echo '- [x] (deadbeef) fixed the flaky teardown' >>"$WL"
check "an evidence-free tick blocks" block "COMPLETION WITHOUT EVIDENCE"
# A fabricated hex pointer must NOT count: it names no real object.
python3 - "$WL" <<'PYEOF'
import sys
p = sys.argv[1]
s = open(p).read().replace(
    "fixed the flaky teardown",
    "fixed the flaky teardown, see 0123abc4567",
)
open(p, "w").write(s)
PYEOF
check "a fabricated sha is not evidence" block "COMPLETION WITHOUT EVIDENCE"
python3 - "$WL" "$(git -C "$BASE/proj" rev-parse --short HEAD)" <<'PYEOF'
import sys
p, sha = sys.argv[1], sys.argv[2]
s = open(p).read().replace("see 0123abc4567", "proof " + sha)
open(p, "w").write(s)
PYEOF
check "a REAL git object in the line is evidence" allow ""

echo "== 95. I7: a task flipping to completed needs evidence near its #id =="
setup
brief_now
hand_now
reg_repo
task 7 pending "prove the budget flag binds"
say "working on it

## Remaining
| #7 | prove the budget flag binds | pending, me |"
run >/dev/null # marker init snapshots task 7 as pending
task 7 completed "prove the budget flag binds"
newturn
say "All done."
check "S-2 REPLAY: completed with no evidence anywhere blocks" block "COMPLETION WITHOUT EVIDENCE"
newturn
say "Done: #7 verified, exit 0 from the budget run."
check "evidence on the #id line clears it" allow ""

echo "== 96. I7 CONTROL: completions that predate the marker never nag =="
setup
brief_now
reg_repo
task 9 completed "long-finished thing"
say "nothing new"
check "an init-stop snapshot asks nothing about old completions" allow ""
check "and the next stop sees no transition" allow ""

echo "== 97. a DOT-LEADING path is a valid citation (.ci, .github, .claude) =="
# `\b[\w]` cannot start on a dot, so `.ci/x.sh:9` matched but CAPTURED `ci/x.sh`,
# which resolves to nothing. That made most of this repo uncitable while the
# check looked strict. Caught by I7 firing on a real tick of mine.
setup
brief_now
hand_now
mkdir -p "$BASE/proj/.ci/scripts"
printf 'a\nb\nc\nd\ne\nf\ng\nh\ni\nj\n' >"$BASE/proj/.ci/scripts/thing.sh"
say "answer

## Remaining
| #7 | thing | blocked, .ci/scripts/thing.sh:3 |"
task 7 pending "thing"
check "a .ci path resolves as a citation" allow ""

echo "== 98. CONTROL: a dot-leading path that does NOT exist is still rejected =="
setup
brief_now
hand_now
say "answer

## Remaining
| #7 | thing | blocked, .ci/scripts/nope.sh:3 |"
task 7 pending "thing"
check "an invented .ci path is caught" block "which does not exist"

echo "== 99. A CRASHING HOOK BLOCKS, it does not wave the stop through =="
# The hook's global escape hatch, and nobody put it there on purpose: an
# unhandled exception writes a traceback to stderr and NOTHING to stdout, the
# harness sees no decision, and the stop is ALLOWED. One bug anywhere silently
# disabled every check. A v8 cut really did crash on a tuple unpack and sail
# through; only a needle assertion caught it.
setup
CRASHED="$BASE/crashy.py"
sed "s/^def main():/def main():\n    raise RuntimeError('planted crash')/" "$HOOK" >"$CRASHED"
OUT=$(printf '{"session_id":"%s","cwd":"%s","transcript_path":"%s"}' "$SID" "$BASE/proj" "$BASE/t.jsonl" |
    TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" WORKLIST_TASKS_DIR="$BASE/tasks" \
        GITHUB_ACTIONS="" python3 "$CRASHED" 2>/dev/null)
GOT=$(python3 -c 'import json,sys
raw=sys.stdin.read().strip()
print(json.loads(raw).get("decision","allow") if raw else "allow")' <<<"$OUT" 2>/dev/null)
if [[ "$GOT" == "block" ]] && grep -qF 'planted crash' <<<"$OUT"; then
    echo "  PASS: a crash blocks and carries its traceback"
    PASS=$((PASS + 1))
else
    echo "  FAIL: a crash produced decision=$GOT (a crash must never allow)"
    echo "        out: ${OUT:0:200}"
    FAIL=$((FAIL + 1))
fi

echo "== 100. CONTROL: the UNMODIFIED hook still allows a clean stop =="
# Without this, case 99 would pass on a hook that blocks unconditionally.
setup
brief_now
hand_now
say "all done"
CRONS='[{"id":"c","schedule":"17 * * * *"},{"id":"p","schedule":"*/5 * * * *"}]' check "a clean stop is still allowed" allow ""

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
    "CI_NOTE_RETRYABLE": ("9", 1, "pats", "rows"),
    "CI_NOTE_DOWNGRADED": ("9", 1, 2, "", "rows"),
    "V_NO_POLL_CRON": ("m", "m"), "V_NO_WAITER": (2, "p", "m"),
    "N_WAITER_NUDGE": (2, "p", "m", 60), "V_MANY_WORK_CRONS": (2, "l"),
    "V_MANY_POLL_CRONS": (2,),
    "V_AGENT_STATE": ("b", "s", "", 250, 4000, "m"),
    "V_AGENT_BOOTSTRAP": ("b", "b", "b"), "V_AGENT_STILL_ABSENT": ("b",),
    "N_AGENT_BLIND": ("r",), "CLI_STATE_REFUSED": ("v", "d", 250, 4000),
    "N_AGENT_PEERS": ("br", "rows"), "CLI_STATE_WHOLE_DOC": ("m",),
    "N_UNREAD_REPORTS": (2, "b", "rows", "p", "p", "m"),
    "CLI_REAP_USAGE": (), "CLI_REAP_UNKNOWN": ("t", "l"),
    "N_ROSTER_STALE": (20, 1, 19, "p", "m"),
    "CLI_LOOP_USAGE": (), "CLI_BRIEF_USAGE": (), "CLI_UNKNOWN_VERB": ("v",),
    "CLI_BRIEF_LOOKS_LIKE_ID": ("v",),
    "V_JUDGE_ORDER_REJECTED": ("v", "v"),
    "V_LADDER_INVESTIGATE_GONE": ("rows", "facts", "m", "m"),
    "CLI_STATE_NO_DIR": ("b", "b", "b"), "CLI_STATE_NO_BRANCH": ("r",),
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
    # v20: the /handoff checklist gate (wl_checklist, docs/<slug>/CHECKLIST.md).
    "V_CL_SHAPE": ("d", "rows"), "V_CL_UNREADABLE": ("e",),
    "V_CL_PRODUCING": ("s", 0, 1, "rows", "d"), "V_CL_PRODUCING_DONE": ("s", "d"),
    "V_CL_FLIP": ("d", "executing", "rows", "d"), "V_CL_WAVES": ("s", "d", "rows"),
    "N_CL_FOREIGN": ("s", "o", ""),
    "N_CL_FOREIGN_DRIFT": ("d", "executing", "o", "rows"),
    "N_CL_DOOR_PARKED": ("d", 1, "rows"),
    "N_CADENCE_PAUSE": (1, "keys", 1, 3),
    "V_PLAN_DRIFT": (1, "rows"),
    "V_INTENT_EXPIRED": ("t", 1, 1, "cov"),
    "CLI_INTENT_USAGE": None,
    "CTX_CHECKLISTS": ("listing",),
    "CTX_PLANS": ("b", "l"), "CTX_PLANS_EXCERPT": ("p", "b"),
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
    "N_EMAIL_SKIPPED": (1, "err"),
    "V_BG_REPORT": ("never", "2026-01-01T00:15:00Z", 15, 2, "rows"),
    "V_BG_REPORT_TASKS": ("never", "2026-01-01T00:15:00Z", 15, 2, 1, "tasks", "rows"),
    "N_EMAIL_SENT": (2, "to@x", 120), "N_EMAIL_FAIL": (2, "err", 15),
    "N_EMAIL_UNCONFIGURED": ("p", 2),
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
    "CLI_BODY_REFUSED": ("b", 1200, 1000), "CTX_SESSION_START": ("s", "d", "l", ""),
    "CTX_SESSION_START_STALE": (3, "s"),
    "CTX_POSTCOMPACT_MISSING": ("p", "b", "m"),
    "CTX_POSTCOMPACT_NO_BRANCH": ("t",),
    "CTX_POSTCOMPACT_BRIEFING": ("d", "s", "r", "p", "t"),
    "CTX_POSTCOMPACT_PEERS": ("b",),
    "JUDGE_PROMPT": {"streak": 1, "remaining": "r", "leases": 0, "loop": "l",
                     "citations": "c", "message": "m", "traps": "t"},
    "REGGATE_PROMPT": {"fixset": "f", "keys": "k"},
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

echo "== 119. a submodule pointer moved onto a feature branch is caught =="
# REGRESSION, from a real near-miss. A subagent committed inside a submodule on
# its own branch, which necessarily moves the superproject's gitlink, and the
# standing "sweep everything with git add -A" rule would have COMMITTED that
# move, silently adding the submodule's PR to this PR's merge chain.
# Quality / Submodule Branches only says so minutes later, in CI.
#
# A REAL git fixture with a REAL remote, because the decisive fact is which
# REMOTE branches contain the commit: a local-only branch proves nothing about
# what CI can fetch.
#
# TWO FIXTURE BUGS, both found by CI and neither by this suite (see the CONTROL
# note below). First: `git init --bare` inherits init.defaultBranch, which the
# author's ~/.gitconfig pins to `main` and a CI runner leaves at `master`. The
# bare remote's HEAD then named a branch that was never pushed, the submodule
# clone landed on an unborn branch, and `submodule add` aborted with "You are on
# a branch yet to be born". Every `-b main` below is therefore load-bearing:
# pin the branch, never inherit it. Second: the fixture swallowed stdout AND
# stderr, so that fatal was invisible and CI could only report `got: `. It is
# captured now and printed on failure.
#
# VERIFIED, so this is not a guess: the same fixture was run under git 2.55.0 in
# a container. Without `-b main` it reproduces CI exactly (submodule add exits
# 128, ls-files -s finds no gitlink). With it, `git submodule status --cached`
# prints the leading `+` on 2.55.0 just as it does on the author's 2.43.0, so the
# DETECTOR was never version-sensitive and is left alone.
SUBW="$BASE/subptr"
SUBLOG="$BASE/subptr.log"
mkdir -p "$SUBW"
{
    git init -q --bare "$SUBW/remote.git" -b main
    git init -q "$SUBW/sub" -b main
    (cd "$SUBW/sub" && echo one >f && git add f &&
        git -c user.email=t@t -c user.name=t commit -qm one &&
        git remote add origin "$SUBW/remote.git" && git push -q origin main)
    git init -q "$SUBW/super" -b main
    (cd "$SUBW/super" && git -c protocol.file.allow=always submodule add -q "$SUBW/remote.git" sub &&
        git add -A && git -c user.email=t@t -c user.name=t commit -qm super)
} >"$SUBLOG" 2>&1

probe_moves() {
    python3 -c "
import sys; sys.path.insert(0, '$(dirname "$HOOK")')
import worklist as W
for p, a, b, where in W.submodule_pointer_moves('$SUBW/super'):
    print('%s|%s' % (p, where))"
}

# CONTROL FIRST, and it must NOT be satisfiable by a broken fixture. The old
# version asserted only "probe_moves prints nothing", which a superproject with
# no submodule at all satisfies -- so it passed green in CI on a fixture whose
# `submodule add` had died, while the detection half beside it failed with an
# empty string. A silent control has to prove the instrument exists before it
# proves the instrument is quiet.
GITLINK="$(git -C "$SUBW/super" ls-files -s sub 2>/dev/null)"
OUT=$(probe_moves)
if [[ "$GITLINK" == 160000* && -z "$OUT" ]]; then
    echo "  PASS: control, the gitlink exists and a pointer matching the index is not reported"
    PASS=$((PASS + 1))
elif [[ "$GITLINK" != 160000* ]]; then
    echo "  FAIL: fixture never built a gitlink (ls-files -s sub: '${GITLINK:-empty}')"
    echo "        git log: $(tr '\n' ' ' <"$SUBLOG" | head -c 300)"
    FAIL=$((FAIL + 1))
else
    echo "  FAIL: control fired on a clean pointer: $OUT"
    FAIL=$((FAIL + 1))
fi

(cd "$SUBW/super/sub" && git checkout -q -b feat && echo two >f2 && git add f2 &&
    git -c user.email=t@t -c user.name=t commit -qm two &&
    git push -q origin feat && git fetch -q origin) >>"$SUBLOG" 2>&1

OUT=$(probe_moves)
if [[ "$OUT" == *"sub|"* && "$OUT" == *"origin/feat"* && "$OUT" == *"NOT on origin/main"* ]]; then
    echo "  PASS: the move is reported with the branch that contains it and that it is off main"
    PASS=$((PASS + 1))
else
    echo "  FAIL: expected sub/origin/feat/NOT on origin/main, got: '$OUT'"
    echo "        git log: $(tr '\n' ' ' <"$SUBLOG" | head -c 300)"
    FAIL=$((FAIL + 1))
fi

# ---------------------------------------------------------------------------
# v10: CI trouble on the open PR (cases 120-131).
#
# EVERY ONE OF THESE IS A CONTROL FOR A REAL MISREAD, not a hypothetical. The
# fixtures below encode the exact shapes that fooled a human reading the same
# API by hand for a night: a cancelled run with zero failed jobs, a cancelled
# run hiding one real failure, a flake the watchdog was already retrying, and a
# background watch pointed at a superseded run. The network is never touched;
# `gh` is a shim serving JSON from files.
# ---------------------------------------------------------------------------

ci_setup() { # a repo with an origin/pub ref, one fresh brief, and a gh shim
    setup
    brief_now
    (
        cd "$BASE/proj" || exit
        git init -q -b main 2>/dev/null
        git config user.email t@t
        git config user.name t
        git remote add origin https://github.com/fake/repo.git 2>/dev/null
        echo a >a.txt
        git add -A
        git commit -qm base
        git update-ref refs/remotes/origin/pub "$(git rev-parse HEAD)"
    ) >/dev/null 2>&1
    # The freshness check shares the `gh api graphql` path, so the shim must
    # answer BOTH queries; a body edited in 2999 keeps that check quiet.
    echo '{"data":{"repository":{"pullRequests":{"nodes":[{"number":543,"lastEditedAt":"2999-01-01T00:00:00Z","updatedAt":"2999-01-01T00:00:00Z"}]}}}}' >"$BASE/ci-fresh.json"
    echo '{"run_id":30514648812,"run_attempt":1,"steps":[{"name":"Set up job","conclusion":"success"},{"name":"Shell format","conclusion":"failure"}]}' >"$BASE/ci-job.json"
    cat >"$BASE/binonly/gh" <<SHIM
#!/bin/bash
for a in "\$@"; do
    case "\$a" in
        *lastEditedAt*) cat "$BASE/ci-fresh.json"; exit 0 ;;
        query=*) cat "$BASE/ci-rollup.json"; exit 0 ;;
    esac
done
case "\$*" in
    *actions/jobs/*) cat "$BASE/ci-job.json"; exit 0 ;;
esac
echo '{}'
SHIM
    chmod +x "$BASE/binonly/gh"
}

ci_rollup() { # ci_rollup <rollup-state> <contexts-json-array>
    printf '{"data":{"repository":{"pullRequests":{"nodes":[{"number":543,"url":"u","commits":{"nodes":[{"commit":{"oid":"deadsha0000","statusCheckRollup":{"state":"%s","contexts":{"totalCount":9,"pageInfo":{"hasNextPage":false,"endCursor":null},"nodes":%s}}}}]}}]}}}}\n' \
        "$1" "$2" >"$BASE/ci-rollup.json"
    # The read is cached on the published tip SHA, so a fixture swap inside one
    # case must drop the cache or it reads the previous shape.
    rm -f "${WL%.md}.cistate-deadbeef"
}

ci_job() { # a completed Actions check run: ci_job <name> <conclusion> [id]
    printf '{"__typename":"CheckRun","name":"%s","status":"COMPLETED","conclusion":"%s","databaseId":%s,"detailsUrl":"https://x/job/%s","checkSuite":{"workflowRun":{"databaseId":30514648812}}}' \
        "$1" "$2" "${3:-90784763855}" "${3:-90784763855}"
}

ci_running() { # a check run still in flight
    printf '{"__typename":"CheckRun","name":"%s","status":"IN_PROGRESS","conclusion":null,"databaseId":1,"detailsUrl":"","checkSuite":{"workflowRun":{"databaseId":30514648812}}}' "$1"
}

ci_run() { # a Stop event with the CI check armed
    printf '{"session_id":"%s","cwd":"%s","last_assistant_message":"%s","session_crons":[],"background_tasks":%s}' \
        "$SID" "$BASE/proj" "${CIMSG:-work done}" "${BG:-[]}" |
        PATH="$BASE/binonly:$PATH" TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" \
            WORKLIST_TASKS_DIR="$BASE/tasks" WORKLIST_PUBLISH_REF="${CIREF-pub}" \
            WORKLIST_JUDGE=off GITHUB_ACTIONS="${GHA:-}" python3 "$HOOK" 2>"$BASE/err.txt"
}

cichk() { # cichk <label> <yes|no> <needle>  -- needle present or absent
    local label="$1" want="$2" needle="$3" out
    out="$(ci_run)"
    if grep -qF "$needle" <<<"$out"; then got=yes; else got=no; fi
    if [[ "$got" == "$want" ]]; then
        echo "  PASS: $label"
        PASS=$((PASS + 1))
    else
        echo "  FAIL: $label (wanted needle $want, got $got) needle='$needle'"
        echo "        out: ${out:0:400}"
        [[ -s "$BASE/err.txt" ]] && echo "        err: $(head -c 200 "$BASE/err.txt")"
        FAIL=$((FAIL + 1))
    fi
}

echo "== 120. CONTROL, it FIRES: a real per-job failure blocks with job, step and log command =="
ci_setup
ci_rollup FAILURE "[$(ci_job "Quality / Static" FAILURE), $(ci_job "Quality / Security" SUCCESS)]"
out="$(ci_run)"
ok=1
for needle in "CI IS RED ON PR #543" "Quality / Static" "failing step: Shell format" \
    "gh api repos/fake/repo/actions/jobs/90784763855/logs" "log-failed"; do
    grep -qF "$needle" <<<"$out" || {
        ok=0
        echo "        MISSING: $needle"
    }
done
if [[ "$ok" == 1 ]] && grep -q '"decision": "block"' <<<"$out"; then
    echo "  PASS: a real failure blocks and hands over job, failing step and the working log command"
    PASS=$((PASS + 1))
else
    echo "  FAIL: red CI did not produce an actionable block: ${out:0:400}"
    FAIL=$((FAIL + 1))
fi

echo "== 121. CONTROL, it stays SILENT: an all-green run says nothing =="
ci_setup
ci_rollup SUCCESS "[$(ci_job "Quality / Static" SUCCESS), $(ci_job "E2E / ubuntu" SUCCESS)]"
cichk "a green run produces no CI complaint" no "CI IS RED"

echo "== 122. CONTROL: a CANCELLED run with ZERO failed jobs is not red =="
# Four runs in one night ended `cancelled` with no failed job, each superseded
# by the session's own next push. Reading the run-level rollup would have nagged
# four times about nothing.
ci_setup
ci_rollup FAILURE "[$(ci_job "Quality / Static" CANCELLED), $(ci_job "E2E / ubuntu" CANCELLED), $(ci_job "Init" SKIPPED)]"
cichk "cancelled-with-no-failures is silent even when the rollup says FAILURE" no "CI IS RED"

echo "== 123. ...but a CANCELLED run HIDING one real failure still fires =="
# The other half: the watchdog force-cancels a run when a gate fails, so
# `cancelled` also means "something genuinely failed". Only per-JOB conclusions
# separate run 30514648812 (cancelled, Quality / Static = failure) from 30513152662.
ci_setup
ci_rollup CANCELLED "[$(ci_job "Quality / Static" FAILURE), $(ci_job "E2E / ubuntu" CANCELLED)]"
cichk "one real failure inside a cancelled run is found" yes "Quality / Static"

echo "== 124. CONTROL: a failing E2E leg with a watchdog retry pending does not block =="
# WATCHDOG_RETRY_ALLOWLIST_PATTERNS in .github/workflows/watchdog-monitor.yml.
# That night an opensuse E2E leg died on a Docker Hub CDN reset, was retried onto
# the same run, and the run finished green at 95 jobs.
ci_setup
ci_rollup PENDING "[$(ci_job "E2E / opensuse" FAILURE), $(ci_running "E2E / ubuntu")]"
out="$(ci_run)"
if ! grep -qF "CI IS RED" <<<"$out" && grep -qF "retry allowlist" <<<"$out"; then
    echo "  PASS: a retryable leg on a live run is reported, never blocked on"
    PASS=$((PASS + 1))
else
    echo "  FAIL: watchdog-retryable leg mishandled: ${out:0:400}"
    FAIL=$((FAIL + 1))
fi

echo "== 125. ...and once the run is FINAL the same leg is hard =="
ci_setup
ci_rollup FAILURE "[$(ci_job "E2E / opensuse" FAILURE)]"
cichk "a retryable leg still red on a finished run becomes actionable" yes "CI IS RED"

echo "== 126. a RUNNING background watch naming this run silences the check =="
ci_setup
ci_rollup FAILURE "[$(ci_job "Quality / Static" FAILURE)]"
BG='[{"id":"w1","status":"running","description":"watch CI","command":"gh run watch 30514648812"}]'
cichk "an armed watch on the current run is the wake-up; the hook stays quiet" no "CI IS RED"

echo "== 127. a COMPLETED watch, or one on a SUPERSEDED run, does NOT count as armed =="
# Both happened: a completed watch reported completed/cancelled for a run that
# had since been superseded, and another reported a FALSE failure because a
# watchdog rerun flipped a terminal run back to in_progress.
ci_setup
ci_rollup FAILURE "[$(ci_job "Quality / Static" FAILURE)]"
BG='[{"id":"w1","status":"completed","description":"watch","command":"gh run watch 30514648812"},
     {"id":"w2","status":"running","description":"watch","command":"gh run watch 30513152662"}]'
cichk "a dead watch and a watch on another run leave the check armed" yes "CI IS RED"
BG='[]'

echo "== 128. the block has a HARD CEILING: the same failure set stops blocking =="
# The deadlock guard. A different check trapped this session for an entire night
# by demanding something it could not produce; this one cannot, by construction.
ci_setup
ci_rollup FAILURE "[$(ci_job "Quality / Static" FAILURE)]"
n=0
for i in 1 2 3 4; do
    grep -qF "CI IS RED" <<<"$(ci_run)" && n=$((n + 1))
done
if [[ "$n" -eq 2 ]]; then
    echo "  PASS: blocks exactly twice for one failure set, then downgrades forever"
    PASS=$((PASS + 1))
else
    echo "  FAIL: expected 2 blocking stops for one failure set, got $n"
    FAIL=$((FAIL + 1))
fi
out="$(ci_run)"
if grep -qF "still red" <<<"$out" && ! grep -qF "CI IS RED" <<<"$out"; then
    echo "  PASS: the downgraded state still reports the failure, it does not go silent"
    PASS=$((PASS + 1))
else
    echo "  FAIL: a downgraded CI failure vanished instead of being reported: ${out:0:300}"
    FAIL=$((FAIL + 1))
fi

echo "== 129. naming the failing job in the stop message clears the block =="
ci_setup
ci_rollup FAILURE "[$(ci_job "Quality / Static" FAILURE)]"
CIMSG="Quality / Static is red on the shfmt step; a sub-agent is on it"
cichk "an acknowledgement that names the job is the fast exit, not a bypass" no "CI IS RED"
CIMSG=""

echo "== 130. an unreadable lookup BLOCKS rather than passing quietly =="
ci_setup
cat >"$BASE/binonly/gh" <<'SHIM'
#!/bin/bash
echo "gh: could not resolve to a Repository" >&2
exit 1
SHIM
chmod +x "$BASE/binonly/gh"
rm -f "${WL%.md}.cistate-deadbeef"
cichk "blindness is its own verdict, per no-escape-hatch" yes "PR CI-status lookup failed"

echo "== 131. two live sessions, and an unset publish ref, both mean SILENCE and NO network =="
ci_setup
ci_rollup FAILURE "[$(ci_job "Quality / Static" FAILURE)]"
brief_other "cafe1234"
cichk "a second live session silences the check (the red may be theirs)" no "CI IS RED"
# And the opt-out must cost NOTHING: a gh that dies if invoked proves the check
# never reaches the network when WORKLIST_PUBLISH_REF is unset.
setup
brief_now
cat >"$BASE/binonly/gh" <<'SHIM'
#!/bin/bash
echo "GH-WAS-CALLED" >&2
exit 3
SHIM
chmod +x "$BASE/binonly/gh"
CIREF='' ci_run >/dev/null
if ! grep -qF "GH-WAS-CALLED" "$BASE/err.txt"; then
    echo "  PASS: with no publish ref the check makes no network call at all"
    PASS=$((PASS + 1))
else
    echo "  FAIL: the opt-out path still shelled out to gh"
    FAIL=$((FAIL + 1))
fi
rm -f "$BASE/binonly/gh"

# ---------------------------------------------------------------------------
# v10 (cases 132+): the JSONL event store, worker liveness, the 45/90/120
# ladder, deferral autonomy, the judge cache, and the dead-code gate. Every
# FIRE case is paired with a SILENT control off the same fixture shape
# differing in one planted fact, because a control satisfied by an unbuilt
# fixture is worse than no control (that exact failure shipped once; see the
# case-119 note above).
# ---------------------------------------------------------------------------

echo "== 132. THE STORE: markdown items fold into the event log (migration) =="
setup
FUT=$(date -u -d '+30 minutes' +%Y-%m-%dT%H:%MZ)
cat >>"$WL" <<EOF
- [ ] (deadbeef) open thing
- [x] (deadbeef) done thing, exit 0
- [?] (deadbeef) question DEFAULT: pick A
- [>] (deadbeef) until:$FUT delegated
- [~] (deadbeef) tombstoned relic
EOF
LIST="$(reqcli --list)"
ok=1
for needle in '- [ ] (deadbeef) open thing' '- [x] (deadbeef) done thing, exit 0' \
    '- [?] (deadbeef) question DEFAULT: pick A' 'delegated'; do
    grep -qF -- "$needle" <<<"$LIST" || {
        ok=0
        echo "        MISSING: $needle"
    }
done
if [[ "$ok" == 1 ]] && ! grep -qF 'tombstoned relic' <<<"$LIST"; then
    pass "all four live states fold in; the [~] tombstone reads as deleted"
else
    fail "markdown sync lost or resurrected items: $LIST"
fi
if grep -q '"ev":"md"' "${WL%.md}.events.jsonl"; then
    pass "the sync left an md event in the log (the store is real, not a re-parse)"
else
    fail "no md event was appended: $(cat "${WL%.md}.events.jsonl" 2>/dev/null)"
fi

echo "== 133. in-place markdown edits are honoured; CLI state survives md churn =="
# The markdown is MUTATED by its writers (ticks flip the state byte in
# place), which is why the sync is a whole-file diff, not an append offset.
setup
brief_now
hand_now
say "answer

## Remaining
- the parser item"
echo '- [ ] (deadbeef) fix the parser crash, verified exit 0' >>"$WL"
check "the imported open item blocks" block "OPEN worklist item"
sed -i 's/^- \[ \] (deadbeef) fix the parser/- [x] (deadbeef) fix the parser/' "$WL"
newturn
say "done

## Remaining
nothing"
check "an in-place tick (state byte flip) clears the block" allow ""
ADDOUT="$(reqcli --add deadbeef 'wire the fixture, run pending')"
AID="$(sed -n 's/^added #\([0-9a-f]\{8\}\).*/\1/p' <<<"$ADDOUT")"
newturn
say "working

## Remaining
- the fixture item"
check "a CLI-added item blocks like any open item" block "wire the fixture"
reqcli --tick deadbeef "$AID" "suite green, exit 0" >/dev/null
echo '- [ ] (deadbeef) a fresh md item to churn the file' >>"$WL"
newturn
say "working

## Remaining
- the churn item"
out="$(run)"
if grep -qF "a fresh md item to churn" <<<"$out" && ! grep -qF "wire the fixture" <<<"$out"; then
    pass "md churn does not resurrect a CLI-ticked item (overlay outlives the sync)"
else
    fail "resurrection or lost item: ${out:0:260}"
fi

echo "== 134. a torn event-log tail is healed, never merged into the next event =="
setup
reqcli --add deadbeef "first item" >/dev/null
EV="${WL%.md}.events.jsonl"
printf '{"ev":"add","id":"tornado1","at":"' >>"$EV" # a crash mid-write: no newline
reqcli --add deadbeef "second item" >/dev/null
OUT=$(
    python3 - "$EV" <<'PYEOF'
import json, sys
adds, bad, merged = 0, 0, 0
for line in open(sys.argv[1]):
    line = line.strip()
    if not line:
        continue
    try:
        ev = json.loads(line)
    except ValueError:
        bad += 1
        if "second item" in line:
            merged += 1
        continue
    if ev.get("ev") == "add":
        adds += 1
print("adds=%d bad=%d merged=%d" % (adds, bad, merged))
PYEOF
)
if [[ "$OUT" == "adds=2 bad=1 merged=0" ]]; then
    pass "the torn fragment stays its own dead line; both real events parse"
else
    fail "torn-tail healing broke: $OUT"
fi
if reqcli --list | grep -qF "second item"; then
    pass "the fold reads through the torn line"
else
    fail "the fold lost the event after the torn line"
fi

echo "== 135. RACE: concurrent --add writers lose nothing =="
setup
for i in $(seq 1 16); do
    as_peer "sess000$i" reqcli --add "sess000$i" "concurrent item $i" >/dev/null 2>&1 &
done
wait
OUT=$(
    python3 - "${WL%.md}.events.jsonl" <<'PYEOF'
import json, sys
ids, bad, n = set(), 0, 0
for line in open(sys.argv[1]):
    line = line.strip()
    if not line:
        continue
    try:
        ev = json.loads(line)
    except ValueError:
        bad += 1
        continue
    if ev.get("ev") == "add":
        n += 1
        ids.add(ev.get("id"))
print("adds=%d ids=%d bad=%d" % (n, len(ids), bad))
PYEOF
)
if [[ "$OUT" == "adds=16 ids=16 bad=0" ]]; then
    pass "16 concurrent adds -> 16 parseable events, 16 distinct ids"
else
    fail "concurrent adds were lost or torn: $OUT"
fi

echo "== 136. --tick REFUSES a completion without evidence =="
setup
ADDOUT="$(reqcli --add deadbeef 'prove the flag binds')"
AID="$(sed -n 's/^added #\([0-9a-f]\{8\}\).*/\1/p' <<<"$ADDOUT")"
if reqcli --tick deadbeef "$AID" "done i guess" >/dev/null 2>"$BASE/tick.err"; then
    fail "an evidence-free tick was accepted"
else
    if grep -qF "REFUSED" "$BASE/tick.err" && ! grep -q '"ev":"state"' "${WL%.md}.events.jsonl"; then
        pass "refused loudly (exit nonzero) and wrote nothing"
    else
        fail "refusal was silent or leaked an event: $(head -c 160 "$BASE/tick.err")"
    fi
fi
if reqcli --tick deadbeef "$AID" "suite run green, exit 0" >/dev/null 2>&1 &&
    reqcli --list | grep -qF -- '- [x]'; then
    pass "the same tick with evidence lands"
else
    fail "an evidenced tick was rejected"
fi

echo "== 137. LADDER rung 1 (45 min): a quiet lease pings, report-only =="
setup
brief_now
hand_now
EV="${WL%.md}.events.jsonl"
OLD=$(date -u -d '-50 minutes' +%Y-%m-%dT%H:%M:%SZ)
UNTIL=$(date -u -d '+30 minutes' +%Y-%m-%dT%H:%MZ)
printf '{"ev":"add","id":"aaaa1111","at":"%s","by":"deadbeef","s":" ","o":"deadbeef","t":"long docs job"}\n{"ev":"lease","id":"aaaa1111","at":"%s","by":"deadbeef","until":"%s","worker":"bw1"}\n' \
    "$OLD" "$OLD" "$UNTIL" >>"$EV"
BG='[{"id":"bw1","type":"shell","status":"running","description":"watch","command":"sleep 999"}]'
say "answer

## Remaining
- the docs job rides a lease"
check "a 50-minute-quiet lease still ALLOWS the stop" allow "Liveness ping"
# CONTROL: a fresh lease draws no ping (same shape, young stamps).
setup
brief_now
hand_now
NOW=$(date -u +%Y-%m-%dT%H:%M:%SZ)
UNTIL=$(date -u -d '+30 minutes' +%Y-%m-%dT%H:%MZ)
printf '{"ev":"add","id":"aaaa1112","at":"%s","by":"deadbeef","s":" ","o":"deadbeef","t":"fresh docs job"}\n{"ev":"lease","id":"aaaa1112","at":"%s","by":"deadbeef","until":"%s","worker":"bw1"}\n' \
    "$NOW" "$NOW" "$UNTIL" >>"${WL%.md}.events.jsonl"
BG='[{"id":"bw1","type":"shell","status":"running","description":"watch","command":"sleep 999"}]'
say "answer

## Remaining
- the docs job rides a lease"
out="$(run)"
if ! grep -qF "Liveness ping" <<<"$out"; then
    pass "CONTROL: a fresh lease draws no ping"
else
    fail "a fresh lease was pinged: ${out:0:200}"
fi

echo "== 138. rungs 2 and 3 block ONCE each; the DEFAULT exit always clears =="
setup
brief_now
hand_now
OLD=$(date -u -d '-100 minutes' +%Y-%m-%dT%H:%M:%SZ)
UNTIL=$(date -u -d '+30 minutes' +%Y-%m-%dT%H:%MZ)
printf '{"ev":"add","id":"aaaa2221","at":"%s","by":"deadbeef","s":" ","o":"deadbeef","t":"stalled docs job"}\n{"ev":"lease","id":"aaaa2221","at":"%s","by":"deadbeef","until":"%s","worker":"bw1"}\n' \
    "$OLD" "$OLD" "$UNTIL" >>"${WL%.md}.events.jsonl"
BG='[{"id":"bw1","type":"shell","status":"running","description":"watch","command":"sleep 999"}]'
say "answer

## Remaining
- the stalled docs job"
check "100 quiet minutes hits the INVESTIGATE rung" block "IN-FLIGHT WORK HAS GONE QUIET"
check "the rung fires ONCE per stamp, not every stop" allow ""
setup
brief_now
hand_now
OLD=$(date -u -d '-125 minutes' +%Y-%m-%dT%H:%M:%SZ)
UNTIL=$(date -u -d '+30 minutes' +%Y-%m-%dT%H:%MZ)
printf '{"ev":"add","id":"aaaa2222","at":"%s","by":"deadbeef","s":" ","o":"deadbeef","t":"two-hour stall"}\n{"ev":"lease","id":"aaaa2222","at":"%s","by":"deadbeef","until":"%s","worker":"bw1"}\n' \
    "$OLD" "$OLD" "$UNTIL" >>"${WL%.md}.events.jsonl"
BG='[{"id":"bw1","type":"shell","status":"running","description":"watch","command":"sleep 999"}]'
say "answer

## Remaining
- the two-hour stall"
check "125 quiet minutes hits the RESOLVE rung" block "QUIET FOR TWO HOURS"
reqcli --defer deadbeef aaaa2222 "keep waiting on the delegate? DEFAULT: stop it and redelegate WHY: the delegate holds state only it can flush, so killing it loses work HOW: the operator says stop, or the DEFAULT redelegates" >/dev/null
newturn
say "deferred it

## Remaining
- the stall, deferred with a default"
check "the [?]+DEFAULT exit clears the top rung (it can never trap)" allow "operator may answer"

echo "== 139. GONE fires on a vanished worker; UNVERIFIABLE never reads as dead =="
setup
brief_now
hand_now
NOW=$(date -u +%Y-%m-%dT%H:%M:%SZ)
UNTIL=$(date -u -d '+30 minutes' +%Y-%m-%dT%H:%MZ)
printf '{"ev":"add","id":"aaaa3331","at":"%s","by":"deadbeef","s":" ","o":"deadbeef","t":"delegated build"}\n{"ev":"lease","id":"aaaa3331","at":"%s","by":"deadbeef","until":"%s","worker":"bogusw1"}\n' \
    "$NOW" "$NOW" "$UNTIL" >>"${WL%.md}.events.jsonl"
BG='[]'
say "answer

## Remaining
- the delegated build (ongoing on its worker)"
check "a lease whose worker the harness no longer lists blocks with the facts" block "NOT in the harness background list"
# THE FALSE-ACCUSATION CONTROL (the one failure mode worse than no check):
# an UNVERIFIABLE worker (teammate: no OS process exists by design) must not
# read as gone. Same fixture shape, worker present in the event.
setup
brief_now
hand_now
NOW=$(date -u +%Y-%m-%dT%H:%M:%SZ)
UNTIL=$(date -u -d '+30 minutes' +%Y-%m-%dT%H:%MZ)
printf '{"ev":"add","id":"aaaa3332","at":"%s","by":"deadbeef","s":" ","o":"deadbeef","t":"delegated design"}\n{"ev":"lease","id":"aaaa3332","at":"%s","by":"deadbeef","until":"%s","worker":"tm1"}\n' \
    "$NOW" "$NOW" "$UNTIL" >>"${WL%.md}.events.jsonl"
BG='[{"id":"tm1","type":"teammate","status":"running","description":"design agent"}]'
say "answer

## Remaining
- the delegated design (ongoing on its agent)"
out="$(run)"
got="$(python3 -c 'import json,sys
raw=sys.stdin.read().strip()
print(json.loads(raw).get("decision","allow") if raw else "allow")' <<<"$out" 2>/dev/null)"
if [[ "$got" == "allow" ]] && ! grep -qF "NOT in the harness background list" <<<"$out"; then
    pass "an unverifiable (teammate) worker is never accused of being dead"
else
    fail "false accusation or wrong verdict (got=$got): ${out:0:260}"
fi

echo "== 140. OS verification: confirmed / suspect / unverifiable, on real processes =="
# Library-level, against the real OS: a spawned child IS found, a killed one
# is not, and a teammate task is honestly unverifiable.
OUT=$(
    cd "$BASE" && python3 - "$(dirname "$HOOK")" <<'PYEOF'
import os, subprocess, sys, time
sys.path.insert(0, sys.argv[1])
import wl_liveness as L
cmd = "sleep 987654321099"
child = subprocess.Popen(["sleep", "987654321099"])
time.sleep(0.2)
anc = {os.getpid()}
bg = [
    {"id": "sh1", "type": "shell", "status": "running", "command": cmd},
    {"id": "tm1", "type": "teammate", "status": "running", "description": "agent"},
]
v1 = L.verify_background(bg, ancestors=anc)
child.kill()
child.wait()
time.sleep(0.2)
v2 = L.verify_background(bg, ancestors=anc)
print("live=%s teammate=%s dead=%s" % (v1.get("sh1"), v1.get("tm1"), v2.get("sh1")))
PYEOF
)
if [[ "$OUT" == "live=confirmed teammate=unverifiable dead=suspect" ]]; then
    pass "a live child is confirmed, a killed one is suspect, a teammate is unverifiable"
else
    fail "verification verdicts wrong: $OUT"
fi

echo "== 141. AUTONOMY: a DEFAULT past its window is executed, not restated =="
setup
brief_now
hand_now
OLD=$(date -u -d '-130 minutes' +%Y-%m-%dT%H:%M:%SZ)
printf '{"ev":"add","id":"bbbb1111","at":"%s","by":"deadbeef","s":"?","o":"deadbeef","t":"keep the flag? DEFAULT: keep it"}\n' \
    "$OLD" >>"${WL%.md}.events.jsonl"
say "answer

## Remaining
- the flag decision, deferred with a default"
check "an aged deferral demands its default be executed" block "OUTLIVED their autonomy window"
reqcli --update deadbeef bbbb1111 "operator pinged; window restarted deliberately" >/dev/null
newturn
say "answer

## Remaining
- the flag decision, deferred with a default"
check "refreshing the item restarts the window (the exit is always available)" allow "operator may answer"
# CONTROL: a fresh deferral just reports (case 3 pins this too; here it is
# the explicit twin of the aged fixture above).
setup
brief_now
hand_now
NOW=$(date -u +%Y-%m-%dT%H:%M:%SZ)
printf '{"ev":"add","id":"bbbb1112","at":"%s","by":"deadbeef","s":"?","o":"deadbeef","t":"keep the flag? DEFAULT: keep it"}\n' \
    "$NOW" >>"${WL%.md}.events.jsonl"
say "answer

## Remaining
- the flag decision, deferred with a default"
check "CONTROL: a fresh deferral does not demand execution" allow "operator may answer"
# DRAIN CAP: five aged deferrals arrive three at a time, never as a wall.
setup
brief_now
hand_now
OLD=$(date -u -d '-130 minutes' +%Y-%m-%dT%H:%M:%SZ)
for i in 1 2 3 4 5; do
    printf '{"ev":"add","id":"bbbb222%s","at":"%s","by":"deadbeef","s":"?","o":"deadbeef","t":"aged question %s DEFAULT: option A"}\n' \
        "$i" "$OLD" "$i" >>"${WL%.md}.events.jsonl"
done
say "answer

## Remaining
- five aged deferrals draining"
out="$(run)"
if grep -qF "OUTLIVED their autonomy window" <<<"$out" && grep -qF "and 2 more, held back" <<<"$out"; then
    pass "five expired deferrals drain 3 per stop, never as a wall"
else
    fail "drain cap wrong: ${out:0:260}"
fi

echo "== 142. the judge CACHES an identical world+message; any change re-asks =="
setup
brief_now
hand_now
task 7 pending "merge the chain"
say "answer

## Remaining
| #7 | merge the chain | pending, me |"
cat >"$BASE/binonly/claude" <<SHIM
#!/bin/bash
echo call >>"$BASE/judgecalls"
echo '{"is_error":false,"structured_output":{"verdict":"stop","reason":"legitimately parked","next_action":"none"}}'
SHIM
chmod +x "$BASE/binonly/claude"
runj >/dev/null
N1=$(grep -c call "$BASE/judgecalls" 2>/dev/null)
out="$(runj)"
N2=$(grep -c call "$BASE/judgecalls" 2>/dev/null)
if [[ "$N1" == "1" && "$N2" == "1" ]] && grep -qF "cached" <<<"$out"; then
    pass "an identical world and message reuses the verdict (1 paid call, not 2)"
else
    fail "cache did not hold: calls=$N1,$N2 out=${out:0:200}"
fi
task 7 in_progress "merge the chain"
newturn
say "answer

## Remaining
| #7 | merge the chain | ongoing, me |"
runj >/dev/null
N3=$(grep -c call "$BASE/judgecalls" 2>/dev/null)
if [[ "$N3" == "2" ]]; then
    pass "CONTROL: a changed world signature pays the judge again"
else
    fail "a changed world did not re-ask: calls=$N3"
fi

echo "== 143. the dead-code gate: every top-level def is referenced somewhere =="
DEADCODE_PY='
import ast, pathlib, re, sys
d = pathlib.Path(sys.argv[1])
srcs = {p.name: p.read_text() for p in sorted(d.glob("wl_*.py"))}
srcs["worklist.py"] = (d / "worklist.py").read_text()
allsrc = "\n".join(srcs.values())
orphans = []
for name, src in srcs.items():
    for node in ast.parse(src).body:
        if isinstance(node, ast.FunctionDef):
            refs = len(re.findall(r"\b%s\b" % re.escape(node.name), allsrc))
            if refs < 2:  # the def line itself is one
                orphans.append("%s.%s" % (name, node.name))
print("orphans=%s" % ",".join(orphans) if orphans else "orphans=none")
sys.exit(1 if orphans else 0)
'
if OUT=$(python3 -c "$DEADCODE_PY" "$(dirname "$HOOK")"); then
    pass "no unreferenced top-level function in the shipped modules ($OUT)"
else
    fail "dead code shipped: $OUT"
fi
# PROVE THE INSTRUMENT: the same gate must FIRE on a planted orphan.
mkdir -p "$BASE/deadcode"
cp "$(dirname "$HOOK")"/wl_*.py "$(dirname "$HOOK")/worklist.py" "$BASE/deadcode/"
printf '\n\ndef orphan_zombie_fn():\n    return 1\n' >>"$BASE/deadcode/wl_core.py"
if OUT=$(python3 -c "$DEADCODE_PY" "$BASE/deadcode"); then
    fail "the dead-code gate cannot fire (planted orphan passed): $OUT"
else
    if grep -qF "orphan_zombie_fn" <<<"$OUT"; then
        pass "CONTROL: the gate fires on a planted orphan def"
    else
        fail "the gate failed for the wrong reason: $OUT"
    fi
fi

echo "== 145. a TICK FLOOD is absorbed as bookkeeping, never asked about =="
# The v10 upgrade guard: tick identity hashes the RENDERED line, and the
# store rewrite can re-render history, so the first post-upgrade stop may
# see hundreds of historical [x] as "new" (791 in the live store). That is
# drift, not 791 simultaneous fixes: absorb with one note, and never route
# those lines into the I7 evidence check either.
setup
say "done for now"
brief_now
reg_repo
run >/dev/null # marker init at current HEAD with zero ticks
for i in $(seq 1 25); do
    echo "- [x] (deadbeef) historical item $i" >>"$WL"
done
out="$(run)"
got="$(python3 -c 'import json,sys
raw=sys.stdin.read().strip()
print(json.loads(raw).get("decision","allow") if raw else "allow")' <<<"$out" 2>/dev/null)"
if [[ "$got" == "allow" ]] && grep -qF "absorbed as bookkeeping" <<<"$out"; then
    pass "25 suddenly-new ticks absorb silently with one note (no judge, no I7)"
else
    fail "tick flood mishandled (got=$got): ${out:0:260}"
fi
out="$(run)"
if ! grep -qF "absorbed as bookkeeping" <<<"$out"; then
    pass "the absorption is recorded; a second stop does not repeat the note"
else
    fail "flood note repeated: ${out:0:200}"
fi

echo "== 144. STATE.md staleness is WORLD-KEYED: a quiet world never stales it =="
# The v9 trap this kills: the 10-minute age limit was outpaced by the
# 5-minute poll cron, so a QUIET session went stale every other poll. Age
# alone is not staleness; the world signature must also have moved. The write
# stays INLINE rather than folded into hand_now: passing WORKLIST_TASKS_DIR
# explicitly here is the point of the case (the signature must cover the task
# dir the stop will read), and the explicitness is what documents that.
setup
brief_now
task 7 pending "thing"
say "answer

## Remaining
| #7 | thing | pending, me |"
printf 'You are picking up the ci-overhaul session driving PR #543 to green on branch 0728-2. Round 23 went red on a dead-shell finding, now fixed by running the stop-gate suite from test-hooks.sh.\n\n## Next action\n\nPush and watch the run, then bump the submodule pointers to the squash commits before the merge chain closes out.\n' |
    TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" WORKLIST_TASKS_DIR="$BASE/tasks" \
        WORKLIST_AGENT_BRANCH=agenttest python3 "$HOOK" --state deadbeef >/dev/null
check "fresh STATE.md, settled world: allowed" allow ""
age_state deadbeef 25 # the heading stamp is the age source, not the file mtime
check "an OLD STATE.md with an UNCHANGED world is NOT stale (the poll trap is dead)" allow ""
task 8 pending "the new thing"
newturn
say "answer

## Remaining
| #7 | thing | pending, me |
| #8 | the new thing | pending, me |"
check "the same old STATE.md goes stale the moment the world moves" block "STATE.md is stale"
# 1.4: the verdict must name the CAUSE. It used to print only "(N min old,
# limit M)", and a session read that as pure wall-clock and concluded the code
# disagreed with its own documentation. The age is a symptom; the signature
# moving is the trigger, and a document a week old whose world never moved is
# never stale.
OUT="$(run)"
if grep -qF "your world signature moved since it was written" <<<"$OUT"; then
    pass "212: a stale STATE.md names the signature move, not just an age"
else
    fail "212: the stale verdict does not say WHY: ${OUT:0:300}"
fi

echo "== 146. v11: the store-derived GUIDE rides every full stop, bounded =="
# The operator's ask: "--list should be used always on stop hook to output
# enforced guided instructions". The defect it fixes: v10 stamped every item
# and the hand-authored Remaining prose never read the store.

# (a) ALLOW stop: guide present, with the state-correct verbs.
setup
brief_now
hand_now
NOW=$(date -u +%Y-%m-%dT%H:%M:%SZ)
UNTIL=$(date -u -d '+30 minutes' +%Y-%m-%dT%H:%MZ)
printf '{"ev":"add","id":"cccc1111","at":"%s","by":"deadbeef","s":" ","o":"deadbeef","t":"delegated build"}\n{"ev":"lease","id":"cccc1111","at":"%s","by":"deadbeef","until":"%s","worker":"bw1"}\n{"ev":"add","id":"cccc1112","at":"%s","by":"deadbeef","s":"?","o":"deadbeef","t":"ship the flag? DEFAULT: ship it"}\n' \
    "$NOW" "$NOW" "$UNTIL" "$NOW" >>"${WL%.md}.events.jsonl"
BG='[{"id":"bw1","type":"shell","status":"running","description":"watch","command":"sleep 999"}]'
say "answer

## Remaining
- the delegated build and the flag question"
out="$(run)"
got="$(python3 -c 'import json,sys
raw=sys.stdin.read().strip()
print(json.loads(raw).get("decision","allow") if raw else "allow")' <<<"$out" 2>/dev/null)"
if [[ "$got" == "allow" ]] && grep -qF "WORKLIST GUIDE" <<<"$out" &&
    grep -qF -- "--update deadbeef cccc1111" <<<"$out" &&
    grep -qF "DEFAULT executes in" <<<"$out"; then
    pass "an ALLOW stop carries the guide: [>] gets --update, fresh [?] gets its window"
else
    fail "guide missing or wrong verbs on allow (got=$got): ${out:0:300}"
fi

# (b) BLOCK stop under WORKLIST_FOCUS=off: the guide rides the dump-all block
# reason, [ ] gets --tick. v13's FOCUSED block deliberately drops the guide
# (operator, 2026-07-31, superseding the v11 every-full-stop mandate), so the
# focused variant is asserted guide-FREE in (b2) below.
setup
brief_now
hand_now
echo '- [ ] (deadbeef) wire the perf fixture' >>"$WL"
say "answer

## Remaining
- the perf fixture"
export WORKLIST_FOCUS=off
out="$(run)"
unset WORKLIST_FOCUS
if grep -qF '"decision": "block"' <<<"$out" && grep -qF "WORKLIST GUIDE" <<<"$out" &&
    grep -qF -- "--tick deadbeef" <<<"$out" && grep -qF "do it, then" <<<"$out"; then
    pass "a FOCUS=off block carries the guide, and an open item gets --tick"
else
    fail "guide missing from the FOCUS=off block path: ${out:0:300}"
fi

# (b2) the v13 FOCUSED block is guide-free: the noise reduction IS the
# feature, and the one check that needs store data carries its own slice.
out="$(run)"
if grep -qF '"decision": "block"' <<<"$out" && ! grep -qF "WORKLIST GUIDE" <<<"$out" &&
    grep -qF "OPEN worklist item" <<<"$out"; then
    pass "the focused block drops the guide and still names the open item"
else
    fail "focused block carried the guide or lost the item: ${out:0:300}"
fi

# (c) ZERO actionable: SILENT since v18. This case used to assert the
# opposite -- "a short honest line, never ambiguous silence" -- and the
# operator overruled it (2026-08-04, quoting a stop whose whole output was
# that line plus the wakeup times): "silent when there is nothing to act on...
# let's go for efficient ai context usage". The ambiguity the old line guarded
# against is also gone, because the poll fast path already exits silently many
# times an hour, so zero bytes is the session's familiar "nothing to do".
setup
brief_now
hand_now
say "all done"
out="$(run)"
if ! grep -qF "no actionable items in the store" <<<"$out"; then
    pass "an empty store no longer announces its own emptiness"
else
    fail "the empty-guide line survived: ${out:0:260}"
fi
# This fixture is NOT silent, and it should not be: a repo with no request
# traffic at all trips the poll-backoff advisory, which is a real thing to act
# on. Pinning that here keeps the zero-byte case below honest -- it proves the
# silence there comes from having nothing to say, not from a muted report.
if grep -qF "INBOX HAS BEEN QUIET" <<<"$out"; then
    pass "and the one section that DID have something to say still speaks"
else
    fail "the backoff advisory was swallowed with the guide: ${out:0:260}"
fi
# NOW the zero-byte case: one fresh request in the log (between two OTHER
# sessions, so it never reaches this inbox) resets the quiet clock and silences
# the backoff advisory, leaving a stop with genuinely nothing to report.
askid_as cafe1234 beefcafe "a question between two other sessions" >/dev/null
newturn
say "all done"
out="$(run)"
rc=$?
if [[ "$rc" -eq 0 && -z "$out" ]]; then
    pass "a clean stop with nothing to act on emits ZERO bytes"
else
    fail "the nothing-to-report stop was not silent (rc=$rc): ${out:0:260}"
fi
# CONTROL, so the silence above is the guide standing down and not the battery
# being skipped: the SAME fixture plus one real item speaks up immediately.
echo '- [?] (deadbeef) keep the flag? DEFAULT: keep it' >>"$WL"
newturn
say "all done

## Remaining
- the flag decision, deferred with a default"
out="$(run)"
if grep -qF "WORKLIST GUIDE" <<<"$out" && grep -qF "keep the flag?" <<<"$out"; then
    pass "CONTROL: one actionable item brings the guide straight back"
else
    fail "CONTROL: the guide stayed silent with a real item: ${out:0:260}"
fi

# (d) TRUNCATION is loud: 15 open items show 12 and SAY 3 were held back.
setup
brief_now
hand_now
for i in $(seq 1 15); do
    echo "- [ ] (deadbeef) backlog item number $i" >>"$WL"
done
say "answer

## Remaining
- fifteen backlog items"
export WORKLIST_FOCUS=off
out="$(run)"
unset WORKLIST_FOCUS
# -o, not -c: the hook's output is ONE JSON line, so a line count reads 1.
NSHOWN=$(grep -oF "do it, then --tick" <<<"$out" | wc -l)
if [[ "$NSHOWN" == "12" ]] && grep -qF "+3 more actionable" <<<"$out" &&
    grep -qF "HELD BACK by the 12-line cap" <<<"$out"; then
    pass "the cap emits 12 of 15 and names the 3 it dropped"
else
    fail "silent or wrong truncation: shown=$NSHOWN out=${out:0:300}"
fi

# (e) VERB-STATE MATCH for the remaining shapes: undefaulted [?], expired
# window, dead lease, each with its own exit spelled out.
setup
brief_now
hand_now
OLD=$(date -u -d '-130 minutes' +%Y-%m-%dT%H:%M:%SZ)
PAST=$(date -u -d '-5 minutes' +%Y-%m-%dT%H:%MZ)
printf '{"ev":"add","id":"cccc2221","at":"%s","by":"deadbeef","s":"?","o":"deadbeef","t":"aged choice DEFAULT: option A"}\n' \
    "$OLD" >>"${WL%.md}.events.jsonl"
echo '- [?] (deadbeef) an undefaulted question' >>"$WL"
echo "- [>] (deadbeef) until:$PAST stale delegation" >>"$WL"
say "answer

## Remaining
- three differently broken items"
export WORKLIST_FOCUS=off
out="$(run)"
unset WORKLIST_FOCUS
ok=1
for needle in "execute its DEFAULT now" "--defer deadbeef" "LEASE DEAD" "re-lease: --lease deadbeef"; do
    grep -qF -- "$needle" <<<"$out" || {
        ok=0
        echo "        MISSING: $needle"
    }
done
if [[ "$ok" == 1 ]]; then
    pass "expired [?], undefaulted [?] and a dead lease each carry their own exit"
else
    fail "verb-state mismatch: ${out:0:400}"
fi

# (f) --list --open is the SAME slice from the CLI, and the full dump keeps
# the [x] history the slice excludes.
setup
echo '- [ ] (deadbeef) open thing' >>"$WL"
echo '- [x] (deadbeef) finished thing, exit 0' >>"$WL"
OPEN="$(reqcli --list --open deadbeef)"
FULL="$(reqcli --list)"
if grep -qF -- "--tick deadbeef" <<<"$OPEN" && grep -qF "open thing" <<<"$OPEN" &&
    ! grep -qF "finished thing" <<<"$OPEN" && grep -qF "finished thing" <<<"$FULL"; then
    pass "--list --open shows the hook's slice; plain --list keeps the history"
else
    fail "CLI slice mismatch: OPEN=${OPEN:0:200} FULL=${FULL:0:120}"
fi

# (f2) the CLI slice is UNCAPPED. GUIDE_TRUNCATED (case (d)) tells the reader
# to run this exact command "for the full slice", and until the full= flag the
# command re-rendered the same 12 rows -- advice that looped back onto itself.
# 15 open items must all appear here, with NO truncation footer. The 12-line
# cap stays on the Stop path, which case (d) pins; this case and that one are
# each other's control, so a regression that lifts the cap everywhere (or
# restores it here) fails one of the two.
setup
for i in $(seq 1 15); do
    echo "- [ ] (deadbeef) uncapped backlog item number $i" >>"$WL"
done
OPEN="$(reqcli --list --open deadbeef)"
NSHOWN=$(grep -cF "do it, then --tick" <<<"$OPEN")
MISS=""
for i in $(seq 1 15); do
    grep -qF "uncapped backlog item number $i" <<<"$OPEN" || MISS="$MISS $i"
done
if [[ "$NSHOWN" == "15" && -z "$MISS" ]] && ! grep -qF "HELD BACK" <<<"$OPEN"; then
    pass "--list --open lifts the 12-line cap: all 15 items, no truncation footer"
else
    fail "CLI slice still capped (shown=$NSHOWN missing=[$MISS]): ${OPEN:0:300}"
fi

# ---------------------------------------------------------------------------
# v12 (cases 147+): deferral justification (WHY/HOW as real store fields),
# the harsh judge audit over sitting [?] items, and the CI-waiting force.
# The operator's evidence: 30+ deferrals sat 117 minutes while the session
# stopped three times with "the run is healthy"; one deferral requested a
# feature that had ALREADY been built. Every FIRE case is paired with a
# SILENT control differing by one planted fact, and every demand's solo exit
# is proven to reach an allowed stop (the anti-deadlock property).
# ---------------------------------------------------------------------------

shim_judge_out() { # shim_judge_out '<structured_output JSON>' -- canned claude + call counter
    SO="$1" CALLS="$BASE/judgecalls" SHIM="$BASE/binonly/claude" python3 -c '
import json, os, pathlib, stat
out = {"is_error": False, "structured_output": json.loads(os.environ["SO"])}
body = ("#!/bin/bash\necho x >> " + json.dumps(os.environ["CALLS"]) + "\n"
        "echo " + json.dumps(json.dumps(out)) + "\n")
p = pathlib.Path(os.environ["SHIM"])
p.write_text(body)
p.chmod(p.stat().st_mode | stat.S_IEXEC)
'
}

echo "== 147. --defer refuses a deferral that cannot justify its seat =="
setup
NID=$(reqcli --add deadbeef "choose the flag default" | sed -n 's/^added #\([0-9a-f]*\).*/\1/p')
OUT=$(reqcli --defer deadbeef "$NID" "keep the flag? DEFAULT: keep it" 2>&1)
RC=$?
if [[ "$RC" -ne 0 ]] && grep -qF "WHY:" <<<"$OUT" && grep -qF "HOW:" <<<"$OUT"; then
    pass "a deferral with no WHY/HOW is refused, naming both fields"
else
    fail "unjustified --defer was accepted (rc=$RC): ${OUT:0:200}"
fi
if ! grep -q '"ev":"state"' "${WL%.md}.events.jsonl"; then
    pass "the refused defer wrote NO state event (a rejected write is not a delivered one)"
else
    fail "a refused defer still wrote an event: $(grep '"ev":"state"' "${WL%.md}.events.jsonl")"
fi
OUT=$(reqcli --defer deadbeef "$NID" "keep the flag? DEFAULT: keep it WHY: did not get to it yet HOW: revisit next week" 2>&1)
RC=$?
if [[ "$RC" -ne 0 ]] && grep -qF "avoidance" <<<"$OUT"; then
    pass "a vacuous WHY ('did not get to it') is refused as avoidance"
else
    fail "the vague-why gate did not fire (rc=$RC): ${OUT:0:200}"
fi
OUT=$(reqcli --defer deadbeef "$NID" "keep the flag? DEFAULT: keep it WHY: flipping it changes billing for live users, an operator-only call HOW: operator confirms, or the DEFAULT keeps it TRIED: read the pricing doc BLOCKED_ON: operator" 2>&1)
RC=$?
if [[ "$RC" -eq 0 ]] && grep -q '"j":{' "${WL%.md}.events.jsonl" &&
    grep -qF '"why":"flipping it changes billing' "${WL%.md}.events.jsonl" &&
    grep -qF '"blocked_on":"operator"' "${WL%.md}.events.jsonl"; then
    pass "a justified defer lands with WHY/HOW/TRIED/BLOCKED_ON as real JSON fields"
else
    fail "justified defer rc=$RC or fields missing: $(tail -c 300 "${WL%.md}.events.jsonl")"
fi

echo "== 148. an AGED [?] with no justification is demanded, bounded =="
setup
brief_now
hand_now
OLD=$(date -u -d '-60 minutes' +%Y-%m-%dT%H:%M:%SZ)
printf '{"ev":"add","id":"dddd1111","at":"%s","by":"deadbeef","s":"?","o":"deadbeef","t":"quarantine the leg? DEFAULT: quarantine it"}\n' \
    "$OLD" >>"${WL%.md}.events.jsonl"
say "answer

## Remaining
- the quarantine decision, deferred"
check "a 60-minute [?] with no WHY/HOW blocks for its justification" block "NO justification on record"
# THE HONEST-ANSWER EXIT (anti-deadlock): re-deferring with a WHY/HOW is
# completable alone in one turn, and it reaches an allowed stop.
reqcli --defer deadbeef dddd1111 "quarantine the leg? DEFAULT: quarantine it WHY: only the operator can accept the coverage loss it causes HOW: operator approves, or the DEFAULT quarantines it" >/dev/null
newturn
say "justified the deferral

## Remaining
- the quarantine decision, deferred with its justification"
check "answering the WHY/HOW honestly reaches an allowed stop" allow "operator may answer"
# CONTROL: the same age WITH a justification never fires (one planted fact).
setup
brief_now
hand_now
printf '{"ev":"add","id":"dddd1112","at":"%s","by":"deadbeef","s":"?","o":"deadbeef","t":"price the tier? DEFAULT: keep the price WHY: pricing is an operator-only call with revenue stakes HOW: operator picks a number"}\n' \
    "$OLD" >>"${WL%.md}.events.jsonl"
say "answer

## Remaining
- the pricing decision, deferred with its justification"
out="$(run)"
got="$(python3 -c 'import json,sys
raw=sys.stdin.read().strip()
print(json.loads(raw).get("decision","allow") if raw else "allow")' <<<"$out" 2>/dev/null)"
if [[ "$got" == "allow" ]] && ! grep -qF "NO justification on record" <<<"$out"; then
    pass "CONTROL: the same aged [?] WITH a WHY/HOW does not fire"
else
    fail "justified deferral was nagged (got=$got): ${out:0:260}"
fi
# DRAIN CAP: five aged unjustified arrive three at a time, never as a wall.
setup
brief_now
hand_now
for i in 1 2 3 4 5; do
    printf '{"ev":"add","id":"dddd222%s","at":"%s","by":"deadbeef","s":"?","o":"deadbeef","t":"aged bare question %s DEFAULT: option A"}\n' \
        "$i" "$OLD" "$i" >>"${WL%.md}.events.jsonl"
done
say "answer

## Remaining
- five bare deferrals"
out="$(run)"
if grep -qF "5 deferred item(s) have sat" <<<"$out" && grep -qF "and 2 more, held back" <<<"$out"; then
    pass "five unjustified deferrals drain 3 per stop, never as a wall"
else
    fail "justification drain cap wrong: ${out:0:300}"
fi

echo "== 149. THE CENTREPIECE: sitting on a CI watch forces the backlog =="
setup
brief_now
hand_now
OLD=$(date -u -d '-60 minutes' +%Y-%m-%dT%H:%M:%SZ)
printf '{"ev":"add","id":"eeee1111","at":"%s","by":"deadbeef","s":"?","o":"deadbeef","t":"backfill the audit log? DEFAULT: backfill last 30 days WHY: only the operator can accept the storage cost HOW: operator confirms the budget"}\n' \
    "$OLD" >>"${WL%.md}.events.jsonl"
BG='[{"id":"cw1","type":"shell","status":"running","command":"gh run watch 30514648812 --exit-status","description":"watch CI run"}]'
say "the run is healthy, nothing to do

## Remaining
- the backfill decision, deferred"
check "a CI watch as the ONLY in-flight work demands the aged backlog by id" block "YOU ARE SITTING ON CI"
out="$(run)"
if grep -qF "#eeee1111" <<<"$out" && grep -qF "NEXT:" <<<"$out"; then
    pass "the force names the item id and its next verb"
else
    fail "no id or verb in the CI-waiting block: ${out:0:300}"
fi
# ANTI-DEADLOCK: doing the demanded work reaches an allowed stop, with the
# same watch still running.
reqcli --tick deadbeef eeee1111 "backfilled, exit 0" >/dev/null
newturn
say "executed the backfill default while the run finished

## Remaining
nothing open; the CI watch is still running"
check "doing the demanded work reaches an allowed stop under the same watch" allow ""
# CONTROL 1 (one planted fact: a real worker beside the watch): not sitting.
setup
brief_now
hand_now
printf '{"ev":"add","id":"eeee2221","at":"%s","by":"deadbeef","s":"?","o":"deadbeef","t":"backfill the audit log? DEFAULT: backfill last 30 days WHY: only the operator can accept the storage cost HOW: operator confirms the budget"}\n' \
    "$OLD" >>"${WL%.md}.events.jsonl"
BG='[{"id":"cw1","type":"shell","status":"running","command":"gh run watch 30514648812 --exit-status","description":"watch CI run"},{"id":"bw2","type":"shell","status":"running","command":"bash scripts/build-embed.sh","description":"rebuild embed assets"}]'
say "watching the run while the embed rebuild runs

## Remaining
- the backfill decision, deferred"
out="$(run)"
if ! grep -qF "SITTING ON CI" <<<"$out"; then
    pass "CONTROL: a non-watch worker beside the watch means not sitting"
else
    fail "the force fired despite real delegated work: ${out:0:260}"
fi
# CONTROL 2 (one planted fact: the backlog is fresh): nothing to force.
setup
brief_now
hand_now
NOW=$(date -u +%Y-%m-%dT%H:%M:%SZ)
printf '{"ev":"add","id":"eeee3331","at":"%s","by":"deadbeef","s":"?","o":"deadbeef","t":"backfill the audit log? DEFAULT: backfill last 30 days WHY: only the operator can accept the storage cost HOW: operator confirms the budget"}\n' \
    "$NOW" >>"${WL%.md}.events.jsonl"
BG='[{"id":"cw1","type":"shell","status":"running","command":"gh run watch 30514648812 --exit-status","description":"watch CI run"}]'
say "watching the run

## Remaining
- the backfill decision, freshly deferred"
out="$(run)"
if ! grep -qF "SITTING ON CI" <<<"$out"; then
    pass "CONTROL: a FRESH deferral is not demanded (re-justifying is a real exit)"
else
    fail "the force fired on a fresh backlog: ${out:0:260}"
fi

echo "== 150. the judge AUDITS sitting justifications; do_now REOPENS the item =="
setup
brief_now
hand_now
OLD=$(date -u -d '-60 minutes' +%Y-%m-%dT%H:%M:%SZ)
printf '{"ev":"add","id":"ffff1111","at":"%s","by":"deadbeef","s":"?","o":"deadbeef","t":"quarantine the flaky leg? DEFAULT: quarantine it WHY: only the operator can accept the coverage loss HOW: operator approves the quarantine"}\n' \
    "$OLD" >>"${WL%.md}.events.jsonl"
say "answer

## Remaining
- the quarantine decision, deferred with its justification"
shim_judge_out '{"verdict":"stop","reason":"ok","next_action":"none","defer_audit":[{"id":"ffff1111","verdict":"do_now","reason":"the flake stats are in the tree","order":"read the flake stats and quarantine it yourself"}]}'
checkj "a do_now audit verdict blocks with the judge's order" block "DEFERRAL AUDIT REJECTED"
LIST="$(reqcli --list)"
if grep -qF -- "- [ ]" <<<"$LIST" && grep -qF "REOPENED by the stop-gate judge" <<<"$LIST"; then
    pass "the rejected deferral is REOPENED as ordinary open work"
else
    fail "no reopened item in the store: ${LIST:0:260}"
fi
# ANTI-DEADLOCK: doing the reopened work reaches an allowed stop.
reqcli --tick deadbeef ffff1111 "quarantined, exit 0" >/dev/null
newturn
say "quarantined the leg as ordered

## Remaining
nothing"
checkj "ticking the reopened item with evidence reaches an allowed stop" allow ""

echo "== 151. a VALID audit verdict is banked; an untouched item is asked once =="
setup
# The [?] item is also an operator-only mail candidate, so the unconfigured
# email channel queues a class-1 note ahead of the audit note. Both are
# one-shots and neither is lost; this case asserts the audit note is produced,
# so it drains wide rather than waiting a stop for its turn.
export WORKLIST_REPORT_PER_STOP=9
brief_now
hand_now
OLD=$(date -u -d '-60 minutes' +%Y-%m-%dT%H:%M:%SZ)
printf '{"ev":"add","id":"ffff2221","at":"%s","by":"deadbeef","s":"?","o":"deadbeef","t":"rotate the org key? DEFAULT: keep the schedule WHY: rotation locks every teammate out for an hour, an operator-only call HOW: operator names the window"}\n' \
    "$OLD" >>"${WL%.md}.events.jsonl"
say "answer

## Remaining
- the rotation decision, deferred with its justification"
shim_judge_out '{"verdict":"stop","reason":"genuinely operator-only","next_action":"none","defer_audit":[{"id":"ffff2221","verdict":"valid","reason":"locking teammates out is a real operator-only stake","order":""}]}'
checkj "a valid verdict allows and reports the banked reason" allow "survived interrogation"
N1=$(wc -l <"$BASE/judgecalls" 2>/dev/null || echo 0)
checkj "the untouched item is not re-audited (banked per stamp)" allow ""
N2=$(wc -l <"$BASE/judgecalls" 2>/dev/null || echo 0)
if [[ "$N1" -eq 1 && "$N2" -eq 1 ]]; then
    pass "one judge call total: the bank and the verdict cache both held ($N1,$N2)"
else
    fail "judge was re-paid for an untouched item: calls=$N1 then $N2"
fi
# FAIL CLOSED: an audit that was requested and not answered is a judge error.
setup
brief_now
hand_now
printf '{"ev":"add","id":"ffff3331","at":"%s","by":"deadbeef","s":"?","o":"deadbeef","t":"rotate the org key? DEFAULT: keep the schedule WHY: rotation locks every teammate out for an hour, an operator-only call HOW: operator names the window"}\n' \
    "$OLD" >>"${WL%.md}.events.jsonl"
say "answer

## Remaining
- the rotation decision, deferred with its justification"
shim_judge_out '{"verdict":"stop","reason":"ok","next_action":"none"}'
checkj "a requested audit with no defer_audit answer FAILS CLOSED" block "no usable defer_audit"

echo "== 152. the silent poll forfeits to the justification demand =="
setup
brief_now
hand_now
OLD=$(date -u -d '-40 minutes' +%Y-%m-%dT%H:%M:%SZ)
printf '{"ev":"add","id":"dddd7771","at":"%s","by":"deadbeef","s":"?","o":"deadbeef","t":"bare aged question DEFAULT: option A"}\n' \
    "$OLD" >>"${WL%.md}.events.jsonl"
say "answer

## Remaining
- the bare deferral"
check "the full stop demands the justification (and banks the poll baseline)" block "NO justification on record"
reqcli --poll deadbeef >/dev/null
OUT="$(run)"
if [[ -n "$OUT" ]] && grep -qF "NO justification on record" <<<"$OUT"; then
    pass "a poll stop cannot slip past an unjustified aged [?]"
else
    fail "the poll fast path swallowed the justification demand: '${OUT:0:200}'"
fi
# CONTROL (one planted fact: the same item, justified): the poll is silent.
setup
brief_now
hand_now
printf '{"ev":"add","id":"dddd7772","at":"%s","by":"deadbeef","s":"?","o":"deadbeef","t":"aged question DEFAULT: option A WHY: only the operator can weigh the trade HOW: operator answers"}\n' \
    "$OLD" >>"${WL%.md}.events.jsonl"
say "answer

## Remaining
- the justified deferral"
check "baseline stop allows" allow ""
reqcli --poll deadbeef >/dev/null
OUT="$(run)"
RC=$?
if [[ "$RC" -eq 0 && -z "$OUT" ]]; then
    pass "CONTROL: the same age WITH a justification keeps the silent poll"
else
    fail "a justified deferral forfeited the fast path: rc=$RC '${OUT:0:160}'"
fi

echo "== 153. a LATCHED ladder rung must not forfeit the silent poll forever =="
# WHAT BROKE. The ladder is latched (fire_once records each rung against the
# subject's stamp), but poll_fast_path forfeited on RAW AGE and never consulted
# that latch. So the two disagreed: the report went silent after firing once
# while the forfeit kept firing on every poll.
#
# Measured 2026-07-30: task #20 sat in_progress for 298 minutes, legitimately,
# waiting on an operator decision and a running agent. Its rung had long since
# fired, yet every five-minute inbox poll paid the full battery and demanded a
# full report, with no way to discharge it short of finishing or abandoning a
# task that was not this session's to finish. That is the "a gate that cannot be
# satisfied deadlocks the session" trap the v10 brief warned about, reintroduced
# by a threshold comparison that looked harmless.
#
# Both directions are asserted, because the cure must not silence a rung that
# has NOT yet been reported.
setup
brief_now
hand_now
# The task must exist BEFORE the baseline stop banks the poll baseline: task
# statuses are part of the world signature, so creating it afterwards moves the
# signature and a DIFFERENT check fires. That fixture bug cost a round here, and
# it is worth stating because it makes a real fix look broken.
task 20 in_progress "wave B acceptance, blocked on the operator"
say "answer

## Remaining
| #20 | wave B acceptance | ongoing, the operator |"
check "baseline stop allows" allow ""
# Its rung ALREADY fired against this exact stamp. Written straight into the
# state doc (which is NOT part of the world signature, so this is safe after the
# baseline) because the point is the latch, not how it got set.
python3 - "$WL" <<'PY'
import json, pathlib, sys
wl = pathlib.Path(sys.argv[1])
p = wl.with_suffix(".state-deadbeef.json")
doc = json.loads(p.read_text()) if p.exists() else {}
stamp = "2026-07-30T06:29:37Z"
doc.setdefault("tasks_seen", {})["20"] = {"status": "in_progress", "since": stamp}
doc.setdefault("ladder", {})["task:20"] = {"investigate": stamp, "resolve": stamp}
p.write_text(json.dumps(doc))
PY
reqcli --poll deadbeef >/dev/null
OUT="$(run)"
RC=$?
if [[ "$RC" -eq 0 && -z "$OUT" ]]; then
    pass "a latched rung on a 298m task keeps the silent poll"
else
    fail "a latched rung still forfeited the fast path: rc=$RC '${OUT:0:200}'"
fi

# CONTROL, and it is the one that matters: the SAME task at the SAME age with
# the rung NOT yet fired must still forfeit. Without this the fix could be a
# blanket "never forfeit on tasks" and the suite would not notice.
setup
brief_now
hand_now
task 20 in_progress "wave B acceptance, blocked on the operator"
say "answer

## Remaining
| #20 | wave B acceptance | ongoing, the operator |"
check "baseline stop allows" allow ""
python3 - "$WL" <<'PY'
import json, pathlib, sys
wl = pathlib.Path(sys.argv[1])
p = wl.with_suffix(".state-deadbeef.json")
doc = json.loads(p.read_text()) if p.exists() else {}
doc.setdefault("tasks_seen", {})["20"] = {"status": "in_progress", "since": "2026-07-30T06:29:37Z"}
doc["ladder"] = {}  # never fired
p.write_text(json.dumps(doc))
PY
reqcli --poll deadbeef >/dev/null
OUT="$(run)"
if [[ -n "$OUT" ]]; then
    pass "CONTROL: an UNFIRED rung at the same age still forfeits the silent poll"
else
    fail "an unfired blocking rung was swallowed by the fast path"
fi

echo "== 153a. T1/T2: a missing .agent/<branch>/ blocks with the bootstrap, ONCE as a wall =="
# Decision 5: block with the exact bootstrap commands, NEVER auto-create (the
# RULES.md copy-forward is a judgement call a hook must not make). The WALL is
# shown once per branch per session, latched on agent_boot_told; the follow-up
# is a one-liner that keeps blocking without repeating itself.
setup
brief_now
say "answer

## Remaining
- #7 thing (pending)"
task 7 pending "thing"
rm -rf "$BASE/proj/.agent/agenttest"
OUT="$(run)"
if grep -qF '"decision": "block"' <<<"$OUT" && grep -qF "mkdir -p .agent/agenttest" <<<"$OUT" &&
    grep -qF "RULES.md" <<<"$OUT"; then
    pass "T1 FIRE: a missing branch dir blocks with the exact bootstrap commands"
else
    fail "T1: bootstrap wall absent or wrong: ${OUT:0:200}"
fi
if [[ -d "$BASE/proj/.agent/agenttest" ]]; then
    fail "T1: the hook AUTO-CREATED the branch dir (decision 5 violated)"
else
    pass "T1: the hook did not auto-create the directory"
fi
newturn
say "answer

## Remaining
- #7 thing (pending)"
OUT2="$(run)"
if grep -qF '"decision": "block"' <<<"$OUT2" && grep -qF "still absent" <<<"$OUT2" &&
    ! grep -qF "mkdir -p .agent/agenttest" <<<"$OUT2"; then
    pass "T2: the second stop still blocks but the wall is not repeated"
else
    fail "T2: second-stop shape wrong: ${OUT2:0:200}"
fi
# SILENT control: with the dir restored and a fresh STATE.md the wall is gone.
# The world is moved first (task 8) or the third consecutive unmoved stop
# would trip the STUCK detector and this control would test the wrong gate.
mkdir -p "$BASE/proj/.agent/agenttest"
task 8 pending "moved"
hand_now
newturn
say "answer

## Remaining
- #7 thing (pending)
- #8 moved (pending)"
check "T1 CONTROL: dir present + fresh STATE.md allows, no bootstrap text" allow ""

echo "== 153b. T7a/T7b: adopt-on-first-sight, and the adopt NEVER fires on stale =="
# A second session arriving on a branch has no recorded signature for the
# document the first session wrote; the old pure-age fallback would order an
# immediate rewrite, reproducing the churn the redesign fixes. Adoption is
# bounded (60m) and fires ONLY on an "ok" verdict: banking the signature on a
# "stale" verdict would let the next stop compare cur_sig against a signature
# recorded DURING the block and allow -- a gate that clears itself without a
# rewrite. T7b is the anti-vacuity control: it must block TWICE running.
setup
brief_now
say "answer

## Remaining
- #7 thing (pending)"
task 7 pending "thing"
printf '%s' "$STATE_BODY" >"$BASE/proj/.agent/agenttest/STATE.md" # planted: NO signature banked
touch -d '30 minutes ago' "$BASE/proj/.agent/agenttest/STATE.md"
check "T7a: an unsigned 30-minute document is ADOPTED, not rewritten" allow ""
if python3 -c "
import json, sys
doc = json.load(open('${WL%.md}.state-deadbeef.json'))
sys.exit(0 if doc.get('state_sig') else 1)"; then
    pass "T7a: the adopt banked state_sig into the state doc (read, not inferred)"
else
    fail "T7a: no state_sig was banked on the ok verdict"
fi
# T7b: age the document past the ADOPT horizon with no signature -> stale, and
# it must STAY stale on a second stop over an unchanged world.
setup
brief_now
say "answer

## Remaining
- #7 thing (pending)"
task 7 pending "thing"
printf '%s' "$STATE_BODY" >"$BASE/proj/.agent/agenttest/STATE.md"
touch -d '90 minutes ago' "$BASE/proj/.agent/agenttest/STATE.md"
check "T7b FIRE: an unsigned 90-minute document is past the adopt horizon" block "STATE.md is stale"
newturn
say "answer

## Remaining
- #7 thing (pending)"
check "T7b ANTI-VACUITY: it blocks AGAIN on an unchanged world (no self-clear)" block "STATE.md is stale"
if python3 -c "
import json, sys
doc = json.load(open('${WL%.md}.state-deadbeef.json'))
sys.exit(1 if doc.get('state_sig') else 0)"; then
    pass "T7b: state_sig was NOT banked during the stale blocks"
else
    fail "T7b: the stale path banked a signature (the gate would clear itself)"
fi
# Move the world (task 8) before the control stop, or the fourth consecutive
# unmoved stop trips the STUCK detector instead of testing this gate.
task 8 pending "moved"
hand_now
newturn
say "answer

## Remaining
- #7 thing (pending)
- #8 moved (pending)"
check "T7b CONTROL: a real --state rewrite clears it" allow ""

echo "== 153b2. C12: a PEER's item must not stale MY recovery document =="
# The v18 bug this pins. state_world_sig hashed EVERY item regardless of owner,
# so with ~48 agents in one worktree any peer --add/--tick moved my key. A check
# whose contract is "an unchanged world never stales it" then degenerated into
# "fires every 15 minutes" -- indistinguishable from wall-clock at the point of
# observation, which is what made the WRONG fix (raise the limit) look obvious.
# v17 had already scoped world_sig this way; state_world_sig was left behind.
setup
brief_now
say "answer

## Remaining
- #7 thing (pending)"
task 7 pending "thing"
printf '%s' "$STATE_BODY" >"$BASE/proj/.agent/agenttest/STATE.md"
touch -d '30 minutes ago' "$BASE/proj/.agent/agenttest/STATE.md"
check "153b2 SETUP: the document is adopted and its signature banked" allow ""
# A DIFFERENT session adds its own item. Peer bookkeeping, not my world.
reqcli --add cafe1234 "peer item nobody else owns" >/dev/null
newturn
say "answer

## Remaining
- #7 thing (pending)"
check "153b2: a peer's item does NOT stale my recovery document" allow ""

echo "== 153b3. C12 CONTROL: MY OWN item still stales it =="
# Without this the narrowing above is indistinguishable from disabling the check.
#
# The item is ADDED AND TICKED in one go, deliberately. An item merely added is
# ALSO an open-items violation, and with only one rotating check surfaced per
# stop the hook showed that one instead -- my first draft asserted on a message
# the rotation had chosen not to print. Ticking leaves exactly one rotating
# violation, so what the stop surfaces is unambiguous.
IID=$(reqcli --add deadbeef "my own item, which IS a reason to rewrite" | grep -oE '#[0-9a-f]+' | tr -d '#')
reqcli --tick deadbeef "$IID" "landed, suite green, exit 0" >/dev/null
newturn
say "answer

## Remaining
- #7 thing (pending)"
OUT="$(run)"
if grep -qF "STATE.md is stale" <<<"$OUT"; then
    pass "153b3: my own item still stales it -- the ownership scope did not disable the check"
else
    fail "153b3: the ownership scope swallowed a REAL staleness: ${OUT:0:400}"
fi

echo "== 153c. T9: a detached HEAD is REPORT-ONLY, never a block =="
# Operator decision 2026-07-30, a deliberate departure from the
# V_PR_UNREADABLE blocks-when-blind precedent: HEAD detaches during every
# interactive rebase and this operator rebase-merges everything, so blocking
# each stop for the duration would be worse than one turn of unenforced
# staleness. The note must NAME the blindness; silence would be a pass-quietly.
setup
brief_now
hand_now
say "answer

## Remaining
- #7 thing (pending)"
task 7 pending "thing"
WORKLIST_AGENT_BRANCH=""
OUT="$(run)"
WORKLIST_AGENT_BRANCH=agenttest
if ! grep -qF '"decision": "block"' <<<"$OUT" && grep -qF "freshness check is BLIND" <<<"$OUT"; then
    pass "T9: no-branch allows AND names the blindness"
else
    fail "T9: no-branch handled wrongly: ${OUT:0:200}"
fi
say "answer

## Remaining
- #7 thing (pending)"
OUT="$(run)"
if ! grep -qF "freshness check is BLIND" <<<"$OUT"; then
    pass "T9 CONTROL: with a branch resolvable the blindness note is absent"
else
    fail "T9 CONTROL: blindness note present despite a resolvable branch"
fi

echo "== 153d. T10/T11: trap TITLES feed the judge; bodies and ### never do =="
setup
printf '# Traps\n\n## Real trap title one\n\nsecret body line\n\n### a sub-heading\n\n## Second title\n' >"$BASE/proj/.agent/TRAPS.md"
OUT=$(
    python3 - "$(dirname "$HOOK")" "$BASE/proj" <<'PYEOF'
import sys
sys.path.insert(0, sys.argv[1])
import wl_store as S
import worklist_messages as M
heads = S.trap_headings(sys.argv[2])
prompt = M.JUDGE_PROMPT % {
    "streak": 1, "remaining": "r", "leases": 0, "loop": "l",
    "citations": "c", "message": "m",
    "traps": "\n".join("  - " + h for h in heads) or "  (none recorded)",
}
checks = [
    ("titles-only", heads == ["Real trap title one", "Second title"]),
    ("prompt-has-title", "Real trap title one" in prompt),
    ("prompt-no-body", "secret body line" not in prompt),
    ("prompt-no-subheading", "a sub-heading" not in prompt),
]
import pathlib
empty = S.trap_headings(sys.argv[2] + "/nonexistent")
checks.append(("absent-file-empty-list", empty == []))
for name, ok in checks:
    print(("PASS " if ok else "FAIL ") + name)
PYEOF
)
if grep -qF "FAIL" <<<"$OUT"; then
    fail "T10/T11: $OUT"
else
    pass "T10/T11: judge sees ## titles only; bodies, ###, and absent files are safe"
fi

echo "== 153e. T12: the silent poll survives an old STATE.md on a quiet world =="
# The poll fast path needs NO new forfeit: STATE.md staleness is world-keyed,
# so an unchanged world cannot stale it, and a moved world already forfeits
# the fast path at the world_sig comparison. Adding a forfeit would
# reintroduce the 5-minute-poll trap the world-keying exists to kill.
setup
brief_now
hand_now
echo '- [?] (deadbeef) keep the flag? DEFAULT: keep it WHY: operator trade HOW: operator answers' >>"$WL"
say "answer

## Remaining
- the flag decision, deferred with a default"
check "T12 baseline stop allows" allow ""
age_state deadbeef 25
reqcli --poll deadbeef >/dev/null
OUT="$(run)"
RC=$?
if [[ "$RC" -eq 0 && -z "$OUT" ]]; then
    pass "T12: a 25-minute STATE.md on an unchanged world keeps the silent poll"
else
    fail "T12: the old STATE.md forfeited the fast path: rc=$RC '${OUT:0:160}'"
fi
task 9 pending "world moved"
reqcli --poll deadbeef >/dev/null
OUT="$(run)"
if [[ -n "$OUT" ]]; then
    pass "T12 CONTROL: a moved world pays the full battery"
else
    fail "T12 CONTROL: the moved world stayed silent"
fi

echo "== 154. v18: NEXT WAKEUPS is GONE, and a broken schedule still warns =="
# Operator, 2026-08-04: "we don't need to print next wakeup times. We should
# just track the hook moments and notify/warn when needed. let's go for
# efficient ai context usage." The section printed every task's next firing on
# every full stop. This case is what remains of the old case 154: the display
# must be absent on BOTH emit paths, and the one actionable row it used to
# carry -- a schedule the hook cannot parse -- must still fire on its own.
setup
brief_now
hand_now
CRONS='[{"id":"w","schedule":"17 * * * *","prompt":"HOURLY LOOP fixture: advance the campaign."},{"id":"p","schedule":"*/5 * * * *","prompt":"INBOX POLL fixture."}]'
# A real item, so this stop has a guide to print: without one the whole report
# would be silent (v18) and the absence assertion below would pass vacuously.
echo '- [?] (deadbeef) keep the flag? DEFAULT: keep it' >>"$WL"
say "answer

## Remaining
- #7 thing (pending)
- the flag decision, deferred with a default"
task 7 pending "thing"
OUT="$(run)"
if ! grep -qF "NEXT WAKEUPS" <<<"$OUT" && ! grep -qF "HOURLY LOOP fixture" <<<"$OUT" &&
    ! grep -qF "INBOX POLL fixture" <<<"$OUT"; then
    pass "154a: the allow stop prints no wakeup times and no cron prompt labels"
else
    fail "154a: the wakeup display survived on allow: ${OUT:0:260}"
fi
# CONTROL that 154a is not vacuous: the stop DID produce its normal report, so
# the absence above is the section being gone rather than the hook being mute.
if grep -qF "WORKLIST GUIDE" <<<"$OUT" && grep -qF "keep the flag?" <<<"$OUT"; then
    pass "154a CONTROL: the stop still emitted its guide, so the absence is real"
else
    fail "154a CONTROL: the stop emitted nothing at all: ${OUT:0:260}"
fi
# The FOCUS=off dump-all block carried the section too; it must not any more.
age_state deadbeef 20
task 8 pending "moved"
newturn
say "answer

## Remaining
- #7 thing (pending)
- #8 moved (pending)"
export WORKLIST_FOCUS=off
OUT="$(run)"
unset WORKLIST_FOCUS
if grep -qF '"decision": "block"' <<<"$OUT" && ! grep -qF "NEXT WAKEUPS" <<<"$OUT"; then
    pass "154b: the FOCUS=off block carries no wakeup section either"
else
    fail "154b: the wakeup section survived on the dump-all block: ${OUT:0:220}"
fi
# THE SURVIVING WARNING. An unparseable schedule is invisible to every other
# cron check, so deleting the display must not delete this.
setup
brief_now
hand_now
CRONS='[{"id":"w","schedule":"not a cron","prompt":"BROKEN fixture."},{"id":"p","schedule":"*/5 * * * *","prompt":"INBOX POLL fixture."}]'
say "answer

## Remaining
- #7 thing (pending)"
task 7 pending "thing"
OUT="$(run)"
if grep -qF "CANNOT PARSE" <<<"$OUT" && grep -qF "BROKEN fixture." <<<"$OUT"; then
    pass "154c: an unparseable schedule is still named, on its own warning"
else
    fail "154c: a broken schedule went silent with the section: ${OUT:0:260}"
fi
# CONTROL: with every schedule valid the warning is silent, so it reports a
# real defect rather than firing on any cron list at all.
setup
brief_now
hand_now
CRONS='[{"id":"w","schedule":"17 * * * *","prompt":"HOURLY LOOP fixture."},{"id":"p","schedule":"*/5 * * * *","prompt":"INBOX POLL fixture."}]'
say "answer

## Remaining
- #7 thing (pending)"
task 7 pending "thing"
OUT="$(run)"
if ! grep -qF "CANNOT PARSE" <<<"$OUT"; then
    pass "154c CONTROL: valid schedules raise no warning"
else
    fail "154c CONTROL: the warning fired on a healthy cron list: ${OUT:0:260}"
fi

echo "== 155. supervised MUST correlate to the live worker, not just be fresh =="
# Real review finding (PR #546, comment 3686791985): the freshest [>] item
# across ALL in-flight records was taken as proof of supervision, with no
# check that it names the SAME worker as the one in live_bg. Two leases: one
# tracking bw1 (the actual watched job) gone STALE past the threshold, one
# tracking an UNRELATED worker zz9 kept FRESH. The unrelated fresh one must
# NOT excuse the stale one -- that is exactly the forgotten-watch case this
# exemption exists to exclude.
export WORKLIST_STUCK_ROUNDS=1
setup
brief_now
hand_now
STALE=$(date -u -d '-100 minutes' +%Y-%m-%dT%H:%M:%SZ)
FRESH=$(date -u +%Y-%m-%dT%H:%M:%SZ)
UNTIL=$(date -u -d '+30 minutes' +%Y-%m-%dT%H:%MZ)
printf '{"ev":"add","id":"bbbb0001","at":"%s","by":"deadbeef","s":" ","o":"deadbeef","t":"watching the real job"}\n{"ev":"lease","id":"bbbb0001","at":"%s","by":"deadbeef","until":"%s","worker":"bw1"}\n' \
    "$STALE" "$STALE" "$UNTIL" >>"${WL%.md}.events.jsonl"
printf '{"ev":"add","id":"bbbb0002","at":"%s","by":"deadbeef","s":" ","o":"deadbeef","t":"unrelated, still being renewed"}\n{"ev":"lease","id":"bbbb0002","at":"%s","by":"deadbeef","until":"%s","worker":"zz9"}\n' \
    "$FRESH" "$FRESH" "$UNTIL" >>"${WL%.md}.events.jsonl"
BG='[{"id":"bw1","type":"shell","status":"running","description":"the actual watched job"}]'
task 9 pending "thing"
say "answer

## Remaining
- #9 thing (pending), watched via bw1 and zz9"
for i in 1 2 3; do LAST="$(run)"; done
if grep -qF "EMPLOY A PLANNING OR INVESTIGATION AGENT" <<<"$LAST"; then
    pass "155: an uncorrelated fresh lease does NOT excuse a stale supervising one"
else
    fail "155: the unrelated fresh lease wrongly silenced the exempt-overrun: ${LAST:0:220}"
fi

echo "== 155b. CONTROL: the CORRELATED lease being fresh DOES supervise =="
setup
brief_now
hand_now
FRESH=$(date -u +%Y-%m-%dT%H:%M:%SZ)
UNTIL=$(date -u -d '+30 minutes' +%Y-%m-%dT%H:%MZ)
printf '{"ev":"add","id":"bbbb0003","at":"%s","by":"deadbeef","s":" ","o":"deadbeef","t":"watching the real job"}\n{"ev":"lease","id":"bbbb0003","at":"%s","by":"deadbeef","until":"%s","worker":"bw1"}\n' \
    "$FRESH" "$FRESH" "$UNTIL" >>"${WL%.md}.events.jsonl"
BG='[{"id":"bw1","type":"shell","status":"running","description":"the actual watched job"}]'
task 9 pending "thing"
say "answer

## Remaining
- #9 thing (pending), watched via bw1"
for i in 1 2 3; do LAST="$(run)"; done
if ! grep -qF "EMPLOY A PLANNING OR INVESTIGATION AGENT" <<<"$LAST"; then
    pass "155b CONTROL: a fresh lease correlated to the live worker DOES supervise"
else
    fail "155b: a genuinely fresh, correlated lease still fired: ${LAST:0:220}"
fi
unset WORKLIST_STUCK_ROUNDS

echo "== 156. v13 FOCUS: one rotating check per stop, LRU rotation =="
# Two rotating checks outstanding (an open item and a stale brief). Stop 1
# surfaces exactly one; stop 2 surfaces the OTHER; stop 3 cycles back. The
# header counts what is held back, so nothing is silently forgotten.
setup
hand_now
export WORKLIST_STUCK_ROUNDS=99
echo '- [ ] (deadbeef) open thing' >>"$WL"
# no brief_now: the session-brief check is the second rotating violation.
# The message carries a '## Remaining' section so exactly TWO rotating
# checks are outstanding and the cycle length is 2, not 3.
say "answer

## Remaining
- the open thing (pending, mine)"
OUT1="$(run)"
newturn
say "answer

## Remaining
- the open thing (pending, mine)"
OUT2="$(run)"
newturn
say "answer

## Remaining
- the open thing (pending, mine)"
OUT3="$(run)"
unset WORKLIST_STUCK_ROUNDS
has() { grep -qF "$2" <<<"$1"; }
o1_open=$(has "$OUT1" "OPEN worklist item" && echo y || echo n)
o1_brief=$(has "$OUT1" "session brief" && echo y || echo n)
o2_open=$(has "$OUT2" "OPEN worklist item" && echo y || echo n)
o2_brief=$(has "$OUT2" "session brief" && echo y || echo n)
if [[ "$o1_open$o1_brief" == "yn" || "$o1_open$o1_brief" == "ny" ]] &&
    [[ "$o2_open$o2_brief" == "yn" || "$o2_open$o2_brief" == "ny" ]] &&
    [[ "$o1_open" != "$o2_open" ]] &&
    grep -qF "check(s) outstanding, surfacing" <<<"$OUT1" &&
    grep -qF "more check(s) outstanding" <<<"$OUT1"; then
    pass "156: each stop surfaces exactly one rotating check, and they alternate"
else
    fail "156: rotation wrong (stop1 open=$o1_open brief=$o1_brief, stop2 open=$o2_open brief=$o2_brief)"
fi
o3_open=$(has "$OUT3" "OPEN worklist item" && echo y || echo n)
if [[ "$o3_open" == "$o1_open" ]]; then
    pass "156b: stop 3 cycles back to stop 1's check (LRU, nothing starves)"
else
    fail "156b: rotation did not cycle (stop1 open=$o1_open, stop3 open=$o3_open)"
fi
unset -f has

echo "== 156c. CONTROL: WORKLIST_FOCUS=off restores the dump-all block =="
# The revert control for the whole feature: the same two-check fixture shows
# BOTH bodies in one block when focus is off.
setup
hand_now
echo '- [ ] (deadbeef) open thing' >>"$WL"
say "answer"
export WORKLIST_FOCUS=off
OUT="$(run)"
unset WORKLIST_FOCUS
if grep -qF "OPEN worklist item" <<<"$OUT" && grep -qF "session brief" <<<"$OUT" &&
    grep -qF "check(s) failed" <<<"$OUT"; then
    pass "156c CONTROL: FOCUS=off carries every violation in one block"
else
    fail "156c: FOCUS=off lost a violation: ${OUT:0:300}"
fi

echo "== 156d. ALWAYS tier rides every focused block beside the rotation =="
# CI-red is latched (its block budget is spent at compute time), so hiding it
# behind rotation would swallow it forever. It must appear IN ADDITION to the
# one rotating check.
ci_setup
ci_rollup FAILURE "[$(ci_job "Quality / Static" FAILURE)]"
echo '- [ ] (deadbeef) open thing' >>"$WL"
out="$(ci_run)"
if grep -qF '"decision": "block"' <<<"$out" && grep -qF "CI IS RED ON PR" <<<"$out" &&
    grep -qF "OPEN worklist item" <<<"$out"; then
    pass "156d: the latched CI-red text and one rotating check ride the same focused block"
else
    fail "156d: ALWAYS tier missing from the focused block: ${out:0:400}"
fi

echo "== 157. CI-queue backpressure: a saturated queue says DO NOT PUSH =="
# The operator's live incident (2026-07-31): pushes queued runs behind each
# other and a run sat pending 25+ minutes. The hook must see the jam and tell
# the session to work locally instead of pushing more.
ci_queue_fixture() { # ci_queue_fixture <runs-json>
    echo "$1" >"$BASE/ci-runs.json"
    rm -f "${WL%.md}.ciqueue-deadbeef"
    cat >"$BASE/binonly/gh" <<SHIM
#!/bin/bash
for a in "\$@"; do
    case "\$a" in
        *lastEditedAt*) cat "$BASE/ci-fresh.json"; exit 0 ;;
        query=*) cat "$BASE/ci-rollup.json"; exit 0 ;;
    esac
done
case "\$*" in
    *actions/runs*) cat "$BASE/ci-runs.json"; exit 0 ;;
    *actions/jobs/*) cat "$BASE/ci-job.json"; exit 0 ;;
esac
echo '{}'
SHIM
    chmod +x "$BASE/binonly/gh"
}
ci_setup
ci_rollup SUCCESS "[$(ci_job "Quality / Static" SUCCESS)]"
QOLD=$(date -u -d '-30 minutes' +%Y-%m-%dT%H:%M:%SZ)
ci_queue_fixture "{\"workflow_runs\":[{\"status\":\"queued\",\"created_at\":\"$QOLD\"},{\"status\":\"completed\",\"created_at\":\"$QOLD\"}]}"
out="$(ci_run)"
if grep -qF "CI QUEUE IS SATURATED" <<<"$out" && grep -qF "DO NOT PUSH" <<<"$out"; then
    pass "157: a 30-minute-queued newest run raises the saturation note"
else
    fail "157: saturation note missing: ${out:0:300}"
fi

echo "== 157b. CONTROL: an in-progress run with an empty queue is clear =="
ci_queue_fixture "{\"workflow_runs\":[{\"status\":\"in_progress\",\"created_at\":\"$QOLD\"},{\"status\":\"completed\",\"created_at\":\"$QOLD\"}]}"
out="$(ci_run)"
if ! grep -qF "CI QUEUE IS SATURATED" <<<"$out"; then
    pass "157b CONTROL: a running (not queued) newest run stays quiet"
else
    fail "157b: clear queue raised the note: ${out:0:300}"
fi

echo "== 157c. depth trigger: two queued runs saturate even when fresh =="
QNEW=$(date -u -d '-1 minute' +%Y-%m-%dT%H:%M:%SZ)
ci_queue_fixture "{\"workflow_runs\":[{\"status\":\"queued\",\"created_at\":\"$QNEW\"},{\"status\":\"queued\",\"created_at\":\"$QOLD\"}]}"
out="$(ci_run)"
if grep -qF "CI QUEUE IS SATURATED" <<<"$out" && grep -qF "2 queued run(s)" <<<"$out"; then
    pass "157c: queue depth >= 2 saturates regardless of the newest run's age"
else
    fail "157c: depth trigger missing: ${out:0:300}"
fi

echo "== 157d. FAILURE MODE: a broken gh grants NO slack (fails toward pressure) =="
rm -f "${WL%.md}.ciqueue-deadbeef"
cat >"$BASE/binonly/gh" <<SHIM
#!/bin/bash
for a in "\$@"; do
    case "\$a" in
        *lastEditedAt*) cat "$BASE/ci-fresh.json"; exit 0 ;;
        query=*) cat "$BASE/ci-rollup.json"; exit 0 ;;
    esac
done
case "\$*" in
    *actions/runs*) echo "boom" >&2; exit 1 ;;
esac
echo '{}'
SHIM
chmod +x "$BASE/binonly/gh"
out="$(ci_run)"
if ! grep -qF "CI QUEUE IS SATURATED" <<<"$out"; then
    pass "157d: gh failure reads as unknown, note absent, no relaxation granted"
else
    fail "157d: a blind queue check granted slack: ${out:0:300}"
fi

echo "== 157e. SUPPRESSION PAIR: pr-stale folds into the note only while saturated =="
# Stale body: last push AFTER the PR-body edit (edit stamped in 2000).
ci_setup
ci_rollup SUCCESS "[$(ci_job "Quality / Static" SUCCESS)]"
echo '{"data":{"repository":{"pullRequests":{"nodes":[{"number":543,"lastEditedAt":"2000-01-01T00:00:00Z","updatedAt":"2000-01-01T00:00:00Z"}]}}}}' >"$BASE/ci-fresh.json"
ci_queue_fixture "{\"workflow_runs\":[{\"status\":\"queued\",\"created_at\":\"$QOLD\"}]}"
CIMSG="answer with work remaining"
echo '- [ ] (deadbeef) open thing' >>"$WL"
out="$(ci_run)"
if ! grep -qF "YOU PUSHED AFTER YOUR LAST PR-DESCRIPTION EDIT" <<<"$out" &&
    grep -qF "the PR body is stale; fold the refresh into that next push" <<<"$out"; then
    pass "157e: under saturation the stale-body nag folds into the queue note"
else
    fail "157e: fold wrong: ${out:0:400}"
fi
# The pair's control: same stale body, queue now clear -> the check fires.
ci_queue_fixture "{\"workflow_runs\":[{\"status\":\"completed\",\"created_at\":\"$QOLD\"}]}"
export WORKLIST_FOCUS=off
out="$(ci_run)"
unset WORKLIST_FOCUS
unset CIMSG
if grep -qF "YOU PUSHED AFTER YOUR LAST PR-DESCRIPTION EDIT" <<<"$out"; then
    pass "157e CONTROL: with the queue clear the stale-body check fires again"
else
    fail "157e CONTROL: pr-stale did not fire on a clear queue: ${out:0:300}"
fi

echo "== 157f. the queue read is cached: two stops inside the TTL, one gh hit =="
ci_setup
ci_rollup SUCCESS "[$(ci_job "Quality / Static" SUCCESS)]"
ci_queue_fixture "{\"workflow_runs\":[{\"status\":\"queued\",\"created_at\":\"$QOLD\"}]}"
cat >"$BASE/binonly/gh" <<SHIM
#!/bin/bash
for a in "\$@"; do
    case "\$a" in
        *lastEditedAt*) cat "$BASE/ci-fresh.json"; exit 0 ;;
        query=*) cat "$BASE/ci-rollup.json"; exit 0 ;;
    esac
done
case "\$*" in
    *actions/runs*) echo hit >>"$BASE/runs-hits.txt"; cat "$BASE/ci-runs.json"; exit 0 ;;
esac
echo '{}'
SHIM
chmod +x "$BASE/binonly/gh"
rm -f "$BASE/runs-hits.txt" "${WL%.md}.ciqueue-deadbeef"
ci_run >/dev/null
ci_run >/dev/null
HITS=$(wc -l <"$BASE/runs-hits.txt" 2>/dev/null || echo 0)
if [[ "$HITS" == "1" ]]; then
    pass "157f: the second stop served the queue state from the cache"
else
    fail "157f: expected exactly 1 runs-endpoint hit, got $HITS"
fi

echo "== 159. operator email: an operator request is mailed once, with its relay command =="
# v13 F2. NOTHING here touches the network: WORKLIST_EMAIL_TRANSPORT=file:<dir>
# makes send() write the SES payload it would have POSTed into <dir>, so the
# assertions read the exact JSON body that would have gone to AWS.
mail_fixture() { # a configured channel writing into $BASE/mail (call AFTER setup)
    mkdir -p "$BASE/mail"
    cat >"$BASE/ses.env" <<'ENVEOF'
AWS_SES_ACCESS_KEY_ID=AKIAFIXTURENOTREAL
AWS_SES_SECRET_ACCESS_KEY=secretfixturenotreal
AWS_SES_REGION=eu-central-1
AWS_SES_FROM=notify@example.invalid
ENVEOF
    export WORKLIST_SES_ENV="$BASE/ses.env"
    export WORKLIST_EMAIL_TRANSPORT="file:$BASE/mail"
}
mailcount() { ls "$BASE/mail" 2>/dev/null | wc -l; }
mailbody() { cat "$BASE/mail"/* 2>/dev/null; }
newest_mail() { ls -t "$BASE/mail" 2>/dev/null | head -n1; }
age_ledger() { # age_ledger <minutes> -- backdate every stamp in the email ledger
    # The suite's usual aging trick for a sidecar it cannot wait out. Rewriting
    # a fixture ledger is fine; the append-only discipline is the PRODUCT's, and
    # cases 159b/159e/159f exist precisely to prove the windows it keys on.
    python3 - "${WL%.md}.emails" "$1" <<'PYEOF'
import datetime, json, sys
p, mins = sys.argv[1], float(sys.argv[2])
old = (datetime.datetime.now(datetime.timezone.utc)
       - datetime.timedelta(minutes=mins)).strftime("%Y-%m-%dT%H:%M:%SZ")
rows = []
for line in open(p, encoding="utf-8"):
    line = line.strip()
    if line:
        o = json.loads(line)
        o["at"] = old
        rows.append(o)
open(p, "w", encoding="utf-8").write(
    "".join(json.dumps(r, separators=(",", ":")) + "\n" for r in rows))
PYEOF
}
setup
mail_fixture
brief_now
hand_now
RID=$(askid deadbeef operator 'which tier map? DEFAULT: ship the draft map')
say "answer

## Remaining
- the tier map question, now with the operator"
run >/dev/null
BODY="$(mailbody)"
if [[ "$(mailcount)" == "1" ]] && grep -qF "which tier map?" <<<"$BODY" &&
    grep -qF "$RID" <<<"$BODY" && grep -qF -- "--answer operator" <<<"$BODY"; then
    pass "159: one digest carries the question, its request id and the relay command"
else
    fail "159: count=$(mailcount) rid=$RID body=${BODY:0:400}"
fi
# CONTROL: same world, cooldown REMOVED, and still nothing goes out. Aging the
# ledger past the cooldown is what makes this a dedup proof rather than a
# restatement of the rate limit.
age_ledger 500
newturn
say "answer

## Remaining
- still waiting on the operator"
run >/dev/null
if [[ "$(mailcount)" == "1" ]]; then
    pass "159 CONTROL: an already-mailed question is never mailed twice (ledger dedup)"
else
    fail "159 CONTROL: a second digest went out for the same question ($(mailcount) files)"
fi

echo "== 159b. COOLDOWN: a new question waits out the window, then goes =="
age_ledger 0 # re-arm: the last send is "now" again
RID2=$(askid deadbeef operator 'ship the ceph leg? DEFAULT: hold it for the next wave')
newturn
say "answer

## Remaining
- two operator questions outstanding"
run >/dev/null
if [[ "$(mailcount)" == "1" ]]; then
    pass "159b: inside the cooldown a fresh question is delayed, not mailed"
else
    fail "159b: the cooldown did not hold ($(mailcount) files)"
fi
age_ledger 500
newturn
say "answer

## Remaining
- two operator questions outstanding"
run >/dev/null
BODY2="$(cat "$BASE/mail/$(newest_mail)")"
if [[ "$(mailcount)" == "2" ]] && grep -qF "$RID2" <<<"$BODY2" && ! grep -qF "$RID" <<<"$BODY2"; then
    pass "159b: past the cooldown the delayed question goes out, alone (nothing lost, nothing repeated)"
else
    fail "159b: count=$(mailcount) second digest=${BODY2:0:400}"
fi

echo "== 159c. ANSWER LOOP: --answer operator reaches the asker, --ack clears it =="
reqcli --answer operator "$RID" 'use tier map B, the draft undercounts seats' >/dev/null
newturn
say "answer

## Remaining
- act on the operator's tier map answer"
export WORKLIST_FOCUS=off
check "the operator's answer blocks its asker with the text in the reason" block \
    "use tier map B, the draft undercounts seats"
reqcli --ack deadbeef "$RID" >/dev/null
newturn
say "acted on it

## Remaining
- one operator question still open"
out="$(run)"
unset WORKLIST_FOCUS
if ! grep -qF "use tier map B" <<<"$out"; then
    pass "159c: --ack ends the delivery permanently"
else
    fail "159c: the acked answer still blocked: ${out:0:300}"
fi
# CONTROL: the self-answer guard is untouched by the operator recipient.
reqcli --answer deadbeef "$RID2" 'answering myself' >"$BASE/self.out" 2>&1
RC=$?
if [[ "$RC" -ne 0 ]] && grep -qF "your own request" "$BASE/self.out"; then
    pass "159c CONTROL: answering your own request is still refused"
else
    fail "159c CONTROL: self-answer rc=$RC out=$(head -c 200 "$BASE/self.out")"
fi

echo "== 159d. an operator request does NOT escalate into a duplicate [?] =="
# Without the exemption every emailed question would ALSO clone itself into a
# deferral carrying the same text and its own DEFAULT window: asked once,
# reported twice, defaulted twice.
setup
mail_fixture
brief_now
hand_now
OLDREQ=$(date -u -d '-300 minutes' +%Y-%m-%dT%H:%M:%SZ)
printf '{"ev":"ask","id":"aaaa1111","from":"deadbeef","to":"operator","at":"%s","body":"which tier map? DEFAULT: ship the draft"}\n' \
    "$OLDREQ" >>"${WL%.md}.requests"
say "answer

## Remaining
- the operator question"
run >/dev/null
if ! grep -q '"ev":"escalate"' "${WL%.md}.requests" &&
    ! grep -q 'aaaa1111' "${WL%.md}.events.jsonl" 2>/dev/null; then
    pass "159d: a 300-minute-old operator request is not cloned into a [?]"
else
    fail "159d: the operator request escalated: $(grep escalate "${WL%.md}.requests" | head -c 200)"
fi
# CONTROL: the dead-recipient rule itself still works for an ordinary session.
printf '{"ev":"ask","id":"bbbb2222","from":"deadbeef","to":"zzzzzzzz","at":"%s","body":"restart the leg? DEFAULT: restart it"}\n' \
    "$OLDREQ" >>"${WL%.md}.requests"
newturn
say "answer

## Remaining
- the operator question and the dead-recipient one"
run >/dev/null
if grep -q '"ev":"escalate"' "${WL%.md}.requests" && grep -q 'bbbb2222' "${WL%.md}.events.jsonl"; then
    pass "159d CONTROL: an ordinary request to a silent session still escalates"
else
    fail "159d CONTROL: dead-recipient escalation stopped working"
fi

echo "== 159e. DEFERRAL DIGEST: aged [?] items fold into one mail, once per generation =="
setup
mail_fixture
brief_now
hand_now
OLDD=$(date -u -d '-90 minutes' +%Y-%m-%dT%H:%M:%SZ)
printf '{"ev":"add","id":"eeee1111","at":"%s","by":"deadbeef","s":"?","o":"deadbeef","t":"flip the billing tier? DEFAULT: keep it WHY: only the operator owns revenue calls HOW: operator picks"}\n' \
    "$OLDD" >>"${WL%.md}.events.jsonl"
printf '{"ev":"add","id":"eeee2222","at":"%s","by":"deadbeef","s":"?","o":"deadbeef","t":"drop the asia region? DEFAULT: keep it WHY: only the operator owns the cost tradeoff HOW: operator decides"}\n' \
    "$OLDD" >>"${WL%.md}.events.jsonl"
say "answer

## Remaining
- two deferred decisions waiting on the operator"
run >/dev/null
BODY="$(mailbody)"
if [[ "$(mailcount)" == "1" ]] && grep -qF "eeee1111" <<<"$BODY" && grep -qF "eeee2222" <<<"$BODY" &&
    grep -qF "flip the billing tier?" <<<"$BODY"; then
    pass "159e: two aged deferrals fold into ONE digest listing both"
else
    fail "159e: count=$(mailcount) body=${BODY:0:400}"
fi
age_ledger 500
newturn
say "answer

## Remaining
- two deferred decisions waiting on the operator"
run >/dev/null
if [[ "$(mailcount)" == "1" ]]; then
    pass "159e: an untouched deferral is never re-mailed, cooldown or no cooldown"
else
    fail "159e: an untouched deferral was mailed again ($(mailcount) files)"
fi
# A re-deferral is a NEW generation, so it re-arms. Planted with an aged stamp
# because a `--defer` issued now is one minute old and correctly not yet due;
# the event below is exactly what that CLI writes, 80 minutes ago.
OLDD2=$(date -u -d '-80 minutes' +%Y-%m-%dT%H:%M:%SZ)
printf '{"ev":"state","id":"eeee1111","at":"%s","by":"deadbeef","s":"?","note":"re-deferred after the pricing call slipped"}\n' \
    "$OLDD2" >>"${WL%.md}.events.jsonl"
newturn
say "answer

## Remaining
- the re-deferred billing decision"
run >/dev/null
BODY2="$(cat "$BASE/mail/$(newest_mail)")"
if [[ "$(mailcount)" == "2" ]] && grep -qF "eeee1111" <<<"$BODY2" && ! grep -qF "eeee2222" <<<"$BODY2"; then
    pass "159e: a re-deferral re-arms that item alone, keyed by its update stamp"
else
    fail "159e: re-arm wrong: count=$(mailcount) body=${BODY2:0:400}"
fi

echo "== 159f. FAILURE: a broken transport is loud, changes no verdict, and retries =="
setup
mail_fixture
export WORKLIST_EMAIL_TRANSPORT="file:$BASE/no-such-mail-dir"
brief_now
hand_now
askid deadbeef operator 'rotate the SES key now? DEFAULT: rotate it next window' >/dev/null
say "answer

## Remaining
- the SES rotation question"
out="$(run)"
got="$(python3 -c 'import json,sys
raw=sys.stdin.read().strip()
print(json.loads(raw).get("decision","allow") if raw else "allow")' <<<"$out" 2>/dev/null)"
export WORKLIST_EMAIL=off
newturn
say "answer

## Remaining
- the SES rotation question"
out_off="$(run)"
got_off="$(python3 -c 'import json,sys
raw=sys.stdin.read().strip()
print(json.loads(raw).get("decision","allow") if raw else "allow")' <<<"$out_off" 2>/dev/null)"
unset WORKLIST_EMAIL
if grep -qF "OPERATOR EMAIL FAILED" <<<"$out" && [[ "$got" == "$got_off" ]] &&
    grep -q '"ev":"fail"' "${WL%.md}.emails" && ! grep -q '"ev":"sent"' "${WL%.md}.emails"; then
    pass "159f: a failed send is loud, records no false 'sent', and leaves the verdict at '$got_off'"
else
    fail "159f: got=$got got_off=$got_off out=${out:0:300}"
fi
# MAIL IS OPTIONAL (operator, 2026-07-31): after a failure with the current
# credentials the channel is SKIPPED with one warning, not retried loudly.
newturn
say "answer

## Remaining
- the SES rotation question"
out="$(run)"
if grep -qF "email channel is SKIPPED" <<<"$out" && ! grep -qF "OPERATOR EMAIL FAILED" <<<"$out"; then
    pass "159f: the second stop warns ONCE that the optional channel is skipped"
else
    fail "159f: skip warning wrong: ${out:0:300}"
fi
newturn
say "answer

## Remaining
- the SES rotation question"
out="$(run)"
if ! grep -qF "email channel is SKIPPED" <<<"$out" && ! grep -qF "OPERATOR EMAIL FAILED" <<<"$out"; then
    pass "159f: after the one warning the skipped channel is silent"
else
    fail "159f: the skip warning repeated: ${out:0:300}"
fi
# FRESH CREDENTIALS RE-ARM the channel by themselves: new key id, transport
# restored, the same question finally goes out. Nothing was lost.
age_ledger 60
cat >"$BASE/ses.env" <<'ENVEOF'
AWS_SES_ACCESS_KEY_ID=AKIAROTATEDFRESHKEY
AWS_SES_SECRET_ACCESS_KEY=secretrotatedfresh
AWS_SES_REGION=eu-central-1
AWS_SES_FROM=notify@example.invalid
ENVEOF
export WORKLIST_EMAIL_TRANSPORT="file:$BASE/mail"
newturn
say "answer

## Remaining
- the SES rotation question"
run >/dev/null
if [[ "$(mailcount)" == "1" ]] && grep -qF "rotate the SES key now?" "$(ls -d "$BASE/mail"/*)"; then
    pass "159f: fresh credentials re-arm the channel and the question is sent, nothing lost"
else
    fail "159f: re-arm did not resend ($(mailcount) files)"
fi

echo "== 159g. UNCONFIGURED: one note, no crash, no block; and --ask operator needs a DEFAULT =="
setup
export WORKLIST_SES_ENV="$BASE/there-is-no-env-file"
export WORKLIST_EMAIL_TRANSPORT="file:$BASE/mail"
mkdir -p "$BASE/mail"
brief_now
hand_now
askid deadbeef operator 'approve the pricing page? DEFAULT: leave it as drafted' >/dev/null
say "answer

## Remaining
- the pricing page question"
check "an unconfigured channel notes itself and never blocks" allow \
    "operator email channel is unconfigured"
newturn
say "answer

## Remaining
- the pricing page question"
out="$(run)"
if ! grep -qF "operator email channel is unconfigured" <<<"$out" && [[ "$(mailcount)" == "0" ]]; then
    pass "159g: the unconfigured note is latched to once per session, and nothing was sent"
else
    fail "159g: the note repeated or mail escaped: ${out:0:300}"
fi
reqcli --ask deadbeef operator 'just tell me what you think' >"$BASE/ask.out" 2>&1
RC=$?
if [[ "$RC" -ne 0 ]] && grep -qF "must carry a DEFAULT:" "$BASE/ask.out"; then
    pass "159g: an operator request with no DEFAULT: is refused at the door"
else
    fail "159g: DEFAULT-less operator ask rc=$RC out=$(head -c 200 "$BASE/ask.out")"
fi
unset WORKLIST_SES_ENV WORKLIST_EMAIL_TRANSPORT WORKLIST_EMAIL

echo "== 160. v14 gap 1: displays show basetext + LATEST note, never the whole history =="
# One live item reached ~20 concatenated notes and every block printed them
# all. brief_line/brief_text keep the full accumulation in the store (--list)
# and render base + newest only.
setup
brief_now
hand_now
GID=$(reqcli --add deadbeef "campaign base text for the brief test" | grep -oE '#[0-9a-f]+' | tr -d '#')
JW="WHY: only the operator can pick between the two tier maps because both are defensible and the code decides nothing HOW: the operator answers on their next pass"
reqcli --defer deadbeef "$GID" "first old note DEFAULT: alpha $JW" >/dev/null
reqcli --defer deadbeef "$GID" "second old note DEFAULT: beta $JW" >/dev/null
reqcli --defer deadbeef "$GID" "newest note wins DEFAULT: gamma $JW" >/dev/null
say "answer

## Remaining
- the deferred campaign item"
export WORKLIST_FOCUS=off
out="$(run)"
unset WORKLIST_FOCUS
if grep -qF "campaign base text for the brief test" <<<"$out" &&
    grep -qF "newest note wins" <<<"$out" &&
    ! grep -qF "first old note" <<<"$out" &&
    ! grep -qF "second old note" <<<"$out"; then
    pass "160: the stop shows base + LATEST and drops the middle history"
else
    fail "160: brief rendering wrong: ${out:0:400}"
fi
FULL="$(reqcli --list)"
if grep -qF "first old note" <<<"$FULL" && grep -qF "second old note" <<<"$FULL"; then
    pass "160 CONTROL: --list still carries the full accumulated history"
else
    fail "160 CONTROL: the store lost history: ${FULL:0:300}"
fi

echo "== 160b. v14 gap 2: own worklist activity resets the stuck counter =="
# A session ticking/leasing/updating items hourly is MOVING even when its
# long-horizon harness tasks never flip; only a session doing neither counts.
# STUCK_ROUNDS=2 so tasks+head fires at 2 unchanged stops (1 would fire on
# every stop by construction: a fresh signature starts its count at 1).
setup
brief_now
hand_now
export WORKLIST_STUCK_ROUNDS=2
task 7 pending "long-horizon watch"
FIRED=0
for i in 1 2 3 4; do
    newturn
    say "answer

## Remaining
- #7 long-horizon watch (pending)"
    OUT="$(run)"
    grep -qF "CONSECUTIVE STOPS" <<<"$OUT" && FIRED=1
    AID=$(reqcli --add deadbeef "movement item $i" | grep -oE '#[0-9a-f]+' | tr -d '#')
    reqcli --tick deadbeef "$AID" "done, exit 0" >/dev/null
done
if [[ "$FIRED" == 0 ]]; then
    pass "160b: worklist activity between stops keeps the stuck detector quiet"
else
    fail "160b: an active session still read as stuck: ${OUT:0:250}"
fi
# CONTROL: the identical shape WITHOUT worklist activity fires.
setup
brief_now
hand_now
task 7 pending "long-horizon watch"
FIRED=0
for i in 1 2 3 4; do
    newturn
    say "answer

## Remaining
- #7 long-horizon watch (pending)"
    OUT="$(run)"
    grep -qF "CONSECUTIVE STOPS" <<<"$OUT" && FIRED=1
done
unset WORKLIST_STUCK_ROUNDS
if [[ "$FIRED" == 1 ]]; then
    pass "160b CONTROL: with no activity the detector still fires"
else
    fail "160b CONTROL: the stuck detector never fired: ${OUT:0:250}"
fi

echo "== 160c. v14 gap 3: --lease warns when the worker id is not a running task =="
setup
brief_now
hand_now
CID=$(reqcli --add deadbeef "leased thing" | grep -oE '#[0-9a-f]+' | tr -d '#')
printf '{"background_tasks":[{"id":"bw1","type":"shell","status":"running","description":"real watch"}]}\n' \
    >"${WL%.md}.lastevent-deadbeef.json"
OUT="$(reqcli --lease deadbeef "$CID" +30 worker:my-agent-name "watching" 2>&1)"
if grep -qF "WARNING: worker:my-agent-name is not among" <<<"$OUT" && grep -qF "bw1" <<<"$OUT"; then
    pass "160c: a name-not-id lease is warned about, naming the real ids"
else
    fail "160c: no warning for an unverifiable worker: ${OUT:0:250}"
fi
OUT="$(reqcli --lease deadbeef "$CID" +30 worker:bw1 "watching" 2>&1)"
if grep -qF "worker verified against the harness" <<<"$OUT" && ! grep -qF "WARNING" <<<"$OUT"; then
    pass "160c CONTROL: a real task id is verified, no warning"
else
    fail "160c CONTROL: verification suffix missing: ${OUT:0:250}"
fi

echo "== 160d. v14 gap 4: an expired lease with an OS-verified-alive worker stays in-flight =="
setup
brief_now
hand_now
FRESH=$(date -u +%Y-%m-%dT%H:%M:%SZ)
PAST=$(date -u -d '-5 minutes' +%Y-%m-%dT%H:%MZ)
printf '{"ev":"add","id":"dddd0001","at":"%s","by":"deadbeef","s":" ","o":"deadbeef","t":"long CI watch"}\n{"ev":"lease","id":"dddd0001","at":"%s","by":"deadbeef","until":"%s","worker":"bw1"}\n' \
    "$FRESH" "$FRESH" "$PAST" >>"${WL%.md}.events.jsonl"
BG='[{"id":"bw1","type":"shell","status":"running","description":"the long CI watch"}]'
say "answer

## Remaining
- the long CI watch, in flight on bw1"
export WORKLIST_FOCUS=off
OUT="$(run)"
unset WORKLIST_FOCUS
if ! grep -qF "lease expired; finish it" <<<"$OUT" && ! grep -qF "OPEN worklist item" <<<"$OUT"; then
    pass "160d: the verified-alive worker keeps the expired lease in flight"
else
    fail "160d: a supervised long job still failed closed: ${OUT:0:300}"
fi
# CONTROL: the same expired lease with the worker GONE fails closed as before.
BG='[]'
newturn
say "answer

## Remaining
- the long CI watch, in flight on bw1"
export WORKLIST_FOCUS=off
OUT="$(run)"
unset WORKLIST_FOCUS
BG=''
if grep -qF "lease expired; finish it" <<<"$OUT"; then
    pass "160d CONTROL: a gone worker still fails the expired lease closed"
else
    fail "160d CONTROL: the expired lease was tolerated without a live worker: ${OUT:0:300}"
fi

echo "== 160e. v14 gap 5: own bookkeeping does not stale STATE.md; structure does =="
setup
brief_now
# The lease vehicle exists and is ALREADY [>] before the document is written,
# so the later renewal changes no structure (state stays '>', only until/upd
# move), which is exactly the bookkeeping-only shape this gap is about.
FID=$(reqcli --add deadbeef "lease vehicle" | grep -oE '#[0-9a-f]+' | tr -d '#')
reqcli --lease deadbeef "$FID" +60 worker:bw9 "watching the long job" >/dev/null
BG='[{"id":"bw9","type":"shell","status":"running","description":"the long job"}]'
hand_now
task 7 pending "thing"
say "answer

## Remaining
- #7 thing (pending)"
run >/dev/null
age_state deadbeef 20
reqcli --lease deadbeef "$FID" +90 worker:bw9 "renewing the watch lease" >/dev/null
newturn
say "answer

## Remaining
- #7 thing (pending)"
OUT="$(run)"
if ! grep -qF "STATE.md is stale" <<<"$OUT"; then
    pass "160e: an aged STATE.md survives a same-session lease renewal"
else
    fail "160e: own bookkeeping staled the document: ${OUT:0:300}"
fi
# CONTROL: a STRUCTURAL move (new open item) stales the aged document.
reqcli --add deadbeef "genuinely new work" >/dev/null
newturn
say "answer

## Remaining
- #7 thing (pending)"
export WORKLIST_FOCUS=off
OUT="$(run)"
unset WORKLIST_FOCUS
if grep -qF "STATE.md is stale" <<<"$OUT"; then
    pass "160e CONTROL: a structural move stales the aged document"
else
    fail "160e CONTROL: structure moved and staleness never fired: ${OUT:0:300}"
fi

echo "== 160f. v14 gap 6: an unchanged world accepts the banked Remaining report =="
setup
brief_now
hand_now
task 7 pending "thing"
say "answer

## Remaining
- #7 thing (pending)"
run >/dev/null
newturn
say "bookkeeping-only turn, nothing moved since the last report"
OUT="$(run)"
if ! grep -qF "no '## Remaining' section" <<<"$OUT"; then
    pass "160f: the banked report stands on an unchanged world"
else
    fail "160f: an unchanged world still demanded a restatement: ${OUT:0:300}"
fi
# CONTROL: the world moves (new open item) and the demand returns.
reqcli --add deadbeef "new work invalidates the bank" >/dev/null
newturn
say "another turn without a remaining section"
export WORKLIST_FOCUS=off
OUT="$(run)"
unset WORKLIST_FOCUS
if grep -qF "no '## Remaining' section" <<<"$OUT"; then
    pass "160f CONTROL: a moved world demands a fresh report"
else
    fail "160f CONTROL: the bank outlived the world it described: ${OUT:0:300}"
fi

echo "== 161. an OPEN operator request suppresses the stuck exempt-overrun =="
# Terminal-hold shape: all work done, the one question posted to the operator
# with DEFAULT: hold, long-lived teammate tasks keeping live_bg nonempty. The
# ball is verifiably out of this session's court, so the overrun must not
# nag it into fake motion; the suppression lifts when the request resolves.
setup
brief_now
hand_now
export WORKLIST_STUCK_ROUNDS=1
task 7 pending "operator-gated decision"
reqcli --ask deadbeef operator "merge the green PR? DEFAULT: hold and do not merge" >/dev/null
BG='[{"id":"tz1","type":"teammate","status":"running","description":"long-lived teammate"}]'
FIRED=0
for i in 1 2 3 4 5 6; do
    newturn
    say "answer

## Remaining
- #7 operator-gated decision (pending)"
    OUT="$(run)"
    grep -qF "CONSECUTIVE STOPS" <<<"$OUT" && FIRED=1
done
if [[ "$FIRED" == 0 ]]; then
    pass "161: waiting on an open operator question is not stuck"
else
    fail "161: the hold state was nagged as stuck: ${OUT:0:250}"
fi
# CONTROL: the same shape WITHOUT the operator request still overruns.
setup
brief_now
hand_now
task 7 pending "operator-gated decision"
BG='[{"id":"tz1","type":"teammate","status":"running","description":"long-lived teammate"}]'
FIRED=0
for i in 1 2 3 4 5 6; do
    newturn
    say "answer

## Remaining
- #7 operator-gated decision (pending)"
    OUT="$(run)"
    grep -qF "CONSECUTIVE STOPS" <<<"$OUT" && FIRED=1
done
unset WORKLIST_STUCK_ROUNDS
BG='[]'
if [[ "$FIRED" == 1 ]]; then
    pass "161 CONTROL: without the request the exempt-overrun still fires"
else
    fail "161 CONTROL: the overrun never fired: ${OUT:0:250}"
fi

echo "== 163. v15: pure background wait gets a 15-min check-in, not make-work =="
# The state: live background jobs, no open items, no expired deferral. The
# hook recognizes it as legitimate and demands only a bounded check-in whose
# worker facts it gathered itself from the output streams.
setup
brief_now
hand_now
mkdir -p "$BASE/bgout"
export WORKLIST_BG_OUTPUT_DIR="$BASE/bgout"
printf 'worker stream content\n' >"$BASE/bgout/bw1.output"
BG='[{"id":"bw1","type":"shell","status":"running","description":"long CI watch"}]'
# v19: an UNBLOCKED pending task now (correctly) makes the wait impure, so this
# case's parked task is in_progress -- the state a watched-by-this-session job
# actually has. The unblocked-pending behavior gets its own case 163y below.
task 7 in_progress "waiting on the nightly"
say "answer

## Remaining
- #7 waiting on the nightly (in_progress)"
# Stop 1 SEEDS the wait clock silently: the check-in means "you have been
# waiting 15 minutes", never "you started waiting".
OUT="$(run)"
if ! grep -qF "PURE BACKGROUND WAIT" <<<"$OUT"; then
    pass "163 seed: first sight of the wait state does not fire"
else
    fail "163 seed: fired on first sight: ${OUT:0:250}"
fi
python3 - "$WL" <<'PYEOF'
import json, pathlib, sys
p = pathlib.Path(sys.argv[1].replace(".md", ".state-deadbeef.json"))
doc = json.loads(p.read_text())
doc["bgwait"] = {"at": "2026-01-01T00:00:00Z"}
p.write_text(json.dumps(doc))
PYEOF
newturn
say "answer

## Remaining
- #7 waiting on the nightly (in_progress)"
OUT="$(run)"
if grep -qF "PURE BACKGROUND WAIT" <<<"$OUT" && grep -qF "bw1 (long CI watch)" <<<"$OUT" &&
    grep -qF "output last grew" <<<"$OUT"; then
    pass "163: after 15 waited minutes the check-in fires with the hook's own stream facts"
else
    fail "163: check-in wrong: ${OUT:0:300}"
fi
# CONTROL: inside the window it does not repeat (latched on fire).
newturn
say "bw1 confirmed: the long CI watch stream matches; nothing stuck.

## Remaining
- #7 waiting on the nightly (in_progress)"
OUT="$(run)"
if ! grep -qF "PURE BACKGROUND WAIT" <<<"$OUT"; then
    pass "163 CONTROL: no second check-in inside the 15-minute window"
else
    fail "163 CONTROL: the check-in drumbeat: ${OUT:0:250}"
fi

echo "== 163y. v19: an unblocked pending task makes the wait IMPURE and gets named =="
# Operator, 2026-08-08: a session idled for hours in "pure background wait"
# beside a fully planned, unblocked pending task; the check-in kept certifying
# the wait because it never consulted the harness queue. Now: pending with no
# unresolved blocker -> the check-in fires as WORKABLE-TASKS and names it;
# pending with a live blocker -> the wait stays pure (the control).
setup
brief_now
hand_now
mkdir -p "$BASE/bgout"
export WORKLIST_BG_OUTPUT_DIR="$BASE/bgout"
printf 'worker stream content\n' >"$BASE/bgout/bw1.output"
BG='[{"id":"bw1","type":"shell","status":"running","description":"long CI watch"}]'
task 7 pending "fully planned and unblocked"
say "answer

## Remaining
- #7 fully planned and unblocked (pending)"
OUT="$(run)" # seed the clock
python3 - "$WL" <<'PYEOF'
import json, pathlib, sys
p = pathlib.Path(sys.argv[1].replace(".md", ".state-deadbeef.json"))
doc = json.loads(p.read_text())
doc["bgwait"] = {"at": "2026-01-01T00:00:00Z"}
p.write_text(json.dumps(doc))
PYEOF
newturn
say "answer

## Remaining
- #7 fully planned and unblocked (pending)"
OUT="$(run)"
if grep -qF "WORKABLE TASKS" <<<"$OUT" && grep -qF "task #7 fully planned and unblocked" <<<"$OUT" &&
    ! grep -qF "not a demand for other work" <<<"$OUT"; then
    pass "163y: the check-in names the unblocked pending task instead of certifying the wait"
else
    fail "163y: workable task not named: ${OUT:0:300}"
fi
# CONTROL: the same task behind a LIVE blocker keeps the wait pure.
setup
brief_now
hand_now
mkdir -p "$BASE/bgout"
export WORKLIST_BG_OUTPUT_DIR="$BASE/bgout"
printf 'worker stream content\n' >"$BASE/bgout/bw1.output"
BG='[{"id":"bw1","type":"shell","status":"running","description":"long CI watch"}]'
task 6 pending "the prerequisite"
task 7 pending "parked behind 6" 6
say "answer

## Remaining
- #6 the prerequisite (pending)
- #7 parked behind 6 (pending)"
OUT="$(run)" # seed
python3 - "$WL" <<'PYEOF'
import json, pathlib, sys
p = pathlib.Path(sys.argv[1].replace(".md", ".state-deadbeef.json"))
doc = json.loads(p.read_text())
doc["bgwait"] = {"at": "2026-01-01T00:00:00Z"}
p.write_text(json.dumps(doc))
PYEOF
newturn
say "answer

## Remaining
- #6 the prerequisite (pending)
- #7 parked behind 6 (pending)"
OUT="$(run)"
if grep -qF "WORKABLE TASKS" <<<"$OUT" && grep -qF "task #6 the prerequisite" <<<"$OUT" &&
    ! grep -qF "task #7 parked behind 6" <<<"$OUT"; then
    pass "163y CONTROL: the blocked task stays unnamed; its live blocker is the one named"
else
    fail "163y CONTROL: blocker logic wrong: ${OUT:0:300}"
fi

echo "== 163x. v19: the transcript join finds a renamed task store; ambiguity refuses =="
# Review finding on #559: the fallback in _resolve_tasks_dir had no committed
# coverage (the original proof ran as ephemeral scratchpad python). This case
# drives it through the REAL hook: the primary session-deadbeef dir is EMPTY
# (setup creates it bare), the actual tasks live under a differently-named
# session-* dir, and the only join evidence is a TaskCreate result line in the
# transcript tail. The workable-tasks check-in naming the task proves the
# whole chain: resolve -> actionable -> fire.
setup
brief_now
hand_now
mkdir -p "$BASE/bgout"
export WORKLIST_BG_OUTPUT_DIR="$BASE/bgout"
printf 'worker stream content\n' >"$BASE/bgout/bw1.output"
BG='[{"id":"bw1","type":"shell","status":"running","description":"long CI watch"}]'
mkdir -p "$BASE/tasks/session-teamzzzz"
printf '{"id":"21","status":"pending","subject":"the mismatch fixture task","blockedBy":[]}\n' \
    >"$BASE/tasks/session-teamzzzz/21.json"
say "Task #21 created successfully: the mismatch fixture task"
say "answer

## Remaining
- #21 the mismatch fixture task (pending)"
OUT="$(run)" # seed the wait clock
python3 - "$WL" <<'PYEOF'
import json, pathlib, sys
p = pathlib.Path(sys.argv[1].replace(".md", ".state-deadbeef.json"))
doc = json.loads(p.read_text())
doc["bgwait"] = {"at": "2026-01-01T00:00:00Z"}
p.write_text(json.dumps(doc))
PYEOF
newturn
say "answer

## Remaining
- #21 the mismatch fixture task (pending)"
OUT="$(run)"
if grep -qF "WORKABLE TASKS" <<<"$OUT" && grep -qF "task #21 the mismatch fixture task" <<<"$OUT"; then
    pass "163x: the join resolved the renamed store off the transcript and named its task"
else
    fail "163x: fallback resolution failed: ${OUT:0:300}"
fi
# CONTROL: TWO dirs matching the same TaskCreate line -> the join refuses, no
# task is named, the wait stays pure. Fresh setup so the durable resolution
# cache from the fire case cannot leak in.
setup
brief_now
hand_now
mkdir -p "$BASE/bgout"
export WORKLIST_BG_OUTPUT_DIR="$BASE/bgout"
printf 'worker stream content\n' >"$BASE/bgout/bw1.output"
BG='[{"id":"bw1","type":"shell","status":"running","description":"long CI watch"}]'
for d in teamzzzz teamyyyy; do
    mkdir -p "$BASE/tasks/session-$d"
    printf '{"id":"21","status":"pending","subject":"the mismatch fixture task","blockedBy":[]}\n' \
        >"$BASE/tasks/session-$d/21.json"
done
say "Task #21 created successfully: the mismatch fixture task"
say "answer

## Remaining
(nothing tracked here)"
OUT="$(run)" # seed
python3 - "$WL" <<'PYEOF'
import json, pathlib, sys
p = pathlib.Path(sys.argv[1].replace(".md", ".state-deadbeef.json"))
doc = json.loads(p.read_text())
doc["bgwait"] = {"at": "2026-01-01T00:00:00Z"}
p.write_text(json.dumps(doc))
PYEOF
newturn
say "answer

## Remaining
(nothing tracked here)"
OUT="$(run)"
if grep -qF "PURE BACKGROUND WAIT" <<<"$OUT" && ! grep -qF "task #21" <<<"$OUT"; then
    pass "163x CONTROL: two candidate dirs refuse the join; no manufactured task, wait stays pure"
else
    fail "163x CONTROL: ambiguity did not refuse: ${OUT:0:300}"
fi

echo "== 163z. v18: a CONFIRMED inbox waiter owes no check-in and needs no poll cron =="
# The waiter blocks until something new arrives for this session and then EXITS,
# and its exit is the harness notification that wakes the session. Its liveness
# IS its report, so the two supervision demands that exist to make a session
# account for a silent background job do not apply to it. Both relaxations are
# keyed on `confirmed` and on nothing weaker.
#
# A REAL wl_wait.py process, not a fake command string: `confirmed` means the OS
# can see a live descendant carrying the command, so a fixture that only claims
# the command would prove the string match and not the verdict.
setup
brief_now
hand_now
mkdir -p "$BASE/bgout"
export WORKLIST_BG_OUTPUT_DIR="$BASE/bgout"
WAITER_CMD="python3 $(dirname "$HOOK")/wl_wait.py deadbeef --timeout 3"
TMPDIR="$BASE/waittmp" CLAUDE_PROJECT_DIR="$BASE" $WAITER_CMD >/dev/null 2>&1 &
WAITER_PID=$!
export WORKLIST_HARNESS_PID=$$
sleep 1
BG="$(
    python3 - "$WAITER_CMD" <<'PYEOF'
import json, sys
print(json.dumps([{"id": "wt1", "type": "shell", "status": "running",
                   "command": sys.argv[1], "description": "inbox waiter"}]))
PYEOF
)"
# Premise, asserted rather than assumed: if the verdict is not `confirmed` this
# whole case is vacuous and would "pass" for the wrong reason.
VERDICT=$(
    cd "$BASE" && python3 - "$(dirname "$HOOK")" "$WAITER_CMD" <<'PYEOF'
import os, sys
sys.path.insert(0, sys.argv[1])
import wl_liveness as L
bg = [{"id": "wt1", "type": "shell", "status": "running", "command": sys.argv[2]}]
print(L.verify_background(bg, ancestors={int(os.environ["WORKLIST_HARNESS_PID"])}).get("wt1"))
PYEOF
)
if [[ "$VERDICT" == "confirmed" ]]; then
    pass "163z premise: the live waiter verifies as confirmed"
else
    fail "163z premise: waiter verdict is '$VERDICT', not confirmed -- this case is vacuous"
fi
CRONS='[{"id":"c1","schedule":"*/30 * * * *","prompt":"work loop"}]'
task 7 in_progress "waiting on the inbox"
say "answer

## Remaining
- #7 waiting on the inbox (in_progress)"
run >/dev/null
python3 - "$WL" <<'PYEOF'
import json, pathlib, sys
p = pathlib.Path(sys.argv[1].replace(".md", ".state-deadbeef.json"))
doc = json.loads(p.read_text())
doc["bgwait"] = {"at": "2026-01-01T00:00:00Z"}  # 15 minutes overdue
p.write_text(json.dumps(doc))
PYEOF
newturn
say "answer

## Remaining
- #7 waiting on the inbox (in_progress)"
OUT="$(run)"
if ! grep -qF "PURE BACKGROUND WAIT" <<<"$OUT"; then
    pass "163z: an overdue check-in is SUPPRESSED when the only live task is a confirmed waiter"
else
    fail "163z: the check-in fired at a waiter: ${OUT:0:250}"
fi
# The needle is lifted VERBATIM from V_NO_POLL_CRON. The first draft of this
# line grepped for "no inbox poll" and "poll cron", neither of which appears in
# that message at all -- so the assertion could never fail and passed for a
# reason unrelated to the waiter.
if ! grep -qF "NOTHING LISTENING FOR CROSS-SESSION MAIL" <<<"$OUT"; then
    pass "163z: a work cron with NO poll cron is accepted beside a confirmed waiter"
else
    fail "163z: no-poll fired despite the waiter: ${OUT:0:250}"
fi
kill "$WAITER_PID" 2>/dev/null
wait "$WAITER_PID" 2>/dev/null

echo "== 163v. a roster the session cannot verify is reaped, but only where certain =="
# THE BUG: after a compaction, or an operator reopening the session, the harness
# still reports every teammate ever spawned as `running`. Measured live: 20
# claimed, exactly 1 transcript still growing. That roster drives _in_pure_wait,
# the 15-minute check-in and confirmed_waiters, so a stale one means a session is
# told it supervises twenty workers forever and confirms phantoms every quarter
# hour.
#
# There is NO JOIN from a task id to an agent -- a task carries only {id, type,
# status, description}, the description is the prompt truncated to ~50 chars, and
# that prefix is provably not unique (10 of 19 collided on a live roster). So the
# automatic reap fires only where it is a CERTAINTY: not one teammate transcript
# fresh means every teammate task is dead, whatever its id.
setup
brief_now
hand_now
# A projects store with a teammate transcript that is STALE (hours old).
python3 - "$BASE" "$SID" <<'MKSTORE'
import json, os, pathlib, re, sys, time
B = pathlib.Path(sys.argv[1])
SID = sys.argv[2]
root = B / "claude" / "projects" / re.sub(r"[^A-Za-z0-9]", "-", str(B / "proj"))
def mate(sess, name, age_min):
    d = root / sess / "subagents"
    d.mkdir(parents=True, exist_ok=True)
    aid = "a%s-1111222233334444" % name
    (d / ("agent-%s.meta.json" % aid)).write_text(json.dumps(
        {"agentType": name, "name": name, "taskKind": "in_process_teammate"}))
    j = d / ("agent-%s.jsonl" % aid)
    j.write_text(json.dumps({"type": "assistant", "message": {"content": []}}) + "\n")
    old = time.time() - age_min * 60
    os.utime(j, (old, old))
# THIS session's own teammate, stale by hours: the roster is genuinely dead.
# The directory is named for the SESSION ID, which is the real convention --
# it used to be a literal "s1", which meant the scoped lookup could not resolve
# and the case was really exercising the unscoped glob.
mate(SID, "oldmate", 600)
# A DIFFERENT session in the same project, with a FRESH teammate. This is the
# cross-session contamination the review found: unscoped, this one transcript
# made fresh > 0 for EVERY session in the project, so a session whose own roster
# was 100% phantom was told it still had live workers and the auto-reap never
# fired. Concurrent sessions in one tree are routine here, so this was the
# common case rather than an edge one.
mate("bystander-9999-8888-7777-666666666666", "freshmate", 0)
MKSTORE
export CLAUDE_CONFIG_DIR="$BASE/claude"
BG='[{"id":"tm1","type":"teammate","status":"running","description":"You are an Opus writer sub-agent in /home..."},{"id":"tm2","type":"teammate","status":"running","description":"You are an Opus writer sub-agent in /home..."}]'
task 7 in_progress "waiting on the teammates"
say "answer

## Remaining
- #7 waiting on the teammates (in_progress)"
run >/dev/null # establishes the state doc
# THE CLOCK MUST BE OVERDUE BEFORE THIS PROVES ANYTHING. Asserting on a seeding
# stop is vacuous: the check-in does not fire on first sight of the wait state
# whether or not the roster was pruned, so the assertion passed with the pruning
# removed entirely (mutation Mk). With the clock overdue the two cases diverge:
# pruned -> the roster is empty, so it is not a pure wait and nothing is owed;
# unpruned -> the check-in fires for two phantoms.
python3 - "$WL" <<'SEED0'
import json, pathlib, sys
p = pathlib.Path(sys.argv[1].replace(".md", ".state-deadbeef.json"))
d = json.loads(p.read_text()) if p.exists() else {}
d["bgwait"] = {"at": "2026-01-01T00:00:00Z"}
p.write_text(json.dumps(d))
SEED0
newturn
say "answer

## Remaining
- #7 waiting on the teammates (in_progress)"
OUT="$(run)"
if ! grep -qF "PURE BACKGROUND WAIT" <<<"$OUT"; then
    pass "163v: with zero fresh transcripts the phantom roster is dropped"
else
    fail "163v: still supervising phantoms: ${OUT:0:250}"
fi
# CONTROL: make one transcript FRESH and the same roster is kept -- the drop is
# the certainty branch, not a blanket "teammates never count".
python3 -c '
import glob, os, sys, time
# THIS SESSIONS OWN transcript, not glob()[0]. With a bystander session in the
# fixture, [0] could pick the other sessions file -- which is already fresh --
# leaving this sessions mate stale, so the control would silently assert the
# opposite of what it means.
hits = glob.glob(sys.argv[1] + "/claude/projects/*/" + sys.argv[2] + "/subagents/*.jsonl")
assert hits, "control fixture missing: no transcript for this session"
os.utime(hits[0], (time.time(), time.time()))' "$BASE" "$SID"
python3 - "$WL" <<'SEED'
import json, pathlib, sys
p = pathlib.Path(sys.argv[1].replace(".md", ".state-deadbeef.json"))
d = json.loads(p.read_text()) if p.exists() else {}
d["bgwait"] = {"at": "2026-01-01T00:00:00Z"}
p.write_text(json.dumps(d))
SEED
newturn
say "answer

## Remaining
- #7 waiting on the teammates (in_progress)"
OUT="$(run)"
if grep -qF "PURE BACKGROUND WAIT" <<<"$OUT"; then
    pass "163v CONTROL: one fresh transcript keeps the roster and the check-in"
else
    fail "163v CONTROL: a live teammate was reaped: ${OUT:0:250}"
fi
# ...and because 2 are claimed while only 1 is fresh, the overclaim is REPORTED
# rather than guessed at.
if grep -qF "ROSTER OVERCLAIMS" <<<"$OUT"; then
    pass "163v: the unresolvable remainder is surfaced, not silently kept"
else
    fail "163v: the overclaim was hidden: ${OUT:0:300}"
fi
unset CLAUDE_CONFIG_DIR

echo "== 163v-c1. --reap retires an id, and refuses one the hook never saw =="
setup
brief_now
hand_now
BG='[{"id":"tm1","type":"teammate","status":"running","description":"a teammate"}]'
task 7 pending "waiting"
say "answer

## Remaining
- #7 waiting (pending)"
run >/dev/null # banks the lastevent the CLI validates against
if reqcli --reap deadbeef nosuchid >/dev/null 2>"$BASE/reap.err"; then
    fail "163v-c1: an unknown task id was accepted"
else
    if grep -qF "not in the last background-task list" "$BASE/reap.err"; then
        pass "163v-c1: an id the hook never saw is REFUSED, not recorded"
    else
        fail "163v-c1: refusal was unclear: $(head -c 120 "$BASE/reap.err")"
    fi
fi
if [ ! -f "${WL%.md}.reaped-deadbeef" ]; then
    pass "163v-c1: the refused reap wrote nothing"
else
    fail "163v-c1: a rejected reap still recorded an id"
fi
# CONTROL: a REAL id from that same roster is accepted and takes effect.
OUT="$(reqcli --reap deadbeef tm1 2>&1)"
assert_c1=$?
if grep -qF "reaped 1 task" <<<"$OUT"; then
    pass "163v-c1 CONTROL: a known id is accepted"
else
    fail "163v-c1 CONTROL: a valid reap was refused: ${OUT:0:150}"
fi
newturn
say "answer

## Remaining
- #7 waiting (pending)"
OUT="$(run)"
if ! grep -qF "PURE BACKGROUND WAIT" <<<"$OUT"; then
    pass "163v-c1: the reaped task no longer counts as running"
else
    fail "163v-c1: the reap had no effect: ${OUT:0:200}"
fi

echo "== 163w. v18: a session that IGNORES the waiter nudges is blocked =="
# The operator asked to "force contexts to run in background". The trigger is
# deliberately NOT "no confirmed waiter right now": a waiter EXITS every time it
# fires, so that condition is true in exactly the window the session is supposed
# to be in, and keying on it blocked correct behaviour and broke 16 cases here.
# It keys on the count of PostToolUse nudges the session has been given and not
# acted on, which only grows over half an hour of being asked.
setup
brief_now
hand_now
brief_other peer1234
CRONS='[{"id":"c1","schedule":"*/30 * * * *","prompt":"work loop"},{"id":"p","schedule":"*/5 * * * *"}]'
say "answer"
# Below the grace threshold: asked twice, not yet blocked.
printf '2 2026-01-01T00:00:00Z\n' >"${WL%.md}.waiternudge-deadbeef"
OUT="$(run)"
if ! grep -qF "AND IS NOT LISTENING" <<<"$OUT"; then
    pass "163w: under the grace count the session is not blocked yet"
else
    fail "163w: blocked too early: ${OUT:0:200}"
fi
# At the threshold: three unheeded nudges is half an hour of being asked.
printf '3 2026-01-01T00:00:00Z\n' >"${WL%.md}.waiternudge-deadbeef"
OUT="$(run)"
if grep -qF "AND IS NOT LISTENING" <<<"$OUT" && grep -qF "wl_wait.py" <<<"$OUT"; then
    pass "163w: three ignored nudges blocks, and the block carries the command"
else
    fail "163w: did not block at the threshold: ${OUT:0:250}"
fi

echo "== 163w-c1. CONTROL: a CONFIRMED waiter silences it =="
# Same ignored count, same peer, same loop -- only a live waiter differs.
setup
brief_now
hand_now
brief_other peer1234
mkdir -p "$BASE/bgout"
export WORKLIST_BG_OUTPUT_DIR="$BASE/bgout"
WAITER_CMD="python3 $(dirname "$HOOK")/wl_wait.py deadbeef --timeout 3"
TMPDIR="$BASE/wt1" CLAUDE_PROJECT_DIR="$BASE" $WAITER_CMD >/dev/null 2>&1 &
W163W=$!
export WORKLIST_HARNESS_PID=$$
sleep 1
BG="$(
    python3 - "$WAITER_CMD" <<'PYEOF'
import json, sys
print(json.dumps([{"id": "wt1", "type": "shell", "status": "running",
                   "command": sys.argv[1], "description": "inbox waiter"}]))
PYEOF
)"
CRONS='[{"id":"c1","schedule":"*/30 * * * *","prompt":"work loop"},{"id":"p","schedule":"*/5 * * * *"}]'
printf '9 2026-01-01T00:00:00Z\n' >"${WL%.md}.waiternudge-deadbeef"
say "answer"
OUT="$(run)"
if ! grep -qF "AND IS NOT LISTENING" <<<"$OUT"; then
    pass "163w-c1 CONTROL: a confirmed waiter silences it even at nine ignored nudges"
else
    fail "163w-c1 CONTROL: blocked despite a live waiter: ${OUT:0:250}"
fi
kill "$W163W" 2>/dev/null
wait "$W163W" 2>/dev/null

echo "== 163w-c2. CONTROL: an UNVERIFIABLE waiter does NOT satisfy it =="
# The case that could silently pass for the wrong reason. Same command string,
# dead process, so the verdict is `suspect` rather than `confirmed`. A waiter
# nobody can see on the OS is worth nothing: the whole argument is that its EXIT
# wakes you.
setup
brief_now
hand_now
brief_other peer1234
mkdir -p "$BASE/bgout"
export WORKLIST_BG_OUTPUT_DIR="$BASE/bgout"
export WORKLIST_HARNESS_PID=$$
BG="$(
    python3 - "$WAITER_CMD" <<'PYEOF'
import json, sys
print(json.dumps([{"id": "wt1", "type": "shell", "status": "running",
                   "command": sys.argv[1], "description": "inbox waiter (dead)"}]))
PYEOF
)"
CRONS='[{"id":"c1","schedule":"*/30 * * * *","prompt":"work loop"},{"id":"p","schedule":"*/5 * * * *"}]'
printf '3 2026-01-01T00:00:00Z\n' >"${WL%.md}.waiternudge-deadbeef"
say "answer"
OUT="$(run)"
if grep -qF "AND IS NOT LISTENING" <<<"$OUT"; then
    pass "163w-c2 CONTROL: a dead (unverifiable) waiter still blocks"
else
    fail "163w-c2 CONTROL: an unseeable waiter satisfied the check: ${OUT:0:250}"
fi
unset WORKLIST_HARNESS_PID

echo "== 163w-c3. CONTROL: no live peer, no block =="
# The harm of not listening is TO SOMEBODY. With no peer there is nobody whose
# request could go unseen, so the check has no victim and must stay silent --
# this is the condition that makes blocking safe at all.
setup
brief_now
hand_now
CRONS='[{"id":"c1","schedule":"*/30 * * * *","prompt":"work loop"},{"id":"p","schedule":"*/5 * * * *"}]'
printf '9 2026-01-01T00:00:00Z\n' >"${WL%.md}.waiternudge-deadbeef"
say "answer"
OUT="$(run)"
if ! grep -qF "AND IS NOT LISTENING" <<<"$OUT"; then
    pass "163w-c3 CONTROL: with no live peer the check stays silent"
else
    fail "163w-c3 CONTROL: blocked with nobody to hear from: ${OUT:0:250}"
fi

echo "== 163x. NO CLI verb may fall through to the Stop battery (the phantom stop) =="
# THE DEFECT, measured on HEAD before the fix, not theorised. A verb whose guard
# put the arity check INSIDE the condition (`len(argv) > 3 and argv[1] ==
# "--loop"`) did not fail on too few arguments -- it fell through to the hook
# path, which runs the whole battery against an EMPTY event. With stdin closed
# that returned a genuine `"decision": "block"` at EXIT 0 and wrote six
# `*-unknown` sidecars for a session id that does not exist; with stdin left open
# it hung forever in json.load(sys.stdin). Both reproduced.
#
# The fix is the CLASS, not the three verbs anyone noticed: any argv[1] with a
# leading dash that matched no verb is refused. A typo must not be able to emit a
# verdict or hang.
setup
for _bad in "--loop x" "--brief" "--tpyo" "--state"; do
    # shellcheck disable=SC2086
    OUT="$(reqcli $_bad </dev/null 2>&1)"
    RC=$?
    if [[ "$RC" == "2" ]] && ! grep -qF '"decision": "block"' <<<"$OUT"; then
        pass "163x: '$_bad' is refused (exit 2) and emits NO verdict"
    else
        fail "163x: '$_bad' rc=$RC verdict=${OUT:0:120}"
    fi
done
# It must not hang either. stdin is a pipe that STAYS OPEN, and the timeout is on
# the interpreter itself -- NOT on a shell wrapping a `sleep`, which is what made
# the first measurement of this read 124 for the sleep rather than for python.
if timeout 8 env TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" \
    python3 "$HOOK" --tpyo < <(sleep 15) >/dev/null 2>&1; then
    fail "163x: an unknown verb succeeded, which it must not"
elif [[ "$?" != "124" ]]; then
    pass "163x: an unknown verb does not hang on an open stdin"
else
    fail "163x: an unknown verb still hangs reading stdin"
fi
# CONTROL 1: the legitimate forms still work, so the guards refuse arity and not
# the verb.
setup
if as_peer looppfx1 reqcli --loop looppfx1 2026-01-01T00:00:00Z 1 label </dev/null 2>&1 | grep -qF "loop declared"; then
    pass "163x CONTROL: a well-formed --loop still declares"
else
    fail "163x CONTROL: --loop broke for valid input"
fi
if as_peer briefpf1 reqcli --brief briefpf1 some text </dev/null 2>&1 | grep -qF "brief recorded"; then
    pass "163x CONTROL: a well-formed --brief still records"
else
    fail "163x CONTROL: --brief broke for valid input"
fi
# 163g: a LONE ITEM ID is a misread of the verb, not a very short brief. The word
# reads both ways (publish a brief / brief me on X) and `--brief <me> <text...>`
# is `--tick <me> <id> <evidence>` minus the evidence, so the id lands where the
# sentence goes. Paid for live: a session meaning to READ item 65ce7ca3 published
# it, and the roster then advertised "65ce7ca3" as that session's live activity to
# every later reader. Both real id widths are covered, since ids are 8 or 12 hex
# and the code must never assume one width.
#
# CAPTURE THEN MATCH, never `refusing-command | grep -q`. This suite runs under
# `set -uo pipefail` (line 5), so a pipeline carries the FIRST non-zero exit, not
# grep's. The refusal exits 2 by design, which made the pipeline false while grep
# was matching perfectly: the first version of these cases failed on a green tree
# and, worse, also failed under a mutation that disabled the guard, so its red
# proved nothing. Every other refusal case here captures first for this reason.
for _wid in 65ce7ca3 a1b2c3d4e5f6; do
    OUT="$(as_peer briefpf2 reqcli --brief briefpf2 "$_wid" </dev/null 2>&1)"
    RC=$?
    if [[ "$RC" == "2" ]] && grep -qF "shape of an item id" <<<"$OUT"; then
        pass "163g a bare ${#_wid}-char id is refused as a brief"
    else
        fail "163g a bare ${#_wid}-char id: rc=$RC out=${OUT:0:90}"
    fi
done
# The controls that keep the refusal from swallowing real briefs: the discriminator
# is a LONE all-hex token of id width, so anything with a second word, any non-hex
# character, or a length outside the band must still record.
while IFS='|' read -r _why _txt; do
    # Deliberately unquoted: word-splitting is the point, since these controls
    # exist to prove a MULTI-token brief still records.
    # shellcheck disable=SC2086
    OUT="$(as_peer briefpf3 reqcli --brief briefpf3 $_txt </dev/null 2>&1)"
    RC=$?
    if [[ "$RC" == "0" ]] && grep -qF "brief recorded" <<<"$OUT"; then
        pass "163g CONTROL: $_why still records"
    else
        fail "163g CONTROL: $_why was wrongly refused (rc=$RC)"
    fi
done <<'BRIEFOK'
an id followed by real words|65ce7ca3 is what I am reading
a short non-hex word|triage
a hex string past the id width|abcdefabcdefabcde
a hex string under the id width|abcde
BRIEFOK
# CONTROL 2, THE LOAD-BEARING ONE: the real Stop hook takes NO arguments, so the
# leading-dash catch-all must not be able to swallow it. If this regressed, every
# stop in the repo would exit 2 instead of running any check at all.
setup
brief_now
hand_now
say "answer"
task 7 pending "something"
OUT="$(run)"
if grep -qF '"decision"' <<<"$OUT" || [[ -n "$OUT" ]]; then
    pass "163x CONTROL: a bare (no-argv) invocation still runs the battery"
else
    fail "163x CONTROL: the catch-all swallowed the real hook: '${OUT:0:200}'"
fi

echo "== 163y. v18: unread sub-agent reports are surfaced on an ORDINARY stop =="
# SessionStart and PostCompact are covered by wl_report's own hooks. This is the
# commoner case they miss: a long-running session whose teammate finished twenty
# minutes ago and whose SendMessage has scrolled out of reach. Report-only: an
# unread report is information, not an obligation, and there is no honest
# evidence a stop could demand for "I read it".
setup
brief_now
hand_now
python3 - "$BASE/reports" <<'PYEOF'
import json, pathlib, sys
store = pathlib.Path(sys.argv[1])
(store / "agenttest").mkdir(parents=True, exist_ok=True)
(store / "agenttest" / "r.md").write_text("SUBSTANTIVE FINDING FROM A TEAMMATE\nbody")
(store / "index.jsonl").write_text(json.dumps({
    "ev": "report", "id": "abcdef123456", "at": "2026-08-05T10:00:00Z",
    "branch": "agenttest", "agent": "some-teammate", "type": "some-teammate",
    "session": "deadbeef", "body": "agenttest/r.md", "bytes": 900,
    "silent": False, "sends": 1, "title": "SUBSTANTIVE FINDING FROM A TEAMMATE",
    "transcript": "", "src": "hook"}) + "\n")
PYEOF
say "all done, nothing outstanding"
OUT="$(run)"
if grep -qF "UNREAD SUB-AGENT REPORTS" <<<"$OUT" && grep -qF "SUBSTANTIVE FINDING FROM A TEAMMATE" <<<"$OUT"; then
    pass "163y: an unread report is surfaced on an ordinary stop, with its title"
else
    fail "163y: no unread-report section: ${OUT:0:300}"
fi
if ! grep -qF '"decision": "block"' <<<"$OUT"; then
    pass "163y: it is REPORT-ONLY and does not block the stop"
else
    fail "163y: an unread report blocked the stop: ${OUT:0:300}"
fi
# CONTROL: marked read, the section is gone. Without this the assertion above is
# satisfied by any section that is simply always emitted.
python3 - "$BASE/reports" <<'PYEOF'
import json, pathlib, sys
store = pathlib.Path(sys.argv[1])
(store / "read.jsonl").write_text(json.dumps({
    "ev": "read", "id": "abcdef123456", "by": "deadbeef",
    "at": "2026-08-05T10:05:00Z", "branch": "agenttest"}) + "\n")
PYEOF
newturn
say "all done, nothing outstanding"
OUT="$(run)"
if ! grep -qF "UNREAD SUB-AGENT REPORTS" <<<"$OUT"; then
    pass "163y CONTROL: once marked read, the section is gone"
else
    fail "163y CONTROL: a read report is still surfaced: ${OUT:0:300}"
fi
# CONTROL: a report on ANOTHER branch is not this branch's business.
python3 - "$BASE/reports" <<'PYEOF'
import json, pathlib, sys
store = pathlib.Path(sys.argv[1])
with (store / "index.jsonl").open("a") as f:
    f.write(json.dumps({
        "ev": "report", "id": "999999999999", "at": "2026-08-05T10:00:00Z",
        "branch": "some-other-branch", "agent": "elsewhere", "type": "elsewhere",
        "session": "deadbeef", "body": "x/y.md", "bytes": 900, "silent": False,
        "sends": 1, "title": "FROM ANOTHER BRANCH", "transcript": "",
        "src": "hook"}) + "\n")
PYEOF
newturn
say "all done, nothing outstanding"
OUT="$(run)"
if ! grep -qF "FROM ANOTHER BRANCH" <<<"$OUT"; then
    pass "163y CONTROL: another branch's report is not surfaced here"
else
    fail "163y CONTROL: a foreign branch's report leaked in: ${OUT:0:300}"
fi

echo "== 163z-c1. CONTROL: a waiter that is NOT confirmed buys nothing =="
# Same fixture, same command string, but the process is DEAD -- so the verdict is
# `suspect`. Without this control, 163z would equally pass if the code had simply
# stopped running either check at all.
setup
brief_now
hand_now
mkdir -p "$BASE/bgout"
export WORKLIST_BG_OUTPUT_DIR="$BASE/bgout"
export WORKLIST_HARNESS_PID=$$
BG="$(
    python3 - "$WAITER_CMD" <<'PYEOF'
import json, sys
print(json.dumps([{"id": "wt1", "type": "shell", "status": "running",
                   "command": sys.argv[1], "description": "inbox waiter (dead)"}]))
PYEOF
)"
CRONS='[{"id":"c1","schedule":"*/30 * * * *","prompt":"work loop"}]'
task 7 in_progress "waiting on the inbox"
say "answer

## Remaining
- #7 waiting on the inbox (in_progress)"
run >/dev/null
python3 - "$WL" <<'PYEOF'
import json, pathlib, sys
p = pathlib.Path(sys.argv[1].replace(".md", ".state-deadbeef.json"))
doc = json.loads(p.read_text())
doc["bgwait"] = {"at": "2026-01-01T00:00:00Z"}
p.write_text(json.dumps(doc))
PYEOF
newturn
say "answer

## Remaining
- #7 waiting on the inbox (in_progress)"
OUT="$(run)"
if grep -qF "PURE BACKGROUND WAIT" <<<"$OUT"; then
    pass "163z-c1 CONTROL: an unconfirmed waiter still owes the check-in"
else
    fail "163z-c1 CONTROL: the check-in was skipped for a DEAD waiter: ${OUT:0:250}"
fi

echo "== 163z-c2. CONTROL: a waiter does not silence a REAL job running beside it =="
# Relaxing on "any waiter present" would let one waiter suppress supervision of
# everything else. The suppression requires EVERY live task to be a confirmed
# waiter, and this is the case that pins that word.
setup
brief_now
hand_now
mkdir -p "$BASE/bgout"
export WORKLIST_BG_OUTPUT_DIR="$BASE/bgout"
printf 'worker stream content\n' >"$BASE/bgout/bw1.output"
TMPDIR="$BASE/waittmp2" CLAUDE_PROJECT_DIR="$BASE" $WAITER_CMD >/dev/null 2>&1 &
WAITER_PID=$!
export WORKLIST_HARNESS_PID=$$
sleep 1
BG="$(
    python3 - "$WAITER_CMD" <<'PYEOF'
import json, sys
print(json.dumps([
    {"id": "wt1", "type": "shell", "status": "running", "command": sys.argv[1],
     "description": "inbox waiter"},
    {"id": "bw1", "type": "shell", "status": "running", "command": "sleep 999",
     "description": "long CI watch"},
]))
PYEOF
)"
task 7 in_progress "waiting on both"
say "answer

## Remaining
- #7 waiting on both (in_progress)"
run >/dev/null
python3 - "$WL" <<'PYEOF'
import json, pathlib, sys
p = pathlib.Path(sys.argv[1].replace(".md", ".state-deadbeef.json"))
doc = json.loads(p.read_text())
doc["bgwait"] = {"at": "2026-01-01T00:00:00Z"}
p.write_text(json.dumps(doc))
PYEOF
newturn
say "answer

## Remaining
- #7 waiting on both (in_progress)"
OUT="$(run)"
if grep -qF "PURE BACKGROUND WAIT" <<<"$OUT"; then
    pass "163z-c2 CONTROL: a real job beside the waiter still gets its check-in"
else
    fail "163z-c2 CONTROL: one waiter silenced supervision of a real job: ${OUT:0:250}"
fi
kill "$WAITER_PID" 2>/dev/null
wait "$WAITER_PID" 2>/dev/null
unset WORKLIST_HARNESS_PID

echo "== 163b. a stale output stream is flagged POSSIBLY STUCK =="
setup
brief_now
hand_now
mkdir -p "$BASE/bgout"
export WORKLIST_BG_OUTPUT_DIR="$BASE/bgout"
printf 'old content\n' >"$BASE/bgout/bw2.output"
touch -d '25 minutes ago' "$BASE/bgout/bw2.output"
BG='[{"id":"bw2","type":"shell","status":"running","description":"quiet worker"}]'
task 7 pending "thing"
say "answer

## Remaining
- #7 thing (pending)"
run >/dev/null # seed the wait clock
python3 - "$WL" <<'PYEOF'
import json, pathlib, sys
p = pathlib.Path(sys.argv[1].replace(".md", ".state-deadbeef.json"))
doc = json.loads(p.read_text())
doc["bgwait"] = {"at": "2026-01-01T00:00:00Z"}
p.write_text(json.dumps(doc))
PYEOF
newturn
say "answer

## Remaining
- #7 thing (pending)"
OUT="$(run)"
if grep -qF "POSSIBLY STUCK" <<<"$OUT"; then
    pass "163b: a 25-minute-silent stream is called out"
else
    fail "163b: stale stream not flagged: ${OUT:0:300}"
fi

echo "== 163c. CONTROL: an open item means normal battery, no wait check-in =="
setup
brief_now
hand_now
mkdir -p "$BASE/bgout"
export WORKLIST_BG_OUTPUT_DIR="$BASE/bgout"
BG='[{"id":"bw3","type":"shell","status":"running","description":"worker"}]'
echo '- [ ] (deadbeef) real open work' >>"$WL"
say "answer

## Remaining
- the open work"
OUT="$(run)"
BG='[]'
unset WORKLIST_BG_OUTPUT_DIR
if ! grep -qF "PURE BACKGROUND WAIT" <<<"$OUT"; then
    pass "163c CONTROL: open work suppresses the wait check-in"
else
    fail "163c: check-in fired despite open work: ${OUT:0:250}"
fi

echo "== 163d. a due check-in forfeits the silent poll; a fresh one does not =="
setup
brief_now
hand_now
mkdir -p "$BASE/bgout"
export WORKLIST_BG_OUTPUT_DIR="$BASE/bgout"
printf 'stream\n' >"$BASE/bgout/bw4.output"
BG='[{"id":"bw4","type":"shell","status":"running","description":"watch"}]'
task 6 in_progress "the live prerequisite"
task 7 pending "thing" 6 # v19: blocked scenery so the pure-wait premise holds
say "answer

## Remaining
- #7 thing (pending)"
run >/dev/null # establishes the bgwait mark via the first check-in
reqcli --poll deadbeef >/dev/null
OUT="$(run)"
if [[ -z "$OUT" ]]; then
    pass "163d: a fresh check-in mark keeps the silent poll"
else
    fail "163d: poll paid the battery inside the window: ${OUT:0:200}"
fi
python3 - "$WL" <<'PYEOF'
import json, pathlib, sys
p = pathlib.Path(sys.argv[1].replace(".md", ".state-deadbeef.json"))
doc = json.loads(p.read_text())
doc["bgwait"] = {"at": "2026-01-01T00:00:00Z"}
p.write_text(json.dumps(doc))
PYEOF
reqcli --poll deadbeef >/dev/null
OUT="$(run)"
BG='[]'
unset WORKLIST_BG_OUTPUT_DIR
if [[ -n "$OUT" ]] && grep -qF "PURE BACKGROUND WAIT" <<<"$OUT"; then
    pass "163d CONTROL: a due check-in forfeits the silent poll and delivers the facts"
else
    fail "163d CONTROL: due check-in stayed silent: ${OUT:0:200}"
fi

echo "== 163e. the output-stream path DERIVATION finds the claude-<uid> layout =="
# Regression gate for 9b557ab0e: every other 163 case overrides the base via
# WORKLIST_BG_OUTPUT_DIR, so the derivation itself was untested and its first
# live firing missed the claude-<uid> segment. This case exercises the real
# derivation end to end: no override, TMPDIR pointed at a fixture root, the
# stream living exactly where the harness writes it.
setup
FAKETMP="$BASE/faketmp"
SID_FULL="b9491d9c-full-session-id-fixture"
MUNGED="-x-y" # re.sub non-alnum -> '-' of cwd "/x/y"
mkdir -p "$FAKETMP/claude-$(id -u)/$MUNGED/$SID_FULL/tasks"
printf 'stream\n' >"$FAKETMP/claude-$(id -u)/$MUNGED/$SID_FULL/tasks/bw5.output"
FOUND=$(
    TMPDIR="$FAKETMP" python3 - "$SID_FULL" "$HOOK" <<'PYEOF'
import sys, os
sys.path.insert(0, os.path.dirname(sys.argv[2]))
import tempfile
tempfile.tempdir = None  # re-read TMPDIR
import wl_liveness
rows = wl_liveness.bg_output_facts("/x/y", sys.argv[1],
    [{"id": "bw5", "status": "running", "description": "d"}])
print("found" if rows and rows[0][2] is not None else "missing")
PYEOF
)
if [[ "$FOUND" == "found" ]]; then
    pass "163e: the real derivation locates the claude-<uid> stream layout"
else
    fail "163e: derivation missed the claude-<uid> layout (got: $FOUND)"
fi
# CONTROL: with the stream ABSENT the same call reports missing, so the case
# cannot pass vacuously on a derivation that never stats anything.
rm -f "$FAKETMP/claude-$(id -u)/$MUNGED/$SID_FULL/tasks/bw5.output"
FOUND=$(
    TMPDIR="$FAKETMP" python3 - "$SID_FULL" "$HOOK" <<'PYEOF'
import sys, os
sys.path.insert(0, os.path.dirname(sys.argv[2]))
import tempfile
tempfile.tempdir = None
import wl_liveness
rows = wl_liveness.bg_output_facts("/x/y", sys.argv[1],
    [{"id": "bw5", "status": "running", "description": "d"}])
print("found" if rows and rows[0][2] is not None else "missing")
PYEOF
)
if [[ "$FOUND" == "missing" ]]; then
    pass "163e CONTROL: an absent stream reads as missing, the probe is real"
else
    fail "163e CONTROL: vacuous probe (got: $FOUND)"
fi

echo "== 163f. a stale stream with a VERIFIED-ALIVE OS process is not called stuck =="
# Fired live 2026-07-31: a healthy `until ... completed` CI poll loop, silent
# by design for 29 minutes, was accused POSSIBLY STUCK. Two fixes pinned here
# at once: _needle must extract a quote-free SEGMENT (the poll-loop command
# has a quoted middle, so the old whole-line rule made it unverifiable), and
# the check-in must consult verify_background before accusing.
setup
brief_now
hand_now
mkdir -p "$BASE/bgout"
export WORKLIST_BG_OUTPUT_DIR="$BASE/bgout"
printf 'old content\n' >"$BASE/bgout/bw6.output"
touch -d '25 minutes ago' "$BASE/bgout/bw6.output"
sleep 3717171717 &
PROBE163F=$!
export WORKLIST_HARNESS_PID=$$
# The quoted tail is load-bearing: the OLD _needle refused any line carrying
# a quote, which is exactly how the live worker became unverifiable.
BG='[{"id":"bw6","type":"shell","status":"running","description":"silent poll loop","command":"sleep 3717171717 \"# ci watch tail\""}]'
task 7 pending "thing"
say "answer

## Remaining
- #7 thing (pending)"
run >/dev/null # seed the wait clock
python3 - "$WL" <<'PYEOF'
import json, pathlib, sys
p = pathlib.Path(sys.argv[1].replace(".md", ".state-deadbeef.json"))
doc = json.loads(p.read_text())
doc["bgwait"] = {"at": "2026-01-01T00:00:00Z"}
p.write_text(json.dumps(doc))
PYEOF
newturn
say "answer

## Remaining
- #7 thing (pending)"
OUT="$(run)"
if grep -qF "VERIFIED ALIVE" <<<"$OUT" && ! grep -qF -- "<- POSSIBLY STUCK" <<<"$OUT"; then
    # NOT a plain "POSSIBLY STUCK" grep: V_BG_REPORT's fixed instruction text
    # says "restart or replace anything marked POSSIBLY STUCK" on every
    # check-in, so only the per-row "<- POSSIBLY STUCK" marker is the accusation.
    pass "163f: a stale stream backed by a live OS process is reported alive, not stuck"
else
    fail "163f: alive worker still accused, or not reported: ${OUT:0:300}"
fi
# CONTROL: kill the process and the SAME setup goes back to POSSIBLY STUCK,
# so the rescue is the verification, not an unconditional soft-pedal.
kill "$PROBE163F" 2>/dev/null
wait "$PROBE163F" 2>/dev/null
python3 - "$WL" <<'PYEOF'
import json, pathlib, sys
p = pathlib.Path(sys.argv[1].replace(".md", ".state-deadbeef.json"))
doc = json.loads(p.read_text())
doc["bgwait"] = {"at": "2026-01-01T00:00:00Z"}
p.write_text(json.dumps(doc))
PYEOF
newturn
say "answer

## Remaining
- #7 thing (pending)"
OUT="$(run)"
if grep -qF -- "<- POSSIBLY STUCK" <<<"$OUT" && ! grep -qF "VERIFIED ALIVE" <<<"$OUT"; then
    pass "163f CONTROL: with the process dead the same worker is called out as stuck"
else
    fail "163f CONTROL: dead worker not flagged: ${OUT:0:300}"
fi
unset WORKLIST_HARNESS_PID
unset WORKLIST_BG_OUTPUT_DIR
BG='[]'

# ---------------------------------------------------------------------------
# v16 (cases 164+): the fix-in-session rule. A finding is fixed by the session
# that finds it, so --triage answers the size question and hands back the exact
# next command, --tick refuses a completion whose only evidence is an issue
# reference, and docs/agent/<branch>/PLAN-*.md becomes a durable design record
# the SessionStart and PostCompact hooks hand back. Every FIRE case is paired
# with a SILENT control differing by one planted fact.
# ---------------------------------------------------------------------------

EVENTS="${WL%.md}.events.jsonl"

triage() { # triage <judge-mode> <args...> -- the --triage verb, judge pinned
    local mode="$1"
    shift
    PATH="$BASE/binonly:$PATH" TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" \
        WORKLIST_AGENT_BRANCH=agenttest WORKLIST_JUDGE="$mode" \
        python3 "$HOOK" --triage "$@"
}

echo "== 164. --triage refuses an empty finding and appends NO event =="
setup
EVENTS="${WL%.md}.events.jsonl"
OUT=$(triage off deadbeef 2>&1)
RC=$?
if [[ "$RC" -ne 0 ]] && grep -qF "usage:" <<<"$OUT"; then
    pass "--triage with no finding at all exits non-zero with the usage"
else
    fail "empty --triage was accepted (rc=$RC): ${OUT:0:200}"
fi
OUT=$(triage off deadbeef "   " 2>&1)
RC=$?
if [[ "$RC" -ne 0 ]] && grep -qF "empty finding triages nothing" <<<"$OUT"; then
    pass "--triage with blank finding text is refused, naming why"
else
    fail "blank-text --triage was accepted (rc=$RC): ${OUT:0:200}"
fi
if [[ ! -s "$EVENTS" ]]; then
    pass "both refusals appended NO event (a rejected write is not a delivered one)"
else
    fail "a refused triage still wrote an event: $(head -c 200 "$EVENTS")"
fi
# CONTROL: the same verb WITH a finding does append, so the assertion above
# could have failed. Without this the no-event check passes on a dead verb.
triage off deadbeef "the retry loop swallows the exit code" >/dev/null 2>&1
if [[ -s "$EVENTS" ]] && grep -q '"ev":"add"' "$EVENTS"; then
    pass "164 CONTROL: a real finding DOES append an add event"
else
    fail "164 CONTROL: the verb appends nothing at all: $(head -c 200 "$EVENTS")"
fi

echo "== 165. --triage degrades to a self-assessment and claims NO verdict =="
setup
EVENTS="${WL%.md}.events.jsonl"
OUT=$(triage off deadbeef "the fork path copies .env into the child repo" 2>&1)
RC=$?
if [[ "$RC" -eq 0 ]] && grep -qF "INLINE" <<<"$OUT" && grep -qF "PLAN+SUBAGENT" <<<"$OUT" &&
    grep -qF "OPERATOR-ONLY" <<<"$OUT" && grep -qF "docs/agent/" <<<"$OUT"; then
    pass "a judge-off triage hands back all three recipes and exits 0"
else
    fail "degraded triage wrong (rc=$RC): ${OUT:0:300}"
fi
if grep -q '"ev":"add"' "$EVENTS"; then
    pass "the finding is TRACKED even when no verdict could be produced"
else
    fail "the degraded triage tracked nothing: $(head -c 200 "$EVENTS")"
fi
if ! grep -q '"ev":"triage"' "$EVENTS"; then
    pass "165 CONTROL: degraded mode records NO triage event, so the machinery never claims a verdict it did not produce"
else
    fail "degraded mode recorded a verdict: $(grep '"ev":"triage"' "$EVENTS")"
fi

echo "== 166. --triage --id refuses another session's item =="
setup
EVENTS="${WL%.md}.events.jsonl"
NID=$(as_peer other123 reqcli --add other123 "their finding" | sed -n 's/^added #\([0-9a-f]*\).*/\1/p')
OUT=$(triage off deadbeef --id "$NID" "my take on their finding" 2>&1)
RC=$?
if [[ "$RC" -ne 0 ]] && grep -qF "is owned by other123" <<<"$OUT"; then
    pass "triaging another session's item is refused by owner"
else
    fail "cross-session triage was accepted (rc=$RC): ${OUT:0:200}"
fi
if ! grep -q '"ev":"triage"' "$EVENTS"; then
    pass "166 CONTROL: the refused triage recorded nothing"
else
    fail "a refused triage still recorded a verdict: $(grep '"ev":"triage"' "$EVENTS")"
fi
# The same item, triaged by its OWNER, reaches the degraded printout: the
# refusal is about ownership and not about --id being broken.
OUT=$(as_peer other123 triage off other123 --id "$NID" "their own finding" 2>&1)
if [[ $? -eq 0 ]] && grep -qF "TRIAGE, SELF-ASSESSED (#$NID)" <<<"$OUT"; then
    pass "166 CONTROL: the OWNER triages the same item fine"
else
    fail "166 CONTROL: --id is broken for the owner too: ${OUT:0:200}"
fi

echo "== 167. --triage judge path: verdict, recipe, recorded event, ONE call =="
setup
EVENTS="${WL%.md}.events.jsonl"
: >"$BASE/judgecalls"
shim_judge_out '{"verdict":"plan-subagent","reason":"multi-file","plan_slug":"fix-x"}'
OUT=$(triage on deadbeef "renet forks inherit the parent buildkit session" 2>&1)
RC=$?
if [[ "$RC" -eq 0 ]] && grep -qF "PLAN+SUBAGENT" <<<"$OUT" &&
    grep -qF "docs/agent/agenttest/PLAN-fix-x.md" <<<"$OUT"; then
    pass "a plan-subagent verdict prints the prefilled plan path and the recipe"
else
    fail "plan-subagent recipe wrong (rc=$RC): ${OUT:0:300}"
fi
if grep -q '"ev":"triage"' "$EVENTS" && grep -qF '"v":"plan-subagent"' "$EVENTS" &&
    grep -qF '"plan":"docs/agent/agenttest/PLAN-fix-x.md"' "$EVENTS"; then
    pass "the verdict is RECORDED with its plan path"
else
    fail "triage event missing or wrong: $(tail -c 300 "$EVENTS")"
fi
if [[ "$(wc -l <"$BASE/judgecalls")" -eq 1 ]]; then
    pass "the judge was called exactly once (no retry loop, no double spend)"
else
    fail "judge called $(wc -l <"$BASE/judgecalls") times"
fi
# CONTROL: one different verdict from the same shim takes the other branch.
setup
EVENTS="${WL%.md}.events.jsonl"
: >"$BASE/judgecalls"
shim_judge_out '{"verdict":"inline","reason":"one line and one check","plan_slug":""}'
OUT=$(triage on deadbeef "the error message names the wrong flag" 2>&1)
TID=$(sed -n 's/^triaging #\([0-9a-f]*\).*/\1/p' <<<"$OUT")
if grep -qF "TRIAGE VERDICT: INLINE" <<<"$OUT" && grep -qF -- "--tick deadbeef $TID" <<<"$OUT" &&
    grep -qF '"v":"inline"' "$EVENTS" && ! grep -qF '"plan":' "$EVENTS"; then
    pass "167 CONTROL: an inline verdict orders the fix now and records no plan"
else
    fail "167 CONTROL: inline branch wrong: ${OUT:0:300}"
fi

echo "== 168. a TRIAGED BIG item with no plan file on disk is demanded =="
setup
EVENTS="${WL%.md}.events.jsonl"
NOW=$(date -u +%Y-%m-%dT%H:%M:%SZ)
printf '{"ev":"add","id":"deadbee1","at":"%s","by":"deadbeef","s":" ","o":"deadbeef","t":"forks leak the parent secrets"}\n' \
    "$NOW" >>"$EVENTS"
printf '{"ev":"triage","id":"deadbee1","at":"%s","by":"deadbeef","v":"plan-subagent","reason":"multi-file","plan":"docs/agent/agenttest/PLAN-big.md"}\n' \
    "$NOW" >>"$EVENTS"
OUT=$(reqcli --list --open deadbeef 2>&1)
if grep -qF "TRIAGED BIG, plan file missing: docs/agent/agenttest/PLAN-big.md" <<<"$OUT" &&
    grep -qF -- "--triage deadbeef --id deadbee1" <<<"$OUT"; then
    pass "a big finding whose design was never written is demanded, with both exits"
else
    fail "the plan follow-through never fired: ${OUT:0:300}"
fi
mkdir -p "$BASE/proj/docs/agent/agenttest"
printf '# PLAN: big\nStatus: draft\nOwner: t\nUpdated: 2026-07-31\n' \
    >"$BASE/proj/docs/agent/agenttest/PLAN-big.md"
OUT=$(reqcli --list --open deadbeef 2>&1)
if ! grep -qF "TRIAGED BIG" <<<"$OUT" &&
    grep -qF "plan: docs/agent/agenttest/PLAN-big.md" <<<"$OUT"; then
    pass "168 CONTROL: writing the plan silences the demand and advertises the path"
else
    fail "168 CONTROL: the probe does not read the disk: ${OUT:0:300}"
fi

echo "== 169. --tick refuses evidence that is ONLY an issue reference =="
setup
EVENTS="${WL%.md}.events.jsonl"
reg_repo
SHA=$(cd "$BASE/proj" && git rev-parse HEAD)
NID=$(reqcli --add deadbeef "the retry loop swallows the exit code" | sed -n 's/^added #\([0-9a-f]*\).*/\1/p')
OUT=$(reqcli --tick deadbeef "$NID" "filed as https://github.com/x/y/issues/560" 2>&1)
RC=$?
if [[ "$RC" -ne 0 ]] && grep -qF "door:operator-only" <<<"$OUT" &&
    grep -qF "door:operator-deferred" <<<"$OUT" && grep -qF "door:no-write-access" <<<"$OUT"; then
    pass "a bare issue URL cannot close a finding, and the refusal names all three doors"
else
    fail "the bare-issue tick was accepted (rc=$RC): ${OUT:0:300}"
fi
if ! grep -q '"ev":"state"' "$EVENTS"; then
    pass "the refused tick wrote NO state event"
else
    fail "a refused tick still closed the item: $(grep '"ev":"state"' "$EVENTS")"
fi
OUT=$(reqcli --tick deadbeef "$NID" "filed as https://github.com/x/y/issues/560 door:no-write-access, that repo is not writable here" 2>&1)
if [[ $? -eq 0 ]] && grep -q '"ev":"state"' "$EVENTS"; then
    pass "the SAME evidence naming its door is accepted (the door is the exit)"
else
    fail "a door-carrying tick was refused: ${OUT:0:300}"
fi
# REGRESSION CONTROLS: the gate is narrow. Ordinary evidence still ticks, and
# a URL that is not an issue reference must keep working, because the gate
# rides on the URL shape completion_evidence already accepts.
N2=$(reqcli --add deadbeef "second finding" | sed -n 's/^added #\([0-9a-f]*\).*/\1/p')
OUT=$(reqcli --tick deadbeef "$N2" "ran the suite, exit 0" 2>&1)
RC=$?
N3=$(reqcli --add deadbeef "third finding" | sed -n 's/^added #\([0-9a-f]*\).*/\1/p')
OUT2=$(reqcli --tick deadbeef "$N3" "green on https://github.com/rediacc/console/actions/runs/123456789" 2>&1)
RC2=$?
N4=$(reqcli --add deadbeef "fourth finding" | sed -n 's/^added #\([0-9a-f]*\).*/\1/p')
OUT3=$(reqcli --tick deadbeef "$N4" "fixed in $SHA" 2>&1)
RC3=$?
if [[ "$RC" -eq 0 && "$RC2" -eq 0 && "$RC3" -eq 0 ]]; then
    pass "169 CONTROLS: exit-code, run-URL and verified-sha ticks all still pass"
else
    fail "169 CONTROLS: the door gate is too wide (rc=$RC/$RC2/$RC3): ${OUT:0:100} | ${OUT2:0:100} | ${OUT3:0:100}"
fi

echo "== 170. SessionStart lists non-done plans, with NO design-docs dir =="
setup
mkdir -p "$BASE/proj/docs/agent/agenttest"
printf '# PLAN: a\nStatus: draft\nOwner: t\nUpdated: 2026-07-31\n\nbody\n' \
    >"$BASE/proj/docs/agent/agenttest/PLAN-a.md"
printf '# PLAN: b\nStatus: done\nOwner: t\nUpdated: 2026-07-31\n\nbody\n' \
    >"$BASE/proj/docs/agent/agenttest/PLAN-b.md"
printf '# PLAN: c\nOwner: t\nUpdated: 2026-07-31\n\nbody\n' \
    >"$BASE/proj/docs/agent/agenttest/PLAN-c.md"
out="$(printf '{"session_id":"%s","cwd":"%s"}' "$SID" "$BASE/proj" |
    TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" WORKLIST_AGENT_BRANCH=agenttest \
        python3 "$HOOK" --session-start 2>/dev/null)"
if grep -qF "docs/agent/agenttest/PLAN-a.md [draft]" <<<"$out" &&
    ! grep -qF "PLAN-b.md" <<<"$out" && grep -qF "1 done or superseded plan(s)" <<<"$out"; then
    pass "draft plans are listed, executed ones collapse to a count"
else
    fail "the plans listing is wrong: ${out:0:400}"
fi
if grep -qF "docs/agent/agenttest/PLAN-c.md [UNKNOWN]" <<<"$out"; then
    pass "a plan with no readable Status line surfaces LOUDLY as [UNKNOWN]"
else
    fail "an unparseable Status was hidden: ${out:0:400}"
fi
# THE CONTROL ON THE RESTRUCTURE: docs/ci-overhaul does not exist in this
# fixture, and the old code RETURNED EARLY on that, which would have eaten
# the plans block entirely. The design-docs prose must be absent and the
# plans block present in the SAME output.
if ! grep -qF "READ ALL OF THEM" <<<"$out" && grep -qF "READ EVERY NON-DONE PLAN" <<<"$out"; then
    pass "170 CONTROL: a missing design-docs dir no longer eats the plans block"
else
    fail "170 CONTROL: the two blocks are still coupled: ${out:0:400}"
fi
# And the reverse: with NEITHER, SessionStart stays silent as it always did.
rm -rf "$BASE/proj/docs"
out="$(printf '{"session_id":"%s","cwd":"%s"}' "$SID" "$BASE/proj" |
    TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" WORKLIST_AGENT_BRANCH=agenttest \
        python3 "$HOOK" --session-start 2>/dev/null)"
if [[ -z "$out" ]]; then
    pass "170 CONTROL: no docs and no plans stays silent, as before"
else
    fail "170 CONTROL: SessionStart now talks about nothing: ${out:0:200}"
fi

echo "== 171. PostCompact hands back the executing plan's ## Status cursor =="
setup
hand_now
mkdir -p "$BASE/proj/docs/agent/agenttest"
printf '# PLAN: exec\nStatus: executing\nOwner: t\nUpdated: 2026-07-31\n\n## Status\n\nMARKER_EXEC_CURSOR wave two landed, wave three is next.\n\n## Detail\n\nnot the cursor\n' \
    >"$BASE/proj/docs/agent/agenttest/PLAN-exec.md"
printf '# PLAN: old\nStatus: done\nOwner: t\nUpdated: 2026-07-31\n\n## Status\n\nMARKER_DONE_PLAN must never be handed back.\n' \
    >"$BASE/proj/docs/agent/agenttest/PLAN-old.md"
out="$(printf '{"session_id":"%s","cwd":"%s"}' "$SID" "$BASE/proj" |
    TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" WORKLIST_AGENT_BRANCH=agenttest \
        python3 "$HOOK" --post-compact 2>/dev/null)"
if grep -qF "MARKER_EXEC_CURSOR" <<<"$out" && grep -qF "PLAN-exec.md [executing]" <<<"$out" &&
    grep -qF "picking up an in-progress session" <<<"$out"; then
    pass "the compacted session gets the plan listing AND the executing plan's cursor"
else
    fail "PostCompact plan excerpt missing: ${out:0:400}"
fi
if ! grep -qF "MARKER_DONE_PLAN" <<<"$out" && ! grep -qF "not the cursor" <<<"$out"; then
    pass "171 CONTROL: a done plan is not handed back, and only the Status section is"
else
    fail "171 CONTROL: the excerpt is unbounded: ${out:0:400}"
fi

echo "== 172. allow-report diet: guide is the single source, advisories latch =="
# Operator, 2026-07-31: "Why I see such a big output? We already had round
# robin." The allow report's in-flight section duplicated the guide's own
# [>] rows, and week-stable advisories (other sessions' briefs) repeated on
# every full stop. Now the guide says it once, and slow-moving sections
# re-show only on content change or after the refresh window.
setup
# The default two-cron shape also produces a poll-backoff tip, which is
# another class-2 section and would take the single per-stop slot. The latch
# is what this case is about, so it drains wide and cases 173 to 177 own the
# per-stop rationing.
export WORKLIST_REPORT_PER_STOP=9
brief_now
hand_now
IID=$(reqcli --add deadbeef "carry the CI watch to green" | grep -oE '#[0-9a-f]+' | tr -d '#')
reqcli --lease deadbeef "$IID" +60 worker:bw7 "watching the run" >/dev/null
BG='[{"id":"bw7","type":"shell","status":"running","description":"the watch"}]'
printf '%s %s %s\n' "cafebabe" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "building the fixture" >>"${WL%.md}.sessions"
say "watching.

## Remaining
- #$IID carry the CI watch to green (in flight)"
OUT="$(run)"
if grep -qF -- "- [>] #$IID" <<<"$OUT" && ! grep -qF "in flight on background work" <<<"$OUT"; then
    pass "172: the guide carries the lease once; the duplicate section is gone"
else
    fail "172: duplication or missing guide row: ${OUT:0:400}"
fi
if grep -qF "Other sessions in this worktree" <<<"$OUT"; then
    pass "172: a fresh other-session brief appears on first sight"
else
    fail "172: first sight of the other session was hidden: ${OUT:0:400}"
fi
newturn
reqcli --update deadbeef "$IID" "still watching, run pending" >/dev/null
say "watching.

## Remaining
- #$IID carry the CI watch to green (in flight)"
OUT="$(run)"
if ! grep -qF "Other sessions in this worktree" <<<"$OUT"; then
    pass "172: an unchanged advisory stays quiet on the next stop"
else
    fail "172: the advisory repeated with unchanged content: ${OUT:0:400}"
fi
# CONTROL: changed content re-shows immediately, so the latch is a dedupe,
# not a mute.
printf '%s %s %s\n' "cafebabe" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "pivoted to the deploy fix" >>"${WL%.md}.sessions"
newturn
reqcli --update deadbeef "$IID" "watch still healthy" >/dev/null
say "watching.

## Remaining
- #$IID carry the CI watch to green (in flight)"
OUT="$(run)"
if grep -qF "Other sessions in this worktree" <<<"$OUT" && grep -qF "pivoted to the deploy fix" <<<"$OUT"; then
    pass "172 CONTROL: changed advisory content re-shows immediately"
else
    fail "172 CONTROL: the latch muted a real change: ${OUT:0:400}"
fi
BG='[]'
unset WORKLIST_REPORT_PER_STOP

echo "== 173. one report section per stop; the rest queue and SAY SO =="
# Operator, 2026-07-31: the allow report still emitted every fired section at
# once. It now releases WORKLIST_REPORT_PER_STOP of them, highest priority
# first, and the tail states how many are waiting -- a silent cap reads as
# "that is everything", the same argument the guide's own truncation carries.
outq_fixture() { # four class-2 sections firing on one stop
    say "done for now"
    brief_now
    hand_now
    brief_other cafe1234
    # An orphan needs a dead owner: a transcript for cafe1234 older than
    # WORKLIST_DEAD_HOURS but younger than WORKLIST_ARCHIVE_HOURS.
    touch -d '-48 hours' "$BASE/cafe1234.jsonl"
    echo '- [ ] (cafe1234) their abandoned item' >>"$WL"
}
outq_seen() { # count the four section headers present in $1
    local out="$1" n=0 needle
    for needle in "INBOX HAS BEEN QUIET" "Other sessions in this worktree" \
        "ORPHANED item(s)" "nothing open for this session"; do
        grep -qF "$needle" <<<"$out" && n=$((n + 1))
    done
    echo "$n"
}
setup
outq_fixture
OUT="$(run)"
# FOUR, not three: an orphaned item is by construction another session's OPEN
# item, so it always drags the other-session count along with it.
if [[ "$(outq_seen "$OUT")" -eq 1 ]] &&
    grep -qF "(3 more report section(s) queued" <<<"$OUT"; then
    pass "173: exactly one of four sections is released, and the tail counts the rest"
else
    fail "173: released $(outq_seen "$OUT") section(s), or the queued count is wrong: ${OUT:0:400}"
fi
# CONTROL: one planted fact differs, the per-stop budget. All four land and
# nothing claims a queue, so the cap is the only thing the FIRE leg measured.
setup
export WORKLIST_REPORT_PER_STOP=4
outq_fixture
OUT="$(run)"
if [[ "$(outq_seen "$OUT")" -eq 4 ]] && ! grep -qF "more report section(s) queued" <<<"$OUT"; then
    pass "173 CONTROL: a wide drain emits all four and claims no queue"
else
    fail "173 CONTROL: released $(outq_seen "$OUT") of 4: ${OUT:0:400}"
fi
unset WORKLIST_REPORT_PER_STOP

echo "== 174. FIFO inside a priority class; changed content goes to the BACK =="
# All four sections above are class 2, so nothing outranks anything here and
# the only thing deciding the order is the sequence number each entry earned
# when it was first queued.
outq_fill() { # queue the four, one stop at a time, emitting nothing
    export WORKLIST_REPORT_PER_STOP=0
    say "done for now"
    brief_now
    hand_now
    run >/dev/null # the poll-backoff tip is alone on this stop
    brief_other cafe1234
    newturn
    say "done for now"
    run >/dev/null # the other session's brief joins it
    touch -d '-48 hours' "$BASE/cafe1234.jsonl"
    echo '- [ ] (cafe1234) their abandoned item' >>"$WL"
    newturn
    say "done for now"
    run >/dev/null # the orphan and its item count join
}
outq_order() { # drain four stops at one section each, printing the order
    export WORKLIST_REPORT_PER_STOP=1
    local order="" out
    for _ in 1 2 3 4; do
        newturn
        say "done for now"
        out="$(run)"
        grep -qF "INBOX HAS BEEN QUIET" <<<"$out" && order="$order backoff"
        grep -qF "Other sessions in this worktree" <<<"$out" && order="$order others"
        grep -qF "ORPHANED item(s)" <<<"$out" && order="$order orphans"
        grep -qF "nothing open for this session" <<<"$out" && order="$order items"
    done
    echo "$order"
}
setup
outq_fill
GOT="$(outq_order)"
if [[ "$GOT" == " backoff others orphans items" ]]; then
    pass "174: one priority class drains in the order it was enqueued"
else
    fail "174: drain order was '$GOT'"
fi
# CONTROL: the operator's "changed content re-enqueues at its priority",
# proven rather than asserted. Touch the SECOND section's body and it loses
# the position it had earned instead of keeping it.
setup
outq_fill
printf '%s %s %s\n' "cafe1234" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "pivoted to the deploy fix" >>"${WL%.md}.sessions"
newturn
say "done for now"
run >/dev/null
GOT="$(outq_order)"
if [[ "$GOT" == " backoff orphans items others" ]]; then
    pass "174 CONTROL: a changed section goes to the back of its own class"
else
    fail "174 CONTROL: drain order was '$GOT'"
fi
unset WORKLIST_REPORT_PER_STOP

echo "== 175. priority beats FIFO: an actionable CI note passes an older advisory =="
# PLANTED DEFECT, run 2026-07-31: outq_drain's sort key was changed from
# (prio, seq) to (seq,). Both legs failed, the first with
#   FAIL: 175: priority did not beat FIFO: {"systemMessage": "WORKLIST GUIDE:
#   ... \n\nWorklist: nothing open for this session.\n  1 open item(s) owned
#   by session cafe1234\n\n(1 more report section(s) queued; ...
# which is the inversion exactly: the older class-2 advisory took the slot and
# the CI note was the one left queued. 173 and 174 stayed green throughout. A
# priority ladder nobody has watched invert is a ladder nobody knows is wired
# up.
ci_setup
# The older advisory is another session's item count, NOT its brief:
# ci_trouble returns "multi-session" the moment a second brief is live, and a
# fixture that quietly switches off the check it is racing proves nothing.
echo '- [ ] (cafe1234) their abandoned item' >>"$WL"
export WORKLIST_REPORT_PER_STOP=0
ci_rollup SUCCESS "[$(ci_job "Quality / Static" SUCCESS)]"
ci_run >/dev/null # the class-2 advisory is queued first, and waits
export WORKLIST_REPORT_PER_STOP=1
ci_rollup PENDING "[$(ci_job "E2E / opensuse" FAILURE), $(ci_running "E2E / ubuntu")]"
out="$(ci_run)"
if grep -qF "retry allowlist" <<<"$out" && ! grep -qF "nothing open for this session" <<<"$out"; then
    pass "175: the class-0 CI note is released ahead of the older class-2 advisory"
else
    fail "175: priority did not beat FIFO: ${out:0:400}"
fi
# CONTROL: with the run green there is no class-0 section, and the advisory
# that was passed over is released on the very next stop. It is also what
# makes the leg above non-vacuous: the section really was queued and waiting.
ci_rollup SUCCESS "[$(ci_job "Quality / Static" SUCCESS)]"
out="$(ci_run)"
if grep -qF "nothing open for this session" <<<"$out"; then
    pass "175 CONTROL: the passed-over advisory drains once nothing outranks it"
else
    fail "175 CONTROL: the advisory was lost, not delayed: ${out:0:400}"
fi
unset WORKLIST_REPORT_PER_STOP

echo "== 176. a ONE-SHOT is never dropped, only delayed =="
# The property that decides the whole design, so the fixture is built to make
# the one-shot LOSE its first stop. wl_email.pump spends its budget at compute
# time: it appends the ledger and sends. Nothing can regenerate that note, so
# a report with no room for it has to keep it.
#
# PLANTED DEFECT, run 2026-07-31: outq_drain's per-entry removal was replaced
# with `q["items"][:] = []` (a plausible "reset the queue after draining"
# bug). Leg 2 failed with
#   FAIL: 176: the one-shot was DROPPED, not delayed (mail=1):
#   {"systemMessage": "WORKLIST GUIDE: ... \n\nRequests you posted, still
#   OPEN (they block their recipients, never you): ...
# The digest note was gone for good and a class-2 advisory took its place,
# while the mail count proves no second send could ever bring it back. 173
# also went red on that run (its queued count read 0 instead of 3), but only
# this case says what was LOST rather than that a number was wrong.
ci_setup
mail_fixture
export WORKLIST_REPORT_PER_STOP=1
askid deadbeef operator 'which tier map? DEFAULT: ship the draft map' >/dev/null
ci_rollup PENDING "[$(ci_job "E2E / opensuse" FAILURE), $(ci_running "E2E / ubuntu")]"
out="$(ci_run)"
if grep -qF "retry allowlist" <<<"$out" && ! grep -qF "OPERATOR EMAILED" <<<"$out" &&
    [[ "$(mailcount)" == "1" ]]; then
    pass "176: the class-0 CI note takes stop 1 although the digest has already gone"
else
    fail "176: leg 1 shape wrong (mail=$(mailcount)): ${out:0:400}"
fi
ci_rollup SUCCESS "[$(ci_job "Quality / Static" SUCCESS)]"
out="$(ci_run)"
# The mail count is the proof: pump() sends nothing on this stop, because its
# ledger already holds the digest, so the text can only have come from the
# queue.
if grep -qF "OPERATOR EMAILED" <<<"$out" && [[ "$(mailcount)" == "1" ]]; then
    pass "176: the send note arrives on stop 2 from the queue, with no second send"
else
    fail "176: the one-shot was DROPPED, not delayed (mail=$(mailcount)): ${out:0:400}"
fi
out="$(ci_run)"
out="$(ci_run)"
if ! grep -qF "more report section(s) queued" <<<"$out"; then
    pass "176: the queue empties instead of holding drained entries forever"
else
    fail "176: entries still queued after every section was released: ${out:0:400}"
fi
# CONTROL: the same fixture with no CI trouble at all. The digest note lands
# on stop 1, which is what makes stop 2 above a DELAY rather than the normal
# path.
ci_setup
mail_fixture
askid deadbeef operator 'which tier map? DEFAULT: ship the draft map' >/dev/null
ci_rollup SUCCESS "[$(ci_job "Quality / Static" SUCCESS)]"
out="$(ci_run)"
if grep -qF "OPERATOR EMAILED" <<<"$out"; then
    pass "176 CONTROL: with nothing outranking it the digest note lands on stop 1"
else
    fail "176 CONTROL: the note did not land unopposed either: ${out:0:400}"
fi
unset WORKLIST_REPORT_PER_STOP

echo "== 177. the judge line is a STAMP unless the context is fresh or the reason changed =="
# Operator, 2026-07-31: the approval reason was reprinted on every stop. It
# now rides a stop whose context was just rebuilt (SessionStart, PostCompact)
# or whose reason genuinely changed, and every other stop gets the bare stamp.
# The verdict cache is pinned OFF so every stop pays a fresh call: a cached
# verdict would make the cache, not the signature latch, the thing under test.
ctx_event() { # drive a context-rebuilding hook mode: ctx_event --session-start
    printf '{"session_id":"%s","cwd":"%s"}' "$SID" "$BASE/proj" |
        TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" \
            WORKLIST_AGENT_BRANCH=agenttest python3 "$HOOK" "$1" >/dev/null 2>&1
}
judge_turn() { # a fresh turn whose message satisfies the Remaining demand
    newturn
    say "answer

## Remaining
| #7 | merge the chain | pending, you |"
}
setup
export WORKLIST_JUDGE_CACHE_MIN=0
# Six stops on an unchanged world would otherwise trip stuck detection, which
# has nothing to do with what this case measures.
export WORKLIST_STUCK_ROUNDS=99
brief_now
hand_now
task 7 pending "merge the chain"
judge_turn
shim_judge_out '{"verdict":"stop","reason":"MARKER_REASON_ONE waiting on the run","next_action":"none"}'
ctx_event --session-start
out="$(runj)"
if grep -qF "MARKER_REASON_ONE" <<<"$out"; then
    pass "177: a context-fresh session gets the judge's full approval reason"
else
    fail "177: the fresh-context reason was withheld: ${out:0:400}"
fi
judge_turn
out="$(runj)"
if grep -qF "Stop-gate judge" <<<"$out" && ! grep -qF "MARKER_REASON_ONE" <<<"$out"; then
    pass "177 CONTROL: an ordinary stop gets the stamp alone"
else
    fail "177 CONTROL: the reason was reprinted on an ordinary stop: ${out:0:400}"
fi
# PostCompact is the case the marker is load-bearing for: the state doc
# SURVIVES a compaction, so the reason signature still matches and only the
# marker can bring the full statement back.
ctx_event --post-compact
judge_turn
out="$(runj)"
if grep -qF "MARKER_REASON_ONE" <<<"$out"; then
    pass "177: PostCompact restores the full reason on the next judged stop"
else
    fail "177: a compacted session got the bare stamp: ${out:0:400}"
fi
# The signature arm on its own: no marker anywhere, but a genuinely different
# reason still fires, and a repeat of it does not.
shim_judge_out '{"verdict":"stop","reason":"MARKER_REASON_TWO the gate changed","next_action":"none"}'
judge_turn
out="$(runj)"
if grep -qF "MARKER_REASON_TWO" <<<"$out"; then
    pass "177: a changed reason fires with no context marker at all"
else
    fail "177: a new reason was swallowed by the latch: ${out:0:400}"
fi
judge_turn
out="$(runj)"
if grep -qF "Stop-gate judge" <<<"$out" && ! grep -qF "MARKER_REASON_TWO" <<<"$out"; then
    pass "177: and repeating that reason drops back to the stamp"
else
    fail "177: the changed reason kept reprinting: ${out:0:400}"
fi
unset WORKLIST_JUDGE_CACHE_MIN WORKLIST_STUCK_ROUNDS

echo "== 178. v17: the poll baseline is SESSION-scoped, not repo-scoped =="
# THE BUG this fixes: world_sig hashed the BYTES of the shared markdown, event
# log and requests file, so one teammate's --add broke every other session's
# baseline and forfeited their silent poll. Measured on the live store before
# the fix: 32 of 32 events in a 3-hour window were foreign, polluting 18 of 36
# five-minute windows.
setup
brief_now
hand_now
echo '- [?] (deadbeef) keep the flag? DEFAULT: keep it' >>"$WL"
say "answer

## Remaining
- the flag decision, deferred with a default"
check "178 baseline: the full stop banks the poll baseline" allow "operator may answer"
# A DIFFERENT session tracks its own work. Nothing about this session moved.
as_peer cafe1234 reqcli --add cafe1234 "a teammate's own finding" >/dev/null
reqcli --poll deadbeef >/dev/null
OUT="$(run)"
if [[ -z "$OUT" ]]; then
    pass "178: another session's worklist event does NOT forfeit the silent poll"
else
    fail "178: a foreign event paid the full battery: ${OUT:0:200}"
fi
# CONTROL: the signature is not simply dead -- this session's OWN store write
# still forfeits, which is the whole point of having a baseline.
reqcli --add deadbeef "my own new finding" >/dev/null
reqcli --poll deadbeef >/dev/null
OUT="$(run)"
if [[ -n "$OUT" ]] && grep -qF "OPEN worklist item" <<<"$OUT"; then
    pass "178 CONTROL: this session's own store write still forfeits the silence"
else
    fail "178 CONTROL: an own item went silent: ${OUT:0:200}"
fi

echo "== 178b. a foreign REQUEST to someone else is invisible; to me it is not =="
setup
brief_now
hand_now
echo '- [?] (deadbeef) keep the flag? DEFAULT: keep it' >>"$WL"
say "answer

## Remaining
- the flag decision, deferred with a default"
check "178b baseline" allow "operator may answer"
askid_as cafe1234 beefcafe "a question between two OTHER sessions" >/dev/null
reqcli --poll deadbeef >/dev/null
OUT="$(run)"
if [[ -z "$OUT" ]]; then
    pass "178b: a request between two other sessions keeps the silence"
else
    fail "178b: a foreign request forfeited: ${OUT:0:200}"
fi
askid_as cafe1234 deadbeef "please rebuild the docs index" >/dev/null
reqcli --poll deadbeef >/dev/null
OUT="$(run)"
if [[ -n "$OUT" ]] && grep -qF "rebuild the docs index" <<<"$OUT"; then
    pass "178b CONTROL: a request addressed to ME still forfeits and delivers"
else
    fail "178b CONTROL: a request to me was swallowed: ${OUT:0:200}"
fi

echo "== 179. v17: the bgwait latch RESETS when the wait ends =="
# THE BUG: the clock was only written inside the wait state, so leaving it
# froze the stamp. Re-entering an hour later found it 60 minutes old and fired
# the roster demand on the FIRST stop back -- "you started waiting, report",
# the exact thing the silent seed exists to prevent.
setup
brief_now
hand_now
mkdir -p "$BASE/bgout"
export WORKLIST_BG_OUTPUT_DIR="$BASE/bgout"
printf 'stream\n' >"$BASE/bgout/bw9.output"
BGON='[{"id":"bw9","type":"shell","status":"running","description":"long watch"}]'
BG="$BGON"
task 7 in_progress "waiting on the nightly"
say "answer

## Remaining
- #7 waiting on the nightly (in_progress)"
run >/dev/null # seeds the wait clock
age_bgwait() {
    python3 - "$WL" <<'PYEOF'
import json, pathlib, sys
p = pathlib.Path(sys.argv[1].replace(".md", ".state-deadbeef.json"))
doc = json.loads(p.read_text())
doc.setdefault("bgwait", {})["at"] = "2026-01-01T00:00:00Z"
p.write_text(json.dumps(doc))
PYEOF
}
has_bgwait() {
    python3 - "$WL" <<'PYEOF'
import json, pathlib, sys
p = pathlib.Path(sys.argv[1].replace(".md", ".state-deadbeef.json"))
try:
    doc = json.loads(p.read_text())
except OSError:
    doc = {}
print("present" if doc.get("bgwait") else "absent")
PYEOF
}
age_bgwait
# The wait ENDS: the workers are gone.
BG='[]'
newturn
say "the watch finished

## Remaining
- #7 waiting on the nightly (in_progress)"
run >/dev/null
if [[ "$(has_bgwait)" == "absent" ]]; then
    pass "179: leaving the wait state clears the check-in clock"
else
    fail "179: the stale clock survived the end of the wait"
fi
# And a LATER wait re-seeds silently instead of firing on arrival.
BG="$BGON"
newturn
say "started a new watch

## Remaining
- #7 waiting on the nightly (in_progress)"
OUT="$(run)"
if ! grep -qF "PURE BACKGROUND WAIT" <<<"$OUT"; then
    pass "179: re-entering a wait re-seeds the clock instead of firing on arrival"
else
    fail "179: the check-in fired on the first stop of a NEW wait: ${OUT:0:250}"
fi
# CONTROL: the latch is not simply disabled -- aged INSIDE a live wait it fires.
age_bgwait
newturn
say "still waiting

## Remaining
- #7 waiting on the nightly (in_progress)"
OUT="$(run)"
if grep -qF "PURE BACKGROUND WAIT" <<<"$OUT"; then
    pass "179 CONTROL: aged inside a live wait, the check-in still fires"
else
    fail "179 CONTROL: the check-in never fires at all now: ${OUT:0:250}"
fi
# v17 requirement 3: the bound is VISIBLE, so a reader can verify the latch
# from the message alone.
if grep -qF "Last delivered:" <<<"$OUT" && grep -qF "Next one no earlier than" <<<"$OUT"; then
    pass "179: the check-in carries its last-fired and next-earliest stamps"
else
    fail "179: the check-in still only CLAIMS a bound: ${OUT:0:300}"
fi
BG='[]'
unset WORKLIST_BG_OUTPUT_DIR

echo "== 180. v17: three no-op wakes collapse the whole stop to ONE line =="
setup
brief_now
hand_now
mkdir -p "$BASE/bgout"
export WORKLIST_BG_OUTPUT_DIR="$BASE/bgout"
printf 'stream\n' >"$BASE/bgout/bwq.output"
BG='[{"id":"bwq","type":"shell","status":"running","description":"long watch"}]'
task 7 in_progress "waiting on the nightly"
# A real deferral, so the NON-collapsed report has a guide in it. Since v18 an
# empty guide is silent, and the reset control below needs a full report it can
# actually see coming back.
echo '- [?] (deadbeef) keep the flag? DEFAULT: keep it' >>"$WL"
quiet_turn() {
    newturn
    say "still waiting on the nightly

## Remaining
- #7 waiting on the nightly (in_progress)
- the flag decision, deferred with a default"
}
quiet_turn
OUT1="$(run)"
quiet_turn
OUT2="$(run)"
quiet_turn
OUT3="$(run)"
if grep -qF "CONSECUTIVE QUIET WAKES" <<<"$OUT3"; then
    pass "180: the third consecutive no-op wake fires the reschedule message"
else
    fail "180: no collapse after three quiet wakes: ${OUT3:0:300}"
fi
if ! grep -qF "CONSECUTIVE QUIET WAKES" <<<"$OUT1" && ! grep -qF "CONSECUTIVE QUIET WAKES" <<<"$OUT2"; then
    pass "180: and NOT before three (one quiet wake proves nothing)"
else
    fail "180: fired too early: 1='${OUT1:0:120}' 2='${OUT2:0:120}'"
fi
if grep -qF '*/10 * * * *' <<<"$OUT3"; then
    pass "180: it names the next rung up from */5"
else
    fail "180: no next rung in the message: ${OUT3:0:300}"
fi
# THE FOCUS REQUIREMENT: this is the ENTIRE output. The worker roster, the
# guide and the advisory sections are all gone.
if ! grep -qF "PURE BACKGROUND WAIT" <<<"$OUT3" &&
    ! grep -qF "bwq (long watch)" <<<"$OUT3" &&
    ! grep -qF "WORKLIST GUIDE" <<<"$OUT3"; then
    pass "180: the quiet wake emits ONLY the one-liner (no roster, no guide)"
else
    fail "180: the collapsed stop still carried other sections: ${OUT3:0:400}"
fi
# CONTROL: a real event -- new bytes on a worker's stream -- resets the streak.
printf 'the worker printed something new\n' >>"$BASE/bgout/bwq.output"
quiet_turn
OUT="$(run)"
if ! grep -qF "CONSECUTIVE QUIET WAKES" <<<"$OUT" && grep -qF "WORKLIST GUIDE" <<<"$OUT"; then
    pass "180 CONTROL: new worker output resets the streak and restores the full report"
else
    fail "180 CONTROL: the collapse survived a real event: ${OUT:0:300}"
fi
# ... and the count starts again from zero rather than resuming where it was.
quiet_turn
OUT="$(run)"
if ! grep -qF "CONSECUTIVE QUIET WAKES" <<<"$OUT"; then
    pass "180 CONTROL: the streak restarts from zero, it does not resume"
else
    fail "180 CONTROL: the streak resumed after a real event: ${OUT:0:300}"
fi

echo "== 180b. a HARD check is never suppressed by the quiet collapse =="
# The whole risk of collapsing output is hiding something that matters. Get a
# session into the collapsed state, then plant an open item: it must BLOCK.
setup
brief_now
hand_now
mkdir -p "$BASE/bgout"
export WORKLIST_BG_OUTPUT_DIR="$BASE/bgout"
printf 'stream\n' >"$BASE/bgout/bwh.output"
BG='[{"id":"bwh","type":"shell","status":"running","description":"long watch"}]'
task 7 pending "waiting"
for _ in 1 2 3; do
    newturn
    say "still waiting

## Remaining
- #7 waiting (pending)"
    OUT="$(run)"
done
if grep -qF "CONSECUTIVE QUIET WAKES" <<<"$OUT"; then
    pass "180b setup: the session is in the collapsed quiet state"
else
    fail "180b setup: never reached the collapsed state: ${OUT:0:250}"
fi
echo '- [ ] (deadbeef) a real finding that must not be swallowed' >>"$WL"
newturn
say "still waiting

## Remaining
- #7 waiting (pending)"
check "180b: an open item BLOCKS even from inside the quiet collapse" block "OPEN worklist item"
BG='[]'
unset WORKLIST_BG_OUTPUT_DIR

echo "== 180c. the rung ladder escalates 5->10->20->40->60 and CAPS =="
OUT=$(
    python3 - "$(dirname "$HOOK")" <<'PYEOF'
import sys
sys.path.insert(0, sys.argv[1])
import wl_checks as CK
fail = 0
want = [("*/5 * * * *", "*/10 * * * *"), ("*/10 * * * *", "*/20 * * * *"),
        ("*/20 * * * *", "*/40 * * * *"), ("*/40 * * * *", "0 * * * *")]
for cur, nxt in want:
    note = CK.quiet_wake_note([{"id": "p", "schedule": cur}], 3)
    if nxt not in note:
        print("rung %s did not recommend %s: %r" % (cur, nxt, note[:120])); fail += 1
cap = CK.quiet_wake_note([{"id": "p", "schedule": "0 * * * *"}], 9)
if "cap" not in cap or "0 * * * *" in cap.split("cap")[1]:
    print("the top rung did not cap cleanly: %r" % cap[:160]); fail += 1
# No recognisable poll cron -> no collapse at all, so the report is never
# replaced by an instruction the session cannot act on.
for crons in ([], [{"id": "p", "schedule": "*/7 * * * *"}],
              [{"id": "p", "schedule": "*/5 * * * *"}, {"id": "q", "schedule": "*/5 * * * *"}]):
    if CK.quiet_wake_note(crons, 5) != "":
        print("collapsed on an unusable cron shape: %r" % crons); fail += 1
print("ladder failures=%d" % fail)
sys.exit(1 if fail else 0)
PYEOF
)
if [[ $? -eq 0 ]]; then
    pass "180c: every rung recommends the next, the top rung caps, odd shapes decline"
else
    fail "180c: $OUT"
fi

echo "== 180d. this session's OWN progress note is a real event =="
# Found by the suite, not by design: with the streak keyed on item STRUCTURE
# alone, a session dutifully renewing its lease and posting --update notes
# looked quiet, and case 172's advisory got collapsed away. Doing what the
# liveness ladder asks is movement.
setup
brief_now
hand_now
mkdir -p "$BASE/bgout"
export WORKLIST_BG_OUTPUT_DIR="$BASE/bgout"
printf 'stream\n' >"$BASE/bgout/bwu.output"
BG='[{"id":"bwu","type":"shell","status":"running","description":"the watch"}]'
UID180=$(reqcli --add deadbeef "carry the CI watch to green" | grep -oE '#[0-9a-f]+' | tr -d '#')
reqcli --lease deadbeef "$UID180" +60 worker:bwu "watching the run" >/dev/null
upd_turn() {
    newturn
    say "watching.

## Remaining
- #$UID180 carry the CI watch to green (in flight)"
}
for _ in 1 2 3; do
    upd_turn
    OUT="$(run)"
done
if grep -qF "CONSECUTIVE QUIET WAKES" <<<"$OUT"; then
    pass "180d setup: three untouched wakes do collapse"
else
    fail "180d setup: never collapsed: ${OUT:0:250}"
fi
reqcli --update deadbeef "$UID180" "still watching, run pending" >/dev/null
upd_turn
OUT="$(run)"
if ! grep -qF "CONSECUTIVE QUIET WAKES" <<<"$OUT"; then
    pass "180d: an --update on this session's own item resets the streak"
else
    fail "180d: a progress note was treated as silence: ${OUT:0:300}"
fi
BG='[]'
unset WORKLIST_BG_OUTPUT_DIR

echo "== 180e. a worker DYING is never silenced by the streak =="
# The one change a byte-level view cannot see: the stream is identical, the
# event still lists the task as running, and the only difference is that the
# OS process is gone. If the streak counter could hide that, the collapse
# would be actively dangerous rather than merely quiet.
setup
brief_now
hand_now
mkdir -p "$BASE/bgout"
export WORKLIST_BG_OUTPUT_DIR="$BASE/bgout"
printf 'old content\n' >"$BASE/bgout/bwd.output"
touch -d '25 minutes ago' "$BASE/bgout/bwd.output"
sleep 3717171718 &
PROBE180E=$!
export WORKLIST_HARNESS_PID=$$
BG='[{"id":"bwd","type":"shell","status":"running","description":"silent watch","command":"sleep 3717171718"}]'
task 7 pending "thing"
dead_turn() {
    newturn
    say "answer

## Remaining
- #7 thing (pending)"
}
for _ in 1 2 3 4; do
    dead_turn
    OUT="$(run)"
done
if grep -qF "CONSECUTIVE QUIET WAKES" <<<"$OUT"; then
    pass "180e setup: a live, silent worker collapses into the quiet state"
else
    fail "180e setup: never collapsed with a live worker: ${OUT:0:250}"
fi
kill "$PROBE180E" 2>/dev/null
wait "$PROBE180E" 2>/dev/null
# The check-in window is opened too, so this case asserts BOTH halves: the
# streak breaks, AND the report that the break makes room for actually
# carries the accusation. Without the ageing it would only ever prove the
# first half, and a half-proof of a safety property is not one.
python3 - "$WL" <<'PYEOF'
import json, pathlib, sys
p = pathlib.Path(sys.argv[1].replace(".md", ".state-deadbeef.json"))
doc = json.loads(p.read_text())
doc.setdefault("bgwait", {})["at"] = "2026-01-01T00:00:00Z"
p.write_text(json.dumps(doc))
PYEOF
dead_turn
OUT="$(run)"
if ! grep -qF "CONSECUTIVE QUIET WAKES" <<<"$OUT" && grep -qF -- "<- POSSIBLY STUCK" <<<"$OUT"; then
    pass "180e: the worker's death breaks the streak and delivers the accusation"
else
    fail "180e: a dead worker stayed hidden behind the streak: ${OUT:0:400}"
fi
BG='[]'
unset WORKLIST_BG_OUTPUT_DIR WORKLIST_HARNESS_PID

echo "== 181. ISOLATION: the suite can never reach the live worklist =="
# Raised by the team lead after a run of this suite came back with failures a
# clean tree could not reproduce, on the hypothesis that fixture state and live
# session state were mixing. They were not mixing on DISK -- every invocation
# passes TMPDIR -- but the check belongs here rather than in anyone's memory,
# because the cost of being wrong is a suite that tests the operator's real
# store. Two halves: the store path resolves inside the fixture, and the
# ENVIRONMENT the hook reads carries no ambient knob.
setup
RESOLVED="$(TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" python3 "$HOOK" --path)"
if [[ "$RESOLVED" == "$BASE/tmp/"* ]]; then
    pass "181: the fixture store resolves inside the fixture, not beside the live one"
else
    fail "181: fixture store escaped to '$RESOLVED'"
fi
# CONTROL: without the fixture TMPDIR the SAME command resolves somewhere else
# entirely, so the assertion above is about TMPDIR doing the work and not about
# the path being unconditionally fixture-shaped.
ELSEWHERE="$(TMPDIR=/var/tmp CLAUDE_PROJECT_DIR="$BASE/proj" python3 "$HOOK" --path)"
if [[ "$ELSEWHERE" != "$RESOLVED" && "$ELSEWHERE" == /var/tmp/* ]]; then
    pass "181 CONTROL: TMPDIR is what pins it; a different one moves the store"
else
    fail "181 CONTROL: TMPDIR did not move the store ('$ELSEWHERE')"
fi
# The env half. Every WORKLIST_* knob the operator's shell might carry is
# scrubbed at suite start, and setup() re-scrubs the ones cases set, so a stop
# here runs on the suite's own configuration whatever the launching shell had.
LEAKED=""
for _v in WORKLIST_QUIET_WAKES WORKLIST_BG_OUTPUT_DIR WORKLIST_HARNESS_PID \
    WORKLIST_BG_REPORT_MIN WORKLIST_REPORT_PER_STOP WORKLIST_FOCUS \
    WORKLIST_STUCK_ROUNDS WORKLIST_JUDGE_CACHE_MIN; do
    [[ -n "${!_v:-}" ]] && LEAKED="$LEAKED $_v=${!_v}"
done
if [[ -z "$LEAKED" ]]; then
    pass "181: no ambient WORKLIST_* knob survives into a case"
else
    fail "181: ambient knobs leaked into the suite:$LEAKED"
fi
# The report store is pinned rather than scrubbed: an UNSET WORKLIST_REPORTS_DIR
# is not neutral, it points wl_report at the operator's real store under $HOME.
if [[ "${WORKLIST_REPORTS_DIR:-}" == "$BASE/reports" ]]; then
    pass "181: the report store is pinned inside the fixture"
else
    fail "181: report store is '${WORKLIST_REPORTS_DIR:-<unset -- reads the REAL store>}'"
fi

echo "== 182. SessionStart source=compact does NOT re-inject the docs blurb =="
# THE BUG (operator, 2026-08-04): a long-running licensing session compacted,
# Claude Code fired SessionStart with source=compact, and the session was handed
# "N design doc(s) in docs/ci-overhaul" plus an order to read all of them --
# material belonging to an unrelated program, injected mid-task. Compaction is
# handle_post_compact's job (cases 20, 21, 171): it already re-points at the
# design docs AND hands back the branch's plans, so SessionStart must stay quiet.
setup
mkdir -p "$BASE/proj/docs/ci-overhaul" "$BASE/proj/docs/agent/agenttest"
printf '# doc\nbody\n' >"$BASE/proj/docs/ci-overhaul/01-design.md"
printf '# PLAN: a\nStatus: draft\nOwner: t\nUpdated: 2026-08-04\n\nbody\n' \
    >"$BASE/proj/docs/agent/agenttest/PLAN-a.md"
ss_out() { # ss_out <source-json-fragment>
    printf '{"session_id":"%s","cwd":"%s","hook_event_name":"SessionStart"%s}' \
        "$SID" "$BASE/proj" "$1" |
        TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" WORKLIST_AGENT_BRANCH=agenttest \
            python3 "$HOOK" --session-start 2>/dev/null
}
out="$(ss_out ',"source":"compact"')"
if [[ -z "$out" ]]; then
    pass "a compact-sourced SessionStart says nothing at all"
else
    fail "compact still injects context: ${out:0:300}"
fi
# THE CONTROL, because a check that can only pass is not a check: the very same
# fixture must still speak on a genuinely new session, and on an event with no
# source field at all (the shape every older case in this suite feeds).
out="$(ss_out ',"source":"startup"')"
if grep -qF "READ ALL OF THEM" <<<"$out" && grep -qF "READ EVERY NON-DONE PLAN" <<<"$out"; then
    pass "182 CONTROL: source=startup still gets the docs AND the plans"
else
    fail "182 CONTROL: startup lost its context: ${out:0:300}"
fi
out="$(ss_out '')"
if grep -qF "READ ALL OF THEM" <<<"$out"; then
    pass "182 CONTROL: an event with no source field is not treated as compact"
else
    fail "182 CONTROL: a missing source silenced the hook: ${out:0:300}"
fi
# The marker the judge stamp rides on is set BEFORE the compact return, so a
# compacted session still gets the full approval reason on its next judged stop.
rm -f "$BASE"/tmp/claude-worklist/*.state-*.json
ss_out ',"source":"compact"' >/dev/null
if python3 - "$BASE" <<'PY'; then
import glob, json, sys
docs = [json.load(open(p)) for p in glob.glob(sys.argv[1] + "/tmp/claude-worklist/*.state-*.json")]
sys.exit(0 if any(d.get("ctx_fresh", {}).get("why", "").startswith("session-start") for d in docs) else 1)
PY
    pass "182: compact still marks the context fresh for the judge stamp"
else
    fail "182: the compact path stopped marking ctx_fresh"
fi

echo "== 183. a failed judge child explains ITSELF, not an empty stderr =="
# THE BUG (2026-08-05): the Stop gate blocked with "judge exited 1: " and nothing
# after the colon, which is unactionable. wl_judge reported proc.stderr on a
# non-zero exit, but the claude CLI writes its error ENVELOPE TO STDOUT -- stderr
# is empty -- and the is_error branch that would have explained it sits behind
# returncode == 0, so it was unreachable exactly when needed. The real cause was
# error_max_budget_usd at $0.1025 against a $0.10 cap. A gate that cannot say why
# it failed is an escape hatch wearing a gate's clothes: the same swallowed-
# failure class this repo scans for, inside the thing that audits it.
if python3 - "$(dirname "$HOOK")" <<'JUDGEDIAG'; then
import sys, json
sys.path.insert(0, sys.argv[1])
import wl_judge

class P:
    def __init__(self, rc, out, err):
        self.returncode, self.stdout, self.stderr = rc, out, err

# Derive the over-budget cost from the CURRENT constant rather than hardcoding
# the 0.1025 that was measured against a $0.10 default. The first draft of this
# case pinned the literal and went red the moment the default was raised to
# $0.25 -- a test coupled to a constant it does not own, caught by running it.
budget = float(wl_judge.JUDGE_BUDGET_USD)
envelope = json.dumps({
    "is_error": True, "subtype": "error_max_budget_usd",
    "stop_reason": "tool_use", "total_cost_usd": budget + 0.01,
})
msg = wl_judge._explain_failed_exit("judge", P(1, envelope, ""))
# The cause must be NAMED. Asserting merely "non-empty" would have passed on the
# original defect too, whose message was also non-empty.
assert "error_max_budget_usd" in msg, msg
assert "cost=" in msg, msg
assert "BUDGET EXHAUSTED" in msg, msg

# CONTROL 0: a failure UNDER budget must NOT cry budget. Without this, a message
# that always shouted BUDGET EXHAUSTED would satisfy the assertion above.
under = json.dumps({"is_error": True, "subtype": "error_during_execution",
                    "total_cost_usd": budget / 2})
m0 = wl_judge._explain_failed_exit("judge", P(1, under, ""))
assert "BUDGET EXHAUSTED" not in m0, m0
assert "error_during_execution" in m0, m0

# CONTROL 1: unparseable stdout must still say something concrete rather than
# falling back to the empty stderr that started all this.
m2 = wl_judge._explain_failed_exit("judge", P(1, "segfault", ""))
assert "segfault" in m2, m2

# CONTROL 2: a populated stderr must still be surfaced, so the fix did not trade
# one blind spot for another.
m3 = wl_judge._explain_failed_exit("triage", P(2, "", "boom: no such model"))
assert "no such model" in m3, m3

# CONTROL 3: the label distinguishes the two call sites, which is how an operator
# knows whether triage or the judge died.
assert m3.startswith("triage exited 2"), m3

# CONTROL 4 -- THE ONE THAT MATTERS, and it was missing from the first draft.
# Everything above exercises the HELPER. The defect lived in the CALL SITES, which
# formatted their own message from an empty stderr. Reverting a call site leaves
# the helper perfect and the bug fully restored, and the planted-defect proof
# showed exactly that: the case passed with the original defect back in place.
# A test that cannot see the regression it was written for is the ninth instance
# of the probe-tests-the-wrong-thing class in this campaign. So assert the wiring,
# not just the function.
import pathlib
src = pathlib.Path(sys.argv[1], "wl_judge.py").read_text(encoding="utf-8")
code = "\n".join(
    ln for ln in src.splitlines() if not ln.lstrip().startswith("#")
)
assert code.count("_explain_failed_exit(") >= 3, (
    "both non-zero-exit call sites must route through the helper "
    "(definition + 2 uses); found %d" % code.count("_explain_failed_exit(")
)
assert "exited %d: %s" not in code, (
    "a call site is formatting its own exit message again -- that is the "
    "2026-08-05 defect, which reports an EMPTY stderr because the CLI writes "
    "its error envelope to stdout"
)
JUDGEDIAG
    pass "183: a failed judge child names its own cause (budget, stdout, stderr, label)"
else
    fail "183: wl_judge._explain_failed_exit no longer explains a failed child"
fi

# ---------------------------------------------------------------------------
# v19: RUNTIME CALLER IDENTITY. Every <me> argument used to be accepted on SHAPE
# alone (PREFIX_RE), and nothing had ever compared one to reality.
# ---------------------------------------------------------------------------

echo "== 184. v19 L1: every verb taking a <me> refuses an identity this session is not =="
# THE DEFECT, replayed verbatim. A session copied a SUB-AGENT's namespace token
# out of a Task-spawn tool result (`agent_id: search-renet2@session-4c3e095a`)
# and passed it as its own <me> for 26 hours: 219 calls under 4c3e095a and 20
# under its real id, from ONE process. Every call SUCCEEDED, because writes and
# reads key off the same unvalidated string -- so one typo splits a session into
# two internally-consistent halves, and a peer's message waited 34 hours in the
# half nobody was reading.
#
# THREE CONTROLS PER VERB, each differing from FIRE in ONE planted fact:
#   A  the prefix is this session's        -> accepted, and the effect HAPPENS
#   B  the environment cannot say who I am -> accepted (the deliberate silent
#      pass), which also proves FIRE was caused by the CHECK and not by an
#      unrelated failure in the same command
#   C  the prefix is too short             -> refused by the length floor
setup
brief_now
brief_other cafe1234
mkdir -p "$BASE/reports/agenttest"
python3 - "$BASE/reports" <<'PYEOF'
import json, pathlib, sys
store = pathlib.Path(sys.argv[1])
(store / "agenttest").mkdir(parents=True, exist_ok=True)
(store / "agenttest" / "l1.md").write_text("L1 FIXTURE REPORT\nbody")
(store / "index.jsonl").write_text(json.dumps({
    "ev": "report", "id": "l1report0001", "at": "2026-08-05T10:00:00Z",
    "branch": "agenttest", "agent": "l1-teammate", "type": "l1-teammate",
    "session": "deadbeef", "body": "agenttest/l1.md", "bytes": 900,
    "silent": False, "sends": 1, "title": "L1 FIXTURE REPORT",
    "transcript": "", "src": "hook"}) + "\n")
PYEOF

l1run() { # the CLI under the fixture; STATE body on stdin so --state is drivable
    printf '%s' "$STATE_BODY" |
        TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" WORKLIST_JUDGE=off \
            python3 "$HOOK" "$@" 2>&1
}

# Fixtures the write verbs need. Built as deadbeef, which is this suite's own
# identity, so building them exercises CONTROL A's path before the table runs.
mkitem() { l1run --add deadbeef "$1" | sed -n 's/^added #\([0-9a-f]*\).*/\1/p'; }
I_TICK=$(mkitem l1-tick-item)
I_DEFER=$(mkitem l1-defer-item)
I_UPDATE=$(mkitem l1-update-item)
I_LEASE=$(mkitem l1-lease-item)
mkitem l1-list-item >/dev/null # the --list row asserts on the TEXT, not the id
R_ANSWER=$(askid_as cafe1234 deadbeef l1-answer-me)
R_DECLINE=$(askid_as cafe1234 deadbeef l1-decline-me)
R_ACK=$(l1run --ask deadbeef cafe1234 l1-ack-me | sed -n 's/.*#\([0-9a-f]\{8\}\).*/\1/p' | head -n1)
as_peer cafe1234 l1run --answer cafe1234 "$R_ACK" l1-their-answer >/dev/null
# A phantom for the --reassign row: three aged events under an identity that has
# never stopped, owning open items. Case 184 runs no Stop hook, so no
# .lastevent- file exists for anybody here, which is exactly the phantom shape.
phantom_store phantom1 90

# label | args (@ME@ is substituted) | needle proving the effect happened
L1_TABLE=(
    "--add|--add @ME@ l1-table-add|added #"
    "--triage|--triage @ME@ l1-table-finding|triaging #"
    "--tick|--tick @ME@ $I_TICK https://ci.invalid/run/1|ticked #"
    "--defer|--defer @ME@ $I_DEFER q DEFAULT: do-it WHY: needs-an-operator-ruling HOW: operator-answers|deferred #"
    "--update|--update @ME@ $I_UPDATE moved-a-bit|updated #"
    "--lease|--lease @ME@ $I_LEASE +30 worker:l1bg|leased #"
    "--list|--list --open @ME@|l1-list-item"
    "--state|--state @ME@|STATE.md section written"
    "--loop|--loop @ME@ 2099-01-01T00:00:00Z 1 l1-label|loop declared"
    "--brief|--brief @ME@ l1-brief-text|brief recorded"
    "--intent|--intent @ME@ l1-intent-text --for 30|intent recorded"
    "--reap|--reap @ME@ l1task9|reaped 1 task"
    "--ask|--ask @ME@ cafe1234 l1-table-ask|request #"
    "--answer|--answer @ME@ $R_ANSWER l1-my-answer|answered #"
    "--decline|--decline @ME@ $R_DECLINE l1-my-decline|declined #"
    "--ack|--ack @ME@ $R_ACK|acked #"
    "--poll|--poll @ME@|"
    "--reports|--reports --read @ME@ l1report0001|marked 1 report"
    "--reports|--reports --list --as @ME@|L1 FIXTURE REPORT"
    "--reassign|--reassign @ME@ phantom1|reassigned phantom1 -> deadbeef"
)
COVERED="$BASE/l1covered"
: >"$COVERED"
L1_FAIL=0
for row in "${L1_TABLE[@]}"; do
    IFS='|' read -r verb tmpl needle <<<"$row"
    echo "$verb" >>"$COVERED"
    read -ra FIREARGS <<<"${tmpl//@ME@/4c3e095a}"
    read -ra GOODARGS <<<"${tmpl//@ME@/deadbeef}"
    read -ra SHORTARGS <<<"${tmpl//@ME@/dead}"

    # FIRE: the exact literal from the incident, against this suite's own id.
    OUT=$(l1run "${FIREARGS[@]}")
    RC=$?
    if [[ "$RC" -ne 0 ]] && grep -qF "identity mismatch" <<<"$OUT" &&
        grep -qF "deadbeef" <<<"$OUT"; then
        pass "184 FIRE $verb: a foreign <me> is refused, naming the real session"
    else
        fail "184 FIRE $verb: accepted a foreign <me> (rc=$RC): ${OUT:0:200}"
        L1_FAIL=$((L1_FAIL + 1))
    fi

    # CONTROL A: one planted fact changed -- the prefix -- and the effect lands.
    OUT=$(l1run "${GOODARGS[@]}")
    RC=$?
    if [[ "$RC" -eq 0 ]] && { [[ -z "$needle" ]] || grep -qF "$needle" <<<"$OUT"; }; then
        pass "184 CONTROL A $verb: this session's own prefix works, effect included"
    else
        fail "184 CONTROL A $verb: the check broke the verb (rc=$RC, needle '$needle'): ${OUT:0:200}"
        L1_FAIL=$((L1_FAIL + 1))
    fi

    # CONTROL B: the instrument BLIND. No id anywhere, so the check cannot know
    # and must say nothing -- and the FIRE command then succeeds, which is what
    # proves FIRE was the check firing rather than the command failing anyway.
    OUT=$(env -u CLAUDE_CODE_SESSION_ID -u WORKLIST_SESSION_ID bash -c '
        printf "%s" "$1"; shift
        TMPDIR="$2/tmp" CLAUDE_PROJECT_DIR="$2/proj" WORKLIST_JUDGE=off \
            python3 "$3" "${@:4}" 2>&1' _ "" "$STATE_BODY" "$BASE" "$HOOK" "${FIREARGS[@]}" </dev/null)
    if ! grep -qF "identity mismatch" <<<"$OUT"; then
        pass "184 CONTROL B $verb: an unresolvable environment accuses nobody"
    else
        fail "184 CONTROL B $verb: accused a caller it could not verify: ${OUT:0:200}"
        L1_FAIL=$((L1_FAIL + 1))
    fi

    # CONTROL C: the length floor, generalised from --poll's. `dead` IS a prefix
    # of this session's id, so only the floor can refuse it -- which is the
    # whole point: same_session's symmetry would have accepted `--add d`.
    OUT=$(l1run "${SHORTARGS[@]}")
    RC=$?
    if [[ "$RC" -ne 0 ]]; then
        pass "184 CONTROL C $verb: a promiscuously short prefix is refused"
    else
        fail "184 CONTROL C $verb: accepted a 4-char <me>: ${OUT:0:200}"
        L1_FAIL=$((L1_FAIL + 1))
    fi
done
# --poll's effect is a FILE, not a line: an empty inbox prints nothing by
# contract, so CONTROL A above can only check the exit code for it.
if [[ -f "${WL%.md}.pollmark-deadbeef" ]]; then
    pass "184 CONTROL A --poll: the marker was actually written"
else
    fail "184 CONTROL A --poll: exit 0 but no marker; the verb did nothing"
fi

echo "== 184w. --wait is on the same rule, and it is the one that BLOCKS on the answer =="
# Separate because it is a different entry point (wl_wait.py, not worklist.py)
# and because getting it wrong is expensive in a way the others are not: a
# waiter armed against the wrong slice blocks for MINUTES on an inbox that is
# not its own, then reports nothing new.
WAITBIN="$(dirname "$HOOK")/wl_wait.py"
OUT=$(TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" \
    python3 "$WAITBIN" 4c3e095a --timeout 0.02 2>&1)
RC=$?
echo "--wait" >>"$COVERED"
if [[ "$RC" -ne 0 ]] && grep -qF "identity mismatch" <<<"$OUT"; then
    pass "184w FIRE: the waiter refuses to listen as another session"
else
    fail "184w FIRE: the waiter armed against a foreign identity (rc=$RC): ${OUT:0:200}"
fi
OUT=$(TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" \
    python3 "$WAITBIN" deadbeef --timeout 0.02 2>&1)
RC=$?
# The heartbeat is UNLINKED on a clean timeout exit (wl_wait.py:202), so the
# effect to assert is the report line naming the session it actually listened
# for -- a waiter armed against the wrong slice would name that one.
if [[ "$RC" -eq 0 ]] && grep -qF "nothing new for deadbeef" <<<"$OUT"; then
    pass "184w CONTROL A: its own prefix waits, and listens on its OWN inbox"
else
    fail "184w CONTROL A: the check broke the waiter (rc=$RC): ${OUT:0:200}"
fi

echo "== 185. ANTI-VACUITY: the verb list is DERIVED from the source, not typed here =="
# THE MOST IMPORTANT CASE IN THIS CHANGE. The defect's shape is "a rule applied
# to some call sites and not others", so a hand-written table is the same bug
# one layer up: add verb 14 next month, forget the table, and the suite stays
# green over a reopened hole. So the verb list comes from worklist.py's OWN
# dispatch, and every me-taking verb must have been DRIVEN above -- proven by
# the coverage file the loop wrote at runtime, not by grepping this file, which
# would pass on a case that never ran.
OUT=$(
    python3 - "$(dirname "$HOOK")" "$COVERED" <<'PYEOF'
import pathlib, re, sys
d = pathlib.Path(sys.argv[1])
src = (d / "worklist.py").read_text(encoding="utf-8")
verbs = set()
verbs.update(re.findall(r'sys\.argv\[1:2\] == \["(--[a-z-]+)"\]', src))
verbs.update(re.findall(r'sys\.argv\[1\] == "(--[a-z-]+)"', src))
for tup in re.findall(r'sys\.argv\[1\] in \(([^)]*)\)', src):
    verbs.update(re.findall(r'"(--?[a-z-]+)"', tup))
# Verbs that take NO <me>, each for a stated reason. Adding to this list is a
# deliberate act; forgetting to add a NEW me-taking verb is not, which is the
# asymmetry that makes this check work.
NO_ME = {
    "--help", "-h", "help",   # prints the catalogue
    "--path", "--compact",    # store-level queries, no identity
    "--requests",             # unfiltered listing of everybody's requests
    "--session-start", "--post-compact",  # harness hooks; identity is in the event
    "--reports",              # a CONTAINER: its me-taking sub-modes are driven
                              # explicitly as `--reports --read` and
                              # `--reports --list --as`, and it is recorded
                              # covered by both.
}
covered = {ln.strip() for ln in pathlib.Path(sys.argv[2]).read_text().splitlines() if ln.strip()}
# The derivation's own control. An empty or broken regex would produce an empty
# `verbs` and this whole case would pass by finding nothing to check -- exactly
# the can't-fail shape it exists to prevent.
if not {"--add", "--tick", "--ask", "--poll", "--state", "--brief"} <= verbs:
    print("DERIVATION BROKEN: the dispatch scan found %s" % sorted(verbs))
    sys.exit(1)
gap = sorted((verbs - NO_ME) - covered)
if gap:
    print("UNCOVERED me-taking verb(s), add a row to L1_TABLE: %s" % gap)
    sys.exit(1)
print("derived=%d covered=%d" % (len(verbs - NO_ME), len(covered)))
PYEOF
)
if [[ $? -eq 0 ]]; then
    pass "185: every verb the dispatch offers with a <me> was actually driven ($OUT)"
else
    fail "185: $OUT"
fi

echo "== 186. META-CONTROL: the ambient scrub at the top of this file really happened =="
# A CHECK ON A CHECK, and it is not redundant. Everything above depends on
# WORKLIST_SESSION_ID being the ONLY identity in the environment. If the scrub
# at line 16 ever stops stripping CLAUDE_CODE_SESSION_ID, this suite splits in
# two: run from inside a Claude session every fixture prefix mismatches and ~110
# sites refuse, and run in CI the variable is unset, check_me silently passes,
# and every identity case above passes VACUOUSLY. The second is the dangerous
# one, because it is green.
#
# The probe: unset WORKLIST_SESSION_ID ONLY, then issue a command that would
# FIRE against any real session id, and require it to PASS. It can only pass if
# there is no ambient id left to compare against.
OUT=$(env -u WORKLIST_SESSION_ID bash -c '
    TMPDIR="$1/tmp" CLAUDE_PROJECT_DIR="$1/proj" \
        python3 "$2" --add 4c3e095a scrub-probe 2>&1' _ "$BASE" "$HOOK" </dev/null)
RC=$?
if [[ "$RC" -eq 0 ]] && ! grep -qF "identity mismatch" <<<"$OUT"; then
    pass "186: no ambient CLAUDE_CODE_SESSION_ID survives the scrub"
else
    fail "186: an ambient session id leaked past the scrub, so case 184 is measuring the SHELL, not the check: ${OUT:0:200}"
fi
# CONTROL: force one back in and the same command must FIRE. Without this,
# case 186 is satisfied by a check that never runs at all.
OUT=$(CLAUDE_CODE_SESSION_ID="beef0000-9999-8888-7777-666666666666" \
    env -u WORKLIST_SESSION_ID bash -c '
    TMPDIR="$1/tmp" CLAUDE_PROJECT_DIR="$1/proj" \
        python3 "$2" --add 4c3e095a scrub-probe 2>&1' _ "$BASE" "$HOOK" </dev/null)
RC=$?
if [[ "$RC" -ne 0 ]] && grep -qF "beef0000" <<<"$OUT"; then
    pass "186 CONTROL: with an ambient id present the same command FIRES, so 186 measures something"
else
    fail "186 CONTROL: CLAUDE_CODE_SESSION_ID is not read at all (rc=$RC): ${OUT:0:200}"
fi

echo "== 184x. a SHORT <me> that exactly matches an explicit declaration is honoured =="
# REGRESSION, from a defect the floor itself caused (26d7814c5). Legacy
# sub-agents tagged items with their NAME rather than a session prefix, and
# `w2s-en` is 6 characters. The floor refused it even WITH the override
# declared, and the refusal then advised "rerun with <me>=w2s-en" -- the exact
# value it had just rejected. An instruction to retry the thing it refused
# leaves no next move: the listing path was closed, so the only way to see
# those items was to reassign them BLIND, which is the opposite of
# inspect-then-decide. A capability reachable only by acting blind is not
# reachable.
#
# The floor guards against an UNDER-SPECIFIED GUESS about self. An exact match
# to an explicit declaration is not a guess, so it is honoured -- and the three
# controls below are what keep that from being a loophole.
#
# PLACED HERE, not beside case 184, deliberately: setup() does `rm -rf $BASE`,
# which would wipe the coverage file case 185 reads. Do not move it up.
setup
OUT=$(TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" WORKLIST_SESSION_ID=w2s-en \
    python3 "$HOOK" --add w2s-en "a legacy agent-named item" 2>&1)
RC=$?
if [[ "$RC" -eq 0 ]] && grep -qF "added #" <<<"$OUT"; then
    pass "184x FIRE: a 6-char <me> matching its declaration exactly is accepted"
else
    fail "184x FIRE: the floor still refuses a declared short identity (rc=$RC): ${OUT:0:200}"
fi
# ...and the path that was actually closed: READING before deciding ownership.
OUT=$(TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" WORKLIST_SESSION_ID=w2s-en \
    python3 "$HOOK" --list --open w2s-en 2>&1)
if [[ $? -eq 0 ]] && grep -qF "a legacy agent-named item" <<<"$OUT"; then
    pass "184x FIRE: its items can be INSPECTED, so ownership is a decision and not a gamble"
else
    fail "184x FIRE: the listing path is still closed: ${OUT:0:200}"
fi
# CONTROL A: one planted fact -- no declaration at all. This is the case the
# floor was built for, and it must still refuse.
OUT=$(TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" \
    CLAUDE_CODE_SESSION_ID=w2s-en-1111-2222 python3 "$HOOK" --add w2s-en "x" 2>&1)
RC=$?
if [[ "$RC" -ne 0 ]] && grep -qF "shorter than 8 characters" <<<"$OUT"; then
    pass "184x CONTROL A: a bare short <me> with no declaration is still refused"
else
    fail "184x CONTROL A: the escape swallowed the whole floor (rc=$RC): ${OUT:0:200}"
fi
# CONTROL B: a declaration that does not EXACTLY match. A prefix relationship is
# not enough -- that is what makes this an exact-match rule rather than a second
# way to express the guess the floor exists to refuse.
OUT=$(TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" \
    WORKLIST_SESSION_ID=w2s-en-1111-2222 python3 "$HOOK" --add w2s-en "x" 2>&1)
RC=$?
if [[ "$RC" -ne 0 ]] && grep -qF "shorter than 8 characters" <<<"$OUT"; then
    pass "184x CONTROL B: a declaration the value merely prefixes is not an exact match"
else
    fail "184x CONTROL B: near-enough counted as exact (rc=$RC): ${OUT:0:200}"
fi
# CONTROL C: THE PROPERTY THAT MAKES THE ESCAPE SAFE, and nothing else asserts
# it. --poll and --wait key SIDECAR FILENAMES off <me>[:8], so a short prefix
# there names a different marker than the Stop hook derives from the full
# session id and silently disables the fast path. Those two carry their own
# floor, ahead of check_me, and the escape must not reach them.
OUT=$(TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" WORKLIST_SESSION_ID=w2s-en \
    python3 "$HOOK" --poll w2s-en 2>&1)
RC=$?
if [[ "$RC" -ne 0 ]] && grep -qF "8-char" <<<"$OUT"; then
    pass "184x CONTROL C: --poll keeps its own floor; the escape does not reach the sidecar verbs"
else
    fail "184x CONTROL C: a declared short prefix reached the poll marker (rc=$RC): ${OUT:0:200}"
fi
OUT=$(TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" WORKLIST_SESSION_ID=w2s-en \
    python3 "$(dirname "$HOOK")/wl_wait.py" w2s-en --timeout 0.01 2>&1)
RC=$?
if [[ "$RC" -ne 0 ]] && grep -qF "8-char" <<<"$OUT"; then
    pass "184x CONTROL C: --wait keeps its own floor too"
else
    fail "184x CONTROL C: a declared short prefix armed the waiter (rc=$RC): ${OUT:0:200}"
fi

echo "== 187. --ask refuses a recipient that has never briefed here =="
# The same defect from the SENDER'S side, and it cost the same incident 34
# hours: peers addressed `4c3e095a`, an identity that never existed, and the
# request sat until it auto-escalated with "recipient silent for 2062min".
setup
brief_now
brief_other cafe1234
OUT=$(reqcli --ask deadbeef 4c3e095a "into the void" 2>&1)
RC=$?
if [[ "$RC" -ne 0 ]] && grep -qF "has never briefed" <<<"$OUT" && grep -qF "cafe1234" <<<"$OUT"; then
    pass "187 FIRE: an ask to a never-briefed prefix is refused, listing who is real"
else
    fail "187 FIRE: posted into an inbox nobody reads (rc=$RC): ${OUT:0:200}"
fi
# CONTROL A: one planted fact -- the recipient HAS briefed.
OUT=$(reqcli --ask deadbeef cafe1234 "a real recipient" 2>&1)
if [[ $? -eq 0 ]] && grep -qF "request #" <<<"$OUT"; then
    pass "187 CONTROL A: a briefed recipient is accepted"
else
    fail "187 CONTROL A: the check refused a real session: ${OUT:0:200}"
fi
# CONTROL B: '*' and 'operator' are not roster entries and never will be.
if reqcli --ask deadbeef '*' "broadcast" >/dev/null 2>&1 &&
    reqcli --ask deadbeef operator "a question DEFAULT: proceed as planned" >/dev/null 2>&1; then
    pass "187 CONTROL B: '*' and 'operator' bypass the roster check"
else
    fail "187 CONTROL B: the roster check swallowed a broadcast or an operator ask"
fi
# CONTROL C: the INSTRUMENT BLIND. An empty roster means the check has no data
# -- a fresh worktree, a wiped TMPDIR -- and refusing every ask there would
# break the mechanism exactly where nothing is wrong.
setup
OUT=$(reqcli --ask deadbeef nobody99 "no roster at all" 2>&1)
if [[ $? -eq 0 ]] && grep -qF "request #" <<<"$OUT"; then
    pass "187 CONTROL C: with an EMPTY roster the check abstains instead of refusing everything"
else
    fail "187 CONTROL C: an empty roster refused every ask: ${OUT:0:200}"
fi

echo "== 188. 'operator' is exempt, and the exemption is narrow =="
# wl_email mails the HUMAN `worklist.py --answer operator <id> '<words>'`. They
# run it in whatever shell is open, and if that is a Claude session's Bash the
# identity check would refuse the one command the mail exists to get run.
# "operator" is a name, not a session prefix, and was never verifiable.
setup
brief_now
brief_other cafe1234
RID=$(askid_as cafe1234 deadbeef "for the operator to answer")
OUT=$(reqcli --answer operator "$RID" "the human's answer" 2>&1)
if [[ $? -eq 0 ]] && grep -qF "answered #" <<<"$OUT"; then
    pass "188: the operator's mailed reply command still works inside a session"
else
    fail "188: the identity check broke the operator's reply path: ${OUT:0:200}"
fi
# CONTROL: the exemption is ONE literal, not "any non-session word".
OUT=$(reqcli --answer operator2 "$RID" "an impostor" 2>&1)
if [[ $? -ne 0 ]] && grep -qF "identity mismatch" <<<"$OUT"; then
    pass "188 CONTROL: a lookalike is not exempt"
else
    fail "188 CONTROL: the exemption is wider than one literal: ${OUT:0:200}"
fi

echo "== 189. v19 L2: an identity that WRITES here and has never stopped is reported =="
# The backstop for what L1 cannot reach: history already written, and the
# deliberate silent-pass where the environment cannot name the caller. The
# signature is exact and binary -- `.lastevent-<prefix>.json` is written at
# exactly ONE place (run_stop), so no file means no Stop hook has ever run under
# that identity, and a real session always stops.
setup
brief_now
hand_now
say "all done, nothing outstanding"
run >/dev/null # one real stop, so a .lastevent-deadbeef.json exists
phantom_store phantom1 90
newturn
say "all done, nothing outstanding"
OUT="$(run)"
if grep -qF "PHANTOM IDENTITY IN THE STORE" <<<"$OUT" && grep -qF "phantom1" <<<"$OUT" &&
    grep -qF -- "--reassign deadbeef" <<<"$OUT"; then
    pass "189 FIRE: the phantom is named, with the exact repair verb"
else
    fail "189 FIRE: no phantom section: ${OUT:0:400}"
fi
if ! grep -qF '"decision": "block"' <<<"$OUT"; then
    pass "189: it is REPORT-ONLY and never blocks"
else
    fail "189: the phantom report blocked a stop it is not this session's job to fix"
fi

echo "== 189a. CONTROL: a .lastevent- file means it DID stop, so it is a real session =="
setup
brief_now
hand_now
say "all done, nothing outstanding"
run >/dev/null
phantom_store phantom1 90
printf '{"session_id":"phantom1-x"}' >"${WL%.md}.lastevent-phantom1.json"
newturn
say "all done, nothing outstanding"
OUT="$(run)"
if ! grep -qF "PHANTOM IDENTITY" <<<"$OUT"; then
    pass "189a CONTROL: one planted fact -- the .lastevent- file -- and it goes silent"
else
    fail "189a CONTROL: flagged an identity that has stopped: ${OUT:0:300}"
fi

echo "== 189b. CONTROL: a brand-new session writes before its first stop =="
setup
brief_now
hand_now
say "all done, nothing outstanding"
run >/dev/null
phantom_store phantom1 2 # younger than WORKLIST_PHANTOM_MIN (30)
newturn
say "all done, nothing outstanding"
OUT="$(run)"
if ! grep -qF "PHANTOM IDENTITY" <<<"$OUT"; then
    pass "189b CONTROL: a 2-minute-old writer is not yet a phantom"
else
    fail "189b CONTROL: accused a session that has not had time to stop: ${OUT:0:300}"
fi

echo "== 189c. CONTROL: a phantom that owns NOTHING is not worth a word =="
# This is the gate that keeps `state-spotchk1`/`state-spotchk2` -- real test
# residue in the operator's live store -- silent.
setup
brief_now
hand_now
say "all done, nothing outstanding"
run >/dev/null
phantom_store phantom1 90
# tick every phantom-owned item: it still WROTE the events, it just owns nothing open
python3 - "${WL%.md}.events.jsonl" <<'PYEOF'
import json, sys
path = sys.argv[1]
ids = [json.loads(l)["id"] for l in open(path) if l.strip()
       and json.loads(l).get("by") == "phantom1"]
with open(path, "a", encoding="utf-8") as fh:
    for i in ids:
        fh.write(json.dumps({"ev": "state", "id": i, "at": "2026-08-05T00:00:00Z",
                             "by": "phantom1", "s": "x", "note": "done"}) + "\n")
PYEOF
newturn
say "all done, nothing outstanding"
OUT="$(run)"
if ! grep -qF "PHANTOM IDENTITY" <<<"$OUT"; then
    pass "189c CONTROL: a phantom owning no open work stays silent"
else
    fail "189c CONTROL: flagged an identity with nothing outstanding: ${OUT:0:300}"
fi

echo "== 189d. CONTROL: with ZERO .lastevent- files the check says it is BLIND =="
# Asserting silence here would be indistinguishable from the check not running.
# With no .lastevent-* anywhere the signature cannot discriminate -- it
# recognises a phantom by the ABSENCE of one -- and it would indict every
# identity at once, so it must report the blindness in words and flag nobody.
#
# DRIVEN AS A LIBRARY CALL, not through a Stop event, and that is a real fact
# about the code rather than test convenience: run_stop writes its OWN
# .lastevent-<me8>.json before this check runs, so on the Stop path the set is
# never empty. The branch guards a store where that write FAILED (an unwritable
# TMPDIR) and any future caller that has not just written one. 189e is its
# control: same call, one file present, and the phantom is named.
setup
brief_now
hand_now
phantom_store phantom1 90
rm -f "${WL%.md}".lastevent-*.json
probe_phantom() { # probe_phantom -> "BLIND: <reason>" or "FLAGGED: <prefixes>"
    TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" python3 - "$(dirname "$HOOK")" "$WL" <<'PYEOF'
import pathlib, sys
sys.path.insert(0, sys.argv[1])
import wl_checks as CK, wl_store as S, wl_requests as R
wl = pathlib.Path(sys.argv[2])
found, blind = CK.phantom_identities(wl, "deadbeef-1111-2222-3333-444444444444",
                                     S.load(wl, sync=False), R.read_requests(wl))
print("BLIND: %s" % blind if blind else "FLAGGED: %s" % ",".join(f[0] for f in found))
PYEOF
}
OUT=$(probe_phantom)
if [[ "$OUT" == BLIND:* ]] && grep -qF "is BLIND this stop" <<<"$OUT"; then
    pass "189d CONTROL: blindness is stated out loud, and nobody is accused"
else
    fail "189d CONTROL: a blind check answered anyway: ${OUT:0:300}"
fi

echo "== 189e. CONTROL for 189d: one .lastevent- file and the same call FLAGS =="
# Without this, 189d is satisfied by a function that never looks at anything.
printf '{"session_id":"deadbeef-x"}' >"${WL%.md}.lastevent-deadbeef.json"
OUT=$(probe_phantom)
if [[ "$OUT" == "FLAGGED: phantom1" ]]; then
    pass "189e CONTROL: one planted file, and the blindness turns into a verdict"
else
    fail "189e CONTROL: the probe cannot flag at all, so 189d proves nothing: ${OUT:0:300}"
fi

echo "== 190. v19 L3: --reassign moves the OPEN work and leaves the history alone =="
# BEFORE AND AFTER in one run. The before-assert is the control: without it the
# test passes on a store that already contained the item and the request.
setup
brief_now
hand_now
say "all done, nothing outstanding"
run >/dev/null
phantom_store phantom1 90
# a request the phantom sent, and one sent TO it -- the incident's real damage
# was in .requests, so a repair that leaves those unreachable fixes the symptom
# nobody complained about and skips the one they did
brief_other phantom1
askid_as phantom1 deadbeef "the message that was lost" >/dev/null
brief_other cafe1234
PRID_TO=$(askid_as cafe1234 phantom1 "a question nobody read")
BEFORE_LIST=$(reqcli --list --open deadbeef 2>&1)
BEFORE_POLL=$(reqcli --poll deadbeef 2>&1)
if ! grep -qF "phantom-owned item" <<<"$BEFORE_LIST" && ! grep -qF "$PRID_TO" <<<"$BEFORE_POLL"; then
    pass "190 BEFORE: neither the items nor the unread request are visible to deadbeef"
else
    fail "190 BEFORE: the fixture already showed them, so the after-assert proves nothing"
fi
OUT=$(reqcli --reassign deadbeef phantom1 2>&1)
RC=$?
if [[ "$RC" -eq 0 ]] && grep -qF "reassigned phantom1 -> deadbeef" <<<"$OUT"; then
    pass "190: --reassign reports what it moved"
else
    fail "190: --reassign failed (rc=$RC): ${OUT:0:300}"
fi
AFTER_LIST=$(reqcli --list --open deadbeef 2>&1)
AFTER_POLL=$(reqcli --poll deadbeef 2>&1)
if grep -qF "phantom-owned item" <<<"$AFTER_LIST"; then
    pass "190 AFTER: the phantom's open items are now in this session's slice"
else
    fail "190 AFTER: the items did not move: ${AFTER_LIST:0:300}"
fi
if grep -qF "$PRID_TO" <<<"$AFTER_POLL"; then
    pass "190 AFTER: the request nobody was reading is now in this session's inbox"
else
    fail "190 AFTER: the lost request is still unreachable: ${AFTER_POLL:0:300}"
fi
# The history must still say the phantom wrote them. A tidy log that lies about
# who did what is worse than an untidy one.
if grep -q '"by": *"phantom1"' "${WL%.md}.events.jsonl" ||
    grep -q '"by":"phantom1"' "${WL%.md}.events.jsonl"; then
    pass "190: the event log still records phantom1 as the writer"
else
    fail "190: --reassign rewrote history instead of appending to it"
fi

echo "== 190b. CONTROL: --reassign refuses a peer that is FRESH but has never stopped =="
# THE REVIEW FINDING THIS PINS (medium, PR #551). The `.lastevent-` guard alone
# does not deliver the guarantee the docstring claims. That file is written at a
# session's FIRST STOP, so a peer that has added items and not yet stopped has
# no file either and is indistinguishable from a genuine phantom. Any session can
# read a peer's prefix out of `--list --open`, and concurrent sessions in one
# tree are routine here, so without an age gate a peer's OPEN items and request
# routing could be moved onto the caller WHILE that peer was working on them.
#
# Case 190 (the FIRE) ages its target 90 minutes and 190a's target has already
# stopped; NEITHER covers a merely-fresh, still-working target, so the untested
# path was the vulnerable one.
setup
brief_now
hand_now
say "all done, nothing outstanding"
run >/dev/null
# 2 minutes old and NO .lastevent- file: exactly the mid-first-turn peer.
phantom_store fresh999 2
OUT=$(reqcli --reassign deadbeef fresh999 2>&1)
RC=$?
if [[ "$RC" -ne 0 ]] && grep -qF "mid-turn" <<<"$OUT"; then
    pass "190b CONTROL: a fresh peer that never stopped cannot be harvested"
else
    fail "190b CONTROL: took over a live peer's work (rc=$RC): ${OUT:0:300}"
fi
# CONTROL ON THE CONTROL: the SAME prefix, aged past the floor, still moves --
# so 190b proves an age gate and not a blanket refusal.
setup
brief_now
hand_now
say "all done, nothing outstanding"
run >/dev/null
phantom_store fresh999 90
OUT=$(reqcli --reassign deadbeef fresh999 2>&1)
RC=$?
if [[ "$RC" -eq 0 ]] && grep -qF "reassigned fresh999" <<<"$OUT"; then
    pass "190b CONTROL: the same prefix aged past the floor still reassigns"
else
    fail "190b CONTROL: the age gate refuses even a real phantom (rc=$RC): ${OUT:0:300}"
fi

echo "== 190c. --lease <id> release accepts the # this tool's own output prints =="
# REVIEW FINDING, PR #551: the release branch read argv[2] raw while every other
# verb goes through the .lstrip("#") at the top of _item_cli. So an id copied
# straight from this tool's OWN output -- it prints ids as `#abc123` -- appended
# an unlease event matching nothing, printed "released ##abc123", and left the
# item [>]. A verb that reports success while changing nothing is precisely what
# this suite exists to catch, and it shipped inside the fix for a different
# silent no-op.
setup
brief_now
hand_now
say "all done, nothing outstanding"
run >/dev/null
RID=$(reqcli --add deadbeef "item for the hash-prefix release case" | grep -oE "#[0-9a-f]+" | head -1 | tr -d '#')
reqcli --lease deadbeef "$RID" +30 worker:probe-worker "riding a probe" >/dev/null 2>&1
OUT=$(reqcli --lease deadbeef "#$RID" release "released with the hash form" 2>&1)
if grep -qF "released #$RID" <<<"$OUT" && ! grep -qF "##$RID" <<<"$OUT"; then
    pass "190c FIRE: the # form is accepted and echoed back singly"
else
    fail "190c FIRE: the # form was mangled: ${OUT:0:200}"
fi
STATE=$(reqcli --list --open deadbeef 2>&1 | grep -oE "\- \[.\] #$RID" | head -1)
if [[ "$STATE" == "- [ ] #$RID" ]]; then
    pass "190c FIRE: the item actually returned to open, not just a success message"
else
    fail "190c FIRE: reported success but the state is '$STATE'"
fi
# CONTROL: the bare form must keep working, so the fix is a widening and not a swap.
reqcli --lease deadbeef "$RID" +30 worker:probe-worker "riding again" >/dev/null 2>&1
reqcli --lease deadbeef "$RID" release "released with the bare form" >/dev/null 2>&1
STATE=$(reqcli --list --open deadbeef 2>&1 | grep -oE "\- \[.\] #$RID" | head -1)
if [[ "$STATE" == "- [ ] #$RID" ]]; then
    pass "190c CONTROL: the bare id form still releases"
else
    fail "190c CONTROL: the bare form broke: '$STATE'"
fi

echo "== 190a. CONTROL: --reassign refuses a session that HAS stopped =="
# The rule that stops this verb becoming a way to steal a live peer's items.
setup
brief_now
hand_now
say "all done, nothing outstanding"
run >/dev/null
phantom_store cafe1234 90
printf '{"session_id":"cafe1234-x"}' >"${WL%.md}.lastevent-cafe1234.json"
OUT=$(reqcli --reassign deadbeef cafe1234 2>&1)
RC=$?
if [[ "$RC" -ne 0 ]] && grep -qF "it is a real session" <<<"$OUT"; then
    pass "190a CONTROL: a peer that has stopped cannot be harvested"
else
    fail "190a CONTROL: took over a live session's work (rc=$RC): ${OUT:0:300}"
fi
# And <me> itself faces the same identity check, so you cannot reassign TO a
# fiction and make the problem worse.
OUT=$(reqcli --reassign 4c3e095a phantom1 2>&1)
RC=$?
if [[ "$RC" -ne 0 ]] && grep -qF "identity mismatch" <<<"$OUT"; then
    pass "190a CONTROL: you cannot reassign work TO an identity you are not"
else
    fail "190a CONTROL: --reassign accepted a foreign <me> (rc=$RC): ${OUT:0:200}"
fi

echo "== 191. root resolution must not walk into a repo NESTED in the repo =="
# THE DEFECT, measured live on 2026-08-06: the Stop event's cwd is wherever the
# session last worked, and this tree holds repos INSIDE the repo -- submodules
# (private/renet) and gitignored non-submodule siblings (private/growth). Every
# root resolution started from that cwd, so project_root() stopped at the NESTED
# repo and the branch check read ITS branch: a session on 0804-1 was ordered to
# bootstrap .agent/main/ because private/growth happened to be on main.
#
# CONTROL FIRST, and it is the pre-fix expression itself rather than a mutation:
# if `event.cwd or getcwd()` does NOT resolve to the nested repo on this
# fixture, the fixture is not reproducing the bug and the FIRE below proves
# nothing.
setup
NESTBASE="$BASE/nesting"
rm -rf "$NESTBASE"
mkdir -p "$NESTBASE/outer/.claude/hooks/stop" "$NESTBASE/outer/nested"
: >"$NESTBASE/outer/.git" # a FILE, as a worktree or submodule writes it
: >"$NESTBASE/outer/nested/.git"
OUT=$(
    export CLAUDE_PROJECT_DIR="$NESTBASE/outer" HOOKDIR
    HOOKDIR="$(dirname "$HOOK")"
    export NESTBASE
    python3 - <<'PYEOF'
import os
import sys

sys.path.insert(0, os.environ["HOOKDIR"])
import wl_core as C

base = os.environ["NESTBASE"]
nested = os.path.join(base, "outer", "nested")
event = {"cwd": nested}
print("CONTROL", C.project_root(event.get("cwd") or os.getcwd()))
print("FIRE", C.project_root(C.project_start(event)))
# Rung 2: with no CLAUDE_PROJECT_DIR at all, a CLI run must anchor on the hook
# FILE's own repo, not on wherever the shell happens to be standing.
del os.environ["CLAUDE_PROJECT_DIR"]
os.chdir(nested)
print("CLI", C.project_start(), C.hook_repo_root())
PYEOF
)
if grep -qF "CONTROL $NESTBASE/outer/nested" <<<"$OUT"; then
    pass "191 CONTROL: the pre-fix ladder does resolve to the nested repo"
else
    fail "191 CONTROL: fixture does not reproduce the bug, so FIRE proves nothing: ${OUT:0:300}"
fi
if grep -qF "FIRE $NESTBASE/outer" <<<"$OUT" && ! grep -qF "FIRE $NESTBASE/outer/nested" <<<"$OUT"; then
    pass "191 FIRE: project_start anchors on the outer repo, not the nested one"
else
    fail "191 FIRE: still resolving into the nested repo: ${OUT:0:300}"
fi
CLI_LINE=$(grep "^CLI " <<<"$OUT")
CLI_START=$(awk '{print $2}' <<<"$CLI_LINE")
CLI_HOOK=$(awk '{print $3}' <<<"$CLI_LINE")
if [[ -n "$CLI_HOOK" && "$CLI_START" == "$CLI_HOOK" ]]; then
    pass "191 FIRE: with no CLAUDE_PROJECT_DIR the anchor is the hook file's repo"
else
    fail "191 FIRE: a CLI run still anchors on cwd (start=$CLI_START hook=$CLI_HOOK)"
fi
# The store path is the thing a wrong root DESTROYS: it is slugged from the
# root, so a root that moves orphans every open item in the old file. Pin it.
PATH_OUTER=$(TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$NESTBASE/outer" python3 "$HOOK" --path)
PATH_NESTED=$(cd "$NESTBASE/outer/nested" && TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$NESTBASE/outer" python3 "$HOOK" --path)
if [[ "$PATH_OUTER" == "$PATH_NESTED" ]]; then
    pass "191 FIRE: --path is identical from the outer repo and from inside the nested one"
else
    fail "191 FIRE: --path moved with cwd ($PATH_OUTER vs $PATH_NESTED)"
fi

# ---------------------------------------------------------------------------
# 192 an hourly poll cron parked off :00 is still a poll cron
#
# THE INCIDENT (2026-08-07): CronCreate tells every session to avoid the :00 and
# :30 marks so the fleet does not hit the API on one instant, and offers
# "hourly -> 7 * * * *" as its example. is_poll_cron knew the hourly rung only
# as `0 * * * *`, so a session obeying both instructions had its poll cron
# counted as a second WORK cron, and the next stop ordered it to CronDelete the
# cron the previous stop had ordered it to create.
#
# THE FIRST FIX WAS WRONG and this case exists to keep it wrong: widening the
# schedule regex to any `<minute> * * * *` took this harness from 1 failure to
# 168, because an hourly WORK cron is indistinguishable from an hourly poll by
# schedule alone. Hence the negative assertions below -- they are not padding,
# they are the guard rail that reverted change would trip.
OUT=$(
    cd "$(dirname "$HOOK")" && python3 - <<'PYEOF'
import sys
sys.path.insert(0, ".")
import wl_checks as W

POLL = {"schedule": "37 * * * *", "prompt": "run .claude/hooks/stop/worklist.py --poll d136ac61"}
WORK = {"schedule": "17 * * * *", "prompt": "pr-babysit HEARTBEAT: check CI, fix reds"}

checks = {
    "poll-offminute": W.is_poll_cron(POLL) is True,
    "work-hourly-not-poll": W.is_poll_cron(WORK) is False,
    "shape-still-sufficient": W.is_poll_cron({"schedule": "*/5 * * * *"}) is True,
    "shape-zero-still-works": W.is_poll_cron({"schedule": "0 * * * *"}) is True,
    "no-prompt-degrades": W.is_poll_cron({"schedule": "37 * * * *"}) is False,
    "daily-not-poll": W.is_poll_cron({"schedule": "0 9 * * *"}) is False,
}
bad = [k for k, v in checks.items() if not v]
print("CLASSIFY", "OK" if not bad else "BAD:" + ",".join(bad))
print("CANON", W.canonical_poll_schedule("37 * * * *"))
print("TIP", repr(W.poll_backoff_tip([POLL], 9999, False)))
PYEOF
)
if grep -q "^CLASSIFY OK$" <<<"$OUT"; then
    pass "192: an off-minute hourly POLL is recognised; an hourly WORK cron still is not"
else
    fail "192: poll-cron classification wrong: $(grep '^CLASSIFY' <<<"$OUT")"
fi
if grep -q "^CANON 0 \* \* \* \*$" <<<"$OUT"; then
    pass "192: an off-minute hourly poll canonicalises onto the ladder's top rung"
else
    fail "192: canonical_poll_schedule did not map :37 to the hourly rung: ${OUT:0:200}"
fi
if grep -q "^TIP ''$" <<<"$OUT"; then
    pass "192: the backoff ladder treats an off-minute hourly poll as capped, not unknown"
else
    fail "192: poll_backoff_tip mis-handled an off-minute hourly poll: $(grep '^TIP' <<<"$OUT")"
fi

# ---------------------------------------------------------------------------
# 193-203 v20: the /handoff checklist gate (docs/<slug>/CHECKLIST.md).
#
# THE GAP THESE PIN: /handoff wrote a design suite and then TOLD the next
# session, in prose inside PROMPT.md, to seed the worklist. Prose gates
# nothing, so a handoff whose PROMPT.md was ignored or compacted away dropped
# program work silently. CHECKLIST.md is the machine-readable half, and its
# two halves are enforced by DIFFERENT means: deliverables are FILE-VERIFIED
# (the tick is bookkeeping, the file is the truth) while waves are
# tick-on-trust with store linkage through the `cl:<slug>/<wN>` token. Every
# case below is paired with a clean-fixture control, because a gate nobody has
# watched stay silent is a gate nobody knows fires for the right reason.

clfile() { # clfile <slug>  -- body on stdin, written to docs/<slug>/CHECKLIST.md
    mkdir -p "$BASE/proj/docs/$1"
    cat >"$BASE/proj/docs/$1/CHECKLIST.md"
}

cldeliver() { # cldeliver <relpath> [content] -- a deliverable file under the repo
    mkdir -p "$BASE/proj/$(dirname "$1")"
    printf '%s' "${2-x}" >"$BASE/proj/$1"
}

echo "== 193. ZERO OVERHEAD: a repo with no checklist never hears the word =="
# The cost claim in wl_checklist's docstring is that a repo keeping no
# handoffs pays one glob and says nothing. That is only half a control: a
# silent gate and a dead gate look identical from here, so the second leg
# plants one checklist into the SAME fixture and demands the words appear.
setup
say "done for now"
brief_now
hand_now
OUT="$(run)"
if ! grep -qi "handoff" <<<"$OUT" && ! grep -qF "CHECKLIST" <<<"$OUT"; then
    pass "193: no docs/<slug>/CHECKLIST.md means not one word about handoffs"
else
    fail "193: the gate talked about checklists that do not exist: ${OUT:0:300}"
fi
clfile demo <<'MD'
# Handoff checklist: demo
Status: producing
Owner: deadbeef

## Deliverables
- [ ] d1 file:docs/demo/README.md

## Waves
- [ ] w1 Wave A: wire the thing
MD
OUT="$(run)"
if grep -qF "docs/demo/CHECKLIST.md" <<<"$OUT" && grep -qi "handoff" <<<"$OUT"; then
    pass "193 CONTROL-FOR-THE-CONTROL: one planted checklist and the same fixture speaks"
else
    fail "193 CONTROL: the silence above was a DEAD gate, not a cheap one: ${OUT:0:300}"
fi

echo "== 194. producing + a missing deliverable blocks its OWNER =="
setup
say "done for now"
brief_now
hand_now
clfile demo <<'MD'
# Handoff checklist: demo
Status: producing
Owner: deadbeef

## Deliverables
- [ ] d1 file:docs/demo/README.md

## Waves
- [ ] w1 Wave A: wire the thing
MD
OUT="$(run)"
if grep -qF "DO NOT VERIFY" <<<"$OUT" && grep -qF "d1 docs/demo/README.md -- MISSING" <<<"$OUT"; then
    pass "194: the producing owner is blocked, and the row names the file and the verdict"
else
    fail "194: the producing block did not name the missing deliverable: ${OUT:0:400}"
fi
check "194: and the decision is block, not a note on an allowed stop" block "0 of 1 are present"

echo "== 194b. producing + everything verified: ONE step left, and it is the flip =="
cldeliver docs/demo/README.md "the readme"
OUT="$(run)"
if grep -qF "ONE step remains and it is the flip" <<<"$OUT" &&
    grep -qF "'Status: producing' to 'Status: executing'" <<<"$OUT" &&
    ! grep -qF "DO NOT VERIFY" <<<"$OUT"; then
    pass "194b: a verified producing checklist demands the status flip, nothing else"
else
    fail "194b: the flip demand is wrong: ${OUT:0:400}"
fi

echo "== 195. a FOREIGN producing checklist is reported, never blocked on =="
setup
say "done for now"
brief_now
hand_now
export WORKLIST_REPORT_PER_STOP=6
clfile demo <<'MD'
# Handoff checklist: demo
Status: producing
Owner: cafe0000

## Deliverables
- [ ] d1 file:docs/demo/README.md

## Waves
- [ ] w1 Wave A: wire the thing
MD
OUT="$(run)"
RC=$?
if [[ "$RC" -eq 0 ]] && ! grep -qF '"decision": "block"' <<<"$OUT" &&
    grep -qF "that session's to finish" <<<"$OUT"; then
    pass "195: another session's producing handoff rides the report and blocks nobody"
else
    fail "195: a foreign producing checklist was mis-adjudicated: ${OUT:0:400}"
fi
if ! grep -qF "adopt it by editing" <<<"$OUT"; then
    pass "195 CONTROL: a LIVE owner gets no adoption hint (that would be a land grab)"
else
    fail "195 CONTROL: the adoption hint fired on a live owner: ${OUT:0:400}"
fi

echo "== 195b. the same checklist, owner's transcript DEAD: adopt or supersede =="
# projects_dir is the transcript's own directory (wl_checks.py:1678), so an
# aged cafe0000*.jsonl beside the fixture transcript is exactly what
# owner_age_hours reads. Planted rather than mocked, for that reason.
touch -d '-48 hours' "$BASE/cafe0000-dead.jsonl"
OUT="$(run)"
if grep -qF "adopt it by editing the 'Owner:' line" <<<"$OUT" &&
    grep -qF "docs/demo/CHECKLIST.md" <<<"$OUT" && grep -qF "superseded" <<<"$OUT"; then
    pass "195b: a dead owner turns the advisory into an adoption offer"
else
    fail "195b: no adoption hint for an abandoned handoff: ${OUT:0:500}"
fi
unset WORKLIST_REPORT_PER_STOP

echo "== 196. TICKED but missing: the file is the truth, the tick is bookkeeping =="
# The wave is claimed by a peer rather than ticked, so the deliverable check
# is the ONLY thing that can speak here and the control below is a real allow
# instead of a different violation wearing the same fixture.
setup
say "done for now"
brief_now
hand_now
clfile demo <<'MD'
# Handoff checklist: demo
Status: executing

## Deliverables
- [x] d1 file:docs/demo/README.md

## Waves
- [ ] w1 Wave A: wire the thing
MD
as_peer cafe0000 reqcli --add cafe0000 "cl:demo/w1 Wave A: wire the thing" >/dev/null
OUT="$(run)"
if grep -qF "reality disagrees" <<<"$OUT" &&
    grep -qF "d1 docs/demo/README.md -- MISSING" <<<"$OUT"; then
    pass "196: a ticked box does not save a deliverable that is not on disk"
else
    fail "196: the ticked-but-missing deliverable passed: ${OUT:0:400}"
fi

echo "== 196b. EMPTY is not MISSING, and the row says which =="
cldeliver docs/demo/README.md ""
OUT="$(run)"
if grep -qF "d1 docs/demo/README.md -- EMPTY" <<<"$OUT" &&
    ! grep -qF -- "-- MISSING" <<<"$OUT"; then
    pass "196b: a 0-byte deliverable reads as EMPTY, distinctly from MISSING"
else
    fail "196b: the truncated deliverable was mis-named: ${OUT:0:400}"
fi
cldeliver docs/demo/README.md "the readme"
check "196b CONTROL: a non-empty file clears the check entirely" allow ""

echo "== 197. an UNCOVERED wave blocks, and carries its own one-command exit =="
setup
say "done for now"
brief_now
hand_now
cldeliver docs/demo/README.md "the readme"
clfile demo <<'MD'
# Handoff checklist: demo
Status: executing

## Deliverables
- [x] d1 file:docs/demo/README.md

## Waves
- [ ] w1 Wave A: wire the thing
MD
OUT="$(run)"
if grep -qF "w1 UNCOVERED" <<<"$OUT" && grep -qF "cl:demo/w1" <<<"$OUT" &&
    grep -qF -- "--add deadbeef 'cl:demo/w1 Wave A: wire the thing'" <<<"$OUT"; then
    pass "197: the uncovered wave names its token and the exact --add that claims it"
else
    fail "197: the uncovered wave has no runnable exit: ${OUT:0:500}"
fi

echo "== 197b. claiming it with --add moves the work into the ORDINARY open-items check =="
# DISJOINTNESS, not merely absence: the cl-waves needle must go while the
# open-item it created appears, because a gate that stopped firing AND took
# the work with it would look identical from a one-needle assertion.
reqcli --add deadbeef "cl:demo/w1 Wave A: wire the thing" >/dev/null
export WORKLIST_FOCUS=off
OUT="$(run)"
if ! grep -qF "UNCOVERED" <<<"$OUT" && grep -qF "OPEN worklist item" <<<"$OUT" &&
    grep -qF "cl:demo/w1" <<<"$OUT"; then
    pass "197b: a claimed wave stops blocking as a wave and starts blocking as an item"
else
    fail "197b: coverage either did not register or swallowed the work: ${OUT:0:500}"
fi
unset WORKLIST_FOCUS

echo "== 197c. a PEER's item covers the wave for everybody, which is the point =="
setup
say "done for now"
brief_now
hand_now
cldeliver docs/demo/README.md "the readme"
clfile demo <<'MD'
# Handoff checklist: demo
Status: executing

## Deliverables
- [x] d1 file:docs/demo/README.md

## Waves
- [ ] w1 Wave A: wire the thing
MD
as_peer cafe0000 reqcli --add cafe0000 "cl:demo/w1 Wave A: wire the thing" >/dev/null
OUT="$(run)"
RC=$?
if [[ "$RC" -eq 0 ]] && ! grep -qF "UNCOVERED" <<<"$OUT" && ! grep -qF '"decision": "block"' <<<"$OUT"; then
    pass "197c: once ANY session claims the wave, the redundant block on the others lifts"
else
    fail "197c: a peer-claimed wave still blocked this session: ${OUT:0:400}"
fi

echo "== 198. DONE-BUT-UNTICKED: the store settled it, the box did not =="
setup
say "done for now"
brief_now
hand_now
cldeliver docs/demo/README.md "the readme"
clfile demo <<'MD'
# Handoff checklist: demo
Status: executing

## Deliverables
- [x] d1 file:docs/demo/README.md

## Waves
- [ ] w1 Wave A: wire the thing
MD
IID=$(reqcli --add deadbeef "cl:demo/w1 Wave A: wire the thing" | grep -oE '#[0-9a-f]+' | tr -d '#')
reqcli --tick deadbeef "$IID" "wave A landed, suite run green, exit 0" >/dev/null
OUT="$(run)"
if grep -qF "w1 DONE-BUT-UNTICKED" <<<"$OUT" && grep -qF "#$IID" <<<"$OUT" &&
    grep -qF "tick '- [x] w1' in docs/demo/CHECKLIST.md" <<<"$OUT"; then
    pass "198: a ticked store item with an unticked box is called out with the box to tick"
else
    fail "198: the settled wave did not demand its tick: ${OUT:0:500}"
fi

echo "== 198c. a wave closed through a DOOR must NOT be told to tick its box =="
setup
say "done for now"
brief_now
hand_now
cldeliver docs/demo/README.md "the readme"
clfile demo <<'MD'
# Handoff checklist: demo
Status: executing

## Deliverables
- [x] d1 file:docs/demo/README.md

## Waves
- [ ] w1 Wave A: set the production secrets and cut over
MD
IID=$(reqcli --add deadbeef "cl:demo/w1 Wave A: set the production secrets and cut over" | grep -oE '#[0-9a-f]+' | tr -d '#')
reqcli --tick deadbeef "$IID" "door:operator-only - needs secrets no session holds; brief at docs/demo/RUNBOOK.md:12" >/dev/null
OUT="$(run)"
if ! grep -qF "w1 DONE-BUT-UNTICKED" <<<"$OUT"; then
    pass "198c: a door-closed wave is covered and correctly unticked, not demanded as done"
else
    fail "198c: the gate demanded a FALSE tick for work no session did: ${OUT:0:500}"
fi

echo "== 198d. control: the same wave WITHOUT a door still demands its tick =="
setup
say "done for now"
brief_now
hand_now
cldeliver docs/demo/README.md "the readme"
clfile demo <<'MD'
# Handoff checklist: demo
Status: executing

## Deliverables
- [x] d1 file:docs/demo/README.md

## Waves
- [ ] w1 Wave A: set the production secrets and cut over
MD
IID=$(reqcli --add deadbeef "cl:demo/w1 Wave A: set the production secrets and cut over" | grep -oE '#[0-9a-f]+' | tr -d '#')
reqcli --tick deadbeef "$IID" "cut over on host-1, verified, exit 0" >/dev/null
OUT="$(run)"
if grep -qF "w1 DONE-BUT-UNTICKED" <<<"$OUT"; then
    pass "198d: control fires -- 198c passes because of the door, not because the check went silent"
else
    fail "198d: the door exemption swallowed a genuinely settled wave: ${OUT:0:500}"
fi

echo "== 198b. every box ticked under 'executing' means the status is stale =="
clfile demo <<'MD'
# Handoff checklist: demo
Status: executing

## Deliverables
- [x] d1 file:docs/demo/README.md

## Waves
- [x] w1 Wave A: wire the thing
MD
OUT="$(run)"
if grep -qF "everything is settled; set 'Status: done'" <<<"$OUT"; then
    pass "198b: an all-settled executing checklist is asked for the last edit it needs"
else
    fail "198b: a finished program was left at executing forever: ${OUT:0:400}"
fi

echo "== 199. 'done' is INACTIVE, and is gated on being honestly done =="
setup
say "done for now"
brief_now
hand_now
cldeliver docs/demo/README.md "the readme"
clfile demo <<'MD'
# Handoff checklist: demo
Status: done

## Deliverables
- [x] d1 file:docs/demo/README.md

## Waves
- [x] w1 Wave A: wire the thing
MD
OUT="$(run)"
RC=$?
if [[ "$RC" -eq 0 ]] && ! grep -qF "CHECKLIST" <<<"$OUT" && ! grep -qF '"decision": "block"' <<<"$OUT"; then
    pass "199: a genuinely done handoff costs a later session nothing at all"
else
    fail "199: a done checklist is still talking: ${OUT:0:400}"
fi
clfile demo <<'MD'
# Handoff checklist: demo
Status: done

## Deliverables
- [x] d1 file:docs/demo/README.md

## Waves
- [ ] w1 Wave A: wire the thing
MD
OUT="$(run)"
if grep -qF "reality disagrees" <<<"$OUT" &&
    grep -qF "wave w1 is not ticked, yet the checklist claims done" <<<"$OUT"; then
    pass "199: 'done' with an unticked wave is a lie the next session would believe"
else
    fail "199: a dishonest done header passed: ${OUT:0:400}"
fi

echo "== 199b. 'superseded' is the terminal escape and adjudicates nothing =="
clfile demo <<'MD'
# Handoff checklist: demo
Status: superseded

## Deliverables
- [ ] d1 file:docs/demo/GONE.md

## Waves
- [ ] w1 Wave A: wire the thing
MD
OUT="$(run)"
RC=$?
if [[ "$RC" -eq 0 ]] && ! grep -qF "CHECKLIST" <<<"$OUT" && ! grep -qF '"decision": "block"' <<<"$OUT"; then
    pass "199b: an abandoned program stops costing anything the moment it says so"
else
    fail "199b: superseded still adjudicated: ${OUT:0:400}"
fi

echo "== 200. the SHAPE gate collects every defect, and scopes itself to the bad file =="
# One error per stop would cost one turn per typo, so the parser collects them
# all. The clean checklist alongside is the control: a malformed file must not
# smear its verdict over its neighbours.
setup
say "done for now"
brief_now
hand_now
cldeliver docs/good/README.md "the readme"
clfile good <<'MD'
# Handoff checklist: good
Status: done

## Deliverables
- [x] d1 file:docs/good/README.md

## Waves
- [x] w1 Wave A: the finished one
MD
clfile broken <<'MD'
# Handoff checklist: broken
Owner: deadbeef

## Deliverables
- [ ] d1 nothing verifies this one
- [ ] d1 file:docs/broken/README.md
- [ ] w9 a wave id under the deliverables

## Waves
- [z] w1 a state character that does not exist
MD
OUT="$(run)"
NROWS=0
for needle in "no 'Status:' line in the first 10 lines" \
    "does not belong under that section" \
    "carries no 'file:<path>' token" \
    "duplicate id 'd1'" \
    "not a checklist item"; do
    grep -qF "$needle" <<<"$OUT" && NROWS=$((NROWS + 1))
done
if grep -qF "is MALFORMED" <<<"$OUT" && [[ "$NROWS" -ge 3 ]]; then
    pass "200: the malformed checklist blocks and reports $NROWS defects in one pass"
else
    fail "200: shape diagnosis is thin (rows=$NROWS): ${OUT:0:600}"
fi
if grep -qF "docs/broken/CHECKLIST.md is MALFORMED" <<<"$OUT" &&
    ! grep -qF "docs/good/CHECKLIST.md" <<<"$OUT"; then
    pass "200 CONTROL: the clean checklist beside it is never mentioned"
else
    fail "200 CONTROL: the shape verdict smeared onto a healthy file: ${OUT:0:600}"
fi

echo "== 201. the poll fast path FORFEITS on a live checklist, stat-only =="
# The banked pollbase carries clsig and cl_live (wl_checks.bank_pollbase).
# Leg 1 banks a LIVE-but-non-blocking world (wave claimed by a peer), so
# cl_live=1 with an unchanged signature -- which is the only thing that can
# make the silent path forfeit here. Legs 2 and 3 are the controls: the same
# dance with no checklist at all, and with a settled one, must stay silent.
setup
brief_now
hand_now
cldeliver docs/demo/README.md "the readme"
clfile demo <<'MD'
# Handoff checklist: demo
Status: executing

## Deliverables
- [x] d1 file:docs/demo/README.md

## Waves
- [ ] w1 Wave A: wire the thing
MD
as_peer cafe0000 reqcli --add cafe0000 "cl:demo/w1 Wave A: wire the thing" >/dev/null
say "answer

## Remaining
- nothing of mine"
check "201: the full stop allows and banks the checklist world" allow ""
BANK="$(cat "${WL%.md}.pollbase-deadbeef")"
if grep -qF '"cl_live": 1' <<<"$BANK" && grep -qE '"clsig": "[0-9a-f]{16}"' <<<"$BANK"; then
    pass "201: the pollbase banks the live count beside a stat-only signature"
else
    fail "201: the checklist world was not banked: $BANK"
fi
reqcli --poll deadbeef >/dev/null
OUT="$(run)"
if [[ -n "$OUT" ]]; then
    pass "201: a live checklist forfeits the silent poll even with an unchanged world"
else
    fail "201: the poll went silent while a live handoff was outstanding"
fi
setup
brief_now
hand_now
say "answer

## Remaining
- nothing of mine"
check "201 CONTROL: baseline stop with no checklist at all" allow ""
if grep -qF '"cl_live": 0' <<<"$(cat "${WL%.md}.pollbase-deadbeef")"; then
    pass "201 CONTROL: a repo with no handoffs banks cl_live=0, which is what keeps polls free"
else
    fail "201 CONTROL: an empty repo banked a live count: $(cat "${WL%.md}.pollbase-deadbeef")"
fi
reqcli --poll deadbeef >/dev/null
OUT="$(run)"
RC=$?
if [[ "$RC" -eq 0 && -z "$OUT" ]]; then
    pass "201 CONTROL: with no checklist the poll stop is still perfectly silent"
else
    fail "201 CONTROL: the gate broke the silent path for everyone: rc=$RC '${OUT:0:200}'"
fi
setup
brief_now
hand_now
cldeliver docs/demo/README.md "the readme"
clfile demo <<'MD'
# Handoff checklist: demo
Status: done

## Deliverables
- [x] d1 file:docs/demo/README.md

## Waves
- [x] w1 Wave A: wire the thing
MD
say "answer

## Remaining
- nothing of mine"
check "201 CONTROL: baseline stop with a SETTLED checklist" allow ""
reqcli --poll deadbeef >/dev/null
OUT="$(run)"
RC=$?
if [[ "$RC" -eq 0 && -z "$OUT" ]]; then
    pass "201 CONTROL: a done program costs polls nothing, exactly as promised"
else
    fail "201 CONTROL: a settled checklist still charged the poll: rc=$RC '${OUT:0:200}'"
fi
# The banked cl_live is still 0, so the ONLY thing that can forfeit the silent
# path on the next poll is the moved signature -- and the battery it pays for
# is what catches the un-tick this edit smuggled in.
clfile demo <<'MD'
# Handoff checklist: demo
Status: done

## Deliverables
- [x] d1 file:docs/demo/README.md

## Waves
- [ ] w1 Wave A: wire the thing
MD
reqcli --poll deadbeef >/dev/null
OUT="$(run)"
if grep -qF "reality disagrees" <<<"$OUT"; then
    pass "201: a MOVED signature forfeits too, so an edited checklist cannot hide behind a poll"
else
    fail "201: an edited checklist slipped past the poll fast path: '${OUT:0:200}'"
fi

echo "== 202. checklists_sig() is STAT-ONLY, and the unreadable file proves it =="
# A contract, not an optimisation: the poll path compares this value, and a
# version that opened files would pay exactly the cost the fast path exists to
# avoid. A chmod-000 checklist is the instrument -- stat still answers where
# read cannot, so the signature must come back while the ADJUDICATION (which
# does read) fails closed into the ALWAYS-tier unreadable violation. The key
# it fails closed UNDER is asserted too, and it is per-slug (`cl-shape:locked`)
# for the reason case 204 pins: one unreadable checklist must not evict a
# second one from the rotation.
setup
mkdir -p "$BASE/proj/docs/locked"
printf 'Status: executing\n' >"$BASE/proj/docs/locked/CHECKLIST.md"
chmod 000 "$BASE/proj/docs/locked/CHECKLIST.md"
OUT=$(
    cd "$(dirname "$HOOK")" && CLROOT="$BASE/proj" python3 - <<'PYEOF'
import os
import sys

sys.path.insert(0, ".")
import wl_checklist as CL

root = os.environ["CLROOT"]
path = os.path.join(root, "docs", "locked", "CHECKLIST.md")
try:
    open(path).read()
    print("READABLE yes")
except OSError:
    print("READABLE no")
print("SIG", CL.checklists_sig(root))
v, a, live = CL.checklist_findings(root, None, "deadbeef-1111", "")
print("V", v[0][0], v[0][1], live)
print("TEXT", "THIS IS A HOOK BUG" in v[0][2])
PYEOF
)
chmod 644 "$BASE/proj/docs/locked/CHECKLIST.md"
if grep -q "^READABLE no$" <<<"$OUT"; then
    pass "202 CONTROL: the fixture really is unreadable, so the leg below means something"
else
    fail "202 CONTROL: chmod 000 did not deny this process (running as root?): ${OUT:0:200}"
fi
if grep -qE "^SIG [0-9a-f]{16}$" <<<"$OUT"; then
    pass "202: checklists_sig returns a signature for a file it may not open"
else
    fail "202: the stat-only signature raised or came back malformed: ${OUT:0:300}"
fi
if grep -q "^V cl-shape:locked True 1$" <<<"$OUT" && grep -q "^TEXT True$" <<<"$OUT"; then
    pass "202: and the reading half fails CLOSED, ALWAYS-tier, naming itself a hook bug"
else
    fail "202: an unreadable checklist did not fail closed: ${OUT:0:300}"
fi
rm -f "$BASE/proj/docs/locked/CHECKLIST.md"

echo "== 203. SessionStart hands a new session the live checklists =="
setup
cldeliver docs/demo/README.md "the readme"
clfile demo <<'MD'
# Handoff checklist: demo
Status: executing
Owner: cafe0000

## Deliverables
- [x] d1 file:docs/demo/README.md

## Waves
- [x] w1 Wave A: wire the thing
- [ ] w2 Wave B: land the rest
MD
out="$(printf '{"session_id":"%s","cwd":"%s"}' "$SID" "$BASE/proj" |
    TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" WORKLIST_AGENT_BRANCH=agenttest \
        python3 "$HOOK" --session-start 2>/dev/null)"
if grep -qF "LIVE HANDOFF CHECKLISTS" <<<"$out" &&
    grep -qF "docs/demo/CHECKLIST.md [executing] owner=cafe0000 deliverables 1/1 verified, waves 1/2 settled" <<<"$out"; then
    pass "203: the listing carries status, owner and both progress fractions"
else
    fail "203: SessionStart did not hand back the live checklist: ${out:0:400}"
fi
clfile demo <<'MD'
# Handoff checklist: demo
Status: done

## Deliverables
- [x] d1 file:docs/demo/README.md

## Waves
- [x] w1 Wave A: wire the thing
MD
out="$(printf '{"session_id":"%s","cwd":"%s"}' "$SID" "$BASE/proj" |
    TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" WORKLIST_AGENT_BRANCH=agenttest \
        python3 "$HOOK" --session-start 2>/dev/null)"
if ! grep -qF "LIVE HANDOFF CHECKLISTS" <<<"$out"; then
    pass "203 CONTROL: a settled checklist is not context anyone needs handed back"
else
    fail "203 CONTROL: the listing surfaced a done handoff: ${out:0:400}"
fi

# ---------------------------------------------------------------------------
# 204-206 v20b: ONE KEY PER CHECKLIST, and an advisory that gives no orders.
# Both gaps were found by the automated review on PR #563, and both are about
# a second concurrent handoff, which this repo ran two of on the day they
# landed.
#
# 204/205 pin the KEY. Every checklist finding used to be pushed under a fixed
# string -- "cl-waves", "cl-foreign" and friends -- while two things downstream
# read that string as an IDENTITY. The focused block's rotation builds its tie
# breaker with `order = {v[0]: i for ...}`, a dict comp in which duplicate keys
# COLLAPSE, so two violations sharing a key get identical sort tuples and `min`
# returns the first one forever; and outq_add finds a non-sticky entry by key
# alone, so the second advisory OVERWRITES the first rather than queueing
# beside it. The second handoff was therefore starved permanently, not for a
# stop or two, and only ever showed up inside the "N more outstanding" count.
#
# 206 pins the AUDIENCE. The drift text was built once and routed either to a
# blocking violation (owner) or to the advisory (non-owner), so a session that
# does not own the handoff was told to restore the artifacts "in this turn".
# Acting on that means editing another session's header or its files, which is
# how a peer's shared STATE.md was destroyed here.

echo "== 204. two handoffs, two keys: the rotation serves BOTH, one per stop =="
setup
say "done for now"
brief_now
hand_now
cldeliver docs/alpha/README.md "the readme"
cldeliver docs/beta/README.md "the readme"
clfile alpha <<'MD'
# Handoff checklist: alpha
Status: executing

## Deliverables
- [x] d1 file:docs/alpha/README.md

## Waves
- [ ] w1 Wave A: wire the alpha thing
MD
clfile beta <<'MD'
# Handoff checklist: beta
Status: executing

## Deliverables
- [x] d1 file:docs/beta/README.md

## Waves
- [ ] w1 Wave A: wire the beta thing
MD
OUT1="$(run)"
OUT2="$(run)"
if grep -qF "handoff 'alpha' (docs/alpha/CHECKLIST.md)" <<<"$OUT1$OUT2" &&
    grep -qF "handoff 'beta' (docs/beta/CHECKLIST.md)" <<<"$OUT1$OUT2"; then
    pass "204: two uncovered waves in one check class are both itemized across two stops"
else
    fail "204: one handoff starved the other in the rotation: 1=${OUT1:0:300} 2=${OUT2:0:300}"
fi
if ! grep -qF "handoff 'beta'" <<<"$OUT1" && ! grep -qF "handoff 'alpha'" <<<"$OUT2"; then
    pass "204: and it is still ONE per stop, in battery order -- the block did not widen"
else
    fail "204: the focused block stopped rotating: 1=${OUT1:0:300} 2=${OUT2:0:300}"
fi
as_peer cafe0000 reqcli --add cafe0000 "cl:alpha/w1 Wave A: wire the alpha thing" >/dev/null
as_peer cafe0000 reqcli --add cafe0000 "cl:beta/w1 Wave A: wire the beta thing" >/dev/null
OUT="$(run)"
RC=$?
if [[ "$RC" -eq 0 ]] && ! grep -qF "UNCOVERED" <<<"$OUT" && ! grep -qF '"decision": "block"' <<<"$OUT"; then
    pass "204 CONTROL: both waves claimed, so neither per-slug key is left outstanding"
else
    fail "204 CONTROL: a per-slug key outlived the wave it belonged to: ${OUT:0:400}"
fi

echo "== 205. two FOREIGN advisories, two keys: the second no longer eats the first =="
# Leg 1 is the needle's own control: with only alpha planted, beta's needle
# must be MISSING. Without it, leg 2 could pass on a grep that matches
# anything, which is the failure mode a two-needle assertion hides best.
#
# EACH LEG GETS ITS OWN FIXTURE, and that is not tidiness. Draining an
# advisory latches it in the queue's `shown` ledger, so planting beta beside an
# ALREADY-SHOWN alpha suppresses alpha through the refresh window -- correct
# behaviour that looks exactly like the overwrite bug and would have made this
# case fire for the wrong reason.
setup
say "done for now"
brief_now
hand_now
export WORKLIST_REPORT_PER_STOP=6
clfile alpha <<'MD'
# Handoff checklist: alpha
Status: producing
Owner: cafe0000

## Deliverables
- [ ] d1 file:docs/alpha/README.md

## Waves
- [ ] w1 Wave A: wire the alpha thing
MD
OUT="$(run)"
if grep -qF "docs/alpha/CHECKLIST.md is 'Status: producing'" <<<"$OUT" &&
    ! grep -qF "docs/beta/CHECKLIST.md" <<<"$OUT"; then
    pass "205 CONTROL: one foreign handoff, one advisory, and beta's needle can be absent"
else
    fail "205 CONTROL: the single-checklist baseline is not what it claims: ${OUT:0:400}"
fi
setup
say "done for now"
brief_now
hand_now
export WORKLIST_REPORT_PER_STOP=6
clfile alpha <<'MD'
# Handoff checklist: alpha
Status: producing
Owner: cafe0000

## Deliverables
- [ ] d1 file:docs/alpha/README.md

## Waves
- [ ] w1 Wave A: wire the alpha thing
MD
clfile beta <<'MD'
# Handoff checklist: beta
Status: producing
Owner: cafe0000

## Deliverables
- [ ] d1 file:docs/beta/README.md

## Waves
- [ ] w1 Wave A: wire the beta thing
MD
OUT="$(run)"
RC=$?
if [[ "$RC" -eq 0 ]] && grep -qF "docs/alpha/CHECKLIST.md is 'Status: producing'" <<<"$OUT" &&
    grep -qF "docs/beta/CHECKLIST.md is 'Status: producing'" <<<"$OUT"; then
    pass "205: both foreign handoffs ride the report; neither advisory overwrites the other"
else
    fail "205: one foreign advisory replaced the other in the queue: ${OUT:0:600}"
fi
unset WORKLIST_REPORT_PER_STOP

echo "== 206. a foreign DRIFT advisory reports it; it does not order the reader around =="
setup
say "done for now"
brief_now
hand_now
export WORKLIST_REPORT_PER_STOP=6
clfile demo <<'MD'
# Handoff checklist: demo
Status: executing
Owner: cafe0000

## Deliverables
- [x] d1 file:docs/demo/README.md

## Waves
- [x] w1 Wave A: wire the thing
MD
OUT="$(run)"
RC=$?
if [[ "$RC" -eq 0 ]] && grep -qF "d1 docs/demo/README.md -- MISSING" <<<"$OUT" &&
    grep -qF "Reported, never blocked on." <<<"$OUT" &&
    grep -qF "cafe0000" <<<"$OUT" && ! grep -qF "in this turn" <<<"$OUT"; then
    pass "206: a non-owner is told about the drift and is handed no instruction to act on"
else
    fail "206: the foreign drift advisory still issues the owner's order: rc=$RC ${OUT:0:600}"
fi
if grep -qF "another session's" <<<"$OUT"; then
    pass "206: and it says out loud that repairing it here would overwrite live work"
else
    fail "206: nothing warned the reader off editing a peer's checklist: ${OUT:0:600}"
fi
clfile demo <<'MD'
# Handoff checklist: demo
Status: executing
Owner: deadbeef

## Deliverables
- [x] d1 file:docs/demo/README.md

## Waves
- [x] w1 Wave A: wire the thing
MD
OUT="$(run)"
if grep -qF '"decision": "block"' <<<"$OUT" && grep -qF "reality disagrees" <<<"$OUT" &&
    grep -qF "in this turn" <<<"$OUT"; then
    pass "206 CONTROL: the SAME drift under its owner still blocks, imperative intact"
else
    fail "206 CONTROL: ownership stopped deciding who is ordered to repair: ${OUT:0:600}"
fi
unset WORKLIST_REPORT_PER_STOP

echo "== 207. the judge ADVISES; it does not get to order the operator's three things =="
# Paid for on 2026-08-09: the stop gate read a session sitting on four green
# stacked PRs and returned next_action "merge PRs 563, 565 and 566". The session
# declined, which is the right outcome reached by the WRONG mechanism: it survived
# on the model's judgement at the moment of reading, and this whole program exists
# because judgement at the moment of reading is the faculty that fails. The filter
# is deterministic so a tireder session cannot comply with its own stop gate.
setup
JUDGE_FILTER_OUT="$(
    python3 - "$(dirname "$HOOK")" <<'PYEOF'
import sys
sys.path.insert(0, sys.argv[1])
from wl_judge import sanitize_next_action as s
BLOCK = [
    ("a bare merge order", "merge PRs 563, 565 and 566"),
    ("a polite merge order", "You should probably merge 563 now that it is green."),
    ("the literal command", "gh pr merge 567 --rebase"),
    ("push main", "push main with the fix"),
    ("push main, reversed wording", "get this onto main by pushing"),
    ("cut a release", "cut the release once CI is green"),
    # DELIBERATE over-inclusion, pinned so nobody relaxes it into a bypass: asking
    # about merging is harmless, but a carve-out for the question reopens the door
    # for "ask the operator whether to merge, and if CI is green, merge".
    ("even ASKING about merging", "ask the operator whether to merge"),
]
KEEP = [
    ("an ordinary review action", "reply to the review summary on 567 and resolve its threads"),
    ("release as a NOUN", "update the release notes in docs/ before the next wave"),
    ("the release CHANNEL", "check the release channel manifest for edge"),
    ("an ordinary suite action", "run the umbrella suite and tick f1c5d077 with the count"),
    ("an empty next action", ""),
]
for why, text in BLOCK:
    got = s({"next_action": text})["next_action"]
    print(("REJECTED " if got.startswith("[rejected") else "LEAKED ") + why)
for why, text in KEEP:
    got = s({"next_action": text})["next_action"]
    print(("KEPT " if got == text else "CLOBBERED ") + why)
# The VERDICT itself must never be touched: stop-or-continue is the judge's actual
# job and rewriting it here would collide with the no-escape-hatch invariant.
v = s({"verdict": "stop", "reason": "clean", "next_action": "merge 563"})
print("VERDICT-INTACT" if v["verdict"] == "stop" and v["reason"] == "clean" else "VERDICT-MUTATED")
PYEOF
)"
if [[ "$(grep -c '^REJECTED ' <<<"$JUDGE_FILTER_OUT")" == "7" ]] && ! grep -q '^LEAKED ' <<<"$JUDGE_FILTER_OUT"; then
    pass "207 every operator-only order is rejected (7 shapes, including the polite one)"
else
    fail "207 an operator-only order leaked: $(grep '^LEAKED ' <<<"$JUDGE_FILTER_OUT")"
fi
if [[ "$(grep -c '^KEPT ' <<<"$JUDGE_FILTER_OUT")" == "5" ]] && ! grep -q '^CLOBBERED ' <<<"$JUDGE_FILTER_OUT"; then
    pass "207 CONTROL: ordinary next actions survive, including release as a noun"
else
    fail "207 CONTROL: a legitimate next action was clobbered: $(grep '^CLOBBERED ' <<<"$JUDGE_FILTER_OUT")"
fi
if grep -q '^VERDICT-INTACT' <<<"$JUDGE_FILTER_OUT"; then
    pass "207 CONTROL: the verdict and reason are left untouched (no escape hatch)"
else
    fail "207 CONTROL: the filter mutated the verdict itself"
fi

echo "== 208. a DEAD worker gets the remedy that can actually resolve it =="
# Paid for live on 2026-08-10. The 90-minute rung reported "its declared
# worker:X is NOT in the harness background list any more" and printed
# `--update <id>` as the command. A session ran exactly that, with real
# evidence, and the IDENTICAL complaint fired on the next stop: --update
# refreshes the item's text and its liveness clock and leaves the false
# worker:X claim standing. The prose offered three remedies and the one
# printed command was the only one that cannot work. One full round trip lost.
setup
brief_now
hand_now
CID=$(reqcli --add deadbeef "work handed to a worker that then died" | grep -oE '#[0-9a-f]+' | tr -d '#')
# Lease it to a worker the harness DOES know, so the lease is accepted...
printf '{"background_tasks":[{"id":"bw9","type":"shell","status":"running","description":"the watch"}]}\n' \
    >"${WL%.md}.lastevent-deadbeef.json"
reqcli --lease deadbeef "$CID" +120 worker:bw9 "watching the run" >/dev/null 2>&1
# ...then take that worker away, which is exactly what a finished task looks like.
printf '{"background_tasks":[]}\n' >"${WL%.md}.lastevent-deadbeef.json"
BG='[]'
OUT="$(run)"
if grep -qF "NO LONGER EXISTS" <<<"$OUT" && grep -qF "worklist.py --lease deadbeef" <<<"$OUT" && grep -qF "worklist.py --tick deadbeef" <<<"$OUT"; then
    pass "208 the dead-worker block offers --lease and --tick"
else
    fail "208 dead-worker block missing its remedies: ${OUT:0:400}"
fi
# THE ASSERTION THAT WOULD HAVE CAUGHT THE ORIGINAL BUG: the command it prints
# must not be the one that cannot resolve a dead worker.
#
# IT REQUIRES THE BLOCK TO BE PRESENT, and that is not belt-and-braces. The first
# version asserted only the absence of --update, and a mutation that suppressed
# the whole dead-worker block made it PASS: with no block there is no --update in
# the output, so a bare negative is satisfied by the feature not existing. A check
# that passes when the thing it guards is gone is the exact defect this suite
# exists to catch, and only running the mutation revealed it.
if grep -qF "NO LONGER EXISTS" <<<"$OUT" && ! grep -qE "worklist\.py --update deadbeef" <<<"$OUT"; then
    pass "208 the block is present AND does not print --update, the remedy that leaves worker:X standing"
else
    fail "208 block absent, or still printing --update for a dead worker: ${OUT:0:400}"
fi
# CONTROL: a worker the harness still lists is merely quiet, not gone, and must
# NOT be pushed onto the dead-worker path.
setup
brief_now
hand_now
CID=$(reqcli --add deadbeef "work with a live worker" | grep -oE '#[0-9a-f]+' | tr -d '#')
printf '{"background_tasks":[{"id":"bw9","type":"shell","status":"running","description":"the watch"}]}\n' \
    >"${WL%.md}.lastevent-deadbeef.json"
reqcli --lease deadbeef "$CID" +120 worker:bw9 "watching the run" >/dev/null 2>&1
BG='[{"id":"bw9","status":"running","description":"the watch"}]'
OUT="$(run)"
if ! grep -qF "NO LONGER EXISTS" <<<"$OUT"; then
    pass "208 CONTROL: a still-listed worker is never called gone"
else
    fail "208 CONTROL: a live worker was reported as gone: ${OUT:0:300}"
fi

echo "== 209. the specialist-agent hint (wl_agents) =="
# WHY THIS EXISTS. On 2026-08-14 the operator had to hint twice BY HAND ("there
# is bench server deployment", "@.claude/agents/ may help for ops as well")
# because nothing surfaced the seven specialists that already existed: the word
# "bench" appeared ZERO times across all seven `description` fields and exactly
# once in the whole directory, in a BODY. The knowledge existed and the matching
# surface did not. The hook now says so unprompted.
#
# EVERY CASE BELOW USES INVENTED NOUNS against the fixture corpus in
# $BASE/agents (setup pins WORKLIST_AGENTS_DIR at it). A fixture borrowing the
# real agents' vocabulary would go red when somebody edits a description, which
# is prose nobody thinks of as test data.
#
# THE HINT IS PRIORITY 3 and OUTQ_PER_STOP is 1, so on any stop carrying another
# advisory the hint correctly loses the slot. That is the single most important
# noise control in the design (209K proves it), and it is why every case that
# wants to SEE a hint widens the drain first.
HINT_DESC="Zorbium recalibration and the frobnicator index, including sprocket torque."
HINT_SAY="done for now, next up is the zorbium frobnicator recalibration"
hint_fixture() { # a clean allow stop whose last message is in the fixture domain
    say "$HINT_SAY"
    brief_now
    hand_now
}
hint_n() { # occurrences of the hint header in $1
    # A COUNT, not a grep: the payload is ONE JSON line, so `grep -c` answers 1
    # for two hints and the double-fire cases below would pass on a feature
    # that fired every stop.
    python3 -c 'import sys; print(sys.stdin.read().count("Specialist agent available"))' <<<"$1"
}
setup
export WORKLIST_REPORT_PER_STOP=4
mk_agent fixtureagent "$HINT_DESC"
hint_fixture
check "209A a matching last message produces the hint on an allow stop" allow \
    "Specialist agent available: fixtureagent"
# CONTROL, and it leads with a POSITIVE PRESENCE check rather than the absence
# alone. This suite documents the trap at case 208: a mutation that suppressed a
# whole block made an absence-only assertion PASS, because with no feature there
# is nothing to find. So the stop must be shown to have spoken at all first.
setup
export WORKLIST_REPORT_PER_STOP=4
mk_agent fixtureagent "$HINT_DESC"
say "done for now, the meeting notes are filed"
brief_now
hand_now
OUT="$(run)"
if grep -qF "INBOX HAS BEEN QUIET" <<<"$OUT" && [[ "$(hint_n "$OUT")" -eq 0 ]]; then
    pass "209A CONTROL: the stop still reports, and neutral text earns no hint"
else
    fail "209A CONTROL: neutral text hinted, or the stop said nothing at all: ${OUT:0:400}"
fi

# B. ADVISORY, NEVER A BLOCK. `vadd` has 46 call sites and every one of them
# stops the session; blocking a session for not consulting a specialist is the
# fastest possible way to get this feature switched off.
setup
export WORKLIST_REPORT_PER_STOP=4
mk_agent fixtureagent "$HINT_DESC"
hint_fixture
OUT="$(run)"
RC=$?
if [[ "$RC" -eq 0 ]] && [[ "$(hint_n "$OUT")" -eq 1 ]] &&
    ! grep -qF '"decision"' <<<"$OUT" && ! grep -qF "Do not stop yet" <<<"$OUT"; then
    pass "209B the hint rides an allow: no decision field, no block reason, rc=0"
else
    fail "209B the hint blocked or failed the stop (rc=$RC): ${OUT:0:400}"
fi

# C. A TIE IS SILENCE, BY CONSTRUCTION: a tie makes the margin 0, which is below
# any positive threshold, so there is no tie-break rule to get wrong. Inventing a
# winner is how a matcher starts lying.
setup
export WORKLIST_REPORT_PER_STOP=4
mk_agent tiealpha "Zorbium recalibration with the widget gearbox lattice."
mk_agent tiebeta "Zorbium recalibration with the sprocket flywheel lattice."
say "done for now, the widget gearbox and the sprocket flywheel both wait on me"
brief_now
hand_now
OUT="$(run)"
if [[ "$(hint_n "$OUT")" -eq 0 ]] && ! grep -qF "Traceback" "$BASE/err.txt"; then
    pass "209C two agents matching equally produce no hint and no error"
else
    fail "209C a tie was broken, or it crashed: ${OUT:0:300} err: $(head -c 200 "$BASE/err.txt")"
fi
# CONTROL: the same two fixtures, a haystack naming only ONE of them. Without
# this, 209C would pass on a matcher that had simply stopped working.
newturn
say "done for now, the widget gearbox waits on me"
OUT="$(run)"
if grep -qF "Specialist agent available: tiealpha" <<<"$OUT"; then
    pass "209C CONTROL: break the tie and the same corpus hints immediately"
else
    fail "209C CONTROL: the corpus could not hint at all, so 209C proved nothing: ${OUT:0:400}"
fi

# D. RATE LIMIT: the same specialist is not suggested twice. A hint that fires
# on every stop is wallpaper, and wallpaper gets ignored.
setup
export WORKLIST_REPORT_PER_STOP=4
mk_agent fixtureagent "$HINT_DESC"
hint_fixture
OUT="$(run)"
newturn
say "$HINT_SAY"
OUT2="$(run)"
if [[ "$(hint_n "$OUT")" -eq 1 ]] && [[ $(($(hint_n "$OUT") + $(hint_n "$OUT2"))) -eq 1 ]]; then
    pass "209D two identical stops in a row emit the hint exactly once"
else
    fail "209D hint counts were $(hint_n "$OUT") then $(hint_n "$OUT2")"
fi

# E. A DELETED AGENT CANNOT BE RECOMMENDED. The corpus is re-read from disk on
# every stop for exactly this reason, which is also why there is no cache: a
# cache is what would let a deleted agent keep being recommended.
#
# The second stop matches a DIFFERENT agent on the same text, deliberately. A
# case that merely re-ran the deleted agent's own haystack would pass on the
# refresh window alone, proving nothing about the corpus being re-read.
setup
export WORKLIST_REPORT_PER_STOP=4
mk_agent gonesoon "$HINT_DESC"
hint_fixture
OUT="$(run)"
rm -f "$BASE/agents/gonesoon.md"
mk_agent stillhere "$HINT_DESC"
newturn
say "$HINT_SAY"
OUT2="$(run)"
if grep -qF "Specialist agent available: gonesoon" <<<"$OUT" &&
    grep -qF "Specialist agent available: stillhere" <<<"$OUT2" &&
    ! grep -qF "gonesoon" <<<"$OUT2" && ! grep -qF "Traceback" "$BASE/err.txt"; then
    pass "209E a deleted agent stops being recommended, and its sibling still is"
else
    fail "209E stale corpus or crash: ${OUT2:0:400} err: $(head -c 200 "$BASE/err.txt")"
fi

# F. INDEPENDENT OF THE JUDGE. wl_judge spends one haiku call per eventful stop
# at 4.9-20.0s and has BLOCKED a stop on a timeout; a second model call was
# refused. This pins that the hint is deterministic and does not ride that call.
setup
export WORKLIST_REPORT_PER_STOP=4
mk_agent fixtureagent "$HINT_DESC"
hint_fixture
OUT="$(run)" # JUDGE_MODE=off, and $BASE/binonly holds no `claude` at all
if [[ "$(hint_n "$OUT")" -eq 1 ]] && ! grep -qF "Stop-gate judge" <<<"$OUT"; then
    pass "209F the hint fires with the judge OFF, so it costs no model call"
else
    fail "209F the hint needed the judge: ${OUT:0:400}"
fi

# G. A MALFORMED CORPUS IS LOUD, AND DEGRADES RATHER THAN DISABLES. A file that
# cannot be parsed is an agent that has silently stopped being reachable, which
# is the exact failure this whole feature exists to end -- so it is reported,
# while every sibling that IS well-formed keeps matching.
setup
export WORKLIST_REPORT_PER_STOP=4
mk_agent goodagent "$HINT_DESC"
printf -- '---\nname: brokenagent\ntools: Bash\n---\nbody with no description\n' \
    >"$BASE/agents/brokenagent.md"
hint_fixture
OUT="$(run)"
if grep -qF "Agent corpus problem" <<<"$OUT" && grep -qF "brokenagent" <<<"$OUT" &&
    grep -qF "Specialist agent available: goodagent" <<<"$OUT"; then
    pass "209G a description-less agent is REPORTED and its valid sibling still matches"
else
    fail "209G the corpus error was swallowed or it disabled the matcher: ${OUT:0:400}"
fi

# H. POSTCOMPACT, which is the highest-value delivery in the design: a compacted
# session is precisely the one that has forgotten a specialist exists, and
# additionalContext is read rather than skimmed. Once per compaction by
# construction, so it needs no rate limit.
setup
mk_agent fixtureagent "$HINT_DESC"
STATE_SAVE="$STATE_BODY"
STATE_BODY='You are picking up the zorbium frobnicator recalibration, which has been running since the sprocket torque numbers came back wrong on the third pass. Nothing is committed yet and the fixture rig is still wired up the way the last session left it.

## Next action

Re-run the frobnicator index build, then compare the recalibration output against the numbers in the notes.'
hand_now
STATE_BODY="$STATE_SAVE"
out="$(printf '{"session_id":"%s","cwd":"%s"}' "$SID" "$BASE/proj" |
    TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" WORKLIST_AGENT_BRANCH=agenttest \
        python3 "$HOOK" --post-compact 2>/dev/null)"
if grep -qF "picking up an in-progress session" <<<"$out" &&
    grep -qF "Specialist agent available: fixtureagent" <<<"$out"; then
    pass "209H PostCompact hands the compacted session its specialist"
else
    fail "209H PostCompact carried no hint: ${out:0:400}"
fi
# CONTROL: the same corpus, a briefing in no agent's domain. The briefing must
# still arrive -- absence of the hint alone would also describe a broken
# PostCompact.
setup
mk_agent fixtureagent "$HINT_DESC"
hand_now
out="$(printf '{"session_id":"%s","cwd":"%s"}' "$SID" "$BASE/proj" |
    TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" WORKLIST_AGENT_BRANCH=agenttest \
        python3 "$HOOK" --post-compact 2>/dev/null)"
if grep -qF "picking up an in-progress session" <<<"$out" && [[ "$(hint_n "$out")" -eq 0 ]]; then
    pass "209H CONTROL: an off-domain briefing still arrives, without a hint"
else
    fail "209H CONTROL: the briefing broke, or hinted off-domain: ${out:0:400}"
fi

# I. THE KILL SWITCH. Positive presence first, for the 208 reason.
setup
export WORKLIST_REPORT_PER_STOP=4
export WORKLIST_AGENT_HINT=off
mk_agent fixtureagent "$HINT_DESC"
hint_fixture
OUT="$(run)"
if grep -qF "INBOX HAS BEEN QUIET" <<<"$OUT" && [[ "$(hint_n "$OUT")" -eq 0 ]]; then
    pass "209I WORKLIST_AGENT_HINT=off silences the hint and nothing else"
else
    fail "209I the kill switch did not kill, or it killed the whole report: ${OUT:0:400}"
fi
unset WORKLIST_AGENT_HINT

# J. THE PER-SESSION CAP, across DIFFERENT agents (the refresh window in 209D
# only bounds one agent; without a cap, eight specialists could each get a turn).
setup
export WORKLIST_REPORT_PER_STOP=4
export WORKLIST_AGENT_HINT_MAX_PER_SESSION=1
mk_agent alphaagent "$HINT_DESC"
mk_agent betaagent "Quixotic pumpjack telemetry and the marlinspike ledger."
hint_fixture
OUT="$(run)"
newturn
say "done for now, the quixotic pumpjack telemetry needs a marlinspike ledger entry"
OUT2="$(run)"
if grep -qF "Specialist agent available: alphaagent" <<<"$OUT" &&
    [[ $(($(hint_n "$OUT") + $(hint_n "$OUT2"))) -eq 1 ]]; then
    pass "209J the per-session cap holds across two different agents"
else
    fail "209J cap leaked: $(hint_n "$OUT") then $(hint_n "$OUT2")"
fi
# CONTROL: one planted fact differs, the cap. The second agent must then land,
# or 209J was measuring a matcher that could only ever hit once.
setup
export WORKLIST_REPORT_PER_STOP=4
export WORKLIST_AGENT_HINT_MAX_PER_SESSION=2
mk_agent alphaagent "$HINT_DESC"
mk_agent betaagent "Quixotic pumpjack telemetry and the marlinspike ledger."
hint_fixture
OUT="$(run)"
newturn
say "done for now, the quixotic pumpjack telemetry needs a marlinspike ledger entry"
OUT2="$(run)"
if grep -qF "Specialist agent available: alphaagent" <<<"$OUT" &&
    grep -qF "Specialist agent available: betaagent" <<<"$OUT2"; then
    pass "209J CONTROL: raise the cap by one and the second specialist lands"
else
    fail "209J CONTROL: the second agent never fired, so the cap proved nothing: ${OUT2:0:400}"
fi
unset WORKLIST_AGENT_HINT_MAX_PER_SESSION
unset WORKLIST_REPORT_PER_STOP

# K. PRIORITY 3 NEVER DISPLACES A REAL SECTION, and this is the case to write
# first: it PROVES the noise control instead of asserting it. Every existing
# advisory is priority 2 or better and outq_drain releases one section per stop,
# so a hint reaches the operator only on a stop with nothing more important to
# say. That property costs nothing to obtain and is the whole reason this
# feature is not wallpaper.
setup
mk_agent fixtureagent "$HINT_DESC"
hint_fixture
brief_other cafe1234
touch -d '-48 hours' "$BASE/cafe1234.jsonl"
echo '- [ ] (cafe1234) their abandoned item' >>"$WL"
OUT="$(run)" # WORKLIST_REPORT_PER_STOP unset, so exactly one section is released
if [[ "$(hint_n "$OUT")" -eq 0 ]] &&
    grep -qE "INBOX HAS BEEN QUIET|ORPHANED item\(s\)|Other sessions in this worktree" <<<"$OUT" &&
    grep -qF "more report section(s) queued" <<<"$OUT"; then
    pass "209K a real advisory takes the slot, the hint waits, and the tail says so"
else
    fail "209K the hint displaced a real section, or nothing was queued: ${OUT:0:400}"
fi
# CONTROL, and it is what makes 209K a measurement rather than a coincidence:
# widen the drain on the very next stop and the hint is STILL THERE, so what
# 209K observed was a queued hint being outranked, not a hint that never fired.
export WORKLIST_REPORT_PER_STOP=6
newturn
say "$HINT_SAY"
OUT2="$(run)"
if grep -qF "Specialist agent available: fixtureagent" <<<"$OUT2"; then
    pass "209K CONTROL: the outranked hint was queued all along and drains next"
else
    fail "209K CONTROL: the hint was never queued at all: ${OUT2:0:400}"
fi
unset WORKLIST_REPORT_PER_STOP

# L. THE OPERATOR'S OWN SENTENCE, verbatim. REGRESSION 2026-08-15.
#
# "there is bench server deployment. Why you don't utilize it?" is the sentence
# that caused this feature to be built, and when the matcher was first wired up
# it returned NOTHING for it. The corpus carried `deploy`, `deploying` and
# `deploys` -- three variants of one verb, hand-enumerated -- and not
# `deployment`, so the query lost that hit to morphology, landed on `bench`
# alone at 1.0, and died against MIN_SCORE=2. The feature would have shipped
# unable to answer the only query we KNOW a real session needed.
#
# Pinned in the operator's words rather than a tidied paraphrase, because a
# paraphrase is written by the same hand that writes the matcher and drifts
# toward whatever the matcher already does.
#
# THE FIXTURE DESCRIPTION MUST NOT CONTAIN "deployment", and the case ASSERTS
# that rather than trusting it: if some future session "fixes" a red run here by
# pasting the query's word into the description, the assertion below goes red
# instead, which is the hand-maintained-variant-list staleness this fold exists
# to end.
setup
export WORKLIST_REPORT_PER_STOP=4
mk_agent benchops "The bench rig: deploy the account worker to the bench box and reset its store."
say "there is bench server deployment. Why you don't utilize it?"
brief_now
hand_now
OUT="$(run)"
if ! grep -qF "deployment" "$BASE/agents/benchops.md" &&
    grep -qF "Specialist agent available: benchops" <<<"$OUT"; then
    pass "209L the operator's literal sentence fires, on a description that never says 'deployment'"
else
    fail "209L the motivating query still does not fire, or the fixture was tautologised: ${OUT:0:400}"
fi
# CONTROL, and it is what makes 209L a measurement of MORPHOLOGY rather than of
# the word `bench`: `bench` on its own scores 1.0, below MIN_SCORE, and stays
# silent. So the hit that carried 209L over the floor can only have come from
# `deployment` folding onto the description's `deploy`.
newturn
say "there is a bench in the corridor and nobody has claimed it"
OUT="$(run)"
if [[ "$(hint_n "$OUT")" -eq 0 ]]; then
    pass "209L CONTROL: one discriminative term alone is still under the floor"
else
    fail "209L CONTROL: a single term cleared MIN_SCORE, so the floor is not holding: ${OUT:0:400}"
fi
unset WORKLIST_REPORT_PER_STOP

echo "== 211. a DOOR-PARKED wave is reported, never blocked on =="
# _wave_rows deliberately emits nothing for a wave whose covering items were all
# closed through a door: the work did not happen, no session can make it happen,
# and demanding a tick would be demanding a lie. That reasoning is right, and it
# skipped the wave into TOTAL silence -- no violation, and its item is [x] so it
# has also left --list --open. Nothing surfaced it again, ever.
#
# Found 2026-08-15 when the operator asked why the stop hook had never mentioned
# an unticked w8. The honest answer was that the ONLY thing keeping it visible
# was a session remembering to write it into a report by hand.
setup
say "done for now

## Remaining
- nothing"
brief_now
hand_now
cldeliver docs/demo/README.md "the readme"
clfile demo <<'MD'
# Handoff checklist: demo
Status: executing

## Deliverables
- [x] d1 file:docs/demo/README.md

## Waves
- [ ] w1 Wave A: mint the production secrets
MD
IID="$(reqcli --add deadbeef "cl:demo/w1 Wave A: mint the production secrets" | grep -o '#[0-9a-f]*' | head -1 | tr -d '#')"
reqcli --tick deadbeef "$IID" "door:operator-only -- secrets are write-only, exit 0" >/dev/null
OUT="$(run)"
DEC="$(python3 -c 'import json,sys
raw=sys.stdin.read().strip()
print(json.loads(raw).get("decision","allow") if raw else "allow")' <<<"$OUT" 2>/dev/null)"
if grep -qF "w1 [door:operator-only]" <<<"$OUT" && [[ "$DEC" != "block" ]]; then
    pass "211: a door-parked wave is REPORTED and does not block"
else
    fail "211: door-parked wave decision=$DEC out: ${OUT:0:400}"
fi

echo "== 211b. CONTROL: the same wave TICKED says nothing at all =="
# Without this the advisory could be firing on any unticked wave, or on every
# checklist regardless of state, and would read as noise within a day.
clfile demo <<'MD'
# Handoff checklist: demo
Status: executing

## Deliverables
- [x] d1 file:docs/demo/README.md

## Waves
- [x] w1 Wave A: mint the production secrets
MD
OUT="$(run)"
if ! grep -qF "door:operator-only]" <<<"$OUT"; then
    pass "211b CONTROL: a ticked wave produces no door advisory"
else
    fail "211b CONTROL: the advisory fired on a TICKED wave: ${OUT:0:300}"
fi

echo "== 211c. CONTROL: closed WITHOUT a door is a different thing entirely =="
# An item ticked by DOING the work leaves the wave genuinely done-but-unticked,
# which is a VIOLATION with its own exit, not a door advisory. If this case ever
# starts printing the advisory, the door detector has stopped reading doors and
# is matching every closed item.
setup
say "done for now

## Remaining
- nothing"
brief_now
hand_now
cldeliver docs/demo/README.md "the readme"
clfile demo <<'MD'
# Handoff checklist: demo
Status: executing

## Deliverables
- [x] d1 file:docs/demo/README.md

## Waves
- [ ] w1 Wave A: wire the thing
MD
IID="$(reqcli --add deadbeef "cl:demo/w1 Wave A: wire the thing" | grep -o '#[0-9a-f]*' | head -1 | tr -d '#')"
reqcli --tick deadbeef "$IID" "wired it, suite green, exit 0" >/dev/null
OUT="$(run)"
if grep -qF "DONE-BUT-UNTICKED" <<<"$OUT" && ! grep -qF "door:" <<<"$OUT"; then
    pass "211c CONTROL: a doorless close is DONE-BUT-UNTICKED, not a door advisory"
else
    fail "211c CONTROL: ${OUT:0:400}"
fi

echo "== 213. the block counter is SESSION-SCOPED =="
# It was a single shared `.blocks` for the whole worktree. With ~48 addressable
# sessions here, one peer's clean allow deleted MY judge streak and one peer's
# block inflated it, so every decision keyed off the streak was reading someone
# else's work. Fixed before the cadence lands, because the cadence's cap is the
# next thing to key off block streaks.
setup
say "done for now"
brief_now
hand_now
echo '- [ ] (deadbeef) open thing' >>"$WL"
run >/dev/null
if [[ -f "${WL%.md}.blocks-deadbeef" ]]; then
    pass "213: the counter is written per-session as .blocks-deadbeef"
else
    fail "213: no per-session counter; found: $(ls "${WL%.md}".blocks* 2>&1)"
fi

echo "== 213b. CONTROL: a PEER's counter is untouched by my stop =="
# The whole point. Plant a peer's streak, take a stop of my own, and it must
# survive byte-for-byte -- under the old shared file my stop would have
# overwritten or deleted it.
printf '7' >"${WL%.md}.blocks-cafe1234"
run >/dev/null
if [[ "$(cat "${WL%.md}.blocks-cafe1234" 2>/dev/null)" == "7" ]]; then
    pass "213b CONTROL: a peer's block streak survives my stop unchanged"
else
    fail "213b CONTROL: peer streak became '$(cat "${WL%.md}.blocks-cafe1234" 2>/dev/null)'"
fi

echo "== 214. THE CADENCE: the hook stands down for ONE turn after being answered =="
# Operator's ask: "1 report/update 1 others/order flow". The acceptance test is
# the plan's own sentence -- the cadence must make it easier to be HEARD, not
# easier to STOP -- so every guard below exists because the naive version fails
# it. These are the ONLY cases that exercise the cadence: run() defaults it off.
setup
CADENCE=on
say "answer

## Remaining
- stuff"
brief_now
hand_now
echo '- [ ] (deadbeef) open thing' >>"$WL"
check "214: the first stop still DEMANDS" block "OPEN worklist item"
newturn
say "I have now answered the demand

## Remaining
- stuff"
OUT="$(run)"
DEC="$(python3 -c 'import json,sys
raw=sys.stdin.read().strip()
print(json.loads(raw).get("decision","allow") if raw else "allow")' <<<"$OUT" 2>/dev/null)"
if [[ "$DEC" != "block" ]] && grep -qF "still outstanding" <<<"$OUT"; then
    pass "214: the next stop is PAUSED, and still names what is outstanding"
else
    fail "214: decision=$DEC out: ${OUT:0:220}"
fi

echo "== 214b. GUARD B: an unchanged message buys NOTHING =="
# Without this a session emits an empty turn after every block and gets a free
# allow every other stop, which is the exact regression the cadence must not be.
# No `say` between stops here, so the assistant message is byte-identical.
setup
CADENCE=on
say "answer

## Remaining
- stuff"
brief_now
hand_now
echo '- [ ] (deadbeef) open thing' >>"$WL"
check "214b: first stop demands" block "OPEN worklist item"
newturn
check "214b GUARD B: no new say means no pause, it demands again" block "OPEN worklist item"

echo "== 214c. GUARD A: the ALWAYS tier defeats the pause =="
# The integrity tier is the reason this machinery exists. A session that just
# answered still does not get a quiet turn while something urgent is outstanding.
setup
CADENCE=on
say "answer

## Remaining
- stuff"
brief_now
hand_now
echo '- [ ] (deadbeef) open thing' >>"$WL"
check "214c: first stop demands" block "OPEN worklist item"
newturn
say "answered, and now something urgent is also true

## Remaining
- stuff"
# hook-blind is an always-tier violation: an unparseable event.
printf 'not json at all' >"$BASE/t.jsonl"
# stderr is CAPTURED, not discarded. This case failed once in CI with an EMPTY
# OUT and passed locally at 735/0, and a discarded stderr is precisely why that
# was undiagnosable: an empty stdout looks identical whether the hook decided to
# allow or died before deciding. A test that cannot say WHICH of those happened
# sends its reader guessing at a difference the machine already knew.
_214c_err="$BASE/214c.stderr"
OUT="$(printf 'garbage-not-json' | TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" \
    WORKLIST_TASKS_DIR="$BASE/tasks" WORKLIST_AGENT_BRANCH=agenttest \
    WORKLIST_JUDGE=off WORKLIST_CADENCE=on python3 "$HOOK" 2>"$_214c_err")"
_214c_rc=$?
if grep -qF '"decision": "block"' <<<"$OUT"; then
    pass "214c GUARD A: an always-tier violation blocks even when a pause was owed"
else
    fail "214c GUARD A: the always tier was paused: rc=${_214c_rc} stdout=[${OUT:0:220}] stderr=[$(tr '\n' ' ' <"$_214c_err" 2>/dev/null | tail -c 400)]"
fi

echo "== 214d. a CLEAN stop consumes the debt =="
# The hook owes a quiet turn to a session it just interrupted, not a voucher
# redeemable whenever that session next happens to be blocked. Found by case
# 3619: block, clean allow, new item -- and the new item was silently paused.
setup
CADENCE=on
say "answer

## Remaining
- stuff"
brief_now
hand_now
echo '- [ ] (deadbeef) open thing' >>"$WL"
check "214d: first stop demands" block "OPEN worklist item"
sed -i 's/^- \[ \] (deadbeef) open thing/- [x] (deadbeef) open thing/' "$WL"
newturn
say "all done

## Remaining
- nothing"
check "214d: the clean stop allows" allow ""
echo '- [ ] (deadbeef) a brand new thing' >>"$WL"
newturn
say "starting the new thing

## Remaining
- the new thing"
check "214d: the NEW item demands, the debt was spent on the clean stop" block "OPEN worklist item"

echo "== 214e. WORKLIST_CADENCE=off restores the old behaviour exactly =="
# The kill switch has to work, or there is no way back if this proves wrong in
# daily use.
setup
CADENCE=off
say "answer

## Remaining
- stuff"
brief_now
hand_now
echo '- [ ] (deadbeef) open thing' >>"$WL"
check "214e: first stop demands" block "OPEN worklist item"
newturn
say "answered

## Remaining
- stuff"
check "214e: with cadence OFF it demands again immediately" block "OPEN worklist item"

echo "== 215. PLAN DRIFT: the session is bound to its own committed design record =="
# The gap the operator named: plans were surfaced at SessionStart and PostCompact
# and NOWHERE else, so a session could work all day while the committed plan
# describing that work went stale. plan_records() existed; nothing on the stop
# path called it.
setup
say "answer

## Remaining
- stuff"
brief_now
hand_now
mkdir -p "$BASE/proj/docs/agent/agenttest"
cat >"$BASE/proj/docs/agent/agenttest/PLAN-thing.md" <<'MD'
# PLAN: the thing
Status: executing
MD
# Backdate the plan, then move MY work after it. The trigger is the work, never
# the clock: a plan a week old on a branch where nothing moved is accurate.
touch -d '-2 hours' "$BASE/proj/docs/agent/agenttest/PLAN-thing.md"
# A TICKED item, deliberately. It stamps `upd` (which is what "my work moved"
# reads) without leaving anything open, so plan-drift is the ONLY rotating check
# outstanding. The focused block surfaces exactly one of those, so an open item
# here would win the rotation and this case would score whichever check happened
# to be picked -- which is how its first version passed its three controls while
# the thing they control for never fired at all.
# FOUR ticked items, not one. The check requires a THRESHOLD of moved work
# (PLAN_DRIFT_MIN_MOVES) rather than any movement at all, because a single tick
# is not a plan going stale -- and treating it as one made the check
# unsatisfiable: update the plan, tick the next item, stale again immediately.
for n in 1 2 3 4; do
    PID="$(reqcli --add deadbeef "work $n that outran the plan" | grep -o '#[0-9a-f]*' | head -1 | tr -d '#')"
    reqcli --tick deadbeef "$PID" "landed, suite green, exit 0" >/dev/null
done
check "215: a plan the work has moved past is flagged" block "PLAN-thing.md"

echo "== 215a. CONTROL: ONE tick is not a plan going stale =="
# The threshold is what makes the exit real. Without this control the check
# could go back to firing on any movement, which is the unsatisfiable version.
setup
say "answer

## Remaining
- stuff"
brief_now
hand_now
mkdir -p "$BASE/proj/docs/agent/agenttest"
cat >"$BASE/proj/docs/agent/agenttest/PLAN-thing.md" <<'MD'
# PLAN: the thing
Status: executing
MD
touch -d '-2 hours' "$BASE/proj/docs/agent/agenttest/PLAN-thing.md"
PID="$(reqcli --add deadbeef 'one small thing' | grep -o '#[0-9a-f]*' | head -1 | tr -d '#')"
reqcli --tick deadbeef "$PID" "landed, exit 0" >/dev/null
OUT="$(run)"
if ! grep -qF "PLAN-thing.md" <<<"$OUT"; then
    pass "215a CONTROL: a single tick does not stale a plan"
else
    fail "215a CONTROL: one tick flagged the plan: ${OUT:0:240}"
fi

echo "== 215b. CONTROL: the same plan, touched AFTER the work, is silent =="
# Without this the check could be firing on the mere existence of a plan file,
# which would make it noise within a day.
touch "$BASE/proj/docs/agent/agenttest/PLAN-thing.md"
newturn
say "still working

## Remaining
- stuff"
OUT="$(run)"
if ! grep -qF "PLAN-thing.md" <<<"$OUT"; then
    pass "215b CONTROL: an up-to-date plan is not flagged"
else
    fail "215b CONTROL: a fresh plan was still flagged: ${OUT:0:240}"
fi

echo "== 215c. CONTROL: a DONE plan is history and is never flagged =="
# Demanding edits to history is how a check earns its way into being ignored.
cat >"$BASE/proj/docs/agent/agenttest/PLAN-thing.md" <<'MD'
# PLAN: the thing
Status: done
MD
touch -d '-2 hours' "$BASE/proj/docs/agent/agenttest/PLAN-thing.md"
newturn
say "still working

## Remaining
- stuff"
OUT="$(run)"
if ! grep -qF "PLAN-thing.md" <<<"$OUT"; then
    pass "215c CONTROL: a done plan is never flagged"
else
    fail "215c CONTROL: a done plan was flagged: ${OUT:0:240}"
fi

echo "== 215d. CONTROL: a project with NO plan directory pays nothing and says nothing =="
setup
say "answer

## Remaining
- stuff"
brief_now
hand_now
echo '- [ ] (deadbeef) work with no plan anywhere' >>"$WL"
OUT="$(run)"
if ! grep -qF "committed plan file" <<<"$OUT"; then
    pass "215d CONTROL: no plan directory means no plan-drift complaint"
else
    fail "215d CONTROL: complained about plans that do not exist: ${OUT:0:240}"
fi

echo "== 216. an UNKNOWN plan carries a DESCRIPTION and FILE POINTERS =="
# An UNKNOWN status told the one reader who has no context precisely nothing:
# "this plan cannot be parsed", full stop. It now carries the plan's title and
# the files it keeps referring to, so a new or compacted session knows what to
# open first.
setup
say "answer

## Remaining
- stuff"
brief_now
hand_now
mkdir -p "$BASE/proj/docs/agent/agenttest"
cat >"$BASE/proj/docs/agent/agenttest/PLAN-mystery.md" <<'MD'
# PLAN: the mystery subject

**Status (dated parenthetical): this shape does not parse**

The work lives in pkg/chunkstore/pipeline_linux.go and pkg/chunkstore/pipeline_linux.go
again, plus cmd/renet/backup_snapshot.go. A passing mention of docs/agent/README.md.
MD
touch -d '-2 hours' "$BASE/proj/docs/agent/agenttest/PLAN-mystery.md"
for n in 1 2 3 4; do
    PID="$(reqcli --add deadbeef "work $n" | grep -o '#[0-9a-f]*' | head -1 | tr -d '#')"
    reqcli --tick deadbeef "$PID" "landed, exit 0" >/dev/null
done
OUT="$(run)"
if grep -qF "the mystery subject" <<<"$OUT" && grep -qF "pkg/chunkstore/pipeline_linux.go" <<<"$OUT"; then
    pass "216: an UNKNOWN plan names its subject and the files to open"
else
    fail "216: no orientation on an UNKNOWN plan: ${OUT:0:320}"
fi

echo "== 216b. CONTROL: the most-mentioned file leads, and the plan itself is never listed =="
# A plan's own path is not a pointer to anywhere useful, and a file mentioned
# once is a passing reference rather than the subject.
if ! grep -qF "PLAN-mystery.md; opens" <<<"$OUT" && ! grep -qF "opens: docs/agent/README.md" <<<"$OUT"; then
    pass "216b CONTROL: self-reference excluded and ranking puts the subject first"
else
    fail "216b CONTROL: bad pointer list: ${OUT:0:320}"
fi

echo "== 216c. CONTROL: a plan with a READABLE status gets no orientation =="
# The orientation is for UNKNOWN specifically. If it appeared on every row it
# would just be noise on plans whose state is already clear.
cat >"$BASE/proj/docs/agent/agenttest/PLAN-mystery.md" <<'MD'
# PLAN: the mystery subject
Status: executing

The work lives in pkg/chunkstore/pipeline_linux.go.
MD
touch -d '-2 hours' "$BASE/proj/docs/agent/agenttest/PLAN-mystery.md"
newturn
say "still working

## Remaining
- stuff"
OUT="$(run)"
if grep -qF "PLAN-mystery.md" <<<"$OUT" && ! grep -qF "opens:" <<<"$OUT"; then
    pass "216c CONTROL: a readable status is flagged without orientation noise"
else
    fail "216c CONTROL: ${OUT:0:320}"
fi

echo "== 217. --intent answers the two STATUS-QUESTION checks, and nothing else =="
# An intent is a statement of PLAN. Its whole legitimate power is answering the
# checks whose entire content is "what are you doing" -- brief and agent-state --
# and reordering attention. It is never evidence.
setup
say "answer

## Remaining
- stuff"
hand_now
printf '%s %s %s\n' deadbeef "$(date -u -d '-200 minutes' +%Y-%m-%dT%H:%M:%SZ)" "old" >>"${WL%.md}.sessions"
echo '- [ ] (deadbeef) open thing' >>"$WL"
check "217: without an intent the stale brief is one of the outstanding checks" block "OPEN worklist item"
reqcli --intent deadbeef "driving the open thing to green" --covers open-items --for 60 >/dev/null
OUT="$(run)"
if ! grep -qF "session brief is stale" <<<"$OUT"; then
    pass "217: a live intent answers the stale-brief question"
else
    fail "217: brief still fired under a live intent: ${OUT:0:260}"
fi

echo "== 217b. C8: an intent must NOT satisfy the TICK-EVIDENCE gate =="
# The plan names this as decisive. "I am working on it" is not evidence, and if
# an intent could close an item the ledger becomes a record of intentions.
IID="$(reqcli --add deadbeef 'needs real evidence' | grep -o '#[0-9a-f]*' | head -1 | tr -d '#')"
OUT="$(reqcli --tick deadbeef "$IID" "I have an intent covering this" 2>&1 || true)"
if grep -qF "REFUSED" <<<"$OUT"; then
    pass "217b C8: a tick still demands real evidence with an intent live"
else
    fail "217b C8: an intent satisfied the evidence gate: ${OUT:0:240}"
fi

echo "== 217c. an intent NEVER suppresses open-items, only reorders it =="
# Covered keys sort LAST but stay in `violations`, so the header count stays
# truthful. An intent reorders attention; it does not make work disappear.
OUT="$(run)"
if grep -qE "check\(s\) outstanding" <<<"$OUT"; then
    pass "217c: covered work is still counted as outstanding, not silently dropped"
else
    fail "217c: outstanding count vanished under an intent: ${OUT:0:240}"
fi

echo "== 217d. an EXPIRED intent becomes its own violation =="
# This is what stops --intent being a mute button: going quiet has a horizon,
# and outliving it while the work is still open is itself the finding.
setup
say "answer

## Remaining
- stuff"
brief_now
hand_now
# NO open item on purpose. The focused block surfaces ONE rotating check, so an
# open item here would win the rotation and this case would score whichever
# check happened to be picked rather than the expiry -- the same trap that made
# an earlier fixture pass its controls while the thing they controlled for never
# fired. An expired intent is a violation in its own right, which is precisely
# what stops --intent being a mute button.
python3 - "$WL" <<'PYEOF'
import json, sys, datetime, pathlib
p = pathlib.Path(sys.argv[1]).with_suffix(".intents")
old = (datetime.datetime.now(datetime.UTC) - datetime.timedelta(minutes=90)).strftime("%Y-%m-%dT%H:%M:%SZ")
p.write_text(json.dumps({"at": old, "by": "deadbeef", "text": "said long ago", "covers": ["open-items"], "min": 30}) + "\n")
PYEOF
check "217d: an expired intent blocks in its own right" block "stated intent has EXPIRED"

echo "== 210. the brief work-gate: an old brief on an UNCHANGED world =="
# A brief goes stale when the WORLD moves, not when the clock does. A sentence
# that still describes what this session is doing is still true at 200 minutes,
# and nagging for a rewrite of an accurate sentence trains the reader to dismiss
# the check.
#
# Uses the REAL --brief CLI, because only that path stamps the world signature
# the gate compares. The direct .sessions writes elsewhere in this suite
# deliberately carry no signature and must keep falling back to wall-clock --
# case 5 above is that fallback, and it still blocks.
#
# hand_now() is required, not decoration: the hook surfaces ONE outstanding
# check, so without a STATE.md this case would pass or fail on whichever
# complaint happened to win the rotation rather than on the brief.
setup
say "answer

## Remaining
- nothing open"
hand_now
TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" WORKLIST_TASKS_DIR="$BASE/tasks" \
    WORKLIST_AGENT_BRANCH=agenttest python3 "$HOOK" --brief deadbeef "doing the thing" >/dev/null 2>&1
# Backdate it. Last line for a prefix wins, so this is an append like any other.
printf '%s %s %s\n' deadbeef "$(date -u -d '-200 minutes' +%Y-%m-%dT%H:%M:%SZ)" "doing the thing" >>"${WL%.md}.sessions"
check_absent "an old brief on an unchanged world does NOT nag" allow "session brief is stale"

echo "== 210b. CONTROL: the same old brief once the world MOVES =="
# Without this the gate above could be a check that can never fire. Same fixture
# and the same 200-minute-old brief; the only difference is that the world moved,
# which is exactly when peers can no longer see what this session is doing.
#
# A DONE item, deliberately: it moves the item structure the signature covers
# without leaving anything open, so the brief stays the only thing left to
# complain about and the rotation cannot surface something else instead.
echo '- [x] (deadbeef) a finished piece of work' >>"$WL"
check "an old brief blocks once the world has moved" block "session brief is stale"

echo
echo "  passed=$PASS failed=$FAIL"
[[ "$FAIL" -eq 0 ]]
