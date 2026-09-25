"""Refuse `[no-review]` on a commit that is not purely writing, and on any `[hotfix]`.

WHY (the commit-policy plan in agent/plans, section 4.2). The per-commit reviewer reads every commit by default. `[no-review]` makes a skip EXPLICIT for the one class where a review adds little: writing. The eligible set is `no_review_eligible` in `.ci/config/commit-policy.json` -- `agent/**`, `docs/**` and `**/*.md` -- minus `no_review_denied`: `.claude/**` holds agent programs (commands, agents, output styles, skills) and `CLAUDE.md` is policy, so neither is writing in the sense that matters. A commit that is eligible but untagged is reviewed anyway, which costs little; the tag only ever narrows.

`[hotfix]` IS NEVER `[no-review]` (operator ruling 1, 2026-09-25). A hotfix lands on `main` without a PR, so the per-commit review is the only review it gets.

CHECKED TWICE: here, at commit time, against the pathspec (or the index when there is none, and the worktree too under `-a`); and again by the reviewer, which writes `Verdict: skipped (no-review)` only after re-checking eligibility against `git show --name-only <sha>`. A gitlink-only commit needs no tag at all; the reviewer already skips it.
"""

from rediacc_hooks import commit_policy, hookio

CHAIN = "pre-bash"
OWN_SUITE = True
ORDER = 48

# Eligibility itself. With it forced true every path rides a `[no-review]`.
DEFECT = (
    "eligible, offenders = commit_policy.no_review_eligible(paths, cfg)",
    "eligible, offenders = True, []",
)

EDGE_CASES = [
    ("a code path", 'git commit -m "feat: x [no-review]" -- src/a.ts'),
    ("an agent program", 'git commit -m "docs: x [no-review]" -- .claude/commands/x.md'),
    ("policy", 'git commit -m "docs: x [no-review]" -- CLAUDE.md'),
    ("writing only", 'git commit -m "docs: x [no-review]" -- agent/plans/x.md docs/y.md'),
    (
        "a hotfix is always reviewed",
        'git commit -m "docs: x [hotfix] [no-review]\n\nHotfix-Evidence: 12345678" -- docs/y.md',
    ),
    ("an untagged code commit", 'git commit -m "feat: x" -- src/a.ts'),
    ("prose naming the tag", "echo 'tag it [no-review]'"),
]


def _refuse(ev, what):
    ev.warn_raw(
        "BLOCKED: %s\n"
        "\n"
        "`[no-review]` is for commits that are purely writing: every path under\n"
        "`agent/**` or `docs/**`, or a `*.md` outside `.claude/` (and never CLAUDE.md).\n"
        "`.claude/**` holds agent programs and is always reviewed; so is every `[hotfix]`.\n"
        "Drop the tag; an untagged commit is simply reviewed, which costs little. Or split\n"
        "the writing into its own commit.\n" % what
    )
    return hookio.DENY


def run(ev):
    cmd = ev.raw("tool_input", "command")
    if cmd in ("", "null"):
        return hookio.ALLOW
    commits = commit_policy.git_runs(cmd, "commit")
    if not commits:
        return hookio.ALLOW
    root = ev.env("CLAUDE_PROJECT_DIR") or hookio.git_out(["rev-parse", "--show-toplevel"])
    base = ev.field("cwd") or root
    cfg = commit_policy.load_config(root)
    for commit in commits:
        repo = commit_policy.run_repo(commit, base)
        # A directory that resolves to no repository is one git itself will refuse; one outside this checkout is not this policy's business.
        if not repo or not commit_policy.is_inside(repo, root):
            continue
        found = commit_policy.tags(commit_policy.commit_message_text(cmd, base, run=commit))
        if "no-review" not in found:
            continue
        if "hotfix" in found:
            return _refuse(ev, "a `[hotfix]` carries `[no-review]`. Hotfixes are always reviewed.")
        paths = commit_policy.judged_paths(commit, cmd, repo, base)
        eligible, offenders = commit_policy.no_review_eligible(paths, cfg)
        if not eligible:
            shown = ", ".join(offenders[:8]) or "(no path could be read)"
            more = " and %d more" % (len(offenders) - 8) if len(offenders) > 8 else ""
            return _refuse(ev, "`[no-review]` on paths that are not writing: %s%s." % (shown, more))
    return hookio.ALLOW
