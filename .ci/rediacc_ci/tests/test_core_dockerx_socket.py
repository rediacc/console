"""`rediacc_ci.core.dockerx.socket_defect` against a planted /proc and a real AF_UNIX listener.

Measured 2026-11-10: Docker Desktop's WSL proxy bound the docker socket path and every docker call hung. The detector reads `/proc/net/unix` and the owners' fds, then pings. Each firing case has a control: a no-op detector is planted and the same assertion must fail, which shows the case is judged by the detector and not by the fixture.
"""

import os
import pathlib
import socket
import threading

import pytest

from rediacc_ci.core import dockerx

HEADER = "Num       RefCount Protocol Flags    Type St Inode Path\n"
LISTEN = "00010000"


def _row(inode: str, path: str, *, flags: str = LISTEN, state: str = "01") -> str:
    return "0000000000000000: 00000002 00000000 %s 0001 %s %s %s\n" % (flags, state, inode, path)


class Responder:
    """A real unix listener: `answer` is bytes to send back, or None to accept and never answer."""

    def __init__(self, path: pathlib.Path, answer: bytes | None) -> None:
        self.path = str(path)
        self.answer = answer
        self.server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.server.bind(self.path)
        self.server.listen(4)
        self.held: list[socket.socket] = []
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.thread.start()

    def _serve(self) -> None:
        while True:
            try:
                conn, _ = self.server.accept()
            except OSError:
                return
            if self.answer is None:
                self.held.append(conn)
                continue
            conn.recv(1024)
            conn.sendall(self.answer)
            conn.close()

    def close(self) -> None:
        self.server.close()
        for conn in self.held:
            conn.close()


OK_ANSWER = b"HTTP/1.0 200 OK\r\n\r\nOK"


def _proc(root: pathlib.Path, owners: dict[str, str]) -> str:
    """A fake /proc with one pid per (inode -> comm)."""
    for index, (inode, comm) in enumerate(owners.items(), start=100):
        pid = root / str(index)
        (pid / "fd").mkdir(parents=True)
        os.symlink("socket:[%s]" % inode, pid / "fd" / "3")
        (pid / "comm").write_text(comm + "\n")
    return str(root)


def _net(tmp: pathlib.Path, path: str, inodes: list[str]) -> str:
    target = os.path.realpath(path)
    net = tmp / "net_unix"
    net.write_text(HEADER + "".join(_row(inode, target) for inode in inodes))
    return str(net)


@pytest.fixture
def sock_dir(tmp_path: pathlib.Path) -> pathlib.Path:
    # AF_UNIX paths are short-limited; tmp_path is short enough under pytest.
    return tmp_path


def _fire_foreign_owner(tmp: pathlib.Path, detector) -> str | None:
    # The 2026-11-10 incident: the socket hung while a foreign or second listener held the path.
    responder = Responder(tmp / "d.sock", None)
    try:
        proc_root = _proc(tmp / "proc", {"5001": "docker-desktop-"})
        return detector(
            responder.path,
            ping_timeout=0.3,
            net_unix=_net(tmp, responder.path, ["5001"]),
            proc_root=proc_root,
        )
    finally:
        responder.close()


def _fire_two_listeners(tmp: pathlib.Path, detector) -> str | None:
    # The 2026-11-10 incident: the socket hung while a foreign or second listener held the path.
    responder = Responder(tmp / "d.sock", None)
    try:
        proc_root = _proc(tmp / "proc", {"5001": "dockerd", "5002": "dockerd"})
        return detector(
            responder.path,
            ping_timeout=0.3,
            net_unix=_net(tmp, responder.path, ["5001", "5002"]),
            proc_root=proc_root,
        )
    finally:
        responder.close()


def _fire_silent_listener(tmp: pathlib.Path, detector) -> str | None:
    responder = Responder(tmp / "d.sock", None)
    try:
        proc_root = _proc(tmp / "proc", {"5001": "dockerd"})
        return detector(
            responder.path,
            ping_timeout=0.3,
            net_unix=_net(tmp, responder.path, ["5001"]),
            proc_root=proc_root,
        )
    finally:
        responder.close()


