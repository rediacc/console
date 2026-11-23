"""check:ci-record-paths -- the record set a push receipt may advance across, and the fixed widths no grant sizes.

WHY THIS EXISTS (agent/plans/PLAN-prepush-full-cpu.md part 5, PF23). `worklist.py --review-commit` commits agent/reviews/<branch>/ after every reviewed commit, and on 2026-10-05 nine pre-push receipts died that way with no code changed. block_unverified_push now lets a receipt ADVANCE across a commit confined to the globs in .ci/policy/record-paths.json, provided the gates that READ those globs
were re-run at the new tree. That rule is exactly as safe as the reader lists are complete: a gate that reads agent/reviews/ but is missing from the list would be skipped by the advance, and its verdict on the pushed tree would be one nobody computed. So the lists are DERIVED here and compared with the policy, in both directions.

HOW A READER IS DERIVED. For every `gate: true` entry of scripts/ci-runner/gates.lock.json, the files of its leaves and of their local imports (Python `rediacc_ci.*` and sibling modules, the stop-hook library, TypeScript relative imports) are read, and a gate reads a record when any of them:
  cite   names the record's literal prefix (`agent/reviews`) inside a string literal that holds no whitespace, or as joined segments (`"agent", "reviews"`), other than a path the record excludes;
  root   names an ancestor of it as a scan root, `"agent/"` or a glob under `agent/`;
  config cites a JSON config file whose glob strings match one of the record's probe paths (prose-style reads `*.md` through .ci/config/prose-style-rules.json, and a review record is a `.md`), other than a glob under a key that names an exclusion (`literalExclude`).
Asked BEFORE those four, from the gate's own gates.lock.json entry (agent/plans/PLAN-push-decoupling.md F1):
  declared a `paths` or `names` glob matches one of the record's probes, or a `lists` directory is the parent of the record's literal prefix or lies at or inside it (the root `''` reaches nothing). This is how the `names: ['**']` gates, which cite no record path and list every file name, are counted as readers. A notReader cannot overrule this tier; a declaration that over-reaches is narrowed in the lock.
scripts/ci-runner/manifest.ts and trace-ledger.ts (NOT_SCAN_CODE) are never read by the file tiers: the globs in them are OTHER gates' declarations, which the declared tier reads at their source.
CODE, NOT PROSE (2026-11-16, when the plan files joined the record set). The cite, root and glob tiers read each file with its comments and docstrings blanked (`code_text`), and the cite tier counts a path only as a whole literal: a docstring that says why a gate exists names plan files by the dozen, and a message such as `"see agent/plans/x.md"` is about the file, not a read of it. Read as citations, those made 168 of 380 gates readers of agent/plans/ where 46 are. A shell script keeps the old reading, since a path there is an unquoted word.
This still OVER-counts on purpose. A false reader costs one extra gate at an advance; a missed reader lets an unjudged record change through the push. A gate the derivation flags that genuinely reads nothing goes in `notReaders` with its reason, by name, and is printed on every run.

THE SECOND MODE (PF9): FIXED WIDTHS. The 2026-10-05 ruling removed every static worker count: a parallel tool sizes itself from the cores granted at launch. What remains fixed is request concurrency against a remote API (`xargs -P 8` of R2 copies, eight `gh api` calls), which is not a core count. Each such width is listed in .ci/policy/fixed-widths.json with the remote limit it respects, and this mode refuses a literal width that is not listed, a
listed width that is gone or changed, and any core cap (`min(8, os.cpu_count())`) at all: a core cap is never an I/O width, so it cannot be listed.

Exit 0 clean, 1 on a finding, 2 when a control fails, the gate cannot see its inputs (zero gates, zero records, zero scanned files), or an argument is unknown or lacks its value.

---- gate ----
kind: step
step: Record paths and fixed widths
lane: quality-static
selftest: true
why: A receipt advances across a record-only commit only when every reader of those records is declared; a fixed parallel width must be a listed I/O fan-out.
---- end gate ----
"""

from __future__ import annotations

import ast
import functools
import io
import json
import pathlib
import re
import subprocess
import sys
import tempfile
import tokenize
from typing import Any

from rediacc_ci import controls, paths
from rediacc_ci.controls import plant
from rediacc_ci.policy_paths import policy_rel

POLICY_REL = policy_rel("record-paths.json")
SELF_REL = ".ci/rediacc_ci/quality/record_paths.py"
WIDTHS_REL = policy_rel("fixed-widths.json")
LOCK_REL = "scripts/ci-runner/gates.lock.json"
POLICY_VERSION = 1
CONTROL_FLOOR = 60

#: Files that are config for this gate or for the runner, never a scanner's scope: their glob strings say what a gate is SELECTED by, not what it reads.
NOT_SCAN_CONFIG = frozenset({POLICY_REL, WIDTHS_REL, LOCK_REL})
#: Code files that hold OTHER gates' path lists as data, never a scope of their own (agent/plans/PLAN-push-decoupling.md F1). scripts/ci-runner/manifest.ts carries every gate's `paths`, and scripts/ci-runner/trace-ledger.ts the traced reads of each; read as code, one `paths: ['agent/plans/**']` there made every gate importing the gate table a reader of the plan records, and each of those needed a hand-written notReader. What a gate DECLARES is read once, from its own gates.lock.json entry, by the `declared` tier.
NOT_SCAN_CODE = frozenset({"scripts/ci-runner/manifest.ts", "scripts/ci-runner/trace-ledger.ts"})
#: The runner's cache: what a run measured or left behind (a receipt, a duration table), never a scanner's scope. scripts/ci-runner/lease-seed.ts names `.ci/cache/prepush-receipt.json` to seed a lease with it, and a receipt quotes every changed path of its advances.
NOT_SCAN_CONFIG_PREFIXES = (".ci/cache/",)
#: A config key that says what a scanner does NOT read. `.ci/config/pins.json` lists `agent/**` under `literalExclude`, and read as a scope that one glob made eleven pin gates readers of every record under agent/ (measured 2026-11-16).
EXCLUSION_KEY_RE = re.compile(r"exclude|skip|ignore", re.IGNORECASE)
#: Package manifests and lockfiles: their `*` strings are version ranges and package-name patterns, never file globs.
NOT_SCAN_CONFIG_NAMES = frozenset({"package.json", "package-lock.json", ".syncpackrc.json"})
#: Where the import closure resolves a Python module name, in order.
PY_IMPORT_BASES = (".ci", ".claude", ".claude/hooks/stop")
TS_SUFFIXES = (".ts", ".mts", ".cts", ".js", ".mjs", ".cjs", ".tsx")
SH_SUFFIXES = (".sh", ".bash")
TEXT_SUFFIXES = (".py", *SH_SUFFIXES, *TS_SUFFIXES)
EVIDENCE_RE = re.compile(r"^(?P<file>[^\s:]+):(?P<line>\d+)\b")
JSON_CITE_RE = re.compile(r"""['"]((?:\.{0,2}/)?[\w./-]+\.json)['"]""")
QUOTED_RE = re.compile(r"""(['"])((?:(?!\1)[^\\\n])*)\1""")
#: A run with no whitespace and no quote in it, standing between two quote characters: the whole of a string literal (`"agent/plans/x.md"`, a template `${root}/agent/plans`), and never a word of a sentence. Read by its two neighbours rather than by pairing quotes along the line, so an apostrophe or a regex literal earlier on the line cannot shift the pairing and hide a literal.
LITERAL_RUN_RE = re.compile(r"""(?<=['"`])[^\s'"`]+(?=['"`])""")
JOINED_RE = re.compile(r"""(['"])([\w.<>*-]+)\1((?:\s*[,/]\s*(['"])[\w.<>*-]+\4)+)""")
SEGMENT_RE = re.compile(r"""(['"])([\w.<>*-]+)\1""")
PY_TS_IMPORT_RE = re.compile(
    r"""(?:\bfrom\s+|\bimport\s*\(?\s*|\brequire\s*\(\s*)['"](\.{1,2}/[^'"]+)['"]"""
)
#: A LEG a TypeScript leaf spawns, in the `{ label, args: ['<repo path>', ...] }` shape scripts/gen/gen-manifest.ts runs its `gen:gates --check` legs in. Those scripts are child processes, not imports, so without this edge check:ci-gen-gates (whose one leaf is gen-manifest.ts) would carry none of the reads of the eight checks it replaced, and a record change one of them judges would advance a receipt unjudged. The path is repo-relative, never `./`.
TS_LEG_RE = re.compile(r"""\bargs:\s*\[\s*['"]((?:scripts|\.ci)/[^'"\s]+\.(?:ts|py))['"]""")


# ---------------------------------------------------------------- globs


def glob_re(glob: str) -> re.Pattern[str]:
    """`glob` as an anchored regex over a repo-relative path: `**` spans directories, `*` and `?` do not.

    The same three rules as `record_glob_re` in .claude/rediacc_hooks/guards/block_unverified_push.py, which judges the push with them; test_gate_record_paths.py pins the two equal on one corpus.
    """
    out = []
    i = 0
    while i < len(glob):
        if glob.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif glob.startswith("**", i):
            out.append(".*")
            i += 2
        elif glob[i] == "*":
            out.append("[^/]*")
            i += 1
        elif glob[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(glob[i]))
            i += 1
    return re.compile("^%s$" % "".join(out))


def literal_prefix(glob: str) -> str:
    """The directory part before the first wildcard: `agent/worklist/*.jsonl` -> `agent/worklist`. A glob with no wildcard names one file, and that path is its own prefix (`.ci/config/carried-reds.json`): cut back to its directory it would cite every file beside it, and measured 2026-11-08 that made 213 of 377 gates readers of the carry file."""
    head = re.split(r"[*?\[{]", glob, maxsplit=1)[0]
    if head == glob:
        return glob
    return head.rsplit("/", 1)[0] if "/" in head else head


def covers(record: dict, path: str) -> bool:
    return bool(glob_re(record["glob"]).match(path)) and not any(
        glob_re(x).match(path) for x in record["exclude"]
    )


def config_glob_matches(pattern: str, path: str) -> bool:
    """Does a scanner's config glob reach `path`? A pattern with no `/` is a basename pattern (`*.md`), the way prose-style, biome and gitignore read one."""
    if pattern.endswith("/"):
        return (
            ("/" + path).find("/" + pattern.lstrip("./")) != -1
            if "*" not in pattern
            else bool(glob_re(pattern + "**").match(path))
        )
    if "/" not in pattern:
        return bool(glob_re(pattern).match(path.rsplit("/", 1)[-1]))
    return bool(glob_re(pattern.lstrip("./")).match(path))


