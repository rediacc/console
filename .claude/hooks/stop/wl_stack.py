"""The stacked development branch (PLAN-two-track-merge-dev LT19): where the development tree's branch stands against the landing branch.

Operator ruling ASKED:2026-11-20T18:46Z: the development branch is STACKED on the landing branch (the landing tip plus development commits), so `git rebase <landing branch>` brings landing's fixes in at once, and commits flow one way, landing into development. After the landing PR rebase-merges, promotion (`./run.sh worktree landing --promote`) rebases the development branch onto origin/main, where landing's copies read absorbed, moves it into the landing tree and rewrites the landing record.

`stack_state(root)` answers one of:

  none     no valid landing record, `root` is the landing tree itself, or the development tree holds no branch of its own (detached, `main`, or the record's branch).
  current  the landing tip is an ancestor of the development branch.
  behind   the landing branch holds commits the development branch lacks: report `git rebase <landing branch>`.
  merged   the landing branch is on origin/main (every commit of it patch-equivalent to one there, or, when it holds none of its own, its PR reads MERGED), and the record still names it: promotion has not run. BLOCKS at every effort level once the merged PR's release is green (`released`); while the release is still in flight or red it is reported, not blocked on (agent/plans/PLAN-simple-two-tree-loop.md D3: promote's premise is a fully green release, and the development tree never waits on landing).

A promoted tree is quiet by construction: promotion rewrites the record to the branch it moved into landing, so the merged branch is no longer the one judged.

The landing tip is the LOCAL branch, which every tree of the repository shares. A development branch rebased onto a landing commit that is not pushed yet is no hazard for the landing push: block_landing_one_way admits a pushed commit the landing branch's reflog shows was made there.

`stack_block` and `stack_report` never raise, and a reader failure never blocks, because a git blip must not block a stop. It is not silent either: a failed read (a git command, gh, a defective landing record) raises StackReadError inside `stack_state`, and `stack_verdict` and `stack_report` answer it as a `landing-stack` advisory naming the failure, since an unread state is unknown, not "none". The merged block is the `landing-stack` key (blocks from effort low, advises at quiet); the behind report is advisory (`landing-behind`).

THE BLOCK ASKS WHETHER PROMOTE WOULD PROCEED (agent/plans/PLAN-stop-hook-retro-20261123.md friction 1, D1 and D2). Blocking a stop on a promotion that refuses for a reason the session cannot act on cost 70 stop turns in one window. `stack_verdict` returns `(block, advisory)`, at most one non-empty, while the merged branch's release is green:

  code-complete  a plan a `Plan-Box:` trailer of the development commits names still holds an open `[writer]` box: promote refuses at its step 5, so the merged state is an advisory naming the plan and its first open box. `open_writer_boxes` is the ONE reader: landing_promote._code_complete raises on its answer, so the hook and the verb cannot disagree.
  live run       a live background task of this session runs in the main checkout (`main_checkout_tasks`), which promote rebases: an advisory naming the tasks (the loop-next rule: a background task of this session downgrades it).
  dirty tree     promote's tracked non-record dirt (landing_promote._dirty, through `_promote_dirt`, which never raises) in the main checkout, the landing tree or a landing submodule tree: when no dirty path is this session's own edit (`own_paths`, the `uc_files` union wl_uncommitted keeps), an advisory naming them; otherwise the block stands and names this session's own dirty paths, since committing them is a real action.

A named plan that cannot be read keeps the block and names the reason: promote refuses on it too, and it is the session's to fix. So does any other failed read under the merged state (the open-box read, the development-commit listing, promote's dirty preflight): the block stands and names what could not be read.
"""

from __future__ import annotations

import dataclasses
import importlib.util
import os
import pathlib
import subprocess

GIT_TIMEOUT_S = 60
REMOTE = "origin"
PROMOTE_COMMAND = "./run.sh worktree landing --promote"

