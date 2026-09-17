"""Reading a `KEY=value` file without `source`.

PORTED FROM THE SIX BASH SITES THAT READ ONE TODAY, not from a single function.
`docs/ci-overhaul/08-driver-contract.md:64` names this module as the home of
`env_file_load`, and the name is aspirational: there is no `env_file_load` in
`.ci/lib/local-common.sh` or anywhere else in the tree. The operation exists,
six times, in two mutually incompatible spellings. Consolidating them is the
whole job, so all six are listed here rather than in a commit message:

    .ci/lib/account.sh:437-440        set -a; source "$ACCOUNT_DIR/.env"; set +a
    .ci/lib/account.sh:790-793        the same three lines again, for E2E
    .ci/scripts/lib/toolchain.sh:33-37  set -a; . "$f"; set +a, for the pins
    .ci/legacy/run-legacy.sh:185      env_vars=$(set -a && source ... && env)
    rdc.sh:246-248                    grep + cut, DELIBERATELY not source
    .ci/lib/local-common.sh:814-815   sed -n 's/^KEY=//p' | tr -d 'CR'

--------------------------------------------------------------------------
WHY THIS PARSES AND NEVER EXECUTES
--------------------------------------------------------------------------
`rdc.sh:240-245` is the receipt, and it is worth quoting because it is the one
comment in the tree that states the threat model:

    Read EXACTLY two values from the dev gateway's env file, by grep. NEVER
    `source` it (not even with `set -a`): private/account/.env also holds
    ACCOUNT_ED25519_PRIVATE_KEY, ACCOUNT_X25519_PRIVATE_KEY, ACCOUNT_JWT_SECRET
    and ACCOUNT_SERVER_API_KEY, and sourcing would leak every one of those
    secrets into the CLI process environment.

`source` is not a parser. It is a shell executing a file, so it also runs
command substitutions, honours `$(...)`, and exports EVERY key including the
four above into a process that needs two of them. `.ci/scripts/test/
test-rdc-sh-env.sh` is a standing gate over exactly that rule for `rdc.sh`, and
this module is how the other five sites get to obey it too: nothing here
executes the file, and a caller asks for the names it wants.

--------------------------------------------------------------------------
WHY THE SHELL WINS OVER THE FILE
--------------------------------------------------------------------------
This INVERTS `set -a; source`, which lets the file overwrite the shell, and the
inversion is deliberate rather than incidental.

`.ci/lib/account.sh:432-440` is the case this was written from, and the
specifics were WRONG until 2026-09-09: `account_allocate_ports` computes
GATEWAY_PORT into the shell four lines before `source .env`, but GATEWAY_PORT is
not a key the file has ever carried (measured against the live
`private/account/.env`, and against the template at `.ci/lib/account.sh:206-250`
that writes it). What the file DOES carry, and therefore did overwrite, is
`PORT`, `ROOT_EMAIL`, `REDIACC_ACCOUNT_SERVER` and `WEBAUTHN_ORIGIN`. The
argument is unchanged and the fix is the same; only the example was fiction, and
a fiction in the paragraph explaining WHY is the kind that gets quoted onward.
Every override this repo ships arrives
through the environment -- a workflow `env:` block, a `GITHUB_ENV` append, a
developer typing `PORT=4900 ./run.sh` -- and file-wins silently discards all of
them in favour of a value written to disk months earlier. An override that is
ignored without a word is worse than one that is refused.

So: a key already carried by the environment keeps its value, and the file
supplies only what the environment does not have.

AN EMPTY ENVIRONMENT VALUE DOES NOT WIN. `.ci/lib/bws-env.sh:100-104` already
ruled on this, in its own words: "An empty value is treated as ABSENT on
purpose: zod strips an unknown key and sm-action exports \"\" without
complaint, so a blank ships a broken feature that still returns 200." The same
reasoning applies here, and applying it in the same way keeps the two answers
from drifting.

--------------------------------------------------------------------------
MISSING IS NORMAL, UNREADABLE IS A DEFECT
--------------------------------------------------------------------------
`.ci/scripts/lib/toolchain.sh:29-32` conflates them: `[[ -r "$f" ]]` fails
identically for an absent file and for one whose mode is 0000, and reports
"pins file missing or unreadable". That is fine for a pins file which must
exist. It is wrong for `.env`, because `.ci/lib/account.sh:311-313` treats
absence as a NORMAL state meaning "generate it".

Conflating the two turns a permissions defect into "no keys configured", which
is a diagnosis that sends the reader to the wrong file. So absence returns an
empty mapping and unreadability raises `EnvFileError`.

--------------------------------------------------------------------------
THE TWO PLACES THIS DELIBERATELY DIVERGES FROM `source`
--------------------------------------------------------------------------
1. AN UNQUOTED `#` IS PART OF THE VALUE. bash would end the assignment at a
   space-preceded `#` and treat the rest as a comment, so `KEY=a#b # note`
   assigns `a#b` but `KEY=abc # note` assigns `abc`. Faithfulness here would
   mean silently truncating a credential at a character that is legal inside
   base64 and inside a URL fragment. The only writer of these files
   (`.ci/lib/account.sh:254-260`) puts every comment on its own line, so the
   divergence has no live caller to break.

2. WHITESPACE AROUND THE VALUE IS STRIPPED. bash reads `KEY= value` as the
   COMMAND `value` carrying a temporary assignment prefix `KEY=`, so the
   variable exists for that one command's environment and the shell keeps
   nothing at all -- `KEY` is not merely empty afterwards, it is unset.
   (Measured, not reasoned: the first draft of this paragraph said "an empty
   assignment followed by an attempt to run `value`", and the differential in
   test_core_env.py caught the difference.) Nobody depends on that; a human who
   types it means the value.

Everything else follows `source`: the LAST assignment of a key wins (which is
what `rdc.sh:247` spells `tail -1`), single quotes are literal, and inside
double quotes a backslash is special only before `$`, a backtick, `"` or
another backslash.

CRLF IS HANDLED BECAUSE IT HAS ALREADY BITTEN. `.ci/lib/local-common.sh:815`
ends its extraction with `tr -d 'CR'` -- a carriage return that would otherwise
ride on the end of the public key and make every signature check fail with a
value that LOOKS right in a log. Here it costs no code at all: see `_lines` for
why `str.splitlines()` is the whole answer, and for the dead guard that was
written before that was checked.

--------------------------------------------------------------------------
COMMAND-LINE ENTRY POINT (what a bash caller invokes)
--------------------------------------------------------------------------
    python3 -m rediacc_ci.core.env keys <file>
        the key names, one per line, in file order. Never a value.

    python3 -m rediacc_ci.core.env get <file> <key>
        ONE value on stdout, no trailing decoration. Exit 1 when the key is
        absent, so `set -e` sees it. This is the rdc.sh:247 pipeline.

    python3 -m rediacc_ci.core.env export <file> [name...]
        shell-quoted `export K=V` lines for `eval`. With names, only those;
        with none, every key the environment does not already carry.

`export` prints values, which is unavoidable for a shim whose job is to put
them into a shell. Prefer the name-list form for the reason rdc.sh:240 gives,
and never run it under `set -x`.
"""

