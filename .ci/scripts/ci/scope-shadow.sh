#!/bin/bash
# Scope engine, LIVE. It decides which CI jobs may skip.
#
# It was SHADOW until 2026-07-31: it wrote artifacts, gated nothing, and every
# job ran regardless. D-1 flipped it. The FILENAME is deliberately unchanged,
# because ci.yml wires this exact path and a rename would be a second thing to
# get wrong on the day the polarity flips.
#
# THE CONTRACT. Into OUTPUT_FILE (the step's $GITHUB_OUTPUT) this writes, for
# every plan key whose entry says `run: false`, exactly one line:
#
#     run_<key>=false
#
# plus exactly one `scope_mode=<full|reduced>` line. It NEVER writes
# `run_<key>=true`, and that asymmetry IS the fail-open. A consumer reads an
# absent output as the empty string, and every job condition is written to run
# unless it reads the literal 'false', so ANY failure here (engine crash,
# timeout, unwritable plan, a plan whose key set has drifted from scope-map's)
# emits ZERO false lines and the round is full. There is no error path that can
# shrink a run; only paths that stop shrinking it.
#
# THREE KILL SWITCHES, in increasing order of blast radius:
#   1. put the `full-ci` label on the PR      -> FULL_CI_LABEL=true here
#   2. set the `FULL_CI` repository variable  -> FORCE_FULL_CI=true here
#   3. delete this step from ci.yml           -> no outputs at all, full CI
# The first two are checked BEFORE the engine runs. An operator forcing a full
# round must not have to wait on a baseline walk, and must not depend on the
# engine being healthy enough to answer.
#
# THE DECIDING PLAN IS THE BASELINE PLAN, and those used to be two different
# objects. plan.json was built from --classify over the MERGE-BASE delta, while
# the reduction that would actually matter came from --resolve-baseline; the
# reconciler then verified the classify plan and attested nothing about the
# plan that gated anything. plan.json is now written from scope-baseline.json,
# so the plan that gates jobs, the plan that is uploaded, and the plan the
# reconciler checks are ONE object. The merge-base classify survives as a
# DIAGNOSTIC in the step summary and the shadow artifact; nothing reads it.
#
# WHY --resolve-baseline is the right source and the merge base is not: the
# merge base does not move when a second commit lands on the PR branch, so
# every push re-diffs the whole branch and the tenth push costs what the first
# did. The baseline that expresses "CI was green, then one line changed" is the
# newest ANCESTOR OF HEAD whose own run was green, ran a FULL suite, and proved
# it with a reconciled skip-plan.
#
# WHAT IT STILL DELIBERATELY DOES NOT DO: it does not write a `reconciled`
# flag. Doing so would attest to an outcome nobody verified, and the engine
# would then chain reduced rounds off an unverified baseline. The READER
# derives that flag, per candidate, at read time (scope-engine.cjs's
# attestPlan).
#
# REQUIRED ENV
#   MERGE_SHA           github.sha (CI checks out the MERGE commit)
#   HEAD_SHA            github.event.pull_request.head.sha (fallback only)
#   GITHUB_REPOSITORY   owner/name, for `gh run list`
#   GITHUB_RUN_ID       stamped into the plan; the reconciler refuses a plan
#                       that does not name the run it was downloaded from
#   GH_TOKEN            needs `actions: read` for the run/artifact lookups
#   OUTPUT_FILE         the step's $GITHUB_OUTPUT. UNSET is supported and means
#                       "decide nothing": the plan is still written and
#                       uploaded, no outputs are emitted. That is what a local
#                       run gets, and it is the old shadow behaviour exactly.
#   FORCE_FULL_CI       'true' => kill switch 2 (the FULL_CI repo variable)
#   FULL_CI_LABEL       'true' => kill switch 1 (the full-ci PR label)
#   FULL_SUITE / POINTER_BUMP_ONLY / IS_BOT
#                       the pre-existing skip conditions, recorded in the plan
#   GITHUB_STEP_SUMMARY optional; falls back to stdout when running locally
#
# REQUIRES a non-shallow clone. With the default depth-1 checkout the engine
# answers `baseline:shallow-clone` on every run and reports full CI forever
# while looking healthy, which is D9's exact failure shape. The `fetch-depth: 0`
# on initialize's checkout and this script land together or not at all.
#
# LOCAL RUN (no OUTPUT_FILE, so it decides nothing)
#   MERGE_SHA=$(git rev-parse HEAD) HEAD_SHA=$(git rev-parse HEAD) \
#   GITHUB_REPOSITORY=rediacc/console .ci/scripts/ci/scope-shadow.sh

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENGINE="$SCRIPT_DIR/scope-engine.cjs"
GREENLIGHT="$SCRIPT_DIR/greenlight.cjs"
RECONCILER="$SCRIPT_DIR/skip-plan-reconcile.cjs"
SCOPE_MAP="$SCRIPT_DIR/scope-map.cjs"
SUMMARY="${GITHUB_STEP_SUMMARY:-/dev/stdout}"

