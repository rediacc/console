"""ONE parser for GitHub Actions workflows, with no dependency to import.

WHAT IT REPLACES, MEASURED 2026-09-06. Fifteen separate parsers read `.github/workflows/*.yml` in this repository, in three incompatible ways:

  PyYAML, 8 gates      check_checkout_cone.py, check_pr_head_ref_completeness.py,
                       check_workflow_env_provision.py, check_python_gate_deps.py,
                       check_ci_gate_prerequisites.py, check_workflow_submodule_deps.py,
                       check_secret_reachability.py, check_git_history_depth.py
  regex / line scan,   check_job_timeout_headroom.py, check_runner_advice.py,
  6 gates              check_environment_names.py, check_actions_allowlist.py,
                       check_docker_npm_pins.py, check_bws_map.py
  a hand scanner in    scripts/ci-runner/lanes.ts
  TypeScript

plus a dozen bash gates driving `awk` and `grep` over the same files. The corpus they disagree about is 28 files and 13,395 lines.

THE THREE OF THEM THAT WROTE DOWN WHY THEY DO NOT USE PyYAML ARE THE REASON THIS
MODULE HAS NO DEPENDENCY:

  * `scripts/ci-runner/lanes.ts:53-60` -- "A hand parser rather than PyYAML/`yaml`:
    this must run in the fast lane with no dependency, and a gate that imports one
    dies with ModuleNotFoundError on a clean runner while passing locally."
  * `check_environment_names.py:73-80` -- importing `yaml` there "died on
    check:ci-python-gate-deps".
  * `check_job_timeout_headroom.py:87-90` and `check_runner_advice.py:316-320` --
    "Deliberately regex-based rather than yaml.safe_load".

They are right about the constraint and each paid for it with a different partial parser. Measured again this session, and it is worse than a preference: pytest is provisioned by `uv tool install`, which builds an ISOLATED virtual environment, so `import yaml` fails inside the very suite these ports are judged by even though the system interpreter has PyYAML 6.0.3. A module that
imported it could not be tested here at all.

So this is a real parser for the subset of YAML that Actions workflows are, and its acceptance is that it agrees with PyYAML on every one of the 28 files. `tests/test_workflows.py` runs `yaml.safe_load` in a SUBPROCESS under the system interpreter -- which is how the comparison happens at all from inside an environment that cannot import it -- and compares document to document.

THE SUBSET, stated so the boundary is a decision rather than a discovery. Block mappings, block sequences, block scalars (`|`, `>`, with `-` and `+` chomping and explicit indent indicators), single-line flow sequences and mappings, single and double quoted scalars with escapes, comments, and YAML 1.1 scalar resolution. NOT supported, because the corpus contains none of them and a
parser that guesses is worse than one that refuses: anchors and aliases, merge keys, tags, multiple documents, and complex mapping keys. `UnsupportedYAMLError` names the line.

THE ONE DELIBERATE DIVERGENCE FROM PyYAML, AND IT IS A BUG FIX. PyYAML applies YAML 1.1 resolution to KEYS as well as values, so the `on:` block that every workflow file opens with parses to the key `True`. `check_secret_reachability.py:151` carries a workaround for exactly that, and any consumer that forgets it silently finds no triggers. Keys here are always strings. The
differential normalises PyYAML's side before comparing, so the divergence is asserted rather than smoothed over -- see `test_workflows.py::test_pyyaml_turns_the_on_key_into_a_boolean`.

VALUES ARE STILL RESOLVED THE YAML 1.1 WAY, including `yes`/`no`/`on`/`off` as booleans, because that is what `submodules: true`, `fetch-depth: 0` and `timeout-minutes: 12` mean to Actions and to every consumer here.
"""

import pathlib
import re

# YAML 1.1 boolean words, which is what PyYAML's safe_load resolves and therefore what every existing consumer in this tree already sees. YAML 1.2 dropped yes/no/on/off; matching 1.1 is a compatibility decision, not an oversight.
_TRUE = frozenset(["true", "True", "TRUE", "yes", "Yes", "YES", "on", "On", "ON"])
_FALSE = frozenset(["false", "False", "FALSE", "no", "No", "NO", "off", "Off", "OFF"])
_NULL = frozenset(["", "~", "null", "Null", "NULL"])

