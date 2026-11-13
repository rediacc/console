"""rediacc_ci.ops.region_smoke: the probe sign-in, store read and baseline comparison, driven by a fake `rdc` so nothing reaches a region."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from rediacc_ci.ops import region_smoke as rs

if TYPE_CHECKING:
    import pathlib

SEED = "JBSWY3DPEHPK3PXP"
VALUES = {
    rs.EMAIL_ENV: "probe@example.invalid",
    rs.PW_ENV: "pw-secret",
    rs.MASTER_PW_ENV: "master-secret",
}
SHOWN = json.dumps({"machines": {"a": 1}, "repos": []})


class FakeRdc:
    """Records every argv and env; answers `config show` with SHOWN and every other verb with rc 0."""

    def __init__(self, show: str = SHOWN, fail: str = "") -> None:
        self.calls: list[tuple[list[str], dict[str, str]]] = []
        self.show = show
        self.fail = fail

    def _rc(self, argv) -> int:
        return 1 if self.fail and self.fail in " ".join(argv) else 0

    def run(self, argv, env) -> int:
        self.calls.append((list(argv), dict(env)))
        return self._rc(argv)

    def capture(self, argv, env, merge_stderr=False):
        del merge_stderr
        self.calls.append((list(argv), dict(env)))
        rc = self._rc(argv)
        return rc, (self.show if argv[-2:] == ["config", "show"] else "")

    def verbs(self) -> list[str]:
        return [" ".join(a[3:]) for a, _ in self.calls]


def _smoke(fake: FakeRdc, region: str = "eu", values=VALUES) -> str:
    return rs.smoke(
        region, values, {"PATH": "/bin", "RDC_DEV": "1"}, fake.run, fake.capture, lambda: 1000.0
    )


def test_the_origin_is_the_regions_domain_or_the_bench_origin() -> None:
    assert rs.origin("eu") == "https://eu.rediacc.cloud"
    assert rs.origin("bench").startswith("https://bench.")
    with pytest.raises(rs.SmokeError) as err:
        rs.origin("mars")
    assert err.value.rc == 2


def test_the_smoke_runs_init_login_enable_refresh_and_show_in_order() -> None:
    fake = FakeRdc()
    digest = _smoke(fake)
    assert fake.verbs() == [
        "config init region-smoke-eu",
        "subscription login --server https://eu.rediacc.cloud",
        "-o json config remote enable --master-password --api-url https://eu.rediacc.cloud",
        "config remote refresh",
        "-o json config show",
    ]
    assert digest == rs.canonical_digest(json.loads(SHOWN))


def test_secrets_reach_only_the_children_that_need_them_and_never_argv() -> None:
    fake = FakeRdc()
    _smoke(fake)
    for argv, _env in fake.calls:
        assert not any(v in " ".join(argv) for v in VALUES.values())
    login = next(e for a, e in fake.calls if a[3] == "subscription")
    enable = next(e for a, e in fake.calls if "enable" in a)
    assert login[rs.LOGIN_PW_ENV] == "pw-secret"
    assert rs.CLI_STORE_MASTER_PW_ENV not in login
    assert enable[rs.CLI_STORE_MASTER_PW_ENV] == "master-secret"
    assert rs.LOGIN_PW_ENV not in enable
    assert all("RDC_DEV" not in e for _a, e in fake.calls)
    assert all(rs.EMAIL_ENV not in e and rs.PW_ENV not in e for _a, e in fake.calls)


def test_a_totp_seed_adds_a_code_to_the_login_child_only() -> None:
    fake = FakeRdc()
    _smoke(fake, values={**VALUES, rs.TOTP_SEED_ENV: SEED})
    login = next(e for a, e in fake.calls if a[3] == "subscription")
    assert len(login[rs.LOGIN_TOTP_ENV]) == 6
    assert all(rs.LOGIN_TOTP_ENV not in e for a, e in fake.calls if a[3] != "subscription")


@pytest.mark.parametrize(
    ("fail", "named"),
    [
        ("subscription login", "subscription login"),
        ("remote enable", "config remote enable"),
        ("remote refresh", "config remote refresh"),
        ("config show", "config show"),
    ],
)
def test_a_failed_step_is_named_and_exits_1(fail: str, named: str) -> None:
    with pytest.raises(rs.SmokeError, match=named) as err:
        _smoke(FakeRdc(fail=fail))
    assert err.value.rc == 1


def test_config_init_that_already_exists_is_not_a_failure() -> None:
    class Exists(FakeRdc):
        def capture(self, argv, env, merge_stderr=False):
            if argv[-3:-1] == ["config", "init"]:
                # The CLI prints this thrown error on stderr: seen only when the caller merges it.
                return 1, ('Config "region-smoke-eu" already exists' if merge_stderr else "")
            return super().capture(argv, env, merge_stderr)

    assert _smoke(Exists())


def test_a_non_json_config_show_is_a_failed_step() -> None:
    with pytest.raises(rs.SmokeError, match="JSON"):
        _smoke(FakeRdc(show="not json"))


def test_the_digest_is_independent_of_key_order_and_changes_with_content() -> None:
    a = rs.canonical_digest({"x": 1, "y": [1, 2]})
    assert a == rs.canonical_digest({"y": [1, 2], "x": 1})
    assert a != rs.canonical_digest({"x": 1, "y": [2, 1]})


def test_values_refuse_a_missing_entry_and_the_placeholder() -> None:
    with pytest.raises(rs.SmokeError, match=rs.PW_ENV) as err:
        rs.read_values({rs.EMAIL_ENV: "e", rs.MASTER_PW_ENV: "m"})
    assert err.value.rc == 2
    with pytest.raises(rs.SmokeError, match="placeholder"):
        rs.read_values({**VALUES, rs.EMAIL_ENV: rs.PLACEHOLDER})
    assert rs.TOTP_SEED_ENV not in rs.read_values(VALUES)


def test_a_bad_totp_seed_is_refused_before_any_step() -> None:
    with pytest.raises(rs.SmokeError, match=rs.TOTP_SEED_ENV):
        rs.read_values({**VALUES, rs.TOTP_SEED_ENV: "not base32 !!"})


def test_arguments_are_refused_with_rc_2() -> None:
    for argv in ([], ["--region"], ["--region", "mars"], ["--region", "eu", "--bogus"]):
        with pytest.raises(rs.SmokeError) as err:
            rs.parse_args(argv)
        assert err.value.rc == 2, argv
    assert rs.parse_args(["--region", "eu", "--record-baseline"]) == ("eu", True, None)


def _main(argv, fake: FakeRdc, monkeypatch) -> int:
    monkeypatch.setenv("REDIACC_BWS_PROFILES", rs.profile_for("bench"))
    for name, value in VALUES.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv(rs.TOTP_SEED_ENV, raising=False)
    return rs.main(argv, fake.run, fake.capture)


def test_record_then_compare_passes_and_a_changed_store_exits_3(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = tmp_path / "eu.json"
    args = ["--region", "bench", "--baseline", str(base)]
    assert _main([*args, "--record-baseline"], FakeRdc(), monkeypatch) == 0
    assert json.loads(base.read_text())["sha256"] == rs.canonical_digest(json.loads(SHOWN))
    assert _main(args, FakeRdc(), monkeypatch) == 0
    changed = FakeRdc(show=json.dumps({"machines": {"a": 2}}))
    assert _main(args, changed, monkeypatch) == 3


def test_a_missing_baseline_is_a_refusal_before_any_rdc_call(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = FakeRdc()
    rc = _main(["--region", "eu", "--baseline", str(tmp_path / "none.json")], fake, monkeypatch)
    assert rc == 2
    assert fake.calls == []


def test_a_baseline_of_another_region_is_refused(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = tmp_path / "b.json"
    rs.write_baseline(base, "us", "00")
    assert _main(["--region", "bench", "--baseline", str(base)], FakeRdc(), monkeypatch) == 2


def test_main_without_the_profile_re_executes_under_it(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("REDIACC_BWS_PROFILES", raising=False)
    fake = FakeRdc()
    base = tmp_path / "eu.json"
    rc = rs.main(["--region", "bench", "--baseline", str(base), "--record-baseline"], fake.run)
    assert rc == 0
    argv = fake.calls[0][0]
    assert argv[1:6] == [
        "-m",
        "rediacc_ci.core.bws_env",
        "exec",
        "--profile",
        rs.profile_for("bench"),
    ]
    assert argv[-5:] == ["--region", "bench", "--baseline", str(base), "--record-baseline"]


def test_a_region_without_a_declared_profile_is_refused_naming_it(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    fake = FakeRdc()
    rc = _main(
        ["--region", "eu", "--baseline", str(tmp_path / "eu.json"), "--record-baseline"],
        fake,
        monkeypatch,
    )
    assert rc == 2
    assert fake.calls == []
    assert "region-smoke-eu" in capsys.readouterr().err


def test_the_bench_profile_is_declared_and_the_declared_set_is_read_from_the_supply_file() -> None:
    assert rs.profile_for("bench") in rs.declared_profiles()
    assert rs.profile_for("mars") not in rs.declared_profiles()


def test_a_failing_remote_enable_with_a_partial_phrase_is_a_failed_step() -> None:
    """4f1397c0.3: only the CLI's already-linked message excuses a non-zero enable."""

    class Enable(FakeRdc):
        text = ""

        def capture(self, argv, env, merge_stderr=False):
            if "enable" in argv:
                return 1, self.text
            return super().capture(argv, env, merge_stderr)

    partial = Enable()
    partial.text = "token refused: this device can open it later"
    with pytest.raises(rs.SmokeError, match="remote enable"):
        _smoke(partial)
    linked = Enable()
    linked.text = 'Config "x" is already linked to remote storage and this device can open it, so'
    assert _smoke(linked)


def test_the_capture_merges_stderr_only_when_asked() -> None:
    """4f1397c0.2: the real subprocess path, with a child that writes to stderr."""
    argv = ["sh", "-c", "echo oops >&2; exit 1"]
    assert rs._subprocess_capture(argv, {}, merge_stderr=True) == (1, "oops\n")
    assert rs._subprocess_capture(argv, {}) == (1, "")


def test_a_non_json_config_show_error_does_not_carry_the_output() -> None:
    """4f1397c0.1: the config content never reaches the error text."""
    with pytest.raises(rs.SmokeError) as err:
        _smoke(FakeRdc(show="machines: SECRET-CONTENT"))
    assert "SECRET-CONTENT" not in str(err.value)
