r"""check:ci-env-manifest -- every environment variable this repo reads or supplies, classified by WHO SUPPLIES THE VALUE and WHO MAY READ IT.

THE NUMBER IS NOT THE ACCEPTANCE, AND THAT IS THE WHOLE DESIGN. The plan box that asked for this file carried a union of 1,014 names; its own design annotation re-measured 745, then 721 over tracked files and 777 over everything on disk, and not one of the five component counts reproduced. The 56-name swing was entirely gitignored `.env` files, one of them a single developer's
`.env.pre-rename.bak`. A manifest whose size depends on whether a stray backup is present is not a manifest, so no count is written down anywhere in this module or in `.ci/config/env-manifest.json`. Every number in the output below is derived on the run that prints it.

THE CORPUS IS TRACKED FILES ONLY, for the same reason `paths.py` answers from a tracked path set: an untracked file is one machine's opinion, and a gate whose verdict changes when you `cp` something into the tree is not measuring the tree.

THE FIVE SOURCE READERS, and what each one is:

  env-file     `KEY=` in a tracked env file (`.env`, `.env.*`, `*.env`)
  workflow-key an ENV-SHAPED yaml mapping key in `.github/workflows/**` or any
               `action.yml`. Deliberately not just `env:` blocks: a job output,
               a composite input and a `secrets:` declaration all become
               environment values somewhere downstream, and reading only `env:`
               would omit every `RESULT_*` and the whole `.github/actions` input
               surface.
  process-env  `process.env.NAME` / `process.env["NAME"]` in JS/TS/Astro
  os-environ   `os.environ[...]`, `.get`, `.setdefault`, `.pop` and `os.getenv`
               in Python -- BOTH the literal form AND one level of module-level
               constant indirection, resolved with `ast`
  vault        the NAMES in `.ci/config/bws-secret-map.json`. Names only. No
               value of any kind is read, printed, or stored by this gate.

WHY THE `os-environ` READER PARSES INSTEAD OF GREPPING, measured 2026-09-09. A regex for `os.environ.get("LITERAL")` misses every read that goes through a module-level constant, and this repository has 55 of them -- `PROFILER_COVERAGE_*` (8), `LABEL_INVENTORY_*` (5), `PLAN_HK_*` (4), and, most pointedly, `REDIACC_CI_ROOT` itself, the ONE fixture-pointing seam `paths.py` exists to
declare. A manifest of environment seams that omitted the canonical environment seam would have been the funniest possible way to fail, and the regex form omits it because `paths.py:74` writes `os.environ.get(ROOT_ENV)`. So the reader walks
the AST, binds module-level `NAME = "literal"` assignments, and resolves them at
the call. The regex still runs and its result is UNIONED in: over-collecting a name costs one manifest line, under-collecting one is a hole.

BASH `${VAR}` IS EXCLUDED, as the box directs. Including it pushes the union past
3,000 and the additions are dominated by loop variables. THE PRICE IS REAL AND IS NOT HIDDEN: see the `RDC_BENCH` note in the manifest, a name three documents call deleted that two shell files still read.

WHAT THE GATE ASSERTS -- four set-arithmetic clauses over `sources` (derived above) and `shards` (the union of the manifest's eight lists):

  1. sources \ shards == {}      every name the tree uses is classified
  2. shards \ sources == tombstones
  3. the seven LIVE shards are pairwise disjoint, and none repeats a name
  4. tombstones & sources == {}  a dead name has not come back

Clause 2 is the one that keeps the manifest honest in the OTHER direction, and it is why tombstones are the eighth shard rather than a separate file. Read together
with clause 4 it says: every live-shard entry must still be a real read, so a
variable that goes away RED-LIGHTS its stale manifest line instead of sitting there looking like coverage. "Tombstones enforced" then falls out of the same arithmetic as "zero unclassified" -- there is no second mechanism to keep in sync.

ANTI-VACUITY, AND WHY IT IS NOT `n > 0`. A per-source count floor is the obvious guard against a reader that silently stops matching, and it is the wrong shape: a clause like `env_file_names > 0` becomes a false red the day the last `.env` example is deleted, which is a legitimate terminal state. Two clauses that are true in EVERY state replace it:

  * every reader is proven on its own FIXTURE, in both directions, in the
    selftest -- it must find a planted name and must not find one in prose. A
    reader that stops matching fails there regardless of what the tree holds.
  * every reader must SEE FILES. Zero candidate files for a reader is a REFUSAL
    naming that reader, because "there are no Python files in this repository"
    is not a pass, it is an instrument that has lost the tree.

and the run then PRINTS the per-source name counts and file counts, so a collapse from 253 to 3 is visible to a reader even while both clauses hold.

TOMBSTONE PROOF SITES. A file whose job is to name dead variables necessarily mentions them, and `packages/cli/src/__tests__/env-tombstones.test.ts` is exactly that file: left in the corpus it resurrects four names into `sources` and breaks clause 4 by existing. The suppression is per (path, NAME) pair, never per file, and it is liveness-checked in both directions -- the pair must
still be found by a reader at that path (a dangling entry fails), and the name must be in the tombstone shard (so the mechanism cannot be used to hide a live variable). Both are printed every run.

WHAT THIS GATE DOES NOT SEE, stated so that its green is not read as a claim it
cannot make. Bash `${VAR}`, as above. And a JS/TS `process.env[expr]` where
`expr` is not a literal: 19 such sites exist today, and every one that resolves to a constant resolves to a name already in the manifest (`REDIACC_TOKEN` via `SUBSCRIPTION_TOKEN_ENV`, `REDIACC_ALLOW_CONFIG_EDIT` via `OVERRIDE_VAR_CONFIG_EDIT`, the four `AGENT_ENV_VARS`), the rest being loop variables. The count is printed every run rather than asserted, because the honest assertion
-- "no unresolvable dynamic read" -- is false today and could only be made true with a baseline.
"""