from __future__ import annotations

import os
import re
import shlex
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # `pathlib` is reached only by the PathLike annotations below
    import pathlib

# A key, with the optional `export ` bash allows in front of it. Anchored at the start of the LEFT-STRIPPED line, and the key class is bash's own (`[A-Za-z_][A-Za-z0-9_]*`) rather than a looser one, because a looser pattern
# would accept `2FA_CODE=` -- a line `source` refuses -- and hand back a name no
# shell could ever hold.
#
# The `[ \t]+` after `export` is what makes `exported=1` a key called `exported`
# instead of a key called `ed`. That is not hypothetical enough to leave to chance: the obvious `^(export )?` with a lazy split does exactly that.
_ASSIGNMENT = re.compile(r"^(?:export[ \t]+)?([A-Za-z_][A-Za-z0-9_]*)=(.*)$")

# The bytes a UTF-8 BOM decodes to. A file written by a Windows editor carries one, and without this the first key is named `<BOM>KEY` -- present in the mapping, absent to every caller that asks for `KEY`, and invisible in a diff.
_BOM = "\ufeff"

# Inside double quotes bash makes a backslash special before exactly these four characters and NOWHERE else, so `"a\nb"` is the six characters it looks like and not a newline. Getting this wrong in the friendly direction (treating `\n` as a newline, the way dotenv does) would change the meaning of values that work today.
_DOUBLE_QUOTE_ESCAPABLE = '$`"\\'


class EnvFileError(RuntimeError):
    """The file exists and could not be read. Absence is not this."""


