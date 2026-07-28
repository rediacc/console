#!/bin/bash
# Licensing enforcement battery: prove that a release-shaped renet binary really
# refuses unlicensed work, and really accepts a valid license, against a
# throwaway Ed25519 master key minted for this run only.
#
# This script IS the local-dev entry point and is exactly what CI runs; there is
# no CI-only variant to drift from.
#
# WHY IT NEEDS NO VM, NO BTRFS, NO LUKS, NO DOCKER
# ------------------------------------------------
# The license gate fires before any storage work:
#   - repository create  checks the license at repository_create.go:124, which is
#     BEFORE the --password-stdin check at :134 and long before any LUKS/BTRFS.
#   - repository up      checks it at repository_up.go:85, before the repo lock,
#     network detection and mount.
# So an accepted license shows up as "renet got past the gate and then failed at
# the SAME later point an unlicensed-build twin fails at". Every scenario below
# is therefore a sub-second binary invocation against an empty scratch directory.
#
# WHAT NEEDS PRIVILEGE
# --------------------
# Only installing the license files. license.RepoLicenseDir
# (/var/lib/rediacc/license/repos) is a hardcoded constant with no env override
# (store.go:14-24, passed directly at runtime_licensed.go:73), so the fixtures go
# there via `sudo -n`. renet itself runs unprivileged except for the chain-state
# scenario, which writes /var/lib/rediacc/license/chain-state.json.
#
# The pre-existing chain-state.json is backed up and restored, and only the
# battery's own repo directories are removed, so running this on a machine with
# real repo licenses does not disturb them.
#
# PROVING THE INSTRUMENT
# ----------------------
# The battery runs three times, against three binaries built from the same
# source, and the two control runs MUST fail:
#   - enforcing   baked with the ephemeral master key   -> every scenario passes
#   - nolicense   built with -tags nolicense            -> S1 must FAIL (the stub
#                                                          accepts everything)
#   - wrong-key   baked with a stranger's public key    -> S2 must FAIL (a valid
#                                                          license stops validating)
# S1 alone cannot catch a wrongly-baked or empty key; S2 alone cannot catch a
# nolicense build. Both controls are required, and a battery that cannot fail
# would be worthless.
#
# Local run (from anywhere in the repo):
#   .ci/scripts/private/license-e2e.sh
#
# Requires: go, jq, passwordless sudo, and renet's embedded assets already
# extracted (private/renet/pkg/embed/assets/<arch>/ — `./build.sh embed_assets`).
# Optional: LICENSE_E2E_MASTER_PUB + LICENSE_E2E_MASTER_PRIV (base64 SPKI/PKCS8)
# to reuse a caller-supplied ephemeral pair instead of generating one.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"
REPO_ROOT="$(get_repo_root)"

# Overridable so the battery can be pointed at a CLEAN checkout of renet, which
# is the state CI actually builds in. It matters because pkg/embed/assets is
# gitignored: a fresh checkout carries only the committed .gitkeep placeholders,
# which is exactly what makes the `//go:embed assets/<arch>/base/*` patterns
# still compile. Verified by building in a throwaway `git worktree`: the binary
# links in 4.6s at 44MB there, against 233MB with the 340MB payload staged.
#
# So this leg needs NO embed-assets cache, unlike every other renet job. Being
# able to PROVE that rather than reason about Go's embed globbing is the whole
# reason this is a variable.
RENET_SRC="${RENET_SRC:-$REPO_ROOT/private/renet}"
MINT_SRC="$SCRIPT_DIR/license-mint"
KEYS_LDPATH="github.com/rediacc/renet/pkg/license/keys.ProductionPublicKey"

# Installed-license root. Hardcoded in renet; not overridable.
LICENSE_ROOT="/var/lib/rediacc/license"
REPO_LICENSE_ROOT="$LICENSE_ROOT/repos"
CHAIN_STATE="$LICENSE_ROOT/chain-state.json"

# Repo identifiers owned by this battery. The create/up scenarios accept any
# name; the chain-state scenario goes through `repository license-status`, which
# only looks at datastore entries shaped like a GUID (repository_license_status.go:42).
REPO_PREFIX="license-e2e"
CHAIN_GUID="1ce1ce2e-0000-0000-0000-000000000001"

