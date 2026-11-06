"""rediacc_ci.ops.deploy_ops_health (agent/plans/PLAN-health-checks-local.md W4), against fakes only.

A recording runner stands in for `rdc` and `wrangler`, and a fake Worker answers the status read from what the fake `wrangler deploy` last set, so a second run sees exactly what the first one deployed. Nothing here reaches Cloudflare, a machine or the network.
"""

from __future__ import annotations

import email.message
import json
import pathlib
import subprocess
import urllib.error
from typing import Any, Self

import pytest

from rediacc_ci.ops import deploy_ops_health as d

PROBES: list[dict[str, Any]] = [
    {"id": "smtps", "kind": "banner-465", "host": "mail.example.test"},
    {
        "id": "imaps",
        "kind": "tls",
        "host": "mail.example.test",
        "port": 993,
        "expect": "Let's Encrypt",
    },
]

GOOD: dict[str, Any] = {
    "version": 1,
    "probes": PROBES,
    "dnsbl": {"ip": "192.0.2.10", "zones": ["bl.example.test"]},
}

SECRETS = {
    "OPS_ALERT_EMAILS": "ops@example.test",
    "AWS_SES_ACCESS_KEY_ID_EU": "AKID-SECRET-VALUE",
    "AWS_SES_SECRET_ACCESS_KEY_EU": "ses-secret-value-xyz",
    "AWS_SES_REGION_EU": "eu-central-1",
    "AWS_SES_FROM": "alerts@example.test",
    "OPS_HEALTH_READ_TOKEN": "read-token-value",
    "OPS_HEALTH_INGEST_TOKEN": "ingest-token-value",
}

ARGS = ["--targets-ref", "ops@box", "--config", "cfg", "--targets-path", "targets.json"]


class FakeWorld:
    """The rdc side (the target file) and the Cloudflare side (what is deployed), behind one runner."""

    def __init__(self, targets: str):
        self.targets = targets
        self.term_rc = 0
        self.calls: list[dict] = []
        self.deployed: d.Deployed | None = None
        self.secrets: dict[str, str] = {}
        self.wrangler_rc = 0

    def run(self, argv, **kwargs):
        argv = list(argv)
        self.calls.append(
            {
                "argv": argv,
                "input": kwargs.get("input"),
                "env": kwargs.get("env"),
                "cwd": kwargs.get("cwd"),
            }
        )
        if argv[0].endswith("rdc.sh"):
            if "term" in argv:
                return subprocess.CompletedProcess(
                    argv, self.term_rc, self.targets if self.term_rc == 0 else "", "term failed"
                )
            local = argv[argv.index("--local") + 1]
            name = pathlib.PurePosixPath(argv[argv.index("--remote-file") + 1]).name
            pathlib.Path(local, name).write_text(self.targets, encoding="utf-8")
            return subprocess.CompletedProcess(argv, 0, "", "")
        if argv[:3] == ["npx", "--no-install", "wrangler"]:
            if self.wrangler_rc:
                return subprocess.CompletedProcess(argv, self.wrangler_rc)
            verb = argv[3]
            if verb == "secret":
                self.secrets.update(json.loads(kwargs["input"]))
            elif verb == "deploy":
                vars_ = dict(argv[i + 1].split(":", 1) for i, a in enumerate(argv) if a == "--var")
                digests = dict(p.split("=") for p in vars_[d.VAR_DIGESTS].split(",") if p)
                self.deployed = d.Deployed(vars_[d.VAR_TARGETS_SHA], vars_[d.VAR_CODE_SHA], digests)
            return subprocess.CompletedProcess(argv, 0)
        raise AssertionError("unexpected command %r" % argv)

    def seams(self) -> d.Seams:
        return d.Seams(
            run=self.run,
            fetch_deployed=lambda _url, _token: self.deployed,
            wrangler_env=lambda env: ({**env, "CLOUDFLARE_API_TOKEN": "cf-token"}, lambda: None),
        )

    def wrangler_calls(self) -> list[dict]:
        return [c for c in self.calls if c["argv"][:3] == ["npx", "--no-install", "wrangler"]]


def run_main(world: FakeWorld, *extra: str, env: dict | None = None) -> int:
    return d.main([*ARGS, *extra], world.seams(), environ=dict(SECRETS if env is None else env))


def test_a_second_write_with_an_unchanged_file_reports_zero_changes(capsys):
    world = FakeWorld(json.dumps(GOOD))
    assert run_main(world, "--write") == 0
    first = len(world.wrangler_calls())
    assert first == 3  # create, secrets, deploy with the digests
    capsys.readouterr()
    assert run_main(world, "--write") == 0
    assert len(world.wrangler_calls()) == first, "an unchanged input must run no wrangler step"
    assert "0 changes" in capsys.readouterr().out


def test_an_invalid_target_file_exits_2_before_any_deploy(capsys):
    world = FakeWorld(
        json.dumps({"version": 1, "probes": [{"id": "Bad Id", "kind": "tls", "host": "h.test"}]})
    )
    assert run_main(world, "--write") == 2
    assert world.wrangler_calls() == []
    assert "invalid" in capsys.readouterr().err


