"""Limit the bench hosts to a short list of allowed IP addresses, kept as ONE Cloudflare WAF custom rule.

    PYTHONPATH=.ci python3 -m rediacc_ci.ops.bench_access add-current   # allow this machine's public IP
    PYTHONPATH=.ci python3 -m rediacc_ci.ops.bench_access list
    PYTHONPATH=.ci python3 -m rediacc_ci.ops.bench_access add <ip>
    PYTHONPATH=.ci python3 -m rediacc_ci.ops.bench_access remove <ip>
    PYTHONPATH=.ci python3 -m rediacc_ci.ops.bench_access clear         # empty the list, enforcement stays on
    PYTHONPATH=.ci python3 -m rediacc_ci.ops.bench_access disable       # delete the rule, bench is open again

WHO RUNS IT. An operator or an AI session whose bench request answers Cloudflare's own 403 page (the rule carries no custom body; deploy_bench prints HINT on that 403). The caller's IP changes (it rotates nightly), so the fix is this one command; no ticket and no operator step.

THE MECHANISM: a zone WAF custom rule (Cloudflare Rulesets API, phase `http_request_firewall_custom`, action `block`). The rediacc.com zone is on the Free plan (read live 2026-10-26: `plan.name` is `Free Website`), and Cloudflare's WAF custom rules page lists, for Free: "Number of rules 5 ... Supported actions All except Log" (https://developers.cloudflare.com/waf/custom-rules/), so a Free zone has a block action and room for the one rule this script owns. A custom block response is NOT available on Free: the first live write on 2026-10-26 was refused with `not entitled to use a custom response`, so a blocked request gets Cloudflare's own 403 page, and the fix is named by the tooling instead (this script's HINT, printed by deploy_bench on a 403, and the bench notes in .claude/agents/account-dev.md and docs/agent-reference/local-env.md). The rule is found by its description, so other custom rules on the zone are never touched. IP Access Rules were rejected: they match the whole account or zone, not two hostnames.

WHAT THE RULE BLOCKS. Every request to a bench host (the route patterns of `workers/*/wrangler.bench.toml`: bench.rediacc.com and proxy.bench.rediacc.com) whose source IP is not in the list, EXCEPT `GET` of the two health paths (`/account/api/v1/health`, `/v1/health`). The exemption is what keeps the automated callers working: `telemetry-probe.yml` (six-hourly, GitHub runner egress, a different IP every run) probes exactly those two paths, and a health answer discloses nothing but liveness. The proxy Worker's own calls to the account Worker are service bindings (`workers/proxy/wrangler.bench.toml` ACCOUNT and ISSUER), which never pass the zone's edge rules. Every other caller (deploy_bench, deploy_proxy's smoke past /v1/health, console_executor, the CLI against `--config bench`, the portal in a browser) is an operator or an AI session on its own machine and runs `add-current` first.

EXPIRY. Every address is allowed for `TTL_DAYS` (7) days from the run that added it. The add time lives in the rule's own `description` (`RULE_DESCRIPTION | added ip=<UTC time> ...`), so the Cloudflare rule is the only store and no local state exists. Every mutating run first drops the addresses older than 7 days (the CLI's clock, UTC), then applies its verb; re-adding a live address refreshes its stamp; the 5-address cap counts what is left after the drop. A LEGACY address (in the expression but with no stamp, written before expiry existed or edited by hand) is treated as EXPIRED and dropped by the next mutating run, never stamped now, so an unknown age cannot become a permanent allowance. `list` is read-only and marks such entries. The expiry is enforced when the script runs, not by Cloudflare: an address stays in the rule past 7 days until the next run (the nightly `add-current` that the rotating IP already needs).

THE LIST. At most `MAX_IPS` (5) single addresses, oldest first in the rule's expression, which is the record: `add-current` appends the caller's address (re-adding one moves it to the end) and evicts from the front when the list is full. With no rule yet, the first `add` creates it holding the caller's own address, so the first enforcement cannot lock the caller out. `add-current` asks Cloudflare's own trace endpoint for the IPv4 and the IPv6 address it sees (one family may be unreachable and is then skipped), so a dual-stack host is allowed in whichever family curl or node picks.

AUTH. `cf_auth.resolve_scoped("bench-access", zone_id=ZONE_ID)`: a supplied `CF_MANAGEMENT_TOKEN`, or a token minted from the Global API Key with `Zone WAF Write` on the rediacc.com zone only (plus the user-scoped API Tokens pair its self-destruct needs), deleted at the end of the run. The script re-runs itself under the `bench-access` Bitwarden profile (`CF_GLOBAL_API_KEY`, `CF_EMAIL`) when neither is in the environment. The credential reaches curl on its stdin (`rediacc_ci.core.curl_stdin`), never on argv, and is never printed.
"""

