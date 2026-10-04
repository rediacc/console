"""`rediacc_ci.review.review_table`: the per-commit review records rendered on the PR page (agent/plans/PLAN-github-pr-review-restore.md, box GR5).

No case touches the network: `publish` takes the `gh` runner as a seam, and a recording fake answers the reads and records the writes. Records are written by the reviewer's own `wl_review.render`, so the parser is held to the format the reviewer really writes.
"""

import pathlib

from rediacc_ci import paths
from rediacc_ci.quality import review_comments
from rediacc_ci.review import review_table as T
from rediacc_ci.well_known import GH_ORIGIN, GH_REPO

paths.on_sys_path(paths.hooks_stop_dir())
import wl_review  # noqa: E402

BRANCH = "1003-1"
ME = "d778be9d"
AT = "2026-10-03T05:01:59Z"


def sha(n: int) -> str:
    return ("%x" % n) * 40 if n < 16 else ("%040x" % n)


def make(
    n: int,
    verdict: str = "clean",
    bump: str = "patch",
    kinds=("bug",),
    findings=(),
    repo: str = "console",
    subject: str = "",
    at: str = "",
) -> "wl_review.Review":
    s = sha(n)
    rev = wl_review.Review(
        sha=s,
        subject=subject or "fix: commit %d" % n,
        repo=repo,
        branch=BRANCH,
        reviewed_at=at or "2026-10-03T00:00:%02dZ" % n,
        model="m",
        diff_bytes=10,
        diff_files=2,
        verdict=verdict,
        labels=None
        if verdict.startswith(("skipped", "failed"))
        else {"bump": bump, "kind": list(kinds), "why": "because"},
    )
    for i, (sev, res) in enumerate(findings, start=1):
        rev.findings.append(
            wl_review.Finding(
                id="%s.%d" % (s[:8], i),
                severity=sev,
                file="src/a.py",
                line=10 + i,
                anchor="in-diff",
                claim="claim %d of %s goes wrong when x" % (i, s[:8]),
                resolution=res,
            )
        )
    return rev


def plant(root: pathlib.Path, *reviews) -> None:
    d = root / "agent" / "reviews" / BRANCH
    d.mkdir(parents=True, exist_ok=True)
    for rev in reviews:
        (d / ("%s.md" % rev.sha)).write_text(wl_review.render(rev), encoding="utf-8")


def fixed(n: int) -> str:
    return "fixed %s | %s %s" % (sha(n), ME, AT)


NAB = "not-a-bug | the guard at src/a.py:12 already refuses this case | %s %s" % (ME, AT)
DEFERRED = "deferred #76a0eaaf | %s %s" % (ME, AT)


class FakeGh:
    def __init__(self, commits=(), existing=(), fail_all=False, fail_commits=False):
        self.commits = list(commits)
        self.existing = list(existing)
        self.fail_all = fail_all
        self.fail_commits = fail_commits
        self.calls: list[list[str]] = []
        self.bodies: list[str] = []

    def __call__(self, args):
        self.calls.append(list(args))
        if self.fail_all:
            return 1, ""
        joined = " ".join(args)
        if "/commits" in joined and "pulls/" in joined:
            if self.fail_commits:
                return 1, ""
            return 0, "\n".join("%s %s" % c for c in self.commits)
        if "startswith" in joined:
            return 0, "\n".join(self.existing)
        for a in args:
            if a.startswith("body=@"):
                self.bodies.append(pathlib.Path(a[len("body=@") :]).read_text(encoding="utf-8"))
        return 0, ""

    def writes(self):
        return [c for c in self.calls if "-X" in c]


def env(**extra):
    base = {
        "PR_NUMBER": "7",
        "HEAD_REF": BRANCH,
        "HEAD_SHA": "f" * 40,
        "GITHUB_REPOSITORY": GH_REPO,
    }
    base.update(extra)
    return base


