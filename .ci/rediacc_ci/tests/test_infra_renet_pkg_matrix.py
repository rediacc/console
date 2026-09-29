"""`rediacc_ci.infra.renet_pkg_matrix`: the Renet pkg matrix checks and the PR scope decision.

Every case drives the module with captured command output (dnf5, dnf4 and zypper text measured in Docker on 2026-09-29) or a fake exec, so nothing starts a container. The verdicts that carry the design, each with its control:

  * the lock check reads only zypper's upgrade and downgrade sections, so the notice naming every LOCKED package does not red it, while a Ceph package in the upgrade section does;
  * a dnf dry run that never resolved is a failure, not an empty (passing) transaction;
  * the drift check names the distro and the version when the pinned build is gone from its repository;
  * the pin comparison ignores an epoch the pin does not state (Fedora) and enforces one it does (el10);
  * scope runs every non-PR event, and on a PR only a watched console path, a watched path inside the renet submodule, or the full-ci label.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from rediacc_ci.infra import renet_pkg_matrix as m

if TYPE_CHECKING:
    from collections.abc import Sequence

DNF5_LOCKED = """Updating and loading repositories:
Repositories loaded.
Package                                  Arch   Version                     Repository                            Size
Upgrading:
 curl                                    x86_64 8.15.0-10.fc43              updates                          461.4 KiB
   replacing curl                        x86_64 8.15.0-8.fc43               b19937cf82db4c2c8570d3daf4365919 461.4 KiB

Transaction Summary:
 Upgrading:         1 package
 Replacing:         1 package
"""

DNF5_UNLOCKED = """Upgrading:
 ceph-common                             x86_64 2:19.2.6-1.fc43             updates                           93.6 MiB
   replacing ceph-common                 x86_64 2:19.2.3-8.fc43             fedora                            93.7 MiB
 librados2                               x86_64 2:19.2.6-1.fc43             updates                           17.7 MiB

Transaction Summary:
"""

DNF4_LOCKED = """ Package        Arch       Version                 Repository              Size
================================================================================
Upgrading:
 curl           x86_64     8.12.1-4.el10_2.6       ol10_baseos_latest     260 k

Transaction Summary
================================================================================
Upgrade  1 Package
Operation aborted.
"""

DNF4_UNLOCKED = """Upgrading:
 ceph-common            x86_64  2:19.2.6-2.el10s      rediacc-ceph-squid   22 M
 cephadm                noarch  2:19.2.6-2.el10s      rediacc-ceph-squid  461 k
Transaction Summary
"""

ZYPPER_LOCKED = """Loading repository data...
Reading installed packages...

The following 12 items are locked and will not be changed by any action:
 Installed:
  ceph-common cephadm libcephfs2 librados2 librbd1 librgw2 python3-ceph-argparse python3-rados

The following 2 packages are going to be upgraded:
  patterns-base-fips patterns-base-minimal_base

The following 2 patterns are going to be upgraded:
  fips minimal_base

The following 5 NEW packages are going to be installed:
  libbrotlicommon1 libcurl4

2 packages to upgrade, 5 new, 1 to remove.
"""

ZYPPER_MOVING = """Reading installed packages...

The following package is going to be upgraded:
  ceph-common

1 package to upgrade.
"""

ZYPPER_SEARCH = """Reading installed packages...

