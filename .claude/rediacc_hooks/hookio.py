#!/usr/bin/env python3
"""The preamble every ported guard repeats, and the shell primitives it needs.

WHAT THIS IS. `.claude/hooks/pre-bash/lib/command-scan.sh` already had a name
for this idea: `hook_init` was extracted there "after
check:ci-shape-duplication counted three identical copies", and its header
argues that centralising the preamble matters more than the line count
suggests, because "a guard that hand-rolls its own preamble is a guard that can
drift away from that fix without anything noticing". This module is that
argument applied to the whole chain rather than to three files: every ported
guard reads its event, its command, its file path and its cwd from here.

WHY IT IS SEPARATE FROM `shellscan`. `shellscan` is the transliteration of ONE
bash file and is judged by a differential against it. Nothing here has a bash
twin of its own: it is the union of the preambles that were copied into 46
separate guards, so it has no single oracle. Keeping the two apart keeps
`shellscan`'s differential honest, because a helper added here can never change
what that differential is comparing.

=============================================================================
THE THREE THINGS THIS MODULE IS CAREFUL ABOUT
=============================================================================

1. `jq -r` PRINTS THE FOUR CHARACTERS `null`, and 26 guards depend on it.

   `CMD=$(jq -r '.tool_input.command' 2>/dev/null)` followed by
   `[ -z "$CMD" ] && exit 0` does NOT exit when the key is absent. jq writes
   `null`, the substitution keeps it, and the guard goes on to scan the string
   `null` as though someone had typed it. Only a jq FAILURE (unparseable JSON)
   or a genuinely empty string reaches the `-z` branch.

   The nine guards spelled `// empty` get the other behaviour, which is why
   both are implemented here separately rather than normalised into one.
   `shellscan._jq_raw_command` records the same asymmetry for its own caller;
   this is the general form, and the differential pins every shape.

2. A GUARD'S OBSERVABLE CONTRACT IS (rc, stdout, stderr), so that is what a
   guard returns. Messages are the product for at least the 21 `check_out`
   assertions in `.claude/hooks/test-hooks.sh`, whose whole point is that "an
   exit code alone cannot tell 'blocked, here is the correct command' from
   'blocked, good luck'". So the ports write their messages BYTE FOR BYTE and
   the differential compares the bytes, not a needle.

3. BUFFERS, NOT STREAMS. A guard writes into `Event.out` / `Event.err` rather
   than to `sys.stdout`. That is what lets the differential run the whole
   Python side inside ONE process while the bash side pays a fork per case, and
   it is also what will let the P6 dispatcher run a chain of guards in one
   process. A guard that reached for `print()` would work today and break both.
"""

import io
import json
import os
import pathlib
import re
import subprocess

# Re-exported so a guard does not grow a second spelling of the character
# classes bash means by [[:space:]]. `shellscan` owns the definitions; a guard
# that needs them imports them from here, and there is exactly one copy.
from rediacc_hooks.shellscan import (  # noqa: F401
    BLANK,
    SPACE,
    _command_substitution,
    _grep_only,
    _grep_out,
    _here_string,
    _printf_line,
    _records,
    _sed_out,
    _tr,
)

ALLOW = 0
DENY = 2


