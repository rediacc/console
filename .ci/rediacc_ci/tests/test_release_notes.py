"""`rediacc_ci.release.release_notes`: the Release-Note grammar, the requirement rule, the collector and the body renderer.

The accept cases of agent/plans/PLAN-release-notes.md box RN1 are each one test below, named after the clause. The collector runs over a real fixture console with a real submodule, so the gitlink delta, the cross-repo dedup and the missing-object refusal are read from git, not mocked.
"""

from __future__ import annotations

import copy
import os
import shutil
import subprocess
import typing

import pytest

from rediacc_ci.controls import isolated_git_env
from rediacc_ci.release import release_notes as rn
from rediacc_ci.well_known import GH_ORIGIN, GH_REPO, SITE_ORIGIN

if typing.TYPE_CHECKING:
    import pathlib

CLI = ["packages/cli/src/x.ts"]
NOTE = "Backups now resume after a dropped connection"


def _msg(subject: str, *trailers: str) -> str:
    lines = [subject, "", "Body text explaining the change.", "", "PR-TASK: 79b7e92e", *trailers]
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- the RN1 accept clauses


def test_feat_on_customer_path_without_trailer_is_refused_and_passes_with_one():
    refused = rn.refusal(_msg("feat(cli): resume backups"), CLI, "console")
    assert "Release-Note:" in refused
    assert "packages/cli/src/x.ts" in refused
    assert (
        rn.refusal(_msg("feat(cli): resume backups", "Release-Note: " + NOTE), CLI, "console") == ""
    )


@pytest.mark.parametrize(
    "subject",
    ["Feat(cli): x", "feat(cli):x", "feat (cli): x", "FIX(cli) : x", "feat(cli) !: x", "Perf: x"],
)
def test_a_loosely_spelled_conventional_subject_still_owes_a_note(subject):
    """Review finding bdbf06a4.1: a subject the strict grammar missed read as exempt and skipped D2."""
    assert rn.subject_of(subject) is not None
    assert "Release-Note:" in rn.refusal(_msg(subject), CLI, "console")


def test_a_subject_outside_the_grammar_is_still_exempt():
    assert rn.subject_of('Revert "feat(cli): x"') is None
    assert rn.subject_of("Merge branch 'a'") is None
    assert rn.refusal(_msg('Revert "feat(cli): x"'), CLI, "console") == ""


def test_none_with_a_short_reason_is_refused():
    refused = rn.refusal(_msg("feat(cli): x", "Release-Note: none -- n/a"), CLI, "console")
    assert "Release-Note:" in refused
    assert "12 characters" in refused
    bare = rn.refusal(_msg("feat(cli): x", "Release-Note: none"), CLI, "console")
    assert "12 characters" in bare
    ok = rn.refusal(
        _msg("feat(cli): x", "Release-Note: none -- an internal refactor of the flag parser"),
        CLI,
        "console",
    )
    assert ok == ""


@pytest.mark.parametrize(
    "note",
    [
        "Fixed a crash in .ci/foo.py when the cache is cold",
        "Closes #d778be9d for backup restores",
        "Restores no longer hang (PLAN-release-notes)",
        "The check:ci-pr-task-trailers gate now passes",
        "Fixed in 334ed40864e0 for every machine",
        "The worklist now keeps every item",
        "Fixed packages/cli/src/x.ts",
    ],
)
def test_a_note_naming_an_internal_thing_is_refused(note):
    refused = rn.refusal(_msg("fix(cli): x", "Release-Note: " + note), CLI, "console")
    assert refused.startswith("invalid `Release-Note:` trailer"), refused
    assert "never a file" in refused


@pytest.mark.parametrize(
    "note",
    [
        "Node.js 24 is now supported on every machine",
        "Upgrades to v4.0.1 keep every repository and its data",
        "Mounts honour read/write flags after a reboot",
        f"The docs at {SITE_ORIGIN}/en/docs/a/b now list every flag",
        "`rdc repo fork` finishes in constant time on large repositories",
    ],
)
def test_customer_language_is_admitted(note):
    assert rn.refusal(_msg("feat(cli): x", "Release-Note: " + note), CLI, "console") == ""


