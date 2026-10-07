"""check:ci-gh-retry-reads, shell half -- every GitHub READ made from SHELL retries a transient fault.

WHY THIS EXISTS. The Python half (`rediacc_ci.quality.gh_retry_reads`) scans only Python, so the live orphan reaper `.ci/breakpoint/scripts/reap-breakpoint-orphans.sh` (run by housekeeping.yml) kept a one-shot `curl ... api.github.com` read nobody flagged until commit ec583bbda gave it `--retry 2 --retry-delay 5`. Writing this half found a worse one: CI's release decision, `rediacc_ci.ci.initialize` (ci.yml and cd-v2.yml), still EXECUTES the bash
`dispatch-release.sh` and `detect-bump-type.sh`, whose one-shot `gh api .../commits/<sha>/pulls` reads are the wrong-release-on-a-5xx class PLAN-gh-retry fixed only in their Python twins. They were frozen in SHELL_DEBT until initialize cut over to the retried Python ports (2026-10-07); both bash scripts are dead twins now, and SHELL_DEBT is empty.

WHAT IS SCANNED.
  * Shell scripts (`*.sh`, `*.bash`) under `.ci` (minus `.ci/cache` and test paths, by `gh_retry_reads.is_test_path`) and `scripts`.
  * Every `run:` block of `.github/workflows/*.yml` and of the composite actions `.github/actions/*/action.yml` (the actions are workflow code by another name, so they ride along). Block (`|`) and folded (`>`) scalars are both read; a folded line break is read as a bash line continuation, which is what folding makes it.
The text is LEXED, not grepped: quotes, `$(...)`, backticks, `${...}`, `$'...'`, heredoc bodies (skipped), comments and backslash-newline continuations are all understood, so `curl -sS \\` on one line and its URL three lines down are ONE command, `echo "gh api"` is not a call, and `${x#gh api}` is not a call.

WHAT IS A SITE, AND WHEN IT IS RETRIED.
  curl  A curl command whose URL names the GitHub API: the literal `api.github.com`, the Actions expression `github.api_url` / `$GITHUB_API_URL`, a `.ci/config/well-known.env` key whose value is the API (`WK_GH_API_BASE`), or a variable assigned any of these in the same text (`GH_API="https://api.github.com"`, to a fixpoint, so `URL="${GH_API}/x"` counts too). A WRITE is `-X/--request POST|PATCH|PUT|DELETE`, or a body flag (`-d`, `--data*`, `--json`, `-F`, `-T`) without `-G`; a computed `-X "$m"` is UNRESOLVED and counts as a read. RETRIED means a literal `--retry N`
        with N >= 1 (curl then retries timeouts, 408, 429, 500, 502, 503 and 504, and nothing else), or a `retry_with_backoff` wrapper.
  gh    A `gh` command at command position (after assignments, `if`/`!`/`then`/`do`, `command`, `env`, `sudo`, a `timeout` launcher). Read or write is `gh_retry_reads.classify`, the SAME classifier the Python half uses, so the two halves cannot disagree about a verb. RETRIED means `.ci/scripts/lib/common.sh`'s `gh_retry <what> -- <args>` / `gh_json <what> -- <args>` (three attempts), or `retry_with_backoff`. common.sh's `_gh_probe` IS the retry, so its own `gh "$@"` is IMPLEMENTATION, not a site.
A WRITE is reported as information and never retried, by design: a retried POST after a lost response creates a second run, release or comment.

THE TWIN RULE (why most shell `gh` is not judged). The 2026-10 ports left bash TWINS of the Python modules under `.ci/scripts`; their `gh` reads were fixed in the ports, and the twins survive only as differential oracles. A hand list of twins would rot the day one is wired back, so the exclusion is COMPUTED: a script is judged only if it is LIVE, meaning a live executor names it, transitively:
  * a workflow or composite-action `run:` block;
  * a `package.json` script (the root and `packages/*`);
  * a non-docstring string constant in a non-test Python module under `.ci`, `scripts` or `.claude` (this is how `rediacc_ci.ci.initialize` reaches `dispatch-release.sh`, and why that twin is NOT dead);
  * a non-comment line of a non-test TS/JS file under `scripts` or `.github/actions`, a Dockerfile under `.ci` / `.devcontainer` / the root, a `.devcontainer/*.json`, or a root-level `*.sh` (`run.sh`, `rdc.sh`);
  * a non-comment line of a script that is itself live (sourcing `lib/common.sh`, calling `$SCRIPT_DIR/x.sh`, or a `"$DIR"/tutorial-*.sh` glob in the same directory).
A name is matched by its path TAIL (`version/detect-bump-type.sh`, `../lib/common.sh`); a bare basename counts only inside a same-directory script, or inside a Python constant that holds no whitespace (a path, not a usage message). Over-counting life is the deliberate direction: a twin wrongly read as live costs a visible finding, a live script wrongly read as dead would hide a read. Every dead script that holds an unretried GitHub read is PRINTED (`TWIN`) on every run, so the exclusion cannot quietly grow.

BLIND SPOTS, stated so a green is not read as more than it is:
  * A script reached only by a computed path (`"$dir/$name.sh"`) or by a `find ... -exec` is read as dead. The TWIN lines are where that would show.
  * An extensionless shell script (a Rediaccfile) is not in the corpus; none under the scan roots reads GitHub (measured 2026-10-07).
  * A hand-rolled bash retry loop around `gh` or `curl` is not recognised; route it through common.sh, or excuse it in ALLOWED with a BLOCKER.
  * `wget`, and reads of `raw.githubusercontent.com` / `github.com` (not the API), are out of scope.

ANTI-VACUITY. Zero scripts, zero live scripts, zero workflow `run:` blocks, zero curl GitHub sites, zero gh sites, zero retried reads or zero writes FAILS: each is the signature of a lexer or a liveness walk that stopped seeing the tree. An unlexable text that names gh or curl is UNPARSEABLE, never clean. Controls run first, then three REAL-TREE plants in memory: the reaper with its `--retry 2 --retry-delay 5` removed must add exactly one finding on the reaper; a one-shot `gh api` line inserted into a real workflow `run:` block must add one; and a reference to a dead twin that holds a read, planted into the same block, must make that twin live and add its reads.

ALLOWED AND SHELL_DEBT. ALLOWED excuses a read that genuinely cannot be retried, by `<path>::<qualname>`, with a `BLOCKER:` reason (validated by `rediacc_ci.core.allowlist`) and a liveness check: an entry that excuses nothing is STALE and fails. SHELL_DEBT freezes reads that must be FIXED, by an id hashing the site's TEXT (path, function or job/step, tool, verb, argv), never its line: a new read fails, and a debt row the tree no longer fills fails as DRAINED until the row is deleted by hand. There is no `--write-baseline` here on purpose: a hand edit of one line is the drain, and it cannot absorb a fresh finding.

Exit codes: 0 clean, 1 a finding (or a stale/invalid entry, a drained debt row, a vacuous scan), 2 an instrument control or a real-tree plant failed.
"""

from __future__ import annotations

import argparse
import ast
import dataclasses
import fnmatch
import functools
import hashlib
import json
import os
import pathlib
import re
import sys

from rediacc_ci import paths
from rediacc_ci.controls import Checker, controls_first, plant
from rediacc_ci.core import allowlist
from rediacc_ci.quality import gh_retry_reads as py

NAME = "gh retry reads (shell)"
SELF_REL = ".ci/rediacc_ci/quality/gh_retry_shell.py"
DRIVER_REL = ".ci/scripts/quality/check_gh_retry_reads.py"
SCRIPT_ROOTS = (".ci", "scripts")
EXCLUDED_DIRS = (".ci/cache/",)
WORKFLOW_GLOBS = (
    ".github/workflows/*.yml",
    ".github/workflows/*.yaml",
    ".github/actions/*/action.yml",
    ".github/actions/*/action.yaml",
)
WELL_KNOWN_REL = ".ci/config/well-known.env"
# `GITHUB_API_URL` is set by the Actions runner itself; `github.api_url` is the same value as an expression.
GH_API_GLOBALS = frozenset({"GITHUB_API_URL"})
GH_API_LITERALS = ("api.github.com", "github.api_url")
# common.sh's retry ladder: its `gh "$@"` IS the retry, so scanning it would report the retry as its own violation.
IMPLEMENTATION = frozenset({(".ci/scripts/lib/common.sh", "_gh_probe")})
# Gates INSPECT scripts: their path tables are data, and a gate that does run a script (dispatch-release's decision gate) runs it against a shimmed `gh`, never GitHub. So no gate module is an executor; this module and its driver are inside these too.
GATE_DIRS = (
    ".ci/rediacc_ci/quality/",
    ".ci/rediacc_ci/security/",
    ".ci/scripts/quality/",
    "scripts/gates/",
)
REAPER_REL = ".ci/breakpoint/scripts/reap-breakpoint-orphans.sh"
# The reaper's retry, as a pattern so a retuned count (`--retry 3`) keeps the plant working.
REAPER_RETRY = re.compile(r"[ \t]+--retry[ =]\d+(?:[ \t]+--retry-delay[ =]\d+)?")

# ---------------------------------------------------------------------------
# ALLOWED: shell reads that stay one-shot, by <path>::<qualname>, each with a BLOCKER reason. Empty on 2026-10-07: every live one-shot read found was a defect, so it went to SHELL_DEBT, not here. Do not add an entry to get a red gate green.
# ---------------------------------------------------------------------------
ALLOWED: dict[str, str] = {}

