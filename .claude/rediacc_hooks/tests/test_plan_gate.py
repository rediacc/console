"""The plan gate's shared module (`rediacc_hooks.plan_gate`, box L2 of agent/plans/PLAN-plan-per-pr-loop.md) and the PR-body refresh that writes its `Plan:` line.

The two guards that call `plan_merge_refusal` have their own suites beside them (`guards/test-block_admin_merge.py`, `guards/test-block_push_to_protected_branch.py`); this file pins the module's parsing and the one writer of the link, `.claude/hooks/post-bash/refresh_pr_body.py`, driven through the same stubbed `git`/`gh` world `test_post_bash_differential.py` builds.
"""

import json
import pathlib
import subprocess

import pytest

from rediacc_hooks import plan_gate
from rediacc_hooks.tests import test_post_bash_differential as pbd
from rediacc_hooks.wellknown import GH_REPO

OPEN = "# PLAN-a\nStatus: approved\n\n## Boxes\n- [x] A the first box is ticked here\n- [ ] B the second box is still open here\n"
DONE = "# PLAN-b\nStatus: approved\n\n## Boxes\n- [x] A the first box is ticked here\n- [x] B the second box is ticked here\n"
NOBOX = "# PLAN-c\nStatus: approved\n\nProse only.\n"
STUB = "# PLAN: b (moved)\nStatus: moved\nMoved-To: agent/plans/_done/PLAN-b.md\n\nMoved.\n"

QUEUE = """# Plan queue

Prose naming agent/plans/PLAN-prose.md is not an entry.

1. agent/plans/PLAN-missing.md
2. `agent/plans/PLAN-a.md` -- the live branch's plan
3. agent/plans/PLAN-b.md
"""


@pytest.fixture
def root(tmp_path):
    plans = tmp_path / "agent" / "plans"
    (plans / "_done").mkdir(parents=True)
    (plans / "PLAN-a.md").write_text(OPEN, encoding="utf-8")
    (plans / "PLAN-b.md").write_text(DONE, encoding="utf-8")
    (plans / "PLAN-c.md").write_text(NOBOX, encoding="utf-8")
    (plans / "PLAN-moved.md").write_text(STUB, encoding="utf-8")
    (plans / "_done" / "PLAN-b.md").write_text(DONE, encoding="utf-8")
    (plans / "QUEUE.md").write_text(QUEUE, encoding="utf-8")
    return str(tmp_path)


def test_queue_reads_numbered_entries_only(root):
    assert plan_gate.queue(root) == [
        "agent/plans/PLAN-missing.md",
        "agent/plans/PLAN-a.md",
        "agent/plans/PLAN-b.md",
    ]


def test_queue_head_skips_a_plan_that_does_not_exist(root):
    assert plan_gate.queue_head(root) == "agent/plans/PLAN-a.md"


def test_no_queue_file_is_an_empty_queue(tmp_path):
    assert plan_gate.queue(str(tmp_path)) == []
    assert plan_gate.queue_head(str(tmp_path)) == ""


def test_the_seeded_queue_names_existing_plans():
    """The committed queue is read by the same parser, and every entry exists: a renamed plan breaks the link."""
    repo = pathlib.Path(__file__).resolve().parents[3]
    entries = plan_gate.queue(str(repo))
    assert entries, "agent/plans/QUEUE.md holds no entry the parser reads"
    missing = [e for e in entries if not (repo / e).is_file()]
    assert not missing, missing


