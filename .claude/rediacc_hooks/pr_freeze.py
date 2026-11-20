"""The PR freeze (PLAN-two-track-merge-dev D1, box F1): while a branch is in its babysit or merge phase, only fix work lands on it.

The freeze binds to the BRANCH, not the session, because a git hook has no session id: it is active when the newest unexpired `babysit|merge` phase event of any owner names the branch being committed to. A commit is admitted when one of these holds:

  1. its Conventional Commits type is fix, style or test;
  2. it is chore(reviews), chore(state), chore(plan) or chore(plans);
  3. every staged path is a record path (.ci/policy/record-paths.json);
  4. it carries `focus-fix:#<id>` naming an item that is open (or leased), owned by the phase owner, and whose text carries the phase's `pr:<n>`;
  5. the staged diff is gitlinks only, and every commit in each bumped range passes rule 1, 2 or 4.

`verdict` is the pure core both hooks call (git/githooks.py commit-msg, and the pre-bash guard block_pr_freeze_commit); the loaders read the phase, the open items, the record globs and the gitlink ranges. A loader that cannot read its source fails open with a note: a store that will not parse must not stop every commit. The one escape is ending the phase: `worklist.py --phase <me> build`.
"""

from __future__ import annotations

import importlib
import json
import pathlib
import re
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
STOP_DIR = HERE.parent / "hooks" / "stop"

CC_RE = re.compile(r"^(?P<type>[a-z]+)(?:\((?P<scope>[^)]*)\))?!?:\s")
ADMIT_TYPES = frozenset({"fix", "style", "test"})
ADMIT_CHORE_SCOPES = frozenset({"reviews", "state", "plan", "plans"})
FOCUS_FIX_RE = re.compile(r"\bfocus-fix:#?([0-9a-f]{6,})\b")
ESCAPE = "worklist.py --phase <me> build"


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


def _focus_fix_ok(msg: str, phase: dict, open_items: dict, owned) -> tuple[bool, str]:
    """Rule 4: `focus-fix:#<id>` naming an open or leased item of the phase owner that carries the phase's pr:<n>."""
    m = FOCUS_FIX_RE.search(msg or "")
    if not m:
        return False, ""
    rec = (open_items or {}).get(m.group(1))
    if rec is None:
        return False, "focus-fix:#%s names no open item" % m.group(1)
    if rec.get("state") not in (" ", ">"):
        return False, "focus-fix:#%s is not open" % m.group(1)
    if not owned(rec.get("owner"), phase.get("o")):
        return False, "focus-fix:#%s belongs to another session" % m.group(1)
    pr = phase.get("pr")
    token = "pr:%s" % pr if pr not in (None, "", 0) else ""
    if not token or not re.search(
        r"(?<![\w:])%s(?!\d)" % re.escape(token), str(rec.get("text") or "")
    ):
        return False, "focus-fix:#%s does not carry %s" % (
            m.group(1),
            token or "the phase's pr:<n>",
        )
    return True, ""


def verdict(
    msg: str,
    staged_paths: list[str],
    gitlink_ranges: dict[str, list[str] | None] | None,
    phase: dict | None,
    open_items: dict | None,
    record_res: list | None = None,
    owned=lambda owner, phase_owner: bool(owner) and str(owner)[:8] == str(phase_owner or "")[:8],
) -> tuple[bool, str]:
    """(ok, reason) for one commit. `phase` is the active, unexpired phase for this branch, or None (no freeze). `gitlink_ranges` maps each staged gitlink to the subjects of the commits its bump brings in. `record_res` are compiled record-path globs."""
    if phase is None:
        return True, ""
    subject = (msg or "").strip().split("\n", 1)[0]
    if subject_admitted(subject):
        return True, ""
    paths = list(staged_paths or [])
    if paths and record_res and all(any(r.match(p) for r in record_res) for p in paths):
        return True, ""
    ok, why_fix = _focus_fix_ok(msg, phase, open_items or {}, owned)
    if ok:
        return True, ""
    ranges = gitlink_ranges or {}
    if paths and ranges and set(paths) <= set(ranges):
        unreadable = sorted(path for path, subjects in ranges.items() if subjects is None)
        if unreadable:
            return False, (
                "the gitlink bump of %s cannot be judged: its submodule range is unreadable (check the submodule out, or end the phase with `%s`)"
                % (", ".join(unreadable), ESCAPE)
            )
        bad = [
            "%s: %s" % (path, s)
            for path, subjects in sorted(ranges.items())
            for s in subjects or []
            if not subject_admitted(s) and not _focus_fix_ok(s, phase, open_items or {}, owned)[0]
        ]
        if not bad:
            return True, ""
        return False, (
            "the gitlink bump brings in commits that are not fix work: %s" % "; ".join(bad[:5])
        )
    return False, (
        "branch %s is frozen in its %s phase for PR #%s: only fix work lands. Admitted: a fix/style/test commit; "
        "chore(reviews|state|plan|plans); a commit of record paths only; focus-fix:#<id> for an open item of the phase owner carrying pr:%s; "
        "a gitlink bump whose range is all of these.%s The phase ends with `%s`."
        % (
            phase.get("branch") or "?",
            phase.get("mode") or "babysit",
            phase.get("pr") or "?",
            phase.get("pr") or "<n>",
            " (%s.)" % why_fix if why_fix else "",
            ESCAPE,
        )
    )


