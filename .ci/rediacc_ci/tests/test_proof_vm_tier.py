"""`rediacc_ci.proof.vm_tier`: write, archive, read and the admit rule of the push guard, at schema 3.

Each case writes a real receipt file under a temporary root and judges it the way the guard does.
"""

from __future__ import annotations

import copy
import json
import os
from typing import TYPE_CHECKING, Any

import pytest

from rediacc_ci.proof import vm_tier as rc

if TYPE_CHECKING:
    import pathlib

TREE = "a" * 40
OTHER_TREE = "b" * 40
PTR = "c" * 40
DIGEST = "d" * 64
RENET = ("renet",)
ACCOUNT = ("account",)
BOTH = ("renet", "account")
APTR = "9" * 40


def make(**over: object) -> dict[str, Any]:
    base: dict[str, Any] = {
        "tier": "vm",
        "schema": 3,
        "status": rc.VERIFIED,
        "reason": None,
        "tree": TREE,
        "head": "e" * 40,
        "dirty": False,
        "inputs": DIGEST,
        "surfaces": ["cli-remote", "renet"],
        "submodules": {
            "private/renet": {"pointer": PTR, "checkout": PTR, "modified": False},
            "private/account": {"pointer": APTR, "checkout": APTR, "modified": False},
        },
        "renet": {"built": PTR, "modified": False, "sha256": "f" * 64, "deployed": PTR},
        "phases": {
            "renet": {"required": True, "ran": True},
            "account": {"required": False, "ran": False},
        },
        "gateway": {"mode": "reused", "port": 3000, "started": 1},
        "trigger": {"base": "origin/main", "via": "@{push}", "hits": ["x"], "sides": ["renet"]},
        "fleet": {"mode": "reused", "os": "ubuntu", "ips": ["1"], "landlock": {}},
        "forks": [],
        "steps": [
            {
                "id": "V1.2",
                "desc": "cross-repo",
                "rc": 0,
                "verdict": "ok",
                "ms": 5,
                "evidence": "ok",
            }
        ],
        "teardown": {"ok": True, "leftovers": []},
        "runId": "run-1",
        "startedAt": "2026-10-14T10:00:00Z",
        "finishedAt": "2026-10-14T10:01:00Z",
        "wallMs": 60000,
    }
    base.update(over)
    return base


def not_verified(**over: object) -> dict[str, Any]:
    return make(
        status=rc.NOT_VERIFIED,
        reason={"class": "fleet-unavailable", "detail": "ops up rc=1"},
        **over,
    )


# ------------------------------------------------------------------ write, archive, read


def test_write_creates_latest_and_the_tree_archive(tmp_path: pathlib.Path) -> None:
    out = rc.write(tmp_path, make())
    assert out == tmp_path / ".ci/cache/vm-check/receipt.json"
    assert json.loads(out.read_text())["tree"] == TREE
    assert rc.read_archive(tmp_path, TREE) == make()
    assert rc.read_latest(tmp_path) == make()


def test_a_later_run_on_another_tree_keeps_the_first_archive(tmp_path: pathlib.Path) -> None:
    rc.write(tmp_path, make())
    rc.write(tmp_path, not_verified(tree=OTHER_TREE))
    archived = rc.read_archive(tmp_path, TREE)
    latest = rc.read_latest(tmp_path)
    assert archived is not None
    assert latest is not None
    assert archived["status"] == rc.VERIFIED
    assert latest["status"] == rc.NOT_VERIFIED


def test_write_leaves_no_temp_files(tmp_path: pathlib.Path) -> None:
    rc.write(tmp_path, make())
    assert sorted(p.name for p in (tmp_path / ".ci/cache/vm-check").iterdir()) == [
        f"{TREE}.json",
        "receipt.json",
    ]


