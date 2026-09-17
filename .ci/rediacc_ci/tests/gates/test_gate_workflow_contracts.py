"""Port of `.ci/scripts/test/gates/test-workflow-contracts.sh`.

Both-ways test for the reusable-workflow contract checks in `.ci/scripts/security/check-workflow-gates.sh`: CHECK 2 (callers in this repo), CHECK 4 (callers in other repositories, declared in `.github/external-callers.yml`) and arm a2 (a `workflow_call` secret declaration nothing reads).

WHY THIS CLASS NEEDS A GATE AT ALL. Inside a reusable workflow, `secrets.FOO` for a secret nobody declared under `on.workflow_call.secrets` evaluates to the EMPTY STRING: no warning, no failure, no log line. `cd-deploy-account.yml` read
`OTLP_CLIENT_CREDENTIALS_{EU,US,ASIA}` that way, so every deployed account Worker ran
with a blank telemetry credential. The failure is invisible at every layer except a
parser that compares declaration to use, which is what this asserts.

Both directions matter, and the too-loud direction has already cost a nightly: `secrets: inherit`, `GITHUB_TOKEN`, optional inputs and a script filename ending in `-secrets.sh` must NOT be reported. Arm a2's liveness sweep shipped with no test at all and reddened `test-slim-timeout.sh` plus every case in the twin, because the sweep ran on FIXTURE trees and judged them against the
real tree's exemption list (nightly 34014201256). `test_liveness_stands_down_on_fixture_trees` is that regression, kept verbatim.

WHAT THE PORT KEEPS. Every fixture is written into pytest's own `tmp_path`, and the subject is driven with `WORKFLOWS_DIR` / `EXTERNAL_CALLERS_FILE` / `EXTERNAL_CALLERS_ROOT` as an env OVERLAY per invocation, exactly as the twin does. The twin's three `sed -i` edits become Python string replacement on the same bytes, and its inline `python3 - <<PYX` heredoc becomes an ordinary
function, which is the only place the port is shorter rather than merely different.

ONE CASE READS THE REAL TREE, and it is the case that makes the other 28 worth having: `test_ec_real_registry_is_wired` drives the subject with no override at all, so a fixture-only suite cannot pass while CI checks nothing. It is READ-ONLY, which is why this twin is not in the lock's real-tree set and needs no `xdist_group`.
"""

import pathlib
import shutil

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

BASH_TWIN = ".ci/scripts/test/gates/test-workflow-contracts.sh"

CHECK = paths.from_root(".ci", "scripts", "security", "check-workflow-gates.sh")

WITH_OK = "    with:\n      target: stable"
SECRETS_OK = "    secrets:\n      DECLARED: ${{ secrets.DECLARED }}"


def _bash() -> str:
    return harness.require_tool("bash", "install bash; the subject is a bash script")


def run_check(directory, **overlay) -> harness.RunResult:
    """Drive the subject with `CI=true` and the twin's env overlay. Streams MERGED."""
    if not CHECK.is_file():
        raise harness.GateAssertionError(
            "%s is missing; this gate has nothing to prove" % paths.relative_to_root(CHECK)
        )
    env = {"CI": "true"}
    if directory is not None:
        env["WORKFLOWS_DIR"] = str(directory)
    env.update(overlay)
    return harness.run([_bash(), str(CHECK)], env=env, timeout=300)


def write_callee(d: pathlib.Path, extra: str = "") -> None:
    """A reusable workflow declaring one required input and one required secret.

    It READS both declared secrets. Arm a2 reports a declaration nothing reads, so a fixture that declares `OPTIONAL_ONE` and ignores it is itself the defect, and it made every case in the twin fail once. `OPTIONAL_ONE` stays optional, which is what the caller-side assertions actually exercise.
    """
    (d / "callee.yml").write_text(
        "name: callee\n"
        "on:\n"
        "  workflow_call:\n"
        "    inputs:\n"
        "      target:\n"
        "        required: true\n"
        "        type: string\n"
        "    secrets:\n"
        "      DECLARED:\n"
        "        required: true\n"
        "      OPTIONAL_ONE:\n"
        "        required: false\n"
        "jobs:\n"
        "  j:\n"
        "    runs-on: ubuntu-latest\n"
        "    steps:\n"
        '      - run: echo "${{ secrets.DECLARED }} ${{ secrets.OPTIONAL_ONE }}%s"\n' % extra,
        encoding="utf-8",
    )


