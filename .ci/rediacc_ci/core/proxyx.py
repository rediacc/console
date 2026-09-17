"""Port of the SHARED CONTRACT in `.ci/scripts/test/proxies/proxy-lib.sh`.

`proxy-lib.sh` is sourced, never executed -- it has no exec bit "by design" (its own header says so) and every real invocation is one of the nine `proxy-*.sh` scripts in that directory sourcing it for its functions. There is therefore no bash TWIN for this file itself to be shadow-gated against: the twin relationship lives one level up, between each `proxy-*.sh` and its
`rediacc_ci.proxies.*` port, both of which import this module the way the bash scripts source `proxy-lib.sh`.

WHAT A PROXY IS, copied from the bash header because the contract is the point: a heavy CI job that `npm run ci` never exercises gets a local stand-in that runs the SAME subject script CI runs, on a reduced input, so a developer finds the breakage before the push instead of after it.

THE ONE RULE THAT MAKES A PROXY HONEST, preserved exactly: the exit alphabet is three symbols and no others.

    0    the real subject ran and passed
    77   the subject could not be run here; NOT a verdict
    any other non-zero   the subject ran and there is a real finding

ANTI-VACUITY, preserved exactly: `finish()` refuses to return 0 when zero checks were made, and `preflight()` refuses to run at all when zero requirements were declared (a preflight that checks nothing could never say cannot-run, so its green would mean nothing).

COLOUR is decided by `sys.stdout.isatty()` at construction time, matching bash's `[[ -t 1 ]]` decided once at `proxy_init` time -- not re-checked per call, so a script that later redirects stdout keeps whatever it started with, exactly as the bash globals do.
"""

from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field

PROXY_CANNOT_RUN = 77

RED = "\033[0;31m"
GREEN = "\033[0;32m"
YEL = "\033[1;33m"
OFF = "\033[0m"


