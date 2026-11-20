"""ONE OPEN PR AT A TIME. Refuse `gh pr create` when this author already has an open PR in the target repo.

WHY THIS IS A HOOK AND NOT A LINE IN CLAUDE.md. The operator's ruling, and the incident behind it: a single session opened FOUR stacked PRs over one night, each one individually reasonable (new work arrived, it needed a base, the previous PR was not merged yet), and the result was four unmerged PRs waiting on one person. Nothing in CLAUDE.md or the pr-babysit command stopped it,
because instructions only bind a session that reads them, remembers them, and applies them at the one second that matters. PreToolUse is the only surface that can DENY the command before it runs, which is the difference between a preference and a control.

WHAT TO DO INSTEAD, and the message says so, because a block without a next step just gets worked around: push the new work onto the EXISTING PR's branch. That is almost always what was wanted anyway. There is no agent path to a second PR: a second open PR is the operator's own `!` command (CLAUDE.md Session Defaults rule 1), so the message names no one to ask.

FAILS CLOSED. If the open-PR list cannot be read, this refuses rather than waving the create through: `gh` being unreachable is not evidence that no PR exists, and creating a duplicate is the expensive direction of the error.

PORT NOTE ON THE TWO SHELL IDIOMS THIS FILE TURNS ON. `LIST=$(gh ... 2>&1)`
followed by `RC=$?` keeps BOTH streams and the status, which no helper in
`hookio` offers (every call site there writes `2>/dev/null` and drops one or the other), so `_run_capture` is private to this module. And
`COUNT=$(... | jq 'length' 2>/dev/null || echo 0)` has three outcomes, not two:
a JSON array gives its length, a jq FAILURE gives the literal `0`, and an EMPTY input gives the EMPTY STRING, because jq with no input prints nothing and exits
0. `[[ "" -gt 0 ]]` is false, so the empty case allows -- the same answer as
zero, by a different route.

TWO TREES, ONE DRAFT BESIDE THE PR (agent/plans/PLAN-two-track-merge-dev.md, box LT4; operator ruling ASKED:2026-11-20T17:47Z "Draft PR"). When the repository carries a landing record (`commit_policy.landing_record`: the open PR's branch bound to the landing tree), the DEVELOPMENT tree's branch may hold exactly one DRAFT PR beside the landing branch's open PR, because the draft PR's run is the only CI that branch gets. The admission is narrow: the create is a draft, it runs in the development tree, its head is that tree's checked-out branch and not the landing branch, and every open PR other than the landing branch's blocks it as before.
So a second draft, a non-draft and a draft from any other head are refused. `gh pr ready` on any PR but the landing branch's is refused while the landing branch's PR is open: the draft turns ready after the PR branch merges. With no landing record every answer is exactly what it was before the binding existed.

ONE PLAIN SUBMODULE PR BESIDE THE LANDING PR'S (box LT18; operator ruling ASKED:2026-11-20T18:46Z). A submodule the development branch touches gets one PR headed by the development branch's name, beside the landing branch's PR in that repository. The submodule repositories (`PAIRED_SUBMODULE_REPOS`) are private free-plan repositories, which have no draft PRs, so this admission takes a plain create. It is as narrow as the draft's: the target is one of those repositories, the console checkout the call runs in (the superproject of the submodule checkout, or the checkout itself) carries a landing record and is the development tree, and the head (`--head`, else the branch checked out where gh runs) is the console's current branch there, never the landing record's branch. Every open PR in the submodule repository other than the landing branch's still blocks it, so a second development PR and a PR from any other head are refused. With no record the answer is exactly today's.
"""

import json
import os
import re
import subprocess

from rediacc_hooks import commit_policy, hookio, shellscan
from rediacc_hooks.wellknown import ACCOUNT_REPO, ELITE_REPO, GH_REPO, RENET_REPO

CHAIN = "pre-bash"
ORDER = 24

