"""`rediacc_ci.core.devbox` against the transcripts frozen from the retired `.ci/lib/devbox.sh` (`goldens/twins/lib.devbox.jsonl`): all fifty-five functions.

THE TWIN IS DELETED. The bash side of every scenario was driven by `rediacc_ci.core.devbox_shadow_driver` while `devbox.sh` existed and its full transcripts are the golden; this file compares the port's live transcript against them. A Rule-T change to the port is recorded with `regolden --source port`.

WHAT IS COVERED is decided by the driver's twenty-three scenarios and stated in its module docstring rather than restated here. Seven are the first slice's pure-function scenarios; sixteen are the STUB-FARM scenarios, in which `docker`, `sudo`, `curl`, `sleep`, `getent`, `stat` and `ss` are stubs that record every call and answer from a scripted table, so a side-effecting function is compared on the calls it MADE as well as on what it printed.

THE ANTI-VACUITY CLAIMS, because a differential that compared two empty transcripts would pass forever: every scenario must clear a floor of observations; every one of the fifty-five functions must be the subject of at least one step; the stub farm must really shadow the host's `docker`; and `test_a_planted_defect_is_caught` plants real defects into the port IN PROCESS and requires the live bash transcript to disagree with each.
THE TWIN'S OWN DEFECTS are pinned against the FROZEN TWIN's transcript, not against the port: `SCENARIO_CLAIMS` asserts each one inside the scenario's own comparison, so a twin that is later fixed fails here loudly rather than silently diverging from a port that still reproduces it.

NO XDIST GROUP. Each scenario's comparison and its claims are ONE test, and each side of a scenario is driven once per pytest RUN: `drive` keeps the transcript in the run's shared directory under a `flock`, so a worker that needs a side another worker already drove reads it instead of driving it again. The driver's fixed work directory is serialised by its own `flock`, which is a lock the scheduler does not need to know about.
"""

import ast
import contextlib
import fcntl
import functools
import hashlib
import io
import json
import os
import pathlib
import pty
import re
import shutil
import socket
import stat
import subprocess
import sys
import tempfile

import pytest

from rediacc_ci import paths
from rediacc_ci.core import devbox
from rediacc_ci.core import devbox_shadow_driver as driver
from rediacc_ci.setup import bridge
from rediacc_ci.tests import differential as diff

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
    "identity-utf8": 38,
    "identity-gone": 30,
    "state": 160,
    "docker-query": 150,
    "proxy": 180,
    "image": 90,
    "lifecycle": 100,
    "exec": 240,
    "exec-quote": 135,
    "exec-quote-utf8": 135,
    "status": 170,
    "up-existing": 380,
    "up-create": 760,
    "ready": 170,
}

# The scenarios cheap enough to drive a second time in process. The rest are compared through the subprocess only.
CHEAP_STUB_SCENARIOS = ("identity-worktree", "identity-gone")

# A legal DNS label, which is what the slug has to be for traefik to route it at all. The same expression `test_gate_devbox_slug.py:40` applies.
HOSTNAME_RE = re.compile(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$")

# The functions that are NOT ported. Empty, and asserted empty: the whole twin has a counterpart.
NOT_PORTED_FUNCTIONS: tuple[str, ...] = ()

_CACHE: dict[tuple[str, str], tuple[int, str, str]] = {}
# The run's directory every xdist worker shares (`<basetemp>/..`), set by `_shared_run_dir`. None outside a session.
_RUN_DIR: list[pathlib.Path] = []


@pytest.fixture(scope="session", autouse=True)
def _shared_run_dir(tmp_path_factory) -> None:
    """One cache directory per pytest RUN, shared by its workers: a worker's basetemp is `<run>/popen-gwN`, and a run's `<run>` is fresh."""
    base = tmp_path_factory.getbasetemp()
    root = base.parent if base.name.startswith("popen-gw") else base
    run_dir = root / "devbox-shadow-transcripts"
    run_dir.mkdir(exist_ok=True)
    _RUN_DIR[:] = [run_dir]


def inputs_digest() -> str:
    """The port and the driver as bytes: a transcript is reused only while both are the ones that produced it."""
    digest = hashlib.sha256()
    for relative in (PORT, DRIVER):
        digest.update((paths.repo_root() / relative).read_bytes())
    return digest.hexdigest()[:16]


def drive(side: str, scenario: str) -> tuple[int, str, str]:
    """One side of one scenario, run ONCE PER PYTEST RUN and remembered.

    Shared across xdist workers through a file in the run's own directory, under an exclusive `flock`, so the `image` twin three tests read is driven once rather than once per worker that happens to run one of them. Every transcript is still a live run of this run's files: the directory is new per run, and the key carries `inputs_digest()`.
    """
    key = (side, scenario)
    if side == "old":
        return frozen_old(scenario)
    if key not in _CACHE:
        if not _RUN_DIR:
            _CACHE[key] = run_driver(side, scenario)
            return _CACHE[key]
        stem = _RUN_DIR[0] / ("%s-%s-%s" % (side, scenario, inputs_digest()))
        with open(str(stem) + ".lock", "w", encoding="utf-8") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            stored = pathlib.Path(str(stem) + ".json")
            if stored.is_file():
                rc, out, err = json.loads(stored.read_text(encoding="utf-8"))
                _CACHE[key] = (rc, out, err)
            else:
                _CACHE[key] = run_driver(side, scenario)
                stored.write_text(json.dumps(list(_CACHE[key])), encoding="utf-8")
    return _CACHE[key]


def frozen_old(scenario: str) -> tuple[int, str, str]:
    """The retired twin's transcript of one scenario, from `goldens/twins/lib.devbox.jsonl`."""
    return diff.twin_call(
        TWIN,
        [scenario],
        _retired,
        port=lambda: run_driver("new", scenario),
    )


def _retired() -> tuple[int, str, str]:
    raise RuntimeError(
        "%s is retired: re-record a Rule-T change with `%s %s --source port --reason ...`"
        % (TWIN, diff.REGOLDEN_VERB, TWIN)
    )


def run_driver(side: str, scenario: str) -> tuple[int, str, str]:
    """The driver as a subprocess, which is how the ledger runs it."""
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
        errors="surrogateescape",
        check=False,
        timeout=1800,
    )
    return (proc.returncode, proc.stdout, proc.stderr)


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
    # Twin defect 8 is RETIRED: the one label inspect is `|| true`, so an inspect failing after the running check no longer kills the status command. The table still prints, under the basename slug the empty labels fall back to.
    assert status_of(obs["hosts-fail"]) == 0
    assert b"VS Code:" in stdout_of(obs["hosts-fail"])


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


