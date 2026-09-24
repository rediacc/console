"""A gate MODULE that writes the real tree must say so: an exclusive `tree:` claim plus a `writesTree` reason.

THE HOLE THIS CLOSES. `check:ci-pool-writer-safety` (`rediacc_ci.quality.pool_writer_safety`) enforces "a tree writer holds an exclusive `tree:` claim" for GATE TESTS only: bash under `.ci/scripts/test/gates/` and the pytest ports that declare the real-tree xdist group. The gates themselves -- the TS/JS/Python/bash leaves `scripts/ci-runner/gates.lock.json` schedules -- were never
looked at. On 2026-09-24 the first cut of the Biome half of `.ci/scripts/quality/lint-rule-liveness.mjs` planted 7 files in the tree, 2 of them in `private/account`, and appended to the tracked `private/account/src/services/email.service.ts`, restoring it only in a `finally` that a hard kill skips. Its manifest entry never had a mutex and no gate could have noticed; worse, the entry's only
leaf is the Python wrapper `check_lint_rule_liveness.py`, which reaches the `.mjs` through `subprocess.run(["node", ...])`, so a scanner that read only declared leaves would have missed the exact file that did the damage. agent/plans/PLAN-ci-gate-write-taint-scanners.md is the design.

WHAT RUNS. For every lock entry the pool can schedule (`gate: true`, and `gate: false` entries a scheduled one `needs`), the entry's `run` is resolved to (leaf, argv) pairs by the SAME resolver `check:ci-parity` uses (`resolveInvocations`, called through `scripts/lib/tree-write-sites.ts --invocations`). From the leaves:
  - Python closure and sites: `rediacc_ci.quality.gate_tree_writes_py`.
  - TS/JS closure and sites: `scripts/lib/tree-write-sites.ts` (oxc-parser).
  - bash leaves: `pool_writer_safety.scan_text`, imported rather than copied.
  - spawn edges cross the languages in both directions until nothing new is reached.

EVERY SITE ENDS AS EXACTLY ONE OF:
  SAFE         TEMP, OUTSIDE or SCRATCH (`.ci/cache/`): silent, counted.
  MODE-GATED   dominated by a flag no registered invocation of the entry passes (`if "--write" in argv:`, an alias one hop away, an early exit, a function whose every call is gated): reported with the flag. It becomes TREE the moment an invocation passes that flag.
  DECLARED     UNRESOLVED with a `tree-write: safe <reason>` pragma on the line or the line above.
  TREE         the entry must hold an exclusive `tree:` claim (`mutex`; `reads` is rejected, as in pool_writer_safety) AND carry `writesTree: '<reason>'`.
  UNRESOLVED   red, unless a pragma declares it.
Pragma rules, all enforced: the reason is at least 20 characters; `safe` on a site resolved TEMP/SCRATCH is STALE and red; `safe` on a resolved TREE site is ignored and reported (a pragma cannot overrule a proven write); `tree-write: mode --flag <reason>` is honoured only while no registered invocation passes that flag (bash-scanner hits and guards the resolver does
not recognise).

REGISTRATION IS CHECKED BOTH WAYS on every lock entry: `writesTree` without an exclusive `tree:` claim is red, and an exclusive `tree:` claim without `writesTree` is red. The rule is otherwise one-directional, as pool_writer_safety's is: a `writesTree` entry with no TREE site is listed as `declared, no site found`, never red.

THE MUTEX IS THE WEAK FIX. It serialises the writer only against the other declared `tree:` claimants (today check:ci-pytest and gate-test:runner-advice); the hundreds of scanners that read the tree declare nothing and still overlap it, and no claim helps with the residue a hard kill leaves. Writing to a temp copy is the real fix, and every red says so.

CONTROLS FIRST, both directions, on every run before the real verdict (PLAN section 4, C1-C10): a fixture tree is planted in a TemporaryDirectory, copied never symlinked, and driven through the same pipeline via `--root/--lock/--pkg`. REAL then asserts on the live tree: the lint-rule-liveness closure reaches the `.mjs`, at least one TEMP and one MODE-GATED site exist, and `check:ci-pytest`
carries both `tree:repo` and `writesTree`.

ANTI-VACUITY REFUSALS (exit 1, each named): the lock missing or unparseable; zero entries resolved to a scannable leaf; the lint-rule-liveness closure without its `.mjs`; the TS extractor exiting non-zero or printing non-JSON (never "no sites"); total sites under the floor; zero TEMP sites; zero TREE-or-MODE-GATED sites.

`--report` prints every site and exits 0; it is the measurement mode task 2.1 of the plan ran. Without it the gate enforces.
"""

from __future__ import annotations

import dataclasses
import io
import json
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import tokenize

from rediacc_ci import log, paths
from rediacc_ci.quality import pool_writer_safety
from rediacc_ci.quality.gate_tree_writes_py import Analyzer, Site, load_mutators

LOCK_REL = "scripts/ci-runner/gates.lock.json"
HELPER_REL = "scripts/lib/tree-write-sites.ts"
MUTATORS_REL = ".ci/config/tree-write-mutators.json"
TREE_PREFIX = "tree:"
PY_EXT = (".py",)
TS_EXT = (".ts", ".tsx", ".js", ".mjs", ".cjs")
SH_EXT = (".sh",)
MIN_REASON = 20
SAFE_ORIGINS = ("TEMP", "OUTSIDE", "SCRATCH")

# The one spawn edge whose absence is a refusal: the file that actually wrote the tree in the incident this gate exists for.
REQUIRED_SPAWNS = {"check:ci-lint-rule-liveness": ".ci/scripts/quality/lint-rule-liveness.mjs"}

# Floors at roughly 80% of the live counts measured 2026-09-24 after the resolver work of plan task 2.2 (Python 1069 sites, TS/JS 322; the first report-only run saw 1065 and 324). A scanner that stopped reading the tree falls under them long before it reads as clean.
FLOOR_PY = 855
FLOOR_TS = 257

