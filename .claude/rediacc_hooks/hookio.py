#!/usr/bin/env python3
"""The preamble every ported guard repeats, and the shell primitives it needs.

WHAT THIS IS. `.claude/hooks/pre-bash/lib/command-scan.sh` already had a name
for this idea: `hook_init` was extracted there "after
check:ci-shape-duplication counted three identical copies", and its header argues that centralising the preamble matters more than the line count suggests, because "a guard that hand-rolls its own preamble is a guard that can drift away from that fix without anything noticing". This module is that argument applied to the whole chain rather than to three files: every ported guard
reads its event, its command, its file path and its cwd from here.

WHY IT IS SEPARATE FROM `shellscan`. `shellscan` is the transliteration of ONE bash file and is judged by a differential against it. Nothing here has a bash twin of its own: it is the union of the preambles that were copied into 46 separate guards, so it has no single oracle. Keeping the two apart keeps `shellscan`'s differential honest, because a helper added here can never change
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
import threading

# Re-exported so a guard does not grow a second spelling of the character classes bash means by [[:space:]]. `shellscan` owns the definitions; a guard that needs them imports them from here, and there is exactly one copy.
from rediacc_hooks.shellscan import (
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

# The names above that guards reach as `hookio.<name>`; listing them here is what states them as re-exports (SPACE and BLANK are also used below, by `_RX_CLASSES`).
__all__ = [
    "BLANK",
    "SPACE",
    "_command_substitution",
    "_grep_only",
    "_grep_out",
    "_here_string",
    "_printf_line",
    "_records",
    "_sed_out",
    "_tr",
]

ALLOW = 0
DENY = 2

# The placeholders `rx` below understands. `{S}` is the whole `[[:space:]]`
# class and `{B}` is the same class without the newline, matching the two
# constants re-exported above; there is no third, because a guard needing a third would be inventing a fourth spelling of the thing this module exists to have one of.
_RX_CLASSES = (("{S}", SPACE), ("{B}", BLANK))


def rx(pattern):
    """A guard's regex written as ONE raw string, with `{S}` / `{B}` for the classes.

    WHAT IT REPLACES, AND WHY THAT WAS WORTH A FUNCTION. A guard that needs the space class inside a character class cannot interpolate a constant into a raw literal, so twenty-three of them built the pattern by concatenation::

        NODE_BUNDLE = (
            r"(^|[;&|(]|["
            + hookio.SPACE
            + r"])node["
            + hookio.SPACE
            + r"]+..."
        )

    Every line of that except the fragments is scaffolding, and the scaffolding is IDENTICAL in every guard that has one: `check:ci-shape-duplication` reported it as its two largest Python findings the moment the guards entered its corpus, ten copies of one six-line window and eight of another. There is nothing per-guard in those lines to preserve -- the regex fragments are the
    content, and they survive here verbatim inside a single readable string.

    IT REFUSES A PATTERN WITH NO PLACEHOLDER, and that refusal is the point rather than tidiness. `rx(r"git push")` would return its argument unchanged and read, at every call site, as though the space class were involved when it is not; the next edit would add `[ ]` by hand and the two spellings this module exists to prevent would be back. A call that buys nothing is a mistake, so
    it says so.
    """
    if not any(token in pattern for token, _ in _RX_CLASSES):
        raise ValueError(
            "rx() was given a pattern with no {S} or {B} placeholder: %r. "
            "Write it as a plain literal, or use the placeholder." % pattern
        )
    for token, expansion in _RX_CLASSES:
        pattern = pattern.replace(token, expansion)
    return pattern


class Event:
    """One hook invocation: the payload in, the three results out.

    `payload` is the RAW stdin text and not a parsed document, because that is what the guards see. Two of them (the chain head's jq check, and the `nojq` arm of `block-settled-questions.sh`) deliberately read the raw JSON body rather than a parsed value, on the stated grounds that they run exactly when the parser is missing. A class that only offered parsed access could not
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

        Parsed lazily and cached: a guard that never asks pays nothing, and a guard that asks four times forks jq four times in bash but parses once here. That is a performance difference and not a behavioural one, because the payload cannot change mid-run.
        """
        if self._doc is _UNPARSED:
            try:
                self._doc = json.loads(self.payload)
            except (ValueError, TypeError):
                # NOT `None`. A payload of the four characters `null` PARSES, and `jq -r .tool_input.command` on it prints `null`; a payload of `nonsense` does not parse and jq exits 5 with an empty stdout. Measured 2026-09-06, both shapes, and the first cut of this collapsed them onto None and got the second one wrong -- a broken payload read as the string "null", which 26 guards
                # would then have scanned as a command.
                self._doc = _BROKEN
        return self._doc

    def raw(self, *path):
        """`jq -r '.a.b'` -- `null` for an absent key, "" for a broken parse.

        See point 1 in the module docstring. The four characters, deliberately.
        """
        return _jq_raw(self.doc, path, empty=False)

    def field(self, *path):
        """`jq -r '.a.b // empty'` -- "" for absent, null, false OR broken.

        `//` is jq's ALTERNATIVE operator, and its left side is falsy for `null` AND for `false`. That matters for exactly one call site, `.tool_input.run_in_background // false`, which is why `flag()` below exists rather than being folded in here.
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

        `block-long-sleep.sh` compares the RESULT to the string `true`, so a Python bool here would silently never match.
        """
        got = _jq_raw(self.doc, path, empty=True)
        return got if got in ("true", "false") else "false"

    def default(self, path, fallback):
        """`jq -r '.a // "unknown"'` -- an explicit textual fallback."""
        got = _jq_raw(self.doc, path, empty=True)
        return got if got != "" else fallback

    def texts(self, *paths):
        """The `[.content, .new_string, .new_source, (.edits[]?.new_string)]` collector four pre-edit guards share, joined by newlines.

        jq prints an array under `-r` as one element per line, so the bash receives a newline-joined string and greps it as a whole. Nulls are printed as the word `null` by `-r`, and the four guards that use this
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
        """`CLAUDE_PROJECT_DIR`, the root nearly every guard cd's into, and when it is unset or EMPTY the checkout the event stands in (`project_root`).

        NOT `.` (#f32d3604). The bash spelled `${CLAUDE_PROJECT_DIR:-.}`, and `.` is the hook PROCESS's directory, which is the project only when the process happens to stand at its root. Run from `.claude/` with the variable unset, block_git_force_push judged `.claude/` as the project and allowed `git push --prune origin` (rc 0 against rc 2 from the root, 2026-10-11), and test_hooks_static failed those two cases. The same class was fixed for `shellscan.repo_root_env` in fae7c16a2. The answer with the variable set is unchanged.
        """
        got = self._env.get("CLAUDE_PROJECT_DIR")
        if got:
            return got
        return project_root(self.field("cwd") or self.cwd)

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

        Separate from `warn` because a heredoc's final newline is part of the body, and appending another would put a blank line at the end of every multi-paragraph message. That is a byte the differential compares.
        """
        self.err.write(text)

    def result(self, rc):
        return rc, self.out.getvalue(), self.err.getvalue()


_UNPARSED = object()
# jq exited 5 and wrote nothing: distinct from a document that IS JSON null.
_BROKEN = object()


def _jq_raw(doc, path, empty):
    """One `jq -r` field read, with jq's own type rules.

    jq indexes only objects and null. Handed a number, a string or an array it exits 5 with nothing on stdout, which the command substitution turns into "" -- the same value as a parse failure, and the guards cannot tell the two apart either.
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
        # `//` is jq's ALTERNATIVE operator and its left side is FALSY, not merely null: `false // empty` is empty. Measured against real jq 2026-09-06, and the first cut of this returned the word "false", which is what `// false` gives and what `// empty` never does.
        return ""
    if isinstance(node, str):
        return _command_substitution(node + "\n")
    if isinstance(node, bool):
        return "true" if node else "false"
    return _command_substitution(json.dumps(node, separators=(",", ":")) + "\n")


def _jq_collect(doc, path):
    """`.a.b[]?.c` -- every element, nulls dropped, as `-r` would print them.

    A `[]?` step over anything that is not an array yields nothing rather than an error, which is what the `?` means and what the four pre-edit guards rely on for a payload with no `edits` key.
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


# --------------------------------------------------------------------------- The shell primitives the guards use, beyond the ones `shellscan` already owns ---------------------------------------------------------------------------


def grep_q(pattern, text, ignore_case=False, fixed=False):
    """`grep -qE <pattern>` over `printf '%s' "$text"`.

    NO HERE-STRING HERE. `printf '%s' "$x" | grep` and `grep <<<"$x"` differ on the empty subject: the pipe gives grep zero records so it cannot match, the here-string gives it one empty record so `^$` would. The guards use both spellings, so both are available and the caller picks the one its original wrote. `echo "$x" | grep` is `here_string` too, since echo appends a newline.
    """
    flags = re.IGNORECASE if ignore_case else 0
    compiled = re.compile(re.escape(pattern) if fixed else pattern, flags)
    records, _ = _records(text)
    return any(compiled.search(record) for record in records)


# `git` global options that may sit between `git` and its subcommand: `-C <dir>`, `-c <k=v>`, `--git-dir[=]<d>`, `--work-tree[=]<d>`, `--no-pager`.
# An option's argument is a bare word or a quoted string (`git -C "/path with spaces" push`, per-commit review c0d7489b.1).
_GIT_OPT_ARG = r"""(?:"[^"]*"|'[^']*'|\S+)"""
_GIT_GLOBAL_OPTS = (
    r"(?:\s+(?:-C\s+%(a)s|-c\s+%(a)s|--git-dir(?:=|\s+)%(a)s|--work-tree(?:=|\s+)%(a)s|--no-pager))*"
    % {"a": _GIT_OPT_ARG}
)
_GIT_PUSH_RE = re.compile(r"\bgit" + _GIT_GLOBAL_OPTS + r"\s+push\b")


_QUOTED_SPAN_RE = re.compile(r"""(-c\s+)?("[^"]*"|'[^']*')""")
_MENTIONS_PUSH_RE = re.compile(r"git\s+push")


def normalize_git_push(cmd):
    """`git -C <dir> push ...` (and the other global-option spellings) rewritten to `git push ...`.

    The post-bash push hooks look for the literal `git push`, so `git -C /home/x/console push -q origin b` never matched: on 2026-10-02 a push spelled that way armed no CI watcher (arm_ci_watch.py) and cancelled no older run (cancel_old_ci.py). The `-C` directory does not need to survive: each hook judges the session's own checkout (arm_ci_watch then checks `origin/<branch> == HEAD`, so a push of another repo still arms nothing).
    """
    # Deferred: hookio is imported far more widely than this one function needs shellscan.
    from rediacc_hooks import shellscan

    # Text that is not a command bash runs is not a push (#00ea15c1, 2026-10-02): a heredoc BODY (a commit message or a file written with `cat <<EOF`) and a quoted string that merely mentions `git push` (`git commit -m "... git push ..."`) both matched, so a commit could arm a watch or cancel a run. A quoted span after `-c` stays: `sh -c "git push"` runs it.
    text = _GIT_PUSH_RE.sub("git push", shellscan._strip_heredocs(cmd or ""))
    return _QUOTED_SPAN_RE.sub(
        lambda m: m.group(0) if m.group(1) or not _MENTIONS_PUSH_RE.search(m.group(2)) else '""',
        text,
    )


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

    `fnmatch` is NOT this: it special-cases a leading dot and, on some platforms, normalises case. A shell `case` does neither, so the glob is translated by hand.
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


# --------------------------------------------------------------------------- Running things, the way a guard's `$( ... 2>/dev/null )` runs them ---------------------------------------------------------------------------


def _stdin_bytes(text):
    """The bytes a str stdin stands for, with no input that can raise.

    Encoding a str that holds a lone surrogate with plain `encode("utf-8")` raised UnicodeEncodeError out of run_out, and a crashed guard is no decision, so the command ran (review 46b000ae.1); swallowing it as a command that did not run hid the caller's text instead (review dd407156.2). Neither is needed, because every lone surrogate has a byte form.
    A surrogate in U+DC80..U+DCFF is what a `surrogateescape` decode makes of a byte that is not UTF-8, and run_out decodes command output exactly that way, so `surrogateescape` hands such text back as the bytes it came from.
    Any other lone surrogate (U+D800..U+DC7F, U+DD00..U+DFFF) never came from a decode, and `surrogatepass` writes it as its three-byte form; `surrogatepass` encodes every code point, so the fallback cannot raise.
    A HIGH SURROGATE FOLLOWED BY A LOW ONE IS ONE CODE POINT (review 2925782e.2), and goes as that code point's four UTF-8 bytes: the per-character rule alone sent U+D83D U+DE00 as two three-byte surrogate forms instead of the bytes of U+1F600.
    THE ESCAPED-BYTE RULE WINS OVER THE JOIN (review 98777d8c.1): a low half in U+DC80..U+DCFF is never joined, because a UTF-16 round trip merged a lone U+D83D before the escaped byte U+DCFF into U+1F4FF and the byte 0xFF was lost. Such a high surrogate goes as its own three-byte form, and the escaped byte as the byte.
    """
    try:
        return text.encode("utf-8", "surrogateescape")
    except UnicodeEncodeError:
        out = []
        i = 0
        while i < len(text):
            code = ord(text[i])
            low = ord(text[i + 1]) if i + 1 < len(text) else 0
            if 0xD800 <= code <= 0xDBFF and 0xDC00 <= low <= 0xDFFF and not 0xDC80 <= low <= 0xDCFF:
                out.append(chr(0x10000 + ((code - 0xD800) << 10) + (low - 0xDC00)).encode("utf-8"))
                i += 2
                continue
            if 0xDC80 <= code <= 0xDCFF:
                out.append(bytes([code - 0xDC00]))
            else:
                out.append(text[i].encode("utf-8", "surrogatepass"))
            i += 1
        return b"".join(out)


def run_out(argv, cwd=None, env=None, want_rc=False, stdin=None):
    """A command substitution: stdout with its trailing newlines stripped.

    stderr is discarded because every call site in the guards writes
    `2>/dev/null`. `want_rc=True` returns None on a non-zero exit, which is the
    `x=$(cmd) || exit 0` shape; the default returns the (possibly empty) output
    and drops the status, which is the `x=$(cmd 2>/dev/null)` shape. Confusing
    the two is how a failing command becomes an empty string that reads as a real answer, so the caller has to choose.
    """
    data = _stdin_bytes(stdin) if isinstance(stdin, str) else stdin
    try:
        proc = subprocess.run(
            list(argv),
            capture_output=True,
            check=False,
            cwd=cwd,
            env=env,
            input=data,
        )
    # ValueError is what subprocess raises for an argument or cwd holding a NUL byte, which bash itself cuts at. Uncaught, it crashed the guard, and a crashed guard is no decision, so the command ran (block_unproven_bulk_transform `gh pr create --head` with a NUL, 2026-10-15); a word that cannot be passed is a command that did not run.
    except (OSError, ValueError):
        return None if want_rc else ""
    if want_rc and proc.returncode != 0:
        return None
    return _command_substitution(proc.stdout.decode("utf-8", "surrogateescape"))


def run_rc(argv, cwd=None, env=None):
    """`cmd >/dev/null 2>&1; echo $?` -- the status alone."""
    try:
        proc = subprocess.run(argv, capture_output=True, check=False, cwd=cwd, env=env)
    except (OSError, ValueError):
        return 127
    return proc.returncode


def command_v(name):
    """What bash 5.3's `command -v <name>` prints for a name that is not a builtin, function or alias; "" when it prints nothing.

    RULE T (PLAN-retire-bash-oracles A4, A0 L15). The lookup this replaces returned the first PATH entry where `os.access(X_OK)` held, and a DIRECTORY passes that test: with `PATH=/etc:/usr/bin`, `ssh` resolved to the directory `/etc/ssh`. Bash's search, measured 2026-09-24 against `/usr/bin/bash` 5.3.9, is:

      * a name containing `/` is not searched: it is printed when it is an executable file;
      * otherwise the FIRST EXECUTABLE REGULAR FILE on PATH wins, directories never count;
      * only when no executable exists anywhere does the first NON-executable regular file win (`PATH=/etc:/usr/bin command -v hosts` prints `/etc/hosts`, rc 0);
      * an empty PATH entry means the current directory, printed as `./<name>`.

    PATH is read at CALL time, never cached: the differential prepends a stub directory between two calls in one process, and a cached answer would make every case after the first read the wrong PATH.
    """
    if "/" in name:
        return name if os.path.isfile(name) and os.access(name, os.X_OK) else ""
    fallback = ""
    for directory in os.environ.get("PATH", "").split(os.pathsep):
        candidate = os.path.join(directory or ".", name)
        if not os.path.isfile(candidate):
            continue
        if os.access(candidate, os.X_OK):
            return candidate
        if fallback == "":
            fallback = candidate
    return fallback


def have(name):
    """`command -v <name> >/dev/null 2>&1`: true exactly when `command_v` prints something."""
    return command_v(name) != ""


def git_out(args, cwd=None, want_rc=False):
    """`git ... 2>/dev/null` as a command substitution."""
    return run_out(["git", *args], cwd=cwd, want_rc=want_rc)


def project_root(start):
    """The project a directory belongs to, as Claude Code names one in `CLAUDE_PROJECT_DIR`: the git checkout holding `start`, climbed through its superprojects to the top, or `start` itself, made absolute, when it is in none.

    Climbed because the session's project is the console even when its shell stands inside `private/renet`, and a guard reading `CLAUDE_PROJECT_DIR` there has always been handed the console. Only SUPERPROJECT links are climbed (review 67459d36.1): a standalone clone that merely sits inside another checkout's tree, like a writer's scratch clone, is its own project, not the outer one's.
    """
    here = os.path.abspath(start)
    top = git_out(["rev-parse", "--show-toplevel"], cwd=here, want_rc=True)
    if not top:
        return here
    for _depth in range(8):
        outer = git_out(["rev-parse", "--show-superproject-working-tree"], cwd=top, want_rc=True)
        if not outer:
            break
        top = outer
    return top


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


def landing(path, cwd=None, root=None):
    """`(absolute, judged, shown)` for the path a write tool was handed: WHERE THE WRITE LANDS, resolved as the kernel resolves it.

    `realpath` over the path joined to `cwd` (else `root`, else this checkout's root), with NO lexical normalisation first: the kernel follows a symlink before it applies the `..` after it, so `out/l/../f` with `out/l` a link into a guarded directory lands inside that directory, and `normpath` would have judged it at `out/f` (review 9c6817f3.1-.4, where four guards each carried that ordering in a copy of this function). `judged` is the landing relative to `root` when it is inside it, the form the guards' patterns are written for, and absolute otherwise. `shown` is what was typed, with the landing appended when the two differ, so a refusal never names a path the write would not touch. An empty path is returned as typed, three times. A path the OS itself refuses (an embedded NUL, 9c6817f3.5) is judged and shown as typed, and its `absolute` is the path joined to the `cwd` it was given, never left relative: a caller reading a directory out of it would otherwise read the hook PROCESS's directory (3c0094e0.2).
    """
    if not path or path == "null":
        return path, path, path
    try:
        if root is None:
            root = str(repo_root())
    except RuntimeError:
        root = cwd or os.getcwd()
    joined = os.path.join(cwd or root, path)
    try:
        landed = os.path.realpath(joined)
        rel = os.path.relpath(landed, os.path.realpath(root))
    except ValueError:
        return joined, path, path
    judged = landed if rel == ".." or rel.startswith("../") else rel
    shown = path if landed == joined else "%s (lands at %s)" % (path, landed)
    return landed, judged, shown


def write_world_file(path, text):
    """Write a differential fixture file at a FIXED path without a torn read.

    Several guards build their world at one `tempfile.gettempdir()` path, because the goldens quote that path literally. Every pytest process on the host shares it: xdist workers, and a second checkout's pre-push. `open(path, "w")` truncates first, so a guard run by one process between another's truncate and write read an empty record and admitted the edit (rc 0 against golden rc 2, block_compacted_plan_edit, 1006-2 pre-push 2026-10-06). Equal bytes are left alone; anything else lands whole through `os.replace`.
    """
    path = pathlib.Path(path)
    try:
        if path.read_text(encoding="utf-8") == text:
            return
    except OSError:
        pass
    tmp = path.with_name(".%s.%d.tmp" % (path.name, os.getpid()))
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def ensure_world_symlink(target, link):
    """Create a differential fixture's directory symlink at a FIXED path, race-free.

    The same shared-path hazard as write_world_file: two xdist workers both saw no link, both called os.symlink, and the loser raised FileExistsError (Pytest 3/4, Console CI run 39215455203, block_plan_without_tasks). The link is created once; a concurrent creator's identical link is accepted, and a link to anything else is replaced whole through os.replace. The temporary name carries the pid AND the thread, so threads of one process never share it, and a stale one a crashed process left under a reused pid is cleared before use.
    """
    target, link = str(target), str(link)
    try:
        os.symlink(target, link)
        return
    except FileExistsError:
        pass
    if os.path.islink(link) and os.readlink(link) == target:
        return
    tmp = "%s.%d.%d.tmp" % (link, os.getpid(), threading.get_ident())
    pathlib.Path(tmp).unlink(missing_ok=True)
    os.symlink(target, tmp)
    os.replace(tmp, link)
