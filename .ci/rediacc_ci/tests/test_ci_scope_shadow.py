"""`rediacc_ci.ci.scope_shadow`, driven against the bytes its bash twin produced.

THE TWIN HAS BEEN DELETED. While both copies existed this file ran `.ci/scripts/ci/scope-shadow.sh` and the port over one fixture apiece and compared the exit code, both streams and the three artifacts the script writes.

Every case now compares against `goldens/scope-shadow/`, which holds the twin's OWN recorded bytes; each golden's provenance header carries the blob sha, so `git cat-file -p <sha>` still yields the program that produced them.

THE LEDGER IS `.ci/shadow/w7p4b-scope-shadow.observations.jsonl`, TWELVE rows over twelve distinct trees, every one EQUIVALENT. The older `w7p6-scope-shadow` file has seven rows and is deliberately not the citation: the w7p4b rows are the ones whose recorded `old.cmd` names this bash path and whose `new.cmd` names the module spec that replaced it.

THREE LAYERS, because this pair has three genuinely different risks, and the deletion changes how two of them are held rather than whether they are.

  1. THE FIVE `node -e` PROGRAMS ARE CARRIED, NOT REWRITTEN, so the only thing
     that can go wrong with them is a transcription drift. The differential
     re-read the twin and compared the five bodies byte for byte; the twin's
     five bodies are now RECORDED in `the-carried-source`, sliced out of it on
     its last day, and the port is compared against that recording instead.
     Nothing about the claim weakens: the bytes are still the twin's.
  2. `greenlight_digest` IS AN AWK PROGRAM turned into Python, and it is still
     driven against the REAL `awk` running the REAL program, which is likewise
     recorded from the twin rather than re-sliced out of a file that is gone.
     A hand-written expectation would only prove the expectation.
  3. THE SCRIPT AS A WHOLE is recorded end to end against a fixture root whose
     four `.cjs` neighbours are config-driven fakes. The real engine,
     greenlight, reconciler and scope-map reach the GitHub API; faking them is
     what makes these branches reachable in a unit test at all, and each fake is
     a real node module the real `require` loads.

WHY FAKE CJS AND NOT THE REAL ONES: `--resolve-baseline` makes up to `limit` `gh run list` plus `gh run download` calls. A case that hit them would be a network case that passes or fails on a token.

ONE RECORDING IS NOT A RUN. `the-carried-source` holds the twin's carried text rather than a subject's output, so its exit code is 0 and its streams are empty by construction; the shape is a requirement of `frozen.assert_corpus`, not a claim. What it carries is the five node programs, the awk program and the handful of literals the port's constants are checked against.

WHAT IS MASKED: the fixture's own absolute path, which appeared identically on both sides anyway, and any forty-character hex sha, because the one case that needs a real git repository mints new commits on every run and their names cannot be recorded.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import typing

import pytest

from rediacc_ci import paths
from rediacc_ci.ci import scope_shadow
from rediacc_ci.tests import frozen

if typing.TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()
SLUG = "scope-shadow"
TWIN = ROOT / ".ci" / "scripts" / "ci" / "scope-shadow.sh"
PORT = ROOT / ".ci" / "rediacc_ci" / "ci" / "scope_shadow.py"

TWIN_REL = ".ci/scripts/ci/scope-shadow.sh"
PORT_REL = ".ci/rediacc_ci/ci/scope_shadow.py"
PORT_FILE = PORT

SURFACES = ["e2e_workers", "renet", "unit"]

CJS_HEAD = """const fs = require("fs");
const CONF = JSON.parse(fs.readFileSync(process.env.FXCONF, "utf8"));
"""

SCOPE_MAP_CJS = (
    CJS_HEAD
    + """
const JOB_SURFACES = {};
for (const k of CONF.surfaces) JOB_SURFACES[k] = { paths: [] };
function buildPlan() {
  const jobs = {};
  for (const k of CONF.surfaces) jobs[k] = { run: true, reason: "forced" };
  return { mode: "full", jobs };
}
module.exports = { JOB_SURFACES, buildPlan };
"""
)

RECONCILER_CJS = (
    CJS_HEAD
    + """
