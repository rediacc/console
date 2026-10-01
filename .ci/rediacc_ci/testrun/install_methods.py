"""Port of `.ci/scripts/test/test-install-methods.sh`: test every documented install method (binary, channel verify, update manifest, promotion fixup, docker, apt, dnf, apk, pacman, homebrew, npm, quick install) against a release channel.

Argument validation, the 77-as-skip convention, the channel-less skips, the fenced version probe, `verify_version`'s exact-token rule and the zero-total refusal are the twin's. The container scripts are the twin's own text (`install_scripts`, captured from what the twin hands `docker run`); a differential compares them through a fake `docker`.

Deliberate differences from the twin (Rule T), each with a test that fails on the bash behaviour:

  1. `set -e` WAS OFF INSIDE EVERY TEST. `run_test` calls each test as `"$@" || exit_code=$?`, a context where bash ignores `set -e`, so an unchecked `curl ... -o`, `docker pull` or `cd` failed silently and surfaced later as an unrelated message ("no version output captured"). Those calls are checked where they happen and say what failed.
  2. `--version latest` THAT COULD NOT BE RESOLVED STAYED `latest`, and `latest` accepts ANY well-formed semver, so a channel serving the wrong release passed whenever latest.json was unreachable or `jq` was missing. An unresolvable `latest` is a failure, exit 1.
  3. `verify_version` ESCAPED ONLY DOTS. A version with `+` (build metadata) became an ERE quantifier, so the version failed to match its own output. The expected version is escaped completely.
  4. THE PROMOTION TEST HAD NO CHANNEL-LESS SKIP, unlike every sibling that fetches a channel path, so a schedule or dispatch run failed it on a 404 (the failure the 2026-08-08 guards removed from the others). It skips (77) the same way. It also skipped when `jq` was absent although it never uses jq; that check is gone.
  5. `jq` IS NOT NEEDED: the manifest and `doctor -o json` are parsed in Python, so the update-check and channel-verify tests no longer skip (or fail "jq not available") on a runner without it.
  6. THE VERIFY TEST'S DOWNLOAD WENT TO A PREDICTABLE `/tmp/rdc-verify-$$` and a failing early path left an ~800 MB binary there. It lives in the run's private temporary directory, removed on every path. Nor does the binary-download test `cd` the whole process into that directory any more.
  7. `DOCKER PULL` FAILURE is reported as such instead of as a version mismatch two lines later.
"""

import contextlib
import dataclasses
import functools
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import typing

from rediacc_ci import log
from rediacc_ci.core import common, release_age
from rediacc_ci.testrun import install_scripts as scripts
from rediacc_ci.well_known import HOMEBREW_TAP as WK_HOMEBREW_TAP
from rediacc_ci.well_known import IMAGE_REGISTRY, RELEASES_ORIGIN

VALID_METHODS = (
    "binary",
    "verify",
    "update",
    "promote",
    "docker",
    "apt",
    "dnf",
    "apk",
    "pacman",
    "homebrew",
    "npm",
    "quick",
    "all",
)
PKG_NAME = "rediacc-cli"
PKG_BINARY_NAME = "rdc"
DOCKER_IMAGE = IMAGE_REGISTRY + "/rdc"
HOMEBREW_TAP = WK_HOMEBREW_TAP + "/rediacc-cli"
DEFAULT_RELEASES = RELEASES_ORIGIN
FENCE_BEGIN = "__RDC_VERSION_BEGIN__"
FENCE_END = "__RDC_VERSION_END__"
SKIPPED = 77
CONTAINER_TIMEOUT = 1800
DL_FLAGS = [
    "-fsSL",
    "--connect-timeout",
    "30",
    "--speed-limit",
    "1024",
    "--speed-time",
    "30",
    "--max-time",
    "1500",
    "--retry",
    "3",
    "--retry-delay",
    "5",
    "--retry-connrefused",
]
LATEST_RE = re.compile(r"^v?[0-9]+\.[0-9]+\.[0-9]+(-[a-zA-Z0-9.]+)?$")
USAGE_LINES = (
    "  usage: test-install-methods.sh [--dry-run] [--method <method>] [--version <ver>]",
    "                                 [--platform linux|mac|win] [--arch x64|arm64]",
    "                                 [--local-artifacts <dir>]",
    f"  valid --method values: {', '.join(VALID_METHODS)}",
)


class UsageError(Exception):
    """A bad invocation. Exit 2, with the usage lines."""


