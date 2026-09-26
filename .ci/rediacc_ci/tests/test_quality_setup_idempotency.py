"""`rediacc_ci.quality.setup_idempotency` against the awk and shell it replaces.

WHAT THIS FILE COVERS. The function-body extractor (an awk one-liner whose exact stop condition matters), the two settle oracles that decide whether a tree delta belongs to `setup --check` or to a neighbouring gate, and the four assertions that read a file rather than running one. The whole gate, including the E and C subprocesses, is covered by
`.ci/shadow/w7p2-setup-idempotency.observations.jsonl` over five distinct trees.
"""

import pathlib

import pytest

from rediacc_ci.quality import setup_idempotency as mod
from rediacc_ci.tests import differential as diff

# The awk extractor's edges. The comment on each names the property.
BODY_CASES = [
    ("before\nfoo() {\n  body\n}\nafter\n", "foo"),  # the ordinary one
    ("foo() {\n  if x; then\n  }\n  more\n}\n", "foo"),  # an INDENTED brace does not stop it
    ("foobar() {\n x\n}\n", "foo"),  # a longer name is not this name
    ("foo() {\n x\n}\nfoo() {\n y\n}\n", "foo"),  # the FIRST definition wins
    ("nothing here\n", "foo"),  # absent
    ("", "foo"),  # empty
    ("foo()  {\n x\n}\n", "foo"),  # two spaces before the brace: NOT matched
]


@pytest.mark.parametrize(("source", "name"), BODY_CASES)
def test_function_body_matches_awk(tmp_path: pathlib.Path, source: str, name: str) -> None:
    target = tmp_path / "lib.sh"
    target.write_text(source, encoding="utf-8")
    script = (
        'awk -v f=%s \'$0 ~ "^"f"\\\\(\\\\) \\\\{" {inside=1} inside {print} '
        "inside && /^}/ {exit}' lib.sh" % name
    )
    code, out, err = diff.bash_streams(script, cwd=str(tmp_path))
    assert code == 0, err
    # `$(...)` strips trailing newlines, which is what the twin captures.
    assert mod.function_body(source, name) == out.rstrip("\n")


def test_the_settle_oracle_ignores_a_neighbour_and_catches_a_real_change() -> None:
    """Two false accusations produced this shape; both are asserted here.

    2026-08-31: another gate's pid-suffixed fixture landed between the two snapshots. 2026-09-03: a TRACKED file the filter had no pattern for was open across them. The answer is a settle poll SCOPED to the delta paths.
    """
    before = "?? a.txt"
    after = "?? a.txt\n?? scratch.tmp"
    paths_watched = mod.delta_paths(before, after)
    assert paths_watched == "scratch.tmp"
    settled = "?? a.txt\n?? unrelated-neighbour.tmp"
    assert mod.scoped_to(settled, paths_watched) == mod.scoped_to(before, paths_watched)
    persisted = "?? a.txt\n?? scratch.tmp"
    assert mod.scoped_to(persisted, paths_watched) != mod.scoped_to(before, paths_watched)


def test_delta_paths_watches_both_directions() -> None:
    """A file that appeared and one that vanished are both ours to watch."""
    assert mod.delta_paths("?? a.txt\n?? gone.tmp", "?? a.txt") == "gone.tmp"


def test_the_fixture_noise_filter_is_narrow() -> None:
    """It must catch another gate's throwaway and nothing else."""
    assert mod.FIXTURE_NOISE_RE.search("?? .ci/scripts/.gate-paths-exist-noise-fixture.2530850.ts")
    assert not mod.FIXTURE_NOISE_RE.search(" M .ci/scripts/version/resolve-version.sh")


def test_check_g_judges_the_code_not_the_prose(tmp_path: pathlib.Path) -> None:
    """ORDER is the invariant, and comments are stripped before it is judged.

    The first version matched "private/renet/go.mod" inside the comment that EXPLAINS the ordering and concluded the correct code was broken.
    """
    report = mod.Report(colour={"RED": "", "GREEN": "", "NC": ""})
    ordered = tmp_path / "ordered.sh"
    ordered.write_text(
        "setup() {\n  bash init-submodules.sh\n  if ! ensure_docker_installed; then :; fi\n}\n",
        encoding="utf-8",
    )
    assert mod.check_g(report, ordered) is True

    late = tmp_path / "late.sh"
    late.write_text(
        "setup() {\n  if ! ensure_docker_installed; then :; fi\n  bash init-submodules.sh\n}\n",
        encoding="utf-8",
    )
    assert mod.check_g(report, late) is False

    commented = tmp_path / "commented.sh"
    commented.write_text(
        "setup() {\n  # reads private/renet/go.mod later on\n"
        "  bash init-submodules.sh\n  if ! ensure_docker_installed; then :; fi\n}\n",
        encoding="utf-8",
    )
    assert mod.check_g(report, commented) is True


def test_check_f_guards_the_class_not_the_instance(tmp_path: pathlib.Path) -> None:
    """The 2026-08-24 defect: a Path redirect with no Method 307s the API."""
    report = mod.Report(colour={"RED": "", "GREEN": "", "NC": ""})
    planted = tmp_path / "planted.sh"
    planted.write_text(
        'x --label "traefik.http.routers.${slug}-dbui.rule=Host(`x`) && Path(`/`)"\n'
        'y --label "traefik.http.middlewares.${slug}-dbui.redirectregex.regex=.*"\n',
        encoding="utf-8",
    )
    assert mod.check_f(report, planted) is False

    scoped = tmp_path / "scoped.sh"
    scoped.write_text(
        'x --label "traefik.http.routers.${slug}-dbui.rule=Host(`x`) && Path(`/`) '
        '&& Method(`GET`)"\n'
        'y --label "traefik.http.middlewares.${slug}-dbui.redirectregex.regex=.*"\n',
        encoding="utf-8",
    )
    assert mod.check_f(report, scoped) is True
