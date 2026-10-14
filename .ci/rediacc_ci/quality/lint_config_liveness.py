r"""Every ruff suppression in pyproject.toml carries a BLOCKER reason and still suppresses something.

Operator ruling 2026-10-08 banned inline suppression markers: a finding is fixed in code, and a pattern that is deliberate moves into the linter's own config. That moves the suppression from a line a reviewer reads beside the code into a table nobody rereads, so the table is held to the two rules every other escape hatch in this repository is held to (docs/agent-reference/suppressions.md): a reason that EXISTS, and a reason that is still TRUE of the tree.

WHAT IS READ. Two tables of the root pyproject.toml:

    [tool.ruff.lint.per-file-ignores]     one (glob, code) pair per listed code
    [tool.ruff.lint.pyflakes]             one name per `allowed-unused-imports` entry

THE BLOCKER HALF. `tomllib` drops comments, so the two tables are read line by line with the group rule the allowlist files use: a `# BLOCKER: <reason>` line covers the entries after it until the next BLOCKER line, a blank line or the end of the array, a plain comment preserves the group, and an entry with no group may carry its reason on its own line. The reason is one line, because it is read off the line that carries the word. `tomllib` then parses the same file and the two readings must agree key for key and code for code: a table written in a spelling the line reader does not know (an inline table, a dotted key under `[tool.ruff.lint]`, `extend-per-file-ignores`) is a disagreement or a named refusal, never an entry that escaped. Each reason goes through `rediacc_ci.core.allowlist.validate_reason`, the one implementation of the quality rules.

THE LIVENESS HALF, AND WHY ruff IS ITS ORACLE. ruff has no "unused per-file-ignore" report; RUF100 covers inline markers only. So the same file list is linted twice with `--ignore-noqa` and `--select <the codes the tables name>`:

    run A   both tables switched off on the command line   the UNIVERSE: what would be reported
    run B   the config as written                           what is still reported

A pair is live when run A holds at least one finding of its code in a file its glob matches, and a name is live when run A holds an F401 on it. Run B is the control on this module's own glob matcher, on the real tree and on every run: each run A finding must be absent from run B exactly when the tables as read here say it is suppressed. A finding the matcher claims and ruff still reports, or the reverse, means the matcher has drifted from ruff, and the verdict is CANNOT VERIFY.

`--ignore-noqa` IS LOAD-BEARING: a site still carrying an inline marker is a site the config entry suppresses too, and counting it keeps an entry's verdict the same before and after the marker strip that follows it.

WHAT A DIRECTORY-WIDE GLOB DOES NOT PROVE, stated rather than hidden. `.claude/hooks/**/*.py` is live while one site exists, so it admits a new deliberate site with no marker and no review of its own. A per-entry count ratchet was considered and rejected as a second baseline (agent/plans/PLAN-inline-suppressions.md, "Known trade-off"). The BLOCKER names the contract instead, and the site count of every entry is PRINTED on every run, so a number that jumps is visible in the log.

WHY THIS IS NOT INSIDE `python_lint.py`, where the plan placed it. That module is pinned byte for byte against its deleted bash twin's recorded output (`tests/goldens/python-lint/`) over a twelve-file specimen that carries the REAL pyproject.toml and none of `rediacc_ci/core/`. In that specimen every entry is dead and `allowlist` does not import, so a check living there would turn eight frozen recordings red for a reason unrelated to them. The entry point `.ci/scripts/quality/check_python_lint.py` runs the lint and then this module, so it is one gate, one step and one exit code, and it reuses that module's enumerator and resolver rather than carrying a second copy of either.

CANNOT VERIFY IS EXIT 1, NEVER A PASS: an empty universe, a ruff run that returned no parseable report, a disagreement between the two readers of the file, or between the matcher and ruff.
"""

import dataclasses
import json
import os
import pathlib
import re
import subprocess
import sys
import tomllib

from rediacc_ci import paths
from rediacc_ci.controls import Controls
from rediacc_ci.core import allowlist
from rediacc_ci.quality import python_lint