# ---------------------------------------------------------------- policy


class PolicyError(ValueError):
    pass


def parse_policy(doc: object) -> list[dict]:
    """record-paths.json -> records. Raises PolicyError naming the first defect: a policy that half-parses judges nothing."""
    if not isinstance(doc, dict) or doc.get("version") != POLICY_VERSION:
        raise PolicyError('%s is not `"version": %d`' % (POLICY_REL, POLICY_VERSION))
    raw = doc.get("records")
    if not isinstance(raw, list) or not raw:
        raise PolicyError(
            "%s has no `records` list; zero records would make every advance a code push"
            % POLICY_REL
        )
    out = []
    for i, rec in enumerate(raw):
        if not isinstance(rec, dict):
            raise PolicyError("record %d is not an object" % i)
        glob = rec.get("glob")
        excepted = rec.get("except", [])
        probes = rec.get("probes")
        if not isinstance(glob, str) or not glob or glob.startswith("/"):
            raise PolicyError("record %d needs a repo-relative `glob`" % i)
        if not isinstance(excepted, list) or not all(isinstance(x, str) and x for x in excepted):
            raise PolicyError("%s: `except` must be a list of globs" % glob)
        # THREE MATCHERS READ THESE GLOBS (this gate, block_unverified_push, run.ts `globToRegExp`), and they agree on `**/`, `**` and `*` only: run.ts reads `?` as any character, slash included. A glob outside that vocabulary would be judged differently by the runner that advances and the guard that admits.
        for g in (glob, *excepted):
            if re.search(r"[?\[\]{}]", g):
                raise PolicyError(
                    "%s: %r uses ? [ ] or { }; record globs use only ** and * so the runner and the guard read them alike"
                    % (glob, g)
                )
        if (
            not isinstance(probes, list)
            or not probes
            or not all(isinstance(p, str) for p in probes)
        ):
            raise PolicyError(
                "%s: `probes` must list at least one real-shaped path the glob covers" % glob
            )
        # `review` is read by the per-commit reviewer (.claude/hooks/stop/wl_review.py skip_globs): a record marked "keep" advances a receipt like any other and still enters the reviewed diff, because a plan is a record of intent whose text is worth a review. One spelling only, so a typo cannot quietly drop a record out of review.
        if rec.get("review", "keep") != "keep":
            raise PolicyError(
                '%s: `review` is %r; the only value is "keep" (the record stays in the per-commit review), and a record that leaves the review omits the key'
                % (glob, rec.get("review"))
            )
        tables = {}
        for name, field in (("readers", "evidence"), ("notReaders", "reason")):
            entries = rec.get(name, [] if name == "notReaders" else None)
            if not isinstance(entries, list) or not all(
                isinstance(e, dict)
                and isinstance(e.get("id"), str)
                and e["id"]
                and isinstance(e.get(field), str)
                and e[field].strip()
                for e in entries
            ):
                raise PolicyError(
                    '%s: `%s` must be a list of {"id", "%s"} with both non-empty'
                    % (glob, name, field)
                )
            ids = [e["id"] for e in entries]
            if len(ids) != len(set(ids)):
                raise PolicyError("%s: `%s` names a gate twice" % (glob, name))
            tables[name] = {e["id"]: e[field] for e in entries}
        out.append(
            {
                "glob": glob,
                "exclude": list(excepted),
                "probes": list(probes),
                "readers": tables["readers"],
                "notReaders": tables["notReaders"],
            }
        )
    return out


# ---------------------------------------------------------------- closure


def _stat_key(path: pathlib.Path) -> tuple[int, int]:
    """(mtime_ns, size), so a memoised read of a file is dropped the moment the file changes, as a control that plants into a file and re-derives needs."""
    try:
        st = path.stat()
    except OSError:
        return (-1, -1)
    return (st.st_mtime_ns, st.st_size)


def _py_imports(path: pathlib.Path, root: pathlib.Path) -> list[pathlib.Path]:
    """Local files `path` imports. MEMOISED on the file's stat: derive_readers takes every gate's closure once per record glob, which re-parsed the same modules 1,793 times and made this gate measure 40.5 s as a CI step (27 s locally, 2026-10-05)."""
    return list(_py_imports_cached(path, root, _stat_key(path)))


@functools.cache
def _py_imports_cached(
    path: pathlib.Path, root: pathlib.Path, _key: tuple[int, int]
) -> tuple[pathlib.Path, ...]:
    return tuple(_py_imports_uncached(path, root))


def _py_imports_uncached(path: pathlib.Path, root: pathlib.Path) -> list[pathlib.Path]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, ValueError):
        return []
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.append(node.module)
            names.extend("%s.%s" % (node.module, a.name) for a in node.names)
    found: list[pathlib.Path] = []
    bases = [path.parent, *(root / b for b in PY_IMPORT_BASES)]
    for name in names:
        parts = name.split(".")
        found.extend(
            cand
            for base in bases
            for cand in (
                base.joinpath(*parts).with_suffix(".py"),
                base.joinpath(*parts, "__init__.py"),
            )
            if cand.is_file()
        )
    return found


def _ts_imports(path: pathlib.Path, root: pathlib.Path) -> list[pathlib.Path]:
    """Local files a TS/JS file imports, and the scripts it spawns as legs (TS_LEG_RE, resolved against `root`), memoised on its stat like `_py_imports`."""
    return list(_ts_imports_cached(path, root, _stat_key(path)))


@functools.cache
def _ts_imports_cached(
    path: pathlib.Path, root: pathlib.Path, _key: tuple[int, int]
) -> tuple[pathlib.Path, ...]:
    return tuple(_ts_imports_uncached(path, root))


def _ts_imports_uncached(path: pathlib.Path, root: pathlib.Path) -> list[pathlib.Path]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    found = [root / rel for rel in TS_LEG_RE.findall(text) if (root / rel).is_file()]
    for spec in PY_TS_IMPORT_RE.findall(text):
        base = path.parent / spec
        stem = (
            pathlib.Path(str(base)[: -len(base.suffix)])
            if base.suffix in (".js", ".mjs", ".cjs")
            else base
        )
        for cand in (base, *(pathlib.Path(str(stem) + s) for s in TS_SUFFIXES), base / "index.ts"):
            if cand.is_file():
                found.append(cand)
                break
    return found


def closure(leaves: list[str], root: pathlib.Path) -> set[pathlib.Path]:
    """Every local file reachable from `leaves` by import. A leaf that is not a file (a tool name like `biome`) contributes nothing."""
    seen: set[pathlib.Path] = set()
    stack = [root / leaf for leaf in leaves]
    while stack:
        path = stack.pop()
        try:
            path = path.resolve()
        except OSError:
            continue
        if path in seen or not path.is_file():
            continue
        seen.add(path)
        if path.suffix == ".py":
            stack.extend(_py_imports(path, root))
        elif path.suffix in TS_SUFFIXES:
            stack.extend(_ts_imports(path, root))
    return seen


# ---------------------------------------------------------------- derivation


def _line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _rel(path: pathlib.Path, root: pathlib.Path) -> str:
    try:
        return str(path.relative_to(root.resolve()))
    except ValueError:
        return str(path)


def _blank(chars: list[str], start: int, end: int) -> None:
    for k in range(max(start, 0), min(end, len(chars))):
        if chars[k] != "\n":
            chars[k] = " "


def _py_code(text: str) -> str:
    """Python source with every comment and every bare string statement (a docstring, or a string standing alone as a note) blanked, offsets kept. Read from the token stream alone: a statement made of nothing but string tokens does nothing when run, wherever it stands. A file that does not tokenise comes back WHOLE: prose left in over-counts, and a citation dropped by a half-read file would be a missed reader."""
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(text).readline))
    except (SyntaxError, ValueError, tokenize.TokenError):
        return text
    starts = [0]
    for line in text.split("\n"):
        starts.append(starts[-1] + len(line) + 1)
    chars = list(text)

    def at(pos: tuple[int, int]) -> int:
        return starts[min(pos[0], len(starts) - 1) - 1] + pos[1]

    statement: list[tokenize.TokenInfo] = []
    only_strings = True
    for tok in tokens:
        if tok.type == tokenize.COMMENT:
            _blank(chars, at(tok.start), at(tok.end))
        elif tok.type in (tokenize.NEWLINE, tokenize.ENDMARKER):
            if only_strings:
                for s in statement:
                    _blank(chars, at(s.start), at(s.end))
            statement, only_strings = [], True
        elif tok.type == tokenize.STRING:
            statement.append(tok)
        elif tok.type not in (tokenize.NL, tokenize.INDENT, tokenize.DEDENT):
            only_strings = False
    return "".join(chars)


def _ts_code(text: str) -> str:
    """TypeScript or JavaScript with its WHOLE-LINE comments blanked: a line that starts `//`, and a block that starts a line with `/*` through its `*/`. A comment after code on the same line stays (it over-counts), and a block that never closes is left alone, because blanking to the end of the file would hide every citation below it. No tokeniser is attempted: a regex literal holding a quote derails one, and the cost of a derail is a reader nobody sees."""
    lines = text.split("\n")
    out = list(lines)
    i = 0
    while i < len(lines):
        bare = lines[i].lstrip()
        if bare.startswith("//"):
            out[i] = " " * len(lines[i])
        elif bare.startswith("/*"):
            open_at = lines[i].index("/*")
            j, close = i, lines[i].find("*/", open_at + 2)
            while close == -1 and j + 1 < len(lines):
                j += 1
                close = lines[j].find("*/")
            if close != -1:
                for k in range(i, j):
                    out[k] = " " * len(lines[k])
                out[j] = " " * (close + 2) + lines[j][close + 2 :]
                i = j
        i += 1
    return "\n".join(out)


def _sh_code(text: str) -> str:
    """A shell script with its whole-line `#` comments blanked."""
    return "\n".join(
        " " * len(line) if line.lstrip().startswith("#") else line for line in text.split("\n")
    )


