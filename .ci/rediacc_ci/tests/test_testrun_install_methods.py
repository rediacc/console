"""`rediacc_ci.testrun.install_methods` against its bash twin `.ci/scripts/test/test-install-methods.sh`.

A local HTTP server plays the release channel (`latest.json`, `manifest.json`, a shell-script `rdc`, the `.repo` file) and a FAKE `docker` records every invocation, so both sides run the same tests against the same fixtures with real `curl`. Compared per case: exit code, stdout, stderr and the fake docker's call log, including the container scripts (comment lines stripped: the quick-install script drops a block that cited line numbers of the bash file). A real run against the production edge channel, real Docker and the real images is in the porting report.

INTENTIONAL DELTAS (Rule T), each a `test_delta_*` failing on the bash behaviour: an unresolvable `latest`; a version with `+`; the promotion test's channel-less skip; no jq needed; a failing `docker pull`; a failing download named as such.
"""

from __future__ import annotations

import functools
import http.server
import json
import re
import shutil
import subprocess
import threading
import typing

import pytest

from rediacc_ci.testrun import install_methods as port
from rediacc_ci.testrun import install_scripts
from rediacc_ci.tests import testrun_support as ts

if typing.TYPE_CHECKING:
    import pathlib

TWIN = ".ci/scripts/test/test-install-methods.sh"
MODULE = "rediacc_ci.testrun.install_methods"
VERSION = "1.2.3"
FENCED = f"__RDC_VERSION_BEGIN__\n{VERSION}\n__RDC_VERSION_END__"

RDC = f"""#!/bin/bash
if [[ "$1" == "--version" ]]; then echo {VERSION}; exit 0; fi
if [[ "$1" == "doctor" ]]; then
  echo "doctor: a warning on stderr" >&2
  echo '{{"Environment":[{{"name":"Update channel","value":"'"${{REDIACC_UPDATE_CHANNEL:-stable}}"'"}},{{"name":"Account server","value":"https://acct.example"}}]}}'
  exit 1
fi
"""


class Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *_args: object) -> None:
        return


@pytest.fixture(scope="module")
def channel(tmp_path_factory: pytest.TempPathFactory) -> typing.Iterator[str]:
    root = tmp_path_factory.mktemp("channel")
    server = http.server.ThreadingHTTPServer(
        ("127.0.0.1", 0), functools.partial(Handler, directory=str(root))
    )
    url = f"http://127.0.0.1:{server.server_address[1]}"
    for ch in ("edge", "empty", "badver"):
        (root / "cli" / ch).mkdir(parents=True)
        (root / "rpm" / ch).mkdir(parents=True)
        (root / "cli" / ch / "latest.json").write_text(json.dumps({"version": VERSION}))
        binary = root / "cli" / ch / "rdc-linux-x64"
        binary.write_text(RDC)
        binary.chmod(0o755)
        (root / "rpm" / ch / "rediacc.repo").write_text(
            f"[rediacc]\nbaseurl={url}/rpm/{ch}/\ngpgkey={url}/rpm/{ch}/gpg.key\n"
        )
    (root / "cli/v1.2.3").mkdir()
    shutil.copy(root / "cli/edge/rdc-linux-x64", root / "cli/v1.2.3/rdc-linux-x64")
    good = {
        "version": VERSION,
        "binaries": {"linux-x64": {"url": f"{url}/cli/v1.2.3/rdc-linux-x64", "sha256": "x"}},
    }
    (root / "cli/edge/manifest.json").write_text(json.dumps(good))
    (root / "cli/empty/manifest.json").write_text(json.dumps({"version": VERSION, "binaries": {}}))
    (root / "cli/badver/manifest.json").write_text(json.dumps({**good, "version": "1.2.30"}))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield url
    server.shutdown()
    server.server_close()


def strip_comments(text: str) -> str:
    return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))


def mask(text: str, directory: pathlib.Path, url: str) -> str:
    return ts.mask(text, directory).replace(url, "<URL>")


def both(
    tmp_path: pathlib.Path,
    args: list[str],
    env: dict[str, str] | None = None,
    tools: tuple[str, ...] = ("docker",),
    url: str = "http://127.0.0.1:1",
) -> tuple[ts.Outcome, ts.Outcome, pathlib.Path, pathlib.Path]:
    base = {
        "RELEASES_BASE_URL": url,
        "REPO_CHANNEL": "",
        "FAKE_OUT_DOCKER": FENCED,
        "CI": "",
        **(env or {}),
    }
    od, nd = tmp_path / "bash", tmp_path / "py"
    old = ts.run_side(ts.bash_cmd(TWIN, *args), od, tools, base, timeout=300)
    new = ts.run_side(ts.py_cmd(MODULE, *args), nd, tools, ts.py_env(base), timeout=300)
    return old, new, od, nd


