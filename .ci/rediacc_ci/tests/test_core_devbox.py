"""`rediacc_ci.core.devbox` against the live `.ci/lib/devbox.sh`.

THE TWIN IS STILL HERE AND IS STILL THE ONLY IMPLEMENTATION OF THIRTY-SIX OF ITS THIRTY-NINE FUNCTIONS.
`.ci/legacy/run-legacy.sh:456`, `.ci/rediacc_ci/setup/bridge.py:35`, `.ci/rediacc_ci/setup/shadow_driver.py:136`, `.ci/rediacc_ci/dev/shadow_driver.py:140` and `.ci/lib/account.sh:1090` all still source it, nothing is cut over, and this file drives the bash for real on every run: `rediacc_ci.core.devbox_shadow_driver` sources `devbox.sh` through the same prelude `bridge.py` uses and calls the twin's own functions, then does the same work through the port, and the two transcripts are compared byte for byte.

WHAT IS COVERED AND WHAT IS NOT is decided by the driver's seven scenarios and stated in its module docstring rather than restated here.
The short version: the three functions whose whole answer is computation over their own arguments, and none of the thirty-six that reach git, docker, the filesystem, a port allocator or the network.

THE ANTI-VACUITY CLAIMS, because a differential that compared two empty transcripts would pass forever: every scenario must produce a floor of observations, the tools the scenarios really use must be installed, and the whole corpus must exercise more than one answer.
`test_a_planted_defect_is_caught` plants five real defects into the port IN PROCESS, one at a time, and requires the live bash transcript to disagree with each.
That is the control on the comparison itself, and it is a control this slice needed: two of the ten defects planted while the port was written changed NOTHING, and both turned out to be behaviours the twin does not actually have.
"""

import ast
import contextlib
import io
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys

import pytest

from rediacc_ci import paths
from rediacc_ci.core import devbox
from rediacc_ci.core import devbox_shadow_driver as driver
from rediacc_ci.tests.gates import test_gate_devbox_slug as slug_gate

TWIN = ".ci/lib/devbox.sh"
PORT = ".ci/rediacc_ci/core/devbox.py"
DRIVER = ".ci/rediacc_ci/core/devbox_shadow_driver.py"
# Invoked as a MODULE, never by path: see the driver's header for why the by-path form would need a hand-written sys.path hop that `test_canonical_sys_path_hop.py` refuses.
DRIVER_MODULE = "rediacc_ci.core.devbox_shadow_driver"
LEDGER = ".ci/shadow/w7p5b-devbox.observations.jsonl"

SCENARIOS = sorted(driver.BASH_SCENARIOS)

# The floor each scenario must clear. Measured against the recorded ledger rows, then rounded DOWN so a corpus gaining an entry does not turn into a test edit; the point is to catch a transcript collapsing to nothing, not to pin a count.
OBSERVATION_FLOOR = {
    "arity": 15,
    "drift": 60,
    "route-label": 200,
    "slug-basic": 45,
    "slug-edge": 30,
    "slug-fuzz": 240,
    "slug-utf8": 45,
}

