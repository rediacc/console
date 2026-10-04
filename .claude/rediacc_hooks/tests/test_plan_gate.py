"""The plan gate's shared module (`rediacc_hooks.plan_gate`, box L2 of agent/plans/PLAN-plan-per-pr-loop.md) and the PR-body refresh that writes its `Plan:` line.

The two guards that call `plan_merge_refusal` have their own suites beside them (`guards/test-block_admin_merge.py`, `guards/test-block_push_to_protected_branch.py`); this file pins the module's parsing and the one writer of the link, `.claude/hooks/post-bash/refresh_pr_body.py`, driven through the same stubbed `git`/`gh` world `test_post_bash_differential.py` builds.
"""

import json
import pathlib
import re
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

1. agent/plans/PLAN-outside.md -- a numbered line outside both sections is not read

## Promoted

1. agent/plans/PLAN-missing.md
2. `agent/plans/PLAN-a.md` -- the live branch's plan

## Generated

<!-- queue:generated:begin -->
1. agent/plans/PLAN-b.md -- P2, approved
2. agent/plans/PLAN-a.md -- P2, approved
<!-- queue:generated:end -->
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


def test_queue_reads_promoted_then_generated(root):
    assert plan_gate.queue(root) == [
        "agent/plans/PLAN-missing.md",
        "agent/plans/PLAN-a.md",
        "agent/plans/PLAN-b.md",
    ]


def test_queue_head_prefers_promoted_over_generated(tmp_path):
    plans = tmp_path / "agent" / "plans"
    plans.mkdir(parents=True)
    for name in ("PLAN-a.md", "PLAN-b.md"):
        (plans / name).write_text(OPEN, encoding="utf-8")
    gen = "## Generated\n\n<!-- queue:generated:begin -->\n1. agent/plans/PLAN-a.md\n<!-- queue:generated:end -->\n"
    (plans / "QUEUE.md").write_text(gen, encoding="utf-8")
    assert plan_gate.queue_head(str(tmp_path)) == "agent/plans/PLAN-a.md"
    # Promoted wins by section, not by position in the file.
    (plans / "QUEUE.md").write_text(
        gen + "\n## Promoted\n\n1. agent/plans/PLAN-b.md\n", encoding="utf-8"
    )
    assert plan_gate.queue_head(str(tmp_path)) == "agent/plans/PLAN-b.md"


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
        (plans / "QUEUE.md").write_text(
            "## Promoted\n\n1. agent/plans/PLAN-a.md\n", encoding="utf-8"
        )
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


# ---------------------------------------------------------------- the generated half (`wl_planqueue`, worklist #0f45b81d)


def _pq():
    from rediacc_hooks import syspath  # noqa: PLC0415 -- the stop dir joins sys.path first

    syspath.on_sys_path(plan_gate.STOP_DIR)
    import wl_planqueue  # noqa: PLC0415

    return wl_planqueue


def _plan(status, priority="P2", extra=""):
    return (
        "# PLAN\nStatus: %s\nPriority: %s -- seed\n%s\n## Boxes\n- [ ] A one open box sits here\n"
        % (status, priority, extra)
    )


PROMOTED = "# Plan queue\n\nHand prose, kept   as typed.\n\n## Promoted\n\n1. agent/plans/PLAN-picked.md -- the operator's pick\n\n"


@pytest.fixture
def qroot(tmp_path):
    """A git checkout: PLAN-untracked.md is left out of the index, every other plan is added."""
    plans = tmp_path / "agent" / "plans"
    (plans / "_done").mkdir(parents=True)
    files = {
        "PLAN-picked.md": _plan("approved", "P0"),
        "PLAN-held-urgent.md": _plan("held", "P0"),
        "PLAN-open-late.md": _plan("ready", "P3"),
        "PLAN-open-early.md": _plan("approved", "P1"),
        "PLAN-finished.md": _plan("done", "P0"),
        "PLAN-untracked.md": _plan("approved", "P0"),
        "_done/PLAN-old.md": _plan("done", "P0"),
    }
    for rel, text in files.items():
        (plans / rel).write_text(text, encoding="utf-8")
    (plans / "QUEUE.md").write_text(PROMOTED, encoding="utf-8")
    env = {"PATH": "/usr/bin:/bin", "HOME": str(tmp_path), "GIT_CONFIG_NOSYSTEM": "1"}
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True, env=env)
    tracked = [str(plans / r) for r in files if r != "PLAN-untracked.md"]
    subprocess.run(["git", "-C", str(tmp_path), "add", "--", *tracked], check=True, env=env)
    return tmp_path


