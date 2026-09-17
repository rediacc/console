"""Differential: `rediacc_ci.security.rdc_sh_env_check` against its twin
`.ci/scripts/test/test-rdc-sh-env.sh` (gate `check:ci-rdc-sh-env`).

THE GREEN RUN IS THE WEAKEST CASE, so most of this file is about the red ones. Both subjects pass on the real tree today, which proves only that two programs agree about an `rdc.sh` neither is currently catching out. Every case below therefore runs both against a FIXTURE TREE holding a MUTATED copy of `rdc.sh`, so each of the twin's eleven `fail` branches is actually reached and
compared byte for byte -- ANSI escapes included, because those are what a reader of a CI log sees and what a "tidier" port would drop.

HOW THE TWO SIDES ARE POINTED AT A FIXTURE, and it differs per side. The twin
resolves `REPO_ROOT` from `${BASH_SOURCE[0]}`, so it is COPIED into the fixture
and run from there. The port resolves it through `paths.repo_root()`, whose documented single override is `$REDIACC_CI_ROOT`, so it runs from the real tree
with that variable set. Both then read the same mutated `rdc.sh`.

NOTHING ON DISK IS MUTATED. Every fixture is built under pytest's `tmp_path`
from `shutil.copy2` of the real files; the repository's own `rdc.sh` and the
twin are only ever read.

LAYER 2 RUNS THE REAL DEV PATH, which is the point: it execs a PATH-shimmed `node` and `curl` inside a throwaway ROOT_DIR, so no network and no build.
`node` must be on PATH or BOTH sides die at rc=1 with empty streams, which is
itself asserted rather than skipped.

K=5 LEDGER: `.ci/shadow/w7p6-rdc-sh-env.observations.jsonl`.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import typing

from rediacc_ci import paths
from rediacc_ci.security import rdc_sh_env_check

if typing.TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()
TWIN = ROOT / ".ci" / "scripts" / "test" / "test-rdc-sh-env.sh"
PORT = ROOT / ".ci" / "rediacc_ci" / "security" / "rdc_sh_env_check.py"
RDC_SH = ROOT / "rdc.sh"

# NOT named `PASS_...`/`FAIL_...`: ruff S105 reads a constant whose NAME carries
# "PASS" as a hardcoded password, and a per-line noqa to get past a gate is the
# thing this repo refuses. The VALUES are the twin's literal glyph lines.
OK_GLYPH = "  \033[0;32m✓\033[0m "
BAD_GLYPH = "  \033[0;31m✗\033[0m "

# The tail of `rdc.sh`. Anything appended AFTER it is unreachable at runtime and still visible to layer 1's greps, which is how a "sources the env file" finding is planted without breaking the dev path that layer 2 drives.
EXEC_TAIL = 'exec node "$ROOT_DIR/packages/cli/dist/cli-bundle.cjs" "$@"\n'


def build_fixture(tmp_path: pathlib.Path) -> pathlib.Path:
    """A two-file skeleton both the twin and the port resolve inside."""
    fixture = tmp_path / "fixture"
    (fixture / ".ci" / "scripts" / "test").mkdir(parents=True, exist_ok=True)
    shutil.copy2(TWIN, fixture / ".ci" / "scripts" / "test" / TWIN.name)
    shutil.copy2(RDC_SH, fixture / "rdc.sh")
    return fixture


def mutate(fixture: pathlib.Path, old: str, new: str) -> None:
    """Edit the fixture's `rdc.sh`, refusing a silently-vacuous mutation."""
    target = fixture / "rdc.sh"
    text = target.read_text(encoding="utf-8")
    assert old in text, "mutation anchor %r is not in rdc.sh" % old
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


def _run(subject: pathlib.Path, fixture: pathlib.Path) -> subprocess.CompletedProcess[str]:
    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": os.environ.get("HOME", ""),
        "LC_ALL": "C",
    }
    if subject.suffix == ".py":
        runner = ["python3", str(subject)]
        env["PYTHONPATH"] = str(ROOT / ".ci")
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env["REDIACC_CI_ROOT"] = str(fixture)
    else:
        runner = ["bash", str(fixture / ".ci" / "scripts" / "test" / TWIN.name)]
    return subprocess.run(runner, env=env, capture_output=True, text=True, check=False, timeout=180)


