"""The narrow red waiver of the release's ci-quick gate (`RELEASE_RED_WAIVER`, operator ruling 2026-11-16 "Narrow release escape").

A production break `check:ci-ops-health` reports stays red until the fix is deployed, and the fix is deployed only by the release the red receipt refuses; an upstream outage blocks the same way. The waiver admits a receipt for the exact HEAD tree whose every red gate is named in it and is on the fixed allowlist: `check:ci-ops-health` by name, or a gate whose re-run at release time prints the upstream marker. Everything else refuses as before.

The receipt worlds are the push guard's own builder (`_repo_with_receipt`), so the receipt shapes judged here are the ones its goldens freeze. The ASKED proof and the gate re-run are injected; the live re-run is driven once against a real `npm run`.
"""

from __future__ import annotations

import json
import os
import subprocess
from typing import TYPE_CHECKING, Any

import pytest

from rediacc_ci.release import local
from rediacc_ci.release import local_gates as lg

if TYPE_CHECKING:
    import pathlib

GUARD = lg._push_guard()
OPS = "check:ci-ops-health"
EMBED = "check:ci-embed-asset-freshness"
ASK = "ASKED:2026-11-16T11:35Z"
REASON = "account-eu HTTP 500 breaks the hostinger backup; this release deploys the fix"
UPSTREAM_OUT = (
    "? rsync: attempt 1 of 3 failed (timeout after 15 s), asking again in 2 s\n"
    "  UPSTREAM REACHABILITY FAILURE (download.samba.org), not a stale pin and not a defect in the tree.\n"
)


def _env() -> dict[str, str]:
    return dict(
        os.environ,
        GIT_AUTHOR_NAME="Fixture",
        GIT_AUTHOR_EMAIL="fixture@example.invalid",
        GIT_COMMITTER_NAME="Fixture",
        GIT_COMMITTER_EMAIL="fixture@example.invalid",
        GIT_CONFIG_NOSYSTEM="1",
    )


@pytest.fixture(autouse=True)
def isolated_git(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = tmp_path / "gitconfig"
    config.write_text("[init]\n\tdefaultBranch = main\n", encoding="utf-8")
    for key, value in _env().items():
        if key.startswith("GIT_"):
            monkeypatch.setenv(key, value)
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(config))
    monkeypatch.delenv(lg.WAIVER_ENV, raising=False)


def tree_of(repo: pathlib.Path) -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD^{tree}"],
        cwd=str(repo),
        capture_output=True,
        text=True,
        check=True,
        env=_env(),
    ).stdout.strip()


def red_world(tmp_path: pathlib.Path, failed: list[str], **over: Any) -> pathlib.Path:
    receipt: dict[str, Any] = {
        "whole": True,
        "exitCode": 1 if failed else 0,
        "failed": failed,
        "droppedTouched": [],
    }
    receipt.update(over)
    return GUARD._repo_with_receipt(tmp_path / "world", receipt)


def proven(_asked: str) -> bool:
    return True


def unproven(_asked: str) -> bool:
    return False


class Rerun:
    """A gate re-run that answers `(rc, out)` and records which gates it was asked for."""

    def __init__(self, rc: int | None = None, out: str = "", *, forbidden: bool = False) -> None:
        self.rc = rc
        self.out = out
        self.forbidden = forbidden
        self.calls: list[str] = []

    def __call__(self, _root: pathlib.Path, gate: str) -> tuple[int | None, str]:
        assert not self.forbidden, "no gate re-run was expected, got one for %s" % gate
        self.calls.append(gate)
        return self.rc, self.out


def verdict(
    root: pathlib.Path,
    waiver: str | None,
    asked_proof: lg.AskedProof = proven,
    rerun: lg.GateRerun | None = None,
) -> tuple[lg.Refusal | None, lg.WaiverAdmission | None]:
    return lg.ci_quick_verdict(
        root,
        tree_of(root),
        waiver_text=waiver,
        asked_proof=asked_proof,
        rerun=rerun or Rerun(forbidden=True),
    )


# --------------------------------------------------------------------------- the waiver's form


def test_the_waiver_parses_gates_asked_and_reason() -> None:
    waiver, why = lg.parse_red_waiver("%s,%s %s %s" % (OPS, EMBED, ASK, REASON))
    assert why == ""
    assert waiver == lg.RedWaiver(gates=(OPS, EMBED), asked=ASK, reason=REASON)


