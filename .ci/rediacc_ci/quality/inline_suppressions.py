"""Inline lint and type suppression markers: the ONE scanner, the gate, and its shrink-only baseline.

WHY THIS EXISTS. Operator ruling 2026-10-08: "statements like '# noq[a]: B010' should be banned: a) with hooks to avoid future edits/inserts b) with CI, fix the existing ones." An inline suppression is a lint finding the author decided not to fix, recorded where no gate reads the reason. This module is the enforcement half. The existing debt (about 2,000 Python markers, ~200 TS/Go/shell
markers in console, 161 in private/renet and 6 in private/account on the day it landed) is frozen in `.ci/config/inline-suppressions-baseline.json` and may only SHRINK; the cleanup is a separate plan.

ONE SCANNER, TWO CLIENTS. `.ci/scripts/quality/check_inline_suppressions.py` (the CI gate) and `.claude/rediacc_hooks/guards/block_suppressions.py` plus `block_suppressions_shell_write.py` (the pre-edit and pre-bash hooks) all call `count_markers` below. A hook with its own private regex drifts from the gate, and the drift always runs the same way: the hook grows lenient, the gate stays strict, and the
difference shows up as a CI failure nobody could reproduce at the keystroke.

WHAT COUNTS AS A MARKER, by language. The test is POSITION, not mention:

  python   a COMMENT token, as `tokenize` reads the file, carrying `# noq[a]` (optionally `: CODES`, or `# ruff: noq[a]` for the file-wide form), `# type: ignor[e]` (optionally `[codes]`), `# pyright: ignor[e]`, `# pylint: disabl[e]=...` or `# mypy: ignore-errors`/`disable-error-code`. A STRING that mentions one is not a marker, which is the TRAPS.md "detector matches its own prose" case: a docstring explaining the ban
           is how the ban gets taught, and `tokenize` is what tells the two apart without a keyword list. A file `tokenize` cannot read falls back to scanning every line, which over-counts, the safe direction.
  js/ts    a directive IMMEDIATELY after a comment opener (`//`, `/*`, a JSX `{/*`, a continued `*`): `@ts-ignor[e]`, `@ts-expect-erro[r]`, `@ts-nochec[k]`, `eslint-disabl[e]` (and its -line / -next-line forms), `biome-ignor[e]` (and -all / -start). Prose puts words between the opener and the token, so `// Never write @ts-ignor[e]` is not a marker; this is the narrowing `block_suppressions.py` measured on 2026-08-27. There is no JS tokenizer here,
           so a string literal that happens to hold `'// @ts-ignor[e]'` IS counted, and the guard tells such an author to assemble the token from halves.
  go       `//nolin[t]` (golangci-lint's own spelling, no space) and `//lint:ignor[e]` (staticcheck).
  shell    `# shellcheck disabl[e]=SC...` (also after other `key=value` directives on the same comment).
  docker   `# hadolint ignor[e]=DL...`.

WIDER THAN THE ORIGINAL ASK, said out loud: shellcheck and hadolint directives were not in the brief's list. They are the same thing in the same position (a linter told to look away on one line), 33 and 2 of them existed on the day this landed, and a ban that covered Python and TypeScript but left shell open would be a ban on two spellings, not on the practice.

WHAT IS DELIBERATELY NOT A MARKER: `# pragma: no cove[r]` (a coverage exclusion, not a lint finding being silenced), `# fmt: off`/`skip` (a formatter instruction), `eslint-enable` and `biome-ignore-end` (they CLOSE a suppression rather than open one), and anything in Markdown or JSON (an example is how a rule is taught).

THE BASELINE IS KEYED ON (file, kind, code) WITH A COUNT, never a line number: a line number churns when anything above it moves, and a baseline that churns gets regenerated wholesale, which silently re-absorbs fresh findings. A count per key survives a move and cannot hide an addition, because the addition raises the count. The write path is `shrink_only.write_verdict` over an expansion of those counts into ids, so "the set only
loses members" is the same shared decision every Python shrink-only gate here makes.
"""

from __future__ import annotations

import collections
import io
import json
import os
import re
import subprocess
import sys
import tokenize
from typing import TYPE_CHECKING

from rediacc_ci import paths
from rediacc_ci.core import common
from rediacc_ci.quality import shrink_only

if TYPE_CHECKING:
    import pathlib
    from collections.abc import Iterable, Iterator

Counts = collections.Counter[tuple[str, str]]

BASELINE_REL = ".ci/config/inline-suppressions-baseline.json"

