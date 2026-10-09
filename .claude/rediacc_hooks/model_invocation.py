"""The ONE predicate for "this command or skill file disables model invocation", shared by the hook guards and the CI gate.

THE RULING (operator, 2026-10-09), verbatim: "no command or skill in this repo is user-only. Every slash command and skill must be invocable by the AI. This is enforced twice: a hook refuses the flag at write time, and a CI gate fails on it." The two halves are
`guards/block_user_only_command.py` + `guards/block_user_only_command_shell_write.py` (write time) and the CI gate `check:ci-model-invocable-commands` (the tree). All of them import THIS module, so they cannot disagree about what counts.

WHAT IS IN SCOPE (`in_scope`). A Markdown file (`.md`, any casing) under a `.claude/commands/` or `.claude/skills/` directory, at ANY depth and under ANY parent: the console's own `.claude/`, a nested one such as `private/account/.claude/commands/update-tax-rates.md` (Claude Code discovers nested `.claude` directories in a monorepo), and a namespaced subdirectory (`.claude/commands/<ns>/x.md`). Measured
2026-10-09: `.claude/settings.json` enables no plugin and the tree tracks no plugin manifest, so no third discovery root exists here; a plugin root would be a `.claude-plugin/` tree and is not matched. `.claude/agents/` holds sub-agent definitions, not commands, and is out of scope.

WHAT "DISABLES" MEANS (`findings`). The frontmatter key `disable-model-invocation` in any spelling: any casing, and `-`, `_`, whitespace or nothing between the three words (`disable_model_invocation`, `Disable-Model-Invocation`, `disableModelInvocation`, `disable model invocation`), quoted or not, at any indentation, as a block-map key or the first key of a flow map. Only the FRONTMATTER is read: a file opens with a `---` line (a BOM
and leading blank lines tolerated) and the frontmatter runs to the next `---` or `...` line, or to the end of the file when none closes it (refusing more, never less). A YAML comment line is not a key. The body is prose: a sentence or a code block naming the key disables nothing.

AN EXPLICIT `false` IS REFUSED TOO, and so is any other value. Every finding carries a `verdict`: `truthy` (`true`, `yes`, `on`, `y`, `1`, any casing, quoted or not: the command IS user-only), `false` (`false`, `no`, `off`, `n`, `0`), or `unparsed` (empty, a block scalar, anything else). A `false` disables nothing today, and the hook and the gate still refuse it, for three reasons: the key has no remaining legitimate
purpose under the ruling (the default is already model-invocable); a present key is a one-word flip away from a user-only command, and that flip is exactly the edit the ruling forbids; and a rule of "present is refused" leaves no value parser for the guard and the gate to disagree about. An `unparsed` value is refused because an unknown is not a pass. So `findings(text)` being non-empty IS the verdict; `verdict` only shapes the message.

THE EXCEPTION LIST, from the operator's amendment of 2026-10-09, verbatim:

    it seems that we need an exceptionlist. I forgot about handoff command. let's include it into the exception list for CI & hook(s)

ONE tracked file, `.ci/config/model-invocation-exceptions.json` (`EXCEPTIONS_REL`), read ONLY through `load_exceptions` here, by both guards and the gate. Each entry names a file, the value its key keeps, and the operator ruling that admits it (date and verbatim quote). The list holds only operator rulings, never a BLOCKER entry. `verdict` is the one decision: an unlisted file may not declare the key at all; a LISTED file must declare it exactly once with exactly the listed value, so editing it is allowed while the flag stays as the list says, and dropping or changing the flag is refused (an AI that removed it would leave an entry the gate refuses as stale and that only the operator can delete). The guards refuse any edit to the list itself.

WHERE THE LIST IS FOUND (`exceptions_for`). Walking up from the judged file to the first directory holding `EXCEPTIONS_REL`, and listed paths are relative to that directory: `private/account/.claude/commands/x.md` finds the console's list and is keyed `private/account/.claude/commands/x.md`, and a scratch tree with its own list is judged by that list. No list found, or a list that fails `schema_errors`, means NO exceptions: the strict answer, never the permissive one.

NOT IN SCOPE: `user-invocable:` in `.claude/skills/*/SKILL.md`. That key decides whether a skill appears in the USER's slash menu; it does not stop the model invoking the skill, so it is a different question and this module never reads it.

STDLIB ONLY, because the guards import it inside the hook process and the gate imports it from `.ci` through the documented `.claude` hop.
"""

