r"""check:ci-literal-sources -- one source per configuration literal, and a refusal when a new one starts spreading.

THE FINDING. The operator searched for the release origin and found it everywhere: re-measured on 0930-1 it sat on 608 lines of 132 tracked files, and the same value was declared as a module constant twelve times in Python alone, each copy "held" by a drift test that only proved the copies still agreed. The request was for a rule smart enough to catch the NEXT literal, not just that one, so this gate is two questions and not a list:

  R1  A REGISTERED value outside its source. `.ci/config/well-known.env` is the
      one hand-edited file (regions.json is the second, for the region hosts).
      A registered origin, bucket, slug, image registry, owned path, address or
      port typed out in CODE anywhere else is a finding that names the symbol to
      use in that file's language.
  R2a An UNREGISTERED literal in an owned namespace (a *.rediacc.com host, an
      @rediacc address, /mnt/rediacc..., rediacc/<repo>, ghcr.io/rediacc/...) in
      CODE in at least `thresholds.R2a` distinct files: register it.
  R2b An unregistered THIRD-PARTY URL stem or image repository in at least
      `thresholds.R2b` distinct files: register it.
  R3  Liveness, both directions: every registry entry has a consumer, every
      carrier still contains the values it declares, every exemption glob still
      matches a tracked file.
  R4  The projections: `packages/shared/src/config/well-known.generated.ts`
      (TypeScript) and `.ci/config/well-known.generated.sh` (bash) each equal
      their render of the registry (this file writes them, with `--write`, and
      checks them through the same table, so emitter and checker cannot
      disagree); constants.sh sources the bash projection; `rediacc_ci/well_known.py`
      exports exactly the registry's names; WK_ACCOUNT_DEFAULT_ORIGIN is the
      default region's domain.
  R5  Near misses: an owned host or address within a small edit distance of a
      registered one but not equal to it, in code OR prose, is a finding. That
      is a typo or a stale host, and prose is where those live.

ONLY CODE COUNTS FOR R1 AND R2. Each candidate file is lexed for its language and every hit is classified CODE (a string, a template literal, a bare YAML/TOML/JSON value, an unquoted shell word) or PROSE (a comment, a Python docstring or other standalone string statement, JSDoc, an HTML comment). A comment that says where a value comes from is documentation; a string that holds it is a second source. f-strings and `::error::` messages are CODE: they are what a user reads, and they are built from the value.

NORMALIZATION decides what "the same literal" means. A URL is reduced to scheme, host and path: the host is lower-cased, userinfo, the default port, the query and the fragment are dropped, the path is cut at the first template marker (`${`, `{`, `%s`, `$`, `<`) and its trailing slash is stripped. A URL-valued entry matches by host (and by path prefix when the entry has a path), a path entry by prefix, everything else exactly. Without this, `https://Releases.rediacc.com/` and `releases.rediacc.com` would be three unrelated strings and the drift would hide in the spelling.

WHAT IS NOT IN SCOPE, and why, is in `scripts/data/literal-sources.json` next to each exemption: history (agent/, *.jsonl, changelogs), recorded bytes (.ci/shadow/, goldens), generated outputs (police the generator instead), vendored trees, version pins (`toolchain_pins.py` owns them). Markdown and translations are not CODE, but R5 still reads them. Tests ARE in scope: an assertion composes its expectation from the symbol, or it is one more copy that agrees with itself.

ANTI-VACUITY. The in-scope file count has a floor (`floor` in the policy) and the gate REFUSES below it, so a broken `git ls-files` cannot read as a clean tree. Zero candidate hits is a refusal for the same reason. Every registry entry must have a consumer, which makes the registry its own known-positive floor. `--selftest` runs first and builds every control of the plan by construction in a temporary repository; a failed control refuses the verdict (exit 2).

USAGE
    check_literal_sources.py                      selftest, then the verdict
    check_literal_sources.py --selftest           controls only
    check_literal_sources.py --report [--paths G...]
                                                  findings grouped by file, with the
                                                  symbol to use; --paths limits the
                                                  PRINTED files, the scan stays whole
                                                  (R2 counts need the whole tree)
    check_literal_sources.py --write              render the TS and bash projections

Exit 0 clean, 1 on a finding or a refusal, 2 on a failed control.
"""

from __future__ import annotations

import bisect
import collections
import concurrent.futures
import dataclasses
import json
import multiprocessing
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Any

from rediacc_ci import log, paths, well_known
from rediacc_ci.controls import Checker, controls_first

POLICY_REL = "scripts/data/literal-sources.json"
REGISTRY_REL = well_known.REGISTRY_REL
REGIONS_REL = "regions.json"
PROJECTION_REL = "packages/shared/src/config/well-known.generated.ts"
SH_PROJECTION_REL = ".ci/config/well-known.generated.sh"
CONSTANTS_REL = ".ci/config/constants.sh"
READER_REL = ".ci/rediacc_ci/well_known.py"
GATE_RELS = (
    ".ci/rediacc_ci/quality/literal_sources.py",
    ".ci/scripts/quality/check_literal_sources.py",
)
REGION_PREFIX = "regions.json:"


class RefusalError(Exception):
    """The instrument cannot reach a verdict: no tree, no registry, a broken policy."""


# --------------------------------------------------------------------------- registry ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class Entry:
    """One registered value. `key` is `WK_NAME` for the registry, `regions.json:<id>.<field>` for a region host."""

    key: str
    value: str
    kind: str  # url | host | email | path | port | image | slug | token
    host: str = ""
    path: str = ""
    # A URL entry listed under `exact_stem` in the policy matches only its own normalized stem, not every URL on its host.
    exact: bool = False

    @property
    def name(self) -> str:
        return self.key.removeprefix("WK_")

    @property
    def is_region(self) -> bool:
        return self.key.startswith(REGION_PREFIX)

    @property
    def needle(self) -> str:
        """What a carrier must still contain for this entry: the host for a URL, the value otherwise."""
        return self.host if self.kind in ("url", "host") and not self.path else self.value


_SLUG_SHAPE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_IMAGE_SHAPE = re.compile(r"^[a-z0-9.-]+\.[a-z]{2,}/[a-z0-9._/-]+$")


def entry_for(key: str, value: str) -> Entry:
    """The kind of a registry value is read off its shape, so the registry stays the toolchain.env format with no type column."""
    if re.match(r"^https?://", value, re.IGNORECASE):
        url = normalize_url(value)
        if url is None:
            raise RefusalError("%s=%s is a URL this gate cannot normalize" % (key, value))
        return Entry(key, value, "url", url.host, url.path)
    if "@" in value:
        return Entry(key, value, "email")
    if value.startswith("/"):
        return Entry(key, value, "path")
    if value.isdigit():
        return Entry(key, value, "port")
    if _IMAGE_SHAPE.match(value):
        return Entry(key, value, "image")
    if _HOSTISH.match(value.lower()):
        return Entry(key, value, "host", value.lower(), "")
    if _SLUG_SHAPE.match(value):
        return Entry(key, value, "slug")
    return Entry(key, value, "token")


def region_entries(regions: dict[str, Any]) -> list[Entry]:
    out = []
    for region in regions.get("regions", []):
        for field in ("domain", "edgeDomain"):
            host = str(region.get(field) or "").lower()
            if host:
                out.append(
                    Entry(
                        "%s%s.%s" % (REGION_PREFIX, region.get("id"), field), host, "host", host, ""
                    )
                )
    return out


def default_region_domain(regions: dict[str, Any]) -> str:
    for region in regions.get("regions", []):
        if region.get("default"):
            return str(region.get("domain") or "").lower()
    return ""


# --------------------------------------------------------------------------- normalization ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class Url:
    scheme: str
    host: str
    port: str
    path: str

    @property
    def stem(self) -> str:
        port = ":" + self.port if self.port else ""
        return "%s://%s%s%s" % (self.scheme, self.host, port, self.path)


_TEMPLATE_MARKERS = re.compile(r"\$\{|\{|%s|%\(|\$|<")
_DEFAULT_PORTS = {"http": "80", "https": "443"}
_HOSTISH = re.compile(
    r"^(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,}$|^localhost$|^\d{1,3}(?:\.\d{1,3}){3}$|^\[[0-9a-f:]+\]$"
)


_NETLOC = re.compile(r"(?:[^@/]*@)?(\[[0-9A-Fa-f:]+\]|[A-Za-z0-9.-]+)(?::(\d+))?")


def normalize_url(raw: str) -> Url | None:
    """Scheme and host lower-cased; userinfo, default port, query, fragment dropped; path cut at the first template marker, trailing slash stripped.

    None when what follows the scheme is not a host (a template, `$HOST`), because such a string is not a literal of anything.
    """
    m = re.match(r"^([A-Za-z][A-Za-z0-9+.-]*)://(.*)$", raw)
    if not m:
        return None
    scheme = m.group(1).lower()
    rest = m.group(2)
    cut = _TEMPLATE_MARKERS.search(rest)
    if cut:
        rest = rest[: cut.start()]
    rest = re.split(r"[?#]", rest, maxsplit=1)[0]
    # The host is the leading host-shaped run after any userinfo, so trailing punctuation (`https://host,` in a YAML flow list, `https://host;` in shell) costs nothing rather than the whole literal.
    hm = _NETLOC.match(rest)
    if not hm:
        return None
    host = hm.group(1).lower().rstrip(".")
    port = hm.group(2) or ""
    if not _HOSTISH.match(host):
        return None
    if port == _DEFAULT_PORTS.get(scheme):
        port = ""
    tail = rest[hm.end() :]
    path = tail if tail.startswith("/") else ""
    path = path.rstrip("/.,;:'")
    return Url(scheme, host, port, path)


def levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if len(a) < len(b):
        a, b = b, a
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def near_miss(candidate: str, known: str, limit: int) -> bool:
    """Unequal, sharing everything after the first label boundary that differs, and within a distance that scales with length.

    The scaling is what keeps `eu.` and `us.` (distance 2, both real) from being typos of each other: a label of three characters gets no slack, four to seven get one, longer ones get `limit`.
    """
    if candidate == known:
        return False
    a_local, _, a_rest = candidate.partition("@") if "@" in candidate else ("", "", candidate)
    b_local, _, b_rest = known.partition("@") if "@" in known else ("", "", known)
    if "@" in candidate or "@" in known:
        if a_rest != b_rest or not a_local or not b_local:
            return False
        a, b = a_local, b_local
    else:
        a_labels, b_labels = a_rest.split("."), b_rest.split(".")
        if len(a_labels) != len(b_labels) or a_labels[1:] != b_labels[1:]:
            return False
        a, b = a_labels[0], b_labels[0]
    longest = max(len(a), len(b))
    slack = 0 if longest < 4 else (1 if longest < 8 else limit)
    return 0 < levenshtein(a, b) <= slack