# The repositories scanned, as (label, path relative to the root, the marker whose presence proves a checkout). The two submodules are the ones carrying code a linter reads; private/elite (4 shell files, 0 markers) and private/homebrew-tap (a formula) are other repositories' business and are printed as out of scope on every run rather than silently skipped.
SCOPE = (
    ("console", "", None),
    ("private/renet", "private/renet", "private/renet/.git"),
    ("private/account", "private/account", "private/account/.git"),
)
OUT_OF_SCOPE = ("private/elite", "private/homebrew-tap")

# ANTI-VACUITY FLOOR. On 2026-10-08 console alone held 1,425 .py and 1,411 JS/TS files; a scan reporting far fewer has lost its file list (a moved root, an empty `git ls-files`) and its silence would read exactly like a clean tree.
MIN_CONSOLE_FILES = 1500

BLANKET = "*"

# --------------------------------------------------------------------------- language ---------------------------------------------------------------------------

_JS_SUFFIXES = frozenset(
    (".ts", ".tsx", ".js", ".jsx", ".cjs", ".mjs", ".mts", ".cts", ".vue", ".svelte", ".astro")
)
# `#!/bin/bash`, `#!/usr/bin/env python3`, `#!/usr/bin/env -S node --flag`: the interpreter is the BASENAME of the first word that is not `env` or an env flag.
_SHEBANG = re.compile(r"^#!\s*(?:\S*/env\s+(?:-\S+\s+)*)?(?:\S*/)?([A-Za-z0-9_.+-]+)")


def language_for(path: str, head: str = "") -> str | None:
    """`py`, `js`, `go`, `sh`, `docker`, or None when the file is not code this scanner reads.

    `head` is the file's first line, consulted only for a file with no suffix: an extensionless script is code if its shebang says so, which is how a good part of `.ci/scripts` and `.claude/hooks` is written.
    """
    name = path.replace("\\", "/").rsplit("/", 1)[-1]
    suffix = os.path.splitext(name)[1].lower()
    if suffix in (".py", ".pyi"):
        return "py"
    if suffix in _JS_SUFFIXES:
        return "js"
    if suffix == ".go":
        return "go"
    if suffix in (".sh", ".bash"):
        return "sh"
    if name.startswith(("Dockerfile", "Containerfile")) or suffix == ".dockerfile":
        return "docker"
    if suffix:
        return None
    match = _SHEBANG.match(head)
    if not match:
        return None
    interpreter = match.group(1)
    if interpreter.startswith("python"):
        return "py"
    if interpreter in ("sh", "bash", "dash", "zsh", "ksh"):
        return "sh"
    if interpreter in ("node", "tsx", "deno", "bun"):
        return "js"
    return None


# --------------------------------------------------------------------------- markers ---------------------------------------------------------------------------
#
# Every token below is spelled with a one-character class (`noq[a]`) so that THIS file's comments and docstrings never hold the literal marker. The patterns match the real tokens all the same; it is the convention `block_suppressions.py` has used since 2026-08-27, for the reason its header gives: drafting a comment without it got the repair refused by the guard being repaired.

_PY_CODES = r"[A-Za-z]+[0-9]+(?:\s*,\s*[A-Za-z]+[0-9]+)*"
_PY_PATTERNS = (
    (
        re.compile(
            r"#\s*(?P<file>(?:ruff|flake8)\s*:\s*)?noq[a]\b(?:\s*:\s*(?P<codes>%s))?" % _PY_CODES,
            re.IGNORECASE,
        ),
        "noqa",
    ),
    (re.compile(r"#\s*type\s*:\s*ignor[e]\b(?:\[(?P<codes>[^\]]*)\])?"), "type-ignore"),
    (re.compile(r"#\s*pyright\s*:\s*ignor[e]\b(?:\[(?P<codes>[^\]]*)\])?"), "pyright-ignore"),
    (
        re.compile(
            r"#\s*pylint\s*:\s*disabl[e](?:-next)?\s*=\s*(?P<codes>[\w-]+(?:\s*,\s*[\w-]+)*)"
        ),
        "pylint-disable",
    ),
    (
        re.compile(r"#\s*mypy\s*:\s*(?P<codes>ignore-error[s]|disable-error-code\s*=\s*\S+)"),
        "mypy",
    ),
)