def write_caller(d: pathlib.Path, with_block: str, secrets_block: str) -> None:
    (d / "caller.yml").write_text(
        "name: caller\non: push\njobs:\n  c:\n"
        "    uses: ./.github/workflows/callee.yml\n%s\n%s\n" % (with_block, secrets_block),
        encoding="utf-8",
    )


def write_exempt(d: pathlib.Path, reads: bool) -> None:
    """The one file `DECLARED_UNUSED_OK` actually names, so the sweep judges something real."""
    body = (
        '- run: echo "${{ secrets.ANTHROPIC_CLAUDE_CODE_OAUTH_TOKEN }}"'
        if reads
        else "- run: echo hi"
    )
    (d / "claude-review-reusable.yml").write_text(
        "name: claude-review-reusable\n"
        "on:\n"
        "  workflow_call:\n"
        "    secrets:\n"
        "      ANTHROPIC_CLAUDE_CODE_OAUTH_TOKEN:\n"
        "        required: false\n"
        "jobs:\n"
        "  j:\n"
        "    runs-on: ubuntu-latest\n"
        "    steps:\n"
        "      %s\n" % body,
        encoding="utf-8",
    )


# `DECLARED_UNUSED_OK` is drained to empty on the real tree (W8 P1b's "declared endgame"), so the differential injects this synthetic pair through the subject's own test-only seam to give the liveness sweep and arm (a3) a positive case at all. `write_exempt` builds the fixture file this pair names.
EXTRA_EXEMPTION = "claude-review-reusable.yml:ANTHROPIC_CLAUDE_CODE_OAUTH_TOKEN"


def run_check_live(directory) -> harness.RunResult:
    """CHECK 2 with the exemption liveness sweep forced ON against a fixture tree.

    SLIM coverage is pinned off because it defaults from the same flag and this fixture has no slim job to offer; CHECK 3 has its own test.
    """
    return run_check(
        directory,
        REAL_WORKFLOW_TREE="true",
        SLIM_TIMEOUT_REQUIRE_COVERAGE="false",
        WORKFLOW_GATES_EXTRA_EXEMPTIONS=EXTRA_EXEMPTION,
    )


def ec_fixture(d: pathlib.Path) -> pathlib.Path:
    """A callee, one external caller in a submodule tree, and a matching registry."""
    root = d / "tree"
    (root / ".github" / "workflows").mkdir(parents=True)
    (root / "private" / "acct" / ".github" / "workflows").mkdir(parents=True)
    (root / ".github" / "workflows" / "callee.yml").write_text(
        "name: callee\n"
        "on:\n"
        "  workflow_call:\n"
        "    inputs:\n"
        "      target:\n"
        "        required: true\n"
        "        type: string\n"
        "      opt:\n"
        "        required: false\n"
        "        type: string\n"
        "    secrets:\n"
        "      TOKEN:\n"
        "        required: true\n"
        "jobs:\n"
        "  j:\n"
        "    runs-on: ubuntu-latest\n"
        "    steps:\n"
        '      - run: echo "${{ secrets.TOKEN }}"\n',
        encoding="utf-8",
    )
    (root / "private" / "acct" / ".github" / "workflows" / "review.yml").write_text(
        "name: caller\n"
        "on: push\n"
        "jobs:\n"
        "  c:\n"
        "    uses: rediacc/console/.github/workflows/callee.yml@main\n"
        "    with:\n"
        "      target: x\n"
        "    secrets:\n"
        "      TOKEN: ${{ secrets.TOKEN }}\n",
        encoding="utf-8",
    )
    (root / "registry.yml").write_text(
        "callers:\n"
        "  - caller: private/acct/.github/workflows/review.yml\n"
        "    repo: rediacc/acct\n"
        "    pinned_at: main\n"
        "    calls: .github/workflows/callee.yml\n"
        "    passes_inputs: [target]\n"
        "    passes_secrets: [TOKEN]\n",
        encoding="utf-8",
    )
    return root


