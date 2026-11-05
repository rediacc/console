"""`rediacc_ci.drills.privdrop_probe` (box H2 of PLAN-rediaccfile-unprivileged): the shipped probe file equals L1's probe, the recipe is the plan's, and the verdict table fails on a root uid or an allowed read."""

from __future__ import annotations

from rediacc_ci.drills import lifecycle_privilege as lp
from rediacc_ci.drills import privdrop_probe as pp
from rediacc_ci.tests.test_drills_lifecycle_privilege import GOOD_UP, ROOT_UP


def test_probe_file_matches_l1_probe() -> None:
    assert (pp.PROBE_DIR / "Rediaccfile").read_text() == lp.probe_rediaccfile()


def test_recipe_is_fork_upload_up_down_up_without_up_flag() -> None:
    steps = pp.recipe("nextcloud")
    assert [s[3:5] for s in steps] == [
        ["repo", "fork"],
        ["repo", "sync"],
        ["repo", "up"],
        ["repo", "down"],
        ["repo", "up"],
    ]
    assert "--up" not in steps[0] and steps[0][-2:] == ["--tag", "privdrop"]
    assert all(s[:3] == ["./rdc.sh", "--config", "eu-bench"] for s in steps)
    assert steps[2][-1] == "nextcloud:privdrop@hostinger"


def test_delete_names_only_the_fork() -> None:
    assert pp.delete_argv("gitlab", True)[-2:] == ["gitlab:privdrop@hostinger", "--dry-run"]
    assert pp.delete_argv("gitlab", False)[-2:] == ["gitlab:privdrop@hostinger", "-y"]


def test_good_probe_passes() -> None:
    p = lp.parse_probe(GOOD_UP)
    assert all(ok for _, ok, _ in pp.verdicts(p, p))


def test_root_uid_turns_red() -> None:
    rows = pp.verdicts(lp.parse_probe(ROOT_UP), lp.parse_probe(GOOD_UP))
    bad = {n for n, ok, _ in rows if not ok}
    assert "up.dropped" in bad and "down.dropped" not in bad
    assert "FAIL" in pp.table("x", rows)


def test_allowed_read_turns_red() -> None:
    p = lp.parse_probe(GOOD_UP.replace("shadow=denied", "shadow=readable"))
    assert {n for n, ok, _ in pp.verdicts(p, lp.parse_probe(GOOD_UP)) if not ok} == {"up.denied"}


def test_missing_probe_fails_everything() -> None:
    assert not any(ok for _, ok, _ in pp.verdicts({}, {}))


def test_dry_run_prints_recipe(capsys) -> None:
    assert pp.main(["nextcloud", "--dry-run"]) == 0
    assert "repo fork nextcloud@hostinger --tag privdrop" in capsys.readouterr().out
