"""wl_schedred: a red scheduled workflow on main reaches an agent session, one session owns it, and reading it costs a bounded number of calls (agent/plans/PLAN-scheduled-red-detector.md, Part A).

The unit cases drive `wl_schedred` directly with a ROUTING `gh` shim on PATH: each call is logged, so a network call is COUNTED rather than assumed absent, and each answer is chosen by a substring of the call so the runs page, the per-workflow fallback and the jobs read can disagree on purpose. The Stop cases drive the real hook to prove the wiring in `wl_checks`: the claimant is blocked with the exact `--add` line, a peer gets one advisory, and the block goes quiet once
the item exists. Every positive case sits beside a control that differs in the one thing under test.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time

import pytest

from rediacc_hooks.tests import wlfix
from rediacc_hooks.tests.wlfix import wl  # noqa: F401

SR = wlfix.import_wl("wl_schedred")
M = wlfix.import_wl("worklist_messages")
S = wlfix.import_wl("wl_store")

RED_RUN = 37101760904
GREEN_RUN = 37201760904
CI_YML = """name: Console CI
on:
  push:
    branches: [main]
  schedule:
    # declared 01:00, dispatched later
    - cron: '0 1 * * *'
  workflow_dispatch:
jobs: {}
"""
HK_YML = """name: Housekeeping
on:
  schedule:
    - cron: '0 3 * * *' # daily
jobs: {}
"""
COMMENTED_YML = """name: Was Nightly
on:
  push:
#  schedule:
#    - cron: '0 2 * * *'
jobs: {}
"""
PLAIN_YML = """name: Plain
on:
  pull_request:
jobs: {}
"""


def run(rid, file="ci.yml", conclusion="failure", attempt=1, created="2026-10-03T06:02:45Z", **kw):
    doc = {
        "id": rid,
        "name": "Console CI",
        "path": ".github/workflows/%s" % file,
        "event": "schedule",
        "status": "completed",
        "conclusion": conclusion,
        "run_attempt": attempt,
        "created_at": created,
        "html_url": "https://github.com/fake/repo/actions/runs/%d" % rid,
    }
    doc.update(kw)
    return doc


SHIM = r"""#!%(py)s
import json, sys
args = " ".join(sys.argv[1:])
with open(%(log)r, "a") as fh:
    fh.write(args + "\n")
routes = json.load(open(%(routes)r))
for needle, answer in routes:
    if needle in args:
        sys.stdout.write(json.dumps(answer.get("out", {})))
        sys.stderr.write(answer.get("err", ""))
        sys.exit(answer.get("rc", 0))
