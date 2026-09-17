#!/bin/bash
# Local proxy for the `renet ops host check` leg of .github/workflows/ci-ops-test.yml.
#
# WHY THIS ONE EXISTS AT ALL, stated first because it is the finding.
# ci-ops-test.yml:573-575 is
#
#     - name: "Test: renet ops host check"
#       run: $RENET_BINARY ops host check || true
#
# The `|| true` means that step cannot fail, on any platform, for any reason.
# The only real assertion on the command's output in the whole workflow is
# Windows-only (ci-ops-test.yml:584-589), where three `jq -e` expressions check
# `.platform` and `.backend`. So on Linux and macOS the command's CONTRACT --
# that it emits parseable JSON with a populated check list at all -- has never
# been asserted anywhere.
#
# WHAT THIS PROXY ASSERTS, AND WHAT IT DELIBERATELY DOES NOT.
# It asserts the SHAPE of the report, not the health of the host:
#
#   - the command exits 0
#   - stdout parses as JSON
#   - .platform is non-empty and matches this host's `go env GOOS` equivalent
#   - .backend is non-empty
#   - .checks is a non-empty array (a report with no checks is the vacuity)
#   - every entry carries name, value and status
#   - every status is one of ok / warn / fail, so a typo cannot pass silently
#   - every non-ok entry carries a `hint`, because a failing probe with no fix
#     text is the "stack trace that reads as flake" failure
#   - and if the one jq program that checks all of that cannot RUN -- a type
#     error aborts it and it exits 5 -- that is a named finding, never the
#     empty finding set it used to be read as (fixed 2026-09-10)
#
# It does NOT assert that every check is `ok`. A developer box legitimately has
# no libvirt, and a gate that reds on that would be a host-configuration gate
# wearing a contract gate's name. The per-status tally is PRINTED instead, so a
# reader can see the composition and notice when it collapses.
#
# --selftest drives the validator over two good fixtures and eight bad ones,
# because a validator with only positive controls will happily accept anything,
# and one with only negative ones will happily flag the whole tree.

set -uo pipefail

PROXY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$PROXY_DIR/../../../.." && pwd)"
# shellcheck source=./proxy-lib.sh
source "$PROXY_DIR/proxy-lib.sh"

