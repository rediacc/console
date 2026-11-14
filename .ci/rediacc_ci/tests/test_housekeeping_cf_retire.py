"""`rediacc_ci.housekeeping.cf_retire` against a fake Cloudflare account (no network, no credentials)."""

from __future__ import annotations

import json
import urllib.parse

import pytest

from rediacc_ci import paths
from rediacc_ci.housekeeping import cf_leftovers as cfl
from rediacc_ci.housekeeping import cf_retire as cr

ROOT = paths.repo_root()
ASKED = "ASKED:2026-11-13T10:07Z"

PLAN = """# PLAN-product-domain-rename: fixture

## Names

| Thing | Before | After |
|---|---|---|
| Account Worker | `edge-rediacc-account-<r>`, `rediacc-account-<r>` | `account-<r>` |
| Proxy Worker | `rediacc-proxy-<r>` | `proxy-<r>` |
| D1 | `account-db-<r>`, `account-db-bench` | `account-<r>` |
| Config bucket | `rediacc-configs-<r>`, `-bench` | `configs-<r>` |

Unprefixed workflows gain `ops-`. Unchanged: `rediacc-account-server` and `rediacc-proxy-executor`.

## Tasks

- [ ] L11 [live] delete the old Workers and the Pages project `oldsite`.
"""

TERMS = {
    "terms": [
        {
            "id": "rediacc-backups-probe",
            "pattern": "(?<![A-Za-z0-9-])rediacc-backups-probe(?![A-Za-z0-9_-])",
            "case_sensitive": True,
        }
    ]
}

WRANGLER = """name = "account-eu"
[[r2_buckets]]
binding = "PUBLIC"
bucket_name = "public-data"
[[queues.producers]]
binding = "Q"
queue = "backup-replicate-eu"
"""


@pytest.fixture(autouse=True)
def _account(monkeypatch):
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "acct")


@pytest.fixture
def tree(tmp_path):
    (tmp_path / "agent" / "plans").mkdir(parents=True)
    (tmp_path / "agent" / "plans" / cr.PLAN_NAME).write_text(PLAN)
    (tmp_path / ".ci" / "config").mkdir(parents=True)
    (tmp_path / ".ci" / "config" / "retired-terms.json").write_text(json.dumps(TERMS))
    (tmp_path / ".ci" / "config" / "notes.json").write_text('{"x": "nothing retired here"}')
    (tmp_path / "workers" / "account").mkdir(parents=True)
    (tmp_path / "workers" / "account" / "wrangler.eu.toml").write_text(WRANGLER)
    (tmp_path / "regions.json").write_text('{"regions": []}')
    return tmp_path


