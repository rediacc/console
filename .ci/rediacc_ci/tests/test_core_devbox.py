"""`rediacc_ci.core.devbox` against the live `.ci/lib/devbox.sh`: all forty-two functions.

THE TWIN IS STILL HERE AND IS STILL SOURCED. `.ci/legacy/run-legacy.sh:456`, `.ci/rediacc_ci/setup/bridge.py:35`, `.ci/rediacc_ci/setup/shadow_driver.py:136`, `.ci/rediacc_ci/dev/shadow_driver.py:140` and `.ci/lib/account.sh:1090` all still source it, nothing is cut over, and this file drives the bash for real on every run: `rediacc_ci.core.devbox_shadow_driver` sources `devbox.sh` through the same prelude `bridge.py` uses and calls the twin's own functions, then does the same work through the port, and the two transcripts are compared byte for byte.

WHAT IS COVERED is decided by the driver's twenty-three scenarios and stated in its module docstring rather than restated here. Seven are the first slice's pure-function scenarios; sixteen are the STUB-FARM scenarios, in which `docker`, `sudo`, `curl`, `sleep`, `getent`, `stat` and `ss` are stubs that record every call and answer from a scripted table, so a side-effecting function is compared on the calls it MADE as well as on what it printed.

THE ANTI-VACUITY CLAIMS, because a differential that compared two empty transcripts would pass forever: every scenario must clear a floor of observations; every one of the forty-two functions must be the subject of at least one step; the stub farm must really shadow the host's `docker`; and `test_a_planted_defect_is_caught` plants real defects into the port IN PROCESS and requires the live bash transcript to disagree with each.
THE TWIN'S OWN DEFECTS are pinned against the LIVE TWIN's transcript, not against the port: `SCENARIO_CLAIMS` asserts each one inside the scenario's own comparison, so a twin that is later fixed fails here loudly rather than silently diverging from a port that still reproduces it.

NO XDIST GROUP. Each scenario's comparison and its claims are ONE test, so a scenario is driven once per worker that runs it; the driver's fixed work directory is serialised by its own `flock`, which is a lock the scheduler does not need to know about.
"""

import ast
import contextlib
import io
import json
import os
import pathlib
import pty
import re
import shutil
import subprocess
import sys

import pytest

from rediacc_ci import paths
from rediacc_ci.core import devbox
from rediacc_ci.core import devbox_shadow_driver as driver
from rediacc_ci.tests.gates import test_gate_devbox_slug as slug_gate

TWIN = ".ci/lib/devbox.sh"
PORT = ".ci/rediacc_ci/core/devbox.py"
DRIVER = ".ci/rediacc_ci/core/devbox_shadow_driver.py"
# Invoked as a MODULE, never by path: see the driver's header for why the by-path form would need a hand-written sys.path hop that `test_canonical_sys_path_hop.py` refuses.
DRIVER_MODULE = "rediacc_ci.core.devbox_shadow_driver"
LEDGER = ".ci/shadow/w7p5b-devbox.observations.jsonl"
CONSTANTS = ".ci/config/constants.sh"

SCENARIOS = driver.SCENARIOS

# The floor each scenario must clear. Measured against the recorded ledger rows, then rounded DOWN so a corpus gaining an entry does not turn into a test edit; the point is to catch a transcript collapsing to nothing, not to pin a count.
OBSERVATION_FLOOR = {
    "arity": 15,
    "drift": 60,
    "route-label": 200,
    "slug-basic": 45,
    "slug-edge": 30,
    "slug-fuzz": 240,
    "slug-utf8": 45,
    "identity": 75,
    "identity-worktree": 18,
    "identity-detached": 60,
    "identity-utf8": 45,
    "identity-gone": 30,
    "state": 160,
    "docker-query": 150,
    "proxy": 180,
    "image": 90,
    "lifecycle": 100,
    "exec": 240,
    "exec-quote": 135,
    "exec-quote-utf8": 135,
    "status": 250,
    "up-existing": 480,
    "up-create": 950,
}

# The scenarios cheap enough to drive a second time in process. The rest are compared through the subprocess only.
CHEAP_STUB_SCENARIOS = ("identity-worktree", "identity-gone")

