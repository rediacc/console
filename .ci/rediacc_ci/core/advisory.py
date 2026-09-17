"""AI-navigable advisory emission, ported from `.ci/scripts/lib/emit-advisory.sh`.

PORTED FROM `.ci/scripts/lib/emit-advisory.sh` (218 lines), which still exists and is still sourced by four callers. This module does NOT shim it: deletion and cutover are a later step, so both implementations are live and `.ci/rediacc_ci/tests/test_core_advisory.py` is the differential that says they agree, byte for byte, on both streams.

WHAT THE PORT DELETES, WHICH IS MOST OF THE FILE. 108 of the twin's 218 lines are comment, and roughly half of that comment exists because of ONE bash fact: bash 3.2 has no `declare -A`. The twin opens with a version guard, a refusal message naming `brew install bash`, and a measured account of what happens without it --
`ADV_SEVERITY[lodash]=critical` aborting the caller with "lodash: unbound
variable" while EXITING ZERO, so a security gate reports PASS having emitted nothing. A Python dict has no such branch to write, so the guard, the refusal and the second `declare -A` refusal all disappear rather than being translated. That is the same argument `rediacc_ci.core.ports` makes about `_sha256sum_portable`, arriving from the other direction: the portability code existed
only because bash lacks the data structure.

THE DEFERENCE RULE DOES NOT TRANSLATE EITHER, AND ITS ABSENCE IS THE POINT. The
twin guards every colour assignment with `${RED+x}` and every logger definition
with `declare -F`, because it is sourced BOTH standalone AND transitively after
`common.sh` has installed its own TTY-gated logger, and in the second case
common.sh must win. `rediacc_ci.log` already records why that is "not a design;
it is two implementations agreeing to take turns". An imported module has no second definition to defer to.

  CONSEQUENCE FOR THE DIFFERENTIAL, STATED SO NOBODY READS MORE INTO IT THAN IS
  THERE: this module reproduces the twin's STANDALONE branch. The transitive
  branch is a statement about `common.sh`, which is a later box, and a
  differential that sourced common.sh first would be measuring common.sh's
  logger while appearing to measure this one.

THE COLOUR RULE HERE IS NOT `rediacc_ci.log`'s, AND THE DIFFERENCE IS DELIBERATE. `log.py` colours on a tty and suppresses under CI or NO_COLOR. The twin tests `CI` AND NOTHING ELSE -- no `isatty`, no NO_COLOR -- so a developer piping a gate into `less` gets escape sequences. That is one of the nine files `log.py`'s header counts as the CI-only variant. Reproducing it is what makes
this a PORT
rather than an improvement; a port that quietly fixed the behaviour would
disagree with the live twin on every non-CI invocation, which is every local run.

TWO STREAMS, AND THE SPLIT IS LOAD-BEARING. `ci_error` off CI writes to STDERR. Every continuation line -- Affected, Summary, Fix, Action, Details -- is a plain `echo` and goes to STDOUT. So one advisory straddles both streams, and a caller that merges them with `2>&1` sees a coherent block while a caller that does not sees the header in one place and the body in another. That is
the twin's behaviour, it is surprising, and it is pinned by a case rather than tidied, because `audit.sh` and `age-check.sh` are reading it as it stands.

`echo -e` IS REPRODUCED, NOT DROPPED. `log_error` is `echo -e "${RED}✗ $*${NC}"`,
which INTERPRETS backslash escapes in the message: an advisory naming a Windows path or a regex prints a tab where the caller wrote `\\t`. `rediacc_ci.log` deliberately diverges there and pins the divergence. This module cannot, because its whole claim is byte equality with the live twin, so `_echo_e` below implements the sequences bash's builtin does. The divergence between the
two Python modules is therefore real and intentional: `log` is the replacement logger, `advisory` is the port.

`emit_advisory` ALWAYS SUCCEEDS. The twin ends with a bare `return 0`, and its own comment says why: "so `set -e` callers don't trip on the trailing conditional". There is nothing to trip on in Python, but the signature keeps the promise, because a caller reading the twin's contract will not have written an error path for it.
"""

import os
import re
import sys
from typing import ClassVar

# The escapes, from the twin's non-CI branch. YELLOW is `1;33`, matching
# common.sh rather than `.ci/bootstrap.sh`'s `0;33`; the twin chose that and the
# port does not get to re-choose it.
RED = "\033[0;31m"
GREEN = "\033[0;32m"
YELLOW = "\033[1;33m"
NC = "\033[0m"

# The six continuation prefixes, exactly as the twin spells them, INCLUDING the two leading spaces and the arrow. ` → Patched in:` carries two spaces on
# each side of the arrow in the twin; a single space would be an invisible
# difference that no reviewer catches and every differential does.
AFFECTED = "  Affected: %s"
PATCHED_SUFFIX = "  →  Patched in: %s"
SUMMARY = "  Summary: %s"
FIX = "  Fix: %s"
ACTION = "  Action: %s"
DETAILS = "  Details: %s"

