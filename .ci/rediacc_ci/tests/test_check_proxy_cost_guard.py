"""`check:ci-proxy-cost-guard` (`.ci/scripts/quality/check_proxy_cost_guard.py`): the executor proxy's cap (`EXECUTOR_CAP`, `EXECUTOR_HEAVY_CAP`, `HARD_CAP`) and `sleepAfter` stay at or under the budget in PLAN-cloudflare-proxy.md section 4 (box A5, missing test 9), and the config holds the one `durable_object` entry (PLAN-executor-durable-object-policy.md box C1).

CONTROL FIRST, AND NEVER ON THE REAL CONFIG. Every plant goes into a COPY of `workers/proxy/wrangler.toml` and `workers/proxy/src/` under `tmp_path`, and the gate is pointed at the copy with `--root`. The unplanted copy must pass first, so a red on a plant is the plant's doing and not a broken fixture. The real files are hashed before and after the module, and any change is a failure.

THE PLANTED DEFECTS, red before the gate existed and green only with it: `EXECUTOR_CAP = "26"` (one over the budget of 25), `sleepAfter = '10m'` (five times the budget), the `sleepAfter` line deleted, and a retired default-policy `Container` entry put back.
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
EXECUTOR_REL = ("workers", "proxy", "src", "org-executor.ts")
CAPACITY_REL = ("workers", "proxy", "src", "capacity.ts")


# The fixture configs are synthetic so the module holds before and after the live configs are renamed or added to; only `src/` is copied from the tree. `%s` is the config's EXECUTOR_CAP.
CONTAINERS = """
[vars]
EXECUTOR_CAP = "%s"
EXECUTOR_HEAVY_CAP = "1"

[[containers]]
class_name = "OrgExecutor"
scheduling_policy = "durable_object"
"""
EU = "wrangler.eu.toml"
# The retired default-policy entry, planted back by the tests that prove it is refused.
LEGACY = """
[[containers]]
class_name = "ExecutorContainer"
image = "./Dockerfile"
max_instances = 2
"""
# A config with the full cap vars, for the dollar tests.
DURABLE = """
[vars]
EXECUTOR_CAP = "25"
EXECUTOR_HEAVY_CAP = "5"

[[containers]]
class_name = "OrgExecutor"
scheduling_policy = "durable_object"
"""


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
    """A fixture tree: eu (cap 2), bench (2), dev (2), plus `extra` deployable configs `{file: EXECUTOR_CAP}`."""
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
    assert "at an executor cap <= 25 in " in proc.stdout
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


def test_a_planted_executor_cap_of_twenty_six_fails(tmp_path: pathlib.Path) -> None:
    root = _copy(tmp_path)
    toml = root / "workers" / "proxy" / EU
    _replace(toml, 'EXECUTOR_CAP = "2"\n', 'EXECUTOR_CAP = "26"\n')
    proc = _run("--root", str(root))
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert 'EXECUTOR_CAP = "26" is over the budget of 25' in proc.stderr
    assert "workers/proxy/wrangler.eu.toml:" in proc.stderr


def test_a_deleted_executor_cap_fails(tmp_path: pathlib.Path) -> None:
    root = _copy(tmp_path)
    _replace(root / "workers" / "proxy" / EU, 'EXECUTOR_CAP = "2"\n', "")
    proc = _run("--root", str(root))
    assert proc.returncode == 1
    assert "[vars] EXECUTOR_CAP as a decimal string" in proc.stderr


def test_a_planted_default_policy_entry_fails(tmp_path: pathlib.Path) -> None:
    """The retired `Container` class's entry, put back beside the durable one, is refused twice over: as a default-policy entry and as a second entry."""
    root = _copy(tmp_path)
    eu = root / "workers" / "proxy" / EU
    eu.write_text(eu.read_text(encoding="utf-8") + LEGACY, encoding="utf-8")
    proc = _run("--root", str(root))
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "ExecutorContainer uses the default scheduling policy" in proc.stderr
    assert "2 [[containers]] entries" in proc.stderr


def test_a_planted_oversize_sleep_after_fails(tmp_path: pathlib.Path) -> None:
    root = _copy(tmp_path)
    _replace(root.joinpath(*EXECUTOR_REL), "sleepAfter = '2m';", "sleepAfter = '10m';")
    proc = _run("--root", str(root))
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "workers/proxy/src/org-executor.ts:" in proc.stderr
    assert "sleepAfter = '10m' is 600s idle, over the budget of 120s" in proc.stderr


def test_a_deleted_sleep_after_fails(tmp_path: pathlib.Path) -> None:
    root = _copy(tmp_path)
    _replace(root.joinpath(*EXECUTOR_REL), "sleepAfter = '2m';", "")
    proc = _run("--root", str(root))
    assert proc.returncode == 1
    assert "class OrgExecutor sets no sleepAfter" in proc.stderr


def test_a_non_literal_sleep_after_is_unchecked_and_fails(tmp_path: pathlib.Path) -> None:
    root = _copy(tmp_path)
    _replace(root.joinpath(*EXECUTOR_REL), "sleepAfter = '2m';", "sleepAfter = IDLE_TIMEOUT;")
    proc = _run("--root", str(root))
    assert proc.returncode == 1
    assert "is not a literal this gate can read" in proc.stderr