CONFIG = "pyproject.toml"
IGNORES_TABLE = "tool.ruff.lint.per-file-ignores"
PYFLAKES_TABLE = "tool.ruff.lint.pyflakes"
IMPORTS_KEY = "allowed-unused-imports"

# The keys ruff reads a per-file suppression from that the line reader does not parse. Present in the parsed document means an entry no BLOCKER rule can see.
UNREAD_KEYS = ("extend-per-file-ignores",)

IGNORE = "ignore"
IMPORT = "import"

_HEADER = re.compile(r"^\[([^\[\]]+)\]\s*$")
_KEY = re.compile(r'^\s*(?:"([^"\\]*)"|([A-Za-z0-9_-]+))\s*=\s*\[')
_STRING = re.compile(r'"([^"\\]*)"')
_BLOCKER = re.compile(r"^#\s*BLOCKER:\s*(.+)$")
_UNUSED = re.compile(r"^`([^`]+)` imported but unused")


@dataclasses.dataclass(frozen=True)
class Entry:
    """One suppression: a (glob, code) pair, or an allowed-unused-imports name with an empty glob."""

    kind: str
    glob: str
    code: str
    reason: str
    line: int

    def label(self) -> str:
        if self.kind == IMPORT:
            return "%s %s" % (IMPORTS_KEY, self.code)
        return '"%s" %s' % (self.glob, self.code)


@dataclasses.dataclass(frozen=True)
class Finding:
    """One ruff finding, keyed so the same site in two runs compares equal."""

    file: str
    code: str
    row: int
    column: int
    message: str


# --------------------------------------------------------------------------- reading the file ---------------------------------------------------------------------------


def split_comment(raw: str) -> tuple[str, str]:
    """(code, comment) for one line. A `#` inside a double-quoted string is not a comment."""
    quoted = False
    for index, char in enumerate(raw):
        if char == '"':
            quoted = not quoted
        elif char == "#" and not quoted:
            return raw[:index], raw[index:].strip()
    return raw, ""


def parse_config(text: str) -> tuple[list[Entry], list[str]]:
    """The two tables, line by line. Returns (entries in file order, lines that could not be read).

    An unreadable line is REPORTED, never skipped: inside the per-file table every line is a key, a code, a bracket or a comment, and one that is none of those is an entry this reader would otherwise have lost. In the pyflakes table only `allowed-unused-imports` is an array of suppressions, so its other keys are left to tomllib.
    """
    entries: list[Entry] = []
    errors: list[str] = []
    table = ""
    current = ""
    open_key: str | None = None
    for number, raw in enumerate(text.split("\n"), start=1):
        code, comment = split_comment(raw)
        header = _HEADER.match(code.strip())
        if header and open_key is None:
            table = header.group(1).strip()
            current = ""
            continue
        if table not in (IGNORES_TABLE, PYFLAKES_TABLE):
            continue
        if not raw.strip():
            # A blank line ends the group, the documented contract of every BLOCKER file.
            current = ""
            continue
        if not code.strip():
            match = _BLOCKER.match(comment)
            if match:
                current = match.group(1).strip()
            continue
        rest = code
        if open_key is None:
            key = _KEY.match(code)
            if key is None:
                if table == IGNORES_TABLE:
                    errors.append(
                        '%s:%d: not a `"<glob>" = [` line: %s' % (CONFIG, number, raw.strip())
                    )
                continue
            name = key.group(1) if key.group(1) is not None else key.group(2)
            if table == PYFLAKES_TABLE and name != IMPORTS_KEY:
                continue
            open_key = name
            rest = code[key.end() :]
        values = _STRING.findall(rest)
        leftover = _STRING.sub("", rest).replace(",", "").strip()
        if leftover not in ("", "]"):
            errors.append(
                "%s:%d: unread text %r inside the array of %s"
                % (CONFIG, number, leftover, open_key)
            )
        inline = _BLOCKER.match(comment)
        # The marker on the entry's own line is the nearest reason, so it is the one validated; the group reason above covers a line that carries none.
        reason = (inline.group(1).strip() if inline else "") or current
        for value in values:
            if table == IGNORES_TABLE:
                entries.append(Entry(IGNORE, open_key, value, reason, number))
            else:
                entries.append(Entry(IMPORT, "", value, reason, number))
        if leftover == "]":
            # The end of an array ends the group too, the rule suppressions.md already states for a JSONC array. Without it a key appended under a closed array would inherit that array's last reason in silence, which is the one way an entry could arrive here with no BLOCKER of its own and still pass.
            open_key = None
            current = ""
    if open_key is not None:
        errors.append("%s: the array of %s is never closed" % (CONFIG, open_key))
    return entries, errors


