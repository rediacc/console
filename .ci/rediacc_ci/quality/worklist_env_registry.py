r"""check:ci-worklist-env-registry -- every WORKLIST_* name is registered, and every registered name is read.

THE DEFECT, IN ONE SENTENCE. A typo'd environment name reads as UNSET, and for a feature flag that defaults to `on` that is the FAIL-OPEN direction: the author believes they switched something off, the default applies, and the check keeps firing with nothing anywhere saying why. Four names in this repository are exactly that shape (`WORKLIST_AGENT_HINT`, `WORKLIST_AGENT_PUSHBACK`,
`WORKLIST_CADENCE`, `WORKLIST_FOCUS`), and until 2026-09-09 there was no registry, no schema and nothing that could tell a live name from a dead one.

MEASURED BEFORE ANY OF IT WAS WRITTEN, 2026-09-09, and the numbers matter because the plan box's did not survive contact:

    133 live names, 60 tracked files, 183 read sites
      = 155 Python environment lookups + 28 bash ${...} expansions
    plus 153 bash ASSIGNMENT sites, which are the test corpora setting them

The box said "134 distinct names across ~56-60 files at 178 read sites". 134 is the GREP answer, and one of those is `WORKLIST_EMAIL`, which appears once, in a COMMENT, at `.claude/hooks/stop/worklist-cases/13-ci-queue-and-mail.sh:142`, describing a name that used to exist. It is read nowhere. A registry built from the grep answer would have enshrined it as a live variable on day
one, which is the whole argument for scanning the AST instead.

WHAT IS DERIVED AND WHAT IS AUTHORED, because a registry whose every field is derivable is a second copy of the code.

  DERIVED, and pinned so drift is a finding: the NAME SET, and the set of
  DEFAULT spellings each name is read with. The default set is the more useful
  half. Two call sites reading one name with different fallbacks is a real bug
  class, invisible to any grep, and this gate reports it as a mismatch against
  the pin the moment it appears.

  AUTHORED, and not derivable: the KIND. The derivation cannot tell `'1'` the
  boolean from `'1'` the count, and it gets that wrong for two names in this
  tree today (`WORKLIST_AGENT_HINT_MIN_MARGIN`, `WORKLIST_AGENT_PUSHBACK_MIN_SCORE`
  both default to "1" and neither is a flag). So the kind is a human's claim,
  and the gate checks it for CONSISTENCY with the default shape rather than
  for equality with a guess.

  AUTHORED AND REQUIRED for `flag`, `handle` and `corpus`: a `why`. Those are
  the three kinds where a typo turns something OFF or narrows what is looked at,
  which is the vacuity direction. `tuning` and `path` are exempt from the
  requirement, because 111 machine-written sentences about numeric thresholds
  would be filler, and filler is how a required field stops being read.

`corpus` IS THE RESIDUAL, AND THAT IS WHY IT REQUIRES A REASON. Any name whose default fits no other shape lands there. Making the residual the most expensive kind to declare is what stops it becoming the drawer everything is swept into.

BOTH DIRECTIONS, WHICH IS THE ACCEPTANCE THE BOX ASKS FOR:

  * a name READ in the corpus and absent from the registry reds. That is the
    typo, and it is the direction people expect.
  * a name in the registry that NOTHING reads reds as dead. That is the
    direction that rots, because nothing breaks when a variable stops being
    read, and a registry full of names nobody uses is a registry nobody trusts.

THE EXCLUSIONS ARE IN THE REGISTRY, NOT IN THIS FILE, and the box is right to insist. `agent/` is live gated state under invariant 7 and is full of plans that NAME these variables in prose; admitting it would register every name any plan ever discussed and make "dead" unreportable forever. `docs/` is the same argument. Both are declared in the registry with their reasons, so the
reason travels with the exclusion and this gate cannot quietly widen it. An exclusion prefix that excludes NOTHING is itself a finding.

ANTI-VACUITY, SIX REFUSALS. A missing or unparseable registry; a registry with no names; a registry with no exclusions; a corpus of zero tracked files; a corpus in which zero names are read; and a `git ls-files` that fails. Each exits 1 with its own sentence. The success line prints the name count, the file count, the read-site count and the per-kind breakdown, so a collapse is
visible.

Exit 1 on any finding or refusal, 2 on a failed control.

THE GATE HEADER LIVES IN THE ENTRY POINT, not here. `gate-bind` reads the file the
registry INVOKES, and the registry invokes .ci/scripts/quality/check_worklist_env_registry.py by path;
a header here derives this module's own path and the binding disagrees with
package.json. Measured 2026-09-09: three gates landed with it in the module and
`check:ci-gate-bind` named all three.
"""

