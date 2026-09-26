"""`rediacc_ci.deploy.promote_r2_to_stable`: the soak-gated promote, server-side (operator ruling 2026-09-26).

THE CONTRACT, asserted against a recording fake bucket (`r2_promote_fake.py`; nothing reaches R2 or Cloudflare):
  * the bulk never passes through the runner: the ONLY objects fetched are the edge channel pointers, and every other object is moved by a server-side `copy-object` from `<dir>/edge/<rel>` to `<dir>/stable/<rel>`;
  * every edge object the phase filters select lands in stable with its bytes, bytes before metadata before signatures;
  * the four channel pointers arrive stamped for stable, are never written unstamped even briefly, and are written after the rest of their tree;
  * the purge list comes from the stable listing after the copy, and a promoted key missing from it refuses the run with nothing purged.
Each clause has a MUTATION CONTROL: a planted `r2_promote.py` that breaks it, run through the same test, which must go red.

The twin `.ci/scripts/deploy/promote-r2-to-stable.sh` still downloads and re-uploads, so its call log is no longer this port's. It is still driven for the refusals that happen before any transfer, where the two must agree.
"""

from __future__ import annotations

import ast
import os
import shutil
import subprocess
import typing

import pytest

from rediacc_ci import paths
from rediacc_ci.deploy import promote_r2_to_stable as port
from rediacc_ci.quality import python_env_registry
from rediacc_ci.tests import r2_promote_fake as fake

if typing.TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()
TWIN = ROOT / ".ci" / "scripts" / "deploy" / "promote-r2-to-stable.sh"
PURGE = ROOT / ".ci" / "scripts" / "deploy" / "cf-purge-urls.sh"
PORT_FILE = ROOT / ".ci" / "rediacc_ci" / "deploy" / "promote_r2_to_stable.py"
MODULE = "rediacc_ci.deploy.promote_r2_to_stable"
BASH = shutil.which("bash") or "/bin/bash"
HOME = os.environ.get("HOME", "/tmp")

BASE_ENV = {
    "AWS_ACCESS_KEY_ID": "akid-fixture",
    "AWS_SECRET_ACCESS_KEY": "secret-fixture",
    "AWS_DEFAULT_REGION": "auto",
    "CLOUDFLARE_R2_ENDPOINT": "https://r2.example.invalid",
    "EDGE_VERSION": "1.2.3",
    "CLOUDFLARE_ZONE_ID": "zone-fixture",
    "CLOUDFLARE_API_TOKEN": "tok-fixture",
}

# `cli/edge/latest-linux.yml` and `rpm/edge/repodata/comps.xml` match a phase-1 exclude and no phase-2 include, so they are never promoted. The `*/stable/history-*` entries are production's shape: stable already holds release history that edge no longer names, and a promote must leave it alone and not purge it.
DEFAULT_BUCKET = {
    "cli/edge/rdc-linux-x64": "rdc binary bytes\n",
    "cli/edge/manifest.json": '{"version":"1.2.3"}\n',
    "cli/edge/latest.json": '{"latest":"1.2.3"}\n',
    "cli/edge/latest-linux.yml": "version: 1.2.3\n",
    "cli/edge/install.sh": '#!/bin/sh\n: "${REDIACC_CHANNEL:-edge}"\n',
    "cli/edge/install.ps1": '$c = if ($e) { "edge" } else { "edge" }\n',
    "apt/edge/pool/rdc.deb": "deb bytes\n",
    "apt/edge/InRelease": "inrelease body\n",
    "apt/edge/Packages.gz": "packages body\n",
    "rpm/edge/rdc.rpm": "rpm bytes\n",
    "rpm/edge/repodata/primary.xml.gz": "primary body\n",
    "rpm/edge/repodata/repomd.xml": "repomd body\n",
    "rpm/edge/repodata/comps.xml": "comps body\n",
    "rpm/edge/rediacc.repo": "[rediacc]\nbaseurl=https://releases.rediacc.com/rpm/edge/\n",
    "apk/edge/rdc.apk": "apk bytes\n",
    "apk/edge/APKINDEX.tar.gz": "apkindex body\n",
    "archlinux/edge/rdc.pkg.tar.zst": "pkg bytes\n",
    "archlinux/edge/rediacc.db.tar.gz": "db body\n",
    "archlinux/edge/rediacc.conf": "[rediacc]\nServer = https://releases.rediacc.com/archlinux/edge/\n",
    **{"%s/stable/history-0.0.1.pkg" % d: "old release bytes\n" for d in port.CHANNEL_DIRS},
}
PHASE_FILTERED = ("cli/edge/latest-linux.yml", "rpm/edge/repodata/comps.xml")
PROMOTED_EDGE_KEYS = sorted(k for k in DEFAULT_BUCKET if "/edge/" in k and k not in PHASE_FILTERED)


