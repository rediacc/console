"""`rediacc_ci.deploy.promote_r2_to_stable_hotfix`: the emergency promote, server-side (operator ruling 2026-09-26).

THE CONTRACT, asserted against a recording fake bucket (`r2_promote_fake.py`; nothing reaches R2 or Cloudflare):
  * the bulk never passes through the runner: the ONLY objects fetched are the edge channel pointers, and every other object is moved by a server-side `copy-object`;
  * EVERY edge object lands in stable (one phase, no filters, as the twin's recursive copy);
  * the four channel pointers arrive stamped for stable, are never written unstamped even briefly (the twin's copy-then-rebake window, which put an edge installer on production on 2026-09-24), and are written after the rest of their tree;
  * the purge list comes from the stable listing after the copy, without the twin's four duplicates, and a promoted key missing from it refuses the run with nothing purged.
Each clause has a MUTATION CONTROL: a planted `r2_promote.py` that breaks it, which must turn the clause's check red.

The twin `.ci/scripts/deploy/promote-r2-to-stable-hotfix.sh` still downloads and re-uploads, so its call log is no longer this port's. It is still driven for the refusals that happen before any transfer, where the two must agree.
"""

from __future__ import annotations

import ast
import os
import shutil
import subprocess
import typing

import pytest

from rediacc_ci import paths
from rediacc_ci.deploy import promote_r2_to_stable_hotfix as port
from rediacc_ci.quality import python_env_registry
from rediacc_ci.tests import r2_promote_fake as fake

if typing.TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()
TWIN = ROOT / ".ci" / "scripts" / "deploy" / "promote-r2-to-stable-hotfix.sh"
PURGE = ROOT / ".ci" / "scripts" / "deploy" / "cf-purge-urls.sh"
PORT_FILE = ROOT / ".ci" / "rediacc_ci" / "deploy" / "promote_r2_to_stable_hotfix.py"
MODULE = "rediacc_ci.deploy.promote_r2_to_stable_hotfix"
BASH = shutil.which("bash") or "/bin/bash"
HOME = os.environ.get("HOME", "/tmp")

BASE_ENV = {
    "CLOUDFLARE_R2_ACCESS_KEY_ID": "r2-key-fixture",
    "CLOUDFLARE_R2_SECRET_ACCESS_KEY": "r2-secret-fixture",
    "CLOUDFLARE_R2_ENDPOINT": "https://r2.example.invalid",
    "CLOUDFLARE_ZONE_ID": "zone-fixture",
    "CLOUDFLARE_API_TOKEN": "tok-fixture",
}

# `apt` holds a file in a SUBDIRECTORY, whose purge URL must keep its directories. The `*/stable/` entries are production's shape: an old stable pointer (which a failed run must leave in place) and history edge no longer names.
DEFAULT_BUCKET = {
    "cli/edge/rdc-linux-x64": "rdc binary bytes\n",
    "cli/edge/manifest.json": '{"version":"1.2.3"}\n',
    "cli/edge/latest.json": '{"latest":"1.2.3"}\n',
    "cli/edge/latest-linux.yml": "version: 1.2.3\n",
    "cli/edge/install.sh": '#!/bin/sh\n: "${REDIACC_CHANNEL:-edge}"\n',
    "cli/edge/install.ps1": '$c = if ($e) { "edge" } else { "edge" }\n',
    "apt/edge/rdc.deb": "deb bytes\n",
    "apt/edge/dists/stable/Packages.gz": "packages body\n",
    "apt/edge/InRelease": "inrelease body\n",
    "rpm/edge/rdc.rpm": "rpm bytes\n",
    "rpm/edge/repodata/repomd.xml": "repomd body\n",
    "rpm/edge/repodata/comps.xml": "comps body\n",
    "rpm/edge/rediacc.repo": "[rediacc]\nbaseurl=https://releases.rediacc.com/rpm/edge/\n",
    "apk/edge/rdc.apk": "apk bytes\n",
    "apk/edge/APKINDEX.tar.gz": "apkindex body\n",
    "archlinux/edge/rdc.pkg.tar.zst": "pkg bytes\n",
    "archlinux/edge/rediacc.db.tar.gz": "db body\n",
    "archlinux/edge/rediacc.conf": "[rediacc]\nServer = https://releases.rediacc.com/archlinux/edge/\n",
    "apt/stable/history-0.0.1.deb": "old release bytes\n",
    "cli/stable/install.sh": '#!/bin/sh\n: "${REDIACC_CHANNEL:-stable}"\n# previous release\n',
}
EDGE_KEYS = sorted(k for k in DEFAULT_BUCKET if "/edge/" in k)


