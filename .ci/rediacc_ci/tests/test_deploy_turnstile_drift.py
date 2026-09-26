"""`rediacc_ci.deploy.turnstile_drift`: exit codes, the no-value rule, and that its own controls can go red.

Nothing here reaches Cloudflare. Every case drives `main()` with an injected env and the module's own `fake_fetch`, which is the same seam the gate's `--selftest` uses, and captures BOTH streams so a value on either one fails the no-value assertion.
"""

from __future__ import annotations

import pytest

from rediacc_ci.deploy import turnstile_drift as td

PLANTED = (
    td._SITEKEY,
    td._PLANT_WIDGET_VALUE,
    td._ENV["CLOUDFLARE_API_TOKEN"],
    td._ENV["CLOUDFLARE_ACCOUNT_ID"],
)


def _ok_fetch():
    return td.fake_fetch(td._live(), {td._SITEKEY: td._PLANT_WIDGET_VALUE})


def _run(capsys, env, fetch, argv=()):
    rc = td.main(list(argv), env=env, fetch=fetch)
    out, err = capsys.readouterr()
    return rc, out, err


def _no_value(out, err):
    for v in PLANTED:
        assert v not in out, "a planted value reached stdout"
        assert v not in err, "a planted value reached stderr"


def test_selftest_passes_and_says_how_many_controls_ran(capsys):
    rc, out, err = _run(capsys, td._ENV, _ok_fetch(), ["--selftest"])
    assert rc == 0, err
    assert "%d controls ran" % len(td.controls()) in out
    assert len(td.controls()) >= 12


def test_match_passes(capsys):
    rc, out, err = _run(capsys, td._ENV, _ok_fetch())
    assert rc == 0, err
    assert "holds TURNSTILE_SITE_KEY and CLOUDFLARE_TURNSTILE_SECRET_KEY" in out
    _no_value(out, err)


def test_secret_mismatch_fails_and_names_rotation(capsys):
    env = {**td._ENV, "CLOUDFLARE_TURNSTILE_SECRET_KEY": "0xSTALE-BITWARDEN-VALUE"}
    rc, out, err = _run(capsys, env, _ok_fetch())
    assert rc == 1
    assert "CLOUDFLARE_TURNSTILE_SECRET_KEY does not equal" in err
    assert td.FIX in err
    assert "0xSTALE-BITWARDEN-VALUE" not in out + err
    _no_value(out, err)


def test_sitekey_mismatch_fails_and_names_its_own_fix(capsys):
    env = {**td._ENV, "TURNSTILE_SITE_KEY": "0xSTALE-SITEKEY"}
    rc, out, err = _run(capsys, env, _ok_fetch())
    assert rc == 1
    assert "TURNSTILE_SITE_KEY does not equal" in err
    assert "set Bitwarden TURNSTILE_SITE_KEY" in err
    assert "0xSTALE-SITEKEY" not in out + err
    _no_value(out, err)


@pytest.mark.parametrize(
    ("env", "fetch"),
    [
        (
            td._ENV,
            td.fake_fetch(td._live(), {td._SITEKEY: td._PLANT_WIDGET_VALUE}, fail="/widgets/"),
        ),
        (
            td._ENV,
            td.fake_fetch(td._live(), {td._SITEKEY: td._PLANT_WIDGET_VALUE}, fail="widgets?"),
        ),
        ({**td._ENV, "CLOUDFLARE_API_TOKEN": "wrong"}, None),
        ({k: v for k, v in td._ENV.items() if k != "CLOUDFLARE_ACCOUNT_ID"}, None),
        (td._ENV, td.fake_fetch(td._live(), {td._SITEKEY: None})),
        (td._ENV, td.fake_fetch([], {})),
    ],
    ids=[
        "widget-get-error",
        "list-error",
        "bad-token",
        "missing-var",
        "no-secret-field",
        "zero-widgets",
    ],
)
def test_no_verdict_fails_closed_with_2(capsys, env, fetch):
    rc, out, err = _run(capsys, env, fetch or _ok_fetch())
    assert rc == 2
    _no_value(out, err)


def test_missing_secret_field_names_the_token_scope(capsys):
    rc, _, err = _run(capsys, td._ENV, td.fake_fetch(td._live(), {td._SITEKEY: None}))
    assert rc == 2
    assert "Turnstile Sites Write" in err


def test_a_crash_is_2_not_python_default_1(capsys):
    def boom(_path, _token):
        raise KeyError(td._PLANT_WIDGET_VALUE)

    rc, out, err = _run(capsys, td._ENV, boom)
    assert rc == 2
    assert "KeyError" in err
    _no_value(out, err)


def test_label_redacts_account_and_sitekey():
    got = td.label("/accounts/abc123/challenges/widgets/0xKEY?page=2")
    assert got == "/accounts/{account_id}/challenges/widgets/{sitekey}"


# ---- the controls can fail ---------------------------------------------------------


def test_selftest_goes_red_when_the_secret_is_never_compared(monkeypatch, capsys):
    real = td.hmac.compare_digest
    monkeypatch.setattr(td.hmac, "compare_digest", lambda _a, _b: True)
    assert td.selftest() is True
    monkeypatch.setattr(td.hmac, "compare_digest", real)
    assert td.selftest() is False
    capsys.readouterr()


def test_selftest_goes_red_when_errors_carry_the_raw_path(monkeypatch, capsys):
    monkeypatch.setattr(td, "label", lambda path: path)
    assert td.selftest() is True
    capsys.readouterr()


def test_selftest_goes_red_when_only_the_first_page_is_read(monkeypatch, capsys):
    monkeypatch.setattr(td, "MAX_PAGES", 1)
    assert td.selftest() is True
    capsys.readouterr()


def test_a_failed_control_refuses_with_2_before_any_live_call(monkeypatch, capsys):
    monkeypatch.setattr(td.hmac, "compare_digest", lambda _a, _b: True)

    def must_not_run(_path, _token):
        raise AssertionError("the live fetch ran after a failed control")

    rc, _, err = _run(capsys, td._ENV, must_not_run)
    assert rc == 2
    assert "instrument control failed" in err