from __future__ import annotations

import dataclasses
import json
import pathlib
import re

RULING = (
    '"no command or skill in this repo is user-only. Every slash command and skill must be '
    'invocable by the AI." (operator ruling 2026-10-09)'
)
OPERATOR_LINE = "a user-only command is an operator decision: the operator edits it with !"

# A command or skill file: `.md` under a `.claude/commands/` or `.claude/skills/` directory, at any depth, under any parent.
SCOPE_RE = re.compile(r"(?:\A|/)\.claude/(?:commands|skills)/(?:.*/)?[^/]+\.md\Z", re.IGNORECASE)
# The DIRECTORY form, for a shell operand that names the directory itself (`cp x.md .claude/commands/`).
SCOPE_DIR_RE = re.compile(r"(?:\A|/)\.claude/(?:commands|skills)(?:/|\Z)", re.IGNORECASE)

# The three words in any casing, joined by `-`, `_`, blanks or nothing.
KEY_WORDS = r"disable[-_ \t]*model[-_ \t]*invocation"
# A frontmatter line that declares the key: indentation, an optional sequence dash or flow-map brace, an optional quote, the key, the same quote, then a colon.
_KEY_LINE = re.compile(
    r"\A[ \t]*(?:-[ \t]+)?\{?[ \t]*(?P<q>[\"']?)(?P<key>%s)(?P=q)[ \t]*:(?P<value>.*)\Z"
    % KEY_WORDS,
    re.IGNORECASE,
)
# The key as a WRITTEN key line, anywhere in a piece of text: what the shell half looks for in what a command WRITES. After the colon comes a value (a word character or a quote), or NOTHING: the end of the line or a `\n`/`\t` escape, because an empty value is a declared key too and the gate refuses it (found by the agreement test's first run, which caught the shell half allowing `disable-model-invocation:` that the gate fails). `/` straight after the colon is a sed address (`/^disable-model-invocation:/d`), which is a removal, so it is the one character that does not count. The key may follow a `\n` or `\t` ESCAPE (`printf '---\ndisable-...'`), whose letter would otherwise read as part of a longer word.
FLAG_IN_TEXT = re.compile(
    r"(?:(?<![A-Za-z0-9])|(?<=\\[nt]))[\"']?%s[\"']?[ \t]*:[ \t]*(?:[\"']?[A-Za-z0-9]|[\"']|\\[nt]|$)"
    % KEY_WORDS,
    re.IGNORECASE | re.MULTILINE,
)
# Cheap pre-filter: text that does not name the three words cannot carry the key.
MENTION = re.compile(KEY_WORDS, re.IGNORECASE)

TRUTHY = frozenset(("true", "yes", "on", "y", "1"))
FALSY = frozenset(("false", "no", "off", "n", "0"))


@dataclasses.dataclass(frozen=True)
class Finding:
    """One frontmatter line that declares the key."""

    line: int
    key: str
    value: str
    verdict: str  # "truthy" | "false" | "unparsed"

    def describe(self) -> str:
        why = {
            "truthy": "makes the command user-only",
            "false": "disables nothing today, but a present key is one word from a user-only command",
            "unparsed": "carries a value that cannot be read, and an unknown is not a pass",
        }[self.verdict]
        shown = self.value or "(empty)"
        return "line %d: `%s: %s` %s" % (self.line, self.key, shown, why)


