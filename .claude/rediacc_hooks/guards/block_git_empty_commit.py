"""Block empty commits used to re-trigger CI.

THE ONE CASE THIS USED TO GET WRONG. The block is unconditional, and its advice is "rerun the run" -- which presupposes a run EXISTS. On 2026-08-26 GitHub created no run at all for PR #577: Actions was enabled, the workflow was
`state=active`, `pull_request: [opened, synchronize]` matched, the branch was
not a fork, there was no draft filter, and an unrelated scheduled run was created 13 seconds after the PR was opened -- so Actions was demonstrably alive. `gh api .../commits/<head>/check-runs` returned `total_count: 0`, and no `startup_failure` run existed either. There was nothing to rerun, and `workflow_dispatch` is guarded to `main` and cannot satisfy PR checks, so the only
remaining lever was a commit -- which this hook refused.

THE CAUSE, established after the fact: githubstatus.com reported Actions in `major_outage` with a critical open incident. So the trigger was an outage, not a repo misconfiguration -- but that is exactly the point rather than a reason to revert this. An outage is the most likely way a head ends up with no run at all, it is invisible from inside the repo (every local signal said
"should have run"), and it is precisely when a session needs the one lever this hook was
refusing. Check githubstatus.com BEFORE spending rounds on config archaeology;
it cost several here.

A guard whose advice is unreachable in the case it fires on stops being a guard. So the escape is a CHECK, not a flag: name the head sha you believe has no run, and the hook VERIFIES that against GitHub. If a run exists the block stands and you are told to rerun it, which is the original advice arriving at the moment it is actually true.

  CI_RETRIGGER_NO_RUN_FOR=<head-sha> git commit --allow-empty -m "..."

It cannot be used to dodge the rerun advice: the verification fails whenever there is something to rerun. It fails CLOSED on every uncertainty -- no `gh`, an API error, a sha that is not HEAD -- because "I could not check" must never read as "there is no run".

ROUTED THROUGH lib/command-scan.sh 2026-08-27. Matching the raw command meant matching PROSE: `echo '<the banned command>'` was refused, and so was a worklist note or a doc quoting it. hook_scan_target removes heredoc bodies and quoted spans while still extracting `sh -c` / `eval` payloads, so a command hidden in a wrapper is scanned exactly as before -- this narrows what the guard
refuses, never what it catches.

PORT NOTE ON WHERE `git rev-parse HEAD` RUNS. The bash does not `cd` anywhere, so HEAD is read from the hook process's own working directory and NOT from CLAUDE_PROJECT_DIR. That is carried across by leaving `cwd` unset on the call below; passing the project dir would be a fix, and this is a port.
"""

from rediacc_hooks import hookio, shellscan

CHAIN = "pre-bash"
TWIN = "pre-bash/block-git-empty-commit.sh"
ORDER = 20

# Removing the verified escape restores exactly the 2026-08-26 defect: the block goes back to being unconditional, so the one case where its own advice is unreachable is refused again.
DEFECT = ('if claim != "":', "if False:")

# ANCHORED TO COMMAND POSITION 2026-08-28. Routing through command-scan.sh in the comment above fixed the QUOTED case (`echo '<the banned command>'`) and left the unquoted one: hook_scan_target strips quoted spans, so an ordinary unquoted sentence advising against the command survived it intact and this guard BLOCKED it -- a worklist note or a doc line refused as if it were the
# command itself. Measured before the fix: exit 2 on such a sentence.
#
# SAME DEFECT CLASS as block-bash-write-to-running-script.sh and block-roundlog-truncate.sh, both fixed earlier the same day: a guard that matches a MENTION rather than a TARGET.
ALLOW_EMPTY = hookio.rx(r"(^|[;&|(]|&&|\|\|)[{S}]*git[{S}]+commit[^|;&]*--allow-empty")

