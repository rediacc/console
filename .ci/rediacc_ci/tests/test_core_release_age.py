"""`rediacc_ci.core.release_age` against literals frozen from the deleted `release-age.sh`.

THE TWIN IS GONE, NOT LIVE. `.ci/scripts/lib/release-age.sh` had exactly two real sourcers (`grep -rnP '^\\s*(source|\\.)\\s+.*release-age\\.sh'`): `audit.sh:39', deleted by W7P5-b, and `check-go-deps.sh:43`, the last one. W7P5-c deleted `check-go-deps.sh` and, with its only remaining sourcer gone, the shim itself. This file used to run BOTH implementations over identical arguments
and assert byte equality; every case below now asserts the PORT's own CLI (`PY`) against the exact bytes the bash twin produced on ITS LAST DAY, captured with `_both`
before the deletion landed and cross-checked `old == new` on every one of the
36 cases below (20 against the real repository, 16 against `ft_ok`) before being written out as literals. Nothing here is a hand-written expectation.

BOTH SIDES DELEGATE TO THE SAME `scripts/lib/release-age.ts`, which is the point: this was always a differential over a TRANSPORT, never over the rule. The rule itself is proved elsewhere (`scripts/lib/release-age.ts` is the only round-up in the tree) and is untouched by this deletion.

FOUR FIXTURE TREES, because three of the interesting behaviours are unreachable against the real repository:

  `ft_ok`        `release-age.ts` present, `.npmrc` says 60 minutes  -> window 3600
  `ft_no_npmrc`  `release-age.ts` present, NO `.npmrc`               -> window 86400
  `ft_broken`    NO `release-age.ts`, a `tsx` stub that exits 1      -> loud refusal
  the real repo  window 86400

THE REAL REPO CANNOT DISTINGUISH THE FALLBACK FROM THE ANSWER, and that is why
`ft_no_npmrc` exists: this repo's `.npmrc` carries `minimum-release-age=1440`
MINUTES, which is 86400 seconds, exactly the number `RELEASE_AGE_DEFAULT_WINDOW_SECONDS` falls back to. A test written against the real tree would pass whether the delegate answered or not, which is the shape of a control that cannot fail.

TWO DEFECTS OF THE TWIN WERE PINNED HERE AS FACTS ABOUT THE BASH, while it lived, by driving the twin directly (`test_the_twins_runner_memo_never_persists`, `test_the_twin_lets_bash_arithmetic_decide_an_unvalidated_now`). Both cases are retired along with the twin they drove: there is nothing left on disk for them to run against, and the divergences they proved are archaeology now,
recorded in full in `rediacc_ci.core.release_age`'s own docstring (DEFECT 1, DEFECT 2) rather than in a test that can no longer execute. The PORT-only halves of each (`test_the_port_probes_exactly_once`, `test_the_port_refuses_a_now_it_cannot_read`) survive unchanged: they never touched the twin.
"""

import hashlib
import importlib.util
import pathlib
import shutil

import pytest

from rediacc_ci import paths
from rediacc_ci.core import release_age as ra
from rediacc_ci.tests import differential as diff

TS_REL = "scripts/lib/release-age.ts"
PORT = ".ci/rediacc_ci/core/release_age.py"

PY = "PYTHONPATH=%s python3 -m rediacc_ci.core.release_age" % paths.from_root(".ci")


def _sh(text: str) -> str:
    return "'" + text.replace("'", "'\\''") + "'"


def _run_port(argv: list[str], *, root: pathlib.Path | None = None):
    """Run the PORT alone, streams separate. Never touches bash."""
    quoted = " ".join(_sh(a) for a in argv)
    env = diff.env_for() if root is None else diff.env_for(REDIACC_CI_ROOT=str(root))
    return diff.bash_streams("%s %s" % (PY, quoted), env=env)


# --------------------------------------------------------------------------- The fixture trees ---------------------------------------------------------------------------


