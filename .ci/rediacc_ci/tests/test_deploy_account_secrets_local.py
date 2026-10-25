"""The local account-secrets path: derivation, the wrangler pin, the Turnstile preflight and the prune verb.

Nothing here reaches Cloudflare, bws or wrangler: the Turnstile fetch, the hydration and the push are injected, and the prune verb's API is a recording fake.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from rediacc_ci.deploy import account_secrets_local as local
from rediacc_ci.deploy import set_account_worker_secrets as pusher
from rediacc_ci.deploy import turnstile_drift as td
from rediacc_ci.deploy import wrangler_pin
from rediacc_ci.ops import prune_worker_secrets as prune

if TYPE_CHECKING:
    import pathlib


def _tree(tmp_path: pathlib.Path, pin: str, spec: str, installed: str | None) -> pathlib.Path:
    (tmp_path / ".ci" / "config").mkdir(parents=True)
    (tmp_path / ".ci" / "config" / "constants.sh").write_text(
        'readonly WRANGLER_VERSION="%s"\n' % pin, encoding="utf-8"
    )
    acct = tmp_path / "workers" / "account"
    acct.mkdir(parents=True)
    (acct / "package.json").write_text(
        json.dumps({"devDependencies": {"wrangler": spec}}), encoding="utf-8"
    )
    if installed is not None:
        mod = acct / "node_modules" / "wrangler"
        mod.mkdir(parents=True)
        (mod / "package.json").write_text(json.dumps({"version": installed}), encoding="utf-8")
    return tmp_path


def test_pin_agrees(tmp_path):
    code, lines = wrangler_pin.check(_tree(tmp_path, "4.150.0", "4.150.0", "4.150.0"))
    assert code == 0, lines


def test_pin_refuses_an_installed_mismatch(tmp_path):
    code, lines = wrangler_pin.check(_tree(tmp_path, "4.150.0", "4.150.0", "4.131.2"))
    assert code == 1
    assert "installed wrangler is 4.131.2" in "\n".join(lines)


def test_pin_refuses_a_range(tmp_path):
    code, lines = wrangler_pin.check(_tree(tmp_path, "4.150.0", "^4.67.0", "4.150.0"))
    assert code == 1
    assert "'^4.67.0'" in "\n".join(lines)


def test_pin_gives_no_verdict_without_an_install(tmp_path):
    code, _lines = wrangler_pin.check(_tree(tmp_path, "4.150.0", "4.150.0", None))
    assert code == 2


def test_the_real_tree_agrees():
    root = local.paths.repo_root()
    code, lines = wrangler_pin.check(root)
    installed = (root / "workers/account/node_modules/wrangler/package.json").is_file()
    # No verdict (2) is accepted only where wrangler is not installed; an installed tree must agree.
    assert code == (0 if installed else 2), lines


@pytest.mark.parametrize(
    ("region", "target", "worker", "suffix", "ses", "jur"),
    [
        ("eu", "stable", "rediacc-account-eu", "EU", "eu-central-1", "eu"),
        ("eu", "edge", "edge-rediacc-account-eu", "EU", "eu-central-1", "eu"),
        ("us", "stable", "rediacc-account-us", "US", "us-east-1", ""),
        ("asia", "edge", "edge-rediacc-account-asia", "ASIA", "eu-central-1", ""),
    ],
)
def test_derive_reads_regions_json(region, target, worker, suffix, ses, jur):
    d = local.derive(region, target)
    assert d["WORKER_NAME"] == worker
    assert d["SUFFIX"] == suffix
    assert d["AWS_SES_REGION"] == ses
    assert d["R2_JURISDICTION"] == jur
    assert d["TARGET"] == target
    assert d["BACKUP_BUCKET_STABLE"].startswith("rediacc-backups-")
    assert d["BACKUP_BUCKET_EDGE"].startswith("edge-rediacc-backups-")


def test_derive_refuses_an_unknown_region():
    with pytest.raises(local.RefusalError):
        local.derive("mars", "stable")


def test_every_region_and_channel_has_a_profile_binding_its_suffix():
    for region, suffix in (("eu", "EU"), ("us", "US"), ("asia", "ASIA")):
        for target in ("stable", "edge"):
            names = local.profile_store_names(local.profile_name(region, target))
            for prefix in (
                "AWS_SES_ACCESS_KEY_ID",
                "AWS_SES_SECRET_ACCESS_KEY",
                "OBS_OTLP_CREDENTIALS",
            ):
                assert "%s_%s" % (prefix, suffix) in names
            assert ("STRIPE_WEBHOOK_SECRET_" + suffix in names) == (target == "stable")
            own = target.upper()
            other = "EDGE" if target == "stable" else "STABLE"
            assert "ACCOUNT_BACKUP_S3_ACCESS_KEY_ID_" + own in names
            assert "ACCOUNT_BACKUP_S3_ACCESS_KEY_ID_" + other not in names


def test_profile_binds_every_variable_the_push_reads():
    """Every non-computed source the push reads, plus the fan-ins, is bound by the profile."""
    for target in ("stable", "edge"):
        names = set(local.profile_store_names(local.profile_name("eu", target)))
        read = {source for _k, _v, source in pusher.KEYS if source}
        if target == "edge":
            read.discard("STRIPE_SECRET_KEY")
        read.discard("AWS_SES_REGION")  # from regions.json, not the store
        assert read <= names, sorted(read - names)


@pytest.mark.parametrize("target", ["stable", "edge"])
def test_dry_run_prints_the_29_names_and_no_value(target, capsys):
    rc = local.run(["--region", "eu", "--target", target, "--dry-run"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "29 Worker key(s) pushed:" in out
    for key, _v, _s in pusher.KEYS:
        assert "  %s\n" % key in out
    assert "rediacc-backups-eu" in out


def test_usage_errors_exit_2(capsys):
    assert local.run(["--region", "eu"]) == 2
    assert local.run(["--region", "eu", "--target", "prod"]) == 2
    assert "usage" in capsys.readouterr().err


def _recorder(sink: list):
    def push(env: dict[str, str]) -> int:
        sink.append(env)
        return 0

    return push


def _env_ok():
    return dict(td._ENV)


def test_planted_drift_refuses_before_any_push(monkeypatch, capsys):
    monkeypatch.setattr(wrangler_pin, "check", lambda _root: (0, []))
    pushed: list[object] = []
    env = {**td._ENV, "CLOUDFLARE_TURNSTILE_SECRET_KEY": "0xSTALE-BITWARDEN-VALUE"}
    rc = local.run(
        ["--region", "eu", "--target", "stable"],
        hydrate_fn=lambda _p: env,
        fetch=td.fake_fetch(td._live(), {td._SITEKEY: td._PLANT_WIDGET_VALUE}),
        push_fn=_recorder(pushed),
    )
    err = capsys.readouterr().err
    assert rc == 1
    assert pushed == []
    assert "Turnstile drift preflight failed" in err
    assert "0xSTALE-BITWARDEN-VALUE" not in err


def test_matching_widget_pushes_with_the_derived_environment(monkeypatch):
    monkeypatch.setattr(wrangler_pin, "check", lambda _root: (0, []))
    pushed: list[dict[str, str]] = []
    rc = local.run(
        ["--region", "eu", "--target", "edge"],
        hydrate_fn=lambda _p: _env_ok(),
        fetch=td.fake_fetch(td._live(), {td._SITEKEY: td._PLANT_WIDGET_VALUE}),
        push_fn=_recorder(pushed),
    )
    assert rc == 0
    assert pushed[0]["WORKER_NAME"] == "edge-rediacc-account-eu"
    assert pushed[0]["TARGET"] == "edge"


def test_a_pin_mismatch_refuses_before_hydration(monkeypatch, capsys):
    monkeypatch.setattr(wrangler_pin, "check", lambda _root: (1, ["pin mismatch"]))

    def boom(_p):
        raise AssertionError("hydrated despite a pin mismatch")

    rc = local.run(["--region", "eu", "--target", "stable"], hydrate_fn=boom)
    assert rc == 1
    assert "pin mismatch" in capsys.readouterr().err


# ---- prune ---------------------------------------------------------------------------


class _Api:
    def __init__(self, live: dict[str, list[dict[str, str]]]) -> None:
        self.live = live
        self.calls: list[tuple[str, str]] = []

    def __call__(self, method: str, path: str, token: str) -> object:
        assert token == "tok"
        self.calls.append((method, path))
        worker = path.split("/scripts/")[1].split("/", maxsplit=1)[0]
        if method == "GET":
            return self.live[worker]
        return {}


def _names(*names: str) -> list[dict[str, str]]:
    return [{"name": n, "type": "secret_text"} for n in names]


ENV = {"CLOUDFLARE_API_TOKEN": "tok", "CLOUDFLARE_ACCOUNT_ID": "acct"}


def test_prune_dry_run_lists_extras_and_deletes_nothing():
    pushed = prune.expected_names()
    api = _Api({"rediacc-account-eu": _names(*pushed, "OLD_NAME")})
    rc, lines, rows = prune.run(["--region", "eu", "--target", "stable"], ENV, api)
    assert rc == 1
    assert rows[0].extras == ["OLD_NAME"]
    assert "extras: OLD_NAME" in "\n".join(lines)
    assert {m for m, _p in api.calls} == {"GET"}


def test_prune_reports_nothing_when_live_equals_pushed():
    api = _Api({"rediacc-account-eu": _names(*prune.expected_names())})
    rc, lines, _rows = prune.run(["--region", "eu", "--target", "stable"], ENV, api)
    assert rc == 0
    assert "extras: none" in lines[0]


def test_prune_ignores_non_secret_text_bindings():
    live = [*_names(*prune.expected_names()), {"name": "SIGNING", "type": "secret_key"}]
    api = _Api({"rediacc-account-eu": live})
    rc, _l, _r = prune.run(["--region", "eu", "--target", "stable"], ENV, api)
    assert rc == 0


def test_prune_delete_goes_through_the_secrets_endpoint():
    api = _Api({"rediacc-account-eu": _names(*prune.expected_names(), "OLD/NAME")})
    rc, _l, _r = prune.run(["--region", "eu", "--target", "stable", "--delete"], ENV, api)
    assert rc == 0
    deletes = [p for m, p in api.calls if m == "DELETE"]
    assert deletes == ["/accounts/acct/workers/scripts/rediacc-account-eu/secrets/OLD%2FNAME"]


def test_prune_without_credentials_gives_no_verdict():
    rc, lines, _r = prune.run(["--region", "eu"], {}, _Api({}))
    assert rc == 2
    assert "no verdict" in lines[0]


def test_prune_api_failure_fails_closed():
    def fail(*_a):
        raise prune.ApiError("HTTP 403")

    rc, lines, _r = prune.run(["--region", "eu"], ENV, fail)
    assert rc == 2
    assert "failing closed" in lines[0]


def test_prune_rejects_unknown_arguments():
    rc, _l, _r = prune.run(["--bogus"], ENV, _Api({}))
    assert rc == 2
