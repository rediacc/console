#!/bin/bash
# Make the "self-contained, copyable folder" claim ENFORCEABLE rather than
# aspirational.
#
# .ci/breakpoint/ exists to be copied wholesale into renet / account / elite,
# repos that have no .ci/scripts/, no package.json, no app-token plumbing and
# no rediacc-specific anything. Nothing about a copy FAILS loudly when that
# stops being true: the folder keeps working here, in console, where all of
# those things happen to exist, and only breaks in the downstream repo months
# later, in somebody else's CI, with an error that points nowhere useful.
#
# So the fixture is the point: every assertion below runs against a COPY of
# .ci/breakpoint/ made into an empty temp dir with no .ci/scripts, no
# package.json and no .git alongside it. What passes there is what a downstream
# repo actually gets.
#
# NOTE ON TWO ASSERTIONS THAT ARE NARROWER THAN THEY LOOK -- both were written
# strict first, and both found something real (see the FINDING notes inline):
#   - console's script tree IS referenced, in two scripts, as an OPTIONAL hook
#     guarded by [[ -x ]]. That is portable (absent => skipped), so the test
#     pins the exact file set plus the guard, not a blanket zero.
#   - `rediacc/` IS present in two scripts, as a ${BREAKPOINT_UPSTREAM_REPO:-}
#     fallback default and one usage example. Those are conf-overridable /
#     diagnostic, so the test pins that shape, not a blanket zero.
# Both keep the property that a NEW hardcoded reference is red.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
# shellcheck source=../lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test gate
source "$SCRIPT_DIR/../lib/test-helpers.sh"

BP_SRC="$REPO_ROOT/.ci/breakpoint"
CANONICAL_VALIDATOR="$REPO_ROOT/.ci/scripts/lib/blocker-validator.sh"

# The two scripts allowed to reach for console's tree, and the reason. Both
# call a console-only service helper behind an [[ -x ]] existence test, so a
# repo without it takes the skip branch instead of dying.
ALLOWED_CONSOLE_HOOKS="scripts/start-origin.sh
scripts/stop-breakpoint.sh"

# -----------------------------------------------------------------------------
# fixture: an isolated copy with NOTHING around it
# -----------------------------------------------------------------------------
make_isolated() {
    local tmp="$1"
    mkdir -p "$tmp/.ci"
    cp -r "$BP_SRC" "$tmp/.ci/"
    echo "$tmp/.ci/breakpoint"
}

# bp_files <root> -- every shell/workflow file in the copy, relative, sorted.
bp_files() {
    local root="$1"
    find "$root" -type f \( -name '*.sh' -o -name '*.yml' -o -name '*.yaml' \) |
        sed "s|^${root}/||" | LC_ALL=C sort
}

# bp_code_hits <root> <ere> -- "<relpath>:<lineno>" for every matching line that
# is NOT a whole-line comment. Comments matter here: most of breakpoint's
# references to console are prose explaining what was deleted and why, and a
# grep that cannot tell prose from code would force the docs to be stripped.
bp_code_hits() {
    local root="$1" ere="$2" f rel hit
    while IFS= read -r f; do
        rel="${f#"$root"/}"
        while IFS= read -r hit; do
            [[ -z "$hit" ]] && continue
            printf '%s:%s\n' "$rel" "${hit%%:*}"
        done < <(grep -nE "$ere" "$f" 2>/dev/null | grep -Ev '^[0-9]+:[[:space:]]*#' || true)
    done < <(bp_files "$root" | sed "s|^|${root}/|")
}

# bp_hit_files <root> <ere> -- just the distinct files, sorted.
bp_hit_files() {
    bp_code_hits "$1" "$2" | sed 's/:[0-9]*$//' | LC_ALL=C sort -u
}

# extract_array <file> <name> -- the quoted string elements of a bash array
# literal, one per line. Comment lines inside the array carry no quotes and are
# therefore skipped for free.
extract_array() {
    awk -v start="readonly $2=(" '
        index($0, start) == 1 { inside = 1; next }
        inside && index($0, ")") == 1 { inside = 0 }
        inside { print }
    ' "$1" | grep -oE '"[^"]*"' | tr -d '"'
}

