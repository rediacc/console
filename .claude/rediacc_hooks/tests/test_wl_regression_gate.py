"""The regression-gate marker, ported from `.claude/hooks/stop/worklist-cases/06-regression-gate.sh`.

What asks, what settles, hallucinated coverage, transitive gate proof, and tick signals. One test per numbered bash case, carrying the same assertions in the same order against the same subprocess.

THE CONTROLS ARE THE POINT of several of these, and they are marked as such: a doc-only fix that must never nag, a gate defined but not reachable from `ci`, a citation that matches no real gate, and product code that must not be called gate maintenance. Each is a document that must still PASS, so the rule under test cannot be satisfied by refusing everything.
"""

from __future__ import annotations

import json
import re

from rediacc_hooks.tests import wlfix
from rediacc_hooks.tests.wlfix import wl  # noqa: F401

# A package.json whose `ci` key really runs `check:ci-real`, which is what makes a citation of that name resolvable rather than hallucinated.
PKG_REAL_GATE = (
    '{"name":"p","version":"0.0.0","scripts":'
    '{"ci":"npm run check:ci-real","check:ci-real":"true"}}\n'
)

PKG_TRIVIAL_CI = '{"name":"p","version":"0.0.0","scripts":{"ci":"true"}}\n'

PKG_RUNNER_CI = '{"name":"p","version":"0.0.0","scripts":{"ci":"tsx scripts/ci-runner/run.ts"}}\n'

MANIFEST_TS = (
    "export const GATES = [\n"
    "  { id: 'gate-test:real-thing', run: '.ci/scripts/test/gates/test-real-thing.sh',"
    " gate: true },\n"
    "];\n"
)

GATES_LOCK = (
    "[\n"
    '  { "id": "gate-test:real-thing", "run": ".ci/scripts/test/gates/test-real-thing.sh",'
    ' "gate": true }\n'
    "]\n"
)


def judge_verdict(**fields) -> str:
    """One `regression_gate` payload for `shim_judge`, with the suite's defaults filled in."""
    payload = {
        "applicable": True,
        "blind_spot": "",
        "existing_gate": "",
        "recurring": False,
        "gate_needed": False,
        "gate_proven": False,
        "instruction": "none",
    }
    payload.update(fields)
    return json.dumps(payload)


def write_manifest_and_lock(fix) -> None:
    """The ci-runner manifest AND the committed lock beside it.

    THE LOCK IS WHAT THE PROBE READS NOW. `wl_reggate.py` used to regex-parse `manifest.ts`; on 2026-09-06 it was drained onto the committed JSON projection `scripts/ci-runner/gates.lock.json`. A fixture that writes only the TypeScript leaves the probe with zero registrations, so every citation reads as hallucinated and four cases went red. The manifest is kept as well: it is what
    a reader of this fixture expects to see, and the two must agree in a fixture exactly as they must in the tree.
    """
    runner = fix.proj / "scripts" / "ci-runner"
    runner.mkdir(parents=True, exist_ok=True)
    (runner / "manifest.ts").write_text(MANIFEST_TS, encoding="utf-8")
    (runner / "gates.lock.json").write_text(GATES_LOCK, encoding="utf-8")


def head_of(fix) -> str:
    return fix.git("rev-parse", "HEAD").stdout.strip()


def short_head_of(fix) -> str:
    return fix.git("rev-parse", "--short", "HEAD").stdout.strip()


def test_81_marker_init_asks_nothing_and_a_doc_only_fix_never_asks(wl):  # noqa: F811
    wl.say("done for now")
    wl.brief_now()
    marker = wl.reg_repo()
    wl.check("allow", "", "the first stop initialises the reggate marker silently")
    assert marker.is_file(), "no marker was written"
    assert '"head": "' in marker.read_text(encoding="utf-8"), "no marker was written"
    wl.fixcommit("docs/note.md", "fix: typo in the docs")
    wl.check("allow", "", "THE NAG CONTROL: a doc-only fix commit never asks")
    assert json.loads(marker.read_text(encoding="utf-8"))["head"] == head_of(wl), (
        "the marker did not advance past a skipped fix"
    )


