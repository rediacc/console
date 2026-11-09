"""Company secrets (PLAN-enterprise-isolation.md D2): generated, stored under opaque names, minted, pushed through `wrangler_argv`.

Every external call is a fake here: the store, the Cloudflare token mint, the IAM user mint, the wrangler push, and the HTTP and aws transports under the production adapters. Nothing reaches a real service.
"""

from __future__ import annotations

import base64
import hashlib
import json
import traceback
from typing import Any

import pytest

from rediacc_ci.deploy import set_account_worker_secrets
from rediacc_ci.enterprise import secrets as es
from rediacc_ci.quality import enterprise_leak

CID = "c0123456789abcdef"
NAME = "acme"
CF_ACCOUNT = "0" * 32

SHARED = {
    "ACCOUNT_ED25519_PUBLIC_KEY": "shared-ed25519-public-VALUE",
    "CLOUDFLARE_TURNSTILE_SECRET_KEY": "shared-turnstile-VALUE",
    "OBS_OTLP_CREDENTIALS": json.dumps({"user": "otlp-user-VALUE", "pass": "otlp-pass-VALUE"}),
    "AWS_SES_REGION": "eu-central-1",
    "AWS_SES_FROM": "noreply@notify.example",
    "AWS_SES_CONFIGURATION_SET": "",
    "ROOT_EMAIL": "root@example.test",
}

R2_TOKEN_ID = "r2-token-id-VALUE-0001"
R2_TOKEN_VALUE = "r2-token-secret-VALUE-0002"
SES_KEY_ID = "AKIASESKEYVALUE0003"
SES_SECRET = "ses-secret-access-key-VALUE-0004"


def company(**over):
    fields = {
        "id": CID,
        "name": NAME,
        "region": "eu",
        "cf_account_id": CF_ACCOUNT,
        "r2_jurisdiction": "eu",
    }
    fields.update(over)
    return es.Company(**fields)


class FakeStore:
    def __init__(self, initial=None, fail_on=None):
        self.data = dict(initial or {})
        self.created: list[str] = []
        self.reads: list[list[str]] = []
        self.fail_on = fail_on

    def read(self, names):
        self.reads.append(list(names))
        return {n: self.data[n] for n in names if n in self.data}

    def create(self, name, value):
        if name == self.fail_on:
            raise RuntimeError("store refused, value was %s" % value)
        assert name not in self.data, "a create over an existing entry"
        self.data[name] = value
        self.created.append(name)


class FakeMinter:
    def __init__(self, fail=False):
        self.r2_calls: list[tuple[str, str]] = []
        self.ses_calls: list[str] = []
        self.fail = fail

    def r2_bucket_token(self, token_name, bucket_resource):
        if self.fail:
            raise RuntimeError("mint failed, token %s" % R2_TOKEN_VALUE)
        self.r2_calls.append((token_name, bucket_resource))
        return R2_TOKEN_ID, R2_TOKEN_VALUE

    def ses_user(self, user_name):
        self.ses_calls.append(user_name)
        return SES_KEY_ID, SES_SECRET


class FakePush:
    def __init__(self, rc=0):
        self.calls: list[tuple[list[str], str]] = []
        self.rc = rc

    def __call__(self, argv, payload):
        self.calls.append((list(argv), payload))
        return self.rc


def counter_bytes():
    state = {"n": 0}

    def rand(n):
        state["n"] += 1
        return bytes([state["n"] % 256]) * n

    return rand


def run(store=None, minter=None, push=None, shared=None, comp=None):
    store = store if store is not None else FakeStore()
    minter = minter or FakeMinter()
    push = push or FakePush()
    report = es.provision(
        comp or company(),
        SHARED if shared is None else shared,
        store=store,
        minter=minter,
        push=push,
        random_bytes=counter_bytes(),
    )
    return report, store, minter, push


# --- opaque ids and store names -------------------------------------------------


def test_new_company_id_is_opaque_random_hex():
    a = es.new_company_id()
    b = es.new_company_id()
    assert es.COMPANY_ID.fullmatch(a)
    assert es.COMPANY_ID.fullmatch(b)
    assert a != b


def test_new_company_id_takes_no_name():
    # Derived from randomness only: a hash of a guessable company name could be reversed by a dictionary.
    assert es.new_company_id(random_bytes=lambda n: b"\xab" * n) == "c" + "ab" * 8


