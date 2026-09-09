"""A PR must not be opened from a branch carrying an OLD date.

WHAT WENT WRONG, 2026-08-26: PR #575 was opened from branch `0825-2`. The
branch itself was created correctly at 23:50 the previous night, but the PR
was filed the NEXT day, so it shipped with yesterday's number. Nothing
noticed, because every existing pr-create guard asks a different question:
block-nondraft-pr-create.sh asks "is it a draft", block-second-open-pr.sh
asks "is one already open". Neither looks at the branch NAME.

The convention is stated in .claude/commands/pr-babysit.md's state block:

    Today (branch base): `date +%m%d`   (feature branches are `MMDD-N`)

It is keyed to the day the WAVE is filed, which is what makes a stale branch
name misleading rather than merely untidy: `git branch -r | grep "$(date
+%m%d)-"` is how a session finds today's waves, and a PR filed from an older
name is invisible to that lookup.

WHY THIS BLOCKS RATHER THAN RENAMING FOR YOU. A hook that mutated git state
mid-command would rename the local branch while the remote kept the old one,
leaving the push tracking a branch that no longer exists -- a worse mess than
the one it fixed, created at the exact moment the session is not looking. So
it does the whole computation (including picking the next free N against the
remote) and hands back a ready-to-run command.

ESCAPE HATCH: PR_BRANCH_DATE_OK=1 for a deliberately long-lived branch, e.g.
resuming a genuinely multi-day wave onto its original PR. It is an env var and
not a flag so it cannot be pasted in by habit.

PORT NOTE ON THE CLOCK, and the defect it hid until 2026-09-07.

`date +%m%d` is the one input here that neither side controls. The differential
runs both implementations within seconds of each other, so they agree except
across a midnight boundary, and `TZ=UTC` is pinned in the harness environment
for BOTH sides so that boundary is at least the same boundary.

THAT PIN IS ALSO WHAT MADE THE DIFFERENTIAL BLIND. This port read the clock as
`datetime.now(tz=datetime.UTC)` -- UTC unconditionally -- while the twin's bare
`date +%m%d` reads LOCAL time and merely honours TZ. Under the harness both are
UTC, so the two could never disagree there; in production, on a machine at
UTC+2, they disagreed for the two hours after local midnight. Measured on
2026-09-07 at 00:47 CEST: `test-hooks.sh` reported

    FAIL [0] stale-pr-branch: today's MMDD allowed (got exit 2)

with the port refusing branch `0907-9` and saying "today is 0906" while the twin
allowed it. That is a guard REFUSING correct work, which is the shape that gets a
guard bypassed rather than obeyed.

The fix is one call: `datetime.now()` is local and honours TZ, exactly as `date`
does, so the harness's `TZ=UTC` still makes both sides agree and production now
agrees too. The general lesson is worth the paragraph: a harness that PINS an
environment variable removes the only input that distinguishes two
implementations, and the differential then proves they agree about everything
except the thing that differs.
"""

import datetime
import os
import pathlib

from rediacc_hooks import hookio, shellscan

CHAIN = "pre-bash"
TWIN = "pre-bash/block-stale-pr-branch-date.sh"
ORDER = 24

# The escape hatch. Without it a deliberately long-lived branch (resuming a
# multi-day wave onto its existing PR) can never file its PR, which is the
# shape that gets a guard bypassed rather than obeyed.
DEFECT = ('if ev.env("PR_BRANCH_DATE_OK") != "":', "if False:")

HEAD_FLAG = hookio.rx(r"(--head|-H)[{S}=]+[A-Za-z0-9._/-]+")

EDGE_CASES = [
    # An explicit --head wins over the checkout, which is what makes the stale
    # case reachable at all from a payload.
    ("an explicitly stale head", "gh pr create --draft --head 0825-2 --fill"),
    ("a stale head with -H", "gh pr create --draft -H 0101-1 --fill"),
    ("a head that is not MMDD-N is out of scope", "gh pr create --draft --head my-branch --fill"),
    ("a four-digit head with no suffix is out of scope", "gh pr create --draft --head 0825 --fill"),
    ("no head at all falls back to the checkout", "gh pr create --draft --fill"),
    ("gh pr edit is not gh pr create", "gh pr edit 42 --add-label ci"),
    ("prose naming the verb", "echo 'then gh pr create --draft'"),
    ("a wrapper payload is still at a command position", "sh -c 'gh pr create --head 0825-2'"),
    # THE TWO CLOCKS, and these two cases exist because a defect lived between
    # them. One head carries UTC's today, the other carries the machine's local
    # today; on any machine whose offset is not zero they are DIFFERENT strings
    # for part of every day, so an implementation that hard-codes UTC and one
    # that honours TZ answer differently on at least one of them. Computed at
    # import rather than written as a literal: a fixed date would be stale
    # tomorrow and the pair would collapse back into "two old branches".
    (
        "a head carrying UTC's today",
        "gh pr create --draft --head %s-9 --fill"
        % datetime.datetime.now(tz=datetime.UTC).strftime("%m%d"),
    ),
    (
        "a head carrying the machine's LOCAL today",
        "gh pr create --draft --head %s-9 --fill" % datetime.datetime.now().strftime("%m%d"),  # noqa: DTZ005
    ),
]

