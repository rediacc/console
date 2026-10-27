#!/usr/bin/env python3
"""The deploy record of one target's account-plus-proxy release, and the steps that read it (agent/plans/PLAN-proxy-cd-six-targets.md, Design item 9, box D2).

    PYTHONPATH=.ci python3 -m rediacc_ci.deploy.deploy_record before    --target T --region R --version V --out BEFORE.json
    PYTHONPATH=.ci python3 -m rediacc_ci.deploy.deploy_record bootstrap --before BEFORE.json --record PROXY-BOOTSTRAP.json
    PYTHONPATH=.ci python3 -m rediacc_ci.deploy.deploy_record rollback  --before BEFORE.json
    PYTHONPATH=.ci python3 -m rediacc_ci.deploy.deploy_record after     --before BEFORE.json --proxy-record PROXY.json --manifest workers/proxy/stage/manifest.json
                                                                        --enable-outcome O --rollback-outcome O --out RECORD.json

CD runs the four verbs inside the per-region deploy job of .github/workflows/cd-deploy-account.yml, in this order: `before`, then (only when the proxy Worker does not exist yet) `bootstrap`, then the account deploy, the Worker secrets, `deploy_proxy`, its `--smoke-only` and `console_executor --enable`; `rollback` on failure; `after` always.

BEFORE, TAKEN BEFORE THE MIGRATIONS. `deploy_account` applies the D1 migrations and then deploys, so the bookmark must exist before it runs: a Worker rollback does not undo a migration, and the bookmark is the only rollback handle for one. `before` records:
  - the account Worker's name and its 100% version (`wrangler deployments list --json`), or none when it has never been deployed;
  - the D1 database and its time-travel bookmark (`wrangler d1 time-travel info <db> --json`);
  - the proxy Worker's name, whether it exists, and its 100% version;
  - the release version the proxy last passed its smoke on, from the pointer `executor-deployments/<target>-<region>.json` in the releases bucket (written by `after`), which is what `rollback` redeploys;
  - the executor manifest sha256s of `executor/v<V>/manifest.json`, the bytes this deploy will build from.
Every one of those is either a value or a stated absence. A lookup that FAILED (wrangler errored without saying the Worker does not exist, the bookmark did not parse, R2 answered anything but NoSuchKey, the version is not staged) is unknown, and unknown exits 1 before anything is deployed. `before` also appends `proxy_exists=true|false` to `$GITHUB_OUTPUT`, which is the bootstrap step's condition.

BOOTSTRAP (U1). An account config binds EXECUTOR to its own target's proxy Worker, and wrangler refuses to deploy a Worker whose `[[services]]` names a Worker that does not exist. The first deploy of a target therefore deploys the proxy first, against the account Worker that is live before this release. That Worker may not export ExecutorIssuer yet, so the proxy's `/v1/ready` smoke can fail on bootstrap: `bootstrap` accepts a non-zero `deploy_proxy` exit only when its record names a deployed version id (the Worker exists, which is all the account deploy needs), and refuses otherwise. The real deploy and smoke follow after the account deploy.

ROLLBACK, IN REVERSE ORDER. (1) `console_executor --disable`, so the region refuses rather than serves a broken executor. (2) The proxy: when its live version is still the one `before` recorded, nothing changed and nothing is redeployed; when `before` recorded no proxy at all, this was a first deploy and there is nothing to return to; otherwise `deploy_proxy --version <the release the pointer names>` redeploys the previous release from its own executor artifacts, because Cloudflare documents no container rollback. With no pointer the Worker-only `wrangler rollback` command is printed for a human. (3) The account Worker rollback and the D1 restore commands are PRINTED, never run: both are destructive enough to stay human decisions.

AFTER. The full record, `deploy-record-<target>-<region>.json`: worker names, version ids before and after, the D1 bookmark, the smoke rc, the enable and rollback outcomes, the executor manifest sha256s and every rollback command. It is printed, appended to `$GITHUB_STEP_SUMMARY` and uploaded by the workflow. When the smoke passed, the executor was enabled and no rollback ran, `after` writes the pointer, so the next release's `rollback` knows which release to return to.

DURABLE SINK (`after --sink r2 --channel edge|stable`, plan local-release W2-D). The record is also written to the releases bucket at `release-records/v<V>/<channel>/deploy-record-<target>-<region>.json`, ONCE: an existing key refuses, so a record is never overwritten (`write_record_once`). `write_once_guard` itself is the SENTINEL guard of a `cli/v<V>/` prefix and cannot answer for a single key, so the once check is the same absent-only probe it uses, `executor_artifacts.get_object`. The account smoke rc (`--account-smoke-rc`) is stored at `account.smoke_rc`.

WWW RECORD (`www-after`). `deploy_www` and `deploy_edge` take the version id before and after through `take_www_before` / `build_www_record` when `DEPLOY_RECORD_OUT` names a file (the record carries `smoke_rc: null`); `www-after --record F --smoke-rc N [--sink r2 --channel C]` fills the smoke rc, and writes the same key family with target `www-<channel>` and region `global`. No record holds a secret value: `refuse_secret_values` checks the serialized record against the secret-named variables of the environment before it is written.

ENVIRONMENT. `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`, and for R2 `CLOUDFLARE_R2_ENDPOINT` plus `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY`: the names of the `deploy-proxy` profile in .ci/config/secret-supply.json.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile
import tomllib
import typing

from rediacc_ci import log, paths
from rediacc_ci.core import awscli
from rediacc_ci.deploy import console_executor, deploy_proxy, executor_artifacts

SELF = "rediacc_ci.deploy.deploy_record"
SCHEMA = 1

ACCOUNT_SUBDIR = ("workers", "account")
PROXY_SUBDIR = ("workers", "proxy")
ACCOUNT_REL = "/".join(ACCOUNT_SUBDIR)
PROXY_REL = "/".join(PROXY_SUBDIR)

# The last release each target's proxy passed its smoke on, outside `executor/` so executor_artifacts' version listing never sees it.
POINTER_PREFIX = "executor-deployments/"

VERSION_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")

# wrangler's answer for a Worker that has never been deployed (`This Worker does not exist on your account. [code: 10007]`).
WORKER_ABSENT_RE = re.compile(r"\[code: 10007\]|does not exist on your account|script_not_found")

# A D1 bookmark as `wrangler d1 time-travel info` prints it: three 8-hex groups and a long hex tail.
BOOKMARK_RE = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{8}-[0-9a-f]{8}-[0-9a-f]{16,}\b")

OUTCOMES = ("success", "failure", "cancelled", "skipped", "")


class RecordError(Exception):
    """A lookup that failed: unknown, and the run exits 1."""


# ---- naming -----------------------------------------------------------------


def check_target(target: str, region: str) -> None:
    if target not in console_executor.TARGETS:
        raise RecordError(
            "--target %s is not one of %s" % (target, ", ".join(console_executor.TARGETS))
        )
    if target == console_executor.BENCH_TARGET and region != console_executor.BENCH_REGION:
        raise RecordError("--target bench refuses --region %s" % region)


def account_config(target: str, region: str) -> str:
    return console_executor.account_config(target, region)


def proxy_config(target: str, region: str) -> str:
    return deploy_proxy.config_name(target, region)


def read_toml(path: pathlib.Path) -> dict:
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise RecordError("%s cannot be read: %s" % (path, exc)) from None


def worker_name(doc: dict, path: pathlib.Path) -> str:
    name = doc.get("name")
    if not isinstance(name, str) or not name:
        raise RecordError("%s has no top-level `name`" % path)
    return name


def database_name(doc: dict, path: pathlib.Path) -> str:
    """The first `[[d1_databases]]` entry's `database_name`, the database `deploy_account` migrates."""
    for entry in doc.get("d1_databases") or []:
        if isinstance(entry, dict) and isinstance(entry.get("database_name"), str):
            return entry["database_name"]
    raise RecordError("%s has no [[d1_databases]] database_name" % path)