def run_ec(root: pathlib.Path) -> harness.RunResult:
    return run_check(
        root / ".github" / "workflows",
        EXTERNAL_CALLERS_FILE=str(root / "registry.yml"),
        EXTERNAL_CALLERS_ROOT=str(root),
    )


def edit(path: pathlib.Path, old: str, new: str) -> None:
    """The twin's `sed -i`, as a substitution that REFUSES a no-op.

    `sed -i s/a/b/` on a file not containing `a` exits 0 and changes nothing, so a fixture whose shape drifted would leave the case asserting against the unedited tree and still going green. Refusing here turns that into the finding it is.
    """
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise harness.GateAssertionError(
            "fixture edit found no %r in %s, so the case would have run against an "
            "UNEDITED fixture and proved nothing" % (old, path.name)
        )
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


# --- CHECK 2: callers in this repo -----------------------------------------


def test_clean_contract_passes(gate, tmp_path):
    write_callee(tmp_path)
    write_caller(tmp_path, WITH_OK, SECRETS_OK)
    result = run_check(tmp_path)
    gate.assert_exit_code(0, result.rc, "a complete, matching contract must pass")
    gate.log_pass("matching caller/callee contract passes")


def test_undeclared_secret_read_in_callee(gate, tmp_path):
    """The OTLP bug itself: read but never declared, so it silently evaluates to ""."""
    write_callee(tmp_path, " ${{ secrets.NEVER_DECLARED }}")
    write_caller(tmp_path, WITH_OK, SECRETS_OK)
    result = run_check(tmp_path)
    gate.assert_exit_code(1, result.rc, "reading an undeclared secret must fail")
    gate.assert_contains(
        result.combined, "reads secrets.NEVER_DECLARED", "names the undeclared secret"
    )
    gate.assert_contains(result.combined, 'silently evaluate to ""', "explains why it is invisible")
    gate.log_pass("callee reading an undeclared secret fails (the OTLP class)")


def test_caller_omits_required_secret(gate, tmp_path):
    write_callee(tmp_path)
    write_caller(tmp_path, WITH_OK, "    secrets:\n      OPTIONAL_ONE: ${{ secrets.OPTIONAL_ONE }}")
    result = run_check(tmp_path)
    gate.assert_exit_code(1, result.rc, "omitting a required secret must fail")
    gate.assert_contains(
        result.combined, "does not pass required secret DECLARED", "names the omitted secret"
    )
    gate.log_pass("caller omitting a required secret fails")


def test_caller_passes_undeclared_secret(gate, tmp_path):
    """Dead wiring: it reads as if the value flows, and it does not."""
    write_callee(tmp_path)
    write_caller(tmp_path, WITH_OK, SECRETS_OK + "\n      GHOST: ${{ secrets.GHOST }}")
    result = run_check(tmp_path)
    gate.assert_exit_code(1, result.rc, "passing a secret the callee never declares must fail")
    gate.assert_contains(result.combined, "passes secret GHOST", "names the dead wiring")
    gate.log_pass("caller passing an undeclared secret fails (dead wiring)")


def test_input_contract_both_directions(gate, tmp_path):
    write_callee(tmp_path)
    write_caller(tmp_path, "    with:\n      bogus: x", SECRETS_OK)
    result = run_check(tmp_path)
    gate.assert_exit_code(1, result.rc, "missing required input + undeclared input must fail")
    gate.assert_contains(
        result.combined, "does not pass required input target", "names the omitted input"
    )
    gate.assert_contains(result.combined, "passes input bogus", "names the undeclared input")
    gate.log_pass("input contract is asserted in both directions")


def test_optional_secret_may_be_omitted(gate, tmp_path):
    """Too-loud guard: `required: false` means exactly that."""
    write_callee(tmp_path)
    write_caller(tmp_path, WITH_OK, SECRETS_OK)
    result = run_check(tmp_path)
    gate.assert_exit_code(0, result.rc, "omitting an optional secret must not be reported")
    gate.log_pass("optional secrets may be omitted without a finding")


