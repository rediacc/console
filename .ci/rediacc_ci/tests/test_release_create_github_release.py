"""Differential: `rediacc_ci.release.create_github_release` against its twin
`.ci/scripts/release/create-github-release.sh`.

THIS SCRIPT PUBLISHES. Its twin's own header says so: `gh release create` makes a real, public GitHub Release and uploads every asset to it. `gh` IS installed and authenticated on this machine, so the fake is not a convenience, it is the only thing standing between this test file and a published release. Three independent guards, in order of how much they are trusted:

  1. A recording fake `gh` FIRST on a scratch PATH.
  2. `test_the_fake_gh_shadows_the_real_one`, which resolves the name through
     the constructed PATH and asserts the answer sits inside `tmp_path`. The
     fakes existing is not the claim; the fakes SHADOWING is.
  3. `GH_CONFIG_DIR` and `GH_TOKEN` pointed at scratch values, so even a leak
     through some path none of the above covers hits an unauthenticated client.

BOTH SIDES RUN IN A THROWAWAY TREE for a second reason: the twin `cd`s to `get_repo_root`, which has no override, and would otherwise glob THIS checkout's `dist/`. Each case builds one console tree per side at the real relative depths and plants the asset fixture inside it.

THE ARGV IS THE COMPARISON, not the stdout. Everything this script decides ends up in one `gh` invocation: the tag, the title, the target sha, the repo and the asset list IN ORDER. stdout is whatever `gh` prints. So the call log is asserted element by element, and the ordering case below is the one that matters most -- see `test_glob_order_is_bytewise_not_a_directory_walk`.

THE ORDERING CASE, spelled out because it is the one place a plausible port is wrong. `shopt -s globstar; dist/cli/**/*` sorts each pattern's matches bytewise, so with `dist/cli/v1/a.bin`, `dist/cli/v1-x` and `dist/cli/v1.y` present, bash emits `v1`, `v1-x`, `v1.y`, `v1/a.bin`: `-` (0x2D) and `.` (0x2E) both sort BELOW `/` (0x2F). A directory walk emitting each directory's children
immediately after the directory would give `v1`, `v1/a.bin`, `v1-x`, `v1.y`.
Both orders are defensible; only one matches. `LC_ALL=C` is pinned on both
sides, because bash sorts glob results with `strcoll` and the port sorts by codepoint, which is the same thing only in the C locale.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import typing

from rediacc_ci import paths
from rediacc_ci.release import create_github_release as port

if typing.TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()
TWIN = ROOT / ".ci" / "scripts" / "release" / "create-github-release.sh"
PORT = ROOT / ".ci" / "rediacc_ci" / "release" / "create_github_release.py"
COMMON = ROOT / ".ci" / "scripts" / "lib" / "common.sh"
BASH = shutil.which("bash") or "/bin/bash"

FAKE_GH = """#!/usr/bin/python3
import os
import sys

with open(os.environ["FAKE_LOG"], "a") as fh:
    fh.write("call: gh " + " ".join(sys.argv[1:]) + "\\n")

rc = int(os.environ.get("FAKE_GH_RC", "0"))
if rc == 0:
    sys.stdout.write("https://github.com/acme/widget/releases/tag/v1.2.3\\n")
else:
    sys.stderr.write("gh: HTTP 422 release already exists\\n")
