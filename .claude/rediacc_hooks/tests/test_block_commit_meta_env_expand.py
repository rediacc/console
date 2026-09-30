"""block_commit_meta reads a body file named through an INHERITED variable (#378c645c).

`--body-file $HOME/pr.md` names a variable no statement in the command assigns. Before the fix `_expand` consulted only same-command assignments, so the name stayed `$HOME/pr.md`, no such file existed, and the footer inside it passed unread. These cases run the guard in-process with a chosen environment, so the file really exists at the expanded path; the differential's `home-bodies` variant freezes the same verdicts into the golden.
"""

import json

from rediacc_hooks import dispatch, guards
from rediacc_hooks.tests import goldenio

STEM = "block_commit_meta"
# Assembled from parts: a source line spelling the footer out is itself one.
FOOTER = "\U0001f916 " + "Generated " + "with [Claude Code](https://claude.com/claude-code)"
TRAILER = "Co-" + "Authored-By: Claude <noreply@anthropic.com>"
CREATE = "gh pr " + "create"


def _verdict(cmd, env, cwd):
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd}})
    rc, _out, _err = dispatch.run_one(STEM, payload, cwd=str(cwd), env=env)
    return rc


def _world(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    (home / "footer.md").write_text("prose\n\n%s\n" % FOOTER, encoding="utf-8")
    (home / "trailer.md").write_text("fix: x\n\n%s\n" % TRAILER, encoding="utf-8")
    (home / "clean.md").write_text("prose\n\nConsole PR: x.\n", encoding="utf-8")
    env = {
        "HOME": str(home),
        "CLAUDE_PROJECT_DIR": str(goldenio.REPO_ROOT),
        "PATH": "/usr/bin:/bin",
    }
    return home, env


def test_an_inherited_home_body_with_the_footer_is_refused(tmp_path):
    _home, env = _world(tmp_path)
    assert _verdict("%s --title t --body-file $HOME/footer.md" % CREATE, env, tmp_path) == 2
    assert _verdict("git commit -F ${HOME}/trailer.md -- a", env, tmp_path) == 2
    assert (
        _verdict("gh api repos/o/r/pulls/7 -X PATCH -F body=@$HOME/footer.md", env, tmp_path) == 2
    )


def test_a_clean_inherited_body_passes(tmp_path):
    """The control on the other side: the same spelling with a clean file is admitted, so the refusal above is the file's bytes and not the `$HOME` spelling."""
    _home, env = _world(tmp_path)
    assert _verdict("%s --title t --body-file $HOME/clean.md" % CREATE, env, tmp_path) == 0


def test_an_unset_variable_fails_open(tmp_path):
    """Unresolvable names are admitted, as the guard's `_expand` docstring says and why."""
    _home, env = _world(tmp_path)
    cmd = "%s --title t --body-file $COMMIT_META_UNSET_VAR/footer.md" % CREATE
    assert _verdict(cmd, env, tmp_path) == 0


def test_a_same_command_assignment_wins_over_the_environment(tmp_path):
    home, env = _world(tmp_path)
    shadowed = "HOME=/nonexistent; %s --title t --body-file $HOME/footer.md" % CREATE
    assert _verdict(shadowed, env, tmp_path) == 0
    # And an assigned value that itself names an inherited variable resolves through it.
    nested = "S=$HOME; %s --title t --body-file $S/footer.md" % CREATE
    assert _verdict(nested, env, tmp_path) == 2
    assert str(home) == env["HOME"]


def test_the_pre_fix_expansion_left_the_name_unread():
    """CONTROL: the names-only lookup the guard had before #378c645c leaves `$HOME/x` unexpanded, which is the fail-open these tests close."""
    module = guards.load(STEM)

    def no_env(_name, fallback=None):
        return fallback

    assert module._expand("$HOME/footer.md", {}, no_env) == "$HOME/footer.md"
    assert module._expand("$HOME/footer.md", {}, {"HOME": "/h"}.get) == "/h/footer.md"
    assert module._expand("${HOME}/f", {"HOME": "/a"}, {"HOME": "/h"}.get) == "/a/f"
