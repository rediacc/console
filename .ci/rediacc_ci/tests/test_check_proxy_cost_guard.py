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
PROXY = ROOT / "workers" / "proxy"
SRC = ROOT / "workers" / "proxy" / "src"
INDEX_REL = ("workers", "proxy", "src", "index.ts")


# The fixture configs are synthetic so the module holds before and after the live configs are renamed or added to; only `src/` is copied from the tree.
CONTAINERS = """
[[containers]]
class_name = "ExecutorContainer"
image = "./Dockerfile"
max_instances = %d
"""
EU = "wrangler.eu.toml"


def _digest() -> str:
    h = hashlib.sha256()
    for config in sorted(PROXY.glob("wrangler*.toml")):
        h.update(config.read_bytes())
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


def _copy(
    tmp_path: pathlib.Path, extra: dict[str, int] | None = None, dev: bool = True
) -> pathlib.Path:
    """A fixture tree: eu (2), bench (2), dev (2), plus `extra` deployable configs `{file: max_instances}`."""
    root = tmp_path / "root"
    proxy = root / "workers" / "proxy"
    proxy.mkdir(parents=True)
    (proxy / EU).write_text(CONTAINERS % 2, encoding="utf-8")
    (proxy / "wrangler.bench.toml").write_text(CONTAINERS % 2, encoding="utf-8")
    if dev:
        (proxy / "wrangler.dev.toml").write_text(CONTAINERS % 2, encoding="utf-8")
    for name, value in (extra or {}).items():
        (proxy / name).write_text(CONTAINERS % value, encoding="utf-8")
    shutil.copytree(SRC, root / "workers" / "proxy" / "src")
    return root


