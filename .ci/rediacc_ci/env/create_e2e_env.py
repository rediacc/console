#!/usr/bin/env python3
"""Port of `.ci/scripts/env/create-e2e-env.sh` (175 lines).

Write the `.env` file the E2E integration harness reads: VM network base and
offset, control-node and worker and Ceph VM ids, per-role RAM, image name,
bridge timeout, renet binary path, and three optional extras. The twin's header
owns the flag catalogue and the topology advice; it is not restated here.

LIVE CALLER, NOT REPOINTED. The bash twin stays the live implementation; this
module is its verified-equivalent alternative, and the cutover is a separate,
later, driver-only step.

Ledger: `.ci/shadow/w7p6-create-e2e-env.observations.jsonl`
(`npx tsx scripts/lib/shadow-gate.ts --pair w7p6-create-e2e-env --assert --k 5`).
Differential: `.ci/rediacc_ci/tests/test_env_create_e2e_env.py`.

THE PRODUCT IS THE FILE, NOT THE STREAMS. Everything this program prints goes
to stderr through `common.sh`'s logger, and `shadow-gate.ts` classifies a line
starting with a step or info glyph as CHATTER before any `--finding-re` sees
it. So a ledger row driven off the messages alone can only ever read
`VACUOUS_BOTH_EMPTY`. Both the pytest differential and the ledger therefore
compare the GENERATED FILE byte for byte, and the ledger's finding lines are
the file's own contents echoed with a distinctive prefix.

WHAT THIS SHELLS OUT TO, AND THE ONE THING IT DOES NOT. The twin runs no
network, renet or VM command: `--renet-path` defaults to a STRING built from
the repository root, and nothing probes the binary or asks `command -v` for it.
The only external command is `mkdir -p`, and this port keeps it as a
subprocess rather than calling `os.makedirs`, because the failure text belongs
to coreutils and not to the script. On this host `mkdir` is uutils coreutils
0.8.0, which prints `mkdir: Not a directory` where GNU prints
`mkdir: cannot create directory 'X': Not a directory`; reimplementing the
message would pin one vendor's spelling into a Python file and break the
differential the day the host's coreutils changes.

-----------------------------------------------------------------------------
DEFECT A -- A ZERO-PADDED RAM VALUE SILENTLY SKIPS THE WHOLE RAM BUDGET CHECK
-----------------------------------------------------------------------------
`assert_ram_budget` computes its total with `local total=$((bridge_ram +
worker_count * worker_ram + ceph_count * ceph_ram))` (twin :116). Bash reads a
leading-zero integer as OCTAL, so `08` and `09` are not integers at all, and
the arithmetic expansion fails. Two things then happen, both bad:

  1. `local` is a builtin whose own exit status is 0, so `set -e` never sees
     the failure. The function is abandoned at :116, which means the budget log
     line at :117 and the ceiling test at :118 NEVER RUN.
  2. The script continues and exits 0, having written the .env file.

Driven 2026-09-14 in the checkout:

    $ bash .ci/scripts/env/create-e2e-env.sh --output /tmp/b.env --vm-ram-worker 08
    .ci/scripts/env/create-e2e-env.sh: line 116: 08: value too great for base (error token is "08")
    -> Creating E2E test environment: /tmp/b.env
    (exit 0, file written, VM_RAM_WORKER=08)

The 14.5 GB ceiling exists so a topology that cannot fit a 16 GB runner is
refused BEFORE the VMs are booted. A zero-padded value defeats it completely:
`--vm-ram-worker 08192 --vm-workers "11 12 13 14"` writes the file and exits 0.
Every other arithmetic error class behaves the same way (`1 2`, `(`, `4096)`,
`1;ls`, and a value naming a set-but-non-numeric variable such as `HOME`), so
this is the general shape and not one bad digit: A MALFORMED INPUT IS SCORED AS
A CLEAN CHECK. Reproduced here exactly, including the skip; not repaired.

-----------------------------------------------------------------------------
DEFECT B -- THE WORKER/CEPH COUNT IS PATHNAME-EXPANDED AGAINST THE CURRENT
DIRECTORY
-----------------------------------------------------------------------------
Twin :111-114 counts nodes with `echo $VM_WORKERS | wc -w`, unquoted, carrying
`# shellcheck disable=SC2086`. That directive silences SC2086, which covers
BOTH word splitting (wanted here) and globbing (not wanted). So a value
containing `*`, `?` or `[` is expanded against the CURRENT WORKING DIRECTORY
and the RAM budget then depends on how many files happen to sit there:

    $ mkdir -p /tmp/g && cd /tmp/g && touch f1 f2 f3 f4 f5
    $ bash .ci/scripts/env/create-e2e-env.sh --output /tmp/g.env --vm-workers '*'
    (info) VM RAM budget: bridge 1024 + 5x4096 (worker) + 0x4096 (ceph) = 21504 MB
    (error) Requested VM RAM 21504 MB exceeds the 14848 MB ... budget
    (exit 1)

The same five-file directory with `--vm-workers '11 f?'` counts SIX workers.
The written file still records the literal `VM_WORKERS=*`, so the budget and
the artifact disagree. Reproduced (`_pathname_expand`); not repaired.

-----------------------------------------------------------------------------
DEFECT C -- `--output` WITH NO VALUE CREATES A FILE CALLED `true`
-----------------------------------------------------------------------------
`common.sh`'s `parse_args` turns a flag with no following value into the STRING
`true` (common.sh:341-344), and the only validation here is
`[[ -z "$OUTPUT" ]]` (twin :100). So a caller who writes `--output` and forgets
the path gets a file named `true` in the current directory and exit 0:

    $ cd /home/developer/console && bash .ci/scripts/env/create-e2e-env.sh --output
    -> Creating E2E test environment: true
    (exit 0)

That happened in this checkout while driving the twin, and the stray untracked
`true` had to be deleted by hand. Reproduced; not repaired.

-----------------------------------------------------------------------------
DEFECT D -- EVERY `ARG_*` NAME IS AN UNDOCUMENTED ENVIRONMENT VARIABLE
-----------------------------------------------------------------------------
`parse_args` assigns shell variables named `ARG_<FLAG>`, and the script reads
them with `${ARG_OUTPUT:-}`. A shell variable and an exported environment
variable are the same namespace, so `ARG_OUTPUT=/tmp/x.env` in the environment
works exactly like `--output /tmp/x.env`, with no flag at all (driven). This
port reproduces it -- `_shell_var` falls through to `os.environ` -- because a
differential that did not would diverge the first time a caller's environment
happened to carry one of these 14 names.

-----------------------------------------------------------------------------
THE ONE PLACE THIS PORT KNOWINGLY DIVERGES
-----------------------------------------------------------------------------
`arithmetic()`, over the `_Arith` parser below, implements bash's integer
CONSTANT grammar exactly (decimal, leading zero octal, `0x` hex, `base#digits`,
and the "value too great for base" error that Defect A rides on) plus
`+ - * / % **`, parentheses, unary `+`/`-`, and recursive variable lookup with
`set -u` semantics for an unset name. It does NOT implement bash's comparison,
bitwise, shift, logical, ternary, comma or assignment operators; a value using
one of those gets an `arithmetic syntax error` instead of bash's answer.

The cost is bounded and stated rather than hidden: those inputs are values of
`--vm-ram-worker` / `--vm-ram-ceph`, which are RAM figures in megabytes, and in
every one of them the twin ALSO reaches Defect A's skip-or-compute fork. So the
divergence usually changes only the diagnostic text. It changes the EXIT CODE
when the expression's value would cross the 14848 MB ceiling, because then the
twin refuses the topology and the port skips the check: `--vm-ram-worker '1<<13'`
is the shortest such input, and
`test_env_create_e2e_env.py::test_the_documented_divergence_on_an_unsupported_operator_is_real`
drives exactly it and asserts BOTH sides of the disagreement, so nobody
discovers this by accident.

A SECOND, SMALLER ONE: colour. `common.sh:18` enables colour when stderr is a
tty and `NO_COLOR` is unset, ignoring `CI`; `rediacc_ci.log` also disables it
under `CI=true`. That divergence is `rediacc_ci.log`'s, is documented there,
and is pinned by `test_log.py`; it is named here so a reader of this file does
not have to find it.
"""