# A comment opener, then nothing but whitespace, then the directive. Openers: `//`, `/*` (which also covers a JSX `{/*`), or a continued block-comment line that starts with `*`.
_JS_OPENER = r"(?://+|/\*+|^[ \t]*\*+)[ \t]*"
_JS_PATTERNS = (
    (re.compile(_JS_OPENER + r"@ts-ignor[e]\b", re.MULTILINE), "ts-ignore"),
    (re.compile(_JS_OPENER + r"@ts-expect-erro[r]\b", re.MULTILINE), "ts-expect-error"),
    (re.compile(_JS_OPENER + r"@ts-nochec[k]\b", re.MULTILINE), "ts-nocheck"),
    (
        re.compile(
            _JS_OPENER + r"eslint-disabl[e](?:-next-line|-line)?(?![\w-])(?P<rest>[^\n]*)",
            re.MULTILINE,
        ),
        "eslint-disable",
    ),
    (
        re.compile(
            _JS_OPENER + r"biome-ignor[e](?:-all|-start)?(?![\w-])[ \t]*(?P<codes>[^\s:*]*)",
            re.MULTILINE,
        ),
        "biome-ignore",
    ),
)
_GO_PATTERNS = (
    (re.compile(r"//nolin[t]\b(?::(?P<codes>[\w,-]+))?"), "nolint"),
    (re.compile(r"//lint:ignor[e][ \t]+(?P<codes>\S+)"), "lint-ignore"),
)
# `#` opens a shell comment only at the start of a word, so `x#y` and `"#..."` are not comments.
_SH_PATTERNS = (
    (
        re.compile(
            r"(?:^|[ \t])#[ \t]*shellcheck[ \t]+(?:[\w-]+=\S+[ \t]+)*disabl[e]=(?P<codes>[\w,-]+)",
            re.MULTILINE,
        ),
        "shellcheck-disable",
    ),
)
_DOCKER_PATTERNS = (
    (
        re.compile(r"(?:^|[ \t])#[ \t]*hadolint[ \t]+ignor[e]=(?P<codes>[\w,-]+)", re.MULTILINE),
        "hadolint-ignore",
    ),
)

LANGUAGES = ("py", "js", "go", "sh", "docker")


def _codes(raw: str | None, *, split_on: str = ",") -> list[str]:
    if raw is None:
        return [BLANKET]
    found = [c.strip() for c in raw.split(split_on) if c.strip()]
    return found or [BLANKET]


def _eslint_codes(rest: str) -> list[str]:
    """The rule list after an eslint directive: up to a `--` description or a `*/` close, comma separated."""
    body = rest.split("--", 1)[0].split("*/", 1)[0]
    return _codes(body)


def _add_matches(
    counts: Counts, text: str, patterns: Iterable[tuple[re.Pattern[str], str]]
) -> None:
    for pattern, kind in patterns:
        for match in pattern.finditer(text):
            groups = match.groupdict()
            label = kind
            if kind == "noqa" and groups.get("file"):
                label = "noqa-file"
            if kind == "eslint-disable":
                codes = _eslint_codes(groups.get("rest") or "")
            else:
                codes = _codes(groups.get("codes") or None)
            for code in codes:
                counts[(label, code)] += 1


def _python_comments(text: str) -> Iterator[str] | None:
    """Every COMMENT token in `text`, or None when `tokenize` cannot read it."""
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(text).readline))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return None
    return (tok.string for tok in tokens if tok.type == tokenize.COMMENT)


def count_markers(text: str, language: str, *, raw: bool = False) -> Counts:
    """Counter of (kind, code) -> occurrences in `text`, read as `language`.

    `raw=True` skips Python tokenization and reads every line, which is what a caller wants when `text` is not a Python FILE at all -- a fragment, or a program whose STRING literals are the content it is about to write (the pre-bash guard).
    """
    counts: Counts = collections.Counter()
    if language == "py":
        comments = None if raw else _python_comments(text)
        if comments is None:
            for line in text.splitlines():
                _add_matches(counts, line, _PY_PATTERNS)
        else:
            for comment in comments:
                _add_matches(counts, comment, _PY_PATTERNS)
    elif language == "js":
        _add_matches(counts, text, _JS_PATTERNS)
    elif language == "go":
        _add_matches(counts, text, _GO_PATTERNS)
    elif language == "sh":
        _add_matches(counts, text, _SH_PATTERNS)
    elif language == "docker":
        _add_matches(counts, text, _DOCKER_PATTERNS)
    return counts