def render_dir(root, commits=None):
    ctx = T.Context(branch=BRANCH, head="f" * 40, repo=GH_REPO, commits=commits)
    return T.render(ctx, T.load_records(root, BRANCH), T.branch_verdicts(root, BRANCH))


# --------------------------------------------------------------------------- the contract


def test_contract_render_and_parse_back():
    rev = make(1, verdict="findings", findings=[("high", fixed(2)), ("low", NAB)])
    rec = T.parse_record(wl_review.render(rev), "%s.md" % rev.sha)
    assert rec.problem == ""
    assert rec.sha == rev.sha
    assert rec.subject == rev.subject
    assert rec.repo == "console"
    assert rec.verdict == "findings"
    assert rec.bump == "patch"
    assert rec.diff_files == 2
    assert [(f.id, f.severity, f.path, f.line) for f in rec.findings] == [
        (f.id, f.severity, f.file, f.line) for f in rev.findings
    ]
    assert [f.claim for f in rec.findings] == [f.claim for f in rev.findings]
    assert [f.resolution_kind for f in rec.findings] == ["fixed", "not-a-bug"]
    # Every record the reviewer can write parses back with the same verdict.
    for verdict in ("clean", "skipped (gitlink-only)", "failed (timeout)"):
        assert T.parse_record(wl_review.render(make(3, verdict=verdict))).verdict == verdict


def test_a_garbled_record_still_gets_a_row_marked_malformed(tmp_path):
    d = tmp_path / "agent" / "reviews" / BRANCH
    d.mkdir(parents=True)
    (d / ("%s.md" % sha(9))).write_text("not a review\n", encoding="utf-8")
    body = render_dir(tmp_path)
    assert "malformed" in body
    assert sha(9)[:8] in body


# --------------------------------------------------------------------------- content


def test_mixed_resolutions_are_counted(tmp_path):
    plant(
        tmp_path,
        make(
            1,
            verdict="findings",
            findings=[("high", fixed(2)), ("medium", NAB), ("low", DEFERRED), ("low", "open")],
        ),
    )
    body = render_dir(tmp_path)
    assert "fixed 1, not-a-bug 1, deferred 1, open 1" in body
    assert "1 high, 1 medium, 2 low" in body
    assert "4 finding(s), 1 open" in body
    # Control: a clean record shows no resolutions at all.
    plant(tmp_path, make(5))
    line = next(ln for ln in render_dir(tmp_path).split("\n") if sha(5)[:8] + "`](" in ln)
    assert "| clean | - | - |" in line


def test_skipped_and_failed_verdicts_have_rows_without_coverage(tmp_path):
    plant(tmp_path, make(1, verdict="skipped (gitlink-only)"), make(2, verdict="failed (timeout)"))
    body = render_dir(tmp_path)
    assert "| skipped (gitlink-only) | - | - | (none) | - |" in body
    assert "| failed (timeout) | - | - | (none) | - |" in body
    assert "no labelled verdicts" in body


def test_submodule_record_gets_its_own_section_and_is_never_superseded(tmp_path):
    plant(tmp_path, make(1), make(2, repo="private/renet", subject="fix(ceph): pin"))
    body = render_dir(tmp_path, commits=[T.Commit(sha(1), "fix: commit 1")])
    sub = body.split("### Submodule commits", 1)[1]
    assert "fix(ceph): pin" in sub
    assert "Superseded" not in body


def test_missing_record_beside_a_review_records_commit(tmp_path):
    plant(tmp_path, make(1))
    commits = [
        T.Commit(sha(1), "fix: commit 1"),
        T.Commit(sha(2), "chore(reviews): record reviews for 1111111"),
        T.Commit(sha(3), "feat: never reviewed"),
    ]
    body = render_dir(tmp_path, commits=commits)
    section = body.split("### PR commits with no record", 1)[1]
    assert (
        "`%s` chore(reviews): record reviews for 1111111: review records only, not reviewed by design"
        % sha(2)[:8]
        in section
    )
    assert "`%s` feat: never reviewed: no record" % sha(3)[:8] in section


