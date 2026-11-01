"""The live-proof recorder (agent/plans/PLAN-tested-on-bench.md Design item 4): run one registry check against bench or hostinger and, on a VERIFIED run, append its receipt row to the committed ledger.

    PYTHONPATH=.ci python3 -m rediacc_ci.ops.live_proof record --plan <rel> --box <sig> --target bench|hostinger --check <id> [--region eu] [--machine <alias>] [--by <session>] [--write]
    PYTHONPATH=.ci python3 -m rediacc_ci.ops.live_proof verify [--plan <rel>]

RECORD. A dry run is the default; `--write` appends the row to `agent/ledgers/live-proof.jsonl`, and only a VERIFIED row. Every run, refused or not, keeps its full log at `.ci/cache/live-proof/<id>.log` (gitignored) and prints the id. There is no `--retro` (operator ruling 3): every receipt is a fresh run. Exit 0 VERIFIED, 1 FAILED or NOT_VERIFIED (nothing written), 2 a request the registry or the plan refuses (nothing run).

What a request must name, all checked before anything runs: a live plan under `agent/plans/` whose `Live-Proof:` line declares the target; an open box of that plan (`--box`, its signature) whose `Accept: live-proof <target> <check-id> [args]` sub-line names this target, check and arguments; a registry check that runs on the target (`tiers.live.checks`, fixed argv, no passthrough); a machine alias from `tiers.live.targets.<target>.machines`, if any; and at least one surface the plan's Owns hit (`surfaces.owns_surfaces`) that the check covers and the target admits. Those surfaces are the row's.

Then, in order, each a refusal that stops the run:
  1. identity: `receipt.identity` of those surfaces (a renet-hash check rebuilds `bin/renet` once through its registry `rebuild` argv), judged by `receipt.identity_refusal` (dirty-tree, checkout-mismatch, modified-checkout, build-mismatch, modified-build);
  2. the ladder: a row surface with a VM phase needs `vm_tier.admit` to admit the head tree (no live run before the ops VMs pass it); the row records the VM run id;
  3. the deploy record (bench-cache): `.ci/cache/live-deploys/bench.json` must exist, keep the identity rules itself, and be cut from the head;
  4. the steps, in registry order; a non-zero exit is FAILED. `stale-binary-empty` needs `stale_binary == []` in the JSON answer, `renet-hash` needs the remote hash to equal the local sha256 (else `not-live`);
  5. live confirmation: bench-cache asks wrangler for the version serving 100% and refuses `not-live` when it is not the recorded one; renet-hash is confirmed by step 4; an `unrecorded` check can confirm nothing and is NOT_VERIFIED;
  6. secrets: the log is scrubbed of every secret-named environment value (`core.secrets.redact_env`), a secret shape in the row refuses, and `deploy_record.refuse_secret_values` runs over the row.

A bench-cache check needs Cloudflare credentials for the wrangler read; without them the recorder re-executes itself under the `deploy-bench` Bitwarden profile, as deploy_bench does. Bench is IP-restricted: run `PYTHONPATH=.ci python3 -m rediacc_ci.ops.bench_access add-current` first, or the server-info step answers 403.

THE eu-bench LOGIN IS THE RECORDER'S OWN STEP (operator order 2026-10-30). An eu-bench rdc step that fails because the login is tied to another network address, or is absent (`login_bench.login_needed`), runs `npm run login:bench` once and retries that step; the log keeps the failed answer, the login and the retry. The login runs on a DRY RUN too (no `--write`): a dry run executes the registry steps like a written one, so a needed eu-bench login, with its bench IP-allowlist refresh (`bench_access add-current`), happens on every `record` call; `verify` runs no step and never logs in. A login that fails leaves the step FAILED and the message names the remedy. Nobody is asked for an authenticator code.

VERIFY. `proof.live_tier.validate_row` over every ledger row (or one plan's), with the git checks and the kept-log digest. Exit 0 when every judged row is valid; 1 on any invalid or unparsable row, or when `--plan` finds no row.
"""

from __future__ import annotations

import argparse
import dataclasses
import importlib
import json
import os
import re
import subprocess
import sys
import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from rediacc_ci import log, paths
from rediacc_ci.core import jsonl_append, secrets
from rediacc_ci.deploy import deploy_record
from rediacc_ci.ops import cf_auth, deploy_bench, login_bench
from rediacc_ci.proof import live_tier as LT
from rediacc_ci.proof import receipt as R
from rediacc_ci.proof import surfaces as S
from rediacc_ci.proof import vm_tier
from rediacc_ci.review import successor as SUCC