def test_82_a_fix_covered_by_a_real_existing_gate_settles_once(wl):  # noqa: F811
    wl.say("done for now")
    wl.brief_now()
    marker = wl.reg_repo()
    (wl.proj / "package.json").write_text(PKG_REAL_GATE, encoding="utf-8")
    wl.run()
    wl.fixcommit("src.ts", "fix(cli): guard the empty ref")
    wl.shim_judge(
        judge_verdict(
            blind_spot="no check compared refs",
            existing_gate="check:ci-real",
            recurring=True,
        )
    )
    wl.checkj("allow", "settled as covered", "a REAL existing gate settles the fix-set as covered")
    assert '"verdict": "covered"' in marker.read_text(encoding="utf-8"), (
        "no covered verdict in the marker: %s" % marker.read_text(encoding="utf-8")[:300]
    )
    wl.checkj("allow", "", "a settled fix-set is NEVER re-asked")


def test_83_hallucinated_coverage_blocks_and_84_the_deferral_exit_settles_it(wl):  # noqa: F811
    """Bash cases 83 and 84 in one function, because 84 calls no `setup`: it reads the deferral token out of 83's block and spends it, so the sequence is the assertion.

    The `[?]` is then OUR deferred item, so the something-remains machinery (handover plus `## Remaining`) applies to that stop, exactly as in case 74 of the requests battery.
    """
    wl.say("done for now")
    wl.brief_now()
    wl.reg_repo()
    (wl.proj / "package.json").write_text(PKG_REAL_GATE, encoding="utf-8")
    wl.run()
    wl.fixcommit("src.ts", "fix: a real defect")
    wl.shim_judge(
        judge_verdict(
            blind_spot="uncovered path",
            existing_gate="check:ci-i-dreamed-this",
            recurring=True,
            instruction="write a gate",
        )
    )
    out = wl.runj().out
    assert '"decision": "block"' in out, "hallucinated coverage was not caught: %s" % out[:220]
    assert "HALLUCINATED" in out, "a nonexistent gate name was not called hallucinated"
    assert "ADD THE REGRESSION TEST" in out, "the block does not name the write-it exit"
    assert "REBUT" in out, "the block does not name the rebuttal exit"

    found = re.search(r"reggate:[0-9a-f]{8}", out)
    assert found, "no reggate token in the block"
    token = found.group(0)
    wl.add_item(
        "- [?] (deadbeef) %s should this be gated? DEFAULT: no gate, operator decides" % token
    )
    wl.hand_now()
    wl.say(
        "deferred the gate question to the operator\n\n## Remaining\n"
        "- the reggate deferral, waiting on the operator"
    )
    wl.checkj("allow", "settled as deferred", "the [?] deferral settles the fix-set")


def test_85_recurring_false_settles_as_one_off(wl):  # noqa: F811
    wl.say("done for now")
    wl.brief_now()
    wl.reg_repo()
    (wl.proj / "package.json").write_text(PKG_TRIVIAL_CI, encoding="utf-8")
    wl.run()
    wl.fixcommit("src.ts", "fix: pasted one wrong constant")
    wl.shim_judge(judge_verdict(blind_spot="typo with no invariant behind it"))
    wl.checkj("allow", "settled as one-off", "a one-off mistake warrants no gate and settles")


def test_86_proof_a_new_gate_wired_transitively_and_green_settles_as_proven(wl):  # noqa: F811
    wl.say("done for now")
    wl.brief_now()
    marker = wl.reg_repo()
    (wl.proj / "package.json").write_text(
        '{"name":"p","version":"0.0.0","scripts":{"ci":"npm run check:ci-batch",'
        '"check:ci-batch":"npm run check:ci-newgate",'
        '"check:ci-newgate":"bash .ci/scripts/quality/check-newgate.sh"}}\n',
        encoding="utf-8",
    )
    wl.run()
    wl.fixcommit("src.ts", "fix: the recurring defect")
    quality = wl.proj / ".ci" / "scripts" / "quality"
    quality.mkdir(parents=True, exist_ok=True)
    (quality / "check-newgate.sh").write_text("#!/bin/bash\nexit 0\n", encoding="utf-8")
    wl.shim_judge(
        judge_verdict(
            blind_spot="nothing asserted the invariant",
            recurring=True,
            gate_needed=True,
            gate_proven=True,
            instruction="gate written",
        )
    )
    wl.checkj(
        "allow", "settled as proven", "a wired (ci -> batch -> gate), green gate is the proof"
    )
    text = marker.read_text(encoding="utf-8")
    assert '"exit": 0' in text, "no cached gate run in the marker: %s" % text[:300]
    assert "check-newgate.sh" in text, "no cached gate run in the marker: %s" % text[:300]