@functools.lru_cache(maxsize=4096)
def code_text(text: str, suffix: str) -> str:
    """`text` as the interpreter reads it, for the tiers that look for a path: comments and docstrings blanked to spaces, every offset and line number unchanged. A docstring that says WHY a gate exists names plan files by the dozen (`agent/plans/PLAN-x.md`), and read as citations those made 168 of 380 gates readers of the plan set where 46 read it (measured 2026-11-16)."""
    if suffix == ".py":
        return _py_code(text)
    if suffix in SH_SUFFIXES:
        return _sh_code(text)
    return _ts_code(text)


@functools.lru_cache(maxsize=4096)
def _quoted(text: str) -> tuple[tuple[int, str], ...]:
    """(offset, string) of every quoted string in `text`, once per text: each record's tiers scan the same files, and re-tokenising them per record was most of this gate's remaining time. Both readings of a quote are kept, the paired one and the whitespace-free run between any two quotes (`_literal_runs`), so a template literal counts and a quote earlier on the line cannot hide a glob."""
    paired = {(m.start(2), m.group(2)) for m in QUOTED_RE.finditer(text)}
    return tuple(sorted(paired | set(_literal_runs(text))))


@functools.lru_cache(maxsize=4096)
def _literal_runs(text: str) -> tuple[tuple[int, str], ...]:
    """(offset, run) of every whitespace-free run standing between two quote characters (LITERAL_RUN_RE), once per text."""
    return tuple((m.start(), m.group(0)) for m in LITERAL_RUN_RE.finditer(text))


@functools.lru_cache(maxsize=4096)
def _joined(text: str) -> tuple[tuple[int, str], ...]:
    """(offset, token) of every path built by joining literal segments, once per text (see `_quoted`)."""
    return tuple(
        (m.start(), "/".join([m.group(2), *(s.group(2) for s in SEGMENT_RE.finditer(m.group(3)))]))
        for m in JOINED_RE.finditer(text)
    )


@functools.cache
def _stem_re(stem: str) -> re.Pattern[str]:
    return re.compile(r"(?<![\w-])%s(?![\w-])(?:/[^\s'\"`),;:\]}]*)?" % re.escape(stem))


def cite_hits(code: str, record: dict, bare_words: bool = False) -> list[tuple[int, str]]:
    """(offset, token) for every citation of the record's literal prefix that is not wholly an excluded path.

    `code` is `code_text` of the file, so a comment or a docstring cites nothing. A citation is the prefix inside a string literal that holds no whitespace (`open("agent/plans/x.md")`, a template `${root}/agent/plans`), or a path joined from literal segments (`"agent" / "plans"`). A path named in a sentence (`"see agent/plans/x.md for the design"`) is a message about the file, not a read of it. `bare_words` is the shell reading, where a path is an unquoted word (`ls agent/plans`), so every occurrence counts there.
    """
    stem = literal_prefix(record["glob"])
    stem_re = _stem_re(stem)
    hits: list[tuple[int, str]] = []
    if stem not in code:
        pass  # no literal can hold it, and the joined form below spells it in segments
    elif bare_words:
        hits = [(m.start(), m.group(0)) for m in stem_re.finditer(code)]
    else:
        for off, run in _literal_runs(code):
            m = stem_re.search(run)
            if m is not None:
                hits.append((off + m.start(), m.group(0)))
    for off, token in _joined(code):
        if token == stem or token.startswith(stem + "/"):
            hits.append((off, token))
    return [
        (off, tok)
        for off, tok in hits
        if not any(glob_re(x).match(tok.rstrip("/")) for x in record["exclude"])
    ]


def root_hits(text: str, record: dict) -> list[tuple[int, str]]:
    """(offset, string) for every quoted ancestor-of-the-record scan root, `"agent/"`."""
    stem = literal_prefix(record["glob"])
    parts = stem.split("/")
    # A glob under an ancestor (`agent/**/*.md`) is the glob tier's to judge against the probes; this tier is the bare directory, which reads everything below it.
    roots = {"/".join(parts[:n]) + "/" for n in range(1, len(parts))}
    return [(off, q) for off, q in _quoted(text) if q in roots]


def is_path_glob(s: str) -> bool:
    """A string that reads as a FILE glob: a wildcard plus something besides wildcards and slashes (`*.md`, `agent/**`), or a directory ending in `/`. A bare `*`, `**` or `**/*` is a match-everything pattern whose meaning (versions, package names, a tsconfig's own directory) a gate cannot know from here, so it is not read as a scan of this tree."""
    if s.startswith("!") or len(s) >= 200 or "\n" in s or " " in s:
        return False
    if s.endswith("/") and "*" not in s:
        return len(s) > 1
    return "*" in s and bool(re.sub(r"[*/?{},]", "", s))


def expand_braces(pattern: str) -> list[str]:
    """`agent/**/*.{md,mdx}` -> the two patterns; a single level is all the tree uses."""
    m = re.search(r"\{([^{}]*)\}", pattern)
    if not m:
        return [pattern]
    return [pattern[: m.start()] + alt + pattern[m.end() :] for alt in m.group(1).split(",")]


def _json_globs(doc: object) -> list[str]:
    """Every file glob a config holds as a scope. A value under a key that names an exclusion (EXCLUSION_KEY_RE: `literalExclude`, `review_skip_globs`, `ignore`) is what the scanner leaves out, so it is not read as something the scanner reads."""
    out: list[str] = []
    if isinstance(doc, str):
        if is_path_glob(doc):
            out.extend(expand_braces(doc))
    elif isinstance(doc, dict):
        for k, v in doc.items():
            if not EXCLUSION_KEY_RE.search(k):
                out.extend(_json_globs(v))
    elif isinstance(doc, list):
        for v in doc:
            out.extend(_json_globs(v))
    return out


def glob_hits(text: str, record: dict) -> list[tuple[int, str]]:
    """(offset, glob) for every quoted file glob in code that reaches one of the record's probes: `git ls-files '*.md'` scans review records as surely as a config file does."""
    return [
        (off, s)
        for off, s, patterns in _code_globs(text)
        if any(config_glob_matches(p, probe) for p in patterns for probe in record["probes"])
    ]


@functools.lru_cache(maxsize=4096)
def _code_globs(text: str) -> tuple[tuple[int, str, tuple[str, ...]], ...]:
    """(offset, glob, its brace expansions) of every quoted file glob in `text`, once per text: which strings are globs does not depend on the record asking."""
    return tuple(
        (off, s, tuple(expand_braces(s)))
        for off, s in _quoted(text)
        if is_path_glob(s) and not s.endswith("/")
    )


def config_hits(text: str, record: dict, root: pathlib.Path, cache: dict) -> list[tuple[int, str]]:
    """(offset, "<config>: <glob>") for every cited JSON config holding a glob that reaches one of the record's probes.

    `text` is the file WHOLE, docstring included, unlike the other tiers: a gate that builds its config path from segments often names the file only in its docstring, and a config cited there is still the config it loads.
    """
    hits = []
    for m in JSON_CITE_RE.finditer(text):
        rel = m.group(1).lstrip("./") if m.group(1).startswith("./") else m.group(1)
        if (
            rel in NOT_SCAN_CONFIG
            or rel.startswith(NOT_SCAN_CONFIG_PREFIXES)
            or rel.rsplit("/", 1)[-1] in NOT_SCAN_CONFIG_NAMES
            or rel.startswith(("/", ".."))
        ):
            continue
        if rel not in cache:
            try:
                cache[rel] = _json_globs(json.loads((root / rel).read_text(encoding="utf-8")))
            except (OSError, ValueError):
                cache[rel] = []
        for pattern in cache[rel]:
            if any(config_glob_matches(pattern, probe) for probe in record["probes"]):
                hits.append((m.start(), "%s: %s" % (rel, pattern)))
                break
    return hits


def file_evidence(
    path: pathlib.Path, text: str, record: dict, root: pathlib.Path, configs: dict
) -> str | None:
    """`file:line (tier) token` for the first way one file reads one record, or None. The answer depends on the file and the record alone, never on the gate asking, so `derive_readers` takes it once per pair."""
    code = code_text(text, path.suffix)
    tiers = (
        ("cite", lambda: cite_hits(code, record, bare_words=path.suffix in SH_SUFFIXES)),
        ("root", lambda: root_hits(code, record)),
        ("glob", lambda: glob_hits(code, record)),
        ("config", lambda: config_hits(text, record, root, configs)),
    )
    for tier, find in tiers:
        found = find()
        if found:
            off, token = found[0]
            return "%s:%d (%s) %s" % (_rel(path, root), _line_of(text, off), tier, token)
    return None


DECLARED_TAG = "(declared)"


def _str_list(value: object) -> list[str]:
    return [v for v in value if isinstance(v, str)] if isinstance(value, list) else []


def lists_reach(directory: str, record: dict) -> bool:
    """Does a gate that LISTS `directory` see a record change? It does when the directory is the parent of the record's literal prefix (a listing of `agent` sees `agent/reviews` appear, and `agent/INDEX.md` come and go) or lies at or inside that prefix. The repository root `''` is the parent of every top-level name and says nothing about a record two levels down, so it reaches none."""
    if not directory:
        return False
    stem = literal_prefix(record["glob"])
    parent = stem.rsplit("/", 1)[0] if "/" in stem else ""
    return directory in (parent, stem) or directory.startswith(stem + "/")


def declared_hit(gate: dict, record: dict) -> str | None:
    """`(declared) <field> <value>` for the first input this gate's own gates.lock.json entry declares that reaches the record, or None.

    A `paths` or `names` glob reaches a record when it matches one of the record's probes (`config_glob_matches`, so a bare `**` reaches everything); a `lists` directory reaches it by `lists_reach`. This is the tier that sees the `names: ['**']` gates: they read the tree's file names, so a record file that appears or goes away changes their verdict, yet no leaf of theirs cites a record path.
    """
    for field in ("paths", "names"):
        for pattern in _str_list(gate.get(field)):
            if any(config_glob_matches(pattern, probe) for probe in record["probes"]):
                return "%s %s %s" % (DECLARED_TAG, field, pattern)
    for directory in _str_list(gate.get("lists")):
        if lists_reach(directory, record):
            return "%s lists %s" % (DECLARED_TAG, directory)
    return None


def lock_id_lines(text: str) -> dict[str, int]:
    """{gate id: the line of its `"id"` key} in a gates.lock.json text, so declared-tier evidence is a `file:line` like every other tier's."""
    return {
        m.group(1): _line_of(text, m.start()) for m in re.finditer(r'"id"\s*:\s*"([^"]+)"', text)
    }


