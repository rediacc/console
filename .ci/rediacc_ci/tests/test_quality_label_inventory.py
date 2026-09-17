"""`rediacc_ci.quality.label_inventory` against its bash twin.

A bash child runs the REAL `.ci/scripts/quality/check-label-inventory.sh` over a
specimen with stdout and stderr captured SEPARATELY, and its bytes are compared
against the port's. Same recipe as the committed ledger,
`.ci/shadow/w7p2-label-inventory.observations.jsonl`.

EVERY CASE USES THE INJECTION SEAMS, so no case touches the network. That is the
twin's own design (`LABEL_INVENTORY_LIVE_FILE`, `LABEL_INVENTORY_PROBE_FILE`,
`LABEL_INVENTORY_LIVE_JSON_FILE`), and the PROBE seam is separate from the LIST
seam on purpose: "the whole point of the re-read is that it can disagree with the
list."

BOTH DIRECTIONS, EVERYWHERE. This gate reconciles two directions and then checks a
third property, so a port can be wrong in six ways. The corpus carries a clean
reconciliation (must be silent), a declared-but-absent label, a live-but-undeclared
label, both at once, a collapsed declaration parse, an over-cap description at the
boundary on BOTH sides of it, an EMPTY live list (a failed read, never a clean
tree), an EMPTY declaration file (the case the twin's missing `|| true` made
unreachable until 96355d3b5 on 2026-09-06), a stale-list rescue by re-read, a real
field drift, and an UNREADABLE drift comparison.

THE LAST ONE IS THE SUBTLE ONE. `|| true` around the drift comparison would make a
CRASHED comparator indistinguishable from "the labels agree" -- empty output either
way. check-swallowed-failures.sh caught exactly that shape at the shell level
(1eac336b) and the twin's embedded python carries the same warning one level down.
The port expresses it as an exception type rather than an exit code, and this file
asserts that the exception is what happens.
"""

import json
import pathlib
import shutil

import pytest

from rediacc_ci.quality import label_inventory as gate
from rediacc_ci.tests import differential as diff

TWIN = ".ci/scripts/quality/check-label-inventory.sh"
MODULE = "label_inventory"

SEAM_ENV = "LABEL_INVENTORY_LABELS_FILE=fx/labels.yml LABEL_INVENTORY_LIVE_FILE=fx/live.txt"
PROBE_ENV = SEAM_ENV + " LABEL_INVENTORY_PROBE_FILE=fx/probe.txt"
REAL_PATH_ENV = (
    "LABEL_INVENTORY_LABELS_FILE=.github/labels.yml "
    "LABEL_INVENTORY_LIVE_FILE=fx/live.txt "
    "LABEL_INVENTORY_LIVE_JSON_FILE=fx/live.json"
)


def declarations(*labels: str) -> str:
    return "".join(
        "- name: %s\n  color: ffffff\n  description: d-%s\n" % (label, label) for label in labels
    )


def build(tmp_path: pathlib.Path, files: dict[str, str]) -> pathlib.Path:
    """A specimen with both implementations, the allowlist's two creator files, and `files`.

    THE CREATOR FILES ARE NOT OPTIONAL. The allowlist is self-expiring: it verifies
    that each named creator still exists AND still mentions its label, so a fixture
    without them fails for a reason that has nothing to do with the case.
    """
    src = pathlib.Path(diff.repo())
    root = tmp_path / "fixture"
    for rel in (
        ".ci/scripts/quality",
        ".ci/scripts/ci",
        ".ci/scripts/review",
        ".ci/rediacc_ci/quality",
        ".github",
        "fx",
    ):
        (root / rel).mkdir(parents=True, exist_ok=True)
    shutil.copytree(src / ".ci" / "scripts" / "lib", root / ".ci" / "scripts" / "lib")
    shutil.copy2(src / TWIN, root / TWIN)
    for name in ("__init__.py", "log.py", "paths.py", "controls.py"):
        shutil.copy2(src / ".ci" / "rediacc_ci" / name, root / ".ci" / "rediacc_ci" / name)
    for name in ("__init__.py", "%s.py" % MODULE):
        shutil.copy2(
            src / ".ci" / "rediacc_ci" / "quality" / name,
            root / ".ci" / "rediacc_ci" / "quality" / name,
        )
    (root / ".ci" / "scripts" / "ci" / "report-nightly-status.cjs").write_text(
        'issues.createLabel({name: "nightly-red"})\n', encoding="utf-8"
    )
    (root / ".ci" / "scripts" / "review" / "claude-review-gate.sh").write_text(
        "gh label create ci\ngh label create bump-none\n", encoding="utf-8"
    )
    for rel, text in files.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        if rel.startswith("fxbin/"):
            target.chmod(0o755)
    return root


def run_both(root: pathlib.Path, env: str) -> tuple[tuple[int, str, str], tuple[int, str, str]]:
    old = diff.bash_streams("%s bash %s" % (env, TWIN), cwd=str(root))
    new = diff.bash_streams(
        "%s PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.ci python3 -m rediacc_ci.quality.%s"
        % (env, MODULE),
        cwd=str(root),
    )
    return old, new


