"""wl_planpreflight against a fixture git repository with an `origin/main` ref (agent/plans/PLAN-plan-preflight.md, box PF3).

Each case plants one defect and pairs it with a silent control from the same fixture with one fact changed. The fixture's history is linear: a MAIN commit is a commit followed by moving `origin/main` to it (the branch already holds it, as after a rebase), a BRANCH commit leaves `origin/main` where it was. So the merge base B is always the last main commit.
"""

from __future__ import annotations

import json
import pathlib
import subprocess

import pytest

from rediacc_hooks.tests.wlfix import import_wl

PP = import_wl("wl_planpreflight")
PR = import_wl("wl_planrec")
PFILE = import_wl("wl_planfile")

PLAN = "agent/plans/PLAN-p.md"
DEP = "agent/plans/PLAN-dep.md"
TODAY = "2026-10-23"
GIT_ENV = {
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_CONFIG_NOSYSTEM": "1",
    "PATH": "/usr/bin:/bin",
}

A_PY = "".join("line %d of a\n" % n for n in range(1, 21))


def plan_text(stamp: str = "", dep: str = "PLAN-dep.md", extra_box: str = "") -> str:
    lines = [
        "# PLAN p",
        "",
        "Status: approved",
        "Depends-On: %s" % dep,
        "Priority: P2 -- fixture plan for the preflight suite",
        "Concurrency: parallel",
        "Owns: pkg/owned/*.py",
    ]
    if stamp:
        lines.append("Revalidated: %s" % stamp)
    lines += [
        "",
        "## Current state",
        "",
        "- The fourth line is src/a.py:4 and the cited module is `src/cited.py`.",
        "",
        "## Tasks",
        "",
        "- [ ] T1 build the first thing in src/a.py",
        "- [ ] T2 build the second thing",
    ]
    if extra_box:
        lines.append(extra_box)
    return "\n".join(lines) + "\n"


def dep_text(
    status: str = "done", boxes: str = "- [x] D1 the dependency box", ruling: str = ""
) -> str:
    head = [
        "# PLAN dep",
        "",
        "Status: %s" % status,
        "Depends-On: no-dep -- the fixture's root plan",
    ]
    if ruling:
        head.append("Ruling: %s" % ruling)
    return "\n".join([*head, "", "## Tasks", "", boxes]) + "\n"


class Repo:
    def __init__(self, root: pathlib.Path):
        self.root = pathlib.Path(root)

    def git(self, *args: str) -> str:
        r = subprocess.run(
            [
                "git",
                "-C",
                str(self.root),
                "-c",
                "user.name=t",
                "-c",
                "user.email=t@t",
                "-c",
                "commit.gpgsign=false",
                "-c",
                "core.hooksPath=/dev/null",
                *args,
            ],
            check=True,
            capture_output=True,
            text=True,
            env=GIT_ENV,
        )
        return r.stdout.strip()

    def write(self, rel: str, text: str) -> None:
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")

    def read(self, rel: str) -> str:
        return (self.root / rel).read_text(encoding="utf-8")

    def has_main(self) -> bool:
        r = subprocess.run(
            [
                "git",
                "-C",
                str(self.root),
                "rev-parse",
                "--verify",
                "--quiet",
                "refs/remotes/origin/main",
            ],
            capture_output=True,
            check=False,
            env=GIT_ENV,
        )
        return r.returncode == 0

    def commit(self, files: dict[str, str], msg: str, main: bool = True) -> str:
        """A BRANCH commit (`main=False`) is an ordinary commit on `work`. A MAIN commit is built on `origin/main` alone, through a scratch index, and `work` is then rebased onto it, so main never holds a branch commit."""
        if not main or not self.has_main():
            for rel, text in files.items():
                self.write(rel, text)
            self.git("add", "-A")
            self.git("commit", "-q", "--allow-empty", "-m", msg)
            sha = self.git("rev-parse", "HEAD")
            if main:
                self.git("update-ref", "refs/remotes/origin/main", sha)
            return sha
        index = self.root.parent / ("index-%s" % self.root.name)
        env = {**GIT_ENV, "GIT_INDEX_FILE": str(index)}

        def plumb(*args: str, stdin: str | None = None) -> str:
            r = subprocess.run(
                ["git", "-C", str(self.root), "-c", "user.name=t", "-c", "user.email=t@t", *args],
                check=True,
                capture_output=True,
                text=True,
                input=stdin,
                env=env,
            )
            return r.stdout.strip()

        plumb("read-tree", "refs/remotes/origin/main")
        for rel, text in files.items():
            blob = plumb("hash-object", "-w", "--stdin", stdin=text)
            plumb("update-index", "--add", "--cacheinfo", "100644,%s,%s" % (blob, rel))
        tree = plumb("write-tree")
        sha = plumb("commit-tree", tree, "-p", "refs/remotes/origin/main", "-m", msg)
        index.unlink()
        self.git("update-ref", "refs/remotes/origin/main", sha)
        self.git("rebase", "-q", "--autostash", "refs/remotes/origin/main")
        return sha


