"""Port of `.ci/scripts/test/gates/test-breakpoint-naming.sh`.

Pins the tunnel-naming grammar produced by `.ci/breakpoint/scripts/derive-descriptor.sh`.

WHY A GATE AND NOT A COMMENT, carried from the twin because it is the reason every assertion below is written as an EXACT string. The name is the only DURABLE channel breakpoint has. A session's state file lives on a runner that can vanish (force-cancel and infra loss both skip `if: always()` entirely), so cleanup cannot depend on it. What cleanup CAN depend on is that the tunnel
name is a pure function of `$GITHUB_RUN_ID`: `reap-breakpoint-orphans.sh` lists Cloudflare's own objects, parses the run id back out of each name, and asks GitHub whether that run has finished. That machinery breaks SILENTLY if the grammar drifts by one byte -- the sweeper stops matching, no error anywhere, and orphaned tunnels accumulate until somebody notices the bill.

WHY THE DRIVER PORTED THIS AND NOT AN AGENT. `agent/8f55d4f0/W7P3-batch5-brief.md` records six `test-breakpoint-*.sh` subjects as unportable by any agent under the standard brief, and NOT on merit: plant-verifying one means temporarily writing under `.ci/breakpoint/**`, which invariant 8 forbids any sweep from touching and which every batch brief lists as must-not-touch. The brief
gives two ways out -- hand one batch owner that path explicitly, or exclude them in the derivation with the reason written down -- and adds "Do not silently drop them a fourth time." This is the first option taken: `.ci/breakpoint` is the driver's path, so the driver ports them.

WHAT THE PORT RESPELLS, and it is one thing. The twin publishes its three results as GLOBALS through a `derive()` helper, with a comment recording why: a function whose result is read back through command substitution runs in a SUBSHELL, so an exit code assigned inside it never reaches the caller, and the twin's first draft printed three green exit-code assertions that checked
nothing. Python has no such hazard -- a
function returns a value -- so `derive()` here returns the `RunResult` directly. The
hazard the twin was guarding against cannot exist in this spelling, which is why the globals are not reproduced.

`env_replace=True` IS THE TWIN'S `env -i`, and it is load-bearing rather than tidy.
`test_missing_run_id_refuses_and_invents_nothing` asserts what the subject does with NO `GITHUB_RUN_ID` in the environment, and this process may well be running under a
real one; inheriting it would hand the subject the value whose absence is the case.

NO `xdist_group`. Every case runs one short-lived `bash` with a replaced environment
whose `HOME` and `RUNNER_TEMP` point into its own `mktemp -d`; the subject is only
ever READ, and nothing binds a port or mutates a module global.
"""

import os

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

BASH_TWIN = ".ci/scripts/test/gates/test-breakpoint-naming.sh"

DERIVE = paths.from_root(".ci", "breakpoint", "scripts", "derive-descriptor.sh")
CONF = paths.from_root(".ci", "breakpoint", "breakpoint.conf")

# The zone every expectation below is written against. ASSERTED rather than read, so a conf change that moves the zone shows up HERE, where the hostname expectations live, instead of as a mystery DNS failure at session start.
EXPECTED_ZONE = "rediacc.io"

LISTED_LABELS = ("rdc-ci", "rdc-dev", "rdc-demo")


def derive(gate, tmp, *args: str) -> harness.RunResult:
    """Run the subject with a SCRUBBED environment and a private state dir.

    The environment is replaced, not overlaid: see the module docstring. `PATH` is carried over because the subject shells out, and `HOME`/`RUNNER_TEMP` point into the caller's temp dir so nothing is written outside it.
    """
    if not os.access(DERIVE, os.X_OK):
        gate.log_fail(
            "subject under test is missing or not executable: %s" % paths.relative_to_root(DERIVE)
        )
    bash = harness.require_tool("bash", "install bash; the subject is a bash script")
    return harness.run(
        [bash, os.fspath(DERIVE), *args],
        env={
            "PATH": os.environ.get("PATH", ""),
            "HOME": os.fspath(tmp),
            "RUNNER_TEMP": os.fspath(tmp),
        },
        env_replace=True,
    )


