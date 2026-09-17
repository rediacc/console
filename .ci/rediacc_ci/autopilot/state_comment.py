#!/usr/bin/env python3
"""Port of `.ci/scripts/autopilot/state-comment.sh`.

The autopilot state comment: ONE comment per PR, authored by the autopilot app, PATCH-updated in place, in plain visible text (03-v2-autonomy.md section 3 -- HTML comments are stripped from prompts and agent mode inlines no thread text at all, so this comment is the ONLY state channel the loop has). Three subcommands:

    select   PURE. A JSON array of {id, author, body} in, the newest TRUSTED
             match out as `{"found":true,"id":N,"body":...}` or `{"found":false}`.
    render   PURE. Rebuilds the whole body from the previous one plus this
             round's lines. Printed on stdout; `update-state.sh` is what writes
             it to GitHub.
    fields   PURE. Reads the campaign metadata back off a rendered body, so
             `autopilot-gate.sh` has exactly one reader of that line and this
             file is exactly one writer.

-----------------------------------------------------------------------------
WHERE THE IDEMPOTENCY ACTUALLY LIVES, because it is NOT in this file
-----------------------------------------------------------------------------
The one-comment-per-PR property is a THREE-PART contract and only two parts are here. `select` finds the existing comment; `render` rebuilds its whole body from the old one; `update-state.sh` then POSTs or PATCHes depending on whether an id was found (`update_state.endpoint_for`). So the upsert is: select -> render -> patch, and this script owns the two halves that never touch the
network.

That split is why `select`'s three cases are worth exhaustive coverage: a comment that exists, one that does not, and a LOOKUP THAT CANNOT BE BELIEVED. The third one is the interesting case and the twin has an answer for it that a reimplementation would lose --

  THE COMMENTS FILE IS UNTRUSTED, AND `select` IS THE TRUST BOUNDARY. console is
  public and anyone can post a lookalike. A comment counts only when its author
  EQUALS the bot login and its body STARTS WITH the exact header; everything
  else is data. Both halves matter: dropping the author check lets any drive-by
  commenter drive the loop's round counter, and dropping the header check lets
  the bot's own unrelated comment be read as state. Newest (highest id) wins if
  the bot somehow posted twice, which is a deliberate choice over "refuse on
  ambiguity" -- a duplicate must not wedge a campaign.

  A MALFORMED COMMENTS FILE IS AN ERROR, NOT AN EMPTY ANSWER. `jq` exits 5 and
  `set -e` ends the run, so the caller never sees `{"found":false}` for a lookup
  that failed. That distinction is the whole difference between "no state
  comment yet, create one" and "the API answer was garbage": the first POSTs a
  new comment, and if a failed lookup were allowed to look like the first, every
  round with a flaky read would post ANOTHER state comment and the loop would
  have several memories.

`jq` IS SPAWNED for `select` and `fields`, deliberately, and this is the wave's standing rule rather than a shortcut. `select`'s program encodes the trust rule
(`startswith`, `sort_by(.id)`, `.[-1]`) and its output bytes are the interface;
`fields`'s `-cn --arg/--argjson` construction is where `rounds_max` becomes a NUMBER and `campaign` stays a STRING, which `autopilot-gate.sh` then reads with `--argjson`. A Python `json.dumps` would have to re-derive jq's key order and compact spacing, and the first character it got wrong would be read by a gate.

-----------------------------------------------------------------------------
WHAT IS RE-IMPLEMENTED INSTEAD OF SPAWNED, AND WHY
-----------------------------------------------------------------------------
The three awk programs (the metadata reader, the carry-over section walk, the ledger compactor) are transliterated into Python, the way `submodule_prs.py` transliterated its own awk. They are small state machines over exact-match lines
with no locale-sensitive collation, and holding them as Python makes the
carry-over rule -- the anti-tamper rule -- readable at the place it is enforced.

  GAWK'S FILE-ARGUMENT HANDLING IS PART OF THAT TRANSLITERATION, and it is not
  cosmetic. A DIRECTORY passed as `--body` makes gawk WARN and continue (exit 0,
  empty output); an unreadable file makes it FATAL (exit 2). Both are reachable
  from a live caller -- `update-state.sh` forwards whatever `--body` it was
  given -- and both are reproduced, message for message, in `_awk_read`. The
  differential asserts the exact byte counts of those warnings, so a gawk
  upgrade that rewords them turns this red instead of quietly diverging.

  AND `set -e` DOES NOT REACH INTO `$( )`. `inherit_errexit` is OFF (verified on
  bash 5.3.9), so a fatal inside `state_field`'s command substitution yields an
  EMPTY value and the script walks on to the sentinel -- while the same fatal in
  the top-level carry-over awk ends the run with 2. That asymmetry is why an
  unreadable body prints five fatals and still answers for `fields`, and six
  fatals and dies for `render`. Both are pinned.

-----------------------------------------------------------------------------
THE LINE CAP IS LOCALE-DEPENDENT, AND THIS IS A REAL DIVERGENCE IN THE TWIN
-----------------------------------------------------------------------------
`cap_line` is `((${#line} > 400))` and `${line:0:400}`, and bash counts
CHARACTERS under a UTF-8 LC_CTYPE and BYTES under C/POSIX. Measured on bash 5.3.9 with a 399-`a` string plus one `e-acute`:

    LC_ALL=C        ${#line} = 401, the cap truncates at 401 bytes
    LC_ALL=C.utf8   ${#line} = 400, the cap does not fire at all

So the same ledger line is capped differently depending on how the workflow's step happens to be invoked. The port reproduces the twin rather than choosing a side: `char_semantics()` resolves LC_ALL/LC_CTYPE/LANG exactly as a C program's `setlocale(LC_CTYPE, "")` does and reports which rule applies, and the differential drives BOTH locales. Choosing one would be a behaviour change
smuggled in as a port, and the choice belongs to the cutover box.

-----------------------------------------------------------------------------
EVERY CARRIED-OVER VALUE IS RE-VALIDATED ON READ AND ON WRITE
-----------------------------------------------------------------------------
`normalize_field` collapses anything unrecognised to the field's sentinel: campaign is one of three literals, model matches a tight identifier shape, rounds_max and sig_count are small integers, last_sig is exactly the eight lowercase hex the gate emits. It is applied to values read back from a previous body AND to values passed in as arguments, so there is no path by which an
unvalidated string reaches the rendered line. These values flow into a MODEL SELECTION and a ROUND CAP, so a surprise value must fail closed rather than propagate.

  `normalize_field` ON AN UNKNOWN FIELD NAME EXITS 2 rather than passing the
  value through. Unreachable from the CLI (the five names are hardcoded at every
  call site) and kept because the alternative is a typo that silently disables a
  validator. Exported and unit-driven.

Exit: 0, 2 on usage / an unknown subcommand / an unknown field name, 1 when `require_file` refuses the comments file, and jq's or gawk's own status when either fails.

K=5 LEDGER: `.ci/shadow/w7p6-state-comment.observations.jsonl`.
"""

