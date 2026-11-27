"""The bench production guard (agent/plans/PLAN-hostinger-to-bench.md Design 3): a declared subscription stops every reset_bench mode before any credential is read, the D1 manifest check refuses on any planted row, and an empty declaration is an unarmed guard that refuses too (fail closed, 2026-11-27)."""

import json
import pathlib

import pytest

from rediacc_ci.ops import bench_preflight, bench_production, reset_bench

SUB = "33333333-3333-4333-8333-333333333333"
OTHER = "99999999-9999-4999-8999-999999999999"
DECLARED = [bench_production.Protected(SUB, "hostinger", "production backups")]
US_ENTRY = bench_production.Protected(SUB, "hostinger", "production backups", "us")
BENCH_NAMES = bench_preflight.BenchNames(
    "account-bench",
    "8c260075-db26-4787-b700-b657f21a5f61",
    "configs-bench",
    "",
    "b",
    "",
    "audit-bench",
)


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


def test_an_empty_declaration_loads_empty_and_refuses_the_reset(tmp_path):
    assert bench_production.load(_write(tmp_path, {"protected": []})) == []
    for region in (None, "eu", "us", "asia"):
        refusal = bench_production.reset_refusal([], region)
        assert refusal is not None
        assert "unarmed" in refusal


def test_a_declared_entry_is_loaded(tmp_path):
    path = _write(
        tmp_path,
        {
            "protected": [
                {
                    "subscription_id": SUB,
                    "region": "eu",
                    "machine": "hostinger",
                    "reason": "r",
                    "plan": "p",
                }
            ]
        },
    )
    assert bench_production.load(path) == [bench_production.Protected(SUB, "hostinger", "r", "eu")]


