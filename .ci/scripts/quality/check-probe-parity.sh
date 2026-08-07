#!/bin/bash
# Parity gate: a capability probe must exercise the operations its CONSUMER
# depends on — not a convenient subset of them.
#
# WHY THIS EXISTS. On 2026-08-05 the transfer drill's keyring preflight ran
# `keyctl add`, saw it succeed, and reported "keyring usable". The drill then
# died anyway, because a GitHub runner permits `keyctl add` and DENIES the read
# (`keyctl pipe`) — and the read is what `KeyctlStorage.get()` actually needs.
# The probe tested a permitted operation while the operation the code depends on
# was the denied one, so it produced a confident false negative.
#
# That was the SIXTH instance of this class in one night (probing `clang` when
# bpf2go also needs `llvm-strip`; `curl -f` on an endpoint documented to answer
# 403; `keyctl show @u` in secure-storage.ts; a liveness probe that read `000000`
# as alive; a gate whose subject never loaded). It was authored hours after the
# TRAPS.md entry describing the class, by someone who had already been caught by
# it twice. Knowing about the pattern demonstrably does not prevent it, which is
# why it needs a gate rather than a note.
#
# WHAT THIS CHECKS, mechanically rather than semantically: the set of `keyctl`
# subcommands invoked by the PROBE must cover the set invoked by the CONSUMER,
# minus an explicit, justified exemption list. Adding a new keyctl call to
# KeyctlStorage without teaching the probe about it is then a red, with a message
# naming the operation that would go untested.
#
# CONTROL-FIRST. The gate fails itself when it cannot see its own inputs: if
# either extraction yields an empty verb set, the comparison would be a
# tautology over nothing, which is the exact vacuity this repo keeps paying for.
#
# Usage: check-probe-parity.sh

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

cd "$(get_repo_root)"

CONSUMER="packages/cli/src/utils/secure-storage.ts"
PROBE="scripts/drills/transfer.sh"

# Cleanup-only verbs. The consumer unlinks; the probe purges. Both remove the
# key and neither is on the success path the probe exists to predict, so they
# are interchangeable here. Anything else must be exercised.
EXEMPT_VERBS=("unlink" "purge" "revoke")

log_step "Checking capability-probe parity ($PROBE vs $CONSUMER)..."

for f in "$CONSUMER" "$PROBE"; do
    if [[ ! -f "$f" ]]; then
        log_error "$f not found — this gate has nothing to check, which is a failure,"
        log_error "not a pass: parity cannot be asserted against a file that is gone."
        exit 1
    fi
done

# Consumer: execFileSync('keyctl', ['<verb>', ...])
consumer_verbs=$(grep -oE "execFileSync\('keyctl', \['[a-z]+" "$CONSUMER" |
    grep -oE "'[a-z]+$" | tr -d "'" | sort -u)

# Probe: bare `keyctl <verb>` invocations in the shell preflight.
#
# COMMENT LINES ARE STRIPPED FIRST, and that is not a detail. The first version
# of this gate did not strip them, so it happily counted the `keyctl pipe`
# appearing inside the preflight's own explanatory comment and reported parity
# for a probe that had the read-back REMOVED. A gate that cannot tell "exercises
# an operation" from "mentions it in prose" is the very defect it audits — found
# by running the planted-defect proof, which is the only reason it is not still
# there.
probe_verbs=$(sed 's/[[:space:]]*#.*$//' "$PROBE" |
    grep -oE '(^|[^-[:alnum:]_])keyctl [a-z]+' |
    awk '{print $NF}' | sort -u)

# CONTROL: an empty side makes the comparison vacuous.
if [[ -z "$consumer_verbs" ]]; then
    log_error "CONTROL FAILED: no keyctl verbs extracted from $CONSUMER."
    log_error "Either the consumer stopped using keyctl (retire this gate) or the"
    log_error "extraction broke. Refusing to report parity against an empty set."
    exit 1
fi
if [[ -z "$probe_verbs" ]]; then
    log_error "CONTROL FAILED: no keyctl verbs extracted from $PROBE."
    log_error "The preflight appears to probe nothing, which is worse than the"
    log_error "partial probe this gate exists to catch."
    exit 1
fi

log_info "consumer verbs: $(tr '\n' ' ' <<<"$consumer_verbs")"
log_info "probe verbs:    $(tr '\n' ' ' <<<"$probe_verbs")"

missing=""
for verb in $consumer_verbs; do
    exempt=0
    for e in "${EXEMPT_VERBS[@]}"; do
        [[ "$verb" == "$e" ]] && exempt=1 && break
    done
    [[ "$exempt" == "1" ]] && continue
    if ! grep -qx "$verb" <<<"$probe_verbs"; then
        missing="$missing $verb"
    fi
done

if [[ -n "$missing" ]]; then
    log_error "The keyring preflight does NOT exercise:$missing"
    log_error ""
    log_error "$CONSUMER calls those, so an environment that permits the probed"
    log_error "operations but denies one of these makes the preflight report"
    log_error "'usable' and the drill fail anyway — the 2026-08-05 defect, where a"
    log_error "runner allowed 'keyctl add' and denied 'keyctl pipe'."
    log_error ""
    log_error "Fix the PROBE to exercise the full round trip. Do not add the verb to"
    log_error "EXEMPT_VERBS unless it genuinely cannot affect whether the consumer"
    log_error "succeeds — cleanup-only operations are the sole intended exemption."
    exit 1
fi

log_info "Probe parity holds: every consumer keyctl operation is exercised by the preflight"
