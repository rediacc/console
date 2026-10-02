"""Differentials and Rule T delta tests for the Cloudflare operator ports: `cf_auth`, `backup_d1`, `reset_bench`, `deploy_bench`.

EACH PORT IS DRIVEN AGAINST ITS BASH TWIN with the same fake `curl`/`npx` on a sealed PATH (`ops_cf_harness.World`), comparing the call log (method, URL, parsed body, argv, cwd), stdout, stderr (ANSI stripped: the bash colours unconditionally, the port only on a tty) and the exit code. A test named `test_delta_*` pins one deliberate Rule T difference: it asserts the bash behaviour first (the control, so the delta cannot be a vacuous pass) and then the port's.

The real-target runs that are the acceptance for these scripts are the lead's recorded runs; this file is the CI-runnable regression net.
"""

from __future__ import annotations

import json
import time
import typing

import pytest

from rediacc_ci.ops import reset_bench
from rediacc_ci.tests import ops_cf_harness as h

if typing.TYPE_CHECKING:
    import pathlib

TOKEN_ENV = {"CF_MANAGEMENT_TOKEN": "supplied-token"}
GLOBAL_ENV = {"CF_GLOBAL_API_KEY": "gk", "CF_EMAIL": "ops@example.invalid"}


@pytest.fixture
def world(tmp_path: pathlib.Path) -> h.World:
    return h.World(tmp_path)


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
    # The POST differs by exactly one added permission group (Workers R2 Storage Write): the bash token could not list buckets.
    post = bash_calls[2]["body"]
    port_post = port_calls[2]["body"]
    extra = [
        g
        for g in port_post["policies"][0]["permission_groups"]
        if g not in post["policies"][0]["permission_groups"]
    ]
    assert extra == [{"id": "bf7481a1826f439697cb59a20b22293e"}]
    port_post["policies"][0]["permission_groups"].remove(extra[0])
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
    stripped = lambda t: h.mask_stamp(h.mask_root(h.strip(t), world))  # noqa: E731
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
    # ONE DECLARED DELTA: the usage line names the module the way it is run now. The bash script it named was deleted (882658c69), so the golden's line is mapped before the comparison, and the golden is asserted to carry it so the mapping cannot go vacuous.
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
    rc_p, out_p, err_p = world.port("rediacc_ci.ops.reset_bench", ["--yes", "--d1-only"], env)
    port_calls = world.calls()
    assert rc_b == rc_p == 0, (err_b, err_p)
    # ONE DECLARED DELTA: the closing hint names the bench deploy the way it is run now. The bash script it named was retired (PLAN-retire-bash-oracles B3), so the golden's line is mapped before the comparison, and the golden is asserted to carry it so the mapping cannot go vacuous.
    redeploy_bash = "To redeploy fresh code: scripts/ops/deploy-bench.sh\n"
    redeploy_port = (
        "To redeploy fresh code: PYTHONPATH=.ci python3 -m rediacc_ci.ops.deploy_bench\n"
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
    assert npx[0]["argv"][:4] == ["wrangler", "d1", "migrations", "apply"]
    assert {"CLOUDFLARE_ACCOUNT_ID", "CLOUDFLARE_API_TOKEN"} <= set(npx[0]["cf_env"])
    assert not {"CF_GLOBAL_API_KEY", "CF_EMAIL", "CF_API_KEY"} & set(npx[0]["cf_env"])
    # The "Dropping N tables: ..." line lists them in drop order, which is the delta pinned below.
    assert [ln for ln in _quiet_selfdestruct(err_b) if "Dropping" not in ln] == [
        ln for ln in _quiet_selfdestruct(err_p) if "Dropping" not in ln
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
    world.port("rediacc_ci.ops.reset_bench", ["--yes", "--d1-only"], env)
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
    rc, _, err = world.port("rediacc_ci.ops.reset_bench", ["--yes", "--r2-only"], env)
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
    rc_p, _, err_p = world.port("rediacc_ci.ops.reset_bench", ["--nope"], env)
    assert rc_b == rc_p == 2
    assert h.strip(err_b) == h.strip(err_p)
    world.reset_log()
    rc_b, _, err_b = world.twin_run("scripts/ops/reset-bench.sh", [], env, stdin="no\n")
    assert [c for c in world.calls() if c["tool"] == "npx"] == []
    world.reset_log()
    rc_p, _, err_p = world.port("rediacc_ci.ops.reset_bench", [], env, stdin="no\n")
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
    rc_p, _, err_p = world.port("rediacc_ci.ops.reset_bench", ["--yes", "--r2-only"], env)
    assert rc_p == 1
    assert "HTTP 403" in err_p
    assert "bench has been reset" not in err_p


def test_delta_the_r2_credentials_are_checked_before_anything_is_wiped(world: h.World) -> None:
    _reset_routes(world)
    env = world.env(**TOKEN_ENV)
    rc, _, err = world.port("rediacc_ci.ops.reset_bench", ["--yes"], env)
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
    world.port("rediacc_ci.ops.reset_bench", ["--yes", "--d1-only"], env)
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
    rc_p, _, err_p = world.port("rediacc_ci.ops.reset_bench", ["--yes", "--r2-only"], env)
    assert rc_p == 1
    assert "0 of 2 objects deleted" in err_p


def test_delta_end_of_input_at_the_prompt_aborts(world: h.World) -> None:
    _reset_routes(world)
    env = world.env(**TOKEN_ENV, **R2_ENV)
    rc_p, _, err_p = world.port("rediacc_ci.ops.reset_bench", [], env, stdin="")
    assert rc_p == 1
    assert "Aborted." in err_p


def test_delta_a_minted_token_is_awaited_before_the_first_query(world: h.World) -> None:
    _reset_routes(world)
    env = world.env(**GLOBAL_ENV, **R2_ENV)
    started = time.monotonic()
    rc, _, err = world.port("rediacc_ci.ops.reset_bench", ["--yes", "--d1-only"], env)
    assert rc == 0, err
    assert time.monotonic() - started >= 7.5
    assert [c["method"] for c in _curl_calls(world)][:3] == ["GET", "GET", "POST"]


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


def _deploy_shape(calls: list[dict]) -> list[dict]:
    return [c for c in h.normalise_calls(calls) if c["tool"] != "sleep"]


def test_deploy_bench_matches_bash(world: h.World) -> None:
    env = world.env(**TOKEN_ENV, **DEPLOY_ENV)
    rc_b, out_b, err_b = world.twin_run("scripts/ops/deploy-bench.sh", [], env)
    bash_calls = world.calls()
    world.reset_log()
    rc_p, out_p, err_p = world.port("rediacc_ci.ops.deploy_bench", [], env)
    port_calls = world.calls()
    assert rc_b == rc_p == 0, (err_b, err_p)
    assert out_b == out_p
    assert _deploy_shape(bash_calls) == _deploy_shape(port_calls)
    secrets = next(c["stdin"] for c in port_calls if c["tool"] == "npx" and c["stdin"])
    assert list(secrets)[:3] == [
        "ACCOUNT_ED25519_PRIVATE_KEY",
        "ACCOUNT_ED25519_PUBLIC_KEY",
        "ACCOUNT_X25519_PRIVATE_KEY",
    ]
    assert secrets["ACCOUNT_BACKUP_S3_BUCKET"] == "rediacc-backups-bench"
    assert secrets["ACCOUNT_BACKUP_S3_ENDPOINT"] == "https://r2.example.invalid"
    assert secrets["STRIPE_SECRET_KEY"] == ""
    # Self-destruct output is the delta (the bash sent it to /dev/null); everything else is the same text.
    assert _quiet_selfdestruct(err_b) == _quiet_selfdestruct(err_p)
    assert "r2-secret" not in err_p
    assert "ses-secret" not in err_p


def test_deploy_bench_tokens_minted_from_the_global_key_wait_then_are_destroyed(
    world: h.World,
) -> None:
    env = world.env(**GLOBAL_ENV, **DEPLOY_ENV)
    world.twin_run("scripts/ops/deploy-bench.sh", [], env)
    bash_calls = world.calls()
    assert any(c["tool"] == "sleep" for c in bash_calls)
    world.reset_log()
    started = time.monotonic()
    world.port("rediacc_ci.ops.deploy_bench", [], env)
    assert (
        time.monotonic() - started >= 7.5
    )  # the port waits itself (time.sleep), not via a `sleep` binary
    port_calls = world.calls()
    assert _deploy_shape(bash_calls) == _deploy_shape(port_calls)


def test_delta_a_supplied_token_does_not_wait(world: h.World) -> None:
    env = world.env(**TOKEN_ENV, **DEPLOY_ENV)
    world.twin_run("scripts/ops/deploy-bench.sh", [], env)
    assert any(c["tool"] == "sleep" for c in world.calls())  # the control
    world.reset_log()
    world.port("rediacc_ci.ops.deploy_bench", [], env)
    assert not any(c["tool"] == "sleep" for c in world.calls())


def test_delta_arguments_are_rejected_not_ignored(world: h.World) -> None:
    env = world.env(**TOKEN_ENV, **DEPLOY_ENV)
    rc_b, _, _ = world.twin_run("scripts/ops/deploy-bench.sh", ["--dry-run"], env)
    assert rc_b == 0
    assert any(
        c["tool"] == "npx" and c["argv"][:2] == ["wrangler", "deploy"] for c in world.calls()
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
        c["tool"] == "npx" and c["argv"][:2] == ["wrangler", "deploy"] for c in world.calls()
    )  # the control: deployed first
    world.reset_log()
    rc_p, _, err_p = world.port("rediacc_ci.ops.deploy_bench", [], env)
    assert rc_p == 1
    assert "ROOT_EMAIL is EMPTY" in h.strip(err_p)
    assert not any(c["tool"] == "npx" for c in world.calls())


def test_deploy_bench_rotation_drift_matches_bash(world: h.World) -> None:
    env = world.env(FAKE_ROTATION_RC="1", **TOKEN_ENV, **DEPLOY_ENV)
    rc_b, _, err_b = world.twin_run("scripts/ops/deploy-bench.sh", [], env)
    rc_p, _, err_p = world.port("rediacc_ci.ops.deploy_bench", [], env)
    assert rc_b == rc_p == 1
    assert "rotation drift detected" in h.strip(err_b)
    assert "rotation drift detected" in h.strip(err_p)