_INT_RE = re.compile(r"^[-+]?[0-9][0-9_]*$")
_OCT_RE = re.compile(r"^[-+]?0o?[0-7_]+$")
_HEX_RE = re.compile(r"^[-+]?0x[0-9a-fA-F_]+$")
_FLOAT_RE = re.compile(r"^[-+]?(\.[0-9]+|[0-9][0-9_]*(\.[0-9_]*)?)([eE][-+]?[0-9]+)?$")

# A block scalar header: the style, an optional chomping indicator, an optional explicit indentation indicator, in either order.
_BLOCK_HEADER_RE = re.compile(r"^([|>])([+-]?)([0-9]?)([0-9]?)([+-]?)\s*(#.*)?$")

# Constructs this parser refuses rather than guesses at. Each would produce a plausible-looking wrong answer, which is the failure mode the whole module exists to remove.
_ANCHOR_RE = re.compile(r"^[&*][A-Za-z0-9_-]")


class UnsupportedYAMLError(ValueError):
    """A construct outside the Actions subset. Names the line so it is findable.

    A distinct type so a caller can tell "this file uses a YAML feature I do not implement" from "this file is malformed", which want different responses: the first is a reason to widen the parser, the second is a reason to fix the file.
    """


class WorkflowParseError(ValueError):
    """Malformed input. Also names the line."""


def _error(kind, line_no: int, text: str, why: str):
    return kind("line %d: %s\n    %s" % (line_no, why, text.rstrip()))


# --------------------------------------------------------------------------- Scalars ---------------------------------------------------------------------------


def resolve_scalar(text: str) -> object:
    """A plain (unquoted) scalar as YAML 1.1 would resolve it.

    ORDER MATTERS AND IS NOT ARBITRARY: null, then bool, then int, then float, then string. `0x10` must reach the hex rule before the float rule, and the underscore stripping happens only inside the numeric branches so a plain string like `some_word` is never touched.
    """
    stripped = text.strip()
    if stripped in _NULL:
        return None
    if stripped in _TRUE:
        return True
    if stripped in _FALSE:
        return False
    if _HEX_RE.match(stripped):
        return int(stripped.replace("_", ""), 16)
    if _OCT_RE.match(stripped):
        body = stripped.replace("_", "").replace("0o", "0", 1)
        return int(body, 8)
    if _INT_RE.match(stripped):
        return int(stripped.replace("_", ""))
    if _FLOAT_RE.match(stripped) and any(ch in stripped for ch in ".eE"):
        return float(stripped.replace("_", ""))
    return stripped


_DOUBLE_ESCAPES = {
    "n": "\n",
    "t": "\t",
    "r": "\r",
    "0": "\0",
    "a": "\a",
    "b": "\b",
    "f": "\f",
    "v": "\v",
    "e": "\033",
    "\\": "\\",
    '"': '"',
    "/": "/",
    " ": " ",
}


def _parse_double_quoted(body: str) -> str:
    """The escape set YAML defines for double quotes, plus \\uXXXX.

    Hand-written rather than delegated to `json.loads`, which is the tempting shortcut: JSON rejects `\\e`, `\\v` and single quotes inside, all of which are legal here, and it would raise on files this parser must read.
    """
    out = []
    index = 0
    while index < len(body):
        char = body[index]
        if char != "\\":
            out.append(char)
            index += 1
            continue
        index += 1
        if index >= len(body):
            out.append("\\")
            break
        code = body[index]
        if code == "u":
            out.append(chr(int(body[index + 1 : index + 5], 16)))
            index += 5
            continue
        if code == "x":
            out.append(chr(int(body[index + 1 : index + 3], 16)))
            index += 3
            continue
        out.append(_DOUBLE_ESCAPES.get(code, code))
        index += 1
    return "".join(out)


def _strip_comment(text: str) -> str:
    """Drop a trailing `# ...` that is outside quotes and preceded by a space.

    THE SPACE IS REQUIRED BY YAML AND BY REALITY: `runs-on: ubuntu#1` is a value containing a hash, and `image: ghcr.io/x#tag` would lose its fragment to a naive split. A `#` at the very start of the field is a comment regardless.
    """
    quote = None
    index = 0
    while index < len(text):
        char = text[index]
        if quote:
            if char == "\\" and quote == '"':
                index += 2
                continue
            if char == quote:
                quote = None
        elif char in "\"'":
            quote = char
        elif char == "#" and (index == 0 or text[index - 1] in " \t"):
            return text[:index]
        index += 1
    return text


