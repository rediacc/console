"""enterprise.lifecycle: list, update, suspend, export and remove, driven over in-memory control databases and recording fakes.

Remove is the destructive verb, so its refusals are each driven in both directions: the refusal must fire on the plant, and the twin that satisfies every rule must go through.
"""

from __future__ import annotations

import json
import sqlite3

import pytest

from rediacc_ci.enterprise import lifecycle, registry, secrets

NOW = "2026-11-09T10:00:00Z"
ACME = "c0123456789abcdef"
GLOBEX = "c1123456789abcdef"
REGIONS = ("eu", "us", "asia")


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(registry.migration_sql())
    return conn


def _add(conn, cid, name, region, state="active", machines=10, storage=100):
    conn.execute(
        "INSERT INTO companies (id, name, region, state, created_at, updated_at) VALUES (?,?,?,?,?,?)",
        (cid, name, region, state, NOW, NOW),
    )
    conn.execute(
        "INSERT INTO scope (company_id, subscription_id, renewal_host, max_machines, max_storage_gb, max_expiry_days) "
        "VALUES (?,?,?,?,?,?)",
        (cid, "sub_" + cid, "%s.example" % name, machines, storage, 30),
    )
    conn.commit()


class World:
    def __init__(self, tmp_path, env=None, down=()):
        self.dbs = {"control-%s" % r: _db() for r in REGIONS}
        _add(self.dbs["control-eu"], ACME, "acme", "eu")
        _add(self.dbs["control-us"], GLOBEX, "globex", "us", state="suspended")
        self.down = set(down)
        self.calls: list[tuple] = []
        self.secrets = {
            secrets.store_name(ACME, "ACCOUNT_CONFIG_SERVER_KEY"): "layer3-key",
            secrets.store_name(ACME, "ACCOUNT_BACKUP_STORE_KEK"): "kek",
        }
        self.buckets = {
            "configs-acme": {"a/one": b"1", "two": b"22"},
            "backups-acme": {"snap": b"333"},
        }
        self.out: list[str] = []
        self.ctx = lifecycle.Context(
            registry=registry.Registry(self.query),
            query=self.query,
            exporter=self,
            teardown=self,
            store=self,
            export_root=tmp_path / "exports",
            env=env or {},
            now=lambda: NOW,
            actor="op",
        )

    # control transport
    def query(self, database, sql, params):
        if database in self.down:
            raise ConnectionError("no route")
        conn = self.dbs[database]
        cur = conn.execute(sql, params)
        rows = [dict(r) for r in cur.fetchall()] if cur.description else []
        conn.commit()
        return rows

    # Store
    def read(self, names):
        return {n: self.secrets[n] for n in names if n in self.secrets}

    def create(self, _name, _value):
        raise AssertionError("lifecycle never writes secrets")

    # Exporter
    def dump_d1(self, company):
        self.calls.append(("dump_d1", company.id))
        return "-- dump of %s\n" % company.id

    def bucket_keys(self, bucket):
        return sorted(self.buckets[bucket])

    def get_object(self, bucket, key):
        return self.buckets[bucket][key]

    # Teardown
    def undeploy(self, company):
        self.calls.append(("undeploy", company.id))

    def delete_d1(self, company):
        self.calls.append(("delete_d1", company.id))

    def delete_bucket(self, _company, bucket):
        self.calls.append(("delete_bucket", bucket))

    def delete_secret(self, name):
        self.calls.append(("delete_secret", name))
        self.secrets.pop(name, None)

    def revoke_tokens(self, company):
        self.calls.append(("revoke_tokens", company.id))

    def drop_lookup(self, company):
        self.calls.append(("drop_lookup", company.id))

    def scope(self, region, cid):
        row = (
            self.dbs["control-" + region]
            .execute("SELECT * FROM scope WHERE company_id=?", (cid,))
            .fetchone()
        )
        return dict(row)

    def state(self, region, cid):
        return (
            self.dbs["control-" + region]
            .execute("SELECT state FROM companies WHERE id=?", (cid,))
            .fetchone()[0]
        )

    def audit(self, region):
        return [
            dict(r)
            for r in self.dbs["control-" + region].execute("SELECT * FROM audit ORDER BY id")
        ]

    def mutating(self):
        return [c for c in self.calls if c[0] != "dump_d1"]


@pytest.fixture
def w(tmp_path):
    return World(tmp_path)


