#!/usr/bin/env python3
"""Template lifecycle suite for `packages/json` (the `test` script): run every Rediaccfile's `up()` and `down()`, watch container health, clean up.

Ported from `packages/json/test-templates.sh` (PLAN-retire-bash-oracles B5, W10).

    python3 .ci/rediacc_ci/catalog/lifecycle.py [OPTIONS]      # --help lists them

NOT RUN BY CI, and that is recorded rather than accidental: see packages/e2e-tests/README.md, "Deliberately not in CI", item 9. Short version: every Rediaccfile calls `renet compose`, which needs a per-repo network id, so this needs a LICENSED rediacc repo on a VM and not merely Docker. On a bare host or a fresh fleet member `up()` fails instantly with "--network-id is required and must be a valid non-zero value".

STDLIB ONLY, AND RUN BY PATH, for the reason `generate.py` gives: the package scripts have no PYTHONPATH.

EQUIVALENCE. The bash needed Docker and a licensed repo to do anything, so the port was driven against a recording `docker` stub and fixture Rediaccfiles, side by side with the bash, for: discovery with every filter, a passing template, a failing `up()`, a failing `down()`, a Rediaccfile that fails to source, a health failure, and the results-file layout. The recorded docker argv, the stderr lines, the exit status and the results JSON (timestamps and durations normalised) agreed except for the deltas below.

DELIBERATE DELTAS FROM THE BASH (Rule T), each with a test in `test_catalog_lifecycle.py` that fails on the bash behaviour:

  * A template that cannot start (directory gone, no Rediaccfile, Rediaccfile fails to source) no longer kills the whole run. The bash recorded the failure and then `return 1`ed from `test_template`, which `set -e` in `main`'s loop turned into an immediate exit: no remaining template ran and no results file was written. The failure is now recorded and the loop continues; the run still exits 1.
  * "No templates found" exits 1 with that message. The bash ran discovery in a process substitution, so its `exit 1` only left the subshell, and the run died a line later on `discovery_output[0]: unbound variable` (after wiping the artifacts directory).
  * A relative `--output` / `RESULTS_FILE` is relative to where the command was run, and the default is the package directory. The bash `cd`ed into template directories and back, and skipped the `cd` back on every early return, so the report could land inside a template directory.
  * The Rediaccfile is sourced in a child shell, not into the test process. Sourcing it into the runner leaked every function and variable one template defined into the next template's run.
  * `docker compose ps --format json` is read in both shapes compose has shipped: one object per line, and a single JSON array. The bash fed the array to `jq .Name`, which failed.
  * `jq` is no longer a dependency.
  * A missing value after an option is a named error rather than `$2: unbound variable`.
  * A timed-out `up()` or `down()` takes its whole process group down, not just the shell, so a half-started compose project does not outlive its timeout.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import shutil
import signal
import subprocess
import sys
import time
from datetime import UTC, datetime
from typing import IO

PACKAGE_DIR = pathlib.Path(__file__).resolve().parents[3] / "packages" / "json"

RED = "\033[0;31m"
GREEN = "\033[0;32m"
BLUE = "\033[0;34m"
YELLOW = "\033[1;33m"
CYAN = "\033[0;36m"
NC = "\033[0m"

TIMEOUT_RC = 124
MISSING_RC = 127
POLL_INTERVAL = 5
NO_HEALTHCHECK_WAIT = 10
COMPOSE_FILES = ("docker-compose.yaml", "docker-compose.yml")
FLAG_OPTIONS = ("--verbose", "--no-cleanup", "--help")
VALUE_OPTIONS = ("--category", "--template", "--skip", "--output")

HELP = """Template Testing Script

Tests all Rediaccfile templates by executing up/down lifecycle

Usage: ./test-templates.sh [OPTIONS]

