"""`rediacc_ci.quality.label_references` against its bash twin.

A bash child runs the REAL `.ci/scripts/quality/check-label-references.sh` over a specimen with stdout and stderr captured SEPARATELY, and its bytes are compared against the port's. Same recipe as the committed ledger, `.ci/shadow/w7p2-label-references.observations.jsonl`.

THIS FILE ASSEMBLES EVERY LABEL-CONSUMING SHAPE AT RUNTIME, and that is not style. This file lives under `.ci`, which is one of the two directories the real sweep reads. Written as literals, its fixtures would BE label references, and the real gate would report them as undeclared: the port's first draft did exactly that, and `check-label-references.sh` went red naming
`.ci/rediacc_ci/quality/label_references.py`. The twin dodges the same problem by
excluding its own basename AND its test's basename; the port cannot use that dodge
without scanning a different corpus than the twin, so it removes the reason instead. Every helper below therefore builds its line from a token that is itself assembled.

BOTH DIRECTIONS. The corpus carries an undeclared label (must fire), a declared one (must stay quiet), a templated placeholder (must be dropped), a broken extractor (must be caught by the self-test before the sweep), a collapsed sweep (must hit the floor), and an EMPTY labels file, which is the case the twin's missing `|| true` made unreachable until 96355d3b5 on 2026-09-06.
"""

import pathlib
import shutil
import subprocess

import pytest

from rediacc_ci.quality import label_references as gate
from rediacc_ci.tests import differential as diff

TWIN = ".ci/scripts/quality/check-label-references.sh"
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
    (root / ".ci" / "scripts" / "quality").mkdir(parents=True)
    (root / ".ci" / "rediacc_ci" / "quality").mkdir(parents=True)
    (root / "fx" / "scan").mkdir(parents=True)
    shutil.copytree(src / ".ci" / "scripts" / "lib", root / ".ci" / "scripts" / "lib")
    shutil.copy2(src / TWIN, root / TWIN)
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


def run_both(root: pathlib.Path) -> tuple[tuple[int, str, str], tuple[int, str, str]]:
    old = diff.bash_streams("%s bash %s" % (ENV_PREFIX, TWIN), cwd=str(root))
    new = diff.bash_streams(
        "%s PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.ci python3 -m rediacc_ci.quality.%s"
        % (ENV_PREFIX, MODULE),
        cwd=str(root),
    )
    return old, new


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


@pytest.mark.parametrize(
    ("labels", "scan", "want_exit"),
    [(c[1], c[2], c[3]) for c in _cases()],
    ids=[c[0] for c in _cases()],
)
def test_differential(tmp_path, labels, scan, want_exit):
    """Byte equality on BOTH streams, plus the exit code the case expects."""
    root = build(tmp_path, labels, scan)
    (old_rc, old_out, old_err), (new_rc, new_out, new_err) = run_both(root)
    assert old_rc == want_exit, "the twin's verdict moved: %s%s" % (old_out, old_err)
    assert new_rc == old_rc
    assert new_out == old_out
    assert new_err == old_err


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


def test_the_twin_is_still_present():
    """Invariant 5: a twin is never deleted in the change that ports it."""
    assert (pathlib.Path(diff.repo()) / TWIN).is_file()
    assert subprocess.run(["bash", "-c", "true"], check=False).returncode == 0
