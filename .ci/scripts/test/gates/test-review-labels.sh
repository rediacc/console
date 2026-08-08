#!/bin/bash
# Both-ways test for `claude-review-gate.sh --apply-labels` -- the arm that
# labels a PR from the automated review that just ran.
#
# WHY THIS CLASS NEEDS A GATE. This arm writes to the repository on the word of
# a language model, and it is the one piece of the review pipeline that cannot
# be exercised before it reaches main (the workflow runs review scripts from
# console@main by design). So the only pre-merge evidence that exists is this
# file, and it has to cover the two failures that would matter:
#
#   - TOO LOUD: a hallucinated or malformed verdict reaching the labels API.
#     `POST /issues/{n}/labels` is not a safe call for an unvalidated name, and
#     a stray label fails check:ci-label-inventory for the whole repo until
#     someone deletes it by hand. Every write is captured here and asserted on
#     by NAME, and the negative cases assert the write did not happen at all.
#   - TOO QUIET: the mechanical floor must still land when the model produced
#     nothing, because a starved review is the common failure mode of this
#     pipeline, not an exotic one.
#
# Plus the property that makes the whole design safe to run unattended: removal
# is scoped to the arm's OWN ledger comment, so a hand-applied label survives
# any verdict, and a tampered ledger cannot be turned into a delete-anything
# primitive.
#
# GitHub is stubbed with a routing fake `gh` that serves fixture JSON per
# endpoint (applying the caller's own --jq, so the real extraction runs) and
# CAPTURES every non-GET call with its full argv.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
# shellcheck source=../lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test gate
source "$SCRIPT_DIR/../lib/test-helpers.sh"

UNDER_TEST="$REPO_ROOT/.ci/scripts/review/claude-review-gate.sh"
LABELS_FILE="$REPO_ROOT/.github/labels.yml"
INVENTORY_GATE="$REPO_ROOT/.ci/scripts/quality/check-label-inventory.sh"
INITIAL_PROMPT="$REPO_ROOT/.ci/scripts/review/prompts/initial.md"
FOLLOWUP_PROMPT="$REPO_ROOT/.ci/scripts/review/prompts/followup.md"
REUSABLE_WF="$REPO_ROOT/.github/workflows/claude-review-reusable.yml"

# The fence key the prompt emits and this arm parses. Asserted present in BOTH
# producers below, for the reason test-review-status.sh spells out about
# json:review-findings: a rename on one side alone makes the parser silently
# blind while everything still reports OK.
LABELS_FENCE_KEY="json:pr-labels"
LEDGER_PREFIX_EXPECTED='<!-- claude-labels:'

HEAD_SHA="3333333333333333333333333333333333333333"

LAST_OUT=""
LAST_RC=0

# Three literal backticks inside a shell string are a parsing hazard for no
# benefit; same trick test-review-status.sh uses.
TICKS='```'

# ---------------------------------------------------------------------------
# Fixture scaffolding
# ---------------------------------------------------------------------------

write_fake_gh() {
    local dir="$1"
    mkdir -p "$dir/bin"
    cat >"$dir/bin/gh" <<'FAKE'
#!/bin/bash
# Routing fake for `gh api`. GETs are served from fixture JSON with the
# caller's own --jq applied; every write is captured with its FULL argv and
# never served, so an assertion can name the label that was written rather
# than merely counting calls.
set -uo pipefail
printf '%s\n' "$*" >>"$GH_CALLS"
if [ -n "${GH_FAIL_ALL:-}" ]; then
    echo "fake gh: forced API failure" >&2
    exit 1
fi
method="GET"
path=""
jqexpr=""
args=("$@")
n=${#args[@]}
i=0
while [ "$i" -lt "$n" ]; do
    a="${args[$i]}"
    case "$a" in
        api) ;;
        -X | --method)
            i=$((i + 1))
            method="${args[$i]}"
            ;;
        --jq)
            i=$((i + 1))
            jqexpr="${args[$i]}"
            ;;
        -f | -F | --field | --raw-field | --input)
            i=$((i + 1))
            ;;
        --paginate | --silent) ;;
        -*) ;;
        *)
            if [ -z "$path" ]; then path="$a"; fi
            ;;
    esac
    i=$((i + 1))
done

if [ "$method" != "GET" ]; then
    {
        echo "WRITE $method $path"
        for a in "$@"; do
            case "$a" in
                -f | -F | --field | --raw-field | api | --silent) ;;
                *) echo "ARG $a" ;;
            esac
        done
        echo "ENDCALL"
    } >>"$GH_CAPTURE"
    echo '{"id": 4242}'
    exit 0
fi