def pointer_key(target: str, region: str) -> str:
    return "%s%s-%s.json" % (POINTER_PREFIX, target, region)


# ---- wrangler ---------------------------------------------------------------


def deployments_argv(config: str) -> list[str]:
    return ["npx", "wrangler", "deployments", "list", "--json", "--config", config]


def time_travel_argv(database: str, config: str) -> list[str]:
    return ["npx", "wrangler", "d1", "time-travel", "info", database, "--json", "--config", config]


def _capture(argv: list[str], cwd: pathlib.Path) -> tuple[int, str, str]:
    proc = subprocess.run(
        argv, cwd=cwd, stdin=subprocess.DEVNULL, capture_output=True, text=True, check=False
    )
    return proc.returncode, proc.stdout, proc.stderr


def _json_span(text: str, open_ch: str, close_ch: str) -> object:
    """The JSON value from the first `open_ch` to the last `close_ch`, so a banner wrangler prints ahead of it does not hide it; None when absent or malformed."""
    start, end = text.find(open_ch), text.rfind(close_ch)
    if start < 0 or end < start:
        return None
    try:
        return json.loads(text[start : end + 1])
    except ValueError:
        return None


def parse_deployed_version(text: str) -> tuple[bool, str | None]:
    """(parsed, version) of a `wrangler deployments list --json` answer: the newest deployment's 100% version.

    An empty list parses to (True, None). A newest deployment split across versions (a gradual rollout) has no single version, and that is not parsed: the version is unknown.
    """
    data = _json_span(text, "[", "]")
    if not isinstance(data, list):
        return False, None
    if not data:
        return True, None
    version = deploy_proxy.newest_deployment_version(json.dumps(data))
    return (version is not None), version