NONE = "none"
CURRENT = "current"
BEHIND = "behind"
MERGED = "merged"

BLOCK_KEY = "landing-stack"
REPORT_KEY = "landing-behind"
# How many dirty paths or tasks one line names before it counts the rest.
SHOWN = 5


class OpenBoxesError(RuntimeError):
    """A commit message or a plan a `Plan-Box:` trailer names cannot be read: `open_writer_boxes` cannot answer."""


class StackReadError(RuntimeError):
    """A git, gh or landing-record read `stack_state` rests on failed: the stack's state is unknown, which is not `none`."""


class Verdict(tuple):
    """`(block, advisory)` of `stack_verdict`: at most one of the two is non-empty."""

    __slots__ = ()

    def __new__(cls, block: str = "", advisory: str = ""):
        return super().__new__(cls, (block, advisory))

    @property
    def block(self) -> str:
        return self[0]

    @property
    def advisory(self) -> str:
        return self[1]


@dataclasses.dataclass(frozen=True)
class StackState:
    state: str
    landing: str = ""
    landing_path: str = ""
    development: str = ""
    ahead: int = 0
    carried: int = 0
    rebased: bool = False
    how: str = ""
    command: str = ""


def _hooks_pkg():
    """commit_policy from `.claude/rediacc_hooks`, through the canonical sys.path hop loaded by file (this module lives outside that package)."""
    helper = pathlib.Path(__file__).resolve().parents[2] / "rediacc_hooks" / "syspath.py"
    spec = importlib.util.spec_from_file_location("_rediacc_syspath", helper)
    if spec is None or spec.loader is None:
        raise ImportError("cannot load %s" % helper)
    syspath = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(syspath)
    syspath.on_sys_path(syspath.CLAUDE_DIR)
    from rediacc_hooks import commit_policy

    return commit_policy


