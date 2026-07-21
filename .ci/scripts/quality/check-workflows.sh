#!/bin/bash
# Check workflow files for banned patterns
#
# Validates that GitHub Actions workflows and actions don't use patterns that
# violate CI design principles:
#   - continue-on-error: Silently ignores step/job failures
#   - script: |          Inline scripts violate multi-CI design (use .ci/scripts/)
#   (fail-fast was previously banned but GitHub defaults to true, not false.
#    Matrix fail-fast cancellation happens BEFORE the watchdog sees the failure.)
#
# Usage: check-workflows.sh

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

cd "$(get_repo_root)"

log_step "Checking workflows for banned patterns..."

ERRORS=0

# Collect all workflow and action YAML files
GITHUB_YAMLS=()
while IFS= read -r file; do
    GITHUB_YAMLS+=("$file")
done < <(find .github/workflows .github/actions -name "*.yml" -type f 2>/dev/null)

# --- Inline-run rule config (see check_inline_run_blocks below) ---------------
# Overridable so the standalone gate test can drive the rule against fixtures.
WORKFLOW_DIR="${WORKFLOW_DIR:-.github/workflows}"
INLINE_MAX_LOGIC="${INLINE_MAX_LOGIC:-8}"

# When the gate test exercises ONLY the inline-run rule, empty the file list the
# banned-pattern scans iterate so they become no-ops. This keeps the rule living
# in this one script while letting the test point WORKFLOW_DIR at a fixture tree
# without also tripping (or depending on) the real .github banned-pattern state.
if [[ "${WORKFLOW_INLINE_ONLY:-0}" == "1" ]]; then
    GITHUB_YAMLS=()
fi

# Check a banned pattern across all files
# Usage: check_pattern <grep_pattern> <label> <fix_hint>
check_pattern() {
    local pattern="$1"
    local label="$2"
    local fix_hint="$3"

    for file in "${GITHUB_YAMLS[@]}"; do
        matches=$(grep -n "$pattern" "$file" 2>/dev/null || true)
        if [[ -n "$matches" ]]; then
            while IFS= read -r match; do
                [[ -z "$match" ]] && continue
                local_line="${match%%:*}"
                local_content="${match#*:}"
                # Skip comments
                if echo "$local_content" | grep -qE "^\s*#"; then
                    continue
                fi
                # Skip lines with security approval comment
                if echo "$local_content" | grep -qF "# security: approved"; then
                    continue
                fi
                log_error "$file:$local_line: ${label} is banned"
                echo "  Line: $local_content"
                echo "  Fix:  $fix_hint"
                echo ""
                ((ERRORS++))
            done <<<"$matches"
        fi
    done
}

# Banned patterns
check_pattern \
    "continue-on-error" \
    "continue-on-error" \
    "Ensure upstream dependencies are correct so steps always succeed"

check_pattern \
    "script:[[:space:]]*|" \
    "inline script: |" \
    "Move script to .ci/scripts/ and use: script: return await require('./.ci/scripts/ci/my-script.cjs')({github, context, core})"

# fail-fast: no longer banned. GitHub defaults to true (not false as previously assumed).
# Matrix fail-fast cancellation happens at the GitHub level BEFORE the watchdog sees the failure.
# Jobs that need independent matrix entries should set fail-fast: false explicitly.

# Security: Ban pull_request_target (exposes secrets to fork PRs)
check_pattern \
    "pull_request_target" \
    "pull_request_target trigger" \
    "Use 'pull_request' instead. pull_request_target exposes secrets to forks. If required, add fork guard and '# security: approved' comment"

# Security: Ban secrets: inherit (explicit passing is safer)
check_pattern \
    "secrets:[[:space:]]*inherit" \
    "secrets: inherit" \
    "Pass required secrets explicitly: secrets: { APP_PRIVATE_KEY: \${{ secrets.APP_PRIVATE_KEY }} }"