def worker_version(cwd: pathlib.Path, config: str, worker: str) -> tuple[bool, str | None]:
    """(exists, 100% version id) of one Worker. Refuses (unknown) unless wrangler answered a list or said the Worker does not exist."""
    status, out, err = _capture(deployments_argv(config), cwd)
    if status == 0:
        parsed, version = parse_deployed_version(out)
        if parsed:
            # A Worker with an empty deployments list holds no deployed version: it did not exist before this deploy.
            return version is not None, version
        raise RecordError(
            "wrangler deployments list for %s answered no single 100%% version: %s"
            % (worker, (out.strip() or "(empty)")[:300])
        )
    if WORKER_ABSENT_RE.search(out + err):
        return False, None
    raise RecordError(
        "wrangler deployments list for %s exited %d without saying the Worker does not exist: %s"
        % (worker, status, ((err or out).strip().splitlines() or ["(no output)"])[-1])
    )


def parse_bookmark(text: str) -> str | None:
    data = _json_span(text, "{", "}")
    if isinstance(data, dict) and isinstance(data.get("bookmark"), str) and data["bookmark"]:
        return data["bookmark"]
    found = BOOKMARK_RE.search(text)
    return found.group(0) if found else None


def d1_bookmark(cwd: pathlib.Path, database: str, config: str) -> str:
    status, out, err = _capture(time_travel_argv(database, config), cwd)
    bookmark = parse_bookmark(out) if status == 0 else None
    if not bookmark:
        raise RecordError(
            "NO D1 BOOKMARK for %s (wrangler d1 time-travel info exited %d%s): the migrations would run with no restore point, so nothing is deployed"
            % (database, status, "; " + err.strip().splitlines()[-1] if err.strip() else "")
        )
    return bookmark


def restore_command(database: str, bookmark: str, config: str) -> str:
    return "npx wrangler d1 time-travel restore %s --bookmark=%s --config %s/%s" % (
        database,
        bookmark,
        ACCOUNT_REL,
        config,
    )


def worker_rollback_command(version_id: str | None, rel: str, config: str) -> str:
    if not version_id:
        return "none: no earlier deployment of this Worker exists"
    return "npx wrangler rollback %s --config %s/%s" % (version_id, rel, config)


def proxy_redeploy_command(target: str, region: str, release: str) -> str:
    return "PYTHONPATH=.ci python3 -m %s --target %s --region %s --version %s" % (
        deploy_proxy.SELF,
        target,
        region,
        release,
    )


def executor_off_command(target: str, region: str) -> str:
    return "PYTHONPATH=.ci python3 -m %s --disable --target %s --region %s" % (
        console_executor.SELF,
        target,
        region,
    )


# ---- R2 ---------------------------------------------------------------------