from __future__ import annotations

import ast
import json
import os
import pathlib
import re
import subprocess
import sys

from rediacc_ci import log, paths
from rediacc_ci.controls import Checker, controls_first, plant
from rediacc_ci.policy_paths import policy_path

REGISTRY_NAME = "worklist-env-registry.json"
NAME_RE = re.compile(r"WORKLIST_[A-Z0-9_]+")

KINDS = ("flag", "tuning", "path", "handle", "corpus")
WHY_REQUIRED = frozenset({"flag", "handle", "corpus"})
WHY_MIN_CHARS = 60

# The environment-reading call shapes. `pop` and `setdefault` are deliberately absent: neither appears in this tree, and adding a shape nothing uses is a branch no control can reach.
GET_FUNCS = frozenset({"get", "getenv"})

FLAG_DEFAULTS = frozenset({"on", "off", "1", "0", ""})


class RefusalError(Exception):
    """The gate cannot reach a verdict. Exit 1, never a silent pass."""


class Read:
    """One place a WORKLIST_* name is read, with the fallback it is read with.

    `default` is a SPELLING, not a value: `str(400 * 1024)` is kept verbatim rather than evaluated. Evaluating it would make the pin agree with a refactor that changed the arithmetic, which is exactly the change a reader would want to see.
    """

    def __init__(self, name, rel, line, default):
        self.name = name
        self.rel = rel
        self.line = line
        self.default = default


def _is_environ(node):
    """True when `node` is the `os.environ` mapping (or a bare `environ`)."""
    text = ast.unparse(node)
    return text.endswith("environ") or text == "os.environ"


def scan_python(rel, source):
    """Every WORKLIST_* environment READ in one Python file.

    Writes are excluded: `os.environ["X"] = v` is a test setting the variable,
    not code depending on it, and counting it would make a name that only the test corpus assigns look alive.
    """
    tree = ast.parse(source, filename=rel)
    written = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            written.update(
                id(target) for target in node.targets if isinstance(target, ast.Subscript)
            )
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            attr = getattr(func, "attr", None) or getattr(func, "id", None)
            if attr not in GET_FUNCS or not node.args:
                continue
            first = node.args[0]
            if not (isinstance(first, ast.Constant) and isinstance(first.value, str)):
                continue
            if not NAME_RE.fullmatch(first.value):
                continue
            if isinstance(func, ast.Attribute) and not _is_environ(func.value):
                continue
            if not isinstance(func, ast.Attribute) and attr != "getenv":
                continue
            if len(node.args) > 1:
                arg = node.args[1]
                default = repr(arg.value) if isinstance(arg, ast.Constant) else ast.unparse(arg)
            else:
                default = "NONE"
            out.append(Read(first.value, rel, node.lineno, default))
        elif isinstance(node, ast.Subscript) and id(node) not in written:
            key = node.slice
            if (
                isinstance(key, ast.Constant)
                and isinstance(key.value, str)
                and NAME_RE.fullmatch(key.value)
                and _is_environ(node.value)
            ):
                out.append(Read(key.value, rel, node.lineno, "REQUIRED"))
    return out


_BASH_WITH_DEFAULT = re.compile(r"\$\{(WORKLIST_[A-Z0-9_]+):-([^}]*)\}")
_BASH_BARE = re.compile(r"\$\{?(WORKLIST_[A-Z0-9_]+)(?![A-Z0-9_:])")