def _generated(root):
    pq = _pq()
    return pq.entries((root / pq.QUEUE_REL).read_text(encoding="utf-8"))[1]


def test_regenerate_preserves_promoted_byte_for_byte(qroot):
    pq = _pq()
    assert pq.problems(qroot), "a queue with no generated section must be reported"
    assert pq.refresh(qroot) is True
    text = (qroot / pq.QUEUE_REL).read_text(encoding="utf-8")
    assert text.startswith(PROMOTED), text
    assert pq.refresh(qroot) is False
    # A hand edit to Promoted survives the next regenerate untouched.
    edited = text.replace("the operator's pick", "re-noted by hand")
    (qroot / pq.QUEUE_REL).write_text(edited, encoding="utf-8")
    pq.refresh(qroot)
    assert (qroot / pq.QUEUE_REL).read_text(encoding="utf-8") == edited


def test_generated_order_by_priority_without_promoted_finished_or_untracked(qroot):
    """Every fixture plan is not started, so Priority decides among the unheld ones, and a held plan follows them (#93798daa, PLAN-stop-hook-one-plan-scope Design 6)."""
    _pq().refresh(qroot)
    assert _generated(qroot) == [
        "agent/plans/PLAN-open-early.md",
        "agent/plans/PLAN-open-late.md",
        "agent/plans/PLAN-held-urgent.md",
    ]


def test_generated_lines_carry_priority_and_status(qroot):
    pq = _pq()
    pq.refresh(qroot)
    text = (qroot / pq.QUEUE_REL).read_text(encoding="utf-8")
    assert "1. agent/plans/PLAN-open-early.md -- P1, approved, not started\n" in text
    assert "3. agent/plans/PLAN-held-urgent.md -- P0, held, not started\n" in text


def test_stale_generated_section_is_refused_by_the_freshness_check(qroot):
    pq = _pq()
    pq.refresh(qroot)
    assert pq.problems(qroot) == []
    path = qroot / pq.QUEUE_REL
    fresh = path.read_text(encoding="utf-8")
    stale = fresh.replace("PLAN-open-late.md -- P3, ready", "PLAN-open-late.md -- P3, held")
    assert stale != fresh
    path.write_text(stale, encoding="utf-8")
    assert pq.problems(qroot), "a hand-edited generated section must be refused"
    assert pq.problems(qroot, update=True) == []
    assert path.read_text(encoding="utf-8") == fresh


def test_the_committed_queue_is_fresh_and_its_head_is_the_first_promoted_plan():
    """The head is whatever the operator promoted first, never a pinned name: `## Promoted` is hand-ordered, so a test naming one plan went red the day PLAN-github-pr-review-restore was promoted ahead of the loop plan (2026-10-03)."""
    repo = pathlib.Path(__file__).resolve().parents[3]
    pq = _pq()
    text = (repo / pq.QUEUE_REL).read_text(encoding="utf-8")
    promoted = text.split("\n## Promoted\n", 1)[1].split("\n## Generated\n", 1)[0]
    first = re.search(r"^1\. (agent/plans/\S+\.md)", promoted, re.MULTILINE)
    head = pq.entries(text)[0][0]
    assert first
    assert head == first.group(1)
    assert (repo / head).is_file(), head
    assert pq.problems(repo) == [], "run `npm run check:ci-plan-record -- --update`"


def test_refresh_index_also_refreshes_the_queue(qroot):
    """The `--plan-tick` path: `wl_planrec.refresh_index` leaves the queue fresh, so a tick that changes a plan's rank cannot leave check:ci-plan-record red."""
    pq = _pq()
    import wl_checks  # noqa: PLC0415 -- importable once _pq() put the stop dir on sys.path
    import wl_planrec  # noqa: PLC0415

    assert pq.problems(qroot)
    wl_planrec.refresh_index(str(qroot), wl_checks.plan_records, wl_checks.plan_box_census)
    assert pq.problems(qroot) == []
    assert (qroot / pq.QUEUE_REL).read_text(encoding="utf-8").startswith(PROMOTED)


# ---------------------------------------------------------------- the progress order (operator rulings 2026-10-02)


def _box_plan(status="approved", priority="P2", opened=1, done=0, depends=""):
    """A plan with `done` ticked and `opened` open boxes. `depends` is a Depends-On value; "" declares no-dep."""
    dep = depends or "no-dep -- a standalone plan in the queue fixture"
    boxes = "".join("- [x] D%d a ticked box sits here\n" % i for i in range(done))
    boxes += "".join("- [ ] O%d an open box sits here\n" % i for i in range(opened))
    return "# PLAN\nStatus: %s\nDepends-On: %s\nPriority: %s -- seed\n\n## Boxes\n%s" % (
        status,
        dep,
        priority,
        boxes,
    )


