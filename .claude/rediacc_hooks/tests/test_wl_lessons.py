"""wl_lessons: Enforced-By pointers, the rotation drop and --lessons-sweep (agent/plans/PLAN-experience-feedback.md P7, box C7a).

Every world here is a temp root with its own HINTS, TRAPS, guards, tests and memory directory. The real memory notes live outside the repo and are never read or written by this suite.
"""

from __future__ import annotations

import json
import random
from typing import TYPE_CHECKING

from rediacc_hooks.tests import wlfix

if TYPE_CHECKING:
    import pathlib


# What the real guards package does: its stems are the modules in the directory.
GUARDS_INIT = (
    "import pathlib\n\n\ndef stems():\n"
    "    return sorted(p.stem for p in pathlib.Path(__file__).parent.glob('block_*.py'))\n"
)


def _lessons():
    return wlfix.import_wl("wl_lessons")


def _hints():
    return wlfix.import_wl("wl_hints")


def _write(root: pathlib.Path, rel: str, text: str) -> pathlib.Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _hint(hint_id: str, enforced: str = "") -> str:
    line = "Enforced-By: %s\n" % enforced if enforced else ""
    return "## Heading for %s\nHint-Id: %s\nSource: file:CLAUDE.md:1\nStatus: active\n%s\n" % (
        hint_id,
        hint_id,
        line,
    )


def _world(tmp_path: pathlib.Path, monkeypatch) -> pathlib.Path:
    """A root with a tested guard, an untested guard, a trapguard rule with a test, and a corpus."""
    monkeypatch.delenv("WORKLIST_HINTS_FILE", raising=False)
    _write(tmp_path, "CLAUDE.md", "rules\n")
    _write(tmp_path, ".claude/rediacc_hooks/guards/block_tested.py", "RULE = 1\n")
    _write(
        tmp_path,
        ".claude/rediacc_hooks/guards/test-block_tested.py",
        "# tests block_tested\ndef test_it():\n    pass\n",
    )
    _write(tmp_path, ".claude/rediacc_hooks/guards/block_untested.py", "RULE = 1\n")
    # The shared resolver (trap_registry.pointer_problem) asks the guards package which stems it loads, and the dispatcher which rules it lists.
    _write(
        tmp_path,
        ".claude/rediacc_hooks/guards/__init__.py",
        GUARDS_INIT,
    )
    _write(
        tmp_path,
        ".claude/hooks/trapguard/dispatch.py",
        "def rule_tested_rule(cmd):\n    return 'NEEDLE-tested'\n\n\n"
        "def rule_lonely_rule(cmd):\n    return 1\n\n\n"
        "RULES = (\n    rule_tested_rule,\n    rule_lonely_rule,\n)\n",
    )
    _write(
        tmp_path,
        ".claude/rediacc_hooks/tests/test_hooks_trapguard.py",
        "def test_tested_rule():\n    assert 'tested-rule'\n\n"
        "check_inject fires 'a case' \"NEEDLE-tested\"\ncheck_inject silent 'a case' \"x\"\n",
    )
    _write(
        tmp_path,
        "docs/agent-reference/HINTS.md",
        _hint("judged", "JUDGMENT-ONLY")
        + _hint("untested", "guard:block_untested")
        + _hint("enforced", "guard:block_tested")
        + _hint("plain")
        + _hint("dead", "guard:block_gone"),
    )
    _write(
        tmp_path,
        "docs/agent-reference/TRAPS.md",
        "# Traps\n\n## a judged trap\nTrap-Id: judged-trap\nEnforced-By: JUDGMENT-ONLY\nResidue: x.\n\n"
        "## a hooked trap\nTrap-Id: hooked-trap\nEnforced-By: hook:tested-rule\nResidue: x.\n\n"
        "## a lonely trap\nTrap-Id: lonely-trap\nEnforced-By: hook:lonely-rule\nResidue: x.\n",
    )
    return tmp_path


def _ids(entries) -> list[str]:
    return [e["id"] for e in entries]


# ---- the rotation drop ------------------------------------------------------


def test_rotation_control_a_judgment_only_entry_stays_in_rotation(tmp_path, monkeypatch):
    """CONTROL: JUDGMENT-ONLY declares that nothing mechanical carries the lesson, so it stays drawable."""
    root = _world(tmp_path, monkeypatch)
    entries, errors = _hints().load_corpus(root / "docs/agent-reference/HINTS.md")
    assert errors == [], errors
    assert "judged" in _ids(_lessons().in_rotation(str(root), entries))


def test_rotation_control_an_entry_whose_enforcer_has_no_test_stays(tmp_path, monkeypatch):
    """CONTROL: a live guard nobody tests is not yet an enforcer; the entry stays drawable."""
    root = _world(tmp_path, monkeypatch)
    entries, _errors = _hints().load_corpus(root / "docs/agent-reference/HINTS.md")
    kept = _ids(_lessons().in_rotation(str(root), entries))
    assert "untested" in kept, kept
    assert "dead" in kept, kept
    assert "plain" in kept, kept