# --- list --------------------------------------------------------------------------


def test_list_reads_every_region(w):
    rows = lifecycle.list_companies(w.ctx)
    assert [(r["name"], r["region"], r["state"]) for r in rows] == [
        ("acme", "eu", "active"),
        ("globex", "us", "suspended"),
    ]
    assert rows[0]["max_machines"] == 10
    assert rows[0]["max_storage_gb"] == 100


def test_list_hides_removed_unless_asked(w):
    w.dbs["control-eu"].execute("UPDATE companies SET state='removed'")
    assert [r["name"] for r in lifecycle.list_companies(w.ctx)] == ["globex"]
    assert [r["name"] for r in lifecycle.list_companies(w.ctx, include_removed=True)] == [
        "acme",
        "globex",
    ]


def test_list_names_an_unreachable_region_and_cmd_exits_1(tmp_path):
    w = World(tmp_path, down={"control-asia"})
    with pytest.raises(registry.RegistryUnreachableError) as exc:
        lifecycle.list_companies(w.ctx)
    assert exc.value.regions == ["asia"]
    rc = lifecycle.cmd_list(w.ctx, out=w.out.append)
    assert rc == 1
    assert any("asia" in line for line in w.out)


def test_cmd_list_prints_one_line_per_company(w):
    assert lifecycle.cmd_list(w.ctx, out=w.out.append) == 0
    text = "\n".join(w.out)
    assert "acme" in text
    assert "globex" in text
    assert "suspended" in text


def test_list_refuses_under_github_actions(tmp_path):
    w = World(tmp_path, env={"GITHUB_ACTIONS": "true"})
    assert lifecycle.cmd_list(w.ctx, out=w.out.append) == 1
    assert "acme" not in "\n".join(w.out)


# --- suspend -----------------------------------------------------------------------


def test_suspend_sets_state_and_audits(w):
    lifecycle.suspend(w.ctx, "acme")
    assert w.state("eu", ACME) == "suspended"
    assert [(a["action"], a["company_id"], a["actor"]) for a in w.audit("eu")] == [
        ("suspend", ACME, "op")
    ]


def test_resume_reverses_suspend(w):
    lifecycle.suspend(w.ctx, "globex", resume=True)
    assert w.state("us", GLOBEX) == "active"
    assert w.audit("us")[0]["action"] == "resume"


def test_suspend_is_idempotent(w):
    lifecycle.suspend(w.ctx, "globex")
    assert w.state("us", GLOBEX) == "suspended"


def test_suspend_refuses_an_onboarding_company(w):
    w.dbs["control-eu"].execute("UPDATE companies SET state='onboarding'")
    with pytest.raises(lifecycle.LifecycleError, match="onboarding"):
        lifecycle.suspend(w.ctx, "acme")


def test_suspend_refuses_a_removed_company(w):
    w.dbs["control-eu"].execute("UPDATE companies SET state='removed'")
    with pytest.raises(lifecycle.LifecycleError, match="no company"):
        lifecycle.suspend(w.ctx, "acme")


def test_unknown_company_is_refused(w):
    with pytest.raises(lifecycle.LifecycleError, match="no company"):
        lifecycle.suspend(w.ctx, "nobody")


def test_suspend_with_a_region_down_refuses_rather_than_guess(tmp_path):
    w = World(tmp_path, down={"control-us"})
    with pytest.raises(registry.RegistryUnreachableError):
        lifecycle.suspend(w.ctx, "acme")
    assert w.state("eu", ACME) == "active"


# --- update ------------------------------------------------------------------------


def test_update_changes_only_the_named_limits(w):
    lifecycle.update(w.ctx, "acme", max_machines=50, max_storage_gb=500)
    s = w.scope("eu", ACME)
    assert (s["max_machines"], s["max_storage_gb"], s["max_expiry_days"]) == (50, 500, 30)
    assert w.audit("eu")[0]["action"] == "update"
    assert json.loads(w.audit("eu")[0]["detail"]) == {"max_machines": 50, "max_storage_gb": 500}


