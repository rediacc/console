r"""Python files no execution route reaches.

Go has `deadcode`, TypeScript has knip, and bash has `scripts/gates/check-dead-bash.ts`. Python had nothing, across 592 tracked `.py` files, which is now the largest body of code in this repository and the one the tooling transformation is actively growing: every workstream that ports a bash gate ADDS a Python file, and W7's shadow protocol deliberately lands the new side BEFORE
the old side is deleted. A port that shadowed green and was then forgotten is invisible to every other instrument in the tree, because nothing is broken by it: the bash twin is still registered, still runs, still passes.

WHAT MAKES THIS DIFFERENT FROM THE BASH GATE, and it is not the language. `check-dead-bash.ts` asks "is this basename mentioned by any other tracked file", which for bash is adequate because a shell script is only ever reached by being NAMED. Python is reached four other ways -- imported, collected by pytest, loaded by a package glob, re-executed by a forwarder -- and it is also
MENTIONED constantly in prose that reaches nothing: this repository's `agent/` directory alone names hundreds of Python paths in plans and briefs. Applying the bash predicate to Python would therefore admit every dead file that any plan ever discussed. So prose is NOT an admission route here, and the routes that are ones are enumerated rather than inferred.

THE ROUTES, and each is a different way a file actually executes:

  wired      Its path or a path-suffix of it appears in one of the WIRING files:
             `package.json`, the manifest, the gate lock, a workflow, the hook
             settings, or `pyproject.toml`. This is "registered", and it is the
             route a gate entry point is SUPPOSED to have.
  pytest     Collected by pytest: under a `testpaths` root and matching
             `python_files`, or a `conftest.py`, both read out of
             `pyproject.toml` rather than typed here. 235 files today have no
             registration at all and are perfectly alive through this route.
  shadow     Named as the NEW side of a `.ci/shadow/*.jsonl` record whose
             verdict is EQUIVALENT and WHOSE BASH TWIN STILL EXISTS ON DISK.
             This route EXPIRES when the twin is deleted, which is the whole
             value of the gate: at that moment route `wired` must have taken
             over, and if it has not, the port is a file nothing runs.
  glob       Discovered by a directory glob inside the program itself. Declared
             BY NAME below with the code that does the globbing, never inferred:
             a glob built at runtime is not decidable from the source.
  imported   Imported, transitively, from anything already reached. Resolved
             from the AST, against the package roots the tree really uses.
  mentioned  Its path or path-suffix appears in the text of something already
             reached and not prose. A forwarder invoked as
             `"$(dirname "$0")/../stop/worklist.py"`, a fixture a gate rewrites
             by path, a test harness that runs a script under a relative name:
             all real, none of them imports.

WHICH DIRECTION TO BE WRONG IN. A false POSITIVE here asks a human to delete live code, so every route above is deliberately generous: a path-SUFFIX match counts, a mention in a comment counts, and a mention inside a dead-but-not-yet- reported file counts if that file is itself reached. The cost of that generosity is stated in the shape line, which prints how many files each route
carries, so a reader can see when a route starts carrying implausibly many.

WHICH ROUTES ARE LOAD-BEARING TODAY, measured by ablation on 2026-09-08 rather than assumed, because a route nobody needs is a route nobody notices breaking:

  glob    removing it changes NO verdict. All 44 guards are also mentioned by
          `scripts/data/hook-inventory-baseline.json` and `.claude/settings.json`,
          so they would be admitted anyway. It is kept for two reasons and both
          are about being wrong in the right direction: `glob` is the TRUE claim
          about how those files are loaded, where `mentioned by a generated
          inventory` is a weaker one that happens to hold; and the day that
          inventory stops listing them, this route is what stops 44 live guards
          from being reported dead in a single run.
  shadow  also changes no verdict today, and the reason is a drift in the plan
          box that asked for it: all five pre-cutover ports named in the ledgers
          are ALSO registered, so the stronger route claims them first. Its value
          is entirely the EXPIRY finding, which is exercised by controls rather
          than by the tree, and the shape line prints the route's count so the day
          it starts carrying files is visible.
  manual  load-bearing, exactly once: `.claude/rediacc_hooks/run_tests.py` has no
          other route at all.

ANTI-VACUITY. There are 11 refusals, all of them the same shape: the gate would rather say "I cannot see my subject" than emit a green nobody can act on. Zero Python files, zero referrers, a missing `pyproject.toml`, one that is not TOML, an empty `testpaths` or `python_files`, a missing wiring file, zero files admitted by `wired`, zero collected by `pytest`, a shadow ledger whose
records will not parse, a shadow directory that yields zero records at all, and a declared glob root that no longer exists.

THAT NUMBER IS CHECKED, not typed and left. A control parses this module's own AST, counts the `RefusalError` raise sites and compares them against the digit in the paragraph above, because the first draft said "nine" while the code had eleven. A docstring that miscounts its own refusals is how a reader concludes a condition is covered when it is not.
"""

from __future__ import annotations

import ast
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
from dataclasses import dataclass, field

from rediacc_ci import log, paths
from rediacc_ci.controls import Controls, plant

# The one root override, spelled the way `rediacc_ci.paths` spells it, so a harness that wants every gate pointed at a fixture sets ONE variable rather than learning this gate's private name.
ROOT_ENV = "REDIACC_CI_ROOT"

# The files whose text REGISTERS something. Named individually and required to exist: a wiring file that moves is a route that silently empties, and a route that silently empties turns live gates into findings.
WIRING_FILES = (
    "package.json",
    "pyproject.toml",
    "scripts/ci-runner/manifest.ts",
    "scripts/ci-runner/gates.lock.json",
    ".claude/settings.json",
)
WIRING_DIRS = (".github/workflows/",)