def test_rotation_an_entry_with_a_live_tested_enforcer_leaves_the_draw(tmp_path, monkeypatch):
    root = _world(tmp_path, monkeypatch)
    h = _hints()
    entries, _errors = h.load_corpus(root / "docs/agent-reference/HINTS.md")
    assert {e["id"]: e["enforced"] for e in entries}["enforced"] == "guard:block_tested"
    kept = h.rotation(str(root), entries)
    assert _ids(kept) == ["judged", "untested", "plain", "dead"], _ids(kept)
    ledger: dict = {}
    picks = {h.hint_pick(kept, ledger, rng=random.Random(i))[0]["id"] for i in range(40)}
    assert "enforced" not in picks, picks
    (root / ".claude/rediacc_hooks/guards/test-block_tested.py").unlink()
    assert "enforced" in _ids(h.rotation(str(root), entries)), "deleting the test returns the hint"


def test_rotation_fails_open_when_the_check_raises(tmp_path, monkeypatch):
    h = _hints()
    entries = [{"id": "x", "enforced": "guard:block_tested", "status": "active"}]

    def boom(*_a, **_k):
        raise RuntimeError("planted")

    monkeypatch.setattr(_lessons(), "in_rotation", boom)
    assert h.rotation(str(tmp_path), entries) == entries


# ---- classify ---------------------------------------------------------------


def test_classify_the_five_classes_and_their_basis(tmp_path, monkeypatch):
    root = str(_world(tmp_path, monkeypatch))
    lessons = _lessons()
    _write(tmp_path, "package.json", json.dumps({"scripts": {"ci": "true"}}))
    ctx = lessons.Ctx(root)

    def cls(value):
        got = lessons.classify(root, value, ctx)
        return got["class"], got["basis"]

    assert cls("guard:block_tested") == ("retire-now", "mechanical")
    assert cls("hook:tested-rule") == ("retire-now", "mechanical")
    assert cls("trap:hooked-trap") == ("retire-now", "mechanical")
    assert cls("JUDGMENT-ONLY") == ("keep-as-prose", "declared")
    assert cls("") == ("keep-as-prose", "curator")
    assert cls("guard:block_untested") == ("encode-as-guard", "curator")
    assert cls("hook:lonely-rule") == ("encode-as-guard", "curator")
    assert cls("trap:judged-trap") == ("keep-as-prose", "curator")
    assert cls("gate:check:ci-absent") == ("encode-as-CI-gate", "curator")
    assert cls("test:no/such/test.py") == ("fix-the-tool", "curator")
    assert cls("shape:not-yet-a-kind") == ("encode-as-guard", "curator")
    # Commas and whitespace both separate, as in trap_registry; the first live tested pointer wins.
    assert cls("guard:block_untested guard:block_tested") == ("retire-now", "mechanical")
    assert cls("JUDGMENT-ONLY, guard:block_tested") == ("retire-now", "mechanical")


def test_file_pointer_to_a_guard_module_takes_the_guard_rule(tmp_path, monkeypatch):
    root = str(_world(tmp_path, monkeypatch))
    lessons = _lessons()
    ctx = lessons.Ctx(root)
    tested = lessons.classify(root, "file:.claude/rediacc_hooks/guards/block_tested.py", ctx)
    assert tested["class"] == "retire-now", tested
    untested = lessons.classify(root, "file:.claude/rediacc_hooks/guards/block_untested.py", ctx)
    assert untested["class"] == "encode-as-guard", untested
    missing = lessons.classify(root, "file:CLAUDE.md:99", ctx)
    assert missing["class"] == "encode-as-guard", missing
    assert "past the end" in missing["why"], missing


# ---- memory notes and the sweep ---------------------------------------------


def _memory(tmp_path: pathlib.Path) -> pathlib.Path:
    mem = tmp_path / "memory"
    _write(tmp_path, "memory/MEMORY.md", "- [a](note_enforced.md) index line\n")
    _write(
        tmp_path,
        "memory/note_enforced.md",
        "---\nname: note-enforced\ndescription: a lesson a tested guard carries\n---\n\n"
        "Body.\n\nEnforced-By: guard:block_tested\n",
    )
    _write(
        tmp_path,
        "memory/note_prose.md",
        "---\nname: note-prose\ndescription: a lesson only judgment applies\n---\n\n"
        "```\nEnforced-By: guard:block_tested\n```\n",
    )
    return mem


def test_memory_notes_read_enforced_by_outside_fences_and_skip_the_index(tmp_path):
    notes = _lessons().memory_notes(_memory(tmp_path))
    assert [(n["id"], n["enforced"]) for n in notes] == [
        ("note_enforced", "guard:block_tested"),
        ("note_prose", ""),
    ]
    assert notes[0]["title"] == "a lesson a tested guard carries"


