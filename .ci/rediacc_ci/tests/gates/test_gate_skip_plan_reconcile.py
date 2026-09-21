"""Port of `.ci/scripts/test/gates/test-skip-plan-reconcile.sh`, retired in W7 P5.

Unit test for the attested skip-plan reconciler, `.ci/scripts/ci/skip-plan-reconcile.cjs` (Wave B edge cases 25-32, section E).

WHAT THIS GUARDS. `ci-complete` sees only caller-level scalars, and for a reusable caller that scalar reads `success` when every inner job succeeded OR self-skipped. Per-inner-job conclusions are not exposed to sibling jobs by any expression, so an inner job silently skipping while its siblings pass (the invisible cell) is undetectable at caller level. The reconciler closes that
hole by checking the attested plan against the Jobs API at leaf level. Until it provably hard-fails on a planted mismatch, the scope engine's vector must never gate a real job; this file is that proof.

THE PLAN IS THE ALLOWLIST. Run 30307775327 (healthy) had ELEVEN skipped inner jobs against zero failures, all legitimate: cached-vs-uncached variants, unexpanded matrix legs, one push-gated job. That exact shape is a fixture here and must NOT fire; only jobs the plan marked `run` may.

PRE-EXISTING SKIPS ARE THE SECOND HALF. ci.yml skipped whole columns long before the scope engine existed: `full_suite` is false on every push-to-main, `pointer_bump_only` cuts the entire expensive pipeline on a submodule-pointer PR, `is_bot` cuts the staging chain. Against an unannotated plan a pointer bump reports SEVENTEEN failures on a run where nothing went wrong, which is why
the gate could not be wired. The cases below pin the exemption AND its edges, each as a pair: a fixture where the new logic must FIRE and a twin where it must stay SILENT.

THE FIXTURE OBLIGATION IS REAL, not a footnote. The plan is generated from `JOB_SURFACES`, so adding a key there without adding its leaf to `HEALTHY_JOBS` makes the healthy fixture fail as planned-job-missing. That is the gate working: a planned job with no observed leaf IS a defect in a real run, so the fix is always to add the leaf, never to loosen the check.

WHAT THE PORT CHANGES, and it is the one thing the twin itself argues for. The twin builds every fixture in ONE `$WORK` directory at file scope, and several cases consume a derived fixture an EARLIER case wrote: `test_annotation_must_agree_with_the_conditions` reads `jobs-unit-skipped.json` from case 25 and `plan-pointer-bump.json` from the pointer-bump case. The twin already names
that hazard in its own comment ("a case that only passes when a sibling ran first is a case that fails the day somebody reorders the list, and it would fail looking like a real find") and fixes it in exactly one place. Under pytest the hazard is worse, because `-n 8 --dist loadgroup` can run the cases in different workers, so every case here builds the fixtures it needs into its
OWN `tmp_path`. Same fixtures, same mutations, no ordering dependence and no shared directory.
"""

import json
import pathlib

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

RECONCILE = paths.from_root(".ci", "scripts", "ci", "skip-plan-reconcile.cjs")
MAP = paths.from_root(".ci", "scripts", "ci", "scope-map.cjs")

RUN_ID = "30307775327"

INSTALL_PREFIX = "Validate Install Methods"

# Run 30307775327's payload: a success leaf for every planned key, the eleven structural skips observed live, and unplanned extras the reconciler must ignore.
HEALTHY_SUCCESS = [
    "Initialize",
    "Tests + Infra / Unit",
    "Tests + Infra / E2E Workers (ubuntu-24.04)",
    "Tests + Infra / E2E Workers (fedora-43)",
    "Tests + Infra / E2E Ceph",
    "Tests + Infra / E2E Ceph Workers",
    "Tests + Infra / E2E K8s",
    "Tests + Infra / E2E K8s Ceph",
    "Tests + Infra / E2E K8s Multinode",
    "Tests + Infra / E2E Migrate",
    "Tests + Infra / Concurrent Fork Isolation",
    "Tests + Infra / Renet",
    "Tests + Infra / License Enforcement",
    "Tests + Infra / Account E2E",
    "Tests + Infra / Drills",
    "Tests + Infra / Migration Test",
    "OPS Tests / OPS Provision (linux-amd64)",
    "OPS Tests / OPS Provision (macos-intel)",
    "OPS Tests / OPS Check (linux-arm64)",
    "Elite Run",
    "Tests + Infra / Update Flow / Update flow (Linux x64)",
    "Tests + Infra / Linux Packages",
    "Validate Install Methods / Linux (x64)",
    "Validate Install Methods / Linux (arm64)",
    "Validate Install Methods / macOS (ARM64)",
    "Validate Install Methods / Windows (x64)",
]

# The healthy eleven, verbatim from run 30307775327.
HEALTHY_SKIPPED = [
    "Build (Renet) / Procwalk (${{ matrix.os }})",
    "Build (Renet) / Renet (Full)",
    "Build (Docker Fast) / Renet Docker",
    "Build (Docker Fast) / CLI Docker",
    "Build (Docker Fast) / JSON",
    "Build (Docker Fast) / CLI Docker (cached)",
    "Build (Docker Fast) / Server Docker (cached)",
    "Build (Docker Fast) / Devcontainer (amd64)",
    "Build (Docker Fast) / Devcontainer (arm64)",
    "Build (Docker Fast) / Devcontainer Manifest",
    "Check Release State",
]


def node_bin() -> str:
    return harness.require_tool("node", "install Node 22 (the reconciler is a .cjs module)")


def node_eval(script: str, *args: str) -> str:
    result = harness.run([node_bin(), "-e", script, *args], timeout=120)
    if result.rc != 0:
        raise harness.GateAssertionError(
            "node -e exited %d; the exported helper could not be reached at all.\n"
            "--- stderr ---\n%s" % (result.rc, result.err)
        )
    return result.out


def surface_keys() -> list[str]:
    """`Object.keys(JOB_SURFACES)`, read from the real map rather than typed here."""
    return json.loads(
        node_eval(
            "const m = require(process.argv[1]);"
            "process.stdout.write(JSON.stringify(Object.keys(m.JOB_SURFACES)));",
            str(MAP),
        )
    )


def healthy_jobs() -> list[dict]:
    return [{"name": n, "conclusion": "success"} for n in HEALTHY_SUCCESS] + [
        {"name": n, "conclusion": "skipped"} for n in HEALTHY_SKIPPED
    ]


