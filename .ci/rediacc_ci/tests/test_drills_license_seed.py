"""The license drill's failed-seed cleanup: a create that fails after issuance leaves a licence blob for a repo the CLI rolled back, and the drill purges exactly the blobs that appeared during the create (vm:check vmc-10231839-73e6a3, 2026-10-23)."""

from __future__ import annotations

import types

from rediacc_ci.drills import license as lic

OLD = "0cfc9ad4-0000-4000-8000-000000000001"
NEW = "edc7642b-f7c4-42ab-b2f1-9f6fc964faa8"


def _fake(listings: list[str]):
    """A stand-in `self` whose ssh_out answers the blob listing from `listings` in order and records every purge script."""
    calls: list[tuple[str, str | None]] = []
    captured: list[str] = []

    def ssh_out(_host, command, stdin=None):
        calls.append((command, stdin))
        if command.startswith("sudo ls -1"):
            return 0, listings.pop(0)
        return 0, "PURGED %s\n" % NEW

    fake = types.SimpleNamespace(
        o=types.SimpleNamespace(vm_ip="192.168.111.11", vm_renet="renet"),
        ssh_out=ssh_out,
        capture=lambda desc, _body: captured.append(desc),
    )
    fake.license_blob_guids = types.MethodType(lic.License.license_blob_guids, fake)
    return fake, calls, captured


def test_blob_listing_keeps_only_repo_guids() -> None:
    fake, _, _ = _fake(["%s\nnot-a-guid\n%s\n" % (OLD, NEW)])
    assert lic.License.license_blob_guids(fake, "h") == {OLD, NEW}


def test_failed_seed_purges_only_the_blob_the_create_left() -> None:
    fake, calls, captured = _fake(["%s\n%s\n" % (OLD, NEW)])
    lic.License.purge_failed_seed(fake, {OLD})
    purges = [stdin for cmd, stdin in calls if cmd == "bash -s"]
    assert len(purges) == 1
    assert NEW in purges[0]
    assert OLD not in purges[0], "a blob that existed before the create is not this run's to purge"
    assert captured


def test_failed_seed_with_no_new_blob_purges_nothing() -> None:
    fake, calls, _ = _fake(["%s\n" % OLD])
    lic.License.purge_failed_seed(fake, {OLD})
    assert not [c for c in calls if c[0] == "bash -s"]
