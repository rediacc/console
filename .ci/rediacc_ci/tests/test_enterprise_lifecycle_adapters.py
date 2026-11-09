"""enterprise.lifecycle_adapters: the production Exporter and Teardown, driven over recording fakes of wrangler, the R2 S3 endpoint, the Cloudflare API and bws.

Nothing here reaches Cloudflare, AWS or bws. The fakes keep the state a real account would (Workers, D1 databases, buckets, tokens, store rows), so a rerun after a failure is checked against what the first run already removed.
"""

from __future__ import annotations

import json
import pathlib
import sqlite3
import stat
import subprocess
import urllib.parse
from typing import Any

import pytest

from rediacc_ci.core import wrangler
from rediacc_ci.enterprise import lifecycle, registry, secrets
from rediacc_ci.enterprise import lifecycle_adapters as la
from rediacc_ci.ops import cf_auth, enterprise_lookup

NOW = "2026-11-09T10:00:00Z"
ACME = "c0123456789abcdef"
ACCOUNT = "a" * 32
SECRET_VALUE = "s3cr3t-value-never-shown"
PEPPER = "pepper-never-shown"
PROJECT = "proj-enterprise"
DOMAIN = "acme-corp.example"


def _company(unlisted: bool = False) -> lifecycle.Target:
    return lifecycle.Target(id=ACME, name="acme", region="eu", state="active", unlisted=unlisted)


# --- fakes -----------------------------------------------------------------------------


class FakeS3:
    """The R2 S3 endpoint: ListObjectsV2 pages of `page` keys, GET and DELETE per object. A missing bucket answers 404."""

    def __init__(self, buckets: dict[str, dict[str, bytes]], page: int = 1000) -> None:
        self.buckets = buckets
        self.page = page
        self.calls: list[tuple[str, str]] = []
        self.fail: set[tuple[str, str]] = set()

    def __call__(self, method: str, path: str) -> tuple[int, bytes]:
        self.calls.append((method, path))
        bucket, _, rest = path.partition("/")
        bucket, _, query = bucket.partition("?")
        if (method, bucket) in self.fail:
            return 500, b"<Error>internal</Error>"
        if bucket not in self.buckets:
            return 404, b"<Error><Code>NoSuchBucket</Code></Error>"
        objects = self.buckets[bucket]
        if method == "GET" and not rest:
            args = urllib.parse.parse_qs(query)
            keys = sorted(objects)
            start = int(args["continuation-token"][0]) if "continuation-token" in args else 0
            chunk = keys[start : start + self.page]
            more = start + self.page < len(keys)
            body = "<ListBucketResult>%s<IsTruncated>%s</IsTruncated>%s</ListBucketResult>" % (
                "".join("<Contents><Key>%s</Key></Contents>" % _xml(k) for k in chunk),
                "true" if more else "false",
                "<NextContinuationToken>%d</NextContinuationToken>" % (start + self.page)
                if more
                else "",
            )
            return 200, body.encode()
        key = urllib.parse.unquote(rest)
        if method == "GET":
            return (200, objects[key]) if key in objects else (404, b"")
        if method == "DELETE":
            objects.pop(key, None)
            return 204, b""
        raise AssertionError("unexpected S3 call %s %s" % (method, path))