def test_update_allow_ips_is_validated_and_stored(w):
    result = lifecycle.update(w.ctx, "acme", allow_ips=("10.0.0.0/8", "203.0.113.7"))
    assert json.loads(w.scope("eu", ACME)["allow_ips"]) == ["10.0.0.0/8", "203.0.113.7"]
    assert result.redeploy_needed is True
    with pytest.raises(lifecycle.LifecycleError, match="ALLOW_IPS"):
        lifecycle.update(w.ctx, "acme", allow_ips=("not-an-ip",))
    assert json.loads(w.scope("eu", ACME)["allow_ips"]) == ["10.0.0.0/8", "203.0.113.7"]


def test_update_limits_need_no_redeploy(w):
    assert lifecycle.update(w.ctx, "acme", max_machines=11).redeploy_needed is False


@pytest.mark.parametrize(
    "kw",
    [{"max_machines": 0}, {"max_storage_gb": -1}, {"max_expiry_days": 0}, {"max_machines": True}],
)
def test_update_refuses_out_of_range_limits(w, kw):
    with pytest.raises(lifecycle.LifecycleError):
        lifecycle.update(w.ctx, "acme", **kw)
    assert w.scope("eu", ACME)["max_machines"] == 10
    assert w.audit("eu") == []


def test_update_with_nothing_to_change_is_refused(w):
    with pytest.raises(lifecycle.LifecycleError, match="nothing to update"):
        lifecycle.update(w.ctx, "acme")


def test_update_ring_override_set_and_cleared(w):
    lifecycle.update(w.ctx, "acme", ring="canary", ring_reason="first customer")
    row = w.dbs["control-eu"].execute("SELECT ring, reason FROM ring_override").fetchone()
    assert tuple(row) == ("canary", "first customer")
    lifecycle.update(w.ctx, "acme", ring="auto")
    assert w.dbs["control-eu"].execute("SELECT COUNT(*) FROM ring_override").fetchone()[0] == 0


def test_update_ring_needs_a_reason_and_a_known_ring(w):
    with pytest.raises(lifecycle.LifecycleError, match="reason"):
        lifecycle.update(w.ctx, "acme", ring="small")
    with pytest.raises(lifecycle.LifecycleError, match="ring"):
        lifecycle.update(w.ctx, "acme", ring="huge", ring_reason="x")


def test_update_refuses_a_removed_company(w):
    w.dbs["control-eu"].execute("UPDATE companies SET state='removed'")
    with pytest.raises(lifecycle.LifecycleError, match="no company"):
        lifecycle.update(w.ctx, "acme", max_machines=2)


# --- export ------------------------------------------------------------------------


def test_export_writes_dump_objects_and_a_verified_manifest_last(w):
    path = lifecycle.export(w.ctx, "acme")
    assert path == w.ctx.export_root / ACME
    manifest = json.loads((path / "manifest.json").read_text())
    assert manifest["complete"] is True
    assert manifest["company_id"] == ACME
    assert (path / "d1.sql").read_text() == "-- dump of %s\n" % ACME
    objs = manifest["objects"]
    assert sorted(o["key"] for o in objs) == ["a/one", "snap", "two"]
    assert {o["bucket"] for o in objs} == {"configs-acme", "backups-acme"}
    for o in objs:
        assert (path / o["file"]).read_bytes() == w.buckets[o["bucket"]][o["key"]]
    company = lifecycle.load_company(w.ctx, "acme")
    assert lifecycle.verify_export(w.ctx, company) == manifest["exported_at"]


def test_export_carries_durable_secrets_at_mode_0600_and_names_only_in_manifest(w):
    path = lifecycle.export(w.ctx, "acme")
    sec = path / "secrets.json"
    assert json.loads(sec.read_text()) == {
        "ACCOUNT_CONFIG_SERVER_KEY": "layer3-key",
        "ACCOUNT_BACKUP_STORE_KEK": "kek",
    }
    assert (sec.stat().st_mode & 0o777) == 0o600
    assert "layer3-key" not in (path / "manifest.json").read_text()


def test_export_failure_leaves_no_complete_manifest(w):
    def boom(_bucket, _key):
        raise OSError("r2 down")

    w.get_object = boom
    with pytest.raises(lifecycle.LifecycleError, match="export failed"):
        lifecycle.export(w.ctx, "acme")
    assert not (w.ctx.export_root / ACME / "manifest.json").exists()


def test_a_failed_reexport_removes_the_older_manifest(w):
    lifecycle.export(w.ctx, "acme")

    def boom(_bucket, _key):
        raise OSError("r2 down")

    w.get_object = boom
    with pytest.raises(lifecycle.LifecycleError):
        lifecycle.export(w.ctx, "acme")
    assert not (w.ctx.export_root / ACME / "manifest.json").exists()