@dataclasses.dataclass
class Config:
    dry_run: bool = False
    method: str = "all"
    version: str = "latest"
    platform: str = ""
    arch: str = ""
    local_artifacts: str = ""
    repo_channel: str = ""
    releases: str = DEFAULT_RELEASES
    docker_tag: str = "latest"
    test_dir: pathlib.Path = dataclasses.field(default_factory=pathlib.Path)

    @property
    def suffix(self) -> str:
        return f"/{self.repo_channel}" if self.repo_channel else ""


def parse(argv: list[str]) -> Config:
    cfg = Config()
    value_flags = {
        "--method": "method",
        "--version": "version",
        "--platform": "platform",
        "--arch": "arch",
        "--local-artifacts": "local_artifacts",
    }
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--dry-run":
            cfg.dry_run = True
            i += 1
        elif arg in value_flags:
            if i + 1 >= len(argv) or not argv[i + 1]:
                raise UsageError(f"{arg} requires a value")
            setattr(cfg, value_flags[arg], argv[i + 1])
            i += 2
        else:
            raise UsageError(f"unknown argument: '{arg}'")
    if cfg.method not in VALID_METHODS:
        raise UsageError(f"unknown --method '{cfg.method}'")
    if not cfg.platform:
        cfg.platform = {"linux": "linux", "macos": "mac", "windows": "win"}.get(
            common.detect_os(), "linux"
        )
    if not cfg.arch:
        cfg.arch = common.detect_arch()
    if cfg.platform not in ("linux", "mac", "win"):
        raise UsageError(f"unknown --platform '{cfg.platform}' (expected linux, mac, or win)")
    if cfg.arch not in ("x64", "arm64"):
        raise UsageError(
            f"unknown --arch '{cfg.arch}' (expected x64 or arm64; detect_arch reports 'unknown' on an unsupported machine)"
        )
    cfg.repo_channel = os.environ.get("REPO_CHANNEL") or ""
    cfg.releases = os.environ.get("RELEASES_BASE_URL") or DEFAULT_RELEASES
    cfg.docker_tag = os.environ.get("DOCKER_TAG") or "latest"
    return cfg


def verify_version(output: str, expected: str) -> bool:
    """There is ALWAYS a version, or this fails. Exact token match; never a silent pass.

    Empty expectation and empty output both fail loudly (`grep -q ""` matches everything). `latest` accepts any well-formed semver on one line. A concrete version must appear as a whole token: not flanked by another digit or dot, so 1.2.1 does not match 1.2.16 or 11.2.1.
    """
    if not expected:
        log.error(
            "verify_version: expected version is EMPTY, so refusing to report a pass. The caller failed to resolve a version."
        )
        return False
    if not output:
        log.error(
            f"verify_version: no version output captured (expected '{expected}'), so refusing to report a pass. The binary did not run, or its output was discarded."
        )
        return False
    lines = output.splitlines()
    if expected == "latest":
        return any(LATEST_RE.match(line) for line in lines)
    want = re.escape(expected.removeprefix("v"))
    token = re.compile(rf"(^|[^0-9.])v?{want}([^0-9.]|$)")
    return any(token.search(line) for line in lines)


def version_fence_probe(command: str) -> str:
    return f'echo "{FENCE_BEGIN}"; {command} 2>&1; echo "{FENCE_END}"'


def extract_fenced_version(transcript: str) -> str:
    """The region between the fence markers, markers removed. Unanchored, because install output without a trailing newline leaves the begin marker glued to another line."""
    inside = False
    kept: list[str] = []
    for line in transcript.splitlines():
        if FENCE_BEGIN in line:
            inside = True
        if inside and FENCE_BEGIN not in line and FENCE_END not in line:
            kept.append(line)
        if FENCE_END in line:
            inside = False
    return "\n".join(kept)


def render(template: str, cfg: Config, probe: str, **extra: str) -> str:
    values = {
        "@RELEASES@": cfg.releases,
        "@SUFFIX@": cfg.suffix,
        "@CHANNEL@": cfg.repo_channel,
        "@PKG@": PKG_NAME,
        "@TAP@": HOMEBREW_TAP,
        "@PROBE@": version_fence_probe(probe),
        **extra,
    }
    for key, value in values.items():
        template = template.replace(key, value)
    return template