@pytest.fixture
def repo(tmp_path):
    r = Repo(tmp_path / "repo")
    r.root.mkdir()
    r.git("init", "-q", "-b", "work")
    base = r.commit(
        {
            "src/a.py": A_PY,
            "src/cited.py": "x = 1\n",
            "src/unrelated.py": "y = 1\n",
            "pkg/owned/m.py": "z = 1\n",
            "pkg/other/m.py": "w = 1\n",
            DEP: dep_text(),
            PLAN: plan_text(),
        },
        "seed",
    )
    r.commit(
        {PLAN: plan_text("%s @ %s" % (TODAY, base[:12]))},
        "stamp the plan on the branch",
        main=False,
    )
    r.base0 = base
    return r


def state(repo: Repo) -> str:
    return PP.revalidation_state(repo.root, PLAN).state


def row(sig: str, verdict: str, head: str, note: str = "") -> dict:
    return {"plan": PLAN, "sig": sig, "verdict": verdict, "head": head, "note": note}


def no_cites() -> object:
    return PP.CitationReport({"plan": PLAN, "unresolved": [], "drifted": []})


def current_rows(repo: Repo, verdicts: dict[str, str], note: str = "") -> list[dict]:
    head = repo.git("rev-parse", "HEAD")
    boxes = PR.open_boxes(repo.read(PLAN))
    return [row(sig, verdicts.get(body[:2], "absent"), head, note) for _i, _l, body, sig in boxes]


def apply_with(repo: Repo, rows: list[dict], cites=None, deps=None):
    text = repo.read(PLAN)
    base = PP.merge_base(repo.root)
    surveyed = PP.survey(repo.root, PLAN, text, base, rows)
    ov = PP.overlap(repo.root, PLAN, text, base)
    return PP.apply(
        repo.root, PLAN, text, base, surveyed, cites or no_cites(), deps or [], ov, TODAY
    )


# --------------------------------------------------------------------------- freshness


def test_fresh_after_stamp_and_missing_and_unknown(repo, tmp_path):
    assert state(repo) == PP.FRESH
    repo.write(PLAN, plan_text())
    assert state(repo) == PP.MISSING
    bare = Repo(tmp_path / "bare")
    bare.root.mkdir()
    bare.git("init", "-q", "-b", "work")
    bare.commit({PLAN: plan_text("%s @ %s" % (TODAY, "a" * 12))}, "seed", main=False)
    assert PP.revalidation_state(bare.root, PLAN).state == PP.UNKNOWN


def test_main_commit_touching_a_cited_path_makes_the_plan_stale(repo):
    sha = repo.commit({"src/a.py": A_PY + "more\n"}, "main edits a cited file")
    got = PP.revalidation_state(repo.root, PLAN)
    assert got.state == PP.STALE, got
    assert got.commits == (sha,)


def test_main_commit_touching_a_backticked_tracked_path_makes_the_plan_stale(repo):
    repo.commit({"src/cited.py": "x = 2\n"}, "main edits a backticked file")
    assert state(repo) == PP.STALE


def test_control_main_commit_on_an_unrelated_path_stays_fresh(repo):
    repo.commit({"src/unrelated.py": "y = 2\n"}, "main edits an unrelated file")
    assert state(repo) == PP.FRESH


def test_control_branch_only_commit_on_a_cited_path_stays_fresh(repo):
    repo.commit({"src/a.py": A_PY + "branch\n"}, "branch implements", main=False)
    assert state(repo) == PP.FRESH


def test_owns_glob_match_makes_the_plan_stale_and_a_sibling_dir_does_not(repo):
    repo.commit({"pkg/other/m.py": "w = 2\n"}, "main edits a path outside Owns")
    assert state(repo) == PP.FRESH
    repo.commit({"pkg/owned/m.py": "z = 2\n"}, "main edits an owned path")
    assert state(repo) == PP.STALE


def test_dependency_plan_edited_on_main_makes_the_plan_stale(repo):
    repo.commit({DEP: dep_text() + "\nA note.\n"}, "main edits the dependency plan")
    assert state(repo) == PP.STALE
    assert DEP in PP.watched_paths(repo.root, PLAN)


