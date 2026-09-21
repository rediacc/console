"""`rediacc_ci.quality.label_references`, driven against the bytes its bash twin printed.

WHILE BOTH COPIES EXISTED a bash child ran the REAL `.ci/scripts/quality/check-label-references.sh` over a specimen with stdout and stderr captured SEPARATELY, and its bytes were compared against the port's. Same recipe as the committed ledger, `.ci/shadow/w7p2-label-references.observations.jsonl`, which holds equivalence over six distinct trees. The twin has now been
deleted and every case that executed it compares against `goldens/label-references/`, which holds the twin's OWN recorded output, captured from the tracked script on its last day in the tree. The provenance header of each golden carries the blob sha, so `git cat-file -p <sha>` still yields the program that printed those bytes.

THIS FILE ASSEMBLES EVERY LABEL-CONSUMING SHAPE AT RUNTIME, and that is not style. This file lives under `.ci`, which is one of the two directories the real sweep reads. Written as literals, its fixtures would BE label references, and the real gate would report them as undeclared: the port's first draft did exactly that, and `check-label-references.sh` went red naming
`.ci/rediacc_ci/quality/label_references.py`. The twin dodges the same problem by excluding its own basename AND its test's basename; the port cannot use that dodge without scanning a different corpus than the twin, so it removes the reason instead. Every helper below therefore builds its line from a token that is itself assembled.

BOTH DIRECTIONS. The corpus carries an undeclared label (must fire), a declared one (must stay quiet), a templated placeholder (must be dropped), a broken extractor (must be caught by the self-test before the sweep), a collapsed sweep (must hit the floor), and an EMPTY labels file, which is the case the twin's missing `|| true` made unreachable until 96355d3b5 on 2026-09-06.
"""

import pathlib
import re
import shutil

import pytest

from rediacc_ci.quality import label_references as gate
from rediacc_ci.tests import differential as diff
from rediacc_ci.tests import frozen

SLUG = "label-references"
MODULE = "label_references"

ENV_PREFIX = (
    "LABEL_REFS_LABELS_FILE=fx/labels.yml LABEL_REFS_SCAN_DIRS=fx/scan LABEL_REFS_MIN_DISTINCT=2"
)


def search_filter(label: str) -> str:
    """A `--search` line naming `label`. ASSEMBLED; see the module docstring."""
    return '--search "merged:>=X %s:%s"' % ("label", label)


def js_const(label: str) -> str:
    """A `const ISSUE_LABEL = '<label>';` line, assembled."""
    return "const ISSUE%s = '%s';" % ("_LABEL", label)


def declarations(*labels: str) -> str:
    return "".join("- name: %s\n  color: ffffff\n" % label for label in labels)


def build(tmp_path: pathlib.Path, labels: str | None, scan: dict[str, str]) -> pathlib.Path:
    """A specimen holding BOTH implementations, `fx/labels.yml` and `fx/scan/`.

    `labels=None` means the declaration file is ABSENT, which is a different
    refusal from an EMPTY one: the first says "I cannot find it", the second is the collapsed-parse case the floor exists for.
    """
    src = pathlib.Path(diff.repo())
    root = tmp_path / "fixture"
    (root / ".ci" / "rediacc_ci" / "quality").mkdir(parents=True)
    (root / "fx" / "scan").mkdir(parents=True)
    for name in ("__init__.py", "log.py", "paths.py", "controls.py"):
        shutil.copy2(src / ".ci" / "rediacc_ci" / name, root / ".ci" / "rediacc_ci" / name)
    for name in ("__init__.py", "%s.py" % MODULE):
        shutil.copy2(
            src / ".ci" / "rediacc_ci" / "quality" / name,
            root / ".ci" / "rediacc_ci" / "quality" / name,
        )
    if labels is not None:
        (root / "fx" / "labels.yml").write_text(labels, encoding="utf-8")
    for name, text in scan.items():
        (root / "fx" / "scan" / name).write_text(text, encoding="utf-8")
    return root


def run_port(root: pathlib.Path) -> tuple[int, str, str]:
    """The port, spelled exactly as the ledger licensed it."""
    return diff.bash_streams(
        "%s PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.ci python3 -m rediacc_ci.quality.%s"
        % (ENV_PREFIX, MODULE),
        cwd=str(root),
    )


