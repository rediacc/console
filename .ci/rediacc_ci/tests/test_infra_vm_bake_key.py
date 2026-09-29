"""`rediacc_ci.infra.vm_bake_key`: the pre-baked VM image key and its completeness walk.

Every case except the real-tree one runs on a COPY of the renet inputs (go.mod, the lock file, every Go file of cmd/renet and of each classified package), so a fixture edit never touches private/renet and the copy stays faithful to the code the key really hashes. The cases skip when private/renet is not checked out.

The three verdicts the box asks for, each with its control:

  * a new internal import in setup_command.go fails the completeness walk, while the same
    edit importing an EXCLUDED package does not (so the red is about classification, not about
    any edit to the file);
  * touching an excluded path leaves the key unchanged;
  * touching an included path changes it.
"""

from __future__ import annotations

import shutil
from typing import TYPE_CHECKING

import pytest

from rediacc_ci import paths
from rediacc_ci.infra import vm_bake_key as vbk

if TYPE_CHECKING:
    import pathlib

REAL_RENET = paths.repo_root() / "private" / "renet"

pytestmark = pytest.mark.skipif(
    not (REAL_RENET / "cmd" / "renet" / "setup_command.go").is_file(),
    reason="private/renet is not checked out",
)

MONTH = "2026-09"
DISTRO = "debian-13"
NEW_IMPORT = '\t"github.com/rediacc/renet/pkg/nodeteardown"\n'


def _copy_inputs(dest: pathlib.Path) -> pathlib.Path:
    dest.mkdir(parents=True)
    for name in ("go.mod", *vbk.EXTRA_FILES):
        (dest / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REAL_RENET / name, dest / name)
    dirs = set(vbk.PACKAGES) | {"cmd/renet", "pkg/embed/proxy"}
    for pkg in sorted(dirs):
        src = REAL_RENET / pkg
        (dest / pkg).mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            for f in src.iterdir():
                if f.is_file():
                    shutil.copy2(f, dest / pkg / f.name)
    return dest


@pytest.fixture
def renet(tmp_path: pathlib.Path) -> pathlib.Path:
    return _copy_inputs(tmp_path / "renet-a")


def _key(root: pathlib.Path) -> str:
    return vbk.compute_key(root, DISTRO, MONTH)


