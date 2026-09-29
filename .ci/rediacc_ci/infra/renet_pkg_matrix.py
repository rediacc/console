#!/usr/bin/env python3
"""The `Renet pkg matrix` job: renet's Ceph and GPU package flows, run for real in one container per non-apt distro.

PLAN-renet-ceph-gpu-non-apt.md, box P6 (section 2d item 1). Rocky 10 and CentOS Stream 10 kernels carry no btrfs, so they can never run the E2E Ceph suites; this container run is the only CI proof those two get, and it is the cheap first line for Fedora 43, Oracle Linux 10 and openSUSE Leap 16.0.

Subcommands, one per workflow step, so each `run:` stays one line:

  scope   (job `Renet pkg scope`) decide whether this event runs the matrix and the non-apt E2E Ceph Workers
          legs. Every non-PR event (the nightly schedule, the rehearsal dispatch) runs them. A pull request
          runs them when it touches a WATCHED path: one of CONSOLE_PATHS, or one of RENET_PATHS inside the
          private/renet submodule (read by diffing the submodule between the pointer the PR's base carries
          and the one its head carries), or when it carries the `full-ci` label. Writes `hit=true|false`.
  run     (job `Renet pkg matrix (<distro>)`) start the distro's container with the given renet mounted,
          and execute, in order, every check in the module's CHECKS list. All checks run even after one
          fails, so a red leg reports every broken rule at once, and the leg exits 1 when any failed.

WHAT `run` PROVES, per distro:

  * `renet ceph install --profile admin`, `--profile client` and `--profile fork-dest` exit 0;
  * DRIFT (plan section 2a, D2): the pinned ceph-common and cephadm still resolve from the repository renet
    configured (Fedora `fedora`, the SIG and OBS `rediacc-ceph-squid`). OBS keeps only its latest build, so
    this is the check that reds the nightly with the distro and the version before an install breaks;
  * `rpm -q ceph-common cephadm` equals the host.<target> pin in private/renet/.ceph-image-pin, and
    `rbd --version` reports its host-version;
  * the sqlite CLI answers `sqlite3 --version`, and podman is neither installed nor on PATH (cephadm prefers
    podman over docker, plan section 1);
  * THE LOCK: an upgrade dry run (`dnf upgrade --assumeno`, `zypper -n up --dry-run`) lists no Ceph package.
    zypper prints a notice naming every LOCKED package before the transaction, so only its "going to be
    upgraded" and "going to be downgraded" sections are read, never a grep over the whole output (P2's
    finding). On dnf the same dry run is repeated with the lock lifted as a CONTROL: it must list a Ceph
    package, or the lock check could not have failed; an empty control is a warning, since it only means
    the repository has no newer build yet;
  * `renet setup --gpu-resolve-only` for AMD and for Nvidia (box P5): the GPU repository setup for real,
    then a resolve-only install.
"""

from __future__ import annotations

import argparse
import dataclasses
import os
import pathlib
import re
import subprocess
import sys
import uuid
from typing import TYPE_CHECKING

from rediacc_ci import log

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

ROOT = pathlib.Path(__file__).resolve().parents[3]
PIN_FILE = ROOT / "private" / "renet" / ".ceph-image-pin"

# The repository id renet writes for the SIG and OBS sources (pkg/infra/cephpkg RepoName).
CEPH_REPO_ID = "rediacc-ceph-squid"


@dataclasses.dataclass(frozen=True)
class Distro:
    """One matrix leg: the container image, the .ceph-image-pin target and the package manager."""

    image: str
    target: str
    manager: str  # "dnf" or "zypper"
    repo: str  # the repository id the pinned build must resolve from


