#!/bin/bash
# Both-ways test for the env-shell-var rule in .ci/scripts/quality/check-workflows.sh.
#
# THE BUG IT GUARDS. GitHub does not expand shell syntax in an `env:` VALUE --
# only `${{ }}` expressions -- and bash does not recursively expand a variable's
# value. So
#
#     env:
#       SSH_KEY: $RUNNER_TEMP/renet/staging/.ssh/id_rsa
#
# reaches the script as a literal string starting with a dollar sign, and the
# failure is a baffling "chown: cannot access '$RUNNER_TEMP/renet'". Observed on
# OPS Provision, run 29830623794.
#
# It is specifically an INLINE-EXTRACTION hazard: inside a `run:` block the shell
# does expand $RUNNER_TEMP, so moving that same text into `env:` while extracting
# a script silently changes its meaning. That is exactly how it got there.
#
# WHY THIS TEST EXISTS AT ALL. The rule was born VACUOUS. Its first version used
# `\b` for a word boundary, but in awk regex `\b` is a BACKSPACE -- and because
# it was written through a non-raw Python string, a literal 0x08 byte landed in
# the script. The regex therefore required an actual backspace character and
# matched nothing, while the gate reported "All workflows are clean". It was
# caught only by planting a violation and watching it NOT fire. A rule that has
# already been silently dead once does not get to rely on review.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
# shellcheck source=../lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test gate
source "$SCRIPT_DIR/../lib/test-helpers.sh"

CHECK="$REPO_ROOT/.ci/scripts/quality/check-workflows.sh"

LAST_OUT=""

# run_check <dir> — drives ONLY the workflow rules against a fixture tree.
run_check() {
    local dir="$1" rc=0
    LAST_OUT="$(CI=true WORKFLOW_INLINE_ONLY=1 WORKFLOW_DIR="$dir" bash "$CHECK" 2>&1)" || rc=$?
    return "$rc"
}

# write_wf <path> <env-block-lines...>
write_wf() {
    local path="$1"
    shift
    {
        echo "name: fixture"
        echo "on: push"
        echo "jobs:"
        echo "  j:"
        echo "    runs-on: ubuntu-latest"
        echo "    steps:"
        echo "      - run: ./script.sh"
        echo "        env:"
        printf '          %s\n' "$@"
    } >"$path"
}

# ---------------------------------------------------------------------------

test_flags_runner_temp() {
    local d="$1"
    write_wf "$d/bad.yml" 'SSH_KEY: $RUNNER_TEMP/renet/id_rsa' 'ATTEMPTS: 15'

    local rc=0
    run_check "$d" || rc=$?
    assert_exit_code 1 "$rc" 'a literal $RUNNER_TEMP in an env: value must fail'
    assert_contains "$LAST_OUT" "shell syntax GitHub will not expand" "explains the mechanism"
    assert_contains "$LAST_OUT" "bad.yml:9" "cites file:line"
    assert_contains "$LAST_OUT" "runner.temp" "names the context to use instead"
    log_pass 'flags $RUNNER_TEMP in an env: value, with file:line and the remedy'
}

test_flags_home() {
    # $HOME has NO GitHub context equivalent, so the remedy differs -- but it is
    # just as broken in an env: value, and must still be caught.
    local d="$1"
    write_wf "$d/bad.yml" 'SSH_KEY: $HOME/.ssh/id_ed25519'

    local rc=0
    run_check "$d" || rc=$?
    assert_exit_code 1 "$rc" 'a literal $HOME in an env: value must fail'
    log_pass 'flags $HOME too, which has no context equivalent'
}

test_context_form_passes() {
    local d="$1"
    write_wf "$d/ok.yml" 'SSH_KEY: ${{ runner.temp }}/renet/id_rsa' 'ATTEMPTS: 15'

    local rc=0
    run_check "$d" || rc=$?
    assert_exit_code 0 "$rc" 'the ${{ }} context form is the fix and must pass'
    log_pass 'the ${{ runner.temp }} form passes'
}

