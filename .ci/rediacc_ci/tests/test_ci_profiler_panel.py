"""Differential: `rediacc_ci.ci.profiler_panel` against its twin `.ci/scripts/ci/profiler/panel.sh`.

BOTH SIDES ARE COMPARED BYTE FOR BYTE ON THREE CHANNELS -- stdout, stderr and the summary file -- plus the exit code, because this program's whole output is text a human reads in a job panel and a machine (`check_runner_advice.py --refresh`) harvests out of one `::notice` annotation. A finding-set comparison would let the machine row drift.

NOTHING HERE TOUCHES THE NETWORK, DOCKER, OR THE REAL TREE. Every case builds its own sampler TSV under pytest's `tmp_path` and both subjects read it through `PROFILER_SAMPLE_FILE`; the only repository files either side opens are `panel.sh` and `report.awk` themselves, and both open the SAME `report.awk` deliberately -- the aggregator is not ported, it is invoked, so a differential
that gave each side its own copy would be comparing two awk runs rather than two wrappers.

THE PLANTED DEFECT (`test_planted_defect_is_caught_by_this_differential`) mutates a COPY of the port in `tmp_path`, never the file on disk: it drops the `%`-escaping from `escape_workflow_command`, which is invisible on every other
case in this file and corrupts exactly one line of one annotation. That is the
control this suite would be worthless without.

K=5 LEDGER: `.ci/shadow/w7p6-profiler-panel.observations.jsonl`.
"""

from __future__ import annotations

import os
import subprocess
import typing

from rediacc_ci import paths
from rediacc_ci.ci import profiler_panel
from rediacc_ci.core import bash_dialect

if typing.TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()
TWIN = ROOT / ".ci" / "scripts" / "ci" / "profiler" / "panel.sh"
PORT = ROOT / ".ci" / "rediacc_ci" / "ci" / "profiler_panel.py"

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

    `walk=False` is how a DEGENERATE series is built on purpose: with the walk
    on, `cpu=0` still produces 0/10/20/30/40 and report.awk correctly declines
    to call it flat. That is a fixture bug the first draft of this file had, and it made the all-zero test pass for the wrong reason.
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


def healthy(tmp_path: pathlib.Path, name: str = "s.tsv") -> pathlib.Path:
    sample = tmp_path / name
    write_meta(sample)
    append_samples(sample, 37)
    return sample


def _run(
    subject: pathlib.Path, env: dict[str, str], cwd: pathlib.Path
) -> subprocess.CompletedProcess[str]:
    runner = ["bash", str(subject)]
    base = {"PATH": os.environ.get("PATH", ""), "HOME": os.environ.get("HOME", "")}
    if subject.suffix == ".py":
        runner = ["python3", str(subject)]
        base["PYTHONPATH"] = str(ROOT / ".ci")
        base["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.run(
        runner,
        cwd=cwd,
        env={**base, **env},
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )


# One monotonic counter for the whole module, so two calls inside one test never share a summary path. Names, not `tempfile`, so a failure names the call.
_CALLS: list[None] = []


def run_both(
    tmp_path: pathlib.Path, env: dict[str, str], *, port: pathlib.Path | None = None
) -> tuple[subprocess.CompletedProcess[str], subprocess.CompletedProcess[str], str, str]:
    """Drive both subjects with their OWN summary file, and return both bodies.

    A FRESH PAIR OF FILES PER CALL, because `>>` APPENDS: a test that invokes this twice against one tmp_path was comparing the second run against the concatenation of both, and the failure read as a port defect.
    """
    _CALLS.append(None)
    nth = len(_CALLS)
    old_summary = tmp_path / ("summary-old-%d.md" % nth)
    new_summary = tmp_path / ("summary-new-%d.md" % nth)
    old = _run(TWIN, {**env, "GITHUB_STEP_SUMMARY": str(old_summary)}, tmp_path)
    new = _run(port or PORT, {**env, "GITHUB_STEP_SUMMARY": str(new_summary)}, tmp_path)
    old_body = old_summary.read_text(encoding="utf-8") if old_summary.exists() else "<absent>"
    new_body = new_summary.read_text(encoding="utf-8") if new_summary.exists() else "<absent>"
    return old, new, old_body, new_body


