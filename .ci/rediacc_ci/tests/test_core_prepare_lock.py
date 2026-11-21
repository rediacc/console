"""`core.prepare_lock`: a reader of `packages/shared/dist` never sees it missing while `ensure_packages_built` rebuilds it, and two builders build once (worklist #6fbf7fa3).

The builder is the real `ensure_packages_built` over a sandbox checkout; only its one external call, `python3 -m rediacc_ci.setup.build_packages`, is replaced by a fake that does what that module does to the tree: delete `packages/shared/dist`, take a while, write it again. Each test has a CONTROL that runs the same scenario with the lock made a no-op, the shape of the code before this change, and asserts the race shows.
"""

from __future__ import annotations

import contextlib
import os
import shutil
import subprocess
import threading
import time
from typing import TYPE_CHECKING, Any

import pytest

from rediacc_ci.core import account_lifecycle, local_common, prepare_lock

if TYPE_CHECKING:
    import pathlib
    from collections.abc import Iterator

BUILD_S = 0.3


def _sandbox(tmp_path: pathlib.Path) -> pathlib.Path:
    root = tmp_path / "checkout"
    for package in ("shared", "provisioning"):
        (root / "packages" / package / "src").mkdir(parents=True)
        (root / "packages" / package / "src" / "index.ts").write_text("export const x = 1;\n")
        (root / "packages" / package / "dist").mkdir()
        (root / "packages" / package / "dist" / "index.js").write_text("export const x = 1;\n")
    (root / ".gitignore").write_text("dist/\n.ci/\n")
    git = ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false"]
    subprocess.run([*git, "init", "-q"], cwd=root, check=True)
    subprocess.run([*git, "add", "-A"], cwd=root, check=True)
    subprocess.run([*git, "commit", "-q", "-m", "x"], cwd=root, check=True)
    return root


class FakeBuild:
    """`build_packages` as the tree sees it: `rm -rf packages/shared/dist`, then `tsc` writing it again."""

    def __init__(self, root: pathlib.Path) -> None:
        self.root = root
        self.runs = 0

    def __call__(self, argv: list[str], **_kw: Any) -> None:
        assert argv[-1] == "rediacc_ci.setup.build_packages", argv
        self.runs += 1
        dist = self.root / "packages" / "shared" / "dist"
        shutil.rmtree(dist, ignore_errors=True)
        time.sleep(BUILD_S)
        dist.mkdir(exist_ok=True)
        (dist / "index.js").write_text("export const x = 2;\n")


@contextlib.contextmanager
def _no_lock(_root: str, *, shared: bool, wait_s: float = 0.0) -> Iterator[None]:
    del shared, wait_s
    yield


def _reader_during_rebuild(root: pathlib.Path) -> tuple[int, FakeBuild]:
    """A reader holds the lock shared and reads `dist/index.js` while a builder thread runs `ensure_packages_built`; the number of reads that found it missing."""
    env = dict(os.environ, LOCAL_ROOT_DIR=str(root))
    build = FakeBuild(root)
    target = root / "packages" / "shared" / "dist" / "index.js"
    misses = 0
    # Replaced BEFORE the thread starts: the real `_must` would run the real `build_packages`, which deletes this checkout's own `packages/shared/dist`.
    local_common._must = build
    with prepare_lock.held(str(root), shared=True):
        builder = threading.Thread(target=local_common.ensure_packages_built, args=(env,))
        builder.start()
        deadline = time.monotonic() + 3 * BUILD_S
        while time.monotonic() < deadline:
            if not target.is_file():
                misses += 1
            time.sleep(0.005)
    builder.join(10)
    assert not builder.is_alive()
    return misses, build


@pytest.fixture(autouse=True)
def restore_must() -> Iterator[None]:
    saved = local_common._must
    yield
    local_common._must = saved


def test_a_reader_holding_the_lock_never_sees_dist_missing_during_a_rebuild(
    tmp_path: pathlib.Path,
) -> None:
    root = _sandbox(tmp_path)
    misses, build = _reader_during_rebuild(root)
    assert misses == 0
    # The build waited for the reader and then ran: the stamp was stale.
    assert build.runs == 1
    assert (
        root / "packages" / "shared" / "dist" / "index.js"
    ).read_text() == "export const x = 2;\n"


