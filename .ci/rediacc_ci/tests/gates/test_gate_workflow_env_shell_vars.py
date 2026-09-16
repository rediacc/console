"""Port of `.ci/scripts/test/gates/test-workflow-env-shell-vars.sh`.

Both-ways test for the env-shell-var rule in
`.ci/scripts/quality/check-workflows.sh`.

THE BUG IT GUARDS. GitHub does not expand shell syntax in an `env:` VALUE, only
`${{ }}` expressions, and bash does not recursively expand a variable's value. So

    env:
      SSH_KEY: $RUNNER_TEMP/renet/staging/.ssh/id_rsa

reaches the script as a literal string starting with a dollar sign, and the
failure is a baffling "chown: cannot access '$RUNNER_TEMP/renet'". Observed on
OPS Provision, run 29830623794.

It is specifically an INLINE-EXTRACTION hazard: inside a `run:` block the shell
DOES expand $RUNNER_TEMP, so moving that same text into `env:` while extracting a
script silently changes its meaning. That is exactly how it got there.

WHY THIS TEST EXISTS AT ALL, and it is the reason every case below is written in
pairs. The rule was born VACUOUS. Its first version used `\\b` for a word
boundary, but in awk regex `\\b` is a BACKSPACE, and because it was written
through a non-raw Python string a literal 0x08 byte landed in the script. The
regex therefore required an actual backspace character and matched nothing, while
the gate reported "All workflows are clean". It was caught only by planting a
violation and watching it NOT fire. A rule that has already been silently dead
once does not get to rely on review.

NO `xdist_group`. Each case gets its own `mktemp -d` fixture directory, and the
subject is driven with a per-subprocess environment rather than by mutating this
one.
"""

from rediacc_ci.tests.gates import harness, workflow_rule

BASH_TWIN = ".ci/scripts/test/gates/test-workflow-env-shell-vars.sh"


def test_flags_runner_temp(gate):
    gate.log_test("the OPS Provision defect: a literal $RUNNER_TEMP in an env: value")
    with harness.temp_dir() as d:
        workflow_rule.write_step_env(
            d / "bad.yml", "SSH_KEY: $RUNNER_TEMP/renet/id_rsa", "ATTEMPTS: 15"
        )
        result = workflow_rule.run_check(gate, d, ci=True)
        gate.assert_exit_code(1, result.rc, "a literal $RUNNER_TEMP in an env: value must fail")
        gate.assert_contains(
            result.combined, "shell syntax GitHub will not expand", "explains the mechanism"
        )
        gate.assert_contains(result.combined, "bad.yml:9", "cites file:line")
        gate.assert_contains(result.combined, "runner.temp", "names the context to use instead")
    gate.log_pass("flags $RUNNER_TEMP in an env: value, with file:line and the remedy")


def test_flags_home(gate):
    gate.log_test("$HOME has no context equivalent, and is just as broken")
    # The remedy differs, but the value still ships as a literal string.
    with harness.temp_dir() as d:
        workflow_rule.write_step_env(d / "bad.yml", "SSH_KEY: $HOME/.ssh/id_ed25519")
        result = workflow_rule.run_check(gate, d, ci=True)
        gate.assert_exit_code(1, result.rc, "a literal $HOME in an env: value must fail")
    gate.log_pass("flags $HOME too, which has no context equivalent")


def test_context_form_passes(gate):
    gate.log_test("CONTROL: the ${{ }} context form IS the fix and must pass")
    with harness.temp_dir() as d:
        workflow_rule.write_step_env(
            d / "ok.yml", "SSH_KEY: ${{ runner.temp }}/renet/id_rsa", "ATTEMPTS: 15"
        )
        result = workflow_rule.run_check(gate, d, ci=True)
        gate.assert_exit_code(0, result.rc, "the ${{ }} context form is the fix and must pass")
    gate.log_pass("the ${{ runner.temp }} form passes")


def test_longer_name_is_reported_as_itself(gate):
    gate.log_test("a long name must be reported as ITSELF, not as a substring")
    # REWRITTEN 2026-09-02 when the rule widened from six names to ANY $IDENT.
    # Under the six-name rule this case asserted exit 0: $HOMEBREW_PREFIX must not
    # be flagged BY MISTAKE as $HOME. Under the widened rule it is flagged ON
    # PURPOSE, because GitHub does not expand $HOMEBREW_PREFIX in an env: value
    # any more than it expands $HOME. The concern that SURVIVES the widening is
    # the substring one: the report must name the variable that is actually
    # there.
    with harness.temp_dir() as d:
        workflow_rule.write_step_env(
            d / "bad.yml", "BREW: $HOMEBREW_PREFIX/bin", "OTHER: $RUNNER_TEMPLATE_X"
        )
        result = workflow_rule.run_check(gate, d, ci=True)
        gate.assert_exit_code(
            1,
            result.rc,
            "any unexpanded $IDENT in an env: value is a violation, long names included",
        )
        gate.assert_contains(
            result.combined,
            "HOMEBREW_PREFIX",
            "the report must name $HOMEBREW_PREFIX itself, not a substring of it",
        )
    gate.log_pass("$HOMEBREW_PREFIX / $RUNNER_TEMPLATE_X are flagged, and reported as themselves")


