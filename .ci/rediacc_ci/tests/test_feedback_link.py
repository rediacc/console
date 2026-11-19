"""rediacc_ci.feedback.link, .ship and the check:ci-plan-feedback gate (PLAN-rdc-feedback R10, D5, box T3), no network: the gate fails an absent id, an empty snapshot with a plan carrying the line, and passes a present id and zero carriers with the count printed; ship maps a ticked plan's landing commit to the first containing v* tag on a fixture repository; link writes the header line and the planned verdict; the snapshot holds only id, status and fixed_in."""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import pytest

from rediacc_ci import controls, paths
from rediacc_ci.feedback import classify, link, plangen, ship, triage

if TYPE_CHECKING:
    from pathlib import Path

GATE = paths.repo_root() / ".ci" / "scripts" / "quality" / "check_plan_feedback.py"
NOW = datetime(2026, 11, 19, 8, 0, tzinfo=UTC)
FP_A = "a" * 64
FP_B = "b" * 64
FP_C = "c" * 64
A = FP_A[:12]
B = FP_B[:12]


@pytest.fixture(autouse=True)
def _no_caller_repo(monkeypatch):
    for name in controls.GIT_REPO_ENV:
        monkeypatch.delenv(name, raising=False)


def _plan(feedback=None, boxes=("- [ ] T1 [writer] x",), extra=""):
    rows = ["# PLAN: x", "", "Status: approved", "Owner: tester", "Owns: agent/plans/PLAN-x.md"]
    if feedback is not None:
        rows.append("Feedback: %s" % feedback)
    return "\n".join(
        [*rows, "", "## Context", "", "- the fix" + extra, "", "## Boxes", "", *boxes, ""]
    )


def _snap(*ids):
    return json.dumps(
        {
            "version": 1,
            "fingerprints": [{"id": i, "status": "planned", "fixed_in": None} for i in ids],
        }
    )


def _tree(tmp_path: Path, plans: dict[str, str], snapshot: str | None) -> Path:
    for name, text in plans.items():
        target = tmp_path / "agent" / "plans" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    if snapshot is not None:
        target = tmp_path.joinpath(*link.SNAPSHOT_PARTS)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(snapshot, encoding="utf-8")
    return tmp_path


def _gate(root: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(GATE), "--root", str(root)],
        capture_output=True,
        text=True,
        check=False,
    )


# ---- the gate, through its real entry point ------------------------------------------------------


def test_gate_fails_an_id_absent_from_the_snapshot(tmp_path):
    done = _gate(_tree(tmp_path, {"PLAN-x.md": _plan(A)}, _snap(B)))
    assert done.returncode == 1, done.stdout + done.stderr
    assert "F1 agent/plans/PLAN-x.md: Feedback: id %s is not in the snapshot" % A in done.stderr


def test_gate_passes_an_id_present_in_the_snapshot(tmp_path):
    done = _gate(_tree(tmp_path, {"PLAN-x.md": _plan(A)}, _snap(A, B)))
    assert done.returncode == 0, done.stdout + done.stderr
    assert (
        "1 live plan(s), 1 carry Feedback: with 1 id(s), snapshot 2 fingerprint(s)" in done.stdout
    )


def test_gate_fails_an_empty_snapshot_while_a_plan_carries_the_line(tmp_path):
    done = _gate(_tree(tmp_path, {"PLAN-x.md": _plan(A)}, _snap()))
    assert done.returncode == 1
    assert (
        "F3 1 plan(s) carry a Feedback: line while agent/ledgers/feedback-snapshot.json is empty"
        in done.stderr
    )


def test_gate_fails_a_missing_snapshot_while_a_plan_carries_the_line(tmp_path):
    done = _gate(_tree(tmp_path, {"PLAN-x.md": _plan(A)}, None))
    assert done.returncode == 1
    assert "is missing" in done.stderr


def test_gate_passes_zero_plans_with_the_line_and_prints_the_count(tmp_path):
    done = _gate(_tree(tmp_path, {"PLAN-x.md": _plan(), "PLAN-y.md": _plan()}, None))
    assert done.returncode == 0, done.stdout + done.stderr
    assert "2 live plan(s), 0 carry Feedback: with 0 id(s), snapshot absent" in done.stdout


def test_gate_with_no_plans_at_all_cannot_run(tmp_path):
    (tmp_path / "agent" / "plans").mkdir(parents=True)
    done = _gate(tmp_path)
    assert done.returncode == 77
    assert "CANNOT RUN" in done.stderr


