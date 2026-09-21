"""Every ported gate test and its bash twin must reach the SAME VERDICT on THIS tree.

WHY THIS FILE IS THE POINT OF THE PORT. A migration that changes a verdict is not a migration, it is a regression wearing one. The only way to know a port still says what the original said is to run BOTH, on the same tree, in the same run -- which is also why invariant 5 forbids deleting a twin in the change that ports it. A twin kept but never driven is a twin that quietly rots; a
twin driven on every run is a control.

WHAT IS COMPARED, and why it is not "did they both exit 0".

  1. THE VERDICT. Both green, or both red. A port that goes green where the twin
     goes red has stopped asserting something; a port that goes red where the twin
     goes green has invented a finding. Either is a defect in the port, and the
     message says which direction it went.

  2. THE CASE SET, which is SET-BASED and therefore cannot be satisfied by a count.
     Every `test_*()` function the twin DECLARES AND CALLS must have a same-named
     `def test_*` in the port. Dropping one case while keeping the others is exactly
     the failure a count of tests would let through -- delete a case, add a case, the
     total is unchanged and the composition is not. (The port may ADD cases; several
     do, to prove a reader the twin implemented in awk and the port reimplemented in
     Python agree.)

  3. FOR A FLAT TWIN, which declares no functions at all, there is no case set to
     compare, so the floor falls back to the twin's own `PASS:` line count MEASURED
     AT RUNTIME. Still corpus-derived -- it moves when the twin moves -- and never
     typed here.

THE CONTROL COUNTS COME FROM A LEDGER, not from parsing pytest's output. The port runs in a subprocess with `$GATE_HARNESS_LEDGER` pointing at a scratch file, and `Harness` appends one JSON row per recorded control. Parsing "N passed" would count TEST FUNCTIONS, which is the number that says nothing about whether they asserted.

ANTI-VACUITY. Discovering zero ported modules is a FAILURE, not an empty parametrize that reports green having compared nothing. `test_the_registry_is_not_empty` is that refusal, and it prints the shape so a collapse is visible rather than silent.
"""

import datetime
import hashlib
import importlib
import json
import os
import pathlib
import re
import subprocess
import sys

import pytest

from rediacc_ci import paths, xdist_groups
from rediacc_ci.tests.gates import harness

HERE = pathlib.Path(__file__).resolve().parent

# A ported module is one whose name starts `test_gate_` AND that declares a `BASH_TWIN`. Both halves matter: the prefix keeps this file and the harness's own controls out of the set, and the attribute is what makes membership a DECLARATION rather than a guess about a filename.
MODULE_GLOB = "test_gate_*.py"

ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
BASH_FN_RE = re.compile(r"^(test_[A-Za-z0-9_]+)\(\)\s*\{", re.MULTILINE)
PY_FN_RE = re.compile(r"^def (test_[A-Za-z0-9_]+)\s*\(", re.MULTILINE)
PASS_LINE_RE = re.compile(r"^PASS:", re.MULTILINE)


# How long a twin, and the nested pytest that ports it, each get before the
# driver gives up. A port may raise its own with `TWIN_TIMEOUT = <seconds>`
# beside its `BASH_TWIN`.
#
# WHY THIS IS DECLARABLE RATHER THAN ONE NUMBER. It was one number, 600, and that silently made a whole class of twin UNPORTABLE: `test-claude-hooks.sh` runs 2 229 offline cases in 13m31s, so the driver would raise `TimeoutExpired` before either side reached a verdict, and the port would look like a defect in the port. A fifth batch would then select that subject, discover the same
# wall, and drop it again -- which is how a real constraint becomes folklore. The subject declares what it costs instead.
#
# CAPPED, because a declared timeout is also a way to hang the suite forever. `check:ci-pytest` is the slowest gate in the estate already; anything past the cap is a subject that needs splitting, not a bigger number.
DEFAULT_TWIN_TIMEOUT = 600
MAX_TWIN_TIMEOUT = 1800


# The attribute a port sets to say "yes, my twin touches the real tree, and I have arranged to be serialised against everything else that does".
REAL_TREE_ATTR = "REAL_TREE_TWIN"


