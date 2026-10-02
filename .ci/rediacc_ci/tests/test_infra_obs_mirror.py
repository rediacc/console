"""`rediacc_ci.infra.obs_mirror`: capture, fetch and verification of the openSUSE Leap 16.0 OBS Ceph mirror.

Nothing here touches OBS, a registry or Docker: the network is a dict, the registry and the containers are fakes. The signature cases run the real gpg and gpgv over a throwaway key made in a temporary home. The verdicts that carry the design (plan section 6), each with its control:

  * repomd parses and lists its hrefs; a checksum mismatch raises, the correct checksum passes;
  * gpgv refuses a one-byte-tampered repomd.xml, and verifies the untampered one;
  * the fingerprint assertion refuses a key that is not the one named, and passes the real OBS key for cephpkg.go's fingerprint;
  * the package-set intersection keeps only this repository's (name, EVR, arch) rows, never a Leap OSS package;
  * capture on an existing tag pushes nothing, while a miss pushes once and reads the tag back;
  * an EVR absent from primary is refused before anything is derived or pushed.
"""

from __future__ import annotations

import gzip
import hashlib
import io
import json
import os
import pathlib
import shutil
import signal
import socket
import subprocess
import tarfile
from typing import Any

import pytest

from rediacc_ci.infra import obs_mirror as om
from rediacc_ci.well_known import IMAGE_REGISTRY

EVR = "19.2.3-lp160.2.98"
OLD = "19.2.3-lp160.2.94"
ORIGIN = om.OBS_ORIGIN

needs_gpg = pytest.mark.skipif(
    shutil.which("gpg") is None or shutil.which("gpgv") is None,
    reason="gpg and gpgv are not installed",
)


# --- fixtures -----------------------------------------------------------------------------


def _pkg_xml(name: str, arch: str, evr: str, body: bytes) -> str:
    ver, rel = evr.split("-", 1)
    href = "%s/%s-%s.%s.rpm" % (arch, name, evr, arch)
    return (
        '<package type="rpm"><name>%s</name><arch>%s</arch>'
        '<version epoch="0" ver="%s" rel="%s"/>'
        '<checksum type="sha512" pkgid="YES">%s</checksum>'
        '<size package="%d" installed="1" archive="1"/>'
        '<location href="%s"/></package>'
    ) % (name, arch, ver, rel, hashlib.sha512(body).hexdigest(), len(body), href)


def rpm_body(name: str, arch: str, evr: str) -> bytes:
    return ("rpm %s %s %s" % (name, arch, evr)).encode()


PACKAGES = [
    ("ceph-common", "x86_64", EVR),
    ("cephadm", "noarch", EVR),
    ("cephadm", "noarch", OLD),
    ("librados2", "x86_64", EVR),
    ("ceph-common", "aarch64", OLD),
]


def primary_xml(packages: list[tuple[str, str, str]] = PACKAGES) -> bytes:
    body = "".join(_pkg_xml(n, a, e, rpm_body(n, a, e)) for n, a, e in packages)
    return (
        '<?xml version="1.0"?><metadata xmlns="http://linux.duke.edu/metadata/common" '
        'packages="%d">%s</metadata>' % (len(packages), body)
    ).encode()


def repomd_xml(files: dict[str, bytes], revision: str = "1790751035") -> bytes:
    data = "".join(
        '<data type="%s"><checksum type="sha512">%s</checksum><location href="%s"/><size>%d</size></data>'
        % (kind, hashlib.sha512(body).hexdigest(), href, len(body))
        for kind, (href, body) in (
            (k, (h, files[h])) for k, h in (("primary", PRIMARY_HREF), ("other", OTHER_HREF))
        )
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?><repomd xmlns="http://linux.duke.edu/metadata/repo">'
        "<revision>%s</revision>%s</repomd>" % (revision, data)
    ).encode()


PRIMARY_HREF = "repodata/abc-primary.xml.gz"
OTHER_HREF = "repodata/def-other.xml.gz"


