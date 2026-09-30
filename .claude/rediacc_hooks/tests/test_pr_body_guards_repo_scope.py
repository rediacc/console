"""Two pre-bash PR-body guards against the two 2026-09-30 submodule PR defects, with real body files.

block_raw_pr_body_edit refused `gh api repos/rediacc/renet/pulls/113 -X PATCH -F body=@<file>` for dropping generated blocks that only console PR bodies carry. block_commit_meta refused the console `gh pr create --body-file <file>` carrying the attribution footer and admitted the renet and account ones: those named their file `$S/pr-renet.md`, after `S=<dir>;` in the same command, and a file
literally named `$S/pr-renet.md` does not exist, so the read failed open. The file-based halves live here because a guard's EDGE_CASES cannot name a file that exists wherever the golden is replayed; the inline halves are EDGE_CASES in the two guard modules.
"""

import pytest

from rediacc_hooks.tests import hookblocks, hookcases

bash_json = hookcases.bash_json

# Assembled from parts, for the reason test_hooks_fixtures.py gives: a source line spelling the footer out is itself one.
FOOTER = "\U0001f916 " + "Generated " + "with [Claude Code](https://claude.com/claude-code)"
TOKEN = "Co-" + "Authored-By"
TRAILER = TOKEN + ": Claude <noreply@anthropic.com>"
CREATE = "gh pr " + "create"


@pytest.mark.xdist_group("hooks-fixtures")
def test_block_raw_pr_body_edit_admits_submodule_whole_body_writes(tmp_path):
    block = hookblocks.Block("raw-pr-body-repo-scope")
    plain = tmp_path / "plain.md"
    plain.write_text("prose with no generated block\n", encoding="utf-8")
    spec_deny = "check 2 guards/block_raw_pr_body_edit.py"
    spec_allow = "check 0 guards/block_raw_pr_body_edit.py"
    for repo in ("rediacc/renet", "rediacc/account", "rediacc/elite", "rediacc/homebrew-tap"):
        block.check(
            spec_allow,
            bash_json("gh api repos/%s/pulls/113 -X PATCH -F body=@%s" % (repo, plain)),
            "raw-pr-body-repo-scope: a %s PATCH has no generated block to drop" % repo,
        )
    block.check(
        spec_deny,
        bash_json("gh api repos/rediacc/console/pulls/591 -X PATCH -F body=@%s" % plain),
        "raw-pr-body-repo-scope CONTROL: the same PATCH to the console PR is refused",
    )
    block.check(
        spec_deny,
        bash_json("gh api repos/o/r/pulls/42 -X PATCH -F body=@%s" % plain),
        "raw-pr-body-repo-scope CONTROL: a repo the deny-list cannot name keeps the guard",
    )
    block.check(
        spec_allow,
        bash_json("gh pr edit 113 --repo rediacc/renet --body-file %s" % plain),
        "raw-pr-body-repo-scope: a submodule edit by --repo is admitted",
    )
    block.check(
        spec_allow,
        bash_json("gh pr edit 89 -R rediacc/account --body-file %s" % plain),
        "raw-pr-body-repo-scope: a submodule edit by -R is admitted",
    )
    block.check(
        spec_deny,
        bash_json("gh pr edit 591 --body-file %s" % plain),
        "raw-pr-body-repo-scope CONTROL: an edit naming no repo defaults to the console",
    )
    block.check(
        spec_allow,
        bash_json("%s --repo rediacc/renet --title t --body-file %s" % (CREATE, plain)),
        "raw-pr-body-repo-scope: a submodule create needs no epic block",
    )
    block.check(
        spec_deny,
        bash_json("%s --repo rediacc/console --title t --body-file %s" % (CREATE, plain)),
        "raw-pr-body-repo-scope CONTROL: a console create still needs its epic block",
    )
    block.done()


@pytest.mark.xdist_group("hooks-fixtures")
def test_block_commit_meta_reads_the_body_in_every_repo_and_flag_order(tmp_path):
    block = hookblocks.Block("commit-meta-repo-scope")
    footer_md = tmp_path / "pr-renet.md"
    footer_md.write_text("prose\n\nConsole PR: x.\n\n%s\n" % FOOTER, encoding="utf-8")
    trailer_md = tmp_path / "trailer.md"
    trailer_md.write_text("prose\n\n%s\n" % TRAILER, encoding="utf-8")
    clean_md = tmp_path / "clean.md"
    clean_md.write_text("prose\n\nConsole PR: x.\n", encoding="utf-8")
    spec_deny = "check 2 guards/block_commit_meta.py"
    spec_allow = "check 0 guards/block_commit_meta.py"
    s = "S=%s; " % tmp_path
    for repo in ("rediacc/renet", "rediacc/account", "rediacc/console"):
        for order, cmd in (
            ("--repo first", "%s --repo %s --title t --body-file %s" % (CREATE, repo, footer_md)),
            (
                "--body-file first",
                "%s --body-file %s --repo %s --title t" % (CREATE, footer_md, repo),
            ),
        ):
            block.check(
                spec_deny,
                bash_json(cmd),
                "commit-meta-repo-scope: %s, literal path, %s" % (repo, order),
            )
    # THE MEASURED SHAPE: the path behind a variable assigned earlier in the same command.
    block.check(
        spec_deny,
        bash_json(
            s + "%s --repo rediacc/renet --head 0930-1 --base main --title t --body-file "
            "$S/pr-renet.md; %s --repo rediacc/account --head 0930-1 --base main --title t "
            "--body-file $S/pr-renet.md" % (CREATE, CREATE)
        ),
        "commit-meta-repo-scope: $S/<file> after S=<dir>; is read (renet#113, account#89)",
    )
    block.check(
        spec_deny,
        bash_json(s + "%s --body-file ${S}/pr-renet.md -R rediacc/account --title t" % CREATE),
        "commit-meta-repo-scope: ${S}/<file> and -R, body flag first",
    )
    block.check(
        spec_deny,
        bash_json(s + "gh api repos/rediacc/renet/pulls/113 -X PATCH -F body=@$S/pr-renet.md"),
        "commit-meta-repo-scope: the PATCH door reads -F body=@$S/<file> too",
    )
    block.check(
        spec_deny,
        bash_json("gh pr edit 113 --repo rediacc/renet --body-file %s" % trailer_md),
        "commit-meta-repo-scope: the trailer in a submodule edit's body file",
    )
    block.check(
        spec_allow,
        bash_json(s + "%s --repo rediacc/renet --title t --body-file $S/clean.md" % CREATE),
        "commit-meta-repo-scope CONTROL: a clean $S/<file> body passes",
    )
    block.check(
        spec_allow,
        bash_json("%s --repo rediacc/renet --title t --body-file $UNSET/pr.md" % CREATE),
        "commit-meta-repo-scope CONTROL: a variable nothing assigns is unreadable, as before",
    )
    block.done()
