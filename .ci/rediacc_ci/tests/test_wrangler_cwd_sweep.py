"""Round 2 of the wrangler resolution sweep (finding e69747ea): every caller that ran `wrangler.ARGV` with no worker directory now starts in `workers/account`.

`npx --no-install wrangler` resolves only a `node_modules/.bin/wrangler` at or above its cwd (npm 11.21.0 never reads PATH), so a call from the repository root, or with no cwd at all, dies on "npx canceled due to missing packages". Each test points REDIACC_CI_ROOT at a temporary tree, records the cwd the module hands its subprocess, and asks `npx_finds_wrangler` (the same walk npm does) whether that cwd reaches an install. Nothing here reaches wrangler, Cloudflare or bws.
"""

from __future__ import annotations

import pathlib
import subprocess
import types
from typing import Any

import pytest

from rediacc_ci import paths
from rediacc_ci.core import wrangler
from rediacc_ci.enterprise import lab, secrets
from rediacc_ci.housekeeping import cleanup_stale_d1
from rediacc_ci.ops import backup_d1, bench_preflight


def npx_finds_wrangler(cwd: Any) -> bool:
    """npm 11's `--no-install` lookup: a local binary at or above `cwd`, and nothing else."""
    return cwd is not None and wrangler.local_binary(pathlib.Path(cwd)) is not None


@pytest.fixture
def tree(tmp_path, monkeypatch) -> pathlib.Path:
    """A repository root whose only wrangler install is `workers/account`'s."""
    bin_dir = tmp_path / "workers" / "account" / "node_modules" / ".bin"
    bin_dir.mkdir(parents=True)
    (bin_dir / "wrangler").write_text("#!/bin/sh\n", encoding="utf-8")
    monkeypatch.setenv(paths.ROOT_ENV, str(tmp_path))
    return tmp_path


def test_the_control_the_root_and_a_missing_cwd_find_no_install(tree) -> None:
    """THE CONTROL: the lookup the tests below rely on answers no for the places the old code ran from, so it can go red."""
    assert not npx_finds_wrangler(None)
    assert not npx_finds_wrangler(tree)
    assert npx_finds_wrangler(tree / "workers" / "account")


@pytest.mark.usefixtures("tree")
def test_wrangler_push_starts_in_the_account_worker_directory() -> None:
    seen: dict[str, Any] = {}

    def runner(_argv, **kw):
        seen.update(kw)
        return types.SimpleNamespace(returncode=0)

    rc = secrets.wrangler_push(["npx", "--no-install", "wrangler", "secret", "bulk"], "{}", runner)
    assert rc == 0
    assert npx_finds_wrangler(seen.get("cwd"))
    assert seen["input"] == "{}"


@pytest.mark.usefixtures("tree")
def test_rollback_calls_start_in_the_account_worker_directory() -> None:
    """`worker_versions` and `put_version` passed no cwd, which `run_process` turns into the repository root."""
    cwds: list[Any] = []

    def run(_argv, cwd, _env):
        cwds.append(cwd)
        return lab.Proc(0, "[]", "")

    lab.worker_versions("account-eu", run=run)
    lab.put_version("account-eu", "v1", run=run)
    assert len(cwds) == 2
    assert all(npx_finds_wrangler(c) for c in cwds), cwds


@pytest.mark.usefixtures("tree")
def test_bucket_calls_start_in_the_account_worker_directory(monkeypatch, tmp_path) -> None:
    cwds: list[Any] = []

    def fake_run(argv, **kw):
        cwds.append(kw.get("cwd"))
        out = "name:           have-it\n" if argv[-2:] == ["bucket", "list"] else ""
        return subprocess.CompletedProcess(argv, 0, out, "")

    monkeypatch.setattr(bench_preflight.subprocess, "run", fake_run)
    config = tmp_path / "wrangler.test.toml"
    config.write_text('[[r2_buckets]]\nbucket_name = "missing-one"\n', encoding="utf-8")
    assert bench_preflight.buckets(str(config)) == 0
    assert len(cwds) == 2, "a list and a create"
    assert all(npx_finds_wrangler(c) for c in cwds), cwds


@pytest.mark.usefixtures("tree")
def test_stale_d1_list_and_delete_start_in_the_account_worker_directory(monkeypatch) -> None:
    cwds: list[Any] = []

    def fake_run(argv, **kw):
        cwds.append(kw.get("cwd"))
        return subprocess.CompletedProcess(argv, 0, b"[]", b"")

    monkeypatch.setattr(cleanup_stale_d1.subprocess, "run", fake_run)
    cleanup_stale_d1.list_databases()
    assert cleanup_stale_d1.delete_database("db") is True
    assert len(cwds) == 2
    assert all(npx_finds_wrangler(c) for c in cwds), cwds


@pytest.mark.usefixtures("tree")
def test_the_d1_export_starts_in_the_account_worker_directory(monkeypatch) -> None:
    seen: dict[str, Any] = {}

    class FakePopen:
        stdout = None

        def __init__(self, _argv, **kw):
            seen.update(kw)

        def wait(self) -> int:
            return 0

    monkeypatch.setattr(backup_d1.subprocess, "Popen", FakePopen)
    assert backup_d1._export({}, "account-db-eu", "out.sql") == 0
    assert npx_finds_wrangler(seen.get("cwd"))