def origin_files(packages: list[tuple[str, str, str]] = PACKAGES) -> dict[str, bytes]:
    files = {
        PRIMARY_HREF: gzip.compress(primary_xml(packages)),
        OTHER_HREF: gzip.compress(b"<other/>"),
    }
    files["repodata/repomd.xml"] = repomd_xml(files)
    files["repodata/repomd.xml.asc"] = b"sig"
    files["repodata/repomd.xml.key"] = b"key"
    for n, a, e in packages:
        files["%s/%s-%s.%s.rpm" % (a, n, e, a)] = rpm_body(n, a, e)
    return files


class Net:
    """A fake OBS: path -> bytes, recording every URL asked for."""

    def __init__(self, files: dict[str, bytes]) -> None:
        self.files = files
        self.asked: list[str] = []

    def __call__(self, url: str) -> bytes:
        self.asked.append(url)
        assert url.startswith(ORIGIN), url
        return self.files[url[len(ORIGIN) :]]


class FakeRun:
    """Answers gpg as a pass, oras from a queue, and records every argv."""

    def __init__(self, oras: list[tuple[int, str, str]] | None = None) -> None:
        self.oras = list(oras or [])
        self.calls: list[list[str]] = []

    def __call__(self, argv: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        self.calls.append(list(argv))
        if argv[0] == "gpg" and "--show-keys" in argv:
            return subprocess.CompletedProcess(argv, 0, "pub:u:4096\nfpr:::::::::%s:\n" % FPR, "")
        if argv[0] == "gpg":
            return subprocess.CompletedProcess(argv, 0, "", "")
        if argv[0] == "gpgv":
            return subprocess.CompletedProcess(argv, 0, "[GNUPG:] VALIDSIG x y z %s\n" % FPR, "")
        rc, out, err = self.oras.pop(0)
        return subprocess.CompletedProcess(argv, rc, out, err)

    def oras_calls(self, verb: str) -> list[list[str]]:
        return [c for c in self.calls if c[:2] == ["oras", verb]]


FPR = "B1FB53748720472205FA601998C97FE7324E6311"


def _ctx(tmp_path: pathlib.Path) -> om.Ctx:
    key = tmp_path / "obs.key"
    key.write_bytes(b"key")
    return om.Ctx(
        key=key,
        rid="rediacc-ceph-squid",
        key_path="/etc/pki/rpm-gpg/k",
        evr=EVR,
        extras=("sshpass",),
    )


def _installed() -> list[tuple[str, str, str]]:
    # librados2 from this repository; sshpass and an OSS reef ceph-common at a different EVR never match.
    return [
        ("ceph-common", EVR, "x86_64"),
        ("cephadm", EVR, "noarch"),
        ("librados2", EVR, "x86_64"),
        ("sshpass", "1.10-1.1", "x86_64"),
        ("ceph-common", "18.2.7-lp160.1.1", "x86_64"),
    ]


def _deps(net: Net, run: FakeRun, checks_ok: bool = True) -> om.Deps:
    return om.Deps(
        get=net,
        run=run,
        derive=lambda _c, _s: _installed(),
        checks=lambda _c, _s, _p: [om.Verdict("POSITIVE", checks_ok, "fake")],
    )


# --- repomd, checksums, primary --------------------------------------------------------------


def test_repomd_parses_and_lists_its_hrefs() -> None:
    md = om.parse_repomd(origin_files()["repodata/repomd.xml"])
    assert md.revision == "1790751035"
    assert [d.href for d in md.data] == [PRIMARY_HREF, OTHER_HREF]
    assert md.get("primary").checksum_type == "sha512"


def test_repomd_refuses_an_href_that_escapes_the_tree() -> None:
    bad = origin_files()["repodata/repomd.xml"].replace(PRIMARY_HREF.encode(), b"../../etc/passwd")
    with pytest.raises(om.MirrorError, match="unsafe path"):
        om.parse_repomd(bad)


def test_a_checksum_mismatch_raises_and_the_correct_checksum_passes() -> None:
    data = b"primary bytes"
    good = hashlib.sha512(data).hexdigest()
    om.verify_checksum("primary", data, "sha512", good, len(data))  # control
    with pytest.raises(om.ChecksumMismatchError):
        om.verify_checksum("primary", data + b"!", "sha512", good)
    with pytest.raises(om.ChecksumMismatchError, match="bytes"):
        om.verify_checksum("primary", data, "sha512", good, len(data) + 1)


def test_fetch_metadata_retries_a_mid_publish_mismatch_from_a_fresh_repomd(
    tmp_path: pathlib.Path,
) -> None:
    files = origin_files()
    rounds: list[str] = []

    def get(url: str) -> bytes:
        rel = url[len(ORIGIN) :]
        if rel == "repodata/repomd.xml":
            rounds.append(rel)
        if rel == PRIMARY_HREF and len(rounds) == 1:
            return b"the primary OBS was halfway through replacing"
        return files[rel]

    md = om.fetch_metadata(ORIGIN, _ctx(tmp_path).key, FPR, get, FakeRun())
    assert len(rounds) == 2
    assert {p.name for p in md.packages} == {"ceph-common", "cephadm", "librados2"}


def test_fetch_metadata_gives_up_after_the_attempts(tmp_path: pathlib.Path) -> None:
    files = origin_files()
    files[PRIMARY_HREF] = b"not what repomd says"
    with pytest.raises(om.MirrorError, match="never settled after 3"):
        om.fetch_metadata(ORIGIN, _ctx(tmp_path).key, FPR, Net(files), FakeRun())


def test_newest_evr_and_an_absent_evr_is_refused() -> None:
    packages = om.parse_primary(primary_xml())
    assert (
        om.newest_evr(packages, "ceph-common") == EVR
    )  # aarch64's 2.94 is not an arch renet takes
    assert len(om.pinned_packages(packages, EVR)) == 2
    with pytest.raises(om.MirrorError, match="does not list ceph-common"):
        om.pinned_packages(packages, OLD)  # cephadm 2.94 is listed, ceph-common 2.94 x86_64 is not


@pytest.mark.parametrize(
    ("a", "b", "want"),
    [
        ("2.97", "2.96", 1),
        ("2.100", "2.99", 1),
        ("lp160.2.98", "lp160.2.98", 0),
        ("1.0~rc1", "1.0", -1),
        ("1.a", "1.1", -1),
    ],
)
def test_rpmvercmp(a: str, b: str, want: int) -> None:
    assert om.rpmvercmp(a, b) == want
    assert om.rpmvercmp(b, a) == -want


def test_the_intersection_excludes_leap_oss_packages() -> None:
    packages = om.parse_primary(primary_xml())
    got = om.intersect(_installed(), packages)
    assert [p.nevra for p in got] == [
        "cephadm-%s.noarch" % EVR,
        "ceph-common-%s.x86_64" % EVR,
        "librados2-%s.x86_64" % EVR,
    ]
    # Control: the same name at this repository's EVR does match.
    assert (
        om.intersect([("ceph-common", OLD, "aarch64")], packages) == []
    )  # not an arch renet takes
    assert om.intersect([("cephadm", OLD, "noarch")], packages)[0].evr == OLD


def test_parse_rpm_qa_spells_no_epoch_as_none() -> None:
    rows = om.parse_rpm_qa(
        "ceph-common (none) 19.2.3 lp160.2.98 x86_64\nfoo 2 1.0 3 noarch\nshort line\n"
    )
    assert rows == [("ceph-common", EVR, "x86_64"), ("foo", "2:1.0-3", "noarch")]


# --- renet's sources ------------------------------------------------------------------


def test_the_repo_directives_are_the_ones_cephpkg_writes() -> None:
    go = om.CEPHPKG_GO.read_text(encoding="utf-8")
    for line in om.repo_directives("KEY"):
        if line.startswith("gpgkey="):
            assert '"gpgkey=file://" + obsKeyPath' in go
            continue
        assert '"%s\\n"' % line in go, line
    assert om.repo_id(go) == "rediacc-ceph-squid"
    assert om.obs_fingerprint(go) == FPR


def test_the_zypper_names_come_from_pkgset() -> None:
    names = om.zypper_names(om.PKGSET_GO.read_text(encoding="utf-8"))
    assert names[:2] == ["ceph-common", "cephadm"]
    assert {"sshpass", "btrfsprogs", "lvm2", "sqlite3"} <= set(names)
    with pytest.raises(om.MirrorError):
        om.zypper_names("var Other = Set{\n}\n")


def test_the_profiles_come_from_ceph_install() -> None:
    profiles = om.ceph_profiles(om.CEPH_INSTALL_GO.read_text(encoding="utf-8"))
    assert {"admin", "node", "client", "fork-dest"} <= set(profiles)


def test_image_ref_refuses_what_a_tag_cannot_carry() -> None:
    assert om.image_ref(EVR) == (IMAGE_REGISTRY + "/ci-vm-bake:obs-mirror-v1-opensuse-16.0-") + EVR
    for bad in ("2:19.2.3-1.el10s", "19.2.3", "19.2.3-1+git", "latest"):
        with pytest.raises(om.MirrorError):
            om.image_ref(bad)


def test_read_pin() -> None:
    assert om.read_pin("host.el10=2:x\nhost.opensuse-16.0=%s\n" % EVR) == EVR
    with pytest.raises(om.MirrorError):
        om.read_pin("host.el10=2:x\n")


# --- gpg, for real -----------------------------------------------------------------------------


@pytest.fixture(scope="module")
def signer(tmp_path_factory: pytest.TempPathFactory) -> tuple[pathlib.Path, pathlib.Path, str]:
    """(home, exported public key, fingerprint) of a throwaway signing key."""
    if shutil.which("gpg") is None:
        pytest.skip("gpg is not installed")
    home = tmp_path_factory.mktemp("gnupg")
    home.chmod(0o700)
    base = [
        "gpg",
        "--homedir",
        str(home),
        "--batch",
        "--pinentry-mode",
        "loopback",
        "--passphrase",
        "",
    ]
    subprocess.run(
        [*base, "--quick-gen-key", "obs-mirror-test", "ed25519", "sign", "never"],
        check=True,
        capture_output=True,
    )
    out = subprocess.run(
        [*base, "--with-colons", "--list-keys"], check=True, capture_output=True, text=True
    ).stdout
    fpr = next(ln.split(":")[9] for ln in out.splitlines() if ln.startswith("fpr:"))
    key = home / "pub.asc"
    subprocess.run(
        [*base, "--armor", "--export", "-o", str(key), fpr], check=True, capture_output=True
    )
    return home, key, fpr


def _sign(home: pathlib.Path, data: pathlib.Path) -> pathlib.Path:
    sig = data.with_name(data.name + ".asc")
    subprocess.run(
        [
            "gpg",
            "--homedir",
            str(home),
            "--batch",
            "--yes",
            "--pinentry-mode",
            "loopback",
            "--passphrase",
            "",
            "--armor",
            "--detach-sign",
            "-o",
            str(sig),
            str(data),
        ],
        check=True,
        capture_output=True,
    )
    return sig


@needs_gpg
def test_gpgv_refuses_a_one_byte_tampered_repomd(
    signer: tuple[pathlib.Path, pathlib.Path, str], tmp_path: pathlib.Path
) -> None:
    home, key, fpr = signer
    md = tmp_path / "repomd.xml"
    md.write_bytes(origin_files()["repodata/repomd.xml"])
    sig = _sign(home, md)
    om.verify_signature(md, sig, key, fpr)  # control: untampered verifies
    md.write_bytes(om.tamper_repomd(md.read_bytes()))
    with pytest.raises(om.MirrorError, match="gpgv refused"):
        om.verify_signature(md, sig, key, fpr)


@needs_gpg
def test_the_fingerprint_assert_refuses_another_key(
    signer: tuple[pathlib.Path, pathlib.Path, str], tmp_path: pathlib.Path
) -> None:
    home, key, _ = signer
    md = tmp_path / "repomd.xml"
    md.write_bytes(b"<repomd/>")
    sig = _sign(home, md)
    with pytest.raises(om.MirrorError, match="expected exactly %s" % FPR):
        om.verify_signature(md, sig, key, FPR)
    # Control: the real OBS key holds exactly cephpkg.go's fingerprint.
    fprs = om.key_fingerprints(om.KEY_FILE, _fresh_home(tmp_path))
    assert fprs == [om.obs_fingerprint(om.CEPHPKG_GO.read_text(encoding="utf-8"))]


def _fresh_home(tmp_path: pathlib.Path) -> pathlib.Path:
    home = tmp_path / "home"
    home.mkdir(mode=0o700)
    return home


def test_tamper_changes_exactly_one_byte() -> None:
    data = origin_files()["repodata/repomd.xml"]
    tampered = om.tamper_repomd(data)
    assert len(tampered) == len(data)
    assert sum(a != b for a, b in zip(data, tampered, strict=True)) == 1
    om.parse_repomd(tampered)  # still parses: only the signature can refuse it


# --- capture ---------------------------------------------------------------------------


def _manifest(repomd_sha: str) -> str:
    return json.dumps({"annotations": {om.ANNOTATION + "repomd-sha256": repomd_sha}})


def test_capture_on_an_existing_tag_pushes_nothing(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    net = Net(origin_files())
    run = FakeRun([(0, "{}", ""), (0, _manifest("0" * 64), "")])
    result = om.capture(EVR, tmp_path / "out", False, _ctx(tmp_path), FPR, _deps(net, run))
    assert not result.pushed
    assert run.oras_calls("push") == []
    assert not any(u.endswith(".rpm") for u in net.asked)
    assert (
        "the first copy is kept" in capsys.readouterr().out
    )  # the stored repomd differs from OBS's


def test_capture_on_a_miss_pushes_once_and_reads_back(tmp_path: pathlib.Path) -> None:
    net = Net(origin_files())
    run = FakeRun([(1, "", "Error: ...: not found"), (0, "", ""), (0, "{}", "")])
    result = om.capture(EVR, tmp_path / "out", False, _ctx(tmp_path), FPR, _deps(net, run))
    assert result.pushed
    pushes = run.oras_calls("push")
    assert len(pushes) == 1
    assert pushes[0][2] == om.image_ref(EVR)
    assert "%s:%s" % (om.LAYER_NAME, om.LAYER_MEDIA_TYPE) in pushes[0]
    notes = [pushes[0][i + 1] for i, a in enumerate(pushes[0]) if a == "--annotation"]
    assert (
        "%spackages=cephadm-%s.noarch,ceph-common-%s.x86_64,librados2-%s.x86_64"
        % (om.ANNOTATION, EVR, EVR, EVR)
        in notes
    )
    assert len(run.oras_calls("manifest")) == 2  # the probe, then the read-back
    with tarfile.open(result.tar) as tar:
        names = sorted(tar.getnames())
    assert "repodata/repomd.xml" in names
    assert "x86_64/librados2-%s.x86_64.rpm" % EVR in names
    assert "noarch/cephadm-%s.noarch.rpm" % OLD not in names  # listed in primary, not taken


def test_capture_stage_only_touches_no_registry(tmp_path: pathlib.Path) -> None:
    run = FakeRun([])  # any oras call would pop an empty queue
    result = om.capture(
        EVR, tmp_path / "out", True, _ctx(tmp_path), FPR, _deps(Net(origin_files()), run)
    )
    assert not result.pushed
    assert result.tar is not None
    assert result.tar.is_file()
    assert not [c for c in run.calls if c[0] == "oras"]


def test_capture_refuses_an_evr_absent_from_primary(tmp_path: pathlib.Path) -> None:
    derived: list[str] = []
    deps = _deps(Net(origin_files()), FakeRun([(1, "", "not found")]))
    deps.derive = lambda _c, _s: derived.append("ran") or []  # type: ignore[func-returns-value]
    with pytest.raises(om.MirrorError, match="does not list"):
        om.capture("19.2.3-lp160.2.95", tmp_path / "out", False, _ctx(tmp_path), FPR, deps)
    assert derived == []


def test_capture_refuses_to_push_when_a_container_check_fails(tmp_path: pathlib.Path) -> None:
    run = FakeRun([(1, "", "not found")])
    with pytest.raises(om.MirrorError, match="container check"):
        om.capture(
            EVR,
            tmp_path / "out",
            False,
            _ctx(tmp_path),
            FPR,
            _deps(Net(origin_files()), run, checks_ok=False),
        )
    assert run.oras_calls("push") == []


# --- fetch --------------------------------------------------------------------------------


def test_fetch_a_miss_is_an_error_naming_the_dispatch(tmp_path: pathlib.Path) -> None:
    run = FakeRun([(1, "", "Error: failed to resolve: not found")])
    with pytest.raises(om.MirrorError, match="ci-obs-mirror.yml with evr=%s" % EVR):
        om.fetch(EVR, tmp_path / "dest", FPR, run, key=_ctx(tmp_path).key)


def test_fetch_unpacks_and_verifies(tmp_path: pathlib.Path) -> None:
    files = origin_files()
    blob = io.BytesIO()
    with tarfile.open(fileobj=blob, mode="w") as tar:
        for rel, data in files.items():
            info = tarfile.TarInfo(rel)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))

    def pulls(argv: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        if argv[:2] == ["oras", "pull"]:
            (pathlib.Path(argv[argv.index("--output") + 1]) / om.LAYER_NAME).write_bytes(
                blob.getvalue()
            )
            return subprocess.CompletedProcess(argv, 0, "", "")
        return FakeRun()(argv)

    repomd = om.fetch(EVR, tmp_path / "dest", FPR, pulls, key=_ctx(tmp_path).key)
    assert repomd.revision == "1790751035"
    assert (tmp_path / "dest" / "x86_64" / ("librados2-%s.x86_64.rpm" % EVR)).is_file()
    # Control: a tree whose primary does not match its repomd is refused.
    (tmp_path / "dest" / PRIMARY_HREF).write_bytes(b"corrupt")
    with pytest.raises(om.ChecksumMismatchError):
        om.verify_tree(tmp_path / "dest", _ctx(tmp_path).key, FPR, FakeRun())


# --- serve --------------------------------------------------------------------------------


def _mirror_tree(tmp_path: pathlib.Path) -> pathlib.Path:
    tree = tmp_path / "mirror"
    (tree / "repodata").mkdir(parents=True)
    (tree / "repodata" / "repomd.xml").write_bytes(b"<repomd/>")
    return tree


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        port: int = s.getsockname()[1]
    return port


def test_serve_returns_a_live_pid_that_serves_the_tree(tmp_path: pathlib.Path) -> None:
    port = _free_port()
    pid = om.serve(_mirror_tree(tmp_path), port, hosts=lambda: ("127.0.0.1",))
    try:
        # The server outlives serve(): it is a detached session, not a child the caller must keep.
        assert om.http_get("http://127.0.0.1:%d/repodata/repomd.xml" % port) == b"<repomd/>"
    finally:
        os.kill(pid, signal.SIGTERM)


def test_serve_probes_every_host_and_names_the_one_that_never_answers(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(om.time, "sleep", lambda _s: None)
    asked: list[str] = []

    def probe(url: str) -> bytes:
        asked.append(url)
        if url.startswith("http://10.9.8.7:"):
            raise OSError("connection refused")
        return b"<repomd/>"

    port = _free_port()
    with pytest.raises(om.MirrorError, match=r"never answered http://10\.9\.8\.7:%d/" % port):
        om.serve(_mirror_tree(tmp_path), port, probe=probe, hosts=lambda: ("127.0.0.1", "10.9.8.7"))
    assert asked[0] == "http://127.0.0.1:%d/repodata/repomd.xml" % port
    assert len(asked) > 2
    assert all(u.startswith("http://10.9.8.7:") for u in asked[1:])


def test_serve_refuses_a_directory_that_is_not_a_mirror(tmp_path: pathlib.Path) -> None:
    with pytest.raises(om.MirrorError, match="not a mirror tree"):
        om.serve(tmp_path, _free_port(), hosts=lambda: ("127.0.0.1",))


def test_primary_ipv4_is_not_loopback() -> None:
    try:
        addr = om.primary_ipv4()
    except (OSError, om.MirrorError):
        pytest.skip("no default route in this sandbox")
    assert not addr.startswith("127.")


def test_the_serve_cli_hands_the_vms_the_fleet_gateway_not_the_bridge_vm(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 192.168.111.1 is the bridge VM (it hosts the :5000 registry); the runner is the libvirt gateway .254. PR #591's first run pointed zypper at .1.
    out = tmp_path / "out"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    monkeypatch.setattr(om, "serve", lambda _d, _p: 4242)
    assert om.main(["serve", "--dir", str(tmp_path), "--port", "8089"]) == 0
    assert out.read_text().splitlines() == ["pid=4242", "url=http://192.168.111.254:8089/"]
    assert om.VM_GATEWAY == "192.168.111.254"