from __future__ import annotations

import contextlib
import locale as _locale
import os
import re
import subprocess
import sys

from rediacc_ci import log
from rediacc_ci.core import common

SELF = "state-comment.py"

HEADER = b"### Autopilot state (machine-maintained, do not edit)"
LINE_CAP = 400
COMPACT_BYTES = 55 * 1024
KEEP_FULL_ROUNDS = 8

USAGE_SELECT = "usage: state-comment.sh select --comments <file> --bot <login>"
USAGE_RENDER = (
    "usage: state-comment.sh render --body <file> --state <s> --round <r/cap> "
    "--head <sha> --last-run <id/attempt handled> [--ledger <line>] "
    "[--ruled-out <line>] [--decision <line>] [--ruled-out-file <file>] "
    "[--decisions-file <file>] [--campaign <c>] [--model <id>] [--rounds-max <n>] "
    "[--last-sig <hex8>] [--sig-count <n>]"
)
USAGE_FIELDS = "usage: state-comment.sh fields --body <file>"
UNKNOWN_SUBCOMMAND = "unknown subcommand '%s' (select|render|fields)"

# THE TRUST RULE, as jq, byte for byte from the twin. Author equality AND the exact header prefix; newest id wins.
SELECT_PROGRAM = """
            [ .[]
              | select((.author == $bot) and (.body | startswith($header))) ]
            | sort_by(.id)
            | if length == 0 then {found: false}
              else {found: true, id: .[-1].id, body: .[-1].body} end
        """

