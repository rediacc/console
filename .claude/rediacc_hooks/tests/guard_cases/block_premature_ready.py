"""The test tables of `block_premature_ready`, moved out of the guard so a hook call imports no test data (PLAN-tooling-code-reduction CR5); the guard forwards each name here through `guards.tables`."""

from rediacc_hooks.wellknown import GH_REPO, RENET_REPO

# `gh` answering is what reaches the enforcement path at all. The suite's own `ready_case` stubs it for exactly this reason, and its comment says why the old "cannot be tested here, it is the network" claim was not a good one: "the command that would have disproved it took one minute to write".
ENVS = [
    ("gh-silent-failure", {}, {}),
    ("ci-green", {}, {"gh": "#!/bin/sh\necho SUCCESS\n"}),
    ("ci-red", {}, {"gh": "#!/bin/sh\necho FAILURE\n"}),
]


EDGE_CASES = [
    ("the flip this guard gates", ("gh pr ready 42 --repo " + GH_REPO)),
    ("the flip with no selector at all", "gh pr ready"),
    # --undo can only push a PR back to draft, so it is always safe.
    ("an undo is always allowed", ("gh pr ready --undo 42 --repo " + GH_REPO)),
    # ...and it must belong to THIS invocation, not to a sibling.
    ("an undo followed by a real flip", "gh pr ready --undo 1; gh pr ready 531"),
    # Only console has draft PRs, so a --repo elsewhere is a no-op flip.
    ("a flip on a private submodule repo", ("gh pr ready 42 --repo " + RENET_REPO)),
    (
        "a sibling view must not donate its repo",
        ("gh pr view 1 --repo " + RENET_REPO + "; gh pr ready 531"),
    ),
    ("a different pr subcommand", "gh pr view 42"),
    ("prose naming the command", "echo '; gh pr ready is hook-gated'"),
    # GraphQL parity: the same mutation reached through `gh api graphql` instead of `gh pr ready`.
    ("the GraphQL ready bypass", "gh api graphql -f query=markPullRequestReadyForReview"),
    (
        "the GraphQL ready bypass with flags reordered",
        "gh api graphql -f o=owner -f query=markPullRequestReadyForReview",
    ),
    (
        "the same endpoint querying something else is not a flip",
        "gh api graphql -f query=someOtherQuery",
    ),
    (
        "prose naming the GraphQL bypass",
        "git commit -m '...gh api graphql markPullRequestReadyForReview...'",
    ),
    # RULE T (PLAN-retire-bash-oracles A4, A0 L3). The suite used to assert that a round-log heredoc mentioning `gh pr ready` in BACKTICKS was prose. With an unquoted delimiter it is not: bash expands the backticks while writing the log and really flips the PR. The quoted-delimiter spelling is the prose, and stays allowed.
    (
        "L3 backticks in an unquoted heredoc run",
        "cat >> log.md <<EOF\ngreen-gated `gh pr ready` + hook-banned --admin\nEOF",
    ),
    (
        "control: the same line under a quoted delimiter is prose",
        "cat >> log.md <<'EOF'\ngreen-gated `gh pr ready` + hook-banned --admin\nEOF",
    ),
]