def assert_same(
    old: subprocess.CompletedProcess[str],
    new: subprocess.CompletedProcess[str],
    old_body: str = "",
    new_body: str = "",
) -> None:
    assert new.returncode == old.returncode, "exit code: twin %s, port %s (twin stderr %r)" % (
        old.returncode,
        new.returncode,
        old.stderr,
    )
    assert new.stdout == old.stdout
    assert new.stderr == old.stderr
    assert new_body == old_body


# --------------------------------------------------------------------------- Usage refusals ---------------------------------------------------------------------------


def test_unset_sample_file_is_a_usage_error(tmp_path: pathlib.Path) -> None:
    old, new, ob, nb = run_both(tmp_path, {})
    assert old.returncode == 2
    assert "panel.sh: PROFILER_SAMPLE_FILE must be set" in old.stderr
    assert_same(old, new, ob, nb)


def test_empty_sample_file_variable_is_also_unset(tmp_path: pathlib.Path) -> None:
    # `${PROFILER_SAMPLE_FILE:-}` plus `[ -z ]`: exported-but-empty is unset.
    old, new, ob, nb = run_both(tmp_path, {"PROFILER_SAMPLE_FILE": ""})
    assert old.returncode == 2
    assert_same(old, new, ob, nb)


# --------------------------------------------------------------------------- The missing-profile branch ---------------------------------------------------------------------------


def test_absent_sample_file_warns_and_still_writes_a_panel(tmp_path: pathlib.Path) -> None:
    old, new, ob, nb = run_both(
        tmp_path, {"PROFILER_SAMPLE_FILE": str(tmp_path / "nope.tsv"), "PROFILER_TITLE": "job-a"}
    )
    assert old.returncode == 0
    assert "**Samples:** none - no sample file was produced." in ob
    assert "## Runner Profile: job-a" in ob
    assert old.stdout.startswith("::warning::profiler: no sample file at ")
    assert_same(old, new, ob, nb)


def test_absent_sample_file_under_strict_is_an_error_and_exit_1(tmp_path: pathlib.Path) -> None:
    old, new, ob, nb = run_both(
        tmp_path,
        {"PROFILER_SAMPLE_FILE": str(tmp_path / "nope.tsv"), "PROFILER_STRICT": "true"},
    )
    assert old.returncode == 1
    assert old.stdout.startswith("::error::profiler: no sample file at ")
    assert_same(old, new, ob, nb)


def test_zero_byte_sample_file_takes_the_same_branch(tmp_path: pathlib.Path) -> None:
    sample = tmp_path / "empty.tsv"
    sample.write_text("", encoding="utf-8")
    old, new, ob, nb = run_both(tmp_path, {"PROFILER_SAMPLE_FILE": str(sample)})
    assert "no sample file was produced" in ob
    assert_same(old, new, ob, nb)


def test_note_replaces_the_default_reason(tmp_path: pathlib.Path) -> None:
    old, new, ob, nb = run_both(
        tmp_path,
        {"PROFILER_SAMPLE_FILE": str(tmp_path / "nope.tsv"), "PROFILER_NOTE": "sampler died"},
    )
    assert "**Reason:** sampler died" in ob
    assert "(sampler died)" in old.stdout
    assert_same(old, new, ob, nb)


def test_empty_strict_is_false_not_a_third_state(tmp_path: pathlib.Path) -> None:
    # `${PROFILER_STRICT:-false}`: exported-but-empty takes the default. A port
    # using os.environ.get(name, "false") would compare "" != "true" and reach
    # the same answer HERE by luck; this pins the `:-` reading of it.
    old, new, ob, nb = run_both(
        tmp_path, {"PROFILER_SAMPLE_FILE": str(tmp_path / "nope.tsv"), "PROFILER_STRICT": ""}
    )
    assert old.returncode == 0
    assert "::warning::" in old.stdout
    assert_same(old, new, ob, nb)


