"""`lab.airgap` over a recorded ssh transport (no live VM) and `lab.testca` with the local openssl (PLAN-enterprise-tenants box C12).

Each failing check has a CONTROL that runs the same scenario with the one fault removed.
"""

from __future__ import annotations

import os
import shlex
import subprocess

import pytest

from rediacc_ci.lab import airgap, testca

GOOD = "\n".join(
    [
        airgap.SSH_MARK,
        *["PROBE %s blocked" % h for h in airgap.HOSTS],
        "PROBE dns:1.1.1.1 blocked",
        "Chain OUTPUT (policy DROP 42 packets, 3360 bytes)",
    ]
)


class Recorder:
    def __init__(self, rc: int = 0, out: str = "") -> None:
        self.calls: list[list[str]] = []
        self.rc, self.out = rc, out

    def __call__(self, argv):
        self.calls.append(list(argv))
        return self.rc, self.out


def test_apply_rules_text():
    script = airgap.apply_script()
    for tool in airgap.TOOLS:
        assert "%s -P OUTPUT DROP" % tool in script
        assert "%s -I OUTPUT 1 -o lo " % tool in script
        assert "%s -I OUTPUT 1 -m conntrack --ctstate ESTABLISHED,RELATED" % tool in script
        assert "%s -I DOCKER-USER 2 -m comment --comment rediacc-airgap -j DROP" % tool in script
    assert "persist" not in script
    assert "-P OUTPUT ACCEPT" in airgap.remove_script()


def test_apply_runs_one_ssh_to_the_vm():
    rec = Recorder()
    assert airgap.main(["apply", "--vm", "192.168.111.12"], rec) == 0
    argv = rec.calls[0]
    assert argv[0] == "ssh"
    assert any(a.endswith("@192.168.111.12") for a in argv)
    assert "-P OUTPUT DROP" in argv[-1]


@pytest.mark.parametrize(
    "ip",
    [
        "10.0.0.5",
        "192.168.112.11",
        "192.168.111.11.example.com",
        "::1",
        "example.com",
        "192.168.111.300",
        "192.168.111.254",
        "192.168.111.0",
        "192.168.111.255",
    ],
)
def test_refuses_non_ops_ip(ip):
    rec = Recorder()
    for verb in ("apply", "remove", "check"):
        assert airgap.main([verb, "--vm", ip], rec) == 2
    assert rec.calls == []


def test_remove_goes_through_the_transport_as_the_remove_script():
    """Review bf0bded8.4: `remove` is sent over ssh, not just present as text."""
    rec = Recorder()
    assert airgap.main(["remove", "--vm", "192.168.111.12"], rec) == 0
    assert rec.calls[0][-1].endswith(shlex.quote(airgap.remove_script()))
    assert airgap.main(["remove", "--vm", "192.168.111.12"], Recorder(1, "boom")) == 1


def _fake_iptables(tmp_path):
    log = tmp_path / "log"
    for tool in airgap.TOOLS:
        path = tmp_path / tool
        path.write_text(
            "#!/bin/sh\n"
            'echo "%s $*" >> %s\n'
            'if [ "$1" = "-S" ]; then\n'
            '  echo "-A $2 -o lo -m comment --comment %s -j ACCEPT"\n'
            '  echo "-A $2 -s 10.9.9.9 -j DROP"\n'
            "fi\n" % (tool, log, airgap.TAG)
        )
        path.chmod(0o755)
    return log


def test_remove_script_deletes_the_tagged_rules_and_no_others(tmp_path, monkeypatch):
    """Review bf0bded8.4: run the script against a fake iptables that holds one tagged and one foreign rule."""
    log = _fake_iptables(tmp_path)
    # The fake leads a fixed system path, so the test writes PATH and never reads the host's.
    monkeypatch.setenv("PATH", "%s:%s" % (tmp_path, os.defpath))
    subprocess.run(["sh", "-c", airgap.remove_script()], check=True)
    lines = log.read_text().splitlines()
    for tool in airgap.TOOLS:
        assert "%s -P OUTPUT ACCEPT" % tool in lines
        for chain in ("OUTPUT", "DOCKER-USER"):
            assert (
                "%s -D %s -o lo -m comment --comment %s -j ACCEPT" % (tool, chain, airgap.TAG)
                in lines
            )
    assert not any("10.9.9.9" in line and " -D " in line for line in lines)


