#!/usr/bin/env python3
"""Both sides of the MACHINE-MUTATING half of the `core.local_common` port differential.

    PYTHONPATH=.ci python3 -m rediacc_ci.core.local_common_actions_shadow_driver --side old --twin .ci/lib/local-common.sh --port .ci/rediacc_ci/core/local_common.py <scenario>
    PYTHONPATH=.ci python3 -m rediacc_ci.core.local_common_actions_shadow_driver --side new --twin .ci/lib/local-common.sh --port .ci/rediacc_ci/core/local_common.py <scenario>

A SECOND DRIVER FOR THE SAME TWIN, and a second ledger pair (`w7p5b-local-common-actions`), because the technique differs: `core/local_common_shadow_driver.py` compares pure answers inside one bash process per side, and this one runs every case as ITS OWN PROCESS per side with the external programs stubbed (`core/stubfarm.py`) and compares rc, both streams, the ordered transcript of every stubbed call and every file the case left behind. RUN AS A MODULE, never by path, for the reason that driver records.

-----------------------------------------------------------------------------
THE SANDBOX LIVES AT THE SAME PATH ON BOTH SIDES, UNDER A LOCK
-----------------------------------------------------------------------------
`ensure_deps` hashes `_sha256sum "$LOCAL_ROOT_DIR/package.json"`, whose output line carries the ABSOLUTE path, so the stamp it writes depends on where the checkout is. Two sides in two temporary directories would write two different stamps and the comparison would be about the harness. So every case builds its sandbox at `<tmp>/rediacc-lc-actions/root` and its stub farm at `<tmp>/rediacc-lc-actions/farm`, rebuilt from nothing per case, and the whole run holds an `flock` on `<tmp>/rediacc-lc-actions.lock` so two drivers cannot share it.

The sandbox is a `CONSOLE_ROOT_DIR` whose `.ci/lib`, `.ci/config`, `.ci/scripts/lib` and `.devcontainer` are SYMLINKS back to this checkout (the twin resolves `LOCAL_ROOT_DIR` logically, so it lands on the sandbox), and whose `package.json`, `node_modules`, `packages/`, `private/renet` and `.ci/cache` are real per-case fixtures. `.ci/scripts/setup/build-packages.sh` and `private/renet/build.sh` are STUBS at those paths, because the twin runs them by path.

STUBBED AND LOGGED: `npm`, `node`, `go`, `sudo`, `curl`, `tar`, `gcc`, `docker`, `sg`, `xdg-open`, `open`, `cmd`, and the two path stubs. STUBBED, NOT LOGGED: `uname`, `mktemp`, `getent` -- questions the twin asks of the machine, whose answers the case scripts. HIDDEN per case: a tool the scenario needs ABSENT is removed from a symlink farm of the host's program directories (`Farm.host_path`), because a stub can add a program but not take one away.

-----------------------------------------------------------------------------
THE SCENARIOS
-----------------------------------------------------------------------------
  deps      `ensure_deps` fresh, twice (the second is the stamp hit), with a failing `npm install`, a failing buildcheck, an empty gypi left by a failed run, a missing lockfile, and a runtime-tag change forcing a reinstall; `ensure_cpu_features_gypi` alone.
  packages  `ensure_packages_built` fresh, twice, with a failing build, and with `packages/provisioning` missing.
  cli       `ensure_cli_built` with no packages stamp (twin behaviour 7), fresh, twice, and with a build that leaves no bundle.
  misc      `prompt_continue` over a corpus of answers, `open_browser` on four platforms and with no `xdg-open`, `run_npm_script`, `check_node_version`, `check_go_installed`.
  go        (ENVIRONMENT-BOUND: whether `/etc/profile.d/golang.sh` exists is read from the REAL filesystem on both sides, so only the branch this host is on is compared; a planted `if True` there is silent on a host without the file, and that is recorded rather than hidden.)
            `ensure_go_installed` with no go.mod, a current Go, an old Go that gets replaced, a toolchain-less go.mod, a non-Linux host, an unsupported arch, a failed download, an invalid tarball, and a failed unpack.
  host      `ensure_host_tools` complete, missing tools installed, a failing apt, a non-Linux host; `ensure_bashcov_sup` built, up to date, no gcc, and a failing build.
  docker    `reexec_with_docker_group` at every early return and at the exec, `ensure_docker_installed` usable, sudo-only, non-Linux, and the full renet-installer path, `_ensure_docker_group` in all four states.
  lane      `gate_lane_decide` down every rule (inside the box, `REDIACC_LANE` valid and not, the sticky state value present and empty, a running and a stopped container, docker only via sudo), `gate_lane_should_route` at all three answers including a broken mount and the dubious-ownership identity, and `gate_lane_run` passing the routed status through and refusing when nothing runs.
  renet     `_renet_source_hash` over a tree with every prune and name rule, an empty tree and a missing one, `_renet_artifact_fp`, and `ensure_renet_built` fresh, twice, license and key variations, a failing build, a build with no binary, and a non-Linux cross-compile.
"""

