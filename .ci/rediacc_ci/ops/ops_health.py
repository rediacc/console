"""Local health checks of every machine the operator's rdc config names, the off-box alerter's state, and the cache the Stop hook reads (agent/plans/PLAN-health-checks-local.md, boxes L1, L2 and L4).

    PYTHONPATH=.ci python3 -m rediacc_ci.ops.ops_health machines [--json]
    PYTHONPATH=.ci python3 -m rediacc_ci.ops.ops_health refresh [--force] [--check <name>]... [--lock-held]
    PYTHONPATH=.ci python3 -m rediacc_ci.ops.ops_health offbox [--json]
    PYTHONPATH=.ci python3 -m rediacc_ci.ops.ops_health gate

MACHINES (D-verdict). The configs come from RDC_HEALTH_CONFIGS (a comma list in the operator's environment; unset means the rdc default config) and the machines from `rdc machine list -o json` in each config, so no machine or config name is written here. Per machine, every rdc call runs with REDIACC_NO_PROVISION=1 forced into the child environment (a health read must never install renet and restart daemons, F5):
  1. `machine health <m> -o json`: exit 1 or higher is red, so warnings fail;
  2. `machine status <m> --containers --health-check`: non-zero is red;
  3. `machine status <m> --services --stability-check`: non-zero is red;
  4. `backup_coverage` present for every autostart repo, and each covered repo younger than `backup_max_age_days`. The repositories and the coverage are read from the health JSON when it carries them, else from one `machine status <m> -o json`.
A repo whose `health()` is absent (`level: none`) is reported as "no check", never as green and never as red. Exit 0 green, 1 red, 2 setup or unreadable (an empty machine list, an rdc call that timed out or printed no JSON). A red row wins over an unreadable one in the aggregate, so an unreachable machine cannot hide a red one.

REFRESH (D-local). Runs the checks that are past their TTL (`--force` runs all): `machines`, then telemetry_delivery under bws profile `telemetry-probe`, portal_captcha, and cf_usage_report under profile `cf-usage-report`, each unchanged as a subprocess keeping its 0/1/2 contract; then the off-box read. It writes `.ci/cache/ops-health/state.json`, appends one row per state transition to agent/ledgers/ops-health.jsonl (an unchanged state appends nothing), and POSTs each fresh local verdict to the Worker's `/v1/ingest` (sources `local-machine-<name>` and `local-<check>`). A failed POST is recorded in the cache and never fails the refresh. The Stop hook (.claude/hooks/stop/wl_opshealth.py) spawns it detached, after taking `.ci/cache/ops-health/refresh.lock` with O_EXCL, and passes `--lock-held`; a hand run takes the same lock itself.

OFFBOX AND GATE (D-record, D-gate). `GET <worker_url>/v1/status` with the bearer OPS_HEALTH_READ_TOKEN. Red when the verdict is red or `last_cron_at` is older than the stale limit; unreadable (exit 2) when the status cannot be read or its verdict is `unknown`. `offbox` also compares `targets_sha` with the sha256 of the `ops` repo's target file when OPS_HEALTH_TARGETS_REF is set (finding `ops.targets.drift`, red, naming the deploy command). `gate` is the CI gate's entry (.ci/scripts/quality/check_ops_health.py): the same judgement with no target comparison.

CONFIG. .ci/config/ops-health.json (D-config) holds the thresholds. `DEFAULTS` below carries the same values for a key the file does not have, so a tree without the file still runs; the file wins wherever it speaks. The Worker's origin is `worker_url` there, or OPS_HEALTH_URL, and is never typed in this source.
"""

from __future__ import annotations

import argparse
import contextlib
import dataclasses
import datetime
import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.error
from collections.abc import Callable
from typing import TYPE_CHECKING

from rediacc_ci.core import bws_env, https, jsonl_append
from rediacc_ci.core.common import repo_root

if TYPE_CHECKING:
    import pathlib

CONFIG_REL = ".ci/config/ops-health.json"
CACHE_DIR_REL = ".ci/cache/ops-health"
STATE_NAME = "state.json"
LOCK_NAME = "refresh.lock"
LEDGER_REL = "agent/ledgers/ops-health.jsonl"
LEDGER_LOCK_NAME = "ledger.lock"
# The hook treats an older lock as a dead refresher (D-local).
LOCK_STALE_S = 20 * 60

NO_PROVISION_ENV = "REDIACC_NO_PROVISION"
CONFIGS_ENV = "RDC_HEALTH_CONFIGS"
RDC_ENV = "OPS_HEALTH_RDC"
URL_ENV = "OPS_HEALTH_URL"
READ_CREDENTIAL_ENV = "OPS_HEALTH_READ_TOKEN"
INGEST_CREDENTIAL_ENV = "OPS_HEALTH_INGEST_TOKEN"
TARGETS_REF_ENV = "OPS_HEALTH_TARGETS_REF"
TARGETS_PATH_ENV = "OPS_HEALTH_TARGETS_PATH"
TARGETS_CONFIG_ENV = "OPS_HEALTH_TARGETS_CONFIG"
CREDENTIAL_PROFILE = "ops-health"

