"""`rediacc_ci.core.renet_flavor`: the flavor-to-path mapping, pinned against `build.sh` and `rdc.sh` so the copies cannot drift."""

import pathlib
import re
import subprocess

from rediacc_ci.core import renet_flavor


def _root():
    return pathlib.Path(__file__).resolve().parents[3]


def test_flavor_for_follows_build_sh_precedence():
    f = renet_flavor.flavor_for
    assert f(None) == "nolicense"
    assert f("0") == "nolicense"
    assert f("1") == "enforce"
    assert f("1", ["--nolicense"]) == "nolicense"
    assert f("0", ["--license"]) == "enforce"
    assert f("0", ["--license", "--nolicense"]) == "nolicense"
    assert f("0", ["--nolicense", "--license"]) == "enforce"
    assert f("1", ["other"]) == "enforce"


def test_build_flag_is_explicit_for_both_flavors():
    assert renet_flavor.build_flag("nolicense") == "--nolicense"
    assert renet_flavor.build_flag("enforce") == "--license"


def test_paths_per_flavor():
    assert renet_flavor.binary("/r", "nolicense") == "/r/bin/renet"
    assert renet_flavor.binary("/r", "enforce", ".exe") == "/r/bin/enforce/renet.exe"
    assert renet_flavor.linux_binaries("/r", "enforce") == [
        "/r/bin/enforce/renet-linux-amd64",
        "/r/bin/enforce/renet-linux-arm64",
    ]
    assert renet_flavor.stamp_path("/r", "nolicense") == "/r/bin/.renet-build-stamp"
    assert renet_flavor.stamp_path("/r", "enforce") == "/r/bin/enforce/.renet-build-stamp"


def test_buildinfo_flavor_and_refusal():
    plain = "\tbuild\t-tags=nolicense\n"
    keyed = "\tbuild\t-ldflags=-X x.ProductionPublicKey=abc\n"
    keyless = "\tbuild\t-ldflags=-s -w\n"
    assert renet_flavor.buildinfo_flavor(plain) == "nolicense"
    assert renet_flavor.buildinfo_flavor(keyed) == "enforce"
    assert renet_flavor.buildinfo_flavor("no build lines") == ""
    assert renet_flavor.flavor_refusal("enforce", keyed) is None
    assert renet_flavor.flavor_refusal("nolicense", plain) is None
    assert "nolicense" in (renet_flavor.flavor_refusal("enforce", plain) or "")
    assert "public key" in (renet_flavor.flavor_refusal("enforce", keyless) or "")
    assert "unknown" in (renet_flavor.flavor_refusal("enforce", "") or "")


def test_subdir_equals_build_sh_dev_out_dir():
    build_sh = _root() / "private" / "renet" / "build.sh"
    text = build_sh.read_text(encoding="utf-8")
    func = re.search(r"^_dev_out_dir\(\) \{.*?^\}", text, re.MULTILINE | re.DOTALL)
    assert func is not None
    for flavor, tags in (("nolicense", "-tags nolicense"), ("enforce", "")):
        script = 'SCRIPT_DIR=/r\n%s\n_dev_out_dir "$1"' % func.group(0)
        out = subprocess.run(
            ["bash", "-c", script, "bash", tags], capture_output=True, text=True, check=True
        ).stdout.strip()
        assert out == "/r/" + renet_flavor.SUBDIR[flavor]


def test_rdc_sh_path_block_names_the_flavor_directory():
    text = (_root() / "rdc.sh").read_text(encoding="utf-8")
    block = re.search(r"^renet_bin_dir=.*?^export PATH=.*?$", text, re.MULTILINE | re.DOTALL)
    assert block is not None
    for license_env, flavor in ((None, "nolicense"), ("1", "enforce")):
        env = {"PATH": "/usr/bin:/bin"}
        if license_env is not None:
            env["RDC_RENET_LICENSE"] = license_env
        script = 'ROOT_DIR=/r\n%s\nprintf "%%s" "${PATH%%%%:*}"' % block.group(0)
        out = subprocess.run(
            ["bash", "-c", script], capture_output=True, text=True, check=True, env=env
        ).stdout
        assert out == "/r/private/renet/" + renet_flavor.SUBDIR[flavor]