from __future__ import annotations

import glob as globmod
import os
import re
import subprocess
import sys
from typing import NoReturn

from rediacc_ci import log
from rediacc_ci.core import common

# ---------------------------------------------------------------------------
# The twin's defaults, one constant per `${...:-default}` in the script.
# ---------------------------------------------------------------------------

DEFAULT_VM_NET_BASE = "192.168.111"  # twin :43
DEFAULT_VM_NET_OFFSET = "0"  # twin :44
DEFAULT_VM_CONTROL = "1"  # twin :48
DEFAULT_TIMEOUT = "120000"  # twin :49
DEFAULT_VM_WORKERS = "11 12"  # twin :74
DEFAULT_VM_CEPH_NODES = "21 22 23"  # twin :71
DEFAULT_VM_IMAGE = "ubuntu-24.04"  # twin :80

# `$(get_repo_root)/private/renet/bin/renet` (twin :50). A STRING, never probed:
# nothing here runs `command -v renet`, stats the path, or shells out to it.
RENET_RELATIVE_PATH = "private/renet/bin/renet"

# The budget, twin :106-109. The bridge is fixed by the kvm driver; the ceiling
# is 14.5 GB so a 16 GB runner keeps headroom for QEMU and the host.
BRIDGE_RAM_MB = 1024
FALLBACK_ROLE_RAM_MB = "4096"  # renet's VMRAM, as a STRING: the twin's `${X:-4096}`
CEILING_MB = 14848

