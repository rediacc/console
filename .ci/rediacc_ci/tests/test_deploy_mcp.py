"""deploy_mcp: configs rendered from regions.json, the region boundary, secrets only on stdin, the version cross-check, the record and the rollback. Every wrangler call goes to a recording fake; nothing reaches Cloudflare."""

from __future__ import annotations

import io
import json
import pathlib
import shutil
import tomllib

import pytest

from rediacc_ci import paths
from rediacc_ci.deploy import deploy_mcp as dm

REPO = pathlib.Path(paths.repo_root())
VERSION = "0b6c8f2e-1111-4222-8333-944445555666"
PREVIOUS = "7d1e2f3a-aaaa-4bbb-8ccc-ddddeeeeffff"
ENV = {"CLOUDFLARE_API_TOKEN": "cf-token", "PATH": ""}


@pytest.fixture
def repo(tmp_path: pathlib.Path) -> pathlib.Path:
    """A copy of the files the module reads, so the tests can plant a bad config."""
    (tmp_path / "workers" / "mcp").mkdir(parents=True)
    shutil.copy(REPO / "regions.json", tmp_path / "regions.json")
    for path in (REPO / "workers/mcp").glob("wrangler*.toml"):
        shutil.copy(path, tmp_path / "workers/mcp" / path.name)
    return tmp_path


def deployments_json(version: str, created: str = "2026-11-26T00:00:00Z") -> str:
    return json.dumps(
        [{"created_on": created, "versions": [{"version_id": version, "percentage": 100}]}]
    )


class FakeWrangler:
    """Records (argv, stdin) and answers each wrangler verb from a table."""

    def __init__(
        self,
        *,
        live: list[str | None],
        secrets: list[str] | None = None,
        deploy_rc: int = 0,
        echo_stdin: bool = False,
    ) -> None:
        self.calls: list[tuple[list[str], str | None]] = []
        # Successive deployments-list answers; the last repeats. None is a Worker that does not exist.
        self.live = list(live)
        self.secrets = secrets or []
        self.deploy_rc = deploy_rc
        self.echo_stdin = echo_stdin

    def verbs(self) -> list[str]:
        return [" ".join(a[3:5]) for a, _ in self.calls]

    def __call__(
        self, argv: list[str], _cwd: pathlib.Path, stdin: str | None, _env: dict[str, str]
    ) -> dm.Result:
        self.calls.append((argv, stdin))
        verb = argv[3]
        if verb == "deployments":
            current = self.live.pop(0) if len(self.live) > 1 else self.live[0]
            if current is None:
                return dm.Result(1, "", "[code: 10007] This Worker does not exist on your account")
            return dm.Result(0, deployments_json(current), "")
        if verb == "deploy":
            if self.deploy_rc:
                return dm.Result(self.deploy_rc, "", "boom")
            if "--dry-run" in argv:
                return dm.Result(0, "--dry-run: exiting now.", "")
            return dm.Result(0, "Current Version ID: %s\n" % VERSION, "")
        if verb == "secret" and argv[4] == "list":
            return dm.Result(0, json.dumps([{"name": n} for n in self.secrets]), "")
        if verb == "secret" and argv[4] == "bulk":
            return dm.Result(0, stdin if self.echo_stdin else "Success!", "")
        if verb == "rollback":
            return dm.Result(0, "rolled", "")
        return dm.Result(99, "", "unexpected %s" % verb)


def answers(
    *, oauth: int = 200, issuer: str | None = "https://mcp.eu.rediacc.cloud", grant: int = 401
) -> dm.Fetcher:
    def fetch(url: str, _method: str) -> tuple[int, str]:
        if url.endswith(dm.SMOKE_PATH_OAUTH):
            return oauth, json.dumps({"issuer": issuer})
        return grant, ""

    return fetch


def drive(repo: pathlib.Path, fake: FakeWrangler, **kwargs):
    out = io.StringIO()
    kwargs.setdefault("fetch", answers())
    result = dm.run_deploy(
        repo,
        kwargs.pop("target", "stable"),
        kwargs.pop("region", "eu"),
        env=kwargs.pop("env", ENV),
        run=fake,
        sleep=lambda _s: None,
        out=out,
        **kwargs,
    )
    return result, out.getvalue()