def split_golden(text: str) -> tuple[int, str, str]:
    """A recorded twin render, back into its three parts."""
    exit_line, rest = text.split("\n", 1)
    stdout, stderr = rest.split("--- stdout ---\n", 1)[1].split("--- stderr ---\n", 1)
    return int(exit_line.removeprefix("exit: ")), stdout, stderr


def _cases():
    """The corpus, built at call time so no consumption shape is a literal here."""
    return [
        (
            "an undeclared label is reported with its one site",
            declarations("full-ci", "autopilot"),
            {"a.yml": search_filter("full-ci") + "\n", "b.js": js_const("ghost-label") + "\n"},
            1,
        ),
        (
            # THE NEGATIVE HALF. Both labels declared, so the gate must be silent. Without this a port that reported everything passes every red case.
            "declared labels are not reported",
            declarations("full-ci", "autopilot"),
            {"a.yml": search_filter("full-ci") + "\n", "b.js": js_const("autopilot") + "\n"},
            0,
        ),
        (
            "a templated placeholder is dropped rather than reported",
            declarations("full-ci", "autopilot"),
            {
                "a.yml": search_filter("full-ci") + "\n",
                "b.yml": "LABEL: ${{ vars.AUTOPILOT%s || 'autopilot' }}\n" % "_LABEL",
            },
            0,
        ),
        (
            "a sweep that collapses below the floor refuses",
            declarations("full-ci"),
            {"a.yml": search_filter("full-ci") + "\n"},
            1,
        ),
        (
            "an absent labels file is a failure, not a skip",
            None,
            {"a.yml": search_filter("full-ci") + "\n", "b.js": js_const("autopilot") + "\n"},
            1,
        ),
        (
            # THE 96355d3b5 CASE. An empty declaration file must reach the per-label loop, not kill the script at the assignment.
            "an EMPTY labels file reports every reference, and does not die silently",
            "",
            {"a.yml": search_filter("solo-alpha") + "\n", "b.js": js_const("solo-bravo") + "\n"},
            1,
        ),
    ]


def slug(case_id: str) -> str:
    """The golden's filename, DERIVED from the case id so the two cannot drift."""
    return re.sub(r"[^a-z0-9]+", "-", case_id.lower()).strip("-")


@pytest.mark.parametrize(
    ("case_id", "labels", "scan", "want_exit"),
    _cases(),
    ids=[c[0] for c in _cases()],
)
def test_port_matches_the_twins_recorded_output(tmp_path, case_id, labels, scan, want_exit):
    """Byte equality on BOTH streams against the twin's recording, plus the exit code."""
    root = build(tmp_path, labels, scan)
    want_exit_recorded, want_out, want_err = split_golden(frozen.read(SLUG, slug(case_id)))
    returncode, stdout, stderr = run_port(root)
    stdout = frozen.mask_root(stdout, root)
    stderr = frozen.mask_root(stderr, root)
    assert want_exit_recorded == want_exit, "the recorded verdict moved"
    assert returncode == want_exit_recorded, "the twin exited %d, the port %d" % (
        want_exit_recorded,
        returncode,
    )
    assert stdout == want_out, "stdout diverged from the twin's recorded bytes"
    assert stderr == want_err, "stderr diverged from the twin's recorded bytes"


def test_every_case_has_a_golden_and_no_golden_is_orphaned() -> None:
    """ANTI-VACUITY on the corpus: a case whose golden vanished would pass by never being compared, and a golden nothing reads is a recording of a case that stopped running."""
    frozen.assert_corpus(SLUG, {slug(c[0]) for c in _cases()})


def test_the_quiet_case_is_not_vacuously_equal() -> None:
    """Two implementations that both print nothing agree about nothing.

    This gate writes everything on stderr and nothing on stdout, so an all-empty recording would make every comparison above a comparison of two empty strings with the twin no longer around to blame. The quiet case must still SAY it found declared labels, the loud one must name the undeclared one, and the two must differ.
    """
    quiet = split_golden(frozen.read(SLUG, slug("declared labels are not reported")))
    loud = split_golden(
        frozen.read(SLUG, slug("an undeclared label is reported with its one site"))
    )
    assert quiet[0] == 0
    assert loud[0] == 1
    assert quiet[2].strip() != ""
    assert loud[2].strip() != ""
    assert quiet[2] != loud[2]


