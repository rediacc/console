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


def test_a_malformed_tick_line_is_never_read_as_legacy_prose():
    """Review 39bfb45b.1: a TICK line in the grammar's shape that fails it fell back to the legacy reader, which read the prose region after it as `legacy=True` rows. CONTROL: the same prose with no grammar-shaped line is still read."""
    prose = "TICK agent/plans/PLAN-a.md box `0123abcd` done 4b3e830f0\n"
    assert [r.legacy for r in P.parse_tick(prose)] == [True]
    bad = "TICK PLAN-a.md#0123abcd finished commits=4b3e830f0 landed=all owed=-\n" + prose
    assert P.parse_tick(bad) == []


def test_an_unknown_owed_half_reads_as_the_placeholder():
    """Review 39bfb45b.2: `owed=C1:bogus` kept `bogus`; an unknown or missing half is `?`."""
    rows = P.parse_tick(
        "TICK PLAN-a.md#0123abcd partial commits=- landed=- owed=C1:bogus,C2,C3:live\n"
    )
    assert rows[0].owed == (("C1", "?"), ("C2", "?"), ("C3", "live"))


def test_landed_map_refuses_a_short_sha_two_lease_commits_share(tmp_path):
    """Review 39bfb45b.3: a short lease sha matched the newest of every `-x` line it prefixes. Two lease shas sharing `abcdef1` make that prefix name neither, a 4-hex input is no sha at all, and a longer prefix still maps."""
    repo = tmp_path / "r"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    one, two = "abcdef1" + "0" * 33, "abcdef1" + "9" * 33
    for n, lease in enumerate((one, two)):
        _git(repo, "commit", "-q", "--allow-empty", "-m", "land %d\n\n" % n + P.PICKED_LINE % lease)
    first = _git(repo, "rev-parse", "HEAD~1")
    assert P.landed_map(repo, ["abcdef1"]) == {}
    assert P.landed_map(repo, ["abcd"]) == {}
    assert P.landed_map(repo, ["abcdef10"]) == {"abcdef10": first}


@pytest.mark.parametrize("given", ["docs/PLAN-fx.md", "other/agent/plans/PLAN-fx.md"])
def test_open_box_refuses_a_plan_path_outside_agent_plans(tmp_path, given):
    """Review 52b4512d.1: only the basename resolved, so `docs/PLAN-fx.md` opened agent/plans/PLAN-fx.md. CONTROL: the basename, the repo-relative and the absolute path still open it."""
    _plant(tmp_path)
    with pytest.raises(P.PlanBoxError, match="no plan under agent/plans"):
        P.open_box(tmp_path, given, OPEN_SIG)
    for ok in ("PLAN-fx.md", "agent/plans/PLAN-fx.md", str(tmp_path / "agent/plans/PLAN-fx.md")):
        assert P.open_box(tmp_path, ok, OPEN_SIG)[1] == OPEN_SIG


def test_open_box_honours_the_plan_folder_it_was_given(tmp_path):
    """Review a493639d.1: `agent/plans/_removed/PLAN-fx.md` opened the live PLAN-fx.md. CONTROL: the live path still opens it; a folder with no such plan is refused."""
    _plant(tmp_path)
    assert P.open_box(tmp_path, "agent/plans/PLAN-fx.md", OPEN_SIG)[0] == "agent/plans/PLAN-fx.md"
    with pytest.raises(P.PlanBoxError, match="no plan under agent/plans"):
        P.open_box(tmp_path, "agent/plans/_removed/PLAN-fx.md", OPEN_SIG)
    done = tmp_path / "agent" / "plans" / "_done" / "PLAN-fx.md"
    done.parent.mkdir(parents=True)
    done.write_text(PLAN_TEXT, encoding="utf-8")
    assert P.open_box(tmp_path, "agent/plans/_done/PLAN-fx.md", OPEN_SIG)[0] == (
        "agent/plans/_done/PLAN-fx.md"
    )


def _stub(root, name, target):
    path = root / "agent" / "plans" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# stub\n\nStatus: moved\nMoved-To: %s\n" % target, encoding="utf-8")