from __future__ import annotations

import ast
import json
import os
import pathlib
import re
import shutil
import subprocess
import tempfile

from rediacc_ci import log, paths, runtmp
from rediacc_ci.controls import Controls, controls_first

MANIFEST_REL = ".ci/config/env-manifest.json"
VAULT_REL = ".ci/config/bws-secret-map.json"

#: Test-only. One file path that REPLACES `.ci/config/env-manifest.json` as the
#: thing every clause is compared against. The corpus side is untouched -- the
#: five readers still derive names from the real `git ls-files` tree, which is
#: the whole point of a plant test driving the live gate -- so only the
#: MANIFEST side becomes a tmp copy the caller mutated.
#:
#: This exists because `test_quality_env_manifest.py`'s `planted()` used to
#: copy the real manifest, write a mutated version OVER the tracked file, run
#: the gate, and restore in a `finally`. A hard kill inside that window leaves
#: `.ci/config/env-manifest.json` genuinely corrupted with no backup. That is
#: not hypothetical: the same shape destroyed
#: `.ci/policy/worklist-env-registry.json` twice in one session, once from a
#: suite timeout and once from a concurrent pytest run in a second worktree,
#: which is why `WORKLIST_REGISTRY_OVERRIDE_FILE` was added one file over. This
#: is that seam, for this gate.
MANIFEST_OVERRIDE = os.environ.get("ENV_MANIFEST_OVERRIDE_FILE", "")

LIVE_SHARDS = (
    "secret",
    "ci-runner",
    "gate-seam",
    "toolchain",
    "machine-local",
    "product-runtime",
    "harness",
)
TOMBSTONE_SHARD = "tombstone"
ALL_SHARDS = (*LIVE_SHARDS, TOMBSTONE_SHARD)

# A legal POSIX-ish environment name. Applied to every reader's output so a yaml key like `runs-on` or a JS property access on a non-name cannot enter.
NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class RefusalError(Exception):
    """The instrument cannot see the tree, so it has no verdict to give."""


# -------------------------------------------------------------------------- The five readers. Each is a pure (text) -> set[str] function plus a pure (relpath) -> bool selector, so the controls can drive them directly and a new reader added to SOURCES automatically acquires both-direction controls. --------------------------------------------------------------------------

ENV_FILE_RE = re.compile(r"(^|/)(\.env(\..+)?|[^/]+\.env(\..+)?)$")
ASSIGN_RE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=")


def selects_env_file(rel: str) -> bool:
    return bool(ENV_FILE_RE.search(rel))


def names_from_env_file(text: str) -> set[str]:
    """`KEY=value` lines. Comments are not assignments."""
    out = set()
    for line in text.splitlines():
        if line.lstrip().startswith("#"):
            continue
        m = ASSIGN_RE.match(line)
        if m:
            out.add(m.group(1))
    return out


WORKFLOW_RE = re.compile(r"^\.github/(workflows|actions)/.*\.ya?ml$")
ACTION_RE = re.compile(r"(^|/)action\.ya?ml$")
YAML_KEY_RE = re.compile(r"^\s*([A-Z][A-Z0-9_]*[A-Za-z0-9_])\s*:")


