"""Tests for `rediacc_ci.ops.r2_lifecycle` against a fake wrangler that keeps lifecycle state per bucket and prints in wrangler's own list format."""

from __future__ import annotations

import pytest

from rediacc_ci.ops import r2_lifecycle as r2


class FakeWrangler:
    def __init__(self, buckets, rules=None):
        self.buckets = list(buckets)
        self.rules = {b: list((rules or {}).get(b, [r2.Rule(r2.PLATFORM_DEFAULT_RULE, "", abort_days=7)])) for b in buckets}
        self.calls: list[tuple[str, ...]] = []

    def mutations(self):
        return [c for c in self.calls if c[:2] == ("bucket", "lifecycle") and c[2] in ("add", "remove")]

    def __call__(self, *args):
        self.calls.append(args)
        if args == ("bucket", "list"):
            return 0, "".join("name:           %s\ncreation_date:  2026-01-01T00:00:00Z\n\n" % b for b in self.buckets)
        if args[:3] == ("bucket", "lifecycle", "list"):
            out = ""
            for r in self.rules[args[3]]:
                out += "name:     %s\nenabled:  Yes\nprefix:   %s\n" % (r.name, r.prefix or "(all prefixes)")
                if r.abort_days is not None:
                    out += "action:   Abort incomplete multipart uploads after %d days\n" % r.abort_days
                if r.expire_days is not None:
                    out += "action:   Delete objects after %d days\n" % r.expire_days
                out += "\n"
            return 0, out
        if args[:3] == ("bucket", "lifecycle", "add"):
            bucket, name, prefix = args[3:6]
            exp = args[args.index("--expire-days") + 1] if "--expire-days" in args else None
            ab = args[args.index("--abort-multipart-days") + 1] if "--abort-multipart-days" in args else None
            self.rules[bucket].append(r2.Rule(name, prefix, int(exp) if exp else None, int(ab) if ab else None))
            return 0, ""
        if args[:3] == ("bucket", "lifecycle", "remove"):
            bucket, name = args[3], args[args.index("--name") + 1]
            self.rules[bucket] = [r for r in self.rules[bucket] if r.name != name]
            return 0, ""
        raise AssertionError(args)


BUCKETS = ["rediacc-releases", "rediacc-backups-eu", "rediacc-configs", "rediacc-www-media"]


def test_first_apply_adds_twelve_rules_plus_multipart():
    w = FakeWrangler(BUCKETS)
    assert r2.run_mode(w, "apply") == 0
    adds = [c for c in w.mutations() if c[2] == "add"]
    assert len(adds) == 13
    assert {c[3] for c in adds} == {"rediacc-releases"}
    assert ("bucket", "lifecycle", "add", "rediacc-releases", "spend-guard-pr-cli", "cli/pr-", "--expire-days", "14", "-y") in w.calls
    assert ("bucket", "lifecycle", "add", "rediacc-releases", "spend-guard-dryrun-apk", "apk/dryrun-", "--expire-days", "21", "-y") in w.calls
    assert ("bucket", "lifecycle", "add", "rediacc-releases", r2.MULTIPART_RULE, "", "--abort-multipart-days", "1", "-y") in w.calls


def test_second_apply_changes_nothing():
    w = FakeWrangler(BUCKETS)
    r2.run_mode(w, "apply")
    w.calls.clear()
    assert r2.run_mode(w, "apply") == 0
    assert w.mutations() == []


def test_changed_window_updates_exactly_one_rule():
    w = FakeWrangler(BUCKETS)
    r2.run_mode(w, "apply")
    w.rules["rediacc-releases"] = [
        r2.Rule(r.name, r.prefix, 30 if r.name == "spend-guard-pr-npm" else r.expire_days, r.abort_days)
        for r in w.rules["rediacc-releases"]
    ]
    w.calls.clear()
    assert r2.run_mode(w, "check") == 1
    assert r2.run_mode(w, "apply") == 0
    assert [c[2] for c in w.mutations()] == ["remove", "add"]
    assert all("spend-guard-pr-npm" in c for c in w.mutations())
    assert r2.run_mode(w, "check") == 0


