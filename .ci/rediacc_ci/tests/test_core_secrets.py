"""`rediacc_ci.core.secrets`: the redactor, and the promise that nothing echoes.

THE PROPERTY THIS SUITE IS REALLY ABOUT is a negative one -- "the value does not
appear in the output" -- and a negative is the easiest kind of assertion to
satisfy vacuously. `assert secret not in out` passes when `out` is empty, when
the function raised and was swallowed, and when the fixture's secret was never
put into the input in the first place. So every leak case here is paired with a
POSITIVE control that proves the value was genuinely in play: the names are
still legible, the surrounding text survived, or the same call masked something
else.

THE NAME CLASSIFIER IS TESTED AGAINST A CORPUS, NOT A TABLE. `looks_secret` is a
heuristic, and a table of expectations written next to it only records what its
author believed twice. `rdc.sh:240-248` is an INDEPENDENT ruling: written for a
different reason, by someone solving a different problem, it names four
variables it refuses to let into a process and two it extracts by hand. Those
six names are harvested from the file at run time and the classifier has to
agree with all of them. `.ci/config/bws-secret-map.json` supplies the second,
wider corpus.
"""

import hashlib
import json
import re

import pytest

from rediacc_ci import paths
from rediacc_ci.core import env, secrets
from rediacc_ci.tests import differential as diff

# A value shaped like the real thing: base64, long, no English in it. Short
# fixture strings ("s3cret") hide bugs, because they collide with ordinary text
# and because a redactor that only ever sees them is never asked to deal with a
# value that contains another value.
FAKE_KEY = "MC4CAQAwBQYDK2VwBCIEIH1AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
FAKE_OPAQUE = "0.deadbeef-1111-2222-3333-444455556666.aaaaBBBBccccDDDD:eeeeFFFF"


# ---------------------------------------------------------------------------
# redact -- the default path
# ---------------------------------------------------------------------------


def test_redact_masks_every_occurrence_and_keeps_the_rest() -> None:
    """The leak assertion and its positive control, in one case.

    `FAKE_KEY not in out` alone would pass on an empty string, so the same case
    asserts the surrounding words survived and the mask count matches.
    """
    text = "before %s middle %s after" % (FAKE_KEY, FAKE_KEY)
    out = secrets.redact(text, [FAKE_KEY])
    assert FAKE_KEY not in out
    assert out == "before %s middle %s after" % (secrets.MASK, secrets.MASK)
    assert "before" in out
    assert "after" in out


def test_control_redact_leaves_text_that_holds_no_secret_alone() -> None:
    """A redactor that returned MASK unconditionally would pass the case above."""
    text = "nothing to see here"
    assert secrets.redact(text, [FAKE_KEY]) == text


def test_redact_skips_an_empty_value_but_still_masks_a_real_one() -> None:
    """Both directions of the empty-value guard, in the SAME call.

    An empty needle matches at every position, so a redactor without this guard
    returns a mask between every pair of characters. The non-empty value in the
    same call is what proves the guard did not simply disable the function.
    """
    out = secrets.redact("keep %s" % FAKE_OPAQUE, ["", None, FAKE_OPAQUE])
    assert out == "keep %s" % secrets.MASK
    assert out.count(secrets.MASK) == 1


def test_redact_masks_the_longest_value_first_leaving_no_fragment() -> None:
    """The ordering bug, asserted as the fragment it produces.

    With "abc" applied before "abcdef", the text "abcdef" becomes "***def" -- a
    string that LOOKS redacted while carrying half the longer secret. The
    fragment is named in the assertion so a regression reads as itself.
    """
    out = secrets.redact("abcdef", ["abc", "abcdef"])
    assert out == secrets.MASK
    assert "***def" not in out
    assert "def" not in out


def test_redact_is_idempotent() -> None:
    once = secrets.redact("x %s y" % FAKE_KEY, [FAKE_KEY])
    assert secrets.redact(once, [FAKE_KEY]) == once


