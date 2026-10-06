"""`rediacc_ci.review.pr_labels`: PR labels from the per-commit review records (agent/plans/PLAN-per-commit-review.md section 8).

No case touches the network: `apply` takes the `gh` runner as a seam, and a recording fake answers the reads and counts the writes. Review files are real files in the reviewer's format under a temporary `agent/reviews/<branch>/`.
"""

import json
import pathlib

from rediacc_ci.review import pr_labels as L

BRANCH = "0930-1"


def review(verdict="clean", bump="patch", kinds="bug"):
    return (
        "# Review aaaaaaaa: x\n\nCommit: %s\nRepo: console\nBranch: %s\nVerdict: %s\nLabels: bump=%s kind=%s why=because\n"
        % ("a" * 40, BRANCH, verdict, bump, kinds)
    )


def plant(root: pathlib.Path, *files):
    d = root / "agent" / "reviews" / BRANCH
    d.mkdir(parents=True, exist_ok=True)
    for n, text in enumerate(files):
        (d / ("%040d.md" % n)).write_text(text, encoding="utf-8")


class FakeGh:
    def __init__(self, changed=("src/a.ts",), ledger=""):
        self.changed = list(changed)
        self.ledger = ledger
        self.calls = []

    def __call__(self, args):
        self.calls.append(args)
        joined = " ".join(args)
        if "/files" in joined:
            return 0, "\n".join(self.changed)
        if "startswith" in joined:
            if not self.ledger:
                return 0, ""
            return 0, "77 <!-- claude-labels: abc -->\napplied: %s" % self.ledger
        if args[:2] == ["api", "repos/o/r/labels/ci"] or args[:2] == [
            "api",
            "repos/o/r/labels/bump-none",
        ]:
            return 0, "{}"
        return 0, ""

    def applied(self):
        return [a[-1].split("=", 1)[1] for a in self.calls if "labels[]" in " ".join(a)]

    def removed(self):
        return [a[3].rsplit("/", 1)[1] for a in self.calls if a[:3] == ["api", "-X", "DELETE"]]

    def ledger_body(self):
        for a in self.calls:
            if a[-1].startswith("body="):
                return a[-1]
        return ""


ENV = {"PR_NUMBER": "591", "HEAD_REF": BRANCH, "HEAD_SHA": "f" * 40, "GITHUB_REPOSITORY": "o/r"}


def run(tmp_path, gh):
    assert L.apply(dict(ENV), tmp_path, gh=gh) == 0
    return gh


def test_the_highest_bump_wins_whatever_the_commit_order(tmp_path):
    plant(tmp_path, review(bump="minor", kinds="feature"), review(bump="patch", kinds="bug"))
    gh = run(tmp_path, FakeGh())
    assert "bump-minor" in gh.applied()
    assert set(gh.applied()) >= {"enhancement", "bug"}


def test_control_last_wins_would_be_wrong(tmp_path):
    """The order case above is only a test if the LAST verdict is the weaker one."""
    plant(tmp_path, review(bump="minor"), review(bump="patch"))
    found = L.verdicts(tmp_path, BRANCH)
    assert found[-1]["bump"] == "patch"


def test_every_commit_none_is_bump_none(tmp_path):
    plant(tmp_path, review(bump="none", kinds="docs"), review(bump="none", kinds="none"))
    gh = run(tmp_path, FakeGh())
    assert "bump-none" in gh.applied()
    assert "documentation" in gh.applied()


def test_one_release_worthy_commit_removes_a_ledgered_bump_none(tmp_path):
    plant(tmp_path, review(bump="none"), review(bump="patch"))
    gh = run(tmp_path, FakeGh(ledger="bump-none,bug"))
    assert "bump-none" in gh.removed()
    assert "bump-none" not in gh.applied()
    assert "applied: bug" in gh.ledger_body()