# A legal DNS label, which is what the slug has to be for traefik to route it at all. The same expression `test_gate_devbox_slug.py:40` applies.
HOSTNAME_RE = re.compile(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$")

# The five real `source` sites, each with the line that does it. A cut-over would delete one of these, and this differential would then be comparing a library nothing loads.
SOURCE_SITES = (
    (".ci/legacy/run-legacy.sh", 'source "$ROOT_DIR/.ci/lib/devbox.sh"'),
    (".ci/rediacc_ci/setup/bridge.py", 'source "$ROOT_DIR/.ci/lib/devbox.sh"'),
    (".ci/rediacc_ci/setup/shadow_driver.py", 'source "$ROOT_DIR/.ci/lib/devbox.sh"'),
    (".ci/rediacc_ci/dev/shadow_driver.py", 'source "$ROOT_DIR/.ci/lib/devbox.sh"'),
    (".ci/lib/account.sh", 'source "$CONSOLE_ROOT_DIR/.ci/lib/devbox.sh"'),
)

# The functions that are NOT ported. Empty, and asserted empty: the whole twin has a counterpart.
NOT_PORTED_FUNCTIONS: tuple[str, ...] = ()

_CACHE: dict[tuple[str, str], tuple[int, str, str]] = {}


def drive(side: str, scenario: str) -> tuple[int, str, str]:
    """One side of one scenario, run once per worker and remembered."""
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
            errors="surrogateescape",
            check=False,
            timeout=1800,
        )
        _CACHE[key] = (proc.returncode, proc.stdout, proc.stderr)
    return _CACHE[key]


def new_transcript(scenario: str) -> str:
    """The port side IN PROCESS, which is what makes a monkeypatched plant visible.

    The subprocess form cannot see a plant, because a `monkeypatch` lives in this interpreter and the driver runs in another. The two agree by construction: this calls the same entry the subprocess calls, and `test_the_in_process_transcript_is_the_subprocess_one` pins that.
    """
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        driver.run_side("new", scenario, paths.repo_root())
    return buffer.getvalue()


def observations(out: str) -> dict[str, list[str]]:
    """The transcript grouped by step label: `{label: [the rest of each line]}`."""
    grouped: dict[str, list[str]] = {}
    for line in out.splitlines():
        if not line.startswith("obs "):
            continue
        label, _, rest = line[4:].partition(" ")
        grouped.setdefault(label, []).append(rest)
    return grouped


def _rule(rule: dict | None) -> dict:
    """The picked rule, asserted present: a test that indexes None would fail with a TypeError that names nothing."""
    assert rule is not None
    return rule


def status_of(step: list[str]) -> int:
    m = re.match(r"rc=(\d+)", step[0])
    assert m is not None, step[0]
    return int(m.group(1))


def stdout_of(step: list[str]) -> bytes:
    return bytes.fromhex(step[0].split(" out=", 1)[1])


def calls_of(step: list[str]) -> list[list[str]]:
    return [json.loads(line[len("call| ") :]) for line in step if line.startswith("call| ")]


def errs_of(step: list[str]) -> list[str]:
    return [line[len("err| ") :] for line in step if line.startswith("err| ")]


# -- the twin's own defects, asserted against the LIVE TWIN's transcript -------


def claims_identity(obs: dict[str, list[str]]) -> None:
    # Twin defect 7 does NOT cross a command substitution: `devbox_url` survives a failing `docker ps`.
    assert status_of(obs["url-ps-fails"]) == 0
    assert stdout_of(obs["url-ps-fails"]) == b"http://feat-box-one.localhost:8090\n"
    # `devbox_docker` asks `docker version` again from every helper; the sudo arm carries through to every docker call after it.
    assert calls_of(obs["url-sudo"])[2][:2] == ["sudo", "docker"]


def claims_docker_query(obs: dict[str, list[str]]) -> None:
    # Twin defect 3: the unterminated `id4` is never inspected.
    assert not any("id4" in call for call in calls_of(obs["conflicts-nonl"]))
    assert any("id1" in call for call in calls_of(obs["conflicts-nonl"]))
    # Twin defect 7: a direct call dies with `docker ps`'s own status.
    assert status_of(obs["active-ps-fails"]) == 3
    assert status_of(obs["missing-ps-fails"]) == 2
    assert errs_of(obs["active-ps-fails"]) == []


def claims_lifecycle(obs: dict[str, list[str]]) -> None:
    assert status_of(obs["stop-ps-fails"]) == 2
    assert obs["remove-ok"][-1] == "file| absent", "devbox_remove must really delete the state file"
    assert obs["remove-rm-fails"][-1] != "file| absent", (
        "a failed docker rm must keep the state file"
    )


def claims_exec(obs: dict[str, list[str]]) -> None:
    # Twin defect 2: the identity probe PASSES when the devbox is not running, and never reaches docker exec.
    assert status_of(obs["identity-not-running"]) == 0
    assert not any(call[1:2] == ["exec"] for call in calls_of(obs["identity-not-running"]))
    # Twin defect 5: zero arguments run `bash -lc "'' "`.
    assert calls_of(obs["zero"])[-1][-1] == "'' "
    # bash's own TERM default: `-e TERM` is forwarded with no TERM in the environment, and not once TERM is empty.
    assert "TERM" in calls_of(obs["one"])[-1]
    assert "TERM" not in calls_of(obs["env-cleared"])[-1]