def test_committed_configs_hold() -> None:
    """The six checked-in files are exactly what the template and regions.json render, and each passes the refusals."""
    assert dm.check(REPO) == []


def test_every_region_and_bench_has_a_config() -> None:
    keys = dm.targets(dm.load_regions(REPO))
    assert sorted(keys) == ["asia", "bench-asia", "bench-eu", "bench-us", "eu", "us"]
    assert keys["eu"].dataset == "mcp_eu"
    assert keys["bench-eu"].dataset == "mcp_bench_eu"


def test_oauth_and_metrics_bindings_are_rendered() -> None:
    doc = tomllib.loads((REPO / "workers/mcp/wrangler.eu.toml").read_text(encoding="utf-8"))
    assert [k["binding"] for k in doc["kv_namespaces"]] == ["OAUTH_KV"]
    assert "id" not in doc["kv_namespaces"][0]
    assert doc["analytics_engine_datasets"] == [{"binding": "MCP_METRICS", "dataset": "mcp_eu"}]
    assert {s["binding"]: (s["service"], s["entrypoint"]) for s in doc["services"]} == {
        "GRANTS": ("account-eu", "ExecutorIssuer"),
        "EXECUTOR": ("proxy-eu", "McpExecutor"),
    }


def test_cross_region_binding_is_refused_control() -> None:
    """The control of the region boundary: an eu config whose GRANTS binding names the us account Worker is refused."""
    regions = dm.load_regions(REPO)
    target = dm.targets(regions)["eu"]
    text = (REPO / "workers/mcp/wrangler.eu.toml").read_text(encoding="utf-8")
    all_regions = frozenset(str(r["id"]) for r in regions)
    assert dm.config_refusals(text, target, all_regions) == []
    bad = text.replace('service = "account-eu"', 'service = "account-us"')
    reasons = dm.config_refusals(bad, target, all_regions)
    assert any("services" in r for r in reasons)
    assert any("names us" in r for r in reasons)
    dataset = text.replace('dataset = "mcp_eu"', 'dataset = "mcp_us"')
    assert any(
        "analytics_engine_datasets" in r for r in dm.config_refusals(dataset, target, all_regions)
    )
    bench = text.replace('REGION = "eu"', 'REGION = "eu"\nNOTE = "bench"')
    assert any("names bench" in r for r in dm.config_refusals(bench, target, all_regions))


def test_a_planted_kv_id_or_secret_is_refused() -> None:
    regions = dm.load_regions(REPO)
    target = dm.targets(regions)["us"]
    all_regions = frozenset(str(r["id"]) for r in regions)
    text = (REPO / "workers/mcp/wrangler.us.toml").read_text(encoding="utf-8")
    with_id = text.replace('binding = "OAUTH_KV"', 'binding = "OAUTH_KV"\nid = "abc"')
    assert any(
        "kv_namespaces must carry no id" in r
        for r in dm.config_refusals(with_id, target, all_regions)
    )
    with_secret = text + '\nAUTH_REQUEST_KEY = "x"\n'
    assert any("Worker secret" in r for r in dm.config_refusals(with_secret, target, all_regions))


def test_check_refuses_a_hand_edit(repo: pathlib.Path) -> None:
    path = repo / "workers/mcp/wrangler.asia.toml"
    path.write_text(path.read_text(encoding="utf-8") + "\n# edited\n", encoding="utf-8")
    assert any("stale" in r and "wrangler.asia.toml" in r for r in dm.check(repo))


def test_write_regenerates_a_stale_file(repo: pathlib.Path) -> None:
    path = repo / "workers/mcp/wrangler.us.toml"
    path.write_text("name = 'x'\n", encoding="utf-8")
    assert dm.write(repo) == ["wrangler.us.toml"]
    assert dm.check(repo) == []


