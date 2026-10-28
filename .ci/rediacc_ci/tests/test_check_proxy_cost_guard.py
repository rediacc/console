"""`check:ci-proxy-cost-guard` (`.ci/scripts/quality/check_proxy_cost_guard.py`): the executor proxy's `max_instances` and `sleepAfter` stay at or under the budget in PLAN-cloudflare-proxy.md section 4 (box A5, missing test 9).

CONTROL FIRST, AND NEVER ON THE REAL CONFIG. Every plant goes into a COPY of `workers/proxy/wrangler.toml` and `workers/proxy/src/` under `tmp_path`, and the gate is pointed at the copy with `--root`. The unplanted copy must pass first, so a red on a plant is the plant's doing and not a broken fixture. The real files are hashed before and after the module, and any change is a failure.

THE PLANTED DEFECTS, red before the gate existed and green only with it: `max_instances = 26` (one over the budget of 25), `sleepAfter = '10m'` (the library default, written out), and the `sleepAfter` line deleted (the same default, silently).
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
# The durable_object entry (box K1) and its code-cap vars, appended to the eu fixture by `_durable`. EXECUTOR_BACKEND is `container` as on the live tree during the dual run.
DURABLE = """
[vars]
EXECUTOR_BACKEND = "container"
EXECUTOR_CAP = "25"
EXECUTOR_HEAVY_CAP = "5"