def parse(text: str) -> dict[str, str]:
    """Every assignment in `text`, last-wins, values unquoted.

    Pure: no filesystem, no environment. The differential against bash lives on
    this function, because a comparison that also has to build a file is a
    comparison that can fail for a reason that is not the parser.
    """
    pairs: dict[str, str] = {}
    for _lineno, key, raw in _assignments(text):
        pairs[key] = _unquote(raw)
    return pairs


def skipped(text: str) -> list[tuple[int, str]]:
    """The 1-based lines that are neither blank, comment, nor an assignment.

    Exposed rather than swallowed. A line silently dropped is how a typo in a
    key name becomes an absence nobody can see, and `source` at least fails
    loudly on it. Callers that want the loud behaviour check this and refuse;
    callers that want the tolerant one ignore it. Both are honest.
    """
    out: list[tuple[int, str]] = []
    for lineno, line in _lines(text):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if _ASSIGNMENT.match(line.lstrip()) is None:
            out.append((lineno, line))
    return out


def read_pairs(
    path: pathlib.Path | str,
    *,
    missing_ok: bool = True,
) -> dict[str, str]:
    """`parse` over a file. Absent yields {}; unreadable raises.

    See the module docstring on why those two are not the same answer.
    """
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            text = handle.read()
    except FileNotFoundError:
        if missing_ok:
            return {}
        raise EnvFileError("env file does not exist: %s" % path) from None
    except OSError as err:
        # PermissionError, IsADirectoryError, a dangling symlink target, a device that returns EIO. All of them mean the file is THERE and the answer is unavailable, which is the case that must never read as "no keys configured".
        raise EnvFileError("cannot read env file %s: %s" % (path, err)) from err
    return parse(text)


def env_file_load(
    path: pathlib.Path | str,
    environ: dict[str, str] | None = None,
    *,
    missing_ok: bool = True,
) -> dict[str, str]:
    """The EFFECTIVE value of every key the file names. The shell wins.

    The returned mapping is keyed by the FILE's keys only -- it is not a merged
    copy of the environment -- so a caller can see exactly what the file has to
    say and what the environment overrode, without the other few hundred
    variables in the way.
    """
    env = os.environ if environ is None else environ
    pairs = read_pairs(path, missing_ok=missing_ok)
    return {key: env.get(key) or value for key, value in pairs.items()}


def overridden(
    path: pathlib.Path | str,
    environ: dict[str, str] | None = None,
    *,
    missing_ok: bool = True,
) -> list[str]:
    """Sorted names where the environment won and the file's value was not used.

    Names, never values: this is the thing a caller prints when it wants the
    reader to understand why the file on disk is not what took effect.
    """
    env = os.environ if environ is None else environ
    pairs = read_pairs(path, missing_ok=missing_ok)
    return sorted(key for key, value in pairs.items() if env.get(key) and env[key] != value)


def apply(
    path: pathlib.Path | str,
    environ: dict[str, str] | None = None,
    *,
    names: list[str] | None = None,
    missing_ok: bool = True,
) -> list[str]:
    """Put the file's keys into `environ` where it does not already carry them.

    Returns the sorted names ASSIGNED. This is the `set -a; source` replacement,
    minus the execution and minus the file-wins precedence.

    `names` restricts it to the keys the caller asked for, which is the
    rdc.sh:246-248 posture generalised: a process that needs two values does not
    have to take forty-nine.
    """
    env = os.environ if environ is None else environ
    pairs = read_pairs(path, missing_ok=missing_ok)
    keep = None if names is None else set(names)
    wanted = pairs if keep is None else {k: v for k, v in pairs.items() if k in keep}
    assigned = []
    for key, value in wanted.items():
        if env.get(key):
            continue
        env[key] = value
        assigned.append(key)
    return sorted(assigned)


def unredacted_value(
    path: pathlib.Path | str,
    key: str,
    environ: dict[str, str] | None = None,
    *,
    missing_ok: bool = True,
) -> str | None:
    """THE VALUE of one key, or None. Named so the call site cannot pretend.

    Every other function here hands back names, counts or a mapping a caller
    chose to build. This one hands back a secret if the key names one, so it
    says so in its own name -- the same rule `rediacc_ci.core.secrets` states
    for itself, applied to the one function in this module that needs it.
    """
    return env_file_load(path, environ, missing_ok=missing_ok).get(key)


def keys(path: pathlib.Path | str, *, missing_ok: bool = True) -> list[str]:
    """The key names in FILE ORDER, deduplicated to the last occurrence.

    File order rather than sorted, because the order is how a human reads the
    file, and `keys` is what a diagnostic prints.
    """
    return list(read_pairs(path, missing_ok=missing_ok))


