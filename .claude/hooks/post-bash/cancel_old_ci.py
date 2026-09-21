#!/usr/bin/env python3
"""PostToolUse advisory: after a git push, force-cancel older in-progress CI runs on this branch.

Always exits 0 (advisory only). Uses $CLAUDE_PROJECT_DIR so it reads the CURRENT worktree's branch (the previous hardcoded path pointed at the main worktree and misread the branch).

PORTED FROM `.claude/hooks/post-bash/cancel-old-ci.sh` BY W7 P6. The bash original is kept as `.claude/oracles/post-bash/cancel-old-ci.sh` and `.claude/rediacc_hooks/tests/test_post_bash_differential.py` runs both over the same scripted `git` and `gh` stubs, comparing exit code, stdout and stderr byte for byte.

THE 10-SECOND STDIN DEADLINE HAS NO COUNTERPART HERE, and that is a fact about the caller rather than a dropped feature. The twin opens with a bounded `read -r -d "" -t 10` because a stdin that stays open and silent blocks a bare `jq` forever; this hook is advisory, so its deadline exits 0. Since the 2026-09-21 collapse the member is spawned by `lifecycle.run_pattern` with
`input=payload`, which closes the pipe, so the deadline cannot fire on either side and `sys.stdin.read()` is the same read. The differential drives both over a closed stdin for the same reason.

`jq -r '.tool_input.command'` CARRIES NO `// empty`, so an absent key yields the four characters `null` and the scan runs against that string. `Event.raw` is that behaviour, and the asymmetry with `// empty` is the first thing `hookio`'s own header is careful about.

`sort -u` IS SHELLED OUT TO, NOT REIMPLEMENTED. `sorted()` is byte order; `sort -u` follows the collation of whatever locale the hook runs under. Branch names are ASCII today so the two agree, but a port that quietly depended on that would diverge the first time a branch carried a separator.

THE TRAILING SPACE IN `BRANCHES` IS REAL AND IS PRINTED. The twin ends the pipeline with `tr '\\n' ' '`, which turns the final newline into a space, and command substitution strips trailing NEWLINES rather than spaces. So the advisory reads `across: 0914-1 .` and the port reproduces that rather than tidying it.

`gh api ... -X POST 2>/dev/null` REDIRECTS ONLY STDERR, so the REST response body lands on this hook's stdout, ahead of both advisories. That is the twin's behaviour and the ordering is preserved here by writing each response as it arrives.
"""

import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from rediacc_hooks import hookio

REPO = "rediacc/console"

CANCELLED = (
    "⚡ Auto-cancelled %d old CI run(s) across: %s. The new push triggers a fresh CI run. "
    "Trace it with .ci/scripts/ci/ci-trace.py --wait (run_in_background: true); ad-hoc watch "
    "commands are refused by the pre-bash guard. Auto-retries land as attempt 2 of the SAME "
    "Console CI run, and the script reads the head's check rollup, so that rerun replaces the "
    "old attempt rather than producing a stale verdict."
)

REFRESH = (
    "📝 If a PR is open for any of: %s, refresh its description NOW (gh api "
    "repos/rediacc/console/pulls/<N> -X PATCH -F body=@<file>, then re-read it to verify -- gh "
    "pr edit --body fails SILENTLY here and is refused by the pre-bash guard). The "
    "PR-Description gate fails when the body is older than the newest commit. Stale-only "
    "failure? Refresh + 'gh run rerun <id> --failed' (no commit needed)."
)


def _capture(argv):
    """A command substitution: stdout with trailing newlines stripped, stderr discarded."""
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, check=False)
    except OSError:
        return ""
    return proc.stdout.rstrip("\n")