# The attribution line renet logs ONLY after a license validates
# (runtime_licensed.go:77). Its presence is the positive proof that the real
# validator ran and succeeded — a nolicense stub never emits it.
ATTRIBUTION="Licensed to: license-e2e@rediacc.invalid"
# Where an accepted create/up lands instead: the same failure an unlicensed
# build reaches, which is the point of the whole design.
CREATE_TAIL="--password-stdin is required"
UP_TAIL="no password or keyfile provided"

SUDO=""
[[ $EUID -ne 0 ]] && SUDO="sudo -n"

WORK=""
LICENSE_ROOT_PREEXISTED=0
CHAIN_STATE_BACKUP=""

cleanup() {
    local status=$?
    set +e
    # The license store is restored BEFORE $WORK is removed: the chain-state
    # backup lives inside $WORK, and wiping it first would turn "restore the
    # operator's chain state" into "delete the operator's chain state".
    if [[ $LICENSE_ROOT_PREEXISTED -eq 0 ]]; then
        $SUDO rm -rf "$LICENSE_ROOT"
    else
        $SUDO rm -rf "$REPO_LICENSE_ROOT/$REPO_PREFIX"-* "$REPO_LICENSE_ROOT/$CHAIN_GUID"
        if [[ -n "$CHAIN_STATE_BACKUP" && -f "$CHAIN_STATE_BACKUP" ]]; then
            $SUDO cp -p "$CHAIN_STATE_BACKUP" "$CHAIN_STATE"
        else
            $SUDO rm -f "$CHAIN_STATE"
        fi
    fi
    if [[ -n "$WORK" ]]; then
        # Never leave an enforcing renet anywhere reachable.
        rm -rf "$WORK"
    fi
    exit $status
}
trap cleanup EXIT

# ---------------------------------------------------------------------------
# Preflight
# ---------------------------------------------------------------------------

preflight() {
    local missing=0
    for tool in go jq; do
        command -v "$tool" >/dev/null || {
            log_error "$tool is required but not on PATH"
            missing=1
        }
    done
    # go:embed fails at COMPILE time when the asset trees are absent, so check
    # for them here rather than letting the build produce a wall of embed errors.
    local arch
    arch="$(go env GOARCH 2>/dev/null || echo amd64)"
    if [[ ! -d "$RENET_SRC/pkg/embed/assets/$arch/base" ]]; then
        log_error "renet embedded assets missing at pkg/embed/assets/$arch/base — run 'cd private/renet && ./build.sh embed_assets'"
        missing=1
    fi
    if ! $SUDO true 2>/dev/null; then
        log_error "passwordless sudo is required to install licenses under $REPO_LICENSE_ROOT (the path is hardcoded in renet)"
        missing=1
    fi
    [[ $missing -eq 0 ]] || exit 1
}

# ---------------------------------------------------------------------------
# Keys and binaries
# ---------------------------------------------------------------------------

# build_renet <output> <public-key-base64> [extra go build args...]
#
# Built with `go build` on purpose. .ci/scripts/infra/build-renet.sh short-
# circuits when the output already exists (build-renet.sh:44-46), so it would
# silently hand back a binary baked with a different key or built with different
# tags. private/renet/build.sh is worse for this job: _account_key_ldflags
# (build.sh:333-343) falls back to ED25519_PUBLIC_KEY out of private/account/.env
# when ACCOUNT_ED25519_PUBLIC_KEY is unset, which would bake the PRODUCTION key
# into a binary this script then treats as a test fixture.
build_renet() {
    local out="$1" pubkey="$2"
    shift 2
    (cd "$RENET_SRC" && go build -ldflags "-X $KEYS_LDPATH=$pubkey" "$@" -o "$out" ./cmd/renet)
}

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

# mint <repo> [mint flags...] — writes <keyId>.json into a staging dir.
mint() {
    local repo="$1"
    shift
    rm -rf "$WORK/stage"
    "$MINT" -master-key "$MASTER_PRIV" -out-dir "$WORK/stage" -repo "$repo" "$@" >/dev/null
}

