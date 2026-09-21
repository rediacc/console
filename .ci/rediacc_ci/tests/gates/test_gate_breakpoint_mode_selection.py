"""Port of `.ci/scripts/test/gates/test-breakpoint-mode-selection.sh`, retired in W7 P5.

Pins the security property of `.ci/breakpoint/scripts/select-mode.sh`:
NAMED MODE NEVER SILENTLY DEGRADES TO QUICK MODE.

quick and named are not two grades of the same thing. In quick mode the random `*.trycloudflare.com` URL is the ONLY thing protecting a runner that holds the repo source and, with debug-shell on, an interactive shell. In named mode the hostname is derived from a public run id, so it is guessable by anyone reading the Actions tab, and Cloudflare Access -- not obscurity -- is the
control.

So a named-mode request that cannot be honoured has exactly one correct outcome: fail, loudly, with EMPTY STDOUT. Falling back would drop authentication at the moment nobody is looking, and the caller downstream would happily start a tunnel on the word it read. Empty stdout is asserted directly for that reason: a caller doing
`MODE=$(select-mode.sh)` with a half-failed script must get nothing rather than
something.

The reverse also matters and is asserted here: an explicit `--mode quick` stays quick even when named-mode credentials are sitting in the environment. A silent upgrade creates Cloudflare-side objects the operator did not ask for and does not know to clean up.

The last-wins quirk of `parse_args` (`--mode named --mode quick` gives quick) is pinned too, not because it is good, but because `breakpoint-common.sh` documents it as deliberate and something must fail if a future edit makes repeated flags accumulate instead.

WHAT THE PORT RESPELLS. The twin publishes its three results as GLOBALS, with a comment recording why: reading the result back through command substitution would run the helper in a SUBSHELL and throw the exit code away, which is how an exit-code assertion silently compares 0 against 0. Python has no such hazard, so `select_mode()` returns the result. STDERR IS LOWERCASED, and that
IS carried over: the real message shouts "FALLING BACK TO QUICK MODE" in capitals, so a case-sensitive check for the lowercase spelling would pass
while the script fell back.

WHY THE DRIVER PORTED THIS AND NOT AN AGENT. `agent/8f55d4f0/W7P3-batch5-brief.md` records six `test-breakpoint-*.sh` subjects as unportable by any agent under the standard brief and NOT on merit, because plant-verifying one means temporarily writing under `.ci/breakpoint/**`, which invariant 8 forbids any sweep from touching. The brief's two ways out are to hand one batch owner
that path explicitly or to exclude them in the derivation with the reason recorded, and it adds "Do not silently drop them a fourth time." This is the first option: `.ci/breakpoint` is the driver's path.

NO `xdist_group`. Every case runs one short-lived `bash` with a replaced environment whose `HOME` and `RUNNER_TEMP` point into its own `mktemp -d`; the subjects are only ever READ.
"""

import os

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

SELECT = paths.from_root(".ci", "breakpoint", "scripts", "select-mode.sh")
PREFLIGHT = paths.from_root(".ci", "breakpoint", "scripts", "preflight-breakpoint.sh")

# Credentials that make named mode configurable. The zone comes from breakpoint.conf, so only these two are environment-supplied.
FAKE_TOKEN = {"CLOUDFLARE_BREAKPOINT_TUNNEL_TOKEN": "not-a-real-token"}
FAKE_ACCOUNT = {"CLOUDFLARE_ACCOUNT_ID": "0000000000000000000000000000dead"}
FAKE_BOTH = {**FAKE_TOKEN, **FAKE_ACCOUNT}


def select_mode(gate, tmp, *args: str, env: dict | None = None) -> harness.RunResult:
    """The subject, environment REPLACED (the twin's `env -i`), stderr LOWERCASED."""
    if not os.access(SELECT, os.X_OK):
        gate.log_fail(
            "subject under test is missing or not executable: %s" % paths.relative_to_root(SELECT)
        )
    bash = harness.require_tool("bash", "install bash; the subject is a bash script")
    merged = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": os.fspath(tmp),
        "RUNNER_TEMP": os.fspath(tmp),
    }
    merged.update(env or {})
    result = harness.run([bash, os.fspath(SELECT), *args], env=merged, env_replace=True)
    return harness.RunResult(result.rc, result.out.rstrip("\n"), result.err.lower())


def test_named_without_credentials_fails_hard(gate):
    """THE HEADLINE PROPERTY."""
    with harness.temp_dir() as tmp:
        run = select_mode(gate, tmp, "--mode", "named")
        gate.assert_exit_code(3, run.rc, "named mode with no credentials must fail")
        gate.assert_eq(run.out, "", "a failed selection must put NOTHING on stdout")
        # Lowercased in the helper so this catches the real message too, which shouts "FALLING BACK TO QUICK MODE" in capitals.
        gate.assert_not_contains(run.err, "falling back", "named mode must not fall back silently")
        # The message must EXPLAIN, not just exit non-zero. Asserting on "unauthenticated" rather than the old "refusing to fall back" wording: there is no fallback to refuse any more, so the reason is now the property that makes downgrading wrong in the first place.
        gate.assert_contains(
            run.err,
            "unauthenticated",
            "the refusal must say WHY quick is not an acceptable substitute",
        )
    gate.log_pass("named without credentials: exit 3, empty stdout, no fallback")