def _parse_flow(text: str, line_no: int):
    """A single-line flow collection: `[a, b]` or `{a: b, c: d}`.

    Nested flow is supported because `needs: [a, b]` and matrix `include:` both appear; a flow collection spanning lines is not, and is refused rather than silently truncated.
    """
    value, index = _flow_node(text, 0, line_no)
    rest = text[index:].strip()
    if rest:
        raise _error(WorkflowParseError, line_no, text, "trailing text after a flow collection")
    return value


def _flow_node(text: str, index: int, line_no: int):
    while index < len(text) and text[index] in " \t":
        index += 1
    if index >= len(text):
        raise _error(WorkflowParseError, line_no, text, "unterminated flow collection")
    char = text[index]
    if char == "[":
        return _flow_sequence(text, index + 1, line_no)
    if char == "{":
        return _flow_mapping(text, index + 1, line_no)
    return _flow_scalar(text, index, line_no)


def _flow_sequence(text: str, index: int, line_no: int):
    out = []
    while True:
        while index < len(text) and text[index] in " \t":
            index += 1
        if index >= len(text):
            raise _error(WorkflowParseError, line_no, text, "unterminated flow sequence")
        if text[index] == "]":
            return out, index + 1
        item, index = _flow_node(text, index, line_no)
        out.append(item)
        while index < len(text) and text[index] in " \t":
            index += 1
        if index < len(text) and text[index] == ",":
            index += 1


def _flow_mapping(text: str, index: int, line_no: int):
    out = {}
    while True:
        while index < len(text) and text[index] in " \t":
            index += 1
        if index >= len(text):
            raise _error(WorkflowParseError, line_no, text, "unterminated flow mapping")
        if text[index] == "}":
            return out, index + 1
        key, index = _flow_scalar(text, index, line_no, stop=":")
        while index < len(text) and text[index] in " \t":
            index += 1
        if index >= len(text) or text[index] != ":":
            raise _error(WorkflowParseError, line_no, text, "flow mapping key with no value")
        value, index = _flow_node(text, index + 1, line_no)
        # Keys are strings. See the module docstring: PyYAML resolves them and turns `on` into True.
        out[str(key) if key is not None else ""] = value
        while index < len(text) and text[index] in " \t":
            index += 1
        if index < len(text) and text[index] == ",":
            index += 1


def _flow_scalar(text: str, index: int, line_no: int, stop: str = ""):
    char = text[index]
    if char in "\"'":
        end = index + 1
        buf = []
        while end < len(text):
            if char == "'" and text[end] == "'":
                if end + 1 < len(text) and text[end + 1] == "'":
                    buf.append("'")
                    end += 2
                    continue
                return "".join(buf), end + 1
            if char == '"' and text[end] == "\\":
                buf.append(text[end : end + 2])
                end += 2
                continue
            if char == '"' and text[end] == '"':
                return _parse_double_quoted("".join(buf)), end + 1
            buf.append(text[end])
            end += 1
        raise _error(WorkflowParseError, line_no, text, "unterminated quoted scalar")
    end = index
    terminators = ",]}" + stop
    while end < len(text) and text[end] not in terminators:
        end += 1
    return resolve_scalar(text[index:end]), end


# --------------------------------------------------------------------------- The block parser ---------------------------------------------------------------------------

# `key:` / `key: value`, with the key optionally quoted. The key may not contain a colon unless quoted, which is the rule the corpus follows.
_KEY_RE = re.compile(r"^(?P<key>\"[^\"]*\"|'[^']*'|[^:#\s][^:]*?)\s*:(?:\s+(?P<rest>.*))?$")


class _Reader:
    """A cursor over the lines, with the two questions the parser keeps asking.

    A class rather than an index passed around because the sequence parser REWRITES a line in place (turning `- key: v` into ` key: v` so the item can be parsed as an ordinary mapping), and threading a mutable list plus an index through recursion by hand is where off-by-ones live.
    """

    def __init__(self, text: str) -> None:
        self.lines = text.split("\n")
        self.index = 0

    def at_end(self) -> bool:
        return self.index >= len(self.lines)

    def skip_ignorable(self) -> None:
        """Advance past blank lines and whole-line comments."""
        while self.index < len(self.lines):
            stripped = self.lines[self.index].strip()
            if stripped and not stripped.startswith("#"):
                return
            self.index += 1

    def peek(self) -> tuple[int, str] | None:
        """(indent, content) of the next meaningful line, or None at the end."""
        self.skip_ignorable()
        if self.at_end():
            return None
        raw = self.lines[self.index]
        return len(raw) - len(raw.lstrip(" ")), raw.strip()

    @property
    def line_no(self) -> int:
        return self.index + 1