# A legal DNS label, which is what the slug has to be for traefik to route it at all. The same expression `test_gate_devbox_slug.py:40` applies.
HOSTNAME_RE = re.compile(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$")

# (bash name, the attribute it became here). Three, and the module docstring says why these three.
PORTED_FUNCTIONS = (
    ("devbox_slugify", "slugify"),
    ("devbox_slug_drift", "slug_drift"),
    ("devbox_route_label", "route_label"),
)

# The other thirty-six. Every one of them reaches git, docker, the filesystem, the port allocator or the network, and NONE of them has a Python counterpart in the port.
NOT_PORTED_FUNCTIONS = (
    "devbox_worktree",
    "devbox_mount_root",
    "devbox_container_name",
    "devbox_docker",
    "devbox_state_write",
    "devbox_state_get",
    "devbox_base_port",
    "devbox_branch",
    "devbox_slug_basename",
    "devbox_slug",
    "devbox_slug_active",
    "devbox_slug_conflicts",
    "devbox_router_hosts",
    "devbox_url",
    "devbox_network_ensure",
    "devbox_proxy_running",
    "devbox_proxy_ensure",
    "devbox_proxy_stop",
    "devbox_image_present",
    "devbox_image_digest",
    "devbox_ensure_image",
    "devbox_build_image",
    "devbox_container_id",
    "devbox_container_running",
    "_devbox_bind_if_present",
    "devbox_up",
    "devbox_status",
    "devbox_stop",
    "devbox_remove",
    "devbox_logs",
    "devbox_shell",
    "devbox_exec",
    "devbox_mount_ok",
    "devbox_identity_ok",
    "devbox_writable_ok",
    "devbox_doctor",
)

# The five real `source` sites, each with the line that does it. A cut-over would delete one of these, and this differential would then be comparing a library nothing loads.
SOURCE_SITES = (
    (".ci/legacy/run-legacy.sh", 'source "$ROOT_DIR/.ci/lib/devbox.sh"'),
    (".ci/rediacc_ci/setup/bridge.py", 'source "$ROOT_DIR/.ci/lib/devbox.sh"'),
    (".ci/rediacc_ci/setup/shadow_driver.py", 'source "$ROOT_DIR/.ci/lib/devbox.sh"'),
    (".ci/rediacc_ci/dev/shadow_driver.py", 'source "$ROOT_DIR/.ci/lib/devbox.sh"'),
    (".ci/lib/account.sh", 'source "$CONSOLE_ROOT_DIR/.ci/lib/devbox.sh"'),
)

_CACHE: dict[tuple[str, str], tuple[int, str, str]] = {}


def drive(side: str, scenario: str) -> tuple[int, str, str]:
    """One side of one scenario, run once per session and remembered.

    Cached because every case below wants the same transcript, and each run of the bash side sources `constants.sh`, `toolchain.sh`, `local-common.sh`, `service.sh` and `devbox.sh` before it does anything at all.
    """
    key = (side, scenario)
    if key not in _CACHE:
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                DRIVER_MODULE,
                "--side",
                side,
                "--twin",
                TWIN,
                "--port",
                PORT,
                scenario,
            ],
            cwd=str(paths.repo_root()),
            env={**os.environ, "PYTHONPATH": ".ci"},
            capture_output=True,
            text=True,
            check=False,
            timeout=600,
        )
        _CACHE[key] = (proc.returncode, proc.stdout, proc.stderr)
    return _CACHE[key]


def new_transcript(scenario: str) -> str:
    """The port side IN PROCESS, which is what makes a monkeypatched plant visible.

    The subprocess form above cannot see a plant, because a `monkeypatch` lives in this interpreter and the driver runs in another. The two agree by construction: this calls the same `run_new` the subprocess calls, and `test_the_in_process_transcript_is_the_subprocess_one` pins that.
    The work directory is never read on the port side, so a path that does not exist is the honest argument.
    """
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        driver.run_new(
            scenario, driver.Printer(pathlib.Path("/nonexistent-work"), paths.repo_root())
        )
    return buffer.getvalue()


# -- the differential itself -------------------------------------------------


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_the_port_matches_the_live_twin(scenario: str) -> None:
    """The whole claim of this file, once per scenario."""
    old_rc, old_out, old_err = drive("old", scenario)
    new_rc, new_out, new_err = drive("new", scenario)
    assert old_rc == 0, "the bash side could not run: %s" % old_err
    assert new_rc == 0, "the port side could not run: %s" % new_err
    assert old_out == new_out, "scenario %s diverged" % scenario


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_each_scenario_observed_something(scenario: str) -> None:
    """ANTI-VACUITY. A transcript that collapsed to nothing would compare equal.

    This is not hypothetical here: a corpus entry holding a surrogate outside the escapable range made BOTH sides die in the fixture builder, and a first comparison script called that a match because the two empty outputs were equal.
    """
    _, out, _ = drive("old", scenario)
    lines = [line for line in out.splitlines() if line.startswith("obs ")]
    assert len(lines) >= OBSERVATION_FLOOR[scenario], (
        "scenario %s produced %d observation(s), under its floor of %d; a transcript "
        "this short means the twin stopped early and the comparison proved nothing"
        % (scenario, len(lines), OBSERVATION_FLOOR[scenario])
    )


