"""The `local-mcp` suite: `rdc mcp serve` over stdio against an on-premise config (PLAN-rmcp-local-mcp.md, Design 9, box LM-OP1).

Each scenario starts the real stdio server with the SDK v2 client and reads what a tool call returns: `tools/list` filtered to the proxy surface equals the parity snapshot, a read tool answers, a fork write is admitted, a write on a grand repository is refused with its structured code while no opt-in is set, and the same write is admitted when `REDIACC_ALLOW_GRAND_REPO` names the repository in the environment the client starts with (an opt-in set before the agent starts, which is where the policy looks for it).

THE DRIVER is one inline Node program (`DRIVER`) run by `ctx.exec`: the harness gives a scenario no bidirectional pipe, and the SDK client is the oracle the plan names. It prints one JSON line (`tools` when asked, `calls` for each tool call). Everything else is judged here, in Python, so a wrong expectation is a failed verdict that the unit test drives directly (`check_refusal`).

The read and listing scenarios name `bench` as well, so `--compare bench` holds their verdicts equal to the eu-bench run. The write scenarios create a repository on the stack's machine and run on the stack only.
"""

from __future__ import annotations

import json
import pathlib
import secrets
from typing import TYPE_CHECKING

from rediacc_ci.testrun.onprem_suites import Result, failed, passed, scenario

if TYPE_CHECKING:
    from collections.abc import Callable

    from rediacc_ci.testrun.onprem_scenarios import Context

SNAPSHOT = pathlib.Path("packages/shared/src/mcp/__tests__/tools-list.snapshot.json")
REGISTRY = pathlib.Path("packages/shared/src/mcp/tools.generated.json")
SPEC = "2026-07-28"
GRAND_VAR = "REDIACC_ALLOW_GRAND_REPO"
REPO_SIZE = "1G"
FORK_TAG = "t1"
# The refusal the child `rdc` returns for a grand-repo write with no opt-in: the envelope code, then the policy's own code as the first detail (utils/command-policy.ts refusalError).
REFUSAL_CODE = "VALIDATION_ERROR"
REFUSAL_DETAIL = "AGENT_OPT_IN_MISSING"
DRIVER_TIMEOUT_S = 600

# argv: [rdc.sh, config name, JSON {list: bool, calls: [{name, arguments}]}]. The environment is the client's own, passed on to the server it spawns.
DRIVER = (
    """
import { Client } from '@modelcontextprotocol/client';
import { StdioClientTransport } from '@modelcontextprotocol/client/stdio';
const [command, config, raw] = process.argv.slice(1);
const plan = JSON.parse(raw);
const transport = new StdioClientTransport({
  command,
  args: ['--config', config, 'mcp', 'serve'],
  env: Object.fromEntries(Object.entries(process.env).filter(([, v]) => v !== undefined)),
  stderr: 'pipe',
});
let stderr = '';
transport.stderr?.on('data', (chunk) => { stderr += chunk.toString(); });
const client = new Client(
  { name: 'onprem-local-mcp', version: '0.0.0' },
  { versionNegotiation: { mode: { pin: '%s' } } },
);
const out = { calls: [] };
try {
  await client.connect(transport);
  out.era = client.getProtocolEra();
  if (plan.list) {
    const { tools } = await client.listTools();
    out.tools = tools.map((t) => ({
      name: t.name, description: t.description, inputSchema: t.inputSchema, annotations: t.annotations,
    }));
  }
  for (const call of plan.calls) {
    const result = await client.callTool({ name: call.name, arguments: call.arguments });
    const text = result.content?.[0]?.text ?? '';
    let envelope;
    try { envelope = JSON.parse(text); } catch { envelope = { raw: text }; }
    out.calls.push({ name: call.name, isError: result.isError === true, envelope });
  }
} catch (error) {
  out.error = String(error?.stack ?? error) + '\\n' + stderr.slice(-400);
} finally {
  await client.close().catch(() => undefined);
}
// A pipe is asynchronous: exit only once the (large) listing has been flushed.
process.stdout.write(JSON.stringify(out) + '\\n', () => process.exit(out.error ? 1 : 0));
"""
    % SPEC
)


