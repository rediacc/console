"""The test tables of `block_unlinked_commit_author`, moved out of the guard so a hook call imports no test data (PLAN-tooling-code-reduction CR5); the guard forwards each name here through `guards.tables`."""

from rediacc_hooks.wellknown import OPERATOR_EMAIL

EDGE_CASES = [
    ("a plain commit", 'git commit -m "feat(x): a change"'),
    # The three override shapes the 2026-09-03 finding names, none of which a `git config` read would have seen.
    ("a -c user.email override", 'git -c user.email=nobody@example.invalid commit -m "x"'),
    ("a GIT_AUTHOR_EMAIL override", 'GIT_AUTHOR_EMAIL=nobody@example.invalid git commit -m "x"'),
    ("an --author override", 'git commit --author="Nobody <nobody@example.invalid>" -m "x"'),
    (
        "an --author override, single quoted",
        "git commit --author='Nobody <nobody@example.invalid>' -m 'x'",
    ),
    # The false positive that this guard's own first commit produced: the
    # message EXPLAINING --author= must not be read as one.
    ("--author named inside the message", 'git commit -m "explain --author=a@b.c in prose"'),
    ("--author named inside a single-quoted message", "git commit -m 'explain --author=a@b.c'"),
    ("a -F message file hides its body", "git commit -F msg.txt"),
    # git's own parse of `--author` (#e8be3092): a unique prefix is the option, and the value is the next word whatever it holds.
    (
        "an --auth override (a unique prefix)",
        'git commit --auth="Nobody <nobody@example.invalid>" -m "x"',
    ),
    (
        "an --author value as the next word",
        'git commit -q --author "Nobody <nobody@example.invalid>" -m x',
    ),
    # Not a commit at all.
    ("prose about an address", ("echo '" + OPERATOR_EMAIL + " is the wrong one'")),
    ("git tag is deliberately out of scope", 'git tag -m "x" v1'),
    ("gh pr create is deliberately out of scope", "gh pr create --draft --fill"),
    # A submodule of this tree IS judged; an independent checkout is not.
    ("a commit in a submodule", 'cd private/renet && git commit -m "x"'),
    ("a commit in an independent checkout", 'cd /tmp && git commit -m "x"'),
    # A `-c` override, not a submodule's own state, so this arm is exercised deterministically. `[bot]` in the exemption pattern is a bracket, and `hookio.case_glob` once read it as a character class rather than a literal -- silently un-exempting every bot address until a poisoned submodule config surfaced it.
    (
        "a bot committer override is exempt",
        'git -c user.email="github-actions[bot]@users.noreply.github.com" commit -m "x"',
    ),
]
