"""Port of `.ci/scripts/test/gates/test-gate-anti-vacuity.sh`.

META-GATE: a validator that PASSES when given nothing is broken by definition.

WHY THIS EXISTS. This repo accumulated about twelve quality gates that were green because they could not fail. Two root patterns, both reproducible by simply removing the input:

  1. Dead path constant. The tree a gate walked was deleted (PR #513 removed
     packages/web, packages/desktop, packages/e2e). The glob returned zero files,
     the gate iterated zero times, and printed a checkmark.
     `check-www-only-translations.ts` compared two empty sets for months.
  2. Assertion disabled when its input is absent. Guarding the real assertion
     behind `if (existsSync(DIR))` means the assertion never runs in an
     environment where DIR is gitignored -- e.g. the R2-hosted tutorial audio
     tree, whose per-file check has never once executed in CI.

Both collapse to one testable property: point the validator at an EMPTY tree and it must exit NON-ZERO, complaining that its input is missing. If it exits 0, it is asserting nothing and its green run in CI means nothing.

REGISTRY POLICY. The registry below is explicit and hand-verified, NOT auto-discovered. Auto-discovery would sweep in generators, one-shot scripts and validators whose input genuinely is optional, producing exactly the kind of noise that gets a gate suppressed. Add a validator here only after confirming by hand that "no input" is a real failure for it rather than a legitimate
no-op.

TWO REGISTRIES ARE TWO ANSWERS TO ONE QUESTION, so this port does not simply carry a second copy and hope. `test_the_registry_agrees_with_the_twins` parses the twin's array and requires the SETS to be equal. Without it the two lists would drift silently -- each side judging its own -- and a validator dropped from one would still look covered because the other still names it. That
control is the port's, not the twin's, and it exists because the port created the hazard.

WHY THIS MODULE OPTS IN TO THE REAL-TREE GROUP. `gates.lock.json` records `mutex: ["tree:repo"]` for `gate-test:gate-anti-vacuity`: three cases PLANT a file inside `scripts/` or `.ci/scripts/` and remove it again, and every registry case copies `scripts/`, `.ci/scripts/` and `.ci/rediacc_ci/` while another gate may be
walking them. `REAL_TREE_TWIN = True` buys the serialisation, and it is honoured
only because this module declares no `XDIST_GROUP` of its own.

THE PLANTED FIXTURES ARE PID-KEYED for the reason `run-all.sh` records about the `.gate-paths-exist` pair: this schedule serialises the writer tests WITHIN one battery, but two batteries (two sessions in one tree) collide on a fixed fixture name, each cleanup deleting the other's file, which reads as "the detector is broken" rather than as a collision.
"""

import os
import pathlib
import shutil

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

BASH_TWIN = ".ci/scripts/test/gates/test-gate-anti-vacuity.sh"

# Three cases plant inside the tracked tree and every registry case copies it.
REAL_TREE_TWIN = True

# The 42 registry entries each cost a fixture copy plus one gate invocation, and several of those gates are `npx tsx`. Measured 2026-09-09 on this tree; the default 600s would be tight if half a dozen more entries land.
TWIN_TIMEOUT = 900

ROOT = paths.repo_root()

