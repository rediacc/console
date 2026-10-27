"""`rediacc_ci.ops.push_backup_credentials` with a recording fake runner and a fake HTTP layer: nothing reaches Cloudflare or the network.

The fake runner records every argv, its working directory and its stdin, and answers `wrangler secret list` from a name list the case controls. The values are SENTINELS, and the strongest assertions here are about where they never appear: in any argv, in the printed output, in wrangler's echoed output.
"""

from __future__ import annotations

import io
import json
import subprocess
import typing

import pytest

from rediacc_ci import paths
from rediacc_ci.ops import portal_health as ph
from rediacc_ci.ops import push_backup_credentials as pbc
from rediacc_ci.well_known import ACCOUNT_DEFAULT_ORIGIN

if typing.TYPE_CHECKING:
    import pathlib

KEY_ID = "SENTINEL-KEY-ID-7c1e"
SECRET = "SENTINEL-SECRET-9f2a"
ENDPOINT = "https://acct0000.r2.cloudflarestorage.com"
ENV = {
    "ACCOUNT_BACKUP_S3_ENDPOINT": ENDPOINT,
    "ACCOUNT_BACKUP_S3_ACCESS_KEY_ID": KEY_ID,
    "ACCOUNT_BACKUP_S3_SECRET_ACCESS_KEY": SECRET,
}
EXISTING = sorted(["ACCOUNT_JWT_SECRET", "ROOT_EMAIL", *pbc.PUSHED])
LOGIN = b'<html><script src="/account/assets/app-1.js"></script></html>'


class FakeWrangler:
    def __init__(
        self, before: list[str], after: list[str] | None = None, bulk_rc: int = 0, echo: str = ""
    ):
        self.lists = [before, before if after is None else after]
        self.bulk_rc = bulk_rc
        self.echo = echo
        self.calls: list[tuple[list[str], str, str | None]] = []

    def __call__(self, argv: list[str], cwd: str, stdin: str | None) -> tuple[int, str, str]:
        self.calls.append((list(argv), cwd, stdin))
        if argv[3:5] == ["secret", "list"]:
            names = self.lists.pop(0)
            return 0, "\n" + json.dumps([{"name": n, "type": "secret_text"} for n in names]), ""
        if argv[3:5] == ["secret", "bulk"]:
            return self.bulk_rc, "Uploaded 4 secrets %s\n" % self.echo, ""
        raise AssertionError("unexpected command %r" % argv)

    def bulk_calls(self) -> list[tuple[list[str], str, str | None]]:
        return [c for c in self.calls if c[0][3:5] == ["secret", "bulk"]]


def _fetch(healthy: list[bool]):
    """A fake HTTP layer whose portal is healthy while `healthy[0]` holds; each full health pass pops one entry."""

    def fetch(url: str) -> ph.Response:
        ok = healthy[0]
        if url.endswith("/account/api/v1/health"):
            if len(healthy) > 1:
                healthy.pop(0)
            return ph.Response(200 if ok else 503, "application/json", b'{"status":"ok"}')
        if url.endswith("/account/login"):
            return ph.Response(200, "text/html", LOGIN)
        return ph.Response(200 if ok else 404, "text/javascript")

    return fetch


def _push(
    p: pbc.Plan, runner, healthy=None, dry_run=False, environ=None
) -> tuple[str, int | Exception]:
    out = io.StringIO()
    try:
        rc: int | Exception = pbc.push(
            p,
            dry_run=dry_run,
            runner=runner,
            fetch=_fetch(healthy or [True, True]),
            environ=ENV if environ is None else environ,
            out=out,
        )
    except pbc.PushError as exc:
        rc = exc
    return out.getvalue(), rc


def _no_value_anywhere(runner: FakeWrangler, text: str) -> None:
    for argv, _cwd, _stdin in runner.calls:
        assert KEY_ID not in " ".join(argv)
        assert SECRET not in " ".join(argv)
    assert KEY_ID not in text
    assert SECRET not in text


def test_bench_pushes_exactly_four_keys_once_on_stdin() -> None:
    p = pbc.plan("bench", None)
    assert (p.worker, p.bucket, p.jurisdiction) == (
        "rediacc-account-bench",
        "rediacc-backups-bench",
        "",
    )
    runner = FakeWrangler(EXISTING)
    text, rc = _push(p, runner)
    assert rc == 0, rc
    (bulk,) = runner.bulk_calls()
    argv, cwd, stdin = bulk
    assert argv == [
        "npx",
        "--no-install",
        "wrangler",
        "secret",
        "bulk",
        "--name",
        "rediacc-account-bench",
    ]
    assert cwd == str(paths.repo_root() / "workers" / "account")
    assert json.loads(stdin or "") == {
        "ACCOUNT_BACKUP_S3_ENDPOINT": ENDPOINT,
        "ACCOUNT_BACKUP_S3_BUCKET": "rediacc-backups-bench",
        "ACCOUNT_BACKUP_S3_ACCESS_KEY_ID": KEY_ID,
        "ACCOUNT_BACKUP_S3_SECRET_ACCESS_KEY": SECRET,
    }
    lists = [c[0] for c in runner.calls if c[0][3:5] == ["secret", "list"]]
    assert lists == [pbc.list_argv("rediacc-account-bench")] * 2
    assert [c[0][3:5] for c in runner.calls] == [
        ["secret", "list"],
        ["secret", "bulk"],
        ["secret", "list"],
    ]
    _no_value_anywhere(runner, text)


