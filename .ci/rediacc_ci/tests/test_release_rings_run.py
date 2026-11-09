"""The oracle for `rediacc_ci.release.rings_run` (agent/plans/PLAN-enterprise-isolation.md box K2): the ring runner over `Step` and `Run`, driven against an in-memory control plane and a recording child runner. Nothing is deployed.

The fake control plane is one sqlite database per region loaded with the real control migration, plus one per company holding `subscription_activations`, so every query the runner sends is real SQL against the real schema. The child runner records each argv and fails the steps a case plants.
"""

from __future__ import annotations

import dataclasses
import datetime
import pathlib
import sqlite3

import pytest

from rediacc_ci.deploy import console_executor
from rediacc_ci.enterprise import registry
from rediacc_ci.release import rings, rings_run

UTC = datetime.UTC
NOW = datetime.datetime(2026, 11, 11, 12, 0, tzinfo=UTC)
V = "0.9.1"
D = datetime.timedelta(days=1)
H = datetime.timedelta(hours=1)
MIGRATION = registry.migration_sql()


def stamp(at: datetime.datetime) -> str:
    return at.strftime("%Y-%m-%dT%H:%M:%SZ")


class Plane:
    """Region control databases and company databases in sqlite, reached through one `Query`."""

    def __init__(self, bench: bool = False) -> None:
        self.bench = bench
        self.dbs: dict[str, sqlite3.Connection] = {}
        for name in registry.databases(bench).values():
            con = sqlite3.connect(":memory:")
            con.row_factory = sqlite3.Row
            con.executescript(MIGRATION)
            self.dbs[name] = con
        self.down: set[str] = set()
        self.sent: list[tuple[str, str]] = []

    def query(self, database: str, sql: str, params: list) -> list[dict]:
        self.sent.append((database, sql))
        if database in self.down:
            msg = "fake: %s is unreachable" % database
            raise OSError(msg)
        con = self.dbs[database]
        try:
            cur = con.execute(sql, params)
        except sqlite3.Error as exc:
            # The `registry.Query` contract: a transport failure raises one of the errors the registry names.
            raise RuntimeError(str(exc)) from None
        rows = [dict(r) for r in cur.fetchall()] if cur.description else []
        con.commit()
        return rows

    def control(self, region: str) -> sqlite3.Connection:
        return self.dbs[registry.control_database(region, self.bench)]

    def add(
        self,
        cid: str,
        machines: int,
        *,
        region: str = "eu",
        stored: int = 0,
        sampled: bool = True,
        override: str | None = None,
        window: tuple[str, int, int] | None = None,
        state: str = "active",
    ) -> None:
        name = "acme" + cid[-4:]
        con = self.control(region)
        con.execute(
            "INSERT INTO companies (id, name, region, state, created_at, updated_at) VALUES (?,?,?,?,?,?)",
            (cid, name, region, state, stamp(NOW), stamp(NOW)),
        )
        con.execute(
            "INSERT INTO ring (company_id, machines_high_water, sampled_at) VALUES (?,?,?)",
            (cid, stored, stamp(NOW - D) if sampled else None),
        )
        if override:
            con.execute(
                "INSERT INTO ring_override (company_id, ring, reason, set_at) VALUES (?,?,?,?)",
                (cid, override, "test", stamp(NOW)),
            )
        if window:
            con.execute(
                "INSERT INTO upgrade_window (company_id, days, start_hour, end_hour) VALUES (?,?,?,?)",
                (cid, *window),
            )
        con.commit()
        company = sqlite3.connect(":memory:")
        company.row_factory = sqlite3.Row
        company.execute("CREATE TABLE subscription_activations (machine_id TEXT)")
        company.executemany(
            "INSERT INTO subscription_activations VALUES (?)",
            [("m%d" % i,) for i in range(machines)],
        )
        company.commit()
        self.dbs["account-%s" % name] = company

    def rollout(
        self, cid: str, status: str, at: datetime.datetime, *, region: str = "eu", rid: str = ""
    ) -> None:
        con = self.control(region)
        ring = "small"
        con.execute(
            "INSERT INTO rollout (release_id, company_id, ring, status, version, finished_at) VALUES (?,?,?,?,?,?)",
            (rid or "v%s" % V, cid, ring, status, V, stamp(at)),
        )
        con.commit()

    def rows(self, sql: str, region: str = "eu") -> list[dict]:
        return [dict(r) for r in self.control(region).execute(sql).fetchall()]


