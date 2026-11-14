"""`rediacc_ci.drills.backup_onprem` (the I7 variant): the pure verdicts, the environment it builds for `src/entry/on-premise.ts`, and the run's row logic against a scripted server.

The live run (RustFS, the real probe script, `npx tsx src/entry/on-premise.ts`) is the acceptance and belongs to the lead.
"""

from __future__ import annotations

import types
import typing

import pytest

from rediacc_ci.core import account
from rediacc_ci.drills import backup, backup_check_trigger, lib
from rediacc_ci.drills import backup_onprem as onprem

if typing.TYPE_CHECKING:
    import pathlib

KEYS = {
    "ed25519_priv": "ep",
    "ed25519_pub": "eu",
    "x25519_priv": "xp",
    "x25519_pub": "xu",
    "api_key": "k" * 32,
    "jwt": "j" * 32,
}
ENDPOINT = "http://127.0.0.1:9100"
BUCKET = "rediacc-onprem-probe-abc"


def test_the_overrides_select_the_on_premise_entry_and_the_run_s_own_store() -> None:
    env = onprem.onprem_overrides(
        port=4321,
        db_path="/w/a.db",
        endpoint=ENDPOINT,
        bucket=BUCKET,
        access_key="ak",
        secret_key="sk",
        keys=KEYS,
    )
    assert env["ON_PREMISE_MODE"] == "true"
    assert env["PORT"] == "4321"
    assert env["ACCOUNT_BACKUP_S3_ENDPOINT"] == ENDPOINT
    assert env["ACCOUNT_BACKUP_S3_BUCKET"] == BUCKET
    assert env["BACKUP_MAINTENANCE_INTERVAL_MS"] == "0"
    # An inherited dev environment must not redirect the store or switch on the test seam or the upstream renew.
    for name in ("TEST_MODE", "UPSTREAM_API_KEY", "CONFIG_R2_ENDPOINT", "CONFIG_R2_BUCKET"):
        assert env[name] == ""
    # envSchema's required fields are all present and the two secrets are long enough.
    for name in (
        "ACCOUNT_ED25519_PRIVATE_KEY",
        "ACCOUNT_ED25519_PUBLIC_KEY",
        "ACCOUNT_X25519_PRIVATE_KEY",
        "ACCOUNT_X25519_PUBLIC_KEY",
    ):
        assert env[name]
    assert len(env["ACCOUNT_SERVER_API_KEY"]) >= 32
    assert len(env["ACCOUNT_JWT_SECRET"]) >= 32


def test_the_probe_reads_its_credentials_from_the_environment_never_from_argv() -> None:
    env = onprem.probe_env(ENDPOINT, BUCKET, "ak", "sk")
    assert env["S3_SECRET_ACCESS_KEY"] == "sk"
    assert set(env) == {
        "S3_ENDPOINT",
        "S3_BUCKET",
        "S3_ACCESS_KEY_ID",
        "S3_SECRET_ACCESS_KEY",
        "S3_REGION",
    }


@pytest.mark.parametrize(
    ("line", "ok"),
    [
        (
            "Backup chunk storage: %s/%s public=%s region=us-east-1" % (ENDPOINT, BUCKET, ENDPOINT),
            True,
        ),
        ("Backup chunk storage: not configured (ACCOUNT_BACKUP_S3_* unset)", False),
        ("Backup chunk storage: http://elsewhere:1/%s public=x region=y" % BUCKET, False),
        ("", False),
    ],
)
def test_plane_configured_needs_this_run_s_store_in_the_boot_line(line: str, ok: bool) -> None:
    assert onprem.plane_configured(line, ENDPOINT, BUCKET) is ok


def test_boot_line_is_found_among_other_output() -> None:
    text = "Email transport: smtp\nBackup chunk storage: x/y public=x region=r\nMode: on-premise\n"
    assert onprem.boot_line(text) == "Backup chunk storage: x/y public=x region=r"
    assert onprem.boot_line("nothing here") == ""


@pytest.mark.parametrize(
    ("status", "body", "verdict"),
    [
        (401, '{"error":"missing token"}', "mounted"),
        (404, "Not Found", "missing"),
        (503, '{"code":"BACKUP_NOT_CONFIGURED"}', "unconfigured"),
        (401, '{"code":"BACKUP_NOT_CONFIGURED"}', "unconfigured"),
        (500, "boom", "other-500"),
        (0, "refused", "other-0"),
    ],
)
def test_route_verdict(status: int, body: str, verdict: str) -> None:
    assert onprem.route_verdict(status, body) == verdict


class FakeServer:
    pid = 4242

    def __init__(self, log_lines: list[str], sink: typing.Any) -> None:
        sink.write(("\n".join(log_lines) + "\n").encode())
        sink.flush()

    def poll(self) -> None:
        return None

    def wait(self, timeout: float | None = None) -> int:
        del timeout
        return 0


