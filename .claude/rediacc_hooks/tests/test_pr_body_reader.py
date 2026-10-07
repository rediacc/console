"""block_raw_pr_body_edit judges the BODY a `gh pr create|edit` sends, whatever flag spelling carries it (#09c80388, from #c17c47c3).

Measured 2026-10-07 through `dispatch.py --chain pre-bash` in a scratch repository, before the fix: `gh pr create --body 'prose only'` rc=2 and `gh pr create -F <file of the same prose>` rc=0; `--body-file -` fed a blockless heredoc rc=0; `printf '<block>' > b.md && gh pr create --body-file b.md` rc=2 over a stale blockless `b.md`, and `printf 'prose' > b.md && ...` rc=0 over a stale `b.md` that carried the block; `gh pr edit 42 -b 'prose'` rc=0.
Each test below states the `--body` verdict first, the control that proves the guard fires at all, then asks the same of a file-borne spelling. The file cases live here rather than in the guard's EDGE_CASES because a golden cannot name a file that exists wherever it is replayed.
"""

from __future__ import annotations

import json
import os
import subprocess

import pytest

from rediacc_hooks import dispatch

STEM = "block_raw_pr_body_edit"
CREATE = "gh pr " + "create --draft --title t"
EDIT = "gh pr " + "edit 42"
BEGIN = "<!-- worklist-epics:begin -->"
# The block as worklist.py now renders it: the PR's epics, then the mandatory backlog section (check-pr-epic-block.ts, bd4388b40). The guard asks only whether the block is there; the section must neither be refused nor stand in for the marker.
BLOCK = (
    "Prose.\n\n"
    + BEGIN
    + "\n## Work\n\n`PR-TASK: abc123`\n\n### Open system backlog (1)\n"
    + "- [ ] `#deadbeef` an item\n<!-- worklist-epics:end -->\n"
)
PROSE = "prose only, no generated block\n"
BACKLOG_ONLY = "Prose.\n\n### Open system backlog (0)\n_none_\n"
ALL_MARKERS = BLOCK + "<!-- pushed-head:begin -->\nx\n<!-- pushed-head:end -->\n"


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "repo"
    (root / "sub").mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(root)], check=True, capture_output=True)
    (root / "nob.md").write_text(PROSE, encoding="utf-8")
    (root / "blk.md").write_text(BLOCK, encoding="utf-8")
    (root / "backlog-only.md").write_text(BACKLOG_ONLY, encoding="utf-8")
    (root / "all.md").write_text(ALL_MARKERS, encoding="utf-8")
    (root / "sub" / "nob.md").write_text(PROSE, encoding="utf-8")
    (root / "sub" / "blk.md").write_text(BLOCK, encoding="utf-8")
    return root


def judge(repo, command, process_cwd=None):
    """rc and stderr of the guard on `command`, with the payload's cwd at `repo` (the harness's spelling)."""
    payload = json.dumps(
        {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": str(repo)}
    )
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(repo))
    rc, _out, err = dispatch.run_one(STEM, payload, cwd=str(process_cwd or repo), env=env)
    return rc, err


def _quote(text):
    return "'" + text.replace("'", "'\\''") + "'"


def test_control_the_inline_body_is_judged(repo):
    rc, err = judge(repo, "%s --body %s" % (CREATE, _quote(PROSE)))
    assert rc == 2, err
    assert "carries no worklist-epics block" in err
    rc, err = judge(repo, "%s --body %s" % (CREATE, _quote(BLOCK)))
    assert rc == 0, err


FILE_SPELLINGS = [
    ("--body-file ABS", lambda r, n: "%s --body-file %s" % (CREATE, r / n)),
    ("--body-file=ABS", lambda r, n: "%s --body-file=%s" % (CREATE, r / n)),
    ("-F ABS", lambda r, n: "%s -F %s" % (CREATE, r / n)),
    ("-FABS", lambda r, n: "%s -F%s" % (CREATE, r / n)),
    ("-dF bundle", lambda r, n: "gh pr " + "create -dF %s" % (r / n)),
    ("--body-file REL", lambda _r, n: "%s --body-file %s" % (CREATE, n)),
    ("cd sub && -F REL", lambda _r, n: "cd sub && %s -F %s" % (CREATE, n)),
    ("$S after S=", lambda r, n: "S=%s; %s --body-file $S/%s" % (r, CREATE, n)),
]


