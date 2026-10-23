"""The scoped mint `cf_auth.resolve_scoped` adds for the spend guard (agent/plans/PLAN-cloudflare-spend-guard.md design item 3, Rule T 8).

The bash differentials and the older Rule T deltas of `cf_auth` live in `test_ops_cf_family.py`; this file pins only the scoped mint: names resolved to ids by scope, a token carrying nothing beyond the caller's groups and the self-destruct pair, readiness awaited on the caller's own service, and no prompt. HTTP is faked at `cf_auth.curl_json`.
"""

from __future__ import annotations

import json

import pytest

from rediacc_ci.ops import cf_auth

ACCT = cf_auth.DEFAULT_ACCOUNT_ID
NOTIF_WRITE = "c3c847c5802d4ce3ba00e3e97b3c8555"
ANALYTICS_READ = "b89a480218d04ceb98b4fe57ca29dc1f"
OBS_WRITE = "82c075da3f4647a2a03becd0fe240f8a"
GROUPS = [
    {"id": NOTIF_WRITE, "name": "Notifications Write", "scopes": ["com.cloudflare.api.account"]},
    {"id": "ce18edbdcebf465e9d6d1d2fc80ffd42", "name": "Notifications Read", "scopes": ["com.cloudflare.api.account"]},
    {"id": ANALYTICS_READ, "name": "Account Analytics Read", "scopes": ["com.cloudflare.api.account"]},
    # The same display name on another scope must not be taken for the account group.
    {"id": "zone-analytics", "name": "Account Analytics Read", "scopes": ["com.cloudflare.api.account.zone"]},
    {"id": OBS_WRITE, "name": "Workers Observability Write", "scopes": ["com.cloudflare.api.account"]},
    {"id": "bf7481a1826f439697cb59a20b22293e", "name": "Workers R2 Storage Write", "scopes": ["com.cloudflare.api.account"]},
]


class FakeApi:
    """Stands in for `cf_auth.curl_json` and records every call."""

    def __init__(self, groups: list[dict] | None = None):
        self.calls: list[tuple[str, str, list[str], str | None]] = []
        self.groups = GROUPS if groups is None else groups

    def __call__(self, method, url, headers, body=None, **_curl_options):
        self.calls.append((method, url, list(headers), body))
        path = url[len(cf_auth.CF_API_BASE) :]
        if method == "GET" and path == "/user":
            return {"success": True, "result": {"id": "USER1"}}
        if method == "GET" and path == "/user/tokens/permission_groups":
            return {"success": True, "result": self.groups}
        if method == "POST" and path == "/user/tokens":
            return {"success": True, "result": {"value": "SCOPED-TOKEN"}}
        if method == "GET":
            return {"success": True, "result": {"id": "TID"}}
        return {"success": False, "errors": [{"message": "no fake route"}]}

    def minted_payload(self) -> dict:
        posts = [c for c in self.calls if c[0] == "POST" and c[1].endswith("/user/tokens")]
        assert len(posts) == 1
        body = posts[0][3]
        assert body is not None
        return json.loads(body)


def test_spend_guard_purposes_name_the_groups_the_plan_needs() -> None:
    assert cf_auth.SCOPED_GROUPS["cf-notifications"] == ("Notifications Write",)
    assert "Account Analytics Read" in cf_auth.SCOPED_GROUPS["cf-usage-report"]
    assert "Workers Observability Write" in cf_auth.SCOPED_GROUPS["observability-volume"]
    # The long-lived management token did not grow: neither group is in its fixed list.
    assert NOTIF_WRITE not in cf_auth.ACCOUNT_PERMISSION_GROUPS
    assert ANALYTICS_READ not in cf_auth.ACCOUNT_PERMISSION_GROUPS


def test_permission_groups_resolve_by_name_on_the_account_scope(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cf_auth, "curl_json", FakeApi())
    ids = cf_auth.permission_group_ids([], ["Account Analytics Read", "Notifications Write"])
    assert ids == [ANALYTICS_READ, NOTIF_WRITE]


