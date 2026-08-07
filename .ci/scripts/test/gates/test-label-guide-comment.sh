#!/bin/bash
# Behavioural test for .ci/scripts/ci/label-guide-comment.cjs.
#
# WHAT IT GUARDS. The repo carries twelve labels, several of them kill switches
# whose effect is invisible unless you already know they exist. The module posts
# one comment per PR explaining them, rendered from .github/labels.yml.
#
# WHY BEHAVIOURAL. Every claim worth testing is about API CALLS -- "creates when
# absent", "updates when stale", and above all "performs ZERO writes when the
# rendered body is unchanged". A PR gets a CI run per push, so a module that
# posts unconditionally would bury the conversation, and you cannot see that
# from the return value: you have to look at the call trace. So this drives the
# real module against a fake GitHub client and asserts on that trace.
#
# The no-op case is the load-bearing one, and it is asserted as an EXACTLY-EQUAL
# trace, not as "no create". A version that skipped createComment but still
# called updateComment every run would pass a weaker assertion while producing
# the same edit-spam.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
# shellcheck source=../lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test/gates/test-*.sh
source "$SCRIPT_DIR/../lib/test-helpers.sh"

MODULE="$REPO_ROOT/.ci/scripts/ci/label-guide-comment.cjs"
REAL_LABELS="$REPO_ROOT/.github/labels.yml"
CI_WORKFLOW="$REPO_ROOT/.github/workflows/ci.yml"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# ---------------------------------------------------------------------------
# Fixture labels file with a KNOWN set. Every name here must appear in the
# rendered table, and the row count is asserted, so a renderer that quietly
# drops entries cannot pass by rendering "enough" of them.
# ---------------------------------------------------------------------------
cat >"$WORK/labels.yml" <<'FIXTURE'
# A comment line, which the reader must skip rather than choke on.
- name: fixture-alpha
  color: "FEF2C0"
  description: "First fixture label"

# Another comment, mid-file.
- name: fixture-beta
  color: "1D76DB"
  description: "Second fixture label"

- name: fixture-gamma
  color: "B60205"
  description: "Third fixture label, with a | pipe in it"

# guide: false -- declared, reconciled by the inventory gate, NOT listed.
- name: fixture-hidden
  color: "cfd3d7"
  description: "Fourth fixture label, deliberately kept out of the guide"
  guide: false

# The explicit-true control: the field is readable in both directions, so a
# parser that treated ANY `guide:` line as "hide" would fail here.
- name: fixture-shown
  color: "0E8A16"
  description: "Fifth fixture label, explicitly opted in"
  guide: true
FIXTURE
# Guide-visible rows expected from the fixture: alpha, beta, gamma (field
# absent) plus fixture-shown (explicitly true). fixture-hidden is excluded.
FIXTURE_COUNT=4
FIXTURE_DECLARED=5

cat >"$WORK/harness.cjs" <<'HARNESS'
const mod = require(process.argv[2]);
const comments = JSON.parse(process.argv[3]);

// A fixture body of "@@RENDER@@" means "byte-identical to what the module would
// render right now". Hand-copying the expected body into the fixture would make
// the no-op case pass for the wrong reason the moment the renderer changed.
// Resolved LAZILY: the malformed-file cases expect the MODULE to throw, and
// pre-rendering here would throw first, outside the catch, printing nothing.
const fs = require('node:fs');
if (comments.some((c) => c.body === '@@RENDER@@')) {
  const rendered = mod.renderBody(mod.parseLabels(fs.readFileSync(process.env.LABEL_GUIDE_LABELS_FILE, 'utf8'), 'fixture'));
  for (const c of comments) if (c.body === '@@RENDER@@') c.body = rendered;
}

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

# run_guide <labels-file> <comments-json>
run_guide() {
    LABEL_GUIDE_LABELS_FILE="$1" node "$WORK/harness.cjs" "$MODULE" "$2" 2>/dev/null || true
}
trace_of() { run_guide "$@" | sed -n 's/^TRACE=//p'; }
verdict_of() { run_guide "$@" | sed -n 's/^VERDICT=//p'; }
body_of() { run_guide "$@" | sed -n 's/^BODY=//p'; }

