"""`rediacc_ci.proxies.docker_prepull`, driven against the bytes its bash twin printed.

THE TWIN HAS BEEN DELETED. While both copies existed this file ran `.ci/scripts/test/proxies/proxy-docker-prepull.sh` and the ported proxy and compared the whole `(exit, stdout, stderr)` tuple byte for byte. The ledger `.ci/shadow/w7p6-proxy-docker-prepull.observations.jsonl` holds 5 rows of that comparison.

Both cases now compare against `goldens/proxy-docker-prepull/`, which holds the twin's OWN recorded bytes, captured on its last day in the tree, and each golden's provenance header carries the blob sha.

A PROXY IS A TEST HARNESS, SO ITS OUTPUT IS ITS PRODUCT. It prints one line per check and one summary line, and nothing else: no timestamps, no temporary paths, no process ids. That is what makes `old == new` on the full tuple the right assertion rather than a weaker finding-set comparison, and it is what makes the bytes freezable at all.

THE SUBJECT IS THE PORT NOW, ON BOTH SIDES, and the order that got there matters because it is the evidence. `.ci/scripts/infra/docker-prepull.sh` was retired in the same wave, and the flip was done in two steps: first only the ported proxy was pointed at `rediacc_ci.infra.docker_prepull` while the bash twin still drove the bash subject, and that comparison stayed byte-identical
over four live pulls, which is a live-daemon check no fixture can make; then both proxies were pointed at the port together, the comparison was re-run, and only then was the twin recorded and deleted.

THE RECORDING NEEDS A DAEMON AND A REGISTRY, and so does the replay. Without either, the subject exits 77, which is CANNOT-RUN rather than a verdict, and a comparison of 77 against 77 proves nothing about the port. Both cases are therefore skipped when docker is unreachable, exactly as a developer's local run would be, and the corpus check still runs so a vanished golden is caught
even on a machine that cannot drive one.

NOTHING IS MASKED, and that is asserted rather than assumed: `test_no_recording_carries_a_path` checks that neither golden mentions this checkout or a temporary directory. A proxy that started printing the paths it ran would be a proxy whose output could not be frozen, and the corpus should say so out loud rather than quietly acquiring a mask.
"""

from __future__ import annotations

import shutil
import subprocess
import typing

import pytest

from rediacc_ci import paths
from rediacc_ci.tests import differential as diff
from rediacc_ci.tests import frozen

if typing.TYPE_CHECKING:  # pragma: no cover - annotations only
    import pathlib

ROOT = paths.repo_root()
MODULE = "rediacc_ci.proxies.docker_prepull"
SLUG = "proxy-docker-prepull"

CASE_KW: dict[str, dict[str, typing.Any]] = {
    "the-selftest": {"args": ["--selftest"]},
    "a-full-run": {"args": []},
}

CASES = tuple(CASE_KW)