def find(jobs: list[dict], name: str) -> dict:
    """The twin's `data.jobs.find(...)`, but REFUSING a miss.

    `Array.prototype.find` returns undefined and the twin's mutation then throws, which is loud enough there. Here a silent None would set an attribute on nothing and the
    case would run against an UNMUTATED fixture, which is the shape that fails open.
    """
    for job in jobs:
        if job["name"] == name:
            return job
    raise harness.GateAssertionError(
        "the fixture has no job named %r, so the mutation would have been a no-op and "
        "the case would prove nothing" % name
    )


class World:
    """One test's fixture directory, with every derived variant built on demand."""

    def __init__(self, root: pathlib.Path) -> None:
        self.root = root
        self.out = ""
        self.err = ""
        self.plan_path = self.write_plan("plan.json", self.base_plan())
        self.jobs_path = self.write_jobs("jobs.json", healthy_jobs())

    def base_plan(self) -> dict:
        return {
            "run_id": RUN_ID,
            "mode": "full",
            "jobs": {k: {"run": True, "reason": "full"} for k in surface_keys()},
        }

    def write_plan(self, name: str, plan: dict) -> pathlib.Path:
        path = self.root / name
        path.write_text(json.dumps(plan, indent=2), encoding="utf-8")
        return path

    def write_jobs(self, name: str, jobs: list[dict] | dict) -> pathlib.Path:
        path = self.root / name
        payload = jobs if isinstance(jobs, dict) else {"jobs": jobs}
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return path

    def write_raw(self, name: str, text: str) -> pathlib.Path:
        path = self.root / name
        path.write_text(text, encoding="utf-8")
        return path

    # -- driving -----------------------------------------------------------

    def reconcile(self, plan: pathlib.Path, jobs: pathlib.Path, run_id: str | None = None) -> int:
        """`run_reconcile`. Streams captured SEPARATELY: failures land on stderr, warnings on stdout, and several cases assert exactly that split."""
        result = harness.run(
            [
                node_bin(),
                str(RECONCILE),
                "--plan",
                str(plan),
                "--jobs",
                str(jobs),
                "--run-id",
                run_id or RUN_ID,
            ],
            timeout=120,
        )
        self.out = result.out
        self.err = result.err
        return result.rc

    def annotate(self, source: pathlib.Path, name: str, conditions: dict) -> pathlib.Path:
        """Run a plan through the REAL `annotatePlan`, the same entry point `scope-shadow.sh` calls. Going through the production writer rather than hand-writing the annotation is what makes these cases test the shipped writer instead of a paraphrase of it."""
        target = self.root / name
        node_eval(
            """
const fs = require("fs");
const { annotatePlan } = require(process.argv[1]);
const plan = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
annotatePlan(plan, JSON.parse(process.argv[4]));
fs.writeFileSync(process.argv[3], JSON.stringify(plan, null, 2));
""",
            str(RECONCILE),
            str(source),
            str(target),
            json.dumps(conditions),
        )
        return target

    def reconcile_module(
        self, plan: pathlib.Path, jobs: pathlib.Path, honor_preexisting: bool
    ) -> str:
        """`<ok>|<first failure>|exempt=<n>`. The CLI always honors, so the strict
        default is only reachable through the module API, which is exactly how scope-engine's `attestPlan` calls it. Without this the default is untestable."""
        return node_eval(
            """
const fs = require("fs");
const r = require(process.argv[1]);
const plan = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
const jobs = r.parseJobsPayload(JSON.parse(fs.readFileSync(process.argv[3], "utf8")));
const ctx = { runId: process.argv[5] };
if (process.argv[4] === "true") ctx.honorPreexisting = true;
const res = r.reconcile(plan, jobs, ctx);
process.stdout.write(`${res.ok}|${res.failures[0] || ""}|exempt=${res.exempt.length}`);
""",
            str(RECONCILE),
            str(plan),
            str(jobs),
            "true" if honor_preexisting else "false",
            RUN_ID,
        )


def make_world(gate, tmp_path) -> World:
    for subject in (RECONCILE, MAP):
        if not subject.is_file():
            gate.log_fail(
                "%s is missing; this gate has nothing to drive" % paths.relative_to_root(subject)
            )
    return World(tmp_path)


def skipped_count(jobs: list[dict]) -> int:
    return len([j for j in jobs if j["conclusion"] == "skipped"])


# ---------------------------------------------------------------------------


def test_mandatory_invisible_cell_hard_fails(gate, tmp_path):
    """Edge case 25, the planted mismatch this whole chunk exists for: plan says `Tests + Infra / Unit` runs, the leaf is skipped, every sibling succeeded, so every caller scalar would read success."""
    world = make_world(gate, tmp_path)
    jobs = healthy_jobs()
    find(jobs, "Tests + Infra / Unit")["conclusion"] = "skipped"
    planted = world.write_jobs("jobs-unit-skipped.json", jobs)
    gate.assert_eq(
        world.reconcile(world.plan_path, planted),
        1,
        "a planned-run leaf that self-skipped must hard-fail",
    )
    gate.assert_contains(
        world.err,
        "planned-run-but-skipped: 'unit' -> 'Tests + Infra / Unit'",
        "with the key and the leaf named, on stderr",
    )
    # CONTROL: the identical pipeline with the leaf back to success is green.
    gate.assert_eq(
        world.reconcile(world.plan_path, world.jobs_path),
        0,
        "the untouched healthy fixture reconciles clean",
    )
    gate.log_pass(
        "the invisible cell hard-fails: planned-run leaf skipped, siblings green (case 25)"
    )


