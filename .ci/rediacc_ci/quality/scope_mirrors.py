r"""check:ci-scope-mirrors: CLAUDE.md's PR-scope rules and their hand-written mirrors agree.

WHY THIS EXISTS (agent/plans/PLAN-scope-mirrors.md). CLAUDE.md is the one place the PR-scope rules are written down, and at least seven other files restate them in their own words: the output style, the pr-epics skill, /pr-babysit, /pr-merge, the pr-babysitter agent, the `MESSAGE` of `block_settled_questions.py` and the QUEUE.md header. Those copies are what an agent actually reads mid-task. Commit 8ed69711c copied one sentence into
six places by hand; earlier changes missed copies, and nothing checked that the copies agree.

THE CONTRACT (plan D1). The canonical text stays CLAUDE.md prose, wrapped inline:

    <!-- scope: pr.turbo-batch-end -->Under `turbo: on` ... fires.<!-- /scope -->

  * Open `<!-- scope: <id>[ -- <note>] -->`, close `<!-- /scope -->`.
  * Ids match `^pr\.[a-z0-9-]{3,40}$`. A comment that starts `scope` but carries a malformed id is a FINDING (C1 in CLAUDE.md, C10 in a mirror), never ignored.
  * In CLAUDE.md the close is REQUIRED, every registered id is opened exactly once, and spans do not nest.
  * In a mirror the close is optional. With no close the span runs to the end of its BLOCK (a paragraph, a list item, a heading or a table row). With a close it runs to that close, which may cross list items but not a blank line; a later open in another block ends an earlier closeless span at the end of its own block, so one close never stretches an unrelated anchor.
  * An anchor inside a backtick code span or a fenced block is prose, not an anchor, so a document that DESCRIBES the syntax does not trip the gate (TRAPS `detector-matches-its-own-prose`).

THE REGISTRY, `.ci/config/scope-mirrors.json` (plan D3):

    {
      "canonical": "CLAUDE.md",                         optional, this default
      "floors": {"clauses": 9, "mirror_checks": 25},    REQUIRED, each >= 1
      "quote_sources": [{"path": "...", "where": "py:MESSAGE"}],
      "clauses": {
        "pr.<id>": {
          "sha": "<sha256[:12] of the normalized canonical span>",
          "atoms": ["...", ...],          each a normalized substring of the span
          "sentinels": ["...", ...],      distinctive atoms the C9 sweep looks for
          "oracle": {"path": "...", "const": "NAME",
                     "rule": "all-in-span" | "equal-backticked"},   optional
          "mirrors": [{"path": "...", "mode": "verbatim" | "terms" | "ref",
                       "where": "frontmatter:<key>" | "py:<CONST>"}]   where optional
        }
      }
    }

  `where` missing means inline anchors in a markdown mirror; EVERY anchor of that id in that file is a span and each is judged. `frontmatter:<key>` reads a YAML front-matter key, where a comment would land inside the string. `py:<CONST>` reads a module-level string constant through `ast`, never by import. A `quote_sources` entry with no `where` quotes the whole file. The floors live in the
  registry so the first registry can list only the mirrors not blocked by other writers; a floor below 1 is refused, because a floor of 0 is a floor that cannot fail.

NORMALIZATION (plan D4), in this order: strip HTML comments, drop `**` and `__`, drop backticks keeping their contents, fold smart quotes, dashes and the ellipsis character to ASCII, collapse whitespace, casefold. Modes: `verbatim` (the normalized canonical span is a substring of the normalized mirror span), `terms` (every atom is), `ref` (the span names CLAUDE.md or another registered mirror path
instead of restating; the success line counts these so the exemption stays visible).

CHECKS (plan D5). Only C5, C6, C7 and C9 are baselinable.

  C0  floors and registry shape; every clause has a mirror or an oracle; zero corpus files is a failure
  C1  canonical anchors: each id opened and closed exactly once, no unknown id, no nesting, no stray close
  C2  pin: sha(canonical span) == registry sha, else the mirrors are listed with the repin command
  C3  every atom and sentinel is a substring of its canonical span; a `terms` mirror needs >= 1 atom
  C4  a mirror or quote source that cannot be located (file, anchor, front-matter key, constant) is red, never skipped
  C5  verbatim; C6 terms and ref
  C7  every double-quoted fragment of a quote source, split on `...`, `[...]` and the ellipsis character, trailing `.,;:` stripped, is a substring of normalized CLAUDE.md outside its gen-docs regions; a source with zero fragments is red
  C8  code oracle: `all-in-span` (every constant value is in the span) or `equal-backticked` (the backticked snake_case tokens of the span equal the constant's set)
  C9  a sentinel in a corpus block that carries no registered span or anchor for that clause
  C10 an anchor in a mirror whose (path, id) pair is not registered, or whose id is malformed

  While a clause is red on C2 its C5/C6 are not judged: the C2 message lists the mirrors, and judging them against an unpinned canonical would bury the one action that matters (re-read them, then repin).

SHRINK-ONLY BASELINE, `.ci/config/scope-mirrors-baseline.json`: `{"findings": [<id>, ...]}` (other keys are kept on rewrite). Ids are `<path>:<clause>:<check>:<sha8 of the normalized offending span>`, keyed on TEXT, never on a line number. The decision is `rediacc_ci.quality.shrink_only` (`baseline_additions`, `write_verdict`): `--write-baseline` refuses growth, `--first-seed` is honoured only while no
baseline exists, and a baselined finding that has been fixed is red until drained. A missing baseline reads as empty on a check run, which is strictly stricter.

`--repin <id>|--all` (plan D6) writes the sha only when every mirror of each target clause passes C3-C6 and C8 against the CURRENT canonical (a baselined C5/C6 finding does not block), and prints the backticked tokens of the new span that are not atoms so a new code token is a reviewed choice. All targets or none are written. There is no `--force` (`scripts/lib/shrink-only-baseline.ts:30-33`).

BLIND SPOTS (plan D9), also printed on every green:
  * A mirror that ADDS an exception the canonical lacks, or contradicts it while still carrying every atom, passes `terms`.
  * C8 reads constant tuples only; behaviour in a function body is outside it.
  * C9 sees only its corpus, and skips fenced blocks (config examples, not restatements).

Exit codes: 0 clean, 1 finding or refused write, 2 broken controls or usage error.
"""

from __future__ import annotations

import ast
import contextlib
import dataclasses
import hashlib
import io
import json
import pathlib
import re
import sys
import tempfile

from rediacc_ci import paths
from rediacc_ci.controls import Controls, controls_first, plant
from rediacc_ci.quality.shrink_only import baseline_additions, write_verdict

REGISTRY_REL = ".ci/config/scope-mirrors.json"
BASELINE_REL = ".ci/config/scope-mirrors-baseline.json"
ENTRY_REL = ".ci/scripts/quality/check_scope_mirrors.py"
DEFAULT_CANONICAL = "CLAUDE.md"

ID_RE = re.compile(r"^pr\.[a-z0-9-]{3,40}$")
WHERE_RE = re.compile(r"^(frontmatter:[A-Za-z_][\w-]*|py:[A-Za-z_]\w*)$")
MODES = ("verbatim", "terms", "ref")
ORACLE_RULES = ("all-in-span", "equal-backticked")
BASELINABLE = ("C5", "C6", "C7", "C9")

# C9's corpus (plan D5). Fixed in code, not in the registry: a corpus the registry could shrink is a sweep the registry could switch off. The bool marks a recursive glob.
CORPUS_GLOBS = (
    ("CLAUDE.md", False),
    (".claude/commands/*.md", False),
    (".claude/agents/*.md", False),
    (".claude/output-styles/*.md", False),
    (".claude/skills/**/*.md", True),
    ("agent/plans/QUEUE.md", False),
)

GEN_DOCS_RE = re.compile(r"<!-- >>> gen-docs:.*?<!-- <<< gen-docs -->", re.DOTALL)
COMMENT_RE = re.compile(r"<!--(.*?)-->", re.DOTALL)
FENCE_RE = re.compile(r"^\s{0,3}(`{3,}|~{3,})")
ITEM_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
INDENT_CODE_RE = re.compile(r"^(?: {4}|\t)")
HEADING_RE = re.compile(r"^\s{0,3}#{1,6}(?:\s|$)")
TABLE_RE = re.compile(r"^\s*\|")
FRONT_KEY_RE = re.compile(r"^([A-Za-z_][\w-]*)\s*:")
CODE_SPAN_RE = re.compile(r"(?<!`)(`+)(?!`)(.+?)(?<!`)\1(?!`)", re.DOTALL)
BACKTICKED_RE = re.compile(r"`([^`\n]+)`")
SNAKE_RE = re.compile(r"^[a-z][a-z0-9_]*$")
ELLIPSIS_RE = re.compile(r"\[\.\.\.\]|\.\.\.")

