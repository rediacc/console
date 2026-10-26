#!/usr/bin/env python3
"""Switch one target's console executor on or off: the account Worker's EXECUTOR_MODE secret (agent/plans/PLAN-proxy-cd-six-targets.md, Design item 2, box D2).

    PYTHONPATH=.ci python3 -m rediacc_ci.deploy.console_executor --enable --target edge|stable --region eu|us|asia
    PYTHONPATH=.ci python3 -m rediacc_ci.deploy.console_executor --disable --target edge|stable|bench [--region eu]

THE SWITCH. EXECUTOR_MODE is never a `[vars]` entry (the account wrangler-config gate refuses one): CD owns it as a Worker secret. `--enable` runs `wrangler secret put EXECUTOR_MODE` with the value `proxy` on wrangler's STDIN, never on argv. `--disable` runs `wrangler secret delete EXECUTOR_MODE`, after which the Worker falls back to its default mode, which a deployed Worker refuses with the coded `CONSOLE_EXECUTION_UNAVAILABLE` 503. A secret survives later account deploys, so a region stays open across releases once its proxy smoke has passed, and CD's rollback step closes it again.

CD runs `--enable` only after that target's proxy smoke passes (operator ruling ASKED:2026-10-25T18:18Z, "Closed until smoke passes"), with `if: steps.proxy_smoke.outcome == 'success'` in .github/workflows/cd-deploy-account.yml.

EVERY SWITCH IS READ BACK. A put or delete that exits 0 is not taken as the answer: `wrangler secret list --format json` must then name EXECUTOR_MODE after an enable and must not name it after a disable. A listing that fails or does not parse is UNKNOWN, and unknown exits 1, because "the region is closed" is a claim this module only makes after reading it. A delete of a secret that was never set fails in wrangler, and the read-back turns that into "already closed" (exit 0), so a disable is idempotent.

THE TARGET. `--target` and `--region` name one account config, `workers/account/wrangler.<region>.toml` for stable, `wrangler.edge-<region>.toml` for edge and `wrangler.bench.toml` for bench (eu only); the Worker name is read from that file's `name` and passed to wrangler as `--name` next to `--config`, so the call names its Worker twice and cannot land on another.

ENVIRONMENT. `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID`, from CD's Bitwarden step. A bare local call needs the `deploy-proxy` bws profile (bench: `deploy-proxy-bench`): when either variable is unset and that profile is not bound, the run re-executes itself under `bws_env exec --profile <profile>`, so no wrapper is typed.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tomllib
from typing import TYPE_CHECKING

from rediacc_ci import log, paths

if TYPE_CHECKING:
    import pathlib

SELF = "rediacc_ci.deploy.console_executor"

MODE_KEY = "EXECUTOR_MODE"
MODE_VALUE = "proxy"

EDGE_TARGET = "edge"
STABLE_TARGET = "stable"
BENCH_TARGET = "bench"
TARGETS = (EDGE_TARGET, STABLE_TARGET, BENCH_TARGET)
BENCH_REGION = "eu"

ACCOUNT_SUBDIR = ("workers", "account")
ACCOUNT_REL = "/".join(ACCOUNT_SUBDIR)

PROFILE = "deploy-proxy"
BENCH_PROFILE = "deploy-proxy-bench"
PACKAGE_PARENT = str(paths.repo_root() / ".ci")


def profile_for(target: str) -> str:
    return BENCH_PROFILE if target == BENCH_TARGET else PROFILE


def missing_env() -> list[str]:
    """The required variables that are unset or empty, read by name."""
    missing = []
    if not os.environ.get("CLOUDFLARE_API_TOKEN"):
        missing.append("CLOUDFLARE_API_TOKEN")
    if not os.environ.get("CLOUDFLARE_ACCOUNT_ID"):
        missing.append("CLOUDFLARE_ACCOUNT_ID")
    return missing


def profile_bound(profile: str) -> bool:
    return profile in (os.environ.get("REDIACC_BWS_PROFILES") or "").split(",")


def reexec_argv(profile: str, argv: list[str]) -> list[str]:
    """This same run under one bws profile."""
    return [
        sys.executable,
        "-m",
        "rediacc_ci.core.bws_env",
        "exec",
        "--profile",
        profile,
        "--",
        sys.executable,
        "-m",
        SELF,
        *argv,
    ]


def package_env() -> dict[str, str]:
    """The child environment with this checkout's `.ci` first on PYTHONPATH."""
    env = dict(os.environ)
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = PACKAGE_PARENT + (os.pathsep + existing if existing else "")
    return env


