"""`python -m rediacc_ci.lab.testca <dir> <host>...` (PLAN-enterprise-tenants box C12): a throwaway CA and one certificate per host for the bring-your-own-TLS drills.

Writes `ca.crt`, `ca.key`, and for each host `<host>.crt` and `<host>.key`. Each certificate's subjectAltName is exactly its own host (an IP literal as an IP entry, a name as a DNS entry), never a wildcard: a host starting with `*` is refused. Needs `openssl`. Test material only; the keys are not protected.

EXIT CODES. 0 written; 1 openssl failed; 2 usage or a refused host.
"""

from __future__ import annotations

import ipaddress
import pathlib
import subprocess
import sys
import tempfile
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

USAGE = "usage: PYTHONPATH=.ci python3 -m rediacc_ci.lab.testca <dir> <host>..."
DAYS = "30"


def san_entry(host: str) -> str:
    if not host or "*" in host or any(c.isspace() or c in ",;=" for c in host):
        raise ValueError("refused host %r: a per-host name or IP, never a wildcard" % host)
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return "DNS:%s" % host
    return "IP:%s" % host


def openssl(*args: str) -> None:
    subprocess.run(["openssl", *args], check=True, capture_output=True)


def write(out: pathlib.Path, hosts: Sequence[str]) -> list[pathlib.Path]:
    sans = {h: san_entry(h) for h in hosts}
    out.mkdir(parents=True, exist_ok=True)
    ca_key, ca_crt = out / "ca.key", out / "ca.crt"
    ca_args = [
        "-x509",
        "-newkey",
        "rsa:2048",
        "-nodes",
        "-keyout",
        str(ca_key),
        "-out",
        str(ca_crt),
    ]
    ca_args += ["-days", DAYS, "-subj", "/CN=Rediacc Test CA"]
    ca_args += [
        "-addext",
        "basicConstraints=critical,CA:TRUE",
        "-addext",
        "keyUsage=critical,keyCertSign,cRLSign",
    ]
    openssl("req", *ca_args)
    written = [ca_crt]
    for host, san in sans.items():
        key, crt = out / ("%s.key" % host), out / ("%s.crt" % host)
        with tempfile.TemporaryDirectory() as tmp:
            csr, ext = pathlib.Path(tmp, "h.csr"), pathlib.Path(tmp, "h.ext")
            ext.write_text(
                "subjectAltName=%s\nbasicConstraints=CA:FALSE\nextendedKeyUsage=serverAuth\n" % san
            )
            req = [
                "-newkey",
                "rsa:2048",
                "-nodes",
                "-keyout",
                str(key),
                "-out",
                str(csr),
                "-subj",
                "/CN=%s" % host,
            ]
            openssl("req", *req)
            sign = [
                "-req",
                "-in",
                str(csr),
                "-CA",
                str(ca_crt),
                "-CAkey",
                str(ca_key),
                "-CAcreateserial",
            ]
            sign += ["-out", str(crt), "-days", DAYS, "-extfile", str(ext)]
            openssl("x509", *sign)
        key.chmod(0o600)
        written += [crt, key]
    return written


def main(argv: Sequence[str]) -> int:
    if len(argv) < 2:
        print(USAGE, file=sys.stderr)
        return 2
    try:
        files = write(pathlib.Path(argv[0]), argv[1:])
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 2
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        print("openssl failed: %s" % exc, file=sys.stderr)
        return 1
    for f in files:
        print(f)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
