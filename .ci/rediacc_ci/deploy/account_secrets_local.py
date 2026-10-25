"""Push the account Worker runtime secrets for ONE region and channel from an agent or operator session.

CI runs `set_account_worker_secrets` with its environment hydrated by the deploy workflow. A local run had no equivalent: the `deploy-workers` profile deliberately carries no Worker secrets, and the 2026-09-24 real run needed a scratch name-binder. This module is that entry, tracked.

WHAT IT DOES, in order. Every step refuses, and nothing later runs after a refusal.

  1. Derives the non-secret inputs from `regions.json`: WORKER_NAME, TARGET, SUFFIX, AWS_SES_REGION, both backup bucket names and R2_JURISDICTION.
  2. Checks the wrangler pin (`wrangler_pin`): constants.sh, workers/account/package.json and the install must agree.
  3. Hydrates the profile `account-secrets-<region>-<target>` of `.ci/config/secret-supply.json` through `bws_env.hydrate`. Values live in this process's environment only, never on argv.
  4. Runs the Turnstile drift preflight (`turnstile_drift`) and refuses on drift or on no verdict. A stale `CLOUDFLARE_TURNSTILE_SECRET_KEY` pushed to a Worker fails every login (2026-09-24).
  5. Runs `set_account_worker_secrets` as a child with the derived environment, from `workers/account`.

`--dry-run` stops after step 2 and prints, names only: the Worker, the profile, the derived non-secret inputs, the Worker keys the push carries and the store names the profile binds. It reads no credential and contacts no service.

Run: `PYTHONPATH=.ci python3 -m rediacc_ci.deploy.account_secrets_local --region eu --target stable [--dry-run]`

Exit codes: 0 pushed (or dry run complete), 1 a refusal, 2 a usage error.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import TYPE_CHECKING

from rediacc_ci import paths
from rediacc_ci.core import bws_env
from rediacc_ci.deploy import set_account_worker_secrets as pusher
from rediacc_ci.deploy import turnstile_drift, wrangler_pin

if TYPE_CHECKING:
    import pathlib
    from collections.abc import Callable, Mapping

SELF = "rediacc_ci.deploy.account_secrets_local"
TARGETS = ("stable", "edge")
USAGE = "usage: %s --region <id> --target stable|edge [--dry-run]" % SELF


class RefusalError(Exception):
    """A step refused; the message is the whole explanation."""


def profile_name(region: str, target: str) -> str:
    return "account-secrets-%s-%s" % (region, target)


def derive(region: str, target: str, root: pathlib.Path | None = None) -> dict[str, str]:
    """The non-secret environment of one run, from `regions.json`."""
    base = paths.repo_root() if root is None else root
    doc = json.loads(base.joinpath("regions.json").read_text(encoding="utf-8"))
    rows = [r for r in doc["regions"] if r["id"] == region]
    if not rows:
        known = " ".join(r["id"] for r in doc["regions"])
        raise RefusalError("unknown region %r (regions.json has: %s)" % (region, known))
    row = rows[0]
    return {
        "WORKER_NAME": row["workerName"] if target == "stable" else row["edgeWorkerName"],
        "TARGET": target,
        "SUFFIX": row["secretSuffix"],
        "AWS_SES_REGION": row["sesRegion"],
        "BACKUP_BUCKET_STABLE": row["backupR2"]["name"],
        "BACKUP_BUCKET_EDGE": row["edgeBackupR2"]["name"],
        "R2_JURISDICTION": row.get("r2Jurisdiction") or "",
    }


def profile_store_names(profile: str) -> list[str]:
    """The store names the profile binds (required then optional)."""
    table = bws_env.profiles()
    required, optional = bws_env.profile_specs(table, [profile])
    return [name for name, _local in required + optional]


def push_keys() -> list[str]:
    return [key for key, _var, _source in pusher.KEYS]


def dry_run_lines(region: str, target: str, root: pathlib.Path | None = None) -> list[str]:
    """Everything the run would use, names only."""
    derived = derive(region, target, root)
    profile = profile_name(region, target)
    keys = push_keys()
    store = profile_store_names(profile)
    return [
        "%s: dry run for %s (region %s, target %s)"
        % (SELF, derived["WORKER_NAME"], region, target),
        "profile: %s" % profile,
        *("derived %s=%s" % (k, derived[k] or "(empty)") for k in derived),
        "%d Worker key(s) pushed:" % len(keys),
        *("  %s" % k for k in keys),
        "%d store name(s) bound by the profile:" % len(store),
        *("  %s" % n for n in store),
        "not run in a dry run: bws hydration, the Turnstile drift preflight, the push",
    ]


def preflight_drift(env: Mapping[str, str], fetch: Callable = turnstile_drift.http_fetch) -> None:
    """The Turnstile drift preflight, in this process. Raises on drift or no verdict."""
    code = turnstile_drift.main([], env=env, fetch=fetch)
    if code != 0:
        raise RefusalError(
            "Turnstile drift preflight failed (exit %d): the push is refused; nothing was sent"
            % code
        )


def hydrate(profile: str) -> dict[str, str]:
    try:
        child, _carried = bws_env.hydrate([profile])
    except bws_env.RefusalError as exc:
        raise RefusalError("\n".join(exc.lines)) from None
    return child


def push(env: dict[str, str], root: pathlib.Path | None = None) -> int:
    """The child that sends the document. Both streams inherited."""
    base = paths.repo_root() if root is None else root
    ci_dir = str(base / ".ci")
    env = dict(env, PYTHONPATH=ci_dir + os.pathsep + env.get("PYTHONPATH", ""))
    return subprocess.run(
        [sys.executable, "-m", "rediacc_ci.deploy.set_account_worker_secrets"],
        env=env,
        cwd=str(base / "workers" / "account"),
        check=False,
    ).returncode


def parse(argv: list[str]) -> tuple[str, str, bool] | None:
    region = target = ""
    dry = False
    i = 0
    while i < len(argv):
        if argv[i] == "--region" and i + 1 < len(argv):
            region = argv[i + 1]
            i += 1
        elif argv[i] == "--target" and i + 1 < len(argv):
            target = argv[i + 1]
            i += 1
        elif argv[i] == "--dry-run":
            dry = True
        else:
            return None
        i += 1
    if not region or target not in TARGETS:
        return None
    return region, target, dry


def run(
    argv: list[str],
    *,
    hydrate_fn: Callable[[str], dict[str, str]] = hydrate,
    fetch: Callable = turnstile_drift.http_fetch,
    push_fn: Callable[[dict[str, str]], int] = push,
    root: pathlib.Path | None = None,
) -> int:
    parsed = parse(argv)
    if parsed is None:
        print(USAGE, file=sys.stderr)
        return 2
    region, target, dry = parsed
    try:
        derived = derive(region, target, root)
        code, lines = wrangler_pin.check(paths.repo_root() if root is None else root)
        if code != 0:
            raise RefusalError("\n".join(lines))
        if dry:
            for line in dry_run_lines(region, target, root):
                print(line)
            return 0
        env = dict(hydrate_fn(profile_name(region, target)))
        preflight_drift(env, fetch)
        env.update(derived)
        return push_fn(env)
    except RefusalError as exc:
        print("%s: refused: %s" % (SELF, exc), file=sys.stderr)
        return 1


def main(argv: list[str]) -> int:
    return run(argv)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
