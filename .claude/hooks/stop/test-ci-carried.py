#!/usr/bin/env python3
"""Controls for the Stop hook's carried-red verdict (`wl_ci.ci_carry_split`, worklist #e3fca920).

    python3 .claude/hooks/stop/test-ci-carried.py

Auto-discovered by TAILED in .claude/rediacc_hooks/tests/test_hooks_delegates.py (glob over test-*.py under .claude/hooks/stop/), so no table edit is needed to wire this file in.

THE DEFECT. Run 37613276374 on PR #599 failed in exactly one job, Quality / Branch, step `Plan implementation clock`, on exactly one finding, `::finding::P-A1:112304fdab4d`, which `.ci/config/carried-reds.json` carries on purpose. The Stop hook never read that file, so it blocked stop after stop with "CI IS RED ON PR #599 AND NOTHING IS WATCHING IT". The log lines below are that job's own, trimmed.

BOTH DIRECTIONS, and the blind ones on the RED side. Carried-only is an advisory; a mixed job, a job with no finding line (a crash), an unreadable job or log, an absent or corrupt or schema-broken carry file, a `"*"` carry and a derived job with no carried root all stay a blocking red, and the blocking red names WHY it is not carried. Every case runs through the real `ci_trouble` with only its network seams replaced (the rollup, the per-job step lookup, the job and log reads, and git), so the controls are red on a ci_trouble that does not read the carry: measured against the pre-fix wl_ci.py, the carried-only control read `trouble`.
"""

import atexit
import importlib.util
import json
import os
import pathlib
import shutil
import tempfile
import types
from typing import Any

_SCRATCH = tempfile.mkdtemp(prefix="ci-carried-")
atexit.register(shutil.rmtree, _SCRATCH, True)
# job_log caches completed logs under XDG_CACHE_HOME; a fixture job id must never read a real cached log, nor leave one behind.
os.environ["XDG_CACHE_HOME"] = _SCRATCH

import wl_ci as W  # noqa: E402

_CI = pathlib.Path(__file__).resolve().parents[3] / ".ci" / "rediacc_ci"


def _by_file(name):
    """A `.ci/rediacc_ci` module loaded BY FILE, not through a `sys.path` hop (test_canonical_sys_path_hop.py freezes those)."""
    spec = importlib.util.spec_from_file_location(name, _CI / ("%s.py" % name))
    if spec is None or spec.loader is None:
        raise SystemExit("%s: .ci/rediacc_ci/%s.py is missing" % (__file__, name))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


controls = _by_file("controls")
T = controls.Controls("ci-carried", floor=40)
check = T.check

DIAG = W._load_diagnose()
if DIAG is None:
    raise SystemExit("FAIL  ci_diagnose did not load; every control below would be vacuous")

TIP = "f99c173a" + "0" * 32
KEY = "P-A1:112304fdab4d"
GATE = "check:ci-plan-implementation"
REASON = "x" * 90

# ---- the real job's lines (job 112766678846), trimmed --------------------------------------------
PREV_TAIL = (
    "2026-10-07T11:23:20.4084012Z ✓ transitions: 275 box(es) open at 97f3917c0 all survive at HEAD"
)


def step_log(gate, findings, exit_line=True, run=None):
    lines = [
        "2026-10-07T11:22:56.0000000Z ##[group]Run actions/checkout@3d3c42e5",
        PREV_TAIL,
        "2026-10-07T11:23:20.4518569Z ##[group]Run %s" % (run or "npm run %s" % gate),
        "2026-10-07T11:23:20.4519207Z npm run %s" % gate,
        "2026-10-07T11:23:20.4526400Z ##[endgroup]",
        "2026-10-07T11:23:29.7242627Z x plan implementation:",
        "2026-10-07T11:23:29.7244113Z   P-A1 OPEN BOXES: 1 plan(s) on this PR's clock are unfinished",
    ]
    lines += ["2026-10-07T11:23:29.7261726Z ::finding::%s" % k for k in findings]
    lines.append("2026-10-07T11:23:29.7429247Z   INFO: 35 queued plan(s) wait off the clock")
    if exit_line:
        lines.append("2026-10-07T11:23:29.7750600Z ##[error]Process completed with exit code 1.")
    lines += [
        "2026-10-07T11:23:29.7827164Z ##[group]Run npm run check:ci-plan-record",
        "2026-10-07T11:25:20.0000000Z ::finding::P-R9:000000000000",
        "2026-10-07T11:25:21.0000000Z Cleaning up orphan processes",
    ]
    return "\n".join(lines) + "\n"