# Folded by `normalize`. Built with chr() so the source stays ASCII: the house rule bans the em dash character from authored text, and this table must still name it.
FOLD = {
    chr(0x2018): "'",  # left single quote
    chr(0x2019): "'",  # right single quote
    chr(0x201A): "'",  # low single quote
    chr(0x201B): "'",  # reversed single quote
    chr(0x201C): '"',  # left double quote
    chr(0x201D): '"',  # right double quote
    chr(0x201E): '"',  # low double quote
    chr(0x2013): "-",  # en dash
    chr(0x2014): "--",  # em dash
    chr(0x2212): "-",  # minus sign
    chr(0x2026): "...",  # ellipsis character
    chr(0x00A0): " ",  # no-break space
}
FOLD_TABLE = str.maketrans(FOLD)

CROSS = chr(0x2717)  # the red mark, as trap_registry prints it
TICK = chr(0x2713)  # the green mark

BLIND_SPOTS = (
    "Blind: a mirror that adds an exception or contradicts the canonical while carrying every "
    "atom passes terms; C8 reads constants only; C9 sees its corpus outside fences only."
)


# --------------------------------------------------------------------------- text


def normalize(text: str) -> str:
    """Plan D4, in its order. Pure, so the unit tests drive it directly."""
    out = COMMENT_RE.sub(" ", text)
    out = out.replace("**", "").replace("__", "").replace("`", "")
    out = out.translate(FOLD_TABLE)
    out = re.sub(r"\s+", " ", out).strip()
    return out.casefold()


def span_sha(text: str) -> str:
    """sha256[:12] of the normalized span: the registry `sha`."""
    return hashlib.sha256(normalize(text).encode("utf-8")).hexdigest()[:12]


def sha8(text: str) -> str:
    return hashlib.sha256(normalize(text).encode("utf-8")).hexdigest()[:8]


def line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def strip_gen_docs(text: str) -> str:
    return GEN_DOCS_RE.sub(" ", text)


def quote_fragments(text: str) -> list[str]:
    """Every double-quoted run, split on `...`, `[...]` and the ellipsis character, trailing `.,;:` stripped, empties dropped.

    Smart quotes are folded FIRST, so a curly-quoted citation is a citation too.
    """
    folded = text.translate(FOLD_TABLE)
    out: list[str] = []
    for match in re.finditer(r'"([^"]*)"', folded):
        for piece in ELLIPSIS_RE.split(match.group(1)):
            frag = piece.strip().rstrip(".,;:").strip()
            if frag:
                out.append(frag)
    return out


# --------------------------------------------------------------------------- markdown structure


@dataclasses.dataclass
class Block:
    """A paragraph, list item, heading, table row, fence or front-matter key, with offsets into the file."""

    start: int
    end: int
    line_start: int
    line_end: int
    kind: str  # para | fence | front
    group: int  # blank-line delimited group; a mirror close never crosses one


def md_blocks(text: str) -> list[Block]:
    lines = text.split("\n")
    offsets = []
    pos = 0
    for line in lines:
        offsets.append(pos)
        pos += len(line) + 1
    blocks: list[Block] = []
    group = [0]  # one-slot cells, so the nested helpers can rebind them
    kind_of = ["para"]
    cur: list[int] = []  # [first line, last line, single-line block]

    def close() -> None:
        if cur:
            a, b = cur[0], cur[1]
            blocks.append(
                Block(
                    offsets[a],
                    offsets[b] + len(lines[b]),
                    a + 1,
                    b + 1,
                    kind_of[0],
                    group[0],
                )
            )
            cur.clear()

    def begin(i: int, kind: str, single: int) -> None:
        close()
        kind_of[0] = kind
        cur.extend([i, i, single])

    i = 0
    n = len(lines)
    if n and lines[0].strip() == "---":
        j = next((k for k in range(1, n) if lines[k].strip() in ("---", "...")), None)
        if j is not None:
            for k in range(1, j):
                if not cur or FRONT_KEY_RE.match(lines[k]):
                    begin(k, "front", 0)
                else:
                    cur[1] = k
            close()
            group[0] += 1
            i = j + 1
    fence = ""
    # An INDENTED code block (CommonMark: four spaces or a tab, opening after a blank line or a heading, never interrupting a paragraph) is code too. Inside a list it is a continuation instead, so `in_list` holds from a list item until a block opens at column 0 that is not one; measured 2026-10-08, `.claude/skills/pr-epics/SKILL.md:20` lists `worklist.py --epic <me> new --plan` as indented code and was read as a restatement.
    indented = False
    in_list = False
    while i < n:
        line = lines[i]
        if indented:
            if line.strip() and INDENT_CODE_RE.match(line):
                cur[1] = i
                i += 1
                continue
            close()
            group[0] += 1
            indented = False
        if fence:
            cur[1] = i
            stripped = line.strip()
            if stripped.startswith(fence) and not stripped.strip(fence[0]):
                close()
                group[0] += 1
                fence = ""
            i += 1
            continue
        m = FENCE_RE.match(line)
        if m:
            group[0] += 1
            begin(i, "fence", 1)
            fence = m.group(1)
            i += 1
            continue
        if not line.strip():
            close()
            group[0] += 1
            i += 1
            continue
        if (not cur or cur[2]) and not in_list and INDENT_CODE_RE.match(line):
            group[0] += 1
            begin(i, "fence", 1)
            indented = True
            i += 1
            continue
        if ITEM_RE.match(line):
            in_list = True
        elif not line[:1].isspace():
            in_list = False
        single = bool(HEADING_RE.match(line) or TABLE_RE.match(line))
        if not cur or single or cur[2] or ITEM_RE.match(line):
            begin(i, "para", 1 if single else 0)
        else:
            cur[1] = i
        i += 1
    close()
    return blocks


def block_index(blocks: list[Block], offset: int) -> int:
    for idx, block in enumerate(blocks):
        if block.start <= offset <= block.end:
            return idx
    return -1


def code_mask(text: str, blocks: list[Block]) -> list[tuple[int, int]]:
    """Ranges that are code, not prose: every fenced block and every inline code span."""
    ranges = [(b.start, b.end) for b in blocks if b.kind == "fence"]
    for b in blocks:
        if b.kind == "fence":
            continue
        ranges.extend((m.start(), m.end()) for m in CODE_SPAN_RE.finditer(text, b.start, b.end))
    return ranges


@dataclasses.dataclass
class Marker:
    kind: str  # open | close | malformed
    start: int
    end: int
    clause: str
    line: int


def parse_anchors(text: str, blocks: list[Block] | None = None) -> list[Marker]:
    """Every scope marker outside code, in file order. Malformed ids are returned, not dropped."""
    if blocks is None:
        blocks = md_blocks(text)
    mask = code_mask(text, blocks)
    out: list[Marker] = []
    for m in COMMENT_RE.finditer(text):
        if any(a <= m.start() < b for a, b in mask):
            continue
        body = m.group(1).strip()
        line = line_of(text, m.start())
        if re.fullmatch(r"/\s*scope", body):
            out.append(Marker("close", m.start(), m.end(), "", line))
            continue
        opened = re.match(r"scope\s*:\s*(.*)$", body, re.DOTALL)
        if opened:
            clause = re.split(r"\s+--\s+", opened.group(1).strip(), maxsplit=1)[0].strip()
            kind = "open" if ID_RE.match(clause) else "malformed"
            out.append(Marker(kind, m.start(), m.end(), clause, line))
            continue
        if re.match(r"/?\s*scope\b", body):
            out.append(Marker("malformed", m.start(), m.end(), body, line))
    return out


@dataclasses.dataclass
class Span:
    path: str
    clause: str
    raw: str
    line: int
    start: int = -1
    end: int = -1


