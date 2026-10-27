"""Limit the bench hosts to a short list of allowed IP addresses, kept as ONE Cloudflare WAF custom rule.

    PYTHONPATH=.ci python3 -m rediacc_ci.ops.bench_access add-current   # allow this machine's public IP
    PYTHONPATH=.ci python3 -m rediacc_ci.ops.bench_access list
    PYTHONPATH=.ci python3 -m rediacc_ci.ops.bench_access add <ip>
    PYTHONPATH=.ci python3 -m rediacc_ci.ops.bench_access remove <ip>
    PYTHONPATH=.ci python3 -m rediacc_ci.ops.bench_access preflight     # ci:quick's step: probe bench, run add-current only on a 403, never fails
    PYTHONPATH=.ci python3 -m rediacc_ci.ops.bench_access clear         # empty the list, enforcement stays on
    PYTHONPATH=.ci python3 -m rediacc_ci.ops.bench_access disable       # delete the rule, bench is open again

WHO RUNS IT. An operator or an AI session whose bench request answers Cloudflare's own 403 page (the rule carries no custom body; deploy_bench prints HINT on that 403). The caller's IP changes (it rotates nightly), so the fix is this one command; no ticket and no operator step.

THE MECHANISM: a zone WAF custom rule (Cloudflare Rulesets API, phase `http_request_firewall_custom`, action `block`). The rediacc.com zone is on the Free plan (read live 2026-10-26: `plan.name` is `Free Website`), and Cloudflare's WAF custom rules page lists, for Free: "Number of rules 5 ... Supported actions All except Log" (https://developers.cloudflare.com/waf/custom-rules/), so a Free zone has a block action and room for the one rule this script owns. A custom block response is NOT available on Free: the first live write on 2026-10-26 was refused with `not entitled to use a custom response`, so a blocked request gets Cloudflare's own 403 page, and the fix is named by the tooling instead (this script's HINT, printed by deploy_bench on a 403, and the bench notes in .claude/agents/account-dev.md and docs/agent-reference/local-env.md). The rule is found by its description, so other custom rules on the zone are never touched. IP Access Rules were rejected: they match the whole account or zone, not two hostnames.

WHAT THE RULE BLOCKS. Every request to a bench host (the route patterns of `workers/*/wrangler.bench.toml`: bench.rediacc.com and proxy.bench.rediacc.com) whose source IP is not in the list, EXCEPT `GET` of the two health paths (`/account/api/v1/health`, `/v1/health`). The exemption is what keeps the automated callers working: `telemetry-probe.yml` (six-hourly, GitHub runner egress, a different IP every run) probes exactly those two paths, and a health answer discloses nothing but liveness. The proxy Worker's own calls to the account Worker are service bindings (`workers/proxy/wrangler.bench.toml` ACCOUNT and ISSUER), which never pass the zone's edge rules. Every other caller (deploy_bench, deploy_proxy's smoke past /v1/health, console_executor, the CLI against `--config bench`, the portal in a browser) is an operator or an AI session on its own machine and runs `add-current` first.

EXPIRY. Every address is allowed for `TTL_DAYS` (7) days from the run that added it. The add time lives in the rule's own `description` (`RULE_DESCRIPTION | added ip=<UTC time> ...`), so the Cloudflare rule is the only store and no local state exists. Every mutating run first drops the addresses older than 7 days (the CLI's clock, UTC), then applies its verb; re-adding a live address refreshes its stamp; the 5-address cap counts what is left after the drop. A LEGACY address (in the expression but with no stamp, written before expiry existed or edited by hand) is treated as EXPIRED and dropped by the next mutating run, never stamped now, so an unknown age cannot become a permanent allowance. `list` is read-only and marks such entries. The expiry is enforced when the script runs, not by Cloudflare: an address stays in the rule past 7 days until the next run (the nightly `add-current` that the rotating IP already needs).

IPv6 IS KEPT AS A /64. A host's IPv6 address is a privacy address that rotates within its /64, so an IPv6 `add`, `remove` or detected address is canonicalized to its /64 network (`2001:a61:50d0:3b01::/64`) and re-adding an address inside it refreshes that one entry. A CIDR given by hand is accepted only for IPv6 /64 or narrower (down to /128); IPv4 stays one address. The allowance is the whole /64: every host sharing that prefix, not only the caller's machine, passes the rule. The prefix is written into `ip.src in {...}` as Cloudflare's CIDR literal. Under WSL `add-current` also asks the Windows host (powershell.exe, api64.ipify.org and api.ipify.org) for its egress addresses, because a Windows browser leaves over a different family than the WSL guest; a family that does not answer is skipped with a note.

PREFLIGHT. `preflight` is the step ci:quick runs first (the `ci:quick` npm script): a read-only GET of bench from this machine (and from the Windows host under WSL), and only a 403 triggers `add-current`. It skips under CI=true, and it ALWAYS exits 0, printing one line on any error, so it can never fail ci:quick.

THE LIST. At most `MAX_IPS` (5) entries (single addresses or IPv6 /64 prefixes), oldest first in the rule's expression, which is the record: `add-current` appends the caller's address (re-adding one moves it to the end) and evicts from the front when the list is full. With no rule yet, the first `add` creates it holding the caller's own address, so the first enforcement cannot lock the caller out. `add-current` asks Cloudflare's own trace endpoint for the IPv4 and the IPv6 address it sees (one family may be unreachable and is then skipped), so a dual-stack host is allowed in whichever family curl or node picks.

AUTH. `cf_auth.resolve_scoped("bench-access", zone_id=ZONE_ID)`: a supplied `CF_MANAGEMENT_TOKEN`, or a token minted from the Global API Key with `Zone WAF Write` on the rediacc.com zone only (plus the user-scoped API Tokens pair its self-destruct needs), deleted at the end of the run. The script re-runs itself under the `bench-access` Bitwarden profile (`CF_GLOBAL_API_KEY`, `CF_EMAIL`) when neither is in the environment. The credential reaches curl on its stdin (`rediacc_ci.core.curl_stdin`), never on argv, and is never printed.
"""