# THE DRAFT ADMISSION'S FILTER is the line planted. Inverted, only the open PRs that stand beside an admitted draft count: with no landing record the second PR this guard exists for is waved through, and with one the landing branch's PR alone blocks the development draft while every other open PR is ignored. The fail-closed arm keeps its own witness (`gh down fails closed` in test-block_second_open_pr.py).
DEFECT = ("if not _stands_beside(row, beside)", "if _stands_beside(row, beside)")

# `gh` answering is what makes the block direction reachable at all: under the harness default it exits 1 with nothing, which is only the fail-closed arm.
_GH_LIST = (
    '#!/bin/sh\ncat <<\'GHEOF\'\n[{"number":563,"title":"t","headRefName":"b","isDraft":false}]\n'
    "GHEOF\n"
)
_GH_EMPTY = "#!/bin/sh\ncat <<'GHEOF'\n[]\nGHEOF\n"
_GH_DOWN = "#!/bin/sh\necho 'gh: could not connect'\nexit 1\n"

ENVS = [
    ("gh-silent-failure", {}, {}),
    ("gh-unreachable", {}, {"gh": _GH_DOWN}),
    ("gh-none-open", {}, {"gh": _GH_EMPTY}),
    ("gh-one-open", {}, {"gh": _GH_LIST}),
]

UNVERIFIABLE = (
    "❌ BLOCKED: cannot verify whether an open PR already exists in %s, so this\n"
    "   `gh pr create` is refused rather than risking a duplicate.\n"
    "\n"
    "   gh said: %s\n"
    "\n"
    "   An unreadable list is not evidence that the list is empty. Fix the gh\n"
    "   problem and retry. There is no agent path around this check: a PR this\n"
    "   guard cannot verify is the operator's own `!` command.\n"
)

# What UNVERIFIABLE says gh answered for a repository the walk cannot evaluate: gh is never asked about it.
UNRESOLVED_REASON = (
    "(not asked: the repository is named through a variable or a substitution this hook "
    "cannot evaluate; name it literally)"
)

# What UNVERIFIABLE says for a create whose `cd` target carries an expansion the walk keeps unexpanded (`for s in ...; do (cd private/$s && gh pr create); done`): the directory, and so the repository, is unknown.
UNRESOLVED_DIR_REASON = (
    "(not asked: the command runs in a directory named through a variable or a substitution "
    "(`cd %s`) this hook cannot evaluate; cd into a literal path, or pass --repo)"
)
# A `cd` target the walk left unexpanded: a parameter, a command substitution or arithmetic.
_UNEXPANDED = re.compile(r"[$`]")

ALREADY_OPEN = (
    "❌ BLOCKED: you already have %s open PR(s) in %s. One at a time.\n"
    "\n"
    "%s\n"
    "\n"
    "   WHY: four stacked PRs from one night is what bought this rule. Each new PR\n"
    "   looked reasonable on its own, and the pile landed on the operator, who has to\n"
    "   review and merge them in order. A second PR does not get work finished\n"
    "   sooner; it just splits one decision into several.\n"
    "\n"
    "   DO THIS INSTEAD: push the new work onto the branch of the PR above and\n"
    "   refresh its body. That is almost certainly what you wanted, and it keeps the\n"
    "   whole change reviewable as one thing.\n"
    "\n"
    "   There is no agent path to a second PR, and nothing to ask for: a second\n"
    "   open PR is the operator's own `!` command (CLAUDE.md Session Defaults\n"
    "   rule 1, one branch and one PR).\n"
)

LANDING_NOTE = (
    "\n"
    "   TWO TREES: this repository binds the landing branch %s to its landing\n"
    "   tree. Beside that branch's open PR, the development tree's branch may hold\n"
    "   ONE draft PR (`gh pr create --draft` run in the development tree, its head\n"
    "   that tree's own branch); any other PR beside it is refused.\n"
)