def test_dry_run_reads_no_secret_and_needs_no_token(repo: pathlib.Path) -> None:
    fake = FakeWrangler(live=[PREVIOUS])
    result, text = drive(repo, fake, target="bench", env={"PATH": ""}, dry_run=True)
    assert result["dry_run"] is True
    assert fake.verbs() == ["deploy --config"]
    assert "--dry-run" in fake.calls[0][0]
    assert all(stdin is None for _, stdin in fake.calls)
    assert "Dry run passed: mcp-bench" in text


def test_deploy_pushes_missing_secrets_on_stdin_only(repo: pathlib.Path, tmp_path) -> None:
    fake = FakeWrangler(live=[PREVIOUS, VERSION], secrets=[], echo_stdin=True)
    record = tmp_path / "mcp.json"
    result, text = drive(repo, fake, record=record)
    assert result["version_id"] == VERSION
    assert result["previous_version_id"] == PREVIOUS
    assert result["secret_names"] == ["AUTH_REQUEST_KEY", "CONFIRM_KEY"]
    assert result["smoke_rc"] == 0
    bulk = [(argv, stdin) for argv, stdin in fake.calls if argv[3:5] == ["secret", "bulk"]]
    assert len(bulk) == 1
    document = json.loads(bulk[0][1])
    assert sorted(document) == ["AUTH_REQUEST_KEY", "CONFIRM_KEY"]
    values = list(document.values())
    assert all(len(v) >= 40 for v in values)
    # A leaky wrangler that echoes stdin never puts a value in the output, the record or an argv.
    stored = record.read_text(encoding="utf-8")
    for value in values:
        assert value not in text
        assert value not in stored
        assert all(value not in " ".join(argv) for argv, _ in fake.calls)
    assert "Rollback: npx --no-install wrangler rollback %s" % PREVIOUS in text
    assert json.loads(stored)["rollback"].startswith(
        "npx --no-install wrangler rollback " + PREVIOUS
    )


def test_present_secrets_are_never_overwritten(repo: pathlib.Path) -> None:
    fake = FakeWrangler(live=[PREVIOUS, VERSION], secrets=list(dm.SECRET_NAMES))
    result, _ = drive(repo, fake)
    assert result["secret_names"] == sorted(dm.SECRET_NAMES)
    assert not any(argv[3:5] == ["secret", "bulk"] for argv, _ in fake.calls)


def test_one_missing_secret_pushes_only_that_one(repo: pathlib.Path) -> None:
    fake = FakeWrangler(live=[PREVIOUS, VERSION], secrets=["AUTH_REQUEST_KEY"])
    drive(repo, fake)
    bulk = [stdin for argv, stdin in fake.calls if argv[3:5] == ["secret", "bulk"]]
    assert [sorted(json.loads(s)) for s in bulk] == [["CONFIRM_KEY"]]


def test_first_deploy_has_no_rollback(repo: pathlib.Path) -> None:
    fake = FakeWrangler(live=[None, VERSION], secrets=list(dm.SECRET_NAMES))
    result, text = drive(repo, fake)
    assert result["rollback"] is None
    assert result["previous_known"] is True
    assert "Rollback: none (first deploy)" in text


def test_a_rollout_that_is_not_the_printed_version_fails(repo: pathlib.Path) -> None:
    fake = FakeWrangler(live=[PREVIOUS, PREVIOUS])
    with pytest.raises(dm.RefusedError, match="deployments list names"):
        drive(repo, fake)
    assert not any(argv[3] == "secret" for argv, _ in fake.calls)


def test_a_failed_deploy_stops_before_secrets(repo: pathlib.Path) -> None:
    fake = FakeWrangler(live=[PREVIOUS], deploy_rc=1)
    with pytest.raises(dm.RefusedError, match="wrangler deploy failed"):
        drive(repo, fake)
    assert not any(argv[3] == "secret" for argv, _ in fake.calls)


def test_a_failing_smoke_fails_the_run_but_keeps_the_record(repo: pathlib.Path, tmp_path) -> None:
    fake = FakeWrangler(live=[PREVIOUS, VERSION], secrets=list(dm.SECRET_NAMES))
    record = tmp_path / "mcp.json"
    with pytest.raises(dm.RefusedError, match="smoke failed"):
        drive(repo, fake, record=record, fetch=answers(grant=200))
    saved = json.loads(record.read_text(encoding="utf-8"))
    assert saved["version_id"] == VERSION
    assert saved["smoke_rc"] == 1
    assert saved["rollback"]


