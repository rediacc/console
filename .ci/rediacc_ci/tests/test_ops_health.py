"""ops_health against an injected runner and HTTP function: no rdc call, no SSH and no request leaves the process (agent/plans/PLAN-health-checks-local.md L1, L2, L4)."""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import pathlib
import subprocess
import time
from typing import Any

import pytest

from rediacc_ci.ops import ops_health as oh

NOW = datetime.datetime(2026, 11, 6, 12, 0, tzinfo=datetime.UTC)
CFG = oh.load_config(pathlib.Path("/nonexistent"))


def envelope(data) -> str:
    return json.dumps({"success": True, "command": "x", "data": data, "errors": None})


HEALTH_OK = {"healthy": True, "exitCode": 0, "message": "ok", "issues": []}
LISTING_OK = {
    "repositories": [{"name": "app", "guid": "g-app", "autostart": True}],
    "backup_coverage": {"repos": [{"guid": "g-app", "name": "app", "age_days": 0}]},
}


def _verb_args(argv):
    """The rdc arguments after the program and any leading `--config <name>`."""
    args = list(argv[1:])
    return args[2:] if args[:1] == ["--config"] else args


class Fleet:
    """A scripted rdc: answers per (config, verb) and records every call with its environment."""

    def __init__(self, machines=("m1",), health=(0, HEALTH_OK), status=0, listing=LISTING_OK):
        # The default config and ENV's RDC_HEALTH_CONFIGS name ("prod") list `machines`; any other config the scenario did not script lists none, so a test cannot pass on machines it never meant a config to hold.
        self.machines: dict[str | None, list] = {None: list(machines), "prod": list(machines)}
        self.health = health
        self.status = status
        self.listing = listing
        self.calls: list[tuple[list, dict]] = []
        self.timeout_on: str | None = None

    def __call__(self, argv, env, _timeout):
        self.calls.append((list(argv), dict(env)))
        args = list(argv[1:])
        config = None
        if args[:1] == ["--config"]:
            config, args = args[1], args[2:]
        verb = " ".join(args[:2])
        if self.timeout_on and self.timeout_on in " ".join(args):
            return oh.Result(124, "", "", timed_out=True)
        if verb == "machine list":
            names = self.machines.get(config, [])
            return oh.Result(0, envelope([{"name": n} for n in names]))
        if verb == "machine health":
            rc, data = self.health
            return oh.Result(rc, envelope(data) if data is not None else "boom")
        if verb == "machine status":
            if "--health-check" in args or "--stability-check" in args:
                return oh.Result(self.status, "", "unhealthy" if self.status else "")
            return oh.Result(0, envelope(self.listing))
        return oh.Result(99, "", "unexpected %s" % argv)


def machines(fleet, env=None):
    return oh.machines_check(fleet, dict(env or {"PATH": "/usr/bin"}), CFG)


# --------------------------------------------------------------------------- L1


def test_green_machine_is_rc0():
    out = machines(Fleet())
    assert out["rc"] == 0, out["detail"]
    assert out["rows"][0]["state"] == "green"


def test_health_rc1_warning_is_red():
    out = machines(Fleet(health=(1, {**HEALTH_OK, "exitCode": 1, "issues": ["datastore 86%"]})))
    assert out["rc"] == 1
    assert "datastore 86%" in out["detail"]


def test_health_rc2_from_repo_health_error_is_red():
    data = {
        **HEALTH_OK,
        "exitCode": 2,
        "issues": ["repo mail health() error"],
        "findings": [{"code": "repo.health.error", "severity": "error", "subject": "mail"}],
    }
    out = machines(Fleet(health=(2, data)))
    assert out["rc"] == 1
    assert out["rows"][0]["findings"][0]["code"] == "repo.health.error"


def test_status_rc1_is_red():
    out = machines(Fleet(status=1))
    assert out["rc"] == 1
    assert "--containers rc 1" in out["detail"]
    assert "--services rc 1" in out["detail"]


def test_coverage_absent_for_autostart_repo_is_red():
    listing = {"repositories": [{"name": "mail", "guid": "g-m", "autostart": True}]}
    out = machines(Fleet(listing=listing))
    assert out["rc"] == 1
    assert "backup.coverage.absent: mail" in out["detail"]


def test_coverage_present_but_old_is_red_and_non_autostart_is_ignored():
    listing = {
        "repositories": [
            {"name": "a", "guid": "g-a", "autostart": True},
            {"name": "b", "guid": "g-b", "autostart": False},
        ],
        "backup_coverage": {"repos": [{"guid": "g-a", "age_days": 9}]},
    }
    out = machines(Fleet(listing=listing))
    assert out["rc"] == 1
    assert "backup.age.stale: a" in out["detail"]
    assert " b" not in out["detail"].replace("backup.age.stale: a", "")


def test_coverage_read_from_health_json_when_it_carries_repositories():
    data = {**HEALTH_OK, **LISTING_OK}
    fleet = Fleet(health=(0, data), listing={"repositories": [{"name": "x", "autostart": True}]})
    out = machines(fleet)
    assert out["rc"] == 0, out["detail"]
    assert not any(c[0][-2:] == ["-o", "json"] and "status" in c[0] for c in fleet.calls)


