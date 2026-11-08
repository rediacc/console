"""`rediacc_ci.ops.enterprise_lookup`: the key matches an independent HMAC, free-mail and malformed input are refused, and `put`/`delete` call wrangler with the namespace and the hashed key only."""

from __future__ import annotations

import hashlib
import hmac

import pytest

from rediacc_ci.ops import enterprise_lookup as el

PEPPER = "pepper-for-tests"


@pytest.fixture(autouse=True)
def pepper(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(el.PEPPER_ENV, PEPPER)


class Recorder:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def __call__(self, argv: list[str], _env: dict[str, str]) -> int:
        self.calls.append(argv)
        return 0


def test_key_is_the_independent_hmac() -> None:
    want = hmac.new(PEPPER.encode(), b"acme.example", hashlib.sha256).hexdigest()
    assert el.lookup_key(PEPPER, "acme.example") == want


def test_normalize_matches_the_worker() -> None:
    assert el.normalize_domain(" Acme.Example. ") == "acme.example"
    assert el.normalize_domain("bücher.example") == "xn--bcher-kva.example"
    for bad in ("localhost", "a@acme.example", "-a.example", ""):
        with pytest.raises(el.LookupRefusedError):
            el.normalize_domain(bad)


def test_put_writes_the_hashed_key_and_the_host() -> None:
    run = Recorder()
    assert el.put("Acme.example", "acme.rediacc.cloud", "NS", run) == 0
    key = el.lookup_key(PEPPER, "acme.example")
    assert run.calls == [
        ["kv", "key", "put", key, "acme.rediacc.cloud", "--namespace-id", "NS", "--remote"]
    ]
    assert "acme.example" not in " ".join(run.calls[0])


def test_put_refuses_free_mail_and_its_subdomains() -> None:
    run = Recorder()
    for domain in ("gmail.com", "GMAIL.com", "mail.gmail.com"):
        with pytest.raises(el.LookupRefusedError, match="free-mail"):
            el.put(domain, "x.rediacc.cloud", "NS", run)
    assert run.calls == []


def test_put_refuses_a_bad_host() -> None:
    with pytest.raises(el.LookupRefusedError, match="host"):
        el.put("acme.example", "not a host", "NS", Recorder())


def test_delete_uses_the_same_key() -> None:
    run = Recorder()
    assert el.delete("acme.example", "NS", run) == 0
    assert run.calls == [
        [
            "kv",
            "key",
            "delete",
            el.lookup_key(PEPPER, "acme.example"),
            "--namespace-id",
            "NS",
            "--remote",
        ]
    ]


def test_missing_pepper_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(el.PEPPER_ENV)
    with pytest.raises(el.LookupRefusedError, match=el.PEPPER_ENV):
        el.delete("acme.example", "NS", Recorder())


def test_main_exit_codes(capsys: pytest.CaptureFixture[str]) -> None:
    run = Recorder()
    assert el.main(["put", "gmail.com", "x.rediacc.cloud"], run) == 1
    assert "free-mail" in capsys.readouterr().err
    assert el.main(["bogus"], run) == 2
    assert el.main(["put", "acme.example", "acme.rediacc.cloud", "--namespace-id", "N2"], run) == 0
    assert "N2" in run.calls[0]
    assert el.main(["key", "acme.example"], run) == 0
    assert capsys.readouterr().out.strip() == el.lookup_key(PEPPER, "acme.example")
    assert len(run.calls) == 1


def test_the_free_mail_list_is_lowercase_and_unique() -> None:
    data = sorted(el.free_mail_domains())
    assert all(d == d.lower() and "." in d for d in data)
    assert "gmail.com" in data