def selects_workflow(rel: str) -> bool:
    return bool(WORKFLOW_RE.match(rel) or ACTION_RE.search(rel))


def names_from_yaml(text: str) -> set[str]:
    """ENV-SHAPED mapping keys: leading capital, no lowercase-only keys.

    Not a yaml parse, and that is deliberate: this must answer on a workflow
    with a `${{ }}` expression in a key position, and it must not need PyYAML
    on a host that has not bootstrapped.
    """
    out = set()
    for line in text.splitlines():
        if line.lstrip().startswith("#"):
            continue
        m = YAML_KEY_RE.match(line)
        if m and NAME_RE.match(m.group(1)):
            out.add(m.group(1))
    return out


JS_RE = re.compile(r"\.(ts|tsx|js|jsx|mjs|cjs|astro|vue|svelte)$")
PROCESS_ENV_RE = re.compile(
    r"process\.env(?:\.([A-Za-z_][A-Za-z0-9_]*)"
    r"|\[\s*['\"`]([A-Za-z_][A-Za-z0-9_]*)['\"`]\s*\])"
)
# Counted and printed, never asserted on: see the module docstring.
PROCESS_ENV_DYNAMIC_RE = re.compile(r"process\.env\[\s*(?!['\"`])")


def selects_js(rel: str) -> bool:
    return bool(JS_RE.search(rel))


def names_from_js(text: str) -> set[str]:
    return {m.group(1) or m.group(2) for m in PROCESS_ENV_RE.finditer(text)}


def dynamic_js_reads(text: str) -> int:
    return len(PROCESS_ENV_DYNAMIC_RE.findall(text))


_ENVIRON_METHODS = frozenset({"get", "setdefault", "pop"})


def selects_py(rel: str) -> bool:
    return rel.endswith(".py")


def _environ_arg(node: ast.AST) -> ast.expr | None:
    """The name expression an `os.environ` read is subscripted or called with."""
    if isinstance(node, ast.Subscript):
        value = node.value
        if isinstance(value, ast.Attribute) and value.attr == "environ":
            return node.slice
        if isinstance(value, ast.Name) and value.id == "environ":
            return node.slice
        return None
    if isinstance(node, ast.Call):
        func = node.func
        if not isinstance(func, ast.Attribute) or not node.args:
            return None
        if func.attr == "getenv":
            return node.args[0]
        if func.attr in _ENVIRON_METHODS:
            base = func.value
            if isinstance(base, ast.Attribute) and base.attr == "environ":
                return node.args[0]
            if isinstance(base, ast.Name) and base.id == "environ":
                return node.args[0]
    return None


def names_from_py(text: str) -> set[str]:
    """`os.environ` reads, INCLUDING one level of module-level constant indirection.

    THIS PARSES RATHER THAN GREPS, and the choice was measured on the tree (2026-09-09) rather than assumed. Against a regex for the literal call forms:

      the AST finds 55 names the regex CANNOT     every read through a constant,
                                                  `os.environ.get(ROOT_ENV)` among
                                                  them -- which is `REDIACC_CI_ROOT`,
                                                  the one seam `paths.py` exists to
                                                  declare
      the regex finds 8 the AST does not          and all eight are string LITERALS
                                                  inside other gates' fixtures:
                                                  FIXTURE_WRITE, FIXTURE_POP,
                                                  FIXTURE_A, FIXTURE_BRAND_NEW, X,
                                                  LIB, STOPDIR, WORKLIST_LIMIT. Not
                                                  one is a read. WORKLIST_LIMIT
                                                  appears NOWHERE in `.claude/`.

    So the regex is not a safety net, it is eight false positives -- and four of them live in a file a concurrent writer is editing, which would have coupled this manifest to another gate's fixture names. Dropped.

    A file that does not parse RAISES. It is not silently skipped and it is not quietly regexed: `derive_sources` turns the raise into a finding, because a Python file this reader cannot read is a hole in the corpus and "unknown" is not "fine".
    """
    tree = ast.parse(text)
    consts: dict[str, str] = {}
    for stmt in tree.body:
        if (
            isinstance(stmt, ast.Assign)
            and len(stmt.targets) == 1
            and isinstance(stmt.targets[0], ast.Name)
            and isinstance(stmt.value, ast.Constant)
            and isinstance(stmt.value.value, str)
        ):
            consts[stmt.targets[0].id] = stmt.value.value
    out = set()
    for node in ast.walk(tree):
        arg = _environ_arg(node)
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            out.add(arg.value)
        elif isinstance(arg, ast.Name) and arg.id in consts:
            out.add(consts[arg.id])
    return {n for n in out if NAME_RE.match(n)}