# REGISTRY -- one entry per line: `(<script>, <expected substring>)`. The substring pins the DIAGNOSTIC, not just the exit code: a validator that fails for an unrelated reason (a crashed import, a missing dependency) is not evidence that it detects a missing input.
#
# `.sh` and `.py` entries are repo-root-relative; `.ts` entries are relative to `scripts/`. TRANSCRIBED FROM THE TWIN, and kept equal to it by `test_the_registry_agrees_with_the_twins`.
REGISTRY: tuple[tuple[str, str], ...] = (
    ("check-translation-hashes.ts", "locale"),
    ("check-translation-completeness.ts", "locale"),
    # The probe gate's subject is a single library file. Against an empty tree that file is absent, and "nothing to check" must be a FAILURE: a liveness gate that silently passes when it cannot reach the probe would recreate the very class it exists to catch (a check that cannot tell absent from present). It also refuses when python3 is missing, because its control listener could
    # not fire.
    (".ci/scripts/quality/check_account_probes.py", "nothing to check"),
    # NOT registered: .ci/scripts/quality/check-drill-verdicts.sh. Its sibling above IS, and the asymmetry is real rather than an oversight. The probe gate's subject is .ci/lib/account.sh, which this harness's fixture does NOT copy, so an empty tree genuinely starves it. The drill-verdict gate's subject is scripts/drills/lib.sh, and the fixture DOES copy scripts/ -- so on the
    # "empty" tree its subject is present, all four verdict assertions run for real, and it correctly exits 0. Registering it asserted that a gate must fail when its input exists, which is backwards; the meta-gate caught exactly that on the first run. Its own missing-subject branch is real but unreachable from here. Against an empty tree every oracle is unavailable, so the run is
    # vacuous and must FAIL rather than report "every entry is still load-bearing".
    ("check-suppression-liveness.ts", "vacuous"),
    # A mutation gate: it copies packages/cli into a sandbox, breaks the source, and requires the tests to fail. On an empty tree there is nothing to mutate, and "no source to mutate" must be a hard error - a mutation gate that reports success having mutated nothing is the purest form of the
    # class this meta-gate exists to catch.
    ("check-guard-mutations.ts", "required subject missing"),
    # A bash gate, reachable only since this harness learned to run .sh. It used to `exit 0` when private/renet was absent, silently taking govulncheck, deadcode and golangci-lint with it.
    (".ci/scripts/private/run-renet.sh", "required"),
    # Same submodule, same failure mode: with private/renet absent it would run `go test` over nothing and report that the licence tier map covers the
    # function registry. The CLI now derives its licence-issuance class from
    # that map, so a vacuous green here would launder a console defect too.
    (".ci/scripts/quality/check_renet_tier_map.py", "required"),
    # REPOINTED 2026-09-08 BY THE W7 P4 CUTOVER, both entries above and below. These pins name a gate BY PATH, and after a cutover the path names the twin rather than the registered gate. Nothing goes red when that happens: the harness keeps exercising the .sh, keeps passing, and silently stops covering the thing CI actually runs. Found by the batch-4 writer for tier-map; the types
    # entry is the same defect left behind by batch 3 and was swept here. Same shape again: `require_submodule ... || exit 0` becomes a hard fail
    # under CI=true (which this harness sets), so an empty tree is a loud
    # "required in CI but missing" rather than a green diff of nothing.
    (".ci/scripts/quality/check_renet_types.py", "required"),
    # Python lint. Against an empty tree `git ls-files` enumerates nothing and `ruff check` with no paths exits 0 -- indistinguishable from a clean repo, which is the exact shape this harness exists to catch. The input floor is therefore checked BEFORE the linter is even resolved, so the empty-tree failure is about VACUITY and not about a missing binary: an absent ruff would be an
    # ENVIRONMENT failure wearing a vacuity failure's exit code, and pinning that would assert nothing about the gate.
    (".ci/scripts/quality/check_python_lint.py", "VACUOUS INPUT"),
    # Same shape, different subject: against an empty tree `git ls-files` returns no JS/TS at all and the detector would report "no inline Python" over zero files -- indistinguishable from a clean repo. The MIN_FILES floor turns that into a loud refusal. Its own detector controls run first and abort separately, so a control failure cannot masquerade as this one.
    (".ci/scripts/quality/check_inline_python.py", "VACUOUS INPUT"),
    # Against an empty tree there are no locale files at all, so every comparison is over an empty set and the gate would exit 0 reporting that every value matches. The MIN_PAIRS floor turns that into a loud refusal.
    (".ci/scripts/quality/check_i18n_value_types.py", "VACUOUS INPUT"),
    # Against an empty tree there is no baseline file and no workflow, so every headroom comparison is over an empty set and the gate would exit 0 while having compared nothing -- indistinguishable from full coverage. Both the missing-file path and the too-few-jobs floor say VACUOUS INPUT.
    (".ci/scripts/quality/check_job_timeout_headroom.py", "VACUOUS INPUT"),
    # Against an empty tree there is no .gitmodules, so nothing is declared and every completeness comparison is over an empty set -- which would read exactly like "all submodules present". The MIN_SUBMODULES floor refuses.
    (".ci/scripts/quality/check_scope_completeness.py", "VACUOUS INPUT"),
    # Against an empty tree there is no .claude/settings.json, so no hook command is parsed and every reference check is over an empty set -- which reads exactly like "every hook resolves". The MIN_COMMANDS floor refuses.
    (".ci/scripts/quality/check_hooks_resolvable.py", "VACUOUS INPUT"),
    # Against an empty tree there are no workflows, so no secret is referenced and the gate would report that every reference is reachable. The MIN_REFERENCES floor turns that into a loud refusal.
    (".ci/scripts/quality/check_actions_allowlist.py", "VACUOUS INPUT"),
    (".ci/scripts/quality/check_plan_housekeeping.py", "VACUOUS INPUT"),
    (".ci/scripts/quality/check_plan_boxes.py", "VACUOUS INPUT"),
    (".ci/scripts/quality/check_syncpack_sources.py", "VACUOUS INPUT"),
    (".ci/scripts/quality/check_secret_reachability.py", "VACUOUS INPUT"),
    (".ci/scripts/quality/check_bws_map.py", "refusing to pass vacuously"),
    # Against an empty tree the probe locale file is absent, so no rule set can be resolved at all and the gate would otherwise report that zero enabled rules are healthy -- which is what a healthy repo looks like too.
    (".ci/scripts/quality/check_lint_rule_liveness.py", "VACUOUS INPUT"),
    # Against an empty tree there is no .claude/agents at all, so every reachability assertion is over an empty corpus and the gate would exit 0 reporting that every agent is reachable -- which is what a healthy corpus looks like too. The missing-directory path and the MIN_AGENTS floor both say VACUOUS INPUT, and both are answered BEFORE wl_agents is imported: the fixture has no
    # .claude/hooks either, so an unguarded import would exit non-zero for an environment reason wearing a vacuity failure's exit code.
    (".ci/scripts/quality/check_agent_hint_liveness.py", "VACUOUS INPUT"),
    # An empty tree tracks no js/ts at all, so "every file reaches a linter" is trivially true over zero files -- indistinguishable from full coverage.
    (".ci/scripts/quality/check_lint_scope_coverage.py", "VACUOUS INPUT"),
    # NOT registered here: .ci/breakpoint/scripts/check-breakpoint-drift.sh. This harness's fixture copies scripts/ and .ci/scripts/ but not .ci/breakpoint/, so the drift gate would fail with "No such file or directory" -- non-zero for a reason that has nothing to do with vacuity, which is precisely the false signal the REGISTRY POLICY above warns about. Its missing-manifest
    # behaviour is proven in test-breakpoint-portability.sh instead, where an isolated copy of the folder genuinely exists. NOT registered here either: .ci/scripts/quality/check-autopilot-no-bypass.sh. Its sibling check-autopilot-workflow-invariants.sh IS registered below, and the asymmetry is deliberate rather than an oversight. That one reads the workflow tree, so an empty
    # fixture makes it vacuous and it must say so. This one never touches the tree at all: it is three `gh api` calls against the live ruleset (:52, :71). An empty-tree run would exit non-zero on the absent GITHUB_AUTOPILOT_APP_ID, which is an ENVIRONMENT failure wearing a vacuity failure's exit code, and pinning it would assert nothing about the gate.
    # Verified live instead, 2026-07-30: with GITHUB_AUTOPILOT_APP_ID=4409539 it exits 0
    # and reports ruleset 12344707 bypass actors [RepositoryRole:5, Integration:2772000] with autopilot absent, which is the property it exists to defend. The harness fixture copies scripts/ and .ci/scripts/ but nothing that REFERENCES them (no workflows, no docs, no allowlist), so the gate must report the resulting orphans loudly rather than pass. The "ZERO shell files" guard
    # covers the stricter case of no shell tree at all.
    ("check-dead-bash.ts", "dead shell symbol"),
    # Both of its checks walk .github/workflows. The empty tree has no workflow YAML, so every invariant it asserts is over an empty set. It used to `exit 0` on a missing directory, which meant renaming the workflow tree would silently retire the gate.
    (".ci/scripts/security/check-workflow-gates.sh", "blind"),
    # The empty tree has no package.json and no .github/workflows, so there is no gate census on either side and every one of its seven assertions would be over an empty set. It replaced check-ci-chain-parity.ts and check-gate-reachability.ts, which were registered here separately for the same property; both are gone.
    ("check-ci-parity.ts", "Refusing to run"),
    # The scope engine's workflow closure is computed by ITERATING `uses: ./.github/workflows/*` at runtime, never by matching names, so the test asserts a real closure over the real tree. On the empty fixture that
    # closure is {} and the assertion must fail: registering it pins the fact
    # that moving or renaming the workflow tree cannot silently turn the closure test into a tautology over an empty set.
    (".ci/scripts/test/gates/test-scope-engine.sh", "closure"),
    # A DIFF gate with no baseline and no ledger measures nothing, and "measured nothing" must never read as "found nothing". Against the empty fixture both its inputs are gone, so it must refuse to run. Its first draft did the opposite: a wrong ledger path made the protected set empty, so it reported OK on a planted fabrication. Only a control caught that.
    ("check-locale-only-edits.ts", "Refusing to run"),
    ("check-jq-boolean-default.ts", "Refusing to run"),
    (".ci/scripts/security/check-autopilot-workflow-invariants.sh", "INVARIANT-FAIL"),
    # Its DOCS_DIR is a hardcoded path constant, so this is root pattern 1 verbatim: point it at a tree without packages/www/src/content/docs and the glob returns zero files, every loop iterates zero times, and it printed "All external links are valid". Measured on the empty fixture before the guard was added, not inferred from reading it.
    ("check-external-links.ts", "Refusing to run"),
    # Root pattern 1 with a baseline bolted on, which makes it worse: with the locale trees absent it finds zero contamination AND every one of its 379 baselined findings looks fixed, so an unguarded version would either print a checkmark or fail for the wrong reason. It must refuse instead.
    ("check-locale-de-contamination.ts", "Refusing to run"),
    # Its sibling, and root pattern 1 again: three hardcoded locale-root constants, so a tree without any of them made it walk zero locales and print a checkmark. It was NOT registered here while it carried a second, subtler vacuity inside itself -- `if (!STOPWORDS[locale]) continue` silently skipped ar/ja/ko/ru/zh/et, which is how 379 German values lived in account-web's
    # ar/ja/ru/zh under a green gate. That skip is now a hard error naming the locale, so the only way left to make this gate assert nothing is to take its input away -- which is exactly what this entry pins.
    ("check-i18n-cross-locale.ts", "Refusing to run"),
    # The eight www-simplification gates, plus the untranslated-text gate whose skip this replaced. EVERY ONE of them is root pattern 1 or 2 by construction -- each walks a hardcoded packages/www path -- so an empty tree is the exact shape that would make them print a checkmark over nothing. check-docs-untranslated-text.ts is the reason this block exists: it used to `exit 0` with
    # "Docs directory not found, skipping", which is pattern 2 verbatim, and it was ALSO proven dead in the other direction (a wholly English paragraph in a German doc exited 0). A gate can be vacuous by having no input and vacuous by having no detector, and this repo has now paid for both.
    ("check-docs-untranslated-text.ts", "Refusing to run"),
    ("check-em-dash-surfaces.ts", "Refusing to run"),
    ("check-locale-config-divergence.ts", "Refusing to run"),
    ("check-dead-translation-keys.ts", "Refusing to run"),
    ("check-layout-overflow.ts", "Refusing to run"),
    ("check-hydration-clean.ts", "Refusing to run"),
    ("check-form-validation.ts", "Refusing to run"),
    # These two read packages/www/dist rather than the source tree. Their refusal is the difference between them and check:ci-seo's built-HTML scan, which SELF-SKIPS without a dist and has therefore been vacuous on every developer machine for its whole life.
    ("check-anchor-integrity.ts", "Refusing to run"),
    ("check-client-bundle-budget.ts", "Refusing to run"),
    # NOT registered here: .ci/scripts/test/gates/test-skip-plan-reconcile.sh. Measured, not assumed: it passes all 55 assertions against the empty tree, because it is a pure unit test that builds every fixture it needs (its plans and job lists are constructed in-test, and it reads scope-map only
    # for the job-key list, which .ci/scripts carries into the fixture). Passing
    # with the repo absent is CORRECT for it rather than vacuous, so an entry
    # here could never fail and would be exactly the dead assertion this harness exists to catch. Its anti-vacuity controls are inline instead.
    #
    # NOT registered here either: .ci/scripts/test/gates/test-scope-baseline-attest.sh,
    # for the same reason and measured the same way: all 75 assertions pass
    # against the empty tree (exit 0), because it too builds every fixture it needs. It drives the real createRepoIo with an INJECTED `run`, so it makes no git call, no gh call and no network call; the only repo files it reads are the three .ci/scripts/ci/*.cjs modules this harness copies in anyway. Passing with the source tree absent is CORRECT for it, so an entry here would
    # assert nothing. Its controls are inline instead, one per planted defect, plus three engine mutants run by hand during authoring (drop the `delete plan.reconciled`, drop the cheap-first mode gate, restore the one-green-run-per-sha pick) each of which flips a different case red.
    #
    # NOT registered here either: .ci/scripts/test/gates/test-scope-gate-outputs.sh, measured the same way and with the same result: all 6 cases pass against the empty tree (exit 0). It BUILDS the tree it needs -- it copies .ci/scripts/ci into a temp dir, `git init`s a repository there with the branch shape a baseline walk requires, and shims `gh` on PATH -- so the only repo input
    # it has is the .ci/scripts/ tree this harness copies in anyway. It reads no packages/, no private/, no .github/. Passing with the source tree absent is CORRECT for it, so an entry here could never fail. Its controls are inline, one per case, and the emitter control was proven
    # by a planted defect during authoring (suppress the run_*=false push in
    # scope-shadow.sh's emitter and case (a) goes red naming the dead emitter;
    # restore and it goes green). That same planted defect also caught a defect in the TEST: collecting the lines before the control check made the failing run exit silently with an empty log, which is a right exit code and a dead diagnostic. The control now runs first.
    #
    # NOT registered here either: .ci/scripts/test/gates/test-watchdog-supersession.sh, and the same measurement was taken rather than reasoned: all 9 assertions pass against the empty tree (exit 0). Its only repo dependency is .ci/scripts/ci/watchdog-monitor.cjs, which this harness copies in, and every input to the decision under test is a literal in the test itself. Passing with
    # the source tree absent is CORRECT for it, so an entry here could never fail. Its controls are inline and were proven by hand during authoring: relaxing the predicate to drop `noFailures` flips "a real failure is never laundered as supersession" red, and relaxing
    # `newerRunExists === true` to `Boolean(newerRunExists)` flips
    # "newerRunExists is compared strictly" red. Both directions were run, not assumed. Its sibling test-watchdog-schedule-exemption.sh is unregistered on the same grounds.
)


