#!/usr/bin/env python3
"""Create the universal `rediacc` OS user the real-sandbox tests drop privileges to.

`requireSandboxUser` (cmd/renet) fails under CI=true when the user is absent. The uid, gid and flags match `renet setup` (ensureUniversalUser). A pre-existing `rediacc` user with another uid or gid would run the tests under the wrong identity, so it is refused instead of passing silently.

Run locally: PYTHONPATH=.ci python3 -m rediacc_ci.ci.ensure_rediacc_user
Requires: passwordless sudo when the user does not exist yet.
"""

from __future__ import annotations

import subprocess
import sys

NAME = "rediacc"
ID = "7111"


def _out(*argv: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, capture_output=True, text=True, check=False)


def main() -> int:
    if _out("id", NAME).returncode != 0:
        subprocess.run(["sudo", "groupadd", "--gid", ID, NAME], check=True)
        subprocess.run(
            [
                "sudo", "useradd", "--system", "--uid", ID, "--gid", ID,
                "--no-create-home", "--shell", "/sbin/nologin", NAME,
            ],
            check=True,
        )  # fmt: skip
    uid = _out("id", "-u", NAME).stdout.strip()
    gid = _out("id", "-g", NAME).stdout.strip()
    if (uid, gid) != (ID, ID):
        print(
            f"::error::the {NAME} user exists but is not uid/gid {ID}: {_out('id', NAME).stdout.strip()}"
        )
        return 1
    print(_out("id", NAME).stdout.strip())
    return 0


if __name__ == "__main__":
    sys.exit(main())