def count_any_language(text: str) -> Counts:
    """Markers of every family, read line by line: for text whose language is unknown or mixed."""
    counts: Counts = collections.Counter()
    for language in LANGUAGES:
        counts.update(count_markers(text, language, raw=True))
    return counts


def growth(old: Counts, new: Counts) -> list[tuple[str, str, int, int]]:
    """(kind, code, before, after) for every key whose count went UP. A move keeps the count; a removal lowers it; only an addition raises it."""
    return sorted(
        (kind, code, old.get((kind, code), 0), n)
        for (kind, code), n in new.items()
        if n > old.get((kind, code), 0)
    )


def render_marker(kind: str, code: str) -> str:
    """The marker as a reader would find it in source, assembled from halves so this file never holds one."""
    forms = {
        "noqa": ("# noq" + "a", "# noq" + "a: %s"),
        "noqa-file": ("# ruff: noq" + "a", "# ruff: noq" + "a: %s"),
        "type-ignore": ("# type: ignor" + "e", "# type: ignor" + "e[%s]"),
        "pyright-ignore": ("# pyright: ignor" + "e", "# pyright: ignor" + "e[%s]"),
        "pylint-disable": ("# pylint: disabl" + "e", "# pylint: disabl" + "e=%s"),
        "mypy": ("# mypy:", "# mypy: %s"),
        "ts-ignore": ("// @ts-ignor" + "e", "// @ts-ignor" + "e %s"),
        "ts-expect-error": ("// @ts-expect-erro" + "r", "// @ts-expect-erro" + "r %s"),
        "ts-nocheck": ("// @ts-nochec" + "k", "// @ts-nochec" + "k %s"),
        "eslint-disable": ("// eslint-disabl" + "e", "// eslint-disabl" + "e %s"),
        "biome-ignore": ("// biome-ignor" + "e", "// biome-ignor" + "e %s"),
        "nolint": ("//nolin" + "t", "//nolin" + "t:%s"),
        "lint-ignore": ("//lint:ignor" + "e", "//lint:ignor" + "e %s"),
        "shellcheck-disable": ("# shellcheck disabl" + "e", "# shellcheck disabl" + "e=%s"),
        "hadolint-ignore": ("# hadolint ignor" + "e", "# hadolint ignor" + "e=%s"),
    }
    bare, coded = forms.get(kind, (kind, kind + " %s"))
    return bare if code == BLANKET else coded % code


# --------------------------------------------------------------------------- the tree ---------------------------------------------------------------------------


def _tracked(repo: pathlib.Path) -> list[str]:
    out = subprocess.run(
        ["git", "-C", str(repo), "ls-files", "-z"],
        capture_output=True,
        check=True,
    ).stdout
    return [p for p in out.decode("utf-8", "surrogateescape").split("\0") if p]


def _head(path: pathlib.Path) -> str:
    try:
        with path.open("rb") as handle:
            return handle.readline(200).decode("utf-8", "replace")
    except OSError:
        return ""


class Scan:
    """The result of reading the tree: per-file marker counts, and the shape of what was read."""

    def __init__(self) -> None:
        self.counts: dict[str, Counts] = {}
        self.files_by_language: collections.Counter[str] = collections.Counter()
        self.files_by_repo: collections.Counter[str] = collections.Counter()
        self.unreadable: list[str] = []
        self.not_checked: list[str] = []


def scan_repo(root: pathlib.Path, label: str, prefix: str, scan: Scan) -> None:
    """Add every tracked code file of one repository to `scan`, keyed by its path from `root`."""
    repo = root / prefix if prefix else root
    for rel in _tracked(repo):
        path = repo / rel
        key = "%s/%s" % (prefix, rel) if prefix else rel
        suffix_language = language_for(rel)
        if suffix_language is None and os.path.splitext(rel)[1]:
            continue
        if not path.is_file():
            # A gitlink (a submodule's mount point) or a tracked file a peer just deleted.
            continue
        language = suffix_language or language_for(rel, _head(path))
        if language is None:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="surrogateescape")
        except OSError:
            scan.unreadable.append(key)
            continue
        scan.files_by_language[language] += 1
        scan.files_by_repo[label] += 1
        found = count_markers(text, language)
        if found:
            scan.counts[key] = found


def scan_tree(root: pathlib.Path, env: dict[str, str] | None = None) -> Scan:
    """Every repository in SCOPE that is checked out. An absent submodule is a hard failure in CI (`common.require_submodule` raises) and a printed NOT CHECKED line locally."""
    scan = Scan()
    for label, prefix, marker in SCOPE:
        if marker is not None and not common.require_submodule(root / marker, label, env=env):
            scan.not_checked.append(label)
            continue
        scan_repo(root, label, prefix, scan)
    return scan