# Outputs go under .ci/cache/ (gitignored, .gitignore:118) rather than the repo
# root. Running this locally used to drop changed.raw and three scope-*.json
# files as untracked litter in the working tree, which in a repo where sessions
# share a tree is one `git add -A` away from being committed by someone else.
OUT_DIR="${SCOPE_SHADOW_OUT:-$SCRIPT_DIR/../../cache/scope-shadow}"
mkdir -p "$OUT_DIR"

# Emit to BOTH the step summary and stdout.
#
# The summary alone was a mistake: GitHub exposes no API for step summaries
# (the job object has no summary field), so everything this script reported was
# readable only by a human in the web UI. An automated caller - the thing most
# likely to be reading this verdict - saw an empty job log and could not tell
# "reported nothing" from "never ran". That is the same unreadable-instrument
# failure this whole mechanism exists to avoid.
#
# stdout lands in the job log, which IS in the API.
emit() {
    printf '%s\n' "$@" | tee -a "$SUMMARY"
}

# Time bound on every external call. This runs inside `initialize`, which every
# other job depends on, so a hang here stalls the ENTIRE pipeline rather than
# just losing a measurement. --resolve-baseline makes up to `limit` candidate
# lookups, each one a `gh run list` plus a `gh run download`, so the call count
# is bounded but the latency is not. A timeout kills the node process, which
# leaves no plan, which emits no false lines, which is a full round: the
# expensive-but-correct direction.
SCOPE_TIMEOUT="${SCOPE_SHADOW_TIMEOUT:-120}"
bounded() { timeout "$SCOPE_TIMEOUT" "$@"; }

# CI checks out the merge commit, whose ^1 is the base and ^2 the PR head.
# Both may be absent (a non-merge checkout, or a shallow clone that never
# fetched the parents), so neither is assumed.
# `--verify -q` is load-bearing. Plain `git rev-parse SHA^2` on a NON-merge
# commit prints the unresolved ref to stdout before failing, so a
# `|| echo "$HEAD_SHA"` fallback yields TWO lines and every downstream use gets
# garbage. Caught by running this: head became "<sha>\n<sha>^2", the diff came
# back empty, and the engine dutifully reported `empty-delta` -- which is
# indistinguishable in the log from a PR that genuinely changed nothing.
#
# `:-` on every one of these, and it is not defensive noise. Under `set -u` an
# unbound MERGE_SHA or GITHUB_REPOSITORY aborts the shell mid-script with
# "unbound variable" and a NON-ZERO status, which would break the one promise
# this file makes (it always exits 0) at the very moment something upstream is
# already wrong. Empty degrades correctly instead: no base, no head, no
# baseline, no outputs, full round.
base="$(git rev-parse --verify -q "${MERGE_SHA:-}^1" 2>/dev/null || true)"
head="$(git rev-parse --verify -q "${MERGE_SHA:-}^2" 2>/dev/null || true)"
[[ -z "$head" ]] && head="${HEAD_SHA:-}"
shallow="$(git rev-parse --is-shallow-repository 2>/dev/null || echo unknown)"

emit "### Scope engine (LIVE: this decides which jobs run)" \
    "" \
    "shallow: \`${shallow}\` (must be false, or nothing below is meaningful)" \
    "base: \`${base:-unknown}\`  head: \`${head:-unknown}\`" \
    ""

