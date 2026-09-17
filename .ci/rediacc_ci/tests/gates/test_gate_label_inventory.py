"""Port of `.ci/scripts/test/gates/test-label-inventory.sh`.

Behavioural test for `.ci/scripts/quality/check-label-inventory.sh`.

WHAT IT GUARDS. The gate reconciles `.github/labels.yml` against the labels that
actually exist on the repo, in BOTH directions, and the direction that bit was
declared-but-absent: `rollback` was declared and referenced and did not exist, and
`promote-stable.yml` searches `label:rollback`. A GitHub search for a nonexistent
label returns zero PRs rather than an error, so the promotion block never fired.
Nothing said so. That is the class this gate catches.

Every case carries its control: a firing direction is only meaningful next to the
matching clean case, and a refusal is only meaningful next to a read that succeeds.

NO NETWORK. The live list is injected through `LABEL_INVENTORY_LIVE_FILE`, which is
also how the real-tree case below drives the REAL gate over the REAL
`.github/labels.yml`.

WHY THIS MODULE OPTS IN TO THE REAL-TREE GROUP. Three cases read the working tree
directly: the two real-tree cases derive their live list from `.github/labels.yml`
and drive the subject at it in place (real parse, real floor, real allowlist
verification against the real `report-nightly-status.cjs`), and the malformed-JSON
case copies the subject itself. A battery step rewriting either mid-read is a
divergence that would be blamed on this port. `REAL_TREE_TWIN = True` is what buys
the serialisation, and it is honoured only because this module declares no
`XDIST_GROUP` of its own; see `real_tree_admission` in `test_twin_parity.py`.

THE SUBJECT IS NEVER REIMPLEMENTED. Every verdict comes from the real
`bash check-label-inventory.sh`. The one piece of the twin rewritten in Python is
the mutant construction in `test_malformed_live_json_fails_closed`, which the twin
already writes in Python via a heredoc; the three anchors and their
count-exactly-one assertions are carried over verbatim, because a mutation that
lands somewhere else is a control that fires for the wrong reason.
"""

import os
import re

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

BASH_TWIN = ".ci/scripts/test/gates/test-label-inventory.sh"

# Two cases drive the subject over the real .github/labels.yml, and a third copies the subject out of the tree to build a mutant. See the module docstring.
REAL_TREE_TWIN = True

GATE_REL = ".ci/scripts/quality/check-label-inventory.sh"
GATE = paths.from_root(*GATE_REL.split("/"))
REAL_LABELS_REL = ".github/labels.yml"
REAL_LABELS = paths.from_root(*REAL_LABELS_REL.split("/"))

NAME_RE = re.compile(r"^- name:[ \t]*(.*)$")


def require_gate(gate) -> str:
    """The subject, proved present before anything is claimed."""
    if not GATE.is_file():
        gate.log_fail("subject under test is missing: %s" % GATE_REL)
    return harness.require_tool("bash", "install bash; the subject IS a bash script")


def run_gate(gate, labels_file, live_file, **extra: str) -> harness.RunResult:
    """`run_gate` from the twin: merged streams, env scoped to this call.

    The twin captures `2>&1` into `LAST_OUT` and asserts on the merged text, so the
    callers below read `.combined` for the same reason. Env is passed per call so
    one case cannot leak a seam into the next -- which is exactly what the twin's
    inline `VAR=... bash "$GATE"` form buys it.
    """
    bash = require_gate(gate)
    env = {
        "LABEL_INVENTORY_LABELS_FILE": os.fspath(labels_file),
        "LABEL_INVENTORY_LIVE_FILE": os.fspath(live_file),
    }
    env.update(extra)
    return harness.run([bash, os.fspath(GATE)], cwd=paths.repo_root(), env=env)


def write_labels(path, *names: str) -> None:
    """A declaration set big enough to clear the gate's own floor (5)."""
    body = "".join(
        '- name: %s\n  color: "FFFFFF"\n  description: "%s does a thing"\n\n' % (n, n)
        for n in names
    )
    path.write_text(body, encoding="utf-8")


