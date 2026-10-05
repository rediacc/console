#!/usr/bin/env python3
"""check:ci-record-paths -- the record set a push receipt may advance across, and the fixed widths no grant sizes.

WHY THIS EXISTS (agent/plans/PLAN-prepush-full-cpu.md part 5, PF23). `worklist.py --review-commit` commits agent/reviews/<branch>/ after every reviewed commit, and on 2026-10-05 nine pre-push receipts died that way with no code changed. block_unverified_push now lets a receipt ADVANCE across a commit confined to the globs in .ci/policy/record-paths.json, provided the gates that READ those globs
were re-run at the new tree. That rule is exactly as safe as the reader lists are complete: a gate that reads agent/reviews/ but is missing from the list would be skipped by the advance, and its verdict on the pushed tree would be one nobody computed. So the lists are DERIVED here and compared with the policy, in both directions.

HOW A READER IS DERIVED. For every `gate: true` entry of scripts/ci-runner/gates.lock.json, the files of its leaves and of their local imports (Python `rediacc_ci.*` and sibling modules, the stop-hook library, TypeScript relative imports) are read, and a gate reads a record when any of them:
  cite   names the record's literal prefix (`agent/reviews`), as a path or as joined segments (`"agent", "reviews"`), other than a path the record excludes;
  root   names an ancestor of it as a scan root, `"agent/"` or a glob under `agent/`;
  config cites a JSON config file whose glob strings match one of the record's probe paths (prose-style reads `*.md` through .ci/config/prose-style-rules.json, and a review record is a `.md`).
This OVER-counts on purpose. A false reader costs one extra gate at an advance; a missed reader lets an unjudged record change through the push. A gate the derivation flags that genuinely reads nothing goes in `notReaders` with its reason, by name, and is printed on every run.

THE SECOND MODE (PF9): FIXED WIDTHS. The 2026-10-05 ruling removed every static worker count: a parallel tool sizes itself from the cores granted at launch. What remains fixed is request concurrency against a remote API (`xargs -P 8` of R2 copies, eight `gh api` calls), which is not a core count. Each such width is listed in .ci/policy/fixed-widths.json with the remote limit it respects, and this mode refuses a literal width that is not listed, a
listed width that is gone or changed, and any core cap (`min(8, os.cpu_count())`) at all: a core cap is never an I/O width, so it cannot be listed.

Exit 0 clean, 1 on a finding, 2 when a control fails or the gate cannot see its inputs (zero gates, zero records, zero scanned files).

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
import json
import pathlib
import re
import subprocess
import sys
import tempfile
from typing import Any

import _cipath  # noqa: F401
from rediacc_ci import controls, paths
from rediacc_ci.controls import plant
from rediacc_ci.policy_paths import policy_rel

POLICY_REL = policy_rel("record-paths.json")
SELF_REL = ".ci/scripts/quality/check_record_paths.py"
WIDTHS_REL = policy_rel("fixed-widths.json")
LOCK_REL = "scripts/ci-runner/gates.lock.json"
POLICY_VERSION = 1
CONTROL_FLOOR = 40

#: Files that are config for this gate or for the runner, never a scanner's scope: their glob strings say what a gate is SELECTED by, not what it reads.
NOT_SCAN_CONFIG = frozenset({POLICY_REL, WIDTHS_REL, LOCK_REL})
#: Package manifests and lockfiles: their `*` strings are version ranges and package-name patterns, never file globs.
NOT_SCAN_CONFIG_NAMES = frozenset({"package.json", "package-lock.json", ".syncpackrc.json"})
#: Where the import closure resolves a Python module name, in order.
PY_IMPORT_BASES = (".ci", ".claude", ".claude/hooks/stop")
TS_SUFFIXES = (".ts", ".mts", ".cts", ".js", ".mjs", ".cjs", ".tsx")
TEXT_SUFFIXES = (".py", ".sh", *TS_SUFFIXES)
EVIDENCE_RE = re.compile(r"^(?P<file>[^\s:]+):(?P<line>\d+)\b")
JSON_CITE_RE = re.compile(r"""['"]((?:\.{0,2}/)?[\w./-]+\.json)['"]""")
QUOTED_RE = re.compile(r"""(['"])((?:(?!\1)[^\\\n])*)\1""")
JOINED_RE = re.compile(r"""(['"])([\w.<>*-]+)\1((?:\s*[,/]\s*(['"])[\w.<>*-]+\4)+)""")
SEGMENT_RE = re.compile(r"""(['"])([\w.<>*-]+)\1""")
PY_TS_IMPORT_RE = re.compile(
    r"""(?:\bfrom\s+|\bimport\s*\(?\s*|\brequire\s*\(\s*)['"](\.{1,2}/[^'"]+)['"]"""
)


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
    """The directory part before the first wildcard: `agent/worklist/*.jsonl` -> `agent/worklist`."""
    head = re.split(r"[*?\[{]", glob, maxsplit=1)[0]
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


def _py_imports(path: pathlib.Path, root: pathlib.Path) -> list[pathlib.Path]:
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


