"""`rediacc_ci.quality.trap_registry` against the awk parser it replaces.

WHY A DIFFERENTIAL ON THE PARSER. It is a fence-tracking state machine whose whole reason for existing is that a `## ` inside a fenced example in a trap body must not become a phantom entry, and trap bodies routinely carry markdown examples. A table of expected entries would be a table of what the port does. Running the twin's awk on the same corpus is the only comparison that can
fail
for the right reason.

The whole gate, including F6's planted controls (the gate prints their count), is covered by `.ci/shadow/w7p2-trap-registry.observations.jsonl` over five distinct trees.

THE TWIN IS RETIRED (PLAN-retire-bash-oracles B3). Its awk parser's answers, its floor and its two summary lines are frozen in `goldens/twins/quality.check-trap-registry.jsonl` through `differential.twin_call`; the extraction below runs only when that golden is re-frozen from a live twin (`regolden.py --source bash`).
"""

import importlib.util
import pathlib
import subprocess
import sys

import pytest

from rediacc_ci import paths
from rediacc_ci.quality import plan_lifecycle
from rediacc_ci.quality import trap_registry as mod
from rediacc_ci.tests import differential as diff

TWIN = pathlib.Path(".ci/scripts/quality/check-trap-registry.sh")
TWIN_REL = str(TWIN)


def _awk_program() -> str:
    """The `parse_corpus` awk body, extracted from the twin at run time.

    Extracted rather than copied so this test breaks LOUDLY when the twin's parser is edited, which is exactly when it should be re-read. Sliced between markers rather than by line number, because a line number churns when a paragraph moves above it.
    """
    text = TWIN.read_text(encoding="utf-8")
    start = text.index("parse_corpus() {")
    body_start = text.index("awk '", start) + len("awk '")
    end = text.index('\n    \' "$1"', body_start)
    return text[body_start:end]


CORPORA = [
    "## first\nTrap-Id: a-trap\nEnforced-By: JUDGMENT-ONLY\nResidue: nothing.\n\nbody\n",
    "## one\nTrap-Id: one\nEnforced-By: gate:check:x\nResidue:\n",  # empty Residue
    "## no trailer at all\n\nbody\n",
    "### not an entry\n",
    (
        "## r\nTrap-Id: r\nEnforced-By: JUDGMENT-ONLY\nResidue: x.\n\n"
        "```markdown\n## Not A Trap\n```\n"
    ),  # a fenced example
    "## r\nTrap-Id: r\n\n~~~\n## Also Not A Trap\n~~~\n",  # the tilde fence
    "## t\nTrap-Id: t\n\nResidue: this is body prose\n",  # trailer ends at the blank line
    "## a\nTrap-Id: a\nEnforced-By: x\nResidue: y\n## b\nTrap-Id: b\n",  # back to back
    "",  # empty corpus
    "no headings at all\n",
]


def _port_rows(corpus: str) -> str:
    """The port's entries in the awk program's own output shape, for a re-record from the port."""
    return "".join(
        "%d\x1f%s\x1f%s\x1f%s\x1f%s\n"
        % (e.line, e.trap_id, e.enforced_by, e.residue, "1" if e.residue_seen else "0")
        for e in mod.parse_corpus(corpus)
    )


@pytest.mark.parametrize("corpus", CORPORA)
def test_parser_matches_the_twins_awk(tmp_path: pathlib.Path, corpus: str) -> None:
    target = tmp_path / "TRAPS.md"
    target.write_text(corpus, encoding="utf-8")

    def awk():
        proc = subprocess.run(
            ["awk", _awk_program(), str(target)],
            capture_output=True,
            text=True,
            check=False,
        )
        return proc.returncode, proc.stdout, proc.stderr

    rc, out, err = diff.twin_call(
        TWIN_REL,
        ["awk parse_corpus", corpus],
        awk,
        port=lambda: (0, _port_rows(corpus), ""),
        work=tmp_path,
    )
    assert rc == 0, err
    expected = []
    for line in out.split("\n"):
        if line == "":
            continue
        # US (0x1f), not TAB: tab is IFS whitespace in bash, so a run of two tabs COLLAPSES and an empty Residue silently reads as no Residue LINE.
        fields = line.split("\x1f")
        expected.append((int(fields[0]), fields[1], fields[2], fields[3], fields[4] == "1"))
    got = [
        (e.line, e.trap_id, e.enforced_by, e.residue, e.residue_seen)
        for e in mod.parse_corpus(corpus)
    ]
    assert got == expected