def test_secrets_inherit_is_not_flagged(gate, tmp_path):
    """`secrets: inherit` forwards everything; there is nothing to compare."""
    write_callee(tmp_path)
    write_caller(tmp_path, WITH_OK, "    secrets: inherit")
    result = run_check(tmp_path)
    gate.assert_exit_code(0, result.rc, "secrets: inherit must not be treated as a missing secret")
    gate.log_pass("secrets: inherit is accepted")


def test_github_token_is_implicit(gate, tmp_path):
    """GITHUB_TOKEN is always available and is never declared under workflow_call."""
    write_callee(tmp_path, " ${{ secrets.GITHUB_TOKEN }}")
    write_caller(tmp_path, WITH_OK, SECRETS_OK)
    result = run_check(tmp_path)
    gate.assert_exit_code(0, result.rc, "GITHUB_TOKEN must not be reported as undeclared")
    gate.log_pass("GITHUB_TOKEN is treated as implicit")


def test_script_filename_is_not_a_secret_reference(gate, tmp_path):
    """A naive `/secrets\\.(\\w+)/` reads the "sh" in `...-secrets.sh` as a secret."""
    write_callee(tmp_path)
    with (tmp_path / "callee.yml").open("a", encoding="utf-8") as handle:
        handle.write("      - run: .ci/scripts/deploy/set-account-worker-secrets.sh\n")
    write_caller(tmp_path, WITH_OK, SECRETS_OK)
    result = run_check(tmp_path)
    gate.assert_exit_code(
        0, result.rc, "a filename ending in -secrets.sh must not read as secrets.sh"
    )
    gate.log_pass("script filenames are not mistaken for secret references")


def test_missing_callee_is_reported(gate, tmp_path):
    write_caller(tmp_path, WITH_OK, SECRETS_OK)
    result = run_check(tmp_path)
    gate.assert_exit_code(1, result.rc, "calling a workflow that does not exist must fail")
    gate.assert_contains(result.combined, "does not exist", "names the missing callee")
    gate.log_pass("a call to a nonexistent local workflow fails")


def test_empty_tree_is_not_a_pass(gate, tmp_path):
    gate.assert_vacuous_tree_fails(
        run_check, tmp_path, "blind", "no workflows means nothing asserted, which must fail"
    )


# --- arm a2: a declaration nothing reads ------------------------------------


def test_declared_unused_secret_is_reported(gate, tmp_path):
    """The 57-declaration class: a caller passes a value that goes nowhere."""
    write_callee(tmp_path)
    write_caller(tmp_path, WITH_OK, SECRETS_OK)
    edit(
        tmp_path / "callee.yml",
        "      OPTIONAL_ONE:\n        required: false\n",
        "      OPTIONAL_ONE:\n        required: false\n      UNREAD_ONE:\n        required: false\n",
    )
    result = run_check(tmp_path)
    gate.assert_exit_code(1, result.rc, "a declaration nothing reads must fail")
    gate.assert_contains(
        result.combined, "declares secret UNREAD_ONE", "names the dead declaration"
    )
    gate.assert_contains(result.combined, "delete the declaration", "says what to do about it")
    gate.log_pass("a workflow_call secret nothing reads is reported")


def test_declared_and_read_is_not_reported(gate, tmp_path):
    """CONTROL. Without it, an arm flagging EVERY declaration is indistinguishable."""
    write_callee(tmp_path)
    write_caller(tmp_path, WITH_OK, SECRETS_OK)
    result = run_check(tmp_path)
    gate.assert_exit_code(0, result.rc, "a declared secret that IS read must not be reported")
    gate.assert_not_contains(result.combined, "never reads it", "no dead-declaration finding")
    gate.log_pass("CONTROL: a declaration the callee reads is left alone")


def test_liveness_reports_a_dangling_exemption(gate, tmp_path):
    write_callee(tmp_path)
    write_caller(tmp_path, WITH_OK, SECRETS_OK)
    result = run_check_live(tmp_path)
    gate.assert_exit_code(1, result.rc, "an exemption naming a file that is gone must fail")
    gate.assert_contains(result.combined, "which does not exist", "names the dangling exemption")
    gate.log_pass("the exemption liveness sweep reports a dangling entry")