FIELDS_PROGRAM = """{campaign: $campaign, model: $model, rounds_max: $rounds_max,
              last_sig: $last_sig, sig_count: $sig_count}"""

# `${value//[[:space:]]/}` in the C locale.
BASH_SPACE_RE = re.compile(r"[ \t\n\v\f\r]")

# The five validators. `\Z` and not `$`, because Python's `$` also matches before a trailing newline and bash's ERE `$` does not.
MODEL_RE = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z")
SMALL_INT_RE = re.compile(r"\A[0-9]{1,4}\Z")
SIG_RE = re.compile(r"\A[0-9a-f]{8}\Z")

# The carry-over section walk, as the awk that wrote it.
LEDGER_HEADING = b"#### Round ledger"
RULED_HEADING = b"#### Ruled out"
DECISIONS_PREFIX = b"#### DECISIONS"
LEDGER_LINE_RE = re.compile(rb"^r[0-9]+ \| run ")
BULLET_RE = re.compile(rb"^- ")

# The compactor's `match($0, /^r[0-9]+ \| run [^ |]+/)`.
COMPACT_HEAD_RE = re.compile(rb"^r[0-9]+ \| run [^ |]+")
COMPACT_SUFFIX = b" | compacted (full detail in run logs)"

# gawk 5.3.2's own words for a file argument it cannot use.
GAWK_DIR_WARNING = "awk: warning: command line argument `%s' is a directory: skipped"
GAWK_FATAL = "awk: fatal: cannot open file `%s' for reading: %s"

_CHAR_SEMANTICS: bool | None = None


def char_semantics() -> bool:
    """Does bash count CHARACTERS in `${#line}` here, or BYTES?

    Resolved the way a C program resolves it: `setlocale(LC_CTYPE, "")` honours LC_ALL, then LC_CTYPE, then LANG, and falls back to the C locale when the named one is not installed -- which is exactly bash's own fallback. The answer is the CODESET: UTF-8 means characters, anything else (C, POSIX, ANSI_X3.4-1968) means bytes.

    The previous LC_CTYPE is restored, so importing this module does not change the locale of a process that only wanted to call a helper. Cached, because bash resolves it once at startup too.
    """
    global _CHAR_SEMANTICS  # noqa: PLW0603
    if _CHAR_SEMANTICS is None:
        previous = _locale.setlocale(_locale.LC_CTYPE)
        codeset = "ANSI_X3.4-1968"
        try:
            _locale.setlocale(_locale.LC_CTYPE, "")
            codeset = _locale.nl_langinfo(_locale.CODESET)
        except (_locale.Error, ValueError):
            # An unsupported locale name: bash falls back to C, so do we.
            codeset = "ANSI_X3.4-1968"
        finally:
            with contextlib.suppress(_locale.Error):
                _locale.setlocale(_locale.LC_CTYPE, previous)
        _CHAR_SEMANTICS = codeset.replace("-", "").upper() == "UTF8"
    return _CHAR_SEMANTICS