def test_the_corpus_is_not_empty() -> None:
    assert len(SCENARIOS) == 7, "the scenario set moved to %d" % len(SCENARIOS)
    assert set(SCENARIOS) == set(OBSERVATION_FLOOR), (
        "a scenario was added or removed without a floor: %s"
        % sorted(set(SCENARIOS) ^ set(OBSERVATION_FLOOR))
    )
    assert len(driver.fuzz_corpus()) == driver.FUZZ_COUNT
    assert len(set(driver.fuzz_corpus())) > driver.FUZZ_COUNT / 2, (
        "the fuzz generator is repeating itself, so its 250 entries are not 250 cases"
    )
    # The generator has to be the same bytes twice, or a ledger row describes inputs nothing can reproduce.
    assert driver.fuzz_corpus() == driver.fuzz_corpus()


def test_the_in_process_transcript_is_the_subprocess_one() -> None:
    """The bridge `test_a_planted_defect_is_caught` stands on, checked rather than assumed."""
    for scenario in SCENARIOS:
        _, subprocess_out, _ = drive("new", scenario)
        assert new_transcript(scenario) == subprocess_out, (
            "the in-process port transcript for %s differs from the subprocess one, so a "
            "planted defect proved against one says nothing about the other" % scenario
        )


# The five plants, each a defect a reasonable port could really have. (label, attribute, value, the scenario that must catch it).
PLANTS = (
    ("the 40-cap became a 41-cap", "SLUG_MAX", 41, "slug-edge"),
    ("the empty answer lost its newline", "slugify_stdout", None, "arity"),
    ("the dash collapse is gone", "sanitise_line", None, "slug-basic"),
    ("a 404 is live again, whatever the caller said", "route_label", None, "route-label"),
    ("the state-file drift line is gone", "slug_drift", None, "drift"),
)


def planted_value(attribute: str):
    """The replacement for one plant, built here so the plants table stays readable."""
    if attribute == "slugify_stdout":
        return lambda value=None: devbox.slugify(value) + "\n" if devbox.slugify(value) else ""
    if attribute == "sanitise_line":
        return lambda line: "".join(
            chr(byte) if byte in devbox.SLUG_KEEP else "-" for byte in line
        ).strip("-")
    if attribute == "route_label":
        return lambda code=None, _hint="", _routed=devbox.ROUTED_UNKNOWN: devbox.Outcome(
            devbox.ROUTE_LIVE % code + "\n", 0
        )
    if attribute == "slug_drift":
        return lambda want=None, baked="", _recorded="": devbox.Outcome(
            devbox.DRIFT_CONTAINER % (baked, want) if baked and want and baked != want else "", 0
        )
    raise AssertionError("no planted value for %s" % attribute)


@pytest.mark.parametrize(("label", "attribute", "value", "scenario"), PLANTS)
def test_a_planted_defect_is_caught(
    label: str, attribute: str, value, scenario: str, monkeypatch
) -> None:
    """THE CONTROL ON THE COMPARISON: each plant must make the live twin disagree.

    Planted in process rather than on disk, so nothing can leave a defect behind in the tree. `monkeypatch` restores the attribute when the case ends, and `test_the_port_matches_the_live_twin` runs the unplanted comparison in the same session.
    """
    _, twin_out, _ = drive("old", scenario)
    assert new_transcript(scenario) == twin_out, "the port already disagrees before the plant"
    monkeypatch.setattr(devbox, attribute, value if value is not None else planted_value(attribute))
    assert new_transcript(scenario) != twin_out, (
        "PLANT DID NOT FIRE: %s changed no observation in %s, so that scenario is not "
        "watching what it claims to watch" % (label, scenario)
    )