[[containers]]
class_name = "OrgExecutor"
scheduling_policy = "durable_object"
"""
CAPACITY_REL = ("workers", "proxy", "src", "capacity.ts")
EXECUTOR_REL = ("workers", "proxy", "src", "org-executor.ts")


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
    assert "at max_instances <= 25 in " in proc.stdout
    assert "deployable" in proc.stdout
    assert "sleepAfter assignment(s) <= 120s" in proc.stdout
    assert "instance size(s) in the allowlist" in proc.stdout
    assert "worst case $" in proc.stdout


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


def test_a_planted_max_instances_of_twenty_six_fails(tmp_path: pathlib.Path) -> None:
    root = _copy(tmp_path)
    toml = root / "workers" / "proxy" / EU
    _replace(toml, "max_instances = 2\n", "max_instances = 26\n")
    proc = _run("--root", str(root))
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "max_instances = 26 is over the budget of 25" in proc.stderr
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


def test_a_planted_bench_max_instances_of_twenty_six_fails(tmp_path: pathlib.Path) -> None:
    root = _copy(tmp_path)
    _replace(_bench(root), "max_instances = 2\n", "max_instances = 26\n")
    proc = _run("--root", str(root))
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "workers/proxy/wrangler.bench.toml:" in proc.stderr
    assert "max_instances = 26 is over the budget of 25" in proc.stderr
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


def test_a_missing_eu_config_is_no_verdict(tmp_path: pathlib.Path) -> None:
    root = _copy(tmp_path)
    (root / "workers" / "proxy" / EU).unlink()
    proc = _run("--root", str(root))
    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert "wrangler.eu.toml is missing" in proc.stderr


def test_two_entries_in_one_config_are_held_to_the_per_config_budget(
    tmp_path: pathlib.Path,
) -> None:
    root = _copy(tmp_path)
    eu = root / "workers" / "proxy" / EU
    eu.write_text(CONTAINERS % 25 + CONTAINERS % 25, encoding="utf-8")
    proc = _run("--root", str(root))
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert (
        "workers/proxy/wrangler.eu.toml: its [[containers]] entries total max_instances = 50"
        in proc.stderr
    )


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


# ---- the glob and the deployable set: at most 7 configs, at most 175 instances, 25 per config ----


def test_a_planted_max_instances_of_twenty_six_over_budget_fails(tmp_path: pathlib.Path) -> None:
    root = _copy(tmp_path)
    _replace(root / "workers" / "proxy" / EU, "max_instances = 2\n", "max_instances = 26\n")
    proc = _run("--root", str(root))
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "max_instances = 26 is over the budget of 25" in proc.stderr


def test_a_planted_max_instances_of_twenty_five_passes(tmp_path: pathlib.Path) -> None:
    root = _copy(tmp_path)
    _replace(root / "workers" / "proxy" / EU, "max_instances = 2\n", "max_instances = 25\n")
    proc = _run("--root", str(root))
    assert proc.returncode == 0, proc.stderr


def test_a_dev_config_over_budget_fails(tmp_path: pathlib.Path) -> None:
    root = _copy(tmp_path)
    _replace(
        root / "workers" / "proxy" / "wrangler.dev.toml",
        "max_instances = 2\n",
        "max_instances = 26\n",
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


def test_a_planted_total_of_one_seventy_six_fails(tmp_path: pathlib.Path) -> None:
    # eu 25 + bench 25 + a..e at 25 = 175 over seven configs (the limit); wrangler.f at 1 is the eighth config and makes 176.
    extra = {"wrangler.a.toml": 25, "wrangler.b.toml": 25, "wrangler.c.toml": 25}
    extra |= {"wrangler.d.toml": 25, "wrangler.e.toml": 25}
    root = _copy(tmp_path, extra)
    _replace(root / "workers" / "proxy" / EU, "max_instances = 2\n", "max_instances = 25\n")
    _replace(
        root / "workers" / "proxy" / "wrangler.bench.toml",
        "max_instances = 2\n",
        "max_instances = 25\n",
    )
    proc = _run("--root", str(root))
    assert proc.returncode == 0, "175 is the limit: " + proc.stderr
    _replace(
        root / "workers" / "proxy" / "wrangler.e.toml",
        "max_instances = 25\n",
        "max_instances = 26\n",
    )
    assert _run("--root", str(root)).returncode == 1  # 26 is over the per-config budget as well
    _replace(
        root / "workers" / "proxy" / "wrangler.e.toml",
        "max_instances = 26\n",
        "max_instances = 25\n",
    )
    (root / "workers" / "proxy" / "wrangler.f.toml").write_text(CONTAINERS % 1, encoding="utf-8")
    proc = _run("--root", str(root))
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "total max_instances = 176" in proc.stderr


# ---- the durable_object entry (box G1): no max_instances or instance_type, caps in code, literal sizes, dollars ----


def _durable(tmp_path: pathlib.Path) -> pathlib.Path:
    """A fixture tree whose eu config also carries the durable OrgExecutor entry and the cap vars."""
    root = _copy(tmp_path)
    eu = root / "workers" / "proxy" / EU
    eu.write_text(eu.read_text(encoding="utf-8") + DURABLE, encoding="utf-8")
    return root


def test_the_unplanted_durable_copy_passes_so_the_plants_below_are_what_fires(
    tmp_path: pathlib.Path,
) -> None:
    proc = _run("--root", str(_durable(tmp_path)))
    assert proc.returncode == 0, proc.stderr
    assert "worst case $" in proc.stdout


def test_a_planted_max_instances_on_the_durable_entry_fails(tmp_path: pathlib.Path) -> None:
    root = _durable(tmp_path)
    eu = root / "workers" / "proxy" / EU
    _replace(
        eu,
        'scheduling_policy = "durable_object"\n',
        'scheduling_policy = "durable_object"\nmax_instances = 25\n',
    )
    proc = _run("--root", str(root))
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "OrgExecutor is scheduling_policy = durable_object and sets max_instances" in proc.stderr


def test_a_planted_instance_type_on_the_durable_entry_fails(tmp_path: pathlib.Path) -> None:
    root = _durable(tmp_path)
    eu = root / "workers" / "proxy" / EU
    _replace(
        eu,
        'scheduling_policy = "durable_object"\n',
        'scheduling_policy = "durable_object"\ninstance_type = "basic"\n',
    )
    proc = _run("--root", str(root))
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "sets instance_type" in proc.stderr


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        (
            'EXECUTOR_CAP = "25"',
            'EXECUTOR_CAP = "26"',
            'EXECUTOR_CAP = "26" is over the budget of 25',
        ),
        (
            'EXECUTOR_HEAVY_CAP = "5"',
            'EXECUTOR_HEAVY_CAP = "6"',
            'EXECUTOR_HEAVY_CAP = "6" is over the budget of 5',
        ),
        ('EXECUTOR_CAP = "25"', "EXECUTOR_CAP = 25", "EXECUTOR_CAP = 25 is not a decimal string"),
        ('EXECUTOR_CAP = "25"\n', "", "[vars] EXECUTOR_CAP as a decimal string"),
    ],
)
def test_a_planted_cap_var_fails(tmp_path: pathlib.Path, old: str, new: str, message: str) -> None:
    root = _durable(tmp_path)
    _replace(root / "workers" / "proxy" / EU, old, new)
    proc = _run("--root", str(root))
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert message in proc.stderr


def test_a_planted_unreadable_backend_fails(tmp_path: pathlib.Path) -> None:
    root = _durable(tmp_path)
    _replace(
        root / "workers" / "proxy" / EU,
        'EXECUTOR_BACKEND = "container"',
        'EXECUTOR_BACKEND = "both"',
    )
    proc = _run("--root", str(root))
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "routed backend" in proc.stderr


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        ("HARD_CAP = 25;", "HARD_CAP = 30;", "HARD_CAP = 30 is over the budget of 25"),
        (
            "HARD_HEAVY_CAP = 5;",
            "HARD_HEAVY_CAP = 6;",
            "HARD_HEAVY_CAP = 6 is over the budget of 5",
        ),
        ("HARD_CAP = 25;", "HARD_CAP = envCap();", "HARD_CAP = envCap() is not an integer literal"),
    ],
)
def test_a_planted_hard_cap_fails(tmp_path: pathlib.Path, old: str, new: str, message: str) -> None:
    root = _durable(tmp_path)
    _replace(root.joinpath(*CAPACITY_REL), old, new)
    proc = _run("--root", str(root))
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert message in proc.stderr
    assert "workers/proxy/src/capacity.ts:" in proc.stderr


def test_a_deleted_capacity_file_fails_when_a_durable_entry_exists(tmp_path: pathlib.Path) -> None:
    root = _durable(tmp_path)
    root.joinpath(*CAPACITY_REL).unlink()
    proc = _run("--root", str(root))
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "capacity.ts is missing" in proc.stderr


def test_a_legacy_only_tree_does_not_need_capacity_ts(tmp_path: pathlib.Path) -> None:
    root = _copy(tmp_path)
    root.joinpath(*CAPACITY_REL).unlink()
    proc = _run("--root", str(root))
    assert proc.returncode == 0, proc.stderr


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("instance: 'standard-1'", "instance: 'standard-2'"),
        ("instance: 'standard-1'", "instance: HEAVY_SIZE"),
        ("diskMb: 4000", "diskMb: 8000"),
    ],
)
def test_a_planted_instance_size_fails(tmp_path: pathlib.Path, old: str, new: str) -> None:
    root = _durable(tmp_path)
    # The size table lives in whichever source file defines it (it moved from org-executor.ts to sizing.ts), so the anchor is found, not named.
    holders = [
        p
        for p in sorted(root.joinpath("workers", "proxy", "src").glob("*.ts"))
        if old in p.read_text(encoding="utf-8")
    ]
    assert holders, "the anchor %r is in no source file; the size table moved" % old
    holders[0].write_text(
        holders[0].read_text(encoding="utf-8").replace(old, new, 1), encoding="utf-8"
    )
    proc = _run("--root", str(root))
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "is not an allowed literal" in proc.stderr
    assert "workers/proxy/src/%s:" % holders[0].name in proc.stderr


def test_a_second_custom_instance_object_fails(tmp_path: pathlib.Path) -> None:
    root = _durable(tmp_path)
    path = root.joinpath(*EXECUTOR_REL)
    path.write_text(
        path.read_text(encoding="utf-8")
        + "\nexport const EXTRA = { instance: { vcpu: 1, memoryMib: 2048, diskMb: 4000 } };\n",
        encoding="utf-8",
    )
    proc = _run("--root", str(root))
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "is not an allowed literal" in proc.stderr


def test_a_deleted_org_executor_sleep_after_fails(tmp_path: pathlib.Path) -> None:
    root = _durable(tmp_path)
    _replace(root.joinpath(*EXECUTOR_REL), "sleepAfter = '2m';", "")
    proc = _run("--root", str(root))
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "class OrgExecutor sets no sleepAfter" in proc.stderr


def test_a_config_over_three_hundred_dollars_fails_and_the_limit_passes(
    tmp_path: pathlib.Path,
) -> None:
    """25 awake of which 5 are heavy is $281.05, under $300. Heavy at 25 of 25 is $684.25, over it; the vars stay legal-looking only up to their own budgets, so this plant also trips the heavy budget."""
    root = _durable(tmp_path)
    assert _run("--root", str(root)).returncode == 0
    _replace(
        root / "workers" / "proxy" / EU, 'EXECUTOR_HEAVY_CAP = "5"', 'EXECUTOR_HEAVY_CAP = "25"'
    )
    proc = _run("--root", str(root))
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "over the per-config limit of $300" in proc.stderr


def test_a_deployable_set_over_twenty_one_hundred_dollars_fails(tmp_path: pathlib.Path) -> None:
    """Seven durable targets at $281.05 are $1,967.35 and pass; an eighth is also an eighth config, so the dollar line is planted through the set limit alone by pricing seven at full cap and heavy at the budget plus the dev-free copy of one more under a name the count refuses."""
    extra = {f"wrangler.t{i}.toml": 1 for i in range(5)}
    root = _copy(tmp_path, extra)
    for name in (EU, "wrangler.bench.toml", *extra):
        path = root / "workers" / "proxy" / name
        path.write_text(path.read_text(encoding="utf-8") + DURABLE, encoding="utf-8")
    proc = _run("--root", str(root))
    assert proc.returncode == 0, proc.stderr
    assert "$1967.35/month" in proc.stdout
    # An eighth deployable config exceeds the set's dollars and its count.
    path = root / "workers" / "proxy" / "wrangler.t9.toml"
    path.write_text(CONTAINERS % 1 + DURABLE, encoding="utf-8")
    proc = _run("--root", str(root))
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert (
        "the deployable configs cost $2248.40/month worst case, over the limit of $2100"
        in proc.stderr
    )
