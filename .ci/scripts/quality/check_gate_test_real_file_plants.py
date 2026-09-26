#!/usr/bin/env python3
"""check:ci-gate-test-real-file-plants -- a test must never CLOBBER a REAL tracked file it also reads, even inside a try/finally restore.

WHY THIS EXISTS. `test_gate_worklist_env_registry.py` had three such plants (two into `.ci/policy/worklist-env-registry.json`, one into `.claude/hooks/stop/worklist-cases/21-cadence.sh`): read the real file's bytes, mutate and write them, run the gate under test, restore from the in-memory original in a `finally`. A hard kill landing in the write-to-restore window leaves the
tracked file genuinely corrupted with no backup -- and it happened
for real, twice in one session, from two unrelated causes (a `check:ci-pytest`
suite timeout, then a concurrent pytest invocation from a second live session). The fix there was a test-only env-var seam (`WORKLIST_REGISTRY_OVERRIDE_FILE`, `WORKLIST_SOURCE_OVERRIDE_FILE`) that redirects the gate under test onto a tmp copy instead. This gate exists so the NEXT test author who reaches for `TARGET.write_text(...); finally: TARGET.write_bytes(original)` is caught
before they write it, not after a third real corruption.

THE PATTERN, stated as a shape rather than a location. A name that resolves to a path under the repo root is a REAL-PATH name. If that name is the target of a `.write_text(`, `.write_bytes(` or `.unlink(` call, the test mutates the real tree -- regardless of whether a `finally` restores it, because the restore only helps a run that finishes.

FIVE WAYS THIS SCAN USED TO MISS A LIVE HAZARD, all five found on 2026-09-15 by running the detector against the corpus it was never pointed at:

  1. `SCAN_DIR` was `.ci/rediacc_ci/tests/gates` alone, so the 281 test modules
     sitting one level up in `.ci/rediacc_ci/tests/` were never read.
     `test_quality_env_manifest.py`'s `planted()` context manager -- copy the
     real `.ci/config/env-manifest.json`, mutate it, write it back, restore in
     a `finally`, the exact T-12 shape -- lived in that unscanned level.
  2. Real-path names were collected from MODULE-LEVEL assignments only. This
     plant's target is a function LOCAL (`live = root / em.MANIFEST_REL`), so
     the deliberate module-level narrowing was what hid it.
  3. `REAL_PATH_RE` only matched `paths.from_root(...)` or `paths.repo_root()/`
     on the assignment's own right-hand side, so a path derived INDIRECTLY
     through a variable (`root = paths.repo_root()` on one line, `live = root /
     ...` on the next) matched nothing.
  4. Blind spot 3 applies at module level too, and it had already cost this
     gate its own headline exemption. `test_gate_docs_gen.py` writes
     `scripts/data/doc-registry.md` via `ROOT = paths.repo_root()` then
     `TARGET = ROOT / "scripts" / "data" / "doc-registry.md"`. It was in the
     ALLOWLIST below, printed every run as a known debt -- and it had NEVER
     been detected, because `ROOT / "scripts"` is not `paths.repo_root() /`.
     The exemption was decorative. That is why ALLOWLIST liveness is now
     enforced (see `main`): an entry that names no live finding FAILS.
  5. The mutation scan only recognised an ATTRIBUTE call on the real name
     (`X.write_text(...)`), so a plant that WRITES BY COPYING -- `shutil.copy2
     (mutated, X)`, where `X` is a destination ARGUMENT rather than the
     receiver -- was invisible even though `reads_existing()` already checked
     the same `COPY_FUNCS` for a SOURCE argument to spot a backup-then-restore.
     Found 2026-09-15 while sweeping this gate's own pattern-matching for the
     class it was just rewritten to catch; no live instance in the corpus, but
     an untested blind spot in a detector whose whole job is finding blind
     spots does not get to wait for one.

CLOBBER versus STRAY, the distinction that keeps this gate honest in both directions. Two different things write inside the repo tree:

  - CLOBBER: the test reads or copies the target's EXISTING bytes and then
    overwrites or deletes them. That file was in the tree before the test and
    is owed a restore, so a kill mid-window destroys real content with no
    backup. This is the class that corrupted a tracked file twice, and it is
    what this gate FAILS on.
  - STRAY: the test creates a file at a path it never read, runs, and removes
    it. A kill leaves an UNTRACKED stray that `git status` shows and nobody is
    owed a restore for. Several gate tests do this deliberately and correctly,
    because their corpus is `git ls-files` and a probe outside the tree would
    be invisible -- the control would silently stop firing, which is the very
    vacuity a plant-based control exists to rule out.

    A stray is reported with its count and its files every run, never silently
    dropped, and it is NOT a pass-by-omission: a stray whose path statically
    resolves to a file `git ls-files` currently tracks is reclassified as a
    CLOBBER, so renaming a probe onto a tracked path cannot sneak through on
    the "it never reads it" branch.

WHAT THIS STILL DOES NOT CATCH, said out loud. A path built from a sandboxed copy (`shutil.copy2(REAL, tmp_copy)`, `tmp_path / "x"`, `harness.temp_dir()`) is the safe pattern and is skipped by construction -- correct, that is the pattern this gate wants MORE of. Dataflow tracking is same-function and same-name only: a real path handed to a helper as an ARGUMENT, or stashed on an
object attribute, is not followed. That bound is deliberate; a full dataflow pass would buy little here and would be unreadable.

ALLOWLIST: two entries, both live, both proven live on every run. It held three. `test_gate_hook_cross_os.py` came out, and the reason is the point of the STRAY
class above rather than a relaxation: that entry's whole argument was "the target
is verified NOT tracked by git", asserted once by a human in 2026-09-14 prose. The classifier now asks `git ls-files` that question on every run, so the entry would name no finding and fail the liveness check. A machine-checked claim replaced a hand-checked one; if the probe is ever moved onto a tracked path it becomes a hazard again by itself, with nobody having to remember.

---- gate ----
step: Gate-test real-file plants
needs: none
lane: quality-code
selftest: true
---- end gate ----
"""