# --------------------------------------------------------------------------- loaders


def _stop_modules():
    """wl_core, wl_standdown and wl_store from the Stop-hook directory, imported on first use (a commit with no phase pays nothing for them)."""
    added = str(STOP_DIR) not in sys.path
    if added:
        sys.path.insert(0, str(STOP_DIR))
    try:
        return tuple(
            importlib.import_module(name)
            for name in ("wl_core", "wl_standdown", "wl_store", "wl_review")
        )[:3]
    finally:
        if added:
            sys.path.remove(
                str(STOP_DIR)
            )  # imported once; the path is not left behind for the caller (review a29977aa.3)


def active_phase(root, branch: str) -> dict | None:
    """The newest unexpired babysit|merge phase event of any owner that names `branch`, or None."""
    if not branch:
        return None
    core, standdown, store = _stop_modules()
    worklist = core.worklist_for(str(root))
    fold = store.phase_fold(worklist, root)
    best = None
    for ev in (fold.phase or {}).values():
        if not isinstance(ev, dict) or (ev.get("branch") or ev.get("br")) != branch:
            continue
        if best is None or (str(ev.get("at") or ""), int(ev.get("ns") or 0)) >= (
            str(best.get("at") or ""),
            int(best.get("ns") or 0),
        ):
            best = ev
    if best is None or best.get("mode") not in standdown.PHASE_MODES or standdown.expired(best):
        return None
    return best


def open_items(root) -> dict:
    """{id: record} for every item of the store (the full fold, paid only when a commit names focus-fix)."""
    core, _standdown, store = _stop_modules()
    return dict(store.load(core.worklist_for(str(root)), sync=False).by_id)


def record_res(root) -> list:
    """The record-path globs of .ci/policy/record-paths.json, compiled in wl_review's dialect, minus each row's `except` globs."""
    _stop_modules()
    wl_review = sys.modules["wl_review"]

    doc = json.loads(
        (pathlib.Path(root) / ".ci" / "policy" / "record-paths.json").read_text(encoding="utf-8")
    )
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
    """{path: [subject...]} for each staged path that is a gitlink: the commits between HEAD's pointer and the staged one. None when the range cannot be read (the submodule is not checked out, a pointer is missing): unreadable is never read as empty (review a29977aa.1)."""
    out: dict[str, list[str] | None] = {}
    for path in paths:
        staged = _git(repo, "ls-files", "-s", "--", path).split()
        if len(staged) < 2 or staged[0] != "160000":
            continue
        new = staged[1]
        old = _git(repo, "rev-parse", "--verify", "--quiet", "HEAD:%s" % path)
        rng = "%s..%s" % (old, new) if old else new
        rc, text = _git_rc(pathlib.Path(repo) / path, "log", "--format=%s", rng)
        out[path] = [s for s in text.splitlines() if s] if rc == 0 else None
    return out


def _git_rc(cwd, *args) -> tuple[int, str]:
    try:
        r = subprocess.run(
            ["git", "-C", str(cwd), *args], capture_output=True, text=True, timeout=30, check=False
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
    """The whole decision for one commit in `repo` on `branch`: loads what the verdict needs and fails open, with the reason, on a loader error."""
    try:
        phase = active_phase(root, branch)
        if phase is None:
            return True, ""
        core, _standdown, _store = _stop_modules()
        items = (
            open_items(root)
            if FOCUS_FIX_RE.search(msg or "")
            or any(
                FOCUS_FIX_RE.search(s)
                for subjects in gitlink_ranges(repo, paths).values()
                for s in subjects
            )
            else {}
        )
        return verdict(
            msg,
            paths,
            gitlink_ranges(repo, paths),
            phase,
            items,
            record_res(root),
            owned=core.owned_by_me,
        )
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
