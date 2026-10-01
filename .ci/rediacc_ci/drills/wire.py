"""Wire helpers shared by the `license` and `backup` drill ports: raw HTTP with the status kept, JS-flavoured value formatting, the workstation's address on the VM network, and a SigV4 signer for the one store write the drill makes itself.

These replace what the bash twins did with `curl`, `node -e`, `awk` and `curl --aws-sigv4` (Rule T: no tool the drill did not already need Python for; `curl` 7.75+ is no longer a precondition). Every helper is deliberately small and takes the values it needs: the drills own the state.
"""

from __future__ import annotations

import datetime
import hashlib
import hmac
import json
import re
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import http.cookiejar

MISSING = object()


def lookup(value: object, path: str) -> object:
    """The node at `path` (`a.b`, `a[0].b`) in parsed JSON, or the `MISSING` sentinel. Mirrors the property walk of `d.a.b` where an absent branch is `undefined`."""
    for key, index in re.findall(r"([A-Za-z0-9_$-]+)|\[(\d+)\]", path):
        if key:
            if not isinstance(value, dict) or key not in value:
                return MISSING
            value = value[key]
        else:
            if not isinstance(value, list) or int(index) >= len(value):
                return MISSING
            value = value[int(index)]
    return value


def parse(raw: str) -> object:
    """Parsed JSON, or the `MISSING` sentinel for text that is not JSON (the bash `drill_json` exited non-zero there)."""
    try:
        return json.loads(raw or "{}")
    except ValueError:
        return MISSING


def typeof(value: object) -> str:
    """JavaScript's `typeof` for a parsed-JSON node, `undefined` for an absent one."""
    if value is MISSING:
        return "undefined"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    return "object"


def jstr(value: object) -> str:
    """`String(v)` as `drill_json` printed it: empty for undefined and null, `true`/`false` for booleans, compact JSON for containers."""
    if value is MISSING or value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dict, list)):
        return json.dumps(value, separators=(",", ":"))
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def compact(value: object) -> str:
    """`JSON.stringify(v)`."""
    return json.dumps(value, separators=(",", ":"))


def iso_now() -> str:
    """`new Date().toISOString()`: UTC, millisecond precision, trailing Z."""
    now = datetime.datetime.now(datetime.UTC)
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + "%03dZ" % (now.microsecond // 1000)


def bridge_host(net_base: str) -> str | None:
    """This workstation's own address on a VM network (`192.168.111` -> `192.168.111.254`), or None when no interface sits on it, so a caller can fall back rather than advertise an address nothing can reach."""
    try:
        listing = subprocess.run(
            ["ip", "-4", "-o", "addr", "show"],
            capture_output=True,
            text=True,
            check=False,
        ).stdout
    except OSError:
        return None
    for line in listing.splitlines():
        fields = line.split()
        if len(fields) > 3:
            addr = fields[3].split("/", 1)[0]
            if addr.startswith(net_base + "."):
                return addr
    return None


def http_call(
    method: str,
    url: str,
    body: str | bytes | None = None,
    headers: dict[str, str] | None = None,
    jar: http.cookiejar.CookieJar | None = None,
    json_body: bool = True,
    timeout: float = 60.0,
) -> tuple[int, str]:
    """`http_bytes` with the body decoded as text (the API answers JSON)."""
    status, raw = http_bytes(method, url, body, headers, jar, json_body, timeout)
    return status, raw.decode(errors="replace")


def http_bytes(
    method: str,
    url: str,
    body: str | bytes | None = None,
    headers: dict[str, str] | None = None,
    jar: http.cookiejar.CookieJar | None = None,
    json_body: bool = True,
    timeout: float = 60.0,
) -> tuple[int, bytes]:
    """One request, the way the drills used `curl -sS -w '%{http_code}'`: returns (status, body text). An HTTP error status is NOT an exception, because the account server puts its reason in the body; a transport failure raises `OSError`.

    `json_body=False` sends the body with curl's `--data-binary` defaults (form content type), which is what a machine PUTting a presigned URL sends.
    """
    handlers: list[urllib.request.BaseHandler] = []
    if jar is not None:
        handlers.append(urllib.request.HTTPCookieProcessor(jar))
    opener = urllib.request.build_opener(*handlers)
    data = body.encode() if isinstance(body, str) else body
    request = urllib.request.Request(url, data=data, method=method)  # noqa: S310 -- the drill's own http gateway or store URL
    if data is not None and json_body:
        request.add_header("Content-Type", "application/json")
    for name, value in (headers or {}).items():
        request.add_header(name, value)
    try:
        with opener.open(request, timeout=timeout) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        with exc:
            return exc.code, exc.read()
    except urllib.error.URLError as exc:
        raise OSError("%s %s: %s" % (method, url, exc.reason)) from exc


def _hmac(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode(), hashlib.sha256).digest()


def sigv4_headers(
    method: str,
    url: str,
    payload: bytes,
    region: str,
    access_key: str,
    secret_key: str,
    now: datetime.datetime | None = None,
) -> dict[str, str]:
    """AWS Signature V4 headers for an S3 request (`curl --aws-sigv4 aws:amz:<region>:s3 -u key:secret`). Signs host, x-amz-content-sha256 and x-amz-date."""
    stamp = (now or datetime.datetime.now(datetime.UTC)).strftime("%Y%m%dT%H%M%SZ")
    day = stamp[:8]
    parsed = urllib.parse.urlsplit(url)
    payload_hash = hashlib.sha256(payload).hexdigest()
    canonical_query = "&".join(
        "%s=%s" % (urllib.parse.quote(k, safe="-_.~"), urllib.parse.quote(v, safe="-_.~"))
        for k, v in sorted(urllib.parse.parse_qsl(parsed.query, keep_blank_values=True))
    )
    signed = "host;x-amz-content-sha256;x-amz-date"
    canonical = "\n".join(
        [
            method,
            urllib.parse.quote(parsed.path or "/", safe="/-_.~"),
            canonical_query,
            "host:%s\nx-amz-content-sha256:%s\nx-amz-date:%s\n"
            % (parsed.netloc, payload_hash, stamp),
            signed,
            payload_hash,
        ]
    )
    scope = "%s/%s/s3/aws4_request" % (day, region)
    to_sign = "\n".join(
        ["AWS4-HMAC-SHA256", stamp, scope, hashlib.sha256(canonical.encode()).hexdigest()]
    )
    key = _hmac(
        _hmac(_hmac(_hmac(("AWS4" + secret_key).encode(), day), region), "s3"), "aws4_request"
    )
    signature = hmac.new(key, to_sign.encode(), hashlib.sha256).hexdigest()
    return {
        "x-amz-date": stamp,
        "x-amz-content-sha256": payload_hash,
        "Authorization": "AWS4-HMAC-SHA256 Credential=%s/%s, SignedHeaders=%s, Signature=%s"
        % (access_key, scope, signed, signature),
    }
