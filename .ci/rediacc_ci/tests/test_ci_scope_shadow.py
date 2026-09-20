"""Differential: `rediacc_ci.ci.scope_shadow` against its twin `.ci/scripts/ci/scope-shadow.sh`.

THREE LAYERS, because this pair has three genuinely different risks.

  1. THE FIVE `node -e` PROGRAMS ARE CARRIED, NOT REWRITTEN, so the only thing
     that can go wrong with them is a transcription drift. One test re-reads the
     twin and compares the five bodies byte for byte, in both directions.
  2. `greenlight_digest` IS AN AWK PROGRAM turned into Python, which is the one
     place real logic changed language. It is driven against the REAL `awk`,
     running the REAL program sliced out of the twin, over adversarial inputs --
     not against a hand-written expectation, which would only prove the
     expectation.
  3. THE SCRIPT AS A WHOLE is run end to end against a fixture root whose four
     `.cjs` neighbours are config-driven fakes. The real engine, greenlight,
     reconciler and scope-map reach the GitHub API; faking them is what makes
     the seven branches below reachable in a unit test at all, and each fake is
     a real node module the real `require` loads.

WHY FAKE CJS AND NOT THE REAL ONES: `--resolve-baseline` makes up to `limit` `gh run list` plus `gh run download` calls. A test that hit them would be a network test that passes or fails on a token.

NOTHING IS NORMALIZED except the fixture's own absolute path, which appears identically on both sides anyway and is folded so a failure diff is readable.

K=7 LEDGER: `.ci/shadow/w7p6-scope-shadow.observations.jsonl` (7 rows, 7
distinct trees, 7 distinct finding sets; K=5 required).
"""

from __future__ import annotations

import json
import os
import subprocess
import typing

from rediacc_ci import paths
from rediacc_ci.ci import scope_shadow

if typing.TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()
TWIN = ROOT / ".ci" / "scripts" / "ci" / "scope-shadow.sh"
PORT = ROOT / ".ci" / "rediacc_ci" / "ci" / "scope_shadow.py"

TWIN_REL = ".ci/scripts/ci/scope-shadow.sh"
PORT_REL = ".ci/rediacc_ci/ci/scope_shadow.py"

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
    tmp_path: pathlib.Path, conf: dict[str, object], *, port_source: str | None = None
) -> pathlib.Path:
    fixture = tmp_path / "fixture"
    (fixture / ".ci" / "scripts" / "ci").mkdir(parents=True, exist_ok=True)
    (fixture / ".ci" / "rediacc_ci" / "ci").mkdir(parents=True, exist_ok=True)
    (fixture / "fx").mkdir(parents=True, exist_ok=True)
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


def _artifacts(fixture: pathlib.Path, side: str) -> str:
    out_dir = fixture / "fx" / ("out-" + side)
    pieces = []
    for label, path in (
        ("summary", fixture / "fx" / ("summary-" + side + ".md")),
        ("gh-output", fixture / "fx" / ("gh-output-" + side)),
        ("plan.json", out_dir / "plan.json"),
    ):
        try:
            body = path.read_text(encoding="utf-8", errors="surrogateescape")
        except OSError:
            body = "(absent)\n"
        pieces.append("=== %s\n%s" % (label, body))
    return "".join(pieces)


def run_both(
    fixture: pathlib.Path, **envvars: str
) -> tuple[tuple[int, str, str, str], tuple[int, str, str, str]]:
    """Both sides, each with its OWN out dir, summary and $GITHUB_OUTPUT.

    Separate artifact paths rather than a reset between runs: this script APPENDS to `$GITHUB_OUTPUT` and to the summary, so a shared path would let the twin's run leak into the port's comparison as extra agreeing lines.
    """
    results = []
    for side, argv in (
        ("old", ["bash", str(fixture / TWIN_REL)]),
        ("new", ["python3", str(fixture / PORT_REL)]),
    ):
        proc = subprocess.run(
            argv,
            env=_env(fixture, side, envvars),
            cwd=str(fixture),
            capture_output=True,
            text=True,
            check=False,
            timeout=180,
        )
        results.append(
            (
                proc.returncode,
                proc.stdout.replace(str(fixture), "<root>"),
                proc.stderr.replace(str(fixture), "<root>"),
                _artifacts(fixture, side).replace(str(fixture), "<root>"),
            )
        )
    return results[0], results[1]


def assert_same(old: tuple[int, str, str, str], new: tuple[int, str, str, str]) -> None:
    assert new[0] == old[0], "exit: twin %s, port %s" % (old[0], new[0])
    assert new[1] == old[1], "stdout"
    assert new[2] == old[2], "stderr"
    assert new[3] == old[3], "artifacts"