function annotatePlan(plan, conditions) {
  if (CONF.annotate_throws) throw new Error("annotatePlan: fixture refusal");
  plan.conditions = {};
  for (const [k, v] of Object.entries(conditions)) {
    if (v === true || v === false) plan.conditions[k] = v;
  }
}
module.exports = { annotatePlan };
"""
)

ENGINE_CJS = (
    CJS_HEAD
    + """
const { buildPlan } = require("./scope-map.cjs");
function forcedFullPlan(reason) {
  const plan = buildPlan();
  plan.reason = reason;
  return plan;
}
module.exports = { forcedFullPlan };
if (require.main === module) {
  const argv = process.argv.slice(2);
  if (argv.includes("--classify")) {
    const files = fs.readFileSync(argv[argv.indexOf("--files") + 1], "utf8");
    process.stdout.write(JSON.stringify({ mode: "diagnostic",
      raw_lines: files.split("\\n").filter(Boolean).length }, null, 2) + "\\n");
    process.exit(0);
  }
  if (argv.includes("--resolve-baseline")) {
    if (CONF.baseline_crash) {
      process.stderr.write("engine: no baseline could be resolved\\n");
      process.exit(4);
    }
    const jobs = {};
    for (const k of CONF.baseline_keys) {
      jobs[k] = { run: CONF.baseline_run[k] !== false, reason: "scope" };
    }
    process.stdout.write(JSON.stringify({ mode: CONF.baseline_mode, jobs }, null, 2) + "\\n");
    process.exit(0);
  }
  process.exit(0);
}
"""
)

GREENLIGHT_CJS = (
    CJS_HEAD
    + """
