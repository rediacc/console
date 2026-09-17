"""Enforce the draft-PR flow on `gh pr create`.

The org is on the GitHub FREE plan: draft PRs exist only on PUBLIC repos. console + homebrew-tap are public -> their PRs MUST be created as drafts (the PR stays draft until CI is green; `gh pr ready` is gated by block-premature-ready.sh). renet/account/elite are private -> GitHub rejects --draft there, so the hook blocks it up front with a real message instead of letting the API
fail cryptically.

Target-repo resolution order: explicit --repo/-R flag > a cd/`git -C` into a private/<submodule> path inside the command > the session cwd's origin remote. Unknown/foreign repos are not policed.

PORT NOTE ON THE LOOP'S FEED. `done <<<"$(hook_gh_pr_segment ...)"` is a here-string, so the segment list arrives with exactly one trailing newline whatever the substitution stripped, and `read` therefore always sees a final record. That is why the records below are taken from `_here_string(segs)` and not from `segs` itself: on a single segment with no trailing newline the two
differ by one iteration, which is the whole loop.
"""

from rediacc_hooks import hookio, shellscan

CHAIN = "pre-bash"
TWIN = "pre-bash/block-nondraft-pr-create.sh"
ORDER = 23

# Reading `--draft` from the whole line instead of from this invocation's segment is the exact donation the header describes: a sibling create's flag makes an unrelated one look compliant.
DEFECT = ("hookio.grep_q_line(HAS_DRAFT, seg)", "hookio.grep_q_line(HAS_DRAFT, scan)")

HAS_DRAFT = hookio.rx(r"(^|[{S}])(--draft|-d)([{S}=]|$)")

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

# REST parity for the draft-flow ban. `gh api .../pulls -X POST` reaches the SAME GitHub create mutation as `gh pr create` and carries no `gh pr` verb, so it is invisible to gh_pr_at_command_pos below -- without this arm it creates a non-draft PR on a public repo with none of this guard's checks ever running. Endpoint and method are matched INDEPENDENTLY, reusing the
# split-on-shell-separators idiom block_raw_pr_body_edit.py:246-249 already uses for the sanctioned PATCH form. The endpoint match requires "pulls" to END the path segment (a space or the line's end), not merely appear in it: `pulls/<n>/comments -X POST` posts a COMMENT, not a PR, and losing that boundary would ban it too.
API_VERB = hookio.rx(r"^[{S}]*gh[{S}]+api([{S}]|$)")
API_PULLS_BARE = hookio.rx(r"pulls([{S}]|$)")
API_POST_METHOD = hookio.rx(r"(^|[{S}])(-X|--method)[{S}]+POST([{S}]|$)")

REST_CREATE_MESSAGE = (
    "❌ BLOCKED: 'gh api .../pulls -X POST' is banned outright. It reaches the same GitHub "
    "create mutation as 'gh pr create' but carries none of the repo/draft shape this guard "
    "reads off a 'gh pr create' invocation, so it can create a non-draft PR on a public repo "
    "with no check at all. Use 'gh pr create --draft' (console/homebrew-tap) or 'gh pr create' "
    "without --draft (renet/account/elite). This does not affect 'gh api .../pulls/<n> -X "
    "PATCH', the sanctioned PR-body edit gated separately by block_raw_pr_body_edit."
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
    # REST parity: the same mutation reached through `gh api` instead of `gh pr create`.
    ("the REST create bypass", "gh api repos/o/r/pulls -X POST -f title=x -f head=b -f base=main"),
    (
        "the REST create bypass with flags reordered",
        "gh api repos/o/r/pulls -f title=x -f head=b -f base=main -X POST",
    ),
    ("a GET on the pulls endpoint is not a create", "gh api repos/o/r/pulls"),
    (
        "prose naming the REST bypass",
        "git commit -m '...gh api repos/o/r/pulls -X POST...'",
    ),
    # The two nearest misses to a bare `pulls` POST, both legitimate and both untouched by this arm.
    (
        "a POST to the comments sub-endpoint is not a create",
        "gh api repos/o/r/pulls/42/comments -X POST -f body=hi",
    ),
    (
        "the sanctioned PATCH body edit is not a create",
        "gh api repos/o/r/pulls/42 -X PATCH -f body=x",
    ),
]


def run(ev):
    cmd = ev.field("tool_input", "command")
    # Bypass-resistant scanning (unwraps sh -c/eval, strips heredocs+prose); a `sh -c 'gh pr create'` must not slip a non-draft past this. SCAN is the only parsed view -- it already carries the prose-stripped command plus any unwrapped payload. See lib/command-scan.sh.
    scan = shellscan._command_substitution(shellscan.scan_target(cmd))

    # REST bypass, checked before the `gh pr` early return two lines down: a REST call carries no `gh pr create` verb, so that anchor treats it as out of scope and everything below is skipped for a command reaching the identical mutation.
    split = hookio.sed_sub(r"[;&|()`]", "\n", scan)
    api_lines = hookio.grep_lines(API_VERB, split)
    api_lines = [line for line in api_lines if hookio.grep_q_line(API_PULLS_BARE, line)]
    api_segs = hookio._command_substitution(hookio._grep_out(api_lines))
    if api_segs and hookio.grep_q(API_POST_METHOD, api_segs):
        ev.warn(REST_CREATE_MESSAGE)
        return hookio.DENY

    if not shellscan.gh_pr_at_command_pos(scan, "create"):
        return hookio.ALLOW

    # --repo and --draft both come from the SEGMENT carrying this `gh pr create`, and EVERY create on the line is judged on its own: line-wide parsing let a sibling invocation donate its repo or its --draft, so `gh pr create --repo rediacc/renet -t x; gh pr create -t y` read as one compliant draft. The cd/-C hint stays line-wide, because a cd genuinely does apply to every later
    # segment. No signal at all defaults to the console checkout, which fails toward draft. See hook_gh_pr_segment / hook_target_repo.
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