def ported_modules() -> list[tuple[str, pathlib.Path, str, int]]:
    """(module name, module path, twin repo-relative path, timeout), sorted."""
    found = []
    for path in sorted(HERE.glob(MODULE_GLOB)):
        module = importlib.import_module("rediacc_ci.tests.gates." + path.stem)
        twin = getattr(module, "BASH_TWIN", None)
        if isinstance(twin, str) and twin:
            declared = getattr(module, "TWIN_TIMEOUT", DEFAULT_TWIN_TIMEOUT)
            if not isinstance(declared, int) or declared <= 0:
                declared = DEFAULT_TWIN_TIMEOUT
            MODULE_OBJECTS[path.stem] = module
            found.append((path.stem, path, twin, min(declared, MAX_TWIN_TIMEOUT)))
    return found


# Kept beside the tuple list because `group_for` reads DECLARATIONS off the imported module, not off its path -- a name in a file is a guess, an attribute on the module is a statement.
MODULE_OBJECTS: dict[str, object] = {}


def real_tree_admission(module: object, twin: str, unsafe: set[str]) -> str | None:
    """None when this module may drive its real-tree twin, else why not.

    THE BLANKET REFUSAL THIS REPLACES was correct about the danger and wrong about the remedy. It refused EVERY ported twin in the real-tree set, so the isolation machinery existed (`group_for` already returns `REAL_TREE_GROUP`) and the parity driver forbade using it -- leaving 27 of the 51 remaining twins, the largest blocked group in W7 P3, unportable by policy rather than by any
    technical obstacle. Those 27 include the instruments this whole slice is measured by: `test-ci-parity.sh`, `test-language-policy.sh`, `test-gate-anti-vacuity.sh`, `test-dead-bash.sh`.

    An opt-in replaces it, and it is deliberately TWO conditions rather than
    one. A module that merely declares `REAL_TREE_TWIN = True` has stated an
    intention; what makes it safe is landing in `REAL_TREE_GROUP`, which is what actually serialises it against the battery. Accepting the declaration alone would be the vacuous shape -- a promise checked against itself.

    The reverse drift is refused too: declaring the attribute for a twin that is NOT in the real-tree set takes a serialisation slot nothing needs, and an opt-in that costs nothing to over-claim stops meaning anything.
    """
    declared = bool(getattr(module, REAL_TREE_ATTR, False))
    is_real_tree = os.path.basename(twin) in unsafe
    if not is_real_tree:
        if declared:
            return (
                "declares %s but its twin %s is NOT in the real-tree set, so the "
                "declaration serialises it against the battery for nothing. Remove "
                "the attribute, or land the `tree:` declaration that makes it true."
                % (REAL_TREE_ATTR, os.path.basename(twin))
            )
        return None
    if not declared:
        return (
            "drives a twin that touches the real tree without declaring %s. "
            "check:ci-pytest declares no isolation to either scheduler, so a parity "
            "run overlapping the battery is a flake nobody can reproduce." % REAL_TREE_ATTR
        )
    if xdist_groups.group_for(module, unsafe) != xdist_groups.REAL_TREE_GROUP:
        return (
            "declares %s but does not land in %r -- an %s of its own overrides the "
            "grouping, so the declaration promises isolation the scheduler will not "
            "give it." % (REAL_TREE_ATTR, xdist_groups.REAL_TREE_GROUP, xdist_groups.GROUP_ATTR)
        )
    return None


MODULES = ported_modules()


def real_tree_tests() -> set[str]:
    """Gate tests that touch the REAL tree while they run.

    WHY THIS EXISTS, and it is the constraint the remaining batches will hit. Driving a bash twin from inside `check:ci-pytest` makes that gate a participant in the battery's isolation contract WITHOUT declaring anything to either scheduler. Four of the 148 write into the real tree (one of them rewrites CLAUDE.md and scripts/data/doc-registry.md and restores them) and about twenty
    read it; a parity run overlapping one of those is the `cp: cannot stat` / grep-exit-2 flake the battery's W/S/T schedule exists to prevent, and it would be blamed on the port.

    THE DERIVATION ITSELF NOW LIVES IN `rediacc_ci.xdist_groups`, and this is a call into it rather than a copy of it. The parallel scheduler asks the SAME question this test asks -- which twins may not run beside another -- and two implementations of one question is two answers, the expensive half being that both look right. The source, and the anti-vacuity refusal on an
    empty answer, are written there.
    """
    return xdist_groups.real_tree_twins(xdist_groups.lock_path())