def run(tmp_path: pathlib.Path, bucket: dict[str, str] | None = None, **kw: typing.Any):
    root = tmp_path / "fx"
    fake.make_bucket(root, DEFAULT_BUCKET if bucket is None else bucket)
    proc, records = fake.run_port(root, MODULE, BASE_ENV, HOME, **kw)
    return root, proc, records


def stable_of(edge_key: str) -> str:
    return "%s/%s" % (fake.BUCKET, edge_key.replace("/edge/", "/stable/", 1))


def _expected_urls() -> list[str]:
    urls = []
    for dir_name in port.CHANNEL_DIRS:
        prefix = "%s/edge/" % dir_name
        urls += [
            port.channel_url(dir_name, k[len(prefix) :]) for k in EDGE_KEYS if k.startswith(prefix)
        ]
    return urls


def _bulk_problems(records) -> list[str]:
    problems = []
    gets = sorted(r["key"] for r in fake.ops(records, "GET"))
    if gets != sorted(fake.EDGE_POINTERS):
        problems.append("fetched to the runner: %s" % gets)
    puts = sorted(r["key"] for r in fake.ops(records, "PUT"))
    if puts != sorted(fake.STABLE_POINTERS):
        problems.append("uploaded from the runner: %s" % puts)
    problems.extend(
        "a tree transfer: %s" % argv
        for argv in fake.aws_calls(records)
        if argv[:2] == ["s3", "sync"] or "--recursive" in argv
    )
    return problems


def _pointer_problems(records) -> list[str]:
    problems = []
    written = fake.pointer_writes(records)
    for op, key, content in written:
        good, bad = fake.STABLE_POINTERS[key]
        if op != "PUT" or good not in content or bad in content:
            problems.append("%s of %s carried %r" % (op, key, content))
    if sorted(k for _op, k, _c in written) != sorted(fake.STABLE_POINTERS):
        problems.append("pointers written: %s" % [k for _op, k, _c in written])
    return problems


# --------------------------------------------------------------------------- The happy path ---------------------------------------------------------------------------


def test_happy_path_prints_the_twins_lines_and_purges_once(tmp_path) -> None:
    _root, proc, records = run(tmp_path)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.splitlines()[:6] == [
        "Promoting cli/edge/ -> cli/stable/",
        "Promoting apt/edge/ -> apt/stable/",
        "Promoting rpm/edge/ -> rpm/stable/",
        "Promoting apk/edge/ -> apk/stable/",
        "Promoting archlinux/edge/ -> archlinux/stable/",
        "R2 promoted to stable",
    ], proc.stdout
    assert proc.stderr == ""
    assert fake.curl_calls(records) == 1


# --------------------------------------------------------------------------- The bulk is server-side, and all of it lands ---------------------------------------------------------------------------


def test_the_bulk_is_copied_server_side_and_only_the_pointers_are_fetched(tmp_path) -> None:
    assert port.BULK_IS_SERVER_SIDE is True
    _root, proc, records = run(tmp_path)
    assert proc.returncode == 0, proc.stderr
    assert _bulk_problems(records) == []
    copied = sorted(r["src"] for r in fake.ops(records, "COPY"))
    assert copied == sorted(
        "%s/%s" % (fake.BUCKET, k)
        for k in EDGE_KEYS
        if "%s/%s" % (fake.BUCKET, k) not in fake.EDGE_POINTERS
    )