def _queue_root(tmp_path, plans: dict[str, str]):
    """A git checkout holding `plans` (every one tracked) and a queue with an empty Promoted list, regenerated once."""
    folder = tmp_path / "agent" / "plans"
    folder.mkdir(parents=True)
    for name, text in plans.items():
        (folder / name).write_text(text, encoding="utf-8")
    (folder / "QUEUE.md").write_text("# Plan queue\n\n## Promoted\n\n", encoding="utf-8")
    env = {"PATH": "/usr/bin:/bin", "HOME": str(tmp_path), "GIT_CONFIG_NOSYSTEM": "1"}
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True, env=env)
    subprocess.run(
        ["git", "-C", str(tmp_path), "add", "--", *(str(folder / n) for n in plans)],
        check=True,
        env=env,
    )
    _pq().refresh(tmp_path)
    return tmp_path


def _names(root):
    return [rel.rsplit("/", 1)[-1] for rel in _generated(root)]


def _not_queued(root):
    """The text after `### Not queued` inside the generated block, "" when there is none."""
    pq = _pq()
    block = pq.generated_text((root / pq.QUEUE_REL).read_text(encoding="utf-8"))
    assert block is not None
    _head, sep, tail = block.partition("### Not queued\n")
    return tail if sep else ""


def test_in_progress_precedes_not_started_regardless_of_priority(tmp_path):
    root = _queue_root(
        tmp_path,
        {
            "PLAN-urgent-fresh.md": _box_plan(priority="P0 (operator)"),
            "PLAN-late-started.md": _box_plan(priority="P3", opened=2, done=1),
        },
    )
    assert _names(root) == ["PLAN-late-started.md", "PLAN-urgent-fresh.md"]


def test_held_follows_unheld_and_is_kept_in_the_note(tmp_path):
    root = _queue_root(
        tmp_path,
        {
            "PLAN-held.md": _box_plan(status="held", priority="P0"),
            "PLAN-open.md": _box_plan(priority="P1"),
        },
    )
    assert _names(root) == ["PLAN-open.md", "PLAN-held.md"]
    text = (root / _pq().QUEUE_REL).read_text(encoding="utf-8")
    assert "2. agent/plans/PLAN-held.md -- P0, held, not started\n" in text, text


def test_a_plan_with_no_open_box_is_not_queued_and_is_named(tmp_path):
    root = _queue_root(
        tmp_path,
        {
            "PLAN-all-ticked.md": _box_plan(opened=0, done=2),
            "PLAN-no-boxes.md": _box_plan(opened=0, done=0),
            "PLAN-work.md": _box_plan(),
        },
    )
    assert _names(root) == ["PLAN-work.md"]
    note = _not_queued(root)
    assert "- agent/plans/PLAN-all-ticked.md -- all boxes ticked: close it\n" in note, note
    assert "- agent/plans/PLAN-no-boxes.md -- no boxes yet: add boxes\n" in note, note
    queued = plan_gate.queue(str(root))
    assert queued == ["agent/plans/PLAN-work.md"], queued


@pytest.mark.parametrize(
    ("plans", "before"),
    [
        pytest.param(
            {
                "PLAN-dep.md": _box_plan(priority="P0", depends="PLAN-pre.md"),
                "PLAN-pre.md": _box_plan(status="held", priority="P3"),
            },
            [("PLAN-pre.md", "PLAN-dep.md")],
            id="direct",
        ),
        pytest.param(
            {
                "PLAN-top.md": _box_plan(priority="P0", opened=1, done=1, depends="PLAN-mid.md"),
                "PLAN-mid.md": _box_plan(priority="P1", depends="PLAN-low.md"),
                "PLAN-low.md": _box_plan(status="held", priority="P3"),
            },
            [("PLAN-low.md", "PLAN-mid.md"), ("PLAN-mid.md", "PLAN-top.md")],
            id="transitive",
        ),
        pytest.param(
            {
                "PLAN-dep.md": _box_plan(priority="P0", depends="PLAN-pre.md#T3"),
                "PLAN-pre.md": _box_plan(status="held", priority="P3"),
            },
            [("PLAN-pre.md", "PLAN-dep.md")],
            id="task-ref",
        ),
        pytest.param(
            {
                "PLAN-parent.md": _box_plan(priority="P0", opened=1, done=1),
                "PLAN-parent.S1.md": _box_plan(status="held", priority="P3"),
            },
            [("PLAN-parent.S1.md", "PLAN-parent.md")],
            id="sub-plan",
        ),
    ],
)
def test_a_dependent_never_precedes_its_prerequisite(tmp_path, plans, before):
    names = _names(_queue_root(tmp_path, plans))
    assert sorted(names) == sorted(plans), names
    for first, then in before:
        assert names.index(first) < names.index(then), names


