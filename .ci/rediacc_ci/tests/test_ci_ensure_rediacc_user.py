"""ensure_rediacc_user refuses an existing `rediacc` user whose uid or gid is not 7111 (review finding 79b343e9.1)."""

import subprocess

from rediacc_ci.ci import ensure_rediacc_user as eru


def _fake(uid: str, gid: str):
    def out(*argv: str) -> subprocess.CompletedProcess[str]:
        text = {"-u": uid, "-g": gid}.get(argv[1], "uid=%s gid=%s" % (uid, gid))
        return subprocess.CompletedProcess(argv, 0, stdout=text + "\n", stderr="")

    return out


def test_a_user_with_another_uid_is_refused(monkeypatch, capsys):
    monkeypatch.setattr(eru, "_out", _fake("1001", eru.ID))
    assert eru.main() == 1
    assert "not uid/gid" in capsys.readouterr().out


def test_a_user_with_another_gid_is_refused(monkeypatch):
    monkeypatch.setattr(eru, "_out", _fake(eru.ID, "1001"))
    assert eru.main() == 1


def test_a_user_with_the_expected_ids_passes(monkeypatch, capsys):
    """Control: the same flow with the one fault removed exits 0."""
    monkeypatch.setattr(eru, "_out", _fake(eru.ID, eru.ID))
    assert eru.main() == 0
    assert "uid=%s" % eru.ID in capsys.readouterr().out