# Security: Ban secrets in run blocks (shell injection risk)
# Secrets must be passed via env: blocks, never interpolated directly in run: shell code.
# Safe: env: { KEY: ${{ secrets.X }} } then run: echo "$KEY"
# Unsafe: run: echo "${{ secrets.X }}" | command
for file in "${GITHUB_YAMLS[@]}"; do
    matches=$(grep -n '\${{.*secrets\.' "$file" 2>/dev/null || true)
    if [[ -n "$matches" ]]; then
        while IFS= read -r match; do
            [[ -z "$match" ]] && continue
            local_line="${match%%:*}"
            local_content="${match#*:}"
            # Skip comments
            if echo "$local_content" | grep -qE "^\s*#"; then
                continue
            fi
            # Skip lines with security approval comment
            if echo "$local_content" | grep -qF "# security: approved"; then
                continue
            fi
            # Safe: YAML key-value assignment (key: value) where key is NOT 'run'
            # This covers env:, with:, secrets:, private-key:, password:, etc.
            if echo "$local_content" | grep -qE '^\s+[a-zA-Z][a-zA-Z0-9_-]*:' &&
                ! echo "$local_content" | grep -qE '^\s+run:'; then
                continue
            fi
            # Unsafe: secret interpolation in shell code (run: block or continuation line)
            log_error "$file:$local_line: secret used directly in shell code"
            echo "  Line: $local_content"
            echo "  Fix:  Move secret to env: block and reference as \$VAR_NAME in run:"
            echo ""
            ((ERRORS++))
        done <<<"$matches"
    fi
done

# Security: Ban unpinned third-party actions (tag-only references like @v3)
# All uses: references must use SHA pinning (e.g. @abc123...def  # v3)
# Local actions (./) are exempt since they're part of the repo
for file in "${GITHUB_YAMLS[@]}"; do
    # Match only YAML 'uses:' keys (indented, as a key, not part of another word)
    matches=$(grep -nE '^\s+uses:\s' "$file" 2>/dev/null || true)
    if [[ -n "$matches" ]]; then
        while IFS= read -r match; do
            [[ -z "$match" ]] && continue
            local_line="${match%%:*}"
            local_content="${match#*:}"
            # Skip comments
            if echo "$local_content" | grep -qE "^\s*#"; then
                continue
            fi
            # Skip local actions (./path)
            if echo "$local_content" | grep -qE 'uses:\s*\./'; then
                continue
            fi
            # Skip lines with security approval comment
            if echo "$local_content" | grep -qF "# security: approved"; then
                continue
            fi
            # Check if the action reference uses a SHA (40-char hex)
            if ! echo "$local_content" | grep -qE '@[a-f0-9]{40}'; then
                log_error "$file:$local_line: unpinned action reference"
                echo "  Line: $local_content"
                echo "  Fix:  Pin action to SHA commit hash (e.g. uses: actions/checkout@abc123...def  # v4)"
                echo ""
                ((ERRORS++))
            fi
        done <<<"$matches"
    fi
done

