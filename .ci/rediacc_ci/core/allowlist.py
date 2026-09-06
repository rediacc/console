"""One parser for this repository's allow/block lists, and the BLOCKER contract.

WHAT IS BEING CONSOLIDATED. `docs/agent-reference/suppressions.md` describes a
single convention: every escape-hatch entry in this tree carries a substantive
`# BLOCKER: <reason>` above it (or inline after it), a blank line ends the group,
and the reason is held to a 30-character floor plus a banned-phrase list. There
are FOUR implementations of that one convention in the tree today, and they do
not have the same capabilities:

  .ci/scripts/lib/blocker-validator.sh   parse_blockered_list + verify_all_blockers
                                         5 gates and 1 gate test source it
  scripts/lib/blocker-validator.ts       parseBlockeredList + verifyAllBlockers
                                         13 gates import it
  .ci/scripts/quality/check_runner_advice.py:599  parse_allowlist -- a third copy,
                                         in Python, whose own docstring says it is
                                         "the same grammar as .profiler-coverage-allowlist"
  .ci/scripts/quality/check-plan-housekeeping.sh:361  a fourth, inline, hand-rolled

This module is the one implementation. It is byte-compatible with the two shared
readers on every list in the tree -- proved, not asserted, by
`.ci/rediacc_ci/tests/test_core_allowlist.py`, which runs both of them over a
frozen corpus taken from the real lists and compares the bytes.

THE TWO PROJECTIONS, because the two readers do not return the same thing and a
port that picked one would silently be wrong about the other:

  records  ordered, one row per entry line, WITH the line number.
           `parseBlockeredList` returns exactly this.
  pairs    deduplicated entry -> reason, last write wins, sorted by byte.
           `parse_blockered_list` returns exactly this, because it populates two
           bash ASSOCIATIVE ARRAYS and an associative array cannot hold two rows
           for one key.

The difference is not academic. `.ci-parity-exempt` is direction-tagged, so its
entry lines read `ci-only  <path>` and the shared parsers both take the FIRST
whitespace token as the key. Nine entry lines in that file collapse to ONE key
under the bash reader; `scripts/check-ci-parity.ts:751` carries a comment about
having to correct for it. A caller that needs per-entry reasons must use
`records`, and this module makes the choice visible instead of leaving it to
whichever reader happened to be reachable from the language the gate was in.

A MISSING LIST IS AN ERROR HERE, AND IT IS NOT IN EITHER READER. Both of them
open with the same shape:

    [[ ! -f "$file" ]] && return 0                    (bash)
    if (!fs.existsSync(filePath)) return [];          (TypeScript)

so a gate handed a path that does not exist gets an empty allowlist, suppresses
nothing, finds nothing to complain about, and reports green. "Empty" and
"absent" produce the same colour and only one of them is correct. `parse_file`
raises `ListNotFoundError`; a caller that genuinely wants the permissive
behaviour writes `missing_ok=True` at the call site, where a reviewer sees it.

AND THE PATHS RESOLVE FROM THE REPO ROOT, NOT FROM cwd. `audit.sh:327` passes
the bare string `".audit-prod-allowlist"`, which is only correct while the gate
is run from the root; the same call from a subdirectory finds nothing and, per
the paragraph above, that nothing is indistinguishable from an empty list. Use
`load(name)`, which goes through `rediacc_ci.paths.from_root`.

KNOWN CROSS-LANGUAGE HAZARDS, recorded because they are real and the goldens
cannot see them (no list in the tree exercises any of them today):

  * `${#normalized}` in bash counts BYTES under LC_ALL=C, `normalized.length` in
    TypeScript counts UTF-16 code units, and `len()` here counts code points.
    A sub-30 reason written in non-ASCII can therefore be judged differently by
    the three. Every reason in the tree is ASCII and well over the floor.
  * `tr '[:upper:]' '[:lower:]'` under LC_ALL=C lowercases ASCII only, while
    `toLowerCase()` and `str.lower()` are Unicode-aware. Same population, same
    reason it has never fired.
  * `echo "$reason"` in `validate_blocker_quality` is the bash builtin, so a
    reason beginning `-n`/`-e`/`-E`, or containing a backslash escape, is
    mangled before it is normalized. This one is a live defect in the bash
    reader rather than a difference of opinion; see the test module.

Nothing in here is imported by the bash or TypeScript readers, and neither of
them is deleted -- `.ci/rediacc_ci/core/__init__.py` states that contract for
every module in this subpackage.
"""

import os
import pathlib
import re
import sys
from typing import NamedTuple

from rediacc_ci import paths