def test_the_transcripts_carry_what_a_divergence_would_move() -> None:
    """A CONTROL ON THE TRANSCRIPT, in the three places a mutation can hide.

    Each substitution below is a transcript a port could plausibly produce and the twin does not, so a comparison that still called it equal would be looking at the wrong thing.
    """
    _, arity_out, _ = drive("old", "arity")
    assert arity_out != arity_out.replace("rc=1", "rc=0"), (
        "the arity transcript carries no exit code, so a port that swallowed the unbound-variable "
        "death would pass"
    )
    assert "$1: unbound variable" in arity_out, (
        "the arity transcript carries no stderr, so a refusal that printed nothing would pass"
    )
    _, slug_out, _ = drive("old", "slug-basic")
    hexes = re.findall(r"out=([0-9a-f]+)", slug_out)
    assert len(hexes) >= 40, "the slug transcript carries %d answer(s)" % len(hexes)
    assert slug_out != slug_out.replace(hexes[0], "00"), (
        "the slug transcript carries no answer bytes, so a port that answered nothing would pass"
    )
    assert len(set(hexes)) > 1, "every slug answer is the same, so a constant would pass"


def test_the_locale_scenario_answers_exactly_what_the_c_locale_does() -> None:
    """The purity claim that needed a scenario rather than a sentence.

    The twin forces `LC_ALL=C` on each stage of its own pipeline, so running the SHELL under a multibyte locale must change nothing. The two scenarios share one corpus, so their transcripts must be identical line for line.
    """
    _, c_locale, _ = drive("old", "slug-basic")
    _, utf8_locale, _ = drive("old", "slug-utf8")
    assert c_locale == utf8_locale, (
        "the twin answered differently under C.utf8, so the slug depends on the caller's locale "
        "and this port is not equivalent to it"
    )
    assert driver.SCENARIO_LOCALE["slug-utf8"] == "C.utf8", (
        "the locale scenario no longer sets a multibyte locale, so it is comparing C against C"
    )


# -- the twin is still there, and still says what this file claims it says ----


def twin_text() -> str:
    return (paths.repo_root() / TWIN).read_text(encoding="utf-8")


def test_the_twin_still_defines_every_function_this_slice_names() -> None:
    """Thirty-nine, split three and thirty-six, measured rather than remembered."""
    text = twin_text()
    for name, _ in PORTED_FUNCTIONS:
        assert "\n%s() {" % name in text, "%s is gone from %s" % (name, TWIN)
    for name in NOT_PORTED_FUNCTIONS:
        assert "\n%s() {" % name in text, "%s is gone from %s" % (name, TWIN)
    assert len(PORTED_FUNCTIONS) + len(NOT_PORTED_FUNCTIONS) == 39
    # And the twin defines NOTHING ELSE, so a function added later cannot slip past the classification above unnoticed.
    defined = [
        line.split("(")[0] for line in text.split("\n") if line.startswith(("devbox_", "_devbox"))
    ]
    defined = [name for name in defined if "\n%s() {" % name in text]
    named = {name for name, _ in PORTED_FUNCTIONS} | set(NOT_PORTED_FUNCTIONS)
    assert set(defined) == named, "the twin's function set moved: %s" % sorted(set(defined) ^ named)


def test_the_ported_three_are_here() -> None:
    for _, attribute in PORTED_FUNCTIONS:
        assert callable(getattr(devbox, attribute, None)), (
            "%s is named as ported and is not callable on the module" % attribute
        )


def test_the_unported_thirty_six_have_no_python_counterpart() -> None:
    """The absence is the claim, so it is asserted rather than left to a reader.

    A future session porting `devbox_up` must delete its name from `NOT_PORTED_FUNCTIONS` here, which is the moment to ask how a `docker run` gets compared.
    """
    for name in NOT_PORTED_FUNCTIONS:
        stem = name.removeprefix("_devbox_").removeprefix("devbox_")
        assert not hasattr(devbox, stem), (
            "%s appeared in the port without this file's list being updated; a ledger row "
            "is a claim of equivalence and nothing compares that function" % stem
        )