def selects_vault(rel: str) -> bool:
    return rel == VAULT_REL


def names_from_vault(text: str) -> set[str]:
    """The NAMES in the Bitwarden map. No value is read; the map holds UUIDs."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return set()
    secrets = data.get("secrets")
    if not isinstance(secrets, dict):
        return set()
    return {n for n in secrets if NAME_RE.match(n)}


class Reader:
    """One source set: a selector, an extractor, and its own two controls."""

    def __init__(self, ident, selects, extract, fixture_name, fixture, negative):
        self.id = ident
        self.selects = selects
        self.extract = extract
        self.fixture_name = fixture_name
        self.fixture = fixture
        self.negative = negative


SOURCES = (
    Reader(
        "env-file",
        selects_env_file,
        names_from_env_file,
        "GATE_PROBE_ENVFILE",
        "# GATE_PROBE_COMMENTED=1\nGATE_PROBE_ENVFILE=x\n",
        "# GATE_PROBE_ENVFILE=x\nnot an assignment GATE_PROBE_ENVFILE\n",
    ),
    Reader(
        "workflow-key",
        selects_workflow,
        names_from_yaml,
        "GATE_PROBE_WFKEY",
        "jobs:\n  x:\n    env:\n      GATE_PROBE_WFKEY: '1'\n",
        "jobs:\n  x:\n    steps:\n      - run: echo GATE_PROBE_WFKEY\n",
    ),
    Reader(
        "process-env",
        selects_js,
        names_from_js,
        "GATE_PROBE_JS",
        "const a = process.env.GATE_PROBE_JS;\n",
        "// GATE_PROBE_JS is named in prose, and in env.GATE_PROBE_JS with no process.\n",
    ),
    Reader(
        "os-environ",
        selects_py,
        names_from_py,
        "GATE_PROBE_PY",
        'SEAM = "GATE_PROBE_PY"\nimport os\nv = os.environ.get(SEAM)\n',
        '# GATE_PROBE_PY in a comment, and "GATE_PROBE_PY" as a bare string\nx = "GATE_PROBE_PY"\n',
    ),
    Reader(
        "vault",
        selects_vault,
        names_from_vault,
        "GATE_PROBE_VAULT",
        '{"secrets": {"GATE_PROBE_VAULT": {"id": "u"}}}',
        '{"secrets": {}, "other": {"GATE_PROBE_VAULT": 1}}',
    ),
)


# -------------------------------------------------------------------------- The tree --------------------------------------------------------------------------


def tracked_files(root: pathlib.Path) -> list[str]:
    """`git ls-files`, and nothing else. See the docstring on why not `--others`."""
    proc = subprocess.run(
        ["git", "ls-files", "-z"],
        capture_output=True,
        text=True,
        cwd=str(root),
        check=False,  # a non-zero rc becomes a RefusalError, not a traceback
    )
    if proc.returncode != 0:
        raise RefusalError("git ls-files failed: %s" % proc.stderr.strip())
    return [p for p in proc.stdout.split("\0") if p]


def _read(root: pathlib.Path, rel: str) -> str:
    try:
        return (root / rel).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def derive_sources(root, files=None, suppress=None):
    """Return (names, per_source_names, per_source_files, dynamic_js).

    `suppress` is {relpath: {NAME}} -- the tombstone proof sites. A suppressed
    pair is removed from the SOURCE set but its hit is recorded, so the caller can prove the entry is still live rather than dangling.
    """
    files = tracked_files(root) if files is None else files
    suppress = suppress or {}
    per_names = {r.id: set() for r in SOURCES}
    per_files = {r.id: 0 for r in SOURCES}
    seen_suppressed = {rel: set() for rel in suppress}
    dynamic_js = []
    unreadable = []
    for rel in files:
        text = None
        for reader in SOURCES:
            if not reader.selects(rel):
                continue
            per_files[reader.id] += 1
            if text is None:
                text = _read(root, rel)
            try:
                found = reader.extract(text)
            except (SyntaxError, ValueError) as exc:
                # Not a skip. A file the reader cannot read is a hole in the corpus, and a hole that reports nothing is how a set silently shrinks. See names_from_py.
                unreadable.append("%s: reader `%s` could not read it: %s" % (rel, reader.id, exc))
                continue
            blocked = suppress.get(rel, set()) & found
            if blocked:
                seen_suppressed[rel] |= blocked
            per_names[reader.id] |= found - blocked
        if text is not None and selects_js(rel):
            n = dynamic_js_reads(text)
            if n:
                dynamic_js.append((rel, n))
    names = set()
    for got in per_names.values():
        names |= got
    return names, per_names, per_files, dynamic_js, seen_suppressed, unreadable


# -------------------------------------------------------------------------- The manifest --------------------------------------------------------------------------


def load_manifest(root: pathlib.Path, override: pathlib.Path | None = None) -> dict:
    """The manifest to compare against: the tracked one, or a test-only override.

    The refusal names the path it actually looked at rather than `MANIFEST_REL`, so an override pointed at the wrong file says so instead of accusing the tracked manifest of being missing.
    """
    path = override or root / MANIFEST_REL
    shown = str(override) if override else MANIFEST_REL
    if not path.is_file():
        raise RefusalError(
            "%s is missing. Every verdict this gate gives is a comparison against "
            "that file; without it there is nothing to compare and a green would "
            "mean nothing." % shown
        )
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RefusalError("%s is not valid JSON: %s" % (shown, exc)) from exc


def shard_lists(manifest: dict) -> dict[str, list[str]]:
    shards = manifest.get("shards")
    if not isinstance(shards, dict):
        raise RefusalError("%s has no `shards` object" % MANIFEST_REL)
    missing = [s for s in ALL_SHARDS if s not in shards]
    if missing:
        raise RefusalError(
            "%s is missing shard(s) %s. All eight are required, an empty list "
            "included -- an ABSENT shard and an EMPTY one read the same in the "
            "arithmetic below, and only one of them was a decision."
            % (MANIFEST_REL, ", ".join(missing))
        )
    return {s: list(shards[s]) for s in ALL_SHARDS}


def clause_report(sources: set[str], lists: dict[str, list[str]]) -> list[str]:
    """The four clauses as ARITHMETIC, printed whether they hold or not.

    A verdict line says "the clauses hold". These lines say what was compared, which is what lets a reader notice that one side collapsed to nothing while the equality stayed technically true.
    """
    sets = {s: set(v) for s, v in lists.items()}
    shards = set()
    for got in sets.values():
        shards |= got
    tombstones = sets[TOMBSTONE_SHARD]
    overlap = 0
    for i, left in enumerate(LIVE_SHARDS):
        for right in LIVE_SHARDS[i + 1 :]:
            overlap += len(sets[left] & sets[right])
    return [
        "1. sources \\ shards         = %4d   want %4d    |sources|    = %d"
        % (len(sources - shards), 0, len(sources)),
        "2. shards \\ sources         = %4d   want %4d    |shards|     = %d"
        % (len(shards - sources), len(tombstones), len(shards)),
        "3. live-shard overlap      = %4d   want %4d    %d pairs over %d shards"
        % (
            overlap,
            0,
            len(LIVE_SHARDS) * (len(LIVE_SHARDS) - 1) // 2,
            len(LIVE_SHARDS),
        ),
        "4. tombstones & sources     = %4d   want %4d    |tombstones| = %d"
        % (len(tombstones & sources), 0, len(tombstones)),
    ]


def clause_findings(sources: set[str], lists: dict[str, list[str]]) -> list[str]:
    """The four clauses, each returning its own findings. Order is the box's."""
    findings = []
    sets = {s: set(v) for s, v in lists.items()}
    shards = set()
    for got in sets.values():
        shards |= got
    tombstones = sets[TOMBSTONE_SHARD]

    # 0. within-shard duplicates, which would make every count below a lie
    for shard, entries in lists.items():
        dupes = sorted({n for n in entries if entries.count(n) > 1})
        findings.extend("shard `%s` lists %s more than once" % (shard, n) for n in dupes)
        if entries != sorted(entries):
            findings.append(
                "shard `%s` is not sorted; sort it so a diff shows the change and "
                "not the reflow" % shard
            )

    # 1. sources \ shards == {}
    findings.extend(
        "UNCLASSIFIED %s -- the tree reads it and %s does not place it. Add it "
        "to exactly one of: %s" % (name, MANIFEST_REL, ", ".join(LIVE_SHARDS))
        for name in sorted(sources - shards)
    )

    # 2. shards \ sources == tombstones
    findings.extend(
        "STALE %s -- classified as live but no reader finds it any more. Delete "
        "the entry, or move it to `tombstone` if the name is retired for good. "
        "Do not leave it: an entry nothing reads looks like coverage." % name
        for name in sorted((shards - sources) - tombstones)
    )

    # 3. the seven live shards pairwise disjoint
    for i, left in enumerate(LIVE_SHARDS):
        for right in LIVE_SHARDS[i + 1 :]:
            findings.extend(
                "%s is in BOTH `%s` and `%s`. The shard answers who supplies the "
                "value and who may read it, and a name cannot have two answers -- "
                "pick the more restrictive one." % (name, left, right)
                for name in sorted(sets[left] & sets[right])
            )

    # 4. tombstones & sources == {}
    findings.extend(
        "RESURRECTED %s is a tombstone and the tree reads it again. Use the "
        "replacement recorded in %s. If the read is a PROOF that the name is "
        "dead, register the exact (path, name) pair under "
        "`tombstone_proof_sites` -- never widen it to a whole file." % (name, MANIFEST_REL)
        for name in sorted(tombstones & sources)
    )
    return findings