def _block_scalar(reader: _Reader, header: str, parent_indent: int) -> str:
    """A `|` or `>` block, with chomping and an optional explicit indent.

    THE INDENT IS TAKEN FROM THE FIRST NON-EMPTY LINE unless the header states one, which is YAML's rule and the one that matters most here: every `run: |` body in these workflows relies on it, and getting it wrong shifts whole shell scripts by a space.
    """
    match = _BLOCK_HEADER_RE.match(header.strip())
    if not match:
        raise _error(WorkflowParseError, reader.line_no, header, "unreadable block scalar header")
    style = match.group(1)
    chomp = match.group(2) or match.group(5) or ""
    explicit = match.group(3) or match.group(4) or ""

    reader.index += 1
    start = reader.index
    body_indent = parent_indent + int(explicit) if explicit else None

    collected: list[str] = []
    while reader.index < len(reader.lines):
        raw = reader.lines[reader.index]
        if raw.strip() == "":
            collected.append("")
            reader.index += 1
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        if body_indent is None:
            if indent <= parent_indent:
                break
            body_indent = indent
        if indent < body_indent:
            break
        collected.append(raw[body_indent:])
        reader.index += 1

    if body_indent is None:
        reader.index = start
        return "" if chomp == "-" else "\n"

    # Trailing blank lines belong to the chomping decision, not to the content.
    while collected and collected[-1] == "":
        collected.pop()

    text = "\n".join(collected) if style == "|" else _fold(collected)

    if chomp == "-":
        return text
    if chomp == "+":
        # KEEP: every trailing newline survives. Counted from the lines that were popped above rather than guessed, so a two-blank-line ending stays two.
        #
        # THE LAST ELEMENT OF `text.split("\n")` IS NOT A LINE. A document ending in a newline splits to a final empty string, and counting it as a blank line adds one newline that PyYAML does not produce. Measured against PyYAML 6.0.3: `a: |+\n x\n\n` is `x\n\n`, not `x\n\n\n`.
        last_is_artifact = reader.index >= len(reader.lines) and reader.lines[-1] == ""
        trailing = 0
        probe = start + len(collected)
        limit = reader.index - (1 if last_is_artifact else 0)
        while probe < limit and reader.lines[probe].strip() == "":
            trailing += 1
            probe += 1
        return text + "\n" * (trailing + 1)
    return text + "\n" if text else ""


def _fold(lines: list[str]) -> str:
    """`>` folding, with the two rules that are easy to get subtly wrong.

    RULE 1: a single line break between two equally-indented non-empty lines folds to a SPACE. RULE 2: blank lines do not fold -- n blank lines between two paragraphs produce n newlines, not n+1. An implementation that appends a newline for the blank line AND another for the join produces `a\n\nb` where YAML says `a\nb`, which is exactly what this function did until the
    differential ran over `.github/actions/setup-workspace/action.yml` and found one extra newline inside a `>-` description.

    THE MORE-INDENTED RULE, which is the one people forget entirely: a line indented further than the block keeps its break literally. Folding it into a space would join two shell commands into one, silently.
    """
    out: list[str] = []
    pending = 0
    previous_more_indented = False
    for line in lines:
        if line == "":
            pending += 1
            continue
        more_indented = line.startswith((" ", "\t"))
        if not out:
            out.append(line)
        elif pending:
            # RULE 3, and it is the one that took a second measurement. A break NEXT TO a more-indented line is not folded at all, so it survives IN ADDITION to the blank lines: `a`, ``, ` b` is `a\n\n b`, while the same pair with `b` at the normal indent is `a\nb`. Found against .github/actions/app-token/action.yml, whose `description` lays a permission table out under a paragraph
            # exactly this way.
            keep = pending + 1 if (more_indented or previous_more_indented) else pending
            out.append("\n" * keep)
            out.append(line)
        elif more_indented or previous_more_indented:
            out.append("\n")
            out.append(line)
        else:
            out.append(" ")
            out.append(line)
        pending = 0
        previous_more_indented = more_indented
    return "".join(out)


