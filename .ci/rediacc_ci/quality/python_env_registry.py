r"""check:ci-python-env-registry -- the pinned SET of every `module:NAME` pair where a tracked Python module reads an environment variable, held shrink-only.

THE GENERAL CASE OF `check:ci-worklist-env-registry`. That gate, landed the same day, asks one question about one PREFIX: is every `WORKLIST_*` name registered, and is every registered name read. This one asks the whole-tree question with no prefix at all, and keys on the PAIR rather than the name, because "who reads it" is the half a name-keyed registry throws away. The two are
complements and the narrow one is NOT subsumed: it additionally pins the DEFAULT SPELLING each name is read with and an authored KIND per name, neither of which this file has any opinion about. See the section "WHAT THIS DOES NOT CLAIM" below.

WHY A REGISTRY AT ALL. An environment read is an undeclared input. Nothing in this tree could answer "which Python modules depend on the environment, and on what" without a fresh grep, and a grep answers wrongly in both directions: it misses the 87 pairs read through a module-level constant (`os.environ.get( paths.ROOT_ENV)`), and it counts names that appear only inside string
literals and prose. Both were measured here, on the tree, before a line of this was written; the numbers are in "THE SEEDING RECEIPT" below.

WHAT IS DERIVED, AND WHY NOTHING IS AUTHORED. Every entry in the baseline is derived from the AST. There is no `why` field, no kind, no owner. That is a deliberate difference from the worklist registry: 445 machine-written sentences about environment variables would be filler, and filler is how a required field stops being read. What this file buys instead is CHANGE DETECTION --
the set is frozen, and any movement in it, in either direction, has to be looked at.

THE BASELINE IS SHRINK-ONLY, AND THE ARM THAT USUALLY GOES MISSING IS THE
SECOND ONE. Both of these red:

  * a pair READ in the tree and ABSENT from the registry (a new undeclared
    input; and, identically, a registry entry someone DELETED while the read is
    still there). Deleting a line cannot buy a green, which is what makes this
    a baseline rather than a suggestion.
  * a pair IN the registry that NOTHING reads (the read was removed and the
    registry was not drained; and, identically, an entry someone BANKED for a
    violation that never existed). Nothing can be pre-loaded into the file
    either.

Those are the same two set differences, and stating them as four cases is the point: the two tamper directions are not extra code, they are what set equality already means, and a gate that only checks `derived \ baseline` has half of it.

HOW A GENUINELY NEW READ IS REGISTERED, and why `--write-baseline` alone cannot do it. A blanket reseed is refused whenever it would ADD a pair, exactly as `.ci/scripts/quality/check_language_policy.py` refuses one: a drain that removes 30 and adds 1 has still added 1, and comparing totals is not the same claim as comparing sets. To add, the pair must be TYPED:

    check_python_env_registry.py --write-baseline --allow-new <module>:<NAME>

and `--allow-new` is itself checked -- a pair that is not actually an addition is refused, so the flag cannot be used to pre-bank a read that does not exist.

WHY NOT PURE SHRINK-ONLY WITH NO ADDITION PATH AT ALL. Because the terminal state of "no Python module reads the environment" is not reachable and never will be: `rediacc_ci.paths` reads `REDIACC_CI_ROOT` to find the repository, and every gate test in the suite steers the gate under test through it. A clause that can never be satisfied is a clause that gets suppressed, and the
whole estate is built on not doing that. So the file shrinks by default and grows only through a typed, individually justified diff.

THE ANTI-VACUITY FLOOR IS WRITTEN FOR THE TERMINAL STATE, which is the trap this
week paid for twice. `derived == {}` is a REFUSAL only when the baseline is
non-empty -- that combination is the scanner having gone blind against a registry that still claims hundreds of pairs. An empty baseline with an empty derivation is the (unreachable, but legal) terminal state and passes, printing
zero. `scanned == 0` is an unconditional refusal, and it cannot fire at the
finish line either, because this gate's own module is a tracked `.py` file.

THE SEEDING RECEIPT, 2026-09-09, and it is a receipt with a date rather than an acceptance: every number below is DERIVED and PRINTED on every run, so a reader watches them move instead of trusting this paragraph.

    563 tracked .py files, all 563 parse
    445 pairs across 164 modules = 426 named + 19 opaque; 295 distinct names
    124 of the read sites do not spell the name as a literal. Most of those
      resolve through a module-level constant and contribute 87 pairs the
      literal-only view cannot see (339 -> 426); 19 stay opaque.

    The FILE count is the one number here that moves without anything being
    wrong: peers land tracked Python all day. The pair count is the one to
    watch, which is why the success line prints both.

THAT 87 IS THE ARGUMENT FOR SCANNING THE AST, and the argument against grep. A grep-shaped registry would have been wrong in both directions at once: short by 87 real inputs, and long by every name that appears only inside a string literal or a comment. Both errors are silent, and the second is the worse one, because a registry full of names nobody reads is a registry nobody
trusts.

OPAQUE READS ARE BANKED VISIBLY, NEVER DROPPED. 19 sites read a name held in a local variable -- `os.environ.get(key)` inside a save/restore harness, or a CLI taking names from argv. The registry cannot name the variable, so it records the EXPRESSION with a `*` prefix (`.ci/rediacc_ci/quality/branch.py:*key`) and counts them separately in the success line. Unknown is not folded
into fine: an opaque read is an entry like any other, and a new one reds like any other.

WHY `.ci/config/` AND NOT `.ci/policy/`. Clause 1 of `.ci/policy/README.md` section 1: a policy file is a DECISION, a set of entries someone chose to exempt, each carrying a BLOCKER reason. This file is a MEASUREMENT, generated wholesale by `--write-baseline`, with no reasons in it and none possible. It fails clause 1 and clause 2 for exactly the reasons
`language-policy-baseline.json`, `secret-scope-baseline.json` and `tracked-credentials-baseline.json` do, and it sits beside them. There is also a hard mechanical reason: `.ci/policy/` is under four-way set equality (`check:ci-policy-inventory`), so a file landing there without a matching edit to two POLICY_FILES tuples and the README reds.

WHAT THIS DOES NOT CLAIM, so nobody reads more into a green than is there:

  * it does not know what a variable MEANS, whether it is a secret, or who sets
    it. That is W8 P2's manifest, keyed on the NAME across all languages.
  * it does not check DEFAULTS. `check:ci-worklist-env-registry` does, for its
    prefix, and that check is the reason it must not be folded into this one.
  * it does not scan bash, TypeScript or Go. The name says Python.
  * a read behind `getattr(os, "environ")`, an `os.environ` or its copy handed
    WHOLE to another function that reads it there, or a name built by
    concatenation is invisible to it. The first does not appear in this tree;
    the second did once (turnstile_drift.py, 2026-09-24) and is fixed by reading
    each name by its literal where the alias is bound; the third lands as an
    opaque entry.

THE GATE HEADER LIVES IN THE ENTRY POINT, not here, for the reason `check_worklist_env_registry.py` records: `gate-bind` reads the file the registry INVOKES BY PATH, and a header on the module derives this module's own path, which the package.json binding then disagrees with.

Exit 1 on any finding or refusal, 2 on a failed control.
"""

