"""RFC 6238 TOTP (HMAC-SHA1, 30 s step, 6 digits) from a base32 seed, computed in memory.

    from rediacc_ci.ops import totp
    code = totp.code(seed)                  # the current six-digit code
    code = totp.code(seed, at=1111111109)   # at a given Unix time

    PYTHONPATH=.ci python3 -m rediacc_ci.ops.totp

The module exists to be imported (`rediacc_ci.ops.login_bench` derives the bench login code with it). The command line runs the RFC 6238 Appendix B self-check and, when `REDIACC_BENCH_TOTP_SEED` is set, confirms that the seed decodes and yields a six-digit code. It prints only `ok` lines or a named error: never the seed, never a code.

A seed is accepted the way authenticator apps accept one: case-insensitive, with spaces and hyphens ignored and the `=` padding optional.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import os
import struct
import sys
import time

STEP = 30
DIGITS = 6
SEED_ENV = "REDIACC_BENCH_TOTP_SEED"

# RFC 6238 Appendix B, SHA-1 rows: the seed is the ASCII string "12345678901234567890"; the RFC prints 8-digit codes, and the 6-digit code is their last six digits.
RFC_SEED_ASCII = b"12345678901234567890"
RFC_VECTORS = (
    (59, "94287082"),
    (1111111109, "07081804"),
    (1111111111, "14050471"),
    (1234567890, "89005924"),
    (2000000000, "69279037"),
    (20000000000, "65353130"),
)


class TotpError(ValueError):
    """The seed is not usable. The message never carries the seed."""


def decode_seed(seed: str) -> bytes:
    """The raw key behind a base32 seed: case-insensitive, spaces and hyphens dropped, padding restored."""
    cleaned = "".join(seed.split()).replace("-", "").upper().rstrip("=")
    if not cleaned:
        raise TotpError("the TOTP seed is empty")
    padded = cleaned + "=" * (-len(cleaned) % 8)
    try:
        key = base64.b32decode(padded, casefold=False)
    except (binascii.Error, ValueError):
        raise TotpError("the TOTP seed is not valid base32") from None
    if not key:
        raise TotpError("the TOTP seed decodes to no bytes")
    return key


def hotp(key: bytes, counter: int, digits: int = DIGITS) -> str:
    """RFC 4226 HOTP over HMAC-SHA1 with dynamic truncation."""
    mac = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = mac[-1] & 0x0F
    value = struct.unpack(">I", mac[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(value % (10**digits)).zfill(digits)


def code_for_key(key: bytes, at: float | None = None, digits: int = DIGITS) -> str:
    """The TOTP code of a raw key at Unix time `at` (now when None)."""
    moment = time.time() if at is None else at
    return hotp(key, int(moment) // STEP, digits)


def code(seed: str, at: float | None = None) -> str:
    """The six-digit TOTP code of a base32 seed at Unix time `at` (now when None)."""
    return code_for_key(decode_seed(seed), at)


def self_check() -> None:
    """Raise AssertionError when the RFC 6238 SHA-1 vectors do not reproduce."""
    for at, expected in RFC_VECTORS:
        got = code_for_key(RFC_SEED_ASCII, at, digits=8)
        if got != expected:
            raise AssertionError("RFC 6238 vector at T=%d did not reproduce" % at)
        if code_for_key(RFC_SEED_ASCII, at) != expected[-6:]:
            raise AssertionError("RFC 6238 vector at T=%d did not truncate to six digits" % at)


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if args:
        if args[0] in ("-h", "--help"):
            print(__doc__.strip())
            return 0
        print("totp: takes no arguments", file=sys.stderr)
        return 2
    try:
        self_check()
    except AssertionError as exc:
        print("totp: self-check failed: %s" % exc, file=sys.stderr)
        return 1
    print("ok rfc6238-sha1-vectors")
    seed = os.environ.get(SEED_ENV) or ""
    if not seed:
        print("ok %s not set (seed check skipped)" % SEED_ENV)
        return 0
    try:
        current = code(seed)
    except TotpError as exc:
        print("totp: %s: %s" % (SEED_ENV, exc), file=sys.stderr)
        return 1
    if len(current) != DIGITS or not current.isdigit():
        print("totp: %s did not yield a six-digit code" % SEED_ENV, file=sys.stderr)
        return 1
    print("ok %s decodes" % SEED_ENV)
    return 0


if __name__ == "__main__":
    sys.exit(main())
