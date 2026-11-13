"""`./run.sh enterprise export|remove` (box C2): the verbs reach the production Exporter and Teardown, built lazily from the environment.

Nothing here reaches Cloudflare, R2 or bws: the wrangler, S3, http, bws and KV seams are recording fakes.
"""

from __future__ import annotations

import json
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


COMPANY_KEY_ID = "company-key-id"
KEYPAIR_ENTRY = "%s_ACCOUNT_BACKUP_S3_KEYPAIR" % ACME
CONFIGS_KEY_ID = "configs-key-id"
CONFIGS_ENTRY = "%s_COMPANY_CONFIGS_S3_KEYPAIR" % ACME


class FakeStore:
    """Holds a value for every name; the backups key pair is a real pair entry unless `without_pair`."""

    without_pair = False
    without_configs_pair = False

    def read(self, names: Any) -> dict[str, str]:
        out = dict.fromkeys(names, "value")
        if CONFIGS_ENTRY in out:
            if self.without_configs_pair:
                del out[CONFIGS_ENTRY]
            else:
                out[CONFIGS_ENTRY] = json.dumps(
                    dict(zip(secrets.CONFIGS_PAIR, (CONFIGS_KEY_ID, "configs-secret"), strict=True))
                )
        if KEYPAIR_ENTRY in out:
            if self.without_pair:
                del out[KEYPAIR_ENTRY]
            else:
                out[KEYPAIR_ENTRY] = json.dumps(
                    dict(zip(secrets.BACKUP_PAIR, (COMPANY_KEY_ID, "company-secret"), strict=True))
                )
        return out

    def create(self, _name: str, _value: str) -> None:
        raise AssertionError("lifecycle never writes secrets")