DISTROS: dict[str, Distro] = {
    "fedora-43": Distro("fedora:43", "fedora-43", "dnf", "fedora"),
    "oracle-10": Distro("oraclelinux:10", "el10", "dnf", CEPH_REPO_ID),
    "rocky-10": Distro("rockylinux/rockylinux:10", "el10", "dnf", CEPH_REPO_ID),
    "centos-stream-10": Distro("quay.io/centos/centos:stream10", "el10", "dnf", CEPH_REPO_ID),
    "opensuse-16.0": Distro("opensuse/leap:16.0", "opensuse-16.0", "zypper", CEPH_REPO_ID),
}

# Watched paths for a pull request. A directory entry ends in "/" and matches every path under it.
CONSOLE_PATHS = (
    ".ci/rediacc_ci/infra/renet_pkg_matrix.py",
    ".ci/rediacc_ci/tests/test_infra_renet_pkg_matrix.py",
    "scripts/gates/check-ceph-image-pin.ts",
)
RENET_PATHS = (
    ".ceph-image-pin",
    "pkg/infra/cephpkg/",
    "pkg/infra/pkgset/",
    "pkg/infra/aptretry/",
    "pkg/infra/ceph/",
    "cmd/renet/ceph_install.go",
    "cmd/renet/ceph_host_runner.go",
    "cmd/renet/kube_fork_dest_prep.go",
    "cmd/renet/pkg_install_retry.go",
    "cmd/renet/gpu_drivers.go",
    "cmd/renet/gpu_keys/",
    "cmd/renet/setup_command.go",
)
RENET_SUBMODULE = "private/renet"
FULL_CI_LABEL = "full-ci"

# Every package name that must not move past the pin (pkg/infra/cephpkg cephNames, the same alternation).
CEPH_NAME = re.compile(
    r"^(ceph|cephadm|librados|librbd|librgw|libcephfs|libcephsqlite|libradosstriper|python3-(ceph|rados|rbd|rgw|cephfs))"
)
# One dnf transaction row: ` name arch version repo size`, or dnf5's `   replacing name arch ...`.
DNF_ROW = re.compile(
    r"^\s+(?:replacing\s+)?(?P<name>\S+)\s+(?:x86_64|aarch64|noarch|i686)\s+\S+\s+\S+"
)
# Markers that the dnf dry run resolved at all: without one, "no Ceph row" proves nothing.
DNF_RESOLVED = (
    "Nothing to do",
    "Transaction Summary",
    "Operation aborted",
    "Dependencies resolved",
)
ZYPPER_HEADING = re.compile(
    r"^The following (?:\d+ )?(?P<kind>.*?) (?:is|are) going to be (?P<verb>\w+)"
)
ZYPPER_RESOLVED = ("Nothing to do", "Reading installed packages")
# A line that states why a renet command failed: cobra's "Error: ...", or a logrus error or warning.
ERROR_LINE = re.compile(r"^Error: |level=(?:error|fatal|warning)")

# `renet setup --gpu-resolve-only` (box P5), one run per vendor.
GPU_RUNS = {
    "amd": [
        "renet",
        "setup",
        "--gpu-resolve-only",
        "--install-amd-driver=true",
        "--install-nvidia-driver=false",
    ],
    "nvidia": [
        "renet",
        "setup",
        "--gpu-resolve-only",
        "--install-amd-driver=false",
        "--install-nvidia-driver=true",
    ],
}


@dataclasses.dataclass(frozen=True)
class Result:
    rc: int
    stdout: str
    stderr: str


@dataclasses.dataclass(frozen=True)
class Verdict:
    name: str
    ok: bool
    detail: str
    warning: str = ""


# ---------------------------------------------------------------------------
# The pin file
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class Pins:
    host_version: str
    hosts: dict[str, str]


def read_pins(text: str) -> Pins:
    """host-version and every host.<target>=<version> line of .ceph-image-pin."""
    host_version = ""
    hosts: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        if key == "host-version":
            host_version = value.strip()
        elif key.startswith("host."):
            hosts[key.removeprefix("host.")] = value.strip()
    if not host_version:
        raise ValueError("no host-version line in the pin file")
    return Pins(host_version, hosts)