# =============================================================================
# Inline-run rule: workflow `run:` blocks must stay thin (env wiring + one call)
# =============================================================================
# CI step LOGIC belongs in .ci/scripts/<area>/<name>.sh, which is locally
# runnable and shareable across CI systems. A workflow `run:` block scalar whose
# shell logic (non-blank, non-comment lines) exceeds $INLINE_MAX_LOGIC lines is a
# violation. Full stop -- there is no baseline and no grandfathering.
#
# There used to be a ratchet: .ci/quality/workflow-inline-baseline.json froze 52
# legacy violations per-file and only allowed the counts to fall. All 52 were
# extracted, so the file and its ratchet logic are gone. Do not reintroduce them:
# an escape hatch that exists gets used, and the rule only actually held once the
# hatch was removed.
check_inline_run_blocks() {
    require_cmd jq
    require_cmd awk

    local awk_prog
    awk_prog="$(mktemp)"
    # BLOCKER: RETURN trap removes the temp awk program when the function unwinds under set -e
    # shellcheck disable=SC2064
    # BLOCKER: expand awk_prog now so the trap rm targets this exact temp path
    trap "rm -f '$awk_prog'" RETURN

    # Block-scalar parser: emit "<startline>\t<logiccount>\t<stepname>" per run: block.
    # A block owns every following line that is blank OR indented deeper than the
    # `run:` key; a logic line is a non-blank line whose first non-space char is not `#`.
    cat >"$awk_prog" <<'AWK_EOF'
function record() {
    if (inblock) {
        printf "%d\t%d\t%s\n", startline, count, sname
        inblock = 0
    }
}
{
    line = $0
    sub(/\r$/, "", line)
    if (line ~ /^[[:space:]]*$/) { next }
    match(line, /^ */)
    cur = RLENGTH
    if (inblock) {
        if (cur > keyindent) {
            rest = substr(line, cur + 1)
            if (substr(rest, 1, 1) != "#") count++
            next
        } else {
            record()
        }
    }
    if (line ~ /^[[:space:]]*(-[[:space:]]+)?name:[[:space:]]/) {
        nm = line
        sub(/^[[:space:]]*(-[[:space:]]+)?name:[[:space:]]*/, "", nm)
        sub(/[[:space:]]+$/, "", nm)
        stepname = nm
    }
    if (line ~ /^[[:space:]]*run:[[:space:]]*[|>]/) {
        keyindent = cur
        inblock = 1
        count = 0
        startline = NR
        sname = stepname
    }
}
END { record() }
AWK_EOF

    log_step "Checking workflow run: blocks stay thin (<= $INLINE_MAX_LOGIC logic lines)..."

    declare -A actual=()
    declare -A detail=()

    local f bn blocks start cnt name vcount d
    if [[ -d "$WORKFLOW_DIR" ]]; then
        for f in "$WORKFLOW_DIR"/*.yml; do
            [[ -e "$f" ]] || continue
            bn="$(basename "$f")"
            vcount=0
            d=""
            blocks="$(awk -f "$awk_prog" "$f")"
            while IFS=$'\t' read -r start cnt name; do
                [[ -z "$start" ]] && continue
                if ((cnt > INLINE_MAX_LOGIC)); then
                    vcount=$((vcount + 1))
                    d+="      - ${bn}:${start} (step: ${name:-<unnamed>}) has ${cnt} logic lines"$'\n'
                fi
            done <<<"$blocks"
            actual["$bn"]=$vcount
            [[ -n "$d" ]] && detail["$bn"]="$d"
        done
    fi

    # Anti-vacuity: no workflows parsed means the layout moved and this gate is
    # asserting nothing. Fail loudly rather than report a clean run.
    if ((${#actual[@]} == 0)); then
        log_error "No workflows found under $WORKFLOW_DIR -- this check is blind"
        ERRORS=$((ERRORS + 1))
        return
    fi

    local sorted=()
    while IFS= read -r _k; do
        [[ -n "$_k" ]] && sorted+=("$_k")
    done < <(printf '%s\n' "${!actual[@]}" | sort)

    local k
    for k in "${sorted[@]}"; do
        ((${actual[$k]} > 0)) || continue
        log_error "$WORKFLOW_DIR/$k: ${actual[$k]} inline run: block(s) exceed $INLINE_MAX_LOGIC logic lines"
        [[ -n "${detail[$k]:-}" ]] && printf '%s' "${detail[$k]}"
        echo "  Fix:  extract each over-threshold block to .ci/scripts/<area>/<name>.sh; the workflow step becomes env wiring + one script call, and the script header documents its required env + how to run it locally."
        echo ""
        ERRORS=$((ERRORS + 1))
    done
}

check_inline_run_blocks

if [[ $ERRORS -gt 0 ]]; then
    echo ""
    log_error "Found $ERRORS problem(s) in workflows"
    exit 1
else
    log_info "All workflows are clean"
fi
