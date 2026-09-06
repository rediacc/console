#!/usr/bin/env bash
# THE RELEASE SIGNING KEY MUST REACH nfpm AS CANONICAL ARMOR.
#
# WHY THIS EXISTS. On 2026-09-05 a release build failed at
# `Stage Artifacts / Build Linux packages` with
#
#     signing error: armored detach sign: decoding armored PGP keyring:
#     openpgp: invalid data: armor invalid
#
# one line AFTER "Signing key matches the published public key". gpg had read the
# very bytes nfpm then rejected. The cause: the key is stored as two Bitwarden
# items whose halves were joined without a newline, welding two base64 lines into
# one over-long line. gpg tolerates that; Go's armor decoder does not.
#
# WHAT THIS GATE CAN AND CANNOT DO, said plainly so its green is not read as more
# than it is. It CANNOT check the real RELEASE_GPG_PRIVATE_KEY: that value is a
# secret, quality jobs do not have it and must not, and a gate that needs a
# credential to run is a gate that gets skipped. So it checks the thing that IS
# checkable offline -- that the canonicaliser the build depends on still repairs
# the defect shape -- using a key generated here and thrown away. If the stored
# value is welded again tomorrow, the BUILD repairs it and this gate proves the
# repair still works.
#
# THE PROXY FOR "Go would reject it", and why it is honest. This runs without Go,
# so it cannot invoke openpgp.ReadArmoredKeyRing. It asserts the structural
# signature instead: RFC 4880 armor wraps base64 at 64 columns, the weld produces
# one line far longer, and that over-long line is precisely what differs between
# the block gpg accepts and the block Go rejects. The causal link was measured
# against x/crypto v0.56.0 on 2026-09-05 -- welded REJECT, newline-joined ACCEPT.
set -uo pipefail
ROOT="${RELEASE_KEY_ROOT:-$(git rev-parse --show-toplevel 2>/dev/null || echo .)}"
CANON="$ROOT/.ci/scripts/build/canonicalise-gpg-key.sh"

fails=0
n=0
_c() {
    n=$((n + 1))
    if [[ "$2" == "$3" ]]; then echo "  ok    $1"; else
        fails=$((fails + 1))
        echo "  FAIL  $1 (got '$2' want '$3')" >&2
    fi
}

[[ -x "$CANON" ]] || {
    echo "✗ $CANON is missing or not executable -- the build depends on it" >&2
    exit 1
}
command -v gpg >/dev/null 2>&1 || {
    echo "✗ gpg is not installed, so nothing here was verified (CI installs it; locally: sudo apt-get install -y gnupg)" >&2
    exit 1
}

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
export GNUPGHOME="$TMP/gnupg"
mkdir -p "$GNUPGHOME"
chmod 700 "$GNUPGHOME"

PASS='gate-throwaway-passphrase'
gpg --batch --pinentry-mode loopback --passphrase "$PASS" \
    --quick-generate-key "Release Key Gate <gate@example.invalid>" rsa2048 sign never >/dev/null 2>&1
FPR="$(gpg --list-secret-keys --with-colons 2>/dev/null | awk -F: '$1=="fpr"{print $10; exit}')"
if [[ -z "$FPR" ]]; then
    echo "✗ could not generate a throwaway key, so NOTHING was verified" >&2
    exit 1
fi
gpg --batch --pinentry-mode loopback --passphrase "$PASS" --armor \
    --export-secret-keys "$FPR" >"$TMP/good.asc" 2>/dev/null

# longest line of the armor BODY (header/footer excluded)
longest() { grep -v -- '-----' "$1" | awk '{ if (length($0) > m) m = length($0) } END { print m+0 }'; }

_c "a canonical key wraps at 64 columns" "$(($(longest "$TMP/good.asc") <= 64 ? 1 : 0))" "1"

# THE DEFECT SHAPE: weld two adjacent body lines, exactly as `part1 + part2` does
# when part1 carries no trailing newline. Content identical, one line break gone.
awk 'BEGIN{done=0}
     /^-----/ { print; next }
     (!done && NR>3) { prev=$0; if ((getline nxt) > 0) { printf "%s%s\n", prev, nxt; done=1; next } else { print prev; next } }
     { print }' "$TMP/good.asc" >"$TMP/welded.asc"

_c "CONTROL: the welded key really is malformed (an over-long body line)" \
    "$(($(longest "$TMP/welded.asc") > 64 ? 1 : 0))" "1"
