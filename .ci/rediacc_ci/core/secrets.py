"""Redaction and presence-checking. Nothing here prints a value.

WHAT THIS IS FOR. Four separate mechanisms in this repository already exist to keep a credential out of a log, and every one of them is partial:

    .ci/lib/bws-env.sh:16-24        a stated rule ("It never PRINTS a value.
                                    Names, counts and errors only") with no
                                    helper behind it, so each caller re-obeys it
    .ci/breakpoint/lib/breakpoint-common.sh:421-425
                                    bp_gha_mask, which works only inside GitHub
                                    Actions and only for output written AFTER it
    rdc.sh:240-245                  a hand-written grep that takes two values
                                    out of a file rather than sourcing forty-nine
    .ci/config/bws-token-expiry.json  a sha256 fingerprint of the IDENTIFIER
                                    half of a token, "never the secret"

None of them helps a Python gate that has a string in hand and is about to print it. This module is that missing piece, and it is deliberately the boring half of the problem: it does not find secrets, it hides ones it is told about and answers questions about ones it must not echo.

--------------------------------------------------------------------------
THE NAMING RULE, WHICH IS THE WHOLE INTERFACE
--------------------------------------------------------------------------
NO FUNCTION IN THIS MODULE RETURNS A SECRET VALUE. `redact` returns text with values removed, `presence` returns the word "present" or "absent", `report` returns lines of names, and `fingerprint` returns a digest. A future function that does hand back a value must say so in its name, the way `rediacc_ci.core.env.unredacted_value` does -- so that a reviewer reading a call site, with
no memory of this file, can still see it happening.

`redact` is the DEFAULT PATH and the others are the exceptions. A caller with arbitrary text and a set of values reaches for `redact`; a caller that wants to say something about a value it is not allowed to show reaches for `presence` or `fingerprint`.

--------------------------------------------------------------------------
WHY `::add-mask::` IS NOT ENOUGH, WITH A RECEIPT
--------------------------------------------------------------------------
`.ci/breakpoint/scripts/publish-endpoints.sh:52-63` records what happened when masking was the only defence. GitHub prints a step's `env:` block into the log BEFORE the step's script runs, so a URL passed through `env:` was published about four seconds before `::add-mask::` could register it, and add-mask "only redacts occurrences AFTER it registers". Observed in run 30254567365 on
a PUBLIC repository: the URL sat in cleartext at log line 1700.

The lesson carried into this module is that redaction is a LAST line, not a first one. `redact` exists for output this process is about to emit, where it runs before the bytes leave. It cannot help with anything already written, and it is not an excuse to put a value somewhere it does not belong.

--------------------------------------------------------------------------
WHY THE COMMAND LINE TAKES NAMES AND NEVER VALUES
--------------------------------------------------------------------------
Every argument to every process on this host is world-readable through `/proc/<pid>/cmdline` for as long as the process lives, and it lands in the shell history of anyone who typed it. So the argv dispatch at the bottom takes NAMES, reads the values out of the environment itself, and never accepts one as an argument. That is also why there is no `redact --value <secret>` verb: the
convenient form is the leaking one.

--------------------------------------------------------------------------
WHY AN EMPTY VALUE IS ABSENT
--------------------------------------------------------------------------
Taken unchanged from `.ci/lib/bws-env.sh:100-104`, in its own words: "An empty value is treated as ABSENT on purpose: zod strips an unknown key and sm-action exports \"\" without complaint, so a blank ships a broken feature that still returns 200." `rediacc_ci.core.env` applies the same ruling to precedence, and they are the same ruling on purpose.

--------------------------------------------------------------------------
COMMAND-LINE ENTRY POINT
--------------------------------------------------------------------------
    python3 -m rediacc_ci.core.secrets redact <NAME>... < text
        stdin to stdout with the environment's value of each NAME masked.

    python3 -m rediacc_ci.core.secrets report <NAME>...
        one "<NAME> present" or "<NAME> absent" line per name. Exit 1 when any
        name is absent, so a caller can gate on it.

    python3 -m rediacc_ci.core.secrets fingerprint <NAME>
        the digest of that name's value. Exit 1 when absent.
"""

from __future__ import annotations

import hashlib
import os
import sys
from collections.abc import Iterable, Mapping

# What a masked value is replaced BY. Three asterisks matches what a GitHub Actions runner substitutes for a registered mask, so a log that has been through both this and the runner reads the same way throughout.
MASK = "***"

