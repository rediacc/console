"""`cf_notifications` against a fake Cloudflare API (agent/plans/PLAN-cloudflare-spend-guard.md T1).

A fake `curl` first on PATH keeps the account's policies in a JSON state file and records every request: method, URL, argv, body, and whether the bearer token arrived on stdin. It answers the token mint (`/user`, `/user/tokens/permission_groups`, `POST /user/tokens`), verify, the self-destruct DELETE and the alerting/v3 policy calls, refusing a policy call that does not carry the minted token and a product named in `FAKE_REFUSED` with Cloudflare's 17106.
"""

from __future__ import annotations

import json
import os
import pathlib
import sys
import types

import pytest

from rediacc_ci.ops import cf_auth, cf_notifications

ACCT = cf_auth.DEFAULT_ACCOUNT_ID
GLOBAL_KEY = "GLOBAL-KEY-SECRET"
MINTED = "MINTED-TOKEN-SECRET"
POLICIES = "/accounts/%s/alerting/v3/policies" % ACCT

FAKE_CURL = r"""#!{py}
import ast, json, os, sys
argv = sys.argv[1:]
config = sys.stdin.read() if "-K" in argv else ""
headers = [ast.literal_eval(l.split("=", 1)[1].strip()) for l in config.splitlines() if l.startswith("header")]
method = argv[argv.index("-X") + 1]
url = next(a for a in argv if a.startswith("http"))
body = argv[argv.index("-d") + 1] if "-d" in argv else None
state_path = os.environ["FAKE_STATE"]
state = json.load(open(state_path))
state["calls"].append({{"method": method, "url": url, "argv": argv, "body": body, "stdin_headers": headers}})
path = url.split("/client/v4", 1)[1]
policies = "/accounts/{acct}/alerting/v3/policies"
def answer(obj):
    json.dump(state, open(state_path, "w"))
    sys.stdout.write(json.dumps(obj))
    sys.exit(0)
bearer = "Authorization: Bearer {minted}" in headers
if path == "/user" and method == "GET":
    answer({{"success": True, "result": {{"id": "USER1"}}}})
if path == "/user/tokens/permission_groups":
    answer({{"success": True, "result": [{{"id": "NW", "name": "Notifications Write", "scopes": ["com.cloudflare.api.account"]}}]}})
if path == "/user/tokens" and method == "POST":
    state["minted"] += 1
    answer({{"success": True, "result": {{"value": "{minted}"}}}})
if path == "/user/tokens/verify":
    answer({{"success": bearer, "result": {{"id": "TID"}}}})
if path == "/user/tokens/TID" and method == "DELETE":
    state["destroyed"] += 1
    answer({{"success": bearer}})
if path.startswith(policies):
    if not bearer:
        answer({{"success": False, "errors": [{{"code": 10000, "message": "Authentication error"}}]}})
    if method == "GET":
        answer({{"success": True, "result": state["policies"]}})
    pid = path[len(policies) + 1:]
    if method in ("POST", "PUT"):
        doc = json.loads(body)
        if doc["filters"]["product"][0] in os.environ.get("FAKE_REFUSED", "").split(","):
            answer({{"success": False, "errors": [{{"code": 17106, "message": "Error 17106: Invalid product selection."}}]}})
        if method == "POST":
            state["next"] += 1
            doc["id"] = "pol%d" % state["next"]
            state["policies"].append(doc)
        else:
            doc["id"] = pid
            state["policies"] = [doc if p["id"] == pid else p for p in state["policies"]]
        answer({{"success": True, "result": {{"id": doc["id"]}}}})
    if method == "DELETE":
        state["policies"] = [p for p in state["policies"] if p["id"] != pid]
        answer({{"success": True, "result": {{"id": pid}}}})
answer({{"success": False, "errors": [{{"message": "no fake route"}}]}})
"""

BUDGET = {
    "id": "budget1",
    "name": "Default budget alert (auto-created)",
    "alert_type": "billing_budget_alert",
    "enabled": True,
    "mechanisms": {"email": [{"id": "ops@example.invalid"}]},
    "filters": {"total_spend_dollars": ["10"]},
}