from __future__ import annotations

import ast
import json
import pathlib
import subprocess
import sys

from rediacc_ci import log, paths
from rediacc_ci.controls import Checker, controls_first, plant

# The baseline, relative to the repository root. NOT reached through `policy_paths.policy_path()`: that seam resolves `.ci/policy/` only, and this file is deliberately not policy (see the docstring).
BASELINE_REL = ".ci/config/python-env-registry.json"
KEY = "modules"

# The call shapes that READ the environment.
#
# `pop` and `setdefault` are DELIBERATELY ABSENT, and the exclusion is worth 7 entries on this tree. Neither is a dependency on a value: `os.environ.pop(k, None)` DISCARDS it (every occurrence here is a test harness clearing the environment before driving a gate) and `setdefault` WRITES. Counting them would put `branch.py:*k` in the registry on the strength of a line whose whole
# purpose is to unset four GITHUB_* variables.
GET_FUNCS = frozenset({"get", "getenv"})

OPAQUE_PREFIX = "*"

NOTE = (
    "SHRINK-ONLY, AND GENERATED -- do not hand-edit except to re-key a moved module. "
    "Every `<module>: [NAME, ...]` here is one environment variable a tracked Python "
    "module reads, derived from the AST by "
    ".ci/scripts/quality/check_python_env_registry.py. A `*` prefix means the name is "
    "not a literal at the call site and the EXPRESSION is recorded instead. The gate "
    "asserts SET EQUALITY with the tree in both directions: a read missing from here "
    "reds, and so does an entry here that nothing reads -- so this file can neither be "
    "trimmed to escape a finding nor pre-loaded with one. Drain it with "
    "`--write-baseline`, which refuses any reseed that would ADD a pair even when the "
    "total shrinks. A genuinely new read must be typed: "
    "`--write-baseline --allow-new <module>:<NAME>`."
)


class RefusalError(Exception):
    """The gate cannot reach a verdict. Exit 1, never a silent pass."""


# --------------------------------------------------------------------------- derivation ---------------------------------------------------------------------------


def module_constants(tree: ast.Module) -> dict[str, str]:
    """MODULE-LEVEL `NAME = "literal"` bindings, with ambiguity dropped.

    Only the top level, and only a plain string constant. A name assigned twice at module level resolves to NOTHING rather than to the first spelling: a wrong resolution is worse than an opaque one, because it puts a name in the registry that the code never reads and the STALE direction then fires on an entry the author cannot find.
    """
    out: dict[str, str] = {}
    seen: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target, value = node.targets[0], node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            target, value = node.target, node.value
        else:
            continue
        if not isinstance(target, ast.Name):
            continue
        if target.id in seen:
            out.pop(target.id, None)
            continue
        seen.add(target.id)
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            out[target.id] = value.value
    return out


def module_index(rels) -> dict[str, str]:
    """Every dotted suffix of every module path -> the file, COLLISIONS NULLED.

    `from rediacc_ci import paths` gives the alias `paths` the dotted target `rediacc_ci.paths`, which must reach `.ci/rediacc_ci/paths.py`; so every suffix of the path is indexed. A suffix produced by two different files maps to nothing at all, for the same reason `module_constants` drops a name assigned twice: an ambiguous hit is a wrong hit.
    """
    hits: dict[str, set[str]] = {}
    for rel in rels:
        parts = rel[: -len(".py")].split("/")
        for i in range(len(parts)):
            hits.setdefault(".".join(parts[i:]), set()).add(rel)
    return {key: next(iter(v)) for key, v in hits.items() if len(v) == 1}


