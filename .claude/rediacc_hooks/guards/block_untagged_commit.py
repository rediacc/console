"""Require a PR-TASK trailer naming a REAL epic, so a per-epic review finds its work.

WHY. The review now runs once per epic, and it selects an epic's commits with
`git log --grep='^PR-TASK: <id>'`. A commit with no trailer belongs to no epic,
so it is reviewed by nobody, silently. That is the same shape as the flat review's licence to leave areas unreviewed, moved one level down to where nothing reports it at all.

ANCHORED TO LINE START, deliberately. The sibling guard block-commit-meta.sh states the rule this follows in its own header: a guard whose only failure mode is refusing CORRECT input teaches people to reword honest messages until it
stops complaining. A commit whose prose merely mentions PR-TASK is not tagged;
only a real trailer line is.

THE `-F` BLIND SPOT WAS WIDER THAN IT NEEDED TO BE, and it mattered: measured 2026-08-27, `git commit -F -` was exempted outright, and that is the form every message longer than one line uses. Thirty-six consecutive commits in one session went through this guard without it ever looking at them. They happened to carry trailers; nothing checked.

Two of the three unreadable shapes were never unreadable:
  -F -  with a heredoc  -> the BODY is in the command string, right there
  -F <file>             -> the file is on disk, and readable
Only a piped stdin or a command-substituted message is genuinely opaque, and that case still ALLOWS rather than refusing a commit it cannot judge.

A TYPO IS WORSE THAN A MISSING TRAILER, which is why shape is no longer enough. `PR-TASK: f2757831` (one character off) looks tagged, routes to an epic that does not exist, and no review pass ever reads it. The id is checked against agent/pr/<branch>.md -- the COMMITTED snapshot, not the worklist sidecar, because the sidecar lives in TMPDIR and was found empty on this very branch
while 35 commits carried a live id.

=============================================================================
PORT NOTES
=============================================================================

THE PCRE. `grep -oP '(^|\\n|\\n)[[:space:]]*PR-TASK:[[:space:]]*\\K[0-9a-f]{6,32}'`
is the only PCRE in the whole chain, and the alternation is not a typo: written in the shell it is `(^|\\n|\n)`, so the first alternative is a LITERAL backslash-n and the second is a real newline. That matters because the message text this reads can arrive either way -- a real multi-line `-m` body, or a command string in which the newline is still escaped. `\\K` drops everything
matched so far, which Python spells as a capture group; a lookbehind cannot be used because the alternation is variable width.

`grep -oP` HAS NO POSIX EQUIVALENT and PCRE is not available in Python's `re`
either, so the two features actually used (`\\K` and `{6,32}`) are reproduced
directly rather than the engine being emulated.

WHAT THIS GUARD INHERITS FROM `shellscan.target_root`. Its `-C` hint grep accepts a TAB, but the sed that strips the flag demands a literal space, so a TAB-separated `git -C<tab><path>` resolves to the empty root and this guard then judges the console tree instead of the named submodule. That is a defect in the bash and it is reproduced deliberately, because a port that quietly
improved it would disagree with its oracle and the disagreement would be reported as the port being wrong.
"""

import os
import pathlib
import re
import subprocess

from rediacc_hooks import hookio, shellscan

CHAIN = "pre-bash"
TWIN = "pre-bash/block-untagged-commit.sh"
ORDER = 38

# The id-validation arm is the one the 2026-08-27 typo finding added, and the one that makes a trailer worth more than its shape. With it gone every well-formed id passes, including one that names no epic.
DEFECT = ("if known and not _grep_qx(found, known):", "if False:")

COMMIT_AT_COMMAND_POS = hookio.rx(
    r"(^|[;&|(]|\$\(|`)[{S}]*git([{S}]+-[A-Za-z-]+([{S}]+[^ ;&|]+)?)*[{S}]+commit([{S}]|$)"
)

HAS_MESSAGE_FLAG = hookio.rx(r"\-m([{S}]|=)|--message([{S}]|=)")
HAS_FILE_DASH = hookio.rx(r"(-F|--file)([{S}]|=)[{S}]*-([{S}]|$)")
FILE_ARGS = hookio.rx(r"(-F|--file)([{S}]+|=)[^{S};|&]+")
SNAPSHOT_ID = hookio.rx(r"^`?PR-TASK:[{S}]*[0-9a-f]{6,32}`?$")
TRAILER = re.compile(r"(?:^|\\n|\n)[ \t\n\v\f\r]*PR-TASK:[ \t\n\v\f\r]*([0-9a-f]{6,32})")