# --------------------------------------------------------------------------- the baseline ---------------------------------------------------------------------------


def flatten(counts: dict[str, Counts]) -> dict[str, dict[str, int]]:
    """The baseline's on-disk shape: {file: {"kind code": n}}, sorted, so a diff of the file is readable."""
    return {
        path: {"%s %s" % kv: n for kv, n in sorted(per.items())}
        for path, per in sorted(counts.items())
    }


def unflatten(raw: dict[str, dict[str, int]]) -> dict[str, Counts]:
    out: dict[str, Counts] = {}
    for path, per in raw.items():
        found: Counts = collections.Counter()
        for key, n in per.items():
            kind, _, code = key.partition(" ")
            found[(kind, code)] = int(n)
        out[path] = found
    return out


def expand_ids(counts: dict[str, Counts]) -> list[str]:
    """One id per marker occurrence, `path::kind code#i`, so a COUNT baseline can go through the shared SET decision unchanged: a count that rises is a new id, and nothing else is."""
    return [
        "%s::%s %s#%d" % (path, kind, code, i)
        for path, per in sorted(counts.items())
        for (kind, code), n in sorted(per.items())
        for i in range(1, n + 1)
    ]


def compare(baseline: dict[str, Counts], current: dict[str, Counts]) -> tuple[list[str], list[str]]:
    """(grew, shrank): human lines for every (file, kind, code) whose count rose, and every one whose count fell."""
    grew: list[str] = []
    shrank: list[str] = []
    for path in sorted(set(baseline) | set(current)):
        old = baseline.get(path, collections.Counter())
        new = current.get(path, collections.Counter())
        for key in sorted(set(old) | set(new)):
            before, after = old.get(key, 0), new.get(key, 0)
            line = "%s: %s  (%d -> %d)" % (path, render_marker(*key), before, after)
            if after > before:
                grew.append(line)
            elif after < before:
                shrank.append(line)
    return grew, shrank


def read_baseline(path: pathlib.Path) -> dict[str, Counts] | None:
    if not path.is_file():
        return None
    doc = json.loads(path.read_text(encoding="utf-8"))
    return unflatten(doc.get("counts", {}))


NOTE = (
    "SHRINK-ONLY. Inline lint and type suppression markers that existed when operator ruling "
    "2026-10-08 banned them, counted per (file, marker kind, code), never by line. Written only "
    "by `.ci/scripts/quality/check_inline_suppressions.py --write-baseline`, which refuses any "
    "growth. Fix the code; a deliberate project-wide exception is a per-file entry in the "
    "linter's own config with a BLOCKER: reason (docs/agent-reference/suppressions.md). The goal "
    "state is an empty map."
)


def write_baseline(path: pathlib.Path, current: dict[str, Counts], *, first_seed: bool) -> int:
    previous = read_baseline(path)
    old_ids = expand_ids(previous or {})
    new_ids = expand_ids(current)
    added = shrink_only.baseline_additions(old_ids, new_ids)
    verdict = shrink_only.write_verdict(
        baseline_exists=previous is not None, first_seed=first_seed, additions=added
    )
    if verdict == "missing-baseline":
        print(
            "Refusing to write the baseline: %s does not exist. With no previous baseline "
            "nothing checks what is absorbed, so deleting the file would switch this rule off. "
            "A genuine first seed says so: --write-baseline --first-seed." % BASELINE_REL,
            file=sys.stderr,
        )
        return 1
    if verdict == "would-grow":
        print(
            "Refusing to write the baseline: it would GAIN %d marker(s) not in the current one:"
            % len(added),
            file=sys.stderr,
        )
        grew, _ = compare(previous or {}, current)
        for line in grew[:40]:
            print("    %s" % line, file=sys.stderr)
        print(
            "  The baseline shrinks. It never grows. Remove the marker and fix the code.\n"
            "  Do not add it to the baseline.",
            file=sys.stderr,
        )
        return 1
    body = {"note": NOTE, "counts": flatten(current)}
    path.write_text(json.dumps(body, indent=1, sort_keys=False) + "\n", encoding="utf-8")
    drained = len(set(old_ids) - set(new_ids))
    print(
        "baseline written: %d marker(s) in %d file(s) (%d before, %d drained, 0 added)"
        % (len(new_ids), len(current), len(old_ids), drained)
    )
    return 0