def proof_site_findings(suppress, seen, lists):
    """Both directions on every (path, NAME) suppression."""
    findings = []
    tombstones = set(lists[TOMBSTONE_SHARD])
    for rel, names in sorted(suppress.items()):
        for name in sorted(names):
            if name not in tombstones:
                findings.append(
                    "tombstone_proof_sites[%s] suppresses %s, which is NOT in the "
                    "tombstone shard. This mechanism may only hide a name that is "
                    "declared dead; anything else is a live variable made invisible." % (rel, name)
                )
            elif name not in seen.get(rel, set()):
                findings.append(
                    "tombstone_proof_sites[%s] names %s and no reader finds it there "
                    "any more -- the entry is dangling. Drop it; the proof it "
                    "protected is gone." % (rel, name)
                )
    return findings


def collision_findings(manifest, root, lists):
    """A name dead in one scope and alive in another must name its authority.

    THE MATCH IS WORD-BOUNDED, and it was a plain substring until a plant refused to fire. Repointing DEBUG's authority at a file that has nothing to do with it still passed, because `REDIACC_DEBUG` contains `DEBUG` -- so any file mentioning the REPLACEMENT would have satisfied the check for the retired name. The plant was the only thing that said so; the selftest agreed with the
    bug, because its fixtures used names that are not substrings of anything.
    """
    findings = []
    tombstones = set(lists[TOMBSTONE_SHARD])
    for entry in manifest.get("collisions", []):
        name = entry.get("name", "")
        authority = entry.get("authority", "")
        if name in tombstones:
            findings.append(
                "collision entry %s is also in the tombstone shard. It is one or the "
                "other: a collision says the name is live SOMEWHERE." % name
            )
        path = root / authority
        if not path.is_file():
            findings.append(
                "collision entry %s cites authority %s, which does not exist" % (name, authority)
            )
        elif not re.search(
            r"\b%s\b" % re.escape(name), path.read_text(encoding="utf-8", errors="replace")
        ):
            findings.append(
                "collision entry %s cites authority %s, which no longer mentions it -- "
                "the scoped ban was dropped and nothing said so" % (name, authority)
            )
    return findings


