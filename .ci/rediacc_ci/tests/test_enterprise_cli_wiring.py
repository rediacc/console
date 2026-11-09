"""`./run.sh enterprise export|remove` (box C2): the verbs reach the production Exporter and Teardown, built lazily from the environment.

Nothing here reaches Cloudflare, R2 or bws: the wrangler, S3, http, bws and KV seams are recording fakes.
"""

from __future__ import annotations

import pathlib
import sqlite3
from typing import Any

import pytest

from rediacc_ci.enterprise import cli, lifecycle, registry, secrets
from rediacc_ci.enterprise import lifecycle_adapters as la

NOW = "2026-11-09T10:00:00Z"
ACME = "c0123456789abcdef"
ACCOUNT = "a" * 32
PROJECT = "proj-enterprise"
DOMAIN = "acme-corp.example"
CF_ENV = {
    cli.CF_API_ENV: "cf-token",
    cli.ACCOUNT_ENV: ACCOUNT,
    "CLOUDFLARE_R2_ACCESS_KEY_ID": "kid",
    "CLOUDFLARE_R2_SECRET_ACCESS_KEY": "ksecret",
}


def _empty() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(registry.migration_sql())
    return conn


def _control() -> sqlite3.Connection:
    conn = _empty()
    conn.execute(
        "INSERT INTO companies (id, name, region, state, created_at, updated_at) VALUES (?,?,?,?,?,?)",
        (ACME, "acme", "eu", "active", NOW, NOW),
    )
    conn.execute(
        "INSERT INTO scope (company_id, subscription_id, renewal_host, max_machines, max_storage_gb, max_expiry_days) "
        "VALUES (?,?,?,?,?,?)",
        (ACME, "sub", "acme.example", 10, 100, 30),
    )
    conn.commit()
    return conn


class FakeStore:
    def read(self, names: Any) -> dict[str, str]:
        return dict.fromkeys(names, "value")

    def create(self, _name: str, _value: str) -> None:
        raise AssertionError("lifecycle never writes secrets")


class Rig:
    def __init__(self, tmp_path: pathlib.Path) -> None:
        self.dbs: dict[str, sqlite3.Connection] = {}
        self.tmp = tmp_path
        self.wrangler_argvs: list[list[str]] = []
        self.s3_calls: list[tuple[str, str]] = []
        self.s3_endpoints: list[str] = []
        self.http_calls: list[tuple[str, str]] = []
        self.deleted: list[str] = []
        self.kv: list[list[str]] = []
        self.seams = cli.LiveSeams(
            wrangler=lambda _cwd, _env: self._wrangler,
            s3=self._s3_factory,
            http=lambda _headers: self._http,
            bws=lambda _project, _env: (self._rows, self._delete),
            lookup_run=self._kv,
        )

    def query(self, database: str, sql: str, params: Any) -> list[dict]:
        conn = self.dbs.setdefault(database, _control() if database.endswith("eu") else _empty())
        cur = conn.execute(sql, params)
        rows = [dict(r) for r in cur.fetchall()] if cur.description else []
        conn.commit()
        return rows

    def _wrangler(self, argv: list[str]) -> int:
        self.wrangler_argvs.append(list(argv))
        out = next(a.split("=", 1)[1] for a in argv if a.startswith("--output="))
        pathlib.Path(out).write_text("-- dump\n")
        return 0

    def _s3_factory(self, endpoint: str, _env: Any) -> la.S3:
        self.s3_endpoints.append(endpoint)

        def call(method: str, path: str) -> tuple[int, bytes]:
            self.s3_calls.append((method, path))
            if method == "GET" and "?" in path:
                return 200, b"<ListBucketResult><IsTruncated>false</IsTruncated></ListBucketResult>"
            return 404, b""

        return call

    def _http(self, method: str, path: str, body: str | None = None, extra: Any = ()) -> dict:
        del body, extra
        self.http_calls.append((method, path))
        return {"success": True, "result": [], "result_info": {"total_pages": 1}}

    def _rows(self) -> list[dict]:
        return []

    def _delete(self, secret_id: str) -> int:
        self.deleted.append(secret_id)
        return 0

    def _kv(self, argv: list[str], _env: dict) -> int:
        self.kv.append(list(argv))
        return 0

    def context(self, env: dict[str, str]) -> Any:
        def build(lc: Any, **opts: Any) -> Any:
            return cli.lifecycle_context(lc, query=self.query, seams=self.seams, env=env, **opts)

        return build


@pytest.fixture
def rig(tmp_path, monkeypatch):
    monkeypatch.setattr(
        secrets.BwsStore, "from_env", classmethod(lambda _c, _p, _e=None: FakeStore())
    )
    monkeypatch.setenv("ENTERPRISE_LOOKUP_PEPPER", "pepper-never-shown")
    return Rig(tmp_path)


def _said(capsys: Any) -> str:
    seen = capsys.readouterr()
    return seen.out + seen.err


def _export(rig: Rig, env: dict[str, str]) -> int:
    argv = ["export", "acme", "--bws-project", PROJECT, "--export-root", str(rig.tmp / "x")]
    return cli.main(argv, context=rig.context(env))


def test_export_reaches_a_real_cloudflare_exporter(rig):
    assert _export(rig, CF_ENV) == 0
    (argv,) = rig.wrangler_argvs
    assert "d1" in argv
    assert "account-acme" in argv
    assert rig.s3_endpoints
    assert all(e.startswith("https://%s." % ACCOUNT) for e in rig.s3_endpoints)
    assert any(m == "GET" and p.startswith("configs-acme") for m, p in rig.s3_calls)


