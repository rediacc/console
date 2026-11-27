"""`rediacc_ci.deploy.preview_keys`: the preview's server secrets are generated per preview and pushed through stdin only.

Nothing here reaches Cloudflare: the pusher seam is a recording fake that logs its argv, its cwd and the bytes on its stdin. Key generation is real in one case (a real X25519 pair and two real random secrets) and swapped for fixed fixtures in the rest.
"""

from __future__ import annotations

import io
import json
import pathlib
import typing

import pytest

from rediacc_ci.deploy import preview_keys as pk

NAME = "pv-able-baker-charlie"
ENV = {
    "PREVIEW_NAME": NAME,
    "ACCOUNT_ED25519_PUBLIC_KEY": "ed-public-fixture",
    "ROOT_EMAIL": "root@example.invalid",
    "CLOUDFLARE_TURNSTILE_SECRET_KEY": "turnstile-fixture",
}


class Recorder:
    def __init__(self, rc: int = 0, stdout: str = "", stderr: str = "") -> None:
        self.calls: list[tuple[list[str], str, str]] = []
        self.result = (rc, stdout, stderr)

    def __call__(self, argv: list[str], cwd: str, stdin: str) -> tuple[int, str, str]:
        self.calls.append((argv, cwd, stdin))
        return self.result


def counter() -> typing.Callable[[], str]:
    state = {"n": 0}

    def draw() -> str:
        state["n"] += 1
        return "secret-%02d-" % state["n"] + "x" * 40

    return draw


def fixed_pair() -> tuple[str, str]:
    return "x25519-private-fixture", "x25519-public-fixture"


def run(environ: dict[str, str], pusher: Recorder) -> int:
    return pk.main([], environ, fixed_pair, counter(), pusher)


def test_real_generation_gives_a_fresh_pair_and_two_distinct_long_secrets() -> None:
    a = pk.generate()
    b = pk.generate()
    assert a.x25519_private != a.x25519_public
    assert len(a.api_key) >= 32
    assert len(a.session_secret) >= 32
    assert a.api_key != a.session_secret
    # Two previews never share a value.
    assert {a.x25519_private, a.api_key, a.session_secret}.isdisjoint(
        {b.x25519_private, b.api_key, b.session_secret}
    )


def test_equal_draws_are_refused() -> None:
    with pytest.raises(pk.RefusedError):
        pk.generate(fixed_pair, lambda: "same" * 10)


def test_bulk_document_carries_the_generated_set_and_the_passthroughs_and_no_mail() -> None:
    keys = pk.generate(fixed_pair, counter())
    doc = pk.bulk_document(keys, ENV)
    assert list(doc) == [*pk.GENERATED_NAMES, *pk.PASSTHROUGH_NAMES]
    assert doc["ACCOUNT_X25519_PUBLIC_KEY"] == "x25519-public-fixture"
    assert not [k for k in doc if k.startswith("AWS_SES_")]


def test_a_mail_credential_in_the_environment_never_reaches_the_document() -> None:
    keys = pk.generate(fixed_pair, counter())
    doc = pk.bulk_document(
        keys, {**ENV, "AWS_SES_ACCESS_KEY_ID": "ses-key", "AWS_SES_SECRET_ACCESS_KEY": "ses-secret"}
    )
    assert "ses-key" not in json.dumps(doc)
    assert "ses-secret" not in json.dumps(doc)


def test_an_empty_optional_passthrough_is_left_out_and_an_empty_required_one_is_refused() -> None:
    keys = pk.generate(fixed_pair, counter())
    doc = pk.bulk_document(keys, {**ENV, "ROOT_EMAIL": ""})
    assert "ROOT_EMAIL" not in doc
    with pytest.raises(pk.RefusedError, match="ACCOUNT_ED25519_PUBLIC_KEY"):
        pk.bulk_document(keys, {**ENV, "ACCOUNT_ED25519_PUBLIC_KEY": ""})


def test_the_push_is_one_bulk_call_with_no_value_in_argv(tmp_path) -> None:
    rec = Recorder()
    out = tmp_path / "gh-output"
    rc = run({**ENV, "GITHUB_OUTPUT": str(out)}, rec)
    assert rc == 0
    assert len(rec.calls) == 1
    argv, cwd, stdin = rec.calls[0]
    assert argv[-4:] == ["secret", "bulk", "--name", NAME]
    assert cwd.endswith("workers/www")
    doc = json.loads(stdin)
    for value in doc.values():
        assert not any(value in arg for arg in argv)
    # Every generated value is in the document, the stdin is where they travel.
    assert doc["ACCOUNT_X25519_PRIVATE_KEY"] == "x25519-private-fixture"
    assert doc["ACCOUNT_SERVER_API_KEY"].startswith("secret-01-")
    assert doc["ACCOUNT_JWT_SECRET"].startswith("secret-02-")


def test_only_the_public_half_leaves_through_github_output(tmp_path) -> None:
    rec = Recorder()
    out = tmp_path / "gh-output"
    assert run({**ENV, "GITHUB_OUTPUT": str(out)}, rec) == 0
    text = out.read_text()
    assert text == "x25519_public=x25519-public-fixture\n"
    assert "private" not in text
    assert "secret-0" not in text


def test_wrangler_output_is_redacted_of_every_value_in_the_document() -> None:
    doc = {"ACCOUNT_JWT_SECRET": "jwt-value-1234", "ACCOUNT_SERVER_API_KEY": "api-value-5678"}
    buf = io.StringIO()
    rec = Recorder(0, "set jwt-value-1234\n", "warn api-value-5678\n")
    assert pk.push(NAME, doc, rec, buf) == 0
    text = buf.getvalue()
    assert "jwt-value-1234" not in text
    assert "api-value-5678" not in text
    assert text.count("[redacted]") == 2


def test_a_wrangler_failure_returns_its_rc_prints_no_value_and_writes_no_output(
    tmp_path, capsys
) -> None:
    rec = Recorder(7, "", "boom secret-01-" + "x" * 40)
    out = tmp_path / "gh-output"
    rc = run({**ENV, "GITHUB_OUTPUT": str(out)}, rec)
    assert rc == 7
    captured = capsys.readouterr()
    assert "secret-01-" not in captured.out + captured.err
    assert not out.exists()


@pytest.mark.parametrize("bad", ["", "pr-12", NAME + "-signer", "pv-able-baker"])
def test_a_name_that_is_not_a_preview_worker_is_refused_before_any_call(bad: str) -> None:
    rec = Recorder()
    rc = run({**ENV, "PREVIEW_NAME": bad}, rec)
    assert rc == 1
    assert rec.calls == []


def test_arguments_are_refused() -> None:
    assert pk.main(["--x"], dict(ENV), fixed_pair, counter(), Recorder()) == 2


def test_the_module_reads_no_production_secret_name() -> None:
    source = pathlib.Path(pk.__file__).read_text(encoding="utf-8")
    for name in ("ACCOUNT_JWT_SECRET", "ACCOUNT_SERVER_API_KEY", "ACCOUNT_X25519_PRIVATE_KEY"):
        # Written as push keys, never read from the environment.
        assert 'environ.get("%s"' % name not in source
        assert 'os.environ["%s"]' % name not in source
    assert "BWS_" not in source