def run(tmp_path: pathlib.Path, bucket: dict[str, str] | None = None, **kw: typing.Any):
    root = tmp_path / "fx"
    fake.make_bucket(root, DEFAULT_BUCKET if bucket is None else bucket)
    proc, records = fake.run_port(root, MODULE, BASE_ENV, HOME, **kw)
    return root, proc, records


def stable_of(edge_key: str) -> str:
    return "%s/%s" % (fake.BUCKET, edge_key.replace("/edge/", "/stable/", 1))


# --------------------------------------------------------------------------- The happy path ---------------------------------------------------------------------------


def test_happy_path_prints_the_twins_lines_and_purges_once(tmp_path) -> None:
    _root, proc, records = run(tmp_path)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.splitlines()[:6] == [
        "Promoting cli/edge/ -> cli/stable/ (2-phase)",
        "Promoting apt/edge/ -> apt/stable/ (2-phase)",
        "Promoting rpm/edge/ -> rpm/stable/ (2-phase)",
        "Promoting apk/edge/ -> apk/stable/ (2-phase)",
        "Promoting archlinux/edge/ -> archlinux/stable/ (2-phase)",
        "R2 promotion complete: edge v1.2.3 -> stable",
    ], proc.stdout
    assert proc.stderr == ""
    assert fake.curl_calls(records) == 1


# --------------------------------------------------------------------------- The bulk is server-side ---------------------------------------------------------------------------


def _bulk_is_server_side(records) -> list[str]:
    """What breaks the contract, as sentences; empty when it holds."""
    problems = []
    gets = sorted(r["key"] for r in fake.ops(records, "GET"))
    if gets != sorted(fake.EDGE_POINTERS):
        problems.append("fetched to the runner: %s" % gets)
    puts = sorted(r["key"] for r in fake.ops(records, "PUT"))
    if puts != sorted(fake.STABLE_POINTERS):
        problems.append("uploaded from the runner: %s" % puts)
    for argv in fake.aws_calls(records):
        if argv[:2] == ["s3", "cp"] and argv[2].startswith("s3://") and argv[3].startswith("s3://"):
            problems.append("a high-level s3-to-s3 copy, which R2 refuses: %s" % argv)
        if argv[:2] == ["s3", "sync"] or "--recursive" in argv:
            problems.append("a tree transfer: %s" % argv)
    return problems


def test_the_bulk_is_copied_server_side_and_only_the_pointers_are_fetched(tmp_path) -> None:
    _root, proc, records = run(tmp_path)
    assert proc.returncode == 0, proc.stderr
    assert _bulk_is_server_side(records) == []
    for record in fake.ops(records, "COPY"):
        assert record["src"].replace("/edge/", "/stable/", 1) == record["key"], record
        assert record["directive"] == "REPLACE", record
        assert record["cache_control"] == "no-cache", record
    # The metadata the old upload gave these objects: aws-cli guessed the type from the name.
    types = {r["key"]: r["content_type"] for r in fake.ops(records, "COPY")}
    assert types["rediacc-releases/cli/stable/manifest.json"] == "application/json"