class RefusedError(Exception):
    """A run that must stop with exit 1; the message is printed as an error."""


def account_config(target: str, region: str) -> str:
    """The account wrangler config file name for one target."""
    if target == BENCH_TARGET:
        return "wrangler.bench.toml"
    if target == EDGE_TARGET:
        return "wrangler.edge-%s.toml" % region
    return "wrangler.%s.toml" % region


def region_ids(repo_root: pathlib.Path) -> list[str]:
    """The region ids regions.json names."""
    try:
        doc = json.loads((repo_root / "regions.json").read_text(encoding="utf-8"))
        return sorted(str(r["id"]).lower() for r in doc["regions"])
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise RefusedError("%s: regions.json cannot be read: %s" % (SELF, exc)) from None


def resolve_target(repo_root: pathlib.Path, target: str, region: str | None) -> tuple[str, str]:
    """(region, config file name) for a valid target, refused otherwise."""
    if target not in TARGETS:
        raise RefusedError("--target %s is not one of %s" % (target, ", ".join(TARGETS)))
    if target == BENCH_TARGET:
        region = region or BENCH_REGION
        if region != BENCH_REGION:
            raise RefusedError(
                "--target bench refuses --region %s: bench exists only in %s"
                % (region, BENCH_REGION)
            )
    else:
        known = region_ids(repo_root)
        if not region or region not in known:
            raise RefusedError(
                "--region %s is not one of %s" % (region or "(none)", ", ".join(known))
            )
    return region, account_config(target, region)


def worker_name(config_path: pathlib.Path) -> str:
    """The `name` of one wrangler config."""
    try:
        doc = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise RefusedError("%s cannot be read: %s" % (config_path, exc)) from None
    name = doc.get("name")
    if not isinstance(name, str) or not name:
        raise RefusedError("%s has no top-level `name`" % config_path)
    return name


def put_argv(worker: str, config: str) -> list[str]:
    return ["npx", "wrangler", "secret", "put", MODE_KEY, "--name", worker, "--config", config]


def delete_argv(worker: str, config: str) -> list[str]:
    return ["npx", "wrangler", "secret", "delete", MODE_KEY, "--name", worker, "--config", config]


def list_argv(worker: str, config: str) -> list[str]:
    return [
        "npx",
        "wrangler",
        "secret",
        "list",
        "--name",
        worker,
        "--format",
        "json",
        "--config",
        config,
    ]


def secret_names(text: str) -> set[str] | None:
    """The secret names a `wrangler secret list --format json` answer holds; None when the text is not that shape.

    The JSON array is read from the first `[` to the last `]`, so a banner line wrangler prints ahead of it does not make a good answer unreadable.
    """
    start, end = text.find("["), text.rfind("]")
    if start < 0 or end < start:
        return None
    try:
        data = json.loads(text[start : end + 1])
    except ValueError:
        return None
    if not isinstance(data, list):
        return None
    names = set()
    for entry in data:
        if not isinstance(entry, dict) or not isinstance(entry.get("name"), str):
            return None
        names.add(entry["name"])
    return names


def _run(argv: list[str], cwd: pathlib.Path, stdin_text: str | None) -> int:
    """One wrangler child, both streams inherited. `stdin_text` None gives it /dev/null, so wrangler takes its non-interactive path and confirms nothing."""
    if stdin_text is None:
        return subprocess.run(argv, cwd=cwd, stdin=subprocess.DEVNULL, check=False).returncode
    return subprocess.run(argv, cwd=cwd, input=stdin_text, text=True, check=False).returncode


