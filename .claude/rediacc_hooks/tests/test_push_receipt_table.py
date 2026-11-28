"""The push-receipt rule table (`rediacc_hooks.guards._push_receipts`, box CR6 of agent/plans/PLAN-tooling-code-reduction.md).

THE ADMIT-LINE PARITY TEST enumerates the rows: ci:quick, vm:check, backup and renet, one per push guard. On the live tree every row's admit line is in its guard's refusal and names a real npm script or drill, every reader resolves, and the rows are exactly the guards that import the table. Each check has a control that turns it red: an edited admit line in a refusal, an admit line naming a script package.json lacks, a renamed reader, an ORDER or escape variable that drifted, and a guard importing the table with no row. The seam (the two-track R4 CI-receipt verifier as one more reader) and the shared escape judgement are pinned too, both directions.
"""

from __future__ import annotations

import dataclasses
import importlib
import json
import types

PR = importlib.import_module("rediacc_hooks.guards._push_receipts")
STEMS = (
    "block_unverified_push",
    "block_vm_unverified_push",
    "block_backup_unverified_push",
    "block_renet_untested_push",
)


def _module_copy(stem, **over):
    """A stand-in for a guard module: every public attribute of the real one, with `over` replacing some."""
    real = importlib.import_module("rediacc_hooks.guards.%s" % stem)
    ns = types.SimpleNamespace(**{k: getattr(real, k) for k in dir(real) if not k.startswith("__")})
    for k, v in over.items():
        setattr(ns, k, v)
    return ns


# --------------------------------------------------------------------------- the table on the live tree


def test_rows_enumerate_the_four_push_guards():
    assert [r.id for r in PR.ROWS] == ["ci:quick", "vm:check", "backup", "renet"]
    assert tuple(r.guard for r in PR.ROWS) == STEMS
    assert sorted(PR.importing_guards()) == sorted(STEMS)


def test_admit_parity_on_the_live_tree_is_clean():
    found = PR.admit_parity(guard_stems=PR.importing_guards())
    assert found == [], "\n".join(found)
    lines = [line for r in PR.ROWS for line in r.admit]
    # The shape, so a collapse is visible: four rows, five admit lines.
    assert len(PR.ROWS) == 4
    assert len(lines) == 5, lines


def test_each_guard_reads_its_constants_from_its_row():
    for r in PR.ROWS:
        mod = importlib.import_module("rediacc_hooks.guards.%s" % r.guard)
        assert mod.ROW is r
        if r.escape:
            assert (r.escape, r.kinds, r.ledger) == (mod.REASON_ENV, mod.KINDS, mod.LEDGER_REL)
    ci = importlib.import_module("rediacc_hooks.guards.block_unverified_push")
    assert ci.V2_REGEN == "npm run ci:quick"


# --------------------------------------------------------------------------- controls: each turns the parity red


def test_control_an_edited_admit_line_in_a_refusal_turns_it_red():
    vm = _module_copy("block_vm_unverified_push")
    vm.REFUSAL = vm.REFUSAL.replace("npm run vm:check -- --changed", "npm run vm:check -- --changd")
    found = PR.admit_parity(modules={"block_vm_unverified_push": vm})
    assert any(
        f.startswith("vm:check: admit line `npm run vm:check -- --changed` is not in")
        for f in found
    ), found
    assert all(f.startswith("vm:check:") for f in found), found


def test_control_an_edited_ci_quick_tail_turns_it_red():
    ci = _module_copy("block_unverified_push")
    ci.REFUSAL_TAIL = ci.REFUSAL_TAIL.replace("  npm run ci:quick\n", "  npm run ci-quick\n")
    found = PR.admit_parity(modules={"block_unverified_push": ci})
    assert any("ci:quick: admit line `npm run ci:quick`" in f for f in found), found


def test_control_an_edited_renet_command_turns_it_red():
    """The renet refusal prints `%(command)s`, filled from COMMAND: the parity fills it the same way, so an edited COMMAND is caught."""
    rn = _module_copy("block_renet_untested_push", COMMAND="npm run check:ci-renet-tests")
    found = PR.admit_parity(modules={"block_renet_untested_push": rn})
    assert any(
        "renet: admit line `npm run check:ci-renet-test-map` is not in" in f for f in found
    ), found


def test_control_an_admit_line_naming_no_script_turns_it_red():
    """`npm run <missing>` exits 1 with nothing on either stream under --silent, so a refusal naming one would send the reader to a dead command."""
    rows = (dataclasses.replace(PR.row("ci:quick"), admit=("npm run ci:quick",)),)
    scripts = {"vm:check": "x"}
    found = PR.admit_parity(rows=rows, scripts=scripts)
    assert found == [
        "ci:quick: admit line `npm run ci:quick` names no package.json script 'ci:quick'"
    ], found