class Children:
    """The recording child runner: `fail` names (company id, step id) pairs that exit 1. A successful `record-after` writes the deployed rollout row, as `deploy_record after --sink control` does."""

    def __init__(self, plane: Plane, clock: list[datetime.datetime]) -> None:
        self.plane = plane
        self.clock = clock
        self.calls: list[tuple[str, str, list[str]]] = []
        self.fail: set[tuple[str, str]] = set()

    def __call__(
        self, argv: list[str], cwd: pathlib.Path, env: dict[str, str], capture: bool
    ) -> tuple[int, str]:
        del cwd, capture
        cid = env.get("RINGS_COMPANY", "")
        step = env.get("RINGS_STEP", "")
        self.calls.append((cid, step, argv))
        if (cid, step) in self.fail or "raise SystemExit(1)" in " ".join(argv):
            return 1, ""
        if step == "record-after":
            region = env["RINGS_REGION"]
            rid = argv[argv.index("--release-id") + 1]
            ring = argv[argv.index("--ring") + 1]
            con = self.plane.control(region)
            con.execute(
                "INSERT INTO rollout (release_id, company_id, ring, status, version, finished_at) VALUES (?,?,?,?,?,?)",
                (rid, cid, ring, "deployed", V, stamp(self.clock[0])),
            )
            con.commit()
        self.clock[0] += datetime.timedelta(seconds=1)
        return 0, ""

    def deployed(self) -> list[str]:
        return [cid for cid, step, _ in self.calls if step == "account-deploy"]

    def steps_of(self, cid: str) -> list[str]:
        return [step for c, step, _ in self.calls if c == cid]


def target(row: rings_run.CompanyRow) -> console_executor.CompanyTarget:
    return console_executor.CompanyTarget(
        name=row.name,
        company_id=row.id,
        region=row.region,
        domain="example.test",
        account_config=pathlib.Path("/x/workers/account/enterprise.%s.toml" % row.name),
        proxy_config=pathlib.Path("/x/workers/proxy/enterprise.%s.toml" % row.name),
        bench=row.bench,
    )


@dataclasses.dataclass
class Rig:
    plane: Plane
    kids: Children
    world: rings_run.World
    clock: list[datetime.datetime]

    def run(self, *argv: str) -> int:
        return rings_run.main(["--version", V, *argv], world=self.world)


def rig(
    tmp_path: pathlib.Path,
    *,
    bench: bool = False,
    fast_at: datetime.datetime | None = NOW - 8 * D,
    record: bool = True,
) -> Rig:
    plane = Plane(bench)
    clock = [NOW]
    kids = Children(plane, clock)

    def release_record(version: str) -> dict | None:
        if not record or fast_at is None:
            return None
        return {"version": version, "failed_step": None, "recorded_at": stamp(fast_at)}

    world = rings_run.World(
        query=plane.query,
        release_record=release_record,
        runner=kids,
        now=lambda: clock[0],
        root=tmp_path,
        out=tmp_path / "out",
        target=target,
    )
    return Rig(plane, kids, world, clock)


# -- one Run per company, the company steps -----------------------------------------


def test_one_run_per_company_in_ring_order(tmp_path: pathlib.Path) -> None:
    r = rig(tmp_path)
    r.plane.add("c00000001", 3)
    r.plane.add("c00000002", 4)
    r.plane.add("c00000003", 60)
    r.plane.add("c00000004", 5, override="canary")
    rc = r.run("--skip-pauses", "--order", "sec-1")
    assert rc == 0
    assert r.kids.deployed() == ["c00000004", "c00000001", "c00000002", "c00000003"]
    rows = r.plane.rows("SELECT company_id, status FROM rollout ORDER BY company_id")
    assert {row["company_id"]: row["status"] for row in rows} == dict.fromkeys(
        ("c00000001", "c00000002", "c00000003", "c00000004"), "deployed"
    )


def test_company_steps_drop_account_secrets_and_name_the_company(tmp_path: pathlib.Path) -> None:
    r = rig(tmp_path)
    r.plane.add("c00000001", 3)
    assert r.run() == 0
    steps = r.kids.steps_of("c00000001")
    assert steps == [
        "record-before",
        "account-deploy",
        "proxy-deploy",
        "proxy-smoke",
        "executor-enable",
        "record-after",
    ]
    assert "account-secrets" not in steps
    argv = next(a for c, s, a in r.kids.calls if s == "account-deploy")
    assert "--proxy-config" not in argv, "deploy_account refuses --proxy-config"
    after = next(a for c, s, a in r.kids.calls if s == "record-after")
    assert after[after.index("--sink") + 1] == "control"
    assert after[after.index("--ring") + 1] == "small"
    assert "r2" not in after