def in_scope(path: str) -> bool:
    """True for a command or skill file this rule judges."""
    return SCOPE_RE.search(str(path).replace("\\", "/")) is not None


def names_scope_dir(path: str) -> bool:
    """True for a path inside (or naming) a command or skill directory, file or directory alike."""
    return SCOPE_DIR_RE.search(str(path).replace("\\", "/")) is not None


def _frontmatter(text: str) -> list[tuple[int, str]]:
    """(line number, line) for every frontmatter line, or [] when the file has none."""
    lines = text.lstrip("﻿").split("\n")
    i = 0
    while i < len(lines) and lines[i].strip() == "":
        i += 1
    if i >= len(lines) or lines[i].rstrip("\r").rstrip() != "---":
        return []
    out = []
    for j in range(i + 1, len(lines)):
        line = lines[j].rstrip("\r")
        if line.rstrip() in ("---", "..."):
            break
        out.append((j + 1, line))
    return out


def _classify(raw: str) -> tuple[str, str]:
    value = raw.strip()
    # A trailing YAML comment, and a flow map's closing brace or separator.
    value = re.sub(r"\s+#.*\Z", "", value).strip().rstrip("},").strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        value = value[1:-1].strip()
    low = value.lower()
    if low in TRUTHY:
        return value, "truthy"
    if low in FALSY:
        return value, "false"
    return value, "unparsed"


def findings(text: str) -> list[Finding]:
    """Every frontmatter line of `text` that declares the key. Non-empty means the file disables (or may disable) model invocation, and is refused."""
    if not MENTION.search(text or ""):
        return []
    out = []
    for number, line in _frontmatter(text):
        if line.lstrip().startswith("#"):
            continue
        m = _KEY_LINE.match(line)
        if m is None:
            continue
        value, verdict = _classify(m.group("value"))
        out.append(Finding(number, m.group("key"), value, verdict))
    return out


def flag_in_text(text: str) -> bool:
    """True when `text` carries the key followed by a value: what a shell write may not put into a command or skill file."""
    return bool(text) and FLAG_IN_TEXT.search(text) is not None


# --------------------------------------------------------------------------- the exception list ---------------------------------------------------------------------------

EXCEPTIONS_REL = ".ci/config/model-invocation-exceptions.json"
EXCEPTIONS_RE = re.compile(r"(?:\A|/)\.ci/config/model-invocation-exceptions\.json\Z")
_DATE = re.compile(r"\A\d{4}-\d{2}-\d{2}\Z")


@dataclasses.dataclass(frozen=True)
class ListEntry:
    """One operator-ruled exception: the file, the value its key keeps, and the ruling."""

    path: str
    value: str
    date: str
    quote: str


@dataclasses.dataclass
class ExceptionList:
    """The parsed list. `errors` non-empty means the list is not trusted and `entries` is empty."""

    source: pathlib.Path | None
    entries: dict[str, ListEntry]
    errors: list[str]


def is_exception_list(path: str) -> bool:
    """True for the exception list itself, wherever the tree is."""
    return EXCEPTIONS_RE.search(str(path).replace("\\", "/")) is not None


