"""`rediacc_ci.core.account` against the transcripts frozen from the retired `.ci/lib/account.sh` (`goldens/twins/lib.account.jsonl`).

ALL TWENTY-TWO OF THE TWIN'S FUNCTIONS HAVE A PYTHON PORT, split across two modules, and the twin is deleted. While `account.sh` existed this file drove it for real through THREE techniques, and the bash side of the first two is now the golden:
  * `rediacc_ci.core.shadow_driver` (pair `w7p5b-account`): the deterministic half of `rediacc_ci.core.account`, compared answer for answer.
  * `rediacc_ci.core.account_lifecycle_shadow_driver` (pair `w7p5b-account-lifecycle`): the twelve side-effecting functions in `rediacc_ci.core.account_lifecycle`, each case its own process with the external programs stubbed, compared on rc, both streams, the ordered call transcript and the resulting tree.
  * REAL RUNS for `account_stop`, `account_rotation` and `account_bws_exec`, against a real tracked process, a real Docker daemon and the real credential-free `rotation` subcommands (the "stop and rotation" section). Only the port side of those still runs.
The twin's four `.env` writers are deleted from BOTH sides (`agent/plans/PLAN-account-env-to-bws.md`), so they appear in neither tuple below; the CI-only `mint-dev-keys` verb that replaced one of their uses has no twin and is tested directly at the end of this file.

WHY SOME ITEMS CARRY AN XDIST GROUP. The driver pins FIXED port numbers on both sides, because the two sides run as two processes and an ephemeral port would differ between them and land in a message text, and the lifecycle driver runs at a fixed tmp path under a machine-wide lock. Only the items that run one of those drivers are grouped (see SHADOW_PORTS_GROUP below); the module as a whole is not, since 2026-10-05.

THE ANTI-VACUITY CLAIMS, because a differential that compared two empty transcripts would pass forever: every scenario must produce a floor of observations, the tools the scenarios really use must be installed, and `test_the_differential_can_fail` mutates one side and demands a mismatch in each of the four places a mutation can hide.
"""

import contextlib
import http.server
import json
import os
import pathlib
import re
import shlex
import shutil
import socket
import subprocess
import sys
import threading
import time

import pytest

from rediacc_ci import paths
from rediacc_ci.core import account, account_lifecycle, shadow_driver, stubfarm
from rediacc_ci.core import account_lifecycle_shadow_driver as lifecycle_driver
from rediacc_ci.tests import differential as diff
from rediacc_ci.well_known import ACCOUNT_DEV_PORT

# NO MODULE-LEVEL GROUP SINCE 2026-10-05 (agent/plans/PLAN-prepush-full-cpu.md PF14). The module used to declare `XDIST_GROUP = "ports"`, which put all 107 items (183 s of test time on 2026-10-03) and three other modules on one worker. Two resources here really are machine-wide, both fixed by the drivers rather than by these tests, so only the items that touch one carry a group, each named for its resource:
#
# * `shadow_driver` pins CONSTANT ports (31210-31340, below the kernel's ephemeral range, `rediacc_ci/core/shadow_driver.py` "Every port below is therefore a CONSTANT") because an ephemeral port would differ between the two sides and land in a message text. Every item that runs it (`drive()`) shares SHADOW_PORTS_GROUP. These ports are above the 20000-30000 the per-worker slices are cut from, so the group serialises these items only against each other.
# * `account_lifecycle_shadow_driver` builds its sandbox at a FIXED tmp path and takes a machine-wide `flock` around every run (`locked()`), so its items serialise however they are scheduled. LIFECYCLE_GROUP keeps them on one worker instead of leaving several workers blocked on the lock.
#
# Everything else in the file distributes per item.
SHADOW_PORTS_GROUP = "account-shadow-fixed-ports"
LIFECYCLE_GROUP = "account-lifecycle-fixed-tmp"

TWIN = ".ci/lib/account.sh"
DEVBOX_TWIN = ".ci/lib/devbox.sh"
PORT = ".ci/rediacc_ci/core/account.py"
DRIVER = ".ci/rediacc_ci/core/shadow_driver.py"
# Invoked as a MODULE, never by path: see the driver's header for why the by-path form would need a hand-written sys.path hop that `test_canonical_sys_path_hop.py` refuses.
DRIVER_MODULE = "rediacc_ci.core.shadow_driver"
LEDGER = ".ci/shadow/w7p5b-account.observations.jsonl"

SCENARIOS = sorted(shadow_driver.SCENARIOS)

# The floor each scenario must clear. Measured against the recorded ledger rows, then rounded DOWN so a real change to a message does not turn into a test edit; the point is to catch a transcript collapsing to nothing, not to pin a count.
OBSERVATION_FLOOR = {
    "db": 10,
    "keys": 7,
    "probe": 12,
    "totp": 8,
}

_CACHE: dict[tuple[str, str], tuple[int, str, str]] = {}

# RULE T: the lines the port INTENTIONALLY no longer shares with the twin. Each is a defect the twin still has and the port fixed (see the `test_delta_*` cases at the end), so the live differential leaves exactly these lines out of its comparison, and `test_every_delta_case_still_diverges` proves each is still a real divergence.
DELTA_LINES = {
    # A2: banner padding by characters, shown by the multibyte row.
    "probe": ("obs banner| ..│..héllo",),
    # A1: the missing-gateway-port refusal, which the twin leaves silent.
    "totp": ("obs err no-key|",),
}


def _delta_comparable(out: str, scenario: str) -> list[str]:
    return [
        line
        for line in out.splitlines()
        if not any(line.startswith(prefix) for prefix in DELTA_LINES.get(scenario, ()))
    ]


def _retired() -> tuple[int, str, str]:
    raise RuntimeError(
        "%s is retired: re-record a Rule-T change with `%s %s --source port --reason ...`"
        % (TWIN, diff.REGOLDEN_VERB, TWIN)
    )


def _run_driver(side: str, scenario: str) -> tuple[int, str, str]:
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            DRIVER_MODULE,
            "--side",
            side,
            "--port",
            PORT,
            scenario,
        ],
        cwd=str(paths.repo_root()),
        env={**os.environ, "PYTHONPATH": ".ci"},
        capture_output=True,
        text=True,
        check=False,
        timeout=300,
    )
    return proc.returncode, proc.stdout, proc.stderr


def drive(side: str, scenario: str) -> tuple[int, str, str]:
    """One side of one scenario, run once per session and remembered. The bash side is the golden frozen from `account.sh` (`goldens/twins/lib.account.jsonl`)."""
    key = (side, scenario)
    if key not in _CACHE:
        if side == "old":
            _CACHE[key] = diff.twin_call(
                TWIN,
                ["shadow", scenario],
                _retired,
                port=lambda: _run_driver("new", scenario),
            )
        else:
            _CACHE[key] = _run_driver(side, scenario)
    return _CACHE[key]


@pytest.mark.xdist_group(SHADOW_PORTS_GROUP)
@pytest.mark.parametrize("scenario", SCENARIOS)
def test_the_port_matches_the_live_twin(scenario: str) -> None:
    """The whole claim of this file, once per scenario."""
    old_rc, old_out, old_err = drive("old", scenario)
    new_rc, new_out, new_err = drive("new", scenario)
    assert old_rc == 0, "the bash side could not run: %s" % old_err
    assert new_rc == 0, "the port side could not run: %s" % new_err
    assert _delta_comparable(old_out, scenario) == _delta_comparable(new_out, scenario), (
        "scenario %s diverged" % scenario
    )


@pytest.mark.xdist_group(SHADOW_PORTS_GROUP)
@pytest.mark.parametrize("scenario", SCENARIOS)
def test_each_scenario_observed_something(scenario: str) -> None:
    """ANTI-VACUITY. A transcript that collapsed to nothing would compare equal.

    The floor is per scenario and deliberately low, because the claim is that the scenario ran at all rather than that it printed a particular number of lines.
    """
    _, out, _ = drive("old", scenario)
    lines = [line for line in out.splitlines() if line.startswith("obs ")]
    assert len(lines) >= OBSERVATION_FLOOR[scenario], (
        "scenario %s produced %d observation(s), under its floor of %d; a transcript "
        "this short means the twin stopped early and the comparison proved nothing"
        % (scenario, len(lines), OBSERVATION_FLOOR[scenario])
    )


def test_the_corpus_is_not_empty() -> None:
    assert len(SCENARIOS) >= 4, "the scenario set collapsed to %d" % len(SCENARIOS)
    assert set(SCENARIOS) == set(OBSERVATION_FLOOR), (
        "a scenario was added or removed without a floor: %s"
        % sorted(set(SCENARIOS) ^ set(OBSERVATION_FLOOR))
    )


@pytest.mark.xdist_group(SHADOW_PORTS_GROUP)
def test_the_differential_can_fail() -> None:
    """A CONTROL ON THE COMPARISON, in the four places a mutation can hide.

    Each line below is a transcript the port could plausibly produce and the twin does not, so a comparison that still called it equal would be looking at the wrong thing.
    """
    _, out, _ = drive("old", "probe")
    assert out != out.replace("obs rc rustfs-dead=1", "obs rc rustfs-dead=0"), (
        "the probe transcript carries no exit code, so a port that inverted one would pass"
    )
    padded = out.replace("..│..hello", ".│..hello")
    assert out != padded, "the probe transcript carries no banner padding"
    _, keys_out, _ = drive("old", "keys")
    assert keys_out != keys_out.replace("ED25519_PUB len=60", "ED25519_PUB len=59"), (
        "the keys transcript carries no key length, so a port minting a different encoding would pass"
    )
    _, totp_out, _ = drive("old", "totp")
    assert totp_out != totp_out.replace("obs err no-state| ", "obs err no-state|"), (
        "the totp transcript carries no message text, so a reworded refusal would pass"
    )


# -- the twin is still there, and still says what this file claims it says ----


# The deterministic half and the three real-run functions, in `rediacc_ci.core.account`.
PORTED_FUNCTIONS = (
    "account_allocate_ports",
    "account_wait_port",
    "account_rustfs_alive",
    "account_generate_crypto_keys",
    "account_banner_row",
    "account_totp",
    "account_db",
    # These three are ported but NOT shadow-differentially proved: see the real-run tests below, and `rediacc_ci.core.account`'s module docstring, "THREE MORE ARE PORTED".
    "account_stop",
    "account_rotation",
    "account_bws_exec",
    # The `.account-state` writer stamp and its check, shared by `account_dev` and `account_stop`. Proved by the real-run stop tests below and the lifecycle `previous-owned` / `previous-foreign` cases.
    "account_writer_stamp",
    "account_state_owned",
)

# The side-effecting half, in `rediacc_ci.core.account_lifecycle`, keyed by the twin's name. Proved by the stub-farm differential at the end of this file.
LIFECYCLE_FUNCTIONS = {
    "account_spawn": "spawn_background",
    "account_cleanup": "cleanup",
    "account_docker_ghost_clean": "docker_ghost_clean",
    "account_stripe_auto": "stripe_auto",
    "account_dev": "dev",
    "account_dev_credentials": "dev_credentials",
    "account_test": "test",
    "account_test_e2e": "test_e2e",
    "account_reset": "reset",
    "account_seed_demo": "seed_demo",
    "account_load_defaults": "load_defaults",
    "account_state_gateway_port": "state_gateway_port",
}

# Deleted from BOTH sides with `private/account/.env`. Asserted gone rather than forgotten: a writer reappearing on either side is a file-based secret path coming back.
DELETED_FUNCTIONS = (
    "account_generate_fresh_env",
    "account_env_add_if_missing",
    "account_ensure_env_keys",
    "account_ensure_env",
)


def test_every_function_the_twin_defined_is_classified() -> None:
    """Twenty-four, split twelve and twelve. The twin's own definition count was checked against these tables while `account.sh` existed; what is kept is that the two tables partition the twenty-four and name no function twice."""
    assert not set(PORTED_FUNCTIONS) & set(LIFECYCLE_FUNCTIONS)
    assert len(PORTED_FUNCTIONS) + len(LIFECYCLE_FUNCTIONS) == 24


def test_the_env_writers_are_gone_from_the_port() -> None:
    """`private/account/.env` is retired, and with it every function that wrote it."""
    for name in DELETED_FUNCTIONS:
        stem = name[len("account_") :]
        assert not hasattr(account, stem), "%s is back in the port" % stem
        assert name not in PORTED_FUNCTIONS
        assert name not in LIFECYCLE_FUNCTIONS
        assert not hasattr(account_lifecycle, stem), "%s is back in the lifecycle port" % stem
    for helper in ("fresh_env_text", "env_path", "BRE_METACHARACTERS"):
        assert not hasattr(account, helper), "%s survived its only callers" % helper