def _twin_floor():
    text = TWIN.read_text(encoding="utf-8")
    marker = 'TRAP_FLOOR="${TRAP_FLOOR:-'
    start = text.index(marker) + len(marker)
    return 0, text[start : text.index('}"', start)], ""


def test_the_floor_is_the_twins_number() -> None:
    """A divergence here is invisible to the differential.

    Every fixture in the shadow ledger sets `TRAP_FLOOR` explicitly, so the DEFAULT is the one value the two implementations can disagree about without any recorded row noticing. It moved 75 -> 76 -> 77 within one session on 2026-09-06, which is precisely why this assertion exists. Since the twin's retirement the frozen value is the floor it carried; raising the port's default is a Rule-T change re-recorded from the port with its reason.
    """
    _rc, twin_floor, _err = diff.twin_call(
        TWIN_REL,
        ["TRAP_FLOOR default"],
        _twin_floor,
        port=lambda: (0, str(mod.TRAP_FLOOR_DEFAULT), ""),
    )
    assert int(twin_floor) == mod.TRAP_FLOOR_DEFAULT


def _twin_summary_lines():
    text = TWIN.read_text(encoding="utf-8")
    needles = ('[ "$errors" -eq 0 ]', '"$found trap-registry finding(s) in $TRAP_CORPUS')
    return 0, "".join("%s\n" % n for n in needles if n in text), ""


def test_the_summary_count_is_the_twins_boolean() -> None:
    """The twin prints a BOOLEAN where its message says "finding(s)".

    `scan` in bash ends with `[ "$errors" -eq 0 ]` on purpose (a shell return is mod 256), and `main` then prints that status as the count. The port carries the bug rather than the intent, because a port that changed it would be non-equivalent to the gate CI runs. This assertion is the record of that decision, now against the frozen twin; fixing it is a B4 Rule-T change that re-records this case from the port.
    """
    _rc, out, _err = diff.twin_call(TWIN_REL, ["summary-count source lines"], _twin_summary_lines)
    assert '[ "$errors" -eq 0 ]' in out
    assert '"$found trap-registry finding(s) in $TRAP_CORPUS' in out


def test_id_grammar() -> None:
    assert mod.ID_RE.match("mark-done-all-stale-is-a-bulk-verb")
    assert mod.ID_RE.match("abc")
    assert not mod.ID_RE.match("ab")
    assert not mod.ID_RE.match("Not_Kebab_Case")
    assert not mod.ID_RE.match("-abc")


# --- W3-retire: the payload probe stays unregistered (PLAN-trap-enforcement.md section 7.1) ---