def test_repo_at_level_none_is_not_red_and_reported_as_no_check():
    data = {**HEALTH_OK, "repo_health": [{"name": "plain", "level": "none"}]}
    out = machines(Fleet(health=(0, data)))
    assert out["rc"] == 0
    assert out["rows"][0]["no_check"] == ["plain"]
    assert "no check: plain" in out["detail"]


def test_empty_machine_list_is_exit_2():
    out = machines(Fleet(machines=()))
    assert out["rc"] == 2
    assert "names no machine" in out["detail"]


def test_ssh_timeout_is_exit_2():
    fleet = Fleet()
    fleet.timeout_on = "machine health"
    out = machines(fleet)
    assert out["rc"] == 2
    assert out["state"] == "unknown"


def test_red_wins_over_unreadable_in_aggregate():
    fleet = Fleet(machines=("m1", "m2"), status=1)
    out = machines(fleet)
    assert out["rc"] == 1
    assert oh.worst_rc([2, 1, 0]) == 1


def test_no_provision_forced_even_when_caller_unset_it():
    fleet = Fleet()
    machines(fleet, env={"PATH": "/usr/bin"})
    assert fleet.calls
    assert all(env.get("REDIACC_NO_PROVISION") == "1" for _argv, env in fleet.calls)
    fleet2 = Fleet()
    machines(fleet2, env={"PATH": "/usr/bin", "REDIACC_NO_PROVISION": "0"})
    assert all(env.get("REDIACC_NO_PROVISION") == "1" for _argv, env in fleet2.calls)


def test_configs_from_env_and_the_default_config():
    assert oh.configs_from_env({}) == [None]
    assert oh.configs_from_env({"RDC_HEALTH_CONFIGS": " a, b ,"}) == ["a", "b"]
    fleet = Fleet()
    fleet.machines = {"a": ["x"], "b": ["y"]}
    out = machines(fleet, env={"RDC_HEALTH_CONFIGS": "a,b"})
    assert [(r["config"], r["machine"]) for r in out["rows"]] == [("a", "x"), ("b", "y")]
    assert all(c[0][1:3] in (["--config", "a"], ["--config", "b"]) for c in fleet.calls)


def test_source_names_no_machine_or_config():
    text = pathlib.Path(oh.__file__).read_text(encoding="utf-8")
    for word in ("hostinger", "eu-remote"):
        assert word not in text


# --------------------------------------------------------------------------- L2: cache, ledger, ingest, offbox


class Web:
    def __init__(self, status_doc=None, status_code=200, ingest_code=200):
        self.status_doc = status_doc
        self.status_code = status_code
        self.ingest_code = ingest_code
        self.calls: list = []

    def __call__(self, method, url, headers, body):
        self.calls.append((method, url, dict(headers), body))
        if url.endswith("/v1/status"):
            if self.status_doc is None:
                return oh.Reply(self.status_code, "", "HTTP %d" % self.status_code)
            return oh.Reply(self.status_code, json.dumps(self.status_doc))
        if url.endswith("/v1/ingest"):
            return oh.Reply(self.ingest_code, "{}", "" if self.ingest_code < 300 else "HTTP 500")
        return oh.Reply(404)


def status_doc(verdict="green", cron_age_min=5, probes=(), sha="abc"):
    return {
        "last_cron_at": oh.iso(NOW - datetime.timedelta(minutes=cron_age_min)),
        "targets_sha": sha,
        "verdict": verdict,
        "probes": list(probes),
        "ingest": [],
    }


ENV = {
    "PATH": "/usr/bin",
    "OPS_HEALTH_URL": "https://ops-health.example.test",
    "OPS_HEALTH_READ_TOKEN": "r",
    "OPS_HEALTH_INGEST_TOKEN": "i",
    "RDC_HEALTH_CONFIGS": "prod",
}


class Combined(Fleet):
    """The fleet plus the three subprocess checks, each with a scripted exit code."""

    def __init__(self, sub_rc=None, **kw):
        super().__init__(**kw)
        self.sub_rc = {"telemetry_delivery": 0, "portal_captcha": 0, "cf_usage_report": 0}
        self.sub_rc.update(sub_rc or {})

    def __call__(self, argv, env, timeout):
        joined = " ".join(argv)
        for mod, rc in self.sub_rc.items():
            if "rediacc_ci.ops." + mod in joined:
                self.calls.append((list(argv), dict(env)))
                return oh.Result(rc, "line %s" % mod)
        return super().__call__(argv, env, timeout)


def run_refresh(root, runner, web, now=NOW, env=None, **kw):
    return oh.refresh(
        root, runner=runner, fetch=web, hydrate=None, env=dict(env or ENV), now=now, **kw
    )