def _git_full(cwd, *args) -> tuple[int, str, str]:
    """`(rc, stdout, stderr)` of `git -C <cwd> <args>`; rc 1 with the exception text as stderr when git cannot run."""
    try:
        r = subprocess.run(
            ["git", "-C", str(cwd), *args],
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT_S,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return 1, "", "%s: %s" % (type(exc).__name__, exc)
    return r.returncode, r.stdout.strip(), r.stderr.strip()


def _git(cwd, *args) -> tuple[int, str]:
    rc, out, _err = _git_full(cwd, *args)
    return rc, out


def _resolves(root, ref: str) -> bool:
    return _git(root, "rev-parse", "--verify", "--quiet", ref + "^{commit}")[0] == 0


def _cherry(root, upstream: str, head: str) -> list[str] | None:
    """`git cherry <upstream> <head>` marks, one `+` or `-` per commit of `head` not in `upstream`; None when git fails."""
    rc, out = _git(root, "cherry", upstream, head)
    if rc != 0:
        return None
    return [line[:1] for line in out.splitlines() if line[:1] in "+-"]


def gh_pr_merged(root, branch: str) -> bool:
    """Whether a MERGED PR is headed by `branch`, read through wl_gh. Raises StackReadError when gh cannot say: an unanswered question is not "no merged PR"."""
    try:
        import wl_gh

        rows, err = wl_gh.call(
            [
                "pr",
                "list",
                "--head",
                branch,
                "--state",
                "merged",
                "--json",
                "number",
                "--limit",
                "1",
            ],
            cwd=str(root),
        )
    except Exception as exc:
        raise StackReadError(
            "gh could not say whether a merged PR is headed by %s (%s: %s)"
            % (branch, type(exc).__name__, exc)
        ) from exc
    if rows is None:
        raise StackReadError(
            "gh could not say whether a merged PR is headed by %s (%s)"
            % (branch, err or "no answer")
        )
    return bool(rows)


def _fetch(root, branch: str) -> None:
    _git(
        root,
        "fetch",
        "--quiet",
        "--no-tags",
        REMOTE,
        "+refs/heads/%s:refs/remotes/%s/%s" % (branch, REMOTE, branch),
    )


def _landing_merged(root, landing: str, main_ref: str, pr_merged) -> str:
    """How the landing branch reads merged ("" when it does not): every commit absorbed on main, or none of its own and a MERGED PR."""
    marks = _cherry(root, main_ref, "refs/heads/" + landing)
    if marks is None:
        raise StackReadError(
            "git could not compare the landing branch %s with %s (`git cherry` failed)"
            % (landing, main_ref.removeprefix("refs/remotes/"))
        )
    if "+" in marks:
        return ""
    if marks:
        return "its %d commit(s) are absorbed on %s" % (
            len(marks),
            main_ref.removeprefix("refs/remotes/"),
        )
    if pr_merged(root, landing):
        return "its PR is merged"
    return ""


def stack_state(root, fetch: bool = True, pr_merged=gh_pr_merged) -> StackState:
    """Where the development tree at `root` stands against the landing branch. `fetch` refreshes origin/main first (best effort); `pr_merged(root, branch)` answers the PR question for a landing branch with no commits of its own. Raises StackReadError when a read it rests on fails (a defective landing record, a failed `git cherry`, gh that cannot say)."""
    cp = _hooks_pkg()
    record, problem = cp.read_landing_record(str(root))
    if problem:
        raise StackReadError(problem)
    if record is None or cp.tree_role(str(root)) == cp.ROLE_LANDING:
        return StackState(NONE)
    landing = record["branch"]
    development = cp.current_branch(str(root), foreign=True)
    if not development or development in ("main", landing):
        return StackState(NONE, landing=landing, landing_path=record["path"])
    base = {"landing": landing, "landing_path": record["path"], "development": development}
    if not _resolves(root, "refs/heads/" + landing):
        return StackState(NONE, **base)
    if fetch:
        _fetch(root, "main")
    main_ref = "refs/remotes/%s/main" % REMOTE
    if _resolves(root, main_ref):
        how = _landing_merged(root, landing, main_ref, pr_merged)
        if how:
            marks = _cherry(root, main_ref, "refs/heads/" + development) or []
            rebased = (
                _git(root, "merge-base", "--is-ancestor", main_ref, "refs/heads/" + development)[0]
                == 0
            )
            return StackState(
                MERGED,
                carried=marks.count("-"),
                rebased=rebased,
                how=how,
                command=PROMOTE_COMMAND,
                **base,
            )
    rc, _ = _git(
        root, "merge-base", "--is-ancestor", "refs/heads/" + landing, "refs/heads/" + development
    )
    if rc == 0:
        return StackState(CURRENT, **base)
    rc, count = _git(root, "rev-list", "--count", "%s..%s" % (development, "refs/heads/" + landing))
    ahead = int(count) if rc == 0 and count.isdigit() else 0
    return StackState(BEHIND, ahead=ahead, command="git rebase %s" % landing, **base)


def _merged_text(st: StackState) -> str:
    if st.carried:
        why = "still carries %d landing commit(s) main absorbed" % st.carried
    elif not st.rebased:
        why = "is not rebased onto %s/main" % REMOTE
    else:
        why = (
            "is rebased onto %s/main, and the rest of promotion (the branch moved into landing, the record rewritten, the draft flipped ready) has not run"
            % REMOTE
        )
    return (
        "LANDING MERGED (blocks from effort low; an advisory at quiet): the landing branch %s is on %s/main (%s), "
        "and this tree's development branch %s %s. Promotion runs here before anything else:\n"
        "  %s\n"
        "A development branch built on a merged landing branch would carry the merged PR's commits a second time.\n"
        "(.claude/hooks/stop/wl_stack.py, PLAN-two-track-merge-dev LT19; operator ruling ASKED:2026-11-20T18:46Z)"
        % (st.landing, REMOTE, st.how, st.development, why, st.command)
    )


def _behind_text(st: StackState) -> str:
    return (
        "LANDING AHEAD: the landing branch %s (tree %s) holds %d commit(s) the development branch %s lacks. "
        "The development branch is stacked on it; take them in this tree:\n"
        "  %s\n"
        "(.claude/hooks/stop/wl_stack.py, PLAN-two-track-merge-dev LT19)"
        % (st.landing, st.landing_path, st.ahead, st.development, st.command)
    )


def _release_pending_text(st: StackState) -> str:
    return (
        "LANDING MERGED, RELEASE PENDING: the landing branch %s is on %s/main (%s), and the release at the "
        "merged sha is not green yet. Keep building; promotion (%s) runs once Console CI on main and the "
        "edge deploy are both SUCCESS, and this stop blocks on it then.\n"
        "(.claude/hooks/stop/wl_stack.py, agent/plans/PLAN-simple-two-tree-loop.md D3)"
        % (st.landing, REMOTE, st.how, st.command)
    )


def open_writer_boxes(root, shas) -> list[tuple[str, list[str]]]:
    """`[(plan rel, [open [writer] box body, ...])]` for each plan a `Plan-Box:` trailer of the commits `shas` names that still holds an open `[writer]` box, in first-named order; [] when every named plan is code-complete. Messages and plans are read in `root` (the main checkout, which holds the development branch). Raises OpenBoxesError when a message or a named plan cannot be read. The ONE reader landing_promote._code_complete and `stack_verdict` share."""
    import wl_boxready
    import wl_planbox
    import wl_planrec

    plans: list[str] = []
    for sha in shas:
        rc, message = _git(root, "show", "-s", "--format=%B", sha)
        if rc != 0:
            raise OpenBoxesError("git could not read the message of %s" % str(sha)[:12])
        for box in wl_planbox.parse_plan_box(message).boxes:
            if box.plan not in plans:
                plans.append(box.plan)
    found_open: list[tuple[str, list[str]]] = []
    for plan in plans:
        try:
            found = wl_planbox.resolve_plan(str(root), plan)
        except wl_planbox.PlanBoxError as exc:
            raise OpenBoxesError(str(exc)) from exc
        if found is None:
            raise OpenBoxesError(
                "the development commits name %s, which the main checkout does not hold" % plan
            )
        rel, text = found
        bodies = [
            body
            for _i, raw, body, _sig in wl_planrec.open_boxes(text)
            if wl_boxready.writer_tagged(raw)
        ]
        if bodies:
            found_open.append((rel, bodies))
    return found_open


def _dev_shas(root, main_ref: str, development: str) -> list[str] | None:
    """The development commits with no patch-equivalent on `main_ref`, oldest first; None when git fails."""
    rc, out = _git(root, "cherry", main_ref, "refs/heads/" + development)
    if rc != 0:
        return None
    return [line.split()[1] for line in out.splitlines() if line.startswith("+ ")]


def _promote_dirt(root, landing_path: str) -> tuple[list[str], str]:
    """`(paths, problem)`: the absolute paths promote's dirty preflight refuses on (landing_promote._dirty: tracked, non-record, not machine-local) in the main checkout, the landing tree and each landing submodule tree with "", or `([], why)` when they cannot be read. Never raises."""
    try:
        hop = pathlib.Path(__file__).resolve().parents[2] / "rediacc_hooks" / "syspath.py"
        spec = importlib.util.spec_from_file_location("_rediacc_syspath", hop)
        if spec is None or spec.loader is None:
            return [], "cannot load %s" % hop
        syspath = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(syspath)
        lp = syspath.import_from_ci("rediacc_ci.dev.landing_promote")
        main = pathlib.Path(_development_path(root) or root)
        trees = [main]
        if landing_path:
            landing = pathlib.Path(landing_path)
            trees.append(landing)
            trees.extend(sub for _p, sub in sorted(lp._submodule_trees(landing).items()))
        rows: list[str] = []
        for tree in trees:
            rows.extend(str(tree / lp._porcelain_path(line)) for line in lp._dirty(tree))
        return rows, ""
    except Exception as exc:
        return [], "%s: %s" % (type(exc).__name__, exc)


def _norm(path) -> str:
    return os.path.normpath(str(pathlib.Path(path).resolve()))


def _abs_set(root, paths) -> set[str]:
    """`paths` (repo-relative to `root`, or absolute) as normalized absolute strings."""
    out = set()
    for p in paths or ():
        path = pathlib.Path(p)
        out.add(_norm(path if path.is_absolute() else pathlib.Path(root) / path))
    return out


def _named(items) -> str:
    items = list(items)
    shown = ", ".join(items[:SHOWN])
    return shown + (" (+%d more)" % (len(items) - SHOWN) if len(items) > SHOWN else "")


def main_checkout_tasks(root, live_bg, metas) -> list[str]:
    """The descriptions of this session's live background tasks that run in the main checkout; [] when `root` (the session's own tree) is not the main checkout. A shell task runs in the session's tree; a subagent does when its meta (`metas`, wl_roster.load_metas) records no tree of its own. A teammate or a workflow, whose tree the event does not say, is not counted, so an unknown keeps the block.

    Raises StackReadError when git cannot list the trees of a repository: "not the main checkout" and "could not tell" are different answers, and the stop names the second beside the landing-stack text (wl_checks, `landing-stack-tasks`)."""
    main = _development_path(root)
    if not main or os.path.realpath(str(root)) != os.path.realpath(main):
        return []
    out = []
    for b in live_bg or ():
        kind = b.get("type")
        tid = str(b.get("id") or "")
        meta = (metas or {}).get(tid)
        main_tree_agent = meta is not None and not meta.get("worktree")
        if kind == "shell" or (kind == "subagent" and main_tree_agent):
            out.append(str(b.get("description") or b.get("command") or tid or "?")[:80])
    return out


def _unread_text(exc: BaseException) -> str:
    return (
        "LANDING STACK UNREAD: where the development branch stands against the landing branch could not be read "
        "(%s: %s), so whether promotion is due is unknown. The stop does not block on an unread state; the next "
        "stop reads it again.\n"
        "(.claude/hooks/stop/wl_stack.py, PLAN-two-track-merge-dev LT19)"
        % (type(exc).__name__, exc)
    )


def _code_complete_text(st: StackState, plans) -> str:
    rel, bodies = plans[0]
    more = (
        " (and %d more plan(s) with an open [writer] box)" % (len(plans) - 1)
        if len(plans) > 1
        else ""
    )
    return (
        "LANDING MERGED, PROMOTION WAITS ON CODE-COMPLETE: `%s` has %d open [writer] box(es), first: %s%s. "
        "The landing branch %s is on %s/main (%s), and promote refuses until every [writer] box of the plans "
        "the development commits name is ticked; then promote at a commit boundary:\n"
        "  %s\n"
        "(.claude/hooks/stop/wl_stack.py, agent/plans/PLAN-stop-hook-retro-20261123.md D1)"
        % (rel, len(bodies), bodies[0][:120], more, st.landing, REMOTE, st.how, st.command)
    )


def _live_run_text(st: StackState, tasks, dirt) -> str:
    also = " Promote's dirty preflight also names: %s." % _named(dirt) if dirt else ""
    return (
        "LANDING MERGED, PROMOTION WAITS ON A LIVE RUN: this session's background task(s) %s run in the main "
        "checkout, which promote rebases.%s Once they finish, promote:\n"
        "  %s\n"
        "(.claude/hooks/stop/wl_stack.py, agent/plans/PLAN-stop-hook-retro-20261123.md D2)"
        % (_named(tasks), also, st.command)
    )


def _peer_dirt_text(st: StackState, dirt) -> str:
    return (
        "LANDING MERGED, PROMOTION WAITS ON A PEER'S DIRTY TREE: promote refuses on tracked non-record changes, "
        "and none of them is this session's edit: %s. Once their owner commits them, promote:\n"
        "  %s\n"
        "(.claude/hooks/stop/wl_stack.py, agent/plans/PLAN-stop-hook-retro-20261123.md D2)"
        % (_named(dirt), st.command)
    )


def stack_verdict(root, released=True, own_paths=None, live_main_bg=None, **kw) -> Verdict:
    """`(block, advisory)` while the landing branch is merged, its release is green (`released`, the development tree's `wl_prscope.LoopState.landing_released`) and promotion has not run; an advisory naming the failure when the stack cannot be read (StackReadError or any other raise of `stack_state`); `("", "")` otherwise. `own_paths` is this session's edited-file union (repo-relative to `root`, or absolute); `live_main_bg` is this session's live background tasks in the main checkout (`main_checkout_tasks`'s list, or a bool). Never raises."""
    if not released:
        return Verdict()
    try:
        st = stack_state(root, **kw)
    except Exception as exc:
        return Verdict(advisory=_unread_text(exc))
    if st.state != MERGED:
        return Verdict()
    notes = []
    shas = _dev_shas(root, "refs/remotes/%s/main" % REMOTE, st.development)
    if shas is None:
        notes.append(
            "git could not list the development commits ahead of %s/main, so whether promote refuses on an open [writer] box is unknown."
            % REMOTE
        )
    if shas:
        try:
            plans = open_writer_boxes(root, shas)
        except OpenBoxesError as exc:
            plans = []
            notes.append("Promote also refuses here: %s." % exc)
        except Exception as exc:
            plans = []
            notes.append(
                "The open [writer] box read failed (%s: %s), so whether promote would proceed is unknown."
                % (type(exc).__name__, exc)
            )
        if plans:
            return Verdict(advisory=_code_complete_text(st, plans))
    dirt, dirt_problem = _promote_dirt(root, st.landing_path)
    if dirt_problem:
        notes.append(
            "Promote's dirty preflight could not be read (%s), so whether it refuses on a dirty tree is unknown."
            % dirt_problem
        )
    if live_main_bg:
        tasks = live_main_bg if isinstance(live_main_bg, (list, tuple)) else ["a live task"]
        return Verdict(advisory=_live_run_text(st, [str(t) for t in tasks], dirt))
    if dirt:
        own = _abs_set(root, own_paths)
        mine = [p for p in dirt if _norm(p) in own]
        if not mine:
            return Verdict(advisory=_peer_dirt_text(st, dirt))
        notes.append(
            "Promote refuses first on this session's own dirty tracked path(s); commit them: %s."
            % _named(mine)
        )
    text = _merged_text(st)
    if notes:
        text = "%s\n%s" % (text, "\n".join(notes))
    return Verdict(block=text)


def stack_block(root, released=True, own_paths=None, live_main_bg=None, **kw) -> str:
    """The stop text of `stack_verdict`: "" when nothing is merged, or when promote waits on something the session cannot act on (an open [writer] box, a peer's dirt, a live main-checkout run). Never raises."""
    return stack_verdict(
        root, released=released, own_paths=own_paths, live_main_bg=live_main_bg, **kw
    ).block


def stack_report(root, released=True, **kw) -> str:
    """The advisory text while the landing branch is ahead of the development branch, or merged while its release is not green yet (`released` False), or the stack cannot be read (naming the failure), else "". Never raises."""
    try:
        st = stack_state(root, **kw)
    except Exception as exc:
        return _unread_text(exc)
    if st.state == MERGED and not released:
        return _release_pending_text(st)
    return _behind_text(st) if st.state == BEHIND else ""


def _development_path(root) -> str:
    """The main checkout, the development tree: the first entry of `git worktree list --porcelain`, "" when git says `root` is in no repository (an answer: no checkout). Raises StackReadError when git fails any other way or lists no tree, so a caller never mistakes an unread answer for a tree."""
    rc, out, err = _git_full(root, "worktree", "list", "--porcelain")
    if rc != 0 and "not a git repository" in err:
        return ""
    if rc != 0:
        raise StackReadError(
            "git could not list the trees of %s (git worktree list exited %d: %s)"
            % (root, rc, (err.splitlines() or ["no stderr"])[0][:160])
        )
    for line in out.splitlines():
        if line.startswith("worktree "):
            return line[len("worktree ") :]
    raise StackReadError("git listed no tree for %s" % root)


def _record(root) -> tuple[dict | None, str]:
    """`(record, problem)`: the validated landing record, or None with "" when there is none, or None with the reason it binds nothing (a defective record, or commit_policy that cannot be loaded)."""
    try:
        cp = _hooks_pkg()
    except (ImportError, OSError, SyntaxError) as exc:
        return None, "commit_policy, the landing record's reader, could not be loaded (%s: %s)" % (
            type(exc).__name__,
            exc,
        )
    record, problem = cp.read_landing_record(str(root))
    return record, ("the landing record binds nothing: %s" % problem if problem else "")


def notify_problem(root) -> str:
    """Why notify_line has no message for a reason other than "there is no record": the record's defect or the unloadable reader, "" when the record reads (or is simply absent). A caller that gets an empty message asks this and names the answer, so a failed read is never latched as a sent message (agent/plans/PLAN-silent-failure-sweep.md D6)."""
    return _record(root)[1]


def notify_line(root, event: str, pr: int | None = None, sha: str = "") -> str:
    """The cross-session message the landing session sends the development session, "" with no valid record or an unknown event. An empty message with a record that fails to read is not "nothing to send": notify_problem names it.

    WHEN. `push`: after each `git push` of the landing branch from the landing tree exits 0 (the post-bash side). `merged`: once `gh pr merge` of the landing PR reads MERGED (/pr-merge, after the merge is confirmed). `cd-done`: once the release at the merged sha (`sha`) is fully green, Console CI on main and the edge deploy both SUCCESS (agent/plans/PLAN-simple-two-tree-loop.md D1 L-RELEASE to L-IDLE): the landing stop names it once per merged sha, and promote is the development session's next step once every plan on its branch is code-complete (D3). The sending itself is the landing session's SendMessage; this is the text.
    """
    record, _problem = _record(root)
    if record is None:
        return ""
    landing = record["branch"]
    try:
        where = _development_path(root)
    except StackReadError as exc:
        where = "the main checkout (%s)" % exc
    if event == "push":
        rc, sha = _git(root, "rev-parse", "--short", "refs/heads/" + landing)
        tip = sha if rc == 0 and sha else "its new tip"
        return (
            "LANDING PUSH: the landing branch %s is pushed at %s. In the development tree (%s), take it now:\n"
            "  git rebase %s" % (landing, tip, where, landing)
        )
    if event == "merged":
        number = "PR #%d" % pr if pr else "its PR"
        return (
            "LANDING MERGED: the landing branch %s (%s) rebase-merged into main. In the development tree (%s), "
            "promotion runs before anything else (its Stop hook blocks until it does):\n"
            "  %s" % (landing, number, where, PROMOTE_COMMAND)
        )
    if event == "cd-done":
        number = "PR #%d" % pr if pr else "its PR"
        at = " at %s" % sha[:12] if sha else ""
        return (
            "CD DONE: the landing branch %s (%s) is merged and its release%s is green (Console CI on main "
            "and CD - Release to Edge). In the development tree (%s), once every [writer] box of the plans "
            "on its branch is ticked, promote at a commit boundary:\n"
            "  %s" % (landing, number, at, where, PROMOTE_COMMAND)
        )
    return ""