@pytest.mark.parametrize(
    "data",
    [
        "{not json",
        {"protected": "x"},
        {},
        {"protected": [{"subscription_id": "not-a-uuid"}]},
        {"protected": [{"subscription_id": SUB + "\n"}]},
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
@pytest.mark.parametrize("argv", [["--yes"], ["--yes", "--d1-only"], ["--yes", "--r2-only"], []])
def test_an_empty_declaration_makes_every_mode_exit_2_before_any_credential(
    monkeypatch, capsys, argv
):
    # The 2026-11-27 defect: an empty list let `--yes` reach the wipe of the bench D1 holding hostinger's backups.
    monkeypatch.setattr(bench_production, "load", lambda *_a: [])
    assert reset_bench.main(argv) == 2
    assert "unarmed" in capsys.readouterr().err


@pytest.mark.usefixtures("no_credentials")
def test_a_declaration_in_another_region_lets_reset_bench_reach_its_credentials(monkeypatch):
    # CONTROL: an armed guard with nothing declared in the wiped region continues to the profile re-exec.
    monkeypatch.setattr(bench_production, "load", lambda *_a: [US_ENTRY])
    with pytest.raises(CredentialReadError):
        reset_bench.main(["--yes"])


# --- the live D1 check


def _rows_with(manifests: dict[str, int]):
    seen: list[str] = []

    def rows(sql: str) -> list[dict]:
        seen.append(sql)
        return [{"subscription_id": s, "manifests": n} for s, n in manifests.items()]

    return rows, seen


def test_the_d1_check_refuses_on_planted_manifest_rows():
    rows, seen = _rows_with({SUB: 3})
    refusal = bench_production.d1_refusal(rows, DECLARED)
    assert refusal is not None
    assert SUB in refusal
    assert "3 manifests, declared" in refusal
    assert seen == [bench_production.MANIFEST_QUERY]
    assert "FROM backup_manifests" in seen[0]


def test_the_d1_check_refuses_on_an_undeclared_subscriptions_manifests():
    # The production signal a declaration can miss: hostinger's rows were in D1 while the list was empty.
    rows, seen = _rows_with({OTHER: 5})
    refusal = bench_production.d1_refusal(rows, DECLARED)
    assert refusal is not None
    assert "%s (5 manifests)" % OTHER in refusal
    assert bench_production.d1_refusal(rows, []) is not None
    assert len(seen) == 2


def test_the_d1_check_passes_only_when_no_row_carries_a_manifest():
    rows, seen = _rows_with({SUB: 0, OTHER: 0})
    assert bench_production.d1_refusal(rows, DECLARED) is None
    # the query runs with nothing declared too
    assert bench_production.d1_refusal(rows, []) is None
    assert len(seen) == 2


def test_the_d1_check_refuses_a_count_that_is_not_a_number():
    with pytest.raises(bench_production.ProductionRefusalError, match="not a number"):
        bench_production.d1_refusal(lambda _s: [{"subscription_id": SUB, "manifests": "x"}], [])


def test_the_manifest_query_interpolates_no_id():
    assert "WHERE" not in bench_production.MANIFEST_QUERY
    assert "GROUP BY subscription_id" in bench_production.MANIFEST_QUERY


class _Auth:
    headers = None


def test_reset_bench_runs_the_d1_check_before_the_wipe(monkeypatch, capsys):
    # The declaration names only a us subscription, so the eu wipe passes the static refusal and reaches the live check: manifests of an UNDECLARED subscription stop it at exit 2 before any wipe.
    monkeypatch.setattr(bench_production, "load", lambda *_a: [US_ENTRY])
    monkeypatch.setattr(reset_bench.shutil, "which", lambda _c: "/usr/bin/true")
    monkeypatch.setattr(reset_bench, "_reexec_under_profile", lambda _a: None)
    monkeypatch.setattr(reset_bench, "_names", lambda *_a: BENCH_NAMES)
    monkeypatch.setattr(reset_bench.cf_auth, "resolve", lambda _a: _Auth())
    monkeypatch.setattr(reset_bench.cf_auth, "wrangler_env", lambda *_a, **_k: {})
    monkeypatch.setattr(reset_bench.cf_auth, "await_propagation", lambda _a: None)
    monkeypatch.setattr(reset_bench.cf_auth, "self_destruct", lambda _a: None)

    class Creds:
        bucket = "configs-bench"

        def __init__(self, *_a):
            pass

        def missing(self):
            return []

    monkeypatch.setattr(reset_bench, "R2Credentials", Creds)
    queries: list[str] = []

    def query(_auth, sql, *_a):
        queries.append(sql)
        return {
            "success": True,
            "result": [{"results": [{"subscription_id": OTHER, "manifests": 2}]}],
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


def test_signer_stop_refusal_names_the_signer_and_the_declaration():
    refusal = bench_production.signer_stop_refusal("signer-bench-eu", DECLARED)
    assert refusal is not None
    assert "signer-bench-eu" in refusal
    assert SUB in refusal
    assert bench_production.CONFIG_REL in refusal
    # control: nothing declared, nothing refused
    assert bench_production.signer_stop_refusal("signer-bench-eu", []) is None


# --- regions: an entry stops only its own region (PLAN-multi-region-bench W3)


def test_an_entry_without_a_region_fails_closed(tmp_path):
    path = _write(tmp_path, {"protected": [{"subscription_id": SUB, "machine": "m"}]})
    with pytest.raises(bench_production.ProductionRefusalError, match="no `region`"):
        bench_production.load(path)


def test_an_entry_with_a_malformed_region_fails_closed(tmp_path):
    path = _write(tmp_path, {"protected": [{"subscription_id": SUB, "region": "US east"}]})
    with pytest.raises(bench_production.ProductionRefusalError, match="no `region`"):
        bench_production.load(path)


def test_reset_refusal_covers_only_the_declared_region():
    assert bench_production.reset_refusal([US_ENTRY], "us")
    assert bench_production.reset_refusal([US_ENTRY], "eu") is None
    assert bench_production.reset_refusal([US_ENTRY], "asia") is None
    # a refusal asked without a region covers every entry
    assert bench_production.reset_refusal([US_ENTRY])


def test_signer_stop_refusal_follows_the_signers_region():
    assert bench_production.signer_stop_refusal("signer-bench-us", [US_ENTRY])
    assert bench_production.signer_stop_refusal("signer-bench-eu", [US_ENTRY]) is None
    # a name that carries no region is held against every entry
    assert bench_production.signer_stop_refusal("signer-other", [US_ENTRY])


def test_refuse_ids_can_be_scoped_to_a_region():
    with pytest.raises(bench_production.ProductionRefusalError):
        bench_production.refuse_ids([SUB], [US_ENTRY], "us")
    bench_production.refuse_ids([SUB], [US_ENTRY], "eu")
    with pytest.raises(bench_production.ProductionRefusalError):
        bench_production.refuse_ids([SUB], [US_ENTRY])


def test_the_refusal_text_names_the_region():
    refusal = bench_production.reset_refusal([US_ENTRY], "us")
    assert refusal is not None
    assert "region us" in refusal