def test_superseded_record_is_listed(tmp_path):
    plant(tmp_path, make(1), make(4, subject="fix: before the rebase"))
    body = render_dir(tmp_path, commits=[T.Commit(sha(1), "fix: commit 1")])
    sup = body.split("### Superseded (rebased)", 1)[1]
    assert "fix: before the rebase" in sup
    # Control: with no commit list nothing is called superseded.
    assert "Superseded" not in render_dir(tmp_path)


def test_at_the_api_cap_coverage_is_unknown_and_nothing_is_superseded(tmp_path):
    plant(tmp_path, make(1), make(4))
    commits = [T.Commit("%040x" % (1000 + i), "c") for i in range(T.COMMITS_API_CAP)]
    body = render_dir(tmp_path, commits=commits)
    assert "coverage is unknown" in body
    assert "Superseded" not in body


def test_header_names_the_bump_and_the_commit_that_earned_it(tmp_path):
    plant(
        tmp_path,
        make(1, bump="patch"),
        make(2, bump="minor", kinds=("feature",), subject="feat: the minor one"),
        make(3, bump="none", kinds=("docs",)),
    )
    body = render_dir(tmp_path)
    assert "Bump: **bump-minor**, earned by `%s` (feat: the minor one)" % sha(2)[:8] in body
    assert "enhancement" in body
    link = (
        GH_ORIGIN
        + "/"
        + GH_REPO
        + "/blob/%s/agent/reviews/%s/%s.md"
        % (
            "f" * 40,
            BRANCH,
            sha(1),
        )
    )
    assert link in body
    assert GH_ORIGIN + "/" + GH_REPO + "/tree/%s/agent/reviews/%s" % ("f" * 40, BRANCH) in body


def test_details_clip_the_claim(tmp_path):
    rev = make(1, verdict="findings", findings=[("high", "open")])
    rev.findings[0].claim = "x" * 600
    plant(tmp_path, rev)
    body = render_dir(tmp_path)
    assert "<details>" in body
    assert "x" * 297 + "..." in body
    assert "x" * 301 not in body


def test_an_oversize_body_is_truncated_below_the_limit(tmp_path):
    reviews = []
    for n in range(1, 400):
        rev = make(
            n, verdict="findings", findings=[("medium", "open")] * 6, subject="fix: " + "s" * 150
        )
        for f in rev.findings:
            f.claim = "c" * 590
        reviews.append(rev)
    plant(tmp_path, *reviews)
    body = render_dir(tmp_path)
    assert len(body) < T.BODY_LIMIT
    assert body.startswith(T.MARKER_PREFIX)
    assert "Truncated to fit GitHub's comment limit" in body
    # Control: a small branch is not truncated.
    small = tmp_path / "small"
    plant(small, make(1))
    assert "Truncated" not in render_dir(small)


def test_the_last_resort_cut_keeps_the_whole_marker_line():
    marker = "%s %s -->" % (T.MARKER_PREFIX, sha(1))
    ctx = T.Context(branch="b", head=sha(1), repo=GH_REPO, commits=None)
    # A header alone over the budget forces the final `body[: BODY_LIMIT - 1]` cut, after every block and row is gone.
    body = T._fit(ctx, [marker, "h" * (T.BODY_LIMIT + 10)], ["| row |"], ["", "### s"], ["block"])
    assert len(body) == T.BODY_LIMIT - 1
    assert body.split("\n", 1)[0] == marker
    # Control: under the budget nothing is cut.
    assert T._fit(ctx, [marker, "h"], [], [], []).split("\n", 1)[0] == marker


def test_details_go_before_table_rows(tmp_path):
    reviews = []
    for n in range(1, 60):
        rev = make(n, verdict="findings", findings=[("low", "open")] * 8)
        for f in rev.findings:
            f.claim = "c" * 590
        reviews.append(rev)
    plant(tmp_path, *reviews)
    body = render_dir(tmp_path)
    assert "finding block(s) omitted" in body
    assert sum(1 for ln in body.split("\n") if ln.startswith("| [`")) == 59