def run_against_empty_tree(script: str) -> harness.RunResult:
    """Execute `script` with the tooling trees copied into an otherwise empty directory, so every `__dirname/../packages/...` and `__dirname/../private/...` lookup resolves to nothing.

    COPYING (rather than deleting the real trees) is what makes this safe to run against a working tree holding other sessions' uncommitted work.

    `.ci/scripts` IS IN THE COPY LIST, and it is not a convenience: without it the harness could only ever test `scripts/*.ts`, which excluded about thirty shell gates -- and the worst real instance of a vacuous gate lived in one of them (`.ci/scripts/private/run-renet.sh` used to exit 0, silently taking govulncheck, deadcode and golangci-lint with it).

    `.ci/rediacc_ci` IS ALSO IN IT, and that one is load-bearing in a subtler way. The CI programs are moving into that Python package, so gates start with `import rediacc_ci`. Copy only `scripts/` and `config/` and every one of them dies in here with `ModuleNotFoundError` -- which arrives as a NON-ZERO EXIT AND A MESSAGE ABOUT A MISSING INPUT, i.e. indistinguishable from the gate
    correctly rejecting an empty tree. This harness would then report every such gate as healthy while testing nothing about it. `test_fixture_can_import_package` is the control that keeps that line honest.

    `CI=true` on purpose: a gate is being judged on what it does IN CI, and some
    deliberately soften to a warning locally.
    """
    with harness.temp_dir() as tmp:
        shutil.copytree(ROOT / "scripts", tmp / "scripts", symlinks=True)
        (tmp / ".ci").mkdir(parents=True, exist_ok=True)
        shutil.copytree(ROOT / ".ci" / "scripts", tmp / ".ci" / "scripts", symlinks=True)
        for optional in ("config", "rediacc_ci"):
            source = ROOT / ".ci" / optional
            if source.is_dir():
                shutil.copytree(source, tmp / ".ci" / optional, symlinks=True)
        # node_modules resolution walks upward from the script, so link the real one in; the point of the fixture is an empty SOURCE tree, not a broken runtime.
        (tmp / "node_modules").symlink_to(ROOT / "node_modules")

        env = {"CI": "true"}
        if script.endswith(".sh"):
            argv = [harness.require_tool("bash", "install bash"), script]
        elif script.endswith(".py"):
            argv = [harness.require_tool("python3", "install python3"), script]
        else:
            # The else-branch used to be the ONLY alternative to `.sh`, which silently resolved any new language to `scripts/<path>` and failed as a stale-registry error rather than as an unsupported one -- the first `.py` entry hit exactly that. Two homes, in step with the twin and with `registry_path` above: after W9 P2 a `.ts` validator lives under `scripts/gates/`. Resolved
            # against the COPY, not the repo, because that is what this process will execute. Fixing only `registry_path` and leaving this on the old home is exactly what broke `test_validator_rejects_empty_tree` here on 2026-09-09 while the twin passed -- one resolver moved and its pair did not.
            rel = "scripts/gates/%s" % script
            if not (tmp / rel).is_file():
                rel = "scripts/%s" % script
            argv = [
                harness.require_tool("npx", "install node; tsx is resolved through npx"),
                "tsx",
                rel,
            ]
        return harness.run(argv, cwd=tmp, env=env, timeout=600)


