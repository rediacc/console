"""`rediacc_ci.ci.profiler_panel`, driven against the bytes its bash twin produced.

WHILE BOTH COPIES EXISTED this file ran `.ci/scripts/ci/profiler/panel.sh` and the port over one sampler TSV each and compared FOUR things: exit code, stdout, stderr and the summary file. The K=5 ledger `.ci/shadow/w7p6-profiler-panel.observations.jsonl` recorded that comparison over five distinct trees.

THE TWIN HAS NOW BEEN DELETED, and every case compares against `goldens/profiler-panel/`, which holds the twin's OWN recorded bytes, captured on its last day in the tree. Each provenance header carries the twin's blob sha, so `git cat-file -p <sha>` still yields the program that produced them.

BYTE FOR BYTE ON THREE CHANNELS, because this program's whole output is text a human reads in a job panel and a machine (`check_runner_advice.py --refresh`) harvests out of one `::notice` annotation. A finding-set comparison would let the machine row drift.

NOTHING HERE TOUCHES THE NETWORK, DOCKER, OR THE REAL TREE, with one named exception. Every case builds its own sampler TSV under pytest's `tmp_path`, and the only repository file the subject opens is `.ci/scripts/ci/profiler/report.awk`.

THAT AGGREGATOR IS THE ONE COUPLING THESE RECORDINGS CARRY, and it is stated rather than discovered later. `report.awk` is NOT ported: it is invoked, because awk is the one text tool guaranteed present on a 1-vCPU runner, and reimplementing 439 lines of mawk dialect would be a rewrite wearing a port's clothes.

So a golden here freezes the PAIR, the twin's wrapper and that awk file as they stood together. A deliberate change to `report.awk` will move these bytes, and the honest response is to re-derive the affected goldens from the port with the reason recorded, as for any golden whose subject legitimately changed.

WHAT IS NORMALISED, and it is two paths. The case's own temporary directory becomes `<work>`, because the missing-profile branch prints the sample path it could not find.

The checkout root becomes `<repo>`, because the one divergent case carries bash's own diagnostic naming the twin. Nothing else is touched.

ONE CASE IS COMPARED BY SHAPE. `[ "$SIZE" -gt abc ]` made bash print `[: abc: integer expected` on stderr and evaluate false, and an `if` condition is exempt from `set -e`, so the run continued and produced an untrimmed panel.

The port reaches the same decision without forging a bash diagnostic that carries the twin's own path and line number, so stdout, the panel and the exit code are compared exactly and only stderr is excused.
"""

from __future__ import annotations

import json
import os
import subprocess
import typing

import pytest

from rediacc_ci import paths
from rediacc_ci.ci import profiler_panel
from rediacc_ci.tests import frozen

if typing.TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()
PORT = ROOT / ".ci" / "rediacc_ci" / "ci" / "profiler_panel.py"
SLUG = "profiler-panel"

SUMMARY_MARKER = "--- summary ---\n"
NO_SUMMARY = "<absent>"

T0_MS = 1700000000000
CEIL_CPU = 1000
CEIL_MEM = 5 * 1024 * 1024 * 1024


def write_meta(
    path: pathlib.Path,
    tier: str = "CGROUP_V2",
    interval: int = 10,
    runner: str = "ubuntu-slim",
    ceil_cpu: int = CEIL_CPU,
    ceil_mem: int = CEIL_MEM,
) -> None:
    """TRUNCATES, as the sampler's own `>` does."""
    path.write_text(
        "#META\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\tUNKNOWN\n"
        % (tier, ceil_cpu, ceil_mem, interval, T0_MS, runner, tier, tier),
        encoding="utf-8",
    )


def append_samples(
    path: pathlib.Path,
    count: int,
    interval: int = 10,
    cpu: int = 420,
    mem_mb: int = 1200,
    *,
    walk: bool = True,
) -> None:
    """Samples walk slightly so nothing is accidentally degenerate.

    `walk=False` is how a DEGENERATE series is built on purpose: with the walk on, `cpu=0` still produces 0/10/20/30/40 and report.awk correctly declines to call it flat. That is a fixture bug the first draft of the differential had, and it made the all-zero case pass for the wrong reason.
    """
    rx = 0
    tx = 0
    rows = []
    for i in range(1, count + 1):
        rx += 100000
        tx += 50000
        rows.append(
            "S\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n"
            % (
                T0_MS + i * interval * 1000,
                cpu + ((i % 5) * 10 if walk else 0),
                (mem_mb + i % 64) * 1048576,
                rx,
                tx,
                8000000,
                900000,
            )
        )
    with open(path, "a", encoding="utf-8") as handle:
        handle.write("".join(rows))


