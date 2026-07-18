#!/bin/bash
# Validate EVERY package-lock.json in the tree, on two independent properties.
#
# ── Why this gate was rewritten ───────────────────────────────────────────────
#
# It used to run lockfile-lint on `package-lock.json` — the ROOT one, and only that
# one. Two consequences, both bad:
#
#   1. The repo has NINE lockfiles (root, private/account{,/web,/e2e}, workers/{account,
#      mta-sts,www}, private/growth/*). All FOUR npm-11 pruning incidents happened in
#      private/account* — a file this gate had never opened. It was green through every
#      one of them.
#   2. The other eight were not supply-chain-validated AT ALL. A non-https or tampered
#      resolved URL in any of them sailed straight through.
#
# And what it validated (--validate-https, --allowed-hosts, --validate-package-names,
# --validate-integrity) says NOTHING about whether npm can install the result. The name
# promised "lockfile"; the check delivered "the root lockfile has no malicious URLs".
#
# ── What this gate proves, and what it does NOT ───────────────────────────────
#
# TWO properties, per lockfile:
#
#   A. SUPPLY CHAIN (lockfile-lint). Unchanged, still valuable, now applied to all of them.
#
#   B. RESOLVABILITY (`npm@10 ci --dry-run`). npm 11 PRUNES nested platform entries that
#      npm 10 requires. CI runs npm 10 (setup-node/Node 22), so a lockfile touched by a
#      local npm 11 fails `npm ci` in CI with `EUSAGE: Missing: <pkg> from lock file`.
#      This check IS that command, so it cannot be fooled by the shape of a diff. A
#      net-negative-diff or deletion-rejection heuristic would miss the realistic case —
#      `check-deps --upgrade` under npm 11 ADDS entries while pruning platform ones, giving
#      a mixed, net-POSITIVE diff — and would then make the lockfile LOOK watched while the
#      prune shipped anyway. That is worse than no gate, because it retires the human
#      vigilance that has actually been catching this.
#
#   ★ HONEST LIMIT: `--dry-run` does NOT run the reify peer check. A lockfile can pass this
#     gate and still fail a REAL cold-cache `npm ci` with ERESOLVE — exactly what happened
#     in round 9 of the 0707 campaign (wrangler/workers-types peer). So this gate proves
#     "npm 10 can RESOLVE this lockfile", NOT "npm 10 can install it". A gate whose name
#     overstates its coverage is the disease being cured here; the cure must not reintroduce
#     it. For a real install check, use CLAUDE.md's clean-room recipe.
#
# Run via: npm run check:ci-lockfile

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/common.sh
source "$SCRIPT_DIR/../lib/common.sh"

REPO_ROOT="$(get_repo_root)"
cd "$REPO_ROOT"

# The npm CI actually runs. Keep in step with setup-node's bundled npm (Node 22 -> npm 10);
# the exact version is printed in every job's "Environment details".
CI_NPM="npm@10"

# Discovered, never hardcoded: a hardcoded list is how this gate went stale in the first
# place, and a lockfile added tomorrow must be covered without anyone remembering to add it.
#
# `while read`, not `mapfile`: mapfile/readarray are bash-4 builtins and are BANNED by
# .ci/scripts/security/check-commands.sh, which tracks what is actually available in the
# minimal CI images (and on macOS / Git Bash). This gate was written to catch npm-10-vs-11
# ENVIRONMENT DRIFT and was itself defeated by environment drift — it passed locally on
# bash 5 and failed in CI. The discovery stays; only the builtin goes.
LOCKFILES=()
while IFS= read -r lock; do
    LOCKFILES+=("$lock")
done < <(find . -name package-lock.json -not -path '*/node_modules/*' | sed 's|^\./||' | sort)

if [[ ${#LOCKFILES[@]} -eq 0 ]]; then
    log_error "No package-lock.json found anywhere. That cannot be right."
    exit 1
fi

FAILED=()
SKIPPED=()

for lock in "${LOCKFILES[@]}"; do
    dir="$(dirname "$lock")"

    # The quality-security job checks out WITHOUT submodules, so private/account* and
    # private/growth* legitimately do not exist there. Skip LOUDLY — a silent skip is how
    # test-embed-credits.sh went green while checking nothing (round 3, 0707 campaign).
    if [[ ! -f "$dir/package.json" ]]; then
        log_warn "SKIP $lock - no package.json beside it (submodule not checked out?)"
        SKIPPED+=("$lock")
        continue
    fi

    log_step "[$lock] supply chain (lockfile-lint)..."
    if ! npx --no-install lockfile-lint \
        --path "$lock" \
        --type npm \
        --validate-https \
        --allowed-hosts npm \
        --validate-package-names \
        --validate-integrity; then
        log_error "[$lock] FAILED supply-chain validation"
        FAILED+=("$lock (supply chain)")
        continue
    fi

    log_step "[$lock] resolvable by CI's npm ($CI_NPM ci --dry-run)..."
    if ! (cd "$dir" && npx -y "$CI_NPM" ci --dry-run --ignore-scripts >/dev/null 2>&1); then
        log_error "[$lock] npm 10 CANNOT RESOLVE this lockfile."
        echo ""
        echo "  This is the failure CI hits, and it is almost always the npm-11 prune: npm 11"
        echo "  removes nested platform entries (e.g. vitest's @esbuild/*) that npm 10 requires,"
        echo "  so a local npm-11 install silently breaks the lockfile for CI."
        echo ""
        echo "  Reconcile with CI's own npm, then re-check:"
        echo "    cd $dir && npx -y $CI_NPM install --package-lock-only --ignore-scripts"
        echo ""
        echo "  The failure, in full:"
        (cd "$dir" && npx -y "$CI_NPM" ci --dry-run --ignore-scripts 2>&1 | head -25 | sed 's/^/    /') || true
        FAILED+=("$lock (npm 10 cannot resolve)")
        continue
    fi

    log_info "[$lock] OK"
done

if [[ ${#SKIPPED[@]} -gt 0 ]]; then
    log_warn "Skipped ${#SKIPPED[@]} lockfile(s) whose package.json is absent: ${SKIPPED[*]}"
fi

if [[ ${#FAILED[@]} -gt 0 ]]; then
    log_error "Lockfile check FAILED for: ${FAILED[*]}"
    exit 1
fi

log_info "All ${#LOCKFILES[@]} lockfile(s): supply-chain clean and resolvable by $CI_NPM"
log_warn "Note the limit: --dry-run does NOT run the reify peer check. This proves npm 10 can RESOLVE these lockfiles, not that it can install them (round-9 ERESOLVE, see CLAUDE.md)."