# --------------------------------------------------------------------------- The normal path ---------------------------------------------------------------------------


def test_healthy_profile_renders_panel_notice_and_no_findings(tmp_path: pathlib.Path) -> None:
    sample = healthy(tmp_path)
    old, new, ob, nb = run_both(
        tmp_path,
        {
            "PROFILER_SAMPLE_FILE": str(sample),
            "PROFILER_WALL_S": "370",
            "PROFILER_TITLE": "fixture-job",
            "PROFILER_STRICT": "true",
        },
    )
    assert old.returncode == 0
    assert "## Runner Profile: fixture-job" in ob
    assert "**Advisory:**" in ob
    assert old.stdout.startswith("::notice title=Runner sizing (profiler)::")
    assert "PROFILER_BASELINE_V1" in old.stdout
    assert "::warning::" not in old.stdout
    assert_same(old, new, ob, nb)


def test_declared_and_hard_are_forwarded_only_when_non_empty(tmp_path: pathlib.Path) -> None:
    sample = healthy(tmp_path)
    base = {"PROFILER_SAMPLE_FILE": str(sample), "PROFILER_WALL_S": "370"}
    old, new, ob, nb = run_both(
        tmp_path, {**base, "PROFILER_DECLARED_S": "600", "PROFILER_HARD_S": "700"}
    )
    assert "62% of the 10m 0s declared timeout, 53% of the 11m 40s slim hard cap" in ob
    assert_same(old, new, ob, nb)
    # Empty means DO NOT PASS THE FLAG, so the aggregator keeps its own default and the panel is byte-identical to the one with the variables absent.
    with_empty = run_both(tmp_path, {**base, "PROFILER_DECLARED_S": "", "PROFILER_HARD_S": ""})
    without = run_both(tmp_path, base)
    assert_same(with_empty[0], with_empty[1], with_empty[2], with_empty[3])
    assert with_empty[2] == without[2]


def test_github_job_keys_the_machine_row(tmp_path: pathlib.Path) -> None:
    sample = healthy(tmp_path)
    old, new, ob, nb = run_both(
        tmp_path,
        {
            "PROFILER_SAMPLE_FILE": str(sample),
            "PROFILER_WALL_S": "370",
            "GITHUB_JOB": "quality-code",
        },
    )
    assert "job=quality-code" in old.stdout
    assert_same(old, new, ob, nb)


def test_note_is_appended_after_the_panel(tmp_path: pathlib.Path) -> None:
    sample = healthy(tmp_path)
    old, new, ob, nb = run_both(
        tmp_path,
        {
            "PROFILER_SAMPLE_FILE": str(sample),
            "PROFILER_WALL_S": "370",
            "PROFILER_NOTE": "sampler restarted once",
        },
    )
    assert ob.rstrip("\n").endswith("**Note:** sampler restarted once")
    assert_same(old, new, ob, nb)


# --------------------------------------------------------------------------- Findings, strict and non-strict ---------------------------------------------------------------------------


def test_too_few_samples_warns_but_does_not_fail(tmp_path: pathlib.Path) -> None:
    sample = tmp_path / "few.tsv"
    write_meta(sample)
    append_samples(sample, 2)
    old, new, ob, nb = run_both(
        tmp_path, {"PROFILER_SAMPLE_FILE": str(sample), "PROFILER_WALL_S": "20"}
    )
    assert old.returncode == 0
    assert "::warning::profiler: " in old.stdout
    assert_same(old, new, ob, nb)