def registry_verdict(script: str, needle: str) -> str | None:
    """None when `script` correctly rejects an empty tree, else why not.

    A SEPARATE FUNCTION so `test_harness_catches_a_vacuous_validator` can drive the identical code path against a planted validator instead of a lookalike.
    """
    result = run_against_empty_tree(script)
    if result.rc == 0:
        return "%s exited 0 on an EMPTY tree -- it asserts nothing (vacuous gate)\n%s" % (
            script,
            result.combined,
        )
    # Case-insensitive: the diagnostic must be about the missing input.
    if needle.lower() not in result.combined.lower():
        return (
            "%s failed on an empty tree, but its message never mentions '%s' -- it may be "
            "crashing for an unrelated reason\n%s" % (script, needle, result.combined)
        )
    return None


def registry_path(script: str) -> pathlib.Path:
    """Where a registry entry's file lives.

    `.sh` and `.py` are repo-root-relative. A `.ts` lives under `scripts/gates/` OR `scripts/`, and BOTH are tried in step with the twin: W9 P2 moved 125 gate bodies into `scripts/gates/` on 2026-09-09 while this resolver hard-coded the old home, so every moved validator read as a stale registry entry -- a staleness check reporting staleness it had caused itself. Trying both is not
    a weakening; an entry present in NEITHER still resolves to the `scripts/` path and fails, which is the real finding.
    """
    if script.endswith((".sh", ".py")):
        return ROOT / script
    gated = ROOT / "scripts" / "gates" / script
    return gated if gated.is_file() else ROOT / "scripts" / script


