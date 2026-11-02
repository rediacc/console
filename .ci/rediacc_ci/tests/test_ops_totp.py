"""rediacc_ci.ops.totp: the RFC 6238 Appendix B SHA-1 vectors, seed normalisation, and a command line that prints nothing secret."""

import base64

import pytest

from rediacc_ci.ops import totp

# GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ
RFC_SEED_B32 = base64.b32encode(b"12345678901234567890").decode()


@pytest.mark.parametrize(("at", "eight"), totp.RFC_VECTORS)
def test_rfc6238_sha1_vectors_eight_digits(at, eight):
    assert totp.code_for_key(b"12345678901234567890", at, digits=8) == eight


@pytest.mark.parametrize(("at", "eight"), totp.RFC_VECTORS)
def test_rfc6238_sha1_vectors_truncated_to_six_from_the_base32_seed(at, eight):
    assert totp.code(RFC_SEED_B32, at=at) == eight[-6:]


def test_the_vector_table_is_the_rfc_one():
    """Pinned literally, so an edit to RFC_VECTORS cannot make the self-check agree with a wrong implementation."""
    assert dict(totp.RFC_VECTORS) == {
        59: "94287082",
        1111111109: "07081804",
        1111111111: "14050471",
        1234567890: "89005924",
        2000000000: "69279037",
        20000000000: "65353130",
    }


@pytest.mark.parametrize(
    "spelling",
    [
        RFC_SEED_B32,
        RFC_SEED_B32.lower(),
        RFC_SEED_B32 + "====",
        " ".join(RFC_SEED_B32[i : i + 4] for i in range(0, len(RFC_SEED_B32), 4)),
        "-".join(RFC_SEED_B32[i : i + 4] for i in range(0, len(RFC_SEED_B32), 4)).lower(),
    ],
)
def test_seed_spellings_decode_to_the_same_key(spelling):
    assert totp.decode_seed(spelling) == b"12345678901234567890"


def test_unpadded_seed_whose_length_is_not_a_multiple_of_eight():
    seed = base64.b32encode(b"0123456789").decode().rstrip("=")  # 16 chars, no padding needed
    odd = base64.b32encode(b"abcdefg").decode()  # 7 bytes -> padded to 16 with '='
    assert "=" in odd
    assert totp.decode_seed(seed) == b"0123456789"
    assert totp.decode_seed(odd.rstrip("=").lower()) == b"abcdefg"


@pytest.mark.parametrize("bad", ["", "   ", "====", "not base32 1!", "ABC18"])
def test_an_unusable_seed_is_a_named_error_that_never_echoes_it(bad):
    with pytest.raises(totp.TotpError) as caught:
        totp.decode_seed(bad)
    if bad.strip(" ="):
        assert bad not in str(caught.value)


def test_the_code_is_six_digits_now():
    current = totp.code(RFC_SEED_B32)
    assert len(current) == 6
    assert current.isdigit()


def test_self_check_passes():
    totp.self_check()


def test_cli_without_a_seed_prints_only_ok_lines(monkeypatch, capsys):
    monkeypatch.delenv(totp.SEED_ENV, raising=False)
    assert totp.main([]) == 0
    out, err = capsys.readouterr()
    assert all(line.startswith("ok ") for line in out.splitlines())
    assert err == ""


def test_cli_with_a_seed_never_prints_the_seed_or_the_code(monkeypatch, capsys):
    monkeypatch.setenv(totp.SEED_ENV, RFC_SEED_B32)
    current = totp.code(RFC_SEED_B32)
    assert totp.main([]) == 0
    out, err = capsys.readouterr()
    assert RFC_SEED_B32 not in out + err
    assert current not in out + err
    assert "ok REDIACC_BENCH_TOTP_SEED decodes" in out


def test_cli_with_a_bad_seed_exits_1_without_echoing_it(monkeypatch, capsys):
    monkeypatch.setenv(totp.SEED_ENV, "not base32 1!")
    assert totp.main([]) == 1
    out, err = capsys.readouterr()
    assert "not base32 1!" not in out + err
    assert "REDIACC_BENCH_TOTP_SEED" in err


def test_cli_refuses_arguments():
    assert totp.main(["--seed", "x"]) == 2
