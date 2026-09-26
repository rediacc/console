"""`rediacc_ci.proxies.cli_manifest`, driven against the bytes its bash twin printed.

THE TWIN HAS BEEN DELETED. While both copies existed this file ran `.ci/scripts/test/proxies/proxy-cli-manifest.sh` and the ported proxy and compared the whole `(exit, stdout, stderr)` tuple byte for byte. The ledger `.ci/shadow/w7p6-proxy-cli-manifest.observations.jsonl` holds 5 rows of that comparison.

Both cases now compare against `goldens/proxy-cli-manifest/`, which holds the twin's OWN recorded bytes, captured on its last day in the tree, and each golden's provenance header carries the blob sha.

A PROXY IS A TEST HARNESS, SO ITS OUTPUT IS ITS PRODUCT. It prints one line per check, one summary line and a four-line hazard report, and nothing else: no timestamps, no temporary paths and no process ids, even though it builds a six-binary dist directory in a fresh tmpdir on every run. The one literal `$(mktemp -d)` in the hazard message is prose, not a real path. That is what
makes the bytes freezable at all, and `test_no_recording_carries_a_path` asserts it rather than trusting it.

THE SUBJECT IS THE PORT NOW, ON BOTH SIDES, and the order that got there matters because it is the evidence. `.ci/scripts/build/generate-cli-manifest.sh` was retired in the same wave, and the flip was done in two steps: first only the ported proxy was pointed at `rediacc_ci.build.generate_cli_manifest` while the bash twin still drove the bash subject, and that comparison stayed
byte-identical across all eleven checks, including every emitted sha256 and both channel URL branches; then both proxies were pointed at the port together, the comparison was re-run, and only then was the twin recorded and deleted.

THE HAZARD LINE IS PART OF THE RECORDING, and deliberately so. An input directory with no `.sha256` files makes the subject exit 0 with an empty `binaries` object, which is a publishable release manifest that offers no downloads; the proxy reports that on every run and rules on nothing, because fixing it means changing the subject. A recording is what stops that report going quiet.
"""

from __future__ import annotations

import typing

import pytest

from rediacc_ci import paths
from rediacc_ci.tests import differential as diff
from rediacc_ci.tests import frozen

if typing.TYPE_CHECKING:  # pragma: no cover - annotations only
    import pathlib

ROOT = paths.repo_root()
MODULE = "rediacc_ci.proxies.cli_manifest"
SLUG = "proxy-cli-manifest"

CASE_KW: dict[str, dict[str, typing.Any]] = {
    "the-selftest": {"args": ["--selftest"]},
    "a-full-run": {"args": []},
}

CASES = tuple(CASE_KW)


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
def test_port_matches_the_twins_recorded_output(name: str) -> None:
    compare(name)


def test_every_case_has_a_golden_and_no_golden_is_orphaned() -> None:
    """ANTI-VACUITY on the corpus: a case whose golden vanished would pass by never being compared, and a golden nothing reads is a recording of a case that stopped running."""
    frozen.assert_corpus(SLUG, set(CASES))


def test_no_recording_carries_a_path() -> None:
    """The no-mask claim in the module docstring, asserted rather than trusted.

    The one exception is spelled out rather than waved through: the hazard report ends with a reproduce command whose `--output /tmp/m.json` is a LITERAL an operator is meant to type, not a path this run used. Every other `/tmp/` in a recording would be a real temporary directory, which is why the count is compared rather than the substring merely being allowed.
    """
    for name in CASES:
        for stream in recorded(name)[1:]:
            assert str(ROOT) not in stream, name
            assert stream.count("/tmp/") == stream.count("--output /tmp/m.json"), name


# --------------------------------------------------------------------------- What the recordings say ---------------------------------------------------------------------------


def test_the_selftest_is_green() -> None:
    """`--selftest` exercises the proxy library itself, with no fixture and no subject."""
    code, stdout, _ = recorded("the-selftest")
    assert code == 0
    assert stdout.strip() != "", "the selftest recorded nothing at all"


def test_the_full_run_passes_eleven_checks_and_names_three_requirements() -> None:
    """The counts are the summary an operator reads, so they are asserted rather than the whole line being taken on trust."""
    code, stdout, _ = recorded("a-full-run")
    assert code == 0
    assert "11 check(s) passed, 3 requirement(s) present" in stdout