def real_declared_names(gate) -> list[str]:
    """The real `.github/labels.yml` names, DERIVED and never hand-copied.

    `grep -E '^- name:' | sed -E 's/^- name:[[:space:]]*//'` in the twin. A
    hardcoded list here would be a second source of truth that rots the next time a
    label is added.

    ANTI-VACUITY: zero names is a FAILURE. Every real-tree assertion below is a
    claim about this list, and an empty one would make them all vacuously true.
    """
    if not REAL_LABELS.is_file():
        gate.log_fail(
            "the real declaration file is missing at %s, so the real-tree cases would "
            "reconcile nothing against nothing." % REAL_LABELS_REL
        )
    names = [
        m.group(1).strip()
        for m in (NAME_RE.match(ln) for ln in REAL_LABELS.read_text(encoding="utf-8").splitlines())
        if m
    ]
    if not names:
        gate.log_fail(
            "%s yielded ZERO label names, so the real-tree cases scanned nothing and "
            "their green would mean nothing." % REAL_LABELS_REL
        )
    return names


# ---------------------------------------------------------------------------


def test_matching_sets_are_clean(gate):
    """The control for everything below. Without it, a gate that failed on ANYTHING
    would pass all four firing cases."""
    with harness.temp_dir() as d:
        write_labels(d / "labels.yml", "one", "two", "three", "four", "five", "six")
        (d / "live.txt").write_text("one\ntwo\nthree\nfour\nfive\nsix\n", encoding="utf-8")
        result = run_gate(gate, d / "labels.yml", d / "live.txt")
        gate.assert_exit_code(
            0,
            result.rc,
            "matching declaration and live sets must pass (output: %s)" % result.combined,
        )
        gate.assert_contains(result.combined, "reconciled", "and say so")
        gate.log_pass("matching sets reconcile cleanly")


def test_declared_but_absent_fires(gate):
    """THE ROLLBACK CASE. A declared label that does not exist makes every search
    and filter on it fail open, silently."""
    with harness.temp_dir() as d:
        write_labels(d / "labels.yml", "one", "two", "three", "four", "five", "ghost-label")
        (d / "live.txt").write_text("one\ntwo\nthree\nfour\nfive\n", encoding="utf-8")
        result = run_gate(gate, d / "labels.yml", d / "live.txt")
        gate.assert_exit_code(1, result.rc, "a declared-but-absent label must fail the gate")
        gate.assert_contains(result.combined, "ghost-label", "the offender is named")
        gate.assert_contains(
            result.combined, "FAILS OPEN", "and the fail-open consequence is stated"
        )
        gate.assert_contains(result.combined, "gh label create", "with the exact fix")
        gate.log_pass("a declared-but-absent label fires, naming the fail-open risk")


def test_live_but_undeclared_fires(gate):
    with harness.temp_dir() as d:
        write_labels(d / "labels.yml", "one", "two", "three", "four", "five")
        (d / "live.txt").write_text("one\ntwo\nthree\nfour\nfive\nstowaway\n", encoding="utf-8")
        result = run_gate(gate, d / "labels.yml", d / "live.txt")
        gate.assert_exit_code(1, result.rc, "a live-but-undeclared label must fail the gate")
        gate.assert_contains(result.combined, "stowaway", "the offender is named")
        gate.assert_contains(
            result.combined,
            "label guide",
            "and the consequence (invisible to the PR guide) is stated",
        )
        gate.log_pass("a live-but-undeclared label fires")