def test_every_twin_function_has_exactly_one_python_home() -> None:
    """Each of the twenty-one is a callable in ONE of the two modules, never both.

    A function in both would be two implementations of one bash function, which is how `check_node_version` came to have two copies that needed a test to keep them agreeing.
    """
    for name in PORTED_FUNCTIONS:
        stem = name[len("account_") :]
        if stem == "db":
            continue
        assert callable(getattr(account, stem, None)), "%s is missing from the port" % stem
        assert not hasattr(account_lifecycle, stem), "%s is ported twice" % stem
    assert callable(account.db)
    for name, attr in LIFECYCLE_FUNCTIONS.items():
        assert callable(getattr(account_lifecycle, attr, None)), "%s has no port" % name
        assert not hasattr(account, attr), "%s is ported twice" % name
        assert name in account_lifecycle.__doc__, "%s is not named in the module docstring" % name


def test_check_node_version_has_one_python_copy() -> None:
    """The duplicate is gone: both account modules borrow `rediacc_ci.core.local_common`'s port, which carries the twin's `sort -V` comparator."""
    for gone in ("check_node_version", "version_tuple", "NODE_VERSION_MIN_DEFAULT"):
        assert not hasattr(account, gone), "%s came back into core/account.py" % gone
        assert not hasattr(account_lifecycle, gone), "%s is duplicated in the lifecycle port" % gone
    source = (paths.repo_root() / PORT).read_text(encoding="utf-8")
    assert "local_common.check_node_version()" in source


def test_the_verbs_are_served_by_these_ports_and_the_legacy_dispatcher_is_gone() -> None:
    """The cut-over claim, checked against the code that dispatches: every `account` verb and `rotation` reaches a function of these two modules, and nothing sources the bash twin to serve a verb."""
    root = paths.repo_root()
    assert not (root / ".ci/legacy/run-legacy.sh").exists()
    verbs = (root / ".ci/rediacc_ci/core/run_verbs.py").read_text(encoding="utf-8")
    for needle in (
        '"dev": lambda _rest: account_lifecycle.main(["dev"])',
        '"db": _account_db',
        "return account.db(rest)",
        '"stop": lambda _rest: account.stop()',
        '"totp": lambda rest: account.totp(',
        "account.rotation(argv)",
    ):
        assert needle in verbs, needle
    router = (root / "run.sh").read_text(encoding="utf-8")
    assert "account.sh" not in router


# -- the helpers, exercised directly -----------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("", 63),
        ("hello", 58),
        ("x" * 63, 0),
        ("x" * 70, 0),
    ],
    ids=["empty", "short", "exact", "overflow"],
)
def test_banner_row_pads_to_63_and_never_truncates(text: str, expected: int) -> None:
    row = account.banner_row(text)
    assert row.startswith("  │  ")
    assert row.endswith("│")
    body = row[len("  │  ") : -1]
    assert body.count(" ") - text.count(" ") == expected
    assert text in row


def test_grep_cut_keeps_every_match_the_way_the_twin_captures_them() -> None:
    """`grep` prints EVERY matching line, so a key written twice reaches the twin as two lines. The port used to keep only the first."""
    text = "gateway_port=%d\npids=1\ngateway_port=%d\n" % (ACCOUNT_DEV_PORT, ACCOUNT_DEV_PORT + 1)
    assert account.grep_cut(text, "gateway_port") == "4800\n4801"
    assert account.gateway_port_from_state(text) == "4800\n4801"
    assert account.state_pids("pids=1 2 3\n") == "1 2 3"
    proc = subprocess.run(
        ["bash", "-c", 'v=$(grep "^gateway_port=" | cut -d= -f2); printf "%s" "$v"'],
        input=text,
        capture_output=True,
        text=True,
        check=True,
    )
    assert proc.stdout == account.grep_cut(text, "gateway_port")


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ('{"code":"123456","secondsRemaining":17}', ("123456", "17")),
        # `??` keeps a zero that `||` would erase, which is why the twin uses both.
        ('{"code":"000000","secondsRemaining":0}', ("000000", "0")),
        ('{"code":"","secondsRemaining":5}', ("", "5")),
        ("{}", ("", "")),
        ("", ("", "")),
        ("not json at all", ("", "")),
    ],
    ids=["ordinary", "zero-seconds", "empty-code", "empty-object", "empty-body", "unparseable"],
)
def test_totp_fields_reproduces_the_twin_two_operators(body: str, expected) -> None:
    assert account.totp_fields(body) == expected


def test_totp_fields_agrees_with_the_node_the_twin_actually_runs() -> None:
    """The one helper whose twin is a JavaScript one-liner, compared against node.

    `.ci/lib/account.sh:652` parses the response with `node -e`, so the port's Python reimplementation is checked against that exact program rather than against a reading of it.
    """
    program = (
        'const d=JSON.parse(require("fs").readFileSync(0,"utf8")||"{}");'
        'console.log(d.code||"");console.log(d.secondsRemaining??"")'
    )
    for body in (
        '{"code":"123456","secondsRemaining":17}',
        '{"code":"000000","secondsRemaining":0}',
        '{"code":"","secondsRemaining":5}',
        "{}",
        "",
    ):
        proc = subprocess.run(
            ["node", "-e", program], input=body, capture_output=True, text=True, check=True
        )
        lines = proc.stdout.split("\n")
        assert account.totp_fields(body) == (lines[0], lines[1]), body


def test_parse_db_args_both_directions() -> None:
    assert account.parse_db_args([]) is False
    assert account.parse_db_args(["--studio"]) is True
    with pytest.raises(account.AccountError) as first:
        account.parse_db_args(["--bogus"])
    assert first.value.code == 2
    # Defect 4: the twin keeps parsing after the flag, so this refuses too.
    with pytest.raises(account.AccountError) as second:
        account.parse_db_args(["--studio", "--bogus"])
    assert second.value.code == 2


def _tuple_of(proc: subprocess.CompletedProcess) -> tuple[int, str, str]:
    return proc.returncode, proc.stdout, proc.stderr


def test_a_missing_curl_degrades_on_both_sides_instead_of_raising(tmp_path) -> None:
    """THE CASE THAT FOUND A REAL PORT DEFECT, kept because a plant here did not fire.

    A planted change to `rustfs_alive`'s empty-body test passed the whole differential, which said the empty-body branch was never reached: every scenario runs with curl installed. Reaching it meant taking curl away, and that measurement showed the twin returning 1 quietly through its `|| true` while the port raised `FileNotFoundError`, a traceback where a verdict belongs.

    The farm below is every binary in `/usr/bin` and `/bin` EXCEPT curl, because `constants.sh` and `local-common.sh` need a working environment to load at all and a hand-listed minimal PATH dies on `dirname` before it reaches the subject.
    """
    farm = tmp_path / "nocurl"
    farm.mkdir()
    linked = 0
    for directory in ("/usr/bin", "/bin"):
        source = pathlib.Path(directory)
        if not source.is_dir():
            continue
        for entry in source.iterdir():
            if entry.name == "curl" or (farm / entry.name).exists():
                continue
            (farm / entry.name).symlink_to(entry)
            linked += 1
    assert linked > 100, "the PATH farm collapsed to %d binaries; nothing below would run" % linked
    assert not (farm / "curl").exists(), "curl survived into the farm, so this proves nothing"
    assert shutil.which("curl") is not None, (
        "curl is absent anyway, so the control is not a control"
    )

    root = shadow_driver.build_sandbox(paths.repo_root())
    try:
        env = {
            "PATH": str(farm),
            "HOME": os.environ.get("HOME", "/tmp"),
            "LC_ALL": "C",
            "CONSOLE_ROOT_DIR": str(root),
            "REDIACC_CI_ROOT": str(root),
        }
        twin_rc, _twin_out, twin_err = diff.twin_call(
            TWIN, ["missing-curl"], _retired, work=(root, farm)
        )
        assert twin_rc == 1, "the twin did not reach the branch: %s" % twin_err
        port = subprocess.run(
            [
                sys.executable,
                "-c",
                "from rediacc_ci.core import account\nraise SystemExit(0 if account.rustfs_alive(%d) else 1)"
                % shadow_driver.DEAD_PORT,
            ],
            cwd=str(paths.repo_root()),
            env={**env, "PYTHONPATH": ".ci"},
            capture_output=True,
            text=True,
            check=False,
        )
        assert "Traceback" not in port.stderr, (
            "the port raised instead of answering: %s" % port.stderr
        )
        assert port.returncode == twin_rc
    finally:
        shutil.rmtree(root, ignore_errors=True)

    # THE OTHER DIRECTION: with curl present the same helper still reads a body.
    assert (
        account.curl_body(
            ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", "http://127.0.0.1:1/"]
        )
        == "000"
    )
    assert account.curl_body(["definitely-not-a-binary-on-this-host"]) == ""


def test_devbox_state_get_matches_the_bash_it_duplicates(tmp_path) -> None:
    """`devbox_state_get` is `.ci/lib/devbox.sh:124`, which this slice does not touch.

    The port re-implements it because a module cannot borrow from its importer, so the two are compared here on the shapes a real `.devbox-state` takes, INCLUDING a key that is absent and a file that is not there.
    """
    root = tmp_path / "root"
    root.mkdir()
    state = root / ".devbox-state"
    env = {"CONSOLE_ROOT_DIR": str(root)}

    def bash(key: str) -> tuple[int, str]:
        """`devbox_state_get <key>` over the current state file, from the golden frozen out of `devbox.sh`."""
        content = state.read_text(encoding="utf-8") if state.is_file() else None

        rc, out, _ = diff.twin_call(DEVBOX_TWIN, ["state_get", key, repr(content)], _retired)
        return rc, out

    assert bash("base_port") == (1, "")
    assert account.devbox_state_get("base_port", env) is None

    state.write_text("slug=demo\nbase_port=17100\n", encoding="utf-8")
    assert bash("base_port")[1].strip() == "17100"
    assert account.devbox_state_get("base_port", env) == "17100"
    assert bash("slug")[1].strip() == "demo"
    assert account.devbox_state_get("slug", env) == "demo"
    assert bash("nosuch")[1] == ""
    assert account.devbox_state_get("nosuch", env) == ""


def test_db_preferred_port_derives_the_devbox_studio_slot(tmp_path) -> None:
    """`.ci/lib/account.sh:977-1000`, the arithmetic the `db` scenario proves end to end."""
    root = tmp_path / "root"
    root.mkdir()
    env = {"CONSOLE_ROOT_DIR": str(root)}
    assert account.db_preferred_port(env) == account.DB_BROWSER_PREFERRED
    (root / ".devbox-state").write_text("base_port=17100\n", encoding="utf-8")
    assert account.db_preferred_port(env) == 17100 + account.DEVBOX_OFFSET_STUDIO
    # A state file with no base_port at all falls back rather than raising.
    (root / ".devbox-state").write_text("slug=demo\n", encoding="utf-8")
    assert account.db_preferred_port(env) == account.DB_BROWSER_PREFERRED


def test_db_path_prefers_the_environment(tmp_path) -> None:
    root = tmp_path / "root"
    env = {"CONSOLE_ROOT_DIR": str(root)}
    assert account.db_path(env).endswith("private/account/account.db")
    assert account.db_path(dict(env, DATABASE_PATH="/x/y.db")) == "/x/y.db"


# -- the licence, and the tools the scenarios really use ---------------------


def test_the_shadow_ledger_holds_five_equivalent_rows_over_five_trees() -> None:
    """The K=5 licence, read off disk rather than remembered from a session.

    Two of the first five rows (`env`, `fresh-env`) are HISTORY about writers deleted from both sides. Four more (`db`, `keys`, `probe`, `totp`) were appended on 2026-09-24 after `check_node_version`, `grep_cut` and the strict keygen changed this port, so the licence describes the bytes that ship. The live differential above is what compares today's code.
    """
    path = paths.repo_root() / LEDGER
    assert path.is_file(), "%s is missing; the port has no recorded licence" % LEDGER
    rows = [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    assert len(rows) >= 5, "%d row(s) recorded, five are required" % len(rows)
    assert all(row["verdict"] == "EQUIVALENT" for row in rows)
    assert len({row["tree"]["id"] for row in rows}) >= 5
    assert all(row["tree"]["clean"] for row in rows)
    assert all(TWIN in row["old"]["cmd"] for row in rows)
    assert all(PORT in row["new"]["cmd"] for row in rows)


def test_the_tools_the_scenarios_use_are_installed() -> None:
    """ANTI-VACUITY. Without these the scenarios compare two identical failures."""
    for tool in ("node", "openssl", "curl", "bash"):
        assert shutil.which(tool) is not None, (
            "%s is absent, so the scenarios that use it compare two identical failures "
            "and prove nothing about the port" % tool
        )


def test_the_driver_refuses_when_the_port_is_not_there() -> None:
    """The driver's own control, driven rather than read."""
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            DRIVER_MODULE,
            "--side",
            "new",
            "--port",
            ".ci/rediacc_ci/core/no-such-file.py",
            "probe",
        ],
        cwd=str(paths.repo_root()),
        env={**os.environ, "PYTHONPATH": ".ci"},
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == shadow_driver.EXIT_CANNOT_RUN
    assert "attests to nothing" in proc.stderr