def _name(prefix: str) -> str:
    return "%s-%s" % (prefix, secrets.token_hex(3))


def _tail(text: str) -> str:
    return text.strip()[-300:]


def drive(
    ctx: Context,
    calls: list[tuple[str, dict]],
    *,
    list_tools: bool = False,
    opt_in: str | None = None,
) -> dict:
    """Start `rdc mcp serve` under the SDK v2 client, make `calls`, and return the driver's JSON. A driver that fails, times out or prints something else raises RuntimeError (a failed verdict naming it)."""
    env = ctx.cli_env(ctx.token("executor"))
    env.pop(GRAND_VAR, None)
    if opt_in is not None:
        env[GRAND_VAR] = opt_in
    plan = {
        "list": list_tools,
        "calls": [{"name": name, "arguments": args} for name, args in calls],
    }
    argv = [
        "node",
        "--input-type=module",
        "-e",
        DRIVER,
        "--",
        str(ctx.root / "rdc.sh"),
        ctx.config_name(),
        json.dumps(plan),
    ]
    done = ctx.exec(argv, env=env, timeout=DRIVER_TIMEOUT_S)
    if done.returncode != 0:
        raise RuntimeError(
            "the MCP driver exited %d: %s" % (done.returncode, _tail(done.stdout + done.stderr))
        )
    try:
        out = json.loads(done.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        raise RuntimeError("the MCP driver printed no JSON line: %s" % _tail(done.stdout)) from None
    if out.get("era") != "modern":
        raise RuntimeError(
            "the server negotiated protocol era %r, expected modern" % out.get("era")
        )
    return out


def proxy_surface(ctx: Context, tools: list[dict]) -> list[dict]:
    """The listing narrowed to the tools the registry marks `proxy`, ordered by name."""
    registry = json.loads((ctx.root / REGISTRY).read_text(encoding="utf-8"))
    proxy = {t["name"] for t in registry["tools"] if t.get("surface") == "proxy"}
    return sorted((t for t in tools if t["name"] in proxy), key=lambda t: t["name"])


def compare_snapshot(ctx: Context, tools: list[dict]) -> str | None:
    """None when the proxy slice of `tools` equals the parity snapshot, else what differs."""
    snapshot = json.loads((ctx.root / SNAPSHOT).read_text(encoding="utf-8"))
    served = {t["name"]: t for t in proxy_surface(ctx, tools)}
    expected = {t["name"]: t for t in snapshot}
    missing, extra = sorted(set(expected) - set(served)), sorted(set(served) - set(expected))
    if missing or extra:
        return "proxy tools differ from the snapshot (missing %s, extra %s)" % (
            missing[:5],
            extra[:5],
        )
    for name, tool in expected.items():
        for field in ("description", "inputSchema", "annotations"):
            if served[name].get(field) != tool.get(field):
                return "tool %s differs from the snapshot in %s" % (name, field)
    return None


def check_success(call: dict, what: str) -> Result | None:
    """A failed Result unless the tool call succeeded with a success envelope."""
    envelope = call["envelope"]
    if call["isError"] or envelope.get("success") is not True:
        errors = envelope.get("errors") or [{}]
        return failed(
            "%s failed: %s %s"
            % (
                what,
                errors[0].get("code"),
                (errors[0].get("details") or [errors[0].get("message")])[0],
            )
        )
    return None


def check_refusal(call: dict, code: str, detail: str, what: str) -> Result:
    """Passed only when `call` is an error carrying envelope code `code` and the policy code `detail` first."""
    envelope = call["envelope"]
    errors = envelope.get("errors") or [{}]
    first = errors[0]
    if not call["isError"]:
        return failed("%s was admitted, expected a refusal" % what)
    if first.get("code") != code:
        return failed("%s was refused with code %r, expected %r" % (what, first.get("code"), code))
    details = first.get("details") or [None]
    if details[0] != detail:
        return failed("%s was refused for %r, expected %r" % (what, details[0], detail))
    return passed("refused with %s / %s" % (code, detail))


def _machine(ctx: Context) -> str:
    return ctx.value("ONPREM_MACHINE_NAME")


def _create(ctx: Context, name: str):
    return ctx.rdc(
        "repo",
        "create",
        name,
        "--machine",
        _machine(ctx),
        "--size",
        REPO_SIZE,
        token=ctx.token("executor"),
    )


def _delete(ctx: Context, ref: str):
    return ctx.rdc("repo", "delete", ref, "--yes", token=ctx.token("executor"))


def _with_grand(ctx: Context, prefix: str, body: Callable[[str], Result]) -> Result:
    """Create a grand repository, run `body(name)`, and delete the repository and any fork; a cleanup that fails fails a passing verdict."""
    name = _name(prefix)
    made = _create(ctx, name)
    if made.returncode != 0:
        return failed(
            "setup: repo create exited %d: %s" % (made.returncode, _tail(made.stderr)),
            made.returncode,
        )
    result = body(name)
    for ref in ("%s:%s" % (name, FORK_TAG), name):
        removed = _delete(ctx, ref)
        if removed.returncode != 0 and ref == name and result.ok:
            result = failed(
                "cleanup: repo delete exited %d: %s" % (removed.returncode, _tail(removed.stderr)),
                removed.returncode,
            )
    return result


@scenario("local-mcp", "tools_list_matches_parity_snapshot", targets=("onprem", "bench"))
def tools_list_matches_parity_snapshot(ctx: Context) -> Result:
    served = drive(ctx, [], list_tools=True)
    diff = compare_snapshot(ctx, served.get("tools") or [])
    if diff:
        return failed(diff)
    return passed("%d tools listed, the proxy surface equals the snapshot" % len(served["tools"]))


@scenario("local-mcp", "read_tool_answers", targets=("onprem", "bench"))
def read_tool_answers(ctx: Context) -> Result:
    args = {"machine": _machine(ctx)} if ctx.target == "onprem" else {}
    call = drive(ctx, [("repo_list", args)])["calls"][0]
    return check_success(call, "repo_list") or passed()


@scenario("local-mcp", "fork_write_admitted")
def fork_write_admitted(ctx: Context) -> Result:
    def body(name: str) -> Result:
        calls = drive(
            ctx,
            [
                ("repo_fork", {"ref": name, "tag": FORK_TAG}),
                ("repo_up", {"ref": "%s:%s" % (name, FORK_TAG)}),
            ],
        )["calls"]
        return (
            check_success(calls[0], "repo_fork")
            or check_success(calls[1], "repo_up on the fork")
            or passed()
        )

    return _with_grand(ctx, "lm-fork", body)


@scenario("local-mcp", "grand_write_refused_without_opt_in")
def grand_write_refused_without_opt_in(ctx: Context) -> Result:
    def body(name: str) -> Result:
        call = drive(ctx, [("repo_up", {"ref": name})])["calls"][0]
        return check_refusal(
            call, REFUSAL_CODE, REFUSAL_DETAIL, "repo_up on the grand repo %s" % name
        )

    return _with_grand(ctx, "lm-refuse", body)


@scenario("local-mcp", "grand_write_admitted_with_opt_in")
def grand_write_admitted_with_opt_in(ctx: Context) -> Result:
    def body(name: str) -> Result:
        call = drive(ctx, [("repo_up", {"ref": name})], opt_in=name)["calls"][0]
        return check_success(call, "repo_up on %s with %s set" % (name, GRAND_VAR)) or passed()

    return _with_grand(ctx, "lm-admit", body)