def ledger_rows(root):
    path = root / oh.LEDGER_REL
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def test_refresh_writes_cache_posts_ingest_and_runs_under_profiles(tmp_path):
    runner, web = Combined(), Web(status_doc())
    rc, doc = run_refresh(tmp_path, runner, web)
    assert rc == 0, json.dumps(doc, indent=1)
    cached = json.loads((tmp_path / oh.CACHE_DIR_REL / oh.STATE_NAME).read_text())
    assert set(cached["checks"]) == set(oh.ALL_CHECKS)
    posted = sorted(b["source"] for m, u, h, b in web.calls if m == "POST")
    assert posted == [
        "local-cf-usage",
        "local-machine-m1",
        "local-portal-captcha",
        "local-telemetry",
    ]
    assert all(h["Authorization"] == "Bearer i" for m, u, h, b in web.calls if m == "POST")
    argv_by_mod = {
        mod: next(a for a, _e in runner.calls if "rediacc_ci.ops." + mod in " ".join(a))
        for mod in ("telemetry_delivery", "cf_usage_report", "portal_captcha")
    }
    assert "--profile telemetry-probe" in " ".join(argv_by_mod["telemetry_delivery"])
    assert "--profile cf-usage-report" in " ".join(argv_by_mod["cf_usage_report"])
    assert "bws_env" not in " ".join(argv_by_mod["portal_captcha"])


def test_refresh_without_named_configs_posts_no_machine_verdict(tmp_path):
    # RDC_HEALTH_CONFIGS unset: the default config's machines (a dev box's VMs) are checked and cached, never sent to the production alerter.
    web = Web(status_doc())
    env = {k: v for k, v in ENV.items() if k != "RDC_HEALTH_CONFIGS"}
    rc, doc = run_refresh(tmp_path, Combined(), web, env=env)
    assert rc == 0, json.dumps(doc, indent=1)
    posted = sorted(b["source"] for m, u, h, b in web.calls if m == "POST")
    assert posted == ["local-cf-usage", "local-portal-captcha", "local-telemetry"]
    cached = (tmp_path / oh.CACHE_DIR_REL / oh.STATE_NAME).read_text()
    assert "m1" in cached


def test_subprocess_exit_contract_is_kept():
    for rc, state in ((0, "green"), (1, "red"), (2, "unknown"), (127, "unknown")):

        def run(_a, _e, _t, rc=rc):
            return oh.Result(rc)

        out = oh.subprocess_check("portal-captcha", run, {})
        assert out["state"] == state
        assert out["rc"] == (rc if rc in (0, 1) else 2)
    timed = oh.subprocess_check("telemetry", lambda _a, _e, _t: oh.Result(124, timed_out=True), {})
    assert timed["rc"] == 2


def test_unchanged_state_appends_no_ledger_row(tmp_path):
    web = Web(status_doc())
    run_refresh(tmp_path, Combined(), web, force=True)
    first = len(ledger_rows(tmp_path))
    assert first == 4  # first sight of each source
    run_refresh(tmp_path, Combined(), web, force=True, now=NOW + datetime.timedelta(minutes=1))
    assert len(ledger_rows(tmp_path)) == first


def test_one_to_zero_change_appends_one_row(tmp_path):
    web = Web(status_doc())
    run_refresh(tmp_path, Combined(status=1), web, force=True)
    before = ledger_rows(tmp_path)
    run_refresh(
        tmp_path, Combined(status=0), web, force=True, now=NOW + datetime.timedelta(minutes=1)
    )
    added = ledger_rows(tmp_path)[len(before) :]
    assert [(r["source"], r["from"], r["to"]) for r in added] == [
        ("local-machine-m1", "red", "green")
    ]


def test_failed_ingest_is_recorded_and_does_not_fail_refresh(tmp_path):
    web = Web(status_doc(), ingest_code=500)
    rc, doc = run_refresh(tmp_path, Combined(), web)
    assert rc == 0
    assert doc["ingest"]["posted"] == []
    assert len(doc["ingest"]["errors"]) == 4
    assert "500" in doc["ingest"]["errors"][0]


def test_missing_ingest_token_is_recorded_not_raised(tmp_path):
    env = {k: v for k, v in ENV.items() if k != "OPS_HEALTH_INGEST_TOKEN"}
    rc, doc = oh.refresh(
        tmp_path, runner=Combined(), fetch=Web(status_doc()), hydrate=None, env=env, now=NOW
    )
    assert rc == 0
    assert "OPS_HEALTH_INGEST_TOKEN unavailable" in doc["ingest"]["errors"][0]


def test_hydrate_failure_is_recorded(tmp_path):
    def boom(_names):
        raise RuntimeError("no token")

    env = {"PATH": "/usr/bin", "OPS_HEALTH_URL": "https://ops-health.example.test"}
    rc, doc = oh.refresh(
        tmp_path, runner=Combined(), fetch=Web(status_doc()), hydrate=boom, env=env, now=NOW
    )
    assert doc["checks"]["offbox"]["state"] == "unknown"
    assert "no token" in doc["checks"]["offbox"]["detail"]
    assert rc == 2


def test_only_due_checks_run(tmp_path):
    web = Web(status_doc())
    run_refresh(tmp_path, Combined(), web)
    runner = Combined()
    run_refresh(tmp_path, runner, web, now=NOW + datetime.timedelta(minutes=20))
    assert runner.calls == []  # machines 30 min, the rest longer
    runner2 = Combined()
    run_refresh(tmp_path, runner2, web, now=NOW + datetime.timedelta(minutes=31))
    joined = [" ".join(a) for a, _e in runner2.calls]
    assert any("machine health" in j for j in joined)
    assert not any("telemetry_delivery" in j for j in joined)