ADVICE = (
    "Instead, rerun the run: for failures in tunnel-CONSUMER jobs (Tests+Infra E2E / CLI / "
    "E2E Electron, or any job that waited on 'tunnel URL'), use a FULL 'gh run rerun RUN_ID "
    "--repo rediacc/console', because the tunnel-url artifact is named per run_attempt and "
    "the already-green publisher job (infra-backend) does not rerun on --failed, so a "
    "--failed rerun leaves consumers waiting 300s for an artifact that never appears. For "
    "all other failures, 'gh run rerun RUN_ID --repo rediacc/console --failed' is cheaper "
    "and sufficient. If the run was force-cancelled and the AI classified a transient "
    "failure as code-change, first update .ci/prompts/ci-failure-classifier.md so that "
    "pattern is recognized as transient, then rerun."
)

# A FIXED sha, from a `git` stub, and that is not cosmetic. The verified arm prints HEAD into its message, so a real HEAD would put this differential at the mercy of any other session committing between the bash pass and the Python pass -- two runs of the same case disagreeing for a reason that is not a port defect. The stub makes the world the same for both sides.
_GIT_STUB = "#!/bin/sh\necho 1111111111111111111111111111111111111111\n"

ENVS = [
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
    # Fails CLOSED: "I could not check" must never read as "there is no run".
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


def run(ev):
    cmd = ev.raw("tool_input", "command")
    scan = shellscan._command_substitution(shellscan.scan_target(cmd))

    if not hookio.grep_q(ALLOW_EMPTY, scan):
        return hookio.ALLOW

    claim = ev.env("CI_RETRIGGER_NO_RUN_FOR", "")
    if claim != "":
        reason = ""
        head_sha = None
        if not hookio.have("gh"):
            reason = "gh is not available, so the no-run claim cannot be verified"
        else:
            head_sha = hookio.git_out(["rev-parse", "HEAD"], want_rc=True)
            if head_sha is None:
                reason = "could not read HEAD, so the claimed sha cannot be checked against it"
            elif head_sha.removeprefix(claim) == head_sha:
                # `${head_sha#"$CLAIM"}` removes the shortest matching PREFIX,
                # once, and leaves the string untouched when it is absent -- which is exactly what this comparison is testing for.
                reason = "CI_RETRIGGER_NO_RUN_FOR='%s' is not a prefix of HEAD (%s)" % (
                    claim,
                    head_sha,
                )
            else:
                count = hookio.run_out(
                    [
                        "gh",
                        "api",
                        "repos/rediacc/console/commits/%s/check-runs" % head_sha,
                        "--jq",
                        ".total_count",
                    ],
                    want_rc=True,
                )
                if count is None:
                    reason = (
                        "the check-runs API could not be read; 'I could not check' is not "
                        "'there is no run'"
                    )
                elif not hookio.grep_q_line(r"^[0-9]+$", count):
                    reason = "the check-runs API returned a non-numeric count ('%s')" % count
                elif int(count) != 0:
                    reason = (
                        "%s check-run(s) already exist for %s -- there IS something to rerun"
                        % (
                            count,
                            head_sha,
                        )
                    )

        if reason == "":
            ev.warn(
                "ℹ️  empty commit ALLOWED: verified 0 check-runs for HEAD (%s), so there is no "
                "run to rerun and a commit is the only lever left." % head_sha
            )
            return hookio.ALLOW

        ev.warn("❌ BLOCKED: the no-run claim did not verify -- %s." % reason)
        ev.warn("   %s" % ADVICE)
        return hookio.DENY

    ev.warn(
        "❌ BLOCKED: Do not use empty commits to re-trigger CI. Empty commits kick off a fresh "
        "CI run (attempt 1 of 2) that redoes ALL jobs and wastes runner minutes. %s" % ADVICE
    )
    ev.warn(
        "   If GitHub created NO run at all for this head (verify: gh api "
        "repos/rediacc/console/commits/$(git rev-parse HEAD)/check-runs --jq .total_count), "
        "there is nothing to rerun; re-run this command with "
        "CI_RETRIGGER_NO_RUN_FOR=$(git rev-parse HEAD), which makes the hook check that claim "
        "itself."
    )
    return hookio.DENY
