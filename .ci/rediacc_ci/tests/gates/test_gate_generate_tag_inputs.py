"""Port of `.ci/scripts/test/gates/test-generate-tag-inputs.sh`.

Both-ways test for the build-config hash in `.ci/scripts/ci/generate-tag.sh`.

WHAT THE HASH IS FOR. `generate-tag.sh --submodule private/renet` mints the tag that names ghcr.io/rediacc/renet. `initialize.sh` asks the registry whether that
tag already exists and, if it does, sets `renet_exists=true`, which skips the
45-minute Renet (Full) build AND the image build. The tag is therefore a cache key, and `BUILD_CONFIG_FILES` is its input list: an input missing from the list means a changed build resolves to an existing tag and a stale image is reused.

WHAT BROKE. The list was consulted through `if [[ -f "$f" ]]`, so a renamed or moved input was skipped in silence. The one visible symptom is a cache miss -- the surviving digests concatenate differently, so the tag still CHANGES -- and a cache miss is indistinguishable from normal behaviour. The list could rot indefinitely and the script would keep printing a plausible tag and
exiting 0.

WHY A FIXTURE TREE. The gate reads real files from the working directory, so the only way to plant a defect without touching a tracked file is to build a throwaway repo with the same shape and run the real script inside it. Nothing about the SUBJECT is reimplemented here: every invocation below is the real `bash .ci/scripts/ci/generate-tag.sh`.

WHY THIS MODULE OPTS IN TO THE REAL-TREE GROUP, and it is the sharper reason of the two kinds. Most real-tree twins only READ the working tree. This one WRITES it: the last two cases overwrite the tracked `.ci/scripts/version/resolve-version.sh`
with a stub resolver and restore it a second later, because `generate-tag.sh`
gives them no fixture seam to do it in (the closure mode invokes the resolver via `cd "$REPO_ROOT"`). A gate reading that script inside the window sees a half-written file: on 2026-08-17 that reddened `gate-test:claude-hooks` with a bash syntax error in a file that parses clean. The twin is in `WRITER_TESTS` in `run-all.sh` and carries `mutex: ["tree:repo"]` in `gates.lock.json`
for exactly
that reason, so the port must be serialised too. `REAL_TREE_TWIN = True` buys the
serialisation, and it is honoured ONLY because this module declares no `XDIST_GROUP` of its own; see `real_tree_admission` in `test_twin_parity.py`, which refuses that combination and refuses over-claiming in the other direction.

WHAT THE PORT ADDS RATHER THAN DROPS. The twin restores the resolver with `cp` and then infers success from the tag coming back to baseline. This restores in a `finally` (so a raised assertion cannot strand the stub the way an `exit` from inside a bash function can) and additionally asserts the restored file is byte-identical by sha256 and keeps its mode. A tag that matches is good
evidence the CONTENT came back; it says nothing about the permission bit, and a resolver left non-executable would fail somewhere else entirely.
"""

import hashlib
import os
import pathlib
import re
import shutil

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

BASH_TWIN = ".ci/scripts/test/gates/test-generate-tag-inputs.sh"

# Two cases overwrite the tracked `.ci/scripts/version/resolve-version.sh` in place and restore it. See the module docstring.
REAL_TREE_TWIN = True

GATE_REL = ".ci/scripts/ci/generate-tag.sh"
GATE = paths.from_root(*GATE_REL.split("/"))
RESOLVER_REL = ".ci/scripts/version/resolve-version.sh"
RESOLVER = paths.from_root(*RESOLVER_REL.split("/"))

# Every path in BUILD_CONFIG_FILES, in the same order, relative to the tree root. Kept here so a list that grows without a test growing with it shows up in `test_declared_inputs_match_the_script` rather than going unnoticed.
DECLARED_INPUTS = (
    "private/renet/Dockerfile",
    "private/renet/Dockerfile.native",
    "private/renet/build.sh",
    ".github/workflows/ci-build-renet.yml",
    ".github/workflows/ci-build-docker.yml",
    ".ci/scripts/build/build-renet.sh",
)

# The sibling that must NOT be an input.
INFRA_SIBLING = ".ci/scripts/infra/build-renet.sh"

TIME_TAG_RE = re.compile(r"^[0-9]{8}-[0-9]{6}$")
SUBMODULE_TAG_RE = re.compile(r"^[0-9a-f]+-[0-9a-f]{12}$")
CLOSURE_TAG_RE = re.compile(r"^rdc-[0-9a-f]{12}$")