def bash_cases(twin_source: str) -> set[str]:
    """Function names the twin both DECLARES and CALLS.

    Declared-but-never-called is dead code in a shell script, and pinning a port against a case the twin does not run would demand coverage of something nothing covers. Requiring both halves is also how this notices a twin whose bottom-of-file call list lost an entry.

    A CALL IS NOT ALWAYS A BARE NAME ON ITS OWN LINE, and requiring that was a hole that failed OPEN. This predicate was a bare-name-on-its-own-line match, so a twin invoking its cases as `test_mapping_form_is_caught "$D/mapping"` or `with_temp_dir test_flags_runner` matched nothing at all. Measured 2026-09-07 across the 130 twins that declare cases: 43 had at least one case
    invisible here, and 16 saw ZERO. A twin seeing zero does not fail; it falls through to the flat-twin floor (the twin's runtime `PASS:` count), so the SET comparison this module exists to perform silently did not happen for those 16, `test-ci-parity.sh` (22 cases) among them.

    The two error directions are not symmetric, which is why widening is right. Over-admitting demands the port cover a case the twin does not run: noisy, and it fails CLOSED. Under-admitting drops the set check entirely and fails OPEN. So a name is called when it appears as a WORD on any line that is neither its own declaration nor a whole-line comment.

    Widening was checked against the ports before landing: it adds zero newly-required cases that any of the 53 current ports lacks, so it strengthens the check without reclassifying existing work.
    """
    declared = set(BASH_FN_RE.findall(twin_source))
    lines = twin_source.splitlines()
    called = set()
    for name in declared:
        declaration = re.compile(r"^\s*%s\(\)" % re.escape(name))
        word = re.compile(r"(?<![A-Za-z0-9_])%s(?![A-Za-z0-9_])" % re.escape(name))
        for line in lines:
            if declaration.match(line) or re.match(r"^\s*#", line):
                continue
            if word.search(line):
                called.add(name)
                break
    return called


def run_port(module_path: pathlib.Path, ledger: pathlib.Path, timeout: int):
    """(returncode, control count) for the ported module, run on its own.

    A SUBPROCESS and not an in-process re-run: the module is already being collected by the outer session, and re-entering it here would double every side effect and make the ledger a sum of two runs.

    NO `-p no:cacheprovider`, and the reason is a trap worth writing down. Disabling that plugin UNREGISTERS the `cache_dir` ini key, and this repo's pyproject sets both `cache_dir` and `--strict-config`; the nested pytest then exits 4 with "Unknown config option: cache_dir" and collects nothing. It was found by this very test refusing to call that a pass, which is the whole
    argument for comparing verdicts rather than trusting a green. The nested run therefore shares the outer run's cache directory, which is gitignored and per-worktree already.
    """
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", str(module_path)],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(paths.repo_root()),
        env={**os.environ, harness.LEDGER_ENV: str(ledger)},
        timeout=timeout,
    )
    rows = []
    if ledger.is_file():
        rows = [
            json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines() if line
        ]
    return proc, len([r for r in rows if r.get("event") == "pass"])


def test_the_registry_is_not_empty(gate):
    """ANTI-VACUITY. Zero ported modules means the parametrize below compared nothing, and an empty parametrize is green."""
    if not MODULES:
        gate.log_fail(
            "no ported gate module under %s declares a BASH_TWIN. Either the glob %r "
            "stopped matching or the ports were removed; either way the parity "
            "comparison below ran against nothing and its green means nothing."
            % (paths.relative_to_root(HERE), MODULE_GLOB)
        )
    for _name, _path, twin, _timeout in MODULES:
        if not paths.from_root(*twin.split("/")).is_file():
            gate.log_fail("BASH_TWIN %s does not exist; the parity claim cannot be made" % twin)
    gate.log_pass(
        "%d ported module(s) declare a twin, and every twin file exists: %s"
        % (len(MODULES), ", ".join(name for name, _, _, _ in MODULES))
    )


class _Stub:
    """A module-shaped object. `group_for` reads attributes, so this is the same input shape the real thing gets -- see `test_xdist_groups.py`, which stubs the identical way."""

    def __init__(self, **attrs):
        for k, v in attrs.items():
            setattr(self, k, v)