def _parse_node(reader: _Reader, indent: int):
    """The value of a block at `indent`: a mapping, a sequence, or a scalar."""
    head = reader.peek()
    if head is None or head[0] < indent:
        return None
    if head[1].startswith("- ") or head[1] == "-":
        return _parse_sequence(reader, head[0])
    return _parse_mapping(reader, head[0])


def _parse_sequence(reader: _Reader, indent: int) -> list:
    out: list = []
    while True:
        head = reader.peek()
        if head is None or head[0] != indent:
            return out
        line_indent, content = head
        if not (content.startswith("- ") or content == "-"):
            return out
        raw = reader.lines[reader.index]
        dash = raw.index("-", line_indent)
        rest = raw[dash + 1 :]
        if rest.strip() == "" or _strip_comment(rest).strip() == "":
            reader.index += 1
            out.append(_parse_node(reader, indent + 1))
            continue
        body = rest.strip()
        # A PLAIN SCALAR ITEM -- `- ubuntu-24.04`, `- test-linux-x64` -- is the commonest shape in these files (every `needs:` and every matrix dimension) and is NOT a mapping. Routing it through the mapping path produces "expected `key:`" on a line that is perfectly valid, which is exactly what this parser did until the differential against PyYAML ran over the real corpus and
        # failed on ct-tests.yml:228.
        if not (body.startswith("- ") or body == "-" or _KEY_RE.match(body)):
            line_no = reader.line_no
            reader.index += 1
            out.append(_parse_inline(body, line_no))
            continue
        # REWRITE THE DASH AS SPACES and re-read the line as ordinary content. `- name: x` followed by ` run: y` is a mapping whose first key happens to share a line with the dash; blanking the dash makes that literally true and removes the need for a second, subtly different mapping parser. It also handles a nested sequence (`- - a`) for free.
        item_indent = dash + 1 + (len(rest) - len(rest.lstrip(" ")))
        reader.lines[reader.index] = " " * item_indent + rest.lstrip(" ")
        out.append(_parse_node(reader, item_indent))
    return out


def _parse_mapping(reader: _Reader, indent: int) -> dict:
    out: dict = {}
    while True:
        head = reader.peek()
        if head is None or head[0] != indent:
            return out
        _line_indent, content = head
        if content.startswith("- "):
            return out
        if _ANCHOR_RE.match(content):
            raise _error(
                UnsupportedYAMLError,
                reader.line_no,
                content,
                "anchors and aliases are outside the Actions subset",
            )
        match = _KEY_RE.match(content)
        if not match:
            raise _error(WorkflowParseError, reader.line_no, content, "expected `key:`")
        key = match.group("key").strip()
        if key[:1] in "\"'" and key[-1:] == key[:1]:
            key = key[1:-1]
        rest = match.group("rest")
        line_no = reader.line_no

        if rest is None or _strip_comment(rest).strip() == "":
            if rest is not None and rest.strip()[:1] in ("|", ">"):
                out[key] = _block_scalar(reader, rest.strip(), indent)
                continue
            reader.index += 1
            # A SEQUENCE MAY SIT AT THE KEY'S OWN INDENT. YAML allows `needs:\n- a\n- b` with the dashes level with `needs`, and a parser that only looks deeper reads that as a null value and then loses the whole list in silence.
            nested = reader.peek()
            if nested and nested[0] == indent and (nested[1].startswith("- ") or nested[1] == "-"):
                out[key] = _parse_sequence(reader, indent)
            else:
                out[key] = _parse_node(reader, indent + 1)
            continue

        value_text = rest.strip()
        if value_text[0] in ("|", ">"):
            out[key] = _block_scalar(reader, value_text, indent)
            continue
        reader.index += 1
        if value_text[0] not in "[{\"'":
            value_text = _continue_plain(reader, value_text, indent)
        out[key] = _parse_inline(value_text, line_no)
    return out