def test_stable_eu_takes_the_eu_jurisdiction_host_and_its_own_bucket() -> None:
    p = pbc.plan("stable", "eu")
    assert (p.worker, p.bucket, p.jurisdiction, p.host) == (
        "rediacc-account-eu",
        "rediacc-backups-eu",
        "eu",
        ACCOUNT_DEFAULT_ORIGIN.split("://", 1)[1],
    )
    runner = FakeWrangler(EXISTING)
    _text, rc = _push(p, runner)
    assert rc == 0
    doc = json.loads(runner.bulk_calls()[0][2] or "")
    assert doc["ACCOUNT_BACKUP_S3_ENDPOINT"] == "https://acct0000.eu.r2.cloudflarestorage.com"
    assert doc["ACCOUNT_BACKUP_S3_BUCKET"] == "rediacc-backups-eu"


@pytest.mark.parametrize("region", ["eu", "us", "asia"])
def test_every_real_worker_config_agrees_with_regions_json(region: str) -> None:
    for target, prefix in (("stable", "rediacc-account-"), ("edge", "edge-rediacc-account-")):
        p = pbc.plan(target, region)
        assert p.worker == prefix + region
        assert p.bucket.endswith("rediacc-backups-" + region)


def test_a_changed_name_set_after_the_push_is_refused_loudly() -> None:
    runner = FakeWrangler(EXISTING, after=[*EXISTING, "SURPRISE"])
    text, rc = _push(pbc.plan("bench", None), runner)
    assert isinstance(rc, pbc.PushError)
    assert "CHANGED: added SURPRISE, removed none" in str(rc)
    _no_value_anywhere(runner, text + str(rc))


def test_a_red_portal_before_refuses_and_touches_nothing() -> None:
    runner = FakeWrangler(EXISTING)
    text, rc = _push(pbc.plan("bench", None), runner, healthy=[False, False])
    assert isinstance(rc, pbc.PushError)
    assert "RED before the push" in str(rc)
    assert runner.calls == []
    assert "RED" in text


def test_a_red_portal_after_names_the_rollback() -> None:
    runner = FakeWrangler(EXISTING)
    _text, rc = _push(pbc.plan("bench", None), runner, healthy=[True, False])
    assert isinstance(rc, pbc.PushError)
    assert "RED AFTER the push" in str(rc)
    assert "Roll back" in str(rc)
    assert len(runner.bulk_calls()) == 1


def test_dry_run_runs_only_the_read_only_steps() -> None:
    runner = FakeWrangler(EXISTING)
    text, rc = _push(pbc.plan("edge", "us"), runner, dry_run=True)
    assert rc == 0
    assert runner.bulk_calls() == []
    assert [c[0][3:5] for c in runner.calls] == [["secret", "list"]]
    for name in pbc.PUSHED:
        assert name in text
    assert "edge-rediacc-account-us" in text
    assert "nothing written" in text
    _no_value_anywhere(runner, text)


def test_a_failed_bulk_is_loud_and_its_output_is_masked() -> None:
    runner = FakeWrangler(EXISTING, bulk_rc=1, echo="debug %s %s" % (KEY_ID, SECRET))
    text, rc = _push(pbc.plan("bench", None), runner)
    assert isinstance(rc, pbc.PushError)
    assert "bulk failed (exit 1)" in str(rc)
    assert pbc.MASK in text
    _no_value_anywhere(runner, text)


def test_a_secret_the_worker_lacks_is_refused_before_the_write() -> None:
    runner = FakeWrangler([n for n in EXISTING if n != "ACCOUNT_BACKUP_S3_BUCKET"])
    _text, rc = _push(pbc.plan("bench", None), runner)
    assert isinstance(rc, pbc.PushError)
    assert "never adds a secret" in str(rc)
    assert runner.bulk_calls() == []


@pytest.mark.parametrize("missing", pbc.BOUND)
def test_a_missing_bound_value_is_refused_by_name(missing: str) -> None:
    runner = FakeWrangler(EXISTING)
    env = {k: v for k, v in ENV.items() if k != missing}
    _text, rc = _push(pbc.plan("bench", None), runner, environ=env)
    assert isinstance(rc, pbc.PushError)
    assert missing in str(rc)
    assert runner.calls == []


def test_a_second_environments_pair_in_reach_is_refused() -> None:
    runner = FakeWrangler(EXISTING)
    env = {**ENV, "ACCOUNT_BACKUP_S3_ACCESS_KEY_ID_STABLE": "x"}
    _text, rc = _push(pbc.plan("bench", None), runner, environ=env)
    assert isinstance(rc, pbc.PushError)
    assert "ACCOUNT_BACKUP_S3_ACCESS_KEY_ID_STABLE" in str(rc)
    assert runner.calls == []


