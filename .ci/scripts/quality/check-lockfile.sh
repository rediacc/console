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
#   B. RESOLVABILITY (`npm ci --dry-run`), under BOTH npm majors in play. npm 11 PRUNES
#      nested platform entries that npm 10 requires, so a lockfile can be readable by one
#      and not the other. This check IS that command, so it cannot be fooled by the shape
#      of a diff. A net-negative-diff or deletion-rejection heuristic would miss the
#      realistic case: `check-deps --upgrade` under npm 11 ADDS entries while pruning
#      platform ones, giving a mixed, net-POSITIVE diff, and would then make the lockfile
#      LOOK watched while the prune shipped anyway. That is worse than no gate, because it
#      retires the human vigilance that has actually been catching this.
#
#      WHY TWO NPMs, since 2026-09-06 (issue #587). These are two different questions and
#      collapsing them to one loses a real answer:
#
#        CANONICAL_NPM (npm 11) is the form the committed lockfiles are WRITTEN in. The
#          operator ruled migrate-not-revert after `main` landed an npm-11 lockfile: the
#          repo had been documenting npm 10 as canonical while carrying npm 11's output,
#          so every session that read CLAUDE.md "fixed" it back and the 27-line `"dev":
#          true` flip oscillated forever. Naming one writer ends the oscillation.
#
#        CI_NPM (npm 10) is the npm that still has to INSTALL it. setup-node with Node 22
#          bundles npm 10.x, and no workflow overrides it (checked 2026-09-06: every
#          `.github/workflows/*` pins `node-version: '22'` and nothing pins npm). Dropping
#          this half when the canonical writer moved would have stopped proving the thing
#          the gate was built for (CI's own `npm ci`) while still printing a tick. That
#          is precisely the overstated-coverage disease this file's ★ note warns about.
#
#      Measured 2026-09-06: all 11 lockfiles resolve clean under BOTH, which is what makes
#      keeping both affordable. When CI's bundled npm eventually reaches 11, CI_NPM folds
#      into CANONICAL_NPM and this becomes one check again.
#
#   ★ HONEST LIMIT: `--dry-run` does NOT run the reify peer check. A lockfile can pass this
#     gate and still fail a REAL cold-cache `npm ci` with ERESOLVE — exactly what happened
#     in round 9 of the 0707 campaign (wrangler/workers-types peer). So this gate proves
#     "both pinned npms can RESOLVE this lockfile", NOT "either can install it". A gate whose name
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

# The npm whose OUTPUT FORM is canonical for every committed lockfile (issue #587).
# CLAUDE.md's "27-line package-lock.json flip" section is the prose half of this pin; the
# two must be changed together or the repo goes back to arguing with itself.
CANONICAL_NPM="npm@11"

# The npm CI actually runs. Keep in step with setup-node's bundled npm (Node 22 -> npm 10);
# the exact version is printed in every job's "Environment details". This is NOT the
# canonical writer any more, but it is still the installer, so it still gets a vote.
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

    # Both majors, and the loop is written once so neither can be dropped by
    # editing only the other. `role` is what the failure message needs to say:
    # the two have DIFFERENT fixes, and telling someone to reconcile with the
    # wrong npm is how the flip oscillated in the first place.
    resolve_failed=""
    for probe in "$CANONICAL_NPM:canonical writer" "$CI_NPM:CI's installer"; do
        npm_pin="${probe%%:*}"
        role="${probe#*:}"
        log_step "[$lock] resolvable by $npm_pin ($role)..."
        if ! (cd "$dir" && npx -y "$npm_pin" ci --dry-run --ignore-scripts >/dev/null 2>&1); then
            log_error "[$lock] $npm_pin CANNOT RESOLVE this lockfile."
            echo ""
            if [[ "$npm_pin" == "$CI_NPM" ]]; then
                echo "  This is the failure CI hits: npm 11 removes nested platform entries"
                echo "  (e.g. vitest's @esbuild/*) that npm 10 requires, so an npm-11 write can"
                echo "  leave a lockfile CI cannot install even though it is the canonical form."
                echo "  Reconciling with $CANONICAL_NPM is the FIRST thing to try, because the"
                echo "  canonical form is supposed to satisfy both; if it cannot, the dependency"
                echo "  itself needs looking at, not the lockfile."
            else
                echo "  The canonical writer cannot read this lockfile, so it was almost"
                echo "  certainly written by something else. Rewrite it with the canonical npm:"
            fi
            echo ""
            echo "    cd $dir && npx -y $CANONICAL_NPM install --package-lock-only --ignore-scripts"
            echo ""
            echo "  The failure, in full:"
            (cd "$dir" && npx -y "$npm_pin" ci --dry-run --ignore-scripts 2>&1 | head -25 | sed 's/^/    /') || true
            FAILED+=("$lock ($npm_pin cannot resolve)")
            resolve_failed=1
            break
        fi
    done
    [[ -n "$resolve_failed" ]] && continue

    log_info "[$lock] OK"
done

if [[ ${#SKIPPED[@]} -gt 0 ]]; then
    log_warn "Skipped ${#SKIPPED[@]} lockfile(s) whose package.json is absent: ${SKIPPED[*]}"
fi

if [[ ${#FAILED[@]} -gt 0 ]]; then
    log_error "Lockfile check FAILED for: ${FAILED[*]}"
    exit 1
fi

log_info "All ${#LOCKFILES[@]} lockfile(s): supply-chain clean and resolvable by BOTH $CANONICAL_NPM (canonical form) and $CI_NPM (CI's installer)"
log_warn "Note the limit: --dry-run does NOT run the reify peer check. This proves npm 10 can RESOLVE these lockfiles, not that it can install them (round-9 ERESOLVE, see docs/agent-reference/ci-gates.md)."
