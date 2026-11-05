"""Tests for `wl_planbox.py`, box T1 of agent/plans/PLAN-tick-tracking.md.

The trailer grammar (Design 1), the TICK line and its legacy prose reader (Design 5), and the lease-to-landed map (Design 2). The legacy cases read copies of the five writer reports of round 1104-1, stored in `tick_tracking_fixtures/planbox/` one file per writer, and must return exactly the five rows of the plan's Measured-facts table. The copies are the report-store files byte for byte, frontmatter included, under a `.report` suffix: as `.md` the prose-style gate would scan the writers' own first-person prose.

THE CONTROL is the old reading of the same inputs: the message of landed commit 4b3e830f0 carries no Plan-Box, and `wl_report.open_boxes` reads 0 boxes in each of the five reports the legacy reader links.
"""

from __future__ import annotations

import os
import pathlib
import subprocess

import pytest

from rediacc_hooks.tests import wlfix

P = wlfix.import_wl("wl_planbox")
FIX = pathlib.Path(__file__).resolve().parent / "tick_tracking_fixtures" / "planbox"
REPO = pathlib.Path(__file__).resolve().parents[3]

# The plan's Measured-facts table: writer -> (plan, sig, lease shas the report names, landed sha of the first).
MEASURED = {
    "live-proof-ladder": ("PLAN-ssh-key-source-ranges.md", "7692f2db", ("e72acf0a7",), "1d600b20e"),
    "drills-upgrade": ("PLAN-detached-jobs.md", "1d17b634", ("2a3bb490a",), "d4125a0b1"),
    "privdrop-probe": ("PLAN-rediaccfile-unprivileged.md", "afa91934", ("e841f2f78",), "ec099603d"),
    "sampler": ("PLAN-backup-local-image.md", "339bf791", ("d93cb2901",), "e2bdb427c"),
    "executor-seam": ("PLAN-detached-jobs.md", "3d256594", ("ae15f7cba", "40972d8dd"), "4b3e830f0"),
}


def _msg(*trailers, body="feat(x): a subject\n\nA body paragraph."):
    return body + "\n\n" + "\n".join(trailers) + "\n"


# ---- the Plan-Box trailer -------------------------------------------------------


def test_box_trailer_parses():
    r = P.parse_plan_box(
        _msg("PR-TASK: 1d805023", "Plan-Box: PLAN-detached-jobs.md#3d256594 clauses=C1,C2")
    )
    assert r.ok
    assert not r.missing
    assert r.none_reason is None
    assert [(b.plan, b.sig, b.clauses) for b in r.boxes] == [
        ("PLAN-detached-jobs.md", "3d256594", ("C1", "C2"))
    ]


def test_box_trailer_all_and_two_boxes():
    r = P.parse_plan_box(
        _msg(
            "Plan-Box: PLAN-a.md#0123abcd clauses=all",
            "Plan-Box: PLAN-b.md#89abcdef clauses=C3",
            "PR-TASK: 1d805023",
        )
    )
    assert r.ok
    assert [(b.plan, b.sig, b.clauses) for b in r.boxes] == [
        ("PLAN-a.md", "0123abcd", "all"),
        ("PLAN-b.md", "89abcdef", ("C3",)),
    ]


def test_none_trailer_parses():
    r = P.parse_plan_box(_msg("PR-TASK: 1d805023", "Plan-Box: none -- a fixture-only change"))
    assert r.ok
    assert r.boxes == ()
    assert r.none_reason == "a fixture-only change"


