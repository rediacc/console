"""The test tables of `block_commit_meta`, moved out of the guard so a hook call imports no test data (PLAN-tooling-code-reduction CR5); the guard forwards each name here through `guards.tables`."""

import pathlib

from rediacc_hooks.wellknown import RENET_REPO

# A body file reached ONLY through an inherited variable (#378c645c). The differential's `_base_env` passes the runner's real HOME, where these files do not exist, so the `home-bodies` variant points HOME at this fixture instead: the same `$HOME/...` payloads are admitted under `default` (no file to read) and judged on their bytes here. The footer is assembled so no source line is itself one.
HOME_BODIES = ".commit-meta-bodies"


def _home_fixture(path):
    bodies = pathlib.Path(path) / HOME_BODIES
    bodies.mkdir(parents=True)
    footer = "\U0001f916 " + "Generated" + " with [Claude Code](u)"
    (bodies / "footer.md").write_text("prose\n\n%s\n" % footer, encoding="utf-8")
    (bodies / "clean.md").write_text("prose\n\nConsole PR: x.\n", encoding="utf-8")
    session = "Claude-" + "Session: https://claude" + ".ai/code/session_01AbCd"
    (bodies / "session.md").write_text("prose\n\n%s\n" % session, encoding="utf-8")
    return path


FIXTURES = {"commit-meta-home": _home_fixture}


# `default` first and with no extras, so every record it already froze keeps its key.
ENVS: list[tuple[str, dict[str, str], dict[str, str]]] = [
    ("default", {}, {}),
    ("home-bodies", {"HOME": "{FIXTURE:commit-meta-home}"}, {}),
]