def _xml(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


class FakeCloudflare:
    """The Cloudflare API: Workers, D1 databases, R2 buckets and user tokens."""

    def __init__(self, s3: FakeS3) -> None:
        self.s3 = s3
        self.workers = {"proxy-acme", "account-acme", "account-eu"}
        self.d1 = {"account-acme": "1111-uuid", "account-eu": "2222-uuid"}
        self.tokens = [
            {"id": "t-own", "name": "enterprise-%s-backups" % ACME},
            {"id": "t-other", "name": "enterprise-c1123456789abcdef-backups"},
            {"id": "t-mgmt", "name": "auto-rotation-management"},
        ]
        self.calls: list[tuple] = []
        self.fail: set[tuple[str, str]] = set()
        self.token_page = 2
        self.d1_page = 100

    def __call__(self, method, path, _body=None, headers=()):
        self.calls.append((method, path, tuple(headers)))
        for m, fragment in self.fail:
            if m == method and fragment in path:
                return {"success": False, "errors": [{"code": 7003, "message": "boom acme"}]}
        base = "/accounts/%s" % ACCOUNT
        if method == "GET" and path == base + "/workers/scripts":
            return {"success": True, "result": [{"id": w} for w in sorted(self.workers)]}
        if method == "DELETE" and path.startswith(base + "/workers/scripts/"):
            name = path.rsplit("/", 1)[1].split("?")[0]
            assert path.endswith("?force=true")
            self.workers.discard(name)
            return {"success": True, "result": None}
        if method == "GET" and path.startswith(base + "/d1/database?"):
            args = urllib.parse.parse_qs(path.split("?", 1)[1])
            wanted = args["name"][0]
            page = int(args.get("page", ["1"])[0])
            # Cloudflare's name filter is a substring match, so the adapter must check equality.
            rows = [{"uuid": u, "name": n} for n, u in self.d1.items() if wanted in n]
            per = self.d1_page
            pages = max(1, -(-len(rows) // per))
            result = rows[(page - 1) * per : page * per]
            return {"success": True, "result": result, "result_info": {"total_pages": pages}}
        if method == "DELETE" and path.startswith(base + "/d1/database/"):
            uuid = path.rsplit("/", 1)[1]
            self.d1 = {n: u for n, u in self.d1.items() if u != uuid}
            return {"success": True, "result": None}
        if method == "DELETE" and path.startswith(base + "/r2/buckets/"):
            bucket = path.rsplit("/", 1)[1]
            assert not self.s3.buckets.get(bucket), "a bucket is deleted only once empty"
            self.s3.buckets.pop(bucket, None)
            return {"success": True, "result": None}
        if method == "GET" and path.startswith("/user/tokens?"):
            args = urllib.parse.parse_qs(path.split("?", 1)[1])
            page = int(args["page"][0])
            per = self.token_page
            rows = self.tokens[(page - 1) * per : page * per]
            pages = max(1, -(-len(self.tokens) // per))
            return {"success": True, "result": rows, "result_info": {"total_pages": pages}}
        if method == "DELETE" and path.startswith("/user/tokens/"):
            tid = path.rsplit("/", 1)[1]
            self.tokens = [t for t in self.tokens if t["id"] != tid]
            return {"success": True, "result": {"id": tid}}
        raise AssertionError("unexpected Cloudflare call %s %s" % (method, path))


class FakeBws:
    def __init__(self) -> None:
        names = sorted(
            secrets.store_name(ACME, k)
            for k in {*secrets.GENERATED, *secrets.OWNED, *secrets.PAIRS}
        )
        self.rows = [
            {"id": "id-%d" % i, "key": n, "value": SECRET_VALUE, "projectId": PROJECT}
            for i, n in enumerate(names)
        ]
        # The same name in another project is never touched.
        self.rows.append(
            {"id": "id-foreign", "key": names[0], "value": SECRET_VALUE, "projectId": "shared"}
        )
        self.deleted: list[str] = []
        self.listed = 0
        self.rc = 0

    def list_rows(self) -> list[dict]:
        self.listed += 1
        return [dict(r) for r in self.rows]

    def delete(self, secret_id: str) -> int:
        if self.rc:
            return self.rc
        self.deleted.append(secret_id)
        self.rows = [r for r in self.rows if r["id"] != secret_id]
        return 0


class FakeWrangler:
    def __init__(self, dump: str = "CREATE TABLE t (x);\n", rc: int = 0, write: bool = True):
        self.dump = dump
        self.rc = rc
        self.write = write
        self.argvs: list[list[str]] = []

    def __call__(self, argv: list[str]) -> int:
        self.argvs.append(list(argv))
        out = next(a.split("=", 1)[1] for a in argv if a.startswith("--output="))
        if self.write:
            pathlib.Path(out).write_text(self.dump)
        return self.rc


class Rig:
    def __init__(self, monkeypatch, *, domains=(DOMAIN,)) -> None:
        monkeypatch.setenv(enterprise_lookup.PEPPER_ENV, PEPPER)
        self.s3 = FakeS3(
            {
                "configs-acme": {"a/one": b"1", "two & three": b"22"},
                "backups-acme": {"snap": b"333"},
                "configs-globex": {"keep": b"x"},
            }
        )
        self.cf = FakeCloudflare(self.s3)
        self.bws = FakeBws()
        self.kv: list[tuple[list[str], dict]] = []
        self.kv_rc = 0
        self.domains = list(domains)
        self.teardown = la.CloudflareTeardown(
            account_id=ACCOUNT,
            http=self.cf,
            s3=self.s3,
            secrets=la.BwsDeleter(PROJECT, list_rows=self.bws.list_rows, delete=self.bws.delete),
            lookup_domains=lambda _company: self.domains,
            lookup_run=self.kv_run,
            r2_jurisdiction="eu",
        )

    def kv_run(self, argv: list[str], env: dict) -> int:
        self.kv.append((list(argv), env))
        return self.kv_rc


# --- Exporter --------------------------------------------------------------------------


def test_dump_d1_runs_wrangler_export_through_the_pinned_argv_and_returns_the_file():
    fake = FakeWrangler(dump="INSERT INTO t VALUES (1);\n")
    exporter = la.CloudflareExporter(wrangler=fake, s3=FakeS3({}))
    assert exporter.dump_d1(_company()) == "INSERT INTO t VALUES (1);\n"
    (argv,) = fake.argvs
    assert argv[: len(wrangler.ARGV)] == wrangler.ARGV
    assert argv[len(wrangler.ARGV) : len(wrangler.ARGV) + 4] == [
        "d1",
        "export",
        "account-acme",
        "--remote",
    ]
    out = pathlib.Path(argv[-1].split("=", 1)[1])
    assert not out.exists(), "the temporary dump is removed once read"


def test_dump_d1_failure_names_the_company_id_and_withholds_wrangler_output():
    exporter = la.CloudflareExporter(wrangler=FakeWrangler(rc=3), s3=FakeS3({}))
    with pytest.raises(lifecycle.LifecycleError) as caught:
        exporter.dump_d1(_company())
    assert ACME in str(caught.value)
    assert "exited 3" in str(caught.value)
    assert "acme " not in str(caught.value) + " "


def test_dump_d1_refuses_a_success_that_wrote_no_file():
    exporter = la.CloudflareExporter(wrangler=FakeWrangler(write=False), s3=FakeS3({}))
    with pytest.raises(lifecycle.LifecycleError, match="wrote no dump"):
        exporter.dump_d1(_company())


def test_bucket_keys_follows_continuation_tokens_and_unescapes_keys():
    s3 = FakeS3({"configs-acme": {"k%02d" % i: b"" for i in range(5)} | {"a&b": b""}}, page=2)
    exporter = la.CloudflareExporter(wrangler=FakeWrangler(), s3=s3)
    assert exporter.bucket_keys("configs-acme") == sorted(["a&b", *("k%02d" % i for i in range(5))])
    assert len([c for c in s3.calls if c[0] == "GET"]) == 3


@pytest.mark.parametrize("status_bucket", ["nosuchbucket", "broken"])
def test_bucket_keys_refuses_a_missing_or_failing_bucket_without_naming_it(status_bucket):
    s3 = FakeS3({"broken": {}})
    s3.fail.add(("GET", "broken"))
    exporter = la.CloudflareExporter(wrangler=FakeWrangler(), s3=s3)
    with pytest.raises(lifecycle.LifecycleError) as caught:
        exporter.bucket_keys(status_bucket)
    assert status_bucket not in str(caught.value)
    assert "HTTP" in str(caught.value)


def test_get_object_quotes_the_key_and_returns_bytes():
    s3 = FakeS3({"configs-acme": {"dir/a b&c": b"\x00\x01"}})
    exporter = la.CloudflareExporter(wrangler=FakeWrangler(), s3=s3)
    assert exporter.get_object("configs-acme", "dir/a b&c") == b"\x00\x01"
    assert s3.calls[-1] == ("GET", "configs-acme/dir/a%20b%26c")
    with pytest.raises(lifecycle.LifecycleError, match="HTTP 404"):
        exporter.get_object("configs-acme", "gone")


def _control_world(tmp_path, exporter, teardown, store, unlisted=False):
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(registry.migration_sql())
    conn.execute(
        "INSERT INTO companies (id, name, region, state, unlisted, created_at, updated_at) VALUES (?,?,?,?,?,?,?)",
        (ACME, "acme", "eu", "active", 1 if unlisted else 0, NOW, NOW),
    )
    conn.execute(
        "INSERT INTO scope (company_id, subscription_id, renewal_host, max_machines, max_storage_gb, max_expiry_days) "
        "VALUES (?,?,?,?,?,?)",
        (ACME, "sub", "acme.example", 10, 100, 30),
    )
    conn.commit()
    empty: dict[str, Any] = {}

    def query(database, sql, params):
        target = conn if database == "control-eu" else empty.setdefault(database, _empty_db())
        cur = target.execute(sql, params)
        rows = [dict(r) for r in cur.fetchall()] if cur.description else []
        target.commit()
        return rows

    ctx = lifecycle.Context(
        registry=registry.Registry(query),
        query=query,
        exporter=exporter,
        teardown=teardown,
        store=store,
        export_root=tmp_path / "exports",
        now=lambda: NOW,
    )
    return ctx, conn


def _empty_db():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(registry.migration_sql())
    return conn


class MemoryStore:
    def __init__(self) -> None:
        self.values = {
            secrets.store_name(ACME, "ACCOUNT_CONFIG_SERVER_KEY"): SECRET_VALUE,
            secrets.store_name(ACME, "ACCOUNT_BACKUP_STORE_KEK"): "kek",
        }

    def read(self, names):
        return {n: self.values[n] for n in names if n in self.values}

    def create(self, _name, _value):
        raise AssertionError("never written")


def test_export_through_the_adapter_writes_dump_objects_and_a_0600_secrets_file(
    tmp_path, monkeypatch
):
    rig = Rig(monkeypatch)
    exporter = la.CloudflareExporter(wrangler=FakeWrangler(dump="-- dump\n"), s3=rig.s3)
    ctx, _conn = _control_world(tmp_path, exporter, rig.teardown, MemoryStore())
    target = lifecycle.export(ctx, "acme")
    manifest = json.loads((target / lifecycle.MANIFEST).read_text())
    assert manifest["complete"] is True
    assert (target / lifecycle.DUMP).read_text() == "-- dump\n"
    keys = sorted((o["bucket"], o["key"]) for o in manifest["objects"])
    assert keys == [
        ("backups-acme", "snap"),
        ("configs-acme", "a/one"),
        ("configs-acme", "two & three"),
    ]
    mode = stat.S_IMODE((target / lifecycle.SECRETS_FILE).stat().st_mode)
    assert mode == 0o600
    assert (
        json.loads((target / lifecycle.SECRETS_FILE).read_text())["ACCOUNT_CONFIG_SERVER_KEY"]
        == SECRET_VALUE
    )
    assert lifecycle.verify_export(ctx, _company()) == NOW


# --- Teardown, step by step --------------------------------------------------------------


def test_token_name_matches_the_minter():
    company = secrets.Company(id=ACME, name="acme", region="eu", cf_account_id=ACCOUNT)
    assert la.backup_token_name(_company()) == secrets.r2_token_name(company)


def test_undeploy_deletes_proxy_then_account_and_skips_an_absent_worker(monkeypatch):
    rig = Rig(monkeypatch)
    rig.cf.workers.discard("proxy-acme")
    rig.teardown.undeploy(_company())
    deletes = [c[1] for c in rig.cf.calls if c[0] == "DELETE"]
    assert deletes == ["/accounts/%s/workers/scripts/account-acme?force=true" % ACCOUNT]
    assert rig.cf.workers == {"account-eu"}
    assert rig.teardown.done == [
        "undeploy proxy worker (already gone)",
        "undeploy account worker",
    ]


def test_drop_lookup_deletes_the_hmac_key_and_puts_neither_domain_nor_pepper_in_argv(monkeypatch):
    rig = Rig(monkeypatch)
    rig.teardown.drop_lookup(_company())
    ((argv, _env),) = rig.kv
    key = enterprise_lookup.lookup_key(PEPPER, DOMAIN)
    assert argv[:4] == ["kv", "key", "delete", key]
    assert "--namespace-id" in argv
    assert argv[argv.index("--namespace-id") + 1] == enterprise_lookup.NAMESPACE_ID
    assert DOMAIN not in " ".join(argv)
    assert PEPPER not in " ".join(argv)


def test_drop_lookup_refuses_when_no_domain_is_known(monkeypatch):
    rig = Rig(monkeypatch, domains=())
    with pytest.raises(lifecycle.LifecycleError, match="lookup domain of company %s" % ACME):
        rig.teardown.drop_lookup(_company())
    assert rig.kv == []


def test_drop_lookup_refusal_withholds_the_domain(monkeypatch):
    rig = Rig(monkeypatch, domains=("not a domain",))
    with pytest.raises(lifecycle.LifecycleError) as caught:
        rig.teardown.drop_lookup(_company())
    assert "not a domain" not in str(caught.value)
    assert "LookupRefusedError" in str(caught.value)
    assert caught.value.__context__ is None
    assert caught.value.__cause__ is None


def test_drop_lookup_nonzero_wrangler_exit_fails(monkeypatch):
    rig = Rig(monkeypatch)
    rig.kv_rc = 1
    with pytest.raises(lifecycle.LifecycleError, match="exited 1"):
        rig.teardown.drop_lookup(_company())


def test_revoke_tokens_deletes_only_this_companys_backup_token_across_pages(monkeypatch):
    rig = Rig(monkeypatch)
    rig.cf.tokens.insert(0, {"id": "t-pad", "name": "unrelated"})
    rig.teardown.revoke_tokens(_company())
    assert sorted(t["id"] for t in rig.cf.tokens) == ["t-mgmt", "t-other", "t-pad"]
    assert [c[1] for c in rig.cf.calls if c[0] == "DELETE"] == ["/user/tokens/t-own"]


def test_delete_bucket_empties_it_then_deletes_it_with_the_jurisdiction_header(monkeypatch):
    rig = Rig(monkeypatch)
    rig.teardown.delete_bucket(_company(), "configs-acme")
    assert "configs-acme" not in rig.s3.buckets
    assert "configs-globex" in rig.s3.buckets
    s3_deletes = [p for m, p in rig.s3.calls if m == "DELETE"]
    assert s3_deletes == ["configs-acme/a/one", "configs-acme/two%20%26%20three"]
    (call,) = [c for c in rig.cf.calls if c[0] == "DELETE"]
    assert call[1] == "/accounts/%s/r2/buckets/configs-acme" % ACCOUNT
    assert call[2] == ("cf-r2-jurisdiction: eu",)


def test_delete_bucket_refuses_a_bucket_of_another_company(monkeypatch):
    rig = Rig(monkeypatch)
    with pytest.raises(lifecycle.LifecycleError, match="not a bucket of company"):
        rig.teardown.delete_bucket(_company(), "configs-globex")
    assert rig.s3.calls == []


def test_delete_d1_matches_the_exact_name_and_deletes_by_uuid(monkeypatch):
    rig = Rig(monkeypatch)
    rig.cf.d1["account-acme-old"] = "3333-uuid"
    rig.teardown.delete_d1(_company())
    assert rig.cf.d1 == {"account-eu": "2222-uuid", "account-acme-old": "3333-uuid"}
    rig.teardown.delete_d1(_company())
    assert rig.teardown.done[-1] == "delete d1 (already gone)"


def test_delete_d1_pages_through_the_listing_before_deciding(monkeypatch):
    rig = Rig(monkeypatch)
    rig.cf.d1 = {"account-acme-%02d" % i: "u%02d" % i for i in range(3)} | {
        "account-acme": "1111-uuid"
    }
    rig.cf.d1_page = 1
    rig.teardown.delete_d1(_company())
    assert "account-acme" not in rig.cf.d1
    assert len(rig.cf.d1) == 3
    assert rig.teardown.done[-1] == "delete d1"
    pages = [c[1] for c in rig.cf.calls if c[0] == "GET" and "/d1/database?" in c[1]]
    assert len(pages) == 4


def test_delete_secret_deletes_only_rows_in_the_enterprise_project(monkeypatch):
    rig = Rig(monkeypatch)
    name = rig.bws.rows[0]["key"]
    rig.teardown.delete_secret(name)
    assert rig.bws.deleted == ["id-0"]
    assert any(r["id"] == "id-foreign" for r in rig.bws.rows)
    rig.teardown.delete_secret(name)
    assert rig.bws.deleted == ["id-0"]
    assert rig.teardown.done[-1].endswith("(already gone)")


def test_bws_deleter_refuses_a_non_opaque_name_and_an_empty_project():
    bws = FakeBws()
    with pytest.raises(lifecycle.LifecycleError, match="non-opaque"):
        la.BwsDeleter(PROJECT, list_rows=bws.list_rows, delete=bws.delete).delete("ACME_KEY")
    with pytest.raises(lifecycle.LifecycleError, match="project"):
        la.BwsDeleter("", list_rows=bws.list_rows, delete=bws.delete)


def test_bws_delete_failure_is_value_free(monkeypatch):
    rig = Rig(monkeypatch)
    rig.bws.rc = 2
    name = rig.bws.rows[0]["key"]
    with pytest.raises(lifecycle.LifecycleError) as caught:
        rig.teardown.delete_secret(name)
    assert SECRET_VALUE not in str(caught.value)
    assert "exited 2" in str(caught.value)


def test_a_seam_exception_keeps_only_its_type_and_chains_nothing(monkeypatch):
    rig = Rig(monkeypatch)

    def boom(*_a, **_k):
        raise ValueError(SECRET_VALUE)

    rig.teardown._http = boom
    with pytest.raises(lifecycle.LifecycleError) as caught:
        rig.teardown.undeploy(_company())
    assert SECRET_VALUE not in str(caught.value)
    assert "ValueError" in str(caught.value)
    assert caught.value.__context__ is None
    assert caught.value.__cause__ is None


def test_a_cloudflare_refusal_reports_codes_not_its_text(monkeypatch):
    rig = Rig(monkeypatch)
    rig.cf.fail.add(("DELETE", "/workers/scripts/proxy-acme"))
    with pytest.raises(lifecycle.LifecycleError) as caught:
        rig.teardown.undeploy(_company())
    assert "7003" in str(caught.value)
    assert "boom" not in str(caught.value)
    assert "acme" not in str(caught.value).replace(ACME, "")


# --- Teardown under remove: a midway failure stops the rest and a rerun resumes ----------


def _remove_ctx(tmp_path, rig, unlisted=False):
    exporter = la.CloudflareExporter(wrangler=FakeWrangler(), s3=rig.s3)
    ctx, conn = _control_world(tmp_path, exporter, rig.teardown, MemoryStore(), unlisted)
    lifecycle.export(ctx, "acme")
    return ctx, conn


def _state(conn) -> str:
    return conn.execute("SELECT state FROM companies WHERE id=?", (ACME,)).fetchone()[0]


def test_full_remove_with_delete_data_tears_down_everything(tmp_path, monkeypatch):
    rig = Rig(monkeypatch)
    ctx, conn = _remove_ctx(tmp_path, rig)
    result = lifecycle.remove(ctx, "acme", delete_data=True, confirm="acme")
    assert result.data_deleted
    assert rig.cf.workers == {"account-eu"}
    assert rig.cf.d1 == {"account-eu": "2222-uuid"}
    assert set(rig.s3.buckets) == {"configs-globex"}
    assert sorted(t["id"] for t in rig.cf.tokens) == ["t-mgmt", "t-other"]
    assert [r["id"] for r in rig.bws.rows] == ["id-foreign"]
    assert len(rig.kv) == 1
    assert _state(conn) == "removed"
    assert rig.teardown.done[:3] == [
        "undeploy proxy worker",
        "undeploy account worker",
        "drop lookup",
    ]


def test_remove_without_delete_data_keeps_d1_buckets_tokens_and_secrets(tmp_path, monkeypatch):
    rig = Rig(monkeypatch)
    ctx, _conn = _remove_ctx(tmp_path, rig)
    lifecycle.remove(ctx, "acme", delete_data=False)
    assert "account-acme" in rig.cf.d1
    assert "configs-acme" in rig.s3.buckets
    assert any(t["id"] == "t-own" for t in rig.cf.tokens)
    assert rig.bws.deleted == []


def test_unlisted_company_never_touches_the_lookup(tmp_path, monkeypatch):
    rig = Rig(monkeypatch, domains=())
    ctx, _conn = _remove_ctx(tmp_path, rig, unlisted=True)
    lifecycle.remove(ctx, "acme", delete_data=False)
    assert rig.kv == []


def test_a_failing_step_stops_the_rest_names_what_ran_and_a_rerun_resumes(tmp_path, monkeypatch):
    rig = Rig(monkeypatch)
    ctx, conn = _remove_ctx(tmp_path, rig)
    rig.cf.fail.add(("DELETE", "/d1/database/"))
    with pytest.raises(lifecycle.LifecycleError) as caught:
        lifecycle.remove(ctx, "acme", delete_data=True, confirm="acme")
    message = str(caught.value)
    assert "delete d1 failed" in message
    for done in (
        "undeploy proxy worker",
        "undeploy account worker",
        "drop lookup",
        "revoke backup token",
        "delete configs bucket",
        "delete backups bucket",
    ):
        assert done in message
    assert "rerun" in message
    # Nothing after the failed step ran, and the company is not marked removed.
    assert rig.bws.deleted == []
    assert "account-acme" in rig.cf.d1
    assert _state(conn) == "active"

    rig.cf.fail.clear()
    rig2 = la.CloudflareTeardown(
        account_id=ACCOUNT,
        http=rig.cf,
        s3=rig.s3,
        secrets=la.BwsDeleter(PROJECT, list_rows=rig.bws.list_rows, delete=rig.bws.delete),
        lookup_domains=lambda _c: [DOMAIN],
        lookup_run=rig.kv_run,
        r2_jurisdiction="eu",
    )
    ctx.teardown = rig2
    before = len(rig.cf.calls)
    lifecycle.remove(ctx, "acme", delete_data=True, confirm="acme")
    assert _state(conn) == "removed"
    assert rig2.done[:2] == [
        "undeploy proxy worker (already gone)",
        "undeploy account worker (already gone)",
    ]
    assert "revoke backup token (already gone)" in rig2.done
    assert "delete configs bucket (already gone)" in rig2.done
    assert "delete d1" in rig2.done
    deletes = [c[1] for c in rig.cf.calls[before:] if c[0] == "DELETE"]
    assert deletes == ["/accounts/%s/d1/database/1111-uuid" % ACCOUNT]
    assert [r["id"] for r in rig.bws.rows] == ["id-foreign"]


def test_a_failing_bucket_step_stops_before_d1_and_secrets(tmp_path, monkeypatch):
    rig = Rig(monkeypatch)
    ctx, _conn = _remove_ctx(tmp_path, rig)
    rig.s3.fail.add(("GET", "backups-acme"))
    with pytest.raises(lifecycle.LifecycleError) as caught:
        lifecycle.remove(ctx, "acme", delete_data=True, confirm="acme")
    assert "delete backups bucket failed" in str(caught.value)
    assert "delete configs bucket" in str(caught.value)
    assert "backups-acme" not in str(caught.value)
    assert "account-acme" in rig.cf.d1
    assert rig.bws.deleted == []


# --- live transports, with their runners injected ---------------------------------------


def test_r2_s3_puts_credentials_on_stdin_and_splits_status_from_a_binary_body():
    seen = {}

    def runner(argv, **kw):
        seen["argv"] = argv
        seen["input"] = kw["input"]
        return subprocess.CompletedProcess(argv, 0, stdout=b"\x00\xff\n200", stderr=b"")

    s3 = la.r2_s3("https://acct.eu.r2.cloudflarestorage.com", "KEYID", SECRET_VALUE, runner=runner)
    assert s3("GET", "configs-acme/x") == (200, b"\x00\xff")
    assert SECRET_VALUE not in " ".join(seen["argv"])
    assert "KEYID" not in " ".join(seen["argv"])
    assert SECRET_VALUE.encode() in seen["input"]
    assert seen["argv"][-1] == "https://acct.eu.r2.cloudflarestorage.com/configs-acme/x"


def test_r2_s3_escapes_quote_and_backslash_in_the_config_line_and_refuses_a_newline():
    seen = {}

    def runner(argv, **kw):
        seen["input"] = kw["input"]
        return subprocess.CompletedProcess(argv, 0, stdout=b"\n200", stderr=b"")

    s3 = la.r2_s3("https://e", 'k"id', "s\\e", runner=runner)
    s3("GET", "b")
    assert seen["input"] == b'user = "k\\"id:s\\\\e"\n'
    with pytest.raises(lifecycle.LifecycleError, match="line break"):
        la.r2_s3("https://e", "k", "s\nuser = x", runner=runner)


def test_r2_s3_curl_failure_withholds_stderr():
    def runner(argv, **_kw):
        return subprocess.CompletedProcess(argv, 6, stdout=b"", stderr=b"host acme leaked")

    s3 = la.r2_s3("https://e", "k", "s", runner=runner)
    with pytest.raises(lifecycle.LifecycleError) as caught:
        s3("GET", "b")
    assert "acme" not in str(caught.value)
    assert "curl exit 6" in str(caught.value)


def test_r2_s3_from_env_refuses_missing_credentials():
    with pytest.raises(lifecycle.LifecycleError, match="CLOUDFLARE_R2_SECRET_ACCESS_KEY"):
        la.r2_s3_from_env("https://e", {"CLOUDFLARE_R2_ACCESS_KEY_ID": "k"})


def test_live_wrangler_captures_output_and_runs_in_the_worker_dir(tmp_path):
    seen: dict[str, Any] = {}

    def runner(argv, **kw):
        seen.update(kw, argv=argv)
        return subprocess.CompletedProcess(
            argv, 0, stdout="url r2.cloudflarestorage.com", stderr=""
        )

    run = la.live_wrangler(tmp_path, {"PATH": ""}, runner=runner, require=lambda *_a: None)
    assert run([*wrangler.ARGV, "d1", "export"]) == 0
    assert seen["cwd"] == tmp_path
    assert seen["capture_output"] is True


def test_cloudflare_http_failure_withholds_the_path(monkeypatch):
    def broken(*_a, **_k):
        raise cf_auth.CfAuthError(
            "GET /accounts/x/workers/scripts/account-acme did not return JSON"
        )

    monkeypatch.setattr(cf_auth, "curl_json", broken)
    http = la.cloudflare_http(["-H", "Authorization: Bearer t"])
    with pytest.raises(lifecycle.LifecycleError) as caught:
        http("GET", "/accounts/x/workers/scripts/account-acme")
    assert "acme" not in str(caught.value)
    assert caught.value.__context__ is None
