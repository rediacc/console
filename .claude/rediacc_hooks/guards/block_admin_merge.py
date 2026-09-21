"""Merge discipline for `gh pr merge`:
  1. --admin is banned OUTRIGHT (no green-escape, operator ruling 2026-07-22).
     The old flow admin-merged over a still-pending pointer-bump CI run and
     left every merged PR permanently red; the pointer-bump fast path makes
     the wait minutes, so --admin has no remaining legitimate use here.
  2. --auto defers only the CI-green requirement (GitHub enforces that at
     merge time). Review hygiene is NOT a required check, so --auto still
     proves it NOW like an immediate merge does.
  3. Review hygiene = zero unresolved review threads AND a substantive
     reply to the newest finished review REPORT (issue-comment channel,
     check-review-report-replies.sh). Required checks are per-commit: a
     report posted after CI went green can never turn the check red, so
     merge time is the only enforcement point, and ci.yml's review-gate only
     re-evaluates on the next push.
  4. An immediate merge (no --auto) must additionally prove CI green NOW.
     Console gets all checks; other rediacc repos get the hygiene checks
     (their thread state feeds console's Submodule Branches gate).
     Network paths are NOT covered by test-hooks.sh; verification
     failures fail CLOSED.

PORT NOTE ON WHAT THE DIFFERENTIAL CAN AND CANNOT REACH. Under the harness's default `gh` stub (exit 1, nothing on stdout) every merge resolves to an empty `PRDATA`, so the corpus exercises arms 1 and 2 and stops at "could not resolve the PR". Arms 3 to 5 are ported line for line and are NOT covered here, and that is deliberate rather than an omission: reaching them means stubbing
`gh` into answering AND letting `check-review-report-replies.sh` run, and that script makes its own live calls, so a stub deep enough to reach the branch would make this differential a network test -- the exact failure the harness's own header says the stub exists to prevent. The bash's line 20 already says those paths are not covered by test-hooks.sh either.
"""

import json
import subprocess

from rediacc_hooks import hookio, shellscan

CHAIN = "pre-bash"
TWIN = "pre-bash/block-admin-merge.sh"
ORDER = 27

# The outright ban is arm 1 and the whole 2026-07-22 ruling. Dropping it does not merely change a message: an --admin merge falls through to the ordinary resolution path and is judged as if it were a normal one.
DEFECT = ('if shellscan.flag_present(cmd, "admin"):', "if False:")

ADMIN_MESSAGE = (
    "❌ BLOCKED: 'gh pr merge --admin' is banned. It bypasses the required CI Complete check "
    "and is how merged PRs ended up permanently red (pointer-bump commits merged mid-run). "
    "The sanctioned path: wait for the fast-path CI run to go green (minutes for pointer-only "
    "pushes), then 'gh pr ready' and 'gh pr merge --rebase --auto'. If GitHub refuses a plain "
    "merge, the PR is not actually green -- fix that instead."
)

UNRESOLVABLE_MESSAGE = (
    "❌ BLOCKED: could not resolve the PR for 'gh pr merge' (repo %s, selector '%s'). Cannot "
    "verify green + resolved threads, so the merge is not allowed. Name the PR explicitly or "
    "re-run after checking 'gh pr view'."
)

NOT_GREEN_MESSAGE = (
    "❌ BLOCKED: immediate merge of console PR #%s requires CI Complete = SUCCESS on the "
    "current head (got: %s). Use 'gh pr merge --rebase --auto' to let GitHub merge at green, "
    "or wait for the run."
)

REPORT_MESSAGE = (
    "❌ BLOCKED: %s#%s has an unaddressed review REPORT (or the check could not run). "
    "Required checks are per-commit, so a report posted after CI went green can only be "
    "enforced here. Details:"
)

THREADS_MESSAGE = (
    "❌ BLOCKED: %s#%s has %s unresolved review thread(s). Reply substantively and resolve "
    "them (GraphQL resolveReviewThread) before merging -- review threads are the blocking "
    "channel of the Claude review flow."
)

GRAPHQL = (
    "query($o: String!, $r: String!, $n: Int!) { repository(owner: $o, name: $r) { "
    "pullRequest(number: $n) { reviewThreads(first: 100) { nodes { isResolved } } } } }"
)

JQ_UNRESOLVED = (
    "[.data.repository.pullRequest.reviewThreads.nodes[] | select(.isResolved | not)] | length"
)

# REST parity for the --admin ban. `gh api .../pulls/<n>/merge -X PUT` reaches the SAME GitHub merge mutation as `gh pr merge` and carries no `gh pr` verb, so it is invisible to gh_pr_at_command_pos below -- without this arm it merges over the --admin ban, the CI-green check and the review-thread/report-reply hygiene checks all at once. Endpoint and method are matched INDEPENDENTLY
# because `gh api` flags are order-independent (the method flag may precede or follow the endpoint), reusing the split-on-shell-separators idiom block_raw_pr_body_edit.py:246-249 already uses for the sanctioned PATCH form, rather than a new shared shellscan helper for a three-line regex.
API_VERB = hookio.rx(r"^[{S}]*gh[{S}]+api([{S}]|$)")
API_MERGE_ENDPOINT = r"pulls/[0-9]+/merge"
API_PUT_METHOD = hookio.rx(r"(^|[{S}])(-X|--method)[{S}]+PUT([{S}]|$)")