def test_orphan_sha_and_its_ancestor_control(repo):
    branch_sha = repo.commit({"src/unrelated.py": "y = 3\n"}, "branch commit", main=False)
    repo.write(PLAN, plan_text("%s @ %s" % (TODAY, branch_sha[:12])))
    assert state(repo) == PP.ORPHAN
    repo.write(PLAN, plan_text("%s @ %s" % (TODAY, "0" * 12)))
    assert state(repo) == PP.ORPHAN
    repo.write(PLAN, plan_text("%s @ %s" % (TODAY, repo.base0[:12])))
    assert state(repo) == PP.FRESH


# --------------------------------------------------------------------------- survey, overlap and apply


def test_survey_currency_follows_the_merge_base(repo):
    old_head = repo.git("rev-parse", "HEAD")
    rows = current_rows(repo, {})
    assert all(b.current for b in PP.survey(repo.root, PLAN, rows=rows))
    repo.commit({"src/unrelated.py": "y = 4\n"}, "main moves on")
    stale_rows = [dict(r, head=old_head) for r in rows]
    assert not any(b.current for b in PP.survey(repo.root, PLAN, rows=stale_rows))


def test_overlap_lists_main_commits_with_the_plans_they_changed(repo):
    repo.commit(
        {"src/a.py": A_PY + "m\n", DEP: dep_text() + "\nx\n"}, "main: cited file and dep plan"
    )
    repo.commit({"src/unrelated.py": "y = 5\n"}, "main: unrelated")
    ov = PP.overlap(repo.root, PLAN)
    assert ov.total == 1
    assert ov.commits[0].subject == "main: cited file and dep plan"
    assert ov.commits[0].plans == (DEP,)
    capped = PP.overlap(repo.root, PLAN, cap=0)
    assert capped.total == 1
    assert capped.commits == ()


def test_partial_row_writes_a_continuation_line_and_keeps_signatures(repo):
    before = repo.read(PLAN)
    rows = current_rows(
        repo, {"T1": "partial"}, note="the parser half landed; the writer half remains"
    )
    out = apply_with(repo, rows).text
    lines = out.splitlines()
    i = next(n for n, ln in enumerate(lines) if ln.startswith("- [ ] T1"))
    assert (
        lines[i + 1]
        == "    (preflight) %s partial: the parser half landed; the writer half remains" % TODAY
    )
    assert [s for *_x, s in PR.open_boxes(out)] == [s for *_x, s in PR.open_boxes(before)]
    assert PFILE.plan_boxes(out) == PFILE.plan_boxes(before)
    # A second preflight replaces the line rather than stacking a second one.
    repo.write(PLAN, out)
    again = apply_with(
        repo, current_rows(repo, {"T1": "partial"}, note="only the writer half remains")
    ).text
    assert again.count("(preflight)") == 1
    assert "only the writer half remains" in again


def test_control_absent_rows_write_no_continuation_line(repo):
    out = apply_with(repo, current_rows(repo, {})).text
    assert "(preflight)" not in out


def test_apply_stamps_the_header_after_owns_and_one_generated_block(repo):
    repo.write(PLAN, plan_text())
    out = apply_with(repo, current_rows(repo, {})).text
    lines = out.splitlines()
    owns = next(n for n, ln in enumerate(lines) if ln.startswith("Owns:"))
    base = PP.merge_base(repo.root)
    assert lines[owns + 1] == "Revalidated: %s @ %s" % (TODAY, base[:12])
    assert out.count(PP.BEGIN) == 1
    repo.write(PLAN, out)
    again = apply_with(repo, current_rows(repo, {})).text
    assert again.count(PP.BEGIN) == 1
    assert again.count("Revalidated:") == 1
    assert PP.revalidation_state(repo.root, PLAN, again).state == PP.FRESH


def test_present_and_open_box_blocks_write(repo):
    rows = current_rows(repo, {"T2": "present"})
    with pytest.raises(PP.PreflightError, match="present"):
        apply_with(repo, rows)


def test_control_uncovered_box_blocks_and_covered_absent_box_writes(repo):
    rows = current_rows(repo, {})
    with pytest.raises(PP.PreflightError, match="no current investigation row"):
        apply_with(repo, rows[:1])
    assert apply_with(repo, rows).text


# --------------------------------------------------------------------------- dependencies


def dep_levels(repo: Repo) -> list[tuple[str, str]]:
    return [(d.edge, d.level) for d in PP.dep_findings(repo.root, PLAN)]