# Every control in `run_controls`, plus the TS helper's selftest. A count under it means controls stopped executing.
SELFTEST_FLOOR = 27

PRAGMA_RE = re.compile(r"(?:#|//)\s*tree-write:\s*(safe|mode)\b\s*(.*)$")
MODE_RE = re.compile(r"^(--?[A-Za-z0-9][\w-]*)\s+(.*)$")
SEVERITY = {
    "TREE": 5,
    "UNRESOLVED": 4,
    "STALE": 4,
    "BAD-PRAGMA": 4,
    "COVERED": 3,
    "MODE-GATED": 2,
    "DECLARED": 1,
    "SAFE": 0,
}
MUTEX_ADVICE = (
    "Prefer writing to a temp copy (tempfile / os.tmpdir() / a mirror), which also survives a hard kill. The fallback is "
    "`mutex: ['tree:repo']` plus `writesTree: '<reason>'` on the entry in scripts/ci-runner/manifest.ts, and it is weak: it "
    "serialises only against the other declared tree: claimants (today check:ci-pytest and gate-test:runner-advice)."
)


@dataclasses.dataclass
class Verdict:
    entry: str
    site: Site
    bucket: str
    note: str = ""


@dataclasses.dataclass
class Result:
    refusals: list[str]
    findings: list[str]
    verdicts: list[Verdict]
    closures: dict[str, set[str]]
    declared_unused: list[str]
    counts: dict[str, dict[str, int]]
    entries_scanned: int
    bare: list[str]
    product: set[str]
    pragmas: dict[str, int]


# --------------------------------------------------------------------------- inputs


def _helper_cmd(repo: pathlib.Path) -> list[str]:
    tsx = repo / "node_modules" / ".bin" / "tsx"
    return [
        str(tsx) if tsx.is_file() else "npx",
        *([] if tsx.is_file() else ["tsx"]),
        str(repo / HELPER_REL),
    ]


def run_helper(
    repo: pathlib.Path, args: list[str], stdin: str | None = None
) -> tuple[object | None, str]:
    """The TS extractor. A non-zero exit or non-JSON output is an ERROR returned as text, never an empty result."""
    try:
        proc = subprocess.run(
            [*_helper_cmd(repo), *args],
            input=stdin,
            capture_output=True,
            text=True,
            cwd=str(repo),
            check=False,
            timeout=600,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, "the TS extractor could not run: %s" % exc
    if proc.returncode != 0:
        return None, "the TS extractor exited %d: %s" % (
            proc.returncode,
            (proc.stderr or proc.stdout).strip()[-600:],
        )
    try:
        return json.loads(proc.stdout), ""
    except ValueError:
        return None, "the TS extractor printed non-JSON: %r" % proc.stdout[:200]


def scheduled(entries: list[dict]) -> list[dict]:
    """`gate: true`, plus the `gate: false` entries a scheduled entry `needs` (transitively)."""
    by_id = {e.get("id"): e for e in entries if isinstance(e, dict)}
    want = {i for i, e in by_id.items() if e.get("gate") is True}
    todo = list(want)
    while todo:
        for n in by_id.get(todo.pop(), {}).get("needs", []) or []:
            if n in by_id and n not in want:
                want.add(n)
                todo.append(n)
    return [e for i, e in by_id.items() if i in want]


def exclusive_tree(entry: dict) -> bool:
    return any(
        isinstance(r, str) and r.startswith(TREE_PREFIX) for r in entry.get("mutex", []) or []
    )


# --------------------------------------------------------------------------- pragmas


class Pragmas:
    """`tree-write:` pragmas on a site's line or the line above, read once per file.

    ONLY A REAL COMMENT COUNTS. A pragma spelled inside a string literal -- this gate's own control fixtures carry several -- is text, not a declaration: in Python the comments come from `tokenize`, elsewhere the marker must open the line or follow code with balanced quotes.
    """

    def __init__(self, root: pathlib.Path) -> None:
        self.root = root
        self._lines: dict[str, list[str]] = {}

    def _comments(self, file: str) -> list[str]:
        lines = self._lines.get(file)
        if lines is not None:
            return lines
        try:
            text = (self.root / file).read_text(encoding="utf-8", errors="replace")
        except OSError:
            text = ""
        raw = text.split("\n")
        lines = [""] * len(raw)
        if file.endswith(".py"):
            try:
                for tok in tokenize.generate_tokens(io.StringIO(text).readline):
                    if tok.type == tokenize.COMMENT:
                        lines[tok.start[0] - 1] = tok.string
            except (tokenize.TokenError, SyntaxError):
                pass
        else:
            for i, ln in enumerate(raw):
                m = re.search(r"(?:#|//)\s*tree-write:", ln)
                if (
                    m
                    and ln[: m.start()].count("'") % 2 == 0
                    and ln[: m.start()].count('"') % 2 == 0
                    and ln[: m.start()].count("`") % 2 == 0
                ):
                    lines[i] = ln[m.start() :]
        self._lines[file] = lines
        return lines

    def at(self, file: str, line: int) -> tuple[str, str, str] | None:
        lines = self._comments(file)
        for n in (line, line - 1):
            if 0 < n <= len(lines):
                m = PRAGMA_RE.search(lines[n - 1])
                if m:
                    kind, rest = m.group(1), m.group(2).strip()
                    if kind == "mode":
                        mm = MODE_RE.match(rest)
                        return (
                            ("mode", mm.group(1), mm.group(2).strip()) if mm else ("mode", "", rest)
                        )
                    return ("safe", "", rest)
        return None

    def count(self, file: str) -> int:
        return sum(1 for ln in self._comments(file) if PRAGMA_RE.search(ln))


def _holds(literal: str, argv: set[str]) -> bool:
    """A guard literal under one invocation: `--x` holds when passed, `!--x` when absent."""
    return literal[1:] not in argv if literal.startswith("!") else literal in argv


def gating(guard: list[list[str]], invocations: list[set[str]]) -> list[list[str]]:
    """The clauses that keep a site from running under EVERY registered invocation; empty when some invocation reaches it."""
    per = [
        [c for c in guard if not any(_holds(f, argv) for f in c)] for argv in invocations or [set()]
    ]
    return per[0] if all(per) else []


def classify(
    site: Site,
    invocations: list[set[str]],
    pragma: tuple[str, str, str] | None,
    *,
    needed: bool = False,
) -> tuple[str, str]:
    """One site under one entry's registered invocations, to exactly one bucket, with a note.

    `needed` says the same line is NOT safe in some other calling context or entry: a `safe` pragma it carries is then doing work there and is not stale here.
    """
    gated = gating(site.guard, invocations)
    passed = set().union(*invocations) if invocations else set()
    if pragma is not None and len(pragma[2]) < MIN_REASON:
        return "BAD-PRAGMA", "pragma reason %r is shorter than %d characters" % (
            pragma[2],
            MIN_REASON,
        )
    if site.origin in SAFE_ORIGINS:
        if pragma is not None and pragma[0] == "safe" and not needed:
            return "STALE", "a `safe` pragma on a site the scanner resolves as %s" % site.origin
        return "SAFE", site.origin
    if gated:
        return "MODE-GATED", "only under %s" % " / ".join("|".join(c) for c in gated)
    if pragma is not None and pragma[0] == "mode":
        if pragma[1] and pragma[1] not in passed:
            return "MODE-GATED", "only under %s (pragma)" % pragma[1]
        return (
            site.origin if site.origin == "TREE" else "UNRESOLVED",
            "mode pragma names %r, which a registered invocation passes" % pragma[1],
        )
    if site.origin == "TREE":
        return (
            "TREE",
            "a `safe` pragma cannot overrule a proven tree write" if pragma is not None else "",
        )
    if pragma is not None and pragma[0] == "safe":
        return "DECLARED", pragma[2]
    return "UNRESOLVED", ""


# --------------------------------------------------------------------------- the pipeline


def _bash_sites(root: pathlib.Path, rel: str) -> list[Site]:
    try:
        text = (root / rel).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    out: list[Site] = []
    lines = text.split("\n")
    for hit in pool_writer_safety.scan_text(text, rel):
        m = re.match(r"^(.*?):(\d+): (.*)$", hit)
        if m:
            line = int(m.group(2))
            flag = bash_mode_flag(lines, line)
            out.append(Site(rel, line, "bash", m.group(3)[:100], "TREE", [[flag]] if flag else []))
    return out


BASH_TEST_RE = re.compile(
    r"^\s*(?:if|elif)\s+\[\[\s*\"?\$\{?(\w+)[^\"\s]*\"?\s*==\s*\"?([\w.-]+)\"?\s*\]\]"
)
BASH_ASSIGN_RE = re.compile(r"^\s*(\w+)=\"?([\w.-]+)\"?\s*$")


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip())


