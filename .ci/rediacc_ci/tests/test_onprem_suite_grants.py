"""Tests for the `grants` on-premise suite against a recorded stack env and a stateful fake of the account seams and the daemon: no stack, no network.

The fake holds grants the way the account server and the daemon would: a seeded grant opens, a probe daemon that is restarted rebuilds its session from the secret, a revoke pushes to the stack daemon and drops its held session, and a member removal ends that member's grants. Each failure mode of the suite has a control that makes the scenario fail, the revoke push that never lands first among them.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from rediacc_ci.testrun import onprem_scenarios as scenarios
from rediacc_ci.testrun import onprem_stack, onprem_suites
from rediacc_ci.testrun.onprem_suites import grants

if TYPE_CHECKING:
    import pathlib

EXECUTOR = "tok-executor-value"
RECOVERY = "RC1-RECOVERY-CODE-VALUE"
ACCOUNT = "http://127.0.0.1:4910"
DAEMON = "http://127.0.0.1:8480"
PROBE_PORT = 8480 + grants.RESTART_PORT_OFFSET
PROBE = "http://127.0.0.1:%d" % PROBE_PORT


def tool_answer(code: str | None = None, echo: str | None = None) -> str:
    content: dict = {"code": code} if code else {"machines": []}
    if echo:
        content["echo"] = echo
    return json.dumps({"result": {"isError": code is not None, "structuredContent": content}})


class FakeOnPrem(onprem_stack.Runtime):
    """The account server's grant seams and two daemons (the stack's and a restartable probe) in one state machine."""

    def __init__(self) -> None:
        super().__init__()
        self.grants: dict[str, dict] = {}
        self.held: dict[str, set[str]] = {DAEMON: set(), PROBE: set()}
        self.probe_pgid: int | None = None
        self.next_pgid = 9000
        self.posts: list[tuple[str, dict]] = []
        # Behaviours a control flips.
        self.push_lands = True
        self.rehydrates = True
        self.cascade_reaches_grants = True
        self.daemon_serves_calls = True
        self.daemon_status = 200
        self.echo_secret = False

    # ── HTTP ────────────────────────────────────────────────────────────────

    def http_post(self, url, body, headers=None, timeout=60):
        del headers, timeout
        self.posts.append((url, body))
        if url.startswith(ACCOUNT + grants.SEAMS):
            return self.seam(url[len(ACCOUNT + grants.SEAMS) :], body)
        base = url[: -len(grants.CALL_ROUTE)]
        if base == PROBE and self.probe_pgid is None:
            return 0, ""
        if not self.daemon_serves_calls:
            return 404, "404 Not Found"
        return 200, self.call(base, body)

    def seam(self, name: str, body: dict) -> tuple[int, str]:
        if name == "/seed-agent-grant":
            if body.get("recoveryCode") != RECOVERY:
                return 409, json.dumps({"error": "The recovery code does not open the store"})
            grant_id = "g%d" % (len(self.grants) + 1)
            secret = "S-%s" % grant_id
            self.grants[grant_id] = {
                "secret": secret,
                "live": True,
                "member": body.get("memberEmail"),
            }
            bearer = "rmcp_%s.%s" % (grant_id, secret)
            return 200, json.dumps({"grantId": grant_id, "bearer": bearer})
        if name == "/revoke-agent-grant":
            self.grants[body["grantId"]]["live"] = False
            if self.push_lands:
                self.held[DAEMON].discard(body["grantId"])
            return 200, json.dumps({"revoked": True})
        if name == "/remove-store-member":
            for grant_id, grant in self.grants.items():
                if grant["member"] == body["memberEmail"] and self.cascade_reaches_grants:
                    grant["live"] = False
                    self.held[DAEMON].discard(grant_id)
            return 200, json.dumps({"removed": True})
        return 404, "no such seam"

    def call(self, base: str, body: dict) -> str:
        grant_id = body["grantId"]
        grant = self.grants.get(grant_id)
        echo = body["secret"] if self.echo_secret else None
        if grant is None or grant["secret"] != body["secret"]:
            return tool_answer(grants.GRANT_ENDED, echo)
        # A held session answers without asking the account; a new one asks it, which a revoked grant fails.
        if grant_id in self.held[base]:
            return tool_answer(echo=echo)
        if not grant["live"] or (base == PROBE and not self.rehydrates and grant.get("seen")):
            return tool_answer(grants.GRANT_ENDED, echo)
        grant["seen"] = True
        self.held[base].add(grant_id)
        return tool_answer(echo=echo)

    def http_get(self, url, headers=None, insecure_tls=False):
        del headers, insecure_tls
        if url.startswith(PROBE) and self.probe_pgid is not None:
            return 200, json.dumps({"mode": "daemon"})
        return 0, ""

    # ── the probe daemon ────────────────────────────────────────────────────

    def spawn_group(self, argv, env, cwd, log_file):
        del cwd, log_file
        assert argv[argv.index("--port") + 1] == str(PROBE_PORT)
        assert env["REDIACC_TOKEN"] == EXECUTOR
        self.next_pgid += 1
        self.probe_pgid = self.next_pgid
        return self.probe_pgid

    def exited(self, pgid):
        del pgid

    def kill_group(self, pgid):
        if pgid == self.probe_pgid:
            self.probe_pgid = None
            self.held[PROBE] = set()  # a restart loses every session held in RAM

    def port_answers(self, port):
        return port == PROBE_PORT and self.probe_pgid is not None

    def sleep(self, seconds):
        del seconds


@pytest.fixture
def home(tmp_path: pathlib.Path) -> pathlib.Path:
    (tmp_path / "executor.token").write_text(EXECUTOR + "\n", encoding="utf-8")
    (tmp_path / "recovery-code.token").write_text(RECOVERY + "\n", encoding="utf-8")
    return tmp_path


def _ctx(rt: FakeOnPrem, home: pathlib.Path) -> scenarios.Context:
    env = {
        "ONPREM_ACCOUNT_URL": ACCOUNT,
        "ONPREM_DAEMON_URL": DAEMON,
        "ONPREM_DAEMON_PORT": "8480",
        "ONPREM_DAEMON_HOME": str(home),
        "ONPREM_CONFIG_NAME": "onprem-stack",
        "ONPREM_USER_EMAIL": "onprem-stack@rediacc.io",
        "ONPREM_EXECUTOR_TOKEN_FILE": str(home / "executor.token"),
        "ONPREM_RECOVERY_CODE_FILE": str(home / "recovery-code.token"),
    }
    return scenarios.Context("onprem", env, home, rt)


def _run(ctx: scenarios.Context, name: str) -> dict:
    return scenarios.run_scenario(onprem_suites.load_all()["grants"][name], ctx)


def test_the_suite_registers_four_onprem_only_scenarios() -> None:
    suite = onprem_suites.load_all()["grants"]
    assert set(suite) == {
        "open_through_daemon",
        "reopen_after_daemon_restart",
        "revoke_refuses_next_call",
        "member_removal_cascades",
    }
    assert all(s.targets == ("onprem",) for s in suite.values())


def test_every_scenario_passes_against_a_stack_that_behaves(home: pathlib.Path) -> None:
    rt = FakeOnPrem()
    ctx = _ctx(rt, home)
    for name in onprem_suites.load_all()["grants"]:
        verdict = _run(ctx, name)
        assert verdict["ok"] is True, verdict
    assert rt.probe_pgid is None, "the restart probe was left running"


def test_control_a_revoke_whose_push_never_reaches_the_daemon_fails(home: pathlib.Path) -> None:
    rt = FakeOnPrem()
    rt.push_lands = False
    verdict = _run(_ctx(rt, home), "revoke_refuses_next_call")
    assert verdict["ok"] is False
    assert "after the revoke: the call was opened" in verdict["detail"]


def test_control_a_member_removal_that_leaves_the_grant_alive_fails(home: pathlib.Path) -> None:
    rt = FakeOnPrem()
    rt.cascade_reaches_grants = False
    verdict = _run(_ctx(rt, home), "member_removal_cascades")
    assert verdict["ok"] is False
    assert "after the member was removed" in verdict["detail"]
    seeded = [body for url, body in rt.posts if url.endswith("/seed-agent-grant")]
    assert seeded[0]["memberEmail"].startswith("onprem-grants-")


def test_control_a_daemon_that_cannot_rebuild_a_session_after_a_restart_fails(
    home: pathlib.Path,
) -> None:
    rt = FakeOnPrem()
    rt.rehydrates = False
    verdict = _run(_ctx(rt, home), "reopen_after_daemon_restart")
    assert verdict["ok"] is False
    assert "after the restart" in verdict["detail"]
    assert rt.probe_pgid is None, "a failed scenario still stops its probe"


def test_control_a_daemon_without_the_call_route_fails_every_scenario(home: pathlib.Path) -> None:
    rt = FakeOnPrem()
    rt.daemon_serves_calls = False
    ctx = _ctx(rt, home)
    for name in onprem_suites.load_all()["grants"]:
        verdict = _run(ctx, name)
        assert verdict["ok"] is False, name
        assert verdict["code"] == 404, verdict


def test_the_secret_and_the_recovery_code_never_reach_a_verdict(home: pathlib.Path) -> None:
    rt = FakeOnPrem()
    rt.push_lands = False
    rt.echo_secret = True
    verdict = _run(_ctx(rt, home), "revoke_refuses_next_call")
    assert verdict["ok"] is False
    text = json.dumps(verdict)
    assert "S-g1" not in text
    assert RECOVERY not in text


def test_a_seed_refusal_is_a_failed_verdict_naming_the_seam(home: pathlib.Path) -> None:
    (home / "recovery-code.token").write_text("RC1-WRONG\n", encoding="utf-8")
    verdict = _run(_ctx(FakeOnPrem(), home), "open_through_daemon")
    assert verdict["ok"] is False
    assert "/seed-agent-grant answered HTTP 409" in verdict["detail"]


@pytest.mark.parametrize(
    ("status", "body", "outcome"),
    [
        (200, tool_answer(), "opened"),
        (200, json.dumps({"job": {"jobId": "j1"}}), "opened"),
        (200, tool_answer("POLICY_DENIED"), "opened"),
        (200, tool_answer(grants.GRANT_ENDED), "refused"),
        (502, "{}", "error"),
        (0, "", "error"),
        (200, "not json", "error"),
        (200, json.dumps([1]), "error"),
        (200, json.dumps({"result": "x"}), "error"),
    ],
)
def test_call_outcome(status: int, body: str, outcome: str) -> None:
    assert grants.call_outcome(status, body) == outcome