def test_target_sha_mismatch_is_red_with_deploy_command():
    body = '{"version":1}'
    good = hashlib.sha256(body.encode()).hexdigest()

    def term(argv, env, _timeout):
        assert env["REDIACC_NO_PROVISION"] == "1"
        assert "term" in argv
        assert "connect" in argv
        return oh.Result(0, body)

    env = {**ENV, "OPS_HEALTH_TARGETS_REF": "ops@box", "OPS_HEALTH_TARGETS_PATH": "targets.json"}
    red = oh.offbox_check(CFG, env, Web(status_doc(sha="stale")), term, NOW, with_targets=True)
    assert red["rc"] == 1
    assert "ops.targets.drift" in red["detail"]
    assert "rediacc_ci.ops.deploy_ops_health --targets-ref ops@box" in red["detail"]
    assert "--targets-path targets.json --write" in red["detail"]
    ok = oh.offbox_check(CFG, env, Web(status_doc(sha=good)), term, NOW, with_targets=True)
    assert ok["rc"] == 0, ok["detail"]


def test_offbox_without_targets_ref_does_not_read_the_repo():
    def never(*_a):
        raise AssertionError("no rdc call expected")

    out = oh.offbox_check(CFG, dict(ENV), Web(status_doc()), never, NOW, with_targets=True)
    assert out["rc"] == 0


def test_offbox_stale_is_flagged():
    def never(*_a):
        raise AssertionError("no rdc call expected")

    out = oh.offbox_check(CFG, dict(ENV), Web(status_doc(cron_age_min=31)), never, NOW, False)
    assert out["rc"] == 1
    assert out["stale"] is True


def test_lock_is_exclusive_and_stale_after_twenty_minutes(tmp_path):
    assert oh.take_lock(tmp_path, now=1000.0)
    assert not oh.take_lock(tmp_path, now=1000.0)
    lock = tmp_path / oh.CACHE_DIR_REL / oh.LOCK_NAME
    os.utime(lock, (1000.0, 1000.0))
    assert oh.take_lock(tmp_path, now=1000.0 + oh.LOCK_STALE_S + 1)
    oh.release_lock(tmp_path)
    assert not lock.exists()


def _dead_pid() -> int:
    proc = subprocess.Popen(["true"])
    proc.wait()
    return proc.pid


def test_lock_of_a_dead_pid_is_taken_over_at_once(tmp_path):
    assert oh.take_lock(tmp_path, now=1000.0)
    lock = tmp_path / oh.CACHE_DIR_REL / oh.LOCK_NAME
    lock.write_text(json.dumps({"pid": _dead_pid(), "at": 1000.0}), encoding="utf-8")
    os.utime(lock, (1000.0, 1000.0))
    assert oh.take_lock(tmp_path, now=1001.0)
    assert json.loads(lock.read_text(encoding="utf-8"))["pid"] == os.getpid()


def test_lock_of_a_live_pid_holds_until_it_is_stale(tmp_path):
    assert oh.take_lock(tmp_path, now=1000.0)
    lock = tmp_path / oh.CACHE_DIR_REL / oh.LOCK_NAME
    os.utime(lock, (1000.0, 1000.0))
    assert not oh.take_lock(tmp_path, now=1001.0)


def test_lock_held_refresher_stamps_only_the_lock_taken_for_it(tmp_path):
    assert oh.take_lock(tmp_path, now=1000.0)
    lock = tmp_path / oh.CACHE_DIR_REL / oh.LOCK_NAME
    lock.write_text(json.dumps({"pid": _dead_pid(), "at": 1000.0, "token": "t1"}), encoding="utf-8")
    assert oh.stamp_lock(tmp_path, "t1", now=1002.0)
    held = json.loads(lock.read_text(encoding="utf-8"))
    assert held["pid"] == os.getpid()
    assert held["start"] == oh.process_start(os.getpid())
    assert held["token"] == "t1"


def test_lock_held_never_stamps_over_another_holder(tmp_path):
    """A manual `refresh --lock-held` carries no token, and a lock another hook took carries another one (review 7acdec1f.3)."""
    assert oh.take_lock(tmp_path, now=1000.0)
    lock = tmp_path / oh.CACHE_DIR_REL / oh.LOCK_NAME
    other = {"pid": 1, "at": 1000.0, "token": "other"}
    lock.write_text(json.dumps(other), encoding="utf-8")
    assert not oh.stamp_lock(tmp_path, None, now=1002.0)
    assert not oh.stamp_lock(tmp_path, "mine", now=1002.0)
    assert json.loads(lock.read_text(encoding="utf-8")) == other


def test_zombie_and_reused_pid_are_not_live_holders(tmp_path):
    """os.kill(pid, 0) succeeds for both; /proc state and the recorded start time tell them apart (review 7acdec1f.4)."""
    zombie = subprocess.Popen(["true"])
    for _ in range(200):
        stat = oh._proc_stat(zombie.pid)
        if stat and stat[0] == "Z":
            break
        time.sleep(0.01)
    try:
        assert not oh.pid_alive(zombie.pid)
    finally:
        zombie.wait()
    me = os.getpid()
    start = oh.process_start(me)
    assert start is not None
    assert oh.pid_alive(me, start)
    assert not oh.pid_alive(me, start + 1)
    lock = tmp_path / oh.CACHE_DIR_REL / oh.LOCK_NAME
    lock.parent.mkdir(parents=True)
    lock.write_text(json.dumps({"pid": me, "start": start + 1, "at": 1000.0}), encoding="utf-8")
    os.utime(lock, (1000.0, 1000.0))
    assert oh.take_lock(tmp_path, now=1001.0)