def test_planned_run_but_cancelled_is_named(gate, tmp_path):
    """A CANCELLED JOB DID NOT RUN, and reconcile used to record it as having run: the branch complained only on `skipped`, so `cancelled` took the silent path under a comment that said "any non-skipped conclusion counts as 'it ran'".

    Both real shapes produce it. The watchdog force-cancels siblings when one job fails, and a job over its own timeout-minutes reports `cancelled` too: Quality / Code did exactly that at 15m19s on 2026-09-03 with 52 of 92 steps executed, and no message anywhere said "timeout"."""
    world = make_world(gate, tmp_path)
    jobs = healthy_jobs()
    find(jobs, "Tests + Infra / Unit")["conclusion"] = "cancelled"
    cancelled = world.write_jobs("jobs-unit-cancelled.json", jobs)
    gate.assert_eq(
        world.reconcile(world.plan_path, cancelled),
        0,
        "a cancelled planned job WARNS rather than failing (assert-ci-complete already reds it)",
    )
    gate.assert_contains(
        world.out,
        "planned-run-but-cancelled: 'unit' -> 'Tests + Infra / Unit'",
        "and it is named, with the key and the leaf",
    )

    # CONTROL, and it is the whole point: the SAME fixture with the SAME job left at success says nothing, so the assertion above is not passing against a reconciler that warns about everything.
    world.reconcile(world.plan_path, world.jobs_path)
    gate.assert_not_contains(
        world.out, "planned-run-but-cancelled", "the untouched fixture warns about no cancellation"
    )

    # AND THE TWO CONCLUSIONS MUST STAY APART. Asserted through the EXIT CODES rather than a second absence check, because that is the difference that matters and an absence proves only that one string is missing: a skip is a hard failure (1), a cancellation is a warning (0).
    jobs = healthy_jobs()
    find(jobs, "Tests + Infra / Unit")["conclusion"] = "skipped"
    skipped = world.write_jobs("jobs-unit-skipped-here.json", jobs)
    gate.assert_eq(
        world.reconcile(world.plan_path, skipped),
        1,
        "a skipped planned job still hard-fails while a cancelled one does not",
    )
    gate.log_pass("a cancelled planned job is named as producing no evidence, never as having run")


def test_healthy_eleven_must_not_fire(gate, tmp_path):
    """Section E: the plan is the allowlist. First prove the fixture SHAPE, or the silence below would be a test of nothing."""
    world = make_world(gate, tmp_path)
    gate.assert_eq(
        skipped_count(healthy_jobs()),
        11,
        "the fixture carries the eleven structural skips from run %s" % RUN_ID,
    )
    gate.assert_eq(
        world.reconcile(world.plan_path, world.jobs_path),
        0,
        "eleven structural skips against a full plan reconcile clean",
    )
    gate.assert_not_contains(world.err, "planned-run-but-skipped", "no skip is flagged")
    gate.assert_not_contains(world.out, "::warning::", "and none is even warned about")

    # CONTROL: the reconciler CAN fire on this very fixture, and when it does it blames only the planted key, never the structural skips.
    jobs = healthy_jobs()
    find(jobs, "Tests + Infra / E2E Ceph")["conclusion"] = "skipped"
    ceph = world.write_jobs("jobs-ceph-skipped.json", jobs)
    gate.assert_eq(
        world.reconcile(world.plan_path, ceph),
        1,
        "planting one scope-relevant skip flips the same fixture red",
    )
    gate.assert_contains(
        world.err, "planned-run-but-skipped: 'e2e_ceph'", "blaming the planted key"
    )
    gate.assert_not_contains(
        world.err,
        "Build (Docker Fast)",
        "and never the structural skips: the plan is the allowlist",
    )
    gate.log_pass(
        "the healthy eleven from run %s stay silent; only planned jobs can fire (section E)"
        % RUN_ID
    )


def test_planned_job_missing_hard_fails(gate, tmp_path):
    """Edge case 27: planned to run, absent from the Jobs API entirely (a rename, a dropped workflow call, a DAG break)."""
    world = make_world(gate, tmp_path)
    jobs = [j for j in healthy_jobs() if j["name"] != "Tests + Infra / Unit"]
    no_unit = world.write_jobs("jobs-no-unit.json", jobs)
    gate.assert_eq(
        world.reconcile(world.plan_path, no_unit),
        1,
        "a planned job absent from the payload must hard-fail",
    )
    gate.assert_contains(world.err, "planned-job-missing: 'unit'", "as planned-job-missing")
    gate.assert_eq(
        world.reconcile(world.plan_path, world.jobs_path),
        0,
        "with the job present the same plan reconciles clean",
    )
    gate.log_pass("a planned job missing from the Jobs API hard-fails (case 27)")


def test_over_running_warns_only(gate, tmp_path):
    """Edge case 28: plan says skip, job ran and passed. Over-running is the safe direction (extra evidence), so it must warn and NOT block; blocking it would punish
    the fail-open `!= 'false'` YAML polarity."""
    world = make_world(gate, tmp_path)
    plan = world.base_plan()
    plan["jobs"]["unit"] = {"run": False, "reason": "out-of-scope"}
    skip_unit = world.write_plan("plan-skip-unit.json", plan)
    gate.assert_eq(
        world.reconcile(skip_unit, world.jobs_path),
        0,
        "a planned-skip job that ran anyway must NOT fail the reconcile",
    )
    gate.assert_contains(
        world.out,
        "::warning::planned-skip-but-ran: 'unit'",
        "but it is warned about, on stdout, as an Actions annotation",
    )
    gate.assert_not_contains(world.err, "FAIL", "and nothing lands on stderr")
    # CONTROL: the warning is earned, not constant.
    jobs = healthy_jobs()
    find(jobs, "Tests + Infra / Unit")["conclusion"] = "skipped"
    skipped = world.write_jobs("jobs-unit-skipped2.json", jobs)
    gate.assert_eq(world.reconcile(skip_unit, skipped), 0, "a planned skip that skipped is clean")
    gate.assert_not_contains(world.out, "::warning::", "with no warning")
    gate.log_pass("over-running warns only; honored skips are silent (case 28)")


def test_missing_plan_hard_fails_polarity_inverted(gate, tmp_path):
    """Edge case 29, THE POLARITY INVERSION: the engine degrades toward more CI, the reconciler degrades toward red. A missing attestation must never read as green."""
    world = make_world(gate, tmp_path)
    gate.assert_eq(
        world.reconcile(tmp_path / "does-not-exist.json", world.jobs_path),
        1,
        "a missing plan artifact must hard-fail",
    )
    gate.assert_contains(world.err, "skip-plan-missing", "named as skip-plan-missing")
    gate.assert_contains(world.err, "degrades to red", "and the message states the polarity")
    garbage = world.write_raw("plan-garbage.json", "not json at all\n")
    gate.assert_eq(
        world.reconcile(garbage, world.jobs_path), 1, "an unparseable plan is as missing"
    )
    gate.assert_eq(
        world.reconcile(world.plan_path, world.jobs_path),
        0,
        "the real plan still reconciles clean",
    )
    gate.log_pass(
        "a missing or unreadable plan hard-fails: the reconciler degrades to red (case 29)"
    )