def test_named_half_configured_still_fails(gate):
    """Token present, account id missing is THE DANGEROUS SHAPE: it LOOKS configured to a reader, and a script that only checked the token would proceed into a broken API call and then "recover" into quick mode."""
    with harness.temp_dir() as tmp:
        run = select_mode(gate, tmp, "--mode", "named", env=FAKE_TOKEN)
        gate.assert_exit_code(3, run.rc, "named mode with only a token must fail")
        gate.assert_eq(run.out, "", "half-configured named mode must produce no stdout")
        gate.assert_contains(
            run.err, "cloudflare_account_id", "the error must name the missing piece"
        )

        # And the mirror: account id present, token missing.
        run = select_mode(gate, tmp, "--mode", "named", env=FAKE_ACCOUNT)
        gate.assert_exit_code(3, run.rc, "named mode with only an account id must fail")
        gate.assert_contains(
            run.err, "breakpoint_tunnel_token", "the error must name the missing piece"
        )
    gate.log_pass("half-configured named mode fails on either missing half")


def test_named_fully_configured_succeeds(gate):
    with harness.temp_dir() as tmp:
        run = select_mode(gate, tmp, "--mode", "named", env=FAKE_BOTH)
        gate.assert_exit_code(0, run.rc, "fully configured named mode must succeed: %s" % run.err)
        gate.assert_eq(run.out, "named", "stdout must be exactly the word 'named'")
    gate.log_pass("fully configured named mode prints exactly 'named'")


def test_quick_without_credentials(gate):
    with harness.temp_dir() as tmp:
        run = select_mode(gate, tmp, "--mode", "quick")
        gate.assert_exit_code(0, run.rc, "quick mode needs no credentials")
        gate.assert_eq(run.out, "quick", "stdout must be exactly the word 'quick'")
    gate.log_pass("quick without credentials prints exactly 'quick'")


def test_quick_with_credentials_is_not_upgraded(gate):
    with harness.temp_dir() as tmp:
        run = select_mode(gate, tmp, "--mode", "quick", env=FAKE_BOTH)
        gate.assert_exit_code(0, run.rc, "an explicit quick request must succeed")
        gate.assert_eq(
            run.out, "quick", "credentials being present must not silently upgrade to named"
        )
        # It should still SAY the credentials went unused, or a run in the wrong mode is indistinguishable in the log from one that asked for it.
        gate.assert_contains(
            run.err, "unused", "the log must note that named credentials were ignored"
        )
    gate.log_pass("quick WITH credentials stays quick (no silent upgrade)")


def test_default_is_quick_not_auto(gate):
    """No `--mode` at all, with credentials present. If the default were `auto` this would print `named`; the safe default is the one that needs no secrets and creates no account-side state."""
    with harness.temp_dir() as tmp:
        run = select_mode(gate, tmp, env=FAKE_BOTH)
        gate.assert_exit_code(0, run.rc, "the no-flag default must succeed")
        gate.assert_eq(run.out, "quick", "the default must be quick, NOT auto")
    gate.log_pass("no --mode flag defaults to quick, not auto")


def test_auto_with_credentials_picks_named(gate):
    with harness.temp_dir() as tmp:
        run = select_mode(gate, tmp, "--mode", "auto", env=FAKE_BOTH)
        gate.assert_exit_code(0, run.rc, "auto with credentials must succeed")
        gate.assert_eq(run.out, "named", "auto must prefer the authenticated mode when it can")
    gate.log_pass("auto with credentials selects named")


def test_auto_without_credentials_warns(gate):
    with harness.temp_dir() as tmp:
        run = select_mode(gate, tmp, "--mode", "auto")
        gate.assert_exit_code(0, run.rc, "auto without credentials must still succeed")
        gate.assert_eq(run.out, "quick", "auto must fall through to quick")
        # The warning is the whole difference between auto and a silent downgrade.
        gate.assert_contains(
            run.err,
            "unauthenticated",
            "auto must announce that the session is unauthenticated",
        )
        gate.assert_contains(run.err, "not configured", "auto must say what was missing")
    gate.log_pass("auto without credentials selects quick AND warns it is unauthenticated")


def test_repeated_mode_flag_is_last_wins(gate):
    """`parse_args` eval-assigns the same variable name per flag, so repeats overwrite rather than accumulate. Pinned so nobody later writes a script that expects `--mode a --mode b` to mean "a and b" or to be an error."""
    with harness.temp_dir() as tmp:
        run = select_mode(gate, tmp, "--mode", "named", "--mode", "quick", env=FAKE_BOTH)
        gate.assert_exit_code(0, run.rc, "a repeated flag must not be an error")
        gate.assert_eq(run.out, "quick", "repeated flags are LAST-WINS, not accumulate")

        # ...and in the other order, so this is a real ordering pin and not a test that would pass on any single-valued behaviour.
        run = select_mode(gate, tmp, "--mode", "quick", "--mode", "named", env=FAKE_BOTH)
        gate.assert_eq(run.out, "named", "last-wins holds in both orders")
    gate.log_pass("repeated --mode is last-wins in both orders")