# --------------------------------------------------------------------------- L4: the gate


def gate(web, env=None, now=NOW):
    return oh.gate_main(fetch=web, env=dict(env or ENV), now=now)


def test_gate_green_is_0():
    assert gate(Web(status_doc())) == 0


def test_gate_red_probe_exits_1(capsys):
    probe = {"probe": "tls-x", "state": "red", "since": "2026-11-06T10:00:00Z", "detail": "6 days"}
    assert gate(Web(status_doc(verdict="red", probes=[probe]))) == 1
    assert "probe tls-x red" in capsys.readouterr().err


def test_gate_stale_cron_exits_1(capsys):
    assert gate(Web(status_doc(cron_age_min=31))) == 1
    assert "31 min old" in capsys.readouterr().err


def test_gate_unreadable_status_exits_2():
    assert gate(Web(None, status_code=503)) == 2
    assert gate(Web(status_doc(verdict="unknown"))) == 2


def test_gate_with_no_env_or_config_origin_reads_the_registered_origin(monkeypatch):
    env = {k: v for k, v in ENV.items() if k != "OPS_HEALTH_URL"}
    monkeypatch.setattr(oh, "load_config", lambda _root: {})
    monkeypatch.setattr(oh.well_known, "OPS_HEALTH_ORIGIN", "https://registered.example.test")
    web = Web(status_doc())
    assert gate(web, env=env) == 0
    assert web.calls[0][1] == "https://registered.example.test/v1/status"


def test_gate_without_any_origin_is_2(monkeypatch):
    env = {k: v for k, v in ENV.items() if k != "OPS_HEALTH_URL"}
    monkeypatch.setattr(oh, "load_config", lambda _root: {})
    monkeypatch.setattr(oh.well_known, "OPS_HEALTH_ORIGIN", "")
    assert gate(Web(status_doc()), env=env) == 2


def test_control_gate_with_a_configured_origin_and_no_env_url_reads_it(monkeypatch):
    env = {k: v for k, v in ENV.items() if k != "OPS_HEALTH_URL"}
    monkeypatch.setattr(oh, "load_config", lambda _root: {"worker_url": "https://w.example.test"})
    assert gate(Web(status_doc()), env=env) == 0


def test_gate_script_runs_the_module_entry():
    script = pathlib.Path(oh.repo_root()) / ".ci/scripts/quality/check_ops_health.py"
    text = script.read_text(encoding="utf-8")
    assert "ops_health" in text
    assert "gate_main" in text
    proc = subprocess.run(
        [str(script), "--help"], capture_output=True, text=True, check=False, timeout=60
    )
    assert proc.returncode == 0, proc.stderr


@pytest.mark.parametrize(("rcs", "want"), [([0, 0], 0), ([0, 2], 2), ([2, 1], 1), ([], 0)])
def test_worst_rc(rcs, want):
    assert oh.worst_rc(rcs) == want


# --------------------------------------------------------------------------- L7 (D-remedy, local side)


def finding(code, klass="auto-safe", window_only=False, subject="m1"):
    return {
        "code": code,
        "severity": "warning",
        "subject": subject,
        "detail": code,
        "fix": {"action": "act-" + code, "class": klass, "window_only": window_only},
    }


def red_health(*findings):
    return (
        1,
        {
            **HEALTH_OK,
            "exitCode": 1,
            "issues": [f["code"] for f in findings],
            "findings": list(findings),
        },
    )


class RepairFleet(Fleet):
    """A fleet whose `machine repair` answers a scripted rc and actions, and turns `machine health` green once a repair ran with exit 0 or 1."""

    def __init__(self, findings, repair_rc=0, actions=None, heals=True, **kw):
        super().__init__(health=red_health(*findings), **kw)
        self.repair_rc = repair_rc
        self.actions = actions
        self.heals = heals
        self.repaired = False

    def repair_calls(self):
        return [a for a, _e in self.calls if _verb_args(a)[:2] == ["machine", "repair"]]

    def __call__(self, argv, env, timeout):
        args = _verb_args(argv)
        if args[:2] == ["machine", "repair"]:
            if self.timeout_on and self.timeout_on in " ".join(args):
                self.calls.append((list(argv), dict(env)))
                return oh.Result(124, "", "", timed_out=True)
            self.calls.append((list(argv), dict(env)))
            codes = [args[i + 1] for i, a in enumerate(args) if a == "--code"]
            actions = self.actions
            if actions is None:
                actions = [
                    {
                        "code": c,
                        "action": "act-" + c,
                        "class": "auto-safe",
                        "result": "fixed",
                        "before": "86%",
                        "after": "40%",
                    }
                    for c in codes
                ]
            if self.repair_rc < 2 and self.heals:
                self.repaired = True
            return oh.Result(
                self.repair_rc,
                envelope({"actions": actions}),
                "boom" if self.repair_rc == 2 else "",
            )
        if self.repaired and args[:2] == ["machine", "health"]:
            self.calls.append((list(argv), dict(env)))
            return oh.Result(0, envelope(HEALTH_OK))
        return super().__call__(argv, env, timeout)