def cross_check(entries: list[Entry], document: dict) -> list[str]:
    """Where the line reader and tomllib disagree about what the two tables hold. Empty means agreement."""
    lint = document.get("tool", {}).get("ruff", {}).get("lint", {})
    problems = [
        "%s: `%s` is set. Its entries suppress findings exactly as per-file-ignores does and no "
        "BLOCKER rule reads them; move them into [%s]." % (CONFIG, key, IGNORES_TABLE)
        for key in UNREAD_KEYS
        if lint.get(key)
    ]
    read: dict[str, list[str]] = {}
    for entry in entries:
        if entry.kind == IGNORE:
            read.setdefault(entry.glob, []).append(entry.code)
    real = {glob: list(codes) for glob, codes in lint.get("per-file-ignores", {}).items()}
    problems += [
        '%s: per-file-ignores "%s" reads as %s line by line and as %s to tomllib'
        % (CONFIG, glob, read.get(glob), real.get(glob))
        for glob in sorted(set(read) | set(real))
        if read.get(glob) != real.get(glob)
    ]
    names = [entry.code for entry in entries if entry.kind == IMPORT]
    real_names = list(lint.get("pyflakes", {}).get(IMPORTS_KEY, []))
    if names != real_names:
        problems.append(
            "%s: %s reads as %s line by line and as %s to tomllib"
            % (CONFIG, IMPORTS_KEY, names, real_names)
        )
    return problems


def reason_failures(entries: list[Entry]) -> list[str]:
    """A missing or low-quality BLOCKER, one message per entry, in file order."""
    failures: list[str] = []
    for entry in entries:
        where = "%s:%d" % (CONFIG, entry.line)
        if not entry.reason:
            failures.append(allowlist.missing_reason(entry.label(), where))
            continue
        rejection = allowlist.validate_reason(entry.label(), entry.reason, where)
        if rejection is not None:
            failures.append(rejection.message)
    return failures


# --------------------------------------------------------------------------- the matcher ---------------------------------------------------------------------------


def glob_regex(pattern: str) -> re.Pattern[str]:
    """ruff's glob dialect as a regex: globset with its defaults, where `*` and `?` cross a `/`.

    Raises ValueError on a shape this translation does not cover (a leading `!` negation, a nested or unclosed brace), so an unreadable pattern is a refusal and not a guess.
    """
    if pattern.startswith("!"):
        raise ValueError("a negated pattern is not supported: %s" % pattern)
    out: list[str] = []
    index = 0
    depth = 0
    while index < len(pattern):
        char = pattern[index]
        if pattern.startswith("**/", index):
            out.append("(?:.*/)?")
            index += 3
            continue
        if char == "*":
            out.append(".*")
            index += 2 if pattern.startswith("**", index) else 1
            continue
        if char == "?":
            out.append(".")
        elif char == "{":
            if depth:
                raise ValueError("a nested brace is not supported: %s" % pattern)
            depth = 1
            out.append("(?:")
        elif char == "}" and depth:
            depth = 0
            out.append(")")
        elif char == "," and depth:
            out.append("|")
        elif char == "[":
            close = pattern.find("]", index + 2)
            if close < 0:
                raise ValueError("an unclosed character class: %s" % pattern)
            body = pattern[index + 1 : close]
            negated = body.startswith(("!", "^"))
            out.append(
                "[%s%s]" % ("^" if negated else "", re.escape(body[negated:]).replace(r"\-", "-"))
            )
            index = close
        else:
            out.append(re.escape(char))
        index += 1
    if depth:
        raise ValueError("an unclosed brace: %s" % pattern)
    return re.compile("".join(out))