def test_the_twin_is_still_sourced_and_nothing_is_cut_over() -> None:
    """The sequencing claim in the port's docstring, checked against every sourcer."""
    root = paths.repo_root()
    for relative, needle in SOURCE_SITES:
        text = (root / relative).read_text(encoding="utf-8")
        assert needle in text, (
            "%s no longer sources the twin; if this slice has been cut over, this "
            "differential needs a different subject" % relative
        )


def test_the_port_reaches_nothing_but_its_own_arguments() -> None:
    """The purity claim, asserted against the AST rather than against a reading.

    A subprocess, an environment read or a file open in the PORT would each make the differential a comparison of environments. The driver is exempt, because driving bash is its whole job.
    ASSERTED AGAINST THE AST AND NOT AGAINST THE TEXT, because the port DISCUSSES `git`, `docker` and the filesystem at length in its docstring and a plain substring search reds on the explanation rather than on the reach.
    """
    forbidden = {"os", "subprocess", "pathlib", "shutil", "sys", "tempfile", "socket"}
    tree = ast.parse((paths.repo_root() / PORT).read_text(encoding="utf-8"))
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.append(node.module or "")
    assert not forbidden.intersection(imported), (
        "the port imports %s, so it is no longer a function of its arguments alone"
        % sorted(forbidden.intersection(imported))
    )
    called = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "open" not in called, "the port opens a file"
    # THE CONTROL, IN THE OTHER DIRECTION. The same walk over the DRIVER, which really does run subprocesses, must find something; a walk that silently collected nothing would pass the loop above forever.
    driver_tree = ast.parse((paths.repo_root() / DRIVER).read_text(encoding="utf-8"))
    driver_imports: list[str] = []
    for node in ast.walk(driver_tree):
        if isinstance(node, ast.Import):
            driver_imports.extend(alias.name for alias in node.names)
    assert forbidden.intersection(driver_imports), (
        "the walk found no forbidden import in a file that genuinely runs subprocesses, so it "
        "proves nothing"
    )


# -- the rules, exercised directly -------------------------------------------

# The nine rows `test_gate_devbox_slug.py:49-59` pins. Restated here rather than imported, and then CROSS-CHECKED against that file, so a change to either is a failure in both rather than a silent agreement.
SLUG_ROWS = (
    ("feat/x", "feat-x"),
    ("feat//x", "feat-x"),
    ("Feature/ABC-123", "feature-abc-123"),
    ("--lead-and-trail--", "lead-and-trail"),
    ("0826-2", "0826-2"),
    ("feat/über", "feat-ber"),
    ("", ""),
    ("///", ""),
    (driver.LONG_BRANCH, "feature-an-extremely-long-branch-name-th"),
)


@pytest.mark.parametrize(("value", "expected"), SLUG_ROWS)
def test_slugify_answers_the_pinned_rows(value: str, expected: str) -> None:
    answer = devbox.slugify(value)
    assert answer == expected
    assert len(answer) <= devbox.SLUG_MAX
    if answer:
        assert HOSTNAME_RE.match(answer), "%r is not a legal DNS label" % answer


def test_the_pinned_rows_agree_with_the_gate_that_also_pins_them() -> None:
    """Two files carrying one table is one file too many unless they are compared."""
    assert dict(SLUG_ROWS) == dict(slug_gate.SLUG_ROWS), (
        "this file and %s disagree about the slug rule: %s"
        % ("test_gate_devbox_slug.py", sorted(set(SLUG_ROWS) ^ set(slug_gate.SLUG_ROWS)))
    )
    assert driver.LONG_BRANCH == slug_gate.LONG


