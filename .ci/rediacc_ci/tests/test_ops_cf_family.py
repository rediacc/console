"""Differentials and Rule T delta tests for the Cloudflare operator ports: `cf_auth`, `backup_d1`, `reset_bench`, `deploy_bench`.

EACH PORT IS DRIVEN AGAINST ITS BASH TWIN with the same fake `curl`/`npx` on a sealed PATH (`ops_cf_harness.World`), comparing the call log (method, URL, parsed body, argv, cwd), stdout, stderr (ANSI stripped: the bash colours unconditionally, the port only on a tty) and the exit code. A test named `test_delta_*` pins one deliberate Rule T difference: it asserts the bash behaviour first (the control, so the delta cannot be a vacuous pass) and then the port's.

The real-target runs that are the acceptance for these scripts are the lead's recorded runs; this file is the CI-runnable regression net.
"""

from __future__ import annotations

import json
import subprocess
import typing

import pytest

from rediacc_ci.ops import cf_auth, deploy_bench, reset_bench
from rediacc_ci.tests import ops_cf_harness as h

if typing.TYPE_CHECKING:
    import pathlib

TOKEN_ENV = {"CF_MANAGEMENT_TOKEN": "supplied-token"}
GLOBAL_ENV = {"CF_GLOBAL_API_KEY": "gk", "CF_EMAIL": "ops@example.invalid"}


@pytest.fixture
def world(tmp_path: pathlib.Path) -> h.World:
    scratch = h.World(tmp_path)
    # deploy_bench reads the bench bucket from the BACKUP_BUCKET binding (PLAN-backup-presign-bucket-require-and-wrangler-vars B4), which the harness's minimal bench config does not declare.
    config = scratch.root / "workers/account/wrangler.bench.toml"
    config.write_text(
        config.read_text()
        + '\n[[r2_buckets]]\nbinding = "BACKUP_BUCKET"\nbucket_name = "rediacc-backups-bench"\n'
    )
    return scratch


def _curl_calls(world: h.World, mask: bool = True) -> list[dict]:
    return [c for c in h.normalise_calls(world.calls(), mask) if c["tool"] == "curl"]


def _quiet_selfdestruct(text: str) -> list[str]:
    """Stderr lines without the self-destruct report, which the bash sent to /dev/null (a deliberate delta)."""
    drop = ("Self-destruct", "Deleting CF management token", "CF management token deleted")
    return [ln for ln in h.strip(text).splitlines() if not any(x in ln for x in drop)]


# ---------------------------------------------------------------- cf_auth


def test_token_mint_sequence_matches_bash(world: h.World) -> None:
    env = world.env(**GLOBAL_ENV)
    rc_b, out_b, _ = world.twin_run("scripts/ops/backup-d1.sh", ["--dry-run"], env)
    bash_calls = _curl_calls(world, mask=False)
    world.reset_log()
    rc_p, out_p, _ = world.port("rediacc_ci.ops.backup_d1", ["--dry-run"], env)
    port_calls = _curl_calls(world, mask=False)
    assert rc_b == rc_p == 0
    assert out_b == out_p
    assert [c["method"] for c in bash_calls] == ["GET", "GET", "POST"]
    assert port_calls[:2] == bash_calls[:2]
    # The POST differs by exactly two added permission groups: Workers R2 Storage Write (the bash token could not list buckets) and Workers Observability Read (the post-deploy rotation check lists the otlp destinations).
    post = bash_calls[2]["body"]
    port_post = port_calls[2]["body"]
    extra = [
        g
        for g in port_post["policies"][0]["permission_groups"]
        if g not in post["policies"][0]["permission_groups"]
    ]
    assert extra == [
        {"id": "bf7481a1826f439697cb59a20b22293e"},
        {"id": "66c1ed49f4ed46098b75696a6d4ee3c9"},
    ]
    for g in extra:
        port_post["policies"][0]["permission_groups"].remove(g)
    assert port_calls[2] == {**bash_calls[2], "body": port_post}
    assert post["name"] == "auto-rotation-management"
    assert next(next(iter(p["resources"])) for p in post["policies"]).startswith(
        "com.cloudflare.api.account."
    )
    assert len(post["policies"]) == 3
    assert len(post["policies"][1]["resources"]) == 2


def test_no_zone_account_omits_the_zone_policy_like_bash(world: h.World) -> None:
    routes = [r for r in h.TOKEN_ROUTES if "/zones" not in r["match"]]
    routes.insert(0, {"method": "GET", "match": "/zones", "body": {"result": []}})
    world.set_routes(routes)
    env = world.env(**GLOBAL_ENV)
    world.twin_run("scripts/ops/backup-d1.sh", ["--dry-run"], env)
    bash_post = _curl_calls(world, mask=False)[2]["body"]
    world.reset_log()
    world.port("rediacc_ci.ops.backup_d1", ["--dry-run"], env)
    port_post = _curl_calls(world, mask=False)[2]["body"]
    assert len(bash_post["policies"]) == len(port_post["policies"]) == 2
    assert port_post["policies"][1] == bash_post["policies"][1]


def test_delta_a_failed_mint_says_why(world: h.World) -> None:
    world.set_routes(
        [
            {
                "method": "GET",
                "match": "/user",
                "body": {"success": False, "errors": [{"message": "Invalid API key"}]},
            }
        ]
    )
    env = world.env(**GLOBAL_ENV)
    rc_b, _, err_b = world.twin_run("scripts/ops/backup-d1.sh", ["--dry-run"], env)
    assert rc_b == 1
    assert "Failed to create" not in err_b
    assert "Invalid API key" not in err_b
    rc_p, _, err_p = world.port("rediacc_ci.ops.backup_d1", ["--dry-run"], env)
    assert rc_p == 1
    assert "Invalid API key" in err_p


def test_delta_an_empty_token_is_refused(world: h.World) -> None:
    env = world.env()
    rc_b, _, _err_b = world.twin_run("scripts/ops/backup-d1.sh", ["--dry-run"], env, stdin="2\n\n")
    assert rc_b == 0  # the control: bash accepted an empty "Bearer " token
    rc_p, _, err_p = world.port("rediacc_ci.ops.backup_d1", ["--dry-run"], env, stdin="2\n\n")
    assert rc_p == 1
    assert "credentials are required" in err_p


def test_delta_self_destruct_reports_a_failed_delete(world: h.World) -> None:
    routes = [r for r in h.TOKEN_ROUTES if r["method"] != "DELETE"]
    routes.insert(
        0,
        {
            "method": "DELETE",
            "match": "/user/tokens/TID",
            "body": {"success": False, "errors": [{"message": "forbidden"}]},
        },
    )
    world.set_routes(routes)
    env = world.env(**TOKEN_ENV)
    _, _, err_b = world.twin_run("scripts/ops/backup-d1.sh", ["edge", "--self-destruct"], env)
    assert "CF management token deleted (self-destruct)" in h.strip(
        err_b
    )  # the control: bash claimed success
    assert "NOT deleted" not in err_b
    _, _, err_p = world.port("rediacc_ci.ops.backup_d1", ["edge", "--self-destruct"], env)
    assert "CF management token was NOT deleted: forbidden" in h.strip(err_p)


