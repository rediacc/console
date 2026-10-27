"""Push one environment's backup key pair to ONE account Worker, outside a release, with a health check on both sides.

    PYTHONPATH=.ci python3 -m rediacc_ci.ops.push_backup_credentials --target stable|edge|bench [--region eu|us|asia] [--dry-run]

WHY IT EXISTS. Each environment's Workers presign backup grants with their own bucket-scoped key pair (agent/plans/PLAN-backup-credential-isolation.md). Stable Workers receive secrets only on promote-stable and bench only on a full deploy_bench, so rotating the pair on a live Worker needs a narrow tool that touches nothing else: the four `ACCOUNT_BACKUP_S3_*` secrets of one Worker, one Worker per run.

THE STEPS, IN ORDER, AND EACH REFUSAL STOPS THE RUN BEFORE THE NEXT STEP:

  1. Re-execute under the `backup-push-<target>` Bitwarden profile (.ci/config/secret-supply.json) unless it is already bound. That profile binds ONLY that environment's pair, renamed to the two names the Worker reads, the shared endpoint, and the Workers deploy token.
  2. Resolve the Worker, its bucket and its host from regions.json (stable, edge) or workers/account/wrangler.bench.toml (bench), and cross-check the Worker's own wrangler config: its `name` and its `BACKUP_BUCKET` binding must be the same Worker and bucket, or the push would hand a Worker a bucket it is not bound to.
  3. Check that the three bound values are present (names only), and that no `ACCOUNT_BACKUP_S3_*_{STABLE,EDGE,BENCH}` name is in the environment: under the profile there is none, so one there means the run is holding a second environment's key.
  4. `portal_health` for the Worker's host. Red refuses: a push onto a broken portal would leave nothing to compare the after-check with.
  5. `wrangler secret list` (names only). The four names must already be there, because this tool replaces values and never adds a secret; a Worker missing one needs a deploy.
  6. ONE `wrangler secret bulk --name <worker>` with exactly the four `ACCOUNT_BACKUP_S3_*` keys: ENDPOINT (through `set_account_worker_secrets.apply_jurisdiction`, so an EU bucket gets the `.eu.` host), BUCKET, ACCESS_KEY_ID and SECRET_ACCESS_KEY. The document goes on wrangler's STDIN, never on argv and never to a file; wrangler's own output is printed with the four values masked.
  7. `wrangler secret list` again. A changed name set refuses loudly (exit 1), naming the added and removed names.
  8. `portal_health` again. Red after a push exits 1 and names the rollback (push the previous pair; the shared token stays valid until B7 revokes it).

`--dry-run` runs steps 1 to 5 and prints the Worker, the bucket, the four NAMES and the commands step 6 to 8 would run. It writes nothing.

NO VALUE IS PRINTED, EVER. The output carries names, the Worker, the bucket, the host, URLs and statuses. The wrangler children receive the Cloudflare token through the environment as every wrangler call here does, and do NOT receive the backup values in theirs: the bulk document on stdin is the only place the values travel.

Exit 0 on success, 1 on any refusal or failure (a regions.json entry the Worker's own wrangler config contradicts included), 2 on a usage error: an argument argparse refuses, `--region` with bench, no `--region` for stable or edge, or a region regions.json does not name.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tomllib
from collections.abc import Callable
from dataclasses import dataclass

from rediacc_ci import paths
from rediacc_ci.core import wrangler
from rediacc_ci.deploy import set_account_worker_secrets
from rediacc_ci.ops import portal_health

TARGETS = ("stable", "edge", "bench")
PROFILE_PREFIX = "backup-push-"
# The four Worker secrets this tool writes, in the order the bulk document carries them.
PUSHED = (
    "ACCOUNT_BACKUP_S3_ENDPOINT",
    "ACCOUNT_BACKUP_S3_BUCKET",
    "ACCOUNT_BACKUP_S3_ACCESS_KEY_ID",
    "ACCOUNT_BACKUP_S3_SECRET_ACCESS_KEY",
)
# The three of them the profile binds; the bucket is not a secret and comes from the tree.
BOUND = (
    "ACCOUNT_BACKUP_S3_ENDPOINT",
    "ACCOUNT_BACKUP_S3_ACCESS_KEY_ID",
    "ACCOUNT_BACKUP_S3_SECRET_ACCESS_KEY",
)
# An environment-suffixed pair name anywhere in the environment means a second environment's key is in reach of this run.
SUFFIXED = tuple(
    "%s_%s" % (name, env)
    for name in ("ACCOUNT_BACKUP_S3_ACCESS_KEY_ID", "ACCOUNT_BACKUP_S3_SECRET_ACCESS_KEY")
    for env in ("STABLE", "EDGE", "BENCH")
)
WORKER_DIR = ("workers", "account")
BENCH_CONFIG = "wrangler.bench.toml"
BUCKET_BINDING = "BACKUP_BUCKET"
MASK = "<redacted>"

# (argv, cwd, stdin) -> (rc, stdout, stderr). The seam the tests replace with a recording fake.
Runner = Callable[[list[str], str, "str | None"], tuple[int, str, str]]


class PushError(Exception):
    """A refusal or failure; each line of the message is printed and the run exits 1."""


class UsageError(PushError):
    """An argument combination the tool cannot run with; printed, and the run exits 2."""


@dataclass(frozen=True)
class Plan:
    target: str
    region: str
    worker: str
    bucket: str
    jurisdiction: str
    host: str
    config: str


def _config_binding(config_path) -> tuple[str, str, str]:
    """(Worker name, backup bucket, its jurisdiction) from one wrangler config."""
    with open(config_path, "rb") as fh:
        doc = tomllib.load(fh)
    for bucket in doc.get("r2_buckets") or []:
        if bucket.get("binding") == BUCKET_BINDING:
            return (
                doc.get("name") or "",
                bucket.get("bucket_name") or "",
                bucket.get("jurisdiction") or "",
            )
    raise PushError("%s binds no %s bucket" % (config_path, BUCKET_BINDING))


def plan(target: str, region: str | None, root=None) -> Plan:
    """The Worker, bucket, jurisdiction, host and config for one push. UsageError on an argument combination that names no Worker; PushError on a mismatch between regions.json and the Worker's own wrangler config, which is a refusal."""
    root = paths.repo_root() if root is None else root
    worker_dir = root.joinpath(*WORKER_DIR)
    if target == "bench":
        if region:
            raise UsageError("bench has one Worker and no regions; drop --region")
        config = BENCH_CONFIG
        worker, bucket, jurisdiction = _config_binding(worker_dir / config)
        host = portal_health.hosts("bench", None)[0]
        if not worker or not bucket:
            raise PushError("%s names no Worker or no backup bucket" % config)
        return Plan(target, "", worker, bucket, jurisdiction, host, config)
    if not region:
        raise UsageError("--target %s needs --region (one Worker per run)" % target)
    with open(root / "regions.json", encoding="utf-8") as fh:
        regions = {r["id"]: r for r in json.load(fh)["regions"]}
    if region not in regions:
        raise UsageError("unknown region %r (regions.json has %s)" % (region, ", ".join(regions)))
    entry = regions[region]
    if target == "stable":
        worker, bucket, host = entry["workerName"], entry["backupR2"]["name"], entry["domain"]
        config = "wrangler.%s.toml" % region
    else:
        worker, bucket, host = (
            entry["edgeWorkerName"],
            entry["edgeBackupR2"]["name"],
            entry["edgeDomain"],
        )
        config = "wrangler.edge-%s.toml" % region
    jurisdiction = entry.get("r2Jurisdiction") or ""
    bound_worker, bound_bucket, bound_jurisdiction = _config_binding(worker_dir / config)
    if (bound_worker, bound_bucket, bound_jurisdiction) != (worker, bucket, jurisdiction):
        raise PushError(
            "regions.json and %s disagree: regions.json says Worker %s, bucket %s, jurisdiction %r; "
            "the config says Worker %s, bucket %s, jurisdiction %r. Fix the tree before pushing."
            % (config, worker, bucket, jurisdiction, bound_worker, bound_bucket, bound_jurisdiction)
        )
    return Plan(target, region, worker, bucket, jurisdiction, host, config)