def test_run_id_mismatch_is_tamper(gate, tmp_path):
    """Edge case 30, anti-tamper: the plan must name THIS run, or a stale or substituted artifact could vouch for skips it never planned."""
    world = make_world(gate, tmp_path)
    gate.assert_eq(
        world.reconcile(world.plan_path, world.jobs_path, "999999"),
        1,
        "a plan carrying another run's id must hard-fail",
    )
    gate.assert_contains(world.err, "plan-run-id-mismatch", "as plan-run-id-mismatch")
    plan = world.base_plan()
    del plan["run_id"]
    no_runid = world.write_plan("plan-no-runid.json", plan)
    gate.assert_eq(
        world.reconcile(no_runid, world.jobs_path),
        1,
        "a plan without a run_id must hard-fail too",
    )
    gate.assert_eq(
        world.reconcile(world.plan_path, world.jobs_path, RUN_ID),
        0,
        "the matching run id reconciles clean",
    )
    gate.log_pass("a run-id mismatch or absence hard-fails, anti-tamper (case 30)")


def test_naming_trap_uses_explicit_table(gate, tmp_path):
    """Edge case 31: ci.yml's `update-flow-test` is a CALLER display-named `Tests + Infra / Update Flow` whose real leaf is three segments deep, while `package-tests` is a PLAIN job named `Tests + Infra / Linux Packages`, NOT inside ct-tests.yml. The name shape lies in both directions."""
    world = make_world(gate, tmp_path)
    names = node_eval(
        """
const r = require(process.argv[1]);
process.stdout.write(JSON.stringify({
  update_flow: r.EXPECTED_JOB_NAMES.update_flow,
  package_tests: r.EXPECTED_JOB_NAMES.package_tests,
}));
""",
        str(RECONCILE),
    )
    gate.assert_contains(
        names,
        "Tests + Infra / Update Flow / Update flow",
        "update_flow maps to the caller LEAF, three name segments deep",
    )
    gate.assert_contains(
        names, "Tests + Infra / Linux Packages", "package_tests maps to the top-level plain job"
    )

    jobs = healthy_jobs()
    find(jobs, "Tests + Infra / Update Flow / Update flow (Linux x64)")["conclusion"] = "skipped"
    updflow = world.write_jobs("jobs-updflow-skipped.json", jobs)
    gate.assert_eq(world.reconcile(world.plan_path, updflow), 1, "a skipped update-flow leaf fires")
    gate.assert_contains(world.err, "'update_flow'", "against the update_flow key")
    # CONTROL: the sibling-named plain job fires its OWN key, so keys are not inferred
    # from the shared display prefix.
    jobs = healthy_jobs()
    find(jobs, "Tests + Infra / Linux Packages")["conclusion"] = "skipped"
    pkg = world.write_jobs("jobs-pkg-skipped.json", jobs)
    gate.assert_eq(world.reconcile(world.plan_path, pkg), 1, "a skipped Linux Packages job fires")
    gate.assert_contains(world.err, "'package_tests'", "against package_tests")
    gate.assert_not_contains(world.err, "'update_flow'", "and never update_flow")
    gate.log_pass("structure comes from the explicit table, not the name shape (case 31)")


def test_matrix_match_by_prefix_never_sloppy(gate, tmp_path):
    """Edge case 32: matrix legs match by expected-name + " (". That must cover the unexpanded-template form a skipped matrix reports, and must NOT let `E2E Ceph` swallow `E2E Ceph Workers`."""
    world = make_world(gate, tmp_path)
    jobs = healthy_jobs()
    jobs.append(
        {"name": "Tests + Infra / E2E Workers (${{ matrix.os-image }})", "conclusion": "skipped"}
    )
    template = world.write_jobs("jobs-template-skip.json", jobs)
    gate.assert_eq(
        world.reconcile(world.plan_path, template),
        1,
        "an unexpanded skipped matrix leg still matches its key",
    )
    gate.assert_contains(
        world.err,
        "planned-run-but-skipped: 'e2e_workers'",
        "as e2e_workers, template form and all",
    )

    # Precision: remove the plain `E2E Ceph` job. `E2E Ceph Workers` is still present and green; if the matcher were bare startsWith it would satisfy e2e_ceph.
    jobs = [j for j in healthy_jobs() if j["name"] != "Tests + Infra / E2E Ceph"]
    no_ceph = world.write_jobs("jobs-no-ceph.json", jobs)
    gate.assert_eq(
        world.reconcile(world.plan_path, no_ceph),
        1,
        "E2E Ceph Workers must not satisfy the e2e_ceph key",
    )
    gate.assert_contains(world.err, "planned-job-missing: 'e2e_ceph'", "which reports missing")
    gate.assert_not_contains(
        world.err,
        "planned-job-missing: 'e2e_ceph_workers'",
        "while e2e_ceph_workers still matches its own job",
    )
    gate.assert_eq(
        world.reconcile(world.plan_path, world.jobs_path),
        0,
        "both ceph keys reconcile clean when both jobs exist",
    )
    gate.log_pass("matrix legs match by prefix + ' (', never bare startsWith (case 32)")


def test_flat_job_never_blames_a_lookalike_caller(gate, tmp_path):
    """Edge case 33: caller-derivation must not fire for a FLAT job whose display name merely shares a prefix with a reusable caller.

    `package-tests` is a plain top-level job named "Tests + Infra / Linux Packages" (ci.yml:572-573). The `tests` reusable caller's own display name is exactly "Tests + Infra" (ci.yml:673-674). Splitting the expected name on ' / ' regardless would derive 'Tests + Infra' and then blame that unrelated job, converting a real
    case-27 rename or DAG break into a bogus case-25 caller-skip."""
    world = make_world(gate, tmp_path)
    jobs = [j for j in healthy_jobs() if j["name"] != "Tests + Infra / Linux Packages"]
    jobs.append({"name": "Tests + Infra", "conclusion": "skipped"})
    trap = world.write_jobs("jobs-flat-trap.json", jobs)
    gate.assert_eq(
        world.reconcile(world.plan_path, trap),
        1,
        "a flat job missing from the payload still hard-fails",
    )
    gate.assert_contains(
        world.err,
        "planned-job-missing: 'package_tests'",
        "reported as the rename/DAG break it actually is",
    )
    gate.assert_not_contains(
        world.err,
        "planned-run-but-skipped: 'package_tests'",
        "never misattributed to the lookalike 'Tests + Infra' caller",
    )

    # CONTROL, and without it this case would pass just as well if caller derivation were deleted outright.
    jobs = [j for j in healthy_jobs() if not j["name"].startswith("OPS Tests / ")]
    jobs.append({"name": "OPS Tests", "conclusion": "skipped"})
    ops = world.write_jobs("jobs-ops-caller-skipped.json", jobs)
    gate.assert_eq(
        world.reconcile(world.plan_path, ops),
        1,
        "a genuinely skipped reusable caller still hard-fails",
    )
    gate.assert_contains(
        world.err,
        "planned-run-but-skipped: 'ops' -> reusable caller 'OPS Tests'",
        "and is still diagnosed as a caller skip, not a missing job",
    )
    gate.assert_not_contains(
        world.err,
        "planned-job-missing: 'ops'",
        "so the caller-derivation path is alive, not merely disabled",
    )
    gate.assert_eq(
        world.reconcile(world.plan_path, world.jobs_path),
        0,
        "the healthy fixture reconciles clean throughout",
    )
    gate.log_pass("flat lookalikes never borrow a caller's skip (case 33)")