test_longer_name_is_reported_as_itself() {
    # REWRITTEN 2026-09-02 when the rule widened from six names to ANY $IDENT.
    # Under the six-name rule this case asserted exit 0: $HOMEBREW_PREFIX must
    # not be flagged BY MISTAKE as $HOME. Under the widened rule it is flagged
    # ON PURPOSE -- GitHub does not expand $HOMEBREW_PREFIX in an env: value any
    # more than it expands $HOME, so it ships the literal string. The concern
    # that survives is the substring one: the report must name the variable
    # that is actually there, not a shorter one hiding inside it.
    local d="$1"
    write_wf "$d/bad.yml" 'BREW: $HOMEBREW_PREFIX/bin' 'OTHER: $RUNNER_TEMPLATE_X'

    local rc=0
    run_check "$d" || rc=$?
    assert_exit_code 1 "$rc" 'any unexpanded $IDENT in an env: value is a violation, long names included'
    # run_check captures the gate's stdout+stderr into LAST_OUT; the offending
    # line is echoed there by check_env_shell_vars.
    grep -q 'HOMEBREW_PREFIX' <<<"$LAST_OUT" || {
        log_fail 'the report must name $HOMEBREW_PREFIX itself, not a substring of it'
        return 1
    }
    log_pass '$HOMEBREW_PREFIX / $RUNNER_TEMPLATE_X are flagged, and reported as themselves'
}

test_arbitrary_variable_is_flagged() {
    # THE CASE THE WIDENING EXISTS FOR. The six-name rule let this through, and
    # it is the exact idiom a job-start secret fetch invites: the value looks
    # like it flows and ships an EMPTY string, because GitHub never expands it.
    local d="$1"
    write_wf "$d/bad.yml" 'SECRET_API_KEY: $ACCOUNT_SERVER_API_KEY'

    local rc=0
    run_check "$d" || rc=$?
    assert_exit_code 1 "$rc" 'SECRET_X: $SOME_VAR in an env: block must be flagged'
    log_pass 'an arbitrary $IDENT (not one of the old six) is flagged'
}

test_comment_line_in_env_block_is_ignored() {
    # A comment inside an env: mapping is prose, not a value. housekeeping.yml
    # documents `${IN_FLIGHT_VERSION:-}` this way and must not read as a hit.
    local d="$1"
    write_wf "$d/ok.yml" '# the ${SOME_DEFAULT:-} form in the script no-ops when absent' 'REAL: plain'

    local rc=0
    run_check "$d" || rc=$?
    assert_exit_code 0 "$rc" 'a comment line inside env: must not be flagged'
    log_pass 'a comment line inside an env: block is ignored'
}

test_run_body_is_not_flagged() {
    # Inside `run:` the shell DOES expand these, so flagging them would be wrong
    # -- and would make the rule unusable. Only env: VALUES are in scope.
    local d="$1"
    {
        echo "name: fixture"
        echo "on: push"
        echo "jobs:"
        echo "  j:"
        echo "    runs-on: ubuntu-latest"
        echo "    steps:"
        echo '      - run: SSH_KEY="$HOME/.ssh/id_ed25519" ./script.sh'
        echo "      - run: |"
        echo '          chown -R "$(whoami)" "$RUNNER_TEMP/renet"'
    } >"$d/ok.yml"

    local rc=0
    run_check "$d" || rc=$?
    assert_exit_code 0 "$rc" 'shell vars inside run: are expanded by the shell and must not be flagged'
    log_pass 'run: bodies are out of scope (the shell expands them there)'
}

test_env_block_ends_at_dedent() {
    # A shell var appearing AFTER the env: mapping closes belongs to a later
    # key, not to env:. If the scanner never exits the block it would flag the
    # whole rest of the file.
    local d="$1"
    {
        echo "name: fixture"
        echo "on: push"
        echo "jobs:"
        echo "  j:"
        echo "    runs-on: ubuntu-latest"
        echo "    steps:"
        echo "      - run: ./a.sh"
        echo "        env:"
        echo "          OK: plain-value"
        echo '      - run: echo "$RUNNER_TEMP"'
    } >"$d/ok.yml"

    local rc=0
    run_check "$d" || rc=$?
    assert_exit_code 0 "$rc" 'the env: block must end at the dedent'
    log_pass 'scanner leaves the env: block at the dedent'
}

log_test "test-workflow-env-shell-vars"
with_temp_dir test_flags_runner_temp
with_temp_dir test_flags_home
with_temp_dir test_context_form_passes
with_temp_dir test_longer_name_is_reported_as_itself
with_temp_dir test_arbitrary_variable_is_flagged
with_temp_dir test_comment_line_in_env_block_is_ignored
with_temp_dir test_run_body_is_not_flagged
with_temp_dir test_env_block_ends_at_dedent
echo ""
log_pass "all tests passed"