def test_87_control_a_gate_defined_but_not_reachable_from_ci_does_not_prove(wl):  # noqa: F811
    """CONTROL, and the anti-substring control too: `ci` MENTIONS the key inside an echo, so a substring reachability test would wrongly pass this. Only `npm run` edges count."""
    wl.say("done for now")
    wl.brief_now()
    wl.reg_repo()
    (wl.proj / "package.json").write_text(
        '{"name":"p","version":"0.0.0","scripts":{"ci":"echo check:ci-newgate",'
        '"check:ci-newgate":"bash .ci/scripts/quality/check-newgate.sh"}}\n',
        encoding="utf-8",
    )
    wl.run()
    wl.fixcommit("src.ts", "fix: the recurring defect")
    quality = wl.proj / ".ci" / "scripts" / "quality"
    quality.mkdir(parents=True, exist_ok=True)
    (quality / "check-newgate.sh").write_text("#!/bin/bash\nexit 0\n", encoding="utf-8")
    wl.shim_judge(
        judge_verdict(
            blind_spot="nothing asserted the invariant",
            recurring=True,
            gate_needed=True,
            gate_proven=True,
            instruction="gate written",
        )
    )
    wl.checkj("block", "NOT reachable", "defined-but-never-run does not count as proof")


def test_88_a_corrupt_marker_is_forgotten_loudly_never_a_block(wl):  # noqa: F811
    wl.say("done for now")
    wl.brief_now()
    marker = wl.reg_repo()
    wl.run()
    marker.write_text("not json {{{\n", encoding="utf-8")
    wl.check("allow", "forgotten", "corruption re-initialises and reports, allowing the stop")
    json.loads(marker.read_text(encoding="utf-8"))


def test_89_a_judge_that_omits_regression_gate_on_a_fix_stop_fails_closed(wl):  # noqa: F811
    wl.say("done for now")
    wl.brief_now()
    wl.reg_repo()
    (wl.proj / "package.json").write_text(PKG_TRIVIAL_CI, encoding="utf-8")
    wl.run()
    wl.fixcommit("src.ts", "fix: something real")
    wl.shim_judge("")
    wl.checkj(
        "block",
        "no usable regression_gate",
        "a missing regression_gate on a fix-signal stop blocks",
    )


def test_90_ticks_are_the_uncommitted_tree_signal(wl):  # noqa: F811
    """A pre-existing tick is seeded, never asked about; a NEWLY ticked `[x]` is a fix signal even with no commit.

    The new tick line carries a real short sha as evidence, else I7 blocks before the reggate settle is ever reached.
    """
    wl.say("done for now")
    wl.brief_now()
    marker = wl.reg_repo()
    wl.add_item("- [x] (deadbeef) an old already-done item")
    wl.shim_judge(judge_verdict(blind_spot="x"))
    wl.checkj("allow", "", "init with a pre-existing tick asks nothing")
    assert '"fixsets": {}' in marker.read_text(encoding="utf-8"), (
        "init asked about an old tick: %s" % marker.read_text(encoding="utf-8")[:300]
    )
    wl.add_item("- [x] (deadbeef) fixed the parser crash on empty input, %s" % short_head_of(wl))
    wl.checkj(
        "allow", "settled as one-off", "a NEWLY ticked [x] is a fix signal even with no commit"
    )


def test_91_control_a_manifest_id_citation_that_does_not_exist_still_hallucinates(wl):  # noqa: F811
    """CONTROL: registration is what makes a citation real, so an id shaped like a manifest id but absent from the lock must still be caught."""
    wl.say("done for now")
    wl.brief_now()
    wl.reg_repo()
    (wl.proj / "package.json").write_text(PKG_RUNNER_CI, encoding="utf-8")
    write_manifest_and_lock(wl)
    wl.run()
    wl.fixcommit("src.ts", "fix: a real defect")
    wl.shim_judge(
        judge_verdict(
            blind_spot="uncovered path",
            existing_gate="gate-test:i-dreamed-this",
            recurring=True,
            instruction="write a gate",
        )
    )
    out = wl.runj().out
    assert '"decision": "block"' in out, "a nonexistent manifest id was not caught: %s" % out[:220]
    assert "HALLUCINATED" in out, "a manifest id that is not registered did not hallucinate"