def test_redact_masks_a_value_that_arrives_with_trailing_whitespace() -> None:
    """An env-file value and a command's stdout differ by a newline routinely.

    The control is the second assertion: the stripped form must mask the padded
    occurrence too, or the pair only proves one direction.
    """
    padded = FAKE_OPAQUE + "\n"
    assert FAKE_OPAQUE not in secrets.redact("log: %s here" % FAKE_OPAQUE, [padded])
    assert FAKE_OPAQUE not in secrets.redact("log: %s" % padded, [FAKE_OPAQUE])


def test_redact_given_a_mapping_masks_values_and_keeps_names() -> None:
    """Names are not secrets, and a log with its names removed is unusable.

    Both halves asserted: the value gone, the name still there.
    """
    out = secrets.redact(
        "ACCOUNT_JWT_SECRET=%s" % FAKE_KEY,
        {"ACCOUNT_JWT_SECRET": FAKE_KEY},
    )
    assert FAKE_KEY not in out
    assert out == "ACCOUNT_JWT_SECRET=%s" % secrets.MASK


def test_redact_env_masks_only_the_secret_named_variables() -> None:
    """The wrapper's whole job, with the non-secret variable as the control."""
    environ = {
        "ACCOUNT_JWT_SECRET": FAKE_KEY,
        "REDIACC_ACCOUNT_SERVER": "http://localhost:4800",
    }
    out = secrets.redact_env(
        "server=http://localhost:4800 jwt=%s" % FAKE_KEY,
        environ,
    )
    assert FAKE_KEY not in out
    assert "http://localhost:4800" in out


# ---------------------------------------------------------------------------
# looks_secret -- against corpora, not against a table
# ---------------------------------------------------------------------------


def _rdc_sh_rulings() -> tuple[set[str], set[str]]:
    """The four names rdc.sh refuses to source, and the two it extracts.

    Harvested from the file so the corpus tracks the file. The caller asserts
    both sets are non-empty, which is what turns a broken harvest into a red
    instead of a vacuous pass.
    """
    text = paths.from_root("rdc.sh").read_text(encoding="utf-8")
    start = text.index("by grep. NEVER")
    end = text.index("grep + cut extracts")
    unsafe = set(re.findall(r"\b[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+\b", text[start:end]))
    safe = set(re.findall(r"grep -E '\^([A-Z][A-Z0-9_]*)='", text))
    return unsafe, safe


def test_looks_secret_agrees_with_the_ruling_rdc_sh_already_made() -> None:
    """An independent human ruling, in another file, for another reason.

    The two non-empty assertions and the disjointness assertion are the control:
    if the harvest regexes stop matching, both sets go empty and the two
    for-loops below iterate over nothing, which is exactly the shape that
    reports green while checking nothing.
    """
    unsafe, safe = _rdc_sh_rulings()
    assert unsafe, "the rdc.sh unsafe-name harvest matched nothing"
    assert safe, "the rdc.sh safe-name harvest matched nothing"
    assert not (unsafe & safe)
    for name in sorted(unsafe):
        assert secrets.looks_secret(name) is True, name
    for name in sorted(safe):
        assert secrets.looks_secret(name) is False, name


def _bws_names() -> set[str]:
    with open(paths.from_root(".ci/config/bws-secret-map.json"), encoding="utf-8") as handle:
        return set(json.load(handle)["secrets"])


