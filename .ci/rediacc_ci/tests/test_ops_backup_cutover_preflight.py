"""`rediacc_ci.ops.backup_cutover_preflight` against its bash twin `scripts/ops/backup-cutover-preflight.sh`, on the sealed fake-binary PATH of `ops_cf_harness`.

Differentials compare stdout, stderr (ANSI stripped) and the exit code over passing and failing worlds. `test_delta_*` cases pin the Rule T differences, each asserting the bash behaviour first as the control.
"""

from __future__ import annotations

import json
import typing

import pytest

from rediacc_ci.tests import ops_cf_harness as h

if typing.TYPE_CHECKING:
    import pathlib

STORE = {
    "ACCOUNT_BACKUP_S3_ENDPOINT": "https://acct.r2.example.invalid/",
    "ACCOUNT_BACKUP_S3_BUCKET": "rediacc-backups-probe",
    "ACCOUNT_BACKUP_S3_ACCESS_KEY_ID": "key-id",
    "ACCOUNT_BACKUP_S3_SECRET_ACCESS_KEY": "key-secret",
}
HEAD_OK = [
    {"method": "GET", "match": "rediacc-backups-probe", "raw": "", "status": 200, "bare": True}
]


def _populate(
    world: h.World,
    *,
    renet_ok: bool = True,
    plane: bool = True,
    generator: str | None = "Refusing to generate a unit that would back up nothing",
) -> None:
    root = world.root
    if renet_ok is not None:
        renet = root / "private/renet/bin/renet"
        renet.parent.mkdir(parents=True)
        renet.write_text("#!/bin/bash\nexit %d\n" % (0 if renet_ok else 1))
        renet.chmod(0o755)
    if plane:
        p = root / "private/account/src/services/backup-chunk-store.ts"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("const x = ACCOUNT_BACKUP_R2_GRANT_PARENT_SECRET;\n")
    if generator is not None:
        g = root / "packages/cli/src/services/backup/backup-schedule-unit-generator.ts"
        g.parent.mkdir(parents=True)
        g.write_text("// %s\n" % generator)


@pytest.fixture
def world(tmp_path: pathlib.Path) -> h.World:
    w = h.World(tmp_path)
    for _tool in ("renet",):
        pass
    return w


def _both(world: h.World, **env: str):
    e = world.env(**env)
    b = world.bash("scripts/ops/backup-cutover-preflight.sh", [], e)
    calls_b = [c for c in world.calls() if c["tool"] == "curl"]
    world.reset_log()
    p = world.port("rediacc_ci.ops.backup_cutover_preflight", [], e)
    return b, p, calls_b, [c for c in world.calls() if c["tool"] == "curl"]


def _same(b: tuple, p: tuple) -> None:
    assert b[0] == p[0]
    assert b[1] == p[1]
    assert h.strip(b[2]) == h.strip(p[2])


def test_all_pass_matches_bash(world: h.World) -> None:
    _populate(world)
    world.set_routes(HEAD_OK)
    b, p, _calls_b, calls_p = _both(world, **STORE)
    _same(b, p)
    assert p[0] == 0
    assert "6 checks, all passed" in p[2]
    head = [c for c in calls_p if c["method"] == "GET" and "rediacc-backups-probe" in c["url"]]
    assert head
    assert head[0]["url"] == "https://acct.r2.example.invalid/rediacc-backups-probe"


def test_no_store_env_is_a_refusal_in_both(world: h.World) -> None:
    _populate(world)
    b, p, _, _ = _both(world)
    _same(b, p)
    assert p[0] == 1
    assert "no chunk store to check" in p[2]


@pytest.mark.parametrize(
    ("status", "needle"), [(403, "403 on"), (404, "404: bucket"), (500, "unexpected HTTP 500")]
)
def test_store_statuses_match_bash(world: h.World, status: int, needle: str) -> None:
    _populate(world)
    world.set_routes(
        [
            {
                "method": "GET",
                "match": "rediacc-backups-probe",
                "raw": "",
                "status": status,
                "bare": True,
            }
        ]
    )
    b, p, _, _ = _both(world, **STORE)
    _same(b, p)
    assert p[0] == 1
    assert needle in p[2]


def test_the_bare_production_bucket_name_fails_in_both(world: h.World) -> None:
    _populate(world)
    world.set_routes(
        [{"method": "GET", "match": "rediacc-backups", "raw": "", "status": 200, "bare": True}]
    )
    b, p, _, _ = _both(world, **{**STORE, "ACCOUNT_BACKUP_S3_BUCKET": "rediacc-backups"})
    _same(b, p)
    assert p[0] == 1
    assert "bare production name" in p[2]


def test_the_jwt_minter_selected_fails_in_both(world: h.World) -> None:
    _populate(world)
    world.set_routes(HEAD_OK)
    b, p, _, _ = _both(world, **{**STORE, "ACCOUNT_BACKUP_R2_GRANT_PARENT_SECRET": "x"})
    _same(b, p)
    assert p[0] == 1
    assert "LOCALLY-SIGNED" in p[2]


def test_a_renet_without_the_verbs_fails_in_both(world: h.World) -> None:
    _populate(world, renet_ok=False)
    world.set_routes(HEAD_OK)
    b, p, _, _ = _both(world, **STORE)
    _same(b, p)
    assert p[0] == 1
    assert "no 'backup restore' verb" in p[2]


def test_a_missing_renet_and_plane_fail_in_both(world: h.World) -> None:
    _populate(world, renet_ok=None, plane=False)  # type: ignore[arg-type]
    world.set_routes(HEAD_OK)
    b, p, _, _ = _both(world, **STORE)
    _same(b, p)
    assert "renet binary is missing" in p[2]
    assert "private/account is not checked out" in p[2]


def test_the_resurrected_rclone_path_fails_in_both(world: h.World) -> None:
    _populate(world, generator="backup sync push")
    world.set_routes(HEAD_OK)
    b, p, _, _ = _both(world, **STORE)
    _same(b, p)
    assert p[0] == 1
    assert "STILL PRESENT" in p[2]


def test_delta_the_secret_is_not_on_curls_argv(world: h.World) -> None:
    _populate(world)
    world.set_routes(HEAD_OK)
    _, _, calls_b, calls_p = _both(world, **STORE)
    head_b = next(c for c in calls_b if "rediacc-backups-probe" in c["url"])
    head_p = next(c for c in calls_p if "rediacc-backups-probe" in c["url"])
    assert head_b["creds_on_argv"] is True  # the control: `--user key:secret` on argv
    assert head_p["creds_on_argv"] is False
    assert head_p["creds_on_stdin"] is True
    assert "key-secret" not in json.dumps(calls_p)


def test_delta_a_long_help_text_does_not_read_as_no_sigv4(world: h.World) -> None:
    _populate(world)
    world.set_routes(HEAD_OK)
    b, p, _, _ = _both(world, FAKE_HELP_LINES="20000", **STORE)
    # The fake curl's help is far longer than the pipe buffer, so the bash `curl --help all | grep -q` under pipefail sees curl die of the closed pipe.
    assert b[0] == 1
    assert "curl lacks --aws-sigv4" in b[2]
    assert p[0] == 0
    assert "curl lacks" not in p[2]