def test_an_unknown_or_ambiguous_group_name_is_refused_by_name(monkeypatch: pytest.MonkeyPatch) -> None:
    doubled = [*GROUPS, {"id": "dup", "name": "Notifications Write", "scopes": ["com.cloudflare.api.account"]}]
    monkeypatch.setattr(cf_auth, "curl_json", FakeApi(doubled))
    with pytest.raises(cf_auth.CfAuthError) as exc:
        cf_auth.permission_group_ids([], ["Notifications Write", "No Such Group"])
    assert "Notifications Write (2 account-scoped matches)" in str(exc.value)
    assert "No Such Group (0 account-scoped matches)" in str(exc.value)


def test_the_scoped_token_carries_only_the_callers_groups(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeApi()
    monkeypatch.setattr(cf_auth, "curl_json", fake)
    auth = cf_auth.create_scoped_token("gk", "ops@example.invalid", "cf-notifications", ACCT)
    assert auth.token == "SCOPED-TOKEN"
    assert auth.created is True
    payload = fake.minted_payload()
    assert payload["name"] == "auto-scoped-cf-notifications"
    account, user = payload["policies"]
    assert account["resources"] == {"com.cloudflare.api.account.%s" % ACCT: "*"}
    assert account["permission_groups"] == [{"id": NOTIF_WRITE}]
    assert user["resources"] == {"com.cloudflare.api.user.USER1": "*"}
    assert [g["id"] for g in user["permission_groups"]] == list(cf_auth.USER_PERMISSION_GROUPS)
    assert auth.probes == [("Notifications", "/accounts/%s/alerting/v3/policies" % ACCT)]
    # The Global API Key travels as a header handed to curl_json, never in the URL or body.
    for _method, url, _headers, body in fake.calls:
        assert "gk" not in url.split("/")
        assert body is None or '"gk"' not in body


def test_an_unknown_purpose_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cf_auth, "curl_json", FakeApi())
    with pytest.raises(cf_auth.CfAuthError, match="no scoped permission set named 'nope'"):
        cf_auth.create_scoped_token("gk", "e", "nope", ACCT)


def test_a_scoped_token_is_awaited_on_its_own_service(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeApi()
    monkeypatch.setattr(cf_auth, "curl_json", fake)
    auth = cf_auth.create_scoped_token("gk", "e", "cf-notifications", ACCT)
    fake.calls.clear()
    cf_auth.await_propagation(auth, sleep=lambda _s: None)
    paths = [url[len(cf_auth.CF_API_BASE) :] for _m, url, _h, _b in fake.calls]
    want = "/accounts/%s/alerting/v3/policies" % ACCT
    assert paths == ["/user/tokens/verify"] * cf_auth.READY_CONSECUTIVE + [want] * cf_auth.READY_CONSECUTIVE


def test_resolve_scoped_prefers_a_supplied_token_and_never_prompts(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeApi()
    monkeypatch.setattr(cf_auth, "curl_json", fake)
    monkeypatch.setattr("builtins.input", lambda *_a: pytest.fail("prompted"))
    for name in ("CF_MANAGEMENT_TOKEN", "CF_GLOBAL_API_KEY", "CF_EMAIL"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(cf_auth.CfAuthError, match="credentials are required"):
        cf_auth.resolve_scoped("cf-notifications")
    monkeypatch.setenv("CF_MANAGEMENT_TOKEN", "supplied")
    auth = cf_auth.resolve_scoped("cf-notifications")
    assert (auth.token, auth.created, fake.calls) == ("supplied", False, [])
    monkeypatch.delenv("CF_MANAGEMENT_TOKEN")
    monkeypatch.setenv("CF_GLOBAL_API_KEY", "gk")
    monkeypatch.setenv("CF_EMAIL", "ops@example.invalid")
    auth = cf_auth.resolve_scoped("cf-notifications")
    assert (auth.token, auth.created) == ("SCOPED-TOKEN", True)
