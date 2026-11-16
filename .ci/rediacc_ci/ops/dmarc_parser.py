"""The DMARC report reader that runs INSIDE the mail container (rediacc_ci.ops.dmarc_reports streams this file's source into `docker exec -i <container> python3 -I -`, so nothing is written on the machine).

Self-contained on purpose: the standard library only, no import from rediacc_ci, and Python 3.11 syntax (the docker-mailserver image's interpreter). The local side imports it too: the tests, and rediacc_ci.ops.dmarc_reports for MARKER and to read this file's source for the stream.

    python3 -I - <base64 of {"mailboxes": [{"user": ..., "mailbox": ...}]}>

For each mailbox it lists the UNSEEN messages with `doveadm -f json fetch -u <user> "uid text" mailbox <mailbox> unseen` (a read: fetching `text` sets no flag) and parses each one. One stdout line carries the result, prefixed with MARKER:

    {"mailboxes": [{"user", "mailbox", "error", "messages": [{"uid", "subject", "kind", "reports", "error"}]}]}

`kind` is `report` (every report attachment parsed), `malformed` (a report attachment that could not be read; `error` names the attachment and why) or `other` (no report attachment: mail the sieve rule filed here that is not a report). A report is `{"type": "aggregate", ...}` (RFC 7489 XML, plain, zip or gzip) or `{"type": "tlsrpt", ...}` (RFC 8460 JSON, plain or gzip). The XML reader is expat with every DOCTYPE and entity declaration refused, so a report cannot expand an entity, and every decompression is capped at MAX_BYTES.
"""

from __future__ import annotations

import base64
import binascii
import email
import email.policy
import gzip
import io
import json
import subprocess
import sys
import zipfile
import zlib
from collections.abc import Callable
from email.message import EmailMessage
from xml.parsers import expat

MARKER = "DMARC-PARSER-JSON "
MAX_BYTES = 32 * 1024 * 1024
DOVEADM_TIMEOUT_S = 120

REPORT_TYPES = {
    "application/zip",
    "application/x-zip",
    "application/x-zip-compressed",
    "application/gzip",
    "application/x-gzip",
    "application/xml",
    "text/xml",
    "application/tlsrpt+gzip",
    "application/tlsrpt+json",
}
REPORT_SUFFIXES = (".xml", ".xml.gz", ".zip", ".gz", ".json", ".json.gz")


class ReportError(ValueError):
    """A report attachment that cannot be read; the message names the attachment and the reason."""


class FetchError(RuntimeError):
    """A mailbox that cannot be listed; the message names the user, the mailbox and the failure."""


# --------------------------------------------------------------------------- XML


class Node:
    """One XML element: its local name (namespace dropped), children and text."""

    def __init__(self, tag: str) -> None:
        self.tag = tag
        self.children: list[Node] = []
        self.text = ""

    def find(self, path: str) -> Node | None:
        node: Node | None = self
        for part in path.split("/"):
            if node is None:
                return None
            node = next((c for c in node.children if c.tag == part), None)
        return node

    def findall(self, tag: str) -> list[Node]:
        return [c for c in self.children if c.tag == tag]

    def get(self, path: str) -> str:
        node = self.find(path)
        return node.text.strip() if node is not None else ""


def parse_xml(data: bytes) -> Node:
    """The document's root element. Raises ReportError on bad XML, a DOCTYPE or an entity declaration."""
    parser = expat.ParserCreate(namespace_separator="}")
    stack: list[Node] = []
    roots: list[Node] = []

    def refuse(*_args: object) -> None:
        msg = "DOCTYPE or entity declaration refused"
        raise ReportError(msg)

    def start(name: str, _attrs: object) -> None:
        node = Node(name.rsplit("}", 1)[-1])
        if stack:
            stack[-1].children.append(node)
        else:
            roots.append(node)
        stack.append(node)

    def end(_name: str) -> None:
        stack.pop()

    def text(chunk: str) -> None:
        if stack:
            stack[-1].text += chunk

    parser.StartDoctypeDeclHandler = refuse
    parser.EntityDeclHandler = refuse
    parser.StartElementHandler = start
    parser.EndElementHandler = end
    parser.CharacterDataHandler = text
    try:
        parser.Parse(data, True)
    except expat.ExpatError as exc:
        raise ReportError("XML does not parse: %s" % exc) from None
    if not roots:
        msg = "XML has no root element"
        raise ReportError(msg)
    return roots[0]


def _int(text: object, what: str) -> int:
    try:
        return int(str(text))
    except ValueError:
        raise ReportError("%s %r is not an integer" % (what, text)) from None


