#!/bin/bash
# Part of the worklist v5 control suite. SOURCED by
# `.claude/hooks/stop/test-worklist-v5.sh`, never run on its own: the harness
# (setup, check, run, the PASS/FAIL counters) lives in `_harness.sh` and every
# fixture path comes from the runner. Running this file directly does nothing
# useful and is not how CI reaches it.
#
# Submodule pointer drift and the CI-status check: failing jobs, cancels, watchdog retries, armed watches, the ceiling.

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
BG='[{"id":"w1","status":"running","description":"watch CI","command":".ci/scripts/ci/ci-trace.py --wait"}]'
cichk "an armed watch on the current run is the wake-up; the hook stays quiet" no "CI IS RED"

echo "== 127. a COMPLETED watch, or one on a SUPERSEDED run, does NOT count as armed =="
# Both happened: a completed watch reported completed/cancelled for a run that
# had since been superseded, and another reported a FALSE failure because a
# watchdog rerun flipped a terminal run back to in_progress.
ci_setup
ci_rollup FAILURE "[$(ci_job "Quality / Static" FAILURE)]"
BG='[{"id":"w1","status":"completed","description":"watch","command":".ci/scripts/ci/ci-trace.py --wait"},
     {"id":"w2","status":"running","description":"watch","command":".ci/scripts/ci/ci-trace.py --wait --ref other"}]'
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
