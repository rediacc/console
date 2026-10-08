"""`check:ci-review-resolutions`, driven as a process against throwaway git repositories (agent/plans/PLAN-deferred-findings-block-merge.md, boxes C2 and C3).

EVERY RULE HAS A CASE THAT FAILS WITHOUT IT, and the pairs differ in one thing only. The planted `deferred` and its `fixed` control change nothing but the `Resolution:` line, so a gate that refused every finding, or none, reds one half. The empty-directory cases differ only in what the one branch commit touches, or when it was authored.

THE FIXTURE IS A REAL REPOSITORY, not a mocked walk: `origin/main` is a ref the fixture writes with `git update-ref`, and the branch commits carry the author dates the epoch rule reads. The gate runs as `python3 .ci/scripts/quality/check_review_resolutions.py --root <fixture>`, the same entry point CI calls, with its environment REPLACED rather than overlaid, so a `GITHUB_HEAD_REF` exported by the CI job running this test cannot pick the directory for it.

THE PARITY CORPUS (C3) loads `.claude/hooks/stop/wl_review.py` BY PATH and classifies one list of resolution strings through its `RESOLUTION_RES` and through `review_resolutions.kind_of`. The two parsers are held equal over the corpus instead of one importing the other, so the hook tree keeps no `.ci` import and the gate keeps no hook import.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from typing import TYPE_CHECKING

import pytest

from rediacc_ci import controls, paths
from rediacc_ci.quality import review_resolutions as RR
from rediacc_ci.tests.gates import harness

if TYPE_CHECKING:
    import pathlib

SHIM = paths.from_root(".ci", "scripts", "quality", "check_review_resolutions.py")
WL_REVIEW = paths.from_root(".claude", "hooks", "stop", "wl_review.py")
BRANCH = "feat-1"
ME = "d778be9d"
AT = "2026-10-08T09:00:00Z"
EPOCH = "2026-10-02T07:09:03Z"
AFTER = "2026-10-08T00:00:00Z"
BEFORE = "2026-09-01T00:00:00Z"

FIXED = "fixed %s | %s %s" % ("b" * 40, ME, AT)
DEFERRED = "deferred #abcdef12 | %s %s" % (ME, AT)
WAIVED = "waived #abcdef12 ASKED:2026-10-08T09:14Z | %s %s" % (ME, AT)
NOT_A_BUG = "not-a-bug | the guard at src/a.py:12 already refuses this | %s %s" % (ME, AT)


def _git(repo: pathlib.Path, *args: str, date: str = "") -> None:
    env = controls.fixture_git_env()
    env.update(
        {
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@example.invalid",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@example.invalid",
        }
    )
    if date:
        env["GIT_AUTHOR_DATE"] = date
    result = harness.run(["git", "-C", str(repo), *args], env=env, env_replace=True)
    assert result.rc == 0, harness.render_output(result)


def record(sha: str, findings: list[tuple[str, str]]) -> str:
    """A `.md` record in the shape `wl_review.render` writes (the parts the CI parser reads)."""
    lines = [
        "# Review %s: feat: change" % sha[:8],
        "",
        "Commit: %s" % sha,
        "Repo: console",
        "Branch: %s" % BRANCH,
        "Reviewed-At: %s" % AT,
        "Diff: 100 bytes, 1 files, truncated: no",
        "Unreviewed: (none)",
        "Verdict: %s" % ("findings" if findings else "clean"),
        "Labels: bump=patch kind=bug why=because",
        "",
        "## Findings",
        "",
    ]
    for n, (sev, resolution) in enumerate(findings, start=1):
        lines += [
            "### %s.%d [%s] src/a.py:%d" % (sha[:8], n, sev, n),
            "Anchor: in-diff",
            "Claim: claim %d goes wrong when the list is empty" % n,
            "Resolution: %s" % resolution,
            "",
        ]
    return "\n".join(lines)


class Fixture:
    def __init__(self, root: pathlib.Path) -> None:
        self.repo = root / "repo"
        self.repo.mkdir(parents=True)
        self.n = 0
        _git(self.repo, "init", "-q", "-b", "main")
        cfg = self.repo / RR.CONFIG_REL
        cfg.parent.mkdir(parents=True)
        cfg.write_text(json.dumps({"block_at": "high", "review_epoch": EPOCH}), encoding="utf-8")
        self.commit(".ci/config/commit-review.json", date=BEFORE, write=False)
        _git(self.repo, "update-ref", "refs/remotes/origin/main", "HEAD")
        _git(self.repo, "checkout", "-q", "-b", BRANCH)

    def commit(self, rel: str, *, date: str = AFTER, write: bool = True) -> None:
        self.n += 1
        path = self.repo / rel
        if write:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("change %d\n" % self.n, encoding="utf-8")
        _git(self.repo, "add", "--", rel)
        _git(self.repo, "commit", "-q", "-m", "change %d" % self.n, date=date)

    def plant(self, findings: list[tuple[str, str]], sha: str = "c" * 40) -> pathlib.Path:
        d = self.repo / "agent" / "reviews" / BRANCH
        d.mkdir(parents=True, exist_ok=True)
        path = d / ("%s.md" % sha)
        path.write_text(record(sha, findings), encoding="utf-8")
        return path

    def run(self, **env: str) -> harness.RunResult:
        base = controls.fixture_git_env()
        for name in (
            "GITHUB_HEAD_REF",
            "GITHUB_BASE_REF",
            "GITHUB_EVENT_NAME",
            "GITHUB_STEP_SUMMARY",
        ):
            base.pop(name, None)
        base.update(env)
        return harness.run(
            [sys.executable, str(SHIM), "--root", str(self.repo)], env=base, env_replace=True
        )


@pytest.fixture
def fx(tmp_path: pathlib.Path) -> Fixture:
    f = Fixture(tmp_path)
    f.commit("src/a.py")
    return f


# --------------------------------------------------------------------------- rule i


@pytest.mark.parametrize("severity", ["low", "medium", "high"])
def test_a_deferred_finding_refuses_at_every_severity(gate, fx, severity):
    fx.plant([(severity, DEFERRED)])
    result = fx.run()
    gate.assert_exit(1, result, "a deferred %s must refuse" % severity)
    gate.assert_contains(result.out, "DEFERRED [%s] cccccccc.1 src/a.py:1" % severity)
    gate.assert_contains(result.out, "--triage <me>")
    gate.assert_contains(result.err, "1 deferred")
    gate.log_pass("a deferred %s finding is refused and named" % severity)


@pytest.mark.parametrize("severity", ["low", "medium", "high"])
def test_the_same_finding_fixed_is_clean(gate, fx, severity):
    """The control: only the resolution changes."""
    fx.plant([(severity, FIXED)])
    result = fx.run()
    gate.assert_exit(0, result, "a fixed %s must pass" % severity)
    gate.assert_contains(result.out, "OK branch %s: 1 record(s), 1 finding(s)" % BRANCH)
    gate.assert_contains(result.out, "1 fixed")
    gate.log_pass("the same %s finding marked fixed passes" % severity)


# --------------------------------------------------------------------------- waivers


def test_a_waiver_passes_and_is_listed_in_output_and_step_summary(gate, fx, tmp_path):
    fx.plant([("high", WAIVED), ("medium", NOT_A_BUG)])
    summary = tmp_path / "summary.md"
    result = fx.run(GITHUB_STEP_SUMMARY=str(summary))
    gate.assert_exit(0, result, "a waiver is a resolution")
    gate.assert_contains(
        result.out,
        "WAIVED [high] cccccccc.1 src/a.py:1 -- waived #abcdef12 ASKED:2026-10-08T09:14Z",
    )
    gate.assert_contains(result.out, "1 waiver(s)")
    text = summary.read_text(encoding="utf-8")
    gate.assert_contains(text, "**Waivers (1)**")
    gate.assert_contains(
        text, "`cccccccc.1` [high] `src/a.py:1`: waived #abcdef12 ASKED:2026-10-08T09:14Z"
    )
    gate.log_pass("a waiver passes and is printed in both places")


# --------------------------------------------------------------------------- rule iii


def test_an_unknown_resolution_word_refuses(gate, fx):
    fx.plant([("low", "postponed #abcdef12 | %s %s" % (ME, AT))])
    result = fx.run()
    gate.assert_exit(1, result, "an unknown resolution is not a resolution")
    gate.assert_contains(result.out, "UNREADABLE [low] cccccccc.1")
    gate.assert_contains(result.err, "1 unknown")
    gate.log_pass("an unknown resolution word refuses instead of reading as open")


def test_a_malformed_record_refuses(gate, fx):
    d = fx.repo / "agent" / "reviews" / BRANCH
    d.mkdir(parents=True)
    (d / ("%s.md" % ("d" * 40))).write_text("not a review\n", encoding="utf-8")
    result = fx.run()
    gate.assert_exit(1, result, "a record the parser cannot read may hide a finding")
    gate.assert_contains(result.out, "MALFORMED record agent/reviews/%s/%s.md" % (BRANCH, "d" * 40))
    gate.log_pass("a garbled record refuses")


# --------------------------------------------------------------------------- rule ii


def test_an_open_high_refuses_and_an_open_low_does_not(gate, fx):
    path = fx.plant([("high", "open")])
    result = fx.run()
    gate.assert_exit(1, result, "an open high is at block_at")
    gate.assert_contains(result.out, "OPEN [high] cccccccc.1")
    path.write_text(record("c" * 40, [("low", "open")]), encoding="utf-8")
    result = fx.run()
    gate.assert_exit(0, result, "an open low is below block_at and advisory")
    gate.assert_contains(result.out, "1 open")
    gate.log_pass("block_at is honoured in both directions")


# --------------------------------------------------------------------------- rule iv


def test_an_empty_directory_with_a_reviewable_commit_refuses(gate, fx):
    result = fx.run()
    gate.assert_exit(1, result, "zero records over a reviewable commit is vacuous")
    gate.assert_contains(result.out, "NO RECORDS in agent/reviews/%s/" % BRANCH)
    gate.assert_contains(result.err, "1 reviewable commit(s)")
    gate.log_pass("an empty review directory is not a clean one")


def test_a_clean_ledger_line_counts_as_a_record(gate, fx):
    """The ledger is a record store too, so a branch whose only reviews are clean lines is not vacuous."""
    d = fx.repo / "agent" / "reviews" / BRANCH
    d.mkdir(parents=True)
    line = {
        "v": 1,
        "sha": "e" * 40,
        "repo": "console",
        "branch": BRANCH,
        "subject": "feat: change",
        "verdict": "clean",
        "reviewed_at": AT,
        "labels": {"bump": "patch", "kind": ["bug"], "why": "because"},
    }
    (d / "clean.jsonl").write_text(json.dumps(line) + "\n", encoding="utf-8")
    result = fx.run()
    gate.assert_exit(0, result, "a clean ledger line is a record")
    gate.assert_contains(result.out, "1 record(s), 0 finding(s)")
    gate.log_pass("clean.jsonl lines count toward the record total")


@pytest.mark.parametrize(
    ("label", "rel", "date"),
    [
        ("review-only", "agent/reviews/%s/notes.txt" % BRANCH, AFTER),
        ("before-the-epoch", "src/old.py", BEFORE),
    ],
)
def test_an_empty_directory_with_no_reviewable_commit_passes(gate, tmp_path, label, rel, date):
    fx = Fixture(tmp_path)
    fx.commit(rel, date=date)
    if label == "review-only":
        # The commit's only path is under agent/reviews/, and no `.md` or ledger line exists there.
        assert not list((fx.repo / "agent" / "reviews" / BRANCH).glob("*.md"))
    result = fx.run()
    gate.assert_exit(0, result, "%s: nothing is owed a record" % label)
    gate.assert_contains(result.out, "0 record(s), 0 finding(s)")
    gate.assert_contains(result.out, "0 reviewable commit(s)")
    gate.log_pass("an empty directory over a %s commit passes" % label)


def test_an_unresolvable_base_with_no_records_cannot_run(gate, fx):
    result = fx.run(GITHUB_BASE_REF="no-such-base")
    gate.assert_exit(2, result, "vacuity cannot be measured without a base")
    gate.assert_contains(result.err, "CANNOT RUN")
    gate.assert_contains(result.err, "git fetch origin no-such-base")
    gate.log_pass("no base and no records is exit 2, never a green")


# --------------------------------------------------------------------------- which branch


def test_pull_request_with_no_head_ref_cannot_run(gate, fx):
    fx.plant([("low", FIXED)])
    result = fx.run(GITHUB_EVENT_NAME="pull_request", GITHUB_HEAD_REF="")
    gate.assert_exit(2, result, "the live directory cannot be named")
    gate.assert_contains(result.err, "GITHUB_HEAD_REF is empty")
    gate.log_pass("pull_request without a head ref is CANNOT RUN")


def test_main_locally_is_not_a_pr_branch(gate, fx):
    _git(fx.repo, "checkout", "-q", "main")
    result = fx.run()
    gate.assert_exit(0, result, "main has no PR to judge")
    gate.assert_contains(result.out, RR.NOT_A_PR)
    gate.log_pass("main prints the not-a-PR line and exits 0")


def test_the_head_ref_names_the_directory_even_when_detached(gate, fx):
    """CI may sit on a detached HEAD; GITHUB_HEAD_REF still picks the live directory, and a deferral there still refuses."""
    fx.plant([("low", DEFERRED)])
    _git(fx.repo, "checkout", "-q", "--detach", "HEAD")
    detached = fx.run()
    gate.assert_exit(0, detached, "a detached local HEAD is not a PR branch")
    gate.assert_contains(detached.out, RR.NOT_A_PR)
    result = fx.run(
        GITHUB_EVENT_NAME="pull_request", GITHUB_HEAD_REF=BRANCH, GITHUB_BASE_REF="main"
    )
    gate.assert_exit(1, result, "the head ref selects the directory")
    gate.assert_contains(result.out, "DEFERRED [low] cccccccc.1")
    gate.log_pass("GITHUB_HEAD_REF wins over the checkout")


def test_only_the_live_directory_is_judged(gate, fx):
    """Another branch's deferral is merged history (plan D7), not this branch's refusal."""
    fx.plant([("low", FIXED)])
    other = fx.repo / "agent" / "reviews" / "1007-1"
    other.mkdir(parents=True)
    (other / ("%s.md" % ("f" * 40))).write_text(
        record("f" * 40, [("high", DEFERRED)]), encoding="utf-8"
    )
    result = fx.run()
    gate.assert_exit(0, result, "history is not judged")
    gate.log_pass("a deferral in another branch's directory is ignored")


# --------------------------------------------------------------------------- the selftest


def test_selftest_exits_zero_and_counts_its_controls(gate):
    result = harness.run([sys.executable, str(SHIM), "--selftest"])
    gate.assert_exit(0, result, "the selftest")
    count = int(result.out.strip().splitlines()[-1].split(" control(s)")[0])
    gate.assert_eq(count >= 37, True, "the selftest ran at least its floor of controls")
    gate.log_pass("the selftest passes %d controls" % count)


# --------------------------------------------------------------------------- C3: local/CI parity

PARITY_CORPUS = (
    # Every legal kind.
    "open",
    FIXED,
    NOT_A_BUG,
    "not-a-bug | the existence oracle refuted the claim | oracle %s" % AT,
    WAIVED,
    # The legacy deferral: still parsed, so merged history is not malformed.
    DEFERRED,
    # Four malformed shapes.
    "deferred #abcdef12",
    "waived #abcdef12 | %s %s" % (ME, AT),
    "fixed abc1234 | %s %s" % (ME, AT),
    "postponed #abcdef12 | %s %s" % (ME, AT),
)


def _load_wl_review():
    hooks = WL_REVIEW.parent
    paths.on_sys_path(hooks)
    spec = importlib.util.spec_from_file_location("wl_review_parity", WL_REVIEW)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Registered before it runs: a dataclass resolves its annotations through sys.modules[cls.__module__].
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _local_kind(wl, text: str) -> str:
    return _classify(wl.RESOLUTION_RES, text)


def _classify(grammar, text: str) -> str:
    for kind, rx in grammar:
        if rx.match(text):
            return kind
    return ""


def test_local_and_ci_classify_the_corpus_identically(gate):
    wl = _load_wl_review()
    gate.assert_eq(
        sorted(kind for kind, _rx in wl.RESOLUTION_RES),
        sorted(RR.KINDS),
        "the two grammars name the same kinds",
    )
    for text in PARITY_CORPUS:
        gate.assert_eq(_local_kind(wl, text), RR.kind_of(text), "parity on %r" % text)
    # The control: a local grammar without `waived` must disagree on the corpus, or the corpus is not exercising the kind this plan added.
    stripped = tuple((k, rx) for k, rx in wl.RESOLUTION_RES if k != "waived")
    gate.assert_eq(
        [t for t in PARITY_CORPUS if _classify(stripped, t) != RR.kind_of(t)],
        [WAIVED],
        "dropping waived from the local grammar breaks parity on exactly the waiver",
    )
    kinds = {RR.kind_of(t) for t in PARITY_CORPUS}
    gate.assert_eq(
        kinds, {*RR.KINDS, ""}, "the corpus exercises every kind and the malformed shape"
    )
    gate.log_pass(
        "wl_review.RESOLUTION_RES and review_resolutions.kind_of agree on %d strings"
        % len(PARITY_CORPUS)
    )