if (CONF.pending_crash && !require.main) {
  throw new Error("greenlight: module load failed");
}
const CLOSURES = {};
for (const k of CONF.closures) CLOSURES[k] = { jobs: [] };
module.exports = { CLOSURES };
if (require.main === module) {
  if (CONF.greenlight_crash) { process.stderr.write("greenlight: engine died\\n"); process.exit(9); }
  const argv = process.argv.slice(2);
  const keys = [];
  for (let i = 0; i < argv.length; i++) if (argv[i] === "--key") keys.push(argv[i + 1]);
  process.stderr.write(CONF.trail);
  for (const k of keys) {
    const ev = CONF.grants[k];
    if (ev) {
      process.stdout.write(`run_${k}=false\\n`);
      process.stdout.write(`evidence_${k}=${ev}\\n`);
    }
  }
  process.exit(0);
}
"""
)

# A trail that reaches every arm of the digest: the two skipped header shapes, a closure line, the `run id` header, several trail rows, a VERDICT, the redundant one-liner, a blank line, an UNRECOGNISED `greenlight[...]` line that must both re-key and be echoed, and a keyless line that must survive verbatim.
TRAIL = (
    "greenlight[e2e_workers] jobs=5\n"
    "greenlight[e2e_workers] pins=3\n"
    "greenlight[e2e_workers] closure=abcdef0123456789abcdef files=12\n"
    "   run id   sha        verdict\n"
    "   331001   deadbeef   rule1: candidate skipped\n"
    "   330900   cafebabe   rule2: closure differs\n"
    "greenlight[e2e_workers] VERDICT: no greenlight (walked 2)\n"
    "greenlight[e2e_workers]: no greenlight\n"
    "\n"
    "greenlight[renet] jobs=1\n"
    "greenlight[renet] closure=0123456789abcdef0123 files=4\n"
    "   run id   sha        verdict\n"
    "   331002   00ff00ff   rule3: executed green\n"
    "greenlight[renet] VERDICT: GREENLIT by run 331002\n"
    "greenlight[renet]: GREENLIT by run 331002\n"
    "greenlight[renet] something the digest has never seen\n"
    "a line with no key at all, which must survive verbatim\n"
)


# A trail whose FIRST-SEEN order is reverse-alphabetical, so a planted `sorted()` has something to reorder. The differential's first attempt used a trail that was already sorted and reported a plant that could not fire.
REVERSED_TRAIL = (
    "greenlight[renet] closure=1111111111111111 f=1\n"
    "   run id   sha        verdict\n"
    "   331002   00ff00ff   rule3: executed green\n"
    "greenlight[renet] VERDICT: GREENLIT by run 331002\n"
    "greenlight[e2e_workers] closure=2222222222222222 f=2\n"
    "   331001   deadbeef   rule1: candidate skipped\n"
    "greenlight[e2e_workers] VERDICT: no greenlight (walked 1)\n"
)


def base_conf(**overrides: object) -> dict[str, object]:
    conf: dict[str, object] = {
        "surfaces": SURFACES,
        "closures": SURFACES,
        "baseline_keys": SURFACES,
        "baseline_run": {},
        "baseline_mode": "reduced",
        "baseline_crash": False,
        "annotate_throws": False,
        "greenlight_crash": False,
        "pending_crash": False,
        "grants": {},
        "trail": TRAIL,
    }
    conf.update(overrides)
    return conf


def build_fixture(
    tmp_path: pathlib.Path,
    conf: dict[str, object],
    *,
    port_source: str | None = None,
    twin: bool = False,
) -> pathlib.Path:
    fixture = tmp_path / "fixture"
    (fixture / ".ci" / "scripts" / "ci").mkdir(parents=True, exist_ok=True)
    (fixture / ".ci" / "rediacc_ci" / "ci").mkdir(parents=True, exist_ok=True)
    (fixture / "fx").mkdir(parents=True, exist_ok=True)
    if twin:
        # ONLY WHEN THE TWIN IS THE SUBJECT, which is the one-shot recorder and nothing else. The suite drives the port or a throwaway mutant of it, and the twin is no longer in the tree to copy.
        (fixture / TWIN_REL).write_bytes(TWIN.read_bytes())
        (fixture / TWIN_REL).chmod(0o755)
    if port_source is None:
        (fixture / PORT_REL).write_bytes(PORT.read_bytes())
    else:
        (fixture / PORT_REL).write_text(port_source, encoding="utf-8")
    cjs = fixture / ".ci" / "scripts" / "ci"
    (cjs / "scope-map.cjs").write_text(SCOPE_MAP_CJS, encoding="utf-8")
    (cjs / "skip-plan-reconcile.cjs").write_text(RECONCILER_CJS, encoding="utf-8")
    (cjs / "scope-engine.cjs").write_text(ENGINE_CJS, encoding="utf-8")
    (cjs / "greenlight.cjs").write_text(GREENLIGHT_CJS, encoding="utf-8")
    (fixture / "fx" / "config.json").write_text(json.dumps(conf, indent=2), encoding="utf-8")
    return fixture


def _env(fixture: pathlib.Path, side: str, extra: dict[str, str]) -> dict[str, str]:
    env = {
        "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
        "HOME": os.environ.get("HOME", "/tmp"),
        "LC_ALL": "C",
        "LANG": "C",
        "PYTHONDONTWRITEBYTECODE": "1",
        "FXCONF": str(fixture / "fx" / "config.json"),
        "GITHUB_REPOSITORY": "rediacc/console",
        "GITHUB_RUN_ID": "12345",
        "SCOPE_SHADOW_OUT": str(fixture / "fx" / ("out-" + side)),
        "GITHUB_STEP_SUMMARY": str(fixture / "fx" / ("summary-" + side + ".md")),
        "OUTPUT_FILE": str(fixture / "fx" / ("gh-output-" + side)),
    }
    env.update(extra)
    return env


CALLS_MARKER = "--- artifacts ---\n"

# The one recording that is not a run. See the module docstring.
CARRIED = "the-carried-source"

# name -> (conf overrides, environment). The wiring is the differential's, verbatim.
CASE_KW: dict[str, tuple[dict[str, object], dict[str, str]]] = {
    "reduced-baseline-with-a-greenlight-grant": (
        {"baseline_run": {"unit": False}, "grants": {"renet": "331002"}},
        {"HEAD_SHA": "deadbeefcafe", "FULL_SUITE": "true"},
    ),
    "an-operator-override": ({}, {"HEAD_SHA": "deadbeefcafe", "FORCE_FULL_CI": "true"}),
    "the-full-ci-label": ({}, {"HEAD_SHA": "deadbeefcafe", "FULL_CI_LABEL": "true"}),
    "a-crashed-baseline-engine": ({"baseline_crash": True}, {"HEAD_SHA": "deadbeefcafe"}),
    "a-drifted-key-set": (
        {"baseline_keys": [*SURFACES, "an_eighteenth_surface"]},
        {"HEAD_SHA": "deadbeefcafe"},
    ),
    "a-failed-plan-writer": ({"annotate_throws": True}, {"HEAD_SHA": "deadbeefcafe"}),
    "no-head-sha": ({}, {}),
    "a-dead-pending-query": ({"pending_crash": True}, {"HEAD_SHA": "deadbeefcafe"}),
    "a-reversed-first-seen-trail": (
        {
            "baseline_run": {"unit": False},
            "grants": {"renet": "331002"},
            "trail": REVERSED_TRAIL,
        },
        {"HEAD_SHA": "deadbeefcafe"},
    ),
    "a-reduced-plan-with-one-false-key": (
        {"baseline_run": {"unit": False}},
        {"HEAD_SHA": "deadbeefcafe"},
    ),
    CARRIED: ({}, {}),
}

CASES = tuple(CASE_KW)

# Cases the parametrized comparison does not drive: the carried source is not a run, and the real-git one mints commits whose names no recording can hold.
NOT_A_RUN = (CARRIED,)

SHA_RE = re.compile(r"\b[0-9a-f]{40}\b")


def mask(text: str, fixture: pathlib.Path) -> str:
    return SHA_RE.sub("<sha>", text.replace(str(fixture), "<root>"))


def artifacts(fixture: pathlib.Path, side: str) -> str:
    """The three files the script writes, plus the trace it writes and never reads.

    `greenlight.err` is in the recorded shape because one case turns on it: the pending query dies at module load, the stack trace lands there, and nothing ever reads it. The differential asserted that by opening the file directly; here it is part of the recording, which is the same evidence in the place every other case's evidence already lives.
    """
    out_dir = fixture / "fx" / ("out-" + side)
    pieces = []
    for label, path in (
        ("summary", fixture / "fx" / ("summary-" + side + ".md")),
        ("gh-output", fixture / "fx" / ("gh-output-" + side)),
        ("plan.json", out_dir / "plan.json"),
        ("greenlight.err", out_dir / "greenlight.err"),
    ):
        try:
            body = path.read_text(encoding="utf-8", errors="surrogateescape")
        except OSError:
            body = "(absent)\n"
        pieces.append("=== %s\n%s" % (label, body))
    return "".join(pieces)


def run(
    tmp_path: pathlib.Path,
    name: str,
    *,
    subject_rel: str = PORT_REL,
    port_source: str | None = None,
) -> tuple[int, str, str, str]:
    """One subject, once, over this case's own fixture."""
    conf, envvars = CASE_KW[name]
    fixture = build_fixture(
        tmp_path, base_conf(**conf), port_source=port_source, twin=subject_rel.endswith(".sh")
    )
    side = "old" if subject_rel.endswith(".sh") else "new"
    argv = (
        ["bash", str(fixture / subject_rel)]
        if subject_rel.endswith(".sh")
        else ["python3", str(fixture / subject_rel)]
    )
    proc = subprocess.run(
        argv,
        env=_env(fixture, side, dict(envvars)),
        cwd=str(fixture),
        capture_output=True,
        text=True,
        check=False,
        timeout=180,
    )
    return (
        proc.returncode,
        mask(proc.stdout, fixture),
        mask(proc.stderr, fixture),
        mask(artifacts(fixture, side), fixture),
    )