def test_both_directions_report_together(gate):
    """A gate that exits on the first problem makes fixing an N-label drift an
    N-round job."""
    with harness.temp_dir() as d:
        write_labels(d / "labels.yml", "one", "two", "three", "four", "five", "ghost-label")
        (d / "live.txt").write_text("one\ntwo\nthree\nfour\nfive\nstowaway\n", encoding="utf-8")
        result = run_gate(gate, d / "labels.yml", d / "live.txt")
        gate.assert_exit_code(1, result.rc, "both-direction drift fails")
        gate.assert_contains(result.combined, "ghost-label", "the absent one is reported")
        gate.assert_contains(result.combined, "stowaway", "and the undeclared one, in the same run")
        gate.assert_contains(result.combined, "2 label inventory mismatch", "the count is exact")
        gate.log_pass("both directions are reported in one run")


def test_create_on_demand_label_is_forgiven_when_absent(gate):
    """`nightly-red` does not exist until the first red night, because
    `report-nightly-status.cjs` creates it right before opening the rolling issue.
    Declared-and-absent is its NORMAL state."""
    with harness.temp_dir() as d:
        write_labels(d / "labels.yml", "one", "two", "three", "four", "five", "nightly-red")
        (d / "live.txt").write_text("one\ntwo\nthree\nfour\nfive\n", encoding="utf-8")
        result = run_gate(gate, d / "labels.yml", d / "live.txt")
        gate.assert_exit_code(
            0,
            result.rc,
            "an absent create-on-demand label must NOT fail (output: %s)" % result.combined,
        )
        gate.assert_contains(
            result.combined,
            "created on demand",
            "and the exemption is stated out loud, not applied silently",
        )
        gate.log_pass("the create-on-demand label is forgiven while absent")


def test_create_on_demand_label_is_still_fine_when_present(gate):
    """The exemption forgives ABSENCE only; once the label exists it must not start
    failing the other direction."""
    with harness.temp_dir() as d:
        write_labels(d / "labels.yml", "one", "two", "three", "four", "five", "nightly-red")
        (d / "live.txt").write_text("one\ntwo\nthree\nfour\nfive\nnightly-red\n", encoding="utf-8")
        result = run_gate(gate, d / "labels.yml", d / "live.txt")
        gate.assert_exit_code(
            0,
            result.rc,
            "a present create-on-demand label is ordinary (output: %s)" % result.combined,
        )
        gate.log_pass("the create-on-demand label passes once it exists")


def test_a_stale_allowlist_entry_is_refused(gate):
    """The exemption must self-expire. If `nightly-red` stops being declared, the
    allowlist entry is a permanent hole pointing at nothing.

    The verification is scoped to the real declaration file (a fixture tree
    legitimately has no `nightly-red`), so the flag is driven on explicitly here
    rather than left to the scoping heuristic.
    """
    with harness.temp_dir() as d:
        write_labels(d / "labels.yml", "one", "two", "three", "four", "five")
        (d / "live.txt").write_text("one\ntwo\nthree\nfour\nfive\n", encoding="utf-8")
        result = run_gate(
            gate, d / "labels.yml", d / "live.txt", LABEL_INVENTORY_VERIFY_ALLOWLIST="true"
        )
        gate.assert_exit_code(
            1, result.rc, "an allowlist entry naming an undeclared label must fail"
        )
        gate.assert_contains(result.combined, "not declared", "and say the exemption is stale")
        gate.log_pass("a stale create-on-demand entry is refused, so the exemption cannot rot")


def test_empty_live_list_is_a_refusal_not_a_clean_tree(gate):
    """An empty list would make direction (b) vacuously green. This repo cannot have
    zero labels, so empty means the read failed."""
    with harness.temp_dir() as d:
        write_labels(d / "labels.yml", "one", "two", "three", "four", "five")
        (d / "live.txt").write_text("", encoding="utf-8")
        result = run_gate(gate, d / "labels.yml", d / "live.txt")
        gate.assert_exit_code(1, result.rc, "an empty live list must be refused")
        gate.assert_contains(result.combined, "EMPTY", "and named as a failed read")
        gate.assert_contains(result.combined, "failed read", "explicitly, not as a tree state")
        gate.log_pass("an empty live list is a refusal, not a clean tree")


