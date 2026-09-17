"""Port of `.ci/scripts/test/gates/test-suppression-liveness.sh`.

Integration test for `scripts/gates/check-suppression-liveness.ts`, the gate that asks
whether every allowlist / blocklist / override entry in this repo still suppresses
something that exists.

WHAT IT GUARDS. The `BLOCKER:` convention proves a reason EXISTS; it cannot prove
the reason is still TRUE. This gate closes the other half, and the twin's header
names the two receipts for why it has to be provable in BOTH directions:
`check_stale_entries` in `audit.sh` skipped the common staleness case for its whole
life, and `check-no-app-admin-perm.sh` was never wired into a job at all. A gate
that has only ever been seen to pass is indistinguishable from `true`.

EVERY FIXTURE CASE RUNS AGAINST A FIXTURE ROOT through `SUPPRESSION_LIVENESS_ROOT`,
so no tracked file is ever mutated. The working tree routinely holds uncommitted
work from other sessions, which is the reason the twin took that shape and the
reason this port keeps it.

WHY THIS MODULE OPTS IN TO THE REAL-TREE GROUP. `test_passes_on_real_repo` and the
added shape case drive the subject seam-free over the REAL repository: the probes
walk `.ci`, `scripts`, `.claude`, `.devcontainer`, `packages` and `private` for
shell scripts, shell out to `git ls-files`, and read the real `package.json`,
`package-lock.json` and eleven policy files. A battery step writing under any of
those mid-sweep is a divergence that would be blamed on this port.
`REAL_TREE_TWIN = True` buys the serialisation, and it is honoured only because
this module declares no `XDIST_GROUP` of its own; see `real_tree_admission` in
`test_twin_parity.py`.

THE SUBJECT DOES NOT SELF-SCAN THIS FILE, checked rather than assumed. The one
probe that walks `.ci` recursively is `dead-bash-allowlist`, and it collects only
names ending `.sh`; `dockerfileFetchTokens` reads `git ls-files` filtered to
`Dockerfile*`. Nothing in either corpus can match a `.py` file under
`.ci/rediacc_ci/tests/gates/`, so the fixture strings below are written out
literally rather than through the `%s` template treatment
`test_gate_label_references.py` owes its own self-scanning subject.

TWO DELIBERATE DIVERGENCES FROM THE TWIN, both narrower than they look.

1. NO EM DASH. The twin's preventive-override reason is
   `BLOCKER: preventive <em dash> guards against ...` and its PASS line quotes that
   spelling. The matcher is `/^BLOCKER:\\s*preventive\\b/i`
   (check-suppression-liveness.ts:842), so the dash is not load-bearing and this
   file uses a plain hyphen, which is what the house rule against em dashes in
   authored text requires.

2. `test_fires_on_dead_template_skiplist_entry` REFUSES A MISSING TEMPLATE TREE.
   The twin copies `packages/json/templates/` with `2>/dev/null || true`. If that
   tree were absent the probe's universe would be null, the probe would SKIP, the
   only entry in the fixture would be unchecked, and the run would exit 1 as
   VACUOUS -- satisfying the twin's `assert_exit_code 1` for a reason that has
   nothing to do with a dead skiplist entry. The port makes the missing tree a loud
   failure instead, so the case cannot pass by the wrong door.

ADDED BY THE PORT: `test_the_real_run_reports_a_non_trivial_corpus`. The twin's
real-repo case asserts exit 0 and the presence of the string `probes:`, which a
run that checked ZERO entries would also satisfy. The added case reads the probe
and entry counts out of the summary line and refuses a collapse, so the SHAPE of
the real sweep is visible on every run rather than only its verdict.
"""

import json
import os
import re
import shutil

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

BASH_TWIN = ".ci/scripts/test/gates/test-suppression-liveness.sh"

# test_passes_on_real_repo and test_the_real_run_reports_a_non_trivial_corpus both drive the subject over the real tree. See the docstring.
REAL_TREE_TWIN = True

SUBJECT_REL = "scripts/gates/check-suppression-liveness.ts"
SUBJECT = paths.from_root(*SUBJECT_REL.split("/"))