def twin_registry() -> list[tuple[str, str]]:
    """The twin's REGISTRY array, parsed. See the module docstring on drift."""
    source = (ROOT / BASH_TWIN).read_text(encoding="utf-8").split("\n")
    start = source.index("REGISTRY=(")
    entries = []
    for line in source[start + 1 :]:
        if line == ")":
            break
        token = line.strip()
        if token.startswith('"') and token.endswith('"'):
            script, _, needle = token[1:-1].partition("|")
            entries.append((script, needle))
    return entries


# ---------------------------------------------------------------------------


def test_fixture_can_import_package(gate):
    """THE COPY LIST IS AN INPUT TO EVERY GATE RUN IN HERE, so it needs a control of its own.

    `import rediacc_ci` must work INSIDE the fixture; if it does not, a gate that uses the package fails here for a reason that has nothing to do with what the gate asserts, and that failure looks exactly like the empty-tree rejection this file is built to observe.

    RED-THEN-GREEN, run in that order rather than assumed: delete the `rediacc_ci` leg of the copy list in `run_against_empty_tree` and this case goes red with `ModuleNotFoundError: No module named 'rediacc_ci'`.

    The probe is planted under `.ci/scripts/` specifically because that is a directory the fixture copies -- a probe outside the copy list could not be run in there at all. And it must resolve to the fixture's OWN copy of the package rather than the repo's, or the case would stay green with the copy-list leg deleted; hence the last assertion.
    """
    probe_rel = ".ci/scripts/.rediacc-ci-import-probe.%d.py" % os.getpid()
    probe = ROOT / probe_rel
    probe.write_text(
        "import importlib\nimport os\nimport sys\n\n"
        "sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))\n"
        'mod = importlib.import_module("rediacc_ci")\n'
        'print("imported rediacc_ci from " + str(mod.__file__))\n',
        encoding="utf-8",
    )
    try:
        result = run_against_empty_tree(probe_rel)
    finally:
        # REMOVED IN A `finally`, and not left to a later line. Every assertion helper raises, and the twin's `trap ... RETURN` does NOT fire on the `exit 1` those helpers perform -- measured while proving this case can fail, the planted `.py` survived the red run and showed up in `git status` as an untracked file in a tree holding other sessions' work.
        probe.unlink(missing_ok=True)
    if result.rc != 0:
        gate.log_fail(
            "a gate run inside the fixture cannot import rediacc_ci (exit %d) -- add "
            ".ci/rediacc_ci to the copy list in run_against_empty_tree:\n%s"
            % (result.rc, result.combined)
        )
    gate.assert_contains(
        result.combined, "imported rediacc_ci from", "the probe must report the package it loaded"
    )
    # It must be the COPY. If this ever resolved to the repo root the case would be green with the copy-list leg deleted, which is the vacuity this whole file exists to police.
    gate.assert_not_contains(
        result.combined,
        str(ROOT / ".ci" / "rediacc_ci"),
        "the fixture must import its OWN copy of the package, not the repo's",
    )
    gate.log_pass("a gate run inside the empty-tree fixture can import rediacc_ci")


