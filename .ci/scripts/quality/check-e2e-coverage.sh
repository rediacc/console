#!/bin/bash
# Check that renet functions and e2e-tests agree in BOTH directions.
#
# This gate has two halves:
#
#   FORWARD (is every shipped renet function exercised by a suite CI RUNS?):
#     delegated to scripts/check-e2e-coverage.ts. Bash cannot honestly parse a
#     playwright config to learn which files a job selects, so the forward pass
#     is TypeScript: it imports each LIVE config, expands its projects into the
#     concrete test files, and only counts coverage from those. A verb mentioned
#     only in a dark suite or a declared-but-uncalled harness method no longer
#     counts — that dead-coverage is the failure mode the rewrite closes. The
#     forward allowlist lives in .e2e-coverage-allowlist (BLOCKER-gated).
#
#   REVERSE (does a test dispatch a verb renet no longer registers?):
#     Phase 3 below, unchanged. It scans ALL e2e sources — dark files included —
#     because a dead file calling a deleted verb is still a rot signal, and the
#     oracle here is RENET_BRIDGE_FUNCTIONS (the dispatcher's full registry),
#     which the forward TypeScript half deliberately does not use.
#
# Usage:
#   .ci/scripts/quality/check-e2e-coverage.sh
#
# Exit codes:
#   0 - Forward coverage complete AND no dispatched verb is missing from renet
#   1 - A function is uncovered (forward), OR a test dispatches a dead verb
#       (reverse), OR the live-config registry drifted from the workflows

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/common.sh
source "$SCRIPT_DIR/../lib/common.sh"

REPO_ROOT="$(get_repo_root)"

FUNCTIONS_FILE="$REPO_ROOT/packages/shared/src/renet-contract/data/functions.generated.ts"
E2E_TESTS_DIR="$REPO_ROOT/packages/e2e-tests"

# Validate required files exist
if [[ ! -f "$FUNCTIONS_FILE" ]]; then
    log_error "Functions file not found: $FUNCTIONS_FILE"
    exit 1
fi

if [[ ! -d "$E2E_TESTS_DIR" ]]; then
    log_error "e2e-tests directory not found: $E2E_TESTS_DIR"
    exit 1
fi

# ── FORWARD half (phases 1-2 + report): live-config membership, in TypeScript ──
FORWARD_RC=0
(cd "$REPO_ROOT" && npx tsx scripts/check-e2e-coverage.ts) || FORWARD_RC=$?

# Phase 3: THE REVERSE DIRECTION — does e2e dispatch a verb that no longer EXISTS?
#
# The forward half walks live -> e2e: "is every renet function exercised?" That is only
# half the contract, and the missing half is the one that bites. An e2e test calling a
# DELETED verb passed the old gate in total silence — which is exactly how
# datastore_init/mount/unmount, datastore_ceph_{init,fork,unfork} and kube_csi_template
# outlived their own removal in P1 and only surfaced when the Tests + Infra tier finally
# ran (it is gated behind the upstream gates, so it had not executed once all campaign).
#
# The oracle is RENET_BRIDGE_FUNCTIONS: every name in the dispatcher's Registry —
# internal verbs included. RENET_FUNCTIONS (the forward half's subject) is the PUBLIC
# surface and omits them, and the bridge drives mostly internal verbs (datastore_*,
# machine_check_*, daemon_*), so it cannot answer this question. A schema-derived list
# cannot either: a verb may be registered WITHOUT a schema (ceph_clone_create is) and
# still dispatch fine. This half stays in bash and stays scanning ALL files.
log_step "Checking e2e-tests dispatch only verbs that still exist..."

