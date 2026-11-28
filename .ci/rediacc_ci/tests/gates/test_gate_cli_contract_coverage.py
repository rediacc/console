"""Gate test for `rediacc_ci.quality.cli_contract_coverage` (`check:ci-cli-contract-coverage`).

The gate reads the committed CLI contract and its 13 locale bundles and refuses a command without a severity, a summaryKey, or a summary of 1 to 100 characters present in every bundle, a preview flag naming no option, and an error code without an origin (PLAN-console-contract-semantics.md D8).

BOTH DIRECTIONS, ON THE REAL SHAPE. The selftest proves the rules against a two-command fixture. That proves the helpers, not that the gate reads the contract the generator actually writes, so the plants here start from a COPY OF THE REAL `packages/shared/src/cli-contract/data` under a root override and change exactly one thing each. The unplanted copy is the control: it must be green, or every red below could be red for a reason unrelated to its plant.

ZERO INPUTS IS 77. An empty root has no contract; the gate must say it cannot run, never report a clean tree, and never mistake it for a finding either.

NO `xdist_group`. Every case is a short-lived subprocess over the real tree (read only) or over its own tmp_path copy.
"""

import inspect
import json
import pathlib
import shutil
import sys

from rediacc_ci import paths
from rediacc_ci.quality import cli_contract_coverage as ccc
from rediacc_ci.tests.gates import harness

MODULE = "rediacc_ci.quality.cli_contract_coverage"
SUT = paths.from_root(".ci", "rediacc_ci", "quality", "cli_contract_coverage.py")
DATA_SUBDIR = "packages/shared/src/cli-contract/data"
REAL_DATA = paths.from_root(*DATA_SUBDIR.split("/"))
LANGUAGES_REL = "packages/shared/src/i18n/types.ts"
REAL_TYPES = paths.from_root(*LANGUAGES_REL.split("/"))


def _run(*args: str, root: pathlib.Path | None = None) -> harness.RunResult:
    env = {"PYTHONPATH": str(paths.from_root(".ci"))}
    if root is not None:
        env[paths.ROOT_ENV] = str(root)
    return harness.run([sys.executable, "-m", MODULE, *args], cwd=paths.repo_root(), env=env)


def _copy_root(tmp_path: pathlib.Path) -> pathlib.Path:
    """A root holding a byte-for-byte copy of the real contract data and nothing else."""
    root = tmp_path / "root"
    shutil.copytree(REAL_DATA, root / DATA_SUBDIR)
    types = root / LANGUAGES_REL
    types.parent.mkdir(parents=True)
    shutil.copy(REAL_TYPES, types)
    return root


def _contract(root: pathlib.Path) -> tuple[pathlib.Path, dict]:
    path = root / DATA_SUBDIR / "contract.json"
    return path, json.loads(path.read_text(encoding="utf-8"))


def _require_subject(gate) -> None:
    if not SUT.is_file():
        gate.log_fail("subject under test is missing: %s" % paths.relative_to_root(SUT))
    if not (REAL_DATA / "contract.json").is_file():
        gate.log_fail(
            "the committed contract is missing at %s, so no case below could read anything. "
            "Fix: npm run generate:cli-contract -w @rediacc/cli" % DATA_SUBDIR
        )


def test_gate_green_on_real_tree_with_a_non_trivial_shape(gate):
    gate.log_test("the gate is green on the committed contract and names a non-empty shape")
    _require_subject(gate)
    result = _run()
    gate.assert_exit(0, result, "gate must pass on the committed contract")
    gate.assert_contains(result.combined, "controls first", "controls ran before the verdict")
    gate.assert_contains(result.combined, "control(s) passed", "the controls reported their tally")
    gate.assert_contains(result.combined, "CLI contract coverage OK", "green summary line present")
    _, contract = _contract(paths.repo_root())
    commands = len(contract["commands"])
    gate.assert_contains(
        result.combined,
        "OK: %d commands" % commands,
        "the success line counts every command of the committed contract",
    )
    gate.assert_contains(
        result.combined,
        "%d of %d bundles" % (len(contract["languages"]), len(contract["languages"])),
        "every declared bundle was read",
    )
    if commands < 100:
        gate.log_fail(
            "the committed contract holds only %d commands; the green covers a collapsed corpus"
            % commands
        )
    gate.assertions += 1
    gate.log_pass("green over %d commands" % commands)