# How many hex digits of the sha256 a fingerprint carries. Not chosen here: `rediacc_ci.core.bws_env.client_fingerprint` already fingerprints a token's client id as `hashlib.sha256(client_id.encode()).hexdigest()[:16]`, and `scripts/dev/bws-rotate.py` compares two of its results to refuse a rotation that installs the credential already in place.
# A second width would mean the two could never be compared. That computation used to live at `scripts/ops/bws-map-refresh.py:67` beside a hand-written expiry file that stored the digests; both were deleted on 2026-09-23 with the reader that read them, and the computation survived because it was the one part of that reader bound to the LIVE token rather than to a date.
FINGERPRINT_HEX_DIGITS = 16

PRESENT = "present"
ABSENT = "absent"

# Name segments that make a name a secret. Matched against the `_`-separated SEGMENTS of the name and never as substrings.
#
# THE COLLISIONS THAT MAKES A DIFFERENCE TO, named because the first draft of this comment named one ("WEBAUTHN_RP_ID contains AUTH") that is not a marker at all, and a planted substring-matching defect went undetected as a result: KEY is inside KEYBOARD, KEYCHAIN, MONKEY SIG is inside DESIGN, ASSIGNMENT Under substring matching DESIGN_DOC_URL and KEYBOARD_LAYOUT are both secrets.
# (WEBAUTHN_RP_ID is not classified for a different reason: the `_ID` rule.)
_STRONG = frozenset(
    {
        "SECRET",
        "SECRETS",
        "PASSWORD",
        "PASSWD",
        "PASSPHRASE",
        "PRIVATE",
        "CREDENTIAL",
        "CREDENTIALS",
        "TOKEN",
        "JWT",
    }
)

# The weaker markers. A name carrying one of these is a secret UNLESS the name is an identifier (see `looks_secret`), because `..._ACCESS_KEY_ID` is the public half of a credential pair and `..._ACCESS_KEY` is the private half.
_WEAK = frozenset({"KEY", "SALT", "SEED", "SIGNATURE", "SIG"})

# The one segment that overrides everything. ACCOUNT_ED25519_PUBLIC_KEY is published: .ci/lib/local-common.sh:814 reads it out of a file specifically to hand it to a build, and rdc.sh:248 extracts ACCOUNT_X25519_PUBLIC_KEY into a config that is written to disk in cleartext.
_PUBLIC = frozenset({"PUBLIC", "PUB"})


def looks_secret(name: str) -> bool:
    """Whether a VARIABLE NAME denotes something that must not be printed.

    A HEURISTIC OVER NAMES, and never a substitute for `redact`. It cannot see that `STRIPE_E2E_WEBHOOK_SECRET` is a fixture (`.ci/lib/account.sh:290` says so in a comment this function cannot read) and it cannot see that a variable called `NOTES` is holding a pasted password. It exists to decide which of a mapping's values to feed to `redact`, where a false positive costs a masked
    port number and a false negative costs a credential -- so it leans conservative, on purpose.
    """
    segments = set(name.upper().split("_"))
    if segments & _PUBLIC:
        return False
    if segments & _STRONG:
        return True
    if name.upper().endswith("_ID"):
        # The identifier half of a pair. `rediacc_ci.core.bws_env.client_fingerprint` rules on exactly this shape: the client id of a BWS token is the IDENTIFIER half and never the secret, which is why fingerprinting it is publishable in a tracked file.
        return False
    return bool(segments & _WEAK)


def presence(value: str | None) -> str:
    """The word "present" or the word "absent". Never the value, never its length.

    Length is withheld deliberately. It is the one property that looks harmless and is not: it narrows a brute force, and for a short value it is most of the answer. `fingerprint` is the escape hatch for when a caller genuinely needs to tell two values apart.
    """
    return PRESENT if value else ABSENT


def is_present(value: str | None) -> bool:
    """`presence` as a boolean, for a caller that is branching rather than printing."""
    return bool(value)


def report(
    source: Mapping[str, str | None],
    names: Iterable[str] | None = None,
) -> list[str]:
    """One "<NAME> <present|absent>" line per name, sorted.

    `names` defaults to the mapping's own keys. Passing it explicitly is the useful case: a caller checking that eight required variables arrived wants a line for the two that did NOT, and a mapping that is missing a key entirely would otherwise produce no line at all -- silence where the failure is.
    """
    wanted = sorted(source) if names is None else sorted(names)
    return ["%s %s" % (name, presence(source.get(name))) for name in wanted]