# --------------------------------------------------------------------------- the line classifier, shared by parse() and skipped() so they cannot disagree ---------------------------------------------------------------------------


def _lines(text: str) -> list[tuple[int, str]]:
    """1-based lines, CRLF and BOM removed.

    `str.splitlines()` IS THE CRLF HANDLING, on its own. It treats a CR, an LF
    and a CRLF as one boundary each and returns none of them, so a line from a
    Windows-written file arrives with no carriage return on it and there is
    nothing left to strip.

    That is worth stating because the first draft did not believe it and added
    `raw.rstrip("CR")` here as well. The line was DEAD: planting a defect that
    deleted it left all 36 cases in test_core_env.py green, including two
    written specifically to catch it. A guard that cannot fail is the shape this
    repository hunts, so it is gone rather than kept for comfort, and this
    paragraph is what stops it being re-added.

    See `.ci/lib/local-common.sh:815` for what a surviving CR costs and why the
    bash had to say `tr -d` at all: a carriage return riding on the end of a
    public key, which looks right in a log and fails every signature check. The
    bash was reading with `sed -n`, which has no notion of a CRLF file; this
    reads with a function that does.
    """
    out = []
    for index, raw in enumerate(text.splitlines(), start=1):
        # The BOM only ever sits on the first line, so the strip is conditional rather than applied to every line: a caller whose VALUE legitimately begins with U+FEFF keeps it.
        out.append((index, raw.lstrip(_BOM) if index == 1 else raw))
    return out


def _assignments(text: str) -> list[tuple[int, str, str]]:
    out = []
    for lineno, line in _lines(text):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = _ASSIGNMENT.match(line.lstrip())
        if match is None:
            continue
        out.append((lineno, match.group(1), match.group(2)))
    return out


def _unquote(raw: str) -> str:
    """Strip one layer of matching quotes and apply bash's escape rules.

    An UNTERMINATED quote is taken literally rather than raising. `source` would
    refuse the whole file, and refusing forty-eight good keys over one bad line
    is the wrong trade for a loader whose absence-of-answer already has a
    meaning. The line is still visible: it parsed as an assignment, so its value
    simply starts with a quote character, which is what a reader sees.
    """
    value = raw.strip()
    if len(value) >= 2 and value[0] == value[-1]:
        if value[0] == "'":
            # Single quotes in bash are absolute: no escape, not even for a backslash. There is no way to put a single quote inside them.
            return value[1:-1]
        if value[0] == '"':
            return _unescape_double(value[1:-1])
    return value


def _unescape_double(body: str) -> str:
    out: list[str] = []
    index = 0
    while index < len(body):
        char = body[index]
        if char == "\\" and index + 1 < len(body) and body[index + 1] in _DOUBLE_QUOTE_ESCAPABLE:
            out.append(body[index + 1])
            index += 2
            continue
        out.append(char)
        index += 1
    return "".join(out)


# --------------------------------------------------------------------------- argv dispatch -- the surface a bash caller invokes ---------------------------------------------------------------------------


def main(argv: list[str]) -> int:
    if not argv:
        print("usage: python3 -m rediacc_ci.core.env <verb> [args]", file=sys.stderr)
        return 2
    verb, rest = argv[0], argv[1:]

    try:
        if verb == "keys":
            for key in keys(rest[0]):
                print(key)
            return 0
        if verb == "get":
            # Exit 1 rather than printing an empty line, so `set -e` and a bare `if !` both see the absence. The rdc.sh pipeline it replaces printed nothing and returned 0, which is why rdc.sh:252 has to test the captured string separately.
            value = unredacted_value(rest[0], rest[1])
            if value is None:
                return 1
            print(value)
            return 0
        if verb == "export":
            wanted = rest[1:] or None
            path = rest[0]
            pairs = read_pairs(path)
            if wanted is not None:
                pairs = {k: v for k, v in pairs.items() if k in set(wanted)}
            for key, value in pairs.items():
                if os.environ.get(key):
                    continue
                print("export %s=%s" % (key, shlex.quote(value)))
            return 0
    except EnvFileError as err:
        print("env: %s" % err, file=sys.stderr)
        return 1
    except IndexError:
        print("env: %s needs more arguments" % verb, file=sys.stderr)
        return 2

    print("unknown verb: %s" % verb, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