from __future__ import annotations

import ast
import os
import pathlib
import re
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[3]

# Both test corpora that drive real gates. `.ci/rediacc_ci/tests` is recursive because the hazard this gate exists for was sitting one level above the only directory the original scan looked at. `.claude/rediacc_hooks/tests` is in scope for the same reason it would be if it were the one with the plant: nothing about the hazard is specific to a package, and a hook test can write
# `.claude/hooks/...` as easily as a gate test can write `.ci/policy/...`.
SCAN_DIRS = (
    ROOT / ".ci" / "rediacc_ci" / "tests",
    ROOT / ".claude" / "rediacc_hooks" / "tests",
)

# ANTI-VACUITY FLOOR. This gate reports success by finding NOTHING, so a scan that collapsed -- a moved directory, a broken glob, a rename of the tests package -- is indistinguishable from a clean tree: both print a tick. The floor makes the difference observable. 458 files present on 2026-09-15; the floor sits well below that rather than at it, because a floor equal to today's
# count turns every deleted test into a failure and teaches people to lower the floor.
MIN_SCANNED = 350

RED = "\033[0;31m"
GREEN = "\033[0;32m"
NC = "\033[0m"

# file -> BLOCKER reason. Printed every run, never silent, and LIVENESS-CHECKED: an entry that names no current finding fails the gate rather than sitting here looking like a tracked debt. That check exists because the entry this dict used to open with (`test_gate_docs_gen.py`) was decorative for its whole life -- the detector could not see the file it excused.
ALLOWLIST = {
    "test_gate_docs_gen.py": (
        "BLOCKER: TARGET (scripts/data/doc-registry.md) needs the same "
        "override-seam treatment as WORKLIST_REGISTRY_OVERRIDE_FILE, inside "
        "scripts/gen/gen-docs.ts (TypeScript, a separate change from the Python "
        "fixes). Tracked 2026-09-14; DETECTED for the first time 2026-09-15, "
        "when indirect `ROOT / ...` derivation was added -- until then this "
        "entry excused a finding the scan could not produce."
    ),
    "test_gate_generate_tag_inputs.py": (
        "BLOCKER: RESOLVER is a DELIBERATE, documented real-tree WRITER (its "
        "own docstring: 'THE WRITE IS THE POINT and there is no seam that "
        "avoids it' -- resolve-version.sh is invoked from the repo root, so "
        "moving the released version means moving that file). Not the "
        "accidental hazard this gate exists to catch: the restore is verified "
        "by digest AND mode afterward, and the module declares "
        "XDIST_GROUP = xdist_groups.REAL_TREE_GROUP specifically so it is "
        "serialised against every other real-tree test rather than racing one "
        "on a second xdist worker. That declaration replaced REAL_TREE_TWIN on "
        "2026-09-21, when the bash twin whose lock entry used to buy the "
        "serialisation was retired."
    ),
}