from __future__ import annotations

import datetime
import ipaddress
import json
import os
import re
import subprocess
import sys
import time
import tomllib
import typing
import urllib.error

from rediacc_ci import log, paths
from rediacc_ci.core import https
from rediacc_ci.ops import apply_cf_redirect_rules, cf_auth

ZONE_ID = apply_cf_redirect_rules.ZONE_ID
PHASE = "http_request_firewall_custom"
PROFILE = "bench-access"
MAX_IPS = 5
TTL_DAYS = 7
TTL = datetime.timedelta(days=TTL_DAYS)
STAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
STAMP_MARK = " | added "
# The rule is found by this description; nothing else on the zone is read or written.
RULE_DESCRIPTION = "rediacc bench IP allowlist (rediacc_ci.ops.bench_access)"
# GET of these paths is never blocked: telemetry-probe.yml probes them from runners with no fixed IP.
EXEMPT_PATHS = ("/account/api/v1/health", "/v1/health")
COMMAND = "PYTHONPATH=.ci python3 -m rediacc_ci.ops.bench_access add-current"
HINT = "bench is IP-restricted; run " + COMMAND
# Cloudflare's own view of the caller's address, one literal per family (the IP literal needs no DNS).
TRACE_URLS = ("https://1.1.1.1/cdn-cgi/trace", "https://[2606:4700:4700::1111]/cdn-cgi/trace")
TRACE_TIMEOUT_S = 8.0
# A freshly minted token answers `Authentication error` (code 10000) for a few seconds.
AUTH_RETRIES = 15
AUTH_RETRY_S = 2.0
ENTRYPOINT_MISSING = 10003
Entry = tuple[str, datetime.datetime | None]
IP_SET = re.compile(r"ip\.src in \{([^}]*)\}")


class AccessError(Exception):
    """The allowlist could not be read or changed; the message is printed and the run exits 1."""


class Api(typing.Protocol):
    def request(self, method: str, path: str, body: dict | None = None) -> dict: ...


def bench_hosts(root=None) -> list[str]:
    """Every custom-domain route pattern in `workers/*/wrangler.bench.toml`, sorted."""
    base = root or paths.repo_root()
    hosts: set[str] = set()
    for config in sorted((base / "workers").glob("*/wrangler.bench.toml")):
        with open(config, "rb") as fh:
            conf = tomllib.load(fh)
        for route in conf.get("routes", []):
            pattern = route if isinstance(route, str) else route.get("pattern", "")
            if pattern:
                hosts.add(pattern)
    if not hosts:
        raise AccessError("no route pattern found in workers/*/wrangler.bench.toml")
    return sorted(hosts)


def normalize_ip(text: str) -> str:
    """The canonical text of one IPv4 or IPv6 address; AccessError for anything else (a CIDR included)."""
    try:
        return str(ipaddress.ip_address(text.strip()))
    except ValueError:
        raise AccessError("not a single IP address: %r" % text) from None


def expression(hosts: list[str], ips: list[str]) -> str:
    """The rule expression: a bench host, a source outside `ips`, and not a GET of an exempt path. With no IPs everything but the exempt GET is blocked."""
    host_set = " ".join('"%s"' % h for h in hosts)
    path_set = " ".join('"%s"' % p for p in EXEMPT_PATHS)
    parts = ["http.host in {%s}" % host_set]
    if ips:
        parts.append("not ip.src in {%s}" % " ".join(ips))
    parts.append('not (http.request.method eq "GET" and http.request.uri.path in {%s})' % path_set)
    return "(" + ") and (".join(parts) + ")"