def test_unreadable_live_source_is_a_refusal(gate):
    with harness.temp_dir() as d:
        write_labels(d / "labels.yml", "one", "two", "three", "four", "five")
        result = run_gate(gate, d / "labels.yml", d / "does-not-exist.txt")
        gate.assert_exit_code(1, result.rc, "an unreadable live source must be refused")
        gate.assert_contains(result.combined, "refuses to pass blind", "and say it is blind")
        gate.log_pass("an unreadable live source refuses rather than passing blind")


def test_a_broken_declaration_read_trips_the_floor(gate):
    """A parse yielding almost nothing is a broken parse, and treating it as a small
    declaration set would make direction (b) scream about every live label while
    direction (a) stayed silent."""
    with harness.temp_dir() as d:
        write_labels(d / "labels.yml", "one", "two")
        (d / "live.txt").write_text("one\ntwo\n", encoding="utf-8")
        result = run_gate(gate, d / "labels.yml", d / "live.txt")
        gate.assert_exit_code(1, result.rc, "a two-label declaration file must trip the floor")
        gate.assert_contains(result.combined, "floor", "and say the reader is broken, not the file")
        gate.log_pass("the declaration floor refuses a broken read")


def test_a_stale_list_read_is_re_verified_before_accusing(gate):
    """THE FALSE POSITIVE THIS EXISTS TO STOP.

    Observed on a real full run: the gate accused `no-auto-retry` of not existing
    while it existed and `watchdog-monitor.cjs` was reading it. Someone was mid-way
    through delete-and-recreate on it, and the paginated list came back one short.
    Wrong-by-one clears the empty-list guard and then fires this gate's loudest
    message, the one about rollback and silent fail-open -- and a gate that cries
    wolf that hard on a race gets ignored.
    """
    with harness.temp_dir() as d:
        write_labels(d / "labels.yml", "one", "two", "three", "four", "five", "racy")
        (d / "live.txt").write_text("one\ntwo\nthree\nfour\nfive\n", encoding="utf-8")
        # The single-label re-read disagrees with the list: `racy` does exist.
        (d / "probe.txt").write_text("one\ntwo\nthree\nfour\nfive\nracy\n", encoding="utf-8")
        result = run_gate(
            gate,
            d / "labels.yml",
            d / "live.txt",
            LABEL_INVENTORY_PROBE_FILE=os.fspath(d / "probe.txt"),
        )
        gate.assert_exit_code(
            0,
            result.rc,
            "a label the re-read finds must NOT be reported (output: %s)" % result.combined,
        )
        gate.assert_contains(
            result.combined, "re-read found it", "the re-verification is stated, not silent"
        )
        gate.assert_not_contains(
            result.combined, "FAILS OPEN", "and the alarming accusation is never printed"
        )
        gate.log_pass("a stale list read is re-verified, and the false positive is dropped")


def test_a_genuinely_absent_label_still_fires_after_re_verification(gate):
    """THE CONTROL, and the one that matters most: re-verification must not become a
    blanket excuse. When both reads agree the label is gone, the finding stands with
    its full message."""
    with harness.temp_dir() as d:
        write_labels(d / "labels.yml", "one", "two", "three", "four", "five", "ghost-label")
        (d / "live.txt").write_text("one\ntwo\nthree\nfour\nfive\n", encoding="utf-8")
        # The re-read agrees: ghost-label is absent from the probe set too.
        (d / "probe.txt").write_text("one\ntwo\nthree\nfour\nfive\n", encoding="utf-8")
        result = run_gate(
            gate,
            d / "labels.yml",
            d / "live.txt",
            LABEL_INVENTORY_PROBE_FILE=os.fspath(d / "probe.txt"),
        )
        gate.assert_exit_code(1, result.rc, "a label both reads agree is absent must still fail")
        gate.assert_contains(result.combined, "ghost-label", "the offender is still named")
        gate.assert_contains(result.combined, "FAILS OPEN", "with the full fail-open explanation")
        gate.assert_not_contains(
            result.combined, "re-read found it", "and no false re-verification note"
        )
        gate.log_pass("re-verification is not a blanket excuse: a real absence still fires")


