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
# Usage: canonicalise-gpg-key.sh <key-file> [passphrase]
# Exit 0 on success (file rewritten), 1 if gpg could not read the key at all.
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

cat "$OUT" >"$KEY_FILE"