REST_MERGE_MESSAGE = (
    "❌ BLOCKED: 'gh api .../pulls/<n>/merge' is banned outright. It reaches the same "
    "GitHub mutation as 'gh pr merge' but skips the --admin ban, the CI-green check "
    "and the review-thread/report-reply hygiene entirely -- this guard has no way to "
    "verify any of that against a raw REST call. The sanctioned path: 'gh pr ready' "
    "once CI Complete is green, then 'gh pr merge --rebase --auto'."
)

EDGE_CASES = [
    ("the banned flag", "gh pr merge 42 --admin"),
    # Over-blocking is the safe direction, so every flag SHAPE counts.
    ("the flag with a value", "gh pr merge 42 --admin=true"),
    ("the flag inside a wrapper payload", "sh -c 'gh pr merge --admin'"),
    ("the flag inside an assignment", 'X="--admin"; gh pr merge 42 $X'),
    # A commit message MENTIONING the banned command must not trip the ban.
    ("prose naming the banned command", "git commit -m '...gh pr merge --admin...'"),
    ("an ordinary merge", "gh pr merge 42 --rebase --auto"),
    ("an immediate merge with no selector", "gh pr merge --rebase"),
    ("a merge on a submodule repo", "gh pr merge 7 --repo rediacc/renet --rebase"),
    # The round-46 cross-attribution: fields belong to ONE invocation.
    (
        "a sibling view must not donate its repo",
        "gh pr view 94 --repo rediacc/renet; gh pr merge 66 --repo rediacc/account",
    ),
    ("a foreign repo is not policed", "gh pr merge 42 --repo someone/other"),
    ("a different pr subcommand", "gh pr view 42"),
    # REST parity: the same mutation reached through `gh api` instead of `gh pr merge`.
    (
        "the REST merge bypass",
        "gh api repos/o/r/pulls/589/merge -X PUT -f merge_method=squash",
    ),
    (
        "the REST merge bypass with flags reordered",
        "gh api repos/o/r/pulls/589/merge -f merge_method=squash -X PUT",
    ),
    ("a GET on the merge endpoint is not a merge", "gh api repos/o/r/pulls/589/merge"),
    (
        "prose naming the REST bypass",
        "git commit -m '...gh api repos/o/r/pulls/589/merge -X PUT...'",
    ),
]


def _run_capture(argv, env=None):
    """`OUT=$(cmd 2>&1)` with its status -- both streams, and `if !` on the rc."""
    try:
        proc = subprocess.run(
            argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False, env=env
        )
    except OSError:
        return "", 127
    return shellscan._command_substitution(proc.stdout.decode("utf-8", "surrogateescape")), (
        proc.returncode
    )


def _jq_number(text):
    """`jq -r '.number // empty'` over PRDATA, empty input included."""
    if text == "":
        return ""
    try:
        doc = json.loads(text)
    except ValueError:
        return ""
    if not isinstance(doc, dict):
        return ""
    value = doc.get("number")
    if value is None or value is False:
        return ""
    return value if isinstance(value, str) else json.dumps(value, separators=(",", ":"))


def _jq_conclusion(text):
    """`[.statusCheckRollup[] | select(.name == "CI Complete")] | first | .conclusion // "ABSENT"`.

    `first` of an EMPTY array is `null`, and `null.conclusion` is `null` in jq rather than an error, so the alternative supplies "ABSENT" -- which is why an absent check and a check with no conclusion read the same here.
    """
    if text == "":
        return ""
    try:
        doc = json.loads(text)
    except ValueError:
        return ""
    if not isinstance(doc, dict) or not isinstance(doc.get("statusCheckRollup"), list):
        return ""
    picked = [
        node
        for node in doc["statusCheckRollup"]
        if isinstance(node, dict) and node.get("name") == "CI Complete"
    ]
    if not picked:
        return "ABSENT"
    value = picked[0].get("conclusion")
    if value is None or value is False:
        return "ABSENT"
    return value if isinstance(value, str) else json.dumps(value, separators=(",", ":"))