def test_a_prerequisite_of_an_in_progress_plan_is_pulled_ahead(tmp_path):
    root = _queue_root(
        tmp_path,
        {
            "PLAN-started.md": _box_plan(priority="P3", opened=1, done=1, depends="PLAN-needed.md"),
            "PLAN-needed.md": _box_plan(priority="P3"),
            "PLAN-unrelated.md": _box_plan(priority="P0"),
        },
    )
    assert _names(root) == ["PLAN-needed.md", "PLAN-started.md", "PLAN-unrelated.md"]


def test_a_dependency_cycle_is_broken_and_reported(tmp_path):
    root = _queue_root(
        tmp_path,
        {
            "PLAN-a.md": _box_plan(depends="PLAN-b.md"),
            "PLAN-b.md": _box_plan(depends="PLAN-a.md"),
            "PLAN-c.md": _box_plan(priority="P3"),
        },
    )
    assert _names(root) == ["PLAN-a.md", "PLAN-b.md", "PLAN-c.md"]
    note = _not_queued(root)
    assert "dependency cycle PLAN-a.md -> PLAN-b.md -> PLAN-a.md" in note, note
    assert _pq().problems(root) == []


# ---------------------------------------------------------------- the PR's plan set (operator ruling 7 of PLAN-stop-hook-one-plan-scope, 2026-10-03)


def _dep_root(tmp_path, plans: dict[str, str], queue: str = ""):
    """A plan tree holding `plans` (basename -> text) and, when given, a QUEUE.md whose Promoted list names `queue`."""
    folder = tmp_path / "agent" / "plans"
    folder.mkdir(parents=True)
    for name, text in plans.items():
        (folder / name).write_text(text, encoding="utf-8")
    if queue:
        (folder / "QUEUE.md").write_text(
            "# Plan queue\n\n## Promoted\n\n1. agent/plans/%s\n" % queue, encoding="utf-8"
        )
    return str(tmp_path)


def _rel(name):
    return "agent/plans/%s" % name


def test_pr_plan_set_without_depends_equals_the_named_plan(root):
    """Control: no `Depends-On:` anywhere, so the set is exactly the body's plan, or the queue head with no body."""
    assert plan_gate.pr_plan_set(root, "Plan: agent/plans/PLAN-a.md") == ((_rel("PLAN-a.md"),), [])
    assert plan_gate.pr_plan_set(root, None) == ((_rel("PLAN-a.md"),), [])
    assert plan_gate.pr_plan_set(root, "Prose only.") == ((_rel("PLAN-a.md"),), [])


def test_pr_plan_set_operational_reason_keeps_every_named_plan(root):
    body = "Plan: agent/plans/PLAN-a.md, agent/plans/PLAN-b.md\nOperational-Reason: one PR"
    plans, problems = plan_gate.pr_plan_set(root, body)
    assert plans == (_rel("PLAN-a.md"), _rel("PLAN-b.md"))
    assert problems == []


def test_an_open_prerequisite_joins_the_set_first_and_refuses_the_merge(tmp_path):
    root = _dep_root(
        tmp_path,
        {
            "PLAN-a.md": _box_plan(opened=0, done=2, depends="PLAN-p.md"),
            "PLAN-p.md": _box_plan(opened=1, done=1),
        },
    )
    body = "Plan: agent/plans/PLAN-a.md"
    assert plan_gate.pr_plan_set(root, body) == ((_rel("PLAN-p.md"), _rel("PLAN-a.md")), [])
    got = plan_gate.plan_merge_refusal(root, body)
    assert "PLAN-p.md" in got, got
    assert "prerequisite" in got, got


@pytest.mark.parametrize(
    "prereq",
    [_box_plan(opened=0, done=2), _box_plan(status="done", opened=1, done=1)],
    ids=["every-box-ticked", "finished-status"],
)
def test_a_finished_prerequisite_is_not_in_the_set(tmp_path, prereq):
    """Control: the same edge with the prerequisite finished, by its boxes or its Status."""
    root = _dep_root(
        tmp_path,
        {"PLAN-a.md": _box_plan(opened=0, done=2, depends="PLAN-p.md"), "PLAN-p.md": prereq},
    )
    body = "Plan: agent/plans/PLAN-a.md"
    assert plan_gate.pr_plan_set(root, body) == ((_rel("PLAN-a.md"),), [])
    assert plan_gate.plan_merge_refusal(root, body) == ""


