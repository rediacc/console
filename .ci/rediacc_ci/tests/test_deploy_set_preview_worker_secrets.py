"""`rediacc_ci.deploy.set_preview_worker_secrets` against a recording fake `npx`.

Nothing here reaches Cloudflare: the fake logs its exact argv AND the bytes on its stdin, and every case uses fixture secrets whose values are two characters long. The observable effect of the program is one JSON document handed to `wrangler secret bulk`, so every case that reaches wrangler asserts the recorded stdin, and the happy path pins it against literal bytes.

The preview Worker signs through its LICENSE_SIGNER service binding (signer-bench-eu), so the pusher sends the signer's PUBLIC key only. `test_no_licence_private_key_is_pushed_or_required` pins that a private key in the environment never reaches the document and never gates the run.

The bash twin `.ci/scripts/deploy/set-preview-worker-secrets.sh` and its frozen golden no longer back this module: the twin pushed a fifteenth key, the private one, that this script no longer sends, so agreement with it would pin the defect.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import typing

from rediacc_ci import paths
from rediacc_ci.deploy import set_preview_worker_secrets as port

if typing.TYPE_CHECKING:
    import pathlib

    import pytest

ROOT = paths.repo_root()
PORT = ROOT / ".ci" / "rediacc_ci" / "deploy" / "set_preview_worker_secrets.py"

# The ten values the script refuses to deploy without, plus the PR number. Two characters each, and visibly not credentials.
FIXTURE_ENV = {
    "PR_NUMBER": "123",
    "ACCOUNT_ED25519_PUBLIC_KEY": "e2",
    "ACCOUNT_X25519_PRIVATE_KEY": "x1",
    "ACCOUNT_X25519_PUBLIC_KEY": "x2",
    "ACCOUNT_SERVER_API_KEY": "ak",
    "ACCOUNT_JWT_SECRET": "jw",
    "ROOT_EMAIL": "root@example.invalid",
    "AWS_SES_ACCESS_KEY_ID": "sk",
    "AWS_SES_SECRET_ACCESS_KEY": "ss",
    "AWS_SES_REGION": "eu-west-1",
    "CLOUDFLARE_TURNSTILE_SECRET_KEY": "ts",
}

FAKE_NPX = """#!/usr/bin/python3
import os
import sys

argv = sys.argv[1:]
payload = sys.stdin.read()
log = os.environ["FAKE_CALL_LOG"]
with open(log, "a") as fh:
    fh.write("npx\\t" + "\\t".join(argv) + "\\n")
    fh.write("STDIN<<<" + payload + ">>>\\n")

rc = int(os.environ.get("FAKE_NPX_RC", "0"))
if rc:
    sys.stderr.write("wrangler: failed to set secrets\\n")
    sys.exit(rc)
sys.stdout.write("Finished processing secrets JSON file.\\n")
"""

# `jq` is a real prerequisite (the port shells out to it), and `uname` / `dirname` are kept so a tool leaking in shows up as a behaviour change.
PATH_MINIMUM = ("jq", "uname", "dirname")
OK_LINE = "✓ Set 14 secrets on pr-123 in one bulk call\n"


def _bin(tmp_path: pathlib.Path, name: str, *, drop: str = "") -> str:
    stub = tmp_path / name
    stub.mkdir(parents=True, exist_ok=True)
    for real_name in PATH_MINIMUM:
        if real_name == drop:
            continue
        real = shutil.which(real_name)
        assert real is not None, f"{real_name} is missing from this machine"
        link = stub / real_name
        if not link.exists():
            link.symlink_to(real)
    if drop != "npx":
        npx = stub / "npx"
        npx.write_text(FAKE_NPX, encoding="utf-8")
        npx.chmod(0o755)
    else:
        assert shutil.which("npx", path=str(stub)) is None, "npx leaked into the stub PATH"
    if drop:
        assert shutil.which(drop, path=str(stub)) is None, f"{drop} leaked into the stub PATH"
    return str(stub)


def _run(
    tmp_path: pathlib.Path,
    *,
    drop: str = "",
    drop_env: tuple[str, ...] = (),
    env_over: dict[str, str] | None = None,
    **extra: str,
):
    call_log = tmp_path / "calls.log"
    call_log.write_text("", encoding="utf-8")
    env = {
        "PATH": _bin(tmp_path, "bin", drop=drop),
        "HOME": os.environ.get("HOME", "/tmp"),
        "LC_ALL": "C.UTF-8",
        "LANG": "C.UTF-8",
        "PYTHONPATH": str(ROOT / ".ci"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "FAKE_CALL_LOG": str(call_log),
        **FIXTURE_ENV,
    }
    env.update(env_over or {})
    env.update(extra)
    for name in drop_env:
        env.pop(name, None)
    proc = subprocess.run(
        [sys.executable, str(PORT)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=120,
        input="",
    )
    return proc, call_log.read_text(encoding="utf-8")


def document(calls: str) -> str:
    """The bytes the recorded call put on wrangler's stdin."""
    match = re.search(r"STDIN<<<(.*)>>>\n", calls, re.DOTALL)
    assert match is not None, f"no wrangler call was recorded in {calls!r}"
    return match.group(1)


