"""The test tables of `block_git_empty_commit`, moved out of the guard so a hook call imports no test data (PLAN-tooling-code-reduction CR5); the guard forwards each name here through `guards.tables`."""

# A FIXED sha, from a `git` stub, and that is not cosmetic. The verified arm prints HEAD into its message, so a real HEAD would put this differential at the mercy of any other session committing between the bash pass and the Python pass -- two runs of the same case disagreeing for a reason that is not a port defect. The stub makes the world the same for both sides.
_GIT_STUB = "#!/bin/sh\necho 1111111111111111111111111111111111111111\n"


ENVS: list = [
    # No claim at all: the ordinary unconditional block.
    ("no-claim", {}, {}),
    # The 2026-08-26 case: a verified zero, so the commit is the only lever.
    (
        "claim-verified",
        {"CI_RETRIGGER_NO_RUN_FOR": "1111111"},
        {"git": _GIT_STUB, "gh": "#!/bin/sh\necho 0\n"},
    ),
    # There IS something to rerun, so the original advice is correct and stands.
    (
        "claim-has-runs",
        {"CI_RETRIGGER_NO_RUN_FOR": "1111111"},
        {"git": _GIT_STUB, "gh": "#!/bin/sh\necho 3\n"},
    ),
    # Fails CLOSED: a check that could not run must never read as "there is no run".
    ("claim-api-fails", {"CI_RETRIGGER_NO_RUN_FOR": "1111111"}, {"git": _GIT_STUB}),
    # A sha that is not HEAD proves nothing, so the claim is a CHECK not a flag.
    ("claim-not-head", {"CI_RETRIGGER_NO_RUN_FOR": "deadbeef"}, {"git": _GIT_STUB}),
]


EDGE_CASES = [
    ("the plain shape", "git commit --allow-empty -m x"),
    ("after a separator", "true; git commit --allow-empty -m x"),
    ("after a logical and", "git fetch && git commit --allow-empty -m retrigger"),
    # The two mention-versus-target classes, quoted and unquoted.
    ("quoted prose is not a command", "echo 'git commit --allow-empty -m x'"),
    (
        "an unquoted sentence advising against it",
        "echo do not git commit --allow-empty to retrigger",
    ),
    ("a wrapper payload is still scanned", "sh -c 'git commit --allow-empty -m x'"),
    ("an ordinary commit", "git commit -m 'fix(cli): x'"),
]