def test_write_refuses_a_malformed_receipt_and_writes_nothing(tmp_path: pathlib.Path) -> None:
    bad = make()
    del bad["inputs"]
    with pytest.raises(ValueError, match="missing field inputs"):
        rc.write(tmp_path, bad)
    assert not (tmp_path / ".ci/cache/vm-check").exists()


@pytest.mark.parametrize(
    "bad",
    [
        {"status": "PASSED"},
        {"schema": 1},
        {"schema": 2},
        {"schema": 4},
        {"tier": "live"},
        {"tier": None},
        {"dirty": "no"},
        {"inputs": "short"},
        {"surfaces": ["gpu"]},
        {"submodules": {}},
        {"submodules": {"private/renet": {"pointer": PTR}, "private/account": {}}},
        {"tree": "../../etc/passwd"},
        {"status": rc.NOT_VERIFIED, "reason": None},
        {"status": rc.FAILED, "reason": {"detail": "no class"}},
        {"reason": {"class": "x", "detail": "y"}},
        {"steps": "none"},
        {"steps": [{"id": "V1", "evidence": "x" * 201}]},
        {"renet": "abc"},
        {"renet": {"built": PTR}},
        {"trigger": ["x"]},
        {"fleet": "reused"},
        {"teardown": True},
        {"forks": {}},
        {"phases": "all"},
        {"gateway": "abc"},
        {"phases": {"renet": {"required": True, "ran": True}}},
        {
            "phases": {
                "renet": {"required": 1, "ran": True},
                "account": {"required": False, "ran": False},
            }
        },
        {
            "submodules": {
                "private/renet": {"pointer": PTR, "checkout": PTR, "modified": False},
                "private/account": {"pointer": APTR, "checkout": APTR, "modified": "no"},
            }
        },
        {"trigger": {"hits": [], "sides": ["gpu"]}},
        {"trigger": {"hits": []}},
    ],
)
def test_validate_rejects(bad: dict[str, Any]) -> None:
    assert rc.validate(make(**bad))


def test_a_receipt_whose_renet_is_a_string_is_refused_not_a_crash(tmp_path: pathlib.Path) -> None:
    folder = tmp_path / rc.CACHE_DIR
    folder.mkdir(parents=True)
    (folder / rc.LATEST).write_text(json.dumps(make(renet="abc")), encoding="utf-8")
    assert rc.read_latest(tmp_path) is None
    assert not rc.admit(tmp_path, TREE, DIGEST, RENET).ok


def test_validate_accepts_a_good_receipt_of_each_status() -> None:
    assert rc.validate(make()) == []
    assert rc.validate(not_verified()) == []
    assert rc.validate(make(status=rc.FAILED, reason={"class": "step", "detail": "V1.2"})) == []
    assert rc.validate("text") == ["receipt is not an object"]


def test_clip_evidence_cuts_on_a_character_boundary() -> None:
    assert rc.clip_evidence("short") == "short"
    clipped = rc.clip_evidence("é" * 150)
    assert len(clipped.encode()) <= rc.EVIDENCE_MAX
    assert clipped == "é" * 100


def test_unreadable_files_read_as_absent(tmp_path: pathlib.Path) -> None:
    folder = tmp_path / ".ci/cache/vm-check"
    folder.mkdir(parents=True)
    (folder / "receipt.json").write_text("{not json")
    (folder / f"{TREE}.json").write_text(json.dumps({"schema": 3}))
    assert rc.read_latest(tmp_path) is None
    assert rc.read_archive(tmp_path, TREE) is None
    assert rc.read_archive(tmp_path, "../x") is None


# ------------------------------------------------------------------ admit


def test_no_receipt_refuses(tmp_path: pathlib.Path) -> None:
    got = rc.admit(tmp_path, TREE, DIGEST, RENET)
    assert (got.ok, got.code) == (False, "no-receipt")


def test_tree_match_admits(tmp_path: pathlib.Path) -> None:
    rc.write(tmp_path, make(inputs="0" * 64))
    got = rc.admit(tmp_path, TREE, DIGEST, RENET)
    assert (got.ok, got.code) == (True, "ok")