def test_looks_secret_splits_the_bitwarden_corpus_in_both_directions() -> None:
    """The wider corpus, and the point is that it SPLITS.

    `.ci/config/bws-secret-map.json` is not a list of secrets -- it is a list of
    values kept in Bitwarden, and it deliberately holds public halves too
    (`..._PUBLIC_KEY`, `..._ENDPOINT`, `..._USERNAME`). So a classifier that
    answered True for everything would be as wrong as one that answered False,
    and both subsets being non-empty is the assertion that catches either.

    The suffix families below are derived from the corpus, not typed: each is
    filtered out of the live name list, and each filter must be non-empty before
    its members are checked.
    """
    names = _bws_names()
    assert names, "the bitwarden corpus is empty"

    hits = {name for name in names if secrets.looks_secret(name)}
    misses = names - hits
    assert hits, "the classifier called nothing in the corpus a secret"
    assert misses, "the classifier called everything in the corpus a secret"

    private = {n for n in names if n.endswith(("_PRIVATE_KEY", "_SECRET", "_TOKEN"))}
    assert private
    assert private <= hits, sorted(private - hits)

    public = {
        n
        for n in names
        if n.endswith(("_PUBLIC_KEY", "_ENDPOINT", "_USERNAME", "_REGION", "_HOST"))
    }
    assert public
    assert public <= misses, sorted(public & hits)


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        # The rows a SUBSTRING matcher gets wrong and a segment matcher does
        # not. These two are the whole reason `looks_secret` splits on "_":
        # "SIG" sits inside DESIGN and "KEY" inside KEYBOARD, and without them
        # a planted substring-matching defect passed this entire suite.
        ("DESIGN_DOC_URL", False),
        ("KEYBOARD_LAYOUT", False),
        # WEBAUTHN_RP_ID is here for a different rule: it ends in `_ID`, the
        # identifier half that .ci/config/bws-token-expiry.json rules public.
        ("WEBAUTHN_RP_ID", False),
        ("ACCOUNT_ED25519_PUBLIC_KEY", False),  # contains "KEY"
        ("CLOUDFLARE_R2_ACCESS_KEY_ID", False),  # the identifier half of a pair
        ("CLOUDFLARE_R2_SECRET_ACCESS_KEY", True),  # the private half
        ("ACCOUNT_ED25519_PRIVATE_KEY", True),
        ("PORT", False),
        ("DATABASE_PATH", False),
    ],
)
def test_looks_secret_on_the_shapes_a_substring_matcher_gets_wrong(
    name: str, expected: bool
) -> None:
    """A table only for the adversarial cases; the bulk lives in the corpora.

    Every row here is a pair with its own opposite somewhere in the table, so
    the parametrisation cannot pass by always answering one way.
    """
    assert secrets.looks_secret(name) is expected


# ---------------------------------------------------------------------------
# presence and report -- saying something without saying it
# ---------------------------------------------------------------------------


def test_presence_is_present_for_a_value_and_absent_for_nothing() -> None:
    assert secrets.presence(FAKE_KEY) == secrets.PRESENT
    assert secrets.presence(None) == secrets.ABSENT


def test_an_empty_value_is_absent() -> None:
    """`.ci/lib/bws-env.sh:100-104`, with a non-empty control beside it."""
    assert secrets.presence("") == secrets.ABSENT
    assert secrets.is_present("") is False
    assert secrets.is_present("x") is True


def test_report_names_every_variable_and_echoes_no_value() -> None:
    """The leak assertion, with the names as its positive control."""
    source = {"ACCOUNT_JWT_SECRET": FAKE_KEY, "BWS_ACCESS_TOKEN": "", "PORT": "3000"}
    lines = secrets.report(source)
    joined = "\n".join(lines)

    assert FAKE_KEY not in joined
    assert "3000" not in joined
    assert set(lines) == {
        "ACCOUNT_JWT_SECRET present",
        "BWS_ACCESS_TOKEN absent",
        "PORT present",
    }


def test_report_names_a_variable_that_is_missing_entirely() -> None:
    """Silence where the failure is, is the failure. Control: the present one."""
    lines = secrets.report({"HERE": "x"}, ["HERE", "GONE"])
    assert lines == ["GONE absent", "HERE present"]


def test_missing_returns_the_actionable_names_only() -> None:
    source = {"A": "x", "B": "", "C": None}
    assert secrets.missing(source, ["A", "B", "C", "D"]) == ["B", "C", "D"]


# ---------------------------------------------------------------------------
# fingerprint
# ---------------------------------------------------------------------------