def scan_bash(rel, source):
    """Every WORKLIST_* expansion in one shell file, with its `:-` fallback.

    An ASSIGNMENT is not a read, for the same reason as in Python. The bash corpus is mostly `worklist-cases/*.sh` setting variables up for a fixture, and 153 of those assignments would otherwise drown the 28 real expansions.
    """
    out = []
    for index, line in enumerate(source.splitlines(), 1):
        out.extend(
            Read(match.group(1), rel, index, repr(match.group(2)))
            for match in _BASH_WITH_DEFAULT.finditer(line)
        )
        out.extend(
            Read(match.group(1), rel, index, "NONE")
            for match in _BASH_BARE.finditer(line)
            if not _BASH_WITH_DEFAULT.match(line, match.start())
        )
    return out


def tracked_files(root):
    """Tracked paths under `root`, from git. Never a filesystem walk.

    The policy is about what is COMMITTED: a scratch file naming a variable is not a read this registry should account for, and a filesystem walk would also drag in `node_modules` and every `__pycache__`.
    """
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), "ls-files", "-z"],
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
    return [p for p in proc.stdout.decode("utf-8", "surrogateescape").split("\0") if p]


#: A single "rel/path:override/file" pair, test-only. `scan_corpus` walks the
#: REAL tracked file list (`git ls-files`) unchanged -- the corpus stays real,
#: which is the whole point of these gate tests plant-driving the live tree --
#: but when the walk reaches `rel/path`, it reads CONTENT from `override/file`
#: (a tmp copy the caller mutated) instead of the tracked file on disk. This is
#: what lets a plant test corrupt a scanned SOURCE file without ever writing to
#: it: `.claude/hooks/stop/test-reggate-ledger.py` is real, tracked, and
#: a hard kill mid-test used to be able to leave it mutated (the same shape as
#: the WORKLIST_FOCUS registry corruption, one file over). Split on the FIRST
#: colon only, so a Windows-style drive-letter override path still parses.
_SOURCE_OVERRIDE = os.environ.get("WORKLIST_SOURCE_OVERRIDE_FILE", "")


def scan_corpus(root, exclusions):
    """(reads, scanned_file_count, excluded_file_count) over the tracked tree."""
    root = pathlib.Path(root)
    files = tracked_files(root)
    if not files:
        raise RefusalError(
            "`git ls-files` returned ZERO paths, so this gate is not seeing the tree; "
            "its green would mean nothing"
        )
    override_rel, _, override_file = _SOURCE_OVERRIDE.partition(":")
    prefixes = tuple(exclusions)
    reads = []
    scanned = 0
    excluded = 0
    for rel in files:
        if prefixes and rel.startswith(prefixes):
            excluded += 1
            continue
        if not rel.endswith((".py", ".sh")):
            continue
        path = pathlib.Path(override_file) if (override_rel and rel == override_rel) else root / rel
        try:
            source = path.read_text(encoding="utf-8", errors="surrogateescape")
        except OSError:
            continue
        scanned += 1
        if rel.endswith(".py"):
            try:
                reads.extend(scan_python(rel, source))
            except SyntaxError as exc:
                raise RefusalError(
                    "%s does not parse (%s), so it cannot be scanned and this gate "
                    "will not report a clean tree around it" % (rel, exc)
                ) from exc
        else:
            reads.extend(scan_bash(rel, source))
    return reads, scanned, excluded


def load_registry(path):
    p = pathlib.Path(path)
    try:
        raw = p.read_text(encoding="utf-8")
    except OSError as exc:
        raise RefusalError(
            "cannot read the registry at %s (%s). Every name in the tree would read "
            "as unregistered and the report would be noise, so this is a refusal." % (p, exc)
        ) from exc
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RefusalError("%s is not valid JSON: %s" % (p, exc)) from exc
    names = obj.get("names")
    if not isinstance(names, dict) or not names:
        raise RefusalError(
            "%s registers no names. An empty registry would report the entire tree "
            "as unregistered, which is not a verdict anybody can act on." % p
        )
    exclusions = obj.get("exclusions")
    if not isinstance(exclusions, dict) or not exclusions:
        raise RefusalError(
            "%s declares no exclusions. agent/ and docs/ NAME these variables in "
            "prose; scanning them would register every name any plan ever discussed. "
            "The exclusions belong here with their reasons, not in the gate." % p
        )
    return obj