def test_store_name_is_opaque_and_carries_no_company_label():
    name = es.store_name(CID, "ACCOUNT_JWT_SECRET")
    assert name == CID + "_ACCOUNT_JWT_SECRET"
    assert NAME not in name


@pytest.mark.parametrize(
    "bad", ["acme", "C0123456789abcdef", "c01234", "c0123456789abcdeg", "c0123456789abcdef_x"]
)
def test_store_name_refuses_a_non_opaque_id(bad):
    with pytest.raises(es.SecretsError):
        es.store_name(bad, "ACCOUNT_JWT_SECRET")


def test_store_name_refuses_a_non_upper_snake_key():
    with pytest.raises(es.SecretsError):
        es.store_name(CID, "acme-jwt")


def test_store_names_match_the_leak_gate_opaque_shape():
    for key in es.STORED:
        assert enterprise_leak.OPAQUE_STORE.fullmatch(es.store_name(CID, key))


def test_company_refuses_a_reserved_or_malformed_name():
    with pytest.raises(es.SecretsError):
        company(name="eu")
    with pytest.raises(es.SecretsError):
        company(id="acme")


def test_external_names_carry_the_opaque_id_not_the_label():
    c = company()
    assert NAME not in es.r2_token_name(c)
    assert CID in es.r2_token_name(c)
    assert NAME not in es.ses_user_name(c)
    assert CID in es.ses_user_name(c)


# --- the required list ----------------------------------------------------------


def test_company_required_list_drops_the_shared_tier_only_names():
    for key in (
        "ACCOUNT_ED25519_PRIVATE_KEY",
        "FREE_LICENSE_HMAC_KEY",
        "STRIPE_SECRET_KEY",
        "STRIPE_WEBHOOK_SECRET",
        "SELLER_NAME",
    ):
        assert key not in es.COMPANY_REQUIRED
        assert key in es.FORBIDDEN


def test_every_payload_key_is_a_key_the_shared_pusher_knows():
    known = {k for k, _v, _s in set_account_worker_secrets.KEYS}
    assert set(es.PAYLOAD_KEYS) <= known


def test_company_required_covers_the_generated_and_minted_secrets():
    for key in (*es.GENERATED, *es.MINTED):
        assert key in es.COMPANY_REQUIRED


# --- provision: happy path ------------------------------------------------------


def test_provision_generates_stores_mints_and_pushes():
    report, store, minter, push = run()
    assert sorted(store.created) == sorted(es.store_name(CID, k) for k in es.STORED)
    assert minter.r2_calls == [
        (
            es.r2_token_name(company()),
            "com.cloudflare.edge.r2.bucket.%s_eu_backups-acme" % CF_ACCOUNT,
        )
    ]
    assert minter.ses_calls == [es.ses_user_name(company())]
    assert len(push.calls) == 1
    argv, payload = push.calls[0]
    assert argv == set_account_worker_secrets.wrangler_argv("account-acme")
    doc = json.loads(payload)
    assert set(doc) == set(es.PAYLOAD_KEYS)
    assert doc["ACCOUNT_BACKUP_S3_ACCESS_KEY_ID"] == R2_TOKEN_ID
    assert (
        doc["ACCOUNT_BACKUP_S3_SECRET_ACCESS_KEY"]
        == hashlib.sha256(R2_TOKEN_VALUE.encode()).hexdigest()
    )
    assert doc["AWS_SES_ACCESS_KEY_ID"] == SES_KEY_ID
    assert doc["AWS_SES_SECRET_ACCESS_KEY"] == SES_SECRET
    assert doc["ACCOUNT_BACKUP_S3_BUCKET"] == "backups-acme"
    assert (
        doc["ACCOUNT_BACKUP_S3_ENDPOINT"] == "https://%s.eu.r2.cloudflarestorage.com" % CF_ACCOUNT
    )
    assert doc["ACCOUNT_ED25519_PUBLIC_KEY"] == SHARED["ACCOUNT_ED25519_PUBLIC_KEY"]
    for key in es.FORBIDDEN:
        assert key not in doc
    assert report.company_id == CID
    assert sorted(report.created) == sorted(es.STORED)
    assert report.reused == []


