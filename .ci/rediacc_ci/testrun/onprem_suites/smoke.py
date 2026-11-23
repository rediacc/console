"""The `smoke` suite: the stack is up and the CLI works against it (PLAN-rmcp-executor-hardening.md, Design 16).

`config_current` and `repo_list` name both targets, so `--compare bench` runs them against the eu bench too and the two must agree on their exit codes; the other two read the local stack only.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from rediacc_ci.testrun.onprem_suites import Result, failed, passed, scenario

if TYPE_CHECKING:
    from rediacc_ci.testrun.onprem_scenarios import Context


@scenario("smoke", "account_health")
def account_health(ctx: Context) -> Result:
    code, _ = ctx.http_get(ctx.value("ONPREM_ACCOUNT_URL") + "/health")
    if code != 200:
        return failed("GET /health answered %d, expected 200" % code, code)
    return passed(code=code)


@scenario("smoke", "config_current", targets=("onprem", "bench"))
def config_current(ctx: Context) -> Result:
    done = ctx.rdc("config", "current")
    if done.returncode != 0:
        return failed(
            "config current exited %d: %s" % (done.returncode, done.stderr.strip()[-200:]),
            done.returncode,
        )
    if ctx.config_name() not in done.stdout + done.stderr:
        return failed("config current does not name %s" % ctx.config_name(), done.returncode)
    return passed(code=done.returncode)


@scenario("smoke", "repo_list", targets=("onprem", "bench"))
def repo_list(ctx: Context) -> Result:
    done = ctx.rdc("repo", "list")
    if done.returncode != 0:
        return failed(
            "repo list exited %d: %s" % (done.returncode, done.stderr.strip()[-200:]),
            done.returncode,
        )
    return passed(code=done.returncode)


@scenario("smoke", "machine_listed")
def machine_listed(ctx: Context) -> Result:
    done = ctx.rdc("--output", "json", "machine", "list")
    name = ctx.value("ONPREM_MACHINE_NAME")
    if done.returncode != 0:
        return failed(
            "machine list exited %d: %s" % (done.returncode, done.stderr.strip()[-200:]),
            done.returncode,
        )
    if name not in done.stdout:
        return failed("machine list does not show %s" % name, done.returncode)
    return passed(code=done.returncode)
