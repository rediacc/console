"""`check:ci-proxy-cost-guard` (`.ci/scripts/quality/check_proxy_cost_guard.py`): the executor proxy's `max_instances` and `sleepAfter` stay at or under the budget in PLAN-cloudflare-proxy.md section 4 (box A5, missing test 9).

CONTROL FIRST, AND NEVER ON THE REAL CONFIG. Every plant goes into a COPY of `workers/proxy/wrangler.toml` and `workers/proxy/src/` under `tmp_path`, and the gate is pointed at the copy with `--root`. The unplanted copy must pass first, so a red on a plant is the plant's doing and not a broken fixture. The real files are hashed before and after the module, and any change is a failure.

THE PLANTED DEFECTS, red before the gate existed and green only with it: `max_instances = 20` (the plan's acceptance value), `sleepAfter = '10m'` (the library default, written out), and the `sleepAfter` line deleted (the same default, silently).
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
import typing

import pytest

from rediacc_ci import paths

if typing.TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()
GATE = ROOT / ".ci" / "scripts" / "quality" / "check_proxy_cost_guard.py"
WRANGLER = ROOT / "workers" / "proxy" / "wrangler.toml"
BENCH_WRANGLER = ROOT / "workers" / "proxy" / "wrangler.bench.toml"
SRC = ROOT / "workers" / "proxy" / "src"
INDEX_REL = ("workers", "proxy", "src", "index.ts")


def _digest() -> str:
    h = hashlib.sha256(WRANGLER.read_bytes())
    h.update(BENCH_WRANGLER.read_bytes())
    for path in sorted(SRC.rglob("*")):
        if path.is_file():
            h.update(path.as_posix().encode())
            h.update(path.read_bytes())
    return h.hexdigest()


@pytest.fixture(scope="module", autouse=True)
def real_config_untouched():
    before = _digest()
    yield
    assert _digest() == before, "a test changed the real proxy config; plants belong in copies"


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(GATE), *args],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )


def _copy(tmp_path: pathlib.Path) -> pathlib.Path:
    root = tmp_path / "root"
    (root / "workers" / "proxy").mkdir(parents=True)
    shutil.copy2(WRANGLER, root / "workers" / "proxy" / "wrangler.toml")
    shutil.copy2(BENCH_WRANGLER, root / "workers" / "proxy" / "wrangler.bench.toml")
    shutil.copytree(SRC, root / "workers" / "proxy" / "src")
    return root


def _replace(path: pathlib.Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    assert text.count(old) == 1, "the plant's anchor %r must occur exactly once in %s" % (old, path)
    path.write_text(text.replace(old, new), encoding="utf-8")


def test_the_real_tree_is_within_budget() -> None:
    proc = _run()
    assert proc.returncode == 0, proc.stderr
    assert "2 container(s) at max_instances <= 2 in 2 config(s)" in proc.stdout
    assert "the bench config naming bench only" in proc.stdout
    assert "1 sleepAfter assignment(s)" in proc.stdout


def test_the_unplanted_copy_passes_so_the_plants_below_are_what_fires(
    tmp_path: pathlib.Path,
) -> None:
    proc = _run("--root", str(_copy(tmp_path)))
    assert proc.returncode == 0, proc.stderr


def test_a_planted_max_instances_of_twenty_fails(tmp_path: pathlib.Path) -> None:
    root = _copy(tmp_path)
    toml = root / "workers" / "proxy" / "wrangler.toml"
    _replace(toml, "max_instances = 2\n", "max_instances = 20\n")
    proc = _run("--root", str(root))
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "max_instances = 20 is over the budget of 2" in proc.stderr
    line = next(
        n
        for n, text in enumerate(toml.read_text(encoding="utf-8").splitlines(), 1)
        if text.startswith("max_instances")
    )
    assert "workers/proxy/wrangler.toml:%d:" % line in proc.stderr


def test_a_deleted_max_instances_fails(tmp_path: pathlib.Path) -> None:
    root = _copy(tmp_path)
    _replace(root / "workers" / "proxy" / "wrangler.toml", "max_instances = 2\n", "")
    proc = _run("--root", str(root))
    assert proc.returncode == 1
    assert "sets no max_instances" in proc.stderr


def test_a_planted_oversize_sleep_after_fails(tmp_path: pathlib.Path) -> None:
    root = _copy(tmp_path)
    _replace(root.joinpath(*INDEX_REL), "sleepAfter = '2m';", "sleepAfter = '10m';")
    proc = _run("--root", str(root))
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "workers/proxy/src/index.ts:" in proc.stderr
    assert "sleepAfter = '10m' is 600s idle, over the budget of 120s" in proc.stderr


def test_a_deleted_sleep_after_fails_on_the_library_default(tmp_path: pathlib.Path) -> None:
    root = _copy(tmp_path)
    _replace(root.joinpath(*INDEX_REL), "sleepAfter = '2m';", "")
    proc = _run("--root", str(root))
    assert proc.returncode == 1
    assert "class ExecutorContainer sets no sleepAfter" in proc.stderr
    assert "'10m'" in proc.stderr


def test_a_non_literal_sleep_after_is_unchecked_and_fails(tmp_path: pathlib.Path) -> None:
    root = _copy(tmp_path)
    _replace(root.joinpath(*INDEX_REL), "sleepAfter = '2m';", "sleepAfter = IDLE_TIMEOUT;")
    proc = _run("--root", str(root))
    assert proc.returncode == 1
    assert "is not a literal this gate can read" in proc.stderr


def test_a_tighter_budget_passes(tmp_path: pathlib.Path) -> None:
    """At or UNDER: lowering either value is never a finding."""
    root = _copy(tmp_path)
    _replace(
        root / "workers" / "proxy" / "wrangler.toml", "max_instances = 2\n", "max_instances = 1\n"
    )
    _replace(root.joinpath(*INDEX_REL), "sleepAfter = '2m';", "sleepAfter = '45s';")
    proc = _run("--root", str(root))
    assert proc.returncode == 0, proc.stderr


def test_zero_containers_is_no_verdict_not_a_pass(tmp_path: pathlib.Path) -> None:
    root = _copy(tmp_path)
    toml = root / "workers" / "proxy" / "wrangler.toml"
    toml.write_text(
        toml.read_text(encoding="utf-8").replace("[[containers]]", "[containers_gone]"),
        encoding="utf-8",
    )
    proc = _run("--root", str(root))
    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert "zero [[containers]] entries" in proc.stderr


def test_no_source_is_no_verdict(tmp_path: pathlib.Path) -> None:
    root = _copy(tmp_path)
    shutil.rmtree(root / "workers" / "proxy" / "src")
    proc = _run("--root", str(root))
    assert proc.returncode == 2
    assert "zero source files" in proc.stderr


def test_a_missing_config_is_no_verdict(tmp_path: pathlib.Path) -> None:
    proc = _run("--root", str(tmp_path))
    assert proc.returncode == 2
    assert "is missing" in proc.stderr


def test_the_selftest_passes_on_its_own() -> None:
    proc = _run("--selftest")
    assert proc.returncode == 0, proc.stderr
    assert "FAIL" not in proc.stderr


# ---- the bench config (workers/proxy/wrangler.bench.toml): the same budget, and bench names only ----


def _bench(root: pathlib.Path) -> pathlib.Path:
    return root / "workers" / "proxy" / "wrangler.bench.toml"


def test_a_planted_bench_max_instances_of_twenty_fails(tmp_path: pathlib.Path) -> None:
    root = _copy(tmp_path)
    _replace(_bench(root), "max_instances = 2\n", "max_instances = 20\n")
    proc = _run("--root", str(root))
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "workers/proxy/wrangler.bench.toml:" in proc.stderr
    assert "max_instances = 20 is over the budget of 2" in proc.stderr
    assert "workers/proxy/wrangler.toml:" not in proc.stderr, "the eu config is unplanted"


def test_a_deleted_bench_max_instances_fails(tmp_path: pathlib.Path) -> None:
    root = _copy(tmp_path)
    _replace(_bench(root), "max_instances = 2\n", "")
    proc = _run("--root", str(root))
    assert proc.returncode == 1
    assert (
        "workers/proxy/wrangler.bench.toml: [[containers]] ExecutorContainer sets no max_instances"
        in (proc.stderr)
    )


@pytest.mark.parametrize(
    ("old", "new", "fragment"),
    [
        (
            'ACCOUNT_URL = "https://bench.rediacc.com"',
            'ACCOUNT_URL = "https://eu.rediacc.com"',
            "vars.ACCOUNT_URL is 'https://eu.rediacc.com'",
        ),
        (
            'service = "rediacc-account-bench"',
            'service = "rediacc-account-eu"',
            "[[services]] binds 'rediacc-account-eu'",
        ),
        (
            'pattern = "proxy.bench.rediacc.com"',
            'pattern = "proxy.eu.rediacc.com"',
            "route 'proxy.eu.rediacc.com' names eu",
        ),
        (
            'name = "rediacc-proxy-bench"',
            'name = "rediacc-proxy-production"',
            "names production",
        ),
    ],
    ids=["account-url", "binding", "route", "name"],
)
def test_a_bench_config_naming_anything_but_bench_fails(
    tmp_path: pathlib.Path, old: str, new: str, fragment: str
) -> None:
    root = _copy(tmp_path)
    _replace(_bench(root), old, new)
    proc = _run("--root", str(root))
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "FAIL  workers/proxy/wrangler.bench.toml: " in proc.stderr
    assert fragment in proc.stderr


def test_a_missing_bench_config_is_no_verdict(tmp_path: pathlib.Path) -> None:
    root = _copy(tmp_path)
    _bench(root).unlink()
    proc = _run("--root", str(root))
    assert proc.returncode == 2
    assert "wrangler.bench.toml is missing" in proc.stderr


def test_zero_bench_containers_is_no_verdict(tmp_path: pathlib.Path) -> None:
    root = _copy(tmp_path)
    bench = _bench(root)
    bench.write_text(
        bench.read_text(encoding="utf-8").replace("[[containers]]", "[containers_gone]"),
        encoding="utf-8",
    )
    proc = _run("--root", str(root))
    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert "wrangler.bench.toml declares zero [[containers]] entries" in proc.stderr
