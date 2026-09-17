#!/usr/bin/env python3
"""Port of `.ci/scripts/autopilot/review-payload.sh`.

Builds the review payload the model is allowed to see out of the raw review threads the gate fetched. PURE: one JSON file in, one JSON object out, no network, no git, no env. The twin's header says the purity is the point, and it is right: this file decides WHOSE TEXT REACHES THE MODEL, and a security decision that cannot be exercised offline is one nobody has tested.

THE FILTER IS ON THE ROOT COMMENT'S AUTHOR, AND ONLY THE ROOT'S. A thread is STARTED by whoever raised the finding, and on a public repository anyone can REPLY into it. So a thread whose root author does not match is dropped whole, and a matching thread keeps every comment including replies, deliberately, as data. The port changes neither half. `select_threads` below is the whole
control, exported so a test can drive it without a subprocess.

NO `jq` SUBPROCESS, UNLIKE `update_state.py`. This module's twin runs exactly one jq program and its result is the product; reproducing it in Python is the port. `update_state.py` shells out because its jq calls sit in the middle of a pipeline whose failure text is load-bearing. Here the failure text is reproduced by hand instead, which is the harder half of this file and is
documented under THE JQ ERROR SURFACE below.

THREE jq BEHAVIOURS A NAIVE PYTHON PORT GETS WRONG, all three found by driving jq 1.8.1 rather than by reading its manual:

  1. `0 == false` IS FALSE IN jq AND TRUE IN PYTHON. The select is
     `(.isResolved // false) == false`, so a thread carrying `"isResolved": 0`
     is DROPPED by the twin. Written as `value == False` in Python, `0` would
     compare equal and the thread would be kept: a resolved-looking thread
     reaching the model on a technicality. `_is_false` compares identity.

  2. `tojson` ESCAPES U+007F, `json.dumps(ensure_ascii=False)` DOES NOT.
     Measured: jq renders DEL as `\\u007f`, Python emits the raw byte. That is
     six bytes against one, and this filter's whole byte cap is measured with
     `utf8bytelength` over `tojson`, so the difference is not cosmetic -- it
     changes which threads survive the cap. `compact` re-escapes it.

  3. `utf8bytelength`, NOT `length`. Carried over from the twin's own comment:
     jq's `length` on a string counts CODEPOINTS, so a CJK or emoji payload
     measures about a third of the bytes it occupies. Python's `len` on a `str`
     has exactly the same defect, so the port measures `len(s.encode())`.

THE BYTE CAP SHEDS OLDEST-FIRST, and the twin's `reduce range(0; length)` is reproduced as a bounded loop rather than a `while`: it runs at most `length`
times, so it CAN end with zero threads and `dropped == length`. A `while
over_cap` loop would be the same thing here only by accident, and a bounded loop is what the twin actually wrote.

THE JQ ERROR SURFACE, REPRODUCED RATHER THAN SWALLOWED. Every element of the threads array is reached with `.field` accessors that RAISE in jq when the value underneath is the wrong type, and under `set -euo pipefail` that takes the twin down with jq's own exit code (5, measured -- not 2) and jq's own message on stderr. `_index` and `_contains` below raise `JqError` carrying the
transliterated text, and `main` prints it in jq's frame:

    jq: error (at <file>:<n>): Cannot index number with string "isResolved"

`<n>` is the newline count of the input file, which is what jq reports for a whole-file value in both the single-line (`:0`) and multi-line cases measured. The differential asserts that against real jq rather than trusting the rule.

A `null` ELEMENT IS NOT AN ERROR, which is the one place the accessors have to be careful: `null.isResolved` is `null` in jq, not a type error, so a null entry flows through the select and is dropped later by the author filter.

Exit: 0 built (a payload with zero threads is a valid payload), 2 usage or parse error, 5 a jq type error inside the filter.

K=5 LEDGER: `.ci/shadow/w7p6-review-payload.observations.jsonl`.
"""

from __future__ import annotations

import contextlib
import json
import re
import sys
from typing import Any

from rediacc_ci import log
from rediacc_ci.core import common

SELF = "review-payload.py"

USAGE = (
    "usage: review-payload.sh --threads <file> [--author-filter <substring>] "
    "[--max-bytes <n>] [--out <file>]"
)

# `${ARG_AUTHOR_FILTER-github-actions}` -- the `-` form, NOT `:-`. An explicitly
# EMPTY --author-filter is a wiring bug and must reach the guard below; `:-` would substitute the safe default and make that guard unreachable.
DEFAULT_AUTHOR_FILTER = "github-actions"

# `${ARG_MAX_BYTES:-49152}` -- 48 KiB.
DEFAULT_MAX_BYTES = "49152"

# `[[ "$MAX_BYTES" =~ ^[0-9]{1,8}$ ]]`.
MAX_BYTES_RE = re.compile(r"^[0-9]{1,8}$")

# jq's own exit code for a runtime error in the program. MEASURED (jq 1.8.1): `jq -c '.[].x' <<<'[1]'` exits 5, not 2. A port that guessed 2 would diverge on every malformed-element case.
JQ_RUNTIME_RC = 5