def render(out: tuple[int, str, str, str]) -> str:
    return "%s%s%s" % (frozen.render(out[0], out[1], out[2]), CALLS_MARKER, out[3])


def recorded(name: str) -> tuple[int, str, str, str]:
    text = frozen.read(SLUG, name)
    exit_line, rest = text.split("\n", 1)
    stdout, rest = rest.split("--- stdout ---\n", 1)[1].split("--- stderr ---\n", 1)
    stderr, arts = rest.split(CALLS_MARKER, 1)
    return int(exit_line.removeprefix("exit: ")), stdout, stderr, arts


def compare(tmp_path: pathlib.Path, name: str) -> tuple[int, str, str, str]:
    want = recorded(name)
    got = run(tmp_path, name)
    for index, field in enumerate(("exit", "stdout", "stderr", "artifacts")):
        assert got[index] == want[index], "%s: %s diverged:\n twin: %r\n port: %r" % (
            name,
            field,
            want[index],
            got[index],
        )
    return got


@pytest.mark.parametrize("name", [c for c in CASES if c not in NOT_A_RUN])
def test_port_matches_the_twins_recorded_output(tmp_path: pathlib.Path, name: str) -> None:
    compare(tmp_path, name)


def test_every_case_has_a_golden_and_no_golden_is_orphaned() -> None:
    """ANTI-VACUITY on the corpus: a case whose golden vanished would pass by never being compared, and a golden nothing reads is a recording of a case that stopped running."""
    frozen.assert_corpus(SLUG, set(CASES))