def test_company_steps_table_matches_the_release_table_rows() -> None:
    row = rings_run.CompanyRow("c00000001", "acme0001", "eu", 3, 3, True, None, (), False)
    steps = rings_run.company_steps(target(row), ring="small", release_id="v1", previous="")
    by_id = {s.id: s for s in steps}
    assert by_id["rollback"].on_failure
    assert by_id["rollback"].arm == "record-before"
    assert by_id["record-after"].always
    assert by_id["record-after"].arm == "record-before"
    assert all(s.cwd == "root" for s in steps)
    assert all("acme" not in s.id for s in steps)


def test_previous_release_is_read_from_the_control_database(tmp_path: pathlib.Path) -> None:
    r = rig(tmp_path)
    r.plane.add("c00000001", 3)
    con = r.plane.control("eu")
    con.execute(
        "INSERT INTO rollout VALUES ('v0.9.0', 'c00000001', 'small', 'deployed', '0.9.0', ?)",
        (stamp(NOW - 9 * D),),
    )
    con.commit()
    assert r.run() == 0
    before = next(a for c, s, a in r.kids.calls if s == "record-before")
    assert before[before.index("--previous-release") + 1] == "0.9.0"


# -- a failure latches a stop; --resume ---------------------------------------------


def test_a_failure_stops_names_the_company_and_leaves_later_rings(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    r = rig(tmp_path)
    r.plane.add("c00000001", 3, override="canary")
    r.plane.add("c00000002", 20)
    r.plane.add("c00000003", 70)
    r.kids.fail.add(("c00000002", "account-deploy"))
    rc = r.run("--skip-pauses", "--order", "sec-1")
    assert rc == 1
    assert "c00000002" in capsys.readouterr().err
    assert "c00000003" not in r.kids.deployed()
    assert "rollback" in r.kids.steps_of("c00000002")
    status = {
        row["company_id"]: row["status"]
        for row in r.plane.rows("SELECT company_id, status FROM rollout ORDER BY finished_at")
    }
    assert status["c00000002"] == "failed"

    # The latch holds on the next invocation, with nothing deployed.
    r.kids.calls.clear()
    assert r.run("--skip-pauses", "--order", "sec-1") == 1
    assert r.kids.deployed() == []

    # A resume naming that version and company redeploys it and finishes.
    r.kids.fail.clear()
    rc = r.run("--skip-pauses", "--order", "sec-1", "--resume", V, "--company", "c00000002")
    assert rc == 0
    assert r.kids.deployed() == ["c00000002", "c00000003"]
    ids = [a[a.index("--release-id") + 1] for c, s, a in r.kids.calls if s == "record-after"]
    assert ids[0] != "v%s" % V, "a resumed attempt writes a fresh rollout key"


def test_resume_needs_exactly_one_company(tmp_path: pathlib.Path) -> None:
    r = rig(tmp_path)
    r.plane.add("c00000001", 3)
    assert r.run("--resume", V) == 2
    assert r.kids.calls == []


def test_planted_failure_is_bench_only_and_stops(tmp_path: pathlib.Path) -> None:
    r = rig(tmp_path)
    r.plane.add("c00000001", 3)
    assert r.run("--plant-failure", "c00000001") == 2
    assert r.kids.calls == []

    b = rig(tmp_path, bench=True)
    b.plane.add("c00000001", 3)
    b.plane.add("c00000002", 4)
    assert b.run("--bench", "--plant-failure", "c00000001") == 1
    assert "planted-failure" in b.kids.steps_of("c00000001")
    assert "c00000001" not in b.kids.deployed()


# -- --company takes the opaque id ---------------------------------------------------


def test_company_refuses_a_name(tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]) -> None:
    r = rig(tmp_path)
    r.plane.add("c00000001", 3)
    assert r.run("--company", "acme0000") == 2
    err = capsys.readouterr().err
    assert "opaque" in err
    assert "acme0000" not in err
    assert r.kids.calls == []


def test_company_restricts_the_deploy(tmp_path: pathlib.Path) -> None:
    r = rig(tmp_path)
    r.plane.add("c00000001", 3)
    r.plane.add("c00000002", 4)
    assert r.run("--company", "c00000002") == 0
    assert r.kids.deployed() == ["c00000002"]


