"""`rediacc_ci.core.local_common` against the live `.ci/lib/local-common.sh`.

THE TWIN IS STILL HERE AND IS STILL THE ONLY IMPLEMENTATION OF TWENTY-ONE OF ITS THIRTY FUNCTIONS.
`rdc.sh:18`, `.ci/legacy/run-legacy.sh:47`, `.ci/media/media-entry.sh:50`, `.ci/rediacc_ci/native.py:137` and `.ci/scripts/test/gates/test-run-sh.sh:116` all still source it, nothing is cut over, and this file drives the bash for real on every run: `rediacc_ci.core.local_common_shadow_driver` sources `local-common.sh` through the same prelude `run-legacy.sh` uses and calls the twin's own functions, then does the same work through the port, and the two transcripts are compared byte for byte.

WHAT IS COVERED AND WHAT IS NOT is decided by the driver's seven scenarios and stated in its module docstring rather than restated here.
The short version: everything whose answer is computation over a local file or a local git read, and none of the eleven installers, the three interactive or session-altering functions, or the three `gate_lane_*` functions, which reach into `.ci/lib/devbox.sh`.

THE ANTI-VACUITY CLAIMS, because a differential that compared two empty transcripts would pass forever: every scenario must produce a floor of observations, the tools the scenarios really use must be installed, and `test_the_differential_can_fail` mutates one side and demands a mismatch in each of the four places a mutation can hide.

THE TWO CONTROLS THE DIFFERENTIAL CANNOT REACH have their own cases here, and one of them found a real defect.
Every scenario runs with `sha256sum` on PATH, so neither missing-tool branch is reachable from the ledger; `test_no_sha256_tool_degrades_the_same_way_on_both_sides` builds a PATH farm without it and measured `compute_hash_for_package_dirs` exiting 125, where the port had assumed 0.
"""

import ast
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys

import pytest

from rediacc_ci import paths
from rediacc_ci.core import account, local_common, stubfarm
from rediacc_ci.core import local_common_actions_shadow_driver as actions_driver
from rediacc_ci.core import local_common_shadow_driver as driver

TWIN = ".ci/lib/local-common.sh"
PORT = ".ci/rediacc_ci/core/local_common.py"
DRIVER = ".ci/rediacc_ci/core/local_common_shadow_driver.py"
# Invoked as a MODULE, never by path: see the driver's header for why the by-path form would need a hand-written sys.path hop that `test_canonical_sys_path_hop.py` refuses.
DRIVER_MODULE = "rediacc_ci.core.local_common_shadow_driver"
LEDGER = ".ci/shadow/w7p5b-local-common.observations.jsonl"

SCENARIOS = sorted(driver.BASH_SCENARIOS)

# The floor each scenario must clear. Measured against the recorded ledger rows, then rounded DOWN so a real change to a message does not turn into a test edit; the point is to catch a transcript collapsing to nothing, not to pin a count.
OBSERVATION_FLOOR = {
    "git-fp": 12,
    "hash": 30,
    "npm-script": 12,
    "sed": 18,
    "stamp": 20,
    "tree-hash": 10,
    "version": 70,
}

# The program the missing-sha256 control runs on the port side. Hoisted out of the call so it is one string rather than an implicit concatenation inside an argument list, which reads as a forgotten comma.
PORT_PROBE = """import os
from rediacc_ci.core import local_common
o = local_common.compute_hash_for_package_dirs(os.environ['CONSOLE_ROOT_DIR'], ['pkg'])
print('walk=%d out=[%s]' % (o.code, o.out.strip()))
try:
    local_common.sha256sum([os.environ['CONSOLE_ROOT_DIR'] + '/plain.txt'])
    print('sha=0')
except local_common.LocalCommonError as exc:
    print('sha=%d' % exc.code)
"""

_CACHE: dict[tuple[str, str], tuple[int, str, str]] = {}