def cap_line(line: bytes) -> bytes:
    """`cap_line` (state-comment.sh:78-85): truncate one line to LINE_CAP.

    LOCALE-DEPENDENT ON PURPOSE. See the module docstring: `${#line}` and
    `${line:0:400}` count characters under a UTF-8 LC_CTYPE and bytes under C.
    Byte slicing can cut a multi-byte character in half, and that is what bash does too; `surrogateescape` makes the halves round-trip so the port emits the same bytes rather than a replacement character.
    """
    if char_semantics():
        text = line.decode("utf-8", "surrogateescape")
        if len(text) > LINE_CAP:
            text = text[:LINE_CAP]
        return text.encode("utf-8", "surrogateescape")
    if len(line) > LINE_CAP:
        return line[:LINE_CAP]
    return line


def normalize_field(name: str, value: str) -> str:
    """`normalize_field` (state-comment.sh:91-108). Anything unrecognised
    collapses to the field's sentinel.

    Raises `common.RefusalError(code=2)` on an unknown field name, which is the
    twin's `log_error ...; exit 2`. See the module docstring for why that arm exists at all.
    """
    value = BASH_SPACE_RE.sub("", value)
    if name == "campaign":
        return value if value in ("open", "closed") else "none"
    if name == "model":
        return value if MODEL_RE.match(value) else "none"
    if name == "rounds_max":
        return value if SMALL_INT_RE.match(value) else "0"
    if name == "last_sig":
        return value if SIG_RE.match(value) else "none"
    if name == "sig_count":
        return value if SMALL_INT_RE.match(value) else "0"
    raise common.RefusalError("normalize_field: unknown field '%s'" % name, code=2)


def _awk_read(path: str) -> tuple[bool, list[bytes]]:
    """gawk's handling of ONE file argument, as records. (ok, records).

    A DIRECTORY is a WARNING and an empty read (gawk exits 0); anything else that will not open is FATAL (gawk exits 2), which the caller turns into its own status. Both messages are gawk 5.3.2's, reproduced so the observable is the same string on both sides -- and asserted in the differential, so a gawk that rewords them turns the test red rather than diverging quietly.

    Records are newline-separated and the FINAL UNTERMINATED LINE IS A RECORD, which is awk's rule and NOT `while read`'s. The two appear in the same script and the difference is load-bearing: `append_entries` uses `read` and drops a final unterminated line; this drops nothing.
    """
    try:
        with open(path, "rb") as handle:
            data = handle.read()
    except IsADirectoryError:
        print(GAWK_DIR_WARNING % path, file=sys.stderr, flush=True)
        return True, []
    except OSError as exc:
        print(GAWK_FATAL % (path, exc.strerror), file=sys.stderr, flush=True)
        return False, []
    if not data:
        return True, []
    records = data.split(b"\n")
    if records and records[-1] == b"":
        records.pop()
    return True, records


def state_field_raw(records: list[bytes], name: str) -> str:
    """The metadata-line awk (state-comment.sh:118-126), over already-read records.

    Only the FIRST `state: ` line counts -- the twin's `exit` -- so a body carrying a second one (appended by anything other than this script) can never win. That is the same first-match discipline `select` applies to comments.

    Every matching part of that line is printed, and `$( )` joins them with newlines; `normalize_field` then strips the whitespace and validates, so two `campaign: ` parts on one line collapse to the sentinel rather than to the first value. Reproduced rather than tidied.
    """
    needle = (name + ": ").encode("utf-8", "surrogateescape")
    for record in records:
        if not record.startswith(b"state: "):
            continue
        found = [part[len(needle) :] for part in record.split(b" | ") if part.startswith(needle)]
        return b"\n".join(found).decode("utf-8", "surrogateescape")
    return ""


def state_field(path: str, name: str) -> tuple[bool, str]:
    """`state_field <body-file> <field>`. (ok, normalized value).

    `ok` is False only on gawk's fatal arm. Its CALLERS all sit inside a command substitution in the twin, where `set -e` does not reach (`inherit_errexit` is off), so every one of them treats a fatal as an empty read and carries on to the sentinel -- while still letting gawk's message reach fd 2.
    """
    if not path:
        return True, normalize_field(name, "")
    try:
        usable = os.path.getsize(path) > 0
    except OSError:
        usable = False
    if not usable:
        return True, normalize_field(name, "")
    ok, records = _awk_read(path)
    if not ok:
        # The twin's subshell died here, so `normalize_field` never ran and the substitution was empty -- which the CALLER then normalizes to the sentinel anyway.
        return False, normalize_field(name, "")
    return True, normalize_field(name, state_field_raw(records, name))


