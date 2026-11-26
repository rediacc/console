"""The `grants` suite: an agent grant opened through the daemon executor of an on-premise stack (PLAN-rmcp-agent-grants.md, Design 8, box AG-OP1).

A grant is created through the account server's TEST_MODE seams (`/test/seed-agent-grant`, which does the portal's create flow in process with the owner's recovery code), then used the way an on-premise caller uses it: `POST /v1/mcp/call` on the daemon with the grant id and its split secret, the secret being the grant's credential. The scenarios prove the grant opens, survives a daemon restart (the session is rebuilt from the secret alone), stops at the next call after a revoke (the account server pushes the revocation to the daemon through the per-org resolver, the stack's `EXECUTOR_URL`), and dies with its holder when that member is removed from the store.

`call_outcome` is the one place a call's answer is judged: `opened` (any tool answer that is not the grant-ended refusal), `refused` (the `REDIACC_GRANT_REVOKED` answer), or `error` (no answer, a non-200 status, an unreadable body). A scenario passes the outcome it expects, so a revoke that never reached the daemon is a failed verdict, and the unit test drives that control directly.

The scenarios need the daemon, so they name `onprem` only (`--compare bench` lists them as skipped; the hosted executor is proved on the bench by LB-eu and LB-cascade).
"""

from __future__ import annotations

import json
import secrets
from typing import TYPE_CHECKING

from rediacc_ci.testrun.onprem_suites import Result, failed, passed, scenario

if TYPE_CHECKING:
    from rediacc_ci.testrun.onprem_scenarios import Context

SEAMS = "/account/api/v1/test"
CALL_ROUTE = "/v1/mcp/call"
# A read-only tool the grant's default scope admits; it reads the grant's config and touches no machine.
TOOL = "machine_list"
GRANT_ENDED = "REDIACC_GRANT_REVOKED"
ATTACH_MS = 30_000
# The restart probe listens beside the stack's daemon; the `daemon` suite's probes use offsets 1 and 2.
RESTART_PORT_OFFSET = 3
PROBE_WAIT_S = 30.0


def call_outcome(status: int, body: str) -> str:
    """`opened`, `refused` or `error` for one `/v1/mcp/call` answer."""
    if status != 200:
        return "error"
    try:
        answer = json.loads(body)
    except ValueError:
        return "error"
    if not isinstance(answer, dict):
        return "error"
    if "job" in answer:
        return "opened"
    result = answer.get("result")
    if not isinstance(result, dict):
        return "error"
    content = result.get("structuredContent")
    code = content.get("code") if isinstance(content, dict) else None
    return "refused" if code == GRANT_ENDED else "opened"


def _seam(ctx: Context, name: str, body: dict) -> dict:
    """POST a TEST_MODE seam of the stack's account server; a refusal raises with its status and text."""
    status, text = ctx.http_post(ctx.value("ONPREM_ACCOUNT_URL") + SEAMS + name, body)
    if status != 200:
        raise RuntimeError("%s answered HTTP %d: %s" % (name, status, text[:200]))
    answer = json.loads(text)
    # A non-object answer carries none of the fields a caller reads, and the caller names what is missing.
    return answer if isinstance(answer, dict) else {}


def seed_grant(ctx: Context, member: str | None = None) -> tuple[str, str]:
    """A fresh grant of the stack's user (or of `member`, joined to the store first): (grant id, secret)."""
    body = {
        "email": ctx.value("ONPREM_USER_EMAIL"),
        "recoveryCode": ctx.secret("ONPREM_RECOVERY_CODE_FILE"),
    }
    if member:
        body["memberEmail"] = member
    answer = _seam(ctx, "/seed-agent-grant", body)
    grant_id, bearer = str(answer.get("grantId", "")), str(answer.get("bearer", ""))
    prefix = "rmcp_%s." % grant_id
    if not grant_id or not bearer.startswith(prefix):
        raise RuntimeError("/seed-agent-grant answered no grant id and bearer")
    secret = bearer[len(prefix) :]
    ctx.remember(bearer)
    return grant_id, secret


