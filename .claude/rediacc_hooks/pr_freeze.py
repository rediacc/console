"""The PR freeze (PLAN-simple-two-tree-loop B1, after PLAN-two-track-merge-dev F1): the landing tree takes fix work only while its PR is open.

The freeze binds to the TREE ROLE, not to a session or a phase, because a git hook has no session id and the tree a session runs in is its job: it is active when the role `commit_policy.tree_binding` gives the committing repository (the `tree_role` reading) is landing (a submodule tree inside the landing tree included) and the landing record's branch has an open PR. The development tree is never frozen. A commit in the frozen tree is admitted when one of these holds:

  1. its Conventional Commits type is fix, style or test;
  2. it is chore(reviews), chore(state), chore(plan) or chore(plans);
  3. every staged path is a record path (.ci/policy/record-paths.json);
  4. it carries `focus-fix:#<id>` naming an item that is open (or leased), of any session, whose text carries the landing PR's `pr:<n>`;
  5. the staged diff is gitlinks only, and every commit in each bumped range passes rule 1, 2 or 4;
  6. the staged diff is gitlinks only, and every bumped gitlink points at an ancestor of that submodule's origin/main: the merge pointer bump (`chore(submodules)`), whose commits main already holds. The subject is not read for this rule; the ancestry is the whole claim.

`verdict` is the pure core both hooks call (git/githooks.py commit-msg, and the pre-bash guard block_pr_freeze_commit); the loaders read the role, the open PR, the open items, the record globs, the gitlink ranges and their ancestry. The PR is read last, through `gh pr list`, and only for a commit rules 1, 2, 3, 5 and 6 did not already admit, so a fix commit costs no network call. A PR read that fails is UNKNOWN and refuses the commit with the reason: the landing tree takes fix work only, and an unchecked PR state is never read as "no PR". A store or policy loader that cannot read its source fails open with a note: a store that will not parse must not stop every commit. Feature work belongs in the development tree; the freeze lifts when the PR merges, and promote (`./run.sh worktree landing --promote`) opens the next one.
"""

from __future__ import annotations

import importlib
import importlib.util
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent


def _load_by_path(name: str, filename: str):
    """A sibling module loaded BY PATH: git/githooks.py loads this module by path too, as `pr_freeze`, so `from rediacc_hooks import ...` would not resolve there."""
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    if spec is None or spec.loader is None:
        raise ImportError("%s is missing" % (HERE / filename))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


syspath = _load_by_path("pr_freeze_syspath", "syspath.py")
STOP_DIR = syspath.STOP_DIR

CC_RE = re.compile(r"^(?P<type>[a-z]+)(?:\((?P<scope>[^)]*)\))?!?:\s")
ADMIT_TYPES = frozenset({"fix", "style", "test"})
ADMIT_CHORE_SCOPES = frozenset({"reviews", "state", "plan", "plans"})
FOCUS_FIX_RE = re.compile(r"\bfocus-fix:#?([0-9a-f]{6,})\b")
ESCAPE = (
    "commit feature work in the development tree; the freeze lifts when the PR merges, "
    "and `./run.sh worktree landing --promote` opens the next one"
)
GH_TIMEOUT_S = 20


def subject_admitted(subject: str) -> bool:
    """Rules 1 and 2: a fix, style or test commit, or chore(reviews|state|plan|plans)."""
    m = CC_RE.match(subject or "")
    if not m:
        return False
    kind, scope = m.group("type"), m.group("scope") or ""
    if kind in ADMIT_TYPES:
        return True
    return (
        kind == "chore"
        and bool(scope)
        and all(part.strip() in ADMIT_CHORE_SCOPES for part in scope.split(","))
    )


def _focus_fix_ok(msg: str, freeze: dict, open_items: dict) -> tuple[bool, str]:
    """Rule 4: `focus-fix:#<id>` naming an open or leased item, of any session, that carries the landing PR's pr:<n>."""
    m = FOCUS_FIX_RE.search(msg or "")
    if not m:
        return False, ""
    rec = (open_items or {}).get(m.group(1))
    if rec is None:
        return False, "focus-fix:#%s names no open item" % m.group(1)
    if rec.get("state") not in (" ", ">"):
        return False, "focus-fix:#%s is not open" % m.group(1)
    pr = freeze.get("pr")
    token = "pr:%s" % pr if pr not in (None, "", 0) else ""
    if not token or not re.search(
        r"(?<![\w:])%s(?!\d)" % re.escape(token), str(rec.get("text") or "")
    ):
        return False, "focus-fix:#%s does not carry %s" % (
            m.group(1),
            token or "the landing PR's pr:<n>",
        )
    return True, ""