DEFAULTS: dict = {
    "local_ttl_min": {
        "machines": 30,
        "telemetry": 360,
        "portal-captcha": 360,
        "cf-usage": 10080,
        "offbox": 15,
    },
    "stale": {"last_cron_at_min": 30},
    "backup_max_age_days": 2,
    "auto_repair": {"classes": ["auto-safe"], "max_attempts_per_code_per_machine_per_day": 3},
}

# The order a refresh runs them in, and each one's command. `machines` runs in-process.
SUBPROCESS_CHECKS: dict[str, tuple[str | None, str]] = {
    "telemetry": ("telemetry-probe", "rediacc_ci.ops.telemetry_delivery"),
    "portal-captcha": (None, "rediacc_ci.ops.portal_captcha"),
    "cf-usage": ("cf-usage-report", "rediacc_ci.ops.cf_usage_report"),
}
LOCAL_CHECKS = ("machines", *SUBPROCESS_CHECKS)
ALL_CHECKS = (*LOCAL_CHECKS, "offbox")

RDC_TIMEOUT_S = 300.0
REPAIR_TIMEOUT_S = 900.0
# An action `result` that starts with one of these did not run the fix, so it does not use up the day's attempts.
NOT_RUN_RESULTS = ("skipped", "noop", "none", "already", "refused", "dry")
SUBPROCESS_TIMEOUT_S = 900.0
HTTP_TIMEOUT_S = 20.0
DETAIL_MAX = 600

GREEN, RED, UNKNOWN = "green", "red", "unknown"
_RC_STATE = {0: GREEN, 1: RED}


def state_of(rc: int) -> str:
    return _RC_STATE.get(rc, UNKNOWN)


def worst_rc(rcs) -> int:
    """1 when any is red, else 2 when any is unreadable, else 0: a red is never hidden behind an unreadable neighbour."""
    rcs = list(rcs)
    if 1 in rcs:
        return 1
    if any(rc not in (0, 1) for rc in rcs):
        return 2
    return 0


def utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


