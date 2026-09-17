"""ONE OPEN PR AT A TIME. Refuse `gh pr create` when this author already has an
open PR in the target repo.

WHY THIS IS A HOOK AND NOT A LINE IN CLAUDE.md. The operator's ruling, and the incident behind it: a single session opened FOUR stacked PRs over one night, each one individually reasonable (new work arrived, it needed a base, the previous PR was not merged yet), and the result was four unmerged PRs waiting on one person. Nothing in CLAUDE.md or the pr-babysit command stopped it,
because instructions only bind a session that reads them, remembers them, and applies them at the one second that matters. PreToolUse is the only surface that can DENY the command before it runs, which is the difference between a preference and a control.

WHAT TO DO INSTEAD, and the message says so, because a block without a next step just gets worked around: push the new work onto the EXISTING PR's branch. That is almost always what was wanted anyway. A second PR is the right answer only when the work is genuinely independent and the operator has said so.

FAILS CLOSED. If the open-PR list cannot be read, this refuses rather than waving the create through: `gh` being unreachable is not evidence that no PR exists, and creating a duplicate is the expensive direction of the error.

PORT NOTE ON THE TWO SHELL IDIOMS THIS FILE TURNS ON. `LIST=$(gh ... 2>&1)`
followed by `RC=$?` keeps BOTH streams and the status, which no helper in
`hookio` offers (every call site there writes `2>/dev/null` and drops one or the other), so `_run_capture` is private to this module. And
`COUNT=$(... | jq 'length' 2>/dev/null || echo 0)` has three outcomes, not two:
a JSON array gives its length, a jq FAILURE gives the literal `0`, and an EMPTY input gives the EMPTY STRING, because jq with no input prints nothing and exits
0. `[[ "" -gt 0 ]]` is false, so the empty case allows -- the same answer as
zero, by a different route.
"""

import json
import subprocess

from rediacc_hooks import hookio, shellscan

CHAIN = "pre-bash"
TWIN = "pre-bash/block-second-open-pr.sh"
ORDER = 25

# FAILS CLOSED is the property, and this is the line that holds it: without the status test an unreadable list becomes an empty list, and "gh is down" reads as "you have no open PRs".
DEFECT = ("if rc != 0:", "if False:")

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
    "   problem and retry, or ask the operator to create the PR.\n"
)

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
    "   A genuinely independent second PR is the operator's call, not yours. Ask,\n"
    "   and say why the work cannot ride the open one.\n"
)

EDGE_CASES = [
    ("the create this guard exists for", "gh pr create --draft -t x -b y"),
    ("sh -c wrapping does not bypass it", "sh -c 'gh pr create --draft -t x -b y'"),
    # THE CONTROL THAT MATTERS: with no open PR the guard must be invisible, or it would block the FIRST PR too and simply stop all work.
    ("a non-create gh command is ignored", "gh pr view 567"),
    ("a submodule create is judged against ITS repo", "gh pr create --repo rediacc/renet -t x"),
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


def run(ev):
    cmd = ev.field("tool_input", "command")
    cwd = ev.field("cwd")
    if cmd == "":
        return hookio.ALLOW

    scan = shellscan._command_substitution(shellscan.scan_target(cmd))
    if not shellscan.gh_pr_at_command_pos(scan, "create"):
        return hookio.ALLOW

    seg = shellscan.gh_pr_segment(scan, "create")
    repo = shellscan.target_repo(seg, scan, cwd)

    listing, rc = _run_capture(
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

    if rc != 0:
        records, _ = shellscan._records(listing)
        head = shellscan._command_substitution("\n".join(records[:2]))
        ev.warn_raw(UNVERIFIABLE % (repo, head))
        return hookio.DENY

    count = _jq_length(listing)
    if not (count != "" and int(count) > 0):
        return hookio.ALLOW

    ev.warn_raw(ALREADY_OPEN % (count, repo, _rows(listing)))
    return hookio.DENY
