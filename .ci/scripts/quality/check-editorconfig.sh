#!/bin/bash
# Enforce .editorconfig rules across the entire repository
#
# Checks:
#   1. All tracked text files end with a final newline
#   2. No UTF-8 BOM in tracked text files
#   3. No CRLF line endings in tracked text files
#   4. No embedded NUL byte in a file whose extension says it must be text
#
# Respects .gitignore and only checks git-tracked files.
# Skips binary files. Includes submodule files.
#
# Usage: check-editorconfig.sh

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

REPO_ROOT="$(get_repo_root)"
cd "$REPO_ROOT"

# Extensions that must always be text; a NUL byte inside one is corruption,
# not content -- e.g. a literal NUL typed in a shell/TS source file where a
# `\0` escape sequence was meant (check-ci-parity.ts:163, found 2026-08-01).
# A real binary asset (png, woff, so, ...) never matches this list, which is
# what makes check 4 unable to false-positive on legitimate binaries: only a
# file `file --mime-encoding` calls binary AND whose extension says it must
# be text gets flagged, and normal binary assets never have such extensions.
TEXT_EXTENSIONS_RE='\.(sh|ts|tsx|js|jsx|cjs|mjs|json|jsonc|yml|yaml|md|mdx|go|py|css|html|toml|txt)$'

# ── Control: the NUL-byte check must be able to FIRE before its green means
# anything -- a check that skips every binary-flagged file (as check 4's own
# branch does, on purpose, for real binary assets) is exactly the shape of
# gate that can silently stop firing if the corruption detection regresses.
_selftest_dir="$(mktemp -d)"
trap 'rm -rf "$_selftest_dir"' EXIT
_selftest_file="$_selftest_dir/control.ts"
printf 'const x = 1;\x00\nconst y = 2;\n' >"$_selftest_file"
if ! (file --mime-encoding "$_selftest_file" 2>/dev/null | grep -q "binary" &&
    LC_ALL=C grep -qaP '\x00' "$_selftest_file" 2>/dev/null); then
    log_error "NUL-byte control did not fire: a synthetic .ts file with a planted NUL byte was not detected as binary+NUL. The detection logic is broken; do not trust this gate."
    exit 1
fi
log_info "Control: planted NUL byte in a synthetic .ts file fires as binary+NUL -- OK"

log_step "Checking editorconfig compliance across repository (including submodules)..."

ERRORS=0
MISSING_NEWLINE=()
HAS_BOM=()
HAS_CRLF=()
HAS_NUL_BYTE=()

# Get tracked text files from repo and all submodules
while IFS= read -r file; do
    [[ -z "$file" ]] && continue
    [[ ! -f "$file" ]] && continue

    # Skip binary files (check via file command), except check 4: a file
    # flagged binary whose extension says it must be text is corruption, not
    # a legitimate asset, and gets checked for the NUL byte that likely
    # caused `file` to call it binary in the first place.
    if file --mime-encoding "$file" 2>/dev/null | grep -q "binary"; then
        if [[ "$file" =~ $TEXT_EXTENSIONS_RE ]] && LC_ALL=C grep -qaP '\x00' "$file" 2>/dev/null; then
            HAS_NUL_BYTE+=("$file")
        fi
        continue
    fi

    # Skip machine-generated checksum files (.hash) — no final newline by design
    if [[ "$file" == *.hash ]]; then
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

done < <(git ls-files --recurse-submodules)

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

if [[ ${#HAS_NUL_BYTE[@]} -gt 0 ]]; then
    log_error "Text source files with an embedded NUL byte (${#HAS_NUL_BYTE[@]}):"
    for f in "${HAS_NUL_BYTE[@]}"; do
        echo "  $f"
    done
    log_error "  A NUL byte makes git treat the file as binary: diffs go unreviewable and it silently stops being 'text' to every downstream tool. Replace it with the \\\\0 escape sequence (or the intended literal character)."
    ERRORS=$((ERRORS + ${#HAS_NUL_BYTE[@]}))
fi

if [[ $ERRORS -gt 0 ]]; then
    echo ""
    log_error "Found $ERRORS editorconfig violation(s)"
    log_info "Ensure all text files: end with a newline, use UTF-8 without BOM, and use LF line endings"
    exit 1
else
    log_info "All tracked text files comply with .editorconfig rules"
fi
