"""Port of `.ci/scripts/test/gates/test-breakpoint-secret-exposure.sh`.

breakpoint must never route an access credential through a step `env:`.

WHY THIS GATE EXISTS -- it is a regression test for a LIVE leak, not a hypothetical. Run 30254567365 (public repo, email channel, 2026-07-27) sent the access email correctly AND published the tunnel URL in cleartext::

    09:39:32.5205053Z   BP_URL: https://program-explore-lucia-graduated.trycloudflare.com
    09:39:36.1644525Z ✓ access details emailed to muhammed@rediacc.com

The runner prints a step's `env:` block BEFORE the step's script runs, and `::add-mask::` only redacts occurrences that appear AFTER it registers, so
`env: BP_URL: ${{ steps.tunnel.outputs.url }}` published the URL roughly four seconds
before `publish-endpoints.sh` could mask it. The email channel is the DEFAULT precisely because a quick-mode URL is a bearer credential to a box holding the repo source and (with debug-shell) an interactive shell, so the leak defeated the entire control while every step still reported success. No other gate can see it: it is a property of the workflow YAML's data flow, invisible to
shellcheck, shfmt, check-commands and the drift manifest, which proves the file is UNCHANGED rather than
CORRECT.

WHY THE DRIVER PORTED THIS AND NOT AN AGENT. `agent/8f55d4f0/W7P3-batch5-brief.md` records six `test-breakpoint-*.sh` subjects as unportable by any agent under the standard brief and NOT on merit, because plant-verifying one means temporarily writing under `.ci/breakpoint/**`, which invariant 8 forbids any sweep from touching. The brief's two ways out are to hand one batch owner
that path explicitly or to exclude them in the derivation with the reason recorded, and it adds "Do not silently drop them a fourth time." This is the first option: `.ci/breakpoint` is the driver's path.

`GITHUB_ACTIONS=true` IS THE LOAD-BEARING PART of the last case, carried verbatim from
the twin. Both helpers no-op without it, so the identical check run locally passes
while the bug is fully present -- which is exactly how it reached CI.

NO `xdist_group`. Every case reads tracked files or runs one short-lived `bash -c`;
the only writes go into a per-case `mktemp -d`.
"""

import difflib
import os
import re

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

BASH_TWIN = ".ci/scripts/test/gates/test-breakpoint-secret-exposure.sh"

BP = paths.from_root(".ci", "breakpoint")
WORKFLOW = BP / "workflow" / "breakpoint.yml"
LIVE_WORKFLOW = paths.from_root(".github", "workflows", "breakpoint.yml")

# The expressions that resolve to an access credential. Each one is a value a human can use to reach the running box.
CREDENTIAL_EXPRESSIONS = (
    "steps.tunnel.outputs.url",
    "steps.shell.outputs.ssh-connection",
    "steps.shell.outputs.web-url",
    "steps.shell.outputs.ssh-ro-connection",
    "steps.shell.outputs.web-ro-url",
)


def credential_hits(path) -> list[str]:
    """Every `<line-number>:<line>` in `path` carrying a credential expression.

    FACTORED OUT for the same reason the twin factors out `detect_credential_exposure`: the anti-vacuity case below points it at a deliberately broken copy, and a detector that only ever runs against the real file has never been shown to fire. The twin returns 1 and prints; this returns the hits, because a caller that must decide whether the detector FIRED needs the evidence rather
    than an exit code.
    """
    return [
        "%d:%s" % (number, line)
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1)
        if any(expression in line for expression in CREDENTIAL_EXPRESSIONS)
    ]


def test_no_credential_expression_in_workflow(gate):
    """Deliberately WHOLE-FILE rather than scoped to `env:` blocks. A credential has no
    legitimate use in workflow text at all -- `run:` interpolation is already banned as script injection, and `env:` is this leak -- so whole-file is both stricter and
    simpler to reason about than a YAML-aware env-block parse."""
    if not WORKFLOW.is_file():
        gate.log_fail("workflow template is missing: %s" % paths.relative_to_root(WORKFLOW))
    hits = credential_hits(WORKFLOW)
    if hits:
        gate.log_fail(
            "workflow routes access credentials through the log; the runner prints env: "
            "blocks BEFORE the step runs, so these are published before they can be "
            "masked. Pass them through the session state file instead "
            "(bp_state_set/get). Hits: %s" % "; ".join(hits)
        )
    gate.log_pass(
        "no access credential is interpolated into the workflow (%d expressions checked)"
        % len(CREDENTIAL_EXPRESSIONS)
    )


