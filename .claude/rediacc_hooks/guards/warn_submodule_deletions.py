"""WARN (never block) when a commit would carry a staged deletion of tracked files inside a submodule.

Why warn and not block: removing a file from a submodule is ordinary work, so a guard that refuses it would be wrong most of the times it fires, and a guard whose usual outcome is a false positive teaches people to route around it. What is worth surfacing is the case where the deletion is not YOURS: a submodule checkout carried a staged `rm` of Formula/rediacc-cli.rb and README.md
-- the entire content of rediacc/homebrew-tap -- from before the session that found it. It sat unnoticed for hours because the parent reports only "m private/homebrew-tap", with no per-file detail, and `git status` in the parent never shows what was staged inside.

Committing that would have deleted the published Homebrew formula.

Exit 0 ALWAYS. This hook's only job is to put the paths in front of you.

PORT NOTE ON THE PROCESS SUBSTITUTION. The bash feeds its loop with
`done < <(git config -f .gitmodules --get-regexp path | awk '{print $2}')`
rather than a pipe, and the choice is load-bearing in bash for the same reason block-binary-deploy.sh records: a piped `while` runs in a SUBSHELL, so `found` would be accumulated in a child and thrown away, and the guard would report nothing while looking correct. Neither the subshell nor the redirection exists in Python, so this paragraph is the only surviving record of why the
original is spelled the way it is.

PORT NOTE ON WHERE THE `git` CALLS RUN. The bash `cd`s once, to the toplevel it just resolved, and every later `git -C "$sub"` is therefore relative to that
directory. The port passes `cwd=root` on each call instead of moving this
process, because a chained dispatcher runs several guards in one interpreter and a guard that chdir'd would move the ones after it.

FINDING, CARRIED ACROSS RATHER THAN FIXED. This guard matches its `git commit` on the RAW command, not on `hook_scan_target`, so `echo "git commit"` -- a worklist note, a doc line, a message explaining the rule -- reaches the submodule scan and can produce the note. Its neighbour warn-stale-index.sh routes through lib/command-scan.sh for exactly this reason and says so in its own
header. The cost here is one spurious advisory rather than a refused command, which is presumably why it was never chased; the edge case below pins the behaviour so a future change to it is a decision and not an accident.
"""

import os

from rediacc_hooks import hookio
from rediacc_hooks.guards import tables

__getattr__ = tables(
    "warn_submodule_deletions",
    "EDGE_CASES",
    "ENVS",
    "FIXTURES",
    "_SUBMODULES",
    "_fixture_git",
    "_submodule_tree",
)

CHAIN = "pre-bash"
ORDER = 6

# Without the "did anything get deleted" test every submodule in .gitmodules is reported, with `wc -l` counting the empty string as one line -- so a clean checkout is announced as having one of its files staged for deletion, and the loudest arm ("this is EVERY tracked file") fires on a submodule where nothing was touched at all.
DEFECT = ('if dels == "":\n            continue', "if False:\n            continue")

# `(^|[;&|[:space:]])git[[:space:]]+(-C[[:space:]]+\\S+[[:space:]]+)?commit\\b` -- only interesting just before a commit is created. The optional `-C <path>` arm is what lets a submodule commit typed from the parent match.
COMMIT = hookio.rx(r"(^|[;&|{S}])git[{S}]+(-C[{S}]+\S+[{S}]+)?commit\b")


def run(ev):
    cmd = ev.raw("tool_input", "command")

    # `echo "$CMD" | grep -qE ...` -- echo, so the subject carries a newline and an empty command is one empty record rather than none.
    if not hookio.grep_q_line(COMMIT, cmd):
        return hookio.ALLOW

    root = hookio.git_out(["rev-parse", "--show-toplevel"], want_rc=True)
    if root is None:
        return hookio.ALLOW
    if not os.path.isdir(root):
        # `cd "$ROOT" 2>/dev/null || exit 0`
        return hookio.ALLOW
    if not os.path.isfile("%s/.gitmodules" % root):
        return hookio.ALLOW

    paths = hookio.git_out(["config", "-f", ".gitmodules", "--get-regexp", "path"], cwd=root)
    found = ""
    for sub in hookio.awk_field(hookio._printf_line(paths), 2).split("\n"):
        if sub == "":
            continue
        if not os.path.exists("%s/%s/.git" % (root, sub)):
            continue
        # --cached: what is STAGED for the submodule's next commit, which is exactly what the parent's status cannot show you.
        dels = hookio.git_out(
            ["-C", sub, "diff", "--cached", "--name-only", "--diff-filter=D"], cwd=root
        )
        if dels == "":
            continue
        listing = hookio.git_out(["-C", sub, "ls-tree", "-r", "HEAD", "--name-only"], cwd=root)
        # `| wc -l` counts NEWLINES, so an empty listing is 0 and a listing of n entries is n. That is not the same as counting split records, which would answer 1 for the empty string.
        tracked = hookio._printf_line(listing).count("\n") if listing != "" else 0
        ndel = hookio._printf_line(dels).count("\n")
        indented = hookio._command_substitution(
            hookio.sed_sub(r"^", "      ", hookio._printf_line(dels))
        )
        found += "\n  %s: %d of %d tracked file(s) staged for deletion\n%s" % (
            sub,
            ndel,
            tracked,
            indented,
        )
        # The loudest case: the deletion would empty the submodule.
        if ndel >= tracked > 0:
            found += "\n      ^^ this is EVERY tracked file in that submodule"

    if found != "":
        ev.warn("⚠️  NOTE: a submodule has staged DELETIONS. Not blocking; look before you commit.")
        ev.warn(found)
        ev.warn("")
        ev.warn("  If they are not yours, restore from HEAD rather than committing them:")
        ev.warn("    git -C <submodule> show HEAD:<path> > <path> && git -C <submodule> add <path>")
    return hookio.ALLOW