def test_mutation_control_a_bulk_through_the_runner_is_caught(tmp_path) -> None:
    """PROVE THE TEST ABOVE CAN FAIL: route each copy through a GET and a PUT on the runner. Every object still lands, so only the transfer contract sees it."""
    planted = fake.plant(tmp_path, *fake.PLANT_BULK_THROUGH_THE_RUNNER)
    root, proc, records = run(tmp_path, plant=planted)
    assert proc.returncode == 0, proc.stderr
    assert _bulk_is_server_side(records) != []
    assert all(stable_of(k) in fake.bucket_keys(root, "") for k in PROMOTED_EDGE_KEYS)


def test_every_selected_edge_object_lands_in_stable_with_its_bytes(tmp_path) -> None:
    root, proc, _records = run(tmp_path)
    assert proc.returncode == 0, proc.stderr
    stable = fake.bucket_keys(root, "")
    for key in PROMOTED_EDGE_KEYS:
        assert stable_of(key) in stable, key
        if "%s/%s" % (fake.BUCKET, key) not in fake.EDGE_POINTERS:
            assert stable[stable_of(key)] == DEFAULT_BUCKET[key], key
    # FACT 1: filtered by phase 1 and named by no phase-2 include, still never promoted.
    assert port.PHASE_FILTERED_FILES_ARE_NEVER_PROMOTED is True
    for key in PHASE_FILTERED:
        assert stable_of(key) not in stable, key
    # Stable history that edge does not name is untouched.
    assert stable["rediacc-releases/apt/stable/history-0.0.1.pkg"] == "old release bytes\n"


def _phase_order_problems(records) -> list[str]:
    order = [r["key"] for r in fake.ops(records, "COPY")]
    at = {key: i for i, key in enumerate(order)}
    stable = "rediacc-releases/%s/stable/%s"
    chains = (
        [("apt", "pool/rdc.deb"), ("apt", "Packages.gz"), ("apt", "InRelease")],
        [("rpm", "rdc.rpm"), ("rpm", "repodata/primary.xml.gz"), ("rpm", "repodata/repomd.xml")],
        [("apk", "rdc.apk"), ("apk", "APKINDEX.tar.gz")],
        [("archlinux", "rdc.pkg.tar.zst"), ("archlinux", "rediacc.db.tar.gz")],
        [("cli", "rdc-linux-x64"), ("cli", "latest.json")],
    )
    problems = []
    for chain in chains:
        keys = [stable % pair for pair in chain]
        if [at.get(k, -1) for k in keys] != sorted(at.get(k, -1) for k in keys) or any(
            k not in at for k in keys
        ):
            problems.append("out of order: %s" % keys)
    return problems


def test_the_phase_order_is_bytes_then_metadata_then_signatures(tmp_path) -> None:
    """THE ENTIRE DESIGN OF THE SOAK-GATED PROMOTE IS AN ORDER: a client must never see `Release` before the `Packages` it hashes, or `repomd.xml` before `primary`. Each phase finishes before the next starts, so completion order in the log is phase order."""
    _root, proc, records = run(tmp_path)
    assert proc.returncode == 0, proc.stderr
    assert _phase_order_problems(records) == []


def test_mutation_control_a_reordered_phase_two_is_caught(tmp_path) -> None:
    """PROVE THE ORDER TEST CAN FAIL: swap `apt`'s two phase-2 arms in a planted copy of the port."""
    source = PORT_FILE.read_text(encoding="utf-8")
    swapped = source.replace(
        '        ("--exclude", "*", "--include", "Packages*"),\n'
        '        ("--exclude", "*", "--include", "Release*", "--include", "InRelease"),\n',
        '        ("--exclude", "*", "--include", "Release*", "--include", "InRelease"),\n'
        '        ("--exclude", "*", "--include", "Packages*"),\n',
    )
    assert swapped != source, "the plant did not apply; the control is broken, not the test"
    planted = tmp_path / "planted_port.py"
    planted.write_text(swapped, encoding="utf-8")
    _root, _proc, records = run(tmp_path, plant_port=str(planted))
    assert _phase_order_problems(records) != []


# --------------------------------------------------------------------------- The channel pointers ---------------------------------------------------------------------------


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


