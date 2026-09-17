"""Port of `.ci/scripts/test/gates/test-label-references.sh`.

Behavioural test for `.ci/scripts/quality/check-label-references.sh`: every GitHub label a workflow or a `.ci` script references by name must be declared in `.github/labels.yml`.

WHAT IT GUARDS. Labels are this repo's kill switches and routing flags, and the failure is SILENT fail-open: `promote-stable.yml` searched for a label that did not exist, a search for a nonexistent label returns zero PRs rather than an error, so the promotion block simply never fired. `full-ci`, `autopilot` and `autopilot-blocked` were all referenced by merged code for weeks while
absent.

ONE DIRECTION ONLY, and that is a decision rather than an omission: a declared label nothing references is inventory, not an error. `test_declared_but_unreferenced_is_fine` is the case that pins it, and it is the converse without which every firing case here would also be satisfied by a gate that reds on anything.

WHY THIS MODULE OPTS IN TO THE REAL-TREE GROUP. Two cases drive the subject seam-free over the REAL tree: it recursively greps `.github` and `.ci` and reconciles what it finds against the real `.github/labels.yml`. A battery step writing under either directory mid-sweep is a divergence that would be blamed on
this port. `REAL_TREE_TWIN = True` buys the serialisation, and it is honoured
only because this module declares no `XDIST_GROUP` of its own; see `real_tree_admission` in `test_twin_parity.py`.

--------------------------------------------------------------------------
WHY EVERY FIXTURE LINE IN THIS FILE IS BUILT FROM A `%s` TEMPLATE
--------------------------------------------------------------------------
THIS IS THE LOAD-BEARING DIFFERENCE FROM THE TWIN, and getting it wrong would turn the real gate red for every session in the tree.

The subject sweeps `.ci` recursively, and it protects itself from its OWN planted samples by excluding exactly two basenames: `check-label-references.sh` and `test-label-references.sh`. The twin is one of those two, so the twin may write its fixture lines out literally. THIS FILE IS NOT ON THAT LIST, it lives under `.ci/rediacc_ci/tests/gates/`, and adding it would mean editing the
subject, which this port does not do.

So no complete, matchable reference shape may exist as a literal anywhere in this source. Every template below carries `%s` where the label goes, and `%` is outside the `[A-Za-z0-9._:-]` character class all ten extractors use, so each pattern fails to match the template and matches only the RENDERED fixture, which lives in a tempdir outside the repository.

`test_this_module_plants_no_label_reference_the_real_sweep_can_see` is the control on that reasoning: it points the real subject at this very directory with the floor dropped to zero, so a template that started matching reds HERE, by name, instead of reddening `check:ci-label-refs` for whoever runs it next.
"""

import os
import re

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

BASH_TWIN = ".ci/scripts/test/gates/test-label-references.sh"

# test_real_tree_is_clean_and_excludes_this_file and the added inertness control both drive the subject over the real .github and .ci trees. See the docstring.
REAL_TREE_TWIN = True

GATE_REL = ".ci/scripts/quality/check-label-references.sh"
GATE = paths.from_root(*GATE_REL.split("/"))
HERE_REL = ".ci/rediacc_ci/tests/gates"

# The subject's own floor on distinct references found in the real tree. Repeated here only so the real-tree case can PRINT the shape it swept; the number that governs is the one in the subject.
REAL_FLOOR = 8

# `all 23 code-referenced labels are declared in .github/labels.yml`
DISTINCT_RE = re.compile(r"all (\d+) code-referenced labels")

# The fixture label stem and the ten names, one per consumption shape the subject knows about. Built rather than written out; see the module docstring.
STEM = "fixture"
SUFFIXES = (
    "alpha",
    "beta",
    "gamma",
    "delta",
    "epsilon",
    "zeta",
    "eta",
    "theta",
    "iota",
    "kappa",
)


def label(suffix: str) -> str:
    return "%s-%s" % (STEM, suffix)


# One reference of every consumption shape, as TEMPLATES. Grouped by the fixture file each lands in, in the twin's order, so the two can be read side by side.
WORKFLOW_TEMPLATES = (
    "    if: contains(github.event.pull_request.labels.*.name, '%s')",
    "    run: gh api -f 'labels[]=%s'",
    '    run: gh pr list --search "label:%s"',
    "    LABEL: ${{ vars.AUTOPILOT_LABEL || '%s' }}",
)
CJS_TEMPLATES = (
    "if (labels.includes('%s')) {}",
    "const ISSUE_LABEL = '%s';",
    "const ISSUE_LABELS = ['%s', ISSUE_LABEL];",
)
SH_TEMPLATES = (
    'LABEL="${AUTOPILOT_LABEL:-%s}"',
    "jq -e --arg l \"%s\" '.labels | index($l)'",
    'grep -qx "%s" <<<"$labels"',
)