# `probes: 12 run, 0 skipped entries: 87 checked findings: 1 (0 fail, 1 warn)`
SUMMARY_RE = re.compile(r"probes: (\d+) run, (\d+) skipped\s+entries: (\d+) checked")

# Floors for the ADDED shape case only. Deliberately far under the live numbers (12 probes / 87 entries on 2026-09-08): this is a "the sweep still sweeps" refusal, not a ratchet, and a ratchet here would be a second source of truth for counts the policy files already own.
REAL_PROBE_FLOOR = 6
REAL_ENTRY_FLOOR = 20

# The four files make_fixture MUST have. Copied from the real tree because the
# probes' oracles are real manifests; a hand-written stub would make every
# liveness answer below a statement about the stub.
REQUIRED_SOURCES = (
    "package.json",
    "package-lock.json",
    ".github/workflows/ci.yml",
    ".github/actions/app-token/action.yml",
)

# Present in a full checkout, absent in one without the submodule. The twin guards each with `[[ -f ]]`, and so does this.
OPTIONAL_SOURCES = (
    "private/renet/Dockerfile",
    "private/renet/go.mod",
)


def require_subject(gate) -> str:
    """The subject and its interpreter, proved present before anything is claimed.

    A missing `npx` is a LOUD failure carrying the fix, never a skip: a case that
    could not run has not been checked, and unchecked folded into fine is the shape
    this directory refuses.
    """
    if not SUBJECT.is_file():
        gate.log_fail("subject under test is missing: %s" % SUBJECT_REL)
    return harness.require_tool(
        "npx", "install Node.js; the subject is a TypeScript program driven through tsx"
    )


def make_fixture(gate, root):
    """`make_fixture`: a repo that is healthy on every probe, for a case to bend one thing.

    ANTI-VACUITY, and it is the whole reason this is a function rather than four
    `cp` lines. A fixture missing one of its oracles does not make a probe report a
    finding, it makes the probe SKIP -- and a skipped probe answers every question
    below with silence that reads as agreement. So the four required sources are a
    loud failure when absent, naming which one.
    """
    for rel in REQUIRED_SOURCES:
        src = paths.from_root(*rel.split("/"))
        if not src.is_file():
            gate.log_fail(
                "the fixture cannot be built: %s is missing from the real tree, so every "
                "probe that reads it would SKIP and this case would assert nothing." % rel
            )
    for sub in (".github/workflows", ".github/actions/app-token", "private/renet", ".ci/policy"):
        (root / sub).mkdir(parents=True, exist_ok=True)
    for rel in REQUIRED_SOURCES:
        shutil.copyfile(paths.from_root(*rel.split("/")), root / rel)
    for rel in OPTIONAL_SOURCES:
        src = paths.from_root(*rel.split("/"))
        if src.is_file():
            shutil.copyfile(src, root / rel)
    return root


def run_gate(gate, root, *args: str) -> harness.RunResult:
    """`run_gate <root>`: the subject, from the repo root, pointed at a fixture.

    ACTION_REFS_MIN_FILES=2, NOT 0, carried verbatim from the twin and for its
    recorded reason: `make_fixture` plants exactly two `.github` files, while
    `collectActionRefs` carries a vacuity floor of 10 sized for the real tree --
    which threw VACUOUS here on 2026-09-05 and took the whole gate-test battery
    red. Telling the probe the fixture's TRUE corpus size keeps the floor
    meaningful (an empty or half-built fixture still refuses) instead of switching
    the guard off, which is what a 0 would do.

    The twin merges `2>&1`, so every caller reads `.combined`. That matters beyond
    fidelity: npm prints an `Unknown project config "minimum-release-age"` warning
    to stderr on every `npx` invocation in this repo, so a port reading only `.err`
    would be matching npm's noise.
    """
    npx = require_subject(gate)
    return harness.run(
        [npx, "tsx", SUBJECT_REL, *args],
        cwd=paths.repo_root(),
        env={
            "SUPPRESSION_LIVENESS_ROOT": os.fspath(root),
            "ACTION_REFS_MIN_FILES": "2",
        },
    )


