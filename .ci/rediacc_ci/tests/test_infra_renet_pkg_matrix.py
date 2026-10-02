"""`rediacc_ci.infra.renet_pkg_matrix`: the Renet pkg matrix checks and the PR scope decision.

Every case drives the module with captured command output (dnf5, dnf4 and zypper text measured in Docker on 2026-09-29) or a fake exec, so nothing starts a container. The verdicts that carry the design, each with its control:

  * the lock check reads only zypper's upgrade and downgrade sections, so the notice naming every LOCKED package does not red it, while a Ceph package in the upgrade section does;
  * a dnf dry run that never resolved is a failure, not an empty (passing) transaction;
  * the drift check names the distro and the version when the pinned build is gone from its repository;
  * the pin comparison ignores an epoch the pin does not state (Fedora) and enforces one it does (el10);
  * scope runs every non-PR event, and on a PR only a watched console path, a watched path inside the renet submodule, or the full-ci label.
  * OBS moved past the pin is a FAIL on the nightly with or without `--obs-mirror` (plan Q5); under `--obs-mirror` every other event reads upstream too and reports the move as a warning on a passing leg, whose installs come from the captured tree (the control: OBS serving the pin is a plain pass on every event).
  * `run --obs-mirror` mounts the fetched tree read-only at /srv/obs-mirror and writes /etc/rediacc/ceph-zypper-mirror before any check, a fetch miss is a FAIL naming the pin and the dispatch that fixes it (no container starts), and without the flag nothing is fetched, mounted or written (the control).
"""

from __future__ import annotations

import argparse
from typing import TYPE_CHECKING

import pytest

from rediacc_ci.infra import obs_mirror
from rediacc_ci.infra import renet_pkg_matrix as m
from rediacc_ci.well_known import ETC_DIR

if TYPE_CHECKING:
    import pathlib
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
il | ceph-common | package | 19.2.3-lp160.2.98 | x86_64 | filesystems:ceph:squid (Leap 16.0), pinned by renet
il | cephadm     | package | 19.2.3-lp160.2.98 | noarch | filesystems:ceph:squid (Leap 16.0), pinned by renet
"""

PIN_TEXT = """# comment with host.fake=1
image=quay.io/ceph/ceph:v19.2.3-20250717
host-version=19.2.3
host.fedora-43=19.2.3-8.fc43
host.el10=2:19.2.3-1.el10s
host.opensuse-16.0=19.2.3-lp160.2.98
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
        "opensuse-16.0": "19.2.3-lp160.2.98",
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
        "ceph-common (none):19.2.3-lp160.2.98\ncephadm 2:19.2.3-8.fc43\npackage x is not installed\n"
    )
    assert got == {"ceph-common": "19.2.3-lp160.2.98", "cephadm": "2:19.2.3-8.fc43"}


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
    v = m.check_drift("opensuse-16.0", _distro("opensuse-16.0"), "19.2.3-lp160.2.98", run)
    assert v.ok
    assert run.calls[0][:7] == ["zypper", "-n", "se", "-s", "--match-exact", "-r", m.CEPH_REPO_ID]


def test_drift_names_the_distro_and_version_when_the_build_is_gone() -> None:
    run = FakeExec([(("zypper",), m.Result(104, "No matching items found.\n", ""))])
    v = m.check_drift("opensuse-16.0", _distro("opensuse-16.0"), "19.2.3-lp160.2.98", run)
    assert not v.ok
    assert v.detail.startswith("DRIFT on opensuse-16.0: ceph-common, cephadm 19.2.3-lp160.2.98")


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


# --- check_upstream: OBS origin primary vs the Leap pin, scheduled runs only ---

LEAP_PIN = "19.2.3-lp160.2.98"
# A build OBS has moved to past the pin.
MOVED = "19.2.3-lp160.2.99"


class FakeUpstream:
    """Stands in for obs_upstream_evr: returns an EVR or raises, and counts the calls."""

    def __init__(self, evr: str = "", exc: BaseException | None = None) -> None:
        self.evr = evr
        self.exc = exc
        self.calls = 0

    def __call__(self) -> str:
        self.calls += 1
        if self.exc is not None:
            raise self.exc
        return self.evr