def test_fetch_retry_reads_every_file_type(gate):
    """PER-FILE-TYPE BLINDNESS: absence of matches is indistinguishable from success.

    `check:ci-fetch-retry` shipped 2026-09-01 reusing `run_blocks` from `check_dockerfile_mirror_resilience.py` -- a parser for Dockerfile RUN instructions -- over a corpus that is mostly shell. Measured: 25 blocks for the Dockerfile, ZERO for any `.sh`. It printed "551 file(s) scanned" and reported the tree clean while four real unretried fetches sat in `.devcontainer` shell
    scripts inside its own corpus. Every one of its ten controls passed, because they all fed it Dockerfile text.

    NOT the same claim as the REGISTRY check: that one proves a validator fails on an EMPTY tree, this proves it can SEE each kind of file it claims to read.

    DRIVEN THROUGH THE PARSER, not through a planted file. The gate's corpus comes
    from `git ls-files`, deliberately, so a fixture written to disk is invisible
    and a plant-based version of this control passes vacuously. That was the first cut, and it failed here rather than in CI.
    """
    python3 = harness.require_tool("python3", "install python3")
    program = (
        "import sys, os\n"
        "sys.path.insert(0, os.path.join(sys.argv[1], '.ci/scripts/quality'))\n"
        "import check_fetch_retry as G\n"
        "bare = 'curl -fsSL -o /tmp/x.tgz https://example.com/x.tgz'\n"
        "retried = 'curl -fsSL --retry 5 -o /tmp/x.tgz https://example.com/x.tgz'\n"
        "if len(G.logical_blocks(bare + chr(10), is_dockerfile=False)) == 0:\n"
        "    sys.exit('shell yields ZERO blocks; the parser is blind to it')\n"
        "if len(G.offences_in(bare, is_dockerfile=False)) != 1:\n"
        "    sys.exit('a bare shell fetch was not reported')\n"
        "if len(G.offences_in(retried, is_dockerfile=False)) != 0:\n"
        "    sys.exit('a retried shell fetch was wrongly reported')\n"
        "if len(G.offences_in('RUN ' + bare, is_dockerfile=True)) != 1:\n"
        "    sys.exit('the Dockerfile path stopped working')\n"
    )
    result = harness.run([python3, "-c", program, str(ROOT)], cwd=ROOT, timeout=300)
    if result.rc != 0:
        gate.log_fail(
            "fetch-retry gate cannot read shell scripts: %s"
            % (result.err.strip() or result.out.strip())
        )
    gate.log_pass("fetch-retry gate reads shell, not just Dockerfiles (both directions)")