# ---------------------------------------------------------------------------
# SHELL_DEBT: live one-shot reads that must be FIXED, frozen so the gate fails on GROWTH. id -> the site, for the reader. Delete a row by hand when its read is routed (the gate reds it as DRAINED until then). Never add a row for a new read.
# ---------------------------------------------------------------------------
SHELL_DEBT: dict[str, str] = {}

FIX_CURL = (
    "add `--retry 2 --retry-delay 5`; curl then retries a timeout, 408, 429 and 5xx only, so a single 5xx is retried and a 4xx still fails at once. "
    "Do not add it to SHELL_DEBT, and do not add it to ALLOWED unless the read genuinely cannot be retried, and then say why as a BLOCKER."
)
FIX_GH = (
    "source .ci/scripts/lib/common.sh and call `gh_retry <what> -- <gh args>` (or `gh_json` when the body must be JSON), or move the read into Python through "
    "rediacc_ci.core.gh_retry. Do not add it to SHELL_DEBT, and do not add it to ALLOWED unless the read genuinely cannot be retried, and then say why as a BLOCKER."
)

# ---------------------------------------------------------------------------
# The lexer.
# ---------------------------------------------------------------------------


class ShellParseError(ValueError):
    """Text the lexer cannot read; the caller reports it as UNPARSEABLE, never as clean."""


@dataclasses.dataclass(frozen=True)
class Word:
    """One shell word: quotes removed, expansions kept verbatim (`${GH_API}/x`), `$(...)` shown as `$(...)`."""

    text: str
    line: int
    dyn: bool = False  # holds an expansion
    whole: str = ""  # "one" when the word IS a single expansion, "star" when it expands to many


@dataclasses.dataclass(frozen=True)
class Command:
    words: tuple[Word, ...]


_WORD_END = frozenset(" \t\r\n;&|()<>")
_REDIRECT = re.compile(r"(?:\d+|&)?(?:<<<|>>|>&|>\||<&|<>|>|<)")
_DOLLAR_NAME = re.compile(r"[A-Za-z_]\w*|[@*#?$!0-9-]")


class _Lexer:
    """Commands out of shell text. Each command is the words between two control operators; a `$(...)`, backtick or `<(...)` body is lexed into commands of its own."""

    def __init__(self, text: str) -> None:
        self.s = text
        self.n = len(text)
        self.i = 0
        self.line = 1
        self.commands: list[Command] = []
        self.heredocs: list[tuple[str, bool]] = []

    def peek(self, k: int = 0) -> str:
        j = self.i + k
        return self.s[j] if j < self.n else ""

    def run(self) -> list[Command]:
        self._commands(None)
        return self.commands

    def _commands(self, stop: str | None) -> None:
        cur: list[Word] = []
        depth = 0

        def flush() -> None:
            if cur:
                self.commands.append(Command(tuple(cur)))
                cur.clear()

        while self.i < self.n:
            c = self.s[self.i]
            if c == "\\" and self.peek(1) == "\n":
                self.i += 2
                self.line += 1
                continue
            if c == "\n":
                flush()
                self.i += 1
                self.line += 1
                self._heredoc_bodies()
                continue
            if c in " \t\r":
                self.i += 1
                continue
            if c == "#":
                while self.i < self.n and self.s[self.i] != "\n":
                    self.i += 1
                continue
            if stop == "`" and c == "`":
                flush()
                self.i += 1
                return
            if stop == ")" and c == ")" and depth == 0:
                flush()
                self.i += 1
                return
            if c in "<>" and self.peek(1) == "(":
                self.i += 2
                self._commands(")")
                continue
            if self.s.startswith("<<", self.i) and not self.s.startswith("<<<", self.i):
                self.i += 2
                dash = self.peek() == "-"
                if dash:
                    self.i += 1
                while self.peek() in (" ", "\t"):
                    self.i += 1
                delim = self._word()
                if delim is not None:
                    self.heredocs.append((delim.text, dash))
                continue
            m = _REDIRECT.match(self.s, self.i)
            if m:
                self.i = m.end()
                while self.peek() in (" ", "\t"):
                    self.i += 1
                if self.i < self.n and self.s[self.i] not in _WORD_END:
                    self._word()  # the target is not an argument
                continue
            if c in ";&|":
                flush()
                while self.peek() in (";", "&", "|"):
                    self.i += 1
                continue
            if c == "(":
                if self.peek(1) == "(":
                    self._balanced("(", ")")
                    continue
                depth += 1
                flush()
                self.i += 1
                continue
            if c == ")":
                depth = max(0, depth - 1)
                flush()
                self.i += 1
                continue
            w = self._word()
            if w is not None:
                cur.append(w)
        if stop is not None:
            raise ShellParseError(
                "unterminated %s at end of text (line %d)"
                % ("$(" if stop == ")" else "`", self.line)
            )
        flush()

    def _heredoc_bodies(self) -> None:
        while self.heredocs:
            delim, dash = self.heredocs.pop(0)
            while self.i < self.n:
                end = self.s.find("\n", self.i)
                end = self.n if end == -1 else end
                body_line = self.s[self.i : end]
                self.i = min(self.n, end + 1)
                self.line += 1
                if (body_line.lstrip("\t") if dash else body_line) == delim:
                    break

    def _balanced(self, open_: str, close: str) -> str:
        """Consume from an `open_` to its matching `close`, returning the text; quotes inside are skipped whole."""
        start = self.i
        depth = 0
        while self.i < self.n:
            c = self.s[self.i]
            if c == "\n":
                self.line += 1
            elif c in ("'", '"') and open_ == "{":
                self.i += 1
                self._until(c)
                continue
            elif c == open_:
                depth += 1
            elif c == close:
                depth -= 1
                if depth == 0:
                    self.i += 1
                    return self.s[start : self.i]
            self.i += 1
        raise ShellParseError("unterminated %s at end of text (line %d)" % (open_, self.line))

    def _until(self, q: str) -> str:
        start = self.i
        end = self.s.find(q, self.i)
        if end == -1:
            raise ShellParseError("unterminated %s quote (line %d)" % (q, self.line))
        text = self.s[start:end]
        self.line += text.count("\n")
        self.i = end + 1
        return text

    def _ansi(self) -> str:
        out = []
        while self.i < self.n:
            c = self.s[self.i]
            if c == "\\" and self.i + 1 < self.n:
                out.append(self.s[self.i : self.i + 2])
                self.i += 2
                continue
            if c == "'":
                self.i += 1
                return "".join(out)
            if c == "\n":
                self.line += 1
            out.append(c)
            self.i += 1
        raise ShellParseError("unterminated $' quote (line %d)" % self.line)

    def _dollar(self, pieces: list[tuple[str, str]]) -> None:
        nxt = self.peek(1)
        if nxt == "(":
            self.i += 1
            if self.peek(1) == "(":
                pieces.append(("var", "$" + self._balanced("(", ")")))
                return
            self.i += 1
            self._commands(")")
            pieces.append(("sub", "$(...)"))
            return
        if nxt == "{":
            self.i += 1
            pieces.append(("var", "$" + self._balanced("{", "}")))
            return
        if nxt == "'":
            self.i += 2
            pieces.append(("lit", self._ansi()))
            return
        if nxt == '"':
            self.i += 1
            return
        m = _DOLLAR_NAME.match(self.s, self.i + 1)
        if m:
            self.i = m.end()
            pieces.append(("var", "$" + m.group(0)))
            return
        self.i += 1
        pieces.append(("lit", "$"))

    def _dquote(self, pieces: list[tuple[str, str]]) -> None:
        while self.i < self.n:
            c = self.s[self.i]
            if c == '"':
                self.i += 1
                pieces.append(("lit", ""))
                return
            if c == "\\":
                nxt = self.peek(1)
                if nxt == "\n":
                    self.i += 2
                    self.line += 1
                    continue
                if nxt in ('"', "$", "`", "\\"):
                    pieces.append(("lit", nxt))
                    self.i += 2
                    continue
                pieces.append(("lit", "\\"))
                self.i += 1
                continue
            if c == "$":
                self._dollar(pieces)
                continue
            if c == "`":
                self.i += 1
                self._commands("`")
                pieces.append(("sub", "`...`"))
                continue
            if c == "\n":
                self.line += 1
            pieces.append(("lit", c))
            self.i += 1
        raise ShellParseError('unterminated " quote (line %d)' % self.line)

    def _word(self) -> Word | None:
        line = self.line
        pieces: list[tuple[str, str]] = []
        while self.i < self.n:
            c = self.s[self.i]
            if c in _WORD_END:
                break
            if c == "\\":
                nxt = self.peek(1)
                if nxt == "\n":
                    self.i += 2
                    self.line += 1
                    continue
                pieces.append(("lit", nxt))
                self.i += 2
                continue
            if c == "'":
                self.i += 1
                pieces.append(("lit", self._until("'")))
                continue
            if c == '"':
                self.i += 1
                self._dquote(pieces)
                continue
            if c == "$":
                self._dollar(pieces)
                continue
            if c == "`":
                self.i += 1
                self._commands("`")
                pieces.append(("sub", "`...`"))
                continue
            pieces.append(("lit", c))
            self.i += 1
        if not pieces:
            return None
        text = "".join(t for _k, t in pieces)
        dyn = any(k != "lit" for k, _t in pieces)
        solid = [(k, t) for k, t in pieces if not (k == "lit" and t == "")]
        whole = ""
        if len(solid) == 1 and solid[0][0] != "lit":
            t = solid[0][1]
            whole = (
                "star" if ("[@]" in t or "[*]" in t or t in ("$@", "$*", "${@}", "${*}")) else "one"
            )
        return Word(text, line, dyn, whole)