def test_the_cap_is_applied_before_the_final_trim() -> None:
    """Reproduced behaviour 2: the answer can be 39 characters, not only 40."""
    assert devbox.slugify("a" * 39 + "-bcd") == "a" * 39
    assert devbox.slugify("a" * 40 + "-bcd") == "a" * 40
    assert devbox.slugify("a" * 41) == "a" * 40
    # And the other direction, so a port that always trimmed one character would fail here.
    assert len(devbox.slugify("a" * 40)) == 40


def test_the_empty_answer_is_still_a_line() -> None:
    """Reproduced behaviour 1, which is the difference between the two entry points."""
    assert devbox.slugify("///") == ""
    assert devbox.slugify_stdout("///") == "\n"
    assert devbox.slugify_stdout() == "\n"
    assert devbox.slugify_stdout("feat/x") == "feat-x\n"


def test_a_newline_in_the_argument_survives_because_sed_works_per_line() -> None:
    """Reproduced behaviour 3, pinned here because nothing in the tree passes one today."""
    assert devbox.slugify("a\nb") == "a\nb"
    assert devbox.slugify("-a-\n-b-") == "a\nb"
    # A TRAILING newline disappears, because command substitution strips it; a LEADING one does not.
    assert devbox.slugify("a\n") == "a"
    assert devbox.slugify("\na") == "\na"


def test_multibyte_collapses_to_one_dash_per_run() -> None:
    """Reproduced behaviour 4, over a 2-byte, a 3-byte and a 4-byte character."""
    assert devbox.slugify("feat/über") == "feat-ber"
    assert devbox.slugify("a日b") == "a-b"
    assert devbox.slugify("a\U0001f389b") == "a-b"
    assert devbox.slugify("ÄÖÜ") == ""
    # A byte that is not valid UTF-8 at all takes the same path, and is NOT dropped.
    assert devbox.slugify("a\udcffb") == "a-b"


def test_lowering_is_ascii_only() -> None:
    """`tr '[:upper:]' '[:lower:]'` under `LC_ALL=C` is A-Z, and nothing wider."""
    assert devbox.slugify("UPPER") == "upper"
    assert devbox.slugify("MiXeD/CaSe") == "mixed-case"
    # A dotted capital letter from the Turkish alphabet is not lowered: it is two bytes, so it becomes one dash and is then trimmed away.
    assert devbox.slugify("İstanbul") == "stanbul"
    assert devbox.lower_ascii(b"ABZ\xc3\x9f") == b"abz\xc3\x9f"


def test_the_separator_collision_is_deliberate() -> None:
    """`feat/x` and `feat-x` are different branches sharing one hostname, by design."""
    one, two = "feat/x", "feat-x"
    assert one != two, "the two collision inputs are identical, so this is vacuous"
    assert devbox.slugify(one) == devbox.slugify(two)


def test_slug_drift_reports_the_two_disagreements_and_nothing_else() -> None:
    """Every combination of the three names, against the rule spelled out."""
    assert devbox.slug_drift("alpha", "alpha", "alpha").out == ""
    assert devbox.slug_drift("alpha").out == ""
    assert devbox.slug_drift("alpha", "").out == ""
    renamed = devbox.slug_drift("beta", "alpha", "alpha").out
    assert "container serves alpha" in renamed
    assert "would use beta" in renamed
    stale = devbox.slug_drift("alpha", "alpha", "stale-name").out
    assert "records stale-name" in stale
    both = devbox.slug_drift("beta", "alpha", "stale-name").out
    assert len(both.splitlines()) == 2
    # An empty name on either side of a comparison silences that comparison.
    assert devbox.slug_drift("beta", "", "stale-name").out == ""
    assert devbox.slug_drift("", "alpha", "stale-name").out.splitlines() == [
        "drift: .devbox-state records stale-name, the container serves alpha"
    ]


def test_slug_drift_never_fails() -> None:
    """Reproduced behaviour 6: the result is what it printed, never its status."""
    for want, baked, recorded in (("a", "a", "a"), ("a", "b", "c"), ("", "", "")):
        assert devbox.slug_drift(want, baked, recorded).code == 0