# --------------------------------------------------------------------------- the selftest ---------------------------------------------------------------------------

# Fixture tokens, assembled from halves so the literal never appears in this file.
_NQ = "# noq" + "a"
_TI = "# type: ignor" + "e"
_TSI = "@ts-ignor" + "e"
_ESL = "eslint-disabl" + "e"
_BIO = "biome-ignor" + "e"
_NOL = "//nolin" + "t"
_SC = "# shellcheck disabl" + "e"


def _selftest_cases() -> list[tuple[str, bool, str]]:
    """(label, ok, detail). Both directions throughout: a scanner that returns nothing passes every negative case, and one that matches everything passes every positive one."""

    def got(text: str, language: str) -> dict[tuple[str, str], int]:
        return dict(count_markers(text, language))

    cases: list[tuple[str, bool, str]] = []

    def check(label: str, ok: bool, detail: object = "") -> None:
        cases.append((label, ok, str(detail)))

    planted = "import os\nos.x = 1  %s: B010\n" % _NQ
    check(
        "python: a coded marker is counted",
        got(planted, "py") == {("noqa", "B010"): 1},
        got(planted, "py"),
    )
    check(
        "python: a multi-code marker counts each code",
        got("x = 1  %s: F401, E402\n" % _NQ, "py") == {("noqa", "F401"): 1, ("noqa", "E402"): 1},
    )
    check(
        "python: a bare marker is a blanket", got("x = 1  %s\n" % _NQ, "py") == {("noqa", "*"): 1}
    )
    check(
        "python: a type ignore keeps its codes",
        got("x = f()  %s[attr-defined]\n" % _TI, "py") == {("type-ignore", "attr-defined"): 1},
    )
    docstring = '"""Never write `%s: B010`; fix the code."""\nx = 1\n' % _NQ
    check(
        "CONTROL python: a DOCSTRING naming the marker is not a marker",
        got(docstring, "py") == {},
        got(docstring, "py"),
    )
    check(
        "CONTROL python: a string literal naming it is not one either",
        got("s = 'x  %s: B010'\n" % _NQ, "py") == {},
    )
    check(
        "CONTROL python: prose in a comment that merely names the word is not a marker",
        got("x = 1  # fix the code rather than reaching for noq" + "a\n", "py") == {},
    )
    check(
        "CONTROL python: a coverage pragma is not a lint suppression",
        got("x = 1  # pragma: no cover\n", "py") == {},
    )
    check("CONTROL python: a formatter switch is not one", got("# fmt: off\nx = 1\n", "py") == {})
    check(
        "python: a file tokenize cannot read still counts, line by line",
        got('s = """unterminated\nx = 1  %s: E501\n' % _NQ, "py") == {("noqa", "E501"): 1},
    )
    check(
        "raw mode reads a marker inside a STRING, for code that is about to WRITE it",
        got("s = 'x  %s: B010'\n" % _NQ, "py") == {}
        and dict(count_markers("s = 'x  %s: B010'\n" % _NQ, "py", raw=True))
        == {("noqa", "B010"): 1},
    )
    check(
        "js: a directive at a comment opener",
        got("// %s\nconst x = 1;\n" % _TSI, "js") == {("ts-ignore", "*"): 1},
    )
    check(
        "js: an eslint block directive counts each rule",
        got("/* %s no-console, no-alert */\n" % _ESL, "js")
        == {("eslint-disable", "no-console"): 1, ("eslint-disable", "no-alert"): 1},
    )
    check(
        "js: a next-line directive with a description keeps only the rule",
        got("// %s-next-line no-undef -- legacy global\n" % _ESL, "js")
        == {("eslint-disable", "no-undef"): 1},
    )
    check(
        "js: a biome directive keeps its category",
        got("// %s lint/suspicious/noExplicitAny: vendor type\n" % _BIO, "js")
        == {("biome-ignore", "lint/suspicious/noExplicitAny"): 1},
    )
    check(
        "js: a JSX comment opener counts",
        got("{/* %s */}\n" % _ESL, "js") == {("eslint-disable", "*"): 1},
    )
    check(
        "CONTROL js: prose between the opener and the token is not a directive",
        got("// Never write %s; fix the type instead.\n" % _TSI, "js") == {},
    )
    check(
        "CONTROL js: eslint-enable closes, it does not suppress",
        got("/* eslint-enable */\n", "js") == {},
    )
    check(
        "go: a nolint with linters counts each",
        got("x() %s:errcheck,gosec\n" % _NOL, "go")
        == {("nolint", "errcheck"): 1, ("nolint", "gosec"): 1},
    )
    check(
        "CONTROL go: prose about nolint is not the directive",
        got("// nolin" + "t is banned here\n", "go") == {},
    )
    check(
        "shell: a shellcheck directive counts",
        got("%s=SC2086\necho $x\n" % _SC, "sh") == {("shellcheck-disable", "SC2086"): 1},
    )
    check(
        "CONTROL shell: a quoted mention is not a comment",
        got('echo "x%s=SC1"\n' % _SC.lstrip("# "), "sh") == {},
    )
    check(
        "language: a python shebang on an extensionless file is python",
        language_for("bin/x", "#!/usr/bin/env python3\n") == "py",
    )
    check("language: a bash shebang is shell", language_for("bin/x", "#!/bin/bash\n") == "sh")
    check("CONTROL language: Markdown is not code", language_for("docs/x.md", "") is None)
    check("CONTROL language: JSON is not code", language_for("a/x.json", "") is None)
    check(
        "language: a Dockerfile variant is docker", language_for("deploy/Dockerfile.ci") == "docker"
    )

    base = {"a.py": collections.Counter({("noqa", "F401"): 2})}
    same = {"a.py": collections.Counter({("noqa", "F401"): 2})}
    more = {"a.py": collections.Counter({("noqa", "F401"): 2, ("noqa", "B010"): 1})}
    less = {"a.py": collections.Counter({("noqa", "F401"): 1})}
    grew, shrank = compare(base, same)
    check(
        "CONTROL baseline: an untouched tree is silent", grew == [] and shrank == [], (grew, shrank)
    )
    grew, shrank = compare(base, more)
    check(
        "baseline: a planted marker is growth",
        len(grew) == 1 and "B010" in grew[0] and shrank == [],
        grew,
    )
    grew, shrank = compare(base, less)
    check(
        "baseline: a removed marker is a drain to record", grew == [] and len(shrank) == 1, shrank
    )
    swapped = {"a.py": collections.Counter({("noqa", "F401"): 1, ("noqa", "B010"): 1})}
    grew, shrank = compare(base, swapped)
    check(
        "baseline CONTROL: a swap of one code for another is growth AND a drain, not a wash",
        len(grew) == 1 and len(shrank) == 1,
    )
    moved = {"b.py": collections.Counter({("noqa", "F401"): 2})}
    grew, _ = compare(base, moved)
    check("baseline: a marker moved to another FILE is growth there", len(grew) == 1)
    check(
        "write path: growth is refused by the shared decision",
        shrink_only.write_verdict(
            baseline_exists=True,
            first_seed=False,
            additions=shrink_only.baseline_additions(expand_ids(base), expand_ids(more)),
        )
        == "would-grow",
    )
    check(
        "CONTROL write path: a drain is allowed",
        shrink_only.write_verdict(
            baseline_exists=True,
            first_seed=False,
            additions=shrink_only.baseline_additions(expand_ids(base), expand_ids(less)),
        )
        is None,
    )
    check(
        "write path: a missing baseline is refused without --first-seed",
        shrink_only.write_verdict(baseline_exists=False, first_seed=False, additions=[])
        == "missing-baseline",
    )
    check("round trip: flatten then unflatten is the identity", unflatten(flatten(more)) == more)
    check(
        "growth(): an untouched count is not growth, a raised one is",
        growth(collections.Counter({("noqa", "X1"): 1}), collections.Counter({("noqa", "X1"): 1}))
        == []
        and growth(collections.Counter(), collections.Counter({("noqa", "X1"): 1}))
        == [("noqa", "X1", 0, 1)],
    )
    return cases