# ---------------------------------------------------------------- cf_auth.await_propagation

ACCT = cf_auth.DEFAULT_ACCOUNT_ID
D1_PROBE = "/accounts/%s/d1/database" % ACCT
SCRIPTS_PROBE = "/accounts/%s/workers/scripts" % ACCT


class FakeCF:
    """Stands in for `cf_auth.curl_json`: verify accepts at once, D1 refuses its first `d1_refusals` probes (the measured propagation shape) and, optionally, the `flap_at`-th one."""

    def __init__(self, d1_refusals: int = 0, flap_at: int | None = None) -> None:
        self.d1_refusals, self.flap_at = d1_refusals, flap_at
        self.calls: list[tuple[str, str]] = []
        self.refused = 0

    def __call__(self, method: str, url: str, *_rest: object, **_kw: object) -> dict:
        path = url.rsplit("/client/v4", maxsplit=1)[-1].split("?", maxsplit=1)[0]
        self.calls.append((method, path))
        if path == D1_PROBE:
            n = sum(1 for _, p in self.calls if p == D1_PROBE)
            if n <= self.d1_refusals or n == self.flap_at:
                self.refused += 1
                return {
                    "success": False,
                    "errors": [{"code": 10000, "message": "Authentication error"}],
                }
        return {"success": True, "result": {}}

    def count(self, path: str) -> int:
        return sum(1 for _, p in self.calls if p == path)


class FakeClock:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t

    def sleep(self, s: float) -> None:
        self.t += s


def _minted() -> cf_auth.Auth:
    return cf_auth.Auth(
        TOKEN_ENV["CF_MANAGEMENT_TOKEN"],
        created=True,
        policies=cf_auth.token_policies(ACCT, "USER1", ["ZONE1"]),
    )


def test_ready_probes_follow_the_minted_policies() -> None:
    probes = cf_auth.ready_probes(cf_auth.token_policies(ACCT, "USER1", ["ZONE1"]))
    assert probes == [
        ("verify", "/user/tokens/verify"),
        ("D1", D1_PROBE + "?per_page=1"),
        ("Workers Scripts", SCRIPTS_PROBE),
    ]
    # A token granting none of the slow services is probed by verify alone.
    bare = [
        {
            "effect": "allow",
            "resources": {"com.cloudflare.api.account.%s" % ACCT: "*"},
            "permission_groups": [{"id": "bf7481a1826f439697cb59a20b22293e"}],
        }
    ]
    assert cf_auth.ready_probes(bare) == [cf_auth.VERIFY_PROBE]


def test_await_propagation_waits_out_refusals(monkeypatch: pytest.MonkeyPatch) -> None:
    fake, clock = FakeCF(d1_refusals=3), FakeClock()
    monkeypatch.setattr(cf_auth, "curl_json", fake)
    waited = cf_auth.await_propagation(_minted(), sleep=clock.sleep, clock=clock)
    assert fake.refused == 3  # the control: the fake really refused before it accepted
    assert fake.count(D1_PROBE) == 3 + cf_auth.READY_CONSECUTIVE
    assert fake.count(SCRIPTS_PROBE) == cf_auth.READY_CONSECUTIVE
    assert all(m == "GET" for m, _ in fake.calls), "readiness probes must be read-only"
    assert waited >= 3


def test_await_propagation_resets_the_streak_on_a_refusal_between_successes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # accepted, refused (another edge node), then accepted twice: one success is not readiness
    fake, clock = FakeCF(flap_at=2), FakeClock()
    monkeypatch.setattr(cf_auth, "curl_json", fake)
    cf_auth.await_propagation(_minted(), sleep=clock.sleep, clock=clock)
    assert fake.refused == 1
    assert fake.count(D1_PROBE) == 4


def test_await_propagation_gives_up_naming_the_service(monkeypatch: pytest.MonkeyPatch) -> None:
    fake, clock = FakeCF(d1_refusals=10**6), FakeClock()
    monkeypatch.setattr(cf_auth, "curl_json", fake)
    with pytest.raises(
        cf_auth.CfAuthError,
        match=r"not accepted by D1 \(GET %s\) within 5 s; last error codes \[10000\]" % D1_PROBE,
    ):
        cf_auth.await_propagation(_minted(), deadline_s=5, sleep=clock.sleep, clock=clock)
    assert clock.t <= 5 + cf_auth.READY_INTERVAL_S
    assert fake.count(SCRIPTS_PROBE) == 0  # never reached past the stuck service


def test_await_propagation_treats_a_non_json_answer_as_a_refusal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    answers = iter([cf_auth.CfAuthError("GET x did not return JSON (curl exit 7)")])
    clock = FakeClock()

    def flaky(*_args: object, **_kwargs: object) -> dict:
        nxt = next(answers, None)
        if nxt is not None:
            raise nxt
        return {"success": True}

    monkeypatch.setattr(cf_auth, "curl_json", flaky)
    cf_auth.await_propagation(_minted(), sleep=clock.sleep, clock=clock)
    assert clock.t > 0


