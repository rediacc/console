"""How the devbox gets its Bitwarden Secrets Manager token, driven for real.

Two halves. `.devcontainer/devbox-bws.sh` is the login-shell hook bound to `/etc/profile.d/zz-devbox-bws.sh`: it reads `BWS_ACCESS_TOKEN` from the token-only file `/home/vscode/.config/rediacc/bws-access-token` at shell start. `private/account/.env`, which it once fell back to, is retired (agent/plans/PLAN-account-env-to-bws.md T18), and a test below plants one to prove it is never read. `core.devbox` binds the hook (`devbox_script_binds`) and recreates a container created before the bind existed (`devbox_missing_binds`, read by `devbox_up`), because a bind only ever comes from `docker run`.

The hook is run under BOTH dash and bash: /etc/profile is read by `sh -l` as well, and a bashism would break every such login. The token in every fixture is a fake; the assertions that matter are that the value reaches the environment and that no stream ever carries it, including an xtrace.

The bind-list functions are driven in process through `core.devbox`, the port of the retired `.ci/lib/devbox.sh`.
"""

import inspect
import io
import shutil
import stat
import subprocess

import pytest

from rediacc_ci import paths
from rediacc_ci.core import devbox

HOOK = paths.from_root(".devcontainer", "devbox-bws.sh")
DEST = "/etc/profile.d/zz-devbox-bws.sh"
FAKE = "not-a-real-token-4f2a9c"

SHELLS = [s for s in ("dash", "bash") if shutil.which(s)]


def token(tmp_path, content: str):
    path = tmp_path / "bws-access-token"
    path.write_text(content, encoding="utf-8")
    return path


def run_hook(shell: str, token_file, preset: str | None = None, workspace=None):
    """Source the hook in a fresh shell and report what it exported, by equality only."""
    body = (
        (". %s\n" % HOOK) + 'if [ "${BWS_ACCESS_TOKEN:-}" = "%s" ]; then echo MATCH; '
        'elif [ -n "${BWS_ACCESS_TOKEN:-}" ]; then echo OTHER; else echo UNSET; fi\n' % FAKE
    )
    env = {"PATH": "/usr/bin:/bin", "DEVBOX_BWS_TOKEN_FILE": str(token_file)}
    if workspace is not None:
        env["DEVBOX_WORKSPACE"] = str(workspace)
    if preset is not None:
        env["BWS_ACCESS_TOKEN"] = preset
    return subprocess.run(
        [shell, "-c", body], env=env, capture_output=True, text=True, timeout=30, check=False
    )


@pytest.mark.parametrize("shell", SHELLS)
@pytest.mark.parametrize(
    "content",
    [FAKE, FAKE + "\n", "  %s  \n" % FAKE, FAKE + "\r\n", FAKE + "\nignored-second-line\n"],
)
def test_the_token_file_is_read(tmp_path, shell: str, content: str) -> None:
    result = run_hook(shell, token(tmp_path, content))
    assert result.stdout.split() == ["MATCH"], result.stdout
    assert result.stderr == ""


@pytest.mark.parametrize("shell", SHELLS)
def test_the_retired_env_file_is_never_read(tmp_path, shell: str) -> None:
    """A planted private/account/.env carrying the token must NOT be picked up: the fallback is gone."""
    env_dir = tmp_path / "ws" / "private" / "account"
    env_dir.mkdir(parents=True)
    (env_dir / ".env").write_text("BWS_ACCESS_TOKEN=%s\n" % FAKE, encoding="utf-8")
    result = run_hook(shell, tmp_path / "absent", workspace=tmp_path / "ws")
    assert result.stdout.split() == ["UNSET"]
    assert result.stderr == ""
    empty = run_hook(shell, token(tmp_path, ""), workspace=tmp_path / "ws")
    assert empty.stdout.split() == ["UNSET"], "an EMPTY token file must not fall back either"


