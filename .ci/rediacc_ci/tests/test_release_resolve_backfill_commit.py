"""`rediacc_ci.release.resolve_backfill_commit` against the bytes its bash twin printed.

THE TWIN HAS BEEN DELETED. `.ci/scripts/release/resolve-backfill-commit.sh` had no call site outside its own usage header; the K=5 ledger `.ci/shadow/w7p5a-resolve-backfill-commit.observations.jsonl` holds five rows of equivalence over five distinct trees, and `goldens/resolve-backfill-commit/` holds the twin's OWN recorded bytes, captured on its last day in the tree. Each
golden's provenance header carries the blob sha, so `git cat-file -p <sha>` still yields the program that printed them.

EVERY CASE HERE RUNS AGAINST A THROWAWAY GIT REPOSITORY BUILT IN `tmp_path`, not against this checkout's own history, and the recording was taken the same way. The twin never `cd`ed -- it ran `git rev-list` / `git cat-file` / `git merge-base` against whatever repo the caller's cwd belonged to -- so a fixture repo with a controlled tag, a controlled `origin/main` (a plain ref,
no real remote needed: `git update-ref refs/remotes/origin/main <sha>` is enough for `merge-base --is-ancestor` to read it), and a controlled off-main commit is what lets the "reachable" and "not reachable from origin/main" arms be deterministic, without depending on this repository's history staying shaped the way it happens to be shaped today.

TWO COMMIT SHAS ARE MASKED, AND THE IDENTITY THEY CARRY IS ASSERTED LIVE INSTEAD. A fixture repository is rebuilt from scratch on every run and its commits carry that run's timestamps, so no sha can be frozen. `<main-tip>` and `<off-main>` therefore stand in for them in the recording, which is what makes the SHAPE comparable; the claim the mask would otherwise lose -- that the
resolved sha is the fixture's own main tip, and that the refused sha is the off-main commit -- is asserted directly against the port's unmasked output in the same case. The fixture root is masked for the same reason, and nothing else is touched.
"""

from __future__ import annotations

import os
import subprocess
from typing import TYPE_CHECKING

from rediacc_ci.tests import differential as diff
from rediacc_ci.tests import frozen

if TYPE_CHECKING:  # pathlib appears only in `tmp_path` annotations, never at runtime.
    import pathlib

TWIN_REL = ".ci/scripts/release/resolve-backfill-commit.sh"
MODULE = "resolve_backfill_commit"
SLUG = "resolve-backfill-commit"
OUT_MARK = "--- github-output ---\n"

# The operator-supplied sha that names no commit. A literal, because its whole property is that no repository can contain it.
BOGUS_SHA = "deadbeef" * 5

CASES = (
    "tag-resolves-and-is-reachable",
    "missing-tag",
    "operator-sha-that-does-not-exist",
    "operator-sha-not-reachable",
    "missing-version",
)


def _git(repo: pathlib.Path, *args: str) -> str:
    r = subprocess.run(
        ["git", *args],
        cwd=str(repo),
        capture_output=True,
        text=True,
        check=True,
        env=diff.env_for(),
    )
    return r.stdout.strip()


def _build_repo(repo: pathlib.Path) -> dict[str, str]:
    """A tiny repo: two commits on `main` (tagged v1.0.0 at the tip, tracked as `origin/main`), and one commit on a feature branch never merged into it.

    Returns the shas/tags a test needs, so a case reads as "which of these" rather than re-deriving offsets into the fixture's own history.
    """
    repo.mkdir(parents=True, exist_ok=True)
    env = diff.env_for(
        GIT_AUTHOR_NAME="w7p5a",
        GIT_AUTHOR_EMAIL="w7p5a@example.invalid",
        GIT_COMMITTER_NAME="w7p5a",
        GIT_COMMITTER_EMAIL="w7p5a@example.invalid",
    )
    run = lambda *args: subprocess.run(  # noqa: E731
        ["git", *args], cwd=str(repo), env=env, capture_output=True, text=True, check=True
    )
    run("init", "-q", "-b", "main")
    (repo / "f.txt").write_text("one\n", encoding="utf-8")
    run("add", "f.txt")
    run("commit", "-q", "-m", "first")
    (repo / "f.txt").write_text("two\n", encoding="utf-8")
    run("commit", "-aq", "-m", "second")
    main_tip = _git(repo, "rev-parse", "HEAD")
    run("tag", "v1.0.0", main_tip)
    # A plain ref is enough for `merge-base --is-ancestor <sha> origin/main` to read; no real remote or network is involved.
    run("update-ref", "refs/remotes/origin/main", main_tip)
    run("checkout", "-qb", "feature")
    (repo / "f.txt").write_text("off-main\n", encoding="utf-8")
    run("commit", "-aq", "-m", "unmerged")
    off_main_sha = _git(repo, "rev-parse", "HEAD")
    run("checkout", "-q", "main")
    return {"main_tip": main_tip, "off_main_sha": off_main_sha}


def mask(text: str, facts: dict[str, str]) -> str:
    """The two per-run commit shas, and only those."""
    return text.replace(facts["main_tip"], "<main-tip>").replace(
        facts["off_main_sha"], "<off-main>"
    )