def test_unknown_plan_key_fails_closed(gate, tmp_path):
    """A plan key the table cannot map cannot be verified: red, not shrug."""
    world = make_world(gate, tmp_path)
    plan = world.base_plan()
    plan["jobs"]["totally_new_job"] = {"run": True, "reason": "modules:x"}
    bogus = world.write_plan("plan-bogus-key.json", plan)
    gate.assert_eq(
        world.reconcile(bogus, world.jobs_path), 1, "an unmappable plan key must hard-fail"
    )
    gate.assert_contains(
        world.err, "unknown-plan-key: 'totally_new_job'", "named as unknown-plan-key"
    )
    gate.assert_eq(
        world.reconcile(world.plan_path, world.jobs_path),
        0,
        "the real key set reconciles clean",
    )
    gate.log_pass("an unknown plan key fails closed (the reconciler cannot verify it)")


def test_name_table_parity_with_scope_map(gate):
    """`EXPECTED_JOB_NAMES` and scope-map's `JOB_SURFACES` must cover the same keys; the module throws at load on drift. Prove the validator fires in BOTH directions, then that the real tables pass."""
    verdicts = node_eval(
        """
const r = require(process.argv[1]);
const m = require(process.argv[2]);
const out = [];
const missing = { ...r.EXPECTED_JOB_NAMES };
delete missing.unit;
try { r.validateNameTable(missing, m.JOB_SURFACES); out.push("missing:no-throw"); }
catch (e) { out.push("missing:" + e.message); }
try { r.validateNameTable({ ...r.EXPECTED_JOB_NAMES, extra_key: ["X"] }, m.JOB_SURFACES); out.push("orphan:no-throw"); }
catch (e) { out.push("orphan:" + e.message); }
try { r.validateNameTable(r.EXPECTED_JOB_NAMES, m.JOB_SURFACES); out.push("real:ok"); }
catch (e) { out.push("real:" + e.message); }
process.stdout.write(out.join("\\n"));
""",
        str(RECONCILE),
        str(MAP),
    )
    gate.assert_contains(
        verdicts,
        "missing:EXPECTED_JOB_NAMES lacks plan key 'unit'",
        "a surface key without a name entry throws",
    )
    gate.assert_contains(
        verdicts,
        "orphan:EXPECTED_JOB_NAMES has orphan key 'extra_key'",
        "a name entry without a surface key throws",
    )
    gate.assert_contains(verdicts, "real:ok", "and the real tables pass both directions")
    gate.log_pass("the name table and scope-map's surfaces cannot drift apart silently")


def test_jobs_payload_forms_and_absence(gate, tmp_path):
    """`gh api .../jobs` returns `{ jobs: [...] }`; a bare array must work too, and
    unusable payloads must hard-fail (reconciler polarity again)."""
    world = make_world(gate, tmp_path)
    bare = world.write_raw("jobs-bare.json", json.dumps(healthy_jobs()))
    gate.assert_eq(
        world.reconcile(world.plan_path, bare),
        0,
        "a bare-array jobs payload reconciles identically",
    )
    garbage = world.write_raw("jobs-garbage.json", "not json\n")
    gate.assert_eq(
        world.reconcile(world.plan_path, garbage),
        1,
        "an unparseable jobs payload must hard-fail",
    )
    gate.assert_contains(world.err, "jobs-payload-missing", "as jobs-payload-missing")
    shapeless = world.write_raw("jobs-shapeless.json", '{"total_count": 0}\n')
    gate.assert_eq(
        world.reconcile(world.plan_path, shapeless),
        1,
        "a payload without a jobs array must hard-fail",
    )
    gate.log_pass("both payload forms parse; unusable evidence hard-fails")


def test_warnings_never_mask_failures(gate, tmp_path):
    """A run can over-run one key and under-run another; the warning must not eat the failure, and the streams must stay separate."""
    world = make_world(gate, tmp_path)
    plan = world.base_plan()
    plan["jobs"]["unit"] = {"run": False, "reason": "out-of-scope"}
    mixed_plan = world.write_plan("plan-mixed.json", plan)
    jobs = healthy_jobs()
    find(jobs, "Tests + Infra / E2E Ceph")["conclusion"] = "skipped"
    mixed_jobs = world.write_jobs("jobs-mixed.json", jobs)
    gate.assert_eq(
        world.reconcile(mixed_plan, mixed_jobs),
        1,
        "a failure alongside a warning still exits non-zero",
    )
    gate.assert_contains(
        world.err, "planned-run-but-skipped: 'e2e_ceph'", "the failure is on stderr"
    )
    gate.assert_contains(
        world.out, "::warning::planned-skip-but-ran: 'unit'", "the warning is on stdout"
    )
    gate.log_pass("warnings never mask failures, and the streams stay separate")


def pointer_bump_jobs() -> list[dict]:
    """Every job skipped: `build-renet` skips on a pointer-bump PR (ci.yml:493) and the entire expensive pipeline goes with it."""
    return [{"name": j["name"], "conclusion": "skipped"} for j in healthy_jobs()]


def push_jobs() -> list[dict]:
    """The push-to-main shape: everything full_suite gates skipped, the install matrix still green."""
    return [
        {
            "name": j["name"],
            "conclusion": j["conclusion"] if j["name"].startswith(INSTALL_PREFIX) else "skipped",
        }
        for j in healthy_jobs()
    ]