# ---------------------------------------------------------------------------
# The quality rules, kept byte-identical to the two shared readers.
# ---------------------------------------------------------------------------

# Exact-match after normalization. Copied from LOW_EFFORT_BLOCKER_PATTERNS in
# .ci/scripts/lib/blocker-validator.sh and its TypeScript twin, in their order,
# which is load-bearing: the message quotes the FIRST pattern that matches and a
# reordering would change the bytes a gate prints.
LOW_EFFORT_PHRASES: tuple[str, ...] = (
    # npm-audit ack-tier phrases
    "no fix",
    "no fix available",
    "no fix yet",
    "no upstream fix",
    "no fix published",
    "no patch",
    "no patch yet",
    "no patch available",
    "none",
    "n/a",
    "na",
    "empty",
    "-",
    # scheduling ack-tier
    "tbd",
    "wip",
    "fixme",
    "todo",
    "later",
    "fix later",
    "will fix",
    "pending",
    "skip",
    "skipping",
    "skipped",
    "ignore",
    "ignoring",
    "ignored",
    "unknown",
    "unknown reason",
    "idk",
    "dunno",
    "whatever",
    # review-gate-style ack phrases
    "ok",
    "okay",
    "ack",
    "acknowledged",
    "noted",
    "done",
    "fixed",
    "applied",
    "addressed",
    "updated",
    "changed",
    "understood",
    # explicit escape-hatch attempts
    "escape",
    "escape hatch",
    "suppressed",
    "suppress",
    "bypass",
    "override",
    "upstream issue",
    "transitive",
    "dev dep",
    "dev only",
)

# Substring-matched, not exact. Deferral-for-convenience rather than a hold.
LOW_EFFORT_SUBSTRINGS: tuple[str, ...] = (
    "deferred to a dedicated dependency-bump pr",
    "not needed by this change",
    "not needed in this change",
    "not needed for this change",
    "to keep this merge focused",
    "to keep this change focused",
    "to keep this pr focused",
)

MIN_REASON_LENGTH = 30

# The two readers' messages contain U+2014. It is written as an escape rather
# than as the character so this file stays ASCII -- the repo's prose rules
# forbid the literal, and the byte still has to reach the output because the
# whole point of these strings is that they match what the gates already print.
_EM_DASH = "\u2014"

_TRAILING_PUNCTUATION = re.compile(r"[.!?,;:]+$")


class ListNotFoundError(FileNotFoundError):
    """The list file is not there.

    A named type rather than a bare FileNotFoundError so a caller can tell "your
    allowlist path is wrong" apart from any other missing file its own work
    touched, and so a test can assert on it without matching a message.
    """


class Entry(NamedTuple):
    """One entry line, with the reason in force at that line."""

    entry: str
    blocker: str
    line: int


class Rejection(NamedTuple):
    """Why a reason was refused. `message` is byte-identical to both readers."""

    kind: str  # "low-effort" | "deferral" | "too-short" | "missing"
    normalized: str
    message: str


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def _patterns(comment_char: str) -> tuple[re.Pattern, re.Pattern, re.Pattern]:
    cc = re.escape(comment_char)
    return (
        re.compile(r"^\s*%s\s*BLOCKER:\s*(.+)$" % cc),
        re.compile(r"^\s*%s" % cc),
        re.compile(r"%s\s*BLOCKER:\s*(.+)$" % cc),
    )


def parse_text(text: str, comment_char: str = "#") -> list[Entry]:
    """The grammar, on a string. `records` order, one row per entry LINE.

    SPLIT ON "\\n" AND NOTHING ELSE. `str.splitlines()` is the obvious call and
    it also breaks on \\r, \\x0b, \\x0c, \\x1c-\\x1e, \\x85, \\u2028 and \\u2029, none of
    which either reader treats as a line boundary. A list carrying one of those
    bytes inside a reason would then be parsed into more entries here than in
    the thing this is supposed to agree with, and the goldens would be the only
    place it showed up.
    """
    blocker_re, comment_re, inline_re = _patterns(comment_char)
    entries: list[Entry] = []
    current = ""
    for number, raw in enumerate(text.split("\n"), start=1):
        stripped = raw.strip()
        if not stripped:
            # A blank line resets the group. This is the documented contract, and
            # it is also why `scripts/check-suppression-liveness.ts:894` has to
            # hunt for reasons that cover no entries at all: the readers walk
            # entries, so a reason orphaned by a stray blank line is invisible.
            current = ""
            continue
        match = blocker_re.match(stripped)
        if match:
            current = match.group(1).strip()
            continue
        if comment_re.match(stripped):
            continue  # a plain comment preserves the group's reason
        token = re.split(r"\s", stripped, maxsplit=1)[0]
        cut = token.find(comment_char)
        if cut >= 0:
            token = token[:cut]
        token = token.strip()
        if not token:
            continue
        blocker = current
        if not blocker:
            inline = inline_re.search(stripped)
            if inline:
                blocker = inline.group(1).strip()
        entries.append(Entry(token, blocker, number))
    return entries