def test_export_refuses_under_github_actions(tmp_path):
    w = World(tmp_path, env={"GITHUB_ACTIONS": "true"})
    with pytest.raises(lifecycle.LifecycleError, match="GITHUB_ACTIONS"):
        lifecycle.export(w.ctx, "acme")
    assert w.calls == []


# --- remove ------------------------------------------------------------------------


def _exported(w, name="acme"):
    lifecycle.export(w.ctx, name)


def test_remove_refuses_without_an_export(w):
    with pytest.raises(lifecycle.LifecycleError, match="export"):
        lifecycle.remove(w.ctx, "acme", delete_data=True, confirm="acme")
    assert w.mutating() == []
    assert w.state("eu", ACME) == "active"


def test_remove_refuses_an_incomplete_export(w):
    _exported(w)
    p = w.ctx.export_root / ACME / "manifest.json"
    m = json.loads(p.read_text())
    m["complete"] = False
    p.write_text(json.dumps(m))
    with pytest.raises(lifecycle.LifecycleError, match="export"):
        lifecycle.remove(w.ctx, "acme", delete_data=True, confirm="acme")
    assert w.mutating() == []


def test_remove_refuses_an_export_whose_file_changed(w):
    _exported(w)
    (w.ctx.export_root / ACME / "d1.sql").write_text("tampered")
    with pytest.raises(lifecycle.LifecycleError, match=r"d1\.sql"):
        lifecycle.remove(w.ctx, "acme", delete_data=True, confirm="acme")
    assert w.mutating() == []


def test_remove_refuses_an_export_missing_a_file(w):
    _exported(w)
    (w.ctx.export_root / ACME / "d1.sql").unlink()
    with pytest.raises(lifecycle.LifecycleError, match=r"d1\.sql"):
        lifecycle.remove(w.ctx, "acme", delete_data=False)
    assert w.mutating() == []


def test_remove_refuses_another_companys_export(w):
    _exported(w)
    p = w.ctx.export_root / ACME / "manifest.json"
    m = json.loads(p.read_text())
    m["company_id"] = GLOBEX
    p.write_text(json.dumps(m))
    with pytest.raises(lifecycle.LifecycleError, match="export"):
        lifecycle.remove(w.ctx, "acme", delete_data=False)
    assert w.mutating() == []


@pytest.mark.parametrize("confirm", [None, "", "ACME", "acm", "globex"])
def test_delete_data_needs_the_exact_company_name(w, confirm):
    _exported(w)
    with pytest.raises(lifecycle.LifecycleError, match="--confirm"):
        lifecycle.remove(w.ctx, "acme", delete_data=True, confirm=confirm)
    assert w.mutating() == []
    assert w.state("eu", ACME) == "active"


@pytest.mark.parametrize("value", ["true", "1", "x"])
def test_remove_refuses_under_github_actions(tmp_path, value):
    w = World(tmp_path)
    _exported(w)
    w.ctx.env = {"GITHUB_ACTIONS": value}
    with pytest.raises(lifecycle.LifecycleError, match="GITHUB_ACTIONS"):
        lifecycle.remove(w.ctx, "acme", delete_data=True, confirm="acme")
    assert w.mutating() == []
    assert w.state("eu", ACME) == "active"


def test_remove_twin_runs_when_github_actions_is_empty(tmp_path):
    w = World(tmp_path)
    _exported(w)
    w.ctx.env = {"GITHUB_ACTIONS": ""}
    lifecycle.remove(w.ctx, "acme", delete_data=False)
    assert w.state("eu", ACME) == "removed"


def test_remove_without_delete_data_keeps_every_byte(w):
    _exported(w)
    result = lifecycle.remove(w.ctx, "acme", delete_data=False)
    assert result.data_deleted is False
    assert w.mutating() == [("undeploy", ACME), ("drop_lookup", ACME)]
    assert w.state("eu", ACME) == "removed"
    assert w.audit("eu")[-1]["action"] == "remove"
    assert len(w.secrets) == 2


