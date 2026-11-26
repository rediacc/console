#!/usr/bin/env python3
"""PostToolUse/Bash: start a detached haiku review for every new commit, and tell the session about each review that finished (agent/plans/PLAN-per-commit-review.md section 3.1; operator ruling 2026-10-02).

FOUR JOBS, ALL CHEAP.

1. TRIGGER. When the command ran `git commit`, `rebase`, `cherry-pick`, `merge`, `revert`, `pull` or `am` at a command position (the shell lexer's own reading, so an `echo` or a commit message quoting the words is not a commit), each repository those invocations ran in is asked `wl_review.uncovered()`: the branch's commits with no review record and no live reviewer. Up to `max_spawn_per_trigger` of them get a
   reviewer started with `wl_review.spawn_detached`, which takes the per-sha lock and detaches the child from this hook's pipes. The hook does not read `tool_response` (it carries no exit code): a failed commit made no new sha, so nothing is uncovered and nothing starts.

2. SURFACE. On EVERY Bash call, the review records (ledger lines and `.md` files) that finished since this session last heard of them are reported as `additionalContext`. With the Stop hook disabled (operator, 2026-10-02) this is the channel that brings a review back to the session that made the commit, one tool call after it lands; SessionStart and the push guard are the other two.

3. COMMIT LANDED. When the command ran a `git commit` that left HEAD where the session's previous Bash call recorded it with paths still staged, the commit is reported as not landed (a filtered output hides a refusal); every Bash call then records each repository's HEAD for the next call's comparison.

4. LANDED FIXES. When the command ran a `git commit`, `cherry-pick` or `am` outside a lease, every `Fixes-Review: <finding id>` trailer of the commits it added marks that finding `fixed <commit>` through the `--review-mark` verb (PLAN-drain-throughput.md DT10); inside a lease the trailers are only named back to the writer.

Advisory: always exits 0, never blocks the tool call that already ran, and does nothing at all inside a reviewer or a Stop-hook child (`COMMIT_REVIEW_CHILD`, `STOPHOOK_CHILD`).
"""

import contextlib
import importlib.util
import json
import os
import pathlib
import re
import sys
import time

HOOKS = pathlib.Path(__file__).resolve().parents[1]


def _load_syspath():
    """The canonical `.claude` hop, rediacc_hooks/syspath.py, loaded BY PATH: this hook runs as a script, so `rediacc_hooks` is not importable by name until the hop has run."""
    hop_file = HOOKS.parent / "rediacc_hooks" / "syspath.py"
    spec = importlib.util.spec_from_file_location("rediacc_hooks_syspath", hop_file)
    if spec is None or spec.loader is None:
        raise ImportError("no loadable %s" % hop_file)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_SYSPATH = _load_syspath()
_SYSPATH.on_sys_path(_SYSPATH.CLAUDE_DIR)
_SYSPATH.on_sys_path(_SYSPATH.STOP_DIR)

R = importlib.import_module("wl_review")
hookio = importlib.import_module("rediacc_hooks.hookio")
shellscan = importlib.import_module("rediacc_hooks.shellscan")
commit_policy = importlib.import_module("rediacc_hooks.commit_policy")


def _bound_paths(root):
    """`commit_policy.bound_trees` as paths: `root`, plus the other tree the landing record binds (box LT11; with no valid record, `[root]` alone)."""
    return [pathlib.Path(t) for t in commit_policy.bound_trees(str(root))]