class FakeCf:
    """A small account: one retired Worker pair with a domain, a container and a DO namespace, a retired queue, D1, buckets and a Pages project, beside live new-name objects and kept ones."""

    def __init__(self):
        self.scripts = [
            "account-eu",
            "rediacc-account-eu",
            "rediacc-proxy-eu",
            "account-proof-loss-eu",
        ]
        self.bindings: dict = {
            "account-eu": [{"type": "queue", "queue_name": "backup-replicate-eu"}]
        }
        self.domains = [
            {"id": "dom1", "hostname": "eu.old.example", "service": "rediacc-account-eu"},
            {"id": "dom2", "hostname": "eu.new.example", "service": "account-eu"},
        ]
        self.namespaces = [
            {"id": "ns1", "name": "rediacc-proxy-eu_Exec", "script": "rediacc-proxy-eu"}
        ]
        self.containers = [
            {
                "id": "c1",
                "name": "rediacc-proxy-eu-exec",
                "durable_objects": {"namespace_id": "ns1"},
            },
            {
                "id": "c2",
                "name": "rediacc-proxy-eu-executorcontainer",
                "durable_objects": {"namespace_id": "gone"},
            },
            {"id": "c3", "name": "account-acme-exec", "durable_objects": {"namespace_id": "gone"}},
        ]
        self.queues = [
            {"queue_id": "q-old", "queue_name": "rediacc-backup-replicate-eu"},
            {"queue_id": "q-new", "queue_name": "backup-replicate-eu"},
        ]
        self.d1 = {
            "account-db-eu": ("u-eu", 0),
            "account-eu": ("u-new", 9),
            "account-acme": ("u-acme", 9),
        }
        self.buckets = {
            ("rediacc-configs-eu", "eu"): ["a", "b/c"],
            ("rediacc-backups-probe", "eu"): [],
            ("rediacc-public-data", "default"): ["big.tar"],
            ("configs-proof-loss-eu", "eu"): [],
            ("configs-eu", "eu"): ["k"],
        }
        self.pages = [{"id": "p1", "name": "oldsite"}]
        self.deletes: list = []

    @staticmethod
    def ok(result, info=None):
        return {"success": True, "result": result, "result_info": info or {"total_pages": 1}}

    def get(self, path, jurisdiction=None):
        base = path.split("?")[0]
        parts = base.strip("/").split("/")
        if base.endswith("/workers/scripts"):
            return self.ok([{"id": s} for s in self.scripts])
        if base.endswith("/settings"):
            return self.ok({"bindings": self.bindings.get(parts[-2], [])})
        if base == "/zones":
            return self.ok([])
        if base.endswith("/workers/domains"):
            return self.ok(self.domains)
        if base.endswith("/containers/applications"):
            return self.ok(self.containers)
        if base.endswith("/durable_objects/namespaces"):
            return self.ok(self.namespaces)
        if base.endswith("/queues"):
            return self.ok(self.queues)
        if base.endswith("/d1/database"):
            return self.ok([{"name": n, "uuid": u} for n, (u, _t) in self.d1.items()])
        if "/d1/database/" in base:
            tables = dict(self.d1.values())[parts[-1]]
            return self.ok({"num_tables": tables, "file_size": tables * 100})
        if base.endswith("/r2/buckets"):
            jur = jurisdiction or "default"
            return self.ok({"buckets": [{"name": n} for n, j in self.buckets if j == jur]}, {})
        if base.endswith("/usage"):
            keys = self.buckets[(parts[-2], jurisdiction or "default")]
            return self.ok({"objectCount": str(len(keys)), "payloadSize": str(10 * len(keys))})
        if base.endswith("/objects"):
            keys = self.buckets[(parts[-2], jurisdiction or "default")]
            return self.ok([{"key": k} for k in keys])
        if base.endswith("/pages/projects"):
            return self.ok(self.pages)
        raise AssertionError("unexpected GET " + path)

    def delete(self, path, jurisdiction=None):
        self.deletes.append((path, jurisdiction))
        if "/objects/" in path:
            bucket = path.split("/r2/buckets/")[1].split("/")[0]
            key = urllib.parse.unquote(path.split("/objects/")[1])
            self.buckets[(bucket, jurisdiction or "default")].remove(key)
        return self.ok(None)


def run(tree, cf, *argv):
    return cr.main(list(argv), client=cf, root=tree)


def test_the_retired_set_reads_the_names_table_terms_prefix_form_and_l11(tree):
    rs = cr.RetiredSet.load(tree)
    assert rs.why("rediacc-account-asia")
    assert rs.why("edge-rediacc-account-us")
    assert rs.why("rediacc-configs-bench"), "a bare -bench cell continues the name before it"
    assert rs.why("account-db-bench")
    assert rs.why("rediacc-backups-probe")
    assert rs.why("rediacc-backup-replicate-eu"), "pre-rename form of a declared queue"
    assert rs.why("oldsite"), "the L11 Pages project"
    for live in (
        "account-eu",
        "configs-eu",
        "backup-replicate-eu",
        "account-acme",
        "rediacc-account-server",
    ):
        assert rs.why(live) is None, live


def test_rediacc_public_data_and_proof_loss_objects_are_kept(tree):
    rs = cr.RetiredSet.load(tree)
    assert rs.matched("rediacc-public-data"), (
        "the fixture declares public-data, so only the keep list holds it back"
    )
    assert rs.why("rediacc-public-data") is None
    assert rs.why("rediacc-configs-proof-loss-eu") is None
    acts, kept = cr.build_plan(tree, "acct", FakeCf(), rs)
    names = {a.name for a in acts}
    assert "rediacc-public-data" not in names
    assert "configs-proof-loss-eu" not in names
    assert any("rediacc-public-data" in k for k in kept)


