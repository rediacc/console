#!/bin/bash
# Check content files for AI slop patterns
#
# Scans markdown documentation and blog posts against the banned phrase list
# defined in .ci/config/content-quality-patterns.conf
#
# Two severity levels:
#   ERROR - Blocks CI (exit 1)
#   WARN  - Informational only (logged but does not block)
#
# Suppression:
#   1. Inline: append <!-- slop-ok --> to any line
#   2. File-level: add path to .ci/config/content-quality-allowlist.txt
#   3. Code blocks: lines inside ``` fenced blocks are skipped automatically
#   4. Frontmatter: YAML frontmatter (between --- markers) is skipped
#
# Usage: check-content-quality.sh [file ...]

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

REPO_ROOT="$(get_repo_root)"
cd "$REPO_ROOT"

PATTERNS_FILE=".ci/config/content-quality-patterns.conf"
ALLOWLIST_FILE=".ci/config/content-quality-allowlist.txt"

CONTENT_DIRS=(
    "packages/www/src/content/docs"
    "packages/www/src/content/blog"
)

ERRORS=0
WARNINGS=0

# ──────────────────────────────────────────────
# Load patterns from .conf file
# ──────────────────────────────────────────────

ERROR_PATTERNS=()
WARN_PATTERNS=()

load_patterns() {
    local severity="ERROR"
    while IFS= read -r line || [[ -n "$line" ]]; do
        [[ -z "${line// /}" ]] && continue
        if [[ "$line" == "# [ERROR]" ]]; then
            severity="ERROR"
            continue
        fi
        if [[ "$line" == "# [WARN]" ]]; then
            severity="WARN"
            continue
        fi
        [[ "$line" == \#* ]] && continue
        if [[ "$severity" == "ERROR" ]]; then
            ERROR_PATTERNS+=("$line")
        else
            WARN_PATTERNS+=("$line")
        fi
    done <"$PATTERNS_FILE"
}

# ──────────────────────────────────────────────
# Load file-level allowlist
# ──────────────────────────────────────────────

declare -A ALLOWLISTED_FILES

load_allowlist() {
    [[ ! -f "$ALLOWLIST_FILE" ]] && return
    while IFS= read -r line || [[ -n "$line" ]]; do
        [[ -z "${line// /}" ]] && continue
        [[ "$line" == \#* ]] && continue
        ALLOWLISTED_FILES["$line"]=1
    done <"$ALLOWLIST_FILE"
}

# ──────────────────────────────────────────────
# Build combined regex from pattern array
# ──────────────────────────────────────────────

build_regex() {
    local IFS='|'
    echo "$*"
}

# ──────────────────────────────────────────────
# Use awk to filter a grep-output stream:
# removes lines inside frontmatter, code blocks,
# or containing <!-- slop-ok -->
# Input: file path + grep -n output (lineno:text)
# Output: filtered lineno:text lines
# ──────────────────────────────────────────────

filter_exempt_lines() {
    local file="$1"
    local grep_output="$2"
    [[ -z "$grep_output" ]] && return

    # Build a set of exempt line numbers using awk (single pass over file)
    local exempt_lines
    exempt_lines=$(awk '
        BEGIN { fm=0; cb=0 }
        /^---$/ && cb==0 { fm++; if (fm<=2) { print NR; next } }
        fm==1 { print NR; next }
        /^```/ { cb=1-cb; print NR; next }
        cb==1 { print NR; next }
        /<!-- slop-ok -->/ { print NR; next }
    ' "$file")

    # If no exempt lines, pass everything through
    if [[ -z "$exempt_lines" ]]; then
        echo "$grep_output"
        return
    fi

    # Filter: remove grep output lines whose line numbers are in the exempt set
    # Use awk for O(n) filtering with an associative array
    echo "$grep_output" | awk -F: -v exempt="$exempt_lines" '
        BEGIN { split(exempt, arr, "\n"); for (i in arr) ex[arr[i]]=1 }
        { if (!($1 in ex)) print }
    '
}

# ──────────────────────────────────────────────
# Identify which pattern matched (fast: test
# each pattern only against the matched line)
# ──────────────────────────────────────────────

identify_pattern() {
    local line="$1"
    shift
    local patterns=("$@")
    # Fast path: check single-char patterns with bash builtins (no grep)
    for p in "${patterns[@]}"; do
        if [[ ${#p} -le 3 ]] && [[ "$line" == *"$p"* ]]; then
            echo "$p"
            return
        fi
    done
    # Slow path: regex patterns via grep
    for p in "${patterns[@]}"; do
        [[ ${#p} -le 3 ]] && continue # already checked above
        if echo "$line" | grep -iqE "$p"; then
            echo "$p"
            return
        fi
    done
    echo "(unknown)"
}

# ──────────────────────────────────────────────
# Report a violation
# ──────────────────────────────────────────────

report_violation() {
    local severity="$1"
    local file="$2"
    local lineno="$3"
    local pattern="$4"
    local line_text="$5"

    if [[ ${#line_text} -gt 120 ]]; then
        line_text="${line_text:0:117}..."
    fi

    if [[ "$severity" == "ERROR" ]]; then
        log_error "$file:$lineno"
        echo "         Pattern: \"$pattern\""
        echo "         Line:    $line_text"
        ERRORS=$((ERRORS + 1))
    else
        log_warn "$file:$lineno"
        echo "         Pattern: \"$pattern\""
        echo "         Line:    $line_text"
        WARNINGS=$((WARNINGS + 1))
    fi
}

# ──────────────────────────────────────────────
# Scan a single file
# ──────────────────────────────────────────────

scan_file() {
    local file="$1"
    local rel_file="${file#"$REPO_ROOT/"}"

    if [[ -n "${ALLOWLISTED_FILES[$rel_file]+x}" ]]; then
        return
    fi

    local error_regex=""
    local warn_regex=""
    if [[ ${#ERROR_PATTERNS[@]} -gt 0 ]]; then
        error_regex="$(build_regex "${ERROR_PATTERNS[@]}")"
    fi
    if [[ ${#WARN_PATTERNS[@]} -gt 0 ]]; then
        warn_regex="$(build_regex "${WARN_PATTERNS[@]}")"
    fi

    # Fast grep pass (file-level, no line-by-line bash)
    local error_raw="" warn_raw=""

    if [[ -n "$error_regex" ]]; then
        error_raw="$(grep -inE "$error_regex" "$file" 2>/dev/null || true)"
    fi
    if [[ -n "$warn_regex" ]]; then
        warn_raw="$(grep -inE "$warn_regex" "$file" 2>/dev/null || true)"
    fi

    # Nothing found
    if [[ -z "$error_raw" ]] && [[ -z "$warn_raw" ]]; then
        return
    fi

    # Filter exempt lines (awk-based, fast)
    local error_filtered="" warn_filtered=""
    if [[ -n "$error_raw" ]]; then
        error_filtered="$(filter_exempt_lines "$file" "$error_raw")"
    fi
    if [[ -n "$warn_raw" ]]; then
        warn_filtered="$(filter_exempt_lines "$file" "$warn_raw")"
    fi

    # Process error matches
    if [[ -n "$error_filtered" ]]; then
        while IFS= read -r match_line; do
            [[ -z "$match_line" ]] && continue
            local lineno="${match_line%%:*}"
            local line_text="${match_line#*:}"
            local pattern
            pattern="$(identify_pattern "$line_text" "${ERROR_PATTERNS[@]}")"
            report_violation "ERROR" "$rel_file" "$lineno" "$pattern" "$line_text"
        done <<<"$error_filtered"
    fi

    # Process warn matches
    if [[ -n "$warn_filtered" ]]; then
        while IFS= read -r match_line; do
            [[ -z "$match_line" ]] && continue
            local lineno="${match_line%%:*}"
            local line_text="${match_line#*:}"
            local pattern
            pattern="$(identify_pattern "$line_text" "${WARN_PATTERNS[@]}")"
            report_violation "WARN" "$rel_file" "$lineno" "$pattern" "$line_text"
        done <<<"$warn_filtered"
    fi

    # NOTE: Double-dash ( -- ) detection was removed because ` -- ` is a
    # legitimate CLI argument separator (e.g., `renet compose -- up -d`,
    # `npm run dev -- --host`). Detecting it requires understanding whether
    # the context is prose or a command, which grep cannot distinguish
    # reliably. The em dash pattern (U+2014) in the patterns file catches
    # the actual AI tell.
}

# ──────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────

log_step "Checking content quality (anti-slop patterns)..."

if [[ ! -f "$PATTERNS_FILE" ]]; then
    log_error "Pattern file not found: $PATTERNS_FILE"
    exit 1
fi

load_patterns
load_allowlist

log_info "Loaded ${#ERROR_PATTERNS[@]} error patterns, ${#WARN_PATTERNS[@]} warn patterns"

FILES=()
if [[ $# -gt 0 ]]; then
    FILES=("$@")
else
    for dir in "${CONTENT_DIRS[@]}"; do
        if [[ -d "$dir" ]]; then
            while IFS= read -r f; do
                FILES+=("$f")
            done < <(find "$dir" -name '*.md' -type f)
        fi
    done
fi

log_info "Scanning ${#FILES[@]} content files..."

for file in "${FILES[@]}"; do
    scan_file "$file"
done

echo ""
if [[ $ERRORS -gt 0 ]] || [[ $WARNINGS -gt 0 ]]; then
    [[ $WARNINGS -gt 0 ]] && log_warn "$WARNINGS warning(s) (review recommended)"
    if [[ $ERRORS -gt 0 ]]; then
        log_error "$ERRORS content quality violation(s) found"
        log_info "Fix violations by restructuring: use periods, commas, colons, or parentheses."
        log_info "Do NOT replace em dashes with hyphens. Restructure the sentence instead."
        log_info "Suppress specific lines with <!-- slop-ok --> (use sparingly)."
        log_info "Pattern definitions: $PATTERNS_FILE"
        exit 1
    fi
else
    log_info "All content files pass quality checks"
fi