# ---------------------------------------------------------------------------
# write_plan <source-plan.json|FORCED> -- write $OUT_DIR/plan.json, or fail.
#
# ONE writer for both paths (operator-forced full, and engine-resolved), so the
# forced plan cannot drift from the shape the reconciler expects: same
# run_id/base_sha/head_sha stamping, same annotatePlan() over the same three
# tri-state conditions, same job table (forcedFullPlan builds THROUGH
# scopeMap.buildPlan for exactly this reason).
#
# No `2>/dev/null || true`, and its absence is a fix rather than a style
# choice. Swallowing this writer's stderr made a crash indistinguishable from
# "no plan was due": the upload step carries `if-no-files-found: ignore`, so a
# broken writer produced no artifact and the reconcile step then reported the
# benign-sounding "no attested plan for this run", one run after another, with
# the actual exception thrown away.
#
# IT ALSO RECORDS THE PRE-EXISTING SKIP CONDITIONS, which is what makes the
# reconcile non-vacuous. The scope verdict alone is an incomplete prediction:
# ci.yml skips whole columns for reasons that predate the engine (`full_suite`
# is false on push-to-main, `pointer_bump_only` cuts the entire expensive
# pipeline, `is_bot` cuts the staging chain), so a plan saying "unit runs" is
# wrong on every pointer-bump PR and the reconciler would red seventeen keys on
# a run where nothing went wrong. annotatePlan() writes the observed values and
# the per-job condition; the reconciler re-derives from the same table and
# hard-fails on disagreement, so writer and reader cannot drift.
#
# TRI-STATE ON PURPOSE. Each value is passed through as the literal string and
# annotatePlan records it only when it is exactly "true" or "false". An unset
# variable is OMITTED rather than defaulted, because both defaults are wrong:
# defaulting full_suite to false would exempt sixteen keys on no evidence.
# Omitted means no exemption, which leaves the reconciler at its strict
# reading. Missing information must never widen an exemption.
# ---------------------------------------------------------------------------
write_plan() {
    bounded node -e '
const fs = require("fs");
const { annotatePlan } = require(process.argv[1]);
const src = process.argv[2];
const plan =
  src === "FORCED"
    ? require(process.argv[6]).forcedFullPlan("operator-forced-full")
    : JSON.parse(fs.readFileSync(src, "utf8"));
plan.run_id = Number(process.env.GITHUB_RUN_ID || 0);
plan.base_sha = process.argv[3] || null;
plan.head_sha = process.argv[4] || null;
const tri = (v) => (v === "true" ? true : v === "false" ? false : undefined);
annotatePlan(plan, {
  full_suite: tri(process.env.FULL_SUITE),
  pointer_bump_only: tri(process.env.POINTER_BUMP_ONLY),
  is_bot: tri(process.env.IS_BOT),
});
fs.writeFileSync(process.argv[5], JSON.stringify(plan, null, 2));
' "$RECONCILER" "$1" "$base" "$head" "$OUT_DIR/plan.json" "$ENGINE" \
        2>"$OUT_DIR/plan-write.err"
}

# ---------------------------------------------------------------------------
# emit_outputs -- append the run_* false lines and scope_mode to OUTPUT_FILE.
#
# CALLED ONLY AFTER plan.json HAS WRITTEN. The plan is the artifact the
# reconciler audits this run against; emitting a reduction the reconciler will
# never see a plan for is a skip nobody can attest.
#
# ALL-OR-NOTHING, via a temp buffer appended in one `cat`. A node process that
# died halfway through printing would otherwise leave a PREFIX of the false
# lines in $GITHUB_OUTPUT: some jobs skipped, others not, and no plan entry
# explaining the difference. Building the whole block first means a partial
# failure appends nothing.
#
# TWO REFUSALS ARE ENCODED HERE, both landing on zero false lines:
#   - a mode that is neither 'full' nor 'reduced' (a corrupt or truncated plan);
#   - a plan whose key set is not EXACTLY scope-map's JOB_SURFACES. That is the
#     drift detector: add an 18th surface and the workflow's 17 inputs no
#     longer describe the plan, so the round goes full until someone wires the
#     new key. Emitting the 17 it recognises and ignoring the 18th would skip
#     jobs against a plan the reconciler reads differently.
# ---------------------------------------------------------------------------
emit_outputs() {
    [[ -n "${OUTPUT_FILE:-}" ]] || return 0
    local buf="$OUT_DIR/gh-output.txt"
    if ! bounded node -e '
const fs = require("fs");
const { JOB_SURFACES } = require(process.argv[1]);
const plan = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
const mode = plan.mode;
if (mode !== "full" && mode !== "reduced") {
  throw new Error(`unusable plan mode: ${JSON.stringify(mode)}`);
}
const jobs = plan.jobs && typeof plan.jobs === "object" ? plan.jobs : {};
const planned = Object.keys(jobs).sort().join(",");
const known = Object.keys(JOB_SURFACES).sort().join(",");
if (planned !== known) {
  throw new Error(`plan key set drifted from scope-map\n  plan: ${planned}\n  map:  ${known}`);
}
const lines = [];
for (const key of Object.keys(JOB_SURFACES)) {
  if (jobs[key] && jobs[key].run === false) lines.push(`run_${key}=false`);
}
lines.push(`scope_mode=${mode}`);
process.stdout.write(`${lines.join("\n")}\n`);
' "$SCOPE_MAP" "$OUT_DIR/plan.json" >"$buf" 2>"$OUT_DIR/output-emit.err"; then
        emit "_**the output emitter FAILED**: no run_* line was written, so every job" \
            "runs. This is a full round with a stated reason, not a silent one._" '```'
        head -c 1000 "$OUT_DIR/output-emit.err" | tee -a "$SUMMARY"
        emit '```' ""
        return 1
    fi
    cat "$buf" >>"$OUTPUT_FILE" || return 1
    emit "**outputs written to \$GITHUB_OUTPUT**" "" '```'
    cat "$buf" | tee -a "$SUMMARY"
    emit '```' ""
}