def test_dry_run_issues_no_mutating_call(tree, capsys):
    cf = FakeCf()
    assert run(tree, cf, "plan") == 0
    assert run(tree, cf, "delete", "--no-archive", ASKED) == 0
    assert cf.deletes == []
    assert "dry run" in capsys.readouterr().out


def test_a_data_holder_without_archive_is_refused(tree, capsys):
    cf = FakeCf()
    assert run(tree, cf, "delete", "--write") == 1
    assert cf.deletes == []
    out = capsys.readouterr().out
    assert "REFUSED r2        rediacc-configs-eu" in out
    assert "no verified archive record" in out


def test_a_verified_archive_record_admits_a_data_holder(tree):
    cf = FakeCf()
    rec = cr.archive_path(tree, "r2", "rediacc-configs-eu")
    rec.parent.mkdir(parents=True)
    rec.write_text(json.dumps({"verified": True}))
    assert run(tree, cf, "delete", "--write") == 0
    assert ("/accounts/acct/r2/buckets/rediacc-configs-eu", "eu") in cf.deletes


def test_no_archive_needs_an_asked_minute(tree):
    cf = FakeCf()
    assert run(tree, cf, "delete", "--write", "--no-archive", "yes") == 2
    assert cf.deletes == []


def test_a_still_referenced_name_is_refused(tree, capsys):
    (tree / ".ci" / "config" / "notes.json").write_text('{"db": "account-db-eu"}')
    cf = FakeCf()
    assert run(tree, cf, "delete", "--write", "--no-archive", ASKED) == 1
    assert cf.deletes == []
    assert "still named by tracked config: .ci/config/notes.json" in capsys.readouterr().out


def test_a_binding_from_a_live_worker_is_refused(tree, capsys):
    cf = FakeCf()
    cf.bindings["account-eu"].append({"type": "service", "service": "rediacc-proxy-eu"})
    assert run(tree, cf, "delete", "--write", "--no-archive", ASKED) == 1
    assert cf.deletes == []
    assert "service binding of account-eu" in capsys.readouterr().out


def test_a_name_outside_the_retired_set_is_refused(tree, capsys):
    cf = FakeCf()
    assert run(tree, cf, "delete", "--write", "--no-archive", ASKED, "--only", "account-eu") == 1
    assert (
        run(tree, cf, "delete", "--write", "--no-archive", ASKED, "--only", "rediacc-public-data")
        == 1
    )
    assert cf.deletes == []
    assert "outside the retired set" in capsys.readouterr().err


def test_the_executor_rechecks_every_name_before_it_is_sent(tree):
    cf = FakeCf()
    rs = cr.RetiredSet.load(tree)
    stray = cr.Action("d1", "account-eu", "u-new", "smuggled in")
    assert cr.execute(tree, "acct", cf, rs, [stray], True, ASKED) == 1
    assert cf.deletes == []


def test_order_is_unbind_workers_containers_queues_d1_r2_pages(tree):
    cf = FakeCf()
    assert run(tree, cf, "delete", "--write", "--no-archive", ASKED) == 0
    order: list[str] = []
    for path, _jur in cf.deletes:
        step = (
            "unbind"
            if "/workers/domains/" in path
            else "worker"
            if "/workers/scripts/" in path
            else "container"
            if "/containers/" in path
            else "queue"
            if "/queues/" in path
            else "d1"
            if "/d1/" in path
            else "r2"
            if "/r2/" in path
            else "pages"
            if "/pages/" in path
            else "?"
        )
        if not order or order[-1] != step:
            order.append(step)
    assert order == ["unbind", "worker", "container", "queue", "d1", "r2", "pages"]
    paths_ = [p for p, _ in cf.deletes]
    assert "/accounts/acct/workers/domains/dom1" in paths_
    assert "/accounts/acct/workers/domains/dom2" not in paths_
    assert "/accounts/acct/workers/scripts/rediacc-proxy-eu?force=true" in paths_
    assert {
        "/accounts/acct/containers/applications/c1",
        "/accounts/acct/containers/applications/c2",
    } <= set(paths_)
    assert "/accounts/acct/containers/applications/c3" not in paths_
    assert "/accounts/acct/queues/q-new" not in paths_
    # The bucket is emptied, object by object through its jurisdiction, before it is deleted.
    bucket = paths_.index("/accounts/acct/r2/buckets/rediacc-configs-eu")
    assert paths_.index("/accounts/acct/r2/buckets/rediacc-configs-eu/objects/b%2Fc") < bucket
    assert cf.buckets[("rediacc-configs-eu", "eu")] == []
    assert not any(
        "rediacc-public-data" in p or p.rsplit("/", 1)[-1] == "configs-eu" for p in paths_
    )
    assert [p for p in paths_ if "/d1/" in p] == ["/accounts/acct/d1/database/u-eu"]
    records = list((tree / cr.RECORD_DIR).glob("*-delete.jsonl"))
    assert len(records) == 1
    rows = [json.loads(line) for line in records[0].read_text().splitlines()]
    assert {r["status"] for r in rows} == {"started", "done"}
    assert all(r["no_archive"] == ASKED for r in rows)