def _enclosing_test(lines: list[str], line: int) -> tuple[str, str] | None:
    """The nearest `if/elif [[ "$VAR" == "value" ]]` whose body holds 1-based `line`, by indentation."""
    here = _indent(lines[line - 1]) if 0 < line <= len(lines) else 0
    for i in range(line - 2, -1, -1):
        text = lines[i]
        if not text.strip() or text.lstrip().startswith("#") or _indent(text) >= here:
            continue
        m = BASH_TEST_RE.match(text)
        if m:
            return m.group(1), m.group(2)
        if text.lstrip().startswith(
            ("if ", "elif ", "else", "case ", "for ", "while ", "function ")
        ) or re.match(r"^\s*\w+\s*\(\)", text):
            here = _indent(text)
    return None


def bash_mode_flag(lines: list[str], line: int) -> str | None:
    """The flag a bash write is gated by: `if [[ "$MODE" == "write" ]]` where `MODE="write"` is set only under `ARG_WRITE == "true"` (the `parse_args` shape), or directly `ARG_WRITE == "true"`. Mirrors the Python/TS guard recognition so a bash writer needs no pragma for the same shape."""
    test = _enclosing_test(lines, line)
    if test is None:
        return None
    var, value = test
    arg = re.match(r"^ARG_(\w+)$", var)
    if arg and value == "true":
        return "--" + arg.group(1).lower().replace("_", "-")
    for n, text in enumerate(lines, start=1):
        m = BASH_ASSIGN_RE.match(text)
        if m and m.group(1) == var and m.group(2) == value:
            inner = _enclosing_test(lines, n)
            if inner is not None:
                arg = re.match(r"^ARG_(\w+)$", inner[0])
                if arg and inner[1] == "true":
                    return "--" + arg.group(1).lower().replace("_", "-")
    return None