def test_re_verification_does_not_touch_the_undeclared_direction(gate):
    """An EXTRA name cannot be a partial-read artifact -- a stale read loses entries,
    it does not invent them -- so direction (b) must fire whatever the probe says. A
    probe set that "confirms" the stowaway must not silence it, which is the mistake
    a symmetric implementation would make."""
    with harness.temp_dir() as d:
        write_labels(d / "labels.yml", "one", "two", "three", "four", "five")
        (d / "live.txt").write_text("one\ntwo\nthree\nfour\nfive\nstowaway\n", encoding="utf-8")
        (d / "probe.txt").write_text("one\ntwo\nthree\nfour\nfive\nstowaway\n", encoding="utf-8")
        result = run_gate(
            gate,
            d / "labels.yml",
            d / "live.txt",
            LABEL_INVENTORY_PROBE_FILE=os.fspath(d / "probe.txt"),
        )
        gate.assert_exit_code(
            1, result.rc, "the undeclared direction is unaffected by re-verification"
        )
        gate.assert_contains(result.combined, "stowaway", "and still names the offender")
        gate.log_pass("re-verification applies to the absent direction only")


def test_injected_mode_without_a_probe_seam_still_reports(gate):
    """The offline seam must keep working. With no probe file and no API to re-read,
    the injected list stands as its own authority: the probe reports "could not", and
    the finding is REPORTED rather than dropped. Failing the other way would make
    every offline run of this gate vacuously green."""
    with harness.temp_dir() as d:
        write_labels(d / "labels.yml", "one", "two", "three", "four", "five", "ghost-label")
        (d / "live.txt").write_text("one\ntwo\nthree\nfour\nfive\n", encoding="utf-8")
        result = run_gate(gate, d / "labels.yml", d / "live.txt")
        gate.assert_exit_code(1, result.rc, "an unprobeable absence is reported, not forgiven")
        gate.assert_contains(result.combined, "ghost-label", "naming it")
        gate.log_pass("with no probe available the finding stands (offline seam unchanged)")


def test_indented_fields_are_never_mistaken_for_names(gate):
    """`.github/labels.yml` carries `color:`, `description:` and `guide:` under each
    entry. The name extraction anchors on `^- name:`, so an indented field cannot be
    picked up -- but "it currently passes" is not the same as "it cannot". If a field
    value ever leaked in, the gate would report a phantom label (`false`, a hex
    colour) as declared-but-absent, and the fix would be hunting a label that was
    never a label."""
    with harness.temp_dir() as d:
        (d / "labels.yml").write_text(
            "- name: one\n"
            '  color: "FFFFFF"\n'
            '  description: "first"\n'
            "- name: two\n"
            '  color: "000000"\n'
            '  description: "second"\n'
            "  guide: false\n"
            "- name: three\n"
            '  color: "AAAAAA"\n'
            '  description: "third"\n'
            "  guide: true\n"
            "- name: four\n"
            '  color: "BBBBBB"\n'
            '  description: "fourth"\n'
            "- name: five\n"
            '  color: "CCCCCC"\n'
            '  description: "fifth"\n',
            encoding="utf-8",
        )
        (d / "live.txt").write_text("one\ntwo\nthree\nfour\nfive\n", encoding="utf-8")
        result = run_gate(gate, d / "labels.yml", d / "live.txt")
        gate.assert_exit_code(
            0,
            result.rc,
            "indented fields must not be read as label names (output: %s)" % result.combined,
        )
        gate.assert_contains(
            result.combined, "5 declared", "exactly the five names, not their field values"
        )
        gate.assert_not_contains(result.combined, "'false'", "no phantom label from a guide value")
        gate.assert_not_contains(result.combined, "FFFFFF", "no phantom label from a colour value")
        gate.log_pass("color/description/guide lines are never mistaken for label names")