def split_evr(evr: str) -> tuple[str, str]:
    """`[epoch:]version-release` as (epoch, version-release); a missing epoch is ''."""
    epoch, sep, rest = evr.partition(":")
    return (epoch, rest) if sep else ("", evr)


def evr_matches(pin: str, installed: str) -> bool:
    """Whether an installed `epoch:version-release` is the pin.

    The pin states an epoch only where one is load-bearing (el10's `2:`); Fedora's pin omits the epoch its
    package carries (`2:19.2.3-8.fc43`, measured), and dnf resolves the NVR either way. So version-release must
    match exactly, and the epoch only when the pin names one.
    """
    pin_epoch, pin_vr = split_evr(pin)
    got_epoch, got_vr = split_evr(installed)
    if pin_vr != got_vr:
        return False
    return not pin_epoch or pin_epoch == got_epoch


# ---------------------------------------------------------------------------
# Parsers (pure, so the tests drive them with captured output)
# ---------------------------------------------------------------------------


def dnf_ceph_rows(stdout: str) -> list[str]:
    """Ceph package names on the transaction rows of a dnf dry run."""
    names: list[str] = []
    for line in stdout.splitlines():
        m = DNF_ROW.match(line)
        if m and CEPH_NAME.match(m["name"]) and m["name"] not in names:
            names.append(m["name"])
    return names


def zypper_changed(stdout: str) -> list[str]:
    """Package names in the "going to be upgraded" and "going to be downgraded" sections of a zypper dry run.

    Only package sections count: the notice listing LOCKED items, the NEW and REMOVED sections and the
    pattern and product sections are skipped. A section's names run until the first blank line.
    """
    names: list[str] = []
    collecting = False
    for line in stdout.splitlines():
        heading = ZYPPER_HEADING.match(line)
        if heading:
            collecting = "package" in heading["kind"] and heading["verb"] in (
                "upgraded",
                "downgraded",
            )
            continue
        if not line.strip() or not line.startswith(" "):
            collecting = False
            continue
        if collecting:
            names.extend(n for n in line.split() if n not in names)
    return names


def resolved(manager: str, stdout: str) -> bool:
    markers = DNF_RESOLVED if manager == "dnf" else ZYPPER_RESOLVED
    return any(m in stdout for m in markers)


def rpm_versions(stdout: str) -> dict[str, str]:
    """`name epoch:version-release` lines (rpm -q --qf) as a map; an absent epoch prints as `(none)`."""
    out: dict[str, str] = {}
    for line in stdout.splitlines():
        parts = line.split()
        if len(parts) == 2:
            evr = parts[1].removeprefix("(none):")
            out[parts[0]] = evr
    return out


def zypper_editions(stdout: str) -> dict[str, list[str]]:
    """Name -> versions from `zypper se -s` table rows (`S | Name | Type | Version | Arch | Repository`)."""
    out: dict[str, list[str]] = {}
    for line in stdout.splitlines():
        cells = [c.strip() for c in line.split("|")]
        if len(cells) >= 6 and cells[2] == "package":
            out.setdefault(cells[1], []).append(cells[3])
    return out


def dnf_available(stdout: str) -> dict[str, list[str]]:
    """Name -> `epoch:version-release` list from `dnf repoquery --qf '%{name} %{epoch}:%{version}-%{release}'`."""
    out: dict[str, list[str]] = {}
    for line in stdout.splitlines():
        parts = line.split()
        if len(parts) == 2:
            out.setdefault(parts[0], []).append(parts[1])
    return out


# ---------------------------------------------------------------------------
# The checks
# ---------------------------------------------------------------------------


def _tail(res: Result, lines: int = 15) -> str:
    text = (res.stdout + ("\n" + res.stderr if res.stderr else "")).strip().splitlines()
    return "\n".join(text[-lines:])