def _noop(*_args: object, **_kwargs: object) -> None:
    return None


FIRING = [_fire_foreign_owner, _fire_two_listeners, _fire_silent_listener]


@pytest.mark.parametrize("case", FIRING)
def test_fires(case, sock_dir: pathlib.Path) -> None:
    message = case(sock_dir, dockerx.socket_defect)
    assert message is not None
    assert (
        "sudo systemctl stop docker docker.socket; sudo rm -f /run/docker.sock; sudo systemctl start docker.socket docker"
        in message
    )
    assert "systemctl restart docker` alone does not fix it" in message


@pytest.mark.parametrize("case", FIRING)
def test_control_noop_detector_goes_silent(case, sock_dir: pathlib.Path) -> None:
    with pytest.raises(AssertionError):
        _assert_fires(case, sock_dir, _noop)


def _assert_fires(case, tmp: pathlib.Path, detector) -> None:
    assert case(tmp, detector) is not None


def test_names_the_foreign_owner(sock_dir: pathlib.Path) -> None:
    assert "docker-desktop-" in (_fire_foreign_owner(sock_dir, dockerx.socket_defect) or "")


def test_silent_on_clean_host(sock_dir: pathlib.Path) -> None:
    responder = Responder(sock_dir / "d.sock", OK_ANSWER)
    try:
        proc_root = _proc(sock_dir / "proc", {"5001": "dockerd", "5002": "systemd"})
        net = _net(sock_dir, responder.path, ["5001"])
        assert (
            dockerx.socket_defect(
                responder.path, ping_timeout=1.0, net_unix=net, proc_root=proc_root
            )
            is None
        )
    finally:
        responder.close()


def test_silent_on_missing_path(sock_dir: pathlib.Path) -> None:
    assert (
        dockerx.socket_defect(str(sock_dir / "absent.sock"), net_unix=str(sock_dir / "nope"))
        is None
    )


def test_eacces_on_fds_lets_the_ping_decide(sock_dir: pathlib.Path) -> None:
    if os.geteuid() == 0:
        pytest.skip("root reads every fd directory")
    responder = Responder(sock_dir / "d.sock", OK_ANSWER)
    try:
        proc_root = _proc(sock_dir / "proc", {"5001": "docker-desktop-"})
        os.chmod(os.path.join(proc_root, "100", "fd"), 0)
        net = _net(sock_dir, responder.path, ["5001"])
        try:
            assert (
                dockerx.socket_defect(
                    responder.path, ping_timeout=1.0, net_unix=net, proc_root=proc_root
                )
                is None
            )
        finally:
            os.chmod(os.path.join(proc_root, "100", "fd"), 0o700)
    finally:
        responder.close()


def test_eacces_with_a_hung_ping_names_ss(sock_dir: pathlib.Path) -> None:
    if os.geteuid() == 0:
        pytest.skip("root reads every fd directory")
    responder = Responder(sock_dir / "d.sock", None)
    try:
        proc_root = _proc(sock_dir / "proc", {"5001": "dockerd"})
        os.chmod(os.path.join(proc_root, "100", "fd"), 0)
        net = _net(sock_dir, responder.path, ["5001"])
        try:
            message = dockerx.socket_defect(
                responder.path, ping_timeout=0.3, net_unix=net, proc_root=proc_root
            )
        finally:
            os.chmod(os.path.join(proc_root, "100", "fd"), 0o700)
        assert message is not None
        assert "sudo ss -xlpn | grep docker.sock" in message
    finally:
        responder.close()


def test_socket_check_verb_maps_defect_to_77(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dockerx, "socket_defect", lambda: "boom")
    assert dockerx.main(["socket-check"]) == dockerx.CANNOT_RUN_RC
    monkeypatch.setattr(dockerx, "socket_defect", lambda: None)
    assert dockerx.main(["socket-check"]) == 0