def drive(side: str, scenario: str) -> tuple[int, str, str]:
    """One side of one scenario, run once per session and remembered.

    Cached because every case below wants the same transcript and each run of the bash side sources `constants.sh`, `toolchain.sh` and `local-common.sh` and builds a git repository before it does anything at all.
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

    The floor is per scenario and deliberately low, because the claim is that the scenario ran at all rather than that it printed a particular number of lines.
    """
    _, out, _ = drive("old", scenario)
    lines = [line for line in out.splitlines() if line.startswith("obs ")]
    assert len(lines) >= OBSERVATION_FLOOR[scenario], (
        "scenario %s produced %d observation(s), under its floor of %d; a transcript "
        "this short means the twin stopped early and the comparison proved nothing"
        % (scenario, len(lines), OBSERVATION_FLOOR[scenario])
    )


def test_the_corpus_is_not_empty() -> None:
    assert len(SCENARIOS) >= 7, "the scenario set collapsed to %d" % len(SCENARIOS)
    assert set(SCENARIOS) == set(OBSERVATION_FLOOR), (
        "a scenario was added or removed without a floor: %s"
        % sorted(set(SCENARIOS) ^ set(OBSERVATION_FLOOR))
    )


def test_the_differential_can_fail() -> None:
    """A CONTROL ON THE COMPARISON, in the four places a mutation can hide.

    Each line below is a transcript the port could plausibly produce and the twin does not, so a comparison that still called it equal would be looking at the wrong thing.
    """
    _, hash_out, _ = drive("old", "hash")
    assert hash_out != hash_out.replace("obs rc walk-missing=1", "obs rc walk-missing=0"), (
        "the hash transcript carries no exit code, so a port that swallowed one would pass"
    )
    digests = re.findall(r"\b[0-9a-f]{64}\b", hash_out)
    assert len(digests) >= 8, (
        "the hash transcript carries %d digest(s), so a port that hashed the wrong bytes "
        "would have little to disagree about" % len(digests)
    )
    assert hash_out != hash_out.replace(digests[0], "0" * 64)
    _, stamp_out, _ = drive("old", "stamp")
    assert stamp_out != stamp_out.replace("obs file write-simple| ", "obs file write-simple|"), (
        "the stamp transcript carries no file dump, so a rewritten stamp would pass"
    )
    _, version_out, _ = drive("old", "version")
    assert version_out != version_out.replace("] = 0", "] = 1"), (
        "the version transcript carries no verdict, so an inverted comparison would pass"
    )


# -- the twin is still there, and still says what this file claims it says ----


def twin_text() -> str:
    return (paths.repo_root() / TWIN).read_text(encoding="utf-8")


# (bash name, the attribute it became here). `_version_gte` loses its underscore because a module-private name in bash is not a module-private name in Python; `_ensure_docker_group`, `_renet_source_hash` and `_renet_artifact_fp` the same.
PORTED_FUNCTIONS = (
    ("_sha256sum", "sha256sum"),
    ("_sed_i", "sed_i"),
    ("compute_hash_for_package_dirs", "compute_hash_for_package_dirs"),
    ("_git_tree_fingerprint", "git_tree_fingerprint"),
    ("compute_tree_hash", "compute_tree_hash"),
    ("read_stamp_hash", "read_stamp_hash"),
    ("write_stamp_hash", "write_stamp_hash"),
    ("_version_gte", "version_gte"),
    ("has_npm_script", "has_npm_script"),
    # The machine-mutating half, 2026-09-24, proved by `core/local_common_actions_shadow_driver.py`.
    ("ensure_cpu_features_gypi", "ensure_cpu_features_gypi"),
    ("ensure_deps", "ensure_deps"),
    ("ensure_packages_built", "ensure_packages_built"),
    ("ensure_cli_built", "ensure_cli_built"),
    ("prompt_continue", "prompt_continue"),
    ("open_browser", "open_browser"),
    ("run_npm_script", "run_npm_script"),
    ("check_node_version", "check_node_version"),
    ("check_go_installed", "check_go_installed"),
    ("ensure_go_installed", "ensure_go_installed"),
    ("ensure_bashcov_sup", "ensure_bashcov_sup"),
    ("ensure_host_tools", "ensure_host_tools"),
    ("reexec_with_docker_group", "reexec_with_docker_group"),
    ("ensure_docker_installed", "ensure_docker_installed"),
    ("_ensure_docker_group", "ensure_docker_group"),
    ("_renet_source_hash", "renet_source_hash"),
    ("_renet_artifact_fp", "renet_artifact_fp"),
    ("ensure_renet_built", "ensure_renet_built"),
    ("gate_lane_decide", "gate_lane_decide"),
    ("gate_lane_should_route", "gate_lane_should_route"),
    ("gate_lane_run", "gate_lane_run"),
)