def guard_text(name: str, worker: str = "pr-123") -> str:
    return (
        f"{port.SELF}: {name} is EMPTY for WORKER_NAME={worker}.\n"
        "  The Worker's schema either accepts an empty value and silently disables the\n"
        "  feature, or rejects it on every request; this refuses to deploy instead.\n"
    )


def test_the_bulk_call_and_its_document_are_pinned_in_full(tmp_path: pathlib.Path) -> None:
    """ONE CALL, PINNED AGAINST LITERAL BYTES: the argv, then the fourteen keys in order, the four legitimately-empty ones present as empty strings, and no licence private key."""
    proc, calls = _run(tmp_path)
    assert proc.returncode == 0
    assert calls.splitlines()[0] == "npx\t--no-install\twrangler\tsecret\tbulk\t--name\tpr-123"
    assert document(calls) == (
        "{\n"
        '  "ACCOUNT_ED25519_PUBLIC_KEY": "e2",\n'
        '  "ACCOUNT_X25519_PRIVATE_KEY": "x1",\n'
        '  "ACCOUNT_X25519_PUBLIC_KEY": "x2",\n'
        '  "ACCOUNT_SERVER_API_KEY": "ak",\n'
        '  "ACCOUNT_JWT_SECRET": "jw",\n'
        '  "STRIPE_SECRET_KEY": "",\n'
        '  "STRIPE_WEBHOOK_SECRET": "",\n'
        '  "ROOT_EMAIL": "root@example.invalid",\n'
        '  "AWS_SES_ACCESS_KEY_ID": "sk",\n'
        '  "AWS_SES_SECRET_ACCESS_KEY": "ss",\n'
        '  "AWS_SES_REGION": "eu-west-1",\n'
        '  "AWS_SES_FROM": "",\n'
        '  "AWS_SES_CONFIGURATION_SET": "",\n'
        '  "CLOUDFLARE_TURNSTILE_SECRET_KEY": "ts"\n'
        "}\n"
    )
    assert proc.stdout == "Finished processing secrets JSON file.\n", "wrangler's own output"
    assert proc.stderr == OK_LINE


def test_no_licence_private_key_is_pushed_or_required(tmp_path: pathlib.Path) -> None:
    """The preview Worker signs through LICENSE_SIGNER, so a private key in the environment never reaches the document, and its absence never refuses the run."""
    proc, calls = _run(tmp_path, ACCOUNT_ED25519_PRIVATE_KEY="SECRET-PRIVATE")
    assert proc.returncode == 0
    assert "ED25519_PRIVATE_KEY" not in document(calls)
    assert "SECRET-PRIVATE" not in calls
    assert "ACCOUNT_ED25519_PRIVATE_KEY" not in {key for key, _var in port.KEYS}
    assert "ACCOUNT_ED25519_PRIVATE_KEY" not in port.REQUIRED_NONEMPTY
    assert "ACCOUNT_ED25519_PUBLIC_KEY" in port.REQUIRED_NONEMPTY


def test_the_worker_name_is_the_pr_number_prefixed(tmp_path: pathlib.Path) -> None:
    proc, calls = _run(tmp_path, PR_NUMBER="9001")
    assert "--name\tpr-9001" in calls
    assert proc.stderr == OK_LINE.replace("pr-123", "pr-9001")


def test_stripe_is_deliberately_not_demanded(tmp_path: pathlib.Path) -> None:
    """A preview without billing is a legitimate state: adding Stripe to the guard list would turn every preview red."""
    proc, calls = _run(tmp_path)
    assert proc.returncode == 0
    assert '"STRIPE_SECRET_KEY": ""' in document(calls)
    assert "STRIPE_SECRET_KEY" not in port.REQUIRED_NONEMPTY
    assert "STRIPE_WEBHOOK_SECRET" not in port.REQUIRED_NONEMPTY