def run_both(
    fixture: pathlib.Path, *, port: pathlib.Path | None = None
) -> tuple[subprocess.CompletedProcess[str], subprocess.CompletedProcess[str]]:
    return _run(TWIN, fixture), _run(port or PORT, fixture)


def assert_same(
    old: subprocess.CompletedProcess[str], new: subprocess.CompletedProcess[str]
) -> None:
    assert new.returncode == old.returncode, "exit: twin %s, port %s" % (
        old.returncode,
        new.returncode,
    )
    assert new.stdout == old.stdout
    assert new.stderr == old.stderr


# --------------------------------------------------------------------------- The green path, on the real tree and on an unmutated fixture ---------------------------------------------------------------------------


def test_real_tree_agrees_byte_for_byte() -> None:
    old = _run(TWIN, ROOT)
    new = _run(PORT, ROOT)
    assert old.returncode == 0, old.stderr
    assert old.stdout.count(OK_GLYPH) == 7
    assert old.stdout.endswith("\nPassed: 7\nFailed: 0\n")
    assert old.stderr == ""
    assert_same(old, new)


def test_unmutated_fixture_is_the_same_run(tmp_path: pathlib.Path) -> None:
    fixture = build_fixture(tmp_path)
    old, new = run_both(fixture)
    assert old.returncode == 0, old.stderr
    assert_same(old, new)
    # The fixture must be a faithful stand-in, or every mutation below is measuring the fixture rather than the mutation.
    assert old.stdout == _run(TWIN, ROOT).stdout


# --------------------------------------------------------------------------- Layer 1's four checks, each reached by a real mutation ---------------------------------------------------------------------------


def test_a_set_a_statement_is_caught(tmp_path: pathlib.Path) -> None:
    fixture = build_fixture(tmp_path)
    mutate(fixture, "export NODE_COMPILE_CACHE=", "set -a\nexport NODE_COMPILE_CACHE=")
    old, new = run_both(fixture)
    assert old.returncode == 1
    assert (
        BAD_GLYPH + "rdc.sh contains a 'set -a' statement (env-export leak vector)\n" in old.stderr
    )
    assert_same(old, new)


def test_sourcing_the_account_env_file_is_caught(tmp_path: pathlib.Path) -> None:
    """Planted AFTER the final `exec`, so layer 1 sees it and layer 2 does not."""
    fixture = build_fixture(tmp_path)
    mutate(fixture, EXEC_TAIL, EXEC_TAIL + 'source "$ROOT_DIR/private/account/.env"\n')
    old, new = run_both(fixture)
    assert old.returncode == 1
    assert BAD_GLYPH + "rdc.sh sources the account env file (secret leak vector)\n" in old.stderr
    assert old.stdout.count(OK_GLYPH) == 6, "only the no-source PASS line is missing"
    assert_same(old, new)


def test_an_extra_export_breaks_the_allowlist(tmp_path: pathlib.Path) -> None:
    fixture = build_fixture(tmp_path)
    mutate(fixture, "export NODE_COMPILE_CACHE=", "export ZZZ_LEAK=1\nexport NODE_COMPILE_CACHE=")
    old, new = run_both(fixture)
    assert old.returncode == 1
    assert (
        BAD_GLYPH + "export set is [NODE_COMPILE_CACHE PATH REDIACC_CONFIG ZZZ_LEAK]; "
        "expected [NODE_COMPILE_CACHE PATH REDIACC_CONFIG]\n" in old.stderr
    )
    assert_same(old, new)


