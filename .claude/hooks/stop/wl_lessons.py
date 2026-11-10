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


# -- P7: Enforced-By, the rotation drop and the sweep -------------------------
#
# A lesson entry names what enforces it in an `Enforced-By:` line: TRAPS and HINTS in their trailer, a memory note anywhere outside a fenced block (its frontmatter or its body), a proposal through its `--hint-resolve` row. `JUDGMENT-ONLY` says on purpose that nothing mechanical can, which keeps it in rotation as prose.
#
# AN ENFORCER COUNTS ONLY WHEN IT IS LIVE AND TESTED. A guard nobody tests can be deleted or broken without a red, and then the lesson it replaced is gone from both places; so a live pointer whose enforcer has no test keeps the entry in rotation and sends it to the curator instead.

JUDGMENT_ONLY = "JUDGMENT-ONLY"
# `file:` is accepted on an Enforced-By line because TRAPS.md already uses it for guard scripts; --hint-resolve keeps the six POINTER_KINDS.
ENFORCED_KINDS = (*POINTER_KINDS, "file")
CLASSES = ("retire-now", "encode-as-guard", "encode-as-CI-gate", "fix-the-tool", "keep-as-prose")
# The class an entry gets when its named enforcer is dead or untested: finish that kind of mechanism.
KIND_CLASS = {
    "guard": "encode-as-guard",
    "hook": "encode-as-guard",
    "file": "encode-as-guard",
    "gate": "encode-as-CI-gate",
    "test": "fix-the-tool",
    "commit": "fix-the-tool",
    "trap": "keep-as-prose",
}
# Where a test that names an enforcer can live. Read once per sweep, never per pointer.
TEST_GLOBS = (
    ".claude/rediacc_hooks/tests/*.py",
    ".claude/rediacc_hooks/guards/test-*.py",
    ".claude/hooks/**/test-*.py",
    ".ci/rediacc_ci/tests/**/*.py",
)


class Ctx:
    """The per-sweep caches: the test corpus text and the TRAPS entries."""

    def __init__(self, root):
        self.root = root
        self._tests = None
        self._traps = None
        self._stems = None

    def tests_text(self):
        if self._tests is None:
            parts = []
            base = pathlib.Path(self.root)
            for pattern in TEST_GLOBS:
                parts.extend(_read(p) for p in sorted(base.glob(pattern)) if p.is_file())
            self._tests = "\n".join(parts)
        return self._tests

    def test_stems(self):
        """The module stems the test files are named for: `test-<stem>.py` and `test_<stem>.py`. A `file:` enforcer counts as tested only through its own test file, since every hook file is named somewhere in some test."""
        if self._stems is None:
            base = pathlib.Path(self.root)
            names = {p.stem for pattern in TEST_GLOBS for p in base.glob(pattern)}
            self._stems = {n[5:] for n in names if n.startswith(("test-", "test_"))}
        return self._stems

    def trap_enforced(self, trap_id):
        if self._traps is None:
            import wl_store as S

            self._traps = {e["id"]: e.get("enforced", "") for e in S.trap_entries(self.root)}
        return self._traps.get(trap_id, "")


def split_enforced(value):
    """The pointers of one Enforced-By value, in order. Commas and whitespace both separate, as in trap_registry (`.replace(",", " ").split()`)."""
    return str(value or "").replace(",", " ").split()


def _file_problem(root, token):
    rel, _sep, line = token.partition(":")
    path = _inside(root, rel)
    if path is None or not path.is_file():
        return "file:%s names no file in this tree" % token
    if line and (not line.isdigit() or int(line) < 1 or int(line) > _read(path).count("\n") + 1):
        return "file:%s points past the end of %s" % (token, rel)
    return None


def _commit_touches_a_test(root, token):
    names = PR._git_out(root, "show", "--name-only", "--format=", token)
    return any("test" in n.rsplit("/", 1)[-1] for n in names.splitlines())