def calls(outcome: ts.Outcome) -> list[tuple]:
    return [(call["tool"], [strip_comments(a) for a in call["argv"]]) for call in outcome.calls]


def same(
    old: ts.Outcome,
    new: ts.Outcome,
    od: pathlib.Path,
    nd: pathlib.Path,
    url: str = "http://127.0.0.1:1",
) -> None:
    assert calls(new) == calls(old)
    assert (new.code, mask(new.out, nd, url), mask(new.err, nd, url)) == (
        old.code,
        mask(old.out, od, url),
        mask(old.err, od, url),
    )


# ---- arguments ---------------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "args",
    [
        ["--bogus"],
        ["--method"],
        ["--method", ""],
        ["--method", "bogus", "--dry-run"],
        ["--version"],
        ["--platform", "beos", "--dry-run"],
        ["--arch", "mips", "--dry-run"],
        ["--local-artifacts"],
        ["--dry-run", "extra"],
    ],
)
def test_argument_refusals_match_the_twin(tmp_path: pathlib.Path, args: list[str]) -> None:
    old, new, od, nd = both(tmp_path, args)
    assert old.code == 2
    same(old, new, od, nd)


@pytest.mark.parametrize(
    "method",
    [
        "binary",
        "verify",
        "update",
        "promote",
        "docker",
        "apt",
        "dnf",
        "apk",
        "pacman",
        "homebrew",
        "npm",
        "quick",
        "all",
    ],
)
@pytest.mark.parametrize("platform", ["linux", "mac", "win"])
def test_dry_run_matrix_matches_the_twin(
    tmp_path: pathlib.Path, method: str, platform: str
) -> None:
    old, new, od, nd = both(
        tmp_path,
        [
            "--dry-run",
            "--method",
            method,
            "--platform",
            platform,
            "--arch",
            "x64",
            "--version",
            "1.2.3",
        ],
        {"REPO_CHANNEL": "edge"},
    )
    assert old.code == 0
    same(old, new, od, nd)


def test_dry_run_without_a_channel_matches_the_twin(tmp_path: pathlib.Path) -> None:
    old, new, od, nd = both(
        tmp_path, ["--dry-run", "--version", "1.2.3", "--platform", "linux", "--arch", "arm64"]
    )
    assert old.code == 0
    same(old, new, od, nd)


def path_without_docker(directory: pathlib.Path) -> str:
    """A PATH holding the coreutils the twin needs and no `docker` (the host's real one lives in /usr/bin, so a sealed PATH alone is not enough)."""
    bindir = directory / "nodocker"
    bindir.mkdir(parents=True)
    for tool in (
        "bash",
        "dirname",
        "basename",
        "mktemp",
        "stat",
        "uname",
        "rm",
        "cat",
        "sed",
        "grep",
        "head",
        "env",
        "tr",
        "ls",
        "date",
    ):
        found = shutil.which(tool)
        if found:
            (bindir / tool).symlink_to(found)
    return str(bindir)


def test_a_missing_docker_is_refused_the_same_way(tmp_path: pathlib.Path) -> None:
    results = []
    for name, runner in (
        (
            "bash",
            ts.bash_cmd(
                TWIN,
                "--method",
                "apt",
                "--version",
                VERSION,
                "--platform",
                "linux",
                "--arch",
                "x64",
            ),
        ),
        (
            "py",
            ts.py_cmd(
                MODULE,
                "--method",
                "apt",
                "--version",
                VERSION,
                "--platform",
                "linux",
                "--arch",
                "x64",
            ),
        ),
    ):
        directory = tmp_path / name
        directory.mkdir()
        env = {
            "PATH": path_without_docker(directory),
            "HOME": str(directory),
            "TMPDIR": str(directory),
            "REPO_CHANNEL": "edge",
            "RELEASES_BASE_URL": "http://127.0.0.1:1",
            "LC_ALL": "C",
        }
        if name == "py":
            env["PYTHONPATH"] = str(ts.ROOT / ".ci")
        results.append(
            subprocess.run(
                runner,
                env=env,
                capture_output=True,
                text=True,
                check=False,
                cwd=str(directory),
                stdin=subprocess.DEVNULL,
                timeout=60,
            )
        )
    old, new = results
    assert old.returncode == new.returncode == 1
    assert "Required command 'docker' is not available" in old.stderr
    assert "Required command 'docker' is not available" in new.stderr