# The precondition the whole repair rests on, and the reason the build's own
# fingerprint check could not catch this: gpg reads the welded block happily.
_c "CONTROL: gpg still reads the welded key, which is why it slipped through" \
    "$(gpg --show-keys --with-colons "$TMP/welded.asc" 2>/dev/null | awk -F: '$1=="fpr"{print 1; exit}')" "1"

cp "$TMP/welded.asc" "$TMP/repaired.asc"
# 0 = was already canonical, 10 = REPAIRED. Both are success here; only 1 is failure.
# Treating any non-zero as failure is what this gate did before the repair signal
# existed, and it turned a working repair into "canonicaliser-failed".
canon_rc=0
"$CANON" "$TMP/repaired.asc" "$PASS" >/dev/null 2>&1 || canon_rc=$?
_c "a welded key reports REPAIRED, not 'already fine'" "$canon_rc" "10"
# CONTROL: an already-canonical key must NOT claim a repair, or the signal is noise
# and the next person mutes it.
cp "$TMP/good.asc" "$TMP/good-probe.asc"
good_rc=0
"$CANON" "$TMP/good-probe.asc" "$PASS" >/dev/null 2>&1 || good_rc=$?
_c "CONTROL: an already-canonical key reports 0, not 10" "$good_rc" "0"
# The caller runs under `set -e`, so a BARE call to a script exiting 10 aborts the
# whole build -- which is exactly the production case the signal exists for.
# Count CODE, not prose: the same idiom appears in the comment that explains it, and
# a naive grep -c reads 2 and fails on a correct file.
_c "build-linux-pkg.sh guards that non-zero exit" \
    "$(grep -v '^\s*#' "$ROOT/.ci/scripts/build/build-linux-pkg.sh" | grep -c '|| canon_rc=\$?')" "1"
if [[ "$canon_rc" == "0" || "$canon_rc" == "10" ]]; then
    _c "the canonicaliser repairs a welded key" \
        "$(($(longest "$TMP/repaired.asc") <= 64 ? 1 : 0))" "1"
    _c "...and the repaired key is still the SAME key" \
        "$(gpg --show-keys --with-colons "$TMP/repaired.asc" 2>/dev/null | awk -F: '$1=="fpr"{print $10; exit}')" "$FPR"
    # If the re-export dropped the passphrase, nfpm's NFPM_*_PASSPHRASE would be
    # wrong and signing would fail with a confusing error somewhere else.
    _c "...and it is still passphrase-protected" \
        "$(grep -c 'BEGIN PGP PRIVATE KEY BLOCK' "$TMP/repaired.asc")" "1"
    # IMPORT IS NOT THE TEST. gpg imports a protected secret key without the
    # passphrase -- it stores it still encrypted -- so an import that succeeds
    # proves nothing about protection. Signing is what needs the passphrase, and
    # it is what nfpm does, so that is what is asserted here.
    _sign_with() {
        local pass="$1" home="$TMP/sign-$2"
        mkdir -p "$home"
        chmod 700 "$home"
        GNUPGHOME="$home" gpg --batch --pinentry-mode loopback --passphrase "$pass" \
            --import "$TMP/repaired.asc" >/dev/null 2>&1
        echo hi >"$home/msg"
        if GNUPGHOME="$home" gpg --batch --pinentry-mode loopback --passphrase "$pass" \
            --armor --detach-sign --output "$home/sig" "$home/msg" >/dev/null 2>&1; then
            echo signed
        else echo refused; fi
    }
    _c "...and it can still SIGN with the right passphrase" "$(_sign_with "$PASS" right)" "signed"
    # CONTROL: without this, a re-export that stripped the passphrase would pass the
    # assertion above while having silently removed the protection.
    _c "CONTROL: and it REFUSES to sign with the wrong one" "$(_sign_with "wrong-pass" wrong)" "refused"
else
    _c "the canonicaliser repairs a welded key" "canonicaliser-failed" "1"
fi

# The build must actually CALL it, or this gate proves a function nothing uses.
_c "build-linux-pkg.sh calls the canonicaliser" \
    "$(grep -c 'canonicalise-gpg-key.sh' "$ROOT/.ci/scripts/build/build-linux-pkg.sh")" "1"

if ((n < 8)); then
    echo "FAIL  only $n control(s) ran; the battery is not being executed as written" >&2
    fails=$((fails + 1))
fi
if ((fails)); then
    echo "✗ release key canonicalisation: $fails of $n control(s) failed" >&2
    exit 1
fi
echo "✓ release key canonicalisation: $n control(s) passed (throwaway key; the real one is a secret and is deliberately out of scope)"