@pytest.mark.parametrize(
    ("code", "hint", "routed", "expected"),
    [
        ("000", "", "unknown", "proxy unreachable"),
        ("000", "a hint", "yes", "proxy unreachable"),
        ("502", "", "unknown", "no backend yet"),
        ("502", "run account dev", "unknown", "no backend yet -- run account dev"),
        ("404", "", "no", "no such router -- nothing serves this hostname"),
        ("404", "a hint", "no", "no such router -- nothing serves this hostname"),
        ("404", "", "yes", "live (HTTP 404)"),
        ("404", "", "unknown", "no matching route, or a backend 404 (HTTP 404)"),
        ("404", "", "", "no matching route, or a backend 404 (HTTP 404)"),
        ("404", "", "maybe", "no matching route, or a backend 404 (HTTP 404)"),
        ("200", "", "unknown", "live (HTTP 200)"),
        ("301", "", "no", "live (HTTP 301)"),
        ("0", "", "unknown", "live (HTTP 0)"),
        ("0000", "", "unknown", "live (HTTP 0000)"),
        ("4040", "", "no", "live (HTTP 4040)"),
        ("404 ", "", "no", "live (HTTP 404 )"),
        ("", "", "unknown", "live (HTTP )"),
    ],
)
def test_route_label_never_lets_the_word_contradict_the_code(
    code: str, hint: str, routed: str, expected: str
) -> None:
    assert devbox.route_label(code, hint, routed).out == expected + "\n"


def test_an_unmatched_host_is_never_called_live() -> None:
    """The ship-blocker the third argument exists for, stated as its own claim."""
    assert "live" not in devbox.route_label("404", "", "no").out
    assert "live" in devbox.route_label("404", "", "yes").out
    assert "live" not in devbox.route_label("404", "", "unknown").out


def test_the_no_argument_call_is_a_death_and_not_a_default() -> None:
    """Reproduced behaviour 7, in all three directions."""
    for function in (devbox.slug_drift, devbox.route_label):
        with pytest.raises(devbox.DevboxError) as raised:
            function()
        assert raised.value.code == devbox.UNBOUND_STATUS
        assert str(raised.value) == devbox.UNBOUND_MESSAGE
    # And the one that does NOT die, because it is written `"${1:-}"`.
    assert devbox.slugify() == ""
    assert devbox.slugify(None) == ""


def test_the_helpers_are_exported_and_answer_on_their_own() -> None:
    """The pure stages, driven directly rather than only through `slugify`."""
    assert devbox.sanitise_line(b"--a--b--") == "a-b"
    assert devbox.sanitise_line(b"") == ""
    assert devbox.sanitise_line(b"----") == ""
    # THE STAGE ORDER, which this case exists to pin: `tr` runs BEFORE this, so an uppercase byte reaching here is outside the keep set and becomes a dash rather than a letter.
    assert devbox.sanitise_line(b"A") == ""
    assert devbox.sanitise_line(devbox.lower_ascii(b"A")) == "a"
    assert devbox.trim_dashes("-a-b-") == "a-b"
    assert devbox.trim_dashes("----") == ""
    # `trim_dashes` must NOT collapse: that is the first pass's job, and doing it twice would hide a defect in the first.
    assert devbox.trim_dashes("a--b") == "a--b"


# -- the licence, and the tools the scenarios really use ---------------------