def test_the_driver_has_no_bash_side() -> None:
    proc = subprocess.run(
        [sys.executable, "-m", DRIVER_MODULE, "--side", "old", "--port", PORT, "probe"],
        cwd=str(paths.repo_root()),
        env={**os.environ, "PYTHONPATH": ".ci"},
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 2
    assert "invalid choice" in proc.stderr


def test_the_paths_derive_from_console_root_and_nothing_else() -> None:
    """The one seam both implementations read, in both directions."""
    env = {"CONSOLE_ROOT_DIR": "/somewhere"}
    assert account.account_dir(env) == "/somewhere/private/account"
    assert account.state_file(env) == "/somewhere/.account-state"
    assert account.log_directory(env) == "/somewhere/.account-logs"
    assert account.devbox_state_file(env) == "/somewhere/.devbox-state"
    # With nothing set it falls back to the repository root, not to the cwd.
    assert account.console_root({}) == str(paths.repo_root())


def test_the_ported_module_has_no_launch_on_its_argv_surface() -> None:
    """`main` offers the twin's two public verbs plus `mint-dev-keys`, and refuses anything else."""
    assert account.main(["nosuch"]) == 2
    assert account.main([]) == 2
    assert account.main(["--help"]) == 0
    assert "totp" in account.USAGE
    assert "db" in account.USAGE
    assert "mint-dev-keys" in account.USAGE
    for name in ("dev", "stop", "reset", "seed-demo"):
        assert account.main([name]) == 2, "%s must not be reachable from this port" % name


def test_the_driver_offers_exactly_the_scenarios_with_a_floor() -> None:
    assert isinstance(shadow_driver.SCENARIOS, tuple)
    assert set(shadow_driver.SCENARIOS) == set(OBSERVATION_FLOOR)


def test_the_repo_root_is_a_checkout_with_the_port_in_it() -> None:
    """A last refusal: everything above is relative to this."""
    assert (paths.repo_root() / PORT).is_file()
    assert pathlib.Path(DRIVER).name == "shadow_driver.py"


# -- stop and rotation: REAL-RUN verification, not shadow-differential -------
#
# `account_stop` and `account_rotation` genuinely start and stop real infrastructure (Docker containers, tracked dev pids, and, through `account_rotation`, a real TypeScript CLI that mints and deletes credentials at AWS IAM, Cloudflare and GitHub), so `shadow_driver.py` does not drive them -- see its own module docstring, "WHAT IS NEVER DRIVEN HERE", which still lists both by name.
# These tests instead run the twin and the port against something real and check the OBSERVABLE SIDE EFFECT -- a process is actually dead, a port is actually free, real stdout from the real rotation CLI matches -- rather than trusting a return code alone.
#
# `rotation()`'s mutating subcommands (`rotate`, `check`, `deactivate`, `delete`, `sweep`, `init`) need live production credentials at AWS IAM / Cloudflare / GitHub and are NEVER invoked by anything below, or by anything else in this repository's test suite: only `list`, `status` and `history`, which read the committed, non-secret manifest and touch no platform.

ROTATION_CREDENTIAL_FREE_SUBCOMMANDS = ("list", "status", "history")

ROTATION_MUTATING_SUBCOMMANDS = ("rotate", "check", "deactivate", "delete", "sweep", "init")


def _alive(pid: int) -> bool:
    """`kill -0 "$pid"`: true process liveness, not zombie ambiguity.

    A child THIS TEST forked stays a zombie -- still answering `kill -0` -- until reaped, which is why every spawn below is paired with a background `Thread(target=proc.wait)`.
    The real dev-server processes `account_stop` targets in production are reaped by whatever forked them, not by the stopper, so a zombie-blind check here would report a killed process as still alive for a reason that is this test's own parentage rather than the port's behaviour.
    """
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _gone(pid: int, timeout: float = 5.0) -> bool:
    """True once `pid` stops answering `kill -0`, polling up to `timeout` seconds.

    "Reaped the moment it exits" is a thread, not an instant: right after `stop()` SIGKILLs a child, the reaper may not have run yet, and the zombie still answers `kill -0`. Asserting `_alive` immediately made this case flaky (#d49ae221: "stop() returned 0 but the real port occupant is still alive", PR #601 run 39761731646). A process `stop()` really missed stays alive past the timeout and still fails, five seconds later.
    """
    deadline = time.monotonic() + timeout
    while _alive(pid):
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.05)
    return True


def _spawn_reaped(argv: list[str], **kwargs) -> subprocess.Popen:
    """A real child process, reaped by a background thread the moment it exits, so `_alive()` reads real process-table state rather than a zombie."""
    proc = subprocess.Popen(argv, start_new_session=True, **kwargs)
    threading.Thread(target=proc.wait, daemon=True).start()
    return proc


def test_stop_real_run_kills_a_real_tracked_pid_and_a_real_port_occupant(
    monkeypatch, tmp_path
) -> None:
    """REAL RUN. A real `sleep` process and a real port listener are spawned -- not mocked -- `stop()` is pointed at them through a real state file, and the kill is confirmed with `kill -0` and the real socket bind, not by trusting the return code.

    Runs inside `shadow_driver.build_sandbox()`, the same isolated `CONSOLE_ROOT_DIR` the differential uses: `stop()` also runs `docker compose down --remove-orphans` in `$ACCOUNT_DIR`, and the sandbox's `private/account` is a real, empty, un-symlinked directory (`shadow_driver.build_sandbox`'s own docstring), so that call finds no compose file and cannot reach whatever the real `private/account` submodule has running.

    A failing `docker` is put first on `PATH` (the real `lsof` stays reachable), so `stop()`'s unscoped container teardown never touches the host's daemon and the case runs on every host, whether or not a real `./run.sh account dev` stack is up. It used to skip on such a host, which turned `check:ci-pytest` red wherever that stack ran.
    """
    monkeypatch.setenv("PATH", _fake_docker(tmp_path / "bin") + os.pathsep + os.environ["PATH"])
    work = shadow_driver.build_sandbox(paths.repo_root())
    tracked = listener = None
    try:
        env = shadow_driver.sandbox_env(work)
        state = pathlib.Path(account.state_file(env))

        tracked = _spawn_reaped(["sleep", "20"])
        listener = _spawn_reaped(
            [
                sys.executable,
                "-c",
                (
                    "import socket, time\n"
                    "s = socket.socket()\n"
                    "s.bind(('127.0.0.1', 0))\n"
                    "s.listen(1)\n"
                    "print(s.getsockname()[1], flush=True)\n"
                    "time.sleep(20)\n"
                ),
            ],
            stdout=subprocess.PIPE,
            text=True,
        )
        assert listener.stdout is not None, "stdout=subprocess.PIPE above, so this is always a pipe"
        port = int(listener.stdout.readline().strip())
        listener.stdout.close()

        assert _alive(tracked.pid), (
            "control: the tracked process must be alive before stop() runs, or killing it proves nothing"
        )
        assert _alive(listener.pid), (
            "control: the port occupant must be alive before stop() runs, or killing it proves nothing"
        )

        state.write_text(
            "gateway_port=%d\npids=%d\nwriter=%s\n" % (port, tracked.pid, account.writer_stamp()),
            encoding="utf-8",
        )
        rc = account.stop(env)

        assert rc == 0
        assert _gone(tracked.pid), "stop() returned 0 but the real tracked pid is still alive"
        assert _gone(listener.pid), "stop() returned 0 but the real port occupant is still alive"
        assert not state.is_file(), "stop() returned 0 but left the state file behind"
    finally:
        for proc in (tracked, listener):
            if proc is not None:
                with contextlib.suppress(OSError):
                    proc.kill()
                if proc.stdout is not None:
                    proc.stdout.close()
        shutil.rmtree(work, ignore_errors=True)


def _serve_info(handler) -> None:
    code = 200 if handler.path == "/account/api/v1/.well-known/server-info" else 404
    handler.send_response(code)
    handler.end_headers()
    handler.wfile.write(b"{}")


class _ServerInfo:
    """A loopback HTTP server that answers the dev gateway's server-info path with 200."""

    def __init__(self) -> None:
        handler = type(
            "Handler",
            (http.server.BaseHTTPRequestHandler,),
            {"log_message": lambda *_a: None},
        )
        setattr(handler, "do_" + "GET", _serve_info)
        self.server = http.server.HTTPServer(("127.0.0.1", 0), handler)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


class _SecondStartError(AssertionError):
    """dev() went past the reuse check into a fresh start."""


def _arm_dev(monkeypatch, work, calls: list[str]) -> pathlib.Path:
    env = shadow_driver.sandbox_env(work)
    monkeypatch.setenv("CONSOLE_ROOT_DIR", env["CONSOLE_ROOT_DIR"])
    monkeypatch.setattr(account, "bws_exec", lambda *_a, **_k: calls.append("bws_exec"))
    monkeypatch.setattr(account_lifecycle, "_check_node", lambda: None)

    def second_start(*_a, **_k):
        calls.append("allocate_ports")
        raise _SecondStartError("a second stack was started")

    monkeypatch.setattr(account, "allocate_ports", second_start)
    monkeypatch.setattr(
        account_lifecycle, "_stop_previous", lambda _state: calls.append("stop_previous")
    )
    return pathlib.Path(account.state_file(env))


def test_dev_reuses_a_live_stack_and_starts_no_second(monkeypatch, capsys) -> None:
    """A state file naming a live pid and a gateway answering server-info is reused: URL printed, rc 0, nothing stopped, nothing spawned, state untouched."""
    work = shadow_driver.build_sandbox(paths.repo_root())
    tracked = None
    gateway = _ServerInfo()
    try:
        calls: list[str] = []
        state = _arm_dev(monkeypatch, work, calls)
        tracked = _spawn_reaped(["sleep", "15"])
        body = "gateway_port=%d\npids=%d\nwriter=%s\n" % (
            gateway.port,
            tracked.pid,
            account.writer_stamp(),
        )
        state.write_text(body, encoding="utf-8")

        assert account_lifecycle.dev() == 0
        assert calls == [], calls
        assert _alive(tracked.pid)
        assert state.read_text(encoding="utf-8") == body
        assert "http://localhost:%d" % gateway.port in capsys.readouterr().out
    finally:
        gateway.close()
        if tracked is not None:
            with contextlib.suppress(OSError):
                tracked.kill()
        shutil.rmtree(work, ignore_errors=True)


@pytest.mark.parametrize("shape", ["dead-pid", "dead-port", "foreign-writer", "no-pids"])
def test_dev_replaces_a_stale_state_file(monkeypatch, shape) -> None:
    """Dead pids, a dead gateway port, another writer's stamp or no pids at all: the state is stale, the previous instance is cleaned and a fresh start begins."""
    work = shadow_driver.build_sandbox(paths.repo_root())
    tracked = None
    gateway = _ServerInfo()
    try:
        calls: list[str] = []
        state = _arm_dev(monkeypatch, work, calls)
        tracked = _spawn_reaped(["sleep", "15"])
        port, pids, writer = gateway.port, str(tracked.pid), account.writer_stamp()
        if shape == "dead-pid":
            pids = "4194302"
        elif shape == "dead-port":
            gateway.close()
        elif shape == "foreign-writer":
            writer = FOREIGN_WRITER
        else:
            pids = ""
        state.write_text(
            "gateway_port=%d\npids=%s\nwriter=%s\n" % (port, pids, writer), encoding="utf-8"
        )

        assert account_lifecycle.live_stack_port(str(state)) is None
        with pytest.raises(_SecondStartError):
            account_lifecycle.dev()
        assert calls == ["bws_exec", "stop_previous", "allocate_ports"], calls
    finally:
        if shape != "dead-port":
            gateway.close()
        if tracked is not None:
            with contextlib.suppress(OSError):
                tracked.kill()
        shutil.rmtree(work, ignore_errors=True)


def test_stop_kills_the_whole_tree_not_only_the_recorded_pid(monkeypatch, tmp_path) -> None:
    """The recorded pid is a job leader (npm exec -> sh -> server). Its child and grandchild must die with it."""
    monkeypatch.setenv("PATH", _fake_docker(tmp_path / "bin") + os.pathsep + os.environ["PATH"])
    work = shadow_driver.build_sandbox(paths.repo_root())
    leader = None
    try:
        env = shadow_driver.sandbox_env(work)
        state = pathlib.Path(account.state_file(env))
        childfile = tmp_path / "child.pid"
        leader = _spawn_reaped(
            ["sh", "-c", "sh -c 'sleep 15 & echo $! > %s; wait' & wait" % childfile]
        )
        for _ in range(100):
            if childfile.is_file() and childfile.read_text().strip():
                break
            time.sleep(0.05)
        child = int(childfile.read_text().strip())
        assert _alive(child)
        state.write_text(
            "gateway_port=1\npids=%d\nwriter=%s\n" % (leader.pid, account.writer_stamp()),
            encoding="utf-8",
        )
        assert account.stop(env) == 0
        assert _gone(leader.pid)
        assert _gone(child), "stop() left a descendant of the recorded pid running"
    finally:
        if leader is not None:
            with contextlib.suppress(OSError):
                leader.kill()
        shutil.rmtree(work, ignore_errors=True)


