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
_selftest_file="$_selftest_dir/control.ts"
printf 'const x = 1;\x00\nconst y = 2;\n' >"$_selftest_file"
if ! (file --mime-encoding "$_selftest_file" 2>/dev/null | grep -q "binary" &&
    LC_ALL=C grep -qaP '\x00' "$_selftest_file" 2>/dev/null); then
    log_error "NUL-byte control did not fire: a synthetic .ts file with a planted NUL byte was not detected as binary+NUL. The detection logic is broken; do not trust this gate."
    exit 1
fi
log_info "Control: planted NUL byte in a synthetic .ts file fires as binary+NUL -- OK"

# ── Control: the binary classifier must key on the ENCODING `file` reports, not
# on the path. The previous implementation ran `file --mime-encoding "$f" | grep
# -q binary` over the WHOLE line, so any path containing the substring "binary"
# was treated as a binary asset and silently exempted from the final-newline,
# BOM and CRLF checks. Five tracked text files matched, including
# .ci/scripts/test/gates/test-watchdog-binary-exec-guard.sh (us-ascii). A gate
# whose coverage depends on filenames is exactly the kind that goes quiet.
_classify() {
    awk -F': ' '$NF ~ /binary/ { sub(/: [^:]*$/, "", $0); print }'
}
if printf '%s\n' 'some-binary-name.sh: us-ascii' | _classify | grep -q .; then
    log_error "Binary-classifier control failed: a us-ascii file whose PATH contains 'binary' was classified as binary. Checks 1-3 would silently skip it."
    exit 1
fi
if ! printf '%s\n' 'assets/logo.png: binary' | _classify | grep -q .; then
    log_error "Binary-classifier control failed: a genuinely binary file was NOT classified as binary. The NUL-corruption path would never run."
    exit 1
fi
log_info "Control: classifier keys on encoding, not path -- OK"

log_step "Checking editorconfig compliance across repository (including submodules)..."

ERRORS=0
MISSING_NEWLINE=()
HAS_BOM=()
HAS_CRLF=()
HAS_NUL_BYTE=()

# BATCHED ON PURPOSE. The previous shape was a while-read loop that spawned
# `file`, `tail`, `head|od|grep` and `grep -P` PER FILE. Measured on this repo:
# 6,595 tracked files at ~87ms of process spawns each = ~573s, i.e. the gate
# looked hung and could not finish inside a 10-minute local run. Nothing was
# wrong with the checks; the cost was fork/exec.
#
# `file` is still the ONLY binary oracle, called with the same flags, so its
# heuristics cannot drift -- it is just invoked in batches via xargs instead of
# once per path. The other three checks are byte-exact (final newline, BOM,
# CRLF, NUL) and move into a single pass that reads each file once.
FILE_LIST="$(mktemp)"
BINARY_LIST="$(mktemp)"
trap 'rm -rf "$_selftest_dir" "$FILE_LIST" "$BINARY_LIST"' EXIT

git ls-files -z --recurse-submodules >"$FILE_LIST"

# One `file --mime-encoding` per batch of paths, not per path.
xargs -0 -a "$FILE_LIST" -r file --mime-encoding -- 2>/dev/null |
    awk -F': ' '$NF ~ /binary/ { sub(/: [^:]*$/, "", $0); print }' >"$BINARY_LIST" || true

# Single pass for every byte-exact check.
mapfile -t _findings < <(
    BINARY_LIST="$BINARY_LIST" TEXT_EXTENSIONS_RE="$TEXT_EXTENSIONS_RE" \
        python3 - "$FILE_LIST" <<'PYEOF'
import os, re, sys

file_list = sys.argv[1]
binary = set()
with open(os.environ["BINARY_LIST"], "r", errors="replace") as fh:
    for line in fh:
        line = line.rstrip("\n")
        if line:
            binary.add(line)

# The bash regex is ERE with escaped dots; Python needs the same meaning.
text_ext = re.compile(os.environ["TEXT_EXTENSIONS_RE"].replace("\\.", "\\."))

with open(file_list, "rb") as fh:
    paths = [p.decode("utf-8", "surrogateescape") for p in fh.read().split(b"\0") if p]

for path in paths:
    if not os.path.isfile(path) or os.path.islink(path):
        continue

    if path in binary:
        # Only corruption matters here: a file `file` calls binary whose
        # extension says it must be text.
        if text_ext.search(path):
            try:
                with open(path, "rb") as fh:
                    if b"\0" in fh.read():
                        print("NUL\t" + path)
            except OSError:
                pass
        continue

    if path.endswith(".hash"):
        continue

    try:
        with open(path, "rb") as fh:
            data = fh.read()
    except OSError:
        continue

    if not data:
        continue

    if not data.endswith(b"\n"):
        print("NEWLINE\t" + path)
    if data.startswith(b"\xef\xbb\xbf"):
        print("BOM\t" + path)
    if b"\r\n" in data:
        print("CRLF\t" + path)
PYEOF
)

for _finding in "${_findings[@]}"; do
    [[ -z "$_finding" ]] && continue
    _kind="${_finding%%$'\t'*}"
    _path="${_finding#*$'\t'}"
    case "$_kind" in
        NEWLINE) MISSING_NEWLINE+=("$_path") ;;
        BOM) HAS_BOM+=("$_path") ;;
        CRLF) HAS_CRLF+=("$_path") ;;
        NUL) HAS_NUL_BYTE+=("$_path") ;;
    esac
done

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