def test_the_live_plan_names_the_rename_objects():
    rs = cr.RetiredSet.load(ROOT)
    for old in (
        "rediacc-account-eu",
        "edge-rediacc-proxy-asia",
        "rediacc-www",
        "account-db-eu",
        "edge-account-db-us",
        "rediacc-backups-probe",
        "edge-rediacc-configs-eu",
        "rediacc-releases",
        "rediacc",
    ):
        assert rs.why(old), old
    for keep in (
        "account-eu",
        "backups-eu",
        "releases",
        "media",
        "rediacc-public-data",
        "backups-proof-loss-eu",
        "rediacc-account-server",
        "rediacc-proxy-executor",
    ):
        assert rs.why(keep) is None, keep


class ThrottledCf(FakeCf):
    """A FakeCf whose object DELETEs answer 429 a set number of times per key before they succeed, or answer another status for ever."""

    def __init__(self, throttles: int = 0, status: int = 429):
        super().__init__()
        self.throttles, self.status = throttles, status
        self.attempts: dict = {}

    def delete(self, path, jurisdiction=None):
        if "/objects/" in path:
            n = self.attempts[path] = self.attempts.get(path, 0) + 1
            if self.status != 429 or n <= self.throttles:
                raise cfl.CfError("DELETE %s: HTTP %s" % (path, self.status), self.status)
        return super().delete(path, jurisdiction)


@pytest.fixture
def pauses(monkeypatch):
    out: list = []
    monkeypatch.setattr(cfl.time, "sleep", out.append)
    return out


def test_emptying_parallelism_defaults_to_four_and_a_flag_sets_it(tree, monkeypatch):
    widths: list = []
    real = cr.concurrent.futures.ThreadPoolExecutor

    def spy(n, *a, **kw):
        widths.append(n)
        return real(n, *a, **kw)

    monkeypatch.setattr(cr.concurrent.futures, "ThreadPoolExecutor", spy)
    assert cr.EMPTY_WORKERS == 4
    assert run(tree, FakeCf(), "delete", "--write", "--no-archive", ASKED) == 0
    assert set(widths) == {4}
    widths.clear()
    assert (
        run(tree, FakeCf(), "delete", "--write", "--empty-workers", "2", "--no-archive", ASKED) == 0
    )
    assert set(widths) == {2}


def test_a_429_storm_on_one_object_eventually_succeeds(tree, pauses):
    cf = ThrottledCf(throttles=cr.THROTTLE_ROUNDS)
    assert run(tree, cf, "delete", "--write", "--no-archive", ASKED) == 0
    assert cf.buckets[("rediacc-configs-eu", "eu")] == []
    assert len(pauses) >= cr.THROTTLE_ROUNDS
    assert all(p >= cr.THROTTLE_PAUSE_S for p in pauses)


def test_a_429_that_never_clears_stops_the_run_after_the_rounds(tree, pauses, capsys):
    cf = ThrottledCf(throttles=10**6)
    assert run(tree, cf, "delete", "--write", "--no-archive", ASKED) == 1
    assert pauses
    assert "failed" in capsys.readouterr().err


def test_control_a_403_stops_the_run_at_once(tree, pauses, capsys):
    cf = ThrottledCf(status=403)
    assert run(tree, cf, "delete", "--write", "--no-archive", ASKED) == 1
    assert pauses == []
    assert "HTTP 403" in capsys.readouterr().err