def _probe_registry(tmp_path: pathlib.Path, lifecycle: str, settings: str) -> "mod.Registry":
    """A registry over a clean fixture corpus whose only variable is what the two registration files say."""
    files = tmp_path / "files"
    (files / "sub").mkdir(parents=True)
    (files / "sub" / "ctl-guard.sh").write_text("#!/bin/bash\necho real\n", encoding="utf-8")
    (tmp_path / "manifest.ts").write_text(mod.CONTROL_MANIFEST, encoding="utf-8")
    (tmp_path / "package.json").write_text(
        '{ "scripts": { "check:ctl-live": "true", "check:ctl-dark": "true" } }\n', encoding="utf-8"
    )
    (tmp_path / "dispatch.py").write_text(mod.CONTROL_DISPATCH, encoding="utf-8")
    (tmp_path / "test-hooks.sh").write_text(mod.CONTROL_SUITE, encoding="utf-8")
    (tmp_path / "lifecycle.py").write_text(lifecycle, encoding="utf-8")
    (tmp_path / "settings.json").write_text(settings, encoding="utf-8")
    (tmp_path / "corpus.md").write_text(mod.fixture_corpus("", 5), encoding="utf-8")
    return mod.Registry(
        {
            "TRAP_CORPUS": tmp_path / "corpus.md",
            "TRAP_MANIFEST": tmp_path / "manifest.ts",
            "TRAP_PACKAGE_JSON": tmp_path / "package.json",
            "TRAP_DISPATCH": tmp_path / "dispatch.py",
            "TRAP_HOOK_SUITE": tmp_path / "test-hooks.sh",
            "TRAP_SETTINGS": tmp_path / "settings.json",
            "TRAP_LIFECYCLE": tmp_path / "lifecycle.py",
            "TRAP_FILE_ROOT": files,
            "TRAP_ANCHOR_ROOT": files,
        }
    )


def _probe_findings(registry: "mod.Registry") -> list[str]:
    found: list[str] = []
    mod.scan(registry, 5, mod.Shape(), report=found.append)
    return found


def test_a_clean_registration_passes_the_probe_assertion(tmp_path: pathlib.Path) -> None:
    reg = _probe_registry(tmp_path, mod.CONTROL_LIFECYCLE, '{ "hooks": {} }\n')
    assert _probe_findings(reg) == []


def test_the_probe_registered_in_lifecycle_reds(tmp_path: pathlib.Path) -> None:
    reg = _probe_registry(tmp_path, mod.CONTROL_LIFECYCLE_PROBE, '{ "hooks": {} }\n')
    found = _probe_findings(reg)
    assert len(found) == 1, found
    assert "registers the trapguard payload probe" in found[0]
    assert "lifecycle.py" in found[0]


def test_the_probe_registered_in_settings_reds(tmp_path: pathlib.Path) -> None:
    reg = _probe_registry(tmp_path, mod.CONTROL_LIFECYCLE, mod.CONTROL_SETTINGS_PROBE)
    found = _probe_findings(reg)
    assert len(found) == 1, found
    assert "settings.json" in found[0]


def test_the_controls_include_the_probe_plant_and_pass(tmp_path: pathlib.Path) -> None:
    """run_controls must carry the W3-retire plant and still behave; the real tree's registration files must be clean."""
    assert mod.run_controls(tmp_path)
    assert (tmp_path / "lifecycle-probe.py").is_file()
    real = mod.Registry(mod.resolve_seams(mod.paths.repo_root(), env={}))
    for reg in (real.settings, real.lifecycle):
        assert mod.PROBE_FLAG not in mod.read_text(reg), reg


# --- PLAN-lessons-registry: Documented-In anchors and guard: pointers ---