# Prose. A plan, a brief, a design doc and a status report all name Python paths by the hundred and execute none of them. `.ci/shadow/` is excluded here and handled as its own route SO THAT THE ROUTE CAN EXPIRE: a ledger entry is a permanent record of a comparison that happened once, so admitting it as an ordinary mention would keep a deleted twin's port alive forever.
PROSE_PREFIXES = ("agent/", "docs/", ".ci/shadow/")
PROSE_SUFFIXES = (".md", ".txt")

# Roots a dotted module name is resolved against, in the order the running programs really use them. `.ci` and `.claude` are on sys.path via `pyproject.toml`'s `pythonpath` and via `_cipath`; the repository root and `scripts/` are how the flat script directories reach their neighbours.
IMPORT_ROOTS = (".ci", ".claude", "", "scripts")

# GLOB DISCOVERY, declared by name with the site that does it, exactly as `.ci/policy/.dead-bash-allowlist` declares `glob:` for shell. Never inferred: `HERE.glob("*.py")` filtered by a prefix tuple is not something a static reader can be trusted to recognise, and guessing wrong in the permissive direction would admit a whole directory.
GLOB_ROOTS = {
    ".claude/rediacc_hooks/guards/": (
        ("block_", "warn_", "require_"),
        (
            "loaded by importlib from .claude/rediacc_hooks/guards/__init__.py:stems(), "
            "which globs *.py in its own directory and admits exactly these three "
            "prefixes; dispatch.py calls it, so no guard is ever named individually"
        ),
    ),
    ".claude/hooks/stop/": (
        ("test-",),
        (
            "run by .claude/rediacc_hooks/tests/test_hooks_delegates.py:_discover_tailed, "
            "which globs test-*.py under every _TAILED_ROOTS directory and asserts each "
            "exits 0 with non-empty output; no suite is named individually"
        ),
    ),
    ".claude/hooks/context/": (
        ("test-",),
        (
            "run by .claude/rediacc_hooks/tests/test_hooks_delegates.py:_discover_tailed, "
            "the same _TAILED_ROOTS glob as .claude/hooks/stop/"
        ),
    ),
}

# EXEMPT BY NAME, WITH THE REASON, AND PRINTED ON EVERY RUN. The `manual:` class of `.ci/policy/.dead-bash-allowlist`, in code rather than in a policy file because a seventeenth file in `.ci/policy/` has to be added to two POLICY_FILES lists and a README section in the same commit (see check:ci-policy-inventory), and one entry does not earn that.
#
# THE EXEMPTION IS ITSELF CHECKED, in both directions, which is what stops it
# from becoming the quiet kind. A named file that no longer exists is a finding,
# and so is a named file that has ACQUIRED a real route: at that moment the exemption stopped being true and the next reader would take it on trust. EMPTY SINCE 2026-09-09, and the emptiness is this mechanism WORKING rather than an absence of exemptions to make. The sole entry named `.claude/rediacc_hooks/run_tests.py`, and W8 P6's `.ci/config/python-env-registry.json` began
# listing that module the same day because it reads the environment. An inventory listing is a deliberate admission route here, not an accident of the matcher -- the `mentioned` route's own docstring names `scripts/data/hook-inventory-baseline.json` as what keeps 44 live guards admitted -- so the file acquired a real route and the exemption stopped being true. The gate said exactly
# that, in the direction that is easy to leave unchecked, and this is that assertion being obeyed rather than argued with.
#
# THE NEW ROUTE IS WEAKER THAN THE ONE IT REPLACED, and a future reader should know it: the exemption was unconditional, while the registry lists this module only for as long as it reads an environment variable. If that stops being true the file goes DEAD again with no exemption standing, and the answer then is to re-add an entry here with a fresh reason, not to assume the old one
# still applies.
MANUAL_ENTRY_POINTS: dict[str, str] = {
    # Quoted from its own docstring: "NOT A GATE. This file carries no `---- gate ----` block and is not registered: it is a one-off recovery tool kept beside the gate it repairs, so a future session that hits the same class has the instrument rather than the archaeology." Run by hand as `python3 .ci/scripts/quality/backfill_plan_implementation.py --me <prefix> [--write]`.
    ".ci/scripts/quality/backfill_plan_implementation.py": (
        "a one-off recovery tool kept beside check_plan_implementation.py, run by hand "
        "(--me <prefix> [--write]) to backfill the investigation trail for plan boxes "
        "closed without one; not a gate and deliberately not registered"
    ),
    # `.ci/rediacc_ci/version/resolve_version.py` was named here until W7P4-b's second family, with the reason "remove the entry the moment a real route lands". One landed: `.github/workflows/cd-v2.yml` calls the module, and `.ci/shadow/w7p4b-resolve-version.observations.jsonl` names it on the new side of ten rows. The gate reported the exemption as no longer true, in the direction
    # that is easy to leave unchecked, and this is that report being obeyed.
    # `.ci/rediacc_ci/ci_signal/create_complete.py` was named here with the reason "remove the entry the moment a real route lands". One landed: eight `ct-tests.yml` jobs call the module, and the greenlight closure that used to name the bash twin now names this file, so the gate reported the exemption as no longer true. The table is empty, which is the state it is
    # supposed to reach; an entry is added back only with a fresh reason of its own.
}

_PY_TOKEN = re.compile(r"[\w.\-/]*[\w\-]\.py")
# A port invoked as `python3 -m rediacc_ci.<pkg>.<mod>`, the form the workflow flips use, names no `.py` path.
_MODULE_TOKEN = re.compile(r"-m\s+rediacc_ci\.([\w.]+)")
_SH_TOKEN = re.compile(r"[\w.\-/]*[\w\-]\.sh")