def test_a_dead_surface_reference_still_prints_its_pass_line(tmp_path: pathlib.Path) -> None:
    """The twin's 1d PASS is UNCONDITIONAL (`test-rdc-sh-env.sh:84`).

    A run that finds `RDC_BENCH` still referenced prints BOTH the failure and "no removed token/mode surface". A port that "fixed" that would disagree here, which is the whole reason this case exists.
    """
    fixture = build_fixture(tmp_path)
    mutate(fixture, "ref_file=", "# note: RDC_BENCH was here\nref_file=")
    old, new = run_both(fixture)
    assert old.returncode == 1
    assert (
        BAD_GLYPH + "rdc.sh still references removed token/mode surface: RDC_BENCH\n" in old.stderr
    )
    assert (
        OK_GLYPH + "no removed token/mode surface (REDIACC_SUBSCRIPTION_TOKEN_FILE / "
        "REDIACC_ENVIRONMENT / RDC_BENCH / .rdc-{dev,bench})\n" in old.stdout
    )
    assert old.stdout.count(OK_GLYPH) == 7, "all seven PASS lines still print"
    assert_same(old, new)


def test_a_missing_dev_config_export_is_only_caught_by_layer_two(
    tmp_path: pathlib.Path,
) -> None:
    """`grep -q 'export REDIACC_CONFIG=dev'` is a SUBSTRING match.

    `export REDIACC_CONFIG=devx` therefore satisfies check 1d, and only layer
    2's dump inspection notices. It is also the case that exercises the `grep -q ... && pass` shape: the second PASS line is simply absent, with no early exit.
    """
    fixture = build_fixture(tmp_path)
    mutate(fixture, "export REDIACC_CONFIG=dev", "export REDIACC_CONFIG=devx")
    old, new = run_both(fixture)
    assert old.returncode == 1
    assert old.stderr == BAD_GLYPH + "CLI env missing REDIACC_CONFIG=dev\n"
    assert "CLI environment carries REDIACC_CONFIG=dev only" not in old.stdout
    assert "dev path must export REDIACC_CONFIG=dev" not in old.stderr
    assert old.stdout.endswith("\nPassed: 6\nFailed: 1\n")
    assert_same(old, new)


# --------------------------------------------------------------------------- Layer 2: the leak the gate exists to catch ---------------------------------------------------------------------------

# `set -a` + `source` of the fixture env file, immediately before the final `exec`, is the exact leak vector the gate's two layers describe. It fires layer 1's first two checks AND puts every sentinel into the CLI environment.
LEAK_PLANT = 'set -a\nsource "$ROOT_DIR/private/account/.env"\nset +a\n' + EXEC_TAIL


def test_a_real_secret_leak_is_caught(tmp_path: pathlib.Path) -> None:
    fixture = build_fixture(tmp_path)
    mutate(fixture, EXEC_TAIL, LEAK_PLANT)
    old, new = run_both(fixture)
    assert old.returncode == 1
    assert "SECRET LEAK: sentinel value reached the CLI environment:" in old.stderr
    for name in rdc_sh_env_check.SECRET_NAMES:
        assert BAD_GLYPH + "SECRET LEAK: %s present in CLI environment\n" % name in old.stderr
    assert_same(old, new)


def test_a_missing_rdc_sh_is_the_same_refusal_on_both_sides(tmp_path: pathlib.Path) -> None:
    fixture = build_fixture(tmp_path)
    (fixture / "rdc.sh").unlink()
    old, new = run_both(fixture)
    assert old.returncode == 1
    assert old.stderr == "FAIL: rdc.sh not found at %s/rdc.sh\n" % fixture
    assert old.stdout == ""
    assert_same(old, new)


# --------------------------------------------------------------------------- The pure helpers, driven against the real tools rather than against a manual ---------------------------------------------------------------------------


def test_has_set_a_matches_the_real_grep() -> None:
    sample = "set -a\n  set -ax\nset -a foo\n#set -a\n\tset -a\n"
    real = subprocess.run(
        ["grep", "-nE", r"^[[:space:]]*set[[:space:]]+-a([[:space:]]|$)"],
        input=sample,
        capture_output=True,
        text=True,
        check=False,
    )
    assert real.stdout == "1:set -a\n3:set -a foo\n5:\tset -a\n", real.stdout
    assert rdc_sh_env_check.has_set_a(sample)
    assert not rdc_sh_env_check.has_set_a("  set -ax\n#set -a\n")