def note_findings(manifest, lists):
    """A note about a name that is not in the manifest is a note about nothing."""
    known = set()
    for entries in lists.values():
        known |= set(entries)
    return [
        "notes names %s, which is in no shard -- a note nobody can reach is a note "
        "that will be wrong and never noticed" % name
        for name in sorted(set(manifest.get("notes", {})) - known)
    ]


def suppress_map(manifest: dict) -> dict[str, set[str]]:
    raw = manifest.get("tombstone_proof_sites", {})
    return {rel: set(names) for rel, names in raw.items()}


# -------------------------------------------------------------------------- Controls --------------------------------------------------------------------------


def selftest() -> bool:
    """Both directions on every reader, then both directions on the arithmetic."""
    c = Controls("env manifest", 2 * len(SOURCES) + 15)

    for reader in SOURCES:
        c.truthy(
            "reader `%s` FINDS its planted name" % reader.id,
            reader.fixture_name in reader.extract(reader.fixture),
        )
        c.truthy(
            "reader `%s` does NOT find it in prose (control)" % reader.id,
            reader.fixture_name not in reader.extract(reader.negative),
        )

    lists = {s: [] for s in ALL_SHARDS}
    lists["gate-seam"] = ["ALIVE"]
    lists[TOMBSTONE_SHARD] = ["DEAD"]

    c.check("clean tree: four clauses hold", clause_findings({"ALIVE"}, lists), [])
    c.truthy(
        "clause 1 fires on an UNCLASSIFIED name",
        any("UNCLASSIFIED NEWNAME" in f for f in clause_findings({"ALIVE", "NEWNAME"}, lists)),
    )
    c.truthy(
        "clause 2 fires on a STALE live entry",
        any("STALE ALIVE" in f for f in clause_findings(set(), lists)),
    )
    c.truthy(
        "clause 4 fires on a RESURRECTED tombstone",
        any("RESURRECTED DEAD" in f for f in clause_findings({"ALIVE", "DEAD"}, lists)),
    )
    both = {s: [] for s in ALL_SHARDS}
    both["gate-seam"] = ["ALIVE"]
    both["harness"] = ["ALIVE"]
    c.truthy(
        "clause 3 fires on a name in two live shards",
        any("BOTH" in f for f in clause_findings({"ALIVE"}, both)),
    )
    dupe = {s: [] for s in ALL_SHARDS}
    dupe["harness"] = ["ALIVE", "ALIVE"]
    c.truthy(
        "a within-shard duplicate is a finding",
        any("more than once" in f for f in clause_findings({"ALIVE"}, dupe)),
    )
    unsorted_ = {s: [] for s in ALL_SHARDS}
    unsorted_["harness"] = ["B", "A"]
    c.truthy(
        "an unsorted shard is a finding",
        any("not sorted" in f for f in clause_findings({"A", "B"}, unsorted_)),
    )
    c.truthy(
        "a proof site for a name that is NOT a tombstone is refused",
        any(
            "NOT in the tombstone shard" in f
            for f in proof_site_findings({"a.ts": {"ALIVE"}}, {"a.ts": {"ALIVE"}}, lists)
        ),
    )
    c.truthy(
        "a DANGLING proof site is a finding",
        any(
            "dangling" in f for f in proof_site_findings({"a.ts": {"DEAD"}}, {"a.ts": set()}, lists)
        ),
    )

    # The collision authority, both directions -- and the SUBSTRING direction is the one that was actually broken. See collision_findings' docstring.
    tmp = pathlib.Path(tempfile.mkdtemp(dir=runtmp.shared("env-manifest-")))
    try:
        (tmp / "near.ts").write_text("const x = 'REDIACC_DEAD_SUFFIX';\n", encoding="utf-8")
        (tmp / "exact.ts").write_text("banned: 'DEAD',\n", encoding="utf-8")
        col = {"collisions": [{"name": "DEAD", "authority": "near.ts"}]}
        c.truthy(
            "an authority that only contains the name as a SUBSTRING does NOT satisfy it",
            any("no longer mentions it" in f for f in collision_findings(col, tmp, lists)),
        )
        col["collisions"][0]["authority"] = "exact.ts"
        c.check(
            "CONTROL: an authority that names it word-bounded DOES satisfy it",
            [f for f in collision_findings(col, tmp, lists) if "no longer mentions" in f],
            [],
        )
        col["collisions"][0]["authority"] = "absent.ts"
        c.truthy(
            "a missing authority file is a finding",
            any("does not exist" in f for f in collision_findings(col, tmp, lists)),
        )

        # Refusals: the three ways this instrument can lose the tree.
        empty = tmp / "empty-repo"
        empty.mkdir()
        subprocess.run(["git", "init", "-q", str(empty)], capture_output=True, check=False)
        c.truthy(
            "VACUITY: a tree with no manifest is a REFUSAL, not a pass",
            _refuses(lambda: run(empty)),
        )
        (empty / ".ci" / "config").mkdir(parents=True)
        (empty / ".ci" / "config" / "env-manifest.json").write_text(
            '{"shards": {"secret": []}}', encoding="utf-8"
        )
        c.truthy(
            "a manifest missing seven of the eight shards is a REFUSAL",
            _refuses(lambda: run(empty)),
        )
        (empty / ".ci" / "config" / "env-manifest.json").write_text(
            json.dumps({"shards": {s: [] for s in ALL_SHARDS}}), encoding="utf-8"
        )
        c.truthy(
            "a tree no reader can see files in is a REFUSAL, not a green",
            _refuses(lambda: run(empty)),
        )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    c.truthy(
        "a Python file that does not parse RAISES rather than reading as empty",
        _raises_syntax("def (:\n"),
    )
    return not c.report()