EDGE_CASES = [
    ("a tag message carries the same rule", "git tag -a v1 -m Co-Authored-By:bot"),
    # The audit shapes the 2026-08-27 gate exists to let through.
    ("grepping the docs for the trailer", "grep -rn 'Co-Authored-By:' docs/"),
    ("prose naming the rule", "echo 'the rule bans Co-Authored-By: lines'"),
    # The clause-crossing gap.
    (
        "a git verb and the word commit in different clauses",
        "git log | grep commit | grep Co-Authored-By:",
    ),
    # `Generated with` keeps its line anchor, so it needs a real line start.
    ("a footer at the start of a message line", 'git commit -m "fix\n\nGenerated with a robot"'),
    ("the same footer mid-line is prose", 'git commit -m "regenerated with npm@10"'),
    ("an ordinary commit", "git commit -m 'fix(cli): x'"),
    # 2026-09-30: a body file this same command writes is judged on the command's own bytes, in any repo and either flag order. The footer is assembled so this source line is not itself one.
    (
        "a submodule create whose body file this command writes with the footer",
        (
            "S=/tmp/pb; printf '%s\\n' 'prose' '' '\U0001f916 "
            "Generated with [Claude Code](u)' > $S/pr.md; "
            "gh pr create --repo " + RENET_REPO + " --title t --body-file $S/pr.md"
        ),
    ),
    (
        "the same with --body-file before --repo",
        (
            "S=/tmp/pb; printf '%s\\n' 'prose' '' '\U0001f916 "
            "Generated with [Claude Code](u)' > $S/pr.md; "
            "gh pr create --body-file $S/pr.md --repo " + RENET_REPO + " --title t"
        ),
    ),
    (
        "the same written body without the footer passes",
        (
            "S=/tmp/pb; printf '%s\\n' 'prose' '' 'Console PR: x.' > $S/pr.md; "
            "gh pr create --repo " + RENET_REPO + " --title t --body-file $S/pr.md"
        ),
    ),
    (
        "a quoted phrase in an inline --body is prose, not a footer",
        (
            "gh pr create --repo "
            + RENET_REPO
            + " --title t --body 'refuses \"Generated with\" lines'"
        ),
    ),
    # #378c645c: a body file named through a variable the command never assigns. Refused under `home-bodies`, where the file carries the footer; admitted under `default`, where it does not exist.
    (
        "an inherited $HOME body file with the footer",
        "gh pr create --title t --body-file $HOME/%s/footer.md" % HOME_BODIES,
    ),
    ("the braced ${HOME} spelling on a commit", "git commit -F ${HOME}/%s/footer.md" % HOME_BODIES),
    (
        "the gh api body spelling",
        "gh api repos/o/r/pulls/7 -X PATCH -F body=@$HOME/%s/footer.md" % HOME_BODIES,
    ),
    # 2026-10-07 (#8ed364fe): every spelling git and gh accept for a message file is read.
    ("an attached -F on a commit", "git commit -F$HOME/%s/footer.md -- a" % HOME_BODIES),
    ("a bundled -qF on a commit", "git commit -qF $HOME/%s/footer.md -- a" % HOME_BODIES),
    ("an attached -F on a tag", "git tag -a v1 -F$HOME/%s/footer.md" % HOME_BODIES),
    ("a bundled -dF on a create", "gh pr create -dF $HOME/%s/footer.md -t x" % HOME_BODIES),
    (
        "an attached -Fbody=@ on a PATCH",
        "gh api repos/o/r/pulls/7 -XPATCH -Fbody=@$HOME/%s/footer.md" % HOME_BODIES,
    ),
    (
        "a merge body file is the merge commit's message",
        "gh pr merge 7 --squash --body-file $HOME/%s/footer.md" % HOME_BODIES,
    ),
    (
        "an inherited $HOME body file without the footer",
        "gh pr create --title t --body-file $HOME/%s/clean.md" % HOME_BODIES,
    ),
    # 2026-10-30 (PR-TASK 9f92c43e): a Claude session link or session trailer, through every publishing channel; the audit shapes stay legal. Assembled, so no source line is itself one.
    ("a session trailer in an inline commit", "git commit -m fix -m 'Claude-" + "Session: x' -- a"),
    (
        "the Claude-Code-Session spelling as a --trailer",
        "git commit -m fix --trailer Claude-Code-" + "Session=x",
    ),
    (
        "a chat link in a PR body",
        "gh pr create -t t --body 'see https://claude" + ".ai/chat/1a2b-3c4d'",
    ),
    (
        "a session link in a PR comment",
        "gh pr comment 5 -b 'https://claude" + ".ai/code/session_01Ab'",
    ),
    (
        "a session link in an issue comment",
        "gh issue comment 5 --body 'claude" + ".ai/code/session_01Ab'",
    ),
    (
        "a share link in a gh api comment field",
        "gh api repos/o/r/issues/5/comments -f body='claude" + ".ai/share/ab1'",
    ),
    (
        "a session trailer in a PR comment body file",
        "gh pr comment 5 --body-file $HOME/%s/session.md" % HOME_BODIES,
    ),
    (
        "a session trailer in a commit -F file",
        "git commit -F $HOME/%s/session.md -- a" % HOME_BODIES,
    ),
    (
        "a session trailer in a gh api -F body=@ file",
        "gh api repos/o/r/pulls/7 -X PATCH -F body=@$HOME/%s/session.md" % HOME_BODIES,
    ),
    (
        "a session trailer read through $(cat)",
        'git commit -m "$(cat $HOME/%s/session.md)" -- a' % HOME_BODIES,
    ),
    ("searching the log for claude.ai is an audit", "git log --oneline --grep claude" + ".ai"),
    ("grepping for the session trailer is an audit", "grep -rn 'Claude-" + "Session:' docs/"),
    (
        "a commit naming the session rule is prose",
        (
            "git commit -m 'fix: refuse the Claude-"
            "Session trailer and claude.ai/code/session_<id> links' -- a"
        ),
    ),
    # Unset in every environment the differential runs: the name stays unresolved and fails open.
    (
        "an unset variable's body file is admitted",
        "gh pr create --title t --body-file $COMMIT_META_UNSET_VAR/%s/footer.md" % HOME_BODIES,
    ),
    # A same-command assignment wins over the environment, as in bash: this HOME has no body file.
    (
        "a same-command assignment shadows the inherited value",
        "HOME=/nonexistent; gh pr create --title t --body-file $HOME/%s/footer.md" % HOME_BODIES,
    ),
]