from __future__ import annotations

import argparse
import contextlib
import dataclasses
import fcntl
import hashlib
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
from typing import TYPE_CHECKING

from rediacc_ci.core.stubfarm import Farm

if TYPE_CHECKING:  # annotation-only import
    from collections.abc import Mapping

EXIT_CANNOT_RUN = 77
BASE_NAME = "rediacc-lc-actions"
LOGGED = (
    "npm",
    "node",
    "go",
    "sudo",
    "curl",
    "tar",
    "gcc",
    "docker",
    "sg",
    "xdg-open",
    "open",
    "cmd",
)
UNLOGGED = ("uname", "mktemp", "getent")
FIXED_MTIME = 1700000000

FN = {
    "cpu-features-gypi": "ensure_cpu_features_gypi",
    "ensure-deps": "ensure_deps",
    "ensure-packages-built": "ensure_packages_built",
    "ensure-cli-built": "ensure_cli_built",
    "prompt-continue": "prompt_continue",
    "open-browser": "open_browser",
    "run-npm-script": "run_npm_script",
    "check-node-version": "check_node_version",
    "check-go-installed": "check_go_installed",
    "ensure-go-installed": "ensure_go_installed",
    "ensure-bashcov-sup": "ensure_bashcov_sup",
    "ensure-host-tools": "ensure_host_tools",
    "reexec-docker-group": "reexec_with_docker_group",
    "ensure-docker-installed": "ensure_docker_installed",
    "ensure-docker-group": "_ensure_docker_group",
    "renet-source-hash": "_renet_source_hash",
    "renet-artifact-fp": "_renet_artifact_fp",
    "ensure-renet-built": "ensure_renet_built",
    "lane-decide": "gate_lane_decide",
    "lane-should-route": "gate_lane_should_route",
    "lane-run": "gate_lane_run",
}


@dataclasses.dataclass
class Case:
    name: str
    verb: str
    args: list[str] = dataclasses.field(default_factory=list)
    rows: list[dict] = dataclasses.field(default_factory=list)
    env: Mapping[str, str | None] = dataclasses.field(default_factory=dict)  # None unsets the name
    setup: tuple[str, ...] = ()
    hidden: tuple[str, ...] = ()
    unstub: tuple[str, ...] = ()
    stdin: str | None = None
    repeat: int = 1
    between: tuple[str, ...] = ()


def row(name: str, glob: str = "*", **kw) -> dict:
    return {"name": name, "glob": glob, **kw}


# ------------------------------------------------------------------ fixtures, by name, built identically for both sides