FOREIGN_WRITER = "some-devbox/pid:[4026532999]"


def _fake_docker(directory: pathlib.Path) -> str:
    """A `docker` that fails every call, so the two tests below need no skip: `account_stop`'s unscoped container teardown and ghost clean reach this instead of the machine's real daemon, and the pid handling under test runs exactly as it would."""
    directory.mkdir(parents=True, exist_ok=True)
    fake = directory / "docker"
    fake.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    fake.chmod(0o755)
    return str(directory)


@pytest.mark.parametrize("writer_line", ["writer=%s\n" % FOREIGN_WRITER, ""])
def test_stop_real_run_leaves_pids_from_another_writer_alone(
    writer_line: str, capfd, monkeypatch, tmp_path
) -> None:
    """REAL RUN, THE CONTROL FOR THE SHARED STATE FILE. The host and the devbox share `.account-state`, and a `pids=` line written in the container names unrelated processes on the host. A real process stands in for that unrelated host process: stamped by another writer, or not stamped at all, it must survive `stop()`, and the refusal must be said.

    Red without `account.state_owned`: the tracked pid is killed. `PATH` holds only a failing `docker`, so the teardown touches no real container and `lsof` is absent (the port is closed anyway).
    """
    work = shadow_driver.build_sandbox(paths.repo_root())
    tracked = None
    try:
        env = shadow_driver.sandbox_env(work)
        state = pathlib.Path(account.state_file(env))
        tracked = _spawn_reaped(["sleep", "20"])
        assert _alive(tracked.pid), "control: the bystander must be alive before stop() runs"
        closed = socket.socket()
        closed.bind(("127.0.0.1", 0))
        port = closed.getsockname()[1]
        closed.close()
        state.write_text(
            "gateway_port=%d\npids=%d\n%s" % (port, tracked.pid, writer_line), encoding="utf-8"
        )
        monkeypatch.setenv("PATH", _fake_docker(tmp_path / "bin"))
        rc = account.stop(env)
        err = capfd.readouterr().err
        assert rc == 0
        assert _alive(tracked.pid), "stop() signalled a pid another writer recorded"
        assert "Not signalling the pids in %s" % state in err, err
        assert ("written by %s" % (FOREIGN_WRITER if writer_line else "an unstamped writer")) in err
        assert "(%s)" % account.writer_stamp() in err
    finally:
        if tracked is not None:
            with contextlib.suppress(OSError):
                tracked.kill()
        shutil.rmtree(work, ignore_errors=True)


def test_the_writer_stamp_names_this_pid_namespace() -> None:
    """`account.writer_stamp()` carries this process's own pid namespace, which is what tells the host from the devbox. (The twin's `account_writer_stamp` printed the same identity; the comparison went with the bash.)"""
    assert account.writer_stamp().endswith("/" + os.readlink("/proc/self/ns/pid"))


def _run_rotation_subcommand_via_bash(args: list[str]) -> subprocess.CompletedProcess:
    """`./run.sh rotation <args>`, the real dispatcher, against the real `private/account` manifest."""
    return subprocess.run(
        ["./run.sh", "rotation", *args],
        cwd=str(paths.repo_root()),
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )


def _run_rotation_subcommand_via_port(args: list[str]) -> subprocess.CompletedProcess:
    """`account.rotation(args)`, in a fresh interpreter so its child's real stdout/stderr are captured cleanly rather than sharing pytest's own streams."""
    return subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys\nsys.path.insert(0, '.ci')\nfrom rediacc_ci.core import account\nsys.exit(account.rotation(sys.argv[1:]))",
            *args,
        ],
        cwd=str(paths.repo_root()),
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )


@pytest.mark.parametrize("subcommand", ROTATION_CREDENTIAL_FREE_SUBCOMMANDS)
def test_rotation_real_run_matches_the_twin_on_credential_free_subcommands(subcommand: str) -> None:
    """REAL RUN, both sides, real `npx tsx`, real manifest, no mock and no sandbox.

    `list`/`status`/`history` are read-only against the committed, non-secret `private/account/rotation-manifest.json` (see `commands/list.ts`, `commands/status.ts`, `commands/history.ts`: each one's own docstring says "Reads from the manifest only; does not query platform state"), so running them for real touches no credential and no live platform.
    This is deliberately NOT run inside a sandbox: the point is the real dispatcher against the real, committed manifest, and there is nothing here to isolate.
    """
    bash = _run_rotation_subcommand_via_bash([subcommand])
    port = _run_rotation_subcommand_via_port([subcommand])
    assert bash.returncode == port.returncode, (
        subcommand,
        bash.returncode,
        port.returncode,
        bash.stderr,
        port.stderr,
    )
    assert bash.stdout == port.stdout, (subcommand, bash.stdout, port.stdout)
    assert bash.stderr == port.stderr, (subcommand, bash.stderr, port.stderr)


def test_rotation_mutating_subcommands_are_named_but_never_invoked() -> None:
    """ANTI-VACUITY, the other direction: the credential-free list above is not simply everything the twin offers.

    `rotate`/`check`/`deactivate`/`delete`/`sweep`/`init` need live AWS IAM, Cloudflare or GitHub credentials (`private/account/CLAUDE.md`, "Secret Rotation") and running any of them for real from a test would mint, rotate or delete a real credential.
    This records the boundary as a checked fact -- the two lists partition the CLI's real subcommand set -- rather than as a comment nobody re-verifies against `index.ts` drifting.
    """
    index_ts = (paths.repo_root() / "private/account/scripts/rotation/index.ts").read_text(
        encoding="utf-8"
    )
    all_named = set(ROTATION_CREDENTIAL_FREE_SUBCOMMANDS) | set(ROTATION_MUTATING_SUBCOMMANDS)
    for subcommand in all_named:
        assert "'%s'," % subcommand in index_ts or "'%s':" % subcommand in index_ts, (
            "%s is no longer a real rotation subcommand; the safe/unsafe partition above needs updating"
            % subcommand
        )
    for subcommand in ROTATION_MUTATING_SUBCOMMANDS:
        assert subcommand not in ROTATION_CREDENTIAL_FREE_SUBCOMMANDS


# -- mint-dev-keys: throwaway CI keys, no twin ---------------------------------


def _mint(env: dict[str, str]) -> subprocess.CompletedProcess:
    """`python3 -m rediacc_ci.core.account mint-dev-keys` in a fresh interpreter, so stdout and stderr are the real streams."""
    return subprocess.run(
        [sys.executable, "-m", "rediacc_ci.core.account", "mint-dev-keys"],
        cwd=str(paths.repo_root()),
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )


def _mint_env(**extra: str) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k != "GITHUB_ENV"}
    env["PYTHONPATH"] = ".ci"
    env.update(extra)
    return env


def test_mint_dev_keys_appends_exactly_six_named_lines_and_prints_no_value(tmp_path) -> None:
    """The whole contract: six `NAME=value` lines appended, non-empty values, names only on stderr, and stdout exactly one `::add-mask::` per value."""
    target = tmp_path / "github_env"
    target.write_text("EARLIER=kept\n", encoding="utf-8")
    proc = _mint(_mint_env(GITHUB_ENV=str(target)))
    assert proc.returncode == 0, proc.stderr

    lines = target.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "EARLIER=kept", "the file was rewritten instead of appended to"
    minted = lines[1:]
    assert [line.split("=", 1)[0] for line in minted] == list(account.CRYPTO_KEYS)
    values = [line.split("=", 1)[1] for line in minted]
    assert all(values), "an empty value was written"
    assert len(set(values)) == 6, "two of the six minted values are identical"
    # Masked, or every later step's env block prints them in this public repo's logs; the runner consumes these lines unshown.
    assert proc.stdout.splitlines() == ["::add-mask::%s" % v for v in values], (
        "stdout must be exactly one ::add-mask:: per minted value, in order"
    )

    for value in values:
        assert value not in proc.stderr, "a minted value reached stderr"
    for name in account.CRYPTO_KEYS:
        assert name in proc.stderr, "%s is not named on stderr" % name
    assert "6 throwaway dev key(s)" in proc.stderr


def test_mint_dev_keys_refuses_without_github_env(tmp_path) -> None:
    """No GITHUB_ENV, no write anywhere: exit 2, one reason on stderr, nothing on stdout, and no file appears."""
    before = sorted(p.name for p in tmp_path.iterdir())
    for env in (_mint_env(), _mint_env(GITHUB_ENV="")):
        proc = _mint(env)
        assert proc.returncode == 2, (proc.returncode, proc.stderr)
        assert proc.stdout == ""
        assert "GITHUB_ENV is not set" in proc.stderr
        assert "ACCOUNT_" not in proc.stderr, "a refusal still minted and named keys"
    assert sorted(p.name for p in tmp_path.iterdir()) == before


def test_mint_dev_keys_writes_nothing_when_a_value_comes_back_empty(tmp_path, monkeypatch) -> None:
    """A missing `node` or `openssl` is an EMPTY capture, not an error, so the refusal has to be the port's own."""
    target = tmp_path / "github_env"
    target.write_text("", encoding="utf-8")
    monkeypatch.setattr(
        account,
        "generate_crypto_keys",
        lambda: account.CryptoKeys("p", "", "x", "y", "jwt", "api"),
    )
    assert account.mint_dev_keys({"GITHUB_ENV": str(target)}) == 1
    assert target.read_text(encoding="utf-8") == "", "a partial key set was written"
    monkeypatch.setattr(
        account,
        "generate_crypto_keys",
        lambda: account.CryptoKeys("p", "q\nINJECTED=1", "x", "y", "jwt", "api"),
    )
    assert account.mint_dev_keys({"GITHUB_ENV": str(target)}) == 1
    assert target.read_text(encoding="utf-8") == "", "a multi-line value was written"


def test_mint_dev_keys_takes_no_arguments(tmp_path, monkeypatch) -> None:
    """GITHUB_ENV is SET here, so the 2 is the argument refusal and not the missing-file one, and the file stays empty."""
    target = tmp_path / "github_env"
    target.write_text("", encoding="utf-8")
    monkeypatch.setenv("GITHUB_ENV", str(target))
    assert account.main(["mint-dev-keys", "extra"]) == 2
    assert target.read_text(encoding="utf-8") == "", "extra arguments still minted keys"


def test_mint_dev_keys_covers_exactly_the_account_dev_required_names() -> None:
    """The reason the verb works at all: with no token, `bws_env exec` proceeds only when every REQUIRED name of the profile is set, so the minted set must be that set."""
    supply = json.loads(
        (paths.repo_root() / ".ci/config/secret-supply.json").read_text(encoding="utf-8")
    )
    required = supply["consumers"]["account-dev"]["required"]
    locals_ = [spec.split(">", 1)[-1].strip() for spec in required]
    assert sorted(locals_) == sorted(account.CRYPTO_KEYS)


# -- the lifecycle half: a stub-farm transcript differential --------------------
#
# `rediacc_ci.core.account_lifecycle` ports the eleven functions that start, stop or talk to real infrastructure. `account_lifecycle_shadow_driver` runs each case as its own process per side with the external programs stubbed, and every case below is the LIVE twin against the live port, not a replay.

LIFECYCLE_PORT = ".ci/rediacc_ci/core/account_lifecycle.py"
LIFECYCLE_MODULE = "rediacc_ci.core.account_lifecycle_shadow_driver"
LIFECYCLE_LEDGER = ".ci/shadow/w7p5b-account-lifecycle.observations.jsonl"
LIFECYCLE_SCENARIOS = sorted(lifecycle_driver.SCENARIOS)

# The floor each scenario must clear, rounded well down from the measured transcripts: the claim is that the scenario reached its subject, not a count.
LIFECYCLE_FLOOR = {
    "credentials": 300,
    "dev": 600,
    "e2e": 150,
    "helpers": 60,
    "reset": 60,
    "seed": 60,
    "stripe": 60,
    "test": 20,
}

_LIFECYCLE_CACHE: dict[tuple[str, str], tuple[int, str, str]] = {}

# RULE T: the lifecycle cases whose WHOLE transcript the port intentionally changed (`test_delta_l*`), per scenario. Everything else is compared byte for byte.
LIFECYCLE_DELTA_CASES = {
    "credentials": {"seed-null", "seed-not-json", "hostname-fails"},
    "dev": {"state-missing-key"},
    # state-file: the fixture state carries a gateway port and no lockfile hash, which the port now refuses as a gateway it cannot show fresh (worklist #c9037d2f); test_e2e_refuses_* below pin the refusal and the pass.
    "e2e": {"install-fails", "state-file"},
    "helpers": {"state-port-equals"},
    "seed": {"state-without-port", "curl-fails"},
    "stripe": {"sync-fails"},
}