def test_92_a_fix_covered_by_a_real_gate_test_manifest_id_settles(wl):  # noqa: F811
    """`npm run ci` runs it through the runner rather than through a `check:*` key, and that has to count."""
    wl.say("done for now")
    wl.brief_now()
    marker = wl.reg_repo()
    (wl.proj / "package.json").write_text(PKG_RUNNER_CI, encoding="utf-8")
    write_manifest_and_lock(wl)
    wl.run()
    wl.fixcommit("src.ts", "fix(cli): guard the empty ref")
    wl.shim_judge(
        judge_verdict(
            blind_spot="no check compared refs",
            existing_gate="gate-test:real-thing",
            recurring=True,
        )
    )
    wl.checkj(
        "allow",
        "settled as covered",
        "a REAL gate-test:* manifest id settles as covered",
    )
    assert '"verdict": "covered"' in marker.read_text(encoding="utf-8"), (
        "the manifest-id citation was not recorded as covered: %s"
        % marker.read_text(encoding="utf-8")[:300]
    )


def test_93_a_fix_covered_by_a_file_path_citation_settles(wl):  # noqa: F811
    """The citation is a PATH with a `::test_name` qualifier, not the manifest id: the shape a human or the judge actually reaches for, and the shape 91 and 92 do not cover, since they only prove the id-keyed lookup."""
    wl.say("done for now")
    wl.brief_now()
    marker = wl.reg_repo()
    (wl.proj / "package.json").write_text(PKG_RUNNER_CI, encoding="utf-8")
    (wl.proj / ".ci" / "scripts" / "test" / "gates").mkdir(parents=True, exist_ok=True)
    write_manifest_and_lock(wl)
    wl.run()
    wl.fixcommit("src.ts", "fix(cli): guard the empty ref")
    wl.shim_judge(
        judge_verdict(
            blind_spot="no check compared refs",
            existing_gate=(".ci/scripts/test/gates/test-real-thing.sh::test_the_specific_case"),
            recurring=True,
        )
    )
    wl.checkj(
        "allow",
        "settled as covered",
        "a FILE-PATH::test_name citation resolves to the real gate and settles as covered",
    )
    assert '"verdict": "covered"' in marker.read_text(encoding="utf-8"), (
        "the path-shaped citation was not recorded as covered: %s"
        % marker.read_text(encoding="utf-8")[:300]
    )


def test_94_control_a_file_path_that_is_not_a_real_gates_run_still_hallucinates(wl):  # noqa: F811
    """CONTROL: without this, case 93 would pass for a probe that accepts any string containing a slash."""
    wl.say("done for now")
    wl.brief_now()
    wl.reg_repo()
    (wl.proj / "package.json").write_text(PKG_RUNNER_CI, encoding="utf-8")
    write_manifest_and_lock(wl)
    wl.run()
    wl.fixcommit("src.ts", "fix: a real defect")
    wl.shim_judge(
        judge_verdict(
            blind_spot="uncovered path",
            existing_gate=".ci/scripts/test-i-dreamed-this.sh::test_x",
            recurring=True,
            instruction="write a gate",
        )
    )
    out = wl.runj().out
    assert '"decision": "block"' in out, (
        "a nonexistent path citation was not caught: %s" % out[:220]
    )
    assert "HALLUCINATED" in out, "a path that matches no gate's run: did not hallucinate"


