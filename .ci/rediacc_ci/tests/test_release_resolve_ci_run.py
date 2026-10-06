"""`rediacc_ci.release.resolve_ci_run` against its bash twin.

THE FAKE `gh` UNDERSTANDS `--jq`, because both the twin and this port ask `gh api` to apply a jq filter itself (`--jq '.workflow_runs[0].id // empty'`, `--jq '.head_sha'`) rather than piping to a separate `jq` process for those two calls -- so a fake that ignores `--jq` and echoes the whole body would silently test a different code path than CI runs. The fake shells out to the REAL
`jq` (a generic tool, no credentials) to apply whatever filter it was given, against one of two canned bodies selected by which endpoint the URL names: `FAKE_GH_LIST_JSON` for the `actions/workflows/ci.yml/runs?...` listing, `FAKE_GH_RUN_JSON` for `actions/runs/<id>` (used for both the explicit-id validation lookup and the final head_sha lookup, exactly as the twin calls that same
endpoint twice). `FAKE_GH_RUN_RC` reproduces the twin's
`2>/dev/null || echo '{}'` fallback path.

THE PORT DIFFERS FROM THE TWIN ON ONE DELIBERATE POINT (see the module docstring): it releases only a run whose `Stage Artifacts / Stage Artifacts` job concluded `success`. The twin's golden is frozen and is never re-recorded, so the cases below that both sides still answer identically stay differentials, the auto-derive success case gives the port (and only the port) a qualifying listing through `port_env`, and the new behaviour is pinned by port-only tests at the bottom. `FAKE_GH_STAGE_JSON` maps a run id to the conclusion of its Stage Artifacts job; an id absent from it has no such job (a skipped duplicate).
"""

from __future__ import annotations

import os
import stat
import sys
from typing import TYPE_CHECKING

from rediacc_ci.tests import differential as diff
from rediacc_ci.well_known import GH_REPO

if TYPE_CHECKING:
    import pathlib

TWIN = ".ci/scripts/release/resolve-ci-run.sh"
MODULE = "resolve_ci_run"

FAKE_GH_SRC = r"""#!{python}
import json
import os
import subprocess
import sys

argv = sys.argv[1:]
# Expected shapes: ["api", URL] or ["api", URL, "--jq", FILTER]
url = argv[1] if len(argv) > 1 else ""
jq_filter = None
if "--jq" in argv:
    jq_filter = argv[argv.index("--jq") + 1]

if os.environ.get("FAKE_GH_URL_LOG"):
    with open(os.environ["FAKE_GH_URL_LOG"], "a") as log:
        log.write(url + "\\n")

if "/jobs" in url:
    rc = 0
    stage = json.loads(os.environ.get("FAKE_GH_STAGE_JSON", "{}"))
    run_id = url.split("/runs/")[1].split("/")[0]
    jobs = []
    if run_id in stage:
        jobs.append({"name": "Stage Artifacts / Stage Artifacts", "conclusion": stage[run_id]})
    jobs.append({"name": "Initialize", "conclusion": "skipped"})
    body = json.dumps({"jobs": jobs})
elif "workflows/ci.yml/runs" in url:
    rc = int(os.environ.get("FAKE_GH_LIST_RC", "0"))
    body = os.environ.get("FAKE_GH_LIST_JSON", "{}")
else:
    rc = int(os.environ.get("FAKE_GH_RUN_RC", "0"))
    body = os.environ.get("FAKE_GH_RUN_JSON", "{}")

if rc != 0:
    sys.stderr.write("gh: simulated failure\n")
    sys.exit(rc)

if jq_filter is None:
    sys.stdout.write(body)
    sys.exit(0)

out = subprocess.run(["jq", "-r", jq_filter], input=body, capture_output=True, text=True, check=False)
sys.stdout.write(out.stdout)
sys.exit(out.returncode)
"""


