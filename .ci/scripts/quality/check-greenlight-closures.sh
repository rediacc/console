#!/bin/bash
# check:ci-greenlight-closures -- every path a greenlight closure names must exist
# on disk AND be tracked by git.
#
# WHY THIS EXISTS, and it is not the obvious reason. greenlight decides whether a
# previous green run still covers this one by hashing the CONTENTS of a declared
# closure of paths. It reads the candidate side out of the REMOTE commit, which
# `.ci/scripts/test/gates/test-greenlight.sh` models with `git ls-tree HEAD`.
#
# So a closure path that is present on disk but NOT COMMITTED resolves to nothing
# on the candidate side: greenlight throws its named refusal, emits no
# `run_<key>=false`, and gate-test:greenlight goes red -- with an error that
# blames the key, not the path. That is exactly what happened on 2026-09-02 when
# `.github/actions/bws-secrets` was added to eighteen closures before the action
# itself was committed, and it cost real time to diagnose because the symptom
# names the wrong thing. See TRAPS.md, trap-id uncommitted-file-reds-a-remote-fake.
#
# The same check catches the duller and more common cases: a typo in a closure
# path, and a path left behind after the file it names moved or was deleted. Both
# silently shrink what greenlight protects, because a path that resolves to
# nothing contributes nothing to the hash.
#
# WHAT IT DELIBERATELY DOES NOT ASSERT: presence in HEAD. Staged-but-uncommitted
# is still invisible to the candidate side, but demanding HEAD-presence would red
# on every new file in an uncommitted working tree -- the state this repo works in
# by standing order. Tracked is the strongest invariant that is true continuously.
#
# Exit 1 on any offender, 2 on setup error.

set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"
cd "$ROOT_DIR" || exit 2

if [[ "${CI:-}" == "true" ]]; then RED="" GREEN="" NC=""; else
    RED='\033[0;31m' GREEN='\033[0;32m' NC='\033[0m'; fi

# CONTROL FIRST. Both directions are planted against fixtures before the real
# tree is judged: a missing path and an untracked path must each be reported, and
# a clean pair must be silent. Without the silent case, a checker that reported
# everything would pass its own controls.
control() {
    local tmp; tmp="$(mktemp -d)"
    trap 'rm -rf "$tmp"' RETURN
    ( cd "$tmp" && git init -q . && echo tracked > tracked.txt && echo untracked > untracked.txt \
        && git add tracked.txt && git -c user.email=t@t -c user.name=t commit -qm x ) || return 1
    local out rc=0
    out="$(GL_CLOSURE_PATHS=$'tracked.txt\nuntracked.txt\nno-such-file.txt' \
           GL_ROOT="$tmp" bash "$0" --scan 2>&1)" || rc=$?
    [[ $rc -ne 0 ]] || { echo "CONTROL FAILED: a bad fixture passed"; return 1; }
    grep -q "no-such-file.txt" <<<"$out" || { echo "CONTROL FAILED: missing path unreported"; return 1; }
    grep -q "untracked.txt" <<<"$out"    || { echo "CONTROL FAILED: untracked path unreported"; return 1; }
    out="$(GL_CLOSURE_PATHS=$'tracked.txt' GL_ROOT="$tmp" bash "$0" --scan 2>&1)" || {
        echo "CONTROL FAILED: a clean fixture was reported"; return 1; }
    return 0
}

scan() {
    local root="${GL_ROOT:-$ROOT_DIR}" paths="${GL_CLOSURE_PATHS:-}"
    if [[ -z "$paths" ]]; then
        paths="$(node -e '
          const { CLOSURES } = require(process.argv[1]);
          const out = new Set();
          for (const c of Object.values(CLOSURES)) for (const p of c.paths || []) out.add(p);
          process.stdout.write([...out].sort().join("\n"));
        ' "$ROOT_DIR/.ci/scripts/ci/greenlight.cjs")" || return 2
    fi
    local n=0 bad=0 p
    while IFS= read -r p; do
        [[ -n "$p" ]] || continue
        n=$((n + 1))
        if [[ ! -e "$root/$p" ]]; then
            echo "  $p -- named by a closure but NOT ON DISK"; bad=$((bad + 1)); continue
        fi
        if ! git -C "$root" ls-files --error-unmatch -- "$p" >/dev/null 2>&1; then
            echo "  $p -- on disk but NOT TRACKED; the candidate side reads the remote"
            echo "      commit, so it resolves to nothing there and greenlight refuses"
            bad=$((bad + 1))
        fi
    done <<<"$paths"
    # A closure set that shrank to nothing must not read as success.
    [[ $n -gt 0 ]] || { echo "  no closure paths found -- this check is blind"; return 1; }
    [[ $bad -eq 0 ]] || return 1
    echo "$n"
    return 0
}

if [[ "${1:-}" == "--scan" ]]; then scan; exit $?; fi

if ! control; then
    echo -e "${RED}✗ instrument control failed; every verdict below would be meaningless${NC}" >&2
    exit 2
fi
out="$(scan)" || {
    echo -e "${RED}✗ greenlight closure paths (see above)${NC}" >&2
    echo "$out" >&2
    echo "  Fix: commit the file, correct the path, or drop it from the closure in" >&2
    echo "  .ci/scripts/ci/greenlight.cjs. A path that resolves to nothing silently" >&2
    echo "  shrinks what greenlight protects." >&2
    exit 1
}
echo -e "${GREEN}✓ greenlight closures: all $out declared path(s) exist and are tracked${NC}"
echo "  (controls: a missing path and an untracked path each reported, a clean pair silent)"
echo "  Residue, stated because it is NOT covered: TRACKED is not IN HEAD. A path that is"
echo "  staged but uncommitted still resolves to nothing on the candidate side, so"
echo "  gate-test:greenlight can be red while this passes. Asserting HEAD-presence instead"
echo "  would red on every new file in an uncommitted tree, which is this repo's normal"
echo "  state, and a gate that is always red gets switched off. See TRAPS.md,"
echo "  uncommitted-file-reds-a-remote-fake."