sys.exit(rc)
"""

BASE_ENV_VARS = {
    "VERSION": "1.2.3",
    "GITHUB_SHA": "0123456789abcdef0123456789abcdef01234567",
    "GITHUB_REPOSITORY": "acme/widget",
}

NO_ASSETS = "::error::No release assets matched dist/{cli,packages}/**/*\n"


def _stub_path(tmp_path: pathlib.Path, side: str) -> str:
    stub = tmp_path / ("%s-bin" % side)
    stub.mkdir(parents=True, exist_ok=True)
    fake = stub / "gh"
    fake.write_text(FAKE_GH, encoding="utf-8")
    fake.chmod(0o755)
    return "%s:%s" % (stub, os.environ.get("PATH", "/usr/bin:/bin"))


def _fixture(tmp_path: pathlib.Path, side: str, assets: tuple[str, ...]) -> pathlib.Path:
    """One throwaway console tree, with `assets` planted under it.

    A trailing `/` in an entry makes a DIRECTORY and nothing else, which is how the empty-directory and directories-are-not-assets cases are expressed.
    """
    root = tmp_path / ("tree-%s" % side)
    for rel in (
        (".ci", "scripts", "release"),
        (".ci", "scripts", "lib"),
        (".ci", "rediacc_ci", "release"),
    ):
        (root / os.path.join(*rel)).mkdir(parents=True, exist_ok=True)
    shutil.copy2(TWIN, root / ".ci" / "scripts" / "release" / TWIN.name)
    shutil.copy2(PORT, root / ".ci" / "rediacc_ci" / "release" / PORT.name)
    shutil.copy2(COMMON, root / ".ci" / "scripts" / "lib" / "common.sh")

    for entry in assets:
        target = root / entry.rstrip("/")
        if entry.endswith("/"):
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(entry.encode("utf-8"))
    return root


def _run(
    tmp_path: pathlib.Path,
    side: str,
    *,
    assets: tuple[str, ...] = (),
    stub_gh: bool = True,
    link: tuple[str, str] | None = None,
    **extra: str,
) -> tuple[int, str, str, list[str]]:
    root = _fixture(tmp_path, side, assets)
    if link is not None:
        source, dest = link
        (root / dest).parent.mkdir(parents=True, exist_ok=True)
        (root / dest).symlink_to(root / source)

    call_log = tmp_path / ("%s-calls.log" % side)
    call_log.write_text("", encoding="utf-8")
    if stub_gh:
        path = _stub_path(tmp_path, side)
    else:
        # A PATH with coreutils but deliberately no `gh`. An EMPTY PATH is not the same test: it kills the twin at `$(dirname ...)` four lines before `require_cmd` runs, which measures the harness, not the subject.
        usable = tmp_path / ("%s-nogh" % side)
        usable.mkdir(parents=True, exist_ok=True)
        for name in ("dirname", "pwd", "uname", "mktemp"):
            real = shutil.which(name)
            if real is not None and not (usable / name).exists():
                (usable / name).symlink_to(real)
        path = str(usable)

    env = {
        "PATH": path,
        "HOME": str(tmp_path),
        "TMPDIR": str(tmp_path),
        "LC_ALL": "C",
        "LANG": "C",
        "NO_COLOR": "1",
        "PYTHONPATH": str(ROOT / ".ci"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "FAKE_LOG": str(call_log),
        # Third guard: even a call that escaped the fake cannot authenticate.
        "GH_CONFIG_DIR": str(tmp_path / "gh-config"),
        "GH_TOKEN": "fake-token-not-a-credential",
        **BASE_ENV_VARS,
    }
    env.update(extra)
    for key, value in list(env.items()):
        if value is None:
            del env[key]

    if side == "old":
        subject = root / ".ci" / "scripts" / "release" / TWIN.name
        runner = [BASH]
    else:
        subject = root / ".ci" / "rediacc_ci" / "release" / PORT.name
        runner = [sys.executable]
    proc = subprocess.run(
        [*runner, str(subject)],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=60,
    )
    calls = [line for line in call_log.read_text(encoding="utf-8").splitlines() if line]
    return proc.returncode, proc.stdout, proc.stderr, calls


def run_both(tmp_path: pathlib.Path, **kw) -> tuple[tuple, tuple]:
    return _run(tmp_path, "old", **kw), _run(tmp_path, "new", **kw)


def assert_agree(old: tuple, new: tuple, label: str) -> None:
    o_rc, o_out, o_err, o_calls = old
    n_rc, n_out, n_err, n_calls = new
    assert n_rc == o_rc, "%s: exit diverged: %d vs %d (old %r, new %r)" % (
        label,
        o_rc,
        n_rc,
        o_err,
        n_err,
    )
    assert n_out == o_out, "%s: stdout diverged:\nold: %r\nnew: %r" % (label, o_out, n_out)
    assert n_err == o_err, "%s: stderr diverged:\nold: %r\nnew: %r" % (label, o_err, n_err)
    assert n_calls == o_calls, "%s: call sequence diverged:\nold: %s\nnew: %s" % (
        label,
        o_calls,
        n_calls,
    )


def _assets_of(call: str) -> list[str]:
    """Everything after `--repo <owner/repo>` in a recorded `gh` call."""
    parts = call.split(" ")
    return parts[parts.index("--repo") + 2 :]


# --------------------------------------------------------------------------- The controls on the harness ---------------------------------------------------------------------------


def test_the_fake_gh_shadows_the_real_one(tmp_path: pathlib.Path) -> None:
    """gh IS installed here. Prove the stub wins the PATH lookup."""
    assert shutil.which("gh") is not None, (
        "gh is absent on this host, so the shadowing guard below proves nothing; "
        "the other guards (GH_CONFIG_DIR, GH_TOKEN) still hold, but re-read this "
        "file's docstring before trusting it."
    )
    path = _stub_path(tmp_path, "control")
    found = shutil.which("gh", path=path)
    assert found is not None
    assert found.startswith(str(tmp_path)), (
        "gh resolved to %s, outside the scratch stub; a real Release is reachable" % found
    )


def test_both_subjects_exist() -> None:
    assert TWIN.is_file(), "the bash twin moved: %s" % TWIN
    assert PORT.is_file(), "the port moved: %s" % PORT


# --------------------------------------------------------------------------- The refusal, which is the behaviour worth more than the gh call ---------------------------------------------------------------------------


def test_no_assets_refuses_and_never_calls_gh(tmp_path: pathlib.Path) -> None:
    """An assetless Release looks published and installs nothing."""
    old, new = run_both(tmp_path)
    assert old[0] == 1
    assert old[1] == NO_ASSETS, "the annotation is a plain echo, so it lands on STDOUT"
    assert old[2] == ""
    assert old[3] == [], "gh ran despite there being nothing to upload"
    assert_agree(old, new, "no-assets")


def test_empty_dist_directories_still_refuse(tmp_path: pathlib.Path) -> None:
    """The directories exist and match the glob; they are not FILES."""
    old, new = run_both(tmp_path, assets=("dist/cli/", "dist/packages/"))
    assert old[0] == 1
    assert old[1] == NO_ASSETS
    assert old[3] == []
    assert_agree(old, new, "empty-dirs")


def test_a_directory_tree_with_no_files_refuses(tmp_path: pathlib.Path) -> None:
    old, new = run_both(tmp_path, assets=("dist/cli/v1/sub/", "dist/packages/deb/"))
    assert old[0] == 1
    assert old[3] == []
    assert_agree(old, new, "dirs-only")


# --------------------------------------------------------------------------- The gh invocation ---------------------------------------------------------------------------


def test_the_full_invocation_is_byte_identical(tmp_path: pathlib.Path) -> None:
    old, new = run_both(tmp_path, assets=("dist/cli/rdc-linux-x64", "dist/packages/rdc.deb"))
    assert old[0] == 0
    assert old[3] == [
        (
            "call: gh release create v1.2.3 --title v1.2.3 --target "
            "0123456789abcdef0123456789abcdef01234567 --generate-notes --repo "
            "acme/widget dist/cli/rdc-linux-x64 dist/packages/rdc.deb"
        )
    ]
    assert old[1] == "https://github.com/acme/widget/releases/tag/v1.2.3\n"
    assert_agree(old, new, "full-invocation")


def test_the_asset_paths_are_relative_to_the_repo_root(tmp_path: pathlib.Path) -> None:
    """The twin globs after `cd "$(get_repo_root)"`, so `gh` sees `dist/...`.

    Absolute paths would still upload, so nothing would look wrong; they would just make the two sides' argv differ, which is the whole comparison.
    """
    old, new = run_both(tmp_path, assets=("dist/cli/rdc-mac-arm64",))
    assert _assets_of(old[3][0]) == ["dist/cli/rdc-mac-arm64"]
    assert not any(part.startswith("/") for part in _assets_of(old[3][0]))
    assert_agree(old, new, "relative-assets")


def test_cli_assets_come_before_packages_assets(tmp_path: pathlib.Path) -> None:
    """`dist/cli/zzz.bin` precedes `dist/packages/aaa.deb`, not the other way.

    AND THIS CASE CANNOT SEPARATE THE TWO SORT STRATEGIES, which is worth recording because it looks as though it does. A plant that replaced the per-pattern sort with a sort of the UNION left every case in this file green: `dist/cli` and `dist/packages` are disjoint prefixes and `c` < `p`, so for THESE two patterns the union sort and the concatenation of two per-pattern sorts are
    the same list, necessarily. What this case pins is that the two groups appear in the twin's order at all -- worth pinning, just not the thing the earlier wording claimed. `test_release_assets_sorts_each_pattern_separately` is the case that actually discriminates, and the plant does fire there.
    """
    old, new = run_both(tmp_path, assets=("dist/cli/zzz.bin", "dist/packages/aaa.deb"))
    assert _assets_of(old[3][0]) == ["dist/cli/zzz.bin", "dist/packages/aaa.deb"]
    assert_agree(old, new, "pattern-order")


def test_release_assets_sorts_each_pattern_separately(tmp_path: pathlib.Path, monkeypatch) -> None:
    """Each pattern's matches are sorted ALONE, then concatenated.

    Driven through the exported helper with the two patterns REVERSED, because that is the only arrangement in which the two strategies disagree: with `dist/packages/**/*` first, per-pattern sorting yields packages then cli,
    while sorting the union yields cli then packages. The live `ASSET_PATTERNS`
    cannot show the difference (see the case above), so without this one a port that sorted the union would be indistinguishable and the twin's
    `assets=(A B)` array semantics would be unpinned.
    """
    root = _fixture(tmp_path, "sortorder", ("dist/cli/zzz.bin", "dist/packages/aaa.deb"))
    monkeypatch.setattr(port, "ASSET_PATTERNS", ("dist/packages/**/*", "dist/cli/**/*"))
    assert port.release_assets(str(root)) == ["dist/packages/aaa.deb", "dist/cli/zzz.bin"], (
        "the helper sorted the union of both patterns instead of each pattern alone"
    )


def test_glob_order_is_bytewise_not_a_directory_walk(tmp_path: pathlib.Path) -> None:
    """The case that separates `sorted()` from `os.walk`. See the docstring."""
    old, new = run_both(
        tmp_path,
        assets=("dist/cli/v1/a.bin", "dist/cli/v1-x", "dist/cli/v1.y"),
    )
    assert _assets_of(old[3][0]) == ["dist/cli/v1-x", "dist/cli/v1.y", "dist/cli/v1/a.bin"], (
        "the twin's glob order moved; re-derive the port's sort"
    )
    assert_agree(old, new, "glob-order")


def test_nested_assets_are_uploaded_and_directories_are_not(tmp_path: pathlib.Path) -> None:
    old, new = run_both(
        tmp_path,
        assets=(
            "dist/cli/top.bin",
            "dist/cli/v1/a.bin",
            "dist/cli/v1/sub/z.bin",
            "dist/cli/v1/sub/b.bin",
            "dist/packages/deb/x.deb",
            "dist/packages/p.txt",
            "dist/packages/rpm/",
        ),
    )
    assert _assets_of(old[3][0]) == [
        "dist/cli/top.bin",
        "dist/cli/v1/a.bin",
        "dist/cli/v1/sub/b.bin",
        "dist/cli/v1/sub/z.bin",
        "dist/packages/deb/x.deb",
        "dist/packages/p.txt",
    ]
    assert_agree(old, new, "nested")


def test_dotfiles_are_skipped_by_both(tmp_path: pathlib.Path) -> None:
    """No `dotglob` on one side, and `glob` skips leading dots on the other."""
    old, new = run_both(tmp_path, assets=("dist/cli/.hidden", "dist/cli/visible.bin"))
    assert _assets_of(old[3][0]) == ["dist/cli/visible.bin"]
    assert_agree(old, new, "dotfiles")


def test_a_symlink_to_a_file_is_uploaded(tmp_path: pathlib.Path) -> None:
    """`[[ -f ]]` follows symlinks, and so does `os.path.isfile`."""
    old, new = run_both(
        tmp_path,
        assets=("dist/cli/real.bin",),
        link=("dist/cli/real.bin", "dist/cli/alias.bin"),
    )
    assert _assets_of(old[3][0]) == ["dist/cli/alias.bin", "dist/cli/real.bin"]
    assert_agree(old, new, "symlink-file")


def test_a_symlink_to_a_directory_is_not_uploaded(tmp_path: pathlib.Path) -> None:
    old, new = run_both(
        tmp_path,
        assets=("dist/cli/v1/a.bin",),
        link=("dist/cli/v1", "dist/cli/alias"),
    )
    assert "dist/cli/alias" not in _assets_of(old[3][0])
    assert "dist/cli/v1/a.bin" in _assets_of(old[3][0])
    assert_agree(old, new, "symlink-dir")


def test_only_the_packages_pattern_matching_is_enough(tmp_path: pathlib.Path) -> None:
    old, new = run_both(tmp_path, assets=("dist/packages/rdc.rpm",))
    assert old[0] == 0
    assert _assets_of(old[3][0]) == ["dist/packages/rdc.rpm"]
    assert_agree(old, new, "packages-only")


def test_a_failing_gh_propagates_its_exit_code(tmp_path: pathlib.Path) -> None:
    old, new = run_both(tmp_path, assets=("dist/cli/rdc-linux-x64",), FAKE_GH_RC="1")
    assert old[0] == 1
    assert old[2] == "gh: HTTP 422 release already exists\n"
    assert_agree(old, new, "gh-rc-1")


def test_a_gh_exit_other_than_one_is_propagated_verbatim(tmp_path: pathlib.Path) -> None:
    """`set -e` hands bash the child's status; the port returns it too. A port
    that collapsed every failure to 1 would hide `gh`'s own codes."""
    old, new = run_both(tmp_path, assets=("dist/cli/rdc-linux-x64",), FAKE_GH_RC="7")
    assert old[0] == 7
    assert_agree(old, new, "gh-rc-7")