def require_gate(gate) -> str:
    """The subject, proved present and executable before anything is claimed.

    The twin dies on a bare `command not found` if either the script or bash is absent. Probing names which one and what to do, because a missing tool is a FAILURE here and never a skip: an unchecked case folded into "fine" is the shape this directory refuses.
    """
    if not GATE.is_file():
        gate.log_fail("subject under test is missing: %s" % GATE_REL)
    if not os.access(GATE, os.X_OK):
        gate.log_fail("subject is not executable: %s. Fix: chmod +x %s" % (GATE_REL, GATE_REL))
    return harness.require_tool("bash", "install bash; the subject IS a bash script")


def require_git() -> str:
    return harness.require_tool(
        "git", "install git; the subject rev-parses a submodule to build the tag"
    )


def build_fixture_tree(gate, root: pathlib.Path) -> None:
    """The twin's `build_fixture_tree`, same shape and same seed bytes.

    The script under test resolves its lib relative to its own path, so the `.ci` layout is mirrored instead of the script being copied somewhere flat.
    """
    require_gate(gate)
    git = require_git()
    if root.exists():
        shutil.rmtree(root)
    for sub in (
        ".ci/scripts/ci",
        ".ci/scripts/lib",
        ".ci/scripts/build",
        ".ci/scripts/infra",
        ".github/workflows",
        "private/renet",
    ):
        (root / sub).mkdir(parents=True, exist_ok=True)
    shutil.copy2(GATE, root / ".ci" / "scripts" / "ci" / GATE.name)
    for lib in sorted(paths.from_root(".ci", "scripts", "lib").glob("*.sh")):
        shutil.copy2(lib, root / ".ci" / "scripts" / "lib" / lib.name)

    for rel in DECLARED_INPUTS:
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("seed content for %s\n" % rel, encoding="utf-8")
    # Present in the tree, as it is in the real repo, so "the tag did not change" below is about the LIST and not about a missing file.
    (root / INFRA_SIBLING).write_text("seed content for infra\n", encoding="utf-8")

    # A real git repo at the submodule path: the script rev-parses it, and a fixed commit keeps the SUBMODULE_COMMIT half of the tag constant so every difference below is attributable to the build-config half.
    sub = root / "private" / "renet"
    harness.run([git, "-C", os.fspath(sub), "init", "-q", "."])
    harness.run([git, "-C", os.fspath(sub), "add", "-A"])
    harness.run(
        [
            git,
            "-C",
            os.fspath(sub),
            "-c",
            "user.email=fixture@example.com",
            "-c",
            "user.name=fixture",
            "commit",
            "-qm",
            "fixture",
        ]
    )


def invoke(gate, cwd: pathlib.Path, *args: str) -> harness.RunResult:
    """The real script, run from `cwd`. Streams are kept apart, as the twin does
    when it reads stdout alone and again when it reads `2>&1`."""
    bash = require_gate(gate)
    return harness.run([bash, ".ci/scripts/ci/generate-tag.sh", *args], cwd=cwd)


def tag(gate, root: pathlib.Path) -> str:
    """`tag` from the twin: prints the generated tag, fails the case on an error.

    `$(...)` strips trailing newlines in bash, so `rstrip("\\n")` here is not tidying: without it every `assert_eq` against a tag would compare a string the twin never compares.
    """
    result = invoke(gate, root, "--submodule", "private/renet")
    if result.rc != 0:
        gate.log_fail(
            "generate-tag.sh exited %s when a tag was expected: %s"
            % (harness.describe_exit(result.rc), result.err.strip())
        )
    return result.out.rstrip("\n")