def test_mutation_control_a_bulk_through_the_runner_is_caught(tmp_path) -> None:
    planted = fake.plant(tmp_path, *fake.PLANT_BULK_THROUGH_THE_RUNNER)
    root, proc, records = run(tmp_path, plant=planted)
    assert proc.returncode == 0, proc.stderr
    assert _bulk_problems(records) != []
    assert all(stable_of(k) in fake.bucket_keys(root, "") for k in EDGE_KEYS)


def test_every_edge_object_lands_in_stable_with_its_bytes(tmp_path) -> None:
    """One phase, no filters: the files the soak-gated lane never promotes (`latest-linux.yml`, `comps.xml`) land here too."""
    root, proc, _records = run(tmp_path)
    assert proc.returncode == 0, proc.stderr
    stable = fake.bucket_keys(root, "")
    for key in EDGE_KEYS:
        assert stable_of(key) in stable, key
        if "%s/%s" % (fake.BUCKET, key) not in fake.EDGE_POINTERS:
            assert stable[stable_of(key)] == DEFAULT_BUCKET[key], key
    assert stable["rediacc-releases/apt/stable/history-0.0.1.deb"] == "old release bytes\n"


# --------------------------------------------------------------------------- The channel pointers ---------------------------------------------------------------------------


def test_the_pointers_arrive_stamped_and_are_never_written_unstamped(tmp_path) -> None:
    """#b22efec4: no write of a stable pointer ever carries the edge default, not even for the twin's copy-then-rebake window."""
    assert port.EDGE_DEFAULT_REACHES_STABLE_BEFORE_THE_REBAKE is False
    root, proc, records = run(tmp_path)
    assert proc.returncode == 0, proc.stderr
    assert _pointer_problems(records) == []
    stable = fake.bucket_keys(root, "")
    for key, (good, bad) in fake.STABLE_POINTERS.items():
        assert good in stable[key], (key, stable[key])
        assert bad not in stable[key], (key, stable[key])


def test_mutation_control_a_pointer_copied_unrewritten_is_caught(tmp_path) -> None:
    planted = fake.plant(tmp_path, *fake.PLANT_POINTERS_IN_THE_BULK)
    root, proc, records = run(tmp_path, plant=planted)
    assert proc.returncode == 0, proc.stderr
    assert _pointer_problems(records) != []
    assert (
        "REDIACC_CHANNEL:-stable"
        in fake.bucket_keys(root, "")["rediacc-releases/cli/stable/install.sh"]
    )


def test_the_pointers_are_written_after_the_rest_of_their_tree(tmp_path) -> None:
    _root, proc, records = run(tmp_path)
    assert proc.returncode == 0, proc.stderr
    writes = [r["key"] for r in records if r.get("op") in ("COPY", "PUT")]
    for pointer in fake.STABLE_POINTERS:
        tree = pointer.rsplit("/", 1)[0] + "/"
        last_copy = max(
            i for i, k in enumerate(writes) if k.startswith(tree) and k not in fake.STABLE_POINTERS
        )
        assert writes.index(pointer) > last_copy, pointer


def test_a_run_that_dies_after_cli_leaves_every_stable_pointer_stamped(tmp_path) -> None:
    """THE 2026-09-24 INCIDENT: the credential expired during `apt`. `cli/stable/` is complete and stamped, the rpm and archlinux pointers were never touched, and nothing is purged."""
    root, proc, records = run(tmp_path, extra={"FAKE_AWS_DENY_MATCH": "apt/"})
    assert proc.returncode == 1, proc.stderr
    stable = fake.bucket_keys(root, "")
    assert "REDIACC_CHANNEL:-stable" in stable["rediacc-releases/cli/stable/install.sh"]
    assert "# previous release" not in stable["rediacc-releases/cli/stable/install.sh"]
    assert "rediacc-releases/rpm/stable/rediacc.repo" not in stable
    assert fake.curl_calls(records) == 0