def claims_image(obs: dict[str, list[str]]) -> None:
    # The derive is SKIPPED when the base's vscode already carries the host's ids: the base is the run image and nothing is built.
    assert stdout_of(obs["run-image-match"]) == (devbox.DEVBOX_IMAGE + "\n").encode()
    assert not any(call[1] == "build" for call in calls_of(obs["ensure-uid-match"]))
    # A present derived tag is REUSED: inspected, never rebuilt.
    assert not any(call[1] == "build" for call in calls_of(obs["ensure-uid-present"]))
    # An absent one is built from Dockerfile.uid with the host's ids, tagged by the base's image id.
    # The fixture's recipe is `ARG BASE\nFROM ${BASE}\n`, so its hash is fixed; an edited recipe is a different tag.
    recipe = hashlib.sha256(b"ARG BASE\nFROM ${BASE}\n").hexdigest()[:12]
    # The ids are the driver's pinned ones (`GOLDEN_HOST_IDS`), not this process's: the transcript is the recording host's.
    tag = "%s:uid%d-gid%d-52b359d8cc2e-%s" % (
        devbox.DEVBOX_UID_IMAGE_REPO,
        *driver.GOLDEN_HOST_IDS,
        recipe,
    )
    assert stdout_of(obs["run-image-derive"]) == (tag + "\n").encode()
    build = next(call for call in calls_of(obs["ensure-uid-builds"]) if call[1] == "build")
    assert build[2:4] == ["-t", tag]
    assert "HOST_UID=%d" % driver.GOLDEN_HOST_IDS[0] in build
    assert build[-2].endswith("/.devcontainer/Dockerfile.uid")
    # Unreadable ids are a failure, never a silent run of the base.
    assert status_of(obs["ensure-uid-unresolved"]) == 1
    assert status_of(obs["ensure-ids-fail"]) == 1


def claims_identity_worktree(obs: dict[str, list[str]]) -> None:
    # No Dockerfile.uid under the mount root is a named refusal, never a tag with an empty hash.
    assert status_of(obs["uid-image-no-recipe"]) == 1
    assert stdout_of(obs["uid-image-no-recipe"]) == b""
    assert any("No derive recipe at" in line for line in errs_of(obs["uid-image-no-recipe"]))