def read_env() -> dict[str, str]:
    """The names this tool reads, one explicit `os.environ.get` per bound name so the env registry records each read (`.ci/config/python-env-registry.json`), plus the six suffixed names it refuses."""
    env = {
        "ACCOUNT_BACKUP_S3_ENDPOINT": os.environ.get("ACCOUNT_BACKUP_S3_ENDPOINT", ""),
        "ACCOUNT_BACKUP_S3_ACCESS_KEY_ID": os.environ.get("ACCOUNT_BACKUP_S3_ACCESS_KEY_ID", ""),
        "ACCOUNT_BACKUP_S3_SECRET_ACCESS_KEY": os.environ.get(
            "ACCOUNT_BACKUP_S3_SECRET_ACCESS_KEY", ""
        ),
    }
    for name in SUFFIXED:
        env[name] = os.environ.get(name, "")
    return env


def payload(p: Plan, environ: dict[str, str] | None = None) -> dict[str, str]:
    """The bulk document. PushError naming each missing value, and naming any suffixed pair name present."""
    environ = read_env() if environ is None else environ
    stray = [name for name in SUFFIXED if environ.get(name)]
    if stray:
        raise PushError(
            "refusing: %s %s in the environment. Under the backup-push-%s profile only the "
            "unsuffixed pair is bound, so a suffixed name here is a second environment's key."
            % (", ".join(stray), "is" if len(stray) == 1 else "are", p.target)
        )
    missing = [name for name in BOUND if not environ.get(name)]
    if missing:
        raise PushError(
            "refusing: %s %s EMPTY. The backup-push-%s profile binds them "
            "(.ci/config/secret-supply.json)."
            % (", ".join(missing), "is" if len(missing) == 1 else "are", p.target)
        )
    return {
        "ACCOUNT_BACKUP_S3_ENDPOINT": set_account_worker_secrets.apply_jurisdiction(
            environ["ACCOUNT_BACKUP_S3_ENDPOINT"], p.jurisdiction
        ),
        "ACCOUNT_BACKUP_S3_BUCKET": p.bucket,
        "ACCOUNT_BACKUP_S3_ACCESS_KEY_ID": environ["ACCOUNT_BACKUP_S3_ACCESS_KEY_ID"],
        "ACCOUNT_BACKUP_S3_SECRET_ACCESS_KEY": environ["ACCOUNT_BACKUP_S3_SECRET_ACCESS_KEY"],
    }