SUBMODULE_NOTE = (
    "\n"
    "   TWO TREES: the console binds the landing branch %s to its landing tree.\n"
    "   Beside that branch's open PR in this submodule repository, the development\n"
    "   branch may hold ONE plain PR, created from the console's development tree\n"
    "   with the development branch's name as its head; any other PR beside it is\n"
    "   refused.\n"
)

# The submodule repositories where the development branch's plain PR may stand beside the landing branch's (box LT18): private free-plan repositories, which have no draft PRs.
PAIRED_SUBMODULE_REPOS = frozenset(name.lower() for name in (RENET_REPO, ACCOUNT_REPO, ELITE_REPO))

READY_REFUSED = (
    "❌ BLOCKED: `gh pr ready` on %s while the landing branch's PR is open in %s.\n"
    "\n"
    "%s\n"
    "\n"
    "   WHY: the development branch's PR rides as a draft beside the landing\n"
    "   branch's PR (agent/plans/PLAN-two-track-merge-dev.md, box LT4). Two ready\n"
    "   PRs are two merges waiting on one person, the pile the one-PR rule exists\n"
    "   to prevent.\n"
    "\n"
    "   DO THIS INSTEAD: merge the landing branch's PR first; the draft turns\n"
    "   ready after it merges.\n"
)

EDGE_CASES = [
    ("the create this guard exists for", "gh pr create --draft -t x -b y"),
    ("sh -c wrapping does not bypass it", "sh -c 'gh pr create --draft -t x -b y'"),
    # THE CONTROL THAT MATTERS: with no open PR the guard must be invisible, or it would block the FIRST PR too and simply stop all work.
    ("a non-create gh command is ignored", "gh pr view 567"),
    (
        "a submodule create is judged against ITS repo",
        ("gh pr create --repo " + RENET_REPO + " -t x"),
    ),
    ("prose naming the command", "echo 'gh pr create --draft'"),
]


def _run_capture(argv):
    """`X=$(cmd 2>&1); RC=$?` -- both streams merged, the status kept."""
    try:
        proc = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    except OSError:
        return "", 127
    text = proc.stdout.decode("utf-8", "surrogateescape")
    return shellscan._command_substitution(text), proc.returncode


def _jq_length(text):
    """`jq 'length' 2>/dev/null || echo 0`, with jq's own type rules.

    Empty input is the empty string (jq reads no value and prints nothing);
    unparseable input is the literal `0` supplied by the `|| echo 0`; an array, object or string is its length; `null` is 0 and a number is its absolute value, which is jq's definition and not an approximation of it.
    """
    if text == "":
        return ""
    try:
        doc = json.loads(text)
    except ValueError:
        return "0"
    if doc is None:
        return "0"
    if isinstance(doc, bool):
        # `true | length` is an ERROR in jq, so the `|| echo 0` supplies this.
        return "0"
    if isinstance(doc, (int, float)):
        return str(abs(doc))
    if isinstance(doc, (str, list, dict)):
        return str(len(doc))
    return "0"


def _render(value):
    """`\\(...)` string interpolation: raw for a string, `null` for null."""
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, str):
        return value
    return json.dumps(value, separators=(",", ":"))


def _rows(text):
    """The `jq -r '.[] | "..."'` row renderer, or "" when jq would have failed."""
    try:
        doc = json.loads(text)
    except ValueError:
        return ""
    if isinstance(doc, list):
        items = doc
    elif isinstance(doc, dict):
        items = list(doc.values())
    else:
        return ""
    out = []
    for item in items:
        if not isinstance(item, dict):
            return ""
        title = item.get("title")
        title = title[0:64] if isinstance(title, str) else title
        draft = " (draft)" if item.get("isDraft") else ""
        out.append(
            "     #%s %s [%s]%s"
            % (_render(item.get("number")), _render(title), _render(item.get("headRefName")), draft)
        )
    return shellscan._command_substitution("".join(row + "\n" for row in out))