def lex(text: str) -> list[Command]:
    """Every command in `text`. Pure, so the selftest drives it directly. Raises ShellParseError."""
    return _Lexer(text).run()


# ---------------------------------------------------------------------------
# Workflow `run:` blocks and shell function spans.
# ---------------------------------------------------------------------------

_RUN_KEY = re.compile(r"^(?P<lead>\s*(?:-\s+)?)run:\s*(?P<val>.*?)\s*$")
_JOB = re.compile(r"^  ([A-Za-z0-9_-]+):\s*(?:#.*)?$")
_NAME_KEY = re.compile(r"^(\s*(?:-\s+)?)name:\s*(.+?)\s*$")


@dataclasses.dataclass(frozen=True)
class RunBlock:
    first_line: int  # 1-based line in the YAML of the block's first body line
    text: str
    qualname: str  # <job>/<step name>


def _indent(s: str) -> int:
    return len(s) - len(s.lstrip(" "))


@functools.cache
def run_blocks(yml: str) -> tuple[RunBlock, ...]:
    """Every `run:` value in a workflow or composite action, dedented, with the YAML line it starts on. Pure."""
    lines = yml.split("\n")
    out: list[RunBlock] = []
    i = 0
    while i < len(lines):
        m = _RUN_KEY.match(lines[i])
        if not m:
            i += 1
            continue
        key_col = len(m.group("lead"))
        val = re.sub(r"\s+#.*$", "", m.group("val"))
        qual = _step_name(lines, i, key_col)
        if val[:1] in ("|", ">"):
            folded = val[:1] == ">"
            j = i + 1
            body: list[str] = []
            while j < len(lines) and (lines[j].strip() == "" or _indent(lines[j]) > key_col):
                body.append(lines[j])
                j += 1
            while body and body[-1].strip() == "":
                body.pop()
            ind = min((_indent(b) for b in body if b.strip()), default=0)
            ded = [b[ind:] if b.strip() else "" for b in body]
            if folded:
                # A folded line break is a space; spelled as a bash continuation, the lexer reads one command and the line count stays exact.
                text = "".join(
                    d
                    + (
                        " \\\n"
                        if d
                        and k + 1 < len(ded)
                        and ded[k + 1]
                        and not ded[k + 1].startswith(" ")
                        and not d.startswith(" ")
                        else "\n"
                    )
                    for k, d in enumerate(ded)
                )
            else:
                text = "\n".join(ded) + "\n"
            out.append(RunBlock(i + 2, text, qual))
            i = j
            continue
        if val:
            if len(val) >= 2 and val[0] == val[-1] == "'":
                val = val[1:-1].replace("''", "'")
            elif len(val) >= 2 and val[0] == val[-1] == '"':
                val = val[1:-1].replace('\\"', '"')
            out.append(RunBlock(i + 1, val + "\n", qual))
        i += 1
    return tuple(out)


def _step_name(lines: list[str], at: int, key_col: int) -> str:
    """`<job>/<step name>` for the run key on line `at`: the step is the list item holding it, the job the nearest two-space key above."""
    item = at
    while item >= 0:
        s = lines[item]
        stripped = s.lstrip(" ")
        if stripped.startswith("- ") and _indent(s) < key_col:
            break
        if s.strip() and _indent(s) < key_col - 2 and not stripped.startswith("- "):
            item = -1
            break
        item -= 1
    step = "<unnamed step>"
    if item >= 0:
        dash = _indent(lines[item])
        j = item
        while j < len(lines):
            if j > item and lines[j].strip() and _indent(lines[j]) <= dash:
                break
            nm = _NAME_KEY.match(lines[j])
            if nm and len(nm.group(1)) == dash + 2:
                step = nm.group(2).strip("'\"")
                break
            j += 1
    job = "<runs>"
    for k in range(at, -1, -1):
        jm = _JOB.match(lines[k])
        if jm:
            job = jm.group(1)
            break
    return "%s/%s" % (job, step)


_FUNC = re.compile(
    r"^(?P<ind>\s*)(?:function\s+(?P<a>[\w:.-]+)\s*(?:\(\))?|(?P<b>[A-Za-z_][\w:.-]*)\s*\(\))\s*(?P<rest>.*)$"
)


def function_spans(text: str) -> list[tuple[int, int, str]]:
    """(first line, last line, name) of every shell function, closed by the first `}` at the opening line's indent. Pure."""
    lines = text.split("\n")
    out = []
    for i, ln in enumerate(lines):
        m = _FUNC.match(ln)
        if not m:
            continue
        name = m.group("a") or m.group("b")
        rest = m.group("rest")
        if rest.startswith("{") and rest.rstrip().endswith("}"):
            out.append((i + 1, i + 1, name))
            continue
        close = re.compile(r"^%s\}" % re.escape(m.group("ind")))
        end = next((k for k in range(i + 1, len(lines)) if close.match(lines[k])), len(lines) - 1)
        out.append((i + 1, end + 1, name))
    return out


def _qual_at(spans: list[tuple[int, int, str]], line: int) -> str:
    inner = [s for s in spans if s[0] <= line <= s[1]]
    if not inner:
        return "<main>"
    return max(inner, key=lambda s: s[0])[2]


# ---------------------------------------------------------------------------
# Sites.
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class ShellSite:
    path: str
    line: int
    qualname: str
    tool: str  # curl | gh
    kind: str  # read | write | local | unresolved
    verb: str
    route: str  # retried | one-shot
    argv: str

    @property
    def key(self) -> str:
        return "%s::%s" % (self.path, self.qualname)

    @property
    def stable_id(self) -> str:
        text = "%s|%s|%s|%s|%s" % (self.path, self.qualname, self.tool, self.verb, self.argv)
        return hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]

    @property
    def needs_retry(self) -> bool:
        return self.kind in ("read", "unresolved") and self.route != "retried"


_ASSIGN = re.compile(r"^([A-Za-z_]\w*)(?:\[[^\]]*\])?\+?=(.*)$", re.DOTALL)
_PREFIX_WORDS = frozenset(
    {
        "if",
        "then",
        "elif",
        "else",
        "do",
        "while",
        "until",
        "!",
        "{",
        "time",
        "exec",
        "nohup",
        "builtin",
    }
)
_TIMEOUT_VALUED = frozenset({"-k", "--kill-after", "-s", "--signal"})


def _command_head(words: tuple[Word, ...]) -> tuple[int, bool] | None:
    """(index of the command word, wrapped-in-retry) past assignments, keywords and launchers, or None."""
    i = 0
    retried = False
    while i < len(words):
        w = words[i].text
        if _ASSIGN.match(w) and not words[i].whole:
            i += 1
            continue
        if w in _PREFIX_WORDS:
            i += 1
            continue
        if w == "command":
            if i + 1 < len(words) and words[i + 1].text.startswith("-"):
                return None
            i += 1
            continue
        if w in ("env", "sudo"):
            i += 1
            while i < len(words) and (
                words[i].text.startswith("-") or _ASSIGN.match(words[i].text)
            ):
                i += 1
            continue
        if w == "timeout":
            i += 1
            while i < len(words) and words[i].text.startswith("-"):
                i += 2 if words[i].text in _TIMEOUT_VALUED else 1
            i += 1
            continue
        if w == "retry_with_backoff":
            i += 3
            retried = True
            continue
        return i, retried
    return None


def gh_api_vars(commands: list[Command], seeds: frozenset[str]) -> frozenset[str]:
    """Variables that hold the GitHub API base: `seeds` plus every name assigned a value naming the API or another such name, to a fixpoint. Pure."""
    assigns: list[tuple[str, str]] = []
    for cmd in commands:
        for w in cmd.words:
            m = _ASSIGN.match(w.text)
            if m:
                assigns.append((m.group(1), m.group(2)))
    found = set(seeds)
    while True:
        more = {n for n, v in assigns if n not in found and names_gh_api(v, frozenset(found))}
        if not more:
            return frozenset(found)
        found |= more


_VAR_REF = re.compile(r"\$\{?([A-Za-z_]\w*)")


def names_gh_api(text: str, gh_vars: frozenset[str]) -> bool:
    if any(lit in text for lit in GH_API_LITERALS):
        return True
    return any(m.group(1) in gh_vars for m in _VAR_REF.finditer(text))


_CURL_VALUED_LONG = frozenset(
    {
        "--header", "--output", "--write-out", "--max-time", "--connect-timeout", "--retry-delay",
        "--retry-max-time", "--user", "--user-agent", "--referer", "--cookie", "--cookie-jar",
        "--cacert", "--capath", "--cert", "--key", "--config", "--proxy", "--range", "--resolve",
        "--limit-rate", "--output-dir", "--dump-header", "--oauth2-bearer", "--max-filesize",
        "--speed-limit", "--speed-time", "--trace", "--trace-ascii", "--stderr", "--interface",
        "--netrc-file", "--proto", "--proto-redir", "--variable", "--connect-to", "--cert-type",
        "--key-type", "--pass", "--hostpubmd5", "--keepalive-time", "--expect100-timeout",
    }
)  # fmt: skip
_CURL_BODY_LONG = frozenset(
    {
        "--data",
        "--data-raw",
        "--data-binary",
        "--data-urlencode",
        "--data-ascii",
        "--json",
        "--form",
        "--form-string",
        "--upload-file",
    }
)
_CURL_VALUED_SHORT = frozenset("HowmuAeKbcrxYyEzQCDtUP")
_CURL_BODY_SHORT = frozenset("dFT")


