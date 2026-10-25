"""In-memory S3 stub, the CONTROL for `python3 -m rediacc_ci.infra.elite_s3_probe --selftest`.

It speaks just the surface private/elite/scripts/s3-conformance-probe.sh exercises (list, PUT/GET/HEAD/DELETE,
presigned requests, DeleteObjects, multipart) and verifies no signature. Two behaviours, chosen by a flag:

  (default)                 conformant: a second `PUT If-None-Match: *` on an existing key answers 412
  --ignore-if-none-match    NON-CONFORMANT: the second PUT overwrites and answers 200, the exact failure the
                            probe's load-bearing step exists to catch

Prints `READY <port>` on stdout once listening, then serves until killed. Not a product component and never
shipped; it exists so the probe's red path is exercised on every selftest instead of assumed.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

OBJECTS: dict[str, bytes] = {}
UPLOADS: dict[str, dict[int, bytes]] = {}
XML = {"Content-Type": "application/xml"}


def etag(body: bytes) -> str:
    return '"%s"' % hashlib.sha256(body).hexdigest()[:32]


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    ignore_if_none_match = False

    def log_message(self, *_args: object) -> None:  # keep the probe's output readable
        return

    def _reply(self, code: int, body: bytes = b"", headers: dict[str, str] | None = None) -> None:
        self.send_response(code)
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _body(self) -> bytes:
        n = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(n) if n else b""

    def _split(self) -> tuple[str, dict[str, list[str]]]:
        u = urlsplit(self.path)
        return u.path, parse_qs(u.query, keep_blank_values=True)

    def do_GET(self) -> None:
        path, q = self._split()
        if "list-type" in q or path.count("/") <= 1:
            self._reply(200, b"<ListBucketResult></ListBucketResult>", XML)
        elif path in OBJECTS:
            self._reply(200, OBJECTS[path], {"ETag": etag(OBJECTS[path])})
        else:
            self._reply(404, b"<Error><Code>NoSuchKey</Code></Error>")

    def do_HEAD(self) -> None:
        self.do_GET()

    def do_PUT(self) -> None:
        path, q = self._split()
        body = self._body()
        if "uploadId" in q and "partNumber" in q:
            UPLOADS.setdefault(q["uploadId"][0], {})[int(q["partNumber"][0])] = body
            self._reply(200, b"", {"ETag": etag(body)})
            return
        if (
            self.headers.get("If-None-Match") == "*"
            and path in OBJECTS
            and not self.ignore_if_none_match
        ):
            self._reply(412, b"<Error><Code>PreconditionFailed</Code></Error>")
            return
        OBJECTS[path] = body
        self._reply(200, b"", {"ETag": etag(body)})

    def do_DELETE(self) -> None:
        path, q = self._split()
        if "uploadId" in q:
            UPLOADS.pop(q["uploadId"][0], None)
        else:
            OBJECTS.pop(path, None)
        self._reply(204)

    def do_POST(self) -> None:
        path, q = self._split()
        body = self._body()
        if "uploads" in q:
            uid = "stub-upload-%d" % len(UPLOADS)
            UPLOADS[uid] = {}
            xml = (
                "<InitiateMultipartUploadResult><UploadId>%s</UploadId></InitiateMultipartUploadResult>"
                % uid
            )
            self._reply(200, xml.encode(), XML)
        elif "uploadId" in q:
            parts = UPLOADS.pop(q["uploadId"][0], {})
            OBJECTS[path] = b"".join(parts[n] for n in sorted(parts))
            self._reply(
                200, b"<CompleteMultipartUploadResult></CompleteMultipartUploadResult>", XML
            )
        elif "delete" in q:
            bucket = "/" + path.strip("/").split("/")[0]
            keys = re.findall(rb"<Key>([^<]*)</Key>", body)
            for k in keys:
                OBJECTS.pop("%s/%s" % (bucket, k.decode()), None)
            out = "".join("<Deleted><Key>%s</Key></Deleted>" % k.decode() for k in keys)
            self._reply(200, ("<DeleteResult>%s</DeleteResult>" % out).encode(), XML)
        else:
            self._reply(400, b"<Error><Code>BadRequest</Code></Error>")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ignore-if-none-match", action="store_true")
    Handler.ignore_if_none_match = ap.parse_args().ignore_if_none_match
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    print("READY %d" % srv.server_address[1], flush=True)
    srv.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