def iso(when: datetime.datetime) -> str:
    return when.astimezone(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(text: object) -> datetime.datetime | None:
    if not isinstance(text, str) or not text:
        return None
    try:
        when = datetime.datetime.fromisoformat(text)
    except ValueError:
        return None
    return when if when.tzinfo else when.replace(tzinfo=datetime.UTC)


def _trim(text: str, limit: int = DETAIL_MAX) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else "..." + text[-limit:]


# --------------------------------------------------------------------------- config


def load_config(root: pathlib.Path) -> dict:
    """DEFAULTS overlaid by .ci/config/ops-health.json, one level deep. An unreadable file is the defaults."""
    cfg = json.loads(json.dumps(DEFAULTS))
    try:
        doc = json.loads((root / CONFIG_REL).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return cfg
    if not isinstance(doc, dict):
        return cfg
    for key, value in doc.items():
        if isinstance(value, dict) and isinstance(cfg.get(key), dict):
            cfg[key] = {**cfg[key], **value}
        else:
            cfg[key] = value
    return cfg


def ttl_s(cfg: dict, check: str) -> int:
    return int(float((cfg.get("local_ttl_min") or {}).get(check, 30)) * 60)


def stale_min(cfg: dict) -> float:
    return float((cfg.get("stale") or {}).get("last_cron_at_min", 30))


def worker_url(cfg: dict, env: dict) -> str:
    return (env.get(URL_ENV) or str(cfg.get("worker_url") or "")).rstrip("/")


# --------------------------------------------------------------------------- subprocesses


@dataclasses.dataclass
class Result:
    rc: int
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False


# (argv, env, timeout_s) -> Result. Injected by the tests; `run_process` is the real one.
Runner = Callable[[list, dict, float], Result]


def run_process(argv: list, env: dict, timeout: float) -> Result:
    try:
        proc = subprocess.run(
            argv,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            cwd=str(repo_root()),
        )
    except subprocess.TimeoutExpired as exc:
        out = exc.stdout if isinstance(exc.stdout, str) else ""
        err = exc.stderr if isinstance(exc.stderr, str) else ""
        return Result(124, out, err, timed_out=True)
    except OSError as exc:
        return Result(127, "", "%s: %s" % (argv[0], exc.strerror or exc))
    return Result(proc.returncode, proc.stdout, proc.stderr)


def child_env(base: dict | None = None) -> dict:
    """The environment every rdc call gets: the caller's, with REDIACC_NO_PROVISION=1 forced whatever the caller set or unset."""
    env = dict(os.environ if base is None else base)
    env[NO_PROVISION_ENV] = "1"
    return env


def rdc_argv(env: dict, config: str | None, args: list) -> list:
    rdc = env.get(RDC_ENV) or str(repo_root() / "rdc.sh")
    return [rdc, *(["--config", config] if config else []), *args]


def envelope_data(stdout: str):
    """The `data` of the CLI's JSON envelope, or the whole document when it has no envelope. None when stdout holds no JSON."""
    text = (stdout or "").strip()
    if not text:
        return None
    try:
        doc = json.loads(text)
    except ValueError:
        # Progress text before the document: take from the first brace or bracket on its own line.
        start = min((i for i in (text.find("\n{"), text.find("\n[")) if i >= 0), default=-1)
        if start < 0:
            return None
        try:
            doc = json.loads(text[start + 1 :])
        except ValueError:
            return None
    if isinstance(doc, dict) and "data" in doc and "success" in doc:
        return doc["data"]
    return doc


# --------------------------------------------------------------------------- machines (L1, D-verdict)


def configs_from_env(env: dict) -> list:
    raw = env.get(CONFIGS_ENV) or ""
    names = [c.strip() for c in raw.split(",") if c.strip()]
    return names or [None]


def _repo_levels(data: dict) -> tuple[list, list]:
    """(names at level none, names at warning or error) from the health JSON's per-repo section, read by shape: `repo_health` as a list or as `{repos: [...]}`."""
    section = data.get("repo_health")
    if isinstance(section, dict):
        section = section.get("repos")
    none, bad = [], []
    for row in section if isinstance(section, list) else []:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or row.get("repo") or row.get("repository") or "?")
        level = str(row.get("level") or "")
        if level == "none":
            none.append(name)
        elif level in ("warning", "error"):
            bad.append("%s (%s)" % (name, level))
    return none, bad


def coverage_problems(listing: dict, max_age_days: float) -> list:
    """Autostart repos with no `backup_coverage` entry, and covered autostart repos older than the limit. An absent `backup_coverage` with autostart repos present is every one of them uncovered (F3: silent by design until now)."""
    repos = [r for r in listing.get("repositories") or [] if isinstance(r, dict)]
    auto = [r for r in repos if r.get("autostart") is True]
    if not auto:
        return []
    cov = listing.get("backup_coverage")
    rows = cov.get("repos") if isinstance(cov, dict) else None
    by_key: dict[str, dict] = {}
    for row in rows if isinstance(rows, list) else []:
        if isinstance(row, dict):
            for key in (row.get("guid"), row.get("name")):
                if key:
                    by_key[str(key)] = row
    problems = []
    for repo in auto:
        name = str(repo.get("name") or repo.get("guid") or "?")
        hit = by_key.get(str(repo.get("guid") or "")) or by_key.get(name)
        if hit is None:
            problems.append("backup.coverage.absent: %s" % name)
            continue
        age = hit.get("age_days")
        if isinstance(age, (int, float)) and age > max_age_days:
            problems.append("backup.age.stale: %s (%s days)" % (name, age))
    return problems


def check_machine(config: str | None, machine: str, runner: Runner, env: dict, cfg: dict) -> dict:
    """One machine's row: {config, machine, rc, state, problems, findings, no_check, steps}."""
    row: dict = {
        "config": config or "",
        "machine": machine,
        "problems": [],
        "findings": [],
        "no_check": [],
        "steps": {},
    }
    unreadable: list[str] = []

    def call(step: str, args: list) -> Result:
        res = runner(rdc_argv(env, config, args), env, RDC_TIMEOUT_S)
        row["steps"][step] = "timeout" if res.timed_out else res.rc
        return res

    health = call("health", ["machine", "health", machine, "-o", "json"])
    data = envelope_data(health.stdout)
    if health.timed_out:
        unreadable.append("machine health timed out after %ds" % RDC_TIMEOUT_S)
    elif not isinstance(data, dict):
        unreadable.append(
            "machine health rc %d printed no JSON: %s"
            % (health.rc, _trim(health.stderr or health.stdout, 200))
        )
    else:
        if health.rc >= 1:
            issues = [str(i) for i in data.get("issues") or []] or [str(data.get("message") or "")]
            row["problems"].append("machine health rc %d: %s" % (health.rc, "; ".join(issues)))
        findings = data.get("findings")
        if isinstance(findings, list):
            row["findings"] = [f for f in findings if isinstance(f, dict)]
        none, bad = _repo_levels(data)
        row["no_check"] = none
        if bad and health.rc < 1:
            # The CLI folds the worst repo level into its exit code (D-repohealth); a level it reports without folding is still a red here.
            row["problems"].append("repo health: %s" % ", ".join(bad))

    for step, args in (
        ("containers", ["machine", "status", machine, "--containers", "--health-check"]),
        ("services", ["machine", "status", machine, "--services", "--stability-check"]),
    ):
        res = call(step, args)
        if res.timed_out:
            unreadable.append("machine status --%s timed out" % step)
        elif res.rc != 0:
            row["problems"].append(
                "machine status --%s rc %d: %s"
                % (step, res.rc, _trim(res.stderr or res.stdout, 200))
            )

    listing = data if isinstance(data, dict) and "repositories" in data else None
    if listing is None and not health.timed_out:
        res = call("listing", ["machine", "status", machine, "-o", "json"])
        listing = envelope_data(res.stdout) if not res.timed_out else None
        if not isinstance(listing, dict):
            unreadable.append("machine status -o json printed no listing for the coverage check")
            listing = None
    if listing is not None:
        row["problems"] += coverage_problems(
            listing, float(cfg.get("backup_max_age_days") or DEFAULTS["backup_max_age_days"])
        )

    row["unreadable"] = unreadable
    row["rc"] = 1 if row["problems"] else (2 if unreadable else 0)
    row["state"] = state_of(row["rc"])
    return row


def repair_settings(cfg: dict) -> tuple[set, int]:
    ar = cfg.get("auto_repair")
    if not isinstance(ar, dict):
        ar = {}
    classes = {str(c) for c in ar.get("classes") or []}
    limit = int(ar.get("max_attempts_per_code_per_machine_per_day") or 0)
    return classes, limit


def _attempt_key(config: str | None, machine: str, code: str) -> str:
    return "%s|%s|%s" % (config or "", machine, code)


def _action_text(action: dict) -> str:
    return "%s %s: %s" % (action.get("code"), action.get("action"), action.get("result"))


def _failed_actions(actions: list) -> list:
    return [
        _action_text(a)
        for a in actions
        if str(a.get("result") or "").lower().startswith(("fail", "error"))
    ]


def repair_machine(
    row: dict,
    runner: Runner,
    env: dict,
    cfg: dict,
    attempts: dict,
    now: datetime.datetime,
) -> dict:
    """D-remedy, local side. Runs `rdc machine repair <m>` for the findings whose fix class is in `auto_repair.classes` and whose code is under the daily attempt limit. {codes, actions, rc, failed, advisories}; never raises. Operator-only and every class outside the config are never passed."""
    classes, limit = repair_settings(cfg)
    today = now.strftime("%Y-%m-%d")
    out: dict = {"codes": [], "actions": [], "rc": None, "failed": "", "advisories": []}
    for finding in row.get("findings") or []:
        fix = finding.get("fix")
        code = str(finding.get("code") or "")
        if not code or not isinstance(fix, dict) or str(fix.get("class") or "") not in classes:
            continue
        if code in out["codes"]:
            continue
        rec = attempts.get(_attempt_key(row["config"], row["machine"], code)) or {}
        if rec.get("day") == today and int(rec.get("n") or 0) >= limit:
            out["advisories"].append(
                "repair of %s skipped: %d attempts today (limit %d); run it by hand"
                % (code, int(rec.get("n") or 0), limit)
            )
            continue
        out["codes"].append(code)
    if not out["codes"]:
        return out
    args = ["machine", "repair", row["machine"], "-o", "json"]
    for code in out["codes"]:
        args += ["--code", code]
    if "auto-with-backup" in classes:
        args.append("--with-backup")
    res = runner(rdc_argv(env, row["config"] or None, args), env, REPAIR_TIMEOUT_S)
    out["rc"] = "timeout" if res.timed_out else res.rc
    data = envelope_data(res.stdout) if not res.timed_out else None
    raw = data.get("actions") if isinstance(data, dict) else None
    actions = [a for a in raw or [] if isinstance(a, dict)]
    out["actions"] = actions
    ran = {
        str(a.get("code"))
        for a in actions
        if not str(a.get("result") or "").lower().startswith(NOT_RUN_RESULTS)
    }
    for code in out["codes"]:
        if code in ran or not actions:
            key = _attempt_key(row["config"], row["machine"], code)
            rec = attempts.get(key) or {}
            n = int(rec.get("n") or 0) if rec.get("day") == today else 0
            attempts[key] = {"day": today, "n": n + 1}
    if res.timed_out or res.rc >= 2 or res.rc < 0:
        out["failed"] = "machine repair %s: %s" % (
            "timed out" if res.timed_out else "rc %d" % res.rc,
            "; ".join(_failed_actions(actions)) or _trim(res.stderr or "no action reported", 200),
        )
    return out


def repair_and_recheck(
    row: dict,
    config: str | None,
    runner: Runner,
    env: dict,
    cfg: dict,
    attempts: dict,
    now: datetime.datetime,
) -> dict:
    """The red row after its auto-repair and a full re-check, carrying `repair` (what ran) and `advisories`."""
    done = repair_machine(row, runner, env, cfg, attempts, now)
    if done["rc"] is None:
        row["advisories"] = done["advisories"]
        return row
    new = check_machine(config, row["machine"], runner, env, cfg)
    new["repair"] = {"codes": done["codes"], "rc": done["rc"], "actions": done["actions"]}
    new["advisories"] = done["advisories"]
    if done["failed"]:
        new["problems"].append(done["failed"])
        new["rc"], new["state"] = 1, RED
    return new


def machines_check(
    runner: Runner,
    env: dict,
    cfg: dict,
    *,
    attempts: dict | None = None,
    now: datetime.datetime | None = None,
) -> dict:
    """D-verdict over every config and machine. {rc, state, detail, rows, setup}. With `attempts` (the refresher passes its persisted counters) a red machine is auto-repaired and re-checked first (D-remedy)."""
    env = child_env(env)
    now = now or utcnow()
    rows: list[dict] = []
    setup: list[str] = []
    for config in configs_from_env(env):
        label = config or "(default config)"
        res = runner(rdc_argv(env, config, ["machine", "list", "-o", "json"]), env, RDC_TIMEOUT_S)
        data = envelope_data(res.stdout) if not res.timed_out else None
        if res.timed_out or res.rc != 0 or not isinstance(data, list):
            setup.append(
                "%s: machine list rc %s: %s"
                % (label, "timeout" if res.timed_out else res.rc, _trim(res.stderr, 200))
            )
            continue
        names = [str(m.get("name")) for m in data if isinstance(m, dict) and m.get("name")]
        if not names:
            setup.append("%s: machine list names no machine" % label)
            continue
        for name in names:
            row = check_machine(config, name, runner, env, cfg)
            if attempts is not None and row["rc"] == 1:
                row = repair_and_recheck(row, config, runner, env, cfg, attempts, now)
            rows.append(row)
    rc = worst_rc([r["rc"] for r in rows] + [2] * len(setup)) if (rows or setup) else 2
    return {
        "rc": rc,
        "state": state_of(rc),
        "rows": rows,
        "setup": setup,
        "detail": machines_detail(rows, setup),
    }


def machines_detail(rows: list, setup: list) -> str:
    lines = list(setup)
    for r in rows:
        head = "%s%s: %s" % (r["config"] + "/" if r["config"] else "", r["machine"], r["state"])
        lines.append(head)
        lines += ["  - %s" % p for p in r["problems"]]
        lines += ["  - unreadable: %s" % u for u in r.get("unreadable") or []]
        done = (r.get("repair") or {}).get("actions") or []
        lines += ["  - repaired: %s" % _action_text(x) for x in done]
        lines += ["  - %s" % x for x in r.get("advisories") or []]
        if r["no_check"]:
            lines.append("  - no check: %s" % ", ".join(r["no_check"]))
    return "\n".join(lines)


# --------------------------------------------------------------------------- off-box read (D-record)


@dataclasses.dataclass
class Reply:
    status: int
    text: str = ""
    error: str = ""


# (method, url, headers, json body or None) -> Reply. Injected by the tests.
Http = Callable[[str, str, dict, "dict | None"], Reply]


def http(method: str, url: str, headers: dict, body: dict | None = None) -> Reply:
    data = None
    headers = dict(headers)
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    try:
        request = https.build_request(url, data=data, headers=headers, method=method)
        with https.urlopen(request, timeout=HTTP_TIMEOUT_S) as resp:
            return Reply(resp.status, resp.read(2_000_000).decode("utf-8", "replace"))
    except urllib.error.HTTPError as exc:
        exc.close()
        return Reply(exc.code, "", "HTTP %d" % exc.code)
    except (OSError, ValueError) as exc:
        return Reply(0, "", type(exc).__name__)


def judge_status(doc: object, now: datetime.datetime, limit_min: float) -> dict:
    """{rc, reasons, last_cron_at, cron_age_min, verdict} for one `/v1/status` answer."""
    if not isinstance(doc, dict):
        return {"rc": 2, "reasons": ["status is not a JSON object"], "verdict": None}
    verdict = doc.get("verdict")
    last = parse_iso(doc.get("last_cron_at"))
    reasons: list[str] = []
    rc = 0
    age = None
    if last is None:
        reasons.append("last_cron_at is absent or unparseable")
        rc = 2
    else:
        age = (now - last).total_seconds() / 60.0
        if age > limit_min:
            reasons.append(
                "last_cron_at %s is %.0f min old (limit %.0f): the alerter is not running"
                % (iso(last), age, limit_min)
            )
            rc = 1
    if verdict == "red":
        rc = 1
        reasons.extend(
            "probe %s red since %s: %s"
            % (p.get("probe"), p.get("since") or "?", _trim(str(p.get("detail") or ""), 160))
            for p in doc.get("probes") or []
            if isinstance(p, dict) and p.get("state") == "red"
        )
        reasons.extend(
            "ingest %s red at %s: %s"
            % (e.get("source"), e.get("at") or "?", _trim(str(e.get("detail") or ""), 160))
            for e in doc.get("ingest") or []
            if isinstance(e, dict) and e.get("state") == "red"
        )
        if not any(r.startswith(("probe ", "ingest ")) for r in reasons):
            reasons.append("verdict red")
    elif verdict == "green":
        pass
    else:
        reasons.append("verdict %r is not green or red" % verdict)
        rc = 1 if rc == 1 else 2
    return {
        "rc": rc,
        "reasons": reasons,
        "verdict": verdict,
        "last_cron_at": iso(last) if last else None,
        "cron_age_min": round(age, 1) if age is not None else None,
        "targets_sha": doc.get("targets_sha"),
    }


def read_status(url: str, token: str, fetch: Http) -> tuple[object, str]:
    """(document, error). The error is "" on a 200 that parsed."""
    if not url:
        return None, "no Worker origin: set worker_url in %s or %s" % (CONFIG_REL, URL_ENV)
    if not token:
        return None, "%s is not set and the %s profile gave none" % (
            READ_CREDENTIAL_ENV,
            CREDENTIAL_PROFILE,
        )
    reply = fetch("GET", url + "/v1/status", {"Authorization": "Bearer " + token}, None)
    if reply.status != 200:
        return None, "GET /v1/status answered %s %s" % (reply.status or "no response", reply.error)
    try:
        return json.loads(reply.text), ""
    except ValueError:
        return None, "GET /v1/status answered 200 with a body that is not JSON"


def deploy_command(ref: str, path: str, config: str) -> str:
    return (
        "PYTHONPATH=.ci python3 -m rediacc_ci.ops.deploy_ops_health --targets-ref %s%s --targets-path %s --write"
        % (
            ref,
            " --config %s" % config if config else "",
            path,
        )
    )


def targets_drift(served_sha: object, env: dict, runner: Runner) -> tuple[int, str]:
    """(rc, reason) for the `ops.targets.drift` finding. (0, "") when OPS_HEALTH_TARGETS_REF is unset."""
    ref = env.get(TARGETS_REF_ENV) or ""
    if not ref:
        return 0, ""
    path = env.get(TARGETS_PATH_ENV) or ""
    config = env.get(TARGETS_CONFIG_ENV) or ""
    if not path:
        return 2, "%s is set but %s is not" % (TARGETS_REF_ENV, TARGETS_PATH_ENV)
    cenv = child_env(env)
    res = runner(
        rdc_argv(cenv, config or None, ["term", "connect", ref, "-c", "cat %s" % path]),
        cenv,
        RDC_TIMEOUT_S,
    )
    if res.timed_out or res.rc != 0:
        return 2, "reading %s:%s failed (rc %s)" % (
            ref,
            path,
            "timeout" if res.timed_out else res.rc,
        )
    sha = hashlib.sha256(res.stdout.encode("utf-8")).hexdigest()
    if str(served_sha or "") != sha:
        return 1, (
            "ops.targets.drift: the Worker serves targets_sha %s but %s:%s hashes to %s; "
            "re-deploy (operator-only, changes a production Worker): %s"
            % (served_sha or "(none)", ref, path, sha, deploy_command(ref, path, config))
        )
    return 0, ""


def offbox_check(
    cfg: dict, env: dict, fetch: Http, runner: Runner, now: datetime.datetime, with_targets: bool
) -> dict:
    """{rc, state, detail, last_cron_at, verdict, stale, read_at}."""
    doc, error = read_status(worker_url(cfg, env), env.get(READ_CREDENTIAL_ENV) or "", fetch)
    if error:
        return {"rc": 2, "state": UNKNOWN, "detail": error, "read_at": iso(now), "stale": False}
    judged = judge_status(doc, now, stale_min(cfg))
    reasons = list(judged["reasons"])
    rc = judged["rc"]
    if with_targets:
        drc, why = targets_drift(judged.get("targets_sha"), env, runner)
        if why:
            reasons.append(why)
        rc = worst_rc([rc, drc])
    return {
        "rc": rc,
        "state": state_of(rc),
        "detail": "\n".join(reasons) or "green",
        "verdict": judged.get("verdict"),
        "last_cron_at": judged.get("last_cron_at"),
        "cron_age_min": judged.get("cron_age_min"),
        "stale": any("the alerter is not running" in r for r in reasons),
        "stale_limit_min": stale_min(cfg),
        "read_at": iso(now),
    }


# --------------------------------------------------------------------------- subprocess checks


def subprocess_check(name: str, runner: Runner, env: dict) -> dict:
    profile, module = SUBPROCESS_CHECKS[name]
    py = sys.executable or "python3"
    argv = [py, "-m", module]
    if profile:
        argv = [py, "-m", "rediacc_ci.core.bws_env", "exec", "--profile", profile, "--", *argv]
    cenv = dict(env)
    cenv["PYTHONPATH"] = str(repo_root() / ".ci")
    res = runner(argv, cenv, SUBPROCESS_TIMEOUT_S)
    rc = 2 if res.timed_out else res.rc
    tail = "\n".join(((res.stdout or "") + "\n" + (res.stderr or "")).strip().splitlines()[-12:])
    return {
        "rc": rc if rc in (0, 1) else 2,
        "raw_rc": "timeout" if res.timed_out else res.rc,
        "state": state_of(rc),
        "detail": _trim(tail),
    }


# --------------------------------------------------------------------------- cache, ledger, ingest (L2)


def cache_dir(root: pathlib.Path) -> pathlib.Path:
    return root / CACHE_DIR_REL


def read_cache(root: pathlib.Path) -> dict:
    try:
        doc = json.loads((cache_dir(root) / STATE_NAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return doc if isinstance(doc, dict) else {}


def write_cache(root: pathlib.Path, doc: dict) -> None:
    d = cache_dir(root)
    d.mkdir(parents=True, exist_ok=True)
    tmp = d / (".%s.%d.tmp" % (STATE_NAME, os.getpid()))
    tmp.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, d / STATE_NAME)


def is_due(entry: object, ttl: int, now: datetime.datetime) -> bool:
    if not isinstance(entry, dict):
        return True
    at = parse_iso(entry.get("at"))
    return at is None or (now - at).total_seconds() >= ttl


def sources_of(check: str, entry: dict) -> dict:
    """source -> (state, detail) for the ingest and the ledger."""
    if check == "machines":
        out = {
            "local-machine-%s" % r["machine"]: (r["state"], machines_detail([r], []))
            for r in entry.get("rows") or []
        }
        if entry.get("setup"):
            out["local-machines"] = (UNKNOWN, "\n".join(entry["setup"]))
        return out
    if check == "offbox":
        return {}
    return {"local-%s" % check: (entry.get("state") or UNKNOWN, entry.get("detail") or "")}


def transitions(old: dict, new: dict, now: datetime.datetime) -> list:
    """Ledger rows for every source whose state differs from the cache's last one (first sight included)."""
    rows = []
    for source, (state, detail) in sorted(new.items()):
        before = (old.get(source) or (None, ""))[0]
        if before != state:
            rows.append(
                {
                    "at": iso(now),
                    "kind": "transition",
                    "source": source,
                    "from": before,
                    "to": state,
                    "detail": _trim(detail, 400),
                }
            )
    return rows


def repair_rows(entry: dict, now: datetime.datetime) -> list:
    """One ledger row per repair action the machines check ran."""
    return [
        {
            "at": iso(now),
            "kind": "repair",
            "source": "local-machine-%s" % row["machine"],
            "code": action.get("code"),
            "action": action.get("action"),
            "class": action.get("class"),
            "result": action.get("result"),
            "before": action.get("before"),
            "after": action.get("after"),
        }
        for row in entry.get("rows") or []
        for action in (row.get("repair") or {}).get("actions") or []
    ]


def append_ledger(root: pathlib.Path, rows: list) -> str:
    """The empty string on success, else the reason. Never raises."""
    if not rows:
        return ""
    try:
        path = root / LEDGER_REL
        path.parent.mkdir(parents=True, exist_ok=True)
        cache_dir(root).mkdir(parents=True, exist_ok=True)
        jsonl_append.append_lines(path, cache_dir(root) / LEDGER_LOCK_NAME, rows)
    except (OSError, ValueError, TypeError) as exc:
        return "%s: %s" % (type(exc).__name__, exc)
    return ""


def post_ingest(url: str, token: str, sources: dict, now: datetime.datetime, fetch: Http) -> dict:
    """{at, posted, errors}. A failure is recorded, never raised."""
    out: dict = {"at": iso(now), "posted": [], "errors": []}
    if not sources:
        return out
    if not url or not token:
        out["errors"].append(
            "ingest skipped: %s"
            % ("no Worker origin" if not url else "%s unavailable" % INGEST_CREDENTIAL_ENV)
        )
        return out
    for source, (state, detail) in sorted(sources.items()):
        body = {"source": source, "state": state, "detail": _trim(detail, 1000), "at": iso(now)}
        reply = fetch("POST", url + "/v1/ingest", {"Authorization": "Bearer " + token}, body)
        if 200 <= reply.status < 300:
            out["posted"].append(source)
        else:
            out["errors"].append(
                "%s: POST /v1/ingest answered %s %s"
                % (source, reply.status or "no response", reply.error)
            )
    return out


def take_lock(root: pathlib.Path, now: float | None = None) -> bool:
    """O_EXCL on refresh.lock; a lock older than LOCK_STALE_S is a dead refresher's and is taken over."""
    now = time.time() if now is None else now
    d = cache_dir(root)
    d.mkdir(parents=True, exist_ok=True)
    path = d / LOCK_NAME
    for _ in range(2):
        try:
            fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        except FileExistsError:
            try:
                age = now - path.stat().st_mtime
            except OSError:
                continue
            if age < LOCK_STALE_S:
                return False
            with contextlib.suppress(OSError):
                path.unlink()
            continue
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump({"pid": os.getpid(), "at": now}, fh)
        return True
    return False


def release_lock(root: pathlib.Path) -> None:
    with contextlib.suppress(OSError):
        (cache_dir(root) / LOCK_NAME).unlink()


def token_env(env: dict, hydrate: Callable[[list], dict] | None) -> tuple[dict, str]:
    """The environment with the ops-health tokens, fetched through the bws profile when the caller has none. ("", error) never raises."""
    if env.get(READ_CREDENTIAL_ENV) and env.get(INGEST_CREDENTIAL_ENV):
        return env, ""
    if hydrate is None:
        return env, ""
    try:
        return {**env, **hydrate([CREDENTIAL_PROFILE])}, ""
    except (RuntimeError, OSError, ValueError, KeyError) as exc:
        return env, "bws profile %s: %s" % (CREDENTIAL_PROFILE, str(exc)[:200])


def bws_hydrate(names: list) -> dict:
    try:
        env, _carried = bws_env.hydrate(names)
    except bws_env.RefusalError as refusal:
        raise RuntimeError(" ".join(refusal.lines)) from None
    return env


def refresh(
    root: pathlib.Path,
    *,
    force: bool = False,
    only: list | None = None,
    runner: Runner = run_process,
    fetch: Http = http,
    hydrate: Callable[[list], dict] | None = bws_hydrate,
    env: dict | None = None,
    now: datetime.datetime | None = None,
) -> tuple[int, dict]:
    """Run the due checks, write the cache, ledger the transitions, POST the fresh verdicts. (rc over every cached check, the cache)."""
    now = now or utcnow()
    env = dict(os.environ if env is None else env)
    cfg = load_config(root)
    cache = read_cache(root)
    checks = dict(cache.get("checks") or {})
    old_sources: dict = {}
    for name, entry in checks.items():
        if isinstance(entry, dict):
            old_sources.update(sources_of(name, entry))
    today = now.strftime("%Y-%m-%d")
    attempts = {
        k: v
        for k, v in (cache.get("repair_attempts") or {}).items()
        if isinstance(v, dict) and v.get("day") == today
    }
    wanted = [c for c in ALL_CHECKS if not only or c in only]
    due = [c for c in wanted if force or only or is_due(checks.get(c), ttl_s(cfg, c), now)]

    tenv, token_error = token_env(env, hydrate) if due else (env, "")
    fresh: dict = {}
    for name in due:
        if name == "machines":
            entry = machines_check(runner, env, cfg, attempts=attempts, now=now)
        elif name == "offbox":
            entry = offbox_check(cfg, tenv, fetch, runner, now, with_targets=True)
            if token_error and entry["state"] == UNKNOWN:
                entry["detail"] += "; " + token_error
        else:
            entry = subprocess_check(name, runner, env)
        entry["at"] = iso(now)
        entry["ttl_s"] = ttl_s(cfg, name)
        fresh[name] = entry
    checks.update(fresh)

    new_sources: dict = {}
    for name, entry in fresh.items():
        new_sources.update(sources_of(name, entry))
    ledger_rows = transitions(old_sources, new_sources, now)
    if "machines" in fresh:
        ledger_rows += repair_rows(fresh["machines"], now)
    ledger_error = append_ledger(root, ledger_rows)
    ingest = post_ingest(
        worker_url(cfg, tenv), tenv.get(INGEST_CREDENTIAL_ENV) or "", new_sources, now, fetch
    )
    if token_error and ingest["errors"]:
        ingest["errors"].append(token_error)

    doc = {
        "version": 1,
        "updated_at": iso(now),
        "checks": checks,
        "repair_attempts": attempts,
        "ingest": ingest if new_sources else cache.get("ingest") or {},
        "ledger": {"rows": len(ledger_rows), "error": ledger_error},
    }
    write_cache(root, doc)
    rcs = [int(e.get("rc", 2)) for e in checks.values() if isinstance(e, dict)]
    return worst_rc(rcs) if rcs else 2, doc


# --------------------------------------------------------------------------- CLI


def _print_entry(name: str, entry: dict, out) -> None:
    print("%s: %s (rc %s)" % (name, entry.get("state"), entry.get("rc")), file=out)
    for line in str(entry.get("detail") or "").splitlines():
        print("  %s" % line, file=out)


def gate_main(*, fetch: Http = http, env: dict | None = None, now=None) -> int:
    """The CI gate: red verdict or stale cron is 1, unreadable is 2. No target comparison."""
    env = dict(os.environ if env is None else env)
    root = repo_root()
    cfg = load_config(root)
    tenv, token_error = token_env(env, bws_hydrate if not env.get(READ_CREDENTIAL_ENV) else None)
    entry = offbox_check(cfg, tenv, fetch, run_process, now or utcnow(), with_targets=False)
    if token_error and entry["state"] == UNKNOWN:
        entry["detail"] += "; " + token_error
    if entry["rc"] == 0:
        print(
            "✓ ops-health: the off-box alerter's verdict is green and its last cron run is %s min old (limit %.0f)."
            % (entry.get("cron_age_min"), stale_min(cfg))
        )
        return 0
    word = "RED" if entry["rc"] == 1 else "UNREADABLE"
    print("✗ ops-health %s:" % word, file=sys.stderr)
    for line in str(entry.get("detail") or "").splitlines():
        print("    %s" % line, file=sys.stderr)
    return entry["rc"]


def main(argv: list | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="rediacc_ci.ops.ops_health", description=__doc__.splitlines()[0]
    )
    sub = parser.add_subparsers(dest="verb", required=True)
    p_m = sub.add_parser("machines")
    p_m.add_argument("--json", action="store_true")
    p_r = sub.add_parser("refresh")
    p_r.add_argument("--force", action="store_true")
    p_r.add_argument("--check", action="append", choices=ALL_CHECKS, default=[])
    p_r.add_argument("--lock-held", action="store_true")
    p_o = sub.add_parser("offbox")
    p_o.add_argument("--json", action="store_true")
    sub.add_parser("gate")
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return 2 if exc.code else 0
    root = repo_root()

    if args.verb == "gate":
        return gate_main()
    if args.verb == "machines":
        entry = machines_check(run_process, dict(os.environ), load_config(root))
        if args.json:
            print(json.dumps(entry, indent=2))
        else:
            _print_entry("machines", entry, sys.stdout)
        return entry["rc"]
    if args.verb == "offbox":
        env, token_error = token_env(dict(os.environ), bws_hydrate)
        entry = offbox_check(load_config(root), env, http, run_process, utcnow(), with_targets=True)
        if token_error and entry["state"] == UNKNOWN:
            entry["detail"] += "; " + token_error
        if args.json:
            print(json.dumps(entry, indent=2))
        else:
            _print_entry("offbox", entry, sys.stdout)
        return entry["rc"]

    # refresh
    if not args.lock_held and not take_lock(root):
        print(
            "ops_health refresh: %s/%s is held by a live refresher; nothing run."
            % (CACHE_DIR_REL, LOCK_NAME),
            file=sys.stderr,
        )
        return 2
    try:
        rc, doc = refresh(root, force=args.force, only=args.check or None)
    finally:
        release_lock(root)
    for name in ALL_CHECKS:
        cached = (doc.get("checks") or {}).get(name)
        if isinstance(cached, dict):
            _print_entry(name, cached, sys.stdout)
    for err in (doc.get("ingest") or {}).get("errors") or []:
        print("ingest: %s" % err, file=sys.stderr)
    if (doc.get("ledger") or {}).get("error"):
        print("ledger: %s" % doc["ledger"]["error"], file=sys.stderr)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