def _derived_shape(defaults):
    """What the default spellings say the kind could be. A hint, not a verdict."""
    numeric = all(re.fullmatch(r"'-?\d+(\.\d+)?'", d) or d.startswith("str(") for d in defaults)
    literal_flag = all(d.startswith("'") and d.strip("'") in FLAG_DEFAULTS for d in defaults)
    empty_only = all(d in ("''", "NONE", "REQUIRED") for d in defaults)
    return {"numeric": numeric, "flag": literal_flag, "empty": empty_only}


def check_entry(name, entry, defaults):
    """Schema findings for one registry entry. Pure."""
    out = []
    if not isinstance(entry, dict):
        return ["%s: the entry is not an object" % name]
    kind = entry.get("kind")
    if kind not in KINDS:
        out.append("%s: kind %r is not one of %s" % (name, kind, ", ".join(KINDS)))
        return out
    pinned = entry.get("defaults")
    if not isinstance(pinned, list) or sorted(pinned) != sorted(defaults):
        out.append(
            "%s: the pinned default spellings %r do not match the %d read site(s), "
            "which use %r. Two sites reading one name with different fallbacks is a "
            "real bug; if the change is deliberate, repin."
            % (name, pinned, len(defaults), sorted(defaults))
        )
    shape = _derived_shape(defaults)
    if kind == "flag" and not shape["flag"]:
        out.append(
            "%s is declared a flag but its default(s) %r are not one of on, off, 1, "
            "0 or empty. A flag whose default is a number is a tuning knob, and the "
            "difference is what decides whether a typo is fail-open." % (name, sorted(defaults))
        )
    if kind == "tuning" and not shape["numeric"]:
        out.append(
            "%s is declared tuning but its default(s) %r do not parse as a number"
            % (name, sorted(defaults))
        )
    if kind == "handle" and not shape["empty"]:
        out.append(
            "%s is declared a handle but has a substantive default %r; a handle's "
            "unset state is its normal state" % (name, sorted(defaults))
        )
    if kind == "path" and not (
        name.endswith(("_DIR", "_ROOT", "_PATH", "_FILE")) or any("/" in d for d in defaults)
    ):
        out.append(
            "%s is declared a path but is neither named *_DIR/_ROOT/_PATH/_FILE nor "
            "defaulted to something containing a separator" % name
        )
    why = entry.get("why", "")
    if kind in WHY_REQUIRED and (not isinstance(why, str) or len(why.strip()) < WHY_MIN_CHARS):
        out.append(
            "%s is a %s, where a typo turns something OFF or narrows what is "
            "looked at, so it needs a `why` of at least %d characters saying "
            "which direction the failure goes. It has %d."
            % (name, kind, WHY_MIN_CHARS, len(str(why).strip()))
        )
    return out


def evaluate(registry, reads):
    """(findings, stats). The whole comparison, pure and testable."""
    by_name = {}
    for read in reads:
        by_name.setdefault(read.name, []).append(read)
    registered = registry["names"]
    findings = []
    findings.extend(
        "UNREGISTERED %s is read at %d site(s), first %s:%d, and is in no "
        "registry entry. If it is a typo, fix the spelling: an unknown name "
        "reads as UNSET, which for a flag is the fail-open direction. If it is "
        "new, register it with its kind."
        % (name, len(by_name[name]), by_name[name][0].rel, by_name[name][0].line)
        for name in sorted(set(by_name) - set(registered))
    )
    findings.extend(
        "DEAD %s is registered and read NOWHERE. Delete the entry, or find the "
        "reader that was removed. A registry full of names nobody reads is a "
        "registry nobody trusts." % name
        for name in sorted(set(registered) - set(by_name))
    )
    for name in sorted(set(registered) & set(by_name)):
        findings.extend(
            check_entry(name, registered[name], sorted({r.default for r in by_name[name]}))
        )
    stats = {
        "names": len(by_name),
        "sites": len(reads),
        "files": len({r.rel for r in reads}),
        "kinds": {},
    }
    for name, entry in registered.items():
        if isinstance(entry, dict) and name in by_name:
            kind = entry.get("kind", "?")
            stats["kinds"][kind] = stats["kinds"].get(kind, 0) + 1
    return findings, stats


