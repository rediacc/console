"""deploy_signer: targets from regions.json and the account configs, a routeless rendered config, the key only on stdin, and the secret list verified. Every wrangler call goes to a recording fake; nothing reaches Cloudflare or bws."""

from __future__ import annotations

import io
import json
import pathlib
import shutil

import pytest

from rediacc_ci import paths
from rediacc_ci.deploy import deploy_signer as ds

REPO = pathlib.Path(paths.repo_root())
PRIVATE = "MC4CAQAwBQYDK2VwBCIEIPRIVATEKEYVALUEFORTHETESTONLY0000000000"
PUBLIC = "MCowBQYDK2VwAyEAPUBLICKEYVALUEFORTHETESTONLY000000000000000000"
VERSION = "0b6c8f2e-1111-4222-8333-944445555666"
PREVIOUS = "7d1e2f3a-aaaa-4bbb-8ccc-ddddeeeeffff"
CONTROL_ID = "11111111-2222-4333-8444-555555555555"
ENV = {
    "CLOUDFLARE_API_TOKEN": "cf-token",
    ds.PRIVATE_KEY: PRIVATE,
    ds.PUBLIC_KEY: PUBLIC,
    "PATH": "",
}


@pytest.fixture
def repo(tmp_path: pathlib.Path) -> pathlib.Path:
    """A copy of the files the module reads, so the rendered config lands in tmp, plus a fake local wrangler."""
    (tmp_path / "workers" / "signer").mkdir(parents=True)
    shutil.copy(REPO / "regions.json", tmp_path / "regions.json")
    shutil.copy(
        REPO / "workers/signer/wrangler.template.toml",
        tmp_path / "workers/signer/wrangler.template.toml",
    )
    shutil.copytree(
        REPO / "workers/account",
        tmp_path / "workers/account",
        ignore=shutil.ignore_patterns("node_modules", "src", "*dist*"),
    )
    bin_dir = tmp_path / "workers/signer/node_modules/.bin"
    bin_dir.mkdir(parents=True)
    (bin_dir / "wrangler").write_text("#!/bin/sh\nexit 99\n")
    return tmp_path


class FakeWrangler:
    """Records (argv, cwd, stdin) and answers each wrangler verb from a table. `echo_stdin` makes `secret bulk` print what it read, as a leaky wrangler might."""

    def __init__(
        self,
        *,
        control: bool = True,
        secrets: list[str] | None = None,
        echo_stdin: bool = False,
        deploy_rc: int = 0,
    ) -> None:
        self.calls: list[tuple[list[str], pathlib.Path, str | None]] = []
        self.control = control
        self.secrets = list(ds.SECRET_NAMES) if secrets is None else secrets
        self.echo_stdin = echo_stdin
        self.deploy_rc = deploy_rc

    def __call__(self, argv: list[str], cwd: pathlib.Path, stdin: str | None) -> ds.Result:
        self.calls.append((argv, cwd, stdin))
        verb = argv[3:5]
        if verb == ["d1", "list"]:
            rows = [{"name": "account-bench", "uuid": "x"}]
            if self.control:
                rows += [
                    {"name": "control-bench-eu", "uuid": CONTROL_ID},
                    {"name": "control-eu", "uuid": CONTROL_ID},
                ]
            return ds.Result(0, json.dumps(rows), "")
        if verb == ["deployments", "list"]:
            return ds.Result(
                0,
                json.dumps(
                    [
                        {
                            "created_on": "2026-11-01T00:00:00Z",
                            "versions": [{"version_id": PREVIOUS, "percentage": 100}],
                        }
                    ]
                ),
                "",
            )
        if argv[3] == "deploy":
            if self.deploy_rc:
                return ds.Result(self.deploy_rc, "", "boom")
            return ds.Result(0, "Uploaded signer\nCurrent Version ID: %s\n" % VERSION, "")
        if verb == ["secret", "bulk"]:
            return ds.Result(
                0, "read: %s\n" % stdin if self.echo_stdin else "Finished processing secrets\n", ""
            )
        if verb == ["secret", "list"]:
            return ds.Result(
                0, json.dumps([{"name": n, "type": "secret_text"} for n in self.secrets]), ""
            )
        raise AssertionError("unexpected wrangler call %s" % argv)


def run(repo: pathlib.Path, fake: FakeWrangler, target: str = "bench-eu", **kw):
    out = io.StringIO()
    result = ds.deploy(repo, target, env=kw.pop("env", ENV), run=fake, out=out, **kw)
    return result, out.getvalue()


