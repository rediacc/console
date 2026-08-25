#!/bin/bash
# devbox_docker CAN ANSWER TWO WORDS, and every consumer must treat it that way.
#
# WHAT WENT WRONG, measured 2026-08-26:
#
#   .ci/lib/devbox.sh: line 606: sudo docker: command not found
#
# `devbox_docker` returns plain `docker` when the caller's shell already has the
# docker group, and the TWO-WORD string `sudo docker` when it does not
# (.ci/lib/devbox.sh:58-63). Sixteen call sites relied on word-splitting an
# UNQUOTED $d and were fine. One -- devbox_exec, the function the whole gate
# lane routes through -- wrote `"$d" "${flags[@]}"`, quoting two words as a
# single command name. Every routed gate therefore died on any machine where
# docker needs sudo, which is the default on a fresh Linux host.
#
# WHY NO EXISTING GATE SAW IT, and why this one is static rather than a runtime
# test. The bug is invisible to every environment CI actually has: runners and
# containers already grant docker without sudo, so the failing branch is never
# taken. A runtime test would have to manufacture a sudo-requiring docker, which
# is neither portable nor honest. But the defect is fully visible in the SOURCE
# -- a quoted expansion where word-splitting is required -- so per
# .claude/skills/testing that routes to a static gate. This is the "could the
# defect be seen without running the product?" question, and the answer is yes.
#
# B2 exists because fixing B1 surfaced a sibling: devbox_shell was still passing
# the numeric `-u $(id -u):$(id -g)` into the container. devbox-entrypoint.sh
# renumbers `vscode` to the host identity, so the NAME is correct on Linux,
# macOS (501:20, where gid 20 is dialout) and WSL2, while a numeric id is
# correct only where the host's numbering means something inside the container.
# Exec as the wrong identity and git refuses the worktree with "dubious
# ownership", `git ls-files` returns empty, and a gate reports green over zero
# files -- the vacuity failure this whole wave exists to prevent.
#
# WHAT THIS GATE CANNOT SEE: it reasons about devbox.sh's own call sites. A new
# file elsewhere that shells out to `sudo docker` on its own is out of scope.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
DEVBOX="$ROOT/.ci/lib/devbox.sh"

RED=$'\033[0;31m'
GREEN=$'\033[0;32m'
NC=$'\033[0m'
fails=0
pass() { echo "  ok   $*"; }
fail() {
    echo "  ${RED}FAIL${NC} $*"
    fails=$((fails + 1))
}

[[ -f "$DEVBOX" ]] || {
    echo "${RED}✗${NC} subject under test is missing: $DEVBOX"
    exit 1
}

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# code_of -- whole-line comments stripped. Every explanation of the WRONG shape
# in this repo lives in a comment, so a scan for that shape must read code only
# or it fails on its own documentation. (Learned the hard way by the editorconfig
# gate, which matched `binary` inside a PATH.)
code_of() { grep -vE '^[[:space:]]*#' "$1"; }

# The bug shape: a variable holding devbox_docker's answer, expanded QUOTED in
# command position. `"$d" ` / `"${d}" ` at the start of a command.
BUG_RE='(^|[;&|(]|then |else |do )[[:space:]]*"\$\{?d\}?"[[:space:]]'

# --- B1. devbox_docker's answer is never invoked as one quoted word ----------
hits="$(code_of "$DEVBOX" | grep -nE "$BUG_RE" || true)"
if [[ -z "$hits" ]]; then
    pass "B1. no call site quotes devbox_docker's two-word answer as one command"
else
    fail "B1. these invoke a possibly-two-word docker as a single command:"
    echo "$hits" | sed 's/^/         /'
fi

# Anti-vacuity: B1 is a scan, and a scan over nothing passes. Prove the
# enumeration actually found the call sites it is supposed to be judging.
sites="$(code_of "$DEVBOX" | grep -cE '\$\{?d\}?[[:space:]]' || true)"
if [[ "$sites" -ge 10 ]]; then
    pass "B1 anti-vacuity: $sites docker invocation(s) actually scanned"
else
    fail "B1 SCANNED ALMOST NOTHING ($sites sites) -- the enumeration broke, not the code"
fi

# --- B2. nothing execs into the devbox under a numeric identity --------------
numeric="$(code_of "$DEVBOX" | grep -nE '\-u[[:space:]]+"?\$\(id -u\)' || true)"
if [[ -z "$numeric" ]]; then
    pass "B2. container exec uses -u vscode by name, never a numeric id"
else
    fail "B2. numeric -u would break on macOS/WSL2 and can yield a vacuous green:"
    echo "$numeric" | sed 's/^/         /'
fi

# --- controls, by CONSTRUCTION -----------------------------------------------
# Built by concatenation, never by substituting into a copy of the real file: a
# substitution silently yields an identical copy when the targeted line is later
# reworded, and the control then passes against unmutated source.
{
    printf '#!/bin/bash\n'
    printf 'd="$(devbox_docker)"\n'
    printf '"$d" exec -u vscode "$cid" bash -lc "$*"\n'
} >"$TMP/bad.sh"
if code_of "$TMP/bad.sh" | grep -qE "$BUG_RE"; then
    pass "B1 control: a quoted two-word invocation is detected"
else
    fail "B1 CONTROL DID NOT FIRE: the planted defect went undetected"
fi

{
    printf '#!/bin/bash\n'
    printf 'd="$(devbox_docker)"\n'
    printf '$d exec -u vscode "$cid" bash\n'
    printf 'local -a dk; read -r -a dk <<<"$d"\n'
    printf '"${dk[@]}" exec "$cid" bash\n'
} >"$TMP/good.sh"
if code_of "$TMP/good.sh" | grep -qE "$BUG_RE"; then
    fail "B1 IS OVER-BROAD: correct word-splitting and array forms were flagged"
else
    pass "B1 control: unquoted and array forms are not flagged"
fi

{
    printf '#!/bin/bash\n'
    printf '$d exec -it -u "$(id -u):$(id -g)" -w "$w" "$cid" bash\n'
} >"$TMP/numeric.sh"
if code_of "$TMP/numeric.sh" | grep -qE '\-u[[:space:]]+"?\$\(id -u\)'; then
    pass "B2 control: a numeric container identity is detected"
else
    fail "B2 CONTROL DID NOT FIRE: a numeric -u went undetected"
fi

{
    printf '#!/bin/bash\n'
    printf '# $d exec -u "$(id -u)" -- the wrong shape, explained in a comment\n'
} >"$TMP/comment.sh"
if code_of "$TMP/comment.sh" | grep -qE '\-u[[:space:]]+"?\$\(id -u\)'; then
    fail "B2 IS OVER-BROAD: prose describing the wrong shape was flagged as code"
else
    pass "B2 control: a comment describing the bad shape is not flagged"
fi

echo
if [[ "$fails" -eq 0 ]]; then
    echo "${GREEN}✓${NC} devbox exec: $sites docker invocation(s), none mis-quoted."
    echo "  Blind spot: scoped to .ci/lib/devbox.sh's own call sites; a new file"
    echo "  that shells out to docker independently is not covered."
    exit 0
fi
echo "${RED}✗${NC} devbox exec: $fails failure(s)."
exit 1
