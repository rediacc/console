"""deploy_bench repeatability from a clean bench (finding 87f7acb9): signer and control databases first, wrangler resolved without PATH, the retired private-key secret removed, and a smoke that refuses a Worker serving 500. A fake runner stands in for every wrangler and child process; nothing reaches Cloudflare. The deploy's own end-to-end pass runs through `.ci/rediacc_ci/tests/deploy_bench_fakes.py`, the entry point `test_ops_cf_family.py` runs in place of `deploy_bench`; it replaces `_ensure_signers` and `smoke`, which this file covers."""

from __future__ import annotations

import json
import stat

import pytest

from rediacc_ci.deploy import deploy_signer
from rediacc_ci.enterprise import control_db
from rediacc_ci.ops import deploy_bench

VID = "0b1f2c3d-4e5f-4a6b-8c7d-9e0f1a2b3c4d"
ASSETS = '[assets]\ndirectory = "./bench/dist"\n'


def _world(monkeypatch, tmp_path, events):
    worker = tmp_path / "workers" / "account"
    worker.mkdir(parents=True)
    (worker / deploy_bench.CONFIG).write_text(ASSETS)
    (worker / "node_modules").mkdir()
    (tmp_path / "private/account/web/node_modules").mkdir(parents=True)
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "x")
    monkeypatch.setattr(deploy_bench, "secrets_payload", lambda: {"K": "v"})
    monkeypatch.setattr(deploy_bench, "root_password", lambda: "p")
    monkeypatch.setattr(deploy_bench.cf_auth, "await_propagation", lambda _a: None)
    monkeypatch.setattr(deploy_bench.bench_preflight, "lockfile", lambda _p: 0)
    monkeypatch.setattr(deploy_bench.bench_preflight, "buckets", lambda _c: 0)
    monkeypatch.setattr(deploy_bench.deploy_account, "check_queues", lambda *_a: [])
    monkeypatch.setattr(deploy_bench, "capture_bookmark", lambda _d: None)
    monkeypatch.setattr(deploy_bench, "_rotation_check", lambda _r: None)
    monkeypatch.setattr(deploy_bench, "_seed_and_report", lambda: None)
    monkeypatch.setattr(deploy_bench, "record_version", lambda *_a: None)
    monkeypatch.setattr(deploy_bench.deploy_record, "worker_version", lambda *_a: (True, "live"))
    monkeypatch.setattr(deploy_bench, "_remove_retired_secrets", lambda _d: [])
    monkeypatch.setattr(deploy_bench, "smoke", lambda: None)
    monkeypatch.setattr(
        deploy_bench,
        "_run",
        lambda argv, *_a, **_k: events.append(list(argv)) or "Current Version ID: " + VID,
    )


def test_signers_and_control_databases_come_before_the_account_deploy(monkeypatch, tmp_path):
    events: list[list[str]] = []
    _world(monkeypatch, tmp_path, events)
    deploy_bench._deploy(deploy_bench.cf_auth.Auth(token="t"), tmp_path)
    joined = [" ".join(e) for e in events]
    control = [i for i, e in enumerate(joined) if "control_db ensure --bench" in e]
    signers = [i for i, e in enumerate(joined) if "deploy_signer --target" in e]
    account = next(
        i for i, e in enumerate(joined) if e.endswith("deploy --config " + deploy_bench.CONFIG)
    )
    migrate = next(i for i, e in enumerate(joined) if "migrations apply" in e)
    assert len(control) == 1
    assert [joined[i].rsplit(" ", 1)[1] for i in signers] == ["bench-eu", "bench-us"]
    assert control[0] < signers[0] < signers[1] < migrate < account
    # the signer runs under its own profile, which binds the private key
    assert all("--profile deploy-signer" in joined[i] for i in signers)


def test_a_failing_signer_deploy_stops_before_the_account_deploy(monkeypatch, tmp_path):
    events: list[list[str]] = []
    _world(monkeypatch, tmp_path, events)

    def run(argv, *_a, **_k):
        events.append(list(argv))
        if "bench-eu" in argv:
            raise deploy_bench.DeployError("deploy_signer --target bench-eu failed (exit 1)")
        return "x"

    monkeypatch.setattr(deploy_bench, "_run", run)
    with pytest.raises(deploy_bench.DeployError, match="bench-eu"):
        deploy_bench._deploy(deploy_bench.cf_auth.Auth(token="t"), tmp_path)
    assert not any(e[-2:] == ["--config", deploy_bench.CONFIG] for e in events)


def _bin(root, name="signer"):
    d = root / "workers" / name / "node_modules" / ".bin"
    d.mkdir(parents=True)
    tool = d / "wrangler"
    tool.write_text("#!/bin/sh\necho resolved-local\n")
    tool.chmod(tool.stat().st_mode | stat.S_IXUSR)
    return d


def test_wrangler_resolves_from_the_repo_without_path(monkeypatch, tmp_path):
    bin_dir = _bin(tmp_path)
    monkeypatch.setenv("PATH", "/nonexistent")
    done = control_db.run_wrangler(["wrangler"], root=tmp_path)
    assert (done.rc, done.stdout.strip()) == (0, "resolved-local")
    assert control_db.wrangler_env(root=tmp_path)["PATH"].startswith(str(bin_dir))