# =============================================================================
# a) no HARD dependency on console's script tree
# =============================================================================
test_console_script_tree_is_optional() {
    local bp files line
    bp="$(make_isolated "$1")"

    files="$(bp_hit_files "$bp" '\.ci/scripts/')"
    assert_eq "$files" "$ALLOWED_CONSOLE_HOOKS" \
        "only the two optional-hook scripts may name console's .ci/scripts/ in code"
    log_pass "no new script reaches into console's .ci/scripts/ tree"

    # ...and in those two, the reference is guarded by an existence test, so a
    # repo without ci-start.sh / ci-stop.sh SKIPS rather than breaks.
    while IFS= read -r line; do
        [[ -z "$line" ]] && continue
        assert_contains "$(cat "$bp/$line")" '-x "$REPO_ROOT/.ci/scripts/' \
            "$line must guard its console hook with an [[ -x ]] existence test"
    done <<<"$ALLOWED_CONSOLE_HOOKS"
    log_pass "both console hooks are [[ -x ]]-guarded (absent tree => skip, not break)"
}

# =============================================================================
# b) none of common.sh's non-portable helpers came along
# =============================================================================
test_no_nonportable_common_helpers() {
    local bp hits
    bp="$(make_isolated "$1")"

    hits="$(bp_code_hits "$bp" 'get_repo_root|r2_count_objects|require_submodule')"
    assert_eq "$hits" "" "console's non-portable common.sh helpers must not be used"
    log_pass "no get_repo_root / r2_count_objects / require_submodule in code"

    # Both directions: the omission has to be DOCUMENTED, not accidental, or the
    # next person re-adds them from common.sh without knowing why they are gone.
    assert_contains "$(cat "$bp/lib/breakpoint-common.sh")" "DELIBERATELY NOT COPIED" \
        "breakpoint-common.sh must record which common.sh helpers were skipped"
    log_pass "breakpoint-common.sh documents the deliberately-omitted helpers"
}

# =============================================================================
# c) no GitHub App / token plumbing (console-only, and a secret dependency)
# =============================================================================
test_no_app_token_plumbing() {
    local bp hits
    bp="$(make_isolated "$1")"

    # Not comment-stripped on purpose: even a commented-out app-token step is a
    # copy-paste hazard in a repo that has no such app registered.
    hits="$(grep -rlE 'app-token|vars\.APP_ID|APP_PRIVATE_KEY' "$bp" || true)"
    assert_eq "$hits" "" "breakpoint must not depend on console's GitHub App token"
    log_pass "zero app-token / APP_ID / APP_PRIVATE_KEY references anywhere in the folder"
}

# =============================================================================
# d) the upstream slug lives in conf, not welded into scripts
# =============================================================================
test_upstream_slug_is_configurable() {
    local bp hit file lineno text
    bp="$(make_isolated "$1")"

    # PRESENT, in the one file that is meant to carry it.
    assert_contains "$(cat "$bp/breakpoint.conf")" 'BREAKPOINT_UPSTREAM_REPO="rediacc/console"' \
        "breakpoint.conf must declare the canonical repo"
    log_pass "breakpoint.conf carries BREAKPOINT_UPSTREAM_REPO=rediacc/console"

    # ABSENT from scripts, except in a conf-overridable shape.
    #
    # FINDING (reported, not fixed -- .ci/breakpoint/ is another owner's): three
    # code lines DO name rediacc/console. Two are `${BREAKPOINT_UPSTREAM_REPO:-
    # rediacc/console}` fallbacks (harmless: conf wins, and every vendored copy
    # ships a conf) and one is an `e.g.` in an error message. A blanket
    # zero-reference assertion is therefore false today; this pins the two shapes
    # that are safe so that a NEW, non-overridable hardcode is red.
    while IFS= read -r hit; do
        [[ -z "$hit" ]] && continue
        file="${hit%:*}"
        lineno="${hit##*:}"
        text="$(sed -n "${lineno}p" "$bp/$file")"
        if [[ "$text" != *'BREAKPOINT_UPSTREAM_REPO'* ]] && [[ "$text" != *'e.g.'* ]]; then
            log_fail "hardcoded upstream slug in $file:$lineno (not conf-overridable): $text"
        fi
    done < <(bp_code_hits "$bp" 'rediacc/')
    log_pass "every rediacc/ reference in a script is conf-overridable or diagnostic"
}

# =============================================================================
# e) the workflow cannot be dispatched onto a runner that cannot host a session
# =============================================================================
test_workflow_runner_choices() {
    local bp wf opts
    bp="$(make_isolated "$1")"
    wf="$bp/workflow/breakpoint.yml"

    # ubuntu-slim's hard 15-minute cap makes a debug session impossible: the box
    # dies mid-investigation, which reads as a breakpoint bug rather than as a
    # runner limit. Offering it as a choice is offering a trap.
    opts="$(awk '/^      runner:/ { inside = 1 } inside && /^          - / { print } inside && /^$/ { inside = 0 }' "$wf")"
    [[ -n "$opts" ]] || log_fail "could not parse the runner choice options out of $wf"
    assert_not_contains "$opts" "ubuntu-slim" "ubuntu-slim must not be a runner choice (15-min cap)"
    log_pass "workflow does not offer ubuntu-slim as a session runner"

    assert_contains "$opts" "'ubuntu-latest'" "ubuntu-latest must be among the runner choices"
    assert_contains "$(grep -A 5 '^      runner:' "$wf")" "default: 'ubuntu-latest'" \
        "ubuntu-latest must be the default runner"
    log_pass "ubuntu-latest is offered and is the default runner"
}

