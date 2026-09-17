"""`rediacc_ci.core.proxyx`, the shared contract every `rediacc_ci.proxies.*`
port imports in place of sourcing `.ci/scripts/test/proxies/proxy-lib.sh`.

NO BASH TWIN OF ITS OWN: `proxy-lib.sh` has no exec bit and is never run as a subprocess by anything (see that file's own header, and `proxyx`'s module docstring for the call-site check that confirmed it). What IS twinned is `run_selftest()` against `proxy_lib_selftest`, byte-for-byte, exercised through every `rediacc_ci.proxies.*` module's own `--selftest` flag in
`test_proxies_cli_manifest.py` and `test_proxies_docker_prepull.py`. This file covers the contract directly, at the unit level, so a defect in `Proxy` itself is caught here rather than only through two downstream twins.

BOTH DIRECTIONS, same shape as the bash `proxy_lib_selftest` it is porting: a proxy that asserts something and has every requirement present must return
0; one that is missing a requirement must return 77, never 0; one that makes
zero checks must return 1, never 0; one that declares zero requirements must
refuse at `preflight()` with 2, before it can even run.
"""

from __future__ import annotations

import pytest

from rediacc_ci.core import proxyx


def test_a_normal_proxy_passes() -> None:
    p = proxyx.Proxy("t", "a fixture subject")
    p.need_cmd("bash", "install bash")
    p.preflight()
    p.ok("something was asserted")
    assert p.finish() == 0


def test_a_failing_check_fails_the_whole_proxy() -> None:
    p = proxyx.Proxy("t", "a fixture subject")
    p.need_cmd("bash", "install bash")
    p.preflight()
    p.ok("one thing passed")
    p.bad("one thing did not")
    assert p.finish() == 1


def test_missing_requirement_is_cannot_run_not_a_verdict() -> None:
    p = proxyx.Proxy("t", "a fixture subject")
    p.need_file("/does/not/exist/anywhere", "create it")
    with pytest.raises(SystemExit) as excinfo:
        p.preflight()
    assert excinfo.value.code == proxyx.PROXY_CANNOT_RUN


def test_zero_declared_requirements_refuses_before_running_anything() -> None:
    p = proxyx.Proxy("t", "a fixture subject with no declared toolchain")
    with pytest.raises(SystemExit) as excinfo:
        p.preflight()
    assert excinfo.value.code == 2


def test_zero_checks_is_a_failure_never_a_pass() -> None:
    p = proxyx.Proxy("t", "a fixture subject that asserts nothing")
    p.need_cmd("bash", "install bash")
    p.preflight()
    assert p.finish() == 1


def test_expect_exit_records_the_last_streams() -> None:
    p = proxyx.Proxy("t", "a fixture subject")
    p.need_cmd("bash", "install bash")
    p.preflight()
    p.expect_exit("0", "true succeeds", ["true"])
    assert p.last_rc == 0
    p.expect_exit("1", "false fails", ["false"])
    assert p.last_rc == 1
    assert p.finish() == 0


def test_expect_exit_accepts_a_comma_list() -> None:
    p = proxyx.Proxy("t", "a fixture subject")
    p.need_cmd("bash", "install bash")
    p.preflight()
    p.expect_exit("1,2", "exits with 2, which is in the accepted list", ["bash", "-c", "exit 2"])
    assert p.failures == 0
    assert p.finish() == 0


def test_run_selftest_passes_both_directions() -> None:
    # The permanent differential twin lives in test_proxies_cli_manifest.py / test_proxies_docker_prepull.py, which check this function's OUTPUT is byte-identical to `proxy_lib_selftest`'s. This asserts its return code directly, over a real PATH removal for the 77 case (see run_selftest's own docstring for why that case forks a real subprocess).
    assert proxyx.run_selftest() == 0