# The sampler fixtures, by the name a case refers to them by. `absent` names a path that is never created; `none` passes no sample file at all.
def build_sample(kind: str, where: pathlib.Path) -> str:
    if kind == "none":
        return ""
    if kind == "absent":
        return str(where / "nope.tsv")
    if kind == "empty":
        path = where / "empty.tsv"
        path.write_text("", encoding="utf-8")
        return str(path)
    path = where / ("%s.tsv" % kind)
    if kind == "healthy":
        write_meta(path)
        append_samples(path, 37)
    elif kind == "few":
        write_meta(path)
        append_samples(path, 2)
    elif kind == "flat":
        write_meta(path)
        append_samples(path, 37, cpu=0, walk=False)
    elif kind == "leak":
        write_meta(path, tier="PROC_HOST")
        with open(path, "a", encoding="utf-8") as handle:
            handle.write("#HOST_LEAK\tcpu\n")
        append_samples(path, 37)
    elif kind == "percent":
        # AN ADVISORY CARRYING A LITERAL `%` IS WHAT THE ESCAPING IS FOR, and the percent reaches the advisory through the RUNNER LABEL, which the action passes straight in and which two arms interpolate verbatim.
        write_meta(path, runner="big%box", ceil_cpu=4000, ceil_mem=16 * 1024 * 1024 * 1024)
        append_samples(path, 37, cpu=2000)
    else:
        raise AssertionError("unknown sample kind %r" % kind)
    return str(path)


HEALTHY_ENV = {"PROFILER_WALL_S": "370"}

# name -> which sampler fixture it uses, its environment, and whether `$GITHUB_STEP_SUMMARY` is set
CASE_KW: dict[str, dict[str, typing.Any]] = {
    "no-sample-file-variable": {"sample": "none", "env": {}, "unset_sample": True},
    # `${PROFILER_SAMPLE_FILE:-}` plus `[ -z ]`: exported-but-empty is unset.
    "an-empty-sample-file-variable": {"sample": "none", "env": {}},
    "an-absent-sample-file": {"sample": "absent", "env": {"PROFILER_TITLE": "job-a"}},
    "an-absent-sample-file-under-strict": {
        "sample": "absent",
        "env": {"PROFILER_STRICT": "true"},
    },
    "a-zero-byte-sample-file": {"sample": "empty", "env": {}},
    "a-note-replaces-the-reason": {"sample": "absent", "env": {"PROFILER_NOTE": "sampler died"}},
    # `${PROFILER_STRICT:-false}`: exported-but-empty takes the default. A port using `os.environ.get(name, "false")` would compare "" != "true" and reach the same answer HERE by luck; this pins the `:-` reading of it.
    "an-empty-strict-flag": {"sample": "absent", "env": {"PROFILER_STRICT": ""}},
    "a-healthy-profile": {
        "sample": "healthy",
        "env": {**HEALTHY_ENV, "PROFILER_TITLE": "fixture-job", "PROFILER_STRICT": "true"},
    },
    "declared-and-hard-forwarded": {
        "sample": "healthy",
        "env": {**HEALTHY_ENV, "PROFILER_DECLARED_S": "600", "PROFILER_HARD_S": "700"},
    },
    "declared-and-hard-empty": {
        "sample": "healthy",
        "env": {**HEALTHY_ENV, "PROFILER_DECLARED_S": "", "PROFILER_HARD_S": ""},
    },
    "declared-and-hard-absent": {"sample": "healthy", "env": dict(HEALTHY_ENV)},
    "the-github-job-keys-the-machine-row": {
        "sample": "healthy",
        "env": {**HEALTHY_ENV, "GITHUB_JOB": "quality-code"},
    },
    "a-note-after-the-panel": {
        "sample": "healthy",
        "env": {**HEALTHY_ENV, "PROFILER_NOTE": "sampler restarted once"},
    },
    "too-few-samples": {"sample": "few", "env": {"PROFILER_WALL_S": "20"}},
    "too-few-samples-under-strict": {
        "sample": "few",
        "env": {"PROFILER_WALL_S": "20", "PROFILER_STRICT": "true"},
    },
    "an-all-zero-cpu-series": {
        "sample": "flat",
        "env": {**HEALTHY_ENV, "PROFILER_STRICT": "true"},
    },
    "a-host-leak": {"sample": "leak", "env": dict(HEALTHY_ENV)},
    "an-oversized-panel": {
        "sample": "healthy",
        "env": {**HEALTHY_ENV, "PROFILER_MAX_PANEL_BYTES": "200"},
    },
    "a-budget-the-panel-fits-inside": {
        "sample": "healthy",
        "env": {**HEALTHY_ENV, "PROFILER_MAX_PANEL_BYTES": "900000"},
    },
    "a-non-numeric-budget": {
        "sample": "healthy",
        "env": {**HEALTHY_ENV, "PROFILER_MAX_PANEL_BYTES": "abc"},
    },
    # No `GITHUB_STEP_SUMMARY`: the panel and the annotations share one fd. Both are captured through a PIPE, which is the shape a human running the subject by hand gets; a pipe has no file offset, so the two writers cannot overwrite each other and the panel must come first.
    "no-summary-variable": {"sample": "healthy", "env": dict(HEALTHY_ENV), "summary": False},
    "a-percent-in-the-runner-label": {
        "sample": "percent",
        "env": {**HEALTHY_ENV, "PROFILER_TITLE": "fixture-job"},
    },
}

