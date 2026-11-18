"""The ops-health `dmarc` check: read the unread DMARC aggregate and TLS-RPT reports in the mail repo's DMARC folders, judge every source against .ci/config/dmarc-known-sources.json, and mark the reports that are fully judged as Seen.

    PYTHONPATH=.ci python3 -m rediacc_ci.ops.dmarc_reports [--json] [--no-mark]

ops_health runs it as a subprocess check (TTL `local_ttl_minutes.dmarc`) and keeps its 0/1/2 contract: 0 green, 1 red, 2 unreadable. The verdict never leaves the machine: no mail, no issue, no ingest POST (operator ruling 2026-11-16); the ops-health red in the Stop hook is the signal.

READ. One `rdc --config <target.config> term connect <target.repo> -c` call pipes the source of rediacc_ci.ops.dmarc_parser, base64-encoded inside the command, into `docker exec -i <target.container> python3 -I -`, so no file is written on the machine. The parser lists only UNSEEN messages (doveadm fetch, which sets no flag) and prints one JSON line.

JUDGE. A record fails DMARC when its evaluated DKIM and SPF both did not pass. Per (domain, source IP):
  - one of `ours` (by CIDR or forward-confirmed rDNS suffix): failing is red `dmarc.ours.failing`;
  - one of `rulings`, the retired providers (verdict `old-provider`: Microsoft 365 for rediacc.com, Zoho EU for rediacc.io, ruled 2026-11-16) or a ruled spoofer (`spoof`): failing is expected and silent, since DNS no longer authorizes them and p=reject blocks the mail; PASSING is red `dmarc.ruled.passing` (DNS still authorizes a source it should not); and a volume jump is red `dmarc.ruled.volume`: more than `volume.max_per_day` messages on one report day, or, once `volume.trailing_days` of history exist, at least `volume.ratio_min_count` messages and `volume.ratio` times the trailing daily average;
  - anything else failing: red `dmarc.source.new`, naming the IP, its rDNS, the domain, the message count and the reporters, so the next session asks the operator and adds a ruling.
A TLS-RPT policy with failed sessions is red `dmarc.tlsrpt.failure`, and a report attachment that cannot be read is red `dmarc.report.malformed` with the parser's reason. `acknowledged_through` (domain -> date) silences every red but a new source and a malformed report, for reports that ended on or before the date.

HISTORY. The ruled sources' message counts per report (by report id, so a report read twice counts once) are kept in .ci/cache/ops-health/dmarc-history.json, the trailing average's input; entries older than HISTORY_DAYS are dropped.

SERVER REPORTS. A mailbox listed with `"kind": "server-reports"` (the Server-Reports folder) holds server mail, judged per message by event (operator ruling 2026-11-18): an SES DeliveryDelay or Transient bounce whose every recipient domain is a reserved test domain (`server_reports.reserved_domains` and `reserved_tlds`) is benign; any Complaint, any non-Transient bounce, any ContentRejected, any delay or bounce to a real domain is red `server-reports.ses`, named by event type and recipient DOMAIN (never the address) with a count; a Postfix daily summary is red `server-reports.postfix` above a count in `server_reports.postfix` (max_rejected, max_deferred, max_bounced) and benign otherwise; an SNS subscription confirmation is benign; a message from a sender not in `server_reports.senders`, or of a shape that sender may not send, or of unknown shape, is red `server-reports.unknown`. Benign messages are marked Seen, red ones stay unread and are listed once, grouped.

UNREADABLE. A mail server that cannot be read (the read, a mailbox listing, or the Seen marking failed: login refused, the IP-rebind refusal, a timeout) is RED `dmarc.mail.unreadable` naming the cause, never unknown (2026-11-18: it sat unknown for two days unnoticed).

MARK. Only report messages whose every finding is green are marked `\\Seen` (doveadm flags add, never a delete or a move). A report that holds a red finding, a malformed one, and any message that is not a report stay unread, so the red stands on the next run until a ruling or an acknowledgement covers it, and non-report mail is never touched.
"""

from __future__ import annotations

import argparse
import base64
import concurrent.futures
import datetime
import ipaddress
import json
import os
import pathlib
import re
import shlex
import socket
import subprocess
import sys
from collections.abc import Callable

from rediacc_ci import well_known
from rediacc_ci.core.common import repo_root
from rediacc_ci.ops import dmarc_parser
from rediacc_ci.ops.ops_health import (
    CACHE_DIR_REL,
    RDC_TIMEOUT_S,
    Result,
    Runner,
    child_env,
    failure_text,
    rdc_argv,
    run_process,
    worst_rc,
)

KNOWN_REL = ".ci/config/dmarc-known-sources.json"
HISTORY_NAME = "dmarc-history.json"
HISTORY_DAYS = 90
RDNS_TIMEOUT_S = 5.0
VERDICTS = ("old-provider", "spoof")
MAILBOX_KINDS = ("dmarc", "server-reports")
SERVER_SHAPES = ("ses-event", "postfix-summary", "sns-confirm")
POSTFIX_LIMITS = ("max_rejected", "max_deferred", "max_bounced")
MARK_CHUNK = 400
SERVER_RED_LINES = 25
LEDGER_REL = "agent/ledgers/mail-events.jsonl"
VOLUME_DEFAULTS = {"max_per_day": 20, "ratio": 5.0, "ratio_min_count": 5, "trailing_days": 14}