def write_policy(root, name: str, body: str) -> None:
    (root / ".ci" / "policy" / name).write_text(body, encoding="utf-8")


def add_override(root, reason: str) -> None:
    """`ghost-pkg` in `overrides`, with `reason` in `_overridesReasons`.

    The twin shells out to `python3 - "$t" <<'PY'` for this because bash cannot
    edit JSON. A port already in Python edits it directly; that is the only
    difference, and the resulting manifest is the same one.
    """
    manifest = root / "package.json"
    data = json.loads(manifest.read_text(encoding="utf-8"))
    data.setdefault("overrides", {})["ghost-pkg"] = "^1.0.0"
    data.setdefault("_overridesReasons", {})["ghost-pkg"] = reason
    manifest.write_text(json.dumps(data, indent=2), encoding="utf-8")


def summary(gate, output: str) -> tuple[int, int, int]:
    """(probes run, probes skipped, entries checked) from the verdict line.

    A run with no summary line at all is a FAILURE. "exit 0" from a gate that
    printed nothing recognisable is not evidence that it checked anything, and
    treating it as such is precisely how a gate passes without running.
    """
    match = SUMMARY_RE.search(output)
    if not match:
        gate.log_fail(
            "the gate exited without printing its probe summary, so its verdict says "
            'nothing about what it checked. Output: "%s"' % output
        )
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


# ---------------------------------------------------------------------------


def test_passes_on_real_repo(gate):
    """THE REAL-TREE CASE. Real policy files, real manifests, real `git ls-files`,
    no seams. A FAIL-tier stale entry anywhere in the tree reds here."""
    npx = require_subject(gate)
    result = harness.run([npx, "tsx", SUBJECT_REL], cwd=paths.repo_root())
    gate.assert_exit_code(
        0,
        result.rc,
        "live tree should have no FAIL-tier stale entries (output: %s)" % result.combined,
    )
    gate.assert_contains(result.combined, "probes:", "prints a probe summary")
    gate.log_pass("passes clean on the real repository")


def test_the_real_run_reports_a_non_trivial_corpus(gate):
    """ADDED BY THE PORT. The twin's real-repo case is satisfied by a run that
    checked ZERO entries, because `probes:` is printed either way. This reads the
    counts out of the summary and refuses a collapse, and PRINTS the shape so a
    reader can see the green was non-trivial."""
    npx = require_subject(gate)
    result = harness.run([npx, "tsx", SUBJECT_REL], cwd=paths.repo_root())
    gate.assert_exit_code(
        0, result.rc, "the real tree must be clean (output: %s)" % result.combined
    )
    run, skipped, entries = summary(gate, result.combined)
    if run < REAL_PROBE_FLOOR:
        gate.log_fail(
            "only %d probe(s) ran against the real tree (floor %d, %d skipped): the gate "
            "is not seeing the tree, so its green would mean nothing."
            % (run, REAL_PROBE_FLOOR, skipped)
        )
    if entries < REAL_ENTRY_FLOOR:
        gate.log_fail(
            "only %d suppression entr(ies) were checked against the real tree (floor %d): "
            "the policy corpus has collapsed or the readers stopped reading."
            % (entries, REAL_ENTRY_FLOOR)
        )
    gate.log_pass(
        "real sweep shape: %d probe(s) run, %d skipped, %d entr(ies) checked"
        % (run, skipped, entries)
    )


def test_fires_on_dead_deps_entry(gate):
    """THE FIRING DIRECTION, and the case the whole gate exists for. The finding
    must name the entry, cite file:line, and hand over the follow-up command --
    "something is stale" sends the reader grepping."""
    with harness.temp_dir() as root:
        make_fixture(gate, root)
        write_policy(
            root,
            ".deps-upgrade-blocklist",
            "# BLOCKER: planted dead package to prove the deps probe fires in this test\n"
            "totally-not-a-real-package\n",
        )
        result = run_gate(gate, root)
        gate.assert_exit_code(1, result.rc, "a dead deps entry must fail the gate")
        gate.assert_contains(result.combined, "totally-not-a-real-package", "names the dead entry")
        gate.assert_contains(result.combined, ".deps-upgrade-blocklist:2", "cites file:line")
        gate.assert_contains(
            result.combined, "npm run check:deps", "emits the exact follow-up command"
        )
        gate.log_pass("fires on a dead .deps-upgrade-blocklist entry")