key=""
case "$path" in
    */pulls/*/files) key="files" ;;
    */issues/*/comments) key="comments" ;;
    */pulls/*/comments) key="inline-comments" ;;
    */labels/*)
        # The single-label existence probe (create-on-demand). Absence is a
        # 404, which is a NON-ZERO exit, exactly as gh reports it.
        name="${path##*/labels/}"
        if [ -f "$GH_FIXTURES/live-labels.txt" ] && grep -qxF "$name" "$GH_FIXTURES/live-labels.txt"; then
            printf '{"name": "%s"}\n' "$name"
            exit 0
        fi
        echo "gh: Not Found (HTTP 404)" >&2
        exit 1
        ;;
    *)
        echo "fake gh: unrouted path: $path" >&2
        exit 3
        ;;
esac

file="$GH_FIXTURES/$key.json"
if [ ! -f "$file" ]; then
    echo "fake gh: missing fixture $file" >&2
    exit 4
fi
if [ -n "$jqexpr" ]; then
    jq -r "$jqexpr" "$file"
else
    cat "$file"
fi
FAKE
    chmod +x "$dir/bin/gh"
}

# files_fixture <TEMP> <path...>
files_fixture() {
    local t="$1"
    shift
    printf '%s\n' "$@" | jq -R '{filename: .}' | jq -s '.' >"$t/fixtures/files.json"
}

# comments_fixture <TEMP> [json-object...]
comments_fixture() {
    local t="$1"
    shift
    if [[ "$#" -eq 0 ]]; then
        echo '[]' >"$t/fixtures/comments.json"
        return
    fi
    printf '%s\n' "$@" | jq -s '.' >"$t/fixtures/comments.json"
}

# ledger_comment <id> <sha> <applied-csv>
ledger_comment() {
    jq -nc --argjson id "$1" --arg sha "$2" --arg applied "$3" \
        '{id: $id, user: {login: "github-actions[bot]"},
          created_at: "2026-08-08T00:00:00Z",
          body: ("<!-- claude-labels: " + $sha + " -->\napplied: " + $applied)}'
}

# report_with_verdict <verdict-json-or-empty> -- the model's final report text,
# in the shape --post-report posts and this arm parses.
report_with_verdict() {
    local verdict="${1:-}"
    {
        printf '%s\n' "## Review verdict: approve"
        printf '%s\n' ""
        printf '%s\n' "<details><summary>machine-readable findings</summary>"
        printf '%s\n' ""
        printf '%s\n' "${TICKS}json:review-findings"
        printf '%s\n' "[]"
        printf '%s\n' "${TICKS}"
        printf '%s\n' ""
        printf '%s\n' "</details>"
        if [[ -n "$verdict" ]]; then
            printf '%s\n' ""
            printf '%s\n' "${TICKS}json:pr-labels"
            printf '%s\n' "$verdict"
            printf '%s\n' "${TICKS}"
        fi
    }
}

# execution_file <TEMP> <report-text>
execution_file() {
    jq -n --arg r "$2" '[{type: "result", subtype: "success", result: $r}]' >"$1/execution.json"
}

setup() {
    local t="$1"
    # ${t:?} so an unset TEMP can never turn this into `rm -rf /bin`.
    rm -rf "${t:?}/fixtures" "${t:?}/bin"
    mkdir -p "$t/fixtures" "$t/bin"
    write_fake_gh "$t"
    : >"$t/calls.txt"
    rm -f "$t/capture.txt"
    # Default world: an ordinary source-code PR, no prior ledger, every managed
    # label except `ci` already live on the repo.
    files_fixture "$t" "packages/cli/src/commands/repo.ts"
    comments_fixture "$t"
    echo '[]' >"$t/fixtures/inline-comments.json"
    printf '%s\n' bug enhancement documentation bump-minor bump-major full-ci rollback \
        >"$t/fixtures/live-labels.txt"
    execution_file "$t" "$(report_with_verdict '{"bump": "patch", "kind": [], "why": "nothing to see"}')"
}

# run_apply <TEMP> [KEY=VALUE ...]
run_apply() {
    local t="$1"
    shift
    local rc=0
    LAST_OUT="$(env \
        PATH="$t/bin:$PATH" \
        GH_FIXTURES="$t/fixtures" \
        GH_CAPTURE="$t/capture.txt" \
        GH_CALLS="$t/calls.txt" \
        GH_TOKEN=fake \
        GITHUB_REPOSITORY=rediacc/console \
        PR_NUMBER=42 \
        HEAD_SHA="$HEAD_SHA" \
        EXECUTION_FILE="$t/execution.json" \
        NO_COLOR=1 \
        "$@" \
        bash "$UNDER_TEST" --apply-labels 2>&1)" || rc=$?
    LAST_RC="$rc"
    return 0
}