# The expression the twin evaluates at :116, verbatim. Kept as source text
# rather than as Python arithmetic because Defect A is a property of PARSING
# it, and a Python expression cannot fail the way bash's does.
BUDGET_EXPRESSION = "bridge_ram + worker_count * worker_ram + ceph_count * ceph_ram"

# Line numbers bash prints inside its own diagnostics, pinned so a drift in the
# twin is a test failure rather than a silent text change. Re-derived by
# `test_the_pinned_twin_line_numbers_still_point_at_the_right_lines`.
ARITH_LINE = 116  # `local total=$((...))`
HEREDOC_LINE = 132  # `cat >"$OUTPUT" <<EOF`
PRINTF_LINE = 333  # common.sh's `printf -v "$key"`, inside parse_args

# The twin's own path, as `${BASH_SOURCE[0]}` spells it in a diagnostic: the
# script's directory, then the unnormalised `../lib/common.sh`.
TWIN_RELATIVE_DIR = ".ci/scripts/env"

USAGE = "Usage: create-e2e-env.sh --output <path> [options]"  # twin :101

# The heredoc at twin :132-156. `\$RUNNER_TEMP` is escaped in the twin, so the
# literal dollar reaches the file; every other `$NAME` is a substitution.
FILE_TEMPLATE = """\
# E2E Test Environment
# Generated by .ci/scripts/env/create-e2e-env.sh
# Note: PROVISION_CEPH_CLUSTER is inferred from VM_CEPH_NODES (if set, Ceph provisioning is enabled)
# Note: Renet auto-detects data directory via CI env var (uses $RUNNER_TEMP/renet in CI)

VM_NET_BASE={VM_NET_BASE}
VM_NET_OFFSET={VM_NET_OFFSET}
VM_CONTROL={VM_BRIDGE}
VM_BRIDGE={VM_BRIDGE}
VM_WORKERS={VM_WORKERS}
VM_CEPH_NODES={VM_CEPH_NODES}
VM_IMAGE={VM_IMAGE_VALUE}
CEPH_MODE={CEPH_MODE}
VM_RAM_WORKER={VM_RAM_WORKER}
VM_RAM_CEPH={VM_RAM_CEPH}
CEPH_OSD_MEMORY_TARGET={CEPH_OSD_MEMORY_TARGET}
PROVISION_CEPH_CLUSTER={PROVISION_CEPH_CLUSTER}
BRIDGE_TIMEOUT={TIMEOUT}
RENET_BINARY_PATH={RENET_PATH}
CI={CI}
NODE_ENV=test
"""


class RefusalError(Exception):
    """Exit with a status, after whatever has already been printed."""

    def __init__(self, code: int) -> None:
        super().__init__(code)
        self.code = code


# ---------------------------------------------------------------------------
# `dirname`, as coreutils implements it (twin :127)
# ---------------------------------------------------------------------------