# ip -> its forward-confirmed reverse name, or "" when it has none. Injected by the tests.
Resolver = Callable[[str], str]


class KnownError(ValueError):
    """The rulings file is missing or malformed; the message names the field."""


# --------------------------------------------------------------------------- rulings


def _entry(raw: object, where: str) -> dict:
    if not isinstance(raw, dict) or not str(raw.get("name") or ""):
        raise KnownError("%s: an entry without a name" % where)
    try:
        nets = [ipaddress.ip_network(str(c), strict=False) for c in raw.get("cidrs") or []]
    except ValueError as exc:
        raise KnownError("%s %s: %s" % (where, raw["name"], exc)) from None
    return {
        "name": str(raw["name"]),
        "nets": nets,
        "suffixes": [str(s).lower().strip(".") for s in raw.get("rdns_suffixes") or []],
        "domains": [str(d).lower() for d in raw.get("domains") or []],
        "verdict": str(raw.get("verdict") or ""),
        "ruled": str(raw.get("ruled") or ""),
    }


_WK_REF = re.compile(r"\$\{(WK_[A-Z][A-Z0-9_]*)\}")


def _compose(value: object, path: pathlib.Path) -> object:
    """Every `${WK_NAME}` in a string of the rulings file replaced by its well-known value, so the file restates none."""
    if isinstance(value, str):

        def sub(match: re.Match[str]) -> str:
            try:
                return well_known.VALUES[match.group(1)]
            except KeyError:
                raise KnownError(
                    "%s: %s is not in %s" % (path, match.group(1), well_known.REGISTRY_REL)
                ) from None

        composed = _WK_REF.sub(sub, value)
        if "${" in composed:
            raise KnownError(
                "%s: %r holds a ${...} that is not a ${WK_NAME} reference" % (path, value)
            )
        return composed
    if isinstance(value, list):
        return [_compose(v, path) for v in value]
    if isinstance(value, dict):
        return {k: _compose(v, path) for k, v in value.items()}
    return value


def _server_reports(raw: object, boxes: list, path: pathlib.Path) -> dict:
    """The validated `server_reports` section; required once a mailbox is of kind server-reports."""
    needed = any(str(b.get("kind") or "dmarc") == "server-reports" for b in boxes)
    if raw is None and not needed:
        return {}
    if not isinstance(raw, dict):
        raise KnownError("%s: a server-reports mailbox needs a server_reports object" % path)
    senders: dict[str, set] = {}
    for entry in raw.get("senders") or []:
        shapes = entry.get("shapes") if isinstance(entry, dict) else None
        if (
            not isinstance(entry, dict)
            or not str(entry.get("from") or "")
            or not isinstance(shapes, list)
            or not shapes
            or any(sh not in SERVER_SHAPES for sh in shapes)
        ):
            raise KnownError(
                "server_reports.senders: each entry needs `from` and `shapes` from %s"
                % ", ".join(SERVER_SHAPES)
            )
        senders[str(entry["from"]).lower()] = set(shapes)
    if not senders:
        raise KnownError("server_reports.senders is empty")
    limits = raw.get("postfix") or {}
    postfix: dict[str, int] = {}
    for key in POSTFIX_LIMITS:
        value = limits.get(key) if isinstance(limits, dict) else None
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise KnownError("server_reports.postfix.%s: %r is not a count" % (key, value))
        postfix[key] = value
    reserved = {
        key: [str(d).lower().strip(".") for d in raw.get(key) or []]
        for key in ("reserved_domains", "reserved_tlds")
    }
    if not reserved["reserved_domains"] and not reserved["reserved_tlds"]:
        raise KnownError("server_reports needs reserved_domains or reserved_tlds")
    return {"senders": senders, "postfix": postfix, **reserved}