# added <TEMP> -- the label names actually sent to the add-labels endpoint,
# sorted and space-joined. Empty string means nothing was applied.
added() {
    [[ -f "$1/capture.txt" ]] || return 0
    sed -n 's/^ARG labels\[\]=//p' "$1/capture.txt" | sort | tr '\n' ' ' | sed 's/ $//'
}

# removed <TEMP> -- the label names sent to the remove-label endpoint.
removed() {
    [[ -f "$1/capture.txt" ]] || return 0
    sed -n 's#^WRITE DELETE .*/issues/42/labels/##p' "$1/capture.txt" | sort | tr '\n' ' ' | sed 's/ $//'
}

# created <TEMP> -- label names sent to the CREATE-a-label endpoint.
created() {
    [[ -f "$1/capture.txt" ]] || return 0
    awk '/^WRITE POST repos\/rediacc\/console\/labels$/ { inblock = 1; next }
         /^ENDCALL$/ { inblock = 0 }
         inblock && /^ARG name=/ { sub(/^ARG name=/, ""); print }' "$1/capture.txt" |
        sort | tr '\n' ' ' | sed 's/ $//'
}

# ledger <TEMP> -- the applied: line of the ledger comment body that was written.
ledger() {
    [[ -f "$1/capture.txt" ]] || return 0
    sed -n 's/^applied: *//p' "$1/capture.txt" | tail -n 1
}

ledger_written() {
    [[ -f "$1/capture.txt" ]] || return 1
    grep -q '^ARG body=<!-- claude-labels:' "$1/capture.txt"
}

# ---------------------------------------------------------------------------
# FIRE: the writes that must happen
# ---------------------------------------------------------------------------
test_valid_verdict_applies_exactly_that_set() {
    local t="$1"
    setup "$t"
    execution_file "$t" "$(report_with_verdict '{"bump": "minor", "kind": ["bug"], "why": "new flag plus a fix"}')"
    run_apply "$t"
    assert_exit_code 0 "$LAST_RC" "the arm is advisory and always exits 0"
    assert_eq "$(added "$t")" "bug bump-minor" "exactly the mapped verdict, nothing else"
    assert_eq "$(removed "$t")" "" "nothing to remove on a first pass"
    assert_eq "$(ledger "$t")" "bump-minor,bug" "the ledger records what was applied, in apply order"
    log_pass "FIRE: a valid verdict applies exactly its mapped set and records it in the ledger"
}

test_kind_vocabulary_maps_to_the_repo_labels() {
    local t="$1"
    setup "$t"
    # `feature` and `docs` are the model's vocabulary; the repo's labels are
    # `enhancement` and `documentation`. A pass-through would create two new
    # labels on the repo and fail the inventory gate.
    execution_file "$t" "$(report_with_verdict '{"bump": "patch", "kind": ["feature", "docs"], "why": "x"}')"
    run_apply "$t"
    assert_eq "$(added "$t")" "documentation enhancement" "feature -> enhancement, docs -> documentation"
    # The needle is BUILT, never spelled out: `labels[]=<word>` written
    # literally in this file is indistinguishable, to check:ci-label-refs, from
    # real code applying a label called `feature`, and that gate would then
    # demand a `feature` label be declared and created. Interpolating dodges its
    # extractor honestly rather than by asking for an exclusion.
    local raw
    for raw in feature docs; do
        assert_not_contains "$(cat "$t/capture.txt")" "labels[]=$raw" \
            "the raw vocabulary word '$raw' is never written to the labels API"
    done
    log_pass "FIRE: the model's kind vocabulary is mapped to this repo's label names"
}

# ---------------------------------------------------------------------------
# The operator ruling: a major verdict is a RECOMMENDATION
# ---------------------------------------------------------------------------
test_major_verdict_is_never_applied() {
    local t="$1"
    setup "$t"
    execution_file "$t" "$(report_with_verdict '{"bump": "major", "kind": [], "why": "config schema break"}')"
    run_apply "$t"
    assert_eq "$(added "$t")" "" "a major verdict applies NOTHING on the model's word"
    assert_not_contains "$(cat "$t/capture.txt")" "bump-major" "bump-major never reaches any write"
    assert_contains "$LAST_OUT" "RECOMMENDS a major bump" "but it is said out loud, with the reason"
    assert_contains "$LAST_OUT" "config schema break" "and the reason is the model's own"

    # CONTROL: the identical path with `minor` DOES write. Without this the
    # assertion above passes just as well on a broken harness that writes
    # nothing ever.
    setup "$t"
    execution_file "$t" "$(report_with_verdict '{"bump": "minor", "kind": [], "why": "new command"}')"
    run_apply "$t"
    assert_eq "$(added "$t")" "bump-minor" "CONTROL: the same code path applies bump-minor autonomously"
    log_pass "major is recommendation-only, minor is autonomous (CONTROL proves writes are reachable)"
}

