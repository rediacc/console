"""`bws_env park NAME...` renames a retired store entry to `__NAME`, keeping its id and value, and never shows the value to argv or a stream.

WHY THIS VERB EXISTS. agent/plans/PLAN-production-key-only.md retires the six ACCOUNT_*_DEV entries by parking them (Design 5, Decision D4): a rename rather than a delete, so the value stays recoverable, done by a tested verb rather than a one-off script so the read-back and the never-print rule are pinned.

METHOD, shared with `test_core_bws_env_store.py`. Both programs the verb can reach are faked on a scrubbed PATH: a `bws` that lists a JSON store file and a writer (`npx`) that edits it the way bws-write.ts does (key, value, note and project replaced together, keyed by id). Each fake logs its argv, and the writer its stdin, so the test asserts the value travels on stdin only. No live store is touched.
"""

import json
import stat

from rediacc_ci.core import bws_env
from rediacc_ci.tests import differential as diff
from rediacc_ci.tests.test_core_bws_env_store import carries_secret

VALUE = "SENTINEL-PARK-VALUE-4f1c9a"
OTHER_VALUE = "SENTINEL-PARK-OTHER-77e0b2"
ENTRY_ID = "c0ffee00-0000-4000-8000-0000000000a1"
OTHER_ID = "c0ffee00-0000-4000-8000-0000000000a2"
PROJECT = "proj-ci-shared-fixture"

FAKE_BWS = r"""#!/usr/bin/env python3
import json, os, sys
root = os.environ["FIXTURE_ROOT"]
with open(os.path.join(root, "spawn.log"), "a") as log:
    log.write(json.dumps({"prog": "bws", "argv": sys.argv}) + "\n")
if "--color" not in sys.argv:
    sys.exit(3)
if sys.argv[1:3] != ["secret", "list"]:
    print("fake bws: only `secret list` is served", file=sys.stderr)
    sys.exit(4)
print(open(os.path.join(root, "store.json")).read())
"""

# The writer edits by id and replaces key, value, note and project together, which is bws-write.ts's documented contract. FAKE_WRITER_CORRUPT makes it store a different value, so the read-back's MISMATCH arm is exercised.
FAKE_NPX = r"""#!/usr/bin/env python3
import json, os, sys
root = os.environ["FIXTURE_ROOT"]
stdin = sys.stdin.read()
with open(os.path.join(root, "spawn.log"), "a") as log:
    log.write(json.dumps({"prog": "npx", "argv": sys.argv, "cwd": os.getcwd(), "stdin": stdin}) + "\n")
req = json.loads(stdin)
path = os.path.join(root, "store.json")
rows = json.load(open(path))
value = req["value"] + "-corrupted" if os.environ.get("FAKE_WRITER_CORRUPT") else req["value"]
for row in rows:
    if row["id"] == req["id"]:
        row.update(key=req["key"], value=value, note=req["note"], projectId=req["projectIds"][0])
json.dump(rows, open(path, "w"))
print(req["id"])
"""


def _exe(path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


def _fixture(root, rows: list[dict] | None = None):
    (root / "bin").mkdir(parents=True)
    _exe(root / "bin" / "bws", FAKE_BWS)
    _exe(root / "bin" / "npx", FAKE_NPX)
    if rows is None:
        rows = [
            {
                "id": ENTRY_ID,
                "key": "DEMO_KEY_DEV",
                "value": VALUE,
                "note": "kept note",
                "projectId": PROJECT,
            },
            {
                "id": OTHER_ID,
                "key": "OTHER_KEY_DEV",
                "value": OTHER_VALUE,
                "note": "",
                "projectId": PROJECT,
            },
            {"id": "live", "key": "DEMO_KEY", "value": "live-v", "note": "", "projectId": PROJECT},
        ]
    (root / "store.json").write_text(json.dumps(rows), encoding="utf-8")
    script = root / "private" / "account" / bws_env.WRITER_SCRIPT_REL
    script.parent.mkdir(parents=True)
    script.write_text("// stand-in; the fake npx on PATH answers\n", encoding="utf-8")
    return root


def _run(root, *names: str, extra: dict | None = None) -> tuple[int, str, str]:
    env = diff.env_for(
        PATH="%s:/usr/local/bin:/usr/bin:/bin" % (root / "bin"),
        BWS_ENV_ROOT=str(root),
        XDG_CONFIG_HOME=str(root / "xdg"),
        BWS_ACCESS_TOKEN="fixture-token-not-a-credential",
        FIXTURE_ROOT=str(root),
        **(extra or {}),
    )
    args = " ".join("'%s'" % n for n in names)
    return diff.bash_streams(
        "PYTHONPATH=.ci python3 -m rediacc_ci.core.bws_env park %s" % args, env=env
    )


def _spawns(root) -> list[dict]:
    log = root / "spawn.log"
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]


def _store(root) -> dict[str, dict]:
    return {r["id"]: r for r in json.loads((root / "store.json").read_text(encoding="utf-8"))}