def enforcer_state(root, pointer, ctx):
    """(live, tested, why) for one Enforced-By pointer."""
    kind, _sep, token = pointer.partition(":")
    kind, token = kind.strip(), token.strip()
    if kind == "file" and token:
        why = _file_problem(root, token)
    elif kind in POINTER_KINDS:
        why = pointer_problem(root, pointer)
    else:
        return False, False, "%r is not one of %s" % (pointer, ", ".join(ENFORCED_KINDS))
    if why:
        return False, False, why
    if kind == "file":
        # Two `file:` shapes name a mechanism of a kind with its own test rule: a guard module, and a gate script a package.json key runs.
        rel = pathlib.PurePosixPath(token.partition(":")[0])
        if str(rel.parent) == GUARDS_REL and not rel.name.startswith("test-"):
            kind, token = "guard", rel.stem
        else:
            gate = next((k for k, v in PR._package_scripts(root).items() if str(rel) in str(v)), "")
            if gate:
                kind, token = "gate", gate
    tests = ctx.tests_text()
    if kind == "guard":
        stem = token.removesuffix(".py")
        tested = (
            pathlib.Path(root) / GUARDS_REL / ("test-%s.py" % stem)
        ).is_file() or stem in tests
        return True, tested, "guard %s %s" % (stem, "has a test" if tested else "has no test")
    if kind == "hook":
        tested = token in tests or "rule_%s" % token.replace("-", "_") in tests
        state = "has a test" if tested else "has no test"
        return True, tested, "trapguard rule %s %s" % (token, state)
    if kind == "file":
        stem = pathlib.PurePosixPath(token.partition(":")[0]).stem
        tested = stem.startswith(("test-", "test_")) or stem in ctx.test_stems()
        state = (
            "has its own test file" if tested else "has no test-%s / test_%s file" % (stem, stem)
        )
        return True, tested, "%s %s" % (stem, state)
    if kind == "gate":
        try:
            import wl_reggate as RG

            tested = bool(RG.gate_reachable(PR._package_scripts(root), token, root))
        except Exception:
            tested = False
        state = "runs in npm run ci" if tested else "is not reachable from npm run ci"
        return True, tested, "gate %s %s" % (token, state)
    if kind == "test":
        return True, True, "test %s exists" % token
    if kind == "commit":
        tested = _commit_touches_a_test(root, token)
        state = "touches a test" if tested else "touches no test"
        return True, tested, "commit %s %s" % (token[:12], state)
    # trap: the trap itself must name a mechanism, not judgment
    inner = [p for p in split_enforced(ctx.trap_enforced(token)) if p != JUDGMENT_ONLY]
    state = "is enforced by %s" % ", ".join(inner) if inner else "is judgment-only"
    return True, bool(inner), "trap %s %s" % (token, state)


def classify(root, enforced, ctx):
    """{"class", "basis", "pointer", "why"} for one entry's Enforced-By value.

    retire-now is the one mechanical verdict: a live pointer whose enforcer is tested. JUDGMENT-ONLY alone is keep-as-prose by declaration. Everything else is provisional (`basis: curator`): a dead or untested enforcer gets the class of the mechanism to finish (KIND_CLASS), and an entry with no Enforced-By gets keep-as-prose until the lesson-curator judges it.
    """
    pointers = split_enforced(enforced)
    if not pointers:
        return {
            "class": "keep-as-prose",
            "basis": "curator",
            "pointer": "",
            "why": "no Enforced-By",
        }
    if pointers == [JUDGMENT_ONLY]:
        return {"class": "keep-as-prose", "basis": "declared", "pointer": "", "why": JUDGMENT_ONLY}
    first = None
    for pointer in pointers:
        if pointer == JUDGMENT_ONLY:
            continue
        live, tested, why = enforcer_state(root, pointer, ctx)
        if live and tested:
            return {"class": "retire-now", "basis": "mechanical", "pointer": pointer, "why": why}
        if first is None:
            first = {
                "class": KIND_CLASS.get(pointer.partition(":")[0].strip(), "encode-as-guard"),
                "basis": "curator",
                "pointer": pointer,
                "why": why,
            }
    return first or {
        "class": "keep-as-prose",
        "basis": "curator",
        "pointer": "",
        "why": "no pointer",
    }