def _append(path: pathlib.Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(text)


def _add_import(root: pathlib.Path, line: str) -> None:
    setup = root / "cmd" / "renet" / "setup_command.go"
    text = setup.read_text(encoding="utf-8")
    assert "\nimport (\n" in text
    setup.write_text(text.replace("\nimport (\n", "\nimport (\n" + line, 1), encoding="utf-8")


def test_the_real_tree_is_completely_classified() -> None:
    assert vbk.findings(REAL_RENET) == []


def test_the_key_has_the_planned_shape(renet: pathlib.Path) -> None:
    key = _key(renet)
    assert vbk.KEY_RE.match(key), key
    assert key.startswith("vm-bake-v1-debian-13-2026-09-")


def test_two_trees_with_the_same_inputs_give_the_same_key(
    renet: pathlib.Path, tmp_path: pathlib.Path
) -> None:
    # Copied from the fixture rather than from private/renet again: another session may be
    # editing the live tree between two copies, and that would be a real input change.
    other = tmp_path / "renet-b"
    shutil.copytree(renet, other)
    assert _key(renet) == _key(other)


def test_a_new_internal_import_in_setup_command_fails_the_walk(renet: pathlib.Path) -> None:
    _add_import(renet, NEW_IMPORT)
    _append(renet / "cmd" / "renet" / "setup_command.go", "\nvar _ = nodeteardown.Probe\n")
    problems = vbk.findings(renet)
    assert any("imports pkg/nodeteardown" in p for p in problems), problems
    with pytest.raises(vbk.BakeKeyError, match="pkg/nodeteardown"):
        _key(renet)


def test_control_importing_an_excluded_package_is_not_a_finding(renet: pathlib.Path) -> None:
    _add_import(renet, '\t"github.com/rediacc/renet/pkg/infra/vm"\n')
    assert vbk.findings(renet) == []


def test_a_same_package_call_into_an_unclassified_file_fails(renet: pathlib.Path) -> None:
    cmd = renet / "cmd" / "renet"
    (cmd / "bake_probe_helper.go").write_text(
        'package main\n\nfunc bakeProbeHelper() string { return "x" }\n', encoding="utf-8"
    )
    _append(cmd / "setup_command.go", "\nvar bakeProbe = bakeProbeHelper()\n")
    problems = vbk.findings(renet)
    assert any("bake_probe_helper.go" in p and "bakeProbeHelper" in p for p in problems), problems


def test_a_qualified_ref_into_an_unclassified_file_of_a_partial_package_fails(
    renet: pathlib.Path,
) -> None:
    (renet / "pkg" / "infra" / "opsconfig" / "bake_probe.go").write_text(
        'package opsconfig\n\nfunc BakeProbe() string { return "x" }\n', encoding="utf-8"
    )
    _append(renet / "pkg" / "infra" / "image" / "builder.go", "\nvar _ = opsconfig.BakeProbe()\n")
    problems = vbk.findings(renet)
    assert any("opsconfig.BakeProbe" in p for p in problems), problems


def test_every_embedded_gpu_key_is_a_hashed_input() -> None:
    """A fourth key added under cmd/renet/gpu_keys/ without a line in EXTRA_FILES would change what setup trusts and not the key."""
    on_disk = {
        p.relative_to(REAL_RENET).as_posix()
        for p in (REAL_RENET / "cmd" / "renet" / "gpu_keys").iterdir()
        if p.is_file()
    }
    assert on_disk, "no GPU keys found: the directory moved?"
    hashed = {p.relative_to(REAL_RENET).as_posix() for p in vbk.hashed_files(REAL_RENET)}
    assert on_disk <= hashed, sorted(on_disk - hashed)


def test_a_new_gpu_key_file_is_not_hashed_until_it_is_listed(renet: pathlib.Path) -> None:
    """Control for the test above: an unlisted key file changes nothing, so listing it is what makes it an input."""
    before = _key(renet)
    (renet / "cmd" / "renet" / "gpu_keys" / "NEWKEY.pub").write_text("key\n", encoding="utf-8")
    assert _key(renet) == before
    assert "cmd/renet/gpu_keys/NEWKEY.pub" not in {
        p.relative_to(renet).as_posix() for p in vbk.hashed_files(renet)
    }


def test_a_classified_file_that_disappears_is_a_finding(renet: pathlib.Path) -> None:
    (renet / "cmd" / "renet" / "literals.go").unlink()
    problems = vbk.findings(renet)
    assert any("cmd/renet/literals.go" in p and "missing" in p for p in problems), problems


@pytest.mark.parametrize(
    "rel",
    [
        "pkg/embed/proxy/docker-compose.yml",
        "pkg/embed/assets/amd64/base/criu",
        "pkg/datastore/btrfs.go",
        "pkg/i18n/i18n.go",
        "pkg/infra/vm/kvm/driver.go",
        "pkg/infra/opsconfig/config.go",
        "pkg/config/config_test.go",
        "pkg/config/VAULT_PARSING.md",
        # cephpkg's pins, plans and embedded Ceph keys shape no image; only fingerprint.go is an input.
        "pkg/infra/cephpkg/cephpkg.go",
        "pkg/infra/cephpkg/keys/RPM-GPG-KEY-CentOS-SIG-Storage",
        "cmd/renet/main.go",
        "cmd/renet/repository_up.go",
        "cmd/renet/setup_command_test.go",
        "README.md",
    ],
)
def test_touching_an_excluded_path_leaves_the_key_unchanged(renet: pathlib.Path, rel: str) -> None:
    before = _key(renet)
    _append(renet / rel, "\n// touched by test_infra_vm_bake_key\n")
    assert _key(renet) == before


@pytest.mark.parametrize(
    "rel",
    [
        "cmd/renet/setup_command.go",
        "cmd/renet/pkg_install_retry.go",
        "cmd/renet/image_build_command.go",
        "cmd/renet/system_commands.go",
        # the GPU driver installs of setup: the flow, its runner, the fingerprint check and every embedded NVIDIA key
        "cmd/renet/gpu_drivers.go",
        "cmd/renet/ceph_host_runner.go",
        "pkg/infra/cephpkg/fingerprint.go",
        "cmd/renet/gpu_keys/CDF6BA43.pub",
        "cmd/renet/gpu_keys/1940C73E.pub",
        "cmd/renet/gpu_keys/3A8B5622.pub",
        "pkg/infra/pkgset/pkgset.go",
        "pkg/infra/opsconfig/images.go",
        "pkg/infra/image/one_shot_builder.go",
        "pkg/config/paths.go",
        "pkg/embed/embed.go",
        "embed-assets.lock.json",
        "pkg/infra/pkgset/added_later.go",
    ],
)
def test_control_touching_an_included_path_changes_the_key(renet: pathlib.Path, rel: str) -> None:
    before = _key(renet)
    path = renet / rel
    if not path.exists():
        path.write_text("package pkgset\n", encoding="utf-8")
    else:
        _append(path, "\n// touched by test_infra_vm_bake_key\n" if rel.endswith(".go") else "\n")
    assert _key(renet) != before


def test_distro_and_month_only_change_their_own_fields(renet: pathlib.Path) -> None:
    a = vbk.compute_key(renet, "debian-13", "2026-09")
    b = vbk.compute_key(renet, "ubuntu-24.04", "2026-10")
    assert a.rsplit("-", 1)[1] == b.rsplit("-", 1)[1]
    assert b.startswith("vm-bake-v1-ubuntu-24.04-2026-10-")


@pytest.mark.parametrize(
    ("distro", "month", "needle"),
    [("nope-1", "2026-09", "unknown distro"), ("debian-13", "2026-13", "YYYY-MM")],
)
def test_bad_arguments_are_refused(
    renet: pathlib.Path, distro: str, month: str, needle: str
) -> None:
    with pytest.raises(vbk.BakeKeyError, match=needle):
        vbk.compute_key(renet, distro, month)


def test_cli_prints_the_key_on_stdout(
    renet: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = vbk.main(["--renet-root", str(renet), "--distro", DISTRO, "--month", MONTH])
    out, err = capsys.readouterr()
    assert (rc, out.strip(), err) == (0, _key(renet), "")


def test_cli_refuses_an_incomplete_tree_on_stderr(
    renet: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _add_import(renet, NEW_IMPORT)
    rc = vbk.main(["--renet-root", str(renet), "--distro", DISTRO, "--month", MONTH])
    out, err = capsys.readouterr()
    assert rc == 1
    assert out == ""
    assert "pkg/nodeteardown" in err
    assert vbk.main(["--renet-root", str(renet), "--check"]) == 1


def test_cli_lists_the_inputs(renet: pathlib.Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert vbk.main(["--renet-root", str(renet), "--list-inputs"]) == 0
    listed = capsys.readouterr().out.split()
    assert "cmd/renet/setup_command.go" in listed
    assert "embed-assets.lock.json" in listed
    assert "cmd/renet/gpu_drivers.go" in listed
    assert "cmd/renet/gpu_keys/CDF6BA43.pub" in listed
    assert not any(p.startswith("pkg/embed/proxy/") or p.endswith("_test.go") for p in listed)