def parse_aggregate(data: bytes) -> dict:
    """An RFC 7489 aggregate report as {type, org, report_id, begin, end, domain, policy, records}."""
    root = parse_xml(data)
    if root.tag != "feedback":
        raise ReportError("root element is <%s>, not <feedback>" % root.tag)
    domain = root.get("policy_published/domain").lower()
    if not domain:
        msg = "policy_published/domain is missing"
        raise ReportError(msg)
    records = []
    for rec in root.findall("record"):
        ip = rec.get("row/source_ip")
        if not ip:
            msg = "a record has no row/source_ip"
            raise ReportError(msg)
        auth = rec.find("auth_results")
        records.append(
            {
                "ip": ip,
                "count": _int(rec.get("row/count") or "0", "row/count"),
                "disposition": rec.get("row/policy_evaluated/disposition"),
                "dkim": rec.get("row/policy_evaluated/dkim").lower(),
                "spf": rec.get("row/policy_evaluated/spf").lower(),
                "header_from": rec.get("identifiers/header_from").lower(),
                "dkim_domains": [
                    "%s=%s" % (n.get("domain").lower(), n.get("result").lower())
                    for n in (auth.findall("dkim") if auth is not None else [])
                ],
                "spf_domains": [
                    "%s=%s" % (n.get("domain").lower(), n.get("result").lower())
                    for n in (auth.findall("spf") if auth is not None else [])
                ],
            }
        )
    return {
        "type": "aggregate",
        "org": root.get("report_metadata/org_name"),
        "report_id": root.get("report_metadata/report_id"),
        "begin": _int(root.get("report_metadata/date_range/begin") or "0", "date_range/begin"),
        "end": _int(root.get("report_metadata/date_range/end") or "0", "date_range/end"),
        "domain": domain,
        "policy": root.get("policy_published/p"),
        "records": records,
    }


# --------------------------------------------------------------------------- TLS-RPT


def parse_tlsrpt(data: bytes) -> dict:
    """An RFC 8460 TLS report as {type, org, report_id, end, policies: [{domain, type, ok, failed, failures}]}."""
    try:
        doc = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise ReportError("TLS-RPT JSON does not parse: %s" % exc) from None
    if not isinstance(doc, dict) or not isinstance(doc.get("policies"), list):
        msg = "TLS-RPT JSON has no policies list"
        raise ReportError(msg)
    policies = []
    for entry in doc["policies"]:
        if not isinstance(entry, dict):
            msg = "a TLS-RPT policy is not an object"
            raise ReportError(msg)
        policy = entry.get("policy") or {}
        summary = entry.get("summary") or {}
        if not isinstance(policy, dict) or not isinstance(summary, dict):
            msg = "a TLS-RPT policy or summary is not an object"
            raise ReportError(msg)
        failures = [
            {
                "result": str(f.get("result-type") or ""),
                "ip": str(f.get("sending-mta-ip") or ""),
                "mx": str(f.get("receiving-mx-hostname") or ""),
                "count": _int(f.get("failed-session-count") or 0, "failed-session-count"),
            }
            for f in entry.get("failure-details") or []
            if isinstance(f, dict)
        ]
        policies.append(
            {
                "domain": str(policy.get("policy-domain") or "").lower(),
                "type": str(policy.get("policy-type") or ""),
                "ok": _int(
                    summary.get("total-successful-session-count") or 0, "total-successful-session-count"
                ),
                "failed": _int(
                    summary.get("total-failure-session-count") or 0, "total-failure-session-count"
                ),
                "failures": failures,
            }
        )
    dates = doc.get("date-range") or {}
    return {
        "type": "tlsrpt",
        "org": str(doc.get("organization-name") or ""),
        "report_id": str(doc.get("report-id") or ""),
        "end": str(dates.get("end-datetime") or "") if isinstance(dates, dict) else "",
        "policies": policies,
    }


# --------------------------------------------------------------------------- attachments


def _gunzip(data: bytes) -> bytes:
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(data)) as fh:
            out = fh.read(MAX_BYTES + 1)
    except (OSError, EOFError, zlib.error) as exc:
        raise ReportError("gzip does not decompress: %s" % exc) from None
    if len(out) > MAX_BYTES:
        raise ReportError("gzip expands past %d bytes" % MAX_BYTES)
    return out


def _unzip(data: bytes) -> bytes:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            names = [n for n in zf.namelist() if n.lower().endswith((".xml", ".json"))]
            if not names:
                raise ReportError("zip holds no .xml or .json member (%s)" % zf.namelist())
            with zf.open(names[0]) as fh:
                out = fh.read(MAX_BYTES + 1)
    except (zipfile.BadZipFile, OSError, EOFError, zlib.error) as exc:
        raise ReportError("zip does not open: %s" % exc) from None
    if len(out) > MAX_BYTES:
        raise ReportError("zip member expands past %d bytes" % MAX_BYTES)
    return out


def decode_report(name: str, ctype: str, data: bytes) -> dict:
    """One attachment's report. The container is read from the bytes (zip and gzip magic), not trusted from the name; the report type from the content."""
    if data[:4] == b"PK\x03\x04":
        data = _unzip(data)
    elif data[:2] == b"\x1f\x8b":
        data = _gunzip(data)
    body = data.lstrip()
    if body.startswith(b"<"):
        return parse_aggregate(data)
    if body.startswith(b"{"):
        return parse_tlsrpt(data)
    raise ReportError("%s (%s) is neither XML nor JSON after decompression" % (name or "?", ctype))