def test_liveness_stands_down_on_fixture_trees(gate, tmp_path):
    """THE REGRESSION, verbatim. Same tree, sweep not forced: it must be silent."""
    write_callee(tmp_path)
    write_caller(tmp_path, WITH_OK, SECRETS_OK)
    result = run_check(tmp_path)
    gate.assert_exit_code(
        0, result.rc, "a fixture tree must not be judged against the real tree's exemptions"
    )
    gate.assert_not_contains(result.combined, "which does not exist", "the sweep stayed silent")
    gate.log_pass("CONTROL: the liveness sweep stands down on a fixture tree")


def test_liveness_honours_a_live_exemption(gate, tmp_path):
    """CONTROL: the exempted file present and still not reading the secret."""
    write_exempt(tmp_path, False)
    result = run_check_live(tmp_path)
    gate.assert_exit_code(0, result.rc, "a live exemption must suppress the finding")
    gate.assert_not_contains(
        result.combined,
        "ANTHROPIC_CLAUDE_CODE_OAUTH_TOKEN",
        "nothing reported for the exempted pair",
    )
    gate.log_pass("CONTROL: a live exemption suppresses its finding")


def test_liveness_reports_an_exemption_now_read(gate, tmp_path):
    """An exemption that has become unnecessary must be surfaced, not left as coverage."""
    write_exempt(tmp_path, True)
    result = run_check_live(tmp_path)
    gate.assert_exit_code(1, result.rc, "an exemption whose secret is now read must fail")
    gate.assert_contains(result.combined, "now READS", "says the exemption is obsolete")
    gate.log_pass("an exemption whose secret is now read is reported")


# --- CHECK 4: external-caller contracts -------------------------------------


def test_ec_clean_passes(gate, tmp_path):
    root = ec_fixture(tmp_path)
    result = run_ec(root)
    gate.assert_exit_code(
        0, result.rc, "a registry matching both the callee and the caller must pass"
    )
    gate.assert_contains(
        result.combined, "1 external caller call-site(s) verified", "reports what it verified"
    )
    gate.log_pass("matching external-caller registry passes")


def test_ec_registry_declares_undeclared_input(gate, tmp_path):
    root = ec_fixture(tmp_path)
    edit(root / "registry.yml", "passes_inputs: [target]", "passes_inputs: [target, ghost]")
    result = run_ec(root)
    gate.assert_exit_code(1, result.rc, "declaring an input the callee never declares must fail")
    gate.assert_contains(result.combined, "passes input ghost", "names the dead wiring")
    gate.log_pass("external caller passing an undeclared input fails")


def test_ec_registry_omits_required_secret(gate, tmp_path):
    root = ec_fixture(tmp_path)
    edit(root / "registry.yml", "passes_secrets: [TOKEN]", "passes_secrets: []")
    result = run_ec(root)
    gate.assert_exit_code(1, result.rc, "omitting a required secret must fail")
    gate.assert_contains(
        result.combined, "does not pass required secret TOKEN", "names the omitted secret"
    )
    gate.assert_contains(result.combined, "is not a fix", "refuses the required:false escape")
    gate.log_pass("external caller omitting a required secret fails")


def test_ec_caller_drifts_from_registry(gate, tmp_path):
    """The rot case: the other repo's file changed, the registry did not."""
    root = ec_fixture(tmp_path)
    edit(
        root / "private" / "acct" / ".github" / "workflows" / "review.yml",
        "      target: x\n",
        "      target: x\n      opt: y\n",
    )
    result = run_ec(root)
    gate.assert_exit_code(1, result.rc, "a registry that no longer describes the caller must fail")
    gate.assert_contains(
        result.combined, "registry declares ['target']", "shows both sides of the drift"
    )
    gate.log_pass("registry drifting from the caller's real file fails")


def test_ec_pin_drift_is_reported(gate, tmp_path):
    root = ec_fixture(tmp_path)
    edit(
        root / "private" / "acct" / ".github" / "workflows" / "review.yml",
        "callee.yml@main",
        "callee.yml@v1",
    )
    result = run_ec(root)
    gate.assert_exit_code(1, result.rc, "a ref the registry does not claim must fail")
    gate.assert_contains(result.combined, "registry says @main", "names the expected ref")
    gate.log_pass("caller pinned at an unregistered ref fails")