def test_major_is_applied_and_is_the_only_bump_label(tmp_path):
    """Operator ruling 2026-10-02: bump-major is applied automatically, and it replaces a ledgered bump-minor rather than joining it."""
    plant(
        tmp_path, review(bump="minor"), review(bump="major", kinds="feature"), review(bump="patch")
    )
    gh = run(tmp_path, FakeGh(ledger="bump-minor"))
    assert [x for x in gh.applied() if x.startswith("bump-")] == ["bump-major"]
    assert "bump-minor" in gh.removed()
    _labels, note = L.aggregate(L.verdicts(tmp_path, BRANCH))
    assert "bump-major applied" in note


def test_patch_is_the_default_and_carries_no_bump_label(tmp_path):
    plant(tmp_path, review(bump="none"), review(bump="patch"))
    gh = run(tmp_path, FakeGh())
    assert not [x for x in gh.applied() if x.startswith("bump-")]


def test_a_hand_applied_or_unmanaged_label_is_never_removed(tmp_path):
    plant(tmp_path, review(bump="patch", kinds="bug"))
    gh = run(tmp_path, FakeGh(ledger="rollback,full-ci,bug"))
    assert gh.removed() == []


def test_failed_and_skipped_reviews_cast_no_vote(tmp_path):
    plant(
        tmp_path,
        review(verdict="failed (model call timed out after 240s)", bump="minor"),
        review(verdict="skipped (gitlink-only)", bump="minor"),
    )
    assert L.verdicts(tmp_path, BRANCH) == []


def test_the_mechanical_floor_needs_no_review(tmp_path):
    gh = run(tmp_path, FakeGh(changed=[".github/workflows/ci.yml", ".ci/x.py"]))
    assert gh.applied() == ["ci"]


def test_missing_inputs_apply_nothing_and_still_exit_zero(tmp_path):
    gh = FakeGh()
    assert L.apply({}, tmp_path, gh=gh) == 0
    assert gh.calls == []


def test_the_whitelist_matches_the_declared_create_on_demand_rows():
    for row in L.CREATE_ON_DEMAND_LABELS:
        assert row.split("|", 1)[0] in L.MANAGED_LABELS


# --------------------------------------------------------------------------- the clean ledger (agent/plans/PLAN-clean-review-ledger.md T9)