def test_plan_refusals() -> None:
    with pytest.raises(pbc.PushError, match="needs --region"):
        pbc.plan("stable", None)
    with pytest.raises(pbc.PushError, match="no regions"):
        pbc.plan("bench", "eu")
    with pytest.raises(pbc.PushError, match="unknown region"):
        pbc.plan("edge", "mars")


def test_plan_refuses_a_config_that_binds_another_bucket(tmp_path: pathlib.Path) -> None:
    (tmp_path / "workers" / "account").mkdir(parents=True)
    (tmp_path / "regions.json").write_text(
        json.dumps(
            {
                "regions": [
                    {
                        "id": "eu",
                        "domain": "eu.example.test",
                        "edgeDomain": "edge-eu.example.test",
                        "workerName": "w-eu",
                        "edgeWorkerName": "edge-w-eu",
                        "backupR2": {"name": "b-eu"},
                        "edgeBackupR2": {"name": "edge-b-eu"},
                        "r2Jurisdiction": "eu",
                    }
                ]
            }
        )
    )
    toml = 'name = "w-eu"\n[[r2_buckets]]\nbinding = "BACKUP_BUCKET"\nbucket_name = "%s"\njurisdiction = "eu"\n'
    (tmp_path / "workers" / "account" / "wrangler.eu.toml").write_text(toml % "b-eu")
    assert pbc.plan("stable", "eu", root=tmp_path).bucket == "b-eu"
    (tmp_path / "workers" / "account" / "wrangler.eu.toml").write_text(toml % "edge-b-eu")
    with pytest.raises(pbc.PushError, match="disagree"):
        pbc.plan("stable", "eu", root=tmp_path)


def test_secret_names_reads_the_array_and_refuses_no_array() -> None:
    assert pbc.secret_names('warning\n[{"name": "B"}, {"name": "A"}]\n') == ["A", "B"]
    with pytest.raises(pbc.PushError):
        pbc.secret_names("Error: not authenticated")


def test_secret_names_skips_a_bracketed_log_line_and_trailing_text() -> None:
    """Review dcdd1ab6.2: slicing from the first `[` to the last `]` read `[WARNING] ...` as the start of the array and refused a good listing."""
    rows = '[\n  {"name": "B", "type": "secret_text"},\n  {"name": "A", "type": "secret_text"}\n]'
    out = "[WARNING] wrangler 3.x is out of date [update]\n%s\n[INFO] done in 1s [ok]\n" % rows
    assert pbc.secret_names(out) == ["A", "B"]
    assert pbc.secret_names("[]\n" + rows) == ["A", "B"], "an empty array does not hide the listing"
    assert pbc.secret_names("[WARNING] none\n[]\n") == []
    with pytest.raises(pbc.PushError, match="no JSON array"):
        pbc.secret_names("[WARNING] not authenticated [code 10000]\n")


def test_main_re_executes_under_its_own_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[list[str]] = []

    def fake_run(argv, **_kw):
        seen.append(list(argv))
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.delenv("REDIACC_BWS_PROFILES", raising=False)
    monkeypatch.setattr(pbc.subprocess, "run", fake_run)
    assert pbc.main(["--target", "edge", "--region", "eu", "--dry-run"]) == 0
    (argv,) = seen
    assert argv[1:6] == ["-m", "rediacc_ci.core.bws_env", "exec", "--profile", "backup-push-edge"]
    assert argv[-5:] == ["--target", "edge", "--region", "eu", "--dry-run"]


def test_main_usage_error_exits_2_before_any_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pbc.subprocess, "run", lambda *_a, **_k: pytest.fail("re-executed"))
    assert pbc.main(["--target", "stable"]) == 2
    assert pbc.main(["--target", "bench", "--region", "eu"]) == 2
    assert pbc.main(["--target", "edge", "--region", "mars"]) == 2


def test_main_a_config_mismatch_is_a_refusal_and_exits_1(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Review dcdd1ab6.1: regions.json contradicting the Worker's wrangler config is a refusal (exit 1), not a usage error (exit 2)."""
    (tmp_path / "workers" / "account").mkdir(parents=True)
    (tmp_path / "regions.json").write_text(
        json.dumps(
            {
                "regions": [
                    {
                        "id": "eu",
                        "domain": "eu.example.test",
                        "edgeDomain": "edge-eu.example.test",
                        "workerName": "w-eu",
                        "edgeWorkerName": "edge-w-eu",
                        "backupR2": {"name": "b-eu"},
                        "edgeBackupR2": {"name": "edge-b-eu"},
                        "r2Jurisdiction": "eu",
                    }
                ]
            }
        )
    )
    (tmp_path / "workers" / "account" / "wrangler.eu.toml").write_text(
        'name = "w-eu"\n[[r2_buckets]]\nbinding = "BACKUP_BUCKET"\nbucket_name = "edge-b-eu"\njurisdiction = "eu"\n'
    )
    monkeypatch.setattr(pbc.paths, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(pbc.subprocess, "run", lambda *_a, **_k: pytest.fail("re-executed"))
    assert pbc.main(["--target", "stable", "--region", "eu"]) == 1
    assert "disagree" in capsys.readouterr().err