def test_real_tree_reconciles_against_an_injected_live_list(gate):
    """THE REAL-TREE CASE, and the one the manifest BLOCKER points at.

    The gate runs seam-free over the REAL `.github/labels.yml` -- real parse, real
    floor, real allowlist verification against the real `report-nightly-status.cjs`
    -- with the live list injected so no network is touched. The live GitHub read
    itself cannot run in the quality lane (no label-read token there); it runs on
    `npm run check:ci-label-inventory`.
    """
    bash = require_gate(gate)
    names = real_declared_names(gate)
    with harness.temp_dir() as d:
        live = d / "live.txt"
        live.write_text("".join(n + "\n" for n in names), encoding="utf-8")
        result = harness.run(
            [bash, os.fspath(GATE)],
            cwd=paths.repo_root(),
            env={"LABEL_INVENTORY_LIVE_FILE": os.fspath(live)},
        )
        gate.assert_exit_code(
            0,
            result.rc,
            "the real labels file must reconcile against itself (output: %s)" % result.combined,
        )
        gate.assert_contains(result.combined, "reconciled", "the real run reports a reconciliation")

        # Control on the real tree: drop one real label from the live list and the real gate must fire. Without this, the case above would also pass if the gate had quietly become a no-op on the real file.
        dropped = names[0]
        short = d / "live-short.txt"
        short.write_text("".join(n + "\n" for n in names if n != dropped), encoding="utf-8")
        result = harness.run(
            [bash, os.fspath(GATE)],
            cwd=paths.repo_root(),
            env={"LABEL_INVENTORY_LIVE_FILE": os.fspath(short)},
        )
        gate.assert_exit_code(
            1, result.rc, "removing a real label from the live list must fire the real gate"
        )
        gate.assert_contains(result.combined, dropped, "naming the real label that went missing")

        # And the other direction, on the real tree.
        extra = d / "live-extra.txt"
        extra.write_text(
            "".join(n + "\n" for n in names) + "an-undeclared-live-label\n", encoding="utf-8"
        )
        result = harness.run(
            [bash, os.fspath(GATE)],
            cwd=paths.repo_root(),
            env={"LABEL_INVENTORY_LIVE_FILE": os.fspath(extra)},
        )
        gate.assert_exit_code(1, result.rc, "an extra live label must fire the real gate too")
        gate.assert_contains(result.combined, "an-undeclared-live-label", "naming it")

        gate.log_pass(
            "the real gate runs over the real labels file (%d declared label(s)) and fires "
            "in both directions" % len(names)
        )


def test_malformed_live_json_fails_closed(gate):
    """Found by the automated review of 01e7111c, and confirmed real.

    `LIVE_JSON` feeds a python heredoc that used to swallow a JSON decode failure
    with a bare `sys.exit(0)`. The outer bash captures that exit code as `drift_rc`,
    so a truncated/malformed API response (a real risk: `gh api ... --paginate ||
    echo ""` can leave partial stdout on a mid-stream failure) read as "the
    comparison ran and found nothing" -- the exact swallowed-failure class 1eac336b
    already fixed once at the shell `|| true` level, one layer down.
    """
    bash = require_gate(gate)
    names = real_declared_names(gate)
    with harness.temp_dir() as d:
        live = d / "live.txt"
        live.write_text("".join(n + "\n" for n in names), encoding="utf-8")
        bad_json = d / "live.json"
        bad_json.write_text("not valid json{{{", encoding="utf-8")
        env = {
            "LABEL_INVENTORY_LIVE_FILE": os.fspath(live),
            "LABEL_INVENTORY_LIVE_JSON_FILE": os.fspath(bad_json),
        }
        result = harness.run([bash, os.fspath(GATE)], cwd=paths.repo_root(), env=env)
        gate.assert_exit_code(
            1,
            result.rc,
            "malformed LIVE_JSON must fail closed, not report a clean tree (output: %s)"
            % result.combined,
        )
        gate.assert_contains(
            result.combined,
            "FAILED to run",
            "the failure names itself as an unreadable comparison, not a clean reconciliation",
        )
        if "all agree" in result.combined.lower():
            gate.log_fail("malformed LIVE_JSON was reported as a reconciled, agreeing tree")

        # CONTROL, built by construction: restore the exact bug this test exists for (a literal string replace of the CURRENT fixed line, not a pattern over unrelated text) and require the same input to flip to a false-clean exit 0. If it does not flip, this test is not measuring anything.
        #
        # The mutant is a plain copy elsewhere, so two more lines that assume the gate's OWN directory location also need patching, or it fails on those for a DIFFERENT reason (source-not-found, or "labels file not found" from get_repo_root()'s 3-levels-up walk landing nowhere) -- either of which looks identical to "control did not fire" without proving anything. Pinning both to
        # the real, already-known repo root sidesteps that path math entirely.
        mutant = d / "mutant-gate.sh"
        mutant.write_text(_mutate_subject(gate), encoding="utf-8")
        result = harness.run([bash, os.fspath(mutant)], cwd=paths.repo_root(), env=env)
        if result.rc == 1:
            gate.log_fail(
                "CONTROL DID NOT FIRE: the mutant with the old sys.exit(0) still failed closed"
            )
        gate.assert_exit_code(
            0,
            result.rc,
            "control: the pre-fix behavior swallows malformed JSON as a clean tree "
            "(output: %s)" % result.combined,
        )
        gate.log_pass("malformed LIVE_JSON fails closed; control proves the old code did not")