def test_planted_defect_is_caught_by_the_goldens(tmp_path) -> None:
    """THE CONTROL ON THE GOLDENS: a declaration reader that keeps the `- name:` prefix.

    The plant is a LOCAL re-read of the same declaration text with the prefix left on, never a change to the module. The green case's recording says both referenced labels ARE declared; a reader that answered `- name: full-ci` instead of `full-ci` matches nothing, so every reference becomes undeclared and the recorded bytes could not have been printed. The mutant and the real
    reader are compared directly, so a reader that stopped stripping reds here rather than quietly re-reporting the whole tree.
    """
    case_id = "declared labels are not reported"
    rc, _out, err = split_golden(frozen.read(SLUG, slug(case_id)))
    assert rc == 0
    assert "undeclared" not in err, "the recorded quiet case is no longer quiet"
    _id, labels, scan, _exit = next(c for c in _cases() if c[0] == case_id)
    real = gate.declared_labels(labels)
    mutant = [line for line in labels.split("\n") if line.startswith("- name:")]
    assert real, "the fixture declares nothing, so neither side can differ"
    assert mutant, "the mutant lists nothing, so neither side can differ"
    assert real != mutant, "the plant no longer diverges: the reader strips nothing"
    probe = tmp_path / "b.js"
    probe.write_text(scan["b.js"], encoding="utf-8")
    referenced = [label for name in gate.PATTERNS for label in gate.extract(name, [probe])]
    assert referenced, "the fixture references nothing, so declaredness decides nothing"
    assert all(label in real for label in referenced), "the quiet recording is unexplained"
    assert not any(label in mutant for label in referenced), "the mutant still matches"


def test_an_empty_labels_file_does_not_kill_the_reader():
    """The defect 96355d3b5 fixed, asserted at the function it lives in.

    `grep -E '^- name:'` exits 1 on a file with no declarations, and without `|| true` that killed the twin AT THE ASSIGNMENT under `set -e` -- so the floor message written for exactly this case ("this reader is broken, not the file") could never fire. The port cannot reproduce the defect, which is precisely why it needs a control: an empty list, never an exception.
    """
    assert gate.declared_labels("") == []
    assert gate.declared_labels("# only a comment\n") == []
    assert gate.declared_labels("- name: alpha\n") == ["alpha"]


def test_every_pattern_has_a_sample_and_the_sample_fires(tmp_path):
    """A pattern with no planted sample is a pattern nothing proves can fire."""
    sample = tmp_path / "sample.txt"
    for name, spec in gate.PATTERNS.items():
        assert "sample" in spec, "%s has no planted sample" % name
        sample.write_text("%s\n" % spec["sample"], encoding="utf-8")
        assert gate.extract(name, [sample]) == [gate.SELFTEST_LABEL], name


def test_no_pattern_matches_a_bare_mention(tmp_path):
    """The half the twin's inline self-test does not have.

    A pattern degraded to a bare identifier class would satisfy all ten of the twin's positive checks and then report every word in the tree as a label. Ten positive controls with no negative one is a gate that will happily flag the whole tree.
    """
    probe = tmp_path / "sample.txt"
    probe.write_text("the %s appears here only in prose\n" % gate.SELFTEST_LABEL, encoding="utf-8")
    for name in gate.PATTERNS:
        assert gate.extract(name, [probe]) == [], name


def test_this_file_and_the_port_contribute_no_label_references():
    """The self-poisoning control, and it is the reason this file is written oddly.

    Both files live under `.ci`, which the real sweep reads. If either carried a consumption shape as a literal, the REAL gate would report a phantom undeclared label and the tree would go red for a reason that has nothing to do
    with labels. That happened once, on 2026-09-06, while this port was being
    written; the fix was to assemble every shape at runtime.
    """
    here = pathlib.Path(__file__)
    port = pathlib.Path(diff.repo()) / ".ci" / "rediacc_ci" / "quality" / ("%s.py" % MODULE)
    for target in (here, port):
        for name in gate.PATTERNS:
            got = gate.extract(name, [target])
            assert got == [], "%s matches %s in %s" % (name, got, target.name)


def test_selftest_exits_zero_and_prints_a_count():
    """Exit 0 with zero PASS lines is a failure, so the count is asserted too."""
    code, out, err = diff.bash_streams(
        "PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.ci python3 -m rediacc_ci.quality.%s --selftest"
        % MODULE
    )
    assert code == 0, err
    assert "control(s) passed" in out
    # TWO controls per pattern, plus the structural ones. Derived from the registry rather than typed, so adding a shape without a sample reds this.
    assert int(out.split(" control(s)")[0].strip()) >= 2 * len(gate.PATTERNS)