@pytest.mark.parametrize(("label", "build"), FILE_SPELLINGS, ids=[s[0] for s in FILE_SPELLINGS])
def test_a_file_body_is_judged_like_the_same_text_inline(repo, label, build):
    inline_no, _ = judge(repo, "%s --body %s" % (CREATE, _quote(PROSE)))
    inline_yes, _ = judge(repo, "%s --body %s" % (CREATE, _quote(BLOCK)))
    rc, err = judge(repo, build(repo, "nob.md"))
    assert rc == inline_no == 2, "%s admitted a blockless body: %s" % (label, err)
    rc, err = judge(repo, build(repo, "blk.md"))
    assert rc == inline_yes == 0, "%s refused a body carrying the block: %s" % (label, err)


def test_the_backlog_section_is_neither_refused_nor_mistaken_for_the_block(repo):
    for flag in ("--body-file", "-F"):
        rc, err = judge(repo, "%s %s %s" % (CREATE, flag, repo / "blk.md"))
        assert rc == 0, err
        rc, err = judge(repo, "%s %s %s" % (CREATE, flag, repo / "backlog-only.md"))
        assert rc == 2, err


def test_a_relative_file_resolves_from_the_payload_cwd_not_the_process(repo, tmp_path, monkeypatch):
    # The process stands in a directory whose nob.md DOES carry the block; gh runs in the payload's cwd, whose nob.md does not.
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / "nob.md").write_text(BLOCK, encoding="utf-8")
    monkeypatch.chdir(elsewhere)
    rc, err = judge(repo, "%s --body-file nob.md" % CREATE, process_cwd=elsewhere)
    assert rc == 2, err


def test_stdin_bodies(repo):
    rc, err = judge(repo, "%s --body-file - <<'EOF'\n%sEOF" % (CREATE, PROSE))
    assert rc == 2, err
    rc, err = judge(repo, "%s -F - <<'EOF'\n%sEOF" % (CREATE, BLOCK))
    assert rc == 0, err
    rc, err = judge(repo, "%s -F - <<< %s" % (CREATE, _quote(PROSE)))
    assert rc == 2, err
    # A pipe is not readable here: allowed, as every unreadable create body is.
    rc, err = judge(repo, "cat nob.md | %s -F -" % CREATE)
    assert rc == 0, err


def test_unreadable_create_bodies_are_allowed(repo):
    for command in (
        "%s --body-file /nonexistent-pr-body.md" % CREATE,
        "%s -F $UNSET_PR_BODY_DIR/nob.md" % CREATE,
    ):
        rc, err = judge(repo, command)
        assert rc == 0, (command, err)


def test_an_earlier_clause_writing_the_body_file_is_refused_unread(repo):
    # The #c17c47c3 symptom: the command fills nob.md with the block, the stale nob.md lacks it.
    rc, err = judge(
        repo, "printf '%%s' %s > nob.md && %s --body-file nob.md" % (_quote(BEGIN), CREATE)
    )
    assert rc == 2, err
    assert "nothing in this command ran, including `printf > nob.md`" in err
    assert "carries no worklist-epics block" not in err
    # The reverse: a stale blk.md carrying the block no longer admits the prose written over it.
    rc, err = judge(repo, "printf prose > blk.md && %s -F blk.md" % CREATE)
    assert rc == 2, err
    assert "printf > blk.md" in err
    # The same file named by its absolute path in the write, relative in the read.
    rc, err = judge(repo, "printf prose > %s && %s -F blk.md" % (repo / "blk.md", CREATE))
    assert rc == 2, err
    rc, err = judge(repo, "echo prose | tee blk.md && %s -F blk.md" % CREATE)
    assert rc == 2, err
    assert "tee blk.md" in err


def test_a_write_after_the_create_does_not_count(repo):
    rc, err = judge(repo, "%s --body-file blk.md && echo x > blk.md" % CREATE)
    assert rc == 0, err
    rc, err = judge(repo, "%s --body-file blk.md; echo x | tee blk.md" % CREATE)
    assert rc == 0, err


def test_the_edit_arm_reads_every_spelling(repo):
    rc, err = judge(repo, "%s --body-file %s" % (EDIT, repo / "all.md"))
    assert rc == 0, err
    for command in (
        "%s -F %s" % (EDIT, repo / "nob.md"),
        "%s -F %s" % (EDIT, repo / "blk.md"),
        "%s -b %s" % (EDIT, _quote(PROSE)),
        "printf x > all.md && %s -F all.md" % EDIT,
    ):
        rc, err = judge(repo, command)
        assert rc == 2, (command, err)
    rc, err = judge(repo, "%s -F %s" % (EDIT, repo / "all.md"))
    assert rc == 0, err


def test_the_patch_arm_refuses_a_body_file_an_earlier_clause_writes(repo):
    patch = "gh api repos/o/r/pulls/42 -X PATCH -F body=@all.md"
    rc, err = judge(repo, patch)
    assert rc == 0, err
    rc, err = judge(repo, "printf x > all.md && " + patch)
    assert rc == 2, err
    assert "printf > all.md" in err