def load_known(path: pathlib.Path) -> dict:
    """The parsed rulings file, its `${WK_NAME}` references composed. Raises KnownError naming what is missing."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise KnownError("%s: %s" % (path, exc)) from None
    doc = _compose(raw, path)
    if not isinstance(doc, dict):
        raise KnownError("%s is not a JSON object" % path)
    target = doc.get("target") or {}
    if not all(str(target.get(k) or "") for k in ("config", "repo", "container")):
        raise KnownError("%s: target needs config, repo and container" % path)
    boxes = doc.get("mailboxes")
    if (
        not isinstance(boxes, list)
        or not boxes
        or not all(isinstance(b, dict) and b.get("user") and b.get("mailbox") for b in boxes)
    ):
        raise KnownError("%s: mailboxes needs at least one {user, mailbox}" % path)
    for b in boxes:
        if str(b.get("kind") or "dmarc") not in MAILBOX_KINDS:
            raise KnownError(
                "mailboxes %s: kind %r is not one of %s"
                % (b["mailbox"], b.get("kind"), ", ".join(MAILBOX_KINDS))
            )
    server = _server_reports(doc.get("server_reports"), boxes, path)
    rulings = [_entry(r, "rulings") for r in doc.get("rulings") or []]
    for ruling in rulings:
        if not ruling["ruled"]:
            raise KnownError("rulings %s: no `ruled` date" % ruling["name"])
        if ruling["verdict"] not in VERDICTS:
            raise KnownError(
                "rulings %s: verdict %r is not one of %s"
                % (ruling["name"], ruling["verdict"], ", ".join(VERDICTS))
            )
    acked: dict[str, datetime.date] = {}
    for domain, day in (doc.get("acknowledged_through") or {}).items():
        try:
            acked[str(domain).lower()] = datetime.date.fromisoformat(str(day))
        except ValueError:
            raise KnownError(
                "acknowledged_through %s: %r is not YYYY-MM-DD" % (domain, day)
            ) from None
    volume = dict(VOLUME_DEFAULTS)
    raw_volume = doc.get("volume") or {}
    if not isinstance(raw_volume, dict):
        raise KnownError("%s: volume is not an object" % path)
    for key, default in VOLUME_DEFAULTS.items():
        value = raw_volume.get(key, default)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
            raise KnownError("volume.%s: %r is not a positive number" % (key, value))
        volume[key] = value
    return {
        "target": {k: str(target[k]) for k in ("config", "repo", "container")},
        "mailboxes": [
            {
                "user": str(b["user"]),
                "mailbox": str(b["mailbox"]),
                "kind": str(b.get("kind") or "dmarc"),
            }
            for b in boxes
        ],
        "server": server,
        "ours": [_entry(o, "ours") for o in doc.get("ours") or []],
        "rulings": rulings,
        "acknowledged_through": acked,
        "volume": volume,
    }


def _in_nets(ip: str, nets: list) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return any(addr.version == n.version and addr in n for n in nets)


def _suffix_hit(rdns: str, suffixes: list) -> bool:
    name = rdns.lower().rstrip(".")
    return bool(name) and any(name == s or name.endswith("." + s) for s in suffixes)


def match(entries: list, ip: str, rdns: Callable[[], str], domain: str = "") -> dict | None:
    """The first entry the source matches: by CIDR first, then by rDNS (resolved only when no CIDR matched)."""
    scoped = [e for e in entries if not e["domains"] or domain in e["domains"]]
    for entry in scoped:
        if _in_nets(ip, entry["nets"]):
            return entry
    if any(e["suffixes"] for e in scoped):
        name = rdns()
        for entry in scoped:
            if _suffix_hit(name, entry["suffixes"]):
                return entry
    return None


def forward_confirmed_rdns(ip: str) -> str:
    """The PTR name of `ip` when that name resolves back to `ip`, else "". Bounded by RDNS_TIMEOUT_S; a lookup failure is no name, never an error."""

    def lookup() -> str:
        try:
            name = socket.gethostbyaddr(ip)[0]
            addrs = {str(a[4][0]) for a in socket.getaddrinfo(name, None)}
            want = ipaddress.ip_address(ip)
            hit = any(ipaddress.ip_address(a.split("%")[0]) == want for a in addrs)
        except (OSError, UnicodeError, ValueError):
            return ""
        return name if hit else ""

    pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    try:
        return pool.submit(lookup).result(timeout=RDNS_TIMEOUT_S)
    except concurrent.futures.TimeoutError:
        return ""
    finally:
        pool.shutdown(wait=False)


# --------------------------------------------------------------------------- history


def history_path(root: pathlib.Path) -> pathlib.Path:
    return root / CACHE_DIR_REL / HISTORY_NAME


def load_history(path: pathlib.Path) -> tuple[dict, str]:
    """({"first": ISO day or "", "reports": {report key: {ruling, day, count}}}, "") or the empty history and why the file could not be read. An absent file is an empty history, not an error."""
    empty: dict = {"first": "", "reports": {}}
    if not path.exists():
        return empty, ""
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return empty, "%s unreadable, trailing averages restart: %s" % (path, exc)
    if not isinstance(doc, dict) or not isinstance(doc.get("reports"), dict):
        return empty, "%s has no reports object, trailing averages restart" % path
    return {"first": str(doc.get("first") or ""), "reports": dict(doc["reports"])}, ""


def save_history(path: pathlib.Path, history: dict, today: datetime.date) -> str:
    """ "" on success, else why the history could not be written."""
    cutoff = (today - datetime.timedelta(days=HISTORY_DAYS)).isoformat()
    history["reports"] = {
        k: v
        for k, v in history["reports"].items()
        if isinstance(v, dict) and str(v.get("day") or "") >= cutoff
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(".%s.%d.tmp" % (path.name, os.getpid()))
        tmp.write_text(json.dumps(history, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        tmp.replace(path)
    except OSError as exc:
        return "writing %s failed: %s" % (path, exc)
    return ""


def daily_counts(history: dict, ruling: str) -> dict:
    """ISO day -> messages the ruled source sent on it, over every recorded report."""
    out: dict[str, int] = {}
    for row in history["reports"].values():
        if isinstance(row, dict) and row.get("ruling") == ruling:
            day = str(row.get("day") or "")
            out[day] = out.get(day, 0) + int(row.get("count") or 0)
    return out


def volume_reason(history: dict, ruling: str, day: str, volume: dict) -> str:
    """Why `ruling`'s count on `day` is a jump, or "" when it is not."""
    counts = daily_counts(history, ruling)
    count = counts.get(day, 0)
    if count > volume["max_per_day"]:
        return "%d message(s) on %s, over the %d a day limit" % (count, day, volume["max_per_day"])
    first = history.get("first") or ""
    trailing = int(volume["trailing_days"])
    try:
        when = datetime.date.fromisoformat(day)
        since = datetime.date.fromisoformat(first) if first else None
    except ValueError:
        return ""
    if since is None or (when - since).days < trailing:
        return ""
    window = [(when - datetime.timedelta(days=n)).isoformat() for n in range(1, trailing + 1)]
    average = sum(counts.get(d, 0) for d in window) / trailing
    if count >= volume["ratio_min_count"] and count >= volume["ratio"] * max(average, 1e-9):
        return "%d message(s) on %s, %.1fx the %d-day average of %.2f" % (
            count,
            day,
            count / average if average else float("inf"),
            trailing,
            average,
        )
    return ""