class JqError(Exception):
    """One of jq's runtime type errors, with jq's wording."""


def _type_name(value: Any) -> str:
    """jq's `type`, which is the noun its error messages use."""
    if value is None:
        return "null"
    if value is True or value is False:
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    return "object"


def _index(value: Any, key: str) -> Any:
    """`value.key` with jq's rules: null indexes to null, objects look up, and
    everything else is a type error rather than a silent None."""
    if value is None:
        return None
    if isinstance(value, dict):
        return value.get(key)
    raise JqError('Cannot index %s with string "%s"' % (_type_name(value), key))


def _index_num(value: Any, position: int) -> Any:
    """`value[0]`. Same shape, different noun; jq says "with number"."""
    if value is None:
        return None
    if isinstance(value, list):
        return value[position] if position < len(value) else None
    raise JqError("Cannot index %s with number" % _type_name(value))


def _iterate(value: Any) -> list[Any]:
    """`(.comments.nodes // [])[]`. `//` has already turned null into `[]`, so
    anything that is not an array here is jq's "Cannot iterate over" error."""
    if isinstance(value, list):
        return value
    raise JqError("Cannot iterate over %s" % _render(value))


# jq TRUNCATES every value it quotes in an error message, and the port has to do the same or its "identical" message is a different string. jq renders the value into a fixed buffer (`char errbuf[15]`) and overwrites the last three usable characters with dots, so a dump of 15 bytes or more comes out as its first 11 bytes plus `...`. MEASURED at the boundary, not read off the source:
# a 14-byte dump survives whole, a 15-byte dump is cut.
JQ_ERRBUF = 15


def _dump_trunc(value: Any) -> str:
    """`jv_dump_string_trunc`: the value as jq quotes it inside an error.

    Sliced on BYTES, because jq's is a `strncpy` into a byte buffer. The one place this can still differ is a multi-byte character straddling the cut, where jq emits the partial bytes and this emits U+FFFD; that is an error message about an already-malformed fixture, and it is named here rather than papered over.
    """
    raw = compact(value).encode("utf-8")
    if len(raw) >= JQ_ERRBUF:
        raw = raw[: JQ_ERRBUF - 4] + b"..."
    return raw.decode("utf-8", "replace")


def _render(value: Any) -> str:
    """How jq prints a value inside an error message: `number (5)`."""
    return "%s (%s)" % (_type_name(value), _dump_trunc(value))


def _contains(haystack: Any, needle: str) -> bool:
    """`contains($af)`. Only string-against-string is defined; anything else is
    jq's containment error, which is how a non-string `login` field surfaces."""
    if not isinstance(haystack, str):
        raise JqError(
            "%s and string (%s) cannot have their containment checked"
            % (_render(haystack), _dump_trunc(needle))
        )
    return needle in haystack


def _alt(value: Any, fallback: Any) -> Any:
    """jq's `//`: substitute for null and false ONLY. `0` and `""` survive."""
    return fallback if (value is None or value is False) else value


def _is_false(value: Any) -> bool:
    """`(.x // false) == false`, which is TRUE only when the field was null,
    absent or literally `false`. See divergence 1 in the module docstring: this
    is `is False`, never `== False`, so `0` does not sneak through."""
    return _alt(value, False) is False


def compact(value: Any) -> str:
    """jq's `tojson`: no spaces, no ASCII escaping, and U+007F escaped.

    The DEL substitution is a post-pass over the encoded text on purpose. A DEL byte can only have come out of a string's contents (no JSON syntax character is DEL), so rewriting it in the finished text cannot corrupt structure, and doing it here keeps one encoder rather than a custom `json.JSONEncoder` subclass that would have to re-implement escaping.
    """
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False).replace("\x7f", "\\u007f")


def utf8_len(text: str) -> int:
    """`utf8bytelength`. BYTES. See divergence 3."""
    return len(text.encode("utf-8"))


def select_threads(data: list[Any], author_filter: str) -> list[dict[str, Any]]:
    """The security control: unresolved, not outdated, and ROOT-AUTHORED by a
    login containing `author_filter`. Shape-preserving, so the result is
    exactly the object the twin's first `[ ... ]` produces."""
    kept: list[dict[str, Any]] = []
    for entry in data:
        if not _is_false(_index(entry, "isResolved")):
            continue
        if not _is_false(_index(entry, "isOutdated")):
            continue
        nodes = _alt(_index(_index(entry, "comments"), "nodes"), [])
        root_login = _alt(_index(_index_num(nodes, 0), "author"), None)
        root_login = _alt(_index(root_login, "login"), "")
        if not _contains(root_login, author_filter):
            continue
        comments = [
            {
                "author": _alt(_index(_index(node, "author"), "login"), "unknown"),
                "body": _alt(_index(node, "body"), ""),
                "id": _alt(_index(node, "databaseId"), None),
            }
            for node in _iterate(nodes)
        ]
        kept.append(
            {
                "id": _index(entry, "id"),
                "repo": _alt(_index(entry, "repo"), None),
                "pr": _alt(_index(entry, "pr"), None),
                "path": _alt(_index(entry, "path"), ""),
                "line": _alt(_index(entry, "line"), None),
                "comments": comments,
            }
        )
    return kept


