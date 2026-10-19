"""The build-config hash in `rediacc_ci.ci.generate_tag`, both ways.

Ported from `.ci/scripts/test/gates/test-generate-tag-inputs.sh`, and since PLAN-retire-bash-oracles B3 it drives the Python module, because `.ci/scripts/ci/generate-tag.sh` is retired.

WHAT THE HASH IS FOR. `generate_tag --submodule private/renet` mints the tag that names ghcr.io/rediacc/renet. The Initialize step asks the registry whether that tag already exists and, if it does, sets `renet_exists=true`, which skips the 45-minute Renet (Full) build AND the image build. The tag is therefore a cache key, and `BUILD_CONFIG_FILES` is its input list: an input missing from the list means a changed build resolves to an existing tag and a stale image is served. An input in the list that does not exist must refuse the run, never narrow the hash.

WHAT BROKE. The list was consulted through `if [[ -f "$f" ]]` in the retired script, so a renamed or moved input was skipped in silence. The one visible symptom was a cache miss -- the surviving digests concatenate differently -- that nobody would investigate. The module refuses with exit 1 and prints nothing on stdout.

WHY A FIXTURE TREE. The module reads real files from the working directory, so the only way to plant a defect without touching a tracked file is to build a throwaway tree with the same shape and run the module inside it. Closure mode reads `git rev-parse HEAD:<path>`, so its fixture is a throwaway git repository holding every closure path, and the version component is moved by cutting a tag in that repository.

INTENTIONAL DELTA (Rule T): the retired script hashed `.ci/scripts/build/build-renet.sh`; the module hashes `.ci/rediacc_ci/build/build_renet.py`, the Python module that replaced it.
"""

import os
import pathlib
import re
import shutil

from rediacc_ci import paths
from rediacc_ci.ci import generate_tag
from rediacc_ci.tests.gates import harness

# Every path in BUILD_CONFIG_FILES, in the same order, relative to the tree root. Kept here so a list that grows without a test growing with it shows up in `test_declared_inputs_match_the_module` rather than going unnoticed.
DECLARED_INPUTS = (
    "private/renet/Dockerfile",
    "private/renet/Dockerfile.native",
    "private/renet/build.sh",
    ".github/workflows/ci-build-renet.yml",
    ".github/workflows/ci-build-docker.yml",
    ".ci/rediacc_ci/build/build_renet.py",
)

# The sibling that must NOT be an input.
INFRA_SIBLING = ".ci/scripts/infra/build-renet.sh"

TIME_TAG_RE = re.compile(r"^[0-9]{8}-[0-9]{6}$")
SUBMODULE_TAG_RE = re.compile(r"^[0-9a-f]+-[0-9a-f]{12}$")
CLOSURE_TAG_RE = re.compile(r"^rdc-[0-9a-f]{12}$")

GIT_IDENTITY = ["-c", "user.email=fixture@example.com", "-c", "user.name=fixture"]


def require_git() -> str:
    return harness.require_tool(
        "git", "install git; the module rev-parses a submodule to build the tag"
    )


def build_fixture_tree(gate, root: pathlib.Path) -> None:
    """A tree with the same shape as the repository root: the declared inputs, and a one-commit git repository at the submodule path."""
    git = require_git()
    if root.exists():
        shutil.rmtree(root)
    for rel in DECLARED_INPUTS:
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("seed content for %s\n" % rel, encoding="utf-8")
    # Present in the tree, as it is in the real repo, so "the tag did not change" below is about the LIST and not about a missing file.
    (root / INFRA_SIBLING).parent.mkdir(parents=True, exist_ok=True)
    (root / INFRA_SIBLING).write_text("seed content for infra\n", encoding="utf-8")

    # A real git repo at the submodule path: the module rev-parses it, and a fixed commit keeps the SUBMODULE_COMMIT half of the tag constant so every difference below is attributable to the build-config half.
    sub = root / "private" / "renet"
    harness.run([git, "-C", os.fspath(sub), "init", "-q", "."])
    # No detached maintenance after the commit: build_fixture_tree rmtree's this root and rebuilds it in a loop, and the child holds .git/objects/maintenance.lock past `commit` (see .claude/rediacc_hooks/tests/test_wl_scratch.py).
    for key, value in (("maintenance.auto", "false"), ("gc.auto", "0")):
        configured = harness.run([git, "-C", os.fspath(sub), "config", key, value])
        if configured.rc != 0:
            gate.log_fail(
                "could not set %s in the fixture submodule: %s" % (key, configured.err.strip())
            )
    harness.run([git, "-C", os.fspath(sub), "add", "-A"])
    result = harness.run(
        [git, "-C", os.fspath(sub), *GIT_IDENTITY, "commit", "-qm", "fixture"],
    )
    if result.rc != 0:
        gate.log_fail("could not commit the fixture submodule: %s" % result.err.strip())