FIVE = ("alpha", "bravo", "charlie", "delta", "echo1")

CASES = [
    (
        # THE NEGATIVE HALF, first. Both directions agree, so the gate must be
        # silent; without this every red case below is satisfied by a port that
        # reports everything.
        "a reconciled inventory is silent",
        {"fx/labels.yml": declarations(*FIVE), "fx/live.txt": "\n".join(FIVE) + "\n"},
        SEAM_ENV,
        0,
    ),
    (
        "a declared label absent from the repo is a fail-open finding",
        {
            "fx/labels.yml": declarations(*FIVE, "foxtrot"),
            "fx/live.txt": "\n".join(FIVE) + "\n",
        },
        SEAM_ENV,
        1,
    ),
    (
        "a live label declared nowhere is a finding",
        {"fx/labels.yml": declarations(*FIVE), "fx/live.txt": "\n".join([*FIVE, "zulu"]) + "\n"},
        SEAM_ENV,
        1,
    ),
    (
        "a collapsed declaration parse refuses rather than screaming",
        {"fx/labels.yml": declarations("alpha", "bravo"), "fx/live.txt": "alpha\nbravo\n"},
        SEAM_ENV,
        1,
    ),
    (
        # THE 96355d3b5 CASE. An empty declaration file must reach the floor, not kill the script at the assignment with zero bytes on both streams.
        "an EMPTY declaration file reaches the floor rather than dying silently",
        {"fx/labels.yml": "", "fx/live.txt": "alpha\nbravo\n"},
        SEAM_ENV,
        1,
    ),
    (
        "an EMPTY live list is a failed read, never a clean tree",
        {"fx/labels.yml": declarations(*FIVE), "fx/live.txt": ""},
        SEAM_ENV,
        1,
    ),
    (
        "a 101-character description is refused at declaration time",
        {
            "fx/labels.yml": declarations(*FIVE)
            + '- name: longone\n  color: ffffff\n  description: "%s"\n' % ("x" * 101),
            "fx/live.txt": "\n".join([*FIVE, "longone"]) + "\n",
        },
        SEAM_ENV,
        1,
    ),
    (
        # THE BOUNDARY, the other side. 100 is allowed, so the cap check must be silent here or it is an off-by-one that reds a legal file.
        "a 100-character description is allowed",
        {
            "fx/labels.yml": declarations(*FIVE)
            + '- name: longone\n  color: ffffff\n  description: "%s"\n' % ("x" * 100),
            "fx/live.txt": "\n".join([*FIVE, "longone"]) + "\n",
        },
        SEAM_ENV,
        0,
    ),
    (
        # VERIFY-AT-READ. The list is one short, the re-read finds the label, and the finding is dropped with a warning rather than accusing a live label of deletion. This is the cry-wolf case from the live CI run.
        "a stale list entry rescued by the re-read is a warning, not a finding",
        {
            "fx/labels.yml": declarations(*FIVE, "golf"),
            "fx/live.txt": "\n".join(FIVE) + "\n",
            "fx/probe.txt": "golf\n",
        },
        PROBE_ENV,
        0,
    ),
    (
        # AND ITS MIRROR. The re-read CONFIRMS absence, so the finding stands.
        "a re-read that confirms absence keeps the finding",
        {
            "fx/labels.yml": declarations(*FIVE, "golf"),
            "fx/live.txt": "\n".join(FIVE) + "\n",
            "fx/probe.txt": "alpha\n",
        },
        PROBE_ENV,
        1,
    ),
    (
        "a drifted description is a finding on the real declaration path",
        {
            ".github/labels.yml": declarations(
                "alpha", "bravo", "charlie", "nightly-red", "ci", "bump-none"
            ),
            "fx/live.txt": "alpha\nbravo\ncharlie\n",
            "fx/live.json": json.dumps(
                [
                    {"name": "alpha", "description": "drifted", "color": "ffffff"},
                    {"name": "bravo", "description": "d-bravo", "color": "ffffff"},
                    {"name": "charlie", "description": "d-charlie", "color": "ffffff"},
                ]
            ),
        },
        REAL_PATH_ENV,
        1,
    ),
    (
        "an UNREADABLE drift comparison is never a clean tree",
        {
            ".github/labels.yml": declarations(
                "alpha", "bravo", "charlie", "nightly-red", "ci", "bump-none"
            ),
            "fx/live.txt": "alpha\nbravo\ncharlie\n",
            "fx/live.json": '[{"name":"alpha","desc',
        },
        REAL_PATH_ENV,
        1,
    ),
    (
        # FIXED 2026-09-10. Neither LIVE_FILE nor LIVE_JSON_FILE is set, so LIVE_SOURCE falls to "GitHub API" for BOTH the names-only read (which succeeds) and the drift-comparison full-object read (which fails). Before the fix, a failed drift read silently skipped the description/ colour comparison and the gate reported "all agree" anyway.
        "a failed live-JSON fetch over the real GitHub API path refuses, not skips",
        {
            ".github/labels.yml": declarations(
                "alpha", "bravo", "charlie", "nightly-red", "ci", "bump-none"
            ),
            "fxbin/gh": (
                "#!/bin/bash\n"
                'for a in "$@"; do [ "$a" = "--jq" ] && '
                "{ printf 'alpha\\nbravo\\ncharlie\\nnightly-red\\nci\\nbump-none\\n'; exit 0; }; "
                "done\n"
                "echo 'HTTP 500: simulated failure' >&2\n"
                "exit 1\n"
            ),
        },
        'LABEL_INVENTORY_LABELS_FILE=.github/labels.yml PATH="$PWD/fxbin:$PATH"',
        1,
    ),
]