def _create_repo(run_, cwd, inherited):
    """The repository one walked `gh pr create` targets, read as gh reads it: `--repo`/`-R`/`GH_REPO` (`shellscan.gh_named_repo`), else the directory the call really runs in after its `cd`s, else the session `cwd`.

    `shellscan.gh_run_repo` alone reads the cd only when it names `private/<submodule>` and otherwise asks the SESSION cwd's origin, so `(cd private/$s && gh pr create)` from the console counted console's open PR (worklist #29531257, console PR 605, 2026-11-11), and a cd into any other checkout did the same. The effective directory is handed to `gh_run_repo` as its cwd, so its own order still applies there. A cd target with an unexpanded `$` or backquote, or `cd -`, is `UNRESOLVED_REPO`; a cd into a missing directory leaves the shell where it was, so the session cwd stands.
    """
    if shellscan.gh_named_repo(run_, inherited):
        return shellscan.gh_run_repo(run_, cwd, inherited)
    rel = run_.cwd or ""
    if rel in ("", "."):
        return shellscan.gh_run_repo(run_, cwd, inherited)
    # `cd -` goes to a previous directory this walk never saw (the walk leaves `-` as the target when the first `cd` of the command is it), so it is as unknown as a variable.
    if rel == "-" or _UNEXPANDED.search(rel):
        return shellscan.UNRESOLVED_REPO
    target = os.path.expanduser(rel)
    if not os.path.isabs(target):
        target = os.path.join(cwd or os.getcwd(), target)
    target = os.path.normpath(target)
    if os.path.isdir(target):
        return shellscan.gh_run_repo(run_, target, inherited)
    return shellscan.gh_run_repo(run_, cwd, inherited)


def _landing_record(root):
    """`commit_policy.landing_record` for the repository at `root`, None when it binds no landing tree.

    THE SEAM. Read through `getattr` because the record reader lands in commit_policy as its own box (LT1); with no reader there is no binding, which is the no-record answer. test-block_second_open_pr.py replaces this function and `_tree_role` to stage a binding in-process.
    """
    reader = getattr(commit_policy, "landing_record", None)
    return reader(root) if reader is not None else None


def _tree_role(root):
    """`commit_policy.tree_role` for the repository at `root`: "landing" or "development" ("" with no reader). The same seam as `_landing_record`."""
    reader = getattr(commit_policy, "tree_role", None)
    return reader(root) if reader is not None else ""


def _effective_dir(run_, cwd):
    """The directory one walked `gh` call runs in after its `cd`s, None when a `cd` target cannot be evaluated (`cd -`, a variable). A `cd` into a missing directory leaves the shell where it was."""
    base = cwd or os.getcwd()
    rel = run_.cwd or ""
    if rel in ("", "."):
        return base
    if rel == "-" or _UNEXPANDED.search(rel):
        return None
    target = os.path.normpath(os.path.join(base, os.path.expanduser(rel)))
    return target if os.path.isdir(target) else base


def _bound(run_, cwd, repo):
    """(repository root, landing record) for one walked call that a landing record governs, (None, None) otherwise.

    Governed means: the call runs in a git checkout whose repository carries a valid record, and it targets that checkout's own origin, so a create or ready aimed at another repository (a submodule's `--repo`) is judged as before. A paired submodule repository is never governed here, even by a record read through its superproject: its one admission is `_submodule_beside`'s.
    """
    directory = _effective_dir(run_, cwd)
    if directory is None or repo == shellscan.UNRESOLVED_REPO:
        return None, None
    if repo.lower() in PAIRED_SUBMODULE_REPOS:
        return None, None
    root = commit_policy.toplevel(directory)
    if not root:
        return None, None
    record = _landing_record(root)
    if not record or repo.lower() != shellscan.gh_repo_name(shellscan._origin_repo(root)):
        return None, None
    return root, record