def test_the_env_is_left_alone_when_no_local_wrangler_exists(monkeypatch, tmp_path):
    monkeypatch.setenv("PATH", "/usr/bin")
    assert control_db.wrangler_env(root=tmp_path)["PATH"] == "/usr/bin"


def test_the_signer_runner_resolves_wrangler_without_path(monkeypatch, tmp_path):
    _bin(tmp_path)
    monkeypatch.setenv("PATH", "/nonexistent")
    monkeypatch.setattr(control_db.paths, "repo_root", lambda: tmp_path)
    res = deploy_signer.run_process(["wrangler"], tmp_path, None)
    assert (res.rc, res.stdout.strip()) == (0, "resolved-local")


def _lister(names):
    calls: list[list[str]] = []

    def run(argv, _cwd, _what, **_kw):
        calls.append(list(argv))
        if "list" in argv:
            rows = [{"name": n, "type": "secret_text"} for n in names]
            return "wrangler banner\n" + json.dumps(rows)
        return ""

    return run, calls


def test_the_retired_private_key_secret_is_deleted_and_nothing_else(tmp_path):
    run, calls = _lister(["ACCOUNT_JWT_SECRET", deploy_signer.PRIVATE_KEY, "ROOT_EMAIL"])
    assert deploy_bench._remove_retired_secrets(tmp_path, run) == [deploy_signer.PRIVATE_KEY]
    deletes = [c for c in calls if "delete" in c]
    assert len(deletes) == 1
    assert deletes[0][-3:] == [deploy_signer.PRIVATE_KEY, "--name", "account-bench"]


def test_a_clean_secret_list_deletes_nothing(tmp_path):
    run, calls = _lister(["ACCOUNT_JWT_SECRET", deploy_signer.PUBLIC_KEY])
    assert deploy_bench._remove_retired_secrets(tmp_path, run) == []
    assert not any("delete" in c for c in calls)


def test_an_unreadable_secret_list_is_a_named_error(tmp_path):
    with pytest.raises(deploy_bench.DeployError, match="secret list"):
        deploy_bench._remove_retired_secrets(tmp_path, lambda *_a, **_k: "no json here")


def test_the_deploy_removes_retired_secrets_then_smokes(monkeypatch, tmp_path):
    events: list[list[str]] = []
    _world(monkeypatch, tmp_path, events)
    seen: list[str] = []

    def remove(_d):
        seen.append("rm")
        return []

    def smoke():
        seen.append("smoke")

    monkeypatch.setattr(deploy_bench, "_remove_retired_secrets", remove)
    monkeypatch.setattr(deploy_bench, "smoke", smoke)
    deploy_bench._deploy(deploy_bench.cf_auth.Auth(token="t"), tmp_path)
    assert seen == ["rm", "smoke"]


def test_smoke_failing_on_500_makes_main_exit_nonzero(monkeypatch, capsys):
    with pytest.raises(deploy_bench.DeployError, match=r"server-info answered 500"):
        deploy_bench.smoke(lambda _u: 500, lambda _s: None)
    monkeypatch.setattr(deploy_bench, "_reexec_under_profile", lambda _a: None)
    monkeypatch.setattr(deploy_bench.shutil, "which", lambda _c: "/bin/x")
    auth = deploy_bench.cf_auth.Auth(token="t")
    monkeypatch.setattr(deploy_bench.cf_auth, "resolve", lambda _a: auth)
    monkeypatch.setattr(deploy_bench.cf_auth, "self_destruct", lambda _a: None)

    def failing(_a, _r):
        deploy_bench.smoke(lambda _u: 500, lambda _s: None)

    monkeypatch.setattr(deploy_bench, "_deploy", failing)
    assert deploy_bench.main([]) == 1
    assert "answered 500" in capsys.readouterr().err


def test_smoke_passes_on_200_and_retries_a_propagation_lag():
    urls: list[str] = []
    answers = iter([502, 200])

    def fetch(url):
        urls.append(url)
        return next(answers)

    waits: list[float] = []
    deploy_bench.smoke(fetch, waits.append)
    assert urls == ["https://%s/account/api/v1/.well-known/server-info" % deploy_bench.DOMAIN] * 2
    assert len(waits) == 1


def test_smoke_stops_asking_after_its_attempts():
    n: list[int] = []

    def fetch(_u):
        n.append(1)
        return 0

    with pytest.raises(deploy_bench.DeployError, match="answered 0"):
        deploy_bench.smoke(fetch, lambda _s: None)
    assert len(n) == deploy_bench.SMOKE_ATTEMPTS


def test_an_unset_path_leaves_no_empty_entry(monkeypatch, tmp_path):
    bin_dir = _bin(tmp_path)
    monkeypatch.delenv("PATH", raising=False)
    path = control_db.wrangler_env(root=tmp_path)["PATH"]
    assert path.startswith(str(bin_dir))
    assert "" not in path.split(":"), "an empty PATH entry searches the working directory"


def test_a_missing_curl_reads_as_no_answer(monkeypatch):
    def missing(_url):
        raise FileNotFoundError("curl")

    monkeypatch.setattr(deploy_bench, "_run_curl", missing)
    assert deploy_bench._http_status("https://bench.example/") == 0
    with pytest.raises(deploy_bench.DeployError):
        deploy_bench.smoke(sleep=lambda _s: None)