def test_a_transitive_chain_orders_the_deepest_prerequisite_first(tmp_path):
    root = _dep_root(
        tmp_path,
        {
            "PLAN-a.md": _box_plan(depends="PLAN-b.md"),
            "PLAN-b.md": _box_plan(depends="PLAN-c.md"),
            "PLAN-c.md": _box_plan(),
        },
        queue="PLAN-a.md",
    )
    want = (_rel("PLAN-c.md"), _rel("PLAN-b.md"), _rel("PLAN-a.md"))
    assert plan_gate.pr_plan_set(root, "Plan: agent/plans/PLAN-a.md") == (want, [])
    # With no body the queue head is the PR's plan, closed the same way.
    assert plan_gate.pr_plan_set(root, None) == (want, [])


def test_a_held_prerequisite_stays_in_the_set(tmp_path):
    root = _dep_root(
        tmp_path,
        {"PLAN-a.md": _box_plan(depends="PLAN-h.md"), "PLAN-h.md": _box_plan(status="held")},
    )
    plans, problems = plan_gate.pr_plan_set(root, "Plan: agent/plans/PLAN-a.md")
    assert plans == (_rel("PLAN-h.md"), _rel("PLAN-a.md"))
    assert problems == []


def test_a_cycle_is_a_named_problem_and_fails_the_merge_closed(tmp_path):
    root = _dep_root(
        tmp_path,
        {
            "PLAN-a.md": _box_plan(opened=0, done=1, depends="PLAN-b.md"),
            "PLAN-b.md": _box_plan(depends="PLAN-a.md"),
        },
    )
    body = "Plan: agent/plans/PLAN-a.md"
    plans, problems = plan_gate.pr_plan_set(root, body)
    assert set(plans) == {_rel("PLAN-a.md"), _rel("PLAN-b.md")}
    assert any(
        "cycle" in p and _rel("PLAN-a.md") in p and _rel("PLAN-b.md") in p for p in problems
    ), problems
    assert "cycle" in plan_gate.plan_merge_refusal(root, body)


def test_an_unresolvable_dependency_is_a_problem_naming_its_path(tmp_path):
    root = _dep_root(tmp_path, {"PLAN-a.md": _box_plan(opened=0, done=1, depends="PLAN-zz.md")})
    body = "Plan: agent/plans/PLAN-a.md"
    plans, problems = plan_gate.pr_plan_set(root, body)
    assert plans == (_rel("PLAN-a.md"),)
    assert any("PLAN-zz.md" in p and _rel("PLAN-a.md") in p for p in problems), problems
    assert "PLAN-zz.md" in plan_gate.plan_merge_refusal(root, body)


# ---------------------------------------------------------------- turbo (agent/plans/PLAN-stop-hook-turbo.md T4, T5, T7)

TURBO_ON = "```stop-hook\nturbo: on\nbatch_size: 2\nplan_concurrency: 9\n```\n"
TURBO_OFF = "```stop-hook\nturbo: off\n```\n"


def _xplan(opened=1, done=0, depends="", status="approved", conc="parallel", owns=""):
    """A plan carrying the X fields `wl_planconc.spawn_verdict` reads; `owns` defaults to a folder of its own."""
    dep = depends or "no-dep -- a standalone plan in the turbo fixture"
    boxes = "".join("- [x] D%d a ticked box sits here\n" % i for i in range(done))
    boxes += "".join("- [ ] O%d an open box sits here\n" % i for i in range(opened))
    return (
        "# PLAN\nStatus: %s\nOwner: d778be9d\nDepends-On: %s\nPriority: P2 -- seed\nConcurrency: %s\nOwns: %s\n\n## Boxes\n%s"
        % (status, dep, conc, owns or "docs/{name}/**", boxes)
    )


def _turbo_root(tmp_path, plans: dict[str, str], promoted: list[str], settings: str = TURBO_ON):
    """A plan tree with `plans` (name -> text, `{name}` in Owns replaced), a QUEUE.md whose Settings block is `settings` and whose Promoted list is `promoted` (entries may carry ` -- solo`)."""
    folder = tmp_path / "agent" / "plans"
    folder.mkdir(parents=True)
    for name, text in plans.items():
        (folder / ("PLAN-%s.md" % name)).write_text(text.replace("{name}", name), encoding="utf-8")
    lines = "".join(
        "%d. agent/plans/PLAN-%s.md%s\n" % (i + 1, e.split(" -- ")[0], e[len(e.split(" -- ")[0]) :])
        for i, e in enumerate(promoted)
    )
    (folder / "QUEUE.md").write_text(
        "# Plan queue\n\n## Settings\n\n%s\n## Promoted\n\n%s" % (settings, lines), encoding="utf-8"
    )
    return str(tmp_path)


