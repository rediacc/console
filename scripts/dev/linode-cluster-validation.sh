#!/bin/bash
# Linode cross-DC cluster validation for the Ceph+Kubernetes campaign (wave L).
#
# Validates the wave-1 Linode VLAN cluster path against REAL Linode infra and
# proves a clean provision -> teardown lifecycle with zero surviving billable
# resources. Safe by default: nothing billable runs without --yes.
#
# Usage:
#   ./scripts/dev/linode-cluster-validation.sh [phase...] [--yes]
#
# Phases (default when none given: preflight plan):
#   preflight     Inspect orphaned tofu state + query the live Linode API for any
#                 running instances/volumes/VLANs. Exits non-zero if live billable
#                 instances exist (surface to the operator; never auto-destroy).
#   plan          Generate the cluster tf.json via the real CLI generator and run
#                 `terraform plan` (creates NOTHING = free) to validate the Linode
#                 VLAN schema against the live provider.
#   provision     [--yes] `rdc config cluster add` + `rdc cluster create`. BILLABLE.
#   verify        Assert zero survivors: `tofu state list` empty AND the Linode API
#                 shows no cluster-tagged instances/volumes/VLANs. Non-zero on any.
#   destroy       [--yes] `rdc cluster destroy --force` + verify + remove workdir.
#   idempotency   [--yes] bare provision -> destroy -> verify, proving a clean cycle.
#
# Config (env overrides):
#   CLUSTER_NAME     cluster + tofu-workdir name (default: lval)
#   CLUSTER_POOLS    `rdc config cluster add --pool` specs (default: a single
#                    2-node k8s pool of nanodes, the cheapest lifecycle proof)
#   PROVIDER         cloudProvider key in rediacc.json (default: my-linode)
#   NETWORK_CIDR     private VLAN CIDR (default: 10.0.0.0/24)
#
# Auth: the Linode API token is read from the PROVIDER entry in
# ~/.config/rediacc/rediacc.json (no env var needed). `rdc` == ./rdc.sh.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
RDC="$REPO_ROOT/rdc.sh"

CLUSTER_NAME="${CLUSTER_NAME:-lval}"
PROVIDER="${PROVIDER:-my-linode}"
NETWORK_CIDR="${NETWORK_CIDR:-10.0.0.0/24}"
# Cheapest lifecycle proof: one 2-node k8s pool of 1GB nanodes on the VLAN.
CLUSTER_POOLS="${CLUSTER_POOLS:-k8s:k8s-server:2:g6-nanode-1}"

CONFIG_JSON="$HOME/.config/rediacc/rediacc.json"
TOFU_DIR="$HOME/.config/rediacc/tofu/clusters/$CLUSTER_NAME"
YES=0

log() { printf '\033[1;36m[linode-val]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[linode-val WARN]\033[0m %s\n' "$*" >&2; }
err() { printf '\033[1;31m[linode-val ERROR]\033[0m %s\n' "$*" >&2; }

require_token() {
    TOKEN="$(python3 -c "
import json,sys
c=json.load(open('$CONFIG_JSON'))
t=c.get('resources',{}).get('cloudProviders',{}).get('$PROVIDER',{}).get('apiToken','')
sys.stdout.write(t)
")"
    if [ -z "${TOKEN:-}" ]; then
        err "No apiToken for provider '$PROVIDER' in $CONFIG_JSON"
        exit 1
    fi
}

# curl the Linode API; args: <path>. Prints the JSON body.
api() {
    curl -fsS -H "Authorization: Bearer $TOKEN" "https://api.linode.com/v4$1"
}

# Count + list live resources whose label starts with the cluster name.
# Sets LIVE_INSTANCES / LIVE_VOLUMES / LIVE_VLANS to the matching counts.
scan_live() {
    require_token
    local prefix="$1"
    LIVE_INSTANCES="$(api /linode/instances | python3 -c "
import json,sys
d=json.load(sys.stdin); n=0
for i in d.get('data',[]):
    if str(i.get('label','')).startswith('$prefix'):
        n+=1; print('  INSTANCE', i['id'], i['label'], i['status'], i['region'], i['type'], file=sys.stderr)
print(n)")"
    LIVE_VOLUMES="$(api /volumes | python3 -c "
import json,sys
d=json.load(sys.stdin); n=0
for v in d.get('data',[]):
    if str(v.get('label','')).startswith('$prefix'):
        n+=1; print('  VOLUME', v['id'], v['label'], v['status'], file=sys.stderr)
print(n)")"
    LIVE_VLANS="$(api /networking/vlans | python3 -c "
import json,sys
d=json.load(sys.stdin); n=0
for v in d.get('data',[]):
    if str(v.get('label','')).startswith('$prefix'):
        n+=1; print('  VLAN', v['label'], v['region'], v.get('linodes'), file=sys.stderr)
print(n)")"
}

phase_preflight() {
    log "Orphan preflight: inspecting tofu state + live Linode API"
    require_token
    for d in "$HOME/.config/rediacc/tofu/linode-1" "$HOME/.config/rediacc/tofu/linodeX" "$TOFU_DIR"; do
        [ -f "$d/terraform.tfstate" ] || continue
        log "tofu state in $d:"
        python3 -c "
import json
s=json.load(open('$d/terraform.tfstate'))
for r in s.get('resources',[]):
    for inst in r.get('instances',[]):
        a=inst.get('attributes',{})
        print('  ', r.get('type'), a.get('label'), 'id', a.get('id'), a.get('status'), a.get('region'))
"
    done
    # Live API is the authoritative check. Match campaign-related prefixes.
    local total=0
    for p in "$CLUSTER_NAME" rediacc linode lval; do
        scan_live "$p"
        total=$((total + LIVE_INSTANCES + LIVE_VOLUMES))
    done
    if [ "$total" -gt 0 ]; then
        err "LIVE billable resources exist on Linode (see stderr list above). Surface to operator; NOT auto-destroying."
        return 2
    fi
    log "Preflight CLEAN: no live billable instances/volumes matching campaign prefixes."
}