def test_selftest_passes(gate):
    gate.log_test("the gate's own controls pass behind --selftest")
    _require_subject(gate)
    result = _run("--selftest")
    gate.assert_exit(0, result, "selftest must pass")
    gate.assert_contains(result.combined, "control(s) passed", "selftest tally present")
    gate.assert_not_contains(result.combined, "FAIL", "no control failed")
    gate.log_pass("selftest green")


def test_unplanted_copy_is_green(gate, tmp_path):
    gate.log_test(
        "CONTROL: an untouched copy of the real contract data is green under the root override"
    )
    _require_subject(gate)
    result = _run(root=_copy_root(tmp_path))
    gate.assert_exit(0, result, "the copy must be green, or every plant below proves nothing")
    gate.log_pass("unplanted copy green")


def _plant_case(gate, tmp_path: pathlib.Path, label: str, mutate, needle: str) -> None:
    gate.log_test("PLANT: %s turns the gate red" % label)
    _require_subject(gate)
    root = _copy_root(tmp_path)
    mutate(root)
    result = _run(root=root)
    gate.assert_exit(1, result, "%s must be a finding" % label)
    gate.assert_contains(result.combined, needle, "the finding names what is wrong")
    gate.assert_contains(
        result.combined, "1 finding(s)", "exactly the planted finding, nothing else"
    )
    gate.log_pass("%s is caught" % label)


def _mutate_command(field_fn):
    def mutate(root: pathlib.Path) -> None:
        path, contract = _contract(root)
        command = next(c for c in contract["commands"] if c["pathKey"] == "repo prune")
        field_fn(command, contract)
        path.write_text(json.dumps(contract), encoding="utf-8")

    return mutate


def test_missing_severity_is_caught(gate, tmp_path):
    _plant_case(
        gate,
        tmp_path,
        "a missing severity",
        _mutate_command(lambda c, _: c.pop("severity")),
        "repo prune: severity is None",
    )


def test_101_character_summary_is_caught(gate, tmp_path):
    _plant_case(
        gate,
        tmp_path,
        "a 101-character summary",
        _mutate_command(lambda c, _: c.__setitem__("summary", "x" * 101)),
        "repo prune: summary is 101 characters",
    )


def test_summary_key_absent_from_one_bundle_is_caught(gate, tmp_path):
    def mutate(root: pathlib.Path) -> None:
        _, contract = _contract(root)
        key = next(c for c in contract["commands"] if c["pathKey"] == "repo prune")["summaryKey"]
        bundle_path = root / DATA_SUBDIR / "i18n" / "tr.json"
        bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
        del bundle[key]
        bundle_path.write_text(json.dumps(bundle), encoding="utf-8")

    _plant_case(
        gate,
        tmp_path,
        "a summary key absent from one bundle",
        mutate,
        "is absent or empty in i18n/tr.json",
    )


def test_error_code_without_origin_is_caught(gate, tmp_path):
    def drop_origin(_command, contract):
        contract["errorCodes"][0].pop("origin")

    _plant_case(
        gate,
        tmp_path,
        "an error code without origin",
        _mutate_command(drop_origin),
        "has origin None",
    )


def test_preview_flag_naming_no_option_is_caught(gate, tmp_path):
    _plant_case(
        gate,
        tmp_path,
        "a preview flag naming no option",
        _mutate_command(lambda c, _: c["preview"].__setitem__("flag", "no-such-flag")),
        "preview flag 'no-such-flag' names no option",
    )


def test_empty_root_cannot_run(gate, tmp_path):
    gate.log_test("an empty root is CANNOT RUN (77), never a pass and never a finding")
    _require_subject(gate)
    empty = tmp_path / "empty"
    empty.mkdir()
    result = _run(root=empty)
    gate.assert_exit(77, result, "nothing to read must exit 77")
    gate.assert_contains(result.combined, "CANNOT RUN", "says it could not run")
    gate.assert_not_contains(result.combined, "coverage OK", "never prints the green line")
    gate.log_pass("empty root exits 77")