def _t(name):
    return "agent/plans/PLAN-%s.md" % name


def test_settings_at_reads_the_working_tree_and_defaults_without_a_file(tmp_path):
    root = _turbo_root(tmp_path, {"a": _xplan()}, ["a"])
    got, problems = plan_gate.settings_at(root)
    assert got.turbo is True
    assert plan_gate.batch_size(got) == 2
    assert problems == []
    empty, problems = plan_gate.settings_at(str(tmp_path / "nowhere"))
    assert empty.turbo is False
    assert plan_gate.batch_size(empty) == 1
    assert problems == []


def test_batch_size_is_one_with_turbo_off(tmp_path):
    root = _turbo_root(
        tmp_path, {"a": _xplan()}, ["a"], "```stop-hook\nturbo: off\nbatch_size: 5\n```\n"
    )
    assert plan_gate.batch_size(plan_gate.settings_at(root)[0]) == 1


def test_next_turbo_names_queue_order_up_to_the_open_slots(tmp_path):
    root = _turbo_root(tmp_path, {"a": _xplan(), "b": _xplan(), "c": _xplan()}, ["a", "b", "c"])
    assert plan_gate.next_turbo(root, (), 2) == [_t("a"), _t("b")]
    assert plan_gate.next_turbo(root, (), 5) == [_t("a"), _t("b"), _t("c")]
    assert plan_gate.next_turbo(root, (), 0) == []


def test_next_turbo_stops_at_plan_concurrency_counting_the_prs_unfinished_plans_and_live_writers(
    tmp_path,
):
    """`plan_concurrency` is the parallelism ceiling (operator 2026-10-04), apart from `batch_size`: the PR's own unfinished plans and the plans live writers serve count against it."""
    three = "```stop-hook\nturbo: on\nbatch_size: 2\nplan_concurrency: 3\n```\n"
    plans = {n: _xplan() for n in "abcde"}
    root = _turbo_root(tmp_path, plans, list("abcde"), three)
    assert plan_gate.plan_concurrency(plan_gate.settings_at(root)[0]) == 3
    assert plan_gate.next_turbo(root, (), 10) == [_t("a"), _t("b"), _t("c")]
    # one unfinished plan in the PR and one live writer's plan leave a single place
    assert plan_gate.next_turbo(root, ("PLAN-d.md",), 10, in_set=(_t("e"),)) == [_t("a")]
    # a finished plan in the PR does not count
    root2 = _turbo_root(
        tmp_path / "f", {**plans, "e": _xplan(opened=0, done=1)}, list("abcde"), three
    )
    assert plan_gate.next_turbo(root2, (), 10, in_set=(_t("e"),)) == [_t("a"), _t("b"), _t("c")]
    # CONTROL: without the key the default is 1, so an empty PR takes one plan
    root3 = _turbo_root(tmp_path / "g", plans, list("abcde"), "```stop-hook\nturbo: on\n```\n")
    assert plan_gate.next_turbo(root3, (), 10) == [_t("a")]


def test_next_turbo_is_empty_with_turbo_off(tmp_path):
    root = _turbo_root(tmp_path, {"a": _xplan(), "b": _xplan()}, ["a", "b"], TURBO_OFF)
    assert plan_gate.next_turbo(root, (), 4) == []


def test_next_turbo_skips_a_held_plan(tmp_path):
    root = _turbo_root(tmp_path, {"h": _xplan(status="held"), "b": _xplan()}, ["h", "b"])
    assert plan_gate.next_turbo(root, (), 4) == [_t("b")]


def test_next_turbo_skips_a_finished_plan(tmp_path):
    root = _turbo_root(tmp_path, {"f": _xplan(opened=0, done=2), "b": _xplan()}, ["f", "b"])
    assert plan_gate.next_turbo(root, (), 4) == [_t("b")]


def test_next_turbo_skips_a_plan_already_in_the_pr_set(tmp_path):
    root = _turbo_root(tmp_path, {"a": _xplan(), "b": _xplan()}, ["a", "b"])
    assert plan_gate.next_turbo(root, (), 4, in_set=(_t("a"),)) == [_t("b")]


def test_next_turbo_picks_the_prerequisite_first(tmp_path):
    root = _turbo_root(tmp_path, {"a": _xplan(depends="PLAN-p.md"), "p": _xplan()}, ["a"])
    assert plan_gate.next_turbo(root, (), 4) == [_t("p")]
    # The prerequisite already rides the PR: the dependent waits for it, nothing else is named.
    assert plan_gate.next_turbo(root, (), 4, in_set=(_t("p"),)) == [_t("a")]