def test_unfinished_dependency_blocks_and_finished_one_passes(repo):
    assert dep_levels(repo) == [("PLAN-dep.md", PP.OK)]
    repo.commit({DEP: dep_text(status="approved", boxes="- [ ] D1 still open")}, "dep reopened")
    findings = PP.dep_findings(repo.root, PLAN)
    assert [(d.edge, d.level) for d in findings] == [("PLAN-dep.md", PP.BLOCK)]
    with pytest.raises(PP.PreflightError, match=r"dependency PLAN-dep\.md blocks"):
        apply_with(repo, current_rows(repo, {}), deps=findings)


def test_done_dependency_with_open_boxes_warns_unless_ruled(repo):
    repo.commit({DEP: dep_text(status="done", boxes="- [ ] D1 left open")}, "dep done, box open")
    assert dep_levels(repo) == [("PLAN-dep.md", PP.WARN)]
    repo.commit(
        {
            DEP: dep_text(
                status="done", boxes="- [ ] D1 left open", ruling='"drop D1, it is moot" in chat'
            )
        },
        "dep ruled",
    )
    assert dep_levels(repo) == [("PLAN-dep.md", PP.OK)]


def test_dangling_dependency_blocks(repo):
    repo.write(PLAN, plan_text(dep="PLAN-nowhere.md"))
    assert dep_levels(repo) == [("PLAN-nowhere.md", PP.BLOCK)]


# --------------------------------------------------------------------------- citations


def fake_runner(report: dict, rc: int = 0):
    def run(_argv, _root):
        return rc, json.dumps(report), ""

    return run


def test_relocation_rewrites_only_the_line_number(repo):
    text = repo.read(PLAN)
    n = next(i for i, ln in enumerate(text.splitlines(), start=1) if "src/a.py:4" in ln)
    cites = PP.citation_report(
        repo.root,
        PLAN,
        fake_runner(
            {
                "plan": PLAN,
                "unresolved": [],
                "drifted": [{"line": n, "token": "src/a.py:4", "relocate_to": 9, "blocking": True}],
            }
        ),
    )
    assert len(cites.relocations) == 1
    result = apply_with(repo, current_rows(repo, {}), cites=cites)
    old, new = text.splitlines()[n - 1], result.text.splitlines()
    changed = [ln for ln in new if "src/a.py:" in ln and not ln.startswith(" ")]
    assert changed == [old.replace("src/a.py:4", "src/a.py:9")]
    assert result.relocated == ((n, "src/a.py:4", "src/a.py:9"),)


def test_control_unrelocatable_blocking_drift_and_a_box_signature_change_refuse(repo):
    text = repo.read(PLAN)
    n = next(i for i, ln in enumerate(text.splitlines(), start=1) if "src/a.py:4" in ln)
    stuck = PP.citation_report(
        repo.root,
        PLAN,
        fake_runner(
            {
                "plan": PLAN,
                "unresolved": [],
                "drifted": [
                    {"line": n, "token": "src/a.py:4", "relocate_to": None, "blocking": True}
                ],
            },
            rc=1,
        ),
    )
    with pytest.raises(PP.PreflightError, match="nowhere to relocate"):
        apply_with(repo, current_rows(repo, {}), cites=stuck)
    repo.write(PLAN, plan_text(extra_box="- [ ] T3 fix src/a.py:4"))
    box_line = len(plan_text(extra_box="- [ ] T3 fix src/a.py:4").splitlines())
    in_box = PP.citation_report(
        repo.root,
        PLAN,
        fake_runner(
            {
                "plan": PLAN,
                "unresolved": [],
                "drifted": [
                    {"line": box_line, "token": "src/a.py:4", "relocate_to": 9, "blocking": True}
                ],
            }
        ),
    )
    with pytest.raises(PP.PreflightError, match="box's signature"):
        apply_with(repo, current_rows(repo, {}), cites=in_box)


def test_citation_report_fails_closed_on_an_instrument_failure(repo):
    broken = PP.citation_report(repo.root, PLAN, lambda _a, _r: (2, "", "control failed\n"))
    assert broken.error
    assert PP.refusals([], broken, [])
    garbled = PP.citation_report(repo.root, PLAN, lambda _a, _r: (0, "not json", ""))
    assert garbled.error
    clean = PP.citation_report(
        repo.root, PLAN, fake_runner({"plan": PLAN, "unresolved": [], "drifted": []})
    )
    assert not clean.error
    assert not PP.refusals([], clean, [])