def test_the_version_is_v_prefixed_exactly_once(tmp_path: pathlib.Path) -> None:
    old, new = run_both(tmp_path, assets=("dist/cli/rdc",), VERSION="9.9.9")
    assert "gh release create v9.9.9 --title v9.9.9 " in old[3][0]
    assert_agree(old, new, "version-prefix")


# --------------------------------------------------------------------------- Refusals, before anything is globbed ---------------------------------------------------------------------------


def test_missing_gh_refuses_identically(tmp_path: pathlib.Path) -> None:
    """`require_cmd gh` runs FIRST, before VERSION is even read.

    Byte-identical including the `✗ ` marker: `common.sh:log_error` on one side and `rediacc_ci.log.error` on the other agree on this message.
    """
    old, new = run_both(tmp_path, assets=("dist/cli/rdc",), stub_gh=False)
    assert old[0] == 1
    assert old[2] == "✗ Required command 'gh' is not available\n"
    assert old[1] == ""
    assert new[0] == 1
    assert new[2] == old[2]
    assert new[1] == ""
    assert old[3] == []
    assert new[3] == []


def test_gh_is_required_before_version(tmp_path: pathlib.Path) -> None:
    """With both missing, both sides must name gh, not VERSION."""
    old, new = run_both(tmp_path, assets=("dist/cli/rdc",), stub_gh=False, VERSION=None)
    assert "gh" in old[2]
    assert "VERSION" not in old[2]
    assert "gh" in new[2]
    assert "VERSION" not in new[2]
    assert old[0] == new[0] == 1


