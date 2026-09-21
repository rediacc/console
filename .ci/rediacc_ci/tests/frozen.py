"""Goldens: a retired bash twin's own recorded bytes, and how a port is compared against them.

WHY A RECORDING RATHER THAN A DIFFERENTIAL. `differential.py` next door runs both implementations and compares them, which is the right instrument WHILE BOTH EXIST. It stops being available the moment the twin is deleted, and deleting the twin is the whole point of the port. The recipe here is the one W7 P6 used for
`goldens/standing-orders-brief/`: on the twin's last day in the tree, run it over every fixture the differential drove it with, capture exit code, stdout and stderr SEPARATELY, and write the bytes to a file. The port is then compared against that file forever. Nothing in a golden is a hand-written expectation, which is
the property that makes it evidence rather than a restatement of the port.

THE HEADER LINE NAMES THE SOURCE. Every golden opens with `# twin <path> blob <sha>`, where the sha is `git rev-parse HEAD:<path>` taken at recording time. The twin is gone from the working tree and retrievable from history with `git cat-file -p <sha>`, so a reader who doubts a recorded byte can read the program that
produced it.

WHAT IS NORMALIZED IS WHAT THE DIFFERENTIAL NORMALIZED, and no more. A golden that masks a value the differential compared is weaker than the comparison it replaced. Each caller declares its own normalizer and says why in its own docstring.

ANTI-VACUITY IS NOT OPTIONAL HERE. A comparison against a file on disk passes trivially if the file is missing and the test swallows the error, or if the corpus quietly shrank to nothing. `assert_corpus` is the guard: the case names the suite runs and the goldens on disk must be the same set, and every golden must be in
the recorded shape.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from rediacc_ci import paths

if TYPE_CHECKING:
    import pathlib

GOLDENS = paths.from_root(".ci", "rediacc_ci", "tests", "goldens")

HEADER_PREFIX = "# twin "
SHAPE_PREFIX = "exit: "


def mask_root(text: str, root: pathlib.Path) -> str:
    """Replace a fixture's absolute path with `<root>`, and its parent with `<base>`.

    THE ONE NORMALIZATION FREEZING ADDS. A differential ran both implementations over the SAME tempdir in the same second, so an absolute fixture path cancelled out and never had to be masked. A recording is compared against a tree built minutes or months later under a different tempdir name, so the path is the one token that cannot be compared. Everything else is still verbatim.
    """
    for path, token in ((root, "<root>"), (root.parent, "<base>")):
        for spelling in (str(path), str(path.resolve())):
            text = text.replace(spelling, token)
    return text


def directory(slug: str) -> pathlib.Path:
    """The golden directory for one retired twin."""
    return GOLDENS / slug


def render(returncode: int, stdout: str, stderr: str) -> str:
    """The recorded shape: one exit line, then the two streams under their own markers.

    The markers exist so that an empty stream is distinguishable from a missing one, and so that a stream ending without a newline is visible rather than glued to the next section.
    """
    return "exit: %d\n--- stdout ---\n%s--- stderr ---\n%s" % (returncode, stdout, stderr)


def write(slug: str, case: str, header: str, body: str) -> pathlib.Path:
    """Write one golden. Called by the one-shot recorder, never by the suite."""
    target = directory(slug)
    target.mkdir(parents=True, exist_ok=True)
    path = target / ("%s.golden" % case)
    path.write_text("%s%s\n%s" % (HEADER_PREFIX, header, body), encoding="utf-8")
    return path


def read(slug: str, case: str) -> str:
    """One golden's recorded body, with the provenance header stripped."""
    path = directory(slug) / ("%s.golden" % case)
    text = path.read_text(encoding="utf-8")
    if not text.startswith(HEADER_PREFIX):
        raise AssertionError("%s has no provenance header" % path)
    return text.split("\n", 1)[1]


def assert_corpus(slug: str, names: set[str]) -> None:
    """The two-way corpus check.

    A case whose golden vanished would pass by never being compared, and a golden nothing reads is a recording of a case that stopped running. Both are silent, so both are asserted.
    """
    target = directory(slug)
    on_disk = {p.stem for p in target.glob("*.golden")}
    if names != on_disk:
        raise AssertionError(
            "%s: case names and goldens disagree: only-in-cases=%r only-on-disk=%r"
            % (slug, sorted(names - on_disk), sorted(on_disk - names))
        )
    for path in sorted(target.glob("*.golden")):
        text = path.read_text(encoding="utf-8")
        if not text.startswith(HEADER_PREFIX):
            raise AssertionError("%s has no provenance header" % path)
        if not text.split("\n", 1)[1].startswith(SHAPE_PREFIX):
            raise AssertionError("%s is not in the recorded shape" % path)