BOT='"user":{"type":"Bot","login":"github-actions[bot]"}'
HUMAN='"user":{"type":"User","login":"an-outsider"}'
MARKER='<!-- rediacc:label-guide -->'

# ---------------------------------------------------------------------------

test_creates_when_absent() {
    local t v
    t="$(trace_of "$WORK/labels.yml" '[]')"
    v="$(verdict_of "$WORK/labels.yml" '[]')"
    assert_eq "$t" "list-comments:5|create:5" "an absent guide is posted, after exactly one read"
    assert_eq "$v" "created" "and the module says so"
    log_pass "the guide is created when the PR has none ($t)"
}

test_ignores_unrelated_comments() {
    # The control for the finder: ordinary PR chatter must not be mistaken for
    # the guide, or the guide would never be posted on a busy PR.
    local t
    t="$(trace_of "$WORK/labels.yml" "[{\"id\":1,\"body\":\"looks good to me\",$HUMAN},{\"id\":2,\"body\":\"rerunning CI\",$BOT}]")"
    assert_contains "$t" "create:5" "unrelated comments do not count as the guide"
    log_pass "unrelated comments are ignored ($t)"
}

test_updates_when_the_body_differs() {
    local t v
    t="$(trace_of "$WORK/labels.yml" "[{\"id\":77,\"body\":\"${MARKER}\\n### Label guide\\n\\nstale contents\",$BOT}]")"
    v="$(verdict_of "$WORK/labels.yml" "[{\"id\":77,\"body\":\"${MARKER}\\n### Label guide\\n\\nstale contents\",$BOT}]")"
    assert_contains "$t" "update:77" "a stale guide is rewritten in place"
    assert_not_contains "$t" "create:" "and NOT duplicated as a second comment"
    assert_eq "$v" "updated" "and the module says so"
    log_pass "a stale guide is updated in place ($t)"
}

test_identical_body_performs_no_write_at_all() {
    # THE LOAD-BEARING CASE. Asserted as trace EQUALITY: "no create" alone would
    # be satisfied by a module that calls updateComment on every run, which is
    # the same spam wearing a different verb.
    local t v
    t="$(trace_of "$WORK/labels.yml" "[{\"id\":77,\"body\":\"@@RENDER@@\",$BOT}]")"
    v="$(verdict_of "$WORK/labels.yml" "[{\"id\":77,\"body\":\"@@RENDER@@\",$BOT}]")"
    assert_eq "$t" "list-comments:5" "a current guide must produce ZERO API writes, only the read"
    assert_eq "$v" "unchanged" "and the module reports the no-op"
    log_pass "an up-to-date guide is left completely alone ($t)"
}

test_a_non_bot_marker_comment_cannot_suppress_the_guide() {
    # Anyone who can comment on a PR could otherwise post an empty comment
    # carrying the marker and silence the guide forever.
    local t
    t="$(trace_of "$WORK/labels.yml" "[{\"id\":9,\"body\":\"${MARKER}\\nnothing to see here\",$HUMAN}]")"
    assert_contains "$t" "create:5" "a human-authored marker comment is not the guide"
    assert_not_contains "$t" "update:9" "and is never rewritten"
    log_pass "an outsider's fake guide cannot suppress the real one ($t)"
}

test_body_renders_every_declared_label() {
    # Driven from the fixture so the COUNT can be asserted. A renderer that
    # silently drops entries would otherwise stay green forever: a table with
    # most of the labels looks exactly like a table with all of them.
    local body rows
    body="$(body_of "$WORK/labels.yml" '[]')"
    assert_contains "$body" "fixture-alpha" "the first label is rendered"
    assert_contains "$body" "fixture-beta" "the second label is rendered"
    assert_contains "$body" "fixture-gamma" "the third label is rendered"
    assert_contains "$body" "First fixture label" "descriptions are rendered, not just names"
    # `|| true` because this runs under `set -o pipefail` and grep exits 1 on
    # no-match: without it, a renderer regression that produced ZERO rows would
    # KILL this test mid-run instead of failing the assertion below, which is
    # the exact assertion written to catch it. Zero is a legitimate value here;
    # judging it is the next line's job, not the pipeline's.
    rows="$( (printf '%s' "$body" | grep -o '| `fixture-' || true) | wc -l)"
    assert_eq "$rows" "$FIXTURE_COUNT" "exactly one table row per guide-visible label"
    log_pass "every guide-visible label reaches the table ($rows rows)"
}

test_guide_false_is_omitted_and_its_control_is_present() {
    # `guide: false` means "declared so the inventory gate is satisfied, but do
    # NOT list it": the guide exists because the roster got too long to
    # remember, and padding it with stock GitHub labels recreates that problem.
    #
    # THE CONTROL IS THE POINT. An assertion that fixture-hidden is absent is
    # satisfied just as well by a renderer that dropped everything, so the two
    # opt-IN shapes are asserted in the same breath: field absent (alpha) and
    # field explicitly true (fixture-shown).
    local body
    body="$(body_of "$WORK/labels.yml" '[]')"
    assert_not_contains "$body" "fixture-hidden" "a guide:false label is not listed"
    assert_not_contains "$body" "deliberately kept out" "nor is its description"
    assert_contains "$body" "fixture-shown" "an explicitly guide:true label IS listed"
    assert_contains "$body" "fixture-alpha" "and so is one with no guide field at all"
    log_pass "guide:false hides a label; both opt-in shapes still render"
}

test_the_omitted_count_is_stated() {
    # A reader who applies `duplicate` and cannot find it in the table needs to
    # know the omission was deliberate rather than a bug in this comment.
    local body
    body="$(body_of "$WORK/labels.yml" '[]')"
    assert_contains "$body" "$((FIXTURE_DECLARED - FIXTURE_COUNT)) further label(s) exist and are deliberately left off" \
        "the body accounts for the labels it does not list"
    log_pass "the rendered body states how many labels it deliberately omits"
}

test_a_malformed_guide_value_fails_loudly() {
    # Coercion here is the dangerous shape: `guide: no` read as a truthy string
    # would SHOW a label meant to be hidden, and `guide: yes` under a
    # falsy-string reading would hide one meant to be shown. Neither is
    # detectable by looking at the comment.
    local out
    printf -- '- name: ok-one\n  description: "fine"\n- name: ok-two\n  description: "fine"\n  guide: no\n' >"$WORK/badguide.yml"
    out="$(run_guide "$WORK/badguide.yml" '[]')"
    assert_contains "$out" "THREW=" "a non-boolean guide value must throw"
    assert_contains "$out" "exactly 'true' or 'false'" "and say what was expected"
    log_pass "a malformed guide value is a loud parse failure, never a coercion"
}

test_hiding_everything_trips_the_guide_floor() {
    # The second vacuity route, and the one `guide: false` introduced: a parser
    # change that mis-read the field would mark every entry hidden while the
    # declaration count still cleared MIN_LABELS, and the table would come out
    # empty with nothing complaining.
    local out
    printf -- '- name: ok-one\n  description: "fine"\n  guide: false\n- name: ok-two\n  description: "fine"\n  guide: false\n- name: ok-three\n  description: "fine"\n  guide: false\n' >"$WORK/allhidden.yml"
    out="$(run_guide "$WORK/allhidden.yml" '[]')"
    assert_contains "$out" "THREW=" "an all-hidden file must throw"
    assert_contains "$out" "floor" "and name the guide floor"
    assert_not_contains "$out" "create:5" "and must NOT post an empty table"
    log_pass "an empty guide set trips its own floor rather than posting a blank table"
}

test_body_says_it_is_generated() {
    local body
    body="$(body_of "$WORK/labels.yml" '[]')"
    assert_contains "$body" ".github/labels.yml" "the body names its source of truth"
    assert_contains "$body" "next CI run overwrites it" "and warns against hand-editing"
    log_pass "the rendered body tells a human not to hand-edit it"
}

test_a_pipe_in_a_description_does_not_break_the_table() {
    local body
    body="$(body_of "$WORK/labels.yml" '[]')"
    # BODY= is JSON-escaped for the shell, so the rendered `\|` reads as `\\|`.
    assert_contains "$body" '\\| pipe in it' "a pipe inside a description is escaped"
    log_pass "a pipe in a description is escaped rather than splitting the row"
}

test_malformed_labels_file_fails_loudly() {
    # The failure mode this replaces: a grep-shaped reader that picks out the
    # lines it recognises and silently yields a SHORT table. A short table looks
    # like a good table, so the reader must throw instead.
    local out
    printf -- '- name: ok-one\n  description: "fine"\n- name: ok-two\n  description: "fine"\nthis line is not yaml we understand\n' >"$WORK/bad.yml"
    out="$(run_guide "$WORK/bad.yml" '[]')"
    assert_contains "$out" "THREW=" "a malformed labels file must throw"
    assert_not_contains "$out" "create:5" "and must NOT post a partial guide"
    log_pass "a malformed labels file fails loudly instead of rendering a short table"
}

test_a_label_without_a_description_fails_loudly() {
    local out
    printf -- '- name: ok-one\n  description: "fine"\n- name: no-desc\n  color: "FFFFFF"\n' >"$WORK/nodesc.yml"
    out="$(run_guide "$WORK/nodesc.yml" '[]')"
    assert_contains "$out" "THREW=" "a description-less label must throw"
    assert_contains "$out" "no-desc" "and must name the offender"
    log_pass "a label with no description is refused (the guide exists to explain labels)"
}

test_a_truncated_labels_file_trips_the_floor() {
    # Strict parsing rejects malformed lines but cannot notice a file truncated
    # to something still well-formed. The floor covers that.
    local out
    printf -- '- name: only-one\n  description: "lonely"\n' >"$WORK/short.yml"
    out="$(run_guide "$WORK/short.yml" '[]')"
    assert_contains "$out" "THREW=" "a one-label file must throw"
    assert_contains "$out" "floor" "and must say the read is broken, not that the file is short"
    log_pass "a truncated labels file trips the anti-vacuity floor"
}

test_the_real_labels_file_renders_every_label() {
    # ANTI-VACUITY against the real tree: the fixture cases prove the renderer
    # works on a file this test wrote, which says nothing about the real one.
    # This drives the real .github/labels.yml and asserts the row count equals
    # the declaration count, so adding a label there without it reaching the
    # guide is impossible.
    # The expected count is DERIVED from the real file (declared minus
    # guide:false), never hardcoded: a hardcoded number here would be a second
    # source of truth that rots the next time a label is added or opted out.
    local declared hidden expected body rows
    declared="$(grep -cE '^- name:' "$REAL_LABELS")"
    hidden="$(grep -cE '^[[:space:]]+guide:[[:space:]]*false[[:space:]]*$' "$REAL_LABELS" || true)"
    expected=$((declared - hidden))
    body="$(body_of "$REAL_LABELS" '[]')"
    # Guarded for the same reason as the fixture case above: under pipefail a
    # zero-row render would abort this test rather than fail its assertion.
    rows="$( (printf '%s' "$body" | grep -o '| `' || true) | wc -l)"
    assert_eq "$rows" "$expected" "the real guide lists exactly the guide-visible labels"

    # Anti-vacuity on the filter itself: if the real file ever stopped carrying
    # any guide:false entry, the equality above would hold trivially and this
    # case would stop testing the filter at all.
    [ "$hidden" -gt 0 ] || log_fail "the real labels file carries no guide:false entry, so this case no longer exercises the filter"

    assert_contains "$body" "rollback" "the rollback kill switch is explained"
    assert_contains "$body" "full-ci" "the scope-engine kill switch is explained"
    assert_not_contains "$body" "good first issue" "a stock GitHub default is kept out of the guide"
    log_pass "the real labels file renders $rows of $declared labels ($hidden opted out)"
}

test_ci_yml_wires_the_job_with_the_narrowest_grant() {
    # The module is inert unless ci.yml actually calls it, and the whole reason
    # it is its OWN job is the permission: pull-requests:write must not be added
    # to `initialize`, which carries a 20-step surface.
    local wf job
    wf="$(cat "$CI_WORKFLOW")"
    assert_contains "$wf" "label-guide-comment.cjs" "ci.yml calls this module"
    assert_contains "$wf" "  label-guide:" "the dedicated job exists"
    assert_contains "$wf" "RESULT_LABEL_GUIDE" "its result reaches ci-complete"

    # The job's own block, from its key to the next top-level job key.
    job="$(awk '/^  label-guide:/{f=1} f&&/^  [a-z][a-z0-9-]*:$/&&!/^  label-guide:/{exit} f' "$CI_WORKFLOW")"
    assert_contains "$job" "pull-requests: write" "the job grants itself the write it needs"
    assert_contains "$job" "contents: read" "and nothing wider than read on contents"
    assert_not_contains "$job" "packages:" "no unrelated grant leaks in"
    assert_not_contains "$job" "issues:" "and no issues grant (PR comments do not need one)"
    assert_contains "$job" "needs: [initialize]" "it runs after initialize"
    assert_contains "$job" "runs-on: ubuntu-slim" "on the cheap runner"

    # ubuntu-slim has a HARD 15-minute platform cap; check-workflow-gates CHECK 3
    # requires <= 14, and a job over it is CANCELLED with no failing step.
    local timeout
    timeout="$(printf '%s\n' "$job" | sed -n 's/^ *timeout-minutes: *\([0-9]*\).*/\1/p' | head -1)"
    [ -n "$timeout" ] || log_fail "the label-guide job declares no timeout-minutes"
    [ "$timeout" -le 14 ] || log_fail "label-guide timeout-minutes is $timeout; ubuntu-slim caps at 15 and the gate requires <= 14"
    log_pass "ci.yml wires label-guide as its own job with pull-requests:write and a ${timeout}m timeout"
}

test_assert_ci_complete_judges_the_job() {
    # A job absent from the aggregator can go red while `CI Complete` stays
    # green. SOFT, not HARD: the job legitimately skips on push-to-main.
    local out rc=0
    out="$(bash "$REPO_ROOT/.ci/scripts/ci/assert-ci-complete.sh" 2>&1)" || rc=$?
    assert_exit_code 1 "$rc" "the assertion script must fail when nothing is passed"
    assert_contains "$out" "LABEL_GUIDE" "LABEL_GUIDE is one of the judged jobs"
    log_pass "assert-ci-complete.sh judges LABEL_GUIDE"
}

log_test "test-label-guide-comment"
test_creates_when_absent
test_ignores_unrelated_comments
test_updates_when_the_body_differs
test_identical_body_performs_no_write_at_all
test_a_non_bot_marker_comment_cannot_suppress_the_guide
test_body_renders_every_declared_label
test_guide_false_is_omitted_and_its_control_is_present
test_the_omitted_count_is_stated
test_a_malformed_guide_value_fails_loudly
test_hiding_everything_trips_the_guide_floor
test_body_says_it_is_generated
test_a_pipe_in_a_description_does_not_break_the_table
test_malformed_labels_file_fails_loudly
test_a_label_without_a_description_fails_loudly
test_a_truncated_labels_file_trips_the_floor
test_the_real_labels_file_renders_every_label
test_ci_yml_wires_the_job_with_the_narrowest_grant
test_assert_ci_complete_judges_the_job
echo ""
log_pass "all tests passed"
