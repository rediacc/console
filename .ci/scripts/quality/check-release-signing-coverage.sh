#!/usr/bin/env bash
# EVERY RELEASE PACKAGE FORMAT MUST BE SIGNED, OR BE DECLARED UNSIGNED ON PURPOSE.
#
# WHY THIS EXISTS. On 2026-09-05 a deb shipped UNSIGNED and green: the signing
# setup was guarded by `[[ -n "${RELEASE_GPG_PRIVATE_KEY:-}" ]]`, the org secret
# behind it had been deleted, and an empty value is indistinguishable from "no
# signing wanted". That was fixed for deb and rpm. A class sweep the next day found
# the SAME shape one branch over in apk, which had shipped unsigned for the same
# reason and was fixed reactively too.
#
# Fixing formats one at a time as they are noticed is the actual defect. This gate
# asks the structural question instead: build-linux-pkg.sh accepts N formats, and
# EACH one must either refuse to ship unsigned when the caller demands signing, or
# appear below as a deliberate, reasoned exception. A fifth format added tomorrow
# fails here before it can ship unsigned.
#
# WHAT IT CANNOT DO: it does not verify a real signature on a real artifact -- that
# needs the release key, which is a secret and is deliberately not available to a
# quality job. It checks that the REFUSAL exists. `check:ci-release-key-canonical`
# covers the key's usability, and test-linux-packages.sh signs real packages in CI.
#
# EVERY EXEMPTION BELOW STATES A TESTED CONSTRAINT, not a guess, because the first
# archlinux reason was a guess and it was WRONG: it said "no signature block in
# nfpm.yaml", which reads as an omission someone could fix by adding one. Adding one
# fails at config load. The two constraints are different in kind and the difference
# was measured, not reasoned:
#   archlinux  nfpm CANNOT sign it -- `field signature not found in type nfpm.ArchLinux`
#   apk        nfpm CAN sign it; only the key is absent (built both ways to check)
# A reason that has not been run is a reason that can be wrong for months.
set -uo pipefail
ROOT="${SIGNING_COVERAGE_ROOT:-$(git rev-parse --show-toplevel 2>/dev/null || echo .)}"
BUILDER="${SIGNING_COVERAGE_BUILDER:-$ROOT/.ci/scripts/build/build-linux-pkg.sh}"

# Formats that ship UNSIGNED on purpose. Each needs a reason, and the gate refuses
# an entry whose format IS guarded, so an exemption cannot outlive its cause.
#
#   archlinux -- nfpm's archlinux packager is configured in .ci/config/nfpm.yaml
#     with no `signature` block, and never has been. It is listed here to make that
#     VISIBLE rather than to bless it: pacman verifies signatures only when a repo
#     provides them, so today an Arch user installs an unverified package. Signing
#     it needs a key decision that belongs to the operator, and is tracked as a
#     finding rather than silently allowlisted.
declare -A UNSIGNED_ON_PURPOSE=(
    [archlinux]="nfpm CANNOT sign archlinux at all -- adding a signature block fails at config load with 'field signature not found in type nfpm.ArchLinux' (measured against the pinned nfpm, 2026-09-06). Signing it needs a detached .sig produced outside nfpm and published beside the package"
    [apk]="the KEY is missing, not the capability -- VERIFIED 2026-09-06 by building both ways: with an RSA key the apk carries a .SIGN.RSA.*.rsa.pub entry, without one it carries none. APK_RSA_PRIVATE_KEY is set by nothing here and is absent from .ci/config/bws-secret-map.json, so nfpm.yaml's apk signature block reads an env var never populated. Mint an RSA key and this exemption goes"
)

MIN_FORMATS=4

fails=0
n=0
_c() {
    n=$((n + 1))
    if [[ "$2" == "$3" ]]; then echo "  ok    $1"; else
        fails=$((fails + 1))
        echo "  FAIL  $1 (got '$2' want '$3')" >&2
    fi
}