# ---------------------------------------------------------------------------
# The pure validator. Reads the report on stdin, echoes one finding per line,
# and exits non-zero when it found any. Kept free of the binary and of the
# proxy's own state so the selftest can drive it directly.
# ---------------------------------------------------------------------------
validate_report() {
    local want_platform="$1" json findings
    json="$(cat)"
    findings=""

    if ! printf '%s' "$json" | jq -e . >/dev/null 2>&1; then
        echo "stdout is not parseable JSON"
        return 1
    fi

    local platform backend n
    platform="$(printf '%s' "$json" | jq -r '.platform // ""')"
    backend="$(printf '%s' "$json" | jq -r '.backend // ""')"
    n="$(printf '%s' "$json" | jq -r '(.checks // []) | length')"

    [[ -n "$platform" ]] || findings+=".platform is missing or empty"$'\n'
    if [[ -n "$want_platform" && -n "$platform" && "$platform" != "$want_platform" ]]; then
        findings+=".platform is \"$platform\" but this host is \"$want_platform\""$'\n'
    fi
    [[ -n "$backend" ]] || findings+=".backend is missing or empty"$'\n'

    # ZERO CHECKS IS A FAILURE, NEVER A PASS. An empty list would satisfy every
    # per-entry rule below by matching nothing at all.
    if [[ "$n" -eq 0 ]]; then
        findings+=".checks is empty; the report enumerated nothing, so its green would mean nothing"$'\n'
    fi

    # THE PER-ENTRY RULES ARE ONE jq PROGRAM, AND ITS FAILURE IS NOW LOUD.
    # jq aborts the WHOLE program on the FIRST type error -- `.checks` holding
    # a number or a string, an entry that is not an object -- printing nothing
    # on stdout and exiting 5. This used to read `2>/dev/null` with the status
    # unread, so `$bad` came back empty and `:87` scored that as "no per-entry
    # findings": every rule below evaporated on exactly the malformed input
    # they exist to catch, and the proxy certified the report. The status is
    # therefore READ and the diagnostic KEPT. Partial stdout from a program
    # that then aborted is deliberately DISCARDED rather than reported as if
    # it were the whole finding set, because a truncated finding set is the
    # same lie in a smaller font.
    local bad bad_rc bad_err
    bad_err="$(mktemp)"
    bad="$(printf '%s' "$json" | jq -r '
        (.checks // []) | to_entries[] |
        . as $e |
        [ (if ($e.value.name // "") == "" then "checks[\($e.key)] has no name" else empty end),
          (if ($e.value.value // "") == "" then "checks[\($e.key)] (\($e.value.name // "?")) has no value" else empty end),
          (if ($e.value.status // "") == "" then "checks[\($e.key)] (\($e.value.name // "?")) has no status" else empty end),
          (if (($e.value.status // "") | IN("ok","warn","fail","")) | not then "checks[\($e.key)] (\($e.value.name // "?")) has unknown status \"\($e.value.status)\"" else empty end),
          (if (($e.value.status // "") | IN("warn","fail")) and (($e.value.hint // "") == "") then "checks[\($e.key)] (\($e.value.name // "?")) is \($e.value.status) with no hint; a failing probe must name its fix" else empty end)
        ] | .[]' 2>"$bad_err")"
    bad_rc=$?
    if [[ $bad_rc -ne 0 ]]; then
        findings+="VACUOUS: the per-entry contract check could not run -- jq exited $bad_rc on this report, so NOTHING about checks[].{name,value,status,hint} was asserted. jq said: $(head -1 "$bad_err")"$'\n'
    elif [[ -n "$bad" ]]; then
        findings+="$bad"$'\n'
    fi
    rm -f "$bad_err"

    if [[ -n "$findings" ]]; then
        printf '%s' "$findings" | grep -v '^$'
        return 1
    fi
    return 0
}

selftest() {
    local fails=0 cases=0
    _c() {
        local want="$1" label="$2" body="$3"
        cases=$((cases + 1))
        local rc
        printf '%s' "$body" | validate_report linux >/dev/null 2>&1
        rc=$?
        if [[ $rc -eq $want ]]; then
            echo "${PROXY_GREEN}PASS:${PROXY_OFF} selftest $label"
        else
            echo "${PROXY_RED}FAIL:${PROXY_OFF} selftest $label: expected rc $want, got $rc" >&2
            fails=$((fails + 1))
        fi
    }
    local good='{"platform":"linux","arch":"amd64","backend":"kvm","checks":[{"name":"a","value":"v","status":"ok"},{"name":"b","value":"v","status":"fail","hint":"do the thing"}]}'
    # MUST NOT fire. A validator with only positive controls flags the whole tree.
    _c 0 "a well-formed report is accepted" "$good"
    _c 0 "a warn entry with a hint is accepted" '{"platform":"linux","backend":"kvm","checks":[{"name":"a","value":"v","status":"warn","hint":"h"}]}'
    # MUST fire.
    _c 1 "non-JSON stdout is rejected" 'not json at all'
    _c 1 "an empty .checks array is rejected" '{"platform":"linux","backend":"kvm","checks":[]}'
    _c 1 "a missing .backend is rejected" '{"platform":"linux","checks":[{"name":"a","value":"v","status":"ok"}]}'
    _c 1 "a platform that disagrees with the host is rejected" '{"platform":"windows","backend":"hyperv","checks":[{"name":"a","value":"v","status":"ok"}]}'
    _c 1 "an unknown status word is rejected" '{"platform":"linux","backend":"kvm","checks":[{"name":"a","value":"v","status":"okish"}]}'
    _c 1 "a fail entry with no hint is rejected" '{"platform":"linux","backend":"kvm","checks":[{"name":"a","value":"v","status":"fail"}]}'
    _c 1 "an entry with no name is rejected" '{"platform":"linux","backend":"kvm","checks":[{"value":"v","status":"ok"}]}'
    # The regression control for the jq-abort hole closed on 2026-09-10: this
    # case used to be ACCEPTED, because the type error emptied the finding set.
    _c 1 "a checks entry that is not an object is rejected, not silently skipped" '{"platform":"linux","backend":"kvm","checks":[1]}'

    if [[ $fails -gt 0 ]]; then
        echo "proxy ops-host-check selftest: $fails of $cases case(s) FAILED" >&2
        return 1
    fi
    echo "proxy ops-host-check selftest: $cases case(s) passed"
    proxy_lib_selftest
}

if [[ "${1:-}" == "--selftest" ]]; then
    if ! command -v jq >/dev/null 2>&1; then
        echo "proxy ops-host-check: jq is not on PATH, the selftest cannot run" >&2
        echo "  fix: sudo apt-get install -y jq" >&2
        exit 77
    fi
    selftest
    exit $?
fi

proxy_init ops-host-check "renet ops host check --json (ci-ops-test.yml 'Test: renet ops host check')"

RENET_BIN="${RENET_BINARY:-$ROOT_DIR/private/renet/bin/renet}"

proxy_need_cmd jq "sudo apt-get install -y jq"
proxy_need_exec "$RENET_BIN" ".ci/scripts/infra/build-renet.sh, or export RENET_BINARY=/path/to/renet"
proxy_preflight

case "$(uname -s)" in
    Linux) WANT_PLATFORM=linux ;;
    Darwin) WANT_PLATFORM=darwin ;;
    MINGW* | MSYS* | CYGWIN*) WANT_PLATFORM=windows ;;
    *) WANT_PLATFORM="" ;;
esac

OUT="$(mktemp)"
ERR="$(mktemp)"
trap 'rm -f "$OUT" "$ERR"' EXIT

"$RENET_BIN" ops host check --json >"$OUT" 2>"$ERR"
RC=$?

# CI writes `|| true` here. This proxy does not, which is the whole point.
if [[ $RC -eq 0 ]]; then
    proxy_pass "renet ops host check --json exited 0"
else
    proxy_fail "renet ops host check --json exited $RC (CI masks this with '|| true'; this proxy does not)"
    echo "  --- stderr ---" >&2
    cat "$ERR" >&2
fi

FINDINGS="$(validate_report "$WANT_PLATFORM" <"$OUT")"
if [[ -z "$FINDINGS" ]]; then
    proxy_pass "the report satisfies the JSON contract (.platform=$WANT_PLATFORM, .backend, .checks[].{name,value,status,hint})"
else
    proxy_fail "the report violates its JSON contract:"
    printf '  - %s\n' "$FINDINGS" >&2
fi

# PRINT THE SHAPE, not just the verdict. Host health is NOT asserted; the tally
# is here so a reader can see a collapse that "OK" would hide.
if command -v jq >/dev/null 2>&1 && jq -e . <"$OUT" >/dev/null 2>&1; then
    N=$(jq -r '(.checks // []) | length' <"$OUT")
    OKN=$(jq -r '[(.checks // [])[] | select(.status=="ok")] | length' <"$OUT")
    WARNN=$(jq -r '[(.checks // [])[] | select(.status=="warn")] | length' <"$OUT")
    FAILN=$(jq -r '[(.checks // [])[] | select(.status=="fail")] | length' <"$OUT")
    echo "proxy ops-host-check: $N probe(s) reported -- $OKN ok, $WARNN warn, $FAILN fail on this host"
    echo "  (host health is deliberately NOT a verdict here; only the contract is)"
    if [[ "$FAILN" -gt 0 ]]; then
        echo "  failing probes on this host, named so the debt is not forgotten:"
        jq -r '[(.checks // [])[] | select(.status=="fail")] | .[] | "    - \(.name): \(.value) -- \(.hint // "no hint")"' <"$OUT"
    fi
fi

proxy_finish
