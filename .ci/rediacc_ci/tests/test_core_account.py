"""`rediacc_ci.core.account` against the live `.ci/lib/account.sh`.

THE TWIN IS STILL HERE AND IS STILL THE ONLY IMPLEMENTATION OF ELEVEN OF ITS TWENTY-TWO FUNCTIONS.
`.ci/legacy/run-legacy.sh:405` and `:443` still source it, nothing is cut over, and this file drives the bash for real on every run: `rediacc_ci.core.shadow_driver` sources `account.sh` through the same prelude `run-legacy.sh` uses and calls the twin's own functions, then does the same work through the port, and the two transcripts are compared byte for byte.

WHAT IS COVERED AND WHAT IS NOT is decided by the driver's five scenarios and stated in its module docstring rather than restated here.
The short version: everything deterministic, and none of `account_dev`, `account_stop`, `account_test`, `account_test_e2e`, `account_reset`, `account_seed_demo`, `account_cleanup`, `account_docker_ghost_clean`, `account_stripe_auto`, `account_dev_credentials`, `account_rotation`, or `account_db`'s launch, all of which start or stop real infrastructure.

WHY `XDIST_GROUP` IS DECLARED. The driver pins FIXED port numbers on both sides, because the two sides run as two processes and an ephemeral port would differ between them and land in a message text.
Two workers running two scenarios at once would contend for those ports, which is the same host-port-space resource `test_core_ports.py` declares, so this joins the same group and is serialised against it.

THE ANTI-VACUITY CLAIMS, because a differential that compared two empty transcripts would pass forever: every scenario must produce a floor of observations, the tools the scenarios really use must be installed, and `test_the_differential_can_fail` mutates one side and demands a mismatch in each of the three places a mutation can hide.
"""

import json
import os
import pathlib
import shutil
import subprocess
import sys

import pytest

from rediacc_ci import paths
from rediacc_ci.core import account, shadow_driver

# The host port space, the same resource `test_core_ports.py` names. See the header.
XDIST_GROUP = "ports"

TWIN = ".ci/lib/account.sh"
PORT = ".ci/rediacc_ci/core/account.py"
DRIVER = ".ci/rediacc_ci/core/shadow_driver.py"
# Invoked as a MODULE, never by path: see the driver's header for why the by-path form would need a hand-written sys.path hop that `test_canonical_sys_path_hop.py` refuses.
DRIVER_MODULE = "rediacc_ci.core.shadow_driver"
LEDGER = ".ci/shadow/w7p5b-account.observations.jsonl"

SCENARIOS = sorted(shadow_driver.BASH_SCENARIOS)

# The floor each scenario must clear. Measured against the recorded ledger rows, then rounded DOWN so a real change to a message does not turn into a test edit; the point is to catch a transcript collapsing to nothing, not to pin a count.
OBSERVATION_FLOOR = {
    "db": 10,
    "env": 100,
    "fresh-env": 100,
    "probe": 12,
    "totp": 8,
}

_CACHE: dict[tuple[str, str], tuple[int, str, str]] = {}


def drive(side: str, scenario: str) -> tuple[int, str, str]:
    """One side of one scenario, run once per session and remembered.

    Cached because every case below wants the same transcript and each run of the bash side sources `constants.sh`, `toolchain.sh`, `local-common.sh` and `account.sh` before it does anything at all.
    """
    key = (side, scenario)
    if key not in _CACHE:
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                DRIVER_MODULE,
                "--side",
                side,
                "--twin",
                TWIN,
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
        _CACHE[key] = (proc.returncode, proc.stdout, proc.stderr)
    return _CACHE[key]


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_the_port_matches_the_live_twin(scenario: str) -> None:
    """The whole claim of this file, once per scenario."""
    old_rc, old_out, old_err = drive("old", scenario)
    new_rc, new_out, new_err = drive("new", scenario)
    assert old_rc == 0, "the bash side could not run: %s" % old_err
    assert new_rc == 0, "the port side could not run: %s" % new_err
    assert old_out == new_out, "scenario %s diverged" % scenario


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
    assert len(SCENARIOS) >= 5, "the scenario set collapsed to %d" % len(SCENARIOS)
    assert set(SCENARIOS) == set(OBSERVATION_FLOOR), (
        "a scenario was added or removed without a floor: %s"
        % sorted(set(SCENARIOS) ^ set(OBSERVATION_FLOOR))
    )


def test_the_differential_can_fail() -> None:
    """A CONTROL ON THE COMPARISON, in the three places a mutation can hide.

    Each line below is a transcript the port could plausibly produce and the twin does not, so a comparison that still called it equal would be looking at the wrong thing.
    """
    _, out, _ = drive("old", "probe")
    assert out != out.replace("obs rc rustfs-dead=1", "obs rc rustfs-dead=0"), (
        "the probe transcript carries no exit code, so a port that inverted one would pass"
    )
    padded = out.replace("..│..hello", ".│..hello")
    assert out != padded, "the probe transcript carries no banner padding"
    _, env_out, _ = drive("old", "env")
    assert env_out != env_out.replace("obs file after-adds| ", "obs file after-adds|"), (
        "the env transcript carries no file dump, so a rewritten .env would pass"
    )