def test_the_shadow_ledger_holds_five_equivalent_rows_over_five_trees() -> None:
    """The K=5 licence, read off disk rather than remembered from a session."""
    path = paths.repo_root() / LEDGER
    assert path.is_file(), "%s is missing; the port has no recorded licence" % LEDGER
    rows = [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    assert len(rows) >= 5, "%d row(s) recorded, five are required" % len(rows)
    assert all(row["verdict"] == "EQUIVALENT" for row in rows)
    assert len({row["tree"]["id"] for row in rows}) >= 5
    assert all(row["tree"]["clean"] for row in rows)
    assert all(TWIN in row["old"]["cmd"] for row in rows)
    assert all(PORT in row["new"]["cmd"] for row in rows)
    # The DISTINCT-EVIDENCE RULE: K trees carrying one finding set is one observation.
    assert len({row["old"]["fingerprint"] for row in rows}) >= 2
    # Every scenario is licensed, not just five of them.
    recorded = {row["new"]["cmd"].rsplit(" ", 1)[1] for row in rows}
    assert recorded == set(SCENARIOS), "the ledger covers %s" % sorted(recorded)


def test_the_ledger_carries_no_comment_audit_and_says_why() -> None:
    """THE ONE EXEMPTION THIS SLICE TAKES, kept visible rather than quiet.

    The comment-byte floor compares the WHOLE twin against the WHOLE port, which is the right denominator for a whole-file port and the wrong one for three functions out of thirty-nine: the other thirty-six carry comment archaeology this slice does not claim.
    Measured, so the number is on the record rather than asserted: the whole file scores 0.49, and the three ported functions' own comments score far above the floor. The rows are therefore recorded WITHOUT the two file arguments, on the `w7p5b-common` precedent, and this case fails if a row ever appears with a comment block whose ratio is below the floor.
    """
    path = paths.repo_root() / LEDGER
    rows = [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    for row in rows:
        ratio = row.get("comments", {}).get("ratio")
        assert ratio is None or ratio >= 0.9, (
            "a row carries a comment ratio of %s, which is below the floor and would fail "
            "--assert" % ratio
        )
    # The slice-level ratio, recomputed here so the claim above is a measurement and not a memory.
    twin = twin_text().split("\n")
    twin_comment_bytes = sum(
        len(line) + 1
        for start, end in ((181, 197), (240, 253), (810, 844))
        for line in twin[start - 1 : end]
        if line.strip().startswith("#")
    )
    assert twin_comment_bytes > 1000, (
        "the three functions' comment block collapsed to %d bytes, so the ratio below is "
        "measuring nothing" % twin_comment_bytes
    )
    port_bytes = len((paths.repo_root() / PORT).read_text(encoding="utf-8"))
    assert port_bytes / twin_comment_bytes >= 0.9, (
        "the port is thinner than the comments it replaced (%d against %d)"
        % (port_bytes, twin_comment_bytes)
    )


def test_the_tools_the_scenarios_use_are_installed() -> None:
    """ANTI-VACUITY. Without these the scenarios compare two identical failures."""
    for tool in ("bash", "sed", "tr", "od"):
        assert shutil.which(tool) is not None, (
            "%s is absent, so the scenarios that use it compare two identical failures "
            "and prove nothing about the port" % tool
        )


def test_the_driver_refuses_when_the_twin_is_not_there() -> None:
    """The driver's own control, driven rather than read."""
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            DRIVER_MODULE,
            "--side",
            "old",
            "--twin",
            ".ci/lib/no-such-file.sh",
            "--port",
            PORT,
            "arity",
        ],
        cwd=str(paths.repo_root()),
        env={**os.environ, "PYTHONPATH": ".ci"},
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == driver.EXIT_CANNOT_RUN
    assert "attests to nothing" in proc.stderr


def test_the_driver_scenarios_and_the_bash_bodies_line_up() -> None:
    """Every scenario the driver offers has a bash body, which is what `old` runs."""
    assert isinstance(driver.BASH_SCENARIOS, dict)
    for name, body in driver.BASH_SCENARIOS.items():
        assert body.strip(), "scenario %s has an empty bash body" % name
        assert "probe " in body, "scenario %s calls nothing" % name
        assert "%(fn)s" not in body, "scenario %s was never interpolated" % name


def test_the_repo_root_is_a_checkout_with_the_twin_in_it() -> None:
    """A last refusal: everything above is relative to this."""
    assert (paths.repo_root() / TWIN).is_file()
    assert (paths.repo_root() / PORT).is_file()
    assert pathlib.Path(DRIVER).name == "devbox_shadow_driver.py"
