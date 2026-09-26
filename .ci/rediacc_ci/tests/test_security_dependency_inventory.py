"""Differential: `rediacc_ci.security.dependency_inventory` against its twin `.ci/scripts/security/dependency-inventory.sh`.

TWO KINDS OF CASE, AND THE SPLIT IS THE POINT.

  REAL RUNS, against this repository's own dependency tree. `npm ls` and the
  three `go` probes are READS, and the twin already runs them on every
  invocation, so there is nothing to stub for the happy path -- and nothing that
  would reproduce it if there were: 1,760 records, 209 Go modules, 1,262 unique
  name@version pairs and seven chain-truncation warnings only exist here.
  Both real-run cases hash `go.mod`, `go.sum` and both lockfiles before and
  after and refuse a byte of drift, so "read-only" is asserted rather than
  assumed.

  FIXTURE RUNS, against a scratch tree with RECORDING FAKE `npm` and `go` on a
  scratch PATH. Every failure path lives here, because there is no way to make
  the real tools fail on demand without breaking the tree. The fakes append
  their exact argv to `$FAKE_LOG`, and every fixture case compares the two call
  logs as well as the two output streams: a port that produced identical bytes
  by asking DIFFERENT questions would pass a stdout comparison and fail this
  one.

WHY THE FIXTURE COPIES BOTH IMPLEMENTATIONS. Each side resolves the repository root from its OWN location -- `get_repo_root` walks up from `.ci/scripts/lib/common.sh`, `paths.repo_root()` walks up from `.ci/rediacc_ci/paths.py` -- and both then hard-code `packages/www`, `packages/cli`, `private/account` and `private/renet` relative to it. There is no `$ROOT` seam on the bash side,
so the only way to point both at a fixture is to put both INSIDE the fixture at their real relative paths.

TWO NORMALISED CASES, both named:
  * the missing-option-value case, where bash prints
    `<path>: line 41: $2: unbound variable` naming the SCRIPT and its LINE.
  * `generatedAt`, which is `date -u` at the moment of the run.
Everything else is byte for byte on both streams, the call log included.

K=5 LEDGER: `.ci/shadow/w7p6-dependency-inventory.observations.jsonl`.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import typing

import pytest

from rediacc_ci import paths
from rediacc_ci.security import dependency_inventory as port
from rediacc_ci.tests import differential

if typing.TYPE_CHECKING:  # pragma: no cover - annotations only
    import pathlib

ROOT = paths.repo_root()
TWIN_REL = ".ci/scripts/security/dependency-inventory.sh"
PORT_REL = ".ci/rediacc_ci/security/dependency_inventory.py"
TWIN = ROOT / TWIN_REL
PORT = ROOT / PORT_REL

# The minimum of the package a path-invoked port needs. Deliberately short: the fixture must not become a second copy of the repository.
COPIED = (
    TWIN_REL,
    ".ci/scripts/lib/common.sh",
    ".ci/rediacc_ci/__init__.py",
    ".ci/rediacc_ci/paths.py",
    ".ci/rediacc_ci/log.py",
    ".ci/rediacc_ci/security/__init__.py",
    PORT_REL,
)

# Files a real run must not touch. `go mod graph` and `go list -m -json all` CAN write go.sum when a checksum is missing, which is the one way this "read-only" tool could mutate the tree.
GUARDED = (
    "package-lock.json",
    "private/account/package-lock.json",
    "private/renet/go.mod",
    "private/renet/go.sum",
)

PACKAGE_JSON = (
    '{"name":"x","dependencies":{"alpha":"^1.0.0"},"devDependencies":{"beta":"^2.0.0"}}\n'
)

WWW_ALL = (
    '{"name":"root","version":"0.0.0","dependencies":{"@rediacc/www":{"version":"1.0.0",'
    '"dependencies":{"alpha":{"version":"1.2.3","dependencies":{"gamma":{"version":"0.1.0"}}},'
    '"beta":{"version":"2.0.0","dependencies":{"gamma":{"version":"0.1.0"},'
    '"delta":{"version":"3.0.0"}}}}}}}\n'
)
WWW_PROD = (
    '{"name":"root","version":"0.0.0","dependencies":{"@rediacc/www":{"version":"1.0.0",'
    '"dependencies":{"alpha":{"version":"1.2.3","dependencies":{"gamma":{"version":"0.1.0"}}}'
    "}}}}\n"
)
CLI_ALL = WWW_ALL.replace("@rediacc/www", "@rediacc/cli")
CLI_PROD = WWW_PROD.replace("@rediacc/www", "@rediacc/cli")
ACCOUNT_ALL = (
    '{"name":"@rediacc/account","version":"9.9.9","dependencies":{"alpha":{"version":"1.2.3"},'
    '"omega":{"version":"5.0.0","dependencies":{"alpha":{"version":"1.2.3"}}}}}\n'
)
ACCOUNT_PROD = (
    '{"name":"@rediacc/account","version":"9.9.9","dependencies":{"alpha":{"version":"1.2.3"}}}\n'
)

GO_LISTM = "example.com/renet\n"
GO_MODULES = (
    '{"Path":"example.com/renet","Main":true}\n'
    '{"Path":"github.com/x/a","Version":"v1.0.0"}\n'
    '{"Path":"github.com/x/b","Version":"v2.0.0","Indirect":true}\n'
    '{"Path":"github.com/x/c","Version":"v3.0.0","Indirect":true}\n'
)
GO_GRAPH = (
    "example.com/renet github.com/x/a@v1.0.0\n"
    "github.com/x/a@v1.0.0 github.com/x/b@v2.0.0\n"
    "github.com/x/b@v2.0.0 github.com/x/c@v3.0.0\n"
)

# THE FAKES RECORD BEFORE THEY ANSWER. Every invocation appends one `FAKECALL ...` line naming the exact argv and the cwd relative to the fixture root, which is what makes "did the port ask the same questions" an assertion rather than an inference from matching output.
FAKE_NPM = """#!/bin/bash
printf 'FAKECALL npm %s [cwd=%s]\\n' "$*" "${PWD#$FIXTURE_ROOT}" >>"$FAKE_LOG"
key=all
[[ "$*" == *--omit=dev* ]] && key=prod
ws=root
prev=""
for a in "$@"; do
    [[ "$prev" == "--workspace" ]] && ws="${a//\\//_}"
    prev="$a"
