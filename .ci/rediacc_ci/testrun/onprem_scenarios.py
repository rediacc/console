"""The on-premise scenario runner (PLAN-rmcp-executor-hardening.md, Design 16, box EHOP2).

    PYTHONPATH=.ci python3 -m rediacc_ci.testrun.onprem_scenarios --suite <name> [--suite <name> ...] [--env .onprem/stack.env] [--compare bench]
    PYTHONPATH=.ci python3 -m rediacc_ci.testrun.onprem_scenarios --all
    PYTHONPATH=.ci python3 -m rediacc_ci.testrun.onprem_scenarios --list

A suite is a module under `rediacc_ci/testrun/onprem_suites/` registering named scenarios (see that package's docstring). Each scenario drives the real CLI, the daemon and, where relevant, the stdio or remote MCP server through a `Context`, and the runner writes ONE JSON verdict line per scenario on stdout:

    {"suite":"smoke","scenario":"account_health","target":"onprem","ok":true,"code":200,"detail":""}

Exit 0 when every verdict is `ok`, 1 otherwise, 2 for a usage error. Diagnostics go to stderr. A scenario that raises a KeyError (a key the env file lacks), OSError, ValueError, RuntimeError or SubprocessError is a failed verdict carrying the exception's type and message, never a crash that drops the verdicts after it (any other exception is a bug in the scenario and propagates); the secrets the stack holds (token values) are scrubbed from every detail.

`--compare bench` (D49, the parity tier) runs each selected scenario that names both targets on the stack AND against `./rdc.sh --config eu-bench`, prints one `{"compare": ...}` line per scenario with both verdicts, and fails on any pair whose `ok` or `code` differ. A scenario that names only `onprem` prints `{"compare":..., "skipped": "onprem only"}`; it counts as neither a match nor a mismatch. A comparison with no scenario in common is a failure, since an empty comparison proves nothing.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import subprocess
import sys
from typing import TYPE_CHECKING

from rediacc_ci import log, paths
from rediacc_ci.testrun import onprem_stack, onprem_suites
from rediacc_ci.testrun.onprem_suites import Result, Scenario

if TYPE_CHECKING:
    from collections.abc import Callable

SELF = "rediacc_ci.testrun.onprem_scenarios"
DEFAULT_ENV = pathlib.Path(onprem_stack.STATE_DIR) / onprem_stack.ENV_NAME
BENCH_CONFIG = "eu-bench"
DETAIL_LIMIT = 300
COMMAND_TIMEOUT_S = 300
TIMEOUT_RC = 124


class UsageError(Exception):
    """A usage error; exit 2."""


def parse_env_file(path: pathlib.Path) -> dict[str, str]:
    """`KEY=value` lines of a stack env file."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise UsageError(
            "%s cannot be read (%s); bring the stack up with `python3 -m %s up`"
            % (path, exc.strerror or exc, onprem_stack.SELF)
        ) from None
    values: dict[str, str] = {}
    for line in text.splitlines():
        key, sep, value = line.partition("=")
        if sep and key.strip():
            values[key.strip()] = value.strip()
    return values