# --------------------------------------------------------------------------- Layer 1: the five carried node programs ---------------------------------------------------------------------------


def _twin_node_bodies() -> list[str]:
    """Each `node -e '...'` payload, INCLUDING the newline that closes it.

    The `+ "\\n"` is not cosmetic and it is not a guess. A single-quoted shell word runs to the closing quote, so the byte before it belongs to the program: bash hands node `\\nconst fs = ...;\\n`, opening AND closing with a newline. Splitting on `"\\n'"` consumes the closing one, and a port built against this helper was therefore one byte short in all five payloads -- inert
    to node, and a divergence in the recorded argv the moment anything logs it.

    Found on 2026-09-20 while recording `w7p4b-scope-shadow` behind a pass-through `node` stub: the twin's call log split the payload's last line from the trailing arguments and the port's did not, on ten of twelve scenarios. Repaired in the port rather than normalised away in the ledger.
    """
    text = TWIN.read_text(encoding="utf-8")
    return [chunk.split("\n'")[0] + "\n" for chunk in text.split("node -e '")[1:]]


def test_the_five_node_programs_are_verbatim() -> None:
    """Both directions: the twin still has five, and each one still matches, to the byte."""
    bodies = _twin_node_bodies()
    assert len(bodies) == 5, "the twin now passes %d inline programs to node" % len(bodies)
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
    text = TWIN.read_text(encoding="utf-8")
    assert (
        "--limit %s --budget %s"
        % (
            scope_shadow.GREENLIGHT_LIMIT,
            scope_shadow.GREENLIGHT_BUDGET,
        )
        in text
    )
    assert (
        'SCOPE_TIMEOUT="${SCOPE_SHADOW_TIMEOUT:-%s}"' % scope_shadow.DEFAULT_SCOPE_TIMEOUT in text
    )
    assert "head -c %d" % scope_shadow.WIDE_HEAD_BYTES in text
    assert "head -c %d" % scope_shadow.NARROW_HEAD_BYTES in text


# --------------------------------------------------------------------------- Layer 2: greenlight_digest against the REAL awk, running the REAL program ---------------------------------------------------------------------------


def _twin_awk_program() -> str:
    """The awk source, sliced out of `greenlight_digest` in the twin."""
    text = TWIN.read_text(encoding="utf-8")
    body = text[text.index("greenlight_digest() {") :]
    start = body.index("awk '") + len("awk '")
    end = body.index('\n    \' "$1"')
    program = body[start:end]
    assert "/^greenlight\\[/" in program, "the awk program moved; this slice is stale"
    return program


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
    program = _twin_awk_program()
    for label, text in DIGEST_CASES.items():
        expected = _run_awk(program, text, tmp_path)
        assert scope_shadow.greenlight_digest(text) == expected, label


def test_the_digest_corpus_is_not_vacuous(tmp_path: pathlib.Path) -> None:
    """Twelve comparisons of "" against "" would prove nothing, so count them.

    SIX of the twelve cases produce output, MEASURED rather than guessed: the other six (empty input, an orphan trail row, a verdict with no closure, a row with no sha column, whitespace-only lines, and a final line with no newline) are all cases where awk's END block has no key in `order`, which is itself the behaviour under test. The floor is the measured six, and at least one
    case must produce a real TABLE row rather than only pass-through lines.
    """
    program = _twin_awk_program()
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
    assert "false (empty graft list; rev-parse says true)" in TWIN.read_text(encoding="utf-8")


# --------------------------------------------------------------------------- Layer 3: the whole script, seven branches ---------------------------------------------------------------------------


def test_reduced_baseline_with_a_greenlight_grant(tmp_path: pathlib.Path) -> None:
    fixture = build_fixture(
        tmp_path,
        base_conf(baseline_run={"unit": False}, grants={"renet": "331002"}),
    )
    old, new = run_both(fixture, HEAD_SHA="deadbeefcafe", FULL_SUITE="true")
    assert old[0] == 0
    assert "run_renet=false" in old[3]
    assert "scope_mode=reduced" in old[3]
    assert "**greenlit, and the plan now says so**: `renet=331002`" in old[1]
    assert_same(old, new)