def carry_over(records: list[bytes]) -> tuple[list[bytes], list[bytes], list[bytes]]:
    """The section walk (state-comment.sh:181-190). (ledger, ruled, decisions).

    ANYTHING OUTSIDE THE KNOWN SECTIONS IS DROPPED, which is the anti-tamper rule: a body someone edited by hand cannot smuggle text into the next round. Note the order of the awk rules, which is preserved exactly --

      * `#### DECISIONS` is a PREFIX match, the other two headings are exact.
      * a `####` or `###` line that is none of the three CLOSES the current
        section, so text after an injected heading is dropped even inside what
        looks like a section.
      * within a section only the shaped lines survive: `r<digits> | run ` for
        the ledger, `- ` for the other two.
    """
    ledger: list[bytes] = []
    ruled: list[bytes] = []
    decisions: list[bytes] = []
    section = ""
    for line in records:
        if line == LEDGER_HEADING:
            section = "ledger"
            continue
        if line == RULED_HEADING:
            section = "ruled"
            continue
        if line.startswith(DECISIONS_PREFIX):
            section = "dec"
            continue
        # The twin has these as two awk rules, `/^####/` then `/^###/`, and they are kept as two prefixes rather than collapsed to `###` (which would match both) so the parser still reads as the awk.
        if line.startswith((b"####", b"###")):
            section = ""
            continue
        if section == "ledger" and LEDGER_LINE_RE.match(line):
            ledger.append(line)
        elif section == "ruled" and BULLET_RE.match(line):
            ruled.append(line)
        elif section == "dec" and BULLET_RE.match(line):
            decisions.append(line)
    return ledger, ruled, decisions


def read_entries(path: str) -> list[bytes]:
    """`append_entries <src-file>`'s `while IFS= read -r line` loop.

    TWO QUIRKS, BOTH THE TWIN'S:

      * a FINAL UNTERMINATED LINE IS DROPPED, because `read` returns non-zero at
        EOF and the loop body does not run for it. `_awk_read` above keeps it.
        Both are in this script, for different inputs, and a port that unified
        them would change what a truncated `--ruled-out-file` contributes.
      * a line that is entirely whitespace is skipped
        (`[[ -z "${line//[[:space:]]/}" ]]`), so "this round ruled nothing out"
        does not render a stray bullet.

    An absent or empty source contributes nothing (`[[ -n && -s ]] || return 0`), and a DIRECTORY passes that test and then fails to read -- which the twin reports as bash's own redirection error. Reproduced as an empty read plus that message; see `_entries_or_error`.
    """
    return [
        line
        for line in _read_lines_dropping_partial(path)
        if BASH_SPACE_RE.sub("", line.decode("utf-8", "surrogateescape")) != ""
    ]


def _read_lines_dropping_partial(path: str) -> list[bytes]:
    with open(path, "rb") as handle:
        data = handle.read()
    # `content.split(b"\n")[:-1]` is exactly the newline-terminated lines.
    return data.split(b"\n")[:-1]


def render_body(
    state_line: bytes, ledger: list[bytes], ruled: list[bytes], decisions: list[bytes]
) -> bytes:
    """`render_body` (state-comment.sh:212-225), byte for byte.

    The blank line before each heading comes from the twin's `printf '\\n####...'` and is real output, not tidy-up: the carry-over parser on the NEXT round reads this same text back, so changing the spacing changes what survives a round.
    """
    out = [HEADER, b"\n", state_line, b"\n", b"\n", LEDGER_HEADING, b"\n"]
    out += [line + b"\n" for line in ledger]
    out += [b"\n", RULED_HEADING, b"\n"]
    out += [line + b"\n" for line in ruled]
    out += [b"\n", b"#### DECISIONS (post-hoc review)", b"\n"]
    out += [line + b"\n" for line in decisions]
    return b"".join(out)