def test_pointer_bump_exempts_every_key(gate, tmp_path):
    """THE case this whole extension exists for. All eighteen planned keys skip while nothing is wrong, so an unannotated plan reports eighteen failures on a healthy run."""
    world = make_world(gate, tmp_path)
    jobs = pointer_bump_jobs()
    pb_jobs = world.write_jobs("jobs-pointer-bump.json", jobs)
    # SHAPE first: the silence below is only meaningful if the skips are real.
    gate.assert_eq(
        skipped_count(jobs), len(jobs), "the pointer-bump fixture skips every job it carries"
    )

    # FIRE: the plan as it was written before this change (no conditions).
    gate.assert_eq(
        world.reconcile(world.plan_path, pb_jobs),
        1,
        "an unannotated plan reds a pointer-bump run: the false-fire this fixes",
    )
    gate.assert_contains(
        world.err, "planned-run-but-skipped: 'unit'", "blaming scope for a non-scope skip"
    )
    gate.assert_contains(
        world.err,
        "planned-run-but-skipped: 'install_methods'",
        "including install_methods, which pointer_bump_only really does cut",
    )

    # SILENT: the same jobs against a plan that records the condition.
    pb_plan = world.annotate(
        world.plan_path,
        "plan-pointer-bump.json",
        {"pointer_bump_only": True, "full_suite": True, "is_bot": False},
    )
    gate.assert_eq(
        world.reconcile(pb_plan, pb_jobs),
        0,
        "recording pointer_bump_only makes the identical run reconcile clean",
    )
    gate.assert_not_contains(world.err, "planned-run-but-skipped", "with no failure at all")
    gate.assert_contains(
        world.out,
        "pre-existing skips (not scope decisions, not verified by this run)",
        "and the excused keys are printed, so a vacuous pass is visible",
    )
    gate.assert_contains(world.out, "unit (pointer_bump_only)", "naming the key and the condition")
    gate.assert_contains(
        world.out,
        "0 of 18 planned keys verified",
        "and the headline counts VERIFIED keys, not planned ones: this pass proves nothing",
    )
    gate.log_pass("pointer_bump_only exempts all 18 keys; the same run reds without the annotation")


def test_full_suite_exempts_seventeen_but_never_install_methods(gate, tmp_path):
    """The condition sets are NOT interchangeable. `validate-install` (ci.yml:1081-1083) hangs off `stage-artifacts`, which carries no full_suite clause (ci.yml:658), so the install matrix genuinely DOES run on push-to-main. Exempting it under full_suite would excuse a real skip for ever."""
    world = make_world(gate, tmp_path)
    push_plan = world.annotate(
        world.plan_path,
        "plan-push.json",
        {"pointer_bump_only": False, "full_suite": False, "is_bot": False},
    )
    jobs = push_jobs()
    push = world.write_jobs("jobs-push.json", jobs)
    gate.assert_eq(
        skipped_count(jobs),
        33,
        "the push fixture skips all 33 non-install jobs and leaves the four install legs",
    )
    gate.assert_eq(
        world.reconcile(push_plan, push),
        0,
        "a push-to-main shape reconciles clean once full_suite is recorded",
    )
    gate.assert_contains(world.out, "unit (full_suite)", "excusing unit under full_suite")
    gate.assert_not_contains(
        world.out,
        "install_methods (full_suite)",
        "and never excusing install_methods, which full_suite does not gate",
    )

    # FIRE, the paired twin: the ONE key full_suite must not cover goes missing.
    jobs = push_jobs()
    for job in jobs:
        if job["name"].startswith(INSTALL_PREFIX):
            job["conclusion"] = "skipped"
    push_install_skipped = world.write_jobs("jobs-push-install-skipped.json", jobs)
    gate.assert_eq(
        world.reconcile(push_plan, push_install_skipped),
        1,
        "a skipped install matrix on push-to-main is a REAL finding and must fire",
    )
    gate.assert_contains(
        world.err, "planned-run-but-skipped: 'install_methods'", "naming install_methods"
    )
    gate.assert_not_contains(
        world.err,
        "planned-run-but-skipped: 'unit'",
        "while the seventeen full_suite really gates stay excused",
    )

    # And pointer_bump_only DOES cover it, on the identical payload. Two conditions, two different key sets, same jobs: the table discriminates rather than handing out one blanket exemption.
    pb_plan = world.annotate(
        world.plan_path,
        "plan-pb2.json",
        {"pointer_bump_only": True, "full_suite": True, "is_bot": False},
    )
    gate.assert_eq(
        world.reconcile(pb_plan, push_install_skipped),
        0,
        "the same skipped install matrix is excused under pointer_bump_only",
    )
    gate.log_pass(
        "full_suite exempts 17 keys and never install_methods; pointer_bump_only exempts all 18"
    )


def test_is_bot_exempts_exactly_one_key(gate, tmp_path):
    """`is_bot` (ci.yml:105) reaches only install_methods, via stage-artifacts (ci.yml:658). A narrow exemption must stay narrow, so plant a skip OUTSIDE it."""
    world = make_world(gate, tmp_path)
    bot_plan = world.annotate(
        world.plan_path,
        "plan-bot.json",
        {"pointer_bump_only": False, "full_suite": True, "is_bot": True},
    )
    jobs = healthy_jobs()
    for job in jobs:
        if job["name"].startswith(INSTALL_PREFIX):
            job["conclusion"] = "skipped"
    bot_jobs = world.write_jobs("jobs-bot.json", jobs)
    gate.assert_eq(world.reconcile(bot_plan, bot_jobs), 0, "is_bot excuses the install matrix")
    gate.assert_contains(world.out, "install_methods (is_bot)", "naming is_bot as the reason")

    # FIRE half: one more key skips, and is_bot must not stretch to cover it.
    find(jobs, "Tests + Infra / Unit")["conclusion"] = "skipped"
    bot_plus_unit = world.write_jobs("jobs-bot-plus-unit.json", jobs)
    gate.assert_eq(
        world.reconcile(bot_plan, bot_plus_unit),
        1,
        "a skipped unit leg is still a hard failure under is_bot",
    )
    gate.assert_contains(world.err, "planned-run-but-skipped: 'unit'", "naming unit")
    gate.assert_not_contains(world.err, "'install_methods'", "while install_methods stays excused")
    gate.log_pass("is_bot exempts install_methods alone; every other key still fires")