def missing(source: Mapping[str, str | None], names: Iterable[str]) -> list[str]:
    """The sorted NAMES that are absent or empty. The actionable half of `report`."""
    return sorted(name for name in names if not source.get(name))


def fingerprint(value: str) -> str:
    """A stable short digest of a value, for telling two values apart.

    ONLY SAFE FOR HIGH-ENTROPY VALUES, and that limit is real rather than ceremonial: sha256 is fast, so the digest of a human-chosen password is recoverable from a wordlist in seconds. The corpus this matches (`rediacc_ci.core.bws_env.client_fingerprint`) fingerprints a machine-account client id, which is a random identifier. Do not reach for this to describe a passphrase.

    An empty value returns "" rather than the digest of the empty string. Otherwise every absent variable in a report would carry the same conspicuous constant, which reads as a value and is not one.
    """
    if not value:
        return ""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:FINGERPRINT_HEX_DIGITS]


def redact(text: str, values: Iterable[str] | Mapping[str, str | None]) -> str:
    """`text` with every occurrence of every value replaced by MASK.

    THE DEFAULT PATH. Accepts either the values themselves or a name-to-value mapping, in which case only the VALUES are masked -- names stay legible, because a log that has had its variable names removed is a log nobody can act on, and the names were never the secret.

    LONGEST FIRST, which is not cosmetic. With values "abc" and "abcdef" and the shorter one applied first, "abcdef" becomes "***def" and the tail of the longer secret survives in the output, masked in a way that looks masked. Sorting by descending length removes that case entirely; the secondary sort is lexicographic so the result does not depend on set iteration order.

    A value is also masked in its whitespace-stripped form. An env-file value and the same value read from a command's stdout routinely differ by one trailing newline, and a redactor that misses on that difference is a redactor that fails exactly when two sources are being compared.

    EMPTY VALUES ARE SKIPPED. "" occurs at every position in every string, so including it would insert a mask between every pair of characters and destroy the text while appearing to protect it. That is also why an absent variable, which `presence` calls absent, cannot be redacted: there is nothing there to hide.
    """
    raw = values.values() if isinstance(values, Mapping) else values
    candidates: set[str] = set()
    for value in raw:
        if not value:
            continue
        candidates.add(value)
        stripped = value.strip()
        if stripped:
            candidates.add(stripped)
    out = text
    for value in sorted(candidates, key=lambda item: (-len(item), item)):
        out = out.replace(value, MASK)
    return out


def redact_env(
    text: str,
    environ: Mapping[str, str] | None = None,
    names: Iterable[str] | None = None,
) -> str:
    """`redact` over the environment, restricted to names `looks_secret` accepts.

    The convenience wrapper a gate wants before printing a captured command's output. `names` narrows it further; without it, every secret-looking name in the environment is masked, which is the conservative default for a program that is about to print bytes it did not produce.
    """
    env = os.environ if environ is None else environ
    wanted = list(env) if names is None else list(names)
    return redact(text, {name: env.get(name) for name in wanted if looks_secret(name)})


# ---------------------------------------------------------------------------
# argv dispatch -- names only; see the module docstring
# ---------------------------------------------------------------------------


def main(argv: list[str]) -> int:
    if not argv:
        print("usage: python3 -m rediacc_ci.core.secrets <verb> [NAME...]", file=sys.stderr)
        return 2
    verb, names = argv[0], argv[1:]

    if verb == "redact":
        # stdin to stdout. The values come from this process's own environment, so no secret ever appears in argv.
        sys.stdout.write(redact_env(sys.stdin.read(), names=names or None))
        return 0
    if verb == "report":
        if not names:
            print("secrets: report needs at least one NAME", file=sys.stderr)
            return 2
        source = {name: os.environ.get(name) for name in names}
        for line in report(source, names):
            print(line)
        return 1 if missing(source, names) else 0
    if verb == "fingerprint":
        if len(names) != 1:
            print("secrets: fingerprint takes exactly one NAME", file=sys.stderr)
            return 2
        digest = fingerprint(os.environ.get(names[0]) or "")
        if not digest:
            return 1
        print(digest)
        return 0

    print("unknown verb: %s" % verb, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
