"""`rediacc_ci.review.claude_review_gate`: the advisory PR-level review gate (agent/plans/PLAN-github-pr-review-restore.md, box GR1).

No case touches the network. `FakeGh` replaces the module's `_gh_call` seam, answers each read by the shape of its argv (the endpoint plus the `--jq` program the gate sends), records every write, and can fail any named read. Every go=false case has a silent control beside it that differs in the one planted fact and decides go=true, so a gate that always refused would fail half of them.
"""

import json
import pathlib

import pytest

from rediacc_ci.core import common, review_budget
from rediacc_ci.review import claude_review_gate as G

REPO = "o/r"
PR = "42"
HEAD = "a" * 40
OLD = "b" * 40
BRANCH = "0930-1"


class FakeGh:
    """Reads answered by argv shape; writes recorded. `fail` names reads that exit 1 on every attempt."""

    def __init__(self, **state):
        self.draft = state.get("draft", False)
        self.head = state.get("head", HEAD)
        self.ref = state.get("ref", BRANCH)
        self.green = state.get("green", "1")
        self.loc = state.get("loc", "100 3")
        self.reports = state.get("reports", 0)
        self.attempts = state.get("attempts", "")
        self.attempt_id = state.get("attempt_id", "")
        self.marker_sha = state.get("marker_sha", "")
        self.marker_id = state.get("marker_id", "")
        self.compare = state.get("compare", '["src/a.ts"]')
        self.report_bodies = state.get("report_bodies", "")
        self.recent_issue = state.get("recent_issue", "901")
        self.recent_inline = state.get("recent_inline", "")
        self.reject_paths = set(state.get("reject_paths", ()))
        self.fail = set(state.get("fail", ()))
        self.calls = []
        self.writes = []

    def _read(self, name, out):
        if name in self.fail:
            return 1, "", "HTTP 403: API rate limit exceeded\n"
        return 0, out, ""

    def __call__(self, args):
        self.calls.append(list(args))
        joined = " ".join(args)
        if args[:3] in (["api", "-X", "POST"], ["api", "-X", "PATCH"]):
            self.writes.append(list(args))
            for arg in args:
                if arg.startswith("path=") and arg[5:] in self.reject_paths:
                    return 1, "", "HTTP 422: line must be part of the diff\n"
            return (1, "", "boom\n") if "write" in self.fail else (0, "{}", "")
        if args[:2] == ["pr", "list"]:
            if self.head != HEAD:
                return self._read("pr_list", "")
            return self._read(
                "pr_list",
                json.dumps({"number": int(PR), "headRefOid": HEAD, "isDraft": self.draft}),
            )
        if args[:2] == ["pr", "view"] and "headRefOid,headRefName,isDraft" in args:
            return self._read(
                "pr_view",
                json.dumps(
                    {"headRefOid": self.head, "headRefName": self.ref, "isDraft": self.draft}
                ),
            )
        if args[:2] == ["pr", "view"] and "additions,deletions,changedFiles" in args:
            return self._read("loc", self.loc)
        if "check-runs" in joined:
            return self._read("checks", self.green)
        if "/compare/" in joined:
            return self._read("compare", self.compare)
        if "now - 3600" in joined:
            if "/pulls/" in joined:
                return self._read("recent", self.recent_inline)
            return self._read("recent", self.recent_issue)
        if G.REPORT_HEADER in joined:
            return self._read("reports", "\n".join(str(900 + n) for n in range(self.reports)))
        if review_budget.ATTEMPT_EOF in joined:
            return self._read("attempts", self.attempts)
        if G.ATTEMPT_PREFIX in joined:
            return self._read("attempt_id", self.attempt_id)
        if G.MARKER_PREFIX in joined and joined.endswith(".body"):
            body = (
                "%s %s -->\nAutomated Claude review completed for commit %s.\nCost: $1 (m) | 3 turns"
                % (G.MARKER_PREFIX, self.marker_sha, self.marker_sha[:7])
                if self.marker_sha
                else ""
            )
            return self._read("marker", body)
        if G.MARKER_PREFIX in joined and joined.endswith(".id"):
            return self._read("marker_id", self.marker_id)
        if G.FINDINGS_FENCE in joined:
            return self._read("report_bodies", self.report_bodies)
        raise AssertionError("unexpected gh call: %r" % args)

    def bodies(self):
        return [a.split("=", 1)[1] for w in self.writes for a in w if a.startswith("body=")]


