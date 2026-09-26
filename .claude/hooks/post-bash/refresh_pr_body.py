#!/usr/bin/env python3
"""PostToolUse: after a git push, keep the PR description current with what was just pushed. Always exits 0 (advisory only).

WHY THIS EXISTS. `Quality / Static` runs a PR-description freshness gate, and a push that lands after the last body edit fails it. One session hit that twice, each time costing a full 55-minute CI round for a mistake that takes ten seconds to fix, because the body refresh kept being treated as a step AFTER the push instead of part of it.

The Stop hook already blocks on the same condition, but blocking is the wrong moment: by then the push has happened and CI is already running the wrong answer. Doing it here closes the window entirely.

WHAT IT WRITES, and why it is not gaming the gate. It maintains a delimited block at the end of the body listing the pushed head and the last few commit subjects. That is genuinely useful description content -- a reviewer opening the PR sees what most recently landed -- and it happens to make the body newer than the tip, which is exactly what the gate is asking for. A no-op edit
that only moved a timestamp would satisfy the gate while telling the reader nothing; this tells them something.

PORTED FROM `.claude/hooks/post-bash/refresh-pr-body.sh` BY W7 P6. The bash original was kept as `.claude/oracles/post-bash/refresh-pr-body.sh` until PLAN-retire-bash-oracles A3 deleted it; `.claude/rediacc_hooks/tests/test_post_bash_differential.py` compared the two over the same scripted `git` and `gh` stubs, byte for byte, and froze the result as `tests/goldens/post-bash.jsonl` before the deletion. The same suite now runs this port against that golden.

THE 10-SECOND STDIN DEADLINE HAS NO COUNTERPART HERE, for the reason its sibling `cancel_old_ci.py` records: since the 2026-09-21 collapse the member is spawned with the payload already on a closed pipe, so neither side's deadline can fire.

`|| continue` ON A COMMAND SUBSTITUTION tests the EXIT STATUS of the command inside it, not whether it printed anything, and the twin uses both idioms within four lines of each other. Each one is carried across as written: a `gh` that exits non-zero skips the branch, and a `gh` that exits 0 printing nothing falls to the emptiness test on the next line.
"""

import pathlib
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from rediacc_hooks import hookio

BEGIN = "<!-- pushed-head:begin -->"
END = "<!-- pushed-head:end -->"


def _run(argv):
    """`$(cmd 2>/dev/null)`: the trimmed stdout, and the exit status the `||` reads."""
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, check=False)
    except OSError:
        return 127, ""
    return proc.returncode, proc.stdout.rstrip("\n")


def destinations(cmd):
    """Destination branches, same parsing as cancel_old_ci.py: `HEAD:0728-2` and a bare `0728-3` both name one, and a bare `git push` targets the current branch."""
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


def _sort_u(lines):
    """`sort -u`, shelled out to for its collation, exactly as the sibling does."""
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
    return proc.stdout.split("\n")[:-1] if proc.stdout.endswith("\n") else proc.stdout.split("\n")


def strip_block(body):
    """`awk '$0 == b { skip = 1 } !skip { print } $0 == e { skip = 0 }'` over `printf '%s\\n' "$body"`."""
    out = []
    skip = False
    for line in (body + "\n").split("\n")[:-1]:
        if line == BEGIN:
            skip = True
        if not skip:
            out.append(line)
        if line == END:
            skip = False
    return "\n".join(out).rstrip("\n")


def main():
    payload = sys.stdin.read()
    event = hookio.Event(payload)
    cmd = event.raw("tool_input", "command")
    # Word-boundary, or `echo git pushed` matches. It only stayed harmless before because no PR happened to exist for that branch, which is luck, not a guard.
    if not hookio.grep_q_line(hookio.rx(r"git +push([{S}]|$)"), cmd):
        return 0
    # A dry run pushes nothing, so there is nothing to describe.
    if hookio.grep_q_line(r"(^| )--dry-run( |$)", cmd):
        return 0

    root = event.project_dir
    # `command -v gh >/dev/null 2>&1 || exit 0` -- a PATH lookup, not a subprocess.
    if shutil.which("gh") is None:
        return 0

    branch = _run(["git", "-C", root, "rev-parse", "--abbrev-ref", "HEAD"])[1]
    # `rev-parse --abbrev-ref HEAD` returns the LITERAL STRING "HEAD" on a detached checkout, unlike `symbolic-ref` which fails outright. Guarded explicitly rather than relying on "no branch is ever named HEAD" as an implicit safety net, same fix as its sibling cancel_old_ci.py.
    if branch in ("", "main", "HEAD"):
        return 0

    # Derived ONCE. It used to be computed inline inside the loop for `gh pr list` only, so the REST call added later had no repo to name -- a break this script would have shipped had its own reference not been checked.
    gh_repo = _run(["gh", "repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner"])[1]
    if gh_repo == "":
        return 0

    for br in _sort_u([branch, *destinations(cmd)]):
        if br in ("", "main"):
            continue
        rc, pr = _run(
            [
                "gh",
                "pr",
                "list",
                "--repo",
                gh_repo,
                "--head",
                br,
                "--state",
                "open",
                "--json",
                "number",
                "--jq",
                ".[0].number",
            ]
        )
        if rc != 0:
            continue
        if pr in ("", "null"):
            continue

        rc, sha = _run(["git", "-C", root, "rev-parse", "--short=9", "origin/%s" % br])
        if rc != 0:
            continue
        log = _run(["git", "-C", root, "log", "-5", "--format=- `%h` %s", "origin/%s" % br])[1]
        if log == "":
            continue

        rc, body = _run(["gh", "pr", "view", pr, "--json", "body", "--jq", ".body"])
        if rc != 0:
            continue
        # Strip any previous block, then append the current one. Whole-body rewrite is safe here: this is one PR description with one writer, not the shared worklist.
        stripped = strip_block(body)
        # mktemp, NOT "$ROOT/.git/...". This repo uses git WORKTREES, where `.git` is a FILE containing a gitdir pointer, so writing under it fails with "Not a directory" -- which is exactly how the first version of this hook silently did nothing while still exiting 0.
        try:
            handle, tmp = tempfile.mkstemp()
        except OSError:
            continue
        with open(handle, "w", encoding="utf-8") as fh:
            fh.write(
                "%s\n\n%s\n**Last pushed:** `%s`\n\n%s\n%s\n" % (stripped, BEGIN, sha, log, END)
            )
        # `gh pr edit --body-file` CANNOT WORK HERE and never could: measured 2026-08-25 it exits 1 with "GraphQL: Projects (classic) is being deprecated ... (repository.pullRequest.projectCards)" and leaves the body untouched. This hook exists to keep the PR-description freshness gate green automatically, and it had been failing on every single push -- loudly, into a stderr
        # nobody was reading -- which is why that gate kept going red on a branch whose body someone had just refreshed by hand. The REST PATCH form is unaffected by the Projects-classic deprecation.
        try:
            proc = subprocess.run(
                [
                    "gh",
                    "api",
                    "repos/%s/pulls/%s" % (gh_repo, pr),
                    "-X",
                    "PATCH",
                    "-F",
                    "body=@%s" % tmp,
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
            edited = proc.returncode == 0
        except OSError:
            edited = False
        if edited:
            sys.stderr.write(
                "refresh-pr-body: PR #%s description updated for %s (freshness gate satisfied)\n"
                % (pr, sha)
            )
        else:
            sys.stderr.write("refresh-pr-body: PR #%s edit FAILED for %s\n" % (pr, sha))
        pathlib.Path(tmp).unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