ENVS = [
    ("default", {}, {}),
    # The escape hatch, driven rather than described.
    ("escape-hatch", {"PR_BRANCH_DATE_OK": "1"}, {}),
    # TWO EXTREME TIME ZONES, and they are the control for the clock defect the
    # module docstring records. `_base_env` pins `TZ=UTC` for both sides, which
    # is right for determinism and is exactly what made a UTC-hardcoded port
    # indistinguishable from a TZ-honouring twin: the harness had removed the
    # only input that told them apart. `env.update(extra)` runs after that pin,
    # so a module can put the variable back, and these two put it as far either
    # side of the line as real zones go (UTC+14 and UTC-12). With the two
    # today-cases above, one of these four combinations always straddles a date
    # boundary, so the differential can see the class rather than being blind to
    # it by construction.
    ("tz-far-east", {"TZ": "Etc/GMT-14"}, {}),
    ("tz-far-west", {"TZ": "Etc/GMT+12"}, {}),
]


def run(ev):
    # `jq -r '.tool_input.command // empty'`: an absent command is "" here, not
    # the four characters "null", because this guard spells the `// empty` form.
    cmd = ev.field("tool_input", "command")

    scan = shellscan._command_substitution(shellscan.scan_target(cmd))
    if not shellscan.gh_pr_at_command_pos(scan, "create"):
        return hookio.ALLOW

    if ev.env("PR_BRANCH_DATE_OK") != "":
        return hookio.ALLOW

    # Fall back to $PWD rather than bailing: a hook already runs with the project
    # as its cwd, and bailing on a missing .cwd would be a FAIL-OPEN -- the payload
    # that omits it is exactly the one a bypass would use.
    cwd = ev.field("cwd")
    if not (cwd != "" and pathlib.Path(cwd).is_dir()):
        cwd = os.environ.get("PWD") or os.getcwd()
    if not pathlib.Path(cwd).is_dir():
        return hookio.ALLOW

    # The branch this PR would come from: an explicit --head wins, else the checkout.
    branch = ""
    matches = hookio.grep_o(HEAD_FLAG, hookio._printf_line(scan))
    if matches:
        branch = hookio.sed_sub(hookio.rx(r"^(--head|-H)[{S}=]+"), "", matches[0]).rstrip("\n")
    if branch == "":
        branch = hookio.git_out(["-C", cwd, "branch", "--show-current"])
    if branch == "":
        return hookio.ALLOW

    # Only police the MMDD-N convention. A differently-shaped branch name is out of
    # scope here: this guard answers "is the date stale", not "is the name legal",
    # and conflating the two would make it fire on every non-wave branch.
    shape = hookio.grep_o(r"^([0-9]{4})-([0-9]+)$", branch)
    if not shape:
        return hookio.ALLOW
    br_date = branch.split("-", 1)[0]
    # LOCAL, not UTC. The twin is a bare `date +%m%d`, which is local time
    # honouring TZ; `datetime.now(tz=UTC)` ignores TZ and was wrong by a day for
    # two hours every night east of Greenwich. See the clock note in the module
    # docstring for the measurement.
    today = datetime.datetime.now().strftime("%m%d")  # noqa: DTZ005 -- see above
    if br_date == today:
        return hookio.ALLOW

    # Pick the next free N for today, against the remote AND local, so the suggested
    # command cannot collide with a wave another session already filed.
    nxt = 1
    while (
        hookio.run_rc(
            ["git", "-C", cwd, "show-ref", "--verify", "--quiet", "refs/heads/%s-%d" % (today, nxt)]
        )
        == 0
        or hookio.run_rc(
            [
                "git",
                "-C",
                cwd,
                "show-ref",
                "--verify",
                "--quiet",
                "refs/remotes/origin/%s-%d" % (today, nxt),
            ]
        )
        == 0
    ):
        nxt += 1
        if nxt > 99:
            break
    new = "%s-%d" % (today, nxt)

    ev.warn_raw(
        "❌ BLOCKED: branch '%s' carries an OLD date; today is %s.\n"
        "\n"
        "Feature branches are MMDD-N keyed to the day the wave is FILED\n"
        "(.claude/commands/pr-babysit.md). A PR opened from '%s' is invisible to\n"
        "the lookup every session uses to find today's waves:\n"
        "\n"
        '    git branch -r | grep "$(date +%%m%%d)-"\n'
        "\n"
        "Rename to the next free slot, then re-run your 'gh pr create':\n"
        "\n"
        '    git -C "%s" branch -m "%s" "%s"\n'
        '    git -C "%s" push origin --delete "%s" 2>/dev/null || true\n'
        '    git -C "%s" push -u origin "%s"\n'
        "\n"
        "Not renaming for you on purpose: doing it mid-command would leave the remote\n"
        "pointing at the old name while the local branch moved.\n"
        "\n"
        "If this branch is deliberately long-lived (resuming a multi-day wave onto its\n"
        "existing PR), re-run with PR_BRANCH_DATE_OK=1.\n"
        % (branch, today, branch, cwd, branch, new, cwd, branch, cwd, new)
    )
    return hookio.DENY
