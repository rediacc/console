"""`rediacc_ci.quality.probe_parity` against its bash twin.

A bash child runs the REAL `.ci/scripts/quality/check-probe-parity.sh` over a git
fixture with stdout and stderr captured SEPARATELY, and its bytes are compared
against the port's. Same recipe as the committed ledger,
`.ci/shadow/w7p2-probe-parity.observations.jsonl`.

WHY A FIXTURE REPOSITORY AND NOT THE REAL TREE. The twin resolves its root from
its OWN location (`get_repo_root` walks three directories up from
`.ci/scripts/lib`), so both implementations have to live inside whatever tree the
case wants judged. That is also the recording recipe's constraint: the comparator
refuses a command reading outside the recorded root.

THE CASES ARE BOTH DIRECTIONS ON PURPOSE. A gate that only ever fires is as
useless as one that never does, and this one is a SET COVERAGE question with two
symmetrical ways to be wrong: forgive everything (report parity always) or
forgive nothing (report every verb missing). So the corpus carries a clean pair,
a gap, the exemption being honoured, the exemption NOT being over-applied, and
both empty-extraction controls, which are the branches the twin's missing
`|| true` made unreachable until 96355d3b5 on 2026-09-06.
"""

import pathlib
import shutil
import subprocess

import pytest

from rediacc_ci.quality import probe_parity as gate
from rediacc_ci.tests import differential as diff

TWIN = ".ci/scripts/quality/check-probe-parity.sh"
MODULE = "probe_parity"


def build(tmp_path: pathlib.Path, consumer: str | None, probe: str | None) -> pathlib.Path:
    """A git specimen holding BOTH implementations plus the two subject files.

    `None` means the file is ABSENT, which is the `require_input` branch. It is a
    distinct case from "present but empty": one is a missing input and the other
    is a collapsed extraction, and the twin says different things about them.
    """
    src = pathlib.Path(diff.repo())
    root = tmp_path / "fixture"
    (root / ".ci" / "scripts" / "quality").mkdir(parents=True)
    (root / ".ci" / "rediacc_ci" / "quality").mkdir(parents=True)
    (root / "packages" / "cli" / "src" / "utils").mkdir(parents=True)
    (root / "scripts" / "drills").mkdir(parents=True)
    shutil.copytree(src / ".ci" / "scripts" / "lib", root / ".ci" / "scripts" / "lib")
    shutil.copy2(src / TWIN, root / TWIN)
    for name in ("__init__.py", "log.py", "paths.py", "controls.py"):
        shutil.copy2(src / ".ci" / "rediacc_ci" / name, root / ".ci" / "rediacc_ci" / name)
    for name in ("__init__.py", "%s.py" % MODULE):
        shutil.copy2(
            src / ".ci" / "rediacc_ci" / "quality" / name,
            root / ".ci" / "rediacc_ci" / "quality" / name,
        )
    if consumer is not None:
        (root / gate.CONSUMER).write_text(consumer, encoding="utf-8")
    if probe is not None:
        (root / gate.PROBE).write_text(probe, encoding="utf-8")
    return root


def run_both(root: pathlib.Path) -> tuple[tuple[int, str, str], tuple[int, str, str]]:
    """Both implementations over one specimen, streams never merged."""
    old = diff.bash_streams("bash %s" % TWIN, cwd=str(root))
    new = diff.bash_streams(
        "PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.ci python3 -m rediacc_ci.quality.%s" % MODULE,
        cwd=str(root),
    )
    return old, new


