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
import shutil
import subprocess
import sys
import typing

import pytest

from rediacc_ci import paths, workflows
from rediacc_ci.quality import workflows as quality_workflows
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
    # The real tree runs the release-order phase too, so the ci.yml blind spot names its phase; the fixture goldens keep the twin's "this reads ci.yml only".
    assert "Blind spot: the ci.yml phase reads ci.yml only" in proc.stderr
    assert "release order holds: init step 'Create version tag' (needs: nothing)" in proc.stderr


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


# ---- root-ancestor-conditional (added after the twin's deletion; no differential) ----------------------------------


def _root_kinds(jobs: dict) -> list[tuple[str, str]]:
    return [
        f
        for f in ci_workflow_invariants.analyse({"jobs": jobs})
        if f[0] == "root-ancestor-conditional"
    ]


def test_a_conditional_ancestor_of_initialize_is_refused():
    """PR #597's run 37465283674: `duplicate-run` ran on push only, skipped on the PR, and every implicit-success job downstream of a green `initialize` skipped with it."""
    jobs = {
        "duplicate-run": {"if": "github.event_name == 'push'", "runs-on": "x"},
        "initialize": {"needs": ["duplicate-run"], "if": "${{ !cancelled() }}"},
        "run-sh-tests": {"needs": ["initialize"], "if": "x != 'y'"},
    }
    assert _root_kinds(jobs) == [("root-ancestor-conditional", "duplicate-run")]


def test_a_transitive_ancestor_is_reached_and_a_string_needs_is_read():
    jobs = {
        "a": {"if": "false"},
        "b": {"needs": "a"},
        "initialize": {"needs": ["b"]},
    }
    assert _root_kinds(jobs) == [("root-ancestor-conditional", "a")]


def test_unconditional_ancestors_and_conditional_descendants_pass():
    jobs = {
        "duplicate-run": {"runs-on": "x"},
        "initialize": {"needs": "duplicate-run", "if": "${{ !cancelled() }}"},
        "later": {"needs": ["initialize"], "if": "github.event_name == 'push'"},
    }
    assert _root_kinds(jobs) == []


# ---- the release-order phase (PLAN-cd-errors-in-ci W5 + W4 pins; added after the twin, no differential) ----------
#
# CD run 37749637824 (v2.2.0): ci.yml sealed cli/v2.2.0/.released, cd-v2's post-publish install validation went red on a Rocky 9 DNF stall, and `tag-and-release`, the only job that created the git tag, was skipped. The pure cases below drive `analyse_release` over literal dicts in both directions; the subprocess cases drive the REAL files, including the real pre-fix cd-v2.yml.

# The last commit whose cd-v2.yml carried the tag inside `tag-and-release`, behind validate-install-published and gated off on retry_mode. A full sha so it cannot become ambiguous.
PRE_FIX_CD_COMMIT = "0e6af2d1cb918135c79c057ee9d29b5dfb276af1"

TAG_RUN = 'git -c user.name="$N" tag -a "v${VERSION}" -m "v${VERSION}" "$CI_SHA"\ngit push origin "v${VERSION}"\n'
PERMS_RUN = (
    'case "$preset" in\n'
    "  readonly)\n"
    '    echo "perm-contents=read" >> "$GITHUB_OUTPUT"\n'
    "    ;;\n"
    "  cd)\n"
    '    echo "perm-contents=write" >> "$GITHUB_OUTPUT"\n'
    "    # perm-workflows=write is what this comment is about\n"
    '    echo "perm-workflows=write" >> "$GITHUB_OUTPUT"\n'
    "    ;;\n"
    "esac\n"
)


def release_trio() -> tuple[dict, dict, dict]:
    """A conformant (ci, cd, action) triple; every red case below breaks exactly one thing in a fresh copy."""
    ci = {
        "jobs": {
            "finalize-release-sentinel": {
                "steps": [
                    {"name": "Refuse", "if": "G", "run": "python3 -m rediacc_ci.ci.sibling_runs"},
                    {
                        "name": "Seal",
                        "if": "G",
                        "run": "python3 -m rediacc_ci.deploy.write_release_sentinel",
                    },
                    {
                        "name": "Dispatch",
                        "if": "G",
                        "run": "python3 -m rediacc_ci.ci.dispatch_release",
                    },
                ]
            }
        }
    }
    cd = {
        "permissions": {},
        "jobs": {
            "init": {
                "permissions": {"contents": "read", "actions": "read"},
                "steps": [
                    {"uses": "actions/checkout@abc", "with": {"persist-credentials": False}},
                    {
                        "uses": "./.github/actions/app-token",
                        "id": "app-token",
                        "with": {"preset": "cd"},
                    },
                    {
                        "uses": "actions/checkout@abc",
                        "with": {"token": "${{ steps.app-token.outputs.token }}"},
                    },
                    {
                        "name": "Create version tag",
                        "if": "steps.skip-check.outputs.workers_only != 'true'",
                        "run": TAG_RUN,
                    },
                ],
            },
            "publish": {
                "needs": ["init"],
                "permissions": {"contents": "read"},
                "steps": [{"run": "echo publish"}],
            },
            "validate": {
                "needs": ["init", "publish"],
                "uses": "./.github/workflows/ct-install-methods.yml",
            },
            "tag-and-release": {
                "needs": ["init", "publish", "validate"],
                "if": "success() && needs.init.outputs.workers_only != 'true'",
                "permissions": {"contents": "read"},
                "steps": [{"run": "python3 -m rediacc_ci.release.tag_submodules"}],
            },
        },
    }
    action = {
        "runs": {
            "steps": [
                {"id": "perms", "run": PERMS_RUN},
                {
                    "id": "token",
                    "uses": "actions/create-github-app-token@abc",
                    "with": {"permission-workflows": "${{ steps.perms.outputs.perm-workflows }}"},
                },
            ]
        }
    }
    return ci, cd, action


def release_kinds(ci: dict, cd: dict, action: dict) -> list[tuple[str, str]]:
    return ci_workflow_invariants.analyse_release(ci, cd, action)[0]


def test_a_conformant_release_trio_is_clean_and_reports_its_shape() -> None:
    """The NEGATIVE direction: without it every red case below could be red for a reason it did not plant."""
    findings, shape = ci_workflow_invariants.analyse_release(*release_trio())
    assert findings == []
    assert shape == {"jobs": 4, "pushes": 1, "tag": [("init", "Create version tag", [])]}


def test_the_pre_fix_shape_tag_behind_validation_and_off_on_retry_is_refused() -> None:
    """The 2026-10-08 graph, as a literal: the tag step lives in tag-and-release, which needs validation and skips on retry_mode."""
    ci, cd, action = release_trio()
    tag_step = cd["jobs"]["init"]["steps"].pop()
    tar = cd["jobs"]["tag-and-release"]
    tar["if"] = "success() && needs.init.outputs.retry_mode != 'true'"
    tar["steps"] = [*cd["jobs"]["init"]["steps"], {**tag_step, "if": None}]
    assert release_kinds(ci, cd, action) == [
        ("release-order-tag-behind-job", "tag-and-release behind publish, validate"),
        ("release-order-tag-skipped-on-retry", "tag-and-release (job if:)"),
    ]


def test_a_tag_behind_publish_alone_is_refused() -> None:
    """Not only validation: anything that can fail after the seal (a Docker retag in publish) strands the sentinel just the same."""
    ci, cd, action = release_trio()
    cd["jobs"]["init"]["needs"] = ["publish"]
    cd["jobs"]["publish"]["needs"] = []
    assert ("release-order-tag-behind-job", "init behind publish") in release_kinds(ci, cd, action)


def test_a_retry_mode_guard_on_the_tag_step_itself_is_refused() -> None:
    ci, cd, action = release_trio()
    cd["jobs"]["init"]["steps"][-1]["if"] = "steps.skip-check.outputs.retry_mode != 'true'"
    assert release_kinds(ci, cd, action) == [
        ("release-order-tag-skipped-on-retry", "init (step if:)")
    ]


def test_no_version_tag_step_is_a_vacuity_failure() -> None:
    """A submodule tagger or a bare `git tag` without the `v$` push is not the version tag; finding none must be red."""
    ci, cd, action = release_trio()
    cd["jobs"]["init"]["steps"][-1]["run"] = 'git tag -a "x" -m m\ngit push origin main\n'
    assert ("release-order-no-tag-step", "<none>") in release_kinds(ci, cd, action)


def test_a_missing_sentinel_writer_is_a_vacuity_failure() -> None:
    ci, cd, action = release_trio()
    del ci["jobs"]["finalize-release-sentinel"]["steps"][1]
    assert release_kinds(ci, cd, action) == [
        ("release-order-no-sentinel-writer", "finalize-release-sentinel")
    ]


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(lambda steps: steps[2].__setitem__("if", "always()"), id="different-if"),
        pytest.param(lambda steps: steps.insert(2, {"run": "echo between"}), id="step-between"),
        pytest.param(lambda steps: steps.pop(2), id="no-dispatch"),
    ],
)
def test_a_dispatch_split_from_the_seal_is_refused(mutate) -> None:
    ci, cd, action = release_trio()
    mutate(ci["jobs"]["finalize-release-sentinel"]["steps"])
    assert release_kinds(ci, cd, action) == [
        ("release-order-dispatch-split", "finalize-release-sentinel step 2 (Seal)")
    ]


@pytest.mark.parametrize(
    ("where", "value", "expected"),
    [
        ("job", {"contents": "write"}, "tag-and-release"),
        ("job", "write-all", "tag-and-release"),
        ("workflow", {"contents": "write"}, "<workflow>"),
    ],
)
def test_contents_write_anywhere_in_cd_is_refused(where, value, expected) -> None:
    ci, cd, action = release_trio()
    target = cd["jobs"]["tag-and-release"] if where == "job" else cd
    target["permissions"] = value
    assert release_kinds(ci, cd, action) == [("cd-contents-write", expected)]


def test_contents_read_and_other_write_scopes_pass() -> None:
    """The negative half: packages: write in publish is legitimate and must not trip the contents pin."""
    ci, cd, action = release_trio()
    cd["jobs"]["publish"]["permissions"] = {"contents": "read", "packages": "write"}
    assert release_kinds(ci, cd, action) == []


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(lambda steps: steps[2]["with"].pop("token"), id="checkout-without-token"),
        pytest.param(
            lambda steps: steps[1]["with"].__setitem__("preset", "readonly"), id="readonly-preset"
        ),
        pytest.param(lambda steps: steps.pop(1), id="no-app-token"),
        pytest.param(
            lambda steps: steps.insert(3, {"uses": "actions/checkout@abc"}),
            id="later-default-checkout",
        ),
    ],
)
def test_a_push_off_the_cd_app_token_is_refused(mutate) -> None:
    ci, cd, action = release_trio()
    steps = cd["jobs"]["init"]["steps"]
    mutate(steps)
    findings = release_kinds(ci, cd, action)
    assert [k for k, _n in findings] == ["cd-push-not-app-token"], findings


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(
            lambda a: a["runs"]["steps"][0].__setitem__(
                "run",
                PERMS_RUN.replace('    echo "perm-workflows=write" >> "$GITHUB_OUTPUT"\n', ""),
            ),
            id="arm-only-mentions-it-in-a-comment",
        ),
        pytest.param(
            lambda a: a["runs"]["steps"][1]["with"].clear(), id="mint-drops-permission-workflows"
        ),
        pytest.param(
            lambda a: a["runs"]["steps"][0].__setitem__(
                "run",
                PERMS_RUN.replace(
                    "  readonly)\n", '  readonly)\n    echo "perm-workflows=write"\n'
                ).replace('    echo "perm-workflows=write" >> "$GITHUB_OUTPUT"\n', ""),
            ),
            id="workflows-on-the-wrong-preset",
        ),
    ],
)
def test_the_cd_preset_losing_workflows_is_refused(mutate) -> None:
    ci, cd, action = release_trio()
    mutate(action)
    assert [k for k, _n in release_kinds(ci, cd, action)] == ["cd-preset-no-workflows"]