def _seed(root: pathlib.Path, *, with_ts: bool, npmrc: str | None, tsx_stub: bool) -> pathlib.Path:
    """No `release-age.sh` copy here, deliberately: the port never reads it, only `scripts/lib/release-age.ts`. The twin used to be copied in so the bash side of `_both` had something to source; that side is gone."""
    (root / ".ci" / "scripts" / "lib").mkdir(parents=True)
    (root / "scripts" / "lib").mkdir(parents=True)
    if with_ts:
        shutil.copy(paths.from_root(TS_REL), root / TS_REL)
    if npmrc is not None:
        (root / ".npmrc").write_text(npmrc, encoding="utf-8")
    if tsx_stub:
        binroot = root / "node_modules" / ".bin"
        binroot.mkdir(parents=True)
        stub = binroot / "tsx"
        # A stub that FAILS rather than one that is absent: absent would send the ladder to `npx tsx`, which resolves over the network and would make this suite depend on a registry.
        stub.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
        stub.chmod(0o755)
    return root


@pytest.fixture(scope="module")
def ft_ok(tmp_path_factory):
    return _seed(
        tmp_path_factory.mktemp("ft_ok"),
        with_ts=True,
        npmrc="minimum-release-age=60\n",
        tsx_stub=False,
    )


@pytest.fixture(scope="module")
def ft_no_npmrc(tmp_path_factory):
    return _seed(tmp_path_factory.mktemp("ft_no"), with_ts=True, npmrc=None, tsx_stub=False)


@pytest.fixture(scope="module")
def ft_broken(tmp_path_factory):
    return _seed(tmp_path_factory.mktemp("ft_bad"), with_ts=False, npmrc=None, tsx_stub=True)


# --------------------------------------------------------------------------- 1. The verbs, byte for byte, frozen from the twin's last run ---------------------------------------------------------------------------

CASES = [
    ("window-seconds", ["window-seconds"]),
    ("eligible-default-window", ["eligible-epoch", "1756000000"]),
    ("eligible-explicit-window", ["eligible-epoch", "1756000000", "3600"]),
    ("eligible-window-zero", ["eligible-epoch", "1756000000", "0"]),
    # `:179` accepts `^-?[0-9]+$`, one character wider than the two `^[0-9]+$` tests, so a pre-1970 publish epoch round-trips.
    ("eligible-negative-epoch", ["eligible-epoch", "-100", "86400"]),
    ("eligible-epoch-zero", ["eligible-epoch", "0", "86400"]),
    ("eligible-non-numeric", ["eligible-epoch", "not-a-number", "86400"]),
    ("eligible-empty-epoch", ["eligible-epoch", "", "86400"]),
    ("deferred-yes", ["deferred", "1756000000", "1756100000"]),
    ("deferred-no", ["deferred", "1756000000", "1900000000"]),
    # The boundary: `now == eligibleAt` is ELIGIBLE, because the comparison is
    # strict (`now < eligibleAt`). One second earlier is deferred.
    ("deferred-exactly-at-the-boundary", ["deferred", "1756000000", "1756166400", "86400"]),
    ("deferred-one-second-before", ["deferred", "1756000000", "1756166399", "86400"]),
    ("deferred-empty-publish", ["deferred", ""]),
    ("deferred-non-numeric-publish", ["deferred", "not-a-number"]),
    ("deferred-negative-publish", ["deferred", "-5"]),
    ("deferred-explicit-window", ["deferred", "1756000000", "1756100000", "3600"]),
]