def dirname(path: str) -> str:
    """POSIX `dirname`, NOT `os.path.dirname`, and the difference is observable.

    `os.path.dirname("a/")` is `"a"`; coreutils `dirname a/` is `"."`. Since the
    result is handed straight to `mkdir -p`, the two answers create different
    directories, and `--output out/` is not an exotic input.

    Driven against `/usr/bin/dirname` over a table in the differential test.
    """
    stripped = path.rstrip("/")
    if not stripped:
        # Every character was a slash: `/`, `//`, `///` all answer `/`.
        return "/" if path else "."
    if "/" not in stripped:
        return "."
    head = stripped[: stripped.rindex("/")].rstrip("/")
    return head or "/"


# ---------------------------------------------------------------------------
# `echo $VALUE | wc -w` (twin :112 and :114) -- see DEFECT B
# ---------------------------------------------------------------------------

# What bash's pathname expansion looks for before it touches the filesystem. A
# word with none of these is passed through untouched and costs no syscall.
_GLOB_METACHARACTERS = ("*", "?", "[")

# `echo`'s option words: any run of n/e/E after a single dash, and only while
# they lead. `-ne` is one word setting both; `-x` ends option parsing.
_ECHO_OPTION = re.compile(r"^-[neE]+$")

# The escapes `echo -e` interprets. `\c` is handled separately: it truncates.
_ECHO_ESCAPES = {
    "a": "\a",
    "b": "\b",
    "e": "\x1b",
    "E": "\x1b",
    "f": "\f",
    "n": "\n",
    "r": "\r",
    "t": "\t",
    "v": "\v",
    "\\": "\\",
}
_ECHO_ESCAPE_TOKEN = re.compile(r"\\(0[0-7]{0,3}|x[0-9A-Fa-f]{1,2}|.)")


def _pathname_expand(word: str) -> list[str]:
    """One word after splitting, expanded against the cwd. DEFECT B lives here.

    Bash keeps the word literally when the pattern matches nothing (nullglob is
    off), and skips dotfiles, both of which `glob.glob` already does. The order
    of the matches differs from bash's collation and does not matter: the only
    consumer counts them.
    """
    if not any(char in word for char in _GLOB_METACHARACTERS):
        return [word]
    matches = globmod.glob(word)
    return sorted(matches) if matches else [word]


def _echo_e(text: str) -> str:
    """`echo -e`'s backslash interpretation, including `\\c`'s truncation."""
    out: list[str] = []
    index = 0
    while index < len(text):
        match = _ECHO_ESCAPE_TOKEN.search(text, index)
        if match is None:
            out.append(text[index:])
            break
        out.append(text[index : match.start()])
        body = match.group(1)
        index = match.end()
        if body == "c":
            return "".join(out)
        if body.startswith("0"):
            out.append(chr(int(body[1:] or "0", 8) & 0xFF))
        elif body.startswith("x"):
            out.append(chr(int(body[1:], 16)))
        else:
            out.append(_ECHO_ESCAPES.get(body, "\\" + body))
    return "".join(out)


def word_count(value: str) -> int:
    """`echo $VALUE | wc -w`, reproduced in four steps, in bash's order.

    Split on IFS, pathname-expand each word (DEFECT B), let `echo` eat its
    leading option words, then count whitespace-separated tokens in what it
    printed. Step three is not academic: `--vm-workers '-n'` prints nothing and
    counts ZERO workers, and `--vm-workers '-e 11 12'` counts two (both driven).
    """
    argv: list[str] = []
    for word in value.split():
        argv.extend(_pathname_expand(word))

    interpret = False
    index = 0
    while index < len(argv) and _ECHO_OPTION.match(argv[index]):
        if "e" in argv[index]:
            interpret = True
        if "E" in argv[index]:
            interpret = False
        index += 1

    text = " ".join(argv[index:])
    if interpret:
        text = _echo_e(text)
    return len(text.split())


# ---------------------------------------------------------------------------
# `$((...))` (twin :116) -- see DEFECT A
# ---------------------------------------------------------------------------


class ArithError(Exception):
    """An arithmetic failure the twin's `local total=$((...))` SWALLOWS.

    Carries the EXPRESSION as well as the reason because bash prints the
    innermost expression it was evaluating, not the outermost: with
    `--vm-ram-worker 08` the message names `08`, not the whole budget
    expression the `08` was substituted into.
    """

    def __init__(self, expression: str, reason: str) -> None:
        super().__init__("%s: %s" % (expression, reason))
        self.expression = expression
        self.reason = reason


