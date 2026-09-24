#!/usr/bin/env python3
"""Control for completion_evidence's citation scan, BOTH directions.

Separate from test-worklist-v5.sh on purpose. That harness drives the whole hook against a fixture repo whose files I cannot cite, and its evidence section is a deliberately sequenced fixture: an earlier attempt to add these cases inline truncated the shared worklist file and broke the two SHA tests that string-replace a line it had just deleted. A control that damages the suite it
joins is not a control. This calls the function directly against the REAL repo, where a resolving path is knowable.

The bug: completion_evidence delegated to citation_state, which uses CITE_RE.search and therefore judges only the FIRST citation in a line. A tick carrying four resolving full paths read as evidence-free because a bare "05-docs-and-decommission.md" happened to come first.
"""

import atexit
import importlib.util
import inspect
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import wl_checks as W
import wl_claimcheck as CC
import wl_classsweep as CS

# A PRIVATE TMPDIR FOR THE WHOLE RUN, removed at exit. The ledgers under test take a flock sidecar at `$TMPDIR/claude-worklist/.judge/<ledger>-<sha1 of the ledger path>.lock`, and every fixture here is a fresh random directory, so each run left new lock files in the machine-wide /tmp that nothing removed. The code under test reads TMPDIR at call time, so pointing it here keeps those sidecars, and every other temp directory this suite makes, inside one directory deleted at exit.
_PRIVATE_TMP = tempfile.mkdtemp(prefix="completion-evidence-suite-")
atexit.register(shutil.rmtree, _PRIVATE_TMP, ignore_errors=True)
os.environ["TMPDIR"] = _PRIVATE_TMP
tempfile.tempdir = _PRIVATE_TMP

ROOT = pathlib.Path(__file__).resolve().parents[3]

# The submodule's OWN current HEAD, computed live rather than hardcoded: a submodule sha is a real object, but only inside its own git database, never in ROOT's. This resolved to False before wl_checks.py grew a per-submodule fallback (found live 2026-09-23 ticking real, verified private/renet work whose only cited sha kept failing this check).
_SUBMODULE_SHA = subprocess.run(
    ["git", "-C", str(ROOT / "private" / "renet"), "rev-parse", "HEAD"],
    capture_output=True,
    text=True,
    check=False,
).stdout.strip()

# A path that really exists in this repo, so "resolving" means resolving.
REAL = ".claude/hooks/stop/wl_checks.py:1"

MUST_PASS = [
    (
        "a typo'd first citation must not hide a resolving one",
        f"cites bare-filename.md:12 first, then {REAL}",
    ),
    ("a single resolving citation is evidence", f"fixed it, see {REAL}"),
    # Root dotfiles, 2026-09-06. 22 of 24 tracked root dotfiles were uncitable because CITE_RE demanded a `.<ext>` suffix; that set is every allowlist and blocklist this repo suppresses through, so the tick that most needs a record was the one that could not leave one.
    ("an extensionless root dotfile resolves", "drained an entry, see .gitignore:9"),
    # RE-KEYED 2026-09-06, and the re-key is the finding. This case cited `.dead-bash-allowlist:19`, a root allowlist that W4's policy move (b80552370) relocated to `.ci/policy/.dead-bash-allowlist`. Nothing about CITE_RE changed, but the control went red and stayed red, so `test-hooks.sh` exited 1 at HEAD for a reason unrelated to any hook. A control keyed on a path that another
    # workstream is allowed to move is a control that reports its own staleness as a defect in the thing it guards.
    #
    # `.ci-trigger` is now the ONLY hyphenated extensionless root dotfile the tree has (`git ls-files | grep -E '^\.[A-Za-z0-9_]+-[A-Za-z0-9_-]*$'` returns exactly it), and W4 P0 keeps it at the root deliberately, so it is the one subject the no-slash branch of CITE_RE can still be driven against.
    (
        "a hyphenated root dotfile resolves",
        "re-armed the trigger at .ci-trigger:1",
    ),
]

if _SUBMODULE_SHA:
    MUST_PASS.append(
        ("a real submodule-only sha resolves", "fixed private/renet %s" % _SUBMODULE_SHA)
    )