def canonical_spans(text: str, path: str = DEFAULT_CANONICAL) -> tuple[dict[str, Span], list[str]]:
    """The strict CLAUDE.md reading: spans by id, plus every C1 problem as `<line>: <what>`."""
    spans: dict[str, Span] = {}
    problems: list[str] = []
    opened: Marker | None = None
    seen: dict[str, int] = {}
    for mk in parse_anchors(text):
        if mk.kind == "malformed":
            problems.append(
                "%d: malformed scope anchor %r; ids match %s" % (mk.line, mk.clause, ID_RE.pattern)
            )
        elif mk.kind == "open":
            if opened is not None:
                problems.append(
                    "%d: %s opens inside %s (opened at line %d); spans do not nest"
                    % (mk.line, mk.clause, opened.clause, opened.line)
                )
                continue
            if mk.clause in seen:
                problems.append(
                    "%d: %s is opened again (first at line %d); each clause is anchored once"
                    % (mk.line, mk.clause, seen[mk.clause])
                )
            seen.setdefault(mk.clause, mk.line)
            opened = mk
        elif opened is None:
            problems.append("%d: a <!-- /scope --> closes nothing" % mk.line)
        else:
            if opened.clause not in spans:
                spans[opened.clause] = Span(
                    path,
                    opened.clause,
                    text[opened.end : mk.start],
                    opened.line,
                    opened.end,
                    mk.start,
                )
            opened = None
    if opened is not None:
        problems.append(
            "%d: %s is never closed; the close is required in CLAUDE.md"
            % (opened.line, opened.clause)
        )
    return spans, problems


def mirror_spans(text: str, path: str) -> list[Span]:
    """Every anchored span of a markdown mirror, by the mirror rules in the module docstring."""
    blocks = md_blocks(text)
    spans: list[Span] = []
    pending: list[tuple[Marker, int]] = []

    def end_at_block(mk: Marker, bi: int) -> None:
        end = blocks[bi].end if bi >= 0 else len(text)
        spans.append(Span(path, mk.clause, text[mk.end : end], mk.line, mk.end, end))

    for mk in parse_anchors(text, blocks):
        bi = block_index(blocks, mk.start)
        group = blocks[bi].group if bi >= 0 else -1
        keep: list[tuple[Marker, int]] = []
        for p, pbi in pending:
            same_group = pbi >= 0 and blocks[pbi].group == group
            if (mk.kind == "close" and same_group) or (mk.kind != "close" and pbi == bi):
                keep.append((p, pbi))
            else:
                end_at_block(p, pbi)
        pending = keep
        if mk.kind == "open":
            pending.append((mk, bi))
        elif mk.kind == "close":
            spans.extend(
                Span(path, p.clause, text[p.end : mk.start], p.line, p.end, mk.start)
                for p, _ in pending
            )
            pending = []
    for p, pbi in pending:
        end_at_block(p, pbi)
    return spans


def frontmatter_span(text: str, key: str, path: str) -> Span | None:
    for b in md_blocks(text):
        if b.kind != "front":
            continue
        raw = text[b.start : b.end]
        m = FRONT_KEY_RE.match(raw)
        if m and m.group(1) == key:
            return Span(path, "", raw[m.end() :], b.line_start, b.start + m.end(), b.end)
    return None


MISSING = object()


def py_constant(source: str, name: str) -> tuple[object, int]:
    """A module-level constant's literal value and line, read through `ast`. `MISSING` when absent or not a literal."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return MISSING, 0
    for node in tree.body:
        targets: list[ast.expr] = []
        value: ast.expr | None = None
        if isinstance(node, ast.Assign):
            targets, value = list(node.targets), node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets, value = [node.target], node.value
        if value is None:
            continue
        if any(isinstance(t, ast.Name) and t.id == name for t in targets):
            try:
                return ast.literal_eval(value), node.lineno
            except ValueError:
                return MISSING, node.lineno
    return MISSING, 0


def constant_values(value: object) -> list[str] | None:
    """The string members of a tuple, list, set or dict constant; None for any other shape."""
    if isinstance(value, dict):
        value = list(value)
    if isinstance(value, (tuple, list, set, frozenset)) and all(isinstance(v, str) for v in value):
        return sorted(str(v) for v in value)
    return None


# --------------------------------------------------------------------------- findings


@dataclasses.dataclass
class Finding:
    check: str
    path: str
    line: int
    clause: str
    message: str
    span: str = ""

    @property
    def fid(self) -> str:
        return "%s:%s:%s:%s" % (self.path, self.clause, self.check, sha8(self.span or self.message))

    @property
    def baselinable(self) -> bool:
        return self.check in BASELINABLE

    def render(self) -> str:
        return CROSS + " %s %s:%d [%s] %s" % (
            self.check,
            self.path,
            self.line,
            self.clause,
            self.message,
        )


@dataclasses.dataclass
class Shape:
    clauses: int = 0
    mirror_checks: int = 0
    spans: int = 0
    modes: dict[str, int] = dataclasses.field(default_factory=lambda: dict.fromkeys(MODES, 0))
    quotes: int = 0
    quote_sources: int = 0
    oracles: int = 0
    corpus_files: int = 0
    corpus_blocks: int = 0
    floor_clauses: int = 0
    floor_mirrors: int = 0


def load_registry(root: pathlib.Path) -> tuple[dict | None, str]:
    path = root / REGISTRY_REL
    if not path.is_file():
        return None, "%s is missing; the gate has nothing to check" % REGISTRY_REL
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return None, "%s is not JSON: %s" % (REGISTRY_REL, exc)
    if not isinstance(data, dict):
        return None, "%s must be a JSON object" % REGISTRY_REL
    return data, ""


def load_baseline(root: pathlib.Path) -> list[str] | None:
    path = root / BASELINE_REL
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return [str(x) for x in data.get("findings", [])]


def corpus_files(root: pathlib.Path) -> list[str]:
    """C9's corpus under `root`, as sorted posix paths relative to it."""
    found: set[str] = set()
    for pattern, recursive in CORPUS_GLOBS:
        matches = root.glob(pattern) if recursive or "*" in pattern else [root / pattern]
        found.update(p.relative_to(root).as_posix() for p in matches if p.is_file())
    return sorted(found)


def locate_text(root: pathlib.Path, rel: str, where: str | None) -> tuple[str, int, int, str]:
    """(text, first line, start offset, error) for a front-matter key, a py constant or a whole file."""
    path = root / rel
    if not path.is_file():
        return "", 0, -1, "%s does not exist" % rel
    text = path.read_text(encoding="utf-8")
    if not where:
        return text, 1, 0, ""
    kind, _, name = where.partition(":")
    if kind == "frontmatter":
        span = frontmatter_span(text, name, rel)
        if span is None:
            return "", 0, -1, "front-matter key %r is gone from %s" % (name, rel)
        return span.raw, span.line, span.start, ""
    value, line = py_constant(text, name)
    if not isinstance(value, str):
        return (
            "",
            line,
            -1,
            "module-level string constant %s is gone from %s, or is not a literal" % (name, rel),
        )
    return value, line, -1, ""


def locate_mirror(root: pathlib.Path, mirror: dict, clause: str) -> tuple[list[Span], str]:
    rel = mirror["path"]
    where = mirror.get("where")
    if where:
        text, line, start, err = locate_text(root, rel, where)
        if err:
            return [], err
        end = start + len(text) if start >= 0 else -1
        return [Span(rel, clause, text, line, start, end)], ""
    path = root / rel
    if not path.is_file():
        return [], "%s does not exist" % rel
    if not rel.endswith(".md"):
        return (
            [],
            "%s is not markdown, so it carries no anchor; give it where: py:<CONST> or frontmatter:<key>"
            % rel,
        )
    spans = [s for s in mirror_spans(path.read_text(encoding="utf-8"), rel) if s.clause == clause]
    if not spans:
        return [], "no <!-- scope: %s --> anchor in %s; restore it" % (clause, rel)
    return spans, ""


def _shape_problems(clause: str, spec: object) -> list[str]:
    """Registry shape for one clause; every problem is a C0 finding and the clause is not judged."""
    if not ID_RE.match(clause):
        return ["clause id %r does not match %s" % (clause, ID_RE.pattern)]
    if not isinstance(spec, dict):
        return ["clause %s must be an object" % clause]
    out = []
    for key in ("atoms", "sentinels"):
        value = spec.get(key, [])
        if not isinstance(value, list) or not all(isinstance(v, str) and v.strip() for v in value):
            out.append("%s.%s must be a list of non-empty strings" % (clause, key))
    mirrors = spec.get("mirrors", [])
    if not isinstance(mirrors, list):
        out.append("%s.mirrors must be a list" % clause)
        mirrors = []
    for m in mirrors:
        if not isinstance(m, dict) or not isinstance(m.get("path"), str) or not m.get("path"):
            out.append("%s has a mirror with no path" % clause)
            continue
        if m.get("mode") not in MODES:
            out.append(
                "%s mirror %s: mode %r is not one of %s"
                % (clause, m["path"], m.get("mode"), ", ".join(MODES))
            )
        where = m.get("where")
        if where is not None and not (isinstance(where, str) and WHERE_RE.match(where)):
            out.append(
                "%s mirror %s: where %r is not frontmatter:<key> or py:<CONST>"
                % (clause, m["path"], where)
            )
    oracle = spec.get("oracle")
    if oracle is not None and not (
        isinstance(oracle, dict)
        and isinstance(oracle.get("path"), str)
        and isinstance(oracle.get("const"), str)
        and oracle.get("rule") in ORACLE_RULES
    ):
        out.append("%s.oracle must be {path, const, rule: %s}" % (clause, " | ".join(ORACLE_RULES)))
    if not mirrors and not oracle:
        out.append("%s has no mirror and no oracle, so nothing about it is checked" % clause)
    return out