def is_report_part(part: EmailMessage) -> bool:
    ctype = part.get_content_type().lower()
    name = (part.get_filename() or "").lower()
    if ctype in REPORT_TYPES or name.endswith(REPORT_SUFFIXES):
        return True
    if ctype != "application/octet-stream" or not name:
        return False
    # A generic attachment is a report candidate only when its bytes look like one (zip or gzip magic, XML or JSON), so a PDF sent as octet-stream stays "other".
    try:
        head = part.get_payload(decode=True)
    except (binascii.Error, ValueError):
        return True
    if not isinstance(head, bytes):
        return False
    return head[:4] == b"PK\x03\x04" or head[:2] == b"\x1f\x8b" or head.lstrip()[:1] in (b"<", b"{")


def parse_message(raw: str | bytes) -> dict:
    """{subject, kind, reports, error} for one message; never raises."""
    data = raw.encode("utf-8", "surrogateescape") if isinstance(raw, str) else raw
    msg = email.message_from_bytes(data, policy=email.policy.default)
    subject = str(msg.get("Subject") or "")
    reports: list[dict] = []
    errors: list[str] = []
    for part in msg.walk():
        if part.is_multipart() or not isinstance(part, EmailMessage) or not is_report_part(part):
            continue
        name = part.get_filename() or ""
        ctype = part.get_content_type()
        try:
            payload = part.get_payload(decode=True)
        except (binascii.Error, ValueError) as exc:
            errors.append("%s (%s): transfer encoding does not decode: %s" % (name, ctype, exc))
            continue
        if not isinstance(payload, bytes) or not payload:
            errors.append("%s (%s): empty attachment" % (name or "?", ctype))
            continue
        try:
            reports.append(decode_report(name, ctype, payload))
        except ReportError as exc:
            errors.append("%s (%s): %s" % (name or "?", ctype, exc))
    if errors:
        return {
            "subject": subject,
            "kind": "malformed",
            "reports": reports,
            "error": "; ".join(errors),
        }
    return {
        "subject": subject,
        "kind": "report" if reports else "other",
        "reports": reports,
        "error": "",
    }


# --------------------------------------------------------------------------- doveadm


# (user, mailbox) -> [{"uid": ..., "text": ...}]; raises FetchError naming the failure.
Fetch = Callable[[str, str], list]


def doveadm_fetch(user: str, mailbox: str) -> list:
    argv = ["doveadm", "-f", "json", "fetch", "-u", user, "uid text", "mailbox", mailbox, "unseen"]
    try:
        proc = subprocess.run(
            argv, capture_output=True, text=True, timeout=DOVEADM_TIMEOUT_S, check=False
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise FetchError("doveadm fetch %s %s: %s" % (user, mailbox, exc)) from None
    if proc.returncode != 0:
        raise FetchError(
            "doveadm fetch %s %s rc %d: %s"
            % (user, mailbox, proc.returncode, proc.stderr.strip()[-300:])
        )
    text = proc.stdout.strip()
    if not text:
        return []
    try:
        rows = json.loads(text)
    except ValueError:
        raise FetchError(
            "doveadm fetch %s %s printed no JSON: %s" % (user, mailbox, text[:200])
        ) from None
    if not isinstance(rows, list):
        raise FetchError("doveadm fetch %s %s printed a non-list" % (user, mailbox))
    return rows


def collect(mailboxes: list, fetch: Fetch) -> dict:
    """The whole result document for `mailboxes`; a mailbox that cannot be read carries its `error`."""
    out = []
    for box in mailboxes:
        user, mailbox = str(box["user"]), str(box["mailbox"])
        entry: dict = {"user": user, "mailbox": mailbox, "error": "", "messages": []}
        try:
            rows = fetch(user, mailbox)
        except FetchError as exc:
            entry["error"] = str(exc)
            out.append(entry)
            continue
        for row in rows:
            uid = str(row.get("uid") or "") if isinstance(row, dict) else ""
            if not uid:
                entry["messages"].append(
                    {
                        "uid": "",
                        "subject": "",
                        "kind": "malformed",
                        "reports": [],
                        "error": ("doveadm row without a uid: %r" % (row,))[:200],
                    }
                )
                continue
            parsed = parse_message(str(row.get("text") or ""))
            entry["messages"].append({"uid": uid, **parsed})
        out.append(entry)
    return {"mailboxes": out}


def main(argv: list) -> int:
    if len(argv) != 2:
        print('usage: python3 -I - <base64 JSON of {"mailboxes": [...]}>', file=sys.stderr)
        return 2
    try:
        spec = json.loads(base64.b64decode(argv[1]).decode("utf-8"))
        mailboxes = spec["mailboxes"]
    except (binascii.Error, UnicodeDecodeError, ValueError, KeyError, TypeError) as exc:
        print(
            "dmarc_parser: the argument is not base64 JSON with mailboxes: %s" % exc,
            file=sys.stderr,
        )
        return 2
    print(MARKER + json.dumps(collect(mailboxes, doveadm_fetch), separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