def commit_repos(cmd, cwd, root):
    """The top levels of every repository a history-writing git invocation in `cmd` ran in, limited to this project and the repositories inside it (its submodules). Empty when there is none.

    A commit in a scratch repository under /tmp is not this branch's work, and reviewing it would file a record into this project's `agent/reviews/` about a commit no push of it ever carries.
    """
    base = pathlib.Path(cwd or root)
    repos = []
    trees = _bound_paths(root)
    for run in shellscan._analyse(cmd).runs:
        if run.git_sub not in R.TRIGGER_SUBS:
            continue
        where = base if run.git_dir in (None, "", ".") else base / run.git_dir
        top = R.git_out(where, "rev-parse", "--show-toplevel")
        # AN UNRESOLVABLE `-C` IS NOT "NO REPOSITORY" (#51e1c0cf). `git -C <dir>/$r commit` in a loop names a directory the lexer cannot expand, so rev-parse fails; skipping it left account 654d186 unreviewed until the push guard refused the push. Every project repository is checked instead: uncovered() is cheap, and a covered repository starts nothing.
        candidates = (
            [top] if top else ([r for t in trees for r in _project_repos(t)] if run.git_dir else [])
        )
        for cand in candidates:
            # MEMBERSHIP IS `.gitmodules`, NOT LOCATION (operator 2026-10-08). private/growth is a separate, gitignored repository inside the tree; reviewing its commits filed the operator's private documents into this project's agent/reviews/.
            inside = bool(cand) and commit_policy.owning_tree(cand, trees) is not None
            if inside and cand not in repos:
                repos.append(cand)
    return repos


def _project_repos(root):
    """The project and its registered submodules, as top-level paths."""
    return [str(pathlib.Path(root)), *commit_policy.submodule_paths(str(root))]


def trigger_lines(cmd, cwd, root, trigger=R.trigger):
    lines = []
    for repo in commit_repos(cmd, cwd, root):
        tree = commit_policy.owning_tree(repo, _bound_paths(root)) or root
        try:
            pending = R.operation_pending(tree, pathlib.Path(repo))
        except Exception as exc:
            # One repository's failed read must not drop the review line of every other repository.
            lines.append(
                "per-commit review NOT started in %s (%s: %s)"
                % (repo, type(exc).__name__, str(exc)[:160])
            )
            continue
        if pending:
            # Said, never silent: the reviews are deferred, not skipped, and a reader of this line must not take it for "covered".
            lines.append(
                "per-commit review deferred in %s: a %s is in progress in %s, and a review record written now is an unstaged tracked change `git rebase --continue` refuses over. The replayed commits are reviewed after it ends."
                % (R.repo_label(tree, repo), pending[1], pending[0])
            )
            continue
        try:
            started = trigger(tree, pathlib.Path(repo))
        except Exception as exc:
            lines.append(
                "per-commit review NOT started in %s (%s: %s)"
                % (repo, type(exc).__name__, str(exc)[:160])
            )
            continue
        if not started:
            # trigger() started nothing: every in-scope commit is covered or has a live reviewer, the command made no commit (a failed or empty commit), the repository has no branch, or a miss (#52978244). The HEAD is named so the next miss can be diagnosed from this result: it is the commit made only when the command made one.
            head = R.git_out(pathlib.Path(repo), "rev-parse", "--short", "HEAD") or "?"
            lines.append(
                "per-commit review: none due for %s, HEAD %s (covered, no new commit, or a miss: run wl_review.py --check)"
                % (R.repo_label(tree, repo), head)
            )
        for sha, pid in started:
            lines.append(
                "per-commit review started for %s %s (pid %s): its record lands in about a minute, in agent/reviews/%s/clean.jsonl or as %s.md"
                % (
                    R.repo_label(tree, repo),
                    sha[:8],
                    pid,
                    R.branch_slug(R.current_branch(repo)),
                    sha,
                )
            )
    return lines