def test_the_body_is_invisible_to_the_review_gate(tmp_path):
    plant(tmp_path, make(1, verdict="findings", findings=[("high", "open")]))
    body = render_dir(tmp_path)
    assert body.startswith("<!--")
    assert "json:review-findings" not in body
    assert not review_comments.VERDICT_HEADING.search(body)
    comment = {"user": {"login": "github-actions[bot]"}, "body": body, "created_at": "x"}
    assert review_comments.newest_summary([comment]) is None
    # Control: the same body without the marker line WOULD be selected once it carries the fence.
    loud = {
        "user": {"login": "github-actions[bot]"},
        "body": "json:review-findings\n",
        "created_at": "x",
    }
    assert review_comments.newest_summary([loud]) is loud


# --------------------------------------------------------------------------- publish


def test_upsert_patches_the_existing_marker_comment(tmp_path):
    plant(tmp_path, make(1))
    gh = FakeGh(commits=[(sha(1), "fix: commit 1")], existing=["555"])
    assert T.publish(env(), tmp_path, gh=gh) == 0
    writes = gh.writes()
    assert len(writes) == 1
    assert writes[0][:4] == ["api", "-X", "PATCH", "repos/" + GH_REPO + "/issues/comments/555"]
    assert gh.bodies[0].startswith("%s %s -->" % (T.MARKER_PREFIX, "f" * 40))


def test_upsert_posts_when_no_marker_comment_exists(tmp_path):
    plant(tmp_path, make(1))
    gh = FakeGh(commits=[(sha(1), "fix: commit 1")])
    T.publish(env(), tmp_path, gh=gh)
    assert gh.writes()[0][:4] == ["api", "-X", "POST", "repos/" + GH_REPO + "/issues/7/comments"]


def test_step_summary_gets_the_same_markdown(tmp_path):
    plant(tmp_path, make(1))
    summary = tmp_path / "summary.md"
    gh = FakeGh(commits=[(sha(1), "fix: commit 1")])
    T.publish(env(GITHUB_STEP_SUMMARY=str(summary)), tmp_path, gh=gh)
    assert summary.read_text(encoding="utf-8").strip() == gh.bodies[0].strip()


def test_a_gh_failure_exits_0(tmp_path):
    plant(tmp_path, make(1))
    gh = FakeGh(fail_all=True)
    assert T.publish(env(), tmp_path, gh=gh) == 0
    assert gh.writes() == []


def test_an_unreadable_commit_list_still_posts_every_record(tmp_path):
    plant(tmp_path, make(1), make(2))
    gh = FakeGh(fail_commits=True)
    assert T.publish(env(), tmp_path, gh=gh) == 0
    assert sum(1 for ln in gh.bodies[0].split("\n") if ln.startswith("| [`")) == 2


def test_missing_env_posts_nothing(tmp_path):
    gh = FakeGh()
    assert T.publish({}, tmp_path, gh=gh) == 0
    assert gh.calls == []


def test_main_swallows_a_crash(monkeypatch):
    def boom(*_a, **_k):
        raise RuntimeError("x")

    monkeypatch.setattr(T, "publish", boom)
    assert T.main([]) == 0


def test_render_only_uses_the_local_commit_list(tmp_path):
    plant(tmp_path, make(1), make(2))

    def git(args):
        if args[:2] == ["rev-parse", "--abbrev-ref"]:
            return 0, BRANCH
        if args[:2] == ["rev-parse", "--verify"]:
            return 0, "x"
        return 0, "%s fix: commit 1" % sha(1)

    body = T.render_only(BRANCH, tmp_path, git=git)
    assert "Superseded" in body
    assert "<!-- per-commit-reviews: local -->" in body

    def nogit(_args):
        return 1, ""

    assert "Superseded" not in T.render_only(BRANCH, tmp_path, git=nogit)


# --------------------------------------------------------------------------- the clean ledger (agent/plans/PLAN-clean-review-ledger.md T10)


