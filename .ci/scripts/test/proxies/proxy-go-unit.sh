#!/bin/bash
# Local proxy for the renet Go unit tests, the heaviest single leg of CI's
# test-renet job.
#
# WHAT CI RUNS. ct-tests.yml -> .ci/scripts/private/run-renet.sh ->
# private/renet/.ci/ci.sh -> private/renet/.ci/scripts/test/run-tests.sh, whose
# unit phase is
#
#     sudo -E gotestsum -- -v -race -coverprofile=coverage.out ./pkg/... ./cmd/...
#
# under root, with the race detector, plus a subscription phase against a live
# account server. None of that is in the parity surface, so a developer's local
# run has never compiled a single renet test.
#
# THE SUBSET, AND WHY IT IS COMPUTED RATHER THAN LISTED.
# Three things in CI's invocation cannot honestly be reproduced on a developer
# box: root, the race detector's cost, and the account server. Dropping root
# means dropping the packages whose tests genuinely need it -- they create loop
# devices, LUKS containers and btrfs subvolumes, and running them unprivileged
# on a real workstation is not a test, it is a hazard.
#
# So the subset is DERIVED on every run, never typed:
#
#   candidates = every ./pkg/... package `go list` reports as having test files
#   excluded   = those whose _test.go files reference Geteuid, RequireRoot or
#                the pkg/testutil privileged helpers (btrfs.go, luksext4.go)
#   subset     = candidates minus excluded
#
# A package renamed, added or deleted moves the numbers by itself. The excluded
# set is PRINTED BY NAME every run: it is real debt (those tests run only in CI)
# and a quiet exemption is how a gate stops meaning what its name says.
#
# WHAT THIS PROXY THEREFORE DOES NOT PROVE: no race detector, no root paths, no
# subscription e2e. It proves that the other 60 packages still compile and pass.

set -uo pipefail

PROXY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$PROXY_DIR/../../../.." && pwd)"
# shellcheck source=./proxy-lib.sh
source "$PROXY_DIR/proxy-lib.sh"

RENET_DIR="$ROOT_DIR/private/renet"

if [[ "${1:-}" == "--selftest" ]]; then
    proxy_lib_selftest
    exit $?
fi

proxy_init go-unit "the ./pkg/... unit phase of private/renet/.ci/scripts/test/run-tests.sh"

proxy_need_cmd go "./run.sh setup, or install the toolchain pinned in .devcontainer/toolchain.env"
proxy_need_file "$RENET_DIR/go.mod" "git submodule update --init private/renet"
proxy_need_file "$RENET_DIR/pkg" "git submodule update --init private/renet"
proxy_preflight

cd "$RENET_DIR" || exit 2
export GOTOOLCHAIN="${GOTOOLCHAIN:-auto}"

# A cold module cache with no network cannot resolve the graph. That is
# cannot-run, not a finding: reporting it as a failure would make a train
# journey look like a broken submodule.
LIST="$(go list -f '{{.ImportPath}} {{len .TestGoFiles}} {{len .XTestGoFiles}} {{.Dir}}' ./pkg/... 2>/dev/null)"
if [[ -z "$LIST" ]]; then
    echo "${PROXY_YEL}proxy go-unit: CANNOT RUN${PROXY_OFF}" >&2
    echo "  'go list ./pkg/...' produced nothing in $RENET_DIR." >&2
    echo "  fix: run 'go mod download' there once with network available." >&2
    echo "  Exiting 77 (cannot-run). The renet unit tests were NOT exercised." >&2
    exit "$PROXY_CANNOT_RUN"
fi

CANDIDATES="$(printf '%s\n' "$LIST" | awk '$2+$3>0')"
CAND_N=$(printf '%s\n' "$CANDIDATES" | grep -c . || true)

EXCLUDED_DIRS="$(grep -rlE 'Geteuid|RequireRoot|requireRoot|testutil\.' pkg/ --include='*_test.go' 2>/dev/null |
    xargs -r -n1 dirname | sort -u)"
EXCL_N=$(printf '%s\n' "$EXCLUDED_DIRS" | grep -c . || true)

SUBSET=()
while read -r ip _nt _nx dir; do
    [[ -z "$ip" ]] && continue
    rel="${dir#"$PWD"/}"
    if [[ -n "$EXCLUDED_DIRS" ]] && printf '%s\n' "$EXCLUDED_DIRS" | grep -qx "$rel"; then
        continue
    fi
    SUBSET+=("$ip")
done <<<"$CANDIDATES"

echo "proxy go-unit: $CAND_N ./pkg/... package(s) have tests; $EXCL_N excluded as root-only; ${#SUBSET[@]} in the subset"
if [[ $EXCL_N -gt 0 ]]; then
    echo "${PROXY_YEL}proxy go-unit: NOT EXERCISED HERE (root-only, CI runs them under sudo):${PROXY_OFF}"
    printf '  - %s\n' $EXCLUDED_DIRS
fi

if [[ ${#SUBSET[@]} -eq 0 ]]; then
    echo "${PROXY_RED}proxy go-unit: the derived subset is EMPTY${PROXY_OFF}" >&2
    echo "  Either go list saw no test files or the exclusion swallowed everything." >&2
    echo "  A run over zero packages exits 0 and proves nothing, so this is a failure." >&2
    exit 1
fi
proxy_pass "derived a non-empty subset: ${#SUBSET[@]} of $CAND_N packages with tests"

OUT="$(mktemp)"
ERR="$(mktemp)"
trap 'rm -f "$OUT" "$ERR"' EXIT

go test -count=1 -timeout 300s "${SUBSET[@]}" >"$OUT" 2>"$ERR"
RC=$?

if [[ $RC -eq 0 ]]; then
    proxy_pass "go test exited 0 over ${#SUBSET[@]} package(s)"
else
    proxy_fail "go test exited $RC"
    echo "  --- go test stdout (failures) ---" >&2
    grep -E '^(FAIL|---|\s+---)' "$OUT" >&2 || tail -40 "$OUT" >&2
    echo "  --- go test stderr (last 40) ---" >&2
    tail -40 "$ERR" >&2
fi

# `go test` prints one result line per package. Fewer than the subset size means
# packages silently dropped out of the invocation, which exits 0 and looks
# exactly like success.
OKN=$(grep -cE '^(ok|---)' "$OUT" || true)
NOTESTS=$(grep -c 'no test files' "$OUT" || true)
REPORTED=$(grep -cE '^(ok|FAIL|\?)' "$OUT" || true)
if [[ "$REPORTED" -eq "${#SUBSET[@]}" ]]; then
    proxy_pass "go test reported one result line per package ($REPORTED of ${#SUBSET[@]}); $OKN ok, $NOTESTS with no test files"
else
    proxy_fail "go test reported $REPORTED result line(s) for ${#SUBSET[@]} package(s); packages went missing from the run"
fi

proxy_finish