def check_command(
    name: str, argv: Sequence[str], run: Callable[[Sequence[str]], Result]
) -> Verdict:
    res = run(argv)
    if res.rc == 0:
        return Verdict(name, True, "rc=0")
    # cobra prints the usage text after the error, so a plain tail shows only flags; lead with renet's own error lines.
    errors = [
        line for line in (res.stdout + "\n" + res.stderr).splitlines() if ERROR_LINE.search(line)
    ]
    why = f" ({errors[-1].strip()})" if errors else ""
    detail = "\n".join([*errors[-5:], _tail(res)])
    return Verdict(name, False, f"`{' '.join(argv)}` exited {res.rc}{why}\n{detail}")


def check_drift(
    distro_name: str, d: Distro, pin: str, run: Callable[[Sequence[str]], Result]
) -> Verdict:
    """The pinned build still resolves from the repository renet configured (the nightly OBS/SIG drift check)."""
    name = "drift: pinned build resolves"
    if d.manager == "dnf":
        specs = [f"ceph-common-{pin}", f"cephadm-{pin}"]
        res = run(
            [
                "dnf",
                "-q",
                "repoquery",
                "--available",
                f"--repo={d.repo}",
                "--qf",
                "%{name} %{epoch}:%{version}-%{release}\n",
                *specs,
            ]
        )
        found = dnf_available(res.stdout)
    else:
        res = run(
            ["zypper", "-n", "se", "-s", "--match-exact", "-r", d.repo, "ceph-common", "cephadm"]
        )
        found = zypper_editions(res.stdout)
    missing = [
        pkg
        for pkg in ("ceph-common", "cephadm")
        if not any(evr_matches(pin, v) for v in found.get(pkg, []))
    ]
    if not missing:
        return Verdict(name, True, f"{pin} from {d.repo}")
    return Verdict(
        name,
        False,
        f"DRIFT on {distro_name}: {', '.join(missing)} {pin} no longer resolves from repository "
        f"{d.repo} (found {found or 'nothing'}; rc={res.rc})\n{_tail(res)}",
    )


def check_versions(
    d: Distro, pin: str, host_version: str, run: Callable[[Sequence[str]], Result]
) -> list[Verdict]:
    res = run(
        ["rpm", "-q", "--qf", "%{NAME} %{EPOCH}:%{VERSION}-%{RELEASE}\n", "ceph-common", "cephadm"]
    )
    got = rpm_versions(res.stdout)
    bad = {
        pkg: got.get(pkg, "not installed")
        for pkg in ("ceph-common", "cephadm")
        if not evr_matches(pin, got.get(pkg, ""))
    }
    out = [
        Verdict(
            "rpm -q equals the pin",
            not bad,
            f"pin {pin} ({d.target})" if not bad else f"pin {pin} ({d.target}), installed {bad}",
        )
    ]
    rbd = run(["rbd", "--version"])
    want = f"ceph version {host_version} "
    out.append(
        Verdict(
            "rbd --version", rbd.rc == 0 and want in rbd.stdout, rbd.stdout.strip() or _tail(rbd)
        )
    )
    return out


def check_no_podman(run: Callable[[Sequence[str]], Result]) -> Verdict:
    pkg = run(["rpm", "-q", "podman"])
    path = run(["sh", "-c", "command -v podman"])
    if pkg.rc != 0 and path.rc != 0:
        return Verdict("no podman", True, "not installed, not on PATH")
    return Verdict(
        "no podman",
        False,
        f"rpm -q podman: {pkg.stdout.strip()}; on PATH: {path.stdout.strip() or '-'}",
    )


def upgrade_dry_run(d: Distro, unlocked: bool) -> list[str]:
    if d.manager == "zypper":
        return ["zypper", "-n", "up", "--dry-run"]
    argv = ["dnf", "upgrade", "--assumeno"]
    if unlocked:
        # Lift both lock kinds: dnf4 versionlock (EL10) and the dnf5 `updates` exclude (Fedora).
        argv += (
            ["--setopt=disable_excludes=*"]
            if d.target == "fedora-43"
            else ["--disableplugin=versionlock"]
        )
    return argv