# L7: the state file's `pids=` line is comma separated now. The twin wrote spaces, so this one spelling is normalised on both sides.
_PIDS_LINE = re.compile(r"(state pids=)([N,]+)")

# RULE T, worklist #3a8d1f46: two argv shapes the twin used and the port no longer does, each rewritten from the twin's spelling onto the port's (idempotent on the port's own lines). The dev logins' JSON body reaches curl on stdin, `--data @-`, where the twin wrote `-d <payload>`; docker reads the RustFS keys from its environment, `-e NAME`, where the twin wrote `-e NAME=VALUE`. The body no longer shows in a call transcript, so `test_delta_3a8d1f46_dev_credentials_send_every_body_on_stdin` pins what reaches stdin, and `test_delta_3a8d1f46_the_recording_still_carries_the_twins_argv` proves both rewrites still meet a twin line.
_CURL_BODY_ARG = re.compile(r"( -H Content-Type:\\ application/json) -d \S+$")
_DOCKER_ENV_VALUE = re.compile(r"(-e AWS_(?:ACCESS_KEY_ID|SECRET_ACCESS_KEY))=\S+")


def _argv_delta_3a8d1f46(line: str) -> str:
    line = _CURL_BODY_ARG.sub(lambda m: m.group(1) + " --data @-", line)
    return _DOCKER_ENV_VALUE.sub(lambda m: m.group(1), line)


# The port records the lockfile hashes in the state file (the stale-Vite guard); the twin has no such lines, so both spellings are dropped on both sides.
_LOCK_SHA_LINE = re.compile(r"\| state (web_lock_sha|lock_sha)=")


def _lifecycle_comparable(lines: list[str], scenario: str) -> list[str]:
    skip = LIFECYCLE_DELTA_CASES.get(scenario, set())
    kept = []
    for line in lines:
        parts = line.split(" ", 2)
        if len(parts) > 1 and parts[0] == "obs" and parts[1] in skip:
            continue
        if _LOCK_SHA_LINE.search(line):
            continue
        delta = _argv_delta_3a8d1f46(line)
        kept.append(_PIDS_LINE.sub(lambda m: m.group(1) + m.group(2).replace(",", " "), delta))
    return kept


def _run_lifecycle(side: str, scenario: str) -> tuple[int, str, str]:
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            LIFECYCLE_MODULE,
            "--side",
            side,
            "--port",
            LIFECYCLE_PORT,
            scenario,
        ],
        cwd=str(paths.repo_root()),
        env={**os.environ, "PYTHONPATH": ".ci"},
        capture_output=True,
        text=True,
        check=False,
        timeout=900,
    )
    return proc.returncode, proc.stdout, proc.stderr


def drive_lifecycle(side: str, scenario: str) -> tuple[int, str, str]:
    """One side of one lifecycle scenario, run once per session and remembered. The bash side is the golden frozen from `account.sh`."""
    key = (side, scenario)
    if key not in _LIFECYCLE_CACHE:
        if side == "old":
            _LIFECYCLE_CACHE[key] = diff.twin_call(
                TWIN,
                ["lifecycle", scenario],
                _retired,
                port=lambda: _run_lifecycle("new", scenario),
            )
        else:
            _LIFECYCLE_CACHE[key] = _run_lifecycle(side, scenario)
    return _LIFECYCLE_CACHE[key]


@pytest.mark.xdist_group(LIFECYCLE_GROUP)
@pytest.mark.parametrize("scenario", LIFECYCLE_SCENARIOS)
def test_the_lifecycle_port_matches_the_live_twin(scenario: str) -> None:
    old_rc, old_out, old_err = drive_lifecycle("old", scenario)
    new_rc, new_out, new_err = drive_lifecycle("new", scenario)
    assert old_rc == 0, "the bash side could not run: %s" % old_err
    assert new_rc == 0, "the port side could not run: %s" % new_err
    old = _lifecycle_comparable(old_out.splitlines(), scenario)
    new = _lifecycle_comparable(new_out.splitlines(), scenario)
    if old != new:
        diverged = sorted(set(old) ^ set(new))
        pytest.fail("scenario %s diverged:\n%s" % (scenario, "\n".join(diverged[:40])))


@pytest.mark.xdist_group(LIFECYCLE_GROUP)
@pytest.mark.parametrize("scenario", LIFECYCLE_SCENARIOS)
def test_each_lifecycle_scenario_reached_its_subject(scenario: str) -> None:
    """ANTI-VACUITY. A transcript that collapsed to nothing would compare equal, and so would two sides that both failed to load the twin."""
    _, out, _ = drive_lifecycle("old", scenario)
    lines = [line for line in out.splitlines() if line.startswith("obs ")]
    assert len(lines) >= LIFECYCLE_FLOOR[scenario], (scenario, len(lines))
    cases = {case.name for case in lifecycle_driver.SCENARIOS[scenario]}
    seen = {line.split(" ", 2)[1] for line in lines}
    assert cases <= seen, "cases that printed nothing: %s" % sorted(cases - seen)
    assert "command not found" not in "\n".join(
        line for line in lines if "no-jq" not in line and "no-node" not in line
    ), "a stub or a twin function was missing on PATH"


@pytest.mark.xdist_group(LIFECYCLE_GROUP)
@pytest.mark.parametrize("side", ["old", "new"])
def test_account_dev_signals_only_the_pids_this_writer_recorded(side: str) -> None:
    """The live differential compares the sides with each other, so both refusing nothing would still agree. This pins the outcome on each side: a real process named in a state file stamped by this writer is ended, one stamped by another host or container, or not stamped, survives."""
    _, out, _ = drive_lifecycle(side, "dev")
    assert "obs previous-owned foreign alive=0 signal=15" in out
    assert "obs previous-foreign foreign alive=1" in out
    assert "obs previous-unstamped foreign alive=1" in out
    assert (
        "obs previous-foreign err#1| ⚠ Not signalling the pids in <root>/.account-state: written by another-host/pid:[4026532999], not by this host and pid namespace (<self-stamp>). Skipping them."
        in out
    )
    assert (
        "obs previous-unstamped err#1| ⚠ Not signalling the pids in <root>/.account-state: written by an unstamped writer"
        in out
    )


def test_the_lifecycle_corpus_covers_every_side_effecting_function() -> None:
    assert set(LIFECYCLE_SCENARIOS) == set(LIFECYCLE_FLOOR)
    driven = {
        lifecycle_driver.FN[case.verb]
        for cases in lifecycle_driver.SCENARIOS.values()
        for case in cases
    }
    # `account_spawn` has no verb of its own: the `tree` cleanup case calls it directly, and every `dev` case reaches it for Astro and Vite.
    driven.add("account_spawn")
    assert driven == set(LIFECYCLE_FUNCTIONS), sorted(driven ^ set(LIFECYCLE_FUNCTIONS))
    assert set(lifecycle_driver.FN) == set(lifecycle_driver.INNER)


@pytest.mark.xdist_group(LIFECYCLE_GROUP)
def test_the_lifecycle_transcripts_carry_what_the_comparison_needs() -> None:
    """A CONTROL ON THE COMPARISON: each of these is a line a wrong port would change, and each is really in the transcript."""
    _, dev_out, _ = drive_lifecycle("old", "dev")
    for needle in (
        "obs previous-instance call#1| kill -9 4194303",
        "obs reuse-rustfs side#9| env WEBAUTHN_ORIGIN=http://localhost:%d" % ACCOUNT_DEV_PORT,
        "obs no-docker-with-stripe side#16| state pids=N N N",
        "obs no-docker-with-stripe bg| npx astro dev --port 4802 --host 192.0.2.10",
        "obs gateway-fails rc=3",
        "obs astro-never rc=1",
        "obs state-missing-key rc=1",
    ):
        assert needle in dev_out, needle
    assert "Dev logins (fresh passwords each start)" in dev_out, (
        "the forked credentials job never printed"
    )
    _, cred_out, _ = drive_lifecycle("old", "credentials")
    assert "obs seed-null rc=1" in cred_out
    assert "obs hostname-fails rc=64" in cred_out
    assert "obs seed-null out#" not in cred_out, "twin behaviour 3 is a SILENT death"
    _, seed_out, _ = drive_lifecycle("old", "seed")
    assert "obs curl-fails rc=7" in seed_out
    assert "Could not reach" not in seed_out, "twin behaviour 1: that branch is dead code"
    _, helpers_out, _ = drive_lifecycle("old", "helpers")
    assert "obs cleanup-kills-foreign foreign alive=0 signal=15" in helpers_out
    _, reset_out, _ = drive_lifecycle("old", "reset")
    assert "obs whole side#2| len ACCOUNT_ED25519_PUBLIC_KEY=60" in reset_out
    assert "obs push-fails tree| private/account/account.db file" in reset_out, (
        "a failed push must leave the database alone"
    )


# Each plant is a defect a plausible port could have. Every one is run against a MUTATED COPY of the package, never the tracked file, and each must change the transcript of the case named.
LIFECYCLE_PLANTS = (
    ("helpers", "cleanup-kills-foreign", "os.kill(pid, signal.SIGTERM)", "pid and None"),
    ("seed", "http-500-json", 'if http_code != "200":', 'if http_code not in ("200", "500"):'),
    ("stripe", "happy", "secret[:12]", "secret[:11]"),
    ("dev", "previous-instance", "for offset in (0, 1, 2):", "for offset in (0, 1):"),
    ("dev", "reuse-rustfs", '",".join(str(p) for p in pids)', '";".join(str(p) for p in pids)'),
)


def _planted_repo(
    tmp_path: pathlib.Path, old: str, new: str, target_rel: str = LIFECYCLE_PORT
) -> pathlib.Path:
    """A repository view whose `.ci/rediacc_ci` is a COPY carrying one plant, and everything else a symlink to the checkout."""
    repo = paths.repo_root()
    fake = tmp_path / "repo"
    (fake / ".ci" / "scripts").mkdir(parents=True)
    for rel in (".ci/config", ".ci/scripts/lib", ".devcontainer", "scripts"):
        (fake / rel).symlink_to(repo / rel)
    shutil.copytree(
        repo / ".ci" / "rediacc_ci",
        fake / ".ci" / "rediacc_ci",
        ignore=shutil.ignore_patterns("__pycache__", "tests"),
    )
    target = fake / target_rel
    text = target.read_text(encoding="utf-8")
    assert text.count(old) == 1, "the plant %r no longer matches the port exactly once" % old
    target.write_text(text.replace(old, new), encoding="utf-8")
    return fake


@pytest.mark.xdist_group(LIFECYCLE_GROUP)
@pytest.mark.parametrize(
    ("scenario", "case_name", "old", "new"), LIFECYCLE_PLANTS, ids=[p[1] for p in LIFECYCLE_PLANTS]
)
def test_a_planted_defect_in_the_lifecycle_port_is_caught(
    tmp_path, scenario, case_name, old, new
) -> None:
    """PLANTED-DEFECT RUNS. The frozen twin transcript against a copy of the port with one defect; the case's transcript must differ."""
    case = next(c for c in lifecycle_driver.SCENARIOS[scenario] if c.name == case_name)
    repo = paths.repo_root()
    fake = _planted_repo(tmp_path, old, new)
    with lifecycle_driver.locked():
        twin = [
            line
            for line in drive_lifecycle("old", scenario)[1].splitlines()
            if line.startswith("obs %s " % case_name)
        ]
        planted = lifecycle_driver.observe("new", fake, case)
        clean = lifecycle_driver.observe("new", repo, case)
    assert _lifecycle_comparable(clean, scenario) == _lifecycle_comparable(twin, scenario), (
        "the unplanted port disagrees on %s, so the plant proves nothing" % case_name
    )
    assert _lifecycle_comparable(planted, scenario) != _lifecycle_comparable(twin, scenario), (
        "the plant %r -> %r went unnoticed on %s" % (old, new, case_name)
    )


# Worklist #e45fc13c: `account_cleanup` signalled only the pid it tracked, so a dev server behind `npx` could outlive `account dev` on its port. Each side WITHOUT the process-group kill must orphan the tree job's child; each side with it must not.
UNGROUPED = {
    "new": (LIFECYCLE_PORT, "os.killpg(pid, signal.SIGTERM)", "os.kill(pid, signal.SIGTERM)"),
}