REAL_PATH_RE = re.compile(r"paths\.from_root\(|paths\.repo_root\(\)\s*/")
ROOT_CALL_RE = re.compile(r"^paths\.repo_root\(\)$|^paths\.from_root\(")
TMP_HINT_RE = re.compile(r"tmp|temp|sandbox|scratch", re.IGNORECASE)

# `.unlink` is here with the two writes because deleting a tracked file mid-test is the same corruption with a larger hole in it: there is not even a truncated file left to notice. `test_quality_env_manifest.py` deleted the real manifest outright in one case, which no write-only detector would have reported.
MUTATE_ATTRS = ("write_text", "write_bytes", "unlink")

# Evidence that the target EXISTED before the test touched it, i.e. that the test owes it a restore. `X.read_text()` / `X.read_bytes()` / `X.open()` / `X.stat()` as attribute calls, plus X as the SOURCE argument of a copy.
READ_ATTRS = ("read_text", "read_bytes", "open", "stat")
COPY_FUNCS = ("copy", "copy2", "copyfile", "move")


def _own_nodes(fn: ast.AST):
    """Every node inside `fn`, NOT descending into a nested function or lambda.

    Nested scopes are visited separately as their own `FunctionDef`, seeded from the module's names only. Keeping the walk inside one scope is what makes the local pass bounded and readable rather than a dataflow engine.

    PRE-ORDER, i.e. SOURCE order, and that is load-bearing rather than tidy. The first cut used a LIFO stack, which handed `local_real_paths` the statements
    backwards: `live = root / X` was classified before `root = paths.repo_root()`
    had bound `root`, so the seed never existed when it was needed and the control for the exact hazard this rewrite exists for went green.
    """
    for child in ast.iter_child_nodes(fn):
        yield child
        if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda):
            continue
        yield from _own_nodes(child)


def _targets(node: ast.Assign) -> list[str]:
    return [t.id for t in node.targets if isinstance(t, ast.Name)]


def _div_base(value: ast.expr) -> str | None:
    """For `X / "a" / "b"`, the leftmost Name `X`. None if the base is not a Name."""
    while isinstance(value, ast.BinOp) and isinstance(value.op, ast.Div):
        value = value.left
    return value.id if isinstance(value, ast.Name) else None


def _literal_parts(value: ast.expr) -> list[str] | None:
    """`X / "a" / "b"` -> ["a", "b"]. None if any part is not a string literal."""
    parts: list[str] = []
    while isinstance(value, ast.BinOp) and isinstance(value.op, ast.Div):
        right = value.right
        if not (isinstance(right, ast.Constant) and isinstance(right.value, str)):
            return None
        parts.insert(0, right.value)
        value = value.left
    return parts