def test_endpoint_without_jurisdiction():
    _r, _s, minter, push = run(comp=company(r2_jurisdiction=None))
    doc = json.loads(push.calls[0][1])
    assert doc["ACCOUNT_BACKUP_S3_ENDPOINT"] == "https://%s.r2.cloudflarestorage.com" % CF_ACCOUNT
    assert minter.r2_calls[0][1].endswith("_default_backups-acme")


def test_generated_values_meet_the_worker_schema_minimums():
    _r, _s, _m, push = run()
    doc = json.loads(push.calls[0][1])
    for key in (
        "ACCOUNT_JWT_SECRET",
        "ACCOUNT_CONFIG_SERVER_KEY",
        "ACCOUNT_SERVER_API_KEY",
        "ACCOUNT_BACKUP_STORE_KEK",
    ):
        assert len(doc[key]) >= 32
    priv = base64.b64decode(doc["ACCOUNT_X25519_PRIVATE_KEY"])
    pub = base64.b64decode(doc["ACCOUNT_X25519_PUBLIC_KEY"])
    assert priv[:16] == es.X25519_PKCS8_PREFIX
    assert len(priv) == 48
    assert pub[:12] == es.X25519_SPKI_PREFIX
    assert len(pub) == 44
    assert es.x25519_public(priv[16:]) == pub[12:]


def test_each_generated_secret_is_distinct():
    _r, _s, _m, push = run()
    doc = json.loads(push.calls[0][1])
    values = [
        doc[k]
        for k in (
            "ACCOUNT_JWT_SECRET",
            "ACCOUNT_CONFIG_SERVER_KEY",
            "ACCOUNT_SERVER_API_KEY",
            "ACCOUNT_BACKUP_STORE_KEK",
        )
    ]
    assert len(set(values)) == len(values)


def test_x25519_matches_the_rfc7748_vector():
    priv = bytes.fromhex("77076d0a7318a57d3c16c17251b26645df4c2f87ebc0992ab177fba51db92c2a")
    want = bytes.fromhex("8520f0098930a754748b7ddcb43ef75a0dbf3a0d26381af4eba4a98eaa9b4e6a")
    assert es.x25519_public(priv) == want


# --- provision: durability and resume -------------------------------------------


def full_store():
    _r, store, _m, _p = run()
    return FakeStore(store.data)


def test_a_rerun_reuses_every_stored_value_and_mints_nothing():
    first_store = full_store()
    before = dict(first_store.data)
    report, store, minter, push = run(store=first_store)
    assert store.created == []
    assert minter.r2_calls == []
    assert minter.ses_calls == []
    assert store.data == before
    assert sorted(report.reused) == sorted(es.STORED)
    doc = json.loads(push.calls[0][1])
    assert (
        doc["ACCOUNT_CONFIG_SERVER_KEY"] == before[es.store_name(CID, "ACCOUNT_CONFIG_SERVER_KEY")]
    )


def test_the_config_server_key_is_never_regenerated():
    key = es.store_name(CID, "ACCOUNT_CONFIG_SERVER_KEY")
    store = FakeStore({key: "k" * 40})
    _r, store, _m, push = run(store=store)
    assert key not in store.created
    assert json.loads(push.calls[0][1])["ACCOUNT_CONFIG_SERVER_KEY"] == "k" * 40


def test_values_are_stored_before_the_push(monkeypatch):
    order: list[str] = []
    store = FakeStore()
    real_create = store.create

    def create(name, value):
        order.append("store")
        real_create(name, value)

    monkeypatch.setattr(store, "create", create)

    def push(*_call):
        order.append("push")
        return 0

    run(store=store, push=push)
    assert order[-1] == "push"
    assert "push" not in order[:-1]


@pytest.mark.parametrize(
    ("entry", "raw"),
    [
        ("ACCOUNT_X25519_KEYPAIR", json.dumps({"ACCOUNT_X25519_PRIVATE_KEY": "half-VALUE"})),
        (
            "AWS_SES_KEYPAIR",
            json.dumps({"AWS_SES_ACCESS_KEY_ID": "half-VALUE", "AWS_SES_SECRET_ACCESS_KEY": ""}),
        ),
        ("ACCOUNT_BACKUP_S3_KEYPAIR", "half-VALUE"),
    ],
)
def test_a_pair_entry_missing_a_half_is_refused_and_nothing_is_minted(entry, raw):
    store, minter = FakeStore({es.store_name(CID, entry): raw}), FakeMinter()
    with pytest.raises(es.SecretsError) as err:
        run(store=store, minter=minter)
    assert "half-VALUE" not in _traceback_text(err.value)
    assert entry in str(err.value)
    assert store.created == []
    assert minter.r2_calls == []
    assert minter.ses_calls == []