def _missing(tmp_path: pathlib.Path, name: str) -> tuple[tuple, tuple]:
    return run_both(tmp_path, assets=("dist/cli/rdc",), **{name: None})


def test_missing_version_refuses(tmp_path: pathlib.Path) -> None:
    old, new = _missing(tmp_path, "VERSION")
    assert old[0] == 1
    assert new[0] == 1
    assert "VERSION" in old[2]
    assert "must be set" in old[2]
    assert "VERSION" in new[2]
    assert "must be set" in new[2]
    assert old[3] == []
    assert new[3] == []


def test_missing_github_sha_refuses(tmp_path: pathlib.Path) -> None:
    old, new = _missing(tmp_path, "GITHUB_SHA")
    assert old[0] == 1
    assert new[0] == 1
    assert "GITHUB_SHA" in old[2]
    assert "must be set" in old[2]
    assert "GITHUB_SHA" in new[2]
    assert "must be set" in new[2]
    assert old[3] == []
    assert new[3] == []


def test_missing_github_repository_refuses(tmp_path: pathlib.Path) -> None:
    old, new = _missing(tmp_path, "GITHUB_REPOSITORY")
    assert old[0] == 1
    assert new[0] == 1
    assert "GITHUB_REPOSITORY" in old[2]
    assert "must be set" in old[2]
    assert "GITHUB_REPOSITORY" in new[2]
    assert "must be set" in new[2]
    assert old[3] == []
    assert new[3] == []