class Context:
    """What a scenario may touch: the stack's env, the CLI, HTTP, and the serve command, through one `Runtime` a test replaces."""

    def __init__(
        self,
        target: str,
        env: dict[str, str],
        root: pathlib.Path,
        runtime: onprem_stack.Runtime | None = None,
    ) -> None:
        self.target = target
        self.env = env
        self.root = root
        self.rt = runtime or onprem_stack.Runtime()
        self._secrets: list[str] = []

    # ── values ──────────────────────────────────────────────────────────────

    def value(self, key: str) -> str:
        """A stack env value; a key the env file does not name raises KeyError, which the runner reports as a failed verdict."""
        if key not in self.env:
            raise KeyError("the stack env file does not name %s" % key)
        return self.env[key]

    def token(self, name: str) -> str:
        """The token whose file the env names (`executor`, `enroll` or `other`); remembered so a verdict never carries it."""
        path = pathlib.Path(self.value("ONPREM_%s_TOKEN_FILE" % name.upper()))
        token = path.read_text(encoding="utf-8").strip()
        self._secrets.append(token)
        return token

    def scrub(self, text: str) -> str:
        for secret in self._secrets:
            if secret:
                text = text.replace(secret, "***")
        return text

    # ── the CLI ─────────────────────────────────────────────────────────────

    def exec(
        self, argv: list[str], env: dict[str, str] | None = None, timeout: float = COMMAND_TIMEOUT_S
    ) -> subprocess.CompletedProcess[str]:
        """Run a command; a timeout is a result with exit code 124, not an exception."""
        try:
            return self.rt.run(argv, env=env, cwd=self.root, timeout=timeout)
        except subprocess.TimeoutExpired:
            return subprocess.CompletedProcess(
                argv, TIMEOUT_RC, "", "timed out after %ss" % timeout
            )

    def cli_env(self, token: str | None = None) -> dict[str, str]:
        """The environment of an `rdc` call: on the stack, its own config home and account server; against bench, the ambient one."""
        env = dict(os.environ)
        if self.target == "onprem":
            env["XDG_CONFIG_HOME"] = self.value("ONPREM_DAEMON_HOME")
            env["REDIACC_ACCOUNT_SERVER"] = self.value("ONPREM_ACCOUNT_URL")
        if token is not None:
            env["REDIACC_TOKEN"] = token
        return env

    def config_name(self) -> str:
        return self.value("ONPREM_CONFIG_NAME") if self.target == "onprem" else BENCH_CONFIG

    def rdc(
        self,
        *args: str,
        token: str | None = None,
        proxy: str | None = None,
        timeout: float = COMMAND_TIMEOUT_S,
    ) -> subprocess.CompletedProcess[str]:
        """`./rdc.sh --config <name> [--proxy <url>] <args>`; `token` becomes REDIACC_TOKEN."""
        argv = [str(self.root / "rdc.sh"), "--config", self.config_name()]
        if proxy:
            argv += ["--proxy", proxy]
        argv += list(args)
        return self.exec(argv, env=self.cli_env(token), timeout=timeout)

    # ── HTTP, ports and the serve command ───────────────────────────────────

    def http_get(
        self, url: str, headers: dict[str, str] | None = None, insecure_tls: bool = False
    ) -> tuple[int, str]:
        return self.rt.http_get(url, headers, insecure_tls)

    def port_answers(self, port: int) -> bool:
        return self.rt.port_answers(port)

    def serve_probe(self, args: list[str], token: str, wait_s: float) -> tuple[int | None, int]:
        """Start `rdc serve <args>` as its own group and wait up to `wait_s` for it to exit.

        Returns (exit code, or None while it still runs; the group id). The caller reads what it needs while the group lives and ends it with `stop`.
        """
        log_file = pathlib.Path(self.value("ONPREM_DAEMON_HOME")) / "probe.log"
        argv = [str(self.root / "rdc.sh"), "--config", self.config_name(), "serve", *args]
        pgid = self.rt.spawn_group(argv, self.cli_env(token), self.root, log_file)
        waited = 0.0
        while waited < wait_s:
            code = self.rt.exited(pgid)
            if code is not None:
                return code, pgid
            self.rt.sleep(0.5)
            waited += 0.5
        return None, pgid

    def exited(self, pgid: int) -> int | None:
        return self.rt.exited(pgid)

    def sleep(self, seconds: float) -> None:
        self.rt.sleep(seconds)

    def stop(self, pgid: int) -> None:
        self.rt.kill_group(pgid)


def verdict_line(scenario: Scenario, result: Result, ctx: Context) -> dict:
    return {
        "suite": scenario.suite,
        "scenario": scenario.name,
        "target": ctx.target,
        "ok": result.ok,
        "code": result.code,
        "detail": ctx.scrub(result.detail)[:DETAIL_LIMIT],
    }