def _make_fake_gh(tmp_path: pathlib.Path) -> pathlib.Path:
    bindir = tmp_path / "fakebin"
    bindir.mkdir(exist_ok=True)
    script = bindir / "gh"
    script.write_text(FAKE_GH_SRC.replace("{python}", sys.executable))
    script.chmod(script.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return bindir


def run_both(
    tmp_path: pathlib.Path,
    bindir: pathlib.Path,
    env_extra: dict[str, str],
    port_env: dict[str, str] | None = None,
) -> tuple[tuple[int, str, str], tuple[int, str, str], str, str]:
    out_old = tmp_path / "old-output.txt"
    out_new = tmp_path / "new-output.txt"
    path_with_fake = f"{bindir}:{os.environ.get('PATH', '/usr/bin:/bin')}"
    old_env = diff.env_for(**env_extra, GITHUB_OUTPUT=str(out_old), PATH=path_with_fake)
    new_env = diff.env_for(
        **{**env_extra, **(port_env or {})},
        GITHUB_OUTPUT=str(out_new),
        PATH=path_with_fake,
        PYTHONPATH=".ci",
        PYTHONDONTWRITEBYTECODE="1",
    )
    rc, out, err, _ = diff.twin_run(
        TWIN,
        sorted("%s=%s" % kv for kv in env_extra.items()),
        lambda: diff.bash_streams("bash %s" % TWIN, env=old_env, timeout=30),
        files=[out_old],
        work=(tmp_path,),
    )
    old = (rc, out, err)
    new = diff.bash_streams("python3 -m rediacc_ci.release.%s" % MODULE, env=new_env, timeout=30)
    old_output = out_old.read_text(encoding="utf-8") if out_old.exists() else ""
    new_output = out_new.read_text(encoding="utf-8") if out_new.exists() else ""
    return old, new, old_output, new_output


def test_auto_derive_picks_the_latest_green_run_on_both_sides(tmp_path: pathlib.Path) -> None:
    bindir = _make_fake_gh(tmp_path)
    env = {
        "GITHUB_REPOSITORY": GH_REPO,
        "FAKE_GH_LIST_JSON": '{"workflow_runs":[{"id":555}]}',
        "FAKE_GH_RUN_JSON": '{"head_sha":"abc123"}',
    }
    # The twin answers from the golden for `env`; the port gets a listing that qualifies (push event, staged), the one thing the twin does not need.
    port_env = {
        "FAKE_GH_LIST_JSON": '{"workflow_runs":[{"id":555,"event":"push"}]}',
        "FAKE_GH_STAGE_JSON": '{"555":"success"}',
    }
    (old_exit, old_out, old_err), (new_exit, new_out, new_err), old_output, new_output = run_both(
        tmp_path, bindir, env, port_env
    )
    assert (old_exit, old_err) == (0, "")
    assert (new_exit, new_err) == (0, "")
    assert "Auto-derived ci_run_id=555" in old_out
    assert old_out == new_out
    assert old_output == "ci_run_id=555\nci_sha=abc123\n"
    assert new_output == old_output


def test_auto_derive_with_no_green_run_fails_on_both_sides(tmp_path: pathlib.Path) -> None:
    bindir = _make_fake_gh(tmp_path)
    env = {
        "GITHUB_REPOSITORY": GH_REPO,
        "FAKE_GH_LIST_JSON": '{"workflow_runs":[]}',
    }
    (old_exit, old_out, _old_err), (new_exit, new_out, _new_err), old_output, new_output = run_both(
        tmp_path, bindir, env
    )
    assert old_exit == 1
    assert new_exit == 1
    assert "No green Console CI run found" in old_out
    assert old_out == new_out
    assert old_output == new_output == ""


def test_explicit_run_id_on_the_wrong_branch_is_refused_on_both_sides(
    tmp_path: pathlib.Path,
) -> None:
    bindir = _make_fake_gh(tmp_path)
    env = {
        "GITHUB_REPOSITORY": GH_REPO,
        "INPUT_CI_RUN_ID": "42",
        "FAKE_GH_RUN_JSON": (
            '{"head_branch":"feature-x","name":"Console CI","status":"completed",'
            '"conclusion":"success"}'
        ),
    }
    (old_exit, old_out, _old_err), (new_exit, new_out, _new_err), old_output, new_output = run_both(
        tmp_path, bindir, env
    )
    assert old_exit == 1
    assert new_exit == 1
    assert "is on branch 'feature-x', not 'main'" in old_out
    assert old_out == new_out
    assert old_output == new_output == ""


def test_explicit_run_id_completed_failure_allow_stale_proceeds_on_both_sides(
    tmp_path: pathlib.Path,
) -> None:
    bindir = _make_fake_gh(tmp_path)
    env = {
        "GITHUB_REPOSITORY": GH_REPO,
        "INPUT_CI_RUN_ID": "42",
        "ALLOW_STALE": "true",
        "FAKE_GH_RUN_JSON": (
            '{"head_branch":"main","name":"Console CI","status":"completed",'
            '"conclusion":"failure","head_sha":"deadbeef"}'
        ),
    }
    (old_exit, old_out, old_err), (new_exit, new_out, new_err), old_output, new_output = run_both(
        tmp_path, bindir, env
    )
    assert (old_exit, old_err) == (0, "")
    assert (new_exit, new_err) == (0, "")
    assert "allow_stale_ci_run_id is set, proceeding anyway" in old_out
    assert old_out == new_out
    assert old_output == "ci_run_id=42\nci_sha=deadbeef\n"
    assert new_output == old_output


def test_a_failed_run_lookup_falls_back_to_empty_object_on_both_sides(
    tmp_path: pathlib.Path,
) -> None:
    """`gh api ... 2>/dev/null || echo '{}'`: a failed lookup degrades to an
    empty object, which then fails validation as an empty branch/workflow -- not a crash."""
    bindir = _make_fake_gh(tmp_path)
    env = {
        "GITHUB_REPOSITORY": GH_REPO,
        "INPUT_CI_RUN_ID": "999",
        "FAKE_GH_RUN_RC": "1",
    }
    (old_exit, old_out, _old_err), (new_exit, new_out, _new_err), _old_output, _new_output = (
        run_both(tmp_path, bindir, env)
    )
    assert old_exit == 1
    assert new_exit == 1
    assert "is on branch '', not 'main'" in old_out
    assert old_out == new_out


def test_missing_github_repository_fails_the_same_way_reworded(tmp_path: pathlib.Path) -> None:
    bindir = _make_fake_gh(tmp_path)
    old, new, _, _ = run_both(tmp_path, bindir, {})
    assert old[0] == 1
    assert new[0] == 1
    assert "GITHUB_REPOSITORY" in old[2]
    assert "GITHUB_REPOSITORY" in new[2]


# --- port-only: the deliberate difference. The twin cannot answer these. ---


def run_port(tmp_path: pathlib.Path, env_extra: dict[str, str]) -> tuple[int, str, str, str]:
    bindir = _make_fake_gh(tmp_path)
    out_file = tmp_path / "port-output.txt"
    env = diff.env_for(
        GITHUB_REPOSITORY=GH_REPO,
        **env_extra,
        GITHUB_OUTPUT=str(out_file),
        PATH=f"{bindir}:{os.environ.get('PATH', '/usr/bin:/bin')}",
        PYTHONPATH=".ci",
        PYTHONDONTWRITEBYTECODE="1",
    )
    rc, out, err = diff.bash_streams(
        "python3 -m rediacc_ci.release.%s" % MODULE, env=env, timeout=30
    )
    written = out_file.read_text(encoding="utf-8") if out_file.exists() else ""
    return rc, out, err, written


def _listing(*runs: tuple[int, str]) -> str:
    return '{"workflow_runs":[%s]}' % ",".join(
        '{"id":%d,"event":"%s"}' % (rid, event) for rid, event in runs
    )


def test_auto_derive_passes_over_a_newest_no_op_duplicate(tmp_path: pathlib.Path) -> None:
    rc, out, err, written = run_port(
        tmp_path,
        {
            # 900 is the newest green run but a duplicate: Stage Artifacts never ran. 800 is the real one.
            "FAKE_GH_LIST_JSON": _listing((900, "push"), (800, "push")),
            "FAKE_GH_STAGE_JSON": '{"800":"success"}',
            "FAKE_GH_RUN_JSON": '{"head_sha":"realsha"}',
        },
    )
    assert (rc, err) == (0, "")
    assert "Auto-derived ci_run_id=800" in out
    assert written == "ci_run_id=800\nci_sha=realsha\n"


def test_auto_derive_passes_over_a_skipped_stage_job(tmp_path: pathlib.Path) -> None:
    rc, out, _err, written = run_port(
        tmp_path,
        {
            "FAKE_GH_LIST_JSON": _listing((900, "push"), (800, "push")),
            "FAKE_GH_STAGE_JSON": '{"900":"skipped","800":"success"}',
            "FAKE_GH_RUN_JSON": '{"head_sha":"s"}',
        },
    )
    assert rc == 0
    assert "Auto-derived ci_run_id=800" in out
    assert written.startswith("ci_run_id=800\n")


def test_auto_derive_passes_over_a_nightly_schedule_run(tmp_path: pathlib.Path) -> None:
    # Even if the API returned a schedule run (it stages nothing), it is not a candidate, whatever its jobs say.
    rc, out, _err, written = run_port(
        tmp_path,
        {
            "FAKE_GH_LIST_JSON": _listing((950, "schedule"), (800, "push")),
            "FAKE_GH_STAGE_JSON": '{"950":"success","800":"success"}',
            "FAKE_GH_RUN_JSON": '{"head_sha":"s"}',
        },
    )
    assert rc == 0
    assert "Auto-derived ci_run_id=800" in out
    assert written.startswith("ci_run_id=800\n")


def test_auto_derive_asks_for_a_page_of_push_runs(tmp_path: pathlib.Path) -> None:
    log = tmp_path / "urls.log"
    rc, _out, _err, _w = run_port(
        tmp_path,
        {
            "FAKE_GH_LIST_JSON": _listing((800, "push")),
            "FAKE_GH_STAGE_JSON": '{"800":"success"}',
            "FAKE_GH_RUN_JSON": '{"head_sha":"s"}',
            "FAKE_GH_URL_LOG": str(log),
        },
    )
    assert rc == 0
    listing_urls = [u for u in log.read_text().splitlines() if "workflows/ci.yml/runs" in u]
    assert listing_urls
    assert "event=push" in listing_urls[0]
    assert "per_page=20" in listing_urls[0]


def test_auto_derive_with_no_staged_candidate_gives_a_clear_error(
    tmp_path: pathlib.Path,
) -> None:
    rc, out, _err, written = run_port(
        tmp_path,
        {
            "FAKE_GH_LIST_JSON": _listing((900, "push"), (800, "push")),
            "FAKE_GH_STAGE_JSON": '{"800":"failure"}',
        },
    )
    assert rc == 1
    assert (
        "::error::None of the 2 newest green push Console CI runs on main staged artifacts" in out
    )
    assert "Cannot auto-derive ci_run_id" in out
    assert written == ""


def _explicit_env(stage: str, **more: str) -> dict[str, str]:
    return {
        "INPUT_CI_RUN_ID": "42",
        "FAKE_GH_RUN_JSON": (
            '{"head_branch":"main","name":"Console CI","status":"completed",'
            '"conclusion":"success","head_sha":"cafe"}'
        ),
        "FAKE_GH_STAGE_JSON": stage,
        **more,
    }


def test_explicit_run_id_that_staged_is_accepted(tmp_path: pathlib.Path) -> None:
    rc, _out, err, written = run_port(tmp_path, _explicit_env('{"42":"success"}'))
    assert (rc, err) == (0, "")
    assert written == "ci_run_id=42\nci_sha=cafe\n"


def test_explicit_run_id_that_is_a_no_op_is_refused(tmp_path: pathlib.Path) -> None:
    rc, out, _err, written = run_port(tmp_path, _explicit_env("{}"))
    assert rc == 1
    assert "ci_run_id 42 did not stage artifacts" in out
    assert "ci_run_id validation failed" in out
    assert written == ""


def test_explicit_no_op_run_id_proceeds_under_allow_stale(tmp_path: pathlib.Path) -> None:
    rc, _out, err, written = run_port(tmp_path, _explicit_env("{}", ALLOW_STALE="true"))
    assert (rc, err) == (0, "")
    assert written == "ci_run_id=42\nci_sha=cafe\n"
