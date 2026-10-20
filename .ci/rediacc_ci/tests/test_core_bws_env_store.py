"""`bws_env store-from-env` writes a value without ever putting it on a spawned argv.

THE DEFECT PINNED HERE. The verb used to run `bws secret edit --value <VALUE> <ID>`: bws 2.1.0 takes a value on argv only, and argv is world-readable through /proc/<pid>/cmdline for the life of the call. `./run.sh account reset` pushed the freshly minted DEV private keys that way. The write now goes through `private/account/scripts/rotation/bws-write.ts` with the request on STDIN.

METHOD. Both programs the verb can reach are faked on a scrubbed PATH, and each fake appends the argv it was started with (and, for the writer, its cwd and stdin) to one log. The store is a JSON file the fake `bws` lists and the fake writer edits, so the verb's own read-back is exercised for real. The assertion is that no logged argv carries the value, verbatim or inside any base64 run, and a positive control proves that check fires on the old argv shape.

The writer's REST protocol and its round trip against a fake Secrets Manager are tested where the writer lives: `private/account/tests/integration/rotation-bws-write.test.ts`.
"""

import base64
import binascii
import json
import re
import shlex
import stat
import time

from rediacc_ci.core import bws_env
from rediacc_ci.tests import differential as diff

VALUE = "SENTINEL-STORE-FROM-ENV-9d2b7e"
ENTRY_ID = "c0ffee00-0000-4000-8000-000000000001"
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

FAKE_NPX = r"""#!/usr/bin/env python3
import json, os, sys
root = os.environ["FIXTURE_ROOT"]
stdin = sys.stdin.read()
with open(os.path.join(root, "spawn.log"), "a") as log:
    log.write(json.dumps({"prog": "npx", "argv": sys.argv, "cwd": os.getcwd(), "stdin": stdin}) + "\n")
if os.environ.get("FAKE_WRITER_FAIL"):
    print("bws-api: edit x failed (HTTP 500): fake", file=sys.stderr)
    sys.exit(1)
req = json.loads(stdin)
path = os.path.join(root, "store.json")
rows = json.load(open(path))
for row in rows:
    if row["id"] == req["id"]:
        row.update(key=req["key"], value=req["value"], note=req["note"], projectId=req["projectIds"][0])
json.dump(rows, open(path, "w"))
print(req["id"])
"""


def _exe(path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


def _fixture(root, *, with_writer: bool = True):
    (root / "bin").mkdir(parents=True)
    _exe(root / "bin" / "bws", FAKE_BWS)
    _exe(root / "bin" / "npx", FAKE_NPX)
    rows = [
        {
            "id": ENTRY_ID,
            "key": "DEMO_KEY_DEV",
            "value": "old-value",
            "note": "kept note",
            "projectId": PROJECT,
            "organizationId": "org",
        },
        {"id": "other", "key": "UNTOUCHED", "value": "u", "note": "", "projectId": PROJECT},
    ]
    (root / "store.json").write_text(json.dumps(rows), encoding="utf-8")
    if with_writer:
        script = root / "private" / "account" / bws_env.WRITER_SCRIPT_REL
        script.parent.mkdir(parents=True)
        script.write_text("// stand-in; the fake npx on PATH answers\n", encoding="utf-8")
    return root


def _run(root, *, extra: dict | None = None) -> tuple[int, str, str]:
    env = diff.env_for(
        PATH="%s:/usr/local/bin:/usr/bin:/bin" % (root / "bin"),
        BWS_ENV_ROOT=str(root),
        XDG_CONFIG_HOME=str(root / "xdg"),
        BWS_ACCESS_TOKEN="fixture-token-not-a-credential",
        FIXTURE_ROOT=str(root),
        DEMO_KEY=VALUE,
        **(extra or {}),
    )
    return diff.bash_streams(
        "PYTHONPATH=.ci python3 -m rediacc_ci.core.bws_env store-from-env 'DEMO_KEY_DEV > DEMO_KEY'",
        env=env,
    )


def _spawns(root) -> list[dict]:
    log = root / "spawn.log"
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]


def carries_secret(text: str, secret: str) -> bool:
    """The secret verbatim, or inside any base64 run at any of the four alignments."""
    if secret in text:
        return True
    needle = secret.encode("utf-8")
    for run in re.findall(r"[A-Za-z0-9+/_-]{8,}", text):
        for offset in range(4):
            chunk = run[offset:]
            # Pad a tail of 2 or 3 symbols back into a quantum; a lone trailing symbol carries no byte.
            chunk = chunk[:-1] if len(chunk) % 4 == 1 else chunk + "=" * (-len(chunk) % 4)
            for decode in (base64.b64decode, base64.urlsafe_b64decode):
                try:
                    if needle in decode(chunk):
                        return True
                except (binascii.Error, ValueError):
                    continue
    return False


def test_the_check_fires_on_the_old_argv_shape() -> None:
    """Positive control: the shape this file exists to forbid is caught, plain and base64'd."""
    old = ["bws", "secret", "edit", "--value", VALUE, "--output", "none", ENTRY_ID]
    assert carries_secret(" ".join(old), VALUE)
    for pad in ("", "a", "ab"):
        wrapped = base64.b64encode((pad + VALUE).encode()).decode()
        assert carries_secret("echo %s | base64 -d" % wrapped, VALUE)
    assert not carries_secret(" ".join(bws_env.WRITER_ARGV), VALUE)


