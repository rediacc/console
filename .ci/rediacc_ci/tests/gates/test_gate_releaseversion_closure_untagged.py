"""Port of `.ci/scripts/test/gates/test-releaseversion-closure-untagged.sh`.

The version component of the closure key in `.ci/scripts/ci/generate-tag.sh`.

WHAT THE KEY IS FOR. `generate-tag.sh --closure web|rdc` mints the tag that names
a Docker image. initialize.sh asks the registry whether that tag exists and skips
the build if it does, so the key is a cache key: two builds that hash the same
reuse the same image. Both images BAKE a version in, and the version comes from a
git tag, which is not a path -- so it is folded into the hash explicitly.

WHAT WAS BROKEN. When no tag was reachable the fallback was an EMPTY marker, and
an empty marker COLLAPSES the key: every version on a tagless checkout hashes
identically, so a cached image built at an older version can be reused and then
promoted under a new one. That is the exact failure the version component was
added to prevent. It also runs at initialize.sh Step 5, BEFORE that script
fetches tags, so the tagless path is not hypothetical -- it is latent purely
because ci.yml's checkout happens to pass fetch-tags: true.

EVERY FIXTURE IS A THROWAWAY GIT REPO UNDER `tmp_path`. The real tree is READ
(three scripts are copied out of it, and the rdc closure list is read back from
generate-tag.sh) and never written, which is what keeps this module admissible
to the parity driver.
"""

import pathlib
import re

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

BASH_TWIN = ".ci/scripts/test/gates/test-releaseversion-closure-untagged.sh"

GENERATE_TAG = paths.from_root(".ci", "scripts", "ci", "generate-tag.sh")

# Every path the rdc closure hashes. Listed here so a closure that grows without
# this fixture growing with it fails loudly in build_fixture rather than
# silently testing a different code path.
RDC_CLOSURE_PATHS = (
    "packages/cli",
    "packages/shared",
    "packages/provisioning",
    "package.json",
    "package-lock.json",
    "tsconfig.json",
    ".ci/scripts/build/build-cli-musl.sh",
    ".ci/scripts/build/build-cli-executables.sh",
    ".ci/scripts/build/prepare-cli-assets.sh",
    "scripts/gen/generate-third-party-licenses.ts",
    ".github/workflows/ci-build-cli.yml",
    ".github/workflows/ci-build-docker.yml",
)

# The `rdc)` arm of the closure case statement, which is where the path list
# actually lives.
RDC_ARM_RE = re.compile(r"^        rdc\)(.*?)^            \)", re.DOTALL | re.MULTILINE)

COPIED = (
    (".ci", "scripts", "ci", "generate-tag.sh"),
    (".ci", "scripts", "lib", "common.sh"),
    (".ci", "scripts", "version", "resolve-version.sh"),
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
    """A throwaway git repo carrying the real generate-tag.sh, its lib and its
    resolver, plus a stand-in for every hashed closure path."""
    root = tmp_path / name
    for parts in COPIED:
        src = paths.from_root(*parts)
        if not src.is_file():
            gate.log_fail("subject under test is missing: %s" % src)
        dest = root.joinpath(*parts)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        dest.chmod(0o755)
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
    """Move HEAD without touching any hashed path, so only the version component
    can distinguish the two keys."""
    readme = root / "README.md"
    readme.write_text(readme.read_text(encoding="utf-8") + "changed\n", encoding="utf-8")
    git(gate, root, "add", "README.md")
    git(gate, root, "commit", "-q", "-m", "next")


def closure_tag(root: pathlib.Path) -> harness.RunResult:
    return harness.run(
        ["bash", "./.ci/scripts/ci/generate-tag.sh", "--closure", "rdc"], cwd=root, timeout=120
    )


def test_closure_paths_all_exist_in_the_real_script(gate):
    if not GENERATE_TAG.is_file():
        gate.log_fail("subject under test is missing: %s" % GENERATE_TAG)
    match = RDC_ARM_RE.search(GENERATE_TAG.read_text(encoding="utf-8"))
    if not match:
        gate.log_fail(
            "the rdc closure arm could not be located in %s, so the fixture's path list "
            "could not be compared against anything" % paths.relative_to_root(GENERATE_TAG)
        )
    arm = match.group(0)
    for rel in RDC_CLOSURE_PATHS:
        gate.assert_contains(arm, rel, "rdc closure must still hash %s" % rel)
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
    """THE CONTROL. Plant the pre-fix empty marker and watch the untagged keys
    collapse into one. Without this, test_untagged_keys_are_distinguishing could
    be passing for reasons unrelated to the version component."""
    root = build_fixture(gate, tmp_path, "planted")
    script = root / ".ci" / "scripts" / "ci" / "generate-tag.sh"
    planted = []
    hit = 0
    for line in script.read_text(encoding="utf-8").splitlines():
        if line.startswith('        CLOSURE_VERSION="untagged-'):
            planted.append('        CLOSURE_VERSION=""')
            hit += 1
            continue
        planted.append(line)
    script.write_text("\n".join(planted) + "\n", encoding="utf-8")
    gate.assert_contains(
        script.read_text(encoding="utf-8"), 'CLOSURE_VERSION=""', "the plant must have applied"
    )

    first = closure_tag(root)
    commit_unhashed_change(gate, root)
    second = closure_tag(root)
    gate.assert_eq(
        second.out.strip(),
        first.out.strip(),
        "planted empty marker must collapse the key (else the control proves nothing)",
    )
    gate.log_pass("the key stays distinct only because the fallback is distinguishing")