#: Test-only override for WHICH FILE `load_registry` reads, matching the
#: `LABEL_INVENTORY_LIVE_FILE` seam already in this estate
#: (`label_inventory.py`). The real corpus scan (`scan_corpus`, above)
#: is untouched by this seam -- only the registry file swaps -- so a plant
#: that mutates the REGISTRY no longer has to write the tracked
#: `.ci/policy/worklist-env-registry.json` to exercise the comparison. Two
#: cases (`test_dropping_a_registered_name_reds`,
#: `test_a_registered_name_nobody_reads_reds`) used to write-mutate-restore
#: that tracked file directly; a hard kill in the write window left it
#: genuinely corrupted twice in one session (`WORKLIST_FOCUS` deleted, then
#: `WORKLIST_ZZZ_PHANTOM` added), each time from an unrelated process
#: (a suite timeout, then a concurrent pytest run) landing in the exact
#: millisecond window between the write and the `finally`.
REGISTRY_OVERRIDE = os.environ.get("WORKLIST_REGISTRY_OVERRIDE_FILE", "")


def run(root=None):
    # The override applies ONLY to the real invocation (no explicit root, i.e. `run()` from main()). selftest()'s own controls always pass an explicit fixture root, and must never be redirected onto a plant test's tmp registry that happens to be sitting in the same process's environment -- that would make every OTHER control's fixture registry silently wrong.
    use_override = root is None and REGISTRY_OVERRIDE
    root = pathlib.Path(root or paths.repo_root())
    registry_path = (
        pathlib.Path(REGISTRY_OVERRIDE) if use_override else policy_path(REGISTRY_NAME, root)
    )
    registry = load_registry(registry_path)
    exclusions = sorted(registry["exclusions"])
    reads, scanned, excluded = scan_corpus(root, exclusions)
    if not reads:
        raise RefusalError(
            "ZERO WORKLIST_* reads across %d scanned file(s). Either the scanner has "
            "stopped seeing them or the program has stopped using them; both are "
            "refusals, because every registered name would then read as dead." % scanned
        )
    findings, stats = evaluate(registry, reads)
    # An exclusion that excludes nothing is a claim about the tree that has stopped being true, and it is the half of the exclusion contract that rots.
    if excluded == 0 and exclusions:
        findings.append(
            "the declared exclusions %s matched ZERO tracked paths. An exclusion "
            "that excludes nothing is either a stale prefix or a scanner that has "
            "stopped applying it." % ", ".join(exclusions)
        )
    stats["scanned"] = scanned
    stats["excluded"] = excluded
    stats["exclusions"] = exclusions
    return findings, stats


def main(argv=None):
    argv = list(argv or [])
    if "--selftest" in argv:
        return 1 if selftest() else 0
    rc = controls_first("worklist env registry", selftest)
    if rc:
        return rc
    try:
        findings, stats = run()
    except RefusalError as exc:
        log.error("worklist env registry: %s" % exc)
        return 1
    if findings:
        for finding in findings:
            log.error("  %s" % finding)
        log.error("%d finding(s) against .ci/policy/%s." % (len(findings), REGISTRY_NAME))
        return 1
    for prefix in stats["exclusions"]:
        log.info("  excluded by declaration: %s" % prefix)
    log.success(
        "worklist env registry: %d name(s) across %d file(s) at %d read site(s), "
        "all registered and all read; %d tracked file(s) scanned, %d excluded by "
        "declaration; kinds %s"
        % (
            stats["names"],
            stats["files"],
            stats["sites"],
            stats["scanned"],
            stats["excluded"],
            ", ".join("%s %d" % (k, stats["kinds"][k]) for k in sorted(stats["kinds"])),
        )
    )
    return 0


# --------------------------------------------------------------------------- controls ---------------------------------------------------------------------------

_FIXTURE_PY = """import os

FOCUS = os.environ.get("WORKLIST_FOCUS", "on")
LIMIT = int(os.environ.get("WORKLIST_LIMIT", "5"))
STORE = os.environ["WORKLIST_STORE_DIR"]
os.environ["WORKLIST_LIMIT"] = "9"
"""

_FIXTURE_SH = """#!/usr/bin/env bash
export WORKLIST_LIMIT=3
echo "${WORKLIST_TAIL:-4}"
"""

