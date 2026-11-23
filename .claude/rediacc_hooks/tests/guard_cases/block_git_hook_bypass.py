"""The test tables of `block_git_hook_bypass`, moved out of the guard so a hook call imports no test data (PLAN-tooling-code-reduction CR5); the guard forwards each name here through `guards._cases.lazy`."""

EDGE_CASES = [
    ("commit --no-verify", "git commit --no-verify -m x -- a"),
    ("commit -n", "git commit -n -m x -- a"),
    ("a bundled -n", "git commit -anm x"),
    ("-c core.hooksPath", "git -c core.hooksPath=/dev/null commit -m x -- a"),
    ("config core.hooksPath", "git config core.hooksPath /tmp/x"),
    ("config --unset", "git config --unset core.hooksPath"),
    ("push --no-verify", "git push --no-verify origin 0923-1"),
    ("the override set by an agent", "COMMIT_POLICY_OK=1 git commit -m x -- a"),
    (
        "the release-run record set by an agent",
        "REDIACC_RELEASE_RUN=.ci/cache/release/run-1.json git push origin main",
    ),
    ("config --get is a read", "git config --get core.hooksPath"),
    ("config with no value is a read", "git config core.hooksPath"),
    ("log -n is not a commit", "git log -n 5"),
    ("push -n is a dry run", "git push -n origin 0923-1"),
    ("an ordinary commit", "git commit -F m -- a"),
    ("prose naming the flag", "echo 'never git commit --no-verify'"),
    ("the last of --no-verify and --verify wins", "git push --no-verify --verify origin 0923-1"),
    ("am -n is --no-verify", "git am -3n x.patch"),
    ("a unique prefix is the option", "git rebase --no-veri main"),
    ("cherry-pick has no --no-verify", "git cherry-pick --no-verify HEAD"),
]
