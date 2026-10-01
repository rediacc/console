"""Port of `.ci/scripts/test/test-linux-packages.sh`: build deb, rpm, apk and archlinux packages around a dummy binary, validate their metadata, install them in distro containers, build signed repository metadata and prove the signing controls.

The test list, the order of the phases and every assertion are the twin's. The package builders are the PORTS (`rediacc_ci.build.build_linux_pkg` and `build_pkg_repo`), reached as `python3 -m`, so this test now exercises the code that replaces the bash builders and keeps working once they are deleted; `nfpm` comes from `rediacc_ci.build.ensure_nfpm` when it is not on PATH.

Deliberate differences from the twin (Rule T), each with a test that fails on the bash behaviour:

  1. `set -e` WAS OFF INSIDE EVERY TEST. `run_test` calls each phase function as an `if` condition, and bash ignores `set -e` there, so a failing `gpg --quick-generate-key`, a failing repo build, or a failing `docker run -d nginx` was silently skipped and surfaced later as a missing file with the wrong name. Each of those calls is now checked where it happens.
  2. A SECRET LEFT BEHIND. The throwaway GPG home, holding the signing key, was removed only at the end of the signing block, and every control that returned early skipped that. It is removed on every path. `GNUPGHOME` and the exported key variables no longer leak into the later phases either: they are passed to the children that need them.
  3. CONTAINERS AND THE NETWORK LEAKED on an interrupted or failed phase 5. nginx and the network are removed in a `finally`.
  4. UNKNOWN ARGUMENTS WERE IGNORED, and `--dry-run` only counted as the first argument. Anything but `--dry-run` is refused with exit 2.
"""

import contextlib
import dataclasses
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import time
import typing

from rediacc_ci import log, paths
from rediacc_ci.core import common
from rediacc_ci.well_known import RELEASES_ORIGIN

PKG_NAME = "rediacc-cli"
PKG_BINARY_NAME = "rdc"
TEST_VERSION = "99.0.0"
DEFAULT_RELEASES = RELEASES_ORIGIN
PUBLISHED_KEY_REL = ".ci/keys/gpg-public.asc"
APK_KEY_NAME = ".SIGN.RSA.releases@rediacc.com.rsa.pub"
DUMMY_BINARY = '#!/bin/sh\necho "rdc version 99.0.0"\n'
USAGE = "usage: test-linux-packages.sh [--dry-run]"


def version_token_re(version: str) -> str:
    """An ERE matching the version as a whole token: not flanked by another digit or dot, so 99.0.0 does not match 99.0.01 or 199.0.0."""
    v = version.removeprefix("v")
    return f"(^|[^0-9.])v?{v.replace('.', chr(92) + '.')}([^0-9.]|$)"


def assert_version_field(text: str, label: str, expected: str = TEST_VERSION) -> bool:
    """The named metadata field must carry EXACTLY `expected`; a prefix match let `99.0.01` through in the old idiom."""
    pattern = re.compile(rf"^\s*{re.escape(label)}\s*:")
    line = next((ln for ln in text.splitlines() if pattern.match(ln)), "")
    if not line:
        log.error(f"no '{label}' field found in package metadata")
        return False
    value = re.sub(rf"^\s*{re.escape(label)}\s*:\s*", "", line)
    if value != expected:
        log.error(f"{label} mismatch: expected '{expected}', got '{value}'")
        return False
    return True


def weld_armor(armor: str) -> str:
    """Join armor line 6 onto line 7, the shape a two-part Bitwarden secret takes when part 1 has no trailing newline (the twin's awk program)."""
    out: list[str] = []
    lines = armor.splitlines()
    i = 0
    n = 0
    while i < len(lines):
        line = lines[i]
        n += 1
        if line.startswith("-----"):
            out.append(line)
        elif n == 6 and i + 1 < len(lines):
            i += 1
            n += 1
            out.append(line + lines[i])
        else:
            out.append(line)
        i += 1
    return "\n".join(out) + "\n"