# --------------------------------------------------------------------------- lexing ---------------------------------------------------------------------------
#
# Each lexer returns the PROSE spans of a file as sorted (start, end) offsets. Everything outside them is CODE, which is the conservative direction: a lexer that loses its place over-counts code, and an over-count is a finding a reader can look at rather than a literal that silently escapes.

Span = tuple[int, int]

# Where a string that opened with each quote ends. A one-quote string stops at the end of its line, so an unbalanced quote costs one line, not the rest of the file.
_STRING_END = {
    "'''": re.compile(r"(?:\\.|[^\\])*?'''", re.DOTALL),
    '"""': re.compile(r'(?:\\.|[^\\])*?"""', re.DOTALL),
    "'": re.compile(r"(?:\\.|[^\\\n'])*(?:'|\n|$)"),
    '"': re.compile(r'(?:\\.|[^\\\n"])*(?:"|\n|$)'),
}
_PY_AFTER = re.compile(r"[ \t]*(#[^\n]*)?(\n|;|$)")
# Comments and whole string literals in ONE C-level pass: a `#` inside a string or a quote inside a comment is consumed by the token it belongs to. An unterminated triple quote falls through to the one-quote forms and costs a line.
_PY_TOKEN = re.compile(
    r"#[^\n]*"
    r"|(?<![A-Za-z0-9_])([rRbBuUfF]{0,2})"
    r"('''(?:\\.|[^\\])*?'''|\"\"\"(?:\\.|[^\\])*?\"\"\"|'(?:\\.|[^\\\n'])*(?:'|\n|$)|\"(?:\\.|[^\\\n\"])*(?:\"|\n|$))",
    re.DOTALL,
)


def lex_python(text: str) -> list[Span]:
    """Comments, and strings that are a whole statement on their own (docstrings, and the bare-string comments some modules use).

    Bracket depth is counted in the CODE gaps between tokens with `str.count`, which is exact because strings and comments are never in a gap.
    """
    spans: list[Span] = []
    depth = 0
    gap_from = 0
    for m in _PY_TOKEN.finditer(text):
        start, end = m.start(), m.end()
        if start > gap_from:
            gap = text[gap_from:start]
            depth += (
                gap.count("(")
                + gap.count("[")
                + gap.count("{")
                - gap.count(")")
                - gap.count("]")
                - gap.count("}")
            )
            depth = max(depth, 0)
        gap_from = end
        if m.group(2) is None:
            spans.append((start, end))
            continue
        prefix = m.group(1)
        line_start = text.rfind("\n", 0, start) + 1
        if depth == 0 and "f" not in prefix.lower() and not text[line_start:start].strip():
            # A string first on its line, at bracket depth 0, not continuing the previous line, and followed only by a comment or the end of the statement, is a statement of its own.
            j = line_start - 2
            while j >= 0 and text[j] in " \t\r":
                j -= 1
            continued = j >= 0 and text[j] == "\\"
            if not continued and _PY_AFTER.match(text, end):
                spans.append((start, end))
    return spans


_JS_START = re.compile(r"//|/\*|['\"`]|/|[(\[{]|[)\]}]")
_JS_REGEX_BODY = re.compile(r"/(?:\\.|\[(?:\\.|[^\]\\\n])*\]|[^/\\\n\[])+/[a-z]*")
_JS_REGEX_PRECEDERS = set("(,=:[!&|?{};+-*%<>~^")
_JS_REGEX_KEYWORDS = (
    "return",
    "typeof",
    "case",
    "do",
    "else",
    "in",
    "of",
    "void",
    "yield",
    "await",
)
_JS_TEMPLATE_PART = re.compile(r"\\.|`|\$\{", re.DOTALL)
_JS_WORD_END = re.compile(r"([A-Za-z_$]+)$")


def _js_scan(text: str, pos: int, spans: list[Span], until_brace: bool) -> int:
    """Lex JS/TS from `pos`; with `until_brace`, stop after the `}` that closes a template `${`. Returns the end offset."""
    n = len(text)
    depth = 0
    last_end = pos
    last_sig = ""
    while pos < n:
        m = _JS_START.search(text, pos)
        if not m:
            return n
        between = text[last_end : m.start()].rstrip()
        if between:
            last_sig = between[-16:]
        tok = m.group(0)
        start = m.start()
        if tok == "//":
            end = text.find("\n", start)
            end = n if end < 0 else end
            spans.append((start, end))
            pos = last_end = end
            continue
        if tok == "/*":
            end = text.find("*/", start + 2)
            end = n if end < 0 else end + 2
            spans.append((start, end))
            pos = last_end = end
            continue
        if tok in ("'", '"'):
            end_m = _STRING_END[tok].match(text, m.end())
            pos = last_end = end_m.end() if end_m else n
            last_sig = "a"
            continue
        if tok == "`":
            pos = m.end()
            while pos < n:
                t = _JS_TEMPLATE_PART.search(text, pos)
                if not t:
                    pos = n
                    break
                if t.group(0) == "`":
                    pos = t.end()
                    break
                if t.group(0) == "${":
                    pos = _js_scan(text, t.end(), spans, True)
                    continue
                pos = t.end()
            last_end = pos
            last_sig = "a"
            continue
        if tok == "/":
            word = _JS_WORD_END.search(last_sig)
            if (
                not last_sig
                or last_sig[-1] in _JS_REGEX_PRECEDERS
                or (word and word.group(1) in _JS_REGEX_KEYWORDS)
            ):
                rm = _JS_REGEX_BODY.match(text, start)
                if rm:
                    pos = last_end = rm.end()
                    last_sig = "a"
                    continue
            pos = last_end = m.end()
            last_sig = "/"
            continue
        if tok in "([{":
            depth += 1
        elif tok in ")]}":
            if tok == "}" and until_brace and depth == 0:
                return m.end()
            depth = max(0, depth - 1)
        pos = last_end = m.end()
        last_sig = tok
    return n


def lex_js(text: str) -> list[Span]:
    spans: list[Span] = []
    _js_scan(text, 0, spans, False)
    return spans


def lex_astro(text: str) -> list[Span]:
    """Frontmatter and <script> bodies are JS; the template's prose is its HTML comments and `{/* */}` blocks."""
    spans: list[Span] = []
    body_from = 0
    fm = re.match(r"---[ \t]*\n(.*?)\n---[ \t]*(\n|$)", text, re.DOTALL)
    if fm:
        sub = lex_js(fm.group(1))
        spans.extend((a + fm.start(1), b + fm.start(1)) for a, b in sub)
        body_from = fm.end()
    for script in re.finditer(
        r"<script\b[^>]*>(.*?)</script>", text[body_from:], re.DOTALL | re.IGNORECASE
    ):
        off = body_from + script.start(1)
        spans.extend((a + off, b + off) for a, b in lex_js(script.group(1)))
    spans.extend(
        (body_from + c.start(), body_from + c.end())
        for c in re.finditer(r"<!--.*?-->|\{/\*.*?\*/\}", text[body_from:], re.DOTALL)
    )
    return sorted(spans)


_QUOTE_OPENERS = set(" \t=:[{(,$\"'")


def lex_hash(text: str, block: tuple[str, str] | None = None) -> list[Span]:
    """`#` comments for shell, YAML, TOML, conf, Dockerfile, env and PowerShell.

    A `#` opens a comment at the start of a line or after whitespace, outside quotes. Quotes are tracked within a line only, and a quote opens only at a token start, so an apostrophe in an unquoted YAML scalar ("Don't") cannot swallow the rest of the file. `block` adds a block comment pair (PowerShell `<#` `#>`).
    """
    spans: list[Span] = []
    if block:
        pattern = re.escape(block[0]) + r".*?" + re.escape(block[1])
        spans.extend((b.start(), b.end()) for b in re.finditer(pattern, text, re.DOTALL))
    offset = 0
    for line in text.splitlines(keepends=True):
        quote = ""
        i = 0
        n = len(line)
        while i < n:
            ch = line[i]
            if quote:
                if ch == "\\" and quote == '"':
                    i += 2
                    continue
                if ch == quote:
                    quote = ""
            elif ch in ("'", '"') and (i == 0 or line[i - 1] in _QUOTE_OPENERS):
                quote = ch
            elif ch == "#" and (i == 0 or line[i - 1] in " \t"):
                spans.append((offset + i, offset + len(line.rstrip("\r\n"))))
                break
            i += 1
        offset += n
    return sorted(spans)


def lexer_for(path: str) -> str:
    base = path.rsplit("/", 1)[-1]
    ext = base.rsplit(".", 1)[-1].lower() if "." in base else ""
    if ext == "py":
        return "py"
    if ext in ("ts", "tsx", "js", "mjs", "cjs", "jsonc"):
        return "js"
    if ext == "astro":
        return "astro"
    if ext == "json":
        return "none"
    if ext == "ps1":
        return "ps1"
    return "hash"


def prose_spans(path: str, text: str) -> list[Span]:
    kind = lexer_for(path)
    if kind == "py":
        return lex_python(text)
    if kind == "js":
        return lex_js(text)
    if kind == "astro":
        return lex_astro(text)
    if kind == "ps1":
        return lex_hash(text, ("<#", "#>"))
    if kind == "none":
        return []
    return lex_hash(text)


def in_spans(spans: list[Span], starts: list[int], offset: int) -> bool:
    i = bisect.bisect_right(starts, offset) - 1
    return i >= 0 and spans[i][0] <= offset < spans[i][1]


def classify_file(job: tuple[str, str, list[tuple[int, int]]]) -> tuple[str, list[bool] | None]:
    """(path, one PROSE verdict per (line, col)), or None when the file is gone from the worktree."""
    root, path, sites = job
    try:
        text = (pathlib.Path(root) / path).read_text(encoding="utf-8", errors="replace")
    except (FileNotFoundError, IsADirectoryError):
        return path, None
    spans = prose_spans(path, text)
    starts = [a for a, _ in spans]
    line_starts = [0] + [m.end() for m in re.finditer("\n", text)]
    return path, [
        line - 1 < len(line_starts) and in_spans(spans, starts, line_starts[line - 1] + col)
        for line, col in sites
    ]