def test_each_pair_is_one_store_entry_holding_both_halves():
    _r, store, _m, push = run()
    doc = json.loads(push.calls[0][1])
    for entry, halves in es.PAIRS.items():
        assert json.loads(store.data[es.store_name(CID, entry)]) == {k: doc[k] for k in halves}
        for half in halves:
            assert es.store_name(CID, half) not in store.data


# --- refusals -------------------------------------------------------------------


@pytest.mark.parametrize(
    "missing",
    [
        "ACCOUNT_ED25519_PUBLIC_KEY",
        "CLOUDFLARE_TURNSTILE_SECRET_KEY",
        "OBS_OTLP_CREDENTIALS",
        "ROOT_EMAIL",
        "AWS_SES_REGION",
    ],
)
def test_a_missing_required_name_is_refused(missing):
    shared = {k: v for k, v in SHARED.items() if k != missing}
    push = FakePush()
    with pytest.raises(es.SecretsError) as err:
        run(shared=shared, push=push)
    assert missing in str(err.value)
    assert push.calls == []


def test_an_empty_required_value_is_refused():
    shared = dict(SHARED, CLOUDFLARE_TURNSTILE_SECRET_KEY="")
    push = FakePush()
    with pytest.raises(es.SecretsError, match="CLOUDFLARE_TURNSTILE_SECRET_KEY"):
        run(shared=shared, push=push)
    assert push.calls == []


def test_missing_names_are_refused_before_anything_is_written_or_minted():
    shared = {k: v for k, v in SHARED.items() if k != "ROOT_EMAIL"}
    store, minter = FakeStore(), FakeMinter()
    with pytest.raises(es.SecretsError):
        run(shared=shared, store=store, minter=minter)
    assert store.created == []
    assert minter.r2_calls == []
    assert minter.ses_calls == []


@pytest.mark.parametrize(
    "forbidden",
    ["ACCOUNT_ED25519_PRIVATE_KEY", "FREE_LICENSE_HMAC_KEY", "STRIPE_SECRET_KEY", "SELLER_NAME"],
)
def test_a_forbidden_name_in_the_shared_set_is_refused(forbidden):
    shared = dict(SHARED, **{forbidden: "forbidden-VALUE"})
    push = FakePush()
    with pytest.raises(es.SecretsError) as err:
        run(shared=shared, push=push)
    assert forbidden in str(err.value)
    assert "forbidden-VALUE" not in str(err.value)
    assert push.calls == []


def test_an_unknown_shared_name_is_refused():
    with pytest.raises(es.SecretsError, match="SOMETHING_ELSE"):
        run(shared=dict(SHARED, SOMETHING_ELSE="x"))


def test_a_company_owned_name_in_the_shared_set_is_refused():
    with pytest.raises(es.SecretsError, match="ACCOUNT_JWT_SECRET"):
        run(shared=dict(SHARED, ACCOUNT_JWT_SECRET="j" * 40))


def test_a_malformed_otlp_value_is_refused_without_echoing_it():
    with pytest.raises(es.SecretsError) as err:
        run(shared=dict(SHARED, OBS_OTLP_CREDENTIALS="dXNlcjpwYXNz-VALUE"))
    assert "OBS_OTLP_CREDENTIALS" in str(err.value)
    assert "dXNlcjpwYXNz-VALUE" not in str(err.value)


def test_a_failed_push_is_refused_by_opaque_id():
    with pytest.raises(es.SecretsError) as err:
        run(push=FakePush(rc=3))
    assert CID in str(err.value)
    assert "3" in str(err.value)
    assert NAME not in str(err.value)


def test_a_failing_seam_does_not_leak_its_message():
    with pytest.raises(es.SecretsError) as err:
        run(minter=FakeMinter(fail=True))
    text = str(err.value)
    assert R2_TOKEN_VALUE not in text
    assert err.value.__cause__ is None
    assert err.value.__context__ is None