# Generate the cluster tf.json via the REAL CLI generator, then terraform plan.
phase_plan() {
    log "Dry-run: generating tf.json via the real generator + terraform plan (free)"
    require_token
    local work
    work="$(mktemp -d)"
    local harness="$work/gen.mts"
    cat >"$harness" <<EOF
import { readFileSync, mkdirSync, writeFileSync } from 'node:fs';
import { homedir } from 'node:os';
import { join } from 'node:path';
import { resolveProviderMapping } from '$REPO_ROOT/packages/cli/src/services/tofu/provider-resolver.ts';
import { generateClusterTfJson } from '$REPO_ROOT/packages/cli/src/services/tofu/cluster-tf-generator.ts';
const cfg = JSON.parse(readFileSync(join(homedir(), '.config/rediacc/rediacc.json'), 'utf-8'));
const pc = cfg.resources.cloudProviders['$PROVIDER'];
const pools = '$CLUSTER_POOLS'.split(',').map((s) => {
  const [name, role, count, size] = s.split(':');
  return { name, role, count: Number(count), ...(size ? { size } : {}) };
});
const tf = generateClusterTfJson({
  clusterName: '$CLUSTER_NAME',
  mapping: resolveProviderMapping(pc),
  apiToken: pc.apiToken,
  sshPublicKey: readFileSync(join(homedir(), '.ssh/id_ed25519.pub'), 'utf-8').trim(),
  network: { primitive: 'vlan', cidr: '$NETWORK_CIDR', mtu: 1500 },
  pools,
});
mkdirSync('$work', { recursive: true });
writeFileSync(join('$work', 'main.tf.json'), JSON.stringify(tf, null, 2));
EOF
    (cd "$REPO_ROOT" && npx tsx "$harness")
    (cd "$work" && terraform init -input=false >/dev/null && terraform plan -input=false -no-color)
    log "Plan complete (nothing created). Review the '+ N to add' summary above."
    rm -rf "$work"
}

require_yes() {
    if [ "$YES" -ne 1 ]; then
        err "'$1' is BILLABLE and needs --yes. Refusing without it."
        exit 3
    fi
}

phase_provision() {
    require_yes provision
    log "Provisioning cluster '$CLUSTER_NAME' ($CLUSTER_POOLS) on $PROVIDER — BILLABLE"
    local pool_args=()
    local IFS=','
    for spec in $CLUSTER_POOLS; do pool_args+=(--pool "$spec"); done
    unset IFS
    "$RDC" config cluster add --name "$CLUSTER_NAME" --provider "$PROVIDER" \
        --network-cidr "$NETWORK_CIDR" --network-primitive vlan "${pool_args[@]}" || true
    "$RDC" cluster create --name "$CLUSTER_NAME"
}

phase_verify() {
    log "Verifying ZERO survivors for cluster '$CLUSTER_NAME'"
    local survivors=0
    if [ -f "$TOFU_DIR/terraform.tfstate" ]; then
        local n
        n="$(cd "$TOFU_DIR" && terraform state list 2>/dev/null | wc -l | tr -d ' ')"
        if [ "$n" != "0" ]; then
            err "tofu state still lists $n resource(s) in $TOFU_DIR"
            survivors=$((survivors + n))
        fi
    fi
    scan_live "$CLUSTER_NAME"
    if [ "$LIVE_INSTANCES" != "0" ] || [ "$LIVE_VOLUMES" != "0" ] || [ "$LIVE_VLANS" != "0" ]; then
        err "Linode API survivors: instances=$LIVE_INSTANCES volumes=$LIVE_VOLUMES vlans=$LIVE_VLANS"
        survivors=$((survivors + LIVE_INSTANCES + LIVE_VOLUMES + LIVE_VLANS))
    fi
    if [ "$survivors" -ne 0 ]; then
        err "ZERO-SURVIVOR CHECK FAILED ($survivors survivor(s))."
        return 4
    fi
    log "ZERO survivors confirmed (tofu state empty AND Linode API clean)."
}

phase_destroy() {
    require_yes destroy
    log "Destroying cluster '$CLUSTER_NAME'"
    "$RDC" cluster destroy --name "$CLUSTER_NAME" --force || warn "destroy returned non-zero; verifying anyway"
    phase_verify
    rm -rf "$TOFU_DIR"
    log "Per-cluster tofu workdir removed: $TOFU_DIR"
}

phase_idempotency() {
    require_yes idempotency
    log "Idempotency loop: bare provision -> destroy -> verify"
    phase_provision
    phase_destroy
    log "Idempotency loop complete: clean create/destroy with zero orphans."
}

main() {
    local phases=()
    for arg in "$@"; do
        case "$arg" in
            --yes) YES=1 ;;
            preflight | plan | provision | verify | destroy | idempotency) phases+=("$arg") ;;
            -h | --help)
                sed -n '2,40p' "${BASH_SOURCE[0]}"
                exit 0
                ;;
            *)
                err "Unknown argument: $arg"
                exit 1
                ;;
        esac
    done
    if [ "${#phases[@]}" -eq 0 ]; then
        phases=(preflight plan)
    fi
    for p in "${phases[@]}"; do
        "phase_$p"
    done
    log "Done: ${phases[*]}"
}

main "$@"