# -- the twin is still there, and still says what this file claims it says ----


def twin_text() -> str:
    return (paths.repo_root() / TWIN).read_text(encoding="utf-8")


PORTED_FUNCTIONS = (
    "account_allocate_ports",
    "account_wait_port",
    "account_rustfs_alive",
    "account_generate_crypto_keys",
    "account_generate_fresh_env",
    "account_env_add_if_missing",
    "account_ensure_env_keys",
    "account_ensure_env",
    "account_banner_row",
    "account_totp",
    "account_db",
)

NOT_PORTED_FUNCTIONS = (
    "account_cleanup",
    "account_docker_ghost_clean",
    "account_stripe_auto",
    "account_dev",
    "account_dev_credentials",
    "account_stop",
    "account_test",
    "account_test_e2e",
    "account_reset",
    "account_seed_demo",
    "account_rotation",
)


def test_the_twin_still_defines_every_function_this_slice_names() -> None:
    """Twenty-two, split eleven and eleven, measured rather than remembered."""
    text = twin_text()
    for name in PORTED_FUNCTIONS + NOT_PORTED_FUNCTIONS:
        assert "\n%s() {" % name in text, "%s is gone from %s" % (name, TWIN)
    assert len(PORTED_FUNCTIONS) + len(NOT_PORTED_FUNCTIONS) == 22


def test_the_unported_half_has_no_python_counterpart() -> None:
    """The absence is the claim, so it is asserted rather than left to a reader.

    A future session porting `account_dev` must delete its name from `NOT_PORTED_FUNCTIONS` here, which is the moment to ask how a dev-server boot transcript gets compared.
    """
    for name in NOT_PORTED_FUNCTIONS:
        stem = name[len("account_") :]
        assert not hasattr(account, stem), (
            "%s appeared in the port without this file's list being updated; a ledger row "
            "is a claim of equivalence and nothing compares that function" % stem
        )


def test_the_twin_is_sourced_by_run_legacy_and_nothing_is_cut_over() -> None:
    """The sequencing claim in the port's docstring, checked against the dispatcher."""
    legacy = (paths.repo_root() / ".ci/legacy/run-legacy.sh").read_text(encoding="utf-8")
    assert legacy.count('source "$ROOT_DIR/.ci/lib/account.sh"') == 2, (
        "the account and rotation verbs no longer both source the twin; if this slice "
        "has been cut over, this differential needs a different subject"
    )


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


def test_banner_row_pads_by_bytes_not_characters() -> None:
    """Defect 2. A multibyte glyph really does shorten the visible field."""
    text = "héllo, ünicode"
    row = account.banner_row(text)
    assert len(text.encode("utf-8")) > len(text)
    assert len(row[len("  │  ") : -1].encode("utf-8")) == 63


def test_state_gateway_port_raises_where_the_twin_dies() -> None:
    """Defect 1: no match is not an empty answer, it is the end of the function."""
    assert account.state_gateway_port("gateway_port=4800\n") == "4800"
    assert account.state_gateway_port("gateway_port=\n") == ""
    with pytest.raises(account.StateAbortedError, match="matched nothing"):
        account.state_gateway_port("started=1\n")


def test_state_gateway_port_truncates_a_value_containing_an_equals_sign() -> None:
    """Defect 3. `cut -d= -f2` takes the second field only. Preserved, not fixed."""
    assert account.state_gateway_port("gateway_port=a=b\n") == "a"


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

    `.ci/lib/account.sh:754` parses the response with `node -e`, so the port's Python reimplementation is checked against that exact program rather than against a reading of it.
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