@pytest.mark.xdist_group(LIFECYCLE_GROUP)
@pytest.mark.parametrize("side", sorted(UNGROUPED))
def test_cleanup_without_the_group_kill_orphans_the_child(tmp_path, side) -> None:
    """THE CASE THAT FAILS WITHOUT THE FIX. The twin's side (a copy of `account.sh` minus the group kill) went with the bash; the port side is the fix."""
    case = next(c for c in lifecycle_driver.SCENARIOS["helpers"] if c.name == "cleanup-kills-tree")
    rel, old, new = UNGROUPED[side]
    fake = _planted_repo(tmp_path, old, new, target_rel=rel)
    with lifecycle_driver.locked():
        fixed = lifecycle_driver.observe(side, paths.repo_root(), case)
        unfixed = lifecycle_driver.observe(side, fake, case)
    assert "obs cleanup-kills-tree child alive=0" in fixed, fixed
    assert "obs cleanup-kills-tree child alive=1" in unfixed, (
        "with only the tracked pid signalled, the job's child should have survived: %s" % unfixed
    )


@pytest.mark.xdist_group(LIFECYCLE_GROUP)
def test_the_lifecycle_stub_farm_really_shadows_the_programs() -> None:
    """ANTI-VACUITY for the harness: the stubs are FIRST on PATH, so the twin cannot be reaching a real docker or curl."""
    case = lifecycle_driver.SCENARIOS["dev"][0]
    with lifecycle_driver.locked():
        root, farm = lifecycle_driver.build_sandbox(paths.repo_root(), case)
        try:
            env = lifecycle_driver.side_env(root, farm, case)
            for name in ("docker", "curl", "sleep", "ss", "openssl", "hostname", "lsof", "kill"):
                assert stubfarm.shadows(farm, name, env), "%s is not the stub" % name
        finally:
            shutil.rmtree(lifecycle_driver.base_dir(), ignore_errors=True)


def test_a_stub_passthrough_keeps_the_callers_stdin(tmp_path) -> None:
    """THE HARNESS DEFECT THIS WORK FOUND, pinned. A row's `sh` ran with the stub TABLE as its stdin, so the twin's `node -e ... <<<"$seed_json"` parsed table rows and `account_dev_credentials` died silently on every case."""
    farm = stubfarm.Farm(tmp_path / "farm")
    farm.stub("tool", logged=False)
    farm.respond("tool", "*", sh="exec cat")
    farm.respond("other", "*", out="A-LATER-ROW")
    env = farm.env({"PATH": "/usr/bin:/bin"})
    proc = subprocess.run(
        ["tool"], input="from-the-caller\n", env=env, capture_output=True, text=True, check=True
    )
    assert proc.stdout == "from-the-caller\n", proc.stdout


