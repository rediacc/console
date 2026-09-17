"""Differential: `rediacc_ci.security.ci_workflow_invariants` against its twin
`.ci/scripts/security/check-ci-workflow-invariants.sh`.

THE COMPARISON IS BYTE FOR BYTE ON BOTH STREAMS, with exactly one exemption (the traceback case, which names a different file on each side and says so in its own docstring). That standard is affordable because 103 of the twin's 224 lines were ALREADY Python inside a `python3 - <<'PY'` heredoc (`:66-168`), so anything short of byte equality would be a transcription error rather than
a legitimate rewrite.

NO FAKES, AND THAT IS A MEASURED CLAIM RATHER THAN AN ASSUMPTION. The twin
shells out to exactly one binary, `python3`, and only to run the heredoc; there
is no `yq`, no `jq`, no `gh`, no network.

    $ grep -nE '(^|[^a-z-])(yq|jq|gh|curl|wget|git) ' \\
        .ci/scripts/security/check-ci-workflow-invariants.sh
    (no output)

So every case here drives both sides over a FIXTURE workflow through `$WORKFLOW_FILE`, the seam the twin already exposes for its own gate test, and one case drives both over the real `.github/workflows/ci.yml`.

WHY A BASELINE-GREEN FIXTURE EXISTS. Without it a case asserting exit 1 proves nothing, because the fixture might have been red for a reason the case did not plant. `test_the_baseline_fixture_is_green` is the control every other fixture
case leans on.

K=5 LEDGER: `.ci/shadow/w7p6-check-ci-workflow-invariants.observations.jsonl`.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import typing

from rediacc_ci import paths
from rediacc_ci.security import ci_workflow_invariants
from rediacc_ci.tests import differential

if typing.TYPE_CHECKING:  # pragma: no cover - annotations only
    import pathlib

ROOT = paths.repo_root()
TWIN = ROOT / ".ci/scripts/security/check-ci-workflow-invariants.sh"
PORT = ROOT / ".ci/rediacc_ci/security/ci_workflow_invariants.py"

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
    # NO `on:` KEY HERE, and that is not an oversight. PyYAML implements YAML 1.1, where the bare word `on` is a BOOLEAN, so `yaml.safe_load("on: push")`
    # returns `{True: "push"}` rather than `{"on": "push"}`. Neither
    # implementation reads the key, so the omission changes no verdict, and `test_the_literal_document_matches_the_baseline_yaml` compares the `jobs` subtree for exactly this reason.
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


def write(tmp_path: pathlib.Path, body: str, name: str = "wf.yml") -> pathlib.Path:
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    return path


def _env(**extra: str) -> dict[str, str]:
    """REPLACES the caller's environment; see `differential.BASE_ENV`.

    `PYTHONPATH` is set for BOTH sides even though only the port needs it, so the two children differ in nothing except which program they run. `REDIACC_CI_ROOT` is deliberately absent: it is the one seam the port has and the twin does not.
    """
    env = differential.env_for(
        PYTHONPATH=str(ROOT / ".ci"),
        PYTHONDONTWRITEBYTECODE="1",
    )
    env.update(extra)
    return env


def run_both(workflow: pathlib.Path | str, **extra: str) -> tuple[tuple, tuple]:
    """Both implementations, same input, same environment. Streams never merged."""
    results = []
    for argv in (["bash", str(TWIN)], ["python3", str(PORT)]):
        proc = subprocess.run(
            argv,
            env=_env(WORKFLOW_FILE=str(workflow), **extra),
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )
        results.append((proc.returncode, proc.stdout, proc.stderr))
    return results[0], results[1]


def assert_same(old: tuple, new: tuple) -> None:
    assert new[0] == old[0], "exit: twin %s, port %s" % (old[0], new[0])
    assert new[1] == old[1], "stdout:\n--- twin\n%s--- port\n%s" % (old[1], new[1])
    assert new[2] == old[2], "stderr:\n--- twin\n%s--- port\n%s" % (old[2], new[2])


def _path_without_python(tmp_path: pathlib.Path) -> pathlib.Path:
    """A scratch bin holding every tool on PATH EXCEPT any python interpreter.

    Built by mirroring rather than by naming the handful of tools the twin needs, because that list is not stable: the first version of this case symlinked only `dirname` and the twin then died on `uname`, which `common.sh:64` calls at SOURCE time. A mirror cannot go stale that way, and the thing under test -- "python3 is not resolvable" -- is stated once.
    """
    bindir = tmp_path / "nopython-bin"
    bindir.mkdir()
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


def assert_red(old: tuple, token: str) -> None:
    """Anti-vacuity for one case: the twin really did fail, for the reason meant.

    Two implementations that both print nothing and both exit 0 agree perfectly
    and prove nothing; `scripts/lib/shadow-gate.ts` calls that VACUOUS_BOTH_EMPTY
    and refuses it, and this is the same refusal inside the differential.
    """
    assert old[0] == 1, "expected the twin to fail, got exit %s\n%s" % (old[0], old[2])
    assert token in old[2], "expected %r in the twin's stderr, got:\n%s" % (token, old[2])


# --------------------------------------------------------------------------- The real repository ---------------------------------------------------------------------------


def test_the_real_repository_agrees() -> None:
    """The clean-tree case, over the real `.github/workflows/ci.yml`.

    Kept alongside the fixtures because the real file is the only input where the `stagers`, `initialize`, `validate-install`, `validate-promote` and `finalize-release-sentinel` jobs all exist at once with their real `if:` text, and because a fixture cannot notice a rename landing in ci.yml.
    """
    results = []
    for argv in (["bash", str(TWIN)], ["python3", str(PORT)]):
        proc = subprocess.run(
            argv,
            env=_env(),
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )
        results.append((proc.returncode, proc.stdout, proc.stderr))
    assert_same(results[0], results[1])
    # This test must have SEEN the verdict, not matched two empty strings.
    assert results[0][0] == 0, "the real ci.yml is not green:\n%s" % results[0][2]
    assert "ci workflow invariants hold" in results[0][2]
    assert "Blind spot: this reads ci.yml only" in results[0][2]


def test_an_unset_workflow_file_falls_back_to_the_real_default() -> None:
    """`${WORKFLOW_FILE:-...}`, exercised with the variable EXPORTED EMPTY.

    An empty value must fall back, not resolve to `<root>` -- which is what `os.environ.get(name, default)` would have done, and is the trap this case exists to hold shut.
    """
    results = []
    for argv in (["bash", str(TWIN)], ["python3", str(PORT)]):
        proc = subprocess.run(
            argv,
            env=_env(WORKFLOW_FILE=""),
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )
        results.append((proc.returncode, proc.stdout, proc.stderr))
    assert_same(results[0], results[1])
    assert results[0][0] == 0
    assert "ci workflow invariants hold" in results[0][2]


# --------------------------------------------------------------------------- Fixtures ---------------------------------------------------------------------------


def test_the_baseline_fixture_is_green(tmp_path: pathlib.Path) -> None:
    """THE CONTROL FOR EVERY OTHER FIXTURE CASE, and the NEGATIVE selftest direction."""
    old, new = run_both(write(tmp_path, BASELINE))
    assert old[0] == 0, "the baseline fixture is not green:\n%s" % old[2]
    assert_same(old, new)


def test_a_channel_docker_tag_job_without_the_guard(tmp_path: pathlib.Path) -> None:
    body = BASELINE.replace("    if: needs.initialize.outputs.channel != ''\n", "", 1)
    old, new = run_both(write(tmp_path, body))
    assert_red(old, "channel-as-docker-tag: job 'channel-consumer'")
    assert_same(old, new)


def test_a_double_quoted_guard_is_accepted(tmp_path: pathlib.Path) -> None:
    """`cond.replace('"', "'")`: the same condition written with double quotes.

    The POSITIVE control's twin. Without it the acceptance branch is never exercised and a port that accepted nothing would still pass every red case.
    """
    body = BASELINE.replace(
        "if: needs.initialize.outputs.channel != ''",
        'if: needs.initialize.outputs.channel != ""',
    )
    old, new = run_both(write(tmp_path, body))
    assert old[0] == 0, "a double-quoted guard should be accepted:\n%s" % old[2]
    assert_same(old, new)


def test_a_whitespace_free_guard_is_accepted(tmp_path: pathlib.Path) -> None:
    """The second acceptance spelling, `channel!=''` after stripping spaces."""
    body = BASELINE.replace(
        "if: needs.initialize.outputs.channel != ''",
        "if: needs.initialize.outputs.channel!=''",
    )
    old, new = run_both(write(tmp_path, body))
    assert old[0] == 0, "a space-free guard should be accepted:\n%s" % old[2]
    assert_same(old, new)


def test_no_channel_derived_docker_tag_is_a_vacuity_failure(tmp_path: pathlib.Path) -> None:
    body = BASELINE.replace("docker_tag: ${{ needs.initialize.outputs.channel }}", "docker_tag: x")
    old, new = run_both(write(tmp_path, body))
    assert_red(old, "no-candidates: no job in")
    assert_same(old, new)


def test_a_workflow_with_no_jobs(tmp_path: pathlib.Path) -> None:
    old, new = run_both(write(tmp_path, "name: empty\non: push\njobs: {}\n"))
    assert_red(old, "no-jobs:")
    assert_same(old, new)


def test_a_workflow_whose_jobs_key_is_a_list(tmp_path: pathlib.Path) -> None:
    """`not isinstance(jobs, dict)`, the other arm of the same guard."""
    old, new = run_both(write(tmp_path, "name: x\non: push\njobs:\n  - a\n  - b\n"))
    assert_red(old, "no-jobs:")
    assert_same(old, new)


def test_a_missing_workflow_file_is_never_green(tmp_path: pathlib.Path) -> None:
    old, new = run_both(tmp_path / "absent.yml")
    assert_red(old, "workflow-missing: no file at")
    assert_same(old, new)


def test_a_stager_that_does_not_pass_skip_release(tmp_path: pathlib.Path) -> None:
    body = BASELINE.replace(
        "    with:\n      skip_release: ${{ needs.initialize.outputs.skip_release }}\n",
        "    with:\n      other: 1\n",
        1,
    )
    old, new = run_both(write(tmp_path, body))
    assert_red(old, "skip-release: job 'stage-artifacts' does not pass")
    assert_same(old, new)


def test_an_initialize_without_the_skip_release_output(tmp_path: pathlib.Path) -> None:
    body = BASELINE.replace("      skip_release: ${{ steps.decide.outputs.skip_release }}\n", "", 1)
    old, new = run_both(write(tmp_path, body))
    assert_red(old, "job 'initialize' declares no `skip_release` output")
    assert_same(old, new)


def test_a_stager_with_no_initialize_job_at_all(tmp_path: pathlib.Path) -> None:
    body = BASELINE.replace("  initialize:\n", "  bootstrap:\n", 1)
    old, new = run_both(write(tmp_path, body))
    assert_red(old, "expected job 'initialize' is absent from")
    assert_same(old, new)


def test_a_sentinel_owner_with_no_stager(tmp_path: pathlib.Path) -> None:
    """`skip-release-no-stage`: the real ci.yml with its stager renamed or rewired."""
    body = BASELINE.replace("uses: ./.github/workflows/cd-stage.yml", "uses: ./other.yml")
    old, new = run_both(write(tmp_path, body))
    assert_red(old, "expected job '<no job uses cd-stage.yml>' is absent from")
    assert_same(old, new)


def test_a_missing_validator_job(tmp_path: pathlib.Path) -> None:
    body = BASELINE.replace("  validate-promote:\n", "  validate-later:\n", 1)
    old, new = run_both(write(tmp_path, body))
    assert_red(old, "expected job 'validate-promote' is absent from")
    assert_same(old, new)


def test_a_validator_that_does_not_gate_on_skip_release(tmp_path: pathlib.Path) -> None:
    body = BASELINE.replace(
        "  validate-install:\n    needs: initialize\n"
        "    if: needs.initialize.outputs.skip_release != 'true'\n",
        "  validate-install:\n    needs: initialize\n    if: always()\n",
        1,
    )
    assert body != BASELINE, "the substitution missed; the case would test nothing"
    old, new = run_both(write(tmp_path, body))
    assert_red(old, "validator 'validate-install' does not gate on")
    assert_same(old, new)


def test_the_sentinel_deciding_a_second_time(tmp_path: pathlib.Path) -> None:
    body = BASELINE.replace(
        "      - run: echo finalize\n",
        "      - run: dispatch-release.sh --decide-only\n",
        1,
    )
    old, new = run_both(write(tmp_path, body))
    assert_red(old, "still runs `dispatch-release.sh --decide-only`")
    assert_same(old, new)


def test_an_unparseable_workflow_is_never_green(tmp_path: pathlib.Path) -> None:
    """A SETUP exit 2 from the heredoc, which bash then reports as exit 1.

    Both the `SETUP: ... does not parse as YAML: ...` line (from PyYAML, so the two sides quote the same message) and the `(exit 2)` in the INVARIANT-FAIL line have to match, which is what pins the twin's 2-becomes-1 translation.
    """
    old, new = run_both(write(tmp_path, "jobs:\n  a: [unclosed\n"))
    assert_red(old, "analysis of")
    assert "(exit 2)" in old[2]
    assert "SETUP:" in old[2]
    assert_same(old, new)


def test_a_scalar_document_crashes_the_analysis_on_both_sides(tmp_path: pathlib.Path) -> None:
    """THE ONE EXEMPTED CASE, and the exemption is one block of text, not a rule.

    `(doc or {}).get("jobs")` on a string raises AttributeError. The twin's
    heredoc prints a traceback naming `<stdin>` and exits 1; the port prints one
    naming its own file. Exit code and stdout are still compared byte for byte, and the stderr is compared with the traceback elided -- so the INVARIANT-FAIL line, its `(exit 1)` and their ORDER relative to the traceback are all still asserted.
    """
    old, new = run_both(write(tmp_path, "just a string\n"))
    assert_red(old, "analysis of")
    assert "(exit 1)" in old[2]
    assert "AttributeError" in old[2], "the twin did not crash the way this case needs"
    assert "AttributeError" in new[2], "the port did not crash the way the twin does"
    assert new[0] == old[0]
    assert new[1] == old[1]
    # GREEDY to the LAST `AttributeError:` line, not the first: the port's own source line is echoed into its traceback, and a non-greedy match stopped at any mention of the name inside it. That is a trap in the TEST rather than in either implementation, and it fired once while this file was being written.
    pattern = re.compile(r"(?s)Traceback \(most recent call last\).*\nAttributeError[^\n]*\n")
    assert pattern.sub("<TRACEBACK>\n", new[2]) == pattern.sub("<TRACEBACK>\n", old[2])
    assert "<TRACEBACK>" in pattern.sub("<TRACEBACK>\n", old[2]), "the elision matched nothing"


def test_missing_python3_is_a_setup_error(tmp_path: pathlib.Path) -> None:
    """Exit 2, the only exit-2 path either side has.

    Driven with a PATH holding `dirname` and nothing else -- `dirname` because the twin resolves its own directory with it before it reaches the probe, and nothing else because the probe is `command -v python3`. Both children are started by absolute path so removing python3 from PATH does not remove the ability to RUN the port.
    """
    bindir = _path_without_python(tmp_path)
    workflow = write(tmp_path, BASELINE)

    env = _env(WORKFLOW_FILE=str(workflow))
    env["PATH"] = str(bindir)
    results = []
    for argv in (["/bin/bash", str(TWIN)], [os.path.realpath(sys.executable), str(PORT)]):
        proc = subprocess.run(
            argv, env=env, cwd=str(ROOT), capture_output=True, text=True, check=False, timeout=120
        )
        results.append((proc.returncode, proc.stdout, proc.stderr))
    assert results[0][0] == 2, "the twin did not take the setup-error path:\n%s" % results[0][2]
    assert "python3 is required to parse" in results[0][2]
    assert_same(results[0], results[1])


def test_colour_is_emitted_when_stderr_is_a_terminal(tmp_path: pathlib.Path) -> None:
    """`[[ -t 2 ]] && [[ -z "${NO_COLOR:-}" ]]` in common.sh:18, the branch a human sees.

    Off a tty both sides print plain text, so every other case in this file proves only the uncoloured half. `CI` is left UNSET: `rediacc_ci.log` also
    disables colour on `CI=true` and common.sh does not, which is `log.py`'s
    documented deliberate divergence and is not this gate's subject.
    """
    body = BASELINE.replace("    if: needs.initialize.outputs.channel != ''\n", "", 1)
    workflow = write(tmp_path, body)
    env = _env(WORKFLOW_FILE=str(workflow))
    old = differential.bash_streams("bash %s" % TWIN, env=env, cwd=str(ROOT), tty="stderr")
    new = differential.bash_streams("python3 %s" % PORT, env=env, cwd=str(ROOT), tty="stderr")
    assert differential.escape_bytes(old[2]) > 0, "the twin printed no colour on a tty"
    assert_same(old, new)


# --------------------------------------------------------------------------- The exported helpers, driven directly (the selftest half) ---------------------------------------------------------------------------


def test_the_literal_document_matches_the_baseline_yaml(tmp_path: pathlib.Path) -> None:
    """CONFORMANT and BASELINE are two spellings of one document; prove it.

    Parsed by the SYSTEM python3 in a subprocess, because that is the interpreter that has PyYAML and is also the one both implementations run under. Without this the literal is a second source of truth that drifts the first time BASELINE is edited, and every helper test above it would keep passing while asserting things about a document nothing else uses.
    """
    program = (
        "import io,json,sys,yaml;"
        "print(json.dumps(yaml.safe_load(io.open(sys.argv[1],encoding='utf-8'))['jobs']))"
    )
    path = write(tmp_path, BASELINE)
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

    The document is a LITERAL dict rather than `yaml.safe_load(BASELINE)`, because PyYAML is importable by the system `python3` that runs both implementations and is NOT importable by the uv-managed interpreter that runs pytest. A test that imported it would be a test that skipped, and a skipped test reads exactly like a passing one in the summary.
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
    """The twin's `case` has no default arm, so an unknown kind is a silent skip."""
    assert ci_workflow_invariants.message_for("invented-kind", "j", "/w.yml") is None


def test_analyse_fires_on_a_missing_guard() -> None:
    """The POSITIVE direction, over the same literal document with one key dropped."""
    doc = json.loads(json.dumps(CONFORMANT))
    del doc["jobs"]["channel-consumer"]["if"]
    assert ("ungated", "channel-consumer") in ci_workflow_invariants.analyse(doc)


def test_analyse_orders_its_findings_the_way_the_twin_prints_them() -> None:
    """Order is observable: the twin logs one line per finding, in stream order.

    `ungated` precedes `no-candidates` precedes the skip-release family, which is the heredoc's own print order, and a port that collected findings into a set or sorted them would still satisfy every membership assertion above.
    """
    doc = json.loads(json.dumps(CONFORMANT))
    del doc["jobs"]["channel-consumer"]["if"]
    del doc["jobs"]["stage-artifacts"]["with"]
    kinds = [kind for kind, _name in ci_workflow_invariants.analyse(doc)]
    assert kinds == ["ungated", "skip-release-not-passed"]
