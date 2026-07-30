#!/bin/bash
# Wall 4 mitigation (docs/ci-overhaul/03-v2-autonomy.md:112-138): on
# workflow_run the action's restoreConfigFromBase NEVER fires (it is gated on
# isEntityContext, and workflow_run is an automation event), while
# .claude/hooks/** still EXECUTE. A job that checks out PR head has therefore
# handed arbitrary PR-authored hook code a shell. This script closes that:
# snapshot the protected set from the trusted ref BEFORE any PR-head checkout,
# then restore it over the checkout and quarantine the branch's copies for
# inspection AS DATA, never as executable config.
#
# Usage:
#   restore-trusted-config.sh snapshot --checkout <dir> --snapshot <dir>
#   restore-trusted-config.sh restore  --checkout <dir> --snapshot <dir> --quarantine <dir>
#   restore-trusted-config.sh assert   --checkout <dir> --snapshot <dir>
#
# `assert` exits 1 with `trusted-config-drift` when any protected entry in the
# checkout differs from the snapshot. It is the control: run it WITHOUT
# restore against a tampered checkout and it must go red, or the restore step
# proves nothing.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/common.sh
source "$SCRIPT_DIR/../lib/common.sh"

# The set restore-config.ts protects on entity events (03-v2-autonomy.md:115).
PROTECTED=(.claude .mcp.json .claude.json .gitmodules .ripgreprc CLAUDE.md CLAUDE.local.md .husky)
MANIFEST=".protected-manifest"

cmd="${1:-}"
shift || true
parse_args "$@"
CHECKOUT="${ARG_CHECKOUT:-}"
SNAPSHOT="${ARG_SNAPSHOT:-}"
QUARANTINE="${ARG_QUARANTINE:-}"

[[ -n "$CHECKOUT" && -n "$SNAPSHOT" ]] || {
    log_error "usage: restore-trusted-config.sh snapshot|restore|assert --checkout <dir> --snapshot <dir> [--quarantine <dir>]"
    exit 2
}
require_dir "$CHECKOUT"

case "$cmd" in
    snapshot)
        mkdir -p "$SNAPSHOT"
        : >"$SNAPSHOT/$MANIFEST"
        for entry in "${PROTECTED[@]}"; do
            if [[ -e "$CHECKOUT/$entry" ]]; then
                cp -a "$CHECKOUT/$entry" "$SNAPSHOT/$entry"
                echo "$entry" >>"$SNAPSHOT/$MANIFEST"
            fi
        done
        log_info "snapshot: $(grep -c . "$SNAPSHOT/$MANIFEST" || true) protected entries captured to $SNAPSHOT"
        ;;
    restore)
        [[ -n "$QUARANTINE" ]] || {
            log_error "restore requires --quarantine"
            exit 2
        }
        # Fail closed: without a manifest there is no trusted baseline, and
        # restoring nothing while reporting success would be wall 4 reopened.
        [[ -f "$SNAPSHOT/$MANIFEST" ]] || {
            log_error "restore-trusted-config: snapshot manifest missing at $SNAPSHOT/$MANIFEST (fail closed: no trusted baseline, refusing to proceed)"
            exit 1
        }
        mkdir -p "$QUARANTINE"
        for entry in "${PROTECTED[@]}"; do
            if [[ -e "$CHECKOUT/$entry" ]]; then
                mv "$CHECKOUT/$entry" "$QUARANTINE/$entry"
            fi
        done
        while IFS= read -r entry; do
            [[ -z "$entry" ]] && continue
            cp -a "$SNAPSHOT/$entry" "$CHECKOUT/$entry"
        done <"$SNAPSHOT/$MANIFEST"
        log_info "restore: protected set overwritten from snapshot; branch copies quarantined in $QUARANTINE (inspect as data only)"
        ;;
    assert)
        [[ -f "$SNAPSHOT/$MANIFEST" ]] || {
            log_error "trusted-config-drift: snapshot manifest missing at $SNAPSHOT/$MANIFEST (nothing to assert against is itself a failure)"
            exit 1
        }
        drift=0
        for entry in "${PROTECTED[@]}"; do
            in_manifest=false
            grep -qxF "$entry" "$SNAPSHOT/$MANIFEST" && in_manifest=true
            if [[ "$in_manifest" == "true" ]]; then
                if ! diff -r "$SNAPSHOT/$entry" "$CHECKOUT/$entry" >/dev/null 2>&1; then
                    log_error "trusted-config-drift: '$entry' differs from the pre-checkout snapshot"
                    drift=1
                fi
            elif [[ -e "$CHECKOUT/$entry" ]]; then
                log_error "trusted-config-drift: '$entry' exists in the checkout but not in the snapshot (branch-introduced config)"
                drift=1
            fi
        done
        if ((drift != 0)); then
            log_error "assert: the checkout's protected set does not match the trusted snapshot; hooks from this tree must not run"
            exit 1
        fi
        log_info "assert: protected set matches the trusted snapshot"
        ;;
    *)
        log_error "unknown subcommand '${cmd}' (snapshot|restore|assert)"
        exit 2
        ;;
esac