def test_detector_fires_on_the_real_leak(gate):
    """ANTI-VACUITY, BY MUTATION AND NOT BY ASSERTION. A gate that has only ever been
    seen to pass has not been verified. This reconstructs the exact line that leaked in run 30254567365, points the detector at it, and asserts it trips; weaken the expression list or the scan and THIS case goes red rather than the gate going quietly blind.

    It also avoids the trap the twin's first version fell into: asserting the guarded output names still exist in the scripts. After the fix they legitimately do not -- the whole point is that nothing emits them any more -- so that check failed on a correct tree and would have been "fixed" by deleting it.
    """
    with harness.temp_dir() as tmp:
        broken = tmp / "leaky-breakpoint.yml"
        # Verbatim shape of the line that leaked, reinstated.
        broken.write_text(
            WORKFLOW.read_text(encoding="utf-8")
            + "          BP_URL: ${{ steps.tunnel.outputs.url }}\n",
            encoding="utf-8",
        )
        if not credential_hits(broken):
            gate.log_fail(
                "detector did NOT fire on a workflow containing the exact line that "
                "leaked in run 30254567365 -- this gate is blind"
            )
    gate.log_pass("detector fires on the reinstated leak line (proven by mutation, not asserted)")


def test_publish_reads_state(gate):
    script = BP / "scripts" / "publish-endpoints.sh"
    if not script.is_file():
        gate.log_fail("missing %s" % paths.relative_to_root(script))
    gate.assert_contains(
        script.read_text(encoding="utf-8"),
        "bp_state_get BP_PUBLIC_URL",
        "publish-endpoints.sh must read the URL from session state, not from env",
    )
    gate.log_pass("publish-endpoints.sh reads the URL from the session state file")


def test_shell_does_not_mask_unconditionally(gate):
    """The first version of this feature masked the tmate strings the moment they were
    created. Masking is irreversible within a run, so on the logs channel the operator got `SSH: ***` -- a shell nobody could reach. Same rule as the URL, opposite direction: never mask without a working alternative channel, and never publish without one either. `publish-endpoints.sh` owns both decisions because it is the
    only thing that knows which channel is live."""
    script = BP / "scripts" / "start-shell.sh"
    if not script.is_file():
        gate.log_fail("missing %s" % paths.relative_to_root(script))
    unconditional = re.compile(r'^\s*\[\[ -n "\$s" \]\] && bp_gha_mask', re.MULTILINE)
    if unconditional.search(script.read_text(encoding="utf-8")):
        gate.log_fail(
            "start-shell.sh masks connection strings unconditionally; the logs channel "
            "then prints '***' and the session is unreachable"
        )
    gate.log_pass("start-shell.sh leaves the masking decision to publish-endpoints.sh")


def test_live_workflow_matches_template(gate):
    """The leak was fixed in the template; if the copy under `.github/workflows/` is
    stale, the fix is not deployed and the next dispatch leaks again."""
    if not LIVE_WORKFLOW.is_file():
        gate.log_pass("no live workflow copy in this repo (template-only checkout)")
        return
    template = WORKFLOW.read_text(encoding="utf-8")
    live = LIVE_WORKFLOW.read_text(encoding="utf-8")
    if template != live:
        diff = "".join(
            difflib.unified_diff(
                template.splitlines(keepends=True),
                live.splitlines(keepends=True),
                fromfile=paths.relative_to_root(WORKFLOW),
                tofile=paths.relative_to_root(LIVE_WORKFLOW),
            )
        )
        gate.log_fail(
            ".github/workflows/breakpoint.yml differs from the template; the fix may "
            "not be deployed.\n%s" % diff
        )
    gate.log_pass("live workflow is byte-identical to the template")


def test_workflow_commands_never_hit_stdout(gate):
    """`bp_gha_mask`/`bp_gha_warning` emit `::add-mask::` / `::warning::` lines. Several
    scripts here have a stdout DATA CONTRACT (`start-tunnel.sh` prints exactly one line,
    the URL, and the workflow does `URL=$(start-tunnel.sh ...)`), so a workflow command
    on stdout is CAPTURED INTO the value. That killed the first real named-mode run after it had already created the tunnel, DNS record and Access app::

        ##[error]Invalid format 'https://rdc-ci-30258284234.rediacc.io'
    """
    lib = BP / "lib" / "breakpoint-common.sh"
    bash = harness.require_tool("bash", "install bash; the subject is a bash library")
    result = harness.run(
        [
            bash,
            "-c",
            "source '%s'; bp_gha_mask 'sup3rs3cret'; bp_gha_warning 'careful'" % os.fspath(lib),
        ],
        # GITHUB_ACTIONS=true is the load-bearing part: both helpers no-op without it,
        # so the identical check run locally passes while the bug is fully present.
        env={"GITHUB_ACTIONS": "true"},
    )
    if result.out:
        gate.log_fail(
            "bp_gha_mask/bp_gha_warning wrote to STDOUT; any $(...) capture of a script "
            "using them is corrupted. stdout was: %s" % result.out
        )
    gate.log_pass("workflow commands stay off stdout under GITHUB_ACTIONS=true")

    # ...and they must still be EMITTED, or masking silently stops protecting the per-tunnel connector token (which is not a repo secret, so the runner does not mask it for us). Off-stdout must not become not-at-all.
    if "::add-mask::sup3rs3cret" not in result.err:
        gate.log_fail("bp_gha_mask emitted no ::add-mask:: at all -- masking is silently dead")
    if "::warning::careful" not in result.err:
        gate.log_fail("bp_gha_warning emitted no ::warning:: at all")
    gate.log_pass("workflow commands are still emitted (on stderr), so masking keeps working")
