#!/usr/bin/env bash
# A CALLER MAY NOT HAND cleanup-staging.sh A TAG IT WILL REFUSE.
#
# WHY THIS EXISTS. cleanup-staging.sh deletes GHCR tags and guards itself with
# `[[ "$TAG" =~ ^staging- ]] || exit 1` -- deliberately, so a stray call cannot
# delete a real published tag. On 2026-09-06 cleanup-channel-docker-tags.sh was
# found calling it with CHANNEL (`edge`/`stable`), which the guard rejects EVERY
# TIME. It had done so on every release since it was written, and the step summary
# blamed a missing `delete:packages` scope -- sending readers to fix a token when
# the wrong tool was being called.
#
# The tempting "fix" is to widen the guard. That would remove the safety rail and
# is exactly what this gate is here to prevent. The other tempting fix is to drop
# the caller's own pre-check and try the call again, which restores the wrong
# diagnosis. Both are caught here.
#
# WHAT THIS DOES NOT DO, said plainly: it does not verify PROSE. "Headers describe
# behaviour correctly" is not mechanically checkable -- a gate over comments either
# cannot fail or fires on every paragraph. This checks the one thing that IS
# checkable and was the real defect: a call that cannot succeed.
set -uo pipefail
ROOT="${STAGING_GUARD_ROOT:-$(git rev-parse --show-toplevel 2>/dev/null || echo .)}"
TARGET="${STAGING_GUARD_TARGET:-$ROOT/.ci/scripts/docker/cleanup-staging.sh}"

# One copy of the tally, shared: check:ci-shape-duplication caught three.
source "$(dirname "${BASH_SOURCE[0]}")/../lib/gate-controls.sh"
_c() { gate_check "$@"; }

[[ -f "$TARGET" ]] || {
    echo "✗ $TARGET not found -- nothing was verified" >&2
    exit 1
}

# The safety rail itself. If this goes, every assertion below is meaningless.
_c "cleanup-staging.sh still refuses a non-staging tag" \
    "$(grep -cE '\^staging-' "$TARGET")" "1"

# Every EXECUTING call site (a `run:`-style invocation, not a mention in prose).
call_files=""
n_calls=0
while IFS= read -r hit; do
    f="${hit%%:*}"
    [[ "$f" == "$TARGET" ]] && continue
    n_calls=$((n_calls + 1))
    case " $call_files " in *" $f "*) ;; *) call_files="$call_files $f" ;; esac
done < <(grep -rn 'cleanup-staging\.sh' "$ROOT/.ci" "$ROOT/.github" --include='*.sh' --include='*.yml' 2>/dev/null |
    grep -vE ':[0-9]+:[[:space:]]*#' | grep -E 'cleanup-staging\.sh["'"'"']?[[:space:]]+(--tag|"\$)' || true)

# ANTI-VACUITY. A rename or a moved tree would find zero call sites and this gate
# would pass having checked nothing at all.
_c "at least one executing call site was found" "$((n_calls >= 1 ? 1 : 0))" "1"
if ((n_calls < 1)); then
    echo "✗ VACUOUS: no executing call site of cleanup-staging.sh found under .ci or .github." >&2
    echo "  Either it is genuinely unused, or this scan broke. Check before trusting the tick." >&2
    exit 1
fi

# Each caller must prove it cannot pass a tag the guard rejects: either it passes a
# literal `staging-` value, or it tests for the prefix itself before calling.
for f in $call_files; do
    rel="${f#"$ROOT"/}"
    guarded=0
    grep -qE '\^staging-|--tag[[:space:]]+["'"'"']?staging-' "$f" && guarded=1
    _c "$rel guards its call against a non-staging tag" "$guarded" "1"
done

if ! gate_finish 3 "staging tag guard ($n_calls call site(s))"; then
    echo "  A caller that passes a non-staging tag can NEVER succeed, and the failure" >&2
    echo "  reads as a token-scope problem. Guard the call; do not widen the rail." >&2
    exit 1
fi