def claims_status(obs: dict[str, list[str]]) -> None:
    # Twin defect 4: `echo -e` expands a TAB, spells an unencodable code point `ü`, and `\c` swallows the newline so the next log line is glued on.
    lines = errs_of(obs["conflict"])
    assert any("/other/x\ty\\u00FCz" in line for line in lines)
    assert any(line.startswith("✓   /cut✓ Which container") for line in lines)
    # Twin defect 8: the label inspect failing after the running check kills the status command before the route table.
    assert status_of(obs["hosts-fail"]) == 1
    assert stdout_of(obs["hosts-fail"]) == b""


def claims_up_existing(obs: dict[str, list[str]]) -> None:
    # Twin defect 9: a failed `docker start` ends devbox_up with docker's status and docker's words alone.
    assert status_of(obs["start-fails"]) == 1
    assert errs_of(obs["start-fails"]) == [
        "→ Starting existing devbox container",
        "Error: cannot start",
    ]
    assert status_of(obs["stopped-stays-down"]) == 1
    # A rehost really goes all the way through a create.
    assert any(call[1:2] == ["run"] for call in calls_of(obs["drift-rehost"]))


def claims_up_create(obs: dict[str, list[str]]) -> None:
    # Twin defect 1: no docker group is a SILENT death with getent's status, straight after the proxy check.
    assert status_of(obs["no-group"]) == 2
    assert calls_of(obs["no-group"])[-1] == ["getent", "group", "docker"]
    assert not any("docker run" in line for line in errs_of(obs["no-group"]))
    # Twin defect 6: `017000` is octal 7680.
    run = next(
        call
        for call in calls_of(obs["octal"])
        if call[1:4] == ["run", "-d", "--name"] and call[4] != "rediacc-devbox-proxy"
    )
    assert "DEVBOX_PORT=7680" in run
    assert "DEVBOX_TERM_PORT=7685" in run
    # The 60-round timeout really ran sixty rounds.
    assert sum(call[0] == "sleep" for call in calls_of(obs["timeout"])) == 60


def claims_state(obs: dict[str, list[str]]) -> None:
    # Twin defect 11: the key is a regular expression.
    assert stdout_of(obs["get-dot"]) == b"17010\n"
    assert stdout_of(obs["get-star"]) == b"feat-box-one\n"
    assert stdout_of(obs["get-last"]) == b"no-newline"
    assert errs_of(obs["write-3"]) == ["$4: unbound variable"]


def claims_proxy(obs: dict[str, list[str]]) -> None:
    assert sum(call[0] == "curl" for call in calls_of(obs["ensure-timeout"])) == 30
    assert status_of(obs["ensure-sleep-fails"]) == 1


SCENARIO_CLAIMS = {
    "identity": claims_identity,
    "docker-query": claims_docker_query,
    "lifecycle": claims_lifecycle,
    "exec": claims_exec,
    "status": claims_status,
    "up-existing": claims_up_existing,
    "up-create": claims_up_create,
    "state": claims_state,
    "proxy": claims_proxy,
}


# -- the differential itself -------------------------------------------------


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_the_port_matches_the_live_twin(scenario: str) -> None:
    """The whole claim of this file, once per scenario, with the scenario's floor and its twin claims."""
    old_rc, old_out, old_err = drive("old", scenario)
    new_rc, new_out, new_err = drive("new", scenario)
    assert old_rc == 0, "the bash side could not run: %s" % old_err
    assert new_rc == 0, "the port side could not run: %s" % new_err
    lines = [line for line in old_out.splitlines() if line.startswith("obs ")]
    # ANTI-VACUITY: a transcript that collapsed to nothing would compare equal. This is not hypothetical: a corpus entry holding an unencodable surrogate once made BOTH sides die in the fixture builder, and a first comparison script called that a match.
    assert len(lines) >= OBSERVATION_FLOOR[scenario], (
        "scenario %s produced %d observation(s), under its floor of %d"
        % (scenario, len(lines), OBSERVATION_FLOOR[scenario])
    )
    if scenario in SCENARIO_CLAIMS:
        SCENARIO_CLAIMS[scenario](observations(old_out))
    assert old_out == new_out, "scenario %s diverged" % scenario


def test_the_basename_fallback_depends_on_the_locale() -> None:
    """Twin defect 10, against the live twin: one checkout, two hostnames, decided by the caller's locale."""
    c_locale = observations(drive("old", "identity-detached")[1])
    utf8 = observations(drive("old", "identity-utf8")[1])
    assert stdout_of(c_locale["basename"]) == b"my-box----9\n"
    assert stdout_of(utf8["basename"]) == b"my-box---9\n"
    assert driver.STUB_SCENARIOS["identity-utf8"][1] == "C.utf8"


def test_the_corpus_is_not_empty() -> None:
    assert len(SCENARIOS) == 23, "the scenario set moved to %d" % len(SCENARIOS)
    assert set(SCENARIOS) == set(OBSERVATION_FLOOR), sorted(set(SCENARIOS) ^ set(OBSERVATION_FLOOR))
    assert len(driver.fuzz_corpus()) == driver.FUZZ_COUNT
    assert len(set(driver.fuzz_corpus())) > driver.FUZZ_COUNT / 2
    assert driver.fuzz_corpus() == driver.fuzz_corpus()