@dataclasses.dataclass
class _Curl:
    github: bool
    kind: str
    verb: str
    retries: int | None  # None: no --retry; -1: a computed value


def classify_curl(args: list[Word], gh_vars: frozenset[str]) -> _Curl:
    """Read/write, GitHub-or-not and retry of one curl argv (without the `curl` word). Pure."""
    method: str | None = None
    method_unknown = False
    body = False
    get = False
    retries: int | None = None
    urls: list[Word] = []
    i = 0

    def value(k: int) -> Word | None:
        return args[k] if k < len(args) else None

    def set_method(w: Word | None) -> None:
        nonlocal method, method_unknown
        if w is None or w.whole:
            method_unknown = True
        else:
            method = w.text.upper()

    def set_retry(text: str | None, dyn: bool) -> None:
        nonlocal retries
        retries = int(text) if text is not None and text.isdigit() and not dyn else -1

    while i < len(args):
        w = args[i]
        t = w.text
        if t == "--":
            urls.extend(args[i + 1 :])
            break
        if t.startswith("--") and not w.whole:
            name, eq, val = t.partition("=")
            if name == "--request":
                if eq:
                    method = val.upper()
                else:
                    set_method(value(i + 1))
                    i += 1
            elif name == "--get":
                get = True
            elif name in _CURL_BODY_LONG:
                body = True
                i += 0 if eq else 1
            elif name == "--retry":
                if eq:
                    set_retry(val, w.dyn)
                else:
                    nxt = value(i + 1)
                    set_retry(nxt.text if nxt else None, bool(nxt and nxt.dyn))
                    i += 1
            elif name == "--url":
                if eq:
                    urls.append(Word(val, w.line, w.dyn))
                else:
                    nxt = value(i + 1)
                    if nxt:
                        urls.append(nxt)
                    i += 1
            elif name in _CURL_VALUED_LONG:
                i += 0 if eq else 1
            i += 1
            continue
        if t.startswith("-") and len(t) > 1 and not w.dyn:
            letters = t[1:]
            for k, ch in enumerate(letters):
                rest = letters[k + 1 :]
                if ch == "X":
                    if rest:
                        method = rest.upper()
                    else:
                        set_method(value(i + 1))
                        i += 1
                    break
                if ch == "G":
                    get = True
                    continue
                if ch in _CURL_BODY_SHORT:
                    body = True
                    i += 0 if rest else 1
                    break
                if ch in _CURL_VALUED_SHORT:
                    i += 0 if rest else 1
                    break
            i += 1
            continue
        urls.append(w)
        i += 1
    github = any(names_gh_api(u.text, gh_vars) for u in urls)
    if method_unknown and method is None:
        return _Curl(github, "unresolved", "curl -X ?", retries)
    m = method or ("POST" if body and not get else "GET")
    kind = "write" if m in py.WRITE_METHODS else "read"
    return _Curl(github, kind, "curl %s" % m, retries)


def _gh_token(w: Word) -> py.Token:
    if w.whole == "star":
        return py.STAR
    if w.whole == "one":
        return py.DYN
    return w.text


def _gh_argv(args: list[Word]) -> list[py.Token]:
    """The classifier's argv, `gh` first. Built by insertion rather than as a `["gh", ...]` literal: the Python half reads any list literal headed `"gh"` that reaches a call as a gh SPAWN, and this one is data (measured 2026-10-07, it reported this module's own classify call)."""
    out: list[py.Token] = [_gh_token(a) for a in args]
    out.insert(0, "gh")
    return out


def _argv_text(words: list[Word]) -> str:
    return " ".join(w.text for w in words)


def scan_text(
    rel: str, text: str, gh_seeds: frozenset[str], *, base_line: int = 1, qual_prefix: str = ""
) -> list[ShellSite]:
    """Every GitHub site (curl to the API, or gh) in one shell text. Pure. Raises ShellParseError."""
    if not re.search(r"\b(gh|curl|gh_retry|gh_json)\b", text):
        return []
    commands = lex(text)
    gh_vars = gh_api_vars(commands, gh_seeds)
    spans = function_spans(text)
    out: list[ShellSite] = []
    for cmd in commands:
        head = _command_head(cmd.words)
        if head is None:
            continue
        i, retried = head
        w = cmd.words[i]
        if w.dyn:
            continue
        rest = list(cmd.words[i + 1 :])
        func = _qual_at(spans, w.line)
        qual = qual_prefix + ("" if func == "<main>" else "." + func) if qual_prefix else func
        line = base_line + w.line - 1
        if w.text == "curl":
            c = classify_curl(rest, gh_vars)
            if not c.github:
                continue
            ok = retried or (c.retries is not None and c.retries >= 1)
            out.append(
                ShellSite(
                    rel,
                    line,
                    qual,
                    "curl",
                    c.kind,
                    c.verb,
                    "retried" if ok else "one-shot",
                    _argv_text([w, *rest]),
                )
            )
            continue
        if w.text in ("gh_retry", "gh_json"):
            if len(rest) < 2:
                continue  # a definition (`gh_retry() {`), not a call
            args = rest[1:]
            if args and args[0].text == "--":
                args = args[1:]
            retried = True
        elif w.text == "gh":
            args = rest
            if not args:
                continue
        else:
            continue
        if (rel, func) in IMPLEMENTATION:
            continue
        kind, verb = py.classify(_gh_argv(args))
        out.append(
            ShellSite(
                rel,
                line,
                qual,
                "gh",
                kind,
                verb,
                "retried" if retried else "one-shot",
                "gh " + _argv_text(args),
            )
        )
    return out


# ---------------------------------------------------------------------------
# The corpus and liveness.
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class Corpus:
    scripts: dict[str, str]  # in-scope shell scripts, rel -> text
    workflows: dict[str, str]  # workflow and composite-action YAML, rel -> text
    executors: dict[str, tuple[str, str]]  # rel -> (kind, text); kind is py | ts | sh | json | text
    gh_seeds: frozenset[str]


def _skip(rel: str) -> bool:
    return (
        rel.startswith(EXCLUDED_DIRS)
        or "/node_modules/" in rel
        or "__pycache__" in rel
        or py.is_test_path(rel)
        or ".test." in rel
        or "/__tests__/" in rel
    )