def verdict(
    msg: str,
    staged_paths: list[str],
    gitlink_ranges: dict[str, list[str] | None] | None,
    freeze: dict | None,
    open_items: dict | None,
    record_res: list | None = None,
    on_main: dict[str, bool | None] | None = None,
) -> tuple[bool, str]:
    """(ok, reason) for one commit. `freeze` is `{"branch", "pr"}` for a commit in the landing tree while its PR is open, or None (no freeze); `pr` None judges without the PR (rule 4 cannot admit). `gitlink_ranges` maps each staged gitlink to the subjects of the commits its bump brings in; `on_main` maps it to whether the staged pointer is an ancestor of the submodule's origin/main (None: unreadable). `record_res` are compiled record-path globs."""
    if freeze is None:
        return True, ""
    subject = (msg or "").strip().split("\n", 1)[0]
    if subject_admitted(subject):
        return True, ""
    paths = list(staged_paths or [])
    if paths and record_res and all(any(r.match(p) for r in record_res) for p in paths):
        return True, ""
    ok, why_fix = _focus_fix_ok(msg, freeze, open_items or {})
    if ok:
        return True, ""
    ranges = gitlink_ranges or {}
    if paths and ranges and set(paths) <= set(ranges):
        anc = on_main or {}
        if all(anc.get(path) is True for path in paths):
            return True, ""
        unreadable = sorted(path for path, subjects in ranges.items() if subjects is None)
        if unreadable:
            return False, (
                "the gitlink bump of %s cannot be judged: its submodule range is unreadable and its pointer is not "
                "a readable ancestor of origin/main (check the submodule out and fetch it)"
                % ", ".join(unreadable)
            )
        bad = [
            "%s: %s" % (path, s)
            for path, subjects in sorted(ranges.items())
            for s in subjects or []
            if not subject_admitted(s) and not _focus_fix_ok(s, freeze, open_items or {})[0]
        ]
        if not bad:
            return True, ""
        return False, (
            "the gitlink bump brings in commits that are not fix work, and its pointer is not on the submodule's "
            "origin/main: %s" % "; ".join(bad[:5])
        )
    return False, (
        "the landing tree takes fix work only while PR #%s of %s is open. Admitted: a fix/style/test commit; "
        "chore(reviews|state|plan|plans); a commit of record paths only; focus-fix:#<id> for an open item carrying pr:%s; "
        "a gitlink bump whose range is all of these, or whose every pointer is an ancestor of the submodule's origin/main.%s "
        "Otherwise %s."
        % (
            freeze.get("pr") or "?",
            freeze.get("branch") or "?",
            freeze.get("pr") or "<n>",
            " (%s.)" % why_fix if why_fix else "",
            ESCAPE,
        )
    )


# --------------------------------------------------------------------------- loaders


def _stop_modules():
    """wl_core and wl_store from the Stop-hook directory (wl_review is imported beside them for `record_res`), imported on first use (a commit outside the landing tree pays nothing for them)."""
    added = syspath.on_sys_path(str(STOP_DIR))
    try:
        return tuple(
            importlib.import_module(name) for name in ("wl_core", "wl_store", "wl_review")
        )[:2]
    finally:
        if added and str(STOP_DIR) in sys.path:
            sys.path.remove(
                str(STOP_DIR)
            )  # imported once; the path is not left behind for the caller (review a29977aa.3)


def _worklist(core, root):
    """`core.worklist_for(root)` without its side effect: worklist_for creates `<tmp>/claude-worklist`, and a commit in a scratch repository (the hook suites run under a private TMPDIR) must not leave that directory behind. With no directory there is no legacy event log to read, so a path inside it that does not exist reads as empty. The temp dir is tempfile's, which is TMPDIR first, as worklist_for's is."""
    if (pathlib.Path(tempfile.gettempdir()) / "claude-worklist").is_dir():
        return core.worklist_for(str(root))
    return pathlib.Path(tempfile.gettempdir()) / "claude-worklist" / "absent.md"