class Rig:
    def __init__(self, tmp_path: pathlib.Path) -> None:
        self.dbs: dict[str, sqlite3.Connection] = {}
        self.tmp = tmp_path
        self.wrangler_argvs: list[list[str]] = []
        self.s3_calls: list[tuple[str, str]] = []
        self.s3_endpoints: list[str] = []
        self.company_s3_calls: list[tuple[str, str]] = []
        self.company_key_ids: list[str] = []
        self.http_calls: list[tuple[str, str]] = []
        self.deleted: list[str] = []
        self.kv: list[list[str]] = []
        self.seams = cli.LiveSeams(
            wrangler=lambda _cwd, _env: self._wrangler,
            s3=self._s3_factory,
            company_s3=self._company_s3_factory,
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

    def _company_s3_factory(self, _endpoint: str, key_id: str, _secret: str) -> la.S3:
        self.company_key_ids.append(key_id)

        def call(method: str, path: str) -> tuple[int, bytes]:
            self.company_s3_calls.append((method, path))
            if method == "GET" and "?" in path:
                return 200, b"<ListBucketResult><IsTruncated>false</IsTruncated></ListBucketResult>"
            return 404, b""

        return call

    def _http(self, method: str, path: str, body: str | None = None, extra: Any = ()) -> dict:
        del body, extra
        self.http_calls.append((method, path))
        # The teardown reads the rediacc.cloud zone before it lists the company's routes (2f9bee93c0).
        if path.startswith("/zones?name="):
            return {"success": True, "result": [{"id": "z1"}]}
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
    assert any(m == "GET" and p.startswith("configs-acme") for m, p in rig.company_s3_calls)


def test_export_lists_the_backups_bucket_with_the_company_key_and_not_the_shared_pair(rig):
    assert _export(rig, CF_ENV) == 0
    assert COMPANY_KEY_ID in rig.company_key_ids
    assert any(m == "GET" and p.startswith("backups-acme") for m, p in rig.company_s3_calls)
    assert not any(p.startswith("backups-acme") for _m, p in rig.s3_calls), rig.s3_calls


def test_export_lists_the_configs_bucket_with_the_configs_key_and_not_the_shared_pair(rig):
    assert _export(rig, CF_ENV) == 0
    assert CONFIGS_KEY_ID in rig.company_key_ids
    assert not any(p.startswith("configs-acme") for _m, p in rig.s3_calls), rig.s3_calls
    # control: the backups listing is signed with the backups key, never the configs one
    assert rig.company_key_ids.count(CONFIGS_KEY_ID) == 1
    assert rig.company_key_ids.count(COMPANY_KEY_ID) == 1


def test_export_without_the_configs_key_names_the_bucket_and_the_mint_command(
    rig, capsys, monkeypatch
):
    store = FakeStore()
    store.without_configs_pair = True
    monkeypatch.setattr(secrets.BwsStore, "from_env", classmethod(lambda _c, _p, _e=None: store))
    assert _export(rig, CF_ENV) == 1
    said = _said(capsys)
    assert "configs-acme" in said
    assert CONFIGS_ENTRY in said
    assert "enterprise configs-key acme" in said
    assert "configs-secret" not in said


def test_export_without_the_company_key_in_the_store_names_the_entry(rig, capsys, monkeypatch):
    store = FakeStore()
    store.without_pair = True
    monkeypatch.setattr(secrets.BwsStore, "from_env", classmethod(lambda _c, _p, _e=None: store))
    assert _export(rig, CF_ENV) == 1
    said = _said(capsys)
    assert KEYPAIR_ENTRY in said
    assert "backups-acme" in said
    assert "holds no key for bucket" in said
    assert "company-secret" not in said
    assert not any(p.startswith("backups-acme") for _m, p in rig.company_s3_calls)


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


def test_export_does_not_need_the_shared_r2_pair(rig):
    # Both company buckets are read with the company's own keys, so the shared pair (scoped to releases and configs-bench) is not required.
    env = {k: v for k, v in CF_ENV.items() if "R2" not in k}
    assert _export(rig, env) == 0
    assert rig.s3_calls == []


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


# --- configs-key -----------------------------------------------------------------------


class MintStore(FakeStore):
    def __init__(self, *, holds_configs: bool) -> None:
        self.without_configs_pair = not holds_configs
        self.created: list[tuple[str, str]] = []

    def create(self, name: str, value: str) -> None:
        self.created.append((name, value))


class RecordingMinter:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def r2_bucket_token(self, token_name: str, bucket_resource: str) -> tuple[str, str]:
        self.calls.append((token_name, bucket_resource))
        return "minted-id", "minted-value"

    def ses_user(self, _user_name: str) -> tuple[str, str]:
        raise AssertionError("configs-key mints no SES user")


def _configs_key(rig, monkeypatch, store, minter, extra=("--bws-project", PROJECT), env=None):
    monkeypatch.setattr(secrets.BwsStore, "from_env", classmethod(lambda _c, _p, _e=None: store))
    environ = CF_ENV if env is None else env
    return cli.configs_key_main(
        ["acme", *extra],
        context=rig.context(environ),
        minter=minter,
        env=environ,
    )


def test_configs_key_mints_the_configs_only_key_for_a_company_without_one(rig, monkeypatch, capsys):
    store, minter = MintStore(holds_configs=False), RecordingMinter()
    assert _configs_key(rig, monkeypatch, store, minter) == 0
    assert [n for n, _v in store.created] == [CONFIGS_ENTRY]
    ((token_name, resource),) = minter.calls
    assert token_name.endswith("-configs")
    assert resource.endswith("_configs-acme")
    assert "minted" in _said(capsys)
    assert "minted-value" not in _said(capsys)


def test_configs_key_is_idempotent_when_the_store_holds_the_key(rig, monkeypatch, capsys):
    store, minter = MintStore(holds_configs=True), RecordingMinter()
    assert _configs_key(rig, monkeypatch, store, minter) == 0
    assert store.created == []
    assert minter.calls == []
    assert "already stored" in _said(capsys)


def test_configs_key_without_a_bws_project_refuses_naming_the_flag(rig, monkeypatch, capsys):
    store, minter = MintStore(holds_configs=False), RecordingMinter()
    assert _configs_key(rig, monkeypatch, store, minter, extra=()) == 1
    assert "--bws-project" in _said(capsys)
    assert minter.calls == []


def test_configs_key_without_the_management_token_refuses_naming_it(rig, monkeypatch, capsys):
    store = MintStore(holds_configs=False)
    assert _configs_key(rig, monkeypatch, store, None) == 1
    assert "CF_MANAGEMENT_TOKEN" in _said(capsys)
    assert store.created == []
