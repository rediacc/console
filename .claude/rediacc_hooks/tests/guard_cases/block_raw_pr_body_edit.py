"""The test tables of `block_raw_pr_body_edit`, moved out of the guard so a hook call imports no test data (PLAN-tooling-code-reduction CR5); the guard forwards each name here through `guards._cases.lazy`."""

from rediacc_hooks.wellknown import ACCOUNT_REPO, ELITE_REPO, GH_REPO, RENET_REPO

EDGE_CASES = [
    ("the sanctioned tool", "PYTHONPATH=.ci python3 -m rediacc_ci.pr.sync_epic_block 42 0831-1"),
    ("an edit with no body flag", "gh pr edit 42 --add-label ci"),
    ("an edit dropping every block", 'gh pr edit 42 --body "prose with no block at all"'),
    # The 2026-09-03 correction: the epic block ALONE is not enough.
    (
        "an edit carrying ONLY the epic block still drops pushed-head",
        'gh pr edit 42 --body "x <!-- worklist-epics:begin --> y"',
    ),
    (
        "an edit carrying EVERY generated marker passes",
        'gh pr edit 42 --body "x <!-- worklist-epics:begin --> y <!-- pushed-head:begin --> z"',
    ),
    # The 2026-09-04 arm: the door this guard's own message points at.
    (
        "a PATCH with no readable body file",
        "gh api repos/o/r/pulls/42 -X PATCH -F body=@/nonexistent-body.md",
    ),
    (
        "a PATCH carrying every marker inline",
        (
            "gh api repos/o/r/pulls/42 -X PATCH -f body='<!-- worklist-epics:begin --> "
            "<!-- pushed-head:begin -->'"
        ),
    ),
    ("a PATCH with no body field at all", "gh api repos/o/r/pulls/42 -X PATCH -f title=x"),
    ("a GET is not a PATCH", "gh api repos/o/r/pulls/42"),
    # create: the hole measured 2026-08-27.
    ("a create with no body flag", "gh pr create --draft --title t --fill"),
    ("a create whose body drops the block", 'gh pr create --draft --body "x"'),
    (
        "a create whose body carries the block",
        'gh pr create --draft --body "x <!-- worklist-epics:begin --> y"',
    ),
    ("a create with an unreadable body file", "gh pr create --draft --body-file /nonexistent.md"),
    # 2026-10-07 (#09c80388): the verdict followed the flag's SPELLING, not the body. File-based halves are in test_pr_body_reader.py.
    ("a create by -b with no block", 'gh pr create --draft -b "prose only"'),
    (
        "a create by -b carrying the block",
        'gh pr create --draft -b "x <!-- worklist-epics:begin --> y"',
    ),
    (
        "a create reading a heredoc on stdin with no block",
        "gh pr create --draft --body-file - <<'EOF'\nprose only\nEOF",
    ),
    (
        "a create reading a heredoc on stdin carrying the block",
        "gh pr create --draft -F - <<'EOF'\nx\n<!-- worklist-epics:begin -->\nEOF",
    ),
    (
        "a create whose body file an earlier clause writes",
        (
            "printf '%s' '<!-- worklist-epics:begin -->' > /nonexistent-pr-body.md && "
            "gh pr create --draft --body-file /nonexistent-pr-body.md"
        ),
    ),
    (
        "a write AFTER the create cannot change what it read",
        (
            "gh pr create --draft --body-file /nonexistent-pr-body.md && "
            "echo x > /nonexistent-pr-body.md"
        ),
    ),
    ("an edit by -F", "gh pr edit 42 -F /nonexistent.md"),
    ("an edit by -b", 'gh pr edit 42 -b "prose only"'),
    (
        "a PATCH whose body file an earlier clause writes",
        (
            "printf x > /nonexistent-pr-body.md && "
            "gh api repos/o/r/pulls/42 -X PATCH -F body=@/nonexistent-pr-body.md"
        ),
    ),
    # ORDER MATTERS: the edit arm runs FIRST.
    (
        "a create that passes, then an edit that does not",
        'gh pr create --draft --body "x <!-- worklist-epics:begin --> y" && gh pr edit 5 --body "z"',
    ),
    # THE FLAG BELONGS TO ITS OWN INVOCATION.
    (
        "a body on create and a label on edit",
        (
            'gh pr create --draft --body "x <!-- worklist-epics:begin --> y '
            '<!-- pushed-head:begin --> z" && gh pr edit 5 --add-label ci'
        ),
    ),
    # Prose about the rule is not the rule being broken.
    ("prose naming the flag", "echo 'never use gh pr edit --body by hand'"),
    # 2026-09-30: a submodule PR carries no generated block, so there is none to drop.
    (
        "a submodule PATCH with a blockless body",
        ("gh api repos/" + RENET_REPO + "/pulls/113 -X PATCH -f body='prose only'"),
    ),
    (
        "a console PATCH with the same blockless body is still refused",
        ("gh api repos/" + GH_REPO + "/pulls/591 -X PATCH -f body='prose only'"),
    ),
    (
        "a submodule PATCH beside a console one: the console one is judged",
        (
            "gh api repos/"
            + RENET_REPO
            + "/pulls/113 -X PATCH -f body=x; "
            + "gh api repos/"
            + GH_REPO
            + "/pulls/591 -X PATCH -f body=y"
        ),
    ),
    (
        "a submodule edit by --repo",
        ("gh pr edit 113 --repo " + RENET_REPO + ' --body "prose only"'),
    ),
    ("a submodule edit by -R", ("gh pr edit 89 -R " + ACCOUNT_REPO + ' --body "prose only"')),
    # 2026-10-07 (#8ed364fe): every spelling gh accepts means what gh makes of it.
    ("a submodule edit by -R=", ("gh pr edit 89 -R=" + ACCOUNT_REPO + ' -b "prose only"')),
    ("a PATCH spelled -XPATCH", "gh api repos/o/r/pulls/42 -XPATCH -f body='prose only'"),
    ("a PATCH spelled --method=PATCH", "gh api repos/o/r/pulls/42 --method=PATCH -fbody=x"),
    ("a PATCH by --raw-field=body=", "gh api repos/o/r/pulls/42 -X PATCH --raw-field=body=x"),
    (
        "a PATCH of a review's own body is not the PR body",
        "gh api repos/o/r/pulls/42/reviews/9 -X PATCH -f body=x",
    ),
    ("a console edit by --repo", ("gh pr edit 591 --repo " + GH_REPO + ' --body "prose only"')),
    (
        "a submodule create",
        ("gh pr create --repo " + ELITE_REPO + ' --title t --body "prose only"'),
    ),
    (
        "a submodule create does not excuse a console edit beside it",
        ("gh pr create --repo " + RENET_REPO + ' --body "x" && gh pr edit 5 --body "y"'),
    ),
]