def test_inputs_match_admits_another_tree(tmp_path: pathlib.Path) -> None:
    rc.write(tmp_path, make())
    got = rc.admit(tmp_path, OTHER_TREE, DIGEST, RENET)
    assert (got.ok, got.code) == (True, "ok")


def test_other_inputs_refuse_and_say_so(tmp_path: pathlib.Path) -> None:
    rc.write(tmp_path, make())
    got = rc.admit(tmp_path, OTHER_TREE, "9" * 64, RENET)
    assert (got.ok, got.code) == (False, "other-inputs")
    assert "other trigger inputs" in got.message


def test_unknown_digest_never_matches_by_inputs(tmp_path: pathlib.Path) -> None:
    rc.write(tmp_path, make())
    assert rc.admit(tmp_path, OTHER_TREE, None, RENET).code == "other-inputs"


def test_a_modified_build_refuses(tmp_path: pathlib.Path) -> None:
    receipt = make()
    receipt["renet"]["modified"] = True
    rc.write(tmp_path, receipt)
    got = rc.admit(tmp_path, TREE, DIGEST, RENET)
    assert (got.ok, got.code) == (False, "modified-build")
    assert rc.admit(tmp_path, TREE, DIGEST, ACCOUNT).code == "phase-missing"


def test_a_build_that_is_not_the_pointer_refuses(tmp_path: pathlib.Path) -> None:
    receipt = make()
    receipt["renet"]["built"] = "f" * 40
    rc.write(tmp_path, receipt)
    got = rc.admit(tmp_path, TREE, DIGEST, RENET)
    assert (got.ok, got.code) == (False, "build-mismatch")


def test_an_unknown_modified_flag_is_not_clean(tmp_path: pathlib.Path) -> None:
    receipt = make()
    receipt["renet"]["modified"] = None
    rc.write(tmp_path, receipt)
    assert rc.admit(tmp_path, TREE, DIGEST, RENET).code == "modified-build"


def test_not_verified_refuses_with_class_and_detail(tmp_path: pathlib.Path) -> None:
    rc.write(tmp_path, not_verified())
    got = rc.admit(tmp_path, TREE, DIGEST, RENET)
    assert (got.ok, got.code) == (False, "not-verified")
    assert "fleet-unavailable" in got.message
    assert "ops up rc=1" in got.message


def test_failed_names_the_failed_step_and_its_evidence(tmp_path: pathlib.Path) -> None:
    steps = [
        {"id": "V1.1", "desc": "forks", "rc": 0, "verdict": "ok", "ms": 1, "evidence": "fine"},
        {
            "id": "V1.2",
            "desc": "cross-repo chmod",
            "rc": 0,
            "verdict": "FAIL",
            "ms": 1,
            "evidence": "chmod succeeded",
        },
    ]
    rc.write(
        tmp_path,
        make(status=rc.FAILED, reason={"class": "step-failed", "detail": "V1.2"}, steps=steps),
    )
    got = rc.admit(tmp_path, TREE, DIGEST, RENET)
    assert (got.ok, got.code) == (False, "failed")
    assert "V1.2" in got.message
    assert "chmod succeeded" in got.message


def test_a_non_verified_status_never_admits_even_with_matching_keys(tmp_path: pathlib.Path) -> None:
    for status, reason in (
        (rc.FAILED, {"class": "step-failed", "detail": "d"}),
        (rc.NOT_VERIFIED, {"class": "interrupted", "detail": "d"}),
    ):
        rc.write(tmp_path, make(status=status, reason=reason))
        assert rc.admit(tmp_path, TREE, DIGEST, RENET).ok is False