def test_a_present_stripe_key_reaches_the_document(tmp_path: pathlib.Path) -> None:
    # PASSED AS A DICT: ruff's S106 keys on the argument name.
    stripe = {"STRIPE_SECRET_KEY": "sk_test_x", "STRIPE_WEBHOOK_SECRET": "whsec_x"}
    _proc, calls = _run(tmp_path, env_over=stripe)
    assert '"STRIPE_SECRET_KEY": "sk_test_x"' in document(calls)
    assert '"STRIPE_WEBHOOK_SECRET": "whsec_x"' in document(calls)


def test_every_one_of_the_ten_guards_fires_with_its_own_name(tmp_path: pathlib.Path) -> None:
    """One case per guard, each driven EMPTY rather than absent."""
    assert len(port.REQUIRED_NONEMPTY) == 10
    for name in port.REQUIRED_NONEMPTY:
        case = tmp_path / f"guard-{name}"
        case.mkdir()
        proc, calls = _run(case, env_over={name: ""})
        assert proc.returncode == 1, f"{name}: an empty value was accepted"
        assert proc.stdout == ""
        assert proc.stderr == guard_text(name)
        assert calls == "", f"{name}: a refused run still called wrangler"


def test_an_absent_value_refuses_exactly_as_an_empty_one_does(tmp_path: pathlib.Path) -> None:
    proc, _calls = _run(tmp_path, drop_env=("ACCOUNT_JWT_SECRET",))
    assert proc.returncode == 1
    assert proc.stderr == guard_text("ACCOUNT_JWT_SECRET")


def test_the_first_empty_guard_wins_and_the_rest_never_run(tmp_path: pathlib.Path) -> None:
    """ORDER IS OBSERVABLE: with every guarded value empty, the message names the first one only."""
    blanks = dict.fromkeys(port.REQUIRED_NONEMPTY, "")
    proc, _calls = _run(tmp_path, env_over=blanks)
    assert proc.stderr.startswith(f"{port.SELF}: ACCOUNT_ED25519_PUBLIC_KEY is EMPTY")
    assert proc.stderr.count("is EMPTY") == 1


def test_missing_jq_refuses_before_anything_else(tmp_path: pathlib.Path) -> None:
    proc, calls = _run(tmp_path, drop="jq")
    assert proc.returncode == 1
    assert proc.stderr == "✗ Required command 'jq' is not available\n"
    assert proc.stdout == ""
    assert calls == ""


def test_missing_npx_refuses_after_jq(tmp_path: pathlib.Path) -> None:
    proc, _calls = _run(tmp_path, drop="npx")
    assert proc.returncode == 1
    assert proc.stderr == "✗ Required command 'npx' is not available\n"


def test_the_tool_checks_run_before_the_pr_number_check(tmp_path: pathlib.Path) -> None:
    proc, _calls = _run(tmp_path, drop="jq", drop_env=("PR_NUMBER",))
    assert proc.stderr == "✗ Required command 'jq' is not available\n"


def test_a_missing_or_empty_pr_number_refuses_without_a_call(tmp_path: pathlib.Path) -> None:
    """`:?` semantics: unset and empty refuse alike, so a Worker literally named `pr-` is never written."""
    unset = tmp_path / "unset"
    unset.mkdir()
    empty = tmp_path / "empty"
    empty.mkdir()
    for proc, calls in (
        _run(unset, drop_env=("PR_NUMBER",)),
        _run(empty, PR_NUMBER=""),
    ):
        assert proc.returncode == 1
        assert proc.stderr == port.MISSING_PR_NUMBER + "\n"
        assert proc.stdout == ""
        assert calls == "", "a missing PR number still reached wrangler"


def test_a_wrangler_failure_ends_the_run_with_its_status(tmp_path: pathlib.Path) -> None:
    """wrangler's status becomes the script's, and the closing line does NOT print."""
    proc, _calls = _run(tmp_path, FAKE_NPX_RC="7")
    assert proc.returncode == 7
    assert proc.stderr == "wrangler: failed to set secrets\n"
    assert "Set 14 secrets" not in proc.stderr
    assert proc.stdout == ""


def test_the_document_carries_raw_utf8_the_way_jq_writes_it(tmp_path: pathlib.Path) -> None:
    """WHY THE PORT SHELLS OUT TO `jq`: jq emits raw UTF-8, `json.dumps` defaults to `\\uXXXX` escapes."""
    exotic = "Ünïcødé 7Ω"
    _proc, calls = _run(tmp_path, ROOT_EMAIL=exotic)
    assert f'"ROOT_EMAIL": "{exotic}"' in document(calls)
    assert json.dumps({"ROOT_EMAIL": exotic}) == (
        '{"ROOT_EMAIL": "\\u00dcn\\u00efc\\u00f8d\\u00e9 7\\u03a9"}'
    ), "json.dumps stopped escaping non-ASCII; the reasoning in the port's docstring changed"