if TYPE_CHECKING:
    import pathlib
    from collections.abc import Callable, Mapping, Sequence

PLANS_DIR = "agent/plans/"
BENCH_PROFILE = deploy_bench.PROFILE
BY_MAX = 32
EXIT_VERIFIED = 0
EXIT_REFUSED = 1
EXIT_USAGE = 2
CODE_LADDER = "ladder"
CODE_FAILED = "check-failed"
CODE_LEAK = "secret-shape"
TIMEOUT_RC = 124
# login_bench waits for a fresh TOTP window, refreshes the IP allowlist and runs up to four rdc children.
LOGIN_TIMEOUT_S = 600
_SHA256 = re.compile(r"^[0-9a-f]{64}$")

D = importlib.import_module("wl_plandeps")


class RequestError(ValueError):
    """The request names something the registry or the plan refuses; nothing runs."""


@dataclasses.dataclass(frozen=True)
class Result:
    rc: int
    stdout: str
    stderr: str


def run_subprocess(
    argv: Sequence[str], cwd: pathlib.Path, timeout: int, env: Mapping[str, str] | None = None
) -> Result:
    """Run `argv` in `cwd` with no stdin; a timeout or a missing program is a non-zero Result, never an exception."""
    try:
        proc = subprocess.run(
            list(argv),
            cwd=str(cwd),
            env=None if env is None else dict(env),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return Result(TIMEOUT_RC, "", f"timed out after {timeout}s\n")
    except OSError as exc:
        return Result(127, "", f"{exc}\n")
    return Result(proc.returncode, proc.stdout or "", proc.stderr or "")


@dataclasses.dataclass
class World:
    """Everything the recorder reaches outside the process, replaceable in tests."""

    run: Callable[..., Result] = run_subprocess
    read_build: Callable[[pathlib.Path], str | None] = S.go_version_m
    admit: Callable[..., R.Verdict] = vm_tier.admit
    now: Callable[[], str] = lambda: datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    environ: Mapping[str, str] = dataclasses.field(default_factory=lambda: dict(os.environ))


@dataclasses.dataclass(frozen=True)
class Request:
    plan: str
    box: str
    target: str
    check: str
    region: str | None = None
    machine: str | None = None
    by: str = ""


@dataclasses.dataclass
class Outcome:
    status: str
    code: str
    message: str
    row: dict[str, Any] | None = None
    log_path: pathlib.Path | None = None
    written: bool = False

    @property
    def exit_code(self) -> int:
        return EXIT_VERIFIED if self.status == R.VERIFIED else EXIT_REFUSED


@dataclasses.dataclass
class _Plan:
    rel: str
    touched: dict[str, list[str]]
    accept: LT.Accept


def _read_plan(root: pathlib.Path, req: Request, check: LT.Check) -> _Plan:
    rel = req.plan
    if not (
        rel.startswith(PLANS_DIR) and rel.endswith(".md") and "/_" not in rel and ".." not in rel
    ):
        raise RequestError(f"--plan {rel!r} is not a live plan under {PLANS_DIR}")
    try:
        text = (root / rel).read_text(encoding="utf-8")
    except OSError as exc:
        raise RequestError(f"--plan {rel}: {exc}") from exc
    header = D.parse_header(text)
    if D.is_stub_header(header):
        raise RequestError(f"{rel} is a stub, not a live plan")
    try:
        finished = header.status in D.finished_states()
    except ImportError:
        finished = False
    if finished:
        raise RequestError(
            f"{rel} is finished (Status: {header.status}); a receipt closes an open box"
        )
    proof = header.live_proof
    if proof is None or req.target not in proof.targets:
        declared = ", ".join(proof.targets) if proof is not None and proof.targets else "none"
        raise RequestError(f"{rel} declares Live-Proof targets {declared}, not {req.target}")
    owns = header.owns
    touched = S.owns_surfaces(owns.globs) if owns is not None else {}
    box = next((b for b in D.plan_boxes(text) if b.sig == req.box), None)
    if box is None:
        raise RequestError(f"{rel} has no box with signature {req.box!r}")
    if box.done:
        raise RequestError(
            f"box {req.box} of {rel} is already ticked; a receipt is recorded before the tick"
        )
    accept = LT.accept_of(text, box.line)
    if accept is None:
        raise RequestError(
            f"box {req.box} of {rel} carries no `Accept: live-proof <target> <check-id> [args]` line"
        )
    wanted = LT.Accept(req.target, check.id, tuple(LT.check_args(req.machine)))
    if accept != wanted:
        raise RequestError(
            f"box {req.box} accepts `{_accept_text(accept)}`, not `{_accept_text(wanted)}`"
        )
    return _Plan(rel, touched, accept)


def _accept_text(accept: LT.Accept) -> str:
    return " ".join(("live-proof", accept.target, accept.check, *accept.args))


def _by(req: Request, environ: Mapping[str, str]) -> str:
    by = (
        req.by
        or (environ.get("WORKLIST_SESSION_ID") or environ.get("CLAUDE_CODE_SESSION_ID") or "")[:8]
    )
    if not by or len(by) > BY_MAX or not all(c.isalnum() or c in "-_" for c in by):
        raise RequestError("--by <session prefix> is needed: the environment names no session")
    return by


class _Log:
    def __init__(self) -> None:
        self.parts: list[str] = []

    def add(self, text: str) -> None:
        self.parts.append(text if text.endswith("\n") else text + "\n")

    def run(self, label: str, argv: Sequence[str], result: Result) -> None:
        self.add(f"$ [{label}] {' '.join(argv)}")
        if result.stdout:
            self.add(result.stdout)
        if result.stderr:
            self.add(result.stderr)
        self.add(f"# rc={result.rc}")

    def text(self, environ: Mapping[str, str]) -> str:
        return secrets.redact_env("".join(self.parts), environ)


def _json_object(text: str) -> dict[str, Any] | None:
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        return None
    try:
        parsed = json.loads(text[start : end + 1])
    except ValueError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _remote_hash(text: str) -> str:
    found = [ln.strip() for ln in text.splitlines() if _SHA256.match(ln.strip())]
    return found[-1] if found else ""


@dataclasses.dataclass
class _Run:
    """The mutable state of one record run."""

    req: Request
    check: LT.Check
    surfaces: list[str]
    ident: dict[str, Any]
    log: _Log
    deploy: dict[str, Any]
    argv: list[list[str]] = dataclasses.field(default_factory=list)
    rc: int | None = None
    ladder: dict[str, Any] = dataclasses.field(default_factory=lambda: {"vm": None})
    started: float = dataclasses.field(default_factory=time.monotonic)


def _wrangler_env(environ: Mapping[str, str]) -> dict[str, str] | None:
    """The environment for a wrangler read: an API token, else the Global API Key pair. None when neither is there."""
    env = dict(environ)
    if environ.get("CLOUDFLARE_API_TOKEN"):
        pass
    elif environ.get("CF_GLOBAL_API_KEY") and environ.get("CF_EMAIL"):
        env["CLOUDFLARE_API_KEY"] = environ["CF_GLOBAL_API_KEY"]
        env["CLOUDFLARE_EMAIL"] = environ["CF_EMAIL"]
    else:
        return None
    env.setdefault("CLOUDFLARE_ACCOUNT_ID", cf_auth.DEFAULT_ACCOUNT_ID)
    return env


def _bench_live_version(root: pathlib.Path, world: World, log_: _Log) -> str | None:
    env = _wrangler_env(world.environ)
    argv = deploy_record.deployments_argv(deploy_bench.CONFIG)
    if env is None:
        log_.add(
            "# no Cloudflare credentials for the wrangler read (CLOUDFLARE_API_TOKEN or CF_GLOBAL_API_KEY + CF_EMAIL)"
        )
        return None
    result = world.run(argv, root / "workers" / "account", LT.DEFAULT_TIMEOUT_S, env)
    log_.run("confirm", argv, result)
    if result.rc != 0:
        return None
    parsed, version = deploy_record.parse_deployed_version(result.stdout)
    return version if parsed else None


def _bench_record(root: pathlib.Path, run: _Run) -> str | None:
    """Fill run.deploy from bench.json; the refusal message, or None."""
    path = root.joinpath(*deploy_bench.VERSION_RECORD)
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return f"no bench deploy record at {'/'.join(deploy_bench.VERSION_RECORD)} ({exc.__class__.__name__}); run deploy_bench from this head"
    if not isinstance(record, dict):
        return "the bench deploy record is not an object"
    run.deploy["version_id"] = record.get("version_id")
    run.deploy["deployed_head"] = record.get("head")
    refused = R.identity_refusal(record, deploy_bench.BENCH_SURFACES)
    if refused is not None:
        return f"the bench deploy was cut from an unclean tree ({refused.code}: {refused.message})"
    if record.get("head") != run.ident["head"]:
        return f"bench serves a deploy cut from {str(record.get('head'))[:12]}, not the head {run.ident['head'][:12]}"
    return None


def _bench_login_needed(argv: Sequence[str], result: Result) -> bool:
    """True when an eu-bench rdc step failed because its login is bound to another IP address, or absent."""
    return (
        result.rc != 0
        and login_bench.targets_config(argv)
        and login_bench.login_needed(result.stdout + result.stderr)
    )


def _relogin_and_retry(
    root: pathlib.Path, world: World, log_: _Log, label: str, item: LT.Run, failed: Result
) -> Result:
    """Run `npm run login:bench` once (agent-allowed, idempotent; operator order 2026-10-30) and rerun the step; the failed answer stands when the login fails."""
    log_.add(
        f"# the eu-bench login is tied to another address or absent: running `{login_bench.REMEDY}` once, then retrying {label}"
    )
    argv = list(login_bench.REMEDY_ARGV)
    login = world.run(argv, root, LOGIN_TIMEOUT_S, None)
    log_.run("login-bench", argv, login)
    if login.rc != 0:
        log_.add(f"# `{login_bench.REMEDY}` exited {login.rc}; {label} is not retried")
        return failed
    retried = world.run(item.argv, root, item.step.timeout_s, None)
    log_.run(label + " (retry after login:bench)", item.argv, retried)
    return retried


def _stale_binary(answer: dict[str, Any] | None) -> Any:
    """`stale_binary` from a `machine status -o json` answer: the CLI nests it under `data` (`{"success":..., "data": {..., "stale_binary": [...]}}`); a top-level key is still read. None when neither carries it."""
    if answer is None:
        return None
    data = answer.get("data")
    if isinstance(data, dict) and "stale_binary" in data:
        return data["stale_binary"]
    return answer.get("stale_binary")


def _stale_text(stale: Any) -> str:
    """The refusal text for a stale_binary answer that is not []: the count and the units when it is a list."""
    if not isinstance(stale, list):
        return f"stale_binary is {json.dumps(stale)}, not []"
    # An entry with none of unit, exe or pid is named by its own JSON, never by the string "None".
    units = sorted(
        {
            str(e.get("unit") or e.get("exe") or e.get("pid") or json.dumps(e, sort_keys=True))
            for e in stale
            if isinstance(e, dict)
        }
    )
    return f"stale_binary lists {len(stale)} process(es) still running a replaced renet, not []: {', '.join(units) or json.dumps(stale)}"


def _step_refusal(
    run: _Run, step: LT.Step, machine: str | None, result: Result
) -> tuple[str, str] | None:
    """(status, message) when a step's answer refuses the run, else None."""
    where = f"step {step.id}" + (f" on {machine}" if machine else "")
    if result.rc != 0:
        return R.FAILED, f"{where} exited {result.rc}"
    if step.expect == LT.EXPECT_STALE_BINARY_EMPTY:
        stale = _stale_binary(_json_object(result.stdout))
        if stale != []:
            return R.NOT_VERIFIED, f"{where}: {_stale_text(stale)}"
    elif step.expect == LT.EXPECT_RENET_HASH:
        local = (run.ident.get("renet") or {}).get("sha256") or ""
        remote = _remote_hash(result.stdout)
        if not local or remote != local:
            return (
                R.NOT_VERIFIED,
                f"{where}: the remote renet hash {remote[:12] or '<none>'} is not the local {local[:12] or '<none>'}",
            )
    return None


def _refuse(
    run: _Run, root: pathlib.Path, world: World, status: str, code: str, message: str
) -> Outcome:
    run.log.add(f"# {status} {code}: {message}")
    row, text = _compose(run, world, status)
    path = _keep_log(root, row, text)
    return Outcome(status, code, message, row, path)


def _compose(run: _Run, world: World, status: str) -> tuple[dict[str, Any], str]:
    """The row of the run so far and its scrubbed log; the row carries the log's digest, and its id names the log."""
    text = run.log.text(world.environ)
    body = {
        "at": world.now(),
        "by": run.req.by,
        "plan": run.req.plan,
        "box": run.req.box,
        "target": run.req.target,
        "region": run.req.region,
        "deploy": dict(run.deploy),
        "check": {
            "id": run.check.id,
            "args": LT.check_args(run.req.machine),
            "argv": run.argv,
            "rc": run.rc,
            "duration_s": round(time.monotonic() - run.started, 1),
            "log_sha256": LT.log_digest(text),
            "tail": LT.tail_of(text),
        },
        "ladder": dict(run.ladder),
    }
    return LT.build_row(run.ident, status, **body), text


def _keep_log(root: pathlib.Path, row: dict[str, Any], text: str) -> pathlib.Path:
    path = LT.log_path(root, row["id"])
    R.write_atomic(path, text)
    return path


def _identity(
    root: pathlib.Path, check: LT.Check, req: Request, names: list[str], world: World, log_: _Log
) -> dict[str, Any]:
    def rebuild() -> None:
        argv = LT.rebuild_argv(check, req.target)
        log_.run("rebuild", argv, world.run(argv, root, LT.DEFAULT_TIMEOUT_S, None))

    def renet(r: pathlib.Path) -> dict[str, Any]:
        return S.renet_identity(
            r, read_build=world.read_build, rebuild=rebuild if check.rebuild else None
        )

    ident = R.identity(root, names, renet=renet)
    if check.deploy == LT.RENET_HASH and ident.get("renet") is None:
        got = renet(root)
        ident["renet"] = {k: got.get(k) for k in ("built", "modified", "sha256")}
    return ident


def _validate_request(req: Request, checks: dict[str, LT.Check]) -> LT.Check:
    check = checks.get(req.check)
    if check is None:
        raise RequestError(
            f"check {req.check!r} is not in tiers.live.checks ({', '.join(sorted(checks))})"
        )
    if req.region is not None and req.region not in LT.REGIONS:
        raise RequestError(f"--region {req.region!r} is not one of {', '.join(LT.REGIONS)}")
    try:
        LT.expand(check, req.target, req.machine)
    except LT.RegistryError as exc:
        raise RequestError(str(exc)) from exc
    return check


def record(
    root: pathlib.Path,
    req: Request,
    *,
    write: bool = False,
    world: World | None = None,
    checks: dict[str, LT.Check] | None = None,
) -> Outcome:
    """Run one live check and judge it; see the module docstring. RequestError before anything runs."""
    world = world or World()
    checks = LT.registry() if checks is None else checks
    check = _validate_request(req, checks)
    plan = _read_plan(root, req, check)
    req = dataclasses.replace(req, by=_by(req, world.environ))
    names = LT.row_surfaces(plan.touched, check, req.target)
    if not names:
        raise RequestError(
            f"{req.plan} touches {sorted(plan.touched) or 'no surface'}; check {check.id} covers "
            f"{sorted(check.surfaces)} and none of them is both touched and admissible on {req.target}"
        )
    log_ = _Log()
    log_.add(
        f"# live-proof {req.plan} box {req.box} target {req.target} check {check.id} surfaces {','.join(names)}"
    )
    ident = _identity(root, check, req, names, world, log_)
    deploy = {
        "surface": LT.DEPLOY_SURFACE[check.deploy],
        "worker": deploy_bench.WORKER_NAME if check.deploy == LT.BENCH_CACHE else None,
        "version_id": None,
        "source": None,
        "deployed_head": None,
        "confirmed_live": False,
    }
    run = _Run(req, check, names, ident, log_, deploy)
    refused = R.identity_refusal(ident, LT.judge_surfaces(names, check))
    if refused is not None:
        return _refuse(run, root, world, R.NOT_VERIFIED, refused.code, refused.message)
    phases = S.phases_for(names)
    if phases:
        verdict = world.admit(root, ident["tree"], S.inputs(root, ident["tree"]), phases)
        if not verdict.ok:
            return _refuse(
                run,
                root,
                world,
                R.NOT_VERIFIED,
                CODE_LADDER,
                f"no VM receipt admits the head tree ({verdict.code}: {verdict.message})",
            )
        run.ladder = {"vm": (verdict.receipt or {}).get("runId")}
    if check.deploy == LT.BENCH_CACHE:
        deploy["source"] = LT.BENCH_CACHE
        why = _bench_record(root, run)
        if why is not None:
            return _refuse(run, root, world, R.NOT_VERIFIED, R.NOT_LIVE, why)
    relogged = False
    for item in LT.expand(check, req.target, req.machine):
        label = item.step.id + (f"@{item.machine}" if item.machine else "")
        result = world.run(item.argv, root, item.step.timeout_s, None)
        log_.run(label, item.argv, result)
        if not relogged and _bench_login_needed(item.argv, result):
            relogged = True
            result = _relogin_and_retry(root, world, log_, label, item, result)
        run.argv.append(list(item.argv))
        run.rc = result.rc
        stop = _step_refusal(run, item.step, item.machine, result)
        if stop is not None:
            code = CODE_FAILED if stop[0] == R.FAILED else R.NOT_LIVE
            message = stop[1]
            if _bench_login_needed(item.argv, result):
                message += f"; the eu-bench login still needs `{login_bench.REMEDY}` (an agent's own step, never the operator's)"
            return _refuse(run, root, world, stop[0], code, message)
    why = _confirm(root, run, world)
    if why is not None:
        return _refuse(run, root, world, R.NOT_VERIFIED, R.NOT_LIVE, why)
    return _judge_and_write(run, root, world, write)


def _confirm(root: pathlib.Path, run: _Run, world: World) -> str | None:
    """Set deploy.confirmed_live from the live side; the refusal message, or None."""
    kind = run.check.deploy
    head = run.ident["head"]
    if kind == LT.BENCH_CACHE:
        live = _bench_live_version(root, world, run.log)
        if not live or live != run.deploy["version_id"]:
            return f"bench serves version {live or '<unknown>'}, not the recorded {run.deploy['version_id']}"
    elif kind == LT.RENET_HASH:
        renet = run.ident.get("renet") or {}
        run.deploy.update(
            version_id=f"renet:{renet.get('built')}@sha256:{renet.get('sha256')}",
            source=f"rdc:{LT.target_entry(run.req.target).get('config')}",
            deployed_head=head,
        )
    elif kind == LT.TREE:
        run.deploy.update(version_id=f"cli:{head}", source="tree", deployed_head=head)
    else:
        return f"check {run.check.id} has no deploy record tying the served version to a console head (deploy {kind})"
    run.deploy["confirmed_live"] = True
    return None


def _judge_and_write(run: _Run, root: pathlib.Path, world: World, write: bool) -> Outcome:
    row, text = _compose(run, world, R.VERIFIED)
    shapes = LT.secret_shapes(R.canonical(row))
    if shapes:
        return _refuse(
            run,
            root,
            world,
            R.NOT_VERIFIED,
            CODE_LEAK,
            f"the row carries a secret shape ({', '.join(shapes)})",
        )
    try:
        deploy_record.refuse_secret_values(row)
    except deploy_record.RecordError as exc:
        return _refuse(run, root, world, R.NOT_VERIFIED, CODE_LEAK, str(exc))
    problems = LT.validate_row(row, checks={run.check.id: run.check}, root=root)
    if problems:
        return _refuse(run, root, world, R.NOT_VERIFIED, "invalid-row", "; ".join(problems))
    path = _keep_log(root, row, text)
    written = False
    if write:
        ledger = LT.ledger_path(root)
        ledger.parent.mkdir(parents=True, exist_ok=True)
        jsonl_append.append_lines(ledger, path.parent / "ledger.lock", [row])
        written = True
    return Outcome(R.VERIFIED, "ok", f"VERIFIED {row['id']}", row, path, written)


# ----------------------------------------------------------------------------- verify


def _base(root: pathlib.Path) -> str:
    """merge-base(HEAD, origin/main), else main: the start of the branch whose patch-ids map a rewritten head."""
    git = S.make_git(root)
    for ref in ("origin/main", "main"):
        got = (git(["merge-base", "HEAD", ref]) or "").strip()
        if got:
            return got
    return ""


def verify(
    root: pathlib.Path,
    plan: str | None = None,
    checks: dict[str, LT.Check] | None = None,
    successor_of: Callable[[str], str | None] | None = None,
) -> tuple[int, list[str]]:
    """(exit code, report lines) of `validate_row` over the ledger rows (of `plan` when given).

    A head a rebase rewrote is re-resolved through `successor_of`, by default the review-record map `check_plan_live_proof` uses (`rediacc_ci.review.successor`), built on first use.
    """
    checks = LT.registry() if checks is None else checks
    if successor_of is None:
        successor_of = SUCC.lazy_successor_of(
            str(root), _base(root), importlib.import_module("wl_planrec")
        )
    lines: list[str] = []
    bad = 0
    judged = 0
    for entry in LT.read_ledger(LT.ledger_path(root)):
        if entry.row is None:
            bad += 1
            lines.append(f"INVALID line {entry.lineno}: {entry.error}")
            continue
        if plan is not None and entry.row.get("plan") != plan:
            continue
        judged += 1
        problems = LT.validate_row(entry.row, checks=checks, root=root, successor_of=successor_of)
        name = f"{entry.row.get('id')} {entry.row.get('plan')} {entry.row.get('target')} {(entry.row.get('check') or {}).get('id')}"
        if problems:
            bad += 1
            lines.append(f"INVALID line {entry.lineno} {name}: " + "; ".join(problems))
        else:
            lines.append(f"ok {name} v={(entry.row.get('deploy') or {}).get('version_id')}")
    lines.append(f"{judged} row(s) judged, {bad} invalid")
    if plan is not None and judged == 0:
        lines.append(f"no receipt row for {plan}")
        return EXIT_REFUSED, lines
    return (EXIT_REFUSED if bad else EXIT_VERIFIED), lines


# ----------------------------------------------------------------------------- command line


def _needs_profile(check: LT.Check | None, environ: Mapping[str, str]) -> bool:
    if check is None or check.deploy != LT.BENCH_CACHE:
        return False
    if BENCH_PROFILE in (environ.get("REDIACC_BWS_PROFILES") or "").split(","):
        return False
    return _wrangler_env(environ) is None


def _reexec_under_profile(argv: list[str]) -> int:
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
            BENCH_PROFILE,
            "--",
            sys.executable,
            "-m",
            "rediacc_ci.ops.live_proof",
            *argv,
        ],
        env=env,
        check=False,
    ).returncode


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="live_proof", description=__doc__.split("\n\n", 1)[0])
    sub = parser.add_subparsers(dest="verb", required=True)
    rec = sub.add_parser(
        "record", help="run one registry check and judge it (dry run unless --write)"
    )
    rec.add_argument("--plan", required=True)
    rec.add_argument("--box", required=True, help="the LP box's signature")
    rec.add_argument("--target", required=True, choices=sorted(S.MAP.live.get("targets") or {}))
    rec.add_argument("--check", required=True)
    rec.add_argument("--region", default=None, choices=LT.REGIONS)
    rec.add_argument(
        "--machine", default=None, help="narrow a per-machine check to one registry alias"
    )
    rec.add_argument(
        "--by", default="", help="session prefix (default: the environment's session id)"
    )
    rec.add_argument("--write", action="store_true", help="append a VERIFIED row to the ledger")
    ver = sub.add_parser("verify", help="judge the ledger rows")
    ver.add_argument("--plan", default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    args = _parser().parse_args(argv)
    root = paths.repo_root()
    if args.verb == "verify":
        code, lines = verify(root, args.plan)
        for line in lines:
            print(line)
        return code
    req = Request(args.plan, args.box, args.target, args.check, args.region, args.machine, args.by)
    try:
        checks = LT.registry()
    except (LT.RegistryError, S.MapError) as exc:
        log.error(f"the check registry cannot be read: {exc}")
        return EXIT_USAGE
    if _needs_profile(checks.get(req.check), os.environ):
        return _reexec_under_profile(argv)
    try:
        outcome = record(root, req, write=args.write, checks=checks)
    except RequestError as exc:
        log.error(str(exc))
        return EXIT_USAGE
    rel_log = outcome.log_path.relative_to(root) if outcome.log_path else None
    if outcome.status == R.VERIFIED:
        where = (
            "appended to " + "/".join(LT.LEDGER)
            if outcome.written
            else "dry run, nothing written (--write appends)"
        )
        log.info(f"{outcome.message}: {where}; log {rel_log}")
    else:
        log.error(
            f"{outcome.status} {outcome.code}: {outcome.message}; nothing written; log {rel_log}"
        )
    return outcome.exit_code


if __name__ == "__main__":
    sys.exit(main())