@pytest.mark.parametrize(
    "text",
    [
        "",
        OPS,
        "%s %s" % (OPS, ASK),
        "%s %s" % (OPS, REASON),
        "%s ASKED:2026-11-16T11:3xZ %s" % (OPS, REASON),
        "%s ASKED:2026-11-16 %s" % (OPS, REASON),
        ",%s %s %s" % (OPS, ASK, REASON),
        "%s,%s %s %s" % (OPS, OPS, ASK, REASON),
        "%s %s    " % (OPS, ASK),
    ],
)
def test_a_malformed_waiver_does_not_parse(text: str) -> None:
    waiver, why = lg.parse_red_waiver(text)
    assert waiver is None
    assert why


# --------------------------------------------------------------------------- admitted


def test_only_ops_health_red_with_a_proven_waiver_admits(tmp_path: pathlib.Path) -> None:
    root = red_world(tmp_path, [OPS])
    refusal, admission = verdict(root, "%s %s %s" % (OPS, ASK, REASON))
    assert refusal is None
    assert admission is not None
    assert admission.gates == (OPS,)
    assert admission.asked == ASK
    assert admission.reason == REASON
    assert admission.tree == tree_of(root)
    assert "allowlisted by name" in admission.evidence[OPS]
    assert admission.warnings == ()


def test_an_upstream_outage_with_the_marker_on_re_run_admits(tmp_path: pathlib.Path) -> None:
    root = red_world(tmp_path, [OPS, EMBED])
    rerun = Rerun(1, UPSTREAM_OUT)
    refusal, admission = verdict(root, "%s,%s %s %s" % (OPS, EMBED, ASK, REASON), rerun=rerun)
    assert refusal is None
    assert admission is not None
    assert admission.gates == (OPS, EMBED)
    assert lg.UPSTREAM_MARKER in admission.evidence[EMBED]
    # ops-health is allowlisted by name and never re-run; the marker gate is re-run once.
    assert rerun.calls == [EMBED]


def test_a_named_gate_that_is_not_red_admits_with_a_warning(tmp_path: pathlib.Path) -> None:
    root = red_world(tmp_path, [OPS])
    refusal, admission = verdict(root, "%s,%s %s %s" % (OPS, EMBED, ASK, REASON))
    assert refusal is None
    assert admission is not None
    assert admission.gates == (OPS,)
    assert any(EMBED in w and "not red" in w for w in admission.warnings)


def test_a_green_receipt_admits_and_applies_no_waiver(tmp_path: pathlib.Path) -> None:
    root = red_world(tmp_path, [])
    refusal, admission = verdict(root, "%s %s %s" % (OPS, ASK, REASON), asked_proof=unproven)
    assert refusal is None
    assert admission is None


# --------------------------------------------------------------------------- refused


def test_no_waiver_refuses_as_today(tmp_path: pathlib.Path) -> None:
    root = red_world(tmp_path, [OPS])
    refusal, admission = verdict(root, None)
    today = lg.ci_quick_refusal(root, tree_of(root))
    assert admission is None
    assert refusal is not None
    assert today is not None
    assert refusal.code == "ci-quick"
    assert OPS in refusal.message
    assert refusal.message == today.message


def test_an_extra_non_allowlisted_red_refuses(tmp_path: pathlib.Path) -> None:
    root = red_world(tmp_path, [OPS, "check:format"])
    refusal, admission = verdict(root, "%s %s %s" % (OPS, ASK, REASON))
    assert admission is None
    assert refusal is not None
    assert "check:format" in refusal.message


def test_naming_a_non_allowlisted_red_still_refuses(tmp_path: pathlib.Path) -> None:
    root = red_world(tmp_path, [OPS, "check:format"])
    rerun = Rerun(1, "src/a.ts: not formatted\n")
    refusal, admission = verdict(root, "%s,check:format %s %s" % (OPS, ASK, REASON), rerun=rerun)
    assert admission is None
    assert refusal is not None
    assert "check:format" in refusal.message
    assert lg.UPSTREAM_MARKER in refusal.message


def test_a_receipt_for_a_different_tree_refuses(tmp_path: pathlib.Path) -> None:
    root = red_world(tmp_path, [OPS], headTree="0" * 40)
    refusal, admission = verdict(root, "%s %s %s" % (OPS, ASK, REASON))
    assert admission is None
    assert refusal is not None
    assert "different tree" in refusal.message