def test_a_changed_hash_forces_a_re_drive_and_an_unchanged_one_does_not(gate, tmp_path):
    """The skip's whole contract, in both directions.

    THIS IS THE CONTROL THE SKIP WAS NOT ALLOWED TO LAND WITHOUT. A reuse rule that is too eager stops proving a differential that has changed -- silently, and reported as a pass. Every clause that can defeat a reuse is therefore shown defeating one, and the permissive case is shown permitting.
    """
    led = tmp_path / "obs.jsonl"

    def row(**kw):
        base = {"subject": "s", "twin_sha": "a" * 16, "port_sha": "b" * 16, "agreed": True}
        base.update(kw)
        led.write_text(
            (led.read_text(encoding="utf-8") if led.exists() else "")
            + json.dumps(base, separators=(",", ":"))
            + "\n",
            encoding="utf-8",
        )

    gate.assert_eq(
        may_reuse("s", "a" * 16, "b" * 16, led), False, "no ledger at all proves nothing"
    )
    gate.ok("control: a missing ledger never licenses a skip")

    row()
    gate.assert_eq(may_reuse("s", "a" * 16, "b" * 16, led), True, "an agreed pair is reusable")
    gate.ok("an unchanged pair does NOT force a re-drive")

    # THE TWO THAT MATTER MOST: either side moving must bring the drive back.
    gate.assert_eq(
        may_reuse("s", "c" * 16, "b" * 16, led), False, "a changed TWIN forces a re-drive"
    )
    gate.assert_eq(
        may_reuse("s", "a" * 16, "c" * 16, led), False, "a changed PORT forces a re-drive"
    )
    gate.ok("control: a changed hash on either side forces the full differential")

    gate.assert_eq(may_reuse("other", "a" * 16, "b" * 16, led), False, "rows are per-subject")
    gate.ok("control: one subject's agreement does not cover another's")

    # AN EMPTY DIGEST is what `_digest` returns for a file it cannot read, and
    # "" == "" would otherwise make two unreadable files look like a match.
    row(twin_sha="", port_sha="")
    gate.assert_eq(may_reuse("s", "", "", led), False, "an unreadable side is never reusable")
    gate.ok("control: an empty digest cannot satisfy the key")

    # LAST ROW WINS. An append-only ledger keeps Monday's agreement after Tuesday's divergence, and "has it ever agreed" is the wrong question.
    led.unlink()
    row()
    row(agreed=False)
    gate.assert_eq(
        may_reuse("s", "a" * 16, "b" * 16, led), False, "a later disagreement supersedes"
    )
    gate.ok("control: a recorded disagreement revokes an earlier agreement")

    # A CORRUPT LINE means the ledger cannot answer, not that it answers yes. THE GOOD ROW ABOVE IT IS THE POINT, and its absence made this control vacuous on the first attempt: with only a corrupt line in the file, a rule that skipped the line still found nothing and still refused, so the control passed against the mutant. A truncated write lands AFTER earlier rows, and skipping
    # it hands back a stale agreement -- which is the failure.
    led.unlink()
    row()
    led.write_text(
        led.read_text(encoding="utf-8") + '{"subject": "s", not json\n', encoding="utf-8"
    )
    gate.assert_eq(may_reuse("s", "a" * 16, "b" * 16, led), False, "a corrupt ledger is no proof")
    gate.ok("control: an unparseable row refuses rather than returning the row above it")

    # THE OFF SWITCH, driven for real through the environment.
    led.unlink()
    row()
    os.environ[ALWAYS_DRIVE_ENV] = "1"
    try:
        gate.assert_eq(
            may_reuse("s", "a" * 16, "b" * 16, led),
            False,
            "%s=1 forces the drive" % ALWAYS_DRIVE_ENV,
        )
    finally:
        del os.environ[ALWAYS_DRIVE_ENV]
    gate.assert_eq(may_reuse("s", "a" * 16, "b" * 16, led), True, "and unsetting it restores reuse")
    gate.ok("control: the escape hatch works in both directions")

    gate.tally_finish("parity ledger reuse")