def test_a_failing_store_create_does_not_leak_the_value():
    store = FakeStore(fail_on=es.store_name(CID, "ACCOUNT_JWT_SECRET"))
    with pytest.raises(es.SecretsError) as err:
        run(store=store)
    assert "value was" not in str(err.value)
    assert err.value.__cause__ is None
    assert err.value.__context__ is None


# --- no value in argv or output -------------------------------------------------


def all_values(store, push):
    doc = json.loads(push.calls[0][1])
    secret_keys = (
        set(es.GENERATED)
        | set(es.MINTED)
        | {"ACCOUNT_ED25519_PUBLIC_KEY", "CLOUDFLARE_TURNSTILE_SECRET_KEY", "OBS_OTLP_CREDENTIALS"}
    )
    values = {doc[k] for k in secret_keys}
    values |= set(store.data.values())
    values |= {R2_TOKEN_VALUE}
    return {v for v in values if v}


def test_no_value_reaches_argv():
    _r, store, minter, push = run()
    argv = push.calls[0][0]
    joined = "\0".join(argv)
    for value in all_values(store, push):
        assert value not in joined
    for name, resource in minter.r2_calls:
        for value in all_values(store, push):
            assert value not in name
            assert value not in resource


def test_no_value_reaches_captured_output_or_the_report(capsys):
    report, store, _m, push = run()
    for line in report.lines():
        print(line)
    out, err = capsys.readouterr()
    assert out
    assert CID in out
    for value in all_values(store, push):
        assert value not in out
        assert value not in err
    assert NAME not in out
    assert NAME not in err
    assert repr(report).count(R2_TOKEN_VALUE) == 0


def test_shared_from_env_takes_the_region_suffixed_otlp():
    env = {
        "ACCOUNT_ED25519_PUBLIC_KEY": "p",
        "CLOUDFLARE_TURNSTILE_SECRET_KEY": "t",
        "OBS_OTLP_CREDENTIALS_EU": "eu-otlp",
        "OBS_OTLP_CREDENTIALS_US": "us-otlp",
        "AWS_SES_REGION": "eu-central-1",
        "ROOT_EMAIL": "r@example.test",
        "FREE_LICENSE_HMAC_KEY": "never-taken",
    }
    shared = es.shared_from_env(env, "EU")
    assert shared["OBS_OTLP_CREDENTIALS"] == "eu-otlp"
    assert "FREE_LICENSE_HMAC_KEY" not in shared
    assert set(shared) <= set(es.SHARED)


# --- production adapters, driven through fake transports ------------------------


def test_bws_store_reads_only_its_project_and_writes_on_stdin_shaped_requests():
    rows = [
        {"key": CID + "_ACCOUNT_JWT_SECRET", "value": "j-VALUE", "projectId": "proj-ent"},
        {"key": CID + "_ACCOUNT_SERVER_API_KEY", "value": "other", "projectId": "proj-shared"},
    ]
    requests: list[dict] = []

    def writer(request):
        requests.append(request)

    store = es.BwsStore("proj-ent", list_rows=lambda: rows, write=writer)
    assert store.read([CID + "_ACCOUNT_JWT_SECRET", CID + "_ACCOUNT_SERVER_API_KEY"]) == {
        CID + "_ACCOUNT_JWT_SECRET": "j-VALUE"
    }
    store.create(CID + "_ACCOUNT_SERVER_API_KEY", "new-VALUE")
    assert requests == [
        {
            "op": "create",
            "key": CID + "_ACCOUNT_SERVER_API_KEY",
            "value": "new-VALUE",
            "note": es.STORE_NOTE,
            "projectIds": ["proj-ent"],
        }
    ]
    assert NAME not in es.STORE_NOTE


def test_bws_store_refuses_a_missing_project_and_a_non_opaque_name():
    with pytest.raises(es.SecretsError):
        es.BwsStore("", list_rows=list, write=lambda _r: None)
    store = es.BwsStore("p", list_rows=list, write=lambda _r: None)
    with pytest.raises(es.SecretsError):
        store.create("ACME_JWT", "v")


