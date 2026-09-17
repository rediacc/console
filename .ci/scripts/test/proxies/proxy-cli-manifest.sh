#!/bin/bash
# Local proxy for .ci/scripts/build/generate-cli-manifest.sh, one of the three
# release-path CI scripts this wave found with NO test of any kind.
#
# WHERE IT RUNS IN CI, and why an untested version of it is expensive: the
# manifest it writes is what `rdc update` fetches to decide which binary to
# download and what sha256 to verify it against. A wrong URL or a wrong hash in
# there is a broken updater for every installed CLI, and nothing in the tree
# exercised the generator until now.
#
# THE PROXY RUNS THE REAL SCRIPT against a synthetic dist directory in a
# throwaway tmpdir: six fake binaries with six .sha256 sidecars, plus one
# deliberately malformed sidecar. Nothing is written inside the checkout.
#
# BOTH DIRECTIONS, because a generator test with only a happy path proves very
# little:
#   MUST PRODUCE  the five well-formed platform/arch keys, each with the channel
#                 URL and the exact 64-character hash from its sidecar
#   MUST REJECT   a missing --version (exit 1), an unknown flag (exit 1)
#   MUST OMIT     the entry whose sidecar hash is not 64 characters
#
# ONE HAZARD IS PRINTED RATHER THAN RULED ON, and it is named here so it is not
# forgotten: with an input directory containing no .sha256 files at all, the
# subject writes a manifest whose `binaries` object is EMPTY and exits 0. That
# is a publishable release manifest that offers no downloads. This proxy does
# not fail on it, because the fix belongs in the subject and this file may not
# edit it; it reports it on every run so the debt stays visible.

set -uo pipefail

PROXY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$PROXY_DIR/../../../.." && pwd)"
# shellcheck source=./proxy-lib.sh
source "$PROXY_DIR/proxy-lib.sh"

SUBJECT="$ROOT_DIR/.ci/scripts/build/generate-cli-manifest.sh"

if [[ "${1:-}" == "--selftest" ]]; then
    proxy_lib_selftest
    exit $?
fi

proxy_init cli-manifest ".ci/scripts/build/generate-cli-manifest.sh"

proxy_need_exec "$SUBJECT" "the subject script is missing from this checkout"
proxy_need_cmd jq "sudo apt-get install -y jq"
proxy_need_cmd sha256sum "sudo apt-get install -y coreutils"
proxy_preflight

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
IN="$WORK/dist"
mkdir -p "$IN"

# Five well-formed pairs and one malformed sidecar. The hashes are computed, not
# typed, so the assertion below compares the manifest against the fixture rather
# than against a constant that could drift out of sync with it.
GOOD_KEYS=(linux-x64 linux-arm64 mac-x64 mac-arm64 win-x64)
declare -A EXPECTED_SHA=()
for key in "${GOOD_KEYS[@]}"; do
    name="rdc-${key}"
    [[ "$key" == win-* ]] && name="${name}.exe"
    printf 'fixture binary for %s\n' "$key" >"$IN/$name"
    sha256sum "$IN/$name" | awk -v n="$name" '{print $1 "  " n}' >"$IN/${name}.sha256"
    EXPECTED_SHA["$key"]="$(awk '{print $1}' "$IN/${name}.sha256")"
done
# win-arm64 gets a truncated hash: the subject must SKIP it, not emit a bad one.
printf 'fixture binary for win-arm64\n' >"$IN/rdc-win-arm64.exe"
printf 'deadbeef  rdc-win-arm64.exe\n' >"$IN/rdc-win-arm64.exe.sha256"

OUT="$WORK/manifest.json"
SO="$(mktemp)"
SE="$(mktemp)"

set +e
"$SUBJECT" --version 9.9.9 --channel edge --input "$IN" --output "$OUT" >"$SO" 2>"$SE"
RC=$?
set -e
if [[ $RC -eq 0 ]]; then
    proxy_pass "generate-cli-manifest.sh exited 0 over the fixture dist dir"
else
    proxy_fail "generate-cli-manifest.sh exited $RC"
    echo "  --- stdout ---" >&2
    cat "$SO" >&2
    echo "  --- stderr ---" >&2
    cat "$SE" >&2
fi