def test_control_an_admit_line_naming_no_drill_turns_it_red():
    found = PR.admit_parity(rows=(PR.row("backup"),), drills={"backup": "m"})
    assert found == [
        "backup: admit line `./run.sh drill backup-onprem` names no drill 'backup-onprem' in run_verbs.DRILL_MODULES"
    ], found


def test_control_a_renamed_reader_turns_it_red():
    rows = (dataclasses.replace(PR.row("renet"), reader="stop:wl_renettests:read_receipt_gone"),)
    found = PR.admit_parity(rows=rows)
    assert len(found) == 1, found
    assert found[0].startswith(
        "renet: reader 'stop:wl_renettests:read_receipt_gone' does not resolve"
    )


def test_control_a_drifted_order_or_escape_turns_it_red():
    bk = _module_copy("block_backup_unverified_push", ORDER=99, REASON_ENV="BACKUP_REASON")
    found = PR.admit_parity(rows=(PR.row("backup"),), modules={"block_backup_unverified_push": bk})
    assert "backup: block_backup_unverified_push.ORDER is 99, the row says 63" in found, found
    assert any(
        f.startswith("backup: block_backup_unverified_push.REASON_ENV is 'BACKUP_REASON'")
        for f in found
    ), found


def test_control_a_guard_importing_the_table_without_a_row_turns_it_red():
    found = PR.admit_parity(guard_stems=[*STEMS, "block_new_receipt_push"])
    assert found == [
        "table: block_new_receipt_push imports the push-receipt table but has no row"
    ], found
    found = PR.admit_parity(guard_stems=STEMS[:3])
    assert found == [
        "table: row guard block_renet_untested_push does not import the push-receipt table"
    ], found


def test_control_a_kind_declared_twice_turns_it_red():
    found = PR.admit_parity(rows=(PR.row("vm:check"), PR.row("vm:check")))
    assert found == ["table: receipt kind 'vm:check' is declared twice"], found


def test_control_importing_guards_reads_the_import_line(tmp_path):
    (tmp_path / "block_a.py").write_text(
        "from rediacc_hooks.guards import _backup_push, _push_receipts\n"
    )
    (tmp_path / "block_b.py").write_text(
        "# from rediacc_hooks.guards import _push_receipts\nimport os\n"
    )
    assert PR.importing_guards(tmp_path) == ["block_a"]


# --------------------------------------------------------------------------- the seam: the CI-receipt verifier is one more reader


def test_readers_put_the_ci_receipt_verifier_beside_the_tree_reader():
    ci = importlib.import_module("rediacc_hooks.guards.block_unverified_push")
    got = PR.readers("ci:quick")
    assert got == {"tree": ci.read_receipt, "ci": ci.ci_origin_gate}
    assert set(PR.readers("vm:check")) == {"tree"}


def test_the_vm_and_backup_tree_readers_read_a_receipt_and_are_not_the_verdict_function(
    monkeypatch,
):
    """edfc3e69.1/.2: `readers(...)["tree"]` is a `(root, tree)` reader: it returns the per-tree archive its module reads, and it is neither row's `admit`. Control: a tree with no archive reads None."""
    tree = "e" * 40
    doc = {"tree": tree, "verdict": "VERIFIED"}
    held: dict[str, dict[str, str] | None] = {"archive": None}
    fake = types.SimpleNamespace(
        read_archive=lambda _root, _tree: held["archive"], read_latest=lambda _root: None
    )
    monkeypatch.setattr(PR, "_vm_tier", lambda: fake)
    monkeypatch.setattr(PR, "_backup_trigger", lambda: fake)
    for row_id in ("vm:check", "backup"):
        reader = PR.readers(row_id)["tree"]
        assert reader is not PR.resolve(PR.row(row_id), PR.row(row_id).reader), row_id
        held["archive"] = None
        assert reader("/root", tree) is None, row_id
        held["archive"] = doc
        assert reader("/root", tree) == doc, row_id


def test_a_new_origin_kind_registers_through_the_same_interface(monkeypatch):
    ci = importlib.import_module("rediacc_hooks.guards.block_unverified_push")

    def other(*_reader_args):
        return None, "fixture"

    monkeypatch.setitem(ci.ORIGIN_READERS, "other-ci", other)
    assert PR.readers("ci:quick")["other-ci"] is other
    assert PR.admit_parity(rows=(PR.row("ci:quick"),)) == []
    # Control: an origin map that is not a map of readers is named.
    monkeypatch.setitem(ci.ORIGIN_READERS, "broken", "not callable")
    assert PR.admit_parity(rows=(PR.row("ci:quick"),)) == [
        "ci:quick: block_unverified_push.ORIGIN_READERS is not a non-empty map of readers"
    ]