def test_upstream_is_red_when_obs_moved_past_the_pin() -> None:
    up = FakeUpstream(MOVED)
    v = m.check_upstream(LEAP_PIN, "schedule", up)
    assert up.calls == 1
    assert not v.ok
    assert not v.skipped
    assert MOVED in v.detail
    assert f"the pin is {LEAP_PIN}" in v.detail
    assert "one-line pin bump" in v.detail
    for site in (
        'cephpkg.go hostPins["opensuse-16.0"]',
        ".ceph-image-pin",
        "ceph_install_profile_test.go",
    ):
        assert site in v.detail


def test_upstream_is_green_when_obs_serves_the_pin() -> None:
    # Control for the red case: the same call with an equal EVR passes.
    up = FakeUpstream(LEAP_PIN)
    v = m.check_upstream(LEAP_PIN, "schedule", up)
    assert up.calls == 1
    assert v.ok
    assert not v.skipped


@pytest.mark.parametrize("event", ["pull_request", "push", "workflow_dispatch", ""])
def test_upstream_is_skipped_off_schedule_with_an_explicit_line(
    event: str, capsys: pytest.CaptureFixture[str]
) -> None:
    # A moved OBS off schedule must not even be fetched, let alone red the run.
    up = FakeUpstream(MOVED)
    v = m.check_upstream(LEAP_PIN, event, up)
    assert up.calls == 0
    assert v.ok
    assert v.skipped
    assert v.detail.startswith("skipped: nightly-only")
    assert m.report("opensuse-16.0", [v]) == 0
    out = capsys.readouterr().out
    assert "[SKIP] opensuse-16.0: upstream: OBS still serves the pin: skipped: nightly-only" in out
    assert "[PASS]" not in out
    assert "0/1 checks passed, 1 skipped" in out


@pytest.mark.parametrize(
    "exc",
    [
        OSError("urlopen error [Errno -3] Temporary failure in name resolution"),
        m.obs_mirror.MirrorError("gpgv refused repomd.xml (rc=1): BAD signature"),
        m.obs_mirror.ChecksumMismatchError("primary.xml.zst: sha256 mismatch"),
    ],
)
def test_upstream_failure_to_read_obs_is_a_failure_not_a_pass(exc: BaseException) -> None:
    v = m.check_upstream(LEAP_PIN, "schedule", FakeUpstream(exc=exc))
    assert not v.ok
    assert not v.skipped
    assert "could not read the OBS origin" in v.detail
    assert str(exc) in v.detail
    assert m.report("opensuse-16.0", [v]) == 1


def test_upstream_rides_the_zypper_leg_only() -> None:
    pins = m.read_pins(PIN_TEXT)
    moved = FakeUpstream(MOVED)
    leap = m.run_checks(
        "opensuse-16.0",
        _distro("opensuse-16.0"),
        pins,
        FakeExec([]),
        event="schedule",
        upstream=moved,
    )
    names = [v.name for v in leap]
    assert "upstream: OBS still serves the pin" in names
    assert (
        names.index("upstream: OBS still serves the pin")
        == names.index("mirror serves the pin") + 1
    )
    assert moved.calls == 1
    # Control: a dnf leg on the same schedule never calls it.
    other = FakeUpstream("x")
    fedora = m.run_checks(
        "fedora-43", _distro("fedora-43"), pins, FakeExec([]), event="schedule", upstream=other
    )
    assert other.calls == 0
    assert "upstream: OBS still serves the pin" not in [v.name for v in fedora]


# With --obs-mirror the leg installs the pin from the captured tree, so OBS moving is a FAIL only on the
# nightly (plan Q5) and a warning on every other event; without the mirror the nightly FAIL is unchanged.
OFF_SCHEDULE = ["pull_request", "push", "workflow_dispatch", ""]


def test_upstream_moved_with_the_mirror_is_red_on_the_nightly() -> None:
    up = FakeUpstream(MOVED)
    v = m.check_upstream(LEAP_PIN, "schedule", up, mirrored=True)
    assert up.calls == 1
    assert not v.ok
    assert not v.skipped
    assert v.detail.startswith("OBS REBUILT")
    assert MOVED in v.detail
    assert m.report("opensuse-16.0", [v]) == 1