sys.stderr.write("no route")
sys.exit(1)
"""


class Gh:
    """A routing `gh` shim: `route(needle, out)` answers every call containing `needle`, first match wins."""

    def __init__(self, base):
        self.bindir = base / "ghbin"
        self.bindir.mkdir(parents=True, exist_ok=True)
        self.log = base / "gh.log"
        self.routes_file = base / "routes.json"
        self.routes = []
        self.save()
        gh = self.bindir / "gh"
        gh.write_text(
            SHIM % {"py": sys.executable, "log": str(self.log), "routes": str(self.routes_file)},
            encoding="utf-8",
        )
        gh.chmod(0o755)

    def save(self):
        self.routes_file.write_text(json.dumps(self.routes), encoding="utf-8")

    def route(self, needle, out=None, rc=0, err=""):
        self.routes.append([needle, {"out": out or {}, "rc": rc, "err": err}])
        self.save()

    def reset(self):
        self.routes = []
        self.save()

    def calls(self, needle=""):
        lines = self.log.read_text(encoding="utf-8").splitlines() if self.log.exists() else []
        return [ln for ln in lines if needle in ln]


def git(root, *args):
    return subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True, check=True
    ).stdout.strip()


def make_repo(root, origin=True, workflows=None):
    """A git repo with `.github/workflows` and, when `origin`, a github origin and an origin/main ref at HEAD."""
    root.mkdir(parents=True, exist_ok=True)
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.email", "t@t")
    git(root, "config", "user.name", "t")
    wdir = root / ".github" / "workflows"
    wdir.mkdir(parents=True, exist_ok=True)
    for name, body in (workflows or {"ci.yml": CI_YML, "housekeeping.yml": HK_YML}).items():
        (wdir / name).write_text(body, encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "base")
    if origin:
        git(root, "remote", "add", "origin", wlfix.FAKE_ORIGIN)
        git(root, "update-ref", "refs/remotes/origin/main", git(root, "rev-parse", "HEAD"))
    return root


@pytest.fixture
def gh(tmp_path, monkeypatch):
    shim = Gh(tmp_path)
    monkeypatch.setenv("PATH", str(shim.bindir), prepend=os.pathsep)
    return shim


@pytest.fixture
def repo(tmp_path):
    return make_repo(tmp_path / "repo")


def serve(gh, runs, jobs=None, fallback=None):
    """Routes for one refresh: the jobs read, the per-workflow fallback, then the runs page (most specific first)."""
    gh.reset()
    gh.route("/jobs", {"jobs": jobs if jobs is not None else []})
    gh.route("/actions/workflows/", {"workflow_runs": fallback or []})
    gh.route("actions/runs?event=schedule", {"workflow_runs": runs})


def row_of(doc, stem):
    return next(w for w in doc["workflows"] if w["stem"] == stem)


# --------------------------------------------------------------------------- discovery


def test_discovery_reads_uncommented_schedules_only(tmp_path):
    root = make_repo(
        tmp_path / "r",
        origin=False,
        workflows={
            "ci.yml": CI_YML,
            "housekeeping.yml": HK_YML,
            "was-nightly.yml": COMMENTED_YML,
            "plain.yaml": PLAIN_YML,
        },
    )
    got = SR.scheduled_workflows(root)
    assert [(w["stem"], w["name"], w["crons"]) for w in got] == [
        ("ci", "Console CI", ["0 1 * * *"]),
        ("housekeeping", "Housekeeping", ["0 3 * * *"]),
    ]
    # Control: uncomment the schedule and the same file is discovered, so the exclusion above is the comment and not the parser missing the shape.
    (root / ".github" / "workflows" / "was-nightly.yml").write_text(
        COMMENTED_YML.replace("#  schedule:", "  schedule:").replace("#    - cron", "    - cron"),
        encoding="utf-8",
    )
    assert "was-nightly" in [w["stem"] for w in SR.scheduled_workflows(root)]


def test_discovery_pins_this_repos_scheduled_workflows():
    """The list is discovered, never hardcoded; this pin says which workflows that discovery finds today, so a schedule silently dropping out of the watch fails here."""
    root = wlfix.STOP_DIR.parents[2]
    stems = {w["stem"] for w in SR.scheduled_workflows(root)}
    assert stems == {"ci", "housekeeping", "promote-stable", "ci-obs-mirror", "ci-vm-bake"}


# --------------------------------------------------------------------------- the verdict


def test_newest_scheduled_run_and_its_latest_attempt_decide(repo, tmp_path, gh):
    runs = [
        run(RED_RUN, conclusion="failure", created="2026-10-02T06:00:00Z"),
        run(GREEN_RUN, conclusion="success", attempt=2, created="2026-10-03T06:00:00Z"),
        run(1, file="housekeeping.yml", conclusion="success"),
    ]
    serve(gh, runs)
    doc = SR.refresh(repo, tmp_path / "wl.md", force=True)
    ci = row_of(doc, "ci")
    assert (ci["run_id"], ci["attempt"], ci["red"]) == (GREEN_RUN, 2, False)
    # Control: the newest run is the red one, so the verdict turns red.
    serve(gh, [run(RED_RUN, created="2026-10-04T06:00:00Z"), *runs[1:]])
    assert row_of(SR.refresh(repo, tmp_path / "wl.md", force=True), "ci")["red"] is True


def test_a_green_dispatch_run_never_clears_a_scheduled_red(repo, tmp_path, gh):
    red = run(RED_RUN, created="2026-10-03T06:00:00Z")
    hk = run(1, file="housekeeping.yml", conclusion="success")
    dispatch = run(
        GREEN_RUN, conclusion="success", created="2026-10-03T09:00:00Z", event="workflow_dispatch"
    )
    serve(gh, [dispatch, red, hk])
    assert row_of(SR.refresh(repo, tmp_path / "wl.md", force=True), "ci")["red"] is True
    # Control: the same green as a SCHEDULED run does clear it.
    serve(gh, [dict(dispatch, event="schedule"), red, hk])
    assert row_of(SR.refresh(repo, tmp_path / "wl.md", force=True), "ci")["red"] is False


@pytest.mark.parametrize(
    ("conclusion", "red"),
    [
        ("success", False),
        ("failure", True),
        ("cancelled", True),
        ("timed_out", True),
        ("startup_failure", True),
        (None, False),
    ],
)
def test_the_red_predicate(conclusion, red):
    assert SR.is_red(conclusion) is red


def test_a_red_names_its_failed_jobs_and_the_jobs_read_is_cached_per_attempt(repo, tmp_path, gh):
    runs = [run(RED_RUN), run(1, file="housekeeping.yml", conclusion="success")]
    jobs = [
        {"name": "Quality / Pytest (3/3)", "conclusion": "failure"},
        {"name": "Skipped one", "conclusion": "skipped"},
        {"name": "Fine", "conclusion": "success"},
        {"name": "Cut", "conclusion": "cancelled"},
    ]
    serve(gh, runs, jobs=jobs)
    wlp = tmp_path / "wl.md"
    ci = row_of(SR.refresh(repo, wlp, force=True), "ci")
    assert ci["failed_jobs"] == ["Quality / Pytest (3/3)", "Cut"]
    assert len(gh.calls("/jobs")) == 1
    SR.refresh(repo, wlp, force=True)
    assert len(gh.calls("/jobs")) == 1, "the same (run, attempt) reuses its cached jobs"
    # Control: a new attempt of the same run is a new key, so its jobs are read again.
    serve(gh, [run(RED_RUN, attempt=2), runs[1]], jobs=jobs)
    SR.refresh(repo, wlp, force=True)
    assert len(gh.calls("/jobs")) == 2


def test_a_workflow_missing_from_the_page_gets_one_fallback_call(repo, tmp_path, gh):
    serve(
        gh,
        [run(RED_RUN)],
        fallback=[run(5, file="housekeeping.yml", conclusion="cancelled")],
    )
    doc = SR.refresh(repo, tmp_path / "wl.md", force=True)
    assert row_of(doc, "housekeeping")["run_id"] == 5
    assert row_of(doc, "housekeeping")["red"] is True, "cancelled is red"
    fb = gh.calls("/actions/workflows/")
    assert len(fb) == 1
    assert "housekeeping.yml/runs?event=schedule&status=completed&per_page=1" in fb[0]
    # Control: with both workflows on the page, no fallback call is made.
    gh.log.unlink()
    serve(gh, [run(RED_RUN), run(5, file="housekeeping.yml")])
    SR.refresh(repo, tmp_path / "wl.md", force=True)
    assert gh.calls("/actions/workflows/") == []


def test_an_in_flight_rerun_is_reported_without_becoming_the_verdict(repo, tmp_path, gh):
    serve(
        gh,
        [
            run(RED_RUN + 1, status="in_progress", conclusion=None, created="2026-10-04T06:00:00Z"),
            run(RED_RUN),
            run(5, file="housekeeping.yml", conclusion="success"),
        ],
    )
    ci = row_of(SR.refresh(repo, tmp_path / "wl.md", force=True), "ci")
    assert (ci["run_id"], ci["red"], ci["in_flight"]) == (RED_RUN, True, True)
    assert row_of(SR.read_cache(tmp_path / "wl.md"), "housekeeping")["in_flight"] is False


# --------------------------------------------------------------------------- cache, TTL, failure


def test_the_ttl_serves_the_shared_cache_then_expires(repo, tmp_path, gh):
    serve(gh, [run(RED_RUN), run(5, file="housekeeping.yml")])
    wlp = tmp_path / "wl.md"
    now = time.time()
    SR.refresh(repo, wlp, now=now)
    page = "actions/runs?event=schedule"
    assert len(gh.calls(page)) == 1
    SR.refresh(repo, wlp, now=now + SR.TTL_S - 5)
    assert len(gh.calls(page)) == 1, "inside the TTL every session reads the cache"
    # Control: past the TTL the page is read again.
    SR.refresh(repo, wlp, now=now + SR.TTL_S + 5)
    assert len(gh.calls(page)) == 2
    # force bypasses the TTL, and writes the shared cache for everyone.
    SR.refresh(repo, wlp, force=True, now=now + SR.TTL_S + 6)
    assert len(gh.calls(page)) == 3
    assert SR.read_cache(wlp)["at"] == now + SR.TTL_S + 6


def test_an_unreadable_answer_is_cached_for_the_error_ttl(repo, tmp_path, gh):
    gh.route("actions/runs", rc=1, err="HTTP 502: Bad Gateway")
    wlp = tmp_path / "wl.md"
    now = time.time()
    doc = SR.refresh(repo, wlp, now=now)
    assert doc["state"] == "unreadable"
    assert "502" in doc["error"]
    SR.refresh(repo, wlp, now=now + SR.ERROR_TTL_S - 5)
    assert len(gh.calls("actions/runs")) == 1
    # Control: past the error TTL (still well inside the ok TTL) it asks again.
    SR.refresh(repo, wlp, now=now + SR.ERROR_TTL_S + 5)
    assert len(gh.calls("actions/runs")) == 2


def test_a_corrupt_cache_is_refetched(repo, tmp_path, gh):
    serve(gh, [run(RED_RUN), run(5, file="housekeeping.yml")])
    wlp = tmp_path / "wl.md"
    SR.cache_path(wlp).write_text("{not json", encoding="utf-8")
    assert SR.read_cache(wlp) is None
    assert SR.refresh(repo, wlp)["state"] == "ok"
    assert len(gh.calls("actions/runs?event=schedule")) == 1


def test_a_missing_gh_fails_open(repo, tmp_path, monkeypatch):
    # git stays reachable (the origin slug comes from it); gh does not exist at all.
    gitonly = tmp_path / "gitonly"
    gitonly.mkdir()
    (gitonly / "git").symlink_to(
        subprocess.run(["which", "git"], capture_output=True, text=True, check=True).stdout.strip()
    )
    monkeypatch.setenv("PATH", str(gitonly))
    doc = SR.refresh(repo, tmp_path / "wl.md", force=True)
    assert doc["state"] == "unreadable"
    assert SR.reds(doc) == []
    assert SR.assess(tmp_path / "wl.md", [], wlfix.SID, doc)["block"] == []


def test_no_origin_means_unset_and_zero_calls(tmp_path, gh):
    root = make_repo(tmp_path / "r", origin=False)
    doc = SR.refresh(root, tmp_path / "wl.md", force=True)
    assert doc["state"] == "unset"
    assert gh.calls() == []
    assert SR.recent_runs(root, "ci") == ([], "no origin remote")
    # Control: with an origin the same call does reach gh.
    git(root, "remote", "add", "origin", wlfix.FAKE_ORIGIN)
    serve(gh, [])
    SR.refresh(root, tmp_path / "wl.md", force=True)
    assert gh.calls() != []


def test_recent_runs_resolves_a_stem_or_file_and_rejects_an_unknown_one(repo, gh):
    gh.route(
        "actions/workflows/ci.yml/runs",
        {"workflow_runs": [run(9, status="queued", conclusion=None), run(RED_RUN)]},
    )
    rows, err = SR.recent_runs(repo, "ci", limit=5)
    assert err == ""
    assert [(r["run_id"], r["red"], r["in_flight"]) for r in rows] == [
        (9, False, True),
        (RED_RUN, True, False),
    ]
    assert "per_page=5" in gh.calls()[0]
    assert SR.recent_runs(repo, "ci.yml")[1] == ""
    rows, err = SR.recent_runs(repo, "nope")
    assert rows == []
    assert "unknown scheduled workflow" in err


# --------------------------------------------------------------------------- tracking


CI_ROW = {"stem": "ci", "name": "Console CI", "file": "ci.yml", "run_id": RED_RUN}


@pytest.mark.parametrize(
    ("text", "want"),
    [
        ("sched:ci run:%d -- Console CI red" % RED_RUN, True),
        ("sched:ci", True),
        ("look at run:%d" % RED_RUN, True),
        ("bare %d id" % RED_RUN, True),
        ("Console CI nightly is red", True),
        ("console ci SCHEDULED failure", True),
        ("fix Console CI lint", False),
        ("sched:ci-obs-mirror red", False),
        ("sched:cix", False),
        ("run %d0" % RED_RUN, False),
        ("nightly housekeeping", False),
    ],
)
def test_tracking_match(text, want):
    assert SR.tracks(text, CI_ROW) is want


def test_only_open_states_track():
    items = [
        {"id": "a", "state": " ", "text": "sched:ci"},
        {"id": "b", "state": ">", "text": "sched:ci"},
        {"id": "c", "state": "?", "text": "sched:ci"},
        {"id": "d", "state": "x", "text": "sched:ci"},
    ]
    assert [r["id"] for r in SR.tracking_items(items, CI_ROW)] == ["a", "b", "c"]


# --------------------------------------------------------------------------- claims and ownership


def stamp(minutes_ago=0.0):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - minutes_ago * 60))


def red_doc(run_id=RED_RUN, conclusion="failure", created="2026-10-03T06:02:45Z", stem="ci"):
    row = dict(
        CI_ROW if stem == "ci" else {"stem": stem, "name": stem, "file": stem + ".yml"},
        run_id=run_id,
        attempt=1,
        conclusion=conclusion,
        created_at=created,
        url="u",
        failed_jobs=["Quality / Pytest (3/3)"],
        red=SR.is_red(conclusion),
        in_flight=False,
        crons=["0 1 * * *"],
    )
    return {"state": "ok", "error": "", "at": time.time(), "workflows": [row]}


def test_one_session_claims_and_the_other_gets_an_advisory(tmp_path):
    wlp = tmp_path / "wl.md"
    S.briefs_path(wlp).write_text(
        "aaaaaaaa %s a\nbbbbbbbb %s b\n" % (stamp(), stamp()), encoding="utf-8"
    )
    doc = red_doc()
    a = SR.assess(wlp, [], "aaaaaaaa-1", doc)
    b = SR.assess(wlp, [], "bbbbbbbb-2", doc)
    assert [r["run_id"] for r in a["block"]] == [RED_RUN]
    assert b["block"] == []
    assert b["peer"][0][1] == "aaaaaaaa"
    # A newer red run id starts the cycle again: the old claim is stale, so whoever stops first claims.
    b2 = SR.assess(wlp, [], "bbbbbbbb-2", red_doc(run_id=RED_RUN + 7))
    assert [r["run_id"] for r in b2["block"]] == [RED_RUN + 7]


def test_a_stale_claimant_hands_the_red_on(tmp_path):
    wlp = tmp_path / "wl.md"
    old = stamp(S.SESSION_BRIEF_STALE_MIN + 5)
    fresh = stamp()
    S.briefs_path(wlp).write_text("aaaaaaaa %s a\n" % fresh, encoding="utf-8")
    assert SR.claim(wlp, "ci", RED_RUN, "aaaaaaaa") == "aaaaaaaa"
    assert SR.claim(wlp, "ci", RED_RUN, "bbbbbbbb") == "aaaaaaaa", "a live claimant keeps it"
    # Control: the same claim with the claimant's brief gone stale moves to the next session.
    S.briefs_path(wlp).write_text("aaaaaaaa %s a\n" % old, encoding="utf-8")
    assert SR.claim(wlp, "ci", RED_RUN, "bbbbbbbb") == "bbbbbbbb"


def test_a_tracking_item_moves_ownership_to_its_owner(tmp_path):
    wlp = tmp_path / "wl.md"
    doc = red_doc()
    item = {
        "id": "c0ffee01",
        "state": " ",
        "owner": "aaaaaaaa",
        "text": "sched:ci run:%d" % RED_RUN,
    }
    mine = SR.assess(wlp, [item], "aaaaaaaa-1", doc)
    theirs = SR.assess(wlp, [item], "bbbbbbbb-2", doc)
    assert mine == {"block": [], "tick": [], "peer": [], "green": []}, "open-items holds the owner"
    assert theirs["block"] == []
    assert theirs["peer"][0][1] == "aaaaaaaa"
    assert not SR.claim_path(wlp, "ci").exists(), "a tracked red never takes a claim"
    # Control: an item about a PR lint red does not track the nightly, so the red is claimed.
    lint = dict(item, text="fix Console CI lint")
    assert SR.assess(wlp, [lint], "bbbbbbbb-2", doc)["block"]


def test_green_owes_the_owner_the_tick_command(tmp_path):
    wlp = tmp_path / "wl.md"
    green = red_doc(run_id=GREEN_RUN, conclusion="success")
    item = {
        "id": "c0ffee01",
        "state": " ",
        "owner": "aaaaaaaa",
        "text": "sched:ci run:%d" % RED_RUN,
    }
    got = SR.assess(wlp, [item], "aaaaaaaa-1", green)
    assert [(r["run_id"], it["id"]) for r, it in got["green"]] == [(GREEN_RUN, "c0ffee01")]
    text = M.N_SCHEDULED_GREEN % dict(SR.fields(got["green"][0][0], "aaaaaaaa"), item="c0ffee01")
    assert "worklist.py --tick aaaaaaaa c0ffee01 'green scheduled run %d" % GREEN_RUN in text
    assert got["block"] == []
    # Control: a peer's item is the peer's tick to make.
    assert SR.assess(wlp, [item], "bbbbbbbb-2", green)["green"] == []


# --------------------------------------------------------------------------- tick evidence


def test_tick_evidence_needs_a_newer_green_scheduled_run(repo, tmp_path):
    wlp = tmp_path / "wl.md"
    doc = red_doc()
    on_main = git(repo, "rev-parse", "HEAD")
    (repo / "side").write_text("x\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "not on main")
    off_main = git(repo, "rev-parse", "HEAD")
    now = stamp()

    def tick(note):
        return {
            "id": "c0ffee02",
            "state": "x",
            "owner": "aaaaaaaa",
            "text": "sched:ci run:%d -- red  %s" % (RED_RUN, note),
            "lastnote": note,
            "upd": now,
        }

    # Operator ruling 2026-10-04 ("Require a green run"): a fix commit, even one already on origin/main, is not evidence; only a newer green scheduled run is.
    on = SR.assess(wlp, [tick("fixed in %s" % on_main[:10])], "aaaaaaaa-1", doc)
    assert [it["id"] for _r, it in on["tick"]] == ["c0ffee02"], "a fix on main does not end a red"
    bad = SR.assess(wlp, [tick("done, should be fine")], "aaaaaaaa-1", doc)
    assert [it["id"] for _r, it in bad["tick"]] == ["c0ffee02"]
    off = SR.assess(wlp, [tick("fixed in %s" % off_main[:10])], "aaaaaaaa-1", doc)
    assert off["tick"], "an unmerged fix does not end a red"
    # A newer green scheduled run named in the evidence ends it.
    greens = [{"run_id": GREEN_RUN, "conclusion": "success", "red": False}]
    assert SR.tick_evidence_ok("green run %d" % GREEN_RUN, doc["workflows"][0], greens)
    assert not SR.tick_evidence_ok("green run %d" % (RED_RUN - 1), doc["workflows"][0], greens)


def test_an_older_cycles_tick_does_not_cover_a_newer_red(tmp_path):
    wlp = tmp_path / "wl.md"
    old_tick = {
        "id": "c0ffee03",
        "state": "x",
        "owner": "aaaaaaaa",
        "text": "sched:ci run:111111111 -- old red",
        "lastnote": "fixed",
        "upd": "2026-09-01T00:00:00Z",
    }
    got = SR.assess(wlp, [old_tick], "aaaaaaaa-1", red_doc())
    assert got["tick"] == []
    assert [r["run_id"] for r in got["block"]] == [RED_RUN], "untracked again, so claimed"


# --------------------------------------------------------------------------- SessionStart


def test_session_start_line_reads_the_cache_only(tmp_path, gh, monkeypatch):
    # The item store is pointed at the sandbox: unset, the tracked-by lookup would read the operator's real worklist.
    monkeypatch.setenv("WORKLIST_STORE_DIR", str(tmp_path / "store"))
    wlp = tmp_path / "wl.md"
    wlp.write_text("", encoding="utf-8")
    assert SR.session_start_line(wlp) == ""
    SR._write_json(SR.cache_path(wlp), dict(red_doc(), jobs={}))
    line = SR.session_start_line(wlp)
    assert line.startswith("Scheduled red on main: Console CI run %d (failure," % RED_RUN), line
    assert "untracked" in line
    assert "stale" not in line
    assert gh.calls() == [], "SessionStart makes zero gh calls"
    # Control: once an open item tracks the red, the line names it.
    S.add_item(wlp, "aaaaaaaa", "sched:ci run:%d -- tracking" % RED_RUN, owner="aaaaaaaa")
    assert "tracked by #" in SR.session_start_line(wlp)
    assert gh.calls() == []
    # Control: a cache older than six hours is marked stale.
    SR._write_json(SR.cache_path(wlp), dict(red_doc(), at=time.time() - 7 * 3600))
    assert "stale" in SR.session_start_line(wlp)
    # Control: an all-green cache says nothing.
    SR._write_json(SR.cache_path(wlp), red_doc(conclusion="success"))
    assert SR.session_start_line(wlp) == ""


# --------------------------------------------------------------------------- the Stop hook wiring


def _stop_world(fix):
    """The fixture project as a real repo with a github origin, a scheduled ci.yml and a gh shim answering one red."""
    fix.setup()
    fix.brief_now()
    make_repo(fix.proj, workflows={"ci.yml": CI_YML})
    shim = Gh(fix.base)
    serve(shim, [run(RED_RUN)], jobs=[{"name": "Quality / Pytest (3/3)", "conclusion": "failure"}])
    env = {"PATH": "%s%s%s" % (shim.bindir, os.pathsep, fix.env.get("PATH", ""))}
    return shim, env


def test_the_stop_blocks_the_claimant_then_goes_quiet_after_add(wl):  # noqa: F811
    shim, env = _stop_world(wl)
    first = wl.run(env)
    assert "SCHEDULED RED ON MAIN, UNTRACKED" in first.out, first.out[:2000]
    add = (
        "sched:ci run:%d -- Console CI red on main since 2026-10-03; failed: Quality / Pytest (3/3)"
        % RED_RUN
    )
    assert "worklist.py --add deadbeef '%s'" % add in first.out
    assert "ci-trace.py --run %d --why" % RED_RUN in first.out
    assert first.decision == "block"
    # A peer stopping now is not blocked: the claim is this session's.
    peer = wl.run_as("cafe1234", env)
    assert "SCHEDULED RED ON MAIN, UNTRACKED" not in peer.out
    assert "owned by session deadbeef" in peer.out, peer.out[:1500]
    # Once the item exists the red is tracked; the scheduled-red block is gone (open-items holds the owner instead).
    assert wl.cli("--add", "deadbeef", add).rc == 0
    second = wl.run(env)
    assert "SCHEDULED RED ON MAIN" not in second.out, second.out[:1500]
    assert shim.calls("actions/runs?event=schedule"), "the read really ran"


def test_the_stop_is_silent_on_a_green_main(wl):  # noqa: F811
    shim, env = _stop_world(wl)
    serve(shim, [run(GREEN_RUN, conclusion="success")])
    got = wl.check_quiet("SCHEDULED RED", result=wl.run(env))
    assert "owned by session" not in got.out


def test_the_stop_fixture_without_origin_makes_no_call(wl):  # noqa: F811
    wl.setup()
    wl.brief_now()
    shim = Gh(wl.base)
    env = {"PATH": "%s%s%s" % (shim.bindir, os.pathsep, wl.env.get("PATH", ""))}
    wl.run(env)
    assert shim.calls("actions/runs") == []


def test_the_session_start_hook_prints_the_cached_red_with_no_call(wl):  # noqa: F811
    wl.setup()
    shim = Gh(wl.base)
    env = dict(wl.env, PATH="%s%s%s" % (shim.bindir, os.pathsep, wl.env.get("PATH", "")))
    payload = json.dumps({"session_id": wl.sid, "cwd": str(wl.proj)})
    quiet = wl.cli("--session-start", stdin=payload, env=env)
    assert "Scheduled red on main" not in quiet.out
    SR._write_json(SR.cache_path(wl.wl), dict(red_doc(), jobs={}))
    got = wl.cli("--session-start", stdin=payload, env=env)
    assert "Scheduled red on main: Console CI run %d" % RED_RUN in got.out, got.out[:1500]
    assert "a scheduled red on main" in got.out
    assert shim.calls() == [], "SessionStart reads the cache only"


def test_no_scheduled_workflow_means_zero_calls(tmp_path, gh):
    root = make_repo(tmp_path / "r", workflows={"plain.yml": PLAIN_YML})
    doc = SR.refresh(root, tmp_path / "wl.md", force=True)
    assert (doc["state"], doc["workflows"]) == ("ok", [])
    assert gh.calls() == []
    # Control: one scheduled workflow is enough to make the read.
    (root / ".github" / "workflows" / "ci.yml").write_text(CI_YML, encoding="utf-8")
    serve(gh, [])
    SR.refresh(root, tmp_path / "wl.md", force=True)
    assert gh.calls("actions/runs?event=schedule")