def test_no_false_positive_on_live_entry(gate):
    """THE CONTROL FOR THE CASE ABOVE. eslint is genuinely declared in the root
    manifest, which is the only one the fixture carries. (zod would NOT work here:
    it appears in the real package.json only under "overrides", and an override is
    not a declaration, so the deps probe would correctly condemn it.)"""
    with harness.temp_dir() as root:
        make_fixture(gate, root)
        write_policy(
            root,
            ".deps-upgrade-blocklist",
            "# BLOCKER: live package pinned deliberately, must not be reported as stale\neslint\n",
        )
        result = run_gate(gate, root)
        gate.assert_exit_code(0, result.rc, "a declared package must not be condemned")
        gate.assert_not_contains(result.combined, "FAIL", "no findings for a live entry")
        gate.log_pass("does not condemn a still-declared package")


def test_oracle_floor_skips_instead_of_condemning(gate):
    """A SUSPECT ORACLE MUST SKIP LOUDLY, never condemn. Two deps only, far below
    the deps probe's floor of 20: the direct analogue of the `total_vulns>0` guard
    in `.ci/scripts/security/audit.sh`.

    The second, LIVE entry on a healthy probe is not decoration. Without it the
    only entry is the skipped one, the run asserts nothing, and the gate's own
    anti-vacuity refusal fails it for a different reason than the one under test.
    """
    with harness.temp_dir() as root:
        make_fixture(gate, root)
        (root / "package.json").write_text(
            '{"name":"fixture","dependencies":{"a":"1.0.0","b":"1.0.0"}}\n', encoding="utf-8"
        )
        write_policy(
            root,
            ".deps-upgrade-blocklist",
            "# BLOCKER: must survive because the oracle is too small to be trusted here\n"
            "something\n",
        )
        write_policy(
            root,
            ".actions-upgrade-blocklist",
            "# BLOCKER: pinned deliberately; referenced only from a composite action file\n"
            "actions/create-github-app-token\n",
        )
        result = run_gate(gate, root)
        gate.assert_exit_code(0, result.rc, "a suspect oracle must not fail the gate")
        gate.assert_contains(result.combined, "SKIP", "reports a skip")
        gate.assert_contains(result.combined, "floor is 20", "explains the floor that was not met")
        gate.assert_not_contains(
            result.combined, "FAIL", "must not condemn against a suspect oracle"
        )
        gate.log_pass("oracle floor skips loudly instead of condemning")


def test_vacuous_run_fails(gate):
    """THE ANTI-VACUITY REFUSAL, IN THE SUBJECT. No manifests, no lockfile, no
    `.github`, no go.mod: every oracle unavailable, yet entries exist. The run
    proved nothing and must not report success.

    `.ci/policy` alone is not a full checkout (`isFullCheckout` wants
    `.ci/scripts/quality`, `package.json` and `.github/workflows`), so this stays
    the all-oracles-missing root it was before the lists moved there.
    """
    with harness.temp_dir() as root:
        (root / ".ci" / "policy").mkdir(parents=True, exist_ok=True)
        write_policy(
            root,
            ".deps-upgrade-blocklist",
            "# BLOCKER: entry that cannot be checked because every oracle is missing here\n"
            "something\n",
        )
        result = run_gate(gate, root)
        gate.assert_exit_code(1, result.rc, "a vacuous run must fail")
        gate.assert_contains(result.combined, "vacuous", "says the run proved nothing")
        gate.log_pass("vacuous run (all probes skipped, entries present) fails")