# =============================================================================
# f) every script parses with no console around it
# =============================================================================
test_all_scripts_parse_standalone() {
    local bp f checked=0
    bp="$(make_isolated "$1")"

    while IFS= read -r f; do
        [[ "$f" == *.sh ]] || continue
        if ! env -i PATH="$PATH" bash -n "$bp/$f" 2>/dev/null; then
            log_fail "bash -n failed for $f in the isolated copy"
        fi
        checked=$((checked + 1))
    done < <(bp_files "$bp")

    ((checked >= 10)) || log_fail "only $checked scripts were syntax-checked; the fixture looks empty"
    log_pass "bash -n clean on all $checked shell scripts in the isolated copy"
}

# =============================================================================
# g) the folder SELF-VERIFIES with no console around it
# =============================================================================
test_drift_gate_runs_standalone() {
    local bp rc=0 out
    bp="$(make_isolated "$1")"

    # This is the assertion that makes the rest credible: the integrity gate is
    # the one script a downstream repo MUST be able to run, and it must not need
    # console's .ci/, a git remote, or the network to do it.
    out="$(env -i PATH="$PATH" HOME="$1" RUNNER_TEMP="$1" \
        bash "$bp/scripts/check-breakpoint-drift.sh" 2>&1)" || rc=$?
    assert_exit_code 0 "$rc" "check-breakpoint-drift.sh must pass inside an isolated copy"
    assert_contains "$out" "Verified" "the drift gate must report what it verified"
    assert_not_contains "$out" "Verified 0 files" "a drift gate that verified nothing is vacuous"
    log_pass "check-breakpoint-drift.sh self-verifies standalone (no .ci/scripts, no .git)"
}

# =============================================================================
# h) the vendored BLOCKER phrase list has not rotted away from the canonical one
# =============================================================================
test_vendored_blocker_list_is_a_subset() {
    local bp phrase canon vendored missing=0 count=0
    bp="$(make_isolated "$1")"

    if [[ ! -f "$CANONICAL_VALIDATOR" ]]; then
        # Downstream: there is no canonical file to compare against, and that is
        # the normal state there. Skipping is correct -- but it must be SAID, or
        # a silently-skipped subset check looks identical to a passing one.
        log_pass "SKIPPED (no $CANONICAL_VALIDATOR here): subset check is console-only"
        return 0
    fi

    canon="$(extract_array "$CANONICAL_VALIDATOR" "LOW_EFFORT_BLOCKER_PATTERNS")"
    vendored="$(extract_array "$bp/lib/breakpoint-blocker.sh" "BREAKPOINT_LOW_EFFORT_BLOCKERS")"

    [[ -n "$canon" ]] || log_fail "could not parse LOW_EFFORT_BLOCKER_PATTERNS out of $CANONICAL_VALIDATOR"
    [[ -n "$vendored" ]] || log_fail "could not parse BREAKPOINT_LOW_EFFORT_BLOCKERS out of the vendored copy"

    while IFS= read -r phrase; do
        [[ -z "$phrase" ]] && continue
        count=$((count + 1))
        if ! printf '%s\n' "$canon" | grep -qxF "$phrase"; then
            echo "  vendored-only phrase: '$phrase'" >&2
            missing=$((missing + 1))
        fi
    done <<<"$vendored"

    ((count >= 20)) || log_fail "only $count vendored phrases parsed; the extractor is broken, not the list"
    assert_eq "$missing" "0" "the vendored blocker list must stay a SUBSET of the canonical one"
    log_pass "all $count vendored BLOCKER phrases exist in the canonical validator"
}

with_temp_dir test_console_script_tree_is_optional
with_temp_dir test_no_nonportable_common_helpers
with_temp_dir test_no_app_token_plumbing
with_temp_dir test_upstream_slug_is_configurable
with_temp_dir test_workflow_runner_choices
with_temp_dir test_all_scripts_parse_standalone
with_temp_dir test_drift_gate_runs_standalone
with_temp_dir test_vendored_blocker_list_is_a_subset