def ips_of(rule_expression: str) -> list[str]:
    """The allowed IPs of a rule this script wrote, in stored order (oldest first)."""
    found = IP_SET.search(rule_expression)
    return found.group(1).split() if found else []


def describe(entries: list[Entry]) -> str:
    """The rule description: the fixed marker plus `ip=<UTC time>` per address, in list order."""
    stamped = ["%s=%s" % (ip, at.strftime(STAMP_FORMAT)) for ip, at in entries if at is not None]
    return RULE_DESCRIPTION + (STAMP_MARK + " ".join(stamped) if stamped else "")


def stamps_of(description: str) -> dict[str, datetime.datetime]:
    """The `ip -> add time` pairs a description carries; a malformed pair is skipped (that address is then legacy)."""
    _, _, tail = description.partition(STAMP_MARK)
    found: dict[str, datetime.datetime] = {}
    for pair in tail.split():
        ip, _, text = pair.rpartition("=")
        try:
            found[normalize_ip(ip)] = datetime.datetime.strptime(text, STAMP_FORMAT).replace(
                tzinfo=datetime.UTC
            )
        except (AccessError, ValueError):
            continue
    return found


def entries_of(rule: dict) -> list[Entry]:
    """The (ip, add time or None) pairs of a rule this script wrote, in stored order."""
    stamps = stamps_of(str(rule.get("description", "")))
    return [(ip, stamps.get(ip)) for ip in ips_of(str(rule.get("expression", "")))]


def is_ours(rule: dict) -> bool:
    return str(rule.get("description", "")).startswith(RULE_DESCRIPTION)


def live_entries(entries: list[Entry], now: datetime.datetime) -> tuple[list[Entry], list[str]]:
    """(the entries younger than `TTL`, the dropped addresses); an entry with no stamp is legacy and dropped."""
    kept = [(ip, at) for ip, at in entries if at is not None and now - at < TTL]
    kept_ips = {ip for ip, _ in kept}
    return kept, [ip for ip, _ in entries if ip not in kept_ips]


def rule_body(hosts: list[str], entries: list[Entry]) -> dict:
    ips = [ip for ip, _ in entries]
    return {
        "description": describe(entries),
        "enabled": True,
        "action": "block",
        "expression": expression(hosts, ips),
    }


def with_ip(
    current: list[Entry], new: str, now: datetime.datetime, limit: int = MAX_IPS
) -> tuple[list[Entry], list[str]]:
    """(the list after adding `new` stamped `now`, the addresses evicted): a repeat moves to the end with a fresh stamp, and the oldest leave first when more than `limit` remain."""
    entries = [e for e in current if e[0] != new] + [(new, now)]
    evicted = [ip for ip, _ in entries[: max(0, len(entries) - limit)]]
    return entries[len(evicted) :], evicted


class CloudflareApi:
    """Rulesets API calls through `cf_auth.curl_json`, which hands the token to curl on stdin."""

    def __init__(self, auth: cf_auth.Auth, sleep: typing.Callable[[float], None] = time.sleep):
        self.auth = auth
        self.sleep = sleep

    def request(self, method: str, path: str, body: dict | None = None) -> dict:
        url = cf_auth.CF_API_BASE + path
        payload = json.dumps(body) if body is not None else None
        for attempt in range(AUTH_RETRIES):
            try:
                answer = cf_auth.curl_json(method, url, self.auth.headers, payload)
            except cf_auth.CfAuthError as exc:
                raise AccessError(str(exc)) from exc
            codes = cf_auth._error_codes(answer)
            if answer.get("success") is False and 10000 in codes and attempt + 1 < AUTH_RETRIES:
                self.sleep(AUTH_RETRY_S)
                continue
            return answer
        raise AccessError("unreachable")


def _fail(what: str, answer: dict) -> AccessError:
    return AccessError("%s refused by Cloudflare: %s" % (what, cf_auth._errors(answer)))