def test_exemption_needs_a_real_boolean(gate, tmp_path):
    """Missing information must never WIDEN an exemption, so the condition test is a strict boolean compare. A plan whose conditions came through as strings (a shell variable passed unparsed) gets nothing."""
    world = make_world(gate, tmp_path)
    pb_jobs = world.write_jobs("jobs-pointer-bump.json", pointer_bump_jobs())
    plan = world.base_plan()
    plan["conditions"] = {
        "pointer_bump_only": "true",
        "full_suite": "false",
        "is_bot": "false",
    }
    stringy = world.write_plan("plan-stringy.json", plan)
    gate.assert_eq(
        world.reconcile(stringy, pb_jobs),
        1,
        "string 'true' is not true: no exemption, and the run reds",
    )
    gate.assert_contains(
        world.err, "planned-run-but-skipped: 'unit'", "exactly as if nothing were recorded"
    )

    # An omitted condition is likewise inactive, which is what the writer produces when the environment variable is unset.
    omitted = world.annotate(world.plan_path, "plan-omitted.json", {})
    gate.assert_eq(
        world.reconcile(omitted, pb_jobs), 1, "an omitted condition grants nothing either"
    )

    # CONTROL: the real booleans, same fixture, silent. Without this the two assertions above would pass just as well if exemptions were dead code.
    pb_plan = world.annotate(
        world.plan_path,
        "plan-pointer-bump.json",
        {"pointer_bump_only": True, "full_suite": True, "is_bot": False},
    )
    gate.assert_eq(
        world.reconcile(pb_plan, pb_jobs),
        0,
        "and real booleans on the identical payload reconcile clean",
    )
    gate.log_pass("only a real boolean activates a condition; strings and omissions grant nothing")


def test_annotation_must_agree_with_the_conditions(gate, tmp_path):
    """Anti-tamper. The exemption is DERIVED from `plan.conditions`; the per-job field is only ever cross-checked. A hand-edited artifact claiming an exemption its own conditions do not support must not buy a free pass on the one check that can see an invisible cell."""
    world = make_world(gate, tmp_path)
    jobs = healthy_jobs()
    find(jobs, "Tests + Infra / Unit")["conclusion"] = "skipped"
    unit_skipped = world.write_jobs("jobs-unit-skipped.json", jobs)

    plan = world.base_plan()
    plan["conditions"] = {"pointer_bump_only": False, "full_suite": True, "is_bot": False}
    plan["jobs"]["unit"]["preexisting_skip"] = "pointer_bump_only"
    forged = world.write_plan("plan-forged.json", plan)
    gate.assert_eq(
        world.reconcile(forged, unit_skipped), 1, "a forged per-job exemption must hard-fail"
    )
    gate.assert_contains(
        world.err,
        "preexisting-claim-mismatch: 'unit' claims 'pointer_bump_only'",
        "named as a claim mismatch, not silently ignored",
    )

    # Drift in the other direction: conditions say the key is exempt, the annotation is missing. That is a stale writer, and it must be as loud.
    pb_jobs = world.write_jobs("jobs-pointer-bump.json", pointer_bump_jobs())
    pb_plan_path = world.annotate(
        world.plan_path,
        "plan-pointer-bump.json",
        {"pointer_bump_only": True, "full_suite": True, "is_bot": False},
    )
    pb_plan = json.loads(pb_plan_path.read_text(encoding="utf-8"))
    del pb_plan["jobs"]["unit"]["preexisting_skip"]
    dropped = world.write_plan("plan-dropped-annot.json", pb_plan)
    gate.assert_eq(
        world.reconcile(dropped, pb_jobs),
        1,
        "a dropped annotation the conditions imply must hard-fail too",
    )
    gate.assert_contains(
        world.err,
        "the plan's conditions yield 'pointer_bump_only'",
        "stating what the conditions actually imply",
    )

    # A condition name that does not exist cannot be smuggled in either.
    jobs = healthy_jobs()
    find(jobs, "Tests + Infra / E2E Ceph")["conclusion"] = "skipped"
    ceph_skipped = world.write_jobs("jobs-ceph-skipped.json", jobs)
    plan = world.base_plan()
    plan["conditions"] = {}
    plan["jobs"]["e2e_ceph"]["preexisting_skip"] = "the_weather"
    invented = world.write_plan("plan-invented.json", plan)
    gate.assert_eq(
        world.reconcile(invented, ceph_skipped), 1, "an invented condition name must hard-fail"
    )
    gate.assert_contains(
        world.err,
        "preexisting-claim-mismatch: 'e2e_ceph' claims 'the_weather'",
        "naming the invention",
    )

    # CONTROL: a plan annotated by the real writer agrees with itself.
    gate.assert_eq(
        world.reconcile(pb_plan_path, pb_jobs),
        0,
        "an annotatePlan-written plan reconciles clean",
    )
    gate.log_pass("the per-job annotation is cross-checked against the conditions, both directions")


def test_strict_mode_is_the_module_default(gate, tmp_path):
    """The two consumers want opposite things. The GATE must not red a pointer-bump run;
    the BASELINE READER (scope-engine's attestPlan) must not accept that run as proof, because it validated nothing. Same plan, same jobs, opposite verdict, decided by the flag alone."""
    world = make_world(gate, tmp_path)
    pb_jobs = world.write_jobs("jobs-pointer-bump.json", pointer_bump_jobs())
    pb_plan = world.annotate(
        world.plan_path,
        "plan-pointer-bump.json",
        {"pointer_bump_only": True, "full_suite": True, "is_bot": False},
    )
    strict = world.reconcile_module(pb_plan, pb_jobs, False)
    lenient = world.reconcile_module(pb_plan, pb_jobs, True)
    gate.assert_contains(
        strict,
        "false|planned-run-but-skipped",
        "the module default refuses a pointer-bump run as a baseline",
    )
    gate.assert_contains(
        strict,
        "pre-existing condition pointer_bump_only was active",
        "and says WHY, since attestPlan only ever surfaces the first failure string",
    )
    gate.assert_contains(strict, "this run is not proof that it ran", "in those words")
    gate.assert_contains(lenient, "true|", "while the gate, which opts in, passes the same input")
    gate.assert_contains(lenient, "exempt=18", "having excused all eighteen keys")

    # CONTROL: the flag is not a blanket mute. On the healthy fixture, where no condition is active, both modes agree and both pass.
    gate.assert_contains(
        world.reconcile_module(world.plan_path, world.jobs_path, False),
        "true||exempt=0",
        "no conditions, strict mode passes",
    )
    gate.assert_contains(
        world.reconcile_module(world.plan_path, world.jobs_path, True),
        "true||exempt=0",
        "and lenient mode passes identically",
    )
    gate.log_pass(
        "honorPreexisting defaults to false, so a baseline reader still refuses an unproven run"
    )