# ---- verify_version ----------------------------------------------------------------------------------------------------------


def bash_verify(output: str, expected: str) -> int:
    text = (ts.ROOT / TWIN).read_text()
    func = text[
        text.index("verify_version() {") : text.index("\n}\n", text.index("verify_version() {")) + 3
    ]
    script = f'source "{ts.ROOT}/.ci/scripts/lib/common.sh"\n{func}\nverify_version "$1" "$2"'
    return subprocess.run(
        [ts.BASH, "-c", script, "x", output, expected],
        capture_output=True,
        text=True,
        check=False,
        stdin=subprocess.DEVNULL,
    ).returncode


CASES = [
    ("1.2.3", "1.2.3"),
    ("v1.2.3", "1.2.3"),
    ("rdc 1.2.3 (build)", "1.2.3"),
    ("1.2.30", "1.2.3"),
    ("11.2.3", "1.2.3"),
    ("1.2.3.4", "1.2.3"),
    ("1x2y3", "1.2.3"),
    ("", "1.2.3"),
    ("1.2.3", ""),
    ("1.2.3", "latest"),
    ("v10.20.30-rc.1", "latest"),
    ("not a version", "latest"),
    ("1.2", "latest"),
    ("banner\n1.2.3", "latest"),
    ("banner\nrdc 1.2.3", "1.2.3"),
    ("1.2.3-rc.1", "1.2.3-rc.1"),
    ("1.2.3-rc.10", "1.2.3-rc.1"),
]


@pytest.mark.parametrize(("output", "expected"), CASES)
def test_verify_version_matches_the_twin(output: str, expected: str) -> None:
    assert port.verify_version(output, expected) == (bash_verify(output, expected) == 0)


def test_fence_extraction_matches_the_twin() -> None:
    transcript = "install noise 1.2.3\nstuff__RDC_VERSION_BEGIN__\n1.2.3\nmore\n__RDC_VERSION_END__\ntrailing 9.9.9"
    text = (ts.ROOT / TWIN).read_text()
    func = text[
        text.index("extract_fenced_version() {") : text.index(
            "\n}\n", text.index("extract_fenced_version() {")
        )
        + 3
    ]
    script = f'VERSION_FENCE_BEGIN="__RDC_VERSION_BEGIN__"\nVERSION_FENCE_END="__RDC_VERSION_END__"\n{func}\nextract_fenced_version "$1"'
    done = subprocess.run(
        [ts.BASH, "-c", script, "x", transcript], capture_output=True, text=True, check=False
    )
    assert port.extract_fenced_version(transcript) == done.stdout.rstrip("\n")


# ---- channel tests against the local channel ---------------------------------------------------------------------------------


@pytest.mark.parametrize("method", ["binary", "update", "verify", "promote"])
def test_channel_methods_match_the_twin(tmp_path: pathlib.Path, channel: str, method: str) -> None:
    old, new, od, nd = both(
        tmp_path,
        ["--method", method, "--version", VERSION, "--platform", "linux", "--arch", "x64"],
        {"REPO_CHANNEL": "edge"},
        url=channel,
    )
    assert old.code == 0, old.err
    same(old, new, od, nd, channel)


@pytest.mark.parametrize(
    "method", ["binary", "update", "verify", "apt", "dnf", "apk", "pacman", "npm", "quick"]
)
def test_channel_less_runs_skip_the_same_way(
    tmp_path: pathlib.Path, channel: str, method: str
) -> None:
    old, new, od, nd = both(
        tmp_path,
        ["--method", method, "--version", VERSION, "--platform", "linux", "--arch", "x64"],
        {"REPO_CHANNEL": ""},
        url=channel,
    )
    assert old.code == 0
    same(old, new, od, nd, channel)


def test_wrong_version_fails_the_same_way(tmp_path: pathlib.Path, channel: str) -> None:
    for method in ("binary", "update", "verify"):
        old, new, od, nd = both(
            tmp_path / method,
            ["--method", method, "--version", "9.9.9", "--arch", "x64"],
            {"REPO_CHANNEL": "edge"},
            url=channel,
        )
        assert old.code == 1
        same(old, new, od, nd, channel)


