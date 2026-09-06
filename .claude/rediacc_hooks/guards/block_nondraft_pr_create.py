"""Enforce the draft-PR flow on `gh pr create`.

The org is on the GitHub FREE plan: draft PRs exist only on PUBLIC repos.
console + homebrew-tap are public -> their PRs MUST be created as drafts
(the PR stays draft until CI is green; `gh pr ready` is gated by
block-premature-ready.sh). renet/account/elite are private -> GitHub
rejects --draft there, so the hook blocks it up front with a real message
instead of letting the API fail cryptically.

Target-repo resolution order: explicit --repo/-R flag > a cd/`git -C` into a
private/<submodule> path inside the command > the session cwd's origin
remote. Unknown/foreign repos are not policed.

PORT NOTE ON THE LOOP'S FEED. `done <<<"$(hook_gh_pr_segment ...)"` is a
here-string, so the segment list arrives with exactly one trailing newline
whatever the substitution stripped, and `read` therefore always sees a final
record. That is why the records below are taken from `_here_string(segs)` and
not from `segs` itself: on a single segment with no trailing newline the two
differ by one iteration, which is the whole loop.
"""

from rediacc_hooks import hookio, shellscan

CHAIN = "pre-bash"
TWIN = "pre-bash/block-nondraft-pr-create.sh"
ORDER = 23

# Reading `--draft` from the whole line instead of from this invocation's
# segment is the exact donation the header describes: a sibling create's flag
# makes an unrelated one look compliant.
DEFECT = ("hookio.grep_q_line(HAS_DRAFT, seg)", "hookio.grep_q_line(HAS_DRAFT, scan)")

HAS_DRAFT = r"(^|[" + hookio.SPACE + r"])(--draft|-d)([" + hookio.SPACE + r"=]|$)"

PUBLIC_MESSAGE = (
    "❌ BLOCKED: PRs on %s must be created as DRAFTS: add --draft to 'gh pr create'. The PR "
    "stays draft while CI runs and is flipped with 'gh pr ready' only once CI Complete is "
    "green (that flip is what triggers the automated Claude review). If you are actually "
    "targeting a private submodule repo, say so explicitly with --repo "
    "rediacc/<renet|account|elite> (drafts are impossible there)."
)

PRIVATE_MESSAGE = (
    "❌ BLOCKED: %s is PRIVATE and the org is on the GitHub free plan, where draft PRs only "
    "exist on public repos. GitHub would reject this. Create the submodule PR without "
    "--draft; only the console PR uses the draft flow."
)

EDGE_CASES = [
    ("a console create without --draft", "gh pr create --title x --body y"),
    ("a console create with --draft", "gh pr create --draft --title x --body y"),
    ("the short flag counts", "gh pr create -d --title x"),
    # Private repos cannot have drafts at all.
    ("a private submodule create", "gh pr create --repo rediacc/renet --title x"),
    ("a private submodule create WITH --draft", "gh pr create --repo rediacc/renet --draft -t x"),
    ("a cd into a submodule resolves the repo", "cd private/account && gh pr create -t x"),
    ("a foreign repo is not policed", "gh pr create --repo someone/other -t x"),
    # The segment scoping: a sibling create must not donate its --draft.
    (
        "two creates, only the first of which is a draft",
        "gh pr create --draft -t x; gh pr create -t y",
    ),
    ("a wrapper payload is still scanned", "sh -c 'gh pr create -t x'"),
    ("a different pr subcommand", "gh pr view 42"),
]


def run(ev):
    cmd = ev.field("tool_input", "command")
    # Bypass-resistant scanning (unwraps sh -c/eval, strips heredocs+prose); a
    # `sh -c 'gh pr create'` must not slip a non-draft past this. SCAN is the only
    # parsed view -- it already carries the prose-stripped command plus any
    # unwrapped payload. See lib/command-scan.sh.
    scan = shellscan._command_substitution(shellscan.scan_target(cmd))
    if not shellscan.gh_pr_at_command_pos(scan, "create"):
        return hookio.ALLOW

    # --repo and --draft both come from the SEGMENT carrying this `gh pr create`,
    # and EVERY create on the line is judged on its own: line-wide parsing let a
    # sibling invocation donate its repo or its --draft, so
    # `gh pr create --repo rediacc/renet -t x; gh pr create -t y` read as one
    # compliant draft. The cd/-C hint stays line-wide, because a cd genuinely does
    # apply to every later segment. No signal at all defaults to the console
    # checkout, which fails toward draft. See hook_gh_pr_segment / hook_target_repo.
    cwd = ev.field("cwd")
    segs = shellscan.gh_pr_segment(scan, "create")
    records, _ = shellscan._records(shellscan._here_string(segs))
    for seg in records:
        if seg == "":
            continue
        repo = shellscan.target_repo(seg, scan, cwd)

        has_draft = hookio.grep_q_line(HAS_DRAFT, seg)

        if hookio.case_glob(repo, "rediacc/console", "rediacc/homebrew-tap"):
            if not has_draft:
                ev.warn(PUBLIC_MESSAGE % repo)
                return hookio.DENY
        elif (
            hookio.case_glob(repo, "rediacc/renet", "rediacc/account", "rediacc/elite")
            and has_draft
        ):
            ev.warn(PRIVATE_MESSAGE % repo)
            return hookio.DENY
    return hookio.ALLOW