def _refuses(fn) -> bool:
    try:
        fn()
    except RefusalError:
        return True
    return False


def _raises_syntax(text: str) -> bool:
    try:
        names_from_py(text)
    except SyntaxError:
        return True
    return False


# -------------------------------------------------------------------------- The run --------------------------------------------------------------------------


def run(root=None):
    # The override applies ONLY to the real invocation (no explicit root, i.e. `run()` from main()). `selftest()`'s controls always pass an explicit fixture root, and must never be redirected onto a plant test's tmp manifest that happens to be sitting in the same process's environment -- that would make every other control's fixture manifest silently wrong.
    use_override = root is None and MANIFEST_OVERRIDE
    base = root or paths.repo_root()
    manifest = load_manifest(base, pathlib.Path(MANIFEST_OVERRIDE) if use_override else None)
    lists = shard_lists(manifest)
    suppress = suppress_map(manifest)
    files = tracked_files(base)
    if not files:
        raise RefusalError(
            "git ls-files returned nothing -- the gate is not seeing the tree, so its "
            "green would mean nothing"
        )
    sources, per_names, per_files, dynamic_js, seen, unreadable = derive_sources(
        base, files, suppress
    )
    blind = [r.id for r in SOURCES if per_files[r.id] == 0]
    if blind:
        raise RefusalError(
            "reader(s) %s matched ZERO candidate files. That is not a repository with "
            "nothing to read, it is a reader that has lost the tree -- fix the selector "
            "or delete the reader." % ", ".join(blind)
        )
    if not sources:
        raise RefusalError("the five readers found ZERO names across %d tracked files" % len(files))
    findings = (
        unreadable
        + clause_findings(sources, lists)
        + proof_site_findings(suppress, seen, lists)
        + collision_findings(manifest, base, lists)
        + note_findings(manifest, lists)
    )
    return findings, sources, per_names, per_files, dynamic_js, lists, manifest, len(files)