# Nothing is left. Kept as a named empty tuple so the "defines these AND NOTHING ELSE" assertion below still has both halves to add up.
NOT_PORTED_FUNCTIONS: tuple[str, ...] = ()


def test_the_twin_still_defines_every_function_this_slice_names() -> None:
    """Thirty, measured rather than remembered."""
    text = twin_text()
    for name, _ in PORTED_FUNCTIONS:
        assert "\n%s() {" % name in text, "%s is gone from %s" % (name, TWIN)
    for name in NOT_PORTED_FUNCTIONS:
        assert "\n%s() {" % name in text, "%s is gone from %s" % (name, TWIN)
    assert len(PORTED_FUNCTIONS) + len(NOT_PORTED_FUNCTIONS) == 30
    # And the twin defines NOTHING ELSE, so a function added later cannot slip past the classification above unnoticed.
    defined = [line.split("(")[0] for line in text.split("\n") if line.endswith("() {")]
    named = {name for name, _ in PORTED_FUNCTIONS} | set(NOT_PORTED_FUNCTIONS)
    assert set(defined) == named, "the twin's function set moved: %s" % sorted(set(defined) ^ named)


def test_the_ported_half_is_here() -> None:
    for _, attribute in PORTED_FUNCTIONS:
        assert callable(getattr(local_common, attribute, None)), (
            "%s is named as ported and is not callable on the module" % attribute
        )


def test_the_unported_half_has_no_python_counterpart() -> None:
    """The absence is the claim, so it is asserted rather than left to a reader.

    A future session porting `ensure_deps` must delete its name from `NOT_PORTED_FUNCTIONS` here, which is the moment to ask how an `npm install` gets compared.
    """
    for name in NOT_PORTED_FUNCTIONS:
        stem = name.lstrip("_")
        assert not hasattr(local_common, stem), (
            "%s appeared in the port without this file's list being updated; a ledger row "
            "is a claim of equivalence and nothing compares that function" % stem
        )


def test_the_twin_is_still_sourced_and_nothing_is_cut_over() -> None:
    """The sequencing claim in the port's docstring, checked against every sourcer."""
    root = paths.repo_root()
    for relative, needle in (
        ("rdc.sh", 'source "$ROOT_DIR/.ci/lib/local-common.sh"'),
        (".ci/legacy/run-legacy.sh", 'source "$ROOT_DIR/.ci/lib/local-common.sh"'),
        (".ci/media/media-entry.sh", 'source "$ROOT_DIR/.ci/lib/local-common.sh"'),
        (".ci/rediacc_ci/native.py", 'source "$1/.ci/lib/local-common.sh"'),
    ):
        text = (root / relative).read_text(encoding="utf-8")
        assert needle in text, (
            "%s no longer sources the twin; if this slice has been cut over, this "
            "differential needs a different subject" % relative
        )


def test_the_lane_reaches_devbox_only_through_the_port() -> None:
    """The three `gate_lane_*` functions call `.ci/lib/devbox.sh` in the twin; the port must reach `core.devbox`, never the bash file.

    ASSERTED AGAINST THE AST: a live string naming `devbox.sh` in the port would be a bash bridge wearing a Python name. The walk must find `devbox` tokens in the port (it imports `core.devbox`) and must find NO `devbox.sh` literal. The pure-half driver stays devbox-free, as that slice ruled.
    """
    twin = twin_text()
    for name in ("devbox_state_get", "devbox_container_running", "devbox_exec"):
        assert name in twin, "%s left the twin, so the coupling claim is stale" % name
    port_tokens = live_tokens_naming(PORT, "devbox")
    assert port_tokens != [], (
        "the port names nothing devbox-shaped, so the lane cannot be reaching core.devbox"
    )
    assert not any("devbox.sh" in token for token in port_tokens), port_tokens
    assert live_tokens_naming(DRIVER, "devbox") == []