test_managed_set_excludes_bump_major_by_construction() {
    # Behaviour above proves the `major` BRANCH does not apply it. This proves
    # no OTHER branch could either: the label is absent from the whitelist that
    # every write passes through.
    local managed
    managed="$(sed -n 's/^MANAGED_LABELS=(\(.*\))$/\1/p' "$UNDER_TEST")"
    [[ -n "$managed" ]] ||
        log_fail "MANAGED_LABELS is no longer parseable out of claude-review-gate.sh; this suite cannot prove what the arm may write"
    assert_not_contains " $managed " " bump-major " \
        "bump-major must never enter the managed set: every write path goes through it"
    local l
    for l in $managed; do
        grep -qE "^- name: ${l}$" "$LABELS_FILE" ||
            log_fail "the applier may write '$l' but .github/labels.yml does not declare it; check:ci-label-inventory would fail the repo"
    done
    log_pass "every label the applier may write is declared, and bump-major is not one of them ($managed)"
}

# ---------------------------------------------------------------------------
# TOO LOUD: malformed and hallucinated model output must reach nothing
# ---------------------------------------------------------------------------
test_hallucinated_kind_invalidates_the_whole_verdict() {
    local t="$1"
    setup "$t"
    files_fixture "$t" "docs/agent/notes.md"
    execution_file "$t" "$(report_with_verdict '{"bump": "minor", "kind": ["security"], "why": "made this up"}')"
    run_apply "$t"
    assert_not_contains "$(cat "$t/capture.txt")" "security" "an invented label name never reaches the API"
    assert_eq "$(added "$t")" "documentation" \
        "the verdict is dropped WHOLE (no bump-minor either), and the mechanical floor still lands"
    assert_contains "$LAST_OUT" "did not validate" "and it says the verdict was rejected"
    log_pass "PLANTED hallucinated kind => whole verdict dropped, mechanical floor survives"
}

test_malformed_json_is_treated_as_absent() {
    local t="$1"
    setup "$t"
    files_fixture "$t" "docs/ci-overhaul/06-progress.md"
    execution_file "$t" "$(report_with_verdict '{"bump": "minor", "kind": [, oops')"
    run_apply "$t"
    assert_eq "$(added "$t")" "documentation" "unparseable JSON applies no AI label at all"
    assert_contains "$LAST_OUT" "did not validate" "and says so"
    log_pass "PLANTED unparseable fence => mechanical labels only"
}

test_out_of_range_bump_is_rejected() {
    local t="$1"
    setup "$t"
    execution_file "$t" "$(report_with_verdict '{"bump": "epic", "kind": ["bug"], "why": "x"}')"
    run_apply "$t"
    assert_eq "$(added "$t")" "" "a bump value outside patch|minor|major invalidates the verdict"
    assert_not_contains "$(cat "$t/capture.txt")" "epic" "and the invented value never leaves the script"
    log_pass "PLANTED bump=epic => verdict rejected whole"
}

test_too_many_kinds_is_rejected() {
    local t="$1"
    setup "$t"
    execution_file "$t" "$(report_with_verdict '{"bump": "patch", "kind": ["bug", "feature", "docs"], "why": "everything"}')"
    run_apply "$t"
    assert_eq "$(added "$t")" "" "a kind list longer than the contract is a verdict that stopped following the contract"
    log_pass "PLANTED 3 kinds (contract says at most 2) => verdict rejected"
}

# ---------------------------------------------------------------------------
# TOO QUIET: the mechanical floor, which is the whole point of always()
# ---------------------------------------------------------------------------
test_missing_execution_file_still_applies_mechanical_labels() {
    local t="$1"
    setup "$t"
    files_fixture "$t" ".ci/scripts/review/claude-review-gate.sh" ".github/workflows/ci.yml"
    run_apply "$t" EXECUTION_FILE="$t/does-not-exist.json"
    assert_eq "$(added "$t")" "ci" "a starved review (no execution file at all) still gets the path-derived label"
    assert_contains "$LAST_OUT" "no json:pr-labels block" "and says why there was no verdict"
    log_pass "no execution file => mechanical floor still lands (the starved-review case)"
}

test_docs_only_diff_yields_documentation() {
    local t="$1"
    setup "$t"
    files_fixture "$t" "docs/agent/ci-gates.md" "CLAUDE.md" "packages/cli/src/commands/repo.ts"
    execution_file "$t" "$(report_with_verdict "")"
    assert_eq "$(added "$t")" "" "precondition: nothing captured yet"
    run_apply "$t"
    # The rule is all-files and conservative: one real source file and this is
    # not a docs PR, however many .md files ride along with it.
    assert_eq "$(added "$t")" "" "a single non-matching path disqualifies the all-files rule"

    setup "$t"
    files_fixture "$t" "docs/agent/ci-gates.md" "CLAUDE.md" "LICENSE" "packages/www/src/content/docs/x.mdx"
    execution_file "$t" "$(report_with_verdict "")"
    run_apply "$t"
    assert_eq "$(added "$t")" "documentation" "CONTROL: an all-docs list DOES earn the label"
    log_pass "the documentation rule is all-files (one stray path disqualifies it; the control still fires)"
}