S  | Name        | Type    | Version           | Arch   | Repository
---+-------------+---------+-------------------+--------+----------------------------------------------------
il | ceph-common | package | 19.2.3-lp160.2.96 | x86_64 | filesystems:ceph:squid (Leap 16.0), pinned by renet
il | cephadm     | package | 19.2.3-lp160.2.96 | noarch | filesystems:ceph:squid (Leap 16.0), pinned by renet
"""

PIN_TEXT = """# comment with host.fake=1
image=quay.io/ceph/ceph:v19.2.3-20250717
host-version=19.2.3
host.fedora-43=19.2.3-8.fc43
host.el10=2:19.2.3-1.el10s
host.opensuse-16.0=19.2.3-lp160.2.96
"""


class FakeExec:
    """Answers each argv by the first matching (prefix, Result) rule and records the calls."""

    def __init__(self, rules: list[tuple[tuple[str, ...], m.Result]]) -> None:
        self.rules = rules
        self.calls: list[list[str]] = []

    def __call__(self, argv: Sequence[str]) -> m.Result:
        self.calls.append(list(argv))
        for prefix, res in self.rules:
            if tuple(argv[: len(prefix)]) == prefix:
                return res
        return m.Result(0, "", "")


OK = m.Result(0, "", "")


def test_read_pins_takes_host_version_and_every_host_line() -> None:
    pins = m.read_pins(PIN_TEXT)
    assert pins.host_version == "19.2.3"
    assert pins.hosts == {
        "fedora-43": "19.2.3-8.fc43",
        "el10": "2:19.2.3-1.el10s",
        "opensuse-16.0": "19.2.3-lp160.2.96",
    }


def test_read_pins_refuses_a_file_without_host_version() -> None:
    with pytest.raises(ValueError, match="host-version"):
        m.read_pins("host.el10=2:19.2.3-1.el10s\n")


def test_every_distro_has_a_pin_in_the_real_file() -> None:
    pins = m.read_pins(m.PIN_FILE.read_text(encoding="utf-8"))
    assert {d.target for d in m.DISTROS.values()} <= set(pins.hosts)


@pytest.mark.parametrize(
    ("pin", "installed", "ok"),
    [
        ("19.2.3-8.fc43", "2:19.2.3-8.fc43", True),  # Fedora: the pin states no epoch
        ("2:19.2.3-1.el10s", "2:19.2.3-1.el10s", True),
        ("2:19.2.3-1.el10s", "19.2.3-1.el10s", False),  # the pin's epoch is enforced
        ("19.2.3-8.fc43", "2:19.2.6-1.fc43", False),  # control: a moved version
        ("19.2.3-8.fc43", "", False),
    ],
)
def test_evr_matches(pin: str, installed: str, ok: bool) -> None:
    assert m.evr_matches(pin, installed) is ok


def test_rpm_versions_strips_an_absent_epoch() -> None:
    got = m.rpm_versions(
        "ceph-common (none):19.2.3-lp160.2.96\ncephadm 2:19.2.3-8.fc43\npackage x is not installed\n"
    )
    assert got == {"ceph-common": "19.2.3-lp160.2.96", "cephadm": "2:19.2.3-8.fc43"}


@pytest.mark.parametrize(("text", "want"), [(DNF5_LOCKED, []), (DNF4_LOCKED, [])])
def test_dnf_rows_of_a_locked_run_name_no_ceph(text: str, want: list[str]) -> None:
    assert m.dnf_ceph_rows(text) == want


@pytest.mark.parametrize(
    ("text", "want"),
    [(DNF5_UNLOCKED, ["ceph-common", "librados2"]), (DNF4_UNLOCKED, ["ceph-common", "cephadm"])],
)
def test_dnf_rows_of_an_unlocked_run_name_ceph(text: str, want: list[str]) -> None:
    assert m.dnf_ceph_rows(text) == want


def test_zypper_lock_notice_is_not_an_upgrade() -> None:
    names = m.zypper_changed(ZYPPER_LOCKED)
    assert names == ["patterns-base-fips", "patterns-base-minimal_base"]
    # Control: a grep over the whole output (the approach P2 found wrong) would have matched the lock notice.
    assert "ceph-common" in ZYPPER_LOCKED


def test_zypper_upgrade_section_with_ceph_is_seen() -> None:
    assert m.zypper_changed(ZYPPER_MOVING) == ["ceph-common"]


def _distro(name: str) -> m.Distro:
    return m.DISTROS[name]


def test_lock_passes_with_a_nonvacuous_control_on_dnf() -> None:
    run = FakeExec(
        [
            (
                ("dnf", "upgrade", "--assumeno", "--disableplugin=versionlock"),
                m.Result(1, DNF4_UNLOCKED, ""),
            ),
            (("dnf", "upgrade", "--assumeno"), m.Result(1, DNF4_LOCKED, "")),
        ]
    )
    v = m.check_lock(_distro("oracle-10"), run)
    assert v.ok
    assert not v.warning
    assert ["dnf", "upgrade", "--assumeno", "--disableplugin=versionlock"] in run.calls


def test_lock_fails_when_the_locked_run_moves_ceph() -> None:
    run = FakeExec([(("dnf", "upgrade"), m.Result(1, DNF5_UNLOCKED, ""))])
    v = m.check_lock(_distro("fedora-43"), run)
    assert not v.ok
    assert "ceph-common" in v.detail


def test_lock_fails_when_the_dry_run_never_resolved() -> None:
    run = FakeExec([(("dnf", "upgrade"), m.Result(1, "", "Error: Failed to download metadata"))])
    v = m.check_lock(_distro("rocky-10"), run)
    assert not v.ok
    assert "did not resolve" in v.detail


def test_lock_warns_when_the_control_offers_nothing() -> None:
    run = FakeExec([(("dnf", "upgrade"), m.Result(1, DNF5_LOCKED, ""))])
    v = m.check_lock(_distro("fedora-43"), run)
    assert v.ok
    assert "VACUOUS" in v.warning
    assert ["dnf", "upgrade", "--assumeno", "--setopt=disable_excludes=*"] in run.calls


def test_lock_on_zypper_reads_only_the_upgrade_sections() -> None:
    ok = m.check_lock(
        _distro("opensuse-16.0"), FakeExec([(("zypper",), m.Result(0, ZYPPER_LOCKED, ""))])
    )
    assert ok.ok
    bad = m.check_lock(
        _distro("opensuse-16.0"), FakeExec([(("zypper",), m.Result(0, ZYPPER_MOVING, ""))])
    )
    assert not bad.ok
    assert "ceph-common" in bad.detail


def test_drift_passes_when_the_pin_resolves_on_zypper() -> None:
    run = FakeExec([(("zypper",), m.Result(0, ZYPPER_SEARCH, ""))])
    v = m.check_drift("opensuse-16.0", _distro("opensuse-16.0"), "19.2.3-lp160.2.96", run)
    assert v.ok
    assert run.calls[0][:7] == ["zypper", "-n", "se", "-s", "--match-exact", "-r", m.CEPH_REPO_ID]


def test_drift_names_the_distro_and_version_when_the_build_is_gone() -> None:
    run = FakeExec([(("zypper",), m.Result(104, "No matching items found.\n", ""))])
    v = m.check_drift("opensuse-16.0", _distro("opensuse-16.0"), "19.2.3-lp160.2.96", run)
    assert not v.ok
    assert v.detail.startswith("DRIFT on opensuse-16.0: ceph-common, cephadm 19.2.3-lp160.2.96")


def test_drift_on_dnf_queries_the_pinned_repo_only() -> None:
    out = "ceph-common 2:19.2.3-1.el10s\n\ncephadm 2:19.2.3-1.el10s\n"
    run = FakeExec([(("dnf",), m.Result(0, out, ""))])
    v = m.check_drift("rocky-10", _distro("rocky-10"), "2:19.2.3-1.el10s", run)
    assert v.ok
    assert f"--repo={m.CEPH_REPO_ID}" in run.calls[0]
    assert "ceph-common-2:19.2.3-1.el10s" in run.calls[0]


def test_versions_fail_on_a_moved_package_and_a_wrong_rbd() -> None:
    run = FakeExec(
        [
            (("rpm",), m.Result(0, "ceph-common 2:19.2.6-1.fc43\ncephadm 2:19.2.3-8.fc43\n", "")),
            (("rbd",), m.Result(0, "ceph version 19.2.6 (abc) squid (stable)\n", "")),
        ]
    )
    rpm_v, rbd_v = m.check_versions(_distro("fedora-43"), "19.2.3-8.fc43", "19.2.3", run)
    assert not rpm_v.ok
    assert "2:19.2.6-1.fc43" in rpm_v.detail
    assert not rbd_v.ok


def test_no_podman_fails_when_podman_is_on_path() -> None:
    run = FakeExec(
        [
            (("rpm",), m.Result(1, "package podman is not installed\n", "")),
            (("sh",), m.Result(0, "/usr/bin/podman\n", "")),
        ]
    )
    assert not m.check_no_podman(run).ok
    assert m.check_no_podman(
        FakeExec([(("rpm",), m.Result(1, "", "")), (("sh",), m.Result(1, "", ""))])
    ).ok


def test_run_checks_runs_every_step_even_after_a_failure() -> None:
    pins = m.read_pins(PIN_TEXT)
    run = FakeExec(
        [
            (("renet", "ceph", "install", "--profile", "admin"), m.Result(1, "", "boom")),
            (
                ("dnf", "-q", "repoquery"),
                m.Result(0, "ceph-common 2:19.2.3-8.fc43\ncephadm 2:19.2.3-8.fc43\n", ""),
            ),
            (
                ("rpm", "-q", "--qf"),
                m.Result(0, "ceph-common 2:19.2.3-8.fc43\ncephadm 2:19.2.3-8.fc43\n", ""),
            ),
            (("rpm", "-q", "podman"), m.Result(1, "", "")),
            (("sh",), m.Result(1, "", "")),
            (("rbd",), m.Result(0, "ceph version 19.2.3 (x) squid (stable)\n", "")),
            (
                ("dnf", "upgrade", "--assumeno", "--setopt=disable_excludes=*"),
                m.Result(1, DNF5_UNLOCKED, ""),
            ),
            (("dnf", "upgrade"), m.Result(1, DNF5_LOCKED, "")),
        ]
    )
    verdicts = m.run_checks("fedora-43", _distro("fedora-43"), pins, run)
    names = [v.name for v in verdicts]
    assert names[0] == "ceph install --profile admin"
    assert not verdicts[0].ok
    assert "gpu resolve-only (amd)" in names
    assert "gpu resolve-only (nvidia)" in names
    assert [v.name for v in verdicts if not v.ok] == ["ceph install --profile admin"]
    assert m.report("fedora-43", verdicts) == 1
    assert m.report("fedora-43", verdicts[1:]) == 0


def test_run_checks_invokes_the_p5_gpu_flag_by_name() -> None:
    run = FakeExec([])
    m.run_checks("fedora-43", _distro("fedora-43"), m.read_pins(PIN_TEXT), run)
    gpu = [c for c in run.calls if c[:2] == ["renet", "setup"]]
    assert len(gpu) == 2
    assert all("--gpu-resolve-only" in c for c in gpu)


@pytest.mark.parametrize("event", ["schedule", "workflow_dispatch"])
def test_scope_runs_every_non_pr_event(event: str) -> None:
    assert m.scope_decision(event, "", [], None)[0]


def test_scope_skips_a_pr_touching_nothing_watched() -> None:
    hit, reason = m.scope_decision(
        "pull_request", "docs", ["packages/www/x.ts", "private/renet"], ["cmd/renet/ops_up.go"]
    )
    assert not hit
    assert reason == "no watched path changed"


@pytest.mark.parametrize(
    ("console", "renet"),
    [
        ([".ci/rediacc_ci/infra/renet_pkg_matrix.py"], None),
        (["private/renet"], ["pkg/infra/cephpkg/cephpkg.go"]),
        (["private/renet"], [".ceph-image-pin"]),
        (["private/renet"], ["cmd/renet/gpu_drivers.go"]),
    ],
)
def test_scope_hits_a_watched_path(console: list[str], renet: list[str] | None) -> None:
    assert m.scope_decision("pull_request", "", console, renet)[0]


def test_scope_prefix_match_needs_a_directory_entry() -> None:
    # "pkg/infra/ceph/" must not match pkg/infra/cephfoo/x.go; a file entry must match exactly.
    assert not m.scope_decision("pull_request", "", ["private/renet"], ["pkg/infra/cephfoo/x.go"])[
        0
    ]
    assert not m.scope_decision(
        "pull_request", "", ["private/renet"], ["cmd/renet/ceph_install_test.go"]
    )[0]


def test_scope_full_ci_label_forces_a_hit() -> None:
    assert m.scope_decision("pull_request", "bump-none,full-ci", [], None)[0]
    assert not m.scope_decision("pull_request", "full-ci-maybe", [], None)[0]


def test_a_failed_command_leads_with_renets_error_not_the_usage_text() -> None:
    out = 'time="t" level=warning msg="kernel headers install: all 3 install attempts failed"\n'
    err = (
        "Error: failed to install the Nvidia driver: exit status 1\nUsage:\n  renet setup [flags]\n"
        + "      --flag x\n" * 20
    )
    v = m.check_command("gpu", ["renet", "setup"], FakeExec([(("renet",), m.Result(1, out, err))]))
    assert not v.ok
    assert v.detail.splitlines()[0].endswith(
        "(Error: failed to install the Nvidia driver: exit status 1)"
    )
    assert "kernel headers install" in v.detail
