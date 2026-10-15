"""`check:ci-bws-map-live`, driven as a process against a FAKE `bws` that lists the real map's names.

WHAT THIS ADDS TO THE GATE'S OWN `--selftest`. The controls prove the projection and the comparison as functions. Here the entry point runs end to end, with `BWS_BIN` naming a fake CLI that prints the committed map's own names and UUIDs beside a sentinel VALUE on every row, so the exit codes (0 clean, 1 lingering or moved, 77 cannot run), the token resolution and the promise that no value reaches either stream are proven through the real invocation. No test here reaches Bitwarden.
"""

import json
import pathlib
import sys

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

GATE = paths.from_root(".ci", "scripts", "quality", "check_bws_map_live.py")
MAP = paths.from_root(".ci", "config", "bws-secret-map.json")
SENTINEL = "SENTINEL-VALUE-from-the-fake-store-91c2"

FAKE = """#!%(python)s
import json, sys
argv = sys.argv[1:]
if argv[:2] != ["--color", "no"] or %(project)r not in argv:
    sys.stderr.write("fake bws: unexpected argv %%r\\n" %% (argv,))
    sys.exit(3)
rows = json.loads(open(%(rows)r).read())
for r in rows:
    r["value"] = %(sentinel)r
sys.stdout.write(json.dumps(rows))
"""


def _fake_store(tmp_path: pathlib.Path, *, drop: str = "", move: str = "", add: str = "") -> str:
    doc = json.loads(MAP.read_text(encoding="utf-8"))
    project = doc["project"]
    rows = [
        {"id": v["id"], "key": k, "projectId": project}
        for k, v in doc["secrets"].items()
        if k != drop
    ]
    for r in rows:
        if r["key"] == move:
            r["id"] = "00000000-0000-4000-8000-000000000000"
    if add:
        rows.append(
            {"id": "00000000-0000-4000-8000-000000000001", "key": add, "projectId": project}
        )
    data = tmp_path / "rows.json"
    data.write_text(json.dumps(rows), encoding="utf-8")
    fake = tmp_path / "bws"
    fake.write_text(
        FAKE
        % {"python": sys.executable, "project": project, "rows": str(data), "sentinel": SENTINEL},
        encoding="utf-8",
    )
    fake.chmod(0o700)
    return str(fake)


def _gate(env: dict[str, str]) -> harness.RunResult:
    return harness.run([sys.executable, str(GATE)], cwd=paths.repo_root(), env=env)


def _names() -> list[str]:
    return sorted(json.loads(MAP.read_text(encoding="utf-8"))["secrets"])


def test_selftest_passes():
    result = harness.run([sys.executable, str(GATE), "--selftest"], cwd=paths.repo_root())
    assert result.rc == 0, result.combined
    assert "control(s) ran" in result.out


def test_a_store_that_backs_the_map_passes_and_prints_no_value(tmp_path):
    result = _gate({"BWS_BIN": _fake_store(tmp_path), "BWS_ACCESS_TOKEN": "fake"})
    assert result.rc == 0, result.combined
    assert "0 lingering, 0 moved" in result.err
    assert SENTINEL not in result.combined


def test_a_mapped_name_deleted_from_the_store_lingers(tmp_path):
    gone = _names()[0]
    result = _gate({"BWS_BIN": _fake_store(tmp_path, drop=gone), "BWS_ACCESS_TOKEN": "fake"})
    assert result.rc == 1, result.combined
    assert "LINGERING %s is in .ci/config/bws-secret-map.json" % gone in result.err
    assert SENTINEL not in result.combined


def test_a_name_recreated_under_a_new_uuid_is_moved(tmp_path):
    moved = _names()[1]
    result = _gate({"BWS_BIN": _fake_store(tmp_path, move=moved), "BWS_ACCESS_TOKEN": "fake"})
    assert result.rc == 1, result.combined
    assert "MOVED %s" % moved in result.err


def test_a_store_only_name_is_reported_not_refused(tmp_path):
    result = _gate(
        {"BWS_BIN": _fake_store(tmp_path, add="ZZ_FIXTURE_ONLY"), "BWS_ACCESS_TOKEN": "fake"}
    )
    assert result.rc == 0, result.combined
    assert "STORE-ONLY ZZ_FIXTURE_ONLY" in result.err


def test_no_token_cannot_run(tmp_path):
    """No token is 77 whether or not a CLI is installed, because the token is what is missing either way."""
    empty = tmp_path / "bin"
    empty.mkdir()
    env = {
        "HOME": str(tmp_path),
        "PATH": str(empty),
        "XDG_CONFIG_HOME": str(tmp_path / "xdg"),
        "BWS_ACCESS_TOKEN": "",
        "BWS_ACCESS_TOKEN_FILE": "",
        "BWS_BIN": "",
    }
    result = _gate(env)
    assert result.rc == 77, result.combined
    assert "SKIP, CANNOT RUN here: missing a BWS token" in result.err
    assert "NOT compared" in result.err


def test_a_failing_bws_with_a_token_is_a_failure_not_a_skip(tmp_path):
    fake = tmp_path / "bws"
    fake.write_text(
        "#!%s\nimport sys\nsys.stdout.write(%r)\nsys.stderr.write('Error: [401 Unauthorized]\\n')\nsys.exit(1)\n"
        % (sys.executable, SENTINEL),
        encoding="utf-8",
    )
    fake.chmod(0o700)
    result = _gate({"BWS_BIN": str(fake), "BWS_ACCESS_TOKEN": "fake"})
    assert result.rc == 1, result.combined
    assert "nothing was compared" in result.err
    assert SENTINEL not in result.combined