@pytest.fixture
def env(monkeypatch, tmp_path):
    out = tmp_path / "github_output"
    out.write_text("", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    for name in (
        "WR_EVENT",
        "WR_CONCLUSION",
        "WR_HEAD_SHA",
        "WR_HEAD_BRANCH",
        "PR_HEAD_SHA",
        "REQUIRED_CHECK",
        "EXECUTION_FILE",
        "REVIEW_OUTCOME",
        "HEAD_SHA",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    monkeypatch.setenv("GITHUB_REPOSITORY", REPO)
    monkeypatch.setattr(common, "require_cmd", lambda cmd, **_kw: "/usr/bin/" + cmd)
    slept: list[float] = []
    monkeypatch.setattr(G, "_sleep", slept.append)
    return {"out": out, "tmp": tmp_path, "mp": monkeypatch, "slept": slept}


def run(env, fake, argv=(), **extra):
    env["mp"].setattr(G, "_gh_call", fake)
    for key, value in extra.items():
        env["mp"].setenv(key, value)
    return G.main(list(argv))


def outputs(env):
    text = env["out"].read_text(encoding="utf-8")
    keys = {}
    prompt = None
    lines = text.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]
        if line == "prompt<<%s" % G.PROMPT_DELIMITER:
            end = lines.index(G.PROMPT_DELIMITER, i + 1)
            prompt = "\n".join(lines[i + 1 : end])
            i = end + 1
            continue
        if "=" in line:
            k, v = line.split("=", 1)
            keys[k] = v
        i += 1
    keys["prompt"] = prompt
    return keys


def gate_pr(env, fake, **extra):
    extra.setdefault("EVENT_NAME", "pull_request")
    extra.setdefault("PR_NUMBER", PR)
    extra.setdefault("REQUIRED_CHECK", "CI Complete")
    rc = run(env, fake, **extra)
    return rc, outputs(env)


def gate_wr(env, fake, **extra):
    base = {
        "EVENT_NAME": "workflow_run",
        "WR_EVENT": "pull_request",
        "WR_CONCLUSION": "success",
        "WR_HEAD_SHA": HEAD,
        "WR_HEAD_BRANCH": BRANCH,
    }
    base.update(extra)
    rc = run(env, fake, **base)
    return rc, outputs(env)


# --------------------------------------------------------------------------- the frozen API ---------------------------------------------------------------------------


def test_the_frozen_api_is_pinned_by_value():
    assert G.MARKER_PREFIX == "<!-- claude-reviewed:"
    assert G.ATTEMPT_PREFIX == "<!-- claude-review-attempt:"
    assert G.REPORT_HEADER == "**Claude finished"
    assert G.REPORT_HEADER == review_budget.REPORT_NEEDLE
    assert G.FINDINGS_FENCE == "json:review-findings"
    assert G.PROMPT_DELIMITER == "CLAUDE_REVIEW_PROMPT_EOF"
    assert G.ARMS == ("--post-report", "--post-findings", "--mark")
    assert set(G.MODES) == set(G.ARMS)
    # The attempt prefix must never satisfy the marker read.
    assert not G.ATTEMPT_PREFIX.startswith(G.MARKER_PREFIX)


def test_an_unknown_arm_is_a_usage_error_and_apply_labels_is_gone(env):
    fake = FakeGh()
    assert run(env, fake, ["--apply-labels"]) == 2
    assert fake.calls == []


def test_prompts_resolve_beside_the_module_and_carry_no_label_fence():
    expected = pathlib.Path(G.__file__).resolve().parent / "prompts"
    assert expected == G.PROMPTS_DIR
    for name in ("initial.md", "followup.md"):
        text = (G.PROMPTS_DIR / name).read_text(encoding="utf-8")
        assert "json:pr-labels" not in text
        assert "{{HEAD_REF_SLUG}}" in text
        assert "{{EPIC" not in text
        assert "```json:review-findings" in text or "json:review-findings fence" in text
        leftover = set(G._UNRENDERED.findall(text)) - set(G.PLACEHOLDERS)
        assert leftover == set()


# --------------------------------------------------------------------------- go=false arms, each with a silent control ---------------------------------------------------------------------------


def test_a_draft_pr_is_not_reviewed_on_workflow_run(env):
    rc, out = gate_wr(env, FakeGh(draft=True))
    assert (rc, out["go"], out["prompt"]) == (0, "false", None)


def test_control_a_ready_pr_is_reviewed_on_workflow_run(env):
    rc, out = gate_wr(env, FakeGh(draft=False))
    assert (rc, out["go"], out["pr_number"], out["head_sha"]) == (0, "true", PR, HEAD)


# Interpolated into `select(.headRefOid == "%s")` this reads `... == "a" or true or ""`, which selects a PR at ANY head and defeats the SHA pin.
INJECTED_SHA = 'a" or true or "'


@pytest.mark.parametrize("bad", [INJECTED_SHA, "A" * 40, "a" * 39, ""])
def test_a_malformed_wr_head_sha_is_refused_before_any_gh_call(env, bad):
    fake = FakeGh()
    rc, out = gate_wr(env, fake, WR_HEAD_SHA=bad)
    assert rc == 1
    assert fake.calls == []
    assert "go" not in out


@pytest.mark.parametrize("bad", [INJECTED_SHA, "a" * 41])
def test_a_malformed_pr_head_sha_is_refused_before_the_check_runs_read(env, bad):
    fake = FakeGh()
    rc, out = gate_pr(env, fake, PR_HEAD_SHA=bad)
    assert rc == 1
    assert not any("check-runs" in " ".join(c) for c in fake.calls)
    assert "go" not in out


@pytest.mark.parametrize("bad", ["42/../../x", "--repo=evil", "4 2"])
def test_a_non_numeric_pr_number_is_refused_before_any_gh_call(env, bad):
    fake = FakeGh()
    rc, _out = gate_pr(env, fake, PR_NUMBER=bad)
    assert rc == 1
    assert fake.calls == []


@pytest.mark.parametrize("arm", ["--post-report", "--post-findings", "--mark"])
@pytest.mark.parametrize(("pr", "head"), [(PR, INJECTED_SHA), ("42/../x", HEAD)])
def test_every_arm_refuses_a_malformed_pr_or_head_before_any_gh_call(env, arm, pr, head):
    fake = FakeGh()
    assert run(env, fake, [arm], PR_NUMBER=pr, HEAD_SHA=head, REVIEW_OUTCOME="failure") == 1
    assert fake.calls == []


def test_a_draft_pr_is_not_reviewed_on_dispatch(env):
    rc, out = gate_pr(env, FakeGh(draft=True), EVENT_NAME="workflow_dispatch")
    assert (rc, out["go"]) == (0, "false")


def test_control_a_ready_pr_is_reviewed_on_dispatch(env):
    rc, out = gate_pr(env, FakeGh(draft=False), EVENT_NAME="workflow_dispatch")
    assert (rc, out["go"]) == (0, "true")


def test_ci_complete_not_green_on_the_head_is_not_reviewed(env):
    fake = FakeGh(green="0")
    rc, out = gate_pr(env, fake)
    assert (rc, out["go"], out["head_sha"]) == (0, "false", HEAD)
    checks = [c for c in fake.calls if "check-runs" in " ".join(c)]
    assert "check_name=CI Complete" in checks[0]


def test_control_ci_complete_green_on_the_head_is_reviewed(env):
    rc, out = gate_pr(env, FakeGh(green="1"))
    assert (rc, out["go"]) == (0, "true")


def test_a_red_ci_run_is_not_reviewed(env):
    rc, out = gate_wr(env, FakeGh(), WR_CONCLUSION="failure")
    assert (rc, out["go"]) == (0, "false")


def test_a_superseded_head_is_not_reviewed(env):
    rc, out = gate_wr(env, FakeGh(head=OLD))
    assert (rc, out["go"], out["pr_number"]) == (0, "false", "")


def test_a_head_already_marked_is_not_reviewed(env):
    rc, out = gate_wr(env, FakeGh(marker_sha=HEAD))
    assert (rc, out["go"], out["last_reviewed_sha"], out["prompt"]) == (0, "false", HEAD, None)


def test_control_an_older_marker_gives_a_follow_up(env):
    rc, out = gate_wr(env, FakeGh(marker_sha=OLD))
    assert (rc, out["go"], out["last_reviewed_sha"]) == (0, "true", OLD)


def test_a_gitlink_only_delta_is_not_reviewed(env):
    (env["tmp"] / ".gitmodules").write_text(
        '[submodule "private/account"]\n\tpath = private/account\n\turl = x\n', encoding="utf-8"
    )
    rc, out = gate_wr(env, FakeGh(marker_sha=OLD, compare='["private/account"]'))
    assert (rc, out["go"], out["prompt"]) == (0, "false", None)


def test_control_a_gitlink_plus_a_file_is_reviewed(env):
    (env["tmp"] / ".gitmodules").write_text(
        '[submodule "private/account"]\n\tpath = private/account\n\turl = x\n', encoding="utf-8"
    )
    rc, out = gate_wr(env, FakeGh(marker_sha=OLD, compare='["private/account", "src/a.ts"]'))
    assert (rc, out["go"]) == (0, "true")


def test_an_empty_delta_is_not_reviewed(env):
    rc, out = gate_wr(env, FakeGh(marker_sha=OLD, compare="[]"))
    assert (rc, out["go"]) == (0, "false")


def test_a_failed_compare_fails_open_into_a_follow_up(env):
    rc, out = gate_wr(env, FakeGh(marker_sha=OLD, fail={"compare"}))
    assert (rc, out["go"], out["last_reviewed_sha"]) == (0, "true", OLD)


def test_a_failed_marker_read_does_not_re_review(env, capsys):
    fake = FakeGh(marker_sha=HEAD, fail={"marker"})
    rc, out = gate_wr(env, fake)
    assert (rc, out["go"], out["prompt"]) == (0, "false", None)
    marker_reads = [c for c in fake.calls if G.MARKER_PREFIX in " ".join(c)]
    assert len(marker_reads) == 3
    assert env["slept"] == [3, 6]
    err = capsys.readouterr()
    assert "could not be read" in err.out + err.err
    assert "API rate limit exceeded" in err.err


def test_control_a_readable_empty_marker_gives_an_initial_review(env):
    rc, out = gate_wr(env, FakeGh(marker_sha=""))
    assert (rc, out["go"], out["last_reviewed_sha"]) == (0, "true", "")


def test_a_capped_pr_is_not_reviewed(env):
    # 100 changed lines -> cap 3; 2 reports + 1 chargeable non-infra attempt = 3.
    attempts = "%s %s -->\nattempts: 1\nclass: error_x\n%s" % (
        G.ATTEMPT_PREFIX,
        OLD,
        review_budget.ATTEMPT_EOF,
    )
    rc, out = gate_wr(env, FakeGh(reports=2, attempts=attempts))
    assert (rc, out["go"]) == (0, "false")


def test_control_one_pass_below_the_cap_is_reviewed(env):
    rc, out = gate_wr(env, FakeGh(reports=2))
    assert (rc, out["go"]) == (0, "true")


def test_an_exhausted_infra_head_is_not_reviewed(env):
    attempts = "%s %s -->\nattempts: 3\nclass: error_max_turns\n%s" % (
        G.ATTEMPT_PREFIX,
        HEAD,
        review_budget.ATTEMPT_EOF,
    )
    rc, out = gate_wr(env, FakeGh(attempts=attempts))
    assert (rc, out["go"]) == (0, "false")


def test_an_unreadable_report_count_stops_the_gate(env):
    rc, out = gate_wr(env, FakeGh(fail={"reports"}))
    assert rc == 1
    assert "go" not in out


def test_an_unreadable_attempt_ledger_stops_the_gate(env):
    rc, out = gate_wr(env, FakeGh(fail={"attempts"}))
    assert rc == 1
    assert "go" not in out


# --------------------------------------------------------------------------- prompt choice ---------------------------------------------------------------------------


def test_the_initial_prompt_carries_the_per_commit_paragraph(env):
    rc, out = gate_wr(env, FakeGh())
    assert rc == 0
    prompt = out["prompt"]
    assert prompt.startswith("This is the FIRST automated review")
    assert "agent/reviews/%s/" % BRANCH in prompt
    assert "Per-commit review records" in prompt
    assert "HEAD SHA: %s" % HEAD in prompt
    assert "{{" not in prompt
    assert out["review_turns"] == str(G.MIN_TURNS)


def test_the_follow_up_prompt_carries_the_per_commit_paragraph(env):
    rc, out = gate_wr(env, FakeGh(marker_sha=OLD))
    assert rc == 0
    prompt = out["prompt"]
    assert prompt.startswith("This is a FOLLOW-UP review")
    assert "git diff %s..%s" % (OLD, HEAD) in prompt
    assert "agent/reviews/%s/" % BRANCH in prompt
    assert "Per-commit review records" in prompt
    assert "{{" not in prompt


def test_the_slug_is_the_reviewers_directory_name(env):
    rc, out = gate_pr(env, FakeGh(ref="feat/x y"))
    assert rc == 0
    assert "agent/reviews/feat-x-y/" in out["prompt"]


def test_turns_scale_with_the_diff_and_clamp():
    assert [G.turns_for(n) for n in (0, 1000, 2001, 3000, 5001, 100000)] == [
        50,
        50,
        75,
        75,
        140,
        140,
    ]


def test_turns_cover_the_breadth_of_a_many_file_diff():
    """PR #594 (2026-10-04) died at the 50-turn floor on 1,050 lines over 49 files: density alone gave the floor. Breadth now earns TURNS_PER_FILE per file."""
    assert G.turns_for(1050, 49) == 98
    assert G.turns_for(1050, 3) == 50
    assert G.turns_for(100000, 49) == G.MAX_TURNS
    assert G.turns_for(0, 200) == G.MAX_TURNS


def test_the_gate_reads_the_file_count_into_the_turn_budget(env):
    rc, out = gate_wr(env, FakeGh(loc="1050 49"))
    assert rc == 0
    assert out["review_turns"] == "98"


def test_an_unparseable_diff_size_takes_the_floor(env):
    rc, out = gate_wr(env, FakeGh(loc="1050"))
    assert rc == 0
    assert out["review_turns"] == str(G.MIN_TURNS)


def test_a_missing_template_leaves_no_prompt(env):
    env["mp"].setattr(G, "PROMPTS_DIR", env["tmp"] / "nowhere")
    rc, out = gate_wr(env, FakeGh())
    assert rc == 1
    assert out["prompt"] is None
    assert "go" not in out


# --------------------------------------------------------------------------- --post-report ---------------------------------------------------------------------------

FENCE = '```json:review-findings\n[{"path": "src/a.ts", "line": 3, "severity": "high", "title": "t", "body": "b"}]\n```'


def execution(env, result=None, subtype=None, **extra):
    record = {"type": "result"}
    if result is not None:
        record["result"] = result
    if subtype is not None:
        record["subtype"] = subtype
    record.update(extra)
    path = env["tmp"] / "execution.json"
    path.write_text(json.dumps([{"type": "system"}, record]), encoding="utf-8")
    return str(path)


def test_post_report_writes_the_header_and_the_fence(env):
    fake = FakeGh()
    report = "Verdict: one defect.\n\n<details>\n\n" + FENCE + "\n\n</details>"
    rc = run(
        env,
        fake,
        ["--post-report"],
        PR_NUMBER=PR,
        HEAD_SHA=HEAD,
        EXECUTION_FILE=execution(env, report),
    )
    assert rc == 0
    assert len(fake.writes) == 1
    assert fake.writes[0][:4] == ["api", "-X", "POST", "repos/o/r/issues/42/comments"]
    body = fake.bodies()[0]
    assert body.startswith("**Claude finished the automated review of aaaaaaa**\n\n---\n\n")
    assert "```json:review-findings" in body


def test_control_post_report_without_a_report_posts_nothing(env):
    fake = FakeGh()
    rc = run(
        env, fake, ["--post-report"], PR_NUMBER=PR, HEAD_SHA=HEAD, EXECUTION_FILE=execution(env)
    )
    assert (rc, fake.writes) == (0, [])


def test_post_report_truncates_the_middle_and_keeps_the_fence(env):
    fake = FakeGh()
    report = "HEAD" + "x" * 70000 + "\n" + FENCE
    rc = run(
        env,
        fake,
        ["--post-report"],
        PR_NUMBER=PR,
        HEAD_SHA=HEAD,
        EXECUTION_FILE=execution(env, report),
    )
    assert rc == 0
    body = fake.bodies()[0]
    assert len(body) < 65536
    assert "report truncated" in body
    assert body.endswith(FENCE)


# --------------------------------------------------------------------------- --post-findings ---------------------------------------------------------------------------


def report_with(findings, trailer=""):
    return (
        "**Claude finished the automated review of aaaaaaa**\n\n```json:review-findings\n%s\n```\n%s"
        % (
            json.dumps(findings),
            trailer,
        )
    )


def findings_run(env, fake):
    return run(env, fake, ["--post-findings"], PR_NUMBER=PR, HEAD_SHA=HEAD)


def test_post_findings_caps_at_twenty(env):
    findings = [
        {"path": "f%d.ts" % n, "line": n + 1, "severity": "low", "title": "t"} for n in range(25)
    ]
    fake = FakeGh(report_bodies=report_with(findings))
    assert findings_run(env, fake) == 0
    assert len(fake.writes) == G.INLINE_COMMENT_CAP == 20
    first = fake.writes[0]
    assert first[:4] == ["api", "-X", "POST", "repos/o/r/pulls/42/comments"]
    assert "commit_id=%s" % HEAD in first
    assert "side=RIGHT" in first


def test_post_findings_orders_by_severity(env):
    findings = [
        {"path": "low.ts", "line": 1, "severity": "low"},
        {"path": "crit.ts", "line": 1, "severity": "critical"},
        {"path": "none.ts", "line": 1},
        {"path": "high.ts", "line": 1, "severity": "HIGH"},
    ]
    fake = FakeGh(report_bodies=report_with(findings))
    findings_run(env, fake)
    paths = [a[5:] for w in fake.writes for a in w if a.startswith("path=")]
    assert paths == ["crit.ts", "high.ts", "none.ts", "low.ts"]
    assert fake.bodies()[2].startswith("**[MEDIUM]** - finding")


def test_post_findings_skips_lines_outside_the_diff(env, capsys):
    findings = [
        {"path": "outside.ts", "line": 900, "severity": "high", "title": "x"},
        {"path": "inside.ts", "line": 3, "severity": "high", "title": "y"},
        {"line": 3, "severity": "high", "title": "no path"},
    ]
    fake = FakeGh(report_bodies=report_with(findings), reject_paths={"outside.ts"})
    assert findings_run(env, fake) == 0
    assert len(fake.writes) == 2
    err = capsys.readouterr()
    assert "1 posted, 2 skipped" in err.out + err.err


def test_control_post_findings_without_a_fence_posts_nothing(env):
    fake = FakeGh(report_bodies="**Claude finished the automated review of aaaaaaa**\n\nno block")
    assert findings_run(env, fake) == 0
    assert fake.writes == []


def test_post_findings_stops_at_the_first_closer_after_the_last_opener(env):
    old = report_with([{"path": "old.ts", "line": 1}])
    new = report_with(
        [{"path": "new.ts", "line": 2, "body": "use ``` here"}],
        trailer="\n```json:other\n{}\n```\n",
    )
    fake = FakeGh(report_bodies=old + "\n" + new)
    assert findings_run(env, fake) == 0
    paths = [a[5:] for w in fake.writes for a in w if a.startswith("path=")]
    assert paths == ["new.ts"]


# --------------------------------------------------------------------------- --mark ---------------------------------------------------------------------------


def test_mark_creates_the_marker_when_none_exists(env):
    fake = FakeGh(marker_id="")
    rc = run(
        env,
        fake,
        ["--mark"],
        PR_NUMBER=PR,
        HEAD_SHA=HEAD,
        REVIEW_OUTCOME="success",
        EXECUTION_FILE=execution(env, "r"),
    )
    assert rc == 0
    assert fake.writes[0][:4] == ["api", "-X", "POST", "repos/o/r/issues/42/comments"]
    body = fake.bodies()[0]
    assert body.startswith(
        "%s %s -->\nAutomated Claude review completed for commit aaaaaaa." % (G.MARKER_PREFIX, HEAD)
    )
    assert G.marker_sha_from_bodies(body) == HEAD
    # The honesty guard ignores every bookkeeping comment.
    recent = [c for c in fake.calls if "now - 3600" in " ".join(c) and "/issues/" in " ".join(c)]
    assert 'startswith("<!--") | not' in recent[0][-1]


def test_mark_patches_the_existing_marker(env):
    fake = FakeGh(marker_id="555\n777")
    rc = run(env, fake, ["--mark"], PR_NUMBER=PR, HEAD_SHA=HEAD, REVIEW_OUTCOME="success")
    assert rc == 0
    assert fake.writes[0][:4] == ["api", "-X", "PATCH", "repos/o/r/issues/comments/777"]


def test_mark_refuses_when_the_review_posted_nothing(env):
    fake = FakeGh(recent_issue="", recent_inline="")
    rc = run(env, fake, ["--mark"], PR_NUMBER=PR, HEAD_SHA=HEAD, REVIEW_OUTCOME="success")
    assert rc == 1
    assert fake.writes == []


def test_control_mark_accepts_inline_output_alone(env):
    fake = FakeGh(recent_issue="", recent_inline="31")
    rc = run(env, fake, ["--mark"], PR_NUMBER=PR, HEAD_SHA=HEAD, REVIEW_OUTCOME="success")
    assert rc == 0
    assert len(fake.writes) == 1


def test_mark_records_a_spent_attempt_when_the_review_failed(env):
    fake = FakeGh()
    rc = run(
        env,
        fake,
        ["--mark"],
        PR_NUMBER=PR,
        HEAD_SHA=HEAD,
        REVIEW_OUTCOME="failure",
        EXECUTION_FILE=execution(env, subtype="error_max_turns"),
    )
    assert rc == 0
    assert fake.writes[0][:4] == ["api", "-X", "POST", "repos/o/r/issues/42/comments"]
    body = fake.bodies()[0]
    assert body.startswith(
        "%s %s -->\nattempts: 1\nclass: error_max_turns\n" % (G.ATTEMPT_PREFIX, HEAD)
    )
    assert "INFRASTRUCTURE-class" in body
    assert G.marker_sha_from_bodies(body) == ""
    states = review_budget.parse_attempt_states(body)
    assert states == [review_budget.AttemptState(HEAD, 1, "error_max_turns")]


def test_mark_records_an_api_failure_by_its_status(env):
    """An LLM outage reaches the ledger as `api_error_<status>`, the class review_status.OUTAGE_CLASSES excuses (operator ruling 2026-10-03)."""
    fake = FakeGh()
    rc = run(
        env,
        fake,
        ["--mark"],
        PR_NUMBER=PR,
        HEAD_SHA=HEAD,
        REVIEW_OUTCOME="failure",
        EXECUTION_FILE=execution(
            env, subtype="error_during_execution", is_error=True, api_error_status=529
        ),
    )
    assert rc == 0
    assert "\nclass: api_error_529\n" in fake.bodies()[0]


def test_control_an_error_without_an_api_status_keeps_its_subtype(env):
    fake = FakeGh()
    rc = run(
        env,
        fake,
        ["--mark"],
        PR_NUMBER=PR,
        HEAD_SHA=HEAD,
        REVIEW_OUTCOME="failure",
        EXECUTION_FILE=execution(env, subtype="error_during_execution", is_error=True),
    )
    assert rc == 0
    assert "\nclass: error_during_execution\n" in fake.bodies()[0]


def test_mark_upserts_the_attempt_with_its_count(env):
    prior = "%s %s -->\nattempts: 2\nclass: error_max_turns\n%s" % (
        G.ATTEMPT_PREFIX,
        HEAD,
        review_budget.ATTEMPT_EOF,
    )
    fake = FakeGh(attempts=prior, attempt_id="808")
    rc = run(env, fake, ["--mark"], PR_NUMBER=PR, HEAD_SHA=HEAD, REVIEW_OUTCOME="cancelled")
    assert rc == 0
    assert fake.writes[0][:4] == ["api", "-X", "PATCH", "repos/o/r/issues/comments/808"]
    body = fake.bodies()[0]
    assert "attempts: 3\nclass: review step did not succeed\n" in body
    assert "Push a change to earn another pass." in body


def test_mark_does_not_reset_the_count_when_the_ledger_is_unreadable(env):
    fake = FakeGh(fail={"attempts"})
    rc = run(env, fake, ["--mark"], PR_NUMBER=PR, HEAD_SHA=HEAD, REVIEW_OUTCOME="failure")
    assert rc == 1
    assert fake.writes == []


def test_cost_line_lists_every_model_by_output():
    record = {
        "total_cost_usd": 4.66004,
        "num_turns": 37,
        "duration_ms": 125000,
        "modelUsage": {"haiku": {"outputTokens": 10}, "sonnet": {"outputTokens": 900}},
        "usage": {"input_tokens": 1, "output_tokens": 2, "cache_read_input_tokens": 3},
    }
    assert G.cost_line(record) == (
        "Cost: $4.66 (sonnet 900out, haiku 10out) | 37 turns | 2m5s\n"
        "Tokens: 1 in / 2 out / 3 cache-read / 0 cache-write"
    )
    assert G.cost_line({}) == ""


# --------------------------------------------------------------------------- nothing fights pr_labels ---------------------------------------------------------------------------


def test_no_arm_writes_the_label_ledger(env):
    writes = []
    cases = [
        (
            [],
            {
                "EVENT_NAME": "workflow_run",
                "WR_EVENT": "pull_request",
                "WR_CONCLUSION": "success",
                "WR_HEAD_SHA": HEAD,
                "WR_HEAD_BRANCH": BRANCH,
            },
        ),
        (
            ["--post-report"],
            {"PR_NUMBER": PR, "HEAD_SHA": HEAD, "EXECUTION_FILE": execution(env, "r\n" + FENCE)},
        ),
        (["--mark"], {"PR_NUMBER": PR, "HEAD_SHA": HEAD, "REVIEW_OUTCOME": "success"}),
        (["--mark"], {"PR_NUMBER": PR, "HEAD_SHA": HEAD, "REVIEW_OUTCOME": "failure"}),
    ]
    for argv, extra in cases:
        fake = FakeGh(report_bodies=report_with([{"path": "a", "line": 1}]))
        run(env, fake, argv, **extra)
        writes += fake.writes
    fake = FakeGh(report_bodies=report_with([{"path": "a", "line": 1}]))
    findings_run(env, fake)
    writes += fake.writes
    assert len(writes) >= 4
    assert not any("claude-labels" in arg for write in writes for arg in write)
    assert not any("/labels" in arg for write in writes for arg in write)