# The twin's default when a range is unknown but a patched version is not. A literal rather than an empty string, because ` Affected: ` with nothing after it reads as a rendering bug to whoever sees it in a log.
UNKNOWN_RANGE = "unknown"

# `echo -e`'s escape table, less `\c` which is handled separately because it TRUNCATES rather than substitutes. `\e` and `\E` are the bash extension over
# POSIX; both are accepted by the builtin.
_ECHO_E_SIMPLE = {
    "a": "\a",
    "b": "\b",
    "e": "\033",
    "E": "\033",
    "f": "\f",
    "n": "\n",
    "r": "\r",
    "t": "\t",
    "v": "\v",
    "\\": "\\",
}

_ECHO_E_TOKEN = re.compile(r"\\(0[0-7]{0,3}|x[0-9a-fA-F]{1,2}|c|.)", re.DOTALL)

# The `\c` marker. NUL cannot appear in a bash argument, so it cannot collide
# with anything a caller could pass through the same path.
_TRUNCATE = "\0TRUNCATE\0"


def _echo_e_sub(match: "re.Match") -> str:
    """One `\\x` token, resolved the way the bash builtin resolves it.

    THE OCTAL FORM NEEDS THE LEADING ZERO AND `\\101` IS LITERAL. Measured: `echo -e '\\101'` prints `\\101`, `echo -e '\\0101'` prints `A`. That is the opposite of `printf`, and the opposite of what a table copied from a C reference would say, so it is asserted against the real builtin in `test_core_advisory.py` rather than trusted.
    """
    body = match.group(1)
    if body == "c":
        return _TRUNCATE
    if body.startswith("0"):
        digits = body[1:]
        return chr(int(digits, 8) & 0xFF) if digits else "\0"
    if body.startswith("x") and len(body) > 1:
        return chr(int(body[1:], 16))
    return _ECHO_E_SIMPLE.get(body, "\\" + body)


# The program's field separator. THE FIELD SEPARATOR IS US (`\x1f`), NOT TAB, AND THAT IS A BUG THIS FILE ALREADY
# PAID FOR. The first draft used tab. TAB IS IFS WHITESPACE IN BASH, so `IFS=$'\t'
# read -r a b c` COLLAPSES consecutive tabs into one delimiter and an empty field simply disappears, shifting every later field left. Measured on the first run of this differential: a case with an empty `name` made the bash side read the FIX hint as the name and print a different header, and the comparator reported a STDOUT-DIFF that looked exactly like a port defect. It was a
# defect in the DRIVER. `\x1f` is not IFS whitespace, so empty fields survive on both sides, and an empty field is a case this contract has to be able to express.
SEP = "\x1f"

USAGE = """advisory -- the `emit-advisory.sh` emitters, driven from stdin.

Program lines, separated by US (0x1f, NOT tab -- see SEP above):
  meta  <table> <id> <value>              one metadata cell
  emit  <level> <id> <name> <fix> [action]

  <table> is one of: severity title ghsa url range patched desc
  <level> is error or warn

Exit: 0 the program ran, 2 the program itself was unusable.
"""


def _echo_e_parts(text: str) -> tuple[str, bool]:
    """`(what echo -e writes, whether \\c truncated it)`.

    THE SECOND HALF IS NOT PEDANTRY. `echo -e 'a\\cb'` writes `a` and NO TRAILING NEWLINE -- measured, `cat -A` shows `a` with no `$`. A port that always appended one would differ by a byte on exactly the input a caller used to suppress it. `_echo_e` below drops the flag for the many callers that only want the text.
    """
    out = _ECHO_E_TOKEN.sub(_echo_e_sub, text)
    marker = out.find(_TRUNCATE)
    if marker < 0:
        return out, False
    return out[:marker], True


def _echo_e(text: str) -> str:
    """What `echo -e` writes for `text`, minus the trailing newline.

    WHY A HAND-ROLLED TABLE AND NOT `codecs.decode(text, "unicode_escape")`. The two are not the same function and the difference is not academic. Bash interprets `\\0nnn` as OCTAL with a leading zero and leaves an unrecognised
    `\\q` as the two literal characters; `unicode_escape` reads `\\nnn` without
    the zero, understands `\\uXXXX` and `\\N{...}` which bash does not, and
    mangles every non-ASCII character on the way through because it decodes latin-1. An advisory title containing `→` would come back as mojibake, which is precisely the kind of difference a differential is for and a convenience function is how it gets introduced.
    """

    return _echo_e_parts(text)[0]