def test_control_without_the_lock_the_reader_sees_dist_missing(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(prepare_lock, "held", _no_lock)
    root = _sandbox(tmp_path)
    misses, build = _reader_during_rebuild(root)
    assert build.runs == 1
    assert misses > 0, "the probe cannot see the race it exists to catch"


def _two_builders(root: pathlib.Path) -> FakeBuild:
    env = dict(os.environ, LOCAL_ROOT_DIR=str(root))
    build = FakeBuild(root)
    local_common._must = build
    threads = [
        threading.Thread(target=local_common.ensure_packages_built, args=(env,)) for _ in range(2)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(10)
    return build


def test_two_builders_build_once(tmp_path: pathlib.Path) -> None:
    build = _two_builders(_sandbox(tmp_path))
    assert build.runs == 1


def test_control_without_the_lock_two_builders_both_delete_dist(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(prepare_lock, "held", _no_lock)
    build = _two_builders(_sandbox(tmp_path))
    assert build.runs == 2


def test_a_current_stamp_takes_no_lock(tmp_path: pathlib.Path) -> None:
    """The reader's own children: with the stamp current, `ensure_packages_built` returns while the parent holds the lock shared, instead of waiting on it."""
    root = _sandbox(tmp_path)
    env = dict(os.environ, LOCAL_ROOT_DIR=str(root))
    local_common._must = FakeBuild(root)
    local_common.ensure_packages_built(env)
    with prepare_lock.held(str(root), shared=True):
        started = time.monotonic()
        assert local_common.ensure_packages_built(env)
        assert time.monotonic() - started < 2


def test_an_exclusive_wait_on_a_held_lock_ends_with_a_named_timeout(tmp_path: pathlib.Path) -> None:
    root = str(tmp_path)
    with (
        prepare_lock.held(root, shared=True),
        pytest.raises(prepare_lock.PrepareLockTimeoutError, match="stayed held for 0 s"),
        prepare_lock.held(root, shared=False, wait_s=0.3),
    ):
        pass


def test_the_lock_file_is_outside_the_checkout_and_one_per_real_path(
    tmp_path: pathlib.Path,
) -> None:
    (tmp_path / "real").mkdir()
    (tmp_path / "link").symlink_to(tmp_path / "real")
    path = prepare_lock.lock_path(str(tmp_path / "real"))
    assert path == prepare_lock.lock_path(str(tmp_path / "link"))
    assert not path.startswith(str(tmp_path))
    assert path != prepare_lock.lock_path(str(tmp_path))


class _Held:
    """Stands in for `prepare_lock.held`, recording the order of enter, exit and the work done between them."""

    def __init__(self) -> None:
        self.events: list[str] = []

    def __call__(self, _root: str, *, shared: bool, **_kw: Any):
        events = self.events

        @contextlib.contextmanager
        def cm():
            events.append("enter shared" if shared else "enter exclusive")
            try:
                yield
            finally:
                events.append("exit")

        return cm()


def test_ensure_deps_takes_the_exclusive_lock_and_rechecks_the_stamp_under_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """20fdede2.1: a preparer that waited on the lock finds the install done under it and installs nothing."""
    held = _Held()
    answers = iter([False, True])  # stale before the lock, current once it is held
    monkeypatch.setattr(local_common.prepare_lock, "held", held)
    monkeypatch.setattr(local_common, "deps_are_current", lambda _env=None: next(answers))

    def no_install(*_a: Any, **_k: Any) -> None:
        raise AssertionError(
            "the install must not run when the stamp became current under the lock"
        )

    monkeypatch.setattr(local_common, "_must", no_install)
    assert local_common.ensure_deps({}) is True
    assert held.events == ["enter exclusive", "exit"]


def test_ensure_deps_installs_under_the_exclusive_lock_when_still_stale(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    held = _Held()
    ran: list[tuple[str, ...]] = []
    monkeypatch.setattr(local_common.prepare_lock, "held", held)
    monkeypatch.setattr(local_common, "deps_are_current", lambda _env=None: False)
    monkeypatch.setattr(
        local_common, "_must", lambda argv, **_k: ran.append((*argv, *held.events[-1:]))
    )
    monkeypatch.setattr(local_common, "ensure_cpu_features_gypi", lambda _nm: True)
    monkeypatch.setattr(local_common, "write_stamp_hash", lambda *_a: None)
    monkeypatch.setattr(local_common, "deps_hash", lambda _env=None: "h")
    assert local_common.ensure_deps({}) is True
    assert held.events == ["enter exclusive", "exit"]
    assert ran
    assert all(call[-1] == "enter exclusive" for call in ran)


def test_the_account_test_run_holds_the_prepare_lock_shared_around_vitest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """20fdede2.2: the lock is taken before vitest starts and released after it ends."""
    held = _Held()
    monkeypatch.setattr(account_lifecycle.prepare_lock, "held", held)
    monkeypatch.setattr(account_lifecycle, "_check_node", lambda: None)
    monkeypatch.setattr(account_lifecycle.local_common, "ensure_packages_built", lambda: True)
    monkeypatch.setattr(account_lifecycle.account, "account_dir", lambda: ".")
    monkeypatch.setattr(account_lifecycle, "_cd_or_die", lambda _d: None)
    monkeypatch.setattr(account_lifecycle.local_common, "local_root_dir", lambda *_a: ".")

    def fake_run(_argv: list[str], **_k: Any) -> int:
        held.events.append("vitest")
        return 0

    monkeypatch.setattr(account_lifecycle, "_run", fake_run)
    assert account_lifecycle.test([]) == 0
    assert held.events == ["enter shared", "vitest", "exit"]