def import_aliases(tree: ast.Module) -> dict[str, str]:
    """Local name -> dotted module it refers to, for `X.CONST` resolution."""
    out: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                out[alias.asname or alias.name] = "%s.%s" % (node.module, alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                out[alias.asname or alias.name] = alias.name
    return out


def _is_environ(node: ast.expr) -> bool:
    """True when `node` is the `os.environ` mapping (or a bare `environ`)."""
    text = ast.unparse(node)
    return text == "os.environ" or text.endswith(".environ") or text == "environ"


def env_key_nodes(tree: ast.Module):
    """Every AST node that is the KEY of an environment READ, in one module.

    Three shapes, and the NON-READ exclusion is the load-bearing part.
    `os.environ["X"] = v` is a test SETTING a variable and `del os.environ["X"]`
    is a test CLEARING one; neither is code depending on a value. Counting either would make a name that only the test corpus manipulates look like an input, and the `del` half is not hypothetical: 34 sites in this tree spell `del os.environ[paths.ROOT_ENV]` inside a save/restore harness, and the first draft of this function scored every one of them as a read. It is the same
    argument that keeps `pop` and `setdefault` out of GET_FUNCS, and the two exclusions have to agree or the registry says a variable is an input depending on which spelling the harness happens to use.
    """
    not_a_read = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            not_a_read.update(id(t) for t in node.targets if isinstance(t, ast.Subscript))
        elif isinstance(node, (ast.AugAssign, ast.AnnAssign)) and isinstance(
            node.target, ast.Subscript
        ):
            not_a_read.add(id(node.target))
        elif isinstance(node, ast.Delete):
            not_a_read.update(id(t) for t in node.targets if isinstance(t, ast.Subscript))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            attr = getattr(func, "attr", None) or getattr(func, "id", None)
            if attr not in GET_FUNCS or not node.args:
                continue
            # `getenv` is admitted BARE or off `os`. `os.getenv(NAME)` is an ast.Attribute whose receiver is `os`, NOT `os.environ`, and the first draft of this function required an environ receiver on every Attribute call, so it saw no `os.getenv` at all.
            #
            # SAY THE UNCOMFORTABLE PART: this arm has ZERO live subjects today. `git ls-files -- '*.py' | xargs grep -c 'os\.getenv'` finds it in no tracked module but this one, so removing the arm would not move the registry by a single pair. It stays because the FIRST `os.getenv` anybody writes would otherwise be invisible, and an undeclared input that the registry cannot see is
            # the one failure this file exists to prevent. Only a fixture reaches it, which is exactly why it needed a control rather than a reading.
            if attr == "getenv":
                if not isinstance(func, ast.Attribute) or ast.unparse(func.value) == "os":
                    yield node.args[0]
            elif isinstance(func, ast.Attribute) and _is_environ(func.value):
                yield node.args[0]
        elif isinstance(node, ast.Subscript) and id(node) not in not_a_read:
            if _is_environ(node.value):
                yield node.slice
        elif (
            isinstance(node, ast.Compare)
            and len(node.ops) == 1
            and isinstance(node.ops[0], (ast.In, ast.NotIn))
            and _is_environ(node.comparators[0])
        ):
            # `"X" in os.environ` is a read of X: the presence IS the value.
            yield node.left


def scan_module(rel: str, tree: ast.Module, consts_by_rel, index) -> set[str]:
    """The NAME set one module contributes. Opaque names carry a `*` prefix."""
    consts = consts_by_rel.get(rel, {})
    aliases = import_aliases(tree)
    here = str(pathlib.PurePosixPath(rel).parent)

    def resolve(node: ast.expr) -> str | None:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, ast.Name):
            return consts.get(node.id)
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            target = index.get(aliases.get(node.value.id, ""))
            if target is not None:
                return consts_by_rel.get(target, {}).get(node.attr)
            sibling = "%s/%s.py" % (here, node.value.id)
            return consts_by_rel.get(sibling, {}).get(node.attr)
        return None

    names = set()
    for key in env_key_nodes(tree):
        resolved = resolve(key)
        names.add(resolved if resolved is not None else OPAQUE_PREFIX + ast.unparse(key))
    return names


def tracked_python(root: pathlib.Path) -> list[str]:
    """Tracked `.py` paths, from git. Never a filesystem walk.

    The claim is about what is COMMITTED. A walk would also drag in every `__pycache__`, `node_modules` and one developer's scratch file, and the baseline would then depend on whose checkout wrote it.
    """
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), "ls-files", "-z", "--", "*.py"],
            capture_output=True,
            check=False,
        )
    except FileNotFoundError as exc:
        raise RefusalError(
            "git is not on PATH, so the tracked-file corpus this gate is built on "
            "cannot be enumerated at all. Install git, or run from a checkout."
        ) from exc
    if proc.returncode != 0:
        raise RefusalError(
            "`git ls-files` failed in %s (exit %d). Without a corpus there is no "
            "verdict, and reporting zero findings would be reporting zero inputs."
            % (root, proc.returncode)
        )
    out = proc.stdout.decode("utf-8", "surrogateescape").split("\0")
    return sorted(p for p in out if p.endswith(".py"))


def derive(root) -> tuple[dict[str, list[str]], int]:
    """({module: sorted names}, scanned_file_count) over the tracked tree."""
    root = pathlib.Path(root)
    rels = tracked_python(root)
    if not rels:
        raise RefusalError(
            "`git ls-files -- '*.py'` returned ZERO paths in %s, so this gate is not "
            "seeing the tree; its green would mean nothing. This gate's own module is "
            "a tracked .py file, so an empty corpus is a broken scan, never a clean one." % root
        )
    for rel in rels:
        if ":" in rel:
            raise RefusalError(
                "the tracked path %r contains a colon, which is the separator this "
                "gate renders `module:NAME` pairs with. Every message and every "
                "--allow-new argument would be ambiguous, so there is no verdict." % rel
            )
    trees: dict[str, ast.Module] = {}
    for rel in rels:
        try:
            source = (root / rel).read_text(encoding="utf-8", errors="surrogateescape")
        except OSError as exc:
            raise RefusalError(
                "%s is tracked but cannot be read (%s), so it cannot be scanned and "
                "this gate will not report a clean tree around it" % (rel, exc)
            ) from exc
        try:
            trees[rel] = ast.parse(source, filename=rel)
        except SyntaxError as exc:
            raise RefusalError(
                "%s does not parse (%s), so its environment reads are invisible and "
                "a clean report around it would be a guess" % (rel, exc)
            ) from exc
    consts_by_rel = {rel: module_constants(tree) for rel, tree in trees.items()}
    index = module_index(trees)
    derived: dict[str, list[str]] = {}
    for rel, tree in trees.items():
        names = scan_module(rel, tree, consts_by_rel, index)
        if names:
            derived[rel] = sorted(names)
    return derived, len(rels)