def test_the_pointers_arrive_stamped_and_are_never_written_unstamped(tmp_path) -> None:
    root, proc, records = run(tmp_path)
    assert proc.returncode == 0, proc.stderr
    assert _pointer_problems(records) == []
    stable = fake.bucket_keys(root, "")
    for key, (good, bad) in fake.STABLE_POINTERS.items():
        assert good in stable[key], (key, stable[key])
        assert bad not in stable[key], (key, stable[key])


def test_mutation_control_a_pointer_copied_unrewritten_is_caught(tmp_path) -> None:
    """PROVE THE TEST ABOVE CAN FAIL: drop the pointer exclusion. The stamped PUT still lands LAST, so the final bucket looks right; only the write log sees the edge body reach stable first."""
    planted = fake.plant(tmp_path, *fake.PLANT_POINTERS_IN_THE_BULK)
    root, proc, records = run(tmp_path, plant=planted)
    assert proc.returncode == 0, proc.stderr
    assert _pointer_problems(records) != []
    assert (
        "REDIACC_CHANNEL:-stable"
        in fake.bucket_keys(root, "")["rediacc-releases/cli/stable/install.sh"]
    )


def test_the_pointers_are_written_after_the_rest_of_their_tree(tmp_path) -> None:
    """`r2_promote.POINTERS_GO_LAST`: a client reading a new pointer finds everything it names already in stable."""
    assert port.BULK_IS_SERVER_SIDE is True
    _root, proc, records = run(tmp_path)
    assert proc.returncode == 0, proc.stderr
    writes = [r["key"] for r in records if r.get("op") in ("COPY", "PUT")]
    for pointer in fake.STABLE_POINTERS:
        tree = pointer.rsplit("/", 1)[0] + "/"
        last_copy = max(
            i for i, k in enumerate(writes) if k.startswith(tree) and k not in fake.STABLE_POINTERS
        )
        assert writes.index(pointer) > last_copy, pointer


def test_an_installer_the_stamp_cannot_reach_is_refused_before_any_write(tmp_path) -> None:
    """#b22efec4: a template whose default the substitution does not recognise would reach stable pointing at edge. Refused before anything is written."""
    bucket = dict(DEFAULT_BUCKET)
    bucket["cli/edge/install.sh"] = '#!/bin/sh\n: "${REDIACC_CHANNEL:=edge}"\n'
    _root, proc, records = run(tmp_path, bucket)
    assert proc.returncode == 1, proc.stderr
    assert "install.sh" in proc.stderr, proc.stderr
    assert "stable" in proc.stderr, proc.stderr
    assert fake.ops(records, "COPY") == []
    assert fake.ops(records, "PUT") == []


def test_an_absent_pointer_is_skipped(tmp_path) -> None:
    stripped = {
        k: v
        for k, v in DEFAULT_BUCKET.items()
        if "%s/%s" % (fake.BUCKET, k) not in fake.EDGE_POINTERS
    }
    _root, proc, records = run(tmp_path, stripped)
    assert proc.returncode == 0, proc.stderr
    assert fake.ops(records, "GET") == []
    assert fake.ops(records, "PUT") == []


def test_a_run_that_dies_after_cli_leaves_the_stable_default_in_place(tmp_path) -> None:
    """THE 2026-09-24 SHAPE: the credential expires once `cli` is done. Everything under `cli/stable/` is right; nothing is purged."""
    root, proc, records = run(tmp_path, extra={"FAKE_AWS_DENY_MATCH": "apt/"})
    assert proc.returncode == 1, proc.stderr
    stable = fake.bucket_keys(root, "")
    assert "REDIACC_CHANNEL:-stable" in stable["rediacc-releases/cli/stable/install.sh"]
    assert '} else { "stable" }' in stable["rediacc-releases/cli/stable/install.ps1"]
    assert fake.curl_calls(records) == 0


# --------------------------------------------------------------------------- The purge list comes from the stable listing ---------------------------------------------------------------------------


