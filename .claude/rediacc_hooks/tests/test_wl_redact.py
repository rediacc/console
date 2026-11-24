"""Credential shapes never reach the tracked worklist store, on ANY write path (finding #e44be537).

THE LEAK. agent/worklist/ace763dd.jsonl carried a full AWS access key id written by `compact` on 2026-11-10: the door redaction in `append_events` covered the verbs, but compaction, the legacy import and the markdown sync each serialised events with their own `json.dumps` and never passed it, so an item added before the door existed was re-published verbatim by every compaction. The
redactor's table also lagged check:ci-tracked-credentials, which reds on ASIA/AIDA/AROA ids, gho_/ghu_/ghs_/ghr_ tokens and Stripe `sk_live_` keys the store let through.

Every fixture is synthetic: the AWS id fixture is AWS's documented example (prefix AKIA plus IOSFODNN7EXAMPLE), and each token is built from a repeated alphabet at runtime.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest
import wl_core as C
import wl_store as S

if TYPE_CHECKING:
    import pathlib

ME = "ccccdddd"

AWS_ID = "AKIA" + "IOSFODNN7EXAMPLE"
ASIA_ID = "ASIA" + "IOSFODNN7EXAMPLE"
GH_TOKEN = "ghp_" + "Ab1" * 12
GHS_TOKEN = "ghs_" + "Zy9" * 12
STRIPE_KEY = "sk_live_" + "Qw7" * 8
PEM_BODY = "MIIEowIBAAKCAQEA" + "b3BlbnNzaC1rZXktdjEAAAAA" * 3
PEM = "-----BEGIN RSA PRIVATE KEY-----\n%s\n%s\n-----END RSA PRIVATE KEY-----" % (
    PEM_BODY,
    PEM_BODY,
)

# An ordinary commit sha, a sig8 and an item id: what evidence text really carries, and none of it may be touched.
CONTROL = (
    "(%s) landed e1a97886ac0f3c5d9b2e4a7f1c8d6b5a4e3f2a1b sig8 3f9a1c2e, rc=0, item 19b4818e, AKIA keys rotated"
    % ME
)


@pytest.fixture
def store(tmp_path, monkeypatch) -> pathlib.Path:
    root = tmp_path / "repo"
    (root / "agent").mkdir(parents=True)
    sd = tmp_path / "store"
    sd.mkdir()
    monkeypatch.setenv("WORKLIST_STORE_DIR", str(sd))
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(root))
    monkeypatch.setenv("TMPDIR", str(tmp_path / "tmp"))
    monkeypatch.setenv("WORKLIST_SESSION_ID", ME + "-0000-0000-0000-000000000000")
    (tmp_path / "tmp").mkdir()
    monkeypatch.chdir(root)
    S._BRANCH_CACHE.clear()
    S._GITDIR_CACHE.clear()
    S.clear_read_memo()
    return sd


def worklist() -> pathlib.Path:
    return C.worklist_for(C.project_start())


def stored(sd: pathlib.Path) -> str:
    return "".join(p.read_text() for p in sorted(sd.glob("*.jsonl")))


SECRETS = [
    ("aws", AWS_ID, "AKIA...MPLE"),
    ("asia", ASIA_ID, "ASIA...MPLE"),
    ("github", GH_TOKEN, "[redacted:github-token]"),
    ("github-server", GHS_TOKEN, "[redacted:github-token]"),
    ("stripe", STRIPE_KEY, "[redacted:stripe-key]"),
    ("pem", PEM, "[redacted:private-key]"),
]


@pytest.mark.parametrize(("label", "secret", "marker"), SECRETS, ids=[s[0] for s in SECRETS])
def test_add_update_tick_and_defer_never_store_the_secret(store, label, secret, marker):
    rid = S.add_item(worklist(), ME, "(%s) add holds %s here" % (ME, secret))
    S.update_item(worklist(), ME, rid, "update holds %s here" % secret)
    S.set_state(worklist(), ME, rid, "?", note="defer holds %s here DEFAULT: rotate it" % secret)
    S.set_state(worklist(), ME, rid, "x", note="tick holds %s here, rc=0" % secret)
    text = stored(store)
    assert secret not in text
    for fragment in (secret[:24], PEM_BODY[:24]):
        assert fragment not in text
    assert text.count(marker) >= 4, (label, text.count(marker))
    # Every line is still valid JSON after the substitution.
    for line in text.splitlines():
        json.loads(line)


def test_the_body_of_a_private_key_is_redacted_not_only_its_header(store):
    S.add_item(worklist(), ME, "(%s) key: %s" % (ME, PEM))
    text = stored(store)
    assert "PRIVATE KEY" not in text
    assert PEM_BODY[:16] not in text


def test_control_a_sha_a_sig8_and_an_item_id_stay_byte_identical(store):
    rid = S.add_item(worklist(), ME, CONTROL)
    S.update_item(worklist(), ME, rid, CONTROL)
    S.set_state(worklist(), ME, rid, "x", note=CONTROL)
    rec = S.load(worklist(), sync=False).by_id[rid]
    assert rec["text"].startswith(CONTROL)
    assert "[redacted" not in stored(store)
    assert stored(store).count("e1a97886ac0f3c5d9b2e4a7f1c8d6b5a4e3f2a1b") >= 3


@pytest.mark.usefixtures("store")
def test_control_a_pem_header_quoted_in_prose_keeps_the_prose():
    note = (
        "(%s) the -----BEGIN OPENSSH PRIVATE KEY----- header alone carries no key, see the docs"
        % ME
    )
    rid = S.add_item(worklist(), ME, note)
    text = S.load(worklist(), sync=False).by_id[rid]["text"]
    assert "header alone carries no key, see the docs" in text
    assert "PRIVATE KEY" not in text


def test_a_mangled_pem_header_with_many_dashes_still_loses_its_body():
    """31a95127.2: six or more closing dashes used to stop the match before the base64 body; five is the control."""
    for dashes in ("-----", "------", "-" * 12):
        text = "see -----BEGIN RSA PRIVATE KEY%s\n%s\n-----END RSA PRIVATE KEY----- done" % (
            dashes,
            PEM_BODY,
        )
        got = S.redact_secret_shapes(text)
        assert PEM_BODY[:16] not in got, dashes
        assert "[redacted:private-key]" in got


def test_compaction_redacts_a_legacy_line_written_before_the_door(store):
    """The 2026-11-10 path: an item already on disk unredacted is re-emitted by compact_store."""
    legacy = {
        "ev": "add",
        "id": "0badf00d",
        "at": "2026-11-01T00:00:00Z",
        "by": "eeeeffff",
        "s": " ",
        "o": "eeeeffff",
        "t": "(eeeeffff) bws holds %s and %s" % (AWS_ID, GH_TOKEN),
    }
    (store / "_legacy.jsonl").write_text(json.dumps(legacy) + "\n")
    assert AWS_ID in stored(store)
    S.compact_store(worklist(), me=ME)
    S.clear_read_memo()
    text = stored(store)
    assert AWS_ID not in text
    assert GH_TOKEN not in text
    assert "AKIA...MPLE" in text
    assert (
        S.load(worklist(), sync=False)
        .by_id["0badf00d"]["text"]
        .startswith("(eeeeffff) bws holds AKIA...MPLE")
    )


def test_every_sidecar_append_through_the_shared_writer_is_redacted(store):
    path = store / "epics.jsonl"
    S.append_store_lines(path, str(path) + ".lock", [{"ev": "epic", "t": "holds %s" % STRIPE_KEY}])
    assert STRIPE_KEY not in path.read_text()
    assert "[redacted:stripe-key]" in path.read_text()


def test_secret_kinds_in_names_the_kind_never_the_value():
    kinds = S.secret_kinds_in("a %s, a %s and a %s" % (AWS_ID, ASIA_ID, GH_TOKEN))
    assert kinds == ["github-token", "aws-key-id"]
    assert S.secret_kinds_in(CONTROL) == []


def test_secret_shapes_in_keeps_the_bare_pem_header_pattern_the_pre_push_scan_keys_on():
    # githooks.outgoing_secret_shapes compares a returned shape against its PEM_SHAPE to judge a header by its body.
    assert S.secret_shapes_in(PEM) == [r"-----BEGIN [A-Z ]*PRIVATE KEY"]
    assert S.secret_shapes_in(STRIPE_KEY)
    assert S.secret_shapes_in(CONTROL) == []


_B64 = "QUJDREVGR0hJSktMTU5PUFFSU1RVVldYWVphYmNkZWZnaGlqa2xtbm9w"


def test_a_pem_key_with_a_short_final_line_is_redacted_to_its_footer() -> None:
    text = (
        "k -----BEGIN RSA PRIVATE KEY-----\n%s\n%s\nQUJDREVGR0hJ\n-----END RSA PRIVATE KEY----- end"
        % (_B64, _B64)
    )
    assert S.redact_secret_shapes(text) == "k [redacted:private-key] end"


def test_a_pem_header_without_its_closing_dashes_loses_its_body_too() -> None:
    out = S.redact_secret_shapes("-----BEGIN RSA PRIVATE KEY\n%s\n%s\n" % (_B64, _B64))
    assert _B64 not in out
    assert "[redacted:private-key]" in out


def test_a_pem_header_with_a_partial_dash_run_loses_its_body_too() -> None:
    for dashes in ("-", "--", "---", "----"):
        out = S.redact_secret_shapes(
            "-----BEGIN RSA PRIVATE KEY%s\n%s\n%s\n" % (dashes, _B64, _B64)
        )
        assert _B64 not in out, dashes
        assert "[redacted:private-key]" in out


def test_control_prose_after_a_pem_header_is_kept() -> None:
    out = S.redact_secret_shapes("-----BEGIN RSA PRIVATE KEY----- appears in the docs")
    assert out == "[redacted:private-key] appears in the docs"