def test_a_supplied_token_is_not_probed(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeCF()
    monkeypatch.setattr(cf_auth, "curl_json", fake)
    assert cf_auth.await_propagation(cf_auth.Auth(TOKEN_ENV["CF_MANAGEMENT_TOKEN"])) == 0.0
    assert fake.calls == []


# ---------------------------------------------------------------- backup_d1


def test_backup_d1_matches_bash(world: h.World) -> None:
    env = world.env(**TOKEN_ENV)
    rc_b, out_b, err_b = world.twin_run("scripts/ops/backup-d1.sh", ["edge"], env)
    bash_calls = world.calls()
    bash_files = sorted(p.name for p in (world.root / ".backups/edge").iterdir())
    world.reset_log()
    for p in (world.root / ".backups").rglob("*"):
        if p.is_file():
            p.unlink()
    rc_p, out_p, err_p = world.port("rediacc_ci.ops.backup_d1", ["edge"], env)
    port_calls = world.calls()
    port_files = sorted(p.name for p in (world.root / ".backups/edge").iterdir())
    assert rc_b == rc_p == 0
    assert h.mask_stamp(json.dumps(bash_calls)) == h.mask_stamp(json.dumps(port_calls))
    assert h.mask_stamp(str(bash_files)) == h.mask_stamp(str(port_files))
    assert out_b == out_p
    assert "r2.cloudflarestorage.com" not in out_p
    assert "valid for one hour" not in out_p
    assert "Exporting database edge-account-db-eu" in out_p

    def stripped(t):
        return h.mask_stamp(h.mask_root(h.strip(t), world))

    lines_b = [ln for ln in stripped(err_b).splitlines() if "Exported" not in ln]
    lines_p = [ln for ln in stripped(err_p).splitlines() if "Exported" not in ln]
    assert lines_b == lines_p
    assert "Exported 2 lines" in err_p
    assert next(c for c in port_calls if c["tool"] == "npx")["cf_env"] == [
        "CF_MANAGEMENT_TOKEN",
        "CLOUDFLARE_ACCOUNT_ID",
        "CLOUDFLARE_API_TOKEN",
    ]


def test_backup_d1_unknown_argument_matches_bash(world: h.World) -> None:
    env = world.env(**TOKEN_ENV)
    rc_b, _, err_b = world.twin_run("scripts/ops/backup-d1.sh", ["--bogus"], env)
    rc_p, _, err_p = world.port("rediacc_ci.ops.backup_d1", ["--bogus"], env)
    assert rc_b == rc_p == 1
    # ONE DECLARED DELTA: the usage line names the module the way it is run now. The bash script it named was deleted (363a35892), so the golden's line is mapped before the comparison, and the golden is asserted to carry it so the mapping cannot go vacuous.
    usage_bash = "Usage: backup-d1.sh "
    usage_port = "Usage: PYTHONPATH=.ci python3 -m rediacc_ci.ops.backup_d1 "
    assert usage_bash in h.strip(err_b), err_b
    assert h.strip(err_b).replace(usage_bash, usage_port) == h.strip(err_p)


def test_delta_a_minted_token_is_always_destroyed(world: h.World) -> None:
    env = world.env(**GLOBAL_ENV)
    world.twin_run("scripts/ops/backup-d1.sh", ["edge"], env)
    assert [c["method"] for c in _curl_calls(world)] == [
        "GET",
        "GET",
        "POST",
    ]  # bash leaves the token alive
    world.reset_log()
    world.port("rediacc_ci.ops.backup_d1", ["edge"], env)
    methods = [c["method"] for c in _curl_calls(world)]
    assert methods == ["GET", "GET", "POST", "GET", "DELETE"]


def test_delta_a_failed_export_is_named_and_still_cleans_up(world: h.World) -> None:
    env = world.env(FAKE_NPX_FAIL="wrangler d1 export", FAKE_NPX_RC="7", **GLOBAL_ENV)
    rc_b, _, err_b = world.twin_run("scripts/ops/backup-d1.sh", ["edge", "--self-destruct"], env)
    assert rc_b != 0
    assert "failed" not in h.strip(err_b)  # the control: silent exit
    assert "DELETE" not in [c["method"] for c in _curl_calls(world)]
    world.reset_log()
    rc_p, _, err_p = world.port("rediacc_ci.ops.backup_d1", ["edge", "--self-destruct"], env)
    assert rc_p == 1
    assert "wrangler d1 export of edge-account-db-eu failed (exit 7)" in err_p
    assert "DELETE" in [c["method"] for c in _curl_calls(world)]


def test_delta_all_filtered_output_is_not_a_failure(world: h.World) -> None:
    quiet = (
        "#!/usr/bin/env python3\nimport os, sys\n"
        "out = next(a for a in sys.argv if a.startswith('--output='))[9:]\n"
        "open(out, 'w').write('x\\n')\n"
        "print('https://a.r2.cloudflarestorage.com/x')\n"
    )
    h.World._write_exec(
        world.bin / "npx", quiet.replace("/usr/bin/env python3", __import__("sys").executable)
    )
    env = world.env(**TOKEN_ENV)
    rc_b, _, _ = world.twin_run("scripts/ops/backup-d1.sh", ["edge"], env)
    assert rc_b != 0  # the control: grep -v selected nothing, pipefail ended the run
    rc_p, _, _ = world.port("rediacc_ci.ops.backup_d1", ["edge"], env)
    assert rc_p == 0


# ---------------------------------------------------------------- reset_bench


def _reset_env(env: dict[str, str]) -> dict[str, str]:
    """The port's environment: already bound to its own `reset-bench` profile, so it does not re-execute under `bws_env`. The twin had no profile, so its environment, and every golden key, is unchanged."""
    return {**env, "REDIACC_BWS_PROFILES": reset_bench.PROFILE}


D1_TABLES = {
    "method": "POST",
    "match": "/d1/database/",
    "body": {
        "success": True,
        "result": [
            {
                "results": [
                    {"name": "users", "sql": "CREATE TABLE users(id)"},
                    {"name": 'we"ird', "sql": 'CREATE TABLE "we""ird"(u REFERENCES users(id))'},
                ]
            }
        ],
    },
}
R2_LIST = {
    "method": "GET",
    "match": "/r2/buckets/",
    "body": {"success": True, "result": [{"key": "a/b.json"}], "result_info": {"cursor": ""}},
}
S3_XML = (
    '<?xml version="1.0"?><ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">'
    "<IsTruncated>false</IsTruncated><Contents><Key>a/b c.json</Key></Contents><Contents><Key>d.json</Key></Contents>"
    "</ListBucketResult>"
)
S3_LIST = {"method": "GET", "match": "rediacc-configs-bench?list-type=2", "raw": S3_XML}
S3_DELETE = {"method": "DELETE", "match": "rediacc-configs-bench/", "raw": "", "status": 204}
R2_ENV = {
    "CLOUDFLARE_R2_ENDPOINT": "https://acct.r2.example.invalid",
    "CLOUDFLARE_R2_ACCESS_KEY_ID": "r2-id",
    "CLOUDFLARE_R2_SECRET_ACCESS_KEY": "r2-secret",
}


def _reset_routes(world: h.World, *extra: dict) -> None:
    world.set_routes([*extra, D1_TABLES, R2_LIST, S3_LIST, S3_DELETE, *h.TOKEN_ROUTES])


def test_reset_bench_d1_half_matches_bash(world: h.World) -> None:
    _reset_routes(world)
    env = world.env(**GLOBAL_ENV, **R2_ENV)
    rc_b, out_b, err_b = world.twin_run("scripts/ops/reset-bench.sh", ["--yes", "--d1-only"], env)
    bash_calls = world.calls()
    world.reset_log()
    world.add_routes(*h.PROBE_ROUTES)  # after the twin: the route table keys its golden
    rc_p, out_p, err_p = world.port(
        "rediacc_ci.ops.reset_bench", ["--yes", "--d1-only"], _reset_env(env)
    )
    # DECLARED DELTA: the port probes the minted token's readiness (the bash did not wait at all); compared without the probe block.
    port_calls, probes = h.split_probe_block(world.calls())
    assert not h.split_probe_block(bash_calls)[1]  # the control: the bash sent no probe
    assert probes, "the minted token was used without a readiness probe"
    assert rc_b == rc_p == 0, (err_b, err_p)
    # ONE DECLARED DELTA: the closing hint names the bench deploy the way it is run now. The bash script it named was retired (PLAN-retire-bash-oracles B3), so the golden's line is mapped before the comparison, and the golden is asserted to carry it so the mapping cannot go vacuous.
    redeploy_bash = "To redeploy fresh code: scripts/ops/deploy-bench.sh\n"
    redeploy_port = (
        "To redeploy fresh code: PYTHONPATH=.ci python3 -m rediacc_ci.ops.deploy_bench "
        "(it also seeds the ROOT_EMAIL user the reset removed)\n"
    )
    assert redeploy_bash in out_b, out_b
    assert out_b.replace(redeploy_bash, redeploy_port) == out_p

    def shape(calls: list[dict]) -> list:
        norm = [c for c in h.normalise_calls(calls) if c["tool"] != "sleep"]
        for call in norm:
            if (
                call["tool"] == "curl"
                and call["body"]
                and "DROP TABLE" in call["body"].get("sql", "")
            ):
                call["body"]["sql"] = "<DROP>"  # compared in the delta tests below
            if (
                call["tool"] == "curl"
                and call["body"]
                and call["body"].get("sql", "").startswith("SELECT name")
            ):
                call["body"]["sql"] = "<LIST>"
        return norm

    assert shape(bash_calls) == shape(port_calls)
    npx = [c for c in port_calls if c["tool"] == "npx"]
    assert npx[0]["argv"][:5] == ["--no-install", "wrangler", "d1", "migrations", "apply"]
    assert {"CLOUDFLARE_ACCOUNT_ID", "CLOUDFLARE_API_TOKEN"} <= set(npx[0]["cf_env"])
    assert not {"CF_GLOBAL_API_KEY", "CF_EMAIL", "CF_API_KEY"} & set(npx[0]["cf_env"])
    # The "Dropping N tables: ..." line lists them in drop order, which is the delta pinned below.
    assert [ln for ln in _quiet_selfdestruct(err_b) if "Dropping" not in ln] == [
        ln
        for ln in _quiet_selfdestruct(err_p)
        if "Dropping" not in ln and "accepted by every service" not in ln
    ]


def test_delta_the_drop_goes_children_first_with_deferred_fks(world: h.World) -> None:
    _reset_routes(world)
    env = world.env(**TOKEN_ENV)
    world.twin_run("scripts/ops/reset-bench.sh", ["--yes", "--d1-only"], env)
    bash_sql = next(
        c["body"]["sql"] for c in _curl_calls(world) if c["body"] and "DROP" in c["body"]["sql"]
    )
    assert bash_sql.startswith("PRAGMA foreign_keys = OFF;")  # the control: D1 ignores this
    assert bash_sql.index('"users"') < bash_sql.index('"we"ird"')  # and parents dropped first
    world.reset_log()
    world.port("rediacc_ci.ops.reset_bench", ["--yes", "--d1-only"], _reset_env(env))
    sql = next(
        c["body"]["sql"] for c in _curl_calls(world) if c["body"] and "DROP" in c["body"]["sql"]
    )
    assert sql.startswith("PRAGMA defer_foreign_keys = on;")
    assert sql.index('"we""ird"') < sql.index('"users"')


def test_drop_order_handles_chains_cycles_and_missing_sql() -> None:
    chain = [
        {"name": "a", "sql": "CREATE TABLE a(x)"},
        {"name": "b", "sql": "CREATE TABLE b(a REFERENCES a(x))"},
        {"name": "c", "sql": "CREATE TABLE c(b INT, FOREIGN KEY(b) REFERENCES `b`(x))"},
    ]
    assert reset_bench.drop_order(chain) == ["c", "b", "a"]
    cycle: list[dict] = [
        {"name": "p", "sql": "CREATE TABLE p(q REFERENCES q)"},
        {"name": "q", "sql": "CREATE TABLE q(p REFERENCES p)"},
        {"name": "z", "sql": None},
    ]
    assert sorted(reset_bench.drop_order(cycle)) == ["p", "q", "z"]
    assert reset_bench.drop_order(
        [{"name": "self", "sql": "CREATE TABLE self(p REFERENCES self(id))"}]
    ) == ["self"]


def test_reset_bench_r2_half_uses_the_s3_api(world: h.World) -> None:
    _reset_routes(world)
    env = world.env(**TOKEN_ENV, **R2_ENV)
    rc, _, err = world.port("rediacc_ci.ops.reset_bench", ["--yes", "--r2-only"], _reset_env(env))
    assert rc == 0, err
    curls = [c for c in world.calls() if c["tool"] == "curl" and "r2.example.invalid" in c["url"]]
    assert [(c["method"], c["url"].split("invalid/")[1]) for c in curls] == [
        ("GET", "rediacc-configs-bench?list-type=2&max-keys=1000"),
        ("DELETE", "rediacc-configs-bench/a/b%20c.json"),
        ("DELETE", "rediacc-configs-bench/d.json"),
    ]
    assert all(c["sigv4"] and c["creds_on_stdin"] and not c["creds_on_argv"] for c in curls)
    assert "r2-secret" not in json.dumps(world.calls())


def test_reset_bench_unknown_argument_and_confirmation_match_bash(world: h.World) -> None:
    _reset_routes(world)
    env = world.env(**TOKEN_ENV, **R2_ENV)
    rc_b, _, err_b = world.twin_run("scripts/ops/reset-bench.sh", ["--nope"], env)
    rc_p, _, err_p = world.port("rediacc_ci.ops.reset_bench", ["--nope"], _reset_env(env))
    assert rc_b == rc_p == 2
    assert h.strip(err_b) == h.strip(err_p)
    world.reset_log()
    rc_b, _, err_b = world.twin_run("scripts/ops/reset-bench.sh", [], env, stdin="no\n")
    assert [c for c in world.calls() if c["tool"] == "npx"] == []
    world.reset_log()
    rc_p, _, err_p = world.port("rediacc_ci.ops.reset_bench", [], _reset_env(env), stdin="no\n")
    assert rc_b == rc_p == 1
    assert "Aborted." in err_b
    assert "Aborted." in err_p
    assert [c for c in world.calls() if c["tool"] == "npx"] == []


def test_delta_a_failed_r2_listing_is_not_an_empty_bucket(world: h.World) -> None:
    failing = {
        "method": "GET",
        "match": "/r2/buckets/",
        "body": {"success": False, "errors": [{"message": "Authentication error"}]},
    }
    s3_denied = {
        "method": "GET",
        "match": "rediacc-configs-bench?list-type=2",
        "raw": "<Error>AccessDenied</Error>",
        "status": 403,
    }
    _reset_routes(world, failing, s3_denied)
    env = world.env(**TOKEN_ENV, **R2_ENV)
    rc_b, _, err_b = world.twin_run("scripts/ops/reset-bench.sh", ["--yes", "--r2-only"], env)
    assert rc_b == 0
    assert "bench has been reset" in err_b
    world.reset_log()
    rc_p, _, err_p = world.port(
        "rediacc_ci.ops.reset_bench", ["--yes", "--r2-only"], _reset_env(env)
    )
    assert rc_p == 1
    assert "HTTP 403" in err_p
    assert "bench has been reset" not in err_p


def test_delta_the_r2_credentials_are_checked_before_anything_is_wiped(world: h.World) -> None:
    _reset_routes(world)
    env = world.env(**TOKEN_ENV)
    rc, _, err = world.port("rediacc_ci.ops.reset_bench", ["--yes"], _reset_env(env))
    assert rc == 1
    assert "CLOUDFLARE_R2_ENDPOINT" in err
    assert world.calls() == []


def test_delta_table_names_are_quoted_as_data(world: h.World) -> None:
    _reset_routes(world)
    env = world.env(**TOKEN_ENV)
    world.twin_run("scripts/ops/reset-bench.sh", ["--yes", "--d1-only"], env)
    bash_sql = next(
        c["body"]["sql"] for c in _curl_calls(world) if c["body"] and "DROP" in c["body"]["sql"]
    )
    assert 'DROP TABLE IF EXISTS "we"ird"' in bash_sql  # the control: unescaped
    world.reset_log()
    world.port("rediacc_ci.ops.reset_bench", ["--yes", "--d1-only"], _reset_env(env))
    port_sql = next(
        c["body"]["sql"] for c in _curl_calls(world) if c["body"] and "DROP" in c["body"]["sql"]
    )
    assert 'DROP TABLE IF EXISTS "we""ird"' in port_sql


def test_delta_a_failed_object_delete_names_the_count(world: h.World) -> None:
    refused = {
        "method": "DELETE",
        "match": "rediacc-configs-bench/",
        "raw": "<Error>no</Error>",
        "status": 403,
    }
    _reset_routes(world, refused)
    env = world.env(**TOKEN_ENV, **R2_ENV)
    rc_p, _, err_p = world.port(
        "rediacc_ci.ops.reset_bench", ["--yes", "--r2-only"], _reset_env(env)
    )
    assert rc_p == 1
    assert "0 of 2 objects deleted" in err_p


def test_delta_end_of_input_at_the_prompt_aborts(world: h.World) -> None:
    _reset_routes(world)
    env = world.env(**TOKEN_ENV, **R2_ENV)
    rc_p, _, err_p = world.port("rediacc_ci.ops.reset_bench", [], _reset_env(env), stdin="")
    assert rc_p == 1
    assert "Aborted." in err_p


def test_delta_a_minted_token_is_awaited_before_the_first_query(world: h.World) -> None:
    _reset_routes(world, *h.PROBE_ROUTES)
    env = world.env(**GLOBAL_ENV, **R2_ENV)
    rc, _, err = world.port("rediacc_ci.ops.reset_bench", ["--yes", "--d1-only"], _reset_env(env))
    assert rc == 0, err
    curls = _curl_calls(world)
    assert [c["method"] for c in curls][:3] == ["GET", "GET", "POST"]
    first_query = next(i for i, c in enumerate(curls) if "/query" in c["url"])
    probed = [c["url"].split("/client/v4")[-1] for c in curls[3:first_query]]
    # Every slow service the token grants accepted it twice in a row before the first D1 query.
    assert probed == [
        "/user/tokens/verify",
        "/user/tokens/verify",
        "/accounts/%s/d1/database?per_page=1" % cf_auth.DEFAULT_ACCOUNT_ID,
        "/accounts/%s/d1/database?per_page=1" % cf_auth.DEFAULT_ACCOUNT_ID,
        "/accounts/%s/workers/scripts" % cf_auth.DEFAULT_ACCOUNT_ID,
        "/accounts/%s/workers/scripts" % cf_auth.DEFAULT_ACCOUNT_ID,
    ]
    assert all(c["method"] == "GET" for c in curls[3:first_query])


def test_delta_a_token_never_accepted_is_a_named_error_not_a_traceback(
    world: h.World, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    refused = {
        "method": "GET",
        "match": "/d1/database?per_page=1",
        "body": {"success": False, "errors": [{"code": 10000, "message": "Authentication error"}]},
    }
    _reset_routes(world, refused, *h.PROBE_ROUTES)
    # In-process, so the 60 s bound can be shortened without a test-only knob in the port.
    for key, value in world.env(**GLOBAL_ENV, **R2_ENV).items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("REDIACC_BWS_PROFILES", reset_bench.PROFILE)
    monkeypatch.chdir(world.root)
    monkeypatch.setattr(cf_auth, "READY_DEADLINE_S", 1.0)
    monkeypatch.setattr(cf_auth, "READY_INTERVAL_S", 0.2)
    rc = reset_bench.main(["--yes", "--d1-only"])
    err = capsys.readouterr().err
    assert rc == 1
    assert "not accepted by D1 (GET /accounts/%s/d1/database)" % cf_auth.DEFAULT_ACCOUNT_ID in err
    assert "[10000]" in err
    assert not any(
        "/query" in c["url"] for c in _curl_calls(world)
    )  # nothing ran on the refused token
    assert any(c["method"] == "DELETE" for c in _curl_calls(world))  # and it was still destroyed


def test_delta_reset_bench_re_executes_under_its_own_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PLAN-backup-credential-isolation B2: the R2 trio left the deploy-bench profile, so reset_bench binds its own. Not yet under `reset-bench` (here: under deploy-bench), it re-executes through `bws_env exec --profile reset-bench` with its arguments, and returns that run's status."""
    seen: list[list[str]] = []

    def fake_run(argv, **_kw):
        seen.append(list(argv))
        return subprocess.CompletedProcess(argv, 7)

    monkeypatch.setenv("REDIACC_BWS_PROFILES", "deploy-bench")
    monkeypatch.setattr(reset_bench.shutil, "which", lambda cmd: "/usr/bin/" + cmd)
    monkeypatch.setattr(reset_bench.subprocess, "run", fake_run)
    assert reset_bench.main(["--yes", "--r2-only"]) == 7
    assert len(seen) == 1
    argv = seen[0]
    assert argv[1:6] == ["-m", "rediacc_ci.core.bws_env", "exec", "--profile", "reset-bench"]
    assert argv[-3:] == ["rediacc_ci.ops.reset_bench", "--yes", "--r2-only"]


# ---------------------------------------------------------------- deploy_bench

DEPLOY_ENV = {
    "ACCOUNT_ED25519_PRIVATE_KEY": "e-priv",
    "ACCOUNT_ED25519_PUBLIC_KEY": "e-pub",
    "ACCOUNT_X25519_PRIVATE_KEY": "x-priv",
    "ACCOUNT_X25519_PUBLIC_KEY": "x-pub",
    "ACCOUNT_SERVER_API_KEY": "api",
    "ACCOUNT_JWT_SECRET": "jwt",
    "ROOT_EMAIL": "root@example.invalid",
    "AWS_SES_ACCESS_KEY_ID": "ses-id",
    "AWS_SES_SECRET_ACCESS_KEY": "ses-secret",
    "CLOUDFLARE_TURNSTILE_SECRET_KEY": "turn",
    "CLOUDFLARE_R2_ENDPOINT": "https://r2.example.invalid",
    "CLOUDFLARE_R2_ACCESS_KEY_ID": "r2-id",
    "CLOUDFLARE_R2_SECRET_ACCESS_KEY": "r2-secret",
    "OBS_OTLP_CREDENTIALS": json.dumps({"user": "u", "pass": "p"}),
    "SELLER_NAME": "Seller",
    "AWS_IAM_ADMIN_ACCESS_KEY_ID": "iam",
}


# PLAN-backup-credential-isolation B2 (Rule T 7 in deploy_bench's docstring): the retired bash filled ACCOUNT_BACKUP_S3_* from the account-wide R2 trio, and its golden was frozen with only that trio in the environment. The port reads only ACCOUNT_BACKUP_S3_*, so its side of each differential receives the SAME values under the backup names and without the R2 trio. The twin's environment, and with it every golden key, is unchanged.
R2_TO_BACKUP = {
    "CLOUDFLARE_R2_ENDPOINT": "ACCOUNT_BACKUP_S3_ENDPOINT",
    "CLOUDFLARE_R2_ACCESS_KEY_ID": "ACCOUNT_BACKUP_S3_ACCESS_KEY_ID",
    "CLOUDFLARE_R2_SECRET_ACCESS_KEY": "ACCOUNT_BACKUP_S3_SECRET_ACCESS_KEY",
}


def _port_deploy_env(env: dict[str, str]) -> dict[str, str]:
    """The twin's environment as the port's profile binds it: the R2 trio renamed to the three backup names, and the stored root password the port's seed reads (DECLARED DELTA: the retired bash seeded nothing)."""
    bound = {R2_TO_BACKUP.get(name, name): value for name, value in env.items()}
    bound["BENCH_ROOT_PASSWORD"] = "bench-root-password-1"
    # PLAN-config-server-key K2: the port reads the bench-only key the deploy-bench profile binds; the retired bash never did, so its env (and every golden key) is unchanged. A fake value, never a real key.
    bound["ACCOUNT_CONFIG_SERVER_KEY"] = "fake-config-server-key-for-tests"
    # PLAN-free-license F2 (e7647063b): the port pushes the FREE licence HMAC key the account Worker reads; the retired bash never held it. A fake value, never a real key.
    bound["FREE_LICENSE_HMAC_KEY"] = "fake-free-license-hmac-key-for-tests"
    return bound


# The secrets the port pushes and the retired bash never held: dropped from the compared body, each asserted present first in `test_deploy_bench_matches_bash`.
PORT_ONLY_SECRETS = ("ACCOUNT_CONFIG_SERVER_KEY", "FREE_LICENSE_HMAC_KEY")


# DECLARED DELTA (27861278): the port seeds the ROOT_EMAIL user after the secrets push (deploy_bench docstring item 8), a POST the retired bash never sent. The route answers it as a fresh bench would, added AFTER the twin run so the golden's route key is unchanged; the call is removed from the compared shape and its two stderr lines from the compared step list, each asserted present first so the removal cannot go vacuous.
SEED_PATH = "/account/api/v1/auth/register"
SEED_ROUTE = {"method": "POST", "match": SEED_PATH, "body": {"user": {}}, "status": 201}


def _is_seed_call(call: dict) -> bool:
    return call.get("tool") == "curl" and SEED_PATH in (call.get("url") or "")


def _deploy_shape(calls: list[dict]) -> list[dict]:
    """The comparable call list. The R2 trio is dropped from each call's `cf_env` (the CLOUDFLARE_* names its environment carried) because only the twin's environment holds it; `test_deploy_bench_matches_bash` asserts separately that no port call inherits it."""
    out = []
    for raw in h.normalise_calls(calls):
        if raw["tool"] == "sleep":
            continue
        # DECLARED DELTA (bb78feea5): the port prints the D1 bookmark before migrating, a `wrangler d1 time-travel info` call the retired bash never made.
        if raw["tool"] == "npx" and raw["argv"][2:5] == ["d1", "time-travel", "info"]:
            continue
        if _is_seed_call(raw):
            continue
        # DECLARED DELTA (263557163): the port lists the Worker's deployments after the secrets push to record the live version; the bash never did.
        if raw["tool"] == "npx" and raw["argv"][2:4] == ["deployments", "list"]:
            continue
        call = dict(raw)
        # DECLARED DELTA (2026-10-28): the keyless bench portal builds into bench/dist, never into the dist a production deploy uploads; the bash built into dist/account.
        if call["tool"] == "npx" and "vite" in call["argv"]:
            call["argv"] = [
                a.replace("/workers/account/bench/dist/", "/workers/account/dist/")
                for a in call["argv"]
            ]
        # DECLARED DELTA: the port runs `npx --no-install vite build` so npx never downloads vite; the retired bash ran a bare `npx vite build`, which is what the golden recorded. The flag is dropped here, only for vite, so every other argv still compares verbatim.
        if call["tool"] == "npx" and call["argv"][:2] == ["--no-install", "vite"]:
            call["argv"] = call["argv"][1:]
        # DECLARED DELTA (PLAN-config-server-key K2, PLAN-free-license F2): the port pushes PORT_ONLY_SECRETS, which the retired bash never held. Dropped from the compared body; `test_deploy_bench_matches_bash` asserts each present first.
        if isinstance(call.get("stdin"), dict):
            call["stdin"] = {k: v for k, v in call["stdin"].items() if k not in PORT_ONLY_SECRETS}
        kept = [n for n in call.get("cf_env") or () if n not in R2_TO_BACKUP]
        out.append({**call, "cf_env": kept} if call.get("cf_env") else call)
    return out


def test_deploy_bench_matches_bash(world: h.World) -> None:
    env = world.env(**TOKEN_ENV, **DEPLOY_ENV)
    rc_b, out_b, err_b = world.twin_run("scripts/ops/deploy-bench.sh", [], env)
    bash_calls = world.calls()
    world.reset_log()
    world.add_routes(SEED_ROUTE)
    rc_p, out_p, err_p = world.port("rediacc_ci.ops.deploy_bench", [], _port_deploy_env(env))
    port_calls = world.calls()
    assert rc_b == rc_p == 0, (err_b, err_p)
    assert any(_is_seed_call(c) for c in port_calls)
    # DECLARED DELTA (263557163): the port captures `wrangler deploy` to record its version and echoes that output to stdout; the bash's fake printed nothing there.
    version_line = "Current Version ID: 0b1f2c3d-4e5f-4a6b-8c7d-9e0f1a2b3c4d\n"
    assert out_p.count(version_line) == 1
    # DECLARED DELTA (12000ad33): the closing hint names the eu-bench config and its agent-run login, where the bash named a `bench` config that does not exist. Each port line is asserted once, then mapped back to the bash's.
    hint_delta = {
        "  npm run login:bench\n": "  ./rdc.sh --config bench subscription login\n",
        "  ./rdc.sh --config eu-bench repo create": "  ./rdc.sh --config bench repo create",
    }
    out_mapped = out_p.replace(version_line, "", 1)
    for port_text, bash_text in hint_delta.items():
        assert out_mapped.count(port_text) == 1
        out_mapped = out_mapped.replace(port_text, bash_text)
    assert out_b == out_mapped
    assert _deploy_shape(bash_calls) == _deploy_shape(port_calls)
    secrets = next(c["stdin"] for c in port_calls if c["tool"] == "npx" and c["stdin"])
    assert list(secrets)[:3] == [
        "ACCOUNT_ED25519_PRIVATE_KEY",
        "ACCOUNT_ED25519_PUBLIC_KEY",
        "ACCOUNT_X25519_PRIVATE_KEY",
    ]
    assert secrets["ACCOUNT_BACKUP_S3_BUCKET"] == "rediacc-backups-bench"
    assert secrets["ACCOUNT_CONFIG_SERVER_KEY"] == "fake-config-server-key-for-tests"
    assert secrets["FREE_LICENSE_HMAC_KEY"] == "fake-free-license-hmac-key-for-tests"
    assert secrets["ACCOUNT_BACKUP_S3_ENDPOINT"] == "https://r2.example.invalid"
    # The bash's fallback fired: with only the R2 trio in its environment it pushed the trio as the backup credential. The port received the same values under the backup names (`_port_deploy_env`).
    bash_secrets = next(c["stdin"] for c in bash_calls if c["tool"] == "npx" and c["stdin"])
    assert bash_secrets["ACCOUNT_BACKUP_S3_SECRET_ACCESS_KEY"] == "r2-secret"
    # And no wrangler child of the port inherits the account-wide trio, where every one of the bash's did.
    assert any(set(R2_TO_BACKUP) <= set(c.get("cf_env") or ()) for c in bash_calls)
    assert not any(set(R2_TO_BACKUP) & set(c.get("cf_env") or ()) for c in port_calls)
    assert secrets["STRIPE_SECRET_KEY"] == ""
    # Self-destruct output is a delta (the bash sent it to /dev/null). The portal build line is the other: bench is built with no Turnstile sitekey since the operator ruling of 2026-10-13, and the bash still names its key.
    bash_build = "→ Building account portal SPA (Turnstile sitekey: 0x4AAAAAAC46Rczgin0T1o04)"
    port_build = "→ Building account portal SPA (captcha disabled on bench: no Turnstile sitekey)"
    bash_lines = _quiet_selfdestruct(err_b)
    assert bash_lines.count(bash_build) == 1
    # DECLARED DELTAS since the bash was retired (bb78feea5 and the portal-health step): the port reports the D1 bookmark (here a missing one, the fake wrangler prints none). The live-host line is no delta: both outputs carry it once and it stays in the comparison.
    all_port_lines = _quiet_selfdestruct(err_p)
    # The delta is asserted before it is filtered, so a port that stops printing the bookmark warning, or drops the live-host line, still fails here.
    assert sum(ln.startswith("⚠ NO D1 BOOKMARK CAPTURED") for ln in all_port_lines) == 1
    assert sum(ln.startswith("✓ bench is live") for ln in all_port_lines) == 1
    seed_lines = ("→ Seeding the root user", "✓ root user created")
    assert sum(ln.startswith(seed_lines) for ln in all_port_lines) == 2
    port_lines = [
        ln
        for ln in all_port_lines
        if not ln.startswith("⚠ NO D1 BOOKMARK CAPTURED") and not ln.startswith(seed_lines)
    ]
    # DECLARED DELTA (263557163): the port records the live bench version; asserted once, then dropped.
    recorded = "✓ Bench version recorded in .ci/cache/live-deploys/bench.json"
    assert port_lines.count(recorded) == 1
    port_lines.remove(recorded)
    # DECLARED DELTA (2026-10-28): the build line names bench/dist/account, where the bash named dist/account.
    port_lines = [
        ln.replace("/workers/account/bench/dist/", "/workers/account/dist/") for ln in port_lines
    ]
    assert [port_build if ln == bash_build else ln for ln in bash_lines] == port_lines
    assert "r2-secret" not in err_p
    assert "ses-secret" not in err_p


def test_deploy_bench_tokens_minted_from_the_global_key_wait_then_are_destroyed(
    world: h.World,
) -> None:
    env = world.env(**GLOBAL_ENV, **DEPLOY_ENV)
    world.twin_run("scripts/ops/deploy-bench.sh", [], env)
    bash_calls = world.calls()
    assert any(c["tool"] == "sleep" for c in bash_calls)  # the control: the bash slept a fixed 5 s
    world.reset_log()
    world.add_routes(*h.PROBE_ROUTES, SEED_ROUTE)  # after the twin: the route table keys its golden
    rc, _, err = world.port("rediacc_ci.ops.deploy_bench", [], _port_deploy_env(env))
    assert rc == 0, err
    # The port probes instead: the probe block sits between the mint and the first wrangler call.
    port_calls, probes = h.split_probe_block(world.calls())
    assert {c["url"].split("/client/v4")[-1].split("?")[0] for c in probes} == {
        "/user/tokens/verify",
        "/accounts/%s/d1/database" % cf_auth.DEFAULT_ACCOUNT_ID,
        "/accounts/%s/workers/scripts" % cf_auth.DEFAULT_ACCOUNT_ID,
    }
    assert _deploy_shape(bash_calls) == _deploy_shape(port_calls)


def test_delta_a_supplied_token_does_not_wait(world: h.World) -> None:
    env = world.env(**TOKEN_ENV, **DEPLOY_ENV)
    world.twin_run("scripts/ops/deploy-bench.sh", [], env)
    assert any(c["tool"] == "sleep" for c in world.calls())  # the control
    world.reset_log()
    world.add_routes(*h.PROBE_ROUTES)
    world.port("rediacc_ci.ops.deploy_bench", [], _port_deploy_env(env))
    assert not any(c["tool"] == "sleep" for c in world.calls())
    assert not any(
        c["tool"] == "curl" and ("/d1/database?" in c["url"] or "/workers/scripts" in c["url"])
        for c in world.calls()
    )


def test_delta_arguments_are_rejected_not_ignored(world: h.World) -> None:
    env = world.env(**TOKEN_ENV, **DEPLOY_ENV)
    rc_b, _, _ = world.twin_run("scripts/ops/deploy-bench.sh", ["--dry-run"], env)
    assert rc_b == 0
    assert any(
        c["tool"] == "npx" and c["argv"][:3] == ["--no-install", "wrangler", "deploy"]
        for c in world.calls()
    )
    world.reset_log()
    rc_p, _, err_p = world.port("rediacc_ci.ops.deploy_bench", ["--dry-run"], env)
    assert rc_p == 2
    assert "takes no arguments" in err_p
    assert world.calls() == []


def test_delta_secrets_are_validated_before_the_first_remote_write(world: h.World) -> None:
    broken = {k: v for k, v in DEPLOY_ENV.items() if k != "ROOT_EMAIL"}
    env = world.env(**TOKEN_ENV, **broken)
    rc_b, _, err_b = world.twin_run("scripts/ops/deploy-bench.sh", [], env)
    assert rc_b == 1
    assert "ROOT_EMAIL is EMPTY" in h.strip(err_b)
    assert any(
        c["tool"] == "npx" and c["argv"][:3] == ["--no-install", "wrangler", "deploy"]
        for c in world.calls()
    )  # the control: deployed first
    world.reset_log()
    rc_p, _, err_p = world.port("rediacc_ci.ops.deploy_bench", [], _port_deploy_env(env))
    assert rc_p == 1
    assert "ROOT_EMAIL is EMPTY" in h.strip(err_p)
    assert not any(c["tool"] == "npx" for c in world.calls())


def test_delta_the_account_wide_r2_trio_alone_is_refused_before_any_remote_write(
    world: h.World,
) -> None:
    """Rule T 7. `test_deploy_bench_matches_bash` is the control: handed only the R2 trio, the bash deployed and pushed the trio's values as the backup credential. The port, handed that same environment untranslated, refuses before the first remote write and names the missing backup value."""
    env = world.env(**TOKEN_ENV, **DEPLOY_ENV)
    assert "ACCOUNT_BACKUP_S3_ENDPOINT" not in env
    assert _port_deploy_env(env)["ACCOUNT_BACKUP_S3_ENDPOINT"] == env["CLOUDFLARE_R2_ENDPOINT"]
    # Only the R2 trio stays untranslated: the port-only secrets are the port's own, so neither may be what refuses.
    bound = _port_deploy_env(env)
    keyed = {**env, **{name: bound[name] for name in PORT_ONLY_SECRETS}}
    rc_p, _, err_p = world.port("rediacc_ci.ops.deploy_bench", [], keyed)
    assert rc_p == 1
    assert "ACCOUNT_BACKUP_S3_ENDPOINT is EMPTY for bench" in h.strip(err_p)
    assert "r2-secret" not in err_p
    assert not any(c["tool"] == "npx" for c in world.calls())


def test_deploy_bench_rotation_drift_matches_bash(world: h.World) -> None:
    env = world.env(FAKE_ROTATION_RC="1", **TOKEN_ENV, **DEPLOY_ENV)
    rc_b, _, err_b = world.twin_run("scripts/ops/deploy-bench.sh", [], env)
    rc_p, _, err_p = world.port("rediacc_ci.ops.deploy_bench", [], _port_deploy_env(env))
    assert rc_b == rc_p == 1
    assert "rotation drift detected" in h.strip(err_b)
    assert "rotation drift detected" in h.strip(err_p)


UNCHECKED_STDERR = (
    "✗ drift detected on 1 credential:\n"  # a stale line from an unrelated block must not be reported
    "  ses-bench: version AKIA state mismatch\n"
    "! could not check 1 credential (the live value was not read, so this is NOT drift):\n"
    "  otlp-bench: observability query failed: ssh exit 255: reader@obs.example.test: Permission denied (publickey).\n"
)


def test_deploy_bench_refuses_on_a_check_that_could_not_run_and_never_pushes(
    world: h.World,
) -> None:
    # Exit 2 is "nothing drifted, a credential could not be checked". The comparison must always run (operator ruling 2026-10-13), so the secrets push is refused, with wording that names the credential and the cause and does not send the reader to rotate. No bash twin: the twin read any non-zero exit as drift.
    env = world.env(
        FAKE_ROTATION_RC="2", FAKE_ROTATION_STDERR=UNCHECKED_STDERR, **TOKEN_ENV, **DEPLOY_ENV
    )
    rc, _, err = world.port("rediacc_ci.ops.deploy_bench", [], _port_deploy_env(env))
    assert rc == 1, err
    text = h.strip(err)
    refusal = text.split("rotation check could NOT READ every credential", 1)[1]
    assert "not checked, otlp-bench: observability query failed: ssh exit 255" in refusal
    assert "ses-bench" not in refusal  # the drift block above it is a different finding
    assert "this is NOT drift" in refusal
    assert "rotation drift detected" not in text
    assert "rotation rotate" not in text
    assert not any(
        c["tool"] == "npx" and c["argv"][:4] == ["--no-install", "wrangler", "secret", "bulk"]
        for c in world.calls()
    )  # nothing was pushed


def test_deploy_bench_still_refuses_on_drift_and_never_pushes(world: h.World) -> None:
    env = world.env(
        FAKE_ROTATION_RC="1", FAKE_ROTATION_STDERR=UNCHECKED_STDERR, **TOKEN_ENV, **DEPLOY_ENV
    )
    rc, _, err = world.port("rediacc_ci.ops.deploy_bench", [], _port_deploy_env(env))
    assert rc == 1
    assert "rotation drift detected" in h.strip(err)
    assert not any(
        c["tool"] == "npx" and c["argv"][:4] == ["--no-install", "wrangler", "secret", "bulk"]
        for c in world.calls()
    )


# PLAN-backup-presign-bucket-require-and-wrangler-vars B4: the bench bucket is the BACKUP_BUCKET binding in wrangler.bench.toml, not an env override or a literal.
def _bench_repo(monkeypatch: pytest.MonkeyPatch, tmp_path, toml_text: str) -> None:
    worker = tmp_path / "workers" / "account"
    worker.mkdir(parents=True)
    (worker / deploy_bench.CONFIG).write_text(toml_text, encoding="utf-8")
    monkeypatch.setattr(deploy_bench.paths, "repo_root", lambda: tmp_path)


BENCH_TOML = (
    'name = "rediacc-account-bench"\n\n'
    "[[r2_buckets]]\n"
    'binding = "BACKUP_BUCKET"\n'
    'bucket_name = "bound-backups-bench"\n'
)


def test_deploy_bench_bucket_comes_from_the_binding(monkeypatch, tmp_path) -> None:
    _bench_repo(monkeypatch, tmp_path, BENCH_TOML)
    monkeypatch.delenv("ACCOUNT_BACKUP_S3_BUCKET", raising=False)
    assert deploy_bench.bench_bucket() == "bound-backups-bench"
    monkeypatch.setenv("ACCOUNT_BACKUP_S3_BUCKET", "bound-backups-bench")
    assert deploy_bench.bench_bucket() == "bound-backups-bench"


def test_deploy_bench_refuses_an_env_bucket_that_differs_from_the_binding(
    monkeypatch, tmp_path
) -> None:
    _bench_repo(monkeypatch, tmp_path, BENCH_TOML)
    monkeypatch.setenv("ACCOUNT_BACKUP_S3_BUCKET", "some-other-bucket")
    with pytest.raises(deploy_bench.DeployError, match="bound-backups-bench"):
        deploy_bench.bench_bucket()


def test_deploy_bench_refuses_a_config_with_no_backup_binding(monkeypatch, tmp_path) -> None:
    _bench_repo(monkeypatch, tmp_path, 'name = "rediacc-account-bench"\n')
    monkeypatch.delenv("ACCOUNT_BACKUP_S3_BUCKET", raising=False)
    with pytest.raises(deploy_bench.DeployError, match="BACKUP_BUCKET"):
        deploy_bench.bench_bucket()