def invoke(cwd: pathlib.Path, *args: str) -> harness.RunResult:
    """The real module, run from `cwd`. Streams are kept apart, as a caller reads stdout alone and stderr for the diagnostics."""
    return harness.run(
        ["python3", "-m", "rediacc_ci.ci.generate_tag", *args],
        cwd=cwd,
        env={"PYTHONPATH": os.fspath(paths.from_root(".ci")), "PYTHONDONTWRITEBYTECODE": "1"},
    )


def tag(gate, root: pathlib.Path) -> str:
    """The generated submodule tag; fails the case on an error."""
    result = invoke(root, "--submodule", "private/renet")
    if result.rc != 0:
        gate.log_fail(
            "generate_tag exited %s when a tag was expected: %s"
            % (harness.describe_exit(result.rc), result.err.strip())
        )
    return result.out.rstrip("\n")


# ---------------------------------------------------------------------------


def test_declared_inputs_match_the_module(gate):
    """Anti-vacuity, and the first thing to break if someone extends the list.

    Every case below is about DECLARED_INPUTS; if that drifts from the real BUILD_CONFIG_FILES, the per-input control proof silently stops covering the new entry.
    """
    actual = tuple(t.format(sub="private/renet") for t in generate_tag.BUILD_CONFIG_FILES)
    gate.assert_eq(
        actual,
        DECLARED_INPUTS,
        "BUILD_CONFIG_FILES has drifted from this test's list; add the new input here",
    )
    gate.log_pass("the %d declared inputs match BUILD_CONFIG_FILES exactly" % len(DECLARED_INPUTS))


def test_tag_is_deterministic(gate):
    """Baseline. Without it, "the tag changed" below proves nothing: it could change on every invocation."""
    with harness.temp_dir() as tmp:
        root = tmp / "repo"
        build_fixture_tree(gate, root)
        first = tag(gate, root)
        second = tag(gate, root)
        gate.assert_eq(second, first, "two runs over an unchanged tree must produce the same tag")
        gate.assert_contains(first, "-", "the tag must carry both halves (commit-confighash)")
        gate.log_pass("the tag is deterministic over an unchanged tree (%s)" % first)


def test_every_declared_input_changes_the_tag(gate):
    """THE CONTROL PROOF, one per entry. An entry that does not move the tag is decoration: it is in the list but not in the key, and a change to it would reuse a stale image. This is the assertion that would have caught a path pointed at the wrong build script."""
    with harness.temp_dir() as tmp:
        root = tmp / "repo"
        build_fixture_tree(gate, root)
        base = tag(gate, root)
        for rel in DECLARED_INPUTS:
            (root / rel).write_text("perturbed %s\n" % rel, encoding="utf-8")
            after = tag(gate, root)
            if after == base:
                gate.log_fail(
                    "editing %s did not change the tag: it is declared but not hashed" % rel
                )
            # Restore so each input is proven independently rather than cumulatively.
            (root / rel).write_text("seed content for %s\n" % rel, encoding="utf-8")
            gate.assert_eq(
                tag(gate, root), base, "restoring %s must return the tag to baseline" % rel
            )
        gate.log_pass(
            "each of the %d declared inputs independently changes the tag" % len(DECLARED_INPUTS)
        )


def test_infra_build_renet_is_not_an_input(gate):
    """The other direction, and the finding that prompted the gate. Nine CI steps build the dev renet through `rediacc_ci.infra.build_renet`, which is NOT in the list, correctly, because it compiles a binary for the local machine and does not affect the image. The case pins that decision, so the next reader gets the answer instead of re-deriving it, and a future decision to include it has to change this case deliberately."""
    with harness.temp_dir() as tmp:
        root = tmp / "repo"
        build_fixture_tree(gate, root)
        base = tag(gate, root)
        (root / INFRA_SIBLING).write_text("perturbed infra\n", encoding="utf-8")
        gate.assert_eq(
            tag(gate, root),
            base,
            "editing the infra build script must NOT change the renet image tag "
            "(it does not affect the image)",
        )
        gate.log_pass("the infra build script is deliberately outside the hash")


