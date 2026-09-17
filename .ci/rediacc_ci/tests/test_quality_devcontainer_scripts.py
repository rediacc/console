"""`rediacc_ci.quality.devcontainer_scripts` against the grep pipeline it replaces.

WHAT IS WORTH TESTING HERE. The shadow ledger `.ci/shadow/w7p2-devcontainer-scripts.observations.jsonl` drives the whole gate over five distinct trees: a broken process-group lifecycle, a suppressed primary operation, a missing subject, a syntax error, and a control whose plant no longer applies. What a ledger row cannot isolate is the three-stage grep pipeline that decides which
lines assertion A objects to, and there is a specific reason to distrust it here.

`PRIMARY_OPS` alternates a `^`-anchored branch with a branch carrying a NEGATED character class (`curl [^|]*`). `docs/agent-reference/TRAPS.md` records exactly that shape returning SILENT FALSE ZEROS from `grep -E` under ugrep, which would make assertion A pass while reading nothing. So the port's Python regex is run against the REAL `grep -E` over every `.devcontainer/*.sh` in the
tree plus a corpus of hand-written positives and negatives, and any divergence is a test failure rather than two gates quietly disagreeing.

The three sed mutations are also exercised here, in both directions: applied to the real files they must plant their markers, and applied to a decoy they must plant nothing. That second half is the `CONTROL IS VACUOUS` arm, which is the only thing standing between a moved target line and a control that mutates nothing and calls it a pass.
"""

import pathlib
import subprocess

from rediacc_ci import paths
from rediacc_ci.quality import devcontainer_scripts as ds

PRIMARY_OPS_ERE = (
    "git (clone|fetch|pull|submodule update|submodule add)"
    "|curl [^|]*(-o |-O |--output)"
    "|^[[:space:]]*tar "
    "|npm (ci|install)"
)
SUPPRESSORS_ERE = (
    "2>/dev/null|2> */dev/null|2>&-|>[[:space:]]*/dev/null[[:space:]]+2>&1|&>[[:space:]]*/dev/null"
)

PIPELINE = 'grep -nE "$1" | grep -vE \'^[0-9]+:[[:space:]]*#\' | grep -E "$2" || true'


def _shell_scan(text: str) -> list[str]:
    """The twin's exact three-stage pipeline, run for real."""
    proc = subprocess.run(
        ["bash", "-c", PIPELINE, "driver", PRIMARY_OPS_ERE, SUPPRESSORS_ERE],
        input=text.encode("utf-8"),
        capture_output=True,
        check=True,
    )
    return [line for line in proc.stdout.decode("utf-8").split("\n") if line != ""]


def test_scan_suppression_agrees_with_the_pipeline_on_the_corpus() -> None:
    """Every positive and every negative the gate's own selftest carries."""
    for line in (*ds.SUPPRESSED, *ds.NOT_SUPPRESSED):
        text = line + "\n"
        assert ds.scan_suppression(text) == _shell_scan(text), line


def test_scan_suppression_agrees_on_every_real_devcontainer_script() -> None:
    """The live corpus, which is where a false zero would actually cost something.

    Also asserts the corpus is non-empty: a comparison over zero files would agree perfectly and prove nothing, which is the vacuity this whole programme is about.
    """
    scripts = sorted(paths.from_root(ds.DC_REL).glob("*.sh"))
    assert len(scripts) >= 5, scripts
    for script in scripts:
        text = script.read_text(encoding="utf-8", errors="replace")
        assert ds.scan_suppression(text) == _shell_scan(text), script.name


def test_the_anchored_branch_and_the_negated_class_branch_both_still_fire() -> None:
    """The TRAPS.md shape, measured rather than assumed, in both engines.

    One line per branch of `PRIMARY_OPS`, so an engine that dropped the anchored branch when a negated class appears elsewhere in the alternation shows up as a shorter list on one side.
    """
    text = (
        "git clone x 2>/dev/null\n"
        "  tar xf a.tgz 2>/dev/null\n"
        "curl -o out http://x 2>/dev/null\n"
        "npm ci 2>/dev/null\n"
    )
    got = ds.scan_suppression(text)
    assert got == _shell_scan(text)
    assert len(got) == 4, got


def test_the_comment_filter_runs_on_the_numbered_lines() -> None:
    """`grep -vE '^[0-9]+:[[:space:]]*#'` sits BETWEEN the two matchers.

    A port that filtered comments before numbering would shift every reported line number, which is the same class of defect check-devbox-exec carries.
    """
    text = "# git clone x 2>/dev/null\ngit clone y 2>/dev/null\n"
    assert ds.scan_suppression(text) == _shell_scan(text) == ["2:git clone y 2>/dev/null"]


def test_the_a_mutation_plants_on_the_real_file_and_not_on_a_decoy(
    tmp_path: pathlib.Path,
) -> None:
    """Both directions of the CONTROL IS VACUOUS arm."""
    real = paths.from_root(ds.DC_REL, ds.INIT_NAME)
    planted = tmp_path / "planted.sh"
    ds.mutate(real, planted, (ds.A_MUTATION,))
    assert ds.A_MARKER in planted.read_text(encoding="utf-8")
    assert ds.scan_suppression(planted.read_text(encoding="utf-8")) != []

    decoy = tmp_path / "decoy.sh"
    decoy.write_text("#!/bin/bash\necho nothing to mutate\n", encoding="utf-8")
    nothing = tmp_path / "nothing.sh"
    ds.mutate(decoy, nothing, (ds.A_MUTATION,))
    assert ds.A_MARKER not in nothing.read_text(encoding="utf-8")


def test_the_b_and_c_mutations_plant_on_the_real_files(tmp_path: pathlib.Path) -> None:
    """The other two plants, against the files the gate actually mutates."""
    init = paths.from_root(ds.DC_REL, ds.INIT_NAME)
    vscode = paths.from_root(ds.DC_REL, ds.VSCODE_NAME)

    b_out = tmp_path / "b.sh"
    ds.mutate(init, b_out, ds.B_MUTATIONS)
    assert ds.B_MARKER in b_out.read_text(encoding="utf-8")

    c_out = tmp_path / "c.sh"
    ds.mutate(vscode, c_out, ds.C_MUTATIONS)
    text = c_out.read_text(encoding="utf-8")
    assert not any(ds.SETSID.search(line) for line in text.split("\n"))
    assert ds.KILL_GROUP.search(text) is None


def test_assert_b_surfaces_gits_own_words_against_a_scratch_superproject(
    tmp_path: pathlib.Path,
) -> None:
    """Hermetic: an unreachable local URL, no network and no credentials."""
    init = paths.from_root(ds.DC_REL, ds.INIT_NAME)
    rc, out = ds.run_init_against_scratch(init, tmp_path)
    assert rc != 0
    assert ds.GIT_ERROR.search(out), out[:400]


def test_selftest_runs_and_meets_its_floor() -> None:
    """The gate's own both-direction controls."""
    assert ds.selftest() == 0