def test_park_renames_by_id_keeps_the_value_and_reads_back(tmp_path) -> None:
    root = _fixture(tmp_path / "ok")
    code, out, err = _run(root, "DEMO_KEY_DEV", "OTHER_KEY_DEV")
    assert code == 0, err
    assert out == "DEMO_KEY_DEV -> __DEMO_KEY_DEV MATCH\nOTHER_KEY_DEV -> __OTHER_KEY_DEV MATCH\n"
    spawns = _spawns(root)
    assert [s["prog"] for s in spawns] == ["bws", "npx", "npx", "bws"], "list, 2 writes, read back"
    for s in spawns:
        for secret in (VALUE, OTHER_VALUE):
            assert not carries_secret(" ".join(s["argv"]), secret), s["argv"]
    assert spawns[1]["argv"][1:] == list(bws_env.WRITER_ARGV[1:])
    assert spawns[1]["cwd"] == str(root / "private" / "account")
    assert json.loads(spawns[1]["stdin"]) == {
        "op": "edit",
        "id": ENTRY_ID,
        "key": "__DEMO_KEY_DEV",
        "value": VALUE,
        "note": "kept note",
        "projectIds": [PROJECT],
    }, "a rename is an edit with the new key, the same id and the unchanged value"
    for stream in (out, err):
        for secret in (VALUE, OTHER_VALUE):
            assert not carries_secret(stream, secret)
    store = _store(root)
    assert (store[ENTRY_ID]["key"], store[ENTRY_ID]["value"]) == ("__DEMO_KEY_DEV", VALUE)
    assert (store[OTHER_ID]["key"], store[OTHER_ID]["value"]) == ("__OTHER_KEY_DEV", OTHER_VALUE)
    assert store["live"]["key"] == "DEMO_KEY", "the live entry is untouched"


def test_park_refuses_an_already_parked_argument_before_any_write(tmp_path) -> None:
    root = _fixture(tmp_path / "parkedarg")
    code, out, err = _run(root, "__DEMO_KEY_DEV")
    assert (code, out) == (1, "")
    assert "__DEMO_KEY_DEV is already a parked name" in err
    assert "nothing was written" in err
    assert [s["prog"] for s in _spawns(root)] == ["bws"], "no writer was started"


def test_park_refuses_an_absent_name_and_writes_none_of_the_others(tmp_path) -> None:
    root = _fixture(tmp_path / "absent")
    code, out, err = _run(root, "DEMO_KEY_DEV", "NOT_IN_STORE")
    assert (code, out) == (1, "")
    assert "NOT_IN_STORE is absent in the store" in err
    assert [s["prog"] for s in _spawns(root)] == ["bws"], "a refused name stops every write"
    assert _store(root)[ENTRY_ID]["key"] == "DEMO_KEY_DEV"


def test_park_refuses_a_name_whose_parked_twin_exists(tmp_path) -> None:
    """Already parked once: `__NAME` is in the store, so a second park would leave two entries claiming the parked name."""
    rows = [
        {"id": ENTRY_ID, "key": "DEMO_KEY_DEV", "value": VALUE, "note": "", "projectId": PROJECT},
        {"id": OTHER_ID, "key": "__DEMO_KEY_DEV", "value": "x", "note": "", "projectId": PROJECT},
    ]
    root = _fixture(tmp_path / "twin", rows)
    code, _out, err = _run(root, "DEMO_KEY_DEV")
    assert code == 1
    assert "__DEMO_KEY_DEV already exists in the store" in err
    assert [s["prog"] for s in _spawns(root)] == ["bws"]


def test_park_reports_mismatch_when_the_value_did_not_survive(tmp_path) -> None:
    """The read-back's failing arm: the writer renamed the entry but stored another value, so the verdict is MISMATCH and rc 1, with no value printed."""
    root = _fixture(tmp_path / "corrupt")
    code, out, err = _run(root, "DEMO_KEY_DEV", extra={"FAKE_WRITER_CORRUPT": "1"})
    assert code == 1
    assert out == "DEMO_KEY_DEV -> __DEMO_KEY_DEV MISMATCH\n"
    assert not carries_secret(out + err, VALUE)


def test_park_verdicts_need_the_same_id_the_new_key_the_old_value_and_no_live_name() -> None:
    """Pure: each of the three MATCH conditions failing alone gives MISMATCH. Control: all three hold."""
    before = {"A": {"id": "1", "key": "A", "value": "v"}}
    good = [{"id": "1", "key": "__A", "value": "v"}]
    assert bws_env.park_verdicts(["A"], before, good) == [("A", bws_env.MATCH)]
    for rows in (
        [{"id": "2", "key": "__A", "value": "v"}],
        [{"id": "1", "key": "A", "value": "v"}],
        [{"id": "1", "key": "__A", "value": "w"}],
        [*good, {"id": "9", "key": "A", "value": "v"}],
    ):
        assert bws_env.park_verdicts(["A"], before, rows) == [("A", bws_env.MISMATCH)], rows


def test_park_preflight_names_every_problem() -> None:
    rows = [{"key": "A"}, {"key": "B"}, {"key": "__B"}, {"key": "D"}, {"key": "D"}]
    problems = bws_env.park_preflight(["A", "__A", "B", "C", "D", "x>y", "A"], rows)
    text = "\n".join(problems)
    assert "__A is already a parked name" in text
    assert "__B already exists in the store" in text
    assert "C is absent in the store" in text
    assert "D is duplicated in the store" in text
    assert "'x>y' is not a store name" in text
    assert "named more than once: A" in text
    assert bws_env.park_preflight(["A"], rows) == [], "the control: a clean live name passes"


def test_park_is_reachable_and_listed() -> None:
    assert "park NAME" in bws_env.USAGE.split("There is deliberately")[0]
    assert bws_env.main(["park"]) == 2, "no NAME is a usage error, before any store access"
