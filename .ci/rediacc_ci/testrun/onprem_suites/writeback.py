"""The `writeback` suite: the daemon executor saves the config records of the commands it runs (PLAN-rmcp-writeback.md, Design 10, box WB-OP1).

A served `repo create`, `repo delete` and `repo fork` each produce EXACTLY ONE pushed config version, which a second device reads with its own `rdc repo list`; a push that races another device's push replays and keeps both edits; an account server that cannot be reached mid-command fails the command and leaves no host job behind. The scenarios need the machines of a `--machines vm` stack, because a repository is created on a real machine; they run against the stack only (`--compare bench` skips them, the hosted executor is proved on the bench by WB-L1 and WB-L2).

`check_new_versions` is the one place the version arithmetic lives. A scenario passes the count it expects, so a wrong count is a failed verdict, and the unit test drives that control directly.

THE SECOND DEVICE is a separate XDG config home (`<daemon home>/device2`) enrolled once, with the stack's machine secret (a file the stack env names), so it reads the config the daemon wrote through the account server rather than through the daemon's disk.
"""

from __future__ import annotations

import concurrent.futures
import json
import pathlib
import secrets
import signal
from typing import TYPE_CHECKING

from rediacc_ci.testrun.onprem_suites import Result, failed, passed, scenario

if TYPE_CHECKING:
    import subprocess
    from collections.abc import Callable

    from rediacc_ci.testrun.onprem_scenarios import Context

# One config version per served command: the executor pushes the record once, after the host job settles.
EXPECTED_VERSIONS = 1
REPO_SIZE = "1G"
ACCOUNT_CONTAINER = "rediacc-onprem-account"
STALLED_COMMAND_TIMEOUT_S = 90


def _name(prefix: str) -> str:
    return "%s-%s" % (prefix, secrets.token_hex(3))


def _tail(done: subprocess.CompletedProcess[str]) -> str:
    return (done.stderr.strip() or done.stdout.strip())[-200:]


def _daemon(ctx: Context) -> dict:
    """The keyword arguments that send an `rdc` call through the daemon as the stack's own org."""
    return {"token": ctx.token("executor"), "proxy": ctx.value("ONPREM_DAEMON_URL")}


def device2_home(ctx: Context) -> str:
    """The config home of the second device, enrolled on first use."""
    home = pathlib.Path(ctx.value("ONPREM_DAEMON_HOME")) / "device2"
    marker = home / ".enrolled"
    if marker.exists():
        return str(home)
    home.mkdir(parents=True, exist_ok=True)
    secret = ctx.secret("ONPREM_MACHINE_SECRET_FILE")
    for step in (
        ("config", "init", ctx.config_name()),
        (
            "config",
            "remote",
            "enable",
            "--machine-secret",
            ctx.value("ONPREM_MACHINE_SECRET_ID"),
            "--api-url",
            ctx.value("ONPREM_ACCOUNT_URL"),
            "--force",
        ),
    ):
        done = ctx.rdc(
            *step,
            token=ctx.token("enroll"),
            home=str(home),
            extra_env={"REDIACC_MACHINE_SECRET": secret},
        )
        if done.returncode != 0:
            raise RuntimeError(
                "enrolling the second device (%s) exited %d: %s"
                % (step[1], done.returncode, _tail(done))
            )
    marker.write_text("1\n", encoding="utf-8")
    return str(home)


def version_count(ctx: Context, home: str) -> int:
    """How many versions the store holds for the config, read by the second device."""
    done = ctx.rdc("--output", "json", "config", "remote", "versions", home=home)
    if done.returncode != 0:
        raise RuntimeError("config remote versions exited %d: %s" % (done.returncode, _tail(done)))
    versions = json.loads(done.stdout)
    if isinstance(versions, list):
        return len(versions)
    raise RuntimeError("config remote versions did not print a JSON list")


def listed_repos(ctx: Context, home: str) -> str:
    done = ctx.rdc("--output", "json", "repo", "list", home=home)
    if done.returncode != 0:
        raise RuntimeError(
            "the second device's repo list exited %d: %s" % (done.returncode, _tail(done))
        )
    return done.stdout


def check_new_versions(
    ctx: Context,
    home: str,
    action: Callable[[], subprocess.CompletedProcess[str]],
    expected: int,
    what: str,
) -> Result:
    """Run `action`; it must succeed and leave exactly `expected` new versions in the store."""
    before = version_count(ctx, home)
    done = action()
    if done.returncode != 0:
        return failed("%s exited %d: %s" % (what, done.returncode, _tail(done)), done.returncode)
    added = version_count(ctx, home) - before
    if added != expected:
        return failed(
            "%s pushed %d new version(s), expected %d" % (what, added, expected), done.returncode
        )
    return passed(code=done.returncode)


def _machine(ctx: Context) -> str:
    return ctx.value("ONPREM_MACHINE_NAME")


def _create(ctx: Context, name: str) -> subprocess.CompletedProcess[str]:
    return ctx.rdc(
        "repo", "create", name, "--machine", _machine(ctx), "--size", REPO_SIZE, **_daemon(ctx)
    )


def _delete(ctx: Context, ref: str) -> subprocess.CompletedProcess[str]:
    return ctx.rdc("repo", "delete", ref, "--yes", **_daemon(ctx))