_FIXTURE_PROSE = "A plan naming WORKLIST_GHOST and WORKLIST_FOCUS in prose.\n"


def _registry_obj():
    return {
        "exclusions": {"agent/": "invariant 7, fixture"},
        "names": {
            "WORKLIST_FOCUS": {
                "kind": "flag",
                "defaults": ["'on'"],
                "why": "a fixture flag whose default is on, so a typo leaves it on and "
                "that is the fail-open direction this registry exists for",
            },
            "WORKLIST_LIMIT": {"kind": "tuning", "defaults": ["'5'"]},
            "WORKLIST_STORE_DIR": {"kind": "path", "defaults": ["REQUIRED"]},
            "WORKLIST_TAIL": {"kind": "tuning", "defaults": ["'4'"]},
        },
    }


def _fixture(tmp, py=_FIXTURE_PY, sh=_FIXTURE_SH, registry=None):
    """A real git repository, because the scanner reads `git ls-files`."""
    root = pathlib.Path(tmp)
    (root / ".ci" / "policy").mkdir(parents=True, exist_ok=True)
    (root / "agent").mkdir(parents=True, exist_ok=True)
    (root / "src.py").write_text(py, encoding="utf-8")
    (root / "run.sh").write_text(sh, encoding="utf-8")
    (root / "agent" / "PLAN.md").write_text(_FIXTURE_PROSE, encoding="utf-8")
    (root / ".ci" / "policy" / REGISTRY_NAME).write_text(
        json.dumps(registry if registry is not None else _registry_obj(), indent=2),
        encoding="utf-8",
    )
    for args in (["init", "-q"], ["add", "-A", "-f"]):
        subprocess.run(["git", "-C", str(root), *args], check=False, capture_output=True)
    return root