test_mixed_diff_earns_no_mechanical_label() {
    local t="$1"
    setup "$t"
    files_fixture "$t" ".ci/scripts/review/claude-review-gate.sh" "packages/cli/src/commands/repo.ts"
    execution_file "$t" "$(report_with_verdict "")"
    run_apply "$t"
    assert_eq "$(added "$t")" "" "a diff that is only PARTLY CI is not a CI PR"
    if ! ledger_written "$t"; then
        log_fail "the ledger must be written even when nothing is applied, or a later pass cannot reconcile"
    fi
    assert_eq "$(ledger "$t")" "" "an empty ledger line is a real state, not a missing write"
    log_pass "a mixed diff earns nothing, and the empty ledger is still recorded"
}

test_unreadable_file_list_skips_the_mechanical_floor() {
    local t="$1"
    setup "$t"
    rm -f "$t/fixtures/files.json" # the files endpoint fails
    execution_file "$t" "$(report_with_verdict '{"bump": "minor", "kind": [], "why": "x"}')"
    run_apply "$t"
    assert_exit_code 0 "$LAST_RC" "a failed file listing is advisory, like everything else here"
    assert_eq "$(added "$t")" "bump-minor" "the verdict still applies; only the path-derived part is skipped"
    assert_contains "$LAST_OUT" "could not read the changed-file list" "and it says which half was skipped"
    log_pass "an unreadable file list skips the mechanical floor and keeps the verdict"
}

# ---------------------------------------------------------------------------
# Create-on-demand for `ci`
# ---------------------------------------------------------------------------
test_ci_label_is_created_before_first_use() {
    local t="$1"
    setup "$t"
    files_fixture "$t" ".ci/scripts/review/claude-review-gate.sh"
    execution_file "$t" "$(report_with_verdict "")"
    run_apply "$t"
    assert_eq "$(created "$t")" "ci" "the label is created before it is applied"
    assert_eq "$(added "$t")" "ci" "and then applied"

    # CONTROL: once it exists, it must NOT be created again.
    setup "$t"
    files_fixture "$t" ".ci/scripts/review/claude-review-gate.sh"
    execution_file "$t" "$(report_with_verdict "")"
    printf '%s\n' bug enhancement documentation bump-minor ci >"$t/fixtures/live-labels.txt"
    run_apply "$t"
    assert_eq "$(created "$t")" "" "CONTROL: an existing label is not recreated"
    assert_eq "$(added "$t")" "ci" "but it is still applied"
    log_pass "the ci label is created on demand exactly once (probe drives it, not a blind create)"
}

test_create_on_demand_metadata_matches_the_declaration() {
    # The applier cannot read labels.yml (the post-review steps run from a
    # staged copy of .ci alone), so the colour and description are duplicated in
    # the script. A duplicate with no gate drifts, and a drifted colour is a
    # label that looks foreign in the UI forever.
    local script_color script_desc yml_color yml_desc
    script_color="$(sed -n "s/^CREATE_ON_DEMAND_COLOR='\(.*\)'$/\1/p" "$UNDER_TEST")"
    script_desc="$(sed -n "s/^CREATE_ON_DEMAND_DESC='\(.*\)'$/\1/p" "$UNDER_TEST")"
    [[ -n "$script_color" && -n "$script_desc" ]] ||
        log_fail "CREATE_ON_DEMAND_COLOR/DESC are no longer parseable out of claude-review-gate.sh"
    yml_color="$(awk '/^- name: ci$/ { found = 1; next }
                      found && /^- name: / { exit }
                      found && /^  color: / { gsub(/^  color: "|"$/, ""); print; exit }' "$LABELS_FILE")"
    yml_desc="$(awk '/^- name: ci$/ { found = 1; next }
                     found && /^- name: / { exit }
                     found && /^  description: / { sub(/^  description: "/, ""); sub(/"$/, ""); print; exit }' "$LABELS_FILE")"
    assert_eq "$script_color" "$yml_color" "the created colour must match .github/labels.yml"
    assert_eq "$script_desc" "$yml_desc" "the created description must match .github/labels.yml"
    log_pass "create-on-demand metadata matches the declaration (colour $yml_color)"
}