def _sort_u(lines):
    """`sort -u`, shelled out to for its collation. See the module docstring."""
    if not lines:
        return []
    try:
        proc = subprocess.run(
            ["sort", "-u"],
            input="\n".join(lines) + "\n",
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return sorted(set(lines))
    return [line for line in proc.stdout.split("\n") if line != ""]


def destinations(cmd):
    """Every branch this push targeted, as the twin's token scan reads them.

    BRANCHES TO CONSIDER = the checked-out branch PLUS every branch this push actually targeted. Using only the checked-out branch made this hook a NO-OP for any wave that pushes with an explicit refspec.

    Observed 2026-07-29: the working branch was 0728-3 while PR #543's CI runs on 0728-2, because each push was `git push origin 0728-3` followed by `git push origin HEAD:0728-2`. The hook queried 0728-3, which has ZERO runs, found nothing to cancel, and exited 0 looking healthy. Meanwhile round 13 kept running and round 14 queued behind it -- a duplicate full round of machine
    time on every push of the wave.

    So parse the refspec out of the command: `HEAD:0728-2` and `0728-3` both name a destination branch, and a bare `git push` targets the current one.
    """
    # `sed -n 's/.*git push//p'`: per line, GREEDY, so everything up to the LAST occurrence goes, and a line that never matched is not printed at all.
    tail = []
    for line in cmd.split("\n"):
        _, sep, rest = line.rpartition("git push")
        if sep:
            tail.append(rest)
    found = []
    for tok in " ".join(tail).split():
        if tok.startswith("-") or tok in ("origin", "gitlab"):
            continue
        found.append(tok.rsplit(":", 1)[-1] if ":" in tok else tok)
    return found


def main():
    payload = sys.stdin.read()
    cmd = hookio.Event(payload).raw("tool_input", "command")
    if not hookio.grep_q_line("git push", cmd):
        return 0

    root = hookio.Event(payload).project_dir
    branch = _capture(["git", "-C", root, "rev-parse", "--abbrev-ref", "HEAD"])
    # `rev-parse --abbrev-ref HEAD` returns the LITERAL STRING "HEAD" on a detached checkout, unlike `symbolic-ref` which fails outright (see wl_core.py's git_branch, which chose symbolic-ref for exactly this reason). Guarded explicitly rather than relying on "no branch is ever named HEAD" as an implicit safety net: `gh pr list --head HEAD` would just find nothing today, but
    # that is luck holding the door shut, not a check.
    if branch in ("", "main", "HEAD"):
        return 0

    branches = _sort_u([b for b in [branch, *destinations(cmd)] if b not in ("", "main")])
    listed = "".join(b + " " for b in branches)

    # Cancel only runs that are GENUINELY superseded, i.e. built from a sha that is no longer the tip of origin/$BRANCH.
    #
    # This hook fires on ANY command containing `git push`, including a push to a SUBMODULE (private/renet, private/account). Those pushes do not advance the console branch, so the in-flight console run is still the one wanted, yet the old logic cancelled it anyway, because it matched every queued/in_progress run regardless of sha. The documented workflow is "submodules first,
    # then console", so this hook was force-cancelling a live console run on essentially every cycle: rounds 10 and 12 of the P4 wave died exactly this way, each showing the misleading "cancelled + zero failed jobs" signature.
    #
    # Comparing against the freshly-fetched tip makes the rule honest: a run whose headSha IS the tip is current (do not touch it); a run whose headSha is not is superseded (cancel it).
    count = 0
    for name in branches:
        subprocess.run(
            ["git", "-C", root, "fetch", "origin", name, "--quiet"],
            stderr=subprocess.DEVNULL,
            check=False,
        )
        tip = _capture(["git", "-C", root, "rev-parse", "origin/%s" % name])
        if tip == "":
            continue
        # NOTE: `gh ... --jq` does NOT accept jq's `--arg`, so the tip is interpolated into the filter. The tip is a hex sha from rev-parse, so there is nothing to quote-escape.
        runs = _capture(
            [
                "gh",
                "run",
                "list",
                "--repo",
                REPO,
                "--branch",
                name,
                "--json",
                "databaseId,status,headSha",
                "--jq",
                '.[] | select(.status == "in_progress" or .status == "queued") '
                '| select(.headSha != "%s") | .databaseId' % tip,
            ]
        )
        if runs == "":
            continue
        for rid in runs.split():
            try:
                proc = subprocess.run(
                    [
                        "gh",
                        "api",
                        "repos/%s/actions/runs/%s/force-cancel" % (REPO, rid),
                        "-X",
                        "POST",
                    ],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    text=True,
                    check=False,
                )
            except OSError:
                continue
            sys.stdout.write(proc.stdout)
            if proc.returncode == 0:
                count += 1

    if count > 0:
        sys.stdout.write(CANCELLED % (count, listed) + "\n")
    sys.stdout.write(REFRESH % listed + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