# install_license <repo> — moves the staged blob into the real license store.
install_license() {
    local repo="$1"
    $SUDO rm -rf "${REPO_LICENSE_ROOT:?}/$repo"
    $SUDO mkdir -p "$REPO_LICENSE_ROOT/$repo"
    $SUDO cp "$WORK"/stage/*.json "$REPO_LICENSE_ROOT/$repo/"
    # World-readable so the unprivileged renet invocations can read them, which
    # is how a real install looks.
    $SUDO chmod -R a+rX "$LICENSE_ROOT"
}

install_fixtures() {
    log_step "Minting and installing license fixtures..."

    # S1 deliberately has NO license installed.

    mint "$REPO_PREFIX-valid"
    install_license "$REPO_PREFIX-valid"

    mint "$REPO_PREFIX-delegated" -delegate
    install_license "$REPO_PREFIX-delegated"

    # Signed by a stranger while still claiming the master key's fingerprint, so
    # the direct-verification path at validator.go:92-97 is the one that rejects it.
    mint "$REPO_PREFIX-forged" -forge-signer "$STRANGER_PRIV" -key-id "$MASTER_KEY_ID"
    install_license "$REPO_PREFIX-forged"

    # A delegation cert the master never signed.
    mint "$REPO_PREFIX-rogue-cert" -delegate -cert-signer "$STRANGER_PRIV"
    install_license "$REPO_PREFIX-rogue-cert"

    mint "$REPO_PREFIX-expired" -hard-expires -1h
    install_license "$REPO_PREFIX-expired"

    mint "$REPO_PREFIX-cert-expired" -delegate -cert-valid-from -48h -cert-valid-until -1h
    install_license "$REPO_PREFIX-cert-expired"

    # Machine mismatch only bites once the 40-day grace from issuedAt has run out
    # (types.go:56-65), so this one is backdated and its twin is not.
    mint "$REPO_PREFIX-wrong-machine" -machine not-this-machine -issued-at -1200h
    install_license "$REPO_PREFIX-wrong-machine"

    mint "$REPO_PREFIX-machine-grace" -machine not-this-machine -issued-at -24h
    install_license "$REPO_PREFIX-machine-grace"
}

# ---------------------------------------------------------------------------
# Assertions
# ---------------------------------------------------------------------------

BATTERY_LABEL=""
BATTERY_FAILED=()

record_pass() {
    log_info "[$BATTERY_LABEL] $1 PASS — $2"
}

record_fail() {
    BATTERY_FAILED+=("$1")
    log_error "[$BATTERY_LABEL] $1 FAIL — $2"
}

# run_renet <cmd...> — drives the binary DIRECTLY, never through rdc: the CLI's
# exit-10 recovery framework (packages/cli/src/services/executor/local-executor.ts)
# retries and rewrites the failure, which would hide the raw exit code this
# battery exists to assert on. stdout and stderr are captured separately.
run_renet() {
    "$@" >"$WORK/stdout.txt" 2>"$WORK/stderr.txt" && RENET_CODE=0 || RENET_CODE=$?
}

# assert_rejected <id> <reason> <cmd...>
assert_rejected() {
    local id="$1" reason="$2"
    shift 2
    run_renet "$@"
    if [[ $RENET_CODE -ne 10 ]]; then
        record_fail "$id" "expected exit 10, got $RENET_CODE; stderr: $(head -c 300 "$WORK/stderr.txt" | tr '\n' ' ')"
        return
    fi
    if ! grep -q "\"reason\":\"$reason\"" "$WORK/stderr.txt"; then
        record_fail "$id" "exit 10 but reason was not '$reason': $(grep -o '{"code".*}' "$WORK/stderr.txt" || echo '<no LICENSE_REQUIRED payload>')"
        return
    fi
    record_pass "$id" "exit 10, reason=$reason"
}

# assert_accepted <id> <expected-later-failure> <cmd...>
#
# Acceptance is three facts, not one: the gate did not fire (exit != 10, no
# LICENSE_REQUIRED anywhere), the validator positively reported success, and the
# command then failed at the SAME later point an unlicensed build reaches.
assert_accepted() {
    local id="$1" tail="$2"
    shift 2
    run_renet "$@"
    if [[ $RENET_CODE -eq 10 ]]; then
        record_fail "$id" "license gate rejected a valid license: $(grep -o '{"code".*}' "$WORK/stderr.txt" || echo '<no payload>')"
        return
    fi
    if grep -q "LICENSE_REQUIRED" "$WORK/stderr.txt"; then
        record_fail "$id" "LICENSE_REQUIRED surfaced despite exit $RENET_CODE"
        return
    fi
    if ! grep -qF -- "$ATTRIBUTION" "$WORK/stderr.txt"; then
        record_fail "$id" "validator never reported acceptance ('$ATTRIBUTION' absent) — the license was not actually validated"
        return
    fi
    if ! grep -qF -- "$tail" "$WORK/stderr.txt"; then
        record_fail "$id" "accepted but did not reach the expected later failure '$tail': $(head -c 300 "$WORK/stderr.txt" | tr '\n' ' ')"
        return
    fi
    record_pass "$id" "accepted (exit $RENET_CODE at '$tail')"
}

# license_status <binary> — the only modeFull vehicle that needs no real repo.
# It reads <datastore>/repositories/<guid> (an empty directory is enough) and
# runs the full validation including chain state. Runs privileged because
# validateBlob persists chain state under $LICENSE_ROOT.
license_status() {
    $SUDO "$1" repository license-status --datastore "$WORK/ds-chain" --output json 2>"$WORK/stderr.txt" |
        jq -r '.[0].status'
}

# ---------------------------------------------------------------------------
# The battery
# ---------------------------------------------------------------------------

run_battery() {
    local bin="$1"
    BATTERY_LABEL="$2"
    BATTERY_FAILED=()

    local create=("$bin" repository create --network-id 77 --size 1G --datastore "$WORK/ds" --skip-mount --name)
    local up=("$bin" repository up --datastore "$WORK/ds" --name)

    # S1 — nothing installed at all.
    assert_rejected S1 missing "${create[@]}" "$REPO_PREFIX-absent"

    # S2 — a license signed directly by the baked master key.
    assert_accepted S2 "$CREATE_TAIL" "${create[@]}" "$REPO_PREFIX-valid"

    # S3 — signed by a delegated key, authorized by a master-signed cert. Also
    # exercises the per-key candidate loop at runtime_licensed.go:105-125, since
    # the file is named after the DELEGATED key, not the baked one.
    assert_accepted S3 "$CREATE_TAIL" "${create[@]}" "$REPO_PREFIX-delegated"

    # S4 — a stranger's signature under the master key's name.
    assert_rejected S4 invalid_signature "${create[@]}" "$REPO_PREFIX-forged"

    # S4b — a delegation cert signed by someone who is not the master.
    assert_rejected S4b cert_invalid "${create[@]}" "$REPO_PREFIX-rogue-cert"

    # S5 — the tier split. An expired license cannot create, but must not stop a
    # user from operating data they already have (runtime_licensed.go:28-33).
    assert_rejected S5a expired "${create[@]}" "$REPO_PREFIX-expired"
    assert_accepted S5b "$UP_TAIL" "${up[@]}" "$REPO_PREFIX-expired"

    # S5c/S5d — same split for the delegation cert's validity window, which the
    # operate tier skips while still enforcing the cert's signature.
    assert_rejected S5c cert_expired "${create[@]}" "$REPO_PREFIX-cert-expired"
    assert_accepted S5d "$UP_TAIL" "${up[@]}" "$REPO_PREFIX-cert-expired"

    # S6 — sequence regression, with the chain state on real disk. Rolling a
    # license back to an older sequence must be rejected after the newer one has
    # been seen. This is the modeFull tier, reached through license-status.
    #
    # Asserted on the status field, not on exit 10, because the full tier only
    # wraps missing/expired into a LICENSE_REQUIRED error (repository_limits.go:70-76);
    # every tamper reason reaches the caller as a plain exit 1. See the report.
    mint "$CHAIN_GUID" -sequence 2 -chain-hash -subscription "$REPO_PREFIX-chain"
    install_license "$CHAIN_GUID"
    local seen
    seen="$(license_status "$bin" || true)"
    if [[ "$seen" != "valid" ]]; then
        record_fail S6a "sequence 2 should validate, got '$seen'"
    else
        record_pass S6a "sequence 2 accepted and recorded in chain state"
    fi

    mint "$CHAIN_GUID" -sequence 1 -chain-hash -subscription "$REPO_PREFIX-chain"
    install_license "$CHAIN_GUID"
    seen="$(license_status "$bin" || true)"
    if [[ "$seen" != "sequence_regression" ]]; then
        record_fail S6b "rolling back to sequence 1 should be refused, got '$seen'"
    else
        record_pass S6b "sequence 1 refused after sequence 2 (sequence_regression)"
    fi

    # S7 — a license minted for a different machine, past the 40-day grace.
    assert_rejected S7 machine_mismatch "${create[@]}" "$REPO_PREFIX-wrong-machine"

    # S7b — the same mismatch inside the grace window is deliberately tolerated,
    # so a VM migration does not brick a repo.
    assert_accepted S7b "$CREATE_TAIL" "${create[@]}" "$REPO_PREFIX-machine-grace"

    [[ ${#BATTERY_FAILED[@]} -eq 0 ]]
}

# expect_control_failure <label> <scenario-that-must-fail>
#
# Runs the battery against a binary that MUST NOT pass it, and fails the whole
# script when it does — or when it fails for the wrong reason.
expect_control_failure() {
    local bin="$1" label="$2" required="$3"
    if run_battery "$bin" "$label"; then
        log_error "CONTROL FAILED: the $label binary passed the battery. The battery cannot detect a broken build and is worthless as written."
        return 1
    fi
    local found=0 id
    for id in "${BATTERY_FAILED[@]}"; do
        [[ "$id" == "$required" ]] && found=1
    done
    if [[ $found -eq 0 ]]; then
        log_error "CONTROL FAILED: the $label binary failed the battery, but $required passed. That scenario is what detects this defect class; failures were: ${BATTERY_FAILED[*]}"
        return 1
    fi
    log_info "Control OK: $label fails the battery at $required (with ${BATTERY_FAILED[*]})"
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

preflight

WORK="$(mktemp -d "${TMPDIR:-/tmp}/license-e2e.XXXXXX")"
mkdir -p "$WORK/ds" "$WORK/ds-chain/repositories/$CHAIN_GUID"

[[ -d "$LICENSE_ROOT" ]] && LICENSE_ROOT_PREEXISTED=1
if [[ $LICENSE_ROOT_PREEXISTED -eq 1 && -f "$CHAIN_STATE" ]]; then
    CHAIN_STATE_BACKUP="$WORK/chain-state.backup.json"
    # cp -p, not a redirect: renet writes this file 0600 root-owned, and the
    # restore has to put back the same mode, not whatever umask produces.
    $SUDO cp -p "$CHAIN_STATE" "$CHAIN_STATE_BACKUP"
    log_info "Backed up the existing chain state; it is restored on exit"
fi

log_step "Building license-mint..."
MINT="$WORK/license-mint"
(cd "$MINT_SRC" && go build -o "$MINT" .)

# The ephemeral master key. Never the production key: a build baked with a key
# this script also holds the private half of can only ever validate this
# script's own fixtures.
if [[ -n "${LICENSE_E2E_MASTER_PUB:-}" && -n "${LICENSE_E2E_MASTER_PRIV:-}" ]]; then
    MASTER_PUB="$LICENSE_E2E_MASTER_PUB"
    MASTER_PRIV="$LICENSE_E2E_MASTER_PRIV"
    log_info "Using the caller-supplied ephemeral master key"
else
    log_step "Generating an ephemeral master key..."
    keypair="$("$MINT" -gen-key)"
    MASTER_PUB="$(jq -r .public <<<"$keypair")"
    MASTER_PRIV="$(jq -r .private <<<"$keypair")"
fi
stranger="$("$MINT" -gen-key)"
STRANGER_PUB="$(jq -r .public <<<"$stranger")"
STRANGER_PRIV="$(jq -r .private <<<"$stranger")"

MASTER_KEY_ID="$("$MINT" -master-key "$MASTER_PRIV" -out-dir "$WORK/fp" -repo fingerprint-probe | jq -r .publicKeyId)"
rm -rf "$WORK/fp"
log_info "Ephemeral master key fingerprint: $MASTER_KEY_ID"

log_step "Building renet: enforcing, nolicense twin, wrong-key twin..."
build_renet "$WORK/renet-enforcing" "$MASTER_PUB"
build_renet "$WORK/renet-nolicense" "$MASTER_PUB" -tags nolicense
build_renet "$WORK/renet-wrongkey" "$STRANGER_PUB"

install_fixtures

log_step "Running the battery against the enforcing binary..."
if ! run_battery "$WORK/renet-enforcing" enforcing; then
    log_error "License enforcement battery FAILED: ${BATTERY_FAILED[*]}"
    exit 1
fi
log_info "Enforcing binary passed every scenario"

log_step "Proving the instrument: the same battery must FAIL on a nolicense build..."
expect_control_failure "$WORK/renet-nolicense" nolicense S1

log_step "Proving the instrument: the same battery must FAIL on a wrongly-baked key..."
expect_control_failure "$WORK/renet-wrongkey" wrong-key S2

log_info "License enforcement battery passed, and both controls failed as required"