def matches(pattern: str, rel: str) -> bool:
    """ruff's two tries for one pattern: the path under the project root, then the bare file name."""
    regex = glob_regex(pattern)
    return bool(regex.fullmatch(rel) or regex.fullmatch(rel.rsplit("/", 1)[-1]))


def unused_name(finding: Finding) -> str | None:
    """The module an F401 finding names, or None for any other finding."""
    if finding.code != "F401":
        return None
    match = _UNUSED.match(finding.message)
    return match.group(1) if match else None


def covers(entry: Entry, finding: Finding, matcher=matches) -> bool:
    """Does this entry suppress this finding, as read here."""
    if entry.kind == IMPORT:
        name = unused_name(finding)
        return name is not None and (name == entry.code or name.startswith(entry.code + "."))
    return finding.code.startswith(entry.code) and matcher(entry.glob, finding.file)


# --------------------------------------------------------------------------- the verdict ---------------------------------------------------------------------------


@dataclasses.dataclass
class Verdict:
    """What one judged tree says. `cannot` non-empty means no verdict at all."""

    cannot: list[str]
    dead: list[str]
    sites: dict[Entry, int]
    universe: int
    suppressed: int


def judge(entries: list[Entry], universe: list[Finding], remaining: list[Finding]) -> Verdict:
    """Liveness of each entry over run A, with run B as the control on the matcher."""
    cache: dict[tuple[str, str], bool] = {}

    def cached(pattern: str, rel: str) -> bool:
        key = (pattern, rel)
        if key not in cache:
            cache[key] = matches(pattern, rel)
        return cache[key]

    verdict = Verdict([], [], dict.fromkeys(entries, 0), len(universe), 0)
    if entries and not universe:
        verdict.cannot.append(
            "run A reported ZERO findings for the codes the tables name, so no entry can be shown "
            "to suppress anything. The file list did not come from the real tree, or ruff did not "
            "read it."
        )
        return verdict
    still = set(remaining)
    disagreements: list[str] = []
    for finding in universe:
        claimed = False
        for entry in entries:
            if covers(entry, finding, cached):
                verdict.sites[entry] += 1
                claimed = True
        if claimed:
            verdict.suppressed += 1
        if claimed == (finding in still):
            disagreements.append(
                "%s:%d %s is %s by the tables as read here and %s by ruff"
                % (
                    finding.file,
                    finding.row,
                    finding.code,
                    "suppressed" if claimed else "not suppressed",
                    "still reported" if finding in still else "not reported",
                )
            )
    if disagreements:
        verdict.cannot.append(
            "the glob matcher and ruff disagree on %d finding(s), so liveness cannot be read off "
            "this matcher:\n      %s" % (len(disagreements), "\n      ".join(disagreements[:10]))
        )
        return verdict
    for entry in entries:
        if verdict.sites[entry]:
            continue
        if entry.kind == IMPORT:
            verdict.dead.append(
                "%s:%d: %s suppresses nothing: no `import %s` is left that ruff would report as "
                "unused. Delete the name." % (CONFIG, entry.line, entry.label(), entry.code)
            )
        else:
            verdict.dead.append(
                "%s:%d: %s suppresses nothing: ruff reports no %s finding in any file the glob "
                "matches. Delete the code, and its BLOCKER line when that covers nothing else."
                % (CONFIG, entry.line, entry.label(), entry.code)
            )
    return verdict


# --------------------------------------------------------------------------- the two ruff runs ---------------------------------------------------------------------------