def selftest():
    """True when a control failed, which is what `controls_first` expects."""
    import tempfile  # noqa: PLC0415

    check = Checker()

    with tempfile.TemporaryDirectory() as tmp:
        root = _fixture(tmp)
        findings, stats = run(root)
        check("CONTROL: a registry that matches its corpus is clean", findings == [])
        check(
            "CONTROL: and the scan is NOT trivially empty",
            stats["names"] == 4 and stats["sites"] >= 4,
        )
        check(
            "CONTROL: the prose file under agent/ was excluded, not scanned",
            stats["excluded"] >= 1,
        )

    with tempfile.TemporaryDirectory() as tmp:
        typo = plant(_FIXTURE_PY, "WORKLIST_LIMIT", "WORKLIST_LMIIT", 1)
        root = _fixture(tmp, py=typo)
        findings, _ = run(root)
        check(
            "PLANT: a typo'd name is UNREGISTERED and reds",
            any("UNREGISTERED WORKLIST_LMIIT" in f for f in findings),
        )
        check(
            "PLANT: and the message says an unknown name reads as unset",
            any("reads as UNSET" in f for f in findings),
        )

    with tempfile.TemporaryDirectory() as tmp:
        reg = _registry_obj()
        reg["names"]["WORKLIST_NOBODY_READS"] = {"kind": "tuning", "defaults": ["'1'"]}
        root = _fixture(tmp, registry=reg)
        findings, _ = run(root)
        check(
            "PLANT: the OTHER direction -- a registered name nobody reads is DEAD",
            any("DEAD WORKLIST_NOBODY_READS" in f for f in findings),
        )

    with tempfile.TemporaryDirectory() as tmp:
        drifted = plant(_FIXTURE_PY, '"WORKLIST_LIMIT", "5"', '"WORKLIST_LIMIT", "7"')
        root = _fixture(tmp, py=drifted)
        findings, _ = run(root)
        check(
            "PLANT: a default the registry does not pin reds",
            any("do not match the" in f and "WORKLIST_LIMIT" in f for f in findings),
        )

    with tempfile.TemporaryDirectory() as tmp:
        second = _FIXTURE_PY + 'OTHER = os.environ.get("WORKLIST_LIMIT", "99")\n'
        root = _fixture(tmp, py=second)
        findings, _ = run(root)
        check(
            "PLANT: TWO sites reading one name with different fallbacks reds",
            any("WORKLIST_LIMIT" in f and "'99'" in f for f in findings),
        )

    with tempfile.TemporaryDirectory() as tmp:
        reg = _registry_obj()
        reg["names"]["WORKLIST_LIMIT"]["kind"] = "flag"
        root = _fixture(tmp, registry=reg)
        findings, _ = run(root)
        check(
            "PLANT: a numeric knob declared a flag reds on shape",
            any("declared a flag" in f for f in findings),
        )

    with tempfile.TemporaryDirectory() as tmp:
        reg = _registry_obj()
        reg["names"]["WORKLIST_FOCUS"]["why"] = "later"
        root = _fixture(tmp, registry=reg)
        findings, _ = run(root)
        check(
            "PLANT: a flag with no substantive `why` reds",
            any("needs a `why`" in f for f in findings),
        )

    with tempfile.TemporaryDirectory() as tmp:
        reg = _registry_obj()
        reg["names"]["WORKLIST_LIMIT"]["kind"] = "corpus"
        root = _fixture(tmp, registry=reg)
        findings, _ = run(root)
        check(
            "PLANT: the RESIDUAL kind is the most expensive one to declare",
            any("WORKLIST_LIMIT is a corpus" in f for f in findings),
        )

    with tempfile.TemporaryDirectory() as tmp:
        # ANTI-SILENCER, and it is the one that decides whether the exclusion is doing anything. WORKLIST_GHOST is named in agent/PLAN.md and nowhere else; it must NOT appear as a read, in either direction.
        root = _fixture(tmp)
        findings, _ = run(root)
        check(
            "ANTI-SILENCER: a name that appears only in agent/ prose is not a read",
            not any("WORKLIST_GHOST" in f for f in findings),
        )

    with tempfile.TemporaryDirectory() as tmp:
        # ANTI-SILENCER: a bash ASSIGNMENT is not a read. The fixture assigns WORKLIST_LIMIT in run.sh; if assignments counted, its default set would gain a spelling and the pin would red for the wrong reason.
        root = _fixture(tmp)
        findings, _ = run(root)
        check(
            "ANTI-SILENCER: a bash assignment is not a read",
            not any("WORKLIST_LIMIT" in f for f in findings),
        )

    with tempfile.TemporaryDirectory() as tmp:
        # ANTI-SILENCER: a Python WRITE is not a read either. src.py assigns os.environ["WORKLIST_LIMIT"], which must not register as a REQUIRED subscript read.
        root = _fixture(tmp)
        _, stats = run(root)
        check(
            "ANTI-SILENCER: os.environ[X] = v is a write, not a required read",
            stats["names"] == 4,
        )

    with tempfile.TemporaryDirectory() as tmp:
        reg = _registry_obj()
        reg["exclusions"] = {"nowhere/": "a prefix matching nothing"}
        root = _fixture(tmp, registry=reg)
        findings, _ = run(root)
        check(
            "PLANT: an exclusion that excludes NOTHING reds",
            any("matched ZERO tracked paths" in f for f in findings),
        )

    with tempfile.TemporaryDirectory() as tmp:
        reg = _registry_obj()
        reg["names"] = {}
        root = _fixture(tmp, registry=reg)
        check("VACUITY: a registry with no names is a REFUSAL", _refuses(root))

    with tempfile.TemporaryDirectory() as tmp:
        reg = _registry_obj()
        reg["exclusions"] = {}
        root = _fixture(tmp, registry=reg)
        check("VACUITY: a registry with no exclusions is a REFUSAL", _refuses(root))

    with tempfile.TemporaryDirectory() as tmp:
        root = _fixture(tmp, py="X = 1\n", sh="echo hi\n")
        check("VACUITY: a corpus with zero reads is a REFUSAL", _refuses(root))

    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        (root / ".ci" / "policy").mkdir(parents=True)
        check("VACUITY: a missing registry file is a REFUSAL", _refuses(root))

    with tempfile.TemporaryDirectory() as tmp:
        root = _fixture(tmp, py="def broken(:\n")
        check("VACUITY: a file that does not parse is a REFUSAL, not a skip", _refuses(root))

    return not check.ok


def _refuses(root):
    try:
        run(root)
    except RefusalError:
        return True
    return False


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