@scenario("writeback", "create_pushes_one_version")
def create_pushes_one_version(ctx: Context) -> Result:
    home, name = device2_home(ctx), _name("wb-create")
    result = check_new_versions(
        ctx, home, lambda: _create(ctx, name), EXPECTED_VERSIONS, "served repo create"
    )
    if not result.ok:
        return result
    if name not in listed_repos(ctx, home):
        return failed("the second device's repo list does not show %s" % name, result.code)
    removed = _delete(ctx, name)
    if removed.returncode != 0:
        return failed(
            "cleanup: repo delete exited %d: %s" % (removed.returncode, _tail(removed)),
            removed.returncode,
        )
    return result


@scenario("writeback", "delete_pushes_one_version")
def delete_pushes_one_version(ctx: Context) -> Result:
    home, name = device2_home(ctx), _name("wb-delete")
    made = _create(ctx, name)
    if made.returncode != 0:
        return failed(
            "setup: repo create exited %d: %s" % (made.returncode, _tail(made)), made.returncode
        )
    result = check_new_versions(
        ctx, home, lambda: _delete(ctx, name), EXPECTED_VERSIONS, "served repo delete"
    )
    if result.ok and name in listed_repos(ctx, home):
        return failed("the second device's repo list still shows %s" % name, result.code)
    return result


@scenario("writeback", "fork_pushes_one_version")
def fork_pushes_one_version(ctx: Context) -> Result:
    home, name, tag = device2_home(ctx), _name("wb-fork"), "t1"
    made = _create(ctx, name)
    if made.returncode != 0:
        return failed(
            "setup: repo create exited %d: %s" % (made.returncode, _tail(made)), made.returncode
        )
    result = check_new_versions(
        ctx,
        home,
        lambda: ctx.rdc("repo", "fork", name, "--tag", tag, **_daemon(ctx)),
        EXPECTED_VERSIONS,
        "served repo fork",
    )
    if result.ok and "%s:%s" % (name, tag) not in listed_repos(ctx, home):
        result = failed(
            "the second device's repo list does not show %s:%s" % (name, tag), result.code
        )
    for ref in ("%s:%s" % (name, tag), name):
        removed = _delete(ctx, ref)
        if removed.returncode != 0 and result.ok:
            result = failed(
                "cleanup: repo delete %s exited %d: %s" % (ref, removed.returncode, _tail(removed)),
                removed.returncode,
            )
    return result


@scenario("writeback", "racing_pushes_keep_both_edits")
def racing_pushes_keep_both_edits(ctx: Context) -> Result:
    home, name, laptop = device2_home(ctx), _name("wb-race"), _name("wb-laptop")

    def served_create() -> subprocess.CompletedProcess[str]:
        return _create(ctx, name)

    def laptop_edit() -> subprocess.CompletedProcess[str]:
        return ctx.rdc("machine", "add", laptop, "--ip", "127.0.0.1", "--user", "root", home=home)

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        served, edited = pool.submit(served_create), pool.submit(laptop_edit)
        created, added = served.result(), edited.result()
    if created.returncode != 0 or added.returncode != 0:
        return failed(
            "the racing commands exited %d (served create) and %d (laptop edit): %s"
            % (created.returncode, added.returncode, _tail(created) or _tail(added)),
            created.returncode or added.returncode,
        )
    machines = ctx.rdc("--output", "json", "machine", "list", home=home)
    repos = listed_repos(ctx, home)
    problems = []
    if laptop not in machines.stdout:
        problems.append("the laptop's machine edit was lost")
    if name not in repos:
        problems.append("the served repo create was lost")
    ctx.rdc("machine", "remove", laptop, "--yes", home=home)
    _delete(ctx, name)
    if problems:
        return failed("; ".join(problems), 0)
    return passed(code=0)


def pause_account(ctx: Context) -> Callable[[], None]:
    """Stop the account server from answering without losing its state: SIGSTOP its process group (a from-source stack), else `docker pause` (the image). Returns the function that resumes it."""
    try:
        pgid = ctx.group_pgid("account")
    except KeyError:
        done = ctx.exec(["docker", "pause", ACCOUNT_CONTAINER])
        if done.returncode != 0:
            raise RuntimeError(
                "docker pause %s failed: %s" % (ACCOUNT_CONTAINER, _tail(done))
            ) from None
        return lambda: ctx.exec(["docker", "unpause", ACCOUNT_CONTAINER])
    ctx.signal_group(pgid, signal.SIGSTOP)
    return lambda: ctx.signal_group(pgid, signal.SIGCONT)


@scenario("writeback", "account_unreachable_fails_without_a_host_job")
def account_unreachable_fails_without_a_host_job(ctx: Context) -> Result:
    home, name = device2_home(ctx), _name("wb-down")
    resume = pause_account(ctx)
    try:
        done = ctx.rdc(
            "repo",
            "create",
            name,
            "--machine",
            _machine(ctx),
            "--size",
            REPO_SIZE,
            timeout=STALLED_COMMAND_TIMEOUT_S,
            **_daemon(ctx),
        )
    finally:
        resume()
    if done.returncode == 0:
        _delete(ctx, name)
        return failed("repo create succeeded while the account server could not be reached", 0)
    if name in listed_repos(ctx, home):
        return failed("a record of %s exists although the command failed" % name, done.returncode)
    on_host = ctx.rdc("repo", "list", "--machine", _machine(ctx), **_daemon(ctx))
    if name in on_host.stdout:
        return failed(
            "a host job created %s although its record could not be saved" % name, done.returncode
        )
    return passed(
        "failed with exit %d, no record and no host repository" % done.returncode, done.returncode
    )
