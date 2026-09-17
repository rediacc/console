"""`rediacc_ci.workflows` against PyYAML on the real corpus, and against lanes.ts.

TWO DIFFERENTIALS, because the module replaces two different kinds of parser.

  1. AGAINST PyYAML, over every tracked Actions YAML file in the repository.
     Eight gates parse these files with `yaml.safe_load`, so PyYAML's answer IS
     the contract for them. The comparison is document to document -- not a
     projection, not a sample -- across `.github/workflows/*.yml`,
     `.github/actions/*/action.yml` and `.ci/breakpoint/workflow/*.yml`.

     PyYAML RUNS IN A SUBPROCESS UNDER THE SYSTEM INTERPRETER, and that is not
     stylistic. `.ci/bootstrap.sh` provisions pytest with `uv tool install`,
     which builds an isolated virtual environment: `import yaml` FAILS inside
     this suite while `python3 -c "import yaml"` succeeds on the same machine
     (PyYAML 6.0.3, measured 2026-09-06). A differential that needed the import
     could not run here at all.

  2. AGAINST `scripts/ci-runner/lanes.ts`, the only TypeScript parser of these
     files, through `npx tsx`. That one is run over a COMMITTED FIXTURE rather
     than the live workflows, with lanes.ts's own output committed beside it as a
     golden -- see `data/lanes-fixture.yml` for why: the live files have four
     other writers this session, and a golden over them would go stale on
     somebody else's commit.

WHAT THE lanes.ts DIFFERENTIAL FOUND, and it is a real defect rather than a formatting difference. lanes.ts matches `runs-on` and `timeout-minutes` with regexes anchored `\\s*$` and does not strip trailing comments, so:

    runs-on: ubuntu-latest  # Needs Docker for registry cache check
    timeout-minutes: 5 # CHECK 3: slim jobs must declare <= 14

both parse to NOTHING -- an empty runner and a null timeout. Measured over the live corpus this session: 124 jobs, 8 with a runner lanes.ts cannot see and 3
with a timeout it cannot see. The irony is worth recording: the comment it
chokes on is the CHECK 3 annotation another gate reads.

IT DOES NOT AFFECT PLACEMENT TODAY. `satisfies()` and `placeGate()` read only `submodules`, `node` and `tools`, and on those three plus the job id the two implementations agreed on all 124 live jobs. The divergence is latent, it is reported to the root driver rather than fixed here (lanes.ts is outside this session's write scope), and the fixture pins all three shapes so it cannot
quietly become load-bearing.
"""

import json
import os
import pathlib
import subprocess

import pytest

from rediacc_ci import workflows
from rediacc_ci.tests import differential as diff

DATA = pathlib.Path(__file__).resolve().parent / "data"
FIXTURE = DATA / "lanes-fixture.yml"
GOLDEN = DATA / "lanes-fixture.golden.json"

# The corpus, DERIVED rather than typed. Three prefixes because those are the three that existing gates read: `check_actions_allowlist.py:64` names all of them, and a parser that handled only `.github/workflows` would be a narrower replacement than the thing it replaces.
CORPUS_PATHSPECS = (
    ".github/workflows/*.yml",
    ".github/actions/*/action.yml",
    ".ci/breakpoint/workflow/*.yml",
)

# yaml.safe_load, then normalise PyYAML's booleanised KEYS back to strings. See the module docstring of rediacc_ci.workflows: `on:` becomes the key True there, and `check_secret_reachability.py:151` carries a workaround for exactly that. The normalisation is applied to PyYAML's side only, so the divergence is converted deliberately rather than hidden -- and it is asserted directly
# by `test_pyyaml_turns_the_on_key_into_a_boolean` below.
_PYYAML_SNIPPET = """
import json, sys, yaml

def normalise(node):
    if isinstance(node, dict):
        out = {}
        for key, value in node.items():
            if key is True:
                key = "on"
            elif key is False:
                key = "off"
            out[str(key)] = normalise(value)
        return out
    if isinstance(node, list):
        return [normalise(item) for item in node]
    return node

with open(sys.argv[1], encoding="utf-8") as handle:
    print(json.dumps(normalise(yaml.safe_load(handle)), default=str, sort_keys=True))
"""