# ---------------------------------------------------------------------------
# apply_greenlight -- the CROSS-PR half, run after the plan is written and
# before any output is emitted.
#
# The scope engine asks a lineage-local question: did the delta against THIS
# branch's baseline touch the job's surface. greenlight.cjs asks a wider one:
# has this exact input closure already been executed green by any run on any
# branch. A rebase, or a second PR bumping the same submodule pointer, is
# invisible to the first question and answerable by the second.
#
# IT RUNS ON THE PLAN, NOT ALONGSIDE IT. plan.json stays the single object that
# gates jobs, gets uploaded, and is audited: this rewrites the entry rather
# than emitting a parallel output, so emit_outputs below derives every run_*
# line from one source and a greenlit skip is one the reconciler can see and
# attest. The reason string names the evidence run, which is the whole audit
# trail (the reconciler reads `run` and `preexisting_skip`, never `reason`, so
# this annotates without changing any verdict).
#
# MODE FLIPS TO reduced, because the plan no longer describes a round that
# executed everything and `mode` is what arms the reconcile gate downstream.
#
# It does NOT, since 2026-08-05, disqualify the run as a future baseline, and
# the correction matters: `renet` and `account_e2e` closures change rarely, so
# this flip fired on nearly every console run and every later walk then refused
# its own parent as 'reduced-baseline'. Measured across 14 consecutive PR runs
# (30944973190..30983418337), not one job was ever skipped by SCOPE. The
# baseline reader now asks per key whether the work was covered -- executed, or
# skipped on greenlight evidence that a different run executed the identical
# closure green -- instead of reading this aggregate label. See
# scope-engine.cjs's planCoverageIsFull. A key skipped as 'out-of-scope' still
# covers nothing, so scope evidence still cannot chain (case 1).
#
# THE PARSE IS DELIBERATELY STRICT: only a line matching exactly
# `run_<key>=false`, paired with an `evidence_<key>=<digits>` line, does
# anything. Any other output, including a hypothetical `=true`, is inert. That
# keeps the fail-open contract intact on this side of the pipe too, so the
# reader cannot be talked into widening a round by a malformed emit.
#
# Every failure path here returns without touching plan.json, which leaves the
# scope engine's verdict exactly as it was: no greenlight, no change.
# ---------------------------------------------------------------------------
# greenlight_digest <err-file> -- one line per key, instead of the raw trail.
#
# WHY THIS EXISTS. The trail is what makes a non-greenlight diagnosable at all,
# and it used to be dumped raw under `head -c 3000`. That was ample for two
# keys. At eighteen keys against a 25-run candidate list it is ~450 rows and
# ~30 KB, so the raw dump truncated MID-LINE inside the second key and the
# other sixteen were simply absent from the summary. A trail nobody can read is
# the unreadable-instrument failure this file was written to fix, arriving by
# the back door, so the surfacing is condensed rather than the cap raised: the
# per-key verdict and the NEWEST candidate's refusal answer "why did this not
# greenlight" in one line, and the remaining rows are almost always the same
# reason repeated down the list.
#
# Anything the digest does not recognise is passed through verbatim. A key
# whose local inputs were unreadable, or an engine that died with a message
# nobody anticipated, must not be filtered into silence.
greenlight_digest() {
    awk '
    /^greenlight\[/ {
        key = $0
        sub(/^greenlight\[/, "", key)
        sub(/\].*/, "", key)
    }
    # Header lines: remembered, not printed.
    /^greenlight\[[^]]*\] jobs=/ { next }
    /^greenlight\[[^]]*\] pins=/ { next }
    /^greenlight\[[^]]*\] closure=/ {
        if (!(key in seen)) { order[++n] = key; seen[key] = 1 }
        h = $0
        sub(/^.*closure=/, "", h)
        sub(/ .*$/, "", h)
        hash[key] = substr(h, 1, 12)
        next
    }
    # The trail table: count every row, keep only the newest.
    /^ +run id/ { next }
    /^ +[0-9]+ +/ {
        walked[key]++
        if (!(key in newest)) {
            row = $0
            sub(/^ +[0-9]+ +[0-9a-f]* +/, "", row)
            newest[key] = $1 " " row
        }
        next
    }
    /^greenlight\[[^]]*\] VERDICT: / {
        v = $0
        sub(/^.*VERDICT: /, "", v)
        verdict[key] = v
        next
    }
    # The per-key one-liner the engine already prints is redundant with the
    # VERDICT line; everything else is unrecognised and survives.
    /^greenlight\[[^]]*\]: (GREENLIT by run|no greenlight)/ { next }
    /^[[:space:]]*$/ { next }
    { print }
    END {
        for (i = 1; i <= n; i++) {
            k = order[i]
            printf "%-22s %-28s closure=%s walked=%d\n", k, verdict[k], hash[k], walked[k]
            if (k in newest) printf "%-22s   newest %s\n", "", newest[k]
        }
    }
    ' "$1"
}

