#!/bin/bash
# Enforce .editorconfig rules across the entire repository
#
# Checks:
#   1. All tracked text files end with a final newline
#   2. No UTF-8 BOM in tracked text files
#   3. No CRLF line endings in tracked text files
#
# Respects .gitignore and only checks git-tracked files.
# Skips binary files, vendored directories, and submodules.
#
# Usage: check-editorconfig.sh

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

REPO_ROOT="$(get_repo_root)"
cd "$REPO_ROOT"

log_step "Checking editorconfig compliance across repository..."

ERRORS=0
MISSING_NEWLINE=()
HAS_BOM=()
HAS_CRLF=()

# Get all tracked files, excluding submodules
SUBMODULE_PATHS=()
while IFS= read -r path; do
    [[ -z "$path" ]] && continue
    SUBMODULE_PATHS+=("$path")
done < <(git config --file .gitmodules --get-regexp '^submodule\..*\.path$' 2>/dev/null | awk '{print $2}')

# Build grep exclude pattern for submodules
EXCLUDE_ARGS=()
for sub in "${SUBMODULE_PATHS[@]}"; do
    EXCLUDE_ARGS+=(":!${sub}")
done

# Get tracked text files (git ls-files with eol check)
while IFS= read -r file; do
    [[ -z "$file" ]] && continue
    [[ ! -f "$file" ]] && continue

    # Skip binary files (check via file command)
    if file --mime-encoding "$file" 2>/dev/null | grep -q "binary"; then
        continue
    fi

    # Skip empty files
    [[ ! -s "$file" ]] && continue

    # Check 1: Missing final newline
    if [[ -n "$(tail -c 1 "$file")" ]]; then
        MISSING_NEWLINE+=("$file")
    fi

    # Check 2: UTF-8 BOM (ef bb bf)
    if head -c 3 "$file" | od -An -tx1 2>/dev/null | grep -q "ef bb bf"; then
        HAS_BOM+=("$file")
    fi

    # Check 3: CRLF line endings
    if grep -Plc '\r\n' "$file" >/dev/null 2>&1; then
        HAS_CRLF+=("$file")
    fi

done < <(git ls-files -- . "${EXCLUDE_ARGS[@]}")

# Report results
if [[ ${#MISSING_NEWLINE[@]} -gt 0 ]]; then
    log_error "Files missing final newline (${#MISSING_NEWLINE[@]}):"
    for f in "${MISSING_NEWLINE[@]}"; do
        echo "  $f"
    done
    ERRORS=$((ERRORS + ${#MISSING_NEWLINE[@]}))
fi

if [[ ${#HAS_BOM[@]} -gt 0 ]]; then
    log_error "Files with UTF-8 BOM (${#HAS_BOM[@]}):"
    for f in "${HAS_BOM[@]}"; do
        echo "  $f"
    done
    ERRORS=$((ERRORS + ${#HAS_BOM[@]}))
fi

if [[ ${#HAS_CRLF[@]} -gt 0 ]]; then
    log_error "Files with CRLF line endings (${#HAS_CRLF[@]}):"
    for f in "${HAS_CRLF[@]}"; do
        echo "  $f"
    done
    ERRORS=$((ERRORS + ${#HAS_CRLF[@]}))
fi

if [[ $ERRORS -gt 0 ]]; then
    echo ""
    log_error "Found $ERRORS editorconfig violation(s)"
    log_info "Ensure all text files: end with a newline, use UTF-8 without BOM, and use LF line endings"
    exit 1
else
    log_info "All tracked text files comply with .editorconfig rules"
fi