class UnboundVariableError(Exception):
    """`set -u` firing inside the arithmetic. FATAL, unlike ArithError.

    The asymmetry is bash's: an arithmetic error makes one command fail (and
    `local` hides even that), while an unset variable under `set -u` exits the
    shell outright. `--vm-ram-worker abc` exits 1; `--vm-ram-worker 08` exits 0.
    """

    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.name = name


_ARITH_TOKEN = re.compile(
    r"\s*(?:(?P<num>[0-9][0-9A-Za-z_@#]*)"
    r"|(?P<name>[A-Za-z_][A-Za-z0-9_]*)"
    r"|(?P<op>\*\*|[-+*/%()]))"
)

# The characters that can begin ANY bash arithmetic token, used only to pick
# between bash's two leftover-input messages. A leftover starting with one of
# these is "syntax error in expression"; anything else is "invalid arithmetic
# operator" (driven: `4096)` gives the first, `1;ls` the second).
_TOKEN_START = re.compile(r"[0-9A-Za-z_(){}\[\]+\-*/%<>=!~^&|?:,]")

_MAX_ARITH_DEPTH = 32


def _digit_value(char: str) -> int | None:
    """Bash's digit alphabet: 0-9, then a-z / A-Z, then `@` and `_`."""
    if char.isdigit():
        return ord(char) - ord("0")
    if "a" <= char <= "z":
        return ord(char) - ord("a") + 10
    if "A" <= char <= "Z":
        return ord(char) - ord("A") + 10
    return None


def _number(token: str, expression: str) -> int:
    """A bash integer constant. The leading-zero octal rule is DEFECT A's root."""
    if "#" in token:
        base_text, _, digits = token.partition("#")
        base = int(base_text) if base_text.isdigit() else 0
    elif token[:2].lower() == "0x":
        base, digits = 16, token[2:]
    elif token.startswith("0") and len(token) > 1:
        base, digits = 8, token[1:]
    else:
        base, digits = 10, token

    if not digits or base < 2 or base > 64:
        raise ArithError(expression, 'invalid number (error token is "%s")' % token)
    value = 0
    for char in digits:
        digit = _digit_value(char)
        if digit is None or digit >= base:
            raise ArithError(expression, 'value too great for base (error token is "%s")' % token)
        value = value * base + digit
    return value


def _truncating_div(left: int, right: int, expression: str) -> int:
    """C semantics, which is what bash uses: `-7/2` is -3, not Python's -4."""
    if right == 0:
        raise ArithError(expression, 'division by 0 (error token is "%d")' % right)
    quotient = abs(left) // abs(right)
    return -quotient if (left < 0) != (right < 0) else quotient