def shed(threads: list[dict[str, Any]], max_bytes: int) -> tuple[list[dict[str, Any]], int]:
    """The oldest-first byte cap. `reduce range(0; length)`: at most one drop
    per original thread, so an over-cap single thread ends up dropped too."""
    dropped = 0
    remaining = list(threads)
    for _ in range(len(threads)):
        if utf8_len(compact(remaining)) <= max_bytes:
            break
        remaining = remaining[1:]
        dropped += 1
    return remaining, dropped


def build_payload(data: list[Any], author_filter: str, max_bytes: int) -> dict[str, Any]:
    """The whole jq program, as one call. Key order matches the twin's object
    construction, because the output is compared as bytes downstream."""
    kept = select_threads(data, author_filter)
    remaining, dropped = shed(kept, max_bytes)
    return {
        "threads": remaining,
        "kept": len(remaining),
        "dropped": dropped,
        "bytes": utf8_len(compact(remaining)),
    }


def jq_error_line(raw: bytes) -> int:
    """The `(at <file>:<n>)` offset jq prints for a whole-file value.

    MEASURED, not assumed: a one-line fixture with no trailing newline reports `:0` and a four-line fixture reports `:4`, i.e. the newline count of the text jq has consumed, which for a single top-level value read in one buffer is the whole file. The differential pins this against real jq; a file large enough to be read in several buffers is outside what this script is ever handed
    (its input is one gate's thread fetch).
    """
    return raw.count(b"\n")


def load_threads(raw: bytes) -> Any:
    """`jq -e 'type == "array"'`, as a decode plus a parse plus a type test.

    DECODED WITH `errors="replace"`, matching jq: measured, jq 1.8.1 accepts a
    fixture carrying a lone `\\xff` and substitutes U+FFFD rather than refusing the file. A port that raised `UnicodeDecodeError` here would turn a payload the twin builds into a usage refusal.

    PARSING ONLY. The `type == "array"` half of `jq -e` is the caller's, so the
    two failures the twin reports with ONE message (a parse error and a well-formed non-array) reach that one message by two paths without this
    function having to invent an exception for the second.
    """
    return json.loads(raw.decode("utf-8", "replace"))


def main(argv: list[str]) -> int:
    try:
        args = common.parse_args(argv)
    except common.RefusalError as exc:
        # parse_args QUIRK 3: `printf -v` refuses an invalid identifier and takes the twin down with exit 2.
        print("%s: %s" % (SELF, exc.lines[0]), file=sys.stderr, flush=True)
        return exc.code

    threads_path = args.get("ARG_THREADS", "")
    author_filter = args.get("ARG_AUTHOR_FILTER", DEFAULT_AUTHOR_FILTER)
    max_bytes_raw = args.get("ARG_MAX_BYTES", "") or DEFAULT_MAX_BYTES
    out_path = args.get("ARG_OUT", "")

    if not threads_path:
        log.error(USAGE)
        return 2
    try:
        common.require_file(threads_path)
    except common.RefusalError as exc:
        exc.report()
        return exc.code
    if not MAX_BYTES_RE.match(max_bytes_raw):
        log.error("--max-bytes must be a number, got '%s'" % max_bytes_raw)
        return 2
    if not author_filter:
        log.error(
            "--author-filter must not be empty: an empty filter would match every "
            "author, which is the opposite of filtering"
        )
        return 2

    with open(threads_path, "rb") as handle:
        raw = handle.read()
    data = None
    with contextlib.suppress(ValueError):
        data = load_threads(raw)
    if not isinstance(data, list):
        # One message for both halves of `jq -e 'type == "array"'`: a file that
        # will not parse, and a file that parses into something else. An empty file lands here too, where `jq -e` exits 4.
        log.error("threads fixture is not a JSON array: %s" % threads_path)
        return 2

    try:
        payload = build_payload(data, author_filter, int(max_bytes_raw))
    except JqError as exc:
        # jq's own frame, on stderr, and jq's own exit code. `set -e` gives the twin no chance to say anything of its own here, so neither does this.
        print(
            "jq: error (at %s:%d): %s" % (threads_path, jq_error_line(raw), exc),
            file=sys.stderr,
            flush=True,
        )
        return JQ_RUNTIME_RC

    text = compact(payload)
    if out_path:
        try:
            with open(out_path, "w", encoding="utf-8") as handle:
                handle.write(text + "\n")
        except OSError as exc:
            # `>"$OUT"` failing is a bash redirection diagnostic carrying the twin's own path and line number; only the text differs.
            print("%s: %s" % (SELF, exc), file=sys.stderr, flush=True)
            return 1
    else:
        sys.stdout.write(text + "\n")
        sys.stdout.flush()

    if payload["dropped"] != 0:
        log.warn(
            "review payload capped at %s bytes: %d oldest thread(s) dropped, %d kept"
            % (max_bytes_raw, payload["dropped"], payload["kept"])
        )
    else:
        log.info(
            "review payload: %d thread(s), %d bytes, rooted by an author matching '%s'"
            % (payload["kept"], payload["bytes"], author_filter)
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