# ---- 3. A COMMIT THAT DID NOT LAND (agent/plans/PLAN-stop-hook-retro-20261125.md R20261125.4) --------------------
#
# A `git commit ... 2>&1 | grep '^\['` hides a commit-policy refusal (its lines start `commit-policy:`) and leaves the index staged; on 2026-11-25 that cost 14 minutes and a failed cherry-pick. This hook cannot read the exit code, so it compares HEAD with the HEAD it recorded after the PREVIOUS Bash call of this session (every Bash call passes through here, so that record is the HEAD this command started from). HEAD unmoved and paths still staged is a commit that did not land. No record yet (the session's first call) says nothing, and so does a commit whose own message subject (`-m`, or a readable `-F` file) is HEAD's subject while HEAD is at most SUBJECT_WITNESS_SEC seconds old: that one landed, whatever the record says, which covers a parallel Bash call that recorded the new HEAD first. An older HEAD with the same subject (a repeated `wip`) is no witness, and neither is a HEAD dated in the future (a negative age is not "at most" SUBJECT_WITNESS_SEC). A `--dry-run` commit never intends to land and is skipped.


# A parallel call's commit is seconds old; a HEAD older than this that merely shares the subject does not witness a landing.
SUBJECT_WITNESS_SEC = 120


def _head_record(session, repo):
    """The file holding the HEAD this session last saw in `repo`."""
    import hashlib

    key = hashlib.sha1(str(pathlib.Path(repo).resolve()).encode("utf-8")).hexdigest()[:16]
    d = R.state_dir() / "heads"
    d.mkdir(parents=True, exist_ok=True)
    return d / ("%s-%s" % (str(session or "nosession")[:8], key))


def record_heads(root, session, cwd=None):
    """Write each project repository's HEAD for this session, the `before` of the next Bash call, and the HEAD of the lease tree `cwd` sits in (a writer's project directory is the main checkout, so its lease is no bound tree)."""
    lease = commit_policy.lease_root(str(cwd)) if cwd else ""
    for tree in [*_bound_paths(root), *([pathlib.Path(lease)] if lease else [])]:
        for repo in _project_repos(tree):
            head = R.git_out(pathlib.Path(repo), "rev-parse", "HEAD")
            if head:
                with contextlib.suppress(OSError):
                    _head_record(session, repo).write_text(head + "\n", encoding="utf-8")


def _message_subject(run, base):
    """The subject line a `git commit` run names (`-m`, `--message`, `-F`, `--file`), or "" when it names none or the file cannot be read."""
    argv = list(run.argv or [])
    for i, word in enumerate(argv):
        msg = path = None
        if word in ("-m", "--message") and i + 1 < len(argv):
            msg = argv[i + 1]
        elif word.startswith("--message="):
            msg = word.split("=", 1)[1]
        elif word.startswith("-m") and len(word) > 2 and not word.startswith("--"):
            msg = word[2:]
        elif word in ("-F", "--file") and i + 1 < len(argv):
            path = argv[i + 1]
        elif word.startswith("--file="):
            path = word.split("=", 1)[1]
        if path and path != "-":
            p = pathlib.Path(path)
            if not p.is_absolute():
                p = pathlib.Path(run.cwd or base) / p
            try:
                msg = p.read_text(encoding="utf-8", errors="replace")
            except OSError:
                msg = None
        if msg is not None:
            return next((ln.strip() for ln in msg.splitlines() if ln.strip()), "")
    return ""


def commit_landed_lines(cmd, cwd, root, session):
    """The `COMMIT DID NOT LAND` notice for each repository where a command-position `git commit` left HEAD where it was with paths still staged."""
    base = pathlib.Path(cwd or root)
    trees = _bound_paths(root)
    lines = []
    seen = set()
    for run in shellscan._analyse(cmd).runs:
        if run.git_sub != "commit" or "--dry-run" in (run.argv or []):
            continue
        where = base if run.git_dir in (None, "", ".") else base / run.git_dir
        top = R.git_out(where, "rev-parse", "--show-toplevel")
        if not top or top in seen or commit_policy.owning_tree(top, trees) is None:
            continue
        seen.add(top)
        try:
            before = _head_record(session, top).read_text(encoding="utf-8").strip()
        except OSError:
            continue
        repo = pathlib.Path(top)
        after = R.git_out(repo, "rev-parse", "HEAD")
        if not after or after != before:
            continue
        staged = [p for p in R.git_out(repo, "diff", "--cached", "--name-only").splitlines() if p]
        if not staged:
            continue
        subject = _message_subject(run, base)
        if subject and subject == R.git_out(repo, "log", "-1", "--format=%s", "HEAD").strip():
            stamp = R.git_out(repo, "log", "-1", "--format=%ct", "HEAD").strip()
            if stamp.isdigit() and 0 <= time.time() - int(stamp) <= SUBJECT_WITNESS_SEC:
                continue
        lines.append(
            "COMMIT DID NOT LAND in %s: HEAD is still %s and %d path(s) are staged; rerun the commit without the output filter to read the refusal (a commit-policy refusal starts `commit-policy:`, which a filter for git's `[branch sha]` line drops)"
            % (top, after[:10], len(staged))
        )
    return lines