# --------------------------------------------------------------------------- the baseline, and the set arithmetic that is the whole gate ---------------------------------------------------------------------------


def pairs_of(modules: dict[str, list[str]]) -> set[str]:
    """`{module: [names]}` flattened to the SET of `module:NAME` pairs."""
    return {"%s:%s" % (rel, name) for rel, names in modules.items() for name in names}


def evaluate(baseline: dict[str, list[str]], derived: dict[str, list[str]]):
    """(findings, stats). Pure, and both tamper directions fall out of it.

    NEW is `derived \\ baseline`: a read the registry does not have. That is a new undeclared input AND it is what happens when someone deletes a line to make a red go away, which is why deleting a line cannot make a red go away.

    STALE is `baseline \\ derived`: an entry nothing reads. That is an undrained removal AND it is what happens when someone banks a violation that never existed, which is why nothing can be pre-loaded either.
    """
    have, want = pairs_of(baseline), pairs_of(derived)
    findings = []
    findings.extend(
        "NEW %s -- this module reads that environment variable and the registry does "
        "not have it. An environment read is an undeclared input. If the read is "
        "correct, register it with `--write-baseline --allow-new %s`. If you got here "
        "by DELETING that line from %s, put it back: trimming the baseline is not a "
        "way past this gate, and this finding is what proves it." % (pair, pair, BASELINE_REL)
        for pair in sorted(want - have)
    )
    findings.extend(
        "STALE %s -- the registry has that pair and nothing in the tree reads it. "
        "Either the read was removed and the registry was not drained (run "
        "`--write-baseline`; do NOT hand-edit), or the entry was added for a read that "
        "does not exist, which is the other thing this gate refuses." % pair
        for pair in sorted(have - want)
    )
    opaque = {p for p in want if ":" + OPAQUE_PREFIX in p}
    stats = {
        "pairs": len(want),
        "modules": len(derived),
        "names": len({p.split(":", 1)[1] for p in want - opaque}),
        "opaque": len(opaque),
        "new": len(want - have),
        "stale": len(have - want),
    }
    return findings, stats


def read_baseline(path: pathlib.Path):
    """The registry, or None when the file is absent. Raises on corruption.

    A corrupt baseline is NOT an empty one. Returning `{}` for unreadable JSON
    would report the whole tree as NEW, which is noise, and would also let a single stray byte convert every real finding into the same undifferentiated wall.
    """
    if not path.is_file():
        return None
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RefusalError(
            "%s exists but cannot be read (%s). A corrupt baseline is not an empty "
            "one: every read in the tree would report as NEW. Repair the JSON; do not "
            "delete the file." % (BASELINE_REL, exc)
        ) from exc
    modules = obj.get(KEY)
    if not isinstance(modules, dict):
        raise RefusalError(
            "%s has no object under %r. That key IS the registry; without it there is "
            "nothing to compare the tree against." % (BASELINE_REL, KEY)
        )
    for rel, names in modules.items():
        if not isinstance(names, list) or not all(isinstance(n, str) for n in names):
            raise RefusalError(
                "%s: the entry for %r is not a list of strings" % (BASELINE_REL, rel)
            )
    return {rel: list(names) for rel, names in modules.items()}


def run(root=None):
    """(findings, stats) for the real tree. Refuses rather than guessing."""
    root = pathlib.Path(root or paths.repo_root())
    baseline = read_baseline(root / BASELINE_REL)
    if baseline is None:
        raise RefusalError(
            "%s does not exist. With no registry there is nothing to compare against, "
            "and deleting the file is otherwise the cheapest way to make every finding "
            "disappear at once. Seed it with `--write-baseline --first-seed`." % BASELINE_REL
        )
    derived, scanned = derive(root)
    if not derived and baseline:
        raise RefusalError(
            "ZERO environment reads derived from %d scanned Python file(s), while the "
            "registry claims %d pair(s). The scanner has gone blind, not the tree gone "
            "clean: every registered pair would report as STALE and the drain would "
            "empty the file." % (scanned, len(pairs_of(baseline)))
        )
    findings, stats = evaluate(baseline, derived)
    stats["scanned"] = scanned
    return findings, stats


# --------------------------------------------------------------------------- --write-baseline, where shrink-only is actually enforced ---------------------------------------------------------------------------


def baseline_additions(old, new):
    """Keys `new` carries that `old` did not -- the DIFF half of the shrink-only guard.

    Named the way `.ci/scripts/quality/check_language_policy.py:442` names it, and extracted from the call site rather than left inline, because the composition gate, whose cases moved to `.ci/rediacc_ci/tests/gates/test_gate_shrink_only_composition.py` when W7 P5 retired the bash twin that carried them at `test-shrink-only-composition.sh:148`, requires a writer to DEFINE the
    diff, CALL the verdict, and compute both -- a writer that reseeds without a named diff can drain thirty findings, absorb
    one brand new one, and print a smaller number while doing it.
    """
    return [] if old is None else [k for k in new if k not in old]