# The formats the builder ACCEPTS, read from its own validation case rather than
# duplicated here -- a list that can drift is a list that will.
formats_of() {
    sed -n 's/^[[:space:]]*\([a-z |]*\))[[:space:]]*;;[[:space:]]*$/\1/p' "$1" |
        head -1 | tr -d ' ' | tr '|' '\n' | grep -v '^$'
}
# A format REFUSES to ship unsigned when ITS OWN case arm contains the guard.
#
# Reading "is RELEASE_SIGNING_REQUIRED anywhere after the arm" is what the first
# draft did, and it was wrong in both directions: the guard sits INSIDE the arm, so
# the arm line is read before anything arms, and a later arm inherits an earlier
# arm's guard. Scope to the arm body, `<formats>)` through `;;`.
guarded_in() {
    awk -v fmt="$1" '
        /^[[:space:]]*[a-z][a-z |]*\)[[:space:]]*$/ {
            arm = $0
            sub(/\)[[:space:]]*$/, "", arm)
            gsub(/[[:space:]]/, "", arm)
            inarm = 0
            m = split(arm, parts, "|")
            for (i = 1; i <= m; i++) if (parts[i] == fmt) inarm = 1
            next
        }
        /^[[:space:]]*;;[[:space:]]*$/ { inarm = 0; next }
        inarm && /RELEASE_SIGNING_REQUIRED/ { found = 1 }
        END { print (found ? "yes" : "no") }
    ' "$2"
}

[[ -f "$BUILDER" ]] || {
    echo "✗ $BUILDER not found -- nothing was verified" >&2
    exit 1
}
# `mapfile` is bash4-only and ubuntu-slim does not carry it; check:ci-shell-commands
# refuses it, so read the list the portable way.
FORMATS=()
while IFS= read -r _fmt; do
    [[ -n "$_fmt" ]] && FORMATS+=("$_fmt")
done < <(formats_of "$BUILDER")

# ANTI-VACUITY. A sed that stops matching would yield an empty list, and a loop
# over nothing passes. The builder documents four formats; a floor at four catches
# a broken parse without firing on an addition.
_c "the builder's format list parses" "$((${#FORMATS[@]} >= MIN_FORMATS ? 1 : 0))" "1"
if ((${#FORMATS[@]} < MIN_FORMATS)); then
    echo "✗ VACUOUS: parsed ${#FORMATS[@]} format(s) from $BUILDER, floor is $MIN_FORMATS." >&2
    echo "  The validation case did not parse, so this gate verified nothing." >&2
    exit 1
fi

for f in "${FORMATS[@]}"; do
    g="$(guarded_in "$f" "$BUILDER")"
    if [[ -n "${UNSIGNED_ON_PURPOSE[$f]:-}" ]]; then
        # A stale exemption is worse than none: it hides a format that got fixed.
        _c "CONTROL: exemption for '$f' still describes an UNguarded format" "$g" "no"
    else
        _c "'$f' refuses to ship unsigned when signing is required" "$g" "yes"
    fi
done

# Every exemption must name a format the builder actually accepts, or it excuses
# nothing and sits forever looking like coverage.
for f in "${!UNSIGNED_ON_PURPOSE[@]}"; do
    hit=no
    for g in "${FORMATS[@]}"; do [[ "$g" == "$f" ]] && hit=yes; done
    _c "exemption '$f' names a real format" "$hit" "yes"
    _c "exemption '$f' carries a reason" "$([[ ${#UNSIGNED_ON_PURPOSE[$f]} -gt 30 ]] && echo yes || echo no)" "yes"
done

if ((n < 6)); then
    echo "FAIL  only $n control(s) ran; the battery is not being executed as written" >&2
    fails=$((fails + 1))
fi
if ((fails)); then
    echo "✗ release signing coverage: $fails of $n control(s) failed" >&2
    echo "  A format that neither refuses nor is declared unsigned ships unverified." >&2
    exit 1
fi
echo "✓ release signing coverage: ${#FORMATS[@]} format(s), $n control(s) passed (${#UNSIGNED_ON_PURPOSE[@]} declared unsigned)"