apply_greenlight() {
    [[ -f "$GREENLIGHT" ]] || return 0
    [[ -s "$OUT_DIR/plan.json" ]] || return 0

    # Ask only about keys the engine still plans to RUN. A key already skipped
    # needs no second opinion, and every key asked costs API calls inside
    # `initialize`, which every other job waits on.
    #
    # ORDER IS COST-DESCENDING and it is CLOSURES' own key order that carries
    # it: Object.keys over string keys is insertion-ordered by the language
    # spec, and `filter` preserves that, so the list below arrives most
    # expensive first (e2e_workers, five 90-minute legs) and cheapest last
    # (unit, fourteen minutes on ubuntu-slim). That matters because the budget
    # is per INVOCATION, not per key: a walk that runs out of time abandons the
    # tail of this list, and the tail is where the cheap keys are. Sorting here
    # instead would need a second copy of the cost ranking to drift out of
    # step with the table. test-greenlight.sh pins both ends of the order.
    local pending
    pending="$(bounded node -e '
const fs = require("fs");
const { CLOSURES } = require(process.argv[1]);
const plan = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
const jobs = (plan && plan.jobs) || {};
const pending = Object.keys(CLOSURES).filter((k) => jobs[k] && jobs[k].run !== false);
process.stdout.write(pending.join(" "));
' "$GREENLIGHT" "$OUT_DIR/plan.json" 2>"$OUT_DIR/greenlight.err")" || pending=""

    if [[ -z "$pending" ]]; then
        emit "_greenlight: nothing to ask (every eligible key is already planned to skip)._" ""
        return 0
    fi

    local args=()
    local key
    for key in $pending; do
        args+=(--key "$key")
    done

    # --budget 90, up from the engine's own default of 60. The walk is now over
    # eighteen keys rather than two, and while the per-candidate API cost is
    # set by the UNION of the closures (every listing is cached per ref and
    # shared across keys), a full candidate still costs one paginated jobs read
    # plus roughly twenty directory listings. 60s was already the measured
    # death of a two-key walk on a candidate list that was mostly jobs reads.
    # 90 stays inside `bounded`'s 120s ceiling, so `initialize` gets at most
    # ~30s slower in the worst case, against skipping up to nine VM-hours.
    # --limit 60, not the default 25. A GREENLIT run cannot serve as evidence
    # for the next one (rule 1 refuses `skipped`, greenlight.cjs:675-697), so the
    # last EXECUTING run recedes one slot per push. Measured on run 32946684108:
    # renet, package_tests and license_enforcement were already at walked=21 of
    # 24 -- three pushes from falling off the window, at which point CI silently
    # reverts to running the 90-minute suites. Nobody would see that happen.
    #
    # Widening is monotone in the SAFE direction: it only ever extends the search
    # for an EXISTING proof and cannot manufacture one, because rules 1-3 are
    # unchanged. The cost is bounded by --budget 90 inside bounded's 120s
    # ceiling, and if the budget runs out the candidate reader THROWS
    # (greenlight.cjs:875-877) rather than returning a benign empty value. Key
    # order is cost-descending (greenlight.cjs:81-85), so the keys that go
    # unasked are the cheap ones -- and unasked means RUN.
    if ! bounded node "$GREENLIGHT" --repo "${GITHUB_REPOSITORY:-}" --limit 60 --budget 90 --debug "${args[@]}" \
        >"$OUT_DIR/greenlight.out" 2>"$OUT_DIR/greenlight.err"; then
        emit "_greenlight: the engine did not complete (timeout or crash), so no key was" \
            "greenlit and the scope verdict stands unchanged._" ""
        return 0
    fi

    local applied
    applied="$(bounded node -e '
const fs = require("fs");
const planPath = process.argv[1];
const plan = JSON.parse(fs.readFileSync(planPath, "utf8"));
const emitted = fs.readFileSync(process.argv[2], "utf8");
const evidence = {};
const granted = [];
for (const line of emitted.split("\n")) {
  let m = /^run_([a-z0-9_]+)=false$/.exec(line);
  if (m) {
    granted.push(m[1]);
    continue;
  }
  m = /^evidence_([a-z0-9_]+)=([0-9]+)$/.exec(line);
  if (m) evidence[m[1]] = m[2];
}
const applied = [];
for (const key of granted) {
  const job = plan.jobs && plan.jobs[key];
  // An unknown key, an already-skipped one, or a grant with no evidence run
  // attached is ignored rather than guessed at.
  if (!job || job.run === false || !evidence[key]) continue;
  job.run = false;
  job.reason = `greenlight:${evidence[key]}`;
  applied.push(`${key}=${evidence[key]}`);
}
if (applied.length > 0) {
  plan.mode = "reduced";
  fs.writeFileSync(planPath, JSON.stringify(plan, null, 2));
}
process.stdout.write(applied.join(" "));
' "$OUT_DIR/plan.json" "$OUT_DIR/greenlight.out" 2>>"$OUT_DIR/greenlight.err")" || applied=""

    emit "**cross-PR greenlight** (asked about: ${pending})" "" '```'
    greenlight_digest "$OUT_DIR/greenlight.err" | tee -a "$SUMMARY"
    emit '```'
    if [[ -n "$applied" ]]; then
        emit "**greenlit, and the plan now says so**: \`${applied}\`" ""
    else
        emit "_no key was greenlit; the scope engine's verdict stands unchanged._" ""
    fi
}