def lint(
    ruff: list[str], root: str, files: list[str], codes: list[str], *, tables_off: bool
) -> list[Finding] | str:
    """One `--ignore-noqa` run over `files`. Returns the findings, or a sentence saying why there is no report."""
    argv = [*ruff, "check", "--no-cache", "--ignore-noqa", "--output-format", "json"]
    if tables_off:
        argv += ["--config", "lint.per-file-ignores = {}"]
        argv += ["--config", "lint.pyflakes.allowed-unused-imports = []"]
    argv += ["--select", ",".join(codes), "--", *files]
    proc = subprocess.run(
        argv, capture_output=True, text=True, check=False, cwd=root, stdin=subprocess.DEVNULL
    )
    if proc.returncode not in (0, 1):
        return "ruff exited %d: %s" % (proc.returncode, proc.stderr.strip()[:400])
    try:
        rows = json.loads(proc.stdout)
    except ValueError:
        return "ruff printed no parseable JSON report (%d byte(s))" % len(proc.stdout)
    real_root = os.path.realpath(root)
    out: list[Finding] = []
    for row in rows:
        rel = os.path.relpath(os.path.realpath(row["filename"]), real_root).replace(os.sep, "/")
        location = row.get("location") or {}
        out.append(
            Finding(
                rel,
                row.get("code") or "",
                location.get("row", 0),
                location.get("column", 0),
                row.get("message") or "",
            )
        )
    return out


def run(root: pathlib.Path) -> int:
    """Judge one tree. 0 every entry reasoned and live, 1 a finding or CANNOT VERIFY, 77 ruff is absent."""
    config = root / CONFIG
    if not config.is_file():
        print(
            "✗ lint-config liveness: %s is missing, so there is no table to read." % config,
            file=sys.stderr,
        )
        return 1
    text = config.read_text(encoding="utf-8")
    entries, errors = parse_config(text)
    errors += cross_check(entries, tomllib.loads(text))
    if errors:
        print(
            "✗ lint-config liveness: CANNOT VERIFY, the suppression tables were not read whole:",
            file=sys.stderr,
        )
        for line in errors:
            print("    %s" % line, file=sys.stderr)
        return 1

    failures = reason_failures(entries)
    pairs = [entry for entry in entries if entry.kind == IGNORE]
    names = [entry for entry in entries if entry.kind == IMPORT]
    if not entries:
        print(
            "✓ lint-config liveness: %s holds no per-file ignore and no allowed-unused-imports name; nothing to prove"
            % CONFIG
        )
        return 0

    ruff = python_lint.resolve_ruff()
    if ruff is None:
        print(
            "✗ lint-config liveness: ruff is not available and neither is uvx, so no entry was "
            "checked. Install it as check:ci-python-lint advises, or set RUFF_BIN.",
            file=sys.stderr,
        )
        return python_lint.EXIT_CANNOT_RUN
    files = python_lint.enumerate_py(str(root))
    codes = sorted({entry.code for entry in pairs} | ({"F401"} if names else set()))
    if not files:
        print(
            "✗ lint-config liveness: CANNOT VERIFY, the Python file list is empty.", file=sys.stderr
        )
        return 1
    universe = lint(ruff, str(root), files, codes, tables_off=True)
    remaining = lint(ruff, str(root), files, codes, tables_off=False)
    if isinstance(universe, str) or isinstance(remaining, str):
        for label, result in (
            ("run A (tables off)", universe),
            ("run B (config as written)", remaining),
        ):
            if isinstance(result, str):
                print(
                    "✗ lint-config liveness: CANNOT VERIFY, %s gave no report: %s"
                    % (label, result),
                    file=sys.stderr,
                )
        return 1
    try:
        verdict = judge(entries, universe, remaining)
    except ValueError as exc:
        print(
            "✗ lint-config liveness: CANNOT VERIFY, a glob in %s could not be read: %s"
            % (CONFIG, exc),
            file=sys.stderr,
        )
        return 1
    if verdict.cannot:
        for line in verdict.cannot:
            print("✗ lint-config liveness: CANNOT VERIFY, %s" % line, file=sys.stderr)
        return 1

    shape = "%d (glob, code) pair(s) under %d glob(s) and %d %s name(s)" % (
        len(pairs),
        len({entry.glob for entry in pairs}),
        len(names),
        IMPORTS_KEY,
    )
    if failures or verdict.dead:
        if failures:
            print(
                "✗ lint-config liveness: %d entr(ies) of %s lack a usable BLOCKER reason:"
                % (len(failures), CONFIG),
                file=sys.stderr,
            )
            for line in failures:
                print("    %s" % line, file=sys.stderr)
            print(
                "  Put `# BLOCKER: <why the rule is wrong for these files>` on the line above the "
                "code, in one line. A blank line ends the group a BLOCKER covers.",
                file=sys.stderr,
            )
        if verdict.dead:
            print(
                "✗ lint-config liveness: %d entr(ies) of %s suppress nothing:"
                % (len(verdict.dead), CONFIG),
                file=sys.stderr,
            )
            for line in verdict.dead:
                print("    %s" % line, file=sys.stderr)
        print("  read: %s; %d file(s) linted" % (shape, len(files)), file=sys.stderr)
        return 1

    print(
        "✓ lint-config liveness: %s in %s, each with a BLOCKER reason and each live"
        % (shape, CONFIG)
    )
    print(
        "  universe: %d finding(s) of %d code(s) in %d file(s) with both tables off; %d suppressed "
        "by the tables, and ruff agrees on every one"
        % (verdict.universe, len(codes), len(files), verdict.suppressed)
    )
    print(
        "  sites per entry (a directory-wide glob admits new ones; a number that jumps is the signal):"
    )
    for entry in entries:
        print("    %6d  %s" % (verdict.sites[entry], entry.label()))
    return 0


