"""Port of `.ci/scripts/test/gates/test-docs-gen.sh`.

Subject: `scripts/gen-docs.ts`, the documentation generator, proved in both
directions.

WHY IT NEEDS A GATE AT ALL. The generator exists because hand-typed registry
numbers go stale in silence: `.dead-bash-allowlist` said "the 17 gate scripts"
against 131, `check-ci-parity.ts` said "runs 57 gate tests", and
`docs/agent-reference/ci-gates.md` said "254 fast gates" against a live 312. A
generator that quietly stops generating puts the tree straight back into that
state, and the symptom -- a document that looks fine -- is invisible.

WHAT IS PROVED, and why each case is here rather than assumed:

  A. verify is GREEN on the tree as it stands. On its own this proves nothing,
     because a generator with no targets, or one that silently renders nothing, is
     also green. Hence B through E.
  B. verify goes RED when one generated row is perturbed. THE CONTROL. Without it,
     A is a check that cannot fail. The perturbation is restored, and the restore
     is itself asserted.
  C. two `--write` runs are byte-identical. Determinism is not a nicety here:
     verify compares rendered text against a file, so a render that reorders on a
     whim reds on noise and teaches everyone to run `--write` without reading.
     Note the ORDERING -- A runs first, so by the time C writes, the write is
     provably a no-op.
  D. `--selftest` passes AND still contains its planted-defect controls by name.
     Asserting the exit code alone would keep passing after someone deletes the
     controls; asserting the labels is what makes D non-vacuous.
  E. the pre-port SET snapshot is present and well-formed. It is the only
     instrument that can catch a port silently dropping rows, and it is worthless
     if it is absent, truncated, or quietly re-baselined.

WHAT IS DELIBERATELY NOT ASSERTED: that the live sets still equal the snapshot.
They are SUPPOSED to diverge as the ports land; `--diff-snapshot` is where that
comparison belongs, run by the wave that does the porting.

THE TWIN IS FLAT -- it declares no `test_*()` functions -- so `test_twin_parity.py`
has no case set to compare and falls back to the twin's runtime `PASS:` count as
the floor on this port's recorded controls. The five cases below are therefore
split so that each of the twin's six PASS lines has a control of its own, plus the
two the port adds.

WHY THIS MODULE OPTS IN TO THE REAL-TREE GROUP, and it is the sharpest reason in
the batch. Case B WRITES a perturbation into `scripts/data/doc-registry.md` and
case C runs `--write`, which rewrites every discovered region in every `.md` file
in the repository -- `CLAUDE.md` among them. The lock records
`mutex: ["tree:repo"]` for `gate-test:docs-gen` for exactly that. Two of these
running at once, or one running beside a gate that reads those files, is a
corruption rather than a flake. `REAL_TREE_TWIN = True` buys the serialisation,
and it is honoured only because this module names no `XDIST_GROUP` of its own.

THE `--write` IS SAFE ONLY BECAUSE A IS ASSERTED FIRST, and that ordering is
load-bearing rather than stylistic: a green verify means the rendered text already
equals the file, so `--write` cannot change a byte. `assert_targets_unchanged`
makes that a claim rather than an assumption by digesting every target before and
after.
"""

import contextlib
import hashlib
import json
import pathlib

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

BASH_TWIN = ".ci/scripts/test/gates/test-docs-gen.sh"

# Case B perturbs a tracked file and case C runs `--write`. See the docstring.
REAL_TREE_TWIN = True

ROOT = paths.repo_root()
GEN = ROOT / "scripts" / "gen-docs.ts"
TARGET = ROOT / "scripts" / "data" / "doc-registry.md"
SNAPSHOT = ROOT / "scripts" / "data" / "doc-registry-preport.json"

# The named controls `--selftest` must still be running. NAMED, not counted: a count survives someone deleting one control and adding another.
SELFTEST_CONTROLS = (
    "planted: an unterminated region is refused",
    "planted: a nested region is refused",
    "planted: a close with no open is refused",
    "planted: an unknown provider is refused",
    "planted: a perturbed row makes the rewrite differ",
    "but the SET diff names all 88 dropped rows",
    "a count floor of 300 PASSES",
)


def gen(*args: str) -> harness.RunResult:
    npx = harness.require_tool("npx", "install node (the lane's setup-workspace step provides it)")
    return harness.run([npx, "tsx", str(GEN), *args], cwd=ROOT, timeout=900)


def require_inputs(gate) -> None:
    """Three files, each of which makes every case below meaningless if absent."""
    for path, why in (
        (GEN, "the generator is gone"),
        (TARGET, "nothing carries a region"),
        (SNAPSHOT, "the pre-port SET record is gone"),
    ):
        if not path.is_file():
            gate.log_fail("%s is missing; %s" % (paths.relative_to_root(path), why))