def test_manifest_defects_fail_the_same_way(tmp_path: pathlib.Path, channel: str) -> None:
    for ch in ("empty", "badver"):
        old, new, od, nd = both(
            tmp_path / ch,
            ["--method", "update", "--version", VERSION],
            {"REPO_CHANNEL": ch},
            url=channel,
        )
        assert old.code == 1
        same(old, new, od, nd, channel)


def test_latest_is_resolved_from_latest_json(tmp_path: pathlib.Path, channel: str) -> None:
    old, new, od, nd = both(
        tmp_path, ["--method", "binary", "--arch", "x64"], {"REPO_CHANNEL": "edge"}, url=channel
    )
    assert old.code == 0
    assert f"Version: {VERSION}" in old.err
    same(old, new, od, nd, channel)


def test_local_artifacts_match_the_twin(tmp_path: pathlib.Path) -> None:
    artifacts = tmp_path / "art"
    (artifacts / "cli").mkdir(parents=True)
    binary = artifacts / "cli" / "rdc-linux-x64"
    binary.write_text(RDC)
    binary.chmod(0o755)
    old, new, od, nd = both(
        tmp_path,
        [
            "--method",
            "binary",
            "--version",
            VERSION,
            "--arch",
            "x64",
            "--platform",
            "linux",
            "--local-artifacts",
            str(artifacts),
        ],
    )
    assert old.code == 0, old.err
    same(old, new, od, nd)
    old, new, od, nd = both(
        tmp_path / "missing",
        [
            "--method",
            "binary",
            "--version",
            VERSION,
            "--arch",
            "x64",
            "--platform",
            "linux",
            "--local-artifacts",
            str(tmp_path / "nope"),
        ],
    )
    assert old.code == 0
    same(old, new, od, nd)


# ---- container methods -------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "method", ["docker", "apt", "dnf", "apk", "pacman", "npm", "quick", "homebrew"]
)
def test_container_scripts_match_the_twin(tmp_path: pathlib.Path, method: str) -> None:
    env = {"REPO_CHANNEL": "pr-42", "RELEASES_BASE_URL": "https://releases.example.test"}
    old, new, od, nd = both(
        tmp_path,
        ["--method", method, "--version", VERSION, "--platform", "linux", "--arch", "x64"],
        env,
        url="https://releases.example.test",
    )
    assert old.code == 0, old.err
    assert old.calls, "the fake docker was never reached"
    same(old, new, od, nd, "https://releases.example.test")


@pytest.mark.parametrize(
    "fake_out",
    [
        "",
        "__RDC_VERSION_BEGIN__\n9.9.9\n__RDC_VERSION_END__",
        "no fence at all 1.2.3",
        "__RDC_VERSION_BEGIN__\n__RDC_VERSION_END__",
    ],
)
def test_container_version_failures_match_the_twin(tmp_path: pathlib.Path, fake_out: str) -> None:
    env = {"REPO_CHANNEL": "edge", "FAKE_OUT_DOCKER": fake_out}
    old, new, od, nd = both(
        tmp_path,
        ["--method", "dnf", "--version", VERSION, "--platform", "linux", "--arch", "x64"],
        env,
    )
    assert old.code == 1
    same(old, new, od, nd)


def test_container_nonzero_exit_matches_the_twin(tmp_path: pathlib.Path) -> None:
    old, new, od, nd = both(
        tmp_path,
        ["--method", "apk", "--version", VERSION, "--platform", "linux"],
        {"REPO_CHANNEL": "edge", "FAKE_RC_DOCKER": "3"},
    )
    assert old.code == 1
    assert "container exited 3" in old.err
    same(old, new, od, nd)


# ---- intentional deltas ------------------------------------------------------------------------------------------------------


def test_delta_an_unresolvable_latest_is_a_failure(tmp_path: pathlib.Path) -> None:
    old, new, *_ = both(
        tmp_path,
        ["--method", "binary", "--arch", "x64"],
        {"REPO_CHANNEL": "edge"},
        url="http://127.0.0.1:1",
    )
    assert "Version: latest" in old.err, "bash carried on with 'latest', which accepts any semver"
    assert new.code == 1
    assert "could not be resolved" in new.err
    assert not new.calls


