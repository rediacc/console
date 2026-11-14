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


def _regions_row(region):
    doc = json.loads(local.paths.repo_root().joinpath("regions.json").read_text(encoding="utf-8"))
    return next(r for r in doc["regions"] if r["id"] == region)


@pytest.mark.parametrize(
    ("region", "suffix", "ses", "jur", "worker"),
    [
        ("eu", "EU", "eu-central-1", "eu", "account-eu"),
        ("us", "US", "us-east-1", "", "account-us"),
        ("asia", "ASIA", "eu-central-1", "", "account-asia"),
    ],
)
def test_derive_reads_regions_json(region, suffix, ses, jur, worker):
    d = local.derive(region)
    row = _regions_row(region)
    # The Worker name is pinned literally as well as against the row, so a wrong workerName in regions.json fails here.
    assert d["WORKER_NAME"] == worker
    assert d["WORKER_NAME"] == row["workerName"]
    assert d["SUFFIX"] == suffix
    assert d["AWS_SES_REGION"] == ses
    assert d["R2_JURISDICTION"] == jur
    # The shared Worker takes Stripe, which is the pusher's `stable` channel, and has one bucket.
    assert d["TARGET"] == "stable"
    assert d["BACKUP_BUCKET_STABLE"] == row["backupR2"]["name"]
    assert "BACKUP_BUCKET_EDGE" not in d


def test_derive_refuses_an_unknown_region():
    with pytest.raises(local.RefusalError):
        local.derive("mars")


def test_the_per_channel_profiles_are_gone():
    table = local.bws_env.profiles()
    assert sorted(p for p in table if p.startswith("account-secrets-")) == [
        "account-secrets-asia",
        "account-secrets-eu",
        "account-secrets-us",
    ]


def test_every_region_has_a_profile_binding_its_suffix_and_stripe():
    for region, suffix, key_value in (
        ("eu", "EU", "STABLE"),
        ("us", "US", "EDGE"),
        ("asia", "ASIA", "EDGE"),
    ):
        names = local.profile_store_names(local.profile_name(region))
        for prefix in (
            "AWS_SES_ACCESS_KEY_ID",
            "AWS_SES_SECRET_ACCESS_KEY",
            "OBS_OTLP_CREDENTIALS",
            "STRIPE_WEBHOOK_SECRET",
        ):
            assert "%s_%s" % (prefix, suffix) in names
        assert "STRIPE_SECRET_KEY" in names
        # One backup pair, and the old edge pair is never bound.
        assert "ACCOUNT_BACKUP_S3_ACCESS_KEY_ID_STABLE" in names
        assert "ACCOUNT_BACKUP_S3_ACCESS_KEY_ID_EDGE" not in names
        # One config server key and one KEK per region. EU takes the EU_STABLE value, because the seeded config objects were encrypted under it; US and ASIA seed from edge, so they take their edge value, bound under the `_STABLE` local name the pusher reads.
        keys = [n for n in names if n.startswith("ACCOUNT_CONFIG_SERVER_KEY")]
        keks = [n for n in names if n.startswith("ACCOUNT_BACKUP_STORE_KEK")]
        if key_value == "STABLE":
            assert keys == ["ACCOUNT_CONFIG_SERVER_KEY_EU_STABLE"]
            assert keks == ["ACCOUNT_BACKUP_STORE_KEK_EU_STABLE"]
        else:
            assert keys == ["ACCOUNT_CONFIG_SERVER_KEY_%s_EDGE" % suffix]
            assert keks == ["ACCOUNT_BACKUP_STORE_KEK_%s_EDGE" % suffix]


@pytest.mark.parametrize("region", ["eu", "us", "asia"])
def test_profile_binds_every_variable_the_push_reads(region):
    """Every non-computed source the push reads, plus the fan-ins, is bound by the profile."""
    names = set(local.profile_store_names(local.profile_name(region)))
    read = {source for _k, _v, source in pusher.KEYS if source}
    read.discard("AWS_SES_REGION")  # from regions.json, not the store
    assert read <= names, sorted(read - names)