def test_a_run_that_dies_mid_tree_keeps_the_previous_stable_pointer(tmp_path) -> None:
    """`POINTERS_GO_LAST`: the credential expires during `cli`'s own copy. The previous (stable-stamped) installer stays in place rather than a new one naming objects not copied yet."""
    root, proc, _records = run(tmp_path, extra={"FAKE_AWS_DENY_MATCH": "cli/stable/rdc-linux-x64"})
    assert proc.returncode == 1, proc.stderr
    assert (
        fake.bucket_keys(root, "")["rediacc-releases/cli/stable/install.sh"]
        == DEFAULT_BUCKET["cli/stable/install.sh"]
    )


def test_an_installer_the_stamp_cannot_reach_is_refused_before_any_write(tmp_path) -> None:
    bucket = dict(DEFAULT_BUCKET)
    bucket["cli/edge/install.sh"] = '#!/bin/sh\n: "${REDIACC_CHANNEL:=edge}"\n'
    _root, proc, records = run(tmp_path, bucket)
    assert proc.returncode == 1, proc.stderr
    assert "install.sh" in proc.stderr, proc.stderr
    assert "stable" in proc.stderr, proc.stderr
    assert fake.ops(records, "COPY") == []
    assert fake.ops(records, "PUT") == []


# --------------------------------------------------------------------------- The purge list comes from the stable listing ---------------------------------------------------------------------------


def test_the_purge_list_is_every_promoted_key_once_and_keeps_directories(tmp_path) -> None:
    """The twin posted the four pointers twice (its `find` loop and its re-bake loops); the port posts each promoted key once."""
    assert port.PURGE_LIST_CONTAINS_DUPLICATES is False
    assert port.PURGE_LIST_IS_BUILT_FROM_THE_STABLE_LISTING is True
    _root, proc, records = run(tmp_path)
    assert proc.returncode == 0, proc.stderr
    urls = fake.purge_urls(records)
    assert urls == _expected_urls(), urls
    assert len(urls) == len(set(urls))
    assert "https://releases.rediacc.com/apt/stable/dists/stable/Packages.gz" in urls
    assert not any("history-" in u for u in urls)


def test_mutation_control_a_purge_list_from_local_files_is_caught(tmp_path) -> None:
    planted = fake.plant(tmp_path, *fake.PLANT_PURGE_FROM_LOCAL_FILES)
    _root, proc, records = run(tmp_path, plant=planted)
    assert proc.returncode == 0, proc.stderr
    assert fake.purge_urls(records) != _expected_urls()


def test_a_copy_that_did_not_land_refuses_and_purges_nothing(tmp_path) -> None:
    _root, proc, records = run(tmp_path, extra={"FAKE_AWS_DROP_COPY_MATCH": "apt/stable/rdc.deb"})
    assert proc.returncode == 1, proc.stderr
    assert "INCOMPLETE: 1 promoted object(s)" in proc.stderr, proc.stderr
    assert fake.curl_calls(records) == 0


def test_mutation_control_a_purge_list_that_skips_the_stable_listing_is_caught(tmp_path) -> None:
    planted = fake.plant(tmp_path, *fake.PLANT_PURGE_WITHOUT_THE_STABLE_LISTING)
    _root, proc, records = run(
        tmp_path, plant=planted, extra={"FAKE_AWS_DROP_COPY_MATCH": "apt/stable/rdc.deb"}
    )
    assert proc.returncode == 0, proc.stderr
    assert "https://releases.rediacc.com/apt/stable/rdc.deb" in fake.purge_urls(records)


# --------------------------------------------------------------------------- Incremental, vacuity ---------------------------------------------------------------------------


def test_a_second_promote_of_the_same_edge_copies_nothing(tmp_path) -> None:
    root, proc, _records = run(tmp_path)
    assert proc.returncode == 0, proc.stderr
    again, records = fake.run_port(root, MODULE, BASE_ENV, HOME)
    assert again.returncode == 0, again.stderr
    assert fake.ops(records, "COPY") == []
    assert fake.purge_urls(records) == _expected_urls()