def call(ctx: Context, daemon_url: str, grant: tuple[str, str]) -> tuple[str, int]:
    """One tool call under `grant` on the daemon at `daemon_url`: (outcome, HTTP status)."""
    grant_id, secret = grant
    status, text = ctx.http_post(
        daemon_url + CALL_ROUTE,
        {
            "grantId": grant_id,
            "secret": secret,
            "tool": TOOL,
            "args": {},
            "requestId": "grants-%s" % secrets.token_hex(4),
            "attachMs": ATTACH_MS,
        },
    )
    return call_outcome(status, text), status


def expect(ctx: Context, daemon_url: str, grant: tuple[str, str], wanted: str, when: str) -> Result:
    outcome, status = call(ctx, daemon_url, grant)
    if outcome != wanted:
        return failed(
            "%s: the call was %s (HTTP %d), expected %s" % (when, outcome, status, wanted), status
        )
    return passed(code=status)


def _daemon(ctx: Context) -> str:
    return ctx.value("ONPREM_DAEMON_URL")


def _probe(ctx: Context, port: int) -> tuple[int, str | None]:
    """A second daemon on `port` with the stack's executor token: (group id, None) once it answers, else (group id, why)."""
    code, pgid = ctx.serve_probe(
        ["--mode", "daemon", "--host", "127.0.0.1", "--port", str(port)],
        ctx.token("executor"),
        wait_s=0,
    )
    if code is not None:
        return pgid, "the probe daemon exited %d" % code
    url = "http://127.0.0.1:%d/v1/server-info" % port
    waited = 0.0
    while waited < PROBE_WAIT_S:
        status, _ = ctx.http_get(url)
        if status == 200:
            return pgid, None
        if ctx.exited(pgid) is not None:
            return pgid, "the probe daemon exited %d" % ctx.exited(pgid)
        ctx.sleep(0.5)
        waited += 0.5
    return pgid, "the probe daemon never answered %s" % url


@scenario("grants", "open_through_daemon")
def open_through_daemon(ctx: Context) -> Result:
    return expect(ctx, _daemon(ctx), seed_grant(ctx), "opened", "a fresh grant")


@scenario("grants", "reopen_after_daemon_restart")
def reopen_after_daemon_restart(ctx: Context) -> Result:
    port = int(ctx.value("ONPREM_DAEMON_PORT")) + RESTART_PORT_OFFSET
    if ctx.port_answers(port):
        return failed("port %d already answers; the restart probe needs it free" % port)
    grant = seed_grant(ctx)
    url = "http://127.0.0.1:%d" % port
    result = passed()
    for when in ("before the restart", "after the restart"):
        pgid, why = _probe(ctx, port)
        try:
            if why:
                return failed("%s: %s" % (when, why))
            result = expect(ctx, url, grant, "opened", when)
        finally:
            ctx.stop(pgid)
        if not result.ok:
            return result
    return result


@scenario("grants", "revoke_refuses_next_call")
def revoke_refuses_next_call(ctx: Context) -> Result:
    grant = seed_grant(ctx)
    opened = expect(ctx, _daemon(ctx), grant, "opened", "before the revoke")
    if not opened.ok:
        return opened
    answer = _seam(
        ctx, "/revoke-agent-grant", {"email": ctx.value("ONPREM_USER_EMAIL"), "grantId": grant[0]}
    )
    if answer.get("revoked") is not True:
        return failed("/revoke-agent-grant did not revoke the grant")
    # The session the first call opened is still held unless the pushed revocation dropped it.
    return expect(ctx, _daemon(ctx), grant, "refused", "after the revoke")


@scenario("grants", "member_removal_cascades")
def member_removal_cascades(ctx: Context) -> Result:
    member = "onprem-grants-%s@rediacc.io" % secrets.token_hex(3)
    grant = seed_grant(ctx, member)
    opened = expect(ctx, _daemon(ctx), grant, "opened", "the member's grant")
    if not opened.ok:
        return opened
    _seam(
        ctx,
        "/remove-store-member",
        {"email": ctx.value("ONPREM_USER_EMAIL"), "memberEmail": member},
    )
    return expect(ctx, _daemon(ctx), grant, "refused", "after the member was removed")