def write_verdict(*, exists: bool, first_seed: bool, additions, allowed):
    """The complete write decision. None means the write is allowed.

    Returns `(code, payload)`. Split out and pure so the controls can drive every arm without a filesystem, and so the three refusals below are one statement each rather than three branches inside an I/O function.
    """
    if not exists and not first_seed:
        return ("missing-baseline", None)
    if not exists and first_seed:
        return (None, None)
    unnamed = sorted(set(additions) - set(allowed))
    if unnamed:
        return ("unnamed-additions", unnamed)
    phantom = sorted(set(allowed) - set(additions))
    if phantom:
        return ("phantom-allow-new", phantom)
    return (None, None)


def _explain(code: str, payload, current: int) -> str:
    if code == "missing-baseline":
        return (
            "Refusing to write the baseline: %s does not exist.\n"
            "  With no previous baseline there is nothing to compare against, so all %d\n"
            "  pair(s) would be absorbed and any read added in the meantime would be\n"
            "  enshrined in the same stroke. If this really is a first seed, say so:\n"
            "  --write-baseline --first-seed. If it is not, restore the file."
            % (BASELINE_REL, current)
        )
    if code == "unnamed-additions":
        return (
            "Refusing to write the baseline: it would GAIN %d pair(s) that are not in it\n"
            "  and were not named on the command line.\n%s\n"
            "  The registry shrinks by default. A reseed that drains 30 and adds 1 has\n"
            "  still added 1, and comparing totals is not the same claim as comparing\n"
            "  sets. If each of these is a correct new read, type it:\n"
            "    --write-baseline %s"
            % (
                len(payload),
                "\n".join("    + %s" % p for p in payload),
                " ".join("--allow-new %s" % p for p in payload),
            )
        )
    return (
        "Refusing to write the baseline: %d --allow-new pair(s) are not additions.\n%s\n"
        "  Either the read does not exist in the tree, or it is already registered.\n"
        "  --allow-new admits a read the scanner can SEE; it is not a way to pre-load\n"
        "  the registry with a pair, which the STALE direction would red on anyway."
        % (len(payload), "\n".join("    ? %s" % p for p in payload))
    )


def write_baseline(root=None, *, first_seed: bool = False, allowed=()) -> int:
    root = pathlib.Path(root or paths.repo_root())
    path = root / BASELINE_REL
    previous = read_baseline(path)
    derived, scanned = derive(root)
    want, have = pairs_of(derived), pairs_of(previous or {})
    additions = [] if previous is None else sorted(baseline_additions(have, want))
    code, payload = write_verdict(
        exists=previous is not None,
        first_seed=first_seed,
        additions=additions,
        allowed=allowed,
    )
    if code is not None:
        log.error(_explain(code, payload, len(want)))
        return 1
    body = {"note": NOTE, KEY: {rel: derived[rel] for rel in sorted(derived)}}
    text = json.dumps(body, indent=2) + "\n"
    # THE COMPOSITION ASSERTION, in the code rather than in anyone's memory: a shrink-only baseline guarantees the total cannot grow and guarantees NOTHING about composition. The bytes are re-parsed and the sets diffed BEFORE anything is written, because the first draft wrote the file and THEN refused -- which left a refused reseed on disk and made the very next `--first-seed`
    # report "446 before" against an empty predecessor.
    landed = pairs_of(json.loads(text)[KEY])
    if landed != want:
        log.error("the serialised registry does not round-trip to the derived set")
        return 1
    # ON A FIRST SEED THERE IS NO `have` TO DIFF AGAINST, so this arm is deliberately skipped rather than made to pass by widening `allowed`: with no previous set every pair is an addition, and calling that a surprise would make --first-seed impossible. --first-seed is itself the refusal that guards this case, which is why it has to be typed.
    surprise = sorted((landed - have) - set(allowed)) if previous is not None else []
    if surprise:
        log.error(
            "the baseline would have ADDED %d pair(s) nobody named: %s"
            % (len(surprise), ", ".join(surprise))
        )
        return 1
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    if previous is None:
        log.success(
            "registry SEEDED: %d pair(s) across %d module(s) from %d scanned file(s). "
            "Nothing was compared, because there was nothing to compare against; that "
            "is what --first-seed means and why it has to be typed."
            % (len(want), len(derived), scanned)
        )
        return 0
    log.success(
        "registry written: %d pair(s) across %d module(s) from %d scanned file(s) "
        "(%d before, %d drained, %d added by name)"
        % (
            len(want),
            len(derived),
            scanned,
            len(have),
            len(have - want),
            len(landed - have),
        )
    )
    return 0


# --------------------------------------------------------------------------- entry ---------------------------------------------------------------------------


def main(argv=None) -> int:
    argv = list(argv or [])
    if "--selftest" in argv:
        return 1 if selftest() else 0
    if "--write-baseline" in argv:
        allowed = []
        for i, arg in enumerate(argv):
            if arg != "--allow-new":
                continue
            # A DANGLING FLAG IS AN ERROR, NOT AN EMPTY LIST. `--allow-new` with nothing after it, or with the next token being another flag, is a typed permission that names nothing; silently dropping it would turn an intended registration into a blanket reseed the very next refusal then blames on the author.
            if i + 1 >= len(argv) or argv[i + 1].startswith("--"):
                log.error("--allow-new needs a <module>:<NAME> argument after it")
                return 1
            allowed.append(argv[i + 1])
        return write_baseline(first_seed="--first-seed" in argv, allowed=allowed)
    rc = controls_first("python env registry", selftest)
    if rc:
        return rc
    try:
        findings, stats = run()
    except RefusalError as exc:
        log.error("python env registry: %s" % exc)
        return 1
    if findings:
        for finding in findings:
            log.error("  %s" % finding)
        log.error(
            "%d finding(s) against %s: %d new, %d stale."
            % (len(findings), BASELINE_REL, stats["new"], stats["stale"])
        )
        return 1
    log.success(
        "python env registry: %d pair(s) across %d module(s) -- %d distinct name(s) plus "
        "%d opaque read(s) -- match %s exactly, in both directions; %d tracked .py "
        "file(s) scanned"
        % (
            stats["pairs"],
            stats["modules"],
            stats["names"],
            stats["opaque"],
            BASELINE_REL,
            stats["scanned"],
        )
    )
    return 0