# --------------------------------------------------------------------------- Layer 1: the five carried node programs ---------------------------------------------------------------------------


def carried_source() -> dict[str, object]:
    """The twin's carried text, as recorded on its last day in the tree."""
    return json.loads(recorded(CARRIED)[3])


def test_the_five_node_programs_are_verbatim() -> None:
    """Both directions: the twin still had five, and each one still matches, to the byte.

    WHAT THE DELETION CHANGED IS THE SOURCE OF THE FIVE, not the comparison. The differential sliced them out of the file on every run; they are now sliced once, into a recording whose provenance header names the blob they came from.
    """
    bodies = carried_source()["node_programs"]
    assert len(bodies) == 5, "the recording carries %d inline programs" % len(bodies)
    carried = [
        scope_shadow.WRITE_PLAN_JS,
        scope_shadow.EMIT_OUTPUTS_JS,
        scope_shadow.PENDING_JS,
        scope_shadow.APPLY_JS,
        scope_shadow.CONDITIONS_JS,
    ]
    for index, (twin_body, port_body) in enumerate(zip(bodies, carried, strict=True)):
        assert port_body == twin_body, "inline node program %d drifted" % (index + 1)


def test_the_numbers_the_twin_argues_for_are_still_the_numbers() -> None:
    """The four literals the port's constants have to render back to, recorded from the twin rather than grepped out of it."""
    literals = carried_source()["literals"]
    assert literals["greenlight_flags"] == "--limit %s --budget %s" % (
        scope_shadow.GREENLIGHT_LIMIT,
        scope_shadow.GREENLIGHT_BUDGET,
    )
    assert (
        literals["scope_timeout"]
        == 'SCOPE_TIMEOUT="${SCOPE_SHADOW_TIMEOUT:-%s}"' % scope_shadow.DEFAULT_SCOPE_TIMEOUT
    )
    assert literals["wide_head"] == "head -c %d" % scope_shadow.WIDE_HEAD_BYTES
    assert literals["narrow_head"] == "head -c %d" % scope_shadow.NARROW_HEAD_BYTES


# --------------------------------------------------------------------------- Layer 2: greenlight_digest against the REAL awk, running the REAL program ---------------------------------------------------------------------------


def _run_awk(program: str, text: str, tmp_path: pathlib.Path) -> str:
    src = tmp_path / "trail.txt"
    src.write_text(text, encoding="utf-8")
    return subprocess.run(
        ["awk", program, str(src)],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    ).stdout