def test_an_empty_edge_tree_is_refused_before_anything_moves(tmp_path) -> None:
    empty = {k: v for k, v in DEFAULT_BUCKET.items() if not k.startswith("cli/edge/")}
    _root, proc, records = run(tmp_path, empty)
    assert proc.returncode == 1
    assert proc.stderr.startswith("VACUOUS: cli/edge/ lists 0 object(s)"), proc.stderr
    assert proc.stdout == "Promoting cli/edge/ -> cli/stable/\n"
    assert len(fake.aws_calls(records)) == 1


# --------------------------------------------------------------------------- Retries and refusals ---------------------------------------------------------------------------


def test_the_r2_credential_is_bridged_to_aws(tmp_path) -> None:
    """R2 speaks S3; the twin exports its CLOUDFLARE_R2_* pair as AWS_* for the `aws` child."""
    root = tmp_path / "fx"
    fake.make_bucket(root, DEFAULT_BUCKET)
    stub = fake.stub_bin(root)
    (root / "fixture-bin" / "aws").write_text(
        '#!/bin/sh\necho "$AWS_ACCESS_KEY_ID $AWS_DEFAULT_REGION" >&2\nexit 1\n', encoding="utf-8"
    )
    env = {"PATH": stub, "HOME": HOME, **BASE_ENV, "PROMOTE_RETRY_DELAY_S": "0"}
    proc = subprocess.run(
        ["python3", "-c", fake.DRIVER, str(fake.CI), MODULE],
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=60,
    )
    assert proc.returncode == 1
    assert proc.stderr.startswith("r2-key-fixture auto\n"), proc.stderr


def test_a_transient_copy_failure_is_retried_and_announced(tmp_path) -> None:
    root, proc, _records = run(
        tmp_path, extra={"FAKE_AWS_FLAKY_MATCH": "apt/stable/rdc.deb", "FAKE_AWS_FLAKY_TIMES": "1"}
    )
    assert proc.returncode == 0, proc.stderr
    assert "copy of apt/edge/rdc.deb failed (exit 1), retrying (2/3)" in proc.stderr, proc.stderr
    assert "rediacc-releases/apt/stable/rdc.deb" in fake.bucket_keys(root, "")


def test_a_persistent_transient_failure_stops_after_three_tries(tmp_path) -> None:
    _root, proc, records = run(
        tmp_path, extra={"FAKE_AWS_RC": "1", "FAKE_AWS_STDERR": fake.INCOMPLETE_READ}
    )
    assert proc.returncode == 1
    assert proc.stderr.count("retrying (") == 2, proc.stderr
    assert fake.curl_calls(records) == 0


def test_access_denied_is_fatal_on_the_first_try(tmp_path) -> None:
    _root, proc, records = run(tmp_path, extra={"FAKE_AWS_RC": "1"})
    assert proc.returncode == 1
    assert "retrying (" not in proc.stderr, proc.stderr
    assert "AccessDenied" in proc.stderr, proc.stderr
    assert "not retrying" in proc.stderr, proc.stderr
    assert len(fake.aws_calls(records)) == 1


def test_an_unset_zone_becomes_an_empty_argument_and_the_purge_refuses(tmp_path) -> None:
    _root, proc, records = run(tmp_path, drop_env=("CLOUDFLARE_ZONE_ID",))
    assert proc.returncode == 1
    assert proc.stdout.rstrip("\n").endswith("R2 promoted to stable")
    assert "--zone <ZONE_ID> is required" in proc.stderr
    assert fake.curl_calls(records) == 0


def test_no_cloudflare_credential_warns_and_still_exits_zero(tmp_path) -> None:
    _root, proc, records = run(tmp_path, drop_env=("CLOUDFLARE_API_TOKEN",))
    assert proc.returncode == 0
    assert "no Cloudflare credentials in env" in proc.stderr
    assert fake.curl_calls(records) == 0


