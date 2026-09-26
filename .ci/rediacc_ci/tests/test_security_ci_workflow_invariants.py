"""`rediacc_ci.security.ci_workflow_invariants`, driven against the bytes its bash twin printed.

THE TWIN HAS BEEN DELETED. While both copies existed this file ran `.ci/scripts/security/check-ci-workflow-invariants.sh` and the port over the same workflow and compared exit code, stdout and stderr byte for byte, with one exemption. The ledger `.ci/shadow/w7p6-check-ci-workflow-invariants.observations.jsonl` holds 5 rows of that comparison.

Byte equality was affordable because 103 of the twin's 224 lines were ALREADY Python inside a `python3 - <<'PY'` heredoc (`:66-168`), so anything short of it would have been a transcription error rather than a legitimate rewrite. Every fixture case now compares against `goldens/ci-workflow-invariants/`, which holds the twin's OWN recorded bytes, captured on its last day in the
tree, and each golden's provenance header carries the blob sha, so `git cat-file -p <sha>` still yields the program that printed them.

WHICH CASES ARE RECORDED, AND WHICH ARE DELIBERATELY NOT. Every case that drives a SYNTHETIC fixture has a golden, because its input is a constant in this file and its output is therefore reproducible for as long as the constant is. The two cases that drive the REAL `.github/workflows/ci.yml` have none, and must not: those bytes are a function of a live tracked file that
legitimately changes, so freezing them would bake today's workflow into a golden and red this suite on the next unrelated workflow edit. They survive as port-only assertions about the real tree, which is what they were really claiming all along: the real file is green, the verdict line is present, and the blind-spot warning is printed.

TWO STREAMS AND NOTHING ELSE, which is the whole observable surface here. The subject reads one file and writes a verdict; it creates nothing, it touches no remote, and there is no third artifact for a section to carry.

NO FAKES, AND THAT WAS A MEASURED CLAIM RATHER THAN AN ASSUMPTION. The twin shelled out to exactly one binary, `python3`, and only to run its heredoc; there was no `yq`, no `jq`, no `gh`, no network:

    $ grep -nE '(^|[^a-z-])(yq|jq|gh|curl|wget|git) ' \\
        .ci/scripts/security/check-ci-workflow-invariants.sh
    (no output)

So every recorded case drives the subject over a fixture through `$WORKFLOW_FILE`, the seam the twin already exposed for its own gate test.

WHY A BASELINE-GREEN FIXTURE EXISTS. Without it a case asserting exit 1 proves nothing, because the fixture might have been red for a reason the case did not plant. `the-baseline-fixture` is the recording every other fixture case leans on, and it is asserted green first.

ONE CASE IS COMPARED BY SHAPE, and it has to be. A scalar document makes `(doc or {}).get("jobs")` raise AttributeError; the twin's heredoc printed a traceback naming `<stdin>` and the port prints one naming its own file.

Exit code and stdout are still compared byte for byte, and the stderr with the traceback elided, so the INVARIANT-FAIL line, its `(exit 1)` and their ORDER relative to the traceback are all still asserted.

WHAT IS MASKED, and it is two paths. The case's temporary directory holds the fixture whose name the subject quotes in almost every message, and it is rebuilt under a different name every run, so it becomes `<work>`; the checkout root becomes `<repo>`, because the port's traceback names its own absolute path. Nothing else is touched.

THE CONTROL IS A WRAPPER PLANT that imports the tracked module and replaces one exported function in its own process, rather than editing a copy of the file. The mutation it wants is the removal of one finding KIND, which is a change to a return value rather than to a line of text, and the file on disk is never written to at all.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import typing

import pytest

from rediacc_ci import paths
from rediacc_ci.security import ci_workflow_invariants
from rediacc_ci.tests import differential, frozen

if typing.TYPE_CHECKING:  # pragma: no cover - annotations only
    import pathlib

ROOT = paths.repo_root()
PORT = ROOT / ".ci/rediacc_ci/security/ci_workflow_invariants.py"
SLUG = "ci-workflow-invariants"

BASH = "/bin/bash"
PYTHON = os.path.realpath(sys.executable)

# A workflow that satisfies every invariant. Every red case below is this file
# with ONE thing broken, so the diff between a case and this constant is exactly
# the defect under test.
BASELINE = """name: ci
on: push
jobs:
  initialize:
    runs-on: ubuntu-latest
    outputs:
      channel: ${{ steps.decide.outputs.channel }}
      skip_release: ${{ steps.decide.outputs.skip_release }}
    steps:
      - id: decide
        run: echo decided
  validate-install:
    needs: initialize
    if: needs.initialize.outputs.skip_release != 'true'
    runs-on: ubuntu-latest
    steps:
      - run: echo install
  validate-promote:
    needs: initialize
    if: needs.initialize.outputs.skip_release != 'true'
    runs-on: ubuntu-latest
    steps:
      - run: echo promote
  stage-artifacts:
    needs: initialize
    uses: ./.github/workflows/cd-stage.yml
    with:
      skip_release: ${{ needs.initialize.outputs.skip_release }}
  channel-consumer:
    needs: initialize
    if: needs.initialize.outputs.channel != ''
    uses: ./.github/workflows/cd-validate.yml
    with:
      docker_tag: ${{ needs.initialize.outputs.channel }}
  finalize-release-sentinel:
    needs: stage-artifacts
    runs-on: ubuntu-latest
    steps:
      - run: echo finalize