def _from_root_parts(value: ast.expr) -> list[str] | None:
    """`paths.from_root("a", "b")` -> ["a", "b"]. None if it is not that call."""
    if not isinstance(value, ast.Call):
        return None
    func = value.func
    if not (isinstance(func, ast.Attribute) and func.attr == "from_root"):
        return None
    parts = []
    for arg in value.args:
        if not (isinstance(arg, ast.Constant) and isinstance(arg.value, str)):
            return None
        parts.append(arg.value)
    return parts


def _classify_assign(node: ast.Assign, roots: set[str], real: set[str]) -> bool:
    """Does this assignment bind a REAL-path name? Updates nothing; pure."""
    src = ast.unparse(node.value)
    if TMP_HINT_RE.search(src):
        return False
    if REAL_PATH_RE.search(src):
        return True
    base = _div_base(node.value)
    return base is not None and (base in roots or base in real)


def real_path_constants(tree: ast.Module) -> tuple[set[str], set[str], dict[str, str]]:
    """Module-level real-path names, root names, and any statically known rel path.

    `tree.body` only, deliberately NOT `ast.walk(tree)`: a local variable named `path` inside some unrelated function can be assigned from a real-path-shaped expression too, and that is not a "the subject's real path" CONSTANT -- it is scoping noise. Restricting to the module's own top-level statements is what makes a hit mean "this file declares a named constant for a real tracked
    path". Function locals are handled by `local_real_paths`, per function, which is a separate pass with its own narrower rules rather than a widening of this one.

    Returns (real names, root names, name -> repo-relative path where resolvable). A root name is one bound to a bare `paths.repo_root()` / `paths.from_root(...)`, which is not itself a file but is the base a later `/` derives one from.
    """
    real: set[str] = set()
    roots: set[str] = set()
    rels: dict[str, str] = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        # NOT wrapped in try/except. A defensive `continue` here would SILENTLY skip an assignment this gate might otherwise have caught mutating a real tracked file -- which is the exact vacuity hazard the gate exists to prevent, reproduced inside the gate. If `ast.unparse` ever fails, the right outcome is a loud crash, not a quiet pass.
        src = ast.unparse(node.value)
        if TMP_HINT_RE.search(src):
            continue
        names = _targets(node)
        if ROOT_CALL_RE.match(src):
            roots.update(names)
        if _classify_assign(node, roots, real):
            real.update(names)
            rel = _resolve_rel(node.value, rels, roots)
            for name in names:
                if rel is not None:
                    rels[name] = rel
        elif ROOT_CALL_RE.match(src):
            parts = _from_root_parts(node.value)
            for name in names:
                rels[name] = "/".join(parts) if parts else ""
    return real, roots, rels


def _resolve_rel(value: ast.expr, rels: dict[str, str], roots: set[str]) -> str | None:
    """The repo-relative path this expression names, when every part is a literal."""
    parts = _from_root_parts(value)
    if parts is not None:
        return "/".join(parts)
    tail = _literal_parts(value)
    base = _div_base(value)
    if tail is None or base is None or (base not in rels and base not in roots):
        return None
    head = rels.get(base, "")
    return "/".join([p for p in (head, *tail) if p])


def local_real_paths(fn: ast.AST, roots: set[str], real: set[str]) -> set[str]:
    """Real-path names bound inside ONE function, in statement order.

    The shape this exists for, and the one the gate missed for a week:

        root = paths.repo_root()        # binds a ROOT
        live = root / em.MANIFEST_REL   # binds a REAL path, indirectly
        live.write_text(...)            # plants into the real tree

    Seeded from the module's own names so a module-level `ROOT` works the same way, and it never leaves this function (see `_own_nodes`).
    """
    local_roots = set(roots)
    local_real = set(real)
    for node in _own_nodes(fn):
        if not isinstance(node, ast.Assign):
            continue
        src = ast.unparse(node.value)
        if TMP_HINT_RE.search(src):
            continue
        names = _targets(node)
        if ROOT_CALL_RE.match(src):
            local_roots.update(names)
        if _classify_assign(node, local_roots, local_real):
            local_real.update(names)
    return local_real