DIGEST_CASES = {
    "the full trail": TRAIL,
    "empty input": "",
    "only unrecognised lines": "hello\nworld\n",
    "a trail row before any key": "   331005   feedface   orphan row\n",
    "closure with no verdict": "greenlight[k] closure=deadbeefdeadbeefdead f=1\n",
    "verdict with no closure": "greenlight[k] VERDICT: something\n",
    "a key containing brackets": "greenlight[a]b] closure=0123456789abcdefx y\n",
    "a short closure hash": "greenlight[k] closure=abc rest\n",
    "the same key twice": (
        "greenlight[k] closure=1111111111111111 a\n"
        "   1 aa row one\n"
        "greenlight[k] closure=2222222222222222 b\n"
        "   2 bb row two\n"
    ),
    "a row whose sha column is empty": "   331006    no sha here\n",
    "blank and whitespace-only lines": "\n   \n\t\n",
    "no trailing newline": "greenlight[k] VERDICT: v",
}


def test_greenlight_digest_matches_real_awk(tmp_path: pathlib.Path) -> None:
    """THE REAL AWK, RUNNING THE REAL PROGRAM, which is now the recorded one.

    The program is the twin's own bytes, so this is still a comparison against the thing being reproduced rather than against a restatement of it.
    """
    program = carried_source()["awk"]
    assert "/^greenlight\\[/" in program, "the recorded awk program is not the digest"
    for label, text in DIGEST_CASES.items():
        expected = _run_awk(program, text, tmp_path)
        assert scope_shadow.greenlight_digest(text) == expected, label


def test_the_digest_corpus_is_not_vacuous(tmp_path: pathlib.Path) -> None:
    """Twelve comparisons of "" against "" would prove nothing, so count them.

    SIX of the twelve cases produce output, MEASURED rather than guessed: the other six are all cases where awk's END block has no key in `order`, which is itself the behaviour under test. The floor is the measured six, and at least one case must produce a real TABLE row rather than only pass-through lines.
    """
    program = carried_source()["awk"]
    produced = [_run_awk(program, text, tmp_path) for text in DIGEST_CASES.values()]
    assert sum(1 for p in produced if p.strip()) == 6, [len(p) for p in produced]
    assert sum(1 for p in produced if "closure=" in p and "walked=" in p) >= 4
    assert any("newest " in p for p in produced)


def test_shallow_report_says_so_when_rev_parse_disagrees_with_the_grafts() -> None:
    assert scope_shadow.shallow_report("true", "0") == (
        "false (empty graft list; rev-parse says true)"
    )
    assert scope_shadow.shallow_report("true", "3") == "true"
    assert scope_shadow.shallow_report("false", "0") == "false"
    assert scope_shadow.shallow_report("unknown", "0") == "unknown"
    assert (
        carried_source()["literals"]["shallow_report"]
        == "false (empty graft list; rev-parse says true)"
    )


# --------------------------------------------------------------------------- Layer 3: what the recordings say ---------------------------------------------------------------------------


def test_reduced_baseline_with_a_greenlight_grant() -> None:
    code, stdout, _stderr, arts = recorded("reduced-baseline-with-a-greenlight-grant")
    assert code == 0
    assert "run_renet=false" in arts
    assert "scope_mode=reduced" in arts
    assert "**greenlit, and the plan now says so**: `renet=331002`" in stdout


def test_operator_override_writes_a_forced_plan_and_never_runs_the_engine() -> None:
    code, stdout, _stderr, arts = recorded("an-operator-override")
    assert code == 0
    assert "**OPERATOR OVERRIDE: full CI forced** by the FULL_CI repository variable." in stdout
    assert "--resolve-baseline" not in stdout
    assert "scope_mode=full" in arts


def test_the_full_ci_label_names_itself_rather_than_the_variable() -> None:
    assert "by the full-ci PR label." in recorded("the-full-ci-label")[1]