READER = "check:fixture-reader"


def advanced_world(
    tmp_path: pathlib.Path,
    failed: list[str],
    *,
    readers: tuple[str, ...] = (READER,),
    touch: str = "agent/reviews/main/clean.jsonl",
) -> pathlib.Path:
    """A receipt for the parent tree, then one commit its `advances` step carries to HEAD. `readers` are the gates the record policy names for agent/reviews/** and the step lists at exit 0; `touch` is the path the commit writes, a record by default."""
    root = tmp_path / "advanced"
    root.mkdir(parents=True)

    def git(*args: str) -> str:
        return subprocess.run(
            ["git", *args], cwd=str(root), capture_output=True, text=True, check=True, env=_env()
        ).stdout.strip()

    git("init", "--initial-branch=main", "-q")
    policy = root / GUARD.RECORD_POLICY_REL
    policy.parent.mkdir(parents=True)
    listed = [{"id": gate, "evidence": "fixture:1"} for gate in readers]
    policy.write_text(
        json.dumps(
            {
                "version": GUARD.RECORD_POLICY_VERSION,
                "records": [{"glob": "agent/reviews/**", "except": [], "readers": listed}],
            }
        ),
        encoding="utf-8",
    )
    (root / "seed.txt").write_text("seed\n", encoding="utf-8")
    GUARD._write_fixture_lock(root)
    git("add", "-A")
    git("commit", "-q", "-m", "seed")
    base = git("rev-parse", "HEAD^{tree}")
    record = root / touch
    record.parent.mkdir(parents=True, exist_ok=True)
    record.write_text("{}\n", encoding="utf-8")
    git("add", "-A")
    git("commit", "-q", "-m", "the commit the step claims is record-only")
    head = git("rev-parse", "HEAD^{tree}")
    advance = {
        "from": base,
        "to": head,
        # What a runner would have written; the guard recomputes the diff and never reads this.
        "paths": ["agent/reviews/main/clean.jsonl"],
        "gates": dict.fromkeys(readers, 0),
        "finishedAt": "2026-11-16T00:00:00Z",
    }
    body = GUARD._v2_body(
        {
            "headTree": base,
            "whole": True,
            "exitCode": 1 if failed else 0,
            "failed": failed,
            "droppedTouched": [],
            "advances": [advance],
        }
    )
    cache = root / ".ci" / "cache"
    cache.mkdir(parents=True)
    (cache / "prepush-receipt.json").write_text(json.dumps(body), encoding="utf-8")
    return root


def test_a_red_receipt_advanced_to_head_by_a_record_commit_is_waived(
    tmp_path: pathlib.Path,
) -> None:
    """Operator ruling 2026-11-16 (plans as records): a record-only commit after the red run no longer costs the waiver a whole lane. The chain is the push guard's own (`advance_chain`), and the admission names HEAD's tree, the one being released."""
    # CONTROL: the green twin is admitted through the same advance with no waiver, so the chain itself is sound.
    green = advanced_world(tmp_path / "green", [])
    assert lg.ci_quick_refusal(green, tree_of(green)) is None
    root = advanced_world(tmp_path / "red", [OPS])
    # CONTROL: with no waiver the red is refused as today, so the admission below is the waiver's.
    assert lg.ci_quick_refusal(root, tree_of(root)) is not None
    refusal, admission = verdict(root, "%s %s %s" % (OPS, ASK, REASON))
    assert refusal is None, refusal
    assert admission is not None
    assert admission.gates == (OPS,)
    assert admission.tree == tree_of(root)


def test_an_advance_that_lists_a_waived_gate_as_a_reader_refuses(tmp_path: pathlib.Path) -> None:
    """The step touched a record the waived gate reads, so the red judged at the receipt's tree says nothing about HEAD. The guard admits the step (the reader passed there); the waiver does not."""
    root = advanced_world(tmp_path, [OPS], readers=(READER, OPS))
    # CONTROL: the same world with the waived gate not a reader is admitted (the test above), and the guard's own chain reaches HEAD here, so the refusal is this rule and not a broken chain.
    receipt = GUARD.read_receipt(str(root), tree_of(root))
    chain, why = GUARD.advance_chain(str(root), receipt, receipt["headTree"], tree_of(root))
    assert chain is not None, why
    refusal, admission = verdict(root, "%s %s %s" % (OPS, ASK, REASON))
    assert admission is None
    assert refusal is not None
    assert OPS in refusal.message
    assert "record-only advance" in refusal.message