class Event:
    """One hook invocation: the payload in, the three results out.

    `payload` is the RAW stdin text and not a parsed document, because that is
    what the guards see. Two of them (`require-jq.sh`, and the `nojq` arm of
    `block-settled-questions.sh`) deliberately read the raw JSON body rather
    than a parsed value, on the stated grounds that they run exactly when the
    parser is missing. A class that only offered parsed access could not
    express them.
    """

    def __init__(self, payload, cwd=None, env=None):
        self.payload = payload
        self.out = io.StringIO()
        self.err = io.StringIO()
        self._env = os.environ if env is None else env
        self._cwd = cwd
        self._doc = _UNPARSED

    # -- the payload ------------------------------------------------------

    @property
    def doc(self):
        """The parsed payload, or None when jq would have failed.

        Parsed lazily and cached: a guard that never asks pays nothing, and a
        guard that asks four times forks jq four times in bash but parses once
        here. That is a performance difference and not a behavioural one,
        because the payload cannot change mid-run.
        """
        if self._doc is _UNPARSED:
            try:
                self._doc = json.loads(self.payload)
            except (ValueError, TypeError):
                # NOT `None`. A payload of the four characters `null` PARSES,
                # and `jq -r .tool_input.command` on it prints `null`; a
                # payload of `nonsense` does not parse and jq exits 5 with an
                # empty stdout. Measured 2026-09-06, both shapes, and the first
                # cut of this collapsed them onto None and got the second one
                # wrong -- a broken payload read as the string "null", which 26
                # guards would then have scanned as a command.
                self._doc = _BROKEN
        return self._doc

    def raw(self, *path):
        """`jq -r '.a.b'` -- `null` for an absent key, "" for a broken parse.

        See point 1 in the module docstring. The four characters, deliberately.
        """
        return _jq_raw(self.doc, path, empty=False)

    def field(self, *path):
        """`jq -r '.a.b // empty'` -- "" for absent, null, false OR broken.

        `//` is jq's ALTERNATIVE operator, and its left side is falsy for
        `null` AND for `false`. That matters for exactly one call site,
        `.tool_input.run_in_background // false`, which is why `flag()` below
        exists rather than being folded in here.
        """
        return _jq_raw(self.doc, path, empty=True)

    def first(self, *paths):
        """`jq -r '.a // .b // empty'` -- the first path that is not null."""
        for path in paths:
            got = _jq_raw(self.doc, path, empty=True)
            if got != "":
                return got
        return ""

    def flag(self, *path):
        """`jq -r '.a // false'` -- the literal words `true` or `false`.

        `block-shell-background-waiter.sh` compares the RESULT to the string
        `true`, so a Python bool here would silently never match.
        """
        got = _jq_raw(self.doc, path, empty=True)
        return got if got in ("true", "false") else "false"

    def default(self, path, fallback):
        """`jq -r '.a // "unknown"'` -- an explicit textual fallback."""
        got = _jq_raw(self.doc, path, empty=True)
        return got if got != "" else fallback

    def texts(self, *paths):
        """The `[.content, .new_string, .new_source, (.edits[]?.new_string)]`
        collector four pre-edit guards share, joined by newlines.

        jq prints an array under `-r` as one element per line, so the bash
        receives a newline-joined string and greps it as a whole. Nulls are
        printed as the word `null` by `-r`, and the four guards that use this
        all filter them out with `| select(. != null)`, so this does too.
        """
        out = []
        for path in paths:
            out.extend(_jq_collect(self.doc, path))
        return "\n".join(out)

    # -- the environment --------------------------------------------------

    def env(self, name, fallback=""):
        return self._env.get(name, fallback)

    @property
    def project_dir(self):
        """`${CLAUDE_PROJECT_DIR:-.}`, the root nearly every guard cd's into.

        `:-` and not `-`: an EMPTY variable takes the fallback too, which is
        what the guards spell and what a harness that exports the variable as
        "" would otherwise defeat.
        """
        return self._env.get("CLAUDE_PROJECT_DIR") or "."

    @property
    def cwd(self):
        return self._cwd if self._cwd is not None else os.getcwd()

    # -- the results ------------------------------------------------------

    def say(self, text):
        """`echo "..."` to stdout: the text plus exactly one newline."""
        self.out.write(text + "\n")

    def warn(self, text):
        """`echo "..." >&2`."""
        self.err.write(text + "\n")

    def warn_raw(self, text):
        """`cat >&2 <<MSG` -- the heredoc body, already carrying its newlines.

        Separate from `warn` because a heredoc's final newline is part of the
        body, and appending another would put a blank line at the end of every
        multi-paragraph message. That is a byte the differential compares.
        """
        self.err.write(text)

    def result(self, rc):
        return rc, self.out.getvalue(), self.err.getvalue()


_UNPARSED = object()
# jq exited 5 and wrote nothing: distinct from a document that IS JSON null.
_BROKEN = object()


