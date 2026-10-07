"""Merge discipline for `gh pr merge`:
  1. --admin is banned OUTRIGHT (no green-escape, operator ruling 2026-07-22).
     The old flow admin-merged over a still-pending pointer-bump CI run and
     left every merged PR permanently red; the pointer-bump fast path makes
     the wait minutes, so --admin has no remaining legitimate use here.
  2. --auto defers only the CI-green requirement (GitHub enforces that at
     merge time). Review hygiene is NOT a required check, so --auto still
     proves it NOW like an immediate merge does.
  3. Review hygiene = the per-commit review precondition AND zero unresolved
     review threads. The precondition: every commit since the base has a
     per-commit review record in agent/reviews/<branch>/ with no open finding
     at or above block_at, and every record is committed
     (`python3 .claude/hooks/stop/wl_review.py --check`). It is judged on the
     PR's head branch (`headRefName`) by `wl_review.check_state`, locally and
     with no network call, and it fails CLOSED when the reviewer module does
     not import. Threads are human review threads; nothing posts bot threads
     since the PR-level review was retired on 2026-10-02.
  4. The plan gate, console PR only (box L2 of PLAN-plan-per-pr-loop,
     `plan_gate.plan_merge_refusal`, shared with the fast-forward fallback in
     block_push_to_protected_branch): the body's `Plan:` line names one plan
     whose boxes are all ticked at `origin/<head>`, or, with `turbo: on` in
     agent/plans/QUEUE.md at that same head (agent/plans/PLAN-stop-hook-turbo.md
     D6), any number of plans that are all ticked, every unfinished
     prerequisite included; or the body carries an `Operational-Reason:` line.
     Both --auto and immediate merges; a body that cannot be read is refused.
  5. An immediate merge (no --auto) must additionally prove CI green NOW.
     Console gets all checks; other rediacc repos get the hygiene checks
     (their thread state feeds console's Submodule Branches gate).
     Network paths are NOT covered by test-hooks.sh; verification
     failures fail CLOSED.

PORT NOTE ON WHAT THE DIFFERENTIAL CAN AND CANNOT REACH. Under the harness's default `gh` stub (exit 1, nothing on stdout) every merge resolves to an empty `PRDATA`, so the corpus exercises arms 1 and 2 and stops at "could not resolve the PR". The review-record arm is covered instead by `tests/test_wl_review_check.py`, which drives `review_refusals` against a fixture branch; the thread
arm needs a live `gh` answer and stays uncovered here.
"""

import json
import pathlib
import re

from rediacc_hooks import commit_policy, hookio, plan_gate, shellscan, syspath
from rediacc_hooks.wellknown import ACCOUNT_REPO, GH_REPO, RENET_REPO

CHAIN = "pre-bash"
ORDER = 26

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

REVIEWS_MESSAGE = (
    "❌ BLOCKED: %s#%s (head branch %s) fails the per-commit review precondition: every "
    "commit since the base has a per-commit review record in agent/reviews/<branch>/ with no "
    "open finding at or above block_at, and every record is committed. Refused: %s. Settle "
    "each line below, then re-check with 'python3 .claude/hooks/stop/wl_review.py --check'."
)

PLAN_MESSAGE = (
    "❌ BLOCKED: console PR #%s fails the plan gate (box L2 of agent/plans/PLAN-plan-per-pr-loop.md): "
    "%s. A console PR merges when its body names its plan (`Plan: agent/plans/PLAN-<slug>.md`, "
    "written by the post-push PR-body refresh from agent/plans/QUEUE.md) and every box of that plan is "
    "ticked; with `turbo: on` in agent/plans/QUEUE.md at the PR head the line may name several plans, "
    "and every box of each is ticked. Otherwise the body carries an `Operational-Reason:` line saying "
    "why it merges anyway (a multi-plan PR without turbo included). Tick the boxes with their commits, or add the reason with "
    "`gh api repos/%s/pulls/%s -X PATCH -F body=@<file>`."
)

THREADS_MESSAGE = (
    "❌ BLOCKED: %s#%s has %s unresolved review thread(s). Reply substantively and resolve "
    "them (GraphQL resolveReviewThread) before merging -- an open review thread is a "
    "reviewer's question the PR has not answered."
)

GRAPHQL = (
    "query($o: String!, $r: String!, $n: Int!) { repository(owner: $o, name: $r) { "
    "pullRequest(number: $n) { reviewThreads(first: 100) { nodes { isResolved } } } } }"
)

JQ_UNRESOLVED = (
    "[.data.repository.pullRequest.reviewThreads.nodes[] | select(.isResolved | not)] | length"
)

# The per-commit reviewer lives beside the Stop hook; the review arm imports it from here.
STOP_DIR = pathlib.Path(__file__).resolve().parents[2] / "hooks" / "stop"