done
f="$FAKE_DATA/npm.$ws.$key"
[[ -f "$f" ]] && cat "$f"
exit 0
"""

FAKE_GO = """#!/bin/bash
printf 'FAKECALL go %s [cwd=%s]\\n' "$*" "${PWD#$FIXTURE_ROOT}" >>"$FAKE_LOG"
case "$*" in
    "list -m") n=listm ;;
    "list -m -json all") n=modules ;;
    "mod graph") n=graph ;;
    *) echo "fake go: unexpected argv: $*" >&2; exit 2 ;;
esac
if [[ -f "$FAKE_DATA/go.$n.err" ]]; then
    cat "$FAKE_DATA/go.$n.err" >&2
    exit 1
fi
[[ -f "$FAKE_DATA/go.$n" ]] && cat "$FAKE_DATA/go.$n"
exit 0
"""


@pytest.fixture
def fixture(tmp_path: pathlib.Path) -> pathlib.Path:
    """A scratch repository holding both implementations and the two fakes."""
    fx = tmp_path / "fx"
    for rel in COPIED:
        dest = fx / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel, dest)
    for rel in ("node_modules", "private/account/node_modules", "private/renet"):
        (fx / rel).mkdir(parents=True, exist_ok=True)
    for rel in ("packages/www", "packages/cli", "private/account"):
        (fx / rel).mkdir(parents=True, exist_ok=True)
        (fx / rel / "package.json").write_text(PACKAGE_JSON, encoding="utf-8")

    data = fx / "fake" / "data"
    data.mkdir(parents=True, exist_ok=True)
    for name, body in (
        ("npm.@rediacc_www.all", WWW_ALL),
        ("npm.@rediacc_www.prod", WWW_PROD),
        ("npm.@rediacc_cli.all", CLI_ALL),
        ("npm.@rediacc_cli.prod", CLI_PROD),
        ("npm.root.all", ACCOUNT_ALL),
        ("npm.root.prod", ACCOUNT_PROD),
        ("go.listm", GO_LISTM),
        ("go.modules", GO_MODULES),
        ("go.graph", GO_GRAPH),
    ):
        (data / name).write_text(body, encoding="utf-8")

    bindir = fx / "fake" / "bin"
    bindir.mkdir(parents=True, exist_ok=True)
    for name, body in (("npm", FAKE_NPM), ("go", FAKE_GO)):
        path = bindir / name
        path.write_text(body, encoding="utf-8")
        path.chmod(0o755)
    return fx


def data_dir(fx: pathlib.Path) -> pathlib.Path:
    return fx / "fake" / "data"


def _env(fx: pathlib.Path, side: str, log: pathlib.Path) -> dict[str, str]:
    """REPLACES the caller's environment; see `differential.BASE_ENV`."""
    env = differential.env_for(PYTHONDONTWRITEBYTECODE="1")
    env["PATH"] = "%s%s%s" % (fx / "fake" / "bin", os.pathsep, env["PATH"])
    env["FIXTURE_ROOT"] = str(fx)
    env["FAKE_DATA"] = str(data_dir(fx))
    env["FAKE_LOG"] = str(log)
    if side == "new":
        env["PYTHONPATH"] = str(fx / ".ci")
    return env