def test_zero_commands_cannot_run(gate, tmp_path):
    gate.log_test(
        "a contract naming zero commands is CANNOT RUN (77): every rule would hold vacuously"
    )
    _require_subject(gate)
    root = _copy_root(tmp_path)
    path, contract = _contract(root)
    contract["commands"] = []
    path.write_text(json.dumps(contract), encoding="utf-8")
    result = _run(root=root)
    gate.assert_exit(77, result, "zero commands must exit 77")
    gate.assert_contains(result.combined, "names no command", "names the vacuity")
    gate.log_pass("zero commands exits 77")


def test_unknown_argument_is_refused(gate):
    gate.log_test("a misspelt flag is refused, never ignored")
    result = _run("--selftset")
    gate.assert_exit(2, result, "an unknown argument exits 2")
    gate.assert_contains(result.combined, "unknown argument", "names the refusal")
    gate.log_pass("unknown argument refused")


def test_contract_dropping_a_shipped_language_is_caught(gate, tmp_path):
    """b2ffbf55.1: a contract that drops a language and its bundle still has to name every shipped locale."""
    gate.log_test("a shortened languages list reds against SUPPORTED_LANGUAGES")
    _require_subject(gate)
    root = _copy_root(tmp_path)
    path, contract = _contract(root)
    contract["languages"] = [lang for lang in contract["languages"] if lang != "ko"]
    path.write_text(json.dumps(contract), encoding="utf-8")
    (root / DATA_SUBDIR / "i18n" / "ko.json").unlink()
    result = _run(root=root)
    gate.assert_exit(1, result, "a dropped language must exit 1")
    gate.assert_contains(result.combined, "missing ['ko']", "names the dropped language")
    gate.log_pass("the dropped language is a finding")


def test_unhashable_severity_is_a_finding_not_a_traceback(gate, tmp_path):
    """b2ffbf55.2: a list or object severity must not die in the severity tally."""
    _plant_case(
        gate,
        tmp_path,
        "an unhashable severity",
        _mutate_command(lambda c, _: c.__setitem__("severity", ["none"])),
        "severity is ['none']",
    )


def test_unhashable_preview_flag_is_a_finding_not_a_traceback(gate, tmp_path):
    """b2ffbf55.3: a list or object preview flag must not die in the option lookup."""
    _plant_case(
        gate,
        tmp_path,
        "an unhashable preview flag",
        _mutate_command(lambda c, _: c["preview"].__setitem__("flag", ["dry-run"])),
        "preview flag ['dry-run'] names no option",
    )


def test_non_utf8_types_file_cannot_run(gate, tmp_path):
    """db0d7c52.2: undecodable bytes in the locale source are CANNOT RUN (77), never an uncaught UnicodeDecodeError."""
    gate.log_test("a non-UTF-8 types.ts exits 77")
    _require_subject(gate)
    root = _copy_root(tmp_path)
    (root / LANGUAGES_REL).write_bytes(b"export const SUPPORTED_LANGUAGES = ['en', '\xff\xfe'];\n")
    result = _run(root=root)
    gate.assert_exit(77, result, "an unreadable locale source must exit 77")
    gate.assert_contains(result.combined, "CANNOT RUN", "says it could not run")
    gate.log_pass("non-UTF-8 types.ts exits 77")


def test_tagged_locale_is_one_supported_language(tmp_path):
    """db0d7c52.1: 'zh-CN' and 'pt-BR' stay in the shipped set instead of being dropped by the regex."""
    types = tmp_path / ccc.LANGUAGES_REL
    types.parent.mkdir(parents=True)
    types.write_text(
        "export const SUPPORTED_LANGUAGES = ['en', 'zh-CN', 'pt-BR', 'fil'] as const;\n",
        encoding="utf-8",
    )
    assert ccc.supported_languages(tmp_path) == ["en", "zh-CN", "pt-BR", "fil"]


def test_evaluate_has_no_skip_default_for_the_shipped_locale_set():
    """db0d7c52.3: `supported` is required, so no caller can silently skip the languages check."""
    param = inspect.signature(ccc.evaluate).parameters["supported"]
    assert param.default is inspect.Parameter.empty
