#!/bin/bash
# Gate test: every vite `onwarn(` callback must be preceded by a substantive
# rationale comment (>= 30 chars after stripping the leading `//` prefix).
#
# Vite's `onwarn` is a suppression surface — it can silently filter out any
# rollup warning — so a new callback without a rationale is a footgun.
# Today there is exactly one site (packages/web/vite.config.ts:92). This
# gate fails loudly the moment a new one lands without a comment.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
# shellcheck source=../lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test/gates/test-*.sh
source "$SCRIPT_DIR/../lib/test-helpers.sh"
# shellcheck source=../../lib/blocker-validator.sh
# BLOCKER: validate_blocker_quality enforces 30-char minimum + banned-phrase list
source "$REPO_ROOT/.ci/scripts/lib/blocker-validator.sh"

# Collect every vite / electron-vite config file across packages/.
CONFIGS=()
while IFS= read -r f; do
    [[ -z "$f" ]] && continue
    CONFIGS+=("$f")
done < <(find "$REPO_ROOT/packages" -maxdepth 3 -type f \
    \( -name 'vite.config.ts' -o -name 'electron.vite.config.ts' \) 2>/dev/null)

# For each file, find every line matching onwarn( and scan a small window
# AROUND it (5 lines before and 5 lines after) for // comments. Concatenate
# any comments found; require the concatenation to pass validate_blocker_quality.
# Scanning both sides handles the common pattern where rationale lives inside
# the callback body rather than above the declaration.
scan_file() {
    local file="$1"
    local line lineno combined
    local -a fails=()

    while IFS=: read -r lineno _; do
        [[ -z "$lineno" ]] && continue
        combined=""
        local start=$((lineno - 5))
        ((start < 1)) && start=1
        local end=$((lineno + 5))
        local probe
        for ((probe = start; probe <= end; probe++)); do
            line=$(sed -n "${probe}p" "$file")
            # Strip leading whitespace
            local stripped
            stripped="${line#"${line%%[![:space:]]*}"}"
            if [[ "$stripped" =~ ^// ]]; then
                local text="${stripped#//}"
                text="${text#"${text%%[![:space:]]*}"}"
                combined="$combined $text"
            fi
        done
        combined="${combined#"${combined%%[![:space:]]*}"}"
        combined="${combined%"${combined##*[![:space:]]}"}"
        if [[ -z "$combined" ]]; then
            fails+=("$file:$lineno: onwarn( has no preceding // rationale comment")
            continue
        fi
        if ! validate_blocker_quality "onwarn@$file:$lineno" "$combined" "$file" >/dev/null 2>&1; then
            fails+=("$file:$lineno: rationale comment is too short or low-effort (\"$combined\")")
        fi
    done < <(grep -n 'onwarn(' "$file" || true)

    if ((${#fails[@]} > 0)); then
        for f in "${fails[@]}"; do echo "$f"; done
        return 1
    fi
    return 0
}

test_real_configs_pass() {
    local all_ok=1
    for cfg in "${CONFIGS[@]}"; do
        local out rc=0
        out=$(scan_file "$cfg") || rc=$?
        if [[ $rc -ne 0 ]]; then
            echo "$out"
            all_ok=0
        fi
    done
    if ((all_ok == 0)); then
        log_fail "vite onwarn rationale gate failed on real repo"
    fi
    log_pass "every real vite.config onwarn() site has a substantive rationale comment"
}

test_crafted_missing_comment_fails() {
    local TEMP tmpfile
    TEMP="$(mktemp -d)"
    # shellcheck disable=SC2064
    # BLOCKER: expand TEMP now so the trap binds the specific path
    trap "rm -rf '$TEMP'" RETURN
    tmpfile="$TEMP/vite.config.ts"
    cat >"$tmpfile" <<'TS'
import { defineConfig } from 'vite';
export default defineConfig({
  build: {
    rollupOptions: {
      onwarn(warning, warn) {
        throw new Error(warning.message);
      },
    },
  },
});
TS
    local out rc=0
    out=$(scan_file "$tmpfile") || rc=$?
    assert_exit_code 1 "$rc" "missing rationale comment must fail"
    assert_contains "$out" "no preceding // rationale comment" "error names the problem"
    log_pass "onwarn without a rationale comment is rejected"
}

test_crafted_short_comment_fails() {
    local TEMP tmpfile
    TEMP="$(mktemp -d)"
    # shellcheck disable=SC2064
    # BLOCKER: expand TEMP now so the trap binds the specific path
    trap "rm -rf '$TEMP'" RETURN
    tmpfile="$TEMP/vite.config.ts"
    cat >"$tmpfile" <<'TS'
import { defineConfig } from 'vite';
export default defineConfig({
  build: {
    rollupOptions: {
      // ok
      onwarn(warning, warn) {
        throw new Error(warning.message);
      },
    },
  },
});
TS
    local out rc=0
    out=$(scan_file "$tmpfile") || rc=$?
    assert_exit_code 1 "$rc" "too-short rationale must fail"
    assert_contains "$out" "too short or low-effort" "error names the issue"
    log_pass "short rationale comment is rejected"
}

test_crafted_good_comment_passes() {
    local TEMP tmpfile
    TEMP="$(mktemp -d)"
    # shellcheck disable=SC2064
    # BLOCKER: expand TEMP now so the trap binds the specific path
    trap "rm -rf '$TEMP'" RETURN
    tmpfile="$TEMP/vite.config.ts"
    cat >"$tmpfile" <<'TS'
import { defineConfig } from 'vite';
export default defineConfig({
  build: {
    rollupOptions: {
      // Fail build on circular dependency warnings in our own code
      // (ignore node_modules which may have internal circular deps)
      onwarn(warning, warn) {
        if (warning.code === 'CIRCULAR_DEPENDENCY') {
          throw new Error(warning.message);
        }
        warn(warning);
      },
    },
  },
});
TS
    local out rc=0
    out=$(scan_file "$tmpfile") || rc=$?
    assert_exit_code 0 "$rc" "substantive rationale must pass"
    log_pass "substantive rationale comment is accepted"
}

log_test "test-vite-onwarn-comment"
if ((${#CONFIGS[@]} == 0)); then
    log_fail "no vite.config.ts files found — scan pattern may be wrong"
fi
test_real_configs_pass
test_crafted_missing_comment_fails
test_crafted_short_comment_fails
test_crafted_good_comment_passes
echo ""
log_pass "all tests passed"