def stub_functions() -> set[str]:
    return {step.fn for _, _, steps in driver.STUB_SCENARIOS.values() for step in steps()}


def test_every_function_is_driven_by_some_scenario() -> None:
    """Every one of the forty-two is the subject of a step, so none of them is licensed by a ledger that never called it."""
    driven = stub_functions() | {"devbox_slugify", "devbox_slug_drift", "devbox_route_label"}
    assert driven == set(devbox.BASH_NAMES), sorted(set(devbox.BASH_NAMES) ^ driven)


@pytest.mark.parametrize("scenario", [*sorted(driver.BASH_SCENARIOS), *CHEAP_STUB_SCENARIOS])
def test_the_in_process_transcript_is_the_subprocess_one(scenario: str) -> None:
    """The bridge `test_a_planted_defect_is_caught` stands on, checked rather than assumed."""
    _, subprocess_out, _ = drive("new", scenario)
    assert new_transcript(scenario) == subprocess_out


# The plants, each a defect a reasonable port could really have. (label, attribute path, the scenario that must catch it).
PLANTS = (
    ("the 40-cap became a 41-cap", "SLUG_MAX", "slug-edge"),
    ("the empty answer lost its newline", "slugify_stdout", "arity"),
    ("the dash collapse is gone", "sanitise_line", "slug-basic"),
    ("a 404 is live again, whatever the caller said", "route_label", "route-label"),
    ("the state-file drift line is gone", "slug_drift", "drift"),
    ("mount_root ignores the git common dir", "Devbox.mount_root", "identity-worktree"),
    (
        "a gone worktree no longer falls back to its literal path",
        "Devbox.worktree_path",
        "identity-gone",
    ),
    (
        "build_image looks under the worktree instead of the mount root",
        "Devbox.build_image",
        "identity-worktree",
    ),
)


def planted_value(attribute: str):
    """The replacement for one plant, built here so the plants table stays readable."""
    if attribute == "SLUG_MAX":
        return 41
    if attribute == "slugify_stdout":
        return lambda value=None: devbox.slugify(value) + "\n" if devbox.slugify(value) else ""
    if attribute == "sanitise_line":
        return lambda line: "".join(
            chr(byte) if byte in devbox.SLUG_KEEP else "-" for byte in line
        ).strip("-")
    if attribute == "route_label":
        return lambda code=None, _hint="", _routed=devbox.ROUTED_UNKNOWN: devbox.Outcome(
            devbox.ROUTE_LIVE % code + "\n", 0
        )
    if attribute == "slug_drift":
        return lambda want=None, baked="", _recorded="": devbox.Outcome(
            devbox.DRIFT_CONTAINER % (baked, want) if baked and want and baked != want else "", 0
        )
    if attribute == "Devbox.mount_root":

        def mount_root(self, *_argv):
            self.write(self.worktree_path() + "\n")
            return 0

        return mount_root
    if attribute == "Devbox.worktree_path":
        original = devbox.Devbox.worktree_path

        def worktree_path(self):
            return original(self) if os.path.isdir(self.console_root) else ""

        return worktree_path
    if attribute == "Devbox.build_image":

        def build_image(self, *_argv):
            self.docker_words()
            self.log("error", "No Dockerfile at %s/.devcontainer" % self.worktree_path())
            return 1

        return build_image
    raise AssertionError("no planted value for %s" % attribute)


@pytest.mark.parametrize(("label", "attribute", "scenario"), PLANTS)
def test_a_planted_defect_is_caught(label: str, attribute: str, scenario: str, monkeypatch) -> None:
    """THE CONTROL ON THE COMPARISON: each plant must make the live twin disagree.

    Planted in process rather than on disk, so nothing can leave a defect behind in the tree. `monkeypatch` restores the attribute when the case ends.
    """
    _, twin_out, _ = drive("old", scenario)
    assert new_transcript(scenario) == twin_out, "the port already disagrees before the plant"
    owner, _, name = attribute.rpartition(".")
    target = devbox.Devbox if owner == "Devbox" else devbox
    monkeypatch.setattr(target, name, planted_value(attribute))
    assert new_transcript(scenario) != twin_out, (
        "PLANT DID NOT FIRE: %s changed no observation in %s" % (label, scenario)
    )