def selftest(*, quiet: bool = False) -> int:
    cases = _selftest_cases()
    bad = [c for c in cases if not c[1]]
    if not quiet or bad:
        for label, ok, detail in cases:
            if not quiet or not ok:
                print(
                    "  %s  %s%s"
                    % ("PASS" if ok else "FAIL", label, "" if ok else "  <- %s" % detail)
                )
    if len(cases) < 30:
        print(
            "  FAIL  only %d control(s) ran; the battery is not being executed as written"
            % len(cases)
        )
        return 1
    print("inline-suppressions selftest: %d control(s), %d failed" % (len(cases), len(bad)))
    return 1 if bad else 0


# --------------------------------------------------------------------------- the gate ---------------------------------------------------------------------------

REMEDY = """\
  Inline lint and type suppressions are banned (operator ruling 2026-10-08).
  Fix the code the linter is pointing at. For a deliberate, project-wide exception,
  add a per-file entry to the linter's own config (pyproject.toml per-file-ignores,
  biome.json overrides, .golangci.yml exclusions) carrying a BLOCKER: reason, per
  docs/agent-reference/suppressions.md. Do not add the marker to the baseline."""


def main(argv: list[str], root: pathlib.Path | None = None) -> int:
    if "--selftest" in argv:
        return selftest()
    root = root if root is not None else paths.repo_root()
    if selftest(quiet=True) != 0:
        print(
            "inline-suppressions: an instrument control failed; every verdict below would be meaningless",
            file=sys.stderr,
        )
        return 2
    try:
        scan = scan_tree(root)
    except common.RefusalError as exc:
        exc.report()
        return exc.code
    except subprocess.CalledProcessError as exc:
        print(
            "inline-suppressions: git ls-files failed (%s); the tree was not read" % exc,
            file=sys.stderr,
        )
        return 1

    if scan.files_by_repo.get("console", 0) < MIN_CONSOLE_FILES:
        print(
            "inline-suppressions: VACUOUS: read %d code file(s) in console, floor is %d. The file "
            "list did not come from the real tree, so its silence would mean nothing."
            % (scan.files_by_repo.get("console", 0), MIN_CONSOLE_FILES),
            file=sys.stderr,
        )
        return 1
    if scan.unreadable:
        print(
            "inline-suppressions: %d tracked file(s) could not be read: %s"
            % (len(scan.unreadable), ", ".join(scan.unreadable[:10])),
            file=sys.stderr,
        )
        return 1

    current = scan.counts
    # A repository that was not checked out locally keeps its baseline entries as they are: it was not read, so it can neither grow nor drain.
    baseline_path = root / BASELINE_REL
    if "--write-baseline" in argv:
        previous = read_baseline(baseline_path) or {}
        for label in scan.not_checked:
            for path, per in previous.items():
                if path.startswith(label + "/"):
                    current[path] = per
        return write_baseline(baseline_path, current, first_seed="--first-seed" in argv)

    baseline = read_baseline(baseline_path)
    if baseline is None:
        print(
            "inline-suppressions: %s is missing; there is nothing to hold the tree to."
            % BASELINE_REL,
            file=sys.stderr,
        )
        return 1
    for label in scan.not_checked:
        baseline = {p: c for p, c in baseline.items() if not p.startswith(label + "/")}

    grew, shrank = compare(baseline, current)
    total = sum(sum(c.values()) for c in current.values())
    shape = "%d code file(s) read (%s) in %s" % (
        sum(scan.files_by_repo.values()),
        ", ".join("%s %d" % kv for kv in sorted(scan.files_by_language.items())),
        ", ".join("%s %d" % kv for kv in scan.files_by_repo.items()),
    )
    rc = 0
    if grew:
        print("✗ %d NEW inline suppression marker(s):" % len(grew), file=sys.stderr)
        for line in grew:
            print("    %s" % line, file=sys.stderr)
        print(REMEDY, file=sys.stderr)
        rc = 1
    if shrank:
        print(
            "✗ %d baselined marker count(s) went DOWN. Good; now record the drain in the same commit:"
            % len(shrank),
            file=sys.stderr,
        )
        for line in shrank[:40]:
            print("    %s" % line, file=sys.stderr)
        if len(shrank) > 40:
            print("    ... and %d more" % (len(shrank) - 40), file=sys.stderr)
        print(
            "  Run: .ci/scripts/quality/check_inline_suppressions.py --write-baseline",
            file=sys.stderr,
        )
        rc = 1
    if rc == 0:
        print(
            "✓ inline suppressions: %d marker(s) in %d file(s), all baselined, none added"
            % (total, len(current))
        )
    print("  %s" % shape)
    by_kind: collections.Counter[str] = collections.Counter()
    for per in current.values():
        for (kind, _code), n in per.items():
            by_kind[kind] += n
    print("  by kind: %s" % ", ".join("%s %d" % kv for kv in by_kind.most_common()))
    if scan.not_checked:
        print(
            "  NOT CHECKED (not checked out here; a hard failure in CI): %s"
            % ", ".join(scan.not_checked)
        )
    print("  out of scope (no linted code surface): %s" % ", ".join(OUT_OF_SCOPE))
    return rc