def test_delta_a_plus_in_the_version_can_match_its_own_output() -> None:
    assert bash_verify("1.2.3+build.5", "1.2.3+build.5") != 0, "bash read + as an ERE quantifier"
    assert port.verify_version("1.2.3+build.5", "1.2.3+build.5")
    assert not port.verify_version("1.2.3+build.6", "1.2.3+build.5")


def test_delta_the_promotion_test_skips_without_a_channel(
    tmp_path: pathlib.Path, channel: str
) -> None:
    old, new, *_ = both(
        tmp_path, ["--method", "promote", "--version", VERSION], {"REPO_CHANNEL": ""}, url=channel
    )
    assert old.code == 1, "bash failed on a root path that is not published"
    assert "Failed to fetch .repo" in old.err
    assert new.code == 0
    assert "skipping promotion check" in new.err
    assert "SKIP: Promotion Config Fixup" in new.err


def test_delta_no_jq_is_needed(tmp_path: pathlib.Path, channel: str) -> None:
    """A PATH without jq: the twin skips the update check (77), the port still verifies the manifest."""
    old_dir, new_dir = tmp_path / "bash", tmp_path / "py"
    outcomes = []
    for directory, runner, py in (
        (old_dir, ts.bash_cmd(TWIN, "--method", "update", "--version", VERSION), False),
        (new_dir, ts.py_cmd(MODULE, "--method", "update", "--version", VERSION), True),
    ):
        bindir = ts.make_fakes(directory, ())
        for tool in (
            "bash",
            "curl",
            "dirname",
            "basename",
            "mktemp",
            "stat",
            "uname",
            "rm",
            "cat",
            "sed",
            "grep",
            "head",
            "env",
            "tr",
            "python3",
            "ls",
        ):
            found = shutil.which(tool)
            if found and not (bindir / tool).exists():
                (bindir / tool).symlink_to(found)
        env = {
            "PATH": str(bindir),
            "HOME": str(directory),
            "TMPDIR": str(directory),
            "RELEASES_BASE_URL": channel,
            "REPO_CHANNEL": "edge",
            "LC_ALL": "C",
        }
        if py:
            env["PYTHONPATH"] = str(ts.ROOT / ".ci")
        done = subprocess.run(
            runner,
            env=env,
            capture_output=True,
            text=True,
            check=False,
            cwd=str(directory),
            stdin=subprocess.DEVNULL,
        )
        outcomes.append(done)
    assert "jq not available" in outcomes[0].stderr
    assert "SKIP: Update Check" in outcomes[0].stderr
    assert outcomes[1].returncode == 0
    assert "Manifest version verified" in outcomes[1].stderr


def test_delta_a_failing_docker_pull_is_named(tmp_path: pathlib.Path) -> None:
    env = {"FAKE_RC_DOCKER": "1", "FAKE_RCWHEN_DOCKER": "pull", "FAKE_OUT_DOCKER": ""}
    old, new, *_ = both(
        tmp_path,
        ["--method", "docker", "--version", VERSION, "--platform", "linux", "--arch", "x64"],
        env,
    )
    assert old.code == 1
    assert "docker pull" not in old.err, (
        "bash ignored the failed pull and reported a version mismatch"
    )
    assert new.code == 1
    assert "docker pull ghcr.io/rediacc/rdc:latest failed" in new.err
    assert [c[1][0] for c in calls(new)] == ["pull"]


def test_delta_a_failing_download_is_named(tmp_path: pathlib.Path, channel: str) -> None:
    old, new, *_ = both(
        tmp_path,
        ["--method", "binary", "--version", VERSION, "--arch", "arm64", "--platform", "linux"],
        {"REPO_CHANNEL": "edge"},
        url=channel,
    )
    assert old.code == 1
    assert "Failed to download binary" not in old.err
    assert "No such file or directory" in old.err, (
        "bash reported the 404 as a missing ./rdc and a version mismatch"
    )
    assert new.code == 1
    assert "Failed to download binary from" in new.err


def test_the_container_scripts_carry_every_placeholder_the_renderer_fills() -> None:
    cfg = port.Config(repo_channel="c", releases="https://r")
    for name in ("APT", "DNF", "APK", "PACMAN", "NPM", "QUICK", "HOMEBREW"):
        template = getattr(install_scripts, name)
        rendered = port.render(
            template, cfg, "rdc --version", **{"@NPM_BEFORE@": "2026-01-01T00:00:00Z"}
        )
        assert not re.search(r"@[A-Z_]+@", rendered), name