def main(argv: list[str] | None = None) -> int:
    """The gate half the entry point chains after the lint. The controls run first, quietly."""
    args = list(argv or [])
    if args and args[0] == "--selftest":
        return selftest()
    if selftest(quiet=True) != 0:
        print(
            "✗ lint-config liveness: an instrument control failed; every verdict below it would be meaningless",
            file=sys.stderr,
        )
        return 1
    return run(paths.repo_root())


def chained(argv: list[str] | None = None) -> int:
    """`check:ci-python-lint`: the lint and format gate, then this one. The first non-zero status wins.

    The lint goes first because its refusals (an empty file list, a linter that is not linting, a missing ruff as 77) are also this check's preconditions, and each is already said there in full.
    """
    status = python_lint.main(argv)
    if status != 0:
        return status
    return main(argv)


# --------------------------------------------------------------------------- the selftest ---------------------------------------------------------------------------

_GOOD = "a reason long enough to pass the thirty character floor of the validator"

_SAMPLE = """[tool.ruff.lint]
select = ["ALL"]

[tool.ruff.lint.per-file-ignores]
"**/tests/**/test_*.py" = [
    # BLOCKER: %(good)s
    # a plain comment keeps the group open
    "S101",
    "S311",

    "S105",
    # BLOCKER: second %(good)s
    "S106",
]
"a/{b,c}/*.py" = ["BLE001"]  # BLOCKER: inline %(good)s
"conftest.py" = ["BLE001"]

[tool.ruff.lint.pyflakes]
extend-generics = ["x.Y"]
allowed-unused-imports = [
    # BLOCKER: names %(good)s
    "_cipath",
]

[tool.ruff.format]
"not/an/entry.py" = ["E501"]
""" % {"good": _GOOD}


def _finding(file: str, code: str, row: int = 1, message: str = "") -> Finding:
    return Finding(file, code, row, 1, message)


