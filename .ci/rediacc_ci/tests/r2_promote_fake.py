"""A recording fake bucket for the two server-side release promotes (`deploy/r2_promote.py`).

NOTHING HERE REACHES R2 OR CLOUDFLARE. `aws` and `curl` are fakes first on a scratch PATH, every run pins a fixture endpoint and credential, and the bucket is a directory tree. The fake models the four aws calls the promotes make (`s3api list-objects-v2`, `s3api copy-object`, `s3 cp` of one object in either direction) and REFUSES a high-level s3-to-s3 `aws s3 cp/sync` the way R2 does (`NotImplemented` on `x-amz-tagging-directive`), so a regression to that form fails here as it would in production.

EVERY EFFECT IS ONE JSON LINE in the call log, written with one `write()` so parallel copies cannot interleave inside a record: `{"argv": [...]}` per invocation, then `{"op": "GET"|"PUT"|"COPY", "key": ..., "src": ..., "content": ...}` per object moved. Records land in COMPLETION order, which is what the phase and pointer ordering assertions read.

Knobs (environment of the run): `FAKE_AWS_RC` fails every call with `FAKE_AWS_STDERR` (default AccessDenied); `FAKE_AWS_DENY_MATCH` fails with AccessDenied any call naming that substring; `FAKE_AWS_FLAKY_MATCH` fails transiently the first `FAKE_AWS_FLAKY_TIMES` calls naming it; `FAKE_AWS_DROP_COPY_MATCH` makes a matching copy-object report success without writing; `FAKE_AWS_SIZE_OVERRIDE` (`key=bytes`) lies about one object's listed size.

The port runs through `DRIVER`, which can substitute a PLANTED copy of `r2_promote.py` for the real one: that is how the mutation controls prove the contract tests can fail.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import typing

from rediacc_ci import paths

if typing.TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()
CI = ROOT / ".ci"
R2_PROMOTE = CI / "rediacc_ci" / "deploy" / "r2_promote.py"
BUCKET = "rediacc-releases"

# Every fixture object's LastModified. Copies and puts stamp "now", so a stable object written by a run is newer than its edge source.
T0 = 1_700_000_000

# What aws printed on 2026-09-24 when a large .deb broke mid-read: the transient class the retry exists for.
INCOMPLETE_READ = (
    "download failed: s3://rediacc-releases/apt/edge/pool/x.deb to /tmp/x.deb "
    "('Connection broken: IncompleteRead(7540288 bytes read, 848320 more expected)', "
    "IncompleteRead(7540288 bytes read, 848320 more expected))\n"
)

FAKE_AWS = r"""#!/usr/bin/env python3
import datetime
import fcntl
import json
import os
import shutil
import sys
import time

argv = sys.argv[1:]
log = os.environ["FAKE_CALL_LOG"]
root = os.environ["FAKE_S3_ROOT"]
env = os.environ