def test_95a_the_gate_maintenance_hint_is_artifact_derived_and_never_skips(wl):  # noqa: F811
    """WHY THIS EXISTS, measured 2026-09-04/05 across TWO sessions independently.

    Writing gate A produced the finding that gate B was needed (A's own selftest tail tripped `check:ci-shape-duplication`; A's new file tripped `check:ci-gate-manifest` leaf-tracked), and fixing B produced C. Roughly 8 rounds in one session and 3 in a peer's, each costing a full CI cycle on a PR that was already green, reviewed and threads-resolved. EVERY one of those findings had
    already been caught by an existing gate, so the correct verdict was `covered` naming that gate, but nothing told the judge it was looking at gate machinery. `gate_only_fixset` is that signal, read from `git diff-tree` and never from a commit subject.

    IT IS A HINT, NOT A SKIP, and that is the assertion that matters most here: a gate-maintenance fix can still deserve a gate of its own, so this must never suppress a fix-set. The last assertion below is what proves it, and it needs `shim_judge` plus `checkj` rather than a bare `check`: without a shimmed verdict there is no judge answer at all, so the stop simply ALLOWS, which
    is how the first three versions of this assertion passed for the wrong reason and then failed for the right one.
    """
    # say + brief_now BEFORE reg_repo: without them the first stop blocks on "session brief is missing" and never reaches the reggate surface, so the final assertion would pass on the wrong block.
    wl.say("done for now")
    wl.brief_now()
    wl.reg_repo()
    # A package.json with a real `ci` key, then marker init, in that order. The marker initialises on the FIRST stop at whatever HEAD it finds, so commits made before it are already behind it and never read as fix signals, which is why the final assertion came back `allow` and proved nothing until this line existed.
    (wl.proj / "package.json").write_text(PKG_REAL_GATE, encoding="utf-8")
    wl.run()

    reggate = wlfix.import_wl("wl_reggate")

    def gate_only(sha: str) -> bool:
        return reggate.gate_only_fixset(str(wl.proj), [sha])

    wl.fixcommit("scripts/gates/check-thing.ts", "fix(gate): a gate artifact")
    sha_gate = head_of(wl)
    wl.fixcommit("packages/cli/src/real.ts", "fix(cli): product code")
    sha_prod = head_of(wl)
    wl.fixcommit("agent/d1589e0b/STATE.md", "fix(state): bookkeeping only")
    sha_book = head_of(wl)

    assert gate_only(sha_gate) is True, "a gate-artifact fix-set was not recognised"
    # CONTROL: product code must NOT be called gate maintenance, or the hint would be appended to every fix-set and say nothing.
    assert gate_only(sha_prod) is False, "CONTROL: product code was called gate maintenance"
    # CONTROL: bookkeeping ALONE is not gate maintenance either. agent/ and docs/ are ignored when they accompany real files, but a fix-set that is nothing else has no gate artifact in it and must not earn the hint.
    assert gate_only(sha_book) is False, (
        "CONTROL: a bookkeeping-only fix-set was called gate maintenance"
    )
    # CONTROL: an unreadable ref fails toward saying NOTHING, never toward skipping.
    assert gate_only("0" * 40) is False, "CONTROL: a bad ref did not fail toward silence"

    wl.shim_judge(
        judge_verdict(
            blind_spot="gate machinery had no guard",
            recurring=True,
            gate_needed=True,
            instruction="write the gate",
        )
    )
    wl.checkj(
        "block",
        "A FIX LANDED",
        "a gate-maintenance fix STILL asks; the hint informs, it does not skip",
    )