# --------------------------------------------------------------------------- the shared escape judgement


class Ev:
    def __init__(self):
        self.warnings = []

    def warn(self, text):
        self.warnings.append(text)


ASK = " ASKED:2026-01-01T00:00Z"
WHY = "the 03:00Z CD promote carries the broken stable licence check otherwise"


def _judge(row_id, reason, answered=True):
    return PR.judge_escape(Ev(), row_id, reason, lambda _ev, _reason: answered)


def test_judge_escape_admits_a_full_escape_and_refuses_each_missing_part():
    env = PR.row("renet").escape
    assert _judge("renet", "deadline: %s%s" % (WHY, ASK)) == ("deadline", WHY)
    assert _judge("renet", None) == (None, "escape-missing: no `%s=` on it" % env)
    assert _judge("renet", "because: %s%s" % (WHY, ASK))[1].startswith(
        "escape-kind: `RENET_TEST_PUSH_REASON='because:"
    )
    assert _judge("renet", "deadline: soon%s" % ASK)[1] == (
        "escape-why: `deadline: soon%s`: the why is 4 characters; at least 40 name the tests or the deadline"
        % ASK
    )
    assert _judge("vm:check", "deadline: soon%s" % ASK)[1].endswith(
        "name the files or the deadline"
    )
    assert _judge("renet", "deadline: %s" % WHY)[1].startswith("escape-asked:")
    assert _judge("renet", "deadline: %s%s" % (WHY, ASK), answered=False)[1].startswith(
        "escape-unproven:"
    )
    # A kind of another row is not this row's.
    assert _judge("renet", "not-runtime: %s%s" % (WHY, ASK))[0] is None


def test_record_appends_one_line_per_row_and_names_a_failed_write(tmp_path):
    ev = Ev()
    PR.record(ev, "renet", tmp_path, [{"b": 2, "a": 1}, {"c": 3}])
    lines = (tmp_path / PR.row("renet").ledger).read_text().splitlines()
    assert [json.loads(line) for line in lines] == [{"a": 1, "b": 2}, {"c": 3}]
    assert lines[0] == '{"a": 1, "b": 2}'
    assert ev.warnings == []
    blocked = tmp_path / "file"
    blocked.write_text("")
    PR.record(ev, "vm:check", blocked, [{"a": 1}])
    assert len(ev.warnings) == 1
    assert ev.warnings[0].startswith(
        "block-vm-unverified-push: the admission was NOT recorded in agent/ledgers/vm-check-push-reasons.jsonl ("
    )


def test_asked_minute():
    assert PR.asked_minute("x ASKED:2026-01-01T00:00Z") == "2026-01-01T00:00Z"
    assert PR.asked_minute("x ASKED:2026-01-01") == ""
    assert PR.asked_minute(None) == ""


# --------------------------------------------------------------------------- the shared tree-based reader


def test_read_renet_is_keyed_on_the_renet_tree(tmp_path, monkeypatch):
    tree = "a" * 40
    monkeypatch.setenv("RENET_TEST_RECEIPT_DIR", str(tmp_path))
    assert PR.read("renet", tmp_path, tree) is None
    doc = {"schema": 1, "renetTree": tree, "packages": ["pkg/license"]}
    (tmp_path / ("%s.json" % tree)).write_text(json.dumps(doc))
    assert PR.read("renet", tmp_path, tree) == doc
    # Control: a receipt filed under the tree but naming another is not this tree's.
    (tmp_path / ("%s.json" % tree)).write_text(json.dumps(dict(doc, renetTree="b" * 40)))
    assert PR.read("renet", tmp_path, tree) is None


def test_read_ci_quick_is_the_guards_own_reader(tmp_path):
    tree = "c" * 40
    assert PR.read("ci:quick", tmp_path, tree) is None
    archive = tmp_path / ".ci/cache/receipts"
    archive.mkdir(parents=True)
    (archive / ("%s.json" % tree)).write_text(
        json.dumps({"headTree": tree, "whole": True, "schema": 2})
    )
    assert PR.read("ci:quick", tmp_path, tree)["headTree"] == tree
    # Control: a per-tree copy naming another tree is MISFILED, never read past.
    (archive / ("%s.json" % tree)).write_text(json.dumps({"headTree": "d" * 40, "whole": True}))
    ci = importlib.import_module("rediacc_hooks.guards.block_unverified_push")
    assert ci.MISFILED in PR.read("ci:quick", tmp_path, tree)