def check(
    root: pathlib.Path, shape: Shape | None = None, repinning: frozenset[str] = frozenset()
) -> list[Finding]:
    """Every finding, baselined or not, in check order. `repinning` treats those clauses as pinned, so their mirrors are judged against the CURRENT canonical (the repin precondition)."""
    if shape is None:
        shape = Shape()
    findings: list[Finding] = []

    def add(code: str, path: str, line: int, clause: str, message: str, span: str = "") -> None:
        findings.append(Finding(code, path, line, clause, message, span))

    registry, err = load_registry(root)
    if registry is None:
        add(
            "C0",
            REGISTRY_REL,
            0,
            "-",
            err
            + ". Write the registry described in the docstring of .ci/rediacc_ci/quality/scope_mirrors.py.",
        )
        return findings
    clauses = registry.get("clauses")
    if not isinstance(clauses, dict) or not clauses:
        add(
            "C0",
            REGISTRY_REL,
            0,
            "-",
            "no clauses registered; a gate with nothing to compare is not a gate",
        )
        return findings

    # -- C0 floors and shape ---------------------------------------------------
    floors = registry.get("floors")
    floor_c = floors.get("clauses") if isinstance(floors, dict) else None
    floor_m = floors.get("mirror_checks") if isinstance(floors, dict) else None
    floors_ok = (
        isinstance(floor_c, int)
        and isinstance(floor_m, int)
        and not isinstance(floor_c, bool)
        and not isinstance(floor_m, bool)
        and floor_c >= 1
        and floor_m >= 1
    )
    if not floors_ok:
        add(
            "C0",
            REGISTRY_REL,
            0,
            "-",
            'floors must be {"clauses": >=1, "mirror_checks": >=1}, got %r; a floor of 0 cannot fail'
            % (floors,),
        )
    valid: dict[str, dict] = {}
    for cid, spec in clauses.items():
        problems = _shape_problems(cid, spec)
        for p in problems:
            add("C0", REGISTRY_REL, 0, cid if ID_RE.match(cid) else "-", p)
        if not problems:
            valid[cid] = spec
    mirror_total = sum(
        len(spec.get("mirrors", [])) for spec in clauses.values() if isinstance(spec, dict)
    )
    shape.clauses = len(clauses)
    shape.mirror_checks = mirror_total
    if floors_ok and isinstance(floor_c, int) and isinstance(floor_m, int):
        shape.floor_clauses, shape.floor_mirrors = floor_c, floor_m
        if len(clauses) < shape.floor_clauses:
            add(
                "C0",
                REGISTRY_REL,
                0,
                "-",
                "%d clauses registered, floor is %d" % (len(clauses), shape.floor_clauses),
            )
        if mirror_total < shape.floor_mirrors:
            add(
                "C0",
                REGISTRY_REL,
                0,
                "-",
                "%d mirror checks registered, floor is %d" % (mirror_total, shape.floor_mirrors),
            )

    # -- C1 canonical anchors --------------------------------------------------
    canon_rel = str(registry.get("canonical") or DEFAULT_CANONICAL)
    canon_path = root / canon_rel
    if not canon_path.is_file():
        add("C0", canon_rel, 0, "-", "the canonical file is missing; nothing can be compared")
        return findings
    canon_text = canon_path.read_text(encoding="utf-8")
    spans, problems = canonical_spans(canon_text, canon_rel)
    for p in problems:
        lno, _, what = p.partition(": ")
        add("C1", canon_rel, int(lno), "-", what + ". Fix the anchor in %s." % canon_rel)
    for cid, cspan in spans.items():
        if cid not in clauses:
            add(
                "C1",
                canon_rel,
                cspan.line,
                cid,
                "anchors an id the registry does not know; register it in %s or remove the anchor"
                % REGISTRY_REL,
            )
    for cid in clauses:
        if cid not in spans:
            add(
                "C1",
                canon_rel,
                0,
                cid,
                "has no closed <!-- scope: %s --> ... <!-- /scope --> span in %s"
                % (cid, canon_rel),
            )

    # -- per clause: C3, C4, C2, C5/C6, C8 --------------------------------------
    all_mirror_paths = {m["path"] for spec in valid.values() for m in spec.get("mirrors", [])}
    coverage: dict[str, dict[str, list[tuple[int, int]]]] = {}
    for cid, cspan in spans.items():
        coverage.setdefault(canon_rel, {}).setdefault(cid, []).append((cspan.start, cspan.end))
    for cid, spec in valid.items():
        atoms = list(spec.get("atoms", []))
        located: list[tuple[dict, list[Span]]] = []
        for m in spec.get("mirrors", []):
            mspans, merr = locate_mirror(root, m, cid)
            if merr:
                add(
                    "C4",
                    m["path"],
                    0,
                    cid,
                    merr + ". A mirror that cannot be found is not skipped.",
                )
                continue
            located.append((m, mspans))
            for ms in mspans:
                shape.spans += 1
                shape.modes[m["mode"]] += 1
                if ms.start >= 0:
                    coverage.setdefault(m["path"], {}).setdefault(cid, []).append(
                        (ms.start, ms.end)
                    )
        span = spans.get(cid)
        if span is None:
            continue
        norm_span = normalize(span.raw)
        for key in ("atoms", "sentinels"):
            for atom in spec.get(key, []):
                if normalize(atom) not in norm_span:
                    add(
                        "C3",
                        REGISTRY_REL,
                        0,
                        cid,
                        "%s entry %r is not in the canonical span at %s:%d; fix the registry"
                        % (key[:-1], atom, canon_rel, span.line),
                    )
        if not atoms and any(m["mode"] == "terms" for m in spec.get("mirrors", [])):
            add(
                "C3",
                REGISTRY_REL,
                0,
                cid,
                "a terms mirror needs at least one atom; with none the test is vacuous",
            )
        pinned = cid in repinning or spec.get("sha") == span_sha(span.raw)
        if not pinned:
            where = ["%s:%d" % (ms.path, ms.line) for _, mss in located for ms in mss]
            where += [
                "%s (not located)" % m["path"]
                for m in spec.get("mirrors", [])
                if m not in [x for x, _ in located]
            ]
            add(
                "C2",
                canon_rel,
                span.line,
                cid,
                "canonical clause changed (registry sha %s, span now %s): re-read its %d mirror span(s) [%s], update them, then python3 %s --repin %s"
                % (
                    spec.get("sha") or "unpinned",
                    span_sha(span.raw),
                    len(where),
                    ", ".join(where) or "none",
                    ENTRY_REL,
                    cid,
                ),
            )
        else:
            for m, mss in located:
                for ms in mss:
                    norm_ms = normalize(ms.raw)
                    if m["mode"] == "verbatim" and norm_span not in norm_ms:
                        add(
                            "C5",
                            ms.path,
                            ms.line,
                            cid,
                            "verbatim mirror no longer contains the canonical text of %s:%d; copy it across (normalized), or register the mirror as terms"
                            % (canon_rel, span.line),
                            ms.raw,
                        )
                    elif m["mode"] == "terms":
                        missing = [a for a in atoms if normalize(a) not in norm_ms]
                        if missing:
                            add(
                                "C6",
                                ms.path,
                                ms.line,
                                cid,
                                "terms mirror is missing %s; restate them from %s:%d"
                                % (", ".join(repr(a) for a in missing), canon_rel, span.line),
                                ms.raw,
                            )
                    elif m["mode"] == "ref":
                        names = {normalize(canon_rel)} | {
                            normalize(p) for p in all_mirror_paths if p != ms.path
                        }
                        if not any(nm in norm_ms for nm in names):
                            add(
                                "C6",
                                ms.path,
                                ms.line,
                                cid,
                                "ref mirror names neither %s nor another registered mirror; point at the source instead of restating it"
                                % canon_rel,
                                ms.raw,
                            )
        oracle = spec.get("oracle")
        if oracle:
            opath = root / oracle["path"]
            if not opath.is_file():
                add("C8", oracle["path"], 0, cid, "oracle file is missing")
                continue
            value, oline = py_constant(opath.read_text(encoding="utf-8"), oracle["const"])
            values = None if value is MISSING else constant_values(value)
            if not values:
                add(
                    "C8",
                    oracle["path"],
                    oline,
                    cid,
                    "oracle %s is missing, not a literal, empty, or not a collection of strings"
                    % oracle["const"],
                )
                continue
            shape.oracles += 1
            if oracle["rule"] == "all-in-span":
                lacking = [v for v in values if normalize(v) not in norm_span]
                if lacking:
                    add(
                        "C8",
                        canon_rel,
                        span.line,
                        cid,
                        "the span lacks %s value(s) %s from %s:%d; name them in %s"
                        % (oracle["const"], ", ".join(lacking), oracle["path"], oline, canon_rel),
                    )
            else:
                tokens = {t for t in BACKTICKED_RE.findall(span.raw) if SNAKE_RE.match(t)}
                lacking = sorted(set(values) - tokens)
                extra = sorted(tokens - set(values))
                if lacking or extra:
                    add(
                        "C8",
                        canon_rel,
                        span.line,
                        cid,
                        "backticked keys differ from %s at %s:%d: missing in the span %s, not in the code %s"
                        % (
                            oracle["const"],
                            oracle["path"],
                            oline,
                            lacking or "none",
                            extra or "none",
                        ),
                    )

    # -- C7 quotes ---------------------------------------------------------------
    canon_quotable = normalize(strip_gen_docs(canon_text))
    sources = registry.get("quote_sources", [])
    if not isinstance(sources, list):
        add("C0", REGISTRY_REL, 0, "-", "quote_sources must be a list")
        sources = []
    for qs in sources:
        if (
            not isinstance(qs, dict)
            or not isinstance(qs.get("path"), str)
            or (qs.get("where") is not None and not WHERE_RE.match(str(qs.get("where"))))
        ):
            add(
                "C0",
                REGISTRY_REL,
                0,
                "quote",
                "quote source %r must be {path, where?: frontmatter:<key> | py:<CONST>}" % (qs,),
            )
            continue
        text, line, _, qerr = locate_text(root, qs["path"], qs.get("where"))
        if qerr:
            add(
                "C4",
                qs["path"],
                line,
                "quote",
                qerr + ". A quote source that cannot be found is not skipped.",
            )
            continue
        shape.quote_sources += 1
        frags = quote_fragments(text)
        if not frags:
            add(
                "C4",
                qs["path"],
                line,
                "quote",
                "quote source carries zero quoted fragments; the gate is not reading it",
            )
        folded = text.translate(FOLD_TABLE)
        for frag in frags:
            shape.quotes += 1
            if normalize(frag) not in canon_quotable:
                at = folded.find(frag)
                add(
                    "C7",
                    qs["path"],
                    line + (folded.count("\n", 0, at) if at >= 0 else 0),
                    "quote",
                    "quotes %s as %r, which it does not say; quote it exactly, or mark the cut with '...'"
                    % (canon_rel, frag),
                    frag,
                )

    # -- C9 unregistered restatement, C10 orphan anchor --------------------------
    corpus = corpus_files(root)
    shape.corpus_files = len(corpus)
    if not corpus:
        add(
            "C0",
            "-",
            0,
            "-",
            "the C9 corpus matched zero files under %s; the sweep is not seeing the tree" % root,
        )
    sentinels = {
        cid: [normalize(s) for s in spec.get("sentinels", [])] for cid, spec in valid.items()
    }
    anchored = {
        (m["path"], cid)
        for cid, spec in valid.items()
        for m in spec.get("mirrors", [])
        if not m.get("where")
    }
    md_mirrors = {p for p, _ in anchored if p.endswith(".md") and (root / p).is_file()}
    for rel in sorted(set(corpus) | md_mirrors):
        text = (root / rel).read_text(encoding="utf-8")
        blocks = md_blocks(text)
        markers = parse_anchors(text, blocks)
        if rel != canon_rel:
            for mk in markers:
                if mk.kind == "malformed":
                    add(
                        "C10",
                        rel,
                        mk.line,
                        "-",
                        "malformed scope anchor %r; ids match %s" % (mk.clause, ID_RE.pattern),
                    )
                elif mk.kind == "open" and (rel, mk.clause) not in anchored:
                    add(
                        "C10",
                        rel,
                        mk.line,
                        mk.clause,
                        "anchor is not registered as a mirror of %s; add the mirror to %s or remove the anchor"
                        % (mk.clause, REGISTRY_REL),
                    )
        if rel not in corpus:
            continue
        shape.corpus_blocks += len(blocks)
        cov = coverage.get(rel, {})
        for b in blocks:
            if b.kind == "fence":
                continue
            raw = text[b.start : b.end]
            nb = normalize(raw)
            for cid, sents in sentinels.items():
                hit = [s for s in sents if s in nb]
                if not hit:
                    continue
                if any(a < b.end and z > b.start for a, z in cov.get(cid, [])):
                    continue
                if any(
                    mk.kind == "open" and mk.clause == cid and b.start <= mk.start <= b.end
                    for mk in markers
                ):
                    continue
                add(
                    "C9",
                    rel,
                    b.line_start,
                    cid,
                    "restates %s (sentinel %r) with no registered span; register it as a mirror in %s and anchor it, or point at %s instead"
                    % (cid, hit[0], REGISTRY_REL, canon_rel),
                    raw,
                )
    return findings


