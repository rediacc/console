#!/usr/bin/env python3
"""Controls for the Stop hook's per-job verdict across run attempts (`wl_ci.latest_per_job`, the ci_trouble cache TTL).

    python3 .claude/hooks/stop/test-ci-rerun.py

Auto-discovered by TAILED in test_hooks_delegates.py (glob over test-*.py here).

THE DEFECT. PR #599, run 37633980671: attempt 1 failed Quality / Submodule Branches (job 112836644226); attempt 2 re-ran it green (job 112840910316). The Stop hook kept saying "CI IS RED ... Submodule Branches FAILURE ... attempt 1". A job's verdict is the LATEST attempt that ran it; a job the later attempt did not re-run keeps its earlier conclusion.

Two seams: the classifier must not count a superseded attempt even when the rollup hands both over, and a final cache that holds a red must not outlive a rerun for the long final TTL. The fixture is the recorded two-attempt shape of that run.
"""

import atexit
import importlib.util
import os
import pathlib
import shutil
import tempfile
import time

_SCRATCH = tempfile.mkdtemp(prefix="ci-rerun-")
atexit.register(shutil.rmtree, _SCRATCH, True)
os.environ["XDG_CACHE_HOME"] = _SCRATCH

import wl_ci as W  # noqa: E402

_CI = pathlib.Path(__file__).resolve().parents[3] / ".ci" / "rediacc_ci"
spec = importlib.util.spec_from_file_location("controls", _CI / "controls.py")
if spec is None or spec.loader is None:
    raise SystemExit("%s: .ci/rediacc_ci/controls.py is missing" % __file__)
controls = importlib.util.module_from_spec(spec)
spec.loader.exec_module(controls)
T = controls.Controls("ci-rerun", floor=10)
check = T.check

RUN = 37633980671
TIP = "c6cca783" + "0" * 32
SUB = "Quality / Submodule Branches"
SHARD = "Quality / Shard receipts"
A1_SUB, A2_SUB = 112836644226, 112840910316
A1_SHARD, A2_SHARD = 112836644300, 112840919449


def ctx(name, job_id, conclusion, run=RUN):
    return {
        "__typename": "CheckRun",
        "name": name,
        "status": "COMPLETED",
        "conclusion": conclusion,
        "databaseId": job_id,
        "detailsUrl": "",
        "checkSuite": {"workflowRun": {"databaseId": run}},
    }


COMPLETE_OK = ctx("CI Complete", 112844873745, "SUCCESS")


def names(rows):
    return sorted(r["name"] for r in rows)


# ---- 1. attempt 1 X failure, attempt 2 X success -> not red (either order in the list) -------------
for label, order in (("old first", [0, 1]), ("new first", [1, 0])):
    cs = [ctx(SUB, A1_SUB, "FAILURE"), ctx(SUB, A2_SUB, "SUCCESS")]
    info = {"contexts": [cs[i] for i in order] + [COMPLETE_OK]}
    live, hard, soft = W.ci_classify(info)
    check("rerun green, %s: no hard failure" % label, hard, [])
    check("rerun green, %s: ci_gate is green" % label, W.ci_gate(info)["verdict"], "green")

# ---- 2. a job the later attempt did NOT re-run keeps its attempt-1 failure --------------------------
info = {
    "contexts": [
        ctx(SUB, A1_SUB, "FAILURE"),
        ctx(SUB, A2_SUB, "SUCCESS"),
        ctx(SHARD, A1_SHARD, "FAILURE"),
        COMPLETE_OK,
    ]
}
_live, hard, _soft = W.ci_classify(info)
check("a job attempt 2 did not re-run stays red", names(hard), [SHARD])
check("... and the gate is red on it", W.ci_gate(info)["verdict"], "red")

# ---- 3. the newest attempt failing is red, whatever the older one did -------------------------------
info = {"contexts": [ctx(SUB, A1_SUB, "SUCCESS"), ctx(SUB, A2_SUB, "FAILURE"), COMPLETE_OK]}
check("attempt 2 failure after attempt 1 success is red", names(W.ci_classify(info)[1]), [SUB])

# ---- 4. the same job name in two different runs is two jobs, not two attempts ------------------------
info = {"contexts": [ctx("X", 5, "FAILURE", run=1), ctx("X", 9, "SUCCESS", run=2)]}
check("same name, different run: both kept", len(W.latest_per_job(info["contexts"])), 2)
check("same name, different run: the failure still counts", names(W.ci_classify(info)[1]), ["X"])

# ---- 5. THE CACHE: a final red must not outlive the rerun for the final TTL --------------------------
CASE = [0]


def trouble_twice(first_ctxs, second_ctxs, age_s):
    """ci_trouble twice over one cache; the cache is aged `age_s` between the reads. Returns the second state."""
    CASE[0] += 1
    base = pathlib.Path(_SCRATCH) / ("case%d" % CASE[0])
    base.mkdir()
    box = {"ctxs": first_ctxs}

    def rollup(_root, _ref, allow_branch=False, repo=None):  # noqa: ARG001 -- ci_rollup's signature
        return "ok", {
            "owner": "rediacc",
            "name": "console",
            "pr": 599,
            "sha": TIP,
            "contexts": list(box["ctxs"]),
        }

    saved = (W.ci_rollup, W.ci_steps, W._git, W.ci_carry_split, W.ci_watch_armed)
    W.ci_rollup = rollup
    W.ci_steps = lambda *_a, **_k: None
    W._git = lambda _r, *a: TIP if a[:1] == ("rev-parse",) else ""
    W.ci_carry_split = lambda _r, _i, _t, hard, _c, **_k: (hard, [])
    W.ci_watch_armed = lambda *_a, **_k: None
    try:
        first, _d = W.ci_trouble(base, base / "wl.md", "deadbeef-t", [], "", ref="pub", owned=True)
        cache_p = W.cistate_path(base / "wl.md", "deadbeef-t")
        doc = W.wl_gh.cache_load(cache_p) or {}
        doc["at"] = time.time() - age_s
        W.wl_gh.cache_write(cache_p, doc)
        box["ctxs"] = second_ctxs
        second, _d = W.ci_trouble(base, base / "wl.md", "deadbeef-t", [], "", ref="pub", owned=True)
    finally:
        W.ci_rollup, W.ci_steps, W._git, W.ci_carry_split, W.ci_watch_armed = saved
    return first, second


red_then_green = (
    [ctx(SUB, A1_SUB, "FAILURE"), COMPLETE_OK],
    [ctx(SUB, A2_SUB, "SUCCESS"), COMPLETE_OK],
)
first, second = trouble_twice(*red_then_green, age_s=400)
check("cache control: the first read is red", first, "trouble")
check(
    "cache: a final red older than the live TTL is re-read, so the green rerun shows", second, "ok"
)
first, second = trouble_twice(
    [ctx(SUB, A1_SUB, "SUCCESS"), COMPLETE_OK], [ctx(SUB, A2_SUB, "FAILURE"), COMPLETE_OK], 400
)
check("cache control: a final GREEN keeps the long TTL (no extra read)", second, "ok")

T.exit()