def refreshed(tmp_path, fleet, now=NOW, cfg_extra=None):
    if cfg_extra is not None:
        (tmp_path / ".ci" / "config").mkdir(parents=True, exist_ok=True)
        (tmp_path / oh.CONFIG_REL).write_text(json.dumps(cfg_extra))
    web = Web(status_doc())
    out = oh.refresh(
        tmp_path, runner=fleet, fetch=web, hydrate=None, env={**ENV}, now=now, only=["machines"]
    )
    return out, web


def test_repair_auto_safe_finding_rechecks_green_posts_green_and_ledgers_one_action(tmp_path):
    fleet = RepairFleet([finding("datastore.usage.high")])
    (rc, doc), web = refreshed(tmp_path, fleet)
    assert rc == 0, json.dumps(doc, indent=1)
    (call,) = fleet.repair_calls()
    assert _verb_args(call) == [
        "machine",
        "repair",
        "m1",
        "-o",
        "json",
        "--code",
        "datastore.usage.high",
    ]
    posted = [(b["source"], b["state"]) for m, u, h, b in web.calls if m == "POST"]
    assert posted == [("local-machine-m1", "green")]
    repairs = [r for r in ledger_rows(tmp_path) if r["kind"] == "repair"]
    assert len(repairs) == 1
    assert repairs[0]["code"] == "datastore.usage.high"
    assert repairs[0]["result"] == "fixed"
    assert (repairs[0]["before"], repairs[0]["after"]) == ("86%", "40%")


def test_repair_call_carries_no_provision():
    fleet = RepairFleet([finding("a.b")])
    oh.machines_check(fleet, {"PATH": "/usr/bin"}, CFG, attempts={}, now=NOW)
    envs = [e for a, e in fleet.calls if a[1:3] == ["machine", "repair"]]
    assert envs
    assert all(e[oh.NO_PROVISION_ENV] == "1" for e in envs)


def test_repair_operator_only_finding_is_never_passed_and_stays_red(tmp_path):
    fleet = RepairFleet([finding("backup.coverage.absent", klass="operator-only")])
    (rc, _doc), _web = refreshed(tmp_path, fleet)
    assert rc == 1
    assert fleet.repair_calls() == []
    assert [r for r in ledger_rows(tmp_path) if r["kind"] == "repair"] == []


def test_repair_only_the_allowed_class_codes_are_passed(tmp_path):
    fleet = RepairFleet(
        [
            finding("safe.one"),
            finding("ops.only", klass="operator-only"),
            finding("needs.backup", klass="auto-with-backup"),
        ],
        heals=False,
    )
    refreshed(tmp_path, fleet)
    (call,) = fleet.repair_calls()
    assert call[call.index("--code") :] == ["--code", "safe.one"]
    assert "--with-backup" not in call


def test_repair_auto_with_backup_is_not_run_unless_configured_and_then_carries_the_flag(tmp_path):
    fleet = RepairFleet([finding("needs.backup", klass="auto-with-backup")], heals=False)
    refreshed(tmp_path, fleet)
    assert fleet.repair_calls() == []
    fleet2 = RepairFleet([finding("needs.backup", klass="auto-with-backup")], heals=False)
    refreshed(
        tmp_path / "second",
        fleet2,
        cfg_extra={"auto_repair": {"classes": ["auto-safe", "auto-with-backup"]}},
    )
    (call,) = fleet2.repair_calls()
    assert "--with-backup" in call


def test_repair_daily_limit_skips_the_fourth_attempt_with_an_advisory(tmp_path):
    findings = [finding("restart.loop")]
    for n in range(3):
        fleet = RepairFleet(findings, heals=False)
        refreshed(tmp_path, fleet, now=NOW + datetime.timedelta(minutes=40 * n))
        assert len(fleet.repair_calls()) == 1
    fleet = RepairFleet(findings, heals=False)
    (rc, doc), _web = refreshed(tmp_path, fleet, now=NOW + datetime.timedelta(minutes=200))
    assert fleet.repair_calls() == []
    assert rc == 1
    row = doc["checks"]["machines"]["rows"][0]
    assert "restart.loop skipped: 3 attempts today (limit 3)" in " ".join(row["advisories"])
    assert "limit 3" in doc["checks"]["machines"]["detail"]


def test_repair_daily_limit_resets_the_next_day(tmp_path):
    findings = [finding("restart.loop")]
    for n in range(3):
        step = datetime.timedelta(minutes=40 * n)
        refreshed(tmp_path, RepairFleet(findings, heals=False), now=NOW + step)
    fleet = RepairFleet(findings, heals=False)
    refreshed(tmp_path, fleet, now=NOW + datetime.timedelta(days=1))
    assert len(fleet.repair_calls()) == 1