def test_bws_store_write_failure_is_reported_without_the_value():
    store = es.BwsStore("p", list_rows=list, write=lambda _r: "rc=1: the writer failed")
    with pytest.raises(es.SecretsError) as err:
        store.create(CID + "_ACCOUNT_JWT_SECRET", "secret-VALUE")
    assert "secret-VALUE" not in str(err.value)


def test_cloudflare_minter_builds_a_bucket_scoped_policy():
    calls: list[tuple[str, str, str | None]] = []

    def http(method, path, body=None):
        calls.append((method, path, body))
        if path == "/user/tokens/permission_groups":
            return {
                "result": [
                    {
                        "id": "g-read",
                        "name": "Workers R2 Storage Bucket Item Read",
                        "scopes": ["com.cloudflare.edge.r2.bucket"],
                    },
                    {
                        "id": "g-write",
                        "name": "Workers R2 Storage Bucket Item Write",
                        "scopes": ["com.cloudflare.edge.r2.bucket"],
                    },
                    {
                        "id": "g-acct",
                        "name": "Workers R2 Storage Write",
                        "scopes": ["com.cloudflare.api.account"],
                    },
                ]
            }
        if method == "GET":
            return {"success": True, "result": [], "result_info": {"total_pages": 1}}
        return {"success": True, "result": {"id": "tok-id", "value": "tok-VALUE"}}

    minter = es.CloudflareMinter(http=http)
    token_id, value = minter.r2_bucket_token(
        "enterprise-%s-backups" % CID, "com.cloudflare.edge.r2.bucket.x_eu_b"
    )
    assert (token_id, value) == ("tok-id", "tok-VALUE")
    method, path, body = calls[-1]
    assert (method, path) == ("POST", "/user/tokens")
    assert body is not None
    payload = json.loads(body)
    assert payload["name"] == "enterprise-%s-backups" % CID
    assert payload["policies"] == [
        {
            "effect": "allow",
            "resources": {"com.cloudflare.edge.r2.bucket.x_eu_b": "*"},
            "permission_groups": [{"id": "g-read"}, {"id": "g-write"}],
        }
    ]


def test_cloudflare_minter_failure_names_no_value():
    def http(method, path, _body=None):
        if method == "GET" and path.startswith("/user/tokens?"):
            return {"success": True, "result": []}
        if path == "/user/tokens/permission_groups":
            return {
                "result": [
                    {
                        "id": "a",
                        "name": "Workers R2 Storage Bucket Item Read",
                        "scopes": ["com.cloudflare.edge.r2.bucket"],
                    },
                    {
                        "id": "b",
                        "name": "Workers R2 Storage Bucket Item Write",
                        "scopes": ["com.cloudflare.edge.r2.bucket"],
                    },
                ]
            }
        return {"success": False, "errors": [{"message": "nope"}]}

    with pytest.raises(es.SecretsError):
        es.CloudflareMinter(http=http).r2_bucket_token("t", "r")


def test_iam_minter_creates_a_send_only_user_with_no_secret_in_argv():
    iam = FakeIam()
    minter = es.IamMinter(aws=iam, ses_region="eu-central-1", from_domain="notify.example")
    assert minter.ses_user("rediacc-ses-%s" % CID) == ("AKIA0001", "iam-secret-VALUE")
    calls = iam.calls
    verbs = [c[2] for c in calls]
    assert verbs == [
        "get-user",
        "create-user",
        "put-user-policy",
        "list-access-keys",
        "create-access-key",
    ]
    for argv in calls:
        assert "iam-secret-VALUE" not in "\0".join(argv)
    put = calls[verbs.index("put-user-policy")]
    policy = json.loads(put[put.index("--policy-document") + 1])
    stmt = policy["Statement"][0]
    assert stmt["Action"] == ["ses:SendEmail", "ses:SendRawEmail"]
    assert stmt["Condition"]["StringEquals"]["aws:RequestedRegion"] == "eu-central-1"


def test_iam_minter_failure_withholds_aws_output():
    def aws(_args):
        return 254, "An error occurred ... secret-ish-VALUE"

    with pytest.raises(es.SecretsError) as err:
        es.IamMinter(aws=aws, ses_region="eu-central-1", from_domain="d").ses_user("u")
    assert "secret-ish-VALUE" not in str(err.value)