class Cf:
    def __init__(self, tmp: pathlib.Path, monkeypatch: pytest.MonkeyPatch):
        self.state = tmp / "state.json"
        self.state.write_text(
            json.dumps({"calls": [], "policies": [BUDGET], "next": 0, "minted": 0, "destroyed": 0})
        )
        self.config = tmp / "cf-spend-guard.json"
        self.write_config(
            {
                "worker_requests": 20000000,
                "r2_storage": 50000000000,
                "r2_class_a_operations": 2000000,
            }
        )
        bindir = tmp / "bin"
        bindir.mkdir()
        curl = bindir / "curl"
        curl.write_text(FAKE_CURL.format(py=sys.executable, acct=ACCT, minted=MINTED))
        curl.chmod(0o755)
        monkeypatch.setenv("PATH", "%s%s%s" % (bindir, os.pathsep, os.environ.get("PATH", "")))
        monkeypatch.setenv("FAKE_STATE", str(self.state))
        monkeypatch.delenv("CF_MANAGEMENT_TOKEN", raising=False)
        monkeypatch.setenv("CF_GLOBAL_API_KEY", GLOBAL_KEY)
        monkeypatch.setenv("CF_EMAIL", "ops@example.invalid")

    def write_config(self, limits: dict[str, int], unavailable: dict | None = None) -> None:
        products = {p: {"limit": v, "unit": "units"} for p, v in limits.items()}
        section = {
            "policy_prefix": "spend-guard:",
            "products": products,
            "unavailable": unavailable or {},
        }
        self.config.write_text(json.dumps({"notifications": section}))

    def read(self) -> dict:
        return json.loads(self.state.read_text())

    def policy_writes(self) -> list[tuple[str, str]]:
        return [
            (c["method"], c["url"].split(POLICIES, 1)[1])
            for c in self.read()["calls"]
            if POLICIES in c["url"] and c["method"] != "GET"
        ]

    def run(self, capsys: pytest.CaptureFixture[str], *args: str) -> tuple[int, str, str]:
        state = self.read()
        state["calls"] = []
        self.state.write_text(json.dumps(state))
        rc = cf_notifications.main(["--config", str(self.config), *args])
        out, err = capsys.readouterr()
        return rc, out, err