def test_a_crashed_baseline_engine_produces_no_plan_and_no_outputs() -> None:
    _code, stdout, _stderr, arts = recorded("a-crashed-baseline-engine")
    assert "_no baseline plan was produced, so no run_* output was written: full round._" in stdout
    assert "engine: no baseline could be resolved" in stdout, "the engine stderr is surfaced"
    assert "=== gh-output\n(absent)\n=== plan.json\n(absent)\n" in arts, (
        "$GITHUB_OUTPUT was never even created, so no job can read a false line"
    )


def test_a_drifted_key_set_refuses_to_emit_any_output() -> None:
    """The drift detector: an 18th surface the workflow's inputs do not describe makes the whole round full."""
    _code, stdout, _stderr, arts = recorded("a-drifted-key-set")
    assert "_**the output emitter FAILED**" in stdout
    assert "plan key set drifted from scope-map" in stdout
    assert "run_" not in arts.split("=== gh-output")[1].split("=== plan.json")[0]


def test_a_failed_plan_writer_says_gap_in_the_evidence() -> None:
    stdout = recorded("a-failed-plan-writer")[1]
    assert "_**the plan writer FAILED**" in stdout
    assert "annotatePlan: fixture refusal" in stdout


def test_no_head_sha_skips_both_engine_calls() -> None:
    stdout = recorded("no-head-sha")[1]
    assert "_skipped --classify: no base/head pair resolved_" in stdout
    assert "_skipped --resolve-baseline: no head sha resolved, so this round is full_" in stdout


def test_defect_1_a_dead_pending_query_is_reported_as_nothing_to_ask() -> None:
    """Reproduced rather than fixed.

    The pending query throws at module load. `pending=""` and the next line prints `nothing to ask (every eligible key is already planned to skip)`, which is FALSE: nothing was asked because node died. The stack trace is captured into `greenlight.err` and then never read by anything, so the failure is invisible in the job log and in the step summary alike.

    Fixing this changes what a live `ci.yml:348` step prints, so it is pinned here instead, and the unread trace is part of the recording.
    """
    _code, stdout, stderr, arts = recorded("a-dead-pending-query")
    assert "_greenlight: nothing to ask (every eligible key is already planned to skip)._" in stdout
    assert "module load failed" not in stdout, "the crash is invisible, which is the defect"
    assert "module load failed" not in stderr
    assert "greenlight: module load failed" in arts.split("=== greenlight.err")[1], (
        "the evidence exists and is unread"
    )


def test_defect_2_an_empty_engine_output_renders_empty_not_no_output() -> None:
    """`|| emit "(no output)"` is DEAD, and this measures it.

    The shell created `scope-baseline.json` with the redirection before node ran, so `head` on the resulting empty file exits 0 and the `||` arm cannot fire. A crashed engine therefore renders as an EMPTY fenced block.
    """
    stdout = recorded("a-crashed-baseline-engine")[1]
    assert "(no output)" not in stdout
    assert "```json\n```" in stdout, "the crashed engine rendered as an empty fence"


# --------------------------------------------------------------------------- The real-git branch, live rather than frozen ---------------------------------------------------------------------------