def test_an_empty_version_refuses_like_an_unset_one(tmp_path: pathlib.Path) -> None:
    """`${VERSION:?}` is the colon form. A port testing only presence would
    publish a Release tagged `v`."""
    old, new = run_both(tmp_path, assets=("dist/cli/rdc",), VERSION="")
    assert old[0] == 1
    assert new[0] == 1
    assert "VERSION" in old[2]
    assert "VERSION" in new[2]
    assert old[3] == []
    assert new[3] == []


# --------------------------------------------------------------------------- The pure helper, and anti-vacuity ---------------------------------------------------------------------------


def test_release_assets_helper_agrees_with_the_subprocess(tmp_path: pathlib.Path) -> None:
    """The exported helper is what the differential's argv assertions rest on."""
    root = _fixture(
        tmp_path,
        "helper",
        ("dist/cli/b.bin", "dist/cli/a.bin", "dist/packages/z.deb", "dist/packages/dir/"),
    )
    assert port.release_assets(str(root)) == [
        "dist/cli/a.bin",
        "dist/cli/b.bin",
        "dist/packages/z.deb",
    ]


def test_the_harness_actually_compared_something(tmp_path: pathlib.Path) -> None:
    """A fake that never ran would make every argv assertion above vacuous."""
    old, new = run_both(tmp_path, assets=("dist/cli/rdc",))
    assert len(old[3]) == 1, "the twin never called gh"
    assert len(new[3]) == 1, "the port never called gh"
    assert len(_assets_of(old[3][0])) == 1