def read_json_object(key: str) -> dict | None:
    """One JSON object from the releases bucket; None for NoSuchKey. Any other failure is unknown."""
    with tempfile.TemporaryDirectory(prefix="deploy-record-") as tmp:
        dest = pathlib.Path(tmp) / "object.json"
        try:
            found = executor_artifacts.get_object(key, dest)
        except executor_artifacts.ArtifactError as exc:
            raise RecordError(str(exc)) from None
        if not found:
            return None
        try:
            data = json.loads(dest.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise RecordError("%s is not JSON: %s" % (key, exc)) from None
    if not isinstance(data, dict):
        raise RecordError("%s is not a JSON object" % key)
    return data


def write_pointer(target: str, region: str, pointer: dict) -> None:
    """`executor-deployments/<target>-<region>.json`, overwritten on each good deploy (so not cached)."""
    with tempfile.TemporaryDirectory(prefix="deploy-record-") as tmp:
        body = pathlib.Path(tmp) / "pointer.json"
        body.write_text(json.dumps(pointer, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        argv = [
            awscli.AWS,
            "s3api",
            "put-object",
            "--key",
            pointer_key(target, region),
            "--body",
            str(body),
            "--content-type",
            "application/json",
            "--cache-control",
            "no-store",
            "--bucket",
            executor_artifacts.BUCKET,
            "--endpoint-url",
            executor_artifacts.endpoint(),
        ]
        proc = awscli.run(argv, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    if proc.returncode != 0:
        raise RecordError(
            "aws put-object %s failed (rc %d): %s"
            % (
                pointer_key(target, region),
                proc.returncode,
                proc.stderr.decode("utf-8", "replace").strip(),
            )
        )


# ---- the durable sink --------------------------------------------------------

RECORD_PREFIX = "release-records/"
CHANNELS = ("edge", "stable")
SINKS = ("r2",)
WWW_REGION = "global"
SECRET_NAME_RE = re.compile(
    r"TOKEN|SECRET|PASSWORD|PASSPHRASE|PRIVATE|ACCESS_KEY|_KEY$", re.IGNORECASE
)


def record_key(version: str, channel: str, target: str, region: str) -> str:
    return "%sv%s/%s/deploy-record-%s-%s.json" % (RECORD_PREFIX, version, channel, target, region)


def _string_leaves(node: object) -> typing.Iterator[str]:
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for key, value in node.items():
            yield str(key)
            yield from _string_leaves(value)
    elif isinstance(node, (list, tuple)):
        for item in node:
            yield from _string_leaves(item)
    elif node is not None:
        # A number or boolean: its text is what a secret of digits would equal.
        yield str(node)


def refuse_secret_values(record: dict) -> None:
    """A record that carries the value of a secret-named variable is never emitted. Every key and leaf, through dicts, lists and tuples, is compared on its decoded text (numbers and booleans through `str`), and the serialized body is compared on the json-escaped form too, so quotes, backslashes, control characters and non-ASCII text cannot hide a value.

    The raw value is not searched in the body: a value that sits inside a key or leaf is already caught on the decoded text, and one that only matches the JSON punctuation between them is no leak.
    """
    leaves = list(_string_leaves(record))
    body = json.dumps(record)
    for name, value in os.environ.items():
        if len(value) < 8 or not SECRET_NAME_RE.search(name):
            continue
        escaped = json.dumps(value)[1:-1]
        if any(value in leaf for leaf in leaves) or escaped in body:
            raise RecordError("the record carries the value of %s; nothing is emitted" % name)


def write_record_once(record: dict, key: str) -> None:
    """Put the record at `key` with a conditional put (`If-None-Match: *`), so a concurrent writer cannot overwrite it. An existing key (412 PreconditionFailed) refuses, and so does any other failure."""
    refuse_secret_values(record)
    with tempfile.TemporaryDirectory(prefix="deploy-record-") as tmp:
        body = pathlib.Path(tmp) / "record.json"
        body.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        try:
            argv = [
                awscli.AWS,
                "s3api",
                "put-object",
                "--key",
                key,
                "--body",
                str(body),
                "--content-type",
                "application/json",
                "--cache-control",
                "public, max-age=31536000, immutable",
                "--if-none-match",
                "*",
                "--bucket",
                executor_artifacts.BUCKET,
                "--endpoint-url",
                executor_artifacts.endpoint(),
            ]
        except executor_artifacts.ArtifactError as exc:
            raise RecordError(str(exc)) from None
        try:
            proc = awscli.run(argv, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        except OSError as exc:
            raise RecordError("aws put-object %s could not run: %s" % (key, exc)) from None
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", "replace").strip()
        if "PreconditionFailed" in err or "(412)" in err:
            raise RecordError("%s already exists: a deploy record is written once" % key)
        raise RecordError("aws put-object %s failed (rc %d): %s" % (key, proc.returncode, err))
    log.info("Deploy record written once to %s." % key)


def sink_record(record: dict, sink: str, channel: str, target: str, region: str) -> None:
    if sink != "r2":
        raise RecordError("--sink %s is not one of %s" % (sink, ", ".join(SINKS)))
    if channel not in CHANNELS:
        raise RecordError("--sink r2 needs --channel %s" % " or ".join(CHANNELS))
    write_record_once(record, record_key(record["version"], channel, target, region))


# ---- the www record -----------------------------------------------------------


def take_www_before(cwd: pathlib.Path, config: str) -> dict:
    """The www Worker's name and its 100% version before a deploy (a stated absence or a refusal)."""
    path = cwd / config
    worker = worker_name(read_toml(path), path)
    exists, version = worker_version(cwd, config, worker)
    return {"worker": worker, "config": config, "exists": exists, "version_before": version}


def build_www_record(
    before: dict,
    version_after: str | None,
    release_version: str,
    target: str,
    deploy_rc: int,
    after_error: str | None = None,
) -> dict:
    """The www record: version ids before and after, the rollback command and the smoke rc (`None` until `www-after`)."""
    return {
        "schema": SCHEMA,
        "kind": "www",
        "target": target,
        "region": WWW_REGION,
        "version": release_version,
        "phase": "after",
        "recorded_at": now(),
        "worker": before["worker"],
        "version_before": before["version_before"],
        "version_after": version_after,
        "version_after_error": after_error,
        "deploy_rc": deploy_rc,
        "smoke_rc": None,
        "rollback_command": worker_rollback_command(
            before["version_before"], "workers/www", before["config"]
        ),
    }


def record_www_deploy(
    cwd: pathlib.Path, config: str, target: str, deploy_rc_fn: typing.Callable[[], int]
) -> int:
    """Bracket one www deploy with its record. Inactive (just the deploy) unless `DEPLOY_RECORD_OUT` and `DEPLOY_RECORD_VERSION` are set; a lookup that fails refuses before anything is deployed."""
    out = os.environ.get("DEPLOY_RECORD_OUT", "")
    release = os.environ.get("DEPLOY_RECORD_VERSION", "")
    if not out:
        return deploy_rc_fn()
    try:
        if not VERSION_RE.match(release):
            raise RecordError("DEPLOY_RECORD_VERSION %r is not X.Y.Z" % release)
        before = take_www_before(cwd, config)
    except RecordError as exc:
        log.error("%s www record: %s" % (SELF, exc))
        return 1
    rc = deploy_rc_fn()
    try:
        _, after = worker_version(cwd, config, before["worker"])
    except RecordError as exc:
        log.error("%s www record: the version after is unknown: %s" % (SELF, exc))
        after, after_error = None, str(exc)
    else:
        after_error = None
    record = build_www_record(before, after, release, target, rc, after_error)
    try:
        refuse_secret_values(record)
    except RecordError as exc:
        log.error("%s www record: %s" % (SELF, exc))
        return rc or 1
    write_json(pathlib.Path(out), record)
    return rc


def manifest_sha256s(manifest: dict, version: str) -> dict[str, str]:
    files = executor_artifacts.parse_manifest(json.dumps(manifest), version)
    return {name: str(entry["sha256"]) for name, entry in sorted(files.items())}


# ---- before -----------------------------------------------------------------


def take_before(repo_root: pathlib.Path, target: str, region: str, version: str) -> dict:
    """The record taken before anything is deployed. Raises RecordError on any unknown."""
    check_target(target, region)
    if not VERSION_RE.match(version):
        raise RecordError("--version %r is not a release version (X.Y.Z)" % version)
    account_dir = repo_root.joinpath(*ACCOUNT_SUBDIR)
    proxy_dir = repo_root.joinpath(*PROXY_SUBDIR)
    acfg = account_config(target, region)
    pcfg = proxy_config(target, region)
    adoc = read_toml(account_dir / acfg)
    pdoc = read_toml(proxy_dir / pcfg)
    account = worker_name(adoc, account_dir / acfg)
    proxy = worker_name(pdoc, proxy_dir / pcfg)
    database = database_name(adoc, account_dir / acfg)

    _, account_version = worker_version(account_dir, acfg, account)
    bookmark = d1_bookmark(account_dir, database, acfg)
    proxy_exists, proxy_version = worker_version(proxy_dir, pcfg, proxy)

    try:
        pointer = read_json_object(pointer_key(target, region))
        manifest = read_json_object(
            executor_artifacts.key_for(version, executor_artifacts.MANIFEST)
        )
        if manifest is None:
            raise RecordError(
                "executor artifacts v%s are not staged (no %s): the proxy cannot be built, so nothing is deployed"
                % (version, executor_artifacts.key_for(version, executor_artifacts.MANIFEST))
            )
        sha256s = manifest_sha256s(manifest, version)
    except executor_artifacts.ArtifactError as exc:
        raise RecordError(str(exc)) from None
    previous_release = None
    if pointer is not None:
        previous_release = pointer.get("release_version")
        if not isinstance(previous_release, str) or not VERSION_RE.match(previous_release):
            raise RecordError(
                "%s names no release version (%r)" % (pointer_key(target, region), previous_release)
            )

    return {
        "schema": SCHEMA,
        "phase": "before",
        "taken_at": now(),
        "target": target,
        "region": region,
        "version": version,
        "account": {
            "worker": account,
            "config": "%s/%s" % (ACCOUNT_REL, acfg),
            "version_before": account_version,
        },
        "d1": {"database": database, "bookmark": bookmark},
        "proxy": {
            "worker": proxy,
            "config": "%s/%s" % (PROXY_REL, pcfg),
            "existed": proxy_exists,
            "version_before": proxy_version,
            "release_before": previous_release,
        },
        "executor_manifest": {"version": version, "sha256": sha256s},
        "rollback": rollback_commands(
            target,
            region,
            acfg,
            pcfg,
            account_version,
            database,
            bookmark,
            proxy_version,
            previous_release,
        ),
    }


def rollback_commands(
    target: str,
    region: str,
    acfg: str,
    pcfg: str,
    account_version: str | None,
    database: str,
    bookmark: str,
    proxy_version: str | None,
    previous_release: str | None,
) -> dict[str, str]:
    """Every rollback command, in the order a rollback runs them."""
    if not proxy_version:
        proxy_cmd = "none: the proxy Worker did not exist before this deploy"
    elif previous_release:
        proxy_cmd = proxy_redeploy_command(target, region, previous_release)
    else:
        proxy_cmd = worker_rollback_command(proxy_version, PROXY_REL, pcfg) + (
            "  (Worker script only: no release is on record for this proxy, so its image cannot be rebuilt from artifacts)"
        )
    return {
        "1_console_executor": executor_off_command(target, region),
        "2_proxy": proxy_cmd,
        "3_account": worker_rollback_command(account_version, ACCOUNT_REL, acfg),
        "4_d1": restore_command(database, bookmark, acfg),
    }


def now() -> str:
    return datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def write_json(path: pathlib.Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_json(path: pathlib.Path, what: str) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RecordError("%s %s cannot be read: %s" % (what, path, exc)) from None
    if not isinstance(data, dict):
        raise RecordError("%s %s is not a JSON object" % (what, path))
    return data


def github_output(pairs: dict[str, str]) -> None:
    target = os.environ.get("GITHUB_OUTPUT")
    if not target:
        return
    with open(target, "a", encoding="utf-8") as fh:
        fh.writelines("%s=%s\n" % (key, value) for key, value in pairs.items())


def cmd_before(args: argparse.Namespace, repo_root: pathlib.Path) -> int:
    record = take_before(repo_root, args.target, args.region, args.version)
    write_json(pathlib.Path(args.out), record)
    exists = "true" if record["proxy"]["existed"] else "false"
    github_output({"proxy_exists": exists})
    proxy = record["proxy"]
    log.info(
        "Before: account %s at %s; D1 %s bookmark %s; proxy %s %s; last good proxy release %s; executor v%s staged (%d files)."
        % (
            record["account"]["worker"],
            record["account"]["version_before"] or "(never deployed)",
            record["d1"]["database"],
            record["d1"]["bookmark"],
            proxy["worker"],
            "at %s" % proxy["version_before"]
            if proxy["existed"]
            else "DOES NOT EXIST (bootstrap deploy follows)",
            proxy["release_before"] or "(none on record)",
            record["version"],
            len(record["executor_manifest"]["sha256"]),
        )
    )
    print("  restore D1: %s" % record["rollback"]["4_d1"])
    return 0


# ---- bootstrap --------------------------------------------------------------


def deploy_proxy_argv(*args: str) -> list[str]:
    """`python3 -m rediacc_ci.deploy.deploy_proxy ...` (the test driver swaps this for a recording fake)."""
    return [sys.executable, "-m", deploy_proxy.SELF, *args]


def _run_child(argv: list[str]) -> int:
    return subprocess.run(argv, env=deploy_proxy.package_env(), check=False).returncode


def cmd_bootstrap(args: argparse.Namespace, repo_root: pathlib.Path) -> int:
    del repo_root
    before = read_json(pathlib.Path(args.before), "the before record")
    if before["proxy"]["existed"]:
        log.error(
            "bootstrap refused: the before record says %s already exists; the regular proxy deploy covers it"
            % before["proxy"]["worker"]
        )
        return 1
    record = pathlib.Path(args.record)
    record.unlink(missing_ok=True)
    log.step(
        "Bootstrap: %s does not exist yet, and the account config binds EXECUTOR to it, so it is deployed before the account Worker..."
        % before["proxy"]["worker"]
    )
    status = _run_child(
        deploy_proxy_argv(
            "--target",
            before["target"],
            "--region",
            before["region"],
            "--version",
            before["version"],
            "--record",
            str(record),
        )
    )
    if status == 0:
        log.info("Bootstrap deploy of %s passed, smoke included." % before["proxy"]["worker"])
        return 0
    landed = deploy_proxy.read_record_version(record)
    if landed:
        log.warn(
            "Bootstrap deploy of %s landed version %s but exited %d: the live account Worker predates ExecutorIssuer, so /v1/ready cannot pass yet. The Worker exists, which is all the account deploy needs; the real proxy deploy and smoke follow it."
            % (before["proxy"]["worker"], landed, status)
        )
        return 0
    log.error(
        "Bootstrap deploy of %s exited %d and recorded no deployed version: the account deploy would be refused for a missing service, so the job stops here"
        % (before["proxy"]["worker"], status)
    )
    return status


# ---- rollback ---------------------------------------------------------------


def cmd_rollback(args: argparse.Namespace, repo_root: pathlib.Path) -> int:
    before = read_json(pathlib.Path(args.before), "the before record")
    target, region = before["target"], before["region"]
    failures = []

    log.step("Rollback 1/4: closing the console executor of %s %s..." % (target, region))
    if console_executor.run("disable", target, region, repo_root) != 0:
        failures.append("the console executor could not be confirmed closed")

    log.step("Rollback 2/4: the proxy Worker %s..." % before["proxy"]["worker"])
    pcfg = before["proxy"]["config"].rsplit("/", 1)[-1]
    try:
        _, live = worker_version(repo_root.joinpath(*PROXY_SUBDIR), pcfg, before["proxy"]["worker"])
    except RecordError as exc:
        live = None
        failures.append("the live proxy version is unknown: %s" % exc)
    else:
        prior = before["proxy"]["version_before"]
        release = before["proxy"]["release_before"]
        if live == prior:
            log.info(
                "The proxy is still on %s, the version before this deploy; nothing to redeploy."
                % (prior or "(none)")
            )
        elif not prior:
            log.info(
                "The proxy did not exist before this deploy (first deploy, now at %s); there is no earlier version to return to, and the closed executor keeps the region refusing."
                % live
            )
        elif release:
            log.info(
                "The proxy moved from %s to %s; redeploying release v%s from its executor artifacts."
                % (prior, live, release)
            )
            status = _run_child(
                deploy_proxy_argv("--target", target, "--region", region, "--version", release)
            )
            if status != 0:
                failures.append("the redeploy of proxy release v%s exited %d" % (release, status))
        else:
            log.warn(
                "The proxy moved from %s to %s and no release is on record for %s, so its image cannot be rebuilt from artifacts. Worker-only rollback, for a human: %s"
                % (prior, live, prior, before["rollback"]["2_proxy"])
            )

    log.step("Rollback 3/4 and 4/4, printed and NOT run (destructive, human decisions):")
    print("  account Worker: %s" % before["rollback"]["3_account"])
    print("  D1 restore:     %s" % before["rollback"]["4_d1"])
    for failure in failures:
        log.error("Rollback incomplete: %s" % failure)
    return 1 if failures else 0


# ---- after ------------------------------------------------------------------


def build_record(
    before: dict,
    proxy_record: dict | None,
    stage_manifest: dict | None,
    account_after: str | None,
    account_known: bool,
    enable_outcome: str,
    rollback_outcome: str,
    account_smoke_rc: int | None = None,
) -> dict:
    proxy_record = proxy_record or {}
    smoke_rc = proxy_record.get("smoke_rc")
    record = json.loads(json.dumps(before))
    record["phase"] = "after"
    record["recorded_at"] = now()
    record["account"]["version_after"] = account_after if account_known else "UNKNOWN"
    record["account"]["smoke_rc"] = account_smoke_rc
    record["proxy"]["version_after"] = proxy_record.get("version_id")
    record["proxy"]["previous_version_id"] = proxy_record.get("previous_version_id")
    record["proxy"]["rollback_command"] = proxy_record.get("rollback")
    record["smoke_rc"] = smoke_rc
    record["console_executor"] = {
        "enable_outcome": enable_outcome or "not run",
        "rollback_outcome": rollback_outcome or "not run",
    }
    if stage_manifest is not None:
        record["executor_manifest"]["fetched_sha256"] = {
            name: str(entry.get("sha256"))
            for name, entry in sorted((stage_manifest.get("files") or {}).items())
            if isinstance(entry, dict)
        }
    record["good"] = (
        smoke_rc == 0 and enable_outcome == "success" and rollback_outcome in ("", "skipped")
    )
    return record


def summary_markdown(record: dict) -> str:
    acc, prx, d1 = record["account"], record["proxy"], record["d1"]
    rows = [
        (
            "account Worker",
            "%s: %s -> %s"
            % (
                acc["worker"],
                acc["version_before"] or "(none)",
                acc.get("version_after") or "(none)",
            ),
        ),
        (
            "proxy Worker",
            "%s: %s -> %s"
            % (
                prx["worker"],
                prx["version_before"] or "(none)",
                prx.get("version_after") or "(not deployed)",
            ),
        ),
        ("proxy release before", prx["release_before"] or "(none on record)"),
        ("D1 bookmark (before migrations)", "%s %s" % (d1["database"], d1["bookmark"])),
        ("account smoke rc", str(record["account"].get("smoke_rc"))),
        ("proxy smoke rc", str(record.get("smoke_rc"))),
        (
            "console executor",
            "enable %s, rollback %s"
            % (
                record["console_executor"]["enable_outcome"],
                record["console_executor"]["rollback_outcome"],
            ),
        ),
        (
            "executor v%s sha256" % record["version"],
            ", ".join(
                "%s %s" % (k, v[:12]) for k, v in record["executor_manifest"]["sha256"].items()
            ),
        ),
    ]
    lines = [
        "### Deploy record: %s %s (v%s)%s"
        % (
            record["target"],
            record["region"],
            record["version"],
            "" if record["good"] else " -- NOT GOOD",
        ),
        "",
        "| Field | Value |",
        "|---|---|",
        *("| %s | `%s` |" % (k, v) for k, v in rows),
        "",
        "Rollback, in order:",
        "",
        *(
            "%d. `%s`" % (i, cmd)
            for i, (_, cmd) in enumerate(sorted(record["rollback"].items()), start=1)
        ),
        "",
    ]
    return "\n".join(lines)


def cmd_after(args: argparse.Namespace, repo_root: pathlib.Path) -> int:
    before = read_json(pathlib.Path(args.before), "the before record")
    proxy_path = pathlib.Path(args.proxy_record)
    proxy_record = read_json(proxy_path, "the proxy record") if proxy_path.is_file() else None
    manifest_path = pathlib.Path(args.manifest)
    stage_manifest = (
        read_json(manifest_path, "the fetched manifest") if manifest_path.is_file() else None
    )
    problems = []
    acfg = before["account"]["config"].rsplit("/", 1)[-1]
    try:
        _, account_after = worker_version(
            repo_root.joinpath(*ACCOUNT_SUBDIR), acfg, before["account"]["worker"]
        )
        account_known = True
    except RecordError as exc:
        account_after, account_known = None, False
        problems.append("the account version after is unknown: %s" % exc)

    record = build_record(
        before,
        proxy_record,
        stage_manifest,
        account_after,
        account_known,
        args.enable_outcome,
        args.rollback_outcome,
        args.account_smoke_rc,
    )
    fetched = record["executor_manifest"].get("fetched_sha256")
    if fetched is not None and fetched != record["executor_manifest"]["sha256"]:
        problems.append(
            "the fetched executor manifest differs from the staged one the before record read"
        )
        record["good"] = False
    try:
        refuse_secret_values(record)
    except RecordError as exc:
        log.error("%s after: %s" % (SELF, exc))
        return 1
    write_json(pathlib.Path(args.out), record)
    if args.sink:
        try:
            sink_record(record, args.sink, args.channel, before["target"], before["region"])
        except RecordError as exc:
            problems.append("the record was not written to %s: %s" % (args.sink, exc))
    text = summary_markdown(record)
    print(text)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write(text + "\n")

    if record["good"] and not problems:
        try:
            write_pointer(
                before["target"],
                before["region"],
                {
                    "release_version": before["version"],
                    "version_id": record["proxy"]["version_after"],
                    "worker": before["proxy"]["worker"],
                    "recorded_at": record["recorded_at"],
                },
            )
            log.info(
                "Pointer %s now names v%s."
                % (pointer_key(before["target"], before["region"]), before["version"])
            )
        except (RecordError, executor_artifacts.ArtifactError) as exc:
            problems.append("the last-good pointer was not written: %s" % exc)
    for problem in problems:
        log.error(problem)
    return 1 if problems else 0


def cmd_www_after(args: argparse.Namespace, repo_root: pathlib.Path) -> int:
    del repo_root
    path = pathlib.Path(args.record)
    record = read_json(path, "the www record")
    record["smoke_rc"] = args.smoke_rc
    try:
        refuse_secret_values(record)
    except RecordError as exc:
        log.error("%s www-after: %s" % (SELF, exc))
        return 1
    if args.sink and record.get("version_after") is None and not args.accept_missing_after:
        log.error(
            "the www record has no version after (%s); not sinking it without --accept-missing-after"
            % (record.get("version_after_error") or "no reason recorded")
        )
        return 1
    write_json(path, record)
    print(json.dumps(record, indent=2, sort_keys=True))
    if args.sink:
        try:
            sink_record(record, args.sink, args.channel, record["target"], record["region"])
        except RecordError as exc:
            log.error("the www record was not written to %s: %s" % (args.sink, exc))
            return 1
    return 0


# ---- main -------------------------------------------------------------------


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=SELF, description=(__doc__ or "").splitlines()[0])
    sub = parser.add_subparsers(dest="verb", required=True)
    be = sub.add_parser("before", help="the record taken before the migrations")
    be.add_argument("--target", required=True)
    be.add_argument("--region", required=True)
    be.add_argument("--version", required=True)
    be.add_argument("--out", required=True)
    bo = sub.add_parser("bootstrap", help="deploy a proxy Worker that does not exist yet")
    bo.add_argument("--before", required=True)
    bo.add_argument("--record", required=True)
    rb = sub.add_parser("rollback", help="close the executor, return the proxy, print the rest")
    rb.add_argument("--before", required=True)
    af = sub.add_parser("after", help="the full record, the job summary and the pointer")
    af.add_argument("--before", required=True)
    af.add_argument("--proxy-record", required=True)
    af.add_argument("--manifest", required=True)
    af.add_argument("--enable-outcome", default="", choices=OUTCOMES)
    af.add_argument("--rollback-outcome", default="", choices=OUTCOMES)
    af.add_argument("--out", required=True)
    af.add_argument("--account-smoke-rc", type=int, default=None)
    af.add_argument("--sink", default="", choices=("", *SINKS))
    af.add_argument("--channel", default="", choices=("", *CHANNELS))
    wa = sub.add_parser("www-after", help="add the smoke rc to a www record and sink it")
    wa.add_argument("--record", required=True)
    wa.add_argument("--smoke-rc", required=True, type=int)
    wa.add_argument("--sink", default="", choices=("", *SINKS))
    wa.add_argument("--channel", default="", choices=("", *CHANNELS))
    wa.add_argument("--accept-missing-after", action="store_true")
    return parser


VERBS = {
    "before": cmd_before,
    "bootstrap": cmd_bootstrap,
    "rollback": cmd_rollback,
    "after": cmd_after,
    "www-after": cmd_www_after,
}


def main(argv: list[str]) -> int:
    try:
        args = _parser().parse_args(argv)
    except SystemExit as exc:
        return int(exc.code or 0)
    try:
        return VERBS[args.verb](args, paths.repo_root())
    except (RecordError, KeyError) as exc:
        log.error("%s %s: %s" % (SELF, args.verb, exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