def test_operator_override_writes_a_forced_plan_and_never_runs_the_engine(
    tmp_path: pathlib.Path,
) -> None:
    fixture = build_fixture(tmp_path, base_conf())
    old, new = run_both(fixture, HEAD_SHA="deadbeefcafe", FORCE_FULL_CI="true")
    assert old[0] == 0
    assert "**OPERATOR OVERRIDE: full CI forced** by the FULL_CI repository variable." in old[1]
    assert "--resolve-baseline" not in old[1]
    assert "scope_mode=full" in old[3]
    assert_same(old, new)


def test_the_full_ci_label_names_itself_rather_than_the_variable(
    tmp_path: pathlib.Path,
) -> None:
    fixture = build_fixture(tmp_path, base_conf())
    old, new = run_both(fixture, HEAD_SHA="deadbeefcafe", FULL_CI_LABEL="true")
    assert "by the full-ci PR label." in old[1]
    assert_same(old, new)


def test_a_crashed_baseline_engine_produces_no_plan_and_no_outputs(
    tmp_path: pathlib.Path,
) -> None:
    fixture = build_fixture(tmp_path, base_conf(baseline_crash=True))
    old, new = run_both(fixture, HEAD_SHA="deadbeefcafe")
    assert "_no baseline plan was produced, so no run_* output was written: full round._" in old[1]
    assert "engine: no baseline could be resolved" in old[1], "the engine stderr is surfaced"
    assert "=== gh-output\n(absent)\n=== plan.json\n(absent)\n" in old[3], (
        "$GITHUB_OUTPUT was never even created, so no job can read a false line"
    )
    assert_same(old, new)


def test_a_drifted_key_set_refuses_to_emit_any_output(tmp_path: pathlib.Path) -> None:
    """The drift detector at `scope-shadow.sh:247-249`: an 18th surface the workflow's inputs do not describe makes the whole round full."""
    fixture = build_fixture(tmp_path, base_conf(baseline_keys=[*SURFACES, "an_eighteenth_surface"]))
    old, new = run_both(fixture, HEAD_SHA="deadbeefcafe")
    assert "_**the output emitter FAILED**" in old[1]
    assert "plan key set drifted from scope-map" in old[1]
    assert "run_" not in old[3].split("=== gh-output")[1].split("=== plan.json")[0]
    assert_same(old, new)


def test_a_failed_plan_writer_says_gap_in_the_evidence(tmp_path: pathlib.Path) -> None:
    fixture = build_fixture(tmp_path, base_conf(annotate_throws=True))
    old, new = run_both(fixture, HEAD_SHA="deadbeefcafe")
    assert "_**the plan writer FAILED**" in old[1]
    assert "annotatePlan: fixture refusal" in old[1]
    assert_same(old, new)


def test_no_head_sha_skips_both_engine_calls(tmp_path: pathlib.Path) -> None:
    fixture = build_fixture(tmp_path, base_conf())
    old, new = run_both(fixture)
    assert "_skipped --classify: no base/head pair resolved_" in old[1]
    assert "_skipped --resolve-baseline: no head sha resolved, so this round is full_" in old[1]
    assert_same(old, new)


def test_defect_1_a_dead_pending_query_is_reported_as_nothing_to_ask(
    tmp_path: pathlib.Path,
) -> None:
    """`scope-shadow.sh:394-406`, reproduced rather than fixed.

    The pending query throws at module load. `pending=""` and the next line
    prints `nothing to ask (every eligible key is already planned to skip)`, which is FALSE -- nothing was asked because node died. The stack trace is captured into `greenlight.err` and then never read by anything, so the failure is invisible in the job log and in the step summary alike.

    Fixing this changes what a live `ci.yml:348` step prints, so it is pinned here instead: both sides must tell the same lie.
    """
    fixture = build_fixture(tmp_path, base_conf(pending_crash=True))
    old, new = run_both(fixture, HEAD_SHA="deadbeefcafe")
    assert "_greenlight: nothing to ask (every eligible key is already planned to skip)._" in old[1]
    assert "module load failed" not in old[1], "the crash is invisible, which is the defect"
    assert "module load failed" not in old[2]
    trace = (fixture / "fx" / "out-old" / "greenlight.err").read_text(encoding="utf-8")
    assert "greenlight: module load failed" in trace, "the evidence exists and is unread"
    assert_same(old, new)


def test_defect_2_an_empty_engine_output_renders_empty_not_no_output(
    tmp_path: pathlib.Path,
) -> None:
    """`|| emit "(no output)"` at `:522`/`:538` is DEAD, and this measures it.

    The shell creates `scope-baseline.json` with the redirection before node runs, so `head` on the resulting empty file exits 0 and the `||` arm cannot fire. A crashed engine therefore renders as an EMPTY fenced block. Both sides must produce that same misleading emptiness.
    """
    fixture = build_fixture(tmp_path, base_conf(baseline_crash=True))
    old, new = run_both(fixture, HEAD_SHA="deadbeefcafe")
    assert "(no output)" not in old[1]
    assert "```json\n```" in old[1], "the crashed engine rendered as an empty fence"
    assert_same(old, new)