Options:
  --category <name>     Test only templates in specified category
  --template <path>     Test only specific template (relative to templates/)
  --skip <path>         Skip specific template (can be used multiple times)
  --verbose             Show detailed output
  --no-cleanup          Don't cleanup Docker images (for debugging)
  --output <file>       Output file for JSON results (default: test-results.json)
  --help                Show this help message

Environment Variables:
  TEST_TIMEOUT              Max time per function in seconds (default: 240)
  HEALTH_CHECK_TIMEOUT      Max wait for health checks in seconds (default: 360)
  RESULTS_FILE              Output file for JSON results
  VERBOSE                   Set to 1 for detailed output
  CLEANUP_IMAGES            Set to 0 to skip image cleanup

Examples:
  ./test-templates.sh                           # Test all templates
  ./test-templates.sh --category databases      # Test only database templates
  ./test-templates.sh --template databases/postgresql  # Test specific template
  ./test-templates.sh --skip databases/mssql --verbose # Skip MSSQL, verbose output
"""

# Seams: a test replaces these so a health poll does not take real minutes.
sleep = time.sleep
now = time.time

Sink = IO[bytes] | int | None


class UsageError(Exception):
    """The command line cannot be acted on."""


class NoTemplatesError(Exception):
    """Discovery found nothing that matches the filters."""


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    if not re.fullmatch(r"-?\d+", raw):
        raise UsageError("%s must be a whole number, got %r" % (name, raw))
    return int(raw)


def _duration(seconds: int) -> str:
    return "%dm%ds" % (seconds // 60, seconds % 60) if seconds >= 60 else "%ds" % seconds


def _stamp() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class Suite:
    """One run: configuration, counters, results."""

    def __init__(self, package_dir: pathlib.Path = PACKAGE_DIR) -> None:
        self.package_dir = package_dir
        self.templates_dir = package_dir / "templates"
        self.test_timeout = _int_env("TEST_TIMEOUT", 240)
        self.health_timeout = _int_env("HEALTH_CHECK_TIMEOUT", 360)
        self.verbose = _int_env("VERBOSE", 0) == 1
        self.cleanup_images_enabled = _int_env("CLEANUP_IMAGES", 1) != 0
        self.artifacts_dir = pathlib.Path(
            os.environ.get("ARTIFACTS_DIR") or package_dir / "test-artifacts"
        )
        self.results_file: pathlib.Path = self._resolve_results(os.environ.get("RESULTS_FILE"))
        self.filter_category = ""
        self.filter_templates: list[str] = []
        self.skip_templates: list[str] = []
        self.total = 0
        self.passed = 0
        self.failed = 0
        self.skipped = 0
        self.results: list[str] = []
        self.start_time = int(now())
        self.env = dict(os.environ)

    # ------------------------------------------------------------------ logging

    def _color(self, color: str, msg: str) -> None:
        print("%s%s%s" % (color, msg, NC), file=sys.stderr)

    def log_info(self, msg: str) -> None:
        self._color(BLUE, "[INFO] " + msg)

    def log_success(self, msg: str) -> None:
        self._color(GREEN, "[PASS] " + msg)

    def log_error(self, msg: str) -> None:
        self._color(RED, "[FAIL] " + msg)

    def log_warn(self, msg: str) -> None:
        self._color(YELLOW, "[WARN] " + msg)

    def log_verbose(self, msg: str) -> None:
        if self.verbose:
            self._color(CYAN, "[VERBOSE] " + msg)

    # ------------------------------------------------------------------ options

    def _resolve_results(self, value: str | None) -> pathlib.Path:
        if not value:
            return self.package_dir / "test-results.json"
        path = pathlib.Path(value)
        return path if path.is_absolute() else pathlib.Path.cwd() / path

    def parse_args(self, argv: list[str]) -> bool:
        """Apply the command line. False when the run should stop with success (--help)."""
        i = 0
        while i < len(argv):
            arg = argv[i]
            if arg not in FLAG_OPTIONS + VALUE_OPTIONS:
                self.log_error("Unknown option: %s" % arg)
                print(HELP, end="")
                raise UsageError("unknown option")
            if arg in FLAG_OPTIONS:
                if arg == "--help":
                    print(HELP, end="")
                    return False
                if arg == "--verbose":
                    self.verbose = True
                else:
                    self.cleanup_images_enabled = False
                i += 1
                continue
            if i + 1 >= len(argv):
                raise UsageError("%s requires a value" % arg)
            value = argv[i + 1]
            if arg == "--category":
                self.filter_category = value
            elif arg == "--template":
                self.filter_templates.append(value)
            elif arg == "--skip":
                self.skip_templates.append(value)
            else:
                self.results_file = self._resolve_results(value)
            i += 2
        return True

    # ------------------------------------------------------------------ processes

    def _run(
        self,
        argv: list[str],
        cwd: pathlib.Path | None = None,
        timeout: int | None = None,
        out: Sink = subprocess.DEVNULL,
        err: Sink = subprocess.DEVNULL,
    ) -> int:
        """Run a command with output sent to `out`/`err`. 124 on timeout, 127 when it is missing."""
        try:
            proc = subprocess.Popen(
                argv,
                cwd=cwd,
                env=self.env,
                stdin=subprocess.DEVNULL,
                stdout=out,
                stderr=err,
                start_new_session=True,
            )
        except OSError:
            return MISSING_RC
        try:
            return proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except OSError:
                proc.kill()
            proc.wait()
            return TIMEOUT_RC

    def _capture(self, argv: list[str], cwd: pathlib.Path | None = None) -> str:
        try:
            proc = subprocess.run(
                argv,
                cwd=cwd,
                env=self.env,
                capture_output=True,
                text=True,
                check=False,
                stdin=subprocess.DEVNULL,
            )
        except OSError:
            return ""
        return proc.stdout

    def _docker(self, *args: str, cwd: pathlib.Path | None = None) -> int:
        return self._run(["docker", *args], cwd=cwd)

    # ------------------------------------------------------------------ discovery

    def discover_templates(self) -> tuple[int, list[str]]:
        """(skip count, relative template paths) for every Rediaccfile that survives the filters."""
        self.log_info("Discovering templates in %s" % self.templates_dir)
        found: list[str] = []
        skip_count = 0
        rediaccfiles = sorted(
            (
                p
                for p in self.templates_dir.rglob("Rediaccfile")
                if p.is_file() and not p.is_symlink()
            ),
            key=lambda p: os.fsencode(str(p)),
        )
        for rediaccfile in rediaccfiles:
            relative = rediaccfile.parent.relative_to(self.templates_dir).as_posix()
            if self.filter_category and relative.split("/")[0] != self.filter_category:
                continue
            if self.filter_templates and relative not in self.filter_templates:
                continue
            if relative in self.skip_templates:
                self.log_verbose("Skipping template: %s" % relative)
                skip_count += 1
                continue
            found.append(relative)
        if not found:
            self.log_error("No templates found matching criteria")
            raise NoTemplatesError
        self.log_info("Found %d templates to test" % len(found))
        return skip_count, found

    # ------------------------------------------------------------------ health

    @staticmethod
    def compose_file(template_dir: pathlib.Path) -> pathlib.Path | None:
        for name in COMPOSE_FILES:
            if (template_dir / name).is_file():
                return template_dir / name
        return None

    @staticmethod
    def parse_ps(output: str) -> list[dict]:
        """Containers from `docker compose ps --format json`: one object per line, or one array."""
        containers: list[dict] = []
        for raw in output.splitlines():
            line = raw.strip()
            if not line:
                continue
            try:
                value = json.loads(line)
            except ValueError:
                continue
            if isinstance(value, list):
                containers.extend(v for v in value if isinstance(v, dict))
            elif isinstance(value, dict):
                containers.append(value)
        return containers

    def validate_all_containers(
        self, template_dir: pathlib.Path, check_healthchecks: bool = False, silent: bool = False
    ) -> bool:
        def fail(msg: str) -> None:
            if not silent:
                self.log_error(msg)

        if self.compose_file(template_dir) is None:
            fail("No docker-compose file found")
            return False
        services = self._capture(["docker", "compose", "config", "--services"], cwd=template_dir)
        expected = services.count("\n")
        ps_output = self._capture(["docker", "compose", "ps", "--format", "json"], cwd=template_dir)
        if not ps_output.strip():
            fail("No containers found (expected %d)" % expected)
            return False

        count = running = healthy = 0
        unhealthy: list[str] = []
        for container in self.parse_ps(ps_output):
            count += 1
            name = container.get("Name")
            status = str(container.get("Status"))
            state = container.get("State")
            health = container.get("Health") or ""
            exit_code = container.get("ExitCode") or 0
            if status.startswith("Up"):
                running += 1
                if check_healthchecks:
                    if health == "healthy" or not health:
                        healthy += 1
                    else:
                        unhealthy.append("%s: health=%s" % (name, health))
            elif state == "exited":
                unhealthy.append("%s: exited (code=%s)" % (name, exit_code))
            elif state == "restarting":
                unhealthy.append("%s: restarting" % name)
            else:
                unhealthy.append("%s: %s" % (name, status))

        if count < expected:
            fail(
                "Missing containers: found %d, expected %d (missing %d)"
                % (count, expected, expected - count)
            )
            return False
        if unhealthy:
            if not silent:
                self.log_error("Unhealthy containers detected:")
                for issue in unhealthy:
                    self.log_error("  - %s" % issue)
            return False
        if check_healthchecks:
            if healthy == expected:
                if not silent:
                    self.log_verbose("All %d container(s) are healthy" % healthy)
                return True
            fail("Only %d/%d container(s) are healthy" % (healthy, expected))
            return False
        if running == expected:
            if not silent:
                self.log_verbose("All %d container(s) are running" % running)
            return True
        fail("Only %d/%d container(s) are running" % (running, expected))
        return False

    def check_health(self, template_dir: pathlib.Path) -> bool:
        self.log_verbose("Checking container health in %s" % template_dir)
        compose = self.compose_file(template_dir)
        has_healthcheck = False
        if compose is not None and "healthcheck:" in compose.read_text(
            encoding="utf-8", errors="replace"
        ):
            has_healthcheck = True
            self.log_verbose("Health checks defined in compose file")
        if has_healthcheck:
            timeout = self.health_timeout
            self.log_verbose("Waiting for all containers to be healthy (timeout: %ds)" % timeout)
            elapsed = 0
            while elapsed < timeout:
                if self.validate_all_containers(template_dir, True, True):
                    self.log_verbose("All containers healthy after %ds" % elapsed)
                    return True
                sleep(POLL_INTERVAL)
                elapsed += POLL_INTERVAL
                if elapsed % 30 == 0:
                    self.log_verbose("Waiting for health checks... %ds/%ds" % (elapsed, timeout))
            self.log_error("Health check timeout after %ds" % timeout)
            self.validate_all_containers(template_dir, True, False)
            return False
        self.log_verbose("No health checks defined, verifying all containers are running")
        sleep(NO_HEALTHCHECK_WAIT)
        if self.validate_all_containers(template_dir, False, False):
            return True
        self.log_error("Container validation failed")
        return False

    # ------------------------------------------------------------------ cleanup

    def cleanup_images(self, template_dir: pathlib.Path) -> None:
        if not self.cleanup_images_enabled:
            self.log_verbose("Skipping image cleanup (--no-cleanup)")
            return
        self.log_verbose("Cleaning up Docker images for %s" % template_dir)
        compose = self.compose_file(template_dir)
        if compose is None:
            self.log_verbose("No compose file found, skipping image cleanup")
            return
        images = []
        for line in compose.read_text(encoding="utf-8", errors="replace").splitlines():
            if not re.match(r"\s*image:", line):
                continue
            fields = line.split()
            if len(fields) < 2:
                continue
            image = re.sub(r"\$\{[^}]*\}", "", fields[1]).replace('"', "").replace("'", "").strip()
            if image and "$" not in image:
                images.append(image)
        for image in images:
            self.log_verbose("Removing image: %s" % image)
            self._docker("rmi", "-f", image)

    def cleanup_directories(self, template_dir: pathlib.Path) -> None:
        self.log_verbose("Cleaning up directories in %s" % template_dir)
        data = template_dir / "data"
        if data.is_dir() and not data.is_symlink():
            shutil.rmtree(data, ignore_errors=True)
        elif data.exists() or data.is_symlink():
            data.unlink(missing_ok=True)
        for child in template_dir.iterdir():
            if child.name.startswith("data") and child.is_dir() and not child.is_symlink():
                shutil.rmtree(child, ignore_errors=True)

    def cleanup_volumes(self) -> None:
        self.log_verbose("Pruning Docker volumes")
        self._docker("volume", "prune", "-f")

    # ------------------------------------------------------------------ diagnostics

    def initialize_artifacts(self) -> None:
        shutil.rmtree(self.artifacts_dir, ignore_errors=True)
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        (self.artifacts_dir / ".keep").touch()

    def collect_template_artifacts(
        self, template_path: str, template_dir: pathlib.Path, stage: str = "unknown"
    ) -> None:
        artifact_dir = self.artifacts_dir / template_path.replace("/", "__")
        artifact_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        stage_dir = artifact_dir / ("%s_%s" % (stamp, stage))
        stage_dir.mkdir(parents=True, exist_ok=True)
        self.log_warn(
            "Collecting diagnostics for %s (stage: %s) -> %s" % (template_path, stage, stage_dir)
        )
        (stage_dir / "metadata.txt").write_text(
            "template_path=%s\nstage=%s\ncaptured_at=%s\n" % (template_path, stage, _stamp()),
            encoding="utf-8",
        )
        for name in ("Rediaccfile", *COMPOSE_FILES):
            if (template_dir / name).is_file():
                shutil.copy2(template_dir / name, artifact_dir / name)
        if not template_dir.is_dir():
            return

        def to_file(name: str, *args: str) -> None:
            with (stage_dir / name).open("wb") as handle:
                self._run(["docker", *args], cwd=template_dir, out=handle, err=subprocess.STDOUT)

        to_file("docker-compose.config", "compose", "config")
        to_file("docker-compose.ps.txt", "compose", "ps")
        to_file("docker-compose.ps.json", "compose", "ps", "--format", "json")
        to_file("docker-compose.logs", "compose", "logs", "--no-color")
        containers = self._capture(["docker", "compose", "ps", "-q"], cwd=template_dir).split()
        if containers:
            to_file("docker-inspect.json", "inspect", *containers)
            for container in containers:
                with (stage_dir / ("%s.log" % container)).open("wb") as handle:
                    self._run(["docker", "logs", container], out=handle, err=subprocess.STDOUT)

    # ------------------------------------------------------------------ one template

    def _record(self, result: dict) -> None:
        self.results.append(json.dumps(result, separators=(",", ":"), ensure_ascii=False))

    def _early_failure(self, result: dict, error: str) -> None:
        result.update({"overall": "failed", "duration": "0s", "error": error})
        self._record(result)
        self.failed += 1

    def _stage(self, result: dict, func: str, template_dir: pathlib.Path) -> bool:
        """Run `up` or `down` through a child shell with a timeout. True when it passed."""
        start = int(now())
        rc = self._run(
            ["bash", "-c", "source ./Rediaccfile && %s" % func],
            cwd=template_dir,
            timeout=self.test_timeout,
        )
        duration = "%ds" % (int(now()) - start)
        if rc == 0:
            self.log_verbose("%s() passed (%s)" % (func, duration))
            result[func] = {"status": "passed", "duration": duration}
            return True
        if rc == TIMEOUT_RC:
            error = "%s function timed out after %ds" % (func, self.test_timeout)
            self.log_error("%s() timed out" % func)
        else:
            error = "%s function failed" % func
            self.log_error("%s() failed with exit code %d" % (func, rc))
        result[func] = {"status": "failed", "duration": duration, "error": error}
        return False

    def test_template(self, template_path: str) -> None:
        template_dir = self.templates_dir / template_path
        self.log_info("Testing template: %s" % template_path)
        result: dict = {"name": template_path, "category": os.path.dirname(template_path) or "."}
        test_start = int(now())
        overall = "passed"
        error_msg = ""
        first_failure = ""

        if not template_dir.is_dir():
            self.log_error("Template directory not found: %s" % template_dir)
            self._early_failure(result, "Directory not found")
            return
        if not (template_dir / "Rediaccfile").is_file():
            self.log_error("Rediaccfile not found in %s" % template_dir)
            self._early_failure(result, "Rediaccfile not found")
            return
        self.log_verbose("Sourcing Rediaccfile")
        source_rc = self._run(
            ["bash", "-c", "source ./Rediaccfile"], cwd=template_dir, timeout=self.test_timeout
        )
        if source_rc != 0:
            self.log_error("Failed to source Rediaccfile")
            self._early_failure(result, "Failed to source Rediaccfile")
            return

        original_network = os.environ.get("REPOSITORY_NETWORK_MODE", "")
        auto_network = ""
        self.log_verbose("Running up()")
        if not original_network:
            auto_network = "rediacc_" + re.sub(r"[^a-z0-9]", "_", template_path.lower())
            self.log_verbose("Auto-configuring REPOSITORY_NETWORK_MODE=%s" % auto_network)
            if self._docker("network", "inspect", auto_network) != 0:
                self._docker("network", "create", auto_network)
            self.env["REPOSITORY_NETWORK_MODE"] = auto_network

        if not self._stage(result, "up", template_dir):
            overall = "failed"
            error_msg = "up() failed"
            first_failure = "up"
            self.collect_template_artifacts(template_path, template_dir, "up")

        # Health-check ONLY when up() passed: there is nothing to be healthy otherwise, and the check can only sit until HEALTH_CHECK_TIMEOUT and then blame the wrong stage. Measured 2026-08-14 on caching/redis: up() failed in 0s, the run took 374s, and the reported cause was "Health check failed". Carrying on to the NEXT template is the run's job, not probing a stack that never came up.
        if overall == "passed":
            health_start = int(now())
            self.log_verbose("Checking health")
            healthy = self.check_health(template_dir)
            duration = "%ds" % (int(now()) - health_start)
            if healthy:
                self.log_verbose("Health check passed (%s)" % duration)
                result["health"] = {"status": "passed", "duration": duration}
            else:
                self.log_error("Health check failed")
                result["health"] = {
                    "status": "failed",
                    "duration": duration,
                    "error": "Health check timeout or containers not healthy",
                }
                overall = "failed"
                error_msg = error_msg or "Health check failed"
                first_failure = first_failure or "health"
                self.collect_template_artifacts(template_path, template_dir, "health")

        self.log_verbose("Running down()")
        if not self._stage(result, "down", template_dir):
            overall = "failed"
            error_msg = error_msg or "down() failed"
            first_failure = first_failure or "down"
            self.collect_template_artifacts(template_path, template_dir, "down")

        cleanup_start = int(now())
        self.log_verbose("Cleaning up")
        self.cleanup_images(template_dir)
        self.cleanup_directories(template_dir)
        self.cleanup_volumes()
        if auto_network:
            self.log_verbose("Removing auto-configured network: %s" % auto_network)
            self._docker("network", "rm", auto_network)
            self.env.pop("REPOSITORY_NETWORK_MODE", None)
        elif original_network:
            self.env["REPOSITORY_NETWORK_MODE"] = original_network
        result["cleanup"] = {"status": "passed", "duration": "%ds" % (int(now()) - cleanup_start)}

        test_duration = int(now()) - test_start
        if overall == "failed" and not first_failure:
            self.collect_template_artifacts(template_path, template_dir, "unknown")
        result["overall"] = overall
        result["duration"] = "%ds" % test_duration
        result["error"] = error_msg or None
        self._record(result)
        if overall == "passed":
            self.passed += 1
            self.log_success("Template passed: %s (%ds)" % (template_path, test_duration))
        else:
            self.failed += 1
            self.log_error("Template failed: %s (%ds)" % (template_path, test_duration))

    # ------------------------------------------------------------------ reporting

    def generate_report(self) -> None:
        duration = _duration(int(now()) - self.start_time)
        self.log_info("Generating test report")
        head = (
            '{\n  "summary": {\n    "total": %d,\n    "passed": %d,\n    "failed": %d,\n'
            '    "skipped": %d,\n    "duration": "%s",\n    "timestamp": "%s"\n  },\n'
            '  "results": [\n'
            % (self.total, self.passed, self.failed, self.skipped, duration, _stamp())
        )
        body = ",\n".join("    %s\n" % r for r in self.results)
        self.results_file.parent.mkdir(parents=True, exist_ok=True)
        self.results_file.write_text(head + body + "\n  ]\n}\n", encoding="utf-8")
        self.log_info("Test report saved to %s" % self.results_file)

    def print_summary(self) -> int:
        duration = _duration(int(now()) - self.start_time)
        err = sys.stderr
        print(file=err)
        print("==========================================", file=err)
        print("          TEST SUMMARY", file=err)
        print("==========================================", file=err)
        print("Total tests:    %d" % self.total, file=err)
        self._color(GREEN, "Passed:         %d" % self.passed)
        self._color(RED, "Failed:         %d" % self.failed)
        self._color(YELLOW, "Skipped:        %d" % self.skipped)
        print("Duration:       %s" % duration, file=err)
        print("==========================================", file=err)
        print(file=err)
        if self.failed > 0:
            self._color(RED, "Some tests failed. Check %s for details." % self.results_file)
            return 1
        self._color(GREEN, "All tests passed!")
        return 0

    # ------------------------------------------------------------------ main

    def run(self, argv: list[str]) -> int:
        try:
            if not self.parse_args(argv):
                return 0
        except UsageError as exc:
            if str(exc) != "unknown option":
                self.log_error(str(exc))
            return 1
        self.log_info("Starting template tests")
        self.log_info("Templates directory: %s" % self.templates_dir)
        self.log_info("Results file: %s" % self.results_file)
        if self.filter_category:
            self.log_info("Filter category: %s" % self.filter_category)
        if self.filter_templates:
            self.log_info("Filter templates: %s" % " ".join(self.filter_templates))
        if self.skip_templates:
            self.log_info("Skipping templates: %s" % " ".join(self.skip_templates))
        self.initialize_artifacts()
        try:
            self.skipped, templates = self.discover_templates()
        except NoTemplatesError:
            return 1
        self.total = len(templates)
        for template in templates:
            self.test_template(template)
            print(file=sys.stderr)
        self.generate_report()
        return self.print_summary()


def main(argv: list[str] | None = None, package_dir: pathlib.Path | None = None) -> int:
    try:
        suite = Suite(package_dir or PACKAGE_DIR)
    except UsageError as exc:
        print("%s[FAIL] %s%s" % (RED, exc, NC), file=sys.stderr)
        return 1
    return suite.run(list(sys.argv[1:] if argv is None else argv))


if __name__ == "__main__":
    sys.exit(main())