# The ten templates in the twin's order, so suffix i belongs to template i.
ALL_TEMPLATES = WORKFLOW_TEMPLATES + CJS_TEMPLATES + SH_TEMPLATES


def require_gate(gate) -> str:
    """The subject, proved present before anything is claimed."""
    if not GATE.is_file():
        gate.log_fail("subject under test is missing: %s" % GATE_REL)
    return harness.require_tool("bash", "install bash; the subject IS a bash script")


def run_gate(gate, root, labels, min_distinct: int = 1) -> harness.RunResult:
    """`run_gate` from the twin: the three env seams, merged streams.

    The twin captures `2>&1` into `LAST_OUT` and asserts on the merged text, so every caller below reads `.combined` for the same reason. Env is passed per
    call rather than exported, which is what the twin's inline `VAR=... bash` form
    buys it: one case cannot leak a seam into the next.
    """
    bash = require_gate(gate)
    return harness.run(
        [bash, os.fspath(GATE)],
        cwd=paths.repo_root(),
        env={
            "LABEL_REFS_SCAN_DIRS": os.fspath(root),
            "LABEL_REFS_LABELS_FILE": os.fspath(labels),
            "LABEL_REFS_MIN_DISTINCT": str(min_distinct),
        },
    )


def scaffold(gate, d):
    """`scaffold <dir>`: one reference of every consumption shape, all declared.

    ANTI-VACUITY, and it is not decoration. If the template list and the suffix list ever fall out of step, the fixture would exercise fewer shapes than the assertions claim and every count below would still be internally consistent. So the pairing is checked, and an empty template list is a FAILURE rather than a fixture that scans nothing.
    """
    if not ALL_TEMPLATES:
        gate.log_fail(
            "no reference templates are defined, so the scaffold would plant NOTHING "
            "and every case below would reconcile an empty set against an empty set."
        )
    if len(ALL_TEMPLATES) != len(SUFFIXES):
        gate.log_fail(
            "%d template(s) against %d label suffix(es): the fixture cannot exercise "
            "one shape per label." % (len(ALL_TEMPLATES), len(SUFFIXES))
        )
    scan = d / "scan"
    scan.mkdir(parents=True, exist_ok=True)
    names = [label(s) for s in SUFFIXES]
    rendered = [tpl % name for tpl, name in zip(ALL_TEMPLATES, names, strict=True)]
    split_a = len(WORKFLOW_TEMPLATES)
    split_b = split_a + len(CJS_TEMPLATES)
    (scan / "wf.yml").write_text("\n".join(rendered[:split_a]) + "\n", encoding="utf-8")
    (scan / "tool.cjs").write_text("\n".join(rendered[split_a:split_b]) + "\n", encoding="utf-8")
    (scan / "gate.sh").write_text("\n".join(rendered[split_b:]) + "\n", encoding="utf-8")
    (d / "labels.yml").write_text("".join("- name: %s\n" % n for n in names), encoding="utf-8")
    return names


# ---------------------------------------------------------------------------


def test_all_declared_passes(gate):
    """THE CONTROL FOR EVERY FIRING CASE, and the one that proves all ten extractors still extract. A pattern that silently stopped matching would drop its shape from the count, and the count is asserted exactly."""
    with harness.temp_dir() as d:
        names = scaffold(gate, d)
        result = run_gate(gate, d / "scan", d / "labels.yml", len(names))
        gate.assert_exit_code(
            0, result.rc, "every shape declared must pass (output: %s)" % result.combined
        )
        gate.assert_contains(
            result.combined,
            "all %d code-referenced labels" % len(names),
            "counts every consumption shape",
        )
        gate.log_pass("all ten consumption shapes are extracted and pass when declared")


def test_undeclared_reference_fails(gate):
    """FIRE: remove one declaration; the gate must name the label AND the file.

    Naming the site is the half that makes the finding actionable. "label X is undeclared" sends the reader grepping; "label X, referenced at tool.cjs" does not.
    """
    with harness.temp_dir() as d:
        names = scaffold(gate, d)
        dropped = label("epsilon")
        (d / "labels2.yml").write_text(
            "".join("- name: %s\n" % n for n in names if n != dropped), encoding="utf-8"
        )
        result = run_gate(gate, d / "scan", d / "labels2.yml", len(names) - 1)
        gate.assert_exit_code(1, result.rc, "an undeclared referenced label must fail")
        gate.assert_contains(result.combined, dropped, "names the undeclared label")
        gate.assert_contains(result.combined, "tool.cjs", "names the referencing site")
        gate.log_pass("an undeclared reference fails, naming label and site")