def check_lock(d: Distro, run: Callable[[Sequence[str]], Result]) -> Verdict:
    name = "lock: upgrade moves no Ceph package"
    res = run(upgrade_dry_run(d, unlocked=False))
    if not resolved(d.manager, res.stdout):
        return Verdict(
            name, False, f"the upgrade dry run did not resolve (rc={res.rc})\n{_tail(res)}"
        )
    moved = (
        dnf_ceph_rows(res.stdout)
        if d.manager == "dnf"
        else [n for n in zypper_changed(res.stdout) if CEPH_NAME.match(n)]
    )
    if moved:
        return Verdict(name, False, f"the dry run would move {', '.join(moved)}\n{_tail(res, 40)}")
    if d.manager != "dnf":
        return Verdict(
            name,
            True,
            "no Ceph package in the upgrade sections",
            warning="no control on zypper: the OBS repository offers only the pinned build",
        )
    control = run(upgrade_dry_run(d, unlocked=True))
    offered = dnf_ceph_rows(control.stdout)
    if offered:
        return Verdict(name, True, f"locked; unlocked, the dry run offers {', '.join(offered[:3])}")
    return Verdict(
        name,
        True,
        "no Ceph package in the transaction",
        warning="CONTROL VACUOUS: with the lock lifted no newer Ceph build is offered either",
    )


def run_checks(
    distro_name: str, d: Distro, pins: Pins, run: Callable[[Sequence[str]], Result]
) -> list[Verdict]:
    pin = pins.hosts.get(d.target)
    if not pin:
        return [Verdict("pin", False, f"no host.{d.target} line in {PIN_FILE}")]
    out = [
        check_command(
            "ceph install --profile admin", ["renet", "ceph", "install", "--profile", "admin"], run
        )
    ]
    out.append(check_drift(distro_name, d, pin, run))
    out.extend(
        check_command(
            f"ceph install --profile {profile}",
            ["renet", "ceph", "install", "--profile", profile],
            run,
        )
        for profile in ("client", "fork-dest")
    )
    out.extend(check_versions(d, pin, pins.host_version, run))
    out.append(check_command("sqlite3 --version", ["sqlite3", "--version"], run))
    out.append(check_no_podman(run))
    out.append(check_lock(d, run))
    out.extend(
        check_command(f"gpu resolve-only ({vendor})", argv, run)
        for vendor, argv in GPU_RUNS.items()
    )
    return out


def report(distro_name: str, verdicts: Sequence[Verdict]) -> int:
    failed = [v for v in verdicts if not v.ok]
    for v in verdicts:
        mark = "PASS" if v.ok else "FAIL"
        print(
            f"[{mark}] {distro_name}: {v.name}: {v.detail.splitlines()[0] if v.detail else ''}",
            flush=True,
        )
        if v.warning:
            print(f"::warning::{distro_name}: {v.name}: {v.warning}", flush=True)
    for v in failed:
        first, _, rest = v.detail.partition("\n")
        print(f"::error::{distro_name}: {v.name}: {first}", flush=True)
        if rest:
            print(rest, flush=True)
    print(f"{distro_name}: {len(verdicts) - len(failed)}/{len(verdicts)} checks passed", flush=True)
    return 1 if failed else 0


# ---------------------------------------------------------------------------
# The container
# ---------------------------------------------------------------------------


def docker_exec(container: str) -> Callable[[Sequence[str]], Result]:
    def run(argv: Sequence[str]) -> Result:
        log.step(" ".join(argv))
        p = subprocess.run(
            ["docker", "exec", container, *argv], capture_output=True, text=True, check=False
        )
        return Result(p.returncode, p.stdout, p.stderr)

    return run