def _entrypoint(api: Api) -> tuple[str | None, dict | None]:
    """(ruleset id, our rule) of the zone's custom-rules entrypoint; (None, None) when the zone has none yet."""
    answer = api.request("GET", "/zones/%s/rulesets/phases/%s/entrypoint" % (ZONE_ID, PHASE))
    if answer.get("success") is not True:
        if ENTRYPOINT_MISSING in cf_auth._error_codes(answer):
            return None, None
        raise _fail("reading the zone's custom rules", answer)
    result = answer.get("result") or {}
    mine = [r for r in result.get("rules") or [] if is_ours(r)]
    if len(mine) > 1:
        raise AccessError(
            "%d rules carry the description %r; delete the extras in the Cloudflare dashboard"
            % (len(mine), RULE_DESCRIPTION)
        )
    return str(result.get("id")), (mine[0] if mine else None)


def current_entries(api: Api) -> list[Entry] | None:
    """The allowed (ip, add time) pairs in stored order, or None when no rule exists (bench is open)."""
    _, rule = _entrypoint(api)
    return None if rule is None else entries_of(rule)


def current_ips(api: Api) -> list[str] | None:
    """The allowed IPs in stored order, or None when no rule exists (bench is open)."""
    entries = current_entries(api)
    return None if entries is None else [ip for ip, _ in entries]


def save(api: Api, hosts: list[str], entries: list[Entry]) -> list[Entry]:
    """Write the rule with `entries` (create or replace) and return what was written."""
    ruleset_id, rule = _entrypoint(api)
    body = rule_body(hosts, entries)
    if ruleset_id is None:
        answer = api.request(
            "PUT",
            "/zones/%s/rulesets/phases/%s/entrypoint" % (ZONE_ID, PHASE),
            {"rules": [body]},
        )
    elif rule is None:
        answer = api.request("POST", "/zones/%s/rulesets/%s/rules" % (ZONE_ID, ruleset_id), body)
    else:
        answer = api.request(
            "PATCH", "/zones/%s/rulesets/%s/rules/%s" % (ZONE_ID, ruleset_id, rule["id"]), body
        )
    if answer.get("success") is not True:
        raise _fail("writing the bench allowlist rule", answer)
    stored = current_entries(api)
    if stored != entries:
        raise AccessError("the stored list is %s after writing %s" % (stored, entries))
    return entries


def delete_rule(api: Api) -> bool:
    """Delete the rule; False when there was none."""
    ruleset_id, rule = _entrypoint(api)
    if rule is None:
        return False
    answer = api.request(
        "DELETE", "/zones/%s/rulesets/%s/rules/%s" % (ZONE_ID, ruleset_id, rule["id"])
    )
    if answer.get("success") is not True:
        raise _fail("deleting the bench allowlist rule", answer)
    return True


def detect_public_ips(
    fetch: typing.Callable[[str], str] | None = None, urls: tuple[str, ...] = TRACE_URLS
) -> list[str]:
    """The caller's public address in each family Cloudflare's trace endpoint answers on; AccessError when it answers on none."""
    fetch = fetch or _fetch_trace
    found: list[str] = []
    for url in urls:
        try:
            text = fetch(url)
        except (OSError, ValueError):
            continue
        line = next((ln for ln in text.splitlines() if ln.startswith("ip=")), "")
        try:
            ip = normalize_ip(line[3:])
        except AccessError:
            continue
        if ip not in found:
            found.append(ip)
    if not found:
        raise AccessError("could not read this machine's public IP from %s" % ", ".join(urls))
    return found


def _fetch_trace(url: str) -> str:
    request = https.build_request(url, method="GET")
    try:
        with https.urlopen(request, timeout=TRACE_TIMEOUT_S) as resp:
            return resp.read(4096).decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        exc.close()
        raise OSError("HTTP %d" % exc.code) from exc


def _print_list(entries: list[Entry] | None, now: datetime.datetime | None = None) -> None:
    if entries is None:
        print("no bench allowlist rule: bench is open to every IP")
        return
    print("bench allowlist (oldest first, at most %d):" % MAX_IPS)
    for ip, at in entries:
        if at is None:
            note = "no add time (legacy, dropped by the next add)"
        else:
            note = "added %s, expires %s" % (
                at.strftime(STAMP_FORMAT),
                (at + TTL).strftime(STAMP_FORMAT),
            )
            if now is not None and now - at >= TTL:
                note += " (EXPIRED, dropped by the next add)"
        print("  %s  %s" % (ip, note))
    if not entries:
        print("  (empty: every IP but the health paths is blocked; run add-current)")