def _draft_beside(run_, root, record):
    """The landing branch an admitted draft may stand beside, None when this create is not the development tree's draft.

    The create is a draft (`--draft`/`-d`, not `--draft=false`), it runs in the development tree, and its head (`--head`/`-H`, an `owner:` prefix dropped, else the branch checked out) is that tree's own branch and not the landing branch.
    """
    if record is None:
        return None
    args = shellscan.gh_args(run_.argv)
    if not args.on("draft") or _tree_role(root) != "development":
        return None
    current = commit_policy.current_branch(root)
    head = _head(run_, root)
    landing = record.get("branch", "")
    if not head or not landing or head != current or head == landing:
        return None
    return landing


def _head(run_, directory):
    """The head branch of one walked `gh pr create`: `--head`/`-H` with an `owner:` prefix dropped, else the branch checked out at `directory`."""
    head = shellscan.gh_args(run_.argv).last("head")
    return head.split(":", 1)[-1] if head else commit_policy.current_branch(directory)


def _submodule_beside(run_, cwd, repo):
    """(landing branch, landing record) when this create is the development branch's plain PR in a paired submodule repository, (None, None) otherwise.

    The console checkout is the superproject of the checkout the call runs in, or that checkout itself (`gh pr create --repo <submodule>` typed in the console); its origin is the console's, it carries a landing record and it is the development tree. The head is the console's current branch there and not the landing branch.
    """
    if repo.lower() not in PAIRED_SUBMODULE_REPOS:
        return None, None
    directory = _effective_dir(run_, cwd)
    top = commit_policy.toplevel(directory) if directory else ""
    if not top:
        return None, None
    console = commit_policy.superproject(top) or top
    if shellscan.gh_repo_name(shellscan._origin_repo(console)) != GH_REPO.lower():
        return None, None
    record = _landing_record(console)
    if not record or _tree_role(console) != "development":
        return None, None
    development = commit_policy.current_branch(console)
    landing = record.get("branch", "")
    if not development or not landing or development == landing:
        return None, None
    if _head(run_, top) != development:
        return None, record
    return landing, record


def _stands_beside(row, beside):
    """Does the open PR `row` stand beside an admitted draft? Only the landing branch's PR does, and only when the create was admitted (`beside`, the landing branch)."""
    return beside is not None and row.get("headRefName") == beside


def _listed(listing):
    """The open-PR listing as a list of objects, None when it is anything else (the count then stays `_jq_length`'s)."""
    try:
        doc = json.loads(listing)
    except ValueError:
        return None
    if isinstance(doc, list) and all(isinstance(item, dict) for item in doc):
        return doc
    return None


def _list_open(repo):
    """`gh pr list` of this author's open PRs in `repo`: (merged output, status)."""
    return _run_capture(
        [
            "gh",
            "pr",
            "list",
            "--repo",
            repo,
            "--author",
            "@me",
            "--state",
            "open",
            "--json",
            "number,title,headRefName,isDraft",
        ]
    )


def _ready_target(selector, root, rows):
    """The head branch a `gh pr ready` selector names: a number (`5`, `#5`, a `/pull/5` URL) read from the open listing, a branch name as given, or the branch checked out at `root`. "" when unknown."""
    m = re.fullmatch(r"#?(\d+)", selector) or re.search(r"/pull/(\d+)", selector)
    if m:
        for row in rows:
            if str(row.get("number")) == m.group(1):
                return row.get("headRefName") or ""
        return ""
    if selector:
        return selector
    return commit_policy.current_branch(root)


def _ready_refusal(ev, run_, cwd):
    """DENY when this `gh pr ready` names a PR other than the landing branch's while that PR is open; None otherwise, and always None with no landing record."""
    args = shellscan.gh_args(run_.argv)
    if args.on("help") or args.on("undo"):
        return None
    repo = _create_repo(run_, cwd, ev.env("GH_REPO"))
    root, record = _bound(run_, cwd, repo)
    if record is None:
        return None
    listing, rc = _list_open(repo)
    rows = _listed(listing) if rc == 0 else None
    if rows is None:
        records, _ = shellscan._records(listing)
        ev.warn_raw(UNVERIFIABLE % (repo, shellscan._command_substitution("\n".join(records[:2]))))
        return hookio.DENY
    landing = record.get("branch", "")
    if not any(row.get("headRefName") == landing for row in rows):
        return None
    target = _ready_target(args.operands[0] if args.operands else "", root, rows)
    if target == landing:
        return None
    ev.warn_raw(READY_REFUSED % (target or "a PR this hook cannot name", repo, _rows(listing)))
    return hookio.DENY


