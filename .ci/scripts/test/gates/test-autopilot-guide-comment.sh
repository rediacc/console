#!/bin/bash
# Behavioural test for .ci/scripts/ci/autopilot-guide-comment.cjs.
#
# Structurally a mirror of test-label-guide-comment.sh, because the module is a
# mirror of that poster: same marker discipline, same bot-only ownership, same
# create/update/no-op contract driven against a fake GitHub client and asserted
# on the CALL TRACE. The no-op case is the load-bearing one and is asserted as
# an EXACTLY-EQUAL trace rather than as "no create": a version that skipped
# createComment but still called updateComment every run would pass a weaker
# assertion while producing the same edit-spam on every push.
#
# PLUS ONE THING THE LABEL GUIDE DOES NOT NEED. That guide is a projection of
# .github/labels.yml, so it cannot disagree with its source. This one is prose
# about a workflow, and prose rots. So every FACT it quotes -- each variable
# name, both label names, the round cap, the turn caps, the round actions -- is
# re-checked here against the file it was taken from. A rename in autopilot.yml
# turns this test red instead of leaving a confidently wrong comment on every
# PR, which is the failure this file exists to prevent.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
# shellcheck source=../lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test/gates/test-*.sh
source "$SCRIPT_DIR/../lib/test-helpers.sh"

MODULE="$REPO_ROOT/.ci/scripts/ci/autopilot-guide-comment.cjs"
LABEL_MODULE="$REPO_ROOT/.ci/scripts/ci/label-guide-comment.cjs"
AUTOPILOT_WF="$REPO_ROOT/.github/workflows/autopilot.yml"
GATE_SH="$REPO_ROOT/.ci/scripts/autopilot/autopilot-gate.sh"
MODEL_ARGS_SH="$REPO_ROOT/.ci/scripts/autopilot/resolve-model-args.sh"
LABELS_FILE="$REPO_ROOT/.github/labels.yml"
CI_WORKFLOW="$REPO_ROOT/.github/workflows/ci.yml"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

for f in "$MODULE" "$AUTOPILOT_WF" "$GATE_SH" "$MODEL_ARGS_SH" "$LABELS_FILE" "$CI_WORKFLOW"; do
    [ -r "$f" ] || log_fail "missing input: $f (this test verifies the guide against its sources; it cannot run without them)"
done

cat >"$WORK/harness.cjs" <<'HARNESS'
const mod = require(process.argv[2]);
const comments = JSON.parse(process.argv[3]);

// A fixture body of "@@RENDER@@" means "byte-identical to what the module would
// render right now". Hand-copying the expected body into the fixture would make
// the no-op case pass for the wrong reason the moment the renderer changed.
for (const c of comments) if (c.body === '@@RENDER@@') c.body = mod.renderBody();

const trace = [];
const github = {
  paginate: async (fn, params) => { trace.push(`list-comments:${params.issue_number}`); return comments; },
  rest: {
    issues: {
      listComments: () => {},
      createComment: async (p) => { trace.push(`create:${p.issue_number}`); global.__body = p.body; return {}; },
      updateComment: async (p) => { trace.push(`update:${p.comment_id}`); global.__body = p.body; return {}; },
    },
  },
};
const core = { info: (m) => trace.push(`info:${String(m).slice(0, 12)}`) };
const context = { repo: { owner: 'rediacc', repo: 'console' }, payload: { pull_request: { number: 5 } } };

mod({ github, context, core })
  .then((verdict) => {
    console.log('TRACE=' + trace.join('|'));
    console.log('VERDICT=' + verdict);
    if (global.__body) console.log('BODY=' + JSON.stringify(global.__body));
  })
  .catch((e) => { console.log('THREW=' + e.message.replace(/\n/g, ' ')); process.exitCode = 3; });
HARNESS

run_guide() { node "$WORK/harness.cjs" "$MODULE" "$1" 2>/dev/null || true; }
trace_of() { run_guide "$1" | sed -n 's/^TRACE=//p'; }
verdict_of() { run_guide "$1" | sed -n 's/^VERDICT=//p'; }

# The rendered body, unescaped, for the content assertions.
rendered_body() {
    node -e 'process.stdout.write(require(process.argv[1]).renderBody())' "$MODULE"
}

BOT='"user":{"type":"Bot","login":"github-actions[bot]"}'
HUMAN='"user":{"type":"User","login":"an-outsider"}'
MARKER='<!-- rediacc:autopilot-guide -->'