def test_a_tighter_budget_passes(tmp_path: pathlib.Path) -> None:
    """At or UNDER: lowering either value is never a finding."""
    root = _copy(tmp_path)
    _replace(root / "workers" / "proxy" / EU, 'EXECUTOR_CAP = "2"\n', 'EXECUTOR_CAP = "1"\n')
    _replace(root.joinpath(*EXECUTOR_REL), "sleepAfter = '2m';", "sleepAfter = '45s';")
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


def test_a_planted_bench_executor_cap_of_twenty_six_fails(tmp_path: pathlib.Path) -> None:
    root = _copy(tmp_path)
    _replace(_bench(root), 'EXECUTOR_CAP = "2"\n', 'EXECUTOR_CAP = "26"\n')
    proc = _run("--root", str(root))
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "workers/proxy/wrangler.bench.toml:" in proc.stderr
    assert 'EXECUTOR_CAP = "26" is over the budget of 25' in proc.stderr
    assert "workers/proxy/wrangler.eu.toml:" not in proc.stderr, "the eu config is unplanted"


def test_a_default_policy_entry_in_bench_fails(tmp_path: pathlib.Path) -> None:
    root = _copy(tmp_path)
    bench = _bench(root)
    bench.write_text(bench.read_text(encoding="utf-8") + LEGACY, encoding="utf-8")
    proc = _run("--root", str(root))
    assert proc.returncode == 1
    assert (
        "workers/proxy/wrangler.bench.toml: [[containers]] ExecutorContainer uses the default "
        "scheduling policy" in proc.stderr
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


def test_two_durable_entries_in_one_config_fail(tmp_path: pathlib.Path) -> None:
    root = _copy(tmp_path)
    eu = root / "workers" / "proxy" / EU
    eu.write_text(
        eu.read_text(encoding="utf-8")
        + '\n[[containers]]\nclass_name = "OrgExecutor"\nscheduling_policy = "durable_object"\n',
        encoding="utf-8",
    )
    proc = _run("--root", str(root))
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "workers/proxy/wrangler.eu.toml: 2 [[containers]] entries" in proc.stderr


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


def test_a_planted_executor_cap_of_twenty_five_passes(tmp_path: pathlib.Path) -> None:
    root = _copy(tmp_path)
    _replace(root / "workers" / "proxy" / EU, 'EXECUTOR_CAP = "2"\n', 'EXECUTOR_CAP = "25"\n')
    proc = _run("--root", str(root))
    assert proc.returncode == 0, proc.stderr


def test_a_dev_config_over_budget_fails(tmp_path: pathlib.Path) -> None:
    root = _copy(tmp_path)
    _replace(
        root / "workers" / "proxy" / "wrangler.dev.toml",
        'EXECUTOR_CAP = "2"\n',
        'EXECUTOR_CAP = "26"\n',
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
    assert "total an executor cap" not in proc.stderr


def test_a_planted_total_of_one_seventy_six_fails(tmp_path: pathlib.Path) -> None:
    # eu 25 + bench 25 + a..e at 25 = 175 over seven configs (the limit); wrangler.f at 1 is the eighth config and makes 176.
    extra = {"wrangler.a.toml": 25, "wrangler.b.toml": 25, "wrangler.c.toml": 25}
    extra |= {"wrangler.d.toml": 25, "wrangler.e.toml": 25}
    root = _copy(tmp_path, extra)
    _replace(root / "workers" / "proxy" / EU, 'EXECUTOR_CAP = "2"\n', 'EXECUTOR_CAP = "25"\n')
    _replace(_bench(root), 'EXECUTOR_CAP = "2"\n', 'EXECUTOR_CAP = "25"\n')
    proc = _run("--root", str(root))
    assert proc.returncode == 0, "175 is the limit: " + proc.stderr
    (root / "workers" / "proxy" / "wrangler.f.toml").write_text(CONTAINERS % 1, encoding="utf-8")
    proc = _run("--root", str(root))
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "total an executor cap of 176" in proc.stderr


# ---- the durable_object entry (boxes G1 and C1): no max_instances or instance_type, caps in code, literal sizes, dollars ----


def _durable(tmp_path: pathlib.Path) -> pathlib.Path:
    """A fixture tree whose eu config carries the full caps (25 and 5)."""
    root = _copy(tmp_path)
    (root / "workers" / "proxy" / EU).write_text(DURABLE, encoding="utf-8")
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
    """Seven durable targets at $281.05 are $1,967.35 and pass; an eighth is also an eighth config, so the dollar line is planted through the set limit alone by pricing seven at full cap and heavy at the budget plus one more config the count refuses."""
    extra = {f"wrangler.t{i}.toml": 1 for i in range(5)}
    root = _copy(tmp_path, extra)
    for name in (EU, "wrangler.bench.toml", *extra):
        (root / "workers" / "proxy" / name).write_text(DURABLE, encoding="utf-8")
    proc = _run("--root", str(root))
    assert proc.returncode == 0, proc.stderr
    assert "$1967.35/month" in proc.stdout
    # An eighth deployable config exceeds the set's dollars and its count.
    (root / "workers" / "proxy" / "wrangler.t9.toml").write_text(DURABLE, encoding="utf-8")
    proc = _run("--root", str(root))
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert (
        "the deployable configs cost $2248.40/month worst case, over the limit of $2100"
        in proc.stderr
    )