def run(ev):
    cmd = ev.field("tool_input", "command")
    cwd = ev.field("cwd")
    if cmd == "":
        return hookio.ALLOW

    for run_ in shellscan.gh_pr_runs(cmd, "ready"):
        refusal = _ready_refusal(ev, run_, cwd)
        if refusal:
            return refusal

    scan = shellscan._command_substitution(shellscan.scan_target(cmd))
    # Each create's repo is read from its own walked call (`_create_repo`, over `shellscan.gh_run_repo`), so `-R=x`, `-Rx` and `--repo 'x'` count the open PRs of the repo they name: measured 2026-10-07, `gh pr create -R=rediacc/renet` listed console's. Only a command the walk finds no create in keeps the text reader.
    runs = shellscan.gh_pr_runs(cmd, "create")
    # repo -> (the landing branch an admitted draft stands beside or None, the landing record or None).
    repos = {}
    if runs:
        for run_ in runs:
            # `--help` prints the usage and creates nothing.
            if shellscan.gh_args(run_.argv).on("help"):
                continue
            repo = _create_repo(run_, cwd, ev.env("GH_REPO"))
            # A repo the walk cannot evaluate (`-R $R`, `GH_REPO=$(...)`, `cd private/$s`) has no open-PR list to read: refused as unverifiable, never listed under a made-up name (#9de9a8e9).
            if repo == shellscan.UNRESOLVED_REPO:
                named = shellscan.gh_named_repo(run_, ev.env("GH_REPO"))
                why = UNRESOLVED_REASON if named else UNRESOLVED_DIR_REASON % run_.cwd
                ev.warn_raw(UNVERIFIABLE % ("the repository this command names", why))
                return hookio.DENY
            if repo.lower() in PAIRED_SUBMODULE_REPOS:
                beside, record = _submodule_beside(run_, cwd, repo)
            else:
                root, record = _bound(run_, cwd, repo)
                beside = _draft_beside(run_, root, record)
            # A second create of the same repository in one command is a second PR: the admission is for exactly one draft.
            if repo in repos:
                beside = None
                record = record or repos[repo][1]
            repos[repo] = (beside, record)
    elif shellscan.gh_pr_at_command_pos(scan, "create"):
        seg = shellscan.gh_pr_segment(scan, "create")
        repos[shellscan.target_repo(seg, scan, cwd)] = (None, None)
    else:
        return hookio.ALLOW

    for repo, (beside, record) in repos.items():
        refusal = _refusal(ev, repo, beside, record)
        if refusal:
            return refusal
    return hookio.ALLOW


def _refusal(ev, repo, beside=None, record=None):
    """DENY, with the message written, when `repo` already has an open PR of ours that does not stand beside an admitted draft (`beside`, the landing branch), or its open PRs cannot be listed; None otherwise. `record`, the landing record, adds the two-tree rule to the message."""
    listing, rc = _list_open(repo)

    if rc != 0:
        records, _ = shellscan._records(listing)
        head = shellscan._command_substitution("\n".join(records[:2]))
        ev.warn_raw(UNVERIFIABLE % (repo, head))
        return hookio.DENY

    count = _jq_length(listing)
    rows = _listed(listing)
    if rows is not None:
        count = str(len([row for row in rows if not _stands_beside(row, beside)]))
    if not (count != "" and int(count) > 0):
        return None

    note = ""
    if record:
        template = SUBMODULE_NOTE if repo.lower() in PAIRED_SUBMODULE_REPOS else LANDING_NOTE
        note = template % record.get("branch", "")
    ev.warn_raw(ALREADY_OPEN % (count, repo, _rows(listing)) + note)
    return hookio.DENY