def _mutate_subject(gate) -> str:
    """The twin's python heredoc, verbatim in intent and in its three anchors.

    Each anchor must appear EXACTLY ONCE. An ambiguous anchor would patch the wrong
    occurrence and the control would prove nothing, so the count is asserted rather
    than assumed -- which is what the twin's `assert src.count(needle) == 1` does.
    """
    repo_root = os.fspath(paths.repo_root())
    src = GATE.read_text(encoding="utf-8")

    needle = "except Exception as e:"
    if src.count(needle) != 1:
        gate.log_fail(
            "mutation anchor missing or ambiguous: %r appears %d time(s) in %s"
            % (needle, src.count(needle), GATE_REL)
        )
    start = src.index(needle)
    end = src.index("sys.exit(1)", start) + len("sys.exit(1)")
    src = src[:start] + "except Exception:\n    sys.exit(0)" + src[end:]

    source_needle = 'source "$SCRIPT_DIR/../lib/common.sh"'
    if src.count(source_needle) != 1:
        gate.log_fail(
            "source anchor missing or ambiguous: %r appears %d time(s)"
            % (source_needle, src.count(source_needle))
        )
    src = src.replace(source_needle, "source %r" % (repo_root + "/.ci/scripts/lib/common.sh"), 1)

    root_needle = 'REPO_ROOT="$(get_repo_root)"'
    if src.count(root_needle) != 1:
        gate.log_fail(
            "REPO_ROOT anchor missing or ambiguous: %r appears %d time(s)"
            % (root_needle, src.count(root_needle))
        )
    return src.replace(root_needle, "REPO_ROOT=%r" % repo_root, 1)


def test_the_real_declaration_file_is_non_trivial(gate):
    """ADDED BY THE PORT: print the shape of the real corpus, so a collapse is
    visible rather than silent.

    `real_declared_names` already REFUSES an empty parse, which is the anti-vacuity
    half. This case states the number out loud on every run, because "the real gate
    reconciled" says nothing about how many labels it reconciled, and a declaration
    file that quietly shrank to the gate's floor of five would still read as green.
    """
    names = real_declared_names(gate)
    floor = 5
    if len(names) < floor:
        gate.log_fail(
            "%s declares only %d label(s), at or under the subject's own floor of %d. "
            "Either the parse broke or the file did." % (REAL_LABELS_REL, len(names), floor)
        )
    gate.log_pass(
        "%s declares %d label(s), comfortably over the subject's floor of %d"
        % (REAL_LABELS_REL, len(names), floor)
    )