def test_usage():
    assert airgap.main(["apply"], Recorder()) == 2


def test_check_passes_when_every_probe_fails(capsys):
    assert airgap.main(["check", "--vm", "192.168.111.11"], Recorder(0, GOOD)) == 0
    assert "dropped 42 packets" in capsys.readouterr().out


@pytest.mark.parametrize("host", [*airgap.HOSTS, "dns:1.1.1.1"])
def test_check_fails_when_a_probe_succeeds(host):
    out = GOOD.replace("PROBE %s blocked" % host, "PROBE %s reached" % host)
    assert out != GOOD
    assert airgap.main(["check", "--vm", "192.168.111.11"], Recorder(0, out)) == 1


def test_check_fails_when_ssh_does_not_answer():
    assert airgap.main(["check", "--vm", "192.168.111.11"], Recorder(255, "")) == 1
    assert (
        airgap.main(["check", "--vm", "192.168.111.11"], Recorder(0, "PROBE ghcr.io blocked")) == 1
    )


def test_check_fails_when_policy_is_not_drop():
    out = GOOD.replace("policy DROP", "policy ACCEPT")
    assert airgap.main(["check", "--vm", "192.168.111.11"], Recorder(0, out)) == 1


def san_of(crt) -> str:
    cmd = ["openssl", "x509", "-in", str(crt), "-noout", "-ext", "subjectAltName"]
    text = subprocess.run(cmd, capture_output=True, text=True, check=True).stdout
    return text.split("\n", 1)[1].strip()


def test_testca_san_is_exactly_the_host(tmp_path):
    assert testca.main([str(tmp_path), "elite-lab.ops.test", "192.168.111.12"]) == 0
    assert (tmp_path / "ca.crt").exists()
    assert (tmp_path / "elite-lab.ops.test.key").exists()
    assert san_of(tmp_path / "elite-lab.ops.test.crt") == "DNS:elite-lab.ops.test"
    assert san_of(tmp_path / "192.168.111.12.crt") == "IP Address:192.168.111.12"
    cmd = [
        "openssl",
        "verify",
        "-CAfile",
        str(tmp_path / "ca.crt"),
        str(tmp_path / "elite-lab.ops.test.crt"),
    ]
    assert subprocess.run(cmd, capture_output=True, check=False).returncode == 0


def test_testca_refuses_wildcard(tmp_path):
    assert testca.main([str(tmp_path), "*.ops.test"]) == 2
    assert not (tmp_path / "ca.crt").exists()


def test_a_vm_address_next_to_the_gateway_is_accepted():
    """Control for the gateway refusal: .253 and .1 are VM addresses."""
    assert airgap.is_ops_vm_ip("192.168.111.253")
    assert airgap.is_ops_vm_ip("192.168.111.1")
    assert not airgap.is_ops_vm_ip("192.168.111.254")


def test_testca_refuses_a_path_separator_in_a_host(tmp_path):
    """bf0bded8.2: a host never reaches the output path with a slash in it."""
    assert testca.main([str(tmp_path / "out"), "a/../x"]) == 2
    assert not (tmp_path / "out").exists()
    assert not (tmp_path / "x.key").exists()


def test_testca_openssl_failure_exits_1(tmp_path, monkeypatch, capsys):
    """bf0bded8.3: a failing openssl is exit 1 with a message, and a missing binary the same."""

    def fail(*_a, **_k):
        raise subprocess.CalledProcessError(1, ["openssl"])

    monkeypatch.setattr(testca.subprocess, "run", fail)
    assert testca.main([str(tmp_path), "h.test"]) == 1
    assert "openssl failed" in capsys.readouterr().err

    def missing(*_a, **_k):
        raise FileNotFoundError("openssl")

    monkeypatch.setattr(testca.subprocess, "run", missing)
    assert testca.main([str(tmp_path), "h.test"]) == 1