def test_fingerprint_is_stable_distinguishing_and_never_the_value() -> None:
    one = secrets.fingerprint(FAKE_OPAQUE)
    assert one == secrets.fingerprint(FAKE_OPAQUE)
    assert one != secrets.fingerprint(FAKE_KEY)
    assert FAKE_OPAQUE not in one
    assert len(one) == secrets.FINGERPRINT_HEX_DIGITS
    assert re.fullmatch(r"[0-9a-f]+", one)


def test_fingerprint_of_nothing_is_empty_not_a_conspicuous_constant() -> None:
    """Otherwise every absent variable in a report carries the same digest.

    The control is that a real value still produces one.
    """
    assert secrets.fingerprint("") == ""
    assert secrets.fingerprint(FAKE_KEY) != ""


def test_fingerprint_matches_the_shell_sha256_it_has_to_interoperate_with() -> None:
    """A differential, because the corpus this must match was computed in bash.

    `scripts/dev/bws-map-refresh.py:67` and `.ci/config/bws-token-expiry.json`
    already carry digests of this exact shape. Recomputing the digest in Python
    here would only prove the function calls hashlib; `sha256sum` is an
    independent implementation.
    """
    value = "0.deadbeef-1111-2222-3333-444455556666"
    rc, out, err = diff.bash_streams(
        "printf '%%s' %s | sha256sum | cut -c1-%d" % (_q(value), secrets.FINGERPRINT_HEX_DIGITS),
        env=diff.env_for(),
    )
    assert rc == 0, err
    assert secrets.fingerprint(value) == out.strip()
    # And the control: an independent Python computation of the SAME thing, so a
    # sha256sum that started printing a filename would not silently agree.
    assert out.strip() == hashlib.sha256(value.encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# the argv dispatch -- names only, never values
# ---------------------------------------------------------------------------


def _module(script: str, environ=None):
    full = "PYTHONPATH=%s\nexport PYTHONPATH\n%s" % (_q(str(paths.ci_dir())), script)
    return diff.bash_streams(full, env=diff.env_for(**(environ or {})))


def test_redact_verb_masks_from_stdin_using_the_environment() -> None:
    rc, out, err = _module(
        "printf '%%s\\n' 'jwt=%s port=3000' | python3 -m rediacc_ci.core.secrets redact "
        "ACCOUNT_JWT_SECRET" % FAKE_KEY,
        {"ACCOUNT_JWT_SECRET": FAKE_KEY},
    )
    assert rc == 0, err
    assert FAKE_KEY not in out
    assert "port=3000" in out
    assert secrets.MASK in out


def test_redact_verb_treats_its_argument_as_a_name_and_never_as_a_value() -> None:
    """The design assertion: argv is world-readable, so it carries no values.

    Passing the secret itself as an argument must NOT mask it, because the
    argument is a variable name. A future convenience verb that accepted a value
    would fail here, which is the point.
    """
    rc, out, err = _module(
        "printf '%%s\\n' 'jwt=%s' | python3 -m rediacc_ci.core.secrets redact %s"
        % (FAKE_KEY, _q(FAKE_KEY)),
        {},
    )
    assert rc == 0, err
    assert FAKE_KEY in out, "the argument is a name; nothing was masked"
    assert secrets.MASK not in out


def test_report_verb_exits_one_when_a_name_is_absent_and_zero_when_all_present() -> None:
    """Both exit codes, because a gate branches on them."""
    rc, out, err = _module(
        "python3 -m rediacc_ci.core.secrets report ALPHA_TOKEN BETA_TOKEN",
        {"ALPHA_TOKEN": FAKE_OPAQUE},
    )
    assert rc == 1, err
    assert out.splitlines() == ["ALPHA_TOKEN present", "BETA_TOKEN absent"]
    assert FAKE_OPAQUE not in out

    rc, out, err = _module(
        "python3 -m rediacc_ci.core.secrets report ALPHA_TOKEN",
        {"ALPHA_TOKEN": FAKE_OPAQUE},
    )
    assert rc == 0, err
    assert out.splitlines() == ["ALPHA_TOKEN present"]


def test_fingerprint_verb_prints_a_digest_and_refuses_an_absent_name() -> None:
    rc, out, err = _module(
        "python3 -m rediacc_ci.core.secrets fingerprint ALPHA_TOKEN",
        {"ALPHA_TOKEN": FAKE_OPAQUE},
    )
    assert rc == 0, err
    assert out.strip() == secrets.fingerprint(FAKE_OPAQUE)
    assert FAKE_OPAQUE not in out

    rc, out, _err = _module("python3 -m rediacc_ci.core.secrets fingerprint ALPHA_TOKEN", {})
    assert rc == 1
    assert out.strip() == ""


def test_the_verbs_refuse_rather_than_guess() -> None:
    rc, _out, err = _module("python3 -m rediacc_ci.core.secrets nonsense")
    assert rc == 2
    assert "unknown verb" in err
    rc, _out, err = _module("python3 -m rediacc_ci.core.secrets report")
    assert rc == 2
    assert "at least one NAME" in err


# ---------------------------------------------------------------------------
# the two modules together, which is how they will actually be used
# ---------------------------------------------------------------------------


def test_an_env_file_can_be_reported_on_without_any_value_escaping(tmp_path) -> None:
    """End to end: read a .env, say what is in it, leak nothing.

    This is the shape `.ci/lib/account.sh` needs and cannot express today. The
    controls are the name assertions -- a report that said nothing at all would
    also leak nothing.
    """
    path = tmp_path / "dotenv"
    path.write_text(
        "ACCOUNT_ED25519_PRIVATE_KEY=%s\n"
        "ACCOUNT_X25519_PUBLIC_KEY=pubpubpub\n"
        "REDIACC_ACCOUNT_SERVER=http://localhost:4800\n"
        "ACCOUNT_JWT_SECRET=\n" % FAKE_KEY,
        encoding="utf-8",
    )
    pairs = env.read_pairs(path, missing_ok=False)
    lines = secrets.report(pairs)
    joined = "\n".join(lines)

    assert FAKE_KEY not in joined
    assert "pubpubpub" not in joined
    assert "ACCOUNT_ED25519_PRIVATE_KEY present" in lines
    assert "ACCOUNT_JWT_SECRET absent" in lines
    assert secrets.missing(pairs, pairs) == ["ACCOUNT_JWT_SECRET"]

    secret_names = {name for name in pairs if secrets.looks_secret(name)}
    assert secret_names == {"ACCOUNT_ED25519_PRIVATE_KEY", "ACCOUNT_JWT_SECRET"}
    masked = secrets.redact("dump: %s" % FAKE_KEY, {n: pairs[n] for n in secret_names})
    assert FAKE_KEY not in masked
    assert masked.startswith("dump: ")


def test_no_public_helper_here_hands_back_a_value() -> None:
    """The module's stated interface rule, asserted rather than reviewed.

    `rediacc_ci.core.env` has exactly one value-returning helper and its name
    says so. This module must have none at all, and a new one added without
    thinking fails here.
    """
    public = {name for name in dir(secrets) if not name.startswith("_")}
    assert not {name for name in public if "value" in name.lower()}
    assert "redact" in public, "the corpus of public names is real"


def test_the_module_never_writes_a_value_anywhere_it_prints() -> None:
    """A source-level control over the promise the docstring makes.

    Not a substitute for the behavioural cases above -- it is the backstop for
    the case they cannot cover, a NEW print statement added later. Every `print`
    in the module is checked to be printing a name, a line built by `report`, a
    digest or a usage string, never a bare value expression.
    """
    source = paths.from_root(".ci/rediacc_ci/core/secrets.py").read_text(encoding="utf-8")
    prints = re.findall(r"^\s*(?:print|sys\.stdout\.write)\((.*)$", source, re.MULTILINE)
    assert prints, "no print statements found; the scan is not looking at the module"
    for statement in prints:
        assert "value" not in statement, statement


def _q(value: str) -> str:
    return "'" + value.replace("'", "'\\''") + "'"