# --------------------------------------------------------------------------- read and mark on the machine


def parse_command(known: dict, source: str) -> str:
    """The shell command `term connect -c` runs: the parser source and its argument travel base64-encoded inside it."""
    script = base64.b64encode(source.encode("utf-8")).decode("ascii")
    spec = json.dumps({"mailboxes": known["mailboxes"]}).encode("utf-8")
    arg = base64.b64encode(spec).decode("ascii")
    return "printf %%s %s | base64 -d | docker exec -i %s python3 -I - %s" % (
        script,
        shlex.quote(known["target"]["container"]),
        arg,
    )


def _chunks(items: list, size: int) -> list:
    return [items[i : i + size] for i in range(0, len(items), size)]


def mark_command(known: dict, marks: dict) -> str:
    """`doveadm flags add ... \\Seen` per mailbox for the uids in `marks` ((user, mailbox) -> [uid])."""
    container = shlex.quote(known["target"]["container"])
    parts = [
        "docker exec %s doveadm flags add -u %s %s mailbox %s uid %s"
        % (
            container,
            shlex.quote(user),
            shlex.quote("\\Seen"),
            shlex.quote(mailbox),
            ",".join(str(u) for u in chunk),
        )
        for (user, mailbox), uids in sorted(marks.items())
        for chunk in _chunks(sorted(int(u) for u in uids), MARK_CHUNK)
    ]
    return " && ".join(parts)


def _term(known: dict, runner: Runner, env: dict, command: str) -> Result:
    cenv = child_env(env)
    args = ["term", "connect", known["target"]["repo"], "-c", command]
    return runner(rdc_argv(cenv, known["target"]["config"], args), cenv, RDC_TIMEOUT_S)


def read_reports(known: dict, runner: Runner, env: dict) -> tuple[dict | None, str]:
    """(the parser's document, "") or (None, why it could not be read)."""
    source = pathlib.Path(dmarc_parser.__file__).read_text(encoding="utf-8")
    res = _term(known, runner, env, parse_command(known, source))
    where = "%s %s" % (known["target"]["repo"], known["target"]["container"])
    if res.timed_out:
        return None, "reading the reports on %s timed out after %ds" % (where, RDC_TIMEOUT_S)
    marker = dmarc_parser.MARKER
    line = next((ln for ln in (res.stdout or "").splitlines() if ln.startswith(marker)), "")
    if res.rc != 0 or not line:
        return None, "reading the reports on %s failed (rc %d): %s" % (
            where,
            res.rc,
            failure_text(res, default="no parser output", config=known["target"]["config"]),
        )
    try:
        doc = json.loads(line[len(marker) :])
    except ValueError:
        return None, "the parser on %s printed a line that is not JSON" % where
    if not isinstance(doc, dict) or not isinstance(doc.get("mailboxes"), list):
        return None, "the parser on %s printed no mailboxes list" % where
    return doc, ""


def mark_seen(known: dict, marks: dict, runner: Runner, env: dict) -> str:
    """ "" when the uids were marked (or there were none), else why not."""
    command = mark_command(known, marks)
    if not command:
        return ""
    res = _term(known, runner, env, command)
    if res.timed_out or res.rc != 0:
        return "marking %d report(s) Seen failed (%s): %s" % (
            sum(len(v) for v in marks.values()),
            "timeout" if res.timed_out else "rc %d" % res.rc,
            failure_text(res, default="no output", config=known["target"]["config"]),
        )
    return ""


# --------------------------------------------------------------------------- judge: server reports


def _reserved(domain: str, server: dict) -> bool:
    """A reserved test domain: one of reserved_domains (or a subdomain of it), or under a reserved TLD."""
    name = domain.lower().strip(".")
    if not name or name == "?":
        return False
    if any(name == d or name.endswith("." + d) for d in server["reserved_domains"]):
        return True
    return name.rsplit(".", 1)[-1] in server["reserved_tlds"]


def _sender_domain(sender: str) -> str:
    return sender.rsplit("@", 1)[-1] if "@" in sender else "?"