def job(job_id, name="Quality / Branch", steps=None):
    return {
        "id": job_id,
        "name": name,
        "status": "completed",
        "conclusion": "failure",
        "steps": steps
        if steps is not None
        else [
            {
                "name": "Plan checkbox ledger",
                "conclusion": "success",
                "started_at": "2026-10-07T11:23:16Z",
                "completed_at": "2026-10-07T11:23:20Z",
            },
            {
                "name": "Plan implementation clock",
                "conclusion": "failure",
                "started_at": "2026-10-07T11:23:20Z",
                "completed_at": "2026-10-07T11:23:29Z",
            },
            {
                "name": "Plan records",
                "conclusion": "success",
                "started_at": "2026-10-07T11:23:29Z",
                "completed_at": "2026-10-07T11:25:21Z",
            },
        ],
    }


def carry_doc(entries):
    return json.dumps({"version": 2, "carried": entries})


CARRY_OK = carry_doc([{"gate": GATE, "findings": [KEY], "reason": REASON}])


class Fetch:
    """The tracer's fetcher, answering from tables. A job or log missing from its table is a failed read."""

    def __init__(self, jobs, logs):
        self.jobs, self.logs, self.calls = jobs, logs, 0

    def json(self, path):
        self.calls += 1
        jid = path.rsplit("/", 1)[-1]
        return (self.jobs[jid], "") if jid in self.jobs else (None, "HTTP 502")

    def text(self, path):
        self.calls += 1
        jid = path.split("/")[-2]
        return (self.logs[jid], "") if jid in self.logs else (None, "HTTP 502")


def ctx(name, job_id, conclusion="FAILURE"):
    return {
        "__typename": "CheckRun",
        "name": name,
        "status": "COMPLETED",
        "conclusion": conclusion,
        "databaseId": job_id,
        "detailsUrl": "",
        "checkSuite": {"workflowRun": {"databaseId": 37613276374}},
    }


CASE = [0]


def trouble(contexts, carry_text, jobs, logs, live=False, base=None):
    """The real ci_trouble with its network seams replaced. Returns (state, detail, fetch). A fresh scratch directory per case unless `base` reuses one, so no case reads another's cache."""
    if base is None:
        CASE[0] += 1
        base = pathlib.Path(_SCRATCH) / ("case%d" % CASE[0])
        base.mkdir()
    # ci_diagnose.job_log caches a completed job's log per job id under XDG_CACHE_HOME, so a shared cache would lend one case's log to the next case reusing the id.
    os.environ["XDG_CACHE_HOME"] = str(base / "xdg")
    info: dict[str, Any] = {
        "owner": "rediacc",
        "name": "console",
        "pr": 599,
        "sha": TIP,
        "contexts": list(contexts) + ([ctx("E2E / still", 999, conclusion="")] if live else []),
    }
    if live:
        info["contexts"][-1]["status"] = "IN_PROGRESS"
    fetch = Fetch(jobs, logs)

    def fake_git(_root, *args):
        if args[:1] == ("rev-parse",):
            return TIP
        if args[:1] == ("show",) and args[1] == "%s:%s" % (TIP, W.CARRIED_REL):
            return carry_text or ""
        return ""

    real_diag = DIAG
    fake_diag = types.SimpleNamespace(**vars(real_diag))
    fake_diag.GhFetcher = lambda *_a, **_k: fetch
    saved = (W.ci_rollup, W.ci_steps, W._git, W._load_diagnose)

    def fake_rollup(_root, _ref, allow_branch=False, repo=None):  # noqa: ARG001 -- ci_rollup's signature
        return "ok", info

    def fake_steps(_root, _info, _rows, _cached):
        return None

    W.ci_rollup = fake_rollup
    W.ci_steps = fake_steps
    W._git = fake_git
    W._load_diagnose = lambda: fake_diag
    try:
        state, detail = W.ci_trouble(
            base, base / "wl.md", "deadbeef-test", [], "", ref="pub", owned=True
        )
    finally:
        W.ci_rollup, W.ci_steps, W._git, W._load_diagnose = saved
    detail = detail if isinstance(detail, dict) else {}
    detail["_base"] = base
    return state, detail, fetch


def rows_text(detail):
    return W.ci_rows_text(detail.get("hard") or [], detail.get("info"))


BRANCH = ctx("Quality / Branch", 112766678846)