def test_composite_action_counts_as_a_reference(gate):
    """`create-github-app-token` is referenced ONLY from the composite action.
    Before `collectActionRefs()` scanned `.github/actions`, this entry would have
    been wrongly condemned -- a false positive that deletes a live pin."""
    with harness.temp_dir() as root:
        make_fixture(gate, root)
        write_policy(
            root,
            ".actions-upgrade-blocklist",
            "# BLOCKER: pinned deliberately; referenced only from a composite action file\n"
            "actions/create-github-app-token\n",
        )
        result = run_gate(gate, root)
        gate.assert_exit_code(0, result.rc, "composite-action reference must count as live")
        gate.assert_not_contains(result.combined, "create-github-app-token", "not reported dead")
        gate.log_pass("composite-action references keep an entry alive")


def test_a_python_port_invocation_keeps_its_exemption_alive(gate):
    """THE W7 P4 REGRESSION, both directions in one pair with the case below.

    The workflow oracle read `(\\.ci/scripts/[\\w./-]+\\.sh)` and nothing else, so the
    instant a cutover repointed a step at `check_<name>.py` the oracle stopped
    seeing any invocation of that gate and condemned its own exemption as DEAD --
    handing the reader a FIX that deletes the line keeping a LIVE gate excused.
    Nine entries went that way at once on 2026-09-08.
    """
    with harness.temp_dir() as root:
        make_fixture(gate, root)
        (root / ".github" / "workflows" / "ported.yml").write_text(
            "jobs:\n"
            "  lane:\n"
            "    steps:\n"
            "      - name: Ported gate\n"
            "        run: .ci/scripts/quality/check_planted_port.py\n",
            encoding="utf-8",
        )
        write_policy(
            root,
            ".ci-parity-exempt",
            "# BLOCKER: planted CI-only PORT, invoked by ported.yml and by nothing local\n"
            "ci-only  .ci/scripts/quality/check_planted_port.py\n",
        )
        result = run_gate(gate, root)
        gate.assert_exit_code(
            0, result.rc, "a workflow that runs the .py port keeps the entry live"
        )
        gate.assert_not_contains(result.combined, "check_planted_port.py", "not reported dead")
        gate.log_pass("a `.py` port invoked from a workflow keeps its parity exemption alive")


def test_an_uninvoked_python_port_exemption_is_still_condemned(gate):
    """THE FIRING HALF of the pair above, and the reason widening the oracle did
    not make it toothless: with no workflow naming it, the same `.py` entry must
    still be reported dead."""
    with harness.temp_dir() as root:
        make_fixture(gate, root)
        write_policy(
            root,
            ".ci-parity-exempt",
            "# BLOCKER: planted CI-only port that NOTHING invokes, to prove the probe still fires\n"
            "ci-only  .ci/scripts/quality/check_planted_port.py\n",
        )
        result = run_gate(gate, root)
        gate.assert_exit_code(1, result.rc, "an exemption nothing invokes must still fail")
        gate.assert_contains(result.combined, "check_planted_port.py", "names the dead entry")
        gate.log_pass("an uninvoked `.py` exemption is still condemned")


def test_overrides_warn_never_fail(gate):
    """TIERING. A dead override is a human call, not a build break, so it WARNS and
    the gate still exits 0 -- and the warning carries the removal command."""
    with harness.temp_dir() as root:
        make_fixture(gate, root)
        add_override(
            root,
            "BLOCKER: forces a patched transitive that is not currently installed anywhere",
        )
        result = run_gate(gate, root)
        gate.assert_exit_code(0, result.rc, "a dead override must WARN, never fail")
        gate.assert_contains(result.combined, "WARN", "reported at warn tier")
        gate.assert_contains(result.combined, "npm pkg delete", "offers the removal command")
        gate.log_pass("dead override warns and never fails the gate")


def test_preventive_annotation_silences_override_warning(gate):
    """THE OPT-OUT, and the converse of the case above. An override that guards
    against a vulnerable transitive RETURNING is dead by construction and must not
    be reported forever.

    The reason string here uses a plain hyphen where the twin uses an em dash. The
    matcher is `/^BLOCKER:\\s*preventive\\b/i`, so only the word is load-bearing;
    see the module docstring.
    """
    with harness.temp_dir() as root:
        make_fixture(gate, root)
        add_override(
            root,
            "BLOCKER: preventive - guards against a vulnerable transitive returning to the tree",
        )
        result = run_gate(gate, root)
        gate.assert_exit_code(0, result.rc, "preventive override stays silent")
        gate.assert_not_contains(result.combined, "ghost-pkg", "annotated override is not reported")
        gate.log_pass("a 'BLOCKER: preventive' reason opts an override out of the warning")