def test_every_release_kind_has_a_message() -> None:
    files = {"ci": "ci.yml", "cd": "cd.yml", "action": "action.yml"}
    for kind in ci_workflow_invariants.RELEASE_KINDS:
        assert ci_workflow_invariants.release_message_for(kind, "j", files) is not None, kind
    assert ci_workflow_invariants.release_message_for("invented", "j", files) is None


# ---- the release-order phase against the REAL files ----


def run_real(tmp_path: pathlib.Path, **files: str) -> subprocess.CompletedProcess[str]:
    """The port over the real tree, with any of WORKFLOW_FILE / CD_WORKFLOW_FILE / APP_TOKEN_ACTION_FILE replaced by a mutated copy."""
    env = env_for()
    for key, text in files.items():
        path = tmp_path / ("%s.yml" % key.lower())
        path.write_text(text, encoding="utf-8")
        env[key] = str(path)
    return subprocess.run(
        [PYTHON, str(PORT)],
        env=env,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )


def cut_once(source: str, before: str, after: str) -> str:
    """Exactly one replacement, asserted: a mutation that silently changed nothing would make the red case pass for no reason."""
    assert source.count(before) == 1, "the mutation target moved (%d matches): %r" % (
        source.count(before),
        before,
    )
    return source.replace(before, after)


REAL_CD = ROOT / ".github/workflows/cd-v2.yml"
REAL_CI = ROOT / ".github/workflows/ci.yml"
REAL_ACTION = ROOT / ".github/actions/app-token/action.yml"


