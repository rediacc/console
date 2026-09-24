"""How the devbox gets its Bitwarden Secrets Manager token, driven for real.

Two halves. `.devcontainer/devbox-bws.sh` is the login-shell hook bound to `/etc/profile.d/zz-devbox-bws.sh`: it reads `BWS_ACCESS_TOKEN` out of `$DEVBOX_WORKSPACE/private/account/.env` at shell start. `.ci/lib/devbox.sh` binds it (`devbox_script_binds`) and recreates a container created before the bind existed (`devbox_missing_binds`, read by `devbox_up`), because a bind only ever comes from `docker run`.

The hook is run under BOTH dash and bash: /etc/profile is read by `sh -l` as well, and a bashism would break every such login. The token in every fixture is a fake; the assertions that matter are that the value reaches the environment, that nothing else from the .env does, and that no stream ever carries it, including an xtrace.

The devbox.sh functions are LIFTED from the live library rather than restated, as `test_gate_devbox_probes.py` does, so this cannot drift into testing a copy.
"""

import re
import shutil
import stat
import subprocess

import pytest

from rediacc_ci import paths

HOOK = paths.from_root(".devcontainer", "devbox-bws.sh")
LIB = paths.from_root(".ci", "lib", "devbox.sh")
DEST = "/etc/profile.d/zz-devbox-bws.sh"
FAKE = "not-a-real-token-4f2a9c"

SHELLS = [s for s in ("dash", "bash") if shutil.which(s)]


def write_env(tmp_path, text: str):
    env_dir = tmp_path / "private" / "account"
    env_dir.mkdir(parents=True, exist_ok=True)
    (env_dir / ".env").write_text(text, encoding="utf-8")
    return tmp_path


def run_hook(
    shell: str, workspace, preset: str | None = None, xtrace: bool = False, token_file=None
):
    """Source the hook in a fresh shell and report what it exported, by name and by equality only."""
    body = (
        (". %s\n" % HOOK) + 'if [ "${BWS_ACCESS_TOKEN:-}" = "%s" ]; then echo MATCH; '
        'elif [ -n "${BWS_ACCESS_TOKEN:-}" ]; then echo OTHER; else echo UNSET; fi\n'
        % FAKE
        + 'env | grep -c "^OTHER_SECRET=" || true\n'
    )
    env = {
        "PATH": "/usr/bin:/bin",
        "DEVBOX_WORKSPACE": str(workspace),
        "DEVBOX_BWS_TOKEN_FILE": str(token_file or workspace / "no-such-token-file"),
    }
    if preset is not None:
        env["BWS_ACCESS_TOKEN"] = preset
    argv = [shell] + (["-x"] if xtrace else []) + ["-c", body]
    return subprocess.run(argv, env=env, capture_output=True, text=True, timeout=30, check=False)


@pytest.mark.parametrize("shell", SHELLS)
@pytest.mark.parametrize(
    "line",
    [
        "BWS_ACCESS_TOKEN=%s" % FAKE,
        'BWS_ACCESS_TOKEN="%s"' % FAKE,
        "BWS_ACCESS_TOKEN='%s'" % FAKE,
        "export BWS_ACCESS_TOKEN=%s" % FAKE,
        "BWS_ACCESS_TOKEN=%s\r" % FAKE,
    ],
)
def test_the_hook_exports_the_token_and_nothing_else(tmp_path, shell: str, line: str) -> None:
    ws = write_env(tmp_path, "# comment\nOTHER_SECRET=nope\n%s\nTRAILING=1\n" % line)
    result = run_hook(shell, ws)
    assert result.returncode == 0, result.stderr
    assert result.stdout.split() == ["MATCH", "0"], result.stdout
    assert FAKE not in result.stderr


@pytest.mark.parametrize("shell", SHELLS)
def test_a_last_line_without_a_newline_is_still_read(tmp_path, shell: str) -> None:
    ws = write_env(tmp_path, "OTHER_SECRET=nope\nBWS_ACCESS_TOKEN=%s" % FAKE)
    assert run_hook(shell, ws).stdout.split()[0] == "MATCH"