def plant_ledger(root: pathlib.Path, *reviews) -> None:
    for rev in reviews:
        assert wl_review.append_clean(root, BRANCH, rev)


def test_contract_a_ledger_line_parses_to_the_same_record(tmp_path):
    rev = make(1, bump="minor", kinds=("feature",))
    plant_ledger(tmp_path, rev)
    (rec,) = T.load_records(tmp_path, BRANCH)
    md = T.parse_record(wl_review.render(rev), "%s.md" % rev.sha)
    for field in ("sha", "subject", "repo", "verdict", "reviewed_at", "diff_files", "bump"):
        assert getattr(rec, field) == getattr(md, field), field
    assert (rec.file, rec.line, rec.findings, rec.problem) == ("clean.jsonl", 1, [], "")
    assert T.labels_cell(rec) == T.labels_cell(md)


def test_a_ledger_row_shows_full_coverage_and_links_its_line(tmp_path):
    plant_ledger(tmp_path, make(1), make(2))
    body = render_dir(tmp_path, commits=[T.Commit(sha(1), "fix: commit 1"), T.Commit(sha(2), "x")])
    line = next(ln for ln in body.split("\n") if sha(2)[:8] + "`](" in ln)
    assert line.endswith("| full |"), line
    link = (
        GH_ORIGIN + "/" + GH_REPO + "/blob/%s/agent/reviews/%s/clean.jsonl#L2" % ("f" * 40, BRANCH)
    )
    assert "(%s)" % link in line, line
    assert "PR commits with no record" not in body


def test_control_without_the_ledger_the_commit_has_no_record(tmp_path, monkeypatch):
    """CONTROL: a `load_records` that skipped the ledger would move the commit to "PR commits with no record"."""
    plant_ledger(tmp_path, make(1))
    monkeypatch.setattr(T.clean_ledger, "read", lambda _p: [])
    body = render_dir(tmp_path, commits=[T.Commit(sha(1), "fix: commit 1")])
    assert "`%s` fix: commit 1: no record" % sha(1)[:8] in body


def test_a_superseded_ledger_record_is_still_listed(tmp_path):
    plant_ledger(tmp_path, make(1), make(4, subject="fix: before the rebase"))
    body = render_dir(tmp_path, commits=[T.Commit(sha(1), "fix: commit 1")])
    sup = body.split("### Superseded (rebased)", 1)[1]
    assert "fix: before the rebase" in sup
    assert "clean.jsonl#L2" in sup


def test_an_md_record_wins_over_a_ledger_line_for_its_sha(tmp_path):
    plant(tmp_path, make(1, verdict="findings", findings=[("low", "open")]))
    plant_ledger(tmp_path, make(1))
    records = T.load_records(tmp_path, BRANCH)
    assert [(r.sha, r.verdict) for r in records] == [(sha(1), "findings")]


def test_branch_verdicts_is_pr_labels_verdicts(tmp_path):
    plant(tmp_path, make(1, bump="patch"))
    plant_ledger(tmp_path, make(2, bump="minor", kinds=("feature",)))
    assert T.branch_verdicts(tmp_path, BRANCH) == T.pr_labels.verdicts(tmp_path, BRANCH)
    assert sorted(v["bump"] for v in T.branch_verdicts(tmp_path, BRANCH)) == ["minor", "patch"]


def test_records_from_files_and_the_ledger_are_in_sha_order(tmp_path):
    """The header names the first record, in sha order, that earned the bump: the same commit before and after a record moves into the ledger."""
    plant(tmp_path, make(5, bump="minor", kinds=("feature",), subject="feat: the file"))
    plant_ledger(tmp_path, make(2, bump="minor", kinds=("feature",), subject="feat: the line"))
    assert [r.sha for r in T.load_records(tmp_path, BRANCH)] == [sha(2), sha(5)]
    assert "earned by `%s` (feat: the line)" % sha(2)[:8] in render_dir(tmp_path)