test_ci_is_on_the_inventory_allowlist() {
    # Without this entry, `ci` is declared and absent and check:ci-label-inventory
    # fails the repo until the first review creates it.
    grep -qF '"ci|.ci/scripts/review/claude-review-gate.sh"' "$INVENTORY_GATE" ||
        log_fail "check-label-inventory.sh has no CREATE_ON_DEMAND entry for 'ci'; the label is declared and absent, which that gate treats as a failure"
    grep -qE '^- name: ci$' "$LABELS_FILE" ||
        log_fail ".github/labels.yml does not declare 'ci', so the allowlist entry above would itself fail the gate"
    log_pass "'ci' is declared AND allowlisted as create-on-demand (both halves, as that gate requires)"
}

# ---------------------------------------------------------------------------
# Ledger reconciliation -- the property that makes this safe unattended
# ---------------------------------------------------------------------------
test_stale_ledger_label_is_removed() {
    local t="$1"
    setup "$t"
    comments_fixture "$t" "$(ledger_comment 900 "$HEAD_SHA" "bug,bump-minor")"
    execution_file "$t" "$(report_with_verdict '{"bump": "patch", "kind": ["bug"], "why": "downgraded"}')"
    run_apply "$t"
    assert_eq "$(removed "$t")" "bump-minor" "a label this arm applied and no longer wants is removed"
    assert_eq "$(added "$t")" "bug" "the still-wanted one is re-applied"
    assert_eq "$(ledger "$t")" "bug" "and the ledger is rewritten to the new set"
    assert_contains "$(cat "$t/capture.txt")" "WRITE PATCH repos/rediacc/console/issues/comments/900" \
        "the existing ledger comment is updated, never duplicated"
    log_pass "a superseded verdict removes ONLY the labels the ledger recorded"
}

test_hand_applied_labels_are_never_removed() {
    local t="$1"
    setup "$t"
    # The PR carries full-ci and bump-minor by hand. The ledger only ever
    # recorded `bug`, and the new verdict wants nothing.
    comments_fixture "$t" "$(ledger_comment 900 "$HEAD_SHA" "bug")"
    execution_file "$t" "$(report_with_verdict '{"bump": "patch", "kind": [], "why": "nothing"}')"
    run_apply "$t"
    assert_eq "$(removed "$t")" "bug" "only the ledger's own label is removed"
    assert_not_contains "$(cat "$t/capture.txt")" "labels/full-ci" "a hand-applied kill switch is untouched"
    assert_not_contains "$(cat "$t/capture.txt")" "labels/bump-minor" "and so is a hand-applied bump"
    log_pass "hand-applied labels survive any verdict (removal is ledger-scoped, not a blind sync)"
}

test_tampered_ledger_cannot_delete_arbitrary_labels() {
    local t="$1"
    setup "$t"
    # The ledger is a PR comment, so anyone with write access can edit it. It
    # must not become a delete-anything primitive.
    comments_fixture "$t" "$(ledger_comment 900 "$HEAD_SHA" "rollback,no-cancel-push,bug")"
    execution_file "$t" "$(report_with_verdict '{"bump": "patch", "kind": [], "why": "x"}')"
    run_apply "$t"
    assert_eq "$(removed "$t")" "bug" "only names inside the managed set are ever deleted"
    assert_not_contains "$(cat "$t/capture.txt")" "labels/rollback" \
        "a release-control label named by a tampered ledger is refused"
    assert_contains "$LAST_OUT" "refusing to remove" "and the refusal is logged"
    log_pass "PLANTED tampered ledger => only managed labels are removable"
}

test_ledger_prefix_is_invisible_to_the_other_counters() {
    # Three comment prefixes now live on a PR. If the ledger shared a prefix
    # with the marker it would satisfy last_marker_sha and suppress reviews; if
    # it started with the report header it would consume review budget.
    local ledger marker attempt
    ledger="$(sed -n "s/^LEDGER_PREFIX='\(.*\)'$/\1/p" "$UNDER_TEST")"
    marker="$(sed -n "s/^MARKER_PREFIX='\(.*\)'$/\1/p" "$UNDER_TEST")"
    attempt="$(sed -n "s/^ATTEMPT_PREFIX='\(.*\)'$/\1/p" "$UNDER_TEST")"
    assert_eq "$ledger" "$LEDGER_PREFIX_EXPECTED" "the ledger prefix is the one this suite asserts on"
    [[ "$ledger" != "$marker" && "$ledger" != "$attempt" ]] ||
        log_fail "the ledger prefix collides with the reviewed-SHA marker or the spent-attempt marker"
    case "$ledger" in
        "**Claude finished"*) log_fail "the ledger body would be counted as a posted review report" ;;
    esac
    log_pass "the ledger prefix is distinct from the marker, the attempt marker and the report header"
}