MUST_FAIL = [
    ("no citation at all is not evidence", "I finished it, all good"),
    ("one fabricated path is not evidence", "see totally/made/up/file.ts:99"),
    (
        "several citations, none resolving, is not evidence",
        "cites nowhere/at/all.md:12 and also other/fake.ts:7",
    ),
    # The dotfile branch must still RESOLVE, or it would turn any dotted prose token into evidence. This is the control that keeps that branch honest.
    ("a fabricated root dotfile is not evidence", "see .no-such-allowlist:4"),
    # A fabricated hex string must still fail even now that submodule roots are also checked -- the per-submodule fallback adds a search location, never a looser match.
    ("a fabricated sha is not evidence even with submodule roots checked", "fixed deadbee1"),
]


def main() -> int:
    bad = []
    for name, text in MUST_PASS:
        if not W.completion_evidence(ROOT, text):
            bad.append(f"MUST PASS but did not: {name}")
    for name, text in MUST_FAIL:
        if W.completion_evidence(ROOT, text):
            bad.append(f"MUST FAIL but passed: {name}")
    if bad:
        print(f"✗ completion_evidence: {len(bad)} control failure(s)")
        for b in bad:
            print(f"    {b}")
        return 1
    print(
        f"✓ completion_evidence: {len(MUST_PASS)} pass-cases, {len(MUST_FAIL)} fail-cases "
        "(scanning every citation did not make everything pass)"
    )
    return 0


# =============================================================================
# v22: the deferred-finding detector and the sweep prompt
# =============================================================================
# Added 2026-08-26 after an operator had to ask, by hand, for the findings a session had reported and not fixed. The pre-existing `found, not fixed` gate matched ONE phrase at line-lead; every near-synonym the session actually used walked past it.
#
# Collects failures and RETURNS a code, matching main() above -- no bare `assert`, which ruff's S101 forbids in this tree and which would also vanish under `python -O`.


def _wl():
    spec = importlib.util.spec_from_file_location(
        "wl_checks_t", pathlib.Path(__file__).resolve().parent / "wl_checks.py"
    )
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


# The REAL phrasings, verbatim from the session that escaped the old gate.
MUST_HIT = [
    "- Reported, not fixed (not my file): rsv_sentinel_exists cannot tell.",
    "- Agent finding I didn't fix: the orphan parser.",
    "- Findings in code I do not own -- not fixed, reported.",
    "- I have not fixed the stale comment yet.",
]

# Must NOT fire on prose ABOUT the rule: a gate that cannot survive being written about is too broad, and this very file quotes its own triggers.
MUST_MISS = [
    "- This line says `found, not fixed` in backticks and is prose.",
    '- The message said "reported, not fixed" in quotes.',
    "- A totally normal line about progress.",
    "- Everything is fixed and verified.",
]


def _extra():
    w = _wl()
    bad = []
    bad.extend(
        f"MISSED a deferred finding: {line!r}" for line in MUST_HIT if not w.deferred_findings(line)
    )
    bad.extend(f"FALSE POSITIVE on: {line!r}" for line in MUST_MISS if w.deferred_findings(line))
    # CONTROL: it must be able to return nothing, or MUST_HIT would pass against a function that simply echoes its input.
    if w.deferred_findings("") or w.deferred_findings("plain text, no admission"):
        bad.append("control failed: the detector fires on text with no admission")

    # The sweep prompt keys on idle_stall's early-return TEXT. The first version looked for "closed", a word that string never contains, so the prompt could never have fired. Pin the coupling: change the sentence and this goes red rather than the prompt going silently off.
    sentinel = "an item left the open state this turn"
    if sentinel not in inspect.getsource(w.idle_stall):
        bad.append("idle_stall's early-return text changed; the sweep prompt would go vacuous")
    if "left the open state" not in sentinel:
        bad.append("the sweep condition substring no longer matches its sentinel")

    if bad:
        print(f"✗ deferred-finding/sweep: {len(bad)} failure(s)")
        for b in bad:
            print(f"    {b}")
        return 1
    print(
        f"ok  deferred-finding detector: {len(MUST_HIT)} hit, {len(MUST_MISS)} missed, "
        "control fired; sweep sentinel still matches"
    )
    return 0


# =============================================================================
# The stub-hop bug: cited_excerpts read the pre-move path raw and handed the judge an empty quote for exactly the citations that survived a plan move. PLAN-stop-hook-task-verification.md section 1.3 measured 9 of 186 resolving citations across the real worklist (4.8%) hit this, all plan-stub paths.
# =============================================================================