@pytest.mark.parametrize("target", ["../../outside.md", "/etc/hostname", "docs/PLAN-fx.md"])
def test_a_stub_pointing_outside_agent_plans_is_no_plan(tmp_path, target):
    """Review 214fe8a1.2: the `Moved-To:` target was read as given, so a stub could name a file outside the checkout. CONTROL: a stub into `_done/` resolves."""
    (tmp_path / "outside.md").write_text("secret\n", encoding="utf-8")
    _stub(tmp_path, "PLAN-s.md", target)
    assert P.resolve_plan(tmp_path, "PLAN-s.md") is None
    (tmp_path / "agent" / "plans" / "_done").mkdir(parents=True)
    (tmp_path / "agent" / "plans" / "_done" / "PLAN-s.md").write_text(PLAN_TEXT, encoding="utf-8")
    _stub(tmp_path, "PLAN-s.md", "agent/plans/_done/PLAN-s.md")
    assert P.resolve_plan(tmp_path, "PLAN-s.md")[0] == "agent/plans/_done/PLAN-s.md"


def test_a_stub_chain_longer_than_the_hop_limit_is_named_not_missing(tmp_path):
    """Review 214fe8a1.3: a deep chain read as "no plan under agent/plans/"."""
    _plant(tmp_path)
    names = ["PLAN-h%d.md" % i for i in range(P.STUB_HOPS)]
    for i, name in enumerate(names):
        _stub(
            tmp_path, name, "agent/plans/" + (names[i + 1] if i + 1 < len(names) else "PLAN-fx.md")
        )
    with pytest.raises(P.PlanBoxError, match="Moved-To chain"):
        P.resolve_plan(tmp_path, names[0])
    box = P.parse_plan_box("x\n\nPlan-Box: %s#%s clauses=all\n" % (names[0], OPEN_SIG)).boxes[0]
    assert "Moved-To chain" in P.box_problems(tmp_path, box)[0]


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


# ---- T8: the progress ledger and the clause verbs ------------------------------------

PLAN_TEXT = """# PLAN: fx

Status: approved

## Tasks

- [ ] F1 the open box of the fixture plan
- [x] F2 the ticked box of the fixture plan
    (ticked) 2026-01-01 by x: commit:abc
"""
OPEN_SIG, DONE_SIG = "fd66592c", "074be283"
SPECS = ("C1 [code] the offline recipe", "C2 [live] baseline read-only on a machine")


def _plant(root):
    plan = root / "agent" / "plans" / "PLAN-fx.md"
    plan.parent.mkdir(parents=True, exist_ok=True)
    plan.write_text(PLAN_TEXT, encoding="utf-8")
    return plan


def test_progress_define_row_written_once_then_deduped(tmp_path, monkeypatch):
    monkeypatch.setenv("TMPDIR", str(tmp_path / "tmp"))
    plan = _plant(tmp_path)
    before = plan.read_bytes()
    row = P.define_row(tmp_path, "agent/plans/PLAN-fx.md", OPEN_SIG, SPECS, "deadbeef")
    assert row["sig"] == OPEN_SIG
    assert row["plan"] == "agent/plans/PLAN-fx.md"
    assert [(c["id"], c["half"]) for c in row["clauses"]] == [("C1", "code"), ("C2", "live")]
    stored, written = P.append_progress(tmp_path, row)
    assert written
    again, written2 = P.append_progress(
        tmp_path, P.define_row(tmp_path, "PLAN-fx.md", OPEN_SIG, SPECS, "cafe1234")
    )
    assert not written2
    assert again["at"] == stored["at"]
    assert len(P.read_progress(tmp_path)) == 1
    assert [c["id"] for c in P.clause_map(tmp_path, "PLAN-fx.md", OPEN_SIG)] == ["C1", "C2"]
    assert plan.read_bytes() == before, "a clause map changes no plan byte"


@pytest.mark.parametrize("sig", [DONE_SIG, "fd66592d", "0123abcd"])
def test_progress_define_on_a_done_or_unknown_sig_is_refused(tmp_path, sig):
    _plant(tmp_path)
    with pytest.raises(P.PlanBoxError):
        P.define_row(tmp_path, "PLAN-fx.md", sig, SPECS, "deadbeef")