@pytest.mark.parametrize("event", OFF_SCHEDULE)
def test_upstream_moved_with_the_mirror_is_a_warning_off_schedule(
    event: str, capsys: pytest.CaptureFixture[str]
) -> None:
    up = FakeUpstream(MOVED)
    v = m.check_upstream(LEAP_PIN, event, up, mirrored=True)
    assert up.calls == 1  # fetched, so the move is reported on every event
    assert v.ok
    assert not v.skipped
    assert MOVED in v.warning
    assert f"the pin is {LEAP_PIN}" in v.warning
    assert "one-line pin bump" in v.warning
    assert m.report("opensuse-16.0", [v]) == 0
    out = capsys.readouterr().out
    assert "::warning::opensuse-16.0: upstream: OBS still serves the pin: OBS REBUILT" in out
    assert "::error::" not in out


@pytest.mark.parametrize("event", OFF_SCHEDULE)
def test_upstream_unreadable_with_the_mirror_is_a_warning_off_schedule(event: str) -> None:
    v = m.check_upstream(
        LEAP_PIN, event, FakeUpstream(exc=OSError("name resolution")), mirrored=True
    )
    assert v.ok
    assert "could not read the OBS origin" in v.warning
    assert "name resolution" in v.warning


def test_upstream_unreadable_with_the_mirror_is_red_on_the_nightly() -> None:
    v = m.check_upstream(
        LEAP_PIN, "schedule", FakeUpstream(exc=OSError("name resolution")), mirrored=True
    )
    assert not v.ok
    assert "could not read the OBS origin" in v.detail


@pytest.mark.parametrize("event", ["schedule", *OFF_SCHEDULE])
def test_upstream_equal_with_the_mirror_is_a_plain_pass_on_every_event(event: str) -> None:
    # Control for the reds and warnings above: OBS serving the pin passes with no warning.
    v = m.check_upstream(LEAP_PIN, event, FakeUpstream(LEAP_PIN), mirrored=True)
    assert v.ok
    assert not v.warning
    assert not v.skipped


def test_run_cli_passes_the_event_through() -> None:
    parser_args = [
        "run",
        "--distro",
        "opensuse-16.0",
        "--renet",
        "/nonexistent/renet",
        "--event",
        "schedule",
    ]
    # A missing renet stops before any container or network: rc 2, and the parser accepted --event.
    assert m.main(parser_args) == 2


# ---------------------------------------------------------------------------
# run --obs-mirror (PLAN-renet-obs-mirror.md section 4 item 4)
# ---------------------------------------------------------------------------

LEAP_PIN_TEXT = PIN_TEXT  # host.opensuse-16.0=19.2.3-lp160.2.98
MIRROR_WRITE = (
    "mkdir -p "
    + ETC_DIR
    + " && printf '%s\\n' 'dir:/srv/obs-mirror' > "
    + ETC_DIR
    + "/ceph-zypper-mirror"
)


class FakeDocker:
    """The container seams of cmd_run: records the `docker run` argv, the exec calls and the removal."""

    def __init__(self, exec_rules: list[tuple[tuple[str, ...], m.Result]] | None = None) -> None:
        self.started: list[list[str]] = []
        self.stopped: list[str] = []
        self.exec = FakeExec(
            exec_rules
            if exec_rules is not None
            else [(("cat", obs_mirror.MIRROR_CONFIG), m.Result(0, "dir:/srv/obs-mirror\n", ""))]
        )

    def start(self, argv: Sequence[str]) -> int:
        self.started.append(list(argv))
        return 0

    def factory(self, _container: str) -> FakeExec:
        return self.exec

    def stop(self, container: str) -> None:
        self.stopped.append(container)


class FakeFetch:
    def __init__(self, exc: BaseException | None = None) -> None:
        self.exc = exc
        self.calls: list[tuple[str, pathlib.Path]] = []

    def __call__(self, pin: str, dest: pathlib.Path) -> None:
        self.calls.append((pin, dest))
        if self.exc is not None:
            raise self.exc
        dest.mkdir(parents=True, exist_ok=True)


def _run_args(tmp_path: pathlib.Path, distro: str, *, obs_mirror_flag: bool) -> argparse.Namespace:
    renet = tmp_path / "renet"
    renet.write_text("#!/bin/sh\n", encoding="utf-8")
    pin_file = tmp_path / ".ceph-image-pin"
    pin_file.write_text(LEAP_PIN_TEXT, encoding="utf-8")
    return argparse.Namespace(
        distro=distro,
        renet=str(renet),
        pin_file=str(pin_file),
        event="pull_request",
        obs_mirror=obs_mirror_flag,
        mirror_dir=str(tmp_path / "mirror-base"),
    )


