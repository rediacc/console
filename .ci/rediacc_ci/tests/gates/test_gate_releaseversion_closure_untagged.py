"""Port of `.ci/scripts/test/gates/test-releaseversion-closure-untagged.sh`, retired in W7 P5.

The version component of the closure key in `rediacc_ci.ci.generate_tag` (the retired `generate-tag.sh` has no other home).

WHAT THE KEY IS FOR. `generate_tag --closure web|rdc` mints the tag that names a Docker image. The Initialize step asks the registry whether that tag exists and skips the build if it does, so the key is a cache key: two builds that hash the same reuse the same image. Both images BAKE a version in, and the version comes from a git tag, which is not a path -- so it is folded into the
hash explicitly.

WHAT WAS BROKEN. When no tag was reachable the fallback was an EMPTY marker, and an empty marker COLLAPSES the key: every version on a tagless checkout hashes identically, so a cached image built at an older version can be reused and then promoted under a new one. That is the exact failure the version component was added to prevent. It also runs at initialize.sh Step 5, BEFORE that
script fetches tags, so the tagless path is not hypothetical -- it is latent purely because ci.yml's checkout happens to pass fetch-tags: true.

EVERY FIXTURE IS A THROWAWAY GIT REPO UNDER `tmp_path`. The real tree is READ (the module is run from it, and the rdc closure list is read back from it) and never written, which is what keeps this module admissible to the parity driver.
"""

import os
import pathlib

from rediacc_ci import paths
from rediacc_ci.ci import generate_tag
from rediacc_ci.tests.gates import harness

GENERATE_TAG = paths.from_root(".ci", "rediacc_ci", "ci", "generate_tag.py")
ENV = {"PYTHONPATH": os.fspath(paths.from_root(".ci")), "PYTHONDONTWRITEBYTECODE": "1"}

# Every path the rdc closure hashes. Listed here so a closure that grows without this fixture growing with it fails loudly in build_fixture rather than silently testing a different code path.
RDC_CLOSURE_PATHS = (
    "packages/cli",
    "packages/shared",
    "packages/provisioning",
    "package.json",
    "package-lock.json",
    "tsconfig.json",
    ".ci/rediacc_ci/build/build_cli_musl.py",
    ".ci/rediacc_ci/build/build_cli_executables.py",
    ".ci/rediacc_ci/build/prepare_cli_assets.py",
    "scripts/gen/generate-third-party-licenses.ts",
    ".github/workflows/ci-build-cli.yml",
    ".github/workflows/ci-build-docker.yml",
)


def git(gate, root: pathlib.Path, *args: str) -> harness.RunResult:
    harness.require_tool("git", "install git; the closure key is derived from git history")
    result = harness.run(
        [
            "git",
            "-C",
            str(root),
            "-c",
            "user.email=t@t",
            "-c",
            "user.name=t",
            "-c",
            "commit.gpgsign=false",
            *args,
        ],
        timeout=120,
    )
    if result.rc != 0:
        gate.log_fail("git %s failed in the fixture: %s" % (" ".join(args), result.err.strip()))
    return result


def build_fixture(gate, tmp_path: pathlib.Path, name: str) -> pathlib.Path:
    """A throwaway git repo carrying a stand-in for every hashed closure path."""
    root = tmp_path / name
    root.mkdir(parents=True, exist_ok=True)
    for rel in RDC_CLOSURE_PATHS:
        dest = root.joinpath(*rel.split("/"))
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text("closure stand-in for %s\n" % rel, encoding="utf-8")
    (root / "README.md").write_text("unhashed\n", encoding="utf-8")

    git(gate, root, "init", "-q")
    git(gate, root, "add", "-A")
    git(gate, root, "commit", "-q", "-m", "first")
    return root


def commit_unhashed_change(gate, root: pathlib.Path) -> None:
    """Move HEAD without touching any hashed path, so only the version component can distinguish the two keys."""
    readme = root / "README.md"
    readme.write_text(readme.read_text(encoding="utf-8") + "changed\n", encoding="utf-8")
    git(gate, root, "add", "README.md")
    git(gate, root, "commit", "-q", "-m", "next")


def closure_tag(root: pathlib.Path, module: pathlib.Path | None = None) -> harness.RunResult:
    """The module run from `root` (or a mutated copy of it, by path)."""
    argv = ["python3", os.fspath(module)] if module else ["python3", "-m", generate_tag.__name__]
    return harness.run([*argv, "--closure", "rdc"], cwd=root, env=ENV, timeout=120)


def test_closure_paths_all_exist_in_the_real_module(gate):
    gate.assert_eq(
        tuple(generate_tag.CLOSURE_PATHS["rdc"]),
        RDC_CLOSURE_PATHS,
        "the rdc closure has drifted from this fixture's stand-ins",
    )
    gate.log_pass("all %d rdc closure paths accounted for" % len(RDC_CLOSURE_PATHS))


def test_untagged_keys_are_distinguishing(gate, tmp_path):
    root = build_fixture(gate, tmp_path, "untagged")
    first = closure_tag(root)
    gate.assert_contains(first.err, "No version tag reachable", "the fallback must announce itself")
    commit_unhashed_change(gate, root)
    second = closure_tag(root)
    if first.out.strip() == second.out.strip():
        gate.log_fail(
            "untagged closure keys collapsed: both commits produced '%s'" % first.out.strip()
        )
    gate.log_pass(
        "untagged keys differ per commit (%s vs %s)" % (first.out.strip(), second.out.strip())
    )


def test_tagged_keys_still_reuse(gate, tmp_path):
    root = build_fixture(gate, tmp_path, "tagged")
    git(gate, root, "tag", "v1.2.17")
    first = closure_tag(root)
    gate.assert_not_contains(
        first.err, "No version tag reachable", "a tagged repo must not take the fallback"
    )
    commit_unhashed_change(gate, root)
    second = closure_tag(root)
    gate.assert_eq(
        second.out.strip(),
        first.out.strip(),
        "a commit touching no hashed path must reuse the image",
    )
    gate.log_pass("cache reuse is preserved when a version exists (%s)" % first.out.strip())


def test_new_tag_invalidates_the_key(gate, tmp_path):
    root = build_fixture(gate, tmp_path, "retagged")
    git(gate, root, "tag", "v1.2.17")
    first = closure_tag(root)
    git(gate, root, "tag", "v1.2.18")
    second = closure_tag(root)
    if first.out.strip() == second.out.strip():
        gate.log_fail(
            "a version bump did not move the closure key: both were '%s'" % first.out.strip()
        )
    gate.log_pass("v1.2.17 and v1.2.18 produce different keys")


def test_planted_empty_marker_collapses_the_key(gate, tmp_path):
    """THE CONTROL. Plant the pre-fix empty marker and watch the untagged keys collapse into one. Without this, test_untagged_keys_are_distinguishing could be passing for reasons unrelated to the version component."""
    root = build_fixture(gate, tmp_path, "planted")
    source = GENERATE_TAG.read_text(encoding="utf-8")
    needle = 'return "untagged-%s" % (head if head_status == 0 and head else "unknown"), True'
    gate.assert_contains(source, needle, "the fallback line this control plants on must exist")
    script = tmp_path / "planted_generate_tag.py"
    script.write_text(source.replace(needle, 'return "", True'), encoding="utf-8")

    first = closure_tag(root, script)
    commit_unhashed_change(gate, root)
    second = closure_tag(root, script)
    gate.assert_eq(
        second.out.strip(),
        first.out.strip(),
        "planted empty marker must collapse the key (else the control proves nothing)",
    )
    gate.log_pass("the key stays distinct only because the fallback is distinguishing")