def test_too_few_samples_under_strict_is_error_and_exit_1(tmp_path: pathlib.Path) -> None:
    sample = tmp_path / "few.tsv"
    write_meta(sample)
    append_samples(sample, 2)
    old, new, ob, nb = run_both(
        tmp_path,
        {
            "PROFILER_SAMPLE_FILE": str(sample),
            "PROFILER_WALL_S": "20",
            "PROFILER_STRICT": "true",
        },
    )
    assert old.returncode == 1
    assert "::error::profiler: " in old.stdout
    assert "::warning::" not in old.stdout
    assert_same(old, new, ob, nb)


def test_all_zero_cpu_is_a_finding(tmp_path: pathlib.Path) -> None:
    sample = tmp_path / "flat.tsv"
    write_meta(sample)
    append_samples(sample, 37, cpu=0, walk=False)
    old, new, ob, nb = run_both(
        tmp_path,
        {
            "PROFILER_SAMPLE_FILE": str(sample),
            "PROFILER_WALL_S": "370",
            "PROFILER_STRICT": "true",
        },
    )
    assert old.returncode == 1
    assert "degenerate CPU series" in old.stdout
    assert_same(old, new, ob, nb)


def test_host_leak_emits_a_notice_with_verdict_none(tmp_path: pathlib.Path) -> None:
    sample = tmp_path / "leak.tsv"
    write_meta(sample, tier="PROC_HOST")
    with open(sample, "a", encoding="utf-8") as handle:
        handle.write("#HOST_LEAK\tcpu\n")
    append_samples(sample, 37)
    old, new, ob, nb = run_both(
        tmp_path, {"PROFILER_SAMPLE_FILE": str(sample), "PROFILER_WALL_S": "370"}
    )
    assert "verdict=NONE" in old.stdout
    assert_same(old, new, ob, nb)


# --------------------------------------------------------------------------- The trim, and the advisory fallback it causes ---------------------------------------------------------------------------


def test_oversized_panel_is_trimmed_and_says_so(tmp_path: pathlib.Path) -> None:
    sample = healthy(tmp_path)
    old, new, ob, nb = run_both(
        tmp_path,
        {
            "PROFILER_SAMPLE_FILE": str(sample),
            "PROFILER_WALL_S": "370",
            "PROFILER_MAX_PANEL_BYTES": "200",
        },
    )
    assert "**Panel trimmed:**" in ob
    assert len(ob.encode("utf-8")) < 400
    # The advisory line was cut off, so the notice says so rather than opening
    # with nothing -- and the machine row after it is still intact.
    assert "(advisory text unavailable: the panel was trimmed)" in old.stdout
    assert "PROFILER_BASELINE_V1" in old.stdout
    assert_same(old, new, ob, nb)


def test_a_budget_the_panel_fits_inside_leaves_no_trim_note(tmp_path: pathlib.Path) -> None:
    sample = healthy(tmp_path)
    old, new, ob, nb = run_both(
        tmp_path,
        {
            "PROFILER_SAMPLE_FILE": str(sample),
            "PROFILER_WALL_S": "370",
            "PROFILER_MAX_PANEL_BYTES": "900000",
        },
    )
    assert "**Panel trimmed:**" not in ob
    assert_same(old, new, ob, nb)


def test_non_numeric_budget_is_a_bash_diagnostic_only(tmp_path: pathlib.Path) -> None:
    """THE ONE NAMED DIVERGENCE, pinned rather than papered over.

    `[ "$SIZE" -gt abc ]` makes bash print `[: abc: integer expected` on stderr and evaluate false; an `if` condition is exempt from `set -e`, so the run continues and produces an untrimmed panel. The port reaches the same decision without forging a bash diagnostic that carries the twin's own path and line number. stdout, the panel and the exit code all still agree; only stderr
    differs, and this test exists so that stops being invisible.
    """
    sample = healthy(tmp_path)
    old, new, ob, nb = run_both(
        tmp_path,
        {
            "PROFILER_SAMPLE_FILE": str(sample),
            "PROFILER_WALL_S": "370",
            "PROFILER_MAX_PANEL_BYTES": "abc",
        },
    )
    assert old.returncode == new.returncode == 0
    assert old.stdout == new.stdout
    assert ob == nb
    assert "**Panel trimmed:**" not in ob
    # Asked of the running bash: 5.3 says "integer expected" where 5.2 says "integer expression expected", and CI runs 5.2.
    assert bash_dialect.integer_expected() in old.stderr
    assert new.stderr == ""