def derive_readers(
    gates: list[dict],
    records: list[dict],
    root: pathlib.Path,
    lock_lines: dict[str, int] | None = None,
) -> tuple[dict, int, int]:
    """({glob: {gate_id: evidence}}, gates scanned, files read). Evidence is `file:line (tier) token`, the first hit found.

    The `declared` tier is asked first, from the gate's own lock entry (`lock_lines` gives its line in LOCK_REL; line 1 when absent), and the file tiers only when it finds nothing. Files in NOT_SCAN_CODE are never read: their path strings are other gates' declarations, which the declared tier reads at their source.
    """
    lock_lines = lock_lines or {}
    derived: dict[str, dict[str, str]] = {r["glob"]: {} for r in records}
    texts: dict[pathlib.Path, str] = {}
    configs: dict = {}
    # ONE ANSWER PER (file, record). A shared module (rediacc_ci/log.py, the hook library) sits in hundreds of closures, and asking it the same question once per gate was this gate's whole cost once the record set grew.
    answers: dict[tuple[pathlib.Path, str], str | None] = {}
    scanned = 0
    for gate in gates:
        if gate.get("gate") is not True:
            continue
        # THIS GATE IS NOT ITS OWN READER. Its leaf cites the record globs in its docstring and selftest fixtures and reads only the policy, which is not a record path; left in, it flags itself as soon as it is registered (measured against a lock with it added: three findings). Skipped by its leaf, never by id, and said in the success line.
        if SELF_REL in (gate.get("leaves") or []):
            continue
        scanned += 1
        files = sorted(
            closure([leaf for leaf in gate.get("leaves") or [] if isinstance(leaf, str)], root)
        )
        for record in records:
            if gate["id"] in derived[record["glob"]]:
                continue
            hit = declared_hit(gate, record)
            if hit is not None:
                derived[record["glob"]][gate["id"]] = "%s:%d %s" % (
                    LOCK_REL,
                    lock_lines.get(gate["id"], 1),
                    hit,
                )
                continue
            for path in files:
                if path.suffix not in TEXT_SUFFIXES or _rel(path, root) in NOT_SCAN_CODE:
                    continue
                if path not in texts:
                    try:
                        texts[path] = path.read_text(encoding="utf-8", errors="replace")
                    except OSError:
                        texts[path] = ""
                key = (path, record["glob"])
                if key not in answers:
                    answers[key] = file_evidence(path, texts[path], record, root, configs)
                evidence = answers[key]
                if evidence is not None:
                    derived[record["glob"]][gate["id"]] = evidence
                    break
    return derived, scanned, len(texts)


def record_findings(
    records: list[dict], derived: dict, gate_ids: set[str], root: pathlib.Path
) -> list[str]:
    """Every way the policy and the derivation disagree. Empty means the reader lists are complete."""
    out: list[str] = []
    for rec in records:
        glob = rec["glob"]
        owners = {
            p: next((r["glob"] for r in records if covers(r, p)), None) for p in rec["probes"]
        }
        out.extend(
            "%s: probe %s is not covered by this record (covered by %s); a probe that misses its glob tests nothing"
            % (glob, p, owner)
            for p, owner in owners.items()
            if owner != glob
        )
        out.extend(
            "%s: %s is both a reader and a notReader; it is one or the other" % (glob, gate)
            for gate in sorted(set(rec["readers"]) & set(rec["notReaders"]))
        )
        out.extend(
            "%s: %s is not a `gate: true` entry of %s; a reader the runner cannot run blocks every advance"
            % (glob, gate, LOCK_REL)
            for gate in sorted(set(rec["readers"]) | set(rec["notReaders"]))
            if gate not in gate_ids
        )
        for gate, evidence in sorted(rec["readers"].items()):
            m = EVIDENCE_RE.match(evidence)
            if m is None:
                out.append(
                    "%s: reader %s has evidence %r, which does not start with file:line"
                    % (glob, gate, evidence)
                )
                continue
            target = root / m.group("file")
            try:
                lines = target.read_text(encoding="utf-8", errors="replace").count("\n") + 1
            except OSError:
                out.append(
                    "%s: reader %s cites %s, which does not exist" % (glob, gate, m.group("file"))
                )
                continue
            if int(m.group("line")) > lines:
                out.append(
                    "%s: reader %s cites %s:%s past the end of the file (%d lines)"
                    % (glob, gate, m.group("file"), m.group("line"), lines)
                )
        out.extend(
            "UNDECLARED READER %s reads %s: %s.\n"
            "    Add it to that record's `readers` in %s with file:line evidence, or to `notReaders` with the reason it\n"
            "    does not read those files. An undeclared reader is skipped by a receipt advance, and its verdict on the pushed tree is then one nobody computed."
            % (gate, glob, evidence, POLICY_REL)
            for gate, evidence in sorted(derived[glob].items())
            if gate not in rec["readers"] and gate not in rec["notReaders"]
        )
        out.extend(
            "%s: %s is exempt as a notReader but the derivation no longer flags it; delete the exemption"
            % (glob, gate)
            for gate in sorted(set(rec["notReaders"]) - set(derived[glob]))
        )
        # A notReader answers a file tier, which can mistake prose or another gate's data for a read. It cannot answer the declared tier: that is the gate's own traced input set, and a reason saying the gate does not read what it declares is a claim the trace contradicts. The fix is a narrower declaration in the gate's lock entry.
        out.extend(
            "%s: %s is exempt as a notReader, but its own lock entry declares an input that reaches this record (%s).\n"
            "    A notReader cannot overrule the gate's declared inputs: move it to `readers`, or narrow the declaration so it no longer reaches the record."
            % (glob, gate, derived[glob][gate])
            for gate in sorted(set(rec["notReaders"]) & set(derived[glob]))
            if DECLARED_TAG in derived[glob][gate]
        )
    return out


# ---------------------------------------------------------------- fixed widths

CORE_PROBES = ("cpu_count", "sched_getaffinity", "availableParallelism", "cpus(")
POOL_CALLS = frozenset({"ThreadPoolExecutor", "ProcessPoolExecutor", "Pool", "ThreadPool"})
WIDTH_KWARGS = frozenset({"max_workers", "processes", "workers", "n_jobs"})
WIDTH_NAME_RE = re.compile(
    r"^[A-Z0-9_]*(?:PARALLELISM|CONCURRENCY|WORKERS|JOBS_CAP|(?:COPY|FETCH|POOL|LANE|PROBE)_WIDTH)$"
)
FLAG_TAKES_WIDTH = frozenset({"-n", "--numprocesses", "-j", "--jobs", "-P", "--max-procs"})
PYTEST_MARKERS = ("--dist", "pytest", "xdist")
LINE_RULES = (
    ("xargs -P", re.compile(r"\bxargs\b[^|;\n]*?\s-P\s*(\d+)")),
    ("--jobs", re.compile(r"(?:^|\s)--jobs[= ](\d+)\b")),
    ("make -j", re.compile(r"\bmake\b[^|;\n]*\s-j\s*(\d+)")),
    ("pytest -n", re.compile(r"\bpytest\b[^|;\n]*\s(?:-n|--numprocesses)[= ]?(\d+)\b")),
    ("--maxWorkers", re.compile(r"--max-?[wW]orkers[= ](\d+)")),
    ("maxWorkers:", re.compile(r"\bmax(?:Workers|Forks|Threads)\s*:\s*(\d+)")),
    ("pLimit", re.compile(r"\bp[Ll]imit\(\s*(\d+)")),
    ("core cap", re.compile(r"Math\.min\(\s*(\d+)\s*,[^;\n]*(?:availableParallelism|cpus\(\))")),
    (
        "width const",
        re.compile(
            r"\b(?:const|let|var)\s+[A-Z0-9_]*(?:PARALLELISM|CONCURRENCY|WORKERS|JOBS_CAP)\s*=\s*(\d+)"
        ),
    ),
    ("GOMAXPROCS", re.compile(r"\bGOMAXPROCS\s*[=:]\s*['\"]?(\d+)")),
    ("RAYON_NUM_THREADS", re.compile(r"\bRAYON_NUM_THREADS\s*[=:]\s*['\"]?(\d+)")),
    ("--threads", re.compile(r"--threads[= ](\d+)\b")),
    ("--concurrency", re.compile(r"--concurrency[= ](\d+)\b")),
    ("go -p", re.compile(r"\bgo\s+(?:test|build|vet)\b[^|;\n]*\s-p\s*(\d+)")),
)
#: `:(glob)` IS LOAD-BEARING. A bare `packages/*/scripts` pathspec matched ZERO files when this gate was written (git reads a plain wildcard pathspec as a whole-path fnmatch, so it never matches a file below the directory), which would have left 79 scripts unswept and the gate green. `width_files` refuses a scope root that contributes nothing.
WIDTH_SCOPE = (
    ".ci",
    "scripts",
    ".github",
    ":(glob)packages/*/scripts/**",
    "package.json",
    ":(glob)packages/*/package.json",
)
LINE_SUFFIXES = (".sh", ".bash", ".yml", ".yaml", ".json", *TS_SUFFIXES)


def is_test_path(rel: str) -> bool:
    name = rel.rsplit("/", 1)[-1]
    return (
        "/tests/" in "/" + rel
        or "/test/" in "/" + rel
        or name.startswith(("test_", "test-"))
        or ".test." in name
        or ".spec." in name
        or "/goldens/" in rel
        or "/fixtures/" in rel
    )


def _int_of(node: ast.AST | None, consts: dict[str, int]) -> int | None:
    if (
        isinstance(node, ast.Constant)
        and isinstance(node.value, int)
        and not isinstance(node.value, bool)
    ):
        return node.value
    if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value.isdigit():
        return int(node.value)
    if isinstance(node, ast.Name):
        return consts.get(node.id)
    return None


def _mentions_cores(node: ast.AST) -> bool:
    return any(probe.rstrip("(") in ast.dump(node) for probe in CORE_PROBES)


def _core_cap(node: ast.AST, consts: dict[str, int]) -> int | None:
    """`min(8, os.cpu_count())` and its spellings: the literal cap, else None."""
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "min":
        literal = [v for v in (_int_of(a, consts) for a in node.args) if v is not None]
        if literal and any(_mentions_cores(a) for a in node.args):
            return max(literal)
    return None


def _segment(src: str, node: ast.AST) -> str:
    return " ".join((ast.get_source_segment(src, node) or "").split())