def test_declared_but_unreferenced_is_fine(gate):
    """Direction check: labels.yml may carry inventory nothing references."""
    with harness.temp_dir() as d:
        names = scaffold(gate, d)
        with open(d / "labels.yml", "a", encoding="utf-8") as handle:
            handle.write("- name: %s\n" % label("unused"))
        result = run_gate(gate, d / "scan", d / "labels.yml", len(names))
        gate.assert_exit_code(
            0, result.rc, "a declared-but-unreferenced label is inventory, not an error"
        )
        gate.log_pass("declaration without reference does not fail (one direction only)")


def test_floor_catches_a_dead_sweep(gate):
    """Anti-vacuity, IN THE SUBJECT: a scan surface with almost nothing in it must REFUSE, not report clean. That is how a wrong SCAN_DIRS would present, and reporting it clean is the exact shape this whole estate exists to refuse."""
    with harness.temp_dir() as d:
        scan = d / "scan"
        scan.mkdir(parents=True, exist_ok=True)
        (scan / "empty.txt").write_text("nothing label-shaped here\n", encoding="utf-8")
        (d / "labels.yml").write_text("- name: whatever\n", encoding="utf-8")
        result = run_gate(gate, scan, d / "labels.yml", 8)
        gate.assert_exit_code(1, result.rc, "a sweep under the floor must refuse")
        gate.assert_contains(result.combined, "floor", "says the sweep is broken, not clean")
        gate.log_pass("the distinct-labels floor refuses a dead sweep")


def test_real_tree_is_clean_and_excludes_this_file(gate):
    """THE REAL-TREE CASE. The real invocation over the real `.github` and `.ci`.

    It also proves the basename exclusion still works, because the TWIN plants matchable reference lines and is excluded by name; if that exclusion broke, the real gate would demand the twin's fixtures be declared in the real labels.yml.

    THE PORT ASSERTS MORE THAN THE TWIN HERE, in two ways. The twin looks for one leaked fixture label; this checks all ten, because an exclusion that broke for one shape broke for all of them and reporting the first is reporting a tenth of the finding. And the DISTINCT count is read out of the verdict line and printed, so a sweep that collapsed toward the subject's floor is
    visible rather than silent -- "the real tree is clean" says nothing about how much tree was swept.
    """
    bash = require_gate(gate)
    result = harness.run([bash, os.fspath(GATE)], cwd=paths.repo_root())
    gate.assert_exit_code(
        0, result.rc, "the real tree must be clean (output: %s)" % result.combined
    )
    for suffix in SUFFIXES:
        gate.assert_not_contains(
            result.combined,
            label(suffix),
            "this test's planted labels leaked into the real sweep: the basename exclusion broke",
        )
    match = DISTINCT_RE.search(result.combined)
    if not match:
        gate.log_fail(
            "the real run exited 0 without stating how many references it reconciled, "
            'so its green says nothing about what it swept. Output: "%s"' % result.combined
        )
    distinct = int(match.group(1))
    if distinct < REAL_FLOOR:
        gate.log_fail(
            "the real sweep found only %d distinct label reference(s), at or under the "
            "subject's own floor of %d." % (distinct, REAL_FLOOR)
        )
    gate.log_pass(
        "real tree clean over %d distinct label reference(s); this file's fixtures stay "
        "excluded from the sweep" % distinct
    )


def test_this_module_plants_no_label_reference_the_real_sweep_can_see(gate):
    """ADDED BY THE PORT, and it is the control on this port's central claim.

    The twin is excluded from the real sweep by basename. This module is NOT, and adding it would mean editing the subject. Instead every fixture line here is a `%s` template that no extractor can match, which is an argument, and an argument is not a control.

    So: point the REAL subject at this directory alone, with the floor dropped to zero so the sweep is allowed to legitimately find nothing, and reconcile against the REAL labels file. A template that started matching -- because a pattern was widened, or because someone wrote a fixture out literally -- shows up as an undeclared reference HERE, naming this file, instead of reddening
    `check:ci-label-refs` for whoever runs it next and sending them hunting.
    """
    here = paths.from_root(*HERE_REL.split("/"))
    if not here.is_dir():
        gate.log_fail("this module's own directory is missing at %s" % HERE_REL)
    modules = sorted(p.name for p in here.glob("*.py"))
    if not modules:
        gate.log_fail(
            "found ZERO python files under %s, so this control swept nothing and its "
            "green would mean nothing." % HERE_REL
        )
    result = run_gate(gate, here, paths.from_root(".github", "labels.yml"), 0)
    gate.assert_exit_code(
        0,
        result.rc,
        "the ported gate tests must contribute no label reference the real sweep can "
        "see (output: %s)" % result.combined,
    )
    for suffix in SUFFIXES:
        gate.assert_not_contains(
            result.combined,
            label(suffix),
            "a fixture template in this directory is now matchable by the real "
            "extractors; render it through a %s placeholder or exclude the file",
        )
    gate.log_pass(
        "%d ported gate-test module(s) under %s plant nothing the real extractors match"
        % (len(modules), HERE_REL)
    )