def test_the_trees_own_archive_outranks_the_latest_receipt(tmp_path: pathlib.Path) -> None:
    rc.write(tmp_path, not_verified())
    rc.write(tmp_path, make(tree=OTHER_TREE, inputs="9" * 64))
    got = rc.admit(tmp_path, TREE, DIGEST, RENET)
    assert (got.ok, got.code) == (False, "not-verified")


def test_an_older_verified_archive_with_the_same_inputs_admits_after_a_failed_latest(
    tmp_path: pathlib.Path,
) -> None:
    rc.write(tmp_path, make())
    rc.write(tmp_path, not_verified(tree=OTHER_TREE, inputs="9" * 64))
    got = rc.admit(tmp_path, "1" * 40, DIGEST, RENET)
    assert (got.ok, got.code) == (True, "ok")


def test_archive_scan_is_bounded(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    folder = tmp_path / ".ci/cache/vm-check"
    rc.write(tmp_path, make(tree="2" * 40, inputs="8" * 64))
    template = json.dumps(make(inputs="8" * 64))
    for i in range(rc.ARCHIVE_SCAN_MAX + 5):
        path = folder / f"{i:040x}.json"
        path.write_text(template.replace(TREE, f"{i:040x}"))
        os.utime(path, (1000 + i, 1000 + i))
    old = folder / f"{TREE}.json"
    old.write_text(json.dumps(make()))
    os.utime(old, (1, 1))
    assert rc.admit(tmp_path, "3" * 40, DIGEST, RENET).code != "ok"
    monkeypatch.setattr(rc, "ARCHIVE_SCAN_MAX", 500)
    assert rc.admit(tmp_path, "3" * 40, DIGEST, RENET).code == "ok"


def test_verdict_carries_the_receipt(tmp_path: pathlib.Path) -> None:
    rc.write(tmp_path, make())
    got = rc.admit(tmp_path, TREE, DIGEST, RENET)
    assert got.receipt == make()
    assert copy.deepcopy(got.receipt)["runId"] == "run-1"


# ------------------------------------------------------------------ schema 3 and the phases


def phases(renet: tuple[bool, bool], account: tuple[bool, bool]) -> dict[str, Any]:
    return {
        "renet": {"required": renet[0], "ran": renet[1]},
        "account": {"required": account[0], "ran": account[1]},
    }


def account_receipt(**account: object) -> dict[str, Any]:
    receipt = make(phases=phases((False, False), (True, True)), surfaces=["account"])
    receipt["submodules"]["private/account"].update(account)
    receipt["trigger"]["sides"] = ["account"]
    return receipt


def write_raw(root: pathlib.Path, name: str, receipt: dict[str, Any]) -> None:
    folder = root / rc.CACHE_DIR
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_text(json.dumps(receipt), encoding="utf-8")


def test_schema_is_three_and_the_tier_is_vm() -> None:
    assert rc.SCHEMA == 3
    assert rc.TIER == "vm"
    assert make()["tier"] == "vm"


def test_a_schema_1_file_is_ignored_and_admit_reports_no_receipt(tmp_path: pathlib.Path) -> None:
    old = make(schema=1)
    write_raw(tmp_path, rc.LATEST, old)
    write_raw(tmp_path, f"{TREE}.json", old)
    assert rc.read_latest(tmp_path) is None
    assert rc.read_archive(tmp_path, TREE) is None
    got = rc.admit(tmp_path, TREE, DIGEST, RENET)
    assert (got.ok, got.code) == (False, "no-receipt")


def test_an_old_not_verified_receipt_cannot_back_an_escape(tmp_path: pathlib.Path) -> None:
    write_raw(tmp_path, rc.LATEST, not_verified(schema=1))
    assert rc.read_latest(tmp_path) is None


def test_a_schema_2_file_is_ignored_and_admit_reports_no_receipt(tmp_path: pathlib.Path) -> None:
    """A schema 2 receipt (no envelope, top-level account block) neither admits nor backs an escape."""
    old = make(schema=2)
    for key in ("tier", "dirty", "surfaces", "submodules", "gateway"):
        del old[key]
    old["account"] = {"pointer": APTR, "checkout": APTR, "modified": False, "gateway": {}}
    write_raw(tmp_path, rc.LATEST, old)
    write_raw(tmp_path, f"{TREE}.json", old)
    assert rc.read_latest(tmp_path) is None
    assert rc.read_archive(tmp_path, TREE) is None
    assert rc.admit(tmp_path, TREE, DIGEST, RENET).code == "no-receipt"
    write_raw(tmp_path, rc.LATEST, make(schema=2))
    assert rc.read_latest(tmp_path) is None


@pytest.mark.parametrize("schema", [1, 2])
def test_write_refuses_a_retired_schema(tmp_path: pathlib.Path, schema: int) -> None:
    with pytest.raises(ValueError, match=f"schema is {schema}"):
        rc.write(tmp_path, make(schema=schema))


def test_a_renet_only_receipt_is_refused_phase_missing_for_account(tmp_path: pathlib.Path) -> None:
    rc.write(tmp_path, make())
    got = rc.admit(tmp_path, TREE, DIGEST, ACCOUNT)
    assert (got.ok, got.code) == (False, "phase-missing")
    assert "account" in got.message
    assert "npm run vm:check -- --changed" in got.message


def test_a_renet_only_receipt_is_admitted_for_renet(tmp_path: pathlib.Path) -> None:
    rc.write(tmp_path, make())
    assert rc.admit(tmp_path, TREE, DIGEST, RENET).ok


def test_a_renet_only_receipt_is_refused_when_the_push_touches_both(tmp_path: pathlib.Path) -> None:
    rc.write(tmp_path, make())
    assert rc.admit(tmp_path, TREE, DIGEST, BOTH).code == "phase-missing"


def test_an_account_receipt_admits_account_and_refuses_renet(tmp_path: pathlib.Path) -> None:
    rc.write(tmp_path, account_receipt())
    assert rc.admit(tmp_path, TREE, DIGEST, ACCOUNT).ok
    got = rc.admit(tmp_path, TREE, DIGEST, RENET)
    assert (got.ok, got.code) == (False, "phase-missing")
    assert "renet" in got.message


def test_a_full_receipt_admits_every_side(tmp_path: pathlib.Path) -> None:
    rc.write(tmp_path, make(phases=phases((True, True), (True, True))))
    for sides in (RENET, ACCOUNT, BOTH):
        assert rc.admit(tmp_path, TREE, DIGEST, sides).ok


def test_an_account_checkout_that_is_not_the_pointer_refuses(tmp_path: pathlib.Path) -> None:
    rc.write(tmp_path, account_receipt(checkout="f" * 40))
    got = rc.admit(tmp_path, TREE, DIGEST, ACCOUNT)
    assert (got.ok, got.code) == (False, "checkout-mismatch")
    assert "private/account" in got.message


def test_a_null_account_pointer_is_a_mismatch_even_when_the_checkout_is_null(
    tmp_path: pathlib.Path,
) -> None:
    rc.write(tmp_path, account_receipt(pointer=None, checkout=None))
    assert rc.admit(tmp_path, TREE, DIGEST, ACCOUNT).code == "checkout-mismatch"


def test_a_modified_account_checkout_refuses(tmp_path: pathlib.Path) -> None:
    rc.write(tmp_path, account_receipt(modified=True))
    got = rc.admit(tmp_path, TREE, DIGEST, ACCOUNT)
    assert (got.ok, got.code) == (False, "modified-checkout")


def test_an_unknown_account_modified_flag_is_not_clean(tmp_path: pathlib.Path) -> None:
    rc.write(tmp_path, account_receipt(modified=None))
    assert rc.admit(tmp_path, TREE, DIGEST, ACCOUNT).code == "modified-checkout"


def test_account_state_is_not_judged_when_the_push_has_no_account_side(
    tmp_path: pathlib.Path,
) -> None:
    receipt = make()
    receipt["submodules"]["private/account"].update(checkout="f" * 40, modified=True)
    rc.write(tmp_path, receipt)
    assert rc.admit(tmp_path, TREE, DIGEST, RENET).ok


def test_renet_state_is_not_judged_when_the_push_has_no_renet_side(tmp_path: pathlib.Path) -> None:
    """The account surface needs no renet build, so a renet checkout or build off its pointer does not refuse an account push."""
    receipt = account_receipt()
    receipt["renet"]["built"] = "f" * 40
    receipt["submodules"]["private/renet"]["modified"] = True
    rc.write(tmp_path, receipt)
    assert rc.admit(tmp_path, TREE, DIGEST, ACCOUNT).ok


def test_the_phase_rule_comes_before_the_identity_rules(tmp_path: pathlib.Path) -> None:
    receipt = make()
    receipt["renet"]["built"] = "f" * 40
    rc.write(tmp_path, receipt)
    assert rc.admit(tmp_path, TREE, DIGEST, ACCOUNT).code == "phase-missing"
    assert rc.admit(tmp_path, TREE, DIGEST, RENET).code == "build-mismatch"


def test_a_dirty_console_tree_refuses(tmp_path: pathlib.Path) -> None:
    rc.write(tmp_path, make(dirty=True))
    assert rc.admit(tmp_path, TREE, DIGEST, RENET).code == "dirty-tree"
    rc.write(tmp_path, make(dirty=None))
    assert rc.admit(tmp_path, TREE, DIGEST, RENET).code == "dirty-tree"


def test_a_renet_checkout_that_is_not_the_pointer_or_is_modified_refuses(
    tmp_path: pathlib.Path,
) -> None:
    receipt = make()
    receipt["submodules"]["private/renet"]["checkout"] = "f" * 40
    rc.write(tmp_path, receipt)
    assert rc.admit(tmp_path, TREE, DIGEST, RENET).code == "checkout-mismatch"
    receipt = make()
    receipt["submodules"]["private/renet"]["modified"] = None
    rc.write(tmp_path, receipt)
    assert rc.admit(tmp_path, TREE, DIGEST, RENET).code == "modified-checkout"


def test_validate_rejects_a_verified_receipt_whose_required_phase_did_not_run(
    tmp_path: pathlib.Path,
) -> None:
    bad = make(phases=phases((True, True), (True, False)))
    assert any("account" in e and "required" in e for e in rc.validate(bad))
    with pytest.raises(ValueError, match="required phase account"):
        rc.write(tmp_path, bad)
    assert not (tmp_path / rc.CACHE_DIR).exists()


def test_validate_rejects_a_verified_receipt_where_no_phase_ran() -> None:
    bad = make(phases=phases((False, False), (False, False)))
    assert any("at least one phase" in e for e in rc.validate(bad))


def test_a_not_verified_receipt_may_leave_a_required_phase_unrun() -> None:
    assert rc.validate(not_verified(phases=phases((True, False), (True, False)))) == []
    failed = make(
        status=rc.FAILED,
        reason={"class": "step-failed", "detail": "A1.1"},
        phases=phases((False, False), (True, False)),
    )
    assert rc.validate(failed) == []


def test_a_phase_that_ran_without_being_required_is_valid() -> None:
    assert rc.validate(make(phases=phases((False, True), (False, False)))) == []


# --------------------------------------------------------------------------- the evidence fields


def test_the_evidence_fields_are_optional_and_accepted_when_well_formed() -> None:
    good = make(runDir=".ci/cache/vm-check/runs/vmc-1")
    good["steps"] = [
        {
            "id": "A2.3",
            "desc": "drill license",
            "rc": 1,
            "verdict": "ok",
            "ms": 1,
            "evidence": "",
            "log": ".ci/cache/vm-check/runs/vmc-1/A2.3-license.log",
            "failedAssertions": ["02 the machine can reach that URL"],
        }
    ]
    assert rc.validate(good) == []
    assert rc.validate(make(runDir=None)) == []
    assert rc.validate(make()) == []


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("log", 3, "log is not a string"),
        ("failedAssertions", "02 x", "failedAssertions is not a list of strings"),
        ("failedAssertions", [2], "failedAssertions is not a list of strings"),
    ],
)
def test_a_malformed_evidence_field_is_refused(field: str, value: object, message: str) -> None:
    bad = make()
    bad["steps"] = [{"id": "A2.3", "evidence": "", field: value}]
    assert any(message in e for e in rc.validate(bad)), rc.validate(bad)