"""


# The same document as `BASELINE`, as the dict PyYAML would produce. Kept as a literal because pytest's interpreter here has no PyYAML (the two children run under the system python3, which does), and `test_the_literal_document_matches_the_baseline_yaml` proves the two agree rather than leaving a second source of truth to rot.
CONFORMANT: dict = {
    "name": "ci",
    # NO `on:` KEY HERE, and that is not an oversight. PyYAML implements YAML 1.1, where the bare word `on` is a BOOLEAN, so `yaml.safe_load("on: push")` returns `{True: "push"}` rather than `{"on": "push"}`.
    #
    # Neither implementation reads the key, so the omission changes no verdict, and `test_the_literal_document_matches_the_baseline_yaml` compares the `jobs` subtree for exactly this reason.
    "jobs": {
        "initialize": {
            "runs-on": "ubuntu-latest",
            "outputs": {
                "channel": "${{ steps.decide.outputs.channel }}",
                "skip_release": "${{ steps.decide.outputs.skip_release }}",
            },
            "steps": [{"id": "decide", "run": "echo decided"}],
        },
        "validate-install": {
            "needs": "initialize",
            "if": "needs.initialize.outputs.skip_release != 'true'",
            "runs-on": "ubuntu-latest",
            "steps": [{"run": "echo install"}],
        },
        "validate-promote": {
            "needs": "initialize",
            "if": "needs.initialize.outputs.skip_release != 'true'",
            "runs-on": "ubuntu-latest",
            "steps": [{"run": "echo promote"}],
        },
        "stage-artifacts": {
            "needs": "initialize",
            "uses": "./.github/workflows/cd-stage.yml",
            "with": {"skip_release": "${{ needs.initialize.outputs.skip_release }}"},
        },
        "channel-consumer": {
            "needs": "initialize",
            "if": "needs.initialize.outputs.channel != ''",
            "uses": "./.github/workflows/cd-validate.yml",
            "with": {"docker_tag": "${{ needs.initialize.outputs.channel }}"},
        },
        "finalize-release-sentinel": {
            "needs": "stage-artifacts",
            "runs-on": "ubuntu-latest",
            "steps": [{"run": "echo finalize"}],
        },
    },
}


def without(fragment: str, count: int = 1) -> str:
    """BASELINE with one fragment removed, refusing to be a no-op.

    A red case whose substitution silently missed still runs, still compares two identical outputs and still passes, while asserting nothing.
    """
    out = BASELINE.replace(fragment, "", count)
    assert out != BASELINE, "the removal of %r matched nothing" % fragment
    return out


def instead(before: str, after: str, count: int = 1) -> str:
    out = BASELINE.replace(before, after, count)
    assert out != BASELINE, "the substitution %r -> %r matched nothing" % (before, after)
    return out


# name -> the fixture body (None means the file is never written), and the flags for the two cases that need something other than a plain run
CASE_KW: dict[str, dict[str, typing.Any]] = {
    "the-baseline-fixture": {"body": BASELINE},
    "a-channel-docker-tag-without-the-guard": {
        "body": without("    if: needs.initialize.outputs.channel != ''\n")
    },
    "a-double-quoted-guard": {
        "body": instead(
            "if: needs.initialize.outputs.channel != ''",
            'if: needs.initialize.outputs.channel != ""',
        )
    },
    "a-whitespace-free-guard": {
        "body": instead(
            "if: needs.initialize.outputs.channel != ''",
            "if: needs.initialize.outputs.channel!=''",
        )
    },
    "no-channel-derived-docker-tag": {
        "body": instead("docker_tag: ${{ needs.initialize.outputs.channel }}", "docker_tag: x")
    },
    "a-workflow-with-no-jobs": {"body": "name: empty\non: push\njobs: {}\n"},
    "a-jobs-key-that-is-a-list": {"body": "name: x\non: push\njobs:\n  - a\n  - b\n"},
    "a-missing-workflow-file": {"body": None},
    "a-stager-that-does-not-pass-skip-release": {
        "body": instead(
            "    with:\n      skip_release: ${{ needs.initialize.outputs.skip_release }}\n",
            "    with:\n      other: 1\n",
        )
    },
    "an-initialize-without-the-skip-release-output": {
        "body": without("      skip_release: ${{ steps.decide.outputs.skip_release }}\n")
    },
    "a-stager-with-no-initialize-job": {"body": instead("  initialize:\n", "  bootstrap:\n")},
    "a-sentinel-owner-with-no-stager": {
        "body": instead("uses: ./.github/workflows/cd-stage.yml", "uses: ./other.yml")
    },
    "a-missing-validator-job": {"body": instead("  validate-promote:\n", "  validate-later:\n")},
    "a-validator-that-does-not-gate": {
        "body": instead(
            "  validate-install:\n    needs: initialize\n"
            "    if: needs.initialize.outputs.skip_release != 'true'\n",
            "  validate-install:\n    needs: initialize\n    if: always()\n",
        )
    },
    "a-sentinel-that-decides-a-second-time": {
        "body": instead(
            "      - run: echo finalize\n",
            "      - run: dispatch-release.sh --decide-only\n",
        )
    },
    "an-unparseable-workflow": {"body": "jobs:\n  a: [unclosed\n"},
    "a-scalar-document": {"body": "just a string\n"},
    "no-python3-on-the-path": {"body": BASELINE, "no_python": True},
    "colour-on-a-terminal": {
        "body": without("    if: needs.initialize.outputs.channel != ''\n"),
        "tty": True,
    },
}

CASES = tuple(CASE_KW)

# The one case whose stderr carries a traceback naming the implementation's own file. Compared by shape, in its own test.
DIVERGENT = ("a-scalar-document",)


def env_for(**extra: str) -> dict[str, str]:
    """REPLACES the caller's environment; see `differential.BASE_ENV`.

    `REDIACC_CI_ROOT` is deliberately absent: it is the one seam the port has and the twin did not.
    """
    env = differential.env_for(
        PYTHONPATH=str(ROOT / ".ci"),
        PYTHONDONTWRITEBYTECODE="1",
    )
    env.update(extra)
    return env


def path_without_python(tmp_path: pathlib.Path) -> pathlib.Path:
    """A scratch bin holding every tool on PATH EXCEPT any python interpreter.

    Built by mirroring rather than by naming the handful of tools the twin needed, because that list was not stable: the first version of this case symlinked only `dirname` and the twin then died on `uname`, which `common.sh:64` calls at SOURCE time. A mirror cannot go stale that way, and the thing under test, that python3 is not resolvable, is stated once.
    """
    bindir = tmp_path / "nopython-bin"
    bindir.mkdir(parents=True, exist_ok=True)
    for entry in os.environ.get("PATH", "").split(os.pathsep):
        if not entry or not os.path.isdir(entry):
            continue
        for name in os.listdir(entry):
            if name.startswith(("python", "uv")):
                continue
            target = bindir / name
            if target.exists() or target.is_symlink():
                continue
            os.symlink(os.path.join(entry, name), target)
    assert not (bindir / "python3").exists(), "the scratch PATH still resolves python3"
    return bindir


def run(subject: pathlib.Path, tmp_path: pathlib.Path, name: str) -> tuple[int, str, str]:
    """One subject, once, over this case's own fixture."""
    kw = CASE_KW[name]
    tmp_path.mkdir(parents=True, exist_ok=True)
    workflow = tmp_path / "wf.yml"
    if kw["body"] is not None:
        workflow.write_text(kw["body"], encoding="utf-8")
    env = env_for(WORKFLOW_FILE=str(workflow))
    if kw.get("no_python"):
        env["PATH"] = str(path_without_python(tmp_path))
    runner = BASH if subject.suffix == ".sh" else PYTHON

    def mask(text: str) -> str:
        return text.replace(str(tmp_path), "<work>").replace(str(ROOT), "<repo>")

    if kw.get("tty"):
        # `[[ -t 2 ]] && [[ -z "${NO_COLOR:-}" ]]` (common.sh:18), the branch a human sees. Off a tty every other case proves only the uncoloured half.
        code, out, err = differential.bash_streams(
            "%s %s" % ("bash" if subject.suffix == ".sh" else "python3", subject),
            env=env,
            cwd=str(ROOT),
            tty="stderr",
        )
        return code, mask(out), mask(err)

    proc = subprocess.run(
        [runner, str(subject)],
        env=env,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    return proc.returncode, mask(proc.stdout), mask(proc.stderr)


def render(code: int, stdout: str, stderr: str) -> str:
    return frozen.render(code, stdout, stderr)


def recorded(name: str) -> tuple[int, str, str]:
    text = frozen.read(SLUG, name)
    exit_line, rest = text.split("\n", 1)
    stdout, stderr = rest.split("--- stdout ---\n", 1)[1].split("--- stderr ---\n", 1)
    return int(exit_line.removeprefix("exit: ")), stdout, stderr


def port(tmp_path: pathlib.Path, name: str) -> tuple[int, str, str]:
    return run(PORT, tmp_path / name, name)


def compare(tmp_path: pathlib.Path, name: str) -> tuple[int, str, str]:
    want = recorded(name)
    got = port(tmp_path, name)
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


def assert_red(result: tuple[int, str, str], token: str) -> None:
    """Anti-vacuity for one recording: the twin really did fail, for the reason meant.

    Two implementations that both print nothing and both exit 0 agree perfectly and prove nothing; `scripts/lib/shadow-gate.ts` calls that VACUOUS_BOTH_EMPTY and refuses it, and this is the same refusal against a recording.
    """
    assert result[0] == 1, "expected the twin to fail, got exit %s\n%s" % (result[0], result[2])
    assert token in result[2], "expected %r in the recorded stderr, got:\n%s" % (token, result[2])


@pytest.mark.parametrize("name", [c for c in CASES if c not in DIVERGENT])
def test_port_matches_the_twins_recorded_output(tmp_path: pathlib.Path, name: str) -> None:
    compare(tmp_path, name)


def test_every_case_has_a_golden_and_no_golden_is_orphaned() -> None:
    """ANTI-VACUITY on the corpus: a case whose golden vanished would pass by never being compared, and a golden nothing reads is a recording of a case that stopped running."""
    frozen.assert_corpus(SLUG, set(CASES))


# --------------------------------------------------------------------------- The real repository, deliberately NOT recorded ---------------------------------------------------------------------------


def test_the_real_workflow_is_green_under_the_port() -> None:
    """The clean-tree case, over the real `.github/workflows/ci.yml`.

    NOT A GOLDEN, and that is the point: the real file legitimately changes, so freezing its bytes would red this suite on the next unrelated workflow edit. What is asserted is what the differential was really claiming here, that the live file passes and the verdict is printed rather than two empty streams agreeing.
    """
    proc = subprocess.run(
        [PYTHON, str(PORT)],
        env=env_for(),
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    assert proc.returncode == 0, "the real ci.yml is not green:\n%s" % proc.stderr
    assert "ci workflow invariants hold" in proc.stderr
    assert "Blind spot: this reads ci.yml only" in proc.stderr


def test_an_empty_workflow_file_falls_back_to_the_real_default() -> None:
    """`${WORKFLOW_FILE:-...}`, exercised with the variable EXPORTED EMPTY.

    An empty value must fall back, not resolve to `<root>`, which is what `os.environ.get(name, default)` would have done and is the trap this case exists to hold shut. Not recorded for the same reason as the case above: the fallback IS the real workflow.
    """
    proc = subprocess.run(
        [PYTHON, str(PORT)],
        env=env_for(WORKFLOW_FILE=""),
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
    assert "ci workflow invariants hold" in proc.stderr


# --------------------------------------------------------------------------- What the recordings say ---------------------------------------------------------------------------


def test_the_baseline_fixture_is_green() -> None:
    """THE CONTROL FOR EVERY OTHER FIXTURE CASE, and the NEGATIVE selftest direction."""
    code, _, stderr = recorded("the-baseline-fixture")
    assert code == 0, "the baseline fixture is not green:\n%s" % stderr


def test_a_channel_docker_tag_job_without_the_guard() -> None:
    assert_red(recorded("a-channel-docker-tag-without-the-guard"), "channel-as-docker-tag: job")


def test_the_two_accepted_guard_spellings() -> None:
    """`cond.replace('"', "'")` and the space-stripped form. THE POSITIVE controls: without them the acceptance branch is never exercised and a port that accepted nothing would still satisfy every red case."""
    for name in ("a-double-quoted-guard", "a-whitespace-free-guard"):
        code, _, stderr = recorded(name)
        assert code == 0, "%s should be accepted:\n%s" % (name, stderr)


def test_no_channel_derived_docker_tag_is_a_vacuity_failure() -> None:
    assert_red(recorded("no-channel-derived-docker-tag"), "no-candidates: no job in")


def test_a_workflow_with_no_usable_jobs() -> None:
    """Both arms of the same guard: an empty mapping and a list."""
    assert_red(recorded("a-workflow-with-no-jobs"), "no-jobs:")
    assert_red(recorded("a-jobs-key-that-is-a-list"), "no-jobs:")


def test_a_missing_workflow_file_is_never_green() -> None:
    assert_red(recorded("a-missing-workflow-file"), "workflow-missing: no file at")


def test_the_skip_release_family() -> None:
    """Four findings that all say the release path can be skipped without the gate noticing, each planted on its own."""
    assert_red(
        recorded("a-stager-that-does-not-pass-skip-release"),
        "skip-release: job 'stage-artifacts' does not pass",
    )
    assert_red(
        recorded("an-initialize-without-the-skip-release-output"),
        "job 'initialize' declares no `skip_release` output",
    )
    assert_red(
        recorded("a-stager-with-no-initialize-job"), "expected job 'initialize' is absent from"
    )
    assert_red(
        recorded("a-sentinel-owner-with-no-stager"),
        "expected job '<no job uses cd-stage.yml>' is absent from",
    )


def test_the_validator_family() -> None:
    assert_red(
        recorded("a-missing-validator-job"), "expected job 'validate-promote' is absent from"
    )
    assert_red(
        recorded("a-validator-that-does-not-gate"), "validator 'validate-install' does not gate on"
    )


def test_the_sentinel_deciding_a_second_time() -> None:
    assert_red(
        recorded("a-sentinel-that-decides-a-second-time"),
        "still runs `dispatch-release.sh --decide-only`",
    )


def test_an_unparseable_workflow_is_never_green() -> None:
    """A SETUP exit 2 from the heredoc, which bash then reported as exit 1.

    Both the `SETUP: ... does not parse as YAML: ...` line (from PyYAML, so both sides quote the same message) and the `(exit 2)` in the INVARIANT-FAIL line are recorded, which is what pins the twin's 2-becomes-1 translation.
    """
    code, _, stderr = recorded("an-unparseable-workflow")
    assert code == 1
    assert "analysis of" in stderr
    assert "(exit 2)" in stderr
    assert "SETUP:" in stderr


def test_missing_python3_is_a_setup_error() -> None:
    """Exit 2, the only exit-2 path either side has.

    Driven with a PATH mirroring every tool except an interpreter, and with both children started by absolute path so removing python3 from PATH does not remove the ability to RUN the port.
    """
    code, _, stderr = recorded("no-python3-on-the-path")
    assert code == 2, "the twin did not take the setup-error path:\n%s" % stderr
    assert "python3 is required to parse" in stderr


def test_colour_is_emitted_when_stderr_is_a_terminal() -> None:
    """The branch a human sees. `CI` is left UNSET: `rediacc_ci.log` also disables colour on `CI=true` and common.sh did not, which is `log.py`'s documented deliberate divergence and is not this gate's subject."""
    stderr = recorded("colour-on-a-terminal")[2]
    assert differential.escape_bytes(stderr) > 0, "the twin printed no colour on a tty"
    assert "channel-as-docker-tag" in stderr


# --------------------------------------------------------------------------- The one divergence, pinned rather than papered over ---------------------------------------------------------------------------


def test_a_scalar_document_crashes_the_analysis_on_both_sides(tmp_path: pathlib.Path) -> None:
    """THE ONE EXEMPTED CASE, and the exemption is one block of text, not a rule.

    `(doc or {}).get("jobs")` on a string raises AttributeError. The twin's heredoc printed a traceback naming `<stdin>` and the port prints one naming its own file. Exit code and stdout are still compared byte for byte, and the stderr with the traceback elided, so the INVARIANT-FAIL line, its `(exit 1)` and their ORDER relative to the traceback are all still asserted.
    """
    name = "a-scalar-document"
    want = recorded(name)
    got = port(tmp_path, name)
    assert_red(want, "analysis of")
    assert "(exit 1)" in want[2]
    assert "AttributeError" in want[2], "the twin did not crash the way this case needs"
    assert "AttributeError" in got[2], "the port did not crash the way the twin did"
    assert got[0] == want[0]
    assert got[1] == want[1]
    # GREEDY to the LAST `AttributeError:` line, not the first: the port's own source line is echoed into its traceback, and a non-greedy match stopped at any mention of the name inside it. That is a trap in the TEST rather than in either implementation, and it fired once while this file was first being written.
    pattern = re.compile(r"(?s)Traceback \(most recent call last\).*\nAttributeError[^\n]*\n")
    assert pattern.sub("<TRACEBACK>\n", got[2]) == pattern.sub("<TRACEBACK>\n", want[2])
    assert "<TRACEBACK>" in pattern.sub("<TRACEBACK>\n", want[2]), "the elision matched nothing"


# --------------------------------------------------------------------------- The exported helpers, driven directly (the selftest half) ---------------------------------------------------------------------------


def test_the_literal_document_matches_the_baseline_yaml(tmp_path: pathlib.Path) -> None:
    """CONFORMANT and BASELINE are two spellings of one document; prove it.

    Parsed by the SYSTEM python3 in a subprocess, because that is the interpreter that has PyYAML and is also the one the subject runs under. Without this the literal is a second source of truth that drifts the first time BASELINE is edited, and every helper test below it would keep passing while asserting things about a document nothing else uses.
    """
    program = (
        "import io,json,sys,yaml;"
        "print(json.dumps(yaml.safe_load(io.open(sys.argv[1],encoding='utf-8'))['jobs']))"
    )
    path = tmp_path / "baseline.yml"
    path.write_text(BASELINE, encoding="utf-8")
    proc = subprocess.run(
        ["python3", "-c", program, str(path)],
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    )
    assert json.loads(proc.stdout) == CONFORMANT["jobs"]


def test_analyse_reports_nothing_for_a_conformant_document() -> None:
    """The NEGATIVE direction: a gate with only positive controls flags everything.

    The document is a LITERAL dict rather than `yaml.safe_load(BASELINE)`, because PyYAML is importable by the system `python3` that runs the subject and is NOT importable by the uv-managed interpreter that runs pytest. A test that imported it would be a test that skipped, and a skipped test reads exactly like a passing one in the summary.
    """
    assert ci_workflow_invariants.analyse(CONFORMANT) == []


def test_analyse_names_every_kind_it_can_emit() -> None:
    """`KINDS` must stay the real vocabulary, or the constant is decoration.

    Derived from the module's own translation table rather than restated, so a kind added to `analyse` with no `message_for` arm is caught here.
    """
    for kind in ci_workflow_invariants.KINDS:
        assert ci_workflow_invariants.message_for(kind, "j", "/w.yml") is not None, (
            "no message arm for kind %r" % kind
        )


def test_message_for_returns_none_on_an_unknown_kind() -> None:
    """The twin's `case` had no default arm, so an unknown kind is a silent skip."""
    assert ci_workflow_invariants.message_for("invented-kind", "j", "/w.yml") is None


def test_analyse_fires_on_a_missing_guard() -> None:
    """The POSITIVE direction, over the same literal document with one key dropped."""
    doc = json.loads(json.dumps(CONFORMANT))
    del doc["jobs"]["channel-consumer"]["if"]
    assert ("ungated", "channel-consumer") in ci_workflow_invariants.analyse(doc)


def test_analyse_orders_its_findings_the_way_the_twin_printed_them() -> None:
    """Order is observable: one line per finding, in stream order.

    `ungated` precedes the skip-release family, which is the heredoc's own print order, and a port that collected findings into a set or sorted them would still satisfy every membership assertion above.
    """
    doc = json.loads(json.dumps(CONFORMANT))
    del doc["jobs"]["channel-consumer"]["if"]
    del doc["jobs"]["stage-artifacts"]["with"]
    kinds = [kind for kind, _name in ci_workflow_invariants.analyse(doc)]
    assert kinds == ["ungated", "skip-release-not-passed"]


# --------------------------------------------------------------------------- The control: these goldens can actually fail ---------------------------------------------------------------------------


# A throwaway entry point that loads the real module, drops one finding KIND from `analyse`, and runs `main`. See the control below.
PLANT = """import sys

from rediacc_ci.security import ci_workflow_invariants as subject

_real = subject.analyse


def _blind_to_ungated(doc):
    return [finding for finding in _real(doc) if finding[0] != "ungated"]


subject.analyse = _blind_to_ungated
raise SystemExit(subject.main(sys.argv[1:]))
"""


def test_a_planted_blind_spot_is_caught(tmp_path: pathlib.Path) -> None:
    """THE CONTROL ON THE GOLDENS, aimed at the worst thing a security gate can do quietly.

    `ungated` is the finding that says a job derives its docker tag from the release channel without guarding on that channel being set. A subject blind to it reports nothing and EXITS 0 on a workflow the recording says is red, which is a gate that passes while the invariant it exists for is broken. The recorded case goes from exit 1 with a named finding to a silent success, so the
    comparison fails on the exit code and on both streams at once.

    THE PLANT IS A WRAPPER, NOT A COPY OF THE FILE. It imports the tracked module and replaces one exported function in its own process, which mutates a return value rather than a line of text and keeps the file on disk untouched.
    """
    original = PORT.read_text(encoding="utf-8")
    assert '"ungated"' in original, "the plant's target moved"

    mutant = tmp_path / "plant" / "mutant.py"
    mutant.parent.mkdir(parents=True)
    mutant.write_text(PLANT, encoding="utf-8")

    name = "a-channel-docker-tag-without-the-guard"
    want = recorded(name)
    assert want[0] == 1, "the recorded corpus moved"
    planted = run(mutant, tmp_path / "planted", name)
    assert planted[0] == 0, "the plant did not blind the subject"
    assert "channel-as-docker-tag" not in planted[2], "the finding survived the plant"
    assert planted != want

    compare(tmp_path / "good", name)
    assert PORT.read_text(encoding="utf-8") == original
