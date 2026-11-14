"""Tests for `rediacc_ci.ops.r2_lifecycle` against a fake wrangler that keeps lifecycle state per bucket and prints in wrangler's own list format."""

from __future__ import annotations

import pytest

from rediacc_ci.ops import r2_lifecycle as r2


class FakeWrangler:
    def __init__(self, buckets, rules=None):
        self.buckets = list(buckets)
        self.rules = {
            b: list((rules or {}).get(b, [r2.Rule(r2.PLATFORM_DEFAULT_RULE, "", abort_days=7)]))
            for b in buckets
        }
        self.calls: list[tuple[str, ...]] = []

    def list_buckets(self):
        return list(self.buckets)

    def mutations(self):
        return [
            c for c in self.calls if c[:2] == ("bucket", "lifecycle") and c[2] in ("add", "remove")
        ]

    def __call__(self, *args):
        self.calls.append(args)
        if args == ("bucket", "list"):
            # wrangler's own listing stops at 20 buckets and has no pagination
            return 0, "".join(
                "name:           %s\ncreation_date:  2026-01-01T00:00:00Z\n\n" % b
                for b in self.buckets[:20]
            )
        if args[:2] == ("bucket", "info"):
            if args[2] in self.buckets:
                return 0, "name: %s\n" % args[2]
            return 1, "The specified bucket does not exist. [code: 10006]"
        if args[:3] == ("bucket", "lifecycle", "list"):
            out = ""
            for r in self.rules[args[3]]:
                out += "name:     %s\nenabled:  Yes\nprefix:   %s\n" % (
                    r.name,
                    r.prefix or "(all prefixes)",
                )
                if r.abort_days is not None:
                    out += (
                        "action:   Abort incomplete multipart uploads after %d days\n"
                        % r.abort_days
                    )
                if r.expire_days is not None:
                    out += "action:   Delete objects after %d days\n" % r.expire_days
                out += "\n"
            return 0, out
        if args[:3] == ("bucket", "lifecycle", "add"):
            bucket, name, prefix = args[3:6]
            exp = args[args.index("--expire-days") + 1] if "--expire-days" in args else None
            ab = (
                args[args.index("--abort-multipart-days") + 1]
                if "--abort-multipart-days" in args
                else None
            )
            self.rules[bucket].append(
                r2.Rule(name, prefix, int(exp) if exp else None, int(ab) if ab else None)
            )
            return 0, ""
        if args[:3] == ("bucket", "lifecycle", "remove"):
            bucket, name = args[3], args[args.index("--name") + 1]
            self.rules[bucket] = [r for r in self.rules[bucket] if r.name != name]
            return 0, ""
        raise AssertionError(args)


BUCKETS = [r2.RELEASES_BUCKET, "rediacc-backups-eu", "rediacc-configs", "rediacc-www-media"]


def test_first_apply_adds_twelve_rules_plus_multipart():
    w = FakeWrangler(BUCKETS)
    assert r2.run_mode(w, "apply") == 0
    adds = [c for c in w.mutations() if c[2] == "add"]
    assert len(adds) == 13
    assert {c[3] for c in adds} == {r2.RELEASES_BUCKET}
    assert (
        "bucket",
        "lifecycle",
        "add",
        r2.RELEASES_BUCKET,
        "spend-guard-pr-cli",
        "cli/pr-",
        "--expire-days",
        "14",
        "-y",
    ) in w.calls
    assert (
        "bucket",
        "lifecycle",
        "add",
        r2.RELEASES_BUCKET,
        "spend-guard-dryrun-apk",
        "apk/dryrun-",
        "--expire-days",
        "21",
        "-y",
    ) in w.calls
    assert (
        "bucket",
        "lifecycle",
        "add",
        r2.RELEASES_BUCKET,
        r2.MULTIPART_RULE,
        "",
        "--abort-multipart-days",
        "1",
        "-y",
    ) in w.calls


def test_second_apply_changes_nothing():
    w = FakeWrangler(BUCKETS)
    r2.run_mode(w, "apply")
    w.calls.clear()
    assert r2.run_mode(w, "apply") == 0
    assert w.mutations() == []