# ---------------------------------------------------------------------------
# The create / update / no-op contract
# ---------------------------------------------------------------------------

test_creates_when_absent() {
    local t v
    t="$(trace_of '[]')"
    v="$(verdict_of '[]')"
    assert_eq "$t" "list-comments:5|create:5" "an absent guide is created, with no update call"
    assert_eq "$v" "created" "and says so"
    log_pass "no guide yet => exactly one createComment"
}

test_ignores_unrelated_comments() {
    local fixture t
    fixture="[{\"id\":1,$BOT,\"body\":\"CI failed on this one\"},{\"id\":2,$HUMAN,\"body\":\"looks good\"}]"
    t="$(trace_of "$fixture")"
    assert_eq "$t" "list-comments:5|create:5" "ordinary chatter is not mistaken for the guide"
    log_pass "unrelated comments are ignored, the guide is still created"
}

test_updates_when_the_body_differs() {
    local fixture t v
    fixture="[{\"id\":77,$BOT,\"body\":\"${MARKER}\nan old, stale guide\"}]"
    t="$(trace_of "$fixture")"
    v="$(verdict_of "$fixture")"
    assert_eq "$t" "list-comments:5|update:77|info:Autopilot gu" "a stale guide is UPDATED in place, never re-created"
    assert_eq "$v" "updated" "and says so"
    log_pass "stale guide => updateComment on the existing id, no duplicate"
}

test_identical_body_performs_no_write_at_all() {
    # THE LOAD-BEARING CASE, and the one PR #555 proved for the label guide: a
    # PR gets a CI run per push, so a poster that wrote unconditionally would
    # bury the conversation. Asserted as an EXACT trace: "no create" alone would
    # be satisfied by a module that called updateComment on every single run.
    local fixture t v
    fixture="[{\"id\":77,$BOT,\"body\":\"@@RENDER@@\"}]"
    t="$(trace_of "$fixture")"
    v="$(verdict_of "$fixture")"
    assert_eq "$t" "list-comments:5" "an unchanged guide performs ZERO writes"
    assert_eq "$v" "unchanged" "and reports itself as unchanged"
    log_pass "identical body => read-only run (no create, no update, idempotent across pushes)"
}

test_a_non_bot_marker_comment_cannot_suppress_the_guide() {
    # Otherwise anyone who can comment could silence the guide forever by
    # posting an empty comment carrying the marker.
    local fixture t
    fixture="[{\"id\":9,$HUMAN,\"body\":\"${MARKER}\"}]"
    t="$(trace_of "$fixture")"
    assert_eq "$t" "list-comments:5|create:5" "a human's marker comment is not THE guide"
    log_pass "only a bot-authored comment counts as the guide"
}

test_newest_bot_guide_wins_and_none_are_deleted() {
    local fixture t
    fixture="[{\"id\":10,$BOT,\"body\":\"${MARKER}\nold one\"},{\"id\":20,$BOT,\"body\":\"${MARKER}\nnewer one\"}]"
    t="$(trace_of "$fixture")"
    assert_eq "$t" "list-comments:5|update:20|info:Autopilot gu" "the newest duplicate is the one kept current"
    assert_not_contains "$t" "delete" "deleting a comment is not reversible; this module never does it"
    log_pass "a duplicate guide is resolved by updating the newest, deleting nothing"
}

# ---------------------------------------------------------------------------
# The content, and its sources. Every fact below is re-derived from the file it
# came from, so a rename turns this red instead of leaving a wrong comment up.
# ---------------------------------------------------------------------------

test_all_three_arming_paths_are_documented() {
    local body
    body="$(rendered_body)"
    assert_contains "$body" "apply \`autopilot\`" "the label path"
    assert_contains "$body" "gh workflow run Autopilot" "the dispatch path, as a runnable command"
    assert_contains "$body" "dispatch IS the arming act" "and what makes the dispatch different"
    assert_contains "$body" "campaign in the state comment" "the campaign path"
    for input in pr_number model max_rounds effort debug-shell; do
        assert_contains "$body" "$input" "the dispatch input '$input' is named"
        grep -q "^      ${input}:" "$AUTOPILOT_WF" ||
            log_fail "the guide names dispatch input '$input', which autopilot.yml does not declare"
    done
    log_pass "all three arming paths documented, and every dispatch input named exists in autopilot.yml"
}

