#!/bin/bash
# Block until the per-PR preview Worker answers its health endpoint.
#
# Cloudflare propagates a new Worker version asynchronously, so the deploy step
# returning is not the same as the Worker serving.
#
# Usage:
#   PR_NUMBER=123 .ci/scripts/deploy/wait-for-preview-worker.sh
#
# Required env:
#   PR_NUMBER   preview worker is named pr-<PR_NUMBER>
#               (not required when PREVIEW_URL_OVERRIDE is set)
#
# Test-only env. CI sets NONE of these; the defaults below are the real policy.
# They exist so .ci/scripts/test/gates/test-preview-readiness.sh can drive this
# script against a local stub in seconds instead of copying it through sed --
# which is how it had to be tested before, and a script you must fork to test is
# a script that stops being tested.
#   PREVIEW_URL_OVERRIDE     probe this base URL instead of deriving one
#   REQUIRED_STREAK          consecutive good probes demanded (default 3)
#   MAX_ATTEMPTS             probe budget (default 60)
#   PROBE_INTERVAL_SECONDS   spacing between probes (default 2)

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

require_cmd curl

if [[ -n "${PREVIEW_URL_OVERRIDE:-}" ]]; then
    PREVIEW_URL="$PREVIEW_URL_OVERRIDE"
else
    : "${PR_NUMBER:?PR_NUMBER is required}"
    PREVIEW_URL="https://pr-${PR_NUMBER}.rediacc.workers.dev"
fi

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

# CHANGING *WHICH* ENDPOINT IS PROBED IS NOT THE FIX. THAT HAS BEEN TRIED TWICE.
#
# Commit 8b7840ed4 ("wait for the endpoint the smoke test needs, not the
# cheapest one") added the server-info probe; commit cefa43ca7 ("repair a
# vacuous preview-readiness gate") corrected the body assertion it grepped for.
# Both changed WHAT is probed. Neither changed HOW MANY TIMES, so the same
# failure came back a third time in runs 30968082228 and 30995469629: this
# script logged "ready" at 10:26:41.557 and smoke-test-preview.ts got HTTP 500
# from the very same server-info URL at 10:26:42.86, 1.3 seconds later. Probing
# the URL by hand afterwards returned 200 fifteen times out of fifteen.
#
# A single success cannot distinguish "up" from "flapping", and this deployment
# flaps by construction: deploy-www.sh deletes and recreates the per-PR D1
# database on EVERY push, and server-info is the first endpoint that touches D1
# (private/account/src/app.ts queries version_policies), while /health touches
# nothing. So the endpoint alternates while the fresh database propagates, and a
# first-success probe simply samples whichever answer it happened to catch.
#
# Hence a STREAK: the endpoints must hold for REQUIRED_STREAK consecutive probes,
# and any single failure resets the count to zero. If this fires falsely again,
# raise the streak or the budget. Do not go looking for a better endpoint.
REQUIRED_STREAK="${REQUIRED_STREAK:-3}"
MAX_ATTEMPTS="${MAX_ATTEMPTS:-60}"
PROBE_INTERVAL_SECONDS="${PROBE_INTERVAL_SECONDS:-2}"

streak=0
for i in $(seq 1 "$MAX_ATTEMPTS"); do
    if ready; then
        streak=$((streak + 1))
        if [[ "$streak" -ge "$REQUIRED_STREAK" ]]; then
            log_info "Preview worker is ready (health + server-info both serving, ${REQUIRED_STREAK} consecutive probes)"
            exit 0
        fi
        log_info "Preview worker answered ($streak/$REQUIRED_STREAK consecutive)... (attempt $i/$MAX_ATTEMPTS)"
    else
        if [[ "$streak" -gt 0 ]]; then
            log_warn "Preview worker flapped after $streak consecutive success(es); streak reset (attempt $i/$MAX_ATTEMPTS)"
        else
            log_info "Waiting for preview worker... (attempt $i/$MAX_ATTEMPTS)"
        fi
        streak=0
    fi
    sleep "$PROBE_INTERVAL_SECONDS"
done

log_error "Preview worker did not become ready (never held for $REQUIRED_STREAK consecutive probes)"
exit 1