def run(ev):
    cmd = ev.field("tool_input", "command")
    # Bypass-resistant command scanning (unwraps sh -c/eval payloads, strips
    # heredocs+prose, matches --flag=value forms). A commit message MENTIONING
    # "gh pr merge --admin" must not trip the ban, but `sh -c 'gh pr merge
    # --admin'` and `--admin=true` MUST. See lib/command-scan.sh.
    scan = shellscan._command_substitution(shellscan.scan_target(cmd))

    # REST bypass, checked before the `gh pr` early return two lines down: a REST call carries no `gh pr merge` verb, so that anchor treats it as out of scope and everything below is skipped for a command reaching the identical mutation. Split SCAN on the shell separators, keep the segment(s) with `gh api` at command position, then require the merge endpoint and the PUT method
    # independently, since either flag may come first on the line.
    split = hookio.sed_sub(r"[;&|()`]", "\n", scan)
    api_lines = hookio.grep_lines(API_VERB, split)
    api_lines = [line for line in api_lines if hookio.grep_q_line(API_MERGE_ENDPOINT, line)]
    api_segs = hookio._command_substitution(hookio._grep_out(api_lines))
    if api_segs and hookio.grep_q(API_PUT_METHOD, api_segs):
        ev.warn(REST_MERGE_MESSAGE)
        return hookio.DENY

    if not shellscan.gh_pr_at_command_pos(scan, "merge"):
        return hookio.ALLOW

    # SCAN is the only parsed view: it already carries the prose-stripped command plus any unwrapped shell-wrapper payload. A second, separately-built stripped view used to exist for field parsing; keeping two views in sync is the drift hazard lib/command-scan.sh already records, so fields are read from SCAN.

    # --admin ban: match the flag in ANY form on the raw command (=value,
    # assignment, inside a wrapper payload). Over-blocking is the safe direction.
    if shellscan.flag_present(cmd, "admin"):
        ev.warn(ADMIN_MESSAGE)
        return hookio.DENY

    # CLAUDE_PROJECT_DIR is unset outside hook invocation (e.g. the harness);
    # fall back to the git toplevel so the script path stays absolute.
    root = ev.env("CLAUDE_PROJECT_DIR", "")
    if root == "":
        root = hookio.git_out(["rev-parse", "--show-toplevel"])
    cwd = ev.field("cwd")

    # Every field (repo, selector, --auto) is read from the SEGMENT that carries this `gh pr merge`, and EACH merge on the line is checked on its own. Parsing line-wide cross-attributed fields between sibling invocations -- observed live: `gh pr view 94 --repo rediacc/renet; gh pr merge 66 --repo rediacc/account` resolved as rediacc/renet#66, an unrelated long-merged PR, and
    # blocked the merge on THAT PR's threads. It also examined only one of several merges on a line. See hook_gh_pr_segment.
    segs = shellscan.gh_pr_segment(scan, "merge")
    records, _ = shellscan._records(shellscan._here_string(segs))
    for seg in records:
        if seg == "":
            continue
        repo = shellscan.target_repo(seg, scan, cwd)
        if not hookio.case_glob(repo, "rediacc/*"):
            continue

        auto = shellscan.flag_present(seg, "auto")

        sel = shellscan._command_substitution(shellscan.pr_selector(seg, "merge"))
        # `${SEL:+"$SEL"}` -- the argument is present only when SEL is not empty.
        view = ["timeout", "20", "gh", "pr", "view"]
        if sel != "":
            view.append(sel)
        view += ["--repo", repo, "--json", "number,statusCheckRollup"]
        prdata = hookio.run_out(view)
        num = _jq_number(prdata)
        if num == "":
            ev.warn(UNRESOLVABLE_MESSAGE % (repo, sel if sel != "" else "<current branch>"))
            return hookio.DENY

        if not auto and repo == "rediacc/console":
            conclusion = _jq_conclusion(prdata)
            if conclusion != "SUCCESS":
                ev.warn(
                    NOT_GREEN_MESSAGE
                    % (num, conclusion if conclusion != "" else "verification failed")
                )
                return hookio.DENY

        # Report-reply hygiene (both --auto and immediate): the newest finished review report must have a substantive id-referencing reply. Reuses the CI gate verbatim; fails CLOSED on script/network failure. The gate moved from `check-review-report-replies.sh` to its registered `.py` entry point when W7 P5 batch G1 retired the bash twin, which is why the frozen oracle beside
        # this file still spells the old path.
        token = hookio.run_out(["gh", "auth", "token"])
        out, rc = _run_capture(
            [
                "timeout",
                "30",
                "env",
                "GH_TOKEN=%s" % token,
                "PR_NUMBER=%s" % num,
                "GITHUB_REPOSITORY=%s" % repo,
                "python3",
                "%s/.ci/scripts/quality/check_review_report_replies.py" % root,
            ]
        )
        if rc != 0:
            ev.warn(REPORT_MESSAGE % (repo, num))
            tail, _ = shellscan._records(shellscan._here_string(out))
            ev.warn_raw("".join(line + "\n" for line in tail[-15:]))
            return hookio.DENY

        owner = repo.split("/", 1)[0]
        name = repo.rsplit("/", 1)[-1]
        unresolved = hookio.run_out(
            [
                "timeout",
                "20",
                "gh",
                "api",
                "graphql",
                "-f",
                "query=%s" % GRAPHQL,
                "-f",
                "o=%s" % owner,
                "-f",
                "r=%s" % name,
                "-F",
                "n=%s" % num,
                "--jq",
                JQ_UNRESOLVED,
            ]
        )
        if unresolved == "" or unresolved != "0":
            ev.warn(
                THREADS_MESSAGE % (repo, num, unresolved if unresolved != "" else "unverifiable")
            )
            return hookio.DENY
    return hookio.ALLOW