def judge_server_message(msg: dict, server: dict) -> tuple[str, str, str]:
    """(verdict, code, detail) for one server mail: verdict `benign` or `red`; a red's code names its class and detail is the line text its group is counted under."""
    sender = str(msg.get("from") or "")
    report = msg.get("report") if isinstance(msg.get("report"), dict) else {}
    shape = str(report.get("shape") or "unknown")
    allowed = server["senders"].get(sender)
    if allowed is None:
        return (
            "red",
            "server-reports.unknown",
            "mail from the unknown sender domain %s" % _sender_domain(sender),
        )
    if shape not in allowed:
        why = str(report.get("why") or "shape %s is not one this sender sends" % shape)
        return (
            "red",
            "server-reports.unknown",
            "mail from %s of unknown shape: %s" % (_sender_domain(sender), why),
        )
    if shape == "sns-confirm":
        return "benign", "", ""
    if shape == "postfix-summary":
        over = [
            "%s %d (limit %d)" % (k, int(report.get(k) or 0), server["postfix"]["max_" + k])
            for k in ("rejected", "deferred", "bounced")
            if int(report.get(k) or 0) > server["postfix"]["max_" + k]
        ]
        if not over:
            return "benign", "", ""
        sent = str(msg.get("subject") or "").rsplit(" sent ", 1)[-1][:40]
        return (
            "red",
            "server-reports.postfix",
            "Postfix summary sent %s: %s" % (sent or "?", ", ".join(over)),
        )
    event = str(report.get("event") or "")
    btype, sub = str(report.get("bounce_type") or ""), str(report.get("bounce_sub_type") or "")
    delay = str(report.get("delay_type") or "")
    domains = [str(d) for d in report.get("domains") or []]
    label = event
    if event == "Bounce":
        label = "Bounce %s/%s" % (btype or "?", sub or "?")
    elif event == "DeliveryDelay":
        label = "DeliveryDelay %s" % (delay or "?")
    if not domains:
        return "red", "server-reports.ses", "%s event with no recipient domain" % label
    real = [d for d in domains if not _reserved(d, server)]
    if event == "Complaint":
        return "red", "server-reports.ses", "Complaint to %s" % ", ".join(domains)
    if event == "Bounce":
        if btype != "Transient" or sub == "ContentRejected" or real:
            return "red", "server-reports.ses", "%s to %s" % (label, ", ".join(real or domains))
        return "benign", "", ""
    if event == "DeliveryDelay":
        if real:
            return "red", "server-reports.ses", "%s to %s" % (label, ", ".join(real))
        return "benign", "", ""
    return (
        "red",
        "server-reports.ses",
        "unhandled SES event %s to %s" % (label, ", ".join(domains)),
    )


def ses_red_keys(msg: dict, server: dict) -> list:
    """[(event, type, domain)] for a red SES event message, one per recipient domain the red names; empty for anything else."""
    report = msg.get("report") if isinstance(msg.get("report"), dict) else {}
    if msg.get("kind") != "server-report" or report.get("shape") != "ses-event":
        return []
    verdict, code, _ = judge_server_message(msg, server)
    if verdict != "red" or code != "server-reports.ses":
        return []
    event = str(report.get("event") or "")
    if event == "Bounce":
        kind = "%s/%s" % (report.get("bounce_type") or "?", report.get("bounce_sub_type") or "?")
    elif event == "DeliveryDelay":
        kind = str(report.get("delay_type") or "?")
    else:
        kind = ""
    domains = [str(d) for d in report.get("domains") or []]
    named = domains if event == "Complaint" else [d for d in domains if not _reserved(d, server)]
    return [(event, kind, d) for d in (named or domains)]


def _ledger_ids(text: str) -> set:
    """Every message id hash that the rows of a ledger text cover; an unreadable line covers nothing."""
    found: set = set()
    for line in text.splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict) and isinstance(row.get("ids"), list):
            found.update(str(i) for i in row["ids"])
    return found