def test_remove_with_delete_data_deletes_everything_after_undeploy(w):
    _exported(w)
    result = lifecycle.remove(w.ctx, "acme", delete_data=True, confirm="acme")
    assert result.data_deleted is True
    assert w.mutating()[0] == ("undeploy", ACME)
    assert ("delete_d1", ACME) in w.calls
    assert ("revoke_tokens", ACME) in w.calls
    assert {c[1] for c in w.calls if c[0] == "delete_bucket"} == {"configs-acme", "backups-acme"}
    assert w.secrets == {}
    assert w.state("eu", ACME) == "removed"
    assert json.loads(w.audit("eu")[-1]["detail"])["data_deleted"] is True


def test_delete_data_refuses_a_database_that_changed_since_the_export(w):
    _exported(w)
    w.dump_d1 = lambda _company: "-- a row written after the export\n"
    with pytest.raises(lifecycle.LifecycleError, match=r"database of company .* changed since"):
        lifecycle.remove(w.ctx, "acme", delete_data=True, confirm="acme")
    assert w.mutating() == []
    assert w.state("eu", ACME) == "active"


def test_delete_data_refuses_a_bucket_listing_that_changed_since_the_export(w):
    _exported(w)
    w.buckets["configs-acme"]["new"] = b"added after the export"
    with pytest.raises(lifecycle.LifecycleError, match=r"buckets of company .* changed since"):
        lifecycle.remove(w.ctx, "acme", delete_data=True, confirm="acme")
    assert w.mutating() == []


def test_a_stale_export_is_harmless_without_delete_data(w):
    _exported(w)
    w.dump_d1 = lambda _company: "-- changed\n"
    lifecycle.remove(w.ctx, "acme", delete_data=False)
    assert w.state("eu", ACME) == "removed"


def test_a_resumed_delete_data_remove_is_not_judged_against_its_own_deletions(w):
    _exported(w)

    def boom(_company):
        raise OSError("d1 refused")

    ok = w.delete_d1
    w.delete_d1 = boom
    with pytest.raises(lifecycle.LifecycleError, match="delete d1"):
        lifecycle.remove(w.ctx, "acme", delete_data=True, confirm="acme")
    w.delete_d1 = ok
    w.buckets.clear()  # the first run already emptied and deleted them
    w.dump_d1 = lambda _company: "-- gone\n"
    w.bucket_keys = lambda _bucket: []
    lifecycle.remove(w.ctx, "acme", delete_data=True, confirm="acme")
    assert w.state("eu", ACME) == "removed"


def test_a_remove_that_fails_before_deleting_data_leaves_no_mark_and_rechecks(w):
    """Review e2c4a3a7.1: a failure before the first bucket deletion (here the undeploy) writes no mark, so a later change to the company is caught on the rerun."""
    _exported(w)

    def boom(_company):
        raise OSError("undeploy refused")

    ok = w.undeploy
    w.undeploy = boom
    with pytest.raises(lifecycle.LifecycleError, match="undeploy"):
        lifecycle.remove(w.ctx, "acme", delete_data=True, confirm="acme")
    assert not (w.ctx.export_root / ACME / lifecycle.CHECKED).exists()
    w.undeploy = ok
    w.dump_d1 = lambda _company: "-- a row written after the failed run\n"
    with pytest.raises(lifecycle.LifecycleError, match=r"database of company .* changed since"):
        lifecycle.remove(w.ctx, "acme", delete_data=True, confirm="acme")
    assert ("delete_d1", ACME) not in w.calls


def test_a_reexport_clears_the_stale_check_mark(w):
    _exported(w)

    def boom(_company):
        raise OSError("d1 refused")

    w.delete_d1 = boom
    with pytest.raises(lifecycle.LifecycleError, match="delete d1"):
        lifecycle.remove(w.ctx, "acme", delete_data=True, confirm="acme")
    folder = w.ctx.export_root / ACME
    assert (folder / lifecycle.CHECKED).exists()
    lifecycle.export(w.ctx, "acme")
    assert not (folder / lifecycle.CHECKED).exists()


def test_export_files_are_owner_only(w):
    path = lifecycle.export(w.ctx, "acme")
    for f in (path / "d1.sql", path / "manifest.json", *path.glob("objects/*/*")):
        assert (f.stat().st_mode & 0o777) == 0o600, f
    for d in (path, path / "objects", *path.glob("objects/*")):
        assert (d.stat().st_mode & 0o777) == 0o700, d