def selftest(*, quiet: bool = False) -> int:
    """Both directions on the reader, the matcher and the verdict. No ruff and no tree: the planted-tree controls that drive the real linter live in `tests/test_quality_lint_config_liveness.py`."""
    ctl = Controls("lint-config-liveness", floor=40)

    entries, errors = parse_config(_SAMPLE)
    by = {(e.glob, e.code): e for e in entries}
    ctl.check("reader: the sample parses with no unread line", errors, [])
    ctl.check("reader: seven entries, the [tool.ruff.format] line is not one", len(entries), 7)
    ctl.check(
        "reader: a BLOCKER covers the code after it",
        by["**/tests/**/test_*.py", "S101"].reason,
        _GOOD,
    )
    ctl.check(
        "reader: and the next code, through a plain comment",
        by["**/tests/**/test_*.py", "S311"].reason,
        _GOOD,
    )
    ctl.check("reader: a blank line ends the group", by["**/tests/**/test_*.py", "S105"].reason, "")
    ctl.check(
        "reader: a new BLOCKER replaces the old one",
        by["**/tests/**/test_*.py", "S106"].reason,
        "second " + _GOOD,
    )
    ctl.check(
        "reader: an inline BLOCKER covers a one-line array",
        by["a/{b,c}/*.py", "BLE001"].reason,
        "inline " + _GOOD,
    )
    ctl.check(
        "reader: the end of an array ends the group, so the next key inherits nothing",
        by["conftest.py", "BLE001"].reason,
        "",
    )
    ctl.check("reader: an allowed-unused-imports name is an entry", by["", "_cipath"].kind, IMPORT)
    ctl.check("reader: with its own reason", by["", "_cipath"].reason, "names " + _GOOD)
    ctl.check(
        "reader: the line number is the code's own line",
        by["**/tests/**/test_*.py", "S105"].line,
        11,
    )
    _entries, bad = parse_config('[%s]\n"a.py" = [\n  S101,\n]\n' % IGNORES_TABLE)
    ctl.truthy("reader: an unquoted code is reported, not skipped", bad)
    _entries, bad = parse_config('[%s]\nper = "x"\n' % IGNORES_TABLE)
    ctl.truthy("reader: a line that is no array is reported", bad)
    _entries, bad = parse_config('[%s]\n"a.py" = [\n  "S101",\n' % IGNORES_TABLE)
    ctl.truthy("reader: an array that never closes is reported", bad)

    document = tomllib.loads(_SAMPLE)
    ctl.check(
        "cross-check: the two readers agree on the sample", cross_check(entries, document), []
    )
    ctl.truthy(
        "cross-check: an entry tomllib sees and the reader lost is named",
        cross_check(entries[1:], document),
    )
    ctl.truthy("cross-check: a name the reader lost is named", cross_check(entries[:-1], document))
    inline = tomllib.loads('[tool.ruff.lint]\nper-file-ignores = {"a.py" = ["S101"]}\n')
    ctl.truthy(
        "cross-check: an inline-table spelling the reader cannot see is a disagreement",
        cross_check([], inline),
    )
    extend = tomllib.loads('[tool.ruff.lint.extend-per-file-ignores]\n"a.py" = ["S101"]\n')
    ctl.truthy("cross-check: extend-per-file-ignores is refused by name", cross_check([], extend))

    reasons = reason_failures(entries)
    ctl.check(
        "reasons: the two entries with no BLOCKER fail and the five with one pass", len(reasons), 2
    )
    ctl.truthy(
        "reasons: and the first is named", reasons and '"**/tests/**/test_*.py" S105' in reasons[0]
    )
    ctl.check(
        "reasons: a short reason is refused",
        len(reason_failures([Entry(IGNORE, "a.py", "S101", "because", 1)])),
        1,
    )
    ctl.check(
        "reasons: a low-effort reason is refused",
        len(reason_failures([Entry(IGNORE, "a.py", "S101", "todo", 1)])),
        1,
    )

    tests_glob = "**/tests/**/test_*.py"
    ctl.check(
        "matcher: `**/` spans zero directories",
        matches(tests_glob, ".ci/rediacc_ci/tests/test_a.py"),
        True,
    )
    ctl.check(
        "matcher: and several", matches(tests_glob, ".ci/rediacc_ci/tests/gates/test_a.py"), True
    )
    ctl.check(
        "matcher: a helper in a test tree is not a test file",
        matches(tests_glob, ".ci/rediacc_ci/tests/differential.py"),
        False,
    )
    ctl.check(
        "matcher: a test-named file outside a tests directory is not matched",
        matches(tests_glob, ".claude/hooks/stop/test_a.py"),
        False,
    )
    ctl.check(
        "matcher: a brace alternative",
        matches("**/hooks/{stop,context}/test-*.py", ".claude/hooks/context/test-x.py"),
        True,
    )
    ctl.check(
        "matcher: only the listed alternatives",
        matches("**/hooks/{stop,context}/test-*.py", ".claude/hooks/post-bash/test-x.py"),
        False,
    )
    ctl.check(
        "matcher: a rooted pattern is anchored at the root",
        matches(
            ".claude/rediacc_hooks/guards/block_*.py",
            ".claude/rediacc_hooks/guards/test-block_x.py",
        ),
        False,
    )
    ctl.check(
        "matcher: a bare name matches that file name in any directory, as ruff does",
        matches("conftest.py", ".ci/rediacc_ci/tests/gates/conftest.py"),
        True,
    )
    ctl.check(
        "matcher: `*` crosses a directory separator, globset's default",
        matches(".claude/hooks/*.py", ".claude/hooks/stop/wl_core.py"),
        True,
    )
    ctl.check("matcher: a dot is literal", matches("a.py", "abpy"), False)
    ctl.raises("matcher: a negated pattern is refused", ValueError, glob_regex, "!a.py")
    ctl.raises("matcher: an unclosed brace is refused", ValueError, glob_regex, "a/{b,c.py")

    live = Entry(IGNORE, "a/**/*.py", "BLE001", _GOOD, 3)
    dead = Entry(IGNORE, "gone/*.py", "BLE001", _GOOD, 5)
    name = Entry(IMPORT, "", "_cipath", _GOOD, 9)
    gone = Entry(IMPORT, "", "_nopath", _GOOD, 10)
    hit = _finding("a/b/c.py", "BLE001")
    miss = _finding("z/c.py", "BLE001")
    unused = _finding("s/e.py", "F401", message="`_cipath` imported but unused")
    other = _finding("s/e.py", "F401", row=2, message="`json` imported but unused")
    universe = [hit, miss, unused, other]
    clean = judge([live, name], universe, [miss, other])
    ctl.check(
        "verdict: live entries on an agreeing tree give no finding",
        (clean.cannot, clean.dead),
        ([], []),
    )
    ctl.check(
        "verdict: the site count is per entry", (clean.sites[live], clean.sites[name]), (1, 1)
    )
    ctl.check("verdict: and the suppressed total is counted", clean.suppressed, 2)
    stale = judge([live, dead, name, gone], universe, [miss, other])
    ctl.check(
        "verdict: a pair with no site and a name with no import are both dead", len(stale.dead), 2
    )
    ctl.truthy(
        "verdict: the dead pair is named with its line",
        stale.dead and "pyproject.toml:5:" in stale.dead[0],
    )
    drift = judge([live, name], universe, [hit, miss, other])
    ctl.truthy(
        "verdict: a finding claimed here and still reported by ruff is CANNOT VERIFY", drift.cannot
    )
    drift = judge([live, name], universe, [other])
    ctl.truthy(
        "verdict: a finding ruff dropped that no entry claims is CANNOT VERIFY", drift.cannot
    )
    empty = judge([live], [], [])
    ctl.truthy("verdict: an empty universe is CANNOT VERIFY, never a pass", empty.cannot)
    ctl.check(
        "verdict: a dotted allowed name covers its submodule",
        covers(
            Entry(IMPORT, "", "a.b", _GOOD, 1),
            _finding("x.py", "F401", message="`a.b.c` imported but unused"),
        ),
        True,
    )
    ctl.check(
        "verdict: and not a sibling that only shares the prefix text",
        covers(
            Entry(IMPORT, "", "a.b", _GOOD, 1),
            _finding("x.py", "F401", message="`a.bc` imported but unused"),
        ),
        False,
    )

    if quiet:
        # The gate's own pre-flight: failures are already on stderr, and the pass line belongs to `--selftest`.
        return 0 if ctl.ok else 1
    return 0 if ctl.report() else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