def list_argv(worker: str) -> list[str]:
    return [*wrangler.ARGV, "secret", "list", "--name", worker, "--format", "json"]


def bulk_argv(worker: str) -> list[str]:
    """The sibling deploy script's own bulk call, so the two cannot drift apart."""
    return set_account_worker_secrets.wrangler_argv(worker)


def _rows(stdout: str) -> list | None:
    """The first non-empty JSON array of objects in `stdout`, decoded from the first `[` at which one parses; an empty array only when no other is printed. A bracketed log line (`[WARNING] ...`) before it, or text after it, does not parse as one and is skipped."""
    decoder = json.JSONDecoder()
    empty: list | None = None
    start = stdout.find("[")
    while start >= 0:
        try:
            rows, end = decoder.raw_decode(stdout, start)
        except ValueError:
            start = stdout.find("[", start + 1)
            continue
        if isinstance(rows, list) and all(isinstance(row, dict) for row in rows):
            if rows:
                return rows
            empty = rows
        start = stdout.find("[", end)
    return empty


def secret_names(stdout: str) -> list[str]:
    """The names in `wrangler secret list --format json` output: a JSON array of {name, type}. Anything printed around the array is ignored, bracketed log lines included; no array is a PushError."""
    rows = _rows(stdout)
    if rows is None:
        raise PushError("wrangler secret list printed no JSON array of secrets")
    return sorted(str(row.get("name")) for row in rows if row.get("name"))


def _mask(text: str, values: list[str]) -> str:
    for value in sorted({v for v in values if v}, key=len, reverse=True):
        text = text.replace(value, MASK)
    return text