def test_missing_input_fails_loudly(gate):
    """THE REGRESSION. Before the fix this exited 0 and printed a tag: a DIFFERENT tag, because the remaining digests concatenate differently, so the only symptom was a cache miss nobody would investigate."""
    with harness.temp_dir() as tmp:
        root = tmp / "repo"
        build_fixture_tree(gate, root)
        tag(gate, root)
        (root / ".ci/rediacc_ci/build/build_renet.py").unlink()
        result = invoke(root, "--submodule", "private/renet")
        gate.assert_exit(
            1, result, "a missing declared input must fail the module, not narrow the hash"
        )
        gate.assert_contains(
            result.combined,
            "Build-config input not found",
            "with a diagnostic that names the failure",
        )
        gate.assert_contains(
            result.combined, ".ci/rediacc_ci/build/build_renet.py", "and names the missing path"
        )
        gate.log_pass("a missing declared input fails loudly instead of silently shrinking the key")


def test_missing_input_does_not_emit_a_tag(gate):
    """The specific shape of the old bug: the caller (`RENET_TAG=$(...)` in the Initialize step) captures stdout. Under the old behaviour it captured a plausible-looking tag computed from a narrowed key. Nothing may reach stdout on this path."""
    with harness.temp_dir() as tmp:
        root = tmp / "repo"
        build_fixture_tree(gate, root)
        (root / ".ci/rediacc_ci/build/build_renet.py").unlink()
        result = invoke(root, "--submodule", "private/renet")
        gate.assert_exit(1, result, "the failure must be visible in the exit code the caller sees")
        gate.assert_eq(
            result.out.rstrip("\n"), "", "no tag may be printed when an input is missing"
        )
        gate.log_pass("a missing input prints no tag, so a caller capturing stdout cannot use one")


def test_every_declared_input_is_individually_load_bearing_for_the_failure(gate):
    """Sweep the class: the guard must cover every entry, not just the one that prompted it. A guard that only checks the last element of a list is a classic partial fix."""
    with harness.temp_dir() as tmp:
        root = tmp / "repo"
        for rel in DECLARED_INPUTS:
            build_fixture_tree(gate, root)
            (root / rel).unlink()
            result = invoke(root, "--submodule", "private/renet")
            gate.assert_exit(1, result, "removing %s must fail the module" % rel)
            gate.assert_contains(result.combined, rel, "the diagnostic must name %s" % rel)
        gate.log_pass("all %d declared inputs are guarded, not just one" % len(DECLARED_INPUTS))


def test_other_modes_are_untouched(gate):
    """The guard lives in the `--submodule` branch. `--self` and the time-based default must keep working. Both modes are still reachable and still pinned here, because nothing else guards them and a silent regression in either would only surface as a mystery tag."""
    git = require_git()
    with harness.temp_dir() as tmp:
        root = tmp / "repo"
        build_fixture_tree(gate, root)
        # The nested fixture submodule makes git warn about an embedded repo; it is noise here, and the commit is only needed so --self has something to rev-parse.
        harness.run([git, "-C", os.fspath(root), "init", "-q", "."])
        harness.run([git, "-C", os.fspath(root), "add", "-A"])
        harness.run([git, "-C", os.fspath(root), *GIT_IDENTITY, "commit", "-qm", "root"])
        self_run = invoke(root, "--self")
        gate.assert_exit(0, self_run, "--self must still succeed")
        self_tag = self_run.out.rstrip("\n")
        gate.assert_eq(len(self_tag), 7, "--self must still be a short commit hash")

        time_run = invoke(root)
        if time_run.rc != 0:
            gate.log_fail("default mode failed: %s" % time_run.err.strip())
        time_tag = time_run.out.rstrip("\n")
        if not TIME_TAG_RE.match(time_tag):
            gate.log_fail("default mode must still emit YYYYMMDD-HHMMSS, got '%s'" % time_tag)
        gate.log_pass("--self and the default time-based mode are unaffected by the guard")