def test_gate_refuses_a_snapshot_row_holding_more_than_the_public_fields(tmp_path):
    snap = json.dumps(
        {
            "version": 1,
            "fingerprints": [{"id": A, "status": "new", "fixed_in": None, "argv": "rdc x"}],
        }
    )
    done = _gate(_tree(tmp_path, {"PLAN-x.md": _plan()}, snap))
    assert done.returncode == 1
    assert "F4" in done.stderr


def test_gate_selftest_passes():
    done = subprocess.run(
        [sys.executable, str(GATE), "--selftest"], capture_output=True, text=True, check=False
    )
    assert done.returncode == 0, done.stdout + done.stderr


# ---- the grammar ---------------------------------------------------------------------------------


def test_feedback_line_reads_the_header_only_and_splits_bad_tokens():
    held = link.feedback_line(_plan("%s, nothex, %s" % (A, A)))
    assert held is not None
    assert held.ids == (A,)
    assert held.bad == ("nothex",)
    assert link.feedback_line(_plan() + "\nFeedback: %s\n" % A) is None


def test_plangen_line_agrees_with_the_grammar(tmp_path):
    """Review b82c76c1.4: the plan text is written by `plangen.write`, so a change to its `Feedback:` output fails here. Control: a hand-written line reads the same."""
    cls = classify.parse_reply(
        json.dumps(
            {
                "meaningful": True,
                "safe_to_reproduce": True,
                "suspicious": False,
                "category": "backup",
                "core_path": True,
                "summary": "backup push fails on a fresh repo",
            }
        )
    )
    written = plangen.write(tmp_path, _item(FP_A, "confirmed"), cls, NOW)
    assert _ids((tmp_path / written.rel).read_text(encoding="utf-8")) == (A,)
    assert _ids("# PLAN\n\nOwner: x\nFeedback: %s\n\n## Context\n" % FP_A[:12]) == (A,)


def _ids(text):
    held = link.feedback_line(text)
    return None if held is None else held.ids


def test_with_feedback_ids_inserts_after_the_header_block():
    text = link.with_feedback_ids(_plan(), [A])
    assert "Owns: agent/plans/PLAN-x.md\nFeedback: %s\n\n## Context" % A in text


def test_with_feedback_ids_merges_into_an_existing_line_once():
    text = link.with_feedback_ids(_plan(A), [B, A])
    assert text.count("Feedback:") == 1
    assert "Feedback: %s, %s\n" % (A, B) in text


def test_with_feedback_ids_keeps_a_malformed_token_for_the_gate():
    """Review b82c76c1.2: a rewrite that gains a match keeps the bad token the gate reports. Control: the well-formed ids merge as before."""
    text = link.with_feedback_ids(_plan("%s, nothex" % A), [B])
    held = link.feedback_line(text)
    assert held is not None
    assert held.ids == (A, B)
    assert held.bad == ("nothex",)
    assert text.count("Feedback:") == 1


def test_link_reply_schema():
    assert link.parse_link_reply('{"ids": ["%s"]}' % A, [A, B]) == [A]
    assert link.parse_link_reply('{"ids": []}', [A]) == []
    for bad in (
        '{"ids": ["%s"]}' % ("f" * 12),
        "sure: {}",
        '{"ids": [], "x": 1}',
        '{"ids": ["%s", "%s"]}' % (A, A),
    ):
        with pytest.raises(link.LinkReplyError):
            link.parse_link_reply(bad, [A, B])


def test_link_prompt_keeps_plan_and_entries_between_markers():
    prompt = link.link_prompt(_plan(), [{"id": A, "category": "backup", "summary": "push fails"}])
    assert prompt.startswith(link.LINK_HEAD)
    assert prompt.endswith(link.LINK_TAIL)
    assert link.LINK_MID in prompt
    assert "## Boxes" not in prompt  # header and first section only


def test_snapshot_rows_hold_only_id_status_fixed_in(tmp_path):
    row = link.snapshot_row(
        {"fingerprint": FP_A, "status": "fixed", "fixedIn": "3.0.1", "argv": "x", "triageNote": "y"}
    )
    assert row == {"id": A, "status": "fixed", "fixed_in": "3.0.1"}
    path = tmp_path / "s.json"
    link.write_snapshot(path, [row])
    doc = json.loads(path.read_text())
    assert set(doc) == {"version", "fingerprints"}
    assert all(set(r) == {"id", "status", "fixed_in"} for r in doc["fingerprints"])