def test_the_lifecycle_ledger_holds() -> None:
    """The K=5 licence on disk, re-derived rather than trusted."""
    proc = subprocess.run(
        [
            "npx",
            "tsx",
            "scripts/lib/shadow-gate.ts",
            "--pair",
            "w7p5b-account-lifecycle",
            "--assert",
            "--k",
            "5",
        ],
        cwd=str(paths.repo_root()),
        capture_output=True,
        text=True,
        check=False,
        timeout=180,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    ledger = (paths.repo_root() / LIFECYCLE_LEDGER).read_text(encoding="utf-8")
    assert LIFECYCLE_MODULE in ledger
    assert LIFECYCLE_PORT in ledger


def test_the_lifecycle_argv_surface_dispatches_like_run_legacy() -> None:
    """`main` offers the verbs the `account` dispatch table sends to this half, and refuses the rest."""
    assert account_lifecycle.main([]) == 2
    assert account_lifecycle.main(["--help"]) == 0
    assert account_lifecycle.main(["nosuch"]) == 2
    for verb in ("dev", "test", "reset", "seed-demo"):
        assert verb in account_lifecycle.USAGE
    assert "test e2e" in account_lifecycle.USAGE


# -- Rule T: the twin's defects, fixed in the ports as INTENTIONAL DELTAS --------
#
# PLAN-retire-bash-oracles section 1 and task B4. Each case below pins the port's FIXED behaviour; the twin still has the defect, and the live differential above excludes exactly the cases named in `DELTA_CASES` / `LIFECYCLE_DELTA_CASES` (and `test_every_delta_case_still_diverges` proves each exclusion is still a real divergence, so a delta cannot go stale).
# The twin's behaviour is shown beside each fix, driven for real, so the claim "bash does this" is measured and not remembered.


def _bash_state(text: str, script: str, tmp_path) -> subprocess.CompletedProcess:
    state = tmp_path / ".account-state"
    state.write_text(text, encoding="utf-8")
    return subprocess.run(
        ["bash", "-c", "set -euo pipefail; ACCOUNT_STATE_FILE=%s; %s" % (state, script)],
        capture_output=True,
        text=True,
        check=False,
    )


def test_delta_a1_totp_names_a_state_file_without_a_gateway_port(tmp_path, capsys) -> None:
    """Defect A1, fixed: a state file with no `gateway_port=` line explains itself instead of dying silently with exit 1."""
    twin = _bash_state(
        "started=1\n",
        'g=$(grep "^gateway_port=" "$ACCOUNT_STATE_FILE" | cut -d= -f2); echo reached',
        tmp_path,
    )
    assert (twin.returncode, twin.stdout, twin.stderr) == (1, "", ""), (
        "the twin's silent death moved"
    )
    (tmp_path / ".account-state").write_text("started=1\n", encoding="utf-8")
    rc = account.totp(env={"CONSOLE_ROOT_DIR": str(tmp_path)})
    assert rc == 1
    assert (
        "Could not read gateway port from %s" % (tmp_path / ".account-state")
        in capsys.readouterr().err
    )


def test_delta_a2_banner_row_pads_by_characters() -> None:
    """Defect A2, fixed: a multibyte glyph no longer shifts the closing bar. The row is as wide as the ASCII row."""
    ascii_row = account.banner_row("hello, unicode")
    assert len(account.banner_row("héllo, ünicode")) == len(ascii_row)
    assert len(account.banner_row("→ arrow ✓ check")) == len(ascii_row)
    assert len(account_lifecycle._pad_bytes("é", 4)) == 4


def test_delta_a3_a_state_value_containing_an_equals_sign_survives() -> None:
    """Defect A3, fixed: the value is everything after the FIRST `=`, where `cut -d= -f2` kept the second field only."""
    assert account.gateway_port_from_state("gateway_port=a=b\n") == "a=b"
    assert account.grep_cut("k=x=y=z\nk=2\n", "k") == "x=y=z\n2"
    assert account_lifecycle.grep_cut("k=x=y\n", "k") == "x=y"


def test_delta_a4_unknown_option_after_studio_is_a_correct_refusal() -> None:
    """Defect A4 is NOT a defect, and this pins why it stays as it is: `account db --studio --bogus` refuses with exit 2 because an unrecognised option is refused wherever it sits. Rejecting it is the right answer, so port and twin agree."""
    with pytest.raises(account.AccountError) as excinfo:
        account.parse_db_args(["--studio", "--bogus"])
    assert excinfo.value.code == 2


@pytest.mark.parametrize("missing", ["gateway_port", "pids"])
def test_delta_a5_stop_runs_the_teardown_when_a_state_key_is_missing(
    missing: str, monkeypatch, tmp_path
) -> None:
    """Defect A5, fixed: a state file lacking `gateway_port=` or `pids=` no longer ends `stop()` before the teardown, so the state file is removed. The twin dies there and leaves it."""
    lines = {"gateway_port": "gateway_port=1\n", "pids": "pids=\n"}
    text = "".join(v for k, v in lines.items() if k != missing) + "started=1\n"
    twin = _bash_state(
        text,
        'old_gateway=$(grep "^gateway_port=" "$ACCOUNT_STATE_FILE" | cut -d= -f2); '
        'old_pids=$(grep "^pids=" "$ACCOUNT_STATE_FILE" | cut -d= -f2); rm -f "$ACCOUNT_STATE_FILE"',
        tmp_path,
    )
    assert twin.returncode == 1, "the twin's death moved"
    assert (tmp_path / ".account-state").exists(), "the twin's death moved"
    (tmp_path / ".account-state").write_text(text, encoding="utf-8")
    monkeypatch.setenv("PATH", _fake_docker(tmp_path / "bin"))
    assert account.stop({"CONSOLE_ROOT_DIR": str(tmp_path)}) == 0
    assert not (tmp_path / ".account-state").exists()


def test_delta_l1_seed_demo_reaches_its_could_not_reach_branch(
    monkeypatch, capsys, tmp_path
) -> None:
    """Defect L1, fixed: an unreachable gateway prints the message the twin wrote and could never reach, and ends 1."""
    monkeypatch.setenv("CONSOLE_ROOT_DIR", str(tmp_path))

    def capture(argv, **_kwargs):
        return (0, '{"email":"x"}') if argv[0] == "jq" else (7, "")

    monkeypatch.setattr(account_lifecycle, "_capture", capture)
    rc = account_lifecycle.main(["seed-demo", "a@b.c", "--port", "1"])
    err = capsys.readouterr().err
    assert rc == 1
    assert "Could not reach the account gateway on port 1" in err
    assert "Is the dev gateway running?" in err


def test_delta_l2_a_state_file_without_the_key_is_not_a_silent_death(monkeypatch, tmp_path) -> None:
    """Defect L2, fixed: `seed-demo` and the previous-instance stop treat a missing `gateway_port=` as an empty value (the preferred port, or nothing to stop) instead of ending silently."""
    monkeypatch.setenv("CONSOLE_ROOT_DIR", str(tmp_path))
    (tmp_path / ".account-state").write_text("started=1\n", encoding="utf-8")
    seen = []

    def capture(argv, **_kwargs):
        seen.append(argv)
        return (0, "x") if argv[0] == "jq" else (7, "")

    monkeypatch.setattr(account_lifecycle, "_capture", capture)
    account_lifecycle.main(["seed-demo", "a@b.c"])
    assert any(
        "127.0.0.1:%s/" % account.ACCOUNT_DEV_PORT_PREFERRED in part
        for argv in seen
        for part in argv
    ), seen
    monkeypatch.setattr(account_lifecycle, "_sleep", lambda _s: None)
    account_lifecycle._stop_previous(str(tmp_path / ".account-state"))
    assert not (tmp_path / ".account-state").exists()


def test_delta_l3_an_unreadable_seed_answer_still_prints_the_logins(monkeypatch, capsys) -> None:
    """Defect L3, fixed: when the seed-config-store answer is not JSON node can read, the logins are still printed with the recovery code shown as unavailable. The twin ends silently before the banner."""
    assert account_lifecycle.seed_fields("not json") == ("", "", "")
    assert account_lifecycle.seed_fields("null") == ("", "", "")
    _drive_credentials(monkeypatch, seed="not json", hostname=(0, "10.0.0.5 10.0.0.6"))
    out = capsys.readouterr().out
    assert "Dev logins" in out
    assert "<unavailable>" in out


def test_delta_l4_a_failing_hostname_still_prints_the_logins(monkeypatch, capsys) -> None:
    """Defect L4, fixed: `hostname -I` failing (macOS) drops the Network row and keeps the banner."""
    _drive_credentials(monkeypatch, seed='{"existing":1}', hostname=(1, ""))
    out = capsys.readouterr().out
    assert "Dev logins" in out
    assert "Network:" not in out


def _drive_credentials(monkeypatch, *, seed: str, hostname: tuple[int, str]) -> None:
    monkeypatch.setattr(account_lifecycle, "_run", lambda _argv, **_kw: 0)
    monkeypatch.setattr(account_lifecycle, "_sleep", lambda _s: None)

    def capture(argv, **_kwargs):
        if argv[0] == "openssl":
            return 0, "abcd1234abcd1234"
        if argv[0] == "hostname":
            return hostname
        return 0, seed

    monkeypatch.setattr(account_lifecycle, "_capture", capture)
    assert account_lifecycle.dev_credentials("4800") == 0


def test_delta_l5_a_failing_stripe_sync_says_so(monkeypatch, capsys, tmp_path) -> None:
    """Defect L5, fixed: a failing `stripe-sync.ts` still ends the run with npx's status, but now names what failed, where the twin died with only the tail of npx's own output."""
    monkeypatch.setenv("STRIPE_SANDBOX_SECRET_KEY", "sk_test_x")
    monkeypatch.setenv("CONSOLE_ROOT_DIR", str(tmp_path))
    monkeypatch.setattr(account_lifecycle.shutil, "which", lambda _name: "/bin/true")
    monkeypatch.setattr(account_lifecycle, "_capture", lambda _argv, **_kw: (1, ""))

    def failing_tail(_argv, _count, **_kw):
        raise account_lifecycle.ErrexitError(3, "npx exited 3")

    monkeypatch.setattr(account_lifecycle, "_tail", failing_tail)
    with pytest.raises(account_lifecycle.ErrexitError) as excinfo:
        account_lifecycle.stripe_auto()
    assert excinfo.value.code == 3
    assert "Stripe product sync failed" in capsys.readouterr().err


def test_stripe_listen_takes_its_key_from_the_environment(monkeypatch, tmp_path) -> None:
    """Review a98fe53d.5, worklist #773eccc5. A real `stripe` on PATH (a recording script) is spawned the way the port spawns it: the key is in its environment as STRIPE_API_KEY and nowhere on its argv, and its webhook secret is still read back."""
    key = "sk_test_" + "k" * 24
    record = tmp_path / "stripe.record"
    bindir = tmp_path / "bin"
    bindir.mkdir()
    fake = bindir / "stripe"
    fake.write_text(
        "#!/bin/sh\n"
        'printf "argv=%%s\\n" "$*" >"%s"\n'
        'printf "env=%%s\\n" "$STRIPE_API_KEY" >>"%s"\n'
        "echo 'Ready! Your webhook signing secret is whsec_0123456789abcdef'\n" % (record, record),
        encoding="utf-8",
    )
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", "%s:%s" % (bindir, os.environ["PATH"]))
    monkeypatch.setenv("STRIPE_SANDBOX_SECRET_KEY", key)
    monkeypatch.delenv("STRIPE_API_KEY", raising=False)
    monkeypatch.delenv("STRIPE_SANDBOX_WEBHOOK_SECRET", raising=False)
    monkeypatch.setattr(account_lifecycle, "_capture", lambda _argv, **_kw: (1, ""))
    monkeypatch.setattr(account_lifecycle, "_tail", lambda *_a, **_kw: None)
    monkeypatch.setattr(account_lifecycle, "_sleep", lambda _s: __import__("time").sleep(0.05))
    assert account_lifecycle.stripe_auto() == 0
    lines = record.read_text(encoding="utf-8").splitlines()
    assert lines[0].startswith("argv=listen --forward-to "), lines
    assert key not in lines[0], "the stripe key reached the listener's argv"
    assert lines[1] == "env=%s" % key, "the listener did not get the key in its environment"


def _recording_run(calls: list[tuple[list[str], object, dict | None]]):
    """A `subprocess.run` that records argv, stdin and environment, and answers the few programs `dev_credentials` and `start_rustfs` read."""

    def run(argv, **kwargs):
        calls.append((list(argv), kwargs.get("input"), kwargs.get("env")))
        text = "a" * 16 if argv[0] == "openssl" else ""
        rc = 1 if argv[0] == "hostname" else 0
        out: str | bytes = text if kwargs.get("text") else text.encode()
        return subprocess.CompletedProcess(argv, rc, stdout=out, stderr=None)

    return run


def test_delta_3a8d1f46_dev_credentials_send_every_body_on_stdin(monkeypatch, capsys) -> None:
    """Worklist #3a8d1f46. Every `/test` POST carries its JSON body on curl's stdin (`--data @-`), so the fresh dev passwords and the store password reach no argv."""
    calls: list[tuple[list[str], object, dict | None]] = []
    monkeypatch.setattr(account_lifecycle.subprocess, "run", _recording_run(calls))
    assert account_lifecycle.dev_credentials("4800") == 0
    capsys.readouterr()
    posts = [(argv, body) for argv, body, _env in calls if argv[0] == "curl" and "POST" in argv]
    assert len(posts) == 6, [argv for argv, _ in posts]
    bodies: list[str] = []
    for argv, body in posts:
        assert argv[-2:] == ["--data", "@-"], argv
        assert "-d" not in argv, argv
        assert "password" not in " ".join(argv), argv
        assert isinstance(body, (bytes, str)), argv
        bodies.append(body.decode() if isinstance(body, bytes) else body)
        assert bodies[-1], argv
    assert sum('"password":"%s"' % ("a" * 16) in b for b in bodies) == 3
    assert any('"password":"%s"' % account_lifecycle.STORE_PASSWORD in b for b in bodies)


def test_delta_3a8d1f46_the_rustfs_keys_reach_docker_through_its_environment(
    monkeypatch, capsys
) -> None:
    """Worklist #3a8d1f46. `docker run -e NAME` copies NAME from docker's own environment, so the RustFS keys are on no argv, and the bucket call still gets them."""
    calls: list[tuple[list[str], object, dict | None]] = []
    monkeypatch.setenv("CONFIG_R2_ACCESS_KEY_ID", "rustfs-key-id")
    monkeypatch.setenv("CONFIG_R2_SECRET_ACCESS_KEY", "rustfs-secret")
    for name in ("CONFIG_R2_ENDPOINT", "CONFIG_R2_BUCKET"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(account_lifecycle, "_docker_usable", lambda: True)
    monkeypatch.setattr(account_lifecycle.account, "rustfs_alive", lambda _port: True)
    monkeypatch.setattr(account_lifecycle.subprocess, "run", _recording_run(calls))
    account_lifecycle.start_rustfs()
    capsys.readouterr()
    ((argv, _body, env),) = [c for c in calls if c[0][:2] == ["docker", "run"]]
    assert "rustfs-secret" not in " ".join(argv), argv
    assert "rustfs-key-id" not in " ".join(argv), argv
    assert argv[argv.index("AWS_ACCESS_KEY_ID") - 1] == "-e"
    assert argv[argv.index("AWS_SECRET_ACCESS_KEY") - 1] == "-e"
    assert env is not None
    assert env["AWS_ACCESS_KEY_ID"] == "rustfs-key-id"
    assert env["AWS_SECRET_ACCESS_KEY"] == "rustfs-secret"


def test_start_rustfs_makes_its_own_log_directory(monkeypatch, tmp_path, capsys) -> None:
    """start_backup_plane calls start_rustfs on a fresh CI checkout, where no .account-logs exists yet (run 39658436875 died on FileNotFoundError); it must not rely on _serve having made it."""
    logs = tmp_path / "fresh-checkout" / ".account-logs"
    calls: list[tuple[list[str], object, dict | None]] = []
    alive = iter([False, True, True, True])
    monkeypatch.setattr(account_lifecycle.account, "log_directory", lambda *_a, **_k: str(logs))
    monkeypatch.setattr(account_lifecycle, "_docker_usable", lambda: True)
    monkeypatch.setattr(account_lifecycle, "docker_ghost_clean", lambda: None)
    monkeypatch.setattr(account_lifecycle.account, "rustfs_alive", lambda _port: next(alive, True))
    monkeypatch.setattr(account_lifecycle.subprocess, "run", _recording_run(calls))
    account_lifecycle.start_rustfs()
    capsys.readouterr()
    assert (logs / "rustfs.log").is_file()


@pytest.mark.xdist_group(LIFECYCLE_GROUP)
def test_delta_3a8d1f46_the_recording_still_carries_the_twins_argv() -> None:
    """The control on `_argv_delta_3a8d1f46`: the frozen twin transcripts still spell both shapes the twin's way, the port's spell them the new way, and the rewrite is what makes them meet. A golden re-recorded from the port would fail the first two assertions."""
    _, old_dev, _ = drive_lifecycle("old", "dev")
    _, new_dev, _ = drive_lifecycle("new", "dev")
    assert "-e AWS_SECRET_ACCESS_KEY=configadmin" in old_dev
    assert ' -d \\{\\"email\\"' in old_dev
    assert "-e AWS_SECRET_ACCESS_KEY=" not in new_dev
    assert " -d \\{" not in new_dev
    assert "application/json --data @-" in new_dev
    twin_line = next(line for line in old_dev.splitlines() if "ensure-login" in line)
    assert _argv_delta_3a8d1f46(twin_line) != twin_line


def test_delta_l6_a_failing_install_shows_more_than_its_last_line(tmp_path, capsys) -> None:
    """Defect L6, fixed: on a non-zero status the tailed log keeps up to thirty lines, where the twin's `tail -1` showed one line of an npm failure."""
    script = tmp_path / "noisy"
    script.write_text(
        "#!/bin/sh\nfor i in $(seq 1 50); do echo line$i; done\nexit 4\n", encoding="utf-8"
    )
    script.chmod(0o755)
    with pytest.raises(account_lifecycle.ErrexitError) as excinfo:
        account_lifecycle._tail([str(script)], 1, cwd=str(tmp_path))
    assert excinfo.value.code == 4
    out = capsys.readouterr().out
    assert "line50" in out
    assert "line21" in out
    assert "line20" not in out
    account_lifecycle._tail(["sh", "-c", "seq 1 9"], 2, cwd=str(tmp_path))
    assert capsys.readouterr().out == "8\n9\n", "a success keeps the tail length"


def test_delta_l7_pids_are_written_comma_separated() -> None:
    """Defect L7, fixed: `pids=` carries the commas the twin's `${A[*]// /,}` was written for and never produced. Both readers split on commas and whitespace, so old and new files both read back."""
    proc = subprocess.run(
        ["bash", "-c", 'A=(101 202 303); echo "${A[*]// /,}"'],
        capture_output=True,
        text=True,
        check=True,
    )
    assert proc.stdout == "101 202 303\n", "the twin's expansion moved"
    assert account_lifecycle.pids_line([101, 202, 303]) == "pids=101,202,303"
    assert account_lifecycle.pids_line([]) == "pids="
    assert account.state_pids("pids=101,202\n").replace(",", " ").split() == ["101", "202"]


@pytest.mark.xdist_group(SHADOW_PORTS_GROUP)
@pytest.mark.parametrize("scenario", sorted(DELTA_LINES))
def test_every_account_delta_line_still_diverges(scenario: str) -> None:
    """A delta that stopped diverging is a stale exclusion hiding a comparison, so each one must still differ between the sides."""
    _, old_out, _ = drive("old", scenario)
    _, new_out, _ = drive("new", scenario)
    for prefix in DELTA_LINES[scenario]:
        old = [line for line in old_out.splitlines() if line.startswith(prefix)]
        new = [line for line in new_out.splitlines() if line.startswith(prefix)]
        assert old != new, "the delta %r no longer diverges: remove it from DELTA_LINES" % prefix


@pytest.mark.xdist_group(LIFECYCLE_GROUP)
@pytest.mark.parametrize("scenario", sorted(LIFECYCLE_DELTA_CASES))
def test_every_lifecycle_delta_case_still_diverges(scenario: str) -> None:
    _, old_out, _ = drive_lifecycle("old", scenario)
    _, new_out, _ = drive_lifecycle("new", scenario)
    for name in LIFECYCLE_DELTA_CASES[scenario]:
        old = [line for line in old_out.splitlines() if line.startswith("obs %s " % name)]
        new = [line for line in new_out.splitlines() if line.startswith("obs %s " % name)]
        assert old, "the delta case %s never ran on the twin side" % name
        assert old != new, "the delta case %s no longer diverges: remove it from the set" % name


@pytest.mark.xdist_group(LIFECYCLE_GROUP)
def test_the_pids_normaliser_is_still_needed() -> None:
    """L7: both sides write a `state pids=` line, and they differ only in the separator."""
    _, old_out, _ = drive_lifecycle("old", "dev")
    _, new_out, _ = drive_lifecycle("new", "dev")
    assert "state pids=N N" in old_out
    assert "state pids=N,N" in new_out
    assert "state pids=N,N" not in old_out


def test_the_pinned_ports_sit_below_the_default_ephemeral_range():
    """A pinned port inside 32768-60999 can be held by any outbound connection's source port (45331, 2026-10-05)."""
    low, high = shadow_driver.PINNED_SPAN
    assert high < 32768, "the pinned ports %d..%d reach into Linux's default ephemeral range" % (
        low,
        high,
    )
    assert low > 30000, (
        "the pinned ports %d..%d overlap xdist_groups' worker slices (20000-30000)" % (low, high)
    )


def test_an_overlapping_ephemeral_range_is_a_refusal(tmp_path):
    overlapping = tmp_path / "range"
    overlapping.write_text("31000\t60999\n", encoding="utf-8")
    with pytest.raises(
        shadow_driver.RefusalError, match=r"overlap this kernel's ephemeral range 31000\.\.60999"
    ):
        shadow_driver.ports_outside_ephemeral(overlapping)
    clear = tmp_path / "clear"
    clear.write_text("32768\t60999\n", encoding="utf-8")
    shadow_driver.ports_outside_ephemeral(clear)
    shadow_driver.ports_outside_ephemeral(tmp_path / "absent")


class _LaunchedError(Exception):
    """Raised by the stand-in for `proc.exec_replace`, which never returns."""


def _launch_sqlite_web(monkeypatch, env):
    seen = {}

    def fake_exec(argv, *, env=None):
        seen["argv"], seen["env"] = list(argv), env
        raise _LaunchedError

    monkeypatch.setattr(account.proc, "exec_replace", fake_exec)
    plan = account.DbPlan(False, "/tmp/x.db", 8123, "/usr/bin/sqlite_web")
    with pytest.raises(_LaunchedError):
        account.db_launch(plan, env)
    return seen


def test_the_database_browser_binds_loopback_unless_the_dev_bind_says_otherwise(monkeypatch):
    """Review dee5310d.2: `db_launch` reads REDIACC_DEV_BIND and defaults to loopback instead of the wildcard address."""
    base = {"PATH": os.environ.get("PATH", "")}
    seen = _launch_sqlite_web(monkeypatch, dict(base))
    assert seen["argv"][seen["argv"].index("--host") + 1] == "127.0.0.1"
    seen = _launch_sqlite_web(monkeypatch, {**base, "REDIACC_DEV_BIND": "10.1.2.3"})
    assert seen["argv"][seen["argv"].index("--host") + 1] == "10.1.2.3"


def test_the_database_browser_child_gets_the_environment_its_bind_was_read_from(monkeypatch):
    """Review dee5310d.3: the bind came from the `env` argument while the exec ran under os.environ."""
    env = {"PATH": os.environ.get("PATH", ""), "REDIACC_DEV_BIND": "10.9.8.7"}
    seen = _launch_sqlite_web(monkeypatch, env)
    assert seen["env"] == env


def _e2e_tree(monkeypatch, tmp_path, *, state_extra: str):
    """A tmp console root with both lockfiles and a state file; every step before the lock check is stubbed."""
    web = tmp_path / "private" / "account" / "web"
    web.mkdir(parents=True)
    (web / "package-lock.json").write_text("web-lock-v2")
    (tmp_path / "private" / "account" / "package-lock.json").write_text("lock-v2")
    (tmp_path / ".account-state").write_text("gateway_port=4999\n" + state_extra)
    monkeypatch.setenv("CONSOLE_ROOT_DIR", str(tmp_path))
    monkeypatch.setenv("GATEWAY_PORT", "4999")
    monkeypatch.setattr(account.proc, "exec_replace", lambda *_a, **_k: None, raising=False)
    monkeypatch.setattr(account, "bws_exec", lambda *_a, **_k: None)
    monkeypatch.setattr(account_lifecycle, "_check_node", lambda: None)
    monkeypatch.setattr(account_lifecycle, "load_defaults", lambda: 0)
    monkeypatch.setattr(account_lifecycle.ports, "is_port_in_use", lambda _p: True)
    reached = []

    def next_step():
        reached.append(True)
        raise _LaunchedError

    monkeypatch.setattr(account_lifecycle.local_common, "ensure_packages_built", next_step)
    return reached


def _sha(text: str) -> str:
    return account_lifecycle.hashlib.sha256(text.encode()).hexdigest()


def test_e2e_refuses_when_a_recorded_lockfile_hash_moved(monkeypatch, tmp_path, capsys):
    reached = _e2e_tree(
        monkeypatch,
        tmp_path,
        state_extra="web_lock_sha=%s\nlock_sha=%s\n" % (_sha("web-lock-v1"), _sha("lock-v2")),
    )
    with pytest.raises(account_lifecycle.ErrexitError) as exc:
        account_lifecycle.test_e2e([])
    assert exc.value.code == 1
    assert not reached
    err = capsys.readouterr()
    text = err.out + err.err
    assert "web/package-lock.json" in text
    assert "./run.sh account stop && ./run.sh account dev" in text


def test_e2e_refuses_a_state_file_with_no_recorded_hash(monkeypatch, tmp_path, capsys):
    reached = _e2e_tree(monkeypatch, tmp_path, state_extra="")
    with pytest.raises(account_lifecycle.ErrexitError) as exc:
        account_lifecycle.test_e2e([])
    assert exc.value.code == 1
    assert not reached
    err = capsys.readouterr()
    assert "./run.sh account stop && ./run.sh account dev" in err.out + err.err


def test_e2e_proceeds_when_the_recorded_hashes_match(monkeypatch, tmp_path):
    reached = _e2e_tree(
        monkeypatch,
        tmp_path,
        state_extra="web_lock_sha=%s\nlock_sha=%s\n" % (_sha("web-lock-v2"), _sha("lock-v2")),
    )
    with pytest.raises(_LaunchedError):
        account_lifecycle.test_e2e([])
    assert reached


def test_e2e_proceeds_without_a_state_file(monkeypatch, tmp_path):
    """No state file: this checkout started no gateway (GATEWAY_PORT names another one), so there is nothing to compare and the run proceeds."""
    reached = _e2e_tree(monkeypatch, tmp_path, state_extra="")
    (tmp_path / ".account-state").unlink()
    with pytest.raises(_LaunchedError):
        account_lifecycle.test_e2e([])
    assert reached


def test_e2e_proceeds_when_the_state_names_another_port(monkeypatch, tmp_path):
    """The state file is this checkout's, but GATEWAY_PORT targets another gateway: its lockfile record says nothing about that one (review 6c9aee6a.1)."""
    reached = _e2e_tree(monkeypatch, tmp_path, state_extra="")
    (tmp_path / ".account-state").write_text("gateway_port=4888\n")
    with pytest.raises(_LaunchedError):
        account_lifecycle.test_e2e([])
    assert reached


def test_an_absent_lockfile_is_a_recorded_state(monkeypatch, tmp_path):
    """A lockfile absent at `dev()` is recorded as `absent`, and an e2e run with it still absent proceeds (review 6c9aee6a.2)."""
    reached = _e2e_tree(
        monkeypatch,
        tmp_path,
        state_extra="web_lock_sha=%s\nlock_sha=absent\n" % _sha("web-lock-v2"),
    )
    (tmp_path / "private" / "account" / "package-lock.json").unlink()
    with pytest.raises(_LaunchedError):
        account_lifecycle.test_e2e([])
    assert reached


def test_tree_refuses_pid_zero_and_one():
    """Review 4fb75de4.3: a recorded pid of 0 or 1 is never a job; os.kill(0, 0) would signal our own group."""
    assert account._tree("0") == []
    assert account._tree("1") == []
    assert account._tree("not-a-pid") == []


def test_stop_kills_a_sigterm_ignoring_child_whose_leader_exited(monkeypatch, tmp_path) -> None:
    """Reviews 4fb75de4.1 and a6ac20cd.3, end to end through stop(): the leader dies on SIGTERM, its child ignores SIGTERM and is reparented, and the SIGKILL pass must still reach it. Red if stop() re-collects the tree after the TERM pass, because by then the dead leader has no children."""
    monkeypatch.setenv("PATH", _fake_docker(tmp_path / "bin") + os.pathsep + os.environ["PATH"])
    work = shadow_driver.build_sandbox(paths.repo_root())
    leader = None
    try:
        env = shadow_driver.sandbox_env(work)
        state = pathlib.Path(account.state_file(env))
        childfile = tmp_path / "child.pid"
        ignorer = (
            "import os, signal, time; signal.signal(signal.SIGTERM, signal.SIG_IGN); "
            "open(%r, 'w').write(str(os.getpid())); time.sleep(30)" % str(childfile)
        )
        leader = _spawn_reaped(
            ["sh", "-c", "%s -c %s & wait" % (sys.executable, shlex.quote(ignorer))]
        )
        for _ in range(100):
            if childfile.is_file() and childfile.read_text().strip():
                break
            time.sleep(0.05)
        assert childfile.is_file(), "the SIGTERM-ignoring child never wrote its pid file"
        child = int(childfile.read_text().strip())
        assert _alive(child)
        state.write_text(
            "gateway_port=1\npids=%d\nwriter=%s\n" % (leader.pid, account.writer_stamp()),
            encoding="utf-8",
        )
        assert account.stop(env) == 0
        assert _gone(child), "the SIGTERM-ignoring child of the exited leader survived stop()"
    finally:
        if leader is not None:
            with contextlib.suppress(OSError):
                leader.kill()
        shutil.rmtree(work, ignore_errors=True)


def test_stop_with_a_foreign_state_kills_only_the_gateway_occupant(monkeypatch, tmp_path) -> None:
    """Review a6ac20cd.2: a state file another writer stamped gets the gateway occupant alone, never the trees on
    gateway+1 and gateway+2."""
    monkeypatch.setenv("PATH", _fake_docker(tmp_path / "bin") + os.pathsep + os.environ["PATH"])
    work = shadow_driver.build_sandbox(paths.repo_root())
    try:
        env = shadow_driver.sandbox_env(work)
        pathlib.Path(account.state_file(env)).write_text(
            "gateway_port=4900\npids=\nwriter=%s\n" % FOREIGN_WRITER, encoding="utf-8"
        )
        tree_kills: list[str] = []
        single_kills: list[str] = []
        monkeypatch.setattr(account, "_lsof_port_pids", lambda port: ["70%s" % port[-1]])
        monkeypatch.setattr(account, "_lsof_port_pid", lambda _port: "7000")
        monkeypatch.setattr(
            account, "_kill_tree", lambda pid, _sig, _members=None: tree_kills.append(pid)
        )
        monkeypatch.setattr(account, "_kill_quiet", lambda pid, _sig: single_kills.append(pid))
        assert account.stop(env) == 0
        assert tree_kills == [], (
            "a foreign state must not license whole-tree kills on the dev ports"
        )
        assert single_kills == ["7000"]
    finally:
        shutil.rmtree(work, ignore_errors=True)


def test_sigkill_pass_reaches_a_child_after_its_leader_exits():
    """Review 4fb75de4.1: with the members collected before SIGTERM, a SIGTERM-ignoring child is still in the SIGKILL
    pass. The stand-in leader is a child this test already reaped (review a6ac20cd.4: no hardcoded pid)."""
    gone = subprocess.Popen([sys.executable, "-c", "pass"])
    gone.wait(timeout=10)
    child = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "import signal, sys, time; signal.signal(signal.SIGTERM, signal.SIG_IGN); print('ready', flush=True); time.sleep(60)",
        ],
        stdout=subprocess.PIPE,
        text=True,
    )
    # Wait until the SIGTERM handler is installed, or the signal can land first and end the child early.
    assert child.stdout is not None
    assert child.stdout.readline().strip() == "ready"
    try:
        members = [gone.pid, child.pid]
        account._kill_tree(str(gone.pid), account.signal.SIGTERM, members)
        time.sleep(0.3)
        assert child.poll() is None, "the child ignores SIGTERM, so it must still be alive here"
        account._kill_tree(str(gone.pid), account.signal.SIGKILL, members)
        child.wait(timeout=5)
        assert child.returncode is not None
    finally:
        with contextlib.suppress(OSError):
            child.kill()
        child.wait(timeout=5)
        child.stdout.close()