# ---- 4. A LANDED FIX MARKS ITS FINDINGS (agent/plans/PLAN-drain-throughput.md DT10) ------------------------------
#
# A writer fixes a per-commit review finding in its lease and names it with a `Fixes-Review: <finding id>` trailer. `./run.sh worktree land <id> --run --me <prefix>` marks those, but the lead usually runs the printed `git cherry-pick -x` lines itself, and 186 landed fixes stayed unmarked on 1121-1 (2026-11-26). So after a command-position `git commit`, `cherry-pick` or `am` outside a lease, each commit between the HEAD recorded after the session's previous Bash call and the new HEAD (a fast-forward only, at most FIXES_SCAN_MAX commits) is read for those trailers, and each finding still open is marked `fixed <that commit>` through the `--review-mark` verb itself, so its descent and file checks hold. A refusal is printed with its reason and the manual command. Inside a lease nothing is marked (the sha is not the landed one): the trailers are named back to the writer for its report. A trailer only ever claims `fixed`; a `not-a-bug` verdict stays a human or lead decision.

FIXES_SUBS = frozenset({"commit", "cherry-pick", "am"})
FIXES_REVIEW_RE = re.compile(r"^Fixes-Review:\s*(\S+)\s*$", re.MULTILINE)
# A landing batch is a handful of picks; a longer range after one command is a pull or a reset, not a landing.
FIXES_SCAN_MAX = 50


def _fixes_tops(cmd, base, root):
    """The top levels of the repositories a `commit`, `cherry-pick` or `am` in `cmd` ran in: this project, its submodules, or a lease tree (named back to its writer, never marked)."""
    trees = _bound_paths(root)
    tops = []
    for run in shellscan._analyse(cmd).runs:
        if run.git_sub not in FIXES_SUBS:
            continue
        where = base if run.git_dir in (None, "", ".") else base / run.git_dir
        top = R.git_out(where, "rev-parse", "--show-toplevel")
        inside = top and (
            commit_policy.owning_tree(top, trees) is not None or commit_policy.lease_root(top)
        )
        if inside and top not in tops:
            tops.append(top)
    return tops


def _new_commits(repo, before, after):
    """The commits `before..after`, oldest first, when `after` fast-forwards `before` by at most FIXES_SCAN_MAX; else []."""
    if not before or not after or before == after:
        return []
    if R.git(repo, "merge-base", "--is-ancestor", before, after)[0] != 0:
        return []
    shas = R.git_out(repo, "rev-list", "--reverse", "%s..%s" % (before, after)).split()
    return shas if len(shas) <= FIXES_SCAN_MAX else []


def _finding_open(review_root, branch, finding_id):
    """True when `finding_id` is an open finding of `branch`'s records, False when it is closed, None when no single record holds it."""
    try:
        _path, _review, finding = R.find_finding(review_root, branch, finding_id)
    except ValueError:
        return None
    return finding.resolution_kind() == "open"