def test_the_classify_branch_over_a_real_git_merge(tmp_path: pathlib.Path) -> None:
    """The only case that needs a real repository: `MERGE_SHA^1` and `^2`.

    `git diff-tree -r --raw --no-commit-id "$base" "$head"` is a real command over real commits, and `--classify` counts the lines it produced.
    """
    fixture = build_fixture(tmp_path, base_conf())

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

    old, new = run_both(fixture, MERGE_SHA=merge_sha)
    assert "**--classify over the merge-base delta**" in old[1]
    assert '"raw_lines": 2' in old[1], old[1]
    assert "shallow: `false`, grafts: `0`" in old[1]
    assert_same(old, new)


# --------------------------------------------------------------------------- A PLANTED DEFECT, on a throwaway copy, never on the file on disk ---------------------------------------------------------------------------


def test_a_planted_sort_in_the_digest_is_caught(tmp_path: pathlib.Path) -> None:
    """Plant the tidiest-looking wrong change there is: sort the digest's keys.

    awk emits them in FIRST-SEEN order, which for greenlight is cost-descending (`greenlight.cjs:81-85`), and a reader uses that order to see which keys the budget reached. Sorting looks like an improvement and destroys the signal. If this ever passes, the layer-3 comparison has stopped comparing anything.

    The real file is hashed before and after; the mutation lives in the fixture copy only.
    """
    before = PORT.read_bytes()
    source = PORT.read_text(encoding="utf-8")
    anchor = "    for k in order:\n"
    assert source.count(anchor) == 1
    planted = source.replace(anchor, "    for k in sorted(order):\n", 1)
    # THE CONTROL HAD TO BE FIXED BEFORE THE PLANT COULD FIRE. `TRAIL`'s first-seen order is e2e_workers then renet, which is ALSO alphabetical, so the first version of this test sorted a list that was already sorted and reported a plant that could not fail. This trail is deliberately reverse-alphabetical in first-seen order.
    reversed_trail = (
        "greenlight[renet] closure=1111111111111111 f=1\n"
        "   run id   sha        verdict\n"
        "   331002   00ff00ff   rule3: executed green\n"
        "greenlight[renet] VERDICT: GREENLIT by run 331002\n"
        "greenlight[e2e_workers] closure=2222222222222222 f=2\n"
        "   331001   deadbeef   rule1: candidate skipped\n"
        "greenlight[e2e_workers] VERDICT: no greenlight (walked 1)\n"
    )
    fixture = build_fixture(
        tmp_path,
        base_conf(baseline_run={"unit": False}, grants={"renet": "331002"}, trail=reversed_trail),
        port_source=planted,
    )
    old, new = run_both(fixture, HEAD_SHA="deadbeefcafe")
    assert old[0] == 0
    assert old[1] != new[1], "the plant did not fire; this control proves nothing"
    assert PORT.read_bytes() == before, "the real port file moved"


def test_a_planted_true_line_in_the_output_emitter_is_caught(
    tmp_path: pathlib.Path,
) -> None:
    """The fail-open contract, planted against: emit `run_<key>=true`.

    `scope-shadow.sh:9-20` says the script NEVER writes a `=true` line, and that
    asymmetry IS the fail-open. The emitter is a carried node program, so the plant goes into the carried text -- which is exactly the drift `test_the_five_node_programs_are_verbatim` guards, driven here as a behaviour change rather than a string compare.
    """
    before = PORT.read_bytes()
    source = PORT.read_text(encoding="utf-8")
    anchor = "if (jobs[key] && jobs[key].run === false) lines.push(`run_${key}=false`);"
    assert source.count(anchor) == 1
    planted = source.replace(
        anchor,
        'lines.push(`run_${key}=${jobs[key] && jobs[key].run === false ? "false" : "true"}`);',
        1,
    )
    fixture = build_fixture(tmp_path, base_conf(baseline_run={"unit": False}), port_source=planted)
    old, new = run_both(fixture, HEAD_SHA="deadbeefcafe")
    assert "=true" not in old[3]
    assert "=true" in new[3], "the plant did not fire; this control proves nothing"
    assert old[3] != new[3]
    assert PORT.read_bytes() == before, "the real port file moved"