def python_widths(rel: str, src: str) -> list[dict]:
    """Fixed widths in one Python source, by AST, so a width in a comment or a docstring is never one."""
    try:
        tree = ast.parse(src)
    except (SyntaxError, ValueError):
        return []
    consts: dict[str, int] = {}
    for node in tree.body:
        # INTEGER CONSTANTS ONLY. A digit STRING bound to a width-shaped name is an identifier, not a count: `DEFAULT_VM_WORKERS = "11"` names worker VM 11 in the ops tests, and reading it as eleven workers was this sweep's first false positive.
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, int)
            and not isinstance(node.value.value, bool)
        ):
            consts[node.targets[0].id] = node.value.value
    out = []

    def add(kind: str, node: ast.AST, width: int) -> None:
        if width >= 2:
            out.append(
                {
                    "file": rel,
                    "line": getattr(node, "lineno", 0),
                    "kind": kind,
                    "width": width,
                    "match": _segment(src, node),
                }
            )

    for stmt in tree.body:
        if (
            isinstance(stmt, ast.Assign)
            and len(stmt.targets) == 1
            and isinstance(stmt.targets[0], ast.Name)
            and WIDTH_NAME_RE.match(stmt.targets[0].id)
            and stmt.targets[0].id in consts
        ):
            add("width const", stmt, consts[stmt.targets[0].id])
    named = {n for n, _ in consts.items() if WIDTH_NAME_RE.match(n)}
    for sub in ast.walk(tree):
        cap = _core_cap(sub, consts)
        if cap is not None:
            add("core cap", sub, cap)
            continue
        if isinstance(sub, ast.Call):
            func = (
                sub.func.attr
                if isinstance(sub.func, ast.Attribute)
                else getattr(sub.func, "id", "")
            )
            candidates = [kw.value for kw in sub.keywords if kw.arg in WIDTH_KWARGS]
            if func in POOL_CALLS and sub.args:
                candidates.append(sub.args[0])
            for value in candidates:
                # A width-named module constant is reported once, at its assignment, not again at each use.
                if isinstance(value, ast.Name) and value.id in named:
                    continue
                width = _int_of(value, consts)
                if width is not None:
                    add("pool width", sub, width)
        if isinstance(sub, (ast.List, ast.Tuple)):
            items = [
                e.value if isinstance(e, ast.Constant) and isinstance(e.value, str) else None
                for e in sub.elts
            ]
            pytesty = any(isinstance(s, str) and any(m in s for m in PYTEST_MARKERS) for s in items)
            for k, item in enumerate(items[:-1]):
                if item not in FLAG_TAKES_WIDTH:
                    continue
                if item in ("-n", "--numprocesses") and not pytesty:
                    continue
                if item in ("-P", "--max-procs") and "xargs" not in items:
                    continue
                width = _int_of(sub.elts[k + 1], {})
                if width is not None:
                    add("argv width", sub, width)
    return out


def line_widths(rel: str, src: str) -> list[dict]:
    """Fixed widths in a shell, YAML, JSON or TypeScript source, line by line, skipping comment lines."""
    out = []
    for n, line in enumerate(src.split("\n"), 1):
        bare = line.strip()
        if bare.startswith(("#", "//", "/*", "*")):
            continue
        for kind, rx in LINE_RULES:
            m = rx.search(line)
            if m and int(m.group(1)) >= 2:
                out.append(
                    {
                        "file": rel,
                        "line": n,
                        "kind": "core cap" if kind == "core cap" else kind,
                        "width": int(m.group(1)),
                        "match": " ".join(bare.split()),
                    }
                )
                break
    return out


def width_files(root: pathlib.Path) -> list[str]:
    proc = subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "ls-files",
            "--cached",
            "--others",
            "--exclude-standard",
            "--",
            *WIDTH_SCOPE,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise OSError("git ls-files failed in %s: %s" % (root, proc.stderr.strip()))
    listed = [p for p in proc.stdout.split("\n") if p]
    for spec in WIDTH_SCOPE:
        head = spec.removeprefix(":(glob)").split("*", 1)[0].rstrip("/")
        if not any(
            p == head or p.startswith(head + "/") or (head.endswith("/") and p.startswith(head))
            for p in listed
        ):
            raise OSError(
                "width scope %r matched no file; the sweep would skip it and stay green" % spec
            )
    # The two policy files quote the widths they list, so sweeping them would report every entry as its own unlisted width.
    return sorted(
        {
            p
            for p in listed
            if not is_test_path(p)
            and p not in NOT_SCAN_CONFIG
            and p.endswith((".py", *LINE_SUFFIXES))
        }
    )


def scan_widths(root: pathlib.Path, files: list[str]) -> list[dict]:
    found = []
    for rel in files:
        try:
            src = (root / rel).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        found.extend(python_widths(rel, src) if rel.endswith(".py") else line_widths(rel, src))
    return found


def parse_widths(doc: object) -> list[dict]:
    if not isinstance(doc, dict) or doc.get("version") != POLICY_VERSION:
        raise PolicyError('%s is not `"version": %d`' % (WIDTHS_REL, POLICY_VERSION))
    raw = doc.get("widths")
    if not isinstance(raw, list):
        raise PolicyError("%s has no `widths` list" % WIDTHS_REL)
    out = []
    for i, entry in enumerate(raw):
        keys = ("file", "match", "width", "kind", "limit", "reason")
        if not isinstance(entry, dict) or not all(k in entry for k in keys):
            raise PolicyError("%s entry %d needs %s" % (WIDTHS_REL, i, ", ".join(keys)))
        if entry["kind"] not in ("io", "fixture"):
            raise PolicyError(
                "%s entry %d: kind %r is not `io` or `fixture`; a core width is sized by the grant, never listed"
                % (WIDTHS_REL, i, entry["kind"])
            )
        if not isinstance(entry["reason"], str) or len(entry["reason"]) < 80:
            raise PolicyError(
                "%s entry %d (%s): a reason under 80 characters justifies nothing"
                % (WIDTHS_REL, i, entry["file"])
            )
        out.append(entry)
    return out


def _masked(match: str) -> str:
    return re.sub(r"\d+", "N", " ".join(match.split()))


def width_findings(found: list[dict], listed: list[dict]) -> list[str]:
    out = []
    # KEYED ON THE TEXT WITH ITS NUMBERS MASKED, so a renumbered width is a CHANGED finding naming both numbers rather than an unlisted one plus a stale one that look unrelated.
    by_key = {(e["file"], _masked(e["match"])): e for e in listed}
    seen = set()
    for f in found:
        key = (f["file"], _masked(f["match"]))
        entry = by_key.get(key)
        if f["kind"] == "core cap":
            out.append(
                "CORE CAP %s:%d caps a core count at %d: %s\n"
                "    Size it from the grant instead (Python `core_lease.granted_cores()`, TypeScript `grantedCores()`); a core cap is never an I/O width, so it cannot be listed."
                % (f["file"], f["line"], f["width"], f["match"])
            )
            seen.add(key)
            continue
        if entry is None:
            out.append(
                "UNLISTED WIDTH %s:%d fixes a parallel width of %d (%s): %s\n"
                "    A core width is sized by the grant. Only request concurrency against a remote API (or a fixture that needs an exact count) may stay fixed, listed in %s with its remote limit and reason."
                % (f["file"], f["line"], f["width"], f["kind"], f["match"], WIDTHS_REL)
            )
            continue
        seen.add(key)
        if entry["width"] != f["width"]:
            out.append(
                "CHANGED WIDTH %s:%d is now %d, listed as %d; re-justify the entry against its remote limit"
                % (f["file"], f["line"], f["width"], entry["width"])
            )
    for key, entry in sorted(by_key.items()):
        if key not in seen:
            out.append(
                "STALE WIDTH %s: the listed width %r is no longer in the file; delete the entry"
                % (entry["file"], entry["match"])
            )
    return out


# ---------------------------------------------------------------- selftest


SELFTEST_POLICY: dict[str, Any] = {
    "version": 1,
    "records": [
        {
            "glob": "agent/reviews/**",
            "except": [],
            "probes": [
                "agent/reviews/0101-1/clean.jsonl",
                "agent/reviews/0101-1/%s.md" % ("0" * 40),
            ],
            "readers": [{"id": "check:reader", "evidence": "gate_reader.py:1"}],
            "notReaders": [],
        },
        {
            "glob": "agent/worklist/*.jsonl",
            "except": ["agent/worklist/epics.jsonl"],
            "probes": ["agent/worklist/abcd1234.jsonl"],
            "readers": [],
            "notReaders": [],
        },
    ],
}


def _write(root: pathlib.Path, rel: str, text: str) -> None:
    target = root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def _derive_one(root: pathlib.Path, leaves: list[str], policy: dict) -> dict:
    records = parse_policy(policy)
    gates = [{"id": "check:probe", "gate": True, "leaves": leaves}]
    return derive_readers(gates, records, root)[0]