def test_a_non_string_run_dir_is_refused() -> None:
    assert "runDir is not a string or null" in rc.validate(make(runDir=7))


def test_receipt_files_names_only_receipts(tmp_path: pathlib.Path) -> None:
    """Review 2fa7d53d.1: A0's gateway.json sat beside the receipts and was counted as one."""
    folder = rc.receipt_dir(tmp_path)
    folder.mkdir(parents=True)
    for name in (rc.LATEST, TREE + ".json", "gateway.json", "gateway.log", "notes.json"):
        (folder / name).write_text("{}")
    (folder / "runs").mkdir()
    assert [p.name for p in rc.receipt_files(tmp_path)] == sorted([TREE + ".json", rc.LATEST])
    assert rc.receipt_files(tmp_path / "absent") == []


# ------------------------------------------------------------------ a run that lost the fleet lock


def busy(**over: object) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "status": rc.NOT_VERIFIED,
        "reason": {"class": "fleet-busy", "detail": "another vm:check holds the lock"},
        "runId": "vmc-10201456-eec456",
    }
    fields.update(over)
    return make(**fields)


def test_a_lock_losers_record_leaves_the_receipts_byte_identical(tmp_path: pathlib.Path) -> None:
    rc.write(tmp_path, make())
    before = {p.name: p.read_bytes() for p in rc.receipt_files(tmp_path)}
    assert sorted(before) == sorted([rc.LATEST, f"{TREE}.json"])
    out = rc.write_run_record(tmp_path, busy())
    assert out == tmp_path / ".ci/cache/vm-check/runs/vmc-10201456-eec456/receipt.json"
    assert json.loads(out.read_text()) == busy()
    assert {p.name: p.read_bytes() for p in rc.receipt_files(tmp_path)} == before