def test_remove_reaches_a_real_cloudflare_teardown(rig):
    assert _export(rig, CF_ENV) == 0
    argv = [
        *("remove", "acme", "--delete-data", "--confirm", "acme"),
        *("--bws-project", PROJECT, "--export-root", str(rig.tmp / "x")),
        *("--lookup-domain", DOMAIN),
    ]
    assert cli.main(argv, context=rig.context(CF_ENV)) == 0
    assert any("/accounts/%s/" % ACCOUNT in p for _m, p in rig.http_calls)
    assert rig.kv
    assert rig.kv[0][:3] == ["kv", "key", "delete"]


@pytest.mark.parametrize("missing", [cli.CF_API_ENV, cli.ACCOUNT_ENV])
def test_export_without_a_credential_refuses_naming_it(rig, missing, capsys):
    env = {k: v for k, v in CF_ENV.items() if k != missing}
    assert _export(rig, env) == 1
    assert missing in _said(capsys)
    assert rig.wrangler_argvs == []


def test_export_without_the_r2_pair_refuses_naming_it(rig, capsys):
    env = {k: v for k, v in CF_ENV.items() if "R2" not in k}
    rig.seams = cli.LiveSeams(wrangler=rig.seams.wrangler)
    assert _export(rig, env) == 1
    assert "CLOUDFLARE_R2_ACCESS_KEY_ID" in _said(capsys)


def test_remove_without_a_bws_project_refuses_naming_the_flag(rig, capsys):
    assert _export(rig, CF_ENV) == 0
    argv = [
        *("remove", "acme", "--delete-data", "--confirm", "acme"),
        *("--export-root", str(rig.tmp / "x")),
    ]
    assert cli.main(argv, context=rig.context(CF_ENV)) == 1
    assert "--bws-project" in _said(capsys)
    assert rig.http_calls == []


def test_list_needs_no_credentials(rig, capsys):
    assert cli.main(["list"], context=rig.context({})) == 0
    assert "acme" in capsys.readouterr().out
    assert rig.wrangler_argvs == []
    assert rig.http_calls == []


def test_the_context_builds_no_adapter_until_a_verb_uses_it():
    ctx = cli.lifecycle_context(lifecycle, bench=False, query=lambda _d, _s, _p: [], env={})
    assert isinstance(ctx.exporter, cli.Lazy)
    assert isinstance(ctx.teardown, cli.Lazy)


class _Region:
    def __init__(self, region: str):
        self.region = region


def test_lazy_builds_one_adapter_per_region():
    built: list[str] = []

    class Inner:
        def __init__(self, region: str):
            self.region = region

        def where(self, _company: Any) -> str:
            return self.region

    def build(region: str) -> Inner:
        built.append(region)
        return Inner(region)

    lazy = cli.Lazy(RuntimeError, build)
    assert lazy.where(_Region("eu")) == "eu"
    assert lazy.where(_Region("us")) == "us"
    assert lazy.where(_Region("eu")) == "eu"
    assert built == ["eu", "us"]


def test_lazy_refuses_a_call_with_no_company():
    with pytest.raises(RuntimeError, match="before a company was named"):
        cli.Lazy(RuntimeError, lambda _r: None).anything()


def test_the_remove_usage_names_every_flag_the_parser_takes():
    remove = next(line for line in cli.__doc__.splitlines() if "enterprise remove" in line)
    block = cli.__doc__[cli.__doc__.index(remove) :].split("\n    ./run.sh enterprise release")[0]
    parser = cli._lifecycle_parser("remove")
    flags = {
        opt for opt in parser._option_string_actions if opt.startswith("--") and opt != "--help"
    }
    # The parser must still take the flags the usage block promises, and name no flag the block omits.
    for flag in ("--lookup-domain", "--bws-project", "--export-root", "--delete-data", "--confirm"):
        assert flag in flags, flag
    assert [f for f in sorted(flags) if f not in block and f not in ("--bench", "--resume")] == []


def test_lazy_refuses_a_call_with_no_company_once_two_regions_are_built():
    class Inner:
        def read(self, key: str) -> str:
            return key

        def dump(self, _company: Any) -> str:
            return "dump"

    lazy = cli.Lazy(RuntimeError, lambda _r: Inner())
    lazy.dump(_Region("eu"))
    lazy.dump(_Region("us"))
    with pytest.raises(RuntimeError, match="ambiguous"):
        lazy.read("k")


def test_bws_listing_refusal_names_the_first_line_of_the_reason(monkeypatch):
    def refuse(*_a, **_k):
        raise cli.bws_env.RefusalError(["first line", "second line"])

    monkeypatch.setattr(cli.bws_env, "with_token", dict)
    monkeypatch.setattr(cli.bws_env, "binary", lambda _env: "/bin/bws")
    monkeypatch.setattr(cli.bws_env, "listing", refuse)
    list_rows, _delete = cli._live_bws(RuntimeError, {})
    with pytest.raises(RuntimeError, match=r"^bws secret list failed: first line$"):
        list_rows()
    monkeypatch.setattr(
        cli.bws_env,
        "listing",
        lambda *_a, **_k: (_ for _ in ()).throw(cli.bws_env.RefusalError([""])),
    )
    with pytest.raises(RuntimeError, match=r"^bws secret list failed$"):
        list_rows()


def test_lazy_sends_a_call_without_a_company_to_the_last_named_adapter():
    class Inner:
        def read(self, key: str) -> str:
            return "got %s" % key

        def dump(self, _company: Any) -> str:
            return "dump"

    lazy = cli.Lazy(RuntimeError, lambda _r: Inner())
    assert lazy.dump(_Region("eu")) == "dump"
    assert lazy.read("k") == "got k"