def test_a_code_path_in_the_advanced_range_refuses(tmp_path: pathlib.Path) -> None:
    """A step whose commit touched code is no advance, whatever its `paths` claim: the guard recomputes the diff, the chain does not reach HEAD, and the waiver has no tree to speak for."""
    root = advanced_world(tmp_path, [OPS], touch="src/code.py")
    refusal, admission = verdict(root, "%s %s %s" % (OPS, ASK, REASON))
    assert admission is None
    assert refusal is not None
    assert "no verified advance chain" in refusal.message


def test_no_receipt_refuses(tmp_path: pathlib.Path) -> None:
    root = GUARD._repo_with_receipt(tmp_path / "world", None)
    refusal, admission = verdict(root, "%s %s %s" % (OPS, ASK, REASON))
    assert admission is None
    assert refusal is not None
    assert GUARD.NO_RECEIPT in refusal.message


def test_a_narrowed_red_receipt_refuses(tmp_path: pathlib.Path) -> None:
    root = red_world(tmp_path, [OPS], whole=False)
    refusal, admission = verdict(root, "%s %s %s" % (OPS, ASK, REASON))
    assert admission is None
    assert refusal is not None
    assert "NARROWED" in refusal.message


def test_a_malformed_waiver_refuses(tmp_path: pathlib.Path) -> None:
    root = red_world(tmp_path, [OPS])
    refusal, admission = verdict(root, "%s %s" % (OPS, REASON))
    assert admission is None
    assert refusal is not None
    assert lg.WAIVER_ENV in refusal.message


def test_an_unproven_asked_refuses(tmp_path: pathlib.Path) -> None:
    root = red_world(tmp_path, [OPS])
    refusal, admission = verdict(root, "%s %s %s" % (OPS, ASK, REASON), asked_proof=unproven)
    assert admission is None
    assert refusal is not None
    assert "AskUserQuestion" in refusal.message


@pytest.mark.parametrize(
    ("rc", "out", "said"),
    [
        (1, "error: the pin is stale\n", lg.UPSTREAM_MARKER),
        (0, "all pins fresh\n", "passed on re-run"),
        (None, "npm is not on PATH", "could not be re-run"),
    ],
)
def test_a_marker_gate_without_the_marker_refuses(
    tmp_path: pathlib.Path, rc: int | None, out: str, said: str
) -> None:
    root = red_world(tmp_path, [EMBED])
    refusal, admission = verdict(root, "%s %s %s" % (EMBED, ASK, REASON), rerun=Rerun(rc, out))
    assert admission is None
    assert refusal is not None
    assert said in refusal.message


def test_a_marker_gate_that_passes_on_re_run_refuses_even_printing_the_marker(
    tmp_path: pathlib.Path,
) -> None:
    """Review ee12d7ab.2: rc 0 means the red is stale whatever the output says; control: rc 1 with the marker admits (test above)."""
    root = red_world(tmp_path, [EMBED])
    refusal, admission = verdict(
        root, "%s %s %s" % (EMBED, ASK, REASON), rerun=Rerun(0, UPSTREAM_OUT)
    )
    assert admission is None
    assert refusal is not None
    assert "passed on re-run" in refusal.message


@pytest.mark.parametrize("failed", [[OPS, 7], [OPS, None], "ops-health"])
def test_a_receipt_failed_list_with_a_non_string_entry_refuses(
    tmp_path: pathlib.Path, failed: Any
) -> None:
    """Review ee12d7ab.3: an entry no gate name can answer is refused, not dropped before the verdict; control: the same receipt with only the named gate admits."""
    root = red_world(tmp_path, failed)
    refusal, admission = verdict(root, "%s %s %s" % (OPS, ASK, REASON))
    assert admission is None
    assert refusal is not None
    assert "failed" in refusal.message
    control = red_world(tmp_path / "control", [OPS])
    refusal, admission = verdict(control, "%s %s %s" % (OPS, ASK, REASON))
    assert refusal is None
    assert admission is not None