# THE HONESTY GUARD, driven for real. --mark refuses to stamp a SHA as reviewed
# unless the pass actually POSTED something. The ledger comment is written by
# this pipeline about itself seconds earlier, so counting it would let the
# pipeline vouch for itself: a review that "succeeded" and posted nothing (the
# 36-permission-denials shape that motivated the guard) would be marked as
# reviewed on the strength of its own bookkeeping.
test_mark_does_not_count_the_ledger_comment_as_output() {
    local t="$1" now
    setup "$t"
    now="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    comments_fixture "$t" "$(jq -nc --arg now "$now" --arg sha "$HEAD_SHA" \
        '{id: 901, user: {login: "github-actions[bot]"}, created_at: $now,
          body: ("<!-- claude-labels: " + $sha + " -->\napplied: ci")}')"
    local rc=0
    LAST_OUT="$(env PATH="$t/bin:$PATH" GH_FIXTURES="$t/fixtures" GH_CAPTURE="$t/capture.txt" \
        GH_CALLS="$t/calls.txt" GH_TOKEN=fake GITHUB_REPOSITORY=rediacc/console \
        PR_NUMBER=42 HEAD_SHA="$HEAD_SHA" REVIEW_OUTCOME=success NO_COLOR=1 \
        bash "$UNDER_TEST" --mark 2>&1)" || rc=$?
    assert_exit_code 1 "$rc" "a ledger comment alone must NOT satisfy the posted-something guard"
    assert_contains "$LAST_OUT" "posted NOTHING" "and the refusal says why"

    # CONTROL: a real report comment in the same slot DOES satisfy it, so the
    # assertion above is about the prefix and not about a broken fixture.
    comments_fixture "$t" "$(jq -nc --arg now "$now" \
        '{id: 902, user: {login: "github-actions[bot]"}, created_at: $now,
          body: "**Claude finished** the automated review.\nverdict: approve"}')"
    rm -f "$t/capture.txt"
    rc=0
    LAST_OUT="$(env PATH="$t/bin:$PATH" GH_FIXTURES="$t/fixtures" GH_CAPTURE="$t/capture.txt" \
        GH_CALLS="$t/calls.txt" GH_TOKEN=fake GITHUB_REPOSITORY=rediacc/console \
        PR_NUMBER=42 HEAD_SHA="$HEAD_SHA" REVIEW_OUTCOME=success NO_COLOR=1 \
        bash "$UNDER_TEST" --mark 2>&1)" || rc=$?
    assert_exit_code 0 "$rc" "CONTROL: a genuine posted report DOES let the SHA be marked"
    assert_contains "$(cat "$t/capture.txt")" "claude-reviewed:" "and the marker is written"
    log_pass "--mark ignores the label ledger as evidence of output (CONTROL: a real report still counts)"
}