def parse_file(
    path: os.PathLike[str] | str,
    comment_char: str = "#",
    *,
    missing_ok: bool = False,
) -> list[Entry]:
    """Parse a list file. Raises `ListNotFoundError` unless `missing_ok`.

    `missing_ok=True` reproduces what both shared readers do unconditionally. It
    is spelled out at the call site on purpose: a gate that wants "no file means
    no suppressions" is making a claim, and the claim should be visible in the
    diff rather than inherited from a library's default.
    """
    p = pathlib.Path(path)
    if not p.is_file():
        if missing_ok:
            return []
        raise ListNotFoundError(
            "%s is not a readable list file. An absent list and an empty list "
            "produce the same green verdict, and only one of them is correct; "
            "pass missing_ok=True if you really mean 'no file, no entries'." % p
        )
    return parse_text(p.read_text(encoding="utf-8"), comment_char)


def load(
    name: str,
    comment_char: str = "#",
    *,
    root: pathlib.Path | None = None,
    missing_ok: bool = False,
) -> list[Entry]:
    """Parse a list named RELATIVE TO THE REPO ROOT, never to cwd.

    The reason this exists rather than callers writing `parse_file(".audit-...")`
    is `audit.sh:327`, which does exactly that in bash and is correct only while
    the gate is invoked from the root.
    """
    return parse_file(paths.from_root(name, root=root), comment_char, missing_ok=missing_ok)


# ---------------------------------------------------------------------------
# Projections -- the two shapes the two readers can express
# ---------------------------------------------------------------------------


def pairs(entries: list[Entry]) -> dict[str, str]:
    """entry -> reason, LAST write wins. What a bash associative array holds."""
    out: dict[str, str] = {}
    for item in entries:
        out[item.entry] = item.blocker
    return out


def render_records(entries: list[Entry]) -> str:
    """`<line>\\t<entry>\\t<reason>` per row, in file order. Trailing newline."""
    return "".join("%d\t%s\t%s\n" % (e.line, e.entry, e.blocker) for e in entries)


def render_pairs(entries: list[Entry]) -> str:
    """`<entry>\\t<reason>` per row, deduplicated, sorted BY BYTE.

    Sorted on the rendered LINE rather than on the key, because that is what
    `LC_ALL=C sort` does to the bash reader's output and the two only coincide
    while the separator sorts below every character a key can contain. TAB is
    0x09, so they do coincide -- but the comparison is written the way the thing
    it is compared against is written, not the way that happens to work.
    """
    rows = ["%s\t%s\n" % (k, v) for k, v in pairs(entries).items()]
    rows.sort(key=lambda row: row.encode("utf-8"))
    return "".join(rows)


# ---------------------------------------------------------------------------
# The BLOCKER quality contract
# ---------------------------------------------------------------------------


def normalize_reason(reason: str) -> str:
    """Lowercase, trim, drop trailing `.!?,;:`. The readers' order, exactly."""
    return _TRAILING_PUNCTUATION.sub("", reason.lower().strip())