def test_record_parity_writes_a_hash_keyed_row_and_never_raises(gate, tmp_path, monkeypatch):
    """The ledger's two claims, neither of which was controlled when it landed.

    IT MUST KEY ON BOTH SIDES. A future skip reads these hashes to decide whether a differential still needs re-proving; a row that pinned only one side would
    let a change on the other go unnoticed, which is the exact hole the skip must
    not have. So the control changes each side in turn and requires the key to move -- and requires the OTHER side's key to hold, because a digest that moved for both would prove nothing about which side it tracks.

    AND IT MUST NEVER RAISE. A ledger that can fail a parity test turns a bookkeeping problem into what reads as a behavioural divergence, the confusion this whole module exists to prevent. `record_parity` swallows everything; nothing asserted that until now, so the `except` was as unfalsifiable as the controls this gate estate keeps finding.

    THE LEDGER IS REDIRECTED, NOT MOCKED. `paths.from_root` is repointed at `tmp_path`, so the real writer runs -- its `mkdir`, its `open("a")`, its JSON -- against a scratch root. A fake writer would control the test's own code.
    """
    twin_rel = "scripts/twin.sh"
    twin = tmp_path / "scripts" / "twin.sh"
    twin.parent.mkdir(parents=True, exist_ok=True)
    twin.write_text("echo one\n", encoding="utf-8")
    port = tmp_path / "port.py"
    port.write_text("x = 1\n", encoding="utf-8")
    ledger = tmp_path.joinpath(*LEDGER_REL.split("/"))

    monkeypatch.setattr(paths, "from_root", tmp_path.joinpath)

    record_parity("subject", twin_rel, port, agreed=True)
    rows = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines()]
    gate.assert_eq(len(rows), 1, "one call appends exactly one row")
    first = rows[0]
    gate.assert_eq(sorted(first), ["agreed", "at", "port_sha", "subject", "twin", "twin_sha"])
    gate.assert_eq(first["agreed"], True, "the verdict is carried as a bool")
    gate.assert_eq(len(first["twin_sha"]), 16, "the twin side is keyed")
    gate.assert_eq(len(first["port_sha"]), 16, "and so is the port side")
    gate.ok("a row names both sides of the pair")

    twin.write_text("echo two\n", encoding="utf-8")
    record_parity("subject", twin_rel, port, agreed=True)
    second = json.loads(ledger.read_text(encoding="utf-8").splitlines()[1])
    gate.assert_eq(second["twin_sha"] != first["twin_sha"], True, "a changed twin moves its key")
    gate.assert_eq(second["port_sha"], first["port_sha"], "and leaves the port's key alone")
    gate.ok("control: the twin side is tracked independently")

    port.write_text("x = 2\n", encoding="utf-8")
    record_parity("subject", twin_rel, port, agreed=False)
    third = json.loads(ledger.read_text(encoding="utf-8").splitlines()[2])
    gate.assert_eq(third["port_sha"] != second["port_sha"], True, "a changed port moves its key")
    gate.assert_eq(third["twin_sha"], second["twin_sha"], "and leaves the twin's key alone")
    gate.assert_eq(third["agreed"], False, "a disagreement is recorded as one")
    gate.ok("control: the port side is tracked independently")

    # UNREADABLE SIDE. A deleted twin must degrade to "cannot key this" rather than to a crash inside a test that is measuring something else.
    twin.unlink()
    record_parity("subject", twin_rel, port, agreed=True)
    fourth = json.loads(ledger.read_text(encoding="utf-8").splitlines()[3])
    gate.assert_eq(fourth["twin_sha"], "", "a missing file keys to empty, not an exception")
    gate.ok("control: an absent side does not raise")

    # UNWRITABLE LEDGER, driven for real: /proc rejects the mkdir. If the swallow is ever removed this line raises and the test says so.
    monkeypatch.setattr(paths, "from_root", pathlib.Path("/proc/1").joinpath)
    record_parity("subject", twin_rel, port, agreed=True)
    gate.ok("control: a ledger that cannot be written is swallowed, not raised")

    gate.tally_finish("parity ledger")


def test_the_real_tree_opt_in_still_discriminates(gate):
    """CONTROL-FIRST for `real_tree_admission`. An opt-in that admits everything is the blanket refusal inverted, which is strictly worse than the refusal: it would let an unisolated twin race the battery while reporting green."""
    unsafe = {"test-writes.sh"}
    writer = ".ci/scripts/test/gates/test-writes.sh"
    quiet = ".ci/scripts/test/gates/test-quiet.sh"

    gate.assert_eq(
        real_tree_admission(_Stub(BASH_TWIN=quiet), quiet, unsafe),
        None,
        "a twin outside the real-tree set needs no declaration",
    )
    gate.ok("clean: an ordinary twin is admitted with no opt-in")

    why = real_tree_admission(_Stub(BASH_TWIN=writer), writer, unsafe)
    gate.assert_contains(str(why), REAL_TREE_ATTR, "a real-tree twin with no opt-in is refused")
    gate.ok("control: a real-tree twin without the declaration is refused")

    gate.assert_eq(
        real_tree_admission(_Stub(BASH_TWIN=writer, REAL_TREE_TWIN=True), writer, unsafe),
        None,
        "declared AND grouped is admitted",
    )
    gate.ok("clean: declared, and it lands in the real-tree group")

    # THE ONE THAT MAKES THE OPT-IN MEAN SOMETHING. An XDIST_GROUP of its own wins in `group_for`, so the module is NOT serialised against the battery even though it claims to be. A one-condition check would admit this.
    why = real_tree_admission(
        _Stub(BASH_TWIN=writer, REAL_TREE_TWIN=True, XDIST_GROUP="something-else"), writer, unsafe
    )
    gate.assert_contains(
        str(why), "does not land in", "the declaration is checked against grouping"
    )
    gate.ok("control: declaring it while overriding the group is refused")

    why = real_tree_admission(_Stub(BASH_TWIN=quiet, REAL_TREE_TWIN=True), quiet, unsafe)
    gate.assert_contains(str(why), "NOT in the real-tree set", "over-claiming is refused too")
    gate.ok("control: declaring it for a twin that does not need it is refused")

    gate.tally_finish("real-tree opt-in")