def test_the_real_pre_fix_cd_workflow_is_refused(tmp_path: pathlib.Path) -> None:
    """THE HISTORICAL CONTROL: the cd-v2.yml that stranded v2.2.0's sentinel must be red, for both of its defects.

    Skipped, loudly, when the commit is unreachable (a shallow clone): a missing object is not evidence of a working gate.
    """
    show = subprocess.run(
        ["git", "show", "%s:.github/workflows/cd-v2.yml" % PRE_FIX_CD_COMMIT],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    if show.returncode != 0:
        pytest.skip(
            "pre-fix commit %s unreachable here: %s" % (PRE_FIX_CD_COMMIT, show.stderr.strip())
        )
    proc = run_real(tmp_path, CD_WORKFLOW_FILE=show.stdout)
    assert proc.returncode == 1, proc.stderr
    assert (
        "sits in tag-and-release behind publish, deploy-marketing-edge, deploy-account-edge, smoke-test, validate-install-published"
        in proc.stderr
    )
    assert "is skipped on retry_mode (tag-and-release (job if:))" in proc.stderr
    # And the fixed file, through the SAME explicit seam, is green: the red above is the graph, not the seam.
    fixed_dir = tmp_path / "fixed"
    fixed_dir.mkdir()
    fixed = run_real(fixed_dir, CD_WORKFLOW_FILE=REAL_CD.read_text(encoding="utf-8"))
    assert fixed.returncode == 0, fixed.stderr
    assert "release order holds" in fixed.stderr


def test_dropping_permission_workflows_from_the_real_action_is_refused(
    tmp_path: pathlib.Path,
) -> None:
    """The plan's W4 control: drop the mint's `permission-workflows` input from the real action.yml."""
    text = cut_once(
        REAL_ACTION.read_text(encoding="utf-8"),
        "        permission-workflows: ${{ steps.perms.outputs.perm-workflows }}\n",
        "",
    )
    proc = run_real(tmp_path, APP_TOKEN_ACTION_FILE=text)
    assert proc.returncode == 1, proc.stderr
    assert "INVARIANT-FAIL: cd-preset:" in proc.stderr


def test_dropping_the_cd_arms_workflows_line_from_the_real_action_is_refused(
    tmp_path: pathlib.Path,
) -> None:
    text = cut_once(
        REAL_ACTION.read_text(encoding="utf-8"),
        '            echo "perm-workflows=write" >> "$GITHUB_OUTPUT"\n',
        "",
    )
    proc = run_real(tmp_path, APP_TOKEN_ACTION_FILE=text)
    assert proc.returncode == 1, proc.stderr
    assert "INVARIANT-FAIL: cd-preset:" in proc.stderr


def test_the_real_init_checkout_losing_the_app_token_is_refused(tmp_path: pathlib.Path) -> None:
    """Scoped to init: its second checkout is the credential the version-tag push rides."""
    source = REAL_CD.read_text(encoding="utf-8")
    head, sep, rest = source.partition("\n  publish:\n")
    assert sep, "the init/publish boundary moved"
    head = cut_once(head, "          token: ${{ steps.app-token.outputs.token }}\n", "")
    proc = run_real(tmp_path, CD_WORKFLOW_FILE=head + sep + rest)
    assert proc.returncode == 1, proc.stderr
    assert "INVARIANT-FAIL: cd-push-token:" in proc.stderr
    assert "init step" in proc.stderr


def test_a_real_dispatch_guard_that_differs_from_the_seal_is_refused(
    tmp_path: pathlib.Path,
) -> None:
    """ci.yml side. CD_WORKFLOW_FILE is set to the real cd-v2 so the phase runs over the mutated ci.yml copy."""
    text = cut_once(
        REAL_CI.read_text(encoding="utf-8"),
        "      - name: Dispatch cd-v2 release\n        if: needs.initialize.outputs.skip_release != 'true'\n",
        "      - name: Dispatch cd-v2 release\n        if: always()\n",
    )
    proc = run_real(
        tmp_path, WORKFLOW_FILE=text, CD_WORKFLOW_FILE=REAL_CD.read_text(encoding="utf-8")
    )
    assert proc.returncode == 1, proc.stderr
    assert "INVARIANT-FAIL: release-order:" in proc.stderr
    assert "Write release sentinels" in proc.stderr


# ---- every external gate is hard on every cadence (operator rulings 2026-10-13 and 2026-10-14) ----

UPSTREAM_IF = (
    "${{ !cancelled() && steps.setup.outcome == 'success' && inputs.external_quality != 'skip' }}"
)
# What gate-bind emits for a gate whose header carries `when: inputs.external_quality != 'skip'`, in an unsharded and in a sharded lane.
BOUND_IF = (
    "${{ !cancelled() && steps.setup.outcome == 'success' && (inputs.external_quality != 'skip') }}"
)
SHARDED_IF = "${{ !cancelled() && steps.setup.outcome == 'success' && ((inputs.external_quality != 'skip') && matrix.shard == 3) }}"
UPSTREAM_MODE = "${{ github.event_name != 'pull_request' && 'soft' || (contains(github.event.pull_request.labels.*.name, 'no-external-quality') && 'skip' || 'hard') }}"
UPSTREAM_ANNOUNCE = (
    "PYTHONPATH=.ci python3 -m rediacc_ci.quality.announce_gate_skips no-external-quality "
    + " ".join(ci_workflow_invariants.UPSTREAM_GATES)
)
REAL_QUALITY = ROOT / ".github/workflows/ci-quality.yml"
# The job each gate's real step sits in, read off the live workflow by the real-file plants below.
REAL_JOB = {
    "check:ci-embed-asset-freshness": "quality-go",
    "check:ci-devcontainer-pins": "quality-go",
    "check:ci-real-provider-pins": "quality-go",
    "check:ci-go-deps": "quality-go",
    "check:actions": "quality-code",
    "check:ci-pin-freshness": "quality-code",
    "check:ci-external-links": "quality-content",
    "check:ci-dkim-notify": "quality-content",
    "check:deps": "quality-content",
}


def upstream_pair() -> tuple[dict, dict]:
    """A conformant (ci, ci-quality) pair; every red case below breaks exactly one thing in a fresh copy."""
    ci = {"jobs": {"initialize": {"outputs": {"external_quality": UPSTREAM_MODE}}}}
    steps: list[dict] = [
        {"id": "setup", "uses": "./.github/actions/setup-workspace"},
        {
            "name": "Announce external gates held by label",
            "if": "${{ !cancelled() && steps.setup.outcome == 'success' }}",
            "env": {
                "GATE_SKIP_MODE": "${{ inputs.external_quality == 'skip' && 'skip' || 'hard' }}"
            },
            "run": UPSTREAM_ANNOUNCE,
        },
    ]
    steps += [
        {"name": gate, "if": UPSTREAM_IF, "env": {"GITHUB_TOKEN": "t"}, "run": "npm run %s" % gate}
        for gate in ci_workflow_invariants.UPSTREAM_GATES
    ]
    return ci, {"jobs": {"quality-go": {"steps": steps}}}


def upstream_kinds(ci: dict, quality: dict) -> list[str]:
    return [kind for kind, _name in ci_workflow_invariants.analyse_upstream_gates(ci, quality)[0]]


def upstream_step(quality: dict, gate: str) -> dict:
    return next(s for s in quality["jobs"]["quality-go"]["steps"] if s.get("name") == gate)


def test_every_external_gate_is_judged() -> None:
    """The ruling of 2026-10-14 names seven gates; check:deps is the eighth because it asks the npm registry. Losing one from the tuple would let its step go soft unseen."""
    assert set(ci_workflow_invariants.UPSTREAM_GATES) == set(REAL_JOB)


def test_a_conformant_upstream_gate_pair_is_clean_and_reports_its_shape() -> None:
    findings, shape = ci_workflow_invariants.analyse_upstream_gates(*upstream_pair())
    assert findings == []
    assert shape == ["%s in quality-go" % gate for gate in ci_workflow_invariants.UPSTREAM_GATES]


@pytest.mark.parametrize(
    "condition",
    [
        "${{ !cancelled() && steps.setup.outcome == 'success' && inputs.external_quality == 'hard' }}",
        UPSTREAM_IF.replace(" }}", " && github.event_name == 'pull_request' }}"),
        SHARDED_IF.replace("matrix.shard == 3", "github.event_name == 'pull_request'"),
        SHARDED_IF.replace(" }}", " && github.event_name == 'pull_request' }}"),
        "${{ !cancelled() && steps.setup.outcome == 'success' }}",
        None,
    ],
)
def test_an_if_that_is_not_the_label_hold_is_refused(condition: str | None) -> None:
    """`== 'hard'` skips the step under `soft`, a pull_request conjunct skips it on a schedule (also beside or instead of a shard conjunct), and dropping the label conjunct removes the documented hold: each is a different `if:`, and only the one is admitted."""
    ci, quality = upstream_pair()
    step = upstream_step(quality, "check:ci-dkim-notify")
    if condition is None:
        del step["if"]
    else:
        step["if"] = condition
    assert upstream_kinds(ci, quality) == ["upstream-gate-conditional"]


@pytest.mark.parametrize(
    "job_if",
    [
        "github.event_name == 'pull_request'",
        "${{ inputs.is_bot != 'true' && github.event_name != 'schedule' }}",
    ],
)
def test_a_job_level_if_that_can_skip_the_nightly_is_refused(job_if: str) -> None:
    """The step-level `if:` is exact, but a condition on the JOB skips every step in it, announcer included, and no step-level check sees it."""
    ci, quality = upstream_pair()
    quality["jobs"]["quality-go"]["if"] = job_if
    assert upstream_kinds(ci, quality) == ["upstream-gate-job-conditional"]


def test_the_bot_guard_on_the_job_is_not_a_finding() -> None:
    """Control: the lane's own guard, with or without the expression wrapper, is admitted."""
    ci, quality = upstream_pair()
    quality["jobs"]["quality-go"]["if"] = "inputs.is_bot != 'true'"
    assert upstream_kinds(ci, quality) == []
    quality["jobs"]["quality-go"]["if"] = "${{ inputs.is_bot != 'true' }}"
    assert upstream_kinds(ci, quality) == []


@pytest.mark.parametrize(
    "condition", [UPSTREAM_IF.replace(" && ", "\n  && "), BOUND_IF, SHARDED_IF]
)
def test_the_admitted_if_in_every_spelling_is_not_a_finding(condition: str) -> None:
    """Control for the comparison: the admitted `if:` reflowed, as gate-bind emits it, and with gate-bind's shard conjunct is still the admitted `if:`."""
    ci, quality = upstream_pair()
    upstream_step(quality, "check:actions")["if"] = condition
    assert upstream_kinds(ci, quality) == []


def test_an_upstream_gate_with_no_step_is_a_vacuity_failure() -> None:
    ci, quality = upstream_pair()
    steps = quality["jobs"]["quality-go"]["steps"]
    steps.remove(upstream_step(quality, "check:ci-go-deps"))
    assert ci_workflow_invariants.analyse_upstream_gates(ci, quality)[0] == [
        ("upstream-gate-missing", "check:ci-go-deps")
    ]
    assert upstream_kinds(ci, {"jobs": {}}) == ["upstream-gate-missing"] * len(REAL_JOB)


def test_a_longer_script_name_is_not_the_gate() -> None:
    """`npm run check:deps-extra` is another script: it does not satisfy the gate, and it is not judged as one."""
    ci, quality = upstream_pair()
    upstream_step(quality, "check:deps")["run"] += "-extra"
    assert upstream_kinds(ci, quality) == ["upstream-gate-missing"]


@pytest.mark.parametrize(
    "mutate",
    [
        lambda a: a.__setitem__("run", a["run"].replace(" check:ci-real-provider-pins", "")),
        lambda a: a.__setitem__("run", a["run"].replace("no-external-quality", "no-media-quality")),
        lambda a: a.__setitem__("if", UPSTREAM_IF),
        lambda a: a["env"].__setitem__("GATE_SKIP_MODE", "${{ inputs.external_quality }}"),
        lambda a: a.__setitem__("run", "true"),
    ],
)
def test_a_label_hold_nothing_announces_is_refused(mutate) -> None:
    """The announcer drops a gate, names another label, sits behind the same label it announces, is handed the raw three-state value (which it refuses under `soft`), or is gone."""
    ci, quality = upstream_pair()
    mutate(quality["jobs"]["quality-go"]["steps"][1])
    kinds = upstream_kinds(ci, quality)
    assert kinds, "the mutation was not seen"
    assert set(kinds) == {"upstream-gate-unannounced"}


@pytest.mark.parametrize(
    "mode",
    [
        "${{ github.event_name != 'pull_request' && 'skip' || 'hard' }}",
        "${{ github.event_name == 'schedule' && 'skip' || 'hard' }}",
        "skip",
        None,
    ],
)
def test_a_ci_yml_that_can_skip_the_external_gates_off_a_pull_request_is_refused(mode) -> None:
    ci, quality = upstream_pair()
    if mode is None:
        del ci["jobs"]["initialize"]["outputs"]["external_quality"]
    else:
        ci["jobs"]["initialize"]["outputs"]["external_quality"] = mode
    assert upstream_kinds(ci, quality) == ["upstream-gate-schedule-skipped"]


def test_every_upstream_gate_kind_has_a_message() -> None:
    files = {"ci": "ci.yml", "quality": "ci-quality.yml"}
    for kind in ci_workflow_invariants.UPSTREAM_GATE_KINDS:
        assert ci_workflow_invariants.upstream_gate_message_for(kind, "g", files) is not None, kind
    assert ci_workflow_invariants.upstream_gate_message_for("invented", "g", files) is None


def test_the_real_workflow_holds_every_external_gate_hard(tmp_path: pathlib.Path) -> None:
    """The live pair, through the gate itself: green, and the shape line names every gate in its job."""
    proc = run_real(tmp_path)
    assert proc.returncode == 0, proc.stderr
    assert "external gates hold (%d gate(s)" % len(REAL_JOB) in proc.stderr
    for gate, job in REAL_JOB.items():
        assert "%s in %s" % (gate, job) in proc.stderr


@pytest.mark.parametrize(
    ("before", "after", "gate"),
    [
        (
            " no-external-quality check:ci-go-deps check:ci-embed-asset-freshness check:ci-devcontainer-pins check:ci-real-provider-pins\n",
            " no-external-quality check:ci-go-deps check:ci-embed-asset-freshness check:ci-devcontainer-pins\n",
            "check:ci-real-provider-pins",
        ),
        (
            " no-external-quality check:deps check:ci-external-links check:ci-dkim-notify\n",
            " no-external-quality check:ci-external-links check:ci-dkim-notify\n",
            "check:deps",
        ),
        (
            " no-external-quality check:actions check:ci-pin-freshness\n",
            " no-external-quality check:ci-pin-freshness\n",
            "check:actions",
        ),
        (
            " no-external-quality check:actions check:ci-pin-freshness\n",
            " no-external-quality check:actions\n",
            "check:ci-pin-freshness",
        ),
    ],
)
def test_a_real_announcer_losing_a_gate_is_refused(
    tmp_path: pathlib.Path, before: str, after: str, gate: str
) -> None:
    text = cut_once(REAL_QUALITY.read_text(encoding="utf-8"), before, after)
    proc = run_real(tmp_path, QUALITY_WORKFLOW_FILE=text)
    assert proc.returncode == 1, proc.stderr
    assert "INVARIANT-FAIL: upstream-gates: %s" % gate in proc.stderr
    assert "no announcer naming it" in proc.stderr


def test_a_real_ci_yml_that_skips_external_gates_on_the_nightly_is_refused(
    tmp_path: pathlib.Path,
) -> None:
    text = cut_once(
        REAL_CI.read_text(encoding="utf-8"),
        "external_quality: ${{ github.event_name != 'pull_request' && 'soft' ||",
        "external_quality: ${{ github.event_name != 'pull_request' && 'skip' ||",
    )
    proc = run_real(
        tmp_path, WORKFLOW_FILE=text, CD_WORKFLOW_FILE=REAL_CD.read_text(encoding="utf-8")
    )
    assert proc.returncode == 1, proc.stderr
    assert "INVARIANT-FAIL: upstream-gates:" in proc.stderr
    assert "take them off the nightly" in proc.stderr


# ---- the cd-preflight pins (PLAN-cd-errors-in-ci W4) ----

PF_PR = 'PYTHONPATH=.ci python3 -m rediacc_ci.release.cd_preflight --phase pr --release-version "$V" --checks a,b,c,d,promotion'
PF_CD = 'PYTHONPATH=.ci python3 -m rediacc_ci.release.cd_preflight --phase cd --release-version "$V" --checks a,c,d'
PF_HK = "PYTHONPATH=.ci python3 -m rediacc_ci.release.cd_preflight --phase pr --release-version 0.0.0 --checks a,c"


def preflight_trio() -> tuple[dict, dict, dict]:
    """A conformant (ci, cd, housekeeping) triple; every red case below breaks exactly one thing in a fresh copy."""
    ci = {
        "jobs": {
            "cd-preflight": {
                "needs": ["initialize"],
                "if": "always() && (github.event_name == 'push' || github.event_name == 'pull_request')",
                "steps": [{"uses": "actions/checkout@abc"}, {"name": "Predict", "run": PF_PR}],
            }
        }
    }
    cd = {
        "jobs": {
            "init": {
                "steps": [
                    {"uses": "actions/checkout@abc"},
                    {"name": "Create version tag", "run": TAG_RUN},
                    {"name": "CD preflight", "run": PF_CD},
                ]
            }
        }
    }
    hk = {
        "jobs": {
            "cleanup": {
                "steps": [
                    {
                        "name": "Retry",
                        "run": "python3 -m rediacc_ci.housekeeping.retry_failed_runs",
                    },
                    {"name": "Preflight", "run": PF_HK},
                    {
                        "name": "Cleanup",
                        "run": "python3 -m rediacc_ci.housekeeping.cleanup_versions",
                    },
                    {"name": "Reap", "if": "${{ !cancelled() }}", "run": "reap.sh"},
                ]
            }
        }
    }
    return ci, cd, hk


def preflight_kinds(ci: dict, cd: dict, hk: dict) -> list[str]:
    return [k for k, _n in ci_workflow_invariants.analyse_preflight(ci, cd, hk)[0]]


def test_a_conformant_preflight_trio_is_clean_and_reports_its_shape() -> None:
    """The NEGATIVE direction, so each red case below is red for the thing it planted."""
    findings, shape = ci_workflow_invariants.analyse_preflight(*preflight_trio())
    assert findings == []
    assert shape == [
        "ci.yml job cd-preflight runs it on pull_request",
        "cd-v2 init step 3 after the tag step 2",
        "housekeeping cleanup step 2 before cleanup step 3",
    ]


def _push_only(ci: dict, _cd: dict, _hk: dict) -> None:
    ci["jobs"]["cd-preflight"]["if"] = "always() && github.event_name == 'push'"


def _main_only_negated(ci: dict, _cd: dict, _hk: dict) -> None:
    ci["jobs"]["cd-preflight"]["if"] = "always() && github.event_name != 'pull_request'"


def _job_pr_step_negated(ci: dict, _cd: dict, _hk: dict) -> None:
    """A positive job-level pull_request test must not mask a step-level `if:` that excludes it."""
    job = ci["jobs"]["cd-preflight"]
    job["if"] = "always() && (github.event_name == 'push' || github.event_name == 'pull_request')"
    job["steps"][1]["if"] = "github.event_name != 'pull_request'"


def _spaced_negation(ci: dict, _cd: dict, _hk: dict) -> None:
    ci["jobs"]["cd-preflight"]["if"] = "always() && ! (github.event_name == 'pull_request')"


def _nested_negation(ci: dict, _cd: dict, _hk: dict) -> None:
    ci["jobs"]["cd-preflight"]["if"] = "always() && !((github.event_name == 'pull_request'))"


def _enclosed_negation(ci: dict, _cd: dict, _hk: dict) -> None:
    ci["jobs"]["cd-preflight"]["if"] = (
        "always() && !(github.event_name == 'pull_request' || github.event_name == 'push')"
    )


def _no_job_if(ci: dict, _cd: dict, _hk: dict) -> None:
    del ci["jobs"]["cd-preflight"]["if"]


def _no_pr_job(ci: dict, _cd: dict, _hk: dict) -> None:
    del ci["jobs"]["cd-preflight"]


def _before_tag(_ci: dict, cd: dict, _hk: dict) -> None:
    steps = cd["jobs"]["init"]["steps"]
    steps[1], steps[2] = steps[2], steps[1]


def _other_job(_ci: dict, cd: dict, _hk: dict) -> None:
    cd["jobs"]["preflight"] = {"steps": [cd["jobs"]["init"]["steps"].pop()]}


def _no_cd_step(_ci: dict, cd: dict, _hk: dict) -> None:
    cd["jobs"]["init"]["steps"].pop()


def _no_hk_step(_ci: dict, _cd: dict, hk: dict) -> None:
    del hk["jobs"]["cleanup"]["steps"][1]


def _hk_after(_ci: dict, _cd: dict, hk: dict) -> None:
    steps = hk["jobs"]["cleanup"]["steps"]
    steps[1], steps[2] = steps[2], steps[1]


def _hk_always(_ci: dict, _cd: dict, hk: dict) -> None:
    hk["jobs"]["cleanup"]["steps"][2]["if"] = "always()"


def _hk_guarded_preflight(_ci: dict, _cd: dict, hk: dict) -> None:
    hk["jobs"]["cleanup"]["steps"][1]["if"] = "inputs.dry_run != true"


def _no_cleanup(_ci: dict, _cd: dict, hk: dict) -> None:
    del hk["jobs"]["cleanup"]["steps"][2]


def _narrow_cd(_ci: dict, cd: dict, _hk: dict) -> None:
    cd["jobs"]["init"]["steps"][2]["run"] = PF_CD.replace("a,c,d", "a,c")


def _narrow_hk(_ci: dict, _cd: dict, hk: dict) -> None:
    hk["jobs"]["cleanup"]["steps"][1]["run"] = PF_HK.replace("a,c", "c")


@pytest.mark.parametrize(
    ("mutate", "expected"),
    [
        (_push_only, ["cd-preflight-not-on-pr"]),
        (_main_only_negated, ["cd-preflight-not-on-pr"]),
        (_job_pr_step_negated, ["cd-preflight-not-on-pr"]),
        (_spaced_negation, ["cd-preflight-not-on-pr"]),
        (_nested_negation, ["cd-preflight-not-on-pr"]),
        (_enclosed_negation, ["cd-preflight-not-on-pr"]),
        (_no_pr_job, ["cd-preflight-no-pr-job"]),
        (_before_tag, ["cd-preflight-before-tag"]),
        (_other_job, ["cd-preflight-before-tag"]),
        (_no_cd_step, ["cd-preflight-no-cd-step"]),
        (_no_hk_step, ["cd-preflight-no-housekeeping-step"]),
        (_hk_after, ["cd-preflight-no-housekeeping-step"]),
        (_hk_always, ["cd-preflight-housekeeping-bypassed"]),
        (_hk_guarded_preflight, ["cd-preflight-housekeeping-bypassed"]),
        (_no_cleanup, ["cd-preflight-no-housekeeping-step"]),
        (_narrow_cd, ["cd-preflight-narrowed"]),
        (_narrow_hk, ["cd-preflight-narrowed"]),
    ],
)
def test_each_preflight_pin_fires_on_exactly_its_plant(mutate, expected) -> None:
    ci, cd, hk = preflight_trio()
    mutate(ci, cd, hk)
    assert preflight_kinds(ci, cd, hk) == expected


def test_a_job_without_an_if_runs_on_pull_request_and_passes() -> None:
    ci, cd, hk = preflight_trio()
    _no_job_if(ci, cd, hk)
    assert preflight_kinds(ci, cd, hk) == []


def test_a_double_negation_and_a_closed_group_before_the_match_still_admit() -> None:
    admits = ci_workflow_invariants._admits_pr
    assert admits("!(!(github.event_name == 'pull_request'))")
    assert admits("!(a) || github.event_name == 'pull_request'")
    assert not admits("x && !(a && (github.event_name == 'pull_request'))")


def test_a_preflight_without_checks_runs_all_and_is_not_narrowed() -> None:
    ci, cd, hk = preflight_trio()
    hk["jobs"]["cleanup"]["steps"][1]["run"] = PF_HK.replace(" --checks a,c", "")
    assert preflight_kinds(ci, cd, hk) == []


def test_every_preflight_kind_has_a_message() -> None:
    files = {"ci": "ci.yml", "cd": "cd.yml", "housekeeping": "hk.yml"}
    for kind in ci_workflow_invariants.PREFLIGHT_KINDS:
        assert ci_workflow_invariants.preflight_message_for(kind, "j", files) is not None, kind
    assert ci_workflow_invariants.preflight_message_for("invented", "j", files) is None


REAL_HK = ROOT / ".github/workflows/housekeeping.yml"


def test_a_push_only_preflight_on_the_real_ci_is_refused(tmp_path: pathlib.Path) -> None:
    """The plan's W4 control on the real ci.yml: drop the same-repo pull_request arm."""
    text = cut_once(
        REAL_CI.read_text(encoding="utf-8"),
        "      ((github.event_name == 'push' && github.ref == 'refs/heads/main') ||\n"
        "      (github.event_name == 'pull_request' && github.event.pull_request.head.repo.full_name == github.repository))\n",
        "      github.event_name == 'push' && github.ref == 'refs/heads/main'\n",
    )
    proc = run_real(
        tmp_path, WORKFLOW_FILE=text, CD_WORKFLOW_FILE=REAL_CD.read_text(encoding="utf-8")
    )
    assert proc.returncode == 1, proc.stderr
    assert "INVARIANT-FAIL: cd-preflight:" in proc.stderr
    assert (
        "job cd-preflight runs the preflight but its `if:` never admits pull_request" in proc.stderr
    )


def test_the_real_cd_preflight_moved_before_the_tag_is_refused(tmp_path: pathlib.Path) -> None:
    """Swap the real init's last two steps: the preflight lands before `Create version tag`."""
    source = REAL_CD.read_text(encoding="utf-8")
    head, sep, rest = source.partition("\n  publish:\n")
    assert sep, "the init/publish boundary moved"
    tag_at = head.index("      - name: Create version tag\n")
    pf_at = head.index("      - name: CD preflight\n")
    assert tag_at < pf_at
    # Comments between the two steps belong to the preflight; carry the block from its comment header.
    pf_start = head.rindex("\n\n", tag_at, pf_at) + 2
    tag_block, pf_block = head[tag_at:pf_start], head[pf_start:].rstrip("\n") + "\n\n"
    mutated = head[:tag_at] + pf_block + tag_block.rstrip("\n") + "\n" + sep + rest
    proc = run_real(tmp_path, CD_WORKFLOW_FILE=mutated)
    assert proc.returncode == 1, proc.stderr
    assert "is not after the version tag step in the same job" in proc.stderr


def test_the_real_housekeeping_cleanup_running_past_a_red_preflight_is_refused(
    tmp_path: pathlib.Path,
) -> None:
    text = cut_once(
        REAL_HK.read_text(encoding="utf-8"),
        "      - name: Cleanup old releases, tags, packages, previews, R2 orphans, branches\n",
        "      - name: Cleanup old releases, tags, packages, previews, R2 orphans, branches\n"
        "        if: always()\n",
    )
    proc = run_real(tmp_path, HOUSEKEEPING_WORKFLOW_FILE=text)
    assert proc.returncode == 1, proc.stderr
    assert "Housekeeping must fail closed" in proc.stderr


def test_the_real_housekeeping_without_its_preflight_is_refused(tmp_path: pathlib.Path) -> None:
    text = cut_once(
        REAL_HK.read_text(encoding="utf-8"),
        "          PYTHONPATH=.ci python3 -m rediacc_ci.release.cd_preflight\n",
        "          PYTHONPATH=.ci python3 -m rediacc_ci.release.removed\n",
    )
    proc = run_real(tmp_path, HOUSEKEEPING_WORKFLOW_FILE=text)
    assert proc.returncode == 1, proc.stderr
    assert "deletes releases, tags and R2 objects with no" in proc.stderr


def pins_doc() -> dict:
    """A conformant pins-soaked document, built by hand: the pytest interpreter carries no PyYAML, and the real file is driven through the gate's own entry point below."""
    return {
        "on": {
            "schedule": [{"cron": "30 0 * * *"}],
            "workflow_dispatch": {},
            "workflow_run": {"workflows": [ci_workflow_invariants.PINS_SOAKED_WORKFLOW]},
        },
        "permissions": {"contents": "read"},
        "jobs": {
            "soaked": {
                "permissions": {"contents": "read"},
                "steps": [
                    {"uses": "actions/checkout@sha"},
                    {
                        "id": "apply",
                        "run": 'npm run --silent pins -- apply-soaked --json --out pins-soaked/\nrc=$?\necho "rc=${rc}" >> "$GITHUB_OUTPUT"',
                    },
                    {"uses": "actions/upload-artifact@sha"},
                    {"if": "steps.apply.outputs.rc != '0'", "run": "echo failed\nexit 1"},
                ],
            }
        },
    }


def pins_kinds(doc: object) -> list[str]:
    return [k for k, _n in ci_workflow_invariants.analyse_pins_soaked(doc)[0]]


def _drop_upload(doc: dict) -> None:
    for step in doc["jobs"]["soaked"]["steps"]:
        if "upload-artifact" in str(step.get("uses")):
            step["uses"] = "x/y@1"


def _drop_apply(doc: dict) -> None:
    steps = doc["jobs"]["soaked"]["steps"]
    steps[:] = [s for s in steps if "apply-soaked" not in str(s.get("run"))]


def _drop_red_path(doc: dict) -> None:
    steps = doc["jobs"]["soaked"]["steps"]
    steps[:] = [s for s in steps if "outputs.rc" not in str(s.get("if"))]


def _red_if(doc: dict, cond: str) -> None:
    for step in doc["jobs"]["soaked"]["steps"]:
        if "outputs.rc" in str(step.get("if")):
            step["if"] = cond


@pytest.mark.parametrize(
    "cond",
    [
        "steps.apply.outputs.rc != '0'",
        'steps.apply.outputs.rc != "0"',
        "steps.apply.outputs.rc != 0",
    ],
)
def test_the_red_path_condition_may_quote_the_zero_either_way_or_not_at_all(cond) -> None:
    doc = pins_doc()
    _red_if(doc, cond)
    assert pins_kinds(doc) == []


def test_a_red_path_watching_another_step_is_no_red_path() -> None:
    doc = pins_doc()
    _red_if(doc, "steps.other.outputs.rc != '0'")
    assert pins_kinds(doc) == ["pins-soaked-no-red-path"]


@pytest.mark.parametrize(
    "run",
    [
        'npm run --silent pins -- apply-soaked --json --out pins-soaked/ || true\nrc=$?\necho "rc=${rc}" >> "$GITHUB_OUTPUT"',
        'npm run --silent pins -- apply-soaked --json --out pins-soaked/\necho "rc=0" >> "$GITHUB_OUTPUT"',
        'npm run --silent pins -- apply-soaked --json --out pins-soaked/\ntrue\nrc=$?\necho "rc=${rc}" >> "$GITHUB_OUTPUT"',
        'npm run --silent pins -- apply-soaked --json --out pins-soaked/ | tee log\nrc=$?\necho "rc=${rc}" >> "$GITHUB_OUTPUT"',
        'npm run --silent pins -- apply-soaked --json --out pins-soaked/; true\nrc=$?\necho "rc=${rc}" >> "$GITHUB_OUTPUT"',
        'npm run --silent pins -- apply-soaked --json --out pins-soaked/ && true\nrc=$?\necho "rc=${rc}" >> "$GITHUB_OUTPUT"',
        'npm run --silent pins -- apply-soaked --json --out pins-soaked/ \\\n  || true\nrc=$?\necho "rc=${rc}" >> "$GITHUB_OUTPUT"',
        'npm run --silent pins -- apply-soaked --json --out pins-soaked/\nrc=$?\nrc=0\necho "rc=${rc}" >> "$GITHUB_OUTPUT"',
        'npm run --silent pins -- apply-soaked --json --out pins-soaked/\nrc=$?\nlet rc=0\necho "rc=${rc}" >> "$GITHUB_OUTPUT"',
        'npm run --silent pins -- apply-soaked --json --out pins-soaked/\nrc=$?\nrc=0; echo "rc=$rc" >> "$GITHUB_OUTPUT"',
        '! npm run --silent pins -- apply-soaked --json --out pins-soaked/\nrc=$?\necho "rc=${rc}" >> "$GITHUB_OUTPUT"',
        'npm run --silent pins -- apply-soaked --json --out pins-soaked/\nrc=$?\necho "rc=$rc >> $GITHUB_OUTPUT"',
        'npm run --silent pins -- apply-soaked --json --out pins-soaked/\nrc=$?\necho "rc=$rc" >> "$GITHUB_OUTPUT',
        'if npm run --silent pins -- apply-soaked --json --out pins-soaked/\nrc=$?\necho "rc=${rc}" >> "$GITHUB_OUTPUT"',
        'npm run --silent pins -- apply-soaked --json --out pins-soaked/\nrc=$?\necho "rc=$rc" >> "$GITHUB_OUTPUT"; rc=0',
    ],
)
def test_an_rc_output_that_is_not_the_apply_exit_status_is_no_red_path(run) -> None:
    doc = pins_doc()
    doc["jobs"]["soaked"]["steps"][1]["run"] = run
    assert pins_kinds(doc) == ["pins-soaked-no-red-path"]


def test_a_comment_or_echo_naming_the_verb_above_the_apply_is_not_the_apply_line() -> None:
    doc = pins_doc()
    step = doc["jobs"]["soaked"]["steps"][1]
    step["run"] = (
        "# runs npm run pins -- apply-soaked below\necho 'pins -- apply-soaked'\n" + step["run"]
    )
    assert pins_kinds(doc) == []


def test_the_word_secrets_outside_an_expression_is_not_a_secret() -> None:
    doc = pins_doc()
    doc["jobs"]["soaked"]["steps"].append({"run": "echo this job holds no secrets, by design"})
    assert pins_kinds(doc) == []


def _rc_write_spellings() -> list[str]:
    """Every accepted spelling of the rc write: each operand fully quoted or bare, and `$name` or `${name}`, so 4 x 4 = 16."""
    spellings = []
    for rc_var in ("$rc", "${rc}"):
        for rc_quoted in (True, False):
            for out_var in ("$GITHUB_OUTPUT", "${GITHUB_OUTPUT}"):
                for out_quoted in (True, False):
                    left = '"rc=%s"' % rc_var if rc_quoted else "rc=%s" % rc_var
                    right = '"%s"' % out_var if out_quoted else out_var
                    spellings.append("echo %s >> %s" % (left, right))
    return spellings


def test_the_rc_write_spelling_matrix_is_all_sixteen_distinct_combinations() -> None:
    spellings = _rc_write_spellings()
    assert len(spellings) == 16
    assert len(set(spellings)) == 16


@pytest.mark.parametrize("write", _rc_write_spellings())
def test_each_accepted_spelling_of_the_rc_write_keeps_the_red_path(write) -> None:
    doc = pins_doc()
    doc["jobs"]["soaked"]["steps"][1]["run"] = (
        "npm run --silent pins -- apply-soaked --json --out pins-soaked/\nrc=$?\n" + write
    )
    assert pins_kinds(doc) == []


def test_a_noclobber_redirection_on_the_apply_line_keeps_the_red_path() -> None:
    doc = pins_doc()
    doc["jobs"]["soaked"]["steps"][1]["run"] = (
        'npm run --silent pins -- apply-soaked --json --out pins-soaked/ >| out.json\nrc=$?\necho "rc=${rc}" >> "$GITHUB_OUTPUT"'
    )
    assert pins_kinds(doc) == []


def test_a_redirection_on_the_apply_line_keeps_the_red_path() -> None:
    doc = pins_doc()
    doc["jobs"]["soaked"]["steps"][1]["run"] = (
        'npm run --silent pins -- apply-soaked --json --out pins-soaked/ > out.json 2>&1\nrc=$?\necho "rc=${rc}" >> "$GITHUB_OUTPUT"'
    )
    assert pins_kinds(doc) == []


def test_an_apply_step_that_never_publishes_rc_has_no_red_path() -> None:
    doc = pins_doc()
    doc["jobs"]["soaked"]["steps"][1]["run"] = (
        "npm run --silent pins -- apply-soaked --json --out pins-soaked/"
    )
    assert pins_kinds(doc) == ["pins-soaked-no-red-path"]


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d.__setitem__("env", {"T": "${{ secrets.DEPLOY_KEY }}"}),
        lambda d: d["jobs"]["soaked"].__setitem__("secrets", {"key": "${{ secrets.DEPLOY_KEY }}"}),
        lambda d: d["jobs"]["soaked"].__setitem__("secrets", "inherit"),
        lambda d: d["jobs"]["soaked"].__setitem__("secrets", "${{ toJSON(secrets) }}"),
        lambda d: d["jobs"]["soaked"].__setitem__(
            "container", {"image": "x", "credentials": {"password": "${{ secrets.REG }}"}}
        ),
        lambda d: d["jobs"]["soaked"].__setitem__(
            "services", {"db": {"image": "x", "env": {"P": "${{ secrets['DB'] }}"}}}
        ),
        lambda d: d["jobs"]["soaked"]["steps"].append({"run": "./tool ${{ secrets.DEPLOY_KEY }}"}),
        lambda d: d["jobs"]["soaked"]["steps"].append({"run": "./tool '${{ secrets }}'"}),
        lambda d: d["jobs"]["soaked"]["steps"].append({"run": "x", "if": "secrets.K != ''"}),
        lambda d: d["jobs"]["soaked"]["steps"].append(
            {"run": "x", "env": {"A": "${{ secrets || 'x' }}"}}
        ),
        lambda d: d["jobs"]["soaked"].__setitem__("if", "${{ secrets.K == '' }}"),
    ],
)
def test_a_secret_through_the_workflow_env_or_a_secrets_block_is_refused(mutate) -> None:
    doc = pins_doc()
    mutate(doc)
    assert pins_kinds(doc) == ["pins-soaked-writes"]