def test_sharedselftestcases_can_fail(gate):
    """THE SHARED CONTROL PROVIDER, proved capable of going false.

    `scripts/lib/shrink-only-baseline.ts` exports `sharedSelftestCases()`, and NINE gates run its cases as their own controls. Nothing proved those cases can go false: if the provider ever returned an all-passing set -- a refactor that stubs `baselineAdditions`, a short-circuit -- all nine gates would keep printing PASS while asserting nothing, at once.

    THE PLANT IS ON THE FUNCTION THE CASES ARE COMPUTED FROM, not on the cases: a provider that hardcoded `ok: true` would survive any assertion about its shape.
    """
    npx = harness.require_tool("npx", "install node; tsx is resolved through npx")
    guard = ROOT / "scripts" / "lib" / "shrink-only-baseline.ts"
    work = ROOT / "scripts" / (".shrink-only-baseline-fixture.%d.ts" % os.getpid())
    probe = ROOT / "scripts" / (".shared-cases-probe.%d.ts" % os.getpid())
    try:
        source = guard.read_text(encoding="utf-8")
        needle = "export const baselineAdditions = ("
        if needle not in source:
            gate.log_fail(
                "CONTROL COULD NOT PLANT: %s no longer spells baselineAdditions as an "
                "exported arrow, so the mutation would leave the file unchanged"
                % paths.relative_to_root(guard)
            )
        work.write_text(
            source.replace(
                needle,
                "export const baselineAdditions = ((..._a: unknown[]) => [])  as unknown as "
                "typeof _unused_orig; const _unused_orig = (",
                1,
            ),
            encoding="utf-8",
        )
        # PROVE THE PLANT LANDED. A no-op substitution produces an identical file and the control then passes against unmutated source -- a green that proves nothing.
        if work.read_text(encoding="utf-8") == source:
            gate.log_fail("CONTROL COULD NOT PLANT: the mutation left the guard unchanged")
        probe.write_text(
            'import { sharedSelftestCases } from "./%s";\n'
            "const c = sharedSelftestCases();\n"
            "console.log(`n=${c.length} failing=${c.filter((x) => !x.ok).length}`);\n"
            % work.name[: -len(".ts")],
            encoding="utf-8",
        )
        result = harness.run([npx, "tsx", str(probe)], cwd=ROOT, timeout=600)
    finally:
        work.unlink(missing_ok=True)
        probe.unlink(missing_ok=True)
    if result.rc != 0:
        gate.log_fail(
            "the shared-cases probe did not run (exit %d) -- this meta-control asserts "
            "nothing:\n%s" % (result.rc, result.combined)
        )
    gate.assert_not_contains(
        result.combined,
        "failing=0",
        "sharedSelftestCases() must go FALSE when its computation is broken",
    )
    gate.assert_not_contains(
        result.combined, "n=0", "an empty case set would make all nine consumers vacuous"
    )
    gate.log_pass("sharedSelftestCases() reports failures when its computation is broken")


def test_runcontrols_can_fail(gate):
    """THE SHARED-HARNESS META-CONTROL.

    `scripts/lib/controls.ts` `runControls()` is the one loop 35 gates are being moved onto, which makes it a shared point of failure: if it ever passes silently, every gate on it goes blind AT ONCE. So the harness must be proved capable of failing before anything depends on it, and that proof lives here rather than in the harness's own selftest, where a broken harness would be
    grading itself.

    Three assertions, because two of them are the ways this could go quietly wrong: a failing case must return non-zero, an all-passing set must return zero (or the "proof" is satisfied by a function that always fails), and an EMPTY set must return non-zero (a case-builder that silently returns [] would otherwise get a clean 0).
    """
    npx = harness.require_tool("npx", "install node; tsx is resolved through npx")
    fixture = ROOT / "scripts" / (".controls-harness-fixture.%d.ts" % os.getpid())
    try:
        fixture.write_text(
            "import { runControls } from './lib/controls.js';\n"
            "const planted = runControls([\n"
            "  { name: 'this one passes', ok: true },\n"
            "  { name: 'THE PLANT: this one must be counted', ok: false, detail: 'planted' },\n"
            "]);\n"
            "const clean = runControls([{ name: 'this one passes', ok: true }]);\n"
            "const empty = runControls([]);\n"
            "console.log(`planted=${planted} clean=${clean} empty=${empty}`);\n",
            encoding="utf-8",
        )
        result = harness.run([npx, "tsx", str(fixture)], cwd=ROOT, timeout=600)
    finally:
        fixture.unlink(missing_ok=True)
    if result.rc != 0:
        gate.log_fail(
            "the controls-harness fixture did not run (exit %d) -- the meta-control asserts "
            "nothing:\n%s" % (result.rc, result.combined)
        )
    gate.assert_contains(
        result.combined, "planted=1", "runControls must COUNT a failing control, not pass it"
    )
    gate.assert_contains(
        result.combined, "clean=0", "runControls must return 0 when every control passes"
    )
    gate.assert_contains(
        result.combined, "empty=1", "an empty control set verified nothing and must not return 0"
    )
    gate.assert_contains(
        result.combined, "THE PLANT", "the failing control's name must reach the operator"
    )
    gate.log_pass("runControls counts a planted failure, an empty set, and a clean set")