@pytest.mark.parametrize(
    ("body", "want"),
    [
        ("Plan: agent/plans/PLAN-a.md", "open box"),
        ("Plan: agent/plans/PLAN-a.md\nOperational-Reason: M7 runs after merge", ""),
        ("Plan: agent/plans/PLAN-b.md", ""),
        ("- **Plan:** `agent/plans/PLAN-b.md`", ""),
        ("Plan: agent/plans/PLAN-moved.md", ""),
        ("Prose only.", "names no plan"),
        ("", "names no plan"),
        (None, "could not be read"),
        ("Plan: agent/plans/PLAN-b.md, agent/plans/PLAN-a.md", "names 2 plans"),
        ("Plan: agent/plans/PLAN-b.md\nPlan: agent/plans/PLAN-a.md", "names 2 plans"),
        ("Plan: agent/plans/PLAN-c.md", "no boxes"),
        ("Plan: agent/plans/PLAN-zz.md", "does not exist"),
        ("Plan: ../../etc/PLAN-x.md", "not agent/plans/PLAN-<slug>.md"),
        ("Plan: the merges one", "not agent/plans/PLAN-<slug>.md"),
        (
            "Plan: agent/plans/PLAN-a.md\n<!-- pushed-head:begin -->\nOperational-Reason: x\n<!-- pushed-head:end -->",
            "open box",
        ),
        (
            "<!-- worklist-epics:begin -->\nPlan: agent/plans/PLAN-b.md\n<!-- worklist-epics:end -->",
            "names no plan",
        ),
    ],
)
def test_plan_merge_refusal(root, body, want):
    got = plan_gate.plan_merge_refusal(root, body)
    if want:
        assert want in got, got
    else:
        assert got == "", got


def test_with_plan_line_is_set_once():
    once = plan_gate.with_plan_line("Body text.", "agent/plans/PLAN-a.md")
    assert once == "Plan: agent/plans/PLAN-a.md\n\nBody text."
    assert plan_gate.with_plan_line(once, "agent/plans/PLAN-b.md") == once
    assert plan_gate.with_plan_line("Body text.", "") == "Body text."


# ---- the writer: refresh_pr_body ------------------------------------------------------------


def _patch_table(body, repo=GH_REPO):
    return dict(
        pbd._git(),
        **{
            pbd._default("gh"): {"rc": 0},
            pbd.REPO_VIEW: {"out": repo + "\n"},
            pbd._pr_list(repo=repo): {"out": "543\n"},
            pbd._key("gh", "pr", "view", "543", "--json", "body", "--jq", ".body"): {
                "out": body + "\n"
            },
            pbd._key(
                "gh", "api", "repos/%s/pulls/543" % repo, "-X", "PATCH", "-F", "body=@<TMP>"
            ): {"out": '{"ok":true}\n'},
        },
    )


def _refresh(tmp_path, table, with_queue=True):
    env, work = pbd._world(tmp_path, table)
    if with_queue:
        plans = work / "repo" / "agent" / "plans"
        plans.mkdir(parents=True)
        (plans / "PLAN-a.md").write_text(OPEN, encoding="utf-8")
        (plans / "QUEUE.md").write_text("1. agent/plans/PLAN-a.md\n", encoding="utf-8")
    proc = subprocess.run(
        ["python3", str(pbd.SUBJECTS["refresh-pr-body"])],
        input=json.dumps({"tool_input": {"command": "git push"}}).encode(),
        capture_output=True,
        check=False,
        env=env,
        cwd=str(work),
        timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
    record = work / "record.txt"
    return record.read_text(encoding="utf-8") if record.is_file() else None


def test_refresh_writes_the_queue_head_as_the_plan_line(tmp_path):
    body = _refresh(tmp_path, _patch_table("A body with no plan."))
    assert body is not None
    assert body.startswith("Plan: agent/plans/PLAN-a.md\n\nA body with no plan."), body


def test_refresh_keeps_a_plan_line_the_body_already_has(tmp_path):
    body = _refresh(tmp_path, _patch_table("Plan: agent/plans/PLAN-b.md\n\nWork."))
    assert body is not None
    assert body.startswith("Plan: agent/plans/PLAN-b.md\n\nWork."), body
    assert "PLAN-a" not in body


def test_refresh_without_a_queue_adds_no_plan_line(tmp_path):
    body = _refresh(tmp_path, _patch_table("Plain."), with_queue=False)
    assert body is not None
    assert "Plan:" not in body, body


def test_refresh_leaves_a_foreign_repo_unlinked(tmp_path):
    body = _refresh(tmp_path, _patch_table("Plain.", repo="someone/other"))
    assert body is not None
    assert "Plan:" not in body, body