def in_rotation(root, entries, ctx=None):
    """The hint entries that stay in rotation: every one whose Enforced-By does not name a live, tested enforcer. An entry that has one leaves the draw before anyone flips its Status (the flip to `retired` is the lead's reviewed edit)."""
    ctx = ctx or Ctx(root)
    return [
        e
        for e in entries
        if not (e.get("enforced") and classify(root, e["enforced"], ctx)["class"] == "retire-now")
    ]


# -- memory notes (outside the repo; read, never written) ---------------------


def default_memory_dir(root):
    """~/.claude/projects/<root with every non-alphanumeric as '-'>/memory, where the harness keeps this project's memory notes."""
    slug = re.sub(r"[^A-Za-z0-9]", "-", str(pathlib.Path(root).resolve()))
    return pathlib.Path.home() / ".claude" / "projects" / slug / "memory"


def memory_notes(memdir):
    """[{id, title, enforced, path}] for every note in `memdir` except the MEMORY.md index. Read-only."""
    out = []
    base = pathlib.Path(memdir)
    if not base.is_dir():
        return out
    for path in sorted(base.glob("*.md")):
        if path.name == "MEMORY.md":
            continue
        name, desc, enforced = "", "", ""
        fence = False
        for line in _read(path).splitlines():
            stripped = line.strip()
            if stripped.startswith(("```", "~~~")):
                fence = not fence
                continue
            if fence:
                continue
            if not name and stripped.startswith("name:"):
                name = stripped[5:].strip().strip("\"'")
            elif not desc and stripped.startswith("description:"):
                desc = stripped[12:].strip().strip("\"'")
            elif not enforced and stripped.startswith("Enforced-By:"):
                enforced = stripped[len("Enforced-By:") :].strip()
        out.append(
            {
                "id": path.stem,
                "title": desc or name or path.stem,
                "enforced": enforced,
                "path": str(path),
            }
        )
    return out


def sweep(root, memdir):
    """Every lesson entry of the four stores, classified: [{store, id, title, class, basis, pointer, why}]. Reads only."""
    import wl_hints as H
    import wl_store as S

    ctx = Ctx(root)
    rows = []

    def add(store, eid, title, enforced):
        rows.append(dict(classify(root, enforced, ctx), store=store, id=eid, title=title))

    for e in S.trap_entries(root):
        add(
            "traps", e.get("id") or "line-%s" % e.get("line"), e.get("title", ""), e.get("enforced")
        )
    entries, _errors = H.load_corpus(H.hints_path(root))
    for e in entries:
        if e.get("status") != "retired":
            add("hints", e.get("id", ""), e.get("heading", ""), e.get("enforced", ""))
    latest = {}
    for res in H._jsonl(H.resolutions_path(root)):
        if res.get("id"):
            latest[str(res["id"])] = str(res.get("pointer") or "")
    for p in H.proposals(root):
        add("proposals", p["id"], p.get("text", ""), latest.get(p["id"], ""))
    for note in memory_notes(memdir):
        add("memory", note["id"], note["title"], note["enforced"])
    return rows


def render_sweep(rows, memdir):
    """The --lessons-sweep table: counts per class, then one line per entry, retire-now first."""
    counts = dict.fromkeys(CLASSES, 0)
    for r in rows:
        counts[r["class"]] += 1
    out = [
        "lessons sweep: %d entries across traps, hints, proposals and memory (%s)"
        % (len(rows), memdir),
        "  " + ", ".join("%s %d" % (c, counts[c]) for c in CLASSES),
        "  retire-now is mechanical (a live, tested enforcer); basis `curator` rows wait on the lesson-curator.",
    ]
    order = {c: i for i, c in enumerate(CLASSES)}
    out.extend(
        "  %-17s %-10s %s:%s  %s  [%s]"
        % (r["class"], r["basis"], r["store"], r["id"], r["pointer"] or "-", r["why"])
        for r in sorted(rows, key=lambda r: (order[r["class"]], r["store"], r["id"]))
    )
    return "\n".join(out)