def test_harness_catches_a_vacuous_validator(gate):
    """CONTROL: prove this file can FAIL.

    A synthetic validator that ignores its input and exits 0 -- the exact shape of the bugs being policed -- must be reported. Without this, a harness that silently never asserts would look identical to a clean run.
    """
    name = ".gate-anti-vacuity-fixture.%d.ts" % os.getpid()
    fixture = ROOT / "scripts" / name
    try:
        fixture.write_text(
            'console.log("locale check passed");\nprocess.exit(0);\n', encoding="utf-8"
        )
        why = registry_verdict(name, "locale")
    finally:
        fixture.unlink(missing_ok=True)
    if why is None:
        gate.log_fail(
            "harness must reject a validator that exits 0 on an empty tree, and it did not"
        )
    gate.assert_contains(str(why), "asserts nothing", "failure message must name the vacuity")
    gate.log_pass("harness catches a vacuous validator (control case)")


def test_registry_is_not_empty(gate):
    """Control for this file itself: an empty registry would make every assertion below vacuous -- the precise failure mode being policed."""
    if not REGISTRY:
        gate.log_fail("REGISTRY is empty -- this meta-gate would assert nothing")
    gate.log_pass("registry holds %d validator(s)" % len(REGISTRY))


def test_registry_entries_exist(gate):
    stale = [script for script, _needle in REGISTRY if not registry_path(script).is_file()]
    if stale:
        for script in stale:
            gate.log_error(
                "registry names %s, which does not exist -- the registry has gone stale"
                % paths.relative_to_root(registry_path(script))
            )
        gate.log_fail("%d registry entr(y/ies) name a file that is not there" % len(stale))
    gate.log_pass("every registered validator exists (%d)" % len(REGISTRY))


def test_validator_rejects_empty_tree(gate):
    """THE REGISTRY LOOP, one case rather than 42, and the difference is only in the report: every entry is driven and every failure is named, instead of the twin's exit-on-first."""
    if not REGISTRY:
        gate.log_fail("REGISTRY is empty, so this loop compared nothing")
    problems = []
    for script, needle in REGISTRY:
        if not registry_path(script).is_file():
            # Named rather than skipped. A registry entry pointing at a missing file has NOT been checked, and `test_registry_entries_exist` above is the case that owns that finding -- but folding it into "fine" here would let this loop report a clean sweep over a short corpus.
            problems.append(
                "%s: the registered file does not exist, so it was NOT checked" % script
            )
            continue
        why = registry_verdict(script, needle)
        if why:
            problems.append(why)
    if problems:
        for problem in problems:
            gate.log_error(problem)
        gate.log_fail(
            "%d of %d registered validator(s) do not reject an empty tree"
            % (len(problems), len(REGISTRY))
        )
    gate.log_pass("all %d registered validator(s) reject an empty tree" % len(REGISTRY))


def test_the_registry_agrees_with_the_twins(gate):
    """ADDED BY THE PORT, because the port is what created the hazard.

    Two hand-maintained registries are two answers to one question, and the expensive half is that both look right: a validator dropped from one still looks covered because the other names it. Set equality, both directions, with the difference printed rather than a count.
    """
    theirs = twin_registry()
    if not theirs:
        gate.log_fail(
            "the twin's REGISTRY array parsed to nothing, so this comparison would admit "
            "any drift at all. Fix the reader before trusting the equality below."
        )
    mine, theirs_set = set(REGISTRY), set(theirs)
    only_here = sorted(mine - theirs_set)
    only_there = sorted(theirs_set - mine)
    if only_here or only_there:
        gate.log_fail(
            "the two registries have drifted: %d entr(y/ies) only in the port (%s), %d only "
            "in the twin (%s). They must name the same validators, or one side is judging a "
            "shorter list and reporting a clean sweep."
            % (len(only_here), only_here, len(only_there), only_there)
        )
    gate.log_pass("the port and the twin register the same %d validator(s)" % len(theirs))