def test_dry_run_prints_every_pushed_name_and_no_value(capsys, monkeypatch):
    # The pin reads workers/account/node_modules, which the quality-pytest job does not install; this case is about the names, and the refusal has its own case.
    monkeypatch.setattr(local.wrangler_pin, "check", lambda _root: (0, []))
    rc = local.run(["--region", "eu", "--dry-run"])
    out = capsys.readouterr().out
    assert rc == 0
    # The count follows the pusher's own list (a hard-coded one went stale when ACCOUNT_AE_READ_TOKEN and CLOUDFLARE_ACCOUNT_ID joined it).
    assert "%d Worker key(s) pushed:" % len(pusher.KEYS) in out
    assert "  ACCOUNT_CONFIG_SERVER_KEY\n" in out
    assert "  ACCOUNT_BACKUP_STORE_KEK\n" in out
    assert "  FREE_LICENSE_HMAC_KEY\n" in out
    for key, _v, _s in pusher.KEYS:
        assert "  %s\n" % key in out
    assert _regions_row("eu")["backupR2"]["name"] in out


def test_usage_errors_exit_2(capsys):
    assert local.run([]) == 2
    assert local.run(["--region", "eu", "--target", "stable"]) == 2
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
        ["--region", "eu"],
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
        ["--region", "eu"],
        hydrate_fn=lambda _p: _env_ok(),
        fetch=td.fake_fetch(td._live(), {td._SITEKEY: td._PLANT_WIDGET_VALUE}),
        push_fn=_recorder(pushed),
    )
    assert rc == 0
    assert pushed[0]["WORKER_NAME"] == _regions_row("eu")["workerName"]
    assert pushed[0]["TARGET"] == "stable"


def test_a_pin_mismatch_refuses_before_hydration(monkeypatch, capsys):
    monkeypatch.setattr(wrangler_pin, "check", lambda _root: (1, ["pin mismatch"]))

    def boom(_p):
        raise AssertionError("hydrated despite a pin mismatch")

    rc = local.run(["--region", "eu"], hydrate_fn=boom)
    assert rc == 1
    assert "pin mismatch" in capsys.readouterr().err


# ---- prune ---------------------------------------------------------------------------


class _Api:
    def __init__(self, live: dict[str, list[dict[str, str]]]) -> None:
        self.live = live
        self.calls: list[tuple[str, str]] = []
        self.bodies: list[dict[str, str]] = []

    def __call__(
        self, method: str, path: str, token: str, body: dict[str, str] | None = None
    ) -> object:
        assert token == "tok"
        self.calls.append((method, path))
        worker = path.split("/scripts/")[1].split("/", maxsplit=1)[0]
        if body is not None:
            self.bodies.append(body)
            self.live[worker] = [*self.live[worker], {"name": body["name"], "type": "secret_text"}]
        if method == "GET":
            return self.live[worker]
        return {}


def _names(*names: str) -> list[dict[str, str]]:
    return [{"name": n, "type": "secret_text"} for n in names]


ENV = {"CLOUDFLARE_API_TOKEN": "tok", "CLOUDFLARE_ACCOUNT_ID": "acct"}


def test_prune_dry_run_lists_extras_and_deletes_nothing():
    pushed = prune.expected_names()
    api = _Api({"account-eu": _names(*pushed, "OLD_NAME")})
    rc, lines, rows = prune.run(["--region", "eu"], ENV, api)
    assert rc == 1
    assert rows[0].extras == ["OLD_NAME"]
    assert "extras: OLD_NAME" in "\n".join(lines)
    assert {m for m, _p in api.calls} == {"GET"}


def test_prune_reports_nothing_when_live_equals_pushed():
    api = _Api({"account-eu": _names(*prune.expected_names())})
    rc, lines, _rows = prune.run(["--region", "eu"], ENV, api)
    assert rc == 0
    assert "extras: none" in lines[0]