# Frozen against the real repository (window 86400). Captured with `_both`
# before the twin was deleted; `old == new` held for every row.
FROZEN = {
    "window-seconds": (0, "86400\n", ""),
    "eligible-default-window": (0, "1756166400\n", ""),
    "eligible-explicit-window": (0, "1756080000\n", ""),
    "eligible-window-zero": (0, "1756080000\n", ""),
    "eligible-negative-epoch": (0, "86400\n", ""),
    "eligible-epoch-zero": (0, "172800\n", ""),
    "eligible-non-numeric": (
        1,
        "",
        (
            "release-age: could not reach scripts/lib/release-age.ts (tsx missing or "
            "failing); treating 'not-a-number' as DEFERRED\n"
        ),
    ),
    "eligible-empty-epoch": (
        1,
        "",
        (
            "release-age: could not reach scripts/lib/release-age.ts (tsx missing or "
            "failing); treating '' as DEFERRED\n"
        ),
    ),
    "deferred-yes": (0, "deferred\n", ""),
    "deferred-no": (1, "eligible\n", ""),
    "deferred-exactly-at-the-boundary": (1, "eligible\n", ""),
    "deferred-one-second-before": (0, "deferred\n", ""),
    "deferred-empty-publish": (0, "deferred\n", ""),
    "deferred-non-numeric-publish": (0, "deferred\n", ""),
    "deferred-negative-publish": (0, "deferred\n", ""),
    "deferred-explicit-window": (1, "eligible\n", ""),
}

# Frozen against `ft_ok` (window 3600 -- the `.npmrc` says 60 minutes), so every default-window answer MOVES relative to FROZEN above.
FROZEN_FT_OK = {
    "window-seconds": (0, "3600\n", ""),
    "eligible-default-window": (0, "1756080000\n", ""),
    "eligible-explicit-window": (0, "1756080000\n", ""),
    "eligible-window-zero": (0, "1756080000\n", ""),
    "eligible-negative-epoch": (0, "86400\n", ""),
    "eligible-epoch-zero": (0, "172800\n", ""),
    "eligible-non-numeric": (
        1,
        "",
        (
            "release-age: could not reach scripts/lib/release-age.ts (tsx missing or "
            "failing); treating 'not-a-number' as DEFERRED\n"
        ),
    ),
    "eligible-empty-epoch": (
        1,
        "",
        (
            "release-age: could not reach scripts/lib/release-age.ts (tsx missing or "
            "failing); treating '' as DEFERRED\n"
        ),
    ),
    "deferred-yes": (1, "eligible\n", ""),
    "deferred-no": (1, "eligible\n", ""),
    "deferred-exactly-at-the-boundary": (1, "eligible\n", ""),
    "deferred-one-second-before": (0, "deferred\n", ""),
    "deferred-empty-publish": (0, "deferred\n", ""),
    "deferred-non-numeric-publish": (0, "deferred\n", ""),
    "deferred-negative-publish": (0, "deferred\n", ""),
    "deferred-explicit-window": (1, "eligible\n", ""),
}


@pytest.mark.parametrize(("case", "argv"), CASES, ids=[c[0] for c in CASES])
def test_the_verbs_match_the_frozen_twin(case, argv):
    got = _run_port(argv)
    assert got == FROZEN[case], "case %s: %r != %r" % (case, got, FROZEN[case])


@pytest.mark.parametrize(("case", "argv"), CASES, ids=[c[0] for c in CASES])
def test_the_verbs_match_the_frozen_twin_on_a_tree_whose_npmrc_says_sixty_minutes(
    ft_ok, case, argv
):
    """The window is 3600 here, so every default-window answer MOVES.

    Against the real tree the window is 86400, which is also the fallback, so this fixture is what proves the delegate is being consulted at all.
    """
    got = _run_port(argv, root=ft_ok)
    assert got == FROZEN_FT_OK[case], "case %s: %r != %r" % (case, got, FROZEN_FT_OK[case])


def test_the_window_fixture_is_not_vacuous(ft_ok, ft_no_npmrc):
    """The three trees must give three DIFFERENT windows, or nothing above holds."""
    live = _run_port(["window-seconds"])
    sixty = _run_port(["window-seconds"], root=ft_ok)
    absent = _run_port(["window-seconds"], root=ft_no_npmrc)
    assert live[1].strip() == "86400"
    assert sixty[1].strip() == "3600"
    assert absent[1].strip() == "86400"
    assert sixty[1] != absent[1], (
        "the .npmrc fixture changed nothing, so these tests cannot tell the delegate's "
        "answer from the 86400 fallback"
    )