def _drive(args: argparse.Namespace, fetch: FakeFetch, docker: FakeDocker) -> int:
    # OBS serving the pin: under --obs-mirror the upstream check reads OBS on every event, never the network here.
    return m.cmd_run(
        args,
        fetch=fetch,
        start=docker.start,
        exec_factory=docker.factory,
        stop=docker.stop,
        upstream=FakeUpstream(LEAP_PIN),
    )


def test_obs_mirror_mounts_the_tree_and_writes_the_mirror_file(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fetch, docker = FakeFetch(), FakeDocker()
    _drive(_run_args(tmp_path, "opensuse-16.0", obs_mirror_flag=True), fetch, docker)
    tree = (tmp_path / "mirror-base" / "obs-mirror-19.2.3-lp160.2.98").resolve()
    assert fetch.calls == [("19.2.3-lp160.2.98", tree)]
    argv = docker.started[0]
    assert f"{tree}:/srv/obs-mirror:ro" in argv
    assert argv[argv.index(f"{tree}:/srv/obs-mirror:ro") - 1] == "-v"
    # The mirror file is written first, before `renet ceph install` runs.
    assert docker.exec.calls[0] == ["sh", "-c", MIRROR_WRITE]
    first_install = docker.exec.calls.index(["renet", "ceph", "install", "--profile", "admin"])
    assert first_install > docker.exec.calls.index(["cat", obs_mirror.MIRROR_CONFIG])
    out = capsys.readouterr().out
    assert "[PASS] opensuse-16.0: obs mirror present" in out
    assert "[PASS] opensuse-16.0: obs mirror configured" in out
    assert "mirror serves the pin" in out
    assert docker.stopped


def test_obs_mirror_fetch_miss_is_a_fail_naming_the_pin_and_the_fix(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    miss = obs_mirror.MirrorError("oras pull ...: not found")
    fetch, docker = FakeFetch(miss), FakeDocker()
    rc = _drive(_run_args(tmp_path, "opensuse-16.0", obs_mirror_flag=True), fetch, docker)
    assert rc == 1
    assert docker.started == []  # nothing runs against OBS in the mirror's place
    out = capsys.readouterr().out
    assert "[FAIL] opensuse-16.0: obs mirror present" in out
    error = next(line for line in out.splitlines() if line.startswith("::error::"))
    assert "19.2.3-lp160.2.98" in error
    assert "dispatch ci-obs-mirror while OBS still serves it" in error
    assert "not found" in error


def test_obs_mirror_unwritable_config_stops_before_the_checks(tmp_path: pathlib.Path) -> None:
    docker = FakeDocker([(("cat",), m.Result(1, "", "No such file"))])
    rc = _drive(_run_args(tmp_path, "opensuse-16.0", obs_mirror_flag=True), FakeFetch(), docker)
    assert rc == 1
    assert ["renet", "ceph", "install", "--profile", "admin"] not in docker.exec.calls
    assert docker.stopped


def test_without_obs_mirror_nothing_is_fetched_mounted_or_written(tmp_path: pathlib.Path) -> None:
    fetch, docker = FakeFetch(), FakeDocker()
    _drive(_run_args(tmp_path, "opensuse-16.0", obs_mirror_flag=False), fetch, docker)
    assert fetch.calls == []
    argv = docker.started[0]
    assert not any("/srv/obs-mirror" in a for a in argv)
    assert argv.count("-v") == 1
    assert ["sh", "-c", MIRROR_WRITE] not in docker.exec.calls
    assert docker.exec.calls[0] == ["renet", "ceph", "install", "--profile", "admin"]


def test_obs_mirror_is_refused_on_a_dnf_leg(tmp_path: pathlib.Path) -> None:
    fetch, docker = FakeFetch(), FakeDocker()
    assert _drive(_run_args(tmp_path, "fedora-43", obs_mirror_flag=True), fetch, docker) == 2
    assert fetch.calls == []
    assert docker.started == []


def test_run_cli_accepts_obs_mirror() -> None:
    args = ["run", "--distro", "opensuse-16.0", "--renet", "/nonexistent/renet", "--obs-mirror"]
    # The missing renet stops first (rc 2), so the parser accepted the flag and nothing was pulled.
    assert m.main(args) == 2


def _healthy_leap_leg(pin: str) -> list[tuple[tuple[str, ...], m.Result]]:
    """Every exec of a passing Leap leg that installs pin from the mirror."""
    search = ZYPPER_SEARCH.replace("19.2.3-lp160.2.98", pin)
    return [
        (("cat", obs_mirror.MIRROR_CONFIG), m.Result(0, "dir:/srv/obs-mirror\n", "")),
        (("zypper", "-n", "se"), m.Result(0, search, "")),
        (("zypper", "-n", "up", "--dry-run"), m.Result(0, ZYPPER_LOCKED, "")),
        (
            ("rpm", "-q", "--qf"),
            m.Result(0, f"ceph-common (none):{pin}\ncephadm (none):{pin}\n", ""),
        ),
        (("rpm", "-q", "podman"), m.Result(1, "package podman is not installed\n", "")),
        (("sh", "-c", "command -v podman"), m.Result(1, "", "")),
        (("rbd",), m.Result(0, "ceph version 19.2.3 (x) squid (stable)\n", "")),
    ]


@pytest.mark.parametrize("event", OFF_SCHEDULE)
def test_pin_absent_upstream_installs_from_the_mirror_and_warns_off_schedule(
    event: str, tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # OBS has moved past the pin: the leg mounts the mirror, installs every profile from it, reports the
    # move as a warning, and exits 0.
    args = _run_args(tmp_path, "opensuse-16.0", obs_mirror_flag=True)
    args.event = event
    fetch, docker = FakeFetch(), FakeDocker(_healthy_leap_leg(LEAP_PIN))
    moved = FakeUpstream(MOVED)
    rc = m.cmd_run(
        args,
        fetch=fetch,
        start=docker.start,
        exec_factory=docker.factory,
        stop=docker.stop,
        upstream=moved,
    )
    out = capsys.readouterr().out
    assert rc == 0, out
    assert moved.calls == 1
    assert fetch.calls
    assert fetch.calls[0][0] == LEAP_PIN
    for profile in ("admin", "client", "fork-dest"):
        assert ["renet", "ceph", "install", "--profile", profile] in docker.exec.calls
    assert docker.exec.calls[0] == ["sh", "-c", MIRROR_WRITE]
    assert "[PASS] opensuse-16.0: mirror serves the pin" in out
    assert "::warning::opensuse-16.0: upstream: OBS still serves the pin: OBS REBUILT" in out
    assert "::error::" not in out


def test_pin_absent_upstream_installs_from_the_mirror_and_reds_the_nightly(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # The same leg on the nightly: every install still succeeds from the mirror, and the only FAIL is the
    # upstream check, which is the signal that customers on OBS are broken until the pin moves.
    args = _run_args(tmp_path, "opensuse-16.0", obs_mirror_flag=True)
    args.event = "schedule"
    docker = FakeDocker(_healthy_leap_leg(LEAP_PIN))
    rc = m.cmd_run(
        args,
        fetch=FakeFetch(),
        start=docker.start,
        exec_factory=docker.factory,
        stop=docker.stop,
        upstream=FakeUpstream(MOVED),
    )
    out = capsys.readouterr().out
    assert rc == 1
    for profile in ("admin", "client", "fork-dest"):
        assert f"[PASS] opensuse-16.0: ceph install --profile {profile}" in out
    errors = [line for line in out.splitlines() if line.startswith("::error::")]
    assert len(errors) == 1
    assert errors[0].startswith(
        "::error::opensuse-16.0: upstream: OBS still serves the pin: OBS REBUILT"
    )


def test_pin_absent_upstream_without_the_mirror_is_still_red_on_the_nightly(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # Control: without the mirror the leg's installs come from OBS, which no longer serves the pin.
    args = _run_args(tmp_path, "opensuse-16.0", obs_mirror_flag=False)
    args.event = "schedule"
    docker = FakeDocker(_healthy_leap_leg(LEAP_PIN))
    rc = m.cmd_run(
        args,
        fetch=FakeFetch(),
        start=docker.start,
        exec_factory=docker.factory,
        stop=docker.stop,
        upstream=FakeUpstream(MOVED),
    )
    out = capsys.readouterr().out
    assert rc == 1
    assert "::error::opensuse-16.0: upstream: OBS still serves the pin: OBS REBUILT" in out