def _list(worker: str, config: str, cwd: pathlib.Path) -> set[str] | None:
    proc = subprocess.run(
        list_argv(worker, config),
        cwd=cwd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        text=True,
        check=False,
    )
    return secret_names(proc.stdout) if proc.returncode == 0 else None


def run(
    action: str,
    target: str,
    region: str | None,
    repo_root: pathlib.Path | None = None,
    argv: list[str] | None = None,
) -> int:
    """Enable or disable one target's console executor and read the result back. Returns the exit status."""
    root = repo_root or paths.repo_root()
    try:
        region, config = resolve_target(root, target, region)
        worker_dir = root.joinpath(*ACCOUNT_SUBDIR)
        worker = worker_name(worker_dir / config)
    except RefusedError as exc:
        log.error(str(exc))
        return 1
    missing = missing_env()
    if missing:
        profile = profile_for(target)
        if argv is not None and not profile_bound(profile):
            return subprocess.run(
                reexec_argv(profile, argv), check=False, env=package_env()
            ).returncode
        log.error(
            "%s must be set (CD's Bitwarden step, or bws_env exec --profile %s)"
            % (" and ".join(missing), profile)
        )
        return 1

    where = "%s (%s %s, %s/%s)" % (worker, target, region, ACCOUNT_REL, config)
    if action == "enable":
        log.step("Opening the console executor on %s: %s=%s..." % (where, MODE_KEY, MODE_VALUE))
        status = _run(put_argv(worker, config), worker_dir, MODE_VALUE)
        if status != 0:
            log.error("wrangler secret put %s exited %d on %s" % (MODE_KEY, status, worker))
            return status
        names = _list(worker, config, worker_dir)
        if names is None:
            log.error(
                "UNVERIFIED: wrangler secret list on %s failed or did not parse, so %s cannot be read back"
                % (worker, MODE_KEY)
            )
            return 1
        if MODE_KEY not in names:
            log.error(
                "wrangler secret put exited 0 but %s does not list %s (%d secrets listed)"
                % (worker, MODE_KEY, len(names))
            )
            return 1
        log.info(
            "Console executor OPEN on %s: %s listed among %d secrets."
            % (where, MODE_KEY, len(names))
        )
        return 0

    log.step("Closing the console executor on %s: deleting %s..." % (where, MODE_KEY))
    status = _run(delete_argv(worker, config), worker_dir, None)
    names = _list(worker, config, worker_dir)
    if names is None:
        log.error(
            "UNVERIFIED: wrangler secret list on %s failed or did not parse, so the region is not known to be closed"
            % worker
        )
        return 1
    if MODE_KEY in names:
        log.error(
            "%s still lists %s after wrangler secret delete (exit %d): the region is OPEN"
            % (worker, MODE_KEY, status)
        )
        return 1
    if status != 0:
        log.info("%s was not set on %s; the region was already closed." % (MODE_KEY, worker))
    log.info(
        "Console executor CLOSED on %s: %s absent among %d secrets." % (where, MODE_KEY, len(names))
    )
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=SELF, description=(__doc__ or "").splitlines()[0])
    switch = parser.add_mutually_exclusive_group(required=True)
    switch.add_argument("--enable", action="store_true", help="put EXECUTOR_MODE=proxy")
    switch.add_argument("--disable", action="store_true", help="delete EXECUTOR_MODE")
    parser.add_argument("--target", required=True, help="edge, stable or bench")
    parser.add_argument("--region", default=None, help="eu, us or asia (bench: eu only)")
    return parser


def main(argv: list[str]) -> int:
    try:
        args = _parser().parse_args(argv)
    except SystemExit as exc:
        return int(exc.code or 0)
    return run("enable" if args.enable else "disable", args.target, args.region, argv=argv)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