def test_zone_is_what_the_expectations_assume(gate):
    """Runs FIRST in the twin's order, and for a reason: every hostname assertion
    below hard-codes the zone, so a conf that moved it must fail here rather than in
    eight confusing places."""
    conf = CONF.read_text(encoding="utf-8")
    gate.assert_contains(
        conf,
        'BREAKPOINT_TUNNEL_ZONE="%s"' % EXPECTED_ZONE,
        "the hostname expectations in this file are written against %s" % EXPECTED_ZONE,
    )
    gate.log_pass("breakpoint.conf zone is %s (the hostname expectations hold)" % EXPECTED_ZONE)


def test_exact_tunnel_name(gate):
    with harness.temp_dir() as tmp:
        run = derive(gate, tmp, "--field", "name", "--label", "rdc-ci", "--run-id", "12345678901")
        gate.assert_exit_code(0, run.rc, "deriving a name for a valid run id")
        gate.assert_eq(run.out.rstrip("\n"), "breakpoint-rdc-ci-12345678901", "tunnel-name grammar")
    gate.log_pass("tunnel name is exactly breakpoint-<label>-<run-id>")


def test_exact_hostname_and_url(gate):
    with harness.temp_dir() as tmp:
        host = derive(
            gate, tmp, "--field", "hostname", "--label", "rdc-dev", "--run-id", "42"
        ).out.rstrip("\n")
        gate.assert_eq(host, "rdc-dev-42.%s" % EXPECTED_ZONE, "hostname grammar")

        url = derive(
            gate, tmp, "--field", "url", "--label", "rdc-dev", "--run-id", "42"
        ).out.rstrip("\n")
        gate.assert_eq(url, "https://rdc-dev-42.%s" % EXPECTED_ZONE, "url grammar")

        # First-level label BY NECESSITY: Universal SSL covers the apex and ONE level, so a middle label would silently need paid Advanced Certificate Manager. Counting dots is how that stays true.
        gate.assert_eq(
            host.count("."),
            2,
            "hostname must be first-level (<label>.<zone>), not <label>.<sub>.<zone>",
        )
    gate.log_pass("hostname and url are exactly <label>-<run-id>.%s, first-level" % EXPECTED_ZONE)


def test_missing_run_id_refuses_and_invents_nothing(gate):
    """No `GITHUB_RUN_ID` in the environment (the replaced env guarantees it) and no
    `--run-id`."""
    with harness.temp_dir() as tmp:
        run = derive(gate, tmp, "--field", "name", "--label", "rdc-ci")
        out = run.out.rstrip("\n")
        if run.rc == 0:
            gate.log_fail("missing run id must be a hard failure, got exit 0 with stdout %r" % out)
        gate.assert_eq(out, "", "a refusal must put NOTHING on stdout")
        # `breakpoint-rdc-ci-` with an empty component is the specific shape that would match no sweep regex and orphan its objects forever.
        gate.assert_not_contains(out, "--", "an empty component must never be emitted")
        gate.assert_not_contains(out, "breakpoint-", "no partial name may leak to stdout")
        gate.assert_contains(run.err, "GITHUB_RUN_ID", "the refusal must name the missing variable")
    gate.log_pass("unset run id exits non-zero with empty stdout and invents no value")


def test_non_numeric_run_id_rejected(gate):
    with harness.temp_dir() as tmp:
        run = derive(
            gate, tmp, "--field", "name", "--label", "rdc-ci", "--run-id", "12345; rm -rf /"
        )
        gate.assert_exit_code(4, run.rc, "a non-numeric run id must be rejected")
        gate.assert_eq(run.out.rstrip("\n"), "", "rejected input must produce no stdout")

        run = derive(gate, tmp, "--field", "name", "--label", "rdc-ci", "--run-id", "abc")
        gate.assert_exit_code(4, run.rc, "an alphabetic run id must be rejected")
    gate.log_pass("non-numeric run ids are rejected with exit 4 and empty stdout")