def _docker_ready() -> bool:
    if shutil.which("docker") is None:
        return False
    return (
        subprocess.run(
            ["docker", "info"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False
        ).returncode
        == 0
    )


DOCKER_READY = _docker_ready()
needs_docker = pytest.mark.skipif(
    not DOCKER_READY,
    reason="docker daemon not reachable; the proxy would report 77, proving nothing",
)


def run(subject: str, name: str) -> tuple[int, str, str]:
    """One proxy, once. `subject` is a bash path or the module to run with `-m`."""
    args = CASE_KW[name]["args"]
    tail = (" " + " ".join(args)) if args else ""
    if subject.endswith(".sh"):
        return diff.bash_streams("bash %s%s" % (subject, tail), env=diff.env_for(), timeout=180)
    return diff.bash_streams(
        "python3 -m %s%s" % (subject, tail),
        env=diff.env_for(PYTHONPATH=".ci", PYTHONDONTWRITEBYTECODE="1"),
        timeout=180,
    )


def render(code: int, stdout: str, stderr: str) -> str:
    return frozen.render(code, stdout, stderr)


def recorded(name: str) -> tuple[int, str, str]:
    text = frozen.read(SLUG, name)
    exit_line, rest = text.split("\n", 1)
    stdout, stderr = rest.split("--- stdout ---\n", 1)[1].split("--- stderr ---\n", 1)
    return int(exit_line.removeprefix("exit: ")), stdout, stderr


def compare(name: str) -> tuple[int, str, str]:
    want = recorded(name)
    got = run(MODULE, name)
    labels = ("exit code", "stdout", "stderr")
    # `strict=True`: the tuple and the labels must stay the same length, and a silently truncated zip is how a comparison stops checking its last field.
    for label, a, b in zip(labels, want, got, strict=True):
        assert a == b, "%s: %s diverged:\n--- recorded ---\n%s\n--- port ---\n%s" % (
            name,
            label,
            a,
            b,
        )
    return got


@pytest.mark.parametrize("name", CASES)
@needs_docker
def test_port_matches_the_twins_recorded_output(name: str) -> None:
    compare(name)


def test_every_case_has_a_golden_and_no_golden_is_orphaned() -> None:
    """ANTI-VACUITY on the corpus, and it runs with or without a daemon: a case whose golden vanished would pass by never being compared, and a golden nothing reads is a recording of a case that stopped running."""
    frozen.assert_corpus(SLUG, set(CASES))


def test_no_recording_carries_a_path() -> None:
    """The no-mask claim in the module docstring, asserted rather than trusted."""
    for name in CASES:
        for stream in recorded(name)[1:]:
            assert str(ROOT) not in stream, name
            assert "/tmp/" not in stream, name


# --------------------------------------------------------------------------- What the recordings say ---------------------------------------------------------------------------


def test_the_selftest_is_green() -> None:
    """`--selftest` exercises the proxy library itself, with no docker and no subject, which is why it is the one case a machine with no daemon could still have recorded."""
    code, stdout, _ = recorded("the-selftest")
    assert code == 0
    assert stdout.strip() != "", "the selftest recorded nothing at all"


def test_the_full_run_passes_nine_checks_and_names_three_requirements() -> None:
    """The counts are the summary the operator reads, so they are asserted rather than the whole line being taken on trust."""
    code, stdout, _ = recorded("a-full-run")
    assert code == 0
    assert "9 check(s) passed, 3 requirement(s) present" in stdout


def test_the_recorded_run_names_the_port_as_its_subject() -> None:
    """The header says what the proxy is a stand-in FOR, and after the flip that is the port rather than a `.sh` that no longer exists. A recording made before the flip would have frozen a dead path into the proxy's own output."""
    stdout = recorded("a-full-run")[1]
    assert (
        "proxy docker-prepull: local stand-in for .ci/rediacc_ci/infra/docker_prepull.py" in stdout
    )


def test_every_check_the_recording_carries() -> None:
    """The labels, in order. A proxy that quietly stopped running one of its checks would still print a summary and still exit 0; the only thing that notices is the list."""
    stdout = recorded("a-full-run")[1]
    for label in (
        "no arguments is refused, not treated as an empty success",
        "the refusal prints its usage",
        "a bare ref pulls",
        "the bare-ref run reported the count it pulled",
        "is present in the local daemon after the pull",
        "the <ref>=<platform> form pulls",
        "the ref=platform run reported the count it pulled",
        "two specs in one call",
        "the two-spec run reported 2",
    ):
        assert label in stdout, label


# --------------------------------------------------------------------------- The control: these goldens can actually fail ---------------------------------------------------------------------------


# A throwaway entry point that loads the real proxy and silently drops ONE of its checks. See the control below.
PLANT = """import sys

from rediacc_ci.core import proxyx
from rediacc_ci.proxies import docker_prepull as subject

_real = proxyx.Proxy.expect_contains


def _skip_the_last_check(self, haystack, needle, label):
    if label == "the two-spec run reported 2":
        return None
    return _real(self, haystack, needle, label)


proxyx.Proxy.expect_contains = _skip_the_last_check
raise SystemExit(subject.main(sys.argv[1:]))
"""


@needs_docker
def test_a_planted_dropped_check_is_caught(tmp_path: pathlib.Path) -> None:
    """THE CONTROL ON THE GOLDENS, aimed at the failure mode a proxy actually has.

    A proxy does not crash when it stops testing something; it prints one line fewer and a smaller count, and both of those read like a healthy run to anyone not comparing them with yesterday's. The plant removes the check that the two-spec call reported two images, which is the one that would catch a subject silently dropping a spec, and the recording notices because the label is
    gone and the summary says eight checks rather than nine.

    THE PLANT IS A WRAPPER, NOT A COPY OF THE FILE, because the mutation belongs to the proxy LIBRARY rather than to any one line of the proxy: it replaces `proxyx.Proxy.expect_contains` in its own process and leaves every file on disk untouched.
    """
    mutant = tmp_path / "mutant.py"
    mutant.write_text(PLANT, encoding="utf-8")

    want = recorded("a-full-run")
    assert "9 check(s) passed" in want[1], "the recorded corpus moved"
    planted = diff.bash_streams(
        "python3 %s" % mutant,
        env=diff.env_for(PYTHONPATH=".ci", PYTHONDONTWRITEBYTECODE="1"),
        timeout=180,
    )
    assert planted[0] == 0, "the plant was supposed to stay green, just quieter"
    assert "8 check(s) passed" in planted[1], "the plant did not drop a check"
    assert "the two-spec run reported 2" not in planted[1]
    assert planted[1] != want[1]

    compare("a-full-run")