# Below this many files a pool costs more to start than it saves; the selftest's trees stay serial.
_POOL_FROM = 64


def classify_all(
    jobs: list[tuple[str, str, list[tuple[int, int]]]],
) -> list[tuple[str, list[bool] | None]]:
    """Lexing is the one CPU-bound phase (about 1.5 s serial on the full tree), and files are independent. Fork, so no worker re-imports anything."""
    if len(jobs) < _POOL_FROM or not hasattr(os, "fork"):
        return [classify_file(j) for j in jobs]
    workers = max(1, min(8, os.cpu_count() or 1))
    with concurrent.futures.ProcessPoolExecutor(
        workers, mp_context=multiprocessing.get_context("fork")
    ) as pool:
        return list(pool.map(classify_file, jobs, chunksize=max(1, len(jobs) // (workers * 4))))


# --------------------------------------------------------------------------- policy ---------------------------------------------------------------------------


def glob_regex(pattern: str) -> re.Pattern[str]:
    """`**` crosses directories, `*` and `?` do not. A pattern with no `/` matches a basename anywhere."""
    if "/" not in pattern:
        pattern = "**/" + pattern
    out = []
    i = 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif pattern[i] == "*":
            out.append("[^/]*")
            i += 1
        elif pattern[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(pattern[i]))
            i += 1
    return re.compile("^" + "".join(out) + "$")


@dataclasses.dataclass
class Policy:
    raw: dict[str, Any]
    floor: int
    r2a: int
    r2b: int
    distance: int
    code_ext: frozenset[str]
    code_basenames: list[re.Pattern[str]]
    host_suffixes: list[str]
    path_prefixes: list[str]
    image_registries: list[str]
    owned_images: list[str]
    owners: list[str]
    reserved_hosts: list[str]
    reserved_suffixes: list[str]
    exemptions: list[dict[str, Any]]
    carriers: list[dict[str, Any]]
    sources: dict[str, list[str]]
    symbols: dict[str, str]
    mirrors: dict[str, str]
    exact_stem: dict[str, str]


def _reasoned(rows: list[dict[str, Any]], field: str, what: str) -> dict[str, str]:
    """`{row[field]: row["reason"]}`, refusing a row whose reason is too short to be an argument."""
    out: dict[str, str] = {}
    for row in rows:
        if len(str(row.get("reason", ""))) < 20:
            raise RefusalError(
                "%s %r needs a reason of at least 20 characters" % (what, row.get(field))
            )
        out[str(row[field])] = str(row["reason"])
    return out


def load_policy(root: pathlib.Path) -> Policy:
    path = root / POLICY_REL
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise RefusalError(
            "%s is missing; the gate has no namespaces to police" % POLICY_REL
        ) from None
    except json.JSONDecodeError as exc:
        raise RefusalError("%s is not JSON: %s" % (POLICY_REL, exc)) from None
    try:
        owned = raw["owned"]
        reserved = raw["reserved"]
        for row in raw["exemptions"]:
            if len(str(row.get("reason", ""))) < 20:
                raise RefusalError(
                    "exemption %r needs a reason of at least 20 characters" % row.get("glob")
                )
            row["_re"] = glob_regex(row["glob"])
            row["_except"] = set(row.get("except", []))
        for row in raw["carriers"]:
            if len(str(row.get("reason", ""))) < 20:
                raise RefusalError(
                    "carrier %r needs a reason of at least 20 characters" % row.get("path")
                )
            row["_lines"] = re.compile(row["lines"]) if row.get("lines") else None
        return Policy(
            raw=raw,
            floor=int(raw["floor"]),
            r2a=int(raw["thresholds"]["R2a"]),
            r2b=int(raw["thresholds"]["R2b"]),
            distance=int(raw["thresholds"]["R5_distance"]),
            code_ext=frozenset(raw["scope"]["extensions"]),
            code_basenames=[glob_regex(g) for g in raw["scope"]["basenames"]],
            host_suffixes=[s.lower() for s in owned["host_suffixes"]],
            path_prefixes=sorted(owned["path_prefixes"], key=len, reverse=True),
            image_registries=list(raw["third_party"]["image_registries"]),
            owned_images=list(owned["image_prefixes"]),
            owners=list(owned["github_owners"]),
            reserved_hosts=[h["host"].lower() for h in reserved["hosts"]],
            reserved_suffixes=[h["suffix"].lower() for h in reserved["suffixes"]],
            exemptions=list(raw["exemptions"]),
            carriers=list(raw["carriers"]),
            sources={k: list(v) for k, v in raw["sources"].items() if not k.startswith("$")},
            symbols=dict(raw["symbols"]),
            mirrors=dict(raw.get("region_mirrors", {})),
            exact_stem=_reasoned(raw.get("exact_stem", []), "key", "exact_stem"),
        )
    except (KeyError, TypeError, ValueError, re.error) as exc:
        raise RefusalError("%s is malformed: %r" % (POLICY_REL, exc)) from None


# --------------------------------------------------------------------------- detectors ---------------------------------------------------------------------------


@dataclasses.dataclass
class Hit:
    path: str
    line: int
    col: int
    detector: str  # url | host | email | path | slug | image | port | token
    raw: str
    key: str  # the normalized literal: a stem, a host, an address, a namespace root
    owned: bool
    host: str = ""
    url_path: str = ""
    prose: bool = False


class Detectors:
    def __init__(self, policy: Policy, entries: list[Entry]) -> None:
        self.policy = policy
        alt = "|".join(re.escape(s) for s in policy.host_suffixes)
        self.owned_host_re = re.compile(r"^(?:[a-z0-9-]+\.)*(?:%s)$" % alt)
        # `|` ends a URL: it is a sed delimiter or a shell pipe far more often than a character in a path. `}` ends one too (RFC 3986 never allows it unencoded): without that, the closing brace of `${X:-https://host}` became part of the host and the literal escaped.
        self.url = re.compile(r"\b[A-Za-z][A-Za-z0-9+.-]*://[^\s'\"`<>\\)\]|}]+")
        self.email = re.compile(
            r"(?<![\w.%%+])([A-Za-z0-9][A-Za-z0-9._%%+-]*@(?:[A-Za-z0-9-]+\.)*(?:%s))(?![\w-]|\.[A-Za-z])"
            % alt,
            re.IGNORECASE,
        )
        self.host = re.compile(
            r"(?<![\w.@/-])((?:[a-z0-9-]+\.)*(?:%s))(?![\w-]|\.[a-z])" % alt, re.IGNORECASE
        )
        palt = "|".join(re.escape(p) for p in policy.path_prefixes)
        self.path = re.compile(r"(?<![\w.~-])(%s)(?=$|[^\w.-])" % palt)
        ralt = "|".join(re.escape(r) for r in policy.image_registries)
        self.image = re.compile(
            r"(?<![\w./-])((?:%s)/[a-z0-9][a-z0-9._/-]*?)(?=[:@][\w.-]|[^\w./-]|$)" % ralt
        )
        oalt = "|".join(re.escape(o) for o in policy.owners)
        self.slug = re.compile(
            r"(?:(?<=github\.com/)|(?<=github\.com:)|(?<=repos/)|(?<![\w@./:~-]))((?:%s)/[A-Za-z0-9_.-]*[A-Za-z0-9_])"
            % oalt
        )
        ports = sorted({e.value for e in entries if e.kind == "port"})
        self.port = None
        if ports:
            self.port = re.compile(
                r"(?:(?:localhost|127\.0\.0\.1|0\.0\.0\.0|\[::1\]|host\.docker\.internal)\s*:\s*"
                r"|\b(?:[A-Z0-9_]*PORT[A-Z0-9_]*|[a-z][A-Za-z0-9]*Port[A-Za-z0-9]*|port[A-Za-z0-9_]*|[a-z0-9_]+_port)\b['\"]?\s*[:=]-?\s*['\"]?)"
                r"(%s)(?!\d)" % "|".join(ports)
            )
        tokens = sorted({e.value for e in entries if e.kind == "token"}, key=len, reverse=True)
        self.token = (
            re.compile(r"(?<![\w.-])(%s)(?![\w-])" % "|".join(re.escape(t) for t in tokens))
            if tokens
            else None
        )
        prefilter = [re.escape(s) for s in policy.host_suffixes]
        prefilter += [re.escape(p) for p in policy.path_prefixes]
        prefilter += [re.escape(r) + "/" for r in policy.image_registries]
        prefilter += [re.escape(o) + "/" for o in policy.owners]
        prefilter += ["[a-z]+://"]
        prefilter += [re.escape(t) for t in tokens] + [re.escape(p) for p in ports]
        self.prefilter = "|".join(prefilter)

    def owned_host(self, host: str) -> bool:
        return bool(self.owned_host_re.match(host))

    def reserved(self, host: str) -> bool:
        p = self.policy
        if host in p.reserved_hosts:
            return True
        return any(
            host == s.lstrip(".") or host.endswith(s if s.startswith(".") else "." + s)
            for s in p.reserved_suffixes
        )

    def scan_line(self, path: str, lineno: int, text: str) -> list[Hit]:
        hits: list[Hit] = []
        taken: list[Span] = []

        def add(start: int, end: int, hit: Hit) -> None:
            for a, b in taken:
                if start < b and a < end:
                    return
            taken.append((start, end))
            hits.append(hit)

        low = text.lower()
        owned_host_here = any(s in low for s in self.policy.host_suffixes)
        for m in self.url.finditer(text) if "://" in text else ():
            url = normalize_url(m.group(0))
            if url is None or not url.scheme.startswith("http"):
                continue
            if self.owned_host(url.host):
                add(
                    m.start(),
                    m.end(),
                    Hit(
                        path,
                        lineno,
                        m.start(),
                        "url",
                        m.group(0),
                        url.stem,
                        True,
                        url.host,
                        url.path,
                    ),
                )
                continue
            hostpath = url.host + url.path
            owned_image = next(
                (
                    i
                    for i in self.policy.owned_images
                    if hostpath == i or hostpath.startswith(i + "/")
                ),
                None,
            )
            if owned_image:
                parts = hostpath.split("/")
                key = "/".join(parts[:3]) if len(parts) >= 3 else hostpath
                add(
                    m.start(), m.end(), Hit(path, lineno, m.start(), "image", m.group(0), key, True)
                )
                continue
            if url.host == "github.com" and any(
                url.path.startswith("/" + o + "/") for o in self.policy.owners
            ):
                continue  # the slug detector below owns it
            if self.reserved(url.host) or re.match(r"^[\d.]+$|^\[", url.host):
                continue
            add(
                m.start(),
                m.end(),
                Hit(
                    path, lineno, m.start(), "url", m.group(0), url.stem, False, url.host, url.path
                ),
            )
        # After URLs: a userinfo part (`user@host` inside a URL) is not an address.
        for m in self.email.finditer(text) if owned_host_here and "@" in text else ():
            addr = m.group(1).lower()
            add(
                m.start(1),
                m.end(1),
                Hit(
                    path,
                    lineno,
                    m.start(1),
                    "email",
                    m.group(1),
                    addr,
                    True,
                    host=addr.split("@")[1],
                ),
            )
        for m in self.host.finditer(text) if owned_host_here else ():
            host = m.group(1).lower()
            add(
                m.start(1),
                m.end(1),
                Hit(path, lineno, m.start(1), "host", m.group(1), host, True, host),
            )
        for m in (
            self.path.finditer(text) if any(x in text for x in self.policy.path_prefixes) else ()
        ):
            add(
                m.start(1),
                m.end(1),
                Hit(path, lineno, m.start(1), "path", m.group(1), m.group(1), True),
            )
        for m in (
            self.image.finditer(text)
            if any(x in text for x in self.policy.image_registries)
            else ()
        ):
            repo = m.group(1).rstrip("/")
            owned = any(repo == i or repo.startswith(i + "/") for i in self.policy.owned_images)
            add(
                m.start(1),
                m.end(1),
                Hit(path, lineno, m.start(1), "image", m.group(1), repo, owned),
            )
        for m in (
            self.slug.finditer(text) if any(o + "/" in text for o in self.policy.owners) else ()
        ):
            if _GO_IMPORT.search(text, 0, m.start(1)):
                continue  # a Go module or import path is code identity, like `@rediacc/shared`, not a repository reference
            slug = re.sub(r"\.git$", "", m.group(1))
            add(
                m.start(1),
                m.end(1),
                Hit(path, lineno, m.start(1), "slug", m.group(1), slug.lower(), True),
            )
        if self.port:
            # Not through `add`: a port sits inside a URL span (`localhost:4800`) the URL detector already took.
            hits.extend(
                Hit(path, lineno, m.start(1), "port", m.group(1), m.group(1), True)
                for m in self.port.finditer(text)
            )
        if self.token:
            for m in self.token.finditer(text):
                add(
                    m.start(1),
                    m.end(1),
                    Hit(path, lineno, m.start(1), "token", m.group(1), m.group(1), True),
                )
        return hits


_UPPER_TOKEN = re.compile(r"\b[A-Z][A-Z0-9_]*\b")

# `github.com/` with no scheme or `git@` before it, ending right where the slug starts.
_GO_IMPORT = re.compile(r"(?<![/@:\w.])github\.com/$")


def match_entry(hit: Hit, entries: list[Entry]) -> Entry | None:
    """The registered entry a hit is a copy of, or None. WK_ entries win over region entries for the same host."""
    best: Entry | None = None
    for e in entries:
        ok = False
        if hit.detector in ("url", "host") and e.kind in ("url", "host"):
            if hit.host == e.host and e.exact:
                ok = hit.detector == "url" and hit.url_path == e.path
            elif hit.host == e.host:
                ok = not e.path or (hit.url_path == e.path or hit.url_path.startswith(e.path + "/"))
        elif hit.detector == "email" and e.kind == "email":
            ok = hit.key == e.value.lower()
        elif (hit.detector == "path" and e.kind == "path") or (
            hit.detector == "image" and e.kind == "image"
        ):
            ok = hit.key == e.value or hit.key.startswith(e.value + "/")
        elif hit.detector == "slug" and e.kind == "slug":
            ok = hit.key == e.value.lower()
        elif hit.detector == e.kind and hit.detector in ("port", "token"):
            ok = hit.key == e.value
        if ok and (
            best is None or (best.is_region and not e.is_region) or len(e.value) > len(best.value)
        ):
            best = e
    return best


def r2_key(hit: Hit, policy: Policy) -> str:
    """What an UNREGISTERED hit is counted under: a host, an address, a namespace root, a slug, an image repository, a URL stem."""
    if hit.detector == "url" and hit.owned:
        return hit.host
    if hit.detector == "path":
        return next(
            (p for p in policy.path_prefixes if hit.key == p or hit.key.startswith(p + "/")),
            hit.key,
        )
    return hit.key


# --------------------------------------------------------------------------- the scan ---------------------------------------------------------------------------


@dataclasses.dataclass
class Finding:
    rule: str
    path: str
    line: int
    message: str
    literal: str = ""

    def render(self) -> str:
        where = "%s:%d" % (self.path, self.line) if self.line else self.path
        return "%s: [%s] %s" % (where, self.rule, self.message)


@dataclasses.dataclass
class Result:
    findings: list[Finding]
    stats: dict[str, int]


class GitCall:
    """A git command started now and read later, so the three passes (ls-files, the prefilter, the consumer grep) overlap instead of queueing."""

    def __init__(self, root: pathlib.Path, *args: str) -> None:
        env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        self.args = args
        self.proc = subprocess.Popen(
            ["git", "-C", str(root), "-c", "core.quotepath=off", *args],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        )

    def result(self) -> bytes:
        out, err = self.proc.communicate()
        # 1 is git grep's "no match"; anything else means git could not answer.
        if self.proc.returncode not in (0, 1):
            raise RefusalError(
                "git %s failed (%d): %s"
                % (
                    " ".join(self.args[:2]),
                    self.proc.returncode,
                    err.decode(errors="replace").strip(),
                )
            )
        return out


def language_of(path: str) -> str:
    base = path.rsplit("/", 1)[-1]
    ext = base.rsplit(".", 1)[-1].lower() if "." in base else ""
    if ext in ("ts", "tsx", "js", "mjs", "cjs", "astro"):
        return "worker" if path.startswith("workers/") else "ts"
    if ext == "py":
        return "py"
    if ext in ("sh", "bash", "env") or base.startswith(".env"):
        return "sh"
    if path.startswith(".github/") and ext in ("yml", "yaml"):
        return "workflow"
    return "config"


def symbol_for(entry: Entry, path: str, policy: Policy) -> str:
    if entry.is_region:
        return policy.symbols["region"].replace("{value}", entry.value)
    template = policy.symbols[language_of(path)]
    return template.replace("{key}", entry.key).replace("{name}", entry.name)


def render_projection(values: dict[str, str]) -> str:
    """The TS projection of the registry: one `export const WK_NAME` per key, digit-only values as numbers.

    ONE BINDING PER KEY, NOT ONE OBJECT. A `WELL_KNOWN = {...}` object was the first draft, and the CLI bundle and both worker bundles then carried all of it (operator address, internal repositories, CI-only mirrors) because no bundler drops unread properties of an object literal. A separate `const` per key is dropped by every bundler when nothing imports it. The `WK_` spelling is the one bash and the workflows already use.
    """
    lines = [
        "// AUTO-GENERATED by .ci/scripts/quality/check_literal_sources.py --write - DO NOT EDIT",
        "// Source: %s, the only place these values are written; check:ci-literal-sources (R4) holds this file equal to it."
        % REGISTRY_REL,
        "",
    ]
    for key, value in values.items():
        rendered = value if value.isdigit() else "'%s'" % value
        lines.append("export const %s = %s;" % (key, rendered))
    lines.append("")
    return "\n".join(lines)


def _sh_quote(value: str) -> str:
    """A single-quoted bash word: nothing inside it expands, and an embedded `'` closes, escapes and reopens."""
    return "'%s'" % value.replace("'", "'\\''")


def render_sh_projection(values: dict[str, str]) -> str:
    """The bash projection of the registry: one guarded assignment per key, then one `export`.

    SHELL WINS. `[ -n "${WK_X:-}" ] || WK_X='...'` keeps a value the environment already holds and fills only an absent one, which is the operator ruling for bash and what env_file_load does for every other env file. An EMPTY value counts as absent, the rule rediacc_ci.core.env states ("AN EMPTY ENVIRONMENT VALUE DOES NOT WIN"), so `WK_X= ./script` gets the registry value rather than a blank.

    NON-EXECUTING BY CONSTRUCTION. Every value is a single-quoted word, so a `$`, a backtick or a space in the registry is data. That is what lets a script source this file under a scrubbed PATH with no python3, where env_file_load cannot run: sourcing it needs nothing but bash.
    """
    lines = [
        "# AUTO-GENERATED by .ci/scripts/quality/check_literal_sources.py --write - DO NOT EDIT",
        "# Source: %s, the only place these values are written; check:ci-literal-sources (R4) holds this file equal to it."
        % REGISTRY_REL,
        "# shellcheck shell=bash",
        "# The shell wins: an exported non-empty WK_* is kept, an absent or empty one is filled. Values are single-quoted, so nothing in them executes.",
        "",
    ]
    for key, value in values.items():
        lines.append('[ -n "${%s:-}" ] || %s=%s' % (key, key, _sh_quote(value)))
    lines.append("export %s" % " ".join(values))
    lines.append("")
    return "\n".join(lines)


# Each projection and its renderer. `--write` emits from this table and R4 checks against it, so there is one renderer per file and no second copy of the format to drift.
PROJECTIONS = (
    (PROJECTION_REL, render_projection),
    (SH_PROJECTION_REL, render_sh_projection),
)


_READER_LINE = re.compile(
    r"^([A-Z][A-Z0-9_]*): (?:str|int) = (?:int\()?_get\(\"(WK_[A-Z0-9_]+)\"\)\)?$", re.MULTILINE
)


def carrier_findings(
    root: pathlib.Path, policy: Policy, by_key: dict[str, Entry], tracked_set: set[str]
) -> list[Finding]:
    """R3 for carriers: each row names a tracked file that still contains every value it declares."""
    out: list[Finding] = []
    for row in policy.carriers:
        path = row["path"]
        if path not in tracked_set:
            out.append(
                Finding(
                    "R3", POLICY_REL, 0, "carrier %s is not a tracked file; drop its row" % path
                )
            )
            continue
        try:
            text = (root / path).read_text(encoding="utf-8", errors="replace")
        except FileNotFoundError:
            out.append(
                Finding("R3", POLICY_REL, 0, "carrier %s is missing from the worktree" % path)
            )
            continue
        for key in row["keys"]:
            entry = by_key.get(key)
            if entry is None:
                out.append(
                    Finding(
                        "R3",
                        POLICY_REL,
                        0,
                        "carrier %s names %s, which is not registered" % (path, key),
                    )
                )
            elif entry.needle not in text:
                message = "carrier no longer contains %s (%s); it has drifted from the registry" % (
                    entry.needle,
                    key,
                )
                out.append(Finding("R3", path, 0, message, key))
    return out


def policy_liveness(
    policy: Policy, exemption_used: collections.Counter[str], tracked_set: set[str]
) -> list[Finding]:
    """R3 for the policy itself: every exemption is the first match for some tracked file, every `except` and every source is tracked."""
    out = [
        Finding(
            "R3",
            POLICY_REL,
            0,
            "exemption %s is the first match for no tracked file (dead, or shadowed by an earlier row); delete it"
            % row["glob"],
        )
        for row in policy.exemptions
        if not exemption_used[row["glob"]]
    ]
    out.extend(
        Finding(
            "R3",
            POLICY_REL,
            0,
            "exemption %s excepts %s, which is not tracked" % (row["glob"], keep),
        )
        for row in policy.exemptions
        for keep in row["_except"]
        if keep not in tracked_set
    )
    out.extend(
        Finding("R3", POLICY_REL, 0, "source %s is not a tracked file" % spath)
        for spath in policy.sources
        if spath not in tracked_set
    )
    return out


def reader_findings(reader: str, values: dict[str, str]) -> list[Finding]:
    """R4 for rediacc_ci/well_known.py: exactly one `NAME: str = _get("WK_NAME")` line per registry key, in both directions."""
    out: list[Finding] = []
    exported: dict[str, str] = {}
    for m in _READER_LINE.finditer(reader):
        if m.group(1) != m.group(2)[3:]:
            out.append(
                Finding(
                    "R4",
                    READER_REL,
                    0,
                    "%s reads %s; the name must be the key without WK_" % (m.group(1), m.group(2)),
                )
            )
        exported[m.group(2)] = m.group(1)
    out.extend(
        Finding("R4", READER_REL, 0, "does not export %s as %s" % (key, key[3:]))
        for key in values
        if key not in exported
    )
    out.extend(
        Finding(
            "R4", READER_REL, 0, "exports %s, which %s no longer declares" % (key, REGISTRY_REL)
        )
        for key in exported
        if key not in values
    )
    return out


def run(root: pathlib.Path) -> Result:
    started = time.monotonic()
    policy = load_policy(root)
    try:
        values = well_known.load(root / REGISTRY_REL)
    except well_known.RegistryError as exc:
        raise RefusalError(str(exc)) from None
    entries = [
        dataclasses.replace(e, exact=e.key in policy.exact_stem)
        for e in (entry_for(k, v) for k, v in values.items())
    ]
    try:
        regions = json.loads((root / REGIONS_REL).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        raise RefusalError(
            "%s is unreadable (%s); the region hosts have no source" % (REGIONS_REL, exc)
        ) from None
    regional = region_entries(regions)
    if not regional:
        raise RefusalError("%s declares no region hosts; the second source is empty" % REGIONS_REL)
    all_entries = entries + regional
    detectors = Detectors(policy, all_entries)
    findings: list[Finding] = []

    # One prefilter pass over the whole tree. History and generated outputs are excluded by pathspec, so their megabyte lines never reach Python.
    # A row with an `except` list is NOT excluded here: a git pathspec exclude always beats an include, so the excepted file went unread (breakpoint.conf did, until a control caught it).
    excludes = [
        ":(exclude,glob)%s" % (row["glob"] if "/" in row["glob"] else "**/" + row["glob"])
        for row in policy.exemptions
        if not row.get("prose_checked") and not row["_except"]
    ]
    ls_call = GitCall(root, "ls-files", "-z")
    # -P (PCRE, JIT) measured 0.5 s against 1.6 s for -E on this pattern. A git built without PCRE falls back to -E below: slower, same verdict.
    grep_args = ("grep", "-z", "-n", "-I", "-i")
    grep_call = GitCall(root, *grep_args, "-P", detectors.prefilter, "--", ".", *excludes)
    consumer_args = ("grep", "-z", "-l", r"WK_[A-Z]|well_known", "--", ".", *excludes)
    consumer_call = GitCall(root, "grep", "-P", *consumer_args[1:])

    tracked = [p for p in ls_call.result().decode("utf-8", "replace").split("\0") if p]
    tracked_set = set(tracked)
    # The FIRST exemption that matches each tracked path, computed once. An exemption that never comes first is dead weight under R3.
    exempt_of: dict[str, dict[str, Any] | None] = {}
    exemption_used: collections.Counter[str] = collections.Counter()
    for p in tracked:
        row = next(
            (r for r in policy.exemptions if r["_re"].match(p) and p not in r["_except"]), None
        )
        exempt_of[p] = row
        if row is not None:
            exemption_used[row["glob"]] += 1

    def exemption_of(path: str) -> dict[str, Any] | None:
        return exempt_of.get(path)

    def in_code_scope(path: str) -> bool:
        base = path.rsplit("/", 1)[-1]
        ext = base.rsplit(".", 1)[-1].lower() if "." in base else ""
        return ext in policy.code_ext or any(r.match(base) for r in policy.code_basenames)

    source_keys: dict[str, set[str]] = {}
    for spath, keys in policy.sources.items():
        source_keys[spath] = set(keys)
    scope = [
        p for p in tracked if in_code_scope(p) and exemption_of(p) is None and p not in source_keys
    ]
    if len(scope) < policy.floor:
        for call in (grep_call, consumer_call):
            call.proc.kill()
            call.proc.communicate()
        raise RefusalError(
            "only %d in-scope file(s), under the floor of %d; the gate is not seeing the tree, and its green would mean nothing"
            % (len(scope), policy.floor)
        )
    scope_set = set(scope)

    try:
        raw = grep_call.result()
    except RefusalError as exc:
        if "perl" not in str(exc).lower() and "pcre" not in str(exc).lower():
            raise
        raw = GitCall(root, *grep_args, "-E", detectors.prefilter, "--", ".", *excludes).result()
    hits_by_file: dict[str, list[Hit]] = collections.defaultdict(list)
    candidate_lines = 0
    for record in raw.split(b"\n"):
        if not record:
            continue
        parts = record.split(b"\0", 2)
        if len(parts) != 3:
            continue
        path = parts[0].decode("utf-8", "replace")
        if path in source_keys:
            continue
        ex = exemption_of(path)
        if ex is not None and not ex.get("prose_checked"):
            continue
        candidate_lines += 1
        text = parts[2].decode("utf-8", "replace")
        if len(text) > 20000:
            text = text[:20000]
        for hit in detectors.scan_line(path, int(parts[1]), text):
            hits_by_file[path].append(hit)
    if candidate_lines == 0:
        raise RefusalError(
            "the prefilter matched no line in the tree; the gate is not seeing the tree"
        )

    # A file is lexed only when the CODE/PROSE split of one of its hits can change a verdict: a registered value (R1), or an unregistered key whose file count, counting prose too, already reaches its threshold. R5 reads code and prose alike and needs no split.
    def matters_for_code(hit: Hit) -> bool:
        if match_entry(hit, all_entries) is not None:
            return True
        return upper_bound[r2_key(hit, policy)] >= (policy.r2a if hit.owned else policy.r2b)

    upper_bound: collections.Counter[str] = collections.Counter()
    for path, hits in hits_by_file.items():
        if path in scope_set:
            for key in {r2_key(h, policy) for h in hits}:
                upper_bound[key] += 1

    lexed = 0
    code_hits = prose_hits = 0
    jobs: list[tuple[str, str, list[tuple[int, int]]]] = []
    for path, hits in hits_by_file.items():
        if path not in scope_set:
            for h in hits:
                h.prose = True
            prose_hits += len(hits)
        elif any(matters_for_code(h) for h in hits):
            jobs.append((str(root), path, [(h.line, h.col) for h in hits]))
    for path, verdicts in classify_all(jobs):
        if verdicts is None:
            continue
        lexed += 1
        for h, prose in zip(hits_by_file[path], verdicts, strict=True):
            h.prose = prose
            if prose:
                prose_hits += 1
            else:
                code_hits += 1

    carriers_by_path: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for row in policy.carriers:
        carriers_by_path[row["path"]].append(row)

    def carried(path: str, entry: Entry, line_text: str) -> bool:
        return any(
            entry.key in row["keys"] and (row["_lines"] is None or row["_lines"].search(line_text))
            for row in carriers_by_path.get(path, [])
        )

    line_cache: dict[str, list[str]] = {}

    def line_of(path: str, n: int) -> str:
        if path not in line_cache:
            try:
                line_cache[path] = (
                    (root / path).read_text(encoding="utf-8", errors="replace").splitlines()
                )
            except (FileNotFoundError, IsADirectoryError):
                line_cache[path] = []
        lines = line_cache[path]
        return lines[n - 1] if 0 < n <= len(lines) else ""

    # R1 and the R2 tallies.
    r2_files: dict[str, set[str]] = collections.defaultdict(set)
    r2_sites: dict[str, list[Hit]] = collections.defaultdict(list)
    for path, hits in hits_by_file.items():
        if path not in scope_set:
            continue
        for h in hits:
            if h.prose:
                continue
            entry = match_entry(h, all_entries)
            if entry is not None:
                if carriers_by_path.get(path) and carried(path, entry, line_of(path, h.line)):
                    continue
                findings.append(
                    Finding(
                        "R1",
                        path,
                        h.line,
                        "%s is %s's value; use %s"
                        % (
                            h.raw,
                            entry.key if not entry.is_region else REGIONS_REL,
                            symbol_for(entry, path, policy),
                        ),
                        entry.key,
                    )
                )
                continue
            key = r2_key(h, policy)
            r2_files[key].add(path)
            r2_sites[key].append(h)
    for key, files in sorted(r2_files.items()):
        sites = r2_sites[key]
        owned = sites[0].owned
        threshold = policy.r2a if owned else policy.r2b
        if len(files) >= threshold:
            rule = "R2a" if owned else "R2b"
            what = "owned literal" if owned else "third-party literal"
            message = (
                "%s %s appears in CODE in %d files (threshold %d); register it in %s and read it from there"
                % (what, key, len(files), threshold, REGISTRY_REL)
            )
            findings.extend(Finding(rule, h.path, h.line, message, key) for h in sites)

    # R5: near misses, in code and prose alike.
    known = {e.host for e in all_entries if e.kind in ("url", "host")} | {
        e.value.lower() for e in all_entries if e.kind == "email"
    }
    for path, hits in hits_by_file.items():
        for h in hits:
            if not h.owned or h.detector not in ("url", "host", "email"):
                continue
            candidate = h.key if h.detector == "email" else h.host
            if candidate in known:
                continue
            twin = next(
                (k for k in sorted(known) if near_miss(candidate, k, policy.distance)), None
            )
            if twin is not None:
                message = "%s is a near miss of the registered %s; a typo or a stale host" % (
                    candidate,
                    twin,
                )
                findings.append(Finding("R5", path, h.line, message, candidate))

    # R3: liveness.
    try:
        consumer_raw = consumer_call.result()
    except RefusalError as exc:
        if "perl" not in str(exc).lower() and "pcre" not in str(exc).lower():
            raise
        consumer_raw = GitCall(root, "grep", "-E", *consumer_args[1:]).result()
    not_consumers = {
        REGISTRY_REL,
        *(rel for rel, _render in PROJECTIONS),
        READER_REL,
        POLICY_REL,
        *GATE_RELS,
    }
    consumed: set[str] = set()
    consumers = 0
    for path in consumer_raw.decode("utf-8", "replace").split("\0"):
        if not path or path in not_consumers:
            continue
        try:
            text = (root / path).read_text(encoding="utf-8", errors="replace")
        except (FileNotFoundError, IsADirectoryError):
            continue
        # A consumer names the key (bash, workflows, TS), `well_known.NAME`, or imports NAME from rediacc_ci.well_known (Python).
        # ONE token pass per file. The first version ran two uncompiled searches per entry per file, 42 x 342 of them, and took 15 of the gate's 18 s once the drain made 342 files consumers.
        tokens = set(_UPPER_TOKEN.findall(text))
        py_reader = "well_known" in text
        here = {e.key for e in entries if e.key in tokens or (py_reader and e.name in tokens)}
        consumed |= here
        consumers += bool(here)
    findings.extend(
        Finding(
            "R3",
            REGISTRY_REL,
            0,
            "%s has no consumer; delete it, or read it where its value is needed" % e.key,
            e.key,
        )
        for e in entries
        if e.key not in consumed
    )
    by_key = {e.key: e for e in all_entries}
    findings.extend(carrier_findings(root, policy, by_key, tracked_set))
    findings.extend(policy_liveness(policy, exemption_used, tracked_set))
    findings.extend(
        Finding(
            "R3", POLICY_REL, 0, "exact_stem names %s, which is not a registered URL entry" % key
        )
        for key in policy.exact_stem
        if key not in by_key or by_key[key].kind != "url"
    )

    # R4: projections and mirrors.
    for rel, render in PROJECTIONS:
        try:
            have = (root / rel).read_text(encoding="utf-8")
        except FileNotFoundError:
            have = ""
        if have != render(values):
            findings.append(
                Finding(
                    "R4",
                    rel,
                    0,
                    "stale projection of %s; run check_literal_sources.py --write" % REGISTRY_REL,
                )
            )
    try:
        constants = (root / CONSTANTS_REL).read_text(encoding="utf-8")
    except FileNotFoundError:
        constants = ""
    if not re.search(
        r"^[^#\n]*%s" % re.escape(SH_PROJECTION_REL.rsplit("/", 1)[-1]), constants, re.MULTILINE
    ):
        findings.append(
            Finding(
                "R4",
                CONSTANTS_REL,
                0,
                "does not source %s; bash would see none of the registry" % SH_PROJECTION_REL,
            )
        )
    try:
        reader = (root / READER_REL).read_text(encoding="utf-8")
    except FileNotFoundError:
        reader = ""
    findings.extend(reader_findings(reader, values))
    for key, field in policy.mirrors.items():
        e = by_key.get(key)
        want_host = default_region_domain(regions) if field == "default.domain" else ""
        if e is None or e.host != want_host:
            findings.append(
                Finding(
                    "R4",
                    REGISTRY_REL,
                    0,
                    "%s must be https://%s, the domain of the default region in %s"
                    % (key, want_host, REGIONS_REL),
                    key,
                )
            )

    stats = {
        "tracked": len(tracked),
        "scope": len(scope),
        "candidate_lines": candidate_lines,
        "files_with_hits": len(hits_by_file),
        "lexed": lexed,
        "code_hits": code_hits,
        "prose_hits": prose_hits,
        "entries": len(entries),
        "region_entries": len(regional),
        "carriers": len(policy.carriers),
        "exemptions": len(policy.exemptions),
        "consumers": consumers,
        "ms": int((time.monotonic() - started) * 1000),
    }
    return Result(findings, stats)


# --------------------------------------------------------------------------- output ---------------------------------------------------------------------------


def shape(stats: dict[str, int]) -> str:
    return (
        "%(scope)d in-scope files of %(tracked)d tracked, %(candidate_lines)d candidate lines in %(files_with_hits)d files, "
        "%(lexed)d lexed, %(code_hits)d CODE / %(prose_hits)d PROSE hits, %(entries)d registry + %(region_entries)d region entries, "
        "%(consumers)d consumer files, %(carriers)d carriers, %(exemptions)d exemptions, %(ms)d ms"
        % stats
    )


def summary(findings: list[Finding]) -> list[str]:
    per_rule = collections.Counter(f.rule for f in findings)
    per_literal = collections.Counter("%s %s" % (f.rule, f.literal) for f in findings if f.literal)
    out = ["by rule: " + ", ".join("%s=%d" % kv for kv in sorted(per_rule.items()))]
    out.append("top literals:")
    out += ["  %5d  %s" % (n, lit) for lit, n in per_literal.most_common(25)]
    return out


def parse_paths(args: list[str]) -> list[str]:
    """Every value after every `--paths`, up to the next `--flag`. Repeatable, and order-free with respect to the other flags."""
    out: list[str] = []
    taking = False
    for a in args:
        if a == "--paths":
            taking = True
        elif a.startswith("--"):
            taking = False
        elif taking:
            out.append(a)
    return out


def path_matcher(specs: list[str]) -> re.Pattern[str] | None:
    """One pattern for all `--paths` specs: a glob as written, and a plain path also as a directory (`packages/cli` covers `packages/cli/**`)."""
    if not specs:
        return None
    parts = []
    for spec in specs:
        parts.append(glob_regex(spec).pattern)
        if not any(c in spec for c in "*?"):
            parts.append(glob_regex(spec.rstrip("/") + "/**").pattern)
    return re.compile("|".join("(?:%s)" % p for p in parts))


def report(result: Result, globs: list[str]) -> None:
    pat = path_matcher(globs)
    shown = [f for f in result.findings if pat is None or pat.match(f.path)]
    by_file: dict[str, list[Finding]] = collections.defaultdict(list)
    for f in shown:
        by_file[f.path].append(f)
    for path in sorted(by_file):
        print(path)
        for f in sorted(by_file[path], key=lambda x: (x.line, x.rule)):
            print(
                "  %s%s [%s] %s"
                % ("" if not f.line else str(f.line), ":" if f.line else "-", f.rule, f.message)
            )
    print()
    print(
        "%d finding(s) in %d file(s)%s"
        % (len(shown), len(by_file), " (of %d in the tree)" % len(result.findings) if pat else "")
    )
    for line in summary(shown):
        print(line)
    print(shape(result.stats))


def main(argv: list[str] | None = None) -> int:
    args = list(argv or [])
    if "--selftest" in args:
        return 1 if selftest() else 0
    try:
        root = paths.repo_root()
    except paths.RootError as exc:
        log.error("literal sources: %s" % exc)
        return 1
    if "--write" in args:
        try:
            values = well_known.load(root / REGISTRY_REL)
        except well_known.RegistryError as exc:
            log.error("literal sources: %s" % exc)
            return 1
        for rel, render in PROJECTIONS:
            (root / rel).write_text(render(values), encoding="utf-8")
            log.success("literal sources: wrote %s from %d registry entries" % (rel, len(values)))
        return 0
    rc = controls_first("literal sources", selftest)
    if rc:
        return rc
    try:
        result = run(root)
    except RefusalError as exc:
        log.error("literal sources: %s" % exc)
        return 1
    if "--report" in args:
        globs = parse_paths(args)
        report(result, globs)
        return 1 if result.findings else 0
    if result.findings:
        for f in result.findings:
            log.error("  " + f.render())
        for line in summary(result.findings):
            log.error(line)
        log.error(
            "literal sources: %d finding(s). Use the symbol each finding names; register a new value in %s. "
            "Do not exempt a file to get past this." % (len(result.findings), REGISTRY_REL)
        )
        # Plain, not log.info: the info glyph is a check mark, and this line sits under a red verdict.
        print("literal sources: shape: " + shape(result.stats), file=sys.stderr)
        return 1
    log.success("literal sources: clean; " + shape(result.stats))
    return 0


# --------------------------------------------------------------------------- controls ---------------------------------------------------------------------------
#
# Built by construction in a throwaway repository, with a fictional owned namespace (fixtureco.com) so this file carries no real value as code. Run 1 is the CLEAN tree: every negative control is in it, and it must produce zero findings. Run 2 adds every plant and must produce each expected finding and still nothing in a negative-control file. Runs 3 and 4 are the refusals.

_FX_REGISTRY = """\
# fixture registry
WK_RELEASES_ORIGIN=https://releases.fixtureco.com
WK_RELEASES_BUCKET=fixtureco-releases
WK_DATASTORE_PATH=/mnt/fixtureco
WK_DEV_PORT=4870
WK_GH_REPO=fixtureco/console
WK_IMAGE_REGISTRY=ghcr.io/fixtureco
WK_CONTACT_EMAIL=contact@fixtureco.com
WK_ACCOUNT_DEFAULT_ORIGIN=https://eu.fixtureco.com
WK_HUB_ORIGIN=https://hub.vendor.net
"""

_FX_REGIONS = json.dumps(
    {
        "regions": [
            {
                "id": "eu",
                "domain": "eu.fixtureco.com",
                "edgeDomain": "edge-eu.fixtureco.com",
                "default": True,
            },
            {
                "id": "us",
                "domain": "us.fixtureco.com",
                "edgeDomain": "edge-us.fixtureco.com",
                "default": False,
            },
        ]
    }
)


def _fx_policy(
    extra_exemptions: list[dict[str, Any]] | None = None,
    extra_carriers: list[dict[str, Any]] | None = None,
    floor: int = 10,
) -> str:
    return json.dumps(
        {
            "floor": floor,
            "thresholds": {"R2a": 3, "R2b": 4, "R5_distance": 2},
            "scope": {
                "extensions": ["py", "ts", "sh", "yml", "yaml", "json", "astro", "js"],
                "basenames": ["Dockerfile*"],
            },
            "owned": {
                "host_suffixes": ["fixtureco.com"],
                "path_prefixes": ["/mnt/fixtureco", "/etc/fixtureco"],
                "image_prefixes": ["ghcr.io/fixtureco"],
                "github_owners": ["fixtureco"],
            },
            "third_party": {"image_registries": ["ghcr.io", "docker.io", "quay.io"]},
            "reserved": {
                "hosts": [{"host": "localhost", "reason": "RFC 6761"}],
                "suffixes": [
                    {"suffix": ".invalid", "reason": "RFC 2606"},
                    {"suffix": "example.com", "reason": "RFC 2606"},
                ],
            },
            "exemptions": [
                {
                    "glob": "agent/**",
                    "reason": "history: recorded words, not configuration",
                    "prose_checked": False,
                },
                {
                    "glob": "vendored/**",
                    "except": ["vendored/edit.sh"],
                    "reason": "vendored tree whose one edit point stays in scope",
                    "prose_checked": False,
                },
            ]
            + (extra_exemptions or []),
            "carriers": [
                {
                    "path": "public/install.sh",
                    "keys": ["WK_RELEASES_ORIGIN"],
                    "reason": "curl|bash standalone, cannot import",
                }
            ]
            + (extra_carriers or []),
            "sources": {
                REGISTRY_REL: ["*"],
                REGIONS_REL: ["regions.json:*", "WK_ACCOUNT_DEFAULT_ORIGIN"],
                POLICY_REL: ["*"],
                PROJECTION_REL: ["*"],
                SH_PROJECTION_REL: ["*"],
            },
            "symbols": {
                "ts": "{key}",
                "worker": "{key} (relative)",
                "py": "from rediacc_ci.well_known import {name}",
                "sh": "$" + "{key}",
                "workflow": "env.{key}",
                "config": "compose from {key}",
                "region": "regions.json ({value})",
            },
            "region_mirrors": {"WK_ACCOUNT_DEFAULT_ORIGIN": "default.domain"},
            "exact_stem": [
                {
                    "key": "WK_HUB_ORIGIN",
                    "reason": "a code host: only the bare origin is this entry",
                }
            ],
        },
        indent=1,
    )


def _fx_reader(values: dict[str, str]) -> str:
    out = ["from x import _get"]
    for key, value in values.items():
        out.append(
            '%s: %s = %s_get("%s")%s'
            % (
                key[3:],
                "int" if value.isdigit() else "str",
                "int(" if value.isdigit() else "",
                key,
                ")" if value.isdigit() else "",
            )
        )
    return "\n".join(out) + "\n"


def _fx_consumers(values: dict[str, str]) -> str:
    return '. "$(dirname "$0")/well-known.generated.sh"\n' + "".join(
        'echo "$%s"\n' % k for k in values
    )


def _fx_clean() -> dict[str, str]:
    values = well_known.parse(_FX_REGISTRY)
    files = {
        REGISTRY_REL: _FX_REGISTRY,
        REGIONS_REL: _FX_REGIONS,
        POLICY_REL: _fx_policy(),
        PROJECTION_REL: render_projection(values),
        SH_PROJECTION_REL: render_sh_projection(values),
        READER_REL: _fx_reader(values),
        CONSTANTS_REL: _fx_consumers(values),
        # (1) py: comment and docstring are silent
        "neg/py_prose.py": '"""Module doc: https://releases.fixtureco.com/cli is where it ships."""\n\n# see https://releases.fixtureco.com\n\n\ndef f():\n    """Fetch from releases.fixtureco.com."""\n    return 1\n',
        # (2) TS: line and block comments silent; the @scope/package import is not a slug
        "neg/ts_prose.ts": "import { x } from '@fixtureco/shared';\n// https://releases.fixtureco.com/stable\n/* releases.fixtureco.com */\nexport const y = x;\n",
        # (3) bash comment and YAML comment silent
        "neg/sh_prose.sh": "#!/bin/bash\n# downloads from https://releases.fixtureco.com\necho ok  # releases.fixtureco.com\n",
        "neg/yaml_prose.yml": "# https://releases.fixtureco.com\nname: fine # releases.fixtureco.com\n",
        # (5) an owned literal in two files is under the R2a threshold; a third-party stem in three is under R2b
        "neg/two_a.ts": "export const a = 'https://two.fixtureco.com';\nexport const t = 'https://api.thirdparty.net/v1';\n",
        "neg/two_b.py": "A = 'https://two.fixtureco.com'\nT = 'https://api.thirdparty.net/v1'\n",
        "neg/third_c.sh": "curl https://api.thirdparty.net/v1\n",
        # an exact-stem entry does not own every URL on its host
        "neg/hub_other.py": "TOOL = 'https://hub.vendor.net/someone/tool/releases'\n",
        # (7) a timeout of the same number is not a port
        "neg/timeout.ts": "export const cfg = { timeout: 4870 };\n",
        # a Go module path is code identity, not a repository reference
        "neg/gomod.py": "MOD = 'github.com/fixtureco/console/pkg/x'\nREPLACE = 'replace github.com/fixtureco/console => ./c'\n",
        # (8) a carrier holding the exact value is silent
        "public/install.sh": 'RELEASES="${RELEASES:-https://releases.fixtureco.com}"\n',
        # history is exempt, and so is a vendored tree except its edit point
        "agent/history.py": "X = 'https://releases.fixtureco.com'\n",
        "vendored/lib.sh": "U=https://releases.fixtureco.com\n",
        "vendored/edit.sh": "# the edit point\n",
    }
    # (6) a reserved name in ten files is silent
    for i in range(10):
        files["neg/reserved_%d.ts" % i] = (
            "export const r%d = 'https://api.example.invalid/v1';\n" % i
        )
    return files


def _fx_plants(clean: dict[str, str]) -> dict[str, str]:
    files = dict(clean)
    dead = _FX_REGISTRY + "WK_DEAD_ORIGIN=https://dead.fixtureco.com\n"
    files[REGISTRY_REL] = (
        dead  # (9) dead entry; also makes the projection stale and the reader short
    )
    files[POLICY_REL] = _fx_policy(
        extra_exemptions=[
            {
                "glob": "nothing-here/**",
                "reason": "a planted dead exemption glob for the control",
                "prose_checked": False,
            }
        ],
        extra_carriers=[
            {
                "path": "public/drifted.sh",
                "keys": ["WK_RELEASES_ORIGIN"],
                "reason": "a planted carrier that has drifted",
            }
        ],
    )
    files.update(
        {
            # (1)
            "pos/py_code.py": "URL = 'https://releases.fixtureco.com/cli'\n",
            # (2) a string and a template with a marker
            "pos/ts_code.ts": "export const a = 'https://releases.fixtureco.com';\nexport const b = `https://releases.fixtureco.com/${format}/stable`;\n",
            # (3)
            "pos/sh_code.sh": 'curl -fsSL "https://releases.fixtureco.com/install.sh"\nR="${R:-https://releases.fixtureco.com}"\n',
            "pos/yaml_code.yml": "url: https://releases.fixtureco.com/x\n",
            # (4) four spellings, one entry
            "pos/spellings.ts": (
                "export const s1 = 'HTTPS://Releases.FixtureCo.com/';\n"
                "export const s2 = 'https://user@releases.fixtureco.com:443/a?b=1#c';\n"
                "export const s3 = 'releases.fixtureco.com';\n"
                "export const s4 = 'https://releases.fixtureco.com';\n"
            ),
            # (5) R2a fires at three, R2b at four
            "pos/three_a.ts": "export const a = 'https://three.fixtureco.com';\n",
            "pos/three_b.py": "A = 'https://three.fixtureco.com'\n",
            "pos/three_c.sh": "curl https://three.fixtureco.com\n",
            "pos/four_d.sh": "curl https://api.thirdparty.net/v1\n",
            # an exact-stem entry fires on the bare origin a path is composed onto
            "pos/hub.py": "BASE = 'https://hub.vendor.net/%s/pull' % repo\n",
            # (7)
            "pos/port.ts": "export const u = 'http://localhost:4870/api';\n",
            # a bash default expansion around an address, and a sed delimiter after a URL
            "pos/edges.sh": 'MAIL="${MAIL:-contact@fixtureco.com}"\nsed -i "s|http://archive.vendor.net/ubuntu|x|g" f\n',
            # each other detector, once
            "pos/kinds.py": (
                "BUCKET = 'fixtureco-releases'\n"
                "MNT = '/mnt/fixtureco/mounts'\n"
                "REPO = 'fixtureco/console'\n"
                "IMG = 'ghcr.io/fixtureco/renet:1.0'\n"
                "MAIL = 'contact@fixtureco.com'\n"
                "REGION = 'https://us.fixtureco.com'\n"
            ),
            # an exemption's `except` keeps that one file in scope
            "vendored/edit.sh": 'REPO="fixtureco/console"\n',
            # (8) a drifted carrier, and a near miss in markdown
            "public/drifted.sh": 'RELEASES="${RELEASES:-https://relases.fixtureco.com}"\n',
            "docs/guide.md": "Download from https://relases.fixtureco.com/stable.\n",
        }
    )
    return files


def _fx_tree(files: dict[str, str]) -> pathlib.Path:
    root = pathlib.Path(tempfile.mkdtemp(prefix="literal-sources-"))
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    subprocess.run(["git", "init", "-q", str(root)], check=True, env=env)
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True, env=env)
    return root


def _has(
    findings: list[Finding], rule: str, path: str, line: int | None = None, needle: str = ""
) -> bool:
    return any(
        f.rule == rule
        and f.path == path
        and (line is None or f.line == line)
        and needle in f.message
        for f in findings
    )


def selftest() -> bool:
    """True when a control failed, which is what `controls_first` expects."""
    check = Checker()
    clean_files = _fx_clean()
    roots: list[pathlib.Path] = []
    try:
        # Pure helpers first.
        u = normalize_url("HTTPS://user@Releases.FixtureCo.com:443/a/${v}/b?x#y")
        check(
            "normalize: case, userinfo, default port, template cut",
            u is not None and u.stem == "https://releases.fixtureco.com/a",
        )
        check(
            "normalize: a templated host is not a literal",
            normalize_url("https://${HOST}/x") is None,
        )
        check(
            "near miss: one typo in a long label fires",
            near_miss("relases.fixtureco.com", "releases.fixtureco.com", 2),
        )
        check(
            "near miss: eu and us are not typos of each other",
            not near_miss("us.fixtureco.com", "eu.fixtureco.com", 2),
        )
        py = lex_python('x = "a"\n"""doc"""\n# c\nf(\n  "b"\n)\n')
        check("python lexer: docstring and comment are prose, an argument is not", len(py) == 2)
        specs = parse_paths(["--paths", "a.py", "b/", "--report", "--paths", "c/*.sh"])
        check(
            "--paths: every value of every --paths, flags excluded",
            specs == ["a.py", "b/", "c/*.sh"],
        )
        pm = path_matcher(specs)
        check(
            "--paths: a file, a directory and a glob each select their files",
            pm is not None and all(pm.match(x) for x in ("a.py", "b/x/y.ts", "c/z.sh")),
        )
        check(
            "--paths: nothing else is selected",
            pm is not None and not any(pm.match(x) for x in ("a.pyc", "bb/x.ts", "c/d/z.sh")),
        )

        # The bash projection, SOURCED by a real bash: the shell wins, empty counts as absent, and a hostile value is data.
        sh_dir = pathlib.Path(tempfile.mkdtemp(prefix="literal-sources-sh-"))
        roots.append(sh_dir)
        canary = sh_dir / "executed"
        hostile = "a $(touch %s) `touch %s` $HOME 'q' \\ b" % (canary, canary)
        (sh_dir / "p.sh").write_text(
            render_sh_projection(
                {"WK_KEEP": "https://file.fixtureco.com", "WK_EMPTY": "fill", "WK_EVIL": hostile}
            ),
            encoding="utf-8",
        )
        probe = subprocess.run(
            [
                "bash",
                "-c",
                'set -euo pipefail; . "$1"; bash -c \'printf "%s\\n%s\\n%s\\n" "$WK_KEEP" "$WK_EMPTY" "$WK_EVIL"\'',
                "_",
                str(sh_dir / "p.sh"),
            ],
            capture_output=True,
            text=True,
            env={**os.environ, "WK_KEEP": "https://shell.example.com", "WK_EMPTY": ""},
            check=False,  # the return code is part of the measurement
        )
        got = probe.stdout.split("\n")
        check("bash projection: sources cleanly under set -euo pipefail", probe.returncode == 0)
        check(
            "bash projection: an exported WK_ value wins over the file",
            got[:1] == ["https://shell.example.com"],
        )
        check(
            "bash projection: an empty exported value counts as absent and is filled",
            got[1:2] == ["fill"],
        )
        check(
            "bash projection: a hostile value is exported verbatim, never executed",
            got[2:3] == [hostile] and not canary.exists(),
        )

        clean = _fx_tree(clean_files)
        roots.append(clean)
        r1 = run(clean)
        check("clean tree: zero findings (every negative control silent)", not r1.findings)
        if r1.findings:
            for f in r1.findings:
                print("      unexpected: %s" % f.render(), file=sys.stderr)
        check("clean tree: the scan saw candidate lines", r1.stats["candidate_lines"] > 0)

        planted = _fx_tree(_fx_plants(clean_files))
        roots.append(planted)
        f2 = run(planted).findings
        check(
            "(1) a registered host in a .py string fires",
            _has(f2, "R1", "pos/py_code.py", 1, "WK_RELEASES_ORIGIN"),
        )
        check("(2) a TS string fires", _has(f2, "R1", "pos/ts_code.ts", 1))
        check("(2) a TS template with ${format} fires", _has(f2, "R1", "pos/ts_code.ts", 2))
        check("(3) a bash string fires", _has(f2, "R1", "pos/sh_code.sh", 1))
        check(
            "(3) a URL closing a `${X:-...}` default fires",
            _has(f2, "R1", "pos/sh_code.sh", 2, "WK_RELEASES_ORIGIN"),
        )
        check(
            "(8) the drifted carrier's near miss fires too",
            _has(f2, "R5", "public/drifted.sh", 1, "relases.fixtureco.com"),
        )
        check("(3) a YAML value fires", _has(f2, "R1", "pos/yaml_code.yml", 1))
        for n in range(1, 5):
            check(
                "(4) spelling %d normalizes to WK_RELEASES_ORIGIN" % n,
                _has(f2, "R1", "pos/spellings.ts", n, "WK_RELEASES_ORIGIN"),
            )
        check(
            "(5) R2a fires at three files",
            all(_has(f2, "R2a", p) for p in ("pos/three_a.ts", "pos/three_b.py", "pos/three_c.sh")),
        )
        check(
            "(5) R2a silent at two files",
            not any(f.rule == "R2a" and "two.fixtureco.com" in f.message for f in f2),
        )
        check(
            "(5) R2b fires at four files",
            all(
                _has(f2, "R2b", p)
                for p in ("neg/two_a.ts", "neg/two_b.py", "neg/third_c.sh", "pos/four_d.sh")
            ),
        )
        check(
            "(6) a reserved name in ten files is silent",
            not any("example.invalid" in f.message for f in f2),
        )
        check("(7) localhost:<port> fires", _has(f2, "R1", "pos/port.ts", 1, "WK_DEV_PORT"))
        check(
            "an exact-stem entry fires on its bare origin",
            _has(f2, "R1", "pos/hub.py", 1, "WK_HUB_ORIGIN"),
        )
        check(
            "an exact-stem entry ignores other URLs on its host",
            not any(f.path == "neg/hub_other.py" for f in f2),
        )
        check("(7) timeout: <port> is silent", not any(f.path == "neg/timeout.ts" for f in f2))
        for key, line in (
            ("WK_RELEASES_BUCKET", 1),
            ("WK_DATASTORE_PATH", 2),
            ("WK_GH_REPO", 3),
            ("WK_IMAGE_REGISTRY", 4),
            ("WK_CONTACT_EMAIL", 5),
        ):
            check("detector for %s fires" % key, _has(f2, "R1", "pos/kinds.py", line, key))
        check(
            "a region host fires with regions.json as its source",
            _has(f2, "R1", "pos/kinds.py", 6, REGIONS_REL),
        )
        check(
            "an address after `:-` is the address, not `-address`",
            _has(f2, "R1", "pos/edges.sh", 1, "contact@fixtureco.com is WK_CONTACT_EMAIL"),
        )
        det = Detectors(
            load_policy(planted),
            [entry_for(k, v) for k, v in well_known.parse(_FX_REGISTRY).items()],
        )
        urls = [
            h.key
            for h in det.scan_line("x.sh", 1, "s|http://archive.vendor.net/ubuntu|x|g")
            if h.detector == "url"
        ]
        check("a sed `|` ends a URL", urls == ["http://archive.vendor.net/ubuntu"])
        check("(8) a drifted carrier fires", _has(f2, "R3", "public/drifted.sh", 0, "drifted"))
        check(
            "(8) a near miss in markdown fires",
            _has(f2, "R5", "docs/guide.md", 1, "relases.fixtureco.com"),
        )
        check("(9) a stale projection fires", _has(f2, "R4", PROJECTION_REL))
        check("(9) a stale bash projection fires", _has(f2, "R4", SH_PROJECTION_REL))
        check(
            "an exemption's `except` file is scanned",
            _has(f2, "R1", "vendored/edit.sh", 1, "WK_GH_REPO"),
        )
        check(
            "the rest of that exempt tree is not", not any(f.path == "vendored/lib.sh" for f in f2)
        )
        check("(9) a dead exemption fires", _has(f2, "R3", POLICY_REL, 0, "nothing-here/**"))
        check("(9) a dead registry entry fires", _has(f2, "R3", REGISTRY_REL, 0, "WK_DEAD_ORIGIN"))
        check("(9) a reader missing a name fires", _has(f2, "R4", READER_REL, 0, "WK_DEAD_ORIGIN"))
        negatives = [
            p
            for p in clean_files
            if p.startswith("neg/") and not p.startswith(("neg/two_", "neg/third_"))
        ]
        stray = [
            f
            for f in f2
            if f.path in negatives or f.path.startswith("agent/") or f.path == "public/install.sh"
        ]
        check("planted tree: nothing fires in a negative-control file", not stray)
        for f in stray:
            print("      unexpected: %s" % f.render(), file=sys.stderr)

        floored = dict(clean_files)
        floored[POLICY_REL] = _fx_policy(floor=10_000)
        root3 = _fx_tree(floored)
        roots.append(root3)
        try:
            run(root3)
            refused = False
        except RefusalError:
            refused = True
        check("under the floor: a refusal, never a pass", refused)

        (clean / REGISTRY_REL).unlink()
        try:
            run(clean)
            refused = False
        except RefusalError as exc:
            refused = REGISTRY_REL in str(exc)
        check("a missing registry: a refusal naming the file", refused)
    except (
        RefusalError,
        OSError,
        subprocess.CalledProcessError,
        KeyError,
        ValueError,
        TypeError,
    ) as exc:
        # A crash in the controls is a failed control, not a pass.
        check("controls ran without crashing: %r" % exc, False)
    finally:
        for r in roots:
            shutil.rmtree(r, ignore_errors=True)
    if check.count < 30:
        check("at least 30 controls ran (%d did)" % check.count, False)
    return not check.ok


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