def test_arbitrary_variable_is_flagged(gate):
    gate.log_test("THE CASE THE WIDENING EXISTS FOR: an arbitrary $IDENT")
    # The six-name rule let this through, and it is the exact idiom a job-start
    # secret fetch invites: the value looks like it flows and ships an EMPTY
    # string, because GitHub never expands it.
    with harness.temp_dir() as d:
        workflow_rule.write_step_env(d / "bad.yml", "SECRET_API_KEY: $ACCOUNT_SERVER_API_KEY")
        result = workflow_rule.run_check(gate, d, ci=True)
        gate.assert_exit_code(1, result.rc, "SECRET_X: $SOME_VAR in an env: block must be flagged")
    gate.log_pass("an arbitrary $IDENT (not one of the old six) is flagged")


def test_comment_line_in_env_block_is_ignored(gate):
    gate.log_test("CONTROL: a comment inside an env: mapping is prose, not a value")
    # housekeeping.yml documents `${IN_FLIGHT_VERSION:-}` this way and must not
    # read as a hit.
    with harness.temp_dir() as d:
        workflow_rule.write_step_env(
            d / "ok.yml",
            "# the ${SOME_DEFAULT:-} form in the script no-ops when absent",
            "REAL: plain",
        )
        result = workflow_rule.run_check(gate, d, ci=True)
        gate.assert_exit_code(0, result.rc, "a comment line inside env: must not be flagged")
    gate.log_pass("a comment line inside an env: block is ignored")


def test_run_body_is_not_flagged(gate):
    gate.log_test("CONTROL: inside run: the shell DOES expand these")
    # Flagging them there would be wrong and would make the rule unusable. Only
    # env: VALUES are in scope. Written out rather than through write_step_env
    # because the whole point is a file with no env: block at all.
    with harness.temp_dir() as d:
        (d / "ok.yml").write_text(
            "name: fixture\n"
            "on: push\n"
            "jobs:\n"
            "  j:\n"
            "    runs-on: ubuntu-latest\n"
            "    steps:\n"
            '      - run: SSH_KEY="$HOME/.ssh/id_ed25519" ./script.sh\n'
            "      - run: |\n"
            '          chown -R "$(whoami)" "$RUNNER_TEMP/renet"\n',
            encoding="utf-8",
        )
        result = workflow_rule.run_check(gate, d, ci=True)
        gate.assert_exit_code(
            0,
            result.rc,
            "shell vars inside run: are expanded by the shell and must not be flagged",
        )
    gate.log_pass("run: bodies are out of scope (the shell expands them there)")


def test_env_block_ends_at_dedent(gate):
    gate.log_test("the scanner must LEAVE the env: block at the dedent")
    # A shell var appearing after the env: mapping closes belongs to a later key,
    # not to env:. If the scanner never exits the block it would flag the whole
    # rest of the file.
    with harness.temp_dir() as d:
        (d / "ok.yml").write_text(
            "name: fixture\n"
            "on: push\n"
            "jobs:\n"
            "  j:\n"
            "    runs-on: ubuntu-latest\n"
            "    steps:\n"
            "      - run: ./a.sh\n"
            "        env:\n"
            "          OK: plain-value\n"
            '      - run: echo "$RUNNER_TEMP"\n',
            encoding="utf-8",
        )
        result = workflow_rule.run_check(gate, d, ci=True)
        gate.assert_exit_code(0, result.rc, "the env: block must end at the dedent")
    gate.log_pass("scanner leaves the env: block at the dedent")


def test_the_fixture_directory_is_what_is_judged(gate):
    """CONTROL ON THE HARNESS ITSELF, which no case above supplies.

    Every case here claims a verdict about a fixture tree, and every one of those
    claims rests on `WORKFLOW_INLINE_ONLY=1` actually emptying GITHUB_YAMLS so the
    banned-pattern scans become no-ops and `WORKFLOW_DIR` is the only thing
    judged. If that switch stopped working, the rule would be reading the REAL
    `.github/workflows` -- which is clean, and has to stay clean, so the passing
    cases would keep passing for a reason that has nothing to do with their
    fixtures.

    That matters more for THIS rule than for its siblings, because this is the
    rule that was born vacuous: an awk `\\b` that matched nothing while the gate
    reported "All workflows are clean". A harness that reads the wrong tree
    produces the identical shape of green.
    """
    with harness.temp_dir() as root:
        bad = root / "bad"
        good = root / "good"
        bad.mkdir()
        good.mkdir()
        workflow_rule.write_step_env(bad / "offender.yml", "SSH_KEY: $RUNNER_TEMP/id_rsa")
        workflow_rule.write_step_env(good / "fine.yml", "SSH_KEY: ${{ runner.temp }}/id_rsa")
        bad_result = workflow_rule.run_check(gate, bad, ci=True)
        good_result = workflow_rule.run_check(gate, good, ci=True)
        gate.assert_exit_code(1, bad_result.rc, "the violating fixture directory reds")
        gate.assert_exit_code(0, good_result.rc, "the clean fixture directory passes")
        gate.assert_contains(
            bad_result.combined,
            str(bad),
            "the finding cites the FIXTURE path, so the real .github tree is not what was scanned",
        )
    gate.log_pass(
        "the verdict tracks WORKFLOW_DIR, so the fixtures above are really what is judged"
    )