def _expected_urls() -> list[str]:
    urls = []
    for dir_name in port.CHANNEL_DIRS:
        prefix = "%s/edge/" % dir_name
        urls += [
            port.channel_url(dir_name, k[len(prefix) :])
            for k in PROMOTED_EDGE_KEYS
            if k.startswith(prefix)
        ]
    return urls


def test_the_purge_list_is_every_promoted_key_the_stable_listing_confirms(tmp_path) -> None:
    assert port.PURGE_LIST_IS_BUILT_FROM_THE_STABLE_LISTING is True
    _root, proc, records = run(tmp_path)
    assert proc.returncode == 0, proc.stderr
    urls = fake.purge_urls(records)
    assert urls == _expected_urls(), urls
    assert "https://releases.rediacc.com/cli/stable/latest-linux.yml" not in urls
    assert not any("history-" in u for u in urls)
    assert "https://releases.rediacc.com/apt/stable/pool/rdc.deb" in urls


def test_mutation_control_a_purge_list_from_local_files_is_caught(tmp_path) -> None:
    """PROVE THE TEST ABOVE CAN FAIL: build the list from the runner's local stage, the old `find` shape. Only the pointers are local now, so the binaries drop out."""
    planted = fake.plant(tmp_path, *fake.PLANT_PURGE_FROM_LOCAL_FILES)
    _root, proc, records = run(tmp_path, plant=planted)
    assert proc.returncode == 0, proc.stderr
    assert fake.purge_urls(records) != _expected_urls()


def test_a_copy_that_did_not_land_refuses_and_purges_nothing(tmp_path) -> None:
    """copy-object reported success and the object is not in the stable listing: `INCOMPLETE:`, exit 1, no purge."""
    _root, proc, records = run(
        tmp_path, extra={"FAKE_AWS_DROP_COPY_MATCH": "apt/stable/pool/rdc.deb"}
    )
    assert proc.returncode == 1, proc.stderr
    assert "INCOMPLETE: 1 promoted object(s)" in proc.stderr, proc.stderr
    assert "pool/rdc.deb" in proc.stderr, proc.stderr
    assert fake.curl_calls(records) == 0


def test_mutation_control_a_purge_list_that_skips_the_stable_listing_is_caught(tmp_path) -> None:
    """PROVE THE TEST ABOVE CAN FAIL: trust the plan instead of the listing, and the dropped object is purged as promoted."""
    planted = fake.plant(tmp_path, *fake.PLANT_PURGE_WITHOUT_THE_STABLE_LISTING)
    _root, proc, records = run(
        tmp_path, plant=planted, extra={"FAKE_AWS_DROP_COPY_MATCH": "apt/stable/pool/rdc.deb"}
    )
    assert proc.returncode == 0, proc.stderr
    assert "https://releases.rediacc.com/apt/stable/pool/rdc.deb" in fake.purge_urls(records)


# --------------------------------------------------------------------------- Incremental, limits, vacuity ---------------------------------------------------------------------------


def test_a_second_promote_of_the_same_edge_copies_nothing(tmp_path) -> None:
    """`aws s3 sync`'s skip rule, kept: an object whose stable copy has the same size and is not older is not copied again. Only the four pointers are re-put."""
    root, proc, _records = run(tmp_path)
    assert proc.returncode == 0, proc.stderr
    again, records = fake.run_port(root, MODULE, BASE_ENV, HOME)
    assert again.returncode == 0, again.stderr
    assert fake.ops(records, "COPY") == []
    assert sorted(r["key"] for r in fake.ops(records, "PUT")) == sorted(fake.STABLE_POINTERS)
    assert fake.purge_urls(records) == _expected_urls()


def test_an_object_over_the_copy_object_limit_is_refused_before_any_copy(tmp_path) -> None:
    _root, proc, records = run(
        tmp_path, extra={"FAKE_AWS_SIZE_OVERRIDE": "cli/edge/rdc-linux-x64=6000000000"}
    )
    assert proc.returncode == 1, proc.stderr
    assert "single CopyObject limit" in proc.stderr, proc.stderr
    assert [r for r in records if r.get("op")] == []