class RefusalError(RuntimeError):
    """The gate cannot see its subject, so its green would mean nothing."""


@dataclass
class Report:
    routes: dict[str, str] = field(default_factory=dict)
    findings: list[dict] = field(default_factory=list)
    corpus: list[str] = field(default_factory=list)
    referrers: int = 0
    expired: dict[str, str] = field(default_factory=dict)
    shadow_records: int = 0
    manual: dict[str, str] = field(default_factory=dict)
    glob_roots: dict[str, int] = field(default_factory=dict)

    def by_route(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for r in self.routes.values():
            out[r] = out.get(r, 0) + 1
        return out


def tracked_files(root: pathlib.Path) -> list[str]:
    """Every file in the working tree: tracked PLUS untracked-but-not-ignored.

    `--others --exclude-standard` is load-bearing and is the same argument `check-dead-bash.ts` makes for it. A brand-new file is untracked, and this gate is a whole-tree reachability scan: with plain `ls-files` the commit that ADDS the caller for a new module reports that module as dead, which is the shape of ordinary work.
    """
    out = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if out.returncode != 0:
        # A fixture root is not a checkout. Walk it instead, and skip the same directories git would have skipped for us. `.git` and `node_modules` are `paths.walk_tree`'s standing prune (along with `.claude/worktrees`, a peer's sibling checkout that git also hides); `__pycache__` is this gate's own, because a `.pyc` is not a Python source file to audit.
        found = []
        for dirpath, _dirnames, filenames in paths.walk_tree(root, exclude_dirs=("__pycache__",)):
            found.extend(os.path.relpath(os.path.join(dirpath, name), root) for name in filenames)
        return sorted(found)
    return sorted({line for line in out.stdout.split("\n") if line and (root / line).is_file()})


def is_prose(rel: str) -> bool:
    return rel.startswith(PROSE_PREFIXES) or rel.endswith(PROSE_SUFFIXES)


def pytest_config(root: pathlib.Path) -> tuple[list[str], list[str]]:
    """`testpaths` and `python_files`, READ rather than restated.

    Typed into this file they would be a second copy of pytest's own answer, and the copy that goes stale is always the one nothing runs. `check_pytest` makes the same argument about the collection floor.
    """
    cfg = root / "pyproject.toml"
    if not cfg.is_file():
        raise RefusalError(
            "%s does not exist, so the pytest collection route cannot be resolved and "
            "every test file in the tree would be reported dead" % cfg
        )
    try:
        data = tomllib.loads(cfg.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise RefusalError("%s does not parse as TOML: %s" % (cfg, exc)) from exc
    ini = data.get("tool", {}).get("pytest", {}).get("ini_options", {})
    testpaths = list(ini.get("testpaths") or [])
    python_files = list(ini.get("python_files") or [])
    if not testpaths or not python_files:
        raise RefusalError(
            "pyproject.toml declares testpaths=%r and python_files=%r; an empty either "
            "way means this gate cannot tell a collected test from a dead file"
            % (testpaths, python_files)
        )
    return testpaths, python_files


def collected_by_pytest(
    paths: list[str], testpaths: list[str], python_files: list[str]
) -> set[str]:
    """The files pytest would import: a `conftest.py` anywhere, plus matches under a root."""
    globs = [re.compile(re.escape(p).replace(r"\*", "[^/]*") + r"\Z") for p in python_files]
    roots = [p.rstrip("/") + "/" for p in testpaths]
    out = set()
    for rel in paths:
        base = os.path.basename(rel)
        if base == "conftest.py":
            out.add(rel)
            continue
        if not any(rel.startswith(r) for r in roots):
            continue
        if any(g.match(base) for g in globs):
            out.add(rel)
    return out


def shadow_admissions(
    root: pathlib.Path, pyset: frozenset[str]
) -> tuple[dict[str, str], dict[str, str], int]:
    """(admitted, expired, records): the new side of every EQUIVALENT shadow record.

    ADMITTED means the twin named on the old side is still on disk. EXPIRED means it is not, and that is the finding this route exists to produce: the shadow protocol lands the port first and deletes the twin later, so the window between them is exactly when a forgotten port stops being run by anything and nothing else in the tree notices.
    """
    admitted: dict[str, str] = {}
    expired: dict[str, str] = {}
    records = 0
    shadow_dir = root / ".ci" / "shadow"
    if not shadow_dir.is_dir():
        return admitted, expired, records
    ledgers = sorted(shadow_dir.glob("*.jsonl"))
    for ledger in ledgers:
        for lineno, line in enumerate(ledger.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError as exc:
                raise RefusalError(
                    "%s:%d does not parse as JSON (%s); the shadow route would silently "
                    "admit nothing and every pre-cutover port would read as dead"
                    % (ledger.relative_to(root), lineno, exc)
                ) from exc
            records += 1
            if rec.get("verdict") != "EQUIVALENT":
                continue
            new_cmd = (rec.get("new") or {}).get("cmd", "")
            old_cmd = (rec.get("old") or {}).get("cmd", "")
            ports = [m for m in _PY_TOKEN.findall(new_cmd) if m in pyset]
            ports += [
                mod_path
                for mod in _MODULE_TOKEN.findall(new_cmd)
                for mod_path in (".ci/rediacc_ci/%s.py" % mod.replace(".", "/"),)
                if mod_path in pyset
            ]
            if not ports:
                continue
            twins = re.findall(_SH_TOKEN, old_cmd)
            live = [t for t in twins if (root / t).is_file()]
            for port in ports:
                if live:
                    admitted[port] = "%s (twin %s)" % (
                        ledger.name,
                        ", ".join(sorted(live)),
                    )
                elif port not in admitted:
                    expired[port] = "%s (twin %s is gone)" % (
                        ledger.name,
                        ", ".join(twins) or "unnamed",
                    )
    if ledgers and records == 0:
        raise RefusalError(
            "%d shadow ledger(s) under .ci/shadow/ yielded ZERO records; the shadow "
            "route is empty for a parsing reason, not a real one" % len(ledgers)
        )
    # A port whose twin is alive in one record and gone in another is ADMITTED: one live twin is enough to keep the pre-cutover window open.
    for port in list(expired):
        if port in admitted:
            del expired[port]
    return admitted, expired, records


def suffix_index(paths: list[str]) -> dict[str, list[str]]:
    """basename -> every corpus path with that basename."""
    index: dict[str, list[str]] = {}
    for rel in paths:
        index.setdefault(os.path.basename(rel), []).append(rel)
    return index


def mentioned_paths(text: str, index: dict[str, list[str]]) -> set[str]:
    r"""Corpus paths a body of text names, by full path or by path-suffix.

    A bare basename admits every corpus file with that name, which over-admits on purpose: two `worklist.py` exist, one a forwarder for the other, and a predicate that resolved the ambiguity by guessing would guess wrong in the direction that deletes live code.

    WRITTEN AS A LITERAL SEARCH AND A BACKWARD WALK, not as one regex, and the difference is 19 seconds against 1. The obvious spelling, `[\w.\-/]*[\w-]\.py`, starts a match attempt at EVERY character of every file, and this corpus holds 23 MiB of generated site search indexes. `str.find` is a memory scan and the backward walk runs once per real occurrence. Measured on the whole
    tree: 19.3s
    for the regex against 1.0s for this, and a control pins the two spellings to
    the same answer on every file so the speed-up cannot quietly narrow the route.
    """
    out: set[str] = set()
    hit = text.find(".py")
    while hit != -1:
        end = hit + 3
        # `.pyc`, `.pyi` and `.python` are not this file's subject.
        if end >= len(text) or not (text[end].isalnum() or text[end] == "_"):
            start = hit
            while start > 0 and (text[start - 1].isalnum() or text[start - 1] in "._-/"):
                start -= 1
            token = text[start:end]
            base = os.path.basename(token)
            for cand in index.get(base, ()):
                if token in (base, cand) or cand.endswith("/" + token.lstrip("./")):
                    out.add(cand)
        hit = text.find(".py", hit + 3)
    return out


def import_targets(source: str, importer: str, pyset: frozenset[str]) -> set[str]:
    """Corpus paths the imports in `source` resolve to.

    Both `import a.b` and `from a.b import c` are followed, and the `c` of the second is tried as a module too, because `from rediacc_ci.quality import dead_python` names a FILE while `from x import y` naming a symbol resolves to nothing and costs one dictionary lookup.
    """
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return set()
    mods: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                parts = importer.split("/")[: -node.level]
                base = ".".join(parts) + ("." + base if base else "")
            if base:
                mods.append(base)
            mods.extend((base + "." if base else "") + alias.name for alias in node.names)
    out: set[str] = set()
    here = os.path.dirname(importer)
    for mod in mods:
        rel = mod.replace(".", "/")
        for prefix in [*IMPORT_ROOTS, here]:
            stem = (prefix + "/" if prefix else "") + rel
            for cand in (stem + ".py", stem + "/__init__.py"):
                if cand in pyset:
                    out.add(cand)
    return out


def glob_discovered(paths: list[str], root: pathlib.Path, roots: dict | None = None) -> set[str]:
    out: set[str] = set()
    for groot, (prefixes, _reason) in (GLOB_ROOTS if roots is None else roots).items():
        if not (root / groot).is_dir():
            raise RefusalError(
                "declared glob root %s does not exist; the declaration is stale and the "
                "files it vouched for would now be reported dead" % groot
            )
        for rel in paths:
            if rel.startswith(groot) and os.path.basename(rel).startswith(prefixes):
                out.add(rel)
    return out


def scan(
    root: pathlib.Path,
    *,
    glob_roots: dict | None = None,
    manual: dict[str, str] | None = None,
) -> Report:
    glob_roots = GLOB_ROOTS if glob_roots is None else glob_roots
    manual = MANUAL_ENTRY_POINTS if manual is None else manual
    files = tracked_files(root)
    corpus = [f for f in files if f.endswith(".py")]
    if not corpus:
        raise RefusalError(
            "found ZERO Python files under %s; the layout changed and this gate is "
            "asserting nothing" % root
        )
    pyset = frozenset(corpus)
    index = suffix_index(corpus)

    referrers = [f for f in files if not is_prose(f) and not f.endswith(".py")]
    if not referrers:
        raise RefusalError(
            "found ZERO non-prose, non-Python files to read references out of; every "
            "registration route is empty and every gate entry point would read as dead"
        )

    # READ AS BYTES AND FILTER BEFORE DECODING. The referrer corpus is 93 MiB, two thirds of it generated site search indexes and PNGs that cannot name a Python file; decoding all of it costs 3.4s against 1.1s for this. A file
    # with no `.py` byte sequence in it contributes nothing to any route, so
    # skipping it changes no verdict, which a control pins.
    texts: dict[str, str] = {}
    for rel in referrers + corpus:
        try:
            raw = (root / rel).read_bytes()
        except OSError:
            continue
        if rel not in pyset and b".py" not in raw:
            continue
        texts[rel] = raw.decode("utf-8", errors="ignore")

    routes: dict[str, str] = {}

    def admit(rel: str, route: str) -> None:
        if rel not in routes:
            routes[rel] = route

    # -- wired ---------------------------------------------------------------
    for name in WIRING_FILES:
        if not (root / name).is_file():
            raise RefusalError(
                "wiring file %s does not exist; a registration route that silently "
                "empties turns registered gates into findings" % name
            )
    wiring = [f for f in referrers if f in WIRING_FILES or f.startswith(WIRING_DIRS)]
    for rel in wiring:
        for hit in mentioned_paths(texts.get(rel, ""), index):
            admit(hit, "wired")
    if "wired" not in set(routes.values()):
        raise RefusalError(
            "ZERO Python files are named by any of the %d wiring file(s); the "
            "registration route resolved nothing, so its green would be an artefact" % len(wiring)
        )

    # -- pytest --------------------------------------------------------------
    testpaths, python_files = pytest_config(root)
    collected = collected_by_pytest(corpus, testpaths, python_files)
    if not collected:
        raise RefusalError(
            "pytest would collect ZERO of the %d Python files under %r; the collection "
            "route resolved nothing" % (len(corpus), testpaths)
        )
    for rel in sorted(collected):
        admit(rel, "pytest")

    # -- shadow --------------------------------------------------------------
    admitted, expired, records = shadow_admissions(root, pyset)
    for rel in sorted(admitted):
        admit(rel, "shadow")

    # -- glob ----------------------------------------------------------------
    for rel in sorted(glob_discovered(corpus, root, glob_roots)):
        admit(rel, "glob")

    # -- closure -------------------------------------------------------------
    #
    # ROUTES ARE ATTRIBUTED IN PRIORITY ORDER, and the order is not cosmetic: the shape line is what a reader uses to notice a route quietly carrying the whole tree, so a file that is BOTH imported and mentioned must be counted once, under the stronger claim. Imports are therefore exhausted from the current frontier before any mention is admitted, and the two alternate to a fixed
    # point.
    imports = {rel: import_targets(texts.get(rel, ""), rel, pyset) for rel in corpus}
    mentions = {rel: mentioned_paths(texts.get(rel, ""), index) for rel in texts}

    # A GATE'S OWN EXEMPTION TABLE IS NOT A REFERENCE, and this cost a red the first time the entry point was driven. `MANUAL_ENTRY_POINTS` spells each exempt path in full, this module is itself reached, so every exempt file picked up a `mentioned` route from the very table that exempts it and was then reported as a STALE exemption. Suppressing the self-reference is what keeps the
    # two-direction check on the table honest.
    self_rel = os.path.relpath(os.path.abspath(__file__), root)
    if not self_rel.startswith("..") and self_rel in mentions:
        mentions[self_rel] = mentions[self_rel] - set(manual)

    def close_imports(frontier: list[str]) -> None:
        while frontier:
            rel = frontier.pop()
            for hit in imports.get(rel, ()):
                if hit not in routes:
                    routes[hit] = "imported"
                    frontier.append(hit)

    close_imports(list(routes))
    while True:
        # Every non-Python referrer is a live source of mentions; a Python file is one only once something reaches it, which is what stops two dead modules from vouching for each other.
        added: list[str] = []
        for rel in referrers + list(routes):
            for hit in mentions.get(rel, ()):
                if hit not in routes:
                    routes[hit] = "mentioned"
                    added.append(hit)
        if not added:
            break
        close_imports(added)

    # -- exempt by name, checked in both directions ---------------------------
    findings = []
    manual_live: dict[str, str] = {}
    for name, reason in sorted(manual.items()):
        if name not in pyset:
            findings.append(
                {
                    "file": name,
                    "why": "exempt BY NAME in MANUAL_ENTRY_POINTS, but there is no such file "
                    "in the tree, so the exemption vouches for nothing",
                    "fix": "delete the %r entry from "
                    "rediacc_ci.quality.dead_python.MANUAL_ENTRY_POINTS" % name,
                }
            )
        elif name in routes:
            findings.append(
                {
                    "file": name,
                    "why": "exempt BY NAME in MANUAL_ENTRY_POINTS, but it now has a real "
                    "route (%s), so the exemption is no longer true" % routes[name],
                    "fix": "delete the %r entry from "
                    "rediacc_ci.quality.dead_python.MANUAL_ENTRY_POINTS; the file is reached "
                    "on its own now" % name,
                }
            )
        else:
            routes[name] = "manual"
            manual_live[name] = reason

    for rel in corpus:
        if rel in routes:
            continue
        why = (
            "no execution route reaches it: not wired, not collected by pytest, not "
            "imported, not named by anything that runs"
        )
        fix = (
            "delete %s -- or give it a route: register it in package.json plus the "
            "manifest plus a workflow step, put it under a pytest testpath, import it "
            "from something that runs, or declare its discovery glob in "
            "rediacc_ci.quality.dead_python.GLOB_ROOTS with the site that globs it" % rel
        )
        if rel in expired:
            why = (
                "its shadow admission EXPIRED: %s, and nothing else runs it, so the "
                "port is a file the cutover left behind" % expired[rel]
            )
            fix = (
                "register %s the way its twin was registered (package.json, the "
                "manifest and a workflow step), or delete it" % rel
            )
        findings.append({"file": rel, "why": why, "fix": fix})

    return Report(
        routes=routes,
        findings=findings,
        corpus=corpus,
        referrers=len(referrers),
        expired=expired,
        shadow_records=records,
        manual=manual_live,
        glob_roots={
            groot: sum(1 for r in routes if routes[r] == "glob" and r.startswith(groot))
            for groot in glob_roots
        },
    )


# -------------------------------------------------------------------------- controls --------------------------------------------------------------------------

_FIXTURE_PYPROJECT = """
[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = ["test_*.py"]
"""

# The regex this module's mention scanner replaced. Kept HERE, in the controls, because the speed-up is only safe while the two spellings agree, and a comment claiming they agree is not a control.
_REFERENCE_TOKEN = re.compile(r"[\w.\-/]*[\w\-]\.py")


def _reference_mentions(text: str, index: dict[str, list[str]]) -> set[str]:
    out: set[str] = set()
    for token in set(_REFERENCE_TOKEN.findall(text)):
        base = os.path.basename(token)
        for cand in index.get(base, ()):
            if token in (base, cand) or cand.endswith("/" + token.lstrip("./")):
                out.add(cand)
    return out


def _write(root: pathlib.Path, rel: str, body: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def _fixture(tmp: pathlib.Path, extra: dict[str, str] | None = None) -> pathlib.Path:
    """A minimal tree with one of every required input, and nothing dead in it.

    THE CLEAN FIXTURE MUST BE GREEN FIRST. A control that only ever plants is a control that cannot tell a working detector from one that flags everything, and this gate's false positives cost deletions of live code.
    """
    root = tmp
    _write(root, "pyproject.toml", _FIXTURE_PYPROJECT)
    _write(root, "package.json", '{"scripts": {"check:x": ".ci/scripts/quality/check_base.py"}}')
    _write(root, "scripts/ci-runner/manifest.ts", "export const GATES = [];\n")
    _write(root, "scripts/ci-runner/gates.lock.json", "{}\n")
    _write(root, ".claude/settings.json", "{}\n")
    _write(root, ".github/workflows/ci.yml", "on: push\n")
    _write(root, ".ci/scripts/quality/check_base.py", "VALUE = 1\n")
    _write(root, "tests/test_base.py", "def test_ok():\n    pass\n")
    for rel, body in (extra or {}).items():
        _write(root, rel, body)
    return root


def _findings(root: pathlib.Path, **kw) -> list[str]:
    kw.setdefault("glob_roots", {})
    kw.setdefault("manual", {})
    return sorted(f["file"] for f in scan(root, **kw).findings)


def _refuses(root: pathlib.Path, **kw) -> bool:
    kw.setdefault("glob_roots", {})
    kw.setdefault("manual", {})
    try:
        scan(root, **kw)
    except RefusalError:
        return True
    return False


def selftest(verbose: bool = False) -> int:
    c = Controls("check-dead-python", floor=26, verbose=verbose)
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="dead-python-selftest-"))
    try:
        # -- the clean fixture, and the orphan it does not contain -----------
        base = _fixture(tmp / "clean")
        c.check("clean fixture is green", _findings(base), [])
        report = scan(base, glob_roots={}, manual={})
        c.check(
            "the wired entry point is attributed to `wired`",
            report.routes.get(".ci/scripts/quality/check_base.py"),
            "wired",
        )
        c.check(
            "the collected test is attributed to `pytest`",
            report.routes.get("tests/test_base.py"),
            "pytest",
        )

        orphan = {".ci/scripts/quality/check_orphan.py": "VALUE = 2\n"}
        root = _fixture(tmp / "orphan", orphan)
        c.check(
            "an unreached file IS reported",
            _findings(root),
            [".ci/scripts/quality/check_orphan.py"],
        )

        # -- each route suppresses that exact finding ------------------------
        root = _fixture(tmp / "wired", orphan)
        _write(
            root,
            "package.json",
            plant(
                (tmp / "clean" / "package.json").read_text(),
                '"check:x"',
                '"check:y": ".ci/scripts/quality/check_orphan.py", "check:x"',
            ),
        )
        c.check("route wired: naming it in package.json clears the finding", _findings(root), [])

        root = _fixture(tmp / "pytest", {"tests/test_orphan.py": "def test_x():\n    pass\n"})
        c.check("route pytest: a collected test is not dead", _findings(root), [])

        root = _fixture(tmp / "imported", orphan)
        _write(
            root,
            ".ci/scripts/quality/check_base.py",
            "import sys\nsys.path.insert(0, '.')\nfrom check_orphan import VALUE\n",
        )
        c.check("route imported: an import from a wired file clears it", _findings(root), [])

        root = _fixture(tmp / "mentioned", orphan)
        _write(root, "run.sh", "python3 .ci/scripts/quality/check_orphan.py\n")
        c.check("route mentioned: a shell caller clears it", _findings(root), [])

        root = _fixture(tmp / "relative", orphan)
        _write(root, "run.sh", "python3 quality/check_orphan.py\n")
        c.check("route mentioned: a path SUFFIX clears it too", _findings(root), [])

        # -- prose is not a route --------------------------------------------
        root = _fixture(tmp / "prose", orphan)
        _write(root, "agent/PLAN-x.md", "we will run .ci/scripts/quality/check_orphan.py\n")
        _write(root, "docs/x.md", "see .ci/scripts/quality/check_orphan.py\n")
        _write(root, "notes.txt", ".ci/scripts/quality/check_orphan.py\n")
        c.check(
            "prose does NOT admit: a plan, a doc and a .txt name it and it is still dead",
            _findings(root),
            [".ci/scripts/quality/check_orphan.py"],
        )

        # -- a mention inside a DEAD python file does not vouch --------------
        root = _fixture(tmp / "mutual", orphan)
        _write(
            root,
            ".ci/scripts/quality/check_other.py",
            "# runs .ci/scripts/quality/check_orphan.py\n",
        )
        c.check(
            "two dead files naming each other are both still dead",
            _findings(root),
            [".ci/scripts/quality/check_orphan.py", ".ci/scripts/quality/check_other.py"],
        )

        # -- .pyc and friends are not mentions --------------------------------
        root = _fixture(tmp / "pyc", orphan)
        _write(root, "run.sh", "rm .ci/scripts/quality/check_orphan.pyc\n")
        c.check(
            "a .pyc mention does not admit the .py",
            _findings(root),
            [".ci/scripts/quality/check_orphan.py"],
        )

        # -- the shadow route, and its expiry ---------------------------------
        ledger = json.dumps(
            {
                "verdict": "EQUIVALENT",
                "old": {"cmd": "bash .ci/scripts/quality/check-orphan.sh"},
                "new": {"cmd": "python3 .ci/scripts/quality/check_orphan.py"},
            }
        )
        root = _fixture(tmp / "shadow", orphan)
        _write(root, ".ci/shadow/w7p2-orphan.observations.jsonl", ledger + "\n")
        _write(root, ".ci/scripts/quality/check-orphan.sh", "#!/bin/bash\ntrue\n")
        c.check(
            "route shadow: an EQUIVALENT port whose twin lives is not dead", _findings(root), []
        )
        c.check(
            "and it is attributed to `shadow`, not to the ledger's text",
            scan(root, glob_roots={}, manual={}).routes[".ci/scripts/quality/check_orphan.py"],
            "shadow",
        )

        # The module-name form a workflow flip uses: `python3 -m rediacc_ci.<pkg>.<mod>` names no .py path, so the route must read the module.
        modroot = _fixture(
            tmp / "shadow-module", {".ci/rediacc_ci/quality/orphan_mod.py": "X = 1\n"}
        )
        _write(
            modroot,
            ".ci/shadow/w7p4b-orphan-mod.observations.jsonl",
            json.dumps(
                {
                    "verdict": "EQUIVALENT",
                    "old": {"cmd": "bash .ci/scripts/quality/check-orphan.sh"},
                    "new": {"cmd": "PYTHONPATH=.ci python3 -m rediacc_ci.quality.orphan_mod"},
                }
            )
            + "\n",
        )
        _write(modroot, ".ci/scripts/quality/check-orphan.sh", "#!/bin/bash\ntrue\n")
        c.check(
            "route shadow: a port named by `-m rediacc_ci.<mod>` in the ledger is not dead",
            _findings(modroot),
            [],
        )

        (root / ".ci/scripts/quality/check-orphan.sh").unlink()
        expired = scan(root, glob_roots={}, manual={}).findings
        c.check(
            "EXPIRY: deleting the twin makes the port a finding",
            [f["file"] for f in expired],
            [".ci/scripts/quality/check_orphan.py"],
        )
        c.truthy(
            "and the finding says the admission EXPIRED rather than 'no route'",
            "EXPIRED" in expired[0]["why"],
        )

        root = _fixture(tmp / "shadow-diff", orphan)
        _write(
            root,
            ".ci/shadow/w7p2-orphan.observations.jsonl",
            plant(ledger, '"EQUIVALENT"', '"DIVERGENT"') + "\n",
        )
        _write(root, ".ci/scripts/quality/check-orphan.sh", "#!/bin/bash\ntrue\n")
        c.check(
            "a DIVERGENT record admits nothing",
            _findings(root),
            [".ci/scripts/quality/check_orphan.py"],
        )

        # -- the glob route ----------------------------------------------------
        root = _fixture(tmp / "glob", {"g/block_a.py": "X = 1\n", "g/other.py": "X = 1\n"})
        groots = {"g/": (("block_",), "a reason")}
        c.check(
            "route glob: the prefixed file is admitted, the sibling is not",
            sorted(f["file"] for f in scan(root, glob_roots=groots, manual={}).findings),
            ["g/other.py"],
        )

        root = _fixture(tmp / "glob-gone", orphan)
        c.truthy(
            "a declared glob root that does not exist is a REFUSAL",
            _refuses(root, glob_roots={"nope/": (("block_",), "a reason")}),
        )

        # -- exempt by name, in both directions --------------------------------
        root = _fixture(tmp / "manual", orphan)
        man = {".ci/scripts/quality/check_orphan.py": "BLOCKER: a reason long enough to be one"}
        c.check(
            "a named exemption clears the finding",
            sorted(f["file"] for f in scan(root, glob_roots={}, manual=man).findings),
            [],
        )
        c.check(
            "and the reason is reported, not swallowed",
            list(scan(root, glob_roots={}, manual=man).manual),
            list(man),
        )

        stale = scan(base, glob_roots={}, manual=man).findings
        c.check(
            "a named exemption for a file that does not exist is a finding",
            [f["file"] for f in stale],
            [".ci/scripts/quality/check_orphan.py"],
        )
        c.truthy(
            "and it says the exemption vouches for nothing",
            "vouches for nothing" in stale[0]["why"],
        )

        root = _fixture(tmp / "manual-live", orphan)
        _write(root, "run.sh", "python3 .ci/scripts/quality/check_orphan.py\n")
        stale = scan(root, glob_roots={}, manual=man).findings
        c.check(
            "a named exemption for a file that gained a route is a finding",
            [f["file"] for f in stale],
            [".ci/scripts/quality/check_orphan.py"],
        )
        c.truthy("and it names the route it gained", "mentioned" in stale[0]["why"])

        # -- the refusals ------------------------------------------------------
        empty = tmp / "empty"
        empty.mkdir()
        _write(empty, "README.md", "nothing here\n")
        c.truthy("zero Python files is a REFUSAL, not a pass", _refuses(empty))

        root = _fixture(tmp / "no-pyproject", orphan)
        (root / "pyproject.toml").unlink()
        c.truthy("a missing pyproject.toml is a REFUSAL", _refuses(root))

        root = _fixture(tmp / "no-wiring", orphan)
        (root / "package.json").unlink()
        c.truthy("a missing wiring file is a REFUSAL", _refuses(root))

        root = _fixture(tmp / "wiring-names-nothing", orphan)
        _write(root, "package.json", '{"scripts": {"check:x": "true"}}')
        c.truthy("wiring that names no Python file at all is a REFUSAL", _refuses(root))

        root = _fixture(tmp / "collects-nothing", orphan)
        _write(
            root,
            "pyproject.toml",
            plant(_FIXTURE_PYPROJECT, 'testpaths = ["tests"]', 'testpaths = ["nowhere"]'),
        )
        c.truthy("a testpaths that collects nothing is a REFUSAL", _refuses(root))

        root = _fixture(tmp / "bad-ledger", orphan)
        _write(root, ".ci/shadow/broken.observations.jsonl", "{not json\n")
        c.truthy("a shadow ledger that will not parse is a REFUSAL", _refuses(root))

        # -- the fast scanner equals the spelling it replaced --------------------
        index = suffix_index(
            [".ci/scripts/quality/check_orphan.py", "a/b/worklist.py", "c/worklist.py"]
        )
        for probe in (
            "python3 .ci/scripts/quality/check_orphan.py --json",
            "run quality/check_orphan.py",
            'GATE=".ci/scripts/quality/check_orphan.py"',
            "stop/worklist.py --path",
            "no python here at all",
        ):
            c.check(
                "fast scanner == reference regex on %r" % probe[:32],
                mentioned_paths(probe, index),
                _reference_mentions(probe, index),
            )

        # THE ONE PLACE THE TWO SPELLINGS DELIBERATELY DISAGREE, asserted rather than glossed. The regex admits `check_orphan.py` out of
        # `check_orphan.pyc` because `[\w-]\.py` does not care what follows;
        # the literal scanner requires a non-word character after `.py`. The narrower answer is the right one and this control pins the direction, so a future "simplification" back to the regex has to argue with it.
        divergent = "rm check_orphan.pyc and worklist.python"
        c.check("the literal scanner refuses `.pyc`", mentioned_paths(divergent, index), set())
        c.check(
            "and the regex it replaced did NOT, which is why the equality above is "
            "asserted probe by probe",
            _reference_mentions(divergent, index),
            {".ci/scripts/quality/check_orphan.py", "a/b/worklist.py", "c/worklist.py"},
        )

        # THE DOCSTRING'S REFUSAL COUNT, AGAINST THE CODE. See the paragraph it checks.
        src = pathlib.Path(__file__).read_text(encoding="utf-8")
        stated = int(re.search(r"There are (\d+) refusals", src).group(1))
        raises = sum(
            1
            for n in ast.walk(ast.parse(src))
            if isinstance(n, ast.Raise)
            and isinstance(n.exc, ast.Call)
            and isinstance(n.exc.func, ast.Name)
            and n.exc.func.id == "RefusalError"
        )
        c.check("the docstring's refusal count matches the code", stated, raises)

        # -- the real constants are not decoration ------------------------------- THROUGH THE SEAM, not `parents[3]`: `rediacc_ci.paths` exists because a depth constant resolves to the WRONG tree in silence when a file moves.
        here = paths.repo_root()
        for groot in GLOB_ROOTS:
            c.truthy(
                "declared glob root %s exists in the real tree" % groot, (here / groot).is_dir()
            )
        for name in MANUAL_ENTRY_POINTS:
            c.truthy("exempt-by-name %s exists in the real tree" % name, (here / name).is_file())
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    return 0 if c.report() else 1


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    verbose = "--verbose" in argv

    # CONTROLS FIRST, ALWAYS, not only under --selftest: a gate whose controls run only when asked is a gate whose controls do not run in CI.
    rc = selftest(verbose)
    if rc != 0:
        print(
            "✗ instrument control failed; every verdict below would be meaningless", file=sys.stderr
        )
        return rc
    if "--selftest" in argv:
        return 0

    root = paths.repo_root()
    try:
        report = scan(root)
    except RefusalError as exc:
        log.error(
            "the gate cannot see its subject: %s\n"
            "  A green here would mean nothing, so this is a failure and not a note." % exc
        )
        return 1

    # PRINTED EVERY RUN, never only on failure. A suppression a reader cannot see is how a gate stops meaning what its name says.
    for name, reason in sorted(report.manual.items()):
        log.warn("EXEMPT BY NAME  %s\n      %s" % (name, reason))

    if "--json" in argv:
        print(json.dumps({"findings": report.findings, "routes": report.by_route()}, indent=2))
        return 1 if report.findings else 0

    if report.findings:
        log.error("%d dead Python file(s):" % len(report.findings))
        for f in report.findings:
            log.error("  DEAD  %s\n        %s\n        FIX: %s" % (f["file"], f["why"], f["fix"]))
            if os.environ.get("CI") == "true":
                print("::error file=%s,line=1::%s" % (f["file"], f["why"]))
        return 1

    routes = report.by_route()
    log.info(
        "dead Python: %d file(s) scanned, every one reached -- %s; read out of "
        "%d non-prose referrer file(s) and %d shadow record(s); %d exempt by name"
        % (
            len(report.corpus),
            ", ".join("%d %s" % (routes[k], k) for k in sorted(routes)),
            report.referrers,
            report.shadow_records,
            len(report.manual),
        )
    )
    return 0
