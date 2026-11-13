"""The bench production guard (agent/plans/PLAN-hostinger-to-bench.md Design 3): a declared subscription stops every reset_bench mode before any credential is read, the D1 manifest check refuses on planted rows, and an empty declaration lets reset_bench run as before."""

import json
import pathlib

import pytest

from rediacc_ci.ops import bench_production, reset_bench

SUB = "33333333-3333-4333-8333-333333333333"
OTHER = "99999999-9999-4999-8999-999999999999"
DECLARED = [bench_production.Protected(SUB, "hostinger", "production backups")]


class CredentialReadError(Exception):
    """Raised by every seam that would read or mint a credential."""


def _write(tmp_path, data) -> pathlib.Path:
    path = tmp_path / "bench-production.json"
    path.write_text(data if isinstance(data, str) else json.dumps(data), encoding="utf-8")
    return path


@pytest.fixture
def no_credentials(monkeypatch):
    """Every credential seam raises, so reaching one fails the test with CredentialReadError."""

    def boom(*_a, **_k):
        raise CredentialReadError

    monkeypatch.setattr(reset_bench, "_reexec_under_profile", boom)
    monkeypatch.setattr(reset_bench, "R2Credentials", boom)
    monkeypatch.setattr(reset_bench.cf_auth, "resolve", boom)
    monkeypatch.setattr(reset_bench.shutil, "which", lambda _c: "/usr/bin/true")


# --- the declaration file


def test_the_committed_declaration_parses():
    assert isinstance(bench_production.load(), list)


def test_an_empty_declaration_declares_nothing(tmp_path):
    assert bench_production.load(_write(tmp_path, {"protected": []})) == []
    assert bench_production.reset_refusal([]) is None


def test_a_declared_entry_is_loaded(tmp_path):
    path = _write(
        tmp_path,
        {
            "protected": [
                {"subscription_id": SUB, "machine": "hostinger", "reason": "r", "plan": "p"}
            ]
        },
    )
    assert bench_production.load(path) == [bench_production.Protected(SUB, "hostinger", "r")]


@pytest.mark.parametrize(
    "data",
    [
        "{not json",
        {"protected": "x"},
        {},
        {"protected": [{"subscription_id": "not-a-uuid"}]},
        {"protected": [{"machine": "hostinger"}]},
    ],
)
def test_an_unreadable_or_malformed_declaration_fails_closed(tmp_path, data):
    with pytest.raises(bench_production.ProductionRefusalError, match="fails closed"):
        bench_production.load(_write(tmp_path, data))


def test_a_missing_declaration_fails_closed(tmp_path):
    with pytest.raises(bench_production.ProductionRefusalError, match="fails closed"):
        bench_production.load(tmp_path / "absent.json")


# --- reset_bench refuses every mode before a credential is read


@pytest.mark.usefixtures("no_credentials")
@pytest.mark.parametrize("argv", [["--yes"], ["--yes", "--d1-only"], ["--yes", "--r2-only"], []])
def test_a_declared_subscription_makes_every_mode_exit_2_before_any_credential(
    monkeypatch, capsys, argv
):
    monkeypatch.setattr(bench_production, "load", lambda *_a: DECLARED)
    assert reset_bench.main(argv) == 2
    err = capsys.readouterr().err
    assert "production data" in err
    assert SUB in err


@pytest.mark.usefixtures("no_credentials")
def test_a_malformed_declaration_makes_reset_bench_exit_2(monkeypatch, capsys):
    def bad(*_a):
        raise bench_production.ProductionRefusalError("cannot read; the guard fails closed")

    monkeypatch.setattr(bench_production, "load", bad)
    assert reset_bench.main(["--yes"]) == 2
    assert "fails closed" in capsys.readouterr().err