def test_the_recorded_run_names_the_port_as_its_subject() -> None:
    """The header says what the proxy is a stand-in FOR, and after the flip that is the port rather than a `.sh` that no longer exists. A recording made before the flip would have frozen a dead path into the proxy's own output, and the hazard message would have told a reader to reproduce it with a command that cannot run."""
    stdout = recorded("a-full-run")[1]
    assert (
        "proxy cli-manifest: local stand-in for .ci/rediacc_ci/build/generate_cli_manifest.py"
        in stdout
    )
    assert "python3 .ci/rediacc_ci/build/generate_cli_manifest.py --version 9.9.9" in stdout


def test_every_check_the_recording_carries() -> None:
    """The labels. A proxy that quietly stopped running one of its checks would still print a summary and still exit 0; the only thing that notices is the list."""
    stdout = recorded("a-full-run")[1]
    for label in (
        "generate_cli_manifest.py exited 0 over the fixture dist dir",
        "the manifest exists and parses as JSON",
        "binaries has exactly the 5 well-formed keys",
        "the malformed sidecar was skipped, not emitted",
        "every emitted sha256 equals the fixture's own sha256sum output",
        "a release channel (edge) bakes the immutable v-version path",
        "the URL names the binary it describes",
        "a non-release channel points at its own channel path instead",
        "version is carried through verbatim",
        "a missing --version is refused",
        "an unknown flag is refused",
    ):
        assert label in stdout, label


def test_the_known_hazard_is_reported_every_time() -> None:
    """Not ruled on, and it must never go quiet: an input directory with no `.sha256` files yields a manifest with no binaries and exit 0, and a release published from it offers no downloads at all."""
    stdout = recorded("a-full-run")[1]
    assert "KNOWN HAZARD in the subject, reported not enforced" in stdout
    assert "a manifest with 0 binaries" in stdout


# --------------------------------------------------------------------------- The control: these goldens can actually fail ---------------------------------------------------------------------------


# A throwaway entry point that loads the real proxy and silently drops ONE of its checks. See the control below.
PLANT = """import sys

from rediacc_ci.core import proxyx
from rediacc_ci.proxies import cli_manifest as subject

_real = proxyx.Proxy.ok


def _skip_one_check(self, label):
    if label == "the malformed sidecar was skipped, not emitted":
        return None
    return _real(self, label)


proxyx.Proxy.ok = _skip_one_check
raise SystemExit(subject.main(sys.argv[1:]))
"""


def test_a_planted_dropped_check_is_caught(tmp_path: pathlib.Path) -> None:
    """THE CONTROL ON THE GOLDENS, aimed at the failure mode a proxy actually has.

    A proxy does not crash when it stops testing something; it prints one line fewer and a smaller count, and both of those read like a healthy run to anyone not comparing them with yesterday's. The plant removes the check that a malformed sidecar hash is SKIPPED rather than emitted, which is the one standing between a truncated checksum and every `rdc update` that would then
    refuse the binary it downloaded, and the recording notices because the label is gone and the summary says ten checks rather than eleven.

    THE PLANT IS A WRAPPER, NOT A COPY OF THE FILE, because the mutation belongs to the proxy LIBRARY rather than to any one line of the proxy: it replaces `proxyx.Proxy.expect_contains` in its own process and leaves every file on disk untouched.
    """
    mutant = tmp_path / "mutant.py"
    mutant.write_text(PLANT, encoding="utf-8")

    want = recorded("a-full-run")
    assert "11 check(s) passed" in want[1], "the recorded corpus moved"
    planted = diff.bash_streams(
        "python3 %s" % mutant,
        env=diff.env_for(PYTHONPATH=".ci", PYTHONDONTWRITEBYTECODE="1"),
        timeout=180,
    )
    assert planted[0] == 0, "the plant was supposed to stay green, just quieter"
    assert "10 check(s) passed" in planted[1], "the plant did not drop a check"
    assert "the malformed sidecar was skipped, not emitted" not in planted[1]
    assert planted[1] != want[1]

    compare("a-full-run")