def load_ledger(root: pathlib.Path) -> dict:
    """{"committed": ids at HEAD, "working": ids in the working-tree file plus the committed ones}; a missing file is empty on both sides."""
    committed: set = set()
    try:
        shown = subprocess.run(
            ["git", "show", "HEAD:" + LEDGER_REL],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if shown.returncode == 0:
            committed = _ledger_ids(shown.stdout)
    except (OSError, subprocess.SubprocessError):
        committed = set()
    path = root / LEDGER_REL
    working = _ledger_ids(path.read_text(encoding="utf-8")) if path.is_file() else set()
    return {"committed": committed, "working": working | committed}


def ledger_rows(doc: dict, server: dict, known_ids: set, now: datetime.datetime) -> list:
    """One row per (day, event, type, domain) over the red SES messages whose id is not in `known_ids`; ids are hashes, never an address."""
    groups: dict[tuple, list] = {}
    for box in doc.get("mailboxes") or []:
        if box.get("kind") != "server-reports" or box.get("error"):
            continue
        for msg in box.get("messages") or []:
            mid = str(msg.get("id") or "")
            if not mid or mid in known_ids:
                continue
            for event, kind, domain in ses_red_keys(msg, server):
                ids = groups.setdefault(
                    (str(msg.get("date") or "unknown"), event, kind, domain), []
                )
                if mid not in ids:
                    ids.append(mid)
    stamp = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    return [
        {
            "date": day,
            "event": event,
            "type": kind,
            "domain": domain,
            "count": len(ids),
            "ids": sorted(ids),
            "logged_at": stamp,
        }
        for (day, event, kind, domain), ids in sorted(groups.items())
    ]


def log_events(
    root: pathlib.Path,
    *,
    runner: Runner = run_process,
    env: dict | None = None,
    now: datetime.datetime | None = None,
) -> dict:
    """{rc, lines}: append the red Server-Reports messages not yet in the ledger file, print the commit form."""
    env = dict(os.environ if env is None else env)
    now = now or datetime.datetime.now(datetime.UTC)
    try:
        known = load_known(root / KNOWN_REL)
    except KnownError as exc:
        return {"rc": 2, "lines": ["dmarc: rulings unreadable: %s" % exc]}
    doc, error = read_reports(known, runner, env)
    if doc is None:
        return {"rc": 1, "lines": ["dmarc.mail.unreadable: %s" % error]}
    known_ids = load_ledger(root)["working"]
    new = ledger_rows(doc, known["server"], known_ids, now)
    if not new:
        return {"rc": 0, "lines": ["mail-events: no red Server-Reports message outside the ledger"]}
    path = root / LEDGER_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        for row in new:
            fh.write(json.dumps(row, sort_keys=True) + "\n")
    lines = [
        "mail-events: %d row(s), %d message(s) appended to %s"
        % (len(new), sum(r["count"] for r in new), LEDGER_REL)
    ]
    lines += [
        "  %s %s %s to %s: %d" % (r["date"], r["event"], r["type"] or "-", r["domain"], r["count"])
        for r in new
    ]
    lines += [
        "review the rows, then commit them; the next run clears these reds from HEAD:",
        "  git add -- %s" % LEDGER_REL,
        "  git commit -F <msg-file> -- %s" % LEDGER_REL,
    ]
    return {"rc": 0, "lines": lines}


def judge_server_box(
    box: dict, server: dict, clean: dict, red: dict, tally: dict, ledger: dict | None = None
) -> None:
    """Judge every message of a server-reports mailbox: `clean` gets its marks, `red` the grouped red lines ((code, detail) -> count), `tally` the counts. A red SES message whose id hash is in the HEAD-committed ledger is benign; one only in the working-tree ledger stays red as `logged, not committed`."""
    ledger = ledger or {"committed": set(), "working": set()}
    user, mailbox = str(box.get("user") or ""), str(box.get("mailbox") or "")
    for msg in box.get("messages") or []:
        tally["messages"] += 1
        if msg.get("kind") != "server-report":
            verdict, code, detail = (
                "red",
                "server-reports.unknown",
                "unreadable message: %s" % msg.get("error"),
            )
        else:
            verdict, code, detail = judge_server_message(msg, server)
            mid = str(msg.get("id") or "")
            if verdict == "red" and code == "server-reports.ses" and mid:
                if mid in ledger["committed"]:
                    verdict = "benign"
                elif mid in ledger["working"]:
                    detail += " (logged, not committed)"
        ukey = (user, mailbox, str(msg.get("uid")))
        if verdict == "benign":
            tally["benign"] += 1
            clean[ukey] = True
            continue
        tally["red"] += 1
        clean[ukey] = False
        red[(code, detail)] = red.get((code, detail), 0) + 1


def server_summary(tally: dict) -> list:
    """The one summary line of a run that read server mail (not a finding)."""
    if not tally["messages"]:
        return []
    return [
        "server-reports: %d unread message(s), %d benign (marked Seen), %d red (left unread)"
        % (tally["messages"], tally["benign"], tally["red"])
    ]


def server_lines(red: dict) -> list:
    """The red groups, largest first, capped at SERVER_RED_LINES."""
    lines: list = []
    ordered = sorted(red.items(), key=lambda kv: (-kv[1], kv[0]))
    reds = ["%s: %s, %d message(s)" % (code, detail, n) for (code, detail), n in ordered]
    lines += reds[:SERVER_RED_LINES]
    if len(reds) > SERVER_RED_LINES:
        rest = ordered[SERVER_RED_LINES:]
        lines.append(
            "server-reports: %d more red group(s), %d message(s)"
            % (len(rest), sum(n for _, n in rest))
        )
    return lines


# --------------------------------------------------------------------------- judge


def _end_day(report: dict) -> datetime.date | None:
    end = report.get("end")
    if isinstance(end, int) and end > 0:
        return datetime.datetime.fromtimestamp(end, datetime.UTC).date()
    if isinstance(end, str) and end:
        try:
            return datetime.datetime.fromisoformat(end).date()
        except ValueError:
            return None
    return None


def _acked(known: dict, domain: str, report: dict) -> bool:
    through = known["acknowledged_through"].get(domain)
    day = _end_day(report)
    return through is not None and day is not None and day <= through


def _report_key(user: str, mailbox: str, msg: dict, report: dict) -> str:
    """A report's identity in the history: the reporter and its report id, else the message."""
    rid = str(report.get("report_id") or "")
    if rid:
        return "%s|%s" % (report.get("org") or "?", rid)
    return "%s|%s|uid %s" % (user, mailbox, msg.get("uid"))


class _Tally:
    """Red and ruled rows keyed by (code or ruling, domain, ip), each with a count and its reporters."""

    def __init__(self) -> None:
        self.rows: dict[tuple, dict] = {}

    def add(self, key: tuple, count: int, org: str, **extra) -> None:
        row = self.rows.setdefault(key, {"count": 0, "reporters": set(), **extra})
        row["count"] += count
        row["reporters"].add(org or "?")


def judge(
    doc: dict,
    known: dict,
    resolve: Resolver,
    history: dict,
    today: datetime.date,
    ledger: dict | None = None,
) -> dict:
    """{rc, findings, known, marks, counts, unreadable}. `findings` are the red lines, `known` the ruled silent failures, `marks` the uids to mark Seen. Records every ruled report's count into `history`."""
    rdns_cache: dict[str, str] = {}

    def rdns_of(ip: str) -> str:
        if ip not in rdns_cache:
            rdns_cache[ip] = resolve(ip)
        return rdns_cache[ip]

    red, ruled = _Tally(), _Tally()
    malformed: list[str] = []
    unreadable: list[str] = []
    counts = {"aggregate": 0, "tlsrpt": 0, "other": 0, "records": 0, "failed": 0}
    # (ruling name, ISO day) -> [(message key, domain, acknowledged)] for the volume pass.
    ruled_days: dict[tuple, list] = {}
    clean: dict[tuple, bool] = {}
    server_red: dict[tuple, int] = {}
    server_tally = {"messages": 0, "benign": 0, "red": 0}
    if not history.get("first"):
        history["first"] = today.isoformat()

    for box in doc.get("mailboxes") or []:
        user, mailbox = str(box.get("user") or ""), str(box.get("mailbox") or "")
        if box.get("error"):
            unreadable.append("%s %s: %s" % (user, mailbox, box["error"]))
            continue
        if box.get("kind") == "server-reports":
            judge_server_box(box, known["server"], clean, server_red, server_tally, ledger)
            continue
        for msg in box.get("messages") or []:
            kind = msg.get("kind")
            if kind == "other":
                counts["other"] += 1
                continue
            if kind != "report":
                malformed.append(
                    "dmarc.report.malformed: %s %s uid %s %r: %s"
                    % (
                        user,
                        mailbox,
                        msg.get("uid") or "?",
                        msg.get("subject") or "",
                        msg.get("error"),
                    )
                )
                continue
            ukey = (user, mailbox, str(msg.get("uid")))
            clean[ukey] = True
            for report in msg.get("reports") or []:
                org = str(report.get("org") or "")
                if report.get("type") == "tlsrpt":
                    counts["tlsrpt"] += 1
                    for policy in report.get("policies") or []:
                        domain = str(policy.get("domain") or "")
                        if not policy.get("failed") or _acked(known, domain, report):
                            continue
                        clean[ukey] = False
                        kinds = sorted({str(f.get("result")) for f in policy.get("failures") or []})
                        red.add(
                            ("dmarc.tlsrpt.failure", domain, ""),
                            int(policy["failed"]),
                            org,
                            why=", ".join(kinds) or "unspecified",
                        )
                    continue
                counts["aggregate"] += 1
                domain = str(report.get("domain") or "")
                day = _end_day(report)
                acked = _acked(known, domain, report)
                ruled_counts: dict[str, int] = {}
                for rec in report.get("records") or []:
                    counts["records"] += 1
                    ip = str(rec.get("ip") or "")
                    count = int(rec.get("count") or 0)
                    passed = "pass" in (rec.get("dkim"), rec.get("spf"))
                    why = "dkim %s, spf %s" % (rec.get("dkim") or "?", rec.get("spf") or "?")
                    if not passed:
                        counts["failed"] += count

                    def lookup(ip: str = ip) -> str:
                        return rdns_of(ip)

                    ours = match(known["ours"], ip, lookup)
                    if ours is not None:
                        if not passed and not acked:
                            clean[ukey] = False
                            red.add(
                                ("dmarc.ours.failing", domain, ip),
                                count,
                                org,
                                why=why,
                                name=ours["name"],
                            )
                        continue
                    ruling = match(known["rulings"], ip, lookup, domain)
                    if ruling is not None:
                        ruled_counts[ruling["name"]] = ruled_counts.get(ruling["name"], 0) + count
                        if passed and not acked:
                            clean[ukey] = False
                            red.add(
                                ("dmarc.ruled.passing", domain, ip),
                                count,
                                org,
                                why=why,
                                name=ruling["name"],
                                verdict=ruling["verdict"],
                            )
                        elif not passed:
                            ruled.add(
                                (ruling["name"], domain, ip),
                                count,
                                org,
                                ruled=ruling["ruled"],
                                verdict=ruling["verdict"],
                            )
                        continue
                    if not passed:
                        clean[ukey] = False
                        red.add(("dmarc.source.new", domain, ip), count, org, why=why)
                key = _report_key(user, mailbox, msg, report)
                for name, count in ruled_counts.items():
                    iso_day = (day or today).isoformat()
                    history["reports"]["%s|%s" % (key, name)] = {
                        "ruling": name,
                        "day": iso_day,
                        "count": count,
                    }
                    ruled_days.setdefault((name, iso_day), []).append((ukey, domain, acked))

    volume_lines = []
    for (name, iso_day), hits in sorted(ruled_days.items()):
        reason = volume_reason(history, name, iso_day, known["volume"])
        live = [h for h in hits if not h[2]]
        if not reason or not live:
            continue
        for ukey, _domain, _acked_flag in live:
            clean[ukey] = False
        domains = ", ".join(sorted({h[1] for h in live}))
        volume_lines.append("dmarc.ruled.volume: %s (%s): %s" % (name, domains, reason))

    findings = []
    for (code, domain, ip), row in sorted(red.rows.items()):
        reporters = ", ".join(sorted(row["reporters"]))
        rdns = rdns_of(ip) if ip else ""
        if code == "dmarc.tlsrpt.failure":
            findings.append(
                "%s: %s, %d failed TLS session(s) (%s), reported by %s"
                % (code, domain, row["count"], row["why"], reporters)
            )
        elif code == "dmarc.ours.failing":
            findings.append(
                "%s: %s from %s (%s, rdns %s) failed DMARC in %d message(s) (%s), reported by %s"
                % (
                    code,
                    domain,
                    ip,
                    row["name"],
                    rdns or "none",
                    row["count"],
                    row["why"],
                    reporters,
                )
            )
        elif code == "dmarc.ruled.passing":
            findings.append(
                "%s: %s from %s (%s, %s, rdns %s) PASSED DMARC in %d message(s) (%s), reported by %s; "
                "DNS still authorizes it"
                % (
                    code,
                    domain,
                    ip,
                    row["name"],
                    row["verdict"],
                    rdns or "none",
                    row["count"],
                    row["why"],
                    reporters,
                )
            )
        else:
            findings.append(
                "%s: %s from %s (rdns %s) failed DMARC in %d message(s) (%s), reported by %s; "
                "ask the operator, then add a ruling to %s"
                % (code, domain, ip, rdns or "none", row["count"], row["why"], reporters, KNOWN_REL)
            )
    findings += volume_lines + malformed
    findings += server_lines(server_red)
    findings += ["dmarc.mail.unreadable: %s" % u for u in unreadable]
    known_lines = [
        "%s %s (ruled %s): %s from %s failed DMARC in %d message(s), expected"
        % (row["verdict"], name, row["ruled"], domain, ip, row["count"])
        for (name, domain, ip), row in sorted(ruled.rows.items())
    ]
    marks: dict[tuple, list] = {}
    for (user, mailbox, uid), ok in clean.items():
        if ok:
            marks.setdefault((user, mailbox), []).append(uid)
    return {
        "rc": 1 if findings else 0,
        "findings": findings,
        "known": known_lines,
        "marks": marks,
        "counts": counts,
        "server": server_tally,
        "server_summary": server_summary(server_tally),
        "unreadable": unreadable,
    }


# --------------------------------------------------------------------------- entry


def run(
    root: pathlib.Path,
    *,
    runner: Runner = run_process,
    env: dict | None = None,
    resolve: Resolver = forward_confirmed_rdns,
    mark: bool = True,
    today: datetime.date | None = None,
) -> dict:
    """{rc, lines, ...}: the verdict and the lines to print, the red ones last (ops_health keeps the output's tail)."""
    env = dict(os.environ if env is None else env)
    today = today or datetime.datetime.now(datetime.UTC).date()
    try:
        known = load_known(root / KNOWN_REL)
    except KnownError as exc:
        return {"rc": 2, "lines": ["dmarc: rulings unreadable: %s" % exc]}
    doc, error = read_reports(known, runner, env)
    if doc is None:
        return {"rc": 1, "lines": ["dmarc.mail.unreadable: %s" % error]}
    hpath = history_path(root)
    history, history_error = load_history(hpath)
    verdict = judge(doc, known, resolve, history, today, load_ledger(root))
    save_error = save_history(hpath, history, today)
    # A history that could not be written leaves the reports unread, so the next run records their counts; a history that could not be read is unknown, not green.
    marks = {} if save_error else verdict["marks"]
    marked = sum(len(v) for v in marks.values())
    mark_error = mark_seen(known, marks, runner, env) if mark else ""
    counts = verdict["counts"]
    lines = [
        "dmarc: %d unread aggregate report(s), %d TLS-RPT report(s), %d other message(s) left alone; "
        "%d failing message(s); %s"
        % (
            counts["aggregate"],
            counts["tlsrpt"],
            counts["other"],
            counts["failed"],
            ("%d report message(s) marked Seen" % marked)
            if mark
            else "Seen marking skipped (--no-mark)",
        )
    ]
    lines += verdict["known"]
    lines += verdict["server_summary"]
    lines += ["history: %s" % e for e in (history_error, save_error) if e]
    rc = verdict["rc"]
    if history_error or save_error:
        rc = worst_rc([rc, 2])
    if mark_error:
        lines.append("dmarc.mail.unreadable: %s" % mark_error)
        rc = worst_rc([rc, 1])
    lines += verdict["findings"]
    if rc == 0:
        lines.append("dmarc: green, no new failing source, ours and the ruled sources as expected")
    return {**verdict, "rc": rc, "lines": lines, "mark_error": mark_error}


def main(argv: list | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="rediacc_ci.ops.dmarc_reports", description=__doc__.splitlines()[0]
    )
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--no-mark", action="store_true", help="read and judge, mark nothing Seen")
    parser.add_argument(
        "--log",
        action="store_true",
        help="append the red Server-Reports messages to %s (hashed ids, no address) and print the commit form"
        % LEDGER_REL,
    )
    args = parser.parse_args(argv)
    if args.log:
        logged = log_events(repo_root())
        for line in logged["lines"]:
            print(line)
        return int(logged["rc"])
    out = run(repo_root(), mark=not args.no_mark)
    if args.json:
        out["marks"] = {"%s %s" % k: v for k, v in (out.get("marks") or {}).items()}
        print(json.dumps(out, indent=2))
    else:
        for line in out["lines"]:
            print(line)
    return int(out["rc"])


if __name__ == "__main__":
    sys.exit(main())