@pytest.fixture
def cf(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> Cf:
    return Cf(tmp_path, monkeypatch)


def _assert_no_secret_leaked(cf: Cf, out: str, err: str) -> None:
    for secret in (MINTED, GLOBAL_KEY):
        assert secret not in out
        assert secret not in err
        for call in cf.read()["calls"]:
            assert not any(secret in a for a in call["argv"]), call["argv"]


def test_first_run_creates_every_policy_and_destroys_its_token(
    cf: Cf, capsys: pytest.CaptureFixture[str]
) -> None:
    rc, out, err = cf.run(capsys)
    assert rc == 0, err
    assert sorted(cf.policy_writes()) == [("POST", "")] * 3
    names = {p["name"]: p for p in cf.read()["policies"]}
    assert set(names) == {
        BUDGET["name"],
        "spend-guard:worker_requests",
        "spend-guard:r2_storage",
        "spend-guard:r2_class_a_operations",
    }
    r2 = names["spend-guard:r2_storage"]
    assert r2["alert_type"] == "billing_usage_alert"
    assert r2["filters"] == {"product": ["r2_storage"], "limit": ["50000000000"]}
    assert r2["mechanisms"] == {"email": [{"id": cf_notifications.OPERATOR_EMAIL}]}
    assert "CREATE spend-guard:r2_storage id=pol" in out
    assert "BUDGET Default budget alert (auto-created) id=budget1" in out
    assert out.rstrip().endswith("3 change(s)")
    state = cf.read()
    assert (state["minted"], state["destroyed"]) == (1, 1)
    _assert_no_secret_leaked(cf, out, err)


def test_second_run_changes_nothing(cf: Cf, capsys: pytest.CaptureFixture[str]) -> None:
    assert cf.run(capsys)[0] == 0
    rc, out, err = cf.run(capsys)
    assert rc == 0, err
    assert cf.policy_writes() == []
    assert out.count("UNCHANGED spend-guard:") == 3
    assert out.rstrip().endswith("0 change(s)")
    _assert_no_secret_leaked(cf, out, err)


def test_a_changed_limit_puts_exactly_that_policy(
    cf: Cf, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cf.run(capsys)[0] == 0
    target = next(p["id"] for p in cf.read()["policies"] if p["name"] == "spend-guard:r2_storage")
    cf.write_config(
        {"worker_requests": 20000000, "r2_storage": 60000000000, "r2_class_a_operations": 2000000}
    )
    rc, out, _err = cf.run(capsys)
    assert rc == 0
    assert cf.policy_writes() == [("PUT", "/" + target)]
    assert "limit ['50000000000'] -> ['60000000000']" in out
    assert out.rstrip().endswith("1 change(s)")


def test_an_unavailable_product_is_named_and_fails_the_run(
    cf: Cf, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FAKE_REFUSED", "r2_storage")
    rc, out, _err = cf.run(capsys)
    assert rc == 1
    assert "UNAVAILABLE r2_storage (Cloudflare: Error 17106: Invalid product selection.)" in out
    # The other products still land; the refused one is not retried.
    assert sorted(cf.policy_writes()) == [("POST", "")] * 3
    assert "spend-guard:r2_storage" not in {p["name"] for p in cf.read()["policies"]}


def test_a_recorded_unavailable_product_is_reported_without_failing(
    cf: Cf, capsys: pytest.CaptureFixture[str]
) -> None:
    cf.write_config({"worker_requests": 1}, {"containers": {"fallback": "the budget alert"}})
    rc, out, _err = cf.run(capsys)
    assert rc == 0
    assert (
        "UNAVAILABLE containers (recorded in .ci/config/cf-spend-guard.json; fallback: the budget alert)"
        in out
    )


def test_dry_run_writes_nothing(cf: Cf, capsys: pytest.CaptureFixture[str]) -> None:
    rc, out, _err = cf.run(capsys, "--dry-run")
    assert rc == 0
    assert cf.policy_writes() == []
    assert "CREATE spend-guard:worker_requests limit=20000000 (dry run)" in out
    assert out.rstrip().endswith("3 change(s) planned (dry run)")


def test_a_policy_dropped_from_the_config_is_deleted_and_others_are_left_alone(
    cf: Cf, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cf.run(capsys)[0] == 0
    gone = next(
        p["id"] for p in cf.read()["policies"] if p["name"] == "spend-guard:r2_class_a_operations"
    )
    cf.write_config({"worker_requests": 20000000, "r2_storage": 50000000000})
    rc, out, _err = cf.run(capsys)
    assert rc == 0
    assert cf.policy_writes() == [("DELETE", "/" + gone)]
    assert "DELETE spend-guard:r2_class_a_operations id=%s" % gone in out
    assert BUDGET["name"] in {p["name"] for p in cf.read()["policies"]}


def test_the_repo_config_loads_and_names_positive_limits() -> None:
    section = cf_notifications.load_config(
        pathlib.Path(__file__).resolve().parents[2] / "config" / "cf-spend-guard.json"
    )
    want = cf_notifications.desired_policies(section)
    assert "spend-guard:worker_standard_cpu_ms" in want
    assert all(int(p["filters"]["limit"][0]) >= 1 for p in want.values())


class _ScriptedApi:
    """`Api` over a scripted `cf_auth.curl_json`: answers in order, records (method, url)."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, answers: list[dict], listed=None) -> None:
        self.calls: list[tuple[str, str]] = []
        self.sleeps: list[float] = []
        answers = list(answers)

        def fake(method, url, _headers, _data=None, **_kw):
            self.calls.append((method, url))
            if method == "GET":
                return {"success": True, "result": listed or []}
            return answers.pop(0)

        monkeypatch.setattr(cf_notifications.cf_auth, "curl_json", fake)
        auth = types.SimpleNamespace(headers={})
        self.api = cf_notifications.Api(auth, "acct", sleep=self.sleeps.append)


REFUSED = {"success": False, "errors": [{"code": 10000, "message": "transient"}]}
OK = {"success": True, "result": {"id": "p1"}}
PRODUCT_REFUSED = {"success": False, "errors": [{"code": 17106, "message": "Invalid product"}]}


def test_write_retries_a_transient_refusal_then_succeeds(monkeypatch) -> None:
    """Review 5c376038.3: two refusals then success is three attempts with two sleeps."""
    s = _ScriptedApi(monkeypatch, [REFUSED, REFUSED, OK])
    assert s.api.write("PUT", "u", {})["success"] is True
    assert len(s.calls) == 3
    assert s.sleeps == [cf_notifications.RETRY_SLEEP_S] * 2


def test_write_gives_up_after_the_attempt_cap(monkeypatch) -> None:
    s = _ScriptedApi(monkeypatch, [REFUSED] * cf_notifications.WRITE_ATTEMPTS)
    with pytest.raises(cf_notifications.NotificationError):
        s.api.write("DELETE", "u/x", None)
    assert len(s.calls) == cf_notifications.WRITE_ATTEMPTS


def test_write_never_retries_a_product_refusal(monkeypatch) -> None:
    s = _ScriptedApi(monkeypatch, [PRODUCT_REFUSED])
    with pytest.raises(cf_notifications.UnavailableError):
        s.api.write("POST", "u", {})
    assert len(s.calls) == 1
    assert s.sleeps == []


def test_a_create_cloudflare_stored_but_reported_as_an_error_is_not_posted_twice(
    monkeypatch,
) -> None:
    """Review 5c376038.2: before a POST retry the policy list is read, and a policy of that name already there ends the retries."""
    s = _ScriptedApi(monkeypatch, [REFUSED], listed=[{"name": "spend-guard:x", "id": "stored1"}])
    assert s.api.create({"name": "spend-guard:x"}) == "stored1"
    assert [m for m, _ in s.calls].count("POST") == 1


def test_a_refused_product_is_not_counted_as_a_change(
    cf: Cf, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Review 5c376038.1: only the two policies that landed count."""
    monkeypatch.setenv("FAKE_REFUSED", "r2_storage")
    _rc, out, _err = cf.run(capsys)
    assert out.rstrip().endswith("2 change(s)")