@pytest.mark.parametrize("failed", ["", 0, {}, False, None])
def test_a_falsy_non_list_failed_field_refuses_not_an_empty_list(
    tmp_path: pathlib.Path, failed: Any
) -> None:
    """Review 950cf891.1/.2: a falsy value that is not a list ("", 0, {}, false, null) is refused as 'not a list', never read as an empty failed list (the receipt consistency check, block_unverified_push.py `failed` list test, refuses it before the waiver)."""
    root = red_world(tmp_path, failed)
    refusal, admission = verdict(root, "%s %s %s" % (OPS, ASK, REASON))
    assert admission is None
    assert refusal is not None
    assert "`failed` list" in refusal.message or "failed field is not a list" in refusal.message


# --------------------------------------------------------------------------- the record


def test_the_admission_line_round_trips_into_the_record_field(tmp_path: pathlib.Path) -> None:
    root = red_world(tmp_path, [OPS])
    _refusal, admission = verdict(root, "%s %s %s" % (OPS, ASK, REASON))
    assert admission is not None
    line = admission.line()
    # local.py's gates_verdict counts every `local-gates:` line without "admitted" as a refusal.
    assert line.startswith("local-gates: ")
    assert "admitted" in line
    record = lg.waiver_from_lines(["local-gates: admitted: HEAD may be released to edge", line])
    assert record == admission.record()
    assert record is not None
    assert record["gates"] == [OPS]
    assert record["asked"] == ASK
    assert record["reason"] == REASON
    assert record["tree"] == tree_of(root)
    assert lg.waiver_from_lines(["local-gates: admitted: HEAD may be released to edge"]) is None


def test_the_entry_does_not_read_the_admission_line_as_a_refusal(tmp_path: pathlib.Path) -> None:
    root = red_world(tmp_path, [OPS])
    _refusal, admission = verdict(root, "%s %s %s" % (OPS, ASK, REASON))
    assert admission is not None
    admitted = "local-gates: admitted: HEAD may be released to edge"
    assert local.gates_verdict(0, [admission.line(), admitted], workers_only=False) == 0
    # CONTROL: a real refusal line beside it still refuses.
    refused = "local-gates: lock: v1.0.1 is taken"
    assert local.gates_verdict(1, [admission.line(), refused], workers_only=False) == 1


def _check(root: pathlib.Path, admitted: list[lg.WaiverAdmission] | None) -> list[lg.Refusal]:
    return lg.check(
        root,
        "edge",
        fetch=lambda _r: (None, "offline"),
        sentinel=lambda _v: False,
        existing=lambda _r, _v: (True, ""),
        version="1.0.1",
        clone=lambda _r, _t, _h: None,
        asked_proof=proven,
        admitted=admitted,
    )


def test_check_reads_the_waiver_from_the_environment_and_collects_it(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = red_world(tmp_path, [OPS])
    monkeypatch.setenv(lg.WAIVER_ENV, "%s %s %s" % (OPS, ASK, REASON))
    admitted: list[lg.WaiverAdmission] = []
    refusals = _check(root, admitted)
    assert not [r for r in refusals if r.code == "ci-quick"], refusals
    assert [a.gates for a in admitted] == [(OPS,)]
    monkeypatch.delenv(lg.WAIVER_ENV)
    assert [r for r in _check(root, None) if r.code == "ci-quick"]


def test_check_without_a_collector_prints_the_admission(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = red_world(tmp_path, [OPS])
    monkeypatch.setenv(lg.WAIVER_ENV, "%s %s %s" % (OPS, ASK, REASON))
    _check(root, None)
    err = capsys.readouterr().err
    assert "red-waiver admitted" in err
    assert ASK in err


# --------------------------------------------------------------------------- the live re-run


def _package(root: pathlib.Path, scripts: dict[str, str]) -> None:
    (root / "package.json").write_text(
        json.dumps({"name": "fixture", "private": True, "scripts": scripts}), encoding="utf-8"
    )


def test_the_live_re_run_refuses_a_script_package_json_lacks(tmp_path: pathlib.Path) -> None:
    _package(tmp_path, {"check:other": "true"})
    rc, why = lg.live_rerun(tmp_path, EMBED)
    assert rc is None
    assert "package.json" in why
    assert EMBED in why


def test_the_live_re_run_captures_the_marker_from_a_real_npm_run(tmp_path: pathlib.Path) -> None:
    _package(
        tmp_path,
        {EMBED: "echo retrying; echo '  UPSTREAM REACHABILITY FAILURE (x)' >&2; exit 1"},
    )
    rc, out = lg.live_rerun(tmp_path, EMBED)
    assert rc == 1
    assert lg.UPSTREAM_MARKER in out
    assert "retrying" in out