def test_check_fails_on_missing_rule_and_never_writes():
    w = FakeWrangler(BUCKETS)
    assert r2.run_mode(w, "check") == 1
    assert w.mutations() == []


@pytest.mark.parametrize("bucket", ["rediacc-backups-eu", "rediacc-configs", "edge-rediacc-backups-us", "rediacc-configs-bench", "rediacc-www-media"])
def test_protected_and_unlisted_buckets_are_refused_before_any_call(bucket):
    w = FakeWrangler(BUCKETS)
    assert r2.run_mode(w, "apply", bucket=bucket) == 2
    assert w.calls == []
    with pytest.raises(r2.RefusedBucket):
        r2.require_writable(bucket)


def test_mutation_helpers_refuse_a_backup_bucket_directly():
    w = FakeWrangler(BUCKETS)
    with pytest.raises(r2.RefusedBucket):
        r2._add(w, "rediacc-backups-eu", r2.desired_rules()[0])
    with pytest.raises(r2.RefusedBucket):
        r2._remove(w, "rediacc-configs", "x")
    assert w.calls == []


def test_apply_never_touches_protected_buckets():
    w = FakeWrangler(BUCKETS)
    r2.run_mode(w, "apply")
    assert not [c for c in w.mutations() if c[3] != "rediacc-releases"]


def test_planted_rule_on_a_backup_bucket_is_reported():
    planted = {"rediacc-backups-eu": [r2.Rule("evil", "chunks/", expire_days=1)]}
    w = FakeWrangler(BUCKETS, planted)
    r2.run_mode(w, "apply")
    assert r2.run_mode(w, "check") == 1
    assert w.mutations()[-1][3] == "rediacc-releases"  # reported, never removed


def test_staging_bucket_gets_rules_only_when_listed():
    w = FakeWrangler(BUCKETS + [r2.STAGING_BUCKET])
    r2.run_mode(w, "apply")
    assert {c[3] for c in w.mutations()} == {"rediacc-releases", r2.STAGING_BUCKET}


def test_no_allowed_bucket_in_listing_exits_2():
    assert r2.run_mode(FakeWrangler(["rediacc-backups-eu"]), "apply") == 2


def test_dry_run_writes_nothing():
    w = FakeWrangler(BUCKETS)
    assert r2.run_mode(w, "apply", dry_run=True) == 0
    assert w.mutations() == []


def test_parse_rules_reads_wrangler_default_rule():
    text = "name:     Default Multipart Abort Rule\nenabled:  Yes\nprefix:   (all prefixes)\naction:   Abort incomplete multipart uploads after 7 days\n"
    assert r2.parse_rules(text) == [r2.Rule("Default Multipart Abort Rule", "", None, 7)]


def test_failed_add_raises():
    def failing(*args):
        if args == ("bucket", "list"):
            return 0, "name: rediacc-releases\n"
        if args[:3] == ("bucket", "lifecycle", "list"):
            return 0, ""
        return 1, "boom"

    with pytest.raises(RuntimeError):
        r2.run_mode(failing, "apply")


def test_protected_pattern_refuses_even_if_the_allowlist_were_widened(monkeypatch):
    monkeypatch.setattr(r2, "ALLOWED_BUCKETS", (*r2.ALLOWED_BUCKETS, "rediacc-backups-eu", "rediacc-configs"))
    w = FakeWrangler(BUCKETS)
    for b in ("rediacc-backups-eu", "rediacc-configs"):
        with pytest.raises(r2.RefusedBucket, match="never get lifecycle rules"):
            r2.require_writable(b)
    with pytest.raises(r2.RefusedBucket):
        r2.run_mode(w, "apply")
    assert w.mutations() == []