def test_company_unknown_is_refused(tmp_path: pathlib.Path) -> None:
    r = rig(tmp_path)
    r.plane.add("c00000001", 3)
    assert r.run("--company", "c0000beef") == 2


def test_no_name_or_host_is_printed(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    r = rig(tmp_path)
    r.plane.add("c00000001", 3)
    r.kids.fail.add(("c00000001", "proxy-deploy"))
    r.run()
    out = capsys.readouterr()
    assert "acme" not in out.out + out.err


# -- machine sampling ----------------------------------------------------------------


def test_sampling_raises_the_high_water_mark_and_never_lowers_it(tmp_path: pathlib.Path) -> None:
    r = rig(tmp_path)
    r.plane.add("c00000001", 12, stored=3)
    r.plane.add("c00000002", 2, stored=60)
    assert r.run("--dry-run") == 0
    rows = r.plane.rows("SELECT company_id, machines_high_water FROM ring ORDER BY company_id")
    assert [row["machines_high_water"] for row in rows] == [3, 60], "a dry run writes nothing"
    assert r.run("--skip-pauses", "--order", "s") == 0
    rows = r.plane.rows("SELECT company_id, machines_high_water FROM ring ORDER BY company_id")
    assert [row["machines_high_water"] for row in rows] == [12, 60]
    after = {c: a[a.index("--ring") + 1] for c, s, a in r.kids.calls if s == "record-after"}
    assert after == {"c00000001": "medium", "c00000002": "large"}


def test_a_failed_sample_uses_the_stored_mark(tmp_path: pathlib.Path) -> None:
    r = rig(tmp_path)
    r.plane.add("c00000001", 3, stored=20)
    del r.plane.dbs["account-acme0001"]
    r.plane.dbs["account-acme0001"] = sqlite3.connect(":memory:")  # no table: the sample fails
    assert r.run() == 0
    after = next(a for c, s, a in r.kids.calls if s == "record-after")
    assert after[after.index("--ring") + 1] == "medium"


def test_a_never_sampled_company_whose_sample_fails_is_refused(tmp_path: pathlib.Path) -> None:
    r = rig(tmp_path)
    r.plane.add("c00000001", 3, sampled=False)
    r.plane.dbs["account-acme0001"] = sqlite3.connect(":memory:")
    assert r.run() == 1
    assert r.kids.calls == []


# -- pauses, resmoke, windows, soak --------------------------------------------------


def test_pause_after_small_waits_then_resmokes_before_medium(tmp_path: pathlib.Path) -> None:
    r = rig(tmp_path)
    r.plane.add("c00000001", 3)
    r.plane.add("c00000002", 20)
    assert r.run() == 0
    assert r.kids.deployed() == ["c00000001"], "the 24 h pause holds medium"
    r.kids.calls.clear()
    r.clock[0] += 25 * H
    assert r.run() == 0
    assert r.kids.steps_of("c00000001") == ["proxy-smoke"], "the small ring is re-smoked"
    assert r.kids.deployed() == ["c00000002"]
    audit = r.plane.rows("SELECT action, detail FROM audit WHERE action = 'ring-resmoke'")
    assert len(audit) == 1
    assert '"small"' in audit[0]["detail"]


def test_a_failed_resmoke_latches_a_stop(tmp_path: pathlib.Path) -> None:
    r = rig(tmp_path)
    r.plane.add("c00000001", 3)
    r.plane.add("c00000002", 20)
    r.plane.rollout("c00000001", "deployed", NOW - 30 * H)
    r.kids.fail.add(("c00000001", "proxy-smoke"))
    assert r.run() == 1
    assert r.kids.deployed() == []


def test_window_holds_the_ring(tmp_path: pathlib.Path) -> None:
    r = rig(tmp_path)
    # NOW is a Wednesday 12:00; the window opens Thursday 02:00.
    r.plane.add("c00000001", 3, window=("4", 2, 4))
    assert r.run() == 0
    assert r.kids.deployed() == []


def test_window_days_and_hours_read_from_the_schema() -> None:
    (w,) = rings_run.windows_of("1-3,5", 22, 24)
    assert w.days == frozenset({0, 1, 2, 4})
    assert (w.start, w.end) == (22 * 60, 0)
    assert rings_run.windows_of(None, None, None) == ()


def test_soak_holds_until_seven_days(tmp_path: pathlib.Path) -> None:
    r = rig(tmp_path, fast_at=NOW - 2 * D)
    r.plane.add("c00000001", 3)
    assert r.run() == 0
    assert r.kids.deployed() == []
    assert r.run("--waive-soak", "--order", "sec-9") == 0
    assert r.kids.deployed() == ["c00000001"]


def test_no_release_record_means_bench_has_not_taken_it(tmp_path: pathlib.Path) -> None:
    r = rig(tmp_path, record=False)
    r.plane.add("c00000001", 3)
    assert r.run() == 0
    assert r.kids.deployed() == []


def test_skip_pauses_without_an_order_is_refused_before_anything(tmp_path: pathlib.Path) -> None:
    r = rig(tmp_path)
    r.plane.add("c00000001", 3)
    sent = len(r.plane.sent)
    assert r.run("--skip-pauses") == 2
    assert r.run("--waive-soak") == 2
    assert len(r.plane.sent) == sent
    assert r.kids.calls == []


def test_bench_shortens_pauses_and_soak(tmp_path: pathlib.Path) -> None:
    r = rig(tmp_path, bench=True, fast_at=NOW - H)
    r.plane.add("c00000001", 3)
    r.plane.add("c00000002", 20)
    assert r.run("--bench", "--soak-days", "0", "--pause-minutes", "0") == 0
    assert r.kids.deployed() == ["c00000001", "c00000002"]


def test_shortened_pauses_and_soak_are_bench_only(tmp_path: pathlib.Path) -> None:
    r = rig(tmp_path)
    r.plane.add("c00000001", 3)
    assert r.run("--pause-minutes", "0") == 2
    assert r.run("--soak-days", "0") == 2


# -- regions -------------------------------------------------------------------------


def test_an_unreachable_region_stops_only_its_own_companies(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    r = rig(tmp_path)
    r.plane.add("c00000001", 3, region="eu")
    r.plane.add("c00000002", 3, region="us")
    r.plane.down.add(registry.control_database("us"))
    assert r.run() == 1
    assert r.kids.deployed() == ["c00000001"]
    assert "us" in capsys.readouterr().err


def test_bench_reads_the_bench_control_databases(tmp_path: pathlib.Path) -> None:
    r = rig(tmp_path, bench=True)
    r.plane.add("c00000001", 3)
    r.run("--bench", "--dry-run")
    assert {db for db, _ in r.plane.sent if db.startswith("control")} <= {
        "control-bench-eu",
        "control-bench-us",
    }


def test_inactive_companies_are_not_released(tmp_path: pathlib.Path) -> None:
    r = rig(tmp_path)
    r.plane.add("c00000001", 3, state="suspended")
    assert r.run() == 0
    assert r.kids.deployed() == []


# -- dry run -------------------------------------------------------------------------


def test_dry_run_deploys_and_writes_nothing(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    r = rig(tmp_path)
    r.plane.add("c00000001", 3)
    assert r.run("--dry-run") == 0
    assert r.kids.calls == []
    assert r.plane.rows("SELECT * FROM rollout") == []
    assert r.plane.rows("SELECT * FROM audit") == []
    assert "deploy" in capsys.readouterr().out


# -- the live transport --------------------------------------------------------------


def test_inline_quotes_text_and_keeps_numbers() -> None:
    sql = rings_run.inline("SELECT ? , ?, ?", ["it's", 3, None])
    assert sql == "SELECT 'it''s' , 3, NULL"
    with pytest.raises(ValueError, match="placeholders"):
        rings_run.inline("SELECT ?", [])


def test_d1_results_flatten_every_statement() -> None:
    text = '[{"results": [{"n": 1}], "success": true}, {"results": [{"n": 2}]}]'
    assert rings_run.d1_rows(text) == [{"n": 1}, {"n": 2}]
    with pytest.raises(ValueError, match="Expecting value"):
        rings_run.d1_rows("not json")


def test_decision_uses_the_k1_core(tmp_path: pathlib.Path) -> None:
    """The runner's state is what `rings.decide` reads: one `rings.Company` per active company."""
    r = rig(tmp_path)
    r.plane.add("c00000001", 3, override="canary")
    read = rings_run.read_world(r.world, V, bench=False, sample=False)
    assert [c.id for c in read.state.companies] == ["c00000001"]
    assert read.state.companies[0].override == "canary"
    assert rings.decide(read.state, NOW).ring == "canary"