MISSING_TRAILER = """BLOCKED: this commit carries no PR-TASK trailer.

The review runs once per epic and selects an epic's commits with
`git log --grep='^PR-TASK: <id>'`. An untagged commit belongs to no epic, so it
is reviewed by nobody and nothing reports the gap.

Add a trailer line naming the epic this change belongs to:

  git commit -m "feat(x): what changed

  PR-TASK: <epic-id>"
"""


def _fixture(path):
    """A checkout on a branch that HAS an epic snapshot.

    Without it the id-validation arm is unreachable: this worktree carries no `agent/pr/<branch>.md`, so `KNOWN` is empty on every case and the guard can only ever answer "missing trailer" or "allowed". The corpus would then have compared two constants for the branch that the 2026-08-27 typo finding exists for.
    """
    env = dict(
        os.environ,
        GIT_AUTHOR_NAME="Fixture",
        GIT_AUTHOR_EMAIL="fixture@example.invalid",
        GIT_COMMITTER_NAME="Fixture",
        GIT_COMMITTER_EMAIL="fixture@example.invalid",
        GIT_CONFIG_GLOBAL="/dev/null",
        GIT_CONFIG_SYSTEM="/dev/null",
    )
    path.mkdir(parents=True)
    subprocess.run(
        ["git", "init", "--initial-branch=0831-1", "-q"],
        cwd=str(path),
        check=True,
        capture_output=True,
        env=env,
    )
    snap = path / "agent" / "pr"
    snap.mkdir(parents=True)
    (snap / "0831-1.md").write_text(
        "### Port the guards\n\n`PR-TASK: a1b2c3d4`\n\n### Wire the registry\n\n`PR-TASK: 0f9e8d7c`\n",
        encoding="utf-8",
    )
    (path / "seed.txt").write_text("seed\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=str(path), check=True, capture_output=True, env=env)
    subprocess.run(
        ["git", "commit", "-q", "-m", "seed"],
        cwd=str(path),
        check=True,
        capture_output=True,
        env=env,
    )
    return path


FIXTURES = {"epic-snapshot": _fixture}

ENVS = [
    ("snapshot", {"CLAUDE_PROJECT_DIR": "{FIXTURE:epic-snapshot}"}, {}),
    # A FROZEN clone of this checkout rather than the live one: the real branch and the real `agent/pr/<branch>.md` the clone carries, with no other session able to rewrite either between the differential's two sides. See block_merge_with_unpushed.py:31.
    ("this-worktree", {"CLAUDE_PROJECT_DIR": "{FIXTURE:this-worktree-snapshot}"}, {}),
]

EDGE_CASES = [
    ("no trailer at all", 'git commit -m "feat(x): a change"'),
    ("a real trailer", 'git commit -m "feat(x): a change\n\nPR-TASK: a1b2c3d4"'),
    ("an escaped-newline trailer", 'git commit -m "feat(x): a change\\n\\nPR-TASK: a1b2c3d4"'),
    # The 2026-08-27 typo finding: one character off, and the commit LOOKS tagged.
    ("an id naming no epic", 'git commit -m "feat(x): a\n\nPR-TASK: f2757831"'),
    # The `-F` shapes the same finding widened.
    (
        "-F - with a heredoc is readable",
        "git commit -F - <<'EOF'\nfeat(x): a\n\nPR-TASK: a1b2c3d4\nEOF",
    ),
    ("-F - on a pipe is not readable, so allowed", "cat msg.txt | git commit -F -"),
    ("-F on a file that does not exist", "git commit -F /nonexistent-msg.txt"),
    # Prose about committing is not a commit.
    ("prose naming the trailer", "echo 'add a PR-TASK: a1b2c3d4 trailer'"),
    ("git log is not git commit", "git log --grep='^PR-TASK: a1b2c3d4'"),
    # A foreign checkout's commits are not this repo's epics' business.
    ("a commit in another tree", 'cd /tmp && git commit -m "x"'),
    ("git -C into another tree", 'git -C /tmp commit -m "x"'),
    # The tab defect inherited from shellscan.target_root, pinned here so a future "fix" to that module is a visible divergence rather than a quiet one.
    ("git -C with a TAB resolves to the empty root", 'git -C\t/tmp commit -m "x"'),
]


def _grep_qx(needle, haystack):
    """`grep -qx -- "$FOUND" <<<"$KNOWN"` -- a whole-RECORD match.

    `-x` and not `-Fx`: the needle is a PATTERN, and every value that reaches here is hex, so no metacharacter can appear. Reproduced as a pattern anyway rather than as equality, because equality would be a different check that happens to agree today.
    """
    pattern = re.compile(needle)
    records, _ = hookio._records(hookio._here_string(haystack))
    return any(pattern.fullmatch(record) for record in records)


def _epic_menu(ev, known, snap, branch_key, branch):
    if known:
        ev.warn("")
        ev.warn("Epics declared for this branch (agent/pr/%s.md):" % branch_key)
        for record in known.split("\n"):
            if record == "":
                continue
            title = ""
            try:
                text = pathlib.Path(snap).read_text(encoding="utf-8", errors="replace")
            except OSError:
                text = ""
            # `grep -B4 -F "PR-TASK: $id" | grep -E '^### ' | tail -1 | sed 's/^### //'`
            lines = text.split("\n")
            heads = []
            for i, line in enumerate(lines):
                if ("PR-TASK: " + record) in line:
                    heads.extend(h for h in lines[max(0, i - 4) : i + 1] if h.startswith("### "))
            if heads:
                title = heads[-1][len("### ") :]
            ev.warn("    %s  %s" % (record, title or "(untitled)"))
    else:
        ev.warn("")
        ev.warn("No snapshot at agent/pr/%s.md, so there is no epic to name yet:" % branch_key)
        ev.warn('    .claude/hooks/stop/worklist.py --epic <me> new "<title>"')
        ev.warn("    .claude/hooks/stop/worklist.py --publish <me> %s" % (branch or "<branch>"))


def run(ev):
    state = shellscan.hook_init(ev.payload)
    if state is None:
        return hookio.ALLOW
    cmd, scan = state

    # Is this a commit at all? Command position, so prose about committing is not.
    if not hookio.grep_q(COMMIT_AT_COMMAND_POS, scan):
        return hookio.ALLOW

    # `${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null)}`:
    # the substitution runs only when the variable is unset OR empty.
    root = ev.env("CLAUDE_PROJECT_DIR") or hookio.git_out(["rev-parse", "--show-toplevel"])

    # THIS REPO IS NOT THE ONLY ONE ON THE MACHINE. A command that `cd`s into an independent sibling checkout (e.g. private/growth, private/generative -- real repos with their own origin, not a console submodule) and commits there was still judged against CLAUDE_PROJECT_DIR/agent/pr/<console-branch>.md: wrong branch name (this repo's HEAD, not the target's), wrong epic snapshot
    # (one that cannot possibly name an epic for a repo it has never heard of), so every such commit was refused for a trailer no epic file could ever supply. Detect a `cd`/`git -C` into another repo anywhere on the line -- a cd applies to every later segment, so this is deliberately line-wide, matching hook_target_repo's convention in lib/command-scan.sh -- and if the git root
    # THAT resolves to is a real repo distinct from this one, this guard has nothing to check: that repo's commits are not this repo's epics' business. THE RESOLUTION MOVED TO lib/command-scan.sh when a third guard needed it. Two siblings had the same defect -- block-unverified-push.sh refused a foreign repo's push against THIS tree's gate stamp (reproduced live), and
    # warn-remote-drift.sh has the same shape latently -- so the walk this file pioneered is now shared rather than copied twice more.
    if shellscan.target_root(scan, root) != "":
        return hookio.ALLOW

    # THE TOOL CALL'S OWN `cwd` IS A SECOND, MORE RELIABLE SIGNAL than the text-parsed `cd`/`-C` hint above -- reproduced live 2026-09-23: a session ran `git commit` with the Bash tool's `cwd` field pointed at an independent local clone (`/home/developer/console-ci-fix-scratch`, cloned to keep a risky change out of this shared tree), with no `cd`/`-C` anywhere in the command text
    # itself, so `target_root` found no hint at all and this guard judged the commit against THIS repo's stale index and its `agent/pr/<this-branch>.md` epic snapshot -- the exact wrong-tree failure the comment above already fixed for the text-hint case, reachable from a second direction the fix never covered. `ev.field("cwd") or root` is the same fallback
    # `block_unproven_bulk_transform.py:262` already uses for this exact field.
    _cwd = ev.field("cwd")
    if _cwd and _cwd != root:
        _cwd_root = hookio.git_out(["-C", _cwd, "rev-parse", "--show-toplevel"], want_rc=True)
        if _cwd_root is not None and _cwd_root.strip() not in ("", root):
            return hookio.ALLOW

    # ---- what message text can we actually see? ---------------------------- Everything readable is concatenated; the trailer only has to appear once.
    msg = ""

    # 1. -m / --message: the raw command carries it.
    if hookio.grep_q(HAS_MESSAGE_FLAG, cmd):
        msg = cmd

    # 2. -F - with a heredoc: the body is in the command string. `scan_target` STRIPS heredocs (they are data, for its purposes), so this reads $CMD. The `<<` is required, not incidental: `-F -` ALONE means the message arrives on a pipe this hook cannot see, and treating the command text as the message then reads a trailer-less command line as a trailer-less COMMIT. Measured: `cat
    # msg.txt | git commit -F -` was refused for a message it never saw.
    if hookio.grep_q(HAS_FILE_DASH, cmd) and hookio.grep_q("<<", cmd, fixed=True):
        msg = msg + "\n" + cmd

    # 3. -F <file> / --file=<file>: read it off disk.
    for match in hookio.grep_o(FILE_ARGS, cmd):
        name = hookio.sed_sub(hookio.rx(r"^(-F|--file)([{S}]+|=)"), "", match).rstrip("\n")
        if name in {"", "-"}:
            continue
        for cand in (name, "%s/%s" % (root, name)):
            path = pathlib.Path(cand)
            if path.is_file():
                try:
                    body = path.read_text(encoding="utf-8", errors="surrogateescape")
                except OSError:
                    body = ""
                # `MSG="$MSG\n$(cat "$cand")"` -- a command substitution, so the
                # file's own trailing newlines are dropped before it is joined.
                msg = msg + "\n" + hookio._command_substitution(body)
                break

    # Nothing readable -- a piped stdin or a command substitution. Allow, as the header says: this hook catches the common case cheaply; CI is the enforcement.
    # `${MSG//[[:space:]]/}` deletes every whitespace character, so a message of
    # only blanks counts as nothing readable.
    if re.sub(r"[ \t\n\v\f\r]", "", msg) == "":
        return hookio.ALLOW

    # ---- the epics that actually exist ------------------------------------- `rev-parse --abbrev-ref HEAD` PRINTS THE STRING "HEAD" WHEN DETACHED, and a detached HEAD is not exotic: it is every pull_request checkout and every halted rebase. The snapshot path then became agent/pr/HEAD.md, which does not exist, so KNOWN was empty and a TYPO'D id -- the case this guard was extended
    # for -- sailed through. Measured 2026-08-27: the suite case asserting the typo
    # is refused returned 0 in CI while passing on every developer machine.
    #
    # `git branch --show-current` prints EMPTY when detached rather than lying, and the CI environment names the branch outright. Same resolution order as scripts/gates/check-pr-task-trailers.ts, so the gate and the guard agree about which branch they are judging.
    cwd = root or "."
    branch = (
        ev.env("PR_HEAD_REF")
        or ev.env("GITHUB_HEAD_REF")
        or hookio.git_out(["-C", cwd, "branch", "--show-current"])
    )
    # A HALTED REBASE IS THE DETACHED CASE THAT ACTUALLY MATTERS HERE. This repo has a rebase executor, so committing mid-rebase is a normal thing to do, and that is exactly when losing id validation would hurt. git remembers the branch it is rebasing in rebase-merge/head-name (rebase-apply/head-name for the am backend), so ask instead of guessing.
    if branch == "":
        for name in ("rebase-merge/head-name", "rebase-apply/head-name"):
            head_path = hookio.git_out(["-C", cwd, "rev-parse", "--git-path", name])
            if head_path and pathlib.Path(head_path).is_file():
                try:
                    text = pathlib.Path(head_path).read_text(encoding="utf-8", errors="replace")
                except OSError:
                    text = ""
                branch = hookio._command_substitution(hookio.sed_sub(r"^refs/heads/", "", text))
                break
    # Still empty means a plain detached checkout, where there genuinely IS no branch and therefore no published epic set. The guard allows, as it does whenever it has nothing to judge against.
    branch_key = branch.replace("/", "-")
    snap = "%s/agent/pr/%s.md" % (root, branch_key)
    known = ""
    snap_path = pathlib.Path(snap)
    if snap_path.is_file():
        try:
            text = snap_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            text = ""
        ids = []
        for record in hookio.grep_lines(SNAPSHOT_ID, text):
            ids.extend(hookio.grep_o(r"[0-9a-f]{6,32}", record))
        known = hookio._command_substitution(hookio._grep_out(ids))

    match = TRAILER.search(msg)
    found = match.group(1) if match else ""

    if found == "":
        ev.warn_raw(MISSING_TRAILER)
        _epic_menu(ev, known, snap, branch_key, branch)
        return hookio.DENY

    # A trailer whose id names no epic is WORSE than no trailer: it looks tagged. Only judge when a snapshot exists -- with none, there is no set to judge against, and refusing would block the very first commit of a new branch.
    if known and not _grep_qx(found, known):
        ev.warn_raw(
            "BLOCKED: PR-TASK id '%s' names no epic on this branch.\n"
            "\n"
            "This is worse than a missing trailer, which is why it is refused. The commit\n"
            "LOOKS tagged, so nothing downstream complains: `git log --grep` finds no epic\n"
            "by that id, the per-epic review never selects the commit, and the gap is\n"
            "reported by nobody. A single mistyped character does it.\n" % found
        )
        _epic_menu(ev, known, snap, branch_key, branch)
        return hookio.DENY
    return hookio.ALLOW