@pytest.mark.parametrize("shell", SHELLS)
def test_xtrace_never_carries_the_value(tmp_path, shell: str) -> None:
    body = '. %s\nprintf "%%s" "${#BWS_ACCESS_TOKEN}"\n' % HOOK
    result = subprocess.run(
        [shell, "-x", "-c", body],
        env={"PATH": "/usr/bin:/bin", "DEVBOX_BWS_TOKEN_FILE": str(token(tmp_path, FAKE + "\n"))},
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
    assert run_hook(shell, token(tmp_path, FAKE), preset="caller-chosen").stdout.split() == [
        "OTHER"
    ]


@pytest.mark.parametrize("shell", SHELLS)
def test_no_file_leaves_it_unset_and_prints_nothing(tmp_path, shell: str) -> None:
    missing = run_hook(shell, tmp_path / "absent")
    assert missing.stdout.split() == ["UNSET"]
    assert missing.stderr == ""


def _box(
    env: dict[str, str] | None = None, cid: str | None = None
) -> tuple[devbox.Devbox, io.BytesIO]:
    """A `Devbox` over `env`, its stdout captured. A given `cid` replaces the container lookup, as the lifted-bash version of this file stubbed `devbox_container_id`."""
    out = io.BytesIO()

    class Box(devbox.Devbox):
        def container_id(self, *_argv: str) -> int:
            if cid:
                self.write(cid + "\n")
            return 0

        def core_lease_src(self, *_argv: str) -> int:
            # The lifted-bash harness never defined this function, so no lease mount was ever expected. Pinned off here so the host's own /run/user does not leak in.
            return 0

    box_class = Box if cid is not None else devbox.Devbox
    box = box_class(
        env=env or {"PATH": "/usr/bin:/bin"},
        cwd=str(paths.repo_root()),
        repo_root=str(paths.repo_root()),
        stdout=out,
        stderr=io.BytesIO(),
    )
    return box, out


def test_the_default_token_path_is_the_read_only_home_bind() -> None:
    hook = HOOK.read_text(encoding="utf-8")
    assert "${DEVBOX_BWS_TOKEN_FILE:-/home/vscode/.config/rediacc/bws-access-token}" in hook
    box, out = _box()
    assert box.invoke("devbox_home_binds") == 0
    lines = out.getvalue().decode().split()
    # The FILE is bound read-only, and AFTER the read-write directory bind it sits in, so the
    # rdc CLI's state stays writable while the root credential does not.
    assert ".config/rediacc/bws-access-token:ro" in lines
    assert lines.index(".config/rediacc:") < lines.index(".config/rediacc/bws-access-token:ro")


def script_binds() -> list[tuple[str, ...]]:
    box, out = _box()
    assert box.invoke("devbox_script_binds") == 0
    return [tuple(line.split(":", 1)) for line in out.getvalue().decode().splitlines() if line]


def test_the_hook_is_in_the_bind_list_and_every_source_exists() -> None:
    binds = script_binds()
    assert ("devbox-bws.sh", DEST) in binds
    for source, dest in binds:
        assert (paths.from_root(".devcontainer", source)).is_file(), source
        assert dest.startswith("/"), dest
    # profile.d only sources `*.sh`; a destination without the suffix would be bound and never read.
    assert DEST.endswith(".sh")


def test_devbox_up_binds_from_the_list_and_passes_no_token() -> None:
    body = inspect.getsource(devbox.Devbox.up)
    assert "for pair in SCRIPT_BINDS" in body
    assert "missing_binds" in body
    assert "BWS" not in body, "the token must be read at shell start, never passed to docker run"


def missing(tmp_path, mounts: str, exit_code: int = 0, cid: str = "cid0", home=None) -> list[str]:
    docker = tmp_path / "docker"
    docker.write_text(
        "#!/usr/bin/env bash\ncat <<'OUT'\n%s\nOUT\nexit %d\n" % (mounts, exit_code),
        encoding="utf-8",
    )
    docker.chmod(docker.stat().st_mode | stat.S_IXUSR)
    box, out = _box(
        {
            "PATH": "/usr/bin:/bin",
            devbox.DOCKER_MEMO: str(docker),
            "HOME": str(home or tmp_path / "empty-home"),
        },
        cid=cid,
    )
    assert box.invoke("devbox_missing_binds") == 0
    return out.getvalue().decode().split()


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
    (home / ".config" / "rediacc").mkdir(parents=True)
    (home / ".config" / "rediacc" / "bws-access-token").write_text("x\n", encoding="utf-8")
    assert missing(tmp_path, every, home=home) == [
        "/home/vscode/.config/rediacc",
        "/home/vscode/.config/rediacc/bws-access-token",
    ]
    bind_dest = "/home/vscode/.config/rediacc/bws-access-token"
    both = every + "\n/home/vscode/.config/rediacc\n" + bind_dest
    assert missing(tmp_path, both, home=home) == []
