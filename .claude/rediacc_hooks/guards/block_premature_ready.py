"""Gate `gh pr ready` on green CI: a console PR may leave draft state ONLY when
the single required check, "CI Complete", is SUCCESS on its current head.
Flipping ready is what triggers the automated Claude review, and the review
invariant is "non-draft AND green" -- this hook enforces the green half.

`gh pr ready --undo` (back to draft) is always allowed: it can never expose
an unreviewed/red PR. Network paths here are NOT covered by test-hooks.sh
(only the pattern paths are); verification failures fail CLOSED.

PORT NOTE ON `${CONCLUSION:-verification failed}`. `:-` fires on an EMPTY value
as well as an unset one, and empty is precisely what the network path yields
when `gh` cannot answer -- so the fail-closed message reads "got: verification
failed" rather than "got: ". The Python below therefore tests for the empty
string, not for None; there is no unset case to distinguish.
"""

from rediacc_hooks import hookio, shellscan

CHAIN = "pre-bash"
TWIN = "pre-bash/block-premature-ready.sh"
ORDER = 26

# The `--undo` test read from the whole line instead of from this invocation:
# `gh pr ready --undo 1; gh pr ready 531` then looks like an always-allowed
# undo and the real flip skips the green gate entirely.
DEFECT = ("hookio.grep_q_line(UNDO, seg)", "hookio.grep_q_line(UNDO, scan)")

UNDO = r"--undo"

# `gh` answering is what reaches the enforcement path at all. The suite's own `ready_case` stubs it for exactly this reason, and its comment says why the old "cannot be tested here, it is the network" claim was not a good one: "the command that would have disproved it took one minute to write".
ENVS = [
    ("gh-silent-failure", {}, {}),
    ("ci-green", {}, {"gh": "#!/bin/sh\necho SUCCESS\n"}),
    ("ci-red", {}, {"gh": "#!/bin/sh\necho FAILURE\n"}),
]

MESSAGE = (
    "❌ BLOCKED: 'gh pr ready' requires CI Complete = SUCCESS on the PR's current head (got: "
    "%s). Read the current state with .ci/scripts/ci/ci-trace.py (exit 0 green, 1 red, 2 no "
    "verdict, 3 head moved); it names the failing job and step. A draft flips to ready only "
    "when CI is green -- that flip triggers the automated Claude review, whose invariant is "
    "non-draft AND green. Wait out the running CI (armed terminal-state watch), fix the red, "
    "or if this was a gh/network hiccup, re-run the exact same command."
)

EDGE_CASES = [
    ("the flip this guard gates", "gh pr ready 42 --repo rediacc/console"),
    ("the flip with no selector at all", "gh pr ready"),
    # --undo can only push a PR back to draft, so it is always safe.
    ("an undo is always allowed", "gh pr ready --undo 42 --repo rediacc/console"),
    # ...and it must belong to THIS invocation, not to a sibling.
    ("an undo followed by a real flip", "gh pr ready --undo 1; gh pr ready 531"),
    # Only console has draft PRs, so a --repo elsewhere is a no-op flip.
    ("a flip on a private submodule repo", "gh pr ready 42 --repo rediacc/renet"),
    (
        "a sibling view must not donate its repo",
        "gh pr view 1 --repo rediacc/renet; gh pr ready 531",
    ),
    ("a different pr subcommand", "gh pr view 42"),
    ("prose naming the command", "echo '; gh pr ready is hook-gated'"),
]


def run(ev):
    cmd = ev.field("tool_input", "command")
    # Two-stage false-positive defense, both learned from live firings: 1. Strip quoted strings (multi-line aware: newlines are folded so a quoted commit message spanning lines is one strippable blob) -- v2 fired on a
    #    `git commit -m` body whose prose said "; gh pr ready is hook-gated".
    # 2. Command-position anchor on what remains (line start or after ; & | $( )
    # -- v1 fired on a heredoc mentioning the command in prose. Bypass-resistant scanning so `sh -c 'gh pr ready'` cannot skip the green gate. SCAN carries both the prose-stripped command and any unwrapped wrapper payload, and every field below is parsed from it -- one view, no drift between two regexes. See lib/command-scan.sh.
    scan = shellscan._command_substitution(shellscan.scan_target(cmd))
    if not shellscan.gh_pr_at_command_pos(scan, "ready"):
        return hookio.ALLOW

    # Every field below is read from the SEGMENT that carries `gh pr ready`, never
    # from the whole bash line. Line-wide parsing let a sibling command donate its
    # fields to this one: `gh pr ready --undo 1; gh pr ready 531` looked like an
    # always-allowed undo, and `gh pr view 1 --repo rediacc/renet; gh pr ready 531`
    # looked like a non-console flip -- both would have skipped the green gate entirely. See hook_gh_pr_segment.
    cwd = ev.field("cwd")
    segs = shellscan.gh_pr_segment(scan, "ready")
    records, _ = shellscan._records(shellscan._here_string(segs))
    for seg in records:
        if seg == "":
            continue
        # --undo (always safe: it can only push a PR back to draft) must belong to THIS invocation, not to a sibling one earlier on the line.
        if hookio.grep_q_line(UNDO, seg):
            continue

        # Only console has draft PRs (free plan, public repo). A --repo pointing
        # elsewhere is a no-op flip; let gh handle it.
        repo = shellscan.target_repo(seg, scan, cwd)
        if repo != "rediacc/console":
            continue

        # PR selector: first bare number/URL/branch token after `ready`, else the session cwd's current branch (matching gh's own default resolution).
        sel = shellscan._command_substitution(shellscan.pr_selector(seg, "ready"))
        if sel == "":
            sel = hookio.git_out(["-C", cwd or ".", "branch", "--show-current"])

        conclusion = hookio.run_out(
            [
                "timeout",
                "20",
                "gh",
                "pr",
                "view",
                sel,
                "--repo",
                "rediacc/console",
                "--json",
                "statusCheckRollup",
                "--jq",
                '[.statusCheckRollup[] | select(.name == "CI Complete")] | first | .conclusion // "ABSENT"',
            ]
        )
        if conclusion != "SUCCESS":
            ev.warn(MESSAGE % (conclusion if conclusion != "" else "verification failed"))
            return hookio.DENY
    return hookio.ALLOW