def test_the_default_token_in_with_is_not_a_write_secret() -> None:
    doc = pins_doc()
    doc["jobs"]["soaked"]["steps"].append(
        {"uses": "some/action@sha", "with": {"token": "${{ secrets.GITHUB_TOKEN }}"}}
    )
    assert pins_kinds(doc) == []


def test_the_real_pins_soaked_workflow_passes_the_gate() -> None:
    env = {**os.environ, "PYTHONPATH": str(paths.from_root(".ci"))}
    proc = subprocess.run(
        [
            "python3",
            str(paths.from_root(".ci", "rediacc_ci", "security", "ci_workflow_invariants.py")),
        ],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert (
        "pins-soaked holds: 1 cron(s), 1 apply step(s), 1 upload step(s)"
        in proc.stdout + proc.stderr
    )


def test_a_conformant_pins_soaked_document_is_clean() -> None:
    findings, shape = ci_workflow_invariants.analyse_pins_soaked(pins_doc())
    assert findings == []
    assert shape[0] == "1 cron(s), 1 apply step(s), 1 upload step(s), contents: read only"
    assert shape[1].startswith("0 read-only checkout token(s)")


@pytest.mark.parametrize(
    ("mutate", "kind"),
    [
        (
            lambda d: d["jobs"]["soaked"]["steps"].append({"run": "git push origin HEAD"}),
            "pins-soaked-writes",
        ),
        (
            lambda d: d["jobs"]["soaked"]["steps"].append({"run": "gh pr create --fill"}),
            "pins-soaked-writes",
        ),
        (
            lambda d: d["jobs"]["soaked"]["steps"].append({"uses": "./.github/actions/app-token"}),
            "pins-soaked-writes",
        ),
        (lambda d: d.__setitem__("permissions", {"contents": "write"}), "pins-soaked-permissions"),
        (
            lambda d: d["jobs"]["soaked"].__setitem__(
                "permissions", {"contents": "read", "pull-requests": "write"}
            ),
            "pins-soaked-permissions",
        ),
        (
            lambda d: d["jobs"]["soaked"]["steps"].append(
                {"uses": "some/action@sha", "with": {"token": "${{ secrets.WRITE_PAT }}"}}
            ),
            "pins-soaked-writes",
        ),
        (
            lambda d: d["jobs"]["soaked"]["steps"].append(
                {"run": "./tool", "env": {"T": "${{ secrets.DEPLOY_KEY }}"}}
            ),
            "pins-soaked-writes",
        ),
        (
            lambda d: d["jobs"]["soaked"].__setitem__("env", {"T": "${{ secrets.DEPLOY_KEY }}"}),
            "pins-soaked-writes",
        ),
        (_drop_red_path, "pins-soaked-no-red-path"),
        (_drop_apply, "pins-soaked-no-apply"),
        (_drop_upload, "pins-soaked-no-upload"),
        (lambda d: d["on"].pop("schedule"), "pins-soaked-triggers"),
        (
            lambda d: d["on"]["workflow_run"].__setitem__("workflows", ["Other"]),
            "pins-soaked-triggers",
        ),
    ],
)
def test_a_pins_soaked_workflow_that_could_write_or_report_nothing_is_refused(mutate, kind) -> None:
    doc = pins_doc()
    mutate(doc)
    assert kind in pins_kinds(doc)


def test_a_missing_pins_soaked_file_is_an_error_never_a_pass() -> None:
    errors, info = ci_workflow_invariants._pins_soaked_phase("/nonexistent/pins-soaked.yml")
    assert len(errors) == 1
    assert "nothing to check cannot pass" in errors[0]
    assert info == []


def test_a_non_mapping_pins_soaked_document_is_refused() -> None:
    assert pins_kinds([]) == ["pins-soaked-triggers"]


PINNED_CHECKOUT = "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1"


def token_triple() -> list[dict]:
    """The read-only checkout token the 2026-10-23 ruling admits, step for step as pins-soaked.yml wires it."""
    return [
        {
            "name": "Fetch secrets from Bitwarden",
            "uses": "./.github/actions/bws-secrets",
            "with": {
                "access-token": "${{ secrets.BWS_ACCESS_TOKEN }}",
                "secrets": "GITHUB_APP_PRIVATE_KEY > BWS_GITHUB_APP_PRIVATE_KEY\nGITHUB_APP_ID > BWS_APP_ID\n",
            },
        },
        {
            "uses": "./.github/actions/app-token",
            "id": "app-token",
            "with": {
                "client-id": "${{ env.BWS_APP_ID }}",
                "private-key": "${{ env.BWS_GITHUB_APP_PRIVATE_KEY }}",
                "preset": "readonly",
                "repositories": "console,renet,account,elite,homebrew-tap",
            },
        },
        {
            "name": "Drop the App credentials from the job environment",
            "run": 'echo "BWS_GITHUB_APP_PRIVATE_KEY=" >> "$GITHUB_ENV"\necho "BWS_APP_ID=" >> "$GITHUB_ENV"\n',
        },
        token_checkout(),
        {
            "name": "Drop the App token from the global git config",
            "run": "\n".join(ci_workflow_invariants._PINS_GIT_SCRUB_LINES) + "\n",
        },
    ]


def token_checkout() -> dict:
    return {
        "uses": PINNED_CHECKOUT,
        "with": {
            "submodules": True,
            "token": "${{ steps.app-token.outputs.token }}",
            "persist-credentials": False,
        },
    }


def token_doc() -> dict:
    """pins_doc with the admitted shape after its first checkout: index 1 is bws-secrets, 2 app-token, 3 the blanking step, 4 the checkout, 5 the git config scrub."""
    doc = pins_doc()
    doc["jobs"]["soaked"]["steps"][1:1] = token_triple()
    return doc


def _tok_steps(d: dict) -> list[dict]:
    return d["jobs"]["soaked"]["steps"]


def test_the_admitted_read_only_checkout_token_passes() -> None:
    findings, shape = ci_workflow_invariants.analyse_pins_soaked(token_doc())
    assert findings == []
    assert shape[1].startswith("1 read-only checkout token(s)")


def test_two_back_to_back_token_checkouts_before_the_scrub_pass() -> None:
    doc = token_doc()
    _tok_steps(doc).insert(5, token_checkout())
    assert pins_kinds(doc) == []


def test_the_pinned_git_scrub_is_the_text_the_workflow_carries() -> None:
    """The scrub lines the invariant demands are the ones a shell run proved; the workflow passing the gate is the other half."""
    lines = ci_workflow_invariants._PINS_GIT_SCRUB_LINES
    assert any("--unset-all" in ln for ln in lines)
    assert lines[-3].startswith("if git config --global --get-regexp 'x-access-token'")


def _git_scrub_edit(old: str, new: str) -> typing.Callable[[dict], None]:
    def edit(d: dict) -> None:
        step = _tok_steps(d)[5]
        assert old in step["run"]
        step["run"] = step["run"].replace(old, new)

    return edit


def test_the_admitted_token_tolerates_whitespace_inside_its_expressions() -> None:
    doc = token_doc()
    _tok_steps(doc)[2]["with"]["client-id"] = "${{env.BWS_APP_ID}}"
    _tok_steps(doc)[4]["with"]["token"] = "${{steps.app-token.outputs.token}}"
    assert pins_kinds(doc) == []


@pytest.mark.parametrize(
    ("mutate", "why"),
    [
        # the shapes the ruling names
        (lambda d: _tok_steps(d)[2]["with"].__setitem__("preset", "pr-read"), "not readonly"),
        (lambda d: _tok_steps(d)[2]["with"].__setitem__("preset", "cd"), "not readonly"),
        (lambda d: _tok_steps(d)[2]["with"].pop("preset"), "no `preset:`"),
        (
            lambda d: _tok_steps(d)[1]["with"].__setitem__(
                "secrets",
                "GITHUB_APP_PRIVATE_KEY > BWS_GITHUB_APP_PRIVATE_KEY\nGITHUB_APP_ID > BWS_APP_ID\nCLOUDFLARE_API_TOKEN\n",
            ),
            "may fetch only",
        ),
        (
            lambda d: _tok_steps(d)[1]["with"].__setitem__(
                "secrets",
                "CF_DEPLOY_KEY > BWS_GITHUB_APP_PRIVATE_KEY\nGITHUB_APP_ID > BWS_APP_ID\n",
            ),
            "may fetch only",
        ),
        (
            lambda d: _tok_steps(d).append({"run": "echo ${{ steps.app-token.outputs.token }}"}),
            "steps.app-token is read at jobs.soaked.steps.",
        ),
        (
            lambda d: _tok_steps(d).append(
                {
                    "uses": "some/action@sha",
                    "with": {"gh-token": "${{ steps.app-token.outputs.token }}"},
                }
            ),
            "steps.app-token is read at jobs.soaked.steps.",
        ),
        (
            lambda d: d["jobs"]["soaked"].__setitem__(
                "env", {"GH_TOKEN": "${{ steps.app-token.outputs.token }}"}
            ),
            "steps.app-token is read at jobs.soaked.env.GH_TOKEN",
        ),
        (
            lambda d: _tok_steps(d).extend(token_triple()),
            "exactly one bws-secrets and one app-token step in the job, found 2 and 2",
        ),
        (
            lambda d: _tok_steps(d)[1]["with"].__setitem__(
                "access-token", "${{ secrets.BWS_ACCESS_TOKEN }}${{ secrets.DEPLOY_KEY }}"
            ),
            "access-token must be",
        ),
        (
            lambda d: _tok_steps(d)[1].__setitem__("env", {"K": "${{ secrets.DEPLOY_KEY }}"}),
            "bws-secrets step carries env",
        ),
        (
            lambda d: _tok_steps(d)[1]["with"].__setitem__(
                "secrets",
                "GITHUB_APP_PRIVATE_KEY > BWS_GITHUB_APP_PRIVATE_KEY\nGITHUB_APP_ID > ${{ secrets.X }}\n",
            ),
            "no expression or comment",
        ),
        # the blanking step, the ordering and the checkout itself
        (lambda d: _tok_steps(d).pop(3), "the step right after app-token must be exactly"),
        (
            lambda d: _tok_steps(d)[3].__setitem__(
                "run", 'echo "BWS_GITHUB_APP_PRIVATE_KEY=" >> "$GITHUB_ENV"\n'
            ),
            "the step right after app-token must be exactly",
        ),
        (
            lambda d: _tok_steps(d).insert(2, {"run": "true"}),
            "app-token must directly follow bws-secrets",
        ),
        (
            lambda d: _tok_steps(d)[4].__setitem__("uses", "actions/checkout@v7"),
            "steps.app-token is read at jobs.soaked.steps.4.with.token",
        ),
        (
            lambda d: _tok_steps(d).insert(0, _tok_steps(d).pop(4)),
            "steps.app-token is read at jobs.soaked.steps.0.with.token",
        ),
        (
            lambda d: _tok_steps(d)[4]["with"].pop("token"),
            "no SHA-pinned actions/checkout after the blanking step takes the token",
        ),
        (lambda d: _tok_steps(d)[2].pop("id"), "app-token step has no `id`"),
        (
            lambda d: _tok_steps(d)[2]["with"].__setitem__(
                "private-key", "${{ secrets.GITHUB_APP_PRIVATE_KEY }}"
            ),
            "private-key must be",
        ),
        (
            lambda d: d["jobs"]["soaked"].__setitem__("outputs", {"t": "${{ toJSON(steps) }}"}),
            "steps.app-token is read at jobs.soaked.outputs.t",
        ),
        # persisted credentials and the global git config entry app-token leaves behind
        (
            lambda d: _tok_steps(d)[4]["with"].pop("persist-credentials"),
            "must set `persist-credentials: false`",
        ),
        (
            lambda d: _tok_steps(d)[4]["with"].__setitem__("persist-credentials", True),
            "must set `persist-credentials: false`",
        ),
        (
            lambda d: _tok_steps(d)[4]["with"].__setitem__("persist-credentials", "true"),
            "must set `persist-credentials: false`",
        ),
        (lambda d: _tok_steps(d).pop(5), "must be exactly the global git config scrub"),
        (
            lambda d: _tok_steps(d).insert(5, {"run": "true"}),
            "must be exactly the global git config scrub",
        ),
        (
            lambda d: _tok_steps(d).insert(5, {"uses": "./.github/actions/profiler"}),
            "must be exactly the global git config scrub",
        ),
        (
            _git_scrub_edit("*x-access-token*)", "*nomatch*)"),
            "must be exactly the global git config scrub",
        ),
        (
            _git_scrub_edit('git config --global --unset-all "$key"', "true"),
            "must be exactly the global git config scrub",
        ),
        (
            _git_scrub_edit("exit 1", "exit 0"),
            "must be exactly the global git config scrub",
        ),
        (
            lambda d: _tok_steps(d)[5].__setitem__("shell", "sh"),
            "must be exactly the global git config scrub",
        ),
        (
            lambda d: _tok_steps(d).insert(7, token_checkout()),
            "must run back to back right after the blanking step",
        ),
    ],
)
def test_any_other_checkout_token_shape_is_refused(mutate, why) -> None:
    doc = token_doc()
    mutate(doc)
    findings = ci_workflow_invariants.analyse_pins_soaked(doc)[0]
    assert {k for k, _n in findings} == {"pins-soaked-writes"}, findings
    assert any(why in n for _k, n in findings), findings


@pytest.mark.parametrize(
    "step",
    [
        {"run": './tool "$BWS_GITHUB_APP_PRIVATE_KEY"'},
        {"run": "./tool", "env": {"K": "${{ env.BWS_APP_ID }}"}},
        {"run": "./tool", "env": {"K": "${{ toJSON(env) }}"}},
        {"uses": "some/action@sha", "with": {"k": "${{ env['BWS_GITHUB_APP_PRIVATE_KEY'] }}"}},
    ],
)
def test_a_later_step_reading_a_bws_value_is_refused(step) -> None:
    doc = token_doc()
    _tok_steps(doc).append(step)
    findings = ci_workflow_invariants.analyse_pins_soaked(doc)[0]
    assert [k for k, _n in findings] == ["pins-soaked-writes"], findings
    assert "reads a BWS_* value" in findings[0][1]


def test_a_bws_value_in_the_job_or_workflow_env_is_refused() -> None:
    doc = token_doc()
    doc["jobs"]["soaked"]["env"] = {"K": "${{ env.BWS_GITHUB_APP_PRIVATE_KEY }}"}
    assert pins_kinds(doc) == ["pins-soaked-writes"]
    doc = token_doc()
    doc["env"] = {"K": "$BWS_APP_ID"}
    assert pins_kinds(doc) == ["pins-soaked-writes"]


def test_a_blanking_step_without_the_token_steps_is_still_a_bws_read() -> None:
    doc = pins_doc()
    _tok_steps(doc).append(token_triple()[2])
    assert pins_kinds(doc) == ["pins-soaked-writes"]


# CASE. GitHub resolves context names and the steps context in any case (actions/runner DictionaryContextData, StringComparer.OrdinalIgnoreCase), and env too on Windows, so every read pattern must see every spelling.
@pytest.mark.parametrize(
    ("step", "why"),
    [
        (
            {"run": "echo ${{ steps.APP-TOKEN.outputs.token }}"},
            "steps.app-token is read at jobs.soaked.steps.6.run",
        ),
        (
            {"run": "x", "env": {"T": "${{ steps.App-Token.outputs.token }}"}},
            "steps.app-token is read at jobs.soaked.steps.6.env.T",
        ),
        (
            {"run": "echo ${{ STEPS.app-token.outputs.token }}"},
            "steps.app-token is read at jobs.soaked.steps.6.run",
        ),
        (
            {"run": "echo ${{ toJSON(STEPS) }}"},
            "steps.app-token is read at jobs.soaked.steps.6.run",
        ),
        (
            {"run": "x", "env": {"K": "${{ env.bws_app_id }}"}},
            "reads a BWS_* value",
        ),
        (
            {"run": "x", "env": {"K": "${{ ENV['Bws_Github_App_Private_Key'] }}"}},
            "reads a BWS_* value",
        ),
        ({"run": "x", "env": {"K": "${{ toJSON(ENV) }}"}}, "reads a BWS_* value"),
        ({"run": "Write-Output $env:bws_app_id"}, "reads a BWS_* value"),
    ],
)
def test_a_read_in_any_case_is_still_a_read(step, why) -> None:
    doc = token_doc()
    _tok_steps(doc).insert(6, step)
    findings = ci_workflow_invariants.analyse_pins_soaked(doc)[0]
    assert {k for k, _n in findings} == {"pins-soaked-writes"}, findings
    assert any(why in n for _k, n in findings), findings


@pytest.mark.parametrize(
    "step",
    [
        {"run": "./tool ${{ SECRETS.DEPLOY_KEY }}"},
        {"run": "./tool ${{ Secrets['DEPLOY_KEY'] }}"},
        {"run": "x", "if": "SECRETS.K != ''"},
        {"run": "Git Push origin HEAD"},
        {"run": "GH PR create --fill"},
        {"run": "curl -X post https://api.github.com/x"},
        {"uses": "./.github/actions/App-Token", "with": {"preset": "cd"}},
        {"uses": "peter-evans/Create-Pull-Request@sha"},
    ],
)
def test_a_write_in_any_case_is_still_a_write(step) -> None:
    doc = token_doc()
    _tok_steps(doc).append(step)
    assert pins_kinds(doc) == ["pins-soaked-writes"]


def test_the_default_token_is_exempt_only_in_its_exact_spelling() -> None:
    doc = token_doc()
    _tok_steps(doc).append(
        {"uses": "some/action@sha", "with": {"t": "${{ secrets.GITHUB_TOKEN }}"}}
    )
    assert pins_kinds(doc) == []
    doc = token_doc()
    _tok_steps(doc).append(
        {"uses": "some/action@sha", "with": {"t": "${{ secrets.github_token }}"}}
    )
    assert pins_kinds(doc) == ["pins-soaked-writes"]


@pytest.mark.parametrize(
    "run",
    [
        "curl --request PUT https://api.github.com/x",
        "curl -XDELETE https://api.github.com/x",
        "curl -d @body.json https://api.github.com/x",
        "curl --data-binary @f https://api.github.com/x",
        "curl -F f=@x https://api.github.com/x",
        "curl --json '{}' https://api.github.com/x",
        "curl -d'{\"a\":1}' https://api.github.com/x",
        "curl -d@body.json https://api.github.com/x",
        "curl -sSd x https://api.github.com/x",
        "curl -Tfile https://api.github.com/x",
        "curl --form-string f=x https://api.github.com/x",
        "curl -sSX POST https://api.github.com/x",
        'curl "https://api.github.com/x?a=1&b=2" -X POST',
        "curl 'https://api.github.com/x?a=1&b=2' -d @body",
    ],
)
def test_a_curl_method_or_body_flag_is_a_write(run) -> None:
    doc = token_doc()
    _tok_steps(doc).append({"run": run})
    assert pins_kinds(doc) == ["pins-soaked-writes"]


@pytest.mark.parametrize(
    "run",
    [
        "curl -fsSL https://example.com/delete-notes -o notes",
        "curl -fsSL https://example.com/put/patch/post.txt",
        "curl -x http://proxy:3128 -D headers.txt https://example.com/a",
        "curl -fsSL -o out https://example.com/a",
        "curl -fsSL https://example.com/a | cut -d: -f1",
        "curl -fsSL https://example.com/a | grep -Fq x && echo ok",
    ],
)
def test_a_method_word_in_a_curl_url_is_a_read(run) -> None:
    doc = token_doc()
    _tok_steps(doc).append({"run": run})
    assert pins_kinds(doc) == []


def test_a_checkout_input_spelled_twice_in_different_case_is_refused() -> None:
    doc = token_doc()
    _tok_steps(doc)[4]["with"]["Persist-Credentials"] = True
    findings = ci_workflow_invariants.analyse_pins_soaked(doc)[0]
    assert {k for k, _n in findings} == {"pins-soaked-writes"}
    assert any("spells one input twice in different case" in n for _k, n in findings), findings


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: _tok_steps(d)[4]["with"].__setitem__(
            "token", "${{ steps.APP-TOKEN.outputs.token }}"
        ),
        lambda d: _tok_steps(d)[2]["with"].__setitem__("preset", "READONLY"),
        lambda d: _tok_steps(d)[1]["with"].__setitem__(
            "access-token", "${{ SECRETS.bws_access_token }}"
        ),
        lambda d: _tok_steps(d)[1].__setitem__("uses", "./.github/actions/BWS-Secrets"),
    ],
)
def test_an_admitted_shape_in_another_case_is_refused_not_admitted(mutate) -> None:
    """The admitting side stays exact: a respelled admitted value costs a rewrite, never a hole."""
    doc = token_doc()
    mutate(doc)
    kinds = pins_kinds(doc)
    assert kinds
    assert set(kinds) == {"pins-soaked-writes"}