# --------------------------------------------------------------------------- verdict, repin, baseline


def judge(root: pathlib.Path) -> tuple[list[Finding], list[Finding], list[str], Shape]:
    """(red findings, baselined findings, stale baseline ids, shape)."""
    shape = Shape()
    findings = check(root, shape)
    baseline = set(load_baseline(root) or [])
    red: list[Finding] = []
    held: list[Finding] = []
    live: set[str] = set()
    for f in findings:
        if f.baselinable and f.fid in baseline:
            held.append(f)
            live.add(f.fid)
        else:
            red.append(f)
    # A clause red on C2 has its C5/C6 unjudged, so its baselined ids are not "fixed"; calling them stale would invite a drain that the repin then trips over.
    unpinned = {f.clause for f in findings if f.check == "C2"}
    stale = sorted(fid for fid in baseline - live if fid.rsplit(":", 3)[-3] not in unpinned)
    return red, held, stale, shape


def report(root: pathlib.Path) -> int:
    red, held, stale, shape = judge(root)
    for f in red:
        print(f.render(), file=sys.stderr)
        if f.baselinable:
            print(
                "    id %s. Fix the text. Do not add it to the baseline." % f.fid, file=sys.stderr
            )
    for fid in stale:
        print(
            CROSS
            + " baselined finding is fixed: %s. Drain it: python3 %s --write-baseline"
            % (fid, ENTRY_REL),
            file=sys.stderr,
        )
    for f in held:
        print("  baselined (still owed): %s %s:%d [%s]" % (f.check, f.path, f.line, f.clause))
    if red or stale:
        print(
            CROSS
            + " scope mirrors: %d finding(s), %d stale baseline id(s)" % (len(red), len(stale)),
            file=sys.stderr,
        )
        return 1
    print(
        TICK
        + " scope mirrors OK: %d clauses (floor %d), %d mirror checks (floor %d) over %d spans "
        "(%d verbatim, %d terms, %d ref), %d quote fragments from %d source(s), %d oracle(s), "
        "C9 swept %d files / %d blocks, %d baselined. %s"
        % (
            shape.clauses,
            shape.floor_clauses,
            shape.mirror_checks,
            shape.floor_mirrors,
            shape.spans,
            shape.modes["verbatim"],
            shape.modes["terms"],
            shape.modes["ref"],
            shape.quotes,
            shape.quote_sources,
            shape.oracles,
            shape.corpus_files,
            shape.corpus_blocks,
            len(held),
            BLIND_SPOTS,
        )
    )
    return 0