def test_96_a_ticks_evidence_is_its_closing_note_not_the_whole_accumulated_history(wl):  # noqa: F811
    """Found live: item 4954f598 blocked roughly 10 consecutive stops although its own closing note carried a real, resolving sha.

    `rec["text"]` accumulates every lease/update note an item ever received, forever; a handful of leases carrying worker-id-shaped hex notes (17-20 chars) outrank a real 9-char commit sha under the evidence scan's "5 longest hex candidates" rule, so the real sha never gets tried. The fix is scope, not the scan: I7 must see the tick's own closing note, not its whole history.
    """
    reggate = wlfix.import_wl("wl_reggate")
    checks = wlfix.import_wl("wl_checks")
    store = wlfix.import_wl("wl_store")
    wl.reg_repo()
    wl.fixcommit("src.ts", "fix: a real defect")
    real_sha = short_head_of(wl)
    stamp = "2026-09-22T08:00:00Z"
    events: list[dict[str, object]] = [
        {
            "ev": "add",
            "id": "poison1",
            "at": stamp,
            "by": wlfix.ME,
            "s": " ",
            "o": wlfix.ME,
            "t": "a tick whose history will grow long",
        },
    ]
    # Several leases, each carrying a worker-id-shaped note LONGER than the real sha below -- the exact shape that outranked it live.
    events.extend(
        {
            "ev": "lease",
            "id": "poison1",
            "at": stamp,
            "by": wlfix.ME,
            "until": stamp,
            "worker": worker,
            "note": "leased to worker:%s" % worker,
            "worker_verified": True,
        }
        for worker in (
            "af61cd805486b8e9f",
            "a6f203ba2d1dad4df",
            "a3eb1f38776140810",
            "a2e744ce62808099b",
            "aef4695176ce25a76",
        )
    )
    events.append(
        {
            "ev": "state",
            "id": "poison1",
            "at": stamp,
            "by": wlfix.ME,
            "s": "x",
            "note": "%s committed: a real defect fixed" % real_sha,
        }
    )
    with wl.events.open("a", encoding="utf-8") as handle:
        for ev in events:
            handle.write(json.dumps(ev) + "\n")

    fold = store.load(wl.wl, sync=False)
    rec = fold.by_id["poison1"]
    assert len(rec["line"]) > 250, "fixture did not accumulate a long enough history: %r" % (
        rec["line"],
    )
    # CONTROL: the full accumulated line, scanned alone, still misses the real sha -- pins the underlying "5 longest hex candidates" fragility so this fixture cannot silently stop testing anything.
    assert checks.completion_evidence(str(wl.proj), rec["line"]) is False, (
        "CONTROL: the full accumulated history unexpectedly carried recognisable evidence"
    )

    state = {"head": head_of(wl), "seen_ticks": [], "fixsets": {}, "gate_runs": {}}
    _descs, _ids, ticks, _head, _banked = reggate.fix_signals(
        str(wl.proj), fold.items, wlfix.ME, state
    )
    assert len(ticks) == 1, "the poisoned tick was not surfaced as a fix signal: %r" % (ticks,)
    _tid, _line, evidence_text = ticks[0]
    assert evidence_text == rec["lastnote"], (
        "evidence_text did not carry the tick's own closing note: %r" % (evidence_text,)
    )
    assert checks.completion_evidence(str(wl.proj), evidence_text) is True, (
        "the real sha in the closing note was not recognised once scoped to it alone"
    )


def test_p27_every_obligation_the_verdict_fired_rides_the_gate_block(wl):  # noqa: F811
    """agent/plans/PLAN-stop-hook-continuity.md P2.7. A verdict whose regression gate blocks AND whose class sweep fired (written into reason/next_action by `wl_rules.apply_order`) used to emit the gate payload alone, so the sweep came back one judged stop later. CONTROL: before the fix the sweep's search is absent from the block."""
    wl.say("done for now")
    wl.brief_now()
    wl.reg_repo()
    (wl.proj / "package.json").write_text(PKG_REAL_GATE, encoding="utf-8")
    wl.run()
    wl.fixcommit("src.ts", "fix: a real defect")
    wl.shim_judge(
        judge_verdict(
            blind_spot="uncovered path",
            existing_gate="check:ci-i-dreamed-this",
            recurring=True,
            instruction="write a gate",
        )
    )
    shim = wl.base / "binonly" / "claude"
    payload = json.loads(json.loads(shim.read_text(encoding="utf-8").split("echo ", 1)[1]))
    payload["structured_output"].update(
        {
            "verdict": "continue",
            "reason": "CLASS SWEEP: the fix touched one call site of a repeated shape",
            "next_action": "git grep -n 'sibling_call(' src/",
        }
    )
    shim.write_text("#!/bin/bash\necho %s\n" % json.dumps(json.dumps(payload)), encoding="utf-8")
    out = wl.runj().out
    assert '"decision": "block"' in out, out[:300]
    assert "HALLUCINATED" in out, out[:600]
    assert "ALSO OWED ON THIS FIX-SET" in out, out[-900:]
    assert "sibling_call(" in out, out[-900:]


def test_p27_inverse_a_stop_verdict_adds_nothing(wl):  # noqa: F811
    wl.say("done for now")
    wl.brief_now()
    wl.reg_repo()
    (wl.proj / "package.json").write_text(PKG_REAL_GATE, encoding="utf-8")
    wl.run()
    wl.fixcommit("src.ts", "fix: a real defect")
    wl.shim_judge(
        judge_verdict(
            blind_spot="uncovered path",
            existing_gate="check:ci-i-dreamed-this",
            recurring=True,
            instruction="write a gate",
        )
    )
    out = wl.runj().out
    assert "HALLUCINATED" in out, out[:600]
    assert "ALSO OWED ON THIS FIX-SET" not in out, out[-900:]