def _stub_fixture(tmp):
    """Build a synthetic plan-move stub plus its target under `tmp`.

    The stub-hop tests used to point straight at the real `agent/PLAN-tooling-transformation.md`, one of the 103 one-time historical flat-layout stubs from the `a81967e94` migration. The 2026-09-22 cleanup deletes every one of those (the operator's "no leftovers" call, tracked in PLAN-plan-path-migration.md), so the tests cannot depend on that file surviving.

    Picking a different real stub to depend on would just relocate the same fragility. This builds its own disposable pair in a tempdir instead: a five-line pointer with the exact `Status: moved` / `Moved-To:` shape `wl_store.plan_stub_target` looks for, plus a target long enough for line 495 to stay in range.
    The ongoing close-time `_done`/`_removed` stub convention (agent/README.md) is untouched; this fixture only stops the test caring which repo file plays the role.
    """
    root = pathlib.Path(tmp)
    stub = root / "agent" / "PLAN-tooling-transformation.md"
    target = root / "agent" / "plans" / "PLAN-tooling-transformation.md"
    stub.parent.mkdir(parents=True, exist_ok=True)
    target.parent.mkdir(parents=True, exist_ok=True)
    stub.write_text(
        "# PLAN: Tooling Transformation (moved)\n"
        "Status: moved\n"
        "Moved-To: agent/plans/PLAN-tooling-transformation.md\n"
        "\n"
        "This plan moved. Fixture stub for the stub-hop tests.\n"
    )
    target.write_text("\n".join("placeholder line %d" % n for n in range(1, 600)) + "\n")
    return str(root)


def _stub():
    bad = []
    # The live pair the plan named: a real stub, a real in-range line into the five-line pointer, past-EOF for the stub but in-range for the moved file.
    stub_cite = "agent/PLAN-tooling-transformation.md:495"

    with tempfile.TemporaryDirectory() as tmp:
        fixture_root = _stub_fixture(tmp)

        excerpt = W.cited_excerpts(fixture_root, f"see {stub_cite}")
        if not excerpt.strip():
            bad.append("cited_excerpts returned empty for a citation through a plan-move stub")
        elif "agent/plans/PLAN-tooling-transformation.md" not in excerpt:
            bad.append(f"excerpt did not resolve through the stub hop: {excerpt!r}")

        ok, detail = W.citation_state(fixture_root, f"see {stub_cite}")
        if not ok:
            bad.append(f"citation_state stopped resolving the stub citation: {detail}")
        elif "agent/plans/" not in detail:
            bad.append(f"citation_state resolved but not through the stub hop: {detail}")

        # CONTROL: a line genuinely out of range even after the hop stays skipped, not resolved through a second one -- check:ci-plan-folders F5 forbids a stub that points at a stub.
        oor = W.cited_excerpts(fixture_root, "see agent/PLAN-tooling-transformation.md:99999999")
        if oor.strip():
            bad.append(
                f"an out-of-range line past the moved file's own end still excerpted: {oor!r}"
            )

    # CONTROL: an ordinary, non-stub citation must be unaffected by the hop.
    plain_excerpt = W.cited_excerpts(ROOT, f"see {REAL}")
    if not plain_excerpt.strip():
        bad.append("cited_excerpts regressed on an ordinary, non-stub citation")

    # PIN: the coupling that made the two functions drift in the first place. One reads `citation_state` used to hop and `cited_excerpts` did not; a future edit reintroducing a private hop in either one un-shares them.
    src_cs = inspect.getsource(W.citation_state)
    src_ce = inspect.getsource(W.cited_excerpts)
    if "_resolve_cite_path" not in src_cs:
        bad.append("citation_state no longer calls the shared stub-hop resolver")
    if "_resolve_cite_path" not in src_ce:
        bad.append(
            "cited_excerpts no longer calls the shared stub-hop resolver -- the bug this pins"
        )

    if bad:
        print(f"✗ stub-hop (cited_excerpts/citation_state): {len(bad)} failure(s)")
        for b in bad:
            print(f"    {b}")
        return 1
    print(
        "ok  stub-hop: cited_excerpts and citation_state share one resolver, both directions checked"
    )
    return 0


# =============================================================================
# The claim check: a citation that RESOLVES and does not demonstrate the claim. PLAN-stop-hook-task-verification.md section 3.3 names the live instance -- item b328b9d3 ticked citing a plan line about something the line does not mention, and every existing check behaved identically to a citation that did support it.
# =============================================================================