test_every_variable_is_documented_and_real() {
    # The pinning that replaces "rendered from a source of truth". A variable
    # renamed in autopilot.yml and not here would leave the guide instructing
    # people to set something that does nothing.
    local body names name
    body="$(rendered_body)"
    names="$(node -e 'for (const [n] of require(process.argv[1]).VARIABLES) console.log(n)' "$MODULE")"
    [ "$(printf '%s\n' "$names" | grep -c .)" -ge 10 ] ||
        log_fail "the guide documents fewer than 10 variables; the roster in autopilot.yml lists more"
    while IFS= read -r name; do
        [ -n "$name" ] || continue
        assert_contains "$body" "$name" "the rendered table names $name"
        grep -q "$name" "$AUTOPILOT_WF" ||
            log_fail "the guide documents '$name', which appears nowhere in autopilot.yml"
    done <<<"$names"
    # The two whose WRONG value is a known trap, per the roster comment.
    assert_contains "$body" "Empty allows NOBODY" "the author allowlist's fail-closed behaviour is stated"
    assert_contains "$body" "never a model name" "AUTOPILOT_ALLOW_MODEL's documented trap is repeated"
    log_pass "every documented variable exists in autopilot.yml, and both known traps are called out"
}

test_stop_switches_are_documented_with_their_scopes() {
    local body
    body="$(rendered_body)"
    assert_contains "$body" "cancel the run (one round)" "the smallest scope, and that it is only one round"
    assert_contains "$body" "autopilot-blocked" "the loop latch"
    assert_contains "$body" "LATCHES" "and that it needs a human to clear"
    assert_contains "$body" "AUTOPILOT_ENABLED" "the repo-wide switch"
    # THE PRECISE CLAIM. Removing the arming label does NOT stop a campaign: the
    # gate's arming chain accepts an open campaign with no label present. A guide
    # that said otherwise would send someone to remove a label and walk away.
    assert_contains "$body" "only the label path" "removing the label is scoped honestly"
    grep -q 'ARMED_BY="campaign"' "$GATE_SH" ||
        log_fail "the guide claims a campaign survives label removal, but the gate has no campaign arming path"
    for label in autopilot autopilot-blocked; do
        grep -q "^- name: ${label}$" "$LABELS_FILE" ||
            log_fail "the guide names the '$label' label, which .github/labels.yml does not declare"
    done
    log_pass "all three stop scopes documented, label removal scoped honestly, both labels declared"
}

test_the_loop_and_its_bounds_match_the_gate() {
    local body cap turns_fix turns_other
    body="$(rendered_body)"
    # `done` is quoted so it reads as a word rather than as the loop keyword;
    # unquoted, bash parses the list as ending there (SC1010).
    for action in fix ready-flip review-response "done"; do
        assert_contains "$body" "\`$action\`" "the round action '$action' is named"
        grep -q "\"$action\"" "$GATE_SH" ||
            log_fail "the guide names round action '$action', which autopilot-gate.sh never emits"
    done
    assert_contains "$body" "stuck-signature" "the stuck-signature bound"
    grep -q "stuck-signature" "$GATE_SH" || log_fail "autopilot-gate.sh has no stuck-signature bound"

    # The NUMBERS, each read back out of its own source.
    cap="$(sed -n 's/^MAX_ROUNDS="\${AUTOPILOT_MAX_ROUNDS:-\([0-9]*\)}".*/\1/p' "$GATE_SH" | head -1)"
    [ -n "$cap" ] || log_fail "could not read the default round cap out of autopilot-gate.sh"
    assert_contains "$body" "default $cap" "the documented round cap matches the gate ($cap)"

    turns_other="$(sed -n 's/^turns=\([0-9]*\)$/\1/p' "$MODEL_ARGS_SH" | head -1)"
    turns_fix="$(sed -n 's/.*"fix" \]\] && turns=\([0-9]*\).*/\1/p' "$MODEL_ARGS_SH" | head -1)"
    [ -n "$turns_other" ] && [ -n "$turns_fix" ] ||
        log_fail "could not read the --max-turns values out of resolve-model-args.sh"
    assert_contains "$body" "$turns_fix fixing, $turns_other otherwise" \
        "the documented turn caps match resolve-model-args.sh"
    log_pass "round actions, stuck-signature, round cap ($cap) and turn caps ($turns_fix/$turns_other) all match their sources"
}