def test_the_classify_branch_over_a_real_git_merge(tmp_path: pathlib.Path) -> None:
    """The only case that needs a real repository: `MERGE_SHA^1` and `^2`.

    NOT FROZEN, and the reason is in the fixture rather than in the subject: every run mints new commits, so the merge sha, the base sha and the head sha are new bytes each time. Masking them would hide the one number this case exists for, `raw_lines`, if it ever moved for a sha-shaped reason.

    It survives as a live run against the port, asserting the shape the differential asserted.
    """
    conf, _envvars = CASE_KW["no-head-sha"]
    fixture = build_fixture(tmp_path, base_conf(**conf))

    def git(*args: str) -> str:
        return subprocess.run(
            ["git", "-C", str(fixture), *args],
            capture_output=True,
            text=True,
            check=True,
            timeout=60,
        ).stdout.strip()

    subprocess.run(["git", "-C", str(fixture), "init", "-b", "main", "-q"], check=True, timeout=60)
    git("config", "user.email", "fixture@example.invalid")
    git("config", "user.name", "fixture")
    (fixture / "a.txt").write_text("a\n", encoding="utf-8")
    git("add", "-A")
    git("commit", "-q", "-m", "base")
    git("checkout", "-q", "-b", "feature")
    (fixture / "b.txt").write_text("b\n", encoding="utf-8")
    git("add", "-A")
    git("commit", "-q", "-m", "feature")
    git("checkout", "-q", "main")
    (fixture / "c.txt").write_text("c\n", encoding="utf-8")
    git("add", "-A")
    git("commit", "-q", "-m", "mainline")
    git("merge", "-q", "--no-ff", "-m", "merge", "feature")
    merge_sha = git("rev-parse", "HEAD")

    proc = subprocess.run(
        ["python3", str(fixture / PORT_REL)],
        env=_env(fixture, "new", {"MERGE_SHA": merge_sha}),
        cwd=str(fixture),
        capture_output=True,
        text=True,
        check=False,
        timeout=180,
    )
    stdout = mask(proc.stdout, fixture)
    assert "**--classify over the merge-base delta**" in stdout
    assert '"raw_lines": 2' in stdout, stdout
    assert "shallow: `false`, grafts: `0`" in stdout


# --------------------------------------------------------------------------- The controls: these goldens can actually fail ---------------------------------------------------------------------------


def test_a_planted_sort_in_the_digest_is_caught(tmp_path: pathlib.Path) -> None:
    """Plant the tidiest-looking wrong change there is: sort the digest's keys.

    awk emits them in FIRST-SEEN order, which for greenlight is cost-descending, and a reader uses that order to see which keys the budget reached. Sorting looks like an improvement and destroys the signal. If this ever passes, the layer-3 comparison has stopped comparing anything.

    THE CASE IT RUNS IS A RECORDED ONE whose trail is deliberately reverse-alphabetical in first-seen order.

    The differential's first version sorted a list that was already sorted and reported a plant that could not fail.

    The trail in that case is part of the control rather than scenery.
    """
    before = PORT_FILE.read_bytes()
    source = PORT_FILE.read_text(encoding="utf-8")
    anchor = "    for k in order:\n"
    assert source.count(anchor) == 1
    planted = source.replace(anchor, "    for k in sorted(order):\n", 1)

    name = "a-reversed-first-seen-trail"
    want = recorded(name)
    got = run(tmp_path / "planted", name, port_source=planted)
    assert got[0] == want[0] == 0
    assert got[1] != want[1], "the plant did not fire; this control proves nothing"
    compare(tmp_path / "good", name)
    assert PORT_FILE.read_bytes() == before, "the real port file moved"


def test_a_planted_true_line_in_the_output_emitter_is_caught(tmp_path: pathlib.Path) -> None:
    """The fail-open contract, planted against: emit `run_<key>=true`.

    The twin's header said the script NEVER writes a `=true` line, and that asymmetry IS the fail-open. The emitter is a carried node program, so the plant goes into the carried text, which is exactly the drift layer 1 guards, driven here as a behaviour change rather than a string compare.
    """
    before = PORT_FILE.read_bytes()
    source = PORT_FILE.read_text(encoding="utf-8")
    anchor = "if (jobs[key] && jobs[key].run === false) lines.push(`run_${key}=false`);"
    assert source.count(anchor) == 1
    planted = source.replace(
        anchor,
        'lines.push(`run_${key}=${jobs[key] && jobs[key].run === false ? "false" : "true"}`);',
        1,
    )

    name = "a-reduced-plan-with-one-false-key"
    want = recorded(name)
    got = run(tmp_path / "planted", name, port_source=planted)
    assert "=true" not in want[3]
    assert "=true" in got[3], "the plant did not fire; this control proves nothing"
    compare(tmp_path / "good", name)
    assert PORT_FILE.read_bytes() == before, "the real port file moved"