def test_repair_skipped_action_does_not_use_up_an_attempt(tmp_path):
    findings = [finding("renet.binary.replaced", window_only=True)]
    skipped = [
        {
            "code": "renet.binary.replaced",
            "action": "restart",
            "class": "auto-safe",
            "result": "skipped: outside the window",
        }
    ]
    for n in range(5):
        fleet = RepairFleet(findings, actions=skipped, heals=False)
        refreshed(tmp_path, fleet, now=NOW + datetime.timedelta(minutes=40 * n))
        assert len(fleet.repair_calls()) == 1


def test_repair_exit_2_keeps_red_names_the_failed_action_and_is_recorded(tmp_path):
    failed = [
        {
            "code": "a.b",
            "action": "act-a.b",
            "class": "auto-safe",
            "result": "failed: docker said no",
        }
    ]
    fleet = RepairFleet([finding("a.b")], repair_rc=2, actions=failed)
    (rc, doc), web = refreshed(tmp_path, fleet)
    assert rc == 1
    row = doc["checks"]["machines"]["rows"][0]
    assert row["state"] == "red"
    assert any("machine repair rc 2" in p and "docker said no" in p for p in row["problems"])
    posted = [(b["source"], b["state"]) for m, u, h, b in web.calls if m == "POST"]
    assert posted == [("local-machine-m1", "red")]
    results = [r["result"] for r in ledger_rows(tmp_path) if r["kind"] == "repair"]
    assert results == ["failed: docker said no"]


def test_repair_timeout_is_red_not_raised(tmp_path):
    fleet = RepairFleet([finding("a.b")])
    fleet.timeout_on = "machine repair"
    (rc, doc), _web = refreshed(tmp_path, fleet)
    assert rc == 1
    assert any("timed out" in p for p in doc["checks"]["machines"]["rows"][0]["problems"])


def test_machines_verb_alone_never_repairs():
    fleet = RepairFleet([finding("a.b")])
    out = machines(fleet)
    assert out["rc"] == 1
    assert fleet.repair_calls() == []


def test_coverage_with_an_unknown_age_fails_closed():
    for age in (None, "9", True):
        listing = {
            "repositories": [{"name": "a", "guid": "g-a", "autostart": True}],
            "backup_coverage": {"repos": [{"guid": "g-a", "age_days": age}]},
        }
        out = machines(Fleet(listing=listing))
        assert out["rc"] == 1, age
        assert "backup.age.unknown: a" in out["detail"]


def test_health_rc1_with_no_json_is_red_not_unreadable():
    out = machines(Fleet(health=(1, None)))
    assert out["rows"][0]["rc"] == 1
    assert "printed no JSON" in out["detail"]


def test_health_rc0_with_no_json_stays_unreadable():
    out = machines(Fleet(health=(0, None)))
    assert out["rows"][0]["rc"] == 2


def test_a_machine_two_configs_share_keeps_both_verdicts_in_the_sources():
    rows = [
        {"config": "a", "machine": "m1", "state": "red", "problems": ["p"], "no_check": []},
        {"config": "b", "machine": "m1", "state": "green", "problems": [], "no_check": []},
        {"config": "a", "machine": "solo", "state": "green", "problems": [], "no_check": []},
    ]
    out = oh.sources_of("machines", {"rows": rows})
    assert out["local-machine-a-m1"][0] == "red"
    assert out["local-machine-b-m1"][0] == "green"
    assert "local-machine-solo" in out


def test_two_pairs_that_spell_one_source_name_keep_both_verdicts():
    """Each machine name is held by two configs, so both are joined to their config and (a, b-c) and (a-b, c) spell `local-machine-a-b-c`."""
    rows = [
        {"config": "a", "machine": "b-c", "state": "red", "problems": ["p"], "no_check": []},
        {"config": "a-b", "machine": "c", "state": "green", "problems": [], "no_check": []},
        {"config": "x", "machine": "b-c", "state": "green", "problems": [], "no_check": []},
        {"config": "x", "machine": "c", "state": "green", "problems": [], "no_check": []},
    ]
    names = oh.machine_sources(rows)
    colliding = [names[("a", "b-c")], names[("a-b", "c")]]
    assert colliding[0] != colliding[1]
    assert all(n.startswith("local-machine-a-b-c-") for n in colliding)
    out = oh.sources_of("machines", {"rows": rows})
    assert len(out) == 4
    assert sorted(out[n][0] for n in colliding) == ["green", "red"]


def test_repair_ledger_rows_use_the_source_of_the_machines_verdict():
    """Two configs share machine m1: each config's repair row names the same source its verdict does."""
    action = {"code": "a.b", "action": "act", "class": "auto-safe", "result": "ok"}
    rows: list[dict[str, Any]] = [
        {
            "config": cfg,
            "machine": "m1",
            "state": "green",
            "problems": [],
            "no_check": [],
            "repair": {"actions": [action], "rc": 0, "codes": ["a.b"]},
        }
        for cfg in ("a", "b")
    ]
    entry = {"rows": rows}
    sources = set(oh.sources_of("machines", entry))
    assert (
        {r["source"] for r in oh.repair_rows(entry, NOW)}
        == sources
        == {
            "local-machine-a-m1",
            "local-machine-b-m1",
        }
    )