def ledger_line(n, verdict="clean", bump="patch", kinds=("bug",)):
    labels = None if verdict != "clean" else {"bump": bump, "kind": list(kinds), "why": "w"}
    return (
        json.dumps(
            {
                "attempt": 1,
                "branch": BRANCH,
                "cost": None,
                "diff": {"bytes": 1, "files": 1},
                "labels": labels,
                "model": "m",
                "parent": "(root)",
                "patch_id": "(none)",
                "repo": "console",
                "reviewed_at": "2026-10-04T00:00:00Z",
                "sha": "%040d" % (100 + n),
                "subject": "s",
                "v": 1,
                "verdict": verdict,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    )


def plant_ledger(root: pathlib.Path, *lines):
    d = root / "agent" / "reviews" / BRANCH
    d.mkdir(parents=True, exist_ok=True)
    (d / "clean.jsonl").write_text("".join(lines), encoding="utf-8")


def test_a_ledger_only_minor_earns_bump_minor(tmp_path):
    plant_ledger(tmp_path, ledger_line(1, bump="minor", kinds=("feature",)), ledger_line(2))
    gh = run(tmp_path, FakeGh())
    assert "bump-minor" in gh.applied()
    assert "enhancement" in gh.applied()


def test_all_none_across_files_and_the_ledger_is_bump_none(tmp_path):
    plant(tmp_path, review(bump="none", kinds="docs"))
    plant_ledger(tmp_path, ledger_line(1, bump="none", kinds=()))
    assert len(L.verdicts(tmp_path, BRANCH)) == 2
    gh = run(tmp_path, FakeGh())
    assert "bump-none" in gh.applied()


def test_control_one_ledger_patch_beside_none_files_is_not_bump_none(tmp_path):
    """CONTROL: the ledger's vote is counted, so a patch line removes bump-none."""
    plant(tmp_path, review(bump="none", kinds="docs"))
    plant_ledger(tmp_path, ledger_line(1, bump="patch"))
    gh = run(tmp_path, FakeGh())
    assert "bump-none" not in gh.applied()


def test_a_skipped_ledger_line_casts_no_vote(tmp_path):
    plant_ledger(tmp_path, ledger_line(1, verdict="skipped (gitlink-only)"))
    assert L.verdicts(tmp_path, BRANCH) == []


def test_an_md_record_beats_the_ledger_line_for_its_sha(tmp_path):
    d = tmp_path / "agent" / "reviews" / BRANCH
    d.mkdir(parents=True)
    (d / ("%040d.md" % 101)).write_text(review(bump="patch"), encoding="utf-8")
    plant_ledger(tmp_path, ledger_line(1, bump="major"))
    assert [v["bump"] for v in L.verdicts(tmp_path, BRANCH)] == ["patch"]


def test_verdicts_only_prints_labels_note_and_count(tmp_path, monkeypatch, capsys):
    plant_ledger(tmp_path, ledger_line(1, bump="minor", kinds=("feature",)))
    monkeypatch.setattr(L.paths, "repo_root", lambda: tmp_path)
    assert L.main(["--verdicts-only", "--branch", BRANCH]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "labels": ["bump-minor", "enhancement"],
        "n": 1,
        "note": "",
    }
    assert L.main(["--verdicts-only"]) == 2


def test_verdicts_merge_files_and_ledger_in_sha_order(tmp_path):
    """Moving a record into the ledger must not reorder the kind labels: the merged list is in sha order, the order the `.md` files alone sorted in (the migration's byte-identity proof depends on it)."""
    d = tmp_path / "agent" / "reviews" / BRANCH
    d.mkdir(parents=True)
    (d / ("%040d.md" % 900)).write_text(review(bump="patch", kinds="docs"), encoding="utf-8")
    plant_ledger(tmp_path, ledger_line(1, bump="patch", kinds=("ci",)))
    assert [v["kind"] for v in L.verdicts(tmp_path, BRANCH)] == [["ci"], ["docs"]]
    labels, _note = L.aggregate(L.verdicts(tmp_path, BRANCH))
    assert labels == ["ci", "documentation"]


# --------------------------------------------------------------------------- transient read retry (PLAN-gh-retry G12) ---------------------------------------------------------------------------


def _flaky_files(failures, text):
    """A FakeGh whose changed-file READ fails `failures` times with `text` first."""

    class Flaky(FakeGh):
        left = failures

        def __call__(self, args):
            if "/files" in " ".join(args) and self.left > 0:
                self.left -= 1
                self.calls.append(args)
                return 1, text
            return super().__call__(args)

    return Flaky()


def test_a_502_on_the_changed_file_list_is_retried(tmp_path, monkeypatch):
    slept: list[float] = []
    monkeypatch.setattr(L, "_sleep", slept.append)
    gh = run(tmp_path, _flaky_files(1, "gh: Server Error (HTTP 502)"))
    assert slept == [5.0]
    assert sum("/files" in " ".join(a) for a in gh.calls) == 2


def test_a_persistent_5xx_leaves_the_changed_list_empty_and_still_returns_0(tmp_path, monkeypatch):
    slept: list[float] = []
    monkeypatch.setattr(L, "_sleep", slept.append)
    gh = run(tmp_path, _flaky_files(9, "gh: Server Error (HTTP 503)"))
    assert slept == [5.0, 15.0]
    assert sum("/files" in " ".join(a) for a in gh.calls) == 3


def test_a_404_on_the_changed_file_list_is_not_retried(tmp_path, monkeypatch):
    slept: list[float] = []
    monkeypatch.setattr(L, "_sleep", slept.append)
    gh = run(tmp_path, _flaky_files(9, "gh: Not Found (HTTP 404)"))
    assert slept == []
    assert sum("/files" in " ".join(a) for a in gh.calls) == 1