def test_ec_unregistered_caller_is_reported(gate, tmp_path):
    root = ec_fixture(tmp_path)
    other = root / "private" / "other" / ".github" / "workflows"
    other.mkdir(parents=True)
    (other / "review.yml").write_text(
        (root / "private" / "acct" / ".github" / "workflows" / "review.yml").read_text(
            encoding="utf-8"
        ),
        encoding="utf-8",
    )
    result = run_ec(root)
    gate.assert_exit_code(1, result.rc, "an external caller nobody registered must fail")
    gate.assert_contains(
        result.combined,
        "private/other/.github/workflows/review.yml",
        "names the unregistered file",
    )
    gate.assert_contains(result.combined, "not declared in registry.yml", "says what is missing")
    gate.log_pass("an unregistered external caller fails (completeness)")


def test_ec_deleted_callee_is_reported(gate, tmp_path):
    """Invisible to CHECK 2 once no local caller remains, and it strands the external ones."""
    root = ec_fixture(tmp_path)
    (root / ".github" / "workflows" / "callee.yml").unlink()
    result = run_ec(root)
    gate.assert_exit_code(1, result.rc, "deleting a callee an external caller depends on must fail")
    gate.assert_contains(
        result.combined, "the callee does not exist in this repo", "names the stranded call"
    )
    gate.log_pass("deleting an externally-called workflow fails")