def fixes_review_lines(cmd, cwd, root, session, verb=None):
    """One line per `Fixes-Review:` trailer of a commit the command landed: marked, already closed, refused, or (in a lease) named for the writer's report."""
    verb = verb or R.verb
    base = pathlib.Path(cwd or root)
    me = str(session or "")[:8]
    lines = []
    for top in _fixes_tops(cmd, base, root):
        repo = pathlib.Path(top)
        try:
            before = _head_record(session, top).read_text(encoding="utf-8").strip()
        except OSError:
            continue
        after = R.git_out(repo, "rev-parse", "HEAD")
        lease = commit_policy.lease_root(top)
        review_root = R.review_root(root)
        branch = R.current_branch(review_root)
        for sha in _new_commits(repo, before, after):
            body = R.git_out(repo, "log", "-1", "--format=%B", sha)
            for fid in dict.fromkeys(FIXES_REVIEW_RE.findall(body)):
                if lease:
                    lines.append(
                        "Fixes-Review %s in lease commit %s: name it fixed by %s in the report; the lead's landing pick marks it (never --review-mark from a lease)"
                        % (fid, sha[:10], sha[:10])
                    )
                    continue
                state = _finding_open(review_root, branch, fid) if branch else None
                if state is False:
                    lines.append(
                        "Fixes-Review %s (%s): already closed, left as it is" % (fid, sha[:10])
                    )
                    continue
                rc, text = verb("--review-mark", me, [fid, "fixed", sha], review_root, dict)
                if rc == 0:
                    lines.append("Fixes-Review %s marked fixed %s: %s" % (fid, sha[:10], text))
                else:
                    lines.append(
                        "Fixes-Review %s NOT marked by %s (%s); close it by hand: worklist.py --review-mark %s %s fixed <sha> or not-a-bug <evidence>"
                        % (fid, sha[:10], text.strip()[:200], me, fid)
                    )
    return lines


def main():
    if os.environ.get("COMMIT_REVIEW_CHILD") or os.environ.get("STOPHOOK_CHILD"):
        return 0
    ev = hookio.Event(sys.stdin.read())
    root = R.git_out(pathlib.Path(ev.project_dir).resolve(), "rev-parse", "--show-toplevel")
    if not root:
        return 0
    root = pathlib.Path(root)
    cmd = ev.field("tool_input", "command")
    lines = []
    session = ev.field("session_id")
    if cmd and "git" in cmd and "commit" in cmd:
        try:
            lines += commit_landed_lines(cmd, ev.field("cwd") or None, root, session)
        except Exception as exc:
            lines.append(
                "commit-landed check failed (%s: %s)" % (type(exc).__name__, str(exc)[:160])
            )
    if cmd and "git" in cmd and any(sub in cmd for sub in FIXES_SUBS):
        try:
            lines += fixes_review_lines(cmd, ev.field("cwd") or None, root, session)
        except Exception as exc:
            lines.append(
                "Fixes-Review marking failed (%s: %s)" % (type(exc).__name__, str(exc)[:160])
            )
    if cmd and "git" in cmd and any(sub in cmd for sub in R.TRIGGER_SUBS):
        try:
            lines += trigger_lines(cmd, ev.field("cwd") or None, root)
        except Exception as exc:
            lines.append(
                "per-commit review trigger failed (%s: %s)" % (type(exc).__name__, str(exc)[:160])
            )
    try:
        record_heads(root, session, ev.field("cwd") or None)
    except Exception as exc:
        lines.append("HEAD record failed (%s: %s)" % (type(exc).__name__, str(exc)[:160]))
    try:
        for tree in _bound_paths(root):
            lines += R.surface_new(tree, R.current_branch(tree), ev.field("session_id"))
    except Exception as exc:
        lines.append(
            "per-commit review surfacing failed (%s: %s)" % (type(exc).__name__, str(exc)[:160])
        )
    if lines:
        sys.stdout.write(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "PostToolUse",
                        "additionalContext": "\n".join(lines),
                    }
                }
            )
            + "\n"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