def _continue_plain(reader: _Reader, first: str, indent: int) -> str:
    """A plain scalar that runs onto the following, more-indented lines.

    THE CASE THAT COST TWO WHOLE JOBS' WORTH OF STEPS.
    `.github/workflows/cd-deploy-account.yml:249-251` writes an Actions expression across three lines:

        STRIPE_SECRET_KEY: ${{ inputs.target == 'stable'
          && env.BWS_STRIPE_SECRET_KEY
          || env.BWS_STRIPE_SANDBOX_SECRET_KEY }}

    A parser that reads only the first line does not merely truncate the value -- the two orphaned continuation lines are more indented than the mapping, so the mapping ends there, and everything after it in the file is silently dropped. The differential against PyYAML measured the damage exactly: 13 steps parsed where 15 exist, with `Deploy account Worker` and `Set Worker secrets`
    gone. Nothing about the result looked wrong; there was simply less of it.

    YAML folds these with a single space, which is why `${{ a\n&& b }}` and
    `${{ a && b }}` are the same expression to Actions and must be the same string
    here. A blank line or a whole-line comment ends the scalar.
    """
    parts = [_strip_comment(first).strip()]
    while reader.index < len(reader.lines):
        raw = reader.lines[reader.index]
        stripped = raw.strip()
        if stripped == "" or stripped.startswith("#"):
            break
        if len(raw) - len(raw.lstrip(" ")) <= indent:
            break
        parts.append(_strip_comment(stripped).strip())
        reader.index += 1
    return " ".join(part for part in parts if part)


def _parse_inline(text: str, line_no: int):
    """A value that sits on the same line as its key."""
    if text[0] in "[{":
        return _parse_flow(text, line_no)
    if text[0] in "\"'":
        value, index = _flow_scalar(text, 0, line_no)
        trailing = _strip_comment(text[index:]).strip()
        if trailing:
            raise _error(WorkflowParseError, line_no, text, "trailing text after a quoted scalar")
        return value
    if _ANCHOR_RE.match(text):
        raise _error(
            UnsupportedYAMLError, line_no, text, "anchors and aliases are outside the subset"
        )
    return resolve_scalar(_strip_comment(text))


def parse(text: str):
    """Parse one YAML document. Returns the same shape `yaml.safe_load` would.

    Multiple documents are refused rather than silently reduced to the first, which is the shape of mistake that makes a gate judge half a file.
    """
    for offset, line in enumerate(text.split("\n")):
        if line.rstrip() == "---" and offset > 0:
            raise _error(
                UnsupportedYAMLError, offset + 1, line, "multiple documents are not supported"
            )
    body = text
    body = body.removeprefix("---\n")
    reader = _Reader(body)
    head = reader.peek()
    if head is None:
        return None
    return _parse_node(reader, head[0])


def load(path: pathlib.Path | str):
    """Parse a file. The path is included in any error, because a line number without a filename is useless when 28 files are being read in a loop."""
    target = pathlib.Path(path)
    try:
        return parse(target.read_text(encoding="utf-8"))
    except (WorkflowParseError, UnsupportedYAMLError) as exc:
        raise type(exc)("%s: %s" % (target, exc)) from exc


# --------------------------------------------------------------------------- The projection every consumer actually wants ---------------------------------------------------------------------------


class Step:
    """One step, with the four fields the fifteen parsers all reach for."""

    __slots__ = ("env", "name", "raw", "run", "uses", "with_")

    def __init__(self, raw: dict) -> None:
        self.raw = raw
        self.name = raw.get("name") or ""
        self.uses = raw.get("uses") or ""
        self.run = raw.get("run") or ""
        self.env = raw.get("env") or {}
        self.with_ = raw.get("with") or {}

    def __repr__(self) -> str:
        return "Step(name=%r, uses=%r, run=%d B)" % (self.name, self.uses, len(self.run))


class Job:
    """One job and its steps, in file order."""

    __slots__ = ("env", "job_id", "needs", "raw", "runs_on", "steps", "timeout_minutes")

    def __init__(self, job_id: str, raw: dict) -> None:
        self.job_id = job_id
        self.raw = raw if isinstance(raw, dict) else {}
        self.steps = [Step(s) for s in self.raw.get("steps") or [] if isinstance(s, dict)]
        self.env = self.raw.get("env") or {}
        self.runs_on = self.raw.get("runs-on")
        self.timeout_minutes = self.raw.get("timeout-minutes")
        needs = self.raw.get("needs")
        # `needs:` is a string for one dependency and a list for several. Every consumer that forgets that iterates the CHARACTERS of the string.
        self.needs = [needs] if isinstance(needs, str) else list(needs or [])

    def __repr__(self) -> str:
        return "Job(%r, %d step(s))" % (self.job_id, len(self.steps))