def validate_reason(entry: str, reason: str, file: str) -> Rejection | None:
    """None when the reason passes. Messages match both readers byte for byte."""
    normalized = normalize_reason(reason)

    for pattern in LOW_EFFORT_PHRASES:
        if normalized == pattern:
            return Rejection(
                "low-effort",
                normalized,
                "\n".join(
                    [
                        'Allowlist %s: BLOCKER for entry %s is a low-effort placeholder ("%s")'
                        % (file, entry, reason),
                        '  Rejected because: "%s" matches the banned-phrase list %s this adds '
                        "no information beyond 'we suppressed it'" % (normalized, _EM_DASH),
                        (
                            "  Action: write a specific reason. Good BLOCKERs cite the "
                            "upstream pin, the package chain, OR why runtime isn't affected."
                        ),
                        (
                            "  Example: 'electron-builder 26.x pins plist > xmldom 0.8.x; "
                            "build-time only, requires major electron migration'"
                        ),
                    ]
                ),
            )

    for pattern in LOW_EFFORT_SUBSTRINGS:
        if pattern in normalized:
            return Rejection(
                "deferral",
                normalized,
                "\n".join(
                    [
                        "Allowlist %s: BLOCKER for entry %s defers a routine bump instead of "
                        'justifying a hold ("%s")' % (file, entry, reason),
                        '  Rejected because: it contains "%s" %s the upgrade blocklist is for '
                        "bumps that genuinely cannot be taken now (breaking major, pin "
                        "conflict, native rebuild, known regression), not for deferring a "
                        "routine installable bump." % (pattern, _EM_DASH),
                        (
                            "  Note: check-deps already auto-defers freshly-published "
                            "versions (until the next UTC day after they age the "
                            "minimum-release-age window), so there is no need to blocklist "
                            "a fresh release."
                        ),
                        (
                            "  Action: TAKE the bump ('npm run check:deps -- --upgrade'), OR "
                            "cite the concrete technical blocker (which package pins what, "
                            "what breaks)."
                        ),
                    ]
                ),
            )

    if len(normalized) < MIN_REASON_LENGTH:
        return Rejection(
            "too-short",
            normalized,
            "\n".join(
                [
                    "Allowlist %s: BLOCKER for entry %s is too short (%d chars, minimum %d)"
                    % (file, entry, len(normalized), MIN_REASON_LENGTH),
                    '  Current: "%s"' % reason,
                    (
                        "  Action: a BLOCKER must explain WHO pins what, WHY the fix cannot "
                        "be taken now, and ideally WHEN to revisit."
                    ),
                    (
                        "  Example: 'axios 1.15.0 pins follow-redirects <1.16.0; not "
                        "runtime-exposed in CLI auth path; revisit when axios bumps'"
                    ),
                ]
            ),
        )

    return None


def missing_reason(entry: str, file: str) -> str:
    """The message `verify_all_blockers` prints for an entry with no reason.

    The literal `'# BLOCKER: ...'` is hardcoded in both readers even when the
    file's comment character is `//`, so it is hardcoded here too. Reproducing a
    wart is the job; diverging from it would make this module's output something
    a gate could not adopt without changing its own expected text.
    """
    return "\n".join(
        [
            "Allowlist %s: entry %s is missing a '# BLOCKER: <reason>' comment above it"
            % (file, entry),
            "  Action: add a line like '# BLOCKER: <who pins what / why we cannot take the "
            "fix>' immediately above %s in %s" % (entry, file),
        ]
    )


def verify(entries: list[Entry], file: str) -> list[str]:
    """Every failure message, in entry order. Empty list means the file is clean.

    THE ENTRIES WITHOUT A REASON ARE REPORTED, not skipped. That is the half of
    the contract a reader could quietly drop and still look correct: an entry
    with an empty reason parses fine, appears in both projections, and is only a
    finding because something asks.
    """
    failures: list[str] = []
    for item in entries:
        if not item.blocker:
            failures.append(missing_reason(item.entry, file))
            continue
        rejection = validate_reason(item.entry, item.blocker, file)
        if rejection is not None:
            failures.append(rejection.message)
    return failures


def unreasoned(entries: list[Entry]) -> list[Entry]:
    """Just the entries carrying no reason at all. The reportable population."""
    return [e for e in entries if not e.blocker]


# ---------------------------------------------------------------------------
# argv dispatch -- what a bash or TypeScript caller can reach
# ---------------------------------------------------------------------------


def main(argv: list[str]) -> int:
    if not argv:
        print(
            "usage: python3 -m rediacc_ci.core.allowlist <records|pairs|verify|reason> [args]",
            file=sys.stderr,
        )
        return 2
    verb, rest = argv[0], argv[1:]

    if verb in ("records", "pairs", "verify"):
        if not rest:
            print("%s needs a list path" % verb, file=sys.stderr)
            return 2
        path, comment_char = rest[0], (rest[1] if len(rest) > 1 and rest[1] else "#")
        try:
            entries = parse_file(path, comment_char)
        except ListNotFoundError as exc:
            # EXIT 2, NOT 1. A caller distinguishes "the list is dirty" (1) from
            # "you pointed me at nothing" (2); collapsing them is how an absent
            # list becomes a clean bill of health.
            print(str(exc), file=sys.stderr)
            return 2
        if verb == "records":
            sys.stdout.write(render_records(entries))
            return 0
        if verb == "pairs":
            sys.stdout.write(render_pairs(entries))
            return 0
        failures = verify(entries, path)
        for message in failures:
            print(message)
        return 1 if failures else 0

    if verb == "reason":
        if len(rest) < 3:
            print("reason needs <entry> <reason> <file>", file=sys.stderr)
            return 2
        rejection = validate_reason(rest[0], rest[1], rest[2])
        if rejection is None:
            print("OK")
            return 0
        print(rejection.message)
        return 1

    print("unknown verb: %s" % verb, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