def test_the_transcripts_carry_what_a_divergence_would_move() -> None:
    """A CONTROL ON THE TRANSCRIPT, in the places a mutation can hide."""
    _, arity_out, _ = drive("old", "arity")
    assert arity_out != arity_out.replace("rc=1", "rc=0")
    assert "$1: unbound variable" in arity_out
    _, slug_out, _ = drive("old", "slug-basic")
    hexes = re.findall(r"out=([0-9a-f]+)", slug_out)
    assert len(hexes) >= 40
    assert len(set(hexes)) > 1, "every slug answer is the same, so a constant would pass"
    _, gone_out, _ = drive("old", "identity-gone")
    assert ' call| ["docker", "version"]' in gone_out, (
        "the stub transcript is missing, so a port that skipped a call would pass"
    )
    assert " file| " in gone_out, (
        "the state file is not observed, so a port that wrote the wrong bytes would pass"
    )


def test_the_locale_scenario_answers_exactly_what_the_c_locale_does() -> None:
    """The twin forces `LC_ALL=C` on each stage of `devbox_slugify`, so running the SHELL under a multibyte locale must change nothing."""
    _, c_locale, _ = drive("old", "slug-basic")
    _, utf8_locale, _ = drive("old", "slug-utf8")
    assert c_locale == utf8_locale
    assert driver.SCENARIO_LOCALE["slug-utf8"] == "C.utf8"


# -- the stub farm is real, and shadows what it claims to ----------------------