class Workflow:
    """A parsed workflow file: its name, triggers, workflow-level env, and jobs."""

    __slots__ = ("doc", "env", "jobs", "name", "path", "triggers")

    def __init__(self, path: pathlib.Path | str, doc: dict) -> None:
        self.path = pathlib.Path(path)
        self.doc = doc if isinstance(doc, dict) else {}
        self.name = self.doc.get("name") or self.path.name
        self.env = self.doc.get("env") or {}
        # "on" as a STRING. PyYAML gives True here; see the module docstring.
        self.triggers = self.doc.get("on") or {}
        jobs = self.doc.get("jobs") or {}
        self.jobs = [Job(job_id, body) for job_id, body in jobs.items()]

    def job(self, job_id: str) -> Job | None:
        for job in self.jobs:
            if job.job_id == job_id:
                return job
        return None

    def steps(self):
        """Every (job, step) pair in file order. The loop 8 gates write by hand."""
        for job in self.jobs:
            for step in job.steps:
                yield job, step

    def __repr__(self) -> str:
        return "Workflow(%r, %d job(s))" % (self.path.name, len(self.jobs))


# --------------------------------------------------------------------------- Lane capabilities: the one consumer that exists in TypeScript today ---------------------------------------------------------------------------
#
# `scripts/ci-runner/lanes.ts:61 laneCapabilities()` answers "what has each CI job already installed", so a gate can be placed in the cheapest lane that satisfies it. It is a hand-written LINE SCANNER, for the dependency reason quoted in this module's docstring, and it is the only TypeScript parser of these files.
#
# WHAT IS REPRODUCED HERE IS ITS ANSWER, NOT ITS METHOD. This computes the same six fields from the structural parse above, and `test_workflows.py` runs the real `lanes.ts` through `npx tsx` and compares the two JSON documents over every workflow file. Two implementations reaching the same answer by different routes is a stronger statement than one transcribed from the other: a
# shared mistake in a regex cannot survive it.

_SUBMODULE_TRUE = frozenset(["true", "recursive", True])
_TARGETED_SUBMODULE_RE = re.compile(
    r"git submodule update --init(?:\s+--depth\s+\d+)?\s+(private/[\w-]+)"
)
_RUFF_RE = re.compile(r"pip install[^\n]*\bruff\b")
_PYYAML_RE = re.compile(r"pip install[^\n]*PyYAML")
SETUP_WORKSPACE = "./.github/actions/setup-workspace"
SETUP_GO = "actions/setup-go"


class LaneCapabilities:
    """What one CI job has installed. Mirrors lanes.ts:38-49 field for field."""

    __slots__ = ("job", "node", "runs_on", "submodules", "timeout_minutes", "tools")

    def __init__(self, job: str) -> None:
        self.job = job
        self.runs_on = ""
        self.timeout_minutes: int | None = None
        self.submodules: list[str] = []
        self.node = False
        self.tools: list[str] = []

    def as_dict(self) -> dict:
        """The exact JSON shape lanes.ts serialises, for the differential."""
        return {
            "job": self.job,
            "runsOn": self.runs_on,
            "timeoutMinutes": self.timeout_minutes,
            "submodules": self.submodules,
            "node": self.node,
            "tools": self.tools,
        }

    def satisfies(self, needs) -> bool:
        """lanes.ts:131. 'submodules' means any; 'private/x' means '*' or exact."""
        for need in needs:
            if need == "submodules":
                if not self.submodules:
                    return False
            elif need.startswith("private/"):
                if "*" not in self.submodules and need not in self.submodules:
                    return False
            elif need == "node":
                if not self.node:
                    return False
            elif need not in self.tools:
                return False
        return True

    def __repr__(self) -> str:
        return "LaneCapabilities(%r, runs_on=%r, tools=%r)" % (
            self.job,
            self.runs_on,
            self.tools,
        )