def test_a_changed_file_changes_only_the_secret_and_the_sha(capsys):
    world = FakeWorld(json.dumps(GOOD))
    assert run_main(world, "--write") == 0
    before = len(world.wrangler_calls())
    changed = dict(
        GOOD, probes=[*PROBES, {"id": "web", "kind": "https", "host": "app.example.test"}]
    )
    world.targets = json.dumps(changed)
    capsys.readouterr()
    assert run_main(world, "--write") == 0
    out = capsys.readouterr().out
    assert "2 change(s): secret:OPS_HEALTH_TARGETS, var:OPS_HEALTH_TARGETS_SHA" in out
    new_calls = world.wrangler_calls()[before:]
    bulk = [c for c in new_calls if c["argv"][3] == "secret"]
    assert len(bulk) == 1
    assert list(json.loads(bulk[0]["input"])) == ["OPS_HEALTH_TARGETS"]
    assert world.deployed is not None
    assert world.deployed.targets_sha == d.sha256_hex(world.targets.encode())


def test_dry_run_is_the_default_and_runs_no_wrangler(capsys):
    world = FakeWorld(json.dumps(GOOD))
    assert run_main(world) == 0
    assert world.wrangler_calls() == []
    out = capsys.readouterr().out
    assert "worker:create" in out
    assert "dry run" in out


@pytest.mark.parametrize("drop", ["--targets-ref", "--config", "--targets-path"])
def test_every_argument_is_required(drop):
    args = list(ARGS)
    i = args.index(drop)
    del args[i : i + 2]
    with pytest.raises(SystemExit) as exc:
        d.parse_args(args)
    assert exc.value.code == 2


def test_the_rdc_read_forces_no_provision_and_names_config_and_ref():
    world = FakeWorld(json.dumps(GOOD))
    env = {**SECRETS, "REDIACC_NO_PROVISION": "0"}
    assert run_main(world, env=env) == 0
    rdc = world.calls[0]
    assert rdc["env"]["REDIACC_NO_PROVISION"] == "1"
    assert rdc["argv"][1:6] == ["--config", "cfg", "term", "connect", "ops@box"]
    assert rdc["argv"][-1] == "cat -- 'targets.json'"


def test_a_failed_term_read_falls_back_to_sync_download():
    world = FakeWorld(json.dumps(GOOD))
    world.term_rc = 1
    assert run_main(world) == 0
    assert any("download" in c["argv"] for c in world.calls)


def test_no_secret_value_reaches_an_argv_and_secrets_travel_on_stdin():
    world = FakeWorld(json.dumps(GOOD))
    assert run_main(world, "--write") == 0
    values = [v for v in SECRETS.values() if len(v) > 8]
    for call in world.calls:
        joined = " ".join(call["argv"])
        for value in values:
            assert value not in joined
    bulk = next(c for c in world.wrangler_calls() if c["argv"][3] == "secret")
    assert (
        json.loads(bulk["input"])["AWS_SES_SECRET_ACCESS_KEY_EU"]
        == SECRETS["AWS_SES_SECRET_ACCESS_KEY_EU"]
    )


def test_a_first_deploy_creates_then_puts_secrets_then_writes_the_digests():
    world = FakeWorld(json.dumps(GOOD))
    assert run_main(world, "--write") == 0
    verbs = [c["argv"][3] for c in world.wrangler_calls()]
    assert verbs == ["deploy", "secret", "deploy"]
    first_vars = world.wrangler_calls()[0]["argv"]
    assert "%s:" % d.VAR_DIGESTS in first_vars, "the create step must not claim the secrets are in"
    assert all(c["cwd"].endswith("workers/ops-health") for c in world.wrangler_calls())


def test_a_failed_secret_step_leaves_the_vars_behind_so_a_rerun_retries(capsys):
    world = FakeWorld(json.dumps(GOOD))
    assert run_main(world, "--write") == 0
    world.targets = json.dumps(dict(GOOD, probes=PROBES[:1]))
    world.wrangler_rc = 1
    assert run_main(world, "--write") == 1
    world.wrangler_rc = 0
    capsys.readouterr()
    assert run_main(world, "--write") == 0
    assert "secret:OPS_HEALTH_TARGETS" in capsys.readouterr().out


def test_missing_secrets_exit_3_naming_the_profile(capsys):
    world = FakeWorld(json.dumps(GOOD))
    env = {k: v for k, v in SECRETS.items() if k != "AWS_SES_FROM"}
    assert run_main(world, env=env) == d.EXIT_NO_SECRETS
    err = capsys.readouterr().err
    assert "AWS_SES_FROM" in err
    assert "--profile ops-health" in err