def test_no_ported_twin_is_a_real_tree_writer_or_scanner(gate):
    """A twin driven from here must be fixture-isolated. See `real_tree_tests`."""
    unsafe = real_tree_tests()
    # ANTI-VACUITY, and it is the whole check: an empty set would make the loop below pass for every module forever. A lock that has gone quiet, or has stopped parsing, is exactly the state this refusal must not be satisfied by -- and it is the ONLY source now that the shell runner's `*_FALLBACK` arrays have been retired, so nothing else is left to keep the answer honest.
    if not unsafe:
        gate.log_fail(
            "gates.lock.json names not a single real-tree test, so the refusal below "
            "would admit every twin including the four that rewrite tracked files. "
            "Fix the reader before trusting this."
        )
    problems = []
    opted_in = 0
    for name, _path, twin, _t in MODULES:
        module = MODULE_OBJECTS.get(name)
        if module is None:
            continue
        why = real_tree_admission(module, twin, unsafe)
        if why:
            problems.append("%s %s" % (name, why))
        elif getattr(module, REAL_TREE_ATTR, False):
            opted_in += 1
    if problems:
        gate.log_fail(
            "%d real-tree admission problem(s):\n  %s" % (len(problems), "\n  ".join(problems))
        )
    gate.log_pass(
        "all %d ported twin(s) are admissible against the %d real-tree test(s) the "
        "lock declares; %d opted in via %s and land in %r"
        % (len(MODULES), len(unsafe), opted_in, REAL_TREE_ATTR, xdist_groups.REAL_TREE_GROUP)
    )


# NOT `*.observations.jsonl`, AND THE SUFFIX IS THE WHOLE REASON. That glob is enumerated by `scripts/lib/shadow-gate.ts`, which reads every file matching it as a SHADOW PAIR ledger and expects a `tree` field on every row. This file is a parity ledger, not a shadow pair -- there is no `twin-parity` gate pair to assert -- so occupying the glob made the standing shadow sweep report
# `RED twin-parity` on a file that is working exactly as intended. Measured 2026-09-08: `shadow-gate.ts --pair twin-parity --assert` died at :1085 with `TypeError: Cannot read properties of undefined (reading 'clean')`.
#
# The SHAPE still mirrors those files deliberately, so a future skip has a precedent to follow. Sharing a directory is fine; answering someone else's glob is not.
LEDGER_REL = ".ci/shadow/twin-parity.ledger.jsonl"


def _digest(path: pathlib.Path) -> str:
    """16 hex of sha256, or "" when the file is unreadable."""
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()[:16]
    except OSError:
        return ""


ALWAYS_DRIVE_ENV = "TWIN_PARITY_ALWAYS_DRIVE"


def ledger_path(ledger: pathlib.Path | None = None) -> pathlib.Path:
    return ledger if ledger is not None else paths.from_root(*LEDGER_REL.split("/"))


def last_agreement(name: str, ledger: pathlib.Path | None = None) -> dict | None:
    """The LAST row for `name`, or None. Later rows supersede earlier ones.

    LAST, NOT ANY. A subject that agreed on Monday and diverged on Tuesday must not be skippable because Monday's row is still in the file; the ledger is append-only, so "has it ever agreed" is the wrong question and "what did it do most recently" is the right one.
    """
    path = ledger_path(ledger)
    found = None
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except ValueError:
                # A CORRUPT LINE IS NOT A LICENCE TO SKIP. Skipping it and reading on would let a truncated write hand back an older agreement; the conservative reading is that this ledger cannot be trusted to answer, so nothing is reused.
                return None
            if isinstance(row, dict) and row.get("subject") == name:
                found = row
    except OSError:
        return None
    return found


