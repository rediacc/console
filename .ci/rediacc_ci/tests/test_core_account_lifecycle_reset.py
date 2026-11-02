"""`./run.sh account reset` is DB-only (agent/plans/PLAN-production-key-only.md K3).

The dev gateway signs with the production keypair, so a reset that minted and pushed keys would overwrite the production entries of every region. These cases pin that `reset()` runs no program at all (no `bws_env store-from-env`, no `cache-to`), generates no key, and still removes the four dev database files.
"""

from __future__ import annotations

import subprocess

import pytest

from rediacc_ci.core import account
from rediacc_ci.core import account_lifecycle as lifecycle

DB_FILES = ("account.db", "account.db-shm", "account.db-wal", "account.db-journal")


@pytest.fixture
def recorded(monkeypatch, tmp_path):
    """A recording runner: every `subprocess.run` / `Popen` the module could reach is captured and answered 0, and the key generator records a call instead of minting."""
    calls: list[list[str]] = []

    def fake_run(argv, *_args, **_kwargs):
        calls.append([str(a) for a in argv])
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    def fake_popen(argv, *_args, **_kwargs):
        calls.append([str(a) for a in argv])
        raise AssertionError("reset() started a background program: %r" % (argv,))

    def fake_keys(*_args, **_kwargs):
        calls.append(["generate_crypto_keys"])
        raise AssertionError("reset() generated a keypair")

    account_dir = tmp_path / "private" / "account"
    account_dir.mkdir(parents=True)
    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    monkeypatch.setattr(account, "generate_crypto_keys", fake_keys)
    monkeypatch.setattr(account, "account_dir", lambda *_a, **_k: str(account_dir))
    return calls, account_dir


def test_reset_runs_no_program_and_removes_the_four_db_files(recorded, capsys) -> None:
    calls, account_dir = recorded
    for name in DB_FILES:
        (account_dir / name).write_text("sqlite\n", encoding="utf-8")
    keep = account_dir / ".cache" / "public-keys.env"
    keep.parent.mkdir()
    keep.write_text("ACCOUNT_ED25519_PUBLIC_KEY=pub\n", encoding="utf-8")
    (account_dir / "account.db.bak").write_text("backup\n", encoding="utf-8")

    assert lifecycle.reset() == 0

    assert calls == [], "reset() reached a program or the key generator: %r" % calls
    assert not any((account_dir / name).exists() for name in DB_FILES)
    # Only the database goes: the public-key cache and an unrelated sibling stay.
    assert keep.read_text(encoding="utf-8") == "ACCOUNT_ED25519_PUBLIC_KEY=pub\n"
    assert (account_dir / "account.db.bak").is_file()
    err = capsys.readouterr().err
    assert "production" in err
    for name in DB_FILES:
        assert "Removing %s" % name in err


def test_reset_with_no_database_is_green_and_still_runs_nothing(recorded) -> None:
    calls, _account_dir = recorded
    assert lifecycle.reset() == 0
    assert calls == []


def test_the_module_no_longer_carries_the_mint_or_its_specs() -> None:
    for gone in ("RESET_STORE_SPECS", "RESET_CACHE_SPECS", "_bws"):
        assert not hasattr(lifecycle, gone), "%s is back in account_lifecycle" % gone


def test_control_the_recorder_sees_a_bitwarden_push(recorded) -> None:
    """CONTROL: the recorder is what `_run` reaches, so the empty transcript above is a real absence and not a recorder that sees nothing."""
    calls, _account_dir = recorded
    status = lifecycle._run(
        ["python3", "-m", "rediacc_ci.core.bws_env", "store-from-env", "A > B"],
        extra_env={"B": "x"},
    )
    assert status == 0
    assert calls == [["python3", "-m", "rediacc_ci.core.bws_env", "store-from-env", "A > B"]]