def test_a_note_breaking_the_prose_style_is_refused():
    refused = rn.refusal(
        _msg("feat(cli): x", "Release-Note: You can now resume backups"), CLI, "console"
    )
    assert "prose style" in refused
    assert "R1" in refused
    refused = rn.refusal(
        _msg("feat(cli): x", "Release-Note: My backups now resume"), CLI, "console"
    )
    assert "R2" in refused


def test_a_note_over_the_limit_or_split_across_lines_is_refused():
    long_note = "Backups resume " + "and keep going " * 20
    assert "limit is 200" in rn.refusal(
        _msg("feat(cli): x", "Release-Note: " + long_note), CLI, "console"
    )
    split = rn.refusal(
        _msg("feat(cli): x", "Release-Note: Backups resume", "  after a dropped connection"),
        CLI,
        "console",
    )
    assert "one line" in split


def test_two_trailers_are_refused():
    refused = rn.refusal(
        _msg("feat(cli): x", "Release-Note: " + NOTE, "Release-Note: Restores are faster"),
        CLI,
        "console",
    )
    assert "one per commit" in refused


def test_fix_on_internal_paths_only_is_exempt():
    assert (
        rn.refusal(
            _msg("fix(hooks): guard"),
            [".claude/hooks/stop/a.py", ".claude/settings.json"],
            "console",
        )
        == ""
    )
    assert not rn.required("fix(hooks): guard", [".claude/hooks/stop/a.py"], "console")


def test_gitlink_bump_is_exempt():
    assert rn.refusal(_msg("chore(submodules): bump account"), ["private/account"], "console") == ""
    # A feat subject on a pure pointer bump is still exempt: the submodule commit carries the note.
    assert not rn.required("feat: bump account", ["private/account", "private/renet"], "console")


def test_exempt_types_never_owe_a_note_even_on_customer_paths():
    for subject in (
        "chore: x",
        "refactor(cli): x",
        "test(cli): x",
        "docs: x",
        "ci: x",
        'Revert "feat(cli): x"',
    ):
        assert not rn.required(subject, CLI, "console"), subject


def test_breaking_bang_and_perf_owe_a_note():
    assert rn.required("feat(cli)!: drop the old flag", CLI, "console")
    assert rn.required("perf: faster restore", CLI, "console")


def test_record_paths_are_exempt_through_record_paths_json():
    config = copy.deepcopy(rn.load_config())
    config["repos"]["console"]["internal"] = []
    assert not rn.required(
        "feat: plan", ["agent/plans/PLAN-x.md", "agent/INDEX.md"], "console", config
    )
    # The record list's `except` keeps epics.jsonl out of the record set, so with no internal glob it is a customer path.
    assert rn.required("feat: plan", ["agent/worklist/epics.jsonl"], "console", config)


def test_submodule_internal_globs_apply_per_repo():
    assert rn.required("fix(api): x", ["src/routes/a.ts"], "private/account")
    assert not rn.required("fix(api): x", ["tests/a.test.ts", "scripts/seed.ts"], "private/account")
    assert rn.required("fix: x", ["pkg/compose/up.go"], "private/renet")
    assert not rn.required(
        "fix: x", ["pkg/compose/up_test.go", ".github/workflows/ci.yml"], "private/renet"
    )
    # A repo outside the config owes nothing.
    assert not rn.required("feat: x", ["Formula/rdc.rb"], "private/homebrew-tap")


def test_an_exempt_commit_with_an_invalid_trailer_is_refused():
    refused = rn.refusal(_msg("chore: x", "Release-Note: none"), [".ci/a.py"], "console")
    assert "Release-Note:" in refused


# --------------------------------------------------------------------------- the trailer block, against git