def test_wrangler_push_captures_output_and_keeps_payload_on_stdin():
    seen: dict = {}

    def runner(argv, **kw):
        seen["argv"] = argv
        seen.update(kw)

        class P:
            returncode = 0

        return P()

    rc = es.wrangler_push(
        ["npx", "wrangler", "secret", "bulk", "--name", "w"], '{"K":"v-VALUE"}', runner=runner
    )
    assert rc == 0
    assert seen["input"] == '{"K":"v-VALUE"}'
    assert seen["capture_output"] is True
    assert "v-VALUE" not in "\0".join(seen["argv"])


# --- review 57f7d3fa: findings 1-5 ----------------------------------------------


def _traceback_text(exc):
    return "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))


@pytest.mark.parametrize("where", ["minter", "store"])
def test_a_failing_seam_leaves_no_cause_no_context_and_no_value_in_the_traceback(where):
    # 57f7d3fa.1: `from None` inside the except block still keeps the seam exception as __context__.
    kw: dict[str, Any]
    if where == "minter":
        kw = {"minter": FakeMinter(fail=True)}
        leaked = R2_TOKEN_VALUE
    else:
        kw = {"store": FakeStore(fail_on=es.store_name(CID, "ACCOUNT_JWT_SECRET"))}
        leaked = "value was"
    with pytest.raises(es.SecretsError) as err:
        run(**kw)
    assert err.value.__cause__ is None
    assert err.value.__context__ is None
    assert leaked not in _traceback_text(err.value)


class FakeIam:
    """A stateful `aws iam` transport: users and their access keys survive between runs."""

    def __init__(self, fail_verb=None):
        self.users: dict[str, list[str]] = {}
        self.calls: list[list[str]] = []
        self.fail_verb = fail_verb
        self.minted = 0

    def __call__(self, args):
        self.calls.append(list(args))
        verb = args[2]
        user = args[args.index("--user-name") + 1]
        if verb == self.fail_verb:
            return 254, "boom"
        if verb == "get-user":
            if user not in self.users:
                return 254, "NoSuchEntity"
            return 0, json.dumps({"User": {"UserName": user}})
        if verb == "create-user":
            if user in self.users:
                return 254, "EntityAlreadyExists"
            self.users[user] = []
            return 0, "{}"
        if verb == "put-user-policy":
            return (0, "") if user in self.users else (254, "NoSuchEntity")
        if verb == "list-access-keys":
            keys = [{"AccessKeyId": k} for k in self.users[user]]
            return 0, json.dumps({"AccessKeyMetadata": keys})
        if verb == "delete-access-key":
            self.users[user].remove(args[args.index("--access-key-id") + 1])
            return 0, ""
        if verb == "create-access-key":
            if len(self.users[user]) >= 2:
                return 254, "LimitExceeded"
            self.minted += 1
            key_id = "AKIA%04d" % self.minted
            self.users[user].append(key_id)
            return 0, json.dumps(
                {"AccessKey": {"AccessKeyId": key_id, "SecretAccessKey": "iam-secret-VALUE"}}
            )
        raise AssertionError("unexpected aws verb %s" % verb)


def test_iam_minter_resumes_after_create_user_succeeded_and_a_later_step_failed():
    # 57f7d3fa.2: a rerun must continue from the user the first run created.
    iam = FakeIam(fail_verb="create-access-key")
    minter = es.IamMinter(aws=iam, ses_region="eu-central-1", from_domain="notify.example")
    with pytest.raises(es.SecretsError):
        minter.ses_user("rediacc-ses-%s" % CID)
    assert "rediacc-ses-%s" % CID in iam.users
    iam.fail_verb = None
    key_id, secret = minter.ses_user("rediacc-ses-%s" % CID)
    assert (key_id, secret) == ("AKIA0001", "iam-secret-VALUE")
    assert [c[2] for c in iam.calls].count("create-user") == 1


def test_iam_minter_deletes_an_orphaned_access_key_before_minting():
    # A key the store never received is unrecoverable; it is revoked rather than left live.
    iam = FakeIam()
    user = "rediacc-ses-%s" % CID
    iam.users[user] = ["AKIAORPHAN1", "AKIAORPHAN2"]
    minter = es.IamMinter(aws=iam, ses_region="eu-central-1", from_domain="notify.example")
    key_id, _secret = minter.ses_user(user)
    assert iam.users[user] == [key_id]
    for argv in iam.calls:
        assert "iam-secret-VALUE" not in "\0".join(argv)