_COMMIT_POLICY: list = []


def commit_policy():
    """commit_policy.py, loaded by path beside this module once per process (its imports are stdlib only)."""
    if not _COMMIT_POLICY:
        _COMMIT_POLICY.append(_load_by_path("pr_freeze_commit_policy", "commit_policy.py"))
    return _COMMIT_POLICY[0]


def landing_branch(repo) -> str:
    """The landing record's branch when `repo` sits in the landing tree (`commit_policy.tree_binding`: a submodule tree inside it included), "" in the development tree, in a lease, or with no valid record."""
    cp = commit_policy()
    record, role = cp.tree_binding(str(repo))
    if role != cp.ROLE_LANDING or not record:
        return ""
    return str(record.get("branch") or "")


def landing_tree(repo) -> str:
    """The landing tree's path from the record, for the PR read (the console's PR, also for a commit in a submodule inside the tree)."""
    record, _role = commit_policy().tree_binding(str(repo))
    return str((record or {}).get("path") or repo)


def open_pr(cwd, branch: str) -> tuple[int | None, str]:
    """(number, error): the open PR whose head is `branch` (the lowest number when several are), read with `gh pr list` in `cwd`; (None, "") when none is open, (None, <why>) when gh cannot answer. An answer that cannot be read is never "no PR"."""
    try:
        r = subprocess.run(
            [
                "gh",
                "pr",
                "list",
                "--head",
                branch,
                "--state",
                "open",
                "--json",
                "number",
                "--limit",
                "5",
            ],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=GH_TIMEOUT_S,
            check=False,
            env={k: v for k, v in os.environ.items() if k not in commit_policy().REPO_ENV},
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return None, "gh could not run (%s: %s)" % (type(exc).__name__, str(exc)[:120])
    if r.returncode != 0:
        return None, "gh pr list exited %d: %s" % (
            r.returncode,
            (r.stderr or r.stdout).strip()[:160],
        )
    try:
        rows = json.loads(r.stdout or "")
    except ValueError:
        return None, "gh pr list printed no JSON: %r" % (r.stdout or "")[:120]
    if not isinstance(rows, list):
        return None, "gh pr list printed %s, not a list" % type(rows).__name__
    numbers = [
        row.get("number")
        for row in rows
        if isinstance(row, dict) and isinstance(row.get("number"), int)
    ]
    if rows and not numbers:
        return None, "gh pr list rows carry no number: %r" % rows[:2]
    return (min(numbers) if numbers else None), ""


def open_items(root) -> dict:
    """{id: record} for every item of the store (the full fold, paid only when a commit names focus-fix)."""
    core, store = _stop_modules()
    return dict(store.load(_worklist(core, root), sync=False).by_id)


def record_res(root) -> list:
    """The record-path globs of .ci/policy/record-paths.json, compiled in wl_review's dialect, minus each row's `except` globs."""
    _stop_modules()
    wl_review = sys.modules["wl_review"]
    policy_path = syspath.import_from_ci("rediacc_ci.policy_paths").policy_path

    doc = json.loads(policy_path("record-paths.json", root).read_text(encoding="utf-8"))
    out = []
    for row in doc.get("records") or []:
        glob = row.get("glob")
        if not glob:
            continue
        inc = wl_review._glob_re(glob)
        exc = [wl_review._glob_re(e) for e in row.get("except") or []]
        out.append(_RecordRe(inc, exc))
    return out


class _RecordRe:
    def __init__(self, inc, exc):
        self.inc, self.exc = inc, exc

    def match(self, path):
        return bool(self.inc.match(path)) and not any(e.match(path) for e in self.exc)


def gitlink_ranges(repo, paths: list[str]) -> dict[str, list[str] | None]:
    """{path: [subject...]} for each staged path that is a gitlink: the commits between HEAD's pointer and the staged one; a gitlink new at this commit (no pointer in HEAD) is judged by the whole history of the staged commit. None when `git log` cannot read the range (the submodule is not checked out, the staged commit is absent): unreadable is never read as empty (review a29977aa.1)."""
    out: dict[str, list[str] | None] = {}
    for path in paths:
        staged = _git(repo, "ls-files", "-s", "--", path).split()
        if len(staged) < 2 or staged[0] != "160000":
            continue
        new = staged[1]
        old = _git(repo, "rev-parse", "--verify", "--quiet", "HEAD:%s" % path)
        rng = "%s..%s" % (old, new) if old else new
        # foreign: in a linked tree (the landing tree) the commit hook runs under GIT_DIR=<common>/worktrees/<name>, and a submodule read under it answered from the superproject, so every range read as unreadable.
        rc, text = _git_rc(pathlib.Path(repo) / path, "log", "--format=%s", rng, foreign=True)
        out[path] = [s for s in text.splitlines() if s] if rc == 0 else None
    return out


def gitlink_on_main(repo, paths: list[str]) -> dict[str, bool | None]:
    """{path: bool | None} for each staged gitlink: whether the staged pointer is an ancestor of that submodule's origin/main (rule 6, the merge pointer bump). None when git cannot say (the submodule is not checked out, the commit or origin/main is absent): unreadable is never read as on main."""
    out: dict[str, bool | None] = {}
    for path in paths:
        staged = _git(repo, "ls-files", "-s", "--", path).split()
        if len(staged) < 2 or staged[0] != "160000":
            continue
        rc, _text = _git_rc(
            pathlib.Path(repo) / path,
            "merge-base",
            "--is-ancestor",
            staged[1],
            "origin/main",
            foreign=True,
        )
        out[path] = True if rc == 0 else False if rc == 1 else None
    return out


def _git_rc(cwd, *args, foreign: bool = False) -> tuple[int, str]:
    """`foreign=True` drops the repository variables a commit hook runs under (commit_policy.REPO_ENV), for a question about another repository: a submodule's ancestry must not be answered from the superproject's GIT_DIR."""
    env = (
        {k: v for k, v in os.environ.items() if k not in commit_policy().REPO_ENV}
        if foreign
        else None
    )
    try:
        r = subprocess.run(
            ["git", "-C", str(cwd), *args],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
            env=env,
        )
    except (OSError, subprocess.SubprocessError):
        return 1, ""
    return r.returncode, r.stdout.strip()


def _git(cwd, *args) -> str:
    try:
        r = subprocess.run(
            ["git", "-C", str(cwd), *args], capture_output=True, text=True, timeout=30, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return r.stdout.strip() if r.returncode == 0 else ""


def check(repo, root, branch: str, msg: str, paths: list[str]) -> tuple[bool, str]:
    """The whole decision for one commit in `repo` (the store is `root`'s): no freeze outside the landing tree; inside it the cheap rules first, then the PR read, then the full verdict. `branch` is the committing tree's own branch and is not what freezes it: the landing record's branch and its open PR are. A store or policy loader error fails open, with the reason; a PR read that fails refuses."""
    del branch  # the role and the record decide; kept in the signature both hooks call
    try:
        landing = landing_branch(repo)
        if not landing:
            return True, ""
        ranges = gitlink_ranges(repo, paths)
        anc = gitlink_on_main(repo, paths)
        recs = record_res(root)
        # Judged first without the PR: every rule but 4 needs no network, so a fix commit, a record commit and a merge pointer bump cost no gh call.
        if verdict(msg, paths, ranges, {"branch": landing, "pr": None}, {}, recs, anc)[0]:
            return True, ""
        pr, err = open_pr(landing_tree(repo), landing)
        if err:
            return False, (
                "the landing tree takes fix work only while its PR is open, and whether %s has an open PR is unknown "
                "(%s), so this commit is not admitted unchecked. Retry once gh answers, or %s."
                % (landing, err, ESCAPE)
            )
        if pr is None:
            return True, ""
        # An unreadable range is None: verdict refuses it, so the focus-fix scan must not raise on it (a TypeError here failed the whole check open).
        items = (
            open_items(root)
            if FOCUS_FIX_RE.search(msg or "")
            or any(FOCUS_FIX_RE.search(s) for subjects in ranges.values() for s in subjects or [])
            else {}
        )
        return verdict(msg, paths, ranges, {"branch": landing, "pr": pr}, items, recs, anc)
    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
        AttributeError,
        ImportError,
        subprocess.SubprocessError,
    ) as exc:
        return True, "pr_freeze could not judge (%s: %s); the commit is not frozen" % (
            type(exc).__name__,
            str(exc)[:160],
        )