def test_sweep_classifies_all_four_stores_and_writes_nothing(tmp_path, monkeypatch):
    root = _world(tmp_path, monkeypatch)
    mem = _memory(tmp_path)
    h = _hints()
    carried = h.propose(str(root), "d778be9d", "a proposal a guard carries", "")
    h.propose(str(root), "d778be9d", "a proposal still waiting", "")
    h.resolve_proposal(str(root), "d778be9d", carried["id"], "guard:block_tested")
    before = {p: p.read_bytes() for p in mem.iterdir()}
    rows = _lessons().sweep(str(root), mem)
    after = {p: p.read_bytes() for p in mem.iterdir()}
    assert before == after, "the sweep wrote to the memory directory"
    got = {(r["store"], r["id"]): r["class"] for r in rows}
    assert got[("memory", "note_enforced")] == "retire-now"
    assert got[("memory", "note_prose")] == "keep-as-prose"
    assert got[("hints", "enforced")] == "retire-now"
    assert got[("hints", "untested")] == "encode-as-guard"
    assert got[("hints", "judged")] == "keep-as-prose"
    assert got[("traps", "hooked-trap")] == "retire-now"
    assert got[("traps", "lonely-trap")] == "encode-as-guard"
    assert got[("proposals", carried["id"])] == "retire-now"
    assert len([k for k in got if k[0] == "proposals"]) == 2
    assert {r["class"] for r in rows} <= set(_lessons().CLASSES)
    for r in rows:
        if r["class"] == "retire-now":
            assert r["pointer"], r
            assert r["basis"] == "mechanical", r


def test_lessons_sweep_cli_prints_the_table_and_the_json(wl):
    mem = _memory(wl.proj)
    _write(wl.proj, ".claude/rediacc_hooks/guards/block_tested.py", "RULE = 1\n")
    _write(wl.proj, ".claude/rediacc_hooks/guards/__init__.py", GUARDS_INIT)
    _write(
        wl.proj,
        ".claude/rediacc_hooks/guards/test-block_tested.py",
        "# tests block_tested\ndef test_it():\n    pass\n",
    )
    got = wl.cli("--lessons-sweep", "deadbeef", "--memory-dir", str(mem))
    assert got.rc == 0, got.err
    assert got.out.startswith("lessons sweep: "), got.out[:300]
    assert "retire-now        mechanical memory:note_enforced  guard:block_tested" in got.out, (
        got.out
    )
    js = wl.cli("--lessons-sweep", "deadbeef", "--memory-dir", str(mem), "--json")
    assert js.rc == 0, js.err
    rows = json.loads(js.out)
    assert {"store", "id", "title", "class", "basis", "pointer", "why"} <= set(rows[0])
    bad = wl.cli("--lessons-sweep", "deadbeef", "--bogus")
    assert bad.rc == 2, bad.err
    assert "usage: worklist.py --lessons-sweep" in bad.err, bad.err


# ---- the shared resolver (box C7b) -------------------------------------------


def test_pointer_problem_asks_the_shared_resolver_for_the_traps_kinds(tmp_path, monkeypatch):
    """CONTROL: a live guard resolves; each dead pointer carries `trap_registry.pointer_problem`'s own clause."""
    root = str(_world(tmp_path, monkeypatch))
    lessons = _lessons()
    assert lessons.pointer_problem(root, "guard:block_tested") is None
    why = lessons.pointer_problem(root, "guard:block_gone")
    assert why is not None
    assert "is not a guard the pre-tool dispatcher loads" in why, why
    why = lessons.pointer_problem(root, "hook:lonely-rule")
    assert why is not None
    assert "lacks a FIRING case or a SILENT case" in why, why
    why = lessons.pointer_problem(root, "gate:check:ci-absent")
    assert why is not None
    assert "not both a manifest entry and a package.json script" in why, why


def test_pointer_problem_is_dead_when_the_shared_resolver_cannot_load(tmp_path, monkeypatch):
    """A resolver failure never makes a pointer live."""
    root = str(_world(tmp_path, monkeypatch))
    lessons = _lessons()

    def boom(*_a, **_k):
        raise ImportError("planted")

    monkeypatch.setattr(lessons, "shared_registry", boom)
    why = lessons.pointer_problem(root, "guard:block_tested")
    assert why is not None
    assert "could not be resolved" in why, why
    assert lessons.classify(root, "guard:block_tested", lessons.Ctx(root))["class"] != "retire-now"


def test_a_self_referencing_shape_entry_is_kept_not_retired(tmp_path):
    """#5394dfa7: an entry whose Enforced-By is shape:<its own id> is the guard's data; retiring it deletes the rule."""
    lessons = _lessons()
    ctx = lessons.Ctx(str(tmp_path))
    row = lessons.classify(str(tmp_path), "shape:feedback_x", ctx, own_id="feedback_x")
    assert row["class"] == "keep-as-prose"
    assert row["basis"] == "declared"
    # CONTROL: the same pointer on a different entry is judged on the enforcer, not kept by declaration.
    other = lessons.classify(str(tmp_path), "shape:feedback_x", ctx, own_id="feedback_y")
    assert other["basis"] != "declared" or other["class"] != "keep-as-prose"