def rendered(repo: pathlib.Path, target: str) -> str:
    return (repo / ("workers/signer/.generated/wrangler.%s.toml" % target)).read_text()


# ---- targets ----------------------------------------------------------------


def test_targets_are_one_per_region_plus_two_bench():
    t = ds.targets(ds.load_region_ids(REPO))
    assert sorted(t) == ["asia", "bench-eu", "bench-us", "eu", "us"]
    assert t["eu"].worker == "signer-eu"
    assert t["eu"].control_db == "control-eu"
    assert t["bench-us"].worker == "signer-bench-us"
    assert t["bench-us"].region == "us"
    assert t["bench-us"].control_db == "control-bench-us"
    assert t["bench-us"].account_config == "wrangler.bench.toml"


@pytest.mark.parametrize("target", ["eu", "us", "asia", "bench-eu", "bench-us"])
def test_every_target_renders_a_config_with_no_refusal(target):
    spec = ds.targets(ds.load_region_ids(REPO))[target]
    account = (REPO / "workers/account" / spec.account_config).read_text()
    db, db_id, hosts = ds.shared_binding(account, spec.account_config)
    assert db_id
    assert hosts
    text = ds.render(
        (REPO / "workers/signer/wrangler.template.toml").read_text(),
        {
            "WORKER": spec.worker,
            "REGION": spec.region,
            "SHARED_HOSTS": ",".join(hosts),
            "CONTROL_DB": spec.control_db,
            "CONTROL_DB_ID": CONTROL_ID,
            "SHARED_DB": db,
            "SHARED_DB_ID": db_id,
        },
    )
    assert ds.config_refusals(text, spec) == []
    assert db == ("account-bench" if target.startswith("bench") else "account-%s" % target)


def test_shared_hosts_come_from_the_account_config():
    _, _, hosts = ds.shared_binding((REPO / "workers/account/wrangler.eu.toml").read_text(), "eu")
    assert hosts == ["eu.rediacc.cloud"]


def test_unknown_target_is_refused_before_any_call(repo):
    fake = FakeWrangler()
    with pytest.raises(ds.RefusedError, match="not a signer target"):
        run(repo, fake, target="mars")
    assert fake.calls == []


# ---- config refusals ----------------------------------------------------------


def _good_text(spec: ds.Target) -> str:
    return ds.render(
        (REPO / "workers/signer/wrangler.template.toml").read_text(),
        {
            "WORKER": spec.worker,
            "REGION": spec.region,
            "SHARED_HOSTS": "eu.rediacc.cloud",
            "CONTROL_DB": spec.control_db,
            "CONTROL_DB_ID": CONTROL_ID,
            "SHARED_DB": "account-eu",
            "SHARED_DB_ID": "id",
        },
    )


@pytest.mark.parametrize(
    ("mutate", "reason"),
    [
        (
            lambda t: t.replace(
                'main = "../src/index.ts"',
                'main = "../src/index.ts"\nroutes = [{ pattern = "signer.rediacc.cloud", custom_domain = true }]',
            ),
            "a signer has no route",
        ),
        (
            lambda t: t.replace(
                'main = "../src/index.ts"', 'main = "../src/index.ts"\nroute = "x.rediacc.cloud/*"'
            ),
            "a signer has no route",
        ),
        (
            lambda t: t.replace("workers_dev = false", "workers_dev = true"),
            "workers_dev is not false",
        ),
        (lambda t: t.replace("preview_urls = false", ""), "preview_urls is not false"),
        (lambda t: t.replace('name = "signer-eu"', 'name = "signer-us"'), "name is"),
        (lambda t: t.replace('REGION = "eu"', 'REGION = "us"'), "vars.REGION"),
        (
            lambda t: t.replace('database_name = "control-eu"', 'database_name = "control-us"'),
            "CONTROL binds",
        ),
        (
            lambda t: t + '\n[vars.extra]\n# ACCOUNT_ED25519_PRIVATE_KEY = "x"\n',
            "the key is a secret only",
        ),
        (lambda t: t + "\n[env.staging]\nname = 'x'\n", "[env.*]"),
        (lambda t: t + '\nexample = "@LEFT_OVER@"\n', "unrendered token"),
        (
            lambda t: (
                t
                + '\n[[d1_databases]]\nbinding = "DB"\ndatabase_name = "account-eu"\ndatabase_id = "z"\n'
            ),
            "not CONTROL and SHARED",
        ),
    ],
)
def test_each_config_refusal_fires_and_the_control_passes(mutate, reason):
    spec = ds.targets(["eu"])["eu"]
    good = _good_text(spec)
    assert ds.config_refusals(good, spec) == []
    reasons = ds.config_refusals(mutate(good), spec)
    assert any(reason in r for r in reasons), reasons