@pytest.mark.parametrize(
    "specs",
    [
        ("C1 code the recipe",),
        ("C1 [cloud] the recipe",),
        ("all [code] x",),
        ("C1 [code] a", "C1 [live] b"),
        (),
    ],
)
def test_progress_define_with_a_bad_clause_is_refused(tmp_path, specs):
    _plant(tmp_path)
    with pytest.raises(P.PlanBoxError):
        P.define_row(tmp_path, "PLAN-fx.md", OPEN_SIG, specs, "deadbeef")


def test_progress_row_needs_a_defined_clause_and_a_known_state(tmp_path, monkeypatch):
    monkeypatch.setenv("TMPDIR", str(tmp_path / "tmp"))
    _plant(tmp_path)
    assert P.progress_row(tmp_path, "PLAN-fx.md", OPEN_SIG, "all", "landed", "abc1234", "x")
    with pytest.raises(P.PlanBoxError, match="not defined"):
        P.progress_row(tmp_path, "PLAN-fx.md", OPEN_SIG, "C1", "landed", "abc1234", "x")
    P.append_progress(tmp_path, P.define_row(tmp_path, "PLAN-fx.md", OPEN_SIG, SPECS, "x"))
    row = P.progress_row(tmp_path, "PLAN-fx.md", OPEN_SIG, "C2", "live-owed", "release", "x")
    P.append_progress(tmp_path, row)
    assert P.box_state(tmp_path, "PLAN-fx.md", OPEN_SIG) == {"C2": ("live-owed", "release")}
    with pytest.raises(P.PlanBoxError, match="state"):
        P.progress_row(tmp_path, "PLAN-fx.md", OPEN_SIG, "C1", "maybe", "abc1234", "x")


def test_progress_cli_box_clauses_writes_then_keeps(wl):
    _plant(wl.proj)
    rel = "agent/plans/PLAN-fx.md"
    got = wl.cli("--box-clauses", wlfix.ME, rel, OPEN_SIG, *SPECS)
    assert got.rc == 0, got.err
    assert "dry run" in got.out
    ledger = wl.proj / "agent" / "ledgers" / "plan-box-progress.jsonl"
    assert not ledger.exists()
    got = wl.cli("--box-clauses", wlfix.ME, rel, OPEN_SIG, *SPECS, "--write")
    assert got.rc == 0, got.err
    assert "appended to agent/ledgers/plan-box-progress.jsonl" in got.out
    got = wl.cli("--box-clauses", wlfix.ME, rel, OPEN_SIG, *SPECS, "--write")
    assert got.rc == 0, got.err
    assert "already holds this row" in got.out
    assert len(ledger.read_text(encoding="utf-8").splitlines()) == 1
    listed = wl.cli("--box-clauses", wlfix.ME)
    assert "clause maps: 1 box(es)" in listed.out
    assert "PLAN-fx.md#%s  C1[code] C2[live]" % OPEN_SIG in listed.out


def test_progress_cli_control_a_typo_sig_exits_2_and_writes_nothing(wl):
    """The box's CONTROL: one hex digit off (fd66592c -> fd66592d) names no open box."""
    _plant(wl.proj)
    rel = "agent/plans/PLAN-fx.md"
    got = wl.cli("--box-clauses", wlfix.ME, rel, "fd66592d", *SPECS, "--write")
    assert got.rc == 2
    assert "no OPEN box matches" in got.err
    assert not (wl.proj / "agent" / "ledgers" / "plan-box-progress.jsonl").exists()


def test_progress_cli_box_progress_writes_a_row(wl):
    _plant(wl.proj)
    rel = "agent/plans/PLAN-fx.md"
    got = wl.cli("--box-progress", wlfix.ME, rel, OPEN_SIG, "all", "proved", "lp-x1", "--write")
    assert got.rc == 0, got.err
    assert "box progress: 1 row(s)" in wl.cli("--box-progress", wlfix.ME).out