def test_store_from_env_writes_through_stdin_and_reads_back(tmp_path) -> None:
    root = _fixture(tmp_path / "ok")
    code, out, err = _run(root)
    assert (code, out) == (0, "DEMO_KEY MATCH\n"), err
    spawns = _spawns(root)
    assert [s["prog"] for s in spawns] == ["bws", "npx", "bws"], "list, write, read back"
    for s in spawns:
        assert not carries_secret(" ".join(s["argv"]), VALUE), s["argv"]
    writer = spawns[1]
    assert writer["argv"][1:] == list(bws_env.WRITER_ARGV[1:])
    assert writer["cwd"] == str(root / "private" / "account")
    request = json.loads(writer["stdin"])
    assert request == {
        "op": "edit",
        "id": ENTRY_ID,
        "key": "DEMO_KEY_DEV",
        "value": VALUE,
        "note": "kept note",
        "projectIds": [PROJECT],
    }, "the REST edit replaces key, note and project, so the listed ones are sent back"
    for stream in (out, err):
        assert not carries_secret(stream, VALUE)
    rows = {r["key"]: r for r in json.loads((root / "store.json").read_text(encoding="utf-8"))}
    assert rows["UNTOUCHED"]["value"] == "u"


def test_a_failed_write_is_refused_without_the_value(tmp_path) -> None:
    root = _fixture(tmp_path / "fail")
    code, out, err = _run(root, extra={"FAKE_WRITER_FAIL": "1"})
    assert code == 1
    assert out == ""
    assert "editing DEMO_KEY_DEV failed (rc=1: the writer failed; its stderr is withheld" in err
    assert "HTTP 500" not in err
    assert not carries_secret(err, VALUE)
    assert [s["prog"] for s in _spawns(root)] == ["bws", "npx"], "no read-back after a failure"


def test_a_missing_writer_is_refused_before_any_write(tmp_path) -> None:
    root = _fixture(tmp_path / "nowriter", with_writer=False)
    code, _out, err = _run(root)
    assert code == 1
    assert "the private/account submodule is needed to write" in err
    assert [s["prog"] for s in _spawns(root)] == ["bws"]


def test_write_secret_refuses_an_answer_that_is_not_the_id(tmp_path) -> None:
    root = _fixture(tmp_path / "id")
    (root / "bin" / "npx").write_text(
        "#!/bin/sh\ncat >/dev/null\necho something-else\n", encoding="utf-8"
    )
    env = diff.env_for(PATH="%s:/usr/bin:/bin" % (root / "bin"))
    failure = bws_env.write_secret(str(root), {"op": "edit", "id": ENTRY_ID, "value": VALUE}, env)
    assert failure == "the writer answered an unexpected id"


def _write_with_fake_npx(tmp_path, name: str, script: str, request: dict) -> str | None:
    root = _fixture(tmp_path / name)
    (root / "bin" / "npx").write_text(script, encoding="utf-8")
    env = diff.env_for(PATH="%s:/usr/bin:/bin" % (root / "bin"))
    return bws_env.write_secret(str(root), request, env)


def test_write_secret_never_relays_the_writers_stderr(tmp_path) -> None:
    for name, value, echo in (
        ("whole", VALUE, VALUE),
        ("multiline", "first-line-secret\nsecond-line-secret", "second-line-secret"),
        ("short", "zq7\n", "zq7"),
        ("prefix", "a-long-secret-value-here", "a-long-se"),
    ):
        failure = _write_with_fake_npx(
            tmp_path,
            name,
            '#!/bin/sh\ncat >/dev/null\necho "bad: %s" >&2\nexit 1\n' % echo,
            {"op": "edit", "id": ENTRY_ID, "value": value},
        )
        assert failure is not None
        assert failure.startswith("rc=1: ")
        assert echo not in failure
        assert "withheld" in failure
        hint = "run `cd %s && npx --no tsx scripts/rotation/bws-write.ts`"
        assert hint % shlex.quote(str(tmp_path / name)) in failure


def test_write_secret_hint_quotes_a_directory_with_spaces(tmp_path) -> None:
    failure = _write_with_fake_npx(
        tmp_path,
        "dir with space",
        "#!/bin/sh\ncat >/dev/null\nexit 1\n",
        {"op": "edit", "id": ENTRY_ID, "value": VALUE},
    )
    assert failure is not None
    assert "cd '%s' && " % (tmp_path / "dir with space") in failure


def test_write_secret_survives_non_utf8_output(tmp_path) -> None:
    failure = _write_with_fake_npx(
        tmp_path,
        "binary",
        "#!/bin/sh\ncat >/dev/null\nprintf '\\377\\376' >&2\nexit 1\n",
        {"op": "edit", "id": ENTRY_ID, "value": VALUE},
    )
    assert failure is not None
    assert failure.startswith("rc=1")


def test_write_secret_refuses_a_request_without_an_id(tmp_path) -> None:
    failure = _write_with_fake_npx(
        tmp_path,
        "noid",
        "#!/bin/sh\ncat >/dev/null\necho anything\n",
        {"op": "edit", "value": VALUE},
    )
    assert failure == "the writer answered an unexpected id"


def test_write_secret_timeout_kills_the_writer_group(tmp_path, monkeypatch) -> None:
    marker = tmp_path / "late-write"
    monkeypatch.setattr(bws_env, "WRITER_TIMEOUT_S", 1)
    failure = _write_with_fake_npx(
        tmp_path,
        "slow",
        "#!/bin/sh\ncat >/dev/null\n(sleep 3; echo late > %s) &\nwait\n" % marker,
        {"op": "edit", "id": ENTRY_ID, "value": VALUE},
    )
    assert failure == "cannot run npx: TimeoutExpired"
    time.sleep(3.5)
    assert not marker.exists(), "the grandchild outlived the timeout and wrote late"