def test_next_turbo_names_a_solo_plan_only_for_an_empty_pr(tmp_path):
    root = _turbo_root(tmp_path, {"s": _xplan(), "b": _xplan()}, ["s -- solo", "b"])
    # An empty PR: the solo plan is the only pick, and nothing joins it.
    assert plan_gate.next_turbo(root, (), 4) == [_t("s")]
    # A PR that already carries a plan never takes the solo one.
    assert plan_gate.next_turbo(root, (), 4, in_set=(_t("x"),)) == [_t("b")]
    # A PR carrying the solo plan takes no further plan.
    assert plan_gate.next_turbo(root, (), 4, in_set=(_t("s"),)) == []


def test_next_turbo_never_pairs_an_exclusive_plan_with_a_live_writers_plan(tmp_path):
    root = _turbo_root(
        tmp_path,
        {
            "e": _xplan(conc="exclusive -- regenerates every golden"),
            "b": _xplan(),
            "live": _xplan(),
        },
        ["e", "b"],
    )
    assert plan_gate.next_turbo(root, ("PLAN-live.md",), 3, in_set=(_t("live"),)) == [_t("b")]
    # Control: with no live writer the exclusive plan is the pick, and it then pairs with nothing.
    assert plan_gate.next_turbo(root, (), 3) == [_t("e")]


def test_next_turbo_never_names_two_plans_claiming_one_file(tmp_path):
    root = _turbo_root(
        tmp_path,
        {"a": _xplan(owns="docs/shared/**"), "b": _xplan(owns="docs/shared/x.md"), "c": _xplan()},
        ["a", "b", "c"],
    )
    assert plan_gate.next_turbo(root, (), 3) == [_t("a"), _t("c")]


def _git_root(tmp_path, queue_text):
    """A git checkout whose committed QUEUE.md is `queue_text`, holding two finished plans."""
    folder = tmp_path / "agent" / "plans"
    folder.mkdir(parents=True)
    for name in ("a", "b"):
        (folder / ("PLAN-%s.md" % name)).write_text(
            _xplan(opened=0, done=2).replace("{name}", name), encoding="utf-8"
        )
    (folder / "QUEUE.md").write_text(queue_text, encoding="utf-8")
    env = {
        "PATH": "/usr/bin:/bin",
        "HOME": str(tmp_path),
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@t",
    }
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True, env=env)
    subprocess.run(["git", "-C", str(tmp_path), "add", "-A"], check=True, env=env)
    subprocess.run(["git", "-C", str(tmp_path), "commit", "-qm", "seed"], check=True, env=env)
    return str(tmp_path)


TWO = "Plan: agent/plans/PLAN-a.md, agent/plans/PLAN-b.md"


def test_turbo_admits_any_count_of_ticked_plans(tmp_path):
    root = _turbo_root(
        tmp_path,
        {
            "a": _xplan(opened=0, done=2),
            "b": _xplan(opened=0, done=1),
            "c": _xplan(opened=0, done=1),
        },
        ["a"],
    )
    assert plan_gate.plan_merge_refusal(root, TWO) == ""
    assert plan_gate.plan_merge_refusal(root, TWO + ", agent/plans/PLAN-c.md") == ""


def test_turbo_refuses_when_the_second_named_plan_is_open(tmp_path):
    root = _turbo_root(
        tmp_path, {"a": _xplan(opened=0, done=2), "b": _xplan(opened=1, done=1)}, ["a"]
    )
    got = plan_gate.plan_merge_refusal(root, TWO)
    assert "PLAN-b.md" in got, got
    assert "open box" in got, got


def test_turbo_checks_every_named_plans_prerequisite(tmp_path):
    root = _turbo_root(
        tmp_path,
        {
            "a": _xplan(opened=0, done=2),
            "b": _xplan(opened=0, done=1, depends="PLAN-p.md"),
            "p": _xplan(),
        },
        ["a"],
    )
    got = plan_gate.plan_merge_refusal(root, TWO)
    assert "PLAN-p.md" in got, got
    assert "prerequisite" in got, got


def test_turbo_on_in_the_tree_but_off_at_the_rev_is_refused(tmp_path):
    root = _git_root(tmp_path, "# Plan queue\n\n## Settings\n\n%s\n## Promoted\n\n" % TURBO_OFF)
    queue = pathlib.Path(root) / "agent" / "plans" / "QUEUE.md"
    queue.write_text(
        "# Plan queue\n\n## Settings\n\n%s\n## Promoted\n\n" % TURBO_ON, encoding="utf-8"
    )
    assert plan_gate.plan_merge_refusal(root, TWO) == ""
    assert "names 2 plans" in plan_gate.plan_merge_refusal(root, TWO, "HEAD")