class Runner:
    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self.passed = 0
        self.failed = 0
        self.skipped = 0
        self.failed_tests: list[str] = []

    # ---- bookkeeping ---------------------------------------------------------------------------------------------

    def run_test(self, name: str, fn: typing.Callable[[], int]) -> None:
        log.step(f"TEST: {name}")
        try:
            code = fn()
        except Exception as exc:  # noqa: BLE001 - a test that raises failed; it must not end the run
            log.error(f"{type(exc).__name__}: {exc}")
            code = 1
        if code == 0 and self.cfg.dry_run:
            # A dry run downloads nothing, installs nothing and compares no version: a SKIP, never a PASS.
            log.warn(f"SKIP: {name} - dry-run, nothing was verified")
            self.skipped += 1
        elif code == 0:
            log.info(f"PASS: {name}")
            self.passed += 1
        elif code == SKIPPED:
            log.warn(f"SKIP: {name} - prerequisites not met")
            self.skipped += 1
        else:
            log.error(f"FAIL: {name}")
            self.failed += 1
            self.failed_tests.append(name)

    def skip_test(self, name: str, reason: str) -> None:
        log.warn(f"SKIP: {name} - {reason}")
        self.skipped += 1

    # ---- helpers -------------------------------------------------------------------------------------------------

    def curl(
        self, url: str, *flags: str, output: str | None = None, quiet: bool = False
    ) -> subprocess.CompletedProcess[str]:
        """Run curl. Its own error line reaches stderr (the twin's `-sS`) unless `quiet`, which is the twin's `2>/dev/null`."""
        argv = ["curl", *flags, url]
        if output:
            argv += ["-o", output]
        try:
            return subprocess.run(
                argv,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL if quiet else None,
                text=True,
                check=False,
                stdin=subprocess.DEVNULL,
            )
        except OSError as exc:
            log.error(f"curl: {exc.strerror or exc}")
            return subprocess.CompletedProcess(argv, 127, "", "")

    def fetch(self, url: str, quiet: bool = False) -> str | None:
        done = self.curl(url, "-fsSL", quiet=quiet)
        return done.stdout if done.returncode == 0 else None

    def head_ok(self, url: str) -> bool:
        return self.curl(url, "-fsSL", "-o", "/dev/null", "--head", quiet=True).returncode == 0

    def run_binary(
        self,
        binary: pathlib.Path,
        *args: str,
        env: dict[str, str] | None = None,
        merge_stderr: bool = True,
    ) -> str:
        """Output of the binary, `|| true` style: a failing binary yields its output (or nothing), never an exception. stderr is folded in (`2>&1`) unless `merge_stderr` is false (`2>/dev/null`)."""
        try:
            done = subprocess.run(
                [str(binary), *args],
                capture_output=True,
                text=True,
                check=False,
                stdin=subprocess.DEVNULL,
                env=env,
            )
        except OSError as exc:
            return str(exc)
        return ((done.stdout + done.stderr) if merge_stderr else done.stdout).rstrip("\n")

    def powershell(self, command: str) -> str:
        done = subprocess.run(
            ["powershell.exe", "-Command", command],
            capture_output=True,
            text=True,
            check=False,
            stdin=subprocess.DEVNULL,
        )
        return (done.stdout + done.stderr).rstrip("\n")

    def container(self, label: str, argv: list[str]) -> int:
        """`run_container_version_test`: the script ends in a fenced probe; the fenced output must be exactly the version under test."""
        try:
            done = subprocess.run(
                argv,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                check=False,
                stdin=subprocess.DEVNULL,
                timeout=CONTAINER_TIMEOUT,
            )
        except subprocess.TimeoutExpired as exc:
            log.error(f"{label}: container did not finish within {CONTAINER_TIMEOUT}s")
            sys.stderr.write(str(exc.output or ""))
            return 1
        except OSError as exc:
            log.error(f"{label}: {exc}")
            return 1
        raw = done.stdout.rstrip("\n")
        if done.returncode != 0:
            log.error(
                f"{label}: container exited {done.returncode} before a version could be verified"
            )
            print(raw, file=sys.stderr)
            return 1
        reported = extract_fenced_version(raw)
        if not verify_version(reported, self.cfg.version):
            log.error(
                f"{label}: version mismatch - expected '{self.cfg.version}', got '{reported}'"
            )
            print(raw, file=sys.stderr)
            return 1
        log.info(f"  {label}: version verified ({reported})")
        return 0

    def get_binary_url(self, platform: str, arch: str) -> str | None:
        filename = {
            "linux": f"rdc-linux-{arch}",
            "mac": f"rdc-mac-{arch}",
            "win": f"rdc-win-{arch}.exe",
        }[platform]
        if self.cfg.repo_channel:
            return f"{self.cfg.releases}/cli/{self.cfg.repo_channel}/{filename}"
        log.error("get_binary_url called with an empty REPO_CHANNEL.")
        log.error(
            "  There is no channel-less path in R2; callers must skip when the channel is empty."
        )
        return None

    def skip_without_channel(self, what: str) -> bool:
        if self.cfg.repo_channel:
            return False
        log.warn(f"No REPO_CHANNEL: skipping {what} (expected on schedule and workflow_dispatch).")
        return True

    # ---- tests ---------------------------------------------------------------------------------------------------

    def test_binary_download(self, platform: str, arch: str) -> int:
        cfg = self.cfg
        binary_name = "rdc.exe" if platform == "win" else "rdc"
        filename = {
            "linux": f"rdc-linux-{arch}",
            "mac": f"rdc-mac-{arch}",
            "win": f"rdc-win-{arch}.exe",
        }[platform]

        if cfg.local_artifacts:
            local = pathlib.Path(cfg.local_artifacts) / "cli" / filename
            if not local.is_file():
                log.warn(f"Local binary not found: {local}")
                return SKIPPED
            download_dir = cfg.test_dir / f"binary-{platform}-{arch}"
            download_dir.mkdir(parents=True, exist_ok=True)
            target = download_dir / binary_name
            shutil.copy(local, target)
            target.chmod(target.stat().st_mode | 0o111)
            if platform == "win":
                if not shutil.which("powershell.exe"):
                    log.warn(
                        "Local Windows binary copied but no powershell.exe to run it; SKIPPING the version assertion rather than reporting a pass."
                    )
                    return SKIPPED
                output = self.powershell(f".\\{download_dir}\\{binary_name} --version")
            else:
                output = self.run_binary(target, "--version")
            if not verify_version(output, cfg.version):
                log.error(f"Version mismatch: expected '{cfg.version}', got '{output}'")
                return 1
            return 0

        if not cfg.repo_channel:
            log.warn(
                "No REPO_CHANNEL: this run staged no artifacts, so there is no binary to validate."
            )
            log.warn(
                f"  Skipping Binary Download ({platform} {arch}). Expected on schedule and workflow_dispatch."
            )
            return SKIPPED

        url = self.get_binary_url(platform, arch)
        if url is None:
            return 1
        if platform == "win":
            if cfg.dry_run:
                log.info("[DRY-RUN] Would download and test Windows binary")
                return 0
            if not shutil.which("powershell.exe"):
                return SKIPPED
            if self.curl(url, *DL_FLAGS, output=binary_name).returncode != 0:
                log.error(f"Failed to download binary from {url}")
                return 1
            output = self.powershell(f".\\{binary_name} --version")
        else:
            if cfg.dry_run:
                log.info(
                    f"[DRY-RUN] Would run: curl -fsSL '{url}' -o '{binary_name}' && chmod +x '{binary_name}' && ./'{binary_name}' --version"
                )
                return 0
            download_dir = cfg.test_dir / f"binary-{platform}-{arch}"
            download_dir.mkdir(parents=True, exist_ok=True)
            target = download_dir / binary_name
            if self.curl(url, *DL_FLAGS, output=str(target)).returncode != 0:
                log.error(f"Failed to download binary from {url}")
                return 1
            target.chmod(target.stat().st_mode | 0o111)
            output = self.run_binary(target, "--version")
        if not verify_version(output, cfg.version):
            log.error(f"Version mismatch: expected '{cfg.version}', got '{output}'")
            return 1
        return 0

    def test_update_check(self) -> int:
        cfg = self.cfg
        if not cfg.repo_channel:
            log.warn("No REPO_CHANNEL: there is no channel manifest to check.")
            log.warn("  Skipping Update Check. Expected on schedule and workflow_dispatch.")
            return SKIPPED
        manifest_url = f"{cfg.releases}/cli/{cfg.repo_channel}/manifest.json"
        if cfg.dry_run:
            log.info(f"[DRY-RUN] Would fetch manifest from: {manifest_url}")
            return 0
        text = self.fetch(manifest_url)
        if text is None:
            log.error(f"Failed to fetch manifest from {manifest_url}")
            return 1
        manifest = _json(text)
        version = manifest.get("version") if isinstance(manifest, dict) else None
        binaries = manifest.get("binaries") if isinstance(manifest, dict) else None
        # Both fields must be present AND non-empty: `{}` is truthy to `jq -e`, so an empty binaries map used to pass.
        if not (isinstance(version, str) and version and isinstance(binaries, dict) and binaries):
            log.error(f"Invalid manifest structure at {manifest_url}:")
            log.error("  .version must be a non-empty string and .binaries a non-empty object.")
            print("\n".join(text.splitlines()[:40]), file=sys.stderr)
            return 1
        if not verify_version(version, cfg.version):
            log.error(
                f"Manifest version mismatch at {manifest_url}: expected '{cfg.version}', got '{version}'"
            )
            return 1
        log.info(f"  Manifest version verified: {version}")
        linux = binaries.get("linux-x64")
        binary_url = linux.get("url") if isinstance(linux, dict) else None
        if not binary_url:
            log.error(f'Manifest at {manifest_url} has no .binaries["linux-x64"].url')
            return 1
        if not self.head_ok(str(binary_url)):
            log.error(f"Binary URL not reachable: {binary_url}")
            return 1
        log.info(f"  Binary URL reachable: {binary_url}")
        return 0

    def test_promotion_config_fixup(self) -> int:
        cfg = self.cfg
        if cfg.dry_run:
            log.info("[DRY-RUN] Would validate promotion config fixup")
            return 0
        if self.skip_without_channel("promotion check"):
            return SKIPPED
        repo_url = f"{cfg.releases}/rpm{cfg.suffix}/rediacc.repo"
        content = self.fetch(repo_url, quiet=True)
        if content is None:
            log.error(f"Failed to fetch .repo from {repo_url}")
            return 1
        if cfg.repo_channel not in content:
            log.error(f".repo file does not contain channel '{cfg.repo_channel}'")
            return 1
        log.info(f"  .repo contains channel: {cfg.repo_channel}")
        promoted = content.replace(f"/{cfg.repo_channel}/", "/stable/")
        if "/stable/" not in promoted:
            log.error("Promotion sed-fix failed: /stable/ not found")
            return 1
        if f"/{cfg.repo_channel}/" in promoted:
            log.error(f"Promotion sed-fix incomplete: /{cfg.repo_channel}/ still present")
            return 1
        log.info(f"  Promotion sed-fix validated: {cfg.repo_channel} -> stable")
        return 0

    def test_channel_verify(self) -> int:
        cfg = self.cfg
        if cfg.dry_run:
            log.info("[DRY-RUN] Would verify channel configuration")
            return 0
        if self.skip_without_channel("channel verification"):
            return SKIPPED
        url = self.get_binary_url("linux", "x64")
        if url is None:
            return 1
        binary = cfg.test_dir / "rdc-verify"
        if self.curl(url, *DL_FLAGS, output=str(binary)).returncode != 0:
            log.error(f"Failed to download binary from {url}")
            return 1
        binary.chmod(binary.stat().st_mode | 0o111)
        output = self.run_binary(binary, "--version")
        if not verify_version(output, cfg.version):
            log.error(f"Version mismatch: expected '{cfg.version}', got '{output}'")
            return 1
        log.info(f"  Binary version: {output}")
        doctor_text = self.run_binary(
            binary,
            "doctor",
            "-o",
            "json",
            env={**os.environ, "REDIACC_UPDATE_CHANNEL": cfg.repo_channel},
            merge_stderr=False,
        )
        doctor = _json(doctor_text)
        if not doctor_text or not isinstance(doctor, dict):
            log.error("Failed to get doctor output")
            return 1
        channel = _environment_value(doctor, "Update channel")
        if channel != cfg.repo_channel:
            log.error(f"Channel mismatch: expected '{cfg.repo_channel}', got '{channel or ''}'")
            return 1
        log.info(f"  Channel verified: {channel}")
        server = _environment_value(doctor, "Account server")
        if not server:
            log.error("Account server not found in doctor output")
            return 1
        log.info(f"  Account server: {server}")
        manifest_url = f"{cfg.releases}/cli/{cfg.repo_channel}/manifest.json"
        if not self.head_ok(manifest_url):
            log.error(f"Manifest not reachable: {manifest_url}")
            return 1
        log.info(f"  Manifest reachable: {manifest_url}")
        return 0

    def test_docker_pull_and_run(self) -> int:
        cfg = self.cfg
        image = f"{DOCKER_IMAGE}:{cfg.docker_tag}"
        if cfg.dry_run:
            log.info(
                f"[DRY-RUN] Would run: docker pull '{image}' && docker run --rm '{image}' --version"
            )
            return 0
        pulled = subprocess.run(["docker", "pull", image], check=False, stdin=subprocess.DEVNULL)
        if pulled.returncode != 0:
            log.error(f"docker pull {image} failed (exit {pulled.returncode})")
            return 1
        done = subprocess.run(
            ["docker", "run", "--rm", image, "--version"],
            capture_output=True,
            text=True,
            check=False,
            stdin=subprocess.DEVNULL,
        )
        output = (done.stdout + done.stderr).rstrip("\n")
        if not verify_version(output, cfg.version):
            log.error(f"Version mismatch: expected '{cfg.version}', got '{output}'")
            return 1
        return 0

    def container_method(
        self,
        kind: str,
        prefix: str,
        label: str,
        template: str,
        probe: str,
        image: str,
        shell: str,
        *,
        docker_args: list[str] | None = None,
    ) -> int:
        cfg = self.cfg
        if cfg.dry_run:
            log.info(f"[DRY-RUN] Would test {kind} install on {label}")
            return 0
        if self.skip_without_channel(f"{kind} install"):
            return SKIPPED
        script = render(template, cfg, probe)
        return self.container(
            f"{prefix} ({label})",
            ["docker", "run", "--rm", *(docker_args or []), image, shell, "-c", script],
        )

    def test_apt_install(self, distro: str, label: str) -> int:
        return self.container_method(
            "APT", "APT", label, scripts.APT, scripts.APT_PROBE, distro, "bash"
        )

    def test_dnf_install(self, distro: str, label: str) -> int:
        return self.container_method(
            "DNF", "DNF", label, scripts.DNF, scripts.DNF_PROBE, distro, "bash"
        )

    def test_apk_install(self, distro: str, label: str) -> int:
        return self.container_method(
            "APK", "APK", label, scripts.APK, scripts.APK_PROBE, distro, "sh"
        )

    def test_pacman_install(self, distro: str, label: str) -> int:
        return self.container_method(
            "Pacman", "Pacman", label, scripts.PACMAN, scripts.PACMAN_PROBE, distro, "bash"
        )

    def test_npm_install(self, distro: str, label: str) -> int:
        cfg = self.cfg
        if cfg.dry_run:
            log.info(f"[DRY-RUN] Would test npm install on {label}")
            return 0
        if self.skip_without_channel("npm install"):
            return SKIPPED
        # The CLI's dependencies resolve live inside the container (a global install has no lockfile), so --before holds them to the release-age window; the cutoff comes from the checkout's one implementation.
        try:
            before = release_age.npm_before()
        except Exception as exc:  # noqa: BLE001
            log.error(
                f"Could not compute the npm --before cutoff (rediacc_ci.core.release_age npm-before): {exc}"
            )
            return 1
        script = render(scripts.NPM, cfg, scripts.NPM_PROBE, **{"@NPM_BEFORE@": before})
        return self.container(
            f"npm ({label})", ["docker", "run", "--rm", distro, "bash", "-c", script]
        )

    def test_homebrew_install(self) -> int:
        cfg = self.cfg
        if cfg.dry_run:
            log.info(
                f"[DRY-RUN] Would run: brew tap {WK_HOMEBREW_TAP} && brew install {HOMEBREW_TAP}"
            )
            return 0
        if not shutil.which("brew"):
            log.error("Homebrew not available")
            return 1
        for argv in (["brew", "tap", WK_HOMEBREW_TAP], ["brew", "install", HOMEBREW_TAP]):
            if subprocess.run(argv, check=False, stdin=subprocess.DEVNULL).returncode != 0:
                log.error(f"{' '.join(argv)} failed")
                return 1
        output = self.run_binary(
            pathlib.Path(shutil.which(PKG_BINARY_NAME) or PKG_BINARY_NAME), "--version"
        )
        if not verify_version(output, cfg.version):
            log.error(f"Version mismatch: expected '{cfg.version}', got '{output}'")
            return 1
        return 0

    def test_homebrew_linuxbrew(self) -> int:
        cfg = self.cfg
        if cfg.dry_run:
            log.info("[DRY-RUN] Would test Homebrew install in homebrew/brew:latest container")
            return 0
        script = render(scripts.HOMEBREW, cfg, scripts.HOMEBREW_PROBE)
        return self.container(
            "Homebrew (Linuxbrew)",
            ["docker", "run", "--rm", "homebrew/brew:latest", "bash", "-c", script],
        )

    def test_quick_install(self, distro: str, label: str) -> int:
        cfg = self.cfg
        return self.container_method(
            "quick",
            "Quick Install",
            label,
            scripts.QUICK,
            scripts.QUICK_PROBE,
            distro,
            "bash",
            docker_args=[
                "-e",
                f"REDIACC_RELEASES_URL={cfg.releases}",
                "-e",
                f"REDIACC_CHANNEL={cfg.repo_channel}",
            ],
        )