class _Arith:
    """Recursive descent over the subset named in the module docstring."""

    def __init__(self, text: str, scope: dict[str, str], depth: int) -> None:
        self.text = text
        self.scope = scope
        self.depth = depth
        self.pos = 0
        self.last = ""

    # -- lexer ------------------------------------------------------------

    def peek(self) -> tuple[str, str] | None:
        match = _ARITH_TOKEN.match(self.text, self.pos)
        if match is None:
            return None
        kind = match.lastgroup or ""
        return kind, match.group(kind)

    def take(self) -> tuple[str, str]:
        match = _ARITH_TOKEN.match(self.text, self.pos)
        if match is None:
            self.operand_expected()
        self.pos = match.end()
        kind = match.lastgroup or ""
        self.last = match.group(kind)
        return kind, self.last

    def rest(self) -> str:
        return self.text[self.pos :].strip()

    def operand_expected(self) -> NoReturn:
        # Bash names the remaining input; when the input is exhausted it names
        # the token it last consumed (driven: `(` reports `(`).
        offender = self.rest() or self.last
        raise ArithError(
            self.text, 'arithmetic syntax error: operand expected (error token is "%s")' % offender
        )

    # -- grammar ----------------------------------------------------------

    def expression(self) -> int:
        value = self.term()
        while True:
            head = self.peek()
            if head is None or head[0] != "op" or head[1] not in ("+", "-"):
                return value
            _, operator = self.take()
            right = self.term()
            value = value + right if operator == "+" else value - right

    def term(self) -> int:
        value = self.power()
        while True:
            head = self.peek()
            if head is None or head[0] != "op" or head[1] not in ("*", "/", "%"):
                return value
            _, operator = self.take()
            right = self.power()
            if operator == "*":
                value *= right
            elif operator == "/":
                value = _truncating_div(value, right, self.text)
            else:
                value -= _truncating_div(value, right, self.text) * right

    def power(self) -> int:
        value = self.unary()
        head = self.peek()
        if head is not None and head == ("op", "**"):
            self.take()
            return value ** self.power()
        return value

    def unary(self) -> int:
        head = self.peek()
        if head is not None and head[0] == "op" and head[1] in ("+", "-"):
            _, operator = self.take()
            value = self.unary()
            return -value if operator == "-" else value
        return self.primary()

    def primary(self) -> int:
        head = self.peek()
        if head is None:
            self.operand_expected()
        kind, text = head
        if kind == "op" and text == "(":
            self.take()
            value = self.expression()
            closing = self.peek()
            if closing is None or closing != ("op", ")"):
                raise ArithError(
                    self.text,
                    'arithmetic syntax error in expression (error token is "%s")' % self.rest(),
                )
            self.take()
            return value
        if kind == "num":
            self.take()
            return _number(text, self.text)
        if kind == "name":
            self.take()
            return self.variable(text)
        return self.operand_expected()

    def variable(self, name: str) -> int:
        if name not in self.scope:
            raise UnboundVariableError(name)
        value = self.scope[name].strip()
        if not value:
            return 0
        if self.depth >= _MAX_ARITH_DEPTH:
            raise ArithError(self.text, "expression recursion level exceeded")
        return _evaluate(value, self.scope, self.depth + 1)


def _evaluate(text: str, scope: dict[str, str], depth: int = 0) -> int:
    parser = _Arith(text, scope, depth)
    value = parser.expression()
    leftover = parser.rest()
    if leftover:
        reason = (
            'arithmetic syntax error in expression (error token is "%s")'
            if _TOKEN_START.match(leftover)
            else 'arithmetic syntax error: invalid arithmetic operator (error token is "%s")'
        )
        raise ArithError(text, reason % leftover)
    return value


def arithmetic(text: str, scope: dict[str, str]) -> int:
    """`$((text))` with `scope` as the shell's variable namespace."""
    return _evaluate(text, scope, 0)


# ---------------------------------------------------------------------------
# `${ARG_X:-...}` -- see DEFECT D
# ---------------------------------------------------------------------------


def _shell_var(args: dict[str, str], name: str) -> str:
    """The value of shell variable `name` where the twin reads it.

    `parse_args` writes into the SAME namespace the environment seeded, so a
    flag overwrites an inherited value and an absent flag leaves it in place.
    The environment is read at THIS call site rather than through a captured
    `dict(os.environ)` alias, deliberately.
    """
    if name in args:
        return args[name]
    return os.environ.get(name, "")


def shell_namespace(args: dict[str, str], scope: dict[str, str]) -> dict[str, str]:
    """Every name `$((...))` can resolve, in the order bash would resolve it.

    NOT an environment ALIAS, and the distinction matters. Nothing here reads a
    configuration value out of this dict; every setting is read from
    `os.environ` at its own call site in `settings()`. This models bash's single
    variable NAMESPACE, which is the thing `--vm-ram-worker HOME` reaches: the
    inherited environment, then `parse_args`' `ARG_*` assignments, then the
    script's own globals, each layer shadowing the last exactly as bash does.

    The five colour names and `SCRIPT_DIR` are in scope in the twin too
    (common.sh:18-32, twin :38). The colours are given their non-tty values,
    which is every run this differential makes; on a tty the twin would hold an
    escape sequence there and `--vm-ram-worker RED` would fail differently.
    """
    namespace = dict(os.environ)
    namespace.update(args)
    namespace.update(scope)
    namespace.update(
        {
            "SCRIPT_DIR": "%s/%s" % (common.repo_root(), TWIN_RELATIVE_DIR),
            "RED": "",
            "GREEN": "",
            "YELLOW": "",
            "BLUE": "",
            "CYAN": "",
            "NC": "",
        }
    )
    return namespace


