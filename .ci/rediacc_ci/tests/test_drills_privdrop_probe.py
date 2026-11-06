"""`rediacc_ci.drills.privdrop_probe` (box H2 of PLAN-rediaccfile-unprivileged): the shipped probe file equals L1's probe, the recipe is the plan's, and the verdict table fails on a root uid or an allowed read."""

from __future__ import annotations

import subprocess

from rediacc_ci.drills import lifecycle_privilege as lp
from rediacc_ci.drills import privdrop_probe as pp
from rediacc_ci.tests.test_drills_lifecycle_privilege import GOOD_UP, ROOT_UP


def test_probe_file_matches_l1_probe() -> None:
    assert (pp.PROBE_DIR / "Rediaccfile").read_text() == lp.probe_rediaccfile()


def test_recipe_mounts_the_fork_before_the_upload() -> None:
    # `repo sync upload` refuses a fork that is not deployed (hostinger, 2026-11-05), so an up precedes it.
    steps = pp.recipe("nextcloud")
    assert [s[3:5] for s in steps] == [
        ["repo", "fork"],
        ["repo", "up"],
        ["repo", "sync"],
        ["repo", "up"],
        ["repo", "down"],
        ["repo", "up"],
    ]
    assert "--up" not in steps[0]
    assert steps[0][-2:] == ["--tag", "privdrop"]
    assert all(s[:3] == ["./rdc.sh", "--config", "eu-bench"] for s in steps)
    assert steps[1][-1] == "nextcloud:privdrop@hostinger"


def test_a_failed_step_prints_rdc_stdout(capsys, monkeypatch) -> None:
    # rdc puts its JSON error envelope on stdout; printing stderr alone showed no reason (hostinger, 2026-11-05).
    def fake(argv, _timeout=1800):
        return subprocess.CompletedProcess(argv, 2, '{"error":"not deployed"}', "progress line")

    monkeypatch.setattr(pp, "_run", fake)
    pp.run("gitlab")
    err = capsys.readouterr().err
    assert '{"error":"not deployed"}' in err
    assert "progress line" in err


def test_a_failed_up_still_probes_and_retries_with_root(capsys, monkeypatch) -> None:
    # nextcloud on hostinger, 2026-11-05: the fork's first up failed on a port its original holds, and the old
    # run stopped there, so the probe never landed and step 6 never ran.
    calls: list[list[str]] = []

    def fake(argv, _timeout=1800):
        calls.append(argv)
        rc = 1 if argv[3:5] == ["repo", "up"] and "--root" not in " ".join(calls[-2]) else 0
        return subprocess.CompletedProcess(argv, rc, "", "")

    monkeypatch.setattr(pp, "_run", fake)
    assert pp.run("nextcloud") == 1
    verbs = [c[3:6] for c in calls]
    assert ["repo", "sync", "upload"] in verbs
    assert ["repo", "permission", "grant"] in verbs
    grant = verbs.index(["repo", "permission", "grant"])
    assert verbs[grant + 1][:2] == ["repo", "up"]
    assert calls[grant][-2:] == ["nextcloud:privdrop@hostinger", "--root"]
    assert "(step 6)" in capsys.readouterr().out


def test_verdicts_are_read_before_the_root_retry(monkeypatch) -> None:
    # observability on hostinger, 2026-11-05: the probe files were read after step 6's root up, so up.* judged uid 0.
    calls: list[list[str]] = []

    def fake(argv, _timeout=1800):
        calls.append(argv)
        rc = 1 if argv[3:5] == ["repo", "up"] else 0
        return subprocess.CompletedProcess(argv, rc, "", "")

    monkeypatch.setattr(pp, "_run", fake)
    pp.run("observability")
    verbs = [c[3:6] for c in calls]
    first_read = next(i for i, v in enumerate(verbs) if v[:2] == ["term", "connect"])
    grant = verbs.index(["repo", "permission", "grant"])
    assert first_read < grant


def test_delete_names_only_the_fork() -> None:
    assert pp.delete_argv("gitlab", True)[-2:] == ["gitlab:privdrop@hostinger", "--dry-run"]
    assert pp.delete_argv("gitlab", False)[-2:] == ["gitlab:privdrop@hostinger", "-y"]


def test_good_probe_passes() -> None:
    p = lp.parse_probe(GOOD_UP)
    assert all(ok for _, ok, _ in pp.verdicts(p, p))


def test_root_uid_turns_red() -> None:
    rows = pp.verdicts(lp.parse_probe(ROOT_UP), lp.parse_probe(GOOD_UP))
    bad = {n for n, ok, _ in rows if not ok}
    assert "up.dropped" in bad
    assert "down.dropped" not in bad
    assert "FAIL" in pp.table("x", rows)


def test_allowed_read_turns_red() -> None:
    p = lp.parse_probe(GOOD_UP.replace("shadow=denied", "shadow=readable"))
    assert {n for n, ok, _ in pp.verdicts(p, lp.parse_probe(GOOD_UP)) if not ok} == {"up.denied"}


def test_missing_probe_fails_everything() -> None:
    assert not any(ok for _, ok, _ in pp.verdicts({}, {}))


def test_dry_run_prints_recipe(capsys) -> None:
    assert pp.main(["nextcloud", "--dry-run"]) == 0
    assert "repo fork nextcloud@hostinger --tag privdrop" in capsys.readouterr().out


def _recorder(monkeypatch, fail):
    calls: list[list[str]] = []

    def fake(argv, _timeout=1800):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 1 if fail(argv) else 0, "", "")

    monkeypatch.setattr(pp, "_run", fake)
    return calls


def test_a_failed_fork_deletes_nothing(monkeypatch) -> None:
    calls = _recorder(monkeypatch, lambda a: a[3:5] == ["repo", "fork"])
    assert pp.run("x") == 1
    assert not any(c[3:5] == ["repo", "delete"] for c in calls)


def test_a_failing_dry_run_stops_the_real_delete(monkeypatch) -> None:
    calls = _recorder(monkeypatch, lambda a: a[3:5] == ["repo", "delete"] and "--dry-run" in a)
    assert pp.run("x") == 1
    deletes = [c for c in calls if c[3:5] == ["repo", "delete"]]
    assert len(deletes) == 1
    assert "--dry-run" in deletes[0]


def test_a_later_stop_skips_the_root_retry(monkeypatch) -> None:
    # the first up fails (continue), then the upload fails (break): step 6 must not run on that fork
    state = {"ups": 0}

    def fail(argv) -> bool:
        if argv[3:5] == ["repo", "up"]:
            state["ups"] += 1
            return state["ups"] == 1
        return argv[3:6] == ["repo", "sync", "upload"]

    calls = _recorder(monkeypatch, fail)
    assert pp.run("x") == 1
    assert not any(c[3:6] == ["repo", "permission", "grant"] for c in calls)


def test_table_is_red_when_a_step_failed_though_the_rows_hold() -> None:
    rows = pp.verdicts(lp.parse_probe(GOOD_UP), lp.parse_probe(GOOD_UP))
    assert "PASS" in pp.table("x", rows)
    assert "FAIL" in pp.table("x", rows, steps_ok=False).splitlines()[0]