@pytest.fixture
def run(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> typing.Callable[..., lib.Drill]:
    root = tmp_path / "root"
    root.mkdir()
    monkeypatch.setenv("REDIACC_CI_ROOT", str(root))
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    monkeypatch.setattr(
        account,
        "generate_crypto_keys",
        lambda **_k: types.SimpleNamespace(
            ed25519_priv="ep",
            ed25519_pub="eu",
            x25519_priv="xp",
            x25519_pub="xu",
            api_key="k" * 32,
            jwt="j" * 32,
        ),
    )
    monkeypatch.setattr(onprem.time, "sleep", lambda _s: None)

    def go(log_lines: list[str], answers: dict[tuple[str, str], tuple[int, str]]) -> lib.Drill:
        drill = lib.Drill("backup-onprem", selftest=False, keep_work=False)
        drill.init()

        def spawn(argv: list[str], **kwargs: typing.Any) -> typing.Any:
            assert argv == ["npx", "--no-install", "tsx", "src/entry/on-premise.ts"]
            assert kwargs["cwd"].endswith("private/account")
            assert kwargs["env"]["ON_PREMISE_MODE"] == "true"
            return FakeServer(log_lines, kwargs["stdout"])

        def status(_port: int, method: str, path: str) -> tuple[int, str]:
            return answers.get((method, path), (404, "Not Found"))

        monkeypatch.setattr(onprem, "http_status", status)
        subject = onprem.OnPrem(drill, spawn=spawn)
        subject.bucket = BUCKET
        if subject.start_server():
            subject.server_rows()
        return drill

    return go


HEALTHY = {("GET", onprem.SERVER_INFO): (200, "{}"), ("GET", onprem.USAGE_PATH): (401, "{}")}
CONFIGURED = [
    "Backup chunk storage: %s/%s public=%s region=us-east-1" % (ENDPOINT, BUCKET, ENDPOINT)
]


def test_a_correctly_booted_on_premise_entry_passes_every_row(
    run: typing.Callable[..., lib.Drill],
) -> None:
    drill = run(CONFIGURED, HEALTHY)
    try:
        assert drill.failures == 0
        assert drill.count == 5
    finally:
        drill.teardown()


@pytest.mark.parametrize(
    "case",
    [
        "unconfigured-line",
        "usage-missing",
        "usage-unconfigured",
        "test-seam-served",
        "admin-served",
    ],
)
def test_each_row_fails_on_the_defect_it_names(
    run: typing.Callable[..., lib.Drill], case: str
) -> None:
    lines = list(CONFIGURED)
    answers = dict(HEALTHY)
    if case == "unconfigured-line":
        lines = ["Backup chunk storage: not configured (ACCOUNT_BACKUP_S3_* unset)"]
    elif case == "usage-missing":
        answers[("GET", onprem.USAGE_PATH)] = (404, "Not Found")
    elif case == "usage-unconfigured":
        answers[("GET", onprem.USAGE_PATH)] = (503, '{"code":"BACKUP_NOT_CONFIGURED"}')
    elif case == "test-seam-served":
        answers[("POST", onprem.ABSENT_ROUTES[0])] = (200, "{}")
    else:
        answers[("POST", onprem.ABSENT_ROUTES[1])] = (401, "{}")
    drill = run(lines, answers)
    try:
        assert drill.failures == 1
    finally:
        drill.teardown()


def test_a_server_that_never_answers_is_a_failed_boot_row(
    run: typing.Callable[..., lib.Drill], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(onprem, "BOOT_TRIES", 2)
    drill = run(CONFIGURED, {})
    try:
        assert drill.failures == 1
        assert drill.count == 1
    finally:
        drill.teardown()


@pytest.mark.parametrize(("dead_rc", "failures"), [(1, 0), (0, 1)])
def test_the_probe_row_fails_when_the_control_does_not_fail(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, dead_rc: int, failures: int
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    monkeypatch.setenv("REDIACC_CI_ROOT", str(root))
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    drill = lib.Drill("backup-onprem", selftest=False, keep_work=False)
    drill.init()
    calls: list[str] = []

    def fake_run(argv: list[str], env: dict[str, str] | None = None, **_k: typing.Any) -> None:
        assert argv[0] == "bash"
        calls.append((env or {})["S3_ENDPOINT"])
        drill.code = 0 if len(calls) == 1 else dead_rc

    monkeypatch.setattr(drill, "run", fake_run)
    try:
        onprem.OnPrem(drill).probe_row()
        assert drill.failures == failures
        assert calls[0] != calls[1]
    finally:
        drill.teardown()


def test_the_selftest_fires_and_an_unknown_option_exits_2(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert onprem.main(["--selftest"]) == 1
    assert "selftest fired as designed" in capsys.readouterr().out
    assert onprem.main(["--bogus"]) == 2


def test_the_receipt_module_still_asks_for_the_on_premise_half() -> None:
    """The variant exists to set `onprem`; a receipt without it must stay NOT_VERIFIED."""
    assert "l" in backup_check_trigger.REQUIRED_LEGS
    assert set(backup_check_trigger.REQUIRED_LEGS) <= set(backup.KNOWN_LEGS)


@pytest.mark.parametrize(
    ("status", "body", "verdict"),
    [
        (200, "<ObjectLockEnabled>Enabled</ObjectLockEnabled>", "supported"),
        (200, "", "unsupported"),
        (501, "NotImplemented", "unsupported"),
        (404, "ObjectLockConfigurationNotFoundError", "unsupported"),
        (403, "<Code>AccessDenied</Code>", "denied"),
        (0, "connection refused", "unreachable"),
    ],
)
def test_capability_verdict_separates_a_real_answer_from_a_bare_one(
    status: int, body: str, verdict: str
) -> None:
    marker = onprem.CAPABILITIES[0][2]
    assert onprem.capability_verdict(status, body, marker) == verdict


def test_the_capability_queries_name_both_features_and_a_marker_each() -> None:
    assert [name for name, _query, _marker in onprem.CAPABILITIES] == ["object-lock", "versioning"]
    assert all(marker.startswith("<") for _name, _query, marker in onprem.CAPABILITIES)


# ---------------------------------------------------------------------------
# Leg u (`capability_row`) driven against a scripted store.
# ---------------------------------------------------------------------------


@pytest.fixture
def capability(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> typing.Callable[[dict[str, tuple[int, str]]], tuple[lib.Drill, list[str]]]:
    root = tmp_path / "root"
    root.mkdir()
    monkeypatch.setenv("REDIACC_CI_ROOT", str(root))
    monkeypatch.setenv("TMPDIR", str(tmp_path))

    def go(answers: dict[str, tuple[int, str]]) -> tuple[lib.Drill, list[str]]:
        drill = lib.Drill("backup-onprem", selftest=False, keep_work=False)
        drill.init()
        notes: list[str] = []
        monkeypatch.setattr(drill, "note", notes.append)

        def http_call(
            method: str, url: str, _data: bytes, _headers: dict[str, str], **_k: typing.Any
        ) -> tuple[int, str]:
            assert method == "GET"
            assert url.startswith("%s/%s?" % (ENDPOINT, BUCKET))
            return answers[url.split("?", 1)[1]]

        monkeypatch.setattr(onprem.wire, "http_call", http_call)
        subject = onprem.OnPrem(drill)
        subject.endpoint = ENDPOINT
        subject.bucket = BUCKET
        subject.capability_row()
        return drill, notes

    return go


def _store(object_lock: tuple[int, str], versioning: tuple[int, str]) -> dict[str, tuple[int, str]]:
    return {
        onprem.CAPABILITIES[0][1]: object_lock,
        onprem.CAPABILITIES[1][1]: versioning,
    }


def test_leg_u_records_a_store_that_offers_both_features(
    capability: typing.Callable[..., tuple[lib.Drill, list[str]]],
) -> None:
    drill, notes = capability(
        _store(
            (200, onprem.CAPABILITIES[0][2]),
            (200, onprem.CAPABILITIES[1][2]),
        )
    )
    try:
        assert drill.failures == 0
        recorded = [n for n in notes if n.startswith("STORE-CAPABILITY")]
        assert recorded == [
            "STORE-CAPABILITY object-lock: supported (HTTP 200)",
            "STORE-CAPABILITY versioning: supported (HTTP 200)",
        ]
    finally:
        drill.teardown()


@pytest.mark.parametrize(
    ("object_lock", "versioning", "verdicts"),
    [
        ((501, "NotImplemented"), (200, ""), ["unsupported", "unsupported"]),
        ((403, "<Code>AccessDenied</Code>"), (0, "refused"), ["denied", "unreachable"]),
    ],
)
def test_leg_u_records_without_asserting_on_a_store_that_lacks_them(
    capability: typing.Callable[..., tuple[lib.Drill, list[str]]],
    object_lock: tuple[int, str],
    versioning: tuple[int, str],
    verdicts: list[str],
) -> None:
    drill, notes = capability(_store(object_lock, versioning))
    try:
        assert drill.failures == 0
        recorded = [n for n in notes if n.startswith("STORE-CAPABILITY")]
        assert [n.split(": ")[1].split(" ")[0] for n in recorded] == verdicts
    finally:
        drill.teardown()


@pytest.mark.parametrize("broken", ["always-supported", "always-unsupported", "never-unreachable"])
def test_leg_u_planted_controls_fire_when_the_verdict_function_is_broken(
    capability: typing.Callable[..., tuple[lib.Drill, list[str]]],
    monkeypatch: pytest.MonkeyPatch,
    broken: str,
) -> None:
    real = onprem.capability_verdict

    def verdict(status: int, body: str, marker: str) -> str:
        if broken == "always-supported":
            return "supported"
        if broken == "always-unsupported":
            return "unsupported"
        return "unsupported" if status == 0 else real(status, body, marker)

    monkeypatch.setattr(onprem, "capability_verdict", verdict)
    drill, _notes = capability(_store((200, ""), (200, "")))
    try:
        assert drill.failures >= 1
    finally:
        drill.teardown()