def _jq_raw(doc, path, empty):
    """One `jq -r` field read, with jq's own type rules.

    jq indexes only objects and null. Handed a number, a string or an array it
    exits 5 with nothing on stdout, which the command substitution turns into
    "" -- the same value as a parse failure, and the guards cannot tell the two
    apart either.
    """
    if doc is _BROKEN:
        return ""
    node = doc
    for key in path:
        if node is None:
            node = None
            continue
        if not isinstance(node, dict):
            return ""
        node = node.get(key)
    if node is None:
        return "" if empty else "null"
    if node is False and empty:
        # `//` is jq's ALTERNATIVE operator and its left side is FALSY, not
        # merely null: `false // empty` is empty. Measured against real jq
        # 2026-09-06, and the first cut of this returned the word "false",
        # which is what `// false` gives and what `// empty` never does.
        return ""
    if isinstance(node, str):
        return _command_substitution(node + "\n")
    if isinstance(node, bool):
        return "true" if node else "false"
    return _command_substitution(json.dumps(node, separators=(",", ":")) + "\n")


def _jq_collect(doc, path):
    """`.a.b[]?.c` -- every element, nulls dropped, as `-r` would print them.

    A `[]?` step over anything that is not an array yields nothing rather than
    an error, which is what the `?` means and what the four pre-edit guards
    rely on for a payload with no `edits` key.
    """
    if doc is _BROKEN:
        return []
    nodes = [doc]
    for key in path:
        nxt = []
        for node in nodes:
            if key == "[]?":
                if isinstance(node, list):
                    nxt.extend(node)
                continue
            if isinstance(node, dict):
                nxt.append(node.get(key))
        nodes = nxt
    out = []
    for node in nodes:
        if node is None:
            continue
        out.append(node if isinstance(node, str) else json.dumps(node, separators=(",", ":")))
    return out


# ---------------------------------------------------------------------------
# The shell primitives the guards use, beyond the ones `shellscan` already owns
# ---------------------------------------------------------------------------


def grep_q(pattern, text, ignore_case=False, fixed=False):
    """`grep -qE <pattern>` over `printf '%s' "$text"`.

    NO HERE-STRING HERE. `printf '%s' "$x" | grep` and `grep <<<"$x"` differ on
    the empty subject: the pipe gives grep zero records so it cannot match, the
    here-string gives it one empty record so `^$` would. The guards use both
    spellings, so both are available and the caller picks the one its original
    wrote. `echo "$x" | grep` is `here_string` too, since echo appends a
    newline.
    """
    flags = re.IGNORECASE if ignore_case else 0
    compiled = re.compile(re.escape(pattern) if fixed else pattern, flags)
    records, _ = _records(text)
    return any(compiled.search(record) for record in records)


def grep_q_line(pattern, text, ignore_case=False, fixed=False):
    """`grep -qE <pattern> <<<"$text"` / `echo "$text" | grep -qE <pattern>`."""
    return grep_q(pattern, _here_string(text), ignore_case=ignore_case, fixed=fixed)


def grep_o(pattern, text, ignore_case=False):
    """`grep -oE` as a list of matches, in order, across every record."""
    if ignore_case:
        compiled = re.compile(pattern, re.IGNORECASE)
        records, _ = _records(text)
        out = []
        for record in records:
            out.extend(m.group(0) for m in compiled.finditer(record))
        return out
    return _grep_only(pattern, text)


def grep_lines(pattern, text, invert=False, ignore_case=False, fixed=False):
    """`grep -E` (or `grep -vE`) as the list of records that matched."""
    flags = re.IGNORECASE if ignore_case else 0
    compiled = re.compile(re.escape(pattern) if fixed else pattern, flags)
    records, _ = _records(text)
    return [r for r in records if bool(compiled.search(r)) != invert]


def sed_sub(pattern, repl, text, count=0):
    """`sed -E 's/x/y/g'` applied per record, final newline preserved.

    `count=0` is the `g` flag; `count=1` is sed with no flag, which replaces
    only the FIRST match on each line and is a different thing.
    """
    records, terminated = _records(text)
    return _sed_out([re.sub(pattern, repl, r, count=count) for r in records], terminated)