def mutations(scope: ast.AST, names: set[str], own_scope: bool) -> list[tuple[str, str, int]]:
    """[(name, attr, lineno)] for every real-path name mutated in this scope.

    TWO SHAPES, because `reads_existing()` already had to know about both to spot a restore, and this side had only learned one of them. `X.write_text(...)` is an ATTRIBUTE call on the real name. `shutil.copy2(mutated, X)` is a FUNCTION call where the real name is the DESTINATION argument, not the receiver -- a plant that copies a doctored file ONTO the real tracked path is
    invisible to an attribute-only scan. `COPY_FUNCS` (`reads_existing`'s source-argument check) is the same list here on the destination argument, `node.args[1]`.
    """
    walker = _own_nodes(scope) if own_scope else ast.walk(scope)
    hits = []
    for node in walker:
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr in MUTATE_ATTRS:
            recv = func.value
            if isinstance(recv, ast.Name) and recv.id in names:
                hits.append((recv.id, func.attr, node.lineno))
        elif isinstance(func, ast.Attribute) and func.attr in COPY_FUNCS and len(node.args) >= 2:
            dst = node.args[1]
            if isinstance(dst, ast.Name) and dst.id in names:
                hits.append((dst.id, func.attr, node.lineno))
    return hits


def reads_existing(scope: ast.AST, name: str, own_scope: bool) -> bool:
    """Does this scope read `name`'s pre-existing content, i.e. owe it a restore?"""
    walker = _own_nodes(scope) if own_scope else ast.walk(scope)
    for node in walker:
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if (
            isinstance(func, ast.Attribute)
            and func.attr in READ_ATTRS
            and isinstance(func.value, ast.Name)
            and func.value.id == name
        ):
            return True
        if isinstance(func, ast.Attribute) and func.attr in COPY_FUNCS and node.args:
            src = node.args[0]
            if isinstance(src, ast.Name) and src.id == name:
                return True
    return False


def tracked_files(root: pathlib.Path) -> set[str]:
    """Every path `git ls-files` reports, as repo-relative strings.

    An EMPTY result is a refusal upstream, not an empty set quietly meaning "nothing is tracked": see `main`.
    """
    proc = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z"],
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        return set()
    out = proc.stdout.decode("utf-8", "surrogateescape")
    return {p for p in out.split("\0") if p}


def scan(
    files: list[pathlib.Path], tracked: set[str] | None = None
) -> list[tuple[str, str, str, str]]:
    """[(name, real_name, attr, kind)] per file, kind in {clobber, tracked, stray}.

    `tracked` is the `git ls-files` set. When a real-path name resolves statically to a path in it, a mutation is a CLOBBER even with no read in sight -- that is the branch that stops a probe being renamed onto a tracked file.
    """
    tracked = tracked or set()
    findings: list[tuple[str, str, str, str]] = []
    for path in files:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError:
            continue
        real, roots, rels = real_path_constants(tree)
        hit = None
        if real:
            for name, attr, _line in mutations(tree, real, own_scope=False):
                kind = _kind(tree, name, rels.get(name), tracked, own_scope=False)
                hit = (path.name, name, attr, kind)
                break
        if hit is None:
            for node in ast.walk(tree):
                if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                    continue
                local = local_real_paths(node, roots, real)
                fresh = local - real
                if not fresh:
                    continue
                found = mutations(node, fresh, own_scope=True)
                if not found:
                    continue
                name, attr, _line = found[0]
                hit = (path.name, name, attr, _kind(node, name, None, tracked, own_scope=True))
                break
        if hit is not None:
            findings.append(hit)
    return findings


def _kind(scope: ast.AST, name: str, rel: str | None, tracked: set[str], own_scope: bool) -> str:
    if rel and rel in tracked:
        return "tracked"
    if reads_existing(scope, name, own_scope):
        return "clobber"
    return "stray"