def _replace(path: pathlib.Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    assert text.count(old) == 1, "the plant's anchor %r must occur exactly once in %s" % (old, path)
    path.write_text(text.replace(old, new), encoding="utf-8")


def test_the_real_tree_is_within_budget() -> None:
    proc = _run()
    assert proc.returncode == 0, proc.stderr
    assert "at max_instances <= 3 in " in proc.stdout
    assert "deployable" in proc.stdout
    assert "1 sleepAfter assignment(s)" in proc.stdout


def test_the_glob_sees_every_config_in_the_real_tree() -> None:
    configs = [
        c for c in sorted(PROXY.glob("wrangler*.toml")) if c.name != "wrangler.template.toml"
    ]
    assert PROXY / "wrangler.bench.toml" in configs
    assert f"in {len(configs)} config(s)" in _run().stdout


def test_the_template_is_not_a_config(tmp_path: pathlib.Path) -> None:
    root = _copy(tmp_path)
    (root / "workers" / "proxy" / "wrangler.template.toml").write_text(
        'name = "@@NAME@@"\n', encoding="utf-8"
    )
    proc = _run("--root", str(root))
    assert proc.returncode == 0, proc.stderr


def test_the_unplanted_copy_passes_so_the_plants_below_are_what_fires(
    tmp_path: pathlib.Path,
) -> None:
    proc = _run("--root", str(_copy(tmp_path)))
    assert proc.returncode == 0, proc.stderr


def test_a_planted_max_instances_of_twenty_fails(tmp_path: pathlib.Path) -> None:
    root = _copy(tmp_path)
    toml = root / "workers" / "proxy" / EU
    _replace(toml, "max_instances = 2\n", "max_instances = 20\n")
    proc = _run("--root", str(root))
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "max_instances = 20 is over the budget of 3" in proc.stderr
    line = next(
        n
        for n, text in enumerate(toml.read_text(encoding="utf-8").splitlines(), 1)
        if text.startswith("max_instances")
    )
    assert "workers/proxy/wrangler.eu.toml:%d:" % line in proc.stderr


def test_a_deleted_max_instances_fails(tmp_path: pathlib.Path) -> None:
    root = _copy(tmp_path)
    _replace(root / "workers" / "proxy" / EU, "max_instances = 2\n", "")
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
    _replace(root / "workers" / "proxy" / EU, "max_instances = 2\n", "max_instances = 1\n")
    _replace(root.joinpath(*INDEX_REL), "sleepAfter = '2m';", "sleepAfter = '45s';")
    proc = _run("--root", str(root))
    assert proc.returncode == 0, proc.stderr


def test_zero_containers_is_no_verdict_not_a_pass(tmp_path: pathlib.Path) -> None:
    root = _copy(tmp_path)
    toml = root / "workers" / "proxy" / EU
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


# ---- the bench config (workers/proxy/wrangler.bench.toml): the same budget; what it names is check:ci-proxy-configs' ----


def _bench(root: pathlib.Path) -> pathlib.Path:
    return root / "workers" / "proxy" / "wrangler.bench.toml"


def test_a_planted_bench_max_instances_of_twenty_fails(tmp_path: pathlib.Path) -> None:
    root = _copy(tmp_path)
    _replace(_bench(root), "max_instances = 2\n", "max_instances = 20\n")
    proc = _run("--root", str(root))
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "workers/proxy/wrangler.bench.toml:" in proc.stderr
    assert "max_instances = 20 is over the budget of 3" in proc.stderr
    assert "workers/proxy/wrangler.eu.toml:" not in proc.stderr, "the eu config is unplanted"


def test_a_deleted_bench_max_instances_fails(tmp_path: pathlib.Path) -> None:
    root = _copy(tmp_path)
    _replace(_bench(root), "max_instances = 2\n", "")
    proc = _run("--root", str(root))
    assert proc.returncode == 1
    assert (
        "workers/proxy/wrangler.bench.toml: [[containers]] ExecutorContainer sets no max_instances"
        in (proc.stderr)
    )


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


# ---- the glob and the deployable set: at most 7 configs, at most 21 instances, 3 per config ----


def test_a_planted_max_instances_of_four_fails(tmp_path: pathlib.Path) -> None:
    root = _copy(tmp_path)
    _replace(root / "workers" / "proxy" / EU, "max_instances = 2\n", "max_instances = 4\n")
    proc = _run("--root", str(root))
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "max_instances = 4 is over the budget of 3" in proc.stderr


def test_a_planted_max_instances_of_three_passes(tmp_path: pathlib.Path) -> None:
    root = _copy(tmp_path)
    _replace(root / "workers" / "proxy" / EU, "max_instances = 2\n", "max_instances = 3\n")
    proc = _run("--root", str(root))
    assert proc.returncode == 0, proc.stderr


def test_a_dev_config_over_budget_fails(tmp_path: pathlib.Path) -> None:
    root = _copy(tmp_path)
    _replace(
        root / "workers" / "proxy" / "wrangler.dev.toml",
        "max_instances = 2\n",
        "max_instances = 4\n",
    )
    proc = _run("--root", str(root))
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "workers/proxy/wrangler.dev.toml:" in proc.stderr


def test_seven_deployable_configs_pass_and_the_dev_config_is_not_counted(
    tmp_path: pathlib.Path,
) -> None:
    extra = {f"wrangler.t{i}.toml": 1 for i in range(5)}
    proc = _run("--root", str(_copy(tmp_path, extra)))
    assert proc.returncode == 0, proc.stderr
    assert "7 deployable" in proc.stdout


def test_a_planted_eighth_deployable_config_fails(tmp_path: pathlib.Path) -> None:
    extra = {f"wrangler.t{i}.toml": 1 for i in range(6)}
    proc = _run("--root", str(_copy(tmp_path, extra)))
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "8 deployable configs" in proc.stderr
    assert "total max_instances" not in proc.stderr


def test_a_planted_total_of_twenty_two_fails(tmp_path: pathlib.Path) -> None:
    # eu 3 + bench 3 + five more at 3 = 21 (the limit); a seventh-config 1 more makes 22 (an eighth config, too).
    extra = {"wrangler.a.toml": 3, "wrangler.b.toml": 3, "wrangler.c.toml": 3}
    extra |= {"wrangler.d.toml": 3, "wrangler.e.toml": 3}
    root = _copy(tmp_path, extra)
    _replace(root / "workers" / "proxy" / EU, "max_instances = 2\n", "max_instances = 3\n")
    _replace(
        root / "workers" / "proxy" / "wrangler.bench.toml",
        "max_instances = 2\n",
        "max_instances = 3\n",
    )
    proc = _run("--root", str(root))
    assert proc.returncode == 0, "21 is the limit: " + proc.stderr
    _replace(
        root / "workers" / "proxy" / "wrangler.e.toml", "max_instances = 3\n", "max_instances = 4\n"
    )
    assert _run("--root", str(root)).returncode == 1  # 4 over the per-config budget as well
    _replace(
        root / "workers" / "proxy" / "wrangler.e.toml", "max_instances = 4\n", "max_instances = 3\n"
    )
    (root / "workers" / "proxy" / "wrangler.f.toml").write_text(CONTAINERS % 1, encoding="utf-8")
    proc = _run("--root", str(root))
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "total max_instances = 22" in proc.stderr