def _json(text: str) -> object:
    try:
        return json.loads(text)
    except ValueError:
        return None


def _environment_value(doctor: dict, name: str) -> str | None:
    for entry in doctor.get("Environment") or []:
        if isinstance(entry, dict) and entry.get("name") == name:
            value = entry.get("value")
            return None if value is None else str(value)
    return None


def resolve_latest(cfg: Config, runner: Runner) -> bool:
    """`--version latest` becomes the channel's `latest.json` version. False when it was asked for and could not be resolved."""
    if cfg.version != "latest" or cfg.local_artifacts or cfg.dry_run:
        return True
    text = runner.fetch(f"{cfg.releases}/cli/{cfg.repo_channel or 'edge'}/latest.json", quiet=True)
    data = _json(text) if text else None
    resolved = data.get("version") if isinstance(data, dict) else None
    if not resolved or not isinstance(resolved, str):
        log.error(
            f"--version latest could not be resolved from {cfg.releases}/cli/{cfg.repo_channel or 'edge'}/latest.json."
        )
        log.error(
            "  'latest' accepts ANY well-formed version, so an unresolved one would verify nothing. Pass --version <ver>."
        )
        return False
    cfg.version = resolved
    return True


def main(argv: list[str]) -> int:
    # Children inherit stdout: line buffering keeps this process's lines in order with theirs when stdout is a pipe.
    if (reconfigure := getattr(sys.stdout, "reconfigure", None)) is not None:
        reconfigure(line_buffering=True)
    try:
        cfg = parse(argv)
    except UsageError as exc:
        log.error(str(exc))
        for line in USAGE_LINES:
            log.error(line)
        return 2
    test_dir = pathlib.Path(
        tempfile.mkdtemp(
            prefix=f"rediacc-sh-{os.getpid()}-install-methods-",
            dir=os.environ.get("TMPDIR") or "/tmp",
        )
    )
    cfg.test_dir = test_dir
    runner = Runner(cfg)
    try:
        if not resolve_latest(cfg, runner):
            return 1
        return run(cfg, runner)
    finally:
        with contextlib.suppress(OSError):
            shutil.rmtree(test_dir, ignore_errors=True)