def test_unlisted_label_rejected(gate):
    """The sweeper's regex is BUILT from `BREAKPOINT_TUNNEL_LABELS`, so a label that is
    used but not listed is invisible to cleanup permanently. Refusing here is the only
    thing keeping that promise true."""
    with harness.temp_dir() as tmp:
        run = derive(gate, tmp, "--field", "name", "--label", "rdc-notalabel", "--run-id", "99")
        gate.assert_exit_code(
            4, run.rc, "a label outside BREAKPOINT_TUNNEL_LABELS must be rejected"
        )
        gate.assert_eq(run.out.rstrip("\n"), "", "a rejected label must produce no stdout")
        gate.assert_contains(
            run.err, "BREAKPOINT_TUNNEL_LABELS", "the refusal must point at the closed set"
        )

        # CONTROL: the listed labels are all accepted, so the check above is a real filter and not a script that rejects everything.
        for label in LISTED_LABELS:
            run = derive(gate, tmp, "--field", "name", "--label", label, "--run-id", "99")
            gate.assert_exit_code(0, run.rc, "listed label %r must be accepted" % label)
            gate.assert_eq(
                run.out.rstrip("\n"),
                "breakpoint-%s-99" % label,
                "listed label %r name" % label,
            )
    gate.log_pass("unlisted labels rejected, all three listed labels accepted")


def test_deterministic(gate):
    with harness.temp_dir() as tmp:
        first = derive(
            gate, tmp, "--field", "name", "--label", "rdc-ci", "--run-id", "777"
        ).out.rstrip("\n")
        second = derive(
            gate, tmp, "--field", "name", "--label", "rdc-ci", "--run-id", "777"
        ).out.rstrip("\n")
        gate.assert_eq(second, first, "the same inputs must produce byte-identical output")
        # Without this the case compares two EMPTY strings, which proves nothing.
        if not first:
            gate.log_fail("deterministic check compared two EMPTY strings, which proves nothing")
    gate.log_pass("derivation is idempotent: same inputs, byte-identical name (%s)" % first)


def test_different_runs_get_different_names(gate):
    with harness.temp_dir() as tmp:
        first = derive(
            gate, tmp, "--field", "name", "--label", "rdc-ci", "--run-id", "1000"
        ).out.rstrip("\n")
        second = derive(
            gate, tmp, "--field", "name", "--label", "rdc-ci", "--run-id", "1001"
        ).out.rstrip("\n")
        if first == second:
            gate.log_fail(
                "two run ids collided on %r; concurrent sessions would fight over one tunnel"
                % first
            )
    gate.log_pass("different run ids yield different names (%s vs %s)" % (first, second))


def test_dns_label_capped_at_63(gate):
    """An 80-digit run id is not realistic; the CAP is, and it has to be exercised by
    an input that actually EXCEEDS it -- a 40-digit id produces a 49-octet label, so the truncation branch never runs and the assertion is decorative. Over-long labels are rejected by the DNS API with a message that does not point back here, so
    truncation must happen before the call."""
    with harness.temp_dir() as tmp:
        run = derive(gate, tmp, "--field", "hostname", "--label", "rdc-demo", "--run-id", "7" * 80)
        gate.assert_exit_code(0, run.rc, "an over-long descriptor must be truncated, not refused")
        label = run.out.rstrip("\n").split(".", 1)[0]
        gate.assert_eq(
            len(label), 63, "an over-long DNS label must be truncated to exactly the RFC 1035 cap"
        )
        gate.assert_eq(
            label[-1], "7", "truncation must not leave a trailing '-' (invalid in a DNS label)"
        )
    gate.log_pass("an 89-octet descriptor is truncated to a valid 63-octet DNS label")