def _read(p: pathlib.Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace")


_PRUNE = frozenset({".git", "node_modules", "__pycache__", ".venv", "dist", "build-output"})


def _files(root: pathlib.Path, base: str, patterns: tuple[str, ...]) -> list[pathlib.Path]:
    """Files under `root/base` whose NAME matches one of `patterns`, never descending into EXCLUDED_DIRS or a vendored tree. `rglob` walked all of `.ci/cache` (131k directory reads) before the filter could drop it."""
    out: list[pathlib.Path] = []
    top = root / base
    if not top.is_dir():
        return out
    for dirpath, dirnames, filenames in os.walk(top):
        rel_dir = pathlib.Path(dirpath).relative_to(root).as_posix() + "/"
        dirnames[:] = sorted(
            d
            for d in dirnames
            if d not in _PRUNE and not (rel_dir + d + "/").startswith(EXCLUDED_DIRS)
        )
        out.extend(
            pathlib.Path(dirpath) / f
            for f in sorted(filenames)
            if any(fnmatch.fnmatch(f, pat) for pat in patterns)
        )
    return out


def well_known_gh_vars(text: str) -> frozenset[str]:
    """Keys of well-known.env whose value names the GitHub API. Pure."""
    out = set()
    for ln in text.splitlines():
        m = re.match(r"^\s*([A-Za-z_]\w*)=(.*)$", ln)
        if m and names_gh_api(m.group(2), frozenset()):
            out.add(m.group(1))
    return frozenset(out)


def load_corpus(root: pathlib.Path) -> Corpus:
    scripts: dict[str, str] = {}
    for base in SCRIPT_ROOTS:
        for p in _files(root, base, ("*.sh", "*.bash")):
            rel = p.relative_to(root).as_posix()
            if p.is_file() and not _skip(rel):
                scripts[rel] = _read(p)
    workflows: dict[str, str] = {}
    for g in WORKFLOW_GLOBS:
        for p in root.glob(g):
            workflows[p.relative_to(root).as_posix()] = _read(p)
    executors: dict[str, tuple[str, str]] = {}

    def add(p: pathlib.Path, kind: str) -> None:
        rel = p.relative_to(root).as_posix()
        if p.is_file() and not _skip(rel) and not rel.startswith(GATE_DIRS):
            executors[rel] = (kind, _read(p))

    for base in (".ci", "scripts", ".claude"):
        for p in _files(root, base, ("*.py",)):
            add(p, "py")
    for base in ("scripts", ".github/actions"):
        for p in _files(root, base, ("*.ts", "*.mts", "*.js", "*.mjs")):
            add(p, "ts")
    for p in [root / "package.json", *sorted(root.glob("packages/*/package.json"))]:
        if p.is_file():
            add(p, "json")
    for p in sorted(root.glob("*.sh")):
        add(p, "sh")
    for base in (".ci", ".devcontainer"):
        for p in _files(root, base, ("Dockerfile*",)):
            add(p, "text")
    for p in sorted(root.glob("Dockerfile*")):
        add(p, "text")
    for p in sorted(root.glob(".devcontainer/*.json")):
        add(p, "text")
    wk = root / WELL_KNOWN_REL
    seeds = GH_API_GLOBALS | (well_known_gh_vars(_read(wk)) if wk.is_file() else frozenset())
    return Corpus(scripts, workflows, executors, frozenset(seeds))


_TAIL = re.compile(r"(?<![\w-])((?:[\w.*-]+/)*[\w.*-]+\.(?:sh|bash))(?![\w-])")
_COMMENT_LINE = {
    "sh": re.compile(r"^\s*#"),
    "text": re.compile(r"^\s*#"),
    "ts": re.compile(r"^\s*(?://|\*|/\*)"),
}


def _strip_comment_lines(text: str, kind: str) -> str:
    pat = _COMMENT_LINE.get(kind)
    if pat is None:
        return text
    return "\n".join(ln for ln in text.split("\n") if not pat.match(ln))


# Calls that FORMAT or REPORT a string rather than run it: `assert_edge_tag_exists.TWIN` names its twin only to print it (2026-10-07).
_MESSAGE_CALLS = frozenset(
    {
        "print",
        "format",
        "join",
        "write",
        "debug",
        "info",
        "warn",
        "warning",
        "error",
        "notice",
        "log",
        "fail",
        "die",
        "exit",
        "append",
        "extend",
        "add",
        "startswith",
        "endswith",
        "replace",
        "split",
        "check",
        "ok",
        "no",
    }
)


def _is_message_call(call: ast.Call) -> bool:
    f = call.func
    name = f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else ""
    return (
        name in _MESSAGE_CALLS or name.startswith("log_") or name.endswith(("Error", "Exception"))
    )


def executed_constants(tree: ast.AST) -> list[str]:
    """String constants a module could EXECUTE: inside a call's arguments (`run([".ci/x.sh", ...])`, `from_root("...")`), or bound to a name that is itself used in a call's arguments or as a parameter default (`DISPATCH = ".ci/.../dispatch-release.sh"` ... `def decide(path=DISPATCH)`). The NEAREST enclosing call decides, and a message call (`print`, a logger, an exception) is not an execution.

    A docstring, a dict key in a table, a usage message held in a constant nothing calls with: none of these is an execution, and counting them made every twin live (measured 2026-10-07: 148 of 148 scripts live, through `bash_lib_migration_complete.LIBS` and the shadow ledgers' path tables). ONE iterative pass: the first version walked each tree four times and cost 30 s over 346 modules.
    """
    used: set[str] = set()
    cands: list[tuple[str, bool, tuple[str, ...]]] = []
    stack: list[tuple[ast.AST, bool, tuple[str, ...]]] = [(tree, False, ())]
    while stack:
        node, in_call, targets = stack.pop()
        if isinstance(node, ast.Constant):
            if isinstance(node.value, str) and (".sh" in node.value or ".bash" in node.value):
                cands.append((node.value, in_call, targets))
            continue
        if isinstance(node, ast.Name):
            if in_call and isinstance(node.ctx, ast.Load):
                used.add(node.id)
            continue
        if isinstance(node, (ast.stmt, ast.Lambda)):
            in_call = False
            if isinstance(node, ast.Assign):
                targets = tuple(t.id for t in node.targets if isinstance(t, ast.Name))
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                targets = (node.target.id,)
            else:
                targets = ()
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                used.update(
                    d.id
                    for d in [*node.args.defaults, *node.args.kw_defaults]
                    if isinstance(d, ast.Name)
                )
        if isinstance(node, ast.Call):
            runs = not _is_message_call(node)
            stack.append((node.func, in_call, targets))
            stack.extend((arg, runs, targets) for arg in node.args)
            stack.extend((k.value, runs, targets) for k in node.keywords)
            continue
        stack.extend((child, in_call, targets) for child in ast.iter_child_nodes(node))
    return [v for v, in_call, targets in cands if in_call or any(t in used for t in targets)]


# A module can execute a script only through a string literal holding its name, and a one-line literal holds the whole name; a module where `.sh` appears only in prose is not parsed (346 parsed modules -> the ones this admits; the parse was most of the run).
_PY_QUOTED_SCRIPT = re.compile(r"""["'][^"'\n]*\.(?:sh|bash)\b[^"'\n]*["']""")


@functools.cache
def _tails(kind: str, text: str) -> tuple[tuple[str, bool], ...]:
    """(path tail, bare basename allowed) for every script name an executor's text holds. Memoised on the text, so a plant re-reads only what it changed."""
    out: list[tuple[str, bool]] = []
    if kind == "py":
        if not _PY_QUOTED_SCRIPT.search(text):
            return ()
        try:
            tree = ast.parse(text)
        except SyntaxError:
            return ()
        for value in executed_constants(tree):
            pathlike = not re.search(r"\s", value.strip())
            # Python runs a script by NAME; a glob in Python (`git ls-files "*.sh"`) enumerates files to inspect them, and read as a reference it made all 148 scripts live (2026-10-07).
            out.extend((t, pathlike) for t in _TAIL.findall(value) if "*" not in t)
        return tuple(out)
    if kind == "json":
        try:
            scripts = json.loads(text).get("scripts", {})
        except (ValueError, AttributeError):
            return ()
        body = "\n".join(str(v) for v in scripts.values()) if isinstance(scripts, dict) else ""
        return tuple((t, False) for t in _TAIL.findall(body))
    tails = _TAIL.findall(_strip_comment_lines(text, kind))
    if kind == "ts":
        # TS, like Python, runs a script by NAME; a glob there is a `paths:` filter or a lint target (manifest.ts made every script live through one, 2026-10-07).
        tails = [t for t in tails if "*" not in t]
    return tuple((t, kind == "sh") for t in tails)


def _resolve(tail: str, bare_ok: bool, from_dir: str | None, scripts: dict[str, str]) -> list[str]:
    t = tail
    while t.startswith(("./", "../")):
        t = t[2:] if t.startswith("./") else t[3:]
    glob = "*" in t
    if "/" in t:
        if glob:
            return [s for s in scripts if fnmatch.fnmatch(s, t) or fnmatch.fnmatch(s, "*/" + t)]
        return [s for s in scripts if s == t or s.endswith("/" + t)]
    if not bare_ok:
        return []
    hits = [s for s in scripts if fnmatch.fnmatch(s.rsplit("/", 1)[-1], t)]
    if from_dir is not None:
        hits = [s for s in hits if s.rsplit("/", 1)[0] == from_dir]
    return hits


def liveness(corpus: Corpus) -> dict[str, str]:
    """script rel -> the executor that makes it live. A script absent from the result is DEAD (a twin nothing runs)."""
    live: dict[str, str] = {}
    queue: list[str] = []

    def mark(hits: list[str], why: str) -> None:
        for s in hits:
            if s not in live:
                live[s] = why
                queue.append(s)

    for rel, yml in sorted(corpus.workflows.items()):
        for blk in run_blocks(yml):
            for tail, _bare in _tails("sh", blk.text):
                mark(_resolve(tail, False, None, corpus.scripts), "%s (%s)" % (rel, blk.qualname))
    for rel, (kind, text) in sorted(corpus.executors.items()):
        for tail, bare in _tails(kind, text):
            # A root-level script (run.sh) resolves a bare name against nothing: it has no siblings in the corpus.
            mark(_resolve(tail, bare and kind == "py", None, corpus.scripts), rel)
    while queue:
        s = queue.pop()
        here = s.rsplit("/", 1)[0]
        for tail, _bare in _tails("sh", corpus.scripts[s]):
            mark(_resolve(tail, True, here, corpus.scripts), s)
    return live


# ---------------------------------------------------------------------------
# The verdict.
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class ShellVerdict:
    scripts: int
    live: dict[str, str]
    workflows: int
    blocks: int
    sites: list[ShellSite]  # judged: live scripts and run blocks
    dead: list[ShellSite]  # in dead scripts, never judged, always printed
    new: list[ShellSite]
    debt: list[ShellSite]
    excused: list[ShellSite]
    drained: list[str]
    problems: list[str]

    def count(self, pred) -> int:
        return sum(1 for s in self.sites if pred(s))


def judge(corpus: Corpus, allowed: dict[str, str], debt: dict[str, str]) -> ShellVerdict:
    live = liveness(corpus)
    problems: list[str] = []
    sites: list[ShellSite] = []
    dead: list[ShellSite] = []
    blocks = 0
    for rel, text in sorted(corpus.scripts.items()):
        try:
            found = _scan_memo(rel, text, corpus.gh_seeds, 1, "")
        except ShellParseError as exc:
            problems.append(
                "UNPARSEABLE %s: %s; its GitHub calls cannot be judged, so this is not a pass"
                % (rel, exc)
            )
            continue
        (sites if rel in live else dead).extend(found)
    for rel, yml in sorted(corpus.workflows.items()):
        for blk in run_blocks(yml):
            blocks += 1
            try:
                sites.extend(
                    _scan_memo(rel, blk.text, corpus.gh_seeds, blk.first_line, blk.qualname)
                )
            except ShellParseError as exc:
                problems.append(
                    "UNPARSEABLE %s:%d (%s): %s; its GitHub calls cannot be judged, so this is not a pass"
                    % (rel, blk.first_line, blk.qualname, exc)
                )
    for key, reason in sorted(allowed.items()):
        if not reason.startswith("BLOCKER:"):
            problems.append("ALLOWED[%r]: the reason must start with 'BLOCKER:'" % key)
            continue
        rejection = allowlist.validate_reason(
            key, reason[len("BLOCKER:") :], "gh_retry_shell.ALLOWED"
        )
        if rejection is not None:
            problems.append(rejection.message)
    unretried = [s for s in sites if s.needs_retry]
    excused = [s for s in unretried if s.key in allowed]
    problems.extend(
        "STALE ALLOWED entry %s: it excuses no unretried shell GitHub read on this tree. Delete it from ALLOWED in %s."
        % (k, SELF_REL)
        for k in sorted(allowed)
        if k not in {s.key for s in excused}
    )
    rest = [s for s in unretried if s not in excused]
    budget = dict.fromkeys(debt, 1)
    new: list[ShellSite] = []
    owed: list[ShellSite] = []
    for s in rest:
        if budget.get(s.stable_id, 0) > 0:
            budget[s.stable_id] -= 1
            owed.append(s)
        else:
            new.append(s)
    drained = sorted("%s (%s)" % (debt[k], k) for k, left in budget.items() if left > 0)
    if not corpus.scripts:
        problems.append(
            "VACUOUS: zero shell scripts under %s; the gate is not seeing the tree."
            % ", ".join(SCRIPT_ROOTS)
        )
    elif not live:
        problems.append(
            "VACUOUS: zero live shell scripts; the liveness walk is not seeing any executor."
        )
    if not blocks:
        problems.append(
            "VACUOUS: zero workflow run: blocks read from %s; the YAML reader has rotted."
            % ", ".join(WORKFLOW_GLOBS)
        )
    # THE DETECTOR FLOORS read the dead twins too: they prove the detectors still SEE the tree, not that the live tree holds a given shape. The tree's one live shell GitHub write went when sync-epic-block.sh became an exec of its Python port, so a live-only floor could no longer pass.
    seen = [*sites, *dead]
    if corpus.scripts and blocks:
        if not any(s.tool == "curl" for s in seen):
            problems.append(
                "VACUOUS: zero curl calls to the GitHub API found; the curl detector is not seeing the tree."
            )
        if not any(s.tool == "gh" for s in seen):
            problems.append(
                "VACUOUS: zero gh calls found in live scripts and run: blocks; the gh detector is not seeing the tree."
            )
        if not any(s.route == "retried" for s in seen):
            problems.append(
                "VACUOUS: zero retried shell reads on the tree; either every live shell GitHub read lost its retry (see the findings above) or the retry detector has rotted."
            )
        if not any(s.kind == "write" for s in seen):
            problems.append(
                "VACUOUS: zero shell writes classified; the read/write classifier has rotted."
            )
    return ShellVerdict(
        len(corpus.scripts),
        live,
        len(corpus.workflows),
        blocks,
        sites,
        dead,
        new,
        owed,
        excused,
        drained,
        problems,
    )


@functools.cache
def _scan_memo(
    rel: str, text: str, seeds: frozenset[str], base_line: int, prefix: str
) -> tuple[ShellSite, ...]:
    return tuple(scan_text(rel, text, seeds, base_line=base_line, qual_prefix=prefix))


def describe(s: ShellSite) -> str:
    if s.tool == "curl":
        what = "a one-shot %s to the GitHub API (no --retry)" % s.verb
    else:
        what = "a one-shot gh %s (no retry)" % s.verb
    if s.kind == "unresolved":
        what += "; the verb is computed, so it is counted as a read"
    return what


# ---------------------------------------------------------------------------
# Controls.
# ---------------------------------------------------------------------------

_FIX_SH = r"""#!/bin/bash
GH_API="https://api.github.com"
CF_API="https://api.cloudflare.com/client/v4"
RUNS="${GH_API}/repos/o/r/actions/runs"
# curl -sS "https://api.github.com/repos/o/r" is a comment, not a call
status() {
    local resp
    resp="$(curl -sS -w $'\n%{http_code}' \
        -H "Accept: application/vnd.github+json" \
        --max-time 30 --retry 2 --retry-delay 5 \
        "${GH_API}/repos/o/r/actions/runs/$1" 2>/dev/null || true)"
    echo "$resp"
}
cancel() {
    curl -sS -X POST "${RUNS}/$1/cancel"
}
cf() {
    curl -sS "${CF_API}/zones"
}
labels() {
    if ! rows=$(gh_retry "labels" -- api "repos/o/r/commits/$1/pulls" \
        --jq '.[].number' 2>&1 </dev/null); then
        return 1
    fi
    echo "gh api repos/o/r/pulls ${x#gh api}"
    command -v gh >/dev/null
    cat <<EOF
gh api repos/o/r/heredoc
curl https://api.github.com/heredoc
EOF
    gh pr edit "$1" --add-label x
    retry_with_backoff 3 2 gh api "repos/o/r/tags"
}
"""

_FIX_YML = """name: fixture
on: push
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - name: Read the PR
        env:
          GH_TOKEN: x
        run: |
          echo start
          gh pr list --repo "$GITHUB_REPOSITORY" --state merged \\
            --json number --jq 'length'
      - name: Inline
        run: curl -fsS "${{ github.api_url }}/repos/o/r" -o out.json
      - name: Folded
        run: >-
          .ci/scripts/live/run-me.sh
          --flag
"""


def _one(
    text: str, rel: str = ".ci/scripts/x/fixture.sh", seeds: frozenset[str] = GH_API_GLOBALS
) -> list[tuple[str, str, str, str]]:
    return [(s.qualname, s.tool, s.kind, s.route) for s in scan_text(rel, text, seeds)]


def _fixture_corpus(workflow_line: str = ".ci/scripts/live/run-me.sh") -> Corpus:
    yml = _FIX_YML.replace(".ci/scripts/live/run-me.sh", workflow_line)
    return Corpus(
        scripts={
            ".ci/scripts/live/run-me.sh": 'source "$(dirname "$0")/../lib/common.sh"\n"$SCRIPT_DIR"/step-*.sh\ngh api repos/o/r/tags\n',
            ".ci/scripts/live/step-one.sh": "curl -sS -X DELETE https://api.github.com/repos/o/r/x\n",
            ".ci/scripts/lib/common.sh": 'gh_retry() { _gh_probe false "$@"; }\n',
            ".ci/scripts/lib/local-common.sh": "true\n",
            ".ci/scripts/twin/old-twin.sh": "gh api repos/o/r/pulls\n",
            ".ci/scripts/twin/py-only.sh": "true\n",
            ".ci/scripts/twin/doc-only.sh": "true\n",
            ".ci/scripts/twin/table-only.sh": "true\n",
            ".ci/scripts/twin/glob-only.sh": "true\n",
            ".ci/scripts/twin/msg-only.sh": "true\n",
            "scripts/direct/called.sh": "true\n",
        },
        workflows={".github/workflows/fixture.yml": yml},
        executors={
            "x/runner.py": (
                "py",
                (
                    '"""Port of `.ci/scripts/twin/doc-only.sh`."""\nimport subprocess\nTWIN = ".ci/scripts/twin/py-only.sh"\nUSAGE = "usage: old-twin.sh <n>"\n'
                    'TABLE = {".ci/scripts/twin/table-only.sh": ("x.py",)}\nDIRECT = 1\n\n\ndef go(path=TWIN):\n'
                    '    subprocess.run([path], check=False)\n    subprocess.run(["scripts/direct/called.sh", "--x"], check=False)\n'
                    '    subprocess.run(["git", "ls-files", "*.sh"], check=False)\n'
                    '    print("see msg-only.sh", ".ci/scripts/twin/msg-only.sh")\n'
                ),
            ),
        },
        gh_seeds=GH_API_GLOBALS,
    )


def selftest() -> bool:
    """True when a control FAILED (the `controls_first` contract)."""
    check = Checker()

    sh = _one(_FIX_SH)
    check(
        "CURL: a GitHub read through a GH_API variable, with --retry 2, is retried",
        ("status", "curl", "read", "retried") in sh,
    )
    check(
        "CURL: a POST through a variable built from GH_API is a write",
        ("cancel", "curl", "write", "one-shot") in sh,
    )
    check("CURL: a call to another API (Cloudflare) is not a site", "cf" not in [x[0] for x in sh])
    check(
        "GH: `gh_retry <what> -- api ...` across a continuation is a retried read",
        ("labels", "gh", "read", "retried") in sh,
    )
    check("GH: `gh pr edit` is a write", ("labels", "gh", "write", "one-shot") in sh)
    check(
        "GH: `retry_with_backoff 3 2 gh api` is retried",
        sum(1 for x in sh if x == ("labels", "gh", "read", "retried")) == 2,
    )
    check(
        "LEXER: comments, echo text, ${x#...}, `command -v gh` and heredoc bodies are not sites",
        len(sh) == 5,
    )
    check(
        "CONTROL: the clean fixture has no finding",
        not [s for s in scan_text("f.sh", _FIX_SH, GH_API_GLOBALS) if s.needs_retry],
    )

    unretried = plant(_FIX_SH, " --retry 2 --retry-delay 5", "")
    got = [s for s in scan_text("f.sh", unretried, GH_API_GLOBALS) if s.needs_retry]
    check(
        "PLANT: the retried curl without --retry is exactly one finding, on its curl line",
        [(s.qualname, s.line) for s in got] == [("status", 8)],
    )
    retry0 = plant(_FIX_SH, "--retry 2 ", "--retry 0 ")
    check(
        "PLANT: `--retry 0` is not a retry",
        len([s for s in scan_text("f.sh", retry0, GH_API_GLOBALS) if s.needs_retry]) == 1,
    )
    allerr = plant(_FIX_SH, "--retry 2 --retry-delay 5", "--retry-all-errors")
    check(
        "PLANT: `--retry-all-errors` without `--retry N` is not a retry",
        len([s for s in scan_text("f.sh", allerr, GH_API_GLOBALS) if s.needs_retry]) == 1,
    )
    oneshot_gh = plant(_FIX_SH, 'gh_retry "labels" -- api', "gh api")
    check(
        "PLANT: the gh_retry read demoted to a bare `gh api` is a finding",
        [s.qualname for s in scan_text("f.sh", oneshot_gh, GH_API_GLOBALS) if s.needs_retry]
        == ["labels"],
    )
    unwrapped = plant(_FIX_SH, "retry_with_backoff 3 2 gh api", "gh api")
    check(
        "PLANT: the same read without retry_with_backoff is a finding",
        len([s for s in scan_text("f.sh", unwrapped, GH_API_GLOBALS) if s.needs_retry]) == 1,
    )
    as_get = plant(_FIX_SH, "curl -sS -X POST", "curl -sS -X GET")
    check(
        "PLANT: the POST turned into an explicit GET is a read finding",
        [s.qualname for s in scan_text("f.sh", as_get, GH_API_GLOBALS) if s.needs_retry]
        == ["cancel"],
    )
    literal = 'curl -fsSL \\\n  "https://api.github.com/repos/o/r/releases/latest"\n'
    check(
        "CURL: a literal api.github.com URL on a continuation line is a read",
        _one(literal) == [("<main>", "curl", "read", "one-shot")],
    )
    check(
        "CURL: `-d` without -G is a write",
        _one("curl -d a=b https://api.github.com/x\n")[0][2] == "write",
    )
    check(
        "CURL: `-G --data-urlencode` is a read",
        _one("curl -G --data-urlencode q=x https://api.github.com/search\n")[0][2] == "read",
    )
    check(
        'CURL: `-X "$m"` is unresolved, counted as a read',
        _one('curl -X "$m" https://api.github.com/x\n')[0][2] == "unresolved",
    )
    check(
        "CURL: `--retry=3` is retried",
        _one("curl --retry=3 https://api.github.com/x\n")[0][3] == "retried",
    )
    check(
        "CURL: combined short flags `-fsSLo out` keep the URL",
        _one("curl -fsSLo out https://api.github.com/x\n")[0][2] == "read",
    )
    check(
        "CURL: WK_GH_API_BASE (a well-known seed) is the GitHub API",
        _one('curl "$WK_GH_API_BASE/x"\n', seeds=frozenset({"WK_GH_API_BASE"}))[0][1] == "curl",
    )
    check(
        "CURL: a GitHub var unknown to the seeds is not the API",
        _one('curl "$WK_GH_API_BASE/x"\n') == [],
    )
    check(
        "GH: `if ! out=$(timeout 20 gh run view 1)` is a read",
        _one("if ! out=$(timeout 20 gh run view 1); then exit 1; fi\n")
        == [("<main>", "gh", "read", "one-shot")],
    )
    check('GH: `gh api -X "$m"` is unresolved', _one('gh api -X "$m" x\n')[0][2] == "unresolved")
    check('GH: `gh "$@"` (a computed verb) is unresolved', _one('gh "$@"\n')[0][2] == "unresolved")
    check(
        "GH: the gh_retry DEFINITION is not a call",
        _one('gh_retry() { _gh_probe false "$@"; }\n') == [],
    )
    check(
        "GH: common.sh's _gh_probe body is the implementation",
        scan_text(
            ".ci/scripts/lib/common.sh",
            '_gh_probe() {\n    out="$(gh "$@" 2>"$err")"\n}\n',
            GH_API_GLOBALS,
        )
        == [],
    )
    check(
        "GH: an array argv `argv=(gh workflow run x)` is a write",
        _one("local -a argv=(gh workflow run cd.yml)\n")[0][2] == "write",
    )
    check(
        "LEXER: `Bash(gh pr view:*)` inside a word is not a call",
        _one('echo "Bash(gh pr view:*)"\nx=Bash\n') == [],
    )
    # A here-string read as `<` + a heredoc delimited by `$resp` swallowed the rest of the reaper, its GitHub curl included (caught on the first real-tree run, 2026-10-07).
    check(
        "LEXER: a `<<<` here-string is not a heredoc, so the lines after it are still read",
        _one('grep -q x <<<"$resp" && return 0\ngh pr list\n')
        == [("<main>", "gh", "read", "one-shot")],
    )
    try:
        lex('echo "unterminated\n')
        bad = False
    except ShellParseError:
        bad = True
    check("LEXER: an unterminated quote raises, never reads as clean", bad)

    blocks = run_blocks(_FIX_YML)
    check("YAML: three run: blocks (block, inline, folded) are read", len(blocks) == 3)
    check(
        "YAML: the block scalar starts on the line after `run: |`",
        blocks and blocks[0].first_line == 11,
    )
    check(
        "YAML: the step name is the qualname", blocks and blocks[0].qualname == "build/Read the PR"
    )
    yml_sites = [
        (s.path, s.line, s.qualname, s.tool, s.kind)
        for b in blocks
        for s in scan_text(
            "w.yml", b.text, GH_API_GLOBALS, base_line=b.first_line, qual_prefix=b.qualname
        )
    ]
    check(
        "YAML: the gh read in the block and the github.api_url curl inline are sites, on their YAML lines",
        yml_sites
        == [
            ("w.yml", 12, "build/Read the PR", "gh", "read"),
            ("w.yml", 15, "build/Inline", "curl", "read"),
        ],
    )
    check(
        "YAML: a folded block joins its lines into one command",
        blocks and blocks[2].text.count("\n") == 2 and "\\\n" in blocks[2].text,
    )

    corpus = _fixture_corpus()
    live = liveness(corpus)
    check(
        "LIVE: a script a workflow run: block names is live", ".ci/scripts/live/run-me.sh" in live
    )
    check(
        "LIVE: a script a live script sources by ../lib/<name> is live",
        ".ci/scripts/lib/common.sh" in live,
    )
    check(
        "LIVE: a same-directory glob in a live script reaches its matches",
        ".ci/scripts/live/step-one.sh" in live,
    )
    check(
        "LIVE: `local-common.sh` is not reached through a `lib/common.sh` reference",
        ".ci/scripts/lib/local-common.sh" not in live,
    )
    check(
        "LIVE: a Python constant used as a parameter default that a call runs makes it live",
        ".ci/scripts/twin/py-only.sh" in live,
    )
    check(
        "LIVE: a Python constant inside a call's argv makes it live",
        "scripts/direct/called.sh" in live,
    )
    check(
        "DEAD: a script only a Python TABLE (dict key) names is dead",
        ".ci/scripts/twin/table-only.sh" not in live,
    )
    check(
        "DEAD: a script a Python print() only names is dead",
        ".ci/scripts/twin/msg-only.sh" not in live,
    )
    check(
        'DEAD: a Python glob (`ls-files "*.sh"`) enumerates, it does not execute',
        ".ci/scripts/twin/glob-only.sh" not in live,
    )
    check(
        "DEAD: a script only a Python DOCSTRING names is dead",
        ".ci/scripts/twin/doc-only.sh" not in live,
    )
    check(
        "DEAD: a bare basename inside a usage message is not a reference",
        ".ci/scripts/twin/old-twin.sh" not in live,
    )
    v = judge(corpus, {}, {})
    check(
        "JUDGE: the dead twin's read is never judged, and is listed",
        [s.path for s in v.dead] == [".ci/scripts/twin/old-twin.sh"],
    )
    check(
        "JUDGE: the live script's one-shot read and the run: block read are the findings",
        sorted(s.path for s in v.new)
        == [
            ".ci/scripts/live/run-me.sh",
            ".github/workflows/fixture.yml",
            ".github/workflows/fixture.yml",
        ],
    )
    wired = judge(_fixture_corpus(".ci/scripts/twin/old-twin.sh"), {}, {})
    check(
        "LIVE PLANT: naming the twin in a run: block makes its read a finding",
        ".ci/scripts/twin/old-twin.sh" in [s.path for s in wired.new],
    )

    debt = {s.stable_id: "fixture" for s in v.new}
    frozen = judge(corpus, {}, debt)
    check("DEBT: frozen reads are debt, not new", not frozen.new and len(frozen.debt) == 3)
    moved = Corpus(
        {**corpus.scripts, ".ci/scripts/live/run-me.sh": "\n\n# moved\n" + corpus.scripts[".ci/scripts/live/run-me.sh"]},
        corpus.workflows, corpus.executors, corpus.gh_seeds,
    )  # fmt: skip
    check("DEBT: the id survives the read moving down the file", not judge(moved, {}, debt).new)
    rewritten = Corpus(
        {**corpus.scripts, ".ci/scripts/live/run-me.sh": corpus.scripts[".ci/scripts/live/run-me.sh"].replace("repos/o/r/tags", "repos/o/r/branches")},
        corpus.workflows, corpus.executors, corpus.gh_seeds,
    )  # fmt: skip
    rw = judge(rewritten, {}, debt)
    check(
        "DEBT: a rewritten argv is NEW, and its old row DRAINED",
        len(rw.new) == 1 and len(rw.drained) == 1,
    )
    lazy = judge(corpus, {".ci/scripts/live/run-me.sh::<main>": "BLOCKER: tbd"}, {})
    check("ALLOWED: a low-effort BLOCKER reason is rejected", bool(lazy.problems))
    stale = judge(
        corpus,
        {"x.sh::nothing": "BLOCKER: a reason long enough to pass the thirty character floor"},
        {},
    )
    check(
        "ALLOWED: an entry that excuses nothing is STALE", any("STALE" in p for p in stale.problems)
    )
    empty = judge(Corpus({}, {}, {}, GH_API_GLOBALS), {}, {})
    check(
        "VACUITY: zero scripts and zero run: blocks are problems",
        any("zero shell scripts" in p for p in empty.problems)
        and any("zero workflow run:" in p for p in empty.problems),
    )
    nocurl = Corpus(
        {k: v for k, v in corpus.scripts.items() if k != ".ci/scripts/live/step-one.sh"},
        {".github/workflows/fixture.yml": _FIX_YML.replace("github.api_url", "env.OTHER")},
        corpus.executors,
        corpus.gh_seeds,
    )
    check(
        "VACUITY: zero curl GitHub sites is a problem",
        any("zero curl calls" in p for p in judge(nocurl, {}, {}).problems),
    )
    broken = Corpus(
        {**corpus.scripts, ".ci/scripts/live/run-me.sh": 'gh api "x\n'},
        corpus.workflows,
        corpus.executors,
        corpus.gh_seeds,
    )
    check(
        "VACUITY: an unlexable script is UNPARSEABLE, never clean",
        any("UNPARSEABLE .ci/scripts/live/run-me.sh" in p for p in judge(broken, {}, {}).problems),
    )

    if check.count < 50:
        print("  FAIL  only %d shell selftest control(s) ran" % check.count, file=sys.stderr)
        return True
    return not check.ok


# ---------------------------------------------------------------------------
# Real-tree plants and the entry point.
# ---------------------------------------------------------------------------

_RUN_BAR = re.compile(r"^(?P<ind>\s*)(?:-\s+)?run:\s*\|\s*$", re.MULTILINE)


def _plant_run_line(yml: str, line: str) -> str | None:
    """`yml` with `line` inserted as the first line of its first `run: |` block, or None when it has none."""
    m = _RUN_BAR.search(yml)
    if not m:
        return None
    nl = yml.index("\n", m.end()) + 1
    nxt = yml[nl : yml.find("\n", nl)]
    ind = " " * _indent(nxt)
    return yml[:nl] + ind + line + "\n" + yml[nl:]


def real_tree_plants(corpus: Corpus, v: ShellVerdict) -> list[str]:
    """Plant into REAL text, in memory, and demand each plant red. Returns failures."""
    failures: list[str] = []
    clean = {s.stable_id for s in v.new}

    def added(c: Corpus) -> list[ShellSite]:
        return [s for s in judge(c, ALLOWED, SHELL_DEBT).new if s.stable_id not in clean]

    reaper = corpus.scripts.get(REAPER_REL)
    hit = REAPER_RETRY.search(reaper) if reaper is not None else None
    if reaper is None or hit is None:
        failures.append(
            "REAL-TREE PLANT: %s no longer carries a `--retry N`; the plant cannot be made"
            % REAPER_REL
        )
    else:
        mutated = Corpus(
            {**corpus.scripts, REAPER_REL: plant(reaper, hit.group(0), "", count=1)},
            corpus.workflows,
            corpus.executors,
            corpus.gh_seeds,
        )
        got = added(mutated)
        if [s.path for s in got] != [REAPER_REL]:
            failures.append(
                "REAL-TREE PLANT did not add exactly one finding on the reaper with --retry removed: %s"
                % [(s.path, s.line) for s in got]
            )
        else:
            print(
                "  shell plant red: the reaper's --retry removed -> %s:%d (%s)"
                % (got[0].path, got[0].line, got[0].qualname)
            )
    target = next(
        (
            r
            for r, y in sorted(corpus.workflows.items())
            if r.startswith(".github/workflows/") and _RUN_BAR.search(y)
        ),
        None,
    )
    if target is None:
        failures.append("REAL-TREE PLANT: no workflow has a `run: |` block to plant into")
        return failures
    one_shot = _plant_run_line(corpus.workflows[target], "gh api repos/o/r/pulls --jq length") or ""
    got = added(
        Corpus(
            corpus.scripts,
            {**corpus.workflows, target: one_shot},
            corpus.executors,
            corpus.gh_seeds,
        )
    )
    if [s.path for s in got] != [target]:
        failures.append(
            "REAL-TREE PLANT did not red: a one-shot gh read in %s's first run: block added %s"
            % (target, [(s.path, s.line) for s in got])
        )
    else:
        print(
            "  shell plant red: a one-shot gh read in a run: block -> %s:%d (%s)"
            % (got[0].path, got[0].line, got[0].qualname)
        )
    twin = next((s.path for s in v.dead if s.needs_retry), None)
    if twin is None:
        print(
            "  shell plant skipped: no dead script holds an unretried read, so the twin rule hides nothing today"
        )
        return failures
    wired = _plant_run_line(corpus.workflows[target], twin) or ""
    got = added(
        Corpus(
            corpus.scripts, {**corpus.workflows, target: wired}, corpus.executors, corpus.gh_seeds
        )
    )
    if twin not in {s.path for s in got}:
        failures.append(
            "REAL-TREE PLANT did not red: wiring the dead twin %s into %s left its reads unjudged"
            % (twin, target)
        )
    else:
        print(
            "  shell plant red: the dead twin %s wired into a run: block -> %d new finding(s)"
            % (twin, len(got))
        )
    return failures


def shape(v: ShellVerdict) -> str:
    return (
        "shell: %d script(s) [%d live, %d dead], %d workflow file(s) with %d run: block(s); %d GitHub call(s): %d curl, %d gh; "
        "%d read(s) [%d retried, %d unresolved], %d write(s); unretried: %d allowlisted, %d debt, %d new; %d unjudged in dead twins"
        % (
            v.scripts, len(v.live), v.scripts - len(v.live), v.workflows, v.blocks, len(v.sites),
            v.count(lambda s: s.tool == "curl"), v.count(lambda s: s.tool == "gh"),
            v.count(lambda s: s.kind in ("read", "unresolved")),
            v.count(lambda s: s.route == "retried" and s.kind != "write"),
            v.count(lambda s: s.kind == "unresolved"), v.count(lambda s: s.kind == "write"),
            len(v.excused), len(v.debt), len(v.new), sum(1 for s in v.dead if s.needs_retry),
        )
    )  # fmt: skip


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(
        prog="check_gh_retry_reads.py (shell)", description=__doc__.splitlines()[0]
    )
    ap.add_argument("--selftest", action="store_true", help="run the controls only")
    ap.add_argument(
        "--root", default=None, help="scan this tree instead of the repository (gate tests)"
    )
    ap.add_argument("--quiet-writes", action="store_true", help="omit the per-site write lines")
    args = ap.parse_args(argv)

    rc = controls_first(NAME, selftest)
    if rc:
        return rc
    if args.selftest:
        print("shell selftest: every control passed")
        return 0

    root = pathlib.Path(args.root).resolve() if args.root else paths.repo_root()
    corpus = load_corpus(root)
    v = judge(corpus, ALLOWED, SHELL_DEBT)
    # The plants prove a GREEN can fail. A verdict that is already red has proved it, and a planted defect (the reaper without its retry) would otherwise turn into "the plant cannot be made", exit 2, hiding the finding it is.
    if not (v.problems or v.new or v.drained):
        plant_failures = real_tree_plants(corpus, v)
        if plant_failures:
            for f in plant_failures:
                print("✗ %s" % f, file=sys.stderr)
            return 2

    if not args.quiet_writes:
        for s in v.sites:
            if s.kind == "write":
                print(
                    "  info: write  %s:%d %s: %s (never retried, by design)"
                    % (s.path, s.line, s.qualname, s.verb if s.tool == "curl" else "gh " + s.verb)
                )
    for s in v.excused:
        print(
            "  EXEMPT %s:%d %s: %s -- %s"
            % (s.path, s.line, s.qualname, describe(s), ALLOWED[s.key])
        )
    for s in v.debt:
        print(
            "  DEBT   %s:%d %s: %s -- frozen in %s SHELL_DEBT (%s); route it, then delete the row"
            % (s.path, s.line, s.qualname, describe(s), SELF_REL, s.stable_id)
        )
    per_twin: dict[str, int] = {}
    for s in v.dead:
        if s.needs_retry:
            per_twin[s.path] = per_twin.get(s.path, 0) + 1
    for path, n in sorted(per_twin.items()):
        print(
            "  TWIN   %s: %d unretried GitHub read(s) not judged; nothing live executes this script"
            % (path, n)
        )
    for s in v.new:
        print(
            "%s:%d: %s: %s. Fix: %s"
            % (s.path, s.line, s.qualname, describe(s), FIX_CURL if s.tool == "curl" else FIX_GH),
            file=sys.stderr,
        )
    for d in v.drained:
        print(
            "✗ DRAINED SHELL_DEBT row, the read is gone or retried now: %s. Delete the row from SHELL_DEBT in %s."
            % (d, SELF_REL),
            file=sys.stderr,
        )
    for p in v.problems:
        print("✗ %s" % p, file=sys.stderr)
    line = shape(v)
    if v.new or v.drained or v.problems:
        print("✗ %s" % line, file=sys.stderr)
        return 1
    print("✓ %s" % line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