def test_the_guard_never_reads_a_lock_losers_record(tmp_path: pathlib.Path) -> None:
    rc.write(tmp_path, make())
    rc.write_run_record(tmp_path, busy())
    got = rc.admit(tmp_path, TREE, DIGEST, RENET)
    assert (got.ok, got.code) == (True, "ok")
    # Alone, the record is no receipt at all: neither an admission nor a refusal source.
    alone = tmp_path / "alone"
    rc.write_run_record(alone, busy())
    assert rc.admit(alone, TREE, DIGEST, RENET).code == "no-receipt"
    assert rc.read_latest(alone) is None
    assert rc.read_archive(alone, TREE) is None


@pytest.mark.parametrize("run_id", ["", ".", "..", "../x", "a/b", "run 1", "vmc-1-ab\n"])
def test_write_run_record_refuses_a_run_id_that_is_no_directory_name(
    tmp_path: pathlib.Path, run_id: str
) -> None:
    with pytest.raises(ValueError, match="runId"):
        rc.write_run_record(tmp_path, busy(runId=run_id))
    assert not rc.receipt_dir(tmp_path).exists()


def test_write_run_record_refuses_a_malformed_record(tmp_path: pathlib.Path) -> None:
    bad = busy()
    del bad["inputs"]
    with pytest.raises(ValueError, match="missing field inputs"):
        rc.write_run_record(tmp_path, bad)
    assert not rc.receipt_dir(tmp_path).exists()