def may_reuse(name: str, twin_sha: str, port_sha: str, ledger: pathlib.Path | None = None) -> bool:
    """True when this exact pair has already been PROVEN equal, so re-driving it would re-prove a differential nothing has changed.

    THE TRADE-OFF, STATED WHERE IT IS MADE. `check:ci-pytest` costs 1879s and 1661s of that is one subject -- `test-claude-hooks` -- driving its twin and its port serially inside one test. Reusing an agreement makes that cost land once per CHANGE instead of once per COMMIT. What is given up is real: a commit touching neither side no longer re-proves their equality, so a divergence
    caused by something OUTSIDE both files (an interpreter bump, a changed shared helper, an environment difference) survives longer before a run notices it. The key covers only the two files it hashes.

    THREE THINGS DEFEAT IT, each for its own reason:
      * no row, or an unreadable/corrupt ledger -- nothing has been proven.
      * `agreed` false -- a recorded DISAGREEMENT must never license a skip.
      * either digest empty -- `_digest` returns "" for a file it cannot read,
        and "" == "" would otherwise make two unreadable files look identical.

    And `TWIN_PARITY_ALWAYS_DRIVE=1` turns the whole thing off, which is the
    seam for anyone who wants the full differential back without editing code.
    """
    if os.environ.get(ALWAYS_DRIVE_ENV):
        return False
    if not twin_sha or not port_sha:
        return False
    row = last_agreement(name, ledger)
    if row is None or row.get("agreed") is not True:
        return False
    return row.get("twin_sha") == twin_sha and row.get("port_sha") == port_sha


def record_parity(name: str, twin: str, module_path: pathlib.Path, agreed: bool) -> None:
    """Append one observation keyed by the sha256 of BOTH sides.

    RECORDING ONLY. This does NOT skip anything, and that restraint is the whole point of landing it now. The expensive half of `check:ci-pytest` is one subject re-proving a differential it has already proven -- `test-claude-hooks` costs 1661s of a 1879s run because parity drives its twin and its port serially inside one test. Skipping on a hash match would fix that, and it is ALSO
    a coverage decision: it means CI stops re-proving parity on commits that touch neither side. That call is the operator's and is parked as a worklist deferral, so this lays the evidence and stops short of acting on it.

    The shape deliberately mirrors `.ci/shadow/*.observations.jsonl`, which already answers the same question for the quality gates -- "has this pair been proven equivalent, and against which trees" -- so a future skip has a precedent to follow rather than a new mechanism to invent.

    NEVER RAISES. A ledger that can fail a parity test would make a bookkeeping problem look like a behavioural divergence, which is precisely the confusion this module exists to prevent.
    """
    try:
        row = {
            "at": datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "subject": name,
            "twin": twin,
            "twin_sha": _digest(paths.from_root(*twin.split("/"))),
            "port_sha": _digest(module_path),
            "agreed": bool(agreed),
        }
        led = paths.from_root(*LEDGER_REL.split("/"))
        led.parent.mkdir(parents=True, exist_ok=True)
        with led.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, separators=(",", ":")) + "\n")
    except Exception:  # noqa: BLE001 - bookkeeping must never fail a verdict
        pass