def cmd_run(args: argparse.Namespace) -> int:
    d = DISTROS[args.distro]
    renet = pathlib.Path(args.renet).resolve()
    if not renet.is_file():
        log.error(f"renet binary not found: {renet}")
        return 2
    pins = read_pins(pathlib.Path(args.pin_file).read_text(encoding="utf-8"))
    container = f"renet-pkg-matrix-{args.distro}-{uuid.uuid4().hex[:8]}"
    start = subprocess.run(
        [
            "docker",
            "run",
            "-d",
            "--name",
            container,
            "-v",
            f"{renet}:/usr/local/bin/renet:ro",
            d.image,
            "sleep",
            "infinity",
        ],
        check=False,
    )
    if start.returncode != 0:
        log.error(f"could not start {d.image} (rc={start.returncode})")
        return 1
    try:
        return report(args.distro, run_checks(args.distro, d, pins, docker_exec(container)))
    finally:
        subprocess.run(["docker", "rm", "-f", container], capture_output=True, check=False)


# ---------------------------------------------------------------------------
# scope
# ---------------------------------------------------------------------------


def watched(path: str, patterns: Sequence[str]) -> bool:
    return any(path.startswith(p) if p.endswith("/") else path == p for p in patterns)


def scope_decision(
    event: str, labels: str, console_changed: Sequence[str], renet_changed: Sequence[str] | None
) -> tuple[bool, str]:
    """(hit, reason). `renet_changed` is None when the submodule pointer did not move."""
    if event != "pull_request":
        return True, f"event {event or '(none)'} runs the matrix"
    if FULL_CI_LABEL in labels.split(","):
        return True, f"label {FULL_CI_LABEL}"
    hits = [p for p in console_changed if watched(p, CONSOLE_PATHS)]
    hits += [f"{RENET_SUBMODULE}/{p}" for p in renet_changed or [] if watched(p, RENET_PATHS)]
    if hits:
        return True, "watched paths changed: " + ", ".join(hits[:10])
    return False, "no watched path changed"


def _git(args: Sequence[str], cwd: pathlib.Path) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=True
    ).stdout


def cmd_scope(args: argparse.Namespace) -> int:
    renet_changed: list[str] | None = None
    console_changed: list[str] = []
    if args.event == "pull_request":
        # On pull_request the checkout is the merge commit, whose first parent is the base branch tip.
        console_changed = _git(["diff", "--name-only", "HEAD^1", "HEAD"], ROOT).split()
        if RENET_SUBMODULE in console_changed:
            old = _git(["rev-parse", f"HEAD^1:{RENET_SUBMODULE}"], ROOT).strip()
            new = _git(["rev-parse", f"HEAD:{RENET_SUBMODULE}"], ROOT).strip()
            sub = ROOT / RENET_SUBMODULE
            _git(["fetch", "--quiet", "--depth=1", "origin", old], sub)
            renet_changed = _git(["diff", "--name-only", old, new], sub).split()
    hit, reason = scope_decision(args.event, args.labels, console_changed, renet_changed)
    print(f"renet pkg scope: hit={str(hit).lower()} ({reason})", flush=True)
    out = os.environ.get("GITHUB_OUTPUT", "")
    if out:
        with open(out, "a", encoding="utf-8") as fh:
            fh.write(f"hit={str(hit).lower()}\n")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="renet_pkg_matrix", description=__doc__.splitlines()[0] if __doc__ else ""
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_run = sub.add_parser("run", help="run every check in one distro's container")
    p_run.add_argument("--distro", required=True, choices=sorted(DISTROS))
    p_run.add_argument("--renet", required=True, help="path of the renet binary to mount")
    p_run.add_argument("--pin-file", default=str(PIN_FILE))
    p_scope = sub.add_parser("scope", help="decide whether this event runs the matrix")
    p_scope.add_argument("--event", required=True)
    p_scope.add_argument("--labels", default="", help="comma-separated PR labels")
    args = parser.parse_args(argv)
    return cmd_run(args) if args.cmd == "run" else cmd_scope(args)


if __name__ == "__main__":
    sys.exit(main())