def run(cfg: Config, r: Runner) -> int:
    log.step("Installation Method Tests")
    log.info(f"  Method: {cfg.method}")
    log.info(f"  Version: {cfg.version}")
    log.info(f"  Platform: {cfg.platform}")
    log.info(f"  Arch: {cfg.arch}")
    log.info(f"  Dry-run: {str(cfg.dry_run).lower()}")
    if cfg.local_artifacts:
        log.info(f"  Local artifacts: {cfg.local_artifacts}")
    print()
    if not cfg.dry_run and cfg.method in ("docker", "apt", "dnf", "apk", "pacman", "quick", "all"):
        try:
            common.require_cmd("docker")
        except common.RefusalError as refusal:
            refusal.report()
            return refusal.code

    def wants(*names: str) -> bool:
        return cfg.method in (*names, "all")

    def section(title: str) -> None:
        log.step(title)

    def done_section() -> None:
        print()

    if wants("binary"):
        section("Binary Download Tests")
        label = {"linux": "Linux", "mac": "macOS", "win": "Windows"}[cfg.platform]
        r.run_test(
            f"Binary Download ({label} {cfg.arch})",
            lambda: r.test_binary_download(cfg.platform, cfg.arch),
        )
        done_section()
    if wants("verify"):
        section("Channel Verification Tests")
        if cfg.platform == "linux" and cfg.repo_channel:
            r.run_test(f"Channel Verify ({cfg.repo_channel})", r.test_channel_verify)
        elif cfg.platform != "linux":
            r.skip_test(
                "Channel Verify",
                f"channel verification runs on Linux only (platform: {cfg.platform})",
            )
        else:
            r.skip_test("Channel Verify", "no REPO_CHANNEL: this run staged no artifacts")
        done_section()
    if wants("update"):
        section("Update Check Tests")
        r.run_test("Update Check (manifest)", r.test_update_check)
        done_section()
    if wants("promote"):
        section("Promotion Validation Tests")
        r.run_test("Promotion Config Fixup", r.test_promotion_config_fixup)
        done_section()
    if wants("docker"):
        section("Docker Tests")
        if cfg.platform in ("linux", "mac"):
            r.run_test("Docker Pull and Run", r.test_docker_pull_and_run)
        else:
            r.skip_test("Docker Pull and Run", "Docker tests not supported on Windows runners")
        done_section()

    def family(
        method: str,
        title: str,
        label: str,
        reason: str,
        cases: list[tuple[str, str, str]],
        fn: typing.Callable[[str, str], int],
    ) -> None:
        if not wants(method):
            return
        section(title)
        if cfg.platform == "linux":
            for case_label, image, human in cases:
                r.run_test(f"{label} Install ({case_label})", functools.partial(fn, image, human))
        else:
            r.skip_test(f"{label} Install", reason)
        done_section()

    family(
        "apt",
        "APT Tests",
        "APT",
        "APT tests require Linux with Docker",
        [
            ("Ubuntu 22.04", "ubuntu:22.04", "Ubuntu 22.04"),
            ("Ubuntu 24.04", "ubuntu:24.04", "Ubuntu 24.04"),
            ("Debian 12", "debian:12", "Debian 12"),
        ],
        r.test_apt_install,
    )
    family(
        "dnf",
        "DNF Tests",
        "DNF",
        "DNF tests require Linux with Docker",
        [
            ("Fedora 40", "fedora:40", "Fedora 40"),
            ("Rocky Linux 9", "rockylinux:9", "Rocky Linux 9"),
        ],
        r.test_dnf_install,
    )
    family(
        "apk",
        "APK Tests",
        "APK",
        "APK tests require Linux with Docker",
        [("Alpine 3.20", "alpine:3.20", "Alpine 3.20")],
        r.test_apk_install,
    )
    family(
        "pacman",
        "Pacman Tests",
        "Pacman",
        "Pacman tests require Linux with Docker",
        [("Arch Linux", "archlinux:latest", "Arch Linux")],
        r.test_pacman_install,
    )
    if wants("homebrew"):
        section("Homebrew Tests")
        if cfg.platform == "mac":
            r.run_test("Homebrew Install (macOS)", r.test_homebrew_install)
        elif cfg.platform == "linux":
            if shutil.which("brew"):
                r.run_test("Homebrew Install (Linuxbrew)", r.test_homebrew_install)
            else:
                r.run_test("Homebrew Install (Linuxbrew Docker)", r.test_homebrew_linuxbrew)
        else:
            r.skip_test("Homebrew Install", "Homebrew not available on Windows")
        done_section()
    if wants("npm"):
        section("npm Install Tests")
        if cfg.platform == "linux":
            r.run_test("npm Install (Node 24)", lambda: r.test_npm_install("node:24", "Node 24"))
        else:
            r.skip_test("npm Install", "npm tests require Linux with Docker")
        done_section()
    family(
        "quick",
        "Quick Install Tests",
        "Quick",
        "Quick install tests require Linux with Docker",
        [
            ("Ubuntu 22.04", "ubuntu:22.04", "Ubuntu 22.04"),
            ("Ubuntu 24.04", "ubuntu:24.04", "Ubuntu 24.04"),
            ("Debian 12", "debian:12", "Debian 12"),
        ],
        r.test_quick_install,
    )

    print()
    total = r.passed + r.failed + r.skipped
    log.step(f"Results: {r.passed} passed, {r.failed} failed, {r.skipped} skipped (total {total})")
    if r.failed_tests:
        log.error("Failed tests:")
        for name in r.failed_tests:
            log.error(f"  - {name}")
    # Success is "something was accounted for". An all-skipped run stays a success (each skip is printed and counted); a zero-total run says nothing at all and must never pass.
    if total == 0:
        log.error("This run executed ZERO tests, so it verified NOTHING.")
        log.error(
            f"  method='{cfg.method}' platform='{cfg.platform}' arch='{cfg.arch}' channel='{cfg.repo_channel or '<empty>'}'"
        )
        log.error("  No test block matched that combination. Refusing to report success.")
        return 1
    return 0 if r.failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