def run_both(fx: pathlib.Path, *args: str) -> tuple[tuple, tuple, list[str], list[str]]:
    """Both implementations, same fixture, same fakes. Returns results AND call logs."""
    results = []
    logs = []
    for side, argv in (
        ("old", ["bash", str(fx / TWIN_REL)]),
        ("new", ["python3", str(fx / PORT_REL)]),
    ):
        log = fx / ("calls.%s" % side)
        log.write_text("", encoding="utf-8")
        proc = subprocess.run(
            [*argv, *args],
            env=_env(fx, side, log),
            cwd=str(fx),
            capture_output=True,
            text=True,
            check=False,
            timeout=180,
        )
        results.append(
            (
                proc.returncode,
                proc.stdout.replace(str(fx), "<fx>"),
                proc.stderr.replace(str(fx), "<fx>"),
            )
        )
        logs.append(log.read_text(encoding="utf-8").splitlines())
    return results[0], results[1], logs[0], logs[1]


def assert_same(old: tuple, new: tuple) -> None:
    assert new[0] == old[0], "exit: twin %s, port %s" % (old[0], new[0])
    assert new[1] == old[1], "stdout:\n--- twin\n%s--- port\n%s" % (old[1], new[1])
    assert new[2] == old[2], "stderr:\n--- twin\n%s--- port\n%s" % (old[2], new[2])


def assert_agree(fx: pathlib.Path, *args: str) -> tuple:
    """Run both and assert on all four channels. Returns the twin's result."""
    old, new, old_log, new_log = run_both(fx, *args)
    assert new_log == old_log, "call log:\n--- twin\n%s\n--- port\n%s" % (
        "\n".join(old_log),
        "\n".join(new_log),
    )
    assert_same(old, new)
    return old


def mask_generated(text: str) -> str:
    return re.sub(r'"generatedAt": "[^"]*"', '"generatedAt": "<MASKED>"', text)


# --------------------------------------------------------------------------- Real runs against this repository ---------------------------------------------------------------------------