def test_prune_ignores_non_secret_text_bindings():
    live = [*_names(*prune.expected_names()), {"name": "SIGNING", "type": "secret_key"}]
    api = _Api({"account-eu": live})
    rc, _l, _r = prune.run(["--region", "eu"], ENV, api)
    assert rc == 0


def test_prune_delete_goes_through_the_secrets_endpoint():
    api = _Api({"account-eu": _names(*prune.expected_names(), "OLD/NAME")})
    rc, lines, _r = prune.run(["--region", "eu", "--delete"], ENV, api)
    assert rc == 0
    deletes = [p for m, p in api.calls if m == "DELETE"]
    assert deletes == ["/accounts/acct/workers/scripts/account-eu/secrets/OLD%2FNAME"]
    assert "deleted account-eu: OLD/NAME" in lines


def test_prune_delete_without_a_region_deletes_nothing():
    api = _Api({"account-eu": _names(*prune.expected_names(), "OLD/NAME")})
    rc, lines, _r = prune.run(["--delete"], ENV, api)
    assert rc == 2
    assert api.calls == []
    assert any("--delete needs --region" in line for line in lines)


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


SECRET_VALUE = "s3cr3t-value-never-printed"


def _bws(have: dict[str, str]):
    return lambda keys: {k: have[k] for k in keys if k in have}


def _archive(api, have, *extra):
    return prune.run(
        ["--region", "eu", "--archive", *extra],
        ENV,
        api,
        values=_bws(have),
    )


def test_prune_archive_puts_then_confirms_then_deletes():
    api = _Api({"account-eu": _names(*prune.expected_names(), "API_KEY")})
    rc, lines, _r = _archive(api, {"ACCOUNT_SERVER_API_KEY": SECRET_VALUE})
    assert rc == 0
    assert [m for m, _p in api.calls] == ["GET", "GET", "PUT", "GET", "DELETE"]
    assert api.bodies == [
        {"name": "__ARCHIVE_API_KEY", "text": SECRET_VALUE, "type": "secret_text"}
    ]
    assert api.calls[-1][1].endswith("/secrets/API_KEY")
    assert "archived account-eu: API_KEY as __ARCHIVE_API_KEY (from the bws value)" in lines


def test_prune_archive_never_overwrites_an_existing_archive():
    live = _names(*prune.expected_names(), "API_KEY", "__ARCHIVE_API_KEY")
    api = _Api({"account-eu": live})
    rc, lines, _r = _archive(api, {"ACCOUNT_SERVER_API_KEY": SECRET_VALUE})
    assert rc == 1
    assert {m for m, _p in api.calls} == {"GET"}
    assert any("__ARCHIVE_API_KEY already exists" in line for line in lines)


def test_prune_archive_refuses_to_write_on_a_non_list_listing():
    api = _Api({"account-eu": _names(*prune.expected_names(), "API_KEY")})
    gets = 0

    def fetch(method, path, token, body=None):
        nonlocal gets
        if method == "GET":
            gets += 1
            if gets == 2:
                return {"unexpected": True}
        return api(method, path, token, body)

    rc, lines, _r = prune.run(
        ["--region", "eu", "--archive"],
        ENV,
        fetch,
        values=_bws({"ACCOUNT_SERVER_API_KEY": SECRET_VALUE}),
    )
    assert rc == 1
    assert {m for m, _p in api.calls} == {"GET"}
    assert any("is not a list; __ARCHIVE_API_KEY not written" in line for line in lines)


def test_prune_delete_with_dry_run_deletes_nothing():
    api = _Api({"account-eu": _names(*prune.expected_names(), "OLD_NAME")})
    rc, lines, _r = prune.run(["--region", "eu", "--delete", "--dry-run"], ENV, api)
    assert rc == 2
    assert api.calls == []
    assert any("--dry-run applies to --archive only" in line for line in lines)