def test_findings_are_capped(gate):
    """25 dead entries against a per-probe output cap of 10. The roll-up line is
    what keeps a bulk failure readable instead of burying the other probes."""
    with harness.temp_dir() as root:
        make_fixture(gate, root)
        lines = ["# BLOCKER: bulk planted dead entries to prove the per-probe output cap works"]
        lines += ["not-a-real-package-%d" % i for i in range(1, 26)]
        write_policy(root, ".deps-upgrade-blocklist", "\n".join(lines) + "\n")
        result = run_gate(gate, root)
        gate.assert_exit_code(1, result.rc, "bulk dead entries still fail")
        gate.assert_contains(result.combined, "and 15 more", "rolls up beyond the per-probe cap")
        gate.log_pass("output is capped per probe with a roll-up line")


def test_fires_on_dead_template_skiplist_entry(gate):
    """A skiplist entry naming a template that no longer exists.

    THE TEMPLATE TREE IS REQUIRED, where the twin tolerates its absence. Without
    it the probe's universe is null, the probe SKIPS, the fixture's only entry goes
    unchecked, and the run exits 1 as VACUOUS -- which satisfies an exit-code
    assertion for entirely the wrong reason. See the module docstring.
    """
    with harness.temp_dir() as root:
        make_fixture(gate, root)
        templates = paths.from_root("packages", "json", "templates")
        if not templates.is_dir():
            gate.log_fail(
                "packages/json/templates is missing, so the templates probe would SKIP and "
                "this case would exit 1 as VACUOUS rather than on the dead entry it is "
                "supposed to catch."
            )
        shutil.copytree(templates, root / "packages" / "json" / "templates", dirs_exist_ok=True)
        (root / "packages" / "json" / ".templates-skiplist").write_text(
            "gone/removed-template\n", encoding="utf-8"
        )
        result = run_gate(gate, root)
        gate.assert_exit_code(1, result.rc, "a skiplist entry for a deleted template must fail")
        gate.assert_contains(result.combined, "gone/removed-template", "names the dead template")
        gate.log_pass("fires on a .templates-skiplist entry whose template is gone")


def test_cli_i18n_prefix_matching(gate):
    """PREFIXES ARE MATCHED AS PREFIXES, not as exact keys. Both directions in one
    fixture: a live dynamic-key prefix that still matches leaves must survive, and
    a prefix matching nothing must fire. A gate doing exact-key lookups would
    condemn the first and pass the second."""
    with harness.temp_dir() as root:
        make_fixture(gate, root)
        catalog_rel = ("packages", "cli", "src", "i18n", "locales", "en", "cli.json")
        catalog = paths.from_root(*catalog_rel)
        if not catalog.is_file():
            gate.log_fail(
                "%s is missing, so the cli-i18n probe would SKIP and neither direction of "
                "this case would be checked." % "/".join(catalog_rel)
            )
        (root / "packages" / "cli" / "src" / "i18n" / "locales" / "en").mkdir(
            parents=True, exist_ok=True
        )
        shutil.copyfile(catalog, root.joinpath(*catalog_rel))
        write_policy(
            root,
            ".cli-i18n-orphan-allowlist",
            "# BLOCKER: live dynamic-key prefix that still matches leaves in the catalog\n"
            "commands.sync.\n"
            "\n"
            "# BLOCKER: prefix matching nothing so it can exempt nothing from the orphan scan\n"
            "nope.not.a.real.prefix.\n",
        )
        result = run_gate(gate, root)
        gate.assert_exit_code(1, result.rc, "a prefix matching zero leaves must fail")
        gate.assert_contains(result.combined, "nope.not.a.real.prefix.", "names the dead prefix")
        gate.assert_not_contains(
            result.combined, "commands.sync.", "live prefix must survive prefix-matching"
        )
        gate.log_pass("cli-i18n prefixes are matched as prefixes, not exact keys")