@pytest.mark.usefixtures("no_credentials")
def test_an_empty_declaration_lets_reset_bench_reach_its_credentials(monkeypatch):
    # CONTROL: with nothing declared the run continues to the profile re-exec exactly as before the guard.
    monkeypatch.setattr(bench_production, "load", lambda *_a: [])
    with pytest.raises(CredentialReadError):
        reset_bench.main(["--yes"])


# --- the live D1 check


def _rows_with(manifests: dict[str, int]):
    seen: list[str] = []

    def rows(sql: str) -> list[dict]:
        seen.append(sql)
        return [
            {"subscription_id": s, "manifests": n}
            for s, n in manifests.items()
            if "'%s'" % s in sql
        ]

    return rows, seen


def test_the_d1_check_refuses_on_planted_manifest_rows():
    rows, seen = _rows_with({SUB: 3})
    refusal = bench_production.d1_refusal(rows, DECLARED)
    assert refusal is not None
    assert SUB in refusal
    assert "3 manifests" in refusal
    assert seen
    assert "FROM backup_manifests" in seen[0]


def test_the_d1_check_passes_when_the_declared_subscription_has_no_manifests():
    rows, _ = _rows_with({OTHER: 5})
    assert bench_production.d1_refusal(rows, DECLARED) is None


def test_the_d1_check_makes_no_query_when_nothing_is_declared():
    rows, seen = _rows_with({SUB: 3})
    assert bench_production.d1_refusal(rows, []) is None
    assert seen == []


def test_the_manifest_query_refuses_a_non_uuid_id():
    with pytest.raises(bench_production.ProductionRefusalError):
        bench_production.manifest_query(["x' OR 1=1 --"])


class _Auth:
    headers = None


def test_reset_bench_runs_the_d1_check_before_the_wipe(monkeypatch, capsys):
    # The static refusal is lifted here so the second layer is reached: planted manifests stop the run at exit 2 before any wipe.
    monkeypatch.setattr(bench_production, "load", lambda *_a: DECLARED)
    monkeypatch.setattr(bench_production, "reset_refusal", lambda _e: None)
    monkeypatch.setattr(reset_bench.shutil, "which", lambda _c: "/usr/bin/true")
    monkeypatch.setattr(reset_bench, "_reexec_under_profile", lambda _a: None)
    monkeypatch.setattr(reset_bench, "_names", object)
    monkeypatch.setattr(reset_bench.cf_auth, "resolve", lambda _a: _Auth())
    monkeypatch.setattr(reset_bench.cf_auth, "wrangler_env", lambda *_a, **_k: {})
    monkeypatch.setattr(reset_bench.cf_auth, "await_propagation", lambda _a: None)
    monkeypatch.setattr(reset_bench.cf_auth, "self_destruct", lambda _a: None)

    class Creds:
        bucket = "configs-bench"

        def missing(self):
            return []

    monkeypatch.setattr(reset_bench, "R2Credentials", Creds)
    queries: list[str] = []

    def query(_auth, sql):
        queries.append(sql)
        return {
            "success": True,
            "result": [{"results": [{"subscription_id": SUB, "manifests": 2}]}],
        }

    monkeypatch.setattr(reset_bench, "_query", query)

    def no_wipe(*_a):
        raise AssertionError("wiped despite manifests of a declared subscription")

    monkeypatch.setattr(reset_bench, "_wipe_d1", no_wipe)
    monkeypatch.setattr(reset_bench, "_wipe_r2", no_wipe)
    assert reset_bench.main(["--yes"]) == 2
    assert len(queries) == 1
    assert "backup_manifests" in queries[0]
    assert "backup manifests" in capsys.readouterr().err


# --- the drills' refusal helper


def test_refuse_ids_names_a_declared_subscription():
    with pytest.raises(bench_production.ProductionRefusalError, match=SUB):
        bench_production.refuse_ids([OTHER, SUB], DECLARED)


def test_refuse_ids_passes_undeclared_subscriptions():
    bench_production.refuse_ids([OTHER], DECLARED)
    bench_production.refuse_ids([SUB], [])