CASES = tuple(CASE_KW)

# The one case whose stderr is a bash diagnostic. Compared by shape, in its own test.
DIVERGENT = ("a-non-numeric-budget",)


def run(subject: pathlib.Path, where: pathlib.Path, name: str) -> tuple[int, str, str, str]:
    """One subject, once, over this case's own sampler fixture."""
    kw = CASE_KW[name]
    where.mkdir(parents=True, exist_ok=True)
    env = {"PATH": os.environ.get("PATH", ""), "HOME": os.environ.get("HOME", "")}
    if subject.suffix == ".py":
        env["PYTHONPATH"] = str(ROOT / ".ci")
        env["PYTHONDONTWRITEBYTECODE"] = "1"
    sample = build_sample(kw["sample"], where)
    if not kw.get("unset_sample"):
        env["PROFILER_SAMPLE_FILE"] = sample
    env.update(kw["env"])
    summary = where / "summary.md"
    if kw.get("summary", True):
        env["GITHUB_STEP_SUMMARY"] = str(summary)
    runner = "bash" if subject.suffix == ".sh" else "python3"
    proc = subprocess.run(
        [runner, str(subject)],
        cwd=str(where),
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    body = summary.read_text(encoding="utf-8") if summary.exists() else NO_SUMMARY

    def mask(text: str) -> str:
        return text.replace(str(where), "<work>").replace(str(ROOT), "<repo>")

    return proc.returncode, mask(proc.stdout), mask(proc.stderr), mask(body)


def render(code: int, stdout: str, stderr: str, body: str) -> str:
    return "%s%s%s\n" % (frozen.render(code, stdout, stderr), SUMMARY_MARKER, body)


def recorded(name: str) -> tuple[int, str, str, str]:
    text = frozen.read(SLUG, name)
    exit_line, rest = text.split("\n", 1)
    stdout, rest = rest.split("--- stdout ---\n", 1)[1].split("--- stderr ---\n", 1)
    stderr, body = rest.split(SUMMARY_MARKER, 1)
    return int(exit_line.removeprefix("exit: ")), stdout, stderr, body.removesuffix("\n")


def compare(tmp_path: pathlib.Path, name: str) -> tuple[int, str, str, str]:
    want = recorded(name)
    got = run(PORT, tmp_path / "port", name)
    labels = ("exit code", "stdout", "stderr", "the summary")
    for label, a, b in zip(labels, want, got, strict=True):
        assert a == b, "%s: %s diverged:\n--- recorded ---\n%r\n--- port ---\n%r" % (
            name,
            label,
            a,
            b,
        )
    return got


@pytest.mark.parametrize("name", [c for c in CASES if c not in DIVERGENT])
def test_port_matches_the_twins_recorded_output(tmp_path: pathlib.Path, name: str) -> None:
    compare(tmp_path, name)


def test_every_case_has_a_golden_and_no_golden_is_orphaned() -> None:
    """ANTI-VACUITY on the corpus: a case whose golden vanished would pass by never being compared, and a golden nothing reads is a recording of a case that stopped running."""
    frozen.assert_corpus(SLUG, set(CASES))


# --------------------------------------------------------------------------- What the recordings say ---------------------------------------------------------------------------


def test_the_two_usage_refusals() -> None:
    """Unset and exported-but-empty are the same refusal, exit 2, on stderr."""
    for name in ("no-sample-file-variable", "an-empty-sample-file-variable"):
        code, _, stderr, _ = recorded(name)
        assert code == 2, name
        assert "panel.sh: PROFILER_SAMPLE_FILE must be set" in stderr, name


def test_the_missing_profile_branch() -> None:
    """A missing sampler file still writes a panel, warns, and exits 0; under strict it errors and exits 1; a zero-byte file takes the same branch."""
    code, stdout, _, body = recorded("an-absent-sample-file")
    assert code == 0
    assert "**Samples:** none - no sample file was produced." in body
    assert "## Runner Profile: job-a" in body
    assert stdout.startswith("::warning::profiler: no sample file at ")

    code, stdout, _, _ = recorded("an-absent-sample-file-under-strict")
    assert code == 1
    assert stdout.startswith("::error::profiler: no sample file at ")

    assert "no sample file was produced" in recorded("a-zero-byte-sample-file")[3]


def test_the_note_and_the_empty_strict_flag() -> None:
    _, stdout, _, body = recorded("a-note-replaces-the-reason")
    assert "**Reason:** sampler died" in body
    assert "(sampler died)" in stdout
    code, stdout, _, _ = recorded("an-empty-strict-flag")
    assert code == 0
    assert "::warning::" in stdout


def test_healthy_profile_renders_panel_notice_and_no_findings() -> None:
    code, stdout, _, body = recorded("a-healthy-profile")
    assert code == 0
    assert "## Runner Profile: fixture-job" in body
    assert "**Advisory:**" in body
    assert stdout.startswith("::notice title=Runner sizing (profiler)::")
    assert "PROFILER_BASELINE_V1" in stdout
    assert "::warning::" not in stdout


def test_declared_and_hard_are_forwarded_only_when_non_empty() -> None:
    """Empty means DO NOT PASS THE FLAG, so the aggregator keeps its own default and the panel is byte-identical to the one with the variables absent."""
    body = recorded("declared-and-hard-forwarded")[3]
    assert "62% of the 10m 0s declared timeout, 53% of the 11m 40s slim hard cap" in body
    assert recorded("declared-and-hard-empty")[3] == recorded("declared-and-hard-absent")[3]


def test_the_job_name_and_the_trailing_note() -> None:
    assert "job=quality-code" in recorded("the-github-job-keys-the-machine-row")[1]
    body = recorded("a-note-after-the-panel")[3]
    assert body.rstrip("\n").endswith("**Note:** sampler restarted once")


def test_findings_strict_and_non_strict() -> None:
    """Too few samples warns and exits 0; under strict the same input errors and exits 1, with no warning left behind."""
    code, stdout, _, _ = recorded("too-few-samples")
    assert code == 0
    assert "::warning::profiler: " in stdout
    code, stdout, _, _ = recorded("too-few-samples-under-strict")
    assert code == 1
    assert "::error::profiler: " in stdout
    assert "::warning::" not in stdout


def test_a_degenerate_series_and_a_host_leak() -> None:
    code, stdout, _, _ = recorded("an-all-zero-cpu-series")
    assert code == 1
    assert "degenerate CPU series" in stdout
    assert "verdict=NONE" in recorded("a-host-leak")[1]


def test_the_trim_and_the_advisory_fallback_it_causes() -> None:
    """The advisory line is cut off, so the notice says so rather than opening with nothing, and the machine row after it is still intact."""
    _, stdout, _, body = recorded("an-oversized-panel")
    assert "**Panel trimmed:**" in body
    assert len(body.encode("utf-8")) < 400
    assert "(advisory text unavailable: the panel was trimmed)" in stdout
    assert "PROFILER_BASELINE_V1" in stdout
    assert "**Panel trimmed:**" not in recorded("a-budget-the-panel-fits-inside")[3]


def test_summary_defaults_to_stdout_and_keeps_its_order() -> None:
    _, stdout, _, body = recorded("no-summary-variable")
    assert body == NO_SUMMARY
    assert stdout.startswith("\n## Runner Profile")
    assert "::notice title=Runner sizing (profiler)::" in stdout
    assert stdout.index("## Runner Profile") < stdout.index("::notice")


def test_the_percent_in_the_runner_label_is_escaped() -> None:
    """The recording that gives the control below something to break: a `%` in the runner label reaches the advisory and must arrive escaped."""
    assert "keep big%25box:" in recorded("a-percent-in-the-runner-label")[1]


# --------------------------------------------------------------------------- Pure helpers ---------------------------------------------------------------------------


def test_escape_workflow_command_matches_the_twins_three_substitutions() -> None:
    assert profiler_panel.escape_workflow_command("100% done") == "100%25 done"
    assert profiler_panel.escape_workflow_command("a\r\nb") == "a%0D%0Ab"
    # `%` FIRST, so the `%0D` it just wrote is not re-escaped into `%250D`.
    assert profiler_panel.escape_workflow_command("%\r") == "%25%0D"
    assert profiler_panel.escape_workflow_command("plain") == "plain"


def test_env_reads_empty_as_unset(monkeypatch) -> None:
    monkeypatch.setenv("W7P6_PROBE", "")
    assert profiler_panel._env("W7P6_PROBE", "fallback") == "fallback"
    monkeypatch.setenv("W7P6_PROBE", "x")
    assert profiler_panel._env("W7P6_PROBE", "fallback") == "x"
    monkeypatch.delenv("W7P6_PROBE")
    assert profiler_panel._env("W7P6_PROBE", "fallback") == "fallback"


def test_read_lines_drops_an_unterminated_final_record(tmp_path: pathlib.Path) -> None:
    """`while IFS= read -r line` never sees a last line with no newline."""
    findings = tmp_path / "findings.txt"
    findings.write_text("one\ntwo\nthree-no-newline", encoding="utf-8")
    assert profiler_panel._read_lines(findings) == ["one", "two"]
    findings.write_text("one\ntwo\n", encoding="utf-8")
    assert profiler_panel._read_lines(findings) == ["one", "two"]


# --------------------------------------------------------------------------- The one divergence, pinned rather than papered over ---------------------------------------------------------------------------


def test_divergence_a_non_numeric_panel_budget(tmp_path: pathlib.Path) -> None:
    """Exit code, stdout and the panel all still agree; only stderr differs, and this case exists so that stops being invisible."""
    name = "a-non-numeric-budget"
    want = recorded(name)
    got = run(PORT, tmp_path / "port", name)
    assert want[0] == got[0] == 0
    assert want[1] == got[1]
    assert want[3] == got[3]
    assert "**Panel trimmed:**" not in want[3]
    assert "integer expression expected" in want[2] or "integer expected" in want[2], (
        "the twin's recorded diagnostic is not the arithmetic refusal this case pins"
    )
    assert got[2] == "", "the port forged a bash diagnostic"


# --------------------------------------------------------------------------- The control: these goldens can actually fail ---------------------------------------------------------------------------


def test_a_planted_drop_of_the_percent_escaping_is_caught(tmp_path: pathlib.Path) -> None:
    """THE CONTROL ON THE GOLDENS. Drop `%`-escaping from a COPY of the port.

    A raw `%` in a workflow command is a truncation, not a typo: the runner reads `%` as the start of an escape and the rest of the annotation is lost, which takes the machine row `check_runner_advice.py --refresh` harvests with it.

    The first draft of this plant used a healthy slim profile and DID NOT FIRE, because every `advise()` return in `report.awk` is percent-free and the escaper was never reached. The percent reaches the advisory through the runner LABEL instead, which is why `a-percent-in-the-runner-label` exists as a case of its own. The tracked port is never written.
    """
    original = PORT.read_text(encoding="utf-8")
    anchor = '    s = s.replace("%", "%25")\n'
    assert original.count(anchor) == 1, "the plant's anchor moved"
    mutant = tmp_path / "plant" / "mutant.py"
    mutant.parent.mkdir(parents=True)
    mutant.write_text(original.replace(anchor, "", 1), encoding="utf-8")

    name = "a-percent-in-the-runner-label"
    planted = run(mutant, tmp_path / "planted", name)
    want = recorded(name)
    assert "keep big%25box:" in want[1], "the recorded corpus moved"
    assert "keep big%box:" in planted[1], "the mutated port must leave the % raw"
    assert planted[1] != want[1], "PLANT DID NOT FIRE: the comparison is vacuous"

    compare(tmp_path, name)
    assert PORT.read_text(encoding="utf-8") == original


def test_the_case_table_is_not_silently_shrinking() -> None:
    """ANTI-VACUITY on the table itself, since every fixture is built from a name in it: a kind that stopped being referenced would take its branch of `build_sample` out of the corpus with it."""
    kinds = {kw["sample"] for kw in CASE_KW.values()}
    assert kinds == {"none", "absent", "empty", "healthy", "few", "flat", "leak", "percent"}
    assert len(CASES) == 22
    assert json.dumps(sorted(CASES))  # the names are JSON-safe, as a golden filename must be