def run_scenario(scenario: Scenario, ctx: Context) -> dict:
    """One verdict line. An exception is a failed verdict naming it."""
    try:
        result = scenario.run(ctx)
    except (KeyError, OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        result = Result(False, None, "%s: %s" % (type(exc).__name__, exc))
    return verdict_line(scenario, result, ctx)


def check_suites(registry: dict[str, dict[str, Scenario]], suites: list[str]) -> None:
    for name in suites:
        if name not in registry:
            raise UsageError(
                "unknown suite %s; registered: %s" % (name, ", ".join(sorted(registry)))
            )


def run_suites(
    registry: dict[str, dict[str, Scenario]],
    suites: list[str],
    ctx: Context,
    emit: Callable[[dict], None],
) -> list[dict]:
    check_suites(registry, suites)
    scenarios = [s for name in suites for s in registry[name].values() if ctx.target in s.targets]
    if not scenarios:
        raise UsageError(
            "suite(s) %s hold no scenario for target %s" % (", ".join(suites), ctx.target)
        )
    lines = []
    for scenario in scenarios:
        line = run_scenario(scenario, ctx)
        emit(line)
        lines.append(line)
    return lines


def compare(
    registry: dict[str, dict[str, Scenario]],
    suites: list[str],
    onprem: Context,
    bench: Context,
    emit: Callable[[dict], None],
) -> bool:
    """Run the shared scenarios on both targets, emit one comparison line each, and return True when every pair matches."""
    check_suites(registry, suites)
    matched = mismatched = 0
    for name in suites:
        for scenario in registry[name].values():
            if "onprem" not in scenario.targets:
                continue
            label = "%s/%s" % (scenario.suite, scenario.name)
            if "bench" not in scenario.targets:
                emit({"compare": label, "skipped": "onprem only"})
                continue
            left = run_scenario(scenario, onprem)
            right = run_scenario(scenario, bench)
            same = (left["ok"], left["code"]) == (right["ok"], right["code"])
            matched += same
            mismatched += not same
            emit(
                {
                    "compare": label,
                    "match": same,
                    "onprem": {k: left[k] for k in ("ok", "code", "detail")},
                    "bench": {k: right[k] for k in ("ok", "code", "detail")},
                }
            )
    if matched + mismatched == 0:
        log.error(
            "--compare found no scenario that names both targets; an empty comparison proves nothing"
        )
        return False
    return mismatched == 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=SELF, description=(__doc__ or "").splitlines()[0])
    parser.add_argument(
        "--suite", action="append", default=[], help="a registered suite (repeatable)"
    )
    parser.add_argument("--all", action="store_true", help="every registered suite")
    parser.add_argument("--list", action="store_true", help="print the registered scenarios")
    parser.add_argument(
        "--env", default=None, help="the stack env file (default .onprem/stack.env)"
    )
    parser.add_argument("--compare", choices=("bench",), default=None)
    return parser


def _emit(line: dict) -> None:
    print(json.dumps(line, separators=(",", ":")), flush=True)


def main(
    argv: list[str],
    runtime: onprem_stack.Runtime | None = None,
    root: pathlib.Path | None = None,
    emit: Callable[[dict], None] = _emit,
) -> int:
    try:
        args = _parser().parse_args(argv)
    except SystemExit as exc:
        return int(exc.code or 0)
    registry = onprem_suites.load_all()
    if args.list:
        for name in sorted(registry):
            for scenario in registry[name].values():
                emit({"suite": name, "scenario": scenario.name, "targets": list(scenario.targets)})
        return 0
    suites = sorted(registry) if args.all else args.suite
    if not suites:
        print("name a suite with --suite <name>, or --all, or --list", file=sys.stderr)
        return 2
    base = root or paths.repo_root()
    try:
        env = parse_env_file(pathlib.Path(args.env) if args.env else base / DEFAULT_ENV)
        onprem = Context("onprem", env, base, runtime)
        if args.compare:
            bench = Context("bench", env, base, runtime)
            return 0 if compare(registry, suites, onprem, bench, emit) else 1
        lines = run_suites(registry, suites, onprem, emit)
    except UsageError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    return 0 if all(line["ok"] for line in lines) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