@dataclasses.dataclass
class Suite:
    dry_run: bool
    root: pathlib.Path
    test_dir: pathlib.Path
    releases: str
    passed: int = 0
    failed: int = 0
    failed_names: list[str] = dataclasses.field(default_factory=list)

    @property
    def env(self) -> dict[str, str]:
        return {
            **os.environ,
            "PYTHONPATH": str(self.root / ".ci") + os.pathsep + os.environ.get("PYTHONPATH", ""),
        }

    def sh(
        self, argv: list[str], env: dict[str, str] | None = None, quiet: bool = True
    ) -> subprocess.CompletedProcess[str]:
        try:
            return subprocess.run(
                argv,
                env=env or self.env,
                capture_output=quiet,
                text=True,
                check=False,
                stdin=subprocess.DEVNULL,
            )
        except OSError as exc:
            return subprocess.CompletedProcess(argv, 127, "", str(exc))

    def build_pkg(
        self,
        *args: str,
        env: dict[str, str] | None = None,
        output: str = "packages",
        quiet: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        """`build_linux_pkg` over the dummy binary into `<test_dir>/<output>`; `args` carry the format and arch."""
        return self.sh(
            [
                sys.executable,
                "-m",
                "rediacc_ci.build.build_linux_pkg",
                "--binary",
                str(self.test_dir / "rdc-dummy"),
                "--version",
                TEST_VERSION,
                *args,
                "--output",
                str(self.test_dir / output),
            ],
            env=env,
            quiet=quiet,
        )

    def run_test(self, name: str, fn: typing.Callable[[], bool]) -> None:
        log.step(f"TEST: {name}")
        try:
            ok = fn()
        except Exception as exc:  # noqa: BLE001 - a phase that raises is a failed phase, not a crashed run
            log.error(f"{type(exc).__name__}: {exc}")
            ok = False
        if ok:
            log.info(f"PASS: {name}")
            self.passed += 1
        else:
            log.error(f"FAIL: {name}")
            self.failed += 1
            self.failed_names.append(name)

    # ---- phase 1 -------------------------------------------------------------------------------------------------

    def p1_dummy(self) -> bool:
        log.step("Phase 1: Package Build Validation")
        dummy = self.test_dir / "rdc-dummy"
        dummy.write_text(DUMMY_BINARY)
        dummy.chmod(0o755)
        return os.access(dummy, os.X_OK)

    def p1_build(self, fmt: str, arch: str) -> bool:
        done = self.build_pkg("--arch", arch, "--format", fmt, quiet=False)
        return done.returncode == 0

    def pkg_path(self, name: str) -> pathlib.Path:
        return self.test_dir / "packages" / name

    def p1_deb_metadata(self) -> bool:
        deb = self.pkg_path(f"{PKG_NAME}_{TEST_VERSION}_amd64.deb")
        if not deb.is_file():
            return False
        info = self.sh(["dpkg-deb", "--info", str(deb)]).stdout
        if f"Package: {PKG_NAME}" not in info or not assert_version_field(info, "Version"):
            return False
        if "Architecture: amd64" not in info or "Maintainer:" not in info:
            return False
        log.info("  DEB fields validated: Package, Version, Architecture, Maintainer")
        return True

    def p1_rpm_metadata(self) -> bool:
        rpm = self.pkg_path(f"{PKG_NAME}-{TEST_VERSION}-1.x86_64.rpm")
        if not rpm.is_file():
            log.error(f"{rpm} was not built")
            return False
        if not shutil.which("rpm"):
            log.error(
                "rpm is not installed, so the .rpm metadata was never read (CI installs it; locally: sudo apt-get install -y rpm)"
            )
            return False
        info = self.sh(["rpm", "-qip", str(rpm)]).stdout
        if (
            not re.search(rf"Name.*: {re.escape(PKG_NAME)}", info)
            or not assert_version_field(info, "Version")
            or "Architecture: x86_64" not in info
        ):
            return False
        log.info("  RPM fields validated: Name, Version, Architecture")
        return True

    def p1_apk_metadata(self) -> bool:
        apk = self.pkg_path(f"{PKG_NAME}-{TEST_VERSION}-r1-amd64.apk")
        if not apk.is_file():
            return False
        if self.sh(["gzip", "-t", str(apk)]).returncode != 0:
            log.error("APK file is not valid gzip")
            return False
        log.info("  APK validated: valid gzip archive")
        return True

    def p1_arch_metadata(self) -> bool:
        pkg = self.pkg_path(f"{PKG_NAME}-{TEST_VERSION}-1-x86_64.pkg.tar.zst")
        if not pkg.is_file():
            return False
        if shutil.which("zstd"):
            if self.sh(["zstd", "-t", str(pkg)]).returncode != 0:
                log.error("Archlinux package is not valid zstd")
                return False
            log.info("  Archlinux validated: valid zstd archive")
            return True
        if pkg.stat().st_size <= 0:
            return False
        log.info("  Archlinux validated: non-empty file (zstd not available for deeper check)")
        return True

    # ---- phases 2, 3: installs in containers ---------------------------------------------------------------------

    def docker_run(self, image: str, script: str) -> bool:
        argv = [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{self.test_dir}:/packages:ro",
            image,
            "sh",
            "-c",
            script,
        ]
        return self.sh(argv, quiet=False).returncode == 0

    def install(self, kind: str, image: str, label: str, command: str) -> bool:
        if self.dry_run:
            log.info(f"[DRY-RUN] Would test {kind} install on {label}")
            return True
        pattern = version_token_re(TEST_VERSION)
        return self.docker_run(
            image,
            f"\n        {command} && \\\n        test -x /usr/local/bin/{PKG_BINARY_NAME} && \\\n"
            f"        /usr/local/bin/{PKG_BINARY_NAME} --version 2>&1 | grep -qE '{pattern}' && \\\n"
            f"        echo 'Install verified on {label}'\n    ",
        )

    def deb(self, image: str, label: str) -> bool:
        return self.install(
            "dpkg", image, label, f"dpkg -i /packages/packages/{PKG_NAME}_{TEST_VERSION}_amd64.deb"
        )

    def rpm(self, image: str, label: str) -> bool:
        return self.install(
            "rpm", image, label, f"rpm -i /packages/packages/{PKG_NAME}-{TEST_VERSION}-1.x86_64.rpm"
        )

    def apk(self, image: str, label: str) -> bool:
        return self.install(
            "apk",
            image,
            label,
            f"apk add --no-cache --allow-untrusted /packages/packages/{PKG_NAME}-{TEST_VERSION}-r1-amd64.apk",
        )

    def pacman(self, image: str, label: str) -> bool:
        return self.install(
            "pacman",
            image,
            label,
            f"pacman -U --noconfirm /packages/packages/{PKG_NAME}-{TEST_VERSION}-1-x86_64.pkg.tar.zst",
        )

    # ---- phase 4 -------------------------------------------------------------------------------------------------

    def repo_build(
        self,
        output: str,
        env: dict[str, str] | None = None,
        dry_run: bool = False,
        quiet: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        argv = [
            sys.executable,
            "-m",
            "rediacc_ci.build.build_pkg_repo",
            "--version",
            TEST_VERSION,
            "--local-pkgs",
            str(self.test_dir / "packages"),
            "--output",
            str(self.test_dir / output),
            "--channel",
            "test",
        ]
        if dry_run:
            argv.append("--dry-run")
        return self.sh(argv, env=env, quiet=quiet)

    def p4_repo_dry_run(self) -> bool:
        return self.repo_build("repo", dry_run=True, quiet=False).returncode == 0

    def signing_controls(self, env: dict[str, str]) -> bool:
        """The twin's controls, in order. `env` carries the throwaway key; each control varies exactly one thing."""
        published = {**env, "RELEASE_GPG_PUBLIC_KEY_FILE": str(self.root / PUBLISHED_KEY_REL)}
        if self.repo_build("repo-control", env=published).returncode == 0:
            log.error(
                "CONTROL FAILED: build-pkg-repo.sh accepted a signing key that is not the published public key"
            )
            return False
        log.info("CONTROL: a signing key that is not the published public key is refused")

        if (
            self.build_pkg(
                "--arch", "amd64", "--format", "deb", env=env, output="packages-signed"
            ).returncode
            != 0
        ):
            log.error("a signed deb build with the matching public key failed")
            return False
        if (
            self.build_pkg(
                "--arch", "amd64", "--format", "deb", env=published, output="packages-control"
            ).returncode
            == 0
        ):
            log.error(
                "CONTROL FAILED: build-linux-pkg.sh signed a deb with a key that is not the published public key"
            )
            return False
        log.info(
            "CONTROL: build-linux-pkg.sh refuses a signing key that is not the published public key"
        )

        # A key whose armor lines are welded must still sign: the private key spans two Bitwarden items and part 1 has no trailing newline.
        welded = {**env, "RELEASE_GPG_PRIVATE_KEY": weld_armor(env["RELEASE_GPG_PRIVATE_KEY"])}
        if (
            self.build_pkg(
                "--arch", "amd64", "--format", "deb", env=welded, output="packages-welded"
            ).returncode
            != 0
        ):
            log.error(
                "a deb build with WELDED armor lines failed; the gpg re-export is not canonicalising the key"
            )
            return False
        log.info("CONTROL: a signing key with welded armor lines is canonicalised and still signs")

        # An empty key must not ship an unsigned package when signing is required.
        required = {**env, "RELEASE_SIGNING_REQUIRED": "1", "RELEASE_GPG_PRIVATE_KEY": ""}
        if (
            self.build_pkg(
                "--arch", "amd64", "--format", "deb", env=required, output="packages-unsigned"
            ).returncode
            == 0
        ):
            log.error(
                "CONTROL FAILED: an EMPTY signing key shipped an unsigned deb under RELEASE_SIGNING_REQUIRED=1"
            )
            return False
        log.info("CONTROL: an empty signing key is refused when signing is required")
        optional = {**env, "RELEASE_GPG_PRIVATE_KEY": ""}
        if (
            self.build_pkg(
                "--arch", "amd64", "--format", "deb", env=optional, output="packages-unsigned-ok"
            ).returncode
            != 0
        ):
            log.error(
                "CONTROL FAILED: an unsigned local build (no RELEASE_SIGNING_REQUIRED) should still succeed"
            )
            return False
        log.info("CONTROL: without the flag, an unsigned local build still succeeds")

        # apk is declared-unsigned, so it must still BUILD under the flag.
        apk_unsigned = {
            **env,
            "RELEASE_SIGNING_REQUIRED": "1",
            "APK_RSA_PRIVATE_KEY": "",
            "RELEASE_GPG_PRIVATE_KEY": "",
        }
        if (
            self.build_pkg(
                "--arch",
                "amd64",
                "--format",
                "apk",
                env=apk_unsigned,
                output="packages-apk-unsigned",
            ).returncode
            != 0
        ):
            log.error("a declared-unsigned apk must still build under RELEASE_SIGNING_REQUIRED=1")
            return False
        log.info("CONTROL: apk is declared-unsigned and still builds when signing is required")
        return self.apk_signing_controls(env)

    def first_apk(self, directory: str) -> pathlib.Path | None:
        found = sorted((self.test_dir / directory).glob("*.apk"))
        return found[0] if found else None

    def apk_signing_controls(self, env: dict[str, str]) -> bool:
        """The signed apk path, with the key_name pin: APKv2 matches the public key by FILENAME, and nfpm defaults key_name to the maintainer email."""
        key = self.test_dir / "apk-signing-test.rsa"
        if self.sh(["openssl", "genrsa", "-out", str(key), "2048"]).returncode != 0:
            log.warn("openssl unavailable; apk signing path NOT verified this run")
            return True
        signed_env = {**env, "APK_RSA_PRIVATE_KEY": key.read_text()}
        if (
            self.build_pkg(
                "--arch", "amd64", "--format", "apk", env=signed_env, output="packages-apk-signed"
            ).returncode
            != 0
        ):
            log.error("an apk build WITH an RSA key failed; conditional signing is broken")
            return False
        signed = self.first_apk("packages-apk-signed")
        if signed is None:
            log.error("the signed apk build produced no .apk at all")
            return False
        member = next((m for m in self.tar_members(signed) if m.startswith(".SIGN.")), "")
        if member != APK_KEY_NAME:
            log.error(
                f"apk signature member is '{member or '<none>'}', expected '{APK_KEY_NAME}' -- key_name is not pinned, "
                "so a PKG_MAINTAINER change would invalidate every deployed /etc/apk/keys entry"
            )
            return False
        log.info(f"CONTROL: with a key, apk signs under the PINNED key_name ({member})")
        unsigned = self.first_apk("packages-apk-unsigned")
        if unsigned is None:
            log.error(
                "the unsigned apk build produced no .apk, so the control below compares nothing"
            )
            return False
        if any(m.startswith(".SIGN.") for m in self.tar_members(unsigned)):
            log.error("CONTROL FAILED: an apk built with NO key still carries a .SIGN member")
            return False
        log.info("CONTROL: with no key, the apk carries no .SIGN member")
        return True

    def tar_members(self, archive: pathlib.Path) -> list[str]:
        return self.sh(["tar", "tzf", str(archive)]).stdout.splitlines()

    def p4_apt_metadata(self) -> bool:
        if self.dry_run:
            log.info("[DRY-RUN] Would validate APT metadata structure")
            return True
        repo_out = self.test_dir / "repo-real"
        repo_out.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="gnupg-") as gnupg:
            os.chmod(gnupg, 0o700)
            genv = {**self.env, "GNUPGHOME": gnupg}
            made = self.sh(
                [
                    "gpg",
                    "--batch",
                    "--yes",
                    "--no-tty",
                    "--pinentry-mode",
                    "loopback",
                    "--passphrase",
                    "",
                    "--quick-generate-key",
                    "Test <test@test.com>",
                    "rsa2048",
                    "sign",
                    "1d",
                ],
                env=genv,
            )
            if made.returncode != 0:
                log.error(
                    f"gpg could not generate the throwaway signing key: {made.stderr.strip()}"
                )
                return False
            listing = self.sh(["gpg", "--list-keys", "--with-colons"], env=genv).stdout
            key_id = next(
                (ln.split(":")[4] for ln in listing.splitlines() if ln.startswith("pub")), ""
            )
            private = self.sh(["gpg", "--armor", "--export-secret-keys", key_id], env=genv).stdout
            public_file = pathlib.Path(gnupg) / "public.asc"
            public_file.write_text(self.sh(["gpg", "--armor", "--export", key_id], env=genv).stdout)
            # The build refuses a signing key that is not the published public key, so the throwaway key's public half is published for this run.
            env = {
                **genv,
                "RELEASE_GPG_PRIVATE_KEY": private.rstrip("\n"),
                "RELEASE_GPG_PUBLIC_KEY_FILE": str(public_file),
            }
            built = self.repo_build("repo-real", env=env, quiet=False)
            if built.returncode != 0:
                log.error("build-pkg-repo.sh failed for the signed repository build")
                return False
            if not self.signing_controls(env):
                return False
        return self.validate_apt_tree(repo_out)

    def validate_apt_tree(self, repo_out: pathlib.Path) -> bool:
        release = repo_out / "apt/dists/stable/Release"
        if not release.is_file():
            log.error("Release file missing")
            return False
        text = release.read_text(errors="replace")
        if "Origin: Rediacc" not in text:
            log.error("Release missing Origin")
            return False
        if "Architectures:" not in text:
            log.error("Release missing Architectures")
            return False
        packages_gz = repo_out / "apt/dists/stable/main/binary-amd64/Packages.gz"
        if not packages_gz.is_file():
            log.error("Packages.gz missing")
            return False
        if self.sh(["gzip", "-t", str(packages_gz)]).returncode != 0:
            log.error("Packages.gz invalid gzip")
            return False
        content = self.sh(["zcat", str(packages_gz)]).stdout
        for needle, message in (
            (f"Package: {PKG_NAME}", "Packages missing Package field"),
            ("Filename:", "Packages missing Filename field"),
            ("SHA256:", "Packages missing SHA256 field"),
        ):
            if needle not in content:
                log.error(message)
                return False
        log.info("  APT metadata validated: Release, Packages.gz, checksums")
        return True

    def p4_rpm_metadata(self) -> bool:
        if self.dry_run:
            log.info("[DRY-RUN] Would validate RPM metadata structure")
            return True
        repo_out = self.test_dir / "repo-real"
        repomd = repo_out / "rpm/repodata/repomd.xml"
        if not repomd.is_file():
            if not shutil.which("createrepo_c"):
                log.error(
                    "createrepo_c is not installed, so no rpm repodata was generated (CI installs it; locally: sudo apt-get install -y createrepo-c)"
                )
            else:
                log.error("repomd.xml missing")
            return False
        if "<repomd" not in repomd.read_text(errors="replace"):
            log.error("repomd.xml invalid XML")
            return False
        repo_file = repo_out / "rpm/rediacc.repo"
        if not repo_file.is_file():
            log.error("rediacc.repo missing")
            return False
        repo_text = repo_file.read_text(errors="replace")
        if f"baseurl={self.releases}/rpm/test/" not in repo_text:
            log.error(f".repo baseurl wrong (expected {self.releases}/rpm/test/)")
            return False
        if f"gpgkey={self.releases}/rpm/test/gpg.key" not in repo_text:
            log.error(f".repo gpgkey wrong (expected {self.releases}/rpm/test/gpg.key)")
            return False
        if not (repo_out / "rpm/gpg.key").is_file():
            log.error("gpg.key missing")
            return False
        log.info("  RPM metadata validated: repomd.xml, rediacc.repo, gpg.key")
        return True

    # ---- phase 5 -------------------------------------------------------------------------------------------------

    def p5_apt_flow(self) -> bool:
        if self.dry_run:
            log.info("[DRY-RUN] Would test full APT flow with local nginx")
            return True
        repo_out = self.test_dir / "repo-real"
        if not (repo_out / "apt").is_dir():
            log.error("APT repo not built (phase 4 must pass first)")
            return False
        network = f"pkg-test-{os.getpid()}"
        nginx = f"pkg-test-nginx-{os.getpid()}"
        self.sh(["docker", "network", "create", network])
        started = False
        try:
            run = self.sh(
                [
                    "docker",
                    "run",
                    "-d",
                    "--rm",
                    "--name",
                    nginx,
                    "--network",
                    network,
                    "-v",
                    f"{repo_out}/apt:/usr/share/nginx/html/apt:ro",
                    "nginx:alpine",
                ]
            )
            if run.returncode != 0:
                log.error(f"nginx did not start: {run.stderr.strip()}")
                return False
            started = True
            ready = False
            for _ in range(10):
                if (
                    self.sh(
                        [
                            "docker",
                            "exec",
                            nginx,
                            "wget",
                            "-q",
                            "-O",
                            "/dev/null",
                            "http://localhost/",
                        ]
                    ).returncode
                    == 0
                ):
                    ready = True
                    break
                time.sleep(1)
            if not ready:
                log.error("nginx never answered")
                return False
            script = f"""
            apt-get update -qq && apt-get install -y -qq gnupg ca-certificates >/dev/null 2>&1
            # Add GPG key
            cat /tmp/gpg.key | gpg --dearmor -o /usr/share/keyrings/rediacc.gpg
            # Add sources list pointing to nginx container
            echo 'deb [signed-by=/usr/share/keyrings/rediacc.gpg] http://{nginx}/apt stable main' > /etc/apt/sources.list.d/rediacc.list
            # Update and verify
            apt-get update -qq 2>&1
            apt-cache show {PKG_NAME} | grep -q 'Package: {PKG_NAME}'
            echo 'Full APT flow verified'
        """
            done = self.sh(
                [
                    "docker",
                    "run",
                    "--rm",
                    "--network",
                    network,
                    "-v",
                    f"{repo_out}/apt/gpg.key:/tmp/gpg.key:ro",
                    "ubuntu:22.04",
                    "bash",
                    "-c",
                    script,
                ],
                quiet=False,
            )
            return done.returncode == 0
        finally:
            if started:
                self.sh(["docker", "stop", nginx])
            self.sh(["docker", "network", "rm", network])


def main(argv: list[str]) -> int:
    # Children inherit stdout: line buffering keeps this process's lines in order with theirs when stdout is a pipe.
    if (reconfigure := getattr(sys.stdout, "reconfigure", None)) is not None:
        reconfigure(line_buffering=True)
    if argv not in ([], ["--dry-run"]):
        log.error(f"Unknown option: {' '.join(argv)}")
        print(USAGE, file=sys.stderr)
        return 2
    dry_run = argv == ["--dry-run"]
    root = paths.repo_root()
    env = dict(os.environ)
    if not shutil.which("nfpm"):
        # nfpm is fetched here, not by the calling job, so a developer machine or the devbox works too.
        fetched = subprocess.run(
            [sys.executable, "-m", "rediacc_ci.build.ensure_nfpm"],
            env={**env, "PYTHONPATH": str(root / ".ci")},
            capture_output=True,
            text=True,
            check=False,
        )
        if fetched.returncode != 0:
            sys.stderr.write(fetched.stderr)
            return fetched.returncode
        os.environ["PATH"] = f"{fetched.stdout.strip()}{os.pathsep}{os.environ.get('PATH', '')}"
    test_dir = pathlib.Path(tempfile.mkdtemp(prefix="linux-packages-"))
    suite = Suite(dry_run, root, test_dir, os.environ.get("RELEASES_BASE_URL") or DEFAULT_RELEASES)
    try:
        log.step("Linux Package Tests")
        log.info(f"  Test version: {TEST_VERSION}")
        log.info(f"  Dry-run: {str(dry_run).lower()}")
        log.info(f"  Working dir: {test_dir}")
        try:
            if not dry_run:
                common.require_cmd("docker")
            common.require_cmd("nfpm")
            common.require_cmd("dpkg-deb")
        except common.RefusalError as refusal:
            refusal.report()
            return refusal.code
        for name, fn in plan(suite):
            suite.run_test(name, fn)
        print()
        log.step(
            f"Results: {suite.passed} passed, {suite.failed} failed (total {suite.passed + suite.failed})"
        )
        if suite.failed_names:
            log.error("Failed tests:")
            for name in suite.failed_names:
                log.error(f"  - {name}")
        return 0 if suite.failed == 0 else 1
    finally:
        with contextlib.suppress(OSError):
            shutil.rmtree(test_dir, ignore_errors=True)


def plan(s: Suite) -> list[tuple[str, typing.Callable[[], bool]]]:
    def build(fmt: str, arch: str) -> typing.Callable[[], bool]:
        return lambda: s.p1_build(fmt, arch)

    def on(
        fn: typing.Callable[[str, str], bool], image: str, label: str
    ) -> typing.Callable[[], bool]:
        return lambda: fn(image, label)

    return [
        ("Build dummy binary", s.p1_dummy),
        ("Build .deb package (amd64)", build("deb", "amd64")),
        ("Build .rpm package (x86_64)", build("rpm", "x86_64")),
        ("Build .apk package (amd64)", build("apk", "amd64")),
        ("Build .pkg.tar.zst package (x86_64)", build("archlinux", "x86_64")),
        ("Validate .deb metadata", s.p1_deb_metadata),
        ("Validate .rpm metadata", s.p1_rpm_metadata),
        ("Validate .apk metadata", s.p1_apk_metadata),
        ("Validate .pkg.tar.zst metadata", s.p1_arch_metadata),
        ("Install .deb on Ubuntu 22.04", on(s.deb, "ubuntu:22.04", "Ubuntu 22.04")),
        ("Install .deb on Ubuntu 24.04", on(s.deb, "ubuntu:24.04", "Ubuntu 24.04")),
        ("Install .deb on Debian 12", on(s.deb, "debian:12", "Debian 12")),
        ("Install .rpm on Fedora 40", on(s.rpm, "fedora:40", "Fedora 40")),
        ("Install .rpm on Rocky Linux 9", on(s.rpm, "rockylinux:9", "Rocky Linux 9")),
        ("Install .apk on Alpine 3.19", on(s.apk, "alpine:3.19", "Alpine 3.19")),
        ("Install .apk on Alpine 3.20", on(s.apk, "alpine:3.20", "Alpine 3.20")),
        ("Install .pkg.tar.zst on Arch Linux", on(s.pacman, "archlinux:latest", "Arch Linux")),
        ("Build repo metadata (dry-run)", s.p4_repo_dry_run),
        ("Validate APT metadata structure", s.p4_apt_metadata),
        ("Validate RPM metadata structure", s.p4_rpm_metadata),
        ("Full APT flow with local nginx", s.p5_apt_flow),
    ]


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