def test_snapshot_merge_keeps_unexported_rows_and_ranks_regions():
    held: list[dict[str, Any]] = [{"id": B, "status": "planned", "fixed_in": None}]
    fresh: list[dict[str, Any]] = [
        {"id": A, "status": "screening", "fixed_in": None},
        {"id": A, "status": "fixed", "fixed_in": "3.0.0"},
    ]
    assert link.merge_rows(held, fresh) == [
        {"id": A, "status": "fixed", "fixed_in": "3.0.0"},
        {"id": B, "status": "planned", "fixed_in": None},
    ]


def test_a_foreign_snapshot_is_never_overwritten(tmp_path):
    path = tmp_path / "s.json"
    path.write_text('{"version": 2}')
    with pytest.raises(link.SnapshotError):
        link.write_snapshot(path, [])
    assert path.read_text() == '{"version": 2}'


# The committed agent/ledgers/feedback-snapshot.json before the first link or ship run: no
# fingerprint yet. `write_snapshot` over an absent file with no rows writes exactly these bytes.
BOOTSTRAP_SNAPSHOT = '{\n  "version": 1,\n  "fingerprints": []\n}\n'


def test_bootstrap_snapshot_is_what_write_snapshot_emits_and_the_gate_reads(tmp_path):
    path = tmp_path.joinpath(*link.SNAPSHOT_PARTS)
    assert link.write_snapshot(path, []) == 0
    assert path.read_text(encoding="utf-8") == BOOTSTRAP_SNAPSHOT
    assert link.read_snapshot(path) == []
    _tree(tmp_path, {"PLAN-x.md": _plan()}, None)
    done = _gate(tmp_path)
    assert done.returncode == 0, done.stdout + done.stderr
    assert "snapshot 0 fingerprint(s)" in done.stdout


# ---- a stub account ------------------------------------------------------------------------------


class Stub:
    def __init__(self, items):
        self.items = items
        self.posts = []

    def get(self, route):
        assert route.startswith("/admin/feedback/export")
        return 200, {"items": self.items}

    def post(self, route, body):
        self.posts.append((route, body))
        return 200, {
            "fingerprints": len(body["verdicts"]),
            "reports": len(body["verdicts"]),
            "missing": [],
        }


def _item(fp, status="screening", **extra):
    base = {"fingerprint": fp, "status": status, "lastSeenAt": "2026-11-19T07:00:00.000Z"}
    return {**base, **extra}


def _note(summary="backup push fails on a fresh repo"):
    cls = classify.parse_reply(
        json.dumps(
            {
                "meaningful": True,
                "safe_to_reproduce": True,
                "suspicious": False,
                "category": "backup",
                "core_path": True,
                "summary": summary,
            }
        )
    )
    return classify.note_for(cls)


# ---- a fixture repository ------------------------------------------------------------------------


def _git(root, *args):
    return subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        text=True,
        check=True,
        env={
            **controls.fixture_git_env(),
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@t",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@t",
        },
    ).stdout.strip()


def _commit(root, name):
    (root / name).write_text(name)
    _git(root, "add", name)
    _git(root, "commit", "-q", "-m", name)
    return _git(root, "rev-parse", "HEAD")


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    first = _commit(root, "one")
    _git(root, "tag", "v1.0.0")
    second = _commit(root, "two")
    _git(root, "tag", "v1.1.0")
    _git(root, "tag", "v1.10.0")
    _git(root, "tag", "not-a-release")
    third = _commit(root, "three")
    return root, first, second, third


def test_first_tag_is_the_lowest_release_tag_containing_the_commit(repo):
    root, first, second, third = repo
    assert ship.git_first_tag(root, first) == "v1.0.0"
    assert ship.git_first_tag(root, second) == "v1.1.0"
    assert ship.git_first_tag(root, third) is None
    with pytest.raises(ship.UnknownCommitError):
        ship.git_first_tag(root, "0" * 40)


def _ship_plan(root, text, name="PLAN-x.md"):
    target = root / "agent" / "plans" / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text)
    return target


def _ticked(*shas):
    return tuple(
        "- [x] T%d [writer] x\n    (ticked) 2026-11-19T07:00:00Z by t: commit:%s done"
        % (n, sha[:9])
        for n, sha in enumerate(shas, 1)
    )