def _fixture(d: pathlib.Path, name: str, body: str) -> pathlib.Path:
    path = d / name
    path.write_text(body, encoding="utf-8")
    return path


def _fail(message: str) -> None:
    print("%s✗ CONTROL FAILED%s: %s" % (RED, NC, message), file=sys.stderr)
    sys.exit(2)


def controls() -> None:
    """Both directions, on every shape the detector claims to see.

    Positive controls prove each of the four blind spots stays closed; negative controls prove the widening did not turn every probe-planting gate test into a finding, which is the failure mode a detector this eager falls into first.
    """
    with tempfile.TemporaryDirectory() as td:
        d = pathlib.Path(td)

        # 1. The original shape: a module constant, clobbered.
        hazard = _fixture(
            d,
            "test_gate_planted_hazard.py",
            "from rediacc_ci import paths\n"
            'TARGET = paths.from_root("scripts", "data", "doc-registry.md")\n'
            "def test_x():\n"
            "    original = TARGET.read_bytes()\n"
            "    TARGET.write_bytes(original)\n",
        )
        got = {f[0]: f for f in scan([hazard])}
        if "test_gate_planted_hazard.py" not in got:
            _fail("a planted real-file write was not caught")
        if got["test_gate_planted_hazard.py"][3] != "clobber":
            _fail("a read-then-write module constant was not classed as a clobber")

        # 2. Blind spot 2+3: a FUNCTION-LOCAL path derived INDIRECTLY through a local root. This is `test_quality_env_manifest.py`'s exact shape and the reason this gate was rewritten.
        local = _fixture(
            d,
            "test_local_indirect_hazard.py",
            "from rediacc_ci import paths\n"
            "def test_x():\n"
            "    root = paths.repo_root()\n"
            '    live = root / "somefile.json"\n'
            "    original = live.read_bytes()\n"
            '    live.write_bytes(b"mutated")\n'
            "    live.write_bytes(original)\n",
        )
        got = {f[0]: f for f in scan([local])}
        if "test_local_indirect_hazard.py" not in got:
            _fail("a function-local path derived from a local repo_root() was not caught")
        if got["test_local_indirect_hazard.py"][3] != "clobber":
            _fail("the function-local indirect hazard was not classed as a clobber")

        # 3. Blind spot 4: a MODULE constant derived indirectly through a module root. This is `test_gate_docs_gen.py`, which the previous detector allowlisted without ever being able to see it.
        indirect = _fixture(
            d,
            "test_module_indirect_hazard.py",
            "from rediacc_ci import paths\n"
            "ROOT = paths.repo_root()\n"
            'TARGET = ROOT / "scripts" / "data" / "doc-registry.md"\n'
            "def test_x():\n"
            "    original = TARGET.read_bytes()\n"
            "    TARGET.write_bytes(original)\n",
        )
        got = {f[0]: f for f in scan([indirect])}
        if "test_module_indirect_hazard.py" not in got:
            _fail("a module constant derived from `ROOT / ...` was not caught")

        # 4. Deletion is a mutation. A write-only detector reported nothing for the case that unlinked the real manifest.
        deleter = _fixture(
            d,
            "test_unlink_hazard.py",
            "from rediacc_ci import paths\n"
            "def test_x():\n"
            "    root = paths.repo_root()\n"
            '    live = root / "somefile.json"\n'
            "    keep = live.read_bytes()\n"
            "    live.unlink()\n"
            "    assert keep\n",
        )
        if not scan([deleter]):
            _fail("unlinking a real tracked path was not caught")

        # 5. NEGATIVE: the safe pattern. A real constant read, a tmp_path written.
        safe = _fixture(
            d,
            "test_gate_safe.py",
            "from rediacc_ci import paths\n"
            'TARGET = paths.from_root("scripts", "data", "doc-registry.md")\n'
            "def test_x(tmp_path):\n"
            "    original = TARGET.read_bytes()\n"
            '    mutated = tmp_path / "mutated.md"\n'
            "    mutated.write_bytes(original)\n",
        )
        if scan([safe]):
            _fail("a tmp_path-only write was misreported as a real plant")

        # 6. NEGATIVE: a fresh probe planted inside the tree and removed. Never read, so nothing pre-existing is destroyed -- reported as a stray, never as a failure. Several gate tests need this: their corpus is `git ls-files`, so a probe under tmp_path would be invisible and the control would silently stop firing.
        stray = _fixture(
            d,
            "test_fresh_probe.py",
            "import os\n"
            "from rediacc_ci import paths\n"
            "ROOT = paths.repo_root()\n"
            "def test_x():\n"
            '    probe = ROOT / (".ci/scripts/.probe.%d.py" % os.getpid())\n'
            '    probe.write_text("x", encoding="utf-8")\n'
            "    try:\n"
            "        pass\n"
            "    finally:\n"
            "        probe.unlink(missing_ok=True)\n",
        )
        got = {f[0]: f for f in scan([stray])}
        if "test_fresh_probe.py" not in got:
            _fail("a fresh in-tree probe was not seen at all; the stray class is not reported")
        if got["test_fresh_probe.py"][3] != "stray":
            _fail("a fresh in-tree probe was misclassified as a clobber")

        # 7. The stray branch is not a free pass: the same never-read shape on a path that IS tracked reclassifies as a clobber.
        named = _fixture(
            d,
            "test_tracked_probe.py",
            "from rediacc_ci import paths\n"
            'PROBE = paths.from_root(".claude", "rediacc_hooks", "__plant.py")\n'
            "def test_x():\n"
            '    PROBE.write_text("x", encoding="utf-8")\n'
            "    PROBE.unlink(missing_ok=True)\n",
        )
        got = {f[0]: f for f in scan([named])}
        if got["test_tracked_probe.py"][3] != "stray":
            _fail("an untracked named probe should be a stray when git does not track it")
        got = {f[0]: f for f in scan([named], {".claude/rediacc_hooks/__plant.py"})}
        if got["test_tracked_probe.py"][3] != "tracked":
            _fail("a never-read probe on a git-TRACKED path must reclassify as a clobber")

        # 8. A FIFTH shape: `shutil.copy2(mutated, X)` plants by COPYING a doctored file ONTO the real path, not by calling a write method on it. `X` is an argument, not a receiver, so the attribute-call scan above cannot see it -- `reads_existing()` already knew to check `COPY_FUNCS` for a
        #    SOURCE argument; this is the same functions checked as a DESTINATION.
        copied = _fixture(
            d,
            "test_copy_destination_hazard.py",
            "import shutil\n"
            "from rediacc_ci import paths\n"
            'TARGET = paths.from_root("scripts", "data", "doc-registry.md")\n'
            "def test_x(tmp_path):\n"
            "    original = TARGET.read_bytes()\n"
            '    mutated = tmp_path / "mutated.md"\n'
            '    mutated.write_bytes(b"mutated")\n'
            "    shutil.copy2(mutated, TARGET)\n"
            "    shutil.copy2(mutated, TARGET)\n",  # restore, same call shape
        )
        got = {f[0]: f for f in scan([copied])}
        if "test_copy_destination_hazard.py" not in got:
            _fail("a shutil.copy2(..., TARGET) plant was not caught")
        if got["test_copy_destination_hazard.py"][3] != "clobber":
            _fail("a copy-as-destination hazard was not classed as a clobber")

        # 9. NEGATIVE: copying INTO a fixture root, the pattern used throughout the real test corpus (`shutil.copy2(TWIN, root / rel)`), must stay silent -- the destination is not a tracked real-path name.
        copy_safe = _fixture(
            d,
            "test_copy_into_fixture.py",
            "import shutil\n"
            "from rediacc_ci import paths\n"
            'TARGET = paths.from_root("scripts", "data", "doc-registry.md")\n'
            "def test_x(tmp_path):\n"
            "    root = tmp_path\n"
            '    shutil.copy2(TARGET, root / "doc-registry.md")\n',
        )
        if scan([copy_safe]):
            _fail("copying a real file INTO a fixture root was misreported as a plant")