TRAILER_CASES = [
    _msg("feat: x", "Release-Note: " + NOTE),
    _msg("feat: x", "Release-Note: " + NOTE)
    + "(cherry picked from commit 0123456789abcdef0123456789abcdef01234567)\n",
    "feat: x\n\nRelease-Note: only the subject paragraph above\n",
    "feat: x\n\nRelease-Note: "
    + NOTE
    + "\nThis line is prose, so the block is not a trailer block.\n",
    "feat: x\n\nprose one\nprose two\nprose three\nRelease-Note: "
    + NOTE
    + "\nSigned-off-by: A <a@b.c>\n",
    "feat: x\n\nprose one\nprose two\nprose three\nprose four\nprose five\nprose six\nprose seven\nRelease-Note: one\n(cherry picked from commit 0123456789abcdef0123456789abcdef01234567)\n",
    "Release-Note: in the subject line\n",
    "feat: x\n\nrelease-note: lower case key\n",
    "feat: x\n\nRelease-Note: first\n  continued\nPR-TASK: y\n",
]


def _git_trailers(msg: str) -> list[tuple[str, str]]:
    proc = subprocess.run(
        ["git", "interpret-trailers", "--parse", "--unfold", "--no-divider"],
        input=msg,
        capture_output=True,
        text=True,
        check=True,
    )
    out = []
    for line in proc.stdout.splitlines():
        key, _, value = line.partition(":")
        out.append((key, value.strip()))
    return out


@pytest.mark.parametrize("msg", TRAILER_CASES)
def test_the_trailer_block_matches_git_interpret_trailers(msg):
    ours = [(k, v) for k, v, _ in rn.trailers(msg)]
    theirs = _git_trailers(msg)
    # git also lists the cherry-pick line under no key; it is no `Key: value` trailer and parse() never needs it.
    theirs = [(k, v) for k, v in theirs if not k.startswith("(cherry picked from commit")]
    assert ours == theirs, msg


def test_a_landed_cherry_pick_keeps_its_trailer():
    msg = (
        _msg("feat: x", "Release-Note: " + NOTE)
        + "(cherry picked from commit 0123456789abcdef0123456789abcdef01234567)\n"
    )
    assert [t.text for t in rn.parse(msg)] == [NOTE]


def test_breaking_is_read_from_the_bang_and_the_footer():
    assert rn.is_breaking("feat(cli)!: x\n")
    assert rn.is_breaking("feat: x\n\nBREAKING CHANGE: the flag is gone\n")
    assert not rn.is_breaking("feat: x\n\nNothing breaks here.\n")


# --------------------------------------------------------------------------- the collector over a fixture console with a submodule