def test_exempt_key_that_ran_warns_only(gate, tmp_path):
    """An exemption handed out where the job ran anyway means the condition table over-claims. Worth saying, never worth blocking: there is no failure to mask when a planned-run job actually ran."""
    world = make_world(gate, tmp_path)
    pb_plan = world.annotate(
        world.plan_path,
        "plan-pointer-bump.json",
        {"pointer_bump_only": True, "full_suite": True, "is_bot": False},
    )
    gate.assert_eq(
        world.reconcile(pb_plan, world.jobs_path),
        0,
        "a fully-exempt plan against a fully-green run must not fail",
    )
    gate.assert_contains(
        world.out,
        "::warning::preexisting-exempt-but-ran: 'unit'",
        "but the over-broad exemption is warned about, on stdout",
    )
    gate.assert_contains(world.out, "the condition table may be over-broad", "with the diagnosis")
    gate.assert_not_contains(world.err, "FAIL", "and nothing lands on stderr")

    # CONTROL: the warning is earned. When the exempt keys really skipped, silence.
    pb_jobs = world.write_jobs("jobs-pointer-bump.json", pointer_bump_jobs())
    gate.assert_eq(
        world.reconcile(pb_plan, pb_jobs), 0, "the same plan against the skipped run is clean"
    )
    gate.assert_not_contains(world.out, "::warning::", "with no warning at all")
    gate.log_pass("an exemption that was not needed warns; one that was is silent")


def test_exemptions_never_mask_a_failure(gate, tmp_path):
    """The house invariant, restated for the new path: warnings never mask failures, and neither do exemptions. Mix all three in one run."""
    world = make_world(gate, tmp_path)
    push_plan_path = world.annotate(
        world.plan_path,
        "plan-push.json",
        {"pointer_bump_only": False, "full_suite": False, "is_bot": False},
    )
    push_plan = json.loads(push_plan_path.read_text(encoding="utf-8"))
    push_plan["jobs"]["package_tests"] = {
        "run": False,
        "reason": "out-of-scope",
        "preexisting_skip": push_plan["jobs"]["package_tests"].get("preexisting_skip"),
    }
    mixed_plan = world.write_plan("plan-push-mixed.json", push_plan)

    jobs = push_jobs()
    find(jobs, "Tests + Infra / Linux Packages")["conclusion"] = "success"
    for job in jobs:
        if job["name"].startswith(INSTALL_PREFIX):
            job["conclusion"] = "skipped"
    mixed_jobs = world.write_jobs("jobs-push-mixed.json", jobs)

    gate.assert_eq(
        world.reconcile(mixed_plan, mixed_jobs),
        1,
        "an exemption alongside a warning still exits non-zero on a real failure",
    )
    gate.assert_contains(
        world.err, "planned-run-but-skipped: 'install_methods'", "the failure is on stderr"
    )
    gate.assert_contains(
        world.out, "::warning::planned-skip-but-ran: 'package_tests'", "the warning is on stdout"
    )
    gate.assert_contains(
        world.out, "unit (full_suite)", "and the exempt list is still printed on failure"
    )
    gate.log_pass("exemptions and warnings both fail to mask a real failure")


def test_condition_table_cannot_rot_silently(gate):
    """Same discipline as the name-table parity check: an entry naming a key that no longer exists is an exemption that can never apply, and a condition missing from CONDITION_ORDER would be evaluated by nothing. Both are silent, both are rot."""
    verdicts = node_eval(
        """
const r = require(process.argv[1]);
const out = [];
const T = () => JSON.parse(JSON.stringify(r.PREEXISTING_CONDITIONS));
const run = (label, conds, order) => {
  try { r.validateConditionTable(conds, order, r.EXPECTED_JOB_NAMES); out.push(label + ":no-throw"); }
  catch (e) { out.push(label + ":" + e.message); }
};
const badKey = T(); badKey.full_suite.keys.push("no_such_job");
run("badkey", badKey, r.CONDITION_ORDER);
run("unordered", T(), r.CONDITION_ORDER.filter((c) => c !== "is_bot"));
const orphan = T(); delete orphan.is_bot;
run("orphan", orphan, r.CONDITION_ORDER);
const bad = T(); bad.is_bot.activeWhen = "true";
run("nonbool", bad, r.CONDITION_ORDER);
run("real", r.PREEXISTING_CONDITIONS, r.CONDITION_ORDER);
process.stdout.write(out.join("\\n"));
""",
        str(RECONCILE),
    )
    gate.assert_contains(
        verdicts,
        "badkey:PREEXISTING_CONDITIONS.full_suite names unknown plan key 'no_such_job'",
        "a condition naming a dead plan key throws",
    )
    gate.assert_contains(
        verdicts,
        "unordered:CONDITION_ORDER omits 'is_bot'",
        "a condition absent from the evaluation order throws",
    )
    gate.assert_contains(
        verdicts,
        "orphan:CONDITION_ORDER has orphan condition 'is_bot'",
        "an order entry with no condition behind it throws",
    )
    gate.assert_contains(
        verdicts,
        "nonbool:PREEXISTING_CONDITIONS.is_bot has a non-boolean activeWhen",
        "a non-boolean activeWhen throws, since the compare is strict",
    )
    gate.assert_contains(verdicts, "real:no-throw", "and the real tables pass")

    # Behavioural counterpart to the table: the key sets are the ones the workflow evidence supports, asserted by size so a silent widening shows.
    sizes = node_eval(
        """
const r = require(process.argv[1]);
const n = (c) => r.PREEXISTING_CONDITIONS[c].keys.length;
process.stdout.write(`pb=${n("pointer_bump_only")} fs=${n("full_suite")} bot=${n("is_bot")}`);
""",
        str(RECONCILE),
    )
    gate.assert_eq(
        sizes,
        "pb=18 fs=17 bot=1",
        "pointer_bump_only cuts all 18, full_suite 17 (not install_methods), is_bot 1",
    )
    gate.log_pass("the condition table cannot rot or widen silently")


def test_usage_errors_are_loud(gate, tmp_path):
    """Forgetting a flag is a wiring bug and must be non-zero, not a default."""
    world = make_world(gate, tmp_path)
    result = harness.run(
        [
            node_bin(),
            str(RECONCILE),
            "--plan",
            str(world.plan_path),
            "--jobs",
            str(world.jobs_path),
        ],
        timeout=120,
    )
    gate.assert_eq(result.rc, 2, "a missing --run-id is a usage error, exit 2")
    gate.assert_contains(result.err, "--run-id", "naming the missing flag")
    gate.log_pass("missing wiring flags exit non-zero")