def test_cannot_run_reason_appends_the_defect(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DOCKER_HOST", raising=False)
    monkeypatch.setattr(dockerx, "state", lambda *_a, **_k: dockerx.STATE_UNREACHABLE)
    monkeypatch.setattr(dockerx, "socket_defect", lambda *_a, **_k: "FOREIGN-LISTENER")
    reason = dockerx.cannot_run_reason()
    assert reason is not None
    assert "FOREIGN-LISTENER" in reason
    with pytest.raises(dockerx.DockerUnreachableError) as excinfo:
        dockerx.require_ready()
    assert "FOREIGN-LISTENER" in excinfo.value.stderr


@pytest.mark.parametrize(
    ("env", "host"),
    [
        ({"DOCKER_HOST": "tcp://10.0.0.1:2375"}, None),
        ({}, "unix:///var/run/rediacc/net-7/docker-7.sock"),
        ({"DOCKER_HOST": "ssh://box"}, None),
    ],
)
def test_the_hint_judges_only_the_host_engine_socket(
    env, host, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The re-bind names the systemd docker.socket, so a tcp, ssh or repo daemon is never judged by it.
    monkeypatch.setattr(dockerx, "state", lambda *_a, **_k: dockerx.STATE_UNREACHABLE)
    monkeypatch.setattr(dockerx, "socket_defect", lambda *_a, **_k: "FOREIGN-LISTENER")
    reason = dockerx.cannot_run_reason(env, host=host)
    assert reason is not None
    assert "FOREIGN-LISTENER" not in reason


def test_a_full_backlog_counts_as_no_answer(
    monkeypatch: pytest.MonkeyPatch, sock_dir: pathlib.Path
) -> None:
    path = sock_dir / "d.sock"
    path.touch()

    class Full:
        def __init__(self, *_a: object) -> None:
            pass

        def settimeout(self, _t: float) -> None:
            pass

        def connect(self, _p: str) -> None:
            raise BlockingIOError(11, "Resource temporarily unavailable")

        def close(self) -> None:
            pass

    monkeypatch.setattr(dockerx.socket, "socket", Full)
    assert dockerx._ping_answers(str(path), 0.3) is False


def test_an_unread_comm_leaves_the_ping_to_decide(sock_dir: pathlib.Path) -> None:
    proc_root = sock_dir / "proc"
    (proc_root / "100" / "fd").mkdir(parents=True)
    os.symlink("socket:[5001]", proc_root / "100" / "fd" / "3")
    owners, unreadable = dockerx._inode_owners(["5001"], str(proc_root))
    assert owners["5001"] == set()
    assert unreadable


def test_answering_engine_beside_a_leftover_listener_is_clean(sock_dir: pathlib.Path) -> None:
    # After the re-bind the proxy's row stays in /proc/net/unix while dockerd answers; docker works, so no defect.
    responder = Responder(sock_dir / "d.sock", OK_ANSWER)
    try:
        proc_root = _proc(sock_dir / "proc", {"5001": "dockerd", "5002": "docker-desktop-"})
        verdict = dockerx.socket_defect(
            responder.path,
            ping_timeout=1.0,
            net_unix=_net(sock_dir, responder.path, ["5001", "5002"]),
            proc_root=proc_root,
        )
    finally:
        responder.close()
    assert verdict is None


def test_a_row_spelled_through_a_symlinked_directory_counts(sock_dir: pathlib.Path) -> None:
    # /var/run is a symlink to /run: the proxy's row named /var/run/docker.sock while dockerd's named /run/docker.sock.
    real = sock_dir / "run"
    real.mkdir()
    alias = sock_dir / "varrun"
    alias.symlink_to(real)
    responder = Responder(real / "d.sock", None)
    try:
        proc_root = _proc(sock_dir / "proc", {"5001": "docker-desktop-"})
        verdict = dockerx.socket_defect(
            responder.path,
            ping_timeout=0.3,
            net_unix=_net(sock_dir, str(alias / "d.sock"), ["5001"]),
            proc_root=proc_root,
        )
    finally:
        responder.close()
    assert verdict is not None
    assert "docker-desktop-" in verdict