if [[ -f "$OUT" ]] && jq -e . "$OUT" >/dev/null 2>&1; then
    proxy_pass "the manifest exists and parses as JSON"

    GOT_KEYS="$(jq -r '.binaries | keys_unsorted | sort | join(" ")' "$OUT")"
    WANT_KEYS="$(printf '%s\n' "${GOOD_KEYS[@]}" | sort | tr '\n' ' ' | sed 's/ $//')"
    if [[ "$GOT_KEYS" == "$WANT_KEYS" ]]; then
        proxy_pass "binaries has exactly the ${#GOOD_KEYS[@]} well-formed keys: $GOT_KEYS"
    else
        proxy_fail "binaries keys are [$GOT_KEYS], expected [$WANT_KEYS]"
    fi

    if jq -e '.binaries | has("win-arm64")' "$OUT" >/dev/null 2>&1; then
        proxy_fail "win-arm64 was emitted despite a malformed (8-character) sidecar hash; a bad checksum would ship to every updater"
    else
        proxy_pass "the malformed sidecar was skipped, not emitted"
    fi

    HASH_OK=1
    for key in "${GOOD_KEYS[@]}"; do
        got="$(jq -r --arg k "$key" '.binaries[$k].sha256 // ""' "$OUT")"
        [[ "$got" == "${EXPECTED_SHA[$key]}" ]] || {
            HASH_OK=0
            echo "  sha256 mismatch for $key: manifest=$got fixture=${EXPECTED_SHA[$key]}" >&2
        }
    done
    if [[ $HASH_OK -eq 1 ]]; then
        proxy_pass "every emitted sha256 equals the fixture's own sha256sum output"
    else
        proxy_fail "at least one sha256 in the manifest does not match the file it names"
    fi

    # THE CHANNEL BRANCH, both sides. A release channel (stable or edge) bakes
    # the immutable /cli/v<version>/ path so homebrew and the CF long-cache can
    # pin it; every other channel points at /cli/<channel>/ so `rdc update`
    # fetches the bits that were actually uploaded for that PR. Asserting only
    # one side would let the branch invert unnoticed.
    URL="$(jq -r '.binaries["linux-x64"].url // ""' "$OUT")"
    proxy_expect_contains "$URL" "/cli/v9.9.9/" "a release channel (edge) bakes the immutable v-version path"
    proxy_expect_contains "$URL" "rdc-linux-x64" "the URL names the binary it describes"

    if "$SUBJECT" --version 9.9.9 --channel pr-420 --input "$IN" --output "$WORK/pr.json" >/dev/null 2>&1; then
        PRURL="$(jq -r '.binaries["linux-x64"].url // ""' "$WORK/pr.json")"
        proxy_expect_contains "$PRURL" "/cli/pr-420/" "a non-release channel points at its own channel path instead"
    else
        proxy_fail "the subject failed outright on --channel pr-420"
    fi

    VER="$(jq -r '.version // ""' "$OUT")"
    if [[ "$VER" == "9.9.9" ]]; then
        proxy_pass "version is carried through verbatim"
    else
        proxy_fail "version is '$VER', expected '9.9.9'"
    fi
else
    proxy_fail "no parseable manifest was written to $OUT"
fi

# The two documented refusals. A generator that accepts a missing --version
# would silently produce a manifest whose download URLs point at /v/.
proxy_expect_exit 1 "a missing --version is refused" -- "$SUBJECT" --input "$IN" --output "$WORK/x.json"
proxy_expect_exit 1 "an unknown flag is refused" -- "$SUBJECT" --version 9.9.9 --input "$IN" --output "$WORK/y.json" --bogus

# THE HAZARD, PRINTED EVERY RUN, NOT RULED ON. Fixing it means editing the
# subject, which this file does not own.
EMPTY="$WORK/empty"
mkdir -p "$EMPTY"
set +e
"$SUBJECT" --version 9.9.9 --channel edge --input "$EMPTY" --output "$WORK/empty.json" >/dev/null 2>&1
ERC=$?
set -e
ECOUNT="$(jq -r '(.binaries // {}) | length' "$WORK/empty.json" 2>/dev/null || echo "?")"
echo "${PROXY_YEL}proxy cli-manifest: KNOWN HAZARD in the subject, reported not enforced.${PROXY_OFF}"
echo "${PROXY_YEL}  With an input dir holding no .sha256 files the subject exits ${ERC} and writes${PROXY_OFF}"
echo "${PROXY_YEL}  a manifest with ${ECOUNT} binaries. A release published from that manifest offers${PROXY_OFF}"
echo "${PROXY_YEL}  no downloads at all, and nothing on the release path notices. Reproduce with:${PROXY_OFF}"
echo "${PROXY_YEL}    .ci/scripts/build/generate-cli-manifest.sh --version 9.9.9 --input \$(mktemp -d) --output /tmp/m.json${PROXY_OFF}"

rm -f "$SO" "$SE"
proxy_finish