def test_an_os_error_while_writing_the_export_is_a_lifecycle_error_naming_only_its_type(w):
    w.ctx.export_root.write_text("a file where the export directory should be")
    with pytest.raises(lifecycle.LifecycleError) as caught:
        lifecycle.export(w.ctx, "acme")
    assert str(caught.value) == "export failed: NotADirectoryError"
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None


@pytest.mark.parametrize("drop", ["secrets", "object-file"])
def test_remove_refuses_a_manifest_missing_the_secrets_file_or_an_object_hash(w, drop):
    _exported(w)
    p = w.ctx.export_root / ACME / "manifest.json"
    m = json.loads(p.read_text())
    if drop == "secrets":
        del m["files"]["secrets.json"]
    else:
        del m["files"][m["objects"][0]["file"]]
    p.write_text(json.dumps(m))
    with pytest.raises(lifecycle.LifecycleError, match="export manifest"):
        lifecycle.remove(w.ctx, "acme", delete_data=False)
    assert w.mutating() == []


def test_a_failed_audit_write_leaves_the_state_untouched_and_the_remove_repeatable(w):
    _exported(w)
    orig = w.query

    def spy(database, sql, params):
        if "INSERT INTO audit" in sql:
            raise OSError("d1 down")
        return orig(database, sql, params)

    w.ctx.query = spy
    with pytest.raises(OSError, match="d1 down"):
        lifecycle.remove(w.ctx, "acme", delete_data=False)
    assert w.state("eu", ACME) == "active"
    w.ctx.query = orig
    lifecycle.remove(w.ctx, "acme", delete_data=False)
    assert w.state("eu", ACME) == "removed"


def test_delete_data_secret_names_cover_every_owned_key_and_pair(w):
    _exported(w)
    lifecycle.remove(w.ctx, "acme", delete_data=True, confirm="acme")
    deleted = {c[1] for c in w.calls if c[0] == "delete_secret"}
    for key in (*secrets.GENERATED, *secrets.PAIRS):
        assert secrets.store_name(ACME, key) in deleted


def test_a_failed_step_stops_before_the_control_row_changes(w):
    _exported(w)

    def boom(_company, _bucket):
        raise OSError("r2 refused")

    w.delete_bucket = boom
    with pytest.raises(lifecycle.LifecycleError, match="delete bucket"):
        lifecycle.remove(w.ctx, "acme", delete_data=True, confirm="acme")
    assert w.state("eu", ACME) == "active"


def test_remove_audit_is_written_after_the_last_destructive_step(w):
    _exported(w)
    order = []
    w.delete_secret = lambda _name: order.append("secret")
    orig = w.query

    def spy(database, sql, params):
        if "INSERT INTO audit" in sql:
            order.append("audit")
        return orig(database, sql, params)

    w.ctx.query = spy
    lifecycle.remove(w.ctx, "acme", delete_data=True, confirm="acme")
    assert order[-1] == "audit"
    assert "secret" in order


def test_remove_a_company_not_found_is_refused(w):
    with pytest.raises(lifecycle.LifecycleError, match="no company"):
        lifecycle.remove(w.ctx, "nobody", delete_data=False)


def test_remove_needs_every_region_readable(tmp_path):
    w = World(tmp_path, down={"control-asia"})
    with pytest.raises(registry.RegistryUnreachableError):
        lifecycle.remove(w.ctx, "acme", delete_data=False)
    assert w.mutating() == []


# --- command wrappers ----------------------------------------------------------------


def test_cmd_remove_returns_1_on_a_refusal_and_prints_the_reason(w):
    rc = lifecycle.cmd_remove(w.ctx, "acme", delete_data=True, confirm="acme", out=w.out.append)
    assert rc == 1
    assert any("export" in line for line in w.out)


def test_cmd_remove_returns_0_on_success(w):
    _exported(w)
    assert (
        lifecycle.cmd_remove(w.ctx, "acme", delete_data=False, confirm=None, out=w.out.append) == 0
    )


def test_cmd_wrappers_map_errors_to_rc_1(w):
    assert lifecycle.cmd_suspend(w.ctx, "nobody", out=w.out.append) == 1
    assert lifecycle.cmd_update(w.ctx, "acme", out=w.out.append) == 1
    assert lifecycle.cmd_export(w.ctx, "nobody", out=w.out.append) == 1
    assert lifecycle.cmd_suspend(w.ctx, "acme", out=w.out.append) == 0
    assert lifecycle.cmd_export(w.ctx, "acme", out=w.out.append) == 0