def _check_plan_boxes():
    """`.ci/scripts/quality/check_plan_boxes.py`, loaded by path: the formula `box_sig` restates."""
    scripts = paths.from_root(".ci", "scripts", "quality")
    # The script's own `import _cipath` shim lives beside it.
    paths.on_sys_path(scripts)
    spec = importlib.util.spec_from_file_location(
        "check_plan_boxes_for_trap_registry", scripts / "check_plan_boxes.py"
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_box_sig_is_the_plan_box_gates_sig_on_every_real_box() -> None:
    """THE FORMULA EXISTS TWICE (L3), so the copies are compared on the real corpus, not on one example.

    `check_plan_boxes.sig` is fed what `wl_planfid.plan_tasks` hands it; `box_sig` reads the raw box body. Every box `plan_boxes` finds must sign as one of the gate's own task sigs. Anti-vacuity: the corpus must hold boxes, or the equality was asserted over nothing.
    """
    cpb = _check_plan_boxes()
    planfid = sys.modules["wl_planfid"]
    compared = 0
    root = paths.repo_root()
    for rel_dir in plan_lifecycle.PLAN_DIRS:
        for plan in sorted((root / rel_dir).glob("PLAN-*.md")):
            text = plan.read_text(encoding="utf-8", errors="replace")
            theirs = {cpb.sig(task) for task in planfid.plan_tasks(text)}
            for label, sig, _record in mod.plan_boxes(text):
                compared += 1
                assert sig in theirs, (plan, label, sig)
    assert compared >= 100, "only %d boxes compared; the plan corpus was not seen" % compared


@pytest.mark.parametrize(
    "body",
    [
        "G4 The guard refuses outstanding `droppedTouched` and fails closed.",
        "L1 Writer A: `parse_corpus` accepts **Documented-In:** lines after snake_case_name.",
        "  trailing and   inner   whitespace  ",
    ],
)
def test_box_sig_matches_the_gate_on_awkward_text(body: str) -> None:
    """Backticks, emphasis and underscores are where a restated normaliser drifts first."""
    cpb = _check_plan_boxes()
    planfid = sys.modules["wl_planfid"]
    (task,) = planfid.plan_tasks("- [ ] %s\n" % body)
    assert mod.box_sig(body) == cpb.sig(task)


def test_documented_in_does_not_move_the_five_golden_fields() -> None:
    """L1: the trailer gains a key after Residue, and the five fields the frozen golden compares are unchanged by it."""
    plain = "## a\nTrap-Id: a-trap\nEnforced-By: JUDGMENT-ONLY\nResidue: r.\n\nbody\n"
    with_anchor = plain.replace("Residue: r.\n", "Residue: r.\nDocumented-In: trap:a-trap\n")

    def five(corpus: str):
        return [
            (e.line, e.trap_id, e.enforced_by, e.residue, e.residue_seen)
            for e in mod.parse_corpus(corpus)
        ]

    assert five(with_anchor) == five(plain)
    assert mod.parse_corpus(with_anchor)[0].documented_in == [(5, "trap:a-trap")]
    assert mod.parse_corpus(plain)[0].documented_in == []


def test_the_anchor_controls_are_in_run_controls(tmp_path: pathlib.Path) -> None:
    """L5: the C-controls ship INSIDE the gate's F6 run, so every real invocation proves them, not only this suite."""
    assert mod.run_controls(tmp_path)
    for name in ("c1.md", "c2.md", "c6.md", "c9.md", "c14.md", "c16.md", "c21.md"):
        assert (tmp_path / name).is_file(), name


def _anchor_registry(tmp_path: pathlib.Path, corpus: str) -> "mod.Registry":
    files = tmp_path / "files"
    files.mkdir()
    mod.build_anchor_fixture(files)
    reg = _probe_registry(tmp_path / "base", mod.CONTROL_LIFECYCLE, '{ "hooks": {} }\n')
    reg.file_root = files
    reg.anchor_root = files
    reg.corpus.write_text(mod.fixture_corpus(corpus, 5), encoding="utf-8")
    return reg


def test_a_reworded_phrase_reds_and_names_the_entry(tmp_path: pathlib.Path) -> None:
    """Both directions over ONE fixture: the phrase as written is green, and after the rewording the same anchor reds naming its entry."""
    entry = mod.anchored(
        "reworded-lesson", "guard:block_ctl_tested", "text:docs/lesson.md a timeout above its sleep"
    )
    reg = _anchor_registry(tmp_path, entry)
    assert _probe_findings(reg) == []
    lesson = tmp_path / "files" / "docs" / "lesson.md"
    lesson.write_text(
        lesson.read_text(encoding="utf-8").replace("timeout above", "limit beyond"),
        encoding="utf-8",
    )
    found = _probe_findings(reg)
    assert len(found) == 1, found
    assert "'reworded-lesson'" in found[0]
    assert "phrase not found in docs/lesson.md" in found[0]


def test_the_shape_counts_every_new_kind(tmp_path: pathlib.Path) -> None:
    """L4: a collapse in any kind must show in the success line, so each kind is counted."""
    sig = mod.box_sig(mod.CONTROL_BOX)
    entry = mod.anchored(
        "counted-lesson",
        "guard:block_ctl_tested",
        "text:docs/lesson.md a timeout above its sleep",
        "doc:docs/headings.md#Deep Moved Heading",
        "box:PLAN-ctl-box#G4@%s" % sig,
        "trap:filler-trap-1",
    )
    reg = _anchor_registry(tmp_path, entry)
    shape = mod.Shape()
    assert mod.scan(reg, 5, shape, report=lambda _m: None) == 0
    assert shape.guard == 1
    assert shape.anchors == {"text": 1, "doc": 1, "box": 1, "trap": 1}


def test_the_real_guard_stems_are_seen() -> None:
    """Anti-vacuity for guard: pointers: an empty stem list would make every guard: red for the wrong reason, or a loader bug read as a clean tree."""
    real = mod.Registry(mod.resolve_seams(paths.repo_root(), env={}))
    stems = real.guard_stems()
    assert len(stems) >= 30, stems
    assert "block_unverified_push" in stems
    assert real.guard_liveness("block_unverified_push") == ""
    assert real.anchor_root == paths.repo_root()


def test_an_anchor_on_the_registry_file_cannot_match_its_own_documented_in_line(
    tmp_path: pathlib.Path,
) -> None:
    """Review e2405948.1: `text:<corpus> <phrase>` must find the phrase in an entry's body, not in the `Documented-In:` line that carries it."""
    phrase = "a lesson sentence that lives nowhere else"
    entry = mod.anchored("self-anchor", "guard:block_ctl_tested", "text:corpus.md %s" % phrase)
    reg = _anchor_registry(tmp_path, entry)
    reg.anchor_root = reg.corpus.parent
    # The corpus file must be reachable under the name the anchor gives.
    named = reg.corpus.parent / "corpus.md"
    named.write_text(reg.corpus.read_text(encoding="utf-8"), encoding="utf-8")
    reg.corpus = named
    assert "phrase not found" in reg.text_problem("corpus.md %s" % phrase)
    named.write_text(
        named.read_text(encoding="utf-8") + "\n%s, written in a body.\n" % phrase, encoding="utf-8"
    )
    assert reg.text_problem("corpus.md %s" % phrase) == ""


def test_an_empty_sibling_suite_does_not_make_a_guard_live(tmp_path: pathlib.Path) -> None:
    """Review e2405948.2: the sibling `test-<stem>.py` has to name the guard, so an empty file is not a suite."""
    reg = _anchor_registry(tmp_path, mod.anchored("t", "guard:block_ctl_tested"))
    sibling = reg.file_root / mod.GUARDS_PACKAGE_REL / "test-block_ctl_tested.py"
    assert reg.guard_liveness("block_ctl_tested") == ""
    sibling.write_text("", encoding="utf-8")
    assert reg.guard_liveness("block_ctl_tested") != ""


def test_a_longer_guard_name_in_the_sibling_suite_does_not_make_a_guard_live(
    tmp_path: pathlib.Path,
) -> None:
    """Review 9928d5bc.2: `block_ctl_tested_extra` in the suite is a different name, not `block_ctl_tested`."""
    reg = _anchor_registry(tmp_path, mod.anchored("t", "guard:block_ctl_tested"))
    sibling = reg.file_root / mod.GUARDS_PACKAGE_REL / "test-block_ctl_tested.py"
    sibling.write_text("# covers block_ctl_tested_extra only\n", encoding="utf-8")
    assert reg.guard_liveness("block_ctl_tested") != ""
    sibling.write_text("# covers block_ctl_tested_extra and block_ctl_tested.\n", encoding="utf-8")
    assert reg.guard_liveness("block_ctl_tested") == ""