# --------------------------------------------------------------------------- controls ---------------------------------------------------------------------------
#
# BOTH DIRECTIONS AND BOTH TAMPERS. A gate with only positive controls will happily flag the whole tree, and a shrink-only baseline with only the NEW direction can be trimmed to green. The four cases named in the docstring each have a control below, and each of the four is planted rather than asserted: `plant()` raises if a mutation would not have changed the fixture, so a control
# cannot pass against clean input.

_SRC = """import os

from pkg import consts

TOKEN_ENV = "FIXTURE_TOKEN"
PROSE = "FIXTURE_STRING_ONLY is only ever a string literal, never read"

A = os.environ.get("FIXTURE_A", "1")
B = os.environ[TOKEN_ENV]
C = os.getenv(consts.ROOT_ENV)
D = "FIXTURE_D" in os.environ

os.environ["FIXTURE_WRITE"] = "x"
os.environ.pop("FIXTURE_POP", None)
os.environ["FIXTURE_DEL"] = "y"
del os.environ["FIXTURE_DEL"]


def loop(keys):
    return [os.environ.get(key) for key in keys]
"""

_CONSTS = """import os

ROOT_ENV = "FIXTURE_ROOT"

TWICE = "FIXTURE_FIRST"
TWICE = "FIXTURE_SECOND"

E = os.environ.get(TWICE)
"""

_CLEAN_MODULES = {
    "pkg/consts.py": ["*TWICE"],
    "src.py": ["*key", "FIXTURE_A", "FIXTURE_D", "FIXTURE_ROOT", "FIXTURE_TOKEN"],
}


def _fixture(tmp, src=_SRC, consts=_CONSTS, modules=_CLEAN_MODULES):
    """A real git repository, because the scanner reads `git ls-files`."""
    root = pathlib.Path(tmp)
    (root / "pkg").mkdir(parents=True, exist_ok=True)
    (root / "src.py").write_text(src, encoding="utf-8")
    (root / "pkg" / "consts.py").write_text(consts, encoding="utf-8")
    (root / "notes.md").write_text("prose naming FIXTURE_GHOST\n", encoding="utf-8")
    if modules is not None:
        path = root / BASELINE_REL
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"note": NOTE, KEY: modules}, indent=2), encoding="utf-8")
    for args in (["init", "-q"], ["add", "-A", "-f"]):
        subprocess.run(["git", "-C", str(root), *args], check=False, capture_output=True)
    return root


def _quiet(fn, *args, **kwargs):
    """Run `fn`, returning `(rc, everything it logged)` and printing none of it.

    The write-path controls DRIVE refusals, and a refusal writes `\u2717 Refusing to write the baseline` to the default logger. Left alone, a fully GREEN selftest scrolls three of those past the reader, which is the shape that teaches people to skim a gate's output. Capturing also upgrades the controls: they assert the message a human would act on, not just the rc.
    """
    import io  # noqa: PLC0415

    buf = io.StringIO()
    log.reset(stream=buf, colour=False)
    try:
        return fn(*args, **kwargs), buf.getvalue()
    finally:
        # `reset()` with no arguments rebuilds exactly the logger `default()` would have built. Restoring `previous.stream` instead would pin sys.stderr as it is RIGHT NOW, and the whole point of the `stream` property one module over is that it resolves late.
        log.reset()


def _refuses(root) -> bool:
    try:
        run(root)
    except RefusalError:
        return True
    return False