def live_tokens_naming(relative: str, needle: str) -> list[str]:
    """Every identifier and non-docstring string literal in `relative` carrying `needle`.

    Docstrings are excluded because both files under this rule DISCUSS the thing they must not reach, at length, and a plain substring search reds on the explanation rather than on the reach.
    """
    tree = ast.parse((paths.repo_root() / relative).read_text(encoding="utf-8"))
    docstrings = {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef))
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
        and isinstance(node.body[0].value.value, str)
    }
    live: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            live.append(node.id)
        elif isinstance(node, ast.Attribute):
            live.append(node.attr)
        elif (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and id(node) not in docstrings
        ):
            live.append(node.value)
    return [token for token in live if needle in token.lower()]


# -- the helpers, exercised directly -----------------------------------------


def test_sha256_line_escapes_the_way_the_tool_on_this_machine_escapes(tmp_path) -> None:
    r"""A backslash in a name changes the BYTES the outer hash sees, so it is measured.

    The control is the ordinary name in the same call: a rule that escaped everything would pass a one-sided assertion.
    """
    plain = tmp_path / "plain.txt"
    plain.write_text("x", encoding="utf-8")
    weird = tmp_path / "back\\slash.txt"
    weird.write_text("x", encoding="utf-8")
    proc = subprocess.run(
        ["sha256sum", str(plain), str(weird)], capture_output=True, text=True, check=True
    )
    digest = local_common.digest_file(str(plain))
    expected = local_common.sha256_line(digest, str(plain)) + local_common.sha256_line(
        digest, str(weird)
    )
    assert proc.stdout == expected
    assert not expected.startswith("\\"), "the plain name must NOT be escaped"
    assert "\\%s" % digest in expected, "the backslash name must be escaped"