def test_env_add_if_missing_refuses_a_key_that_is_not_a_literal(tmp_path) -> None:
    """The one place the port refuses where the twin would quietly pattern-match."""
    target = tmp_path / ".env"
    target.write_text("ABC=1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="BRE metacharacter"):
        account.env_add_if_missing(str(target), "A.C", "2")
    # The control: an ordinary key still works in both directions.
    assert account.env_add_if_missing(str(target), "NEW", "2") is True
    assert account.env_add_if_missing(str(target), "NEW", "3") is False
    assert target.read_text(encoding="utf-8").count("NEW=") == 1


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
        script = (
            'W="%s"\nset -euo pipefail\n'
            'source "$W/.ci/config/constants.sh"\n'
            'source "$W/.ci/scripts/lib/toolchain.sh"\n'
            'source "$W/.ci/lib/local-common.sh"\n'
            'source "$W/.ci/lib/account.sh"\n'
            "set +e\n"
            "( set -e; account_rustfs_alive 45211 )\n"
            "exit $?\n" % root
        )
        env = {
            "PATH": str(farm),
            "HOME": os.environ.get("HOME", "/tmp"),
            "LC_ALL": "C",
            "CONSOLE_ROOT_DIR": str(root),
            "REDIACC_CI_ROOT": str(root),
        }
        twin = subprocess.run(
            ["bash", "-c", script], env=env, capture_output=True, text=True, check=False
        )
        assert twin.returncode == 1, "the twin did not reach the branch: %s" % twin.stderr
        port = subprocess.run(
            [
                sys.executable,
                "-c",
                "from rediacc_ci.core import account\nraise SystemExit(0 if account.rustfs_alive(45211) else 1)",
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
        assert port.returncode == twin.returncode
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


def test_version_tuple_orders_the_way_sort_v_does() -> None:
    assert account.version_tuple("22.14.0") > account.version_tuple("18.0.0")
    assert account.version_tuple("18.0.0") == account.version_tuple("18.0.0")
    assert account.version_tuple("9.0.0") < account.version_tuple("10.0.0")


def test_devbox_state_get_matches_the_bash_it_duplicates(tmp_path) -> None:
    """`devbox_state_get` is `.ci/lib/devbox.sh:124`, which this slice does not touch.

    The port re-implements it because a module cannot borrow from its importer, so the two are compared here on the shapes a real `.devbox-state` takes, INCLUDING a key that is absent and a file that is not there.
    """
    root = tmp_path / "root"
    root.mkdir()
    state = root / ".devbox-state"
    env = {"CONSOLE_ROOT_DIR": str(root)}
    twin = str(paths.repo_root() / ".ci/lib/devbox.sh")

    def bash(key: str) -> tuple[int, str]:
        script = 'source "%s"\ndevbox_state_get "%s"\n' % (twin, key)
        proc = subprocess.run(
            ["bash", "-c", script],
            env={"DEVBOX_STATE_FILE": str(state), "PATH": "/usr/bin:/bin"},
            capture_output=True,
            text=True,
            check=False,
        )
        return proc.returncode, proc.stdout

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
    """`.ci/lib/account.sh:1074-1097`, the arithmetic the `db` scenario proves end to end."""
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


def test_fresh_env_text_carries_every_key_the_ensure_path_also_writes() -> None:
    """The template and the incremental path must not drift apart.

    `account_ensure_env_keys` exists to add to an OLD `.env` what a fresh one already has. A key present in one and absent from the other is a machine that works on a fresh checkout and not on an upgraded one.
    """
    keys = account.CryptoKeys("p1", "p2", "p3", "p4", "jwt", "api")
    text = account.fresh_env_text(keys, "2026-01-01T00:00:00Z", "")
    for name in account.CRYPTO_KEYS:
        assert "\n%s=" % name in text
    for name in ("REDIACC_ACCOUNT_SERVER", "DATABASE_PATH", "PORT", "WEBAUTHN_RP_ID"):
        assert "\n%s=" % name in text
    # ROOT_EMAIL is quoted in the template and unquoted by the incremental path, because only a fresh generation ever writes it. Pinned, not corrected.
    assert '\nROOT_EMAIL=""\n' in text


# -- the licence, and the tools the scenarios really use ---------------------


def test_the_shadow_ledger_holds_five_equivalent_rows_over_five_trees() -> None:
    """The K=5 licence, read off disk rather than remembered from a session."""
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


def test_the_driver_refuses_when_the_twin_is_not_there() -> None:
    """The driver's own control, driven rather than read."""
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            DRIVER_MODULE,
            "--side",
            "old",
            "--twin",
            ".ci/lib/no-such-file.sh",
            "--port",
            PORT,
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


def test_the_paths_derive_from_console_root_and_nothing_else() -> None:
    """The one seam both implementations read, in both directions."""
    env = {"CONSOLE_ROOT_DIR": "/somewhere"}
    assert account.account_dir(env) == "/somewhere/private/account"
    assert account.env_path(env) == "/somewhere/private/account/.env"
    assert account.state_file(env) == "/somewhere/.account-state"
    assert account.log_directory(env) == "/somewhere/.account-logs"
    assert account.devbox_state_file(env) == "/somewhere/.devbox-state"
    # With nothing set it falls back to the repository root, not to the cwd.
    assert account.console_root({}) == str(paths.repo_root())


def test_the_ported_module_has_no_launch_on_its_argv_surface() -> None:
    """`main` offers the twin's two public verbs and refuses anything else."""
    assert account.main(["nosuch"]) == 2
    assert account.main([]) == 2
    assert account.main(["--help"]) == 0
    assert "totp" in account.USAGE
    assert "db" in account.USAGE
    for name in ("dev", "stop", "reset", "seed-demo"):
        assert account.main([name]) == 2, "%s must not be reachable from this port" % name


def test_the_driver_scenarios_and_the_bash_bodies_line_up() -> None:
    """Every scenario the driver offers has a bash body, which is what `old` runs."""
    assert isinstance(shadow_driver.BASH_SCENARIOS, dict)
    for name, body in shadow_driver.BASH_SCENARIOS.items():
        assert body.strip(), "scenario %s has an empty bash body" % name
        assert "step " in body or "banner " in body, "scenario %s calls nothing" % name


def test_the_repo_root_is_a_checkout_with_the_twin_in_it() -> None:
    """A last refusal: everything above is relative to this."""
    assert (paths.repo_root() / TWIN).is_file()
    assert (paths.repo_root() / PORT).is_file()
    assert pathlib.Path(DRIVER).name == "shadow_driver.py"