def test_real_tree_still_produces_a_tag(gate):
    """The fixture proves the logic; this proves the guard is satisfiable by the ACTUAL repo. If any declared path were wrong TODAY, this fails -- which is the whole point of turning the silent skip into an error."""
    result = invoke(paths.repo_root(), "--submodule", "private/renet")
    out = result.out.rstrip("\n")
    gate.assert_exit(0, result, "the real tree must still generate a renet tag: %s" % out)
    if not SUBMODULE_TAG_RE.match(out):
        gate.log_fail("the real tag has an unexpected shape: '%s'" % out)
    gate.log_pass("the real private/renet tag still generates (%s)" % out)


def closure_repo(gate, root: pathlib.Path) -> pathlib.Path:
    """A throwaway git repository holding every `rdc` closure path and NO tags: closure mode reads `git rev-parse HEAD:<path>` and the tag list, both from `cwd`."""
    git = require_git()
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)
    for entry in generate_tag.CLOSURE_PATHS["rdc"]:
        target = root / entry
        if entry.endswith((".json", ".py", ".ts", ".yml")):
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("%s content\n" % entry, encoding="utf-8")
        else:
            target.mkdir(parents=True, exist_ok=True)
            (target / "keep.txt").write_text("%s\n" % entry, encoding="utf-8")
    harness.run([git, "-C", os.fspath(root), "init", "-q", "."])
    harness.run([git, "-C", os.fspath(root), "add", "-A"])
    result = harness.run([git, "-C", os.fspath(root), *GIT_IDENTITY, "commit", "-qm", "closure"])
    if result.rc != 0:
        gate.log_fail("could not commit the closure fixture: %s" % result.err.strip())
    return root


def closure_tag(gate, root: pathlib.Path) -> str:
    result = invoke(root, "--closure", "rdc", "--extra", "fixed")
    gate.assert_exit(0, result, "closure mode must succeed: %s" % result.err.strip())
    return result.out.rstrip("\n")


def test_closure_tag_moves_when_the_released_version_moves(gate):
    """THE BUG THIS PINS, reproduced twice on real traffic before the fix.

    Both closure images BAKE a version in, and that version comes from the latest git TAG -- not from a path -- so no CLOSURE_PATHS entry can cover it. The OID-at-HEAD hashing is even documented as being "immune to the in-job version bump", which is exactly why nothing else moves the key when a release lands.

    Release v1.2.12 landed 2026-07-30T10:16:14Z mid-PR. Runs 30534726467 and 30542942037 both failed `Validate Install Methods / Linux` with "Version mismatch: expected '1.2.13', got '1.2.12'", because `Build (Docker) / CLI Docker` was SKIPPED while the key stayed put: nothing on the branch could move it.

    Driven by cutting tags in a throwaway repository, so the case needs no write access to the real tag namespace.
    """
    git = require_git()
    with harness.temp_dir() as tmp:
        root = closure_repo(gate, tmp / "closure")
        untagged = closure_tag(gate, root)
        harness.run([git, "-C", os.fspath(root), "tag", "v9.9.9"])
        first = closure_tag(gate, root)
        # CONTROL: without this the assertion below is satisfied by ANY nondeterminism, including a tag that changes on every invocation, which would be a different and worse bug.
        gate.assert_eq(
            closure_tag(gate, root), first, "the same tag must reproduce the same closure key"
        )
        harness.run([git, "-C", os.fspath(root), "tag", "v9.9.10"])
        second = closure_tag(gate, root)
    if first in (second, untagged):
        gate.log_fail(
            "the rdc closure tag did NOT move when the released version moved (%s, %s, %s): a "
            "cached pre-release image would be served under the new version"
            % (untagged, first, second)
        )
    gate.log_pass(
        "the closure tag tracks the released version (%s -> %s -> %s), real tree untouched"
        % (untagged, first, second)
    )


def test_closure_tag_survives_an_unresolvable_version(gate):
    """This module also runs where no tag is reachable (a shallow clone, a fresh fork). Failing to resolve must degrade to a well-defined key, never break the build, so the marker is added even when no tag exists."""
    with harness.temp_dir() as tmp:
        root = closure_repo(gate, tmp / "closure")
        result = invoke(root, "--closure", "rdc", "--extra", "fixed")
    out = result.out.rstrip("\n")
    gate.assert_exit(0, result, "an unresolvable version must not fail tag generation")
    if not CLOSURE_TAG_RE.match(out):
        gate.log_fail("an unresolvable version produced a malformed tag: '%s'" % out)
    gate.assert_contains(
        result.err, "No version tag reachable", "and say that image reuse is disabled"
    )
    gate.log_pass("an unresolvable version degrades to a well-formed tag (%s)" % out)