# --------------------------------------------------------------------------- GITHUB_STEP_SUMMARY unset: the `/dev/stdout` default ---------------------------------------------------------------------------


def test_summary_defaults_to_stdout_and_keeps_its_order(tmp_path: pathlib.Path) -> None:
    """No `GITHUB_STEP_SUMMARY`: the panel and the annotations share one fd.

    Both subjects are captured through a PIPE here (`capture_output=True`), which
    is the shape a human running the twin's own documented `PROFILER_SAMPLE_FILE=
    /tmp/p.tsv .ci/scripts/ci/profiler/panel.sh` gets. A pipe has no file offset, so the two writers cannot overwrite each other and the panel must come first.
    """
    sample = healthy(tmp_path)
    env = {"PROFILER_SAMPLE_FILE": str(sample), "PROFILER_WALL_S": "370"}
    old = _run(TWIN, env, tmp_path)
    new = _run(PORT, env, tmp_path)
    assert old.stdout.startswith("\n## Runner Profile")
    assert "::notice title=Runner sizing (profiler)::" in old.stdout
    assert old.stdout.index("## Runner Profile") < old.stdout.index("::notice")
    assert_same(old, new)


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
    f = tmp_path / "findings.txt"
    f.write_text("one\ntwo\nthree-no-newline", encoding="utf-8")
    assert profiler_panel._read_lines(f) == ["one", "two"]
    f.write_text("one\ntwo\n", encoding="utf-8")
    assert profiler_panel._read_lines(f) == ["one", "two"]


# --------------------------------------------------------------------------- The control: a planted defect must turn this suite red ---------------------------------------------------------------------------


def test_planted_defect_is_caught_by_this_differential(tmp_path: pathlib.Path) -> None:
    """Drop `%`-escaping from a COPY of the port and watch the notice diverge.

    The real file on disk is never touched. Without this case the suite proves only that two programs that agree today agree today.
    """
    source = PORT.read_text(encoding="utf-8")
    broken_src = source.replace('    s = s.replace("%", "%25")\n', "", 1)
    assert broken_src != source, "the line the plant removes must still exist"
    broken = tmp_path / "profiler_panel_broken.py"
    broken.write_text(broken_src, encoding="utf-8")

    # AN ADVISORY CARRYING A LITERAL `%` IS WHAT THE ESCAPING IS FOR, and the first draft of this plant used a healthy slim profile and DID NOT FIRE: every `advise()` return in report.awk:340-418 is percent-free, so the escaper was never reached and a port with no escaping at all agreed. The `%` reaches the advisory through the RUNNER LABEL, which the action passes straight in and
    # which two arms interpolate verbatim ("keep <rn>: ..."), so the fixture is a non-slim box whose label carries one.
    sample = tmp_path / "pct.tsv"
    write_meta(sample, runner="big%box", ceil_cpu=4000, ceil_mem=16 * 1024 * 1024 * 1024)
    append_samples(sample, 37, cpu=2000)
    env = {
        "PROFILER_SAMPLE_FILE": str(sample),
        "PROFILER_WALL_S": "370",
        "PROFILER_TITLE": "fixture-job",
    }
    old, new, _ob, _nb = run_both(tmp_path, env, port=broken)
    assert "keep big%25box:" in old.stdout, "the twin escapes the advisory's percent sign"
    assert new.stdout != old.stdout, "PLANT DID NOT FIRE: the differential is vacuous"
    assert "keep big%box:" in new.stdout, "the mutated port must leave the % raw"
    # And the unmutated port still agrees, so the plant is what moved.
    good_old, good_new, gob, gnb = run_both(tmp_path, env)
    assert_same(good_old, good_new, gob, gnb)