@pytest.mark.parametrize(
    ("bad", "good"),
    [
        ("Plan-Box: none -- too short", "Plan-Box: none -- long enough now"),
        (
            "Plan-Box: PLAN-detached-jobs.md#3d25659 clauses=all",
            "Plan-Box: PLAN-detached-jobs.md#3d256594 clauses=all",
        ),
        (
            "Plan-Box: PLAN-detached-jobs.md#3d256594#3d256594 clauses=all",
            "Plan-Box: PLAN-detached-jobs.md#3d256594 clauses=all",
        ),
        (
            "Plan-Box: agent/plans/PLAN-detached-jobs.md#3d256594 clauses=all",
            "Plan-Box: PLAN-detached-jobs.md#3d256594 clauses=all",
        ),
        (
            "Plan-Box: PLAN-detached-jobs.md#3d256594",
            "Plan-Box: PLAN-detached-jobs.md#3d256594 clauses=all",
        ),
        (
            "Plan-Box: PLAN-detached-jobs.md#3d256594 clauses=C1,C1",
            "Plan-Box: PLAN-detached-jobs.md#3d256594 clauses=C1",
        ),
        (
            "plan-box: PLAN-detached-jobs.md#3d256594 clauses=all",
            "Plan-Box: PLAN-detached-jobs.md#3d256594 clauses=all",
        ),
    ],
)
def test_malformed_refused_and_its_fix_admitted(bad, good):
    """Each refusal is paired with the corrected trailer, so a parser that refuses everything fails here."""
    r = P.parse_plan_box(_msg("PR-TASK: 1d805023", bad))
    assert not r.ok
    assert not r.missing
    assert all(P.GRAMMAR in e for e in r.errors)
    assert P.parse_plan_box(_msg("PR-TASK: 1d805023", good)).ok


def test_none_beside_a_box_refused():
    r = P.parse_plan_box(
        _msg("Plan-Box: none -- a fixture-only change", "Plan-Box: PLAN-a.md#0123abcd clauses=all")
    )
    assert not r.ok


def test_trailer_in_body_prose_is_not_a_trailer():
    body = "docs: describe the trailer\n\nWrite Plan-Box: PLAN-a.md#0123abcd clauses=all\nin the trailer block."
    r = P.parse_plan_box(_msg("PR-TASK: 1d805023", body=body))
    assert r.missing
    assert r.errors == (P.NO_PLAN_BOX,)


def _git(cwd, *args):
    env = dict(os.environ)
    env.update(
        {
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@example.invalid",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@example.invalid",
        }
    )
    done = subprocess.run(
        [
            "git",
            "-c",
            "core.hooksPath=" + os.devnull,
            "-c",
            "commit.gpgsign=false",
            "-C",
            str(cwd),
            *args,
        ],
        capture_output=True,
        text=True,
        env=env,
        check=True,
    )
    return done.stdout.strip()


def test_trailer_survives_cherry_pick_x_and_landed_map_reads_it(tmp_path):
    repo = tmp_path / "r"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    (repo / "a").write_text("a\n")
    _git(repo, "add", "a")
    _git(repo, "commit", "-q", "-m", "base")
    _git(repo, "checkout", "-q", "-b", "lease")
    (repo / "b").write_text("b\n")
    _git(repo, "add", "b")
    msg = _msg(
        "PR-TASK: 1d805023",
        "Plan-Box: PLAN-detached-jobs.md#3d256594 clauses=C1,C2",
        body="feat(b): add b\n\nWhy b.",
    )
    _git(repo, "commit", "-q", "-m", msg)
    lease = _git(repo, "rev-parse", "HEAD")
    _git(repo, "checkout", "-q", "main")
    _git(repo, "cherry-pick", "-x", lease)
    landed = _git(repo, "rev-parse", "HEAD")
    assert landed != lease
    out = _git(repo, "show", "-s", "--format=%B", landed)
    assert P.PICKED_LINE % lease in out
    r = P.parse_plan_box(out)
    assert r.ok
    assert [(b.plan, b.sig, b.clauses) for b in r.boxes] == [
        ("PLAN-detached-jobs.md", "3d256594", ("C1", "C2"))
    ]
    # The map: a short lease sha resolves to the landed commit, an unpicked sha is absent, and the lease's own sha is never a value.
    m = P.landed_map(repo, [lease[:9], "0123456789"])
    assert m == {lease[:9]: landed}
    assert lease not in m.values()
    assert P.landed_map(repo, [lease[:9]], rev="lease") == {}
    assert P.landed_map(tmp_path / "nope", [lease[:9]]) is None