class CrashingStore(FakeStore):
    """Fails the `nth` create whose name contains `marker`, once."""

    def __init__(self, marker, nth):
        super().__init__()
        self.marker = marker
        self.nth = nth
        self.seen = 0

    def create(self, name, value):
        if self.marker in name:
            self.seen += 1
            if self.seen == self.nth:
                raise RuntimeError("crash while storing")
        super().create(name, value)


@pytest.mark.parametrize(
    ("marker", "pair_key", "halves"),
    [
        ("SES", "AWS_SES_KEYPAIR", es.SES_PAIR),
        ("BACKUP_S3", "ACCOUNT_BACKUP_S3_KEYPAIR", es.BACKUP_PAIR),
        ("X25519", "ACCOUNT_X25519_KEYPAIR", es.X25519_PAIR),
    ],
)
@pytest.mark.parametrize("nth", [1, 2])
def test_a_crash_while_storing_a_pair_leaves_a_store_the_rerun_completes(
    marker, pair_key, halves, nth
):
    # 57f7d3fa.3 and 57f7d3fa.4: two separate creates left a half pair every later run refused.
    store = CrashingStore(marker, nth)
    if nth == 1:
        with pytest.raises(es.SecretsError):
            run(store=store)
    else:
        run(store=store)  # one write per pair, so there is no second write to crash on
    store.seen = -100  # the crash is spent; the rerun stores normally
    _r, store, _m, push = run(store=store)
    entry = es.store_name(CID, pair_key)
    assert entry in store.data
    held = json.loads(store.data[entry])
    assert set(held) == set(halves)
    assert all(held.values())
    for half in halves:
        assert es.store_name(CID, half) not in store.data
    doc = json.loads(push.calls[0][1])
    assert {k: doc[k] for k in halves} == held


def test_cloudflare_minter_revokes_an_orphaned_same_named_token_before_minting():
    calls: list[tuple[str, str, str | None]] = []
    groups = [
        {
            "id": "g-read",
            "name": "Workers R2 Storage Bucket Item Read",
            "scopes": ["com.cloudflare.edge.r2.bucket"],
        },
        {
            "id": "g-write",
            "name": "Workers R2 Storage Bucket Item Write",
            "scopes": ["com.cloudflare.edge.r2.bucket"],
        },
    ]
    name = "enterprise-%s-backups" % CID

    def http(method, path, body=None):
        calls.append((method, path, body))
        if path == "/user/tokens/permission_groups":
            return {"result": groups}
        if method == "GET" and path.startswith("/user/tokens"):
            return {
                "result": [
                    {"id": "tok-orphan", "name": name},
                    {"id": "tok-other", "name": "enterprise-c1111111111111111-backups"},
                ],
                "result_info": {"page": 1, "total_pages": 1},
            }
        if method == "DELETE":
            return {"success": True, "result": {"id": path.rsplit("/", 1)[1]}}
        return {"success": True, "result": {"id": "tok-new", "value": "tok-VALUE"}}

    assert es.CloudflareMinter(http=http).r2_bucket_token(name, "res") == ("tok-new", "tok-VALUE")
    deletes = [p for m, p, _b in calls if m == "DELETE"]
    assert deletes == ["/user/tokens/tok-orphan"]
    assert calls[-1][:2] == ("POST", "/user/tokens")


@pytest.mark.parametrize(
    "otlp",
    [
        "dXNlcjpwYXNz-VALUE",
        json.dumps({"user": "u"}),
        json.dumps(["user", "pass"]),
        json.dumps({"user": 1, "pass": "p"}),
    ],
)
def test_a_malformed_otlp_value_mints_and_writes_nothing(otlp):
    # 57f7d3fa.5: the shape was checked only after the mint and the store writes.
    store, minter, push = FakeStore(), FakeMinter(), FakePush()
    with pytest.raises(es.SecretsError, match="OBS_OTLP_CREDENTIALS"):
        run(shared=dict(SHARED, OBS_OTLP_CREDENTIALS=otlp), store=store, minter=minter, push=push)
    assert store.created == []
    assert store.reads == []
    assert minter.r2_calls == []
    assert minter.ses_calls == []
    assert push.calls == []