@pytest.mark.parametrize("shell", SHELLS)
def test_xtrace_never_carries_the_value(tmp_path, shell: str) -> None:
    ws = write_env(tmp_path, "BWS_ACCESS_TOKEN=%s\n" % FAKE)
    body = '. %s\nprintf "%%s" "${#BWS_ACCESS_TOKEN}"\n' % HOOK
    result = subprocess.run(
        [shell, "-x", "-c", body],
        env={
            "PATH": "/usr/bin:/bin",
            "DEVBOX_WORKSPACE": str(ws),
            "DEVBOX_BWS_TOKEN_FILE": str(ws / "absent"),
        },
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    # The length proves the value arrived without putting it on a stream to compare.
    assert result.stdout == str(len(FAKE)), result.stdout
    # The control: the trace is live, so its silence about the value means something.
    assert "+ " in result.stderr
    assert FAKE not in result.stderr


@pytest.mark.parametrize("shell", SHELLS)
def test_a_preset_token_wins(tmp_path, shell: str) -> None:
    ws = write_env(tmp_path, "BWS_ACCESS_TOKEN=%s\n" % FAKE)
    assert run_hook(shell, ws, preset="caller-chosen").stdout.split()[0] == "OTHER"


@pytest.mark.parametrize("shell", SHELLS)
def test_no_file_or_no_line_leaves_it_unset_and_prints_nothing(tmp_path, shell: str) -> None:
    missing = run_hook(shell, tmp_path)
    assert missing.stdout.split()[0] == "UNSET"
    assert missing.stderr == ""
    ws = write_env(tmp_path / "other", "OTHER_SECRET=nope\nBWS_ACCESS_TOKEN=\n")
    empty = run_hook(shell, ws)
    assert empty.stdout.split() == ["UNSET", "0"]
    assert empty.stderr == ""


@pytest.mark.parametrize("shell", SHELLS)
@pytest.mark.parametrize(
    "content", [FAKE, FAKE + "\n", "  %s  \n" % FAKE, FAKE + "\nignored-second-line\n"]
)
def test_the_token_file_is_read_first(tmp_path, shell: str, content: str) -> None:
    token = tmp_path / "bws-access-token"
    token.write_text(content, encoding="utf-8")
    ws = write_env(tmp_path, "BWS_ACCESS_TOKEN=from-the-env-file\n")
    result = run_hook(shell, ws, token_file=token)
    assert result.stdout.split()[0] == "MATCH", result.stdout
    assert result.stderr == ""


@pytest.mark.parametrize("shell", SHELLS)
def test_an_empty_token_file_falls_back_to_the_env_line(tmp_path, shell: str) -> None:
    token = tmp_path / "bws-access-token"
    token.write_text("", encoding="utf-8")
    ws = write_env(tmp_path, "BWS_ACCESS_TOKEN=%s\n" % FAKE)
    assert run_hook(shell, ws, token_file=token).stdout.split()[0] == "MATCH"


def test_the_default_token_path_is_the_read_only_home_bind() -> None:
    hook = HOOK.read_text(encoding="utf-8")
    assert "${DEVBOX_BWS_TOKEN_FILE:-/home/vscode/.config/rediacc-console/bws-access-token}" in hook
    lines = subprocess.run(
        ["bash", "-c", lift("devbox_home_binds") + "\ndevbox_home_binds"],
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    ).stdout.split()
    assert ".config/rediacc-console:ro" in lines
    # Never inside the rdc CLI's own read-write state directory.
    assert "/.config/rediacc/" not in hook


def lift(name: str) -> str:
    source = LIB.read_text(encoding="utf-8")
    match = re.search(r"^%s\(\) \{.*?^\}" % re.escape(name), source, re.MULTILINE | re.DOTALL)
    assert match, "could not lift %s() out of %s; a rename must red here" % (name, LIB)
    return match.group(0)


def script_binds() -> list[tuple[str, str]]:
    result = subprocess.run(
        ["bash", "-c", lift("devbox_script_binds") + "\ndevbox_script_binds"],
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    return [tuple(line.split(":", 1)) for line in result.stdout.splitlines() if line]


def test_the_hook_is_in_the_bind_list_and_every_source_exists() -> None:
    binds = script_binds()
    assert ("devbox-bws.sh", DEST) in binds
    for source, dest in binds:
        assert (paths.from_root(".devcontainer", source)).is_file(), source
        assert dest.startswith("/"), dest
    # profile.d only sources `*.sh`; a destination without the suffix would be bound and never read.
    assert DEST.endswith(".sh")


def test_devbox_up_binds_from_the_list_and_passes_no_token() -> None:
    body = lift("devbox_up")
    assert "done < <(devbox_script_binds)" in body
    assert "devbox_missing_binds" in body
    assert "BWS" not in body, "the token must be read at shell start, never passed to docker run"


def missing(tmp_path, mounts: str, exit_code: int = 0, cid: str = "cid0", home=None) -> list[str]:
    docker = tmp_path / "docker"
    docker.write_text(
        "#!/usr/bin/env bash\ncat <<'OUT'\n%s\nOUT\nexit %d\n" % (mounts, exit_code),
        encoding="utf-8",
    )
    docker.chmod(docker.stat().st_mode | stat.S_IXUSR)
    script = "\n".join(
        (
            "set -euo pipefail",
            "devbox_docker() { printf '%s' \"$FAKE_DOCKER\"; }",
            "devbox_container_id() { printf '%s' \"$CID\"; }",
            'DEVBOX_CONTAINER_HOME="/home/vscode"',
            lift("devbox_script_binds"),
            lift("devbox_home_binds"),
            lift("devbox_missing_binds"),
            "devbox_missing_binds",
        )
    )
    result = subprocess.run(
        ["bash", "-c", script],
        env={
            "PATH": "/usr/bin:/bin",
            "FAKE_DOCKER": str(docker),
            "CID": cid,
            "HOME": str(home or tmp_path / "empty-home"),
        },
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.split()


def test_missing_binds_names_exactly_what_an_old_container_lacks(tmp_path) -> None:
    every = [dest for _, dest in script_binds()]
    old = "\n".join(
        ["/home/developer/console", "/var/run/docker.sock"] + [d for d in every if d != DEST]
    )
    assert missing(tmp_path, old) == [DEST]
    assert missing(tmp_path, old + "\n" + DEST) == []


def test_an_unanswerable_probe_never_asks_for_a_recreate(tmp_path) -> None:
    assert missing(tmp_path, "", exit_code=1) == []
    assert missing(tmp_path, "") == []
    assert missing(tmp_path, "/whatever", cid="") == []


def test_a_home_bind_counts_only_once_its_host_source_exists(tmp_path) -> None:
    every = "\n".join(dest for _, dest in script_binds())
    home = tmp_path / "home"
    home.mkdir()
    assert missing(tmp_path, every, home=home) == []
    (home / ".config" / "rediacc-console").mkdir(parents=True)
    assert missing(tmp_path, every, home=home) == ["/home/vscode/.config/rediacc-console"]
    assert missing(tmp_path, every + "\n/home/vscode/.config/rediacc-console", home=home) == []