def test_changed_window_updates_exactly_one_rule():
    w = FakeWrangler(BUCKETS)
    r2.run_mode(w, "apply")
    w.rules[r2.RELEASES_BUCKET] = [
        r2.Rule(
            r.name, r.prefix, 30 if r.name == "spend-guard-pr-npm" else r.expire_days, r.abort_days
        )
        for r in w.rules[r2.RELEASES_BUCKET]
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


def test_a_green_check_names_the_rules_it_matched(capsys):
    w = FakeWrangler(BUCKETS)
    r2.run_mode(w, "apply")
    capsys.readouterr()
    assert r2.run_mode(w, "check") == 0
    wanted = len(r2.desired_rules())
    assert (
        "%s: %d of %d rule(s) match" % (r2.RELEASES_BUCKET, wanted, wanted)
        in capsys.readouterr().out
    )


def test_a_red_check_counts_only_the_rules_that_match(capsys):
    w = FakeWrangler(BUCKETS)
    r2.run_mode(w, "apply")
    gone, moved = (r.name for r in r2.desired_rules()[:2])
    # One rule removed and one drifted: the count leaves out both, beside their MISSING and DRIFTED lines.
    w.rules[r2.RELEASES_BUCKET] = [
        r2.Rule(r.name, r.prefix, (r.expire_days or 0) + 1, r.abort_days) if r.name == moved else r
        for r in w.rules[r2.RELEASES_BUCKET]
        if r.name != gone
    ]
    capsys.readouterr()
    assert r2.run_mode(w, "check") == 1
    out = capsys.readouterr().out
    wanted = len(r2.desired_rules())
    assert "MISSING %s: %s" % (r2.RELEASES_BUCKET, gone) in out
    assert "DRIFTED %s: %s" % (r2.RELEASES_BUCKET, moved) in out
    assert "%s: %d of %d rule(s) match" % (r2.RELEASES_BUCKET, wanted - 2, wanted) in out


@pytest.mark.parametrize(
    "bucket",
    [
        "rediacc-backups-eu",
        "rediacc-configs",
        "edge-rediacc-backups-us",
        "rediacc-configs-bench",
        "rediacc-www-media",
        "backups-eu",
        "configs-eu",
        "backups-bench",
        "configs-staging",
        "media",
    ],
)
def test_protected_and_unlisted_buckets_are_refused_before_any_call(bucket):
    w = FakeWrangler(BUCKETS)
    assert r2.run_mode(w, "apply", bucket=bucket) == 2
    assert w.calls == []
    with pytest.raises(r2.RefusedBucketError):
        r2.require_writable(bucket)


def test_mutation_helpers_refuse_a_backup_bucket_directly():
    w = FakeWrangler(BUCKETS)
    with pytest.raises(r2.RefusedBucketError):
        r2._add(w, "rediacc-backups-eu", r2.desired_rules()[0])
    with pytest.raises(r2.RefusedBucketError):
        r2._remove(w, "rediacc-configs", "x")
    assert w.calls == []


def test_apply_never_touches_protected_buckets():
    w = FakeWrangler(BUCKETS)
    r2.run_mode(w, "apply")
    assert not [c for c in w.mutations() if c[3] != r2.RELEASES_BUCKET]


def test_planted_rule_on_a_backup_bucket_is_reported():
    planted = {"rediacc-backups-eu": [r2.Rule("evil", "chunks/", expire_days=1)]}
    w = FakeWrangler(BUCKETS, planted)
    r2.run_mode(w, "apply")
    assert r2.run_mode(w, "check") == 1
    assert w.mutations()[-1][3] == r2.RELEASES_BUCKET  # reported, never removed


# PLAN-product-domain-rename W6: the shared names carry no `rediacc-` prefix, so `*-backups-*` and `rediacc-backups*` never matched them, and a planted lifecycle rule on `backups-eu` read as a clean bucket.
@pytest.mark.parametrize(
    "bucket",
    ["backups-eu", "backups-us", "backups-asia", "backups-bench", "configs-eu", "configs-staging"],
)
def test_the_shared_backup_and_config_names_are_protected(bucket):
    assert r2.is_protected(bucket)
    with pytest.raises(r2.RefusedBucketError, match="never get lifecycle rules"):
        r2.require_writable(bucket)


def test_a_planted_rule_on_a_shared_backup_bucket_is_reported():
    planted = {"backups-eu": [r2.Rule("evil", "chunks/", expire_days=1)]}
    w = FakeWrangler([r2.RELEASES_BUCKET, "backups-eu"], planted)
    r2.run_mode(w, "apply")
    assert r2.run_mode(w, "check") == 1
    assert not [c for c in w.mutations() if c[3] == "backups-eu"]


def test_the_releases_and_media_buckets_are_not_protected():
    assert not r2.is_protected(r2.RELEASES_BUCKET)
    assert not r2.is_protected("media")


def test_staging_bucket_gets_rules_only_when_listed():
    w = FakeWrangler([*BUCKETS, r2.STAGING_BUCKET])
    r2.run_mode(w, "apply")
    assert {c[3] for c in w.mutations()} == {r2.RELEASES_BUCKET, r2.STAGING_BUCKET}


def test_no_allowed_bucket_in_listing_exits_2():
    assert r2.run_mode(FakeWrangler(["rediacc-backups-eu"]), "apply") == 2


def _crowded(*extra):
    """Twenty-two unrelated buckets first, so anything in `extra` sits past wrangler's 20-bucket listing."""
    return [*("filler-%02d" % i for i in range(22)), *extra]


def test_target_past_the_twentieth_bucket_is_found():
    w = FakeWrangler(_crowded(r2.RELEASES_BUCKET))
    assert r2.run_mode(w, "apply") == 0
    assert {c[3] for c in w.mutations()} == {r2.RELEASES_BUCKET}


def test_protected_bucket_past_the_twentieth_is_audited():
    planted = {"backups-eu": [r2.Rule("evil", "chunks/", expire_days=1)]}
    w = FakeWrangler(_crowded(r2.RELEASES_BUCKET, "backups-eu"), planted)
    assert r2.run_mode(w, "check") == 1
    assert ("bucket", "lifecycle", "list", "backups-eu") in w.calls


def test_an_incomplete_listing_fails_loudly_instead_of_auditing_a_partial_one():
    class Truncated(FakeWrangler):
        def list_buckets(self):
            raise RuntimeError("complete bucket listing unavailable: test")

    with pytest.raises(RuntimeError, match="complete bucket listing unavailable"):
        r2.run_mode(Truncated(BUCKETS), "check")


def test_bucket_info_failure_other_than_not_found_raises():
    def run(*_a):
        return 1, "Authentication error [code: 10000]"

    with pytest.raises(RuntimeError, match="bucket info"):
        r2.bucket_exists(run, r2.RELEASES_BUCKET)


@pytest.mark.parametrize(
    "out",
    [
        "Authentication error [code: 10000]: token not found",
        "fetch failed: host not found (ENOTFOUND api.cloudflare.com)",
    ],
)
def test_an_unrelated_failure_mentioning_not_found_is_not_an_absent_bucket(out):
    with pytest.raises(RuntimeError, match="bucket info"):
        r2.bucket_exists(lambda *_a: (1, out), r2.RELEASES_BUCKET)


@pytest.mark.parametrize(
    "out",
    ["The specified bucket does not exist. [code: 10006]", "bucket not found [code: 10006]"],
)
def test_a_real_not_found_answer_is_an_absent_bucket(out):
    assert r2.bucket_exists(lambda *_a: (1, out), "x") is False


@pytest.mark.parametrize("entry", ["oops", {"nom": "x"}, {"name": None}, {"name": 5}])
def test_list_all_buckets_refuses_a_malformed_entry(entry):
    def get(*_a):
        return {"success": True, "result": {"buckets": [{"name": "a"}, entry]}}

    with pytest.raises(RuntimeError, match="no name"):
        r2.list_all_buckets(get, [], "acct")


def test_list_all_buckets_accepts_well_formed_entries_control():
    def get(*_a):
        return _page(["a", "b"])

    assert r2.list_all_buckets(get, [], "acct") == ["a", "b"]


def test_wrangler_runs_the_verified_binary_without_a_real_install(monkeypatch, tmp_path):
    fake = tmp_path / "wrangler"
    fake.write_text("")
    monkeypatch.setattr(r2.wrangler, "local_binary", lambda _cwd: fake)
    w = r2.Wrangler({"CLOUDFLARE_API_TOKEN": "t", "CLOUDFLARE_ACCOUNT_ID": "a"})
    assert w.argv == [str(fake)]


def _page(names, cursor=""):
    return {
        "success": True,
        "result": {"buckets": [{"name": n} for n in names]},
        "result_info": {"cursor": cursor, "per_page": 2},
    }


def test_list_all_buckets_follows_the_cursor():
    pages = {"": _page(["a", "b"], "c1"), "c1": _page(["c"])}
    urls: list[str] = []

    def get(_method, url, _headers):
        urls.append(url)
        return pages[url.partition("cursor=")[2]]

    assert r2.list_all_buckets(get, [], "acct") == ["a", "b", "c"]
    assert "cursor=c1" in urls[1]


def test_list_all_buckets_refuses_a_stuck_cursor_and_an_error_reply():
    def stuck(*_a):
        return _page(["a"], "same")

    def bad(*_a):
        return {"success": False, "errors": [{"message": "nope"}]}

    with pytest.raises(RuntimeError, match="did not advance"):
        r2.list_all_buckets(stuck, [], "acct")
    with pytest.raises(RuntimeError, match="complete bucket listing unavailable"):
        r2.list_all_buckets(bad, [], "acct")


def test_list_all_buckets_refuses_a_full_page_with_no_cursor():
    def full(*_a):
        return _page(["b%d" % i for i in range(r2.LIST_PAGE)])

    with pytest.raises(RuntimeError, match="no cursor"):
        r2.list_all_buckets(full, [], "acct")


def test_dry_run_writes_nothing():
    w = FakeWrangler(BUCKETS)
    assert r2.run_mode(w, "apply", dry_run=True) == 0
    assert w.mutations() == []


def test_parse_rules_reads_wrangler_default_rule():
    text = "name:     Default Multipart Abort Rule\nenabled:  Yes\nprefix:   (all prefixes)\naction:   Abort incomplete multipart uploads after 7 days\n"
    assert r2.parse_rules(text) == [r2.Rule("Default Multipart Abort Rule", "", None, 7)]


def test_failed_add_raises():
    class Failing(FakeWrangler):
        def __call__(self, *args):
            if args[:3] == ("bucket", "lifecycle", "add"):
                return 1, "boom"
            return super().__call__(*args)

    with pytest.raises(RuntimeError, match="lifecycle add"):
        r2.run_mode(Failing([r2.RELEASES_BUCKET]), "apply")


def test_a_failed_replacement_restores_the_drifted_rule():
    """Review d945e387.2: remove-then-add must not leave the bucket without the prefix's rule when the add fails."""
    w = FakeWrangler(BUCKETS)
    r2.run_mode(w, "apply")
    old = next(r for r in w.rules[r2.RELEASES_BUCKET] if r.name == "spend-guard-pr-npm")
    w.rules[r2.RELEASES_BUCKET] = [
        r2.Rule(r.name, r.prefix, 30 if r is old else r.expire_days, r.abort_days)
        for r in w.rules[r2.RELEASES_BUCKET]
    ]
    drifted = next(r for r in w.rules[r2.RELEASES_BUCKET] if r.name == "spend-guard-pr-npm")
    adds = {"n": 0}

    class Flaky(FakeWrangler):
        def __call__(self, *args):
            if args[:3] == ("bucket", "lifecycle", "add") and args[4] == "spend-guard-pr-npm":
                adds["n"] += 1
                if adds["n"] == 1:
                    return 1, "boom"
            return w(*args)

        def list_buckets(self):
            return w.list_buckets()

    with pytest.raises(RuntimeError, match="was restored"):
        r2.run_mode(Flaky(BUCKETS), "apply")
    assert drifted in w.rules[r2.RELEASES_BUCKET], "the rule that existed is back"


def test_protected_pattern_refuses_even_if_the_allowlist_were_widened(monkeypatch):
    monkeypatch.setattr(
        r2, "ALLOWED_BUCKETS", (*r2.ALLOWED_BUCKETS, "rediacc-backups-eu", "rediacc-configs")
    )
    w = FakeWrangler(BUCKETS)
    for b in ("rediacc-backups-eu", "rediacc-configs"):
        with pytest.raises(r2.RefusedBucketError, match="never get lifecycle rules"):
            r2.require_writable(b)
    with pytest.raises(r2.RefusedBucketError):
        r2.run_mode(w, "apply")
    assert w.mutations() == []