def compact(ledger: list[bytes]) -> list[bytes]:
    """The compactor (state-comment.sh:232-244).

    Everything but the newest KEEP_FULL_ROUNDS lines collapses to a one-line pointer; the run id keeps the full detail reachable in that round's workflow logs. A line that does not carry the `r<n> | run <id>` shape is passed through untouched rather than mangled.

    `total` is `grep -c .`, which counts NON-EMPTY lines, while `cut` is compared against awk's NR, which counts ALL of them. The two disagree the moment a blank line is in the ledger file -- which the carry-over parser cannot produce, since it only keeps `r<n> | run ` lines. Preserved as-is: the divergence is unreachable, and "fixing" it would change which rounds survive at the
    boundary.
    """
    total = sum(1 for line in ledger if line)
    cut_at = total - KEEP_FULL_ROUNDS
    out = []
    for index, line in enumerate(ledger, start=1):
        if index <= cut_at:
            match = COMPACT_HEAD_RE.match(line)
            out.append(match.group(0) + COMPACT_SUFFIX if match else line)
        else:
            out.append(line)
    return out


def _jq(args: list[str]) -> int:
    """jq with stdout and stderr both INHERITED, the way an unredirected jq in a
    `case` arm behaves. Its status becomes the script's."""
    sys.stdout.flush()
    sys.stderr.flush()
    return subprocess.run(["jq", *args], check=False).returncode


def _select(args: dict[str, str]) -> int:
    comments = args.get("ARG_COMMENTS", "")
    bot = args.get("ARG_BOT", "")
    if not (comments and bot):
        log.error(USAGE_SELECT)
        return 2
    try:
        common.require_file(comments)
    except common.RefusalError as exc:
        exc.report()
        return exc.code
    return _jq(
        ["-c", "--arg", "bot", bot, "--arg", "header", HEADER.decode(), SELECT_PROGRAM, comments]
    )


def _render(args: dict[str, str]) -> int:
    body = args.get("ARG_BODY", "")
    state = args.get("ARG_STATE", "")
    round_ = args.get("ARG_ROUND", "")
    head = args.get("ARG_HEAD", "")
    last_run = args.get("ARG_LAST_RUN", "")
    if not (state and round_ and head and last_run):
        log.error(USAGE_RENDER)
        return 2

    # An explicit argument WINS; otherwise the value carried in the previous body survives. That is what makes a round with nothing to say about the campaign (a label-armed round, say) preserve it instead of silently closing it.
    fields = {}
    for name, key in (
        ("campaign", "ARG_CAMPAIGN"),
        ("model", "ARG_MODEL"),
        ("rounds_max", "ARG_ROUNDS_MAX"),
        ("last_sig", "ARG_LAST_SIG"),
        ("sig_count", "ARG_SIG_COUNT"),
    ):
        given = args.get(key, "")
        if given:
            fields[name] = normalize_field(name, given)
        else:
            _, fields[name] = state_field(body, name)

    ledger: list[bytes] = []
    ruled: list[bytes] = []
    decisions: list[bytes] = []
    if body and _size_or_zero(body) > 0:
        ok, records = _awk_read(body)
        if not ok:
            # A top-level awk this time, so `set -e` DOES end the run. Contrast the five reads above, which sit inside `$( )`.
            return 2
        ledger, ruled, decisions = carry_over(records)

    if args.get("ARG_LEDGER", ""):
        ledger.append(cap_line(args["ARG_LEDGER"].encode("utf-8", "surrogateescape")))
    if args.get("ARG_RULED_OUT", ""):
        ruled.append(cap_line(b"- " + args["ARG_RULED_OUT"].encode("utf-8", "surrogateescape")))
    if args.get("ARG_DECISION", ""):
        decisions.append(cap_line(b"- " + args["ARG_DECISION"].encode("utf-8", "surrogateescape")))
    for key, dest in (("ARG_RULED_OUT_FILE", ruled), ("ARG_DECISIONS_FILE", decisions)):
        source = args.get(key, "")
        if source and _size_or_zero(source) > 0:
            code = _append_entries(source, dest)
            if code != 0:
                return code

    state_line = (
        "state: %s | round: %s | head: %s | last_run: %s | campaign: %s | model: %s "
        "| rounds_max: %s | last_sig: %s | sig_count: %s"
        % (
            state,
            round_,
            head,
            last_run,
            fields["campaign"],
            fields["model"],
            fields["rounds_max"],
            fields["last_sig"],
            fields["sig_count"],
        )
    ).encode("utf-8", "surrogateescape")

    rendered = render_body(state_line, ledger, ruled, decisions)
    if len(rendered) > COMPACT_BYTES:
        rendered = render_body(state_line, compact(ledger), ruled, decisions)
    sys.stdout.buffer.write(rendered)
    sys.stdout.buffer.flush()
    return 0