from __future__ import annotations

import datetime
import http.client
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
import urllib.request

from rediacc_ci import log, paths
from rediacc_ci.core import https
from rediacc_ci.ops import apply_cf_redirect_rules, cf_auth
from rediacc_ci.well_known import BENCH_ORIGIN

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
V6_PREFIX = 64
BENCH_URL = BENCH_ORIGIN + "/"
PROBE_TIMEOUT_S = 10.0
# Cloudflare answers the default `Python-urllib` agent 403 whatever the source IP (measured 2026-10-27), so the probe names itself.
PROBE_AGENT = "rediacc-bench-access/1"
POWERSHELL = "/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe"
HOST_IP_URLS = ("https://api64.ipify.org", "https://api.ipify.org")
WSL_MARKER = "/proc/sys/fs/binfmt_misc/WSLInterop"
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
    """The canonical entry text for one address or prefix: an IPv4 address as itself, an IPv6 address as its /64 network, a hand-written IPv6 CIDR as given when its prefix is /64 to /128. AccessError for anything else (a broader IPv6 prefix, an IPv4 range, garbage)."""
    raw = text.strip()
    if "/" not in raw:
        try:
            ip = ipaddress.ip_address(raw)
        except ValueError:
            raise AccessError("not a single IP address: %r" % text) from None
        if ip.version == 4:
            return str(ip)
        return str(ipaddress.ip_network("%s/%d" % (ip, V6_PREFIX), strict=False))
    try:
        net = ipaddress.ip_network(raw, strict=False)
    except ValueError:
        raise AccessError("not a single IP address: %r" % text) from None
    if net.version == 4 and net.prefixlen == 32:
        return str(net.network_address)
    if net.version == 6 and net.prefixlen >= V6_PREFIX:
        return str(net)
    raise AccessError(
        "refusing %r: only an IPv4 address or an IPv6 prefix of /%d to /128 may be allowed"
        % (text, V6_PREFIX)
    )


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
    out: list[str] = []
    for raw in found.group(1).split() if found else []:
        try:
            canonical = normalize_ip(raw)  # a bare IPv6 written before /64 entries reads as its /64
        except AccessError:
            canonical = raw
        if canonical not in out:
            out.append(canonical)
    return out


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
    """True for a rule whose description is the marker alone or the marker followed by the stamp list `describe` writes; a foreign description that merely begins with the marker is not ours."""
    text = str(rule.get("description", ""))
    return text == RULE_DESCRIPTION or text.startswith(RULE_DESCRIPTION + STAMP_MARK)


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


def in_wsl() -> bool:
    """True under WSL (the interop marker or WSL_DISTRO_NAME)."""
    return os.path.exists(WSL_MARKER) or bool(os.environ.get("WSL_DISTRO_NAME"))


def _powershell(command: str) -> str:
    done = subprocess.run(
        [POWERSHELL, "-NoProfile", "-Command", command],
        capture_output=True,
        text=True,
        timeout=PROBE_TIMEOUT_S + 10,
        check=False,
    )
    if done.returncode != 0:
        raise OSError("powershell exit %d" % done.returncode)
    return done.stdout