def test_an_empty_edge_tree_is_refused_before_anything_moves(tmp_path) -> None:
    empty = {k: v for k, v in DEFAULT_BUCKET.items() if not k.startswith("cli/edge/")}
    _root, proc, records = run(tmp_path, empty)
    assert proc.returncode == 1
    assert proc.stderr.startswith("VACUOUS: cli/edge/ lists 0 object(s)"), proc.stderr
    assert proc.stdout == "Promoting cli/edge/ -> cli/stable/ (2-phase)\n"
    assert len(fake.aws_calls(records)) == 1


# --------------------------------------------------------------------------- Retries and refusals ---------------------------------------------------------------------------


def test_a_transient_copy_failure_is_retried_and_announced(tmp_path) -> None:
    root, proc, _records = run(
        tmp_path,
        extra={"FAKE_AWS_FLAKY_MATCH": "apt/stable/pool/rdc.deb", "FAKE_AWS_FLAKY_TIMES": "1"},
    )
    assert proc.returncode == 0, proc.stderr
    assert "copy of apt/edge/pool/rdc.deb failed (exit 1), retrying (2/3)" in proc.stderr, (
        proc.stderr
    )
    assert "rediacc-releases/apt/stable/pool/rdc.deb" in fake.bucket_keys(root, "")


def test_a_persistent_transient_failure_stops_after_three_tries(tmp_path) -> None:
    _root, proc, records = run(
        tmp_path, extra={"FAKE_AWS_RC": "1", "FAKE_AWS_STDERR": fake.INCOMPLETE_READ}
    )
    assert proc.returncode == 1
    assert proc.stderr.count("retrying (") == 2, proc.stderr
    assert fake.curl_calls(records) == 0


def test_access_denied_is_fatal_on_the_first_try(tmp_path) -> None:
    """#b22efec4: an expired or wrong credential does not heal in ten seconds."""
    _root, proc, records = run(tmp_path, extra={"FAKE_AWS_RC": "1"})
    assert proc.returncode == 1
    assert "retrying (" not in proc.stderr, proc.stderr
    assert "AccessDenied" in proc.stderr, proc.stderr
    assert "not retrying" in proc.stderr, proc.stderr
    assert len(fake.aws_calls(records)) == 1


def test_access_denied_mid_copy_is_not_retried(tmp_path) -> None:
    _root, proc, _records = run(tmp_path, extra={"FAKE_AWS_DENY_MATCH": "apt/stable/pool/rdc.deb"})
    assert proc.returncode == 1
    assert "copy of apt/edge/pool/rdc.deb failed with AccessDenied" in proc.stderr, proc.stderr
    assert "retrying (" not in proc.stderr


def test_an_unset_zone_becomes_an_empty_argument_and_the_purge_refuses(tmp_path) -> None:
    """The promotion has already happened by then, which the twin's header says is deliberate."""
    _root, proc, records = run(tmp_path, drop_env=("CLOUDFLARE_ZONE_ID",))
    assert proc.returncode == 1
    assert proc.stdout.rstrip("\n").endswith("R2 promotion complete: edge v1.2.3 -> stable")
    assert "--zone <ZONE_ID> is required" in proc.stderr
    assert fake.curl_calls(records) == 0


def test_no_cloudflare_credential_warns_and_still_exits_zero(tmp_path) -> None:
    _root, proc, records = run(tmp_path, drop_env=("CLOUDFLARE_API_TOKEN",))
    assert proc.returncode == 0
    assert "no Cloudflare credentials in env" in proc.stderr
    assert fake.curl_calls(records) == 0


def _twin(root: pathlib.Path, drop_env: tuple[str, ...] = (), drop: str = "", **extra: str):
    env = {"PATH": fake.stub_bin(root, drop=drop), "HOME": HOME, "LC_ALL": "C.UTF-8", **BASE_ENV}
    env["FAKE_CALL_LOG"] = str(root / "twin-calls.jsonl")
    env["FAKE_S3_ROOT"] = str(root / "s3")
    env.update(extra)
    for name in drop_env:
        env.pop(name, None)
    return subprocess.run(
        [BASH, str(TWIN)], capture_output=True, text=True, env=env, check=False, timeout=60
    )