def assert_ram_budget(scope: dict[str, str], namespace: dict[str, str], prog: str) -> None:
    """Twin :105-124. Returns normally when the check is SKIPPED -- see DEFECT A."""
    worker_ram = scope["VM_RAM_WORKER"] or FALLBACK_ROLE_RAM_MB
    ceph_ram = scope["VM_RAM_CEPH"] or FALLBACK_ROLE_RAM_MB
    worker_count = word_count(scope["VM_WORKERS"]) if scope["VM_WORKERS"] else 0
    ceph_count = word_count(scope["VM_CEPH_NODES"]) if scope["VM_CEPH_NODES"] else 0

    locals_ = dict(namespace)
    locals_.update(
        {
            "worker_ram": worker_ram,
            "ceph_ram": ceph_ram,
            "bridge_ram": str(BRIDGE_RAM_MB),
            "ceiling_mb": str(CEILING_MB),
            "worker_count": str(worker_count),
            "ceph_count": str(ceph_count),
        }
    )

    try:
        total = arithmetic(BUDGET_EXPRESSION, locals_)
    except ArithError as failure:
        # DEFECT A: bash prints this, `local` hides the non-zero status, and the
        # function is abandoned. The budget is NEVER CHECKED and the caller
        # carries on to write the file.
        _bash_diagnostic(prog, ARITH_LINE, "%s: %s" % (failure.expression, failure.reason))
        return
    except UnboundVariableError as failure:
        # `set -u` is fatal even though the arithmetic error above is not.
        _bash_diagnostic(prog, ARITH_LINE, "%s: unbound variable" % failure.name)
        raise RefusalError(1) from None

    log.info(
        "VM RAM budget: bridge %d + %dx%s (worker) + %dx%s (ceph) = %d MB"
        % (BRIDGE_RAM_MB, worker_count, worker_ram, ceph_count, ceph_ram, total)
    )
    if total > CEILING_MB:
        log.error(
            "Requested VM RAM %d MB exceeds the %d MB (14.5 GB) budget for a 16 GB runner."
            % (total, CEILING_MB)
        )
        log.error("Lower --vm-ram-worker/--vm-ram-ceph or reduce node counts.")
        raise RefusalError(1)


def _bash_diagnostic(prog: str, line: int, message: str) -> None:
    """`<prog>: line <N>: <message>`, bash's own shape, on stderr.

    Reproduced rather than reworded because the differential compares bytes and
    because these lines are the ONLY evidence a caller gets that Defect A fired.
    """
    sys.stderr.write("%s: line %d: %s\n" % (prog, line, message))
    sys.stderr.flush()


def render(scope: dict[str, str]) -> str:
    """The heredoc body (twin :132-156) plus the three conditional extras."""
    body = FILE_TEMPLATE.format(CI=os.environ.get("CI", "") or "true", **scope)
    if scope["VM_NET_NAME"]:
        body += "VM_NET=%s\n" % scope["VM_NET_NAME"]
    if scope["DOCKER_REGISTRY_VALUE"]:
        body += "DOCKER_REGISTRY=%s\n" % scope["DOCKER_REGISTRY_VALUE"]
    if scope["K8S_TOGGLE"] == "true":
        body += "K8S_MODE=1\n"
    return body