def digest(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def declared_array_body(gate) -> str:
    """The `BUILD_CONFIG_FILES=(` ... `)` block, the twin's `sed -n` range.

    Anchored on the same two lines the twin anchors on, so a reindentation that would hide the array from the twin hides it from the port too, rather than the two disagreeing about whether the gate still declares one.
    """
    source = GATE.read_text(encoding="utf-8")
    lines = source.splitlines()
    body = []
    inside = False
    for line in lines:
        if line.startswith("    BUILD_CONFIG_FILES=("):
            inside = True
        if inside:
            body.append(line)
        if inside and line.startswith("    )"):
            break
    if not body:
        gate.log_fail(
            "BUILD_CONFIG_FILES=( ... ) is no longer parseable out of %s, so every "
            "per-input control below would be checking a list nobody declares" % GATE_REL
        )
    return "\n".join(body)


# ---------------------------------------------------------------------------


def test_declared_inputs_match_the_script(gate):
    """Anti-vacuity, and the first thing to break if someone extends the list.

    Every case below is about DECLARED_INPUTS; if that drifts from the real BUILD_CONFIG_FILES, the per-input control proof silently stops covering the new entry.
    """
    body = declared_array_body(gate)
    gate.assert_contains(
        body, "BUILD_CONFIG_FILES=(", "the array must still be parseable from the script"
    )
    for rel in DECLARED_INPUTS:
        # The array spells the submodule paths through $SUBMODULE_PATH.
        needle = rel.replace("private/renet", "$SUBMODULE_PATH")
        gate.assert_contains(
            body, '"%s"' % needle, "BUILD_CONFIG_FILES must still declare %s" % rel
        )
    actual = len([line for line in body.splitlines() if line.startswith('        "')])
    gate.assert_eq(
        actual,
        len(DECLARED_INPUTS),
        "BUILD_CONFIG_FILES has %d entries but this test knows about %d; add the new one here"
        % (actual, len(DECLARED_INPUTS)),
    )
    gate.log_pass("the %d declared inputs match BUILD_CONFIG_FILES exactly" % len(DECLARED_INPUTS))


def test_tag_is_deterministic(gate):
    """Baseline. Without it, "the tag changed" below proves nothing: it could
    change on every invocation."""
    with harness.temp_dir() as tmp:
        root = tmp / "repo"
        build_fixture_tree(gate, root)
        first = tag(gate, root)
        second = tag(gate, root)
        gate.assert_eq(second, first, "two runs over an unchanged tree must produce the same tag")
        gate.assert_contains(first, "-", "the tag must carry both halves (commit-confighash)")
        gate.log_pass("the tag is deterministic over an unchanged tree (%s)" % first)


def test_every_declared_input_changes_the_tag(gate):
    """THE CONTROL PROOF, one per entry. An entry that does not move the tag is
    decoration: it is in the list but not in the key, and a change to it would reuse a stale image. This is the assertion that would have caught a path pointed at the wrong build-renet.sh, because the wrong path cannot be
    perturbed into changing anything."""
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
    """The other direction, and the finding that prompted the twin. Nine CI steps
    run `.ci/scripts/infra/build-renet.sh` and it is NOT in the list -- correctly, because it compiles a dev binary for ct-tests / ci-ops-test, which never pull the renet image and are never handed this tag. Pinning it here means the next reader gets the answer instead of re-deriving it, and a future decision to
    include it has to change this case deliberately."""
    with harness.temp_dir() as tmp:
        root = tmp / "repo"
        build_fixture_tree(gate, root)
        base = tag(gate, root)
        (root / INFRA_SIBLING).write_text("perturbed infra\n", encoding="utf-8")
        gate.assert_eq(
            tag(gate, root),
            base,
            "editing infra/build-renet.sh must NOT change the renet image tag "
            "(it does not affect the image)",
        )
        gate.log_pass("the sibling infra/build-renet.sh is deliberately outside the hash")


def test_missing_input_fails_loudly(gate):
    """THE REGRESSION. Before the fix this exited 0 and printed a tag: a DIFFERENT
    tag, because the remaining digests concatenate differently, so the only
    symptom was a cache miss nobody would investigate."""
    with harness.temp_dir() as tmp:
        root = tmp / "repo"
        build_fixture_tree(gate, root)
        tag(gate, root)
        (root / ".ci/scripts/build/build-renet.sh").unlink()
        result = invoke(gate, root, "--submodule", "private/renet")
        gate.assert_exit_code(
            1, result.rc, "a missing declared input must fail the script, not narrow the hash"
        )
        gate.assert_contains(
            result.combined,
            "Build-config input not found",
            "with a diagnostic that names the failure",
        )
        gate.assert_contains(
            result.combined, ".ci/scripts/build/build-renet.sh", "and names the missing path"
        )
        gate.log_pass("a missing declared input fails loudly instead of silently shrinking the key")


def test_missing_input_does_not_emit_a_tag(gate):
    """The specific shape of the old bug: the caller (`initialize.sh:141`,
    `RENET_TAG=$(...)`) captures stdout. Under the old behaviour it captured a
    plausible-looking tag computed from a narrowed key. Nothing may reach stdout
    on this path."""
    with harness.temp_dir() as tmp:
        root = tmp / "repo"
        build_fixture_tree(gate, root)
        (root / ".ci/scripts/build/build-renet.sh").unlink()
        result = invoke(gate, root, "--submodule", "private/renet")
        gate.assert_exit_code(
            1, result.rc, "the failure must be visible in the exit code the caller sees"
        )
        gate.assert_eq(
            result.out.rstrip("\n"), "", "no tag may be printed when an input is missing"
        )
        gate.log_pass("a missing input prints no tag, so a caller capturing stdout cannot use one")


def test_every_declared_input_is_individually_load_bearing_for_the_failure(gate):
    """Sweep the class: the guard must cover every entry, not just the one that
    prompted it. A guard that only checks the last element of a list is a classic
    partial fix."""
    with harness.temp_dir() as tmp:
        root = tmp / "repo"
        for rel in DECLARED_INPUTS:
            build_fixture_tree(gate, root)
            (root / rel).unlink()
            result = invoke(gate, root, "--submodule", "private/renet")
            gate.assert_exit_code(1, result.rc, "removing %s must fail the script" % rel)
            gate.assert_contains(result.combined, rel, "the diagnostic must name %s" % rel)
        gate.log_pass("all %d declared inputs are guarded, not just one" % len(DECLARED_INPUTS))


def test_other_modes_are_untouched(gate):
    """The guard lives in the `--submodule` branch. `--self` and the time-based
    default must keep working even though `initialize.sh` no longer uses `--self`
    for WEB_TAG (it moved to `--closure web` when D5 landed). Both modes are still
    reachable and still pinned here, because nothing else guards them and a silent
    regression in either would only surface as a mystery tag."""
    git = require_git()
    with harness.temp_dir() as tmp:
        root = tmp / "repo"
        build_fixture_tree(gate, root)
        # The nested fixture submodule makes git warn about an embedded repo; it is noise here, and the commit is only needed so --self has something to rev-parse.
        harness.run([git, "-C", os.fspath(root), "init", "-q", "."])
        harness.run([git, "-C", os.fspath(root), "add", "-A"])
        harness.run(
            [
                git,
                "-C",
                os.fspath(root),
                "-c",
                "user.email=fixture@example.com",
                "-c",
                "user.name=fixture",
                "commit",
                "-qm",
                "root",
            ]
        )
        self_run = invoke(gate, root, "--self")
        gate.assert_exit_code(0, self_run.rc, "--self must still succeed")
        self_tag = self_run.out.rstrip("\n")
        gate.assert_eq(len(self_tag), 7, "--self must still be a short commit hash")

        time_run = invoke(gate, root)
        if time_run.rc != 0:
            gate.log_fail("default mode failed: %s" % time_run.err.strip())
        time_tag = time_run.out.rstrip("\n")
        if not TIME_TAG_RE.match(time_tag):
            gate.log_fail("default mode must still emit YYYYMMDD-HHMMSS, got '%s'" % time_tag)
        gate.log_pass("--self and the default time-based mode are unaffected by the guard")


def test_real_tree_still_produces_a_tag(gate):
    """The fixture proves the logic; this proves the guard is satisfiable by the
    ACTUAL repo. If any declared path were wrong TODAY, this fails -- which is the
    whole point of turning the silent skip into an error."""
    result = invoke(gate, paths.repo_root(), "--submodule", "private/renet")
    out = result.out.rstrip("\n")
    gate.assert_exit_code(0, result.rc, "the real tree must still generate a renet tag: %s" % out)
    if not SUBMODULE_TAG_RE.match(out):
        gate.log_fail("the real tag has an unexpected shape: '%s'" % out)
    gate.log_pass("the real private/renet tag still generates (%s)" % out)


def swap_resolver(gate, body: str) -> str:
    """Overwrite the REAL resolver with `body`, returning its original sha256.

    THE WRITE IS THE POINT and there is no seam that avoids it: closure mode invokes `.ci/scripts/version/resolve-version.sh` from the repo root, so the only way to move the released version is to move that file. It is why this module is a real-tree WRITER and why the twin lives in `WRITER_TESTS`.
    """
    if not RESOLVER.is_file():
        gate.log_fail("the version resolver is missing at %s" % RESOLVER_REL)
    before = digest(RESOLVER)
    RESOLVER.write_text(body, encoding="utf-8")
    RESOLVER.chmod(RESOLVER.stat().st_mode | 0o111)
    return before


def restore_resolver(gate, backup: pathlib.Path, mode: int, before: str) -> None:
    """Put it back, and PROVE it went back.

    A `finally`, not a trap: a bash function cannot clean up after an `exit` from inside itself, which is why the twin binds its restore to a `cp` on the happy path. Python unwinds, so the stub cannot outlive a failed assertion here.
    """
    shutil.copyfile(backup, RESOLVER)
    RESOLVER.chmod(mode)
    gate.assert_eq(
        digest(RESOLVER), before, "the real %s must be byte-identical afterwards" % RESOLVER_REL
    )
    gate.assert_eq(
        RESOLVER.stat().st_mode & 0o777,
        mode & 0o777,
        "the real %s must keep its mode; a resolver left non-executable fails elsewhere"
        % RESOLVER_REL,
    )


def test_closure_tag_moves_when_the_released_version_moves(gate):
    """THE BUG THIS PINS, reproduced twice on real traffic before the fix.

    Both closure images BAKE a version in, and that version comes from the latest git TAG -- not from a path -- so no CLOSURE_PATHS entry can cover it. The OID-at-HEAD hashing is even documented as being "immune to the in-job version bump", which is right for a dirty working file and exactly wrong for this: the key went insensitive to the one input the image is stamped with.

    Release v1.2.12 landed 2026-07-30T10:16:14Z mid-PR. Runs 30534726467 and 30542942037 both failed `Validate Install Methods / Linux` with "Version mismatch: expected '1.2.13', got '1.2.12'", because `Build (Docker) / CLI Docker` was SKIPPED while its cached twin succeeded and the mutable pr-546 tag kept serving a pre-release image. Deterministic and self-perpetuating, not a
    race: nothing on the branch could move the key.

    Driven by swapping the RESOLVER rather than by cutting a git tag, so the case needs no write access to the real tag namespace.
    """
    root = paths.repo_root()
    with harness.temp_dir() as tmp:
        backup = tmp / "resolve-version.real"
        shutil.copyfile(RESOLVER, backup)
        mode = RESOLVER.stat().st_mode
        before_tag = invoke(gate, root, "--closure", "rdc", "--extra", "fixed").out.rstrip("\n")
        after_tag = ""
        try:
            swap_resolver(
                gate,
                '#!/bin/bash\n[ "$1" = "--current" ] && echo "v9.9.9" || echo "9.9.10"\n',
            )
            after_tag = invoke(gate, root, "--closure", "rdc", "--extra", "fixed").out.rstrip("\n")
        finally:
            restore_resolver(gate, backup, mode, digest(backup))
        restored = invoke(gate, root, "--closure", "rdc", "--extra", "fixed").out.rstrip("\n")

        if before_tag == after_tag:
            gate.log_fail(
                "the rdc closure tag did NOT move when the released version moved (%s): a "
                "cached pre-release image would be served under the new version" % before_tag
            )
        # CONTROL: without this the assertion above is satisfied by ANY nondeterminism, including a tag that changes on every invocation, which would be a different and worse bug.
        gate.assert_eq(
            restored,
            before_tag,
            "restoring the resolver must reproduce the ORIGINAL tag, so the key is "
            "version-sensitive rather than merely unstable",
        )
        gate.log_pass(
            "the closure tag tracks the released version (%s -> %s -> %s)"
            % (before_tag, after_tag, restored)
        )


def test_closure_tag_survives_an_unresolvable_version(gate):
    """This script also runs where no tag is reachable (a shallow clone, a fresh
    fork). Failing to resolve must degrade to a well-defined key, never break the
    build, so the marker is added even when empty."""
    root = paths.repo_root()
    with harness.temp_dir() as tmp:
        backup = tmp / "resolve-version.real2"
        shutil.copyfile(RESOLVER, backup)
        mode = RESOLVER.stat().st_mode
        try:
            swap_resolver(gate, "#!/bin/bash\nexit 1\n")
            result = invoke(gate, root, "--closure", "rdc", "--extra", "fixed")
        finally:
            restore_resolver(gate, backup, mode, digest(backup))
        out = result.out.rstrip("\n")
        gate.assert_exit_code(0, result.rc, "an unresolvable version must not fail tag generation")
        if not CLOSURE_TAG_RE.match(out):
            gate.log_fail("an unresolvable version produced a malformed tag: '%s'" % out)
        gate.log_pass("an unresolvable version degrades to a well-formed tag (%s)" % out)