def selftest() -> bool:
    """True when a control failed, which is what `controls_first` expects."""
    import copy  # noqa: PLC0415
    import tempfile  # noqa: PLC0415

    check = Checker()

    with tempfile.TemporaryDirectory() as tmp:
        root = _fixture(tmp)
        findings, stats = run(root)
        check("CONTROL: a registry that matches its corpus is clean", findings == [])
        check(
            "CONTROL: and the scan is NOT trivially empty",
            (stats["pairs"], stats["modules"], stats["opaque"]) == (6, 2, 2),
        )
        check(
            "CONTROL: a module-level constant RESOLVES (FIXTURE_TOKEN via TOKEN_ENV)",
            "FIXTURE_TOKEN" in derive(root)[0]["src.py"],
        )
        check(
            "CONTROL: a CROSS-MODULE constant resolves (consts.ROOT_ENV)",
            "FIXTURE_ROOT" in derive(root)[0]["src.py"],
        )
        check(
            "CONTROL: `'X' in os.environ` is a read",
            "FIXTURE_D" in derive(root)[0]["src.py"],
        )
        check(
            "ANTI-SILENCER: os.environ[X] = v is a WRITE, not a read",
            not any("FIXTURE_WRITE" in n for n in derive(root)[0]["src.py"]),
        )
        check(
            "ANTI-SILENCER: os.environ.pop() DISCARDS a value, so it is not a read",
            not any("FIXTURE_POP" in n for n in derive(root)[0]["src.py"]),
        )
        check(
            "ANTI-SILENCER: `del os.environ[X]` CLEARS a value, so it is not a read",
            not any("FIXTURE_DEL" in n for n in derive(root)[0]["src.py"]),
        )
        check(
            "ANTI-SILENCER: a name that is only ever a string literal is not a read",
            not any("FIXTURE_STRING_ONLY" in n for n in derive(root)[0]["src.py"]),
        )
        check(
            "ANTI-SILENCER: a name that appears only in prose is not a read",
            not any("FIXTURE_GHOST" in n for ns in derive(root)[0].values() for n in ns),
        )
        check(
            "CONTROL: a constant assigned TWICE resolves to nothing, not to the first",
            derive(root)[0]["pkg/consts.py"] == ["*TWICE"],
        )
        check(
            "CONTROL: a non-literal key is banked as an OPAQUE entry, never dropped",
            "*key" in derive(root)[0]["src.py"],
        )

    # ---- THE ARM THAT USUALLY GOES MISSING, direction 1 ------------------- An entry REMOVED while the read is still there must red. A baseline that can be trimmed to escape the gate is not a baseline.
    with tempfile.TemporaryDirectory() as tmp:
        trimmed = copy.deepcopy(_CLEAN_MODULES)
        trimmed["src.py"] = [n for n in trimmed["src.py"] if n != "FIXTURE_A"]
        if len(trimmed["src.py"]) == len(_CLEAN_MODULES["src.py"]):
            raise AssertionError("the trim removed nothing; the control would be vacuous")
        root = _fixture(tmp, modules=trimmed)
        findings, _ = run(root)
        check(
            "TAMPER 1: DELETING a baseline entry whose read persists reds as NEW",
            any(f.startswith("NEW src.py:FIXTURE_A") for f in findings),
        )
        check(
            "TAMPER 1: and the message says trimming is not a way past the gate",
            any("trimming the baseline is not a way past" in f for f in findings),
        )

    # Removing the WHOLE module's entry is the same tamper at a coarser grain, and it is the one a `del` on a JSON key produces.
    with tempfile.TemporaryDirectory() as tmp:
        gutted = {k: v for k, v in _CLEAN_MODULES.items() if k != "src.py"}
        root = _fixture(tmp, modules=gutted)
        findings, _ = run(root)
        check(
            "TAMPER 1b: deleting an entire module key reds once per read it held",
            len([f for f in findings if f.startswith("NEW src.py:")]) == 5,
        )

    with tempfile.TemporaryDirectory() as tmp:
        root = _fixture(tmp, modules={})
        findings, _ = run(root)
        check(
            "TAMPER 1c: emptying the registry entirely reds, it does not pass",
            len(findings) == 6,
        )

    # ---- THE ARM THAT USUALLY GOES MISSING, direction 2 ------------------- An entry ADDED for a violation that does not exist must red. Nothing may be banked in advance.
    with tempfile.TemporaryDirectory() as tmp:
        banked = copy.deepcopy(_CLEAN_MODULES)
        banked["src.py"] = sorted([*banked["src.py"], "FIXTURE_NEVER_READ"])
        root = _fixture(tmp, modules=banked)
        findings, _ = run(root)
        check(
            "TAMPER 2: BANKING an entry no read backs reds as STALE",
            any(f.startswith("STALE src.py:FIXTURE_NEVER_READ") for f in findings),
        )
        check(
            "TAMPER 2: and the message names the pre-banking case explicitly",
            any("added for a read that does not exist" in f for f in findings),
        )

    with tempfile.TemporaryDirectory() as tmp:
        banked = copy.deepcopy(_CLEAN_MODULES)
        banked["no/such/module.py"] = ["FIXTURE_A"]
        root = _fixture(tmp, modules=banked)
        findings, _ = run(root)
        check(
            "TAMPER 2b: a pair keyed on a module that does not exist reds as STALE",
            any(f.startswith("STALE no/such/module.py:FIXTURE_A") for f in findings),
        )

    # ---- the two ordinary directions --------------------------------------
    with tempfile.TemporaryDirectory() as tmp:
        grown = _SRC + 'F = os.environ.get("FIXTURE_BRAND_NEW")\n'
        root = _fixture(tmp, src=grown)
        findings, _ = run(root)
        check(
            "PLANT: a NEW environment read in the tree reds",
            any(f.startswith("NEW src.py:FIXTURE_BRAND_NEW") for f in findings),
        )
        check(
            "PLANT: and the failure names the exact --allow-new invocation",
            any("--allow-new src.py:FIXTURE_BRAND_NEW" in f for f in findings),
        )

    with tempfile.TemporaryDirectory() as tmp:
        shrunk = plant(_SRC, 'A = os.environ.get("FIXTURE_A", "1")\n', "A = 1\n")
        root = _fixture(tmp, src=shrunk)
        findings, _ = run(root)
        check(
            "PLANT: a read REMOVED from the tree reds until the registry is drained",
            any(f.startswith("STALE src.py:FIXTURE_A") for f in findings),
        )
        check(
            "PLANT: and the drain instruction forbids hand-editing",
            any("do NOT hand-edit" in f for f in findings),
        )

    with tempfile.TemporaryDirectory() as tmp:
        renamed = plant(
            plant(_SRC, "for key in keys", "for slot in keys"),
            "os.environ.get(key)",
            "os.environ.get(slot)",
        )
        root = _fixture(tmp, src=renamed)
        findings, _ = run(root)
        check(
            "RE-KEY: renaming the variable an opaque read uses reds BOTH ways",
            any("NEW src.py:*slot" in f for f in findings)
            and any("STALE src.py:*key" in f for f in findings),
        )

    # ---- the write path: shrink-only is enforced HERE ----------------------
    check(
        "WRITE: a reseed that would absorb an unnamed addition is refused",
        write_verdict(exists=True, first_seed=False, additions=["a.py:X"], allowed=[])[0]
        == "unnamed-additions",
    )
    check(
        "WRITE: a pure drain is allowed",
        write_verdict(exists=True, first_seed=False, additions=[], allowed=[])[0] is None,
    )
    check(
        "WRITE: a drain of 30 that adds 1 is STILL refused (composition, not total)",
        write_verdict(exists=True, first_seed=False, additions=["a.py:X"], allowed=[])[1]
        == ["a.py:X"],
    )
    check(
        "WRITE: a NAMED addition is allowed",
        write_verdict(exists=True, first_seed=False, additions=["a.py:X"], allowed=["a.py:X"])[0]
        is None,
    )
    check(
        "WRITE: --allow-new for a pair that is not an addition is refused",
        write_verdict(exists=True, first_seed=False, additions=[], allowed=["a.py:X"])[0]
        == "phantom-allow-new",
    )
    check(
        "WRITE: a missing baseline is refused without --first-seed",
        write_verdict(exists=False, first_seed=False, additions=[], allowed=[])[0]
        == "missing-baseline",
    )
    check(
        "CONTROL: --first-seed permits a missing baseline",
        write_verdict(exists=False, first_seed=True, additions=[], allowed=[])[0] is None,
    )

    with tempfile.TemporaryDirectory() as tmp:
        grown = _SRC + 'F = os.environ.get("FIXTURE_BRAND_NEW")\n'
        root = _fixture(tmp, src=grown)
        rc_blanket, said = _quiet(write_baseline, root)
        findings_after_refusal, _ = run(root)
        rc_named, _ = _quiet(write_baseline, root, allowed=["src.py:FIXTURE_BRAND_NEW"])
        check("WRITE: a blanket --write-baseline over a new read exits 1", rc_blanket == 1)
        check(
            "WRITE: and the refusal names the pair and the typed form",
            "+ src.py:FIXTURE_BRAND_NEW" in said and "--allow-new src.py:FIXTURE_BRAND_NEW" in said,
        )
        # THE REFUSAL MUST NOT HAVE WRITTEN. The first draft serialised, wrote, and only then diffed the sets, so a refused reseed sat on disk and the next --first-seed reported "446 before" against an empty predecessor.
        check(
            "WRITE: the refusal left the file UNTOUCHED -- the new read still reds",
            any(f.startswith("NEW src.py:FIXTURE_BRAND_NEW") for f in findings_after_refusal),
        )
        check("WRITE: the named write succeeds", rc_named == 0)
        check("WRITE: and the gate is green after it", run(root)[0] == [])

    with tempfile.TemporaryDirectory() as tmp:
        shrunk = plant(_SRC, 'A = os.environ.get("FIXTURE_A", "1")\n', "A = 1\n")
        root = _fixture(tmp, src=shrunk)
        rc, _ = _quiet(write_baseline, root)
        findings, _ = run(root)
        check("WRITE: a pure drain writes and leaves the gate green", (rc, findings) == (0, []))
        check(
            "WRITE: and the drained pair is gone from the file",
            "FIXTURE_A" not in json.dumps(read_baseline(root / BASELINE_REL)),
        )

    # ---- anti-vacuity ------------------------------------------------------
    with tempfile.TemporaryDirectory() as tmp:
        root = _fixture(tmp, modules=None)
        check("VACUITY: a MISSING registry file is a REFUSAL, not an empty set", _refuses(root))

    with tempfile.TemporaryDirectory() as tmp:
        root = _fixture(tmp)
        (root / BASELINE_REL).write_text("{ not json", encoding="utf-8")
        check("VACUITY: a CORRUPT registry is a REFUSAL, not an empty one", _refuses(root))

    with tempfile.TemporaryDirectory() as tmp:
        root = _fixture(tmp)
        (root / BASELINE_REL).write_text('{"note": "x"}', encoding="utf-8")
        check("VACUITY: a registry with no `modules` key is a REFUSAL", _refuses(root))

    with tempfile.TemporaryDirectory() as tmp:
        root = _fixture(tmp, src="def broken(:\n")
        check("VACUITY: a file that does not PARSE is a REFUSAL, not a skip", _refuses(root))

    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        (root / BASELINE_REL).parent.mkdir(parents=True)
        (root / BASELINE_REL).write_text(json.dumps({KEY: _CLEAN_MODULES}), encoding="utf-8")
        subprocess.run(["git", "-C", str(root), "init", "-q"], check=False, capture_output=True)
        check("VACUITY: a corpus of ZERO tracked .py files is a REFUSAL", _refuses(root))

    with tempfile.TemporaryDirectory() as tmp:
        root = _fixture(tmp, src="X = 1\n", consts="Y = 2\n")
        check(
            "VACUITY: zero derived reads against a NON-EMPTY registry is a REFUSAL",
            _refuses(root),
        )

    # THE FINISH-LINE CLAUSE, and it is written for the terminal state on
    # purpose. An empty registry over a tree with no reads is legal and PASSES;
    # `n > 0` here would red the day the debt reached zero and report a success as a broken parser, which is a shape this estate has shipped twice.
    with tempfile.TemporaryDirectory() as tmp:
        root = _fixture(tmp, src="X = 1\n", consts="Y = 2\n", modules={})
        findings, stats = run(root)
        check(
            "TERMINAL STATE: an empty registry over a tree with no reads PASSES",
            (findings, stats["pairs"]) == ([], 0),
        )

    with tempfile.TemporaryDirectory() as tmp:
        root = _fixture(tmp)
        (root / "has:colon.py").write_text("X = 1\n", encoding="utf-8")
        subprocess.run(
            ["git", "-C", str(root), "add", "-A", "-f"], check=False, capture_output=True
        )
        check(
            "VACUITY: a tracked path containing the pair separator is a REFUSAL",
            _refuses(root),
        )

    return not check.ok


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