def test_the_template_itself_has_no_route_and_no_key_name():
    text = (REPO / "workers/signer/wrangler.template.toml").read_text()
    assert ds.PRIVATE_KEY not in text
    assert "routes" not in text.replace("NO ROUTE", "").split("\nname =", 1)[1]


# ---- the deploy ---------------------------------------------------------------


def test_deploy_order_record_and_rollback(repo, tmp_path):
    fake = FakeWrangler()
    record = tmp_path / "record.json"
    result, out = run(repo, fake, record=record)
    verbs = [c[0][3:5] for c in fake.calls]
    assert verbs == [
        ["d1", "list"],
        ["deployments", "list"],
        ["deploy", "--config"],
        ["secret", "bulk"],
        ["secret", "list"],
    ]
    assert all(c[1] == repo / "workers/signer" for c in fake.calls)
    assert all(c[0][:3] == ["npx", "--no-install", "wrangler"] for c in fake.calls)
    assert result["version_id"] == VERSION
    assert result["previous_version_id"] == PREVIOUS
    assert (
        result["rollback"]
        == "npx --no-install wrangler rollback %s --config workers/signer/.generated/wrangler.bench-eu.toml --yes"
        % PREVIOUS
    )
    assert json.loads(record.read_text()) == result
    assert "control-bench-eu" in rendered(repo, "bench-eu")
    assert CONTROL_ID in rendered(repo, "bench-eu")
    assert 'SHARED_HOSTS = "bench.rediacc.cloud"' in rendered(repo, "bench-eu")
    assert "Deployed signer-bench-eu version %s" % VERSION in out


def test_the_key_reaches_wrangler_only_on_stdin(repo, tmp_path):
    fake = FakeWrangler(echo_stdin=True)
    record = tmp_path / "record.json"
    result, out = run(repo, fake, record=record)
    bulk = [c for c in fake.calls if c[0][3:5] == ["secret", "bulk"]]
    assert len(bulk) == 1
    document = bulk[0][2]
    assert document is not None
    assert json.loads(document) == {ds.PRIVATE_KEY: PRIVATE, ds.PUBLIC_KEY: PUBLIC}
    for argv, _, stdin in fake.calls:
        assert not any(PRIVATE in a or PUBLIC in a for a in argv)
        if argv[3:5] != ["secret", "bulk"]:
            assert stdin is None
    # A wrangler that echoes its stdin still prints no value.
    assert PRIVATE not in out
    assert PUBLIC not in out
    assert ds.REDACTED in out
    assert PRIVATE not in record.read_text()
    assert PRIVATE not in json.dumps(result)
    assert PRIVATE not in rendered(repo, "bench-eu")


def test_no_failure_message_carries_the_key(repo):
    for fake in (
        FakeWrangler(deploy_rc=1),
        FakeWrangler(secrets=[ds.PUBLIC_KEY]),
        FakeWrangler(control=False),
    ):
        with pytest.raises(ds.RefusedError) as exc:
            run(repo, fake)
        text = " ".join(exc.value.lines) + str(exc.value)
        assert PRIVATE not in text
        assert PUBLIC not in text


def test_missing_control_database_is_named_and_nothing_deploys(repo):
    fake = FakeWrangler(control=False)
    with pytest.raises(ds.RefusedError, match="control-bench-eu does not exist"):
        run(repo, fake)
    assert [c[0][3:5] for c in fake.calls] == [["d1", "list"]]


def test_missing_key_is_refused_by_name_before_any_call(repo):
    fake = FakeWrangler()
    env = {k: v for k, v in ENV.items() if k != ds.PRIVATE_KEY}
    with pytest.raises(ds.RefusedError) as exc:
        run(repo, fake, env=env)
    assert ds.PRIVATE_KEY in exc.value.lines[0]
    assert PUBLIC not in exc.value.lines[0]
    assert ds.PROFILE in exc.value.lines[0]
    assert fake.calls == []


def test_missing_cloudflare_token_is_refused(repo):
    fake = FakeWrangler()
    env = {k: v for k, v in ENV.items() if k != "CLOUDFLARE_API_TOKEN"}
    with pytest.raises(ds.RefusedError, match="CLOUDFLARE_API_TOKEN"):
        run(repo, fake, env=env)
    assert fake.calls == []


