"""No drill hands a secret to a child on its argv (worklist #773eccc5).

Every argument of every process is readable through `ps` and `/proc/<pid>/cmdline` for as long as the process lives, so the dev API token, the minted config-enroll token and the store password reach `rdc` on stdin (`subscription login --token -`) or in its environment, never as an argument. Each case drives one call site with a recording drill: the commands are recorded rather than run, and every recorded argv is searched for the secret.
"""

from __future__ import annotations

import sys
import types
import typing

import pytest

from rediacc_ci.drills import backup, lib, transfer
from rediacc_ci.drills import license as license_drill

if typing.TYPE_CHECKING:
    import collections.abc
    import pathlib

API_TOKEN = "rdt_drill_secret_token_0123456789"
MINTED_TOKEN = "rdt_minted_enroll_token_9876543210"


class Recorder(backup.BackupDrill):
    """A drill whose commands are recorded, not run: (argv, env overrides, stdin)."""

    def __init__(self, root: pathlib.Path) -> None:
        super().__init__("argv-secrets", keep_work=False)
        self.root = root
        self.calls: list[tuple[list[str], dict[str, str], str | None]] = []

    def run(
        self, argv: list[str], env: dict[str, str] | None = None, stdin_text: str | None = None
    ) -> None:
        base = self.cli_env()
        overrides = {k: v for k, v in (env or {}).items() if base.get(k) != v}
        self.calls.append((list(argv), overrides, stdin_text))
        self.last_cmd = " ".join(argv)
        self.code = 0


@pytest.fixture
def drill(tmp_path: pathlib.Path) -> collections.abc.Iterator[Recorder]:
    d = Recorder(tmp_path)
    d.init()
    yield d
    d.teardown()


def assert_off_argv(d: Recorder, secret: str) -> None:
    assert d.calls, "the call site ran no command"
    for argv, _env, _stdin in d.calls:
        leaked = [arg for arg in argv if secret in arg]
        assert not leaked, "a secret reached a child argv: %r" % argv


def login_call(d: Recorder) -> tuple[list[str], dict[str, str], str | None]:
    found = [c for c in d.calls if c[0][1:3] == ["subscription", "login"]]
    assert len(found) == 1, d.calls
    return found[0]


def test_license_setup_logs_in_with_the_token_on_stdin(
    drill: Recorder, monkeypatch: pytest.MonkeyPatch
) -> None:
    opts = types.SimpleNamespace(
        ssh_key="/dev/null",
        ssh_user="root",
        vm_ip="192.0.2.1",
        vm2_ip="192.0.2.2",
        vm_renet="renet",
        enabled=lambda _leg: False,
    )
    lic = license_drill.License(drill, typing.cast("license_drill.Options", opts))
    lic.api_token = API_TOKEN
    lic.server_url = "http://127.0.0.1:1"
    monkeypatch.setattr(lic, "verify_renet_key", lambda: None)
    lic.setup_config()
    assert_off_argv(drill, API_TOKEN)
    argv, _env, stdin = login_call(drill)
    assert argv[argv.index("--token") + 1] == "-"
    assert stdin == API_TOKEN


def test_backup_cli_config_logs_in_with_the_token_on_stdin(
    drill: Recorder, monkeypatch: pytest.MonkeyPatch
) -> None:
    bk = backup.Backup(drill, typing.cast("backup.Options", types.SimpleNamespace(bucket="b")))
    bk.api_token = API_TOKEN
    monkeypatch.setattr(drill, "server_url", lambda: "http://127.0.0.1:1")
    bk.setup_cli_config()
    assert_off_argv(drill, API_TOKEN)
    argv, _env, stdin = login_call(drill)
    assert argv[argv.index("--token") + 1] == "-"
    assert stdin == API_TOKEN


def test_transfer_enrollment_carries_the_token_and_password_in_the_environment(
    drill: Recorder, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`config remote enable --master-password` is a FLAG: the master password rides REDIACC_STORE_MASTER_PASSWORD and the minted token REDIACC_TOKEN."""
    tr = transfer.Transfer(drill, restart_gateway=False)
    tr.device1 = tr.device2 = str(drill.work)
    tr.server_url = "http://127.0.0.1:1"

    def mint(_name: str) -> None:
        tr.minted_token = MINTED_TOKEN

    monkeypatch.setattr(tr, "init_config", lambda _home, _name: None)
    monkeypatch.setattr(tr, "mint_token", mint)
    tr.phase_seed_on_enable()
    assert_off_argv(drill, MINTED_TOKEN)
    assert_off_argv(drill, transfer.STORE_PASSWORD)
    enable = [c for c in drill.calls if c[0][1:4] == ["config", "remote", "enable"]]
    assert len(enable) == 1
    argv, env, _stdin = enable[0]
    assert argv[argv.index("--master-password") + 1].startswith("--"), (
        "--master-password takes no value"
    )
    assert env["REDIACC_TOKEN"] == MINTED_TOKEN
    assert env["REDIACC_STORE_MASTER_PASSWORD"] == transfer.STORE_PASSWORD


def test_run_feeds_stdin_text_to_the_child_and_keeps_it_off_last_cmd() -> None:
    d = lib.Drill("argv-secrets-run", keep_work=False)
    d.init()
    try:
        d.run(
            [sys.executable, "-c", "import sys; sys.stdout.write(sys.stdin.read()[::-1])"],
            stdin_text="abc",
        )
        assert d.code == 0
        assert d.stdout_text() == "cba"
        assert "abc" not in d.last_cmd
    finally:
        d.teardown()