def digest(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def region_targets() -> list[pathlib.Path]:
    """Every `.md` file `--write` could rewrite, discovered the way the generator
    discovers them: a real marker line, not a mention of one.

    THIS IS WHAT MAKES THE `--write` CASES AUDITABLE. Digesting only
    `doc-registry.md` would miss `CLAUDE.md`, which the same run rewrites, so a
    non-deterministic render there would go unnoticed by a test that claims to
    prove determinism.
    """
    git = harness.require_tool("git", "install git; the generator enumerates through git")
    proc = harness.run(
        [git, "ls-files", "--cached", "--others", "--exclude-standard", "-z", "--", "*.md"],
        cwd=ROOT,
        timeout=300,
    )
    if proc.rc != 0:
        raise harness.GateAssertionError(
            "`git ls-files` failed (rc=%d), so the target set could not be enumerated and "
            "the byte-identity claims below would be about nothing" % proc.rc
        )
    found = []
    for rel in proc.out.split("\0"):
        if not rel:
            continue
        path = ROOT / rel
        try:
            if not path.is_file() or path.stat().st_size > 4 * 1024 * 1024:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line in text.split("\n"):
            if line.lstrip().startswith("<!-- >>> gen-docs:"):
                found.append(path)
                break
    return found


@contextlib.contextmanager
def assert_targets_unchanged(gate, label: str):
    """Digest every region target, run the body, and require byte-identity.

    A `--write` after a green verify cannot change a byte, and this turns that
    from a belief into a measurement -- across every file the generator can touch,
    not just the one this test names.
    """
    targets = region_targets()
    if not targets:
        gate.log_fail(
            "no `.md` file carries a gen-docs region, so this whole gate is about an empty "
            "target set and its green would mean nothing"
        )
    before = {path: digest(path) for path in targets}
    yield targets
    moved = sorted(paths.relative_to_root(path) for path in targets if digest(path) != before[path])
    if moved:
        gate.log_fail(
            "%s changed %d generated file(s) that verify had just called clean: %s"
            % (label, len(moved), ", ".join(moved))
        )


def perturb_first_row(gate, text: str) -> str:
    """Append a marker to the first data row of the first generated table.

    FOUND BY SHAPE, not by content, so this control survives every rewording of
    every provider: the row after a `|---` separator that itself follows a `| `
    header.
    """
    lines = text.split("\n")
    for index, line in enumerate(lines):
        if (
            line.startswith("| ")
            and not line.startswith("|---")
            and index + 1 < len(lines)
            and lines[index + 1].startswith("|---")
            and index + 2 < len(lines)
        ):
            lines[index + 2] = lines[index + 2] + " <!-- PERTURBED -->"
            return "\n".join(lines)
    gate.log_fail("no generated table row found to perturb; the control could not be planted")
    raise AssertionError  # unreachable: log_fail raises


# ---------------------------------------------------------------------------


def test_verify_accepts_the_tree_as_it_stands(gate):
    """A. And it must have named at least one target, or the green is vacuous."""
    require_inputs(gate)
    result = gen()
    if result.rc != 0:
        gate.log_error(result.err.strip())
        gate.log_fail(
            "gen-docs verify failed. If a provider's inputs changed, run: "
            "npx tsx scripts/gen-docs.ts --write"
        )
    ok_lines = [line for line in result.out.split("\n") if line.startswith("ok ")]
    if not ok_lines:
        gate.log_fail("verify passed while reporting no target at all -- vacuous")
    gate.log_pass("A. verify is green and named %d target(s)" % len(ok_lines))


def test_a_perturbed_row_is_reported_as_drift(gate):
    """B. THE CONTROL, and the restore is asserted rather than trusted.

    A killed run must not leave a perturbed row behind: the next verify would red,
    which is the safe direction, but the finding would name a defect nobody
    introduced. So the original bytes are captured first and written back in a
    `finally`, and the file's digest is compared afterwards.
    """
    require_inputs(gate)
    original = TARGET.read_bytes()
    before = hashlib.sha256(original).hexdigest()
    try:
        TARGET.write_text(perturb_first_row(gate, original.decode("utf-8")), encoding="utf-8")
        result = gen()
        if result.rc == 0:
            gate.log_fail("CONTROL DID NOT FIRE: verify passed over a perturbed generated row")
        gate.assert_contains(
            result.err, "DRIFT", "verify failed but never said DRIFT: %s" % result.err.strip()
        )
        gate.assert_contains(
            result.err, "doc-registry.md", "the drift report did not name the file"
        )
        gate.log_pass("B. a single perturbed row is reported as DRIFT and exits non-zero")
    finally:
        TARGET.write_bytes(original)
    if digest(TARGET) != before:
        gate.log_fail("restore failed -- the target is not what it was")
    restored = gen()
    if restored.rc != 0:
        gate.log_fail("verify is still red after restoring the target: %s" % restored.err.strip())
    gate.log_pass("B. restored, and verify is green again")


def test_two_write_runs_are_byte_identical(gate):
    """C. Determinism AND idempotence, in one measurement.

    `test_verify_accepts_the_tree_as_it_stands` has already established that the
    render equals the file, so BOTH writes must be no-ops. Anything else is either
    a non-deterministic provider or a verify that lied.
    """
    require_inputs(gate)
    with assert_targets_unchanged(gate, "--write") as targets:
        before = digest(TARGET)
        first = gen("--write")
        if first.rc != 0:
            gate.log_fail("first --write failed: %s" % first.err.strip())
        one = digest(TARGET)
        second = gen("--write")
        if second.rc != 0:
            gate.log_fail("second --write failed: %s" % second.err.strip())
        two = digest(TARGET)
        gate.assert_eq(one, two, "two --write runs disagree -- the render is not deterministic")
        gate.assert_eq(one, before, "--write changed a file that verify had just called clean")
    gate.log_pass(
        "C. --write is deterministic and idempotent across %d target(s) (%s)"
        % (len(targets), one[:16])
    )


def test_selftest_passes_and_still_plants_its_defects(gate):
    """D. The exit code alone would keep passing after someone deletes the
    controls; asserting the LABELS is what makes this non-vacuous."""
    require_inputs(gate)
    result = gen("--selftest")
    if result.rc != 0:
        gate.log_error(result.out)
        gate.log_fail("gen-docs --selftest failed")
    if any(line.startswith("FAIL") for line in result.out.split("\n")):
        gate.log_fail("--selftest exited 0 with FAIL lines in its output")
    for want in SELFTEST_CONTROLS:
        if want not in result.out:
            gate.log_fail("the selftest no longer runs the control: %s" % want)
    passes = len([line for line in result.out.split("\n") if line.startswith("PASS")])
    gate.log_pass(
        "D. --selftest is green with all %d named control(s) present (%d PASS lines)"
        % (len(SELFTEST_CONTROLS), passes)
    )


def test_the_preport_snapshot_is_recorded_and_well_formed(gate):
    """E. A snapshot that is absent, truncated or quietly re-baselined catches
    nothing, and the reasoning is part of the artifact: a snapshot whose file does
    not say WHY a set beats a count is a pile of strings the next reader will feel
    free to regenerate."""
    require_inputs(gate)
    try:
        snap = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    except ValueError as exc:
        gate.log_fail("the snapshot could not be parsed at all: %s" % exc)
        raise AssertionError from exc

    problems = []
    if snap.get("format") != 1:
        problems.append("format is %r, expected 1" % snap.get("format"))
    if not snap.get("recorded_at_commit"):
        problems.append("recorded_at_commit is empty")
    why = "\n".join(snap.get("why") or [])
    problems.extend(
        "the `why` block never mentions %s" % phrase
        for phrase in ("SET", "COUNT", "BEFORE")
        if phrase.lower() not in why.lower()
    )
    providers = snap.get("providers") or {}
    if len(providers) < 4:
        problems.append("only %d provider(s) recorded" % len(providers))
    for name, entry in sorted(providers.items()):
        keys = entry.get("keys") or []
        if not keys:
            problems.append("%s recorded ZERO rows -- a snapshot of nothing catches nothing" % name)
        if entry.get("rows") != len(keys):
            problems.append(
                "%s says %r rows but lists %d keys" % (name, entry.get("rows"), len(keys))
            )
        if len(set(keys)) != len(keys):
            problems.append("%s has duplicate keys, so it is not a set" % name)
        if keys != sorted(keys):
            problems.append(
                "%s keys are not in a fixed order, so two diffs are not comparable" % name
            )
    if problems:
        for problem in problems:
            gate.log_error("E. %s" % problem)
        gate.log_fail("the pre-port snapshot is malformed")
    gate.log_pass(
        "E. the pre-port snapshot is well-formed (%d provider(s), %d row(s))"
        % (len(providers), sum(len(e.get("keys") or []) for e in providers.values()))
    )


def test_the_write_target_set_is_wider_than_the_file_this_gate_names(gate):
    """ADDED BY THE PORT, and it names a hazard the twin leaves implicit.

    Cases B and C reason about `scripts/data/doc-registry.md`, but a single
    `--write` rewrites EVERY discovered region -- `CLAUDE.md` included. A reader of
    the twin could reasonably conclude the blast radius is one file. It is not, and
    a session running this gate should know that before it runs. Printing the set
    also makes a COLLAPSE visible: if the discovery ever narrowed to one file, the
    determinism claim above would silently shrink with it.
    """
    targets = region_targets()
    if len(targets) < 2:
        gate.log_fail(
            "only %d file(s) carry a gen-docs region; --write's determinism is then a claim "
            "about almost nothing, and the discovery has probably collapsed" % len(targets)
        )
    names = sorted(paths.relative_to_root(path) for path in targets)
    if paths.relative_to_root(TARGET) not in names:
        gate.log_fail(
            "%s carries no region any more, so cases B and C are perturbing and digesting a "
            "file the generator does not own" % paths.relative_to_root(TARGET)
        )
    gate.log_info("--write rewrites: %s" % ", ".join(names))
    gate.log_pass(
        "the write target set holds %d file(s), not just the one this gate names" % len(names)
    )