@dataclass
class Proxy:
    name: str
    subject: str
    checks: int = 0
    failures: int = 0
    reqs: int = 0
    missing: list[str] = field(default_factory=list)
    _color: bool = field(default_factory=sys.stdout.isatty)
    last_stdout: str = ""
    last_stderr: str = ""
    last_rc: int = 0

    def __post_init__(self) -> None:
        print(f"proxy {self.name}: local stand-in for {self.subject}")

    # -- colour helpers, mirroring PROXY_RED/GREEN/YEL/OFF ------------------
    def _c(self, code: str) -> str:
        return code if self._color else ""

    # -- requirement declarations --------------------------------------
    def need_cmd(self, cmd: str, fix: str) -> None:
        self.reqs += 1
        if shutil.which(cmd) is None:
            self.missing.append(f"{cmd} is not on PATH -- fix: {fix}")

    def need_file(self, path: str, fix: str) -> None:
        self.reqs += 1
        if not os.path.exists(path):
            self.missing.append(f"{path} does not exist -- fix: {fix}")

    def need_exec(self, path: str, fix: str) -> None:
        self.reqs += 1
        if not (os.path.isfile(path) and os.access(path, os.X_OK)):
            self.missing.append(f"{path} is not an executable file -- fix: {fix}")

    def need_docker_daemon(self) -> None:
        self.reqs += 1
        if shutil.which("docker") is None:
            self.missing.append("docker is not on PATH -- fix: ./run.sh setup")
            return
        rc = subprocess.run(
            ["docker", "info"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        ).returncode
        if rc != 0:
            self.missing.append(
                "the docker daemon is not reachable -- fix: start docker, or add "
                "yourself to the docker group and re-login"
            )

    def need_passwordless_sudo(self) -> None:
        self.reqs += 1
        rc = subprocess.run(
            ["sudo", "-n", "true"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        ).returncode
        if rc != 0:
            self.missing.append(
                "passwordless sudo is unavailable -- fix: run this on a host where "
                "'sudo -n true' succeeds"
            )

    def need_url(self, url: str, fix: str) -> None:
        self.reqs += 1
        if shutil.which("curl") is None:
            self.missing.append("curl is not on PATH -- fix: install curl")
            return
        rc = subprocess.run(
            ["curl", "-sS", "-m", "10", "-o", "/dev/null", url],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        ).returncode
        if rc != 0:
            self.missing.append(f"{url} is unreachable -- fix: {fix}")

    # -- preflight --------------------------------------------------------
    def preflight(self) -> None:
        if self.reqs == 0:
            print(
                f"{self._c(RED)}proxy {self.name}: declared ZERO requirements{self._c(OFF)}",
                file=sys.stderr,
            )
            print(
                "  A preflight that checks nothing cannot report cannot-run, so its",
                file=sys.stderr,
            )
            print("  green would mean nothing. Declare what the subject needs.", file=sys.stderr)
            raise SystemExit(2)
        if self.missing:
            print(
                f"{self._c(YEL)}proxy {self.name}: CANNOT RUN "
                f"({len(self.missing)} of {self.reqs} requirement(s) missing){self._c(OFF)}",
                file=sys.stderr,
            )
            for m in self.missing:
                print(f"  - {m}", file=sys.stderr)
            print(
                f"  Exiting {PROXY_CANNOT_RUN} (cannot-run). This is NOT a pass and NOT a verdict:",
                file=sys.stderr,
            )
            print(f"  {self.subject} was not exercised on this host.", file=sys.stderr)
            raise SystemExit(PROXY_CANNOT_RUN)
        print(f"proxy {self.name}: toolchain complete, {self.reqs} requirement(s) satisfied")

    # -- assertions ---------------------------------------------------------
    def ok(self, label: str) -> None:
        self.checks += 1
        print(f"{self._c(GREEN)}PASS:{self._c(OFF)} {label}")

    def bad(self, label: str) -> None:
        self.checks += 1
        self.failures += 1
        print(f"{self._c(RED)}FAIL:{self._c(OFF)} {label}", file=sys.stderr)

    def expect_exit(self, expected: str, label: str, cmd: list[str]) -> None:
        """`expected` may be a single code or a comma list, both as strings."""
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        rc = proc.returncode
        wanted = {int(x) for x in expected.split(",")}
        if rc in wanted:
            self.ok(f"{label} (exit {rc})")
        else:
            self.bad(f"{label}: expected exit {expected}, got {rc}")
            print("  --- subject stdout (last 40 lines) ---", file=sys.stderr)
            for line in proc.stdout.splitlines()[-40:]:
                print(line, file=sys.stderr)
            print("  --- subject stderr (last 40 lines) ---", file=sys.stderr)
            for line in proc.stderr.splitlines()[-40:]:
                print(line, file=sys.stderr)
        self.last_stdout = proc.stdout
        self.last_stderr = proc.stderr
        self.last_rc = rc

    def expect_contains(self, haystack: str, needle: str, label: str) -> None:
        if needle in haystack:
            self.ok(label)
        else:
            self.bad(f"{label}: expected output to contain '{needle}'")

    # -- finish -------------------------------------------------------------
    def finish(self) -> int:
        if self.checks == 0:
            print(
                f"{self._c(RED)}proxy {self.name}: made ZERO checks{self._c(OFF)}", file=sys.stderr
            )
            print(
                "  The proxy is not seeing its subject; its green would mean nothing.",
                file=sys.stderr,
            )
            return 1
        if self.failures > 0:
            print(
                f"{self._c(RED)}proxy {self.name}: {self.failures} of {self.checks} "
                f"check(s) FAILED{self._c(OFF)}",
                file=sys.stderr,
            )
            print(f"  Subject: {self.subject}", file=sys.stderr)
            return 1
        print(
            f"{self._c(GREEN)}proxy {self.name}: {self.checks} check(s) passed, "
            f"{self.reqs} requirement(s) present{self._c(OFF)}"
        )
        return 0


# --------------------------------------------------------------------------- The shared selftest, mirroring `proxy_lib_selftest` in the bash twin.
#
# Same shape, same reason: a REAL PATH removal (env -i with PATH pointing at an empty directory), not a simulated "pretend it is missing" flag, and BOTH directions -- something that must exit 0, something that must exit 77 (toolchain gone), something that must exit 1 (zero checks), something that must exit 2 (zero declared requirements).
# ---------------------------------------------------------------------------


def _probe_present() -> int:
    p = Proxy("selftest-probe", "a fixture subject")
    p.need_cmd("bash", "install bash")
    p.preflight()
    p.ok("the fixture asserted something")
    return p.finish()


def _probe_vacuous() -> int:
    p = Proxy("selftest-vacuous", "a fixture subject that asserts nothing")
    p.need_cmd("bash", "install bash")
    p.preflight()
    return p.finish()


def _probe_noreqs() -> int:
    p = Proxy("selftest-noreqs", "a fixture subject with no declared toolchain")
    p.preflight()
    return p.finish()


def run_selftest() -> int:
    """Both directions, over a real subprocess boundary for the PATH case.

    Cases 2-4 run `python3 -c "..."` as a CHILD process (like the bash twin running a throwaway probe script), because case 2 needs an environment where `shutil.which('bash')` genuinely fails -- a real PATH removal, not a monkeypatched one.
    """
    fails = 0
    cases = 0
    module = __name__
    # `.ci`, the directory a caller normally puts on PYTHONPATH to reach the `rediacc_ci` package. Computed from this file's own location (three parents up from `.ci/rediacc_ci/core/proxyx.py`) rather than trusted from the CALLING process's environment, because that environment is not guaranteed to carry it -- a pytest run of this module directly does not, and the child subprocess
    # below would then fail to import `rediacc_ci` at all rather than exercising the case it is meant to prove.
    ci_dir = str(pathlib.Path(__file__).resolve().parents[2])

    def _case(want: int, label: str, env: dict[str, str] | None, func: str) -> None:
        nonlocal fails, cases
        cases += 1
        code = f"import sys; from {module} import {func}; sys.exit({func}())"
        child_env = dict(env or {})
        existing = child_env.get("PYTHONPATH", "")
        child_env["PYTHONPATH"] = ci_dir if not existing else f"{ci_dir}{os.pathsep}{existing}"
        result = subprocess.run(
            [sys.executable, "-c", code],
            env=child_env,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == want:
            print(f"PASS: selftest {label} (exit {result.returncode})")
        else:
            print(
                f"FAIL: selftest {label}: expected {want}, got {result.returncode}",
                file=sys.stderr,
            )
            fails += 1

    _case(0, "toolchain present -> 0", os.environ.copy(), "_probe_present")

    with tempfile.TemporaryDirectory() as bindir:
        stripped = os.environ.copy()
        stripped["PATH"] = bindir
        _case(PROXY_CANNOT_RUN, "toolchain removed from PATH -> 77", stripped, "_probe_present")

    _case(1, "zero checks -> 1, never 0", os.environ.copy(), "_probe_vacuous")
    _case(2, "zero declared requirements -> 2", os.environ.copy(), "_probe_noreqs")

    # "proxy-lib", not "proxyx": every ported proxy's `--selftest` output must stay byte-identical to its bash twin's, and the bash twin's own selftest (`proxy_lib_selftest` in `proxy-lib.sh`) prints that literal name. Caught by `test_proxies_cli_manifest.py::test_selftest_is_byte_identical` the first time this said "proxyx selftest" instead.
    if fails:
        print(f"proxy-lib selftest: {fails} of {cases} case(s) FAILED", file=sys.stderr)
        return 1
    print(f"proxy-lib selftest: {cases} case(s) passed")
    return 0