def in_ci(env: dict | None = None) -> bool:
    """`[[ "${CI:-}" == "true" ]]`. The string, not a truthiness test.

    `CI=1` is FALSE here, and that is not a bug to fix: the twin compares
    against the literal `true`, and a port that accepted `1` would start emitting GitHub annotations on any machine where some other tool exports
    `CI=1`.
    """
    environ = os.environ if env is None else env
    return environ.get("CI", "") == "true"


def _colours(env: dict | None = None) -> tuple[str, str, str, str]:
    """(RED, GREEN, YELLOW, NC), emptied under CI as the twin empties them."""
    if in_ci(env):
        return "", "", "", ""
    return RED, GREEN, YELLOW, NC


def _emit(text: str, stream) -> None:
    """`echo -e "<text>"`: the bytes, then a newline unless `\\c` ate it."""
    body, truncated = _echo_e_parts(text)
    stream.write(body if truncated else body + "\n")


def log_error(message: str, *, env: dict | None = None, stream=None) -> None:
    """`echo -e "${RED}✗ $*${NC}" >&2`."""
    red, _, _, nc = _colours(env)
    _emit("%s✗ %s%s" % (red, message, nc), stream or sys.stderr)


def log_success(message: str, *, env: dict | None = None, stream=None) -> None:
    """`echo -e "${GREEN}✓ $*${NC}"` -- STDOUT, unlike the other three."""
    _, green, _, nc = _colours(env)
    _emit("%s✓ %s%s" % (green, message, nc), stream or sys.stdout)


def log_warn(message: str, *, env: dict | None = None, stream=None) -> None:
    """`echo -e "${YELLOW}⚠ $*${NC}"` -- STDOUT in the twin's standalone branch."""
    _, _, yellow, nc = _colours(env)
    _emit("%s⚠ %s%s" % (yellow, message, nc), stream or sys.stdout)


def log_info(message: str, *, stream=None) -> None:
    """`echo -e "→ $*"` -- no colour at all in the twin, so none here.

    NO `env=` HERE, unlike its three siblings, and the asymmetry is the point:
    this level has no colour to suppress, so there is nothing for the environment to decide. A parameter accepted and ignored is a promise the
    function does not keep.
    """
    _emit("→ %s" % message, stream or sys.stdout)


def ci_error(message: str, *, env: dict | None = None) -> None:
    """`::error::<m>` on STDOUT under CI, `✗ <m>` on STDERR otherwise.

    THE STREAM CHANGES WITH THE ENVIRONMENT, which is worth saying because it reads as a bug and is the twin's actual behaviour: an annotation has to be on stdout for GitHub to parse it, and a human-facing error belongs on stderr. A caller that captures only one stream therefore sees the message in CI and not locally, or the reverse.
    """
    if in_ci(env):
        print("::error::%s" % message)
    else:
        log_error(message, env=env)


def ci_warn(message: str, *, env: dict | None = None) -> None:
    """`::warning::<m>` on STDOUT under CI, `⚠ <m>` on STDOUT otherwise."""
    if in_ci(env):
        print("::warning::%s" % message)
    else:
        log_warn(message, env=env)


class Advisories:
    """The seven optional `ADV_*` tables, as one object instead of seven globals.

    The twin declares `ADV_URL ADV_TITLE ADV_SEVERITY ADV_GHSA ADV_VULN_RANGE ADV_PATCHED_VERSION ADV_DESC_PREVIEW` as associative arrays in the caller's
    shell and reads them with `${ADV_X[$id]:-}`. Every one is optional and an
    absent entry is skipped, so the empty string and the missing key are the same thing here as there -- which is why `get` defaults to `""` rather than raising or returning None.

    ONE OBJECT RATHER THAN SEVEN MODULE DICTS because seven globals is what the twin had to have and is the reason its `declare -A` failure mode existed at all. A caller can still keep a process-wide instance if it wants the twin's
    lifetime exactly; `MODULE_ADVISORIES` below is that instance.
    """

    TABLES: ClassVar[tuple[str, ...]] = (
        "severity",
        "title",
        "ghsa",
        "url",
        "range",
        "patched",
        "desc",
    )

    # The twin's variable name per table, so an error message can name the thing the reader will grep for in bash rather than the thing this file calls it.
    BASH_NAME: ClassVar[dict[str, str]] = {
        "severity": "ADV_SEVERITY",
        "title": "ADV_TITLE",
        "ghsa": "ADV_GHSA",
        "url": "ADV_URL",
        "range": "ADV_VULN_RANGE",
        "patched": "ADV_PATCHED_VERSION",
        "desc": "ADV_DESC_PREVIEW",
    }

    def __init__(self) -> None:
        self.tables: dict[str, dict[str, str]] = {name: {} for name in self.TABLES}

    def set(self, table: str, ident: str, value: str) -> None:
        if table not in self.tables:
            raise KeyError(
                "no advisory table %r; the seven are %s" % (table, ", ".join(self.TABLES))
            )
        self.tables[table][ident] = value

    def get(self, table: str, ident: str) -> str:
        return self.tables[table].get(ident, "")

    def clear(self) -> None:
        for table in self.tables.values():
            table.clear()