def pyyaml_load(path: pathlib.Path):
    """Parse with the real PyYAML, out of process. None when it could not run."""
    result = subprocess.run(
        ["python3", "-c", _PYYAML_SNIPPET, str(path)],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    if result.returncode != 0:
        return None
    return json.loads(result.stdout)


def corpus() -> list[pathlib.Path]:
    """Tracked Actions YAML, from `git ls-files`. Never a hand-written list."""
    root = pathlib.Path(diff.repo())
    result = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z", "--", *CORPUS_PATHSPECS],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    return [root / p for p in result.stdout.split("\0") if p]


def roundtrip(value):
    """Through JSON, so tuples/ints/strings compare the way PyYAML's side does."""
    return json.loads(json.dumps(value, default=str, sort_keys=True))


# --------------------------------------------------------------------------- ANTI-VACUITY: both sides of both differentials must actually be present ---------------------------------------------------------------------------


def test_pyyaml_is_reachable_through_the_system_interpreter():
    """Without it every comparison below has nothing to compare against.

    Also the measurement behind this module's central design decision: PyYAML is available to `python3` and NOT to the interpreter running this suite.
    """
    probe = subprocess.run(
        ["python3", "-c", "import yaml; print(yaml.__version__)"],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert probe.returncode == 0, "PyYAML must be importable by python3: %s" % probe.stderr
    assert probe.stdout.strip().startswith("6.")


def test_the_suites_own_interpreter_cannot_import_yaml():
    """THE REASON THE PARSER HAS NO DEPENDENCY, asserted rather than asserted-in-prose.

    `uv tool install pytest` builds an isolated environment. If this ever starts passing -- because the bootstrap grew `--with PyYAML` -- the constraint has changed and the design decision above deserves re-examining. That is a conversation, not a silent drift, so it is pinned here.
    """
    with pytest.raises(ImportError):
        import yaml  # noqa: F401, PLC0415


def test_the_corpus_is_derived_and_covers_every_tracked_workflow():
    """SET EQUALITY, not a hand-typed count. Section 6 of the driver contract.

    The floor is `every tracked file under the three prefixes`, so a rename re-keys it automatically and a collapsed glob is caught by the set being empty rather than by a number somebody remembered to update.
    """
    files = corpus()
    assert files, "the corpus enumeration returned nothing"

    root = pathlib.Path(diff.repo())
    on_disk = set((root / ".github" / "workflows").glob("*.yml"))
    assert on_disk <= set(files), "a workflow on disk is missing from the enumeration"
    assert all(p.is_file() for p in files)
    # Corpus-derived: every workflow declares at least one job, so the job count cannot honestly be below the file count.
    jobs = sum(len(workflows.load_workflow(p).jobs) for p in files if "workflows/" in str(p))
    assert jobs >= len(on_disk)


# --------------------------------------------------------------------------- Differential 1: PyYAML, whole documents, whole corpus ---------------------------------------------------------------------------


def test_every_tracked_workflow_parses_identically_to_pyyaml():
    """THE ACCEPTANCE FOR THIS MODULE.

    Document to document, every file. Not a projection and not a sample: a projection would let a difference hide in the half nobody compared, and this parser's whole claim is that it can stand in for `yaml.safe_load` for the eight gates that use it.
    """
    mismatched = []
    compared = 0
    for path in corpus():
        expected = pyyaml_load(path)
        assert expected is not None, "PyYAML could not read %s" % path
        if roundtrip(workflows.load(path)) != expected:
            mismatched.append(str(path))
        compared += 1
    assert compared > 0, "nothing was compared"
    assert mismatched == [], "%d file(s) differ from PyYAML: %s" % (
        len(mismatched),
        mismatched,
    )


def test_the_pyyaml_comparison_can_actually_fail():
    """CONTROL. A comparison that cannot fail is the failure this repo names most.

    If `pyyaml_load` silently returned the parser's own answer -- or if `roundtrip` flattened both sides to the same thing -- the case above would be green over any corpus at all. A deliberately wrong document is fed through the same comparison and must be reported as different.
    """
    path = corpus()[0]
    expected = pyyaml_load(path)
    corrupted = dict(expected) if isinstance(expected, dict) else {"x": 1}
    corrupted["a-key-that-is-not-in-any-workflow"] = "planted"
    assert roundtrip(workflows.load(path)) != corrupted


def test_pyyaml_turns_the_on_key_into_a_boolean():
    """THE ONE DELIBERATE DIVERGENCE, measured in both directions.

    PyYAML applies YAML 1.1 resolution to keys, so the `on:` block every workflow opens with arrives as the key `True`. `check_secret_reachability.py:151` carries a workaround; a consumer that forgets it finds no triggers and says nothing. This parser keeps keys as strings.
    """
    raw = subprocess.run(
        [
            "python3",
            "-c",
            (
                "import json,sys,yaml;print(json.dumps([str(k) for k in "
                "yaml.safe_load(open(sys.argv[1],encoding='utf-8'))]))"
            ),
            str(pathlib.Path(diff.repo()) / ".github" / "workflows" / "ci-quality.yml"),
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert raw.returncode == 0
    assert "True" in json.loads(raw.stdout), "PyYAML must still booleanise the key"

    parsed = workflows.load(pathlib.Path(diff.repo()) / ".github" / "workflows" / "ci-quality.yml")
    assert "on" in parsed
    assert True not in parsed
    assert workflows.load_workflow(
        pathlib.Path(diff.repo()) / ".github" / "workflows" / "ci-quality.yml"
    ).triggers


# --------------------------------------------------------------------------- Differential 2: lanes.ts, over a committed fixture with a committed golden ---------------------------------------------------------------------------


def run_lanes_ts(path: pathlib.Path):
    """lanes.ts's own answer for `path`, or None when tsx is not installed.

    None is a real possibility rather than a defensive habit: the CI lane that runs this suite is `quality-static`, which lanes.ts itself reports as `node: false` -- so there is no `node_modules` there and no tsx. The caller below asserts the golden either way and uses the live answer only to prove the golden is not stale.
    """
    script = (
        "import fs from 'node:fs';\n"
        "import { laneCapabilities } from '%s/scripts/ci-runner/lanes.js';\n"
        "console.log(JSON.stringify([...laneCapabilities("
        "fs.readFileSync(process.argv[2], 'utf-8')).values()]));\n" % diff.repo()
    )
    # PID-KEYED: `.ci/cache/` is shared by every session working in this tree, and a fixed name would let two concurrent suites truncate each other's entry point mid-run.
    entry = (
        pathlib.Path(diff.repo()) / ".ci" / "cache" / ("lanes-differential-%d.mts" % os.getpid())
    )
    try:
        entry.parent.mkdir(parents=True, exist_ok=True)
        entry.write_text(script, encoding="utf-8")
        result = subprocess.run(
            ["npx", "--no-install", "tsx", str(entry), str(path)],
            capture_output=True,
            text=True,
            check=False,
            cwd=diff.repo(),
            timeout=180,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    finally:
        entry.unlink(missing_ok=True)
    if result.returncode != 0:
        return None
    for line in reversed(result.stdout.splitlines()):
        if line.startswith("["):
            return json.loads(line)
    return None


def test_lane_capabilities_match_the_lanes_ts_golden_on_every_agreed_field():
    """The four fields `satisfies()` and `placeGate()` actually read.

    Compared for every job in the fixture, which exercises setup-workspace, setup-go, `pip install ruff`, `pip install PyYAML`, `submodules: true`, a targeted `git submodule update --init`, and the suppression of a targeted entry once `*` is present.
    """
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    mine = [c.as_dict() for c in workflows.lane_capabilities(workflows.load_workflow(FIXTURE))]
    assert len(mine) == len(golden) > 5, "the fixture must cover several jobs"
    for got, expected in zip(mine, golden, strict=True):
        for field in ("job", "submodules", "node", "tools"):
            assert got[field] == expected[field], "%s.%s" % (expected["job"], field)


def test_the_golden_is_the_real_lanes_ts_answer_when_tsx_is_installed():
    """PROVES THE GOLDEN IS NOT STALE, and says so honestly when it cannot.

    Not a skip: a skipped test reads exactly like a passing one in the count `check_pytest.py` parses, and that gate refuses a run whose passes and collections disagree. So the branch where tsx is absent asserts the ABSENCE rather than passing blindly -- if tsx is installed and lanes.ts still could not be run, that is a real failure and it is reported as one.
    """
    live = run_lanes_ts(FIXTURE)
    if live is None:
        tsx = pathlib.Path(diff.repo()) / "node_modules" / "tsx"
        assert not tsx.exists(), (
            "tsx IS installed but lanes.ts could not be run; the differential is "
            "broken rather than unavailable"
        )
        return
    assert live == json.loads(GOLDEN.read_text(encoding="utf-8")), (
        "regenerate data/lanes-fixture.golden.json: lanes.ts's answer has changed"
    )


def test_lanes_ts_loses_a_runner_that_carries_a_trailing_comment():
    """DIVERGENCE 1, both directions, from the golden.

    Live measurement over the real corpus this session: 8 of 124 jobs have a runner lanes.ts reports as ''. Two of them are plain `ubuntu-latest` with an explanatory comment (`ci.yml:89` and `:638`); the other six are
    `${{ matrix.os }}`-style expressions, which its single-token `(\\S+)` cannot
    match either.
    """
    golden = {row["job"]: row for row in json.loads(GOLDEN.read_text(encoding="utf-8"))}
    mine = {c.job: c for c in workflows.lane_capabilities(workflows.load_workflow(FIXTURE))}

    assert golden["runner-with-a-trailing-comment"]["runsOn"] == ""
    assert mine["runner-with-a-trailing-comment"].runs_on == "ubuntu-latest"

    assert golden["runner-from-an-expression"]["runsOn"] == ""
    assert mine["runner-from-an-expression"].runs_on == "${{ matrix.os }}"

    assert golden["plain-slim"]["runsOn"] == "ubuntu-slim", "the agreeing case still agrees"
    assert mine["plain-slim"].runs_on == "ubuntu-slim"


def test_lanes_ts_loses_a_timeout_that_carries_a_trailing_comment():
    """DIVERGENCE 2, and the irony is the point.

    The comment it chokes on is `# CHECK 3: slim jobs must declare <= 14`, which
    is the annotation another gate reads. 3 of 124 live jobs are affected.
    """
    golden = {row["job"]: row for row in json.loads(GOLDEN.read_text(encoding="utf-8"))}
    mine = {c.job: c for c in workflows.lane_capabilities(workflows.load_workflow(FIXTURE))}

    assert golden["timeout-with-a-trailing-comment"]["timeoutMinutes"] is None
    assert mine["timeout-with-a-trailing-comment"].timeout_minutes == 8
    assert golden["plain-slim"]["timeoutMinutes"] == 12
    assert mine["plain-slim"].timeout_minutes == 12


def test_a_targeted_submodule_is_suppressed_once_star_is_present():
    """lanes.ts:111-114, reproduced. A job that took every submodule has this one, and listing it again would make an exact-match need look unsatisfiable."""
    mine = {c.job: c for c in workflows.lane_capabilities(workflows.load_workflow(FIXTURE))}
    assert mine["all-submodules"].submodules == ["*"]
    assert mine["targeted-submodule"].submodules == ["private/account", "private/renet"]


def test_satisfies_reproduces_the_lane_placement_rules():
    """lanes.ts:131-139: 'submodules' is any, 'private/x' matches '*' or itself."""
    mine = {c.job: c for c in workflows.lane_capabilities(workflows.load_workflow(FIXTURE))}
    assert mine["all-submodules"].satisfies(["private/renet"]) is True
    assert mine["targeted-submodule"].satisfies(["private/renet"]) is True
    assert mine["targeted-submodule"].satisfies(["private/elite"]) is False
    assert mine["plain-slim"].satisfies(["submodules"]) is False
    assert mine["with-node"].satisfies(["node"]) is True
    assert mine["plain-slim"].satisfies(["node"]) is False
    assert mine["plain-slim"].satisfies(["ruff", "python-yaml"]) is True
    assert mine["with-go"].satisfies(["go"]) is True
    assert mine["with-go"].satisfies(["ruff"]) is False


# --------------------------------------------------------------------------- The parser's own edges, where a differential over this corpus proves nothing ---------------------------------------------------------------------------


def test_yaml_1_1_scalar_resolution_matches_what_the_gates_already_see():
    assert workflows.resolve_scalar("true") is True
    assert workflows.resolve_scalar("yes") is True, "YAML 1.1, which PyYAML applies"
    assert workflows.resolve_scalar("off") is False
    assert workflows.resolve_scalar("~") is None
    assert workflows.resolve_scalar("") is None
    assert workflows.resolve_scalar("0") == 0
    assert workflows.resolve_scalar("-3") == -3
    assert workflows.resolve_scalar("0x1f") == 31
    assert workflows.resolve_scalar("1.5") == 1.5
    assert workflows.resolve_scalar("1e3") == 1000.0
    assert workflows.resolve_scalar("ubuntu-24.04") == "ubuntu-24.04"
    assert workflows.resolve_scalar("v1.2.3") == "v1.2.3"


def test_a_literal_block_scalar_keeps_its_newlines_and_its_indentation():
    doc = workflows.parse("run: |\n  line one\n    indented\n  line three\n")
    assert doc["run"] == "line one\n  indented\nline three\n"


def test_chomping_indicators_do_what_they_say():
    assert workflows.parse("a: |\n  x\n")["a"] == "x\n"
    assert workflows.parse("a: |-\n  x\n")["a"] == "x"
    assert workflows.parse("a: |+\n  x\n\n")["a"] == "x\n\n"


def test_folded_scalars_fold_a_single_break_and_keep_a_blank_line():
    assert workflows.parse("a: >-\n  one\n  two\n")["a"] == "one two"
    assert workflows.parse("a: >-\n  one\n\n  two\n")["a"] == "one\ntwo"


def test_a_more_indented_line_in_a_folded_scalar_keeps_its_break():
    """The rule that took two measurements; see `_fold`'s docstring."""
    assert workflows.parse("a: >-\n  one\n    deeper\n  two\n")["a"] == "one\n  deeper\ntwo"
    assert workflows.parse("a: >-\n  one\n\n    deeper\n")["a"] == "one\n\n  deeper"


def test_a_plain_scalar_continues_onto_more_indented_lines():
    """cd-deploy-account.yml:249-251. Getting this wrong dropped two whole steps."""
    doc = workflows.parse(
        "env:\n  KEY: ${{ inputs.target == 'stable'\n    && env.A\n    || env.B }}\n  NEXT: plain\n"
    )
    assert doc["env"]["KEY"] == "${{ inputs.target == 'stable' && env.A || env.B }}"
    assert doc["env"]["NEXT"] == "plain", "the following key must survive"


def test_a_sequence_of_plain_scalars_is_not_mistaken_for_a_mapping():
    """ct-tests.yml:228. The commonest shape in these files."""
    doc = workflows.parse("needs:\n  - a\n  - b-c\n  - ubuntu-24.04\n")
    assert doc["needs"] == ["a", "b-c", "ubuntu-24.04"]


def test_a_sequence_may_sit_at_its_key_s_own_indent():
    """Legal YAML that a depth-only parser reads as a null value."""
    assert workflows.parse("needs:\n- a\n- b\n")["needs"] == ["a", "b"]


def test_flow_collections_parse_inline():
    doc = workflows.parse("needs: [a, b]\nmatrix: {os: ubuntu, n: 2}\nempty: []\n")
    assert doc["needs"] == ["a", "b"]
    assert doc["matrix"] == {"os": "ubuntu", "n": 2}
    assert doc["empty"] == []


def test_quoted_scalars_keep_their_content_including_colons_and_hashes():
    doc = workflows.parse("a: 'has: a colon'\nb: \"has # a hash\"\nc: \"tab\\there\"\nd: 'it''s'\n")
    assert doc["a"] == "has: a colon"
    assert doc["b"] == "has # a hash"
    assert doc["c"] == "tab\there"
    assert doc["d"] == "it's"


def test_a_comment_needs_a_preceding_space_to_be_a_comment():
    """`image: ghcr.io/x#tag` would lose its fragment to a naive split."""
    doc = workflows.parse("a: value # comment\nb: ghcr.io/x#tag\n")
    assert doc["a"] == "value"
    assert doc["b"] == "ghcr.io/x#tag"


def test_unsupported_constructs_are_refused_by_name_and_line():
    """A parser that guesses at an anchor produces a plausible wrong answer."""
    with pytest.raises(workflows.UnsupportedYAMLError, match="anchors"):
        workflows.parse("a: &anchor\n  b: 1\n")
    with pytest.raises(workflows.UnsupportedYAMLError, match="multiple documents"):
        workflows.parse("a: 1\n---\nb: 2\n")


def test_a_parse_error_names_the_file_as_well_as_the_line(tmp_path):
    """A line number without a filename is useless when 34 files are in a loop."""
    bad = tmp_path / "broken.yml"
    bad.write_text("a: 1\nnot a mapping line\n", encoding="utf-8")
    with pytest.raises(workflows.WorkflowParseError, match=r"broken\.yml"):
        workflows.load(bad)


# --------------------------------------------------------------------------- The projection eight gates write by hand today ---------------------------------------------------------------------------


def test_the_workflow_projection_reaches_jobs_and_steps_in_file_order():
    workflow = workflows.load_workflow(FIXTURE)
    assert workflow.name == "Lanes Fixture"
    assert [job.job_id for job in workflow.jobs][:2] == ["plain-slim", "with-node"]
    assert workflow.job("with-go") is not None
    assert workflow.job("not-a-job") is None
    pairs = list(workflow.steps())
    assert pairs, "the step iterator must yield something"
    assert all(isinstance(step, workflows.Step) for _job, step in pairs)


def test_a_step_exposes_the_four_fields_every_gate_reaches_for():
    workflow = workflows.load_workflow(FIXTURE)
    job = workflow.job("plain-slim")
    assert job.steps[0].uses.startswith("actions/checkout@")
    assert job.steps[0].run == ""
    assert "pip install ruff" in job.steps[1].run
    assert job.steps[1].name == "Install python tools"
    assert workflow.job("with-go").steps[0].with_ == {"go-version": "1.25"}


def test_needs_is_a_list_even_when_the_file_writes_a_single_string():
    """A consumer that forgets iterates the CHARACTERS of the string."""
    one = workflows.Job("j", {"needs": "initialize"})
    many = workflows.Job("j", {"needs": ["a", "b"]})
    none = workflows.Job("j", {})
    assert one.needs == ["initialize"]
    assert many.needs == ["a", "b"]
    assert none.needs == []


def test_a_job_body_that_is_not_a_mapping_does_not_crash_the_projection():
    """A malformed workflow must produce an empty job, not a traceback in a gate."""
    job = workflows.Job("j", None)
    assert job.steps == []
    assert job.needs == []
    assert job.runs_on is None