def test_ship_maps_a_ticked_plans_landing_commits_to_the_first_containing_tag(repo):
    root, first, second, _ = repo
    _ship_plan(root, _plan(A, boxes=_ticked(first, second)))
    stub = Stub([_item(FP_A, "planned"), _item(FP_B, "planned")])
    out: list[str] = []
    deps = ship.Deps(open_region=lambda *_: stub, out=out.append)
    snap = root / "snap.json"
    rc = ship.run(ship.Options(("eu",), snapshot=snap, root=root), deps)
    assert rc == 0, out
    # first is in v1.0.0, second first in v1.1.0: the plan is out only in v1.1.0.
    assert stub.posts == [
        (
            "/admin/feedback/verdicts",
            {"verdicts": [{"fingerprint": FP_A, "status": "fixed", "fixedIn": "1.1.0"}]},
        )
    ]
    assert "eu %s fixed-in-v1.1.0" % A in out
    doc = json.loads(snap.read_text())
    assert doc["fingerprints"] == [
        {"id": A, "status": "fixed", "fixed_in": "1.1.0"},
        {"id": B, "status": "planned", "fixed_in": None},
    ]


def test_ship_leaves_a_plan_whose_commit_is_in_no_release_pending(repo):
    root, first, _, third = repo
    _ship_plan(root, _plan(A, boxes=_ticked(first, third)))
    stub = Stub([_item(FP_A, "planned")])
    out: list[str] = []
    rc = ship.run(
        ship.Options(("eu",), snapshot=root / "s.json", root=root),
        ship.Deps(open_region=lambda *_: stub, out=out.append),
    )
    assert rc == 0
    assert stub.posts == []
    assert any("pending" in line for line in out)


def test_ship_ignores_a_plan_with_an_open_box(repo):
    root, first, _, _ = repo
    _ship_plan(root, _plan(A, boxes=(*_ticked(first), "- [ ] T9 [writer] still open")))
    stub = Stub([_item(FP_A, "planned")])
    rc = ship.run(
        ship.Options(("eu",), snapshot=root / "s.json", root=root),
        ship.Deps(open_region=lambda *_: stub, out=lambda _: None),
    )
    assert rc == 0
    assert stub.posts == []


def test_ship_reads_done_plans_and_skips_an_already_fixed_fingerprint(repo):
    root, first, _, _ = repo
    _ship_plan(root, _plan(A, boxes=_ticked(first)), name="_done/PLAN-x.md")
    stub = Stub([_item(FP_A, "fixed", fixedIn="1.0.0")])
    rc = ship.run(
        ship.Options(("eu",), snapshot=root / "s.json", root=root),
        ship.Deps(open_region=lambda *_: stub, out=lambda _: None),
    )
    assert rc == 0
    assert stub.posts == []


def test_ship_errors_on_an_unknown_commit_and_dry_run_writes_nothing(repo):
    root, _, _, _ = repo
    _ship_plan(root, _plan(A, boxes=_ticked("d" * 40)))
    stub = Stub([_item(FP_A, "planned")])
    snap = root / "s.json"
    rc = ship.run(
        ship.Options(("eu",), dry_run=True, snapshot=snap, root=root),
        ship.Deps(open_region=lambda *_: stub, out=lambda _: None),
    )
    assert rc == 1
    assert stub.posts == []
    assert not snap.exists()


# ---- link ----------------------------------------------------------------------------------------


def test_link_writes_the_line_the_planned_verdict_the_snapshot_and_the_state(repo):
    root, _, _, _ = repo
    base = _git(root, "rev-parse", "HEAD")
    _ship_plan(root, _plan())
    _ship_plan(
        root,
        "# PLAN draft\n\nOwner: t\nFeedback: %s\n\n## Context\n" % B,
        name="PLAN-feedback-x.md",
    )
    _git(root, "add", "agent")
    _git(root, "commit", "-q", "-m", "plans")
    stub = Stub(
        [
            _item(FP_A, "confirmed", triageNote=_note()),
            _item(FP_B, "planned", triageNote=_note("another"), planRef="PLAN-feedback-x.md"),
            _item(FP_C, "quarantined", triageNote="stage1 url"),
        ]
    )
    prompts = []

    def complete(prompt):
        prompts.append(prompt)
        return '{"ids": ["%s"]}' % A

    out: list[str] = []
    snap = root / "snap.json"
    state = root / "state.json"
    opts = link.Options(("eu",), since=base, snapshot=snap, state=state, root=root)
    rc = link.run(
        opts,
        link.Deps(open_region=lambda *_: stub, out=out.append, complete=complete, now=lambda: NOW),
    )
    assert rc == 0, out
    assert len(prompts) == 1  # the PLAN-feedback-* draft is skipped
    assert FP_C[:12] not in prompts[0]  # a quarantined fingerprint is no candidate
    text = (root / "agent" / "plans" / "PLAN-x.md").read_text()
    assert _ids(text) == (A,)
    assert stub.posts == [
        (
            "/admin/feedback/verdicts",
            {"verdicts": [{"fingerprint": FP_A, "status": "planned", "planRef": "PLAN-x.md"}]},
        )
    ]
    doc = json.loads(snap.read_text())
    assert [r["id"] for r in doc["fingerprints"]] == [A, B, FP_C[:12]]
    assert doc["fingerprints"][0] == {"id": A, "status": "planned", "fixed_in": None}
    assert json.loads(state.read_text())["head"] == _git(root, "rev-parse", "HEAD")


