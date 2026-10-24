"""The license drill's failed-seed cleanup: a create that fails after issuance leaves a licence blob for a repo the CLI rolled back, and the drill purges exactly the blobs that appeared during the create (vm:check vmc-10231839-73e6a3, 2026-10-23)."""

from __future__ import annotations

import types

from rediacc_ci.drills import license as lic

OLD = "0cfc9ad4-0000-4000-8000-000000000001"
NEW = "edc7642b-f7c4-42ab-b2f1-9f6fc964faa8"


def _fake(listings: list[str | None]):
    """A stand-in `self` whose ssh_out answers the blob listing from `listings` in order and records every purge script."""
    calls: list[tuple[str, str | None]] = []
    captured: list[str] = []

    def ssh_out(_host, command, stdin=None):
        calls.append((command, stdin))
        if "ls -1" in command:
            listing = listings.pop(0)
            return (1, "") if listing is None else (0, listing)
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


def test_failed_seed_with_an_unreadable_baseline_purges_nothing() -> None:
    """A baseline listing that failed is unknown, never empty: every blob already on the host would otherwise look like this create's (review b4c1a83b.1)."""
    fake, calls, captured = _fake(["%s\n%s\n" % (OLD, NEW)])
    lic.License.purge_failed_seed(fake, None)
    assert not [c for c in calls if c[0] == "bash -s"]
    assert "nothing purged" in captured[0]


def test_failed_seed_with_an_unreadable_after_listing_purges_nothing() -> None:
    fake, calls, _ = _fake([None])
    lic.License.purge_failed_seed(fake, {OLD})
    assert not [c for c in calls if c[0] == "bash -s"]


def test_seed_captures_the_baseline_before_the_create_and_purges_on_failure() -> None:
    """The wiring of `seed_licensed_repo` itself (review b4c1a83b.2): baseline first, create, purge only when the create failed."""
    order: list[str] = []
    for create_code, expect_purge in ((1, True), (0, False)):
        order.clear()
        d = types.SimpleNamespace(
            code=create_code,
            step=lambda *_a: None,
            note=lambda *_a: None,
            run=lambda *_a: order.append("create"),
            assert_exit=lambda *_a: None,
            assert_equal=lambda *_a: None,
        )

        def blobs(_host, order=order):
            order.append("baseline-blobs")
            return {OLD}

        fake = types.SimpleNamespace(
            d=d,
            o=types.SimpleNamespace(vm_ip="h"),
            rdc="rdc",
            status_guids=lambda _h: {NEW},
            license_blob_guids=blobs,
            purge_failed_seed=lambda before, order=order: order.append("purge:%s" % sorted(before)),
            learn_repo_guid=lambda *_a: order.append("learn"),
            seeded=False,
        )
        lic.License.seed_licensed_repo(fake)
        assert order[:2] == ["baseline-blobs", "create"], order
        assert ("purge:%s" % [OLD] in order) is expect_purge, order
        assert fake.seeded is (not expect_purge)