# ---------------------------------------------------------------------------
# KILL SWITCH, CHECKED BEFORE THE ENGINE. See the header for all three.
#
# The plan is still written and uploaded on this path, because a forced full
# round is a perfectly good BASELINE for the next one: it ran everything.
# Dropping the artifact here would make the operator's "just run everything"
# cost the FOLLOWING PR a full round too, which is the opposite of what they
# asked for.
# ---------------------------------------------------------------------------
if [[ "${FORCE_FULL_CI:-}" == "true" || "${FULL_CI_LABEL:-}" == "true" ]]; then
    override_reason="the FULL_CI repository variable"
    [[ "${FULL_CI_LABEL:-}" == "true" ]] && override_reason="the full-ci PR label"
    emit "**OPERATOR OVERRIDE: full CI forced** by ${override_reason}." \
        "The engine did not run: no baseline walk, no classify, no reduction." ""
    if write_plan FORCED; then
        emit_outputs
    else
        emit "_**the forced-full plan writer FAILED**: no attested plan will be" \
            "uploaded for this run, so the reconcile step will report 'no attested" \
            "plan' and that will be a GAP IN THE EVIDENCE, not a clean result._" '```'
        head -c 1000 "$OUT_DIR/plan-write.err" | tee -a "$SUMMARY"
        emit '```' ""
    fi
    exit 0