# ---- the workflow-estate pins (2026-10-23; asked for by the Stop hook's regression judge) ----
#
# Two fixes landed that day that no check could catch. `pipe-no-pipefail` (commit 41437ea6f): cf-usage-report.yml piped its report into `tee` under GitHub's implicit `bash -e {0}`, which has no pipefail, so a failing report passed green. `dispatch-write-off-default-branch` (commit f8d184807): obs-ceph-autobump.yml's cd-token job could be dispatched from any branch. Each rule below is driven in both directions over literal documents, over the two pre-fix files read from git history, and over the real tree in the real invocation.

PIPEFAIL_FIX = "41437ea6fec97878060164859b01984c1108d32a"
DISPATCH_FIX = "f8d184807ca93051f04bd554b68adfddd5dd81d5"
GUARD = ci_workflow_invariants.DEFAULT_BRANCH_GUARD


def git_blob(rev: str, path: str) -> str:
    """A tracked file at a revision. A missing object FAILS: quality-pytest checks out with fetch-depth 0, and check:ci-pytest refuses a skip anyway, so an unreachable commit means this control did not run."""
    show = subprocess.run(
        ["git", "show", "%s:%s" % (rev, path)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    assert show.returncode == 0, "cannot read %s:%s (%s)" % (rev, path, show.stderr.strip())
    return show.stdout


def yaml_doc(text: str) -> object:
    """In-process parse through `rediacc_ci.workflows`, the PyYAML-agreeing subset parser: the pytest interpreter cannot import PyYAML (an isolated uv venv), while the subject's own subprocess runs below use the system interpreter, which can."""
    return workflows.parse(text)


def pipe_doc(
    run: str,
    *,
    shell: str | None = None,
    job_shell: str | None = None,
    top_shell: str | None = None,
    runs_on: str = "ubuntu-latest",
) -> dict:
    step: dict = {"name": "report", "run": run}
    if shell is not None:
        step["shell"] = shell
    job: dict = {"runs-on": runs_on, "steps": [step]}
    if job_shell is not None:
        job["defaults"] = {"run": {"shell": job_shell}}
    doc: dict = {"on": {"push": None}, "jobs": {"report": job}}
    if top_shell is not None:
        doc["defaults"] = {"run": {"shell": top_shell}}
    return doc


def pipe_kinds(doc: object) -> list[str]:
    return [k for k, _n in ci_workflow_invariants.analyse_pipefail(doc)[0]]


TEE_RUN = (
    'PYTHONPATH=.ci python3 -m rediacc_ci.ops.cf_usage_report | tee -a "$GITHUB_STEP_SUMMARY"\n'
)


def test_a_pipe_under_the_implicit_shell_is_refused() -> None:
    findings, runs, pipes = ci_workflow_invariants.analyse_pipefail(pipe_doc(TEE_RUN))
    assert (runs, pipes) == (1, 1)
    assert [k for k, _n in findings] == ["pipe-no-pipefail"]
    assert "the implicit `bash -e {0}`" in findings[0][1]
    assert "report step 1 (report): line 1" in findings[0][1]


@pytest.mark.parametrize(
    "kw",
    [
        {"shell": "bash"},
        {"job_shell": "bash"},
        {"top_shell": "bash"},
        {"shell": "bash --noprofile --norc -eo pipefail {0}"},
        {"shell": "pwsh"},
        {"shell": "python"},
        {"runs_on": "windows-latest"},
    ],
)
def test_a_pipe_under_bash_or_a_non_posix_shell_passes(kw) -> None:
    assert pipe_kinds(pipe_doc(TEE_RUN, **kw)) == []


@pytest.mark.parametrize(
    "kw",
    [
        {"shell": "sh"},
        {"shell": "bash {0}"},
        {"job_shell": "sh"},
        # A matrix runner may be linux, so the implicit shell may be bash -e.
        {"runs_on": "${{ matrix.os }}"},
        # A step's own shell beats a safe default.
        {"shell": "sh", "job_shell": "bash"},
    ],
)
def test_a_pipe_under_a_shell_without_pipefail_is_refused(kw) -> None:
    assert pipe_kinds(pipe_doc(TEE_RUN, **kw)) == ["pipe-no-pipefail"]


@pytest.mark.parametrize(
    "prefix",
    [
        "set -o pipefail\n",
        "set -euo pipefail\n",
        "set -Eeuo pipefail\n",
        "set -e -o pipefail\n",
        "set -o pipefail; ",
    ],
)
def test_set_pipefail_on_or_before_the_pipe_passes(prefix) -> None:
    assert pipe_kinds(pipe_doc(prefix + TEE_RUN)) == []


@pytest.mark.parametrize(
    "run",
    [
        TEE_RUN + "set -o pipefail\n",
        "# set -o pipefail\n" + TEE_RUN,
        "echo 'set -o pipefail'\n" + TEE_RUN,
        "set +o pipefail\n" + TEE_RUN,
    ],
)
def test_a_pipefail_after_the_pipe_or_in_text_does_not_count(run) -> None:
    assert pipe_kinds(pipe_doc(run)) == ["pipe-no-pipefail"]


@pytest.mark.parametrize(
    "run",
    [
        'x="$(df -BG / | tail -n1)"\n',
        'x=$(echo "$S" | jq -r .ip)\n',
        "a |& tee log\n",
        "a \\\n  | tee log\n",
        "curl -fsSL https://x |\n  sh\n",
        'echo "$(printf "%s" "$(id | cut -c1)")"\n',
    ],
)
def test_every_real_pipe_spelling_is_read(run) -> None:
    assert ci_workflow_invariants.pipe_lines(run), run
    assert pipe_kinds(pipe_doc(run)) == ["pipe-no-pipefail"]


@pytest.mark.parametrize(
    "run",
    [
        "a || b\n",
        "echo 'a | b'\n",
        'echo "a | b"\n',
        "echo hi # a | b\n",
        "echo hi >| out\n",
        "echo ${{ inputs.a || 'x' }}\n",
        "jq -r '.regions[] | .domain' regions.json > out\n",
        "cat <<'EOF'\na | b\nEOF\necho done\n",
        "cat <<-EOF\n\ta | b\n\tEOF\necho done\n",
        'case "$x" in\n  a|b) echo ab ;;\n  *) echo other ;;\nesac\n',
        "x=$((1 | 2))\n",
    ],
)
def test_text_that_only_looks_like_a_pipe_is_not_one(run) -> None:
    """The NEGATIVE direction: without it the rule could be red on every run step in the tree."""
    assert ci_workflow_invariants.pipe_lines(run) == [], run
    assert pipe_kinds(pipe_doc(run)) == []


def test_a_heredoc_does_not_swallow_the_pipe_after_it() -> None:
    run = "cat <<EOF > f\nbody\nEOF\na | tee log\n"
    assert ci_workflow_invariants.pipe_lines(run) == [4]


def test_composite_action_steps_are_read() -> None:
    action = {"runs": {"using": "composite", "steps": [{"run": TEE_RUN, "shell": "sh"}]}}
    assert pipe_kinds(action) == ["pipe-no-pipefail"]
    action["runs"]["steps"][0]["shell"] = "bash"
    assert pipe_kinds(action) == []


def test_the_pre_fix_cf_usage_report_is_refused_and_the_fix_passes() -> None:
    """THE HISTORICAL CONTROL for 41437ea6f: the file before the fix is red, the file the fix wrote is green."""
    path = ".github/workflows/cf-usage-report.yml"
    before = ci_workflow_invariants.analyse_pipefail(yaml_doc(git_blob(PIPEFAIL_FIX + "^", path)))[
        0
    ]
    assert [k for k, _n in before] == ["pipe-no-pipefail"], before
    assert "the implicit `bash -e {0}`" in before[0][1]
    after = ci_workflow_invariants.analyse_pipefail(yaml_doc(git_blob(PIPEFAIL_FIX, path)))
    assert after[0] == [], after
    assert after[2] == 1, after


def test_the_ct_tests_drill_steps_pass_on_set_pipefail() -> None:
    """The drill universe, transfer and backup steps pipe into tee under `set -o pipefail` and no `shell: bash`; they must pass, and they must really pipe (or this proves nothing)."""
    doc = yaml_doc((ROOT / ".github/workflows/ct-tests.yml").read_text(encoding="utf-8"))
    assert isinstance(doc, dict)
    drills = [
        (jname, st)
        for jname, job in doc["jobs"].items()
        for st in ci_workflow_invariants._steps(job)
        if re.search(r"run\.sh drill (universe|transfer|backup)", str(st.get("run") or ""))
        and "| tee" in str(st.get("run"))
    ]
    assert len(drills) == 3, [st.get("name") for _j, st in drills]
    for jname, st in drills:
        assert not st.get("shell"), st.get("name")
        assert ci_workflow_invariants.pipe_lines(st["run"]), st.get("name")
        sub = {"jobs": {jname: {"runs-on": "ubuntu-latest", "steps": [st]}}}
        assert pipe_kinds(sub) == [], st.get("name")


def dispatch_doc(
    *,
    job_if: str | None = None,
    preset: str | None = "cd",
    perms: object = None,
    trigger: str = "workflow_dispatch",
) -> dict:
    with_ = {"client-id": "x", "private-key": "y"}
    if preset is not None:
        with_["preset"] = preset
    job: dict = {
        "runs-on": "ubuntu-latest",
        "steps": [
            {"id": "app-token", "uses": "./.github/actions/app-token", "with": with_},
            {"run": "git push"},
        ],
    }
    if job_if is not None:
        job["if"] = job_if
    if perms is not None:
        job["permissions"] = perms
    return {"on": {trigger: None}, "jobs": {"land": job}}


def dispatch_kinds(doc: object, load=None) -> list[str]:
    return [k for k, _n in ci_workflow_invariants.analyse_dispatch(doc, load)[0]]


@pytest.mark.parametrize(
    "kw",
    [
        {},
        {"job_if": "needs.plan.outputs.action == 'bump'"},
        {"preset": "housekeeping"},
        {"preset": "${{ inputs.preset }}"},
        {"preset": None, "perms": {"contents": "write"}},
        {"preset": None, "perms": "write-all"},
        # A guard that an OR or a negation can bypass guards nothing.
        {"job_if": GUARD + " || github.event_name == 'workflow_dispatch'"},
        {"job_if": "!(" + GUARD + ")"},
        {
            "job_if": "github.ref != format('refs/heads/{0}', github.event.repository.default_branch)"
        },
        {"job_if": "github.ref == 'refs/heads/feature'"},
    ],
)
def test_a_write_capable_dispatch_job_without_the_guard_is_refused(kw) -> None:
    assert dispatch_kinds(dispatch_doc(**kw)) == ["dispatch-write-off-default-branch"]


@pytest.mark.parametrize(
    "kw",
    [
        {"job_if": GUARD},
        {"job_if": "${{ " + GUARD + " }}"},
        {"job_if": GUARD + " && needs.plan.outputs.action == 'bump'"},
        {"job_if": "always() && (" + GUARD + ") && (a == 'b' || c == 'd')"},
        {
            "job_if": "format('refs/heads/{0}', github.event.repository.default_branch) == github.ref"
        },
        {"job_if": "  " + GUARD.replace(" == ", "  ==  ") + "\n  && success()"},
        {"preset": "readonly"},
        {"preset": "pr-read"},
        {"preset": None},
        {"preset": None, "perms": {"contents": "read"}},
        {"trigger": "push"},
    ],
)
def test_a_guarded_read_only_or_undispatchable_job_passes(kw) -> None:
    assert dispatch_kinds(dispatch_doc(**kw)) == []


def test_workflow_level_contents_write_reaches_a_job_without_its_own_block() -> None:
    doc = dispatch_doc(preset=None)
    doc["permissions"] = {"contents": "write"}
    assert dispatch_kinds(doc) == ["dispatch-write-off-default-branch"]
    doc["jobs"]["land"]["permissions"] = {"contents": "read"}
    assert dispatch_kinds(doc) == []


def test_a_call_to_a_local_reusable_workflow_that_writes_is_write_capable() -> None:
    callee = dispatch_doc(job_if=GUARD)
    callee["on"] = {"workflow_call": None}
    caller = {
        "on": {"workflow_dispatch": None},
        "jobs": {"deploy": {"uses": "./.github/workflows/deploy.yml", "secrets": "inherit"}},
    }
    files = {".github/workflows/deploy.yml": callee}
    findings = ci_workflow_invariants.analyse_dispatch(caller, files.get)[0]
    assert [k for k, _n in findings] == ["dispatch-write-off-default-branch"]
    assert "calls ./.github/workflows/deploy.yml, whose job land can write" in findings[0][1]
    caller["jobs"]["deploy"]["if"] = GUARD
    assert dispatch_kinds(caller, files.get) == []
    callee["jobs"]["land"]["steps"][0]["with"]["preset"] = "readonly"
    caller["jobs"]["deploy"].pop("if")
    assert dispatch_kinds(caller, files.get) == []


def test_a_reusable_workflow_cycle_terminates() -> None:
    a = {
        "on": {"workflow_dispatch": None, "workflow_call": None},
        "jobs": {"j": {"uses": "./.github/workflows/b.yml"}},
    }
    b = {"on": {"workflow_call": None}, "jobs": {"j": {"uses": "./.github/workflows/a.yml"}}}
    files = {".github/workflows/a.yml": a, ".github/workflows/b.yml": b}
    assert dispatch_kinds(a, files.get) == []


def test_the_pre_fix_obs_ceph_autobump_is_refused_and_the_fix_passes() -> None:
    """THE HISTORICAL CONTROL for f8d184807: the pre-fix `land` job (cd preset, no ref guard) is red; the fixed file is green with its write job counted."""
    path = ".github/workflows/obs-ceph-autobump.yml"
    before = ci_workflow_invariants.analyse_dispatch(yaml_doc(git_blob(DISPATCH_FIX + "^", path)))[
        0
    ]
    assert [k for k, _n in before] == ["dispatch-write-off-default-branch"], before
    assert before[0][1].startswith("job land ("), before
    assert "preset cd" in before[0][1], before
    after = ci_workflow_invariants.analyse_dispatch(yaml_doc(git_blob(DISPATCH_FIX, path)))
    assert after == ([], 1), after


def test_every_estate_kind_has_a_message() -> None:
    for kind in ci_workflow_invariants.PIPEFAIL_KINDS + ci_workflow_invariants.DISPATCH_KINDS:
        assert ci_workflow_invariants.estate_message_for(kind, "0", "x") is not None, kind


def test_an_empty_estate_is_an_error_never_a_pass(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(ci_workflow_invariants, "load_workflow", workflows.load)
    errors, info = ci_workflow_invariants._estate_phase(str(tmp_path))
    assert info == []
    assert len(errors) == 1, errors
    assert "nothing to check cannot pass" in errors[0]
    (tmp_path / ".github/workflows").mkdir(parents=True)
    (tmp_path / ".github/workflows/x.yml").write_text(
        "on: push\njobs:\n  a:\n    steps:\n      - uses: x@y\n"
    )
    errors, info = ci_workflow_invariants._estate_phase(str(tmp_path))
    assert info == []
    assert len(errors) == 1, errors
    assert "no `run:` step found" in errors[0]


ESTATE_PROBE = (
    "import json, sys\n"
    "from rediacc_ci.security import ci_workflow_invariants as m\n"
    "print(json.dumps(m._estate_phase(sys.argv[1])))\n"
)


def test_the_real_workflow_estate_holds() -> None:
    """The real tree, every workflow and composite action, through the subject's own PyYAML loader in the system interpreter, with the shape asserted so a collapse is visible."""
    proc = subprocess.run(
        [PYTHON, "-c", ESTATE_PROBE, str(ROOT)],
        env=env_for(),
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
    errors, info = json.loads(proc.stdout)
    assert errors == [], "\n".join(errors)
    m = re.match(
        r"workflow estate holds: (\d+) file\(s\), (\d+) run step\(s\), (\d+) piping", info[0]
    )
    assert m, info
    files, runs, pipes = (int(g) for g in m.groups())
    assert files >= 30, info[0]
    assert runs >= 500, info[0]
    assert pipes >= 10, info[0]


def test_planted_violations_in_a_copy_of_the_real_tree_go_red(tmp_path) -> None:
    """THE CONTROL ON THE REAL INVOCATION: the port's main over a copy of the real .github, with the two 2026-10-23 fixes reverted in place, names both files; the unplanted copy is the real tree's own verdict."""
    shutil.copytree(ROOT / ".github", tmp_path / ".github")
    cf = tmp_path / ".github/workflows/cf-usage-report.yml"
    cf.write_text(
        cut_once(cf.read_text(encoding="utf-8"), "        shell: bash\n", ""), encoding="utf-8"
    )
    obs = tmp_path / ".github/workflows/obs-ceph-autobump.yml"
    obs.write_text(
        cut_once(
            obs.read_text(encoding="utf-8"),
            "    if: " + GUARD + " && needs.plan.outputs.action == 'bump'\n",
            "    if: needs.plan.outputs.action == 'bump'\n",
        ),
        encoding="utf-8",
    )
    proc = subprocess.run(
        [PYTHON, str(PORT)],
        env=env_for(REDIACC_CI_ROOT=str(tmp_path)),
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    assert proc.returncode == 1, proc.stderr
    assert "pipe-no-pipefail: .github/workflows/cf-usage-report.yml: report step" in proc.stderr
    assert (
        "dispatch-write-off-default-branch: .github/workflows/obs-ceph-autobump.yml: job land ("
        in proc.stderr
    )


def test_the_estate_reads_every_workflow_and_action_check_ci_workflows_reads() -> None:
    """A file the estate skips is a file both pins pass unread; `check:ci-workflows`' own walk is the reference set, including the nested profiler/nest-probe action."""
    estate = set(ci_workflow_invariants.estate_files(str(ROOT)))
    reference = {p.replace(os.sep, "/") for p in quality_workflows.github_yamls(ROOT)}
    unread = {
        p
        for p in reference - estate
        if p.startswith(".github/workflows/") or p.endswith("/action.yml")
    }
    assert unread == set(), unread
    assert ".github/actions/profiler/nest-probe/action.yml" in estate
    assert len(estate) >= 30, sorted(estate)