def _git(cwd: pathlib.Path, *args: str) -> str:
    env = dict(os.environ)
    env.update(
        GIT_AUTHOR_NAME="t",
        GIT_AUTHOR_EMAIL="t@example.invalid",
        GIT_COMMITTER_NAME="t",
        GIT_COMMITTER_EMAIL="t@example.invalid",
        GIT_CONFIG_GLOBAL=os.devnull,
        GIT_CONFIG_SYSTEM=os.devnull,
    )
    proc = subprocess.run(
        [
            "git",
            "-c",
            "protocol.file.allow=always",
            "-c",
            "core.hooksPath=/dev/null",
            "-c",
            "commit.gpgsign=false",
            *args,
        ],
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    return proc.stdout.strip()


_TICK = [1_700_000_000]


def _commit(repo: pathlib.Path, rel: str, msg: str) -> str:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(path.read_text() + "x\n" if path.exists() else "x\n")
    _git(repo, "add", "--", rel)
    _TICK[0] += 10
    stamp = "@%d +0000" % _TICK[0]
    os.environ["GIT_COMMITTER_DATE"] = stamp
    os.environ["GIT_AUTHOR_DATE"] = stamp
    try:
        _git(repo, "commit", "-q", "-m", msg)
    finally:
        os.environ.pop("GIT_COMMITTER_DATE", None)
        os.environ.pop("GIT_AUTHOR_DATE", None)
    return _git(repo, "rev-parse", "HEAD")


@pytest.fixture
def fixture_console(tmp_path):
    """A console with `private/account` as a real submodule, tag `v1.0.0` at the start of the range."""
    with isolated_git_env():
        upstream = tmp_path / "account-upstream"
        upstream.mkdir()
        _git(upstream, "init", "-q", "-b", "main")
        _commit(upstream, "src/a.ts", "chore: init")
        console = tmp_path / "console"
        console.mkdir()
        _git(console, "init", "-q", "-b", "main")
        _commit(console, "README.md", "chore: init")
        _git(console, "submodule", "add", "-q", str(upstream), "private/account")
        _git(console, "commit", "-q", "-m", "chore: add account")
        _git(console, "tag", "v1.0.0")
        yield console


def _config() -> dict:
    config = copy.deepcopy(rn.load_config())
    config["repos"] = {
        k: v for k, v in config["repos"].items() if k in ("console", "private/account")
    }
    return config


def test_collect_counts_each_submodule_note_once_and_collapses_identical_notes(fixture_console):
    console = fixture_console
    sub = console / "private" / "account"
    with isolated_git_env():
        s_feat = _commit(sub, "src/a.ts", _msg("feat(api): resume", "Release-Note: " + NOTE))
        _commit(
            sub,
            "src/b.ts",
            _msg("fix(api): restore", "Release-Note: Restores finish after a reboot."),
        )
        _commit(sub, "tests/a.test.ts", "test(api): cover resume\n")
        _commit(
            sub,
            "src/c.ts",
            _msg("fix(api): typo", "Release-Note: none -- an internal log message only"),
        )
        _git(console, "add", "--", "private/account")
        _git(console, "commit", "-q", "-m", "chore(submodules): bump account")
        # The same note landing on the console side collapses into the submodule's.
        _commit(
            console,
            "packages/cli/src/x.ts",
            _msg(
                "feat(cli): resume", "Release-Note: backups now resume after a dropped   connection"
            ),
        )
        _commit(console, ".claude/hooks/a.py", "fix(hooks): guard\n")
        collection = rn.collect("v1.0.0", "HEAD", console, _config())
    assert collection.offenders == []
    assert [(c.repo, c.note) for c in collection.notes] == [
        ("private/account", NOTE),
        ("private/account", "Restores finish after a reboot."),
    ]
    assert collection.notes[0].sha == s_feat
    assert collection.none_count == 1
    assert {c.repo for c in collection.commits} == {"console", "private/account"}
    assert len(collection.commits) == 7
    groups = rn.group(collection.notes, _config())
    assert groups == {"Added": [NOTE], "Fixed": ["Restores finish after a reboot."], "Improved": []}


def test_collect_names_a_trailerless_submodule_feat_as_an_offender(fixture_console):
    console = fixture_console
    sub = console / "private" / "account"
    with isolated_git_env():
        bad = _commit(sub, "src/a.ts", "feat(api): resume\n")
        _git(console, "add", "--", "private/account")
        _git(console, "commit", "-q", "-m", "chore(submodules): bump account")
        collection = rn.collect("v1.0.0", "HEAD", console, _config())
    assert [(c.repo, c.sha) for c in collection.offenders] == [("private/account", bad)]
    assert "Release-Note:" in collection.offenders[0].refusal


def test_collect_refuses_a_submodule_commit_that_is_not_present(fixture_console):
    console = fixture_console
    with isolated_git_env():
        missing = "0123456789abcdef0123456789abcdef01234567"
        _git(console, "update-index", "--cacheinfo", "160000,%s,private/account" % missing)
        _git(console, "commit", "-q", "-m", "chore(submodules): bump to an unfetched commit")
        with pytest.raises(rn.ReleaseNotesError, match="not present"):
            rn.collect("v1.0.0", "HEAD", console, _config())


def test_collect_refuses_a_submodule_that_is_not_checked_out(fixture_console):
    """Review finding bdbf06a4.3: an absent submodule directory raised FileNotFoundError, not the typed error."""
    console = fixture_console
    with isolated_git_env():
        missing = "0123456789abcdef0123456789abcdef01234567"
        _git(console, "update-index", "--cacheinfo", "160000,%s,private/account" % missing)
        _git(console, "commit", "-q", "-m", "chore(submodules): bump to an unfetched commit")
        shutil.rmtree(console / "private" / "account")
        with pytest.raises(rn.ReleaseNotesError, match="not checked out"):
            rn.collect("v1.0.0", "HEAD", console, _config())


def test_collect_ignores_a_git_dir_inherited_from_a_hook(fixture_console, monkeypatch):
    console = fixture_console
    with isolated_git_env():
        _commit(console / "private" / "account", "src/a.ts", "feat(api): x\n")
        _git(console, "add", "--", "private/account")
        _git(console, "commit", "-q", "-m", "chore(submodules): bump account")
        monkeypatch.setenv("GIT_DIR", str(console / ".git"))
        collection = rn.collect("v1.0.0", "HEAD", console, _config())
    assert [c.repo for c in collection.offenders] == ["private/account"]


# --------------------------------------------------------------------------- grouping and the body


def _note(note: str, type_: str = "feat", breaking: bool = False) -> rn.CommitNote:
    return rn.CommitNote("console", "0" * 40, "s", type_, breaking, 0, note, False, "")


def test_group_maps_types_and_prefixes_breaking():
    groups = rn.group(
        [
            _note("New flag", "feat"),
            _note("Old flag removed", "feat", breaking=True),
            _note("Crash fixed", "fix"),
            _note("Faster restore", "perf"),
            _note("Docs page added", "docs"),
        ]
    )
    assert groups == {
        "Added": ["New flag", "Breaking: Old flag removed"],
        "Fixed": ["Crash fixed"],
        "Improved": ["Faster restore", "Docs page added"],
    }


def test_render_markdown_carries_groups_orphan_stable_and_full_changelog():
    collection = rn.Collection(
        commits=[],
        notes=[_note("New flag"), _note("Crash fixed", "fix")],
        none_count=0,
        warnings=[],
    )
    doc = rn.document("4.0.1", "v3.0.1", collection, orphans=["v4.0.0"], stable="v3.0.1")
    body = rn.render_markdown(doc)
    assert body == (
        "## Added\n\n- New flag\n\n"
        "## Fixed\n\n- Crash fixed\n\n"
        "v4.0.0 was tagged but not published; its changes are listed here.\n\n"
        "Stable: v3.0.1, marked Latest; this is an edge release.\n\n"
        f"**Full Changelog**: {GH_ORIGIN}/{GH_REPO}/compare/v3.0.1...v4.0.1\n"
    )
    assert doc["version"] == "4.0.1"
    assert doc["stable"] == "3.0.1"


def test_render_markdown_says_so_when_the_range_holds_no_customer_note():
    empty = rn.Collection(commits=[], notes=[], none_count=3, warnings=[])
    body = rn.render_markdown(rn.document("v4.0.2", "v4.0.1", empty, orphans=["v4.0.0", "v4.0.1a"]))
    assert rn.EMPTY_LINE in body
    assert (
        "v4.0.0 and v4.0.1a were tagged but not published; their changes are listed here." in body
    )
    assert "Stable:" not in body


def test_the_shipped_config_is_well_formed():
    config = rn.load_config()
    assert set(config["repos"]) == {"console", "private/account", "private/renet"}
    assert config["required_types"] == ["feat", "fix", "perf"]
    assert set(config["groups"].values()) <= set(rn.GROUP_ORDER)
    for glob in (g for repo in config["repos"].values() for g in repo["internal"]):
        assert set(glob) & set("?[]{}") == set(), glob
