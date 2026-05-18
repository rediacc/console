#!/bin/bash
# Validate .npmrc supply-chain hardening.
# Usage: check-npmrc.sh
#
# Enforces both directions:
#   Forbidden  -- settings that hide dependency problems
#       legacy-peer-deps : silently ignores peer dependency conflicts
#       force            : forces installation despite errors
#   Required   -- supply-chain defenses (see /workspace/console/.npmrc for rationale)
#       ignore-scripts=true           : blocks dependency lifecycle scripts
#       allow-git=none                : rejects git+/github:/tarball deps (PackageGate)
#       minimum-release-age=1440      : 24h cooldown (Axios-style smash-and-grab)
#
# Example:
#   .ci/scripts/quality/check-npmrc.sh

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

cd "$(get_repo_root)"

log_step "Checking .npmrc for supply-chain hardening settings..."

if [[ ! -f .npmrc ]]; then
    log_error ".npmrc is missing"
    log_error "Supply-chain hardening requires .npmrc at the repo root with:"
    log_error "  ignore-scripts=true"
    log_error "  allow-git=none"
    log_error "  minimum-release-age=1440"
    exit 1
fi

# Forbidden settings.
if grep -qiE "^[[:space:]]*(legacy-peer-deps|force)[[:space:]]*=" .npmrc; then
    log_error ".npmrc contains legacy-peer-deps or force=true"
    log_error "These settings hide dependency problems that should be fixed properly."
    echo ""
    echo "Problematic lines:"
    grep -niE "^[[:space:]]*(legacy-peer-deps|force)[[:space:]]*=" .npmrc || true
    exit 1
fi

# Required settings -- exact value match.
declare -A required=(
    ["ignore-scripts"]=true
    ["allow-git"]=none
    ["minimum-release-age"]=1440
)

missing=0
for key in "${!required[@]}"; do
    expected="${required[$key]}"
    actual="$(grep -E "^[[:space:]]*${key}[[:space:]]*=" .npmrc | tail -n1 | sed -E "s/^[[:space:]]*${key}[[:space:]]*=[[:space:]]*//" | tr -d '[:space:]' || true)"
    if [[ -z "$actual" ]]; then
        log_error ".npmrc is missing required setting: ${key}=${expected}"
        missing=1
    elif [[ "$actual" != "$expected" ]]; then
        log_error ".npmrc has ${key}=${actual}, expected ${key}=${expected}"
        missing=1
    fi
done

if [[ "$missing" -ne 0 ]]; then
    echo ""
    echo "See /workspace/console/.npmrc header for the rationale behind each setting."
    exit 1
fi

log_info ".npmrc is clean and hardened"