# ---------------------------------------------------------------------------
# Advisory end to end
# ---------------------------------------------------------------------------
test_fence_only_in_posted_comment_is_found() {
    local t="$1"
    setup "$t"
    # The feature's FIRST LIVE RUN (#559, run 31267699743): the model posted its
    # summary itself and put the fence in the COMMENT; its result text back to
    # the harness did not repeat it. The old extraction read only the result
    # text, logged "no json:pr-labels block", and applied nothing beside a PR
    # whose verdict comment plainly carried a verdict.
    execution_file "$t" "$(report_with_verdict '')"
    comments_fixture "$t" "$(jq -n --arg body "## Verdict: request changes

${TICKS}json:pr-labels
{\"bump\": \"patch\", \"kind\": [\"bug\", \"ci\"], \"why\": \"live shape\"}
${TICKS}" '{"id": 900001, "body": $body}')"
    run_apply "$t"
    assert_exit_code 0 "$LAST_RC" "advisory always"
    assert_eq "$(added "$t")" "bug ci" "the comment-borne verdict is found and applied"
    log_pass "FIRE: a fence living only in the posted comment is found by the fallback"
}

test_result_fence_wins_over_comment_fence() {
    local t="$1"
    setup "$t"
    # Priority pin: when BOTH carry a fence, the result text stays the primary
    # source -- the comment path is a fallback, not a second voter.
    execution_file "$t" "$(report_with_verdict '{"bump": "patch", "kind": ["ci"], "why": "from the result"}')"
    comments_fixture "$t" "$(jq -n --arg body "${TICKS}json:pr-labels
{\"bump\": \"minor\", \"kind\": [\"bug\"], \"why\": \"from a comment\"}
${TICKS}" '{"id": 900002, "body": $body}')"
    run_apply "$t"
    assert_eq "$(added "$t")" "ci" "the result-text verdict wins; the comment fence is not consulted"
    log_pass "FIRE: the result-text fence outranks a comment fence"
}

test_total_api_failure_is_advisory() {
    local t="$1"
    setup "$t"
    execution_file "$t" "$(report_with_verdict '{"bump": "minor", "kind": ["bug"], "why": "x"}')"
    run_apply "$t" GH_FAIL_ALL=1
    assert_exit_code 0 "$LAST_RC" "no label failure may fail the review job or block a merge"
    assert_contains "$LAST_OUT" "could not" "and every failure is logged rather than swallowed"
    log_pass "every gh call failing => exit 0 with warnings (labels never block a merge)"
}

# ---------------------------------------------------------------------------
# Contracts with the files this arm cannot reach at runtime
# ---------------------------------------------------------------------------
test_fence_key_is_shared_by_prompt_and_parser() {
    grep -qF -- "$LABELS_FENCE_KEY" "$INITIAL_PROMPT" ||
        log_fail "prompts/initial.md no longer asks for the '$LABELS_FENCE_KEY' block; --apply-labels would find nothing to parse forever"
    grep -qF -- "$LABELS_FENCE_KEY" "$FOLLOWUP_PROMPT" ||
        log_fail "prompts/followup.md no longer asks for the '$LABELS_FENCE_KEY' block; every re-review would silently drop the verdict"
    grep -qF -- "$LABELS_FENCE_KEY" "$UNDER_TEST" ||
        log_fail "claude-review-gate.sh no longer parses '$LABELS_FENCE_KEY'"
    # The closed vocabulary has to be stated to the model, or it will invent
    # words the validator then rejects on every single run.
    local w
    for w in "bug" "feature" "docs" "ci"; do
        grep -qF -- "$w" "$INITIAL_PROMPT" ||
            log_fail "prompts/initial.md no longer names the kind '$w' the parser accepts"
    done
    grep -qF -- "RECOMMENDATION" "$INITIAL_PROMPT" ||
        log_fail "the prompt no longer tells the model that a major verdict is advisory; it will report one as though it lands"
    log_pass "the json:pr-labels fence and its vocabulary are stated by both prompts and parsed by the gate"
}

test_workflow_step_is_guarded_against_the_arm_not_being_on_main() {
    # Review scripts execute from console@main, the workflow comes from the PR.
    # An unguarded call to a brand-new arm takes the job red for the whole life
    # of the introducing PR; that exact mistake is documented at the
    # "Record the review invocation" step (run 30552035566).
    grep -qF -- "--apply-labels" "$REUSABLE_WF" ||
        log_fail "claude-review-reusable.yml never calls --apply-labels, so nothing applies labels at all"
    grep -qF -- "grep -q -- '--apply-labels'" "$REUSABLE_WF" ||
        log_fail "the Apply PR labels step lost its grep guard; until the arm is on main it will fail the review job"
    grep -qF "github.repository == 'rediacc/console'" "$REUSABLE_WF" ||
        log_fail "the Apply PR labels step is not scoped to console; the submodule repos consume no bump labels and have no inventory gate"
    awk '/name: Apply PR labels/ { found = 1 }
         found && /if: / { print; exit }' "$REUSABLE_WF" | grep -q 'always()' ||
        log_fail "the Apply PR labels step does not run under always(); a starved review would lose its mechanical labels"
    log_pass "the workflow step is guarded, console-scoped, and runs under always()"
}

# ---------------------------------------------------------------------------

test_managed_set_excludes_bump_major_by_construction
test_create_on_demand_metadata_matches_the_declaration
test_ci_is_on_the_inventory_allowlist
test_ledger_prefix_is_invisible_to_the_other_counters
test_fence_key_is_shared_by_prompt_and_parser
test_workflow_step_is_guarded_against_the_arm_not_being_on_main

with_temp_dir test_valid_verdict_applies_exactly_that_set
with_temp_dir test_kind_vocabulary_maps_to_the_repo_labels
with_temp_dir test_major_verdict_is_never_applied

with_temp_dir test_hallucinated_kind_invalidates_the_whole_verdict
with_temp_dir test_malformed_json_is_treated_as_absent
with_temp_dir test_out_of_range_bump_is_rejected
with_temp_dir test_too_many_kinds_is_rejected

with_temp_dir test_missing_execution_file_still_applies_mechanical_labels
with_temp_dir test_docs_only_diff_yields_documentation
with_temp_dir test_mixed_diff_earns_no_mechanical_label
with_temp_dir test_unreadable_file_list_skips_the_mechanical_floor

with_temp_dir test_ci_label_is_created_before_first_use

with_temp_dir test_stale_ledger_label_is_removed
with_temp_dir test_hand_applied_labels_are_never_removed
with_temp_dir test_tampered_ledger_cannot_delete_arbitrary_labels
with_temp_dir test_mark_does_not_count_the_ledger_comment_as_output

with_temp_dir test_fence_only_in_posted_comment_is_found
with_temp_dir test_result_fence_wins_over_comment_fence

with_temp_dir test_total_api_failure_is_advisory