# (label, consumer text or None, probe text or None, expected exit)
CASES = [
    (
        "clean: the probe exercises every consumer verb",
        "execFileSync('keyctl', ['add', k]);\nexecFileSync('keyctl', ['pipe', k]);\n",
        "keyctl add @u\nkeyctl pipe @u\n",
        0,
    ),
    (
        "gap: one consumer verb is never probed",
        "execFileSync('keyctl', ['add', k]);\nexecFileSync('keyctl', ['pipe', k]);\n",
        "keyctl add @u\n",
        1,
    ),
    (
        # THE EXEMPTION, POSITIVE HALF. `unlink` is cleanup-only, so a probe that purges instead is parity. Without this case the exemption could be deleted and every test would still pass.
        "exemption: a cleanup-only verb is forgiven",
        "execFileSync('keyctl', ['add', k]);\nexecFileSync('keyctl', ['unlink', k]);\n",
        "keyctl add @u\nkeyctl purge user x\n",
        0,
    ),
    (
        # THE EXEMPTION, NEGATIVE HALF. `search` is NOT on the list, so the same shape must still fire. A blanket exemption would pass the case above and fail this one.
        "exemption: a non-cleanup verb is not forgiven",
        "execFileSync('keyctl', ['add', k]);\nexecFileSync('keyctl', ['search', k]);\n",
        "keyctl add @u\n",
        1,
    ),
    (
        # THE FOUNDING DEFECT. A verb named only in the preflight's own comment must not count as exercised.
        "prose: a verb mentioned in a comment does not count as probed",
        "execFileSync('keyctl', ['add', k]);\nexecFileSync('keyctl', ['pipe', k]);\n",
        "keyctl add @u\n# then we would keyctl pipe it back\n",
        1,
    ),
    (
        "control: an empty consumer extraction refuses rather than passing",
        "// nothing here calls keyctl any more\n",
        "keyctl add @u\nkeyctl pipe @u\n",
        1,
    ),
    (
        "control: an empty probe extraction refuses rather than passing",
        "execFileSync('keyctl', ['add', k]);\n",
        "# keyctl add is only described here\necho hi\n",
        1,
    ),
    (
        "require_input: an absent consumer is a failure, not a skip",
        None,
        "keyctl add @u\n",
        1,
    ),
    (
        "require_input: an absent probe is a failure, not a skip",
        "execFileSync('keyctl', ['add', k]);\n",
        None,
        1,
    ),
]


@pytest.mark.parametrize(
    ("consumer", "probe", "want_exit"),
    [(c[1], c[2], c[3]) for c in CASES],
    ids=[c[0] for c in CASES],
)
def test_differential(tmp_path, consumer, probe, want_exit):
    """Byte equality on BOTH streams, and the exit code the case expects.

    The expected exit is asserted as well as the equality, because two
    implementations that are equally broken are byte-identical and prove nothing.
    That is the both-empty trap `scripts/lib/shadow-gate.ts` names as rule 2,
    reproduced here at the level of one case.
    """
    root = build(tmp_path, consumer, probe)
    (old_rc, old_out, old_err), (new_rc, new_out, new_err) = run_both(root)
    assert old_rc == want_exit, "the twin's verdict moved: %s" % old_err
    assert new_rc == old_rc
    assert new_out == old_out
    assert new_err == old_err


def test_selftest_exits_zero_and_prints_a_count():
    """`--selftest` is a real run, not an import.

    EXIT 0 WITH ZERO PASS LINES IS A FAILURE, so the count line is asserted as
    well as the status. A selftest whose cases stopped executing would still exit
    0, and the `Controls` floor is what turns that into a red; this asserts the
    floor is actually reported.
    """
    code, out, err = diff.bash_streams(
        "PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.ci python3 -m rediacc_ci.quality.%s --selftest"
        % MODULE
    )
    assert code == 0, err
    assert "control(s) passed" in out
    ran = int(out.split(" control(s)")[0].strip())
    assert ran >= 15, "the control corpus collapsed to %d assertions" % ran


def test_consumer_extractor_rejects_a_different_binary():
    """The negative half of the consumer extractor, called directly.

    Exported helpers exist so a case can drive the decision without shelling out;
    this is the one that would silently pass if the pattern were loosened to
    `\\['[a-z]+`.
    """
    assert gate.consumer_verbs("execFileSync('gpg', ['add', k])") == []
    assert gate.consumer_verbs("execFileSync('keyctl', ['add', k])") == ["add"]


def test_probe_extractor_respects_the_word_boundary():
    """`xkeyctl` and `re-keyctl` are different commands, and must not contribute."""
    assert gate.probe_verbs("xkeyctl show @u") == []
    assert gate.probe_verbs("re-keyctl add @u") == []
    assert gate.probe_verbs("keyctl show @u") == ["show"]


def test_the_twin_is_still_present():
    """Invariant 5: a twin is never deleted in the change that ports it.

    Asserted rather than assumed, because every differential case above silently
    degenerates into "two missing files behave the same" if the twin goes away,
    and `bash <missing>` exits 127 on both sides.
    """
    assert (pathlib.Path(diff.repo()) / TWIN).is_file()


def test_git_is_available():
    """The specimen builder needs no git, but the twin's root walk needs a shell.

    A missing tool is a LOUD failure with the fix in the message, never a stack
    trace read as flake.
    """
    if shutil.which("bash") is None:  # pragma: no cover - defensive
        pytest.fail("bash is not on PATH; install it (apt-get install bash)")
    assert subprocess.run(["bash", "-c", "true"], check=False).returncode == 0