test_the_guide_is_shorter_than_the_label_guide() {
    # An operator requirement, and a real one: this comment sits on every PR
    # under a guide that is already long. A reference manual nobody reads is
    # worse than the discoverability problem it was meant to fix.
    local mine theirs
    mine="$(rendered_body | wc -c)"
    theirs="$(node -e '
        const m = require(process.argv[1]);
        const fs = require("node:fs");
        process.stdout.write(m.renderBody(m.parseLabels(fs.readFileSync(process.argv[2], "utf8"), "real")));
    ' "$LABEL_MODULE" "$LABELS_FILE" | wc -c)"
    [ "$mine" -lt "$theirs" ] ||
        log_fail "the autopilot guide is $mine bytes, the label guide $theirs; it must be the shorter of the two"
    log_pass "the autopilot guide is $mine bytes against the label guide's $theirs"
}

test_the_trailer_is_present_and_readable() {
    # The footer is LOAD-BEARING: it is the only line telling a reader that
    # hand-edits are overwritten and which file to change instead. Both halves
    # are asserted, because each fails differently -- a missing trailer leaves
    # people editing a comment that reverts every push, and a <sub>-wrapped one
    # is present but rendered as tiny subscript text nobody reads.
    local body
    body="$(rendered_body)"
    assert_contains "$body" "edits here are overwritten" "the trailer says hand-edits do not survive"
    assert_contains "$body" "autopilot-guide-comment.cjs</code>" "and names the file to change instead"
    assert_not_contains "$body" "<sub>" "it must not render as tiny subscript text"
    assert_contains "$body" "> Posted by" "it renders as a normal-size blockquote footer"
    log_pass "the trailer exists, names its source, and renders at readable size"
}

test_marker_is_the_first_bytes_and_unique() {
    local body
    body="$(rendered_body)"
    case "$body" in
        "$MARKER"*) ;;
        *) log_fail "the marker must be the FIRST bytes of the body, or a prefix test cannot find it" ;;
    esac
    [ "$(grep -c -F "$MARKER" <<<"$body")" -eq 1 ] ||
        log_fail "the marker appears more than once; a quoted copy would match the finder"
    # And it must not collide with the label guide's, or the two posters would
    # fight over one comment forever.
    node -e '
        const a = require(process.argv[1]).MARKER;
        const b = require(process.argv[2]).MARKER;
        if (a === b) { console.error("the two guides share a marker"); process.exit(1); }
    ' "$MODULE" "$LABEL_MODULE" || log_fail "the autopilot and label guides must not share a marker"
    log_pass "the marker leads the body, appears once, and differs from the label guide's"
}

test_ci_yml_wires_the_step_in_the_existing_grant() {
    # The module is inert unless ci.yml calls it. It rides the label-guide job
    # deliberately: that job already holds `pull-requests: write` and the
    # `.ci/scripts` sparse checkout, and a second job for one more comment would
    # need its own `needs` entry and its own assert-ci-complete arm.
    local wf job
    wf="$(cat "$CI_WORKFLOW")"
    assert_contains "$wf" "autopilot-guide-comment.cjs" "ci.yml calls this module"
    job="$(awk '/^  label-guide:/{f=1} f&&/^  [a-z][a-z0-9-]*:$/&&!/^  label-guide:/{exit} f' "$CI_WORKFLOW")"
    assert_contains "$job" "autopilot-guide-comment.cjs" "the step is inside the job that has the grant"
    assert_contains "$job" "pull-requests: write" "which is the write it needs"
    assert_contains "$job" "label-guide-comment.cjs" "and the label guide still runs beside it"
    log_pass "ci.yml runs the autopilot guide as a step of the label-guide job, reusing its grant"
}

log_test "test-autopilot-guide-comment"
test_creates_when_absent
test_ignores_unrelated_comments
test_updates_when_the_body_differs
test_identical_body_performs_no_write_at_all
test_a_non_bot_marker_comment_cannot_suppress_the_guide
test_newest_bot_guide_wins_and_none_are_deleted
test_all_three_arming_paths_are_documented
test_every_variable_is_documented_and_real
test_stop_switches_are_documented_with_their_scopes
test_the_loop_and_its_bounds_match_the_gate
test_the_guide_is_shorter_than_the_label_guide
test_the_trailer_is_present_and_readable
test_marker_is_the_first_bytes_and_unique
test_ci_yml_wires_the_step_in_the_existing_grant
echo ""
log_pass "all tests passed"