# The real shape from section 3.3, verbatim enough to stay recognisable: a real plan path, a real in-range line reached through the plan-move stub, and a claim about a token that line does not carry.
ADVERSARIAL = (
    "Explore agent re-verified all 8 boxes live: W7P4-Q "
    "(agent/PLAN-tooling-transformation.md:495, GITHUB_AUTOPILOT_APP_ID unset)"
)
# The spelling the citation resolves TO, after the stub hop.
MOVED = "agent/plans/PLAN-tooling-transformation.md"


def _claim():
    bad = []

    # ADVERSARIAL cites the same synthetic stub-hop pair _stub() builds -- see _stub_fixture's docstring for why this cannot point at the real, now-deleted agent/PLAN-tooling-transformation.md any more.
    with tempfile.TemporaryDirectory() as tmp:
        fixture_root = _stub_fixture(tmp)

        # THE CASE THIS MODULE EXISTS FOR: it resolves, and git says the fix-set never touched it.
        untouched = CC.profile(fixture_root, ADVERSARIAL, ["packages/cli/src/index.ts"])
        if untouched["shape"] != CC.UNTOUCHED:
            bad.append(
                f"the adversarial tick profiled as {untouched['shape']!r}, not resolved-untouched"
            )
        if [c["verdict"] for c in untouched["citations"]] != [CC.UNTOUCHED]:
            bad.append(
                f"per-citation verdicts were {[c['verdict'] for c in untouched['citations']]}"
            )
        if not untouched["citations"] or not untouched["citations"][0]["excerpt"].strip():
            bad.append(
                "the cited line was not quoted at all, so the judge would be handed an empty block"
            )
        section = CC.prompt_section(untouched)
        if CC.CLAIM_MARKER not in section:
            bad.append(
                "the prompt section carries no marker, so judge_schema_for would never require the object"
            )
        if MOVED not in section or "resolved-untouched" not in section:
            bad.append("the prompt section names neither the resolved path nor the mismatch")

        # CONTROL, and without it the case above passes against a function that flags everything: the SAME claim, against a fix-set that really did touch the cited file, must not be flagged.
        touched = CC.profile(fixture_root, ADVERSARIAL, [MOVED, "packages/cli/src/index.ts"])
        if touched["shape"] != CC.RESOLVED:
            bad.append(f"a citation to a file the fix-set touched profiled as {touched['shape']!r}")

        # CONTROL: the PRE-MOVE spelling counts as touched too. The fix-set names whichever path the session actually edited, and comparing only the resolved spelling would report a file it did touch as untouched.
        pre_move = CC.profile(fixture_root, ADVERSARIAL, ["agent/PLAN-tooling-transformation.md"])
        if pre_move["shape"] != CC.RESOLVED:
            bad.append(
                f"the pre-move spelling was not recognised as touched: {pre_move['shape']!r}"
            )

    # VACUITY, per wl_classsweep's precedent and check_plan_boxes.py G-A6: a check that cannot see must SAY it cannot see, never report a clean profile.
    for label, text, fixset in (
        ("no citation, empty fix-set", "done, exit 0", []),
        ("no citation, unknown fix-set", "finished, run id 1234567890", None),
        ("a decorative hex that is no object", "landed as deadbeef", []),
    ):
        vac = CC.profile(ROOT, text, fixset)
        if vac["shape"] != CC.VACUOUS:
            bad.append(f"{label} profiled as {vac['shape']!r}, not unverifiable-shape")
        if "nothing checkable" not in CC._render(vac):
            bad.append(f"{label} rendered a profile that does not say it saw nothing")
    if "could not be made at all" not in CC._render(CC.profile(ROOT, "done, exit 0", [])):
        bad.append(
            "an absent fix-set list is not stated, so the comparison reads as made and passed"
        )

    # An unreadable tree: every git call fails and every path is absent, which must still be unverifiable-shape rather than an exception or a clean answer.
    with tempfile.TemporaryDirectory() as tmp:
        nogit = CC.profile(tmp, ADVERSARIAL, [])
        if nogit["shape"] != CC.VACUOUS:
            bad.append(f"an unreadable tree profiled as {nogit['shape']!r}")

    # No claim at all asks nothing. A commit-only fix-set has no completion claim, and a rule that fires on everything is a rule that gets skimmed.
    if CC.prompt_section(CC.profile(ROOT, "", [])) != "":
        bad.append("a fix-set with no tick behind it still produced a prompt section")

    # PIN: ADVISORY, NEVER BLOCKING, asserted against the module's own source rather than against its behaviour on one input. The decision is in the docstring and a docstring cannot fail; this can.
    src = inspect.getsource(CC)
    # THE CALL, not the name. The module's own docstring names `wl_rules.apply_order` when it records the graduation criterion -- the one route by which this rule may ever start blocking -- so a bare-name search would red on the sentence that documents the decision it is pinning.
    if "apply_order(" in src:
        bad.append(
            "wl_claimcheck calls wl_rules.apply_order -- the advisory decision has been reversed"
        )
    if re.search(r"""["']decision["']""", src):
        bad.append("wl_claimcheck writes a `decision` key, which is how this hook blocks")
    # CONTROL ON THE PIN ITSELF: both searches must be able to hit, or they pin nothing. wl_classsweep really does call apply_order, and a `decision` key really does appear in the driver.
    if "apply_order(" not in inspect.getsource(CS):
        bad.append(
            "the apply_order search found nothing in a module that calls it -- the pin is vacuous"
        )
    if not re.search(r"""["']decision["']""", inspect.getsource(W)):
        bad.append(
            "the decision-key search found nothing in the driver that emits one -- the pin is vacuous"
        )
    if "wl_rules.Demand" not in src:
        bad.append("the latch is gone, so an unsettled claim could be asked on every stop forever")

    # THE LATCH, driven rather than grepped. A fix-set the regression gate keeps BLOCKING returns on every stop, and this is the only thing that stops the claim question riding along with it forever -- the failure mode two plans in this hook have already paid for.
    with tempfile.TemporaryDirectory() as tmp:
        latch, sig = pathlib.Path(tmp) / "claimcheck.json", "abcdef123456"
        dem = CC.demand_for(sig)
        if CC.exhausted(sig, latch):
            bad.append("a fix-set nobody has asked about reads as already exhausted")
        dem.bank({"sig": sig}, dem.peek(latch), latch)
        if CC.exhausted(sig, latch):
            bad.append("one ask exhausted the latch, so the question could never be repeated")
        dem.bank({"sig": sig}, dem.peek(latch), latch)
        if not CC.exhausted(sig, latch):
            bad.append("the latch never exhausts, so an unsettled claim would be asked forever")

    # The verdict reader: a missing or malformed object degrades, never raises, and never touches the verdict.
    out = {"verdict": "stop", "reason": "r"}
    if CC.apply_verdict(out, None)[0] != "degraded":
        bad.append("a missing claim_check object did not degrade")
    if (
        CC.apply_verdict({"verdict": "stop", "claim_check": {"supported": "maybe"}}, None)[0]
        != "degraded"
    ):
        bad.append("an out-of-enum `supported` did not degrade")
    answered = {
        "verdict": "stop",
        "claim_check": {"supported": "no", "why": "w", "instruction": "i"},
    }
    kind, note = CC.apply_verdict(answered, untouched)
    if kind != "no" or "supported=no" not in note:
        bad.append(f"a `no` verdict did not surface as one: {kind!r} {note[:80]!r}")
    if answered["verdict"] != "stop":
        bad.append("apply_verdict mutated the judge's verdict -- this object may not block")

    # The census: the graduation criterion is answerable only from rows, so a census that writes nothing is the whole rule going quietly advisory forever.
    with tempfile.TemporaryDirectory() as tmp:
        CC.census(tmp, {"sig": "abc", "kind": "no", "shape": CC.UNTOUCHED})
        written = pathlib.Path(CC.census_path(tmp))
        if not written.exists() or "resolved-untouched" not in written.read_text():
            bad.append("the claim-check census wrote no readable row")

    if bad:
        print(f"✗ claim-check: {len(bad)} failure(s)")
        for b in bad:
            print(f"    {b}")
        return 1
    print(
        "ok  claim-check: the adversarial resolved-untouched tick fires, a touched citation "
        "does not, three vacuity shapes report they saw nothing, and the never-blocks pin holds"
    )
    return 0


# THE ENTRYPOINT IS LAST ON PURPOSE. It used to sit mid-file, so the cases appended below it never ran and the suite still exited 0 -- a test that cannot fail, caught only because its own output never appeared.
if __name__ == "__main__":
    sys.exit(main() or _extra() or _stub() or _claim())