def _write(path: pathlib.Path, text: str, mode: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    if mode is not None:
        path.chmod(mode)
    os.utime(path, (FIXED_MTIME, FIXED_MTIME))


def fx_manifests(root: pathlib.Path) -> None:
    _write(root / "package.json", '{"name":"sandbox","scripts":{"build":"x"}}\n')
    _write(root / "package-lock.json", '{"lockfileVersion":3}\n')
    _write(root / ".npmrc", "ignore-scripts=true\n")


def fx_no_lock(root: pathlib.Path) -> None:
    (root / "package-lock.json").unlink()


def fx_modules(root: pathlib.Path) -> None:
    _write(root / "node_modules" / ".bin" / "tsx", "#!/bin/sh\n", 0o755)
    (root / "node_modules" / "@rediacc").mkdir(parents=True, exist_ok=True)
    (root / "node_modules" / "@rediacc" / "cli").symlink_to("../../packages/cli")
    _write(root / "node_modules" / "cpu-features" / "buildcheck.js", "// buildcheck\n")


def fx_empty_gypi(root: pathlib.Path) -> None:
    _write(root / "node_modules" / "cpu-features" / "buildcheck.gypi", "")


def fx_packages(root: pathlib.Path) -> None:
    for pkg in ("shared", "provisioning", "cli"):
        _write(root / "packages" / pkg / "src" / "index.ts", "export const %s = 1;\n" % pkg)
        _write(root / "packages" / pkg / "package.json", '{"name":"@rediacc/%s"}\n' % pkg)


def fx_no_provisioning(root: pathlib.Path) -> None:
    shutil.rmtree(root / "packages" / "provisioning")


def fx_packages_stamp(root: pathlib.Path) -> None:
    _write(root / ".ci" / "cache" / "build-packages.stamp", "feedface\n")


def fx_gomod(root: pathlib.Path) -> None:
    _write(root / "private" / "renet" / "go.mod", "module x\n\ngo 1.25.0\n\ntoolchain go1.25.13\n")


def fx_gomod_plain(root: pathlib.Path) -> None:
    _write(root / "private" / "renet" / "go.mod", "module x\n\ngo 1.24.2\n")


def fx_renet_tree(root: pathlib.Path) -> None:
    base = root / "private" / "renet"
    for rel, body in (
        ("cmd/renet/main.go", "package main\n"),
        ("pkg/a/a.go", "package a\n"),
        ("pkg/a/a.c", "int a;\n"),
        ("pkg/a/a.h", "int a;\n"),
        ("go.sum", "sum\n"),
        ("docker-compose.yml", "services: {}\n"),
        ("README.md", "not hashed\n"),
        ("bin/ignored.go", "package ignored\n"),
        ("build/ignored.go", "package ignored\n"),
        ("pkg/embed/assets/ignored.go", "package ignored\n"),
        ("pkg/embed/keep.go", "package embed\n"),
        ("name with space.go", "package s\n"),
    ):
        _write(base / rel, body)
    fx_gomod(root)


def fx_renet_env(root: pathlib.Path) -> None:
    """The public-key cache `ensure_renet_built` reads, plus the retired `.env` it must NOT read any more."""
    _write(
        root / "private" / "account" / ".cache" / "public-keys.env",
        "X=1\nACCOUNT_ED25519_PUBLIC_KEY=pubkey-from-cache\r\n",
    )
    _write(root / "private" / "account" / ".env", "ACCOUNT_ED25519_PUBLIC_KEY=stale-dotenv-key\n")


def fx_cli_dir(root: pathlib.Path) -> None:
    """Replace the `@rediacc/cli` SYMLINK with a real directory: `[[ -L ]]` must now fail."""
    link = root / "node_modules" / "@rediacc" / "cli"
    link.unlink()
    link.mkdir()


def fx_bashcov_old_bin(root: pathlib.Path) -> None:
    binary = root / "home" / ".local" / "share" / "rediacc" / "bin" / "bashcov-sup"
    _write(binary, "#!/bin/sh\nexit 0\n", 0o755)
    os.utime(binary, (FIXED_MTIME + 10**9, FIXED_MTIME + 10**9))


def fx_sticky_devbox(root: pathlib.Path) -> None:
    _write(root / ".devbox-state", "slot=4\ngate_lane=devbox\n")


def fx_sticky_empty(root: pathlib.Path) -> None:
    _write(root / ".devbox-state", "slot=4\ngate_lane=\n")


FIXTURES = {
    name[3:]: fn for name, fn in dict(globals()).items() if name.startswith("fx_") and callable(fn)
}

# ------------------------------------------------------------------ stub behaviours

NPM_INSTALL_SH = (
    "mkdir -p node_modules/.bin node_modules/@rediacc node_modules/cpu-features; "
    "printf '#!/bin/sh\\n' > node_modules/.bin/tsx; chmod +x node_modules/.bin/tsx; "
    "ln -sfn ../../packages/cli node_modules/@rediacc/cli; "
    "printf '// buildcheck\\n' > node_modules/cpu-features/buildcheck.js"
)
BUILD_PACKAGES_SH = 'mkdir -p "$CONSOLE_ROOT_DIR/packages/shared/dist" "$CONSOLE_ROOT_DIR/packages/provisioning/dist"'
BUNDLE_SH = "mkdir -p packages/cli/dist; printf 'bundle\\n' > packages/cli/dist/cli-bundle.cjs"
RENET_BUILD_SH = (
    "mkdir -p bin; printf 'renet\\n' > bin/renet; chmod +x bin/renet; touch -d @%d bin/renet"
    % FIXED_MTIME
)
MKTEMP_SH = 'd="$STUB_ROOT/mktmp"; mkdir -p "$d"; printf "%s\\n" "$d"'
GCC_SH = 'out=""; while [ $# -gt 0 ]; do if [ "$1" = -o ]; then out="$2"; fi; shift; done; printf "#!/bin/sh\\nexit 0\\n" > "$out"; chmod +x "$out"'

GROUP_MEMBER = row("getent", "group docker", out="docker:x:999:alice,sandbox-user\n")
GROUP_OTHER = row("getent", "group docker", out="docker:x:999:alice\n")
GROUP_NONE = row("getent", "group docker", rc=2)
DOCKER_DOWN = row("docker", "version", rc=1)
GO_NEW = row("go", "version", out="go version go1.26.4 linux/amd64\n")
RUNNING = [
    row("docker", "ps -aq *", out="cid1\n"),
    row("docker", "inspect -f {{.State.Running}} *", out="true\n"),
]
GO_OLD = row("go", "version", out="go version go1.19.8 linux/amd64\n")

SCENARIOS: dict[str, list[Case]] = {
    "deps": [
        Case(
            "deps-fresh",
            "ensure-deps",
            rows=[
                row("npm", "install", sh=NPM_INSTALL_SH),
                row("node", "buildcheck.js", out="{ 'gypi': 1 }\n"),
            ],
            setup=("manifests", "packages"),
            env={"DEBUG": "true"},
            repeat=2,
        ),
        Case(
            "deps-install-fails",
            "ensure-deps",
            rows=[row("npm", "install", rc=5, err="npm ERR! boom\n")],
            setup=("manifests",),
        ),
        Case(
            "deps-buildcheck-fails",
            "ensure-deps",
            rows=[
                row("npm", "install", sh=NPM_INSTALL_SH),
                row(
                    "node",
                    "buildcheck.js",
                    rc=1,
                    out="partial",
                    err="Unable to detect compiler type\n",
                ),
            ],
            setup=("manifests", "packages"),
        ),
        Case(
            "deps-empty-gypi",
            "ensure-deps",
            rows=[row("node", "buildcheck.js", out="{ 'gypi': 2 }\n")],
            setup=("manifests", "packages", "modules", "empty_gypi"),
            env={"DEBUG": "true"},
        ),
        Case(
            "deps-cli-not-a-symlink",
            "ensure-deps",
            rows=[row("npm", "install", sh=NPM_INSTALL_SH)],
            setup=("manifests", "packages"),
            env={"DEBUG": "true"},
            repeat=2,
            between=("cli_dir",),
        ),
        Case(
            "deps-no-lockfile",
            "ensure-deps",
            rows=[row("npm", "install", sh=NPM_INSTALL_SH)],
            setup=("manifests", "packages", "no_lock"),
        ),
        Case(
            "deps-runtime-tag",
            "ensure-deps",
            rows=[row("npm", "install", sh=NPM_INSTALL_SH)],
            setup=("manifests", "packages", "modules"),
            env={"REDIACC_NPM_RUNTIME": "devbox"},
        ),
        Case(
            "gypi-alone",
            "cpu-features-gypi",
            args=["node_modules"],
            rows=[row("node", "buildcheck.js", out="{}\n")],
            setup=("manifests", "packages", "modules"),
        ),
    ],
    "packages": [
        Case(
            "packages-fresh",
            "ensure-packages-built",
            setup=("manifests", "packages"),
            rows=[row("build-packages.sh", sh=BUILD_PACKAGES_SH)],
            env={"DEBUG": "true"},
            repeat=2,
        ),
        Case(
            "packages-build-fails",
            "ensure-packages-built",
            setup=("manifests", "packages"),
            rows=[row("build-packages.sh", rc=3, err="tsc failed\n")],
        ),
        Case(
            "packages-missing-provisioning",
            "ensure-packages-built",
            setup=("manifests", "packages", "no_provisioning"),
            rows=[row("build-packages.sh", sh=BUILD_PACKAGES_SH)],
        ),
    ],
    "cli": [
        Case("cli-no-packages-stamp", "ensure-cli-built", setup=("manifests", "packages")),
        Case(
            "cli-fresh",
            "ensure-cli-built",
            setup=("manifests", "packages", "packages_stamp"),
            rows=[row("npm", "run build:bundle *", sh=BUNDLE_SH)],
            env={"DEBUG": "true"},
            repeat=2,
        ),
        Case(
            "cli-no-bundle", "ensure-cli-built", setup=("manifests", "packages", "packages_stamp")
        ),
        Case(
            "cli-build-fails",
            "ensure-cli-built",
            setup=("manifests", "packages", "packages_stamp"),
            rows=[row("npm", "run build -w *", rc=2)],
        ),
    ],
    "misc": [
        *[
            Case("prompt-%d" % i, "prompt-continue", args=["Proceed?"], stdin=answer)
            for i, answer in enumerate(
                (
                    "y\n",
                    "Y\n",
                    "yes\n",
                    "n\n",
                    "\n",
                    "",
                    " y \n",
                    "\\y\n",
                    "y",
                    "\\\ny\n",
                    "yy\n",
                    "N\n",
                )
            )
        ],
        Case("prompt-default-message", "prompt-continue", stdin="y\n"),
        Case(
            "browser-linux",
            "open-browser",
            args=["http://localhost:1/x y"],
            rows=[row("xdg-open", rc=3, err="no display\n")],
        ),
        Case(
            "browser-linux-no-xdg",
            "open-browser",
            args=["http://a"],
            unstub=("xdg-open",),
            hidden=("xdg-open",),
        ),
        Case(
            "browser-macos",
            "open-browser",
            args=["http://a"],
            rows=[row("uname", "-s", out="Darwin\n")],
        ),
        Case(
            "browser-windows",
            "open-browser",
            args=["http://a"],
            rows=[row("uname", "-s", out="MINGW64_NT-10.0\n")],
        ),
        Case(
            "browser-unknown",
            "open-browser",
            args=["http://a"],
            rows=[row("uname", "-s", out="Plan9\n")],
        ),
        Case(
            "npm-script-ok",
            "run-npm-script",
            args=["build:web", "Building web"],
            setup=("manifests",),
        ),
        Case("npm-script-default-desc", "run-npm-script", args=["lint"], setup=("manifests",)),
        Case(
            "npm-script-fails",
            "run-npm-script",
            args=["lint"],
            rows=[row("npm", "run lint", rc=4)],
            setup=("manifests",),
        ),
        Case(
            "node-ok",
            "check-node-version",
            rows=[row("node", "-v", out="v22.1.0\n")],
            env={"DEBUG": "true"},
        ),
        Case("node-old", "check-node-version", rows=[row("node", "-v", out="v16.20.2\n")]),
        Case(
            "node-min-arg",
            "check-node-version",
            args=["22.10.0"],
            rows=[row("node", "-v", out="v22.9.0\n")],
        ),
        Case(
            "node-no-v",
            "check-node-version",
            rows=[row("node", "-v", out="20.0.0\n")],
            env={"DEBUG": "true"},
        ),
        Case("node-absent", "check-node-version", unstub=("node",), hidden=("node", "nodejs")),
        Case("go-present", "check-go-installed", env={"DEBUG": "true"}),
        Case("go-absent", "check-go-installed", unstub=("go",), hidden=("go",)),
    ],
    "go": [
        Case("go-no-gomod", "ensure-go-installed"),
        Case(
            "go-current",
            "ensure-go-installed",
            setup=("gomod",),
            rows=[GO_NEW],
            env={"DEBUG": "true"},
        ),
        Case(
            "go-old-replaced",
            "ensure-go-installed",
            setup=("gomod",),
            rows=[GO_OLD, row("mktemp", "-d", sh=MKTEMP_SH)],
        ),
        Case(
            "go-absent-arm",
            "ensure-go-installed",
            setup=("gomod_plain",),
            unstub=("go",),
            hidden=("go",),
            rows=[row("uname", "-m", out="aarch64\n"), row("mktemp", "-d", sh=MKTEMP_SH)],
        ),
        Case(
            "go-not-linux",
            "ensure-go-installed",
            setup=("gomod",),
            rows=[GO_OLD, row("uname", "-s", out="Darwin\n")],
        ),
        Case(
            "go-bad-arch",
            "ensure-go-installed",
            setup=("gomod",),
            rows=[GO_OLD, row("uname", "-m", out="riscv64\n")],
        ),
        Case(
            "go-download-fails",
            "ensure-go-installed",
            setup=("gomod",),
            rows=[
                GO_OLD,
                row("mktemp", "-d", sh=MKTEMP_SH),
                row("curl", rc=22, err="curl: (22) 404\n"),
            ],
        ),
        Case(
            "go-bad-tarball",
            "ensure-go-installed",
            setup=("gomod",),
            rows=[GO_OLD, row("mktemp", "-d", sh=MKTEMP_SH), row("tar", "-tzf *", rc=2)],
        ),
        Case(
            "go-unpack-fails",
            "ensure-go-installed",
            setup=("gomod",),
            rows=[GO_OLD, row("mktemp", "-d", sh=MKTEMP_SH), row("sudo", "tar *", rc=2)],
        ),
        Case(
            "go-version-fails",
            "ensure-go-installed",
            setup=("gomod",),
            rows=[row("go", "version", rc=3)],
        ),
    ],
    "host": [
        Case("tools-complete", "ensure-host-tools", rows=[row("uname", "-s", out="Linux\n")]),
        Case(
            "tools-missing",
            "ensure-host-tools",
            unstub=("curl", "gcc"),
            hidden=("jq", "zstd", "cc", "gcc"),
        ),
        Case(
            "tools-apt-fails",
            "ensure-host-tools",
            unstub=("gcc",),
            hidden=("jq", "cc", "gcc"),
            rows=[row("sudo", "apt-get install *", rc=100)],
        ),
        Case(
            "tools-not-linux",
            "ensure-host-tools",
            hidden=("zstd",),
            rows=[row("uname", "-s", out="Darwin\n")],
        ),
        Case("bashcov-build", "ensure-bashcov-sup", rows=[row("gcc", sh=GCC_SH)]),
        Case("bashcov-current", "ensure-bashcov-sup", setup=("bashcov_old_bin",)),
        Case("bashcov-no-gcc", "ensure-bashcov-sup", unstub=("gcc",), hidden=("gcc",)),
        Case(
            "bashcov-gcc-fails", "ensure-bashcov-sup", rows=[row("gcc", rc=1, err="cc1: error\n")]
        ),
    ],
    "docker": [
        Case(
            "reexec-already",
            "reexec-docker-group",
            args=["devbox"],
            env={"REDIACC_DOCKER_GROUP_REEXEC": "1"},
        ),
        Case("reexec-docker-works", "reexec-docker-group", args=["devbox"]),
        Case(
            "reexec-no-sg",
            "reexec-docker-group",
            rows=[DOCKER_DOWN],
            unstub=("sg",),
            hidden=("sg",),
        ),
        Case("reexec-no-group", "reexec-docker-group", rows=[DOCKER_DOWN, GROUP_NONE]),
        Case("reexec-not-member", "reexec-docker-group", rows=[DOCKER_DOWN, GROUP_OTHER]),
        Case(
            "reexec-probe-fails",
            "reexec-docker-group",
            rows=[DOCKER_DOWN, GROUP_MEMBER, row("sg", "docker -c docker version", rc=1)],
        ),
        Case(
            "reexec-execs",
            "reexec-docker-group",
            args=["devbox", "up", "a b", "it's", "--x=$HOME", "a,b", "#c", "~d", "e~#", ""],
            rows=[DOCKER_DOWN, GROUP_MEMBER],
        ),
        Case(
            "reexec-substring-member",
            "reexec-docker-group",
            rows=[
                DOCKER_DOWN,
                row("getent", "group docker", out="docker:x:999:sandbox-user2,xsandbox-user\n"),
            ],
        ),
        Case(
            "reexec-no-entrypoint",
            "reexec-docker-group",
            rows=[DOCKER_DOWN, GROUP_MEMBER],
            env={"SCRIPT_ENTRYPOINT": None},
        ),
        Case(
            "install-usable",
            "ensure-docker-installed",
            rows=[row("docker", "--version", out="Docker version 27.0.1\n")],
            env={"DEBUG": "true"},
        ),
        Case("install-sudo-only", "ensure-docker-installed", rows=[DOCKER_DOWN, GROUP_MEMBER]),
        Case(
            "install-not-linux",
            "ensure-docker-installed",
            rows=[
                DOCKER_DOWN,
                row("sudo", "docker version", rc=1),
                row("uname", "-s", out="Darwin\n"),
            ],
        ),
        Case(
            "install-full",
            "ensure-docker-installed",
            setup=("renet_tree",),
            rows=[
                DOCKER_DOWN,
                row("sudo", "docker version", rc=1),
                GO_NEW,
                row("build.sh", "dev", sh=RENET_BUILD_SH),
                GROUP_OTHER,
            ],
        ),
        Case(
            "install-renet-fails",
            "ensure-docker-installed",
            setup=("renet_tree",),
            rows=[
                DOCKER_DOWN,
                row("sudo", "docker version", rc=1),
                GO_NEW,
                row("build.sh", "dev", sh=RENET_BUILD_SH),
                row("sudo", "*install-docker*", rc=1),
            ],
        ),
        Case("group-none", "ensure-docker-group", rows=[GROUP_NONE]),
        Case("group-member-active", "ensure-docker-group", rows=[GROUP_MEMBER]),
        Case("group-member-inactive", "ensure-docker-group", rows=[GROUP_MEMBER, DOCKER_DOWN]),
        Case("group-add", "ensure-docker-group", rows=[GROUP_OTHER]),
        Case(
            "group-substring-member",
            "ensure-docker-group",
            rows=[row("getent", "group docker", out="docker:x:999:sandbox-user2\n")],
        ),
        Case(
            "group-add-fails",
            "ensure-docker-group",
            rows=[GROUP_OTHER, row("sudo", "usermod *", rc=6)],
        ),
    ],
    "lane": [
        Case(
            "decide-in-devbox",
            "lane-decide",
            env={"REDIACC_IN_DEVBOX": "1", "REDIACC_LANE": "devbox"},
        ),
        Case("decide-env-devbox", "lane-decide", env={"REDIACC_LANE": "devbox"}),
        Case("decide-env-bogus", "lane-decide", env={"REDIACC_LANE": "podman"}),
        Case("decide-sticky", "lane-decide", setup=("sticky_devbox",)),
        Case("decide-sticky-empty", "lane-decide", setup=("sticky_empty",), rows=RUNNING),
        Case("decide-running", "lane-decide", rows=RUNNING),
        Case(
            "decide-stopped",
            "lane-decide",
            rows=[
                row("docker", "ps -aq *", out="cid1\n"),
                row("docker", "inspect *", out="false\n"),
            ],
        ),
        Case("decide-sudo-docker", "lane-decide", rows=[DOCKER_DOWN, *RUNNING]),
        Case("route-host", "lane-should-route", env={"REDIACC_LANE": "host"}),
        Case("route-not-running", "lane-should-route", env={"REDIACC_LANE": "devbox"}),
        Case("route-ok", "lane-should-route", rows=RUNNING),
        Case(
            "route-mount-bad",
            "lane-should-route",
            rows=[*RUNNING, row("docker", "exec *test -f*", rc=1)],
        ),
        Case(
            "route-identity-bad",
            "lane-should-route",
            rows=[
                *RUNNING,
                row(
                    "docker",
                    "exec *status --porcelain*",
                    rc=128,
                    err="fatal: detected dubious ownership in repository\n",
                ),
            ],
        ),
        Case(
            "run-passes-status",
            "lane-run",
            args=["check:ci-foo", "a b"],
            rows=[*RUNNING, row("docker", "exec *", rc=7, out="gate output\n")],
        ),
        Case("run-not-running", "lane-run", args=["x"]),
    ],
    "renet": [
        Case("source-hash", "renet-source-hash", args=["private/renet"], setup=("renet_tree",)),
        Case("source-hash-empty", "renet-source-hash", args=["packages"], setup=("packages",)),
        Case("source-hash-missing", "renet-source-hash", args=["nowhere"]),
        Case("artifact-fp", "renet-artifact-fp", args=["package.json"], setup=("manifests",)),
        Case("artifact-fp-absent", "renet-artifact-fp", args=["nothing"]),
        Case(
            "renet-fresh",
            "ensure-renet-built",
            setup=("renet_tree",),
            rows=[row("build.sh", "dev", sh=RENET_BUILD_SH)],
            env={"DEBUG": "true"},
            repeat=2,
        ),
        Case(
            "renet-license-key",
            "ensure-renet-built",
            setup=("renet_tree", "renet_env"),
            rows=[row("build.sh", "dev", sh=RENET_BUILD_SH)],
            env={"RDC_RENET_LICENSE": "1"},
        ),
        Case(
            "renet-key-from-shell",
            "ensure-renet-built",
            setup=("renet_tree", "renet_env"),
            rows=[row("build.sh", "dev", sh=RENET_BUILD_SH)],
            env={"ACCOUNT_ED25519_PUBLIC_KEY": "shell-key"},
        ),
        Case(
            "renet-build-fails",
            "ensure-renet-built",
            setup=("renet_tree",),
            rows=[row("build.sh", "dev", rc=1, err="asset staging aborted\n")],
        ),
        Case("renet-no-binary", "ensure-renet-built", setup=("renet_tree",)),
        Case(
            "renet-darwin",
            "ensure-renet-built",
            setup=("renet_tree", "renet_env"),
            rows=[row("uname", "-s", out="Darwin\n"), row("build.sh", "dev", sh=RENET_BUILD_SH)],
        ),
        Case(
            "renet-no-go",
            "ensure-renet-built",
            setup=("renet_tree",),
            unstub=("go",),
            hidden=("go",),
        ),
    ],
}


def base_dir() -> pathlib.Path:
    return pathlib.Path(tempfile.gettempdir()) / BASE_NAME


def build_sandbox(repo: pathlib.Path, case: Case) -> tuple[pathlib.Path, Farm]:
    base = base_dir()
    if base.exists():
        shutil.rmtree(base)
    root = base / "root"
    (root / ".ci" / "scripts").mkdir(parents=True)
    (root / ".ci" / "lib").symlink_to(repo / ".ci" / "lib")
    (root / ".ci" / "config").symlink_to(repo / ".ci" / "config")
    # `devbox.sh` refuses to load without `<its dir>/../rediacc_ci/core`, resolved LOGICALLY through the `.ci/lib` link, so the lane cases need the package beside it.
    (root / ".ci" / "rediacc_ci").symlink_to(repo / ".ci" / "rediacc_ci")
    (root / ".ci" / "scripts" / "lib").symlink_to(repo / ".ci" / "scripts" / "lib")
    (root / ".devcontainer").symlink_to(repo / ".devcontainer")
    (root / "home").mkdir()
    for name in case.setup:
        FIXTURES[name](root)
    farm = Farm(base / "farm")
    farm.stub(*(n for n in LOGGED if n not in case.unstub))
    farm.stub(*UNLOGGED, logged=False)
    farm.stub_at(root / ".ci" / "scripts" / "setup" / "build-packages.sh")
    farm.stub_at(root / "private" / "renet" / "build.sh")
    for spec in case.rows:
        fields = dict(spec)
        farm.respond(fields.pop("name"), fields.pop("glob"), **fields)
    farm.respond("uname", "-s", out="Linux\n")
    farm.respond("uname", "-m", out="x86_64\n")
    farm.respond("getent", "group docker", out="docker:x:999:sandbox-user\n")
    farm.respond("go", "version", out="go version go1.25.13 linux/amd64\n")
    farm.respond("node", "-v", out="v22.23.2\n")
    farm.respond("docker", "version", out="Client: 27\n")
    return root, farm


def side_env(root: pathlib.Path, farm: Farm, case: Case) -> dict[str, str]:
    base = {
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "HOME": str(root / "home"),
        "USER": "sandbox-user",
        "LC_ALL": "C",
        "LANG": "C",
        "PYTHONDONTWRITEBYTECODE": "1",
        "CONSOLE_ROOT_DIR": str(root),
        "SCRIPT_ENTRYPOINT": str(root / "run.sh"),
    }
    for key, value in case.env.items():
        if value is None:
            base.pop(key, None)
        else:
            base[key] = value
    return farm.env(base, hidden=case.hidden)


OLD_PROGRAM = r"""
set -euo pipefail
R="$1"; shift
source "$R/.ci/config/constants.sh"
source "$R/.ci/scripts/lib/toolchain.sh"
source "$R/.ci/lib/local-common.sh"
fn="$1"; shift
case "$fn" in
    prompt_continue) prompt_continue "$@" || exit 1 ;;
    # `gate_lane_run` does not load devbox.sh itself: its only caller (`.ci/legacy/run-legacy.sh`) runs `gate_lane_should_route` first, which does. The harness loads it the same way that call path does.
    gate_lane_run) . "$R/.ci/lib/devbox.sh"; gate_lane_run "$@" ;;
    _renet_source_hash | _renet_artifact_fp) "$fn" "$@" ;;
    *) "$fn" "$@" ;;
esac
"""


def run_side(
    side: str, repo: pathlib.Path, root: pathlib.Path, case: Case, env: dict[str, str]
) -> subprocess.CompletedProcess:
    if side == "old":
        argv = ["bash", "-c", OLD_PROGRAM, "lc-old", str(root), FN[case.verb], *case.args]
    else:
        env = dict(env, PYTHONPATH=str(repo / ".ci"))
        argv = ["python3", "-m", "rediacc_ci.core.local_common", case.verb, *case.args]
    return subprocess.run(
        argv,
        cwd=root,
        env=env,
        input=case.stdin if case.stdin is not None else "",
        capture_output=True,
        text=True,
        check=False,
        timeout=300,
    )


def tree_listing(root: pathlib.Path) -> list[str]:
    """Every path under the sandbox that is not a symlink into the checkout: kind, and content hash for files."""
    out = []
    for current, dirs, files in os.walk(root):
        dirs.sort()
        for name in sorted(dirs + files):
            path = pathlib.Path(current) / name
            rel = path.relative_to(root)
            if path.is_symlink():
                out.append("%s link %s" % (rel, os.readlink(path)))
                with contextlib.suppress(ValueError):
                    dirs.remove(name)
            elif path.is_dir():
                out.append("%s dir" % rel)
            else:
                mode = "x" if os.access(path, os.X_OK) else "-"
                out.append(
                    "%s file%s %s" % (rel, mode, hashlib.sha256(path.read_bytes()).hexdigest()[:16])
                )
    return out


def observe(side: str, repo: pathlib.Path, case: Case) -> list[str]:
    """Run one case on one side in the fixed sandbox; return its observation lines."""
    root, farm = build_sandbox(repo, case)
    lines: list[str] = []

    def norm(text: str) -> str:
        return text.replace(str(root), "<root>").replace(str(farm.root), "<farm>")

    for attempt in range(case.repeat):
        tag = case.name if case.repeat == 1 else "%s#%d" % (case.name, attempt)
        if attempt:
            for name in case.between:
                FIXTURES[name](root)
        farm.reset_log()
        proc = run_side(side, repo, root, case, side_env(root, farm, case))
        lines.append("obs %s rc=%d" % (tag, proc.returncode))
        lines += [
            "obs %s out#%d| %s" % (tag, i, norm(t)) for i, t in enumerate(proc.stdout.splitlines())
        ]
        for i, raw in enumerate(proc.stderr.splitlines()):
            # bash stamps `<file>: line <N>: ` on its own diagnostics (unbound variable, cd); a port cannot reproduce the twin's line numbers, so the stamp is dropped on both sides and the message compared.
            text = raw
            if ": line " in raw and raw.split(": line ", 1)[1].split(":", 1)[0].isdigit():
                text = raw.split(": line ", 1)[1].split(": ", 1)[1]
            lines.append("obs %s err#%d| %s" % (tag, i, norm(text)))
        lines += ["obs %s call#%d| %s" % (tag, i, norm(t)) for i, t in enumerate(farm.transcript())]
        lines += ["obs %s tree| %s" % (tag, norm(t)) for t in tree_listing(root)]
    shutil.rmtree(base_dir(), ignore_errors=True)
    return lines


@contextlib.contextmanager
def locked():
    lock = pathlib.Path(tempfile.gettempdir()) / (BASE_NAME + ".lock")
    with open(lock, "w") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="one side of the core.local_common actions differential"
    )
    parser.add_argument("--side", choices=("old", "new"), required=True)
    parser.add_argument("--twin", required=True)
    parser.add_argument("--port", required=True)
    parser.add_argument("scenario", choices=sorted(SCENARIOS))
    args = parser.parse_args(argv)
    repo = pathlib.Path.cwd().resolve()
    for label, rel in (("twin", args.twin), ("port", args.port)):
        if not (repo / rel).is_file():
            sys.stderr.write(
                "local_common_actions_shadow_driver: the %s %s does not exist under %s\n"
                % (label, rel, repo)
            )
            return EXIT_CANNOT_RUN
    with locked():
        for case in SCENARIOS[args.scenario]:
            for line in observe(args.side, repo, case):
                print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