# ---- the TICK line and the legacy reader ------------------------------------------


def test_tick_lines_parse_with_close():
    body = (
        "Prose first.\n\n"
        "TICK PLAN-detached-jobs.md#3d256594 partial commits=ae15f7cba,40972d8dd landed=C6 owed=C1:live,C4:operator\n"
        "  close: ./rdc.sh --config eu-bench repo up fork --debug\n"
        "TICK PLAN-backup-local-image.md#339bf791 done commits=d93cb2901 landed=all owed=-\n"
    )
    rows = P.parse_tick(body)
    assert [(r.plan, r.sig, r.state, r.commits, r.landed, r.owed, r.legacy) for r in rows] == [
        (
            "PLAN-detached-jobs.md",
            "3d256594",
            "partial",
            ("ae15f7cba", "40972d8dd"),
            ("C6",),
            (("C1", "live"), ("C4", "operator")),
            False,
        ),
        ("PLAN-backup-local-image.md", "339bf791", "done", ("d93cb2901",), "all", (), False),
    ]
    assert rows[0].close == "./rdc.sh --config eu-bench repo up fork --debug"
    assert rows[1].close is None


def test_tick_line_with_unknown_state_is_not_a_row():
    assert P.parse_tick("TICK PLAN-a.md#0123abcd finished commits=- landed=- owed=-\n") == []


def _bodies():
    return {name: (FIX / (name + ".report")).read_text(encoding="utf-8") for name in MEASURED}


def test_legacy_reader_returns_the_measured_rows():
    got = {}
    for name, body in _bodies().items():
        rows = P.parse_tick(body)
        assert len(rows) == 1, (name, rows)
        assert rows[0].legacy
        got[name] = (rows[0].plan, rows[0].sig, rows[0].commits)
    assert got == {name: (plan, sig, shas) for name, (plan, sig, shas, _l) in MEASURED.items()}


def test_legacy_rows_carry_state_and_live_owed():
    rows = {name: P.parse_tick(body)[0] for name, body in _bodies().items()}
    assert rows["privdrop-probe"].state == "partial"
    assert rows["privdrop-probe"].owed == (("*", "live"),)
    assert all(r.state != "done" for r in rows.values())


def test_landed_map_on_this_history():
    """The five lease shas map to the landed shas of the Measured-facts table, through the real `-x` lines."""
    if subprocess.run(
        ["git", "-C", str(REPO), "cat-file", "-e", "4b3e830f0^{commit}"],
        capture_output=True,
        check=False,
    ).returncode:
        pytest.skip("history without the 1104-1 landed commits (shallow clone)")
    m = P.landed_map(REPO, [shas[0] for _p, _s, shas, _l in MEASURED.values()])
    assert {k: v[:9] for k, v in m.items()} == {
        shas[0]: landed for _p, _s, shas, landed in MEASURED.values()
    }


# ---- CONTROL: the old reading of the same inputs -------------------------------------


def test_control_landed_commit_has_no_plan_box():
    msg = (FIX / "control-4b3e830f0.msg").read_text(encoding="utf-8")
    probe = subprocess.run(
        ["git", "-C", str(REPO), "show", "-s", "--format=%B", "4b3e830f0"],
        capture_output=True,
        text=True,
        check=False,
    )
    if probe.returncode == 0:
        assert probe.stdout == msg, "the fixture is a copy of the real message"
    r = P.parse_plan_box(msg)
    assert r.missing
    assert r.errors == (P.NO_PLAN_BOX,)
    assert r.boxes == ()


def test_control_open_boxes_reads_zero_where_the_legacy_reader_links_five():
    wl_report = wlfix.import_wl("wl_report")
    bodies = _bodies()
    assert [wl_report.open_boxes(b) for b in bodies.values()] == [0] * 5
    assert sum(len(P.parse_tick(b)) for b in bodies.values()) == 5
