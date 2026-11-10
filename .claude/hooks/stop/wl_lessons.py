"""wl_lessons: lesson pointers, and the sweep that takes an enforced lesson out of rotation.

agent/plans/PLAN-experience-feedback.md, parts P2 and P7. A lesson lives in one of four stores: a TRAPS.md entry, a HINTS.md entry, a hint proposal (agent/ledgers/hint-proposals.jsonl), or a memory note outside the repo. Once something mechanical enforces it (a guard, a gate, a test, a trapguard rule, a tool fix), repeating it in rotation costs attention and buys nothing.

POINTERS. One grammar, `<kind>:<token>`, for `worklist.py --hint-resolve` and for an `Enforced-By:` line:

  trap    a `Trap-Id:` in docs/agent-reference/TRAPS.md (wl_planrec.resolve)
  guard   .claude/rediacc_hooks/guards/<token>.py exists
  gate    a key in package.json `scripts` (wl_planrec.resolve)
  hook    a trapguard rule: `def rule_<token>(` in .claude/hooks/trapguard/dispatch.py
  test    a repo-relative test file, optionally `<path>::<name>` with `def <name>` in it
  commit  a commit reachable from HEAD or origin/main (wl_planrec.resolve)

`pointer_problem` is a LOCAL existence check. The exported resolver `trap_registry.pointer_problem` (PLAN-experience-feedback.md D3) replaces it in C7b; until then this module asks the same questions of the tree directly, so a dead pointer never counts as an enforcer.
"""

from __future__ import annotations

import pathlib
import re

import wl_planrec as PR

POINTER_KINDS = ("trap", "guard", "gate", "hook", "test", "commit")
GUARDS_REL = ".claude/rediacc_hooks/guards"
TRAPGUARD_REL = ".claude/hooks/trapguard/dispatch.py"
_NAME_RE = re.compile(r"^[A-Za-z0-9_.:-]+$")


def parse_pointer(text):
    """(kind, token) for `<kind>:<token>`, or (None, text) when the kind is not one of POINTER_KINDS."""
    kind, sep, token = (text or "").strip().partition(":")
    kind = kind.strip()
    if not sep or kind not in POINTER_KINDS or not token.strip():
        return None, (text or "").strip()
    return kind, token.strip()


def _read(path):
    try:
        return pathlib.Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _inside(root, rel):
    """The repo path for `rel`, or None when it escapes the root or is absolute."""
    if not rel or rel.startswith("/") or ".." in pathlib.PurePosixPath(rel).parts:
        return None
    return pathlib.Path(root) / rel


def pointer_problem(root, pointer):
    """None when `pointer` names something that exists in this tree; else one line saying why not."""
    kind, token = parse_pointer(pointer)
    if kind is None:
        return "%r is not <kind>:<token> with kind one of %s" % (token, ", ".join(POINTER_KINDS))
    if kind in ("trap", "gate", "commit"):
        try:
            ok, detail = PR.resolve(root, kind, token)
        except Exception as exc:  # a resolver failure is a dead pointer, never a crash
            return "%s:%s could not be resolved (%s)" % (kind, token, exc)
        return None if ok else "%s:%s does not resolve -- %s" % (kind, token, detail)
    if kind == "guard":
        if not _NAME_RE.match(token) or "/" in token:
            return "guard:%s is not a guard module name" % token
        stem = token.removesuffix(".py")
        path = pathlib.Path(root) / GUARDS_REL / ("%s.py" % stem)
        return None if path.is_file() else "guard:%s has no %s/%s.py" % (token, GUARDS_REL, stem)
    if kind == "hook":
        fn = "rule_%s" % token.replace("-", "_")
        if re.search(
            r"^def %s\(" % re.escape(fn), _read(pathlib.Path(root) / TRAPGUARD_REL), re.MULTILINE
        ):
            return None
        return "hook:%s has no `def %s(` in %s" % (token, fn, TRAPGUARD_REL)
    # test
    rel, _sep, name = token.partition("::")
    path = _inside(root, rel)
    if path is None or not path.is_file():
        return "test:%s names no file in this tree" % token
    if name and not re.search(r"^\s*def %s\(" % re.escape(name), _read(path), re.MULTILINE):
        return "test:%s has no `def %s(` in %s" % (token, name, rel)
    return None
