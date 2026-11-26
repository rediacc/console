"""An upstream gate run as its registered Python module counts as its step (9edc242388 moved check:ci-ops-health off npm)."""

from rediacc_ci.security import ci_workflow_invariants as inv


def _doc(run: str) -> dict:
    return {"jobs": {"quality-go": {"steps": [{"name": "ops health", "run": run}]}}}


def test_the_registered_module_counts_as_the_gate_step() -> None:
    found = inv.upstream_gate_steps(_doc("PYTHONPATH=.ci python3 -m rediacc_ci.quality.ops_health"))
    assert [(job, i) for job, i, _ in found["check:ci-ops-health"]] == [("quality-go", 0)]


def test_control_the_npm_form_still_counts() -> None:
    found = inv.upstream_gate_steps(_doc("npm run check:ci-ops-health"))
    assert len(found["check:ci-ops-health"]) == 1


def test_control_another_module_does_not_count() -> None:
    found = inv.upstream_gate_steps(
        _doc("PYTHONPATH=.ci python3 -m rediacc_ci.quality.ops_health_extra")
    )
    assert found["check:ci-ops-health"] == []


def test_a_gate_named_only_in_an_echo_or_a_comment_does_not_count() -> None:
    """ee21aba7.1: text that mentions the module or the npm script without running it is not the step."""
    for run in (
        "echo PYTHONPATH=.ci python3 -m rediacc_ci.quality.ops_health",
        "# PYTHONPATH=.ci python3 -m rediacc_ci.quality.ops_health\ntrue",
        "true # npm run check:ci-ops-health",
        'printf "%s" "npm run check:ci-ops-health"',
    ):
        assert inv.upstream_gate_steps(_doc(run))["check:ci-ops-health"] == [], run


def test_a_gate_run_after_other_lines_still_counts() -> None:
    found = inv.upstream_gate_steps(
        _doc("echo start\nPYTHONPATH=.ci python3 -m rediacc_ci.quality.ops_health\n")
    )
    assert len(found["check:ci-ops-health"]) == 1


def test_a_gate_chained_after_an_echo_on_one_line_still_counts() -> None:
    """17f9d3d7.2: `echo start && npm run <gate>` runs the gate, so the echo prefix does not hide it; text chained after an echo stays text."""
    for run in (
        "echo start && npm run check:ci-ops-health",
        "echo a; echo b && PYTHONPATH=.ci python3 -m rediacc_ci.quality.ops_health",
    ):
        assert len(inv.upstream_gate_steps(_doc(run))["check:ci-ops-health"]) == 1, run
    for run in (
        "echo start && echo npm run check:ci-ops-health",
        "echo start && true # npm run check:ci-ops-health",
    ):
        assert inv.upstream_gate_steps(_doc(run))["check:ci-ops-health"] == [], run


def test_a_separator_inside_a_quoted_echo_is_text_not_a_chain() -> None:
    """4f789e58.1: `echo "x && npm run <gate>"` only names the gate; the && inside the quotes does not end the echo, so nothing executes. Control: the same gate chained after a closed quote runs."""
    assert inv._after_echo('echo "x && npm run check:ci-ops-health"') == ""
    assert inv._after_echo("echo 'a; npm run g'") == ""
    assert (
        inv._after_echo('echo "x" && npm run check:ci-ops-health') == "npm run check:ci-ops-health"
    )
    assert inv._after_echo("echo 'a; b' ; npm run h") == "npm run h"


def test_an_escaped_quote_opens_no_quote_and_a_substitution_runs() -> None:
    """6ccb06b9.1: `echo \\"x && npm run <gate>` chains, because the backslash escapes the quote. 6ccb06b9.2: a `$(...)` or backtick substitution inside the echoed text runs, so the line counts as executed. Control: single quotes keep both as text."""
    assert (
        inv._after_echo('echo \\"x && npm run check:ci-ops-health') == "npm run check:ci-ops-health"
    )
    assert "check:ci-ops-health" in inv._after_echo('echo "ok && $(npm run check:ci-ops-health)"')
    assert "check:ci-ops-health" in inv._after_echo("echo `npm run check:ci-ops-health`")
    assert inv._after_echo("echo 'ok $(npm run check:ci-ops-health)'") == ""


def test_text_beside_a_substitution_is_not_executed() -> None:
    """e166b8d7.1: `echo "$(date) npm run <gate>"` runs `date`, so the gate named in the same echo stays text. Controls: the substitution body itself runs, and a chain after the echo still runs."""
    gate = "npm run check:ci-ops-health"
    assert gate not in inv._after_echo(f'echo "$(date) {gate}"')
    assert gate not in inv._after_echo(f'echo "`date` {gate}"')
    assert inv._after_echo('echo "$(date)"') == "date"
    assert inv._after_echo(f'echo "$(date)" && {gate}') == f"date\n{gate}"
    assert gate in inv._after_echo(f'echo "$(echo $(date)) x" && {gate}')
    assert inv.upstream_gate_steps(_doc(f'echo "$(date) {gate}"'))["check:ci-ops-health"] == []
    assert len(inv.upstream_gate_steps(_doc(f'echo "$({gate})"'))["check:ci-ops-health"]) == 1


def test_a_backslash_outside_quotes_escapes_the_next_character() -> None:
    """6ccb06b9.3: the backslash cases the escape handling in _split_chain must keep. `echo \\"x && g` chains; an escaped separator is text; an escaped quote after a real quote stays inside it; a backslash inside single quotes escapes nothing."""
    g = "npm run check:ci-ops-health"
    assert inv._after_echo(f'echo \\"x && {g}') == g
    assert inv._after_echo(f"echo a \\&& {g}") == ""
    assert inv._after_echo(f'echo "a \\" && {g}"') == ""
    assert inv._after_echo(f"echo 'a\\' && {g}") == g
    assert inv._after_echo(f'echo "a" && echo \\"b && {g}') == g


def test_a_quoted_parenthesis_inside_a_substitution_does_not_close_it() -> None:
    """747c7fe6.1: the depth of a dollar-paren substitution counts parentheses outside quotes only, so a `)` inside quotes or after a backslash leaves the gate after it inside the body. Controls: a plain body is unchanged, a quoted `(` opens nothing, and an unclosed substitution runs to the end."""
    gate = "npm run check:ci-ops-health"
    assert gate in inv._after_echo(f"echo \"$(printf ')' ; {gate})\"")
    assert gate in inv._after_echo(f'echo "$(printf ")" ; {gate})"')
    assert gate in inv._after_echo(f'echo "$(printf \\) ; {gate})"')
    assert gate in inv._after_echo(f"echo \"$(printf '(' ; {gate})\"")
    assert inv._after_echo('echo "$(date)"') == "date"
    assert gate in inv._after_echo(f'echo "$({gate}')