BRIDGE_FUNCTIONS=()
IN_ARRAY=false
while IFS= read -r line; do
    if [[ "$line" =~ RENET_BRIDGE_FUNCTIONS[[:space:]]*=[[:space:]]*\[ ]]; then
        IN_ARRAY=true
        continue
    fi
    if $IN_ARRAY && [[ "$line" =~ \][[:space:]]*as[[:space:]]+const ]]; then
        break
    fi
    if $IN_ARRAY && [[ "$line" =~ \'([a-z0-9_]+)\' ]]; then
        BRIDGE_FUNCTIONS+=("${BASH_REMATCH[1]}")
    fi
done <"$FUNCTIONS_FILE"

if [[ ${#BRIDGE_FUNCTIONS[@]} -eq 0 ]]; then
    log_error "No functions extracted from RENET_BRIDGE_FUNCTIONS — parsing may be broken,"
    log_error "or the contract predates it. Regenerate:"
    log_error "  private/renet/bin/renet functions generate-types --output packages/shared/src/renet-contract/data --version dev"
    exit 1
fi
log_info "Found ${#BRIDGE_FUNCTIONS[@]} dispatchable verbs in RENET_BRIDGE_FUNCTIONS"

is_dispatchable() {
    local needle="$1"
    local item
    for item in "${BRIDGE_FUNCTIONS[@]}"; do
        [[ "$item" == "$needle" ]] && return 0
    done
    return 1
}

# Every `function: 'name'` literal in the harness IS a dispatch — that is how
# src/utils/bridge/methods/*.ts name the verb they send to `functions once`.
DEAD=()
while IFS= read -r hit; do
    # grep -rn gives  <file>:<line>:<match>
    file="${hit%%:*}"
    rest="${hit#*:}"
    line="${rest%%:*}"
    verb="$(printf '%s' "$rest" | sed -E "s/.*function:[[:space:]]*'([a-z0-9_]+)'.*/\1/")"
    is_dispatchable "$verb" && continue
    DEAD+=("$verb  — ${file#"$REPO_ROOT"/}:$line")
done < <(grep -rn --include='*.ts' -E "function:[[:space:]]*'[a-z0-9_]+'" "$E2E_TESTS_DIR/src" "$E2E_TESTS_DIR/tests" 2>/dev/null || true)

# ★ THE SECOND WAY THE HARNESS DISPATCHES, and the gate could not see it.
#
# `function: 'name'` is how the METHOD classes name a verb. But a test can also shell the
# bridge out directly, as a raw command string:
#
#     sudo renet functions once --test-mode --function datastore_init --datastore-path ...
#
# That is the SAME dispatch through a different door, and the gate above is blind to it —
# which is exactly how the dual-group migrate suite kept calling the DELETED datastore_init
# and dying with "no command builder registered", while the coverage gate reported that every
# e2e-dispatched verb existed. A gate that checks one of two call sites is not a gate.
while IFS= read -r hit; do
    file="${hit%%:*}"
    rest="${hit#*:}"
    line="${rest%%:*}"
    code="${rest#*:}"
    # Skip COMMENTS. Both this gate's own explanation and OpsManager's name the dead verb
    # in prose ("the old `functions once --function datastore_init` path fails..."), and a
    # gate that reds on a comment about a bug is a gate people delete.
    case "$(printf '%s' "$code" | sed -E 's/^[[:space:]]*//')" in
        '//'* | '*'* | '/*'*) continue ;;
    esac
    verb="$(printf '%s' "$rest" | sed -E 's/.*--function[[:space:]]+([a-z0-9_]+).*/\1/')"
    is_dispatchable "$verb" && continue
    DEAD+=("$verb  — ${file#"$REPO_ROOT"/}:$line  (raw --function dispatch)")
done < <(grep -rn --include='*.ts' -E -- "--function[[:space:]]+[a-z0-9_]+" "$E2E_TESTS_DIR/src" "$E2E_TESTS_DIR/tests" 2>/dev/null || true)

REVERSE_RC=0
if [[ ${#DEAD[@]} -gt 0 ]]; then
    REVERSE_RC=1
    log_error "e2e-tests dispatch ${#DEAD[@]} verb(s) that renet no longer registers:"
    log_error ""
    for d in "${DEAD[@]}"; do
        log_error "  - $d"
    done
    log_error ""
    log_error "These calls fail at RUNTIME with \"no command builder registered\". A renamed"
    log_error "verb means the test is stale by design: fix it FORWARD against the surviving"
    log_error "surface (see RENET_BRIDGE_FUNCTIONS), never restore the old name."
else
    log_info "All e2e-dispatched verbs exist in the renet registry"
fi

# ── Combined verdict ──────────────────────────────────────────────────────────
if [[ $FORWARD_RC -ne 0 || $REVERSE_RC -ne 0 ]]; then
    exit 1
fi
exit 0
