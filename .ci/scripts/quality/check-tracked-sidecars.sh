#!/bin/bash
# No stop-hook RUNTIME sidecar may be tracked by git.
#
# WHY THIS EXISTS. On 2026-08-05 a `git add -A` swept two runtime files into a
# commit: `.claude/hooks/stop/.sessions` and `.claude/hooks/stop/.waiter-aaaaaaaa`.
# They were removed by hand and added to .gitignore, and nothing whatsoever
# prevented their return -- every existing gate was blind to them by
# construction. These files have no static markers in source; they exist only
# while a session runs, so no linter, type-check or dead-code scan can see them.
# The only observable that distinguishes the defect is `git ls-files`.
#
# WHY A TRACKED SIDECAR IS WORSE THAN UNTIDY. The PostToolUse nudge reads a
# `.waiter-<prefix>` heartbeat to decide whether a session is listening for peer
# messages. A committed heartbeat tells every fresh clone that a waiter is
# already running when none is, so the nudge goes quiet and the session is
# silently deaf -- the exact failure the waiter was built to remove. A committed
# `.sessions` brief describes a session that no longer exists, and a committed
# `.requests` would replay other sessions' questions into a clone as if new.
#
# THE PATTERN LIST IS DERIVED, NOT COPIED. wl_store.py's module docstring is the
# single source for the sidecar family. Hard-coding the list here would let the
# two drift, and a gate that checks a stale list is the vacuity this repo keeps
# paying for. If that docstring is reworded so the list cannot be parsed, this
# gate FAILS rather than silently checking nothing.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
cd "$REPO_ROOT"

STORE="$REPO_ROOT/.claude/hooks/stop/wl_store.py"
HOOK_DIR=".claude/hooks/stop"

if [[ ! -f "$STORE" ]]; then
    echo "✗ $STORE not found -- cannot derive the sidecar list, so this gate" >&2
    echo "  would be checking nothing. That is a failure, not a pass." >&2
    exit 1
fi

# Parse the family out of the docstring: the parenthesised list after
# "The sidecars (" up to the closing paren, which may span several lines.
PATTERNS="$(
    python3 - "$STORE" <<'PY'
import re, sys
src = open(sys.argv[1], encoding="utf-8").read()
m = re.search(r"The sidecars \((.*?)\)", src, re.S)
if not m:
    sys.exit(0)
for tok in re.split(r"[,\s]+", m.group(1)):
    tok = tok.strip()
    if tok.startswith("."):
        print(tok)
PY
)"

if [[ -z "$PATTERNS" ]]; then
    echo "✗ could not parse the sidecar list out of wl_store.py's docstring." >&2
    echo "  The list is the single source for this gate; if it was reworded," >&2
    echo "  re-point this parser rather than deleting the check." >&2
    exit 1
fi

COUNT="$(wc -l <<<"$PATTERNS")"

# --- CONTROL -----------------------------------------------------------------
# Prove the detector can FIRE before trusting it to pass. A gate whose matcher
# is broken reports a clean tree exactly like a clean tree does, which is how a
# check that cannot fail survives for months. Feed it a synthetic tracked path
# that MUST match, and fail loudly if it does not.
control_hit=0
while read -r pat; do
    [[ -n "$pat" ]] || continue
    # shellcheck disable=SC2053  # glob match is the point
    if [[ "$HOOK_DIR/$pat" == $HOOK_DIR/$pat ]]; then control_hit=1; fi
done <<<"$PATTERNS"
if [[ "$control_hit" -ne 1 ]]; then
    echo "✗ CONTROL FAILED: the matcher did not match a path built from its own" >&2
    echo "  pattern list. The detector is broken; a clean result would be a lie." >&2
    exit 1
fi

# --- the real check ----------------------------------------------------------
TRACKED=""
while read -r pat; do
    [[ -n "$pat" ]] || continue
    # The exit status is load-bearing and MUST NOT be discarded. `2>/dev/null
    # || true` here would make a FAILED `git ls-files` -- no repo, a broken
    # index, a bad pathspec -- read exactly like "no sidecars are tracked", so
    # the gate would report a clean tree precisely when it could not look. That
    # is the vacuity this gate exists to prevent, and the swallowed-failure
    # scanner caught it in this very file on the first CI run.
    if ! hits="$(git ls-files -- "$HOOK_DIR/$pat" 2>&1)"; then
        echo "✗ git ls-files failed for pattern '$pat', so this gate cannot" >&2
        echo "  tell a clean tree from an unreadable one. Refusing to pass." >&2
        echo "  git said: $hits" >&2
        exit 1
    fi
    [[ -n "$hits" ]] && TRACKED+="$hits"$'\n'
done <<<"$PATTERNS"

TRACKED="$(grep -v '^$' <<<"${TRACKED:-}" || true)"

if [[ -n "$TRACKED" ]]; then
    echo "✗ RUNTIME SIDECAR(S) ARE TRACKED BY GIT:" >&2
    echo >&2
    sed 's/^/    /' >&2 <<<"$TRACKED"
    echo >&2
    echo "  These are per-session runtime state, not source. A tracked" >&2
    echo "  .waiter-* heartbeat tells a fresh clone a waiter is running when" >&2
    echo "  none is, so its session goes silently deaf to peer messages." >&2
    echo >&2
    echo "  Fix: git rm --cached <path>, and add the pattern to .gitignore." >&2
    echo "  Do not just delete the file -- it will be recreated on the next run." >&2
    exit 1
fi

echo "✓ no runtime sidecars tracked ($COUNT pattern(s) derived from wl_store.py)"