def test_invalid_mode_rejected(gate):
    with harness.temp_dir() as tmp:
        run = select_mode(gate, tmp, "--mode", "sneaky")
        gate.assert_exit_code(4, run.rc, "an unknown mode must be rejected")
        gate.assert_eq(run.out, "", "a rejected mode must produce no stdout")
        # Listing the valid ones is what turns a typo into a ten-second fix.
        for mode in ("quick", "named", "auto"):
            gate.assert_contains(run.err, mode, "the error must list the valid modes")
    gate.log_pass("an invalid mode exits 4 and lists quick, named, auto")


def test_named_never_falls_back_to_quick(gate):
    """THERE IS NO ESCAPE HATCH.

    This replaces a test for `--allow-fallback`, a flag that let named mode silently become quick mode. The flag was removed, and this proves the REMOVAL rather than merely deleting its test: a deleted test and a removed feature look identical in a diff, and only one of them is safe. The old flag carried its own refusal for debug-shell/desktop sessions, which was the tell -- the
    guard existed because the downgrade was already known to be dangerous, and it narrowed the blast radius instead of removing it.
    """
    source = SELECT.read_text(encoding="utf-8")
    mentions = [line for line in source.splitlines() if "allow-fallback" in line]
    handled = [line for line in mentions if not line.lstrip().startswith("#")]
    if handled:
        gate.log_fail(
            "select-mode.sh still handles --allow-fallback; the downgrade path is "
            "reachable: %s" % "; ".join(handled)
        )

    with harness.temp_dir() as tmp:
        # An unconfigured named request fails, and emits NOTHING on stdout. Empty stdout
        # is the load-bearing half: callers do `MODE=$(select-mode.sh ...)`, so a stray
        # "quick" on stdout would be consumed as a successful choice.
        run = select_mode(gate, tmp, "--mode", "named")
        gate.assert_exit_code(3, run.rc, "an unconfigurable named request must fail, not downgrade")
        gate.assert_eq(
            run.out, "", "a refusal must produce EMPTY stdout, or the caller consumes it as a mode"
        )
        gate.assert_not_contains(
            run.err,
            "falling back",
            "the words 'falling back' must not appear: there is no fallback",
        )

        # ...and passing the removed flag must not resurrect the behaviour. Whether it errors on the unknown flag or ignores it, what it must NEVER do is print "quick" and exit 0.
        run = select_mode(gate, tmp, "--mode", "named", "--allow-fallback")
        gate.assert_eq(run.out, "", "the removed flag must not produce a mode on stdout")
        if run.rc == 0:
            gate.log_fail(
                "passing the removed --allow-fallback still exits 0 -- the downgrade survived"
            )

        # Same with an interactive session, which is the case that most needs auth.
        run = select_mode(gate, tmp, "--mode", "named", env={"BREAKPOINT_DEBUG_SHELL": "true"})
        gate.assert_exit_code(3, run.rc, "named + debug-shell must fail rather than downgrade")
        gate.assert_eq(run.out, "", "no stdout on refusal")
    gate.log_pass("named mode never downgrades to quick, with or without the removed flag")


def test_named_refuses_too_short_a_duration(gate):
    """Regression test for a real session. Named mode fronts the box with Cloudflare Access, whose one-time-PIN login is TWO email round trips. Teardown deletes the Access application the instant the timer expires, so run 30259141278 (duration 5) died mid-login and Cloudflare answered `That account does not have access.` -- which blames the policy, the one component that was
    correct. The operator went looking for a permissions bug that did not exist. This guard turns a misleading runtime failure into an accurate refusal before anything is built."""
    bash = harness.require_tool("bash", "install bash; the subject is a bash script")

    def run_pre(tmp, mode: str, duration: str) -> int:
        return harness.run(
            [bash, os.fspath(PREFLIGHT)],
            env={
                "RUNNER_TEMP": os.fspath(tmp),
                "GITHUB_RUN_ID": "1",
                "BP_ACTOR": "mfbayraktar",
                "BP_RUNNER": "ubuntu-latest",
                "BP_LABEL": "rdc-ci",
                "BP_MODE": mode,
                "BP_DURATION": duration,
            },
        ).rc

    with harness.temp_dir() as tmp:
        if run_pre(tmp, "named", "5") == 0:
            gate.log_fail(
                "named mode accepted a 5-minute duration; the session would be torn down mid-login"
            )
        gate.assert_exit_code(
            0,
            run_pre(tmp, "named", "15"),
            "named mode must accept the documented 15-minute minimum",
        )
        # Quick mode has NO login step, so a short session is legitimate there. If this ever fails the guard has been applied too broadly.
        gate.assert_exit_code(
            0,
            run_pre(tmp, "quick", "5"),
            "quick mode must still allow short sessions (it has no login step)",
        )
    gate.log_pass("named mode requires >= 15m; quick mode is unaffected")