fi

# DIAGNOSTIC ONLY, and the demotion is the point. This is the merge-base
# delta, which is what the engine USED to plan from; it is kept because a
# side-by-side with the baseline verdict is how a wrong reduction gets
# diagnosed, and because it is the only reading available when no baseline
# resolves. Nothing downstream reads scope-classify.json.
if [[ -n "$base" && -n "$head" ]]; then
    git diff-tree -r --raw --no-commit-id "$base" "$head" >"$OUT_DIR/changed.raw" 2>/dev/null || true
    bounded node "$ENGINE" --classify --files "$OUT_DIR/changed.raw" >"$OUT_DIR/scope-classify.json" 2>/dev/null || true
    emit "**--classify over the merge-base delta** (diagnostic; decides nothing)" "" '```json'
    head -c 4000 "$OUT_DIR/scope-classify.json" 2>/dev/null | tee -a "$SUMMARY" || emit "(no output)"
    emit '```' ""
else
    emit "_skipped --classify: no base/head pair resolved_" ""
fi

# THE DECIDING PLAN. Every failure mode inside resolveBaseline already resolves
# to a forced-full plan carrying a `baseline:<reason>`, so a non-empty
# scope-baseline.json is either a real reduction or a stated full round. An
# EMPTY or absent one (the engine crashed, or was killed by `bounded`) writes
# no plan below, which emits no outputs, which is also full.
if [[ -n "$head" ]]; then
    bounded node "$ENGINE" --resolve-baseline \
        --repo "${GITHUB_REPOSITORY:-}" --head "$head" --merge-sha "${MERGE_SHA:-}" \
        >"$OUT_DIR/scope-baseline.json" 2>"$OUT_DIR/scope-baseline.err" || true
    emit "**--resolve-baseline** (THIS is the plan that gates jobs)" "" '```json'
    head -c 4000 "$OUT_DIR/scope-baseline.json" 2>/dev/null | tee -a "$SUMMARY" || emit "(no output)"
    emit '```'
    if [[ -s "$OUT_DIR/scope-baseline.err" ]]; then
        emit "stderr:" '```'
        head -c 1000 "$OUT_DIR/scope-baseline.err" | tee -a "$SUMMARY"
        emit '```'
    fi
else
    emit "_skipped --resolve-baseline: no head sha resolved, so this round is full_" ""
fi

# The plan is uploaded under the name --resolve-baseline looks for on a LATER
# run, which is what proves the artifact path end to end (upload here, discover
# and download on a later run) -- the half that cannot be unit-tested. It
# carries no `reconciled` flag; the reader recomputes that per candidate.
if [[ -s "$OUT_DIR/scope-baseline.json" ]]; then
    if ! write_plan "$OUT_DIR/scope-baseline.json"; then
        emit "_**the plan writer FAILED**: no attested plan will be uploaded for this" \
            "run and NO run_* output was written, so every job runs and the reconcile" \
            "step will report 'no attested plan'. That is a GAP IN THE EVIDENCE, not a" \
            "clean result._" '```'
        head -c 1000 "$OUT_DIR/plan-write.err" | tee -a "$SUMMARY"
        emit '```' ""
    else
        emit "**pre-existing skip conditions recorded in the plan**" "" '```json'
        bounded node -e '
const p = JSON.parse(require("fs").readFileSync(process.argv[1], "utf8"));
const exempt = Object.entries(p.jobs || {})
  .filter(([, v]) => v && v.preexisting_skip)
  .map(([k, v]) => `${k}:${v.preexisting_skip}`);
process.stdout.write(JSON.stringify({
  conditions: p.conditions,
  exempt_keys: exempt,
  planned_keys: Object.keys(p.jobs || {}).length,
}, null, 2) + "\n");
' "$OUT_DIR/plan.json" | tee -a "$SUMMARY"
        emit '```' ""
        # AFTER the plan is written and BEFORE anything is emitted: the
        # greenlight only ever rewrites plan.json, and emit_outputs is the one
        # thing that turns a plan into outputs.
        apply_greenlight
        emit_outputs
    fi
else
    emit "_no baseline plan was produced, so no run_* output was written: full round._" ""
fi

# Always green. This script decides what runs; it must never be what fails.
# Every path above either emits a reduction it has a written plan for, or emits
# nothing and says why.
exit 0