def test_a_repair_that_exited_1_with_no_actions_is_ledgered_as_such():
    entry = {
        "rows": [
            {
                "config": "",
                "machine": "m1",
                "repair": {"actions": [], "rc": 1, "codes": ["a.b"]},
            }
        ]
    }
    rows = oh.repair_rows(entry, NOW)
    assert [(r["code"], r["result"]) for r in rows] == [("a.b", "no action reported (rc 1)")]


def test_subprocess_checks_carry_no_provision():
    seen = []

    def runner(_argv, env, _timeout):
        seen.append(env)
        return oh.Result(0, "ok")

    oh.subprocess_check("telemetry", runner, {"PATH": "/usr/bin", oh.NO_PROVISION_ENV: "0"})
    assert seen[0][oh.NO_PROVISION_ENV] == "1"


def test_repair_limit_zero_runs_no_repair_even_on_the_first_attempt():
    fleet = RepairFleet([finding("a.b")])
    out = oh.machines_check(
        fleet,
        {"PATH": "/usr/bin"},
        {**CFG, "auto_repair": {"classes": ["auto-safe"]}},
        attempts={},
        now=NOW,
    )
    assert fleet.repair_calls() == []
    assert "limit 0" in out["detail"]


def test_a_non_numeric_repair_limit_degrades_to_no_repair():
    classes, limit = oh.repair_settings(
        {"auto_repair": {"classes": ["x"], "max_attempts_per_code_per_machine_per_day": "many"}}
    )
    assert (classes, limit) == ({"x"}, 0)


def test_repair_that_reports_only_other_codes_still_counts_an_attempt():
    findings = [finding("a.b"), finding("c.d")]
    only_cd = [{"code": "c.d", "action": "act", "class": "auto-safe", "result": "fixed"}]
    attempts: dict = {}
    fleet = RepairFleet(findings, actions=only_cd, heals=False)
    oh.machines_check(fleet, {"PATH": "/usr/bin"}, CFG, attempts=attempts, now=NOW)
    assert attempts[oh._attempt_key("", "m1", "a.b")]["n"] == 1


def test_a_timed_out_repair_without_actions_is_ledgered(tmp_path):
    fleet = RepairFleet([finding("a.b")])
    fleet.timeout_on = "machine repair"
    refreshed(tmp_path, fleet)
    rows = [r for r in ledger_rows(tmp_path) if r["kind"] == "repair"]
    assert [(r["code"], r["result"]) for r in rows] == [("a.b", "no action reported (rc timeout)")]


def test_a_long_bws_refusal_keeps_its_first_200_characters():
    def hydrate(_names):
        raise RuntimeError("H" * 200 + "T" * 100)

    _env, error = oh.token_env({"PATH": "/usr/bin"}, hydrate)
    assert error.endswith("H" * 200)
    assert "T" not in error


@pytest.mark.parametrize("result", ["gone", "covered", "planned", "cancelled", "operator"])
def test_repair_results_that_ran_no_fix_do_not_use_up_attempts(tmp_path, result):
    # CONTROL: the result names `rdc machine repair` (RepairResult) gives an action it did not run.
    findings = [finding("restart.loop")]
    acts = [{"code": "restart.loop", "action": "restart", "class": "auto-safe", "result": result}]
    for n in range(5):
        fleet = RepairFleet(findings, actions=acts, heals=False)
        refreshed(tmp_path, fleet, now=NOW + datetime.timedelta(minutes=40 * n))
        assert len(fleet.repair_calls()) == 1


def test_config_file_keys_reach_the_readers(tmp_path):
    """The names in .ci/config/ops-health.json are the ones ttl_s and stale_min read, so a value set there is honoured."""
    cfg_dir = tmp_path / ".ci" / "config"
    cfg_dir.mkdir(parents=True)
    (cfg_dir / "ops-health.json").write_text(
        json.dumps(
            {
                "stale": {"last_cron_minutes": 45},
                "local_ttl_minutes": {
                    "portal_captcha": 7,
                    "cf_usage": 8,
                    "offbox_read": 9,
                    "machines": 11,
                },
            }
        ),
        encoding="utf-8",
    )
    cfg = oh.load_config(tmp_path)
    assert oh.stale_min(cfg) == 45.0
    assert oh.ttl_s(cfg, "portal-captcha") == 7 * 60
    assert oh.ttl_s(cfg, "cf-usage") == 8 * 60
    assert oh.ttl_s(cfg, "offbox") == 9 * 60
    assert oh.ttl_s(cfg, "machines") == 11 * 60


def test_the_repo_config_names_every_key_the_readers_use():
    """The key ttl_s derives for every check in ALL_CHECKS is in the shipped file and in DEFAULTS, so no check silently falls back to 30 minutes."""
    doc = json.loads(
        (
            pathlib.Path(__file__).resolve().parents[3] / ".ci" / "config" / "ops-health.json"
        ).read_text(encoding="utf-8")
    )
    derived = {oh.TTL_KEYS.get(check, check.replace("-", "_")) for check in oh.ALL_CHECKS}
    assert derived <= set(doc["local_ttl_minutes"])
    assert derived <= set(oh.DEFAULTS["local_ttl_minutes"])
    assert set(oh.DEFAULTS["local_ttl_minutes"]) <= set(doc["local_ttl_minutes"])
    assert set(oh.DEFAULTS["stale"]) <= set(doc["stale"])