def test_ec_missing_file_in_checked_out_tree(gate, tmp_path):
    root = ec_fixture(tmp_path)
    (root / "private" / "acct" / ".github" / "workflows" / "review.yml").unlink()
    other = root / "private" / "other" / ".github" / "workflows"
    other.mkdir(parents=True)
    (other / "unrelated.yml").write_text(
        (root / ".github" / "workflows" / "callee.yml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    result = run_ec(root)
    gate.assert_exit_code(
        1, result.rc, "a registry entry whose file is gone from a checked-out tree must fail"
    )
    gate.assert_contains(
        result.combined, "absent from a checked-out tree", "says the entry is stale"
    )
    gate.log_pass("a stale registry entry fails when its tree is present")


def test_ec_absent_submodule_is_blind_not_pass(gate, tmp_path):
    """Anti-vacuity in the shape that happens: `npm run ci` with no submodules out."""
    root = ec_fixture(tmp_path)
    shutil.rmtree(root / "private")
    result = run_ec(root)
    gate.assert_exit_code(1, result.rc, "no submodule tree means nothing asserted, which must fail")
    gate.assert_contains(
        result.combined, "this check is blind", "says the check has nothing to assert"
    )
    gate.log_pass("an absent submodule tree fails rather than passing vacuously")


def test_ec_empty_registry_is_blind_not_pass(gate, tmp_path):
    root = ec_fixture(tmp_path)
    (root / "registry.yml").write_text("callers: []\n", encoding="utf-8")
    result = run_ec(root)
    gate.assert_exit_code(1, result.rc, "an emptied registry must fail rather than assert nothing")
    gate.assert_contains(result.combined, "declares no callers", "names the empty registry")
    gate.log_pass("emptying the registry fails (anti-vacuity)")


def test_ec_fixture_tree_skips_cleanly(gate, tmp_path):
    """The skip is reachable only when the registry env is unset AND the tree is not real."""
    write_callee(tmp_path)
    write_caller(tmp_path, WITH_OK, SECRETS_OK)
    result = run_check(tmp_path)
    gate.assert_exit_code(0, result.rc, "a CHECK 2 fixture tree must still pass")
    gate.assert_contains(
        result.combined, "Skipping external-caller contract check", "says it stood down"
    )
    gate.log_pass("CHECK 4 stands down on fixture trees, audibly")


def test_ec_real_registry_is_wired(gate):
    """The registry is only worth having if the real run reads the real file.

    Without this, every case above could pass against fixtures while the gate checked nothing in CI. READ-ONLY on the real tree: no override, no write.
    """
    result = run_check(None)
    gate.assert_exit_code(
        0, result.rc, "the real tree must satisfy its own external-caller registry"
    )
    gate.assert_contains(
        result.combined, "external caller call-site(s) verified", "the real run reached CHECK 4"
    )
    gate.log_pass("the real .github/external-callers.yml is enforced, not just fixtures")


# --- arm a3: the exemption list must be justified by the registry ------------
#
# Arm a2 may be silenced for exactly one reason: a caller in ANOTHER repository still passes the secret, so deleting the declaration breaks their next run rather than this PR. That justification used to live in a COMMENT above `DECLARED_UNUSED_OK`, and a comment cannot go stale loudly: retire the external caller and the exemption survives it, looking like coverage. Arm a3 makes the
# two sides one set equality, and these cases drive both directions plus the two ways it has to stay quiet.


def a3_fixture(d: pathlib.Path) -> pathlib.Path:
    """The exempted callee, an external caller passing it, and a registry agreeing."""
    root = d / "tree"
    (root / ".github" / "workflows").mkdir(parents=True)
    (root / "private" / "acct" / ".github" / "workflows").mkdir(parents=True)
    (root / ".github" / "workflows" / "claude-review-reusable.yml").write_text(
        "name: claude-review-reusable\n"
        "on:\n"
        "  workflow_call:\n"
        "    secrets:\n"
        "      ANTHROPIC_CLAUDE_CODE_OAUTH_TOKEN:\n"
        "        required: false\n"
        "jobs:\n"
        "  j:\n"
        "    runs-on: ubuntu-latest\n"
        "    steps:\n"
        "      - run: echo hi\n",
        encoding="utf-8",
    )
    (root / "private" / "acct" / ".github" / "workflows" / "review.yml").write_text(
        "name: caller\n"
        "on: push\n"
        "jobs:\n"
        "  c:\n"
        "    uses: rediacc/console/.github/workflows/claude-review-reusable.yml@main\n"
        "    secrets:\n"
        "      ANTHROPIC_CLAUDE_CODE_OAUTH_TOKEN: "
        "${{ secrets.ANTHROPIC_CLAUDE_CODE_OAUTH_TOKEN }}\n",
        encoding="utf-8",
    )
    (root / "registry.yml").write_text(
        "callers:\n"
        "  - caller: private/acct/.github/workflows/review.yml\n"
        "    repo: rediacc/acct\n"
        "    pinned_at: main\n"
        "    calls: .github/workflows/claude-review-reusable.yml\n"
        "    passes_inputs: []\n"
        "    passes_secrets: [ANTHROPIC_CLAUDE_CODE_OAUTH_TOKEN]\n",
        encoding="utf-8",
    )
    return root


def run_ec_live(root: pathlib.Path) -> harness.RunResult:
    """`run_ec` with the real-tree flag forced on, so the a2 sweep and a3 both run.

    SLIM coverage is pinned off: it defaults from the same flag and this fixture has no slim job to offer.
    """
    return run_check(
        root / ".github" / "workflows",
        EXTERNAL_CALLERS_FILE=str(root / "registry.yml"),
        EXTERNAL_CALLERS_ROOT=str(root),
        REAL_WORKFLOW_TREE="true",
        SLIM_TIMEOUT_REQUIRE_COVERAGE="false",
        WORKFLOW_GATES_EXTRA_EXEMPTIONS=EXTRA_EXEMPTION,
    )


def test_a3_pinned_exemption_passes(gate, tmp_path):
    """CONTROL, and the load-bearing one: quiet, and audible about what it compared."""
    root = a3_fixture(tmp_path)
    result = run_ec_live(root)
    gate.assert_exit_code(0, result.rc, "an exemption the registry pins alive must pass")
    gate.assert_contains(
        result.combined,
        "arm (a3): 1 declared-unused exemption(s) == 1 pinned alive",
        "prints the shape it compared, not just a verdict",
    )
    gate.log_pass("CONTROL: an exemption pinned alive by the registry passes")


def test_a3_unpinned_exemption_is_reported(gate, tmp_path):
    """The rot: the external caller stopped passing it and the exemption outlived it."""
    root = a3_fixture(tmp_path)
    edit(
        root / "registry.yml",
        "passes_secrets: [ANTHROPIC_CLAUDE_CODE_OAUTH_TOKEN]",
        "passes_secrets: []",
    )
    edit(
        root / "private" / "acct" / ".github" / "workflows" / "review.yml",
        "    secrets:\n      ANTHROPIC_CLAUDE_CODE_OAUTH_TOKEN: "
        "${{ secrets.ANTHROPIC_CLAUDE_CODE_OAUTH_TOKEN }}\n",
        "",
    )
    result = run_ec_live(root)
    gate.assert_exit_code(1, result.rc, "an exemption nothing pins alive must fail")
    gate.assert_contains(result.combined, "pins it alive", "says the justification is gone")
    gate.assert_contains(
        result.combined,
        "delete the declaration and the exemption, not the check",
        "says what to do instead of suppressing",
    )
    gate.log_pass("an exemption no external caller justifies is reported")


def test_a3_pinned_but_unexempted_is_reported(gate, tmp_path):
    """The other direction: registry pins a declared-unread pair the list never names."""
    root = a3_fixture(tmp_path)
    (root / ".github" / "workflows" / "other.yml").write_text(
        "name: other\n"
        "on:\n"
        "  workflow_call:\n"
        "    secrets:\n"
        "      UNUSED_TOKEN:\n"
        "        required: false\n"
        "jobs:\n"
        "  j:\n"
        "    runs-on: ubuntu-latest\n"
        "    steps:\n"
        "      - run: echo hi\n",
        encoding="utf-8",
    )
    (root / "private" / "acct" / ".github" / "workflows" / "other-caller.yml").write_text(
        "name: other-caller\n"
        "on: push\n"
        "jobs:\n"
        "  c:\n"
        "    uses: rediacc/console/.github/workflows/other.yml@main\n"
        "    secrets:\n"
        "      UNUSED_TOKEN: ${{ secrets.UNUSED_TOKEN }}\n",
        encoding="utf-8",
    )
    with (root / "registry.yml").open("a", encoding="utf-8") as fh:
        fh.write(
            "  - caller: private/acct/.github/workflows/other-caller.yml\n"
            "    repo: rediacc/acct\n"
            "    pinned_at: main\n"
            "    calls: .github/workflows/other.yml\n"
            "    passes_inputs: []\n"
            "    passes_secrets: [UNUSED_TOKEN]\n"
        )
    result = run_ec_live(root)
    gate.assert_exit_code(1, result.rc, "a pinned declared-unused secret the list omits must fail")
    gate.assert_contains(
        result.combined, "pins other.yml/UNUSED_TOKEN alive", "names the unreconciled pair"
    )
    gate.log_pass("a registry-pinned pair the exemption list omits is reported")


def test_a3_empty_registry_is_blind_not_pass(gate, tmp_path):
    """Zero inputs is a failure: with no entries the arm asserts nothing either way."""
    root = a3_fixture(tmp_path)
    (root / "registry.yml").write_text("callers: []\n", encoding="utf-8")
    result = run_ec_live(root)
    gate.assert_exit_code(1, result.rc, "an emptied registry must fail rather than assert nothing")
    gate.assert_contains(result.combined, "arm (a3)", "a3 says it is blind, not just CHECK 4")
    gate.assert_contains(result.combined, "this arm is blind", "names the vacuity")
    gate.log_pass("a3 refuses an empty registry (anti-vacuity)")


def test_a3_stands_down_without_a_registry(gate, tmp_path):
    """CONTROL, the regression a2's liveness sweep already paid for once.

    An arm that cannot see the registry must stay SILENT rather than condemn a fixture tree for lacking one.
    """
    # The a3 arm itself is what must stay silent, not the unrelated per-file "declares but never reads" check that a3_fixture's callee trips on its own merit and that runs regardless of real_tree -- the same synthetic exemption run_ec_live uses keeps that check quiet here too.
    root = a3_fixture(tmp_path)
    result = run_check(
        root / ".github" / "workflows",
        EXTERNAL_CALLERS_FILE=str(root / "registry.yml"),
        EXTERNAL_CALLERS_ROOT=str(root),
        WORKFLOW_GATES_EXTRA_EXEMPTIONS=EXTRA_EXEMPTION,
    )
    gate.assert_exit_code(
        0, result.rc, "a non-real tree must not be judged against the real exemption list"
    )
    gate.assert_not_contains(result.combined, "arm (a3)", "the arm stayed silent")
    gate.log_pass("CONTROL: a3 stands down when the tree is not the real one")