def test_smoke_names_each_failure() -> None:
    target = dm.targets(dm.load_regions(REPO))["eu"]
    assert dm.smoke_once(target, answers()) is None
    assert "answered 503" in (dm.smoke_once(target, answers(oauth=503)) or "")
    assert "issuer" in (dm.smoke_once(target, answers(issuer="https://mcp.us.rediacc.cloud")) or "")
    assert "not 401" in (dm.smoke_once(target, answers(grant=200)) or "")


def test_smoke_only_reads_the_live_version(repo: pathlib.Path) -> None:
    fake = FakeWrangler(live=[VERSION])
    result, _ = drive(repo, fake, smoke_only=True)
    assert result["version_id"] == VERSION
    assert result["smoke_rc"] == 0
    assert fake.verbs() == ["deployments list"]


def test_rollback_checks_the_listing_and_records(repo: pathlib.Path, tmp_path) -> None:
    fake = FakeWrangler(live=[PREVIOUS])
    record = tmp_path / "mcp.json"
    result, _ = drive(repo, fake, rollback=PREVIOUS.upper(), record=record)
    assert result["rolled_back"] is True
    assert result["version_id"] == PREVIOUS
    argv = next(a for a, _ in fake.calls if a[3] == "rollback")
    assert argv[4] == PREVIOUS
    assert "--yes" in argv
    assert json.loads(record.read_text(encoding="utf-8"))["smoke_rc"] == 0


def test_rollback_that_does_not_land_records_the_listing(repo: pathlib.Path, tmp_path) -> None:
    fake = FakeWrangler(live=[VERSION])
    record = tmp_path / "mcp.json"
    with pytest.raises(dm.RefusedError):
        drive(repo, fake, rollback=PREVIOUS, record=record)
    saved = json.loads(record.read_text(encoding="utf-8"))
    assert saved["version_id"] == VERSION
    assert saved["requested_version_id"] == PREVIOUS
    assert saved["smoke_rc"] is None


def test_refusals_before_any_credential(repo: pathlib.Path) -> None:
    fake = FakeWrangler(live=[PREVIOUS])
    with pytest.raises(dm.RefusedError, match="full version UUID"):
        drive(repo, fake, rollback="abc")
    with pytest.raises(dm.RefusedError, match="exclusive"):
        drive(repo, fake, dry_run=True, smoke_only=True)
    with pytest.raises(dm.RefusedError, match="CLOUDFLARE_API_TOKEN"):
        drive(repo, fake, env={"PATH": ""})
    with pytest.raises(dm.RefusedError, match="names no config"):
        drive(repo, fake, region="mars")
    assert fake.calls == []


def test_a_stale_config_never_reaches_wrangler(repo: pathlib.Path) -> None:
    path = repo / "workers/mcp/wrangler.eu.toml"
    path.write_text(path.read_text(encoding="utf-8") + "\n# edited\n", encoding="utf-8")
    fake = FakeWrangler(live=[PREVIOUS])
    with pytest.raises(dm.RefusedError, match="stale"):
        drive(repo, fake)
    assert fake.calls == []


def test_reexec_runs_under_the_target_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CLOUDFLARE_API_TOKEN", raising=False)
    monkeypatch.delenv(dm.PROFILES_ENV, raising=False)
    argv = dm.reexec_argv("bench", ["--target", "bench"])
    assert argv is not None
    assert argv[argv.index("--profile") + 1] == dm.BENCH_PROFILE
    assert argv[-2:] == ["--target", "bench"]
    stable = dm.reexec_argv("stable", [])
    assert stable is not None
    assert stable[stable.index("--profile") + 1] == dm.STABLE_PROFILE
    monkeypatch.setenv(dm.PROFILES_ENV, dm.BENCH_PROFILE)
    assert dm.reexec_argv("bench", []) is None
    monkeypatch.delenv(dm.PROFILES_ENV)
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "x")
    assert dm.reexec_argv("stable", []) is None