def main(argv=None):
    argv = list(argv or [])
    if "--selftest" in argv:
        return 1 if selftest() else 0
    rc = controls_first("env manifest", selftest)
    if rc:
        return rc
    try:
        findings, sources, per_names, per_files, dynamic_js, lists, manifest, n_files = run()
    except RefusalError as exc:
        log.error("env manifest: %s" % exc)
        return 2

    log.info("sources, derived on this run over tracked files:")
    for reader in SOURCES:
        print(
            "  %-13s %5d name(s) from %5d file(s)"
            % (reader.id, len(per_names[reader.id]), per_files[reader.id])
        )
    print("  %-13s %5d name(s) (the union)" % ("TOTAL", len(sources)))

    log.info("the four clauses, as arithmetic:")
    for line in clause_report(sources, lists):
        print("  %s" % line)

    log.info("shards, as %s classifies them:" % MANIFEST_REL)
    for shard in ALL_SHARDS:
        print("  %-16s %4d" % (shard, len(lists[shard])))

    proof = manifest.get("tombstone_proof_sites", {})
    if proof:
        log.info("tombstone proof sites, printed every run so none becomes invisible:")
        for rel, names in sorted(proof.items()):
            print("  %s -> %s" % (rel, ", ".join(sorted(names))))

    for entry in manifest.get("collisions", []):
        log.warn(
            "SCOPED, NOT REPO-WIDE: %s is dead in %s (enforced by %s) and live in %s"
            % (
                entry.get("name"),
                entry.get("dead_in"),
                entry.get("authority"),
                entry.get("live_in"),
            )
        )

    total_dynamic = sum(n for _rel, n in dynamic_js)
    log.info(
        "outside the corpus and NOT asserted on: bash ${VAR}, and %d non-literal "
        "process.env[expr] read(s) in %d file(s)" % (total_dynamic, len(dynamic_js))
    )

    if findings:
        for finding in findings:
            log.error("  %s" % finding)
        log.error(
            "%d finding(s) against %s. Classify the name, do not delete the clause."
            % (len(findings), MANIFEST_REL)
        )
        return 1
    log.success(
        "%d name(s) derived from %d tracked file(s) by %d readers; all classified "
        "across %d live shard(s) plus %d tombstone(s); the four clauses hold"
        % (len(sources), n_files, len(SOURCES), len(LIVE_SHARDS), len(lists[TOMBSTONE_SHARD]))
    )
    return 0


if __name__ == "__main__":
    import sys

    raise SystemExit(main(sys.argv[1:]))
