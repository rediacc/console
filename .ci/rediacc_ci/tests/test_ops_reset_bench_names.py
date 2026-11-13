"""reset_bench reads its bucket, jurisdiction and database id from wrangler.bench.toml (review finding 6826f345.1)."""

import pytest

from rediacc_ci.ops import bench_preflight, reset_bench


def _names(**over) -> bench_preflight.BenchNames:
    base = {
        "database_name": "account-bench",
        "database_id": "db-id-1",
        "config_bucket": "config-bench",
        "config_jurisdiction": "eu",
        "backup_bucket": "",
        "backup_jurisdiction": "",
    }
    return bench_preflight.BenchNames(**{**base, **over})


def _creds(monkeypatch, names, endpoint="https://abc123.r2.cloudflarestorage.com"):
    monkeypatch.setattr(bench_preflight, "bench_names", lambda *_a: names)
    monkeypatch.setenv("CLOUDFLARE_R2_ENDPOINT", endpoint)
    monkeypatch.setenv("CLOUDFLARE_R2_ACCESS_KEY_ID", "k")
    monkeypatch.setenv("CLOUDFLARE_R2_SECRET_ACCESS_KEY", "s")
    return reset_bench.R2Credentials()


class _Auth:
    headers = None


def test_a_jurisdictional_config_bucket_is_reached_through_the_jurisdiction_host(monkeypatch):
    creds = _creds(monkeypatch, _names())
    assert creds.bucket == "config-bench"
    assert creds.host() == "https://abc123.eu.r2.cloudflarestorage.com"


def test_a_bucket_without_a_jurisdiction_keeps_the_default_host(monkeypatch):
    creds = _creds(monkeypatch, _names(config_jurisdiction=""))
    assert creds.host() == "https://abc123.r2.cloudflarestorage.com"


def test_a_missing_config_bucket_binding_is_named_as_missing(monkeypatch):
    creds = _creds(monkeypatch, _names(config_bucket=""))
    assert creds.missing() == ["CONFIG_BUCKET in wrangler.bench.toml"]
    assert _creds(monkeypatch, _names()).missing() == []


def test_the_query_targets_the_database_id_of_the_toml(monkeypatch):
    seen = {}

    def fake_curl(_method, url, _headers, _body, flags=""):
        seen["url"] = url
        seen["flags"] = flags
        return {"success": True}

    monkeypatch.setattr(bench_preflight, "bench_names", lambda *_a: _names())
    monkeypatch.setattr(reset_bench.cf_auth, "curl_json", fake_curl)
    reset_bench._query(_Auth(), "SELECT 1")
    assert seen["url"].endswith("/d1/database/db-id-1/query")


def test_a_toml_without_a_database_id_refuses_the_query(monkeypatch):
    monkeypatch.setattr(bench_preflight, "bench_names", lambda *_a: _names(database_id=""))
    with pytest.raises(reset_bench.ResetError, match="database_id"):
        reset_bench._query(_Auth(), "SELECT 1")
