"""The `config-edit` suite: an agent cannot edit or rotate the config, whatever its environment holds (PLAN-rmcp-config-edit-removal.md, Design 7, box R-OP1).

The old `REDIACC_ALLOW_CONFIG_EDIT` override is gone, so an agent environment that exported it before the agent started is refused for `config edit --apply` and for `config field rotate` exactly like one that did not. Each refusal must exit non-zero with a message on stderr that names no page of the hosted portal, and the config store (the Node account server on the stack) must hold the same latest version afterwards, which is read by `config remote versions` outside the agent environment. `config edit --dump --redacted` stays allowed for the agent, the control that the refusals are not a broken command.

`assert_refused` and `assert_unchanged` are the two judgements; a command that exits 0, or a store that moved, is a failed verdict, and the unit test drives both.
"""

from __future__ import annotations

import json
import pathlib
import tempfile
from typing import TYPE_CHECKING

from rediacc_ci.testrun.onprem_suites import Result, failed, passed, scenario
from rediacc_ci.well_known import PRODUCT_DOMAIN

if TYPE_CHECKING:
    import subprocess

    from rediacc_ci.testrun.onprem_scenarios import Context

OLD_VAR = "REDIACC_ALLOW_CONFIG_EDIT"
# What marks the process as an agent (utils/agent-guard.ts reads it from the environment).
AGENT_ENV = {"CLAUDECODE": "1", OLD_VAR: "*"}
ROTATE_POINTER = "/credentials/ssh/privateKey"
# A refusal that sends the reader to the hosted portal is wrong on an on-premise stack.
HOSTED_ONLY_MARKS = (PRODUCT_DOMAIN, "/account/")
APPLY_FILE = "config-edit-probe.jsonc"


def _tail(done: subprocess.CompletedProcess[str]) -> str:
    return (done.stderr.strip() or done.stdout.strip())[-200:]


def latest_version(ctx: Context) -> int:
    """The newest version the store holds for the config, read outside the agent environment."""
    done = ctx.rdc("--output", "json", "config", "remote", "versions")
    if done.returncode != 0:
        raise RuntimeError("config remote versions exited %d: %s" % (done.returncode, _tail(done)))
    versions = json.loads(done.stdout)
    if not isinstance(versions, list) or not versions:
        raise RuntimeError("config remote versions did not print a non-empty JSON list")
    return len(versions)


def assert_refused(done: subprocess.CompletedProcess[str], what: str) -> Result | None:
    """A failed Result unless `done` exited non-zero with a message on stderr that names no hosted-only page."""
    if done.returncode == 0:
        return failed("%s was admitted for an agent, expected a refusal" % what, 0)
    if not done.stderr.strip():
        return failed(
            "%s was refused (exit %d) with nothing on stderr" % (what, done.returncode),
            done.returncode,
        )
    hosted = [mark for mark in HOSTED_ONLY_MARKS if mark in done.stderr]
    if hosted:
        return failed(
            "the %s refusal names a hosted-only page (%s)" % (what, ", ".join(hosted)),
            done.returncode,
        )
    return None


def assert_unchanged(before: int, after: int, what: str) -> Result | None:
    if after != before:
        return failed("%s moved the store from version %d to %d" % (what, before, after))
    return None


def _refusal_scenario(ctx: Context, what: str, *args: str) -> Result:
    before = latest_version(ctx)
    done = ctx.rdc(*args, token=ctx.token("executor"), extra_env=AGENT_ENV)
    refused = assert_refused(done, what)
    if refused:
        return refused
    return assert_unchanged(before, latest_version(ctx), what) or passed(
        "refused with exit %d, the store stayed at version %d" % (done.returncode, before),
        done.returncode,
    )


@scenario("config-edit", "apply_refused_for_an_agent", targets=("onprem", "bench"))
def apply_refused_for_an_agent(ctx: Context) -> Result:
    with tempfile.TemporaryDirectory() as scratch:
        probe = pathlib.Path(scratch) / APPLY_FILE
        probe.write_text("{}\n", encoding="utf-8")
        return _refusal_scenario(
            ctx, "config edit --apply", "config", "edit", "--apply", str(probe)
        )


@scenario("config-edit", "rotate_refused_for_an_agent", targets=("onprem", "bench"))
def rotate_refused_for_an_agent(ctx: Context) -> Result:
    return _refusal_scenario(
        ctx,
        "config field rotate",
        "config",
        "field",
        "rotate",
        "--pointer",
        ROTATE_POINTER,
        "--new",
        "x",
    )


@scenario("config-edit", "redacted_dump_allowed_for_an_agent", targets=("onprem", "bench"))
def redacted_dump_allowed_for_an_agent(ctx: Context) -> Result:
    done = ctx.rdc(
        "config", "edit", "--dump", "--redacted", token=ctx.token("executor"), extra_env=AGENT_ENV
    )
    if done.returncode != 0:
        return failed(
            "config edit --dump --redacted exited %d for an agent: %s"
            % (done.returncode, _tail(done)),
            done.returncode,
        )
    return passed(code=done.returncode)