# --------------------------------------------------------------------------- 2. The unreachable delegate, which is the branch that decides fail-closed ---------------------------------------------------------------------------

BROKEN_CASES = [
    ("window-seconds-falls-back", ["window-seconds"]),
    ("eligible-refuses-loudly", ["eligible-epoch", "1756000000", "86400"]),
    ("deferred-fails-closed", ["deferred", "1756000000", "1756100000", "86400"]),
    (
        "deferred-fails-closed-even-when-now-is-far-future",
        ["deferred", "1756000000", "1900000000", "86400"],
    ),
]

# Frozen against `ft_broken` (no `release-age.ts`, a `tsx` stub that exits 1).
FROZEN_BROKEN = {
    "window-seconds-falls-back": (0, "86400\n", ""),
    "eligible-refuses-loudly": (
        1,
        "",
        (
            "release-age: could not reach scripts/lib/release-age.ts (tsx missing or "
            "failing); treating '1756000000' as DEFERRED\n"
        ),
    ),
    "deferred-fails-closed": (
        0,
        "deferred\n",
        (
            "release-age: could not reach scripts/lib/release-age.ts (tsx missing or "
            "failing); treating '1756000000' as DEFERRED\n"
        ),
    ),
    "deferred-fails-closed-even-when-now-is-far-future": (
        0,
        "deferred\n",
        (
            "release-age: could not reach scripts/lib/release-age.ts (tsx missing or "
            "failing); treating '1756000000' as DEFERRED\n"
        ),
    ),
}

# The same `deferred` call against the real repo (a WORKING delegate), frozen so `test_the_unreachable_delegate_is_loud_and_fails_closed` below has something to contrast the fail-closed answer against without re-deriving it.
FROZEN_WORKING_DEFERRED_FAR_FUTURE = (1, "eligible\n", "")


@pytest.mark.parametrize(("case", "argv"), BROKEN_CASES, ids=[c[0] for c in BROKEN_CASES])
def test_an_unreachable_delegate_matches_the_frozen_twin(ft_broken, case, argv):
    got = _run_port(argv, root=ft_broken)
    assert got == FROZEN_BROKEN[case], "case %s: %r != %r" % (case, got, FROZEN_BROKEN[case])


def test_the_unreachable_delegate_is_loud_and_fails_closed(ft_broken):
    """The two halves of the policy, asserted rather than assumed from equality.

    A silent fallback here would make every version look eligible, or every one deferred, depending on the sentinel chosen, and a freshness gate that quietly stops deferring is exactly the shape this repo keeps getting caught by.
    """
    argv = ["deferred", "1756000000", "1900000000", "86400"]
    broken = _run_port(argv, root=ft_broken)
    assert broken == FROZEN_BROKEN["deferred-fails-closed-even-when-now-is-far-future"]
    expected = (
        "release-age: could not reach scripts/lib/release-age.ts (tsx missing or "
        "failing); treating '1756000000' as DEFERRED"
    )
    assert expected in broken[2]
    # 1900000000 is well past any eligibility, so a working delegate says ELIGIBLE. The broken one must say DEFERRED anyway.
    assert broken[1].strip() == "deferred"
    assert broken[0] == 0
    working = _run_port(argv)
    assert working == FROZEN_WORKING_DEFERRED_FAR_FUTURE
    assert working[1].strip() == "eligible", "the control is vacuous: this case is deferred anyway"


def test_a_failed_lookup_is_not_memoised(ft_broken):
    """`release-age.sh:190` used to write the cache only AFTER the regex accepted; this port matches that.

    A transient delegate failure must be retried on the next call rather than frozen into the run; a port that cached `None` would make one network blip defer every remaining version in the gate.
    """
    shim = ra.ReleaseAge(ft_broken)
    assert shim.eligible_epoch(1756000000, 86400) is None
    assert (1756000000, 86400) not in shim._eligible
    assert shim.eligible_epoch(1756000000, 86400) is None