# REST parity for the --admin ban. `gh api .../pulls/<n>/merge -X PUT` reaches the SAME GitHub merge mutation as `gh pr merge` and carries no `gh pr` verb, so it is invisible to gh_pr_at_command_pos below -- without this arm it merges over the --admin ban, the CI-green check, the per-commit review precondition and the review-thread check all at once. Endpoint and method are matched INDEPENDENTLY
# because `gh api` flags are order-independent (the method flag may precede or follow the endpoint), reusing the split-on-shell-separators idiom block_raw_pr_body_edit.py:246-249 already uses for the sanctioned PATCH form, rather than a new shared shellscan helper for a three-line regex.
API_VERB = hookio.rx(r"^[{S}]*gh[{S}]+api([{S}]|$)")
API_MERGE_ENDPOINT = r"pulls/[0-9]+/merge"
API_PUT_METHOD = hookio.rx(r"(^|[{S}])(-X|--method)[{S}]+PUT([{S}]|$)")

REST_MERGE_MESSAGE = (
    "❌ BLOCKED: 'gh api .../pulls/<n>/merge' is banned outright. It reaches the same "
    "GitHub mutation as 'gh pr merge' but skips the --admin ban, the CI-green check, "
    "the per-commit review precondition and the review-thread check entirely -- this guard has no way to "
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
    ("a merge on a submodule repo", ("gh pr merge 7 --repo " + RENET_REPO + " --rebase")),
    # The round-46 cross-attribution: fields belong to ONE invocation.
    (
        "a sibling view must not donate its repo",
        ("gh pr view 94 --repo " + RENET_REPO + "; gh pr merge 66 --repo " + ACCOUNT_REPO),
    ),
    ("a foreign repo is not policed", "gh pr merge 42 --repo someone/other"),
    # 2026-10-07 (#8ed364fe): every spelling gh accepts means what gh makes of it.
    ("-R=<foreign> is not policed either", "gh pr merge 42 -R=someone/other"),
    ("the REST merge spelled -XPUT", "gh api repos/o/r/pulls/5/merge -XPUT"),
    ("the REST merge spelled --method=PUT", "gh api repos/o/r/pulls/5/merge --method=PUT"),
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


def review_refusals(root, branch, repo):
    """(reasons, lines) of the per-commit review precondition for the PR head `branch` of `repo`. Fails CLOSED: an import or runtime error is itself a refusal. No network call."""
    try:
        syspath.on_sys_path(STOP_DIR)
        import wl_review  # noqa: PLC0415 -- loaded only for a merge, never for the rest of the chain

        label = "console" if repo == GH_REPO else "private/" + repo.rsplit("/", 1)[-1]
        return wl_review.check_state(pathlib.Path(root), branch, label=label)
    except Exception as exc:  # noqa: BLE001 -- unverifiable is refused, never allowed
        return (
            ["unverifiable"],
            ["the per-commit review check could not run (%s: %s)" % (type(exc).__name__, exc)],
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


def _jq_head_ref(text):
    """`.headRefName // empty` over PRDATA."""
    try:
        doc = json.loads(text) if text else None
    except ValueError:
        return ""
    value = doc.get("headRefName") if isinstance(doc, dict) else None
    return value if isinstance(value, str) else ""


def _jq_body(text):
    """`.body` over PRDATA as a string, None when it is absent or not a string (an unreadable body)."""
    try:
        doc = json.loads(text) if text else None
    except ValueError:
        return None
    value = doc.get("body") if isinstance(doc, dict) else None
    return value if isinstance(value, str) else None


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


def _rest_merge(scan, cmd):
    """Does `cmd` merge a PR through `gh api .../pulls/<n>/merge` with a PUT, in any spelling of the method (`-X PUT`, `-XPUT`, `--method=PUT`)?

    Read from each walked `gh api` call; only a command the walk finds none in keeps the text match, which saw the long `-X PUT` spelling alone until 2026-10-07.
    """
    calls = shellscan.gh_runs(cmd, ("api",))
    if calls:
        for call in calls:
            parsed = shellscan.gh_args(call.argv)
            if re.search(r"pulls/[0-9]+/merge$", shellscan.gh_api_endpoint(parsed)) and (
                shellscan.gh_api_method(parsed) == "PUT"
            ):
                return True
        return False
    # Split SCAN on the shell separators, keep the segment(s) with `gh api` at command position, then require the merge endpoint and the PUT method independently, since either flag may come first on the line.
    split = hookio.sed_sub(r"[;&|()`]", "\n", scan)
    api_lines = hookio.grep_lines(API_VERB, split)
    api_lines = [line for line in api_lines if hookio.grep_q_line(API_MERGE_ENDPOINT, line)]
    api_segs = hookio._command_substitution(hookio._grep_out(api_lines))
    return bool(api_segs and hookio.grep_q(API_PUT_METHOD, api_segs))


def run(ev):
    cmd = ev.field("tool_input", "command")
    # Bypass-resistant command scanning (unwraps sh -c/eval payloads, strips
    # heredocs+prose, matches --flag=value forms). A commit message MENTIONING
    # "gh pr merge --admin" must not trip the ban, but `sh -c 'gh pr merge
    # --admin'` and `--admin=true` MUST. See lib/command-scan.sh.
    scan = shellscan._command_substitution(shellscan.scan_target(cmd))

    # REST bypass, checked before the `gh pr` early return two lines down: a REST call carries no `gh pr merge` verb, so that anchor treats it as out of scope and everything below is skipped for a command reaching the identical mutation.
    if _rest_merge(scan, cmd):
        ev.warn(REST_MERGE_MESSAGE)
        return hookio.DENY

    # Every merge is read from its own walked call (`shellscan.gh_args`): `-R=x`, `-Rx` and `--repo 'x'` name the repo they name, and the PR is the first OPERAND wherever the flags sit (`gh pr merge --repo x 66` is #66, which the text reader took to be a PR called "x"). Measured 2026-10-07. Only a command the walk finds no merge in keeps the text reader.
    runs = shellscan.gh_pr_runs(cmd, "merge")
    if not runs and not shellscan.gh_pr_at_command_pos(scan, "merge"):
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

    merges = []
    for run_ in runs:
        parsed = shellscan.gh_args(run_.argv)
        if parsed.on("help"):
            continue
        sel = parsed.operands[0] if parsed.operands else ""
        merges.append((shellscan.gh_run_repo(run_, cwd), parsed.on("auto"), sel))
    if not runs:
        # Every field (repo, selector, --auto) is read from the SEGMENT that carries this `gh pr merge`, and EACH merge on the line is checked on its own. Parsing line-wide cross-attributed fields between sibling invocations -- observed live: `gh pr view 94 --repo rediacc/renet; gh pr merge 66 --repo rediacc/account` resolved as rediacc/renet#66, an unrelated long-merged PR, and
        # blocked the merge on THAT PR's threads. It also examined only one of several merges on a line. See hook_gh_pr_segment.
        segs = shellscan.gh_pr_segment(scan, "merge")
        records, _ = shellscan._records(shellscan._here_string(segs))
        for seg in records:
            if seg == "":
                continue
            merges.append(
                (
                    shellscan.target_repo(seg, scan, cwd),
                    shellscan.flag_present(seg, "auto"),
                    shellscan._command_substitution(shellscan.pr_selector(seg, "merge")),
                )
            )
    for repo, auto, sel in merges:
        if not hookio.case_glob(repo, "rediacc/*"):
            continue

        # `${SEL:+"$SEL"}` -- the argument is present only when SEL is not empty.
        view = ["timeout", "20", "gh", "pr", "view"]
        if sel != "":
            view.append(sel)
        view += ["--repo", repo, "--json", "number,statusCheckRollup,headRefName,body"]
        prdata = hookio.run_out(view)
        num = _jq_number(prdata)
        if num == "":
            ev.warn(UNRESOLVABLE_MESSAGE % (repo, sel if sel != "" else "<current branch>"))
            return hookio.DENY

        if not auto and repo == GH_REPO:
            conclusion = _jq_conclusion(prdata)
            if conclusion != "SUCCESS":
                ev.warn(
                    NOT_GREEN_MESSAGE
                    % (num, conclusion if conclusion != "" else "verification failed")
                )
                return hookio.DENY

        # The plan gate (box L2), console only: the PR's plan read at the PR head's remote-tracking ref when this checkout has it, else the working tree. An absent or unreadable body refuses.
        head = _jq_head_ref(prdata)
        if repo == GH_REPO:
            rev = ""
            if head and commit_policy.git(
                ["rev-parse", "--verify", "-q", "refs/remotes/origin/%s^{commit}" % head], cwd=root
            ):
                rev = "refs/remotes/origin/%s" % head
            refusal = plan_gate.plan_merge_refusal(root, _jq_body(prdata), rev=rev)
            if refusal:
                ev.warn(PLAN_MESSAGE % (num, refusal, repo, num))
                return hookio.DENY

        # The per-commit review precondition (both --auto and immediate), judged on the PR's head branch from the local tree. An unreadable head branch or a reviewer module that does not import refuses: the precondition is unverifiable, and unverifiable never merges.
        reasons, lines = review_refusals(root, head, repo)
        if reasons:
            ev.warn(REVIEWS_MESSAGE % (repo, num, head or "unknown", ", ".join(reasons)))
            ev.warn_raw("".join("  %s\n" % line for line in lines))
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