MODULE_ADVISORIES = Advisories()


def header_for(ident: str, name: str, severity: str, ghsa: str, title: str) -> str:
    """The twin's header composition, extracted so it can be asserted directly.

    `id`, then a parenthesised comma-joined list of whichever of name / severity
    / ghsa are non-empty, then `: title` if there is one. The `${parens:+$parens, }`
    idiom in the twin means the separator appears only between present values, so a missing name does NOT leave a leading comma -- the single most likely thing for a naive port to get wrong, and the reason this is a function.
    """
    parens = ", ".join(part for part in (name, severity, ghsa) if part)
    head = "%s (%s)" % (ident, parens) if parens else ident
    return "%s: %s" % (head, title) if title else head


def emit_advisory(
    level: str,
    ident: str,
    name: str,
    fix_hint: str,
    action_hint: str = "",
    *,
    advisories: Advisories | None = None,
    env: dict | None = None,
) -> int:
    """`emit_advisory <level> <id> <name> <fix_hint> [action_hint]`. Always 0.

    An UNKNOWN level is the one place this cannot match the twin and must not pretend to. Bash runs `"ci_$level" "$header"`, so `emit_advisory notice ...` dies with `ci_notice: command not found` and a 127 that `set -e` turns into an aborted gate. Raising here is the nearest honest equivalent: both refuse, both name the bad level, and neither invents an emitter. It is called out
    rather than buried because the differential deliberately does not compare that case.
    """
    table = MODULE_ADVISORIES if advisories is None else advisories
    if level not in ("error", "warn"):
        raise ValueError(
            "emit_advisory level must be 'error' or 'warn' (got %r). The bash twin "
            "resolves `ci_%s` as a command and dies with 127; there is no emitter to "
            "fall back to." % (level, level)
        )

    severity = table.get("severity", ident)
    ghsa = table.get("ghsa", ident)
    title = table.get("title", ident)
    url = table.get("url", ident)
    vuln_range = table.get("range", ident)
    patched = table.get("patched", ident)
    desc = table.get("desc", ident)

    header = header_for(ident, name, severity, ghsa, title)
    (ci_error if level == "error" else ci_warn)(header, env=env)

    if vuln_range or patched:
        line = AFFECTED % (vuln_range or UNKNOWN_RANGE)
        if patched:
            line += PATCHED_SUFFIX % patched
        print(line)
    if desc:
        print(SUMMARY % desc)
    if fix_hint:
        print(FIX % fix_hint)
    if action_hint:
        print(ACTION % action_hint)
    if url:
        print(DETAILS % url)
    return 0


def run_program(lines: list[str], advisories: Advisories | None = None) -> int:
    """Interpret the US-separated program. 0, or 2 for a program this cannot run.

    ZERO `emit` LINES IS A REFUSAL. A driver that set metadata and emitted nothing would exit 0 having produced no output, which is indistinguishable
    from a clean run of a gate that found nothing -- the shape a differential
    would record as EQUIVALENT while proving neither side works.
    """
    table = Advisories() if advisories is None else advisories
    program = [line for line in lines if line.strip()]
    emitted = 0
    for raw in program:
        fields = raw.rstrip("\n").split(SEP)
        verb = fields[0]
        if verb == "meta":
            if len(fields) != 4:
                print("advisory: `meta` needs table, id, value.", file=sys.stderr)
                return 2
            try:
                table.set(fields[1], fields[2], fields[3])
            except KeyError as exc:
                print("advisory: %s" % exc.args[0], file=sys.stderr)
                return 2
        elif verb == "emit":
            if len(fields) not in (5, 6):
                print(
                    "advisory: `emit` needs level, id, name, fix and an optional action.",
                    file=sys.stderr,
                )
                return 2
            action = fields[5] if len(fields) == 6 else ""
            try:
                emit_advisory(fields[1], fields[2], fields[3], fields[4], action, advisories=table)
            except ValueError as exc:
                print("advisory: %s" % exc.args[0], file=sys.stderr)
                return 2
            emitted += 1
        else:
            print(
                "advisory: unknown verb %r; the program understands `meta` and `emit`." % (verb,),
                file=sys.stderr,
            )
            return 2
    if emitted == 0:
        print(
            "advisory: the program emitted zero advisories, so it proves nothing.\n"
            "  An empty run and a working run are the same bytes; that is not a pass.",
            file=sys.stderr,
        )
        return 2
    return 0


def main(argv: list[str]) -> int:
    if "--help" in argv or "-h" in argv:
        print(USAGE)
        return 0
    return run_program(sys.stdin.read().splitlines())


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