def _ts_imports(path: pathlib.Path) -> list[pathlib.Path]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    found = []
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
            stack.extend(_ts_imports(path))
    return seen


# ---------------------------------------------------------------- derivation


def _line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _rel(path: pathlib.Path, root: pathlib.Path) -> str:
    try:
        return str(path.relative_to(root.resolve()))
    except ValueError:
        return str(path)


def cite_hits(text: str, record: dict) -> list[tuple[int, str]]:
    """(offset, token) for every citation of the record's literal prefix that is not wholly an excluded path."""
    stem = literal_prefix(record["glob"])
    hits = [
        (m.start(), m.group(0))
        for m in re.finditer(
            r"(?<![\w-])%s(?![\w-])(?:/[^\s'\"`),;:\]}]*)?" % re.escape(stem), text
        )
    ]
    for m in JOINED_RE.finditer(text):
        token = "/".join([m.group(2), *(s.group(2) for s in SEGMENT_RE.finditer(m.group(3)))])
        if token == stem or token.startswith(stem + "/"):
            hits.append((m.start(), token))
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
    return [(m.start(), m.group(2)) for m in QUOTED_RE.finditer(text) if m.group(2) in roots]


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
    out: list[str] = []
    if isinstance(doc, str):
        if is_path_glob(doc):
            out.extend(expand_braces(doc))
    elif isinstance(doc, dict):
        for v in doc.values():
            out.extend(_json_globs(v))
    elif isinstance(doc, list):
        for v in doc:
            out.extend(_json_globs(v))
    return out


def glob_hits(text: str, record: dict) -> list[tuple[int, str]]:
    """(offset, glob) for every quoted file glob in code that reaches one of the record's probes: `git ls-files '*.md'` scans review records as surely as a config file does."""
    hits = []
    for m in QUOTED_RE.finditer(text):
        s = m.group(2)
        if not is_path_glob(s) or s.endswith("/"):
            continue
        if any(
            config_glob_matches(p, probe) for p in expand_braces(s) for probe in record["probes"]
        ):
            hits.append((m.start(), s))
    return hits


def config_hits(text: str, record: dict, root: pathlib.Path, cache: dict) -> list[tuple[int, str]]:
    """(offset, "<config>: <glob>") for every cited JSON config holding a glob that reaches one of the record's probes."""
    hits = []
    for m in JSON_CITE_RE.finditer(text):
        rel = m.group(1).lstrip("./") if m.group(1).startswith("./") else m.group(1)
        if (
            rel in NOT_SCAN_CONFIG
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


def derive_readers(
    gates: list[dict], records: list[dict], root: pathlib.Path
) -> tuple[dict, int, int]:
    """({glob: {gate_id: evidence}}, gates scanned, files read). Evidence is `file:line (tier) token`, the first hit found."""
    derived: dict[str, dict[str, str]] = {r["glob"]: {} for r in records}
    texts: dict[pathlib.Path, str] = {}
    configs: dict = {}
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
            for path in files:
                if path.suffix not in TEXT_SUFFIXES:
                    continue
                if path not in texts:
                    try:
                        texts[path] = path.read_text(encoding="utf-8", errors="replace")
                    except OSError:
                        texts[path] = ""
                text = texts[path]
                for tier, found in (
                    ("cite", cite_hits(text, record)),
                    ("root", root_hits(text, record)),
                    ("glob", glob_hits(text, record)),
                    ("config", config_hits(text, record, root, configs)),
                ):
                    if found:
                        off, token = found[0]
                        derived[record["glob"]][gate["id"]] = "%s:%d (%s) %s" % (
                            _rel(path, root),
                            _line_of(text, off),
                            tier,
                            token,
                        )
                        break
                if gate["id"] in derived[record["glob"]]:
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
        gates = _load_json(lock_path)
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
        [g for g in gates if isinstance(g, dict)], records, root
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
        "record-paths: OK (this gate's own leaf excluded), %d record glob(s), %d gate(s) scanned (%d files in their import closures), %d reader declaration(s) (%d derived, %d beyond the derivation), %d exempt by name"
        % (
            len(records),
            scanned,
            read,
            declared,
            sum(len(d) for d in derived.values()) - len(exempt),
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


def _flag(argv: list[str], name: str) -> str | None:
    if name in argv:
        k = argv.index(name)
        if k + 1 < len(argv):
            return argv[k + 1]
    return None


def main(argv: list[str]) -> int:
    if "--selftest" in argv:
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
    policy_path = pathlib.Path(_flag(argv, "--policy") or root / POLICY_REL)
    lock_path = pathlib.Path(_flag(argv, "--lock") or root / LOCK_REL)
    widths_path = pathlib.Path(_flag(argv, "--widths") or root / WIDTHS_REL)
    rc_records = 0 if "--widths-only" in argv else run_records(root, policy_path, lock_path)
    rc_widths = 0 if "--records-only" in argv else run_widths(root, widths_path)
    return max(rc_records, rc_widths)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