def main() -> int:
    controls()
    files: list[pathlib.Path] = []
    for scan_dir in SCAN_DIRS:
        if scan_dir.is_dir():
            files.extend(sorted(scan_dir.rglob("*.py")))
    scanned = len(files)
    if scanned < MIN_SCANNED:
        print(
            "%s✗%s VACUOUS: scanned %d file(s) across %s, below the floor of %d. This "
            "gate passes by finding nothing, so a corpus this small means the SCAN broke, "
            "not that the tree is clean. Refusing rather than printing a tick."
            % (
                RED,
                NC,
                scanned,
                ", ".join(os.path.relpath(d, ROOT) for d in SCAN_DIRS),
                MIN_SCANNED,
            ),
            file=sys.stderr,
        )
        return 1
    tracked = tracked_files(ROOT)
    if not tracked:
        print(
            "%s✗%s UNKNOWN: `git ls-files` returned nothing, so no finding can be "
            "classified as tracked or untracked. Unchecked is not clean; refusing." % (RED, NC),
            file=sys.stderr,
        )
        return 1

    findings = scan(files, tracked)
    hazards = [f for f in findings if f[3] != "stray"]
    strays = [f for f in findings if f[3] == "stray"]

    if strays:
        print(
            "in-tree probe writes, the STRAY class (a path never read, so a kill "
            "leaves an untracked file and destroys nothing) -- reported, not failed:"
        )
        for name, real_name, attr, _ in strays:
            print("  %s  %s.%s()" % (name, real_name, attr))

    print("exemptions, printed every run so the debt cannot be forgotten:")
    for f, reason in ALLOWLIST.items():
        print("  %s\n      %s" % (f, reason))

    hazard_names = {f[0] for f in hazards}
    dead = [f for f in ALLOWLIST if f not in hazard_names]
    if dead:
        for f in dead:
            print(
                "%s✗%s %s is ALLOWLISTED but produces no finding. Either the plant was "
                "fixed (delete the entry) or the detector stopped seeing it (fix the "
                "detector). An exemption nobody can trigger is not a tracked debt, it is "
                "a decoration -- this gate shipped one for a week." % (RED, NC, f),
                file=sys.stderr,
            )
        return 1

    unallowed = [f for f in hazards if f[0] not in ALLOWLIST]
    if unallowed:
        for name, real_name, attr, kind in unallowed:
            print(
                "%s✗%s %s calls %s.%s() on a REAL tracked path (%s) with no tmp-path "
                "override seam. A hard kill mid-test corrupts a tracked file with no "
                "backup. Add a test-only env-var seam to the module under test and point "
                "it at a tmp copy; see .ci/rediacc_ci/quality/worklist_env_registry.py's "
                "WORKLIST_REGISTRY_OVERRIDE_FILE and "
                ".ci/rediacc_ci/quality/env_manifest.py's ENV_MANIFEST_OVERRIDE_FILE for "
                "the pattern. Do not add it to the ALLOWLIST."
                % (RED, NC, name, real_name, attr, kind),
                file=sys.stderr,
            )
        print(
            "%d test file(s) mutate a real tracked file." % len(unallowed),
            file=sys.stderr,
        )
        return 1
    print(
        "%s✓%s no test file clobbers a real tracked file without a declared exemption "
        "(%d file(s) scanned, %d tracked path(s) known, %d exempted, %d stray)"
        % (GREEN, NC, scanned, len(tracked), len(ALLOWLIST), len(strays))
    )
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        controls()
        print("%s✓%s selftest" % (GREEN, NC))
        sys.exit(0)
    sys.exit(main())