@pytest.mark.parametrize(
    "secrets", [[ds.PUBLIC_KEY], [*ds.SECRET_NAMES, "FREE_LICENSE_HMAC_KEY"], []]
)
def test_secret_list_must_name_exactly_the_two_keys(repo, secrets):
    with pytest.raises(ds.RefusedError, match="not exactly"):
        run(repo, FakeWrangler(secrets=secrets))


def test_failed_deploy_pushes_no_key(repo):
    fake = FakeWrangler(deploy_rc=2)
    with pytest.raises(ds.RefusedError, match="wrangler deploy failed"):
        run(repo, fake)
    assert not any(c[0][3:5] == ["secret", "bulk"] for c in fake.calls)


def test_first_deploy_has_no_rollback(repo):
    class First(FakeWrangler):
        def __call__(self, argv, cwd, stdin):
            if argv[3:5] == ["deployments", "list"]:
                self.calls.append((argv, cwd, stdin))
                return ds.Result(1, "", "This Worker does not exist on your account. [code: 10007]")
            return super().__call__(argv, cwd, stdin)

    result, out = run(repo, First())
    assert result["previous_version_id"] is None
    assert result["rollback"] is None
    assert "none (first deploy)" in out


@pytest.mark.parametrize(
    "answer",
    [
        ds.Result(1, "", "network down"),
        ds.Result(0, "not json", ""),
        ds.Result(0, '{"a": 1}', ""),
        ds.Result(0, "[1]", ""),
        ds.Result(1, "", "wrangler.toml not found in the working directory"),
        ds.Result(1, "", "the account does not exist"),
    ],
)
def test_an_unreadable_deployments_list_is_not_claimed_as_a_first_deploy(repo, answer):
    class Unreadable(FakeWrangler):
        def __call__(self, argv, cwd, stdin):
            if argv[3:5] == ["deployments", "list"]:
                self.calls.append((argv, cwd, stdin))
                return answer
            return super().__call__(argv, cwd, stdin)

    result, out = run(repo, Unreadable())
    assert result["previous_known"] is False
    assert result["rollback"] is None
    assert "first deploy" not in out
    assert "Rollback: unknown" in out


def test_an_empty_deployments_list_is_a_first_deploy(repo):
    class Empty(FakeWrangler):
        def __call__(self, argv, cwd, stdin):
            if argv[3:5] == ["deployments", "list"]:
                self.calls.append((argv, cwd, stdin))
                return ds.Result(0, "[]", "")
            return super().__call__(argv, cwd, stdin)

    result, out = run(repo, Empty())
    assert result["previous_known"] is True
    assert "none (first deploy)" in out


def test_the_record_and_rollback_exist_before_the_key_is_pushed(repo, tmp_path):
    class BulkFails(FakeWrangler):
        def __call__(self, argv, cwd, stdin):
            if argv[3:5] == ["secret", "bulk"]:
                self.calls.append((argv, cwd, stdin))
                return ds.Result(1, "", "boom")
            return super().__call__(argv, cwd, stdin)

    record = tmp_path / "record.json"
    out = io.StringIO()
    with pytest.raises(ds.RefusedError, match="secret bulk failed"):
        ds.deploy(repo, "bench-eu", env=ENV, run=BulkFails(), out=out, record=record)
    written = json.loads(record.read_text())
    assert written["version_id"] == VERSION
    assert written["previous_version_id"] == PREVIOUS
    assert written["rollback"]
    assert "Rollback: npx --no-install wrangler rollback %s" % PREVIOUS in out.getvalue()


def test_a_duplicate_d1_binding_is_refused():
    spec = ds.targets(["eu"])["eu"]
    good = _good_text(spec)
    dup = (
        good
        + '\n[[d1_databases]]\nbinding = "SHARED"\ndatabase_name = "account-us"\ndatabase_id = "z"\n'
    )
    reasons = ds.config_refusals(dup, spec)
    assert any("SHARED is declared 2 times" in r for r in reasons), reasons


def test_dry_run_needs_no_credential_and_reads_no_control(repo):
    fake = FakeWrangler()
    result, _ = run(repo, fake, env={}, dry_run=True)
    assert result["dry_run"] is True
    assert len(fake.calls) == 1
    assert fake.calls[0][0][3:6] == [
        "deploy",
        "--config",
        str(repo / "workers/signer/.generated/wrangler.bench-eu.toml"),
    ]
    assert "--dry-run" in fake.calls[0][0]
    assert ds.DRY_RUN_DB_ID in rendered(repo, "bench-eu")


def test_main_prints_refusal_and_exits_1(capsys):
    assert ds.main(["--target", "mars"], run=FakeWrangler()) == 1
    assert "not a signer target" in capsys.readouterr().err
