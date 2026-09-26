"""`rediacc_ci.deploy.r2_promote`'s pure pieces: the filter rule, the skip rule, the listing parser and the copy argv. The end-to-end contract is in the two promote test files."""

from __future__ import annotations

import datetime
import json

from rediacc_ci.deploy import r2_promote

T = datetime.datetime(2026, 9, 25, 12, 0, tzinfo=datetime.UTC)


def test_keep_follows_aws_cli_last_match_wins_default_include() -> None:
    assert r2_promote.keep("pool/a.deb", ())
    assert not r2_promote.keep("Packages.gz", ("--exclude", "Packages*"))
    assert r2_promote.keep("Packages.gz", ("--exclude", "*", "--include", "Packages*"))
    assert not r2_promote.keep("repodata/comps.xml", ("--exclude", "repodata/*"))
    # `*` crosses `/`, as aws-cli's fnmatch does.
    assert not r2_promote.keep("dists/stable/Packages.gz", ("--exclude", "*Packages*"))
    assert r2_promote.keep("a", ("--include", "a", "--exclude", "b"))


def test_unchanged_is_the_sync_skip_rule() -> None:
    src = r2_promote.Obj("a", 10, T)
    assert not r2_promote.unchanged(src, None)
    assert r2_promote.unchanged(src, r2_promote.Obj("a", 10, T))
    assert r2_promote.unchanged(src, r2_promote.Obj("a", 10, T + datetime.timedelta(seconds=1)))
    assert not r2_promote.unchanged(src, r2_promote.Obj("a", 10, T - datetime.timedelta(seconds=1)))
    assert not r2_promote.unchanged(src, r2_promote.Obj("a", 11, T + datetime.timedelta(days=1)))


def test_parse_listing_keeps_exact_keys_and_tolerates_an_empty_reply() -> None:
    reply = {
        "Contents": [
            {
                "Key": "apt/edge/b  two spaces.deb",
                "Size": 3,
                "LastModified": "2026-09-25T12:00:00.000Z",
            },
            {"Key": "apt/edge/", "Size": 0, "LastModified": "2026-09-25T12:00:00.000Z"},
            {"Key": "apt/edge/a.deb", "Size": 5, "LastModified": "2026-09-25T12:00:00+00:00"},
        ]
    }
    objs = r2_promote.parse_listing(json.dumps(reply), "apt/edge/")
    assert [o.rel for o in objs] == ["a.deb", "b  two spaces.deb"]
    assert objs[0] == r2_promote.Obj("a.deb", 5, T)
    assert r2_promote.parse_listing("", "apt/edge/") == []
    assert r2_promote.parse_listing('{"Prefix": "apt/edge/"}', "apt/edge/") == []


def test_copy_argv_is_a_server_side_copy_object_with_the_uploads_metadata() -> None:
    argv = r2_promote.copy_argv("cli/edge/manifest.json", "cli/stable/manifest.json", "https://x")
    assert argv[:3] == ["aws", "s3api", "copy-object"]
    assert argv[argv.index("--copy-source") + 1] == "rediacc-releases/cli/edge/manifest.json"
    assert argv[argv.index("--key") + 1] == "cli/stable/manifest.json"
    assert argv[argv.index("--metadata-directive") + 1] == "REPLACE"
    assert argv[argv.index("--cache-control") + 1] == "no-cache"
    assert argv[argv.index("--content-type") + 1] == "application/json"
    # R2 answers NotImplemented to a tagging directive; none is sent.
    assert not any("tagging" in a for a in argv)
    assert "--content-type" not in r2_promote.copy_argv(
        "a/edge/InRelease", "a/stable/InRelease", "https://x"
    )


def test_the_pointers_are_the_stamp_table() -> None:
    assert r2_promote.pointers("cli") == ("install.sh", "install.ps1")
    assert r2_promote.pointers("rpm") == ("rediacc.repo",)
    assert r2_promote.pointers("archlinux") == ("rediacc.conf",)
    assert r2_promote.pointers("apt") == r2_promote.pointers("apk") == ()
    assert r2_promote.POINTERS_GO_LAST is True