def selftest() -> int:
    """Every derivation tier and every width rule, planted and mirrored."""
    tally = controls.Controls("record paths", floor=CONTROL_FLOOR)

    # Globs: the rules the guard shares.
    tally.truthy(
        "glob ** spans directories", glob_re("agent/reviews/**").match("agent/reviews/a/b.md")
    )
    tally.falsy(
        "glob * stops at a slash",
        glob_re("agent/worklist/*.jsonl").match("agent/worklist/a/b.jsonl"),
    )
    tally.truthy("glob **/ matches zero directories", glob_re("**/x.md").match("x.md"))
    tally.check("literal prefix", literal_prefix("agent/worklist/*.jsonl"), "agent/worklist")
    tally.check(
        "a wildcard-free glob is its own prefix, not its directory",
        literal_prefix(".ci/config/carried-reds.json"),
        ".ci/config/carried-reds.json",
    )
    with tempfile.TemporaryDirectory(prefix="record-paths-literal-") as td:
        lit = pathlib.Path(td)
        _write(lit, "cites_file.py", 'P = ".ci/config/carried-reds.json"\n')
        _write(lit, "cites_sibling.py", 'P = ".ci/config/release-age.json"\n')
        lit_policy = {
            "version": POLICY_VERSION,
            "records": [
                {
                    "glob": ".ci/config/carried-reds.json",
                    "except": [],
                    "probes": [".ci/config/carried-reds.json"],
                    "readers": [],
                }
            ],
        }
        lit_derived = _derive_one(lit, ["cites_file.py"], lit_policy)
        tally.truthy(
            "a literal record: a gate citing the file reads it",
            lit_derived[".ci/config/carried-reds.json"],
        )
        lit_derived = _derive_one(lit, ["cites_sibling.py"], lit_policy)
        tally.falsy(
            "a literal record MIRROR: a gate citing only a sibling file does not read it",
            lit_derived[".ci/config/carried-reds.json"],
        )
    tally.truthy("basename config glob", config_glob_matches("*.md", "agent/reviews/a/b.md"))
    tally.falsy("basename config glob MIRROR", config_glob_matches("*.py", "agent/reviews/a/b.md"))

    with tempfile.TemporaryDirectory(prefix="record-paths-selftest-") as td:
        root = pathlib.Path(td)
        _write(root, "gate_reader.py", 'P = "agent/reviews/"\n')
        _write(root, "gate_clean.py", 'P = "docs/"\n')
        _write(root, "gate_epics.ts", "const L = 'agent/worklist/epics.jsonl';\n")
        _write(root, "gate_joined.ts", "const p = path.join(REPO, 'agent', 'reviews', branch);\n")
        _write(root, "gate_root.py", 'CORPUS = ["agent/", "docs/"]\n')
        _write(root, "gate_mdglob.ts", "const G = ['agent/**/*.{md,mdx}'];\n")
        _write(root, "gate_cfg.py", 'RULES = ".cfg/prose.json"\n')
        _write(root, ".cfg/prose.json", json.dumps({"include": ["*.md"], "exclude": ["!agent/**"]}))
        _write(root, "gate_cfg_py.py", 'RULES = ".cfg/code.json"\n')
        _write(root, ".cfg/code.json", json.dumps({"include": ["*.py"]}))
        _write(root, "gate_lsmd.py", 'FILES = git("ls-files", "--", "*.md")\n')
        _write(root, "gate_lock.py", 'L = "package-lock.json"\n')
        _write(
            root, "package-lock.json", json.dumps({"packages": {"": {"dependencies": {"x": "*"}}}})
        )
        _write(root, "gate_import.py", "import helper_mod\n")
        _write(root, "helper_mod.py", 'D = "agent/reviews"\n')
        _write(root, "gate_import.ts", "import { x } from './lib/helper';\n")
        _write(root, "lib/helper.ts", "export const x = 'agent/worklist/';\n")
        _write(
            root,
            "gate_legs.ts",
            "const LEGS = [{ label: 'a', args: ['scripts/leg_reader.ts', '--x'] }];\n",
        )
        _write(root, "scripts/leg_reader.ts", "const L = 'agent/worklist/';\n")
        _write(root, "gate_legs_cite.ts", "const NOTE = 'scripts/leg_reader.ts';\n")

        # THE PLANT the plan names: a leaf citing agent/reviews/ must be reported as an undeclared reader.
        planted = {"version": 1, "records": [dict(SELFTEST_POLICY["records"][0], readers=[])]}
        records = parse_policy(planted)
        gates = [{"id": "check:reader", "gate": True, "leaves": ["gate_reader.py"]}]
        derived = derive_readers(gates, records, root)[0]
        findings = record_findings(records, derived, {"check:reader"}, root)
        tally.truthy(
            "PLANT: a leaf citing agent/reviews/ is an UNDECLARED READER",
            any("UNDECLARED READER check:reader" in f for f in findings),
        )
        records = parse_policy(SELFTEST_POLICY)
        derived = derive_readers(gates, records, root)[0]
        tally.check(
            "MIRROR: the same leaf declared is clean",
            record_findings(records, derived, {"check:reader"}, root),
            [],
        )

        tally.check(
            "a leaf citing nothing reads nothing",
            _derive_one(root, ["gate_clean.py"], SELFTEST_POLICY),
            {g: {} for g in ("agent/reviews/**", "agent/worklist/*.jsonl")},
        )
        epics = _derive_one(root, ["gate_epics.ts"], SELFTEST_POLICY)
        tally.check(
            "an EXCLUDED path (epics.jsonl) is not a citation", epics["agent/worklist/*.jsonl"], {}
        )
        plant_src = plant(
            "const L = 'agent/worklist/epics.jsonl';\n", "epics.jsonl", "abcd1234.jsonl"
        )
        _write(root, "gate_epics2.ts", plant_src)
        tally.truthy(
            "MIRROR: a non-excluded worklist file is",
            "check:probe"
            in _derive_one(root, ["gate_epics2.ts"], SELFTEST_POLICY)["agent/worklist/*.jsonl"],
        )
        tally.truthy(
            "cite tier: joined segments",
            "check:probe"
            in _derive_one(root, ["gate_joined.ts"], SELFTEST_POLICY)["agent/reviews/**"],
        )
        root_d = _derive_one(root, ["gate_root.py"], SELFTEST_POLICY)
        tally.truthy(
            "root tier: an agent/ scan root reads every record under it",
            "(root)" in root_d["agent/reviews/**"].get("check:probe", "")
            and "check:probe" in root_d["agent/worklist/*.jsonl"],
        )
        md = _derive_one(root, ["gate_mdglob.ts"], SELFTEST_POLICY)
        tally.truthy(
            "glob tier: agent/**/*.{md,mdx} reads review .md records",
            "check:probe" in md["agent/reviews/**"],
        )
        tally.check(
            "glob tier MIRROR: and not .jsonl worklist records", md["agent/worklist/*.jsonl"], {}
        )
        cfg = _derive_one(root, ["gate_cfg.py"], SELFTEST_POLICY)
        tally.truthy(
            "config tier: *.md reaches a review .md probe",
            "(config)" in cfg["agent/reviews/**"].get("check:probe", ""),
        )
        tally.check(
            "config tier: *.md does not reach a .jsonl-only record",
            cfg["agent/worklist/*.jsonl"],
            {},
        )
        tally.check(
            "config tier MIRROR: *.py reaches nothing",
            _derive_one(root, ["gate_cfg_py.py"], SELFTEST_POLICY)["agent/reviews/**"],
            {},
        )
        tally.truthy(
            "glob tier: a '*.md' literal in code reaches a review .md",
            "(glob)"
            in _derive_one(root, ["gate_lsmd.py"], SELFTEST_POLICY)["agent/reviews/**"].get(
                "check:probe", ""
            ),
        )
        tally.check(
            "config tier: a lockfile's '*' version range is not a file glob",
            _derive_one(root, ["gate_lock.py"], SELFTEST_POLICY)["agent/reviews/**"],
            {},
        )
        tally.check(
            "brace expansion",
            expand_braces("agent/**/*.{md,mdx}"),
            ["agent/**/*.md", "agent/**/*.mdx"],
        )
        tally.falsy("a bare ** is not a file glob", is_path_glob("**"))
        tally.truthy(
            "closure: a Python import that cites is followed",
            "helper_mod.py"
            in _derive_one(root, ["gate_import.py"], SELFTEST_POLICY)["agent/reviews/**"].get(
                "check:probe", ""
            ),
        )
        tally.truthy(
            "closure: a TypeScript relative import is followed",
            "lib/helper.ts"
            in _derive_one(root, ["gate_import.ts"], SELFTEST_POLICY)["agent/worklist/*.jsonl"].get(
                "check:probe", ""
            ),
        )
        tally.truthy(
            "closure: a script a leaf spawns as a leg (`args: ['scripts/x.ts']`) is followed",
            "scripts/leg_reader.ts"
            in _derive_one(root, ["gate_legs.ts"], SELFTEST_POLICY)["agent/worklist/*.jsonl"].get(
                "check:probe", ""
            ),
        )
        tally.falsy(
            "closure MIRROR: the same path as a bare string, not a leg, is not followed",
            _derive_one(root, ["gate_legs_cite.ts"], SELFTEST_POLICY)["agent/worklist/*.jsonl"].get(
                "check:probe", ""
            ),
        )
        # CODE, NOT PROSE: each silent case below is the firing case with the citation moved into prose, so the silence is the rule's and not a broken fixture's.
        reviews = "agent/reviews/**"

        def reads(rel: str, text: str) -> bool:
            _write(root, rel, text)
            return "check:probe" in _derive_one(root, [rel], SELFTEST_POLICY)[reviews]

        tally.truthy(
            "cite: a path that is a whole literal is read",
            reads("gate_open.py", 'F = open("agent/reviews/x.md")\n'),
        )
        tally.falsy(
            "cite MIRROR: the same path in a module docstring is not",
            reads(
                "gate_doc.py",
                '"""Reads nothing; see agent/reviews/x.md and "agent/reviews/"."""\nX = 1\n',
            ),
        )
        tally.falsy(
            "cite MIRROR: nor in a function docstring or a # comment",
            reads(
                "gate_fn.py",
                'def f():\n    """Like open("agent/reviews/x.md")."""\n    return 1  # "agent/reviews/"\n',
            ),
        )
        tally.falsy(
            "cite MIRROR: nor in a message string with spaces",
            reads("gate_msg.py", 'MSG = "see agent/reviews/x.md for the record"\n'),
        )
        tally.truthy(
            "cite: joined with `/` is read",
            reads("gate_div.py", 'D = ROOT / "agent" / "reviews"\n'),
        )
        tally.truthy(
            "cite: a file that does not tokenise is read WHOLE, docstring included",
            reads("gate_broken.py", '"""agent/reviews/x.md is "agent/reviews/"."""\nX = (\n'),
        )
        tally.truthy(
            "cite: a TypeScript template literal is read",
            reads("gate_tpl.ts", "const p = `${root}/agent/reviews/${branch}`;\n"),
        )
        tally.falsy(
            "cite MIRROR: a TypeScript block comment and a // line are not",
            reads(
                "gate_cmt.ts",
                "/**\n * Reads 'agent/reviews/' never.\n */\n// 'agent/reviews/'\nexport const x = 1;\n",
            ),
        )
        tally.truthy(
            "cite: code after a block comment closes on its own line is still read",
            reads("gate_after.ts", "/* why */ export const p = 'agent/reviews/';\n"),
        )
        tally.truthy(
            "cite: a block comment that never closes blanks nothing",
            reads("gate_open.ts", "/* unterminated\nexport const p = 'agent/reviews/';\n"),
        )
        tally.truthy(
            "cite: an apostrophe earlier on the line does not hide a literal",
            reads("gate_apos.ts", "const r = /'/.test(s) ? 'agent/reviews/x' : '';\n"),
        )
        tally.truthy(
            "cite: a shell script reads an unquoted path",
            reads("gate_ls.sh", "#!/bin/bash\nls agent/reviews/main\n"),
        )
        tally.falsy(
            "cite MIRROR: a shell # comment does not",
            reads("gate_cmt.sh", "#!/bin/bash\n# ls agent/reviews/main\ntrue\n"),
        )
        _write(root, ".cfg/excl.json", json.dumps({"literalExclude": [{"glob": "agent/**"}]}))
        tally.falsy(
            "config: a glob under an exclusion key is not a scope",
            reads("gate_excl.py", 'PINS = ".cfg/excl.json"\n'),
        )
        _write(root, ".cfg/incl.json", json.dumps({"literalInclude": [{"glob": "agent/**"}]}))
        tally.truthy(
            "config MIRROR: the same glob under an inclusion key is",
            reads("gate_incl.py", 'PINS = ".cfg/incl.json"\n'),
        )
        _write(root, ".ci/cache/seen.json", json.dumps({"paths": ["agent/**"]}))
        tally.falsy(
            "config: a file under .ci/cache/ is never a scanner's scope",
            reads("gate_cache.ts", "const R = '.ci/cache/seen.json';\n"),
        )
        tally.raises(
            'a `review` value other than "keep" is a policy error',
            PolicyError,
            parse_policy,
            {"version": 1, "records": [dict(SELFTEST_POLICY["records"][0], review="skip")]},
        )
        tally.truthy(
            'MIRROR: `"review": "keep"` parses',
            parse_policy(
                {"version": 1, "records": [dict(SELFTEST_POLICY["records"][0], review="keep")]}
            ),
        )

        _write(root, SELF_REL, 'P = "agent/reviews/"\n')
        self_gates = [{"id": "check:ci-record-paths", "gate": True, "leaves": [SELF_REL]}]
        tally.check(
            "this gate's own leaf is not derived as a reader",
            derive_readers(self_gates, parse_policy(SELFTEST_POLICY), root)[0]["agent/reviews/**"],
            {},
        )
        tally.truthy(
            "MIRROR: the same text under another leaf is",
            "check:probe"
            in _derive_one(root, ["gate_reader.py"], SELFTEST_POLICY)["agent/reviews/**"],
        )
        tally.check(
            "a tool leaf (not a file) reads nothing and does not crash",
            _derive_one(root, ["biome"], SELFTEST_POLICY)["agent/reviews/**"],
            {},
        )

        # THE DECLARED TIER (PLAN-push-decoupling F1): the gate's own lock entry, read with a leaf that cites nothing, so every hit below is the declaration's.
        def declared(**entry: Any) -> dict:
            gate = dict({"id": "check:probe", "gate": True, "leaves": ["gate_clean.py"]}, **entry)
            records = parse_policy(SELFTEST_POLICY)
            return derive_readers([gate], records, root, {"check:probe": 7})[0]

        star = declared(names=["**"])
        tally.check(
            "declared: names ['**'] reads every record, with lock file:line evidence",
            [star[g].get("check:probe") for g in ("agent/reviews/**", "agent/worklist/*.jsonl")],
            ["%s:7 (declared) names **" % LOCK_REL] * 2,
        )
        tally.check(
            "declared MIRROR: names narrowed to **/*.sh reads neither",
            declared(names=["**/*.sh"]),
            {g: {} for g in ("agent/reviews/**", "agent/worklist/*.jsonl")},
        )
        narrowed = declared(paths=["agent/reviews/**", "docs/**"])
        tally.truthy(
            "declared: a paths glob matching a probe reads that record",
            "check:probe" in narrowed["agent/reviews/**"],
        )
        tally.check(
            "declared MIRROR: and not a record none of whose probes it matches",
            narrowed["agent/worklist/*.jsonl"],
            {},
        )
        tally.truthy(
            "declared: lists the parent of the prefix (agent) reads agent/reviews/**",
            "check:probe" in declared(lists=["agent"])["agent/reviews/**"],
        )
        tally.truthy(
            "declared: lists a directory inside the prefix reads it",
            "check:probe" in declared(lists=["agent/reviews/0101-1"])["agent/reviews/**"],
        )
        tally.check(
            "declared MIRROR: lists '' (the root), a sibling and a look-alike read nothing",
            declared(lists=["", "agent/plans", "agent/reviewsx"])["agent/reviews/**"],
            {},
        )
        tally.truthy(
            "declared: lists the parent of a literal record reads it",
            lists_reach(".ci/config", {"glob": ".ci/config/carried-reds.json"}),
        )
        tally.falsy(
            "declared MIRROR: lists a grandparent of a literal record does not",
            lists_reach(".ci", {"glob": ".ci/config/carried-reds.json"}),
        )
        exempt_star = json.loads(json.dumps(SELFTEST_POLICY))
        exempt_star["records"][0]["notReaders"] = [{"id": "check:probe", "reason": "says no"}]
        tally.truthy(
            "declared: a notReader cannot overrule a declared hit",
            any(
                "cannot overrule" in f
                for f in record_findings(parse_policy(exempt_star), star, {"check:probe"}, root)
            ),
        )
        # NOT SCAN CODE: the gate table holds other gates' globs as data. The same text in any other imported file still makes a reader, so the silence is the set's.
        table = "export const M = [{ id: 'x', paths: ['agent/reviews/**'] }];\n"
        _write(root, "scripts/ci-runner/manifest.ts", table)
        _write(root, "scripts/ci-runner/trace-ledger.ts", table)
        _write(root, "scripts/ci-runner/elsewhere.ts", table)
        _write(root, "gate_table.ts", "import { M } from './scripts/ci-runner/manifest';\n")
        _write(root, "gate_ledger.ts", "import { M } from './scripts/ci-runner/trace-ledger';\n")
        _write(root, "gate_elsewhere.ts", "import { M } from './scripts/ci-runner/elsewhere';\n")
        tally.check(
            "not scan code: a record glob only inside manifest.ts or trace-ledger.ts reads nothing",
            [
                _derive_one(root, [leaf], SELFTEST_POLICY)["agent/reviews/**"]
                for leaf in ("gate_table.ts", "gate_ledger.ts")
            ],
            [{}, {}],
        )
        tally.truthy(
            "not scan code MIRROR: the same text in another imported file reads the record",
            "check:probe"
            in _derive_one(root, ["gate_elsewhere.ts"], SELFTEST_POLICY)["agent/reviews/**"],
        )

        # Policy-side findings.
        stale = json.loads(json.dumps(SELFTEST_POLICY))
        stale["records"][0]["notReaders"] = [
            {"id": "check:gone", "reason": "it used to be flagged and no longer is"}
        ]
        recs = parse_policy(stale)
        tally.truthy(
            "a STALE notReader is reported",
            any(
                "check:gone is exempt" in f
                for f in record_findings(recs, derived, {"check:reader", "check:gone"}, root)
            ),
        )
        tally.truthy(
            "an unknown reader id is reported",
            any(
                "not a `gate: true` entry" in f
                for f in record_findings(records, derived, set(), root)
            ),
        )
        bad_ev = json.loads(json.dumps(SELFTEST_POLICY))
        bad_ev["records"][0]["readers"] = [{"id": "check:reader", "evidence": "gate_reader.py:99"}]
        tally.truthy(
            "evidence past the end of its file is reported",
            any(
                "past the end" in f
                for f in record_findings(parse_policy(bad_ev), derived, {"check:reader"}, root)
            ),
        )
        bad_probe = json.loads(json.dumps(SELFTEST_POLICY))
        bad_probe["records"][1]["probes"] = ["agent/worklist/epics.jsonl"]
        tally.truthy(
            "a probe its own record excludes is reported",
            any(
                "probe agent/worklist/epics.jsonl" in f
                for f in record_findings(parse_policy(bad_probe), derived, {"check:reader"}, root)
            ),
        )
        tally.raises(
            "an empty records list is a policy error, never zero findings",
            PolicyError,
            parse_policy,
            {"version": 1, "records": []},
        )
        tally.raises(
            "a record with no probes is a policy error",
            PolicyError,
            parse_policy,
            {"version": 1, "records": [{"glob": "a/**", "readers": []}]},
        )
        tally.raises(
            "a `?` glob is a policy error (the runner reads it differently)",
            PolicyError,
            parse_policy,
            {
                "version": 1,
                "records": [dict(SELFTEST_POLICY["records"][0], glob="agent/review?/**")],
            },
        )
        tally.raises(
            "a reader map (not a list of {id}) is a policy error",
            PolicyError,
            parse_policy,
            {
                "version": 1,
                "records": [dict(SELFTEST_POLICY["records"][0], readers={"check:reader": "x:1"})],
            },
        )

    # Fixed widths.
    py_clean = "import os\nfrom concurrent.futures import ThreadPoolExecutor\nwith ThreadPoolExecutor(max_workers=granted_cores()) as p:\n    pass\n"
    tally.check("width: a grant-sized pool is no finding", python_widths("a.py", py_clean), [])
    py_lit = plant(py_clean, "max_workers=granted_cores()", "max_workers=6")
    tally.check(
        "width PLANT: max_workers=6 is found",
        [(f["kind"], f["width"]) for f in python_widths("a.py", py_lit)],
        [("pool width", 6)],
    )
    py_const = "FETCH_PARALLELISM = 8\nwith ThreadPoolExecutor(FETCH_PARALLELISM) as p:\n    pass\n"
    tally.check(
        "width: a width-named constant is found once, at its assignment",
        [(f["kind"], f["match"]) for f in python_widths("a.py", py_const)],
        [("width const", "FETCH_PARALLELISM = 8")],
    )
    py_cap = "import os\nJ = min(8, os.cpu_count() or 1)\n"
    tally.check(
        "width: min(8, cpu_count()) is a core cap",
        [f["kind"] for f in python_widths("a.py", py_cap)],
        ["core cap"],
    )
    tally.check(
        "width: a docstring naming -n 8 is not a width",
        python_widths("a.py", '"""runs pytest -n 8"""\n'),
        [],
    )
    tally.check(
        "width: pytest argv -n 2 with --dist is found",
        [f["width"] for f in python_widths("a.py", 'A = ["-n", "2", "--dist", "loadgroup"]\n')],
        [2],
    )
    tally.check(
        "width: a digit STRING under a width name is an identifier",
        python_widths("a.py", 'DEFAULT_VM_WORKERS = "11"\n'),
        [],
    )
    tally.check(
        "args: --update is refused by name",
        "'--update'" in parse_args(["--update"])[2],
        True,
    )
    tally.check(
        "args: a valued flag with no path is refused",
        "--lock needs a path" in parse_args(["--records-only", "--lock"])[2],
        True,
    )
    tally.check(
        "args: the known flags parse",
        parse_args(["--records-only", "--policy", "p.json"]),
        ({"--records-only"}, {"--policy": "p.json"}, ""),
    )
    tally.check("width: jq -n is not a width", python_widths("a.py", 'A = ["jq", "-n", "2"]\n'), [])
    tally.check(
        "width: width 1 (serial) is not a width",
        python_widths("a.py", "with ThreadPoolExecutor(max_workers=1) as p:\n    pass\n"),
        [],
    )
    tally.check(
        "width: xargs -P 8 in shell is found",
        [f["kind"] for f in line_widths("a.sh", "find . | xargs -P 8 -I{} cp {} x\n")],
        ["xargs -P"],
    )
    tally.check(
        "width: a commented xargs -P 8 is not",
        line_widths("a.sh", "# xargs -P 8 was the old width\n"),
        [],
    )
    tally.check(
        "width: tail -n 80 is not a width", line_widths("a.yml", "  run: tail -n 80 log\n"), []
    )
    tally.check(
        "width: --jobs 1 is serial, not a width",
        line_widths("a.yml", "  run: run.ts --jobs 1\n"),
        [],
    )
    tally.check(
        "width: a TS core cap is found",
        [
            f["kind"]
            for f in line_widths(
                "a.ts", "const w = Math.max(1, Math.min(8, os.availableParallelism() - 1));\n"
            )
        ],
        ["core cap"],
    )
    tally.check(
        "width: a TS CONCURRENCY const is found",
        [f["width"] for f in line_widths("a.ts", "const PROBE_CONCURRENCY = 4;\n")],
        [4],
    )
    found = python_widths("a.py", py_const)
    listed = [
        {
            "file": "a.py",
            "match": "FETCH_PARALLELISM = 8",
            "width": 8,
            "kind": "io",
            "limit": "x",
            "reason": "r" * 80,
        }
    ]
    tally.check("width MIRROR: a listed io width is clean", width_findings(found, listed), [])
    tally.truthy(
        "width: an unlisted width is reported",
        any(f.startswith("UNLISTED WIDTH") for f in width_findings(found, [])),
    )
    tally.truthy(
        "width: a listed width that is gone is STALE",
        any(f.startswith("STALE WIDTH") for f in width_findings([], listed)),
    )
    tally.truthy(
        "width: a changed number is reported",
        any(
            f.startswith("CHANGED WIDTH")
            for f in width_findings(python_widths("a.py", plant(py_const, "= 8", "= 9")), listed)
        ),
    )
    cap_listed = [
        {
            "file": "a.py",
            "match": "min(8, os.cpu_count() or 1)",
            "width": 8,
            "kind": "io",
            "limit": "x",
            "reason": "r" * 80,
        }
    ]
    tally.truthy(
        "width: a core cap is refused even when listed",
        any(
            f.startswith("CORE CAP")
            for f in width_findings(python_widths("a.py", py_cap), cap_listed)
        ),
    )
    tally.raises(
        "width: kind `cores` cannot be listed",
        PolicyError,
        parse_widths,
        {"version": 1, "widths": [dict(listed[0], kind="cores")]},
    )
    tally.raises(
        "width: a short reason cannot be listed",
        PolicyError,
        parse_widths,
        {"version": 1, "widths": [dict(listed[0], reason="known")]},
    )
    tally.truthy(
        "width: a test path is out of scope",
        is_test_path(".ci/rediacc_ci/tests/test_x.py") and not is_test_path(".ci/rediacc_ci/x.py"),
    )
    return 0 if tally.report() else 2


