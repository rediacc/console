"""The bench refusal hint (`.claude/hooks/stop/wl_benchblock.py`), a member of the post-bash pattern.

EVERY FIRE CASE HAS A CONTROL that must stay silent: the same 403 from eu-remote, from GitHub, a bench command printing an unrelated 403, a document that quotes the block page, and output that already names the fix. The hosts come from `rediacc_hooks.wellknown`, never typed here, and the fix texts are pinned equal to their owners in `.ci`.
"""

from __future__ import annotations

import io
import json
import subprocess
import sys
import urllib.parse

import pytest
import wl_benchblock as B

from rediacc_hooks import lifecycle, syspath, wellknown
from rediacc_hooks.tests import wlfix

MEMBER = wlfix.STOP_DIR / "wl_benchblock.py"
BENCH_HOST = urllib.parse.urlsplit(wellknown.BENCH_ORIGIN).hostname
PROXY_HOST = wellknown.PROXY_BENCH_HOST

# What the CLI printed against eu-bench on 2026-11-10 while this IP was off the allowlist: progress on stderr, the envelope on stdout.
CLI_STDERR = (
    "→ Preparing CLI development environment\n"
    "✓ Renet available at /x\n"
    "→ Starting CLI (config eu-bench)\n"
)
CLI_STDOUT = json.dumps(
    {
        "success": False,
        "command": "machine list",
        "data": None,
        "errors": [{"code": "GENERAL_ERROR", "message": "HTTP 403"}],
    }
)
# Cloudflare's own block page, as curl prints it (the bench rule has no custom body).
CF_PAGE = (
    "HTTP/2 403 \r\ndate: Tue, 10 Nov 2026 05:00:00 GMT\r\ncontent-type: text/html; charset=UTF-8\r\n"
    "cf-ray: 8d1f2a3b4c5d6e7f-FRA\r\n\r\n"
    "<!DOCTYPE html>\n<title>Attention Required! | Cloudflare</title>\n"
    '<h1 data-translate="block_headline">Sorry, you have been blocked</h1>\n'
)
CF_PAGE_BODY_ONLY = (
    "<!DOCTYPE html>\n<title>Attention Required! | Cloudflare</title>\n"
    "<h1>Sorry, you have been blocked</h1>\n"
)
CF_MITIGATED = "HTTP/2 403 \ncf-mitigated: challenge\nserver: cloudflare\n"
LOGIN_REFUSAL = json.dumps(
    {
        "success": False,
        "errors": [
            {
                "message": "The config token could not be renewed because this device's login is "
                "tied to another network address. Your IP address changed, and this login only "
                "works from the old one."
            }
        ],
    }
)


def payload(command, stdout="", stderr="", tool="Bash"):
    return {
        "session_id": "cafef00d-1",
        "cwd": str(wlfix.STOP_DIR),
        "hook_event_name": "PostToolUse",
        "tool_name": tool,
        "tool_input": {"command": command},
        "tool_response": {
            "stdout": stdout,
            "stderr": stderr,
            "interrupted": False,
            "isImage": False,
        },
    }


def context(doc):
    """The additionalContext the member injects for `doc`, or "" when it says nothing."""
    out = io.StringIO()
    assert B.main(stdin=io.StringIO(json.dumps(doc)), stdout=out) == 0
    text = out.getvalue()
    if not text:
        return ""
    parsed = json.loads(text)
    return parsed["hookSpecificOutput"]["additionalContext"]


# ---- the fix texts and hosts come from their owners ---------------------------


def test_sources_are_the_owners_values():
    bench_access = syspath.import_from_ci("rediacc_ci.ops.bench_access")
    login_bench = syspath.import_from_ci("rediacc_ci.ops.login_bench")
    command, remedy, markers, hosts = B.sources()
    assert command == bench_access.COMMAND
    assert remedy == login_bench.REMEDY == "npm run login:bench"
    assert markers == tuple(login_bench.LOGIN_NEEDED_MARKERS)
    assert set(hosts) == {BENCH_HOST, PROXY_HOST}
    assert set(hosts) == set(bench_access.bench_hosts())


def test_is_bench_command_both_directions():
    """The context alone, without the prefilter in front of it: the end-to-end controls below are also silenced by `_maybe`, so this pins the context's own precision."""
    hosts = B.sources()[3]
    for cmd in (
        "./rdc.sh --config eu-bench machine list",
        "rdc --config=bench repo list",
        "REDIACC_CONFIG=eu-bench rdc machine list",
        "curl https://%s/x" % BENCH_HOST,
        "curl https://%s/v1/x" % PROXY_HOST,
    ):
        assert B.is_bench_command(cmd, hosts), cmd
    for cmd in (
        "./rdc.sh --config eu-remote machine list",
        "./rdc.sh --config eu-bench-old machine list",
        "./rdc.sh --config bench2 machine list",
        "gh api repos/o/r --jq .bench",
        "curl https://x%s/" % BENCH_HOST,
        "cat docs/agent-reference/TRAPS.md",
    ):
        assert not B.is_bench_command(cmd, hosts), cmd


def test_the_prefilter_admits_every_signal():
    """A signal with no fragment in `PREFILTER` is dropped before it is read; each marker and page phrase must carry one."""
    _command, _remedy, markers, _hosts = B.sources()
    for signal in (*markers, CF_PAGE_BODY_ONLY, CF_MITIGATED, CLI_STDOUT):
        assert any(f in signal for f in B.PREFILTER), signal


# ---- the allowlist note: fires ---------------------------------------------------


