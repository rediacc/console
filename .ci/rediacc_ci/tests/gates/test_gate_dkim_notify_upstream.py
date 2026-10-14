"""`scripts/gates/check-dkim-notify.ts` fails closed when no resolver answers (operator ruling 2026-10-14, "Extend to all seven").

`DKIM_MANIFEST_FILE` hands the gate a fixture rotation manifest and `DKIM_RESOLVERS` points its queries at a stub DNS server on 127.0.0.1 (`upstream_stub.py`), so the resolver calls, the answered-absent handling and the shared retry in `scripts/lib/upstream.ts` are the gate's real code path.

Proved, control first: the stub serving the DKIM TXT and the three MAIL FROM MX records is green; a resolver port nothing listens on is RED after three attempts with the reachability sentence; a SERVFAIL that persists is RED the same way; an NXDOMAIN for one MX is a DNS finding and NOT an outage, because a resolver that says a name does not exist has answered; a TXT whose key does not match the manifest's fingerprint is a finding.
"""

import base64
import hashlib
import json
import pathlib

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness
from rediacc_ci.tests.gates.upstream_stub import closed_port, stub_dns

VALIDATOR = paths.from_root("scripts", "gates", "check-dkim-notify.ts")
DOMAIN = "notify.test"
SELECTOR = "sel-1"
KEY = base64.b64encode(b"a stand-in public key, never a real one").decode()
REGIONS = {"eu": "eu-central-1", "us": "us-east-1", "asia": "ap-northeast-1"}


def manifest(directory: pathlib.Path, key: str = KEY) -> pathlib.Path:
    fingerprint = hashlib.sha256(base64.b64decode(key)).hexdigest()
    body = {
        "credentials": {
            "dkim": {
                "platform": "dkim-notify",
                "domain": DOMAIN,
                "versions": [{"id": SELECTOR, "name": fingerprint, "state": "active"}],
            }
        }
    }
    path = directory / "rotation-manifest.json"
    path.write_text(json.dumps(body), encoding="utf-8")
    return path


def records(**overrides: object) -> dict[tuple[str, str], object]:
    held: dict[tuple[str, str], object] = {
        ("%s._domainkey.%s" % (SELECTOR, DOMAIN), "TXT"): "v=DKIM1; k=rsa; p=%s" % KEY
    }
    for alias, region in REGIONS.items():
        held[("bounce-%s.%s" % (alias, DOMAIN), "MX")] = [
            (10, "feedback-smtp.%s.amazonses.com" % region)
        ]
    for name, value in overrides.items():
        held[(name.replace("_", "-") + "." + DOMAIN, "MX")] = value
    return held


def run_gate(gate, directory: pathlib.Path, resolver: str):
    if not VALIDATOR.is_file():
        gate.log_fail("subject under test is missing: %s" % paths.relative_to_root(VALIDATOR))
    npx = harness.require_tool(
        "npx", "install node; the subject is a TypeScript program driven through tsx"
    )
    return harness.run(
        [npx, "tsx", str(VALIDATOR)],
        cwd=paths.repo_root(),
        env={"DKIM_MANIFEST_FILE": str(manifest(directory)), "DKIM_RESOLVERS": resolver},
    )


def test_control_every_record_served_is_green(gate, tmp_path):
    with stub_dns(records()) as dns:
        result = run_gate(gate, tmp_path, dns.address)
        gate.assert_eq(len(dns.asked), 4, "one TXT and three MX questions reached the stub")
    gate.assert_exit(0, result, "the stub serving every record passes")
    gate.assert_contains(result.out, "OK: dkim-notify selector %s healthy" % SELECTOR, "green")
    gate.log_pass("the stub resolver, answering, is green")


def test_a_resolver_nothing_answers_on_is_red(gate, tmp_path):
    port = closed_port()
    result = run_gate(gate, tmp_path, "127.0.0.1:%d" % port)
    gate.assert_exit(1, result, "no resolver answering fails closed")
    gate.assert_contains(
        result.err, "4 DKIM notify DNS record(s) were NOT compared with upstream", "all four"
    )
    gate.assert_contains(
        result.err,
        "MX bounce-eu.%s -> DNS 127.0.0.1:%d " % (DOMAIN, port),
        "the finding names the question and the resolver",
    )
    gate.assert_contains(result.err, "after 3 attempt(s)", "the attempts are printed")
    gate.assert_contains(
        result.err,
        "UPSTREAM REACHABILITY FAILURE (127.0.0.1:%d), not a DNS misconfiguration" % port,
        "the finding says what kind of red this is",
    )
    gate.assert_not_contains(result.out, "OK: dkim-notify", "no green line is printed")
    gate.log_pass("an unreachable resolver is red after three attempts")


def test_a_persistent_servfail_is_red_as_an_outage(gate, tmp_path):
    with stub_dns(records(bounce_us="SERVFAIL")) as dns:
        result = run_gate(gate, tmp_path, dns.address)
        asked = sum(1 for name, _ in dns.asked if name == "bounce-us.%s" % DOMAIN)
    gate.assert_exit(1, result, "a resolver that keeps failing fails closed")
    gate.assert_eq(asked, 3, "SERVFAIL is asked three times")
    gate.assert_contains(result.err, "1 DKIM notify DNS record(s) were NOT compared", "one record")
    gate.assert_contains(result.err, "ESERVFAIL, after 3 attempt(s)", "the code is printed")
    gate.log_pass("SERVFAIL is an outage, red")


def test_nxdomain_is_a_dns_finding_not_an_outage(gate, tmp_path):
    held = records()
    del held[("bounce-asia.%s" % DOMAIN, "MX")]
    with stub_dns(held) as dns:
        result = run_gate(gate, tmp_path, dns.address)
    gate.assert_exit(1, result, "a missing MAIL FROM record fails")
    gate.assert_contains(result.err, "bounce-asia.%s: no MX records" % DOMAIN, "the finding")
    gate.assert_not_contains(result.err, "UPSTREAM REACHABILITY FAILURE", "NXDOMAIN is an answer")
    gate.log_pass("a name the resolver says does not exist is a finding in DNS")


def test_a_rotated_key_is_a_fingerprint_finding(gate, tmp_path):
    other = base64.b64encode(b"another key").decode()
    held = records()
    held[("%s._domainkey.%s" % (SELECTOR, DOMAIN), "TXT")] = "v=DKIM1; k=rsa; p=%s" % other
    with stub_dns(held) as dns:
        result = run_gate(gate, tmp_path, dns.address)
    gate.assert_exit(1, result, "a key that is not the manifest's fails")
    gate.assert_contains(result.err, "does not match manifest fingerprint", "the finding")
    gate.log_pass("the fingerprint check still bites through the stub")