def emit(record):
    line = json.dumps(record) + "\n"
    fd = os.open(log, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
    try:
        os.write(fd, line.encode("utf-8"))
    finally:
        os.close(fd)


def fail(stderr, rc=1):
    sys.stderr.write(stderr)
    sys.exit(rc)


emit({"argv": argv})
joined = "\t".join(argv)
denied = "fatal error: An error occurred (AccessDenied) when calling the operation: Access Denied\n"
if int(env.get("FAKE_AWS_RC", "0") or "0"):
    fail(env.get("FAKE_AWS_STDERR", denied), int(env["FAKE_AWS_RC"]))
if env.get("FAKE_AWS_DENY_MATCH") and env["FAKE_AWS_DENY_MATCH"] in joined:
    fail(denied)
flaky = env.get("FAKE_AWS_FLAKY_MATCH", "")
if flaky and flaky in joined:
    counter = env["FAKE_AWS_FLAKY_COUNTER"]
    with open(counter, "a+") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        fh.seek(0)
        done = len(fh.read())
        if done < int(env.get("FAKE_AWS_FLAKY_TIMES", "1")):
            fh.write("x")
            fh.flush()
            fail("An error occurred (InternalError): We encountered an internal error. Please try again.\n")


def opt(name):
    return argv[argv.index(name) + 1] if name in argv else None


def path_of(bucket_key):
    return os.path.join(root, bucket_key)


def body(path):
    with open(path, encoding="utf-8", errors="replace") as fh:
        return fh.read()


def touch_now(path):
    now = time.time()
    os.utime(path, (now, now))


service, verb = argv[0], argv[1]
if service == "s3api" and verb == "list-objects-v2":
    bucket, prefix = opt("--bucket"), opt("--prefix")
    base = path_of(bucket)
    sizes = dict(item.split("=", 1) for item in env.get("FAKE_AWS_SIZE_OVERRIDE", "").split(",") if item)
    contents = []
    for dirpath, _dirs, files in os.walk(base):
        for name in files:
            full = os.path.join(dirpath, name)
            key = os.path.relpath(full, base)
            if key.startswith(prefix):
                stamp = datetime.datetime.fromtimestamp(os.stat(full).st_mtime, datetime.timezone.utc)
                contents.append({
                    "Key": key,
                    "Size": int(sizes.get(key, os.stat(full).st_size)),
                    "LastModified": stamp.strftime("%Y-%m-%dT%H:%M:%S.") + "%03dZ" % (stamp.microsecond // 1000),
                })
    contents.sort(key=lambda item: item["Key"])
    reply = {"Contents": contents, "Prefix": prefix} if contents else {"Prefix": prefix}
    print(json.dumps(reply))
    sys.exit(0)

if service == "s3api" and verb == "copy-object":
    bucket, key, source = opt("--bucket"), opt("--key"), opt("--copy-source")
    src_path = path_of(source)
    if not os.path.isfile(src_path):
        fail("An error occurred (NoSuchKey) when calling the CopyObject operation\n", 254)
    drop = env.get("FAKE_AWS_DROP_COPY_MATCH", "")
    if not (drop and drop in key):
        dst = path_of(bucket + "/" + key)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copyfile(src_path, dst)
        touch_now(dst)
    emit({"op": "COPY", "key": bucket + "/" + key, "src": source, "content": body(src_path),
          "cache_control": opt("--cache-control"), "content_type": opt("--content-type"),
          "directive": opt("--metadata-directive")})
    print(json.dumps({"CopyObjectResult": {"ETag": "\"fake\""}}))
    sys.exit(0)

if service == "s3" and verb in ("cp", "sync", "mv"):
    positional = []
    skip = False
    for i, a in enumerate(argv[2:], start=2):
        if skip:
            skip = False
            continue
        if a in ("--endpoint-url", "--cache-control", "--exclude", "--include", "--content-type", "--copy-props", "--metadata-directive"):
            skip = True
            continue
        if not a.startswith("-"):
            positional.append(a)
    src, dst = positional[0], positional[1]
    if src.startswith("s3://") and dst.startswith("s3://"):
        # WHAT R2 ANSWERS (simulate-promotion.sh, CI run 32465461193).
        fail("An error occurred (NotImplemented) when calling the CopyObject operation: Header "
             "'x-amz-tagging-directive' with value 'REPLACE' not implemented\n", 1)
    if verb != "cp" or "--recursive" in argv:
        fail("fake aws: only single-object `s3 cp` is modelled, got %r\n" % argv, 2)
    if src.startswith("s3://"):
        src_path = path_of(src[5:])
        if not os.path.isfile(src_path):
            fail("fatal error: An error occurred (404) when calling the HeadObject operation: Key not found\n")
        os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
        shutil.copyfile(src_path, dst)
        emit({"op": "GET", "key": src[5:]})
        sys.exit(0)
    dst_path = path_of(dst[5:])
    os.makedirs(os.path.dirname(dst_path), exist_ok=True)
    shutil.copyfile(src, dst_path)
    touch_now(dst_path)
    emit({"op": "PUT", "key": dst[5:], "content": body(src), "cache_control": opt("--cache-control")})
    sys.exit(0)

fail("fake aws: unmodelled call %r\n" % argv, 2)
"""

FAKE_CURL = """#!/usr/bin/env python3
import json
import os
import sys

line = json.dumps({"curl": sys.argv[1:]}) + "\\n"
fd = os.open(os.environ["FAKE_CALL_LOG"], os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
os.write(fd, line.encode("utf-8"))
os.close(fd)
sys.stdout.write(json.dumps({"success": True, "errors": []}) + "\\n")
"""

# Runs a port module as `__main__`, optionally with a planted `r2_promote.py` registered in its place first (`FAKE_PLANT_R2_PROMOTE`), or a planted copy of the port itself (`FAKE_PLANT_PORT`; its purge script path then resolves beside the plant, so only the transfer log of such a run means anything).
DRIVER = """
import importlib.util, os, runpy, sys
sys.path.insert(0, sys.argv[1])
plant = os.environ.get("FAKE_PLANT_R2_PROMOTE", "")
if plant:
    import rediacc_ci.deploy as deploy
    spec = importlib.util.spec_from_file_location("rediacc_ci.deploy.r2_promote", plant)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    deploy.r2_promote = module
port = os.environ.get("FAKE_PLANT_PORT", "")
sys.argv = [sys.argv[2]]
if port:
    runpy.run_path(port, run_name="__main__")
else:
    runpy.run_module(sys.argv[0], run_name="__main__")
"""

PATH_MINIMUM = (
    "jq",
    "uname",
    "dirname",
    "basename",
    "tr",
    "find",
    "wc",
    "sed",
    "rm",
    "cat",
    "mktemp",
    "env",
    "python3",
)


def stub_bin(root: pathlib.Path, *, drop: str = "") -> str:
    """A PATH holding the fakes and the few real tools the purge script needs."""
    stub = root / "fixture-bin"
    stub.mkdir(parents=True, exist_ok=True)
    for real_name in PATH_MINIMUM:
        real = shutil.which(real_name)
        link = stub / real_name
        if real is not None and not link.exists():
            link.symlink_to(real)
    for name, text in (("aws", FAKE_AWS), ("curl", FAKE_CURL)):
        script = stub / name
        if name == drop:
            if script.exists():
                script.unlink()
            continue
        script.write_text(text, encoding="utf-8")
        script.chmod(0o755)
    return str(stub)


def make_bucket(root: pathlib.Path, objects: dict[str, str]) -> pathlib.Path:
    """The fake S3 root: `<root>/s3/<bucket>/<key>`, every object stamped `T0`."""
    base = root / "s3" / BUCKET
    base.mkdir(parents=True, exist_ok=True)
    for key, text in objects.items():
        target = base / key
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        os.utime(target, (T0, T0))
    return root / "s3"


def run_port(
    root: pathlib.Path,
    module: str,
    base_env: dict[str, str],
    home: str,
    *,
    plant: str = "",
    plant_port: str = "",
    drop: str = "",
    drop_env: tuple[str, ...] = (),
    extra: dict[str, str] | None = None,
) -> tuple[subprocess.CompletedProcess[str], list[dict[str, typing.Any]]]:
    """Run `module` against the fixture bucket under `root`. Returns the process and the parsed call log."""
    call_log = root / "calls.jsonl"
    call_log.write_text("", encoding="utf-8")
    env = {
        "PATH": stub_bin(root, drop=drop),
        "HOME": home,
        "LC_ALL": "C.UTF-8",
        "LANG": "C.UTF-8",
        "PYTHONDONTWRITEBYTECODE": "1",
        "FAKE_CALL_LOG": str(call_log),
        "FAKE_S3_ROOT": str(root / "s3"),
        "FAKE_AWS_FLAKY_COUNTER": str(root / "flaky.count"),
        "PROMOTE_RETRY_DELAY_S": "0",
        **base_env,
    }
    if plant:
        env["FAKE_PLANT_R2_PROMOTE"] = plant
    if plant_port:
        env["FAKE_PLANT_PORT"] = plant_port
    env.update(extra or {})
    for name in drop_env:
        env.pop(name, None)
    proc = subprocess.run(
        [sys.executable, "-c", DRIVER, str(CI), module],
        cwd=str(root),
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=180,
        input="",
    )
    records = [
        json.loads(line) for line in call_log.read_text(encoding="utf-8").splitlines() if line
    ]
    return proc, records


def plant(tmp_path: pathlib.Path, old: str, new: str) -> str:
    """A copy of `r2_promote.py` with `old` replaced by `new` exactly once. Asserts the plant applied, so a stale control fails as a broken control rather than passing."""
    source = R2_PROMOTE.read_text(encoding="utf-8")
    if source.count(old) != 1:
        raise AssertionError(
            "the plant did not apply; the control is broken, not the test: %r" % old
        )
    target = tmp_path / "planted_r2_promote.py"
    target.write_text(source.replace(old, new, 1), encoding="utf-8")
    return str(target)


def aws_calls(records: list[dict[str, typing.Any]]) -> list[list[str]]:
    return [r["argv"] for r in records if "argv" in r]


def ops(records: list[dict[str, typing.Any]], op: str) -> list[dict[str, typing.Any]]:
    return [r for r in records if r.get("op") == op]


def purge_urls(records: list[dict[str, typing.Any]]) -> list[str]:
    for r in records:
        if "curl" in r and "--data" in r["curl"]:
            argv = r["curl"]
            return list(json.loads(argv[argv.index("--data") + 1])["files"])
    return []


def curl_calls(records: list[dict[str, typing.Any]]) -> int:
    return len([r for r in records if "curl" in r])


def bucket_keys(root: pathlib.Path, prefix: str) -> dict[str, str]:
    """Every object in the fixture bucket after a run whose `<bucket>/<key>` starts with `prefix`, as `<bucket>/<key>` -> body."""
    base = root / "s3" / BUCKET
    found = {}
    for dirpath, _dirs, files in os.walk(base):
        for name in files:
            full = os.path.join(dirpath, name)
            key = "%s/%s" % (BUCKET, os.path.relpath(full, base))
            if key.startswith(prefix):
                with open(full, encoding="utf-8") as fh:
                    found[key] = fh.read()
    return found


# The contract every promote shares: the four stable pointers, and what each must and must not say.
STABLE_POINTERS = {
    "rediacc-releases/cli/stable/install.sh": ("REDIACC_CHANNEL:-stable", "REDIACC_CHANNEL:-edge"),
    "rediacc-releases/cli/stable/install.ps1": ('} else { "stable" }', '} else { "edge" }'),
    "rediacc-releases/rpm/stable/rediacc.repo": ("/rpm/stable/", "/edge/"),
    "rediacc-releases/archlinux/stable/rediacc.conf": ("/archlinux/stable/", "/edge/"),
}
EDGE_POINTERS = tuple(k.replace("/stable/", "/edge/", 1) for k in STABLE_POINTERS)


def pointer_writes(records: list[dict[str, typing.Any]]) -> list[tuple[str, str, str]]:
    """Every write (COPY or PUT) to a stable pointer key, as (op, key, content), in log order."""
    return [
        (r["op"], r["key"], r["content"])
        for r in records
        if r.get("op") in ("COPY", "PUT") and r["key"] in STABLE_POINTERS
    ]


# The planted regressions, shared by both test files. Each is (old, new) text in `r2_promote.py`.
PLANT_BULK_THROUGH_THE_RUNNER = (
    (
        "            status = self._retried(\n"
        '                copy_argv(pair[0], pair[1], self.endpoint), "copy of %s" % pair[0]\n'
        "            )\n"
    ),
    (
        "            local = os.path.join(os.environ['FAKE_S3_ROOT'], '..', pair[0].replace('/', '_'))\n"
        '            status = self._retried(get_argv(pair[0], local, self.endpoint), "get") or self._retried(\n'
        '                put_argv(local, pair[1], self.endpoint), "put"\n'
        "            )\n"
    ),
)
PLANT_POINTERS_IN_THE_BULK = (
    "    excluded = set(pointers(dir_name))\n",
    "    excluded: set[str] = set()\n",
)
PLANT_PURGE_FROM_LOCAL_FILES = (
    "    return [channel_url(dir_name, rel) for rel in promoted]\n",
    "    return [channel_url(dir_name, name) for name in sorted(os.listdir(stage))]\n",
)
PLANT_PURGE_WITHOUT_THE_STABLE_LISTING = (
    "    missing = [rel for rel in promoted if rel not in landed]\n",
    "    missing: list[str] = []\n",
)