@pytest.mark.parametrize(
    "doc",
    [
        "{not json",
        {"version": 2, "probes": []},
        {"version": True, "probes": []},
        {"version": 1},
        {
            "version": 1,
            "probes": [
                {"id": "a", "kind": "tls", "host": "h.test"},
                {"id": "a", "kind": "tls", "host": "h.test"},
            ],
        },
        {"version": 1, "probes": [{"id": "mailer", "kind": "tls", "host": "h.test"}]},
        {"version": 1, "probes": [{"id": "health:account-eu", "kind": "tls", "host": "h.test"}]},
        {"version": 1, "probes": [{"id": "a", "kind": "tls", "host": "h.test", "port": 70000}]},
        {"version": 1, "probes": [{"id": "a", "kind": "tls", "host": "h.test/x"}]},
        {"version": 1, "probes": [], "dnsbl": {"ip": "999.1.1.1", "zones": []}},
        {"version": 1, "probes": [], "dnsbl": {"ip": "2001:db8::1", "zones": []}},
    ],
)
def test_the_schema_refuses_what_the_worker_refuses(doc):
    text = doc if isinstance(doc, str) else json.dumps(doc)
    with pytest.raises(d.TargetsInvalidError):
        d.validate_targets(text)


def test_the_schema_counts_dnsbl_zones_as_probes():
    assert d.validate_targets(json.dumps(GOOD)) == 3


def test_the_status_url_comes_from_the_custom_domain_route():
    assert d.status_url(d.paths.repo_root()) == "https://ops-health.rediacc.com/v1/status"


def test_the_digest_var_survives_wrangler_var_syntax():
    encoded = d.encode_digests({"B": "00ff", "A": "abcd"})
    assert encoded == "A=abcd,B=00ff"
    assert ":" not in encoded
    assert '"' not in encoded


# CONTROL for review d7c95c5d.1: an HTTP error from /v1/status other than 404 is not a first deploy.
class _Resp:
    def __init__(self, body: bytes) -> None:
        self._body = body

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_a: object) -> None:
        return None

    def read(self) -> bytes:
        return self._body


def _http_error(code: int) -> Exception:
    return urllib.error.HTTPError("https://x", code, "status", email.message.Message(), None)


def _fetch_with(monkeypatch: pytest.MonkeyPatch, outcome: Any) -> Any:
    def urlopen(_request: Any, **_kw: Any) -> Any:
        if isinstance(outcome, BaseException):
            raise outcome
        return _Resp(outcome)

    monkeypatch.setattr(d.https, "urlopen", urlopen)
    return d.fetch_deployed("https://ops-health.example.test/v1/status", "tok")


@pytest.mark.parametrize("code", [401, 403, 500, 503])
def test_control_a_refused_or_failing_status_raises_rather_than_reading_as_first_deploy(
    monkeypatch: pytest.MonkeyPatch, code: int
) -> None:
    with pytest.raises(d.StatusUnreadableError, match="HTTP %d" % code):
        _fetch_with(monkeypatch, _http_error(code))


def test_a_404_or_an_unreachable_host_is_a_first_deploy(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _fetch_with(monkeypatch, _http_error(404)) is None
    assert _fetch_with(monkeypatch, urllib.error.URLError("Name or service not known")) is None


def test_a_non_json_status_body_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(d.StatusUnreadableError, match="not JSON"):
        _fetch_with(monkeypatch, b"<html>")


def test_main_refuses_to_deploy_when_the_status_is_unreadable(
    capsys: pytest.CaptureFixture[str],
) -> None:
    world = FakeWorld(json.dumps(GOOD))
    base = world.seams()

    def refused(_url: str, _token: str) -> d.Deployed | None:
        raise d.StatusUnreadableError("https://ops-health.example.test/v1/status answered HTTP 401")

    seams = d.Seams(run=base.run, fetch_deployed=refused, wrangler_env=base.wrangler_env)
    rc = d.main([*ARGS, "--write"], seams, environ=dict(SECRETS))
    assert rc == d.EXIT_FAILED
    assert world.wrangler_calls() == []
    assert "HTTP 401" in capsys.readouterr().err


class _Auth:
    created = True
    token = "minted"


def test_a_failed_propagation_wait_still_destroys_the_minted_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    destroyed: list[object] = []
    auth = _Auth()
    monkeypatch.setattr(d.cf_auth, "resolve", lambda _account: auth)

    def boom(_auth: object) -> None:
        raise RuntimeError("token never propagated")

    monkeypatch.setattr(d.cf_auth, "await_propagation", boom)
    monkeypatch.setattr(d.cf_auth, "self_destruct", destroyed.append)
    with pytest.raises(RuntimeError, match="never propagated"):
        d._cloudflare_env({})
    assert destroyed == [auth]


def test_the_scrubbed_global_key_is_not_restored_from_the_caller_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    auth = _Auth()
    auth.created = False
    monkeypatch.setattr(d.cf_auth, "resolve", lambda _account: auth)
    monkeypatch.setattr(
        d.cf_auth, "wrangler_env", lambda *_a, **_k: {"CLOUDFLARE_API_TOKEN": "minted"}
    )
    base = {"CF_GLOBAL_API_KEY": "g", "CF_API_KEY": "k", "CF_EMAIL": "e", "OPS_HEALTH_X": "x"}
    env, _cleanup = d._cloudflare_env(base)
    assert env == {"CLOUDFLARE_API_TOKEN": "minted", "OPS_HEALTH_X": "x"}