@pytest.mark.parametrize(
    "missing",
    ["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "CLOUDFLARE_R2_ENDPOINT", "EDGE_VERSION"],
)
def test_each_required_variable_refuses_as_the_twin_does(tmp_path, missing) -> None:
    """THE ONE NAMED DIVERGENCE: bash prefixes its refusal with `<path>: line N: `."""
    root, proc, records = run(tmp_path, drop_env=(missing,))
    old = _twin(root, drop_env=(missing,))
    tail = "%s: %s: %s must be set\n" % (missing, port.SELF, missing)
    assert old.returncode == proc.returncode == 1
    assert old.stdout == proc.stdout == ""
    assert old.stderr.endswith(tail), repr(old.stderr)
    assert proc.stderr == tail, repr(proc.stderr)
    assert records == []


def test_an_empty_variable_refuses_exactly_as_an_absent_one_does(tmp_path) -> None:
    _root, proc, _records = run(tmp_path, extra={"EDGE_VERSION": ""})
    assert proc.returncode == 1
    assert proc.stderr == "EDGE_VERSION: %s: EDGE_VERSION must be set\n" % port.SELF


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


def test_every_channel_directory_has_a_phase_two_arm() -> None:
    """A DIRECTORY MISSING FROM THE TABLE WOULD PROMOTE ITS BYTES AND NONE OF ITS METADATA."""
    assert set(port.PHASE_TWO) == set(port.CHANNEL_DIRS)
    assert [len(v) for v in (port.PHASE_TWO[d] for d in port.CHANNEL_DIRS)] == [1, 2, 2, 1, 1]
    assert port.phases("apt")[0] == port.META_EXCLUDES


def test_the_phase_one_excludes_are_the_twins_list_in_the_twins_order() -> None:
    """A REORDERED LIST IS A DIFFERENT FILTER, because the last matching rule wins."""
    excludes = [port.META_EXCLUDES[i + 1] for i in range(0, len(port.META_EXCLUDES), 2)]
    assert excludes == [
        "Packages*",
        "Release*",
        "InRelease",
        "repodata/*",
        "APKINDEX.tar.gz",
        "*.db.tar.gz",
        "*.files.tar.gz",
        "rediacc.db",
        "rediacc.files",
        "latest*.yml",
        "latest.json",
        "manifest.json",
        "install.sh",
        "install.ps1",
        "*.repo",
        "*.conf",
        "rediacc-cli-latest.tgz",
        "versions.json",
    ]
    assert set(port.META_EXCLUDES[0::2]) == {"--exclude"}


def test_the_rewrite_table_names_the_four_pointers() -> None:
    assert set(port.REWRITES) == {"cli", "rpm", "archlinux"}
    assert [name for name, _ in port.REWRITES["cli"]] == ["install.sh", "install.ps1"]
    assert port.REWRITES["rpm"] == (("rediacc.repo", (port.CHANNEL_SED,)),)
    assert port.REWRITES["archlinux"] == (("rediacc.conf", (port.CHANNEL_SED,)),)


def test_endpoint_args_reproduces_the_unquoted_word_split() -> None:
    assert port.endpoint_args("https://x") == ["--endpoint-url", "https://x"]
    assert port.endpoint_args("a b") == ["--endpoint-url", "a", "b"]


def test_the_purge_script_is_still_the_bash_one_and_still_exists() -> None:
    assert port.PURGE_SCRIPT_RELATIVE == ".ci/scripts/deploy/cf-purge-urls.sh"
    assert PURGE.is_file()
    assert port.purge_argv("z")[-2:] == ["--zone", "z"]


def test_every_variable_is_read_with_a_literal_os_environ_get() -> None:
    """`check:ci-python-env-registry` derives a module's inputs from its AST; ask ITS scanner, in both directions."""
    source = PORT_FILE.read_text(encoding="utf-8")
    names = set(port.environment())
    assert names == {
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "CLOUDFLARE_R2_ENDPOINT",
        "EDGE_VERSION",
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
