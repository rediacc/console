#!/bin/bash
# Block until the per-PR preview Worker answers its health endpoint.
#
# Cloudflare propagates a new Worker version asynchronously, so the deploy step
# returning is not the same as the Worker serving. 30 attempts, 2s apart.
#
# Usage:
#   PR_NUMBER=123 .ci/scripts/deploy/wait-for-preview-worker.sh
#
# Required env:
#   PR_NUMBER   preview worker is named pr-<PR_NUMBER>

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

require_cmd curl
: "${PR_NUMBER:?PR_NUMBER is required}"

PREVIEW_URL="https://pr-${PR_NUMBER}.rediacc.workers.dev"

# READINESS MUST PROBE WHAT THE CALLER ACTUALLY NEEDS, not the cheapest
# endpoint that answers.
#
# This used to wait on /health alone and then declare the worker ready. Measured
# failure, run 30400413239: /health answered, this script printed "Preview
# worker is ready", and smoke-test-preview.ts immediately got HTTP 500 from
# /account/api/v1/.well-known/server-info, its very first real call. Probing the
# same URL by hand afterwards returned 200 with a valid key set, so the endpoint
# was merely still cold, not broken.
#
# The two endpoints do not have the same dependency footprint: /health is a
# trivial handler, while server-info has to produce the E2E key set. Waiting on
# the first proves nothing about the second, which is what made a green
# readiness gate hand a red job to the next step.
#
# So both must answer, and server-info must answer with a USABLE body: a 200
# carrying no keys would satisfy `curl -f` and fail the smoke test one line
# later, which is the same defect wearing a different status code.
# THE USABLE-BODY CHECK GREPPED FOR THE WRONG STRING AND PROVED NOTHING.
#
# It matched '"keys"', but private/account/src/app.ts:154-173 declares
# `const keys: {...}[] = []` and unconditionally returns
# `c.json({ e2e: { keys }, ... })`. So the literal `"keys"` is in the body even
# when X25519_PUBLIC_KEY is unset and the array is empty -- which is exactly the
# body the comment above says must be rejected. The gate passed on its own
# counterexample.
#
# `publicKeySpki` is only ever emitted from inside a populated entry
# (app.ts:158), so it is present if and only if at least one key exists. That is
# the property this wait is for.
#
# The health half was never wrong, and the 200-at-all improvement this script
# was written for still stands: it addresses the cold-start case from run
# 30400413239. Only the usable-body half was decorative.
ready() {
    curl -fsSL "${PREVIEW_URL}/account/api/v1/health" -o /dev/null 2>/dev/null || return 1
    curl -fsSL "${PREVIEW_URL}/account/api/v1/.well-known/server-info" 2>/dev/null |
        grep -q '"publicKeySpki"' || return 1
}

for i in $(seq 1 30); do
    if ready; then
        log_info "Preview worker is ready (health + server-info both serving)"
        exit 0
    fi
    log_info "Waiting for preview worker... (attempt $i/30)"
    sleep 2
done

log_error "Preview worker did not become ready"
exit 1