@pytest.mark.parametrize(
    ("command", "stdout", "stderr"),
    [
        ("./rdc.sh --config eu-bench machine list", CLI_STDOUT, CLI_STDERR),
        ("./rdc.sh --config=eu-bench machine list -o json", CLI_STDOUT, CLI_STDERR),
        ("REDIACC_CONFIG=eu-bench ./rdc.sh machine list", CLI_STDOUT, CLI_STDERR),
        ("rdc --config bench repo list", CLI_STDOUT, ""),
        ("curl -si https://%s/account/api/v1/me" % BENCH_HOST, CF_PAGE, ""),
        ("curl -s 'https://%s/v1/x'" % PROXY_HOST, CF_PAGE_BODY_ONLY, ""),
        ("curl -sI https://%s/" % BENCH_HOST, CF_MITIGATED, ""),
    ],
    ids=[
        "flag",
        "flag-equals",
        "env-prefix",
        "bench-config",
        "curl-page",
        "proxy-body",
        "cf-mitigated",
    ],
)
def test_a_bench_403_names_the_allowlist_fix(command, stdout, stderr):
    text = context(payload(command, stdout, stderr))
    assert "bench IP allowlist" in text
    assert "NOT a rate limit" in text
    assert B.sources()[0] in text
    assert "login:bench" not in text
    assert 2 <= len(text.splitlines()) <= 3


def test_the_note_is_said_once_per_output():
    text = context(
        payload("./rdc.sh --config eu-bench machine list", CF_PAGE + CLI_STDOUT, CF_PAGE)
    )
    assert text.count("bench-block:") == 1


# ---- the allowlist note: controls ------------------------------------------------


@pytest.mark.parametrize(
    ("command", "stdout"),
    [
        # the same envelope from another config
        ("./rdc.sh --config eu-remote machine list", CLI_STDOUT),
        # GitHub's own 403
        (
            "gh api repos/o/r/actions/secrets",
            "gh: Resource not accessible by integration (HTTP 403)",
        ),
        # a bench command printing a 403 that is no status
        ("./rdc.sh --config eu-bench repo list", "processed 403 items\nok"),
        # a bench command that succeeded
        ("./rdc.sh --config eu-bench machine list", json.dumps({"success": True, "data": []})),
        # a document that quotes the block page, the context is never read off the output
        ("cat docs/agent-reference/TRAPS.md", "%s %s HTTP 403" % (BENCH_HOST, CF_PAGE_BODY_ONLY)),
        # a config whose name merely contains bench
        ("./rdc.sh --config eu-bench-old machine list", CLI_STDOUT),
        # output that already names the fix (bench_access preflight, deploy_bench's HINT)
        (
            "npm run deploy:bench",
            "HTTP 403 from %s\nbench is IP-restricted; run "
            "PYTHONPATH=.ci python3 -m rediacc_ci.ops.bench_access add-current" % BENCH_HOST,
        ),
    ],
    ids=["eu-remote", "github", "plain-403", "success", "doc-read", "other-config", "already-told"],
)
def test_control_no_allowlist_note(command, stdout):
    assert context(payload(command, stdout)) == ""


def test_control_another_tool_is_silent():
    doc = payload("./rdc.sh --config eu-bench machine list", CLI_STDOUT, tool="Read")
    assert context(doc) == ""


# ---- the login note --------------------------------------------------------------


def test_the_eu_bench_ip_changed_refusal_names_login_bench():
    text = context(payload("./rdc.sh --config eu-bench machine status hostinger", LOGIN_REFUSAL))
    assert "npm run login:bench" in text
    assert "bench-block:" not in text


@pytest.mark.parametrize(
    ("command", "stdout"),
    [
        ("./rdc.sh --config eu-remote machine status m1", LOGIN_REFUSAL),  # human login there
        ("npm run login:bench", LOGIN_REFUSAL + "\nrun npm run login:bench"),  # already told
        ("./rdc.sh --config eu-bench machine status m1", "Your IP is 192.0.2.1"),  # no marker
    ],
    ids=["eu-remote", "already-told", "no-marker"],
)
def test_control_no_login_note(command, stdout):
    assert context(payload(command, stdout)) == ""


# ---- the member as the harness runs it -------------------------------------------


def test_the_member_script_reads_the_harness_payload_on_stdin():
    doc = payload("./rdc.sh --config eu-bench machine list", CLI_STDOUT, CLI_STDERR)
    proc = subprocess.run(
        [sys.executable, str(MEMBER)],
        input=json.dumps(doc),
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stderr == ""
    parsed = json.loads(proc.stdout)
    assert parsed["hookSpecificOutput"]["hookEventName"] == "PostToolUse"
    assert "bench_access add-current" in parsed["hookSpecificOutput"]["additionalContext"]


def test_the_member_script_is_silent_and_exits_0_on_an_unrelated_call():
    proc = subprocess.run(
        [sys.executable, str(MEMBER)],
        input=json.dumps(payload("ls", "a\nb\n")),
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert (proc.returncode, proc.stdout, proc.stderr) == (0, "", "")


def test_an_unloadable_source_is_said_not_swallowed(monkeypatch):
    def broken():
        raise ImportError("planted")

    monkeypatch.setattr(B, "sources", broken)
    text = context(payload("./rdc.sh --config eu-bench machine list", CLI_STDOUT))
    assert "could not load" in text
    assert "planted" in text


def test_the_member_is_wired_into_post_bash():
    commands = [m["command"] for m in lifecycle.PATTERNS["post-bash"]["members"]]
    assert any("hooks/stop/wl_benchblock.py" in c for c in commands)