def test_turbo_off_still_refuses_a_multi_plan_body_and_a_reason_still_admits(tmp_path):
    root = _turbo_root(
        tmp_path, {"a": _xplan(opened=0, done=2), "b": _xplan(opened=1)}, ["a"], TURBO_OFF
    )
    assert "names 2 plans" in plan_gate.plan_merge_refusal(root, TWO)
    assert plan_gate.plan_merge_refusal(root, TWO + "\nOperational-Reason: one PR") == ""


def test_with_plan_line_append_adds_without_duplicating_or_rewriting():
    body = "- **Plan:** `agent/plans/PLAN-a.md`\n\nWork."
    got = plan_gate.with_plan_line(
        body, "agent/plans/PLAN-q.md", append=[_t("b"), _t("a"), _t("b")]
    )
    assert got == "- **Plan:** `agent/plans/PLAN-a.md`, agent/plans/PLAN-b.md\n\nWork.", got
    assert plan_gate.body_plans(got) == [_t("a"), _t("b")]
    # Idempotent: a second push with the same names changes nothing.
    assert plan_gate.with_plan_line(got, "agent/plans/PLAN-q.md", append=[_t("b")]) == got
    # A body with no plan gets the queue head and the named plans on one line.
    assert plan_gate.with_plan_line(
        "Work.", _t("q"), append=[_t("b")]
    ) == "Plan: %s, %s\n\nWork." % (_t("q"), _t("b"))
    # A `Plan:` line inside a generated block is not the body's own, so it is never extended.
    gen = "<!-- worklist-epics:begin -->\nPlan: agent/plans/PLAN-z.md\n<!-- worklist-epics:end -->\nPlan: agent/plans/PLAN-a.md\n"
    assert plan_gate.with_plan_line(gen, "", append=[_t("b")]) == gen.replace(
        "Plan: agent/plans/PLAN-a.md", "Plan: agent/plans/PLAN-a.md, agent/plans/PLAN-b.md"
    )


def test_with_plan_line_without_append_is_the_write_once_link():
    once = plan_gate.with_plan_line("Body text.", _t("a"), append=())
    assert once == plan_gate.with_plan_line("Body text.", _t("a"))
    assert plan_gate.with_plan_line(once, _t("b"), append=()) == once


def test_turbo_named_round_trip(tmp_path, monkeypatch):
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    root = str(tmp_path / "repo")
    pathlib.Path(root).mkdir()
    assert plan_gate.turbo_named(root, "1004-1") == []
    plan_gate.record_turbo_named(root, "1004-1", [_t("a"), _t("b")])
    plan_gate.record_turbo_named(root, "1004-1", [_t("b"), _t("c")])
    plan_gate.record_turbo_named(root, "1004-2", [_t("z")])
    assert plan_gate.turbo_named(root, "1004-1") == [_t("a"), _t("b"), _t("c")]
    assert plan_gate.turbo_named(root, "1004-2") == [_t("z")]


def _refresh_turbo(tmp_path, monkeypatch, body, settings):
    env, work = pbd._world(tmp_path, _patch_table(body))
    plans = work / "repo" / "agent" / "plans"
    plans.mkdir(parents=True)
    (plans / "PLAN-a.md").write_text(OPEN, encoding="utf-8")
    (plans / "QUEUE.md").write_text(
        "## Settings\n\n%s\n## Promoted\n\n1. agent/plans/PLAN-a.md\n" % settings, encoding="utf-8"
    )
    monkeypatch.setenv("TMPDIR", env["TMPDIR"])
    plan_gate.record_turbo_named(str(work / "repo"), pbd.BRANCH, [_t("b"), _t("c")])
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
    return (work / "record.txt").read_text(encoding="utf-8")


def test_refresh_under_turbo_appends_the_named_plans(tmp_path, monkeypatch):
    body = _refresh_turbo(tmp_path, monkeypatch, "Plan: agent/plans/PLAN-x.md\n\nWork.", TURBO_ON)
    assert body.startswith("Plan: agent/plans/PLAN-x.md, %s, %s\n\nWork." % (_t("b"), _t("c"))), (
        body
    )


def test_refresh_with_turbo_off_ignores_the_named_plans(tmp_path, monkeypatch):
    body = _refresh_turbo(tmp_path, monkeypatch, "Plan: agent/plans/PLAN-x.md\n\nWork.", TURBO_OFF)
    assert body.startswith("Plan: agent/plans/PLAN-x.md\n\nWork."), body
    assert "PLAN-b" not in body
