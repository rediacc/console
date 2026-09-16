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
#   excluded   = those whose _test.go files match, as a SUBSTRING anywhere in
#                the file (comments and string literals included), any of the
#                five alternatives of
#
#                    Geteuid|RequireRoot|requireRoot|testutil\.|Getuid
#
#   subset     = candidates minus excluded
#
# A package renamed, added or deleted moves the numbers by itself. The excluded
# set is PRINTED BY NAME every run: it is real debt (those tests run only in CI)
# and a quiet exemption is how a gate stops meaning what its name says.
#
# THE FOURTH ALTERNATIVE IS DELIBERATELY BROADER THAN "PRIVILEGED", and this
# comment is where that was got wrong. Until 2026-09-10 it described the
# excluded set as the packages referencing "the pkg/testutil privileged helpers
# (btrfs.go, luksext4.go)", which reads as a per-SYMBOL distinction the grep
# does not make. It matches ANY `testutil.` reference, and that is the correct
# behaviour rather than the bug: pkg/testutil is those two files and exists to
# host root-only helpers, but not every symbol in it is one (SHA256File,
# NewSeededRng, MakePatch and FilesIdentical need no privilege at all), so a
# per-symbol rule could only be a HAND-TYPED allowlist -- the one thing this
# subset refuses to be -- and it would go stale in the HAZARDOUS direction: add
# a privileged helper to that package, forget the list, and an unprivileged
# workstation starts creating loop devices and LUKS containers. So a reference
# to the package is read as a privilege signal, full stop. Over-exclusion costs
# local coverage and is PRINTED BY NAME every run; under-exclusion costs a
# damaged workstation and says nothing. Measured on this tree on 2026-09-10 the
# fourth alternative removes NOTHING extra: the five files it matches
# (chunkstore, delta x2, kubecsi, repodiff) are a strict subset of the nine
# matched by the first three, so all eight excluded directories would be
# excluded without it. The documentation was corrected, the grep was not
# touched.
#
# THE FIFTH ALTERNATIVE WAS ADDED 2026-09-10, A REAL GAP FOUND BY DRIVING THIS
# PROXY UNDER A CI-SHAPED ENVIRONMENT. `pkg/storage` gates its root-only tests
# with plain `os.Getuid() != 0` (directory_test.go, luks_test.go), an idiom the
# first four alternatives do not catch -- it is neither `Geteuid` (a different,
# real Go function this pattern also has to ignore) nor `RequireRoot` nor
# `testutil.`. Locally, with no `CI` env var, those tests just SKIP and this
# proxy silently reports a clean pass over 11 tests it never really ran. Under
# `CI=true` (what real CI sets, and what this proxy's own differential drives
# it under), `pkg/storage`'s tests instead call `t.Fatalf("CI must run as root
# for LUKS storage tests")`, and the whole package -- including its non-LUKS
# `TestDirectoryStorage_*` cases, gated by the same idiom -- hard-fails this
# gate. Measured: `pkg/repository` and `pkg/filesystem` use the identical
# `os.Getuid() != 0` guard and move into the excluded set too; `pkg/daemon` was
# already excluded by the first alternative. Net: 68 -> 11 excluded, 57 in the
# subset (was 8 excluded, 60 in the subset).
#
# WHAT THIS PROXY THEREFORE DOES NOT PROVE: no race detector, no root paths, no
# subscription e2e. It proves that the other 57 packages still compile and pass.

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

EXCLUDED_DIRS="$(grep -rlE 'Geteuid|RequireRoot|requireRoot|testutil\.|Getuid' pkg/ --include='*_test.go' 2>/dev/null |
    xargs -r -n1 dirname | sort -u)"
EXCL_N=$(printf '%s\n' "$EXCLUDED_DIRS" | grep -c . || true)

SUBSET=()
while read -r ip _nt _nx dir; do
    [[ -z "$ip" ]] && continue
    rel="${dir#"$PWD"/}"
    # `grep -qx` became `[ -n "$(... | grep -Fx ...)" ]`: $EXCLUDED_DIRS scales with
    # pkg/ and is re-emitted on every trip round this loop, so grep -q's early exit
    # could SIGPIPE the printf and leave a root-only package in the subset. `-F` is
    # not cosmetic either -- $rel is a path, and without it a `.` in a package name
    # matches any character.
    if [[ -n "$EXCLUDED_DIRS" ]] && [ -n "$(printf '%s\n' "$EXCLUDED_DIRS" | grep -Fx "$rel")" ]; then
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