def run(
    command: str,
    argument: str | None,
    api: Api,
    detect: typing.Callable[[], list[str]] = detect_public_ips,
    root=None,
    clock: typing.Callable[[], datetime.datetime] = lambda: datetime.datetime.now(datetime.UTC),
) -> int:
    """Run one verb against `api`; 0 on success. Raises AccessError."""
    if command == "list":
        _print_list(current_entries(api), clock())
        return 0
    if command == "disable":
        print("rule deleted: bench is open again" if delete_rule(api) else "no rule to delete")
        return 0
    hosts = bench_hosts(root)
    now = clock().replace(
        microsecond=0
    )  # stamps keep whole seconds, so the read-back compares equal
    existing = current_entries(api)
    ips, expired = live_entries(list(existing or []), now)
    for gone in expired:
        log.warn("dropped %s: older than %d days or with no add time" % (gone, TTL_DAYS))
    if command in ("add-current", "add"):
        new = detect() if command == "add-current" else [normalize_ip(argument or "")]
        for ip in new:
            ips, evicted = with_ip(ips, ip, now)
            for gone in evicted:
                log.warn("evicted the oldest allowed IP %s (limit %d)" % (gone, MAX_IPS))
        print("allowing " + ", ".join(new))
    elif command == "remove":
        target = normalize_ip(argument or "")
        if target not in [ip for ip, _ in ips]:
            raise AccessError("%s is not in the allowlist" % target)
        ips = [e for e in ips if e[0] != target]
    elif command == "clear":
        if existing is None:
            raise AccessError("no bench allowlist rule exists, so there is nothing to clear")
        ips = []
    else:
        raise AccessError("unknown command %r" % command)
    save(api, hosts, ips)
    if not ips:
        log.warn("the list is empty: every bench request but the health paths is blocked")
    _print_list(ips, now)
    return 0


HELP = (
    __doc__.split("WHO RUNS IT.")[0].strip().replace("\n    ", "\n  ")
    + "\n\nCredentials: the "
    + PROFILE
    + " Bitwarden profile, or CF_MANAGEMENT_TOKEN, or CF_GLOBAL_API_KEY + CF_EMAIL.\n"
)
VERBS = {"add-current": 0, "list": 0, "disable": 0, "clear": 0, "add": 1, "remove": 1}


def _reexec_under_profile(argv: list[str]) -> int | None:
    """This command under the bench-access profile, unless a credential is already in the environment; None when it should run here."""
    have_key = os.environ.get("CF_GLOBAL_API_KEY") and os.environ.get("CF_EMAIL")
    if os.environ.get("CF_MANAGEMENT_TOKEN") or have_key:
        return None
    if PROFILE in (os.environ.get("REDIACC_BWS_PROFILES") or "").split(","):
        return None
    env = dict(os.environ)
    ci = str(paths.repo_root() / ".ci")
    env["PYTHONPATH"] = ci + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "rediacc_ci.core.bws_env",
            "exec",
            "--profile",
            PROFILE,
            "--",
            sys.executable,
            "-m",
            "rediacc_ci.ops.bench_access",
            *argv,
        ],
        env=env,
        check=False,
    ).returncode


def main(argv: list[str]) -> int:
    if argv and argv[0] in ("-h", "--help"):
        sys.stdout.write(HELP)
        return 0
    if not argv or argv[0] not in VERBS or len(argv) - 1 != VERBS[argv[0]]:
        log.error(
            "usage: bench_access add-current | list | add <ip> | remove <ip> | clear | disable"
        )
        return 2
    rebound = _reexec_under_profile(argv)
    if rebound is not None:
        return rebound
    try:
        auth = cf_auth.resolve_scoped("bench-access", zone_id=ZONE_ID)
    except cf_auth.CfAuthError as exc:
        log.error(str(exc))
        return 1
    try:
        cf_auth.await_propagation(auth)
        return run(argv[0], argv[1] if len(argv) > 1 else None, CloudflareApi(auth))
    except (AccessError, cf_auth.CfAuthError) as exc:
        log.error(str(exc))
        return 1
    finally:
        cf_auth.self_destruct(auth)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