def test_still_same_drops_a_reused_pid():
    """Review a6ac20cd.1: a member whose start time changed since collection was reused and is not signalled."""
    me = os.getpid()
    assert account._still_same([me], {me: account._start_time(me)}) == [me]
    assert account._still_same([me], {me: "not-the-real-start-time"}) == []


def test_kill_tree_with_members_never_signals_a_dropped_leader():
    """Review 4cb0f2b2.1: when the leader pid was reused and _still_same dropped it, _kill_tree(pid, sig, survivors)
    signals the survivors only; the process now holding the leader pid is left alone."""
    bystander = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    survivor = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        account._kill_tree(str(bystander.pid), account.signal.SIGKILL, [survivor.pid])
        survivor.wait(timeout=5)
        time.sleep(0.2)
        assert bystander.poll() is None, "the reused leader pid was signalled"
    finally:
        for proc in (bystander, survivor):
            with contextlib.suppress(OSError):
                proc.kill()
            proc.wait(timeout=5)


def test_stop_does_not_sigkill_a_member_whose_pid_was_reused(monkeypatch, tmp_path) -> None:
    """Review 4cb0f2b2.2, end to end through stop(): a recorded process that survives SIGTERM but whose start time
    changes before the SIGKILL pass (its pid was reused) is not killed. Red if stop() passes the unfiltered tree."""
    monkeypatch.setenv("PATH", _fake_docker(tmp_path / "bin") + os.pathsep + os.environ["PATH"])
    work = shadow_driver.build_sandbox(paths.repo_root())
    proc = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "import signal, time; signal.signal(signal.SIGTERM, signal.SIG_IGN); print('ready', flush=True); time.sleep(30)",
        ],
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        assert proc.stdout is not None
        assert proc.stdout.readline().strip() == "ready"
        calls: dict[int, int] = {}

        def changing_start_time(pid: int) -> str:
            calls[pid] = calls.get(pid, 0) + 1
            return "first" if calls[pid] == 1 else "reused"

        monkeypatch.setattr(account, "_start_time", changing_start_time)
        monkeypatch.setattr(account, "_tree", lambda pid: [int(pid)])
        env = shadow_driver.sandbox_env(work)
        pathlib.Path(account.state_file(env)).write_text(
            "gateway_port=1\npids=%d\nwriter=%s\n" % (proc.pid, account.writer_stamp()),
            encoding="utf-8",
        )
        assert account.stop(env) == 0
        assert proc.poll() is None, (
            "stop() SIGKILLed a member whose start time changed (a reused pid)"
        )
    finally:
        with contextlib.suppress(OSError):
            proc.kill()
        proc.wait(timeout=5)
        if proc.stdout is not None:
            proc.stdout.close()
        shutil.rmtree(work, ignore_errors=True)