def recorded(case: str) -> tuple[int, str, str, str]:
    """One golden, split back into exit code, stdout, stderr and the output file."""
    body, github_output = frozen.read(SLUG, case).split(OUT_MARK, 1)
    head, rest = body.split("\n--- stdout ---\n", 1)
    out, err = rest.split("--- stderr ---\n", 1)
    return int(head[len("exit: ") :]), out, err, github_output


def run_port(repo: pathlib.Path, env_extra: dict[str, str]) -> tuple[int, str, str, str]:
    """The port, over the fixture repo. Returns the UNMASKED streams and output file."""
    written = repo / "new-output.txt"
    env = diff.env_for(
        **env_extra,
        GITHUB_OUTPUT=str(written),
        PYTHONPATH=os.path.join(diff.repo(), ".ci"),
        PYTHONDONTWRITEBYTECODE="1",
    )
    code, out, err = diff.bash_streams(
        "python3 -m rediacc_ci.release.%s" % MODULE, env=env, cwd=str(repo), timeout=30
    )
    got = written.read_text(encoding="utf-8") if written.exists() else ""
    return code, out, err, got


def masked(
    run: tuple[int, str, str, str], facts: dict[str, str], repo: pathlib.Path
) -> tuple[int, str, str, str]:
    return (
        run[0],
        mask(run[1], facts),
        frozen.mask_root(mask(run[2], facts), repo),
        mask(run[3], facts),
    )


def test_tag_resolves_and_is_reachable(tmp_path: pathlib.Path) -> None:
    repo = tmp_path / "repo"
    facts = _build_repo(repo)
    old = recorded("tag-resolves-and-is-reachable")
    raw = run_port(repo, {"VERSION": "v1.0.0"})
    assert old[0] == 0
    assert old[2] == ""
    assert old[1] == "→ resolved v1.0.0 → <main-tip>\n✓ commit reachable from origin/main\n"
    assert old[3] == "commit_sha=<main-tip>\n"
    assert masked(raw, facts, repo) == old
    # WHAT THE MASK WOULD OTHERWISE LOSE, asserted against the port's own unmasked bytes.
    assert raw[3] == "commit_sha=%s\n" % facts["main_tip"]


def test_missing_tag_names_the_tag_byte_for_byte(tmp_path: pathlib.Path) -> None:
    repo = tmp_path / "repo"
    facts = _build_repo(repo)
    old = recorded("missing-tag")
    raw = run_port(repo, {"VERSION": "v9.9.9-does-not-exist"})
    assert old[0] == 1
    assert old[1] == (
        "::error::tag v9.9.9-does-not-exist not found in this checkout; pass commit_sha explicitly\n"
    )
    assert old[2] == ""
    assert masked(raw, facts, repo) == old


def test_operator_supplied_sha_that_does_not_exist_byte_for_byte(tmp_path: pathlib.Path) -> None:
    repo = tmp_path / "repo"
    facts = _build_repo(repo)
    old = recorded("operator-sha-that-does-not-exist")
    raw = run_port(repo, {"VERSION": "v1.0.0", "INPUT_SHA": BOGUS_SHA})
    assert old[0] == 1
    assert "commit %s does not name a commit" % BOGUS_SHA in old[1]
    assert "2026-08-23 git history rewrite" in old[1]
    assert masked(raw, facts, repo)[:2] == old[:2]


def test_operator_supplied_sha_not_reachable_from_origin_main(tmp_path: pathlib.Path) -> None:
    repo = tmp_path / "repo"
    facts = _build_repo(repo)
    old = recorded("operator-sha-not-reachable")
    raw = run_port(repo, {"VERSION": "v1.0.0", "INPUT_SHA": facts["off_main_sha"]})
    assert old[0] == 1
    assert old[1] == (
        "→ using operator-supplied commit_sha: <off-main>\n"
        "::error::commit <off-main> is not reachable from origin/main\n"
        "::error::refusing to backfill a sentinel for a detached tag\n"
    )
    assert old[2] == ""
    assert masked(raw, facts, repo) == old
    # WHAT THE MASK WOULD OTHERWISE LOSE: the refused sha is the fixture's own off-main commit.
    assert facts["off_main_sha"] in raw[1]


def test_missing_version_fails_the_same_way_reworded(tmp_path: pathlib.Path) -> None:
    """NOT BYTE-COMPARED, and the twin's recording says why: bash's own `${VAR:?msg}` diagnostic is line-numbered and names the shell, so the port has never matched it. What both sides owe is the exit code and the substance."""
    repo = tmp_path / "repo"
    _build_repo(repo)
    old = recorded("missing-version")
    raw = run_port(repo, {})
    assert old[0] == 1
    assert raw[0] == 1
    for stream in (old[2], raw[2]):
        assert "VERSION" in stream
        assert "must be set" in stream


def test_the_corpus_and_the_goldens_are_the_same_set() -> None:
    """ANTI-VACUITY on the corpus: a case whose golden vanished would pass by never being compared, and a golden nothing reads is a recording of a case that stopped running."""
    frozen.assert_corpus(SLUG, set(CASES))


def test_the_recording_holds_both_verdicts_and_a_non_empty_product() -> None:
    """A recording of refusals only would agree with a port that writes no output file at all, which is this script's whole product."""
    codes = {recorded(case)[0] for case in CASES}
    assert codes == {0, 1}, "the recording must hold a green and a red"
    assert any(recorded(case)[3] for case in CASES), "no case recorded a $GITHUB_OUTPUT write"