def test_prune_archive_leaves_a_name_without_a_bws_value():
    api = _Api({"account-eu": _names(*prune.expected_names(), "API_KEY", "ODD_NAME")})
    rc, lines, _r = _archive(api, {})
    assert rc == 1
    assert {m for m, _p in api.calls} == {"GET"}
    text = "\n".join(lines)
    assert "no recoverable copy, left in place: account-eu: API_KEY" in text
    assert "ODD_NAME (bws key: unmapped)" in text


def test_prune_archive_uses_the_region_suffix_for_otlp():
    api = _Api({"account-eu": _names(*prune.expected_names(), "OTLP_CLIENT_CREDENTIALS")})
    rc, _l, _r = _archive(
        api, {"OBS_OTLP_CREDENTIALS_EU": SECRET_VALUE, "OBS_OTLP_CREDENTIALS_US": "x"}
    )
    assert rc == 0
    assert api.bodies[0]["text"] == SECRET_VALUE


def test_prune_archive_names_are_not_extras():
    live = _names(*prune.expected_names(), "__ARCHIVE_API_KEY")
    api = _Api({"account-eu": live})
    rc, lines, rows = _archive(api, {})
    assert rc == 0
    assert rows[0].extras == []
    assert "extras: none" in lines[0]


def test_prune_archive_never_prints_the_value():
    api = _Api({"account-eu": _names(*prune.expected_names(), "API_KEY")})
    _rc, lines, _r = _archive(api, {"ACCOUNT_SERVER_API_KEY": SECRET_VALUE})
    assert SECRET_VALUE not in "\n".join(lines)
    _rc, lines, _r = _archive(api, {"ACCOUNT_SERVER_API_KEY": SECRET_VALUE}, "--dry-run")
    assert SECRET_VALUE not in "\n".join(lines)


def test_prune_archive_dry_run_writes_nothing():
    api = _Api({"account-eu": _names(*prune.expected_names(), "API_KEY")})
    rc, lines, _r = _archive(api, {"ACCOUNT_SERVER_API_KEY": SECRET_VALUE}, "--dry-run")
    assert rc == 1
    assert {m for m, _p in api.calls} == {"GET"}
    assert any(line.startswith("would archive") for line in lines)


def test_prune_archive_waits_for_a_listing_that_lags_the_put(monkeypatch):
    monkeypatch.setattr(prune, "LIST_PAUSE_S", 0)

    class Lagging(_Api):
        gets = 0

        def __call__(self, method, path, token, body=None):
            if method == "GET" and self.bodies:
                Lagging.gets += 1
                if Lagging.gets < 3:
                    return [
                        r for r in self.live["account-eu"] if not r["name"].startswith("__ARCHIVE_")
                    ]
            return super().__call__(method, path, token, body)

    api = Lagging({"account-eu": _names(*prune.expected_names(), "API_KEY")})
    rc, lines, _r = _archive(api, {"ACCOUNT_SERVER_API_KEY": SECRET_VALUE})
    assert rc == 0
    assert "deleted account-eu: API_KEY" in lines


def test_prune_archive_keeps_the_original_when_the_archive_is_not_listed(monkeypatch):
    monkeypatch.setattr(prune, "LIST_PAUSE_S", 0)

    class Lossy(_Api):
        def __call__(self, method, path, token, body=None):
            if body is not None:
                self.calls.append((method, path))
                return {}
            return super().__call__(method, path, token)

    api = Lossy({"account-eu": _names(*prune.expected_names(), "API_KEY")})
    rc, lines, _r = _archive(api, {"ACCOUNT_SERVER_API_KEY": SECRET_VALUE})
    assert rc == 1
    assert "DELETE" not in {m for m, _p in api.calls}
    assert any("not listed after the PUT" in line for line in lines)


def test_prune_archive_needs_a_region():
    api = _Api({})
    rc, lines, _r = prune.run(["--archive"], ENV, api, values=_bws({}))
    assert rc == 2
    assert api.calls == []
    assert any("--archive needs --region" in line for line in lines)