# ---------------------------------------------------------------- main


def _load_json(path: pathlib.Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def run_records(root: pathlib.Path, policy_path: pathlib.Path, lock_path: pathlib.Path) -> int:
    try:
        records = parse_policy(_load_json(policy_path))
        lock_text = lock_path.read_text(encoding="utf-8")
        gates = json.loads(lock_text)
    except (OSError, ValueError) as exc:
        print("record-paths: cannot read its inputs: %s" % exc, file=sys.stderr)
        return 2
    if not isinstance(gates, list) or not gates:
        print(
            "record-paths: %s lists no gates; the derivation would see nothing and its green would mean nothing"
            % LOCK_REL,
            file=sys.stderr,
        )
        return 2
    gate_ids = {
        g["id"]
        for g in gates
        if isinstance(g, dict) and g.get("gate") is True and isinstance(g.get("id"), str)
    }
    derived, scanned, read = derive_readers(
        [g for g in gates if isinstance(g, dict)], records, root, lock_id_lines(lock_text)
    )
    if scanned == 0 or read == 0:
        print(
            "record-paths: scanned %d gate(s) and read %d file(s); the gate is not seeing the tree"
            % (scanned, read),
            file=sys.stderr,
        )
        return 2
    findings = record_findings(records, derived, gate_ids, root)
    declared = sum(len(r["readers"]) for r in records)
    hand = sorted(
        "%s <- %s" % (r["glob"], g)
        for r in records
        for g in r["readers"]
        if g not in derived[r["glob"]]
    )
    exempt = sorted(
        "%s <- %s: %s" % (r["glob"], g, why) for r in records for g, why in r["notReaders"].items()
    )
    for line in hand:
        print("  declared beyond the derivation: %s" % line)
    for line in exempt:
        print("  exempt by name (notReaders): %s" % line)
    if findings:
        for f in findings:
            print("::error::%s" % f, file=sys.stderr)
        print(
            "record-paths: %d finding(s) over %d record glob(s), %d gate(s) scanned"
            % (len(findings), len(records), scanned),
            file=sys.stderr,
        )
        return 1
    print(
        "record-paths: OK (this gate's own leaf excluded), %d record glob(s), %d gate(s) scanned (%d files in their import closures), %d reader declaration(s) (%d derived, %d of them through the declared tier, %d beyond the derivation), %d exempt by name"
        % (
            len(records),
            scanned,
            read,
            declared,
            sum(len(d) for d in derived.values()) - len(exempt),
            sum(DECLARED_TAG in ev for d in derived.values() for ev in d.values()),
            len(hand),
            len(exempt),
        )
    )
    return 0


def run_widths(root: pathlib.Path, widths_path: pathlib.Path) -> int:
    try:
        listed = parse_widths(_load_json(widths_path))
        files = width_files(root)
    except (OSError, ValueError) as exc:
        print("fixed-widths: cannot read its inputs: %s" % exc, file=sys.stderr)
        return 2
    if not files:
        print(
            "fixed-widths: zero files in scope (%s); the sweep is not seeing the tree"
            % ", ".join(WIDTH_SCOPE),
            file=sys.stderr,
        )
        return 2
    found = scan_widths(root, files)
    findings = width_findings(found, listed)
    for entry in listed:
        print(
            "  listed %s width %d: %s | %s (limit: %s)"
            % (entry["kind"], entry["width"], entry["file"], entry["match"], entry["limit"])
        )
    if findings:
        for f in findings:
            print("::error::%s" % f, file=sys.stderr)
        print(
            "fixed-widths: %d finding(s) over %d file(s), %d width site(s) found, %d listed"
            % (len(findings), len(files), len(found), len(listed)),
            file=sys.stderr,
        )
        return 1
    print(
        "fixed-widths: OK, %d file(s) swept, %d fixed width site(s), all listed (%d io, %d fixture)"
        % (
            len(files),
            len(found),
            sum(e["kind"] == "io" for e in listed),
            sum(e["kind"] == "fixture" for e in listed),
        )
    )
    return 0


# Every argument this gate takes. Anything else is a usage error (rc 2), never ignored: `npm run check:ci-record-paths -- --update` once exited 0 having done nothing, since the gate has no --update.
SWITCHES = ("--selftest", "--records-only", "--widths-only")
VALUED = ("--policy", "--lock", "--widths")


def parse_args(argv: list[str]) -> tuple[set[str], dict[str, str], str]:
    """`(switches, values, problem)`: the switches present, each valued flag mapped to its value, and `problem` names the first unknown argument or valued flag with no value, "" when the arguments parse."""
    accepted = "accepted: %s, and %s <path>" % (", ".join(SWITCHES), " <path>, ".join(VALUED))
    switches: set[str] = set()
    values: dict[str, str] = {}
    k = 0
    while k < len(argv):
        arg = argv[k]
        if arg in SWITCHES:
            switches.add(arg)
        elif arg in VALUED:
            if k + 1 >= len(argv) or argv[k + 1].startswith("--"):
                return switches, values, "%s needs a path (%s)" % (arg, accepted)
            k += 1
            values[arg] = argv[k]
        else:
            return switches, values, "unknown argument %r (%s)" % (arg, accepted)
        k += 1
    return switches, values, ""


def main(argv: list[str]) -> int:
    switches, values, problem = parse_args(argv)
    if problem:
        print("record-paths: %s" % problem, file=sys.stderr)
        return 2
    if "--selftest" in switches:
        return selftest()
    # CONTROLS FIRST, every run: for a `.py` gate the registry runs the bare path (scripts/lib/gate-header.ts `derivedRun`), so a `--selftest &&` leg in package.json is not where the controls live. An instrument that cannot fire exits 2 before it judges the tree.
    if selftest() != 0:
        print(
            "record-paths: the controls failed, so this gate's verdict would mean nothing",
            file=sys.stderr,
        )
        return 2
    root = paths.repo_root()
    # `--policy`, `--lock` and `--widths` exist for the gate test's real-tree controls, which plant into COPIES of these files rather than into the shared tree.
    policy_path = pathlib.Path(values.get("--policy") or root / POLICY_REL)
    lock_path = pathlib.Path(values.get("--lock") or root / LOCK_REL)
    widths_path = pathlib.Path(values.get("--widths") or root / WIDTHS_REL)
    rc_records = 0 if "--widths-only" in switches else run_records(root, policy_path, lock_path)
    rc_widths = 0 if "--records-only" in switches else run_widths(root, widths_path)
    return max(rc_records, rc_widths)


if __name__ == "__main__":
    from rediacc_ci.quality import gate_args

    gate_args.parse("check_record_paths.py", sys.argv[1:], switches=SWITCHES, valued=VALUED)
    sys.exit(main(sys.argv[1:]))