def _hashes() -> dict[str, str]:
    """sha256 of every guarded file. A MISSING one is a failure, not a skip.

    `if path.is_file(): ...` was the first version, and it makes the whole guard
    vacuous the moment a submodule is not checked out: `_hashes() == before`
    then compares two empty dicts and reports "nothing was mutated" having hashed nothing. All four are present in any working checkout, so demanding all four costs nothing and closes the hole.
    """
    out = {}
    for rel in GUARDED:
        path = ROOT / rel
        assert path.is_file(), (
            "%s is absent, so the read-only guard would compare nothing. "
            "Check out the submodules (git submodule update --init) rather than "
            "letting this case pass over an unhashed tree." % rel
        )
        out[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    assert len(out) == len(GUARDED)
    return out


def _run_real(*args: str) -> tuple[tuple, tuple]:
    results = []
    for side, argv in (("old", ["bash", str(TWIN)]), ("new", ["python3", str(PORT)])):
        env = differential.env_for(PYTHONDONTWRITEBYTECODE="1")
        if side == "new":
            env["PYTHONPATH"] = str(ROOT / ".ci")
        proc = subprocess.run(
            [*argv, *args],
            env=env,
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            check=False,
            timeout=600,
        )
        results.append((proc.returncode, proc.stdout, proc.stderr))
    return results[0], results[1]


def test_the_real_repository_agrees_in_table_format() -> None:
    """1,760 records over four real packages, byte for byte on both streams.

    No fixture reproduces this input, and it is the only case that exercises `align_tsv` at real column widths, the four real truncation warnings and the real Go module graph at once.
    """
    before = _hashes()
    old, new = _run_real()
    assert old[0] == 0, "the twin failed on the real tree:\n%s" % old[2]
    assert_same(old, new)
    # SEEN the verdict, not matched two empty strings.
    assert "SUMMARY  packages=4  records=" in old[1]
    assert old[1].count("\n") > 1000, "the real inventory collapsed to %d lines" % (
        old[1].count("\n")
    )
    assert "chains capped for" in old[2], "no truncation warning: --max-chains is not biting"
    assert _hashes() == before, "a real run mutated a lockfile"


def test_the_real_repository_agrees_in_json_format() -> None:
    """`jq .` against `json.dumps(indent=2, ensure_ascii=False)`, on 1.1 MB.

    `generatedAt` is the one masked field; everything else, including key ORDER and the exact indentation of a 25-deep chain array, is compared raw.
    """
    before = _hashes()
    old, new = _run_real("--format", "json", "--max-chains", "3")
    assert old[0] == 0, "the twin failed on the real tree:\n%s" % old[2]
    assert new[0] == old[0]
    assert new[2] == old[2]
    assert mask_generated(new[1]) == mask_generated(old[1])
    assert "<MASKED>" in mask_generated(old[1]), "the mask matched nothing"
    document = json.loads(old[1])
    assert document["summary"]["packagesAnalyzed"] == 4
    assert document["summary"]["totals"]["records"] > 1000
    assert _hashes() == before, "a real run mutated a lockfile"


# --------------------------------------------------------------------------- Argument handling (no external tool involved) ---------------------------------------------------------------------------


def test_help_is_byte_identical(fixture: pathlib.Path) -> None:
    """Including the eight lines of leaked shell source; see the port's note 2."""
    old = assert_agree(fixture, "--help")
    assert old[0] == 0
    assert "set -euo pipefail" in old[1], "the leak this case pins is gone from the twin"


def test_help_text_constant_still_matches_the_twin() -> None:
    """`sed -n '2,35p' "$0" | sed 's/^# \\?//'`, re-derived from the twin's bytes.

    The port cannot slice its OWN source and get the twin's header, so the text is a constant -- and a constant is a second source of truth unless something re-derives it. This is that something.
    """
    lines = TWIN.read_text(encoding="utf-8").split("\n")[1:35]
    derived = "".join(re.sub(r"^# ?", "", line) + "\n" for line in lines)
    assert derived == port.HELP_TEXT


def test_the_jq_diagnostics_still_match_this_host() -> None:
    """The two jq error texts the port emits, re-derived from the jq on PATH.

    THE --argjson BANNER IS NO LONGER A CONSTANT, and this test is why the change was needed rather than optional. jq moved its documentation URL between releases -- 1.7.x says `https://jqlang.github.io/jq`, 1.8.x says `https://jqlang.org` -- so a pinned string is right on one host and wrong on another AT THE SAME TIME. That is not drift a pin can catch up with; both hosts are
    correct. The port now asks jq, and what this test checks is that asking produces exactly what jq produces, and that the answer is not vacuous.

    `JQ_OPEN_ERROR` stays a constant: it carries no version-dependent text, and it is still asserted below so a future jq rewording it goes red here.
    """
    banner = subprocess.run(
        ["jq", "-c", "--argjson", "p", "", "."],
        input="{}",
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    port.jq_argjson_banner.cache_clear()
    assert port.jq_argjson_banner() == banner.stderr
    # ANTI-VACUITY: a probe that returned "" and fell back would still satisfy the equality above if jq had also printed nothing. Pin the shape.
    assert banner.stderr.startswith("jq: invalid JSON text passed to --argjson\n")
    assert "online docs  at https://" in banner.stderr
    missing = subprocess.run(
        ["jq", "-c", ".", "/nonexistent/package.json"],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert missing.stderr == port.JQ_OPEN_ERROR % "/nonexistent/package.json"


def test_an_unknown_option(fixture: pathlib.Path) -> None:
    old = assert_agree(fixture, "--bogus")
    assert old[0] == 1
    assert "Unknown option: --bogus" in old[2]


def test_a_bad_format(fixture: pathlib.Path) -> None:
    old = assert_agree(fixture, "--format", "xml")
    assert old[0] == 1
    assert "--format must be 'json' or 'table'" in old[2]


@pytest.mark.parametrize("value", ["abc", "-1", "", "1.5", "1e3", " 7"])
def test_a_bad_max_chains(fixture: pathlib.Path, value: str) -> None:
    """`^[0-9]+$` in bash, `all(char in "0123456789")` here. Six spellings of wrong."""
    old = assert_agree(fixture, "--max-chains", value)
    assert old[0] == 1
    assert "--max-chains must be a non-negative integer" in old[2]


@pytest.mark.parametrize("flag", ["--format", "--output", "--max-chains"])
def test_a_missing_option_value(fixture: pathlib.Path, flag: str) -> None:
    """THE ONE STRUCTURALLY-NORMALISED CASE. See the port's note 3.

    Bash's `$2: unbound variable` names the SCRIPT's path and the SCRIPT's line number, neither of which the port can honestly copy. Exit code, stdout and the call log are still compared raw; only the path and the number are replaced, and the sentence itself is asserted intact on both sides.
    """
    old, new, old_log, new_log = run_both(fixture, flag)
    assert new_log == old_log == []
    assert new[0] == old[0] == 1
    assert new[1] == old[1] == ""
    shape = re.compile(r"^\S+: line \d+: \$2: unbound variable\n$")
    assert shape.match(old[2]), "the twin's diagnostic changed shape: %r" % old[2]
    assert shape.match(new[2]), "the port's diagnostic changed shape: %r" % new[2]
    normalise = re.compile(r"^\S+: line \d+:")
    assert normalise.sub("<script>: line <N>:", new[2]) == normalise.sub(
        "<script>: line <N>:", old[2]
    )


# --------------------------------------------------------------------------- Fixture happy paths ---------------------------------------------------------------------------


def test_the_fixture_baseline_is_green(fixture: pathlib.Path) -> None:
    """THE CONTROL FOR EVERY OTHER FIXTURE CASE, and the NEGATIVE selftest direction."""
    old = assert_agree(fixture)
    assert old[0] == 0, "the fixture baseline is not green:\n%s" % old[2]
    assert "SUMMARY  packages=4  records=" in old[1]


def test_the_fixture_calls_exactly_the_nine_expected_commands(fixture: pathlib.Path) -> None:
    """The call log itself, asserted rather than merely compared.

    Comparing two logs proves the two sides agree; it does not prove either one
    asked the right thing. If both stopped calling `--omit=dev` they would still
    agree, and `prodReachable` would silently become false everywhere.
    """
    old, new, old_log, _new_log = run_both(fixture)
    assert old[0] == 0, old[2]
    assert old_log == [
        "FAKECALL npm ls --all --json --workspace @rediacc/www [cwd=]",
        "FAKECALL npm ls --all --json --omit=dev --workspace @rediacc/www [cwd=]",
        "FAKECALL npm ls --all --json --workspace @rediacc/cli [cwd=]",
        "FAKECALL npm ls --all --json --omit=dev --workspace @rediacc/cli [cwd=]",
        "FAKECALL npm ls --all --json [cwd=/private/account]",
        "FAKECALL npm ls --all --json --omit=dev [cwd=/private/account]",
        "FAKECALL go list -m [cwd=/private/renet]",
        "FAKECALL go list -m -json all [cwd=/private/renet]",
        "FAKECALL go mod graph [cwd=/private/renet]",
    ]
    assert new[0] == 0


def test_chain_truncation_is_logged_not_silent(fixture: pathlib.Path) -> None:
    """`--max-chains 1` against a diamond, so `gamma` really has two chains."""
    old = assert_agree(fixture, "--max-chains", "1")
    assert old[0] == 0
    assert "@rediacc/www: chains capped for gamma@0.1.0 (2 chains)" in old[2]


def test_unlimited_chains(fixture: pathlib.Path) -> None:
    """`--max-chains 0`: no cap, and therefore no warning."""
    old = assert_agree(fixture, "--max-chains", "0")
    assert old[0] == 0
    assert "chains capped" not in old[2], "0 should mean unlimited, not zero"


def test_json_format_on_the_fixture(fixture: pathlib.Path) -> None:
    """Small enough to assert the SHAPE, which the 1.1 MB real case cannot."""
    old, new, old_log, new_log = run_both(fixture, "--format", "json", "--max-chains", "1")
    assert new_log == old_log
    assert new[0] == old[0] == 0
    assert new[2] == old[2]
    assert mask_generated(new[1]) == mask_generated(old[1])
    document = json.loads(old[1])
    assert document["tool"] == {"name": "dependency-inventory.sh", "maxChains": 1}
    assert [package["name"] for package in document["packages"]] == [
        "@rediacc/www",
        "@rediacc/cli",
        "@rediacc/account",
        "renet",
    ]
    gamma = next(
        record for record in document["packages"][0]["dependencies"] if record["name"] == "gamma"
    )
    assert gamma["totalChains"] == 2
    assert gamma["chainsTruncated"] is True
    assert len(gamma["chains"]) == 1
    renet = document["packages"][3]
    assert renet["edges"] == [
        {"from": "example.com/renet", "to": "github.com/x/a@v1.0.0"},
        {"from": "github.com/x/a@v1.0.0", "to": "github.com/x/b@v2.0.0"},
        {"from": "github.com/x/b@v2.0.0", "to": "github.com/x/c@v3.0.0"},
    ]
    assert [record["depth"] for record in renet["dependencies"]] == [1, 2, 3]


@pytest.mark.parametrize("fmt", ["table", "json"])
def test_output_to_a_file(fixture: pathlib.Path, fmt: str) -> None:
    """`--output` writes the document and logs one line; stdout stays empty.

    The two sides write to DIFFERENT paths on purpose, because the confirmation line quotes the path: writing to one shared path would let a port that never wrote anything pass by reading the twin's file.
    """
    results = []
    logs = []
    for side, argv in (
        ("old", ["bash", str(fixture / TWIN_REL)]),
        ("new", ["python3", str(fixture / PORT_REL)]),
    ):
        log = fixture / ("calls.%s" % side)
        log.write_text("", encoding="utf-8")
        target = fixture / ("out.%s.txt" % side)
        proc = subprocess.run(
            [*argv, "--format", fmt, "--output", str(target)],
            env=_env(fixture, side, log),
            cwd=str(fixture),
            capture_output=True,
            text=True,
            check=False,
            timeout=180,
        )
        results.append(
            (
                proc.returncode,
                proc.stdout,
                proc.stderr.replace(str(target), "<out>").replace(str(fixture), "<fx>"),
                target.read_text(encoding="utf-8") if target.is_file() else None,
            )
        )
        logs.append(log.read_text(encoding="utf-8").splitlines())
    old, new = results
    assert logs[1] == logs[0]
    assert new[0] == old[0] == 0
    assert new[1] == old[1] == "", "--output must leave stdout empty"
    assert new[2] == old[2]
    assert "Wrote %s inventory to <out>" % ("JSON" if fmt == "json" else "table") in old[2]
    assert old[3] is not None
    assert mask_generated(new[3]) == mask_generated(old[3])


# --------------------------------------------------------------------------- Fixture failure paths ---------------------------------------------------------------------------


def test_a_missing_workspace_node_modules(fixture: pathlib.Path) -> None:
    shutil.rmtree(fixture / "node_modules")
    old = assert_agree(fixture)
    assert old[0] == 1
    assert "missing. Run 'npm install'" in old[2]


def test_a_missing_standalone_node_modules(fixture: pathlib.Path) -> None:
    """The other arm of the same check, which reads a DIFFERENT directory."""
    shutil.rmtree(fixture / "private" / "account" / "node_modules")
    old = assert_agree(fixture)
    assert old[0] == 1
    assert "@rediacc/account: <fx>/private/account/node_modules missing" in old[2]


def test_npm_producing_invalid_json(fixture: pathlib.Path) -> None:
    (data_dir(fixture) / "npm.@rediacc_www.all").write_text("not json", encoding="utf-8")
    old = assert_agree(fixture)
    assert old[0] == 1
    assert "@rediacc/www: npm ls produced invalid JSON" in old[2]


def test_an_invalid_prod_tree_is_tolerated(fixture: pathlib.Path) -> None:
    """`prodset='{}'`: the run continues and every record reports prodReachable false.

    The POSITIVE control's twin. Without it nothing distinguishes "invalid prod tree" from "invalid all tree", and a port that failed on either would pass every other case here.
    """
    (data_dir(fixture) / "npm.@rediacc_www.prod").write_text("not json", encoding="utf-8")
    old = assert_agree(fixture)
    assert old[0] == 0
    assert "SUMMARY  packages=4" in old[1]


def test_npm_printing_nothing_silently_drops_the_package(fixture: pathlib.Path) -> None:
    """A REPRODUCED DEFECT, pinned so nobody 'fixes' one side alone.

    With `tree_all` empty every jq downstream has no input and emits none, so `$WORK/pkg_0.json` is written EMPTY, `jq -s` slurps nothing from it, and @rediacc/www vanishes from an SBOM that still exits 0 and still says
    `packages=3` as though three were all that was asked for. Reported in this
    wave's findings; fixed in neither side, because a one-sided fix would make this differential lie.
    """
    (data_dir(fixture) / "npm.@rediacc_www.all").write_text("", encoding="utf-8")
    old = assert_agree(fixture)
    assert old[0] == 0, "the twin still exits 0, which is the defect"
    assert "SUMMARY  packages=3" in old[1]
    assert "@rediacc/www" not in old[1]
    assert "@rediacc/www" in old[2], "only the 'Analyzing' line survives"


def test_an_empty_prod_tree_dies_on_a_raw_jq_diagnostic(fixture: pathlib.Path) -> None:
    """A second REPRODUCED DEFECT: `--argjson prodset ""`, exit 2, no explanation.

    `jq -c '<keyset>' <<<""` produces no output, the shell assigns the empty string, and jq refuses it with its usage banner. Nothing in the message names npm, the package or the tool.
    """
    (data_dir(fixture) / "npm.@rediacc_www.prod").write_text("", encoding="utf-8")
    old = assert_agree(fixture)
    assert old[0] == 2
    assert old[2].endswith(port.jq_argjson_banner())
    assert "npm" not in old[2].split("Analyzing")[-1], "the banner still says nothing useful"


def test_a_missing_package_json_dies_on_a_raw_jq_diagnostic(fixture: pathlib.Path) -> None:
    """A third: exit 2 with jq's `Could not open file`, and no gate-level line."""
    (fixture / "packages" / "www" / "package.json").unlink()
    old = assert_agree(fixture)
    assert old[0] == 2
    assert "Could not open file <fx>/packages/www/package.json" in old[2]


@pytest.mark.parametrize(
    ("probe", "message"),
    [
        ("listm", "go list -m failed in"),
        ("modules", "go list -m -json all failed in"),
        ("graph", "go mod graph failed in"),
    ],
)
def test_a_failing_go_probe(fixture: pathlib.Path, probe: str, message: str) -> None:
    """Each probe's own error, and the four-space indent of its captured stderr."""
    (data_dir(fixture) / ("go.%s.err" % probe)).write_text(
        "go: some error\ngo: second line\n", encoding="utf-8"
    )
    old = assert_agree(fixture)
    assert old[0] == 1
    assert message in old[2]
    assert "    go: some error\n    go: second line\n" in old[2]


def test_a_go_probe_whose_stderr_lacks_a_final_newline(fixture: pathlib.Path) -> None:
    """GNU sed PRESERVES a missing final newline rather than adding one.

    The reflex is the opposite, and the port got it wrong first:

        $ printf 'a\\nb' | sed 's/^/    /' | xxd
        2020 2020 610a 2020 2020 62          .a.    b

    A `go` probe that dies mid-line is the only way to reach it, so nothing else in this file would have caught the extra byte.
    """
    (data_dir(fixture) / "go.listm.err").write_text("go: broke", encoding="utf-8")
    old = assert_agree(fixture)
    assert old[0] == 1
    assert old[2].endswith("    go: broke"), "the twin terminated the line after all: %r" % (
        old[2][-30:],
    )


def test_a_silent_go_probe_failure_prints_no_indented_block(fixture: pathlib.Path) -> None:
    """`[[ -s "$probe_err" ]]`: an EMPTY stderr must produce no blank indented line."""
    (data_dir(fixture) / "go.listm.err").write_text("", encoding="utf-8")
    old = assert_agree(fixture)
    assert old[0] == 1
    assert "go list -m failed in" in old[2]
    assert "\n    \n" not in old[2]
    assert not old[2].endswith("    \n")


def test_an_empty_go_mod_graph(fixture: pathlib.Path) -> None:
    """The twin's own anti-vacuity refusal: zero edges is not zero dependencies."""
    (data_dir(fixture) / "go.graph").write_text("   \n\n", encoding="utf-8")
    old = assert_agree(fixture)
    assert old[0] == 1
    assert "refusing to emit an empty dependency graph" in old[2]


def test_a_workspace_key_absent_from_the_npm_tree(fixture: pathlib.Path) -> None:
    """`rootexpr // {}`: jq indexes null without raising, and the package is empty.

    Distinct from the empty-output case above: here `npm ls` returns a VALID tree that simply does not mention the workspace, so the package object DOES appear, with zero dependencies.
    """
    (data_dir(fixture) / "npm.@rediacc_www.all").write_text(
        '{"name":"root","dependencies":{}}\n', encoding="utf-8"
    )
    old = assert_agree(fixture)
    assert old[0] == 0
    assert "=== @rediacc/www [npm]  direct=0 transitive=0 total=0 ===" in old[1]


def test_colour_is_emitted_when_stderr_is_a_terminal(fixture: pathlib.Path) -> None:
    """`[[ -t 2 ]] && [[ -z "${NO_COLOR:-}" ]]`, the branch a human sees.

    Every other case runs off a tty and therefore proves only the uncoloured half. `CI` is left unset: `rediacc_ci.log` also disables colour on
    `CI=true` while common.sh does not, which is `log.py`'s documented
    deliberate divergence and is not this tool's subject.
    """
    log = fixture / "calls.tty"
    log.write_text("", encoding="utf-8")
    old = differential.bash_streams(
        "bash %s" % (fixture / TWIN_REL),
        env=_env(fixture, "old", log),
        cwd=str(fixture),
        tty="stderr",
    )
    log.write_text("", encoding="utf-8")
    new = differential.bash_streams(
        "python3 %s" % (fixture / PORT_REL),
        env=_env(fixture, "new", log),
        cwd=str(fixture),
        tty="stderr",
    )
    assert differential.escape_bytes(old[2]) > 0, "the twin printed no colour on a tty"
    assert_same(old, new)


# --------------------------------------------------------------------------- The exported helpers, driven directly (the selftest half) ---------------------------------------------------------------------------


def test_walk_tree_emits_one_record_per_occurrence() -> None:
    """Not per NAME: the whole chain model depends on the difference."""
    tree = {
        "a": {"version": "1", "dependencies": {"c": {"version": "3"}}},
        "b": {"version": "2", "dependencies": {"c": {"version": "3"}}},
    }
    records = list(port.walk_tree(tree, ()))
    assert [(r["name"], r["depth"]) for r in records] == [
        ("a", 1),
        ("c", 2),
        ("b", 1),
        ("c", 2),
    ]
    assert records[1]["chain"] == ["a@1", "c@3"]
    assert records[3]["chain"] == ["b@2", "c@3"]


def test_walk_tree_defaults_a_missing_version_to_unknown_in_the_chain() -> None:
    """`$v.version // "unknown"` in the chain, `//null` in the record. Both spellings."""
    records = list(port.walk_tree({"a": {}}, ()))
    assert records == [{"name": "a", "version": None, "depth": 1, "chain": ["a@unknown"]}]


def test_type_map_lets_dependencies_win() -> None:
    """jq's object `+` is right-biased, and the twin merges `dependencies` LAST."""
    assert port.type_map({"devDependencies": {"x": "1"}, "dependencies": {"x": "1"}}) == {
        "x": "dependencies"
    }
    assert port.type_map({"devDependencies": {"x": "1"}}) == {"x": "devDependencies"}


def test_group_dependencies_sorts_direct_before_transitive() -> None:
    tree = {
        "zeta": {"version": "1", "dependencies": {"alpha": {"version": "9"}}},
        "beta": {"version": "2"},
    }
    records = port.group_dependencies(tree, {}, {}, 25)
    assert [(r["level"], r["depth"], r["name"]) for r in records] == [
        ("direct", 1, "beta"),
        ("direct", 1, "zeta"),
        ("transitive", 2, "alpha"),
    ]


def test_group_dependencies_caps_and_flags_chains() -> None:
    tree = {
        "a": {"version": "1", "dependencies": {"c": {"version": "3"}}},
        "b": {"version": "2", "dependencies": {"c": {"version": "3"}}},
    }
    capped = next(r for r in port.group_dependencies(tree, {}, {}, 1) if r["name"] == "c")
    assert capped["totalChains"] == 2
    assert capped["chainsTruncated"] is True
    assert capped["chains"] == [["a@1", "c@3"]]
    uncapped = next(r for r in port.group_dependencies(tree, {}, {}, 0) if r["name"] == "c")
    assert uncapped["chainsTruncated"] is False
    assert len(uncapped["chains"]) == 2


def test_bfs_chains_takes_the_shortest_path() -> None:
    """Two routes to `d`; BFS must pick the two-hop one, not the three-hop one."""
    edges = "r a\nr b\na d\nb c\nc d\n"
    found = port.bfs_chains(edges, "r")
    assert found["d"] == {"depth": 2, "chain": ["a", "d"]}
    assert "r" not in found, "the main module must not appear in its own chain set"


def test_align_tsv_pads_to_the_widest_cell_and_rstrips() -> None:
    assert port.align_tsv([["a", "bb"], ["ccc", "d"]]) == ["a    bb", "ccc  d"]
    assert port.align_tsv([["a", ""]]) == ["a"]


def test_jq_tostring_matches_jq() -> None:
    assert port._jq_tostring(True) == "true"
    assert port._jq_tostring(False) == "false"
    assert port._jq_tostring(None) == "null"
    assert port._jq_tostring(3) == "3"


def test_slurp_reads_a_stream_of_concatenated_values() -> None:
    assert port._slurp('{"a":1}\n{"b":2}\n') == [{"a": 1}, {"b": 2}]
    assert port._slurp("") == []
    assert port._slurp("{oops}") is None


def test_jq_empty_distinguishes_no_value_from_invalid_from_null() -> None:
    """THE THREE-WAY DISTINCTION the two reproduced defects hang on."""
    assert port._jq_empty("") is port._NOVALUE
    assert port._jq_empty("  \n") is port._NOVALUE
    assert port._jq_empty("not json") is port._INVALID
    assert port._jq_empty("null") is None
    assert port._jq_empty("{}") == {}