def test_a_value_with_quotes_and_newlines_survives_intact(tmp_path: pathlib.Path) -> None:
    awkward = {"ACCOUNT_JWT_SECRET": 'a"b\nc\\d'}
    _proc, calls = _run(tmp_path, env_over=awkward)
    assert '"ACCOUNT_JWT_SECRET": "a\\"b\\nc\\\\d"' in document(calls)


def test_the_closing_line_counts_what_is_actually_sent() -> None:
    assert len(port.KEYS) == port.SECRET_COUNT_CLAIM == 14


def test_pure_helpers() -> None:
    assert port.SELF == "rediacc_ci.deploy.set_preview_worker_secrets"
    assert port.worker_name("42") == "pr-42"
    assert port.jq_argv() == ["jq", port.jq_filter()], (
        "the program only; the values travel on stdin"
    )
    document_in = json.loads(port.jq_input({"ROOT_EMAIL": "a@b", "AWS_SES_FROM": "f@g"}))
    assert list(document_in) == [var for _key, var in port.KEYS]
    assert document_in["ed25519_pub"] == "", "an absent value is the empty string"
    assert document_in["admin"] == "a@b"
    assert port.jq_filter().startswith("{ACCOUNT_ED25519_PUBLIC_KEY: .ed25519_pub")
    assert port.jq_filter().endswith("CLOUDFLARE_TURNSTILE_SECRET_KEY: .turnstile}")
    assert port.wrangler_argv("pr-7") == [
        "npx",
        "--no-install",
        "wrangler",
        "secret",
        "bulk",
        "--name",
        "pr-7",
    ]
    guard = port.GuardError("ROOT_EMAIL", "pr-7")
    assert guard.lines()[0] == f"{port.SELF}: ROOT_EMAIL is EMPTY for WORKER_NAME=pr-7."
    assert len(guard.lines()) == 3


# ---------------------------------------------------------------- no value on any child's argv (worklist #a2d19f74)


def test_no_secret_value_reaches_any_child_argv(monkeypatch: pytest.MonkeyPatch) -> None:
    """`argv` is visible in `ps` for the length of the call, and the twin, like this port until #a2d19f74, passed every value to `jq --arg`. Every child this module starts is recorded: jq runs for real, wrangler is answered by the recorder, and no sentinel value may appear in any argv while every one of them must reach wrangler's stdin."""
    sentinels = {
        name: "SENTINEL-%s-4b1d" % name.lower() for name in FIXTURE_ENV if name != "PR_NUMBER"
    }
    for name, value in {**FIXTURE_ENV, **sentinels}.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(port.common, "require_cmd", lambda *_a, **_k: "/bin/true")

    real_run = subprocess.run
    calls: list[tuple[list[str], object]] = []

    def recording_run(argv, **kw):
        calls.append((list(argv), kw.get("input")))
        if argv[0] == "npx":
            return subprocess.CompletedProcess(argv, 0)
        return real_run(argv, **kw)

    monkeypatch.setattr(port.subprocess, "run", recording_run)
    assert port.main([]) == 0
    assert [argv[0] for argv, _stdin in calls] == ["jq", "npx"], calls
    for argv, _stdin in calls:
        for value in sentinels.values():
            assert not any(value in arg for arg in argv), "a secret value is on argv: %r" % argv[0]
    for name, value in sentinels.items():
        assert value in str(calls[-1][1]), "%s never reached wrangler's stdin" % name


def test_wrangler_starts_in_the_worker_directory(monkeypatch: pytest.MonkeyPatch) -> None:
    """Run 41348962671, Deploy Preview: `npx --no-install wrangler` ran from the repo root, which has no local wrangler, and died on `npx canceled due to missing packages`. Only workers/www is installed by the job."""
    for name, value in FIXTURE_ENV.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(port.common, "require_cmd", lambda *_a, **_k: "/bin/true")
    real_run = subprocess.run
    cwds: dict[str, object] = {}

    def recording_run(argv, **kw):
        cwds[argv[0]] = kw.get("cwd")
        if argv[0] == "npx":
            return subprocess.CompletedProcess(argv, 0)
        return real_run(argv, **kw)

    monkeypatch.setattr(port.subprocess, "run", recording_run)
    assert port.main([]) == 0
    assert cwds["npx"] == port.paths.repo_root() / "workers" / "www"
    assert (port.paths.repo_root() / "workers" / "www").is_dir()