@pytest.mark.parametrize(
    ("files", "env", "want_exit"),
    [(c[1], c[2], c[3]) for c in CASES],
    ids=[c[0] for c in CASES],
)
def test_differential(tmp_path, files, env, want_exit):
    """Byte equality on BOTH streams, plus the exit code the case expects."""
    root = build(tmp_path, files)
    (old_rc, old_out, old_err), (new_rc, new_out, new_err) = run_both(root, env)
    assert old_rc == want_exit, "the twin's verdict moved: %s%s" % (old_out, old_err)
    assert new_rc == old_rc
    assert new_out == old_out
    assert new_err == old_err


def test_an_unreadable_drift_raises_rather_than_returning_nothing():
    """The swallowed-failure distinction, at the function that owns it.

    "the comparison ran and found nothing" and "the comparison never ran" must not
    be the same value. An empty list for malformed JSON would make a crashed
    comparator report "names, descriptions and colours all agree".
    """
    with pytest.raises(gate.DriftUnreadableError):
        gate.drift("{", "- name: a\n")
    with pytest.raises(gate.DriftUnreadableError):
        gate.drift('[{"name":"a"', "- name: a\n")
    assert gate.drift("[]", "- name: a\n  description: x\n") == []


def test_the_probe_has_three_outcomes(tmp_path):
    """0 exists, 1 CONFIRMED absent, 2 could not probe. Never two.

    Only a 404 confirms absence; a 403, a 500 or a network error says nothing about
    the label and must not be read as agreement with a stale list.
    """
    present = tmp_path / "probe.txt"
    present.write_text("alpha\n", encoding="utf-8")
    env = {gate.PROBE_FILE_ENV: str(present)}
    assert gate.probe_label("alpha", env) == 0
    assert gate.probe_label("gamma", env) == 1
    assert gate.probe_label("alpha", {gate.PROBE_FILE_ENV: str(tmp_path / "nope")}) == 2
    assert gate.probe_label("alpha", {gate.LIVE_FILE_ENV: "x"}) == 2


def test_the_allowlist_is_short_and_every_entry_names_a_creator():
    """A stale exemption is a permanent hole, so both halves are verifiable.

    The entries are also PRINTED on every run (`log_info`), which is the house rule
    about quiet exemptions: a forgiven label that never appears in the output is a
    debt nobody can see.
    """
    assert len(gate.CREATE_ON_DEMAND) == 3
    for entry in gate.CREATE_ON_DEMAND:
        name, _, creator = entry.partition("|")
        assert name, entry
        assert creator, entry
        assert creator.startswith(".ci/"), entry


def test_the_declaration_reader_keeps_the_twins_unquoting_order():
    """A bug carried on purpose, because fixing it changes which names reconcile.

    The trailing-whitespace strip runs AFTER the unquote, so `- name: "x"  ` keeps
    its quotes: the `^"(.*)"$` anchor fails while the spaces are still there.
    """
    assert gate.declared_labels('- name: "alpha"\n') == ["alpha"]
    assert gate.declared_labels("- name: 'alpha'\n") == ["alpha"]
    assert gate.declared_labels("- name: alpha   \n") == ["alpha"]
    assert gate.declared_labels('- name: "alpha"  \n') == ['"alpha"']
    assert gate.declared_labels("") == []


def test_the_description_cap_is_exact_at_the_boundary():
    """100 passes, 101 fails. An off-by-one here reds a legal file or misses a real one."""
    assert gate.desc_over_cap('- name: a\n  description: "%s"\n' % ("x" * 100)) == []
    assert gate.desc_over_cap('- name: a\n  description: "%s"\n' % ("x" * 101)) == [("a", 101)]


def test_selftest_exits_zero_and_prints_a_count():
    """Exit 0 with zero PASS lines is a failure, so the count is asserted too."""
    code, out, err = diff.bash_streams(
        "PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.ci python3 -m rediacc_ci.quality.%s --selftest"
        % MODULE
    )
    assert code == 0, err
    assert "control(s) passed" in out
    assert int(out.split(" control(s)")[0].strip()) >= 24


def test_the_twin_is_still_present():
    """Invariant 5: a twin is never deleted in the change that ports it."""
    assert (pathlib.Path(diff.repo()) / TWIN).is_file()