def awk_field(text, index):
    """`awk '{print $N}'`, with awk's default whitespace splitting.

    `$NF` is `index=-1`. Empty records print an empty line, which is what awk
    does and what a naive `split()` on a blank line would get wrong.
    """
    records, _ = _records(text)
    out = []
    for record in records:
        fields = record.split()
        if not fields:
            out.append("")
        elif index == -1:
            out.append(fields[-1])
        elif 1 <= index <= len(fields):
            out.append(fields[index - 1])
        else:
            out.append("")
    return "".join(line + "\n" for line in out)


def case_glob(value, *patterns):
    """`case "$x" in <pattern>) ... esac` -- shell globbing, not regex.

    `fnmatch` is NOT this: it special-cases a leading dot and, on some
    platforms, normalises case. A shell `case` does neither, so the glob is
    translated by hand.
    """
    return any(re.fullmatch(_glob_to_re(p), value, re.DOTALL) for p in patterns)


def _glob_to_re(pattern):
    out = []
    i = 0
    while i < len(pattern):
        char = pattern[i]
        if char == "*":
            out.append(".*")
        elif char == "?":
            out.append(".")
        elif char == "[":
            end = pattern.find("]", i + 2)
            if end == -1:
                out.append(r"\[")
            else:
                body = pattern[i + 1 : end]
                if body.startswith("!"):
                    body = "^" + body[1:]
                out.append("[" + body + "]")
                i = end + 1
                continue
        else:
            out.append(re.escape(char))
        i += 1
    return "".join(out)


# ---------------------------------------------------------------------------
# Running things, the way a guard's `$( ... 2>/dev/null )` runs them
# ---------------------------------------------------------------------------


def run_out(argv, cwd=None, env=None, want_rc=False, stdin=None):
    """A command substitution: stdout with its trailing newlines stripped.

    stderr is discarded because every call site in the guards writes
    `2>/dev/null`. `want_rc=True` returns None on a non-zero exit, which is the
    `x=$(cmd) || exit 0` shape; the default returns the (possibly empty) output
    and drops the status, which is the `x=$(cmd 2>/dev/null)` shape. Confusing
    the two is how a failing command becomes an empty string that reads as a
    real answer, so the caller has to choose.
    """
    try:
        proc = subprocess.run(
            list(argv),
            capture_output=True,
            check=False,
            cwd=cwd,
            env=env,
            input=stdin.encode("utf-8") if isinstance(stdin, str) else stdin,
        )
    except OSError:
        return None if want_rc else ""
    if want_rc and proc.returncode != 0:
        return None
    return _command_substitution(proc.stdout.decode("utf-8", "surrogateescape"))


def run_rc(argv, cwd=None, env=None):
    """`cmd >/dev/null 2>&1; echo $?` -- the status alone."""
    try:
        proc = subprocess.run(argv, capture_output=True, check=False, cwd=cwd, env=env)
    except OSError:
        return 127
    return proc.returncode


def have(name):
    """`command -v <name> >/dev/null 2>&1`.

    PATH is read at CALL time, never cached: the differential prepends a stub
    directory between two calls in one process, and a cached answer would make
    every case after the first read the wrong PATH.
    """
    for directory in os.environ.get("PATH", "").split(os.pathsep):
        if directory and os.access(os.path.join(directory, name), os.X_OK):
            return True
    return False


def git_out(args, cwd=None, want_rc=False):
    """`git ... 2>/dev/null` as a command substitution."""
    return run_out(["git", *args], cwd=cwd, want_rc=want_rc)


def repo_root():
    """The tree holding both `.claude` and `.ci`, found by looking, not counting.

    The same predicate `rediacc_hooks.tests.corpus` and `run_tests` use, and
    for the reason `.ci/rediacc_ci/paths.py` argues at length: a `parents[N]`
    constant still resolves after the file moves, silently, to the wrong tree.
    """
    for candidate in pathlib.Path(__file__).resolve().parents:
        if (candidate / ".claude").is_dir() and (candidate / ".ci").is_dir():
            return candidate
    msg = "no repository root above %s (looked for a directory holding .claude and .ci)" % __file__
    raise RuntimeError(msg)