def test_a_successful_lookup_is_memoised(ft_ok):
    """The memo the twin's globals existed for, on the port's side."""
    shim = ra.ReleaseAge(ft_ok)
    first = shim.eligible_epoch(1756000000, 86400)
    calls = shim.delegate_calls
    assert first is not None
    assert shim.eligible_epoch(1756000000, 86400) == first
    assert shim.delegate_calls == calls, "the second lookup spawned the delegate again"
    assert shim.eligible_epoch(1756000001, 86400) is not None
    assert shim.delegate_calls == calls + 1, "a DIFFERENT key must miss the memo"


# --------------------------------------------------------------------------- 3. The ladder itself ---------------------------------------------------------------------------


@pytest.fixture
def counting_node(tmp_path):
    """A `node` first on PATH that appends one line per invocation, then execs."""
    real = shutil.which("node")
    if real is None:
        pytest.skip("node is not on PATH; the runner ladder's first rung cannot be observed")
    bindir = tmp_path / "fakebin"
    bindir.mkdir()
    log = tmp_path / "node-calls.log"
    wrapper = bindir / "node"
    wrapper.write_text(
        '#!/bin/bash\necho "$*" >> %s\nexec %s "$@"\n' % (log, real), encoding="utf-8"
    )
    wrapper.chmod(0o755)
    log.write_text("", encoding="utf-8")
    return bindir, log


def _counts(log: pathlib.Path) -> tuple[int, int]:
    """(total node starts, `--window-seconds` starts)."""
    lines = [line for line in log.read_text(encoding="utf-8").splitlines() if line]
    window = [line for line in lines if line.endswith("--window-seconds")]
    return len(lines), len(window)


def test_the_port_probes_exactly_once(ft_ok, counting_node, monkeypatch):
    """DEFECT 1 in `rediacc_ci.core.release_age`'s docstring was measured against the twin while it lived: the bash never persisted its runner choice across a command substitution, so it re-probed once per delegate call (N+1 probes for N verdicts). That control drove the twin directly and is retired with it. What survives is the port's own guarantee, measured on the same
    instrument: exactly ONE probe for the whole process.
    """
    bindir, log = counting_node
    monkeypatch.setenv("PATH", "%s:%s" % (bindir, diff.BASE_ENV["PATH"]))
    shim = ra.ReleaseAge(ft_ok)
    epochs = [1756000001, 1756000002, 1756000003, 1756000004, 1756000005]
    verdicts = [shim.is_release_deferred(epoch, 1756100000) for epoch in epochs]
    total, window_starts = _counts(log)
    assert window_starts == 2, (
        "expected exactly two `--window-seconds` starts (ONE probe for the whole "
        "process, plus the real window query), saw %d" % window_starts
    )
    assert total == len(epochs) + 2, "expected %d node starts, saw %d" % (
        len(epochs) + 2,
        total,
    )
    # Every one of these epochs is well before the 1756100000 "now" plus the default 86400s window, so every verdict is ELIGIBLE (not deferred).
    assert verdicts == [False] * len(epochs), verdicts


# --------------------------------------------------------------------------- 4. `now` is unvalidated on the (deleted) twin; the port refuses instead ---------------------------------------------------------------------------


def test_the_port_refuses_a_now_it_cannot_read(ft_ok):
    """DEFECT 2 in `rediacc_ci.core.release_age`'s docstring was measured against the twin while it lived: bash arithmetic let an unvalidated `now` decide, and a number with a stray suffix (`"1756100000x"`) resolved to the exact false "must upgrade" the fail-closed policy exists to prevent. That control drove the twin directly and is retired with it. The port's divergence --
    refusing outright -- is what survives.
    """
    shim = ra.ReleaseAge(ft_ok)
    with pytest.raises(ValueError, match="invalid literal for int"):
        shim.is_release_deferred(1756000000, "1756100000x", 86400)  # type: ignore[arg-type]
    # A real integer still works, so the refusal is not blanket.
    assert shim.is_release_deferred(1756000000, 1756100000, 86400) is True