def test_sources_account_env_matches_the_real_grep() -> None:
    positives = ("source private/account/.env\n", '   . "$account_env"\n')
    negatives = ("# source private/account/.env\n", "echo source private/account/.env\n")
    for sample in positives + negatives:
        real = subprocess.run(
            [
                "grep",
                "-nE",
                r"(^[[:space:]]*(source|\.)[[:space:]]).*(account_env|private/account/\.env)",
            ],
            input=sample,
            capture_output=True,
            text=True,
            check=False,
        )
        assert rdc_sh_env_check.sources_account_env(sample) == (real.returncode == 0), sample
    assert rdc_sh_env_check.sources_account_env(positives[0])
    assert not rdc_sh_env_check.sources_account_env(negatives[0])


def test_exported_names_matches_the_real_pipeline() -> None:
    """`grep -oE ... | awk '{print $2}' | sort -u | tr | sed`, actually run."""
    text = RDC_SH.read_text(encoding="utf-8")
    pipeline = (
        r"grep -oE '^[[:space:]]*export[[:space:]]+[A-Za-z_][A-Za-z0-9_]*' "
        r"| awk '{print $2}' | sort -u | tr '\n' ' ' | sed 's/ $//'"
    )
    real = subprocess.run(
        ["bash", "-c", pipeline],
        input=text,
        capture_output=True,
        text=True,
        check=True,
        env={**os.environ, "LC_ALL": "C"},
    )
    assert real.stdout != "", "the anchor moved; this comparison would be vacuous"
    assert rdc_sh_env_check.exported_names(text) == real.stdout
    assert rdc_sh_env_check.exported_names(text) == rdc_sh_env_check.ALLOWLIST


def test_exported_names_is_deduplicated_and_sorted() -> None:
    assert rdc_sh_env_check.exported_names("export B=1\nexport A=2\nexport B=3\n") == "A B"
    assert rdc_sh_env_check.exported_names("  export INDENTED=1\n") == "INDENTED"
    assert rdc_sh_env_check.exported_names("exportNOSPACE=1\n") == ""
    assert rdc_sh_env_check.exported_names("export 9BAD=1\n") == ""


# --------------------------------------------------------------------------- The control: a planted defect must turn this differential red ---------------------------------------------------------------------------


def test_planted_defect_is_caught_by_this_differential(tmp_path: pathlib.Path) -> None:
    """Delete the sentinel check from a COPY of the port.

    That check is the entire reason this gate exists, and it is invisible on every green run: a port that dropped it agrees with the twin on the real tree and disagrees only against an `rdc.sh` that actually leaks, which is exactly the fixture built here. The real port file on disk is never touched.
    """
    source = PORT.read_text(encoding="utf-8")
    anchor = """        leaks = grep_lines(text, re.compile("LEAKSENTINEL"))
        if leaks:
            tally.fail(
                "SECRET LEAK: sentinel value reached the CLI environment: %s" % "\\n".join(leaks)
            )
        else:
            tally.ok("no sentinel secret value in CLI environment")
"""
    assert source.count(anchor) == 1, "the plant's anchor must still be where it was"
    broken = tmp_path / "rdc_sh_env_check_broken.py"
    broken.write_text(
        source.replace(
            anchor, '        tally.ok("no sentinel secret value in CLI environment")\n', 1
        ),
        encoding="utf-8",
    )

    fixture = build_fixture(tmp_path)
    mutate(fixture, EXEC_TAIL, LEAK_PLANT)
    old, new = run_both(fixture, port=broken)
    assert old.returncode == 1, "the twin must catch the leaking rdc.sh"
    assert "SECRET LEAK: sentinel value" in old.stderr
    assert new.stderr != old.stderr, "PLANT DID NOT FIRE: the differential is vacuous"

    # And the unmutated port still agrees against the same leaking fixture.
    good_old, good_new = run_both(fixture)
    assert_same(good_old, good_new)