def _append_entries(source: str, dest: list[bytes]) -> int:
    """`append_entries` (state-comment.sh:197-204).

    THE ONE NAMED DIVERGENCE IN THIS PORT, and it is on fd 2 only. A DIRECTORY passes the `-s` test and bash then opens it successfully (Linux allows `open(2)` on a directory) but `read` fails, so the twin prints BASH'S OWN diagnostic --

        <path-as-invoked>: line 200: read: 0: read error: Is a directory

    -- appends nothing, and carries on with exit 0. The message names the twin's own file and line number, which no port can reproduce without lying about where it came from, so this port appends nothing and carries on SILENTLY. Exit code and stdout are identical; stderr differs by exactly that one line. Pinned by `test_a_directory_as_an_entries_file_is_the_one_named_divergence`,
    which asserts the difference is that line and nothing else -- so if the twin ever starts REFUSING here, the test goes red rather than the port drifting.
    """
    try:
        entries = read_entries(source)
    except OSError:
        return 0
    dest.extend(cap_line(b"- " + line) for line in entries)
    return 0


def _size_or_zero(path: str) -> int:
    try:
        return os.path.getsize(path)
    except OSError:
        return 0


def _fields(args: dict[str, str]) -> int:
    body = args.get("ARG_BODY", "")
    if not body:
        log.error(USAGE_FIELDS)
        return 2
    # An ABSENT body is not an error: no state comment yet is the normal first round, and it must read as "no campaign" rather than as a wiring failure.
    values = {}
    for name in ("campaign", "model", "rounds_max", "last_sig", "sig_count"):
        _, values[name] = state_field(body, name)
    return _jq(
        [
            "-cn",
            "--arg",
            "campaign",
            values["campaign"],
            "--arg",
            "model",
            values["model"],
            "--argjson",
            "rounds_max",
            values["rounds_max"],
            "--arg",
            "last_sig",
            values["last_sig"],
            "--argjson",
            "sig_count",
            values["sig_count"],
            FIELDS_PROGRAM,
        ]
    )


def main(argv: list[str]) -> int:
    # `cmd="${1:-}"; shift || true`: the subcommand is positional and never
    # reaches parse_args. With no arguments at all it is the empty string, which lands in the unknown arm.
    cmd = argv[0] if argv else ""
    try:
        args = common.parse_args(argv[1:])
    except common.RefusalError as exc:
        print("%s: %s" % (SELF, exc.lines[0]), file=sys.stderr, flush=True)
        return exc.code

    try:
        if cmd == "select":
            return _select(args)
        if cmd == "render":
            return _render(args)
        if cmd == "fields":
            return _fields(args)
    except common.RefusalError as exc:
        exc.report()
        return exc.code

    log.error(UNKNOWN_SUBCOMMAND % cmd)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