def detect_host_ips(
    run_ps: typing.Callable[[str], str] | None = None, wsl: bool | None = None
) -> list[str]:
    """The Windows host's egress addresses when running under WSL, else []. Each family fails soft with a printed note."""
    if not (in_wsl() if wsl is None else wsl):
        return []
    run_ps = run_ps or _powershell
    found: list[str] = []
    for url in HOST_IP_URLS:
        try:
            text = run_ps("(Invoke-RestMethod -TimeoutSec 10 %s)" % url).strip()
            ip = str(ipaddress.ip_address(text))
        except (OSError, ValueError, subprocess.SubprocessError):
            print("note: the Windows host did not answer at %s; skipped" % url)
            continue
        if ip not in found:
            found.append(ip)
    return found


def detect_current(
    trace: typing.Callable[[], list[str]] | None = None,
    host: typing.Callable[[], list[str]] = detect_host_ips,
) -> list[str]:
    """This machine's addresses (Cloudflare trace) plus, under WSL, the Windows host's; AccessError only when both are empty."""
    trace = trace or detect_public_ips
    host_ips = host()
    try:
        found = trace()
    except AccessError:
        if not host_ips:
            raise
        found = []
    return found + [ip for ip in host_ips if ip not in found]


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        return None


def _probe_local() -> int:
    """The HTTP status of bench from this machine (a redirect is followed; only a 403 matters)."""
    opener = https.build_opener(_NoRedirect())
    try:
        with opener.open(
            https.build_request(BENCH_URL, method="GET", headers={"User-Agent": PROBE_AGENT}),
            timeout=PROBE_TIMEOUT_S,
        ) as r:
            return r.status
    except urllib.error.HTTPError as exc:
        exc.close()
        return exc.code


_PS_PROBE = (
    "try { (Invoke-WebRequest -UseBasicParsing -MaximumRedirection 0 -TimeoutSec 10 %s).StatusCode }"
    " catch { if ($_.Exception.Response) { [int]$_.Exception.Response.StatusCode } else { 'err' } }"
)


def _probe_host() -> int:
    """The HTTP status of bench from the Windows host (WSL only)."""
    out = _powershell(_PS_PROBE % BENCH_URL).strip().splitlines()
    return int(out[-1]) if out else 0


def preflight(
    probes: tuple[typing.Callable[[], int], ...] | None = None,
    add: typing.Callable[[], int] | None = None,
    environ: typing.Mapping[str, str] | None = None,
) -> int:
    """ci:quick's step: probe bench; only a 403 from some egress runs add-current. Skips under CI=true and ALWAYS returns 0."""
    env = os.environ if environ is None else environ
    if env.get("CI") == "true":
        print("bench-access: skipped under CI")
        return 0
    try:
        if probes is None:
            probes = (_probe_local, _probe_host) if in_wsl() else (_probe_local,)
        statuses = []
        failed: list[Exception] = []
        for probe in probes:
            try:
                statuses.append(probe())
            except (
                OSError,
                ValueError,
                subprocess.SubprocessError,
                http.client.HTTPException,
            ) as exc:
                # one egress that cannot be probed (no powershell, a timeout, a non-numeric reply) must not hide a 403 on another
                failed.append(exc)
        if not statuses and failed:
            raise failed[0]
        if 403 not in statuses:
            print("bench-access: bench reachable (%s)" % ", ".join(str(s) for s in statuses))
            return 0
        print("bench-access: bench answered 403, allowing this machine's addresses")
        rc = (add or (lambda: main(["add-current"])))()
        if rc != 0:
            print("bench-access: add-current exited %d; continuing" % rc)
    except (
        OSError,
        ValueError,
        RuntimeError,
        subprocess.SubprocessError,
        http.client.HTTPException,
        AccessError,
        cf_auth.CfAuthError,
        SystemExit,
    ) as exc:
        print("bench-access: skipped (%s: %s)" % (type(exc).__name__, exc))
    return 0


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
    detect: typing.Callable[[], list[str]] = detect_current,
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
        new = list(
            dict.fromkeys(
                normalize_ip(ip)
                for ip in (detect() if command == "add-current" else [argument or ""])
            )
        )
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
VERBS = {
    "preflight": 0,
    "add-current": 0,
    "list": 0,
    "disable": 0,
    "clear": 0,
    "add": 1,
    "remove": 1,
}


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
            "usage: bench_access preflight | add-current | list | add <ip> | remove <ip> | clear | disable"
        )
        return 2
    if argv[0] == "preflight":
        return preflight()
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