SCENARIO_CLAIMS = {
    "image": claims_image,
    "identity-worktree": claims_identity_worktree,
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

# RULE T: the step labels whose lines the port INTENTIONALLY no longer shares with the twin, per scenario. Each is a defect the twin still has and the port fixed (`test_delta_*` at the end of this file); the live differential leaves exactly these labels out, and `test_every_delta_label_still_diverges` proves each is still a real divergence.
DELTA_LABELS = {
    "docker-query": {
        "conflicts-nonl",  # D3
        "running-ps-fails",  # D7
        "active-ps-fails",  # D7
        "missing-ps-fails",  # D7
        "cid-fail",  # D7
    },
    "exec": {"doctor-not-running", "zero", "identity-not-running"},  # D2, D5
    "identity": {"url-ps-fails"},  # D7
    "identity-utf8": {"status-escape", "slug", "basename"},  # D4, D10
    "lifecycle": {"stop-ps-fails"},  # D7
    "state": {"get-dot", "get-star", "get-bracket"},  # D11
    "status": {"conflict"},  # D4
    "up-create": {"no-group", "octal"},  # D1, D6
    "up-existing": {"start-fails"},  # D9
}

# P3: a newline in a slug argument is a dash. The scenarios whose corpus carries newlines compare those labels against the TWIN'S answer for the same input with each newline replaced by another byte outside the DNS alphabet, which is what the fix means.
NEWLINE_SCENARIOS = ("slug-edge", "slug-fuzz")


def _label_of(line: str) -> str:
    return line[4:].partition(" ")[0]


def _without_delta_labels(out: str, scenario: str) -> list[str]:
    skip = DELTA_LABELS.get(scenario, set())
    return [line for line in out.splitlines() if _label_of(line) not in skip]


def _hex_stdout(line: str) -> bytes:
    return bytes.fromhex(line.split(" out=", 1)[1])


@functools.cache
def _twin_stdout_for(values: tuple[str, ...]) -> tuple[bytes, ...]:
    """The retired twin's `devbox_slugify` stdout for each value, one hex line per value, from the golden."""
    _, out, _ = diff.twin_call(
        TWIN, ["slugify-stdout", json.dumps(list(values))], _retired, label="slugify-stdout"
    )
    return tuple(bytes.fromhex(line) for line in out.splitlines())


def _newline_delta_holds(scenario: str, old_out: str, new_out: str) -> bool:
    """Every diverging slug label has a newline in its input, and the port answers what the twin answers with that newline spelled `!`."""
    corpus = driver.slug_corpus(scenario)
    old_lines = {_label_of(x): x for x in old_out.splitlines() if x.startswith("obs slug-")}
    new_lines = {_label_of(x): x for x in new_out.splitlines() if x.startswith("obs slug-")}
    if old_lines.keys() != new_lines.keys():
        return False
    diverged = [label for label in old_lines if old_lines[label] != new_lines[label]]
    for label in diverged:
        index = label.rpartition("-")[2]
        if not index.isdigit() or "\n" not in corpus[int(index)]:
            return False
    expected = _twin_stdout_for(
        tuple(corpus[int(label.rpartition("-")[2])].replace("\n", "!") for label in diverged)
    )
    return all(
        _hex_stdout(new_lines[label]) == answer
        for label, answer in zip(diverged, expected, strict=True)
    )


# D12: the twin's bind sources went through `.ci/lib/../..`; the port's do not (the directory is gone). The scenarios whose `docker run` argv carries the binds compare the twin's transcript with that spelling folded to the port's.
BIND_SPELLING_SCENARIOS = ("up-create", "up-existing")
TWIN_BIND_SPELLING = "/.ci/lib/../../.devcontainer/"
PORT_BIND_SPELLING = "/.devcontainer/"


# The twin pinned the proxy image at `traefik:v3.6`; the port reads `DEVBOX_PROXY_IMAGE`, which moves with the product proxy's pin (e52a9d8f0). The frozen transcripts keep the old tag, so every comparison folds it to the port's rather than re-recording a golden whose D12 spelling must stay.
TWIN_PROXY_IMAGE = '"traefik:v3.6"'


def _fold_twin_spellings(scenario: str, old_out: str) -> str:
    if scenario in BIND_SPELLING_SCENARIOS:
        old_out = old_out.replace(TWIN_BIND_SPELLING, PORT_BIND_SPELLING)
    return old_out.replace(TWIN_PROXY_IMAGE, '"%s"' % devbox.DEVBOX_PROXY_IMAGE)


def equivalent(scenario: str, old_out: str, new_out: str) -> bool:
    """The comparison the whole file stands on, minus the Rule T deltas."""
    old_out = _fold_twin_spellings(scenario, old_out)
    if scenario in NEWLINE_SCENARIOS:
        return _newline_delta_holds(scenario, old_out, new_out)
    return _without_delta_labels(old_out, scenario) == _without_delta_labels(new_out, scenario)


DIVERGENCE_LINES = 12
DIVERGENCE_WIDTH = 4000


def divergence(scenario: str, old_out: str, new_out: str) -> str:
    """The first lines the two transcripts disagree on, both sides, for the failure message.

    A bare `assert equivalent(...)` prints pytest's elided repr of two transcripts tens of kilobytes long, which names no line: runs 38389205702 and 38409515814 each cost a round trip to learn WHAT diverged. A `docker run` argv is one long line, so each side is cut around the first differing column.
    """
    old_out = _fold_twin_spellings(scenario, old_out)
    old_lines = _without_delta_labels(old_out, scenario)
    new_lines = _without_delta_labels(new_out, scenario)
    found = [
        "scenario %s diverged (%d twin lines, %d port lines)"
        % (scenario, len(old_lines), len(new_lines))
    ]
    if scenario in NEWLINE_SCENARIOS:
        # equivalent() accepts a slug label whose input holds a newline when the port answers as the twin does with that newline spelled `!`; the raw lines below do not apply that rule, so a pair listed here can be one it accepts.
        found.append(
            "(raw lines; a slug label with a newline in its input differs by rule, see _newline_delta_holds)"
        )
    for index in range(max(len(old_lines), len(new_lines))):
        old_line = old_lines[index] if index < len(old_lines) else "<no line>"
        new_line = new_lines[index] if index < len(new_lines) else "<no line>"
        if old_line == new_line:
            continue
        column = next(
            (at for at, (a, b) in enumerate(zip(old_line, new_line, strict=False)) if a != b),
            min(len(old_line), len(new_line)),
        )
        start = max(0, column - 200)
        found.append("line %d, column %d:" % (index + 1, column))
        found.append("  twin: %s" % old_line[start : start + DIVERGENCE_WIDTH])
        found.append("  port: %s" % new_line[start : start + DIVERGENCE_WIDTH])
        if len(found) > 3 * DIVERGENCE_LINES:
            found.append("... and more")
            break
    return "\n".join(found)


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
    assert equivalent(scenario, old_out, new_out), divergence(scenario, old_out, new_out)


@pytest.mark.parametrize("scenario", sorted(DELTA_LABELS))
def test_every_delta_label_still_diverges(scenario: str) -> None:
    """A delta that stopped diverging is a stale exclusion hiding a comparison."""
    old_out, new_out = drive("old", scenario)[1], drive("new", scenario)[1]
    for label in DELTA_LABELS[scenario]:
        old = [x for x in old_out.splitlines() if _label_of(x) == label]
        new = [x for x in new_out.splitlines() if _label_of(x) == label]
        assert old, "the twin never ran %s" % label
        assert old != new, "the delta %s no longer diverges: remove it from DELTA_LABELS" % label


@pytest.mark.parametrize("scenario", NEWLINE_SCENARIOS)
def test_the_newline_delta_is_a_real_divergence(scenario: str) -> None:
    assert drive("old", scenario)[1] != drive("new", scenario)[1]


def test_the_basename_fallback_depends_on_the_locale() -> None:
    """Twin defect 10, against the live twin: one checkout, two hostnames, decided by the caller's locale. The PORT answers the C one for both (`test_delta_d10`)."""
    c_locale = observations(drive("old", "identity-detached")[1])
    utf8 = observations(drive("old", "identity-utf8")[1])
    assert stdout_of(c_locale["basename"]) == b"my-box----9\n"
    assert stdout_of(utf8["basename"]) == b"my-box---9\n"
    assert driver.STUB_SCENARIOS["identity-utf8"][1] == "C.utf8"


def test_the_corpus_is_not_empty() -> None:
    assert len(SCENARIOS) == 24, "the scenario set moved to %d" % len(SCENARIOS)
    assert set(SCENARIOS) == set(OBSERVATION_FLOOR), sorted(set(SCENARIOS) ^ set(OBSERVATION_FLOOR))
    assert len(driver.fuzz_corpus()) == driver.FUZZ_COUNT
    assert len(set(driver.fuzz_corpus())) > driver.FUZZ_COUNT / 2
    assert driver.fuzz_corpus() == driver.fuzz_corpus()


def stub_functions() -> set[str]:
    return {step.fn for _, _, steps in driver.STUB_SCENARIOS.values() for step in steps()}


def test_every_function_is_driven_by_some_scenario() -> None:
    """Every one of the fifty-five is the subject of a step, so none of them is licensed by a ledger that never called it."""
    driven = stub_functions() | {"devbox_slugify", "devbox_slug_drift", "devbox_route_label"}
    assert driven == set(devbox.BASH_NAMES), sorted(set(devbox.BASH_NAMES) ^ driven)


@pytest.mark.parametrize("scenario", [*sorted(driver.PURE_SCENARIOS), *CHEAP_STUB_SCENARIOS])
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
    ("the run image is always the base, so nothing is ever derived", "Devbox.run_image", "image"),
    ("the derived tag drops the recipe hash", "Devbox.uid_image", "image"),
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
        return lambda code=None, _hint="", _routed=devbox.ROUTED_UNKNOWN, _starting="no": (
            devbox.Outcome(devbox.ROUTE_LIVE % code + "\n", 0)
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
    if attribute == "Devbox.run_image":

        def run_image(self, *_argv):
            self.write(devbox.DEVBOX_IMAGE + "\n")
            return 0

        return run_image
    if attribute == "Devbox.uid_image":

        def uid_image(self, *_argv):
            self.docker_words()
            self.write(
                "%s:uid%d-gid%d-52b359d8cc2e\n" % (devbox.DEVBOX_UID_IMAGE_REPO, self.uid, self.gid)
            )
            return 0

        return uid_image
    raise AssertionError("no planted value for %s" % attribute)


@pytest.mark.parametrize(("label", "attribute", "scenario"), PLANTS)
def test_a_planted_defect_is_caught(label: str, attribute: str, scenario: str, monkeypatch) -> None:
    """THE CONTROL ON THE COMPARISON: each plant must make the live twin disagree.

    Planted in process rather than on disk, so nothing can leave a defect behind in the tree. `monkeypatch` restores the attribute when the case ends.
    """
    _, twin_out, _ = drive("old", scenario)
    assert equivalent(scenario, twin_out, new_transcript(scenario)), (
        "the port already disagrees before the plant"
    )
    owner, _, name = attribute.rpartition(".")
    target = devbox.Devbox if owner == "Devbox" else devbox
    monkeypatch.setattr(target, name, planted_value(attribute))
    assert not equivalent(scenario, twin_out, new_transcript(scenario)), (
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
    bin_dir = driver.build_stub_farm(tmp_path)
    search = str(bin_dir) + ":" + os.environ.get("PATH", "")
    for name in driver.STUBBED:
        assert shutil.which(name, path=search) == str(bin_dir / name), "%s is not shadowed" % name
    with driver.StubServer(tmp_path / "stub"):
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


# -- the twin is retired, and the port carries all of it ------------------------


def test_the_port_defines_these_fifty_five_and_nothing_else() -> None:
    """The twin's function list was measured against `devbox.BASH_NAMES` while the bash existed (fifty-five names); the count is what is kept."""
    assert len(devbox.BASH_NAMES) == 55
    assert len(set(devbox.BASH_NAMES.values())) == 55


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


def test_nothing_sources_the_retired_twin() -> None:
    """The bridge reaches the port in process, so no prelude of its names the library."""
    assert not any("devbox.sh" in line for line in bridge.PRELUDE)
    assert bridge._devbox_words("devbox_up") == ["devbox_up"]
    assert bridge._devbox_words("ensure_deps") is None


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


# -- the host's ids, which the differential pins and therefore cannot see ----


def _quiet_box(out: io.BytesIO, **kwargs) -> devbox.Devbox:
    return devbox.Devbox(
        {"PATH": "/usr/bin:/bin", "HOME": "/nonexistent"},
        stdout=out,
        stderr=io.BytesIO(),
        **kwargs,
    )


def test_the_host_ids_are_the_running_users_by_default(tmp_path: pathlib.Path) -> None:
    """The driver pins `GOLDEN_HOST_IDS`, so every scenario above would still pass if the DEFAULT stopped being this process's effective ids. This is the test that reads the default, and the directory probe behind the lease pool, against the real host."""
    out = io.BytesIO()
    box = _quiet_box(out)
    assert (box.uid, box.gid) == (os.geteuid(), os.getegid())
    assert box.host_ids() == "%d:%d" % (os.geteuid(), os.getegid())
    # A directory this process made is this user's; a missing one is not a directory at all.
    assert box.owns_runtime_dir(str(tmp_path)) is True
    assert box.owns_runtime_dir(str(tmp_path / "missing")) is False
    # CONTROL: injected ids are the ones every reader answers with, and somebody else's directory is not theirs.
    stranger = (os.geteuid() + 4242, os.getegid() + 4343)
    pinned = _quiet_box(out, host_ids=stranger)
    assert pinned.host_ids() == "%d:%d" % stranger
    assert pinned.owns_runtime_dir(str(tmp_path)) is False
    assert pinned.core_lease_src() == 0
    assert out.getvalue() == b"", "a lease pool was reported under a runtime dir nobody checked"


def test_the_driver_answers_as_the_recording_host(tmp_path: pathlib.Path) -> None:
    """What `GoldenHostDevbox` changes, and that it changes nothing else: the recorded runtime dir is owned, every other path is not, whatever this host holds."""
    out = io.BytesIO()
    box = driver.GoldenHostDevbox(
        {"PATH": "/usr/bin:/bin", "HOME": "/nonexistent"},
        stdout=out,
        stderr=io.BytesIO(),
        host_ids=driver.GOLDEN_HOST_IDS,
    )
    assert box.core_lease_src() == 0
    assert out.getvalue() == (driver.GOLDEN_RUNTIME_DIR + "/rediacc-cores\n").encode()
    assert box.owns_runtime_dir(str(tmp_path)) is False


def test_up_reads_the_host_by_default(tmp_path: pathlib.Path) -> None:
    """The driver pins the three probes `up` makes of the host, so every scenario above would still pass if a DEFAULT stopped reading it. These are the defaults, against real paths: a node, a socket, and the lease pool's `mkdir -m 700`."""
    box = _quiet_box(io.BytesIO())
    # `[ -e ]`: whatever this host has, and never a path that is not there.
    assert box.has_host_node("/dev/null") is True
    assert box.has_host_node(str(tmp_path / "missing")) is False
    for node in driver.GOLDEN_HOST_NODES:
        assert box.has_host_node(node) is os.path.exists(node)
    # `[[ -S ]]`: a real socket, through a symlink too; a regular file and a missing path are not one.
    # A unix socket path is capped at 108 bytes and pytest's tmp_path nests several directories under TMPDIR (docs/agent-reference/TRAPS.md), so the socket lives in a directory of its own under the SHORTER of TMPDIR and /tmp: a long TMPDIR alone would overflow the cap (review f80bbd39.1), and /tmp alone ignores a host whose TMPDIR is the writable one (review 8f0b56be.3).
    roots = [
        d for d in (tempfile.gettempdir(), "/tmp") if os.path.isdir(d) and os.access(d, os.W_OK)
    ]
    short = pathlib.Path(tempfile.mkdtemp(dir=min(roots, key=len)))
    listener = socket.socket(socket.AF_UNIX)
    try:
        listener.bind(str(short / "s"))
        (short / "link").symlink_to(short / "s")
        (short / "file").write_text("", encoding="utf-8")
        assert box.has_host_socket(str(short / "s")) is True
        assert box.has_host_socket(str(short / "link")) is True
        assert box.has_host_socket(str(short / "file")) is False
        assert box.has_host_socket(str(short / "missing")) is False
    finally:
        listener.close()
        shutil.rmtree(short, ignore_errors=True)
    # `[ -d ] || mkdir -m 700`: made once at mode 700, an answer when it is already there, and no answer under a parent that is not.
    pool = tmp_path / "pool"
    assert box.lease_dir_ready(str(pool)) is True
    assert stat.S_IMODE(pool.stat().st_mode) == 0o700
    assert box.lease_dir_ready(str(pool)) is True
    assert box.lease_dir_ready(str(tmp_path / "missing" / "pool")) is False
    assert not (tmp_path / "missing").exists()


def test_the_driver_answers_for_the_recorded_devices_and_no_others(tmp_path: pathlib.Path) -> None:
    """`GoldenHostDevbox` says yes to exactly what the recording host had, and its lease answer never makes a directory."""
    box = driver.GoldenHostDevbox(
        {"PATH": "/usr/bin:/bin", "HOME": "/nonexistent"},
        stdout=io.BytesIO(),
        stderr=io.BytesIO(),
        host_ids=driver.GOLDEN_HOST_IDS,
    )
    assert [box.has_host_node(node) for node in driver.GOLDEN_HOST_NODES] == [True, True]
    assert box.has_host_node("/dev/null") is False
    assert box.has_host_socket(driver.GOLDEN_DOCKER_SOCKET) is True
    assert box.has_host_socket(str(tmp_path)) is False
    assert box.lease_dir_ready(driver.GOLDEN_RUNTIME_DIR + "/rediacc-cores") is True
    assert box.lease_dir_ready(str(tmp_path / "pool")) is False
    assert not (tmp_path / "pool").exists()


class BareHostDevbox(driver.GoldenHostDevbox):
    """The recording host's ids on a host with none of the four: no kvm, no tun, no docker socket, no runtime dir."""

    def owns_runtime_dir(self, _runtime: str) -> bool:
        return False

    def has_host_node(self, _path: str) -> bool:
        return False

    def has_host_socket(self, _path: str) -> bool:
        return False


# The words `up` adds to `docker run` only where the host has the thing, as the contiguous runs the argv carries them in. 993 is the stub farm's `stat -c %g /dev/kvm`.
HOST_ONLY_RUNS = (
    ["-v", "/var/run/docker.sock:/var/run/docker.sock"],
    ["-v", driver.GOLDEN_RUNTIME_DIR + "/rediacc-cores:" + devbox.DEVBOX_CORE_LEASE_DEST],
    ["--device", "/dev/kvm"],
    ["--device", "/dev/net/tun"],
    ["--group-add", "993", "--cap-add", "NET_ADMIN", "--cap-add", "SYS_ADMIN"],
    ["-e", "REDIACC_CORE_LEASE_DIR=" + devbox.DEVBOX_CORE_LEASE_DEST],
)


def _first_run(transcript: str, label: str) -> list[str]:
    step = observations(transcript)[label]
    assert status_of(step) == 0
    return next(call for call in calls_of(step) if call[1:4] == ["run", "-d", "--name"])


def _without_run(argv: list[str], words: list[str]) -> list[str]:
    """`argv` with its ONE occurrence of the contiguous `words` cut out; a run that is absent or repeated fails here by name."""
    starts = [at for at in range(len(argv)) if argv[at : at + len(words)] == words]
    assert len(starts) == 1, "%r occurs %d time(s) in the `docker run` argv" % (words, len(starts))
    return argv[: starts[0]] + argv[starts[0] + len(words) :]


def test_up_drops_what_the_host_does_not_have(monkeypatch) -> None:
    """The arm the differential cannot compare: on a host with no kvm, tun, docker socket or runtime dir, `up` still creates the devbox, and its `docker run` is the recorded one minus exactly those words.

    This is also what proves the driver's pins are the ONLY way those words reach the argv: it runs on whatever host the suite is on, and the recording machine has all four.
    """
    # CONTROL: the same step as the recording host saw it carries every run, once. `_without_run` asserts that.
    expected = _first_run(new_transcript("up-create"), "ok")
    for words in HOST_ONLY_RUNS:
        expected = _without_run(expected, words)
    monkeypatch.setattr(driver, "GoldenHostDevbox", BareHostDevbox)
    bare = _first_run(new_transcript("up-create"), "ok")
    assert bare == expected
    # The docker group's gid is the stub farm's getent answer, not a host probe: it stays.
    assert bare.count("--group-add") == 1
    assert "--device" not in bare


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


def test_the_driver_refuses_the_retired_bash_side() -> None:
    proc = subprocess.run(
        [sys.executable, "-m", DRIVER_MODULE, "--side", "old", "--port", PORT, "arity"],
        cwd=str(paths.repo_root()),
        env={**os.environ, "PYTHONPATH": ".ci"},
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 2, "argparse refuses a side the driver no longer has"
    assert "invalid choice" in proc.stderr


def test_the_driver_refuses_when_the_port_is_not_there() -> None:
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            DRIVER_MODULE,
            "--side",
            "new",
            "--port",
            ".ci/rediacc_ci/core/no-such-file.py",
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


def test_the_driver_scenarios_line_up() -> None:
    assert set(driver.PURE_SCENARIOS) == {
        "arity",
        "drift",
        "route-label",
        "slug-basic",
        "slug-edge",
        "slug-fuzz",
        "slug-utf8",
    }
    for name, (fixture, locale, steps) in driver.STUB_SCENARIOS.items():
        built = steps()
        assert built, name
        assert fixture in ("main", "worktree", "detached", "gone"), name
        assert locale in ("C", "C.utf8"), name


# -- the pure rules, exercised directly -------------------------------------------

# The nine rows the retired `test_gate_devbox_slug.py` pinned (its bash lift of `devbox_slugify` is gone with `devbox.sh`; the same rows are in the `slug-basic` and `slug-edge` goldens).
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


def test_the_cap_is_applied_before_the_final_trim() -> None:
    assert devbox.slugify("a" * 39 + "-bcd") == "a" * 39
    assert devbox.slugify("a" * 40 + "-bcd") == "a" * 40
    assert devbox.slugify("a" * 41) == "a" * 40


def test_the_empty_answer_is_still_a_line() -> None:
    assert devbox.slugify("///") == ""
    assert devbox.slugify_stdout("///") == "\n"
    assert devbox.slugify_stdout() == "\n"


def test_a_newline_in_the_argument_is_a_dash() -> None:
    """Rule T fix P3 (`test_delta_p3`): the twin kept the newline, because `sed` works per line."""
    assert devbox.slugify("a\nb") == "a-b"
    assert devbox.slugify("-a-\n-b-") == "a-b"
    assert devbox.slugify("a\n") == "a"
    assert devbox.slugify("\na") == "a"


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
    """No collapse, no cap, and the C locale's dash count whatever the caller's locale (Rule T fix D10)."""
    assert devbox.slug_basename_rule("a..b") == "a--b\n"
    assert devbox.slug_basename_rule("x" * 50) == "x" * 50 + "\n"
    assert devbox.slug_basename_rule("aÜb") == "a--b\n"


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


def test_the_repo_root_is_a_checkout_with_the_port_in_it() -> None:
    assert (paths.repo_root() / PORT).is_file()
    assert pathlib.Path(DRIVER).name == "devbox_shadow_driver.py"


# -- Rule T: the twin's defects, fixed in the port as INTENTIONAL DELTAS ---------
#
# PLAN-retire-bash-oracles section 1 and task B4. Each case below pins the port's FIXED behaviour from the PORT's transcript of the scenario that exposes the defect. The twin's behaviour is pinned beside it by `SCENARIO_CLAIMS` (against the live twin), so a twin that moved fails there. The live differential leaves exactly the labels named in `DELTA_LABELS` out of its comparison, and `test_every_delta_label_still_diverges` proves each is still a real divergence.


def port_obs(scenario: str) -> dict[str, list[str]]:
    rc, out, err = drive("new", scenario)
    assert rc == 0, err
    return observations(out)


def test_delta_d1_a_host_with_no_docker_group_still_creates_the_devbox() -> None:
    """Defect D1, fixed: no `docker` group is a warning and a container with no `--group-add`, where the twin died silently with getent's status after the proxy check."""
    obs = port_obs("up-create")["no-group"]
    assert status_of(obs) == 0
    run = next(call for call in calls_of(obs) if call[1:4] == ["run", "-d", "--name"])
    # The only `--group-add` left is the kvm group's (the driver answers as the recording host, which has /dev/kvm); the docker group's is gone and its gid env is empty.
    assert run.count("--group-add") == 1
    assert "DOCKER_GID=" in run
    assert any("No docker group on this host" in line for line in errs_of(obs))


@pytest.mark.parametrize("scenario", BIND_SPELLING_SCENARIOS)
def test_delta_d12_the_script_binds_do_not_go_through_the_deleted_lib_directory(
    scenario: str,
) -> None:
    """Defect D12, fixed: the bind sources are `<root>/.devcontainer/<file>`. The twin's `<root>/.ci/lib/../../.devcontainer/<file>` cannot be resolved once `.ci/lib` is not a directory, so docker would refuse every `devbox_up`.

    Both directions: the frozen twin transcript carries the old spelling (so the fold in `equivalent` is a real fold), and the port's carries the new one and never the old.
    """
    # The record `test_the_port_matches_the_live_twin[<scenario>]` froze: its label is passed explicitly, so this test reads the same key.
    old_out = diff.twin_call(
        TWIN,
        [scenario],
        _retired,
        label="test_the_port_matches_the_live_twin[%s]" % scenario,
    )[1]
    new_out = drive("new", scenario)[1]
    assert TWIN_BIND_SPELLING in old_out, "the frozen twin no longer shows the old spelling"
    assert TWIN_BIND_SPELLING not in new_out
    assert "%sdevbox-entrypoint.sh:/usr/local/bin/devbox-entrypoint.sh:ro" % PORT_BIND_SPELLING in (
        new_out
    )


def test_delta_d2_the_identity_probe_fails_when_the_devbox_is_not_running() -> None:
    """Defect D2, fixed: a devbox that is not running has no usable identity. The twin's `|| true` swallowed the refusal and reported success."""
    obs = port_obs("exec")["identity-not-running"]
    assert status_of(obs) == 1
    assert any("not running" in line for line in errs_of(obs))


def test_delta_d3_an_unterminated_final_docker_line_is_still_a_container() -> None:
    """Defect D3, fixed: the last `docker ps` line is read even without a trailing newline, so `id4` is inspected."""
    obs = port_obs("docker-query")["conflicts-nonl"]
    assert any("id4" in call for call in calls_of(obs))
    assert any("id1" in call for call in calls_of(obs))


def test_delta_d4_log_lines_print_data_verbatim() -> None:
    """Defect D4, fixed: a worktree label's backslashes are DATA. The twin's `echo -e` expanded `\\t`, spelled `\\u00fc` as `ü` and let `\\c` swallow the rest of the line."""
    lines = errs_of(port_obs("status")["conflict"])
    assert "✓   /other/x\\ty\\u00fcz" in lines
    assert "✓   /cut\\chere" in lines
    assert any(line.startswith("✓ Which container answers") for line in lines)


def test_delta_d5_exec_with_no_command_is_a_usage_error() -> None:
    """Defect D5, fixed: zero arguments are refused with status 2. The twin ran `bash -lc "'' "` inside the container."""
    obs = port_obs("exec")["zero"]
    assert status_of(obs) == 2
    assert not any(call[1:2] == ["exec"] for call in calls_of(obs))
    assert any("needs a command" in line for line in errs_of(obs))


def test_delta_d6_a_zero_padded_base_port_is_decimal() -> None:
    """Defect D6, fixed: `017000` is port 17000. The twin's shell arithmetic read it as octal 7680 and moved every route to a port nothing listens on."""
    run = next(
        call
        for call in calls_of(port_obs("up-create")["octal"])
        if call[1:4] == ["run", "-d", "--name"] and call[4] != "rediacc-devbox-proxy"
    )
    assert "DEVBOX_PORT=17000" in run
    assert "DEVBOX_TERM_PORT=17005" in run
    assert devbox.decimal("017000") == 17000
    assert devbox.decimal(" 08 ") == 8
    with pytest.raises(devbox.DevboxError):
        devbox.decimal("a1")


@pytest.mark.parametrize(
    ("scenario", "label", "status"),
    [("docker-query", "active-ps-fails", 3), ("docker-query", "missing-ps-fails", 2)],
)
def test_delta_d7_a_failing_docker_ps_says_so(scenario: str, label: str, status: int) -> None:
    """Defect D7, fixed: the call still ends with docker's status, and now names the failure. The twin ended silently, with nothing on stderr."""
    obs = port_obs(scenario)[label]
    assert status_of(obs) == status
    assert any("docker ps failed" in line for line in errs_of(obs))


def test_delta_d7_stop_names_a_failing_docker_ps() -> None:
    obs = port_obs("lifecycle")["stop-ps-fails"]
    assert status_of(obs) == 2
    assert any("docker ps failed" in line for line in errs_of(obs))


def test_delta_d9_a_failed_docker_start_says_what_failed() -> None:
    """Defect D9, fixed: a failed `docker start` is named. The twin ended with docker's words alone."""
    obs = port_obs("up-existing")["start-fails"]
    assert status_of(obs) == 1
    errs = errs_of(obs)
    assert errs[0] == "→ Starting existing devbox container"
    assert any("Could not start the existing devbox container" in line for line in errs)


def test_delta_d10_the_basename_fallback_ignores_the_locale() -> None:
    """Defect D10, fixed: one checkout has one hostname, whatever the caller's locale. The twin answered `my-box----9` under the C locale and `my-box---9` under UTF-8; both are the C answer now."""
    c_locale = port_obs("identity-detached")
    utf8 = port_obs("identity-utf8")
    assert stdout_of(c_locale["basename"]) == b"my-box----9\n"
    assert stdout_of(utf8["basename"]) == b"my-box----9\n"
    assert driver.STUB_SCENARIOS["identity-utf8"][1] == "C.utf8"


def test_delta_d11_the_state_key_is_a_literal() -> None:
    """Defect D11, fixed: `base.port` is not `base_port` and `sl*ug` is not `slug`. The twin compiled the key as a regular expression."""
    obs = port_obs("state")
    assert stdout_of(obs["get-dot"]) == b""
    assert stdout_of(obs["get-star"]) == b""
    # The literal spelling still reads the real key.
    assert stdout_of(obs["get-last"]) == b"no-newline"


def test_delta_p3_a_newline_in_a_slug_input_is_a_dash() -> None:
    """Pure-three defect 3, fixed: a newline is outside the DNS alphabet like any other byte. The twin's `sed` trimmed per LINE, so a two-line argument produced a two-line, unroutable hostname."""
    assert devbox.slugify("a\nb") == "a-b"
    assert devbox.slugify("\nfeat\n") == "feat"
    assert devbox.slugify_stdout("x\ny") == "x-y\n"


def test_delta_p7_a_missing_argument_stays_a_refusal() -> None:
    """Pure-three behaviour 7 is NOT a defect: `devbox_slug_drift` and `devbox_route_label` need their first argument, and refusing the call is the strict answer. Port and twin agree, so the case is pinned here and left as it is."""
    with pytest.raises(devbox.DevboxError):
        devbox.slug_drift(None)
    with pytest.raises(devbox.DevboxError):
        devbox.route_label(None)