# ---- 1. CARRIED-ONLY: the PR #599 shape is an advisory, not a block --------------------------------
st, det, _f = trouble(
    [BRANCH], CARRY_OK, {"112766678846": job(112766678846)}, {"112766678846": step_log(GATE, [KEY])}
)
check("carried-only: the PR #599 red is `carried`, not `trouble`", st, "carried")
note = W.ci_carried_note(det) if st == "carried" else ""
check("carried-only: the advisory names the key", KEY in note, True)
check("carried-only: the advisory names the carry file", W.CARRIED_REL in note, True)
check("carried-only: the advisory names the job", "Quality / Branch" in note, True)
check("carried-only: the advisory is ONE line", note.count("\n"), 0)
check("carried-only: the next step's finding is not lent to this step", "P-R9" in note, False)

# CACHED per tip: the second stop on the same tip reads the verdict from the steps cache, with no job or log read.
st2, _d2, f2 = trouble([BRANCH], CARRY_OK, {}, {}, base=det["_base"])
check("carried-only, second stop: still `carried` from the cache", st2, "carried")
check("carried-only, second stop: no job or log read", f2.calls, 0)
# CONTROL for the cache: the same empty tables in a FRESH directory cannot read the job, so the verdict above came from the cache.
st3, _d3, _f3 = trouble([BRANCH], CARRY_OK, {}, {})
check("CONTROL: with no cache and no reads it is `trouble`", st3, "trouble")

# ---- 2. MIXED: one carried key and one uncarried key in the same step stays a block ------------------
st, det, _f = trouble(
    [BRANCH],
    CARRY_OK,
    {"112766678846": job(112766678846)},
    {"112766678846": step_log(GATE, [KEY, "P-A2:deadbeef0000"])},
)
check("mixed keys: stays `trouble`", st, "trouble")
check("mixed keys: the red names the uncarried key", "P-A2:deadbeef0000" in rows_text(det), True)

# MIXED ACROSS JOBS: a carried job beside a real one blocks on the real one only.
st, det, _f = trouble(
    [BRANCH, ctx("Quality / Static", 2)],
    CARRY_OK,
    {"112766678846": job(112766678846), "2": job(2, "Quality / Static")},
    {"112766678846": step_log(GATE, [KEY]), "2": step_log("check:format", ["F-1:abc"])},
)
check("mixed jobs: stays `trouble`", st, "trouble")
check(
    "mixed jobs: only the real job is listed as red",
    [r["name"] for r in det["hard"]],
    ["Quality / Static"],
)
check(
    "mixed jobs: the carried job rides in detail",
    [r["name"] for r in det["carried"]],
    ["Quality / Branch"],
)

# ---- 3. NO FINDING LINE: a crash is a real red -------------------------------------------------------
st, det, _f = trouble(
    [BRANCH], CARRY_OK, {"112766678846": job(112766678846)}, {"112766678846": step_log(GATE, [])}
)
check("no finding line: stays `trouble`", st, "trouble")
check("no finding line: says so", "no ::finding:: line" in rows_text(det), True)

# ---- 4. UNREADABLE: a failed job or log read is NOT carried --------------------------------------------
st, det, _f = trouble([BRANCH], CARRY_OK, {"112766678846": job(112766678846)}, {})
check("unreadable log: stays `trouble`", st, "trouble")
check("unreadable log: names the read", "log read failed" in rows_text(det), True)
st, det, _f = trouble([BRANCH], CARRY_OK, {}, {"112766678846": step_log(GATE, [KEY])})
check("unreadable job: stays `trouble`", st, "trouble")
check("unreadable job: names the read", "job read failed" in rows_text(det), True)
# A step the slicer cannot place (no exit line where the step ends) is unreadable, never the whole log's findings.
st, det, _f = trouble(
    [BRANCH],
    CARRY_OK,
    {"112766678846": job(112766678846)},
    {"112766678846": step_log(GATE, [KEY], exit_line=False)},
)
check("unplaced step: stays `trouble`", st, "trouble")
check("unplaced step: says it could not be placed", "could not be placed" in rows_text(det), True)
# No job id at all (a StatusContext) cannot be read.
status_ctx = {
    "__typename": "StatusContext",
    "context": "ext/status",
    "state": "FAILURE",
    "targetUrl": "u",
}
st, det, _f = trouble([status_ctx], CARRY_OK, {}, {})
check("status context with no job id: stays `trouble`", st, "trouble")