def test_the_stub_farm_really_shadows_docker(tmp_path: pathlib.Path) -> None:
    """No scenario may reach the host's docker. Resolved through the SAME PATH string both sides are given, `docker` must be the stub, and calling it must land on the transcript."""
    bin_dir = driver.build_stub_farm(tmp_path, paths.repo_root())
    search = str(bin_dir) + ":" + os.environ.get("PATH", "")
    for name in driver.STUBBED:
        assert shutil.which(name, path=search) == str(bin_dir / name), "%s is not shadowed" % name
    proc = subprocess.run(
        ["docker", "run", "--rm", "never-pulled"],
        env={**os.environ, "PATH": search},
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0
    assert proc.stdout == ""
    assert json.loads((tmp_path / "stub" / "transcript.jsonl").read_text()) == [
        "docker",
        "run",
        "--rm",
        "never-pulled",
    ]
    # And bash resolves it the same way once the prelude has put the farm first.
    resolved = subprocess.run(
        ["bash", "-c", 'export PATH="$FAKEBIN:$PATH"; type -P docker'],
        env={**os.environ, "FAKEBIN": str(bin_dir)},
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    assert resolved == str(bin_dir / "docker")
    real = shutil.which("docker")
    if real is not None:
        assert real != resolved, "the stub and the host's docker are the same file"


def test_the_stub_answers_by_pattern_ordinal_and_history() -> None:
    """`pick_rule`'s four conditions, each in both directions."""
    table = [
        driver.rule("curl", rc=7, nth=1),
        driver.rule("docker", "ps", out="after\n", after=("docker", "run")),
        driver.rule("docker", "ps", out="before\n", before=("docker", "run")),
        driver.rule("docker", "inspect", "x", exact=True, rc=3),
    ]
    assert _rule(driver.pick_rule(table, ["curl"], []))["rc"] == 7
    assert driver.pick_rule(table, ["curl"], [["curl"]]) is None
    assert _rule(driver.pick_rule(table, ["docker", "ps"], []))["out"] == "before\n"
    assert (
        _rule(driver.pick_rule(table, ["docker", "ps"], [["docker", "run", "-d"]]))["out"]
        == "after\n"
    )
    assert _rule(driver.pick_rule(table, ["docker", "inspect", "x"], []))["rc"] == 3
    assert driver.pick_rule(table, ["docker", "inspect", "x", "y"], []) is None


# -- the twin is still there, and still says what this file claims it says ----


def twin_text() -> str:
    return (paths.repo_root() / TWIN).read_text(encoding="utf-8")


def test_the_twin_defines_these_forty_two_and_nothing_else() -> None:
    """Measured rather than remembered: a function added to the twin later cannot slip past unported."""
    text = twin_text()
    defined = set(re.findall(r"^([a-z_]+)\(\) *\{", text, re.MULTILINE))
    assert len(devbox.BASH_NAMES) == 42
    assert defined == set(devbox.BASH_NAMES), sorted(defined ^ set(devbox.BASH_NAMES))


def test_every_twin_function_has_a_counterpart_and_none_is_unported() -> None:
    assert NOT_PORTED_FUNCTIONS == ()
    for name, attribute in devbox.BASH_NAMES.items():
        assert callable(getattr(devbox.Devbox, attribute, None)), "%s has no Devbox.%s" % (
            name,
            attribute,
        )
        expected = name.removeprefix("_devbox_").removeprefix("devbox_")
        assert attribute == expected, "%s is ported as %s, not by its stem" % (name, attribute)
    for pure in ("slugify", "slug_drift", "route_label"):
        assert callable(getattr(devbox, pure))


def test_the_twin_is_still_sourced_and_nothing_is_cut_over() -> None:
    root = paths.repo_root()
    for relative, needle in SOURCE_SITES:
        assert needle in (root / relative).read_text(encoding="utf-8"), relative


def test_the_constants_match_constants_sh() -> None:
    """The port COPIES `.ci/config/constants.sh`'s DEVBOX_* values; this reads the file and fails on any drift."""
    text = (paths.repo_root() / CONSTANTS).read_text(encoding="utf-8")
    declared = dict(re.findall(r'^readonly (DEVBOX_[A-Z_]+)="?([^"\s]*)"?', text, re.MULTILINE))
    assert len(declared) >= 12, "constants.sh declares only %d DEVBOX_ value(s)" % len(declared)
    for name, value in declared.items():
        if name == "DEVBOX_STATE_FILE":
            assert value == "$CONSOLE_ROOT_DIR/" + devbox.DEVBOX_STATE_NAME
            continue
        assert str(getattr(devbox, name)) == value, "%s is %r in constants.sh" % (name, value)


def test_the_pure_three_reach_nothing_but_their_arguments() -> None:
    """The first slice's purity claim, kept for the three that ARE pure, with the side-effecting class as the other-direction control."""
    tree = ast.parse((paths.repo_root() / PORT).read_text(encoding="utf-8"))
    pure = {
        "slugify",
        "slugify_stdout",
        "sanitise_line",
        "trim_dashes",
        "lower_ascii",
        "slug_drift",
        "route_label",
    }
    functions = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
    assert pure <= set(functions)
    for name in pure:
        names = {node.id for node in ast.walk(functions[name]) if isinstance(node, ast.Name)}
        assert not names & {"os", "subprocess", "open", "sys"}, "%s reaches %s" % (
            name,
            names & {"os", "subprocess", "open", "sys"},
        )
    devbox_class = next(
        node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "Devbox"
    )
    reached = {node.id for node in ast.walk(devbox_class) if isinstance(node, ast.Name)}
    assert {"subprocess", "os"} <= reached, (
        "the walk found nothing in a class that does run subprocesses"
    )


# -- the shell text rules, against the live bash rather than a table ----------


def bash_outputs(script: str, words: list[str], locale: str = "C") -> list[bytes]:
    """Run `script` once per word (as "$1") in ONE bash, NUL-separated answers."""
    payload = b"".join(word.encode("utf-8", "surrogateescape") + b"\0" for word in words)
    proc = subprocess.run(
        ["bash", "-c", 'while IFS= read -r -d "" w; do %s; printf "\\0"; done' % script],
        input=payload,
        env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LC_ALL": locale},
        capture_output=True,
        check=True,
    )
    return proc.stdout.split(b"\0")[:-1]


QUOTE_WORDS = [chr(code) for code in range(1, 128)] + [
    "",
    "a b",
    "~x",
    "x~",
    "a:~b",
    "a=~b",
    "#x",
    "x#",
    "é",
    "日本",
    "a\udcffb",
    "tab\there",
    "it's",
]


@pytest.mark.parametrize("locale", ["C", "C.utf8"])
def test_shell_quote_is_bash_printf_q(locale: str) -> None:
    answers = bash_outputs('printf "%q" "$w"', QUOTE_WORDS, locale)
    utf8 = locale != "C"
    for word, answer in zip(QUOTE_WORDS, answers, strict=True):
        assert devbox.shell_quote(word, utf8).encode("utf-8", "surrogateescape") == answer, repr(
            word
        )


ECHO_WORDS = [
    "plain",
    "a\\tb",
    "\\0101",
    "\\101",
    "\\x41\\x4g\\x",
    "\\u41\\u00fc\\u\\U0001F389\\uD800",
    "\\cgone",
    "\\q\\\\\\e\\E",
    "\\0777",
    "trailing\\",
]


@pytest.mark.parametrize("locale", ["C", "C.utf8"])
def test_echo_e_is_bash_echo_e(locale: str) -> None:
    answers = bash_outputs('echo -e "$w"', ECHO_WORDS, locale)
    for word, answer in zip(ECHO_WORDS, answers, strict=True):
        body, newline = devbox.echo_e(word, locale != "C")
        assert body + (b"\n" if newline else b"") == answer, repr(word)


def test_bash_int_reads_octal_and_hex_as_shell_arithmetic_does() -> None:
    assert devbox.bash_int("017000") == 7680
    assert devbox.bash_int("0x10") == 16
    assert devbox.bash_int(" 17010 ") == 17010
    assert devbox.bash_int("0") == 0
    with pytest.raises(devbox.DevboxError):
        devbox.bash_int("08")
    with pytest.raises(devbox.DevboxError):
        devbox.bash_int("base_port")


def test_the_state_key_refusal_is_explicit() -> None:
    """Twin defect 11's boundary: a key sed would parse differently is REFUSED, not guessed."""
    for key in ("a/b", "a\\b", "a\nb", "[[:alpha:]]"):
        with pytest.raises(devbox.DevboxError):
            devbox.bre_prefix(key)
    assert devbox.bre_prefix("sl*ug").match(b"sllug=x")
    assert devbox.bre_prefix("*x").match(b"*x=1")


# -- the tty arms of devbox_exec, which the differential cannot reach ----------


class RecordingDevbox(devbox.Devbox):
    """`Devbox` with every external answered in process: a running container, and every argv recorded."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.calls: list[list[str]] = []

    def run(self, argv, out=devbox.INHERIT, err=devbox.INHERIT, extra_env=None):
        del err, extra_env  # the parent's redirections; this fake answers every command in process
        self.calls.append(list(argv))
        if argv[1:2] == ["ps"]:
            answer = "cid\n"
        elif argv[1:4] == ["inspect", "-f", "{{.State.Running}}"]:
            answer = "true\n"
        else:
            answer = ""
        if out == devbox.CAPTURE:
            return 0, answer
        self.write(answer)
        return 0, ""


@pytest.mark.parametrize(
    ("stdin_tty", "stdout_tty", "flags"),
    [(False, False, []), (True, False, ["-i"]), (True, True, ["-i", "-t"])],
)
def test_the_exec_tty_arms(stdin_tty: bool, stdout_tty: bool, flags: list[str]) -> None:
    master, slave = pty.openpty()
    try:
        with (
            os.fdopen(os.dup(slave), "rb") if stdin_tty else open(os.devnull, "rb") as stdin,
            os.fdopen(os.dup(slave), "wb") if stdout_tty else open(os.devnull, "wb") as stdout,
            open(os.devnull, "wb") as stderr,
        ):
            dev = RecordingDevbox(
                {"PATH": "/usr/bin:/bin", "HOME": "/nonexistent", "TERM": ""},
                stdin=stdin,
                stdout=stdout,
                stderr=stderr,
            )
            assert dev.invoke("devbox_exec", ["true"]) == 0
    finally:
        os.close(master)
        os.close(slave)
    execs = [call for call in dev.calls if call[1:2] == ["exec"]]
    assert len(execs) == 1
    between = execs[0][execs[0].index("-w") + 2 : execs[0].index("-e")]
    assert between == flags


# -- the licence, and the tools the scenarios really use ---------------------


def ledger_rows() -> list[dict]:
    path = paths.repo_root() / LEDGER
    assert path.is_file(), "%s is missing; the port has no recorded licence" % LEDGER
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def test_the_shadow_ledger_holds_equivalent_rows_over_five_trees() -> None:
    """The K=5 licence, read off disk rather than remembered from a session, covering EVERY scenario."""
    rows = ledger_rows()
    assert len(rows) >= 5
    assert all(row["verdict"] == "EQUIVALENT" for row in rows)
    assert len({row["tree"]["id"] for row in rows}) >= 5
    assert all(row["tree"]["clean"] for row in rows)
    assert all(TWIN in row["old"]["cmd"] for row in rows)
    assert all(PORT in row["new"]["cmd"] for row in rows)
    assert len({row["old"]["fingerprint"] for row in rows}) >= 2
    recorded = {row["new"]["cmd"].rsplit(" ", 1)[1] for row in rows}
    assert recorded == set(SCENARIOS), "the ledger covers %s" % sorted(recorded)


def test_every_row_carries_the_whole_file_comment_audit() -> None:
    """A WHOLE-FILE port is audited against the WHOLE twin, so every row carries the comment ratio and every ratio clears the floor.

    The first slice recorded without the two file arguments because three functions out of forty-two were measured against a whole file; that exemption ends with the port, and this case is what holds it ended.
    """
    for row in ledger_rows():
        comments = row.get("comments")
        assert comments is not None, "a row was recorded without --old-file/--new-file"
        assert comments["ratio"] >= 0.9, comments


def test_the_tools_the_scenarios_use_are_installed() -> None:
    for tool in ("bash", "sed", "tr", "od", "git"):
        assert shutil.which(tool) is not None, tool


def test_the_driver_refuses_when_the_twin_is_not_there() -> None:
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
            "arity",
        ],
        cwd=str(paths.repo_root()),
        env={**os.environ, "PYTHONPATH": ".ci"},
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == driver.EXIT_CANNOT_RUN
    assert "attests to nothing" in proc.stderr


def test_the_driver_scenarios_and_the_bash_bodies_line_up() -> None:
    for name, body in driver.BASH_SCENARIOS.items():
        assert "probe " in body, name
        assert "%(fn)s" not in body, name
    for name, (fixture, locale, steps) in driver.STUB_SCENARIOS.items():
        built = steps()
        assert built, name
        assert fixture in ("main", "worktree", "detached", "gone"), name
        assert locale in ("C", "C.utf8"), name
        assert "sprobe " in driver.stub_body(built), name


# -- the pure rules, exercised directly -------------------------------------------

# The nine rows `test_gate_devbox_slug.py:49-59` pins. Restated here rather than imported, and then CROSS-CHECKED against that file, so a change to either is a failure in both rather than a silent agreement.
SLUG_ROWS = (
    ("feat/x", "feat-x"),
    ("feat//x", "feat-x"),
    ("Feature/ABC-123", "feature-abc-123"),
    ("--lead-and-trail--", "lead-and-trail"),
    ("0826-2", "0826-2"),
    ("feat/über", "feat-ber"),
    ("", ""),
    ("///", ""),
    (driver.LONG_BRANCH, "feature-an-extremely-long-branch-name-th"),
)


@pytest.mark.parametrize(("value", "expected"), SLUG_ROWS)
def test_slugify_answers_the_pinned_rows(value: str, expected: str) -> None:
    answer = devbox.slugify(value)
    assert answer == expected
    assert len(answer) <= devbox.SLUG_MAX
    if answer:
        assert HOSTNAME_RE.match(answer)


def test_the_pinned_rows_agree_with_the_gate_that_also_pins_them() -> None:
    assert dict(SLUG_ROWS) == dict(slug_gate.SLUG_ROWS)
    assert driver.LONG_BRANCH == slug_gate.LONG


def test_the_cap_is_applied_before_the_final_trim() -> None:
    assert devbox.slugify("a" * 39 + "-bcd") == "a" * 39
    assert devbox.slugify("a" * 40 + "-bcd") == "a" * 40
    assert devbox.slugify("a" * 41) == "a" * 40


def test_the_empty_answer_is_still_a_line() -> None:
    assert devbox.slugify("///") == ""
    assert devbox.slugify_stdout("///") == "\n"
    assert devbox.slugify_stdout() == "\n"


def test_a_newline_in_the_argument_survives_because_sed_works_per_line() -> None:
    assert devbox.slugify("a\nb") == "a\nb"
    assert devbox.slugify("-a-\n-b-") == "a\nb"
    assert devbox.slugify("a\n") == "a"
    assert devbox.slugify("\na") == "\na"


def test_multibyte_collapses_to_one_dash_per_run() -> None:
    assert devbox.slugify("feat/über") == "feat-ber"
    assert devbox.slugify("a日b") == "a-b"
    assert devbox.slugify("a\U0001f389b") == "a-b"
    assert devbox.slugify("a\udcffb") == "a-b"


def test_lowering_is_ascii_only() -> None:
    assert devbox.slugify("MiXeD/CaSe") == "mixed-case"
    assert devbox.slugify("İstanbul") == "stanbul"
    assert devbox.lower_ascii(b"ABZ\xc3\x9f") == b"abz\xc3\x9f"


def test_the_basename_rule_is_not_slugify() -> None:
    """No collapse, no cap, and the locale decides the dash count (twin defect 10)."""
    assert devbox.slug_basename_rule("a..b", False) == "a--b\n"
    assert devbox.slug_basename_rule("x" * 50, False) == "x" * 50 + "\n"
    assert devbox.slug_basename_rule("aÜb", False) == "a--b\n"
    assert devbox.slug_basename_rule("aÜb", True) == "a-b\n"


def test_slug_drift_reports_the_two_disagreements_and_nothing_else() -> None:
    assert devbox.slug_drift("alpha", "alpha", "alpha").out == ""
    assert "container serves alpha" in devbox.slug_drift("beta", "alpha", "alpha").out
    assert len(devbox.slug_drift("beta", "alpha", "stale").out.splitlines()) == 2
    assert devbox.slug_drift("beta", "", "stale").out == ""


@pytest.mark.parametrize(
    ("code", "hint", "routed", "expected"),
    [
        ("000", "", "unknown", "proxy unreachable"),
        ("502", "run account dev", "unknown", "no backend yet -- run account dev"),
        ("404", "", "no", "no such router -- nothing serves this hostname"),
        ("404", "", "yes", "live (HTTP 404)"),
        ("404", "", "", "no matching route, or a backend 404 (HTTP 404)"),
        ("200", "", "unknown", "live (HTTP 200)"),
        ("404 ", "", "no", "live (HTTP 404 )"),
    ],
)
def test_route_label_never_lets_the_word_contradict_the_code(code, hint, routed, expected) -> None:
    assert devbox.route_label(code, hint, routed).out == expected + "\n"


def test_the_no_argument_call_is_a_death_and_not_a_default() -> None:
    for function in (devbox.slug_drift, devbox.route_label):
        with pytest.raises(devbox.DevboxError) as raised:
            function()
        assert raised.value.code == devbox.UNBOUND_STATUS
    assert devbox.slugify() == ""


def test_the_repo_root_is_a_checkout_with_the_twin_in_it() -> None:
    assert (paths.repo_root() / TWIN).is_file()
    assert (paths.repo_root() / PORT).is_file()
    assert pathlib.Path(DRIVER).name == "devbox_shadow_driver.py"