@pytest.mark.parametrize(
    ("name", "module_path", "twin", "twin_timeout"), MODULES, ids=[m[0] for m in MODULES]
)
def test_port_and_twin_agree(gate, tmp_path, name, module_path, twin, twin_timeout):
    twin_path = paths.from_root(*twin.split("/"))

    # THE LEDGER IS READ BEFORE ANYTHING IS DRIVEN. Reused or not, the decision is PRINTED, because a gate that quietly stops doing most of its work is the "green that hides how much ran" this estate exists to refuse.
    #
    # NOT `pytest.skip()`, DELIBERATELY. `check_pytest.py`'s verdict refuses a run
    # where `passed != collected`, so a skipped case would red the gate it is
    # meant to speed up. The case passes on the strength of the recorded agreement and says so.
    twin_sha, port_sha = _digest(twin_path), _digest(module_path)
    if may_reuse(name, twin_sha, port_sha):
        gate.log_pass(
            "%s: REUSED a recorded agreement -- twin %s and port %s are byte-identical "
            "to the pair last proven equal, so neither was re-driven. Set %s=1 to force "
            "the full differential." % (name, twin_sha, port_sha, ALWAYS_DRIVE_ENV)
        )
        return
    # A TIMEOUT IS A VERDICT HERE, NOT AN ERROR. `subprocess.run(timeout=)`
    # raises, and an escaping `TimeoutExpired` arrives as a traceback in the parity driver rather than as a statement about the subject -- so the first thing a reader learns is that the harness broke, not that the twin is too slow to be driven this way. Caught on BOTH sides, because a port that hangs and a twin that is merely long are different findings and the message has to say
    # which.
    try:
        twin_run = harness.run(["bash", str(twin_path)], timeout=twin_timeout)
    except subprocess.TimeoutExpired:
        gate.log_fail(
            "TWIN TIMED OUT for %s: %s did not finish in %ds, so NO verdict was "
            "reached and this comparison proves nothing. If the twin is legitimately "
            "this slow, declare `TWIN_TIMEOUT = <seconds>` beside `BASH_TWIN` in %s "
            "(capped at %ds). If it is not, the twin hangs and that is the finding."
            % (name, twin, twin_timeout, module_path.name, MAX_TWIN_TIMEOUT)
        )
    twin_passes = len(PASS_LINE_RE.findall(ANSI_RE.sub("", twin_run.out)))

    try:
        port_proc, port_controls = run_port(module_path, tmp_path / "ledger.jsonl", twin_timeout)
    except subprocess.TimeoutExpired:
        gate.log_fail(
            "PORT TIMED OUT for %s: the nested pytest did not finish in %ds while the "
            "twin did. The port is slower than the subject it replaces, which is a "
            "regression in the port, not a reason to raise `TWIN_TIMEOUT`." % (name, twin_timeout)
        )

    twin_green = twin_run.rc == 0
    port_green = port_proc.returncode == 0
    if twin_green != port_green:
        gate.log_fail(
            "VERDICT DIVERGED for %s: the twin %s (rc=%d) and the port %s (rc=%d) on the "
            "same tree. A port that changes a verdict is a regression, not a migration.\n"
            "--- twin stdout ---\n%s\n--- twin stderr ---\n%s\n"
            "--- port stdout ---\n%s\n--- port stderr ---\n%s"
            % (
                name,
                "passed" if twin_green else "FAILED",
                twin_run.rc,
                "passed" if port_green else "FAILED",
                port_proc.returncode,
                twin_run.out,
                twin_run.err,
                port_proc.stdout,
                port_proc.stderr,
            )
        )
    gate.log_pass("%s: twin and port agree (both %s)" % (name, "green" if twin_green else "red"))

    cases = bash_cases(twin_path.read_text(encoding="utf-8"))
    ported = set(PY_FN_RE.findall(module_path.read_text(encoding="utf-8")))
    if cases:
        missing = sorted(cases - ported)
        if missing:
            gate.log_fail(
                "%s dropped %d case(s) the twin runs: %s. Port them or say in the module "
                "docstring why the case cannot exist in Python; do not let the total "
                "hide the composition." % (name, len(missing), ", ".join(missing))
            )
        gate.log_pass(
            "%s: all %d twin case(s) are present in the port (%d test(s) total)"
            % (name, len(cases), len(ported))
        )
    else:
        # A FLAT TWIN has no case set, so the floor is its runtime PASS count.
        if port_controls < twin_passes:
            gate.log_fail(
                "%s is a flat twin printing %d PASS line(s), but the port recorded only "
                "%d control(s). A flat script has no case names to compare, so the only "
                "floor available is the twin's own output, and the port is under it."
                % (name, twin_passes, port_controls)
            )
        gate.log_pass(
            "%s: flat twin printed %d PASS line(s); the port recorded %d control(s)"
            % (name, twin_passes, port_controls)
        )

    # The shape, printed on every run so a collapse is visible rather than silent.
    gate.log_info(
        "%s: twin rc=%d passes=%d | port rc=%d controls=%d tests=%d"
        % (name, twin_run.rc, twin_passes, port_proc.returncode, port_controls, len(ported))
    )
    # Reached only when every refusal above declined to fire, so `agreed=True` is
    # the verdict this run actually produced rather than an assumption about it.
    record_parity(name, twin, module_path, agreed=True)