# ---- 5. THE CARRY FILE: absent, corrupt, schema-broken -> a block with the reason named -------------
for label, text, needle in (
    ("absent", "", "absent or empty"),
    ("corrupt", "{not json", "does not parse"),
    ("v1 schema", json.dumps({"version": 1, "carried": []}), "version"),
    (
        "entry without findings",
        json.dumps({"version": 2, "carried": [{"gate": GATE, "reason": REASON}]}),
        "has no `findings`",
    ),
):
    st, det, f = trouble(
        [BRANCH], text, {"112766678846": job(112766678846)}, {"112766678846": step_log(GATE, [KEY])}
    )
    check("carry file %s: stays `trouble`" % label, st, "trouble")
    check("carry file %s: the red names why (%s)" % (label, needle), needle in rows_text(det), True)
    check("carry file %s: no job or log is read" % label, f.calls, 0)

# A carry entry whose reason is under the push guard's bar carries nothing (parse_carried's rule, reused).
st, det, _f = trouble(
    [BRANCH],
    carry_doc([{"gate": GATE, "findings": [KEY], "reason": "short"}]),
    {"112766678846": job(112766678846)},
    {"112766678846": step_log(GATE, [KEY])},
)
check("a short-reason carry carries nothing", st, "trouble")
check(
    "a short-reason carry: the gate is named as not carried",
    "is not carried" in rows_text(det),
    True,
)

# The key carried for ANOTHER gate is not carried for this one.
st, _d, _f = trouble(
    [BRANCH],
    carry_doc([{"gate": "check:ci-pytest", "findings": [KEY], "reason": REASON}]),
    {"112766678846": job(112766678846)},
    {"112766678846": step_log(GATE, [KEY])},
)
check("a key carried under another gate stays `trouble`", st, "trouble")

# "*" cannot be told from the gate's own crash.
st, det, _f = trouble(
    [BRANCH],
    carry_doc([{"gate": GATE, "findings": "*", "reason": "y" * 170}]),
    {"112766678846": job(112766678846)},
    {"112766678846": step_log(GATE, [KEY])},
)
check('a "*" carry stays `trouble`', st, "trouble")
check('a "*" carry: says why', 'carried as "*"' in rows_text(det), True)

# A step that runs no `npm run <gate>` cannot be matched to an entry.
st, det, _f = trouble(
    [BRANCH],
    CARRY_OK,
    {"112766678846": job(112766678846)},
    {"112766678846": step_log(GATE, [KEY], run=".ci/scripts/x.py")},
)
check("a non-npm step stays `trouble`", st, "trouble")
check("a non-npm step: says why", "runs no `npm run <gate>`" in rows_text(det), True)

# ---- 6. DERIVED JOBS: CI Complete rides a carried root, and alone it is real -----------------------------
st, det, _f = trouble(
    [BRANCH, ctx("CI Complete", 3)],
    CARRY_OK,
    {"112766678846": job(112766678846)},
    {"112766678846": step_log(GATE, [KEY])},
)
check("CI Complete beside a carried root: `carried`", st, "carried")
check(
    "CI Complete beside a carried root: no read of CI Complete",
    sorted(r["name"] for r in det["carried"]),
    ["CI Complete", "Quality / Branch"],
)
st, _d, _f = trouble([ctx("CI Complete", 3)], CARRY_OK, {}, {})
check("CI Complete alone: stays `trouble`", st, "trouble")
st, _d, _f = trouble([ctx("Review Complete", 4)], CARRY_OK, {}, {})
check("Review Complete is its own result, never derived", st, "trouble")

# ---- 7. A LIVE RUN: the verdict is given, and says the run is still in progress ------------------------
st, det, _f = trouble(
    [BRANCH],
    CARRY_OK,
    {"112766678846": job(112766678846)},
    {"112766678846": step_log(GATE, [KEY])},
    live=True,
)
check("live run, carried-only: `carried`", st, "carried")
check("live run: the advisory says so", "still in progress" in W.ci_carried_note(det), True)

# ---- 8. THE PURE JUDGE, both directions -----------------------------------------------------------------
carried = {GATE: {KEY}}
v = W.judge_job_carry(DIAG, job(1), step_log(GATE, [KEY]), carried)
check("judge: carried-only", (v["verdict"], v["gate"], v["keys"]), ("carried", GATE, [KEY]))
v = W.judge_job_carry(DIAG, job(1), step_log(GATE, [KEY]), None)
check("judge: no carry read is unreadable", v["verdict"], "unreadable")
v = W.judge_job_carry(DIAG, job(1, steps=[]), step_log(GATE, [KEY]), carried)
check("judge: a failed job with no failed step is real", v["verdict"], "real")
two_failed = job(1)["steps"]
two_failed[2]["conclusion"] = "failure"
v = W.judge_job_carry(DIAG, job(1, steps=two_failed), step_log(GATE, [KEY]), carried)
check(
    "judge: a second failed step that cannot be placed is not carried",
    v["verdict"] != "carried",
    True,
)

T.exit()