def _twin(root: pathlib.Path, drop_env: tuple[str, ...] = (), drop: str = ""):
    env = {"PATH": fake.stub_bin(root, drop=drop), "HOME": HOME, "LC_ALL": "C.UTF-8", **BASE_ENV}
    env["FAKE_CALL_LOG"] = str(root / "twin-calls.jsonl")
    env["FAKE_S3_ROOT"] = str(root / "s3")
    for name in drop_env:
        env.pop(name, None)
    return subprocess.run(
        [BASH, str(TWIN)], capture_output=True, text=True, env=env, check=False, timeout=60
    )


@pytest.mark.parametrize(
    "missing",
    ["CLOUDFLARE_R2_ACCESS_KEY_ID", "CLOUDFLARE_R2_SECRET_ACCESS_KEY", "CLOUDFLARE_R2_ENDPOINT"],
)
def test_each_required_variable_refuses_as_the_twin_does(tmp_path, missing) -> None:
    root, proc, records = run(tmp_path, drop_env=(missing,))
    old = _twin(root, drop_env=(missing,))
    tail = "%s: %s: %s must be set\n" % (missing, port.SELF, missing)
    assert old.returncode == proc.returncode == 1
    assert old.stdout == proc.stdout == ""
    assert old.stderr.endswith(tail), repr(old.stderr)
    assert proc.stderr == tail, repr(proc.stderr)
    assert records == []


def test_an_empty_variable_refuses_exactly_as_an_absent_one_does(tmp_path) -> None:
    _root, proc, _records = run(tmp_path, extra={"CLOUDFLARE_R2_ENDPOINT": ""})
    assert proc.returncode == 1
    assert (
        proc.stderr
        == "CLOUDFLARE_R2_ENDPOINT: %s: CLOUDFLARE_R2_ENDPOINT must be set\n" % port.SELF
    )


def test_a_missing_aws_refuses_before_the_variable_guards(tmp_path) -> None:
    root, proc, records = run(tmp_path, drop="aws", drop_env=tuple(BASE_ENV))
    old = _twin(root, drop="aws", drop_env=tuple(BASE_ENV))
    assert old.returncode == proc.returncode == 1
    assert proc.stderr == old.stderr == "✗ Required command 'aws' is not available\n", repr(
        proc.stderr
    )
    assert records == []


# --------------------------------------------------------------------------- The tables ---------------------------------------------------------------------------


def test_the_directory_order_is_the_twins() -> None:
    assert port.CHANNEL_DIRS == ("cli", "apt", "rpm", "apk", "archlinux")
    assert port.PHASES == ((),)


def test_endpoint_args_reproduces_the_unquoted_word_split() -> None:
    assert port.endpoint_args("https://x") == ["--endpoint-url", "https://x"]
    assert port.endpoint_args("a b") == ["--endpoint-url", "a", "b"]


def test_the_purge_script_is_still_the_bash_one_and_still_exists() -> None:
    assert port.PURGE_SCRIPT_RELATIVE == ".ci/scripts/deploy/cf-purge-urls.sh"
    assert PURGE.is_file()
    assert port.purge_argv("z")[-2:] == ["--zone", "z"]


def test_every_variable_is_read_with_a_literal_os_environ_get() -> None:
    source = PORT_FILE.read_text(encoding="utf-8")
    names = set(port.environment())
    assert names == {
        "CLOUDFLARE_R2_ACCESS_KEY_ID",
        "CLOUDFLARE_R2_SECRET_ACCESS_KEY",
        "CLOUDFLARE_R2_ENDPOINT",
        "CLOUDFLARE_ZONE_ID",
        "PROMOTE_RETRY_DELAY_S",
    }
    tree = ast.parse(source, filename=str(PORT_FILE))
    derived = python_env_registry.scan_module(
        str(PORT_FILE),
        tree,
        {str(PORT_FILE): python_env_registry.module_constants(tree)},
        {},
    )
    assert derived == names, f"the gate would derive {sorted(derived)}, not {sorted(names)}"