def lane_capabilities(workflow: "Workflow") -> list[LaneCapabilities]:
    """Per job, in file order. The structural twin of lanes.ts:61.

    THE `str()` ON runs-on IS NOT COSMETIC. lanes.ts reads the raw token out of the line, so `runs-on: ubuntu-slim` is the string "ubuntu-slim" there; the structural parse of the same line is also a string, but a bare `runs-on: 22` would resolve to an int here and to "22" there. Coercing at the boundary keeps the two comparable without weakening the parser for everyone else.
    """
    out = []
    for job in workflow.jobs:
        caps = LaneCapabilities(job.job_id)
        if isinstance(job.runs_on, str):
            caps.runs_on = job.runs_on
        elif job.runs_on is not None:
            caps.runs_on = str(job.runs_on)
        if isinstance(job.timeout_minutes, int) and not isinstance(job.timeout_minutes, bool):
            caps.timeout_minutes = job.timeout_minutes

        for step in job.steps:
            uses = step.uses if isinstance(step.uses, str) else ""
            if uses.startswith(SETUP_WORKSPACE):
                caps.node = True
            if uses.startswith(SETUP_GO) and "go" not in caps.tools:
                caps.tools.append("go")
            declared = step.with_.get("submodules") if isinstance(step.with_, dict) else None
            if declared in _SUBMODULE_TRUE and "*" not in caps.submodules:
                caps.submodules = ["*"]
            run = step.run if isinstance(step.run, str) else ""
            for line in run.split("\n"):
                if _RUFF_RE.search(line) and "ruff" not in caps.tools:
                    caps.tools.append("ruff")
                if _PYYAML_RE.search(line) and "python-yaml" not in caps.tools:
                    caps.tools.append("python-yaml")
                # SUPPRESSED ONCE '*' IS PRESENT, matching lanes.ts:111-114: a job that took every submodule already has this one, and listing it again would make an exact-match need look unsatisfiable.
                if "*" in caps.submodules:
                    continue
                for found in _TARGETED_SUBMODULE_RE.findall(line):
                    if found not in caps.submodules:
                        caps.submodules.append(found)
        out.append(caps)
    return out


def load_workflow(path: pathlib.Path | str) -> Workflow:
    return Workflow(path, load(path))


# LIFTED FROM check_bws_map.py, per agent/plans/PLAN-github-actions-to-bitwarden.md Decision 4: "NO NEW PARSER... those three should be lifted into rediacc_ci/workflows.py so both gates import one copy, which is the same move workflows.py was created to make." `check_actions_vars.py` needed the exact same corpus and the exact same "which job owns this line" answer that `check_bws_map.py` already had; a second copy of either is a second answer to one question.
#
# LINE-SCAN, NOT STRUCTURAL. `job_index`/`job_at` answer "which job owns line N" from the raw text, not from a parsed `Workflow`/`Job` tree, because both callers need this for a `vars.NAME`/`secrets.NAME` reference found by a bare regex over the whole file -- turning every such reference into a structural walk of `Job.steps` would mean re-deriving the line number the structural
# parse does not keep. `JOB_RE` matches this repo's own convention (two-space top-level job indent under `jobs:`), the same assumption `check_bws_map.py` made.
JOB_RE = re.compile(r"^  ([A-Za-z0-9_-]+):\s*$")

# The frozen twin: `.ci/breakpoint/workflow/breakpoint.yml` carries a copy of `breakpoint.yml` at the same line numbers (see PLAN-github-actions-to-bitwarden.md Decision 3, "THE JOB THAT MUST NOT FETCH"), so any gate enumerating "every workflow-shaped file" must include it or silently miss half of every exemption keyed against it.
_EXTRA_WORKFLOW_DIRS = ((".ci", "breakpoint", "workflow"),)


def call_sites(root: pathlib.Path) -> list[pathlib.Path]:
    """Every file that may carry a workflow-shaped `vars.`/`secrets.`/`bws-secrets` reference: `.github/workflows/*.yml`, `.github/actions/*/action.yml`, and the breakpoint twin directory above."""
    out = sorted((root / ".github" / "workflows").glob("*.yml"))
    out += sorted((root / ".github" / "actions").glob("*/action.yml"))
    for parts in _EXTRA_WORKFLOW_DIRS:
        out += sorted(root.joinpath(*parts).glob("*.yml"))
    return out


def job_index(lines: list[str]) -> list[tuple[int, str]]:
    """[(line_no, job_id), ...] for every top-level job header in `lines`, in file order."""
    return [(i, m.group(1)) for i, line in enumerate(lines) if (m := JOB_RE.match(line))]


def job_at(index: list[tuple[int, str]], i: int) -> str | None:
    """The job owning line `i`, from an already-built `job_index`, or None above the first job header."""
    cur = None
    for start, name in index:
        if start <= i:
            cur = name
        else:
            break
    return cur


__all__ = [
    "JOB_RE",
    "SETUP_GO",
    "SETUP_WORKSPACE",
    "Job",
    "LaneCapabilities",
    "Step",
    "UnsupportedYAMLError",
    "Workflow",
    "WorkflowParseError",
    "call_sites",
    "job_at",
    "job_index",
    "lane_capabilities",
    "load",
    "load_workflow",
    "parse",
    "resolve_scalar",
]