def schema_errors(doc: object) -> list[str]:
    """Every way `doc` (the parsed JSON) fails the list's schema. A BLOCKER entry is refused: the list holds operator rulings only."""
    if not isinstance(doc, dict) or not isinstance(doc.get("exceptions"), list):
        return ["the list must be an object with an `exceptions` array"]
    errors = []
    seen = set()
    for i, entry in enumerate(doc["exceptions"]):
        where = "exceptions[%d]" % i
        if not isinstance(entry, dict):
            errors.append("%s is not an object" % where)
            continue
        if "BLOCKER" in json.dumps(entry):
            errors.append(
                "%s carries a BLOCKER: this list holds operator rulings only, never a BLOCKER entry"
                % where
            )
        extra = sorted(set(entry) - {"path", "value", "ruling"})
        if extra:
            errors.append("%s has unknown key(s) %s" % (where, ", ".join(extra)))
        path = entry.get("path")
        if not isinstance(path, str) or not in_scope(path) or path.startswith("/"):
            errors.append(
                "%s: `path` must be a repo-relative command or skill file, got %r" % (where, path)
            )
        elif path in seen:
            errors.append("%s: %s is listed twice" % (where, path))
        else:
            seen.add(path)
        value = entry.get("value")
        if not isinstance(value, str) or value.lower() not in TRUTHY | FALSY:
            errors.append(
                "%s: `value` must be the key's value as a string (true, false, ...), got %r"
                % (where, value)
            )
        ruling = entry.get("ruling")
        if not isinstance(ruling, dict):
            errors.append(
                "%s has no `ruling`: an exception exists only by operator ruling (date and verbatim quote)"
                % where
            )
            continue
        if not isinstance(ruling.get("date"), str) or not _DATE.match(ruling["date"]):
            errors.append(
                "%s: `ruling.date` must be YYYY-MM-DD, got %r" % (where, ruling.get("date"))
            )
        quote = ruling.get("quote")
        if not isinstance(quote, str) or len(quote.strip()) < 20:
            errors.append(
                "%s: `ruling.quote` must be the operator's verbatim words (20+ characters)" % where
            )
    return errors


def parse_exceptions(text: str, source: pathlib.Path | None = None) -> ExceptionList:
    """The list from its JSON text; any schema error empties it (strict)."""
    try:
        doc = json.loads(text)
    except ValueError as exc:
        return ExceptionList(source, {}, ["the list is not valid JSON (%s)" % exc])
    errors = schema_errors(doc)
    if errors:
        return ExceptionList(source, {}, errors)
    entries = {
        e["path"]: ListEntry(e["path"], e["value"], e["ruling"]["date"], e["ruling"]["quote"])
        for e in doc["exceptions"]
    }
    return ExceptionList(source, entries, [])


def load_exceptions(root: pathlib.Path | str) -> ExceptionList:
    """THE ONE LOADER: the list under `root`, or an empty list (with an error) when it is absent or unreadable."""
    source = pathlib.Path(root) / EXCEPTIONS_REL
    try:
        text = source.read_text(encoding="utf-8")
    except OSError as exc:
        return ExceptionList(None, {}, ["%s cannot be read (%s)" % (EXCEPTIONS_REL, exc)])
    return parse_exceptions(text, source)


def exceptions_for(path: pathlib.Path | str) -> tuple[str, ExceptionList]:
    """(the path relative to the list's tree, the list) for a file, found by walking up from it. No list above it: (the path as given, an empty list)."""
    p = pathlib.Path(path)
    for parent in p.parents:
        if (parent / EXCEPTIONS_REL).is_file():
            return p.relative_to(parent).as_posix(), load_exceptions(parent)
    return p.as_posix(), ExceptionList(None, {}, [])


def verdict(rel: str, text: str, exceptions: ExceptionList) -> list[str]:
    """THE DECISION, shared by both guards and the gate: why the file at `rel` with content `text` is refused, or [] when it is allowed."""
    found = findings(text)
    entry = exceptions.entries.get(rel)
    if entry is None:
        return [f.describe() for f in found]
    if len(found) == 1 and found[0].value.lower() == entry.value.lower():
        return []
    want = "`disable-model-invocation: %s` (operator ruling %s)" % (entry.value, entry.date)
    if not found:
        return [
            "listed in %s as %s, but the file no longer carries the key; the flag stays as the list says, and only the operator changes either"
            % (EXCEPTIONS_REL, want)
        ]
    return [
        "listed in %s as %s, but the file carries: %s"
        % (EXCEPTIONS_REL, want, "; ".join(f.describe() for f in found))
    ]