# --------------------------------------------------------------------------- 5. The ladder itself ---------------------------------------------------------------------------


def test_the_fast_rung_is_proven_before_it_is_adopted(ft_broken):
    """A node that cannot answer must fall THROUGH, not poison every verdict.

    `ft_broken` has no `release-age.ts`, so the probe runs, fails, and the ladder must land on the local `tsx` stub rather than on `node --experimental-strip-types`.
    """
    shim = ra.ReleaseAge(ft_broken)
    runner = shim.resolve_runner()
    assert runner == [str(ft_broken / "node_modules" / ".bin" / "tsx")], runner
    assert shim.probe_calls == 1, "the probe did not run, so nothing was proven"


def test_the_fast_rung_is_taken_when_it_answers(ft_ok):
    shim = ra.ReleaseAge(ft_ok)
    if shutil.which("node") is None:
        pytest.skip("node is not on PATH")
    assert shim.resolve_runner() == ["node", "--experimental-strip-types"]


# --------------------------------------------------------------------------- 6. The planted defects ---------------------------------------------------------------------------


def _digest(rel: str) -> str:
    return hashlib.sha256(pathlib.Path(paths.from_root(rel)).read_bytes()).hexdigest()


def _load_mutated(tmp_path, old: str, new: str, name: str):
    """Load a MUTATED COPY of the port from a tmpdir, under a fresh module name.

    The real file is never opened for writing, so an aborted test cannot leave the tree broken.
    """
    source = pathlib.Path(paths.from_root(PORT)).read_text(encoding="utf-8")
    assert old in source, "the plant did not land: %r is not in the port" % old
    target = tmp_path / ("%s.py" % name)
    target.write_text(source.replace(old, new, 1), encoding="utf-8")
    spec = importlib.util.spec_from_file_location(name, target)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_a_planted_defect_in_the_port_is_caught(tmp_path, ft_ok, ft_broken):
    """THE CONTROL FOR EVERY CASE ABOVE. Three real mutations, each caught."""
    before = _digest(PORT)

    # PLANT 1: fail-OPEN on an unreachable delegate. This is the defect the twin's loud refusal exists to make impossible, and a gate carrying it would report every version as installable while the delegate was down.
    m1 = _load_mutated(
        tmp_path,
        "        if eligible is None:\n            return True",
        "        if eligible is None:\n            return False",
        "ra_p1",
    )
    assert ra.ReleaseAge(ft_broken).is_release_deferred(1756000000, 1756100000, 86400) is True
    assert m1.ReleaseAge(ft_broken).is_release_deferred(1756000000, 1756100000, 86400) is False, (
        "the mutation did not change the verdict, so this control proves nothing"
    )

    # PLANT 2: the window fallback made unconditional, which silently disables deferral tuning on every tree whose .npmrc says something else.
    m2 = _load_mutated(
        tmp_path,
        "        if answer is None or not _UNSIGNED.fullmatch(answer) or int(answer) <= 0:",
        "        if True:",
        "ra_p2",
    )
    assert ra.ReleaseAge(ft_ok).window_seconds() == 3600
    assert m2.ReleaseAge(ft_ok).window_seconds() == 86400, (
        "the fixture's 60-minute window did not survive, so plant 2 is invisible"
    )

    # PLANT 3: the strict comparison relaxed. `now == eligibleAt` is ELIGIBLE.
    m3 = _load_mutated(tmp_path, "return moment < eligible", "return moment <= eligible", "ra_p3")
    boundary = ra.ReleaseAge(ft_ok).eligible_epoch(1756000000, 86400)
    assert boundary is not None
    assert ra.ReleaseAge(ft_ok).is_release_deferred(1756000000, boundary, 86400) is False
    assert m3.ReleaseAge(ft_ok).is_release_deferred(1756000000, boundary, 86400) is True, (
        "the boundary moved by one second and nothing noticed"
    )

    assert _digest(PORT) == before, "a planted defect was written to the real module"