def analyze(
    root: pathlib.Path,
    lock_path: pathlib.Path,
    pkg_path: pathlib.Path | None,
    repo: pathlib.Path,
    required: dict[str, str],
) -> Result:
    """The whole pipeline over one tree. `repo` is where the TS helper lives; `root` is the tree being judged."""
    res = Result([], [], [], {}, [], {}, 0, [], set(), {})
    try:
        lock = json.loads(lock_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        res.refusals.append("the gate lock at %s is missing or unparseable (%s)" % (lock_path, exc))
        return res
    if not isinstance(lock, list):
        res.refusals.append("the gate lock at %s is not a JSON list" % lock_path)
        return res
    args = ["--invocations", "--lock", str(lock_path), "--root", str(root)]
    if pkg_path is not None:
        args += ["--pkg", str(pkg_path)]
    inv, err = run_helper(repo, args)
    if not isinstance(inv, dict):
        res.refusals.append(err or "the TS extractor returned no invocations")
        return res
    entries = scheduled(lock)
    py = Analyzer(root, load_mutators(root, repo))
    plan: dict[str, dict[str, set[str]]] = {}
    argvs: dict[str, list[set[str]]] = {}
    for e in entries:
        eid = e["id"]
        files: dict[str, set[str]] = {"py": set(), "ts": set(), "sh": set()}
        argvs[eid] = []
        for leaf in inv.get(eid, []):
            name = leaf.get("leaf", "")
            argvs[eid].append({a for a in leaf.get("argv", []) if isinstance(a, str)})
            if not (root / name).is_file():
                res.bare.append("%s: %s" % (eid, name))
                continue
            if name.endswith(PY_EXT):
                files["py"].add(name)
            elif name.endswith(TS_EXT):
                files["ts"].add(name)
            elif name.endswith(SH_EXT):
                files["sh"].add(name)
            else:
                res.bare.append("%s: %s" % (eid, name))
        if any(files.values()):
            plan[eid] = files
    res.entries_scanned = len(plan)
    if not plan:
        res.refusals.append("zero lock entries resolved to a scannable leaf")
        return res
    site_sets: dict[str, dict[tuple[str, int, str, str, str, str], tuple[Site, str]]] = {
        eid: {} for eid in plan
    }
    done_py: dict[str, set[str]] = {eid: set() for eid in plan}
    done_ts: dict[str, set[str]] = {eid: set() for eid in plan}
    for _round in range(6):
        changed = False
        for eid, files in plan.items():
            if files["py"] and files["py"] != done_py[eid]:
                done_py[eid] = set(files["py"])
                g = py.analyze_group(sorted(files["py"]))
                res.closures.setdefault(eid, set()).update(g.modules)
                for err_line in g.errors:
                    res.findings.append("%s: cannot parse %s" % (eid, err_line))
                for s in g.sites:
                    site_sets[eid][_key(s)] = (s, "py")
                for f, flags in g.spawns:
                    for argv in argvs[eid]:
                        argv.update(flags)
                    kind = (
                        "ts"
                        if f.endswith(TS_EXT)
                        else "sh"
                        if f.endswith(SH_EXT)
                        else "py"
                        if f.endswith(PY_EXT)
                        else ""
                    )
                    if kind and f not in files[kind]:
                        files[kind].add(f)
                        changed = True
        groups = {
            eid: sorted(files["ts"])
            for eid, files in plan.items()
            if files["ts"] and files["ts"] != done_ts[eid]
        }
        if groups:
            out, err = run_helper(
                repo, ["--batch"], json.dumps({"root": str(root), "groups": groups})
            )
            if not isinstance(out, dict):
                res.refusals.append(err or "the TS extractor returned no groups")
                return res
            for eid, g in out.items():
                done_ts[eid] = set(groups[eid])
                res.closures.setdefault(eid, set()).update(g.get("modules", []))
                res.product.update(g.get("product", []))
                for err_line in g.get("errors", []):
                    res.findings.append("%s: cannot parse %s" % (eid, err_line))
                for s in g.get("sites", []):
                    site = Site(
                        s["file"],
                        s["line"],
                        s["sink"],
                        s["target"],
                        s["origin"],
                        s.get("guard", []),
                    )
                    site_sets[eid][_key(site)] = (site, "ts")
                for sp in g.get("spawns", []):
                    f = sp["file"]
                    for argv in argvs[eid]:
                        argv.update(sp.get("argv", []))
                    kind = "sh" if f.endswith(SH_EXT) else "py" if f.endswith(PY_EXT) else ""
                    if kind and f not in plan[eid][kind]:
                        plan[eid][kind].add(f)
                        changed = True
        if not changed and not groups:
            break
    for eid, files in plan.items():
        res.closures.setdefault(eid, set()).update(files["sh"])
        for rel in files["sh"]:
            for s in _bash_sites(root, rel):
                site_sets[eid][_key(s)] = (s, "sh")
    _judge(root, lock, plan, site_sets, argvs, required, res)
    return res


def _key(s: Site) -> tuple[str, int, str, str, str, str]:
    return (s.file, s.line, s.sink, s.target, s.origin, json.dumps(s.guard))


def _judge(
    root: pathlib.Path,
    lock: list,
    plan: dict,
    site_sets: dict,
    argvs: dict,
    required: dict[str, str],
    res: Result,
) -> None:
    pragmas = Pragmas(root)
    by_id = {e.get("id"): e for e in lock if isinstance(e, dict)}
    worst: dict[tuple[str, int, str, str], tuple[str, str]] = {}
    # A pragma is stale only where its line is safe EVERYWHERE: in every calling context, under every entry that reaches it.
    unsafe_lines = {
        (site.file, site.line)
        for eid in plan
        for site, _lang in site_sets[eid].values()
        if site.origin not in SAFE_ORIGINS
    }
    for eid in sorted(plan):
        entry = by_id.get(eid, {})
        tree_sites: list[Verdict] = []
        # One site may arrive in several CALLING CONTEXTS (gate_tree_writes_py.Analyzer.sites_of); the worst context is the site's verdict.
        best: dict[tuple[str, int, str, str], tuple[Site, str, str, str]] = {}
        for _k, (site, lang) in sorted(site_sets[eid].items()):
            bucket, note = classify(
                site,
                argvs[eid],
                pragmas.at(site.file, site.line),
                needed=(site.file, site.line) in unsafe_lines,
            )
            base = (site.file, site.line, site.sink, site.target)
            prev_b = best.get(base)
            if prev_b is None or SEVERITY[bucket] > SEVERITY[prev_b[2]]:
                best[base] = (site, lang, bucket, note)
        declared = exclusive_tree(entry) and bool(entry.get("writesTree"))
        for key, (site, lang, bucket0, note) in sorted(best.items()):
            # An entry that already holds an exclusive tree: claim and says what it writes is serialised whatever the site resolves to, so an unresolved write inside it cannot overlap a reader: COVERED, reported, not red.
            bucket = "COVERED" if bucket0 == "UNRESOLVED" and declared else bucket0
            v = Verdict(eid, site, bucket, note)
            res.verdicts.append(v)
            prev = worst.get(key)
            if prev is None or SEVERITY[bucket] > SEVERITY[prev[1]]:
                worst[key] = (lang, bucket)
            if bucket == "TREE":
                tree_sites.append(v)
            elif bucket in ("UNRESOLVED", "STALE", "BAD-PRAGMA"):
                res.findings.append(
                    "%s: %s:%d: %s %s -> %s%s. %s"
                    % (
                        eid,
                        site.file,
                        site.line,
                        site.sink,
                        site.target,
                        bucket,
                        " (%s)" % note if note else "",
                        "Resolve it to a temp path, or declare it on the line or the line above with `# tree-write: safe <reason>` (`//` in TS/JS)."
                        if bucket == "UNRESOLVED"
                        else "Fix the pragma.",
                    )
                )
        if tree_sites and not (exclusive_tree(entry) and entry.get("writesTree")):
            lines = "\n".join(
                "    %s:%d: %s %s%s"
                % (
                    v.site.file,
                    v.site.line,
                    v.site.sink,
                    v.site.target,
                    " (%s)" % v.note if v.note else "",
                )
                for v in tree_sites
            )
            res.findings.append(
                "%s writes the real tree but does not declare an exclusive tree: claim plus writesTree:\n%s\n  %s"
                % (eid, lines, MUTEX_ADVICE)
            )
        if entry.get("writesTree") and not tree_sites:
            res.declared_unused.append(eid)
    for e in lock:
        if not isinstance(e, dict):
            continue
        if e.get("writesTree") and not exclusive_tree(e):
            res.findings.append(
                "%s declares writesTree but holds no exclusive tree: claim (`mutex`, not `reads`)"
                % e.get("id")
            )
        if exclusive_tree(e) and not e.get("writesTree"):
            res.findings.append(
                "%s holds an exclusive tree: claim but no writesTree reason naming what it writes"
                % e.get("id")
            )
    for eid, want in required.items():
        if eid in plan and want not in res.closures.get(eid, set()):
            res.refusals.append(
                "the closure of %s does not contain %s: the spawn edge that reaches it broke"
                % (eid, want)
            )
    for lang, bucket in worst.values():
        res.counts.setdefault(lang, {}).setdefault(bucket, 0)
        res.counts[lang][bucket] += 1
    for f in {k[0] for k in worst}:
        n = pragmas.count(f)
        if n:
            res.pragmas[f] = n


def vacuity(res: Result, floor_py: int, floor_ts: int) -> list[str]:
    out: list[str] = []
    py_total = sum(res.counts.get("py", {}).values())
    ts_total = sum(res.counts.get("ts", {}).values())
    if py_total < floor_py:
        out.append(
            "only %d Python site(s) seen, under the floor of %d: the scanner stopped reading the tree"
            % (py_total, floor_py)
        )
    if ts_total < floor_ts:
        out.append(
            "only %d TS/JS site(s) seen, under the floor of %d: the scanner stopped reading the tree"
            % (ts_total, floor_ts)
        )
    safe = sum(c.get("SAFE", 0) for c in res.counts.values())
    if safe == 0:
        out.append("zero TEMP sites: the TEMP seeds died")
    live = sum(c.get("TREE", 0) + c.get("MODE-GATED", 0) for c in res.counts.values())
    if live == 0:
        out.append(
            "zero TREE-or-MODE-GATED sites: the TREE seeds died (the live tree has confirmed mode-gated writers)"
        )
    return out


# --------------------------------------------------------------------------- controls

FIXTURE: dict[str, str] = {
    "c1/a/b/gate.mjs": "import fs from 'node:fs';\nimport path from 'node:path';\nconst HERE = import.meta.dirname;\nconst ROOT = path.resolve(HERE, '../../..');\nfor (const fx of [{ file: 'x.ts' }]) fs.appendFileSync(path.join(ROOT, fx.file), 'code');\nfs.writeFileSync(path.join(ROOT, 'private/account/src/__x.ts'), '');\n",
    "c1m/gate.mjs": "import fs from 'node:fs';\nimport os from 'node:os';\nimport path from 'node:path';\nconst ROOT = path.resolve(import.meta.dirname, '..');\nconst mirrorRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'biome-plugin-liveness-'));\nfor (const fx of [{ file: 'x.ts' }]) fs.writeFileSync(path.join(mirrorRoot, fx.file, ROOT), '');\n",
    "c2/gate.py": 'import pathlib\n\nfrom rediacc_ci import paths\n\nprobe = pathlib.Path(paths.repo_root()) / "enum_probe.py"\nprobe.write_text("x")\n',
    "c2m/gate.py": 'import pathlib\nimport tempfile\n\nwith tempfile.TemporaryDirectory() as tmp:\n    root = pathlib.Path(tmp)\n    (root / ".github").mkdir(parents=True)\n',
    "c3/gate.py": 'import shutil\n\nfrom rediacc_ci import paths\n\n\ndef stage(root):\n    shutil.copyfile("a", root / "x")\n\n\nstage(paths.repo_root())\n',
    "c3m/gate.py": 'import shutil\nimport tempfile\n\n\ndef stage(root):\n    shutil.copyfile("a", root / "x")\n\n\nstage(tempfile.mkdtemp())\n',
    "c4/entry.py": 'import pathlib\nimport subprocess\n\nDRIVER = "d.mjs"\nsubprocess.run(["node", str(pathlib.Path(__file__).parent / DRIVER)], check=True)\n',
    "c4/d.mjs": "import fs from 'node:fs';\nimport path from 'node:path';\nconst ROOT = path.resolve(import.meta.dirname, '..');\nfs.writeFileSync(path.join(ROOT, 'f'), '');\n",
    "c4m/entry.py": 'import pathlib\nimport subprocess\n\nDRIVER = "missing.mjs"\nsubprocess.run(["node", str(pathlib.Path(__file__).parent / DRIVER)], check=True)\n',
    "c5/gate.py": 'import sys\n\nfrom rediacc_ci import paths\n\nargv = sys.argv[1:]\nroot = paths.repo_root()\nif "--reseed" in argv:\n    (root / "BASE").write_text("x")\n',
    "c7/g.ts": "import type { T } from './lib';\nexport const x: T | null = null;\n",
    "c7/lib.ts": "import fs from 'node:fs';\nexport type T = number;\nexport function save(): void {\n  fs.writeFileSync('packages/www/src/data/m.json', '');\n}\n",
    "c7m/g.ts": "import { save } from '../c7/lib.js';\nsave();\n",
    "c8/gate.py": 'import pathlib\nimport sys\n\n\ndef put(p):\n    p.write_text("x")  # tree-write: safe the caller hands a fixture path it built itself\n\n\nput(pathlib.Path(sys.argv[1]))\n',
    "c8b/gate.py": 'import pathlib\nimport tempfile\n\nroot = pathlib.Path(tempfile.mkdtemp())\n# tree-write: safe this pragma is stale because the target is a temp dir\n(root / "x").write_text("x")\n',
    "c8c/gate.py": 'from rediacc_ci import paths\n\n# tree-write: safe a pragma cannot overrule a write the scanner proved\n(paths.repo_root() / "x").write_text("x")\n',
    "c9/gate.py": 'import subprocess\n\nsubprocess.run(["git", "add", "-A"], check=True)\n',
    "c9m/gate.py": 'import subprocess\nimport tempfile\n\ntmp = tempfile.mkdtemp()\nsubprocess.run(["git", "add", "-A"], cwd=tmp, check=True)\n',
    "c9t/g.ts": "import { execSync } from 'node:child_process';\nimport path from 'node:path';\nconst ROOT = path.resolve(import.meta.dirname, '..');\nexecSync('sed -i s/a/b/ ' + path.join(ROOT, 'f'));\n",
    "c10/gate.py": 'from rediacc_ci import paths\n\n(paths.repo_root() / ".ci" / "cache" / "x").mkdir()\n',
    "c11/gate.sh": '#!/bin/bash\nREPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"\nMANIFEST="$REPO_ROOT/MANIFEST"\nMODE="verify"\nif [[ "${ARG_WRITE:-}" == "true" ]]; then\n    MODE="write"\nfi\nif [[ "$MODE" == "write" ]]; then\n    {\n        echo x\n    } >"$MANIFEST"\nfi\nprintf y >"$REPO_ROOT/always"\n',
    "c10m/gate.py": 'from rediacc_ci import paths\n\n(paths.repo_root() / "packages" / "www" / "dist").mkdir()\n',
}

CONTROL_LOCK: list[dict] = [
    {"id": "c1", "run": "node c1/a/b/gate.mjs", "gate": True},
    {"id": "c1m", "run": "node c1m/gate.mjs", "gate": True},
    {"id": "c2", "run": "c2/gate.py", "gate": True},
    {"id": "c2m", "run": "c2m/gate.py", "gate": True},
    {"id": "c3", "run": "c3/gate.py", "gate": True},
    {"id": "c3m", "run": "c3m/gate.py", "gate": True},
    {"id": "c4", "run": "c4/entry.py", "gate": True},
    {"id": "c4m", "run": "c4m/entry.py", "gate": True},
    {"id": "c5", "run": "c5/gate.py", "gate": True},
    {"id": "c5m", "run": "c5/gate.py --reseed", "gate": True},
    {
        "id": "c6a",
        "run": "node c1/a/b/gate.mjs",
        "gate": True,
        "mutex": ["tree:repo"],
        "writesTree": "the fixture writes the root on purpose",
    },
    {
        "id": "c6b",
        "run": "node c1/a/b/gate.mjs",
        "gate": True,
        "reads": ["tree:repo"],
        "writesTree": "a shared claim is not a writer claim",
    },
    {"id": "c6c", "run": "node c1/a/b/gate.mjs", "gate": True, "mutex": ["tree:repo"]},
    {
        "id": "c6d",
        "run": "node c1m/gate.mjs",
        "gate": True,
        "writesTree": "a reason with no claim behind it",
    },
    {"id": "c7", "run": "tsx c7/g.ts", "gate": True},
    {"id": "c7m", "run": "tsx c7m/g.ts", "gate": True},
    {"id": "c8", "run": "c8/gate.py", "gate": True},
    {"id": "c8b", "run": "c8b/gate.py", "gate": True},
    {"id": "c8c", "run": "c8c/gate.py", "gate": True},
    {"id": "c9", "run": "c9/gate.py", "gate": True},
    {"id": "c9m", "run": "c9m/gate.py", "gate": True},
    {"id": "c9t", "run": "tsx c9t/g.ts", "gate": True},
    {"id": "c10", "run": "c10/gate.py", "gate": True},
    {"id": "c10m", "run": "c10m/gate.py", "gate": True},
    {"id": "c11", "run": "c11/gate.sh", "gate": True},
    {"id": "c11m", "run": "c11/gate.sh --write", "gate": True},
]
CONTROL_REQUIRED = {"c4": "c4/d.mjs", "c4m": "c4m/missing.mjs"}


def _red(res: Result, eid: str) -> list[str]:
    """Findings that name an entry, by the id at the start of the finding."""
    return [f for f in res.findings if f.startswith((eid + ":", eid + " "))]


def _buckets(res: Result, eid: str) -> list[str]:
    return sorted(v.bucket for v in res.verdicts if v.entry == eid)


def build_fixture(dest: pathlib.Path, repo: pathlib.Path) -> None:
    """Plant the control tree. Copied, never symlinked (pool_writer_safety.py records why)."""
    for rel, body in FIXTURE.items():
        p = dest / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    (dest / ".ci" / "config").mkdir(parents=True, exist_ok=True)
    shutil.copyfile(repo / MUTATORS_REL, dest / MUTATORS_REL)
    (dest / "lock.json").write_text(json.dumps(CONTROL_LOCK), encoding="utf-8")
    (dest / "package.json").write_text(json.dumps({"scripts": {}}), encoding="utf-8")


def run_controls(repo: pathlib.Path, check: object) -> None:
    """C1-C10 (PLAN section 4) through the whole pipeline over a planted tree. `check(label, cond)` records each."""
    record = check  # a Checker-shaped callable
    with tempfile.TemporaryDirectory(prefix="gate-tree-writes-") as tmp:
        root = pathlib.Path(tmp)
        build_fixture(root, repo)
        res = analyze(root, root / "lock.json", root / "package.json", repo, CONTROL_REQUIRED)
        c1 = _red(res, "c1")
        _call(
            record,
            "C1: the TS tree writer is red and names both sites",
            len(c1) == 1 and "gate.mjs:5:" in c1[0] and "gate.mjs:6:" in c1[0],
        )
        _call(
            record,
            "C1': the temp mirror with a decoy ROOT in the join is green",
            not _red(res, "c1m") and set(_buckets(res, "c1m")) == {"SAFE"},
        )
        _call(record, "C2: the Python repo-root probe (V1 shape) is red", bool(_red(res, "c2")))
        _call(
            record,
            "C2': `root = pathlib.Path(tmp)` is green whatever it is called",
            not _red(res, "c2m") and _buckets(res, "c2m") == ["SAFE"],
        )
        _call(
            record,
            "C3: a parameter called with repo_root() is red (V3 shape)",
            bool(_red(res, "c3")),
        )
        _call(record, "C3': the same body called only with mkdtemp is green", not _red(res, "c3m"))
        _call(
            record,
            "C4: the spawn edge reaches d.mjs and it is red",
            any("c4/d.mjs:4:" in f for f in _red(res, "c4")),
        )
        _call(
            record,
            "C4': a DRIVER naming a missing file is a closure refusal, not a green",
            any("c4m/missing.mjs" in r for r in res.refusals),
        )
        _call(
            record,
            "C5: a --reseed write with argv [] is green and MODE-GATED",
            not _red(res, "c5") and _buckets(res, "c5") == ["MODE-GATED"],
        )
        _call(
            record,
            "C5': the same write with --reseed registered is red",
            bool(_red(res, "c5m")),
        )
        _call(record, "C6: mutex tree:repo plus writesTree is green", not _red(res, "c6a"))
        _call(record, "C6: reads tree:repo is red", bool(_red(res, "c6b")))
        _call(record, "C6: mutex without writesTree is red", bool(_red(res, "c6c")))
        _call(record, "C6: writesTree without mutex is red", bool(_red(res, "c6d")))
        _call(
            record,
            "C7: a type-only import is green and does not enter lib.ts",
            not _red(res, "c7") and "c7/lib.ts" not in res.closures.get("c7", set()),
        )
        _call(record, "C7': a value import that calls the writer is red", bool(_red(res, "c7m")))
        _call(
            record,
            "C8: an UNRESOLVED site with a safe pragma is green (DECLARED)",
            not _red(res, "c8") and _buckets(res, "c8") == ["DECLARED"],
        )
        _call(
            record,
            "C8: the same pragma on a TEMP site is red (STALE)",
            any("STALE" in f for f in _red(res, "c8b")),
        )
        _call(record, "C8: the same pragma on a TREE site is still red", bool(_red(res, "c8c")))
        _call(record, "C9: git add -A with no cwd is red", bool(_red(res, "c9")))
        _call(record, "C9: git add -A with cwd=tmp is green", not _red(res, "c9m"))
        _call(
            record,
            "C9: execSync('sed -i ... ' + path.join(ROOT, f)) is red",
            bool(_red(res, "c9t")),
        )
        _call(
            record,
            "C10: repo_root()/.ci/cache/x is green (SCRATCH)",
            not _red(res, "c10") and _buckets(res, "c10") == ["SAFE"],
        )
        _call(record, "C10: repo_root()/packages/www/dist is red", bool(_red(res, "c10m")))
        c11 = [v for v in res.verdicts if v.entry == "c11"]
        _call(
            record,
            "C11: a bash write under MODE=write (ARG_WRITE) is MODE-GATED; the unguarded one is TREE",
            sorted((v.site.line, v.bucket) for v in c11) == [(11, "MODE-GATED"), (13, "TREE")],
        )
        _call(
            record,
            "C11': with --write registered the gated write is TREE too",
            sum(v.bucket == "TREE" for v in res.verdicts if v.entry == "c11m") == 2,
        )


def _call(record: object, label: str, cond: bool) -> None:
    fn = record
    if callable(fn):
        fn(label, cond)


def real_checks(res: Result, lock: list, check: object) -> None:
    """REAL: the live tree is not empty in the ways that matter."""
    lr = "check:ci-lint-rule-liveness"
    _call(
        check,
        "REAL: the lint-rule-liveness closure contains lint-rule-liveness.mjs",
        REQUIRED_SPAWNS[lr] in res.closures.get(lr, set()),
    )
    buckets = [v.bucket for v in res.verdicts]
    _call(check, "REAL: at least one SAFE (TEMP) site", "SAFE" in buckets)
    _call(check, "REAL: at least one MODE-GATED site", "MODE-GATED" in buckets)
    pytest = next((e for e in lock if isinstance(e, dict) and e.get("id") == "check:ci-pytest"), {})
    _call(
        check,
        "REAL: check:ci-pytest carries both tree:repo and writesTree",
        exclusive_tree(pytest) and bool(pytest.get("writesTree")),
    )


# --------------------------------------------------------------------------- output


def print_report(res: Result, full: bool) -> None:
    langs = sorted(res.counts)
    print(
        "gate-tree-writes: %d entr(ies) scanned, %d bare leaf/leaves not scanned, %d product module(s) not entered"
        % (res.entries_scanned, len(res.bare), len(res.product))
    )
    for lang in langs:
        c = res.counts[lang]
        print("  %-3s %s" % (lang, ", ".join("%s=%d" % (k, c[k]) for k in sorted(c))))
    print("  pragmas: %d across %d file(s)" % (sum(res.pragmas.values()), len(res.pragmas)))
    for f, n in sorted(res.pragmas.items()):
        print("    %s: %d" % (f, n))
    for eid in res.declared_unused:
        print("  declared, no site found: %s" % eid)
    if full:
        seen: set[tuple[str, str, int, str]] = set()
        for v in sorted(res.verdicts, key=lambda x: (x.bucket, x.site.file, x.site.line, x.entry)):
            if v.bucket == "SAFE":
                continue
            key = (v.bucket, v.site.file, v.site.line, v.site.sink)
            if key in seen:
                continue
            seen.add(key)
            entries = sorted(
                {
                    x.entry
                    for x in res.verdicts
                    if (x.site.file, x.site.line, x.site.sink) == key[1:] and x.bucket == v.bucket
                }
            )
            print(
                "  %-10s %s:%d: %s %s%s  [%s]"
                % (
                    v.bucket,
                    v.site.file,
                    v.site.line,
                    v.site.sink,
                    v.site.target,
                    " (%s)" % v.note if v.note else "",
                    ", ".join(entries[:4])
                    + (" +%d" % (len(entries) - 4) if len(entries) > 4 else ""),
                )
            )
        for b in res.bare:
            print("  bare-leaf, not scanned: %s" % b)


def _opt(argv: list[str], name: str) -> str | None:
    if name in argv:
        i = argv.index(name)
        return argv[i + 1] if i + 1 < len(argv) else None
    return None


class _Tally:
    """PASS lines only under `--selftest`; a gate run prints a count, and every FAIL."""

    def __init__(self, *, verbose: bool) -> None:
        self.ok = 0
        self.bad: list[str] = []
        self.verbose = verbose

    def __call__(self, label: str, cond: bool) -> None:
        if cond:
            self.ok += 1
            if self.verbose:
                print("  PASS  %s" % label)
        else:
            self.bad.append(label)
            print("  FAIL  %s" % label, file=sys.stderr)


def selftest(repo: pathlib.Path) -> int:
    """The controls alone, plus the TS helper's own selftest. Floor: every control must run."""
    tally = _Tally(verbose=True)
    run_controls(repo, tally)
    proc = subprocess.run(
        [*_helper_cmd(repo), "--selftest"],
        capture_output=True,
        text=True,
        cwd=str(repo),
        check=False,
    )
    tally(
        "TS helper --selftest exits 0 (%s)"
        % (proc.stdout.strip().split("\n")[-1] if proc.stdout else proc.stderr.strip()[-200:]),
        proc.returncode == 0,
    )
    total = tally.ok + len(tally.bad)
    if total < SELFTEST_FLOOR:
        print(
            "FAIL  only %d control(s) ran; the file is not being executed as written" % total,
            file=sys.stderr,
        )
        return 1
    if tally.bad:
        print("FAIL: %d of %d control(s) failed" % (len(tally.bad), total), file=sys.stderr)
        return 1
    print("%d control(s) passed" % total)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = list(argv or [])
    repo = paths.repo_root()
    if "--selftest" in args:
        return selftest(repo)
    report = "--report" in args
    root = pathlib.Path(_opt(args, "--root") or repo)
    lock_path = pathlib.Path(_opt(args, "--lock") or root / LOCK_REL)
    pkg = _opt(args, "--pkg")

    # THE INPUTS FIRST, before a control needs them: against a tree with no lock, no package.json or no mutator table there is nothing to schedule and nothing to judge, and "judged nothing" must never read as "found nothing".
    missing = [
        str(p)
        for p in (
            lock_path,
            pathlib.Path(pkg) if pkg else root / "package.json",
            repo / MUTATORS_REL,
            repo / HELPER_REL,
        )
        if not p.is_file()
    ]
    if missing:
        log.error(
            "VACUOUS INPUT: %s missing, so no gate can be scheduled or judged" % ", ".join(missing)
        )
        return 1

    tally = _Tally(verbose=False)
    run_controls(repo, tally)
    if tally.bad:
        log.error(
            "CONTROL FAILED: %s. The scanner's verdict on the real tree would mean nothing."
            % "; ".join(tally.bad)
        )
        return 1

    res = analyze(root, lock_path, pathlib.Path(pkg) if pkg else None, repo, REQUIRED_SPAWNS)
    try:
        lock = json.loads(lock_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        lock = []
    refusals = list(res.refusals)
    # The floors and REAL describe THE LIVE TREE; a `--root` fixture (the differential proof of plan task 4.3) is judged on its findings alone.
    live = root.resolve() == repo.resolve()
    if not refusals and live:
        refusals += vacuity(res, 0 if report else FLOOR_PY, 0 if report else FLOOR_TS)
        real = _Tally(verbose=False)
        real_checks(res, lock, real)
        refusals += ["REAL control failed: %s" % b for b in real.bad]
    print_report(res, full=report)
    if report:
        for f in res.findings:
            print("  finding: %s" % f)
        for r in refusals:
            print("  refusal: %s" % r)
        return 0
    if refusals:
        for r in refusals:
            log.error("check-gate-tree-writes: refusing to pass: %s" % r)
        return 1
    if res.findings:
        for f in res.findings:
            log.error(f)
        log.error(
            "%d finding(s). A gate that writes the shared tree without declaring it runs beside its readers and leaves residue on a hard kill."
            % len(res.findings)
        )
        return 1
    log.info(
        "every tree write reached by a scheduled gate is declared, gated, or temp (%d controls fired in both directions, so this verdict is real)"
        % tally.ok
    )
    return 0
