#!/usr/bin/env bash
# Rewrite an armored GPG private key into CANONICAL armor, in place.
#
# WHY THIS EXISTS, and why it is its own file rather than six lines inline.
# gpg parses armored keys leniently; nfpm decodes them with Go's
# openpgp.ReadArmoredKeyRing, which does not. On 2026-09-05 run 33990640584 died
# with
#
#     signing error: armored detach sign: decoding armored PGP keyring:
#     openpgp: invalid data: armor invalid
#
# one line AFTER "Signing key matches the published public key" -- the gpg-based
# fingerprint check had already passed on the same bytes.
#
# THE CAUSE, reproduced rather than guessed. A GPG private key does not fit one
# Bitwarden field, so it is stored as two items (`gpg-private.asc - 1` and `- 2`).
# Part 1 carries no trailing newline and part 2 has no armor header, so
# concatenating them WELDS part 1's last base64 line onto part 2's first. Measured
# against x/crypto v0.56.0 with a throwaway key: gpg reads the welded block fine,
# Go answers `armor invalid` verbatim, and joining with a newline is accepted.
#
# Importing and re-exporting through gpg repairs EVERY variant gpg can read, and
# gpg being able to read it is exactly what the caller's fingerprint check proves.
# The re-export KEEPS the key passphrase-protected (verified: signing with the
# right passphrase succeeds, the wrong one fails with "private key checksum
# failure"), so the caller's NFPM_*_PASSPHRASE stays correct.
#
# It lives here so check:ci-release-key-canonical can exercise the real thing with
# a throwaway key, instead of a copy that can drift from what the build runs.
#
# IT ALSO REPORTS WHETHER REPAIR WAS NEEDED, and that matters more than it looks.
# A repair that happens silently on every build is a workaround that never ends: the
# stored Secrets Manager value stays welded forever because nothing ever says so. The
# exit code distinguishes the two cases so the caller can be loud about the second.
#
# Usage: canonicalise-gpg-key.sh <key-file> [passphrase]
# Exit 0  the key was ALREADY canonical; the file is unchanged in substance
#      10 the key was REPAIRED -- the stored value is malformed and should be fixed
#         at source, not left to this script
#      1  gpg could not read the key at all
set -uo pipefail

KEY_FILE="${1:?usage: canonicalise-gpg-key.sh <key-file> [passphrase]}"
PASSPHRASE="${2-}"

[[ -s "$KEY_FILE" ]] || {
    echo "canonicalise-gpg-key: $KEY_FILE is missing or empty" >&2
    exit 1
}
command -v gpg >/dev/null 2>&1 || {
    echo "canonicalise-gpg-key: gpg is not installed" >&2
    exit 1
}

HOME_DIR="$(mktemp -d)"
chmod 700 "$HOME_DIR"
trap 'rm -rf "$HOME_DIR"' EXIT

if ! GNUPGHOME="$HOME_DIR" gpg --batch --pinentry-mode loopback \
    --passphrase "$PASSPHRASE" --import "$KEY_FILE" 2>/dev/null; then
    echo "canonicalise-gpg-key: gpg could not import the key" >&2
    exit 1
fi

FPR="$(GNUPGHOME="$HOME_DIR" gpg --list-secret-keys --with-colons 2>/dev/null |
    awk -F: '$1=="fpr"{print $10; exit}')"
[[ -n "$FPR" ]] || {
    echo "canonicalise-gpg-key: no secret key after import" >&2
    exit 1
}

OUT="$HOME_DIR/canonical.asc"
if ! GNUPGHOME="$HOME_DIR" gpg --batch --pinentry-mode loopback \
    --passphrase "$PASSPHRASE" --armor --export-secret-keys "$FPR" >"$OUT" 2>/dev/null ||
    [[ ! -s "$OUT" ]]; then
    echo "canonicalise-gpg-key: re-export produced nothing" >&2
    exit 1
fi

# JUDGE THE INPUT, NOT A DIFF AGAINST THE OUTPUT.
#
# The first version compared the input's base64 body to the re-exported one and
# called any difference a repair. That can NEVER be right: gpg re-encrypts a
# passphrase-protected secret key with fresh salt on every export, so the body
# differs every time even for a byte-identical key, and a canonical key reported
# itself repaired.
#
# The weld has a structural signature instead: RFC 4880 wraps armor at 64 columns,
# and joining two halves without a newline produces one far longer body line. That
# is exactly the difference between the block gpg accepts and the one Go rejects.
if [[ "$(awk 'BEGIN{m=0} !/-----/ { if (length($0) > m) m = length($0) } END { print m+0 }' "$KEY_FILE")" -le 64 ]]; then
    REPAIRED=0
else
    REPAIRED=1
fi

cat "$OUT" >"$KEY_FILE"
[[ "$REPAIRED" == "1" ]] && exit 10
exit 0