def settings(args: dict[str, str]) -> dict[str, str]:
    """Twin :42-97, in the twin's own order, as one namespace."""
    ceph_mode = _shell_var(args, "ARG_CEPH") or "false"
    if ceph_mode == "true":
        vm_workers = ""
        vm_ceph_nodes = _shell_var(args, "ARG_VM_CEPH_NODES") or DEFAULT_VM_CEPH_NODES
    else:
        vm_workers = _shell_var(args, "ARG_VM_WORKERS") or DEFAULT_VM_WORKERS
        vm_ceph_nodes = _shell_var(args, "ARG_VM_CEPH_NODES")

    renet_path = (
        _shell_var(args, "ARG_RENET_PATH")
        or os.environ.get("RENET_BINARY", "")
        # Evaluated LAST and only when needed, matching bash's lazy `${X:-$(...)}`.
        or "%s/%s" % (common.repo_root(), RENET_RELATIVE_PATH)
    )

    return {
        "OUTPUT": _shell_var(args, "ARG_OUTPUT"),
        "VM_NET_BASE": _shell_var(args, "ARG_VM_NET_BASE") or DEFAULT_VM_NET_BASE,
        "VM_NET_OFFSET": _shell_var(args, "ARG_VM_NET_OFFSET") or DEFAULT_VM_NET_OFFSET,
        "VM_BRIDGE": (
            _shell_var(args, "ARG_VM_CONTROL")
            or _shell_var(args, "ARG_VM_BRIDGE")
            or DEFAULT_VM_CONTROL
        ),
        "TIMEOUT": (
            _shell_var(args, "ARG_TIMEOUT")
            or os.environ.get("BRIDGE_TIMEOUT", "")
            or DEFAULT_TIMEOUT
        ),
        "RENET_PATH": renet_path,
        "VM_NET_NAME": _shell_var(args, "ARG_VM_NET"),
        "DOCKER_REGISTRY_VALUE": _shell_var(args, "ARG_DOCKER_REGISTRY"),
        "K8S_TOGGLE": _shell_var(args, "ARG_K8S") or "false",
        "CEPH_MODE": ceph_mode,
        "VM_WORKERS": vm_workers,
        "VM_CEPH_NODES": vm_ceph_nodes,
        "VM_IMAGE_VALUE": (
            _shell_var(args, "ARG_VM_IMAGE") or os.environ.get("VM_IMAGE", "") or DEFAULT_VM_IMAGE
        ),
        "VM_RAM_WORKER": (
            _shell_var(args, "ARG_VM_RAM_WORKER") or os.environ.get("VM_RAM_WORKER", "")
        ),
        "VM_RAM_CEPH": _shell_var(args, "ARG_VM_RAM_CEPH") or os.environ.get("VM_RAM_CEPH", ""),
        "CEPH_OSD_MEMORY_TARGET": (
            _shell_var(args, "ARG_CEPH_OSD_MEMORY_TARGET")
            or os.environ.get("CEPH_OSD_MEMORY_TARGET", "")
        ),
        # Twin :90-97: written EXPLICITLY rather than left to renet's inference,
        # because renet also sources a parent-directory .env.
        "PROVISION_CEPH_CLUSTER": "true" if vm_ceph_nodes else "false",
    }


def _write(path: str, body: str, prog: str) -> None:
    try:
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(body)
    except OSError as failure:
        # `bash: line 132: <path>: Is a directory` / `Permission denied`. Bash
        # reports the redirection's strerror, so this does too.
        _bash_diagnostic(prog, HEREDOC_LINE, "%s: %s" % (path, failure.strerror))
        raise RefusalError(1) from None


def main(argv: list[str]) -> int:
    prog = sys.argv[0]
    try:
        args = common.parse_args(argv)
    except common.RefusalError as failure:
        # common.sh:333, and the path bash prints is the twin's unnormalised
        # `$SCRIPT_DIR/../lib/common.sh`. Reproduced verbatim so the bytes match.
        _bash_diagnostic(
            "%s/%s/../lib/common.sh" % (common.repo_root(), TWIN_RELATIVE_DIR),
            PRINTF_LINE,
            str(failure),
        )
        return failure.code

    scope = settings(args)

    if not scope["OUTPUT"]:
        log.error(USAGE)
        return 1

    try:
        assert_ram_budget(scope, shell_namespace(args, scope), prog)
    except RefusalError as refusal:
        return refusal.code

    # `mkdir -p "$OUTPUT_DIR"` under `set -e`: the twin exits with mkdir's own
    # status and lets mkdir's own message reach stderr untouched.
    completed = subprocess.run(["mkdir", "-p", dirname(scope["OUTPUT"])], check=False)
    if completed.returncode != 0:
        return completed.returncode

    log.step("Creating E2E test environment: %s" % scope["OUTPUT"])
    try:
        _write(scope["OUTPUT"], render(scope), prog)
    except RefusalError as refusal:
        return refusal.code
    log.info("Created E2E test environment: %s" % scope["OUTPUT"])

    if os.environ.get("DEBUG", "false") == "true":
        print()
        print("Contents:")
        with open(scope["OUTPUT"], encoding="utf-8") as handle:
            sys.stdout.write(handle.read())
        sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