def test_the_empty_file_set_is_not_the_hash_of_nothing(tmp_path) -> None:
    """Reproduced behaviour 1, pinned against the live pipeline rather than a constant."""
    (tmp_path / "empty").mkdir()
    outcome = local_common.compute_hash_for_package_dirs(str(tmp_path), ["empty"])
    proc = subprocess.run(
        [
            "bash",
            "-c",
            "cd %s && find empty -type f -print0 2>/dev/null | LC_ALL=C sort -z | "
            "xargs -0 sha256sum 2>/dev/null | sha256sum | awk '{print $1}'" % tmp_path,
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert outcome.out == proc.stdout
    # And it is NOT the hash of an empty stream, which is what a reasonable port would answer.
    assert outcome.out.strip() != local_common.EMPTY_STDIN_LINE.split()[0]


@pytest.mark.parametrize(
    ("path", "pruned"),
    [
        ("pkg/dist/a.js", True),
        ("pkg/dist/sub", True),
        ("pkg/node_modules/x/d.js", True),
        ("pkg/reports/r.json", True),
        ("pkg/test-results/t.xml", True),
        ("pkg/e.tsbuildinfo", True),
        ("pkg/.DS_Store", True),
        # The other direction, which is what stops the rule from pruning the whole tree.
        ("pkg/dist", False),
        ("pkg/src/c.ts", False),
        ("pkg/README.md", False),
        ("pkg/distant/a.js", False),
        ("pkg/src/dist.ts", False),
        ("pkg/reportsx/r.json", False),
    ],
)
def test_is_pruned_both_directions(path: str, pruned: bool) -> None:
    assert local_common.is_pruned(path) is pruned


def test_a_stamp_grows_a_newline_and_the_reader_keeps_it(tmp_path) -> None:
    """Reproduced behaviour 5, and the nested-directory creation in the same call."""
    target = tmp_path / "deep" / "nested" / "out.stamp"
    local_common.write_stamp_hash(str(target), "deadbeef")
    assert target.read_text(encoding="utf-8") == "deadbeef\n"
    assert local_common.read_stamp_hash(str(target)) == "deadbeef\n"
    # The two-line shape `ensure_renet_built:907` writes, and the `sed -n 1p` it reads back.
    local_common.write_stamp_hash(str(target), "abc\nbin=4096:1700000000")
    assert local_common.read_stamp_hash(str(target)).split("\n")[0] == "abc"
    # A missing file is the empty string and not an error, which is why a fresh checkout reads as stale rather than as a failure.
    assert local_common.read_stamp_hash(str(tmp_path / "nosuch")) == ""
    assert local_common.read_stamp_hash(str(tmp_path)) == ""


def test_write_stamp_hash_handles_a_bare_relative_name(tmp_path, monkeypatch) -> None:
    """`dirname foo` is `.` and `os.path.dirname('foo')` is the empty string."""
    monkeypatch.chdir(tmp_path)
    local_common.write_stamp_hash("relative.stamp", "rel")
    assert (tmp_path / "relative.stamp").read_text(encoding="utf-8") == "rel\n"


def test_version_gte_agrees_with_the_sort_v_the_twin_actually_runs() -> None:
    """The transcribed `filevercmp`, checked against the live tool over every pair.

    `sort -V` here is uutils 0.8.0 rather than GNU coreutils (see the port's docstring), so this drives the binary on PATH rather than asserting against a table somebody typed. One `bash` process for the whole corpus, because 72 of them is 40 seconds.
    """
    pairs = driver.VERSION_PAIRS
    assert len(pairs) >= 70, "the version corpus collapsed to %d pair(s)" % len(pairs)
    script = (
        '_version_gte() { [[ "$1" == "$2" ]] && return 0; local lower; '
        'lower="$(printf \'%s\\n%s\\n\' "$1" "$2" | sort -V | head -1)"; '
        '[[ "$lower" == "$2" ]]; }\n'
        "while IFS='|' read -r a b; do\n"
        '  if _version_gte "$a" "$b"; then echo 0; else echo 1; fi\n'
        "done\n"
    )
    payload = "".join("%s|%s\n" % pair for pair in pairs)
    proc = subprocess.run(
        ["bash", "-c", script],
        input=payload,
        capture_output=True,
        text=True,
        check=True,
        env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LC_ALL": "C"},
    )
    answers = [line for line in proc.stdout.split("\n") if line != ""]
    assert len(answers) == len(pairs)
    for index, (one, two) in enumerate(pairs):
        expected = answers[index] == "0"
        assert local_common.version_gte(one, two) is expected, (
            "version_gte(%r, %r) disagrees with the live sort -V" % (one, two)
        )
    # ANTI-VACUITY: the corpus must exercise BOTH verdicts, or a constant would pass.
    assert "0" in answers, "every pair answered false, so a constant would pass"
    assert "1" in answers, "every pair answered true, so a constant would pass"


def test_version_gte_gets_the_cases_a_dotted_split_gets_wrong() -> None:
    """The four orderings that motivated transcribing `filevercmp` rather than splitting."""
    assert local_common.version_gte("1.10", "1.9") is True
    assert local_common.version_gte("1.9", "1.10") is False
    # `~` sorts before the end of a string, so a tilde release precedes its own version.
    assert local_common.version_gte("2.0", "2.0~rc1") is True
    assert local_common.version_gte("2.0~rc1", "2.0") is False
    # LEADING ZEROS COLLAPSE UNDER -V, so these tie there and `sort`'s LAST-RESORT byte compare decides, which makes the pair ASYMMETRIC in a way no version intuition predicts. Measured against the twin: `_version_gte 1.00 1.0` is 0 and `_version_gte 01.0 1.0` is 1, because `1.00` sorts after `1.0` byte-wise while `01.0` sorts before it.
    assert local_common.version_gte("1.00", "1.0") is True
    assert local_common.version_gte("01.0", "1.0") is False


def test_has_npm_script_refuses_a_name_that_is_not_a_literal(tmp_path) -> None:
    """The one place the port refuses where the twin would quietly pattern-match."""
    (tmp_path / "package.json").write_text('{"scripts":{"abc":"x"}}', encoding="utf-8")
    env = {"LOCAL_ROOT_DIR": str(tmp_path)}
    with pytest.raises(ValueError, match="BRE metacharacter"):
        local_common.has_npm_script("a.c", env)
    # The control: an ordinary name still answers in both directions.
    assert local_common.has_npm_script("abc", env) is True
    assert local_common.has_npm_script("nosuch", env) is False


def test_has_npm_script_finds_a_dependency_name_too(tmp_path) -> None:
    """Reproduced behaviour 3, preserved rather than corrected.

    The twin greps the whole file, so a dependency and the manifest's own keys answer true. Anything that narrowed this to the `scripts` object would be a different function with the same name.
    """
    (tmp_path / "package.json").write_text(
        '{\n  "name": "x",\n  "scripts": {"build": "b"},\n  "dependencies": {"zod": "^4"}\n}\n',
        encoding="utf-8",
    )
    env = {"LOCAL_ROOT_DIR": str(tmp_path)}
    assert local_common.has_npm_script("build", env) is True
    assert local_common.has_npm_script("zod", env) is True
    assert local_common.has_npm_script("name", env) is True
    assert local_common.has_npm_script("buil", env) is False


def test_has_npm_script_exits_two_on_a_missing_manifest(tmp_path) -> None:
    """Reproduced behaviour 4: that is grep's status, and it is not 1."""
    env = {"LOCAL_ROOT_DIR": str(tmp_path / "nowhere")}
    with pytest.raises(local_common.LocalCommonError) as raised:
        local_common.has_npm_script("build", env)
    assert raised.value.code == 2


def test_the_local_root_seam_derives_the_same_three_paths() -> None:
    env = {"LOCAL_ROOT_DIR": "/somewhere"}
    assert local_common.local_root_dir(env) == "/somewhere"
    assert local_common.local_ci_dir(env) == "/somewhere/.ci"
    assert local_common.local_lib_dir(env) == "/somewhere/.ci/lib"
    # `CONSOLE_ROOT_DIR` is the fallback, and the repository root is the last resort.
    assert local_common.local_root_dir({"CONSOLE_ROOT_DIR": "/elsewhere"}) == "/elsewhere"
    assert local_common.local_root_dir({}) == str(paths.repo_root())


def test_cd_error_reports_the_three_shapes_bash_reports(tmp_path) -> None:
    """The diagnostic an unusable root produces, and the control that a good one is silent."""
    good = tmp_path / "dir"
    good.mkdir()
    assert local_common.cd_error(str(good)) is None
    missing = local_common.cd_error(str(tmp_path / "nosuch"))
    assert missing is not None
    assert missing.endswith("No such file or directory")
    plain = tmp_path / "file.txt"
    plain.write_text("x", encoding="utf-8")
    not_a_directory = local_common.cd_error(str(plain))
    assert not_a_directory is not None
    assert not_a_directory.endswith("Not a directory")


def test_git_tree_fingerprint_refuses_outside_a_work_tree(tmp_path) -> None:
    """None where the twin prints nothing and exits 1, in the two reachable shapes."""
    plain = tmp_path / "plain"
    plain.mkdir()
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "GIT_CEILING_DIRECTORIES": str(tmp_path),
    }
    assert local_common.git_tree_fingerprint(str(plain), ["."], env) is None
    assert local_common.git_tree_fingerprint(str(tmp_path / "nosuch"), ["."], env) is None
    # And the fallback really is a different function: `compute_tree_hash` still answers.
    (plain / "a.txt").write_text("a\n", encoding="utf-8")
    fallback = local_common.compute_tree_hash(str(plain), ["."], env)
    assert fallback.code == 0
    assert len(fallback.out.strip()) == 64


def test_no_sha256_tool_degrades_the_same_way_on_both_sides(tmp_path) -> None:
    """THE CASE THAT FOUND A REAL PORT DEFECT, kept because the differential cannot reach it.

    Every scenario runs with `sha256sum` installed, so neither missing-tool branch is in the ledger.
    Reaching them means taking the tool away, and that measurement showed `compute_hash_for_package_dirs` exiting 125 rather than the 0 this port had assumed: `xargs` with no command runs `echo`, nothing reads the pipe, `echo` takes SIGPIPE, and `pipefail` carries a signal-killed child out as 125.

    The farm below is every binary in `/usr/bin` and `/bin` EXCEPT the two sha256 tools, because `constants.sh` and `local-common.sh` need a working environment to load at all and a hand-listed minimal PATH dies on `dirname` before it reaches the subject.
    """
    farm = tmp_path / "nosha"
    farm.mkdir()
    linked = 0
    for directory in ("/usr/bin", "/bin"):
        source = pathlib.Path(directory)
        if not source.is_dir():
            continue
        for entry in source.iterdir():
            if entry.name in ("sha256sum", "shasum") or (farm / entry.name).exists():
                continue
            (farm / entry.name).symlink_to(entry)
            linked += 1
    assert linked > 100, "the PATH farm collapsed to %d binaries; nothing below would run" % linked
    for name in ("sha256sum", "shasum"):
        assert not (farm / name).exists(), (
            "%s survived into the farm, so this proves nothing" % name
        )
    assert shutil.which("sha256sum") is not None, (
        "sha256sum is absent anyway, so the control is not a control"
    )

    work = driver.build_sandbox(paths.repo_root())
    try:
        driver.build_hash_tree(work)
        env = {
            "PATH": str(farm),
            "HOME": os.environ.get("HOME", "/tmp"),
            "LC_ALL": "C",
            "CONSOLE_ROOT_DIR": str(work),
            "REDIACC_CI_ROOT": str(work),
        }
        script = (
            'W="%s"\nset -euo pipefail\n'
            'source "$W/.ci/config/constants.sh"\n'
            'source "$W/.ci/scripts/lib/toolchain.sh"\n'
            'source "$W/.ci/lib/local-common.sh"\n'
            "set +e\n"
            '( set -e; _sha256sum "$W/plain.txt" ) >/dev/null 2>&1; echo "sha=$?"\n'
            'o="$( ( set -e; compute_hash_for_package_dirs "$W" pkg ) 2>/dev/null )"\n'
            'echo "walk=$? out=[$o]"\n' % work
        )
        twin = subprocess.run(
            ["bash", "-c", script], env=env, capture_output=True, text=True, check=False
        )
        assert "sha=1" in twin.stdout, "the twin did not reach its refusal: %s" % twin.stdout
        walk_line = next(line for line in twin.stdout.split("\n") if line.startswith("walk="))
        twin_walk_code = int(walk_line.split()[0].split("=")[1])
        assert "out=[]" in walk_line, "the twin printed a hash with no tool: %s" % walk_line

        # The port, over the same tree, with the same tool absent.
        port = subprocess.run(
            [
                sys.executable,
                "-c",
                PORT_PROBE,
            ],
            cwd=str(paths.repo_root()),
            env={**env, "PYTHONPATH": ".ci"},
            capture_output=True,
            text=True,
            check=False,
        )
        assert "Traceback" not in port.stderr, (
            "the port raised instead of answering: %s" % port.stderr
        )
        assert "sha=1" in port.stdout, port.stdout
        assert "walk=%d out=[]" % twin_walk_code in port.stdout, (
            "the port answered %r where the twin answered walk=%d with an empty hash"
            % (port.stdout.strip(), twin_walk_code)
        )
        assert twin_walk_code == local_common.XARGS_KILLED_BY_SIGNAL
    finally:
        shutil.rmtree(work, ignore_errors=True)

    # THE OTHER DIRECTION: with the tool present the same helpers still answer.
    assert local_common.sha256_command()[0] in ("sha256sum", "shasum")
    assert local_common.sha256sum([], stdin=b"").out == local_common.EMPTY_STDIN_LINE


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


def test_the_tools_the_scenarios_use_are_installed() -> None:
    """ANTI-VACUITY. Without these the scenarios compare two identical failures."""
    for tool in ("git", "sha256sum", "sort", "sed", "grep", "xargs", "awk", "bash"):
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
            "hash",
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
        assert "step " in body or "emit " in body, "scenario %s calls nothing" % name


def test_the_repo_root_is_a_checkout_with_the_twin_in_it() -> None:
    """A last refusal: everything above is relative to this."""
    assert (paths.repo_root() / TWIN).is_file()
    assert (paths.repo_root() / PORT).is_file()
    assert pathlib.Path(DRIVER).name == "local_common_shadow_driver.py"


# -- the machine-mutating half, against a stub farm ---------------------------
#
# Driven by `rediacc_ci.core.local_common_actions_shadow_driver`: each case runs both sides as child processes in one fixed sandbox with `npm`, `node`, `go`, `sudo`, `curl`, `tar`, `gcc`, `docker` and `sg` stubbed, and compares rc, both streams, the ordered stub transcript and the whole sandbox tree afterwards. Every case drives the LIVE twin.

ACTION_CASES = [
    (scenario, case) for scenario, cases in actions_driver.SCENARIOS.items() for case in cases
]


@pytest.mark.parametrize(
    ("scenario", "case"), ACTION_CASES, ids=["%s/%s" % (s, c.name) for s, c in ACTION_CASES]
)
def test_actions_match_the_live_twin(scenario, case) -> None:
    repo = paths.repo_root()
    with actions_driver.locked():
        old = actions_driver.observe("old", repo, case)
        new = actions_driver.observe("new", repo, case)
    assert old == new, "case %s/%s diverged" % (scenario, case.name)


def test_every_ported_action_is_driven() -> None:
    """ANTI-VACUITY: every machine-mutating function has at least one case."""
    driven = {actions_driver.FN[c.verb] for _, c in ACTION_CASES}
    actions = {name for name, _ in PORTED_FUNCTIONS[9:]}
    assert len(actions) == 21
    assert actions <= driven, "not driven: %s" % sorted(actions - driven)


def test_the_action_farm_really_shadows_npm() -> None:
    """ANTI-VACUITY: the stubs are what the cases reach, and the cases reach them."""
    case = actions_driver.SCENARIOS["deps"][0]
    with actions_driver.locked():
        root, farm = actions_driver.build_sandbox(paths.repo_root(), case)
        env = actions_driver.side_env(root, farm, case)
        for name in ("npm", "node", "sudo", "docker", "uname"):
            assert stubfarm.shadows(farm, name, env), "%s is not the stub" % name
        lines = actions_driver.observe("old", paths.repo_root(), case)
    assert sum(" call#" in line for line in lines) >= 3


def test_a_hidden_tool_is_really_absent() -> None:
    """CONTROL ON `Farm.host_path`: a hidden name must not resolve, and an unhidden one must."""
    case = actions_driver.Case("probe", "ensure-host-tools", hidden=("jq",), unstub=("curl",))
    with actions_driver.locked():
        root, farm = actions_driver.build_sandbox(paths.repo_root(), case)
        env = actions_driver.side_env(root, farm, case)
    assert shutil.which("jq", path=env["PATH"]) is None
    assert shutil.which("python3", path=env["PATH"]) is not None


@pytest.mark.parametrize(
    "word",
    [
        "",
        "a",
        "a b",
        "it's",
        'say "hi"',
        "$HOME",
        "`x`",
        "a,b",
        "#c",
        "c#",
        "~d",
        "d~",
        "=x",
        "x=y",
        "a\\b",
        "tab\there",
        "line\nbreak",
        "\x01",
        "\x7f",
        "esc\x1b",
        "é",
        "ü ö",
        "!bang",
        "*?[]",
        "{a,b}",
        "(x)",
        "a|b&c;d",
        "<in>out",
        "^caret",
        "100%",
        "@at",
        "+plus",
    ],
)
@pytest.mark.parametrize("locale", ["C", "C.UTF-8"])
def test_bash_q_matches_printf_q(word, locale, monkeypatch) -> None:
    """`bash_q` against the live `printf %q`, byte for byte, in both locales the twin can run under."""
    monkeypatch.setenv("LC_ALL", locale)
    proc = subprocess.run(
        ["bash", "-c", 'printf "%q" "$1"', "q", word],
        capture_output=True,
        env={"PATH": "/usr/bin:/bin", "LC_ALL": locale},
        check=True,
    )
    assert local_common.bash_q(word) == proc.stdout.decode("utf-8", "surrogateescape")


def test_check_node_version_agrees_with_the_account_copy() -> None:
    """TWO PYTHON COPIES OF ONE BASH FUNCTION EXIST, and this pins that they agree until one is deleted.

    `core/account.py` re-implemented `check_node_version` with its own `version_tuple` compare before this module ported it with the twin's `sort -V` comparator. `account.py` was under another writer's live rewrite (PLAN-account-env-to-bws) when this port landed, so the duplicate is handed over rather than removed from under them; this case keeps the two from drifting in the meantime.
    """
    for have, want in (
        ("22.1.0", "18.0.0"),
        ("16.20.2", "18.0.0"),
        ("22.9.0", "22.10.0"),
        ("18.0.0", "18.0.0"),
    ):
        assert local_common.version_gte(have, want) == (
            account.version_tuple(have) >= account.version_tuple(want)
        ), (have, want)


def test_the_actions_ledger_holds() -> None:
    proc = subprocess.run(
        [
            "npx",
            "tsx",
            "scripts/lib/shadow-gate.ts",
            "--pair",
            "w7p5b-local-common-actions",
            "--assert",
            "--k",
            "5",
        ],
        cwd=paths.repo_root(),
        capture_output=True,
        text=True,
        check=False,
        timeout=180,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