def _link_once(root, stub, base, state, replies):
    return link.run(
        link.Options(("eu",), since=base, snapshot=root / "s.json", state=state, root=root),
        link.Deps(
            open_region=lambda *_: stub,
            out=lambda _: None,
            complete=lambda prompt: replies.append(prompt) or '{"ids": []}',
            now=lambda: NOW,
        ),
    )


def _commit_plan(root):
    base = _git(root, "rev-parse", "HEAD")
    _ship_plan(root, _plan())
    _git(root, "add", "agent")
    _git(root, "commit", "-q", "-m", "plan")
    return base


def test_link_holds_the_state_when_a_changed_plan_met_no_candidate(repo):
    """Review b82c76c1.1: a changed plan offered nothing is not marked read, or a fingerprint classified later would never be offered to it. Control: with a candidate the same run writes the state."""
    root, _, _, _ = repo
    base = _commit_plan(root)
    state = root / "state.json"
    replies: list[str] = []
    stub = Stub([_item(FP_C, "quarantined", triageNote="stage1 url")])
    assert _link_once(root, stub, base, state, replies) == 0
    assert replies == []
    assert not state.exists()
    stub = Stub([_item(FP_A, "confirmed", triageNote=_note())])
    assert _link_once(root, stub, base, state, replies) == 0
    assert len(replies) == 1
    assert state.exists()


def test_link_warns_and_holds_the_state_when_candidates_are_cut(repo, monkeypatch, capsys):
    """Review b82c76c1.3 and .1: fingerprints beyond CANDIDATES_MAX are named in a warning and hold the state. Control: within the bound there is no warning and the state is written."""
    root, _, _, _ = repo
    base = _commit_plan(root)
    state = root / "state.json"
    items = [
        _item(FP_A, "confirmed", triageNote=_note()),
        _item(FP_B, "confirmed", triageNote=_note("another")),
    ]
    assert _link_once(root, Stub(items), base, state, []) == 0
    assert "beyond the first" not in capsys.readouterr().err
    assert state.exists()
    state.unlink()
    monkeypatch.setattr(link, "CANDIDATES_MAX", 1)
    assert _link_once(root, Stub(items), base, state, []) == 0
    assert "1 open fingerprint(s) beyond the first 1" in capsys.readouterr().err
    assert not state.exists()


def test_link_first_run_without_since_is_refused(repo):
    root, _, _, _ = repo
    opts = link.Options(("eu",), snapshot=root / "s.json", state=root / "state.json", root=root)
    rc = link.run(
        opts, link.Deps(open_region=lambda *_: pytest.fail("no request"), out=lambda _: None)
    )
    assert rc == 2


def test_link_reply_off_schema_leaves_the_plan_and_holds_the_state(repo):
    root, _, _, _ = repo
    base = _git(root, "rev-parse", "HEAD")
    _ship_plan(root, _plan())
    _git(root, "add", "agent")
    _git(root, "commit", "-q", "-m", "plan")
    stub = Stub([_item(FP_A, "confirmed", triageNote=_note())])
    state = root / "state.json"
    opts = link.Options(("eu",), since=base, snapshot=root / "s.json", state=state, root=root)
    rc = link.run(
        opts,
        link.Deps(
            open_region=lambda *_: stub,
            out=lambda _: None,
            complete=lambda _: "ok",
            now=lambda: NOW,
        ),
    )
    assert rc == 1
    assert link.feedback_line((root / "agent" / "plans" / "PLAN-x.md").read_text()) is None
    assert stub.posts == []
    assert not state.exists()


# ---- the shared entry ----------------------------------------------------------------------------


def test_reexec_names_the_calling_module():
    seen: list[list[str]] = []

    def child(argv, _env):
        seen.append(list(argv))
        return 0

    rc = triage.reexec_under_profile(["run"], "root-login", {}, child, link.SELF)
    assert rc == 0
    assert seen[0][-3:] == ["-m", link.SELF, "run"]


def test_parse_args_defaults_to_the_production_regions():
    assert link.parse_args(["run", "--since", "HEAD"]).regions == ("eu", "us", "asia")
    assert ship.parse_args(["run", "--region", "bench"]).regions == ("bench",)