def repin(root: pathlib.Path, target: str) -> int:
    registry, err = load_registry(root)
    if registry is None:
        print(CROSS + " repin refused: %s" % err, file=sys.stderr)
        return 2
    clauses = registry.get("clauses") or {}
    ids = sorted(clauses) if target == "--all" else [target]
    unknown = [i for i in ids if i not in clauses]
    if unknown or not ids:
        print(
            CROSS + " repin refused: unknown clause(s) %s" % (unknown or "(none registered)"),
            file=sys.stderr,
        )
        return 2
    canon_rel = str(registry.get("canonical") or DEFAULT_CANONICAL)
    canon_path = root / canon_rel
    canon_text = canon_path.read_text(encoding="utf-8") if canon_path.is_file() else ""
    spans, _ = canonical_spans(canon_text, canon_rel)
    baseline = set(load_baseline(root) or [])
    findings = check(root, None, frozenset(ids))
    blocking = [
        f
        for f in findings
        if f.clause in ids
        and f.check in ("C0", "C1", "C3", "C4", "C5", "C6", "C8")
        and not (f.baselinable and f.fid in baseline)
    ]
    missing = [i for i in ids if i not in spans]
    for i in missing:
        print(
            CROSS + " repin refused: %s has no canonical span in %s (C1)" % (i, canon_rel),
            file=sys.stderr,
        )
    for f in blocking:
        print(f.render(), file=sys.stderr)
    if missing or blocking:
        print(
            CROSS + " repin refused: %d blocking finding(s). Fix the mirrors against the new "
            "canonical, then repin again. Nothing was written; there is no --force."
            % (len(blocking) + len(missing)),
            file=sys.stderr,
        )
        return 1
    for i in ids:
        atoms = {normalize(a) for a in clauses[i].get("atoms") or []}
        extra = sorted(
            {t for t in BACKTICKED_RE.findall(spans[i].raw) if normalize(t) not in atoms}
        )
        if extra:
            print(
                "  %s: backticked tokens in the span that are not atoms: %s" % (i, ", ".join(extra))
            )
    changed = []
    for i in ids:
        new = span_sha(spans[i].raw)
        old = clauses[i].get("sha")
        if old != new:
            clauses[i]["sha"] = new
            changed.append("%s %s -> %s" % (i, old or "(unpinned)", new))
    if changed:
        (root / REGISTRY_REL).write_text(
            json.dumps(registry, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    for line in changed:
        print("  repinned %s" % line)
    print(TICK + " repin: %d clause(s) checked, %d repinned" % (len(ids), len(changed)))
    return 0


def write_baseline(root: pathlib.Path, first_seed: bool) -> int:
    findings = check(root)
    current = sorted({f.fid for f in findings if f.baselinable})
    old = load_baseline(root)
    additions = baseline_additions(old or [], current)
    verdict = write_verdict(
        baseline_exists=old is not None, first_seed=first_seed, additions=additions
    )
    if verdict == "missing-baseline":
        print(
            CROSS + " %s is missing. A first seed says so: --write-baseline --first-seed. "
            "Otherwise restore the file." % BASELINE_REL,
            file=sys.stderr,
        )
        return 1
    if verdict == "would-grow":
        for fid in additions:
            print(CROSS + " would add %s" % fid, file=sys.stderr)
        print(
            CROSS + " --write-baseline refused: the set would GROW by %d. Fix the mirror text. "
            "Do not add it to the baseline." % len(additions),
            file=sys.stderr,
        )
        return 1
    path = root / BASELINE_REL
    data: dict = {}
    if path.is_file():
        data = json.loads(path.read_text(encoding="utf-8"))
    data["findings"] = current
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    removed = sorted(set(old or []) - set(current))
    # The composition check, said out loud: a drain must add NOTHING. `write_verdict` already refused growth; the count printed here is what lets a reader see it.
    added = additions if old is not None else []
    for fid in removed:
        print("  drained %s" % fid)
    print(
        TICK
        + " baseline written: %d entries, %d drained, %d added%s"
        % (len(current), len(removed), len(added), " (first seed)" if old is None else "")
    )
    return 0


# --------------------------------------------------------------------------- selftest fixture

FIX_CANON = """# Fixture rules

## Session defaults

- **Pushing.** <!-- scope: pr.push-cadence -->Pushes happen at an epic milestone, at least every 2 hours of committed work, and before a stop that leaves unpushed commits.<!-- /scope --> Pushes are backups.
- **Turbo.** <!-- scope: pr.turbo-kinds -->Under `turbo: on` an early push needs `TURBO_PUSH_REASON` naming `ci-cd`, `red-fix`, `deadline` or `backup`.<!-- /scope -->
- **Switches.** Every switch of the hook (<!-- scope: pr.queue-switches -->`stop_hook`, `turbo`, `batch_size`<!-- /scope -->) lives in the queue.
- **Findings.** Ask for the big-bang, not for permission to patch one thing. Put the whole cluster (root cause, siblings, tests) into a single plan and ask to run it.

An anchor is written as `<!-- scope: pr.code-span-demo -->`, which is prose here.

```markdown
<!-- scope: pr.fenced-demo -->
```
"""

FIX_SO = """# Standing orders

- Cadence: <!-- scope: pr.push-cadence -->Pushes happen at an epic milestone, at least every 2 hours of committed work, and before a stop that leaves unpushed commits.<!-- /scope -->
"""

FIX_SKILL = """---
name: demo
description: a demo skill.
---

# Demo

- <!-- scope: pr.push-cadence -->Push at an epic milestone or every 2 hours, and never stop with unpushed commits.
- An unrelated item that restates nothing.
"""

FIX_AGENT = """---
name: demo-agent
description: Pushes at an epic milestone, every 2 hours, and before a stop with unpushed commits.
tools: Bash
---

Body text.
"""

FIX_GUARD = '''KINDS = ("ci-cd", "red-fix", "deadline", "backup")

MESSAGE = """BLOCKED: pushes run on a cadence ("at an epic milestone, at least every 2
hours of committed work, and before a stop that leaves unpushed commits").

  Findings rule: "Ask for the big-bang, not for permission to patch one thing...
  put the whole cluster ... into a single plan and ask to run it."
"""
'''

FIX_QUEUE = 'SETTINGS_KEYS = ("stop_hook", "turbo", "batch_size")\n'

FIX_CMD = """# Demo command

<!-- scope: pr.turbo-kinds -->The early-push reasons are listed in CLAUDE.md and not restated here.
"""

SO = ".claude/output-styles/so.md"
SKILL = ".claude/skills/demo/SKILL.md"
AGENT = ".claude/agents/demo.md"
GUARD = ".claude/rediacc_hooks/guards/demo_guard.py"
QUEUE_PY = ".claude/hooks/stop/demo_queue.py"
CMD = ".claude/commands/demo-cmd.md"


def fixture_registry() -> dict:
    """The selftest's registry, pinned to FIX_CANON by the module's own sha."""
    spans, _ = canonical_spans(FIX_CANON)

    def pin(clause: str) -> str:
        return span_sha(spans[clause].raw) if clause in spans else ""

    return {
        "canonical": "CLAUDE.md",
        "floors": {"clauses": 3, "mirror_checks": 5},
        "quote_sources": [{"path": GUARD, "where": "py:MESSAGE"}],
        "clauses": {
            "pr.push-cadence": {
                "sha": pin("pr.push-cadence"),
                "atoms": ["at an epic milestone", "every 2 hours", "unpushed commits"],
                "sentinels": ["every 2 hours"],
                "mirrors": [
                    {"path": SO, "mode": "verbatim"},
                    {"path": SKILL, "mode": "terms"},
                    {"path": AGENT, "mode": "terms", "where": "frontmatter:description"},
                    {"path": GUARD, "mode": "terms", "where": "py:MESSAGE"},
                ],
            },
            "pr.turbo-kinds": {
                "sha": pin("pr.turbo-kinds"),
                "atoms": ["`turbo: on`", "`TURBO_PUSH_REASON`"],
                "sentinels": ["TURBO_PUSH_REASON"],
                "oracle": {"path": GUARD, "const": "KINDS", "rule": "all-in-span"},
                "mirrors": [{"path": CMD, "mode": "ref"}],
            },
            "pr.queue-switches": {
                "sha": pin("pr.queue-switches"),
                "atoms": [],
                "sentinels": [],
                "oracle": {"path": QUEUE_PY, "const": "SETTINGS_KEYS", "rule": "equal-backticked"},
                "mirrors": [],
            },
        },
    }


def _write(root: pathlib.Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _read(root: pathlib.Path, rel: str) -> str:
    return (root / rel).read_text(encoding="utf-8")


def _mutate(root: pathlib.Path, rel: str, old: str, new: str) -> None:
    _write(root, rel, plant(_read(root, rel), old, new))


def build_fixture(root: pathlib.Path, baseline: list[str] | None = None) -> pathlib.Path:
    """The selftest tree: a mini CLAUDE.md, a registry, verbatim, terms, front-matter, py:MESSAGE and ref mirrors."""
    files = {
        "CLAUDE.md": FIX_CANON,
        SO: FIX_SO,
        SKILL: FIX_SKILL,
        AGENT: FIX_AGENT,
        GUARD: FIX_GUARD,
        QUEUE_PY: FIX_QUEUE,
        CMD: FIX_CMD,
        REGISTRY_REL: json.dumps(fixture_registry(), indent=2) + "\n",
    }
    for rel, text in files.items():
        _write(root, rel, text)
    if baseline is not None:
        _write(root, BASELINE_REL, json.dumps({"findings": baseline}) + "\n")
    return root


def _red(root: pathlib.Path) -> list[Finding]:
    return judge(root)[0]


def _hits(found: list[Finding], code: str, path: str = "") -> int:
    return sum(1 for f in found if f.check == code and path in f.path)


def _quiet(fn, *args) -> int:
    """Run a write path with its chatter captured, returning its rc."""
    sink = io.StringIO()
    with contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
        return fn(*args)


def selftest(verbose: bool = True) -> int:
    """Control-first: one clean fixture, then one planted defect per check, each built with `plant`."""
    ctl = Controls("scope-mirrors", floor=45, verbose=verbose)
    with tempfile.TemporaryDirectory() as tmp:
        base = pathlib.Path(tmp)
        made = [0]

        def fresh(baseline: list[str] | None = None) -> pathlib.Path:
            made[0] += 1
            return build_fixture(base / ("t%d" % made[0]), baseline)

        # -- pure helpers --------------------------------------------------
        ctl.check(
            "normalize folds markup, quotes, dashes, comments and case",
            normalize(
                "A **b** `c`" + chr(0x2014) + chr(0x201C) + "d" + chr(0x201D) + " <!-- x -->\n  E"
            ),
            'a b c--"d" e',
        )
        ctl.check(
            "quote fragments split on every ellipsis spelling and drop trailing punctuation",
            quote_fragments('x "one, two... three [...] four' + chr(0x2026) + ' five." y'),
            ["one, two", "three", "four", "five"],
        )
        ctl.check("a backticked anchor is prose", parse_anchors("`<!-- scope: pr.abc -->`\n"), [])
        ctl.check(
            "a fenced anchor is prose", parse_anchors("```\n<!-- scope: pr.abc -->\n```\n"), []
        )
        ctl.check(
            "a bare anchor is an anchor",
            [m.kind for m in parse_anchors("x <!-- scope: pr.abc -- why -->y\n")],
            ["open"],
        )
        ctl.check(
            "a closeless mirror span ends with its list item",
            [normalize(s.raw) for s in mirror_spans("- <!-- scope: pr.abc -->one\n- two\n", "m")],
            ["one"],
        )
        ctl.check(
            "a closed mirror span may cross list items",
            [
                normalize(s.raw)
                for s in mirror_spans("<!-- scope: pr.abc -->a\n- b\n- c<!-- /scope -->\n", "m")
            ],
            ["a - b - c"],
        )
        ctl.check(
            "a later open ends an earlier closeless span at its own block",
            [
                normalize(s.raw)
                for s in mirror_spans(
                    "- <!-- scope: pr.abc -->a\n- <!-- scope: pr.def -->b<!-- /scope -->\n", "m"
                )
            ],
            ["a", "b"],
        )
        ctl.check(
            "an indented code block is code, not prose",
            [b.kind for b in md_blocks("# H\n\n    cmd --flag\n    cmd two\n\nProse.\n")],
            ["para", "fence", "para"],
        )
        ctl.check(
            "a list continuation indented four spaces stays prose",
            [b.kind for b in md_blocks("- item\n\n    continued text\n")],
            ["para", "para"],
        )
        ctl.check(
            "py_constant reads a tuple",
            py_constant(FIX_QUEUE, "SETTINGS_KEYS")[0],
            ("stop_hook", "turbo", "batch_size"),
        )
        ctl.truthy(
            "py_constant reports a missing name", py_constant(FIX_QUEUE, "NOPE")[0] is MISSING
        )

        # -- clean fixture: silent, and the shape is non-trivial ------------
        root = fresh()
        red, _, stale, shape = judge(root)
        ctl.check("CLEAN fixture has zero findings", [f.render() for f in red], [])
        ctl.check("CLEAN fixture has no stale ids", stale, [])
        ctl.check("CLEAN shape counts the clauses", shape.clauses, 3)
        ctl.check("CLEAN shape counts the mirror checks", shape.mirror_checks, 5)
        ctl.check("CLEAN shape counts the ref span", shape.modes["ref"], 1)
        ctl.check("CLEAN shape counts the quote fragments", shape.quotes, 4)
        ctl.truthy("CLEAN shape swept corpus files", shape.corpus_files >= 5)

        # -- C0 floors and registry shape -----------------------------------
        root = fresh()
        _mutate(root, REGISTRY_REL, '"clauses": 3', '"clauses": 4')
        ctl.truthy("C0 fires when the clause floor is not met", _hits(_red(root), "C0"))
        root = fresh()
        _mutate(root, REGISTRY_REL, '"mirror_checks": 5', '"mirror_checks": 0')
        ctl.truthy("C0 refuses a floor of 0", _hits(_red(root), "C0"))
        root = fresh()
        _mutate(root, REGISTRY_REL, '"rule": "equal-backticked"', '"rule": "nonsense"')
        ctl.truthy("C0 refuses an unknown oracle rule", _hits(_red(root), "C0"))
        root = fresh()
        _mutate(
            root,
            REGISTRY_REL,
            '"oracle": {\n        "path": ".claude/hooks',
            '"gone": {\n        "path": ".claude/hooks',
        )
        ctl.truthy("C0 fires on a clause with no mirror and no oracle", _hits(_red(root), "C0"))

        # -- C1 canonical anchors -------------------------------------------
        root = fresh()
        _mutate(root, "CLAUDE.md", "unpushed commits.<!-- /scope -->", "unpushed commits.")
        ctl.truthy("C1 fires on an unclosed canonical anchor", _hits(_red(root), "C1"))
        root = fresh()
        _mutate(
            root,
            "CLAUDE.md",
            "Pushes are backups.",
            "<!-- scope: pr.push-cadence -->Again.<!-- /scope -->",
        )
        ctl.truthy("C1 fires on a clause anchored twice", _hits(_red(root), "C1"))
        root = fresh()
        _mutate(
            root,
            "CLAUDE.md",
            "`<!-- scope: pr.code-span-demo -->`",
            "<!-- scope: pr.code-span-demo -->x<!-- /scope -->",
        )
        ctl.truthy("C1 fires on an unknown id once the backticks go", _hits(_red(root), "C1"))
        root = fresh()
        _mutate(
            root,
            "CLAUDE.md",
            "at least every 2 hours",
            "at least <!-- scope: pr.queue-switches -->every 2 hours",
        )
        ctl.truthy("C1 fires on a nested anchor", _hits(_red(root), "C1"))

        # -- C2 pin, and T3's shape: mirrors are not judged while the pin is red
        root = fresh()
        _mutate(
            root,
            "CLAUDE.md",
            "unpushed commits.<!-- /scope -->",
            "unpushed commits, and at night.<!-- /scope -->",
        )
        found = _red(root)
        ctl.truthy("C2 fires when the canonical span changes", _hits(found, "C2"))
        ctl.check("C2 suppresses C5/C6 for that clause", _hits(found, "C5") + _hits(found, "C6"), 0)
        ctl.truthy(
            "C2 names the repin command",
            any("--repin pr.push-cadence" in f.message for f in found),
        )

        # -- C3 config integrity --------------------------------------------
        root = fresh()
        _mutate(
            root,
            REGISTRY_REL,
            '"every 2 hours",\n        "unpushed',
            '"every 3 hours",\n        "unpushed',
        )
        ctl.truthy("C3 fires on an atom not in the canonical span", _hits(_red(root), "C3"))

        # -- C4 mirror located ----------------------------------------------
        root = fresh()
        _mutate(root, SKILL, "<!-- scope: pr.push-cadence -->", "")
        ctl.truthy("C4 fires when a mirror anchor is deleted", _hits(_red(root), "C4", SKILL))
        root = fresh()
        _mutate(root, GUARD, "MESSAGE = ", "MESSAGES = ")
        ctl.truthy("C4 fires when a py constant is gone", _hits(_red(root), "C4", GUARD))
        root = fresh()
        _mutate(root, AGENT, "description: Pushes", "summary: Pushes")
        ctl.truthy("C4 fires when a front-matter key is gone", _hits(_red(root), "C4", AGENT))

        # -- C5 verbatim, and an untouched mirror stays silent ---------------
        root = fresh()
        _mutate(root, SO, "before a stop", "before any stop")
        found = _red(root)
        ctl.truthy("C5 fires on a reworded verbatim mirror", _hits(found, "C5", SO))
        ctl.check(
            "C5 leaves the untouched mirrors silent", [f.path for f in found if f.path != SO], []
        )

        # -- C6 terms and ref -----------------------------------------------
        root = fresh()
        _mutate(root, SKILL, "never stop with unpushed commits", "never stop with open work")
        found = _red(root)
        ctl.truthy("C6 fires on a terms mirror missing an atom", _hits(found, "C6", SKILL))
        ctl.check("C6 names only the drifted mirror", sorted({f.path for f in found}), [SKILL])
        root = fresh()
        _mutate(root, SKILL, "or every 2 hours, and", "and")
        _mutate(root, SKILL, "restates nothing.", "restates nothing, every 2 hours.")
        ctl.truthy(
            "C6 does not read past a closeless span's block end", _hits(_red(root), "C6", SKILL)
        )
        root = fresh()
        _mutate(root, CMD, "listed in CLAUDE.md and", "listed elsewhere and")
        ctl.truthy("C6 fires on a ref mirror that names no source", _hits(_red(root), "C6", CMD))
        root = fresh()
        _mutate(root, AGENT, "every 2 hours", "hourly")
        ctl.truthy("C6 reads a front-matter mirror", _hits(_red(root), "C6", AGENT))
        root = fresh()
        _mutate(root, GUARD, 'unpushed commits").', 'open work").')
        ctl.truthy("C6 reads a py:MESSAGE mirror", _hits(_red(root), "C6", GUARD))

        # -- C7 quotes ------------------------------------------------------
        root = fresh()
        _mutate(root, GUARD, "Ask for the big-bang", "Ask for the big-change")
        ctl.truthy("C7 fires on a changed word inside a quote", _hits(_red(root), "C7", GUARD))
        root = fresh()
        _mutate(root, GUARD, "put the whole cluster ... into", "put the whole cluster into")
        ctl.truthy("C7 fires on a cut not marked with an ellipsis", _hits(_red(root), "C7", GUARD))

        # -- C8 oracle ------------------------------------------------------
        root = fresh()
        _mutate(root, GUARD, '"backup")', '"backup", "late")')
        ctl.truthy("C8 all-in-span fires on a value the span lacks", _hits(_red(root), "C8"))
        root = fresh()
        _mutate(root, QUEUE_PY, '"batch_size")', '"batch_size", "judge")')
        ctl.truthy("C8 equal-backticked fires on a key the span lacks", _hits(_red(root), "C8"))

        # -- C9 and C10 -----------------------------------------------------
        root = fresh()
        _write(root, ".claude/commands/new.md", "# New\n\nPush every 2 hours.\n")
        ctl.truthy("C9 fires on an unregistered restatement", _hits(_red(root), "C9", "new.md"))
        root = fresh()
        _write(
            root,
            ".claude/commands/new.md",
            "# New\n\n<!-- scope: pr.push-cadence -->Push every 2 hours.\n",
        )
        found = _red(root)
        ctl.truthy("C10 fires on an unregistered anchor", _hits(found, "C10", "new.md"))
        ctl.check("an anchored restatement is C10, not C9", _hits(found, "C9", "new.md"), 0)
        root = fresh()
        _mutate(root, CMD, "<!-- scope: pr.turbo-kinds -->", "<!-- scope: pr.X -->")
        ctl.truthy("C10 fires on a malformed mirror id", _hits(_red(root), "C10", CMD))

        # -- baseline -------------------------------------------------------
        root = fresh()
        _mutate(root, SKILL, "never stop with unpushed commits", "never stop with open work")
        fid = next((f.fid for f in _red(root) if f.check == "C6"), "no-c6-finding")
        _write(root, BASELINE_REL, json.dumps({"findings": [fid]}) + "\n")
        red, held, _, _ = judge(root)
        ctl.check("a baselined finding is held, not red", (len(red), len(held)), (0, 1))
        root = fresh([fid])
        ctl.check("a fixed baselined finding is red until drained", judge(root)[2], [fid])
        root = fresh([])
        _mutate(root, SKILL, "never stop with unpushed commits", "never stop with open work")
        ctl.check("--write-baseline refuses growth", _quiet(write_baseline, root, False), 1)
        ctl.check("and leaves the baseline untouched", load_baseline(root), [])
        root = fresh([fid])
        ctl.check("--write-baseline drains a fixed finding", _quiet(write_baseline, root, False), 0)
        ctl.check("and the drained set adds nothing", load_baseline(root), [])
        root = fresh()
        _mutate(root, SKILL, "never stop with unpushed commits", "never stop with open work")
        ctl.check(
            "--write-baseline without a file needs --first-seed",
            _quiet(write_baseline, root, False),
            1,
        )
        ctl.check(
            "--first-seed is accepted while no baseline exists",
            _quiet(write_baseline, root, True),
            0,
        )
        ctl.check("and the seed holds the finding", load_baseline(root), [fid])

        # -- repin ----------------------------------------------------------
        root = fresh()
        _mutate(root, SO, "before a stop", "before any stop")
        before = _read(root, REGISTRY_REL)
        ctl.check(
            "--repin refuses while a mirror drifts", _quiet(repin, root, "pr.push-cadence"), 1
        )
        ctl.check("and writes nothing", _read(root, REGISTRY_REL), before)
        root = fresh()
        _mutate(
            root,
            "CLAUDE.md",
            "unpushed commits.<!-- /scope -->",
            "unpushed commits, and at night.<!-- /scope -->",
        )
        ctl.check(
            "--repin refuses a changed canonical the verbatim mirror lacks",
            _quiet(repin, root, "--all"),
            1,
        )
        _mutate(
            root,
            SO,
            "unpushed commits.<!-- /scope -->",
            "unpushed commits, and at night.<!-- /scope -->",
        )
        ctl.check("--repin is allowed once the mirrors follow", _quiet(repin, root, "--all"), 0)
        ctl.check("and the gate is green after it", [f.render() for f in _red(root)], [])
        ctl.check("--repin refuses an unknown clause", _quiet(repin, root, "pr.nope-nope"), 2)

    return 0 if ctl.report() else 1


# --------------------------------------------------------------------------- entry


USAGE = (
    "usage: check_scope_mirrors.py [--root DIR] [--selftest | --repin <id>|--all | "
    "--write-baseline [--first-seed]]"
)


def main(argv: list[str] | None = None, root: pathlib.Path | None = None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    if args == ["--selftest"]:
        return selftest()
    tree = root if root is not None else paths.repo_root()
    if "--root" in args:
        i = args.index("--root")
        if i + 1 >= len(args):
            print(USAGE, file=sys.stderr)
            return 2
        tree = pathlib.Path(args[i + 1]).resolve()
        del args[i : i + 2]
    target = ""
    repinning = "--repin" in args
    if repinning:
        i = args.index("--repin")
        if i + 1 >= len(args):
            print(USAGE, file=sys.stderr)
            return 2
        target = args[i + 1]
        del args[i : i + 2]
    write = "--write-baseline" in args
    first_seed = "--first-seed" in args
    rest = [a for a in args if a not in ("--write-baseline", "--first-seed")]
    if rest or (first_seed and not write) or (target and write):
        print(USAGE, file=sys.stderr)
        return 2
    rc = controls_first("scope mirrors", lambda: selftest(verbose=False))
    if rc:
        return rc
    if repinning:
        return repin(tree, target)
    if write:
        return write_baseline(tree, first_seed)
    return report(tree)


__all__ = [
    "BASELINE_REL",
    "MISSING",
    "REGISTRY_REL",
    "Finding",
    "Shape",
    "canonical_spans",
    "check",
    "constant_values",
    "frontmatter_span",
    "judge",
    "load_baseline",
    "load_registry",
    "main",
    "md_blocks",
    "mirror_spans",
    "normalize",
    "parse_anchors",
    "py_constant",
    "quote_fragments",
    "repin",
    "selftest",
    "span_sha",
    "write_baseline",
]