def default_runner(argv: list[str], cwd: str, stdin: str | None) -> tuple[int, str, str]:
    """Run one wrangler call with the backup values REMOVED from its environment; the bulk document on stdin is where they travel."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("ACCOUNT_BACKUP_S3_")}
    proc = subprocess.run(
        argv, cwd=cwd, env=env, input=stdin, capture_output=True, text=True, check=False
    )
    return proc.returncode, proc.stdout, proc.stderr


def _list(p: Plan, cwd: str, runner: Runner, when: str) -> list[str]:
    rc, out, err = runner(list_argv(p.worker), cwd, None)
    if rc != 0:
        tail = (err.strip().splitlines() or ["(no output)"])[-1]
        raise PushError("wrangler secret list %s failed (exit %d): %s" % (when, rc, tail))
    names = secret_names(out)
    if not names:
        raise PushError("wrangler secret list %s returned no secret for %s" % (when, p.worker))
    return names


def _health(p: Plan, fetch, out, when: str) -> int:
    print("--- portal health %s the push: %s" % (when, p.host), file=out, flush=True)
    region = p.region or None
    return portal_health.run(p.target, region, fetch=fetch, out=out)


def push(
    p: Plan,
    *,
    dry_run: bool,
    runner: Runner = default_runner,
    fetch=portal_health.http_get,
    environ=None,
    out=None,
) -> int:
    """Steps 3 to 8 of the module docstring for one resolved Worker. Returns the exit status; prints names, never values."""
    out = sys.stdout if out is None else out
    cwd = str(paths.repo_root().joinpath(*WORKER_DIR))
    print(
        "push backup credentials: target %s, Worker %s, bucket %s%s, host %s"
        % (
            p.target,
            p.worker,
            p.bucket,
            (" (%s)" % p.jurisdiction) if p.jurisdiction else "",
            p.host,
        ),
        file=out,
        flush=True,
    )
    print("  secrets: %s" % ", ".join(PUSHED), file=out, flush=True)
    document = payload(p, environ)
    if _health(p, fetch, out, "before") != 0:
        raise PushError("the portal is RED before the push; refusing to write to %s" % p.worker)
    before = _list(p, cwd, runner, "before the push")
    print("  %d secret name(s) before" % len(before), file=out, flush=True)
    absent = [name for name in PUSHED if name not in before]
    if absent:
        raise PushError(
            "%s has no %s; this tool replaces values and never adds a secret (a deploy adds them)"
            % (p.worker, ", ".join(absent))
        )
    if dry_run:
        print("dry run: would run, in %s:" % cwd, file=out)
        print(
            "  %s   (stdin: a JSON object with the %d names above)"
            % (" ".join(bulk_argv(p.worker)), len(PUSHED)),
            file=out,
        )
        print("  %s" % " ".join(list_argv(p.worker)), file=out)
        print(
            "  PYTHONPATH=.ci python3 -m rediacc_ci.ops.portal_health --target %s%s"
            % (p.target, (" --region %s" % p.region) if p.region else ""),
            file=out,
        )
        print("dry run: nothing written", file=out, flush=True)
        return 0
    rc, bulk_out, bulk_err = runner(bulk_argv(p.worker), cwd, json.dumps(document))
    secrets = list(document.values())
    for line in (_mask(bulk_out, secrets) + _mask(bulk_err, secrets)).splitlines():
        print("  wrangler: %s" % line, file=out)
    if rc != 0:
        raise PushError("wrangler secret bulk failed (exit %d) for %s" % (rc, p.worker))
    after = _list(p, cwd, runner, "after the push")
    if after != before:
        added = sorted(set(after) - set(before))
        removed = sorted(set(before) - set(after))
        raise PushError(
            "the secret names of %s CHANGED: added %s, removed %s. The push only overwrites four "
            "existing secrets, so inspect the Worker now."
            % (p.worker, ", ".join(added) or "none", ", ".join(removed) or "none")
        )
    print("  %d secret name(s) after, unchanged" % len(after), file=out, flush=True)
    if _health(p, fetch, out, "after") != 0:
        raise PushError(
            "the portal is RED AFTER the push to %s. Roll back by pushing the previous pair to this Worker "
            "(the shared token stays valid until it is revoked), then investigate." % p.worker
        )
    print("push backup credentials: done, %s" % p.worker, file=out, flush=True)
    return 0


def _reexec_under_profile(target: str, argv: list[str]) -> int | None:
    """Run the same entry point under `backup-push-<target>` and return its exit status; None when already bound."""
    profile = PROFILE_PREFIX + target
    if profile in (os.environ.get("REDIACC_BWS_PROFILES") or "").split(","):
        return None
    env = dict(os.environ)
    ci = str(paths.repo_root() / ".ci")
    env["PYTHONPATH"] = ci + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "rediacc_ci.core.bws_env",
            "exec",
            "--profile",
            profile,
            "--",
            sys.executable,
            "-m",
            "rediacc_ci.ops.push_backup_credentials",
            *argv,
        ],
        env=env,
        check=False,
    ).returncode


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rediacc_ci.ops.push_backup_credentials",
        description=(__doc__ or "").splitlines()[0],
    )
    parser.add_argument("--target", required=True, choices=TARGETS)
    parser.add_argument("--region", default=None, help="one regions.json id (stable and edge)")
    parser.add_argument(
        "--dry-run", action="store_true", help="read-only steps only; write nothing"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    args = build_parser().parse_args(argv)
    try:
        resolved = plan(args.target, args.region)
    except UsageError as exc:
        print("push backup credentials: %s" % exc, file=sys.stderr)
        return 2
    except PushError as exc:
        for line in str(exc).splitlines():
            print("push backup credentials: %s" % line, file=sys.stderr)
        return 1
    rebound = _reexec_under_profile(args.target, argv)
    if rebound is not None:
        return rebound
    try:
        return push(resolved, dry_run=args.dry_run)
    except PushError as exc:
        for line in str(exc).splitlines():
            print("push backup credentials: %s" % line, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
