#!/usr/bin/env bash
# Compare shadow (Bitwarden) secrets against their GitHub org twins, by hash.
#
# WHY A SCRIPT. This body was inlined into 62 workflow steps across 21 files at
# 18 logic lines each; check:ci-workflows caps inline logic at 8 with no baseline,
# and it was right to. One script, one place to read, runnable locally.
#
# Required env (the workflow step is env wiring only):
#   SHADOW_NAMES              space-separated shadow names compared in this job
#   SHADOW_EXPECTED_MISMATCH  optional: names excused by .ci/config/shadow-expected-mismatches.json
#   GH_<name>                 the GitHub-side value, from ${{ secrets.<github-name> }}
#   BWS_<name>                the Bitwarden-side value, from the bws-secrets action
#
# Run locally:  SHADOW_NAMES="X" GH_X=... BWS_X=... .ci/scripts/ci/shadow-compare.sh
#
# Empty on EITHER side is fatal, even for an excused name: an absent GitHub secret
# and an empty Bitwarden value both hash to e3b0c442..., so without that arm two
# nothings compare EQUAL and the shadow reports "match" having verified nothing.
set -uo pipefail
rc=0
read -ra names <<<"$SHADOW_NAMES"
read -ra expected <<<"${SHADOW_EXPECTED_MISMATCH-}"
sha() { printf '%s' "${1-}" | { sha256sum 2>/dev/null || shasum -a 256; } | cut -d' ' -f1; }
is_expected() {
    local q="$1" e
    for e in ${expected+"${expected[@]}"}; do [ "$e" = "$q" ] && return 0; done
    return 1
}
# A name excused here must be one this job actually compares, or the entry
# sits forever excusing nothing.
for e in ${expected+"${expected[@]}"}; do
    case " $SHADOW_NAMES " in *" $e "*) ;; *)
        echo "shadow $e is in SHADOW_EXPECTED_MISMATCH but not in SHADOW_NAMES -- it excuses nothing here; delete it"
        rc=1
        ;;
    esac
done
for n in "${names[@]}"; do
    gv="GH_$n"
    bv="BWS_$n"
    # An ABSENT GitHub secret and an EMPTY Bitwarden value both hash to
    # e3b0c442..., so without this arm two nothings compare EQUAL and the
    # shadow reports "match" having verified nothing -- the exact defect
    # this whole run exists to catch. Empty on either side is a failure, and
    # stays fatal even for an excused name: an empty is a broken fetch, not
    # the known value drift the ledger describes.
    if [ -z "${!gv-}" ] || [ -z "${!bv-}" ]; then
        echo "shadow $n EMPTY (github=${!gv:+set}${!gv:-unset} bitwarden=${!bv:+set}${!bv:-unset}) -- nothing was compared"
        rc=1
    elif [ "$(sha "${!gv-}")" = "$(sha "${!bv-}")" ]; then
        # An excused name that MATCHES means the drift is gone, so the excuse must
        # go too, or exemptions outlive the reason for them.
        if is_expected "$n"; then
            echo "shadow $n matches, but is still excused by SHADOW_EXPECTED_MISMATCH -- the drift is resolved; delete it here and in shadow-expected-mismatches.json"
            rc=1
        else echo "shadow $n match"; fi
    else
        # WHICH KIND OF MISMATCH, said without printing a byte of either value.
        # RELEASE_GPG_PRIVATE_KEY mismatched on run 33904687989 while the key it
        # carries was PROVEN identical on both sides (same fingerprints as the
        # committed public key; releases CD signed with the GitHub copy verify
        # against it). The only remaining difference was bytes -- an armored
        # block stored with or without its trailing newline -- and the verdict
        # line could not say so, which turned a one-line normalisation into an
        # operator ticket. A sha of each side would be reversible for a short
        # secret, so the diagnostic is limited to: equal once trailing
        # whitespace is stripped, and whether each side ends in a newline.
        # Neither is secret material. The verdict is unchanged either way; a
        # whitespace-only drift is still a drift, because the same value fed to
        # a header or a URL would break on that byte.
        gs="${!gv-}"
        bs="${!bv-}"
        while [ "${gs: -1}" = $'\n' ] || [ "${gs: -1}" = $'\r' ]; do gs="${gs%?}"; done
        while [ "${bs: -1}" = $'\n' ] || [ "${bs: -1}" = $'\r' ]; do bs="${bs%?}"; done
        if [ "$(sha "$gs")" = "$(sha "$bs")" ]; then
            kind="whitespace-only: equal once trailing newlines are stripped (github ends with newline: $([ "${!gv: -1}" = $'\n' ] && echo yes || echo no), bitwarden: $([ "${!bv: -1}" = $'\n' ] && echo yes || echo no))"
        else
            kind="content differs"
        fi
        if is_expected "$n"; then
            # Known drift, recorded with its evidence and its door. It does not stop
            # this job (the ledger is .ci/config/shadow-expected-mismatches.json):
            # blocking on it took the CI watchdog down on 2026-09-03 without
            # it monitoring anything, and the finding is already the operator's.
            echo "shadow $n MISMATCH (EXPECTED -- shadow-expected-mismatches.json, operator-only) [$kind]"
        else
            echo "shadow $n MISMATCH [$kind]"
            rc=1
        fi
    fi
done
exit "$rc"
